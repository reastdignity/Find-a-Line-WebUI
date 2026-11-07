"""The end zone and the lift in the line search (helpers.end_zone_rule): the kernels against a brute
force over every anchor pair with helpers.evaluate_line, the evaluation and the profiles against their
Python references, the ladder's buckets against re-runs, nesting, the count mode, threads, the zone's
steps and the refusals (offline, seconds)."""

import functools
import json
import math

import numpy as np
import pytest

import helpers as sh
import lineprofiles as lp
import linesearch as ls
import sag

RULES = [(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (0.0, 1.0, 0.0), (10.0, 1.0, 2.5), (20.0, 2.0, 0.0)]  # zone, lift, end clr
ZONES = (0.0, 5.0, 10.0, 20.0)
LIFTS = (0.0, 1.0, 2.0)
MIN_LENGTH, MAX_LENGTH, DH_RATIO = 20.0, 120.0, 0.4


def canyon(seed=5):
    """A canyon across the columns with rounded rims (the strict rule fails next to most anchors),
    gentle ramps along the rows and on the floor, a little noise, a few NaNs; a surface model with
    a few trees; anchors on the steep pixels and anywhere; a tile's first mask; strong anchors."""
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0:110, 0:130].astype(np.float64)
    edge = lambda c, c0, w: 0.5 - 0.5 * np.cos(np.pi * np.clip((c - c0) / w, 0, 1))  # noqa: E731
    z = 100 - 45 * edge(cols, 28, 8) + 50 * edge(cols, 92, 6)  # a 45 m drop and a 50 m rise
    z += 0.04 * rows + 0.02 * np.abs(cols - 65) + rng.random(z.shape) * 0.6
    z[rng.random(z.shape) < 0.002] = np.nan
    z = z.astype(np.float32)
    surface = (z + (rng.random(z.shape) < 0.05) * rng.random(z.shape) * 12).astype(np.float32)
    steep = sh.find_significant_slopes(z, 1.0, 20, np.ones(z.shape, dtype=bool), threads=1)
    anchors = np.vstack([steep[rng.choice(len(steep), 170, replace=False)], rng.integers(0, 110, (20, 2))])
    first = rng.random(len(anchors)) < 0.7
    strong = rng.random(len(anchors)) < 0.5
    values = rng.random((len(anchors), 2)) * 50  # prominence, drop of the anchors
    return z, surface, anchors.astype(np.int64), first, strong, values


# model, nmpt mode (None: no surface), first mask, strong anchors, wall-angle limit
CASES = [("formula", "mark", True, False, None), ("formula", None, False, True, 120.0),
         ("sag", "reject", False, False, 150.0), ("sag", "mark", True, True, None)]


@functools.lru_cache(maxsize=None)
def table_of(model):
    return sag.EnvelopeTable(sag.Rigging(), MIN_LENGTH, MAX_LENGTH) if model == "sag" else None


@functools.lru_cache(maxsize=None)
def canyon_of(seed=5):
    return canyon(seed)


def search(case, rule, zones=(), threads=2, sink=None):
    """find_valid_lines on the canyon of a case at a rule (end_zone, lift, end_clearance)."""
    model, nmpt, first, strong, wall = case
    z, surface, anchors, first_mask, strong_mask, values = canyon_of()
    end_zone, lift, end_clearance = rule
    return ls.find_valid_lines(z, surface if nmpt else None, anchors, 1.0, MIN_LENGTH, MAX_LENGTH, nmpt_mode=nmpt,
                               threads=threads, sag_table=table_of(model), max_dh_ratio=DH_RATIO,
                               first=first_mask if first else None,
                               limits=sh.LineLimits(max_wall_angle=wall) if wall else None, anchor_values=values,
                               strong=strong_mask if strong else None, sink=sink, end_zone=end_zone, lift=lift,
                               end_clearance=end_clearance, zones=zones)


