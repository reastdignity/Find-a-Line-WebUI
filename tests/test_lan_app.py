"""tools/lan_app.py, the local app on the LAN for a phone's test of the result view (gate 2), and the one parameter of
web.create_app it needs, `lan_origins`: by default the local app admits its own host names and origins only, as
before; with the parameter the given origins too, and nothing else. The tool refuses what starts work on this PC (a
search, "Edit & run again", an OSM download) and keeps Measure, profiles, Download and favourites; it serves a scratch
build of the viewer with VIEW_DEFAULT true and never writes the repository's viewer/dist; its data folder holds copies
of the runs it names only; it never takes the app's own port. The smoke test serves the tool's app over HTTPS and opens
Home and a run's page in Playwright's Edge (from PowerShell: .claude/rules/browser-tests.md)."""

import contextlib
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import lan_app  # noqa: E402
from test_web import EDGE  # noqa: E402  (Edge's install path, as the other browser tests)
import web  # noqa: E402

TOKEN = "lan-token"
LAN = "https://192.0.2.5:8443"  # a made-up LAN origin of the tool (RFC 5737's documentation addresses)
OTHER = "https://192.0.2.6:8443"  # another address on the network: never admitted
VIEWER = os.path.join(REPO, "viewer")
READY = "() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)"
WHICH = "() => window.FINDALINE_VIEW ? 'view' : window.FINDALINE_RESULT ? 'today' : null"
WAIT = 60000  # ms: the deadline of a wait for the page


def _folder_post(client, origin):
    return client.post("/api/favourites/folders", json={"name": "Tatras"},
                       headers={"origin": origin, "x-findaline-token": TOKEN})


