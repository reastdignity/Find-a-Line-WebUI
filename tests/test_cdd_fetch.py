"""tools/cdd_fetch.py: the bulk fetch of Portugal's CDD models and of plain file lists (Wallonia), against a fake
server of its own (the search, the Keycloak form, cookies, redirects to a signed store, faults on request). No test
reaches the real host or reads the real credentials: the environment's CDD_USER / CDD_PASSWORD are replaced."""

import ast
import errno
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import struct
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import cdd_fetch as cf  # noqa: E402

REAL_SITE, REAL_AUTH, REAL_SCHEMES = cf.SITE, cf.AUTH_URL, cf.SCHEMES  # before any fixture; never requested
USER = "user-SECRET-u1"
PASSWORD = "pw SECRET&p1"  # a space and an ampersand: masked in the form's encoding too
TIFF = b"II*\x00"


def tiff(n, seed):
    body = TIFF + hashlib.sha256(seed.encode()).digest() * (n // 32 + 1)
    return body[:n]


class Fake:
    """CDD as the tool meets it: GET / and /auth/login (a redirect to the realm's form), the form's POST (a
    redirect back with a session cookie), POST /dgt-be/v1/search (paging tokens, ids, a new address per search),
    GET /dgt-be/v1/download/<64 hex> (a redirect to /store/<id>?X-Amz-Signature=..., or to the login without a
    valid session), and plain files under /wal/ that ignore Range. `actions[id]` is a list of what the next answers
    to that file do: ok, 429, 503, html, expire, short, magic, 500, 404, stop, signal."""

    def __init__(self):
        self.items = []           # (collection, id, properties)
        self.bodies = {}          # id -> bytes
        self.actions = {}         # id -> list of actions, used up in order
        self.sessions = set()
        self.tokens = {}          # 64 hex -> id
        self.minted = []          # every token and secret value handed out
        self.log = []             # (method, path, user agent)
        self.searches = []        # the bodies of the searches
        self.logins = 0
        self.posts = 0
        self.form_fails = 0
        self.times = []           # (when, Host header) of every request
        self.headers = []         # (path, the request's headers) of every request
        self.action_base = ""     # the form's action before its path ("" = this server, relative)
        self.down = 0             # the next n requests: the connection closed without an answer (an outage)
        self.repeat_paging = False  # every page is the first one again, with the same next token
        self.search_throttle = 0  # the next n searches: 429
        self.search_list = False  # searches answer a JSON list
        self.stop_at_root = False  # GET / sets the tool's stop (a SIGTERM during the sign-in)
        self.elsewhere = None     # where actions "ftp" and "file" redirect a download
        self.store_base = None    # the host a download redirects to (None: this one; another name: another host)
        self.post_down = 0        # the next n credential POSTs: no answer
        self.realm_down = False   # the realm's login page: no answer
        self.reset_form = 0       # the next n login pages: headers, part of the page, then a reset
        self.slow = False
        self.marked = False       # set when a file of action "mark" starts coming
        self.stall_form = 0       # the next n login pages: headers, then nothing for a second
        self.login_location = "/realms/dgterritorio/protocol/openid-connect/auth?state=s1"
        self.active = self.most = 0
        self.lock = threading.Lock()
        self.plain = {}           # /wal/<name> -> bytes
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.handle(self, "GET")

            def do_POST(self):
                fake.handle(self, "POST")

        # two listeners of one fake: `base` (the site) and `other` (another host for a store or a realm; a name
        # like localhost would cost a refused IPv6 try of about 2 s on Windows)
        self.servers = []
        for _ in range(2):
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            self.servers.append(server)
        self.base, self.other = ("http://127.0.0.1:%d" % s.server_address[1] for s in self.servers)

    def close(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def add(self, collection, item_id, size=3000, version="01", sized=True, body=None):
        self.items.append((collection, item_id, {"version": version, "datetime": "2026-01-01T00:00:00Z",
                                                 **({"file:size": size} if sized else {})}))
        self.bodies[item_id] = body if body is not None else tiff(size, item_id)

    def secret(self, prefix):
        value = "%s-SECRET-%s" % (prefix, secrets.token_hex(4))
        self.minted.append(value)
        return value

    # serving

    def handle(self, h, method):
        parts = urllib.parse.urlsplit(h.path)
        with self.lock:
            self.active += 1
            self.most = max(self.most, self.active)
            self.log.append((method, parts.path, h.headers.get("User-Agent")))
            self.times.append((time.monotonic(), h.headers.get("Host")))
            self.headers.append((parts.path, {k.lower(): v for k, v in h.headers.items()}))
        try:
            with self.lock:
                self.slow = False  # a new request: an earlier slow file's thread no longer moves the clock
                down = self.down > 0
                self.down -= down
            if down:
                h.close_connection = True
                return
            self.route(h, method, parts)
        finally:
            with self.lock:
                self.active -= 1

    def send(self, h, status, body=b"", headers=None, length=None):
        h.send_response(status)
        for name, value in (headers or {}).items():
            h.send_header(name, value)
        h.send_header("Content-Length", str(len(body) if length is None else length))
        h.end_headers()
        h.wfile.write(body)

    def cookies(self, h):
        found = {}
        for part in (h.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            found[name] = value
        return found

    def form_page(self):
        code = self.secret("sc")
        action = self.action_base + \
            "/realms/dgterritorio/login-actions/authenticate?session_code=%s&amp;execution=e1" % code
        return ('<html><body><form id="kc-form-login" class="x" action="%s" method="post">'
                '<input type="text" name="username"><input type="password" name="password">'
                '<input type="hidden" name="flow" value="f1"></form></body></html>' % action).encode()

    def route(self, h, method, parts):
        path = parts.path
        if method == "GET" and path == "/" and self.stop_at_root:
            cf.STOP.set()
            self.send(h, 200, b"<html>site</html>", {"Content-Type": "text/html"})
        elif method == "GET" and path == "/":
            self.send(h, 200, b"<html>site</html>", {"Content-Type": "text/html",
                                                      "Set-Cookie": "site=%s; Path=/" % self.secret("site")})
        elif method == "GET" and path == "/auth/login":
            self.send(h, 302, headers={"Location": self.login_location})
        elif method == "POST" and path.endswith("/authenticate") and self.post_down:
            self.post_down -= 1
            self.posts += 1  # it arrived: the credentials were sent, no answer comes back
            h.rfile.read(int(h.headers.get("Content-Length") or 0))
            h.close_connection = True
        elif method == "GET" and path.startswith("/realms/") and path.endswith("/auth") and self.realm_down:
            h.close_connection = True  # the realm never answers
        elif method == "GET" and path.startswith("/realms/") and path.endswith("/auth") and self.reset_form:
            self.reset_form -= 1
            page = self.form_page()
            h.send_response(200)
            h.send_header("Content-Length", str(len(page)))
            h.end_headers()
            h.wfile.write(page[:20])
            h.wfile.flush()
            h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            h.close_connection = True
            h.connection.close()
        elif method == "POST" and path.endswith("/authenticate") and self.form_fails:
            self.form_fails -= 1
            h.rfile.read(int(h.headers.get("Content-Length") or 0))
            self.send(h, 500, b"down", {"Content-Type": "text/plain"})
        elif method == "GET" and path.startswith("/realms/") and path.endswith("/auth") and self.stall_form:
            self.stall_form -= 1
            page = self.form_page()
            h.send_response(200)
            h.send_header("Content-Length", str(len(page)))
            h.end_headers()
            h.wfile.write(page[:20])
            h.wfile.flush()
            time.sleep(5.0)
            h.close_connection = True
        elif method == "GET" and path.startswith("/realms/") and path.endswith("/auth"):
            self.send(h, 200, self.form_page(), {"Content-Type": "text/html",
                                                 "Set-Cookie": "AUTH_SESSION_ID=%s; Path=/" % self.secret("auth")})
        elif method == "POST" and path.endswith("/authenticate"):
            self.posts += 1
            length = int(h.headers.get("Content-Length") or 0)
            fields = dict(urllib.parse.parse_qsl(h.rfile.read(length).decode()))
            assert fields.get("flow") == "f1", "the form's hidden fields are sent back"
            if fields.get("username") != USER or fields.get("password") != PASSWORD:
                self.send(h, 200, self.form_page(), {"Content-Type": "text/html"})
                return
            self.logins += 1
            session = self.secret("session")
            self.sessions.add(session)
            self.send(h, 302, headers={"Location": "/auth/callback?code=%s" % self.secret("code"),
                                       "Set-Cookie": "session=%s; Path=/" % session})
        elif method == "GET" and path == "/auth/callback":
            self.send(h, 302, headers={"Location": "/"})
        elif method == "POST" and path == "/dgt-be/v1/search":
            length = int(h.headers.get("Content-Length") or 0)
            body = json.loads(h.rfile.read(length))
            self.searches.append(body)
            if self.search_throttle:
                self.search_throttle -= 1
                self.send(h, 429, b"slow down", {"Content-Type": "text/plain", "Retry-After": "7"})
                return
            if self.search_list:
                self.send(h, 200, b"[1, 2]", {"Content-Type": "application/json"})
                return
            self.send(h, 200, json.dumps(self.search(body)).encode(), {"Content-Type": "application/geo+json"})
        elif method == "GET" and path.startswith("/dgt-be/v1/download/"):
            item_id = self.tokens.get(path.rsplit("/", 1)[-1])
            if item_id is None:
                self.send(h, 404, b"no such address", {"Content-Type": "text/plain"})
                return
            action = self.next_action(item_id)
            if action in ("expire", "expire-down"):
                self.sessions.clear()
            if action == "expire-down":  # the next sign-in's form answers 500
                self.form_fails = 1
            if action in ("429", "503"):
                self.send(h, int(action), b"slow down", {"Content-Type": "text/plain", "Retry-After": "7"})
            elif action in ("401", "403"):
                self.send(h, int(action), b"who are you", {"Content-Type": "text/plain"})
            elif action == "close":  # the connection closed before any answer: the network, not the file
                h.close_connection = True
            elif action == "badstatus":  # not an HTTP answer at all
                h.wfile.write(b"NOT-HTTP/1.1 nonsense\r\n\r\n")
                h.close_connection = True
            elif action == "badloc":
                self.send(h, 302, headers={"Location": "http://[bad/x"})
            elif action in ("ftp", "file"):
                self.send(h, 302, headers={"Location": self.elsewhere})
            elif action == "404":
                self.send(h, 404, b"gone", {"Content-Type": "text/plain"})
            elif action == "500":
                self.send(h, 500, ("error at " + self.base + path).encode(), {"Content-Type": "text/plain"})
            elif self.cookies(h).get("session") not in self.sessions:
                self.send(h, 302, headers={"Location": "/auth/login"})
            elif action == "html":
                self.send(h, 200, b"<!DOCTYPE html><html>please sign in</html>", {"Content-Type": "text/html"})
            else:
                signature = self.secret("sig")
                self.send(h, 302, headers={"Location": "%s/store/%s?X-Amz-Signature=%s&a=%s" % (
                    self.store_base or self.base, item_id, signature, action)})
        elif method == "GET" and path.startswith("/store/"):
            item_id = path.rsplit("/", 1)[-1]
            action = dict(urllib.parse.parse_qsl(parts.query)).get("a", "ok")
            if action == "storedown":  # the store's connection closes before any answer
                h.close_connection = True
                return
            self.serve_file(h, self.bodies[item_id], action)
        elif method == "GET" and path.startswith("/wal/"):
            name = path.rsplit("/", 1)[-1]
            self.serve_file(h, self.plain[name], self.next_action(name))  # Range ignored: always the whole file
        else:
            self.send(h, 404, b"not found", {"Content-Type": "text/plain"})

    def serve_file(self, h, body, action):
        if action == "500":
            self.send(h, 500, b"error", {"Content-Type": "text/plain"})
        elif action == "short":
            self.send(h, 200, body[:len(body) // 2], {"Content-Type": "image/tiff"}, length=len(body))
            h.close_connection = True
        elif action in ("nolength-more", "nolength-short"):  # no Content-Length: the body ends when it closes
            h.send_response(200)
            h.send_header("Content-Type", "image/tiff")
            h.end_headers()
            h.wfile.write(body + b"0123" if action == "nolength-more" else body[:len(body) // 2])
            h.close_connection = True
        elif action == "slow":
            self.slow = True  # the tests' clock runs from here until the next request starts (handle)
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            for i in range(0, len(body), 100):
                h.wfile.write(body[i:i + 100])
                h.wfile.flush()
                time.sleep(0.01)
        elif action == "close":  # no answer at all (a plain file's server down)
            h.close_connection = True
        elif action == "slowreset":  # headers, half the body slowly (the tests' clock runs), then a reset
            self.slow = True
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            for i in range(0, len(body) // 2, 100):
                h.wfile.write(body[i:i + 100])
                h.wfile.flush()
                time.sleep(0.01)
            h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            h.close_connection = True
            try:
                h.connection.close()
            except OSError:
                pass
        elif action == "reset":  # headers and half the body, then a reset
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body[:len(body) // 2])
            h.wfile.flush()
            h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            h.close_connection = True
            try:
                h.connection.close()
            except OSError:
                pass
        elif action == "mark":
            self.marked = True
            self.send(h, 200, body, {"Content-Type": "image/tiff"})
        elif action == "magic":
            self.send(h, 200, b"XXXX" + body[4:], {"Content-Type": "image/tiff"})
        elif action == "size":
            self.send(h, 200, body + b"0123", {"Content-Type": "image/tiff"})
        elif action == "stop":
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body[:len(body) // 2])
            h.wfile.flush()
            cf.STOP.set()
            time.sleep(0.2)
            h.wfile.write(body[len(body) // 2:])
        elif action == "signal":
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body[:len(body) // 2])
            h.wfile.flush()
            signal.raise_signal(signal.SIGTERM)
            time.sleep(0.3)
            h.wfile.write(body[len(body) // 2:])
        else:
            self.send(h, 200, body, {"Content-Type": "image/tiff"})

    def next_action(self, item_id):
        queue = self.actions.get(item_id) or []
        return queue.pop(0) if queue else "ok"

    def feature(self, collection, item_id, props):
        token = secrets.token_hex(32)
        self.tokens[token] = item_id
        self.minted.append(token)
        return {"type": "Feature", "id": item_id, "collection": collection, "properties": dict(props),
                "assets": {"data": {"href": self.base + "/dgt-be/v1/download/" + token,
                                    "type": "image/tiff; application=geotiff"}}}

    def search(self, body):
        chosen = [i for i in self.items if i[0] in body["collections"]]
        if "ids" in body:
            chosen = [i for i in chosen if i[1] in body["ids"]]
        chosen.sort(key=lambda i: i[1], reverse=True)
        start = 0
        if body.get("token") and not self.repeat_paging:
            last = body["token"].split(":", 2)[2]
            start = [i[1] for i in chosen].index(last) + 1
        page = chosen[start:start + body.get("limit", 10)]
        answer = {"type": "FeatureCollection", "context": {"limit": body.get("limit"), "matched": len(chosen),
                                                             "returned": len(page)},
                  "features": [self.feature(*i) for i in page], "links": []}
        if start + len(page) < len(chosen):
            following = dict(body, token="next:%s:%s" % (body["collections"][0], page[-1][1]))
            answer["links"].append({"rel": "next", "method": "POST", "href": self.base + "/dgt-be/v1/search?undefined",
                                    "body": following})
        return answer


@pytest.fixture(autouse=True)
def nowhere(monkeypatch):
    """Every test: fake credentials and a dead address for the site, so no test can reach the real CDD or read
    the real CDD_USER / CDD_PASSWORD, with or without the fake server."""
    monkeypatch.setenv("CDD_USER", USER)
    monkeypatch.setenv("CDD_PASSWORD", PASSWORD)
    monkeypatch.setattr(cf, "SITE", "http://127.0.0.1:9")
    monkeypatch.setattr(cf, "AUTH_URL", "http://127.0.0.1:9/realms/x/auth")
    monkeypatch.setattr(cf, "SCHEMES", {"https", "http"})  # the fake server speaks http


@pytest.fixture
def fake(monkeypatch):
    server = Fake()
    monkeypatch.setattr(cf, "SITE", server.base)
    monkeypatch.setattr(cf, "AUTH_URL", server.base + "/realms/dgterritorio/protocol/openid-connect/auth")
    monkeypatch.setattr(cf, "REQUEST_PAUSE", 0)
    monkeypatch.setattr(cf, "CHUNK", 512)
    monkeypatch.setattr(cf, "PAGE", 2)
    monkeypatch.setenv("CDD_USER", USER)
    monkeypatch.setenv("CDD_PASSWORD", PASSWORD)
    waits = []
    monkeypatch.setattr(cf, "_wait", lambda seconds: waits.append(seconds))
    server.waits = waits
    yield server
    server.close()
    cf.STOP.clear()


def mainland(fake, n=4):
    for i in range(n):
        fake.add("MDT-50cm", "MDT-50cm-%06d-07-2024" % (90200 + i), size=3000 + i)


def run(out, *args):
    return cf.main([args[0], "--out", str(out), *args[1:]])


def planned(fake, out, *extra):
    assert run(out, "plan", "--collections", "MDT-50cm", *extra) == 0


def fetch(out, *extra):
    return run(out, "fetch", "--pause", "0", *extra)


def done_rows(out):
    return [json.loads(line) for line in open(os.path.join(out, "portugal", "done.jsonl"), encoding="utf-8")]


def tifs(out):
    return sorted(os.path.relpath(os.path.join(r, f), out).replace(os.sep, "/")
                  for r, _, files in os.walk(out) for f in files if f.endswith((".tif", ".zip", ".part")))


# the module

def test_standard_library_only():
    with open(os.path.join(REPO, "tools", "cdd_fetch.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read(), feature_version=(3, 11))  # the oldest Python it runs on
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            names.add(node.module.split(".")[0])
    assert names and names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def test_default_out_is_beside_the_script():
    assert cf.default_out() == os.path.join(os.path.dirname(os.path.abspath(cf.__file__)), "downloads")
    assert cf._parser().parse_args(["status"]).out == cf.default_out()


def test_the_wallonia_list():
    files = cf.LISTS["wallonia"]["files"]
    assert len(files) == 10 and sum(size for _, _, size in files) == 469_592_033_857
    assert all(url.startswith("https://geoservices.wallonie.be/") and "_3812_PROV_" in url for _, url, _ in files)
    assert len({url for _, url, _ in files}) == 10


# plan

def test_plan_walks_every_page_and_keeps_the_newest_version(fake, tmp_path):
    mainland(fake, 3)
    fake.add("MDT-50cm", "MDT-50cm-090200-07-2025", size=5000, version="01")  # a newer survey of a sheet
    fake.add("MDT-50cm", "MDT-50cm-150000-07-2025", size=5100, version="02")
    fake.add("MDT-50cm", "MDT-50cm-150000-09-2024", size=5200, version="02")  # another block's survey: kept
    fake.add("ACORES-MDE-1", "2024_SMG_PDL_31-2-3-4_01_MDE", size=4000)
    fake.add("ACORES-MDE-1", "2024_SMG_PDL_31-2-3-4_02_MDE", size=4100)
    fake.add("ACORES-MDE-1", "2024_TER_ANG_24-2-5-4_01_MDE", size=4200)
    fake.add("ACORES-MDE-1", "../evil", size=10)
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "ACORES-MDE-1", "--bbox", "36.9", "42.2", "-9.6",
               "-6.1") == 0
    rows = [json.loads(line) for line in open(tmp_path / "portugal" / "manifest.jsonl", encoding="utf-8")]
    ids = {r["id"]: r for r in rows}
    assert set(ids) == {"MDT-50cm-090200-07-2025", "MDT-50cm-090201-07-2024", "MDT-50cm-090202-07-2024",
                        "MDT-50cm-150000-07-2025", "MDT-50cm-150000-09-2024", "2024_SMG_PDL_31-2-3-4_02_MDE",
                        "2024_TER_ANG_24-2-5-4_01_MDE"}
    assert ids["MDT-50cm-090201-07-2024"]["folder"] == "090" and ids["2024_TER_ANG_24-2-5-4_01_MDE"]["folder"] == "TER"
    assert ids["MDT-50cm-090200-07-2025"]["size"] == 5000
    assert "href" not in open(tmp_path / "portugal" / "manifest.jsonl", encoding="utf-8").read()
    assert not any(t in open(tmp_path / "portugal" / "manifest.jsonl", encoding="utf-8").read() for t in fake.minted)
    summary = json.load(open(tmp_path / "portugal" / "plan.json", encoding="utf-8"))
    assert summary["collections"]["MDT-50cm"] == {"matched": 6, "found": 6, "files": 5, "older_versions": 1,
                                                  "left_out": 0, "bytes": 5000 + 3001 + 3002 + 5100 + 5200,
                                                  "without_size": 0}
    assert summary["collections"]["ACORES-MDE-1"]["left_out"] == 1
    # pages of 2: every page after the first is the next link's body with its token, sent to the search itself
    walked = [s for s in fake.searches if s["collections"] == ["MDT-50cm"]]
    assert len(walked) == 3 and "token" not in walked[0] and all(s["token"].startswith("next:") for s in walked[1:])
    assert all(s["filter"]["op"] == "s_intersects" for s in fake.searches)
    assert {ua for _, _, ua in fake.log} == {cf.AGENT}


def test_every_search_is_paced(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "REQUEST_PAUSE", 5.0)
    mainland(fake, 3)
    fake.add("ACORES-MDE-1", "2024_SMG_PDL_31-2-3-4_01_MDE")
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "ACORES-MDE-1") == 0
    assert len(fake.searches) == 3 and len(fake.waits) == 2 and all(4 < w <= 5 for w in fake.waits)


def test_a_collection_named_twice_gives_one_row_per_item(fake, tmp_path):
    mainland(fake, 3)
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "MDT-50cm") == 0
    rows = [json.loads(line) for line in open(tmp_path / "portugal" / "manifest.jsonl", encoding="utf-8")]
    assert len(rows) == 3 == len({r["id"] for r in rows})


def test_paging_that_repeats_ends_the_plan(fake, tmp_path, capsys):
    mainland(fake, 5)
    fake.repeat_paging = True
    assert run(tmp_path, "plan", "--collections", "MDT-50cm") == cf.EXIT_ERROR
    assert len(fake.searches) == 2 and "repeats" in capsys.readouterr().err
    assert not os.path.exists(tmp_path / "portugal" / "manifest.jsonl")


def test_sheet_of_the_id_forms():
    assert cf.sheet_of("MDT-50cm", "MDT-50cm-090203-07-2024", "03")[1:] == ("090", 3, 2024)
    assert cf.sheet_of("ACORES-MDS-1", "2024_SMG_PDL_27-1-4-5_01_MDS", None)[1:] == ("SMG", 1, 2024)
    assert cf.sheet_of("X", "odd", "x") == (("X", "odd"), "other", 0, 0)
    # a sheet over a municipal border names each municipality; some sheet names hold an underscore (2026-11-15)
    assert cf.sheet_of("ACORES-MDE-1", "2024_SMG_LAG_RBG_VFC_33-1-4-1_02_MDE", None) == (
        ("ACORES-MDE-1", "SMG", "33-1-4-1"), "SMG", 2, 2024)
    assert cf.sheet_of("ACORES-MDE-1", "2024_GRA_SCG_21A-4_1-4_01_MDE", None)[0] == ("ACORES-MDE-1", "GRA", "21A-4_1-4")
    assert cf.sheet_of("ACORES-MDS-1", "2024_TER_PRV_22A-4-5-3_01_MDS", None)[:2] == (
        ("ACORES-MDS-1", "TER", "22A-4-5-3"), "TER")
    assert cf.sheet_of("MDT-50cm", "MDT-50cm-213442-07-2025", "02")[0] != \
        cf.sheet_of("MDT-50cm", "MDT-50cm-213442-09-2024", "02")[0]  # two blocks' surveys: both kept


# fetch

def test_fetch_resumes_and_records_every_file(fake, tmp_path):
    mainland(fake, 4)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--limit", "2") == 0
    assert len(done_rows(tmp_path)) == 2
    assert fetch(tmp_path) == 0
    rows = done_rows(tmp_path)
    assert sorted(r["id"] for r in rows) == sorted(fake.bodies)
    for row in rows:
        body = fake.bodies[row["id"]]
        assert row["sha256"] == hashlib.sha256(body).hexdigest() and row["size"] == len(body)
        with open(tmp_path / "portugal" / row["path"], "rb") as f:
            assert f.read() == body
    assert tifs(tmp_path) == ["portugal/MDT-50cm/090/MDT-50cm-%06d-07-2024.tif" % (90200 + i) for i in range(4)]
    assert fake.most == 1 and {ua for _, _, ua in fake.log} == {cf.AGENT}
    downloads = len([p for _, p, _ in fake.log if p.startswith("/store/")])
    os.remove(tmp_path / "portugal" / rows[0]["path"])  # deleted by hand after cutting: done.jsonl decides
    assert fetch(tmp_path) == 0  # nothing left: no sign-in, no request
    assert len([p for _, p, _ in fake.log if p.startswith("/store/")]) == downloads
    status = json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))
    assert status["groups"]["MDT-50cm"]["done"] == 4 and status["state"] == "finished"


def test_a_duplicate_manifest_row_is_fetched_once(fake, tmp_path):
    mainland(fake, 2)
    planned(fake, tmp_path)
    manifest = tmp_path / "portugal" / "manifest.jsonl"
    rows = manifest.read_text(encoding="utf-8")
    manifest.write_text(rows + rows, encoding="utf-8")
    assert fetch(tmp_path) == 0
    assert len([p for _, p, _ in fake.log if p.startswith("/store/")]) == 2 and len(done_rows(tmp_path)) == 2


def test_a_second_fetch_on_one_folder_stops_and_touches_nothing(fake, tmp_path, capsys):
    import subprocess
    mainland(fake, 2)
    planned(fake, tmp_path)
    area = tmp_path / "portugal"
    holder = subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys, time; sys.path.insert(0, sys.argv[1]); import cdd_fetch as cf; "
         "held = cf._lock(sys.argv[2]); print('locked', flush=True); time.sleep(60)", os.path.join(REPO, "tools"),
         str(area)], stdout=subprocess.PIPE, text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("CDD_")})
    try:
        assert holder.stdout.readline().strip() == "locked"
        part = area / "MDT-50cm" / "090" / "MDT-50cm-090200-07-2024.tif.part"
        part.parent.mkdir(parents=True)
        part.write_bytes(b"II*\x00live")  # the first process's file under way
        before = sorted(os.listdir(area))
        requests = len(fake.log)
        assert fetch(tmp_path) == cf.EXIT_LOCKED
        assert part.exists() and sorted(os.listdir(area)) == before and len(fake.log) == requests
        assert "another fetch holds" in capsys.readouterr().err
    finally:
        holder.kill()
        holder.wait(30)
        holder.stdout.close()
    for _ in range(100):  # the system frees a dead process's lock (Windows: after a moment)
        try:
            cf._unlock(cf._lock(str(area)))
            break
        except cf.Locked:
            time.sleep(0.1)
    assert fetch(tmp_path) == 0 and len(done_rows(tmp_path)) == 2


def test_addresses_are_resolved_in_batches(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "RESOLVE_BATCH", 3)
    mainland(fake, 7)
    planned(fake, tmp_path)
    before = len(fake.searches)
    assert fetch(tmp_path) == 0
    resolving = fake.searches[before:]
    assert [len(s["ids"]) for s in resolving] == [3, 3, 1]


def test_a_part_left_by_a_kill_and_an_unrecorded_file(fake, tmp_path):
    mainland(fake, 2)
    planned(fake, tmp_path)
    folder = tmp_path / "portugal" / "MDT-50cm" / "090"
    folder.mkdir(parents=True)
    (folder / "MDT-50cm-090200-07-2024.tif.part").write_bytes(b"II*\x00half")
    (folder / "MDT-50cm-090201-07-2024.tif").write_bytes(fake.bodies["MDT-50cm-090201-07-2024"])
    assert fetch(tmp_path) == 0
    assert [p for _, p, _ in fake.log if p.startswith("/store/")] == ["/store/MDT-50cm-090200-07-2024"]
    assert sorted(r["id"] for r in done_rows(tmp_path)) == ["MDT-50cm-090200-07-2024", "MDT-50cm-090201-07-2024"]
    assert not [p for p in tifs(tmp_path) if p.endswith(".part")]


def test_a_file_on_disk_that_does_not_check_is_left_alone(fake, tmp_path):
    mainland(fake, 1)
    planned(fake, tmp_path)
    path = tmp_path / "portugal" / "MDT-50cm" / "090" / "MDT-50cm-090200-07-2024.tif"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a tiff")
    assert fetch(tmp_path) == 0
    assert path.read_bytes() == b"not a tiff"  # never deleted
    assert not [p for _, p, _ in fake.log if p.startswith("/store/")]


def test_a_session_that_ends_mid_run_is_renewed(fake, tmp_path):
    mainland(fake, 3)
    fake.actions["MDT-50cm-090201-07-2024"] = ["expire"]
    fake.actions["MDT-50cm-090202-07-2024"] = ["html"]
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert len(done_rows(tmp_path)) == 3 and fake.logins == 3


def test_a_failed_sign_in_mid_run_is_that_files_failure(fake, tmp_path):
    mainland(fake, 3)
    fake.actions["MDT-50cm-090201-07-2024"] = ["expire-down"]
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert len(done_rows(tmp_path)) == 3 and fake.logins == 2
    failed = [json.loads(line) for line in open(tmp_path / "portugal" / "failed.jsonl", encoding="utf-8")]
    assert [f["id"] for f in failed] == ["MDT-50cm-090201-07-2024"] and "sign-in answered" in failed[0]["error"]


def test_a_stale_address_then_a_lost_session_on_one_file(fake, tmp_path):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["404", "expire"]
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert len(done_rows(tmp_path)) == 2 and fake.logins == 2
    assert not os.path.exists(tmp_path / "portugal" / "failed.jsonl")


def test_an_outage_waits_longer_each_time_and_fails_no_file(fake, tmp_path, monkeypatch):
    mainland(fake, 3)
    planned(fake, tmp_path)
    states = []

    def wait(seconds):
        fake.waits.append(seconds)
        states.append(json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8")))
    monkeypatch.setattr(cf, "_wait", wait)
    fake.down = 4  # the sign-in's first request and three tries after it
    assert fetch(tmp_path) == 0
    assert fake.waits[:4] == [30.0, 60.0, 120.0, 240.0] and len(done_rows(tmp_path)) == 3
    assert not os.path.exists(tmp_path / "portugal" / "failed.jsonl")
    assert states[0]["state"] == "waiting: network" and "seconds_since_last_good_file" in states[0]
    fake.down = 0
    fake.add("MDT-50cm", "MDT-50cm-090300-07-2024")
    planned(fake, tmp_path)
    os.remove(tmp_path / "portugal" / "signins.json")  # no 60 s gap after the first run's sign-in in this list
    fake.down, fake.waits[:] = 6, []
    assert fetch(tmp_path) == 0
    assert fake.waits == [30.0, 60.0, 120.0, 240.0, 480.0, 900.0]  # doubling up to 15 min


def test_an_outage_longer_than_the_limit_stops(fake, tmp_path):
    mainland(fake, 3)
    planned(fake, tmp_path)
    fake.down = 1000
    assert fetch(tmp_path, "--outage-hours", "0") == cf.EXIT_FAILURES
    assert not os.path.exists(tmp_path / "portugal" / "failed.jsonl")
    assert json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))["state"] == \
        "stopped (exit code 4)"


def test_a_login_page_broken_after_its_headers_is_a_failed_attempt(fake, tmp_path):
    """Not an outage: the file's body failures count (30 s, 60 s, then a failed row), the sign-in that never sent
    the credentials does not count towards three in a row, and the next file signs in."""
    mainland(fake, 2)
    planned(fake, tmp_path)
    fake.reset_form = 3
    assert fetch(tmp_path) == 0
    failed = _failed(tmp_path)
    assert [f["id"] for f in failed] == ["MDT-50cm-090200-07-2024"] and "(3 times)" in failed[0]["error"]
    assert [w for w in fake.waits if w] == [30.0, 60.0] and fake.posts == 1
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]


def test_a_stalled_login_page_is_a_body_failure(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "TIMEOUT", 2.0)  # seconds of margin for every other answer on a loaded PC
    mainland(fake, 1)
    planned(fake, tmp_path)
    fake.stall_form = 1  # the page's headers, then 5 s of nothing
    assert fetch(tmp_path) == 0
    assert [w for w in fake.waits if w] == [30.0] and len(done_rows(tmp_path)) == 1 and not _failed(tmp_path)


def test_an_unexpected_error_ends_the_run_with_its_state(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    real = cf._append_jsonl

    def append(path, row):
        if path.endswith("done.jsonl"):
            raise PermissionError(13, "denied " + USER)
        real(path, row)
    monkeypatch.setattr(cf, "_append_jsonl", append)
    assert fetch(tmp_path) == cf.EXIT_ERROR
    status = json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))
    assert status["state"] == "stopped: error (PermissionError)"
    assert USER not in capsys.readouterr().err


def test_files_that_failed_before_go_to_the_end(fake, tmp_path):
    mainland(fake, 8)
    bad = sorted(fake.bodies)[:5]
    for item_id in bad:
        fake.actions[item_id] = ["size"] * 10
    planned(fake, tmp_path)
    assert fetch(tmp_path) == cf.EXIT_FAILURES and not os.path.exists(tmp_path / "portugal" / "done.jsonl")
    assert fetch(tmp_path) == cf.EXIT_FAILURES  # the three good files first, then the five bad ones in a row
    assert sorted(r["id"] for r in done_rows(tmp_path)) == sorted(fake.bodies)[5:]


def test_the_disk_is_checked_and_the_status_saved_within_a_long_file(fake, tmp_path, monkeypatch):
    fake.add("MDT-50cm", "MDT-50cm-090200-07-2024", size=5000)
    fake.add("MDT-50cm", "MDT-50cm-090201-07-2024", size=5000)
    fake.actions["MDT-50cm-090201-07-2024"] = ["mark"]
    planned(fake, tmp_path)
    monkeypatch.setattr(cf, "DISK_EVERY", 1500)
    saved = []
    real_save = cf.Run.save
    monkeypatch.setattr(cf.Run, "save", lambda self, current=None: (saved.append(current), real_save(self, current)))
    real_usage = cf.shutil.disk_usage
    # the disk fills while the second file comes: its check before it starts sees room, a check within it none
    monkeypatch.setattr(cf.shutil, "disk_usage",
                        lambda path: real_usage(path)._replace(free=0 if fake.marked else 10 ** 15))
    assert fetch(tmp_path) == cf.EXIT_DISK
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090200-07-2024"]
    assert "/store/MDT-50cm-090201-07-2024" in [p for _, p, _ in fake.log]  # stopped within it, not before
    assert any(c and c[0] == "MDT-50cm-090200-07-2024" and 1500 <= c[1] < 5000 for c in saved)  # status within
    assert not [p for p in tifs(tmp_path) if p.endswith(".part")]


def test_three_sign_ins_without_a_file_stop(fake, tmp_path):
    mainland(fake, 3)
    for item_id in fake.bodies:
        fake.actions[item_id] = ["expire"] * 5
    planned(fake, tmp_path)
    assert fetch(tmp_path) == cf.EXIT_SIGNINS
    assert fake.logins == 3 and not os.path.exists(tmp_path / "portugal" / "done.jsonl")
    assert "stopped" in json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))["state"]


def test_refused_credentials_stop_at_once(fake, tmp_path, monkeypatch):
    mainland(fake, 2)
    planned(fake, tmp_path)
    monkeypatch.setenv("CDD_PASSWORD", "wrong-SECRET-pw")
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS
    assert fake.posts == 1


def test_a_form_action_elsewhere_gets_no_credentials(fake, tmp_path, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    fake.action_base = fake.base.replace("127.0.0.1", "localhost")  # the same server under another host name
    capsys.readouterr()
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS
    assert fake.posts == 0 and not [h for _, h in fake.times if h.startswith("localhost")]
    err = capsys.readouterr().err
    assert "localhost" in err and "not signing in" in err and "SECRET" not in err


def test_a_redirect_elsewhere_during_the_sign_in_is_not_followed(fake, tmp_path, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    fake.login_location = fake.base.replace("127.0.0.1", "localhost") + \
        "/realms/dgterritorio/protocol/openid-connect/auth?state=s1"
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS
    assert fake.posts == 0 and not [h for _, h in fake.times if h.startswith("localhost")]


def test_the_sign_in_stays_on_https_and_the_two_hosts(monkeypatch):
    monkeypatch.setattr(cf, "SITE", REAL_SITE)
    monkeypatch.setattr(cf, "AUTH_URL", REAL_AUTH)
    monkeypatch.setattr(cf, "SCHEMES", REAL_SCHEMES)
    monkeypatch.setattr(cf, "REQUEST_PAUSE", 0)
    client = cf.Http(cf.Scrub())
    client.guard = cf.signin_hosts()
    client.before("https://cdd.dgterritorio.gov.pt/auth/login")
    client.before("https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/login-actions/authenticate?x=1")
    client.before("https://auth.cdd.dgterritorio.gov.pt:443/realms/x")  # the default port written out: one host
    with pytest.raises(cf.UnsafeLogin, match=":8443"):  # another port: refused, and the message names it
        client.before("https://auth.cdd.dgterritorio.gov.pt:8443/realms/x")
    for url in ("http://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/login-actions/authenticate",  # http
                "http://cdd.dgterritorio.gov.pt/auth/callback",  # a redirect from https down to http
                "https://other.example/realms/x", "https://auth.cdd.dgterritorio.gov.pt.example/x"):
        with pytest.raises(cf.UnsafeLogin):
            client.before(url)
    client.guard = None
    client.before("https://objects.example/bucket/file.tif?X-Amz-Signature=1")  # a download's store: allowed
    for url in ("http://objects.example/file.tif", "ftp://objects.example/file.tif", "file:///etc/passwd"):
        with pytest.raises(cf.BadFile):  # only https outside a sign-in too
            client.before(url)


def test_requests_are_paced_per_host(fake, tmp_path, monkeypatch):
    mainland(fake, 3)
    planned(fake, tmp_path)
    clock = [1000.0]  # a fake clock the pauses move on: the gate's arithmetic, independent of the PC's load
    monkeypatch.setattr(cf, "REQUEST_PAUSE", 1.5)
    monkeypatch.setattr(cf, "_clock", lambda: clock[0])
    monkeypatch.setattr(cf, "_wait", lambda seconds: clock.__setitem__(0, clock[0] + max(seconds, 0)))
    sent, before = [], cf.Http.before

    def recorded(self, url):
        before(self, url)
        sent.append((clock[0], cf._host(url)[1]))
    monkeypatch.setattr(cf.Http, "before", recorded)
    asked = len(fake.log)
    assert fetch(tmp_path) == 0
    assert len(sent) == len(fake.log) - asked >= 12  # every request (sign-in steps, searches, redirects) passed
    hosts = {}
    for when, host in sent:
        hosts.setdefault(host, []).append(when)
    for times in hosts.values():
        assert all(b - a >= 1.5 for a, b in zip(times, times[1:])), times


def test_sign_ins_have_a_ceiling(fake, tmp_path):
    mainland(fake, 8)
    for item_id in fake.bodies:
        fake.actions[item_id] = ["expire"]
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--max-signins-per-hour", "6") == cf.EXIT_SIGNINS
    assert fake.posts == 6 and len(done_rows(tmp_path)) == 5
    assert [w for w in fake.waits if w > 50] and all(55 < w <= 60 for w in fake.waits if w > 50)


def test_a_password_too_short_to_mask_is_refused(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 1)
    planned(fake, tmp_path)
    monkeypatch.setenv("CDD_PASSWORD", "ab")
    before = len(fake.log)
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS
    assert len(fake.log) == before and "3 characters" in capsys.readouterr().err


def test_missing_credentials(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 1)
    planned(fake, tmp_path)
    monkeypatch.delenv("CDD_PASSWORD")
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS
    assert "CDD_USER and CDD_PASSWORD" in capsys.readouterr().err


def test_a_stale_address_is_resolved_again_once(fake, tmp_path):
    mainland(fake, 1)
    fake.actions["MDT-50cm-090200-07-2024"] = ["404"]
    planned(fake, tmp_path)
    before = len(fake.searches)
    assert fetch(tmp_path) == 0
    assert len(done_rows(tmp_path)) == 1 and len(fake.searches) - before == 2


def test_a_file_is_accepted_only_with_its_magic_and_size(fake, tmp_path):
    mainland(fake, 3)
    fake.actions["MDT-50cm-090200-07-2024"] = ["magic", "magic", "magic"]
    fake.actions["MDT-50cm-090201-07-2024"] = ["size", "ok"]
    fake.actions["MDT-50cm-090202-07-2024"] = ["short"]
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--retries", "2") == 0
    assert sorted(r["id"] for r in done_rows(tmp_path)) == ["MDT-50cm-090201-07-2024", "MDT-50cm-090202-07-2024"]
    assert not [p for p in tifs(tmp_path) if "090200" in p]  # the .part removed
    failed = [json.loads(line) for line in open(tmp_path / "portugal" / "failed.jsonl", encoding="utf-8")]
    assert [f["id"] for f in failed].count("MDT-50cm-090200-07-2024") == 3  # the first try and two retries
    status = json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))
    assert status["groups"]["MDT-50cm"]["failed_this_run"] == 1 and "expected" in status["last_error"]["error"]
    fake.actions.clear()
    assert fetch(tmp_path) == 0  # retried at the next run
    assert len(done_rows(tmp_path)) == 3


def test_a_file_without_a_stated_size_needs_its_magic_only(fake, tmp_path):
    fake.add("MDT-50cm", "MDT-50cm-090200-07-2024", size=2500, sized=False)
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0 and done_rows(tmp_path)[0]["size"] == 2500


def test_five_failed_files_in_a_row_stop(fake, tmp_path):
    mainland(fake, 7)
    for item_id in fake.bodies:
        fake.actions[item_id] = ["500"] * 3
    planned(fake, tmp_path)
    assert fetch(tmp_path) == cf.EXIT_FAILURES
    assert len([p for _, p, _ in fake.log if p.startswith("/dgt-be/v1/download/")]) == 5


def test_429_and_503_wait_longer_each_time_and_honour_retry_after(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "WAIT_BASE", 2.0)
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["429", "503", "503"]
    planned(fake, tmp_path)
    fake.waits.clear()
    assert fetch(tmp_path, "--pause", "3") == 0
    assert fake.waits == [7.0, 7.0, 8.0, 3.0]  # max(2, 7), max(4, 7), max(8, 7); then the pause between files
    assert len(done_rows(tmp_path)) == 2


def test_low_disk_stops_cleanly(fake, tmp_path):
    mainland(fake, 2)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--min-free-gb", "1e12") == cf.EXIT_DISK
    assert not [p for _, p, _ in fake.log if p.startswith("/store/")]
    assert "exit code 5" in json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))["state"]


def test_a_stop_drops_the_part_and_saves_the_state(fake, tmp_path):
    mainland(fake, 3)
    fake.actions["MDT-50cm-090201-07-2024"] = ["stop"]
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090200-07-2024"]
    assert not [p for p in tifs(tmp_path) if p.endswith(".part") or "090201" in p]
    assert json.load(open(tmp_path / "portugal" / "status.json", encoding="utf-8"))["state"] == "stopped by a signal"
    cf.STOP.clear()
    assert fetch(tmp_path) == 0 and len(done_rows(tmp_path)) == 3


@pytest.mark.skipif(threading.current_thread() is not threading.main_thread(), reason="signals need the main thread")
def test_sigterm_stops_the_run(fake, tmp_path):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["signal"]
    planned(fake, tmp_path)
    before = signal.getsignal(signal.SIGTERM)
    assert fetch(tmp_path) == 0
    assert not os.path.exists(tmp_path / "portugal" / "done.jsonl")
    assert not [p for p in tifs(tmp_path) if p.endswith(".part")]
    assert signal.getsignal(signal.SIGTERM) == before  # the handler restored


@pytest.mark.parametrize("status", ["401", "403"])
def test_401_and_403_on_a_download_are_a_lost_session(fake, tmp_path, status):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = [status]
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert len(done_rows(tmp_path)) == 2 and fake.logins == 2


def test_the_size_is_checked_on_the_stream_without_a_content_length(fake, tmp_path):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["nolength-more"] * 2
    fake.actions["MDT-50cm-090201-07-2024"] = ["nolength-short"] * 3  # a cut body: three tries, then failed
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--retries", "1") == 0
    assert not os.path.exists(tmp_path / "portugal" / "done.jsonl")
    errors = {json.loads(line)["id"]: json.loads(line)["error"]
              for line in open(tmp_path / "portugal" / "failed.jsonl", encoding="utf-8")}
    assert "more than the 3000 bytes" in errors["MDT-50cm-090200-07-2024"]
    assert "cut short" in errors["MDT-50cm-090201-07-2024"]
    assert not [p for p in tifs(tmp_path) if p.endswith(".part")]


def test_a_file_that_trickles_fails(fake, tmp_path, monkeypatch):
    # the rate's clock moves one second per look only while the slow file comes: the good file sees no time pass,
    # whatever the PC's load
    clock = [0.0]

    def tick():
        clock[0] += 1.0 if fake.slow else 0.0
        return clock[0]
    monkeypatch.setattr(cf, "_clock", tick)
    monkeypatch.setattr(cf, "RATE_WINDOW", 5.0)
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["slow"] * 3
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--min-rate-kb", "50") == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]
    failed = [json.loads(line) for line in open(tmp_path / "portugal" / "failed.jsonl", encoding="utf-8")]
    assert len(failed) == 3 and all("slower than 50 kB/s" in f["error"] for f in failed)


def test_six_throttles_fail_the_file(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "WAIT_BASE", 1.0)
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["429"] * 6
    planned(fake, tmp_path)
    fake.waits.clear()
    assert fetch(tmp_path, "--retries", "0") == 0
    assert [w for w in fake.waits if w] == [7.0, 7.0, 7.0, 8.0, 16.0]  # five waits: the sixth fails the file
    failed = [json.loads(line) for line in open(tmp_path / "portugal" / "failed.jsonl", encoding="utf-8")]
    assert [f["error"] for f in failed] == ["HTTP 429/503 6 times"]
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]


def test_a_429_to_the_address_search_waits(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "WAIT_BASE", 2.0)
    mainland(fake, 2)
    planned(fake, tmp_path)
    fake.search_throttle, fake.waits[:] = 1, []
    assert fetch(tmp_path) == 0
    assert [w for w in fake.waits if w] == [7.0] and len(done_rows(tmp_path)) == 2


def test_retry_after_as_seconds_or_a_date():
    import email.utils
    import datetime
    assert cf._retry_after({"Retry-After": "7"}) == 7.0
    when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=120)
    assert 115 <= cf._retry_after({"Retry-After": email.utils.format_datetime(when, usegmt=True)}) <= 121
    assert cf._retry_after({"Retry-After": "soon"}) is None and cf._retry_after({}) is None


