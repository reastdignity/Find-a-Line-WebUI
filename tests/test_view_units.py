"""Units of the result view's pure parts, run under Node (docs/line-volume/spec-view.md B.7): the reader of the
view's columns (viewer/src/types.ts hasView, result/load.ts readStore), the model built without the grouping
(result/model.ts ResultOptions.ungrouped), the geometry (result/viewgeom.ts: the level of a zoom, in view, the
squares and their breaks, a direction, the fit between a run's grid and the map) and the model of spots
(result/spots.ts: which lines pass, the shown lines, the order, the sectors, the picks, the lines not beaten, in
view and the numbers, the selection, "Lines from here", Esc).

The run is made up here (about 6 000 lines in 151 spots on a real grid, UTM 34N, with latitudes and longitudes
from pyproj), its view's columns by the rule of mapping.view_columns written out again in Python; every expected
value is counted in Python from the rule's words, not taken from the page."""
import json
import math
import os
import shutil
import subprocess

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

LIMIT, FAN_MAX, FAN_HERE, FAN_GROUP, PICK_APART, BEST_ROWS = 5000, 40, 10, 20, 100, 100
X0, Y0, SIDE = 424000.0, 5455000.0, 2000.0  # the made-up run's corner and side, m (UTM 34N, the Tatras)
CRS = "EPSG:32634"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """The view's modules bundled for Node."""
    folder = tmp_path_factory.mktemp("view-bundle")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export * from "{src}/types";\nexport * from "{src}/result/model";\n'
                     f'export * from "{src}/result/spots";\nexport * from "{src}/result/viewgeom";\n'
                     f'export {{ readStore }} from "{src}/result/load";\n', encoding="utf-8")
    out = folder / "view.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], "
                                  "bundle: true, format: 'cjs', platform: 'node', "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


class Run:
    """A made-up run: its lines' values as arrays, and the view's columns by mapping.view_columns' rule."""

    def __init__(self, seed: int = 3, side: float = SIDE, spots: int = 150, access: bool = True):
        from pyproj import Transformer
        rng = np.random.default_rng(seed)
        ends1, ends2, group = [], [], []
        # spot 0 of the making: a star of 90 lines from one point, their far ends 22 m apart on a circle
        centre = np.array([X0 + side * 0.5, Y0 + side * 0.5])
        for k in range(90):
            turn = 2 * math.pi * k / 90
            ends1.append(centre + rng.uniform(-2, 2, 2))
            ends2.append(centre + 320 * np.array([math.cos(turn), math.sin(turn)]))
            group.append(0)
        for g in range(1, spots + 1):
            at = np.array([X0, Y0]) + rng.uniform(0.05, 0.95, 2) * side
            turn, length = rng.uniform(0, math.pi), rng.uniform(30, 300)
            far = at + length * np.array([math.cos(turn), math.sin(turn)])
            for _ in range(int(rng.integers(20, 61))):
                a, b = at + rng.uniform(-6, 6, 2), far + rng.uniform(-30, 30, 2)
                if rng.random() < 0.5:
                    a, b = b, a
                ends1.append(a)
                ends2.append(b)
                group.append(g)
        n = self.n = len(group)
        a, b = np.array(ends1), np.array(ends2)
        self.x1, self.y1, self.x2, self.y2 = a[:, 0].copy(), a[:, 1].copy(), b[:, 0].copy(), b[:, 1].copy()
        to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
        self.lon1, self.lat1 = (np.round(v, 7) for v in to_wgs.transform(self.x1, self.y1))
        self.lon2, self.lat2 = (np.round(v, 7) for v in to_wgs.transform(self.x2, self.y2))
        self.len = np.hypot(self.x2 - self.x1, self.y2 - self.y1)
        self.clr = np.round(rng.uniform(0.3, 25, n), 2)
        self.hmean = np.round(rng.uniform(5, 60, n), 2)
        self.hmean[rng.random(n) < 0.03] = np.nan
        self.hmax = np.round(np.where(np.isnan(self.hmean), 30, self.hmean) + rng.uniform(0, 30, n), 2)
        self.e1, self.e2 = np.round(rng.uniform(900, 1500, n), 2), np.round(rng.uniform(900, 1500, n), 2)
        self.over = rng.random(n) < 0.2
        self.access = access
        self.a1, self.a2 = rng.integers(0, 3, n), rng.integers(0, 3, n)
        self.top = (rng.random(n) < 0.7).astype(int)
        group = np.array(group)
        # the order inside a spot: mean height, clearance, length (each highest first, NaN last), then the row
        inside = sorted(range(n), key=lambda i: (group[i], *self._down(self.hmean[i]), -self.clr[i], -self.len[i], i))
        first = {}
        for i in inside:
            first.setdefault(int(group[i]), i)
        # four sectors by the quarter of the box a spot's first line starts in, numbered by their best spot's first
        # line's mean height; the spots numbered by sector, then by their first line's mean height
        quarter = {g: int(self.x1[i] > X0 + side / 2) + 2 * int(self.y1[i] > Y0 + side / 2) for g, i in first.items()}
        score = {g: self._down(self.hmean[i]) for g, i in first.items()}
        best = {}
        for g in sorted(first, key=lambda g: (score[g], g)):
            best.setdefault(quarter[g], g)
        sector_of = {q: s for s, q in enumerate(sorted(best, key=lambda q: (score[best[q]], best[q])))}
        numbered = sorted(first, key=lambda g: (sector_of[quarter[g]], score[g], g))
        spot_of = {g: s for s, g in enumerate(numbered)}
        self.spot = np.array([spot_of[int(g)] for g in group])
        self.spots = len(numbered)
        self.by_spot = np.array(sorted(inside, key=lambda i: self.spot[i]))  # stable: the order inside stays
        self.start = np.searchsorted(self.spot[self.by_spot], np.arange(self.spots + 1))
        words = ["south-west", "south-east", "north-west", "north-east"]
        counts = np.bincount([sector_of[quarter[g]] for g in numbered], minlength=len(sector_of))
        self.sectors = [{"word": words[q], "spots": int(counts[s])} for q, s in sorted(sector_of.items(), key=lambda p: p[1])]
        self.sector_start = np.concatenate([[0], np.cumsum(counts)])
        self.sector_of_spot = np.repeat(np.arange(len(counts)), counts)
        self.box = [float(min(self.x1.min(), self.x2.min())), float(min(self.y1.min(), self.y2.min())),
                    float(max(self.x1.max(), self.x2.max())), float(max(self.y1.max(), self.y2.max()))]

    @staticmethod
    def _down(v):
        """A sort key: highest first, NaN last."""
        return (1, 0.0) if v != v else (0, -float(v))

    def lines_of(self, spot):
        return [int(i) for i in self.by_spot[self.start[spot]:self.start[spot + 1]]]

    def rows(self):
        """The lines as rows of data.js (types.ts LineRow), the access mark's two values last."""
        none = lambda v: None if v != v else float(v)  # noqa: E731
        return [[float(self.lat1[i]), float(self.lon1[i]), float(self.lat2[i]), float(self.lon2[i]), float(self.x1[i]),
                 float(self.y1[i]), float(self.x2[i]), float(self.y2[i]), float(self.len[i]), float(self.clr[i]), None,
                 float(self.e1[i]), float(self.e2[i]), bool(self.over[i]), 0, 0, float(self.hmax[i]), none(self.hmean[i]),
                 50.0, 10.0, 10.0, None, None, None, None,
                 *((int(self.a1[i]), int(self.a2[i])) if self.access else ())] for i in range(self.n)]

    def made(self):
        head = {"run": {"id": "made-up", "name": "Made up", "created": "2026-11-16T10:00:00+00:00", "description": ""},
                "center": [float(self.lat1.mean()), float(self.lon1.mean())], "area": {"type": "Polygon", "coordinates": []},
                "crs": CRS, "ortho": None, "distance": 20, "by": "clearance", "model": "sag",
                "rigging": {"pretension": 2.0, "stretch": 5.0, "webbing_weight": 60.0, "athlete_mass": 75.0, "fall_zone": 6.0},
                "slope": 0.15, "leash_fall": 6, "high_above": 20, "max_zoom": 21,
                **({"ends": ["access1", "access2"]} if self.access else {}),
                "sectors": self.sectors, "box": self.box, "lengths": [float(self.len.min()), float(self.len.max())]}
        return {"rows": self.rows(), "head": head,
                "view": {"spot": self.spot.tolist(), "top": self.top.tolist(), "by_spot": self.by_spot.tolist()}}

    # --- the rules, in Python ---

    def passing(self, top_only=True, len_min=None, clr_min=None, height_min=None, show_over=True):
        ok = np.ones(self.n, dtype=bool)
        if len_min is not None:
            ok &= self.len >= len_min
        if clr_min is not None:
            ok &= self.clr >= clr_min
        if height_min is not None:
            ok &= self.hmax >= height_min
        if not show_over:
            ok &= ~self.over
        other = ok.copy()
        if top_only:
            ok &= self.top == 1
        return ok, int((other & (self.top == 0)).sum())

    def shown(self, ok):
        return [next((i for i in self.lines_of(s) if ok[i]), -1) for s in range(self.spots)]

    def order(self, ok, sort="hmean"):
        shown = self.shown(ok)
        count = [sum(1 for i in self.lines_of(s) if ok[i]) for s in range(self.spots)]
        value = {"hmean": self.hmean, "clr": self.clr, "len": self.len, "hmax": self.hmax}.get(sort)
        key = lambda s: (self._down(value[shown[s]]) if value is not None else (0, -count[s]), s)  # noqa: E731
        return sorted((s for s in range(self.spots) if shown[s] >= 0), key=key)

    def not_beaten(self, ok, spot):
        """The passing lines of a spot that no earlier passing line of it matches in length and clearance."""
        mine = [i for i in self.lines_of(spot) if ok[i]]
        return [i for k, i in enumerate(mine)
                if not any(self.len[j] >= self.len[i] and self.clr[j] >= self.clr[i] for j in mine[:k])]

    def crossing(self, box):
        """Does each line cross the box (x0, y0, x1, y1): more than a point of it lies inside."""
        from shapely.geometry import LineString, box as rectangle
        area = rectangle(*box)
        return np.array([LineString([(self.x1[i], self.y1[i]), (self.x2[i], self.y2[i])]).intersection(area).length > 0
                         for i in range(self.n)])

    def picks(self, ok):
        shown, rows = self.shown(ok), [int(i) for i in np.flatnonzero(ok)]
        count = [sum(1 for i in self.lines_of(s) if ok[i]) for s in range(self.spots)]

        def highest(values, among):
            best = -1
            for i in among:
                if values[i] == values[i] and (best < 0 or values[i] > values[best]):
                    best = i
            return best
        most = max((s for s in range(self.spots) if count[s]), key=lambda s: (count[s], -s), default=-1)
        found = [("mean", highest(self.hmean, rows)), ("long3", highest(self.len, [i for i in rows if self.clr[i] >= 3])),
                 ("high", highest(self.hmax, rows)), ("most", shown[most] if most >= 0 else -1)]
        middle = lambda i: ((self.x1[i] + self.x2[i]) / 2, (self.y1[i] + self.y2[i]) / 2)  # noqa: E731
        out = []
        for kind, row in found:
            if row < 0:
                continue
            if all(self.spot[o] != self.spot[row] and math.dist(middle(o), middle(row)) >= PICK_APART for _, o in out):
                out.append((kind, row))
        if self.access:
            edge = highest(self.hmean, [i for i in rows if self.a1[i] == 2 and self.a2[i] == 2])
            if edge >= 0 and all(o != edge for _, o in out):
                out.append(("edge", edge))
        return [{"kind": kind, "row": row, "spot": int(self.spot[row]), "n": k + 1} for k, (kind, row) in enumerate(out)]

    def fan(self, ok, x, y, marks):
        """"Lines from here" at (x, y): marks {row: number} of the lines that carry a number on the map."""
        d1, d2 = np.hypot(self.x1 - x, self.y1 - y), np.hypot(self.x2 - x, self.y2 - y)
        found = [int(i) for i in np.flatnonzero(ok & (np.minimum(d1, d2) <= FAN_HERE))]
        near = {i: 1 if d1[i] <= d2[i] else 2 for i in found}
        found.sort(key=lambda i: (self._down(self.hmean[i]), i))
        far = lambda i: (self.x2[i], self.y2[i]) if near[i] == 1 else (self.x1[i], self.y1[i])  # noqa: E731
        groups = []

        def group(i, numbered):
            if not numbered:
                for g in groups:
                    if math.dist(far(g["row"]), far(i)) <= FAN_GROUP:
                        g["rows"].append(i)
                        return
            groups.append({"row": i, "rows": [i], "near": near[i], "numbered": numbered})
        seeded = sorted((i for i in found if i in marks),
                        key=lambda i: (math.floor(min(d1[i], d2[i]) + 0.5), marks[i]))
        for i in seeded:
            group(i, True)
        for i in found:
            if i not in seeded:
                group(i, False)
        for g in groups:
            i = g["row"]
            g["dh"] = float(self.e2[i] - self.e1[i]) if g["near"] == 1 else float(self.e1[i] - self.e2[i])
        return {"lines": len(found), "farEnds": len(groups), "capped": len(groups) > FAN_MAX, "rows": groups[:FAN_MAX]}


