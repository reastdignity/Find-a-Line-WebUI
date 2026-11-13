"""The viewer (viewer/src, TypeScript) against Python: the sag estimator and the
grouping must give the same results, and viewer/dist must be built from the sources.

Needs Node and `npm install` in viewer/; skipped without them.
"""

import json
import math
import os
import random
import re
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")
sys.path.insert(0, REPO)
import helpers  # noqa: E402
import mapping  # noqa: E402
import sag  # noqa: E402
import web  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")


def run_ts(tmp_path, module: str, script: str, bundles=None):
    """Bundle viewer/src/<module>.ts for Node and run script with it as `m`; returns its JSON output.
    bundles: more modules bundled beside it ({name: module}: <tmp_path>/<name>.cjs)."""
    bundle = tmp_path / f"{module}.cjs"
    for name, source in [(module, module), *(bundles or {}).items()]:
        out = tmp_path / f"{name}.cjs"
        subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: ['src/{source}.ts'], bundle: true, "
                                      f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(out))}}})"],
                       cwd=VIEWER, check=True)
    path = tmp_path / f"{module}-test.cjs"
    path.write_text(f"const m = require({json.dumps(str(bundle))});\n{script}", encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


CASES = [(30, 0), (100, 0), (300, -40), (1000, 0), (100, 100)]


def test_sag_matches_python(tmp_path):
    rig = sag.Rigging()
    rigging = {"pretension": rig.pretension, "stretch": rig.stretch, "webbing_weight": rig.webbing_weight,
               "athlete_mass": rig.athlete_mass, "fall_zone": rig.fall_zone}
    found = run_ts(tmp_path, "sag", f"""
const out = {json.dumps(CASES)}.map(([span, dh]) => {{
  const e = m.estimate(span, dh, {json.dumps(rigging)});
  return {{L0: e.L0, sag: e.sag, unloaded: e.unloaded, athlete: e.athlete(span * 0.3).sag}};
}});
console.log(JSON.stringify(out));""")
    for (span, dh), ts in zip(CASES, found):
        L0, _ = sag.unstretched(span, dh, rig)
        _, envelope = sag.envelope(span, dh, rig)
        athlete = sag.loaded(span, dh, rig, span * 0.3, L0)["sag"]
        assert ts["L0"] == pytest.approx(L0, abs=1e-6)
        assert ts["sag"] == pytest.approx(envelope.tolist(), abs=1e-6)
        unloaded = [v for p in sag.unloaded_curve(span, dh, rig) for v in p]
        assert [v for p in ts["unloaded"] for v in p] == pytest.approx(unloaded, abs=1e-6)
        assert ts["athlete"] == pytest.approx(athlete, abs=1e-6)


@pytest.mark.parametrize("tied", [False, True], ids=["values", "ties"])
def test_grouping_matches_python(tmp_path, tied):
    """groupLines and mapping.group_lines give the same groups for lines in the same order. With ties
    (clearance and length from a few values, as an end zone with A-frames makes them, the lines in
    search._fixed_order's order: the order a run's data.js hands the browser) too: lines that rank the
    same keep their order in both."""
    random.seed(1)
    results = []
    for _ in range(2000):  # clusters of similar lines, some over trees
        x, y = random.choice([(0, 0), (30, 5), (500, 500), (-40, 70)])
        x1, y1 = x + random.uniform(-25, 25), y + random.uniform(-25, 25)
        length, clearance = round(random.uniform(80, 130), 1), round(random.uniform(0, 20), 2)
        if tied:
            length, clearance = random.choice([90.0, 100.5, 120.0]), random.choice([0.5, 1.25, 2.0])
        results.append({"a1_xy": (x1, y1), "a2_xy": (x1 + 100 + random.uniform(-25, 25), y1 + random.uniform(-25, 25)),
                        "length": length, "clearance": clearance, "over_obstacles": random.random() < 0.3,
                        "height_max": random.choice([10.0, 20.0, round(random.uniform(5, 60), 2)])})
    if tied:  # search._fixed_order: best clearance, longest, then the anchors (northing down, easting up)
        results.sort(key=lambda r: (-r["clearance"], -r["length"], -r["a1_xy"][1], r["a1_xy"][0], -r["a2_xy"][1],
                                    r["a2_xy"][0]))
    lines = [{"x1": r["a1_xy"][0], "y1": r["a1_xy"][1], "x2": r["a2_xy"][0], "y2": r["a2_xy"][1],
              "len": r["length"], "clr": r["clearance"], "over": r["over_obstacles"], "hmax": r["height_max"], "k": k}
             for k, r in enumerate(results)]
    for distance, by in ((20, "clearance"), (7, "longest"), (15, "height")):
        groups = mapping.group_lines(helpers.LineTable.from_rows(results), distance, by)
        python = [[int(rep)] + groups.of(g).tolist() for g, rep in enumerate(groups.rep)]
        ts = run_ts(tmp_path, "grouping", f"""
const lines = {json.dumps(lines)};
console.log(JSON.stringify(m.groupLines(lines, {distance}, {json.dumps(by)})
  .map((g) => [g.rep.k].concat(g.members.map((x) => x.k)))));""")
        assert ts == python


def test_list_sorting(tmp_path):
    """The list of lines: both directions, unknown values (null, NaN) last in both, ties in their order."""
    found = run_ts(tmp_path, "list", """
const rows = [[5, 1], [null, 2], [7, 3], [NaN, 4], [5, 5], [1, 6]]
  .map(([clrN, k]) => ({line: {clrN, k}, n: 1}));
const key = m.sortKey("clrN");
console.log(JSON.stringify([true, false].map((desc) => m.sortRows(rows, key, desc).map((r) => r.line.k))));""")
    assert found == [[3, 1, 5, 6, 2, 4], [6, 1, 5, 3, 2, 4]]


def test_favourites_export(tmp_path):
    """The export of favourite lines: lines.csv's column names, text quoted and kept from being read as
    a formula, unknown values empty (CSV) or null (GeoJSON), the anchors as a LineString."""
    found = run_ts(tmp_path, "favourites", """
const f = {run_id: "r1", run_name: "=cmd \\"x\\", y", run_created: "", created: "", line: "50.1,19.7,50.2,19.8",
           data: {len: 120.5, clr: 1.2, clrN: null, e1: 330, e2: 328.5, over: true, water: 0, filled: 0, hmax: 15,
                  hmean: null, highPct: 0, angle1: 12, angle2: null, prom1: 3, prom2: null, drop1: 30, drop2: null}};
const line = m.favouriteLine(f), lines = [{line, runId: f.run_id, runName: f.run_name}];
console.log(JSON.stringify({csv: m.favouritesCsv(lines), geojson: JSON.parse(m.favouritesGeoJSON(lines)),
                            data: m.favouriteData(line)}));""")
    head, row = found["csv"].split("\r\n")[:2]
    assert head.split(",")[:5] == ["run_id", "run_name", "folder", "length_m", "clearance_m"]
    assert row.startswith('"r1","\'=cmd ""x"", y","",120.5,1.2,,true,0,0,15,,0,50.1,19.7,330,12,3,30,50.2,19.8,328.5,,,')
    feature = found["geojson"]["features"][0]
    assert feature["geometry"] == {"type": "LineString", "coordinates": [[19.7, 50.1], [19.8, 50.2]]}
    assert feature["properties"]["height_mean_m"] is None and feature["properties"]["over_trees_buildings"] is True
    assert found["data"]["hmean"] is None and found["data"]["len"] == 120.5  # back as the server keeps it


def test_to_line_with_and_without_ends(tmp_path):
    """toLine reads rows of data.js and lines.js of a run without the end zone (the rows of before) and of a
    run with it (the A-frame heights its head's "ends" names before the profile), by that list or by
    END_VALUES without it; favouriteData sends the heights only for a line that has them (a favourite of
    before keeps its values) and favouriteLine reads them back, null when missing."""
    base = [50.1, 19.7, 50.2, 19.8, 1.0, 2.0, 3.0, 4.0, 120.5, 1.25, None, 330.0, 328.5, False, 0.0, 0.0, 15.0,
            9.5, 20.0, 12.0, 30.0, 3.1, None, 30.0, None]
    profile = {"d": [0, 120.5], "z": [330, 328.5], "min": [60, 1.25], "water_m": 0, "filled_m": 0}
    found = run_ts(tmp_path, "favourites", f"""
const t = require({json.dumps(str(tmp_path / "types.cjs"))});
const base = {json.dumps(base)}, profile = {json.dumps(profile)};
const pick = (l) => [l.len, l.drop2, l.lift_needed, l.lift_no_zone, l.prof && l.prof.min];
const rows = [base.concat([profile]), base.concat([null]), base, base.concat([0.75, 3.5, profile]),
              base.concat([0.75, 3.5, null]), base.concat([0, 1.5])];
const lines = rows.map((row) => t.toLine(row));
const swapped = t.toLine(base.concat([0.75, 3.5]), undefined, null, ["lift_no_zone", "lift_needed"]);
const plain = m.favouriteData(lines[0]), ends = m.favouriteData(lines[3]);
const back = m.favouriteLine({{run_id: "r", run_name: "", run_created: "", created: "", folder_id: null,
                               line: "50.1,19.7,50.2,19.8", data: ends}});
const old = m.favouriteLine({{run_id: "r", run_name: "", run_created: "", created: "", folder_id: null,
                              line: "50.1,19.7,50.2,19.8", data: plain}});
console.log(JSON.stringify({{lines: lines.map(pick), swapped: pick(swapped), plain: Object.keys(plain),
                            ends: [ends.lift_needed, ends.lift_no_zone], back: pick(back), old: pick(old),
                            names: t.END_VALUES}}));""", bundles={"types": "types"})
    assert found["lines"] == [[120.5, None, None, None, [60, 1.25]], [120.5, None, None, None, None],
                              [120.5, None, None, None, None], [120.5, None, 0.75, 3.5, [60, 1.25]],
                              [120.5, None, 0.75, 3.5, None], [120.5, None, 0, 1.5, None]]
    assert found["swapped"] == [120.5, None, 3.5, 0.75, None]
    assert "lift_needed" not in found["plain"] and found["ends"] == [0.75, 3.5]
    assert found["back"] == [120.5, None, 0.75, 3.5, None] and found["old"] == [120.5, None, None, None, None]
    assert found["names"] == list(helpers.END_VALUES)


def test_run_being_saved(tmp_path):
    """The new shells hide a listed run that its unfinished job is still saving (run.json is written before
    the map, and the job gets its run_id only when done): no map yet and made after the job was queued."""
    found = run_ts(tmp_path, "app/jobStatus", """
const job = (status, created, run_id = null) => ({status, created, run_id});
const run = (has_map, created) => ({has_map, created});
const running = [job("computing", "2026-10-29T07:50:00")];
console.log(JSON.stringify([
  m.beingSaved(run(false, "2026-10-29T07:58:00"), running),                     // being saved: hidden
  m.beingSaved(run(true, "2026-10-29T07:58:00"), running),                      // its map is written
  m.beingSaved(run(false, "2026-10-29T07:40:00"), running),                     // older than the job
  m.beingSaved(run(false, "2026-10-29T07:58:00"), [job("done", "2026-10-29T07:50:00", "r")]),
  m.beingSaved(run(false, "2026-10-29T07:58:00"), [job("failed", "2026-10-29T07:50:00")]),
]));""")
    assert found == [True, False, False, False, False]


def test_bundle_is_built_from_sources(tmp_path):
    """viewer/dist is committed: rebuild it (cd viewer; npm run build) after changing viewer/src."""
    subprocess.run(["node", "build.mjs", "--out", str(tmp_path)], cwd=VIEWER, check=True)
    for name in os.listdir(os.path.join(VIEWER, "dist")):
        with open(os.path.join(VIEWER, "dist", name), "rb") as a, open(tmp_path / name, "rb") as b:
            assert a.read() == b.read(), f"viewer/dist/{name} is out of date: run `npm run build` in viewer/"


def test_ortho_attribution_url(tmp_path):
    """data.js names the orthophoto's attribution link when its service has one (layers.ts makes the
    attribution a link to it), and leaves the field out otherwise, as in the maps of before."""
    from types import SimpleNamespace

    from shapely.geometry import Point

    class Area:
        center = (50.0, 19.1)

        @staticmethod
        def shape_wgs84():
            return Point(19.1, 50.0).buffer(0.01)

    run = {"id": "r", "name": "r", "created": "2026-11-01T10:00:00+00:00"}
    found = []
    for url in ("https://example.org/terms", None):
        service = SimpleNamespace(name="Ortho", url=None, layer="", attribution="© Test", base_url="https://x/{z}",
                                  base_max_zoom=18, **({"attribution_url": url} if url else {}))
        folder = tmp_path / ("with" if url else "without")
        folder.mkdir()
        mapping.save_map(helpers.LineTable.empty(), Area, str(folder), str(tmp_path / "runs"), run, "EPSG:2180",
                         ortho_service=service)
        text = (folder / "data.js").read_text(encoding="utf-8")
        found.append(json.loads(text.partition(" = ")[2].rstrip().rstrip(";"))["ortho"])
    assert found[0]["attribution_url"] == "https://example.org/terms" and found[0]["attribution"] == "© Test"
    assert "attribution_url" not in found[1]


@pytest.fixture(scope="module")
def clip_data(tmp_path_factory):
    """data.js of a run of the Żabi Koń clip with the surface model (clear lines and lines over trees),
    computed once, offline: (its JSON text, the value)."""
    import clip_runs  # the search once per session, this module's own copy
    tests_data = os.path.join(REPO, "tests", "data")
    data = clip_runs.data_copy(tmp_path_factory, "clip", [
        "--elevation-file", os.path.join(tests_data, "zabi_kon_nmt.tif"),
        "--surface-file", os.path.join(tests_data, "zabi_kon_nmpt.tif"), "--northing", "254608",
        "--easting", "553966", "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes",
        "--ortho", "never"])
    path = next((data / "runs").glob("*/data.js"))
    text = path.read_text(encoding="utf-8").partition(" = ")[2].rstrip().rstrip(";")
    return text, json.loads(text)


def _js_number(v) -> str:
    """A number as JavaScript's String() writes it (the anchors in keys.lineCoords)."""
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def _key(row) -> str:
    """keys.lineCoords of a data.js row."""
    return ",".join(_js_number(v) for v in row[:4])


def _python_groups(rows, distance, by, keep=lambda r: True):
    """mapping.group_lines over the data.js rows that `keep` passes, as lists of the members' keys."""
    kept = [r for r in rows if keep(r)]
    groups = mapping.group_lines(helpers.LineTable.from_rows([
        {"a1_xy": (r[4], r[5]), "a2_xy": (r[6], r[7]), "length": r[8], "clearance": r[9], "over_obstacles": r[13],
         "height_max": r[16]} for r in kept]), distance, by)
    return [[_key(kept[k]) for k in groups.of(g).tolist()] for g in range(len(groups))]


# Run with model.ts bundled as `m`: the model over a run's data (argv[2]) with a fake server
def test_folder_tree(tmp_path):
    """folders.ts: children by name, paths, depth and height, the moves jobs.Jobs.change_folder allows (not into
    itself or its own folders, not where it is, not deeper than FOLDER_DEPTH_MAX), counts with the folders inside."""
    found = run_ts(tmp_path, "folders", """
const f = (id, parent_id, name) => ({id, parent_id, name, created: ""});
const t = new m.FolderTree([f(1, null, "trips"), f(2, 1, "Tatras"), f(3, 2, "West"), f(4, null, "Alps"), f(5, 99, "lost")]);
const chain = new m.FolderTree(Array.from({length: 8}, (_, k) => f(k + 1, k ? k : null, "L" + (k + 1))));
const extra = new m.FolderTree([...chain.byId.values(), f(20, null, "x")]);
console.log(JSON.stringify({
  top: t.children(null).map((x) => x.name), path: t.path(3), depth: [t.depth(null), t.depth(3)], height: t.height(1),
  subtree: t.subtree(1).sort(), moves: [t.canMove(1, 3), t.canMove(1, 1), t.canMove(2, 1), t.canMove(2, 4), t.canMove(2, null)],
  deep: [chain.canAdd(8), chain.canAdd(7), extra.canMove(20, 8), extra.canMove(20, 7)],
  flat: t.flat().map(({folder, depth}) => folder.name + depth),
  counts: [...t.counts([{folder_id: 3}, {folder_id: 2}, {folder_id: null}, {folder_id: 42}]).entries()],
}));""")
    assert found["top"] == ["Alps", "lost", "trips"] and found["path"] == "trips / Tatras / West"
    assert found["depth"] == [0, 3] and found["height"] == 3 and found["subtree"] == [1, 2, 3]
    assert found["moves"] == [False, False, False, True, True]
    assert found["deep"] == [False, True, False, True]
    assert found["flat"] == ["Alps1", "lost1", "trips1", "Tatras2", "West3"]
    assert {k: v for k, v in found["counts"]} == {None: 4, 1: 2, 2: 2, 3: 1}


MODEL_SCRIPT = r"""
const data = JSON.parse(require("fs").readFileSync(process.argv[2], "utf-8"));
const keys = (g) => g.members.map((l) => [l.lat1, l.lon1, l.lat2, l.lon2].join(","));
const tick = () => new Promise((r) => setTimeout(r, 0));
const out = {};
(async () => {
  let favourites = [], refuse = false;
  const api = {loadFavourites: async () => favourites,
               saveFavourite: async () => { if (refuse) throw new Error("refused"); },
               profile: async () => ({d: [0, 1], z: [1, 2], min: [0, 3], water_m: 0, filled_m: 0})};
  let model = new m.ResultModel(data, {favourites: true, api});
  let notified = 0;
  model.subscribe(() => notified++);
  await tick();
  out.groups = model.groups.map(keys);
  out.rows = model.rows.map((r) => keys(r.group)[0]);
  out.rowLen = model.rows.map((r) => r.line.len);
  out.shown = model.shown;
  out.ranges = {len: model.ranges.len, group: model.ranges.group, favourites: model.ranges.favourites};
  model.setState({...model.state, by: "longest", distance: 7});
  out.longest = model.groups.map(keys);
  model.setState({...model.state, by: data.by, distance: data.distance});
  model.setList({...model.list, sort: "clr", desc: false});
  out.byClr = model.rows.map((r) => r.line.clr);
  model.setList({...model.list, sort: "len", desc: true});
  // Filters before grouping, the group size after it
  const lenMin = out.rowLen[Math.floor(out.rowLen.length / 2)];
  model.setFilters({...model.filters, lenMin});
  out.filtered = model.groups.map(keys);
  model.setFilters({...m.NO_FILTERS, groupMin: 3});
  out.groupMin = model.groups.map(keys);
  model.clearFilters();
  model.setState({...model.state, showOver: false});
  out.clearOnly = model.groups.map(keys);
  model.setState({...model.state, showOver: true, group: false});
  out.ungrouped = model.baseRows.map((r) => keys(r.group)[0]);  // the map's order
  model.setState({...model.state, group: true});
  // next / prev walk the rows
  const walk = [];
  model.next(); walk.push(model.position);
  model.next(); walk.push(model.position);
  model.prev(); walk.push(model.position);
  walk.push(model.prev(), model.position);
  out.walk = walk;
  out.first = model.selected.group === model.rows[0].group;
  // Choosing a line of a group keeps the groups; the selection follows it
  const big = model.rows.findIndex((r) => r.n >= 3);
  const group = model.rows[big].group, before = JSON.stringify(model.groups.map(keys));
  model.select(group);
  model.choose(group, group.members[2]);
  out.choose = {same: JSON.stringify(model.groups.map(keys)) === before, variant: model.variantIndex(),
                selected: model.selected.line === group.members[2], row: model.rows[big].line === group.members[2]};
  // A link to a line: found, chosen and selected in its group; hidden by filters: a note, its action clears them
  const multi = model.groups.filter((g) => g.members.length > 1)[1];
  const linked = multi.members[1], link = "#line=" + model.lineLink(linked);
  model.select(null);
  const found = model.openLinked(link);
  out.link = {found: found === linked, selected: model.selected.line === linked, variant: model.variantIndex(),
              unknown: model.openLinked("#line=1,2,3,4"), unknownNote: model.note.text};
  model.setFilters({...model.filters, lenMin: linked.len + 0.5});
  out.hidden = {found: model.openLinked(link), note: model.note.text};
  model.note.onAction();
  out.hidden.after = model.selected.line === linked && model.filters.lenMin === null;
  // Favourites: the favourite of a group is shown, "only favourites", a refused change rolled back
  favourites = [model.lineLink(model.groups.find((g) => g.members.length > 1).members[1])];
  model = new m.ResultModel(data, {favourites: true, api});  // its own lines
  await tick();
  const fav = model.lines.find((l) => model.lineLink(l) === favourites[0]);
  const g0 = model.groupOf(fav);
  out.fav = {on: model.favouritesOn, shown: model.shownOf(g0) === fav, isFav: model.isFavourite(fav),
             asFav: model.shownAsFavourite(g0)};
  model.setFilters({...model.filters, favOnly: true});
  out.favOnly = model.groups.map(keys);
  model.setFilters({...model.filters, favOnly: false});
  const other = model.groups.find((g) => !g.members.includes(fav)).rep;
  refuse = true;
  const saving = model.toggleFavourite(other);
  out.optimistic = model.isFavourite(other);
  await saving;
  out.rolledBack = {fav: model.isFavourite(other), note: model.note.text};
  refuse = false;
  await model.toggleFavourite(fav);
  out.unmarked = {fav: model.isFavourite(fav), stillShown: model.shownOf(model.groupOf(fav)) === fav};
  // A profile closed with × comes back when the spot is selected again
  model.select(model.rows[0].group);
  model.closeProfile();
  out.profileClosed = [model.profileClosed];
  model.select(model.rows[0].group);
  out.profileClosed.push(model.profileClosed);
  // Folders: where a favourite is, a new folder, a line marked into it, a favourite moved to the top level
  const changes = [], made = [];
  const folderApi = {...api,
    loadFavourites: async () => ({lines: [favourites[0]], in: {[favourites[0]]: 5},
                                  folders: [{id: 5, parent_id: null, name: "Trips", created: ""}]}),
    saveFavourite: async (run, l, on, folder) => { changes.push(["save", on, folder ?? null]); },
    moveFavourite: async (run, line, folder) => { changes.push(["move", folder]); },
    addFolder: async (name, parent) => { made.push([name, parent]); return 9; }};
  model = new m.ResultModel(data, {favourites: true, api: folderApi});
  await tick();
  const inTrips = model.lines.find((l) => model.lineLink(l) === favourites[0]);
  const plain = model.groups.find((g) => !g.members.includes(inTrips)).rep;
  out.folders = {of: model.folderOf(inTrips), path: model.tree.path(5), plain: model.folderOf(plain) === undefined};
  const nine = await model.newFolder(" Later ", 5);
  await model.saveTo(plain, nine);
  await model.saveTo(inTrips, null);
  out.folders.after = {made, changes, plain: model.folderOf(plain), trips: model.folderOf(inTrips),
                       path: model.tree.path(9)};
  // Profiles: saved ones as they are, others from the server
  const noProfile = model.lines.find((l) => !l.prof);
  out.profile = noProfile ? (await model.profile(noProfile)).min[1] : null;
  out.notified = notified;
  console.log(JSON.stringify(out));
})();
"""


def test_result_model(tmp_path, clip_data):
    """result/model.ts on a real run: its groups and rows (Python's grouping,
    clear groups first), filters before grouping and the group size after, next/prev, choosing a variant,
    links to lines, favourites (shown in their group, only favourites, a refused change rolled back)."""
    text, data = clip_data
    rows = data["lines"]
    assert any(r[13] for r in rows) and not all(r[13] for r in rows)  # clear lines and lines over trees
    data_path = tmp_path / "data.json"
    data_path.write_text(text, encoding="utf-8")
    bundle = tmp_path / "model.cjs"
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['src/result/model.ts'], bundle: true, "
                                  f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    script = tmp_path / "model-test.cjs"
    script.write_text(f"const m = require({json.dumps(str(bundle))});\n{MODEL_SCRIPT}", encoding="utf-8")
    result = subprocess.run(["node", str(script), str(data_path)], capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    distance, by = data["distance"], data["by"]
    groups = _python_groups(rows, distance, by)
    assert out["groups"] == groups
    # The list sorted by length (the default), stable: equal lengths keep the groups' order
    length = {_key(r): r[8] for r in rows}
    assert out["rows"] == [g[0] for g in sorted(groups, key=lambda g: -length[g[0]])]
    assert out["shown"] == {"spots": len(groups), "lines": len(rows)}
    assert out["ranges"] == {"len": {"min": min(length.values()), "max": max(length.values())},
                             "group": {"min": 1, "max": max(len(g) for g in groups)}, "favourites": True}
    assert out["longest"] == _python_groups(rows, 7, "longest")
    assert out["byClr"] == sorted(out["byClr"])
    len_min = out["rowLen"][len(out["rowLen"]) // 2]
    assert out["filtered"] == _python_groups(rows, distance, by, lambda r: r[8] >= len_min) != groups
    assert out["groupMin"] == [g for g in groups if len(g) >= 3] and out["groupMin"]
    assert out["clearOnly"] == _python_groups(rows, distance, by, lambda r: not r[13])
    assert out["ungrouped"] == [_key(r) for r in rows if not r[13]] + [_key(r) for r in rows if r[13]]
    assert out["walk"] == [0, 1, 0, False, 0] and out["first"]
    assert out["choose"] == {"same": True, "variant": 2, "selected": True, "row": True}
    assert out["link"] == {"found": True, "selected": True, "variant": 1, "unknown": None,
                           "unknownNote": "The line of the link is not in this run."}
    assert out["hidden"] == {"found": None, "note": "The line of the link is hidden by the filters.", "after": True}
    assert out["fav"] == {"on": True, "shown": True, "isFav": True, "asFav": True}
    assert len(out["favOnly"]) == 1 and len(out["favOnly"][0]) == 1
    assert out["optimistic"] is True
    assert out["rolledBack"] == {"fav": False, "note": "The favourite was not saved: refused"}
    assert out["unmarked"] == {"fav": False, "stillShown": True}
    assert out["profileClosed"] == [True, False]
    assert out["folders"] == {"of": 5, "path": "Trips", "plain": True,
                              "after": {"made": [[" Later ", 5]], "changes": [["save", True, 9], ["move", None]],
                                        "plain": 9, "trips": None, "path": "Trips / Later"}}
    assert out["profile"] in (None, 3)
    assert out["notified"] > 10


def _rank_reference(h, z: float) -> int:
    """The percentile rank of height z in histogram h, as Python reads it: floor(100 * the share of the
    land at or below z's bin), in integers."""
    import numpy as np
    import hypsometry as hy
    k = int(np.clip((int(np.rint(z * 100)) - hy.LOW_CM) // hy.BIN_CM, 0, hy.BINS - 1))
    return int(h.counts[:k + 1].sum()) * 100 // h.n


def test_percentile_rank_matches_python(tmp_path):
    """types.ts percentileRank on the quantiles of hypsometry.statistics gives exactly Python's rank of a
    height in the histogram: random heights in centimetres with a plateau, heights below the lowest and above
    the highest, and each quantile and 1 cm either side of it."""
    import numpy as np
    import hypsometry as hy
    rng = random.Random(7)
    cm = [rng.randint(41_234, 128_765) for _ in range(5000)] + [80_000] * 3000 + [41_230, 128_770]
    heights = np.array(cm, np.float64) / 100
    h = hy.land_histogram(heights[None, :], np.ones((1, heights.size), bool))  # a grid of one row
    q = hy.statistics(h, 1.0)["quantiles"]
    zs = [c / 100 for c in rng.sample(cm, 300)] + [0.0, 412.0, 1287.71, 1300.0, 800.0, 799.99, 800.01]
    zs += [v + d for v in q for d in (-0.01, 0.0, 0.01)]
    found = run_ts(tmp_path, "types", f"""
const q = {json.dumps(q)};
console.log(JSON.stringify({json.dumps(zs)}.map((z) => m.percentileRank(z, q))));""")
    assert found == [_rank_reference(h, z) for z in zs]
    assert found[300] == 0 and found[303] == 100 and min(found) == 0 and max(found) == 100


FILTER_SCRIPT = r"""
const data = JSON.parse(require("fs").readFileSync(process.argv[2], "utf-8"));
const terrain = data.terrain;
const upper = (l) => Math.max(l.e1, l.e2);
const out = {};
const api = {loadFavourites: async () => [], saveFavourite: async () => {},
             profile: async () => ({d: [0, 5, 10], z: [terrain.quantiles[62] + 0.05, 1, terrain.quantiles[5]],
                                    min: [5, 3], water_m: 0, filled_m: 0})};
(async () => {
  const model = new m.ResultModel(data, {favourites: false, api, profiles: true});
  out.pct = model.lines.map((l) => [l.pct1, l.pct2]);
  out.ranges = {elevHigh: model.ranges.elevHigh, pct: model.ranges.pct};
  const elevMax = [...model.lines.map(upper)].sort((a, b) => a - b)[Math.floor(model.lines.length / 2)];
  model.setFilters({...m.NO_FILTERS, elevMax});
  out.elevMax = {value: elevMax, shown: model.shown.lines, uppers: model.groups.flatMap((g) => g.members.map(upper))};
  model.setFilters({...m.NO_FILTERS, pctMin: 30});
  out.pctMin = model.shown.lines;
  model.setFilters({...m.NO_FILTERS, pctMax: 70});
  out.pctMax = model.shown.lines;
  // Another run without terrain statistics: its lines pass a percentile filter
  model.setFilters({...m.NO_FILTERS, pctMin: 30});
  model.addRun({id: "other", name: "Other", created: "2026-11-01T00:00:00+00:00", description: ""},
               {crs: data.crs, area: data.area, lines: data.lines.map((r) => r.slice(0, 25))});
  out.withOther = {shown: model.shown.lines, otherPct: model.others.get("other").lines.map((l) => [l.pct1, l.pct2])};
  // A measured line: its ends' ranks with the run's terrain, null without
  const measured = await model.measure([49, 19], [49.001, 19.001]);
  out.measured = [measured.pct1, measured.pct2];
  const p = await api.profile();
  const bare = m.measuredLine([49, 19], [49.001, 19.001], p);
  out.bare = [bare.pct1, bare.pct2];
  // A run saved without the statistics
  const old = {...data};
  delete old.terrain;
  const oldModel = new m.ResultModel(old, {favourites: false, api});
  out.old = {pct: oldModel.lines.map((l) => [l.pct1, l.pct2]), range: oldModel.ranges.pct};
  oldModel.setFilters({...m.NO_FILTERS, pctMin: 30, pctMax: 40});
  out.old.shown = oldModel.shown.lines;
  // The details of a line
  const line = {...model.lines[0], pct1: 62, pct2: null};
  out.facts = m.lineFacts(line, 10).filter(([k]) => k.startsWith("Anchor ")).map(([, v]) => v);
  out.ordinals = [1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 62, 100, 111, 0].map(m.ordinal);
  console.log(JSON.stringify(out));
})();
"""


def test_elevation_and_percentile_filters(tmp_path, clip_data):
    """filters.ts and result/model.ts: the upper anchor's bound, the anchors' percentiles in the run's area
    (types.ts percentileRank of data.js `terrain`), lines of a run without the statistics (another run shown, a
    run saved before them) passing a percentile filter, a measured line's percentiles, and lineFacts' text."""
    import numpy as np
    import hypsometry as hy
    _, data = clip_data
    rows = data["lines"]
    # The run's terrain from its anchors' heights: percentiles spread over the lines
    heights = np.array([r[11] for r in rows] + [r[12] for r in rows], np.float64)
    h = hy.land_histogram(heights[None, :], np.ones((1, heights.size), bool))  # a grid of one row
    data = {**data, "terrain": hy.statistics(h, 1.0)}
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(data), encoding="utf-8")
    entry = tmp_path / "entry.ts"
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry.write_text(f'export * from "{src}/result/model";\nexport {{ lineFacts, ordinal }} from '
                     f'"{src}/result/view/LineDetails";\n', encoding="utf-8")
    bundle = tmp_path / "filters.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], "
                                  "bundle: true, format: 'cjs', platform: 'node', "
                                  "loader: {'.png': 'dataurl', '.svg': 'text', '.woff2': 'empty'}, "  # fonts: not in Node
                                  f"outfile: {json.dumps(str(bundle))}}})"], cwd=VIEWER, check=True)
    script = tmp_path / "filters-test.cjs"
    # LineDetails' imports read the page's meta tags when loaded
    script.write_text("globalThis.document = {querySelector: () => null};\n"
                      f"const m = require({json.dumps(str(bundle))});\n{FILTER_SCRIPT}", encoding="utf-8")
    result = subprocess.run(["node", str(script), str(data_path)], capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    pct = [[_rank_reference(h, r[11]), _rank_reference(h, r[12])] for r in rows]
    assert out["pct"] == pct and len({p for pair in pct for p in pair}) > 10
    uppers = [max(r[11], r[12]) for r in rows]
    assert out["ranges"] == {"elevHigh": {"min": min(uppers), "max": max(uppers)},
                             "pct": {"min": min(map(min, pct)), "max": max(map(max, pct))}}
    elev = out["elevMax"]
    assert elev["shown"] == sum(u <= elev["value"] for u in uppers) < len(rows)
    assert sorted(elev["uppers"]) == sorted(u for u in uppers if u <= elev["value"])
    assert out["pctMin"] == sum(min(p) >= 30 for p in pct) < len(rows)
    assert out["pctMax"] == sum(max(p) <= 70 for p in pct) < len(rows)
    assert out["withOther"] == {"shown": out["pctMin"] + len(rows), "otherPct": [[None, None]] * len(rows)}
    q = data["terrain"]["quantiles"]
    assert out["measured"] == [_rank_reference(h, q[62] + 0.05), _rank_reference(h, q[5])] and out["measured"][0] >= 62
    assert out["bare"] == [None, None]
    assert out["old"] == {"pct": [[None, None]] * len(rows), "range": None, "shown": len(rows)}
    assert out["facts"][0].endswith(f" · {rows[0][11]:.1f} m (62nd percentile)")
    assert out["facts"][1].endswith(f" · {rows[0][12]:.1f} m (percentile not known)")
    assert out["ordinals"] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "62nd",
                               "100th", "111th", "0th"]


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_result_map_in_edge(tmp_path, clip_data):
    """result/ResultMap and loadRun in headless Edge, on a test page of a run served by the app (its CSP):
    the run downloaded and parsed, lines drawn, a selection with its variants, a click on a variant shows it,
    measuring (two clicks, Esc cancels), onMove, and destroy() leaves the map without a layer of it."""
    import re
    import test_web  # the app on a real server, its CSP stubs
    text, data = clip_data
    run_id = data["run"]["id"]
    folder = tmp_path / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "data.js").write_text(f"window.FINDALINE_RUN = {text};\n", encoding="utf-8")
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['test/resultmap_page.ts'], "
                                  "bundle: true, format: 'iife', target: 'es2020', loader: {'.png': 'dataurl'}, "
                                  f"outdir: {json.dumps(str(folder))}}})"], cwd=VIEWER, check=True)
    (folder / "csp_stub.js").write_text(test_web.CSP_STUB, encoding="utf-8")
    (folder / "resultmap_test.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="resultmap_page.css">'
        '<script src="csp_stub.js"></script></head><body><script src="resultmap_page.js"></script></body></html>',
        encoding="utf-8")
    dom = test_web._edge_page(tmp_path, f"runs/{run_id}/resultmap_test.html")
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-2000:]
    out = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    assert "error" not in out, out["error"]
    assert out["load"] == {"failed": True, "lines": len(data["lines"]), "cleared": True, "cached": True}
    assert out["drawn"] > 0 and out["selectedLayers"] > out["drawn"]
    assert out["clicked"] == ["variant"] and out["variantShown"] is True
    assert out["measured"] is True and out["escaped"] is True and out["moves"] == 1
    assert out["after"] == 0
    # The uncertain shore (shoreLayer.ts): one overlay, the control with the metres while the segment is in view
    assert out["shore"]["overlays"] == 1 and out["shore"]["shown"] is True
    assert "90 m: the sea" in out["shore"]["text"] and "0 m: the foot" in out["shore"]["text"]
    assert out["shore"]["help"] == [True, True, "true"]  # the explanation closed at first, opened by the "?"
    assert out["shoreAway"] is True
    assert test_web._violations(dom) == []


