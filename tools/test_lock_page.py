"""
Run by hand (or at logon): the test lock's page, where the user says whether they are using the PC
and stops a running command (tools/test_lock.py).

A small web server on 127.0.0.1 only (port FINDALINE_LOCK_PAGE_PORT, default 8771), meant to stay
open as an Edge app window (`msedge --app=http://127.0.0.1:8771/`):

- four buttons set the user's state in the queue (test_lock.STATES; the queue's rules are in
  tools/test_lock.py's docstring): Free (everything runs), Heavy OK (no measurements; big untimed
  runs start below your programs' priority on at most 16 threads; tests keep running), Busy (no
  measurements start, tests keep running below your programs' priority), Quiet (nothing new
  starts); each with no end or until a time (in 1, 2 or 4 h, at 18:00 or 07:00, or any time),
  then another state (free, or busy after Free, unless chosen);
- the queue's running commands, each with Stop (asked once: its wrapper kills the command's
  process tree and exits 125, and the run never goes into the estimates), and the waiting ones
  with what holds them (the state, the commands they wait for, the slots);
- refreshed every 3 s, the browser's clock corrected by the server's.

    python tools/test_lock_page.py serve [--port N] [--verbose]
    python tools/test_lock_page.py install [--port N] [--dry-run]
    python tools/test_lock_page.py uninstall [--dry-run]

install (Windows) registers the scheduled task "Find-a-Line test lock page" (at the user's logon,
the main checkout's .venv pythonw.exe running the main checkout's copy of this script, restarted
every minute on failure, started at once) through Windows PowerShell's Register-ScheduledTask,
and writes the desktop shortcut "Test lock" (Edge as an app window, Edge's path from the
registry's App Paths; without Edge a plain `start` of the address); uninstall removes both;
--dry-run prints what either would do and changes nothing.

Routes: GET / (the page), /page.css, /page.js, /api/state ({state, now, slots, entries});
POST /api/state ({value, until, after, note}: until in epoch seconds or null), POST /api/stop
({id} of a running entry, else 404). A POST needs the header X-Test-Lock: 1 and an Origin that is
absent or the page's own (a page of another site can send neither), else 403; a Host other than
127.0.0.1 or localhost at the port is refused (DNS rebinding); other methods 405, other paths 404.
Every answer carries Content-Security-Policy: default-src 'self' (nothing inline). A request that
fails is answered with 500 and the server goes on.

Runs with the standard library and the test lock's module beside it (filelock); the queue is the
test lock's (FINDALINE_TEST_LOCK_DIR, else <git common dir>/findaline-locks/).
"""

import argparse
import base64
import json
import ntpath
import os
import re
import shlex
import socket
import socketserver
import subprocess
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_lock as tl  # noqa: E402

DEFAULT_PORT = 8771   # the app has 8765, 8766 and 8799, the Lock monitor 3300 and 5439
PORT = int(os.environ.get("FINDALINE_LOCK_PAGE_PORT", str(DEFAULT_PORT)))
TASK = "Find-a-Line test lock page"   # the scheduled task of install
SHORTCUT = "Test lock.lnk"            # on the desktop
BODY_MAX = 4096                       # bytes of a request's body
NOTE_MAX = 200                        # characters of a state's note
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
HELD_BY = {"busy": "held: the PC is in use", "quiet": "held: quiet", "memory": "held: not enough free memory"}
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                          "powershell.exe")


class BadRequest(ValueError):
    """A request answered with 400 and its text."""


# --- the queue as the page sees it ---------------------------------------------------------------

def state_json(state: tl.UserState, now: float) -> dict:
    return {"value": state.value, "since": state.since, "until": state.until, "after": state.after,
            "note": state.note, "text": tl.describe_state(state, now)}


def short_command(text: str, words: int = 4, width: int = 72) -> str:
    """A command shortened to its program or script and its first words (long paths by name)."""
    try:
        command = shlex.split(text)
    except ValueError:
        command = text.split()
    if not command:
        return ""
    i = tl.program_index(command)
    if i >= len(command):
        i = 0
    elif command[i].startswith("-") and i > 0:  # python -c ...: from python on
        i -= 1

    def word(w: str) -> str:
        w = " ".join(w.split())
        if len(w) > 24 and ("/" in w or "\\" in w):
            w = ntpath.basename(w.rstrip("/\\")) or w
        return w if len(w) <= 40 else w[:39] + "\u2026"

    shown = [tl._name(command[i]), *(word(w) for w in command[i + 1:i + 1 + words])]
    out = " ".join(shown) + (" \u2026" if len(command) > i + 1 + words else "")
    return out if len(out) <= width else out[:width - 1] + "\u2026"


