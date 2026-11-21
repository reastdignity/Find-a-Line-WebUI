"""A share link's page and a run outside the page's list of runs read the run's store (lines.arrow,
profiles.arrow) (result/load.ts storeOf: STORE_PROBE; docs/line-volume/spec-store.md 1.10, store SL, 2026-11-17): in
load.ts with a made-up XMLHttpRequest, and in headless Edge on the local app (a run missing from runs.js: its map.html
and the app) and on the public site (share links). A run without a store shows that its data could not be loaded after
its store's two 404s (store wave 4's item 5: no data.js); the list of runs is asked for once at most; a share link's
visitor gets no list."""

import json
import os
import re
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runs as rn  # noqa: E402

pytest.importorskip("httpx2")

from test_viewer import _run_node, _store_bundle, clip_folder, store_cases  # noqa: E402,F401
from test_shell_c import (BIG, C_STUBS, HELPERS, OLD, RUN_DATA, SMALL, SMALL_LINES, _edge, big_clip, data,  # noqa: E402,F401
                          drop_store, small_copy, stub_page)
from test_public import ACCOUNTS, RUN_A, RUN_B, account_settings, clip_run, copy_run, session_of  # noqa: E402,F401
from test_web import EDGE, _result_of, _server, _violations  # noqa: E402

TOKEN = "AbCdEf0123456789-share_token-xyzXYZ0123"  # a share link's token (token_urlsafe's alphabet)
OTHER_TOKEN = TOKEN[::-1]

PROBE_SCRIPT = r"""
const fs = require("fs");
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
// A made-up XMLHttpRequest serving /runs/<case>/<file> and /s/<token>/<file> (the token's run: `shared`); a file of
// `gone` answers 404 (a run without a store); every request and every script tag (a list of runs) recorded
const asked = [], scripts = [], gone = new Set();
let shared = "zone";
class FakeXHR {
  static HEADERS_RECEIVED = 2;
  open(method, url) { this.url = url; }
  setRequestHeader() {}
  getResponseHeader(name) { return name.toLowerCase() === "x-findaline-bytes" ? String(this.size) : null; }
  send() {
    const path = this.url.replace("http://test", "");
    asked.push(path);
    const runs = /^\/runs\/([^/]+)\/([^/]+)$/.exec(path), share = /^\/s\/[^/]+\/([^/]+)$/.exec(path);
    const run = runs ? runs[1] : shared, file = runs ? runs[2] : share[1], local = cases[run] + "/" + file;
    setTimeout(() => {
      const b = fs.existsSync(local) && !gone.has(file) ? fs.readFileSync(local) : null;
      this.status = b ? 200 : 404;
      const ab = new ArrayBuffer(b ? b.length : 0);
      if (b) new Uint8Array(ab).set(b);
      this.response = this.responseType === "text" ? (b ? b.toString("utf-8") : "") : ab;
      this.size = ab.byteLength;
      this.readyState = 2;
      this.onreadystatechange && this.onreadystatechange();
      this.onprogress && this.onprogress({loaded: ab.byteLength});
      this.onload({loaded: ab.byteLength});
    });
  }
}
const block = {format: 1, lines: 0, bytes: 0, sha256: ""};
const info = (id, store) => ({id, name: id, created: "", description: "", ...(store ? {store} : {})});
let listed = [info("plain", block), info("nosurface")];  // what /runs/runs.js would give
globalThis.window = globalThis;
globalThis.XMLHttpRequest = FakeXHR;
globalThis.location = {protocol: "http:", href: "http://test/app/", origin: "http://test"};
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
// A script tag: a list of runs (recorded); any other script is recorded too (none may come: no data.js)
globalThis.document = {createElement: () => ({remove() {}}), head: {appendChild(s) {
  const path = s.src.replace("http://test", "");
  scripts.push(path);
  if (path.endsWith("/runs.js")) setTimeout(() => { window.FINDALINE_RUNS = listed; s.onload(); });
  else setTimeout(() => s.onerror());
}}};
const outcome = async (f) => {
  asked.splice(0);
  scripts.splice(0);
  try { const d = await f(); return {ok: d.columns.length, asked: asked.splice(0), scripts: scripts.splice(0)}; }
  catch (e) { return {error: e.name, message: e.message, asked: asked.splice(0), scripts: scripts.splice(0)}; }
};
(async () => {
  const out = {};
  // A share link (its runs.js, /s/runs.js, lists no runs): the store asked for at once, no list
  out.share = await outcome(() => m.loadRun(process.argv[3], "/s/"));
  gone.add("lines.arrow"); gone.add("profiles.arrow");
  shared = "square";
  out.shareOld = await outcome(() => m.loadRun(process.argv[4], "/s/"));
  gone.clear();
  // A run of /runs/: the list loaded once (no list yet), then a run it lacks: asked for directly, no list again
  out.unlisted = await outcome(() => m.loadRun("zone"));
  out.unlistedAgain = await outcome(() => m.loadRun("both"));
  gone.add("lines.arrow"); gone.add("profiles.arrow");
  out.unlistedOld = await outcome(() => m.loadRun("square"));  // a run without a store: the 404s, then it fails
  gone.clear();
  out.listed = await outcome(() => m.loadRun("plain"));                // listed with its block: the store
  out.listedWithout = await outcome(() => m.loadRun("nosurface"));     // listed without one: its store all the same
  console.log(JSON.stringify(out));
})();
"""