def test_fetch_without_a_manifest(tmp_path, capsys):
    assert fetch(tmp_path) == cf.EXIT_ERROR
    assert "run `plan` first" in capsys.readouterr().err


def test_fetch_only_the_collections_asked(fake, tmp_path):
    mainland(fake, 2)
    fake.add("ACORES-MDE-1", "2024_SMG_PDL_31-2-3-4_01_MDE")
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "ACORES-MDE-1") == 0
    assert fetch(tmp_path, "--collections", "ACORES-MDE-1") == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["2024_SMG_PDL_31-2-3-4_01_MDE"]
    assert tifs(tmp_path) == ["portugal/ACORES-MDE-1/SMG/2024_SMG_PDL_31-2-3-4_01_MDE.tif"]


def test_a_line_cut_by_a_kill_does_not_swallow_the_next(fake, tmp_path):
    mainland(fake, 3)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--limit", "1") == 0
    with open(tmp_path / "portugal" / "done.jsonl", "ab") as f:
        f.write(b'{"id": "MDT-50cm-0902')  # a kill in the middle of a line
    assert fetch(tmp_path) == 0
    rows = cf._read_jsonl(str(tmp_path / "portugal" / "done.jsonl"))
    assert sorted(r["id"] for r in rows) == sorted(fake.bodies)