def test_create_app_by_default(tmp_path):
    """Without lan_origins the local app is as before: its own host names only, a change only from its own origin."""
    hosts = list(web.LOCAL_HOSTS)
    app = web.create_app(str(tmp_path), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/").status_code == 200
        assert client.get("/", headers={"host": "192.0.2.5:8443"}).status_code == 400
        assert _folder_post(client, LAN).status_code == 403
        assert _folder_post(client, "http://127.0.0.1:8765").status_code == 200
    assert web.LOCAL_HOSTS == hosts


def test_create_app_with_lan_origins(tmp_path):
    """The given origins' hosts are admitted and their changes taken (with the page's token); another address is not;
    the loopback's own origins stay; LOCAL_HOSTS is not changed."""
    hosts = list(web.LOCAL_HOSTS)
    app = web.create_app(str(tmp_path), token=TOKEN, port=8443, start_scheduler=False, lan_origins=(LAN,))
    with TestClient(app, base_url=LAN) as client:
        page = client.get("/")
        assert page.status_code == 200 and TOKEN in page.text
        assert client.get("/", headers={"host": "192.0.2.6:8443"}).status_code == 400
        assert _folder_post(client, LAN).status_code == 200
        assert _folder_post(client, OTHER).status_code == 403
        assert client.post("/api/favourites/folders", json={"name": "x"}, headers={"origin": LAN}).status_code == 403
        assert _folder_post(client, "http://127.0.0.1:8443").status_code == 200  # the loopback's own
    assert web.LOCAL_HOSTS == hosts


@pytest.mark.parametrize("origin", ["https://192.0.2.5:8443/", "192.0.2.5", "https://192.0.2.5:8443/x",
                                    "ftp://192.0.2.5", "https://user@192.0.2.5", "https://*:8443",
                                    "https://*.example:8443", "*"])
def test_lan_origins_are_origins(tmp_path, origin):
    with pytest.raises(ValueError):
        web.create_app(str(tmp_path), token=TOKEN, start_scheduler=False, lan_origins=(origin,))


def test_lan_origins_not_public(tmp_path):
    from settings import AccountSettings, PublicSettings
    public = PublicSettings(public_url="https://localhost:9000", trusted_proxy="127.0.0.1", contact="x@example.org")
    accounts = AccountSettings(session_secret="s" * 40)
    with pytest.raises(ValueError):
        web.create_app(str(tmp_path), public=public, accounts=accounts, lan_origins=(LAN,))


@pytest.fixture
def fake_build(tmp_path):
    """A stand-in build folder (the real one: test_the_build): app.js and viewer.js of known contents."""
    build = tmp_path / "build"
    build.mkdir()
    (build / "app.js").write_text("window.LAN_BUILD = 'app';", encoding="utf-8")
    (build / "viewer.js").write_text("window.LAN_BUILD = 'viewer';", encoding="utf-8")
    return build


def test_the_tools_app(tmp_path, fake_build, monkeypatch):
    """The tool's app: the search, "Edit & run again" and an OSM download refused (403 with the reason), a favourite's
    folder and Download's export not refused; /app/ and the runs' _viewer/ from the scratch build; the Esri key left
    out; the app's own port refused."""
    monkeypatch.setenv("ESRI_API_KEY", "lan-test-key")
    data = tmp_path / "data"
    app, inner = lan_app.make_app(str(data), 8443, ["192.0.2.5"], str(fake_build), start_scheduler=False)
    assert os.environ["ESRI_API_KEY"] == "lan-test-key"  # the process's environment as it was
    assert web.web_key("esri_api_key") == "lan-test-key"
    with TestClient(app, base_url=LAN) as client:
        headers = {"origin": LAN, "x-findaline-token": inner.state.token}
        for path, body in (("/api/jobs", {"params": {}}), ("/api/jobs/20261122-000000-abcdef/again", {}),
                           ("/api/osm", {})):
            answer = client.post(path, json=body, headers=headers)
            assert answer.status_code == 403 and answer.json() == {"detail": lan_app.REFUSED_TEXT}, path
            assert answer.headers["cache-control"] == "no-store"
        assert client.post("/api/favourites/folders", json={"name": "Tatras"}, headers=headers).status_code == 200
        export = client.post("/api/runs/no-such-run/export", json={"format": "csv"}, headers=headers)
        assert export.status_code != 403 and export.json() != {"detail": lan_app.REFUSED_TEXT}
        assert client.get("/api/jobs").status_code == 200  # the list of searches is no search
        assert client.get("/app/app.js").text == "window.LAN_BUILD = 'app';"
        assert client.get("/runs/_viewer/viewer.js").text == "window.LAN_BUILD = 'viewer';"
        page = client.get("/").text
        assert "lan-test-key" not in page and "lan-test-key" not in client.get("/runs/runs.js").text
        assert client.get("/", headers={"host": "192.0.2.6:8443"}).status_code == 400
    assert os.path.realpath(web.APP_DIST) == os.path.realpath(os.path.join(REPO, "viewer", "dist"))
    keyed, _ = lan_app.make_app(str(data), 8443, [], str(fake_build), start_scheduler=False, esri=True)
    with TestClient(keyed, base_url="https://127.0.0.1:8443") as client:  # --esri: the page gets the key
        assert "lan-test-key" in client.get("/").text
    with pytest.raises(SystemExit, match="8765 is the app's own"):
        lan_app.make_app(str(data), web.PORT, [], str(fake_build), start_scheduler=False)


def test_never_the_apps_port(tmp_path):
    """The tool's default port is its own (8443), never the app's (web.PORT 8765): `serve` refuses 8765 for that reason
    (in a data folder it would otherwise serve); the origins it passes are https on its port, without the port when it
    is https' own (443), as a browser writes the Origin."""
    assert lan_app.PORT == 8443 != web.PORT
    data = _served_folder(tmp_path)
    with pytest.raises(SystemExit, match="8765 is the app's own"):
        lan_app.main(["serve", "--data-dir", str(data), "--port", str(web.PORT)])
    assert lan_app.origins(8443, ["198.51.100.2"]) == ("https://localhost:8443", "https://127.0.0.1:8443",
                                                       "https://198.51.100.2:8443")
    assert lan_app.origins(443, ["198.51.100.2"]) == ("https://localhost", "https://127.0.0.1", "https://198.51.100.2")


def test_serve_needs_a_prepared_folder(tmp_path):
    """`serve` shows only a folder `prepare` made (its MARKER): a data folder without it, even one full of runs, is
    refused before anything is built or written there."""
    data = _served_folder(tmp_path)
    (data / lan_app.MARKER).unlink()
    before = _listing(data)
    with pytest.raises(SystemExit, match=lan_app.MARKER):
        lan_app.main(["serve", "--data-dir", str(data), "--port", "8443"])
    assert _listing(data) == before


def _served_folder(tmp_path):
    """A data folder as `prepare` leaves it, without its cache: one run (run.json, no store) and the MARKER."""
    data = tmp_path / "data"
    folder = data / "runs" / "test-run-a"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"id": folder.name, "name": "A", "created": "2026-11-01T00:00:00"}),
                                     encoding="utf-8")
    (data / lan_app.MARKER).write_text(json.dumps({"prepared": True}), encoding="utf-8")
    return data


