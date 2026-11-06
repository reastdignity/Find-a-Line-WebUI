"""Several lines in the 3D view (docs/3d-view-contract.md, "Round 2", decision 7; viewer/src/view3d/others.ts,
otherlines.ts, page.ts, save.ts and the 2D result's link): in Node the lines of the address (`&also=`: the limits, bad
entries dropped, "Copy link" carrying them), the inverse of the meta's affine against geometry.ts and a real
projection, which lines are drawn (inside the patch, over data, not the active one, the cap and the order), the label's
place, and the 2D result's link for a spot of one and of several lines; in headless Edge the page with the lines of
the address drawn (`data-others`), the tool "Saved lines", a click on a label making that line the active one (the
root's `data-edit`, the readout, the previous line among the others, "Back to the found line"), a favourite saved
through the app's API shown after the switch goes on and "Saved" when made active, at the full and the phone level,
with no Content-Security-Policy violation. Run the Edge test from PowerShell (headless Edge prints nothing from Git
Bash)."""

import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_viewer import VIEWER, clip_data as run_data, run_ts  # noqa: E402,F401 (the run's data.js: the model)
from test_view3d_profile import _clear_favourites  # noqa: E402
from test_view3d_reach import run_entry  # noqa: E402
from test_view3d import EDGE_SECONDS, VIRTUAL_BUDGET, _with_until  # noqa: E402 (the shared frame-counted waits)
from test_web import CSP_STUB, EDGE, LOCAL, TOKEN, _lines_of, _server, _violations, web  # noqa: E402

node = pytest.mark.skipif(not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                          reason="needs Node and `npm install` in viewer/")

FOUND = "50.1559508,19.7562722,50.1561234,19.757123"


@node
def test_the_address_hands_lines_over(tmp_path):
    """page.ts: `&also=` after `line`: entries separated by ";", each four finite numbers, kept in their canonical form,
    bad ones, repeats and the line itself dropped, at most 20; the link back to the map carries none, the link to this
    view carries them (the line shown never among them), and a page without `also` keeps its links byte for byte."""
    keys = [f"50.{1001 + 2 * k},19.{2001 + 2 * k},50.{1001 + 2 * k}1,19.{2001 + 2 * k}1" for k in range(30)]  # canonical
    found = run_ts(tmp_path, "view3d/page", f"""
const keys = {json.dumps(keys)};
const enc = (s) => encodeURIComponent(s);
const parse = (also, line = "1.5,2.5,3.5,4.5", search = "") =>
  m.parsePage(search, "#run=r1&line=" + line + (also === null ? "" : "&also=" + enc(also)), false);
const out = {{}};
out.none = parse(null).also;
out.empty = parse("").also;
out.two = parse("1,2,3,4;5.50,6,7,8").also;           // "5.50" is "5.5"
out.bad = parse("1,2,3;x,2,3,4;;1,2,3,4,5;,2,3,4;1,2,3,Infinity;9,9,9,9").also;
out.repeats = parse("1,2,3,4;1.0,2,3,4;1,2,3,4").also;
out.itself = parse("1.50,2.5,3.5,4.5;1,2,3,4", "1.5,2.5,3.5,4.5").also;
out.cap = parse(keys.join(";")).also.length;
out.capKeys = parse(keys.join(";")).also.slice(-1);
out.noLine = [parse("1,2,3,4", "nonsense").also, parse("1,2,3,4", "nonsense").line];
const p = parse("1,2,3,4;5,6,7,8");
const moved = "50,19.5,50.0002,19.5001";
out.back = [m.backUrl(p), m.backUrl(p, moved)];
out.view = [m.viewUrl(p, moved, ""), m.viewUrl(p, moved, "?level=phone"), m.viewUrl(p, null, ""),
            m.viewUrl(p, moved, "", ["1,2,3,4", "9,9,9,9", moved, "5,6,7,8"]), m.viewUrl(p, moved, "", [])];
out.plain = [m.viewUrl(parse(null), moved, ""), m.backUrl(parse(null))];
out.param = [m.alsoParam([]), m.alsoParam(["1,2,3,4"]), m.alsoParam(["1,2,3,4", "5,6,7,8"]), m.alsoParam(keys).split("%3B").length];
console.log(JSON.stringify(out));""")
    assert found["none"] == [] and found["empty"] == []
    assert found["two"] == ["1,2,3,4", "5.5,6,7,8"]
    assert found["bad"] == ["9,9,9,9"]
    assert found["repeats"] == ["1,2,3,4"]
    assert found["itself"] == ["1,2,3,4"]
    assert found["cap"] == 20 and found["capKeys"] == [keys[19]]
    assert found["noLine"] == [["1,2,3,4"], None]
    assert found["back"] == ["/#run=r1&line=1.5%2C2.5%2C3.5%2C4.5", "/#run=r1&line=50%2C19.5%2C50.0002%2C19.5001"]
    moved = "50%2C19.5%2C50.0002%2C19.5001"
    assert found["view"] == [
        f"/view3d#run=r1&line={moved}&also=1%2C2%2C3%2C4%3B5%2C6%2C7%2C8",
        f"/view3d?level=phone#run=r1&line={moved}&also=1%2C2%2C3%2C4%3B5%2C6%2C7%2C8",
        "/view3d#run=r1",
        f"/view3d#run=r1&line={moved}&also=1%2C2%2C3%2C4%3B9%2C9%2C9%2C9%3B5%2C6%2C7%2C8",
        f"/view3d#run=r1&line={moved}"]
    assert found["plain"] == [f"/view3d#run=r1&line={moved}", "/#run=r1&line=1.5%2C2.5%2C3.5%2C4.5"]
    assert found["param"] == ["", "&also=1%2C2%2C3%2C4", "&also=1%2C2%2C3%2C4%3B5%2C6%2C7%2C8", 20]