def test_the_scrubber():
    scrub = cf.Scrub()
    scrub.add("cookie-value-123")
    scrub.add("pw SECRET&p1")
    token = "ab" * 32
    text = scrub.text("Cookie: session=cookie-value-123; a password pw SECRET&p1 or pw+SECRET%26p1; "
                      "https://cdd.dgterritorio.gov.pt/dgt-be/v1/download/" + token + " and "
                      "https://bucket.objects.example/a/b.tif?X-Amz-Signature=sig123&X-Amz-Credential=KEY; "
                      "a bare token " + token)
    for secret in ("cookie-value-123", "SECRET", token, "X-Amz", "sig123", "KEY", "/dgt-be/", "b.tif"):
        assert secret not in text, secret
    assert "https://cdd.dgterritorio.gov.pt/..." in text and "https://bucket.objects.example/..." in text
    scrub.add("ab")  # too short to mask: refused before (fetch stops with a short credential)
    assert "ab" in scrub.text("ab")


def _status(tmp_path, area="portugal"):
    return json.load(open(tmp_path / area / "status.json", encoding="utf-8"))


def _failed(tmp_path, area="portugal"):
    path = tmp_path / area / "failed.jsonl"
    return [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []


def test_a_file_whose_body_always_breaks_fails_and_the_rest_come(fake, tmp_path):
    mainland(fake, 3)
    fake.actions["MDT-50cm-090200-07-2024"] = ["reset"] * 10  # headers, half the body, a reset: every time
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert sorted(r["id"] for r in done_rows(tmp_path)) == ["MDT-50cm-090201-07-2024", "MDT-50cm-090202-07-2024"]
    failed = _failed(tmp_path)
    assert [f["id"] for f in failed] == ["MDT-50cm-090200-07-2024"] and "(3 times)" in failed[0]["error"]
    assert [w for w in fake.waits if w] == [30.0, 60.0]  # two waits between the three tries, no outage wait
    assert len([p for _, p, _ in fake.log if p == "/store/MDT-50cm-090200-07-2024"]) == 3
    assert _status(tmp_path)["state"] == "finished this run, 1 left"
    assert fetch(tmp_path) == 0 and len(_failed(tmp_path)) == 2  # the next run tries it again, last


def test_a_reset_within_a_long_file_is_tried_again(fake, plain, tmp_path):
    fake.actions["A_MNT.zip"] = ["reset"]
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0") == 0
    assert [w for w in fake.waits if w] == [30.0] and not _failed(tmp_path, "wallonia")
    rows = [json.loads(line) for line in open(tmp_path / "wallonia" / "done.jsonl", encoding="utf-8")]
    assert {r["id"]: r["sha256"] for r in rows} == {n: hashlib.sha256(b).hexdigest() for n, b in plain.items()}


def test_resets_within_a_long_file_count_as_its_failures_not_an_outage(fake, plain, tmp_path):
    fake.actions["A_MNT.zip"] = ["reset"] * 3
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0") == 0
    failed = _failed(tmp_path, "wallonia")
    assert [f["id"] for f in failed] == ["A_MNT.zip"] and "(3 times)" in failed[0]["error"]
    assert [w for w in fake.waits if w] == [30.0, 60.0]  # an outage would wait 30, 60, 120 ... and fail nothing
    assert len([p for _, p, _ in fake.log if p == "/wal/A_MNT.zip"]) == 3


def test_a_malformed_redirect_fails_that_file_only(fake, tmp_path):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["badloc"] * 3
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]
    assert all("malformed" in f["error"] for f in _failed(tmp_path)) and len(_failed(tmp_path)) == 3


