"""Home's mini maps read a run's store (store wave 4, item 3; docs/line-volume/spec-store.md 1.9 row 4): a run with a
store and at most Thumb.MAX_LINES lines draws its lines from its lines.arrow (never profiles.arrow), the same picture
as from its lines.js; a run listed without a store reads its lines.js as before; a run the list of runs does not name
asks for its lines.arrow directly (result/load.ts loadRunLines, as storeOf's STORE_PROBE); a store that fails (both
files missing, a fetch error, a file that is no store, a newer format) shows the card's placeholder as a lines.js
that failed, and a newer store never reads lines.js; a run of more lines asks for none. In headless Edge on the local
app with the Żabi Koń clip's run (1 048 lines, its store and lines.js both written by save_run); on the public site
the page's list of runs gives the store and RunFiles serves lines.arrow to the run's owner only."""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runs as rn  # noqa: E402
import web  # noqa: E402

pytest.importorskip("httpx2")

from test_shell_c import C_STUBS, HELPERS, RUN_DATA, _edge, copy_clip, drop_store, stub_page  # noqa: E402
from test_public import (RUN_A, RUN_B, account_settings, clip_run, providers, run_people,  # noqa: E402,F401
                         settings)
from test_web import EDGE, _server  # noqa: E402


def run_id(name: str) -> str:
    return f"2026-10-20_120000_{name}_{name.lower():0>16}"


STORED = run_id("Stored")        # the clip's run as saved: its store listed in runs.js
SCRIPT = run_id("Script")        # the same run listed without its store block: lines.js
MISSING = run_id("Missing")      # listed with a store whose lines.arrow is gone (404): lines.js, while runs keep it
GONE = run_id("Gone")            # listed with a store, lines.arrow and lines.js both gone: the placeholder
BROKEN = run_id("Broken")        # listed with a store whose lines.arrow is no Arrow file
NEWER = run_id("Newer")          # listed with a store of a newer format (run.json's block)
FAILING = run_id("Failing")      # listed with a store whose download fails (a network error)
UNLISTED = run_id("Unlisted")    # left out of the page's list (saved since it was read): its store asked for
UNLISTED_OLD = run_id("Unold")   # left out of the list, without a store: lines.arrow's 404, then lines.js
UNLISTED_NEW = run_id("Unnew")   # left out of the list, its lines.arrow of a newer format (the file's metadata)
UNLISTED_FAIL = run_id("Unfail")  # left out of the list, its lines.arrow not fetched: lines.js
LARGE = run_id("Large")          # more lines than a mini map draws (MAX_LINES): no request for its lines
DRAWN = (STORED, SCRIPT, MISSING, UNLISTED, UNLISTED_OLD, UNLISTED_FAIL)
FAILED = (GONE, BROKEN, NEWER, FAILING, UNLISTED_NEW)
HIDDEN = (UNLISTED, UNLISTED_OLD, UNLISTED_NEW, UNLISTED_FAIL)
NOT_FETCHED = (FAILING, UNLISTED_FAIL)
MAX_LINES = 3000  # viewer/src/app/c/Thumb.tsx

# Before the app: the runs of HIDDEN left out of runs.js's list, and every download of NOT_FETCHED's files a network
# error (the requests recorded)
THUMB_STUBS = C_STUBS + """
const HIDDEN = %(hidden)s, NOT_FETCHED = %(not_fetched)s;
let listed;
Object.defineProperty(window, "FINDALINE_RUNS", {configurable: true, get: () => listed,
  set: (runs) => { listed = runs && runs.filter((r) => !HIDDEN.includes(r.id)); }});
window.NOT_FETCHED_ASKED = [];
const xhrOpen = XMLHttpRequest.prototype.open, xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (method, url, ...rest) {
  this.notFetched = NOT_FETCHED.some((id) => String(url).includes("/" + id + "/")) ? String(url) : null;
  return xhrOpen.call(this, method, url, ...rest);
};
XMLHttpRequest.prototype.send = function (...args) {
  if (!this.notFetched) return xhrSend.apply(this, args);
  NOT_FETCHED_ASKED.push(new URL(this.notFetched, location.href).pathname);
  setTimeout(() => this.onerror && this.onerror(new ProgressEvent("error")), 0);
};
"""