def _affine():
    """The affine of a patch around the clip's middle as the server writes it: a plane fitted to EPSG:2180 → WGS84 (one
    metre steps at the centre), lon = a0 + a1·x + a2·y, lat = b0 + b1·x + b2·y; and the projection itself."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    x0, y0 = 553966.0, 254608.0
    lon0, lat0 = tr.transform(x0, y0)
    lonx, latx = tr.transform(x0 + 1000, y0)
    lony, laty = tr.transform(x0, y0 + 1000)
    a1, b1, a2, b2 = (lonx - lon0) / 1000, (latx - lat0) / 1000, (lony - lon0) / 1000, (laty - lat0) / 1000
    return [lon0 - a1 * x0 - a2 * y0, a1, a2, lat0 - b1 * x0 - b2 * y0, b1, b2], tr, (x0, y0)


@node
def test_inverse_affine_and_the_lines_drawn(tmp_path):
    """others.ts: `gridOf` inverts geometry.ts `lonLat` (to a nanometre) and a real projection to centimetres over a
    patch; a line is placed only with both ends in the patch over terrain data; the lines chosen are the kept and the
    address' first in their order, then the favourites nearest the active line's middle, never the active one or a key
    twice, outside the patch or over no data dropped before the cap, at most 20; the label stands at 70 % of the
    unloaded webbing."""
    import sag
    rig = sag.Rigging()
    rigging = {"pretension": rig.pretension, "stretch": rig.stretch, "webbing_weight": rig.webbing_weight,
               "athlete_mass": rig.athlete_mass, "fall_zone": rig.fall_zone}
    affine, tr, (x0, y0) = _affine()
    pts = [(x0 + dx, y0 + dy) for dx in (-250, -3.7, 0, 111.1, 250) for dy in (-250, 0, 42.4, 250)]
    truth = [list(tr.transform(x, y)) for x, y in pts]
    found = run_entry(tmp_path, """