@pytest.fixture
def listener():
    """A socket where an ftp or a stray connection would land; the test asserts nothing came."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.setblocking(False)
    yield server
    with pytest.raises(BlockingIOError):
        server.accept()
    server.close()


@pytest.mark.parametrize("where", ["ftp", "file"])
def test_a_redirect_to_ftp_or_file_during_the_sign_in(fake, tmp_path, listener, where):
    mainland(fake, 1)
    planned(fake, tmp_path)
    fake.login_location = "ftp://127.0.0.1:%d/x" % listener.getsockname()[1] if where == "ftp" else \
        "file:///C:/Windows/win.ini"
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS and fake.posts == 0


@pytest.mark.parametrize("where", ["ftp", "file"])
def test_a_redirect_to_ftp_or_file_on_a_download(fake, tmp_path, listener, where):
    mainland(fake, 2)
    fake.elsewhere = "ftp://127.0.0.1:%d/x" % listener.getsockname()[1] if where == "ftp" else "file:///etc/hosts"
    fake.actions["MDT-50cm-090200-07-2024"] = [where] * 3
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]
    assert all("refused" in f["error"] for f in _failed(tmp_path))


def test_no_request_after_a_stop(fake, tmp_path):
    mainland(fake, 2)
    planned(fake, tmp_path)
    fake.stop_at_root = True
    asked = len(fake.log)
    assert fetch(tmp_path) == 0
    assert [p for _, p, _ in fake.log[asked:]] == ["/"] and fake.posts == 0
    assert _status(tmp_path)["state"] == "stopped by a signal"


def test_a_held_lock_and_a_filesystem_without_locks(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 1)
    planned(fake, tmp_path)

    def refuse(code):
        def lock_file(f):
            raise OSError(code, os.strerror(code))
        monkeypatch.setattr(cf, "_lock_file", lock_file)
    refuse(errno.EAGAIN)
    assert fetch(tmp_path) == cf.EXIT_LOCKED
    refuse(errno.ENOLCK)
    capsys.readouterr()
    assert fetch(tmp_path) == cf.EXIT_ERROR and "--no-lock" in capsys.readouterr().err
    assert not (tmp_path / "portugal" / "fetch.log").exists()
    assert fetch(tmp_path, "--no-lock") == 0 and len(done_rows(tmp_path)) == 1


def test_lines_of_the_state_files_that_cannot_be_read_are_skipped(fake, tmp_path, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--limit", "1") == 0
    with open(tmp_path / "portugal" / "done.jsonl", "ab") as f:
        f.write(b"\xff\xfe not utf-8\n")
    capsys.readouterr()
    assert fetch(tmp_path) == 0
    assert "done.jsonl, line 2: not UTF-8 or not JSON, skipped" in capsys.readouterr().err
    assert len(cf._read_jsonl(str(tmp_path / "portugal" / "done.jsonl"))) == 2


def test_a_state_file_that_cannot_be_opened_ends_the_run_with_its_state(fake, tmp_path):
    mainland(fake, 1)
    planned(fake, tmp_path)
    cf._write_json(str(tmp_path / "portugal" / "status.json"), {"state": "running"})
    (tmp_path / "portugal" / "done.jsonl").mkdir()  # not a file
    assert fetch(tmp_path) == cf.EXIT_ERROR
    assert _status(tmp_path)["state"].startswith("stopped: error (")


def test_two_runs_share_the_sign_in_ceiling(fake, tmp_path, capsys):
    mainland(fake, 3)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--limit", "1", "--max-signins-per-hour", "2") == 0
    fake.waits.clear()
    assert fetch(tmp_path, "--limit", "1", "--max-signins-per-hour", "2") == 0
    assert [w for w in fake.waits if w > 50]  # the 60 s gap held across the restart
    capsys.readouterr()
    assert fetch(tmp_path, "--max-signins-per-hour", "2") == cf.EXIT_SIGNINS and fake.posts == 2
    assert "sent 2 times within the last hour" in capsys.readouterr().err
    times = json.load(open(tmp_path / "portugal" / "signins.json", encoding="utf-8"))
    assert len(times) == 2 and all(isinstance(t, float) for t in times)


def test_a_sign_in_time_in_the_future_counts_as_now(fake, tmp_path):
    mainland(fake, 1)
    planned(fake, tmp_path)
    cf._write_json(str(tmp_path / "portugal" / "signins.json"), [time.time() + 86400])  # a clock set back
    assert fetch(tmp_path) == 0
    assert [w for w in fake.waits if w > 50]


def test_the_ceiling_says_the_sign_ins_did_not_complete(fake, tmp_path, capsys):
    mainland(fake, 4)
    planned(fake, tmp_path)
    fake.form_fails = 10
    assert fetch(tmp_path, "--max-signins-per-hour", "2") == cf.EXIT_SIGNINS
    assert "of this run's 2 sendings 2 did not complete a sign-in" in capsys.readouterr().err


def test_the_state_says_when_the_server_asked_to_wait(fake, tmp_path, monkeypatch):
    mainland(fake, 1)
    fake.actions["MDT-50cm-090200-07-2024"] = ["429"]
    planned(fake, tmp_path)
    states = []
    monkeypatch.setattr(cf, "_wait", lambda s: states.append(_status(tmp_path)["state"]))
    monkeypatch.setattr(cf, "WAIT_BASE", 2.0)
    assert fetch(tmp_path) == 0
    assert "waiting: server asked to wait (7 s)" in states


def test_a_newer_version_after_a_new_plan_is_reported_not_fetched(fake, tmp_path, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    collection, item_id, props = fake.items[0]
    fake.items[0] = (collection, item_id, dict(props, version="02", **{"file:size": 3500}))
    planned(fake, tmp_path)
    capsys.readouterr()
    downloads = len([p for _, p, _ in fake.log if p.startswith("/store/")])
    assert fetch(tmp_path) == 0
    out = capsys.readouterr().out
    assert "1 items have a newer version in the manifest" in out and item_id in out
    assert len([p for _, p, _ in fake.log if p.startswith("/store/")]) == downloads
    assert run(tmp_path, "status") == 0 and "1 items have a newer version" in capsys.readouterr().out


def test_a_full_disk_while_writing_stops(fake, tmp_path, monkeypatch):
    mainland(fake, 2)
    planned(fake, tmp_path)
    real_open = open

    class Full:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.f.close()

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(cf, "open", lambda path, *a, **k: Full(real_open(path, *a, **k))
                        if str(path).endswith(".tif.part") else real_open(path, *a, **k), raising=False)
    assert fetch(tmp_path) == cf.EXIT_DISK
    assert not [p for p in tifs(tmp_path) if p.endswith(".part")]


def test_an_id_listed_by_two_collections_is_one_row(fake, tmp_path):
    mainland(fake, 1)
    fake.items.append(("MDS-50cm", "MDT-50cm-090200-07-2024", {"version": "01", "file:size": 3000}))
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "MDS-50cm") == 0
    rows = [json.loads(line) for line in open(tmp_path / "portugal" / "manifest.jsonl", encoding="utf-8")]
    assert [r["id"] for r in rows] == ["MDT-50cm-090200-07-2024"]


def test_a_username_too_short_to_mask_is_refused(fake, tmp_path, monkeypatch):
    mainland(fake, 1)
    planned(fake, tmp_path)
    monkeypatch.setenv("CDD_USER", "ab")
    assert fetch(tmp_path) == cf.EXIT_CREDENTIALS


def test_a_search_answering_a_list_ends_the_plan(fake, tmp_path, capsys):
    mainland(fake, 1)
    fake.search_list = True
    assert run(tmp_path, "plan", "--collections", "MDT-50cm") == cf.EXIT_ERROR
    assert "not an object" in capsys.readouterr().err


def test_a_walk_beyond_max_pages_ends_the_plan(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cf, "MAX_PAGES", 2)
    mainland(fake, 5)  # three pages of two
    assert run(tmp_path, "plan", "--collections", "MDT-50cm") == cf.EXIT_ERROR
    assert len(fake.searches) == 2 and "never ends" in capsys.readouterr().err


def _fake_clock(monkeypatch, fake):
    """Pauses move a clock of their own: hours of outage in no time."""
    clock = [0.0]
    monkeypatch.setattr(cf, "_clock", lambda: clock[0])
    monkeypatch.setattr(cf, "_wait", lambda s: (fake.waits.append(s), clock.__setitem__(0, clock[0] + max(s, 0))))
    return clock


DOUBLING = [30.0, 60.0, 120.0, 240.0, 480.0, 900.0, 900.0, 900.0]  # then 3630 s >= 1 h: exit 4 at the ninth error


def test_a_store_that_never_answers_is_its_outage(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 3)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    fake.store_base = fake.other  # the store: another host than the site
    fake.actions["MDT-50cm-090200-07-2024"] = ["storedown"] * 100
    searches = len(fake.searches)
    assert fetch(tmp_path, "--outage-hours", "1") == cf.EXIT_FAILURES
    assert [w for w in fake.waits if w] == DOUBLING  # the site answers each search: the store's outage grows
    assert len(fake.searches) - searches == 9  # one address search a try, bounded by the limit
    assert not [p for _, p, _ in fake.log if p.startswith("/store/MDT-50cm-09020") and "090200" not in p]
    assert "no answer from 127.0.0.1:%s" % fake.other.rsplit(":", 1)[1] in capsys.readouterr().err
    assert not _failed(tmp_path)


def test_a_realm_that_never_answers_is_its_outage(fake, tmp_path, monkeypatch):
    mainland(fake, 2)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    realm = fake.other
    monkeypatch.setattr(cf, "AUTH_URL", realm + "/realms/dgterritorio/protocol/openid-connect/auth")
    fake.login_location = realm + "/realms/dgterritorio/protocol/openid-connect/auth?state=s1"
    fake.realm_down = True  # GET / answers, the realm's page never does
    assert fetch(tmp_path, "--outage-hours", "1") == cf.EXIT_FAILURES
    assert [w for w in fake.waits if w] == DOUBLING and fake.posts == 0


def test_a_tls_failure_at_the_store_is_its_outage(fake, tmp_path, monkeypatch, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    fake.store_base = fake.other.replace("http://", "https://")  # TLS to a server without it
    assert fetch(tmp_path, "--outage-hours", "1") == cf.EXIT_FAILURES
    assert [w for w in fake.waits if w] == DOUBLING
    assert "no answer from 127.0.0.1:%s" % fake.other.rsplit(":", 1)[1] in capsys.readouterr().err
    assert not os.path.exists(tmp_path / "portugal" / "done.jsonl")


def test_when_the_failing_step_comes_through_its_waits_restart(fake, tmp_path, monkeypatch):
    mainland(fake, 1)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    fake.store_base = fake.other
    fake.actions["MDT-50cm-090200-07-2024"] = ["storedown", "storedown", "reset", "storedown"]
    assert fetch(tmp_path) == 0
    # the download's outage: 30, 60; its headers (a body broken after them: 30) end it; the next error 30 again
    assert [w for w in fake.waits if w] == [30.0, 60.0, 30.0, 30.0] and len(done_rows(tmp_path)) == 1


def test_a_download_endpoint_down_while_the_search_answers_is_its_outage(fake, tmp_path, monkeypatch, capsys):
    """The address search and the download's GET share the site's host: the search answering every time does
    not end the download's outage."""
    mainland(fake, 3)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    fake.actions["MDT-50cm-090200-07-2024"] = ["close"] * 100  # the site's /download/ never answers
    searches = len(fake.searches)
    assert fetch(tmp_path, "--outage-hours", "1") == cf.EXIT_FAILURES
    assert [w for w in fake.waits if w] == DOUBLING and len(fake.searches) - searches == 9
    assert not _failed(tmp_path) and "(download)" in capsys.readouterr().err
    assert not [p for _, p, _ in fake.log if p.startswith("/store/")]