THUMB_SCRIPT = """
const RUNS = %(runs)s, RUN_FILES = %(run_files)s;
window.addEventListener("unhandledrejection", (e) => { result.rejection = String(e.reason && e.reason.stack || e.reason); });
const asked = () => performance.getEntriesByType("resource").map((e) => new URL(e.name).pathname);
const filesOf = (id) => asked().filter((p) => p.startsWith("/runs/" + id + "/")).map((p) => p.split("/").pop());
const thumbOf = (id) => card("run", id) && card("run", id).querySelector(".c-thumb");
run({
  thumbs(next) { wait(() => RUNS.every((id) => thumbOf(id) && thumbOf(id).dataset.thumb !== "loading"), () => {
    result.cards = Object.fromEntries(RUNS.map((id) => {
      const t = thumbOf(id), svg = t.querySelector(":scope > svg");
      return [id, {thumb: t.dataset.thumb, lines: t.dataset.lines === undefined ? null : Number(t.dataset.lines),
                   svg: svg ? svg.outerHTML : null, paths: svg ? svg.querySelectorAll("path.c-thumb-line").length : 0,
                   label: (t.querySelector(".c-thumb-label") || {}).textContent || "",
                   icon: !!t.querySelector(".c-thumb-empty svg"), files: filesOf(id)}];
    }));
    result.notFetched = window.NOT_FETCHED_ASKED;
    result.lists = asked().filter((p) => p.endsWith("/runs.js"));
    result.outside = asked().filter((p) => /^\\/runs\\/[^/]+\\/[^/]+$/.test(p) && !p.startsWith("/runs/_viewer/")
                                       && !p.startsWith("/runs/cthumb/") && !RUN_FILES.includes(p.split("/").pop()));
    next();
  }); },
});
"""