def test_messages_match_python(tmp_path):
    """messages.py formats the catalogue as the page's i18next does: interpolation (numbers, values not
    given stay as {{name}}, spaces in the braces) and plural forms (_zero, _one, _other), the key for an unknown one."""
    import messages
    samples = {"lines_one": "{{count}} line in {{place}}", "lines_other": "{{count}} lines in {{place}}",
               "lines_zero": "no lines", "area": "The area is {{ km2 }} km², limit {{max}} km².",
               "plain": "Spot {{n}}"}
    cases = [("lines", {"count": 1, "place": "Gozo"}), ("lines", {"count": 3, "place": "Gozo"}),
             ("lines", {"count": 0}), ("lines", {"count": 1.5, "place": "x"}), ("area", {"km2": 51.25, "max": 50.0}),
             ("plain", {}), ("plain", {"n": "<b>"}), ("unknown.key", {"n": 1}), ("ui.view3d.length", {"m": "12.5"})]
    found = run_ts(tmp_path, "i18n", f"""
const own = m.translator({json.dumps(samples)});
console.log(JSON.stringify({json.dumps(cases)}.map(([key, params]) =>
  key.startsWith("ui.") ? m.t(key, params) : own(key, params))));""")
    python = [messages.text(key, **params) if key.startswith("ui.") else messages.render(samples, key, **params)
              for key, params in cases]
    assert found == python
    assert python[:3] == ["1 line in Gozo", "3 lines in Gozo", "no lines"] and python[5] == "Spot {{n}}"
    assert python[4] == "The area is 51.25 km², limit 50 km²." and python[6] == "Spot <b>"  # Preact escapes