def brute_force(case, rule):
    """Every anchor pair that find_valid_lines' filters let through (the line belongs to its first
    anchor, smaller x then y, with first; one strong anchor; length; height difference), decided by
    helpers.evaluate_line at the rule and helpers.is_valid, then the wall-angle limit: Lines."""
    model, nmpt, first, strong, wall = case
    z, surface, anchors, first_mask, strong_mask, values = canyon_of()
    end_zone, lift, end_clearance = rule
    table = table_of(model)
    s = surface if nmpt else None
    down = sh.downslope(z, anchors, 1.0)
    elev = z[anchors[:, 0], anchors[:, 1]]
    lines = []
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            if first:
                f = i if (anchors[i, 1], anchors[i, 0]) < (anchors[j, 1], anchors[j, 0]) else j
                if not first_mask[f]:
                    continue
            if strong and not (strong_mask[i] or strong_mask[j]):
                continue
            dr, dc = anchors[j] - anchors[i]
            length = math.hypot(dr, dc)
            if length > MAX_LENGTH or length < MIN_LENGTH:
                continue
            if not abs(float(elev[j]) - float(elev[i])) <= min(DH_RATIO * length, np.inf):
                continue
            result = sh.evaluate_line(anchors[i], anchors[j], z, 1.0, s, table, end_zone=end_zone, lift=lift,
                                      end_clearance=end_clearance)
            if not sh.is_valid(result, nmpt):
                continue
            a1, a2 = sh.wall_angles(anchors[i:i + 1], anchors[j:j + 1], down[i:i + 1], down[j:j + 1])
            if wall is not None and not max(float(a1[0]), float(a2[0])) <= wall:
                continue
            elev_a1, elev_a2, length, clearance, clearance_nmpt, *heights = result
            lines.append(sh.Line(tuple(map(int, anchors[i])), tuple(map(int, anchors[j])), length, elev_a1, elev_a2,
                                 clearance, clearance_nmpt, *heights, float(a1[0]), float(a2[0]), values[i, 0],
                                 values[j, 0], values[i, 1], values[j, 1]))
    return lines


def pairs(table):
    return list(zip(map(tuple, table.columns["a1"].tolist()), map(tuple, table.columns["a2"].tolist())))


@pytest.mark.parametrize("case", CASES, ids=["-".join(map(str, c)) for c in CASES])
def test_search_equals_brute_force(case):
    """find_valid_lines at every rule gives exactly the lines (every value) of the brute force, longest
    first; the rule matters on the canyon (every zone and lift adds lines)."""
    counts = []
    for rule in RULES:
        found = search(case, rule)
        lines = found.lines()
        want = brute_force(case, rule)
        key = lambda line: (line.a1, line.a2)  # noqa: E731
        assert sorted(lines, key=key) == sorted(want, key=key), (case, rule)
        lengths = found.columns["length"]
        assert np.all(lengths[:-1] >= lengths[1:])  # longest first
        counts.append(len(lines))
    assert counts[0] < counts[1] and counts[0] < counts[2] and counts[0] < counts[4], counts