def _newer_file(folder):
    """lines.arrow with the metadata's `format` above linestore.FORMAT (run.json's block left as it was)."""
    import pyarrow as pa
    import linestore
    path = os.path.join(str(folder), linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    meta["format"] = linestore.FORMAT + 1
    linestore._write_file(path, table.replace_schema_metadata(
        {linestore.META_KEY: json.dumps(meta, ensure_ascii=False).encode("utf-8")}))


def _edit_meta(folder, change):
    path = folder / "run.json"
    meta = json.loads(path.read_text("utf-8"))
    change(meta)
    path.write_text(json.dumps(meta), "utf-8")


@pytest.fixture
def thumb_data(tmp_path, clip_run):
    """A local data folder with the clip's run as every case above."""
    import linestore
    data = tmp_path / "data"
    runs = data / "runs"
    for k, name in enumerate(DRAWN + FAILED + (LARGE,)):
        copy_clip(clip_run, data, name, f"Run {k}")
        _edit_meta(runs / name, lambda m, k=k: m.update(created=f"2026-10-20T12:{k:02d}:00"))
    assert json.loads((runs / STORED / "run.json").read_text("utf-8"))["store"]["lines"] <= MAX_LINES
    drop_store(data, SCRIPT)
    (runs / MISSING / linestore.LINES_FILE).unlink()
    for name in (linestore.LINES_FILE, "lines.js"):
        (runs / GONE / name).unlink()
    (runs / BROKEN / linestore.LINES_FILE).write_bytes(b"not an Arrow file " * 100)
    _edit_meta(runs / NEWER, lambda m: m["store"].update(format=m["store"]["format"] + 1))
    for name in linestore.FILES:
        (runs / UNLISTED_OLD / name).unlink()
    drop_store(data, UNLISTED_OLD)
    _newer_file(runs / UNLISTED_NEW)
    _edit_meta(runs / LARGE, lambda m: m["summary"].update(lines=MAX_LINES + 1))
    rn.write_index(str(runs))
    return data


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_thumbnails_from_the_store(thumb_data, tmp_path):
    """Each case's mini map, the files its run's folder was asked for (resource timing: 404s too) and the picture:
    the store's and lines.js's SVG the same, element for element; no CSP violation, no unhandled rejection."""
    import linestore
    runs = list(DRAWN + FAILED + (LARGE,))
    stubs = THUMB_STUBS % {"hidden": json.dumps(list(HIDDEN)), "not_fetched": json.dumps(list(NOT_FETCHED))}
    page = stub_page(thumb_data, "cthumb", THUMB_SCRIPT % {"runs": json.dumps(runs),
                                                           "run_files": json.dumps(list(web.RUN_FILES))}, stubs=stubs)
    with _server(thumb_data) as port:
        r = _edge(port, page + "?ui=c", tmp_path / "edge-thumb", size="1280,6000")  # every card in view
    assert "timeout" not in r and "error" not in r and "rejection" not in r, json.dumps(r)[:3000]
    assert r["csp"] == []
    cards = r["cards"]
    lines = json.loads((thumb_data / "runs" / STORED / "run.json").read_text("utf-8"))["store"]["lines"]
    data_of = lambda name: [f for f in cards[name]["files"] if f in RUN_DATA]  # noqa: E731
    # 1. the store's lines.arrow alone; lines.js for a run listed without a store; nothing for a large run
    assert data_of(STORED) == ["lines.arrow"], cards[STORED]
    assert data_of(SCRIPT) == ["lines.js"], cards[SCRIPT]
    assert data_of(UNLISTED) == ["lines.arrow"], cards[UNLISTED]
    assert data_of(UNLISTED_OLD) == ["lines.arrow", "lines.js"], cards[UNLISTED_OLD]  # the probe's 404 first
    assert data_of(MISSING) == ["lines.arrow", "lines.js"], cards[MISSING]  # lines.js while runs keep it
    assert data_of(UNLISTED_FAIL) == ["lines.js"], cards[UNLISTED_FAIL]  # its lines.arrow not fetched
    for name in DRAWN:
        assert cards[name]["thumb"] == "lines" and cards[name]["lines"] == lines and cards[name]["paths"] >= 1, \
            (name, cards[name])
    assert cards[LARGE]["thumb"] == "outline" and data_of(LARGE) == [], cards[LARGE]
    assert cards[LARGE]["label"] == f"{MAX_LINES + 1:,} lines", cards[LARGE]
    # 2. the same picture from the store as from lines.js: the tiles, the area and the lines, in the same order
    assert cards[STORED]["svg"] and cards[STORED]["svg"].count("<path") >= 2, cards[STORED]
    for name in DRAWN[1:]:
        assert cards[name]["svg"] == cards[STORED]["svg"], name
    # 3. a store that fails: the placeholder as a lines.js that fails, never a blank card; a newer one reads no lines.js
    assert data_of(GONE) == ["lines.arrow", "lines.js"], cards[GONE]
    assert data_of(BROKEN) == ["lines.arrow"], cards[BROKEN]
    assert data_of(NEWER) == [], cards[NEWER]  # refused by run.json's block before any download
    assert data_of(UNLISTED_NEW) == ["lines.arrow"], cards[UNLISTED_NEW]
    assert data_of(FAILING) == [], cards[FAILING]
    assert sorted(r["notFetched"]) == sorted(f"/runs/{name}/{linestore.LINES_FILE}" for name in NOT_FETCHED), r
    for name in FAILED:
        assert cards[name]["thumb"] == "failed" and cards[name]["svg"] is None and cards[name]["icon"], \
            (name, cards[name])
    # 4. only files RunFiles serves, and the list of runs once; 5. never profiles.arrow
    assert r["outside"] == [] and r["lists"] == ["/runs/runs.js"], r
    assert not any("profiles.arrow" in cards[name]["files"] for name in runs), cards


def test_public_runs_list_gives_the_store(run_people):
    """On the public site a user's list of runs (/runs/runs.js, what Thumb looks a run up in) carries the run's
    store block, and its lines.arrow (web.RUN_FILES) is served to its owner only: the mini map's one request."""
    a, b = run_people["a"], run_people["b"]
    listed = json.loads(a.get("/runs/runs.js").text.split("window.FINDALINE_RUNS = ")[1].split(";\n")[0])
    assert [r["id"] for r in listed] == [RUN_A] and listed[0]["store"]["lines"] > 0, listed
    assert "lines.arrow" in web.RUN_FILES
    assert a.get(f"/runs/{RUN_A}/lines.arrow").status_code == 200
    assert b.get(f"/runs/{RUN_A}/lines.arrow").status_code == 404
    assert RUN_B not in a.get("/runs/runs.js").text