@pytest.fixture(scope="module")
def run():
    made = Run()
    assert made.n > LIMIT + 200 and made.spots == 151 and len(made.sectors) == 4
    return made


@pytest.fixture(scope="module")
def made_path(run, tmp_path_factory):
    path = tmp_path_factory.mktemp("view-run") / "made.json"
    path.write_text(json.dumps(run.made()), encoding="utf-8")
    return path


PRELUDE = r"""
const fs = require("fs");
const m = require(process.argv[2]);
const made = JSON.parse(fs.readFileSync(process.argv[3], "utf-8"));
const api = {loadFavourites: async () => [], saveFavourite: async () => {}, profile: async () => { throw new Error("no"); }};
const dataOf = (of = made) => ({...of.head, columns: m.lineColumns(of.rows, null, of.head.ends),
                               view: {spot: Uint32Array.from(of.view.spot), top: Uint8Array.from(of.view.top),
                                      bySpot: Uint32Array.from(of.view.by_spot)}});
function build(options = {}, of = made) {
  const data = dataOf(of), model = new m.ResultModel(data, {ungrouped: true, favourites: false, profiles: false, api, ...options});
  return {data, model, view: m.createSpotView(model)};
}
const list = (a) => Array.from(a);
const box = ([x0, y0, x1, y1]) => [[x0, y1], [x1, y1], [x1, y0], [x0, y0]];
const all = (view) => Array.from({length: view.spotCount}, (_, s) => s);
const out = {};
const done = () => console.log(JSON.stringify(out));
"""


def node(tmp_path, bundle, made_path, script: str):
    path = tmp_path / "script.cjs"
    path.write_text(PRELUDE + script, encoding="utf-8")
    result = subprocess.run(["node", str(path), str(bundle), str(made_path)], capture_output=True, text=True,
                            encoding="utf-8", timeout=300)
    assert result.returncode == 0, result.stderr[-4000:]
    return json.loads(result.stdout)


def _sectors(run, ok, order):
    """The tree's heads: the sectors with a passing line by their best spot in the order."""
    heads = []
    for s in range(len(run.sectors)):
        spots = [p for p in order if run.sector_of_spot[p] == s]
        if not spots:
            continue
        rows = [i for p in range(run.sector_start[s], run.sector_start[s + 1]) for i in run.lines_of(p) if ok[i]]
        means = [run.hmean[i] for i in rows if run.hmean[i] == run.hmean[i]]
        heads.append((order.index(spots[0]), {
            "n": s, "word": run.sectors[s]["word"], "spots": spots, "lines": len(rows),
            "hmeanMax": float(max(means)) if means else None,
            "len": [float(min(run.len[i] for i in rows)), float(max(run.len[i] for i in rows))]}))
    return [head for _, head in sorted(heads, key=lambda h: h[0])]


def test_passing_shown_order_sectors(tmp_path, bundle, made_path, run):
    """Which lines pass ("Top level only" on at the start, the model's filters, the lines shown), the counts, each
    spot's shown line, the order under the five sorts, the sectors' heads, the labels."""
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const state = () => ({counts: view.counts, shown: all(view).map((s) => view.shownOf(s)), order: list(view.order),
                      sectors: view.sectors, passing: all(view).map((s) => view.passingCount(s)), version: view.version});
out.start = {...state(), topOnly: view.topOnly, sort: view.sort, best: view.best, count: view.count, spots: view.spotCount,
             labels: all(view).map((s) => view.label(s)), sectorOf: all(view).map((s) => view.sectorOf(s)),
             lines3: list(view.linesOf(3)), passing3: list(view.passingOf(3)), spotOf: [0, 1, 2].map((r) => view.spotOf(r)),
             passes: Array.from({length: 40}, (_, r) => view.passes(r))};
out.sorts = {};
for (const key of ["clr", "len", "hmax", "n", "hmean"]) { view.setSort(key); out.sorts[key] = {order: list(view.order), sectors: view.sectors.map((s) => s.n)}; }
let told = 0;
view.subscribe(() => told++);
view.setTopOnly(false);
out.all = {...state(), told};
view.setTopOnly(true);
model.setFilters({...m.NO_FILTERS, lenMin: 80, clrMin: 3, heightMin: 20});
out.filtered = {...state(), topOnly: view.topOnly, told};
model.clearFilters();
out.cleared = {counts: view.counts, topOnly: view.topOnly};
model.setState({...model.state, showOver: false});
out.clear = state();
model.setFilters({...m.NO_FILTERS, lenMin: 1e6});
out.none = {counts: view.counts, order: list(view.order), sectors: view.sectors, picks: view.picks()};
done();
""")
    ok, top_hidden = run.passing()
    start, order = found["start"], run.order(ok)
    assert start["counts"] == {"spots": len(order), "lines": int(ok.sum()), "hidden": int((~ok).sum()),
                               "topHidden": top_hidden, "total": run.n}
    assert top_hidden == int((run.top == 0).sum()) > 0 and len(order) == run.spots
    assert start["topOnly"] is True and start["sort"] == "hmean" and start["best"] == 10
    assert (start["count"], start["spots"]) == (run.n, run.spots)
    assert start["shown"] == run.shown(ok) and start["order"] == order
    assert start["sectors"] == _sectors(run, ok, order)
    assert start["passing"] == [sum(1 for i in run.lines_of(s) if ok[i]) for s in range(run.spots)]
    assert start["labels"] == [f"{run.sector_of_spot[s] + 1}.{s - run.sector_start[run.sector_of_spot[s]] + 1}"
                               for s in range(run.spots)]
    assert start["labels"][0] == "1.1" and start["sectorOf"] == run.sector_of_spot.tolist()
    assert start["lines3"] == run.lines_of(3) and start["passing3"] == [i for i in run.lines_of(3) if ok[i]]
    assert start["spotOf"] == run.spot[:3].tolist() and start["passes"] == ok[:40].tolist()
    for key, got in found["sorts"].items():
        assert got["order"] == run.order(ok, key), key
        assert got["sectors"] == [h["n"] for h in _sectors(run, ok, run.order(ok, key))], key
    assert found["sorts"]["len"]["order"] != order != found["sorts"]["n"]["order"]
    # "Top level only" off: every line passes, the lines that hang lower are counted all the same
    every, hidden = run.passing(top_only=False)
    assert found["all"]["counts"] == {"spots": run.spots, "lines": run.n, "hidden": 0, "topHidden": hidden, "total": run.n}
    assert found["all"]["shown"] == run.shown(every) and found["all"]["order"] == run.order(every)
    assert found["all"]["told"] == 1 and found["all"]["version"] == start["version"] + 1
    # the model's filters: the count of the chip's sentence is of the lines that pass the other filters
    some, lower = run.passing(len_min=80, clr_min=3, height_min=20)
    other, _ = run.passing(top_only=False, len_min=80, clr_min=3, height_min=20)
    filtered = found["filtered"]
    assert filtered["counts"] == {"spots": len(run.order(some)), "lines": int(some.sum()), "hidden": run.n - int(some.sum()),
                                  "topHidden": lower, "total": run.n}
    assert lower == int((other & (run.top == 0)).sum()) and 0 < lower < top_hidden
    assert filtered["shown"] == run.shown(some) and filtered["order"] == run.order(some)
    assert filtered["sectors"] == _sectors(run, some, run.order(some)) and filtered["topOnly"] is True
    assert -1 in filtered["shown"]  # a spot with no passing line is in no order
    # "Clear all" (the model's) leaves "Top level only" on
    assert found["cleared"] == {"counts": start["counts"], "topOnly": True}
    clear, _ = run.passing(show_over=False)
    assert found["clear"]["counts"]["lines"] == int(clear.sum()) and found["clear"]["shown"] == run.shown(clear)
    assert found["none"] == {"counts": {"spots": 0, "lines": 0, "hidden": run.n, "topHidden": 0, "total": run.n},
                             "order": [], "sectors": [], "picks": []}


def test_not_beaten_and_picks(tmp_path, bundle, made_path, run):
    """The lines not beaten of every spot equal a count by mean height, length and clearance; "Start here" over
    every passing line: four picks apart, then "From a top edge" (only in a run with the access mark)."""
    bare = Run(access=False)
    bare_path = tmp_path / "bare.json"
    bare_path.write_text(json.dumps(bare.made()), encoding="utf-8")
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const front = () => all(view).map((s) => list(view.notBeatenOf(s)));
out.start = {front: front(), picks: view.picks(), same: view.notBeatenOf(5) === view.notBeatenOf(5)};
view.setTopOnly(false);
out.all = {front: front(), picks: view.picks()};
model.setFilters({...m.NO_FILTERS, clrMin: 3, heightMin: 40});
out.filtered = {front: front(), picks: view.picks()};
const bare = build({}, JSON.parse(fs.readFileSync(%s, "utf-8")));
out.bare = {picks: bare.view.picks(), access: bare.model.hasAccess};
done();
""" % json.dumps(str(bare_path)))
    for name, ok in (("start", run.passing()[0]), ("all", run.passing(top_only=False)[0]),
                     ("filtered", run.passing(top_only=False, clr_min=3, height_min=40)[0])):
        got = found[name]
        assert got["front"] == [run.not_beaten(ok, s) for s in range(run.spots)], name
        assert got["picks"] == run.picks(ok), name
        # the three values at once: no kept line is matched by another passing line of its spot in mean height,
        # length and clearance
        for s in (0, 7, 50):
            mine = [i for i in run.lines_of(s) if ok[i]]
            for i in got["front"][s]:
                assert not any(j != i and run.len[j] >= run.len[i] and run.clr[j] >= run.clr[i] and
                               (run.hmean[j] > run.hmean[i] or (run.hmean[j] == run.hmean[i] and mine.index(j) < mine.index(i)))
                               for j in mine), (name, s, i)
    assert found["start"]["same"] is True
    kinds = [[p["kind"] for p in found[name]["picks"]] for name in ("start", "all", "filtered")]
    assert all(k[0] == "mean" and 2 <= len(k) <= 5 for k in kinds) and any(k[-1] == "edge" for k in kinds)
    assert any(len(f) < len([i for i in run.lines_of(s) if run.passing()[0][i]])
               for s, f in enumerate(found["start"]["front"]))  # some line is beaten
    assert found["bare"] == {"picks": bare.picks(bare.passing()[0]), "access": False}
    assert all(p["kind"] != "edge" for p in found["bare"]["picks"])


def test_levels_in_view_numbers_and_the_limit(tmp_path, bundle, made_path, run):
    """Auto with its band, a held level, the spots in view (their shown line crosses the view; a touch does not),
    the best N, the numbers (none with All, when refused, at Area), the thin lines of the Lines level and their
    limit; an unchanged view tells nobody."""
    whole = [X0 - 400, Y0 - 400, X0 + SIDE + 400, Y0 + SIDE + 400]
    part = [X0 + 300, Y0 + 500, X0 + 1500, Y0 + 1400]
    close = [X0 + 900, Y0 + 900, X0 + 1100, Y0 + 1100]
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const [whole, part, close] = %s;
const seen = () => { const v = view.inView; return {level: view.level, auto: view.auto, spots: list(v.spots), best: list(v.best), m: v.m,
  numbered: v.numbered, refused: v.refused, strokes: v.strokes, thin: v.thin && list(v.thin),
  numbers: all(view).map((s) => view.numberOf(s)).filter((n) => n).length}; };
out.before = {level: view.level, auto: view.auto, m: view.inView.m, mpp: view.mpp};
let told = 0;
view.subscribe(() => told++);
view.setView(box(whole), 5);
out.area = {...seen(), told, picks: view.picks().map((p) => [p.spot, view.numberOf(p.spot), view.markOf(p.spot), view.markOfRow(p.row)])};
view.setView(box(whole), 5);
out.again = told;
view.setView(box(part), 1);
out.spots = {...seen(), numberOf: list(view.inView.best).map((s) => [view.numberOf(s), view.markOf(s)])};
out.rest = view.numberOf(list(view.inView.spots)[10]);
view.setBest(30); out.best30 = seen();
view.setBest(100); out.best100 = seen();
view.setBest("all"); out.bestAll = seen();
view.setBest(10);
view.setView(box(close), 0.3);
out.lines = seen();
view.setBest("all"); out.linesAll = seen();
view.setTopOnly(false);
view.setLevel("lines");
view.setView(box(whole), 5);
out.held = seen();
view.setBest(100); out.held100 = seen();
view.setLevel("auto");
out.auto = {level: view.level, auto: view.auto};
// Auto's band, from the first view on
const fresh = build().view, band = [];
for (const mpp of [2.1, 1.95, 1.85, 2.1, 2.15, 0.57, 0.55, 0.64, 0.65, 0.5, 5]) { fresh.setView(box(whole), mpp); band.push(fresh.level); }
out.band = band;
out.pure = [[3, null], [1, null], [0.5, null], [2, null], [0.6, null], [1.87, "area"], [1.85, "area"], [0.55, "area"], [2.13, "spots"],
            [2.15, "spots"], [0.56, "spots"], [0.55, "spots"], [0.64, "lines"], [0.65, "lines"], [2.2, "lines"]].map(([mpp, now]) => m.autoLevel(mpp, now));