import { lonLat } from "./geometry";
import { gridOf, placeLine, chooseOthers, labelPoint, keyCoords, inPatch } from "./others";
import { webbing } from "./webbing";
import { canonicalKey } from "./save";
export { lonLat, gridOf, placeLine, chooseOthers, labelPoint, keyCoords, inPatch, webbing, canonicalKey };
""", f"""
const affine = {json.dumps(affine)}, pts = {json.dumps(pts)}, truth = {json.dumps(truth)};
const out = {{}};
out.round = Math.max(...pts.map(([x, y]) => {{
  const g = m.gridOf(affine, ...m.lonLat(affine, x, y));
  return Math.hypot(g[0] - x, g[1] - y);
}}));
out.real = Math.max(...pts.map(([x, y], k) => {{
  const g = m.gridOf(affine, ...truth[k]);
  return Math.hypot(g[0] - x, g[1] - y);
}}));
out.singular = [m.gridOf([0, 0, 0, 0, 0, 0], 1, 2), m.gridOf([0, 1, 1, 0, 2, 2], 1, 2)];
// a patch of 100 x 100 samples of 5 m with its corner at (1000, 5000); heights 10 + x/100 (no data in a window)
const frame = {{affine: [0, 1e-5, 0, 50, 0, 9e-6], left: 1000, top: 5000, res: 5, width: 100, height: 100}};
const heightAt = (x, y) => (x > 1300 && x < 1400 && y > 4600 && y < 4700) ? null : 10 + x / 100;
const key = (x1, y1, x2, y2) => [50 + 9e-6 * y1, 1e-5 * x1, 50 + 9e-6 * y2, 1e-5 * x2].map((v) => Number(v.toFixed(9))).join(",");
out.keyCoords = [m.keyCoords("1,2,3,4"), m.keyCoords("1,2,3"), m.keyCoords("1,,3,4"), m.keyCoords("1,2,3,x")];
out.inPatch = [m.inPatch(frame, 1000, 5000), m.inPatch(frame, 1500, 4500), m.inPatch(frame, 999, 4800), m.inPatch(frame, 1200, 5001),
               m.inPatch(frame, 1200, 4499)];
const inside = key(1100, 4900, 1200, 4800);
const placed = m.placeLine(frame, inside, heightAt);
out.placed = placed && placed.map((a) => [Math.round(a.x * 1e6) / 1e6, Math.round(a.y * 1e6) / 1e6, a.h]);
out.outside = m.placeLine(frame, key(1100, 4900, 1600, 4800), heightAt);
out.nodata = m.placeLine(frame, key(1100, 4900, 1350, 4650), heightAt);
out.bad = m.placeLine(frame, "1,2,3", heightAt);
// the candidates: the order, the exclusion, the cap, the sources
const line = (k, dx = 0) => key(1100 + dx, 4900 - 10 * k, 1150 + dx, 4900 - 10 * k);  // the k-th line, 10 m farther south
const options = (extra = {{}}) => ({{frame, heightAt, exclude: [], middle: {{x: 1125, y: 4900}}, ...extra}});
const keys = (list) => list.map((p) => p.key);
const cands = [
  {{key: line(7), source: "favourite"}}, {{key: line(1), source: "favourite"}}, {{key: line(3), source: "address"}},
  {{key: line(2), source: "kept"}}, {{key: line(5), source: "favourite"}}, {{key: line(3), source: "favourite"}},
  {{key: key(1100, 4900, 1600, 4800), source: "address"}}, {{key: key(1100, 4900, 1350, 4650), source: "address"}},
  {{key: "garbage", source: "address"}}, {{key: line(0), source: "favourite"}},
];
const full = m.chooseOthers(cands, options());
out.order = [keys(full).map((k) => [line(2), line(3), line(0), line(1), line(5), line(7)].indexOf(k)),
             full.map((p) => p.source)];
const excluded = m.chooseOthers(cands, options({{exclude: [line(3).split(",").map((v) => Number(v).toFixed(12)).join(",")]}}));
out.excluded = keys(excluded).length;
out.excludedLine = excluded.some((p) => p.key === m.canonicalKey(line(3)));
out.exclude2 = keys(m.chooseOthers(cands, options({{exclude: [line(0), line(2)]}}))).length;
out.cap = keys(m.chooseOthers(cands, options({{max: 3}}))).length;
const many = Array.from({{length: 60}}, (_, k) => ({{key: line(k % 40 + 1), source: "favourite"}}));
const chosen = m.chooseOthers(many, options());
out.many = [chosen.length, new Set(keys(chosen)).size];
// the nearest favourites come first: from the middle further and further away
const far = Array.from({{length: 30}}, (_, k) => ({{key: line(k + 1), source: "favourite"}})).reverse();
out.nearest = keys(m.chooseOthers(far, options())).map((k) => [line(1), line(2), line(3)].indexOf(k)).slice(0, 4);
// outside and without data do not use up the cap
const poor = [...Array.from({{length: 25}}, () => ({{key: key(1100, 4900, 1600, 4800), source: "address"}})),
              ...Array.from({{length: 3}}, (_, k) => ({{key: line(k + 1), source: "favourite"}}))];
