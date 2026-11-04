"""The layout of a result on a desktop (viewer/src/result/view/layout.ts): the kept value made safe, the side
panels fitted to a window (shrunk, then collapsed, never kept), the profile card's insets and height, and the
card and a splitter in headless Edge (the keys and the pointer change the card's size, the chart follows).

Needs Node and `npm install` in viewer/; skipped without them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")


def run_layout(tmp_path, script: str):
    """Bundle layout.ts for Node and run `script` with it as `m`; returns its JSON output."""
    bundle = tmp_path / "layout.cjs"
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['src/result/view/layout.ts'], "
                                  f"bundle: true, format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    path = tmp_path / "layout-test.cjs"
    path.write_text(f"const m = require({json.dumps(str(bundle))});\n{script}", encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


DEFAULT = {"v": 1, "list": {"w": 340, "open": True}, "details": {"w": 380, "open": True},
           "profile": {"h": 260, "folded": False, "l": 12, "r": 12}}


def test_defaults_and_sanitize(tmp_path):
    """Anything but a layout of version 1 gives the defaults; each field is clamped or replaced by its default."""
    out = run_layout(tmp_path, """
const bad = [null, undefined, "x", 3, [], {v: 2, list: {w: 300}}, {list: {w: 300}}];
console.log(JSON.stringify({
  defaults: m.DEFAULT_LAYOUT, limits: m.LIMITS,
  bad: bad.map((v) => m.sanitize(v)),
  clamped: m.sanitize({v: 1, list: {w: 9999, open: "no"}, details: {w: "a", open: false},
                       profile: {h: -5, folded: "yes", l: NaN, r: 13.6}}),
  infinite: m.sanitize({v: 1, list: {w: Infinity}, details: {w: 100}, profile: {h: 1e9, folded: true, l: 1e9, r: -1}}),
  parts: m.sanitize({v: 1, list: 5, details: null, profile: "x"}),
  kept: m.sanitize({v: 1, list: {w: 400, open: false}, details: {w: 500, open: true},
                    profile: {h: 300, folded: true, l: 40, r: 90}}),
}));""")
    assert out["defaults"] == DEFAULT
    assert out["limits"] == {"list": [260, 560], "details": [300, 600], "rail": 36, "map": 360, "cardMin": 160,
                             "cardShare": 0.7, "low": 420, "cardWidthMin": 360, "inset": 12}
    assert out["bad"] == [DEFAULT] * 7
    assert out["clamped"] == {"v": 1, "list": {"w": 560, "open": True}, "details": {"w": 380, "open": False},
                              "profile": {"h": 160, "folded": False, "l": 12, "r": 14}}
    assert out["infinite"] == {"v": 1, "list": {"w": 340, "open": True}, "details": {"w": 300, "open": True},
                               "profile": {"h": 2000, "folded": True, "l": 4000, "r": 12}}
    assert out["parts"] == DEFAULT
    assert out["kept"] == {"v": 1, "list": {"w": 400, "open": False}, "details": {"w": 500, "open": True},
                           "profile": {"h": 300, "folded": True, "l": 40, "r": 90}}


def test_load_and_save(tmp_path):
    """localStorage "findaline.layout": kept and read back, a bad value or no storage gives the defaults."""
    out = run_layout(tmp_path, """
const store = {};
globalThis.localStorage = {getItem: (k) => k in store ? store[k] : null, setItem: (k, v) => { store[k] = String(v); }};
const found = {empty: m.loadLayout()};
const mine = m.sanitize({v: 1, list: {w: 420, open: false}, details: {w: 333, open: true},
                         profile: {h: 222, folded: true, l: 30, r: 44}});