def test_times_in_the_viewers_zone(tmp_path):
    """time.ts shows the server's UTC times in the viewer's time zone (Warsaw here: CET, CEST in
    summer), times without an offset (stored before UTC) as the viewer's local time, and compares
    them as moments."""
    found = run_ts(tmp_path, "time", """
process.env.TZ = "Europe/Warsaw";
console.log(JSON.stringify([
  m.when("2026-10-31T06:17:52+00:00"), m.when("2026-07-01T23:30:00+00:00"), m.day("2026-07-01T23:30:00+00:00"),
  m.when("2026-10-31T06:17:52"), m.when("2026-10-31 06:17:52"), m.when(null, "never"), m.when("soon"),
  m.timeOf("2026-10-31T07:17:52+01:00") === m.timeOf("2026-10-31T06:17:52+00:00"), m.timeOf(undefined)]));""")
    assert found == ["31 Oct 2026, 07:17", "2 Jul 2026, 01:30", "2026-07-02",
                     "31 Oct 2026, 06:17", "31 Oct 2026, 06:17", "never", "soon",
                     True, 0]


def test_error_texts_match_python(tmp_path):
    """The page renders a coded error as the server writes its web text (i18n.ts errorText and
    detailMessage, the text of app/api.ts ApiError): the field's label, plural forms, the server's
    message for a code it does not know, and a plain text as it is."""
    import messages
    details = [messages.UserError.web("positive", field="radius").detail(),
               messages.UserError.web("at_most", field="max_length", max="2000 m").detail(),
               messages.Note("x", "coast_pieces_left_out", count=1, near=200, far=400, lat=1, lon=2).info(),
               {"message": "A newer server's text", "code": "no_such_code", "params": {}},
               "a plain text", None]
    found = run_ts(tmp_path, "i18n", f"""
console.log(JSON.stringify({json.dumps(details)}.map((d) => m.detailMessage(d, "fallback"))));""")
    assert found == ["Search radius must be more than 0.", "Longest line: at most 2000 m on this site.",
                     messages.Note("x", "coast_pieces_left_out", count=1, near=200, far=400, lat=1, lon=2).web_text(),
                     "A newer server's text", "a plain text", "fallback"]
    assert found[2].startswith("1 part of the coast is 200–400 m")


def test_area_searched_by_local_day(tmp_path):
    """searched.ts: the finished searches of /api/usage `area` grouped by the viewer's day (Warsaw here: a UTC
    time before midnight is the next day there), 30 days ending today across the clock change of 25 Oct,
    today's km², the numbers for people and the country's name."""
    found = run_ts(tmp_path, "app/searched", """
process.env.TZ = "Europe/Warsaw";
const now = new Date("2026-10-31T12:00:00+00:00");
const area = {total_km2: 1234.567, searches: 4, recent: [
  ["2026-10-01T10:00:00+00:00", 5],          // 31 days ago: not on the chart
  ["2026-10-25T00:30:00+00:00", 2.5],        // the day of the clock change
  ["2026-10-30T23:30:00+00:00", 0.07],       // 31 Oct in Warsaw: today
  ["2026-10-31T09:00:00+00:00", 12.25]]};
const days = m.daysOf(area, now);
console.log(JSON.stringify([days.length, days[0].key, days[29].key, new Set(days.map((d) => d.key)).size,
  days.filter((d) => d.searches).map((d) => [d.key, d.km2, d.searches]), m.todayKm2(area, now),
  [0.004, 0.07, 3.14159, 12.25, 99.96, 1234.567, 48300].map(m.km2Text), m.countText(1234), m.countryName("pl")]));""")
    assert found == [30, "2026-10-02", "2026-10-31", 30, [["2026-10-25", 2.5, 1], ["2026-10-31", 12.32, 2]], 12.32,
                     ["< 0.01", "0.07", "3.14", "12.3", "100", "1,235", "48,300"], "1,234", "Poland"]


PATCH = os.path.join(REPO, "tests", "data", "patch_zabi_kon")


def test_patch_decoder(tmp_path):
    """view3d/decode.ts against the recorded patch (tests/data/make_patch_fixture.py, docs/3d-view-contract.md
    "Body"): a whole answer (uint32 LE N, UTF-8 meta, the deflated heights) through DecompressionStream gives
    the int16 values of `values_sha256` and the samples' heights; inflated bytes decode alone; a grid of
    257 samples (step 2) is padded to 513 with no data."""
    with open(PATCH + ".json", encoding="utf-8") as f:
        fixture = json.load(f)
    found = run_ts(tmp_path, "view3d/decode", f"""
const fs = require("fs"), zlib = require("zlib"), crypto = require("crypto");
const fx = {json.dumps(fixture)}, body = fs.readFileSync({json.dumps(PATCH + ".bin")});
const meta = Buffer.from(JSON.stringify({{width: fx.width, height: fx.height, base_dm: fx.base_dm, step: 1,
                                          attribution: "Główny Urząd Geodezji"}}), "utf-8");
const head = Buffer.alloc(4); head.writeUInt32LE(meta.length);
const answer = Buffer.concat([head, meta, body]);
const sha = (v) => crypto.createHash("sha256").update(Buffer.from(v.buffer, v.byteOffset, v.byteLength)).digest("hex");
// The same with the shore's kinds after the heights (search.encode_shore): a few samples of each kind
const kinds = Buffer.alloc(fx.width * fx.height); kinds[5 * fx.width + 7] = 1; kinds[9 * fx.width + 2] = 2;
const shoreBlock = zlib.deflateSync(kinds);
const meta2 = Buffer.from(JSON.stringify({{width: fx.width, height: fx.height, base_dm: fx.base_dm, step: 1,
                                           shore_bytes: shoreBlock.length}}), "utf-8");
const head2 = Buffer.alloc(4); head2.writeUInt32LE(meta2.length);
const answer2 = Buffer.concat([head2, meta2, body, shoreBlock]);
(async () => {{
  const p = await m.decodePatch(answer.buffer.slice(answer.byteOffset, answer.byteOffset + answer.length));
  const p2 = await m.decodePatch(answer2.buffer.slice(answer2.byteOffset, answer2.byteOffset + answer2.length));
  const shore = {{plain: p.shore === undefined, sha: sha(p2.values), kinds: [p2.shore[5 * fx.width + 7], p2.shore[9 * fx.width + 2],
                 p2.shore.reduce((n, k) => n + (k ? 1 : 0), 0)]}};
  const alone = m.decodeValues(new Uint8Array(zlib.inflateSync(body)), fx.width, fx.height);
  const at = (r, c) => {{ const h = p.heights[r * p.cols + c]; return Number.isNaN(h) ? null : Math.round(h * 10) / 10; }};
  const small = m.toHeights(new Int16Array(257 * 257).fill(5), 257, 257, 100);
  console.log(JSON.stringify({{sha: sha(p.values), alone: sha(alone), attribution: p.meta.attribution, shore,
    size: [p.cols, p.rows], samples: fx.samples.map(([r, c]) => at(r, c)),
    small: [small.cols, small.rows, small.heights[0], small.heights[256 * 513 + 256], Number.isNaN(small.heights[257]),
            Number.isNaN(small.heights[257 * 513])],
    padded: [1, 513, 514, 1025, 1026].map(m.paddedSize)}}));
}})();""")
    assert found["sha"] == fixture["values_sha256"] and found["alone"] == fixture["values_sha256"]
    assert found["attribution"] == "Główny Urząd Geodezji" and found["size"] == [513, 513]
    assert found["samples"] == [h for _, _, h in fixture["samples"]]
    assert found["small"] == [513, 513, 10.5, 10.5, True, True]
    assert found["padded"] == [513, 513, 1025, 1025, 1537]
    assert found["shore"] == {"plain": True, "sha": fixture["values_sha256"], "kinds": [1, 2, 2]}