def test_a_realm_whose_form_target_never_answers(fake, tmp_path, monkeypatch):
    """The realm's page answers, the credentials' POST never does: the sign-in step never comes through. Every
    POST counts towards three sign-ins in a row, so that rule ends the run before the outage limit."""
    mainland(fake, 2)
    planned(fake, tmp_path)
    _fake_clock(monkeypatch, fake)
    fake.post_down = 100
    assert fetch(tmp_path, "--outage-hours", "1") == cf.EXIT_SIGNINS
    assert fake.posts == 3 and not _failed(tmp_path)
    # the sign-in's outage doubles (whole seconds; the 60 s gaps between POSTs are measured on the wall clock)
    assert [w for w in fake.waits if w and w == int(w)] == [30.0, 60.0, 120.0]


def test_a_long_file_between_two_outages_is_not_one_outage(fake, plain, tmp_path, monkeypatch):
    """A network error, then hours of a body (fake time), a body failure, another network error: the download
    came through in between, so the outage limit is not reached."""
    clock = [0.0]

    def tick():  # the body moves the clock a thousand seconds a look
        clock[0] += 1000.0 if fake.slow else 0.0
        return clock[0]
    monkeypatch.setattr(cf, "_clock", tick)
    monkeypatch.setattr(cf, "_wait", lambda s: (fake.waits.append(s), clock.__setitem__(0, clock[0] + max(s, 0))))
    fake.actions["A_MNT.zip"] = ["close", "slowreset", "close"]
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0", "--outage-hours", "1", "--min-rate-kb", "0") == 0
    assert clock[0] > 3 * 3600 and [w for w in fake.waits if w] == [30.0, 30.0, 30.0]
    assert not _failed(tmp_path, "wallonia") and len(cf._read_jsonl(str(tmp_path / "wallonia" / "done.jsonl"))) == 2