m.saveLayout(mine);
found.key = Object.keys(store);
found.back = m.loadLayout();
store["findaline.layout"] = "{not json";
found.broken = m.loadLayout();
store["findaline.layout"] = JSON.stringify({v: 1, list: {w: 1}});
found.old = m.loadLayout();
globalThis.localStorage = {getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }};
found.blocked = m.loadLayout();
m.saveLayout(mine);  // does not throw
delete globalThis.localStorage;
found.none = m.loadLayout();
m.saveLayout(mine);
console.log(JSON.stringify(found));""")
    assert out["empty"] == DEFAULT and out["key"] == ["findaline.layout"]
    assert out["back"] == {"v": 1, "list": {"w": 420, "open": False}, "details": {"w": 333, "open": True},
                           "profile": {"h": 222, "folded": True, "l": 30, "r": 44}}
    assert out["broken"] == DEFAULT
    assert out["old"] == {**DEFAULT, "list": {"w": 260, "open": True}}
    assert out["blocked"] == DEFAULT and out["none"] == DEFAULT


def test_fit_columns(tmp_path):
    """The panels in a window: shrunk in proportion to what each has above its minimum, then the details
    collapse, then the list (forced); `prefer` collapses the other first; a panel the user collapsed is a rail."""
    out = run_layout(tmp_path, """
const L = m.DEFAULT_LAYOUT, closed = {...L, details: {w: 380, open: false}};
const fit = (layout, w, prefer = null) => m.fitColumns(layout, w, prefer);
const wide = [400, 1000, 1400].map((w) => fit(L, w));
console.log(JSON.stringify({
  w1400: fit(L, 1400), w1000: fit(L, 1000), w900: fit(L, 900), w700: fit(L, 700), w600: fit(L, 600),
  prefer: fit(L, 900, "details"), preferList: fit(L, 900, "list"), closed: fit(closed, 1000),
  max: {list1400: m.maxColumnWidth("list", 1400, fit(L, 1400)), list1000: m.maxColumnWidth("list", 1000, fit(L, 1000)),
        details1400: m.maxColumnWidth("details", 1400, fit(L, 1400)),
        detailsRail: m.maxColumnWidth("details", 1400, fit({...L, list: {w: 340, open: false}}, 1400)),
        tiny: m.maxColumnWidth("list", 600, fit(L, 600))},
  unchanged: L,
}));""")
    col = lambda open, width, forced=False: {"open": open, "width": width, "forced": forced}  # noqa: E731
    assert out["w1400"] == {"list": col(True, 340), "details": col(True, 380)}
    # 1000 px: 640 for both, 80 too much, each has 80 above its minimum: 40 off each
    assert out["w1000"] == {"list": col(True, 300), "details": col(True, 340)}
    # 900 px: 180 too much, 160 to shrink: the details collapse, the list fits beside its rail
    assert out["w900"] == {"list": col(True, 340), "details": col(False, 380, True)}
    # 700 px: the details collapse, the list shrinks to 700 - 360 - 36
    assert out["w700"] == {"list": col(True, 304), "details": col(False, 380, True)}
    assert out["w600"] == {"list": col(False, 340, True), "details": col(False, 380, True)}
    assert out["prefer"] == {"list": col(False, 340, True), "details": col(True, 380)}
    assert out["preferList"] == out["w900"]
    assert out["closed"] == {"list": col(True, 340), "details": col(False, 380)}
    assert out["max"] == {"list1400": 560, "list1000": 300, "details1400": 600, "detailsRail": 600, "tiny": 260}
    assert out["unchanged"] == DEFAULT


def test_card_insets_height_and_edges(tmp_path):
    """The card's insets (narrowed in proportion, not kept, in a narrow map), its height within its limits, and
    moving one edge keeps the other where it was."""
    out = run_layout(tmp_path, """