def test_shore_in_view(tmp_path):
    """shore.ts: a segment's box, the metres of each kind among the segments a view's box reaches."""
    segments = [{"kind": "surface", "px": 50, "m": 120, "ring": [[14.24, 36.01], [14.25, 36.01], [14.25, 36.02], [14.24, 36.01]]},
                {"kind": "sea", "px": 10, "m": 30, "ring": [[14.30, 36.05], [14.31, 36.05], [14.31, 36.06], [14.30, 36.05]]},
                {"kind": "sea", "px": 5, "m": 15, "ring": [[14.245, 36.015], [14.246, 36.015], [14.246, 36.016], [14.245, 36.015]]}]
    found = run_ts(tmp_path, "shore", f"""
const shore = {{rim_min: 5, segments: {json.dumps(segments)}, totals: {{}}}};
console.log(JSON.stringify({{
  box: m.segmentBox(shore.segments[0]),
  all: m.metresInView(shore, {{south: 36.0, west: 14.2, north: 36.1, east: 14.4}}),
  first: m.metresInView(shore, {{south: 36.0, west: 14.2, north: 36.012, east: 14.242}}),
  touching: m.metresInView(shore, {{south: 36.02, west: 14.25, north: 36.03, east: 14.26}}),
  none: m.metresInView(shore, {{south: 35.9, west: 14.0, north: 35.95, east: 14.1}}),
  has: [m.hasShore(shore), m.hasShore(null), m.hasShore({{rim_min: 5, segments: [], totals: {{}}}})]}}));""")
    assert found["box"] == {"south": 36.01, "west": 14.24, "north": 36.02, "east": 14.25}
    assert found["all"] == {"surface": 120, "sea": 45}
    assert found["first"] == {"surface": 120, "sea": 0}
    assert found["touching"] == {"surface": 120, "sea": 0}  # a box touching at its corner counts
    assert found["none"] == {"surface": 0, "sea": 0}
    assert found["has"] == [True, False, False]


def test_shore_hatching_and_walls(tmp_path):
    """view3d/shore.ts: the shore's samples as rectangles of a chunk's texture (within the chunk's bounds only),
    the detector of walls from the heights (a sample at the sea's level next to one WALL_DROP higher) and its
    agreement with the data's kinds."""
    found = run_ts(tmp_path, "view3d/shore", """
const width = 6, height = 4, kinds = new Uint8Array(width * height);
kinds[1 * width + 2] = 1; kinds[2 * width + 4] = 2; kinds[3 * width + 0] = 2;
// A grid of 1 m samples at the equator, lon = x·1e-5 ..., so world pixels are easy to reason about
const meta = {width, height, left: 100, top: 200, res: 1, affine: [0, 1e-5, 0, 0, 0, 1e-5]};
const plan = {z: 20, px0: 0, py0: 0, width: 4096, height: 4096};
const all = m.shoreCells(kinds, meta, plan, {x0: 100, y0: 196, x1: 106, y1: 200});
const part = m.shoreCells(kinds, meta, plan, {x0: 100, y0: 198, x1: 103, y1: 200});
const heights = new Float32Array([50, 50, 50, 50, 50, 50,
                                  50, 45, 50, 9, 50, 50,
                                  0, 0, 0, 0, 0, 50,
                                  0, 0, NaN, 0, 0, 0]);
const walls = m.detectWalls(heights, width, height, 10);
console.log(JSON.stringify({all: all.map((c) => [c.kind, c.w > 0 && c.h > 0, Math.round(c.x), Math.round(c.y)]),
  part: part.map((c) => c.kind), within: [m.shoreWithin(kinds, meta, {x0: 100, y0: 198, x1: 103, y1: 200}),
  m.shoreWithin(kinds, meta, {x0: 103, y0: 199, x1: 106, y1: 200})],
  walls: Array.from(walls), agreement: m.agreement(walls, kinds), drop: m.WALL_DROP}));""")
    assert [c[0] for c in found["all"]] == [1, 2, 2] and all(c[1] for c in found["all"])
    # Row 1 is above row 2 on the canvas (y down); sample 2 of row 1 lies left of sample 5 of row 2
    assert found["all"][0][3] < found["all"][1][3] and found["all"][0][2] < found["all"][1][2]
    assert found["part"] == [1] and found["within"] == [True, False]
    # The detector: the 0 m samples with a neighbour 10 m or more higher are walls (the 9 m one is not enough by
    # itself, but its row's 50 m samples reach diagonally); a 0 m sample among 0 m samples is not
    assert found["walls"][12:18] == [2, 2, 2, 2, 2, 0]
    assert found["walls"][18:] == [0, 0, 0, 0, 2, 2]
    assert found["agreement"] == {"detected": 7, "data": 3, "both": 1} and found["drop"] == 10

    """view3d/geometry.ts: the webbing from sag.ts between the anchors (its ends at the anchors, a level line's
    lowest point in the middle, the walker's start at the envelope's largest sag, as sag.py), the scene's axes,
    the walk's stepping, the affine and Web Mercator."""
    rig = sag.Rigging()
    rigging = {"pretension": rig.pretension, "stretch": rig.stretch, "webbing_weight": rig.webbing_weight,
               "athlete_mass": rig.athlete_mass, "fall_zone": rig.fall_zone}
    cases = [[{"x": 100.5, "y": 200.5, "h": 350.0}, {"x": 220.5, "y": 290.5, "h": 350.0}],
             [{"x": -10.5, "y": 0.5, "h": 410.25}, {"x": 290.5, "y": -399.5, "h": 380.0}]]
    found = run_ts(tmp_path, "view3d/geometry", f"""
const out = {json.dumps(cases)}.map((a) => {{
  const w = m.webbing(a, {json.dumps(rigging)}), u = w.unloaded, low = u.reduce((k, p, i) => p[2] < u[k][2] ? i : k, 0);
  const at = m.loadedAt(w, a, w.start.s);
  return {{span: w.span, dh: w.dh, first: u[0], last: u[u.length - 1], low: u[low], start: w.start, sag: at.sag,
          walker: at.walker, curveEnd: at.points[at.points.length - 1]}};
}});
const o = m.originOf({{left: 1000, top: 5000, width: 513, height: 513, res: 2, base_dm: 2896}});
console.log(JSON.stringify({{out, o, scene: m.toScene(o, 1513, 4487, 300), xy: m.sampleXY({{left: 1000, top: 5000, res: 2}}, 0, 3),
  walk: [m.walkStep(10, 0.5, 100, 4, 1, false), m.walkStep(99, 1, 100, 1, 1, false), m.walkStep(0.5, 1, 100, 1, -1, false),
         m.walkStep(10, 0.5, 100, 4, 1, true)],
  lonLat: m.lonLat([19, 1e-5, 0, 50, 0, 1e-5], 100, 200), merc: m.mercator(180, 0)}}));""")
    for a, ts in zip(cases, found["out"]):
        p, q = a
        span, dh = ((q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2) ** 0.5, p["h"] - q["h"]
        assert ts["span"] == pytest.approx(span) and ts["dh"] == pytest.approx(dh)
        assert ts["first"] == pytest.approx([p["x"], p["y"], p["h"]], abs=1e-6)
        assert ts["last"] == pytest.approx([q["x"], q["y"], q["h"]], abs=1e-6)
        assert ts["curveEnd"] == pytest.approx([q["x"], q["y"], q["h"]], abs=1e-6)
        f, envelope = sag.envelope(span, dh, rig)
        k = int(envelope.argmax())
        assert ts["start"]["sag"] == pytest.approx(envelope[k], abs=1e-6)
        at = int(round(ts["start"]["s"] / span * (len(f) - 1)))  # a level line has two equal largest sags
        assert ts["start"]["s"] == pytest.approx(f[at] * span, abs=1e-9)
        assert envelope[at] == pytest.approx(envelope[k], abs=1e-6)
        assert ts["sag"] == pytest.approx(envelope[k], abs=1e-6)
        t = ts["start"]["s"] / span
        assert ts["walker"][2] == pytest.approx(p["h"] - dh * t - envelope[k], abs=1e-6)
    level = found["out"][0]
    assert level["low"][:2] == pytest.approx([160.5, 245.5], abs=1e-6)  # the middle of the span
    assert abs(level["start"]["s"] - level["span"] / 2) <= level["span"] / 41 / 2 + 1e-9
    assert found["o"] == {"cx": 1513, "cy": 4487, "h0": 289.6}
    assert found["scene"] == pytest.approx([0, 10.4, 0]) and found["xy"] == [1007, 4999]
    assert found["walk"] == [{"s": 12, "done": False}, {"s": 100, "done": True}, {"s": 0, "done": True},
                             {"s": 10, "done": True}]
    assert found["lonLat"] == pytest.approx([19.001, 50.002])
    assert found["merc"] == pytest.approx([20037508.342789244, 0], abs=1e-6)


def test_view3d_page_request(tmp_path):
    """view3d/page.ts: the hash's run and line, the level (?level= over the pointer), the patch's step and the way
    back to the app's run page."""
    found = run_ts(tmp_path, "view3d/page", """
const line = "50.1559508,19.7562722,50.1561234,19.7571234";
const hash = "#run=" + encodeURIComponent("2026-11-01_12-00_Żabi Koń_ab12") + "&line=" + encodeURIComponent(line);
const pages = [m.parsePage("", hash, false), m.parsePage("", hash, true), m.parsePage("?level=full", hash, true),
               m.parsePage("?level=phone", hash, false), m.parsePage("", "#run=x&line=1,2,3", false),
               m.parsePage("", "#run=x&line=1,2,3,abc", false)];
console.log(JSON.stringify({pages, urls: pages.slice(0, 2).map(m.patchUrl), back: m.backUrl(pages[0])}));""")
    pages = found["pages"]
    assert pages[0] == {"run": "2026-11-01_12-00_Żabi Koń_ab12", "line": "50.1559508,19.7562722,50.1561234,19.7571234",
                        "level": "full", "also": []}
    assert [p["level"] for p in pages[:4]] == ["full", "phone", "full", "phone"]
    assert pages[4]["line"] is None and pages[5]["line"] is None
    run = "2026-11-01_12-00_%C5%BBabi%20Ko%C5%84_ab12"
    assert found["urls"] == [f"/api/patch?run={run}&line=50.1559508%2C19.7562722%2C50.1561234%2C19.7571234&step=1",
                             f"/api/patch?run={run}&line=50.1559508%2C19.7562722%2C50.1561234%2C19.7571234&step=2"]
    assert found["back"] == f"/#run={run}&line=50.1559508%2C19.7562722%2C50.1561234%2C19.7571234"


# A grid of 2 x 2 chunks (900 x 700 samples of data padded to 1025 with no data, a hole of no data inside) and a
# line from sample (200, 100) to (600, 700) across three of them: the checks of view3d/terrain.ts' meshes
TERRAIN_SCRIPT = """
const CH = 512, cols = 1025, rows = 1025, width = 900, height = 700;
const heights = new Float32Array(cols * rows).fill(NaN);
const hole = (i, j) => i >= 300 && i < 340 && j >= 600 && j < 650;
for (let i = 0; i < height; i++) for (let j = 0; j < width; j++) {
  if (!hole(i, j)) heights[i * cols + j] = 300 + 20 * Math.sin(i / 37) + 15 * Math.cos(j / 23) + ((i * 7919 + j * 104729) % 13) / 6.5;
}
const meta = {left: 1000, top: 5000, res: 1, width, height, base_dm: 2800,
  anchors: [{x: 1100.5, y: 4799.5, h: heights[200 * cols + 100]}, {x: 1700.5, y: 4399.5, h: heights[600 * cols + 700]}]};
const patch = {meta, heights, cols, rows};
const origin = {cx: 1450, cy: 4650, h0: 280};
const forced = m.forcedSamples(patch);
const out = {chunks: [], footprintMissing: 0, badTriangles: 0, skirtBad: 0, skirtOuter: 0, skirts: 0, empty: []};
const inside = (ci, cj, i, j) => i >= ci * CH && i <= ci * CH + CH && j >= cj * CH && j <= cj * CH + CH;
const counts = {};
for (const error of [5, 0.25]) {
  let total = 0;
  for (let ci = 0; ci < 2; ci++) for (let cj = 0; cj < 2; cj++) {
    const tile = m.chunkTile(patch, ci, cj, forced.all, origin.h0);
    if (!tile) { if (error === 5) out.empty.push([ci, cj]); continue; }
    const c = m.chunkMesh(patch, origin, ci, cj, tile, error, forced.line);
    total += c.positions.length / 3;
    if (error !== 5) continue;
    const verts = new Set(Array.from(c.samples.subarray(0, c.surfaceVertices)));
    for (const [i, j] of forced.line) if (inside(ci, cj, i, j) && !verts.has(i * cols + j)) out.footprintMissing++;
    const rc = (v) => [Math.floor(c.samples[v] / cols), c.samples[v] % cols];
    for (let t = 0; t < c.surfaceIndices; t += 3) {
      const [a, b, d] = [c.indices[t], c.indices[t + 1], c.indices[t + 2]].map(rc);
      const area = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
      const s = Math.sign(area(a, b, d));
      for (let i = Math.min(a[0], b[0], d[0]); i <= Math.max(a[0], b[0], d[0]); i++)
        for (let j = Math.min(a[1], b[1], d[1]); j <= Math.max(a[1], b[1], d[1]); j++) {
          const p = [i, j];
          if (s * area(a, b, p) >= 0 && s * area(b, d, p) >= 0 && s * area(d, a, p) >= 0 && Number.isNaN(heights[i * cols + j]))
            out.badTriangles++;
        }
    }
    for (let v = c.surfaceVertices; v < c.positions.length / 3; v++) {
      out.skirts++;
      const [i, j] = rc(v), top = heights[i * cols + j] - origin.h0 - m.skirtDepth(error);
      if (Math.abs(c.positions[3 * v + 1] - top) > 1e-3) out.skirtBad++;
      if (!(i === CH || j === CH)) out.skirtOuter++;  // only along the edges between chunks
    }
    out.chunks.push([ci, cj, c.hasLine, c.surfaceVertices > 0, c.positions.length / 3 > c.surfaceVertices]);
  }
  counts[error] = total;
}
out.coarser = counts[5] < counts[0.25];
const built = m.buildTerrain(patch, origin, 0.25, 20000);
out.budget = [built.vertices <= 20000, built.maxError > 0.25, built.chunks.length];
out.cells = [m.footprint({left: 0, top: 0, res: 1}, {x: 0.5, y: -0.5}, {x: 2.5, y: -2.5}),
             m.footprint({left: 0, top: 0, res: 1}, {x: 0.5, y: -0.5}, {x: 3.5, y: -0.5}),
             m.footprint({left: 0, top: 0, res: 2}, {x: 1, y: -1}, {x: 4.9, y: -2.2})];
out.anchors = meta.anchors.map((a) => forced.line.some(([i, j]) => meta.left + j + 0.5 === a.x && meta.top - i - 0.5 === a.y));
console.log(JSON.stringify(out));
"""


def test_view3d_terrain_chunks(tmp_path):
    """view3d/terrain.ts: every chunk with data meshed (one without data left out), the anchors' samples and
    every sample of the line's footprint vertices of the chunks holding them, no triangle over no data (the
    padding and a hole) even in a coarse mesh, skirts only along the edges between chunks and their depth below,
    the error raised until a budget holds, the footprint's cells (a corner crossed touches both cells)."""
    found = run_ts(tmp_path, "view3d/terrain", TERRAIN_SCRIPT)
    assert found["empty"] == []  # chunk (1, 0) holds rows 512 to 699 of data
    assert found["anchors"] == [True, True]
    assert found["footprintMissing"] == 0 and found["badTriangles"] == 0
    assert found["skirts"] > 0 and found["skirtBad"] == 0 and found["skirtOuter"] == 0
    chunks = {(ci, cj): rest for ci, cj, *rest in found["chunks"]}
    assert chunks[(0, 0)] == [True, True, True] and chunks[(0, 1)] == [True, True, True]
    assert chunks[(1, 1)] == [True, True, True] and chunks[(1, 0)][0] is False
    assert found["coarser"] and found["budget"][:2] == [True, True]
    assert found["cells"][0] == [[0, 0], [0, 1], [1, 0], [1, 1], [1, 2], [2, 1], [2, 2]]
    assert found["cells"][1] == [[0, 0], [0, 1], [0, 2], [0, 3]]
    assert found["cells"][2] == [[0, 0], [0, 1], [0, 2], [1, 2]]  # 2 m cells: v reaches 1 only at u = 2.125


def test_view3d_terrain_of_the_recorded_patch(tmp_path):
    """The recorded patch (513 x 513 of the clip at 1 m, its last 16 x 16 samples no data) as one chunk within
    the budgets of the desktop and the phone, its anchors (tests/test_patch.py's line) vertices."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_patch_fixture",
                                                  os.path.join(REPO, "tests", "data", "make_patch_fixture.py"))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    with open(PATCH + ".json", encoding="utf-8") as f:
        recorded = json.load(f)
    with open(PATCH + ".bin", "rb") as f:
        heights = fixture.decode(f.read(), 513, 513, recorded["base_dm"]).astype("<f4")
    path = tmp_path / "heights.f32"
    path.write_bytes(heights.tobytes())
    found = run_ts(tmp_path, "view3d/terrain", f"""
const buf = require("fs").readFileSync({json.dumps(str(path))});
const heights = new Float32Array(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length));
const h = (i, j) => heights[i * 513 + j];
const meta = {{left: 553665.5, top: 254908.5, res: 1, width: 513, height: 513, base_dm: {recorded["base_dm"]},
  anchors: [{{x: 553665.5 + 206.5, y: 254908.5 - 256.5, h: h(256, 206)}}, {{x: 553665.5 + 306.5, y: 254908.5 - 256.5, h: h(256, 306)}}]}};