def _reason(entry: tl.Entry, entries: List[tl.Entry], state: str, admitted: set, slots: int) -> str:
    """Why a waiting entry waits, in words."""
    hold = tl.held(entry, state)
    if hold is not None:
        return HELD_BY[hold]
    if entry.id in admitted:
        return "starting"
    blocking = [e for e in tl.blockers(entry, entries, state) if tl.conflicts(entry, e)]
    parts = []
    running = [f"#{e.id}" for e in blocking if e.started is not None]
    earlier = [f"#{e.id}" for e in blocking if e.started is None]
    if running:
        parts.append("waiting for " + ", ".join(running))
    if earlier:
        parts.append("behind " + ", ".join(earlier))
    if entry.mode == "shared" and sum(e.mode == "shared" and e.started is not None for e in entries) >= slots:
        parts.append(f"all {slots} shared slots taken")
    return "; ".join(parts) or "waiting its turn"


def snapshot(folder: str) -> dict:
    """The answer of GET /api/state: the user's state and the queue's live entries."""
    queue = tl.Queue(folder)
    try:
        queue.db.execute("BEGIN IMMEDIATE")
        try:
            entries = queue.live()
            now = time.time()
            state = queue.user_state(now)
            admitted = tl.startable(entries, now, queue.estimate, passing=lambda e: queue.estimate(e, passing=True),
                                    state=state.value)
        finally:
            queue.db.execute("COMMIT")
        rows = []
        for entry in sorted(entries, key=lambda e: (e.started is None, e.started or 0, tl.order(e))):
            estimate = queue.estimate(entry)
            waiting = entry.started is None
            rows.append({
                "id": entry.id, "mode": entry.mode, "resources": entry.resources, "owner": entry.owner,
                "command": entry.command, "short": short_command(entry.command),
                "kind": _kind(entry.command), "queued": entry.queued, "started": entry.started,
                "estimate": estimate,
                "expected_end": entry.started + estimate if not waiting and estimate is not None else None,
                "held_by": tl.held(entry, state.value) if waiting else None,
                "first": entry.first, "stop": entry.stop,
                "reason": _reason(entry, entries, state.value, admitted, tl.SLOTS) if waiting else None})
    finally:
        queue.db.close()
    return {"state": state_json(state, now), "now": now, "slots": tl.SLOTS, "entries": rows}


def _kind(text: str) -> Optional[str]:
    try:
        return tl.command_kind(shlex.split(text))
    except ValueError:
        return None