out.poor = keys(m.chooseOthers(poor, options())).length;
// the label at 70 % of the unloaded webbing
const a = [{{x: 1100, y: 4900, h: 40}}, {{x: 1200, y: 4900, h: 30}}];
const w = m.webbing(a, {json.dumps(rigging)});
out.label = w ? m.labelPoint(w, a).map((v) => Math.round(v * 1000) / 1000) : null;
out.chord = m.labelPoint({{span: 100, estimate: {{unloaded: []}}}}, a).map((v) => Math.round(v * 1000) / 1000);
console.log(JSON.stringify(out));""")
    assert found["round"] < 1e-6, found
    assert found["real"] < 0.1, found  # a plane over the projection: centimetres over 500 m
    assert found["singular"] == [None, None]
    assert found["keyCoords"] == [[1, 2, 3, 4], None, None, None]
    assert found["inPatch"] == [True, True, False, False, False]
    assert found["placed"] is not None and len(found["placed"]) == 2
    assert [p[2] for p in found["placed"]] == pytest.approx([21, 22], abs=1e-3)
    assert found["outside"] is None and found["nodata"] is None and found["bad"] is None
    # order: the kept and address' lines as given (3, then 2), then the favourites from the nearest to the middle
    # (lines 0, 1, 5, 7)
    assert found["order"] == [[1, 0, 2, 3, 4, 5], ["address", "kept", "favourite", "favourite", "favourite", "favourite"]]
    assert found["excluded"] == 5 and found["excludedLine"] is False
    assert found["exclude2"] == 4 and found["cap"] == 3
    assert found["many"] == [20, 20]
    assert found["nearest"] == [0, 1, 2, -1]
    assert found["poor"] == 3
    assert found["label"] is not None and found["label"][0] == pytest.approx(1170, abs=0.5)
    assert found["chord"] == [1170, 4900, 33]


@node
def test_the_2d_result_hands_the_spot_over(tmp_path, run_data):
    """result/model.ts `alsoOf`: the other lines of the opened line's spot in the group's order, of its run, at most the
    cap; none for a line alone in its spot or outside the groups shown; with page.ts `alsoParam` the link of a line
    alone is what it always was."""
    text, data = run_data
    path = tmp_path / "data.json"
    path.write_text(text, encoding="utf-8")
    out = run_ts(tmp_path, "result/model", """