const patch = {{meta, heights, cols: 513, rows: 513}}, origin = {{cx: 553665.5 + 256.5, cy: 254908.5 - 256.5, h0: meta.base_dm / 10}};
const out = {{}};
for (const [name, error, budget] of [["full", 0.25, 300000], ["phone", 1.5, 130000]]) {{
  const t0 = Date.now(), built = m.buildTerrain(patch, origin, error, budget), c = built.chunks[0];
  const verts = new Set(Array.from(c.samples.subarray(0, c.surfaceVertices)));
  out[name] = {{vertices: built.vertices, triangles: c.indices.length / 3, error: built.maxError, chunks: built.chunks.length,
    anchors: [256 * 513 + 206, 256 * 513 + 306].map((k) => verts.has(k)), ms: Date.now() - t0, hasLine: c.hasLine}};
}}
console.log(JSON.stringify(out));""")
    print(found)
    for level, budget in (("full", 300000), ("phone", 130000)):
        f = found[level]
        assert f["chunks"] == 1 and f["vertices"] <= budget and f["anchors"] == [True, True] and f["hasLine"]
    assert found["full"]["vertices"] > found["phone"]["vertices"]


def test_view3d_walker_on_the_webbing(tmp_path):
    """view3d/webbing.ts: the walker's feet on the loaded webbing (sag.ts) at s, below the chord by the sag, the
    curve of 61 points from anchor to anchor, the yaw along the line, the segment buffer, the readout's values."""
    import math
    rig = sag.Rigging()
    rigging = {"pretension": rig.pretension, "stretch": rig.stretch, "webbing_weight": rig.webbing_weight,
               "athlete_mass": rig.athlete_mass, "fall_zone": rig.fall_zone}
    anchors = [{"x": 100.5, "y": 200.5, "h": 350.0}, {"x": 220.5, "y": 200.5, "h": 340.0}]
    found = run_ts(tmp_path, "view3d/webbing", f"""
const a = {json.dumps(anchors)}, w = m.webbing(a, {json.dumps(rigging)});
const near = (p, pts) => Math.min(...pts.slice(1).map((q, k) => {{
  const o = pts[k], d = [q[0] - o[0], q[1] - o[1], q[2] - o[2]], v = [p[0] - o[0], p[1] - o[1], p[2] - o[2]];
  const t = Math.max(0, Math.min(1, (v[0] * d[0] + v[1] * d[1] + v[2] * d[2]) / (d[0] ** 2 + d[1] ** 2 + d[2] ** 2)));
  return Math.hypot(v[0] - t * d[0], v[1] - t * d[1], v[2] - t * d[2]);
}}));
const poses = [w.start.s, 10, 60, 119].map((s) => {{
  const p = m.walkerPose(w, a, s);
  return {{s, at: p.at, sag: p.sag, n: p.points.length, first: p.points[0], last: p.points[p.points.length - 1],
          near: near(p.at, p.points), yaw: p.yaw}};
}});
const buf = new Float32Array(60 * 6), pts = m.resample(w.unloaded);
m.writeSegments(pts, {{cx: 100, cy: 200, h0: 300}}, buf);
console.log(JSON.stringify({{poses, start: w.start, span: w.span, n: pts.length, seg: Array.from(buf.slice(0, 9)), p1: pts[1],
  readout: m.readoutOf({{d: [0, 50, 120.2], z: [1, 2, 3], min: [50, 7.25], min_nmpt: [40, -0.5], water_m: 0, filled_m: 0}}),
  clear: m.readoutOf({{d: [0, 120.2], z: [1, 3], min: [50, 7.25], min_nmpt: null, water_m: 0, filled_m: 0}}).overTrees,
  text: m.metres(7.26)}}));""")
    span = found["span"]
    assert span == pytest.approx(120)
    for pose in found["poses"]:
        t = pose["s"] / span
        assert pose["n"] == 61 and pose["first"] == pytest.approx([100.5, 200.5, 350.0], abs=1e-6)
        assert pose["last"] == pytest.approx([220.5, 200.5, 340.0], abs=1e-6)
        assert pose["at"][:2] == pytest.approx([100.5 + 120 * t, 200.5], abs=1e-6)
        assert pose["at"][2] == pytest.approx(350.0 - 10 * t - pose["sag"], abs=1e-6)
        assert pose["near"] < 0.05  # standing on the drawn curve
        assert pose["yaw"] == pytest.approx(math.pi / 2)  # its front (+Z) turned east, along the line
    start = found["poses"][0]
    _, envelope = sag.envelope(span, 10.0, rig)
    assert start["sag"] == pytest.approx(envelope.max(), abs=1e-6) and found["start"]["s"] == start["s"]
    assert found["n"] == 61
    p1 = [found["p1"][0] - 100, found["p1"][2] - 300, -(found["p1"][1] - 200)]  # in the scene's axes
    assert found["seg"] == pytest.approx([0.5, 50, -0.5, *p1, *p1], abs=1e-3)
    assert found["readout"] == {"length": 120.2, "clearance": 7.25, "overTrees": True,
                                 "verdict": "terrain_only"} and found["clear"] is False
    assert found["text"] == "7.3"


def test_view3d_interaction(tmp_path):
    """view3d/interact.ts: the walker dragged to the point of the span nearest the pointer's ray, the walk's start,
    the pin's threshold, the moved line for /api/profile and the queue of its requests (300 ms after a release,
    one in flight, a release during it waiting and only the newest sent, answers of older or cancelled keys
    dropped)."""
    found = run_ts(tmp_path, "view3d/interact", """
const near = [
  m.nearestOnSegment([30, 50, 100], [0, -0.6, -0.8], [0, 0, 0], [100, 0, 0]),  // looking down at x = 30
  m.nearestOnSegment([-50, 10, 0], [1, 0, 0], [0, 0, 0], [100, 0, 0]),       // along the line: its near end
  m.nearestOnSegment([500, 10, 0], [1, 0, 0], [0, 0, 0], [100, 0, 0]),       // past the far end
  m.nearestOnSegment([70, 10, 10], [0, 0.6, 0.8], [0, 0, 0], [100, 0, 0]),   // pointing away: the nearest point
  m.nearestOnSegment([0, 0, 0], [0, 0, 1], [5, 0, 0], [5, 0, 0]),            // no span
];
let now = 0, timers = [], calls = [], answers = [], resolvers = {};
const clock = {setTimeout(fn, ms) { const h = {at: now + ms, fn}; timers.push(h); return h; },
               clearTimeout(h) { timers = timers.filter((x) => x !== h); }};
const advance = (ms) => { now += ms; for (const h of timers.filter((x) => x.at <= now)) { timers = timers.filter((x) => x !== h); h.fn(); } };
const q = m.profileQueue((key) => { calls.push(key); return new Promise((ok, no) => { resolvers[key] = {ok, no}; }); },
                         (o) => answers.push(o.key + ("value" in o ? ":" + o.value : ":error")), 300, clock);
const tick = () => new Promise((r) => setTimeout(r, 0));
(async () => {
  const log = [];
  q.push("a"); advance(200); q.push("b"); advance(299); log.push(calls.slice());  // debounced: nothing yet
  advance(1); log.push(calls.slice());                                             // b sent
  q.push("c"); advance(300); q.push("d"); advance(300); log.push(calls.slice());    // in flight: c, d wait
  resolvers.b.ok(1); await tick(); log.push(calls.slice(), answers.slice());        // b dropped, d sent (not c)
  resolvers.d.ok(2); await tick(); log.push(answers.slice());
  q.push("e"); advance(300); q.cancel(); resolvers.e.ok(3); await tick(); log.push(answers.slice(), q.sent);
  q.push("f"); advance(300); resolvers.f.no(new Error("429")); await tick(); log.push(answers.slice());
  console.log(JSON.stringify({near, log, walk: [m.walkFrom(12, 100), m.walkFrom(100, 100), m.walkFrom(-1, 100)],
    pin: [m.pinShown(6), m.pinShown(19.9), m.pinShown(20), m.pinShown(Infinity)], below: m.PIN_BELOW_PX,
    line: m.lineParam([19.75627221, 50.15595081], [19.7, 50.2])}));
})();""")
    near = found["near"]
    assert near[0] == pytest.approx(0.3) and near[1] == 0 and near[2] == 1
    assert near[3] == pytest.approx(0.7) and near[4] == 0
    log = found["log"]
    assert log[0] == [] and log[1] == ["b"] and log[2] == ["b"]
    assert log[3] == ["b", "d"] and log[4] == []
    assert log[5] == ["d:2"]
    assert log[6] == ["d:2"] and log[7] == 3  # e sent, its answer dropped
    assert log[8] == ["d:2", "f:error"]
    assert found["walk"] == [12, 0, 0]
    assert found["pin"] == [True, True, False, False] and found["below"] == 20
    assert found["line"] == "50.1559508,19.7562722,50.2000000,19.7000000"