def _fake_source(root):
    """A data folder to copy from: two runs (one with text files of before), a runs.js, a cache with a listed and an
    unlisted file."""
    for run in ("test-run-a", "test-run-b"):
        folder = root / "runs" / run
        folder.mkdir(parents=True)
        meta = {"id": run, "name": run[-1], "created": "2026-11-01T00:00:00+00:00",
                "data": [{"layer": "NMT", "paths": [f"poland/nmt/{run}.tif"]}]}
        (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
        for name in web.RUN_FILES + ("data.js", "lines.csv", "progress.json"):
            (folder / name).write_bytes(b"x")
        (root / "cache" / "poland" / "nmt").mkdir(parents=True, exist_ok=True)
        (root / "cache" / "poland" / "nmt" / f"{run}.tif").write_bytes(b"tif")
    (root / "runs" / "runs.js").write_text("window.FINDALINE_RUNS = [];", encoding="utf-8")
    (root / "cache" / "LAYOUT").write_text("1", encoding="utf-8")
    (root / "cache" / "poland" / "index.sqlite").write_bytes(b"db")
    (root / "cache" / "poland" / "unlisted.tif").write_bytes(b"no")


def _listing(root):
    """Every file under a folder with its size and time (a copy must not change its source)."""
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            stat = os.stat(os.path.join(folder, name))
            found[os.path.relpath(os.path.join(folder, name), root)] = (stat.st_size, stat.st_mtime_ns)
    return found


def test_prepare_copies_the_listed_runs_only(tmp_path):
    """`prepare`: the named runs only, each with web.RUN_FILES and its run.json (no text files of before, no work
    state); the cache's parts and the files the runs name, nothing else; the source untouched; the data folder never
    the source. Both commands need a data folder named (the tool holds none)."""
    source, data = tmp_path / "source", tmp_path / "data"
    _fake_source(source)
    before = _listing(source)
    ids = lan_app.prepare(str(data), str(source), runs=["test-run-a"], clip=False,
                          parts=("LAYOUT", "poland/index.sqlite", "missing/part"), say=lambda *a: None)
    assert ids == ["test-run-a"] and lan_app.read_marker(str(data)) == {"prepared": True}
    assert sorted(n for n in os.listdir(data / "runs") if not n.startswith("_")) == ["runs.js", "test-run-a"]
    assert sorted(os.listdir(data / "runs" / "test-run-a")) == sorted(web.RUN_FILES + ("run.json",))
    assert sorted(_listing(data / "cache")) == sorted(os.path.join(*p.split("/")) for p in (
        "LAYOUT", "poland/index.sqlite", "poland/nmt/test-run-a.tif"))
    assert "test-run-a" in (data / "runs" / "runs.js").read_text(encoding="utf-8")
    assert _listing(source) == before
    for inside in (source, source / "runs" / "lan", source / "cache"):  # never the source nor a folder in it
        with pytest.raises(SystemExit, match="neither the one copied from nor inside it"):
            lan_app.prepare(str(inside), str(source), clip=False, say=lambda *a: None)
    assert _listing(source) == before
    for argv in (["prepare", "--from", str(source)], ["serve"]):  # no data folder of its own: it must be named
        with pytest.raises(SystemExit):
            lan_app.main(argv)


def test_prepare_writes_only_into_its_own_folder(tmp_path):
    """`prepare` writes into a new or empty folder or one it made before (its MARKER) only: a folder holding anything
    else (a real data folder: runs, the job database) is refused before anything is written, as is a file; a run the
    source lacks is refused before the first write too (no mark, no folder left)."""
    source = tmp_path / "source"
    _fake_source(source)
    quiet = {"clip": False, "say": lambda *a: None, "parts": ("LAYOUT",)}
    real = tmp_path / "real"
    (real / "runs" / "2026-11-01_000000_Mine_0000000000000001").mkdir(parents=True)
    (real / "jobs.sqlite").write_bytes(b"db")
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / "notes.txt").write_text("mine", encoding="utf-8")
    afile = tmp_path / "a-file"
    afile.write_text("x", encoding="utf-8")
    for folder in (real, lone, afile):
        before = _listing(folder) if folder.is_dir() else afile.read_text(encoding="utf-8")
        with pytest.raises(SystemExit, match=f"not made by `tools/lan_app.py prepare` \\(no {lan_app.MARKER}\\)"):
            lan_app.prepare(str(folder), str(source), runs=["test-run-a"], **quiet)
        assert (_listing(folder) if folder.is_dir() else afile.read_text(encoding="utf-8")) == before, folder
    new = tmp_path / "new"
    with pytest.raises(SystemExit, match="no run test-run-x"):
        lan_app.prepare(str(new), str(source), runs=["test-run-a", "test-run-x"], **quiet)
    assert not new.exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert lan_app.prepare(str(empty), str(source), runs=["test-run-a"], **quiet) == ["test-run-a"]
    again = lan_app.prepare(str(empty), str(source), runs=["test-run-b"], **quiet)  # its own folder: taken again
    assert sorted(again) == ["test-run-a", "test-run-b"]
    assert lan_app.read_marker(str(empty)) == {"prepared": True}