def test_evaluate_lines_matches_evaluate_line():
    """The numba evaluation gives exactly (==) helpers.evaluate_line's decisions, values and bucket minima
    at a zone, a lift and an end clearance, for both models and nmpt modes."""
    rng = np.random.default_rng(7)
    terrain = (rng.random((120, 120)) * 30 + 100).astype(np.float32)
    terrain[rng.random((120, 120)) < 0.002] = np.nan
    surface = (terrain + rng.random((120, 120)) * 15).astype(np.float32)
    surface[rng.random((120, 120)) < 0.3] = np.nan
    terrain[:, :8] += 60
    terrain[:, -8:] += 60
    anchors = np.column_stack([rng.integers(0, 120, 400),
                               np.where(rng.random(400) < 0.5, rng.integers(0, 8, 400), rng.integers(112, 120, 400))])
    anchors[:50] = rng.integers(0, 120, (50, 2))
    found = rng.integers(0, 400, (3000, 2))
    for model in ("formula", "sag"):
        table = sag.EnvelopeTable(sag.Rigging(), 20, 200) if model == "sag" else None
        for mode, (end_zone, lift, end_clearance) in (("mark", (10.0, 1.0, 0.0)), ("reject", (5.0, 2.0, 1.5)),
                                                      ("mark", (0.0, 0.5, 0.0)), ("reject", (30.0, 0.0, 0.0))):
            values = rng.random((len(anchors), 2)) * 50
            fast = ls.evaluate_lines(found, anchors, terrain, 1.0, surface, table, mode, anchor_values=values,
                                     end_zone=end_zone, lift=lift, end_clearance=end_clearance, zones=ZONES)
            down = sh.downslope(terrain, anchors, 1.0)
            angles = np.column_stack(sh.wall_angles(anchors[found[:, 0]], anchors[found[:, 1]],
                                                    down[found[:, 0]], down[found[:, 1]])).tolist()
            slow, buckets, buckets_nmpt = [], [], []
            for (i, j), (angle1, angle2) in zip(found, angles):
                result = sh.evaluate_line(anchors[i], anchors[j], terrain, 1.0, surface, table, end_zone=end_zone,
                                          lift=lift, end_clearance=end_clearance, zones=ZONES)
                if sh.is_valid(result, mode):
                    elev_a1, elev_a2, length, clearance, clearance_nmpt, *heights = result[:8]
                    slow.append(sh.Line(tuple(map(int, anchors[i])), tuple(map(int, anchors[j])), length, elev_a1,
                                        elev_a2, clearance, clearance_nmpt, *heights, angle1, angle2, values[i, 0],
                                        values[j, 0], values[i, 1], values[j, 1]))
                    buckets.append(result[8])
                    buckets_nmpt.append(result[9])
            assert slow and fast.lines() == slow, (model, mode)
            assert np.array_equal(fast.columns["zone_margins"], np.array(buckets))
            assert np.array_equal(fast.columns["zone_margins_nmpt"], np.array(buckets_nmpt))
            if end_zone in ZONES:  # the clearance is the decision value the buckets give
                expected = decision(np.array(buckets), ZONES.index(end_zone), lift, sh.end_delta(table, end_clearance))
                assert np.array_equal(fast.columns["clearance"], expected)
    # no zones: the columns of before
    plain = ls.evaluate_lines(found, anchors, terrain, 1.0, surface, None, "mark", end_zone=5.0, lift=1.0)
    assert set(plain.columns) == {"a1", "a2", *sh.LINE_VALUES}


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_line_profiles_match_line_profile(model):
    """lineprofiles.line_profiles gives every line exactly (==, and the same JSON text) helpers.line_profile's
    profile at a zone and a lift, with "zone" and "lift" at its end; "min" follows the decision values,
    "max_height" the strict margin's plus the lift; at 0 / 0 neither key is there."""
    from test_units import _profile_case
    terrain, surface, water, filled, a1, a2 = _profile_case()
    table = sag.EnvelopeTable(sag.Rigging(), 2, 400) if model == "sag" else None
    encoder = json.JSONEncoder(separators=(",", ":"))
    changed = 0
    for res, s, w, g, points, rule in ((0.25, surface, water, filled, 200, (5.0, 1.0, 0.0)),
                                       (1.0, surface, None, filled, 7, (20.0, 0.0, 2.0)),
                                       (2.0, None, water, None, 50, (0.0, 2.0, 0.0)),
                                       (1.0, surface, water, None, 30, (0.0, 0.0, 3.0))):
        end_zone, lift, end_clearance = rule
        batch = lp.line_profiles(a1, a2, terrain, res, s, points, table, w, g, parts=7, end_zone=end_zone, lift=lift,
                                 end_clearance=end_clearance)
        plain = lp.line_profiles(a1, a2, terrain, res, s, points, table, w, g, parts=7)
        for k in range(len(a1)):
            slow = sh.line_profile(tuple(a1[k].tolist()), tuple(a2[k].tolist()), terrain, res, s, points, table, w, g,
                                   end_zone=end_zone, lift=lift, end_clearance=end_clearance)
            fast = batch[k].as_dict()
            assert fast == slow, (res, points, k)
            assert list(fast) == list(slow)
            assert encoder.encode(fast) == encoder.encode(slow), (res, points, k)
            before = plain[k].as_dict()
            assert ("zone" in fast) == bool(end_zone or lift) and "zone" not in before
            # the webbing on the A-frames: the strict margin's highest point, raised by the lift (rounded apart)
            assert fast["max_height"][0] == before["max_height"][0]  # (the points kept follow "min")
            assert abs(fast["max_height"][1] - before["max_height"][1] - lift) < 0.0101
            changed += fast["min"] != before["min"]
    assert changed > 100