def test_view3d_pin_placement(tmp_path):
    """view3d/interact.ts pinPlacement (round 2, point 1): the pin's tip 14 px above the unloaded webbing at the
    walker's place along the walker's own up on the screen, or 3 px over the head when that is higher (or the
    webbing's point is missing); the leader from the head to the tip; segmentBox turns two points into an element
    of a length and a rotation; webbing.ts unloadedAt: the unloaded curve's point at the walker's x and y."""
    rig = sag.Rigging()
    rigging = {"pretension": rig.pretension, "stretch": rig.stretch, "webbing_weight": rig.webbing_weight,
               "athlete_mass": rig.athlete_mass, "fall_zone": rig.fall_zone}
    anchors = [{"x": 100.5, "y": 200.5, "h": 350.0}, {"x": 220.5, "y": 200.5, "h": 340.0}]
    found = run_ts(tmp_path, "view3d/webbing", f"""
const a = {json.dumps(anchors)}, w = m.webbing(a, {json.dumps(rigging)});
const at = (s) => m.unloadedAt(w, a, s);
console.log(JSON.stringify({{
  ends: [at(0), at(w.span), at(-5), at(w.span + 5)], mid: at(60), chord: 350 - 10 * 60 / 120,
  along: [1, 17, 40, 77, 100].map(at),
  none: m.unloadedAt({{...w, estimate: {{...w.estimate, unloaded: []}}}}, a, 10)}}));""")
    start, end = found["ends"][0], found["ends"][1]
    assert start == pytest.approx([100.5, 200.5, 350.0], abs=1e-6)
    assert end == pytest.approx([220.5, 200.5, 340.0], abs=1e-6)
    assert found["ends"][2] == start and found["ends"][3] == end  # clamped to the span
    mid = found["mid"]
    assert mid[:2] == pytest.approx([160.5, 200.5], abs=1e-6)
    assert 0 < found["chord"] - mid[2] < 10  # below the chord by the unloaded webbing's sag
    for p, s in zip(found["along"], [1, 17, 40, 77, 100]):
        assert p[0] == pytest.approx(100.5 + s, abs=1e-6) and p[1] == pytest.approx(200.5)
    assert found["none"] is None
    found = run_ts(tmp_path, "view3d/interact", """
const feet = {x: 100, y: 200}, head = {x: 100, y: 184};
const P = (webbing, f = feet, h = head) => m.pinPlacement(f, h, webbing);
console.log(JSON.stringify({
  lift: [m.PIN_LIFT_PX, m.PIN_HEAD_GAP_PX],
  over: P({x: 100, y: 190}),                  // the webbing below the head: 14 px over it
  high: P({x: 100, y: 170}),                  // the webbing above the head: still 14 px over the webbing
  low: P({x: 100, y: 200}),                   // the webbing at the feet: 14 px over it is under the head's own
  missing: P(null),
  tilted: P({x: 3, y: -2}, {x: 0, y: 0}, {x: 3, y: -4}),  // the walker's up (0.6, -0.8)
  upsideDown: P(null, {x: 10, y: 10}, {x: 10, y: 14}),
  flat: P(null, {x: 10, y: 10}, {x: 10, y: 10}),
  boxes: [m.segmentBox({x: 0, y: 10}, {x: 0, y: 0}), m.segmentBox({x: 10, y: 0}, {x: 0, y: 0}),
          m.segmentBox({x: -3, y: 4}, {x: 0, y: 0}), m.segmentBox({x: 5, y: 5}, {x: 5, y: 5})],
}));""")
    assert found["lift"] == [14, 3]
    assert found["over"]["tip"] == {"x": 100, "y": 176}  # 190 - 14: higher than 184 - 3
    assert found["over"]["leader"] == {"from": {"x": 100, "y": 184}, "to": {"x": 100, "y": 176}}
    assert found["high"]["tip"] == {"x": 100, "y": 156}
    assert found["low"]["tip"] == {"x": 100, "y": 181}  # 3 px over the head
    assert found["low"]["leader"]["from"] == {"x": 100, "y": 184}
    assert found["missing"]["tip"] == {"x": 100, "y": 181}
    tip = found["tilted"]["tip"]
    assert (tip["x"], tip["y"]) == pytest.approx((3 + 0.6 * 14, -2 - 0.8 * 14))
    assert found["upsideDown"]["tip"]["y"] == pytest.approx(11)  # up is towards the top of the screen
    assert found["flat"]["tip"] == {"x": 10, "y": 7}
    down, right, back, none = found["boxes"]
    assert down["length"] == 10 and down["angle"] == pytest.approx(0)
    assert right["length"] == 10 and right["angle"] == pytest.approx(-math.pi / 2)  # +y turned counter-clockwise onto +x
    assert back["length"] == 5 and back["angle"] == pytest.approx(math.atan2(3, 4))
    assert none == {"length": 0, "angle": 0}


def test_view3d_credits_box(tmp_path):
    """view3d/scene.ts creditsBox (round 2, point 6): the data credits behind their button at every width, open at
    the start from 768 px up and folded under it unless the user chose before ("open"/"folded" in the browser's
    storage under findaline.view3d.credits, written on each click); a storage that throws changes nothing but the
    memory; the imagery's credits stay out of the fold; the focus returns to the new button."""
    found = run_ts(tmp_path, "view3d/scene", r"""
const make = (stored, wide, broken = false) => {
  const written = [];
  const store = broken ? {getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }}
                       : {getItem: (k) => (k === m.CREDITS_KEY ? stored : null), setItem: (k, v) => written.push([k, v])};
  let focused = 0, handler = null;
  const box = {innerHTML: "", hidden: null, classList: {toggle(c, on) { box.hidden = on; }},
               addEventListener(type, fn) { if (type === "click") handler = fn; },
               querySelector(sel) { return sel === ".u-credits-toggle" ? {focus() { focused++; }} : null; }};
  const credits = m.creditsBox(box, store, () => wide);
  credits.set("data", "<b>Data</b>", 1);
  credits.set("imagery", "<i>Imagery</i>", 2);
  const state = () => ({
    open: /class="u-credits u-open"/.test(box.innerHTML), expanded: (box.innerHTML.match(/aria-expanded="(\w+)"/) || [])[1],
    imageryOutside: /<span class="v3-credit"><i>Imagery<\/i><\/span>/.test(box.innerHTML),
    button: /<button type="button" class="u-credits-toggle"/.test(box.innerHTML)});
  const click = () => handler({target: {closest: (sel) => (sel === ".u-credits-toggle" ? {} : null)}});
  const other = () => handler({target: {closest: () => null}});
  return {box, written, state, click, other, focused: () => focused};
};
const out = {};
let c = make(null, true);
out.wide = c.state(); c.click(); out.wideClicked = [c.state(), c.written.slice(), c.focused()];
c.other(); out.otherClick = [c.written.length, c.focused()];
c = make(null, false);
out.narrow = c.state(); c.click(); out.narrowClicked = [c.state(), c.written.slice()]; c.click(); out.narrowAgain = [c.state(), c.written.slice(-1)];
out.chosen = [make("folded", true).state().open, make("open", false).state().open, make("junk", true).state().open, make("junk", false).state().open];
c = make(null, true, true);
out.broken = c.state(); c.click(); out.brokenClicked = c.state();
console.log(JSON.stringify(out));""")
    assert found["wide"] == {"open": True, "expanded": "true", "imageryOutside": True, "button": True}
    assert found["wideClicked"][0]["open"] is False and found["wideClicked"][0]["expanded"] == "false"
    assert found["wideClicked"][1] == [["findaline.view3d.credits", "folded"]] and found["wideClicked"][2] == 1
    assert found["otherClick"] == [1, 1]  # a click elsewhere in the box changes nothing
    assert found["narrow"] == {"open": False, "expanded": "false", "imageryOutside": True, "button": True}
    assert found["narrowClicked"][0]["open"] is True
    assert found["narrowClicked"][1] == [["findaline.view3d.credits", "open"]]
    assert found["narrowAgain"][0]["open"] is False and found["narrowAgain"][1] == [["findaline.view3d.credits", "folded"]]
    assert found["chosen"] == [False, True, True, False]  # a stored choice wins; anything else: by the width
    assert found["broken"]["open"] is True and found["brokenClicked"]["open"] is False  # storage denied: still works


def test_view3d_imagery_counts_in_the_pill(tmp_path):
    """view3d/imagery.ts (round 2, point 2): the tiles loaded are counted in the stage's activity pill (entry
    "imagery": "Imagery 3 / 12" and the fraction), no more often than COUNT_MS and ending at all of them; the entry
    is cleared when the loading ends, when Shaded or Edges replaces it, and on dispose; a kind started over another
    keeps one entry."""
    from test_view3d_tiles import AFFINE, CX, CY, FAKE_DOM, GEOPORTAL
    ax, ay = CX - 100, CY + 50
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}],
            "ortho": {**GEOPORTAL, "cache": "../../cache/orthophoto/poland/wm256"}, "attribution": None}
    bounds = [{"x0": ax - 60, "y0": ay - 60, "x1": ax + 140, "y1": ay + 60},
              {"x0": CX + 600, "y0": CY + 600, "x1": CX + 900, "y1": CY + 900}]
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: "key"}});
  await im.set("ortho");
  const loaded = activity.splice(0);
  await im.set("esri");
  const second = activity.splice(0);
  im.set("ortho");             // not awaited ...
  await wait(0);
  const mid = activity.splice(0);
  await im.set("shaded");      // ... replaced by Shaded before it ends
  await wait(20);
  const replaced = activity.splice(0);
  await im.set("ortho");
  activity.splice(0);
  im.dispose();
  console.log(JSON.stringify({{loaded, second, mid, replaced, disposed: activity.splice(0),
                              toolbar: toolbar.children[0].children.map((c) => c.className)}}));
}})();""")
    loaded = found["loaded"]
    sets = [e for e in loaded if e[0] == "set"]
    assert sets and loaded[-1] == ["clear", "imagery"] and all(e[1] == "imagery" for e in loaded)
    total = int(re.search(r"/ (\d+)$", sets[0][2]).group(1))
    assert total > 3 and sets[0][2] == f"Imagery 0 / {total}" and sets[0][3] == 0
    assert sets[-1][2] == f"Imagery {total} / {total}" and sets[-1][3] == 1  # all of them, whatever the throttle
    fractions = [e[3] for e in sets]
    assert fractions == sorted(fractions) and len(sets) < total  # at most every COUNT_MS: fewer than the tiles
    assert [e[0] for e in found["second"]][-1] == "clear" and found["second"][0][0] == "set"
    assert found["mid"] and found["mid"][-1][0] == "set"
    assert found["replaced"] == [["clear", "imagery"]]  # the stopped loading adds nothing after the clear
    assert found["disposed"] == [["clear", "imagery"]]
    assert "u-small v3-imagery-status" not in found["toolbar"]


def test_view3d_imagery_says_what_failed(tmp_path):
    """view3d/imagery.ts: tiles that could not be loaded are named in a notice of the activity pill with "Try
    again" (their number, or that the service does not answer); a service failing REFUSED_AFTER times in a row is
    not asked for its other tiles; a chunk none of whose tiles came is shaded, not a flat picture; the notice goes
    when a loading succeeds and when Shaded is chosen."""
    from test_view3d_tiles import AFFINE, CX, CY, FAKE_DOM
    ax, ay = CX - 100, CY + 50
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}], "ortho": None,
            "attribution": None}
    bounds = [{"x0": ax - 300, "y0": ay - 300, "x1": ax + 300, "y1": ay + 300},
              {"x0": CX + 300, "y0": CY + 300, "x1": CX + 760, "y1": CY + 760}]
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
// Esri's tiles (one image a tile): all refused, one tile failing, or all answered
let mode = "refuse", bad = null;
const base = (v) => v.replace(/[?&]_fal3d=[^&]*/, "");
global.Image = class {{
  set src(v) {{
    this._src = v; if (!v) return;
    loads.push(v);
    if (mode === "one" && bad === null) bad = base(v);
    const fails = mode === "refuse" || (mode === "one" && base(v) === bad);
    setTimeout(() => (fails ? this.onerror : this.onload)?.(), 1);
  }}
  get src() {{ return this._src; }}
}};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// the pill's notice of the failed tiles (the activity's entry "imagery-failed"): what it says last, or "cleared"
const state = () => {{
  const log = activity.splice(0), mine = log.filter((e) => e[1] === "imagery-failed").at(-1) || null;
  return {{notice: mine && mine[0] === "notice" ? mine.slice(2) : mine && "cleared", loads: loads.splice(0).length,
          total: Number((log.find((e) => e[0] === "set") || [0, 0, "/ 0"])[2].split("/ ")[1]),
          last: [0, 1].map((k) => (textures.filter((x) => x[0] === k).at(-1) || [k, "none"])[1])}};
}};
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: "key"}});
  await im.set("esri");
  const out = {{refusedAfter: m.REFUSED_AFTER, refused: state()}};
  mode = "one";
  await im.set("esri");
  out.one = state();
  mode = "refuse";
  await im.set("esri");
  state();
  mode = "ok";
  scene.noticeAction.onClick();  // Try again
  await wait(300);
  out.again = state();
  mode = "one"; bad = null;
  await im.set("esri");
  await im.set("shaded");
  out.shaded = state();
  console.log(JSON.stringify(out));
}})();""")
    refused, total = found["refused"], found["refused"]["total"]
    assert total > 2 * found["refusedAfter"], found  # enough tiles for the refusal to save requests
    assert refused["notice"] == ["The imagery service does not answer: the terrain is shaded where its tiles are missing.",
                                 "Try again"]
    # the failures in a row and what was in flight beside them (six at a time), each asked twice, and the six of
    # the loading the page began by itself: fewer requests than one a tile
    assert refused["loads"] <= 2 * (found["refusedAfter"] + 2 * 6) + 6 < total, found
    assert refused["last"] == [None, None]  # shaded chunks, no flat picture of the terrain's colour
    one = found["one"]
    assert one["notice"] == [f"1 of {total} imagery tiles could not be loaded.", "Try again"]
    assert one["loads"] == total + 1 and any(t for t in one["last"])  # the one tile asked twice; its chunk keeps its picture
    again = found["again"]
    assert again["notice"] == "cleared" and again["loads"] == total and all(again["last"])
    assert found["shaded"]["notice"] == "cleared"  # Shaded shows no failed tiles of the kind before


def test_view3d_verdict(tmp_path):
    """view3d/webbing.ts: a line's verdict from its profile (fits; over the terrain only when the surface model's
    clearance is ≤ 0; does not fit when the terrain's is below 0, whatever the surface's), its colour token and
    the readout's text with the minus sign kept."""
    found = run_ts(tmp_path, "view3d/webbing", """
const p = (min, nmpt) => ({d: [0, 100], z: [1, 2], min: [50, min], min_nmpt: nmpt === null ? null : [40, nmpt], water_m: 0, filled_m: 0});
const cases = [p(3, null), p(3, 1), p(3, 0), p(3, -0.5), p(0, null), p(0, -1), p(-0.01, null), p(-2.8, 5), p(-2.8, -3)];
console.log(JSON.stringify({verdicts: cases.map((c) => m.verdictOf(c)), colours: cases.map((c) => m.VERDICT_COLOUR[m.verdictOf(c)]),
  readout: m.readoutOf(p(-2.8, -3)), text: m.metres(-2.84)}));""")
    assert found["verdicts"] == ["fits", "fits", "terrain_only", "terrain_only", "fits", "terrain_only", "no_fit",
                                 "no_fit", "no_fit"]
    assert found["colours"][:4] == ["--clear", "--clear", "--trees", "--trees"] and found["colours"][-1] == "--bad"
    assert found["readout"] == {"length": 100, "clearance": -2.8, "overTrees": False, "verdict": "no_fit"}
    assert found["text"] == "-2.8"