done();
""" % json.dumps([whole, part, close]))
    ok, _ = run.passing()
    order, shown = run.order(ok), run.shown(ok)
    assert found["before"] == {"level": "area", "auto": True, "m": 0, "mpp": None}

    def in_view(box, of=ok, by=None):
        crossing = run.crossing(box)
        return [s for s in (by or run.order(of)) if crossing[run.shown(of)[s]]], crossing
    spots, _ = in_view(whole)
    area = found["area"]
    assert spots == order and area["spots"] == spots and area["m"] == len(spots) and area["best"] == spots[:10]
    assert (area["level"], area["auto"], area["numbered"], area["refused"], area["thin"]) == ("area", True, False, 0, None)
    assert area["told"] == 1 and found["again"] == 1  # the same view again: nobody is told
    picks = run.picks(ok)
    # at Area a pick's spot carries P and its number (the pick "From a top edge" may share a spot with an earlier pick)
    for pick, (spot, number, mark, of_row) in zip(picks, area["picks"]):
        first = next(p for p in picks if p["spot"] == pick["spot"])
        assert spot == pick["spot"] and number == first["n"] and mark == {"kind": "P", "n": first["n"], "row": first["row"]}
        assert of_row == {"kind": "P", "n": pick["n"], "row": pick["row"]}
    assert area["numbers"] == len({p["spot"] for p in picks})
    spots, _ = in_view(part)
    assert 30 < len(spots) < len(order)  # the view holds a part of the run
    got = found["spots"]
    assert (got["level"], got["spots"], got["m"], got["best"]) == ("spots", spots, len(spots), spots[:10])
    assert got["numbered"] is True and got["numbers"] == 10 and got["thin"] is None and got["strokes"] == 0
    assert got["numberOf"] == [[r + 1, {"kind": "B", "n": r + 1, "row": shown[s]}] for r, s in enumerate(spots[:10])]
    assert found["rest"] == 0
    assert found["best30"]["best"] == spots[:30] and found["best30"]["numbers"] == 30 and found["best30"]["numbered"] is True
    assert found["best100"]["best"] == spots[:100] and found["best100"]["numbers"] == min(100, len(spots))
    assert found["bestAll"]["best"] == spots and found["bestAll"]["numbered"] is False and found["bestAll"]["numbers"] == 0
    # Lines: each best spot's lines not beaten that cross the view; with All every passing line that crosses it
    spots, crossing = in_view(close)
    lines = found["lines"]
    thin = [i for s in spots[:10] for i in run.not_beaten(ok, s) if crossing[i]]
    assert lines["level"] == "lines" and lines["spots"] == spots and len(spots) > 0
    assert sorted(lines["thin"]) == sorted(thin) and lines["strokes"] == len(thin) > 0 and lines["refused"] == 0
    assert lines["numbered"] is True and lines["numbers"] == min(10, len(spots))
    every = [int(i) for i in np.flatnonzero(ok & crossing)]
    assert found["linesAll"]["thin"] == every and found["linesAll"]["strokes"] == len(every)
    assert found["linesAll"]["numbered"] is False and found["linesAll"]["numbers"] == 0
    # Lines held far out with All: more than 5 000 thin lines are refused, counted, and nothing carries a number
    everything, _ = run.passing(top_only=False)
    spots, crossing = in_view(whole, everything)
    held = found["held"]
    assert (held["level"], held["auto"]) == ("lines", False) and held["spots"] == spots
    assert held["refused"] == held["strokes"] == int((everything & crossing).sum()) > LIMIT
    assert held["thin"] is None and held["numbered"] is False and held["numbers"] == 0
    # ... and the best 100's lines not beaten are few enough
    thin = [i for s in spots[:100] for i in run.not_beaten(everything, s) if crossing[i]]
    assert found["held100"]["strokes"] == len(thin) <= LIMIT and found["held100"]["refused"] == 0
    assert found["held100"]["numbered"] is True and found["held100"]["numbers"] == 100
    assert found["auto"] == {"level": "area", "auto": True}  # Auto pressed: the level of the zoom at once
    assert found["band"] == ["area", "area", "spots", "spots", "area", "spots", "lines", "lines", "spots", "lines", "area"]
    assert found["pure"] == ["area", "spots", "lines", "spots", "lines", "area", "spots", "lines", "spots", "area", "spots",
                             "lines", "lines", "spots", "area"]


def test_crosses_squares_breaks_bearing(tmp_path, bundle, made_path, run):
    """In view is strict (a touch does not cross), also in a turned view; the squares: a line in the squares of both
    anchors (once when one), a spot once per square, counted once per change of the filters; the breaks; the side
    by the zoom; a direction's word."""
    passing = int(np.flatnonzero(run.passing()[0])[0])  # a line that passes: its first anchor's square is drawn
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const unit = [[0, 10], [10, 10], [10, 0], [0, 0]], turned = [[5, 12], [12, 5], [5, -2], [-2, 5]];
out.crosses = [[-5, 5, 15, 5], [2, 2, 3, 3], [-5, -5, 0, 0], [-5, 5, 0, 5], [0, -5, 0, 15], [-5, 15, 15, 15], [10, 10, 15, 15],
               [-3, 20, 20, -3], [5, 5, 5, 5], [12, 0, 20, 5]].map((s) => m.crosses(...s, unit));
out.turned = [[5, 5, 6, 6], [0, 0, 1, 1], [-2, 5, 5, 12], [0, 0, 1.5, 1.5], [0, 0, 3, 3], [20, 20, 30, 30]].map((s) => m.crosses(...s, turned));
out.backwards = m.crosses(-5, 5, 15, 5, [...unit].reverse());
const squares = (side) => Object.fromEntries(["spots", "lines", "clr", "len"].map((by) => {
  const g = m.squareValues(view, side, by);
  return [by, {x0: g.x0, y0: g.y0, nx: g.nx, ny: g.ny, cells: list(g.cells), values: list(g.values), side: g.side, by: g.by}];
}));
out.s50 = squares(50); out.s200 = squares(200);
const a = m.squareValues(view, 50, "spots"), b = m.squareValues(view, 50, "lines");
out.once = a.cells === b.cells;
const at = made.rows[%d];
out.at = [m.squareAt(a, at[4], at[5]), m.squareAt(a, a.x0 - 1, a.y0), m.squareAt(a, a.x0 + a.nx * 50 + 1, a.y0)];
out.cellAt = a.cells[out.at[0]];
model.setFilters({...m.NO_FILTERS, lenMin: 150});
out.filtered = squares(50).lines;
out.again = m.squareValues(view, 50, "spots").cells !== a.cells;
out.sides = [0.3, 0.96, 0.97, 1.9, 1.93, 3.8, 3.9, 7.6, 7.7, 30].map((mpp) => m.squareSide(mpp));
out.breaks = [m.breaks(Float64Array.from([]), true), m.breaks(Float64Array.from([1, 1, 1, 1]), true),
              m.breaks(Float64Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 40, 80, 160, 320, 640]), true),
              m.breaks(Float64Array.from([0.5, 1, 2, 4, 8, 16, 32, 64]), false), m.breaks(Float64Array.from([0, 0, 7]), false)];
out.classes = [0, 1, 2, 2.5, 3, 4, 100].map((v) => m.classOf(v, [1, 2, 3, 4]));
out.bearing = [[0, 1], [1, 1], [1, 0], [1, -1], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0.38, 1], [0.42, 1], [-0.01, 1]]
  .map(([dx, dy]) => { const b = m.bearing(dx, dy); return [Math.round(b.deg * 10) / 10, b.word]; });