const L = m.DEFAULT_LAYOUT, wideCard = m.sanitize({v: 1, profile: {h: 260, l: 300, r: 100}});
const tall = m.sanitize({v: 1, profile: {h: 1000}});
const moved = m.moveCardEdge(L, "l", 200, [12, 12], 1000);
console.log(JSON.stringify({
  insets: [m.cardInsets(L, 1000), m.cardInsets(wideCard, 1000), m.cardInsets(wideCard, 600), m.cardInsets(L, 300),
           m.cardInsets(m.sanitize({v: 1, profile: {l: 100}}), 300)],
  least: [m.cardWidthMin(1000), m.cardWidthMin(300)],
  moved: moved.profile, far: m.moveCardEdge(L, "l", 900, [12, 12], 1000).profile,
  right: m.moveCardEdge(moved, "r", 50, [200, 12], 1000).profile,
  rightOut: m.moveCardEdge(moved, "r", -40, [200, 12], 1000).profile,
  rightFar: m.moveCardEdge(moved, "r", 2000, [200, 12], 1000).profile,
  fromNarrowed: m.moveCardEdge(wideCard, "l", 150, m.cardInsets(wideCard, 600), 600).profile,
  input: L.profile,
  heights: [m.cardHeight(L, 800), m.cardHeight(L, 300), m.cardHeight(L, 200), m.cardHeight(tall, 800),
            m.cardHeight(m.sanitize({v: 1, profile: {h: 100}}), 800)],
  max: [m.cardMaxHeight(800), m.cardMaxHeight(100)],
  low: [m.isLowMap(419), m.isLowMap(420)],
}));""")
    assert out["insets"] == [[12, 12], [300, 100], [177, 63], [12, 12], [12, 12]]
    assert out["least"] == [360, 276]
    assert out["moved"] == {"h": 260, "folded": False, "l": 200, "r": 12}
    assert out["far"]["l"] == 1000 - 12 - 360 and out["far"]["r"] == 12
    assert out["right"] == {"h": 260, "folded": False, "l": 200, "r": 50}
    assert out["rightOut"]["r"] == 12 and out["rightFar"]["r"] == 1000 - 200 - 360
    # From insets narrowed by a narrow map: the other edge keeps where it was drawn, and that is kept
    assert out["fromNarrowed"] == {"h": 260, "folded": False, "l": 150, "r": 63}
    assert out["input"] == DEFAULT["profile"]
    assert out["heights"] == [260, 210, 160, 560, 160]
    assert out["max"] == [560, 160]
    assert out["low"] == [True, False]


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


from test_viewer import clip_data  # noqa: E402,F401  (a run of the Żabi Koń clip, the fixture)


def _playwright() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_profile_card_in_edge(tmp_path, clip_data):
    """result/view/ProfileCard in headless Edge on a test page of a run served by the app (its CSP), over a Leaflet
    map in a box of 1000 × 700 px: the top edge's keys and pointer change the card's height and the chart follows,
    Home/End go to its limits (the chart keeps 120 px), the side edges move one inset each (a double click resets
    it), the corners go above the card only where it covers them, the fold button and Enter, a low box opens it
    folded (unfolding there is not kept), a narrow box shrinks the insets (not kept), × removes it."""
    import test_web  # the app on a real server, its CSP stubs
    text, data = clip_data
    run_id = data["run"]["id"]
    folder = tmp_path / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "data.js").write_text(f"window.FINDALINE_RUN = {text};\n", encoding="utf-8")
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['test/profilecard_page.tsx'], "
                                  "bundle: true, format: 'iife', target: 'es2020', "
                                  "loader: {'.png': 'dataurl', '.svg': 'text', '.woff2': 'file'}, "
                                  f"outdir: {json.dumps(str(folder))}}})"], cwd=VIEWER, check=True)
    (folder / "csp_stub.js").write_text(test_web.CSP_STUB, encoding="utf-8")
    (folder / "card_test.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="profilecard_page.css">'
        '<script src="csp_stub.js"></script></head><body><script src="profilecard_page.js"></script></body></html>',
        encoding="utf-8")
    # Playwright, not --dump-dom: its virtual time draws no frame, so no ResizeObserver ever reports
    from playwright.sync_api import sync_playwright
    with test_web._server(tmp_path) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(f"http://127.0.0.1:{port}/runs/{run_id}/card_test.html")
            page.wait_for_selector("#result", state="attached", timeout=60000)
            out = json.loads(page.text_content("#result"))
            violations = page.evaluate("() => window.CSP_VIOLATIONS")
        finally:
            browser.close()
    assert "error" not in out, out["error"]
    # Drawn at the kept height (260 unless its content needs more), the chart filling its box
    first = out["initial"]
    assert first["height"] >= 260 and not first["folded"] and first["left"] == 12 and first["width"] == 976, first
    assert first["chart"]["svg"] == first["chart"]["box"] >= 120, first
    assert (first["min"], first["max"]) == (160, 490), first
    assert out["initialCorners"]["attribution"] not in ("", None), out["initialCorners"]
    # ↑ and Shift+↑: 80 px more, each key kept, the chart grows with it
    keys = out["keys"]
    assert keys["height"] == first["height"] + 80 and keys["commits"] == 2 and keys["kept"] == first["height"] + 80, out
    assert keys["chart"]["svg"] == keys["chart"]["box"] == first["chart"]["box"] + 80, out
    # The pointer: 40 px more while dragging, kept only when released
    assert out["dragging"]["height"] == keys["height"] + 40 and out["dragging"]["commits"] == 2, out
    assert "u-dragging" in out["dragging"]["cls"], out
    assert out["dragged"]["commits"] == 3 and out["dragged"]["kept"] == keys["height"] + 40, out
    # Home: the least height (the card's content may need more: the chart keeps 120 px); End: 70 % of the map
    home = out["home"]
    assert home["kept"] == 160 and home["height"] >= 160 and home["chart"]["box"] >= 120, home
    assert home["chart"]["svg"] == max(120, home["chart"]["box"]), home
    assert out["end"]["height"] == 490 and out["end"]["chart"]["svg"] == out["end"]["chart"]["box"], out["end"]
    # The sides
    assert out["leftKey"]["left"] == 28 and out["leftKey"]["width"] == 960 and out["leftKey"]["r"] == 12, out
    assert (out["rightDrag"]["l"], out["rightDrag"]["r"]) == (28, 112) and out["rightDrag"]["width"] == 860, out
    assert out["leftReset"] == {"l": 12, "r": 112, "kept": 12}, out
    clear = out["clearOfAttribution"]
    assert clear["r"] == 1000 - 12 - 360 and clear["width"] == 360, clear
    assert clear["corners"]["attribution"] == "" and clear["corners"]["scale"] not in ("", None), clear
    assert out["coveringAgain"]["attribution"] not in ("", None), out
    # Folded and unfolded (kept: not a low map)
    folded = out["folded"]
    assert folded["folded"] and folded["kept"] is True and folded["commits"] == 1 and folded["height"] < 80, folded
    assert folded["label"] == "Unfold the profile" and folded["expanded"] == "false", folded
    assert int(folded["corners"]["attribution"].rstrip("px")) < 120, folded
    assert not out["unfolded"]["folded"] and out["unfolded"]["kept"] is False, out
    # A low map: folded though the layout is not; unfolded there without anything kept
    assert out["low"]["folded"] and out["low"]["kept"] is False, out
    assert not out["lowUnfolded"]["folded"] and out["lowUnfolded"]["commits"] == 0, out
    assert not out["backHigh"]["folded"], out
    # A narrow map: the card keeps its least width, the kept inset stays
    narrow = out["narrow"]
    assert narrow["width"] == 360 and narrow["l"] == narrow["wideL"] == 140 and narrow["commits"] == 0, narrow
    assert narrow["left"] == 500 - 12 - 360, narrow
    assert out["closed"] == {"card": False, "closed": True, "corners": {"attribution": "", "scale": ""}}, out
    assert violations == []
