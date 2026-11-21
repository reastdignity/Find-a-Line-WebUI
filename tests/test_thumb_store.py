"""Home's mini maps read a run's store (store wave 4, item 3; docs/line-volume/spec-store.md 1.9 row 4): a run with a
store and at most Thumb.MAX_LINES lines draws its lines from its lines.arrow (never profiles.arrow), the same picture
whether the list of runs names its store, names it without the block, or does not name the run (result/load.ts
loadRunLines: STORE_PROBE); a store that fails (a missing file, a run without a store, a fetch error, a file that is no
store, a newer format) shows the card's placeholder and asks for nothing else (since item 5 no lines.js); a run of
more lines asks for none. In headless Edge on the local app with the Żabi Koń clip's run (1 048 lines; no line too
close to trees or buildings without a surface model) and the first lines of the big clip's (surface model: both kinds
of line, each its own path); on the public site the page's list of runs gives the store and RunFiles serves
lines.arrow to the run's owner only."""

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

from test_shell_c import (C_STUBS, HELPERS, RUN_DATA, _edge, big_clip, copy_clip, drop_store, small_copy,  # noqa: E402,F401
                          stub_page)
from test_public import (RUN_A, RUN_B, account_settings, clip_run, providers, run_people,  # noqa: E402,F401
                         settings)
from test_web import EDGE, _server  # noqa: E402


def run_id(name: str) -> str:
    return f"2026-10-20_120000_{name}_{name.lower():0>16}"