def decision(m, j, lift, delta):
    """The clearance of a run at ladder zone j and lift from bucket minima m (helpers.decision_values)."""
    zone = m[:, :j].min(axis=1) if j else np.full(len(m), np.inf)
    core = m[:, j:].min(axis=1)
    c = lift + delta
    return np.minimum(zone if c == 0.0 else zone + c, core if lift == 0.0 else core + lift)


@pytest.mark.parametrize("case", CASES[:3], ids=["-".join(map(str, c)) for c in CASES[:3]])
def test_ladder_equals_reruns(case):
    """The superset run's buckets decide at every ladder zone and lift (helpers.valid_at, the surface's
    too with "reject") exactly as a run at that zone and lift: the same lines in the same order, and
    its clearances; also with an end clearance (delta smaller); every larger setting nests the smaller."""
    model, nmpt, *_ = case
    for end_clearance in (0.0, 2.5):
        delta = sh.end_delta(table_of(model), end_clearance)
        top = search(case, (ZONES[-1], LIFTS[-1], end_clearance), zones=ZONES)
        before = None
        for j, x in enumerate(ZONES):
            for lift in LIFTS:
                mask = sh.valid_at(top.columns["zone_margins"], j, lift, delta)
                if nmpt == "reject":
                    mask &= sh.valid_at(top.columns["zone_margins_nmpt"], j, lift, delta)
                again = search(case, (x, lift, end_clearance), zones=ZONES)
                assert pairs(top.take(mask)) == pairs(again), (x, lift)
                assert np.array_equal(decision(top.columns["zone_margins"][mask], j, lift, delta),
                                      again.columns["clearance"])
                assert np.array_equal(again.columns["zone_margins"], top.columns["zone_margins"][mask])
                if lift == 0.0 and before is not None:
                    assert set(pairs(before)) <= set(pairs(again))  # a larger zone nests the smaller
                if lift == 0.0:
                    before = again
                if j and lift:  # a larger lift at the same zone nests the smaller
                    smaller = sh.valid_at(top.columns["zone_margins"], j, lift - 1.0, delta)
                    assert not (smaller & ~sh.valid_at(top.columns["zone_margins"], j, lift, delta)).any()
    plain = search(case, (0.0, 0.0, 0.0))
    assert set(plain.columns) == {"a1", "a2", *sh.LINE_VALUES}