# --- the server ----------------------------------------------------------------------------------

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"   # on Windows SO_REUSEADDR would let a second server take the port

    def __init__(self, port: int, folder: str, verbose: bool = False):
        self.folder = folder
        self.verbose = verbose
        os.makedirs(folder, exist_ok=True)
        tl.Queue(folder).db.close()  # the queue's tables, once, before the first request
        super().__init__(("127.0.0.1", port), Handler)
        self.port = self.server_address[1]

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # HTTPServer's own asks socket.getfqdn(), which may wait for a reverse lookup on Windows
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "TestLockPage"

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args) -> None:
        if self.server.verbose and sys.stderr is not None:  # none under pythonw
            sys.stderr.write(f"{self.log_date_time_string()} {format % args}\n")

    def do_GET(self) -> None:
        self.sent = False
        try:
            self.body = self._read_body()
            if self.body is None:
                return self._json({"error": "the body is too large"}, 413)
            if not self._own_host():
                return self._json({"error": "unknown host"}, 403)
            route = ROUTES.get(urlsplit(self.path).path)
            if route is None:
                return self._json({"error": "not found"}, 404)
            handler = route.get(self.command)
            if handler is None:
                return self._json({"error": "method not allowed"}, 405, {"Allow": ", ".join(route)})
            if self.command == "POST" and not self._may_write():
                return self._json({"error": "refused: a change needs the header X-Test-Lock: 1 from the page itself"},
                                  403)
            handler(self)
        except BadRequest as error:
            self._json({"error": str(error)}, 400)
        except Exception as error:  # noqa: BLE001 (the server goes on)
            if sys.stderr is not None:
                traceback.print_exc()
            if not self.sent:
                try:
                    self._json({"error": f"internal error: {error}"}, 500)
                except Exception:  # noqa: BLE001 (the client went away)
                    pass

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_GET

    def _read_body(self) -> Optional[bytes]:
        """The request's body (read before any answer: an unread body may reset the connection
        on Windows before the answer is read); None when larger than BODY_MAX."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > BODY_MAX:
            self.close_connection = True
            if length <= 16 * BODY_MAX:
                self.rfile.read(length)
            return None
        return self.rfile.read(length) if length > 0 else b""

    def _origins(self) -> set:
        return {f"http://127.0.0.1:{self.server.port}", f"http://localhost:{self.server.port}"}

    def _own_host(self) -> bool:
        host = self.headers.get("Host")
        return host is None or host.lower() in {o[len("http://"):] for o in self._origins()}

    def _may_write(self) -> bool:
        origin = self.headers.get("Origin")
        return self.headers.get("X-Test-Lock") == "1" and (origin is None or origin.lower() in self._origins())

    def json_body(self) -> dict:
        try:
            body = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise BadRequest("the body is not JSON") from None
        if not isinstance(body, dict):
            raise BadRequest("the body is not a JSON object")
        return body

    def send(self, status: int, body: bytes, content_type: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        for name, value in {**SECURITY_HEADERS, "Content-Type": content_type, "Content-Length": str(len(body)),
                            **(headers or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.sent = True
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, value, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        self.send(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8", headers)


def _page(handler: Handler) -> None:
    handler.send(200, PAGE_HTML.encode("utf-8"), "text/html; charset=utf-8")


def _css(handler: Handler) -> None:
    handler.send(200, PAGE_CSS.encode("utf-8"), "text/css; charset=utf-8")


def _js(handler: Handler) -> None:
    handler.send(200, PAGE_JS.encode("utf-8"), "text/javascript; charset=utf-8")


def _get_state(handler: Handler) -> None:
    handler._json(snapshot(handler.server.folder))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _post_state(handler: Handler) -> None:
    body = handler.json_body()
    value, until, after, note = (body.get(k) for k in ("value", "until", "after", "note"))
    if not isinstance(value, str):
        raise BadRequest(f"value: one of {', '.join(tl.STATES)}")
    if until is not None and not _number(until):
        raise BadRequest("until: epoch seconds or null")
    if after is not None and not isinstance(after, str):
        raise BadRequest(f"after: one of {', '.join(tl.STATES)} or null")
    if note is not None and (not isinstance(note, str) or len(note) > NOTE_MAX):
        raise BadRequest(f"note: a text of at most {NOTE_MAX} characters or null")
    queue = tl.Queue(handler.server.folder)
    try:
        now = time.time()
        state = queue.set_state(value, until, after, note.strip() if note else None, now)
    except ValueError as error:
        raise BadRequest(str(error)) from None
    finally:
        queue.db.close()
    handler._json({"state": state_json(state, now)})


def _post_stop(handler: Handler) -> None:
    id = handler.json_body().get("id")
    if not isinstance(id, int) or isinstance(id, bool):
        raise BadRequest("id: the number of a running entry")
    queue = tl.Queue(handler.server.folder)
    try:
        stopped = queue.request_stop(id)
    finally:
        queue.db.close()
    if not stopped:
        return handler._json({"error": f"#{id} is not running"}, 404)
    handler._json({"id": id, "stop": True})


ROUTES: Dict[str, Dict[str, Callable[[Handler], None]]] = {
    "/": {"GET": _page},
    "/page.css": {"GET": _css},
    "/page.js": {"GET": _js},
    "/api/state": {"GET": _get_state, "POST": _post_state},
    "/api/stop": {"POST": _post_stop},
}


def serve(args) -> int:
    folder = tl.lock_dir()
    try:
        server = Server(args.port, folder, args.verbose)
    except OSError as error:
        print(f"test lock page: port {args.port} on 127.0.0.1 cannot be used ({error})", file=sys.stderr)
        return 1
    print(f"test lock page: http://127.0.0.1:{server.port}/ over {folder} (Ctrl+C stops it)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# --- install and uninstall (Windows) -------------------------------------------------------------

def main_checkout() -> str:
    """The main checkout: the folder of the git common directory."""
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=HERE, capture_output=True, text=True,
                            encoding="utf-8", check=True).stdout.strip()  # git's paths: UTF-8
    return os.path.dirname(os.path.abspath(os.path.join(HERE, common)))


def interpreter(checkout: str) -> str:
    """The checkout's .venv Python, without a console window when it has one (pythonw)."""
    for parts in (("Scripts", "pythonw.exe"), ("Scripts", "python.exe"), ("bin", "python")):
        path = os.path.join(checkout, ".venv", *parts)
        if os.path.exists(path):
            return path
    return sys.executable