const data = JSON.parse(require("fs").readFileSync(PATH, "utf-8"));
const model = new m.ResultModel(data, {favourites: false, api: {}, profiles: false});
const key = (l) => model.lineLink(l);
const out = {spots: model.groups.length, sizes: model.groups.map((g) => g.members.length)};
const wide = model.groups.find((g) => g.members.length > 2), alone = model.groups.find((g) => g.members.length === 1);
if (wide) {
  const l = wide.members[1];
  out.wide = {size: wide.members.length, line: key(l), also: model.alsoOf(l).map(key), order: wide.members.filter((x) => x !== l).map(key),
              capped: model.alsoOf(l, 1).map(key), selectedAlso: (model.select(l), model.alsoOf(l).map(key))};
}
if (alone) out.alone = model.alsoOf(alone.members[0]).map(key);
out.unknown = model.alsoOf({...model.groups[0].rep}).length;
console.log(JSON.stringify(out));""".replace("PATH", json.dumps(str(path))))
    print(out)
    assert out["spots"] >= 1
    if "wide" in out:
        wide = out["wide"]
        assert wide["also"] == wide["order"][:20] and wide["line"] not in wide["also"]
        assert wide["capped"] == wide["order"][:1] and wide["selectedAlso"] == wide["also"]
    if "alone" in out:
        assert out["alone"] == []
    assert out["unknown"] == 0


# ---------------------------------------------------------------------------------------------------------------
# In headless Edge: the real page (main.ts with the module wired in as the coordinator wires it) over the local app,
# with the clip's run, a few of its lines handed over in the address and two saved through the app's API.

OTHERS_SCRIPT = _with_until("""
(function () {
  const root = document.getElementById("view3d");
  const out = {steps: []};
  const done = () => {
    const pre = document.createElement("pre");
    pre.id = "result";
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  };
  const onPollError = (e) => { out.pollError = String(e); };  // UNTIL_JS's until polls on after it
  /* until */
  const settled = (ms, then) => settledOn(() => root.dataset.frames, ms, then);  // ten polls over frames, none drawn
  const tool = (id) => document.querySelector('.v3-tool[data-tool="' + id + '"]');
  const labels = () => [...document.querySelectorAll(".v3-others .v3-other")];
  const keys = () => labels().map((b) => b.dataset.other).sort();
  const star = (b) => !!b.querySelector(".v3-other-star");
  const visible = (b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !b.closest(".v3-hidden"); };
  const found = decodeURIComponent(location.hash.match(/line=([^&]*)/)[1]);
  const canon = (k) => k.split(",").map(Number).join(",");
  const run = decodeURIComponent(location.hash.match(/run=([^&]*)/)[1]);
  const readout = () => (document.querySelector(".v3-readout") || {}).textContent;

  until(() => root.dataset.ready === "1", 25000, (ready) => settled(15000, (still) => {
    out.ready = ready;
    out.settled = still;
    if (!ready) { done(); return; }
    out.tools = [...document.querySelectorAll(".v3-tool")].map((b) => [b.dataset.tool, getComputedStyle(b).order,
                 b.classList.contains("v3-hidden")]);
    // 1: the lines of the address are drawn from the start
    out.n0 = root.dataset.others;
    out.keys0 = keys();
    out.stars0 = labels().map(star);
    out.sizes = labels().map((b) => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; });
    out.font = labels().length ? getComputedStyle(labels()[0]).fontSize : null;
    out.visible0 = labels().filter(visible).length;
    out.text0 = labels().length ? labels()[0].textContent : null;
    out.titles0 = labels().length ? labels()[0].getAttribute("aria-label") : null;
    out.also0 = window.__others.also();
    out.alsoPressed = (tool("others") || {getAttribute: () => null}).getAttribute("aria-pressed");
    // 2: the switch shows the favourites
    const sw = tool("others");
    out.switchShown = !!sw && !sw.classList.contains("v3-hidden");
    if (!out.switchShown) { done(); return; }
    sw.click();
    until(() => Number(root.dataset.others) > Number(out.n0), 8000, (grew) => {
      out.grew = grew;
      out.n1 = root.dataset.others;
      out.keys1 = keys();
      out.stars1 = labels().filter(star).map((b) => b.dataset.other).sort();
      out.pressed1 = sw.getAttribute("aria-pressed");
      out.noteHidden = document.querySelector(".v3-others-note").classList.contains("v3-hidden");
      // 3: a click on a label of the address makes that line the active one
      const target = labels().find((b) => !star(b));
      out.clicked = target.dataset.other;
      const lengthBefore = readout();
      target.click();
      until(() => root.dataset.edit === "checked" || root.dataset.edit === "error", 20000, (checked) => {
        out.checked = checked;
        out.edit = root.dataset.edit;
        out.readout = readout();
        out.readoutBefore = lengthBefore;
        out.reset = !document.querySelector(".v3-reset").classList.contains("v3-hidden");
        out.back = document.querySelector(".v3-back").getAttribute("href");
        out.n2 = root.dataset.others;
        out.keys2 = keys();
        out.foundAmong = keys().includes(canon(found));
        out.clickedGone = !keys().includes(canon(out.clicked));
        out.also2 = window.__others.also();
        out.saveState = [tool("save").dataset.saved, tool("save").title];
        // 4: back to the found line
        document.querySelector(".v3-reset").click();
        until(() => root.dataset.edit === "", 5000, () => {
          out.afterReset = [root.dataset.edit, keys().includes(canon(out.clicked)), keys().includes(canon(found))];
          out.back2 = document.querySelector(".v3-back").getAttribute("href");
          // 5: a favourite made active is Saved
          const fav = labels().find(star);
          out.favClicked = fav.dataset.other;
          fav.click();
          until(() => root.dataset.edit === "checked" || root.dataset.edit === "error", 20000, (ok) => {
            out.favChecked = ok;
            out.favSave = [tool("save").dataset.saved, tool("save").title, tool("save").getAttribute("aria-pressed")];
            out.favKeys = keys();
            // 6: the switch off keeps the lines of the address, the line left stays
            sw.click();
            until(() => Number(root.dataset.others) < Number(out.n1), 8000, () => {
              out.n3 = root.dataset.others;
              out.keys3 = keys();
              out.stars3 = labels().filter(star).length;
              out.noteAfter = document.querySelector(".v3-others-note").classList.contains("v3-hidden");
              done();
            });
          });
        });
      });
    });
  }));
})();
""")


def _main_with_others(tmp_path) -> str:
    """The text of main.ts with the other lines wired in as the coordinator wires them (when main.ts has them already,
    it is used as it is), its relative imports made absolute for a bundle built from a temporary folder."""
    src = (VIEWER + "/src").replace("\\", "/")
    with open(os.path.join(VIEWER, "src", "view3d", "main.ts"), encoding="utf-8") as f:
        text = f.read()
    if "createOthers" not in text:
        old = "    createSave(scene, line, page.run, current, ui.readout);"
        assert old in text, "main.ts changed: wire createOthers into this test's copy"
        text = text.replace(old, """    const save = createSave(scene, line, page.run, current, ui.readout);
    const others = createOthers(scene, line, edit!, root, {page, current, favourites: save,
                                                            notes: {parent: ui.bar, before: ui.note.nextElementSibling}});
    (window as any).__others = others;""")
        text = text.replace('import { createSave, currentOf } from "./save";',
                            'import { createSave, currentOf } from "./save";\nimport { createOthers } from "./otherlines";')
        old = "viewUrl(page, current.key(), location.search)"
        assert old in text
        text = text.replace(old, "viewUrl(page, current.key(), location.search, others.also())")
    else:  # main.ts wires them itself: only the test's handle on the module
        text, n = re.subn(r"(const others = createOthers\([^;]*;)", r"\1\n    (window as any).__others = others;", text)
        assert n == 1, "main.ts changed: give this test's copy its handle on createOthers' result"
    text = re.sub(r'(from |import )"\./', r'\1"%s/view3d/' % src, text)
    text = re.sub(r'(from |import )"\.\./', r'\1"%s/' % src, text)
    return text


def _others_page(data, tmp_path) -> str:
    """The app's /view3d template with the bundle of this test's main instead of view3d.js, in runs/otherstest/."""
    from fastapi.testclient import TestClient
    folder = data / "runs" / "otherstest"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stubs.js").write_text(CSP_STUB, encoding="utf-8")
    (folder / "test.js").write_text(OTHERS_SCRIPT, encoding="utf-8")
    entry = tmp_path / "main-others.ts"
    entry.write_text(_main_with_others(tmp_path), encoding="utf-8")
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: [%s], bundle: true, format: 'iife', "
                                  "platform: 'browser', outfile: %s, loader: {'.png': 'dataurl', '.svg': 'text', "
                                  "'.woff2': 'file'}, assetNames: '[name]-[hash]'})" % (
                                      json.dumps(str(entry)), json.dumps(str(folder / "bundle.js")))],
                   cwd=VIEWER, check=True)
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        page = client.get("/view3d").text
    script = '<script src="/app/view3d.js"></script>'
    assert script in page
    (folder / "index.html").write_text(page.replace(
        script, '<link rel="stylesheet" href="bundle.css"><script src="stubs.js"></script><script src="bundle.js">'
                '</script><script src="test.js"></script>'), encoding="utf-8")
    return "runs/otherstest/index.html"


def _favourite(port: int, run: str, line: str):
    """Mark `line` as the local user's favourite of `run` through the app's API."""
    import urllib.request
    open_ = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # the test env's proxy is a dead end
    base = f"http://127.0.0.1:{port}"
    url = f"{base}/api/runs/{quote(run, safe='')}/favourites"
    with open_(url) as response:
        token = json.loads(response.read())["token"]
    data = {"len": 50.0, "clr": 5.0, "clrN": None, "e1": 300.0, "e2": 310.0, "over": False, "water": 0.0, "filled": 0.0,
            "hmax": None, "hmean": None, "highPct": None, "angle1": None, "angle2": None, "prom1": None, "prom2": None,
            "drop1": None, "drop2": None}
    request = urllib.request.Request(url, json.dumps({"line": line, "favourite": True, "data": data, "folder": None}).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "X-Findaline-Token": token, "Origin": base})
    open_(request).read()


def _key_of(row) -> str:
    return ",".join(str(v) for v in row[:4])  # keys.ts lineCoords


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
@pytest.mark.parametrize("level", ["full", "phone"])
def test_view3d_several_lines(clip_data, tmp_path, monkeypatch, level):
    """The address hands over two lines: they are drawn from the start with their labels (at least 28 px high, in a
    readable type); the tool "Saved lines" is offered since the run has other favourites (two, saved through the API),
    off at the start, and shows them with a star; a click on a label makes that line the active one (the profile of
    its key is asked for, the readout is its own, the way back follows it, the found line is drawn among the others),
    "Back to the found line" brings the found line back; a favourite made active is "Saved"; the switch off hides
    the favourites and keeps the lines of the address; no violation of the Content-Security-Policy."""
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    rows = _lines_of(data, meta["id"])
    keys = [_key_of(r) for r in rows]
    assert len(set(keys)) == len(keys) >= 6, len(keys)
    line, address, favourites = keys[0], keys[1:3], keys[3:5]
    page = _others_page(data, tmp_path)
    window = "390,844" if level == "phone" else "1200,800"
    with _server(data, start_scheduler=True) as port:
        _clear_favourites(port, meta["id"])
        for key in favourites:
            _favourite(port, meta["id"], key)
        url = (f"http://127.0.0.1:{port}/{page}?level={level}#run={meta['id']}&line={quote(line, safe='')}"
               f"&also={quote(';'.join(address), safe='')}")
        dom = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge'}", "--no-first-run",
             f"--window-size={window}", f"--virtual-time-budget={VIRTUAL_BUDGET}", "--force-prefers-no-reduced-motion", "--dump-dom", url],
            capture_output=True, text=True, encoding="utf-8", timeout=EDGE_SECONDS).stdout
        if os.environ.get("FAL_SHOT"):  # by hand: a picture of the page as the test leaves it, for a visual review
            subprocess.run([EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'edge-shot'}", "--no-first-run",
                            f"--window-size={window}", "--virtual-time-budget=40000", "--hide-scrollbars",
                            f"--screenshot={os.environ['FAL_SHOT']}-{level}.png", url],
                           capture_output=True, text=True, timeout=300)
        _clear_favourites(port, meta["id"])
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-3000:]
    r = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    print(level, {k: v for k, v in r.items() if k != "steps"})
    canon = lambda k: ",".join(str(float(v)) if not float(v).is_integer() else str(int(float(v))) for v in k.split(","))  # noqa: E731
    assert r["ready"] and r["settled"] and "pollError" not in r, r
    # the lines of the address, from the start, labelled with their length; no star (not favourites)
    tools = {t[0]: t for t in r["tools"]}
    assert "others" in tools and tools["others"][1:] == ["4", False], r["tools"]
    assert r["n0"] == "2" and r["keys0"] == sorted(canon(k) for k in address), r
    assert r["stars0"] == [False, False] and r["alsoPressed"] == "false", r
    assert all(h >= 28 and w >= 28 for w, h in r["sizes"]) and r["visible0"] == 2, r
    assert float(r["font"].rstrip("px")) >= 11, r["font"]
    assert re.fullmatch(r"\d+ m", r["text0"]) and r["titles0"].startswith("Show this line of "), r
    assert r["also0"] == [canon(k) for k in address]
    # the switch: the favourites join, with a star; the found line is not among them (it is the active one)
    assert r["switchShown"] and r["grew"] and r["pressed1"] == "true", r
    assert r["keys1"] == sorted(canon(k) for k in address + favourites) and r["n1"] == "4", r
    assert r["stars1"] == sorted(canon(k) for k in favourites) and r["noteHidden"] is True, r
    # a click on a label of the address: that line is the active one, the found line among the others
    assert r["clicked"] in [canon(k) for k in address] and r["checked"] and r["edit"] == "checked", r
    assert r["readout"] != r["readoutBefore"] and r["reset"] is True, r
    assert r["back"].endswith("&line=" + quote(r["clicked"], safe="")), r
    assert r["foundAmong"] is True and r["clickedGone"] is True and r["n2"] == "4", r
    assert r["also2"][0] == canon(line) and r["clicked"] not in r["also2"], r
    assert r["saveState"][0] == "", r
    # back to the found line: the line left is among the others again
    assert r["afterReset"] == ["", True, False] and r["back2"].endswith("&line=" + quote(line, safe="")), r
    # a favourite made active is saved
    assert r["favChecked"] and r["favSave"] == ["1", "Saved", "true"], r
    # the switch off: the favourites go (but the one active, and the lines of the address and the ones left stay)
    assert int(r["n3"]) < int(r["n1"]) and r["stars3"] <= 1 and r["noteAfter"] is True, r
    assert _violations(dom) == []