@pytest.mark.parametrize("case", [CASES[0], CASES[2]], ids=["formula", "sag"])
def test_lift_values_against_brute_force(case):
    """helpers.lift_values from the buckets (0, X) of a search at zone X and A-frames H, as search._pair_search
    takes them: "lift_needed" is the smallest A-frame height at which helpers.evaluate_line passes the line on
    the terrain with the zone X (just above it the line passes, just below it fails), at most H for every line
    found; "lift_no_zone" the same without a zone, which may exceed H; both 0 for the lines valid at 0 / 0."""
    model = case[0]
    z, surface, anchors, *_ = canyon_of()
    table = table_of(model)
    delta = sh.end_delta(table)
    eps = 1e-6

    def passes(a1, a2, end_zone, lift):
        return sh.evaluate_line(a1, a2, z, 1.0, None, table, end_zone=end_zone, lift=lift)[3] > 0

    plain = set(pairs(search(case, (0.0, 0.0, 0.0))))
    above = 0
    for end_zone, lift in ((10.0, 2.0), (5.0, 1.0), (0.0, 2.0), (20.0, 0.0)):
        zones = (0.0, end_zone) if end_zone else (0.0,)
        found = search(case, (end_zone, lift, 0.0), zones=zones)
        needed, no_zone = sh.lift_values(found.columns["zone_margins"], delta, lift)
        assert len(found) > 50 and np.all(needed <= lift) and np.all(needed >= 0) and np.all(no_zone >= needed)
        assert not np.any(np.signbit(needed)) and not np.any(np.signbit(no_zone))  # 0.0, never -0.0
        above += int(np.sum(no_zone > lift))
        for k, (a1, a2) in enumerate(pairs(found)):
            if (a1, a2) in plain:
                assert needed[k] == no_zone[k] == 0.0, (a1, a2)
            if k % 3:  # a third of the lines against the brute force (seconds)
                continue
            a1, a2 = np.array(a1), np.array(a2)
            for value, zone in ((needed[k], end_zone), (no_zone[k], 0.0)):
                assert passes(a1, a2, zone, value + eps), (a1, a2, zone, value)
                if value > eps:
                    assert not passes(a1, a2, zone, value - eps), (a1, a2, zone, value)
    assert above  # some lines need the zone: without it they would need more than the A-frames


@pytest.mark.parametrize("case", [CASES[0], CASES[2]], ids=["formula", "sag"])
@pytest.mark.parametrize("rule, zones", [((10.0, 1.0, 0.0), ZONES), ((5.0, 2.0, 0.0), (0.0, 5.0))])
def test_count_mode_with_a_zone(case, rule, zones):
    """The sink (count) mode gives the lines of the table mode at a zone and a lift, every column; with
    the ladder search._pair_search passes ((0, zone)) each part's lines get the A-frame heights of the
    table's (helpers.lift_values of their buckets, per line)."""
    parts = []
    assert search(case, rule, zones=zones, sink=parts.append) is None
    joined = sh.LineTable.concat(parts)
    table = search(case, rule, zones=zones)
    order = np.lexsort((joined.columns["a2"][:, 1], joined.columns["a2"][:, 0], joined.columns["a1"][:, 1],
                        joined.columns["a1"][:, 0]))
    expected = np.lexsort((table.columns["a2"][:, 1], table.columns["a2"][:, 0], table.columns["a1"][:, 1],
                           table.columns["a1"][:, 0]))
    assert len(joined) == len(table) > 50 and set(joined.columns) == set(table.columns)
    for name in table.columns:
        assert np.array_equal(joined.columns[name][order], table.columns[name][expected], equal_nan=True), name
    if len(zones) == 2:
        delta = sh.end_delta(table_of(case[0]))
        per_part = [sh.lift_values(p.columns["zone_margins"], delta, rule[1]) for p in parts]
        mine = [np.concatenate([v[i] for v in per_part])[order] for i in (0, 1)]
        theirs = [v[expected] for v in sh.lift_values(table.columns["zone_margins"], delta, rule[1])]
        assert all(np.array_equal(a, b) for a, b in zip(mine, theirs))
        assert (theirs[0] > 0).any() and (theirs[1] > theirs[0]).any()


