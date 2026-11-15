"""tools/cdd_fetch.py: the bulk fetch of Portugal's CDD models and of plain file lists (Wallonia), against a fake
server of its own (the search, the Keycloak form, cookies, redirects to a signed store, faults on request). No test
reaches the real host or reads the real credentials: the environment's CDD_USER / CDD_PASSWORD are replaced."""

import ast
import hashlib
import json
import os
import re
import secrets
import signal
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import cdd_fetch as cf  # noqa: E402

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

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

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
        try:
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
        action = "/realms/dgterritorio/login-actions/authenticate?session_code=%s&amp;execution=e1" % code
        return ('<html><body><form id="kc-form-login" class="x" action="%s" method="post">'
                '<input type="text" name="username"><input type="password" name="password">'
                '<input type="hidden" name="flow" value="f1"></form></body></html>' % action).encode()

    def route(self, h, method, parts):
        path = parts.path
        if method == "GET" and path == "/":
            self.send(h, 200, b"<html>site</html>", {"Content-Type": "text/html",
                                                      "Set-Cookie": "site=%s; Path=/" % self.secret("site")})
        elif method == "GET" and path == "/auth/login":
            self.send(h, 302, headers={"Location": "/realms/dgterritorio/protocol/openid-connect/auth?state=s1"})
        elif method == "POST" and path.endswith("/authenticate") and self.form_fails:
            self.form_fails -= 1
            h.rfile.read(int(h.headers.get("Content-Length") or 0))
            self.send(h, 500, b"down", {"Content-Type": "text/plain"})
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
                self.send(h, 302, headers={"Location": "/store/%s?X-Amz-Signature=%s&a=%s" % (
                    item_id, signature, action)})
        elif method == "GET" and path.startswith("/store/"):
            item_id = path.rsplit("/", 1)[-1]
            action = dict(urllib.parse.parse_qsl(parts.query)).get("a", "ok")
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
        if body.get("token"):
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


@pytest.fixture
def fake(monkeypatch):
    server = Fake()
    monkeypatch.setattr(cf, "SITE", server.base)
    monkeypatch.setattr(cf, "AUTH_URL", server.base + "/realms/dgterritorio/protocol/openid-connect/auth")
    monkeypatch.setattr(cf, "SEARCH_PAUSE", 0)
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
    monkeypatch.setattr(cf, "SEARCH_PAUSE", 5.0)
    mainland(fake, 3)
    fake.add("ACORES-MDE-1", "2024_SMG_PDL_31-2-3-4_01_MDE")
    assert run(tmp_path, "plan", "--collections", "MDT-50cm", "ACORES-MDE-1") == 0
    assert len(fake.searches) == 3 and len(fake.waits) == 2 and all(4 < w <= 5 for w in fake.waits)


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
    assert [f["id"] for f in failed] == ["MDT-50cm-090201-07-2024"] and "sign-in failed" in failed[0]["error"]


def test_the_disk_is_checked_and_the_status_saved_within_a_long_file(fake, tmp_path, monkeypatch):
    fake.add("MDT-50cm", "MDT-50cm-090200-07-2024", size=5000)
    fake.add("MDT-50cm", "MDT-50cm-090201-07-2024", size=5000)
    planned(fake, tmp_path)
    monkeypatch.setattr(cf, "DISK_EVERY", 1500)
    saved = []
    real_save = cf.Run.save
    monkeypatch.setattr(cf.Run, "save", lambda self, current=None: (saved.append(current), real_save(self, current)))
    calls = []
    real_usage = cf.shutil.disk_usage

    def usage(path):  # plenty before the files and for the first one, then nothing
        calls.append(path)
        free = 10 ** 15 if len(calls) <= 5 else 0
        return real_usage(path)._replace(free=free)
    monkeypatch.setattr(cf.shutil, "disk_usage", usage)
    assert fetch(tmp_path) == cf.EXIT_DISK
    assert [r["id"] for r in done_rows(tmp_path)] == ["MDT-50cm-090200-07-2024"]
    assert ("MDT-50cm-090200-07-2024", 1544) in saved  # bytes so far: 8 + three chunks of 512
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
    fake.actions["MDT-50cm-090205-07-2024"] = ["expire"] * 5
    fake.actions["MDT-50cm-090206-07-2024"] = ["expire"] * 5
    fetch(tmp_path)
    monkeypatch.setenv("CDD_PASSWORD", "wrong " + PASSWORD)
    fetch(tmp_path)
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
    secret_values = [USER, PASSWORD, urllib.parse.quote_plus(PASSWORD), "wrong " + PASSWORD] + fake.minted
    assert len(fake.minted) > 40
    for where, text in texts.items():
        for value in secret_values:
            assert value not in text, (where, value)
        assert "SECRET" not in text and "X-Amz" not in text and "/download/" not in text, where
        assert not re.search(r"[0-9a-f]{64}", text) or where.endswith("done.jsonl"), where  # the files' sha256