def test_the_marker_keeps_both_runs(tmp_path, monkeypatch):
    """make_coast adds the coast's id to the marker and keeps the clip's (its search stood in for: one new run folder),
    with network blocked and no Esri key in the search's environment; a second call makes no search."""
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    (data / lan_app.MARKER).write_text(json.dumps({"clip": "clip-id"}), encoding="utf-8")
    calls = []

    def search(args, cwd, env):
        calls.append((args, env))
        (data / "runs" / "coast-id").mkdir()
        (data / "runs" / "coast-id" / "run.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(lan_app.subprocess, "run", search)
    monkeypatch.setenv("ESRI_API_KEY", "lan-test-key")
    assert lan_app.make_coast(str(data), say=lambda *a: None) == "coast-id"
    assert lan_app.read_marker(str(data)) == {"clip": "clip-id", "coast": "coast-id"}
    args, env = calls[0]
    assert list(lan_app.COAST) == args[2:2 + len(lan_app.COAST)] and "--data-dir" in args
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9" and "ESRI_API_KEY" not in {k.upper() for k in env}
    assert lan_app.make_coast(str(data), say=lambda *a: None) == "coast-id" and len(calls) == 1


def _dist_digest() -> str:
    digest = hashlib.sha256()
    dist = os.path.join(VIEWER, "dist")
    for name in sorted(os.listdir(dist)):
        digest.update(name.encode("utf-8"))
        with open(os.path.join(dist, name), "rb") as f:
            digest.update(hashlib.sha256(f.read()).digest())
    return digest.hexdigest()


needs_esbuild = pytest.mark.skipif(not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                                   reason="esbuild missing: npm ci in viewer/")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The tool's scratch build and a plain build (viewer/build.mjs --out), with the digest of viewer/dist before."""
    before = _dist_digest()
    flipped = lan_app.build_viewer(str(tmp_path_factory.mktemp("lan-build")), say=lambda *a: None)
    plain = str(tmp_path_factory.mktemp("plain-build"))
    done = subprocess.run(["node", "build.mjs", "--out", plain], cwd=VIEWER, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)
    assert done.returncode == 0, done.stderr
    return flipped, plain, before


@needs_esbuild
def test_the_build(built):
    """The scratch build differs from a plain one in app.js and viewer.js at most (the constant set: build_viewer fails
    unless its one line was found once): in both while the source's VIEW_DEFAULT is false, in none once it is true (the
    flip of gate 2); it holds every file of a plain build, and viewer/dist is untouched."""
    import today_page
    flipped, plain, before = built
    assert sorted(os.listdir(flipped)) == sorted(os.listdir(plain))
    differ = []
    for name in os.listdir(plain):
        with open(os.path.join(flipped, name), "rb") as a, open(os.path.join(plain, name), "rb") as b:
            if a.read() != b.read():
                differ.append(name)
    assert sorted(differ) == ([] if today_page.view_default() else ["app.js", "viewer.js"])
    assert _dist_digest() == before


@contextlib.contextmanager
def _served(data, build):
    """The tool's app with its worker over HTTPS on a free port of 127.0.0.1 (uvicorn in a thread, as `serve` runs it);
    yields its address. The certificate in the data folder (pytest's temporary one), as `serve` keeps it."""
    import uvicorn

    import device_page
    port = _free_port()
    folder = os.path.join(str(data), lan_app.CERT_DIR)
    os.makedirs(folder)
    cert_file, key_file = device_page.certificate(folder, [])
    app, _ = lan_app.make_app(str(data), port, [], build)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           ssl_certfile=cert_file, ssl_keyfile=key_file))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline, "the server did not start"
        time.sleep(0.05)
    try:
        yield f"https://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def _running(processes) -> list:
    """The processes (psutil.Process) still running, a zombie counted as ended; one that ends while it is asked about
    counts as ended (psutil.NoSuchProcess between is_running and status: seen under a full pytest's load)."""
    import psutil
    left = []
    for p in processes:
        try:
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                left.append(p)
        except psutil.NoSuchProcess:
            pass
    return left