def test_credentials_sent_without_an_answer_count_towards_three(fake, tmp_path):
    mainland(fake, 3)
    planned(fake, tmp_path)
    fake.post_down = 10
    assert fetch(tmp_path) == cf.EXIT_SIGNINS and fake.posts == 3


def test_a_broken_status_line_fails_that_file_only(fake, tmp_path):
    mainland(fake, 2)
    fake.actions["MDT-50cm-090200-07-2024"] = ["badstatus"] * 3
    planned(fake, tmp_path)
    assert fetch(tmp_path) == 0
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090201-07-2024"]
    assert len(_failed(tmp_path)) == 3 and all("malformed" in f["error"] for f in _failed(tmp_path))


@pytest.mark.parametrize("content", ["{}", '["x"]', "not json"])
def test_a_signins_file_that_cannot_be_read_stops_before_any_request(fake, tmp_path, capsys, content):
    mainland(fake, 1)
    planned(fake, tmp_path)
    (tmp_path / "portugal" / "signins.json").write_text(content, encoding="utf-8")
    asked = len(fake.log)
    assert fetch(tmp_path) == cf.EXIT_ERROR and len(fake.log) == asked
    assert "signins.json cannot be read" in capsys.readouterr().err


# fetch-list

@pytest.fixture
def plain(fake, monkeypatch):
    bodies = {"A_MNT.zip": b"PK\x03\x04" + b"a" * 3000, "A_MNS.zip": b"PK\x03\x04" + b"b" * 2000}
    fake.plain.update(bodies)
    monkeypatch.setitem(cf.LISTS, "wallonia", dict(cf.LISTS["wallonia"], files=[
        ("MNT", fake.base + "/wal/A_MNT.zip", len(bodies["A_MNT.zip"])),
        ("MNS", fake.base + "/wal/A_MNS.zip", len(bodies["A_MNS.zip"]))]))
    return bodies