done();
""" % passing)
    # through, inside, touching a corner, touching an edge from outside, along an edge, outside along, from a corner
    # outwards, across two corners' neighbourhood, a point inside, outside
    assert found["crosses"] == [True, True, False, False, True, False, False, True, True, False]
    assert found["turned"] == [True, False, True, False, True, False] and found["backwards"] is True

    def squares(ok, side):
        cells = {}
        for s in range(run.spots):
            for i in run.lines_of(s):
                if not ok[i]:
                    continue
                for cell in {(math.floor(run.x1[i] / side), math.floor(run.y1[i] / side)),
                             (math.floor(run.x2[i] / side), math.floor(run.y2[i] / side))}:
                    c = cells.setdefault(cell, {"spots": set(), "lines": 0, "clr": -math.inf, "len": -math.inf})
                    c["spots"].add(s)
                    c["lines"] += 1
                    c["clr"], c["len"] = max(c["clr"], run.clr[i]), max(c["len"], run.len[i])
        return cells
    ok, _ = run.passing()
    for side, got in ((50, found["s50"]), (200, found["s200"])):
        want = squares(ok, side)
        grid = got["spots"]
        ix0, iy0 = math.floor(run.box[0] / side), math.floor(run.box[1] / side)
        assert (grid["x0"], grid["y0"], grid["side"]) == (ix0 * side, iy0 * side, side)
        assert grid["nx"] == math.floor(run.box[2] / side) - ix0 + 1 and grid["ny"] == math.floor(run.box[3] / side) - iy0 + 1
        keys = sorted(want, key=lambda c: (c[1] - iy0) * grid["nx"] + (c[0] - ix0))
        assert grid["cells"] == [(c[1] - iy0) * grid["nx"] + (c[0] - ix0) for c in keys]
        assert grid["values"] == [len(want[c]["spots"]) for c in keys]
        assert got["lines"]["values"] == [want[c]["lines"] for c in keys] and got["lines"]["by"] == "lines"
        assert got["clr"]["values"] == [float(want[c]["clr"]) for c in keys]
        assert got["len"]["values"] == [float(want[c]["len"]) for c in keys]
        assert sum(got["lines"]["values"]) > int(ok.sum())  # most lines count in two squares
        assert max(grid["values"]) > 1
    assert found["once"] is True and found["again"] is True
    grid = found["s50"]["spots"]
    i = passing
    assert found["at"][1:] == [-1, -1] and found["cellAt"] == \
        (math.floor(run.y1[i] / 50) - math.floor(run.box[1] / 50)) * grid["nx"] + math.floor(run.x1[i] / 50) - math.floor(run.box[0] / 50)
    some, _ = run.passing(len_min=150)
    want = squares(some, 50)
    assert sorted(found["filtered"]["values"]) == sorted(c["lines"] for c in want.values())
    assert found["sides"] == [25, 25, 50, 50, 100, 100, 200, 200, 200, 200]
    none, flat, counts, metres, one = found["breaks"]
    assert none == [1, 2, 3, 4] and flat == [1, 2, 3, 4]
    assert counts == sorted(set(counts)) and all(isinstance(b, int) for b in counts) and len(counts) == 4
    lo, hi = math.log10(1), math.log10(320)  # the 2nd and the 98th percentile of the 16 values
    assert counts == [round(float(f"{10 ** (lo + (hi - lo) * k / 5):.2g}")) for k in (1, 2, 3, 4)]
    lo, hi = math.log10(0.5), math.log10(32)
    assert metres == [float(f"{10 ** (lo + (hi - lo) * k / 5):.2g}") for k in (1, 2, 3, 4)]
    assert one == [float(f"{10 ** (math.log10(7) + 0.2 * k / 5):.2g}") for k in (1, 2, 3, 4)]
    assert found["classes"] == [0, 1, 2, 2, 3, 4, 4]
    assert found["bearing"][:8] == [[0, "N"], [45, "NE"], [90, "E"], [135, "SE"], [180, "S"], [225, "SW"], [270, "W"], [315, "NW"]]
    assert [b[1] for b in found["bearing"][8:]] == ["N", "NE", "N"] and found["bearing"][10][0] > 359


def test_selection_fan_escape(tmp_path, bundle, made_path, run):
    """A selected spot and its lines' stepper; "Lines from here": the lines that start within 10 m, far ends within
    20 m in one row, at most 40 rows, a numbered line first under its number, the sorts, no line near; a filter
    change closes it and a sort change keeps it; Esc closes it, then ends the selection; a Line is made only for
    the selected lines."""
    ok, _ = run.passing()
    shown, order = run.shown(ok), run.order(ok)
    star = int(run.spot[0])  # the star's spot: 60 lines from one point
    mine = [i for i in run.lines_of(star) if ok[i]]
    assert len(mine) > FAN_MAX + 2
    row = shown[star]
    assert np.hypot(run.x1[row] - (X0 + SIDE / 2), run.y1[row] - (Y0 + SIDE / 2)) < 3
    whole = [X0 - 400, Y0 - 400, X0 + SIDE + 400, Y0 + SIDE + 400]
    # a view in which the star's spot is among the best 10: around its start, with the spots in it
    near_box = [X0 + SIDE / 2 - 40, Y0 + SIDE / 2 - 40, X0 + SIDE / 2 + 40, Y0 + SIDE / 2 + 40]
    crossing = run.crossing(near_box)
    in_view = [s for s in order if crossing[shown[s]]]
    assert star in in_view[:10]
    other = next(s for s in order if s != star and sum(1 for i in run.lines_of(s) if ok[i]) > 3)
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const [star, row, other, whole, nearBox] = %s;
const sel = () => view.selected && {spot: view.selected.spot, row: view.selected.row, index: view.selectedIndex,
                                    line: [view.selected.line.x1, view.selected.line.len], same: view.selected.line === model.lineAt(view.selected.row)};
const fan = () => view.fan && {lines: view.fan.lines, farEnds: view.fan.farEnds, capped: view.fan.capped, sort: view.fan.sort, xy: view.fan.xy,
  rows: view.fan.rows.map((r) => ({row: r.row, rows: list(r.rows), near: r.near, numbered: r.numbered, label: r.label, dh: r.dh, bearing: r.bearing}))};
out.none = {sel: sel(), index: view.selectedIndex, step: view.step(1), escape: view.escape(), made: model.madeLines};
let told = 0;
view.subscribe(() => told++);
view.select(other);
out.first = {sel: sel(), told, made: model.madeLines};
const lines = list(view.passingOf(other));
out.steps = [view.step(-1), view.step(1), sel(), view.step(1), sel(), view.step(-1), view.step(-1), view.step(-1), sel()];
view.select(other, lines[lines.length - 1]);
out.last = [sel(), view.step(1)];
view.select(other, list(view.passingOf(star))[1]);  // a line of another spot: the spot's shown line
out.wrong = sel();
out.made = model.madeLines;
// the selected line stops passing: the selection moves to the spot's shown line; no line of the spot passes: it ends
view.select(other, lines[2]);
model.setFilters({...m.NO_FILTERS, clrMin: made.rows[lines[2]][9] + 0.001});
out.moved = {sel: sel(), shown: view.shownOf(other)};
model.setFilters({...m.NO_FILTERS, lenMin: 1e6});
out.gone = sel();
model.clearFilters();
// "Lines from here" at the star's point, at Area (no B numbers there)
view.setView(box(whole), 5);
const at = {lat: made.rows[row][0], lng: made.rows[row][1]};
view.openFan(at, {row, end: 1});
out.area = fan();
out.levelArea = view.level;
view.closeFan();
view.select(star);
view.setView(box(nearBox), 1);
out.numbers = {star: view.numberOf(star), level: view.level};
view.openFan(at, {row, end: 1});
out.fan = {fan: fan(), sel: sel(), misses: view.fanMisses};
out.sorts = {};
for (const key of ["clr", "len", "dh", "dir", "hmean"]) { view.sortFan(key); out.sorts[key] = fan(); }
view.openFan({lat: at.lat + 0.02, lng: at.lng}, undefined);
out.missed = {misses: view.fanMisses, lines: view.fan.lines};
view.setSort("len");
out.sorted = {open: !!view.fan, labels: view.fan.rows.map((r) => r.label)};
view.setSort("hmean");
view.openFan(at);  // by the point alone: through the fit
out.byPoint = {lines: view.fan.lines, xy: view.fan.xy};
out.escape = [view.escape(), !!view.fan, sel() && sel().spot, view.escape(), sel(), view.escape()];
view.select(star); view.openFan(at, {row, end: 1});
view.select(other);
out.selectCloses = [!!view.fan, sel().spot];
view.openFan(at, {row, end: 1});
model.setFilters({...m.NO_FILTERS, lenMin: 20});
out.filterCloses = !!view.fan;
view.openFan(at, {row, end: 1});
view.select(null);
out.deselect = [!!view.fan, sel()];
out.madeEnd = model.madeLines;
done();
""" % json.dumps([star, row, other, whole, near_box]))
    lines = [i for i in run.lines_of(other) if ok[i]]

    def sel(spot, r):
        of = [i for i in run.lines_of(spot) if ok[i]]
        return {"spot": spot, "row": r, "index": of.index(r), "line": [float(run.x1[r]), float(run.len[r])], "same": True}
    assert found["none"] == {"sel": None, "index": -1, "step": False, "escape": False, "made": 0}
    assert found["first"] == {"sel": sel(other, lines[0]), "told": 1, "made": 1}
    assert found["steps"] == [False, True, sel(other, lines[1]), True, sel(other, lines[2]), True, True, False,
                              sel(other, lines[0])]
    assert found["last"] == [sel(other, lines[-1]), False] and found["wrong"] == sel(other, lines[0])
    assert found["made"] == len({lines[0], lines[1], lines[2], lines[-1]})  # only the selected lines became Lines
    moved, _ = run.passing(clr_min=run.clr[lines[2]] + 0.001)
    still = run.shown(moved)[other]
    assert found["moved"]["shown"] == still and found["gone"] is None
    assert (found["moved"]["sel"] or {"row": -1})["row"] == still  # its shown line now, or none when no line passes

    def check(got, want, labels):
        assert (got["lines"], got["farEnds"], got["capped"]) == (want["lines"], want["farEnds"], want["capped"])
        assert [(r["row"], r["rows"], r["near"], r["numbered"]) for r in got["rows"]] == \
            [(g["row"], g["rows"], g["near"], g["numbered"]) for g in want["rows"]]
        assert [r["dh"] for r in got["rows"]] == pytest.approx([g["dh"] for g in want["rows"]])
        assert [r["label"] for r in got["rows"]] == labels
    x, y = float(run.x1[row]), float(run.y1[row])
    want = run.fan(ok, x, y, {})
    area = found["area"]
    assert found["levelArea"] == "area" and area["xy"] == [x, y] and area["sort"] == "hmean"
    picks = {p["row"]: p["n"] for p in run.picks(ok)}
    marked = run.fan(ok, x, y, picks)
    names, n = [], 0
    for g in marked["rows"]:
        if g["row"] in picks:
            names.append(f"P{picks[g['row']]}")
        else:
            n += 1
            names.append(f"L{n}")
    check(area, marked, names)
    assert want["lines"] >= len(mine) and want["farEnds"] > FAN_MAX and want["capped"] and len(area["rows"]) == FAN_MAX
    # the direction to the far end, from true north
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    for r in area["rows"][:10]:
        i = r["row"]
        ends = (run.lon1[i], run.lat1[i], run.lon2[i], run.lat2[i]) if r["near"] == 1 else \
            (run.lon2[i], run.lat2[i], run.lon1[i], run.lat1[i])
        forward, _, _ = geod.inv(*ends)
        assert abs((r["bearing"] - forward + 180) % 360 - 180) < 0.3
    # at Spots the star's shown line carries its B number: it comes first, under that number
    number = in_view.index(star) + 1
    assert found["numbers"] == {"star": number, "level": "spots"}
    marks = {shown[s]: k + 1 for k, s in enumerate(in_view[:10])}
    want = run.fan(ok, x, y, marks)
    fan = found["fan"]["fan"]
    assert want["rows"][0]["row"] == row and want["rows"][0]["numbered"] is True
    labels, n = [], 0
    for g in want["rows"]:
        if g["row"] in marks:
            labels.append(f"B{marks[g['row']]}")
        else:
            n += 1
            labels.append(f"L{n}")
    check(fan, want, labels)
    assert labels[0] == f"B{number}" and "L1" in labels
    assert found["fan"]["sel"]["spot"] == star and found["fan"]["misses"] == 0  # the selection stays under the fan
    value = {"clr": lambda g: -run.clr[g["row"]], "len": lambda g: -run.len[g["row"]], "dh": lambda g: abs(g["dh"]),
             "hmean": lambda g: Run._down(run.hmean[g["row"]])}
    for key, got in found["sorts"].items():
        first = [r for r in got["rows"] if r["numbered"]]
        rest = got["rows"][len(first):]
        assert got["sort"] == key and first and not any(r["numbered"] for r in rest), key  # numbered rows stay first
        assert {r["label"] for r in first} == {l for l in labels if l[0] == "B"}
        assert [r["label"] for r in rest] == [f"L{k + 1}" for k in range(len(rest))], key  # the numbers follow the order
        assert sorted(r["row"] for r in got["rows"]) == sorted(g["row"] for g in want["rows"])
        if key == "dir":
            assert [r["bearing"] for r in rest] == sorted(r["bearing"] for r in rest)
        else:
            by_row = {g["row"]: g for g in want["rows"]}
            keys = [value[key](by_row[r["row"]]) for r in rest]
            assert keys == sorted(keys), key
    assert found["missed"] == {"misses": 1, "lines": want["lines"]}  # no line near: the open fan stays
    assert found["sorted"]["open"] is True  # a sort of the list keeps the fan (its labels follow the map's numbers)
    # by the point alone the fit places it within centimetres of the anchor
    assert math.dist(found["byPoint"]["xy"], [x, y]) < 0.5 and abs(found["byPoint"]["lines"] - want["lines"]) <= 2
    assert found["escape"] == [True, False, star, True, None, False]
    assert found["selectCloses"] == [False, other] and found["filterCloses"] is False and found["deselect"] == [False, None]
    assert found["madeEnd"] <= found["made"] + 4  # the star's and the other spot's selected lines, no more


def test_view_without_grouping_and_favourites(tmp_path, bundle, made_path, run):
    """The model of a run opened in the view groups nothing (no group or filter measure, no rows), its filters stay
    the model's; a favourite among a spot's passing lines is its shown line (today's rule)."""
    ok, _ = run.passing()
    spot = next(s for s in run.order(ok) if sum(1 for i in run.lines_of(s) if ok[i]) > 4)
    mine = [i for i in run.lines_of(spot) if ok[i]]
    hidden = next(i for i in run.lines_of(spot) if not ok[i])
    found = node(tmp_path, bundle, made_path, r"""
(async () => {
const names = () => [...new Set(performance.getEntriesByType("measure").map((e) => e.name))].sort();
const {model, view} = build();
model.setFilters({...m.NO_FILTERS, lenMin: 100});
view.setView(box([0, 0, 1e7, 1e7]), 1);
view.picks(); view.openFan({lat: 0, lng: 0}, {row: 0, end: 1});
out.view = {names: names(), ungrouped: model.ungrouped, groups: model.groups.length, rows: model.rows.length, selected: model.selected,
            lenMin: model.filters.lenMin, ranges: model.ranges.len, group: model.ranges.group, made: model.madeLines, lines: view.counts.lines};
performance.clearMeasures();
const grouped = new m.ResultModel(dataOf(), {favourites: false, profiles: false, api});
out.today = {names: names(), ungrouped: grouped.ungrouped, groups: grouped.groups.length > 0};
// favourites: a passing line that is not the first of its spot, and a line that does not pass
const [spot, favourite, hidden] = %s;
const key = (r) => [r[0], r[1], r[2], r[3]].join(",");  // keys.lineCoords
const fav = build({favourites: true, api: {...api, loadFavourites: async () => [key(made.rows[favourite]), key(made.rows[hidden])]}});
out.before = {shown: fav.view.shownOf(spot), version: fav.view.version};
let told = 0;
fav.view.subscribe(() => told++);
// the favourites are read: the model says so, and the view was told (asked after every turn, 1 000 at most)
for (let k = 0; k < 1000 && !(fav.model.favouritesOn && told); k++) await new Promise((resolve) => setImmediate(resolve));
out.after = {shown: fav.view.shownOf(spot), on: fav.model.favouritesOn, told, version: fav.view.version, order: list(fav.view.order)};
fav.model.setFilters({...m.NO_FILTERS, favOnly: true});
out.only = {counts: fav.view.counts, order: list(fav.view.order)};
done();
})();
""" % json.dumps([spot, mine[2], hidden]))
    view = found["view"]
    assert "fal:run:group" not in view["names"] and "fal:run:filter" not in view["names"] and "fal:run:rows" not in view["names"]
    assert {"fal:run:ranges", "fal:view:pass", "fal:view:shown", "fal:view:order", "fal:view:inview", "fal:view:picks",
            "fal:view:fan"} <= set(view["names"])
    assert (view["ungrouped"], view["groups"], view["rows"], view["selected"], view["lenMin"]) == (True, 0, 0, None, 100)
    assert view["ranges"] == {"min": float(run.len.min()), "max": float(run.len.max())} and view["group"] is None
    assert view["made"] == 0 and view["lines"] == int(run.passing(len_min=100)[0].sum())
    assert "fal:run:group" in found["today"]["names"] and found["today"] == {**found["today"], "ungrouped": False, "groups": True}
    assert found["before"]["shown"] == mine[0] and found["after"]["shown"] == mine[2] and found["after"]["on"] is True
    assert found["after"]["told"] >= 1 and found["after"]["version"] == found["before"]["version"] + 1
    shown = run.shown(ok)
    shown[spot] = mine[2]
    key = lambda s: (Run._down(run.hmean[shown[s]]), s)  # noqa: E731
    assert found["after"]["order"] == sorted(range(run.spots), key=key)
    assert found["only"] == {"counts": {"spots": 1, "lines": 1, "hidden": run.n - 1, "topHidden": 1, "total": run.n},
                             "order": [spot]}