def test_share_links_and_unlisted_runs_read_the_store(tmp_path, store_cases):
    """load.ts over http with a made-up XMLHttpRequest: a share link's run, and a run the page's list of runs does not
    name, are read from lines.arrow and profiles.arrow; without a store (404) they fail (StoreFailed) and ask for
    nothing else (no data.js); the list of runs is loaded once for /runs/ and never for a share link; a run listed
    without its store block is read from its store all the same."""
    cases = {name: str(folder).replace("\\", "/") for name, folder in store_cases.items()}
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    out = _run_node(tmp_path, _store_bundle(tmp_path), PROBE_SCRIPT, cases_path, TOKEN, OTHER_TOKEN)
    share = f"/s/{TOKEN}/"
    assert out["share"] == {"ok": 3000, "asked": [share + "lines.arrow", share + "profiles.arrow"], "scripts": []}
    other = f"/s/{OTHER_TOKEN}/"
    assert out["shareOld"]["error"] == "StoreFailed", out
    assert {k: out["shareOld"][k] for k in ("asked", "scripts")} == {
        "asked": [other + "lines.arrow", other + "profiles.arrow"], "scripts": []}, out
    assert out["unlisted"] == {"ok": 3000, "asked": ["/runs/zone/lines.arrow", "/runs/zone/profiles.arrow"],
                               "scripts": ["/runs/runs.js"]}
    assert out["unlistedAgain"] == {"ok": 3000, "asked": ["/runs/both/lines.arrow", "/runs/both/profiles.arrow"],
                                    "scripts": []}
    assert out["unlistedOld"]["error"] == "StoreFailed", out
    assert {k: out["unlistedOld"][k] for k in ("asked", "scripts")} == {
        "asked": ["/runs/square/lines.arrow", "/runs/square/profiles.arrow"], "scripts": []}, out
    assert out["listed"] == {"ok": 3000, "asked": ["/runs/plain/lines.arrow", "/runs/plain/profiles.arrow"],
                             "scripts": []}
    assert out["listedWithout"] == {"ok": 3000, "asked": ["/runs/nosurface/lines.arrow",
                                                          "/runs/nosurface/profiles.arrow"], "scripts": []}


# The files the page asked for (resource timing: 404s too), of the run's folder and the lists of runs
FILES_JS = """
const asked = () => performance.getEntriesByType("resource").map((e) => new URL(e.name).pathname);
const filesOf = (folder) => asked().filter((p) => p.startsWith(folder)).map((p) => p.split("/").pop())
  .filter((f) => %(run_data)s.includes(f));
const lists = () => asked().filter((p) => p.endsWith("/runs.js"));
const model = () => window.FINDALINE_RESULT && window.FINDALINE_RESULT.model;
""" % {"run_data": json.dumps(list(RUN_DATA))}

