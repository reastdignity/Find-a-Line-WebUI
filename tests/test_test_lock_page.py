"""tools/test_lock_page.py: the test lock's page, over its own queue in tmp_path (never the real one)."""

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import test_lock as tl  # noqa: E402
import test_lock_page as page  # noqa: E402
from test_test_lock import Runs  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
WRITE = {"X-Test-Lock": "1", "Content-Type": "application/json"}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no system proxy for 127.0.0.1


@pytest.fixture
def runs(tmp_path):
    runs = Runs(tmp_path)
    yield runs
    runs.stop()


@pytest.fixture
def server(runs):
    """The page's server on a free port over the wrappers' queue, in a thread."""
    server = page.Server(0, runs.env["FINDALINE_TEST_LOCK_DIR"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(10)


def call(server, method, path, body=None, headers=None):
    """(status, headers, the body parsed when JSON)."""
    data = body if body is None or isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"http://127.0.0.1:{server.port}{path}", data=data, method=method,
                                     headers=headers or {})
    try:
        with OPENER.open(request, timeout=30) as response:
            status, answer, raw = response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        status, answer, raw = error.code, error.headers, error.read()
    if (answer.get("Content-Type") or "").startswith("application/json"):
        return status, answer, json.loads(raw)
    return status, answer, raw.decode("utf-8")


def test_state_and_entries(runs, server):
    """GET /api/state: the user's state, the clock and the live entries, each with what the page
    shows of it (a running one's expected end, a waiting one held by the state)."""
    status, headers, answer = call(server, "GET", "/api/state")
    assert status == 200 and "default-src 'self'" in headers["Content-Security-Policy"]
    assert answer["state"] == {"value": "free", "since": None, "until": None, "after": None, "note": None,
                               "text": "free"}
    assert abs(answer["now"] - time.time()) < 60 and answer["entries"] == [] and answer["slots"] == tl.SLOTS
    runs.set_state("busy", note="call")
    a = runs.start("a", "--expect", "600")
    runs.wait_for(lambda: runs.started("a"))
    runs.start("e", "--exclusive")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    answer = call(server, "GET", "/api/state")[2]
    assert answer["state"]["value"] == "busy" and answer["state"]["text"].startswith("busy since ")
    running, waiting = answer["entries"]
    for entry in (running, waiting):
        assert {"id", "mode", "resources", "owner", "command", "queued", "started", "expected_end", "held_by",
                "first"} <= set(entry)
    assert (running["owner"], running["mode"], running["held_by"]) == ("a", "shared", None)
    assert running["expected_end"] == pytest.approx(running["started"] + 600)
    assert running["short"].startswith("python -c import os, sys")
    assert (waiting["owner"], waiting["mode"], waiting["started"], waiting["expected_end"]) == \
        ("e", "exclusive", None, None)
    assert waiting["held_by"] == "busy" and waiting["reason"] == "held: the PC is in use"
    runs.set_state("free")
    waiting = call(server, "GET", "/api/state")[2]["entries"][1]
    assert waiting["held_by"] is None and waiting["reason"] == f"waiting for #{running['id']}"
    runs.go("a")
    assert a.wait(timeout=60) == 0


def test_heavy_and_memory_on_the_page(runs, server):
    """A heavy one started while free shows as running untamed once the state is heavy-ok; one
    waiting for memory is held by "memory" with what it needs; the PC's memory and the budget."""
    h = runs.start("h", "--heavy")
    runs.wait_for(lambda: runs.started("h"))
    answer = call(server, "GET", "/api/state")[2]
    heavy = answer["entries"][0]
    assert (heavy["mode"], heavy["tamed"], heavy["untamed"], heavy["memory"]) == ("heavy", False, False, None)
    runs.set_state("heavy-ok")
    m = runs.start("m", "--memory", "100000")
    runs.wait_for(lambda: runs.queued("shared") == 1)
    answer = call(server, "GET", "/api/state")[2]
    heavy, waiting = answer["entries"]
    assert (heavy["owner"], heavy["untamed"]) == ("h", True)
    assert heavy["rss"] is None or heavy["rss"] > 0
    assert (waiting["owner"], waiting["memory"], waiting["peak"]) == ("m", 100000 * tl.GB, 100000 * tl.GB)
    if answer["memory"] is None:                      # no psutil: nothing guarded
        assert waiting["held_by"] is None
    else:
        assert set(answer["memory"]) == {"available", "total", "budget", "share"}
        assert 0 < answer["memory"]["available"] <= answer["memory"]["total"]
        assert waiting["held_by"] == "memory"
        assert re.fullmatch(r"held: not enough free memory \(needs ~100000\.0 GB, \d+\.\d GB free for it\)",
                            waiting["reason"]), waiting["reason"]
    m.kill()
    runs.set_state("free")
    runs.go("h")
    assert h.wait(timeout=60) == 0


def test_set_the_state(server):
    """POST /api/state with the page's header and an own or no Origin; 403 otherwise, 400 for a
    value the queue refuses."""
    now = time.time()
    body = {"value": "busy", "until": now + 3600, "after": None, "note": "call"}
    status, _, answer = call(server, "POST", "/api/state", body, WRITE)
    assert status == 200, answer
    state = answer["state"]
    assert (state["value"], state["until"], state["after"], state["note"]) == ("busy", now + 3600, "free", "call")
    assert re.fullmatch(r"busy since \d\d:\d\d, until (tomorrow )?\d\d:\d\d, then free; note: call", state["text"])
    assert call(server, "GET", "/api/state")[2]["state"] == state
    free = {"value": "free", "until": None, "after": None, "note": None}
    for headers in ({"Content-Type": "application/json"}, {**WRITE, "X-Test-Lock": "yes"},
                    {**WRITE, "Origin": "http://evil.example"}, {**WRITE, "Origin": "null"},
                    {**WRITE, "Origin": f"http://127.0.0.1:{server.port + 1}"}):
        assert call(server, "POST", "/api/state", free, headers)[0] == 403, headers
    assert call(server, "GET", "/api/state")[2]["state"]["value"] == "busy"
    for origin in (f"http://127.0.0.1:{server.port}", f"http://localhost:{server.port}"):
        assert call(server, "POST", "/api/state", free, {**WRITE, "Origin": origin})[0] == 200
    for bad in ({"value": "nap"}, {"value": "busy", "until": now - 10}, {"value": "busy", "until": "18:00"},
                {"value": "busy", "after": "free"}, {"value": "busy", "until": now + 60, "after": "nap"},
                {"value": "busy", "note": "x" * (page.NOTE_MAX + 1)}, {"value": True}, [1], b"not json"):
        status, _, answer = call(server, "POST", "/api/state", bad, WRITE)
        assert status == 400 and answer["error"], bad
    state = call(server, "POST", "/api/state", {"value": "free", "until": now + 60, "after": "quiet"}, WRITE)[2]["state"]
    assert (state["value"], state["after"]) == ("free", "quiet")


def test_stop_a_running_command(runs, server):
    """POST /api/stop of a running entry: its wrapper kills the command (125); a waiting or unknown
    one is 404, and without the page's header nothing is stopped."""
    a = runs.start("a")
    runs.wait_for(lambda: runs.started("a"))
    runs.set_state("quiet")
    runs.start("b")
    runs.wait_for(lambda: runs.queued("shared") == 2)
    ids = runs.ids()
    assert call(server, "POST", "/api/stop", {"id": ids["b"]}, WRITE)[0] == 404
    assert call(server, "POST", "/api/stop", {"id": 999}, WRITE)[0] == 404
    assert call(server, "POST", "/api/stop", {"id": "1"}, WRITE)[0] == 400
    assert call(server, "POST", "/api/stop", {"id": ids["a"]}, {"Content-Type": "application/json"})[0] == 403
    time.sleep(0.3)
    assert a.poll() is None
    status, _, answer = call(server, "POST", "/api/stop", {"id": ids["a"]}, WRITE)
    assert status == 200 and answer == {"id": ids["a"], "stop": True}
    assert a.wait(timeout=60) == 125 and "stopped by the user from the test lock page" in a.stderr.read()
    entries = call(server, "GET", "/api/state")[2]["entries"]
    assert [(e["owner"], e["held_by"], e["stop"]) for e in entries] == [("b", "quiet", None)]
    runs.set_state("free")
    runs.wait_for(lambda: runs.started("b"))


def test_routes_and_headers(server):
    """The page and its two files with no inline script or style; 404 and 405 elsewhere; a foreign
    Host refused; the security headers on every answer."""
    status, headers, html = call(server, "GET", "/")
    assert status == 200 and headers["Content-Type"] == "text/html; charset=utf-8"
    assert "<title>Test lock</title>" in html and '<script src="/page.js" defer></script>' in html
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "<style" not in html and " style=" not in html
    for state, label in (("free", "Free"), ("heavy-ok", "Heavy OK"), ("busy", "Busy"), ("quiet", "Quiet")):
        assert f'data-state="{state}">{label}</button>' in html
    assert "<b>Heavy OK:</b> no measurements; big untimed runs start below your programs'" in html
    assert call(server, "GET", "/page.css")[1]["Content-Type"] == "text/css; charset=utf-8"
    status, headers, script = call(server, "GET", "/page.js")
    assert status == 200 and headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert '"X-Test-Lock": "1"' in script and "setInterval(refresh, 3000)" in script
    for method, path, code in (("GET", "/nothing", 404), ("GET", "/api/state/", 404), ("PUT", "/", 405),
                               ("GET", "/api/stop", 405), ("DELETE", "/api/state", 405), ("POST", "/", 405)):
        status, headers, _ = call(server, method, path, b"{}" if method != "GET" else None, WRITE)
        assert status == code, (method, path)
        assert headers["Content-Security-Policy"].startswith("default-src 'self'")
        assert headers["X-Content-Type-Options"] == "nosniff"
    assert call(server, "PUT", "/", b"{}")[1]["Allow"] == "GET"
    assert call(server, "GET", "/api/state", headers={"Host": f"evil.example:{server.port}"})[0] == 403
    assert call(server, "GET", "/api/state", headers={"Host": f"localhost:{server.port}"})[0] == 200
    assert call(server, "POST", "/api/state", b"x" * (page.BODY_MAX + 1), WRITE)[0] == 413


def test_a_failing_request_leaves_the_server_running(server, monkeypatch):
    def fail(folder):
        raise RuntimeError("the queue is gone")

    monkeypatch.setattr(page, "snapshot", fail)
    status, _, answer = call(server, "GET", "/api/state")
    assert status == 500 and answer["error"] == "internal error: the queue is gone"
    monkeypatch.undo()
    assert call(server, "GET", "/api/state")[0] == 200


def test_short_command():
    venv = "C:/x/.venv/Scripts/python.exe"
    assert page.short_command(f"{venv} -m pytest tests/test_a.py tests/test_b.py -q -k x") == \
        "pytest tests/test_a.py tests/test_b.py -q -k \u2026"
    assert page.short_command(f"{venv} -c 'import time; time.sleep(1)'") == "python -c import time; time.sleep(1)"
    assert page.short_command("uv run --frozen tools/perf_profile.py --cores 4") == "perf_profile.py --cores 4"
    assert page.short_command(f"{venv} tools/check_source.py C:/Users/someone/scratch/very/long/data/folder") == \
        "check_source.py folder"
    assert page.short_command("npm run build") == "npm run build" and page.short_command("") == ""
    assert len(page.short_command("pytest " + "x" * 200)) <= 72


def test_install_and_uninstall_dry_run(tmp_path, monkeypatch, capsys):
    """--dry-run prints the scheduled task, the shortcut and the PowerShell, and changes nothing."""
    def never(script):
        raise AssertionError("PowerShell run by a dry run")

    monkeypatch.setattr(page, "_powershell", never)
    monkeypatch.setattr(page, "desktop", lambda: str(tmp_path))
    checkout = page.main_checkout()
    assert page.main(["install", "--dry-run", "--port", "8771"]) == 0
    out = capsys.readouterr().out
    assert f'Would register the scheduled task "{page.TASK}"' in out
    assert page.interpreter(checkout) in out and os.path.join(checkout, "tools", "test_lock_page.py") in out
    assert f"Would write the shortcut {os.path.join(str(tmp_path), page.SHORTCUT)}" in out
    assert "http://127.0.0.1:8771/" in out and "serve --port" not in out
    for word in ("New-ScheduledTaskTrigger -AtLogOn", "-RestartCount 999", "Register-ScheduledTask",
                 "Start-ScheduledTask", "CreateShortcut"):
        assert word in out
    if page.edge_path():
        assert f"--app=http://127.0.0.1:8771/" in out
    assert page.main(["install", "--dry-run", "--port", "8790"]) == 0
    out = capsys.readouterr().out
    assert "serve --port 8790" in out and "http://127.0.0.1:8790/" in out
    (tmp_path / page.SHORTCUT).write_text("")
    assert page.main(["uninstall", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Unregister-ScheduledTask" in out and str(tmp_path / page.SHORTCUT) in out
    assert (tmp_path / page.SHORTCUT).exists() and os.listdir(tmp_path) == [page.SHORTCUT]


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Edge (run from PowerShell: Git Bash's Edge prints nothing)")
def test_page_in_edge(runs, server, tmp_path):
    """The page as headless Edge draws it: the state's button on, its line, the running commands
    with Stop (a heavy one started while free as running untamed), the waiting one held by the
    state, the PC's memory."""
    runs.start("h", "--heavy")
    runs.wait_for(lambda: runs.started("h"))
    runs.set_state("busy", note="call")
    runs.start("a")
    runs.wait_for(lambda: runs.started("a"))
    runs.start("e", "--exclusive")
    runs.wait_for(lambda: runs.queued("exclusive") == 1)
    dom = subprocess.run([EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
                          "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{server.port}/"],
                         capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
    assert re.search(r'<button[^>]*class="state on"[^>]*data-state="busy"[^>]*aria-pressed="true"', dom), dom
    assert re.search(r'<p id="line" class="line busy">Busy since \d\d:\d\d; note: call</p>', dom), dom
    running, waiting = (re.search(rf'<ul id="{name}" class="entries">(.*?)</ul>', dom, re.S).group(1)
                        for name in ("running", "waiting"))
    assert '<span class="muted">a</span>' in running and '<button class="stop" type="button">Stop</button>' in running
    assert '<span class="muted">e</span>' in waiting and '<span class="held">held: the PC is in use</span>' in waiting
    assert '<span class="badge heavy">heavy</span>' in running and '<span class="muted">h</span>' in running
    assert '<span class="untamed">running untamed: all threads, normal priority</span>' in running
    assert f"1 of {tl.SLOTS} shared slots in use · a heavy command runs</span>" in dom
    assert re.search(r'<span id="ram" class="muted">(RAM \d+\.\d GB free of \d+\.\d GB · budget for the lock '
                     r'\d+\.\d GB|RAM unknown \(no psutil\))</span>', dom), dom