def _made_of(lines: list, sectors: int = 1) -> dict:
    """A made-up run of a few given lines (dicts: x1, y1, x2, y2 in metres from the run's corner, clr, hmean, hmax,
    spot: its group; optional top): rows of data.js and the view's columns by mapping.view_columns' rule (the spots
    numbered by their first line's mean height, one sector), without the access mark."""
    from pyproj import Transformer
    to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    n = len(lines)
    x1, y1 = np.array([X0 + l["x1"] for l in lines]), np.array([Y0 + l["y1"] for l in lines])
    x2, y2 = np.array([X0 + l["x2"] for l in lines]), np.array([Y0 + l["y2"] for l in lines])
    lon1, lat1 = (np.round(v, 7) for v in to_wgs.transform(x1, y1))
    lon2, lat2 = (np.round(v, 7) for v in to_wgs.transform(x2, y2))
    length = np.hypot(x2 - x1, y2 - y1)
    inside = sorted(range(n), key=lambda i: (lines[i]["spot"], -lines[i]["hmean"], -lines[i]["clr"], -length[i], i))
    first = {}
    for i in inside:
        first.setdefault(lines[i]["spot"], i)
    numbered = sorted(first, key=lambda g: (-lines[first[g]]["hmean"], g))
    spot_of = {g: s for s, g in enumerate(numbered)}
    spot = [spot_of[l["spot"]] for l in lines]
    rows = [[float(lat1[i]), float(lon1[i]), float(lat2[i]), float(lon2[i]), float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i]),
             float(length[i]), float(lines[i]["clr"]), None, 1000.0, 1000.0, False, 0, 0, float(lines[i]["hmax"]), float(lines[i]["hmean"]),
             50.0, 10.0, 10.0, None, None, None, None] for i in range(n)]
    head = {"run": {"id": "few", "name": "Few", "created": "2026-11-17T10:00:00+00:00", "description": ""},
            "center": [float(lat1.mean()), float(lon1.mean())], "area": {"type": "Polygon", "coordinates": []}, "crs": CRS,
            "ortho": None, "distance": 20, "by": "clearance", "model": "sag",
            "rigging": {"pretension": 2.0, "stretch": 5.0, "webbing_weight": 60.0, "athlete_mass": 75.0, "fall_zone": 6.0},
            "slope": 0.15, "leash_fall": 6, "high_above": 20, "max_zoom": 21,
            "sectors": [{"word": "centre", "spots": len(numbered)}],
            "box": [float(min(x1.min(), x2.min())), float(min(y1.min(), y2.min())), float(max(x1.max(), x2.max())), float(max(y1.max(), y2.max()))],
            "lengths": [float(length.min()), float(length.max())]}
    return {"rows": rows, "head": head, "view": {"spot": spot, "top": [l.get("top", 1) for l in lines],
                                                 "by_spot": sorted(inside, key=lambda i: spot[i])}}


def test_picks_apart_and_the_limits_boundary(tmp_path, bundle, made_path):
    """"Start here": a pick in the spot of an earlier pick is left out (also 150 m from it), and one whose middle
    lies 99 m from an earlier pick's; at exactly 100 m it stays. The Lines level draws 5 000 thin lines and refuses
    5 001."""
    def few(apart: float) -> dict:
        lines = [
            {"spot": 0, "x1": 480, "y1": 500, "x2": 520, "y2": 500, "clr": 2, "hmean": 60, "hmax": 70},    # highest on average
            {"spot": 0, "x1": 350, "y1": 650, "x2": 650, "y2": 650, "clr": 5, "hmean": 20, "hmax": 30},    # longest with 3 m clear
            {"spot": 1, "x1": 500 + apart, "y1": 475, "x2": 500 + apart, "y2": 525, "clr": 1, "hmean": 30, "hmax": 90},  # highest point
            *({"spot": 2, "x1": 1500 + 3 * k, "y1": 1500, "x2": 1500 + 3 * k, "y2": 1560, "clr": 4, "hmean": 10 + k, "hmax": 15}
              for k in range(3))]                                                                              # most lines
        return _made_of(lines)
    # 5 001 lines side by side, the first of them not top level: 5 000 pass with "Top level only", 5 001 without
    many = _made_of([{"spot": k // 100, "x1": 100 + 0.2 * k, "y1": 100 + (k % 7), "x2": 100 + 0.2 * k, "y2": 160, "clr": 3 + (k % 5),
                      "hmean": 20 + (k % 11), "hmax": 40, "top": 0 if k == 0 else 1} for k in range(LIMIT + 1)])
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"near": few(99), "at": few(100), "many": many}), encoding="utf-8")
    found = node(tmp_path, bundle, made_path, r"""
const cases = JSON.parse(fs.readFileSync(%s, "utf-8"));
const picks = (name) => build({}, cases[name]).view.picks().map((p) => [p.kind, p.row, p.n]);
out.near = picks("near"); out.at = picks("at");
const {view} = build({}, cases.many), b = cases.many.head.box;
view.setLevel("lines"); view.setBest("all");
view.setView(box([b[0] - 50, b[1] - 50, b[2] + 50, b[3] + 50]), 0.3);
const seen = () => ({strokes: view.inView.strokes, refused: view.inView.refused, thin: view.inView.thin && view.inView.thin.length, lines: view.counts.lines});
out.five = seen();
view.setTopOnly(false);
out.more = seen();
done();
""" % json.dumps(str(cases)))
    # rows: 0 the highest on average, 1 the longest with 3 m clear (its spot), 2 the highest point, 3-5 the spot of most lines
    assert found["near"] == [["mean", 0, 1], ["most", 5, 2]]
    assert found["at"] == [["mean", 0, 1], ["high", 2, 2], ["most", 5, 3]]
    assert found["five"] == {"strokes": LIMIT, "refused": 0, "thin": LIMIT, "lines": LIMIT}
    assert found["more"] == {"strokes": LIMIT + 1, "refused": LIMIT + 1, "thin": None, "lines": LIMIT + 1}


def test_a_view_off_the_run_and_a_malformed_head(tmp_path, bundle, made_path, run):
    """A view without an area (the map panned off the run: every corner clamped to one place) holds nothing: no
    segment crosses it, no spot is in view, nothing carries a number, no line is asked. A store whose head disagrees
    with its columns (the box, a sector's entry, the lengths) is refused by the gate with its reason, never thrown.
    The squares count a line whose first anchor lies outside the head's box."""
    ok, _ = run.passing()
    half = [run.box[0] + (run.box[2] - run.box[0]) / 2, run.box[1], run.box[2], run.box[3]]  # the box's east half
    found = node(tmp_path, bundle, made_path, r"""
const point = [[9, 9], [9, 9], [9, 9], [9, 9]], line = [[0, 0], [10, 0], [10, 0], [0, 0]];
out.crosses = [m.crosses(0, 0, 1, 1, point), m.crosses(9, 9, 9, 9, point), m.crosses(0, 0, 10, 0, line), m.crosses(-5, -5, 20, 20, line),
               m.quadArea(point), m.quadArea(line), m.quadArea([[0, 10], [10, 10], [10, 0], [0, 0]]), m.QUAD_MIN];
const {view, model} = build(), b = made.head.box, corner = [b[2] + 262, b[3] + 262];
let told = 0;
view.subscribe(() => told++);
const seen = () => { const v = view.inView; return {m: v.m, spots: v.spots.length, best: v.best.length, numbered: v.numbered, strokes: v.strokes,
  refused: v.refused, thin: v.thin, numbers: all(view).filter((s) => view.numberOf(s)).length, level: view.level}; };
view.setView(box(b), 1);
out.on = seen().m;
view.setView([corner, corner, corner, corner], 1);
out.off = seen();
view.setLevel("lines"); view.setBest("all");
out.offAll = seen();
view.setView([[b[2] + 262, b[1]], [b[2] + 262, b[1]], [b[2] + 262, b[3]], [b[2] + 262, b[3]]], 0.3);  // off to the east: a line of a view
out.offEast = seen();
view.setView(box(b), 1);
out.back = seen().m;
const said = (change) => { const d = dataOf(); change(d); try { const r = m.viewOf(d); return typeof r === "string" ? r : "ok"; } catch (e) { return "THROWN " + e.message; } };
out.gate = {
  ok: said(() => {}),
  boxShort: said((d) => { d.box = [1, 2, 3]; }), boxText: said((d) => { d.box = [0, 0, "9", 9]; }), boxNaN: said((d) => { d.box = [NaN, 0, 1e7, 1e7]; }),
  boxNull: said((d) => { d.box = null; }), boxNarrow: said((d) => { d.box = [d.box[0] + 50, d.box[1], d.box[2], d.box[3]]; }),
  boxLow: said((d) => { d.box = [d.box[0], d.box[1] + 50, d.box[2], d.box[3]]; }), boxRight: said((d) => { d.box = [d.box[0], d.box[1], d.box[2] - 50, d.box[3]]; }),
  boxTop: said((d) => { d.box = [d.box[0], d.box[1], d.box[2], d.box[3] - 50]; }),
  sectorNull: said((d) => { d.sectors = [null]; }), sectorWord: said((d) => { d.sectors = [{word: 5, spots: 151}]; }),
  sectorCount: said((d) => { d.sectors = [{word: "north", spots: "151"}]; }), sectorZero: said((d) => { d.sectors = [{word: "north", spots: 151}, {word: "south", spots: 0}]; }),
  lengthsShort: said((d) => { d.lengths = [5]; }), lengthsText: said((d) => { d.lengths = ["a", 2]; }), lengthsTurned: said((d) => { d.lengths = [9, 2]; }),
  lengthsNull: said((d) => { d.lengths = null; }),
};
// the squares with a box narrower than the anchors (the model is built, then its head's box replaced): a line whose
// first anchor lies outside still counts in its second anchor's square
const narrow = build();
narrow.model.data.box = %s;
const g = m.squareValues(narrow.view, 50, "lines");
out.narrow = {x0: g.x0, y0: g.y0, nx: g.nx, cells: list(g.cells), values: list(g.values)};
done();
""" % json.dumps(half))
    assert found["crosses"] == [False, False, False, False, 0, 0, 100, 1]
    assert found["on"] == len(run.order(ok))
    nothing = {"m": 0, "spots": 0, "best": 0, "numbered": False, "strokes": 0, "refused": 0, "thin": None, "numbers": 0}
    assert found["off"] == {**nothing, "level": "spots"} and found["offAll"] == {**nothing, "level": "lines"}
    assert found["offEast"] == {**nothing, "level": "lines"} and found["back"] == found["on"]
    gate = found["gate"]
    assert gate["ok"] == "ok" and not any(text.startswith("THROWN") for text in gate.values()), gate
    for name in ("boxShort", "boxText", "boxNaN", "boxNull"):
        assert "box is not four numbers" in gate[name], name
    for name in ("boxNarrow", "boxLow", "boxRight", "boxTop"):
        assert "box does not hold every anchor" in gate[name], name
    for name in ("sectorNull", "sectorWord", "sectorCount", "sectorZero"):
        assert "sectors" in gate[name], name
    for name in ("lengthsShort", "lengthsText", "lengthsTurned", "lengthsNull"):
        assert "lengths" in gate[name], name
    # every anchor inside the narrow box counts its line in its square, once per square
    side, ix0, iy0 = 50, math.floor(half[0] / 50), math.floor(half[1] / 50)
    want = {}
    for i in np.flatnonzero(ok):
        cells = {(math.floor(x / side), math.floor(y / side)) for x, y in ((run.x1[i], run.y1[i]), (run.x2[i], run.y2[i]))
                 if 0 <= math.floor(x / side) - ix0 < found["narrow"]["nx"]}
        for cell in cells:
            want[cell] = want.get(cell, 0) + 1
    keys = sorted(want, key=lambda c: (c[1] - iy0) * found["narrow"]["nx"] + (c[0] - ix0))
    assert found["narrow"]["cells"] == [(c[1] - iy0) * found["narrow"]["nx"] + (c[0] - ix0) for c in keys]
    assert found["narrow"]["values"] == [want[c] for c in keys]
    assert (found["narrow"]["x0"], found["narrow"]["y0"]) == (ix0 * side, iy0 * side)
    # some line's first anchor lies outside the narrow box and its second inside
    assert any(math.floor(run.x1[i] / side) < ix0 <= math.floor(run.x2[i] / side) for i in np.flatnonzero(ok))


