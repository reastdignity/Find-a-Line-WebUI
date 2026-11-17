"""The result view's columns (mapping.view_columns; docs/line-volume/spec-store.md 1.3, spec-view.md B.3, view B1):
the spots renumbered by sector, the order inside a spot (`by_spot`), at most ten sectors, the top-level flag (`top`,
tools/prune_study.py's higher_wins) and the head's `sectors`, `box`, `lengths`, each re-derived here by plain Python
from the words of the specification; written into the store for every new run (linestore.write via
search.save_run), read back, the export unchanged; a run whose view columns fail saved without a store; the same
columns on 1 and 8 threads and for a tiled search; today's page reads such a store as before."""

import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
import pyarrow as pa
import pytest
from scipy.cluster.hierarchy import fcluster, linkage

import helpers as sh
import linestore
import mapping as mp
import runs as rn
from test_linestore import DATA, OFFLINE_ENV, _clip_run, _hard_lines, _meta, _profiles

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import prune_study as ps  # noqa: E402

WORDS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


# ---------------------------------------------------------------------------------------------
# The reference: the specification's words in plain Python

def _key(value: float) -> tuple:
    """A sort key of "highest first, NaN last"."""
    return (1, 0.0) if math.isnan(value) else (0, -value)


def _sectors_by_the_words(ends: list) -> list:
    """A cluster per spot: one each up to 10 spots; Ward's clustering (scipy) of all of them up to
    mapping.SECTOR_WARD_SPOTS; above it Ward's of that many spots taken evenly (np.linspace over the spots'
    order, rounded), then each spot to the nearest mean of a cluster's taken ends (squared distance; a tie to the
    lower cluster), in plain Python."""
    n, cap = len(ends), mp.SECTOR_WARD_SPOTS
    if n <= 10:
        return list(range(n))
    cut = lambda points: (fcluster(linkage(np.array(points), method="ward"), 10,  # noqa: E731
                                   criterion="maxclust") - 1).tolist()
    if n <= cap:
        return cut(ends)
    taken = sorted(set(np.linspace(0, n - 1, cap).round().astype(int).tolist()))
    label = cut([ends[k] for k in taken])
    centres = []
    for c in sorted(set(label)):
        mine = [ends[k] for k, l in zip(taken, label) if l == c]
        total = [0.0] * 4
        for p in mine:
            total = [t + v for t, v in zip(total, p)]
        centres.append([t / len(mine) for t in total])
    out = []
    for p in ends:
        distances = [(p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2 + (p[3] - c[3]) ** 2
                     for c in centres]
        out.append(distances.index(min(distances)))
    return out


def _expected(lines, groups, centre) -> dict:
    """spot, by_spot, top and the head's keys of a LineTable by the specification's words (loops, no shortcut of
    view_columns), from the values as the store holds them."""
    c = lines.columns
    n = len(lines)
    mean = rn.round_floats(c["height_mean"], 2).tolist()
    clr, length = c["clearance"].tolist(), c["length"].tolist()
    x1, y1 = c["a1_xy"][:, 0].tolist(), c["a1_xy"][:, 1].tolist()
    x2, y2 = c["a2_xy"][:, 0].tolist(), c["a2_xy"][:, 1].tolist()
    inside = [sorted(groups.of(g).tolist(), key=lambda r: (_key(mean[r]), _key(clr[r]), _key(length[r]), r))
              for g in range(len(groups))]
    first = [rows[0] for rows in inside]
    ends = []
    for r in first:
        west = (x1[r], y1[r]) <= (x2[r], y2[r])
        ends.append([x1[r], y1[r], x2[r], y2[r]] if west else [x2[r], y2[r], x1[r], y1[r]])
    cluster = _sectors_by_the_words(ends)
    score = [_key(mean[r]) for r in first]  # lower is better: the highest mean height, NaN after every number
    best = {}
    for g, s in enumerate(cluster):
        if s not in best or score[g] < score[best[s]]:
            best[s] = g
    numbered = sorted(best, key=lambda s: (score[best[s]], best[s]))
    sector = [numbered.index(s) for s in cluster]
    spots = sorted(range(len(groups)), key=lambda g: (sector[g], score[g], g))
    spot_of_group = {g: k for k, g in enumerate(spots)}
    spot = [0] * n
    for g in range(len(groups)):
        for r in inside[g]:
            spot[r] = spot_of_group[g]
    by_spot = [r for g in spots for r in inside[g]]
    xs, ys = x1 + x2, y1 + y2
    box = [min(xs), min(ys), max(xs), max(ys)]
    centre_m = min(150, 0.12 * max(box[2] - box[0], box[3] - box[1]))
    sectors = []
    for s in range(len(numbered)):
        mine = [first[g] for g in range(len(groups)) if sector[g] == s]
        mx = float(np.mean([(x1[r] + x2[r]) / 2 for r in mine])) - centre[0]
        my = float(np.mean([(y1[r] + y2[r]) / 2 for r in mine])) - centre[1]
        bearing = (math.degrees(math.atan2(mx, my)) + 360) % 360
        word = "centre" if math.hypot(mx, my) < centre_m else WORDS[int((bearing + 22.5) // 45) % 8]
        sectors.append({"word": word, "spots": len(mine)})
    table = ps.Table({"x1": c["a1_xy"][:, 0].copy(), "y1": c["a1_xy"][:, 1].copy(), "x2": c["a2_xy"][:, 0].copy(),
                      "y2": c["a2_xy"][:, 1].copy(), "elev_a1": rn.round_floats(c["elev_a1"], 2),
                      "elev_a2": rn.round_floats(c["elev_a2"], 2)})
    top = ps.higher_wins(table, cell=8, step=10)
    finite = [v for v in length if math.isfinite(v)]
    return {"spot": spot, "by_spot": by_spot, "top": top.astype(int).tolist(), "sectors": sectors, "box": box,
            "lengths": [min(finite), max(finite)] if finite else None}


def _assert_as_expected(lines, groups, centre):
    view, head = mp.view_columns(lines, groups, centre)
    want = _expected(lines, groups, centre)
    assert (view["spot"].dtype, view["top"].dtype, view["by_spot"].dtype) == (np.uint32, np.uint8, np.uint32)
    assert view["spot"].tolist() == want["spot"]
    assert view["by_spot"].tolist() == want["by_spot"]
    assert view["top"].tolist() == want["top"]
    assert head == {"sectors": want["sectors"], "box": want["box"], "lengths": want["lengths"]}
    return view, head


def _made_up(n: int, seed: int, faces: int = 60, nan_share: float = 0.05) -> sh.LineTable:
    """n lines on `faces` faces of a made-up place: anchors scattered around each face's two ends (spots of
    several lines), elevations in a few levels (stacks of the same plan cells: top-level flags of 0), mean
    heights that tie once rounded to 0.01 m (the order then by clearance, length, the row), clearances and
    lengths that tie too, some lines over trees, NaN mean heights."""
    rng = np.random.default_rng(seed)
    face = rng.integers(0, faces, n)
    centre = rng.uniform(0, 3000, (faces, 2)) + [500_000.0, 250_000.0]
    angle, span = rng.uniform(0, 2 * np.pi, faces), rng.uniform(30, 300, faces)
    a1 = centre[face] + np.round(rng.normal(0, 12, (n, 2)), 1)
    a2 = a1 + np.column_stack([np.cos(angle[face]), np.sin(angle[face])]) * span[face, None] \
        + np.round(rng.normal(0, 12, (n, 2)), 1)
    level = rng.choice([0.0, 4.0, 12.0, 25.0], n)
    e1 = 300 + level + rng.uniform(0, 2, n)
    e2 = 310 + level + rng.uniform(0, 2, n)
    mean = rng.integers(10, 60, n) / 2 + rng.uniform(0, 0.004, n)  # many ties at 0.01 m
    mean[rng.random(n) < nan_share] = np.nan
    columns = {"a1_xy": a1, "a2_xy": a2, "elev_a1": e1, "elev_a2": e2, "height_mean": mean,
               "clearance": rng.integers(0, 12, n) / 4, "length": np.round(np.hypot(*(a2 - a1).T), 0),
               "over_obstacles": rng.random(n) < 0.2, "height_max": mean + 5}
    return sh.LineTable(columns)


# ---------------------------------------------------------------------------------------------
# view_columns

@pytest.mark.parametrize("by", ["clearance", "longest", "height"])
def test_view_columns_by_the_words(by):
    """A made-up place of 20 000 lines: spots, the order inside a spot (mean height, clearance, length, the row;
    NaN last), the sectors (Ward's clustering of the shown lines' ends, at most 10, numbered by their best spot),
    the words, `top` as prune_study's higher_wins, the box and the lengths, as the reference derives them; the
    spots keep group_lines' members; a spot's lines are one run of by_spot; the labels "<sector>.<k>"."""
    lines = _made_up(20_000, 1)
    groups = mp.group_lines(lines, 20, by)
    centre = (501_500.0, 251_500.0)
    view, head = _assert_as_expected(lines, groups, centre)
    spot, by_spot = view["spot"].astype(np.int64), view["by_spot"].astype(np.int64)
    assert sorted(by_spot.tolist()) == list(range(len(lines)))  # a permutation
    assert (np.diff(spot[by_spot]) >= 0).all()  # by spot: a spot's lines are one run
    members = {frozenset(groups.of(g).tolist()) for g in range(len(groups))}
    assert {frozenset(np.flatnonzero(spot == s).tolist()) for s in range(len(groups))} == members
    assert len(head["sectors"]) == 10 and sum(s["spots"] for s in head["sectors"]) == len(groups)
    assert not view["top"].all() and view["top"].any()  # stacks: some lines below their stack's top level
    # The labels: "<sector>.<k>", k from 1 inside each sector, sectors from 1; unique
    first = np.cumsum([0] + [s["spots"] for s in head["sectors"]])
    labels = [f"{s + 1}.{k - first[s] + 1}" for s in range(len(head["sectors"])) for k in range(first[s], first[s + 1])]
    assert len(set(labels)) == len(groups) and labels[0] == "1.1" and labels[first[1]] == "2.1"
    # Inside a sector the spots by their first line's mean height; the sectors by their best (first) spot's
    mean = rn.round_floats(lines.columns["height_mean"], 2)
    starts = np.flatnonzero(np.concatenate([[True], np.diff(spot[by_spot]) != 0]))
    lead = np.where(np.isnan(mean[by_spot[starts]]), -np.inf, mean[by_spot[starts]])
    falling = lambda v: bool((v[1:] <= v[:-1]).all())  # noqa: E731 (-inf twice: no NaN of a difference)
    for s in range(len(head["sectors"])):
        assert falling(lead[first[s]:first[s + 1]]), s
    assert falling(lead[first[:-1]])
    # Rounded ties are ordered by clearance: two lines of one spot with the same stored mean height
    ties = 0
    for a, b in zip(by_spot[:-1], by_spot[1:]):
        if spot[a] == spot[b] and mean[a] == mean[b]:
            assert lines.columns["clearance"][a] >= lines.columns["clearance"][b]
            ties += lines.columns["height_mean"][a] < lines.columns["height_mean"][b]  # unrounded: the other way
    assert ties > 0
    # NaN mean heights last in their spot
    nan = np.isnan(mean[by_spot])
    for s0, s1 in zip(starts, list(starts[1:]) + [len(by_spot)]):
        assert not (np.diff(nan[s0:s1].astype(int)) < 0).any()
    words = {s["word"] for s in head["sectors"]}
    assert words <= set(WORDS) | {"centre"} and len(words) > 2


def test_view_columns_of_few_spots():
    """One spot, two spots, ten and eleven: up to ten spots a sector each (the accepted mock-up's data, P7's
    tree_lib.sectors), numbered by the spot's mean height; eleven are clustered. A spot's words from the run's
    centre; "centre" within 12 % of the extent in a small run."""
    lines = _made_up(4_000, 2, faces=30)
    groups = mp.group_lines(lines, 20, "clearance")
    for count in (1, 2, 10, 11):
        keep = np.sort(np.concatenate([groups.of(g) for g in range(count)]))
        part = lines.take(keep)
        part_groups = mp.group_lines(part, 20, "clearance")
        assert len(part_groups) == count
        view, head = _assert_as_expected(part, part_groups, (501_500.0, 251_500.0))
        assert len(head["sectors"]) == min(count, 10)
        if count <= 10:
            assert [s["spots"] for s in head["sectors"]] == [1] * count
    # A single line, its centre the run's: "centre"
    one = lines.take(np.array([0]))
    x = (one.columns["a1_xy"][0] + one.columns["a2_xy"][0]) / 2
    view, head = _assert_as_expected(one, mp.group_lines(one, 20, "clearance"), tuple(x))
    assert view["spot"].tolist() == [0] and view["by_spot"].tolist() == [0] and view["top"].tolist() == [1]
    assert head["sectors"] == [{"word": "centre", "spots": 1}]


def test_view_columns_without_mean_heights_and_lines():
    """Every mean height NaN: spots and sectors by group_lines' order, lines by clearance; no line: empty
    columns, no sectors, no box or lengths (JSON null, never NaN)."""
    lines = _made_up(3_000, 3, nan_share=1.0)
    assert np.isnan(lines.columns["height_mean"]).all()
    _assert_as_expected(lines, mp.group_lines(lines, 20, "clearance"), (501_500.0, 251_500.0))
    empty = lines.take(np.zeros(0, dtype=np.int64))
    view, head = mp.view_columns(empty, mp.Groups.each_alone(0), (0.0, 0.0))
    assert [(len(v), v.dtype) for v in view.values()] == [(0, np.uint32), (0, np.uint8), (0, np.uint32)]
    assert head == {"sectors": [], "box": None, "lengths": None}


def test_top_level_is_higher_wins():
    """mapping.top_level is tools/prune_study.py's higher_wins (cell 8 m from (0, 0), step 10 m) on a made-up
    table: stacks exactly 10 m apart (the edge), negative coordinates, reversed lines, cells' edges."""
    rng = np.random.default_rng(4)
    n = 30_000
    x1, y1 = rng.integers(-20, 20, n) * 2.0, rng.integers(-20, 20, n) * 2.0
    x2, y2 = x1 + rng.integers(-8, 8, n) * 2.0, y1 + rng.integers(-8, 8, n) * 2.0
    e1 = rng.choice([100.0, 105.0, 110.0, 120.0], n) + rng.integers(0, 3, n)
    e2 = rng.choice([100.0, 105.0, 110.0, 120.0], n) + rng.integers(0, 3, n)
    table = ps.Table({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "elev_a1": e1, "elev_a2": e2})
    want = ps.higher_wins(table, cell=8, step=10)
    got = mp.top_level(x1, y1, x2, y2, e1, e2)
    assert np.array_equal(got, want) and 0.1 < want.mean() < 0.95
    assert (mp.STACK_CELL, mp.STACK_STEP) == (ps.STACK_CELL, ps.STACK_STEP)


def test_sectors_above_the_cap(monkeypatch):
    """The user's "Sample" (2026-11-16): up to mapping.SECTOR_WARD_SPOTS spots every spot goes into Ward's
    clustering, so a run of the cap's spots gives exactly today's (uncapped) result; above it that many spots taken
    evenly, every spot to the nearest cluster: as the plain-Python reference, every spot in a sector, at most 10
    sectors, none empty, the sectors and spots numbered by the rules, the words; twice the same."""
    lines = _made_up(20_000, 1)
    groups = mp.group_lines(lines, 20, "clearance")
    centre = (501_500.0, 251_500.0)
    assert len(groups) > 1_000 and mp.SECTOR_WARD_SPOTS >= 8_269  # the goal case's spots stay exact
    whole = mp.view_columns(lines, groups, centre)
    monkeypatch.setattr(mp, "SECTOR_WARD_SPOTS", len(groups))  # at the cap: exact Ward, today's result
    at_cap = _assert_as_expected(lines, groups, centre)
    assert at_cap[1] == whole[1] and all(np.array_equal(at_cap[0][k], whole[0][k]) for k in mp.VIEW_COLUMNS)
    for cap in (len(groups) - 1, 300, 11):
        monkeypatch.setattr(mp, "SECTOR_WARD_SPOTS", cap)
        view, head = _assert_as_expected(lines, groups, centre)
        sizes = [s["spots"] for s in head["sectors"]]
        assert 1 <= len(sizes) <= 10 and min(sizes) > 0 and sum(sizes) == len(groups), cap
        assert {s["word"] for s in head["sectors"]} <= set(WORDS) | {"centre"}
        spot, by_spot = view["spot"].astype(np.int64), view["by_spot"].astype(np.int64)
        assert sorted(set(spot.tolist())) == list(range(len(groups)))
        mean = rn.round_floats(lines.columns["height_mean"], 2)
        starts = np.flatnonzero(np.concatenate([[True], np.diff(spot[by_spot]) != 0]))
        lead = np.where(np.isnan(mean[by_spot[starts]]), -np.inf, mean[by_spot[starts]])
        first = np.cumsum([0] + sizes)
        assert all(bool((lead[first[s] + 1:first[s + 1]] <= lead[first[s]:first[s + 1] - 1]).all())
                   for s in range(len(sizes)))
        assert bool((lead[first[1:-1]] <= lead[first[:-2]]).all())
        again = mp.view_columns(lines, groups, centre)
        assert again[1] == head and all(np.array_equal(again[0][k], view[k]) for k in view)
    assert head != whole[1]  # 11 spots taken: other sectors than all of them


def test_nan_after_infinities():
    """NaN comes after every number, -inf included, in a spot's order and in the spots' and sectors' order (the
    code review's F1): one spot of four lines with clearances NaN, -inf, 1, NaN; mean heights NaN, -inf, 5, NaN;
    and three spots led by NaN, -inf and 5."""
    def table(mean, clearance):
        n = len(mean)
        a1 = np.column_stack([np.arange(n) * 0.1, np.zeros(n)])
        return sh.LineTable({"a1_xy": a1, "a2_xy": a1 + [50.0, 0.0], "elev_a1": np.full(n, 300.0),
                             "elev_a2": np.full(n, 310.0), "height_mean": np.array(mean, dtype=float),
                             "clearance": np.array(clearance, dtype=float), "length": np.full(n, 50.0),
                             "over_obstacles": np.zeros(n, dtype=bool)})
    one = mp.Groups(np.array([0]), np.arange(4), np.array([0, 4]))
    view, _ = _assert_as_expected(table([20.0] * 4, [np.nan, -np.inf, 1.0, np.nan]), one, (0.0, 0.0))
    assert view["by_spot"].tolist() == [2, 1, 0, 3]
    view, _ = _assert_as_expected(table([np.nan, -np.inf, 5.0, np.nan], [1.0] * 4), one, (0.0, 0.0))
    assert view["by_spot"].tolist() == [2, 1, 0, 3]
    three = mp.Groups(np.array([0, 1, 2]), np.arange(3), np.array([0, 1, 2, 3]))
    view, head = _assert_as_expected(table([np.nan, -np.inf, 5.0], [1.0] * 3), three, (0.0, 0.0))
    assert view["spot"].tolist() == [2, 1, 0] and len(head["sectors"]) == 3
    # The leader of a sector and the spots' order inside one (the second code review's F2, its table): 44 lines,
    # each a spot, in 11 places 1 000 m apart (place 10 beside place 9, so Ward's ten sectors are the places, 9 and
    # 10 together); place 0's spots all NaN, place 1's NaN, NaN, NaN, -inf. Place 1's sector (its leader -inf)
    # comes before place 0's (NaN), and inside it the -inf spot (row 7) before the three NaN ones (rows 4-6)
    n = 44
    place = np.repeat(np.arange(11), 4)
    base = np.column_stack([np.where(place == 10, 9_005.0, place * 1_000.0), np.zeros(n)]) + np.tile(
        [[0, 0], [1, 0], [0, 1], [1, 1]], (11, 1))
    mean = np.tile([5.0, 4.0, 3.0, 2.0], 11)
    mean[0:4] = np.nan
    mean[4:8] = [np.nan, np.nan, np.nan, -np.inf]
    places = sh.LineTable({"a1_xy": base, "a2_xy": base + [60.0, 0.0], "elev_a1": np.full(n, 300.0),
                           "elev_a2": np.full(n, 310.0), "height_mean": mean, "clearance": np.ones(n),
                           "length": np.full(n, 60.0), "over_obstacles": np.zeros(n, dtype=bool)})
    view, head = _assert_as_expected(places, mp.Groups.each_alone(n), (5_000.0, 0.0))
    spot = view["spot"].tolist()
    assert len(head["sectors"]) == 10 and spot[7] < min(spot[4:7]) and max(spot[4:8]) < min(spot[0:4])
    assert spot[4:8] == [37, 38, 39, 36] and sorted(spot[0:4]) == [40, 41, 42, 43]  # place 1's 9th, place 0's last


# ---------------------------------------------------------------------------------------------
# The store

@pytest.mark.parametrize("ends, square, access", [(False, False, False), (True, True, True)],
                         ids=["plain", "all"])
def test_store_with_the_view_columns(tmp_path, ends, square, access):
    """linestore.write with the view's columns: three non-null fields after the lines' columns (spot uint32, top
    uint8, by_spot uint32), the head's keys, format 1; read gives them back; the export is the run's lines.csv and
    lines.geojson byte for byte, as without them. The hard floats of test_linestore (NaN, -inf and +inf of
    clearance and length, NaN mean heights) go through view_columns as the reference gives them; they never put a
    -inf and a NaN where they tie, which test_nan_after_infinities covers."""
    rng = np.random.default_rng(8)
    n = 5_000
    lines = _hard_lines(n, ends, square, rng, access)
    lines.profiles = _profiles(n, rng)
    meta = _meta(lines, ends, square, "clearance", access)
    groups = mp.group_lines(lines, 20, "clearance")
    assert {-np.inf, np.inf} <= set(lines.columns["clearance"].tolist()) and np.isnan(lines.columns["clearance"]).any()
    view, view_head = _assert_as_expected(lines, groups, (0.0, 0.0))
    head = {"run": {"id": "r"}, "distance": 20, **view_head}
    bytes_of = {}
    for name, columns in (("with", view), ("without", None)):
        folder = tmp_path / name
        folder.mkdir()
        meta["store"] = linestore.write(str(folder), lines, head if columns is not None else {"run": {"id": "r"}},
                                        columns)
        (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
        for fmt, file in linestore.EXPORTS.items():
            linestore.export(str(folder), fmt, str(tmp_path / f"{name}-{file}"))
            bytes_of[name, file] = (tmp_path / f"{name}-{file}").read_bytes()
    assert all(bytes_of["with", f] == bytes_of["without", f] for f in linestore.EXPORTS.values())
    with pa.OSFile(str(tmp_path / "with" / linestore.LINES_FILE), "rb") as f:
        schema = pa.ipc.open_file(f).schema
    assert schema.names[-3:] == [name for name, _ in linestore.VIEW] == list(mp.VIEW_COLUMNS)
    assert [(schema.field(k).type, schema.field(k).nullable) for k in mp.VIEW_COLUMNS] == [
        (pa.uint32(), False), (pa.uint8(), False), (pa.uint32(), False)]
    assert json.loads(schema.metadata[b"findaline"])["format"] == 1
    back, got_head = linestore.read(str(tmp_path / "with"))
    assert all(np.array_equal(back.columns[k], view[k]) and back.columns[k].dtype == view[k].dtype for k in view)
    assert {k: got_head[k] for k in linestore.VIEW_HEAD} == view_head
    plain, _ = linestore.read(str(tmp_path / "without"))
    assert not set(mp.VIEW_COLUMNS) & set(plain.columns)
    # A column that does not fit the lines is refused, never wrapped or cut: too short, below and above its type
    beyond = view["spot"].astype(np.int64)
    beyond[0] = 2 ** 32
    flag = view["top"].astype(np.int64)
    flag[1] = 256
    for wrong in ({**view, "spot": view["spot"][:-1]}, {**view, "by_spot": view["by_spot"].astype(np.int64) - 1},
                  {**view, "spot": beyond}, {**view, "top": flag}):
        with pytest.raises(ValueError):
            linestore.lines_table(lines, head, wrong)


def test_store_of_no_lines_with_the_view_columns(tmp_path):
    """A table without lines through view_columns, linestore.write with the view and read: format 1, the three
    columns empty in their types, the head's sectors [] and box and lengths null."""
    lines = _hard_lines(200, False, False, np.random.default_rng(1)).take(np.zeros(0, dtype=np.int64))
    view, view_head = mp.view_columns(lines, mp.Groups.each_alone(0), (0.0, 0.0))
    block = linestore.write(str(tmp_path), lines, {"run": {"id": "e"}, **view_head}, view)
    assert block["format"] == 1 and block["lines"] == 0
    back, head = linestore.read(str(tmp_path))
    assert [(len(back.columns[k]), back.columns[k].dtype) for k in mp.VIEW_COLUMNS] == [
        (0, np.uint32), (0, np.uint8), (0, np.uint32)]
    assert {k: head[k] for k in linestore.VIEW_HEAD} == {"sectors": [], "box": None, "lengths": None}


def _folder_search(tmp_path, name: str, *args, cap: int = 0) -> tuple:
    """findaline.py <args> offline into <tmp_path>/<name>: (the run folder, the output); with `cap`,
    mapping.SECTOR_WARD_SPOTS set to it in that process first."""
    data = tmp_path / name
    run = [sys.executable, "findaline.py"] if not cap else [
        sys.executable, "-c", "import runpy, sys, mapping; mapping.SECTOR_WARD_SPOTS = int(sys.argv[1]); "
                              "sys.argv = ['findaline.py'] + sys.argv[2:]; runpy.run_path('findaline.py', "
                              "run_name='__main__')", str(cap)]
    result = subprocess.run(
        [*run, *args, "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes",
         "--ortho", "never", "--data-dir", str(data)],
        cwd=REPO, env={**os.environ, **OFFLINE_ENV}, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    runs = data / "runs"
    return next(runs / d for d in os.listdir(runs) if (runs / d / "run.json").is_file()), result.stdout


def _stored_view(folder) -> tuple:
    """The view's columns and head keys of a run's store, and what view_columns gives for its lines read back."""
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    lines, head = linestore.read(str(folder), profiles=False)
    stored = {k: lines.columns[k] for k in mp.VIEW_COLUMNS}
    groups = mp.group_lines(lines, meta["params"]["group_distance"], meta["params"]["group_by"])
    again, again_head = mp.view_columns(lines, groups, (meta["center"]["x"], meta["center"]["y"]))
    return stored, {k: head[k] for k in linestore.VIEW_HEAD}, again, again_head, meta


def _by_line(folder, stored) -> tuple:
    """The view's columns of a run by its lines, whatever their rows: {line: (spot, top)} and by_spot as lines
    (a line: its anchors' unrounded grid coordinates, read from the store)."""
    lines, _ = linestore.read(str(folder), profiles=False)
    keys = [tuple(v) for v in np.column_stack([lines.columns["a1_xy"], lines.columns["a2_xy"]]).tolist()]
    assert len(set(keys)) == len(keys)
    return ({keys[r]: (int(stored["spot"][r]), int(stored["top"][r])) for r in range(len(keys))},
            [keys[r] for r in stored["by_spot"].tolist()])


CLIP = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--northing", "254608", "--easting", "553966"]
SURFACE = ["--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif")]
SQUARE = [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580], [19.7522, 50.1580], [19.7522, 50.1546]]]


def test_every_new_run_has_the_view_columns(tmp_path):
    """search.save_run writes the view's columns and head keys for every new run: a circle with every profile
    and a surface model, the square rule on, the access mark on, a tiled area; each equals view_columns of the
    lines read back from the store (its values as stored), and the export is the run's lines.csv byte for byte.
    A tiled area and one grid with equal lines: the same columns."""
    area = tmp_path / "square.geojson"
    area.write_text(json.dumps({"type": "Feature", "properties": {},
                                "geometry": {"type": "Polygon", "coordinates": SQUARE}}))
    area_args = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--area", str(area), "--max-length", "150"]
    cases = {"circle": [*CLIP, *SURFACE, "--radius", "150"],
             "square": [*CLIP, "--radius", "200", "--same-line-square", "5", "--nmpt", "off"],
             "access": [*CLIP, *SURFACE, "--radius", "150", "--access"],
             "one": area_args, "tiled": [*area_args, "--tile-size", "150"]}
    seen = {}
    for name, args in cases.items():
        folder, output = _folder_search(tmp_path, name, *args)
        stored, head, again, again_head, meta = _stored_view(folder)
        assert all(np.array_equal(stored[k], again[k]) for k in stored) and head == again_head, name
        assert meta["store"]["format"] == 1 and meta["store"]["lines"] == len(stored["spot"]) > 0, name
        assert len(head["sectors"]) == min(10, meta["summary"]["spots"]), name
        linestore.export(str(folder), "csv", str(tmp_path / f"{name}.csv"))
        assert (tmp_path / f"{name}.csv").read_bytes() == (folder / "lines.csv").read_bytes(), name
        seen[name] = (_by_line(folder, stored), head, (folder / "lines.csv").read_bytes(), output, meta)
    assert seen["circle"][4]["summary"]["profiles"] == "all"
    assert "same_line_side" in seen["square"][4]["params"] and seen["access"][4]["params"].get("access")
    # The tiles' table holds the lines in another row order (data.js's and the store's): the same lines (lines.csv),
    # each with the same spot and top, and by_spot the same lines in the same order
    assert "tiles)" in seen["tiled"][3] and seen["one"][2] == seen["tiled"][2]
    assert seen["one"][0] == seen["tiled"][0] and seen["one"][1] == seen["tiled"][1]


@pytest.mark.parametrize("cap", [0, 12], ids=["exact", "above-the-cap"])
def test_the_same_columns_on_1_and_8_threads(tmp_path, cap):
    """The clip's search on 1 and 8 threads of the line search: the same lines.csv and the same view columns;
    also with mapping.SECTOR_WARD_SPOTS at 12 in the search's process and spots of 5 m (sectors of 12 spots taken
    evenly, every spot to the nearest)."""
    out = {}
    more = ["--group-distance", "5"] if cap else []
    for threads in (1, 8):
        folder, _ = _folder_search(tmp_path, f"t{threads}", *CLIP, *SURFACE, "--radius", "290", "--threads",
                                   str(threads), *more, cap=cap)
        stored, head, again, again_head, meta = _stored_view(folder)
        out[threads] = (stored, head, (folder / "lines.csv").read_bytes())
        assert meta["summary"]["spots"] > (cap or 10)
        if cap:  # the sample path was taken in the search's process: its head is the capped one, not exact Ward's
            assert head != again_head
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(mp, "SECTOR_WARD_SPOTS", cap)
                lines, _ = linestore.read(str(folder), profiles=False)
                capped = mp.view_columns(lines, mp.group_lines(lines, 5, "clearance"),
                                         (meta["center"]["x"], meta["center"]["y"]))
            assert capped[1] == head and all(np.array_equal(capped[0][k], stored[k]) for k in stored)
        else:
            assert head == again_head
    assert out[1][2] == out[8][2] and out[1][1] == out[8][1]
    assert all(np.array_equal(out[1][0][k], out[8][0][k]) for k in mp.VIEW_COLUMNS)


def test_view_columns_that_fail_never_cost_the_run(tmp_path, monkeypatch):
    """view_columns raising (here a MemoryError) leaves the run saved as when its store fails: the text files and
    the map, run.json without "store", no lines.arrow, a coded warning."""
    def failing(lines, groups, centre):
        raise MemoryError("no memory for the view")
    monkeypatch.setattr(mp, "view_columns", failing)
    folder, results, events = _clip_run(tmp_path, monkeypatch, os.path.join(DATA, "zabi_kon_nmt.tif"), radius=150)
    assert sorted(os.listdir(folder)) == ["ATTRIBUTION.txt", "data.js", "lines.csv", "lines.geojson", "lines.js",
                                          "map.html", "run.json"]
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert "store" not in meta and meta["summary"]["lines"] == len(results) > 0
    assert ("warning", "The run is saved without its store (lines.arrow): MemoryError: no memory for the view") \
        in events


# ---------------------------------------------------------------------------------------------
# Today's page reads such a store as before

PAGE_SCRIPT = r"""
const fs = require("fs");
const [withView, without] = process.argv.slice(2);
const bytes = (p) => { const b = fs.readFileSync(p), ab = new ArrayBuffer(b.length); new Uint8Array(ab).set(b); return ab; };
const read = (folder) => m.readStore(bytes(folder + "/lines.arrow"), bytes(folder + "/profiles.arrow"));
const a = read(withView), b = read(without), bad = [];
const n = b.columns.length;
for (let i = 0; i < n; i++) {
  const x = m.lineAt(a.columns, i), y = m.lineAt(b.columns, i);
  if (JSON.stringify(Object.keys(x)) !== JSON.stringify(Object.keys(y))) bad.push([i, "keys"]);
  for (const k of Object.keys(y)) {
    if (k === "prof") { if (JSON.stringify(x.prof) !== JSON.stringify(y.prof)) bad.push([i, "prof"]); continue; }
    if (!Object.is(x[k], y[k])) bad.push([i, k, String(x[k]), String(y[k])]);
  }
  if (m.lineCoords(x) !== m.lineCoords(y)) bad.push([i, "coords"]);
}
const api = {loadFavourites: async () => [], saveFavourite: async () => {}, profile: async () => { throw new Error("no"); }};
const state = (run) => { const model = new m.ResultModel(run, {favourites: false, api});
  return JSON.stringify({shown: model.shown, count: model.count,
                         groups: model.groups.map((g) => [m.lineCoords(g.rep)].concat(g.members.map(m.lineCoords)))}); };
const {columns: _a, ...headA} = a, {columns: _b, ...headB} = b;
console.log(JSON.stringify({n, length: a.columns.length, bad: bad.slice(0, 20), model: state(a) === state(b),
                            keys: Object.keys(headA).filter((k) => !(k in headB)).sort()}));
"""


def test_todays_page_reads_a_store_with_the_view_columns(tmp_path):
    """result/load.ts readStore on the clip's store with the view's columns and on the same store without them:
    every Line value, its profile and keys.lineCoords are the same, and the page's model gives the same spots and
    counts; the head only gains the view's keys."""
    from test_viewer import VIEWER, _run_node, _store_bundle
    if shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")):
        pytest.skip("needs Node and `npm install` in viewer/")
    folder, _ = _folder_search(tmp_path, "clip", *CLIP, *SURFACE, "--radius", "150")
    assert {name for name, _ in linestore.VIEW} <= set(pa.ipc.open_file(
        pa.OSFile(str(folder / linestore.LINES_FILE), "rb")).schema.names)
    lines, head = linestore.read(str(folder))
    for name in mp.VIEW_COLUMNS:
        lines.columns.pop(name)
    without = tmp_path / "without"
    without.mkdir()
    linestore.write(str(without), lines, {k: v for k, v in head.items() if k not in linestore.VIEW_HEAD})
    out = _run_node(tmp_path, _store_bundle(tmp_path), PAGE_SCRIPT, str(folder).replace("\\", "/"),
                    str(without).replace("\\", "/"))
    assert out["bad"] == [] and out["model"] and out["n"] == out["length"] == len(lines) > 100
    assert out["keys"] == sorted(linestore.VIEW_HEAD)