MAP_SCRIPT = FILES_JS + """
run({
  map(next) { wait(() => (model() && $(".r-rows .r-row")) || text(".c-result-wait .c-error"), () => {
    result.map = {files: filesOf("%(folder)s"), lists: lists(), lines: model() ? model().total : null,
                  error: text(".c-result-wait .c-error"), listed: (window.FINDALINE_RUNS || []).map((r) => r.id)};
    next();
  }); },
});
"""

APP_SCRIPT = FILES_JS + """
run({
  open(next) { wait(() => model() && model().runId === "%(run)s" && $(".c-col-list .r-rows .r-row"), () => {
    result.app = {files: filesOf("/runs/%(run)s/"), lists: lists(), lines: model().total};
    next();
  }); },
});
"""


def _unlist(data_dir, *run_ids):
    """runs.js without the runs `run_ids` (as a list read before they were saved, or a user's list without another
    user's runs)."""
    path = data_dir / "runs" / "runs.js"
    text = path.read_text("utf-8")
    runs = json.loads(text[text.index(" = ") + 3:].rstrip().rstrip(";"))
    path.write_text("window.FINDALINE_RUNS = " + json.dumps([r for r in runs if r["id"] not in run_ids]) + ";\n",
                    "utf-8")


def _test_map(data_dir, run_id: str, name: str):
    """A copy of a run's map.html (`name`) with the stubs before and the test script after it."""
    folder = data_dir / "runs" / run_id
    (folder / "map_stubs.js").write_text(C_STUBS, encoding="utf-8")
    (folder / "map_test.js").write_text(HELPERS + MAP_SCRIPT % {"folder": f"/runs/{run_id}/"}, encoding="utf-8")
    page = (folder / "map.html").read_text(encoding="utf-8")
    (folder / name).write_text(page.replace("<head>", '<head><script src="map_stubs.js"></script>')
                               .replace("</body>", '<script src="map_test.js"></script></body>'), encoding="utf-8")
    return f"runs/{run_id}/{name}"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_unlisted_runs_read_the_store_in_edge(data, tmp_path):
    """The local app over http with runs.js lacking two runs: the run with a store, in its own map.html and in the app,
    is read from lines.arrow and profiles.arrow (no data.js), with runs.js asked for once at most; the run without a
    store (its files deleted, its block gone) shows ui.result.store_failed's words after the two 404s and asks for
    nothing else; no CSP violation."""
    small_copy(data, BIG, small=OLD)
    drop_store(data, OLD)  # its files and its block
    import mapping
    mapping.install_viewer(str(data / "runs"))
    _unlist(data, SMALL, OLD)
    page = stub_page(data, "capp", APP_SCRIPT % {"run": SMALL})
    with _server(data) as port:
        own = _edge(port, _test_map(data, SMALL, "probe.html"), tmp_path / "edge-map")
        old = _edge(port, _test_map(data, OLD, "probe.html"), tmp_path / "edge-old")
        app = _edge(port, page + f"?ui=c#run={SMALL}", tmp_path / "edge-app")
    for found in (own, old, app):
        assert "timeout" not in found and "error" not in found, json.dumps(found)
        assert found["csp"] == []
    assert SMALL not in own["map"]["listed"] and OLD not in old["map"]["listed"]  # really outside the list
    assert sorted(own["map"]["files"]) == ["lines.arrow", "profiles.arrow"], own
    assert own["map"]["lists"] == ["/runs/runs.js"], own  # the map's own, no second one
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        words = json.load(f)["ui.result.store_failed"]
    assert sorted(old["map"]["files"]) == ["lines.arrow", "profiles.arrow"], old  # the store's two files, each a 404
    assert old["map"]["error"] == words and old["map"]["lines"] is None, old
    assert old["map"]["lists"] == ["/runs/runs.js"], old
    assert sorted(app["app"]["files"]) == ["lines.arrow", "profiles.arrow"], app
    assert len(app["app"]["lists"]) <= 1, app
    assert own["map"]["lines"] == app["app"]["lines"] == SMALL_LINES and own["map"]["error"] == "", own