def test_independent_of_threads():
    """A search at a zone and a lift gives the same table (==, in the same order) with any number of threads."""
    import numba
    most = numba.config.NUMBA_NUM_THREADS
    results = []
    try:
        for threads in sorted({1, min(3, most), most}):
            numba.set_num_threads(threads)
            results.append(search(CASES[3], (20.0, 2.0, 0.0), zones=ZONES, threads=threads).columns)
    finally:
        numba.set_num_threads(most)
    assert len(results[0]["a1"]) > 100
    for other in results[1:]:
        assert other.keys() == results[0].keys()
        for name in other:
            assert np.array_equal(other[name], results[0][name], equal_nan=True), name


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_heights_include_the_lift(model):
    """The webbing on A-frames of h metres stands h higher: height_max, height_mean and high_pct of
    helpers.evaluate_line and a profile's "max_height" at a lift are the values at lift 0 plus the lift
    (high_pct: the share at high_above - h at lift 0, within one pixel), the zone leaving them alone;
    linesearch.evaluate_lines gives evaluate_line's heights (==) at the lift; at lift 0 webbing_height
    adds nothing (the values of before, bit for bit)."""
    z, surface, anchors, *_ = canyon_of()
    table = table_of(model)
    rng = np.random.default_rng(11)
    found = rng.integers(0, len(anchors), (400, 2))
    found = found[found[:, 0] != found[:, 1]]
    lift, high = 2.0, 12.0
    rule = dict(high_above=high, end_zone=5.0)
    seen = 0
    for i, j in found.tolist():
        base = sh.evaluate_line(anchors[i], anchors[j], z, 1.0, None, table, **rule)
        if base is None or not np.isfinite(base[5]):
            continue
        up = sh.evaluate_line(anchors[i], anchors[j], z, 1.0, None, table, lift=lift, **rule)
        low = sh.evaluate_line(anchors[i], anchors[j], z, 1.0, None, table, high_above=high - lift, end_zone=5.0)
        seen += 1
        assert up[5] == base[5] + lift  # max(a + h) == max(a) + h: rounding is monotone
        assert math.isclose(up[6], base[6] + lift, abs_tol=1e-9)
        steps = int(np.abs(anchors[i] - anchors[j]).max())
        assert abs(up[7] - low[7]) <= 100.0 / (steps - 1) + 1e-9
        profile = sh.line_profile(tuple(anchors[i]), tuple(anchors[j]), z, 1.0, sag_table=table, end_zone=5.0,
                                  lift=lift)
        before = sh.line_profile(tuple(anchors[i]), tuple(anchors[j]), z, 1.0, sag_table=table, end_zone=5.0)
        assert profile["max_height"][0] == before["max_height"][0]
        assert abs(profile["max_height"][1] - before["max_height"][1] - lift) < 0.0101
    assert seen > 100
    # the numba evaluation: evaluate_line's heights (==) at the lift, for every line it keeps
    lifted = ls.evaluate_lines(found, anchors, z, 1.0, None, table, None, lift=lift, **rule)
    assert len(lifted.columns["a1"]) > 10
    for k, (a1, a2) in enumerate(zip(lifted.columns["a1"].tolist(), lifted.columns["a2"].tolist())):
        up = sh.evaluate_line(np.array(a1), np.array(a2), z, 1.0, None, table, lift=lift, **rule)
        got = [float(lifted.columns[name][k]) for name in ("height_max", "height_mean", "high_pct")]
        assert got == list(up[5:8]), (a1, a2)
    # at lift 0 nothing is added: margin + fall allowance as before
    margin = np.array([-0.0, 1.5, -6.0, np.nan])
    assert np.array_equal(sh.webbing_height(margin, table), margin + sh.fall_allowance(table), equal_nan=True)
    assert np.array_equal(sh.webbing_height(margin, table, lift), margin + sh.fall_allowance(table) + lift,
                          equal_nan=True)