def test_fetch_list_starts_a_broken_file_again_from_zero(fake, plain, tmp_path):
    fake.actions["A_MNT.zip"] = ["short"]
    fake.actions["A_MNS.zip"] = ["size", "ok"]
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0") == 0
    rows = [json.loads(line) for line in open(tmp_path / "wallonia" / "done.jsonl", encoding="utf-8")]
    assert {r["id"]: r["sha256"] for r in rows} == {n: hashlib.sha256(b).hexdigest() for n, b in plain.items()}
    assert tifs(tmp_path) == ["wallonia/A_MNS.zip", "wallonia/A_MNT.zip"]
    assert fake.logins == 0 and not [p for _, p, _ in fake.log if p.startswith("/realms/")]
    assert not [p for p in fake.log if p[1] == "/"]  # no sign-in for a plain list
    asked = [headers for path, headers in fake.headers if path.startswith("/wal/")]
    assert len(asked) == 4 and not [h for h in asked if "range" in h]  # never a Range, a retry from zero too


def test_fetch_list_refuses_a_file_of_another_size(fake, plain, tmp_path):
    fake.actions["A_MNT.zip"] = ["size"] * 3
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0", "--retries", "2") == 0
    rows = [json.loads(line) for line in open(tmp_path / "wallonia" / "done.jsonl", encoding="utf-8")]
    assert [r["id"] for r in rows] == ["A_MNS.zip"]
    assert len([p for _, p, _ in fake.log if p == "/wal/A_MNT.zip"]) == 3