SHARE_SCRIPT = FILES_JS + """
const out = document.createElement("pre");
const finish = (r) => { out.id = "result"; out.textContent = JSON.stringify(r); document.body.appendChild(out); };
const waitFor = (ok, then, tries = 300) => ok() ? then() : tries ? setTimeout(() => waitFor(ok, then, tries - 1), 200)
                                                 : finish({timeout: location.pathname});
// The run's actions (RunActions: .r-actions): the labels of its buttons, and the Download menu's links once opened
const actions = () => [...document.querySelectorAll(".r-actions button")]
  .map((b) => b.getAttribute("aria-label") || b.textContent.trim());
const downloadButton = () => [...document.querySelectorAll(".r-actions button")]
  .find((b) => b.textContent.trim() === "Download" || b.getAttribute("aria-label") === "Download");
const error = () => (document.querySelector(".c-result-wait .c-error") || {}).textContent || "";
waitFor(() => (model() && document.querySelector(".r-rows .r-row") && document.querySelector(".r-actions")) || error(), () => {
  const folder = location.pathname.replace(/[^/]*$/, "");
  if (error()) return finish({files: filesOf(folder), lists: lists(), error: error(), runs: window.FINDALINE_RUNS === undefined,
                              others: asked().filter((p) => p.startsWith("/runs/"))});
  const r = {files: filesOf(folder), lists: lists(), lines: model().total, runs: window.FINDALINE_RUNS === undefined,
             others: asked().filter((p) => p.startsWith("/runs/") || (p.startsWith("/s/") && !p.startsWith(folder)
                                                                    && p !== "/s/runs.js" && !p.startsWith("/s/_viewer/"))),
             map: !!window.FINDALINE_MAP && !!document.querySelector(".leaflet-container"),
             actionsBar: !!document.querySelector(".r-actions"), actions: actions(), downloads: null,
             menu: !!document.querySelector(".r-downloads")};
  if (!downloadButton()) return finish(r);
  downloadButton().click();
  waitFor(() => document.querySelector(".r-downloads a"), () => {
    r.downloads = [...document.querySelectorAll(".r-downloads a")].map((a) => new URL(a.href).pathname);
    finish(r);
  });
});
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_share_links_read_the_store_in_edge(tmp_path, clip_run, account_settings, monkeypatch):
    """The public site: a share link's map of a run with a store reads lines.arrow and profiles.arrow, never data.js,
    and of a run without a store says its data could not be loaded after the two 404s (store wave 4's item 5: no
    data.js); the only list asked for is /s/runs.js, which lists no
    runs (FINDALINE_RUNS undefined), and nothing of another run or of /runs/ is asked for: the visitor learns no other
    run's name, id or size; no CSP violation."""
    import socket

    import uvicorn

    import accounts as ac
    import web
    from jobs import Jobs
    from settings import PublicSettings
    from test_web import CSP_STUB
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import today_page
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"http://localhost:{port}"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "csp_stub.js").write_text(today_page.SCRIPT + CSP_STUB, encoding="utf-8")  # today's page pinned
    (stubs / "share_test.js").write_text(SHARE_SCRIPT, encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    tokens = {RUN_A: TOKEN, RUN_B: OTHER_TOKEN}
    jobs = Jobs(str(data))
    user_id, _, _ = session_of(data, account_settings, "a")
    for run_id, name in ((RUN_A, "A's run"), (RUN_B, "B's run")):
        folder = copy_run(clip_run, data, run_id, name)
        page = (folder / "map.html").read_text("utf-8")
        (folder / "map.html").write_text(page.replace("<head>", '<head><script src="/test/csp_stub.js"></script>')
                                         .replace("</body>", '<script src="/test/share_test.js"></script></body>'),
                                         "utf-8")
        jobs.add_run(run_id, user_id, 1)
        jobs.set_share(run_id, ac.digest(tokens[run_id]))
    assert json.loads((data / "runs" / RUN_A / "run.json").read_text("utf-8")).get("store")
    drop_store(data, RUN_B)  # RUN_B as a run saved before the store: no block, no files
    settings = PublicSettings(public_url=site, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(str(data), public=settings, accounts=account_settings)
    from starlette.staticfiles import StaticFiles
    app.mount("/test", StaticFiles(directory=str(stubs)))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        found = {}
        jobs.set_visibility(RUN_A, "demo")  # also a demo run: a visitor not signed in opens /runs/<id>/map.html
        pages = [(run_id, f"/s/{token}/map.html") for run_id, token in tokens.items()]
        for key, page in pages + [("demo", f"/runs/{RUN_A}/map.html")]:
            import subprocess
            dom = subprocess.run(
                [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / ('edge-' + key[-2:])}",
                 "--no-first-run", "--virtual-time-budget=90000", "--dump-dom", f"{site}{page}"],
                capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
            found[key] = _result_of(dom)
            assert _violations(dom) == [], key
    finally:
        server.should_exit = True
        thread.join(10)
    store, old = found[RUN_A], found[RUN_B]
    for got in (store, old):
        assert "timeout" not in got, got
        assert got["lists"] == ["/s/runs.js"] and got["runs"] is True and got["others"] == [], got
    assert sorted(store["files"]) == ["lines.arrow", "profiles.arrow"], store
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        words = json.load(f)["ui.result.store_failed"]
    assert sorted(old["files"]) == ["lines.arrow", "profiles.arrow"] and old["error"] == words, old
    # The Download (the user, 2026-11-16: "No Download there"): a share link's page of a run with a store has none, in
    # its actions bar (.r-actions: no button "Download", no menu .r-downloads), the page itself drawn (the map, the
    # rows, the bar); a not-signed-in visitor's demo run with a store has none either
    demo = found["demo"]
    for got in (store, demo):
        assert "timeout" not in got and got["map"] and got["actionsBar"] and got["lines"] > 0, got
        assert "Download" not in got["actions"] and not got["menu"] and got["downloads"] is None, got


PROBE_FAILURES_SCRIPT = r"""
const fs = require("fs");
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
// A made-up XMLHttpRequest as the servers answer: a file served with web.SIZE_HEADER, a missing one (404) with a short
// body and its Content-Length only (as web.RunFiles' "Not Found"); `broken` files answer 502, `dropped` ones fail as a
// network error. /s/<token>/ serves the case `shared[token]`; every send, answer and progress report is an event.
const events = [], broken = new Set(), dropped = new Set(), shared = {};
const NOT_FOUND = Buffer.from('{"detail":"Not Found"}');
class FakeXHR {
  static HEADERS_RECEIVED = 2;
  open(method, url) { this.url = url; }
  setRequestHeader() {}
  getResponseHeader(name) {
    name = name.toLowerCase();
    if (name === "x-findaline-bytes") return this.status === 200 ? String(this.size) : null;
    return name === "content-length" ? String(this.size) : null;
  }
  send() {
    const path = this.url.replace("http://test", "");
    const runs = /^\/runs\/([^/]+)\/([^/]+)$/.exec(path), share = /^\/s\/([^/]+)\/([^/]+)$/.exec(path);
    const run = runs ? runs[1] : shared[share[1]], file = runs ? runs[2] : share[2], local = cases[run] + "/" + file;
    events.push("send " + file);
    setTimeout(() => {
      events.push("answer " + file);
      if (dropped.has(file)) { this.onerror(); return; }
      const found = fs.existsSync(local) ? fs.readFileSync(local) : null;
      this.status = broken.has(file) ? 502 : found ? 200 : 404;
      const b = this.status === 200 ? found : NOT_FOUND;
      const ab = new ArrayBuffer(b.length);
      new Uint8Array(ab).set(b);
      this.response = this.responseType === "text" ? b.toString("utf-8") : ab;
      this.size = ab.byteLength;
      this.readyState = 2;
      this.onreadystatechange && this.onreadystatechange();
      this.onprogress && this.onprogress({loaded: ab.byteLength});
      this.onload({loaded: ab.byteLength});
    });
  }
}
const block = {format: 1, lines: 0, bytes: 0, sha256: ""};
globalThis.window = globalThis;
window.FINDALINE_RUNS = [{id: "plain", name: "plain", created: "", description: "", store: block}];  // map's runs.js
globalThis.XMLHttpRequest = FakeXHR;
globalThis.location = {protocol: "http:", href: "http://test/app/", origin: "http://test"};
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.document = {createElement: () => ({remove() {}}), head: {appendChild(s) {  // no script may be added
  events.push("script " + s.src);
  setTimeout(() => s.onerror());
}}};
const outcome = async (token, run) => {
  events.splice(0);
  shared[token] = run;
  const report = (p) => { if (p.total != null) events.push("progress " + p.done + " of " + p.total); };
  const load = token === "listed" ? m.loadRun("plain", "/runs/", report) : m.loadRun(token, "/s/", report);
  try { const d = await load; return {ok: d.columns.length, events: events.splice(0)}; }
  catch (e) { return {error: e.name, events: events.splice(0)}; }
};
(async () => {
  const out = {};
  out.store = await outcome("t1", "zone");          // both store files asked for before either answers
  out.old = await outcome("t2", "old");             // no store: two 404s with a body, no progress from them, refused
  broken.add("lines.arrow");
  out.badGateway = await outcome("t3", "zone");     // a probe's file answers 502: refused
  out.listedBadGateway = await outcome("listed", "plain");  // a listed store's file answers 502: refused
  broken.clear();
  dropped.add("profiles.arrow");
  out.networkError = await outcome("t4", "zone");   // a probe's file fails on the network: refused
  dropped.clear();
  out.newer = await outcome("t5", "newer");         // a probe that finds a store of a newer format: refused
  out.unreadable = await outcome("t6", "garbage");  // a probe that finds a store it cannot read: refused
  console.log(JSON.stringify(out));
})();
"""


def test_the_probes_failures_and_progress(tmp_path, store_cases):
    """The probe (a share link's run here): its two store files asked for at once (both sent before either answers);
    a 404 (with a short body that has a Content-Length) reports no progress and is a StoreFailed, as are a file that
    cannot be fetched (502, a network error) and a listed store's 502; a store the probe fetched but of a newer format
    (NewerStore) or unreadable (StoreFailed) is refused; nothing else is asked for and no script added (store wave 4's
    item 5: no data.js)."""
    import shutil

    import pyarrow as pa

    import linestore
    cases = {name: str(folder).replace("\\", "/") for name, folder in store_cases.items()}
    old = tmp_path / "old"  # a run saved before the store: no store files
    shutil.copytree(store_cases["zone"], old, ignore=shutil.ignore_patterns("*.arrow"))
    newer = tmp_path / "newer"  # a store whose metadata says format 2
    shutil.copytree(store_cases["zone"], newer)
    with pa.OSFile(str(newer / linestore.LINES_FILE), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    meta["format"] = linestore.FORMAT + 1
    linestore._write_file(str(newer / linestore.LINES_FILE),
                          table.replace_schema_metadata({linestore.META_KEY: json.dumps(meta).encode("utf-8")}))
    garbage = tmp_path / "garbage"
    shutil.copytree(store_cases["zone"], garbage)
    (garbage / linestore.LINES_FILE).write_bytes(b"not an Arrow file " * 100)
    cases.update(old=str(old).replace("\\", "/"), newer=str(newer).replace("\\", "/"),
                 garbage=str(garbage).replace("\\", "/"))
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    out = _run_node(tmp_path, _store_bundle(tmp_path), PROBE_FAILURES_SCRIPT, cases_path)
    store = out["store"]
    assert store["ok"] == 3000 and sorted(store["events"][:2]) == ["send lines.arrow", "send profiles.arrow"], store
    old_events = out["old"]["events"]
    assert out["old"]["error"] == "StoreFailed" and not any(e.startswith("progress") for e in old_events), old_events
    for name, error in (("old", "StoreFailed"), ("badGateway", "StoreFailed"), ("networkError", "StoreFailed"),
                        ("listedBadGateway", "StoreFailed"), ("newer", "NewerStore"), ("unreadable", "StoreFailed")):
        got = out[name]
        sent = [e for e in got["events"] if e.startswith(("send", "script"))]
        assert got.get("error") == error, (name, got)
        assert sent in ([], ["send lines.arrow", "send profiles.arrow"], ["send profiles.arrow", "send lines.arrow"]), \
            (name, got)