STORED = run_id("Stored")        # the clip's run as saved: its store listed in runs.js
NOBLOCK = run_id("Noblock")      # the same run listed without its store block: its store asked for directly
UNLISTED = run_id("Unlisted")    # left out of the page's list (saved since it was read): its store asked for
MISSING = run_id("Missing")      # listed with a store whose lines.arrow is gone (404)
OLD = run_id("Old")              # a run of before (no store, no block: tests/old_runs.py), until runs remove-old
BROKEN = run_id("Broken")        # listed with a store whose lines.arrow is no Arrow file
NEWER = run_id("Newer")          # listed with a store of a newer format (run.json's block)
FAILING = run_id("Failing")      # listed with a store whose download fails (a network error)
UNLISTED_NEW = run_id("Unnew")   # left out of the list, its lines.arrow of a newer format (the file's metadata)
UNLISTED_FAIL = run_id("Unfail")  # left out of the list, its lines.arrow not fetched
LARGE = run_id("Large")          # more lines than a mini map draws (MAX_LINES): no request for its lines
DRAWN = (STORED, NOBLOCK, UNLISTED)
FAILED = (MISSING, OLD, BROKEN, NEWER, FAILING, UNLISTED_NEW, UNLISTED_FAIL)
HIDDEN = (UNLISTED, UNLISTED_NEW, UNLISTED_FAIL)
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
                   // each path's stroke and its lines (one "M" a line)
                   strokes: svg ? [...svg.querySelectorAll("path.c-thumb-line")]
                     .map((p) => [p.getAttribute("stroke"), (p.getAttribute("d").match(/M/g) || []).length]) : [],
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
    """A local data folder with the clip's run (saved since store wave 4: its store and no text file) as every case
    above."""
    import linestore
    data = tmp_path / "data"
    runs = data / "runs"
    for k, name in enumerate(DRAWN + FAILED + (LARGE,)):
        copy_clip(clip_run, data, name, f"Run {k}")
        _edit_meta(runs / name, lambda m, k=k: m.update(created=f"2026-10-20T12:{k:02d}:00"))
    assert json.loads((runs / STORED / "run.json").read_text("utf-8"))["store"]["lines"] <= MAX_LINES
    _edit_meta(runs / NOBLOCK, lambda m: m.pop("store"))
    drop_store(data, OLD)
    (runs / MISSING / linestore.LINES_FILE).unlink()
    (runs / BROKEN / linestore.LINES_FILE).write_bytes(b"not an Arrow file " * 100)
    _edit_meta(runs / NEWER, lambda m: m["store"].update(format=m["store"]["format"] + 1))
    _newer_file(runs / UNLISTED_NEW)
    _edit_meta(runs / LARGE, lambda m: m["summary"].update(lines=MAX_LINES + 1))
    rn.write_index(str(runs))
    return data


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_thumbnails_from_the_store(thumb_data, tmp_path):
    """Each case's mini map, the files its run's folder was asked for (resource timing: 404s too) and the picture:
    the same SVG, element for element, however the store is found; no CSP violation, no unhandled rejection."""
    import linestore
    runs = list(DRAWN + FAILED + (LARGE,))
    stubs = THUMB_STUBS % {"hidden": json.dumps(list(HIDDEN)), "not_fetched": json.dumps(list(NOT_FETCHED))}
    page = stub_page(thumb_data, "cthumb", THUMB_SCRIPT % {"runs": json.dumps(runs),
                                                           "run_files": json.dumps(list(web.RUN_FILES))}, stubs=stubs,
                     today=True)
    with _server(thumb_data) as port:
        r = _edge(port, page + "?ui=c", tmp_path / "edge-thumb", size="1280,6000")  # every card in view
    assert "timeout" not in r and "error" not in r and "rejection" not in r, json.dumps(r)[:3000]
    assert r["csp"] == []
    cards = r["cards"]
    lines = json.loads((thumb_data / "runs" / STORED / "run.json").read_text("utf-8"))["store"]["lines"]
    data_of = lambda name: [f for f in cards[name]["files"] if f in RUN_DATA]  # noqa: E731
    # 1. the store's lines.arrow alone, however the store is found; nothing for a large run
    for name in DRAWN:
        assert data_of(name) == ["lines.arrow"], (name, cards[name])
        assert cards[name]["thumb"] == "lines" and cards[name]["lines"] == lines and cards[name]["paths"] >= 1, \
            (name, cards[name])
    assert cards[LARGE]["thumb"] == "outline" and data_of(LARGE) == [], cards[LARGE]
    assert cards[LARGE]["label"] == f"{MAX_LINES + 1:,} lines", cards[LARGE]
    # 2. the same picture: the tiles, the area and the lines, in the same order
    assert cards[STORED]["svg"] and cards[STORED]["svg"].count("<path") >= 2, cards[STORED]
    assert sum(count for _, count in cards[STORED]["strokes"]) == lines, cards[STORED]["strokes"]
    for name in DRAWN[1:]:
        assert cards[name]["svg"] == cards[STORED]["svg"], name
    # 3. a store that fails: the placeholder, never a blank card, and no other file asked for (no lines.js)
    for name in (MISSING, OLD, BROKEN, UNLISTED_NEW):
        assert data_of(name) == ["lines.arrow"], (name, cards[name])
    for name in (NEWER, FAILING, UNLISTED_FAIL):  # refused by run.json's block before any download; not fetched
        assert data_of(name) == [], (name, cards[name])
    assert sorted(r["notFetched"]) == sorted(f"/runs/{name}/{linestore.LINES_FILE}" for name in NOT_FETCHED), r
    for name in FAILED:
        assert cards[name]["thumb"] == "failed" and cards[name]["svg"] is None and cards[name]["icon"], \
            (name, cards[name])
    # 4. only files RunFiles serves, and the list of runs once; 5. never profiles.arrow
    assert r["outside"] == [] and r["lists"] == ["/runs/runs.js"], r
    assert not any("profiles.arrow" in cards[name]["files"] for name in runs), cards