def test_zone_steps():
    """helpers.zone_steps and its numba twin agree; the zone's steps and the cap for short lines; the
    rings' offsets (the zone uncapped)."""
    assert sh.zone_steps(100, 100.0, 0.0) == 0
    assert sh.zone_steps(100, 100.0, 5.0) == 5  # steps 1-4 (1-4 m) of each end
    assert sh.zone_steps(100, 100 * 2 ** 0.5, 5.0) == 4  # diagonal: 1.41, 2.83, 4.24 m
    assert sh.zone_steps(30, 30.0, 20.0) == 8  # capped at 7.5 m: steps 1-7
    offsets = sh.zone_offsets(30, 30.0, 20.0, 1.0, 6.0)
    assert (offsets == 7.0).sum() == 14 and (offsets[:7] == 7.0).all() and (offsets[7:22] == 1.0).all()
    assert (sh.zone_offsets(30, 30.0, 20.0, 0.0, 6.0, 0.5) == 6.0).sum() == 28  # cap 0.5: all but the middle
    assert (sh.zone_offsets(30, 30.0, 0.0, 0.0, 6.0) == 0.0).all()
    rng = np.random.default_rng(3)
    for _ in range(20000):
        steps = int(rng.integers(2, 3000))
        length = steps * float(rng.choice([1.0, 2 ** 0.5, 1 + rng.random() * 0.42])) * float(rng.choice([0.5, 1, 2]))
        end_zone = float(rng.choice([0.0, 5.0, 10.0, 20.0, rng.random() * 50, length / 4]))
        cap = float(rng.choice([0.25, 0.5, 0.0, rng.random() * 0.5]))
        assert sh.zone_steps(steps, length, end_zone, cap) == ls._zone_steps(steps, length, end_zone, cap)
    assert ls.ring_offsets(6.0, 1.0, 10, 5.0, 1.0, 6.0).tolist() == [6.0] + [-1.0] * 5 + [5.0] * 5
    assert ls.ring_offsets(6.0, 1.0, 4).tolist() == [6.0] * 5
    # the bucket columns of a ladder: [0, 5), [5, 10), [10, 20), the core
    columns = sh.zone_columns(100, 100.0, np.array(ZONES))
    assert columns[:4].tolist() == [0] * 4 and columns[4:9].tolist() == [1] * 5 and columns[9:19].tolist() == [2] * 10
    assert (columns[19:80] == 3).all() and columns[-4:].tolist() == [0] * 4


def test_refusals():
    """A negative lift or end zone, an end clearance below 0 or above the fall allowance, a zone cap
    outside 0 .. 0.5 or a ladder not ascending from 0 are refused where the arguments enter."""
    z, surface, anchors, *_ = canyon()
    bad = [dict(lift=-1.0), dict(end_zone=-1.0), dict(end_clearance=-0.5), dict(end_clearance=6.5),
           dict(zone_cap=0.6), dict(lift=float("nan"))]
    calls = [lambda **k: ls.find_valid_lines(z, None, anchors, 1.0, 20, 120, **k),
             lambda **k: ls.evaluate_lines(np.array([[0, 1]]), anchors, z, 1.0, None, None, None, **k),
             lambda **k: sh.evaluate_line(anchors[0], anchors[1], z, 1.0, **k),
             lambda **k: sh.line_profile(tuple(anchors[0]), tuple(anchors[1]), z, 1.0, **k),
             lambda **k: lp.line_profiles(anchors[:1], anchors[1:2], z, 1.0, **k)]
    for call in calls:
        for kwargs in bad:
            with pytest.raises(ValueError):
                call(**kwargs)
    for zones in ((5.0, 10.0), (0.0, 10.0, 5.0)):
        with pytest.raises(ValueError):
            ls.find_valid_lines(z, None, anchors, 1.0, 20, 120, zones=zones)
        with pytest.raises(ValueError):
            sh.evaluate_line(anchors[0], anchors[1], z, 1.0, zones=zones)
    # the sag model's fall zone is the bound of the end clearance
    table = sag.EnvelopeTable(sag.Rigging(), 20, 120)
    fall = sh.fall_allowance(table)
    assert sh.end_delta(table, fall) == 0.0 and sh.end_delta(None) == sh.LEASH_FALL
    with pytest.raises(ValueError):
        sh.end_delta(table, fall + 0.1)