def test_the_fan_follows_the_maps_numbers(tmp_path, bundle, made_path, run):
    """An open fan is derived again when the numbers on the map change: a line that loses its B number becomes an L
    row in its place by the sort (no L row above a numbered one), one that gains it comes first; the person's sort
    of the fan is kept; the Fan stays one object. It is derived for its anchor (a press on an anchor's circle lies
    beside the anchor) or, opened at a point, for that point. A move that changes no number derives nothing, nor
    does a view off the run. With "Favourites only" on, a favourite that changes the passing lines closes the fan,
    one that does not (of a line "Top level only" hides) keeps it."""
    ok, _ = run.passing()
    shown, order = run.shown(ok), run.order(ok)
    star = int(run.spot[0])
    row = shown[star]
    not_top = next(i for i in run.lines_of(star) if run.top[i] == 0)
    near_box = [X0 + SIDE / 2 - 40, Y0 + SIDE / 2 - 40, X0 + SIDE / 2 + 40, Y0 + SIDE / 2 + 40]
    found = node(tmp_path, bundle, made_path, r"""
(async () => {
const [star, row, nearBox, notTop] = %s;
const {view} = build();
const refans = () => performance.getEntriesByName("fal:view:refan").length;
const anchor = [view.values.x1[row], view.values.y1[row]];
// the press that opens the fan of an anchor lies beside the anchor (here 30 m east of it: no line starts there)
const beside = view.fit.toLatLng(anchor[0] + 30, anchor[1]), at = {lat: beside[0], lng: beside[1]};
const fan = () => ({sort: view.fan.sort, rows: view.fan.rows.map((r) => [r.row, r.label, r.numbered])});
view.setLevel("spots");
view.setView(box(nearBox), 1);
view.openFan(at, {row, end: 1});
const first = view.fan;
out.numbered = fan();
out.anchor = {anchor, xy: [list(view.fan.xy)]};
// a move that changes no number (the same best spots in view), a view off the run and the way back: nothing derived
const best = () => JSON.stringify(list(view.inView.best)), bestBefore = best(), b = made.head.box, away = [b[2] + 262, b[3] + 262];
let count = refans();
view.setView(box([nearBox[0] + 0.5, nearBox[1], nearBox[2] + 0.5, nearBox[3]]), 1);
out.moved = {sameBest: best() === bestBefore, refans: refans() - count, rows: JSON.stringify(fan()) === JSON.stringify(out.numbered)};
view.setView([away, away, away, away], 1);
out.away = {m: view.inView.m, refans: refans() - count, rows: JSON.stringify(fan()) === JSON.stringify(out.numbered)};
view.setView(box(nearBox), 1);
out.back = {sameBest: best() === bestBefore, refans: refans() - count};
// the list sorted another way: the best spots in view carry other numbers, the fan is derived again once
count = refans();
view.setSort("clr");
out.resorted = {changed: best() !== bestBefore, refans: refans() - count, n: view.numberOf(star),
                label: (view.fan.rows.find((r) => r.row === view.shownOf(star)) || {}).label};
view.setSort("hmean");
count = refans();
view.setBest("all");                       // no number on the map any more
out.plain = {...fan(), same: view.fan === first, refans: refans() - count};
out.anchor.xy.push(list(view.fan.xy));
// opened at a point (a right click 3 m beside the anchor): derived again for that point
const p = build().view;
p.setLevel("spots");
p.setView(box(nearBox), 1);
const near = p.fit.toLatLng(anchor[0] + 3, anchor[1] + 2);
p.openFan({lat: near[0], lng: near[1]});
out.point = {before: list(p.fan.xy), numbered: p.fan.rows.filter((r) => r.numbered).length};
p.setBest("all");
out.point.after = list(p.fan.xy);
out.point.plain = p.fan.rows.filter((r) => r.numbered).length;
view.sortFan("len");
view.setBest(10);                          // the numbers are back: the person's sort stays
out.sorted = {...fan(), same: view.fan === first};
view.setBest("all");
out.sortedPlain = fan();
// "Favourites only": the favourites are the passing lines; one taken away closes the fan
const key = (r) => [r[0], r[1], r[2], r[3]].join(",");
const lines = list(build().view.passingOf(star)).slice(0, 3);
const fav = build({favourites: true, api: {...api, loadFavourites: async () => lines.map((r) => key(made.rows[r]))}});
for (let k = 0; k < 1000 && !fav.model.favouritesOn; k++) await new Promise((resolve) => setImmediate(resolve));
fav.model.setFilters({...m.NO_FILTERS, favOnly: true});
fav.view.openFan(at, {row: lines[0], end: 1});
out.fav = {open: !!fav.view.fan, lines: fav.view.fan && fav.view.fan.lines, passing: fav.view.counts.lines};
// a favourite given to a line that "Top level only" hides: the same lines pass, the fan stays
await fav.model.toggleFavourite(fav.model.lineAt(notTop));
out.favSame = {open: !!fav.view.fan, passing: fav.view.counts.lines, favourites: fav.model.favouriteLines().length};
await fav.model.toggleFavourite(fav.model.lineAt(lines[1]));
out.favGone = {open: !!fav.view.fan, passing: fav.view.counts.lines};
// without the filter a favourite's change keeps the fan
const kept = build({favourites: true, api: {...api, loadFavourites: async () => lines.map((r) => key(made.rows[r]))}});
for (let k = 0; k < 1000 && !kept.model.favouritesOn; k++) await new Promise((resolve) => setImmediate(resolve));
kept.view.openFan(at, {row: lines[0], end: 1});
await kept.model.toggleFavourite(kept.model.lineAt(lines[1]));
out.kept = !!kept.view.fan;
// a favourite becomes its spot's shown line: the spot's number goes with it, in the open fan too (the same best spots)
const moved = build({favourites: true, api: {...api, loadFavourites: async () => []}});
for (let k = 0; k < 1000 && !moved.model.favouritesOn; k++) await new Promise((resolve) => setImmediate(resolve));
moved.view.setLevel("spots");
moved.view.setView(box(nearBox), 1);
moved.view.openFan(at, {row: lines[0], end: 1});
const carrying = () => ({shown: moved.view.shownOf(star), rows: moved.view.fan.rows.filter((r) => r.numbered).map((r) => [r.row, r.label]),
                         best: JSON.stringify(list(moved.view.inView.best))});
out.shownBefore = carrying();
await moved.model.toggleFavourite(moved.model.lineAt(lines[2]));
out.shownAfter = carrying();
done();
})();
""" % json.dumps([star, row, near_box, not_top]))
    numbered = found["numbered"]["rows"]
    # the fan is the anchor's, at its opening and derived again (not the pressed point's, 30 m away)
    assert found["anchor"]["xy"] == [found["anchor"]["anchor"]] * 2 == [[float(run.x1[row]), float(run.y1[row])]] * 2
    # nothing derived by a move that keeps the numbers, off the run, and back; once when the numbers go
    assert found["moved"] == {"sameBest": True, "refans": 0, "rows": True}
    assert found["away"] == {"m": 0, "refans": 0, "rows": True} and found["back"] == {"sameBest": True, "refans": 0}
    resorted = found["resorted"]
    assert resorted["changed"] is True and resorted["refans"] == 1 and resorted["n"] > 0 and resorted["label"] == f"B{resorted['n']}"
    assert found["plain"]["refans"] == 1
    # opened at a point: its place stays the point's (3 m east, 2 m north of the anchor, through the fit)
    point = found["point"]
    assert point["after"] == point["before"] and (point["numbered"], point["plain"]) == (1, 0)
    assert math.dist(point["before"], [run.x1[row] + 3, run.y1[row] + 2]) < 0.6
    assert numbered[0][0] == row and numbered[0][1].startswith("B") and numbered[0][2] is True
    assert [r[1] for r in numbered[1:]] == [f"L{k + 1}" for k in range(len(numbered) - 1)]
    # without numbers: every row an L row, by mean height; the line that was B stands where its mean height puts it
    plain = found["plain"]
    assert plain["same"] is True and all(not r[2] for r in plain["rows"])
    assert [r[1] for r in plain["rows"]] == [f"L{k + 1}" for k in range(len(plain["rows"]))]
    means = [Run._down(run.hmean[r[0]]) for r in plain["rows"]]
    assert means == sorted(means)
    want = run.fan(ok, float(run.x1[row]), float(run.y1[row]), {})
    assert [r[0] for r in plain["rows"]] == [g["row"] for g in want["rows"]]
    # numbered again, the person's sort (by length) kept: the numbered row first, the others by length
    by_length = found["sorted"]
    assert by_length["same"] is True and by_length["sort"] == "len" and by_length["rows"][0][0] == row and by_length["rows"][0][2] is True
    rest = [run.len[r[0]] for r in by_length["rows"] if not r[2]]
    assert rest == sorted(rest, reverse=True) and [r[1] for r in by_length["rows"] if not r[2]] == [f"L{k + 1}" for k in range(len(rest))]
    every = [run.len[r[0]] for r in found["sortedPlain"]["rows"]]
    assert every == sorted(every, reverse=True) and found["sortedPlain"]["sort"] == "len"
    assert found["fav"] == {"open": True, "lines": 3, "passing": 3}
    assert found["favSame"] == {"open": True, "passing": 3, "favourites": 4}
    assert found["favGone"] == {"open": False, "passing": 2} and found["kept"] is True
    mine = [i for i in run.lines_of(star) if ok[i]]
    before, after = found["shownBefore"], found["shownAfter"]
    assert before["shown"] == row == mine[0] and len(before["rows"]) == 1 and before["rows"][0][0] == row and before["rows"][0][1].startswith("B")
    assert after == {"shown": mine[2], "rows": [[mine[2], before["rows"][0][1]]], "best": before["best"]}


FIT_MAX = 0.5
# The five grids the fit was measured on (2026-11-16): name, CRS, a longitude and latitude in it
GRIDS = [("utm36", "EPSG:32633", 14.3, 36.0), ("utm49", "EPSG:32634", 20.0, 49.2), ("pl1992", "EPSG:2180", 19.8, 50.1),
         ("albers", "EPSG:3005", -123.0, 50.0), ("laea", "EPSG:3035", 11.0, 47.0)]
FIT_SIZES = {2: 1, 15: 2, 50: 2, 100: 3}  # the side of the area, km: the degree the fit takes


def _anchored(crs, lon0, lat0, lonlat):
    """Rows of data.js for lines between pairs of points (lon, lat): only the anchors matter."""
    from pyproj import Transformer
    lon, lat = np.round(lonlat[:, 0], 7), np.round(lonlat[:, 1], 7)
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    half = len(lon) // 2
    rows = [[float(lat[i]), float(lon[i]), float(lat[half + i]), float(lon[half + i]), float(x[i]), float(y[i]),
             float(x[half + i]), float(y[half + i]), 50.0, 5.0, None, 100.0, 100.0, False, 0, 0, 20.0, 10.0, 50.0, 10.0, 10.0,
             None, None, None, None] for i in range(half)]
    return rows, lon, lat, np.asarray(x), np.asarray(y)


def _area(lon0, lat0, km, rng, lines=200):
    """`lines` pairs of points spread over a square of `km` around (lon0, lat0)."""
    half_lat = km * 1000 / 2 / 111000
    half_lon = half_lat / math.cos(math.radians(lat0))
    return np.column_stack([rng.uniform(lon0 - half_lon, lon0 + half_lon, 2 * lines),
                            rng.uniform(lat0 - half_lat, lat0 + half_lat, 2 * lines)])


def _numpy_residual(lon, lat, x, y, degree):
    """The largest and the root mean square distance of the least-squares polynomial of `degree` at the anchors."""
    u, v = (lon - lon.mean()) / (np.ptp(lon) or 1), (lat - lat.mean()) / (np.ptp(lat) or 1)
    design = np.column_stack([u ** i * v ** j for i in range(degree + 1) for j in range(degree + 1 - i)])
    dx = design @ np.linalg.lstsq(design, x - x.mean(), rcond=None)[0] - (x - x.mean())
    dy = design @ np.linalg.lstsq(design, y - y.mean(), rcond=None)[0] - (y - y.mean())
    d = np.hypot(dx, dy)
    return float(d.max()), float(np.sqrt((d ** 2).mean()))


FIT_SCRIPT = r"""
const cases = JSON.parse(fs.readFileSync(%s, "utf-8"));
for (const [name, c] of Object.entries(cases)) {
  const cols = m.lineColumns(c.rows), fit = m.gridFit(cols, m.FIT_MAX);
  if (!fit) { out[name] = null; continue; }
  out[name] = {degree: fit.degree, residual: fit.residual, rms: fit.rms, back: fit.back, anchors: fit.anchors, margin: fit.margin,
               turn: fit.turn, points: (c.points || []).map(([lat, lon]) => fit.toGrid(lat, lon)),
               places: (c.places || []).map(([x, y]) => fit.toLatLng(x, y)),
               scales: (c.points || []).map(([lat, lon]) => fit.scale(lat, lon))};
}
out.empty = m.gridFit(m.lineColumns([]));
out.max = m.FIT_MAX; out.needs = m.FIT_ANCHORS; out.margins = [m.FIT_MARGIN, m.FIT_MARGIN_SHARE];
done();
"""