OVER = run_id("Over")  # the big clip's first lines, both kinds (over and clean)


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_thumbnail_over_and_clean_lines(tmp_path, big_clip):
    """The two kinds of line (the store's column `over`) drawn as two paths, each of as many lines as the store holds
    of its kind (linestore.read): the big clip's (surface model) first lines up to both kinds, at most MAX_LINES."""
    import linestore
    over = linestore.read(str(big_clip), profiles=False)[0].columns["over_obstacles"].astype(bool).tolist()
    first = next(i for i, value in enumerate(over) if value != over[0])
    n = min(MAX_LINES, max(300, first + 1))
    assert set(over[:n]) == {True, False}, n
    data = tmp_path / "data"
    big = run_id("Bigclip")
    copy_clip(big_clip, data, big, "Big run")
    small_copy(data, big, lines=n, small=OVER, name=OVER)
    stubs = THUMB_STUBS % {"hidden": "[]", "not_fetched": "[]"}
    page = stub_page(data, "cthumb", THUMB_SCRIPT % {"runs": json.dumps([OVER]),
                                                     "run_files": json.dumps(list(web.RUN_FILES))}, stubs=stubs,
                     today=True)
    with _server(data) as port:
        r = _edge(port, page + "?ui=c", tmp_path / "edge-over", size="1280,2000")
    assert "timeout" not in r and "error" not in r and "rejection" not in r, json.dumps(r)[:3000]
    assert r["csp"] == []
    card = r["cards"][OVER]
    assert [f for f in card["files"] if f in RUN_DATA] == ["lines.arrow"], card
    assert card["thumb"] == "lines" and card["lines"] == n and card["paths"] == 2, card
    assert sorted(count for _, count in card["strokes"]) == sorted([sum(over[:n]), n - sum(over[:n])]), card
    assert len({stroke for stroke, _ in card["strokes"]}) == 2, card


THUMB_LINES_SCRIPT = r"""
const fs = require("fs");
const bytes = (p) => { const b = fs.readFileSync(p), ab = new ArrayBuffer(b.length); new Uint8Array(ab).set(b); return ab; };
const drawn = m.thumbLines(m.readStore(bytes(process.argv[2] + "/lines.arrow"), null));
console.log(JSON.stringify(drawn.map((l) => [l.a[0], l.a[1], l.b[0], l.b[1], l.over])));
"""


@pytest.mark.skipif(not os.path.isdir(os.path.join(REPO, "viewer", "node_modules", "esbuild")),
                    reason="needs Node and `npm install` in viewer/")
def test_thumb_lines_are_the_stores_anchors(tmp_path, big_clip):
    """Thumb.tsx thumbLines on the page's reading of a store (result/load.ts readStore) gives every line, in the
    store's order, its anchors as [lon, lat] and its kind (`over`) exactly as Python's reading of the store gives them
    (linestore.read: the independent reference of the mini map's geometry, as test_store_gives_the_rows_values')."""
    import subprocess
    import linestore
    viewer = os.path.join(REPO, "viewer")
    src = os.path.join(viewer, "src").replace("\\", "/")
    entry = tmp_path / "thumb_entry.ts"
    entry.write_text(f'export {{ thumbLines }} from "{src}/app/c/Thumb";\n'
                     f'export {{ readStore }} from "{src}/result/load";\n', encoding="utf-8")
    bundle = tmp_path / "thumb.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], "
                                  "bundle: true, format: 'cjs', platform: 'node', "
                                  "loader: {'.css': 'empty', '.png': 'empty', '.svg': 'text'}, "
                                  f"outfile: {json.dumps(str(bundle))}}})"], cwd=viewer, check=True)
    script = tmp_path / "thumb-test.cjs"
    script.write_text("globalThis.document = {querySelector: () => null};  // app/api.ts reads the page's token\n"
                      f"const m = require({json.dumps(str(bundle))});\n{THUMB_LINES_SCRIPT}", encoding="utf-8")
    result = subprocess.run(["node", str(script), str(big_clip)], capture_output=True, text=True, encoding="utf-8",
                            timeout=300)
    assert result.returncode == 0, result.stderr
    drawn = json.loads(result.stdout)
    lines, _ = linestore.read(str(big_clip), profiles=False)
    a1, a2, over = lines.columns["anchor1"], lines.columns["anchor2"], lines.columns["over_obstacles"]
    expected = [[float(a1[i, 1]), float(a1[i, 0]), float(a2[i, 1]), float(a2[i, 0]), bool(over[i])]
                for i in range(len(lines))]
    assert len(drawn) == len(expected) > 1000 and {row[4] for row in expected} == {True, False}
    assert drawn == expected


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