def test_status_covers_both_areas(fake, plain, tmp_path, capsys):
    mainland(fake, 2)
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--limit", "1") == 0
    assert run(tmp_path, "fetch-list", "wallonia", "--pause", "0", "--limit", "1") == 0
    capsys.readouterr()
    assert run(tmp_path, "status") == 0
    out = capsys.readouterr().out
    assert "portugal" in out and "wallonia" in out
    assert re.search(r"MDT-50cm\s+1 of\s+2 files", out) and re.search(r"MNT\s+1 of\s+1 files", out)
    assert re.search(r"MNS\s+0 of\s+1 files", out)


# secrets

def test_no_secret_in_any_output(fake, plain, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cf, "WAIT_BASE", 0.0)
    mainland(fake, 7)
    fake.actions["MDT-50cm-090200-07-2024"] = ["expire"]
    fake.actions["MDT-50cm-090201-07-2024"] = ["500", "500", "500"]
    fake.actions["MDT-50cm-090202-07-2024"] = ["429", "html", "html"]
    fake.actions["MDT-50cm-090203-07-2024"] = ["404", "404"]
    fake.actions["MDT-50cm-090204-07-2024"] = ["short", "magic", "size"]
    planned(fake, tmp_path)
    assert fetch(tmp_path, "--retries", "1") == 0
    # each stop below in a folder of its own, so that it really runs (the POST counts keep it from going hollow)
    three, ceiling, refused = tmp_path / "three", tmp_path / "ceiling", tmp_path / "refused"
    for folder in (three, ceiling, refused):
        planned(fake, folder)
    for item_id in fake.bodies:
        fake.actions[item_id] = ["expire"] * 5
    posts = fake.posts
    assert fetch(three) == cf.EXIT_SIGNINS and fake.posts - posts == 3
    for item_id in fake.bodies:
        fake.actions[item_id] = ["expire"] * 5
    posts = fake.posts
    assert fetch(ceiling, "--max-signins-per-hour", "1") == cf.EXIT_SIGNINS and fake.posts - posts == 1
    fake.actions.clear()
    monkeypatch.setenv("CDD_PASSWORD", "wrong " + PASSWORD)
    posts = fake.posts
    assert fetch(refused) == cf.EXIT_CREDENTIALS and fake.posts - posts == 1
    fake.actions["A_MNT.zip"] = ["500"]
    run(tmp_path, "fetch-list", "wallonia", "--pause", "0")
    run(tmp_path, "status")
    # an error escaping to the top: its text is masked too
    monkeypatch.setenv("CDD_PASSWORD", PASSWORD)
    monkeypatch.setattr(cf, "_portugal_items", lambda *a: (_ for _ in ()).throw(
        RuntimeError("boom %s %s %s/dgt-be/v1/download/%s" % (USER, PASSWORD, fake.base, fake.minted[-1]))))
    assert fetch(tmp_path) == cf.EXIT_ERROR
    captured = capsys.readouterr()
    texts = {"stdout": captured.out, "stderr": captured.err}
    for root, _, files in os.walk(tmp_path):
        for name in files:
            if not name.endswith((".tif", ".zip")):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    texts[os.path.relpath(os.path.join(root, name), tmp_path).replace(os.sep, "/")] = f.read()
    assert {"portugal/" + n for n in ("fetch.log", "status.json", "done.jsonl", "failed.jsonl", "manifest.jsonl",
                                      "plan.json")} <= set(texts)
    assert {"wallonia/fetch.log", "wallonia/done.jsonl", "wallonia/failed.jsonl"} <= set(texts)
    assert "boom" in captured.err and "failed" in texts["portugal/fetch.log"]
    for message in ("sign-ins in a row without a fetched file", "the credentials were sent 1 times",
                    "the sign-in was refused"):
        assert message in captured.err, message
    secret_values = [USER, PASSWORD, urllib.parse.quote_plus(PASSWORD), "wrong " + PASSWORD] + fake.minted
    assert len(fake.minted) > 40
    for where, text in texts.items():
        for value in secret_values:
            assert value not in text, (where, value)
        assert "SECRET" not in text and "X-Amz" not in text and "/download/" not in text, where
        assert not re.search(r"[0-9a-f]{64}", text) or where.endswith("done.jsonl"), where  # the files' sha256