def test_fit_degrees(tmp_path, bundle, made_path, run):
    """The fit between a run's grid and the map (viewgeom.ts gridFit): the lowest degree, 1 to 3, within 0.5 m at the
    anchors, on five real grids over 2, 15, 50 and 100 km, its residual against numpy's least squares; a degree only
    with three times as many distinct anchors as it has numbers per axis; anchors on one line and a run of one line
    by a turn and a scale; every point clamped to the anchors' box and its margin before it is asked."""
    from pyproj import Geod, Transformer
    rng = np.random.default_rng(21)
    cases, want = {}, {}
    for name, crs, lon0, lat0 in GRIDS:
        for km in FIT_SIZES:
            rows, lon, lat, x, y = _anchored(crs, lon0, lat0, _area(lon0, lat0, km, rng))
            # a point in the middle, one on the box's edge, and one 80 km east of the area (clamped to its margin)
            points = [[lat0, lon0], [float(lat.max()), float(lon.max())], [lat0, lon0 + 1.2]]
            cases[f"{name}-{km}"] = {"rows": rows, "points": points, "places": [[float(x.mean()), float(y.mean())],
                                                                                [float(x.max()) + 1e5, float(y.mean())]]}
            want[f"{name}-{km}"] = (crs, lon, lat, x, y, points)
    # all anchors within 300 m, the run's head would say nothing else: the box is the anchors' own
    lon0, lat0 = 20.0, 49.2
    rows, lon, lat, x, y = _anchored("EPSG:32634", lon0, lat0, _area(lon0, lat0, 0.3, rng, lines=40))
    cases["clustered"] = {"rows": rows, "points": [[lat0 + 0.5, lon0 + 0.7], [lat0 - 0.5, lon0 - 0.7]],
                          "places": [[float(x.min()) - 5e4, float(y.max()) + 5e4]]}
    clustered = (lon, lat, x, y)
    # anchors on one straight line of the map (12 lines along it), and a point 200 m beside it
    along = np.linspace(-0.006, 0.006, 24)
    rows, lon, lat, x, y = _anchored("EPSG:32634", lon0, lat0, np.column_stack([lon0 + along, lat0 + 0.4 * along]))
    cases["collinear"] = {"rows": rows, "points": [[lat0 + 0.0018, lon0]]}
    # six lines (12 anchors) over 15 km: too few for degree 2, and degree 1 is metres off
    rows, lon, lat, x, y = _anchored("EPSG:32634", lon0, lat0, _area(lon0, lat0, 15, rng, lines=6))
    cases["few"] = {"rows": rows}
    few = _numpy_residual(lon, lat, x, y, 1)
    cases["one"] = {"rows": run.rows()[100:101], "points": [[float(run.lat1[101]), float(run.lon1[101])]]}
    cases["made"] = {"rows": run.rows()}
    path = tmp_path / "fits.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    found = node(tmp_path, bundle, made_path, FIT_SCRIPT % json.dumps(str(path)))
    assert found["max"] == FIT_MAX and found["needs"] == [2, 9, 18, 30] and found["margins"] == [200, 0.1]
    assert found["empty"] is None
    geod = Geod(ellps="WGS84")
    for key, (crs, lon, lat, x, y, points) in want.items():
        km = int(key.split("-")[1])
        got = found[key]
        residuals = {d: _numpy_residual(lon, lat, x, y, d) for d in (1, 2, 3)}
        degree = next(d for d in (1, 2, 3) if residuals[d][0] <= FIT_MAX)
        assert got["degree"] == degree == FIT_SIZES[km], (key, residuals)
        assert got["residual"] == pytest.approx(residuals[degree][0], abs=5e-3) and got["residual"] <= FIT_MAX, key
        assert got["rms"] == pytest.approx(residuals[degree][1], abs=5e-3) and got["back"] <= FIT_MAX, key
        assert got["anchors"] == 400 and got["margin"] == pytest.approx(max(200, 0.1 * max(np.ptp(x), np.ptp(y)))), key
        # inside the area the fit is the grid within its residual; a place comes back to its latitude and longitude
        to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        for (la, lo), at in zip(points[:2], got["points"][:2]):
            assert math.dist(at, to_grid.transform(lo, la)) <= max(2 * got["residual"], 0.05), key
        back = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(float(x.mean()), float(y.mean()))
        assert abs(got["places"][0][0] - back[1]) < 1e-5 and abs(got["places"][0][1] - back[0]) < 1e-5, key
        # far outside, a point is asked at the box's margin: never farther than the margin from the anchors' box
        beyond = got["points"][2][0] - x.max()
        assert 0.5 * got["margin"] < beyond < 1.6 * got["margin"], (key, beyond, got["margin"])
        far = to_grid.transform(got["places"][1][1], got["places"][1][0])
        assert 0.5 * got["margin"] < far[0] - x.max() < 1.6 * got["margin"], key
        # the grid's metres per metre on the ground, along the east, at the middle
        # (the ground's metre as the sphere of the map's distances has it: the two cancel in the metres per pixel)
        east = to_grid.transform(points[0][1] + 5e-5, points[0][0])
        west = to_grid.transform(points[0][1] - 5e-5, points[0][0])
        ground = math.radians(1e-4) * 6371008.8 * math.cos(math.radians(points[0][0]))
        assert got["scales"][0] == pytest.approx(math.dist(east, west) / ground, rel=2e-4), key
        _, _, true = geod.inv(points[0][1] - 5e-5, points[0][0], points[0][1] + 5e-5, points[0][0])
        assert got["scales"][0] == pytest.approx(math.dist(east, west) / true, rel=5e-3), key
    lon, lat, x, y = clustered
    got = found["clustered"]
    assert got["degree"] == 1 and got["residual"] < 0.05 and got["margin"] == 200
    for at in got["points"]:  # 50 km away both ways: asked at the corner of the box and its margin
        assert x.min() - 350 < at[0] < x.max() + 350 and y.min() - 350 < at[1] < y.max() + 350
        assert min(abs(at[0] - x.min()), abs(at[0] - x.max())) > 100 and min(abs(at[1] - y.min()), abs(at[1] - y.max())) > 100
    assert lat.max() < got["places"][0][0] < lat.max() + 0.004 and lon.min() - 0.006 < got["places"][0][1] < lon.min()
    # anchors on one line: a turn and one scale; a point beside the line is still placed within decimetres
    got = found["collinear"]
    assert got["degree"] == 0 and got["residual"] < 0.05 and got["anchors"] == 24
    beside = Transformer.from_crs("EPSG:4326", "EPSG:32634", always_xy=True).transform(lon0, lat0 + 0.0018)
    assert math.dist(got["points"][0], beside) < 0.5
    # too few anchors for degree 2: the fit stays at degree 1 with its residual, and the gate refuses the run
    got = found["few"]
    assert got["degree"] == 1 and got["anchors"] == 12 and got["residual"] == pytest.approx(few[0], abs=5e-3) and few[0] > FIT_MAX
    got = found["one"]
    assert got["degree"] == 0 and got["residual"] < 0.02 and got["anchors"] == 2
    assert math.dist(got["points"][0], [run.x1[101], run.y1[101]]) < 0.5
    made = found["made"]
    worst, rms = _numpy_residual(np.concatenate([run.lon1, run.lon2]), np.concatenate([run.lat1, run.lat2]),
                                 np.concatenate([run.x1, run.x2]), np.concatenate([run.y1, run.y2]), 1)
    assert made["degree"] == 1 and made["residual"] == pytest.approx(worst, abs=1e-3) and worst < FIT_MAX
    assert made["rms"] == pytest.approx(rms, abs=1e-3) and made["anchors"] == 2 * run.n
    # the grid's north on the map: UTM 34N's meridian convergence west of 21 E turns it a little off true north
    to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    lon_a, lat_a = to_wgs.transform(X0 + SIDE / 2, Y0 + SIDE / 2)
    lon_b, lat_b = to_wgs.transform(X0 + SIDE / 2, Y0 + SIDE / 2 + 1000)
    turn = math.degrees(math.atan2((lon_b - lon_a) * math.cos(math.radians(lat_a)), lat_b - lat_a)) % 360
    assert abs((made["turn"] - turn + 180) % 360 - 180) < 0.05 and 0.1 < min(made["turn"], 360 - made["turn"]) < 3


def test_gate(tmp_path, bundle, made_path, run):
    """The gate before the view opens (spots.ts viewOf): the view's columns, every line once in runs of spots, the
    sectors' spots, a fit within FIT_MAX: a run over 60 km opens (degree 2), one whose anchors are too few for the
    degree it needs does not, and the reason names the degree and the distance."""
    wide = Run(seed=5, side=60000.0, spots=40)
    wide_path = tmp_path / "wide.json"
    wide_path.write_text(json.dumps(wide.made()), encoding="utf-8")
    rng = np.random.default_rng(22)
    rows, lon, lat, x, y = _anchored("EPSG:32634", 20.0, 49.2, _area(20.0, 49.2, 15, rng, lines=6))
    few = {"rows": rows, "view": {"spot": [0] * 6, "top": [1] * 6, "by_spot": list(range(6))},
           "head": {**run.made()["head"], "sectors": [{"word": "centre", "spots": 1}], "ends": [],
                    "box": [min(min(r[4], r[6]) for r in rows), min(min(r[5], r[7]) for r in rows),
                            max(max(r[4], r[6]) for r in rows), max(max(r[5], r[7]) for r in rows)]}}
    few_path = tmp_path / "few.json"
    few_path.write_text(json.dumps(few), encoding="utf-8")
    found = node(tmp_path, bundle, made_path, r"""
const [widePath, fewPath] = %s;
const wide = dataOf(JSON.parse(fs.readFileSync(widePath, "utf-8"))), few = dataOf(JSON.parse(fs.readFileSync(fewPath, "utf-8")));
const said = (r) => typeof r === "string" ? r : "ok";
const gate = (change) => { const d = dataOf(); change(d); return said(m.viewOf(d)); };
const one = {...made, rows: made.rows.slice(100, 101), view: {spot: [0], top: [1], by_spot: [0]},
             head: {...made.head, sectors: [{word: "centre", spots: 1}]}};
out.gate = {
  ok: gate(() => {}), same: (() => { const d = dataOf(); return m.viewOf(d) === m.viewOf(d); })(),
  degree: m.viewOf(dataOf()).fit.degree,
  noView: gate((d) => { delete d.view; }), noSectors: gate((d) => { delete d.sectors; }),
  short: gate((d) => { d.view.top = d.view.top.subarray(1); }),
  twice: gate((d) => { d.view.bySpot[5] = d.view.bySpot[4]; }),
  beyond: gate((d) => { d.view.bySpot[5] = d.columns.length; }),
  gap: gate((d) => { for (let i = 0; i < d.view.spot.length; i++) if (d.view.spot[i] > 3) d.view.spot[i]++; }),
  mixed: gate((d) => { const a = d.view.bySpot[0]; d.view.bySpot[0] = d.view.bySpot[d.view.bySpot.length - 1]; d.view.bySpot[d.view.bySpot.length - 1] = a; }),
  sectors: gate((d) => { d.sectors = [{word: "north", spots: 5}]; }),
  empty: said(m.viewOf({...made.head, sectors: [], box: null, columns: m.lineColumns([]), view: {spot: new Uint32Array(0), top: new Uint8Array(0), bySpot: new Uint32Array(0)}})),
  wide: said(m.viewOf(wide)), wideFit: [m.viewOf(wide).fit.degree, m.viewOf(wide).fit.residual],
  few: said(m.viewOf(few)), fewFit: (() => { const f = m.gridFit(few.columns, m.FIT_MAX); return Math.max(f.residual, f.back); })(),
  one: said(m.viewOf(dataOf(one))),
};
const data = dataOf();
out.has = [m.hasView(data), m.hasView({...data, view: undefined}), m.hasView({...data, sectors: undefined})];
let thrown = "";
try { m.createSpotView(new m.ResultModel({...dataOf(), view: undefined}, {ungrouped: true, favourites: false, profiles: false, api})); } catch (e) { thrown = e.message; }
out.thrown = thrown;
done();
""" % json.dumps([str(wide_path), str(few_path)]))
    gate = found["gate"]
    assert gate["ok"] == "ok" and gate["same"] is True and gate["degree"] == 1 and gate["one"] == "ok"
    assert "no lines" in gate["empty"]
    for name in ("noView", "noSectors", "short"):
        assert "no columns" in gate[name], name
    assert "every line once" in gate["twice"] and "every line once" in gate["beyond"]
    assert "in runs" in gate["gap"] and ("in runs" in gate["mixed"] or "every line once" in gate["mixed"])
    assert "sectors" in gate["sectors"]
    assert gate["wide"] == "ok" and gate["wideFit"][0] == 2 and gate["wideFit"][1] < FIT_MAX  # 60 km: degree 2
    assert gate["fewFit"] > FIT_MAX and f"{gate['fewFit']:.2f} m" in gate["few"] and "degree 1" in gate["few"]
    assert found["has"] == [True, False, False] and "no columns" in found["thrown"]