def _names(processes) -> list:
    """The processes' names for a message (one that has ended meanwhile by its pid)."""
    import psutil
    names = []
    for p in processes:
        try:
            names.append(p.name())
        except psutil.Error:
            names.append(f"pid {p.pid}")
    return names


def _ended_within(processes, seconds: float) -> list:
    """Waits up to `seconds` for the processes to end; those still running then (_running)."""
    deadline = time.monotonic() + seconds
    while True:
        left = _running(processes)
        if not left or time.monotonic() > deadline:
            return left
        time.sleep(0.2)


class _Tree:
    """A process a test started and every descendant of it seen while it ran (psutil.Process objects, which know their
    start time: a pid used again by another process is never stopped). watch() while the root runs: once it has ended,
    its orphaned children can no longer be found from it."""

    def __init__(self, pid: int):
        import psutil
        self.root = psutil.Process(pid)
        self.seen = set()

    def watch(self) -> list:
        """The descendants of the root now, added to those seen; all seen."""
        import psutil
        try:
            self.seen.update(self.root.children(recursive=True))
        except psutil.NoSuchProcess:
            pass
        return list(self.seen)

    def stop(self):
        """Every process of the tree killed, the children first (then none is orphaned by the root's end), those that have
        ended already skipped; waits for them to end."""
        import psutil
        processes = [*self.watch(), self.root]
        for p in processes:
            with contextlib.suppress(psutil.NoSuchProcess):
                p.kill()
        psutil.wait_procs(processes, timeout=30)