def test_view3d_walker_views(tmp_path):
    """view3d/look.ts (docs/3d-view-contract.md, "Wave F"): the cameras of the walker's eyes (1.6 m over the feet,
    along the gaze) and of behind the walker (5 m back from its chest along the gaze, so above it when looking
    down), the walker's yaw turning both, the pitch clamped per view; a drag's turn (eyes: grabbing the world, a
    drag over the stage's height turns by the field of view; behind: as the orbit turns, π a height); the phone's
    heading and pitch from DeviceOrientationEvent's angles (portrait and landscape, the screen's angle needed to
    hold the heading when the phone tilts, steady when it points down), the gaze's offset from it (turning right
    turns the view right, across ±π) and the dead band of the sensors' noise."""
    found = run_ts(tmp_path, "view3d/look", """
const r = (v) => v === null ? null : Array.isArray(v) ? v.map(r) : (typeof v === "object" && v !== null ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, r(x)])) : Math.round(v * 1e6) / 1e6);
const feet = [10, 2, -5];
const look = (a, angle) => { const l = m.deviceLook(...a, angle); return l && r(l); };
console.log(JSON.stringify(r({
  eyes: m.cameraPose("eyes", {feet, yaw: 0}, {yaw: 0, pitch: 0}),
  eyesTurned: m.cameraPose("eyes", {feet, yaw: Math.PI / 2}, {yaw: 0, pitch: 0}),
  eyesLeft: m.cameraPose("eyes", {feet, yaw: 0}, {yaw: Math.PI / 2, pitch: 0}),
  eyesUp: m.cameraPose("eyes", {feet, yaw: 0}, {yaw: 0, pitch: 3}),
  behind: m.cameraPose("behind", {feet, yaw: 0}, m.VIEW_SPECS.behind.start),
  behindLow: m.cameraPose("behind", {feet, yaw: 0}, {yaw: 0, pitch: 1}),
  starts: [m.VIEW_SPECS.eyes.start, m.VIEW_SPECS.behind.start], fovs: [m.VIEW_SPECS.eyes.fov, m.VIEW_SPECS.behind.fov],
  dragEyes: m.dragGaze("eyes", {yaw: 0, pitch: 0}, 100, 50, 700),
  dragEyesDown: m.dragGaze("eyes", {yaw: 0, pitch: 0}, 0, 1e6, 700),
  dragBehind: m.dragGaze("behind", {yaw: 0, pitch: -0.3}, 100, -50, 700),
  dragBehindUp: m.dragGaze("behind", {yaw: 0, pitch: -0.3}, 0, -1e6, 700),
  north: look([0, 90, 0], 0), east: look([-90, 90, 0], 0), up: look([0, 120, 0], 0),
  landscape: look([0, 0, -90], 90), landscapeDown: look([0, 0, -60], 90), landscapeAsPortrait: look([0, 0, -60], 0),
  flat: look([0, 0, 0], 0), flatTurned: look([-90, 0, 0], 0), none: m.deviceLook(null, 90, 0, 0),
  right: m.motionOffset({heading: 0, pitch: 0.1}, {heading: 0.5, pitch: 0.3}),
  across: m.motionOffset({heading: 3.0, pitch: 0}, {heading: -3.0, pitch: 0}),
  moved: [m.gazeMoved({yaw: 0, pitch: 0}, {yaw: 0.001, pitch: -0.001}), m.gazeMoved({yaw: 0, pitch: 0}, {yaw: 0.01, pitch: 0}),
          m.gazeMoved({yaw: 3.14159, pitch: 0}, {yaw: -3.14159, pitch: 0})],
})));""")
    approx = lambda v: pytest.approx(v, abs=1e-6)  # noqa: E731
    assert found["eyes"] == {"position": [10, 3.6, -5], "target": approx([10, 3.6, -4])}
    assert found["eyesTurned"]["target"] == approx([11, 3.6, -5])   # the walker's yaw turns the gaze
    assert found["eyesLeft"]["target"] == approx([11, 3.6, -5])     # facing +Z (south), a yaw of +π/2 is east: left
    assert found["eyesUp"]["target"][1] == approx(3.6 + math.sin(1.45))  # clamped, never upside down
    c, s = math.cos(0.3), math.sin(0.3)
    assert found["behind"] == {"position": approx([10, 3.2 + 5 * s, -5 - 5 * c]), "target": [10, 3.2, -5]}
    assert found["behindLow"]["position"][1] == approx(3.2 - 5 * math.sin(0.25))  # at most 0.25 rad from below
    assert found["starts"] == [{"yaw": 0, "pitch": -0.2}, {"yaw": 0, "pitch": -0.3}] and found["fovs"] == [60, 60]
    k = math.radians(60) / 700
    assert found["dragEyes"] == {"yaw": approx(100 * k), "pitch": approx(50 * k)}
    assert found["dragEyesDown"]["pitch"] == 1.45
    assert found["dragBehind"] == {"yaw": approx(-100 * math.pi / 700), "pitch": approx(-0.3 + 50 * math.pi / 700)}
    assert found["dragBehindUp"]["pitch"] == 0.25
    assert found["north"] == {"heading": 0, "pitch": 0}
    assert found["east"] == {"heading": approx(math.pi / 2), "pitch": 0}   # turned right
    assert found["up"] == {"heading": 0, "pitch": approx(math.pi / 6)}      # tilted up
    assert found["landscape"] == {"heading": approx(math.pi / 2), "pitch": 0}
    assert found["landscapeDown"] == {"heading": approx(math.pi / 2), "pitch": approx(-math.pi / 6)}
    assert abs(found["landscapeAsPortrait"]["heading"] - math.pi / 2) > 0.3  # the screen's angle is needed
    assert found["flat"] == {"heading": 0, "pitch": approx(-math.pi / 2)}  # pointing down: the screen's up
    assert found["flatTurned"]["heading"] == approx(math.pi / 2) and found["none"] is None
    assert found["right"] == {"yaw": -0.5, "pitch": approx(0.2)}
    assert found["across"]["yaw"] == approx(-(2 * math.pi - 6.0))
    assert found["moved"] == [False, True, False]


def test_view3d_walker_zoom(tmp_path):
    """view3d/look.ts (docs/3d-view-contract.md, "Wave F2"): the eyes' vertical angle from the horizontal one and
    the canvas's aspect (60° wide on a desktop and on an upright phone), the zoom's range (eyes about 110° to ×8 of
    60°, behind 1.5 to 30 m), the buttons' steps onto the grid of √2 and their clamps, the wheel's and the pinch's
    factors, the indicator's text, the camera behind at the zoom's distance and a drag's turn given by the view."""
    found = run_ts(tmp_path, "view3d/look", """
const r = (v) => v === null ? null : Array.isArray(v) ? v.map(r) : (typeof v === "object" && v !== null ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, r(x)])) : (typeof v === "number" ? Math.round(v * 1e6) / 1e6 : v));
const steps = (view, z, dir, n) => { const out = []; for (let i = 0; i < n; i++) { z = m.zoomStep(view, z, dir); out.push(z); } return out; };
console.log(JSON.stringify(r({
  vDesktop: m.verticalFov(60, 1.5), vPhone: m.verticalFov(60, 390 / 600), vSquare: m.verticalFov(90, 1), vBad: m.verticalFov(60, 0),
  camEyes: m.cameraFov("eyes", 1, 2), camEyes2: m.cameraFov("eyes", 2, 1), camBehind: m.cameraFov("behind", 3, 0.5),
  eyesRange: m.zoomRange("eyes"), behindRange: m.zoomRange("behind"),
  angles: [m.eyesAngle(1), m.eyesAngle(m.zoomRange("eyes")[0]), m.eyesAngle(8)],
  distances: [m.behindDistance(1), ...m.zoomRange("behind").map(m.behindDistance)],
  eyesIn: steps("eyes", 1, 1, 8), eyesOut: steps("eyes", 1, -1, 4), behindIn: steps("behind", 1, 1, 5),
  behindOut: steps("behind", 1, -1, 7), fromBetween: [m.zoomStep("eyes", 1.2, 1), m.zoomStep("eyes", 1.2, -1)],
  clamps: [m.zoomBy("eyes", 4, 10), m.zoomBy("eyes", 1, 0.01), m.zoomBy("behind", 1, 1.5), m.clampZoom("eyes", NaN)],
  wheel: [m.wheelFactor(-100), m.wheelFactor(100), m.wheelFactor(3, 1), m.wheelFactor(1e6), m.wheelFactor(0), m.wheelFactor(NaN)],
  pinch: [m.pinchFactor([0, 0, 100, 0], [0, 0, 200, 0]), m.pinchFactor([10, 10, 10, 70], [0, 0, 0, 30]),
          m.pinchFactor([5, 5, 5, 5], [0, 0, 50, 0])],
  labels: [m.zoomLabel("eyes", 1), m.zoomLabel("eyes", Math.SQRT2), m.zoomLabel("eyes", 2), m.zoomLabel("eyes", 0.5),
           m.zoomLabel("eyes", 8), m.zoomLabel("behind", 1), m.zoomLabel("behind", Math.SQRT2), m.zoomLabel("behind", 5 / 14.14),
           m.zoomLabel("behind", 5 / 30)],
  behindPose: m.cameraPose("behind", {feet: [0, 0, 0], yaw: 0}, {yaw: 0, pitch: 0}, 12),
  dragTurn: m.dragGaze("eyes", {yaw: 0, pitch: 0}, 70, 0, 700, 0.1),
})));""")
    approx = lambda v: pytest.approx(v, abs=1e-5)  # noqa: E731
    v = lambda h, a: math.degrees(2 * math.atan(math.tan(math.radians(h) / 2) / a))  # noqa: E731
    assert found["vDesktop"] == approx(v(60, 1.5)) and found["vPhone"] == approx(v(60, 0.65))
    assert found["vPhone"] > 60 > found["vDesktop"]  # an upright phone: taller than wide
    assert found["vSquare"] == approx(90) and found["vBad"] == approx(60)
    assert found["camEyes"] == approx(v(60, 2))
    assert found["camEyes2"] == approx(2 * math.degrees(math.atan(math.tan(math.radians(30)) / 2)))
    assert found["camBehind"] == 60  # behind the walker: a vertical angle, whatever the zoom
    t30 = math.tan(math.radians(30))
    assert found["eyesRange"] == approx([t30 / math.tan(math.radians(55)), 8])
    assert found["behindRange"] == approx([5 / 30, 5 / 1.5])
    assert found["angles"][0] == approx(60) and found["angles"][1] == approx(110)
    assert 8 < found["angles"][2] < 8.5  # ×8: about 8°
    assert found["distances"] == approx([5, 30, 1.5])
    s2 = math.sqrt(2)
    assert found["eyesIn"] == approx([s2, 2, 2 * s2, 4, 4 * s2, 8, 8, 8])  # clamped at ×8
    assert found["eyesOut"] == approx([1 / s2, 0.5, found["eyesRange"][0], found["eyesRange"][0]])
    assert found["behindIn"] == approx([s2, 2, 2 * s2, 5 / 1.5, 5 / 1.5])  # nearest 1.5 m
    assert [5 / z for z in found["behindOut"]] == pytest.approx([5 * s2, 10, 10 * s2, 20, 20 * s2, 30, 30], rel=1e-4)
    assert found["fromBetween"] == approx([s2, 1])  # onto the grid
    assert found["clamps"] == approx([8, found["eyesRange"][0], 1.5, 1])
    w = found["wheel"]
    assert w[0] == approx(math.exp(0.2)) and w[1] == approx(math.exp(-0.2)) and w[2] == approx(math.exp(-0.096))
    assert w[3] == approx(math.exp(-1)) and w[4] == 1 and w[5] == 1
    assert found["pinch"] == approx([2, 0.5, 1])
    assert found["labels"] == ["1", "1.4", "2", "0.5", "8", "5", "3.5", "14", "30"]
    assert found["behindPose"] == {"position": approx([0, 1.2, -12]), "target": [0, 1.2, 0]}
    assert found["dragTurn"] == {"yaw": approx(0.01), "pitch": 0}


def test_view3d_feature_edges(tmp_path):
    """view3d/edges.ts: the mesh's feature edges (an edge two faces share, turning by at least the angle; never
    an edge of one face, a degenerate face or the index entries past the surface's: the skirts), and the pass's
    sampling step (the pixel ratio, 1 to 2: lines one CSS pixel wide)."""
    found = run_ts(tmp_path, "view3d/edges", """
// two faces folded along the edge A-B (A = vertex 0, B = vertex 1) by phi degrees, a skirt face after them
const fold = (phi) => {
  const r = phi * Math.PI / 180;
  return [0, 0, 0,  0, 0, 1,  1, 0, 0,  -Math.cos(r), Math.sin(r), 0,  0, -5, 0];
};
const faces = [0, 1, 2,  0, 3, 1,  0, 2, 4];
// two vertical faces (walls: y is up) meeting along the vertical edge A-B, folded by phi degrees
const wall = (phi) => {
  const r = phi * Math.PI / 180;
  return [0, 0, 0,  0, 1, 0,  1, 0, 0,  -Math.cos(r), 0, Math.sin(r),  0, -5, 0];
};
console.log(JSON.stringify({
  flat: m.featureEdges(fold(0), faces, 6).length, at20: m.featureEdges(fold(20), faces, 6).length,
  at20fine: Array.from(m.featureEdges(fold(20), faces, 6, 10)), at90: Array.from(m.featureEdges(fold(90), faces, 6)),
  skirt: m.featureEdges(fold(0), faces, 9).length / 6, degenerate: m.featureEdges([0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 0, 1], [0, 1, 2, 0, 1, 3], 6).length,
  wall: m.featureEdges(wall(60), faces.slice(0, 6), 6).length,
  wallOnly: Array.from(m.featureEdges(wall(60), faces.slice(0, 6), 6, undefined, "only")),
  wallIn: m.featureEdges(wall(60), faces.slice(0, 6), 6, undefined, "in").length,
  ledgeOnly: m.featureEdges(fold(90), faces, 6, undefined, "only").length,
  angle: m.FEATURE_ANGLE, wallSlope: m.WALL_SLOPE, wallOpacity: m.WALL_OPACITY, silhouette: m.SILHOUETTE, crease: m.CREASE, strength: m.CREASE_STRENGTH,
  steps: [0.5, 1, 1.5, 2, 3, NaN].map(m.sampleStep), layer: m.TERRAIN_LAYER}));""")
    assert found["flat"] == 0 and found["at20"] == 0
    for segment in (found["at20fine"], found["at90"]):  # the edge A-B, either way round
        assert sorted([segment[:3], segment[3:]]) == [[0, 0, 0], [0, 0, 1]]
    assert found["skirt"] == 1  # past the surface: the skirt face turns by 90° from the first along A-C
    assert found["degenerate"] == 0
    # the edges between two faces of a wall apart (drawn at 35%: they crawled as the camera turned); a wall meeting
    # flat ground is no wall edge (at90 above: the first face flat, the second vertical)
    assert found["wall"] == 0 and found["wallIn"] == 6 and found["ledgeOnly"] == 0
    assert sorted([found["wallOnly"][:3], found["wallOnly"][3:]]) == [[0, 0, 0], [0, 1, 0]]
    assert found["wallSlope"] == 65 and found["wallOpacity"] == 0.35
    # the user's variant M of the prototype (docs/3d-view-contract.md, "Wave E")
    assert found["angle"] == 28 and found["silhouette"] == [0.012, 0.035] and found["crease"] == [0.1, 0.28]
    assert found["strength"] == 0.75 and found["layer"] == 1
    assert found["steps"] == [1, 1, 1.5, 2, 2, 1]