def edge_path() -> Optional[str]:
    """msedge.exe from the registry's App Paths, None without it (or off Windows)."""
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
                path = winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
        if path and os.path.exists(path):
            return path
    return None


def desktop() -> str:
    """The user's desktop folder (also where OneDrive moved it)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            return os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0])
    except (ImportError, OSError):
        return os.path.join(os.path.expanduser("~"), "Desktop")


def _quoted(text: str) -> str:
    """A PowerShell string literal."""
    return "'" + text.replace("'", "''") + "'"


def install_plan(port: int) -> dict:
    checkout = main_checkout()
    python = interpreter(checkout)
    script = os.path.join(checkout, "tools", "test_lock_page.py")
    arguments = subprocess.list2cmdline([script, "serve", *(["--port", str(port)] if port != DEFAULT_PORT else [])])
    url = f"http://127.0.0.1:{port}/"
    edge = edge_path()
    if edge:
        target, link_arguments = edge, f"--app={url}"
    else:
        target = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
        link_arguments = f'/c start "" "{url}"'
    return {"checkout": checkout, "python": python, "script": script, "arguments": arguments, "url": url,
            "edge": edge, "target": target, "link_arguments": link_arguments,
            "shortcut": os.path.join(desktop(), SHORTCUT)}


def install_script(plan: dict) -> str:
    """The Windows PowerShell of install: the scheduled task, started at once, and the shortcut."""
    lines = [
        "$ErrorActionPreference = 'Stop'",
        '$user = "$env:USERDOMAIN\\$env:USERNAME"',
        f"$action = New-ScheduledTaskAction -Execute {_quoted(plan['python'])} -Argument {_quoted(plan['arguments'])}"
        f" -WorkingDirectory {_quoted(plan['checkout'])}",
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user",
        "$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)"
        " -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable"
        " -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries",
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited",
        f"Register-ScheduledTask -TaskName {_quoted(TASK)} -Description {_quoted('The test lock page: ' + plan['url'])}"
        " -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null",
        f"Start-ScheduledTask -TaskName {_quoted(TASK)}",
        "$shell = New-Object -ComObject WScript.Shell",
        f"$link = $shell.CreateShortcut({_quoted(plan['shortcut'])})",
        f"$link.TargetPath = {_quoted(plan['target'])}",
        f"$link.Arguments = {_quoted(plan['link_arguments'])}",
        f"$link.Description = {_quoted('Find-a-Line test lock page')}",
    ]
    if plan["edge"]:
        lines.append(f"$link.IconLocation = {_quoted(plan['edge'] + ',0')}")
    else:
        lines.append("$link.WindowStyle = 7")  # cmd's window minimised
    lines.append("$link.Save()")
    return "\n".join(lines)


def uninstall_script() -> str:
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$task = Get-ScheduledTask -TaskName {_quoted(TASK)} -ErrorAction SilentlyContinue",
        "if ($task) {",
        f"  Stop-ScheduledTask -TaskName {_quoted(TASK)}",
        f"  Unregister-ScheduledTask -TaskName {_quoted(TASK)} -Confirm:$false",
        "}",
    ])


def _powershell(script: str) -> int:
    """Runs a script in Windows PowerShell (encoded: no quoting of its own on the command line)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.call([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", encoded])


def _indented(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def install(args) -> int:
    plan = install_plan(args.port)
    missing = not os.path.exists(plan["script"])
    print(f"{'Would register' if args.dry_run else 'Registering'} the scheduled task \"{TASK}\" (at your logon, "
          "restarted every minute on failure, started at once):")
    print(f"  {subprocess.list2cmdline([plan['python']])} {plan['arguments']}")
    print(f"  in {plan['checkout']}")
    print(f"{'Would write' if args.dry_run else 'Writing'} the shortcut {plan['shortcut']}:")
    print(f"  {subprocess.list2cmdline([plan['target']])} {plan['link_arguments']}")
    if not plan["edge"]:
        print("  (Edge not found in the registry's App Paths: the address opens in the default browser)")
    if missing:
        print(f"Note: {plan['script']} does not exist (the page is not in the main checkout yet)")
    if args.dry_run:
        print(f"Through Windows PowerShell ({POWERSHELL}):")
        print(_indented(install_script(plan)))
        return 0
    if os.name != "nt":
        print("test lock page: install is for Windows only", file=sys.stderr)
        return 2
    if missing:
        print("test lock page: install refused: run it once the page is in the main checkout", file=sys.stderr)
        return 1
    return _powershell(install_script(plan))


def uninstall(args) -> int:
    shortcut = os.path.join(desktop(), SHORTCUT)
    if args.dry_run:
        print(f"Would stop and unregister the scheduled task \"{TASK}\" (when registered)")
        print(f"Would delete the shortcut {shortcut} (when there)")
        print(f"Through Windows PowerShell ({POWERSHELL}):")
        print(_indented(uninstall_script()))
        return 0
    if os.name != "nt":
        print("test lock page: uninstall is for Windows only", file=sys.stderr)
        return 2
    code = _powershell(uninstall_script())
    if os.path.exists(shortcut):
        os.remove(shortcut)
        print(f"Deleted {shortcut}")
    return code


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    server = commands.add_parser("serve", help="run the page's server in the foreground")
    server.add_argument("--port", type=int, default=PORT, help=f"the port on 127.0.0.1 (default {PORT})")
    server.add_argument("--verbose", action="store_true", help="print every request")
    installer = commands.add_parser("install", help="Windows: the scheduled task at logon and the desktop shortcut")
    installer.add_argument("--port", type=int, default=PORT, help=f"the port on 127.0.0.1 (default {PORT})")
    installer.add_argument("--dry-run", action="store_true", help="print what it would do, change nothing")
    remover = commands.add_parser("uninstall", help="remove the scheduled task and the shortcut")
    remover.add_argument("--dry-run", action="store_true", help="print what it would do, change nothing")
    args = parser.parse_args(argv)
    return {"serve": serve, "install": install, "uninstall": uninstall}[args.action](args)


# --- the page ------------------------------------------------------------------------------------

PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Test lock</title>
<link rel="stylesheet" href="/page.css">
<script src="/page.js" defer></script>
</head>
<body>
<main>
  <header class="top">
    <h1>Test lock</h1>
    <span id="slots" class="muted"></span>
  </header>
  <p id="error" class="error" hidden></p>

  <section class="panel" aria-labelledby="you">
    <h2 id="you">You</h2>
    <p id="line" class="line">Loading&hellip;</p>
    <div class="states" role="group" aria-label="Your state">
      <button type="button" class="state" data-state="free">Free</button>
      <button type="button" class="state" data-state="heavy-ok">Heavy OK</button>
      <button type="button" class="state" data-state="busy">Busy</button>
      <button type="button" class="state" data-state="quiet">Quiet</button>
    </div>
    <ul class="meanings">
      <li data-state="free"><b>Free:</b> everything runs, measurements too</li>
      <li data-state="heavy-ok"><b>Heavy OK:</b> no measurements; big untimed runs start below your programs'
        priority on at most 16 threads; tests keep running</li>
      <li data-state="busy"><b>Busy:</b> no measurements start, tests keep running below your programs' priority</li>
      <li data-state="quiet"><b>Quiet:</b> nothing new starts</li>
    </ul>
    <div class="until" role="group" aria-label="For how long">
      <span class="muted">For:</span>
      <button type="button" class="pick" data-pick="none">No end</button>
      <button type="button" class="pick" data-pick="3600">1 h</button>
      <button type="button" class="pick" data-pick="7200">2 h</button>
      <button type="button" class="pick" data-pick="14400">4 h</button>
      <button type="button" class="pick" data-pick="18:00">until 18:00</button>
      <button type="button" class="pick" data-pick="07:00">until 07:00</button>
      <label class="pick-time">until <input type="time" id="at" aria-label="until a time"></label>
      <label class="then">then
        <select id="then" aria-label="the state afterwards">
          <option value="">the usual</option>
          <option value="free">free</option>
          <option value="heavy-ok">heavy OK</option>
          <option value="busy">busy</option>
          <option value="quiet">quiet</option>
        </select>
      </label>
    </div>
    <p class="muted small">Pick a time first, then a state. The usual afterwards: free, or busy after Free.</p>
    <input type="text" id="note" class="note" maxlength="200" placeholder="Note (optional), set with the state">
  </section>

  <section class="panel" aria-labelledby="running-title">
    <h2 id="running-title">Running</h2>
    <ul id="running" class="entries"><li class="muted">Loading&hellip;</li></ul>
  </section>

  <section class="panel" aria-labelledby="waiting-title">
    <h2 id="waiting-title">Waiting</h2>
    <ul id="waiting" class="entries"><li class="muted">Loading&hellip;</li></ul>
  </section>
</main>
</body>
</html>
"""

PAGE_CSS = """:root {
  color-scheme: light dark;
  --bg: #f4f5f7;
  --panel: #ffffff;
  --text: #1c2230;
  --muted: #5d6677;
  --line: #d8dce4;
  --button: #eef0f4;
  --button-hover: #e2e6ed;
  --accent: #2563a8;
  --free: #2e7d4f;
  --heavy-ok: #8a6a12;
  --busy: #b5541c;
  --quiet: #a3303a;
  --on-text: #ffffff;
  --error-bg: #fdecec;
  --error-text: #8d1f1f;
  --held: #8a5a00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #121418;
    --panel: #1b1f26;
    --text: #e4e7ed;
    --muted: #9aa3b3;
    --line: #2d333d;
    --button: #262b34;
    --button-hover: #313743;
    --accent: #6ea8e8;
    --free: #3f9c66;
    --heavy-ok: #a98a2c;
    --busy: #cc6a2e;
    --quiet: #c4505a;
    --error-bg: #3a1c1e;
    --error-text: #f2b8b8;
    --held: #e0b25a;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font: 15px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif;
}
main { max-width: 860px; margin: 0 auto; padding: 16px; }
.top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h1 { font-size: 22px; margin: 0 0 12px; }
h2 { font-size: 15px; margin: 0 0 10px; color: var(--muted); font-weight: 600; text-transform: uppercase;
     letter-spacing: 0.04em; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
         margin-bottom: 14px; }
.muted { color: var(--muted); }
.small { font-size: 13px; margin: 6px 0 8px; }
.line { font-size: 18px; margin: 0 0 12px; }
.line.free { color: var(--free); }
.line.heavy-ok { color: var(--heavy-ok); }
.line.busy { color: var(--busy); }
.line.quiet { color: var(--quiet); }
.error { background: var(--error-bg); color: var(--error-text); border-radius: 8px; padding: 8px 12px; }
button, select, input { font: inherit; color: inherit; }
button {
  background: var(--button); border: 1px solid var(--line); border-radius: 7px; padding: 6px 12px; cursor: pointer;
}
button:hover:not(:disabled) { background: var(--button-hover); }
button:disabled { opacity: 0.55; cursor: default; }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.states { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); border-radius: 9px;
          overflow: hidden; }
.states .state { border: 0; border-radius: 0; border-left: 1px solid var(--line); padding: 10px 6px; font-weight: 600; }
.states .state:first-child { border-left: 0; }
.state.on { color: var(--on-text); }
.state.on[data-state="free"] { background: var(--free); }
.state.on[data-state="heavy-ok"] { background: var(--heavy-ok); }
.state.on[data-state="busy"] { background: var(--busy); }
.state.on[data-state="quiet"] { background: var(--quiet); }
.meanings { list-style: none; margin: 10px 0 12px; padding: 0; font-size: 13px; color: var(--muted); }
.meanings li { padding: 2px 0 2px 10px; border-left: 3px solid transparent; }
.meanings li.on { color: var(--text); border-left-color: var(--accent); }
.until { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.pick.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.pick-time, .then { display: inline-flex; align-items: center; gap: 4px; }
.pick-time input, .then select { background: var(--button); border: 1px solid var(--line); border-radius: 7px;
                                  padding: 5px 6px; }
.pick-time.on input { border-color: var(--accent); }
.note { width: 100%; background: var(--button); border: 1px solid var(--line); border-radius: 7px; padding: 6px 10px; }
.entries { list-style: none; margin: 0; padding: 0; }
.entries > li { border-top: 1px solid var(--line); padding: 8px 0; display: flex; gap: 12px; align-items: center; }
.entries > li:first-child { border-top: 0; }
.entry-main { flex: 1; min-width: 0; }
.entry-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.entry-id { font-weight: 700; }
.badge { font-size: 12px; border: 1px solid var(--line); border-radius: 999px; padding: 0 7px; color: var(--muted); }
.badge.exclusive { border-color: var(--busy); color: var(--busy); }
.entry-command { font-family: Consolas, ui-monospace, monospace; font-size: 13px; overflow: hidden;
                 text-overflow: ellipsis; white-space: nowrap; }
.entry-meta { font-size: 13px; color: var(--muted); }
.entry-meta .held { color: var(--held); font-weight: 600; }
.stop { border-color: var(--quiet); color: var(--quiet); font-weight: 600; }
@media (max-width: 560px) {
  .states { grid-template-columns: repeat(2, 1fr); }
  .states .state:nth-child(3) { border-left: 0; }
  .states .state:nth-child(n+3) { border-top: 1px solid var(--line); }
  .entries > li { flex-wrap: wrap; }
}
"""

PAGE_JS = r""""use strict";
(() => {
  const LABELS = {"free": "Free", "heavy-ok": "Heavy OK", "busy": "Busy", "quiet": "Quiet"};
  const $ = (id) => document.getElementById(id);
  let offset = 0;          // the server's clock less the browser's, in ms
  let data = null;         // the last answer of /api/state
  let pick = "none";       // the chosen "for how long": none, seconds, HH:MM or "time" (the input)
  let posting = false;

  const serverNow = () => Date.now() + offset;

  async function call(method, path, body) {
    const options = {method, cache: "no-store", headers: {}};
    if (body !== undefined) {
      options.headers = {"Content-Type": "application/json", "X-Test-Lock": "1"};
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    let answer = null;
    try { answer = await response.json(); } catch (e) { answer = null; }
    if (!response.ok) throw new Error((answer && answer.error) || (response.status + " " + response.statusText));
    return answer;
  }

  function showError(text) {
    const box = $("error");
    box.hidden = !text;
    box.textContent = text || "";
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clock(seconds) {
    const at = new Date(seconds * 1000);
    return String(at.getHours()).padStart(2, "0") + ":" + String(at.getMinutes()).padStart(2, "0");
  }

  function span(seconds) {
    const minutes = Math.max(0, Math.round(seconds / 60));
    if (minutes < 60) return minutes + " min";
    return Math.floor(minutes / 60) + " h " + String(minutes % 60).padStart(2, "0") + " min";
  }

  function nextAt(text) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(text || "");
    if (!match) return undefined;
    const now = serverNow();
    const at = new Date(now);
    at.setHours(Number(match[1]), Number(match[2]), 0, 0);
    if (at.getTime() <= now) at.setDate(at.getDate() + 1);
    return at.getTime() / 1000;
  }

  function untilSeconds() {
    if (pick === "none") return null;
    if (pick === "time") return nextAt($("at").value);
    if (pick.includes(":")) return nextAt(pick);
    return serverNow() / 1000 + Number(pick);
  }

  async function choose(value) {
    if (posting) return;
    const until = untilSeconds();
    if (until === undefined) { showError("Pick a time for \"until\" first."); return; }
    const after = until === null ? null : ($("then").value || (value === "free" ? "busy" : "free"));
    const note = $("note").value.trim() || null;
    posting = true;
    render();
    try {
      await call("POST", "/api/state", {value, until, after, note});
      pick = "none";
      $("note").value = "";
      $("at").value = "";
      $("then").value = "";
      await refresh();
    } catch (e) {
      showError("The state was not set: " + e.message);
    } finally {
      posting = false;
      render();
    }
  }

  async function stop(entry) {
    const what = entry.kind || entry.short;
    if (!window.confirm("Stop #" + entry.id + " " + what + " of owner " + entry.owner +
                        "? Its agent will have to queue it again.")) return;
    try {
      await call("POST", "/api/stop", {id: entry.id});
      await refresh();
    } catch (e) {
      showError("#" + entry.id + " was not stopped: " + e.message);
    }
  }

  function head(entry) {
    const line = element("div", "entry-head");
    line.append(element("span", "entry-id", "#" + entry.id));
    line.append(element("span", "badge " + entry.mode,
                        entry.mode + (entry.resources.length ? " +" + entry.resources.join(",") : "")));
    if (entry.first) line.append(element("span", "badge", "first"));
    line.append(element("span", "muted", entry.owner));
    return line;
  }

  function command(entry) {
    const line = element("div", "entry-command", entry.short);
    line.title = entry.command;
    return line;
  }

  function runningItem(entry, now) {
    const item = element("li");
    const main = element("div", "entry-main");
    const meta = element("div", "entry-meta");
    let text = "running " + span(now - entry.started);
    if (entry.expected_end !== null) {
      text += entry.expected_end >= now ? " \u00b7 expected end " + clock(entry.expected_end)
                                        : " \u00b7 expected to end at " + clock(entry.expected_end) + ", overdue";
    }
    if (entry.stop !== null) text += " \u00b7 stopping";
    meta.textContent = text;
    main.append(head(entry), command(entry), meta);
    const button = element("button", "stop", entry.stop !== null ? "Stopping" : "Stop");
    button.type = "button";
    button.disabled = entry.stop !== null;
    button.addEventListener("click", () => stop(entry));
    item.append(main, button);
    return item;
  }

  function waitingItem(entry, now) {
    const item = element("li");
    const main = element("div", "entry-main");
    const meta = element("div", "entry-meta");
    meta.append("waiting " + span(now - entry.queued) + " \u00b7 ");
    meta.append(element("span", entry.held_by ? "held" : "", entry.reason));
    main.append(head(entry), command(entry), meta);
    item.append(main);
    return item;
  }

  function fill(list, entries, make, empty, now) {
    list.replaceChildren(...(entries.length ? entries.map((e) => make(e, now))
                                            : [element("li", "muted", empty)]));
  }

  function render() {
    for (const button of document.querySelectorAll(".pick")) {
      button.classList.toggle("on", button.dataset.pick === pick);
    }
    document.querySelector(".pick-time").classList.toggle("on", pick === "time");
    $("then").disabled = pick === "none";
    if (!data) return;
    const state = data.state;
    for (const button of document.querySelectorAll(".state")) {
      const on = button.dataset.state === state.value;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.disabled = posting;
    }
    for (const item of document.querySelectorAll(".meanings li")) {
      item.classList.toggle("on", item.dataset.state === state.value);
    }
    const line = $("line");
    line.className = "line " + state.value;
    line.textContent = (LABELS[state.value] || state.value) + state.text.slice(state.value.length);
    const now = serverNow() / 1000;
    const running = data.entries.filter((e) => e.started !== null);
    const waiting = data.entries.filter((e) => e.started === null);
    const shared = running.filter((e) => e.mode === "shared").length;
    $("slots").textContent = shared + " of " + data.slots + " shared slots in use" +
      (running.some((e) => e.mode === "exclusive") ? " \u00b7 an exclusive command runs" : "");
    fill($("running"), running, runningItem, "Nothing runs.", now);
    fill($("waiting"), waiting, waitingItem, "Nothing waits.", now);
  }

  async function refresh() {
    try {
      const sent = Date.now();
      const answer = await call("GET", "/api/state");
      offset = answer.now * 1000 - (sent + Date.now()) / 2;
      data = answer;
      showError(null);
      render();
    } catch (e) {
      showError("The test lock page's server does not answer (" + e.message + ").");
    }
  }

  for (const button of document.querySelectorAll(".state")) {
    button.addEventListener("click", () => choose(button.dataset.state));
  }
  for (const button of document.querySelectorAll(".pick")) {
    button.addEventListener("click", () => { pick = button.dataset.pick; render(); });
  }
  $("at").addEventListener("input", () => { pick = $("at").value ? "time" : "none"; render(); });
  render();
  refresh();
  setInterval(refresh, 3000);
})();
"""


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline); none under pythonw
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