def test_a_failed_test_leaves_no_process():
    """_Tree, test_serve_starts_and_stops's cleanup: a test that fails while the process it started still runs leaves
    neither that process nor the processes it started (a grandchild that would sleep a minute); a process of the tree
    that has ended already does not stop the cleanup, nor does one asked about as it ends (_running)."""
    import psutil
    script = ("import subprocess, sys, time\n"
              "child = subprocess.Popen([sys.executable, '-c', 'import time; print(\"up\", flush=True); time.sleep(60)'])\n"
              "print(child.pid, flush=True)\n"
              "time.sleep(60)\n")
    root = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
    started = []
    try:
        tree = _Tree(root.pid)
        with pytest.raises(RuntimeError):
            try:
                lines = [root.stdout.readline().strip() for _ in range(2)]  # the grandchild's pid, and it runs
                assert "up" in lines, lines
                grandchild = psutil.Process(int(next(line for line in lines if line.isdigit())))
                started = tree.watch()
                assert grandchild in started
                quick = subprocess.Popen([sys.executable, "-c", "pass"])
                tree.seen.add(psutil.Process(quick.pid))
                quick.wait(timeout=60)
                raise RuntimeError("the test fails midway")
            finally:
                tree.stop()
        assert _ended_within(started, 10) == [], _names(started)
        assert root.wait(timeout=10) is not None
    finally:  # this test's own processes, should _Tree have left any
        for p in started:
            with contextlib.suppress(psutil.NoSuchProcess):
                p.kill()
        if root.poll() is None:
            root.kill()
        root.wait(timeout=30)
        root.stdout.close()

    class Ending:  # a process that ends between is_running and status
        pid = 1

        def is_running(self):
            return True

        def status(self):
            raise psutil.NoSuchProcess(1)

        def name(self):
            raise psutil.NoSuchProcess(1)
    assert _running([Ending()]) == [] and _names([Ending()]) == ["pid 1"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _playwright() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


@needs_esbuild
@pytest.mark.skipif(not os.path.exists(EDGE)
                    or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_smoke_over_https(tmp_path, built, view_clip):
    """The tool's app over HTTPS: Home lists the run, its page `/?ui=c#run=` opens in the view without asking (the
    build's default), `?view=today` opens today's page; a search is refused from the page's own origin; nothing of the
    server is left running after its stop."""
    import warnings

    import psutil
    import requests
    import urllib3
    from playwright.sync_api import sync_playwright

    from test_shell_c import BIG, copy_clip
    flipped, _, _ = built
    data = tmp_path / "data"
    copy_clip(view_clip, data, BIG, "Clip")
    children_before = {p.pid for p in psutil.Process().children(recursive=True)}
    with _served(data, flipped) as site:
        with warnings.catch_warnings():  # the self-signed certificate, on purpose
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            home = requests.get(site + "/", verify=False, timeout=30)
        assert home.status_code == 200 and '<script src="/app/app.js"></script>' in home.text
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            try:
                context = browser.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                page.goto(site + "/")
                page.wait_for_selector(f'.c-card[data-run="{BIG}"]', timeout=WAIT)
                page.goto(f"{site}/?ui=c#run={BIG}")
                page.wait_for_function(READY, timeout=WAIT)
                assert page.evaluate(WHICH) == "view"
                page.goto("about:blank")
                page.goto(f"{site}/?ui=c&view=today#run={BIG}")
                page.wait_for_function(READY, timeout=WAIT)
                assert page.evaluate(WHICH) == "today"
                post = """async ([path, body]) => {
                  const token = document.querySelector('meta[name=findaline-token]')?.content;
                  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json',
                    'X-Findaline-Token': token || ''}, body});
                  return [r.status, (await r.json()).detail || null];
                }"""
                assert page.evaluate(post, ["/api/jobs", '{"params": {}}']) == [403, lan_app.REFUSED_TEXT]
                # a change the page may make, from its https origin: taken
                assert page.evaluate(post, ["/api/favourites/folders", '{"name": "Tatras"}']) == [200, None]
                assert errors == []
            finally:
                browser.close()
    # the worker's processes end with the server (the scheduler's stop)
    started = [p for p in psutil.Process().children(recursive=True) if p.pid not in children_before]
    left = _ended_within(started, 30)
    names = _names(left)
    for p in left:  # this test's own, not left behind when it fails
        with contextlib.suppress(psutil.NoSuchProcess):
            p.kill()
    assert left == [], names


@needs_esbuild
def test_serve_starts_and_stops(tmp_path, view_clip):
    """`serve` itself, as the user starts it (its own process; 127.0.0.1 and a free port): it builds the page, serves
    Home over HTTPS with its certificate in the data folder, and Ctrl+Break (Windows; SIGINT elsewhere) stops it
    cleanly: "Stopped.", exit 0, the port free, the certificate's folder gone, none of its processes left. Should it
    fail midway, its whole process tree is stopped (_Tree), not the tool's process alone (the numba warm-up would go
    on compiling in the data folder)."""
    import signal
    import warnings

    import requests
    import urllib3

    from test_shell_c import BIG, copy_clip
    data = tmp_path / "data"
    copy_clip(view_clip, data, BIG, "Clip")
    (data / lan_app.MARKER).write_text(json.dumps({"prepared": True}), encoding="utf-8")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k.upper() != "ESRI_API_KEY"}
    windows = sys.platform == "win32"
    server = subprocess.Popen([sys.executable, os.path.join(REPO, "tools", "lan_app.py"), "serve", "--data-dir",
                               str(data), "--port", str(port), "--host", "127.0.0.1"], cwd=REPO, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0)
    printed = []
    reader = threading.Thread(target=lambda: printed.extend(line.rstrip() for line in server.stdout), daemon=True)
    reader.start()
    tree = None
    try:
        tree = _Tree(server.pid)  # its processes, stopped in `finally` also when the test fails midway
        deadline = time.monotonic() + 300
        while not any("Ctrl+C stops" in line for line in printed):
            assert server.poll() is None and time.monotonic() < deadline, printed
            tree.watch()
            time.sleep(0.1)
        assert any(f"https://localhost:{port}/" in line for line in printed), printed
        assert (data / lan_app.CERT_DIR / "device-key.pem").is_file()
        with warnings.catch_warnings():  # the self-signed certificate, on purpose
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            home = requests.get(f"https://127.0.0.1:{port}/", verify=False, timeout=60)
        assert home.status_code == 200 and '<script src="/app/app.js"></script>' in home.text
        children = tree.watch()
        server.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGINT)
        assert server.wait(timeout=60) == 0
        reader.join(timeout=10)
        left = _ended_within(children, 30)  # ended by the stop itself, before any cleanup below
        assert left == [], _names(left)
    finally:
        if tree is not None:
            tree.stop()
        if server.poll() is None:
            server.kill()
            server.wait(timeout=30)
    assert "Stopped." in printed, printed
    assert not (data / lan_app.CERT_DIR).exists()
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", port)) != 0


from test_shell_c_view_map import view_clip  # noqa: E402,F401  (the result view's clip run, module fixture)