def test_reader_of_the_views_columns(tmp_path, bundle):
    """result/load.ts readStore gives a store's `spot`, `top` and `by_spot` as they are (RunData.view), the head's
    sectors, box and lengths with the head, and every line's value as from the same store without them; a store
    without the three columns, or with one of another type, has no view."""
    import pyarrow as pa
    import linestore
    from test_linestore import _hard_lines, _profiles
    from test_viewer import _store_head
    rng = np.random.default_rng(11)
    n = 500
    lines = _hard_lines(n, True, True, rng)
    lines.profiles = _profiles(n, rng)
    head = _store_head(lines, True, True)
    plain = tmp_path / "plain"
    plain.mkdir()
    linestore.write(str(plain), lines, head)
    table = linestore.lines_table(lines, head)
    spot = np.sort(rng.integers(0, 7, n)).astype(np.uint32)  # the reader takes the values as they are
    by_spot = rng.permutation(n).astype(np.uint32)
    top = (rng.random(n) < 0.6).astype(np.uint8)
    extra = {"sectors": [{"word": "north-west", "spots": 4}, {"word": "centre", "spots": 3}],
             "box": [1.5, -2.25, 1000.125, 2000.5], "lengths": [30.0, 299.5]}

    def store(name, columns, more):
        made = table
        for column, values in columns:
            made = made.append_column(pa.field(column, values.type, nullable=False), values)
        meta = json.loads(table.schema.metadata[linestore.META_KEY].decode("utf-8"))
        meta["head"] = {**meta["head"], **more}
        made = made.replace_schema_metadata({linestore.META_KEY: json.dumps(meta, ensure_ascii=False,
                                                                            separators=(",", ":")).encode("utf-8")})
        folder = tmp_path / name
        folder.mkdir()
        linestore._write_file(str(folder / linestore.LINES_FILE), made)
        shutil.copy(plain / linestore.FILES[1], folder / linestore.FILES[1])
        return str(folder)
    three = [("spot", pa.array(spot, type=pa.uint32())), ("top", pa.array(top, type=pa.uint8())),
             ("by_spot", pa.array(by_spot, type=pa.uint32()))]
    folders = {"plain": str(plain), "view": store("view", three, extra),
               "two": store("two", three[:2], extra),
               "typed": store("typed", [three[0], ("top", pa.array(top.astype(np.uint32), type=pa.uint32())), three[2]], extra)}
    script = tmp_path / "reader.cjs"
    script.write_text(r"""
const fs = require("fs");
const m = require(process.argv[2]), folders = JSON.parse(process.argv[3]);
const bytes = (p) => { const b = fs.readFileSync(p), ab = new ArrayBuffer(b.length); new Uint8Array(ab).set(b); return ab; };
const read = (folder) => m.readStore(bytes(folder + "/lines.arrow"), bytes(folder + "/profiles.arrow"));
const plain = read(folders.plain), view = read(folders.view), two = read(folders.two), typed = read(folders.typed);
const lines = (d) => JSON.stringify(Array.from({length: d.columns.length}, (_, i) => { const l = m.lineAt(d.columns, i); return Object.keys(l).map((k) => Object.is(l[k], -0) ? "-0" : String(JSON.stringify(l[k]))); }));
const out = {
  n: view.columns.length, has: [m.hasView(view), m.hasView(plain), m.hasView(two), m.hasView(typed)],
  views: ["view" in plain, "view" in two, "view" in typed],
  spot: Array.from(view.view.spot), top: Array.from(view.view.top), bySpot: Array.from(view.view.bySpot),
  types: [view.view.spot.constructor.name, view.view.top.constructor.name, view.view.bySpot.constructor.name],
  head: {sectors: view.sectors, box: view.box, lengths: view.lengths}, plainHead: [plain.sectors, plain.box, plain.lengths].map((v) => v === undefined),
  same: lines(view) === lines(plain), crs: view.crs === plain.crs,
};
console.log(JSON.stringify(out));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script), str(bundle), json.dumps(folders)], capture_output=True, text=True,
                            encoding="utf-8", timeout=300)
    assert result.returncode == 0, result.stderr[-4000:]
    out = json.loads(result.stdout)
    assert out["n"] == n and out["has"] == [True, False, False, False] and out["views"] == [False, False, False]
    assert out["spot"] == spot.tolist() and out["top"] == top.tolist() and out["bySpot"] == by_spot.tolist()
    assert out["types"] == ["Uint32Array", "Uint8Array", "Uint32Array"]
    assert out["head"] == extra and out["plainHead"] == [True, True, True]
    assert out["same"] is True and out["crs"] is True


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_frame_in_edge(tmp_path, run):
    """The view's frame (result/view/SpotColumns.tsx) in headless Edge, on a test page served by the app (its
    CSP), with the made-up run: the flag; the columns with the map's bar, the slots' placeholders and the map's own
    controls; window.FINDALINE_VIEW once the view is drawn (and no FINDALINE_RESULT); a level held and back to
    Auto; Auto and the spots in view following the zoom; Best; Esc; the same model of spots when the window
    becomes a phone's, whose view is the part of the map above the sheet."""
    import re
    import test_web  # the app on a real server, its CSP stubs
    folder = tmp_path / "runs" / "made-up"
    folder.mkdir(parents=True)
    (folder / "made.js").write_text(f"window.MADE = {json.dumps(run.made())};\n", encoding="utf-8")
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['test/spotmap_page.ts'], "
                                  "bundle: true, format: 'iife', target: 'es2020', "
                                  "loader: {'.png': 'dataurl', '.svg': 'text', '.woff2': 'empty', '.woff': 'empty'}, "
                                  f"outdir: {json.dumps(str(folder))}}})"], cwd=VIEWER, check=True)
    (folder / "csp_stub.js").write_text(test_web.CSP_STUB, encoding="utf-8")
    (folder / "spotmap_test.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<link rel="stylesheet" href="spotmap_page.css"><script src="csp_stub.js"></script><script src="made.js"></script>'
        '</head><body><script src="spotmap_page.js"></script></body></html>', encoding="utf-8")
    dom = test_web._edge_page(tmp_path, "runs/made-up/spotmap_test.html", size="1400,900")
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    assert found, dom[-2000:]
    out = json.loads(found.group(1).replace("&nbsp;", chr(160)).replace("&quot;", '"').replace("&lt;", "<")
                     .replace("&gt;", ">").replace("&amp;", "&"))
    assert "error" not in out, out["error"]
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        words = json.load(f)
    ok, _ = run.passing()
    spots = len(run.order(ok))
    # the flag: off until it is set in the browser's storage; a run without the view's columns never opens the view
    assert out["flag"] == {"before": [False, False], "wanted": True, "opens": True, "old": False} and out["after"] is False
    first = out["first"]
    assert out["drawn"] is True and (first["level"], first["auto"], first["best"]) == ("area", True, 10)
    assert first["m"] == first["spots"] == spots and first["status"] == words["ui.view.map.status_area"]
    assert first["pressed"] == [["auto", "true", False], ["area", "false", True], ["spots", "false", False],
                                ["lines", "false", False]]
    # the slots hold the page's own panels; in the columns the hint stands beside the status line
    assert first["slots"] == ["the list's slot", "the details' slot"] and first["places"] == [["hint-map", "map"]]
    assert first["result"] is True and first["leaflet"] is True and first["controls"] == [True] * 4
    assert "Made up" in first["header"] and f"{run.n}lines" in re.sub(r"\s", "", first["header"])
    assert first["actions"] is False  # the run's actions are not in the view yet
    assert "fal:view:first" in first["measures"] and "fal:view:inview" in first["measures"]
    assert not {"fal:run:group", "fal:run:filter", "fal:run:rows"} & set(first["measures"])
    assert first["bestOff"] is True and first["snap"] == [0.25, 0.5]

    def legend(drawn, area=False):
        """The legend lists exactly the shapes and colours the canvas drew (at Area the squares stand for the
        lines' colours), then the access mark's three states."""
        kinds = ("sq", "P") if area else ("clear", "over", "P", "B", "pale", "A", "L", "here")
        assert drawn["legend"] == [k for k in kinds if k in drawn["shapes"]] + ["access-2", "access-1", "access-0"], drawn
        assert drawn["ink"] is True and len(set(map(tuple, drawn["boxes"]))) == len(drawn["numbers"])
    # Area: the squares, the picks bold with their P numbers
    drawn, picks = first["drawn"], run.picks(ok)
    legend(drawn, area=True)
    assert drawn["strokes"] == len(picks) == drawn["picks"] and {"sq", "P"} <= set(drawn["shapes"])
    assert drawn["numbers"] and set(drawn["numbers"]) <= {f"P{p['n']}" for p in picks}
    assert 2.14 < first["mpp"] < 8  # the run's 2.6 km in the map's column: the Area level
    held = out["held"]
    assert (held["level"], held["auto"], held["refused"]) == ("lines", False, False)
    assert held["status"] == (words["ui.view.map.status_lines"].replace("{{n}}", "10").replace("{{m}}", str(spots)) +
                              words["ui.view.map.held"] + words["ui.view.map.back_auto"])
    assert held["pressed"] == [["auto", "false", False], ["area", "false", False], ["spots", "false", False],
                               ["lines", "true", False]]
    assert out["back"] == {"level": "area", "auto": True, "status": words["ui.view.map.status_area"]}
    # Lines held far out, Best 10: the ten bold lines, their lines not beaten thin, every other spot pale
    drawn = held["drawn"]
    legend(drawn)
    # (each line counted once: a best spot's shown line is one of its lines not beaten, drawn thin and bold)
    assert drawn["strokes"] == held["m"] - 10 + drawn["thin"] and drawn["thin"] > 10 and held["m"] == spots
    assert {"B", "pale"} <= set(drawn["shapes"]) and set(drawn["numbers"]) <= {f"B{k}" for k in range(1, 11)}
    zoomed = out["spots"]
    assert zoomed["level"] == "spots" and 0 < zoomed["m"] < spots and zoomed["best"] == min(10, zoomed["m"])
    assert zoomed["numbered"] is True and zoomed["zoom"] * 4 == int(zoomed["zoom"] * 4)  # quarter steps
    assert zoomed["mpp"] == pytest.approx(first["mpp"] / 2 ** 2.5, rel=0.01)
    assert zoomed["status"] == words["ui.view.map.status_spots"].replace("{{n}}", str(zoomed["best"])).replace("{{m}}", str(zoomed["m"]))
    assert {k: v for k, v in zoomed["all"].items() if k != "drawn"} == {"best": "all", "disabled": False,
                             "status": words["ui.view.map.status_spots_all"].replace("{{m}}", str(zoomed["m"]))}
    assert out["escape"] == [True, True] and out["zoomTo"] is True and out["gone"] is True
    # the map moved off the run beyond its north-east corner: no spot in view, the status line says so (B.2 item
    # 16), nothing drawn
    off = out["off"]
    assert off["corner"] == [True, True] and off["level"] != "area"
    assert (off["m"], off["status"]) == (0, words["ui.view.map.status_empty"]), off
    assert (off["drawn"]["strokes"], off["drawn"]["numbers"], off["drawn"]["thin"], off["drawn"]["ink"]) == (0, [], 0, False), off
    # the bar's row beside the status line, with a hint that leaves the row wider than its boxes: the point is the
    # map's, a press there ended the selection; the status line and the hint themselves take their presses
    assert out["row"] == {"wider": True, "wrapped": True, "under": True, "inFoot": False, "inMap": True, "wasSelected": True,
                          "selected": False, "status": True, "hint": True}, out["row"]
    # Spots: the best bold and numbered, the others pale; with All every spot bold, no number, nothing pale
    drawn = zoomed["drawn"]
    legend(drawn)
    assert drawn["strokes"] == zoomed["m"] and "B" in drawn["shapes"] and ("pale" in drawn["shapes"]) == (zoomed["m"] > 10)
    assert drawn["numbers"] and set(drawn["numbers"]) <= {f"B{k}" for k in range(1, zoomed["best"] + 1)}
    drawn = zoomed["all"]["drawn"]
    legend(drawn)
    assert drawn["strokes"] == zoomed["m"] and drawn["numbers"] == [] and not {"B", "pale"} & set(drawn["shapes"])
    # a spot selected: its passing lines on top, A1 and A2 with the access mark on their corners
    drawn = out["selected"]["drawn"]
    legend(drawn)
    # (its shown line is one of the spots' lines in view and one of its own passing lines: counted once)
    assert out["selected"]["inView"] is True and out["selected"]["passing"] > 1
    assert drawn["strokes"] == zoomed["m"] + out["selected"]["passing"] - 1 and drawn["numbers"] == ["A1", "A2"]
    assert out["selected"]["marks"] == 2
    # "Lines from here" at its first anchor: the fan's lines with their numbers, the ring; the spot's lines step back
    drawn = out["fan"]["drawn"]
    legend(drawn)
    # (opened through the model: the canvas moved the map until every far end was in view, and not again)
    # (the fan's row of the spot's shown line is also that spot's line in view: counted once)
    assert out["fan"]["also"] == 1
    assert drawn["strokes"] == out["fan"]["m"] + len(out["fan"]["rows"]) - 1 and "here" in drawn["shapes"] and out["fan"]["marks"] == 0
    assert out["fan"]["moved"] is True and out["fan"]["outside"] == 0
    assert out["fanAgain"] == {"moved": False, "open": True, "outside": 0}
    assert drawn["numbers"] and set(drawn["numbers"]) <= set(out["fan"]["rows"]) and "A" not in drawn["shapes"], out["fan"]
    phone = out["phone"]
    assert out["phoneDrawn"] is True and phone["same"] is True and phone["best"] == "all"
    assert phone["slots"] == first["slots"] and phone["pill"] == "Made up" and phone["footAbove"] is True
    # a phone: the sheet's head, the hint as the sheet's first line, and its "?" beside the map's status line
    # (B.2 item 12: the sheet from its top is the handle, the hint, the head's row, then the body)
    assert phone["places"] == [["hint-map", "map"], ["hint-sheet", "sheet"], ["head", "sheet"]]
    assert phone["sheetOrder"] == ["handle", "hint-sheet", "head", "details", "list"] and out["sheetDrawn"] is True
    # the view opens with the sheet low (132 px), the bar's foot above it
    assert phone["sheet"] == 132 < phone["height"] and phone["covered"] == f"{phone['sheet']}px"
    # the legend: unfolded by itself while the sheet is low, folded at half; a person's unfold at half and fold at
    # low hold until the sheet next changes its stop; at full the bar's foot is not shown
    assert out["folds"] == [["peek", "true", True], ["half", "false", False], ["half", "true", True], ["peek", "true", True],
                            ["peek", "false", False], ["half", "false", False], ["peek", "true", True]], out["folds"]
    assert out["footOff"] is True
    # in view, counted in grid metres through the fit, against a count in the map's own pixels: the whole map in
    # the columns, on a phone the part above the sheet (the sheet's part holds more spots)
    assert abs(zoomed["m"] - zoomed["pixels"]) <= 1
    above = out["phoneView"]
    assert abs(above["above"] - above["pixels"]) <= 1 and above["whole"] > above["pixels"] > 0
    assert above["fitted"]["above"] == above["fitted"]["spots"] == spots  # the first fit left no spot under the sheet
    # a fan opened through the model on the phone: the map moved until every far end is above the sheet
    assert out["phoneFan"]["moved"] is True and out["phoneFan"]["outside"] == 0 and out["phoneFan"]["rows"] == 40
    # the sheet at full: what covers the map exceeds its height, and a panel's move still gives a finite view
    full = out["full"]
    assert full["padding"][0] + full["padding"][1] > full["height"] and full["sane"] == [True] * 3, full
    assert full["sheet"] == "function"  # a phone's panels get the sheet's state and its setter
    assert test_web._violations(dom) == []