def test_view3d_imagery_edges(tmp_path):
    """view3d/imagery.ts with the "Edges" look on a fake scene that can draw it: the fourth kind after Shaded, no
    imagery credit, the scene's look switched on and off with the kind, the listeners told; without imagery the
    control offers Shaded and Edges with the note that there is none."""
    from test_view3d_tiles import AFFINE, CX, CY, FAKE_DOM, GEOPORTAL
    ax, ay = CX - 100, CY + 50
    meta = {"left": CX - 768.5, "top": CY + 768.5, "width": 1537, "height": 1537, "res": 1, "affine": AFFINE,
            "anchors": [{"x": ax, "y": ay, "h": 400}, {"x": ax + 80, "y": ay, "h": 395}],
            "ortho": {**GEOPORTAL, "cache": None}, "attribution": None}
    bounds = [{"x0": ax - 60, "y0": ay - 60, "x1": ax + 140, "y1": ay + 60},
              {"x0": CX + 600, "y0": CY + 600, "x1": CX + 900, "y1": CY + 900}]
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = {json.dumps(bounds)};
{FAKE_DOM}
const looks = [], kinds = [];
scene.edgesSupported = true;
scene.setEdges = (on) => looks.push(on);
(async () => {{
  const im = m.createImagery(scene, {{runId: "r1", esriKey: null}});
  im.onChange((k) => kinds.push(k));
  const seg = toolbar.children[0].children[0];
  await new Promise((r) => setTimeout(r, 50));
  textures.splice(0);
  const out = {{available: im.available, buttons: seg.children.map((b) => b.textContent),
               notes: toolbar.children[0].children.length, first: looks.splice(0)}};
  await im.set("edges");
  out.edges = {{textures: textures.splice(0), imagery: credits.imagery || null, looks: looks.splice(0),
               checked: seg.children.map((b) => b.attrs["aria-checked"]), current: im.current,
               select: toolbar.children[0].children[1].value}};
  await im.set("shaded");
  out.shaded = {{looks: looks.splice(0)}};
  await im.set("edges");
  await im.set("ortho");
  out.ortho = {{looks: looks.splice(0), imagery: !!credits.imagery}};
  out.kinds = kinds;
  im.dispose();
  const bare = m.createImagery({{...scene, toolbar: new El("div"), meta: {{...META, ortho: null}}}}, {{runId: "r1", esriKey: null}});
  out.bare = {{available: bare.available}};
  console.log(JSON.stringify(out));
}})();""")
    assert found["available"] == ["ortho", "shaded", "edges"]
    assert found["buttons"] == ["Orthophoto", "Shaded", "Edges"]
    assert found["notes"] == 2  # the control and its select: there is imagery, no note; the count is in the pill
    assert found["first"] == [False]  # the orthophoto first: the look off
    edges = found["edges"]
    assert edges["current"] == "edges" and edges["imagery"] is None and edges["looks"] == [True]
    assert edges["textures"] == [[0, None, None], [1, None, None]]
    assert edges["checked"] == ["false", "false", "true"] and edges["select"] == "edges"  # the select in sync
    assert found["shaded"]["looks"] == [False]
    assert found["ortho"]["looks"] == [True, False] and found["ortho"]["imagery"]
    assert found["kinds"] == ["edges", "shaded", "edges", "ortho"]
    assert found["bare"]["available"] == ["shaded", "edges"]


def test_view3d_imagery_edges_note(tmp_path):
    """Without imagery but with the "Edges" look: the control (Shaded, Edges) and the note that there is none."""
    from test_view3d_tiles import EQUATOR, FAKE_DOM
    meta = {"left": 0, "top": 513, "width": 513, "height": 513, "res": 1, "affine": EQUATOR,
            "anchors": [{"x": 100, "y": 100, "h": 1}, {"x": 200, "y": 100, "h": 1}], "ortho": None, "attribution": None}
    found = run_ts(tmp_path, "view3d/imagery", f"""
const META = {json.dumps(meta)}, BOUNDS = [{{x0: 0, y0: 0, x1: 513, y1: 513}}, {{x0: 0, y0: 0, x1: 513, y1: 513}}];
{FAKE_DOM}
scene.edgesSupported = true;
scene.setEdges = () => {{}};
const im = m.createImagery(scene, {{runId: "r", esriKey: null}});
const row = toolbar.children[0];
console.log(JSON.stringify({{available: im.available, texts: row.children.map((c) => [c.className, c.textContent || null]),
                            buttons: row.children[0].children.map((b) => b.textContent)}}));""")
    assert found["available"] == ["shaded", "edges"]
    assert found["texts"] == [["u-seg", None], ["u-input v3-select", None],
                              ["u-small v3-imagery-note", "No imagery for this result: the terrain is shaded."]]
    assert found["buttons"] == ["Shaded", "Edges"]


def test_run_script_parsed_and_body_sized(tmp_path):
    """result/load.ts: a data.js's text read by JSON.parse (null for NaN, for another script, for a file cut
    short: those are loaded as a script); download.ts: the bytes a body will read, web.SIZE_HEADER first,
    Content-Length only when nothing compressed the body."""
    found = run_ts(tmp_path, "result/load", r"""
const ok = m.parseRunScript('window.FINDALINE_RUN = {"run":{"id":"r"},"lines":[[1,2],[3,4]]};\n');
console.log(JSON.stringify({
  lines: ok && ok.lines.length,
  nan: m.parseRunScript('window.FINDALINE_RUN = {"a":NaN,"lines":[]};\n'),
  other: m.parseRunScript('(window.FINDALINE_LINES = window.FINDALINE_LINES || {})["r"] = {"lines":[]};\n'),
  cut: m.parseRunScript('window.FINDALINE_RUN = {"lines":[[1,2'),
}));""")
    assert found == {"lines": 2, "nan": None, "other": None, "cut": None}
    sizes = run_ts(tmp_path, "download", r"""
const size = (h) => m.bodySize((name) => new Headers(h).get(name));
console.log(JSON.stringify({
  header: size({"x-findaline-bytes": "1000", "content-length": "300", "content-encoding": "gzip"}),
  length: size({"content-length": "300"}),
  gzip: size({"content-length": "300", "content-encoding": "gzip"}),
  none: size({}),
  name: m.SIZE_HEADER,
}));""")
    assert sizes == {"header": 1000, "length": 300, "gzip": None, "none": None, "name": web.SIZE_HEADER}


def _quarry():
    with open(os.path.join(REPO, "tests", "data", "profile_quarry.json"), encoding="utf-8") as f:
        return json.load(f)


def test_end_zone_rule_matches_python(tmp_path):
    """endzone.ts: zoneSteps is helpers.zone_steps (the same integer arithmetic), inZone at a DDA step's distance is
    the step's test (but for a rounding on the zone's edge), the rule's limit (formula) is max_safe_elevation raised by the lift and by the fall allowance
    in the zone (helpers.zone_offsets), liftChoices, and riggingNeed from a found line's values or a profile's."""
    rng = random.Random(4)
    cases = []
    for _ in range(3000):
        steps = rng.randint(2, 3000)
        length = steps * rng.choice([1.0, 2 ** 0.5, 1 + rng.random() * 0.42]) * rng.choice([0.5, 1, 2])
        cases.append([steps, length, rng.choice([0.0, 5.0, 10.0, 20.0, rng.random() * 50, length / 4]),
                      rng.choice([0.25, 0.5, 0.0, rng.random() * 0.5])])
    quarry = _quarry()
    found = run_ts(tmp_path, "endzone", f"""
const cases = {json.dumps(cases)}, q = {json.dumps(quarry)};
const kz = cases.map(([s, l, z, c]) => m.zoneSteps(s, l, z, c));
// inZone at a step's distance and the step's own test: they differ only on the zone's edge, by a rounding
const agree = cases.every(([s, l, z, c], n) => {{
  const zone = m.zoneMetres(l, z, c);
  for (let k = 1; k < s; k++) {{
    if (m.inZone(k * l / s, l, zone) === m.stepInZone(k, s, kz[n])) continue;
    if (Math.abs(Math.min(k, s - k) * l / s - zone) > 1e-9 * l) return false;
  }}
  return true;
}});
const rule = {{model: "formula", slope: 0.15, leashFall: 6, fall: 3, zone: m.zoneMetres(q.len, 5)}};
const lim = m.limits(q.len, q.e1 + 2, q.e2 + 2, rule, null);
const line = {{lift_needed: 0.4, lift_no_zone: 4.8}};
const profile = {{d: q.d, z: q.z, min: [3, 1.6], lift: 2, zone: 5, water_m: 0, filled_m: 0}};
console.log(JSON.stringify({{kz, agree,
  limit: q.d.map((d) => lim.limitAt(d)), strict: q.d.map((d) => lim.strict(d)),
  choices: [m.liftChoices(2), m.liftChoices(1.2), m.liftChoices(0.3)],
  saved: m.riggingNeed(line, null, rule), fromProfile: m.riggingNeed({{}}, profile, rule),
  none: m.riggingNeed({{}}, {{d: [0, 1], z: [1, 1], min: [0, 1], water_m: 0, filled_m: 0}}, rule),
  short: [m.shortMetres(2), m.shortMetres(1.5), m.shortMetres(0.25)]}}));""")
    assert found["kz"] == [helpers.zone_steps(*c) for c in cases]
    assert found["agree"] is True
    t = [d / quarry["len"] for d in quarry["d"]]
    for k, d in enumerate(quarry["d"]):
        strict = float(helpers.max_safe_elevation(t[k], quarry["len"], quarry["e1"], quarry["e2"])) + 2
        assert found["strict"][k] == pytest.approx(strict, abs=1e-9)
        zone = min(d, quarry["len"] - d) < 5
        assert found["limit"][k] == pytest.approx(strict + (helpers.LEASH_FALL if zone else 0), abs=1e-9)
    assert found["choices"] == [[0, 0.5, 1, 1.5, 2], [0, 0.5, 1, 1.2], [0, 0.3]]
    assert found["saved"] == {"needed": 0.4, "noZone": 4.8}
    # the need with the zone is the lift less the rule's smallest clearance; without it the smallest strict margin
    margins = [float(helpers.max_safe_elevation(t[k], quarry["len"], quarry["z"][0], quarry["z"][-1])) - z
               for k, z in enumerate(quarry["z"]) if 0 < k < len(quarry["z"]) - 1]
    assert found["fromProfile"]["needed"] == pytest.approx(0.4)
    assert found["fromProfile"]["noZone"] == pytest.approx(max(0.4, -min(margins)))
    assert found["none"] is None and found["short"] == ["2", "1.5", "0.3"]


LABEL_CASES = r"""
const out = [];
for (const [lift, endZone] of [[2, 5], [0, 0], [2, 0], [0, 5]]) for (const W of [360, 600, 1100]) for (const H of [120, 170, 250]) {
  const e1 = q.e1 + lift, e2 = q.e2 + lift, zone = E.zoneMetres(q.len, endZone);
  const rule = {model: "formula", slope: 0.15, leashFall: 6, fall: 3, zone};
  const lim = E.limits(q.len, e1, e2, rule, null);
  let min = null, high = null;
  for (let i = 1; i < q.d.length - 1; i++) {
    const c = lim.limitAt(q.d[i]) - q.z[i], h = lim.strict(q.d[i]) + 6 - q.z[i];
    if (!min || c < min[1]) min = [q.d[i], c];
    if (!high || h > high[1]) high = [q.d[i], h];
  }
  const values = q.z.concat([e1, e2, q.e1, q.e2]);
  for (let k = 0; k <= 40; k++) values.push(lim.limitAt(q.len * k / 40));
  const frame = m.chartFrame(W, H, q.len, values, false);
  const marks = {len: q.len,
    anchors: [{d: 0, ground: q.e1, post: lift, text: "A1 " + q.e1.toFixed(1) + " m" + (lift ? " +" + lift : "")},
              {d: q.len, ground: q.e2, post: lift, text: "A2 " + q.e2.toFixed(1) + " m" + (lift ? " +" + lift : "")}],
    aframe: lift ? [["A-frame " + lift + " m", lift + " m"], ["A-frame " + lift + " m", lift + " m"]] : undefined,
    min: {d: min[0], top: lim.limitAt(min[0]), bottom: lim.limitAt(min[0]) - min[1], at: "below",
          texts: ["min. clearance " + min[1].toFixed(1) + " m"]},
    highest: {d: high[0], top: lim.strict(high[0]) + 6, bottom: lim.strict(high[0]) + 6 - high[1], at: "middle",
              texts: ["highest " + high[1].toFixed(0) + " m above terrain", "highest " + high[1].toFixed(0) + " m"]},
    zone: zone ? {metres: zone, texts: ["no-fall zone " + endZone + " m", "zone " + endZone + " m"]} : null};
  const width = (text, bold) => L.estimateWidth(text, bold);
  const specs = m.labelSpecs(frame, marks, width);
  const placed = m.chartLabels(frame, marks, width);
  const bold = new Set(["anchor1", "anchor2"]);
  const boxes = placed.map((p) => L.boxOf(p.x, p.y, width(p.text, bold.has(p.id)), p.anchor));
  let overlaps = 0;
  for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) if (L.intersects(boxes[a], boxes[b])) overlaps++;
  const bounds = m.labelBounds(frame);
  const outside = boxes.filter((b) => b.left < bounds.left || b.right > bounds.right || b.top < bounds.top || b.bottom > bounds.bottom).length;
  out.push({lift, endZone, W, H, specs: specs.map((s) => s.id), placed: placed.map((p) => p.id + ":" + p.text), overlaps, outside});
}
// the layout alone: a label with no room left is dropped, a higher priority wins the place, a short text is taken
const bounds = {left: 0, top: 0, right: 100, bottom: 30};
const spec = (id, priority, texts, x, y) => ({id, priority, texts: texts.map((t) => ({text: t, width: t.length * 6})),
                                             x, anchor: "start", y, yMin: y, yMax: y});
const crowd = L.layoutLabels([spec("low", 5, ["aaaaaaaaaa"], 0, 15), spec("high", 1, ["bbbbbbbbbb"], 10, 15),
                              spec("short", 3, ["cccccccccccccccc", "cc"], 80, 15)], bounds);
console.log(JSON.stringify({out, crowd}));
"""


def test_profile_labels_do_not_overlap(tmp_path):
    """The profile chart's labels (profilechart.ts with labels.ts' layout) on the quarry line of the mock-up, on
    A-frames of 2 m with a no-fall zone of 5 m and without either, at the 3D card's and the result's widths (360,
    600 and 1100 px) and heights: no two label boxes intersect, every box is inside the chart, the anchors' and the
    smallest clearance's labels are always there; the layout leaves out what cannot fit and keeps priorities."""
    quarry = _quarry()
    head = (f"const L = require({json.dumps(str(tmp_path / 'labels.cjs'))}), "
            f"E = require({json.dumps(str(tmp_path / 'endzone.cjs'))});\nconst q = {json.dumps(quarry)};\n")
    found = run_ts(tmp_path, "profilechart", head + LABEL_CASES, bundles={"labels": "labels", "endzone": "endzone"})
    for case in found["out"]:
        assert case["overlaps"] == 0 and case["outside"] == 0, case
        ids = [p.split(":")[0] for p in case["placed"]]
        assert {"anchor1", "anchor2", "min"} <= set(ids), case
        if case["lift"]:
            assert "aframe1" in case["specs"] and "aframe2" in case["specs"]
        if case["endZone"]:
            assert "zone1" in case["specs"]
    # at the result's desktop width everything fits
    wide = [c for c in found["out"] if c["W"] == 1100 and c["H"] >= 170]
    assert all(len(c["placed"]) == len(c["specs"]) for c in wide), wide
    assert [(q["id"], q["text"]) for q in found["crowd"]] == [("high", "bbbbbbbbbb"), ("short", "cc")]
