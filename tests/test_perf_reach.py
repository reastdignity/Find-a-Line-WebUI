"""tools/perf_reach.py: the numpy and numba engines of the reach of a fixed anchor against helpers.evaluate_line
and the search itself, the answer's encoding, the representatives of a point, and the patch of the Żabi Koń clip
rebuilt as search.patch_of_line builds it, offline."""

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import perf_reach as pr  # noqa: E402
import sag  # noqa: E402

# The canyon's west rim at some rows (terrain() below): an anchor just above the cliff
CLIFFS = tuple((r, int(35 + 6 * np.sin(r / 11)) - 9) for r in range(8, 64, 4))
LIMITS = {"min_length": 8.0, "max_length": 40.0, "max_dh_ratio": 0.3, "max_dh": 30.0}


def terrain(seed=5, size=70):
    """A winding canyon between two plateaus (float32, as the search's grids), with a patch of no data, and a
    surface model with scattered trees: lines across it are valid or not, some of them over trees."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    centre = size / 2 + 6 * np.sin(y / 11)
    z = np.where(np.abs(x - centre) < 8, 20.0 + 0.5 * np.abs(x - centre), 60.0)   # a canyon with cliffs
    z += 2 * np.sin(x / 5) * np.cos(y / 7) + rng.normal(0, 0.3, z.shape)
    z[5:9, 56:60] = np.nan  # no data
    trees = np.where(rng.random(z.shape) < 0.2, rng.uniform(5, 45, z.shape), 0.0)
    return z.astype(np.float32), (z + trees).astype(np.float32)


@pytest.fixture(scope="module")
def grids():
    return terrain()


@pytest.fixture(scope="module")
def sag_table():
    return sag.EnvelopeTable(sag.Rigging(), LIMITS["min_length"], LIMITS["max_length"])


def _same(a, b, valid_only=False):
    on = None if not valid_only else b.valid
    diff = pr.compare(a, b, on)
    assert diff["valid_differs"] == 0 and diff["trees_differs"] == 0, diff
    assert diff["max_clearance_diff"] < 1e-9 and diff["max_clearance_nmpt_diff"] < 1e-9, diff
    return diff


@pytest.mark.parametrize("mode,table", [("mark", False), ("reject", False), (None, False), ("mark", True)])
def test_engines_equal_evaluate_line(grids, sag_table, mode, table):
    """Both engines give helpers.evaluate_line's decision and clearances for every target, for the fixed anchor
    in the middle, at a corner and on an edge (the pair's direction is the search's: the lower [row, col] first)."""
    z, s = grids
    s = None if mode is None else s
    sag_t = sag_table if table else None
    valid_total = trees_total = 0
    for fixed in CLIFFS + ((35, 35), (0, 0), (69, 12), (30, 69)):
        targets = pr.candidate_targets(z, 1.0, fixed, 1, **LIMITS)
        assert len(targets) > 100
        args = (z, s, 1.0, fixed, targets.rows, targets.cols, mode, sag_t)
        reference = pr.evaluate_reference(*args)
        assert not reference.valid.all()
        valid_total += int(reference.valid.sum())
        trees_total += int(reference.trees.sum())
        _same(pr.evaluate_numpy(*args), reference)
        _same(pr.evaluate_numba(*args), reference, valid_only=True)
        assert (pr.evaluate_numba(*args).valid == reference.valid).all()
        small = pr.evaluate_numpy(*args[:-2], mode, sag_t, elements=2000)  # many small batches, the same values
        _same(small, reference)
    assert valid_total > 5   # a mix of valid and invalid lines, so the comparison means something
    assert (trees_total > 0) == (mode == "mark")


def test_numba_in_parts_and_threads(grids):
    z, s = grids
    targets = pr.candidate_targets(z, 1.0, (30, 30), 1, **LIMITS)
    args = (z, s, 1.0, (30, 30), targets.rows, targets.cols, "mark", None)
    whole = pr.evaluate_numba(*args)
    _same(pr.evaluate_numba(*args, threads=1, part=777), whole)
    _same(pr.evaluate_numba(*args, threads=2, part=123), whole)


def test_direction_is_the_searches():
    rows, cols = np.array([3, 5, 5, 7]), np.array([9, 4, 6, 1])
    assert pr.forward((5, 5), rows, cols).tolist() == [False, False, True, True]


def test_targets_obey_the_pair_search_limits():
    z = np.zeros((20, 20), dtype=np.float32)
    z[10, 14] = 3.0   # 4 px away, 3 m higher
    z[2, 2] = np.nan
    targets = pr.candidate_targets(z, 2.0, (10, 10), 1, 5.0, 12.0, 0.5, 2.0)
    pixels = set(zip(targets.rows.tolist(), targets.cols.tolist()))
    assert (10, 14) not in pixels                    # 3 m higher than allowed by max_dh 2
    assert (10, 11) not in pixels                    # 2 m: shorter than min_length 5
    assert (10, 13) in pixels and (10, 16) in pixels  # 6 m and 12 m: both limits are inclusive
    assert (10, 17) not in pixels and (2, 2) not in pixels   # 14 m; no data
    assert (10, 10) not in pixels
    coarse = pr.candidate_targets(z, 2.0, (10, 10), 4, 5.0, 12.0, 0.5, 2.0)
    assert set(zip(coarse.rows.tolist(), coarse.cols.tolist())) <= pixels
    assert (coarse.rows % 4 == 0).all() and (coarse.cols % 4 == 0).all()
    assert coarse.shape == (5, 5) and (coarse.flat == (coarse.rows // 4) * 5 + coarse.cols // 4).all()


def test_valid_is_what_the_search_finds():
    """linesearch.find_valid_lines on a grid whose anchors are all its pixels finds exactly the valid targets
    of a fixed anchor (the length and height tests, the pair's direction and the final decision), for anchors on
    the canyon's west rim (the fixed anchor first of its pairs) and east rim (second)."""
    z, s = terrain(seed=2)
    west = [(r, int(35 + 6 * np.sin(r / 11)) - 9) for r in (20, 32, 44)]
    east = [(r, int(35 + 6 * np.sin(r / 11)) + 9) for r in (28, 40)]
    checked = 0
    for fixed in west + east:
        out = pr.check_search(z, s, 1.0, fixed, LIMITS, "mark")
        assert out["only_search"] == 0 and out["only_ours"] == 0, out
        checked += out["valid"]
    assert checked > 5


def test_mask_encoding_round_trips(grids):
    z, s = grids
    targets = pr.candidate_targets(z, 1.0, (35, 35), 2, **LIMITS)
    ev = pr.evaluate_numpy(z, s, 1.0, (35, 35), targets.rows, targets.cols, "mark")
    mask = pr.encode_mask(targets, ev)
    assert mask.dtype == np.uint8 and mask.shape == targets.shape
    valid, upper, trees = pr.decode_mask(mask)
    at = targets.flat
    assert (valid.ravel()[at] == ev.valid).all() and valid.sum() == ev.valid.sum()
    assert (trees.ravel()[at] == ev.trees).all()
    clearance, bound = ev.clearance[ev.valid], upper.ravel()[at][ev.valid]
    below = clearance <= 127 * pr.MASK_STEP_M
    assert (bound[below] >= clearance[below]).all() and (bound[below] - clearance[below] < pr.MASK_STEP_M + 1e-9).all()
    assert (bound[~below] == 127 * pr.MASK_STEP_M).all()
    assert pr.mask_bytes(mask) < mask.size
    # The ends: a barely valid line is 1, a very clear one is capped at 127, the high bit is the trees
    one = pr.Targets(1, (1, 3), np.array([0, 1, 2]), np.zeros(3, int), np.arange(3))
    made = pr.Evaluation(np.array([True, True, False]), np.array([0.01, 90.0, np.nan]),
                         np.array([5.0, -1.0, np.nan]), np.array([False, True, False]))
    assert pr.encode_mask(one, made).ravel().tolist() == [1, 255, 0]


def test_sector_representatives():
    # Sectors of 15 degrees: targets 0 and 1 in the first, 2 in the fifth, 3 and 4 (equal values) in the sixth, 5 in the twelfth
    dx = np.array([10.0, 20.0, 5.0, 1.0, 2.0, -9.0])
    dy = np.array([1.0, 2.0, 9.0, 10.0, 20.0, 0.5])
    value = np.array([3.0, 7.0, 1.0, 2.0, 2.0, 4.0])
    chosen = pr.sector_representatives(dx, dy, value)
    assert sorted(chosen.tolist()) == [1, 2, 3, 5]   # the greater of 3 and 7; alone; the first of equal values; alone
    assert len(pr.sector_representatives(np.zeros(0), np.zeros(0), np.zeros(0))) == 0


def test_spot_representatives():
    # Targets 3 m apart in a row (distance 4): the best takes its neighbours, the farthest one is a spot of its own
    x = np.array([0.0, 3.0, 6.0, 9.0, 40.0, 41.0])
    y = np.zeros(6)
    clearance = np.array([1.0, 5.0, 2.0, 1.5, 3.0, 4.0])
    length = np.array([50.0, 50.0, 50.0, 50.0, 60.0, 60.0])
    over = np.zeros(6, dtype=bool)
    reps = pr.spot_representatives(x, y, clearance, length, over, 4.0)
    # 1 (clearance 5) takes 0 and 2 (within 4 m); 3 (9 m) is 3 m from 2 (taken) and 6 m from 1: its own; 5 takes 4
    assert sorted(reps.tolist()) == [1, 3, 5]
    assert pr.spot_representatives(x, y, clearance, length, over, 4.0, "longest").tolist()[0] == 5  # longest, then clearance
    # Lines over trees never join a clear one, however close
    over[2] = True
    reps = pr.spot_representatives(x, y, clearance, length, over, 4.0)
    assert sorted(reps.tolist()) == [1, 2, 3, 5]
    assert len(pr.spot_representatives(x[:0], y[:0], clearance[:0], length[:0], over[:0], 4.0)) == 0
    # The limit is inclusive, like the result's grouping (dx*dx + dy*dy <= d2)
    assert len(pr.spot_representatives(np.array([0.0, 4.0]), np.zeros(2), np.array([2.0, 1.0]),
                                       np.array([5.0, 5.0]), np.zeros(2, dtype=bool), 4.0)) == 1


# --- The clip's patch ----------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    out = tmp_path_factory.mktemp("reach")
    data = pr.case_data_folder(str(out), "clip", None)
    meta = pr.make_clip_run(data)
    a1, a2, _ = pr.longest_line(os.path.join(data, "runs", meta["id"]))  # a line the search found
    return out, data, meta, a1, a2


def test_patch_is_patch_of_lines_square(clip):
    """build_patch's grid and anchors are the patch search.patch_of_line gives; the surface follows the rule."""
    import search
    out, data, meta, a1, a2 = clip
    patch = pr.build_patch(meta, data, str(out / "work" / "a"), a1, a2, side_m=pr.CLIP_SIDE_M)
    try:
        paths = search.Paths(data, str(out / "work" / "b"))
        os.makedirs(paths.work)
        reference, _ = search.patch_of_line(meta, paths, a1, a2, side_m=pr.CLIP_SIDE_M)
        assert (patch.size, patch.left, patch.top, patch.res) == (reference["width"], reference["left"], reference["top"],
                                                                  reference["res"])
        assert patch.z.shape == (513, 513) and patch.s is None and patch.nmpt_mode is None
        h = [float(patch.z[r, c]) for r, c in patch.anchors]
        assert [round(v, 2) for v in h] == [a["h"] for a in reference["anchors"]]
        assert patch.step1_seconds > 0 and patch.sag_table is not None
        assert patch.pixel(*a1) == patch.anchors[0] and patch.pixel(*a2) == patch.anchors[1]
        lat, lon, n = pr.busiest_anchor(os.path.join(data, "runs", meta["id"]))
        r, c = patch.pixel(lat, lon)
        assert n > 0 and 0 <= r < patch.size and 0 <= c < patch.size
        # A lattice of 4 on the clip: both engines equal the line-by-line evaluation on a sample
        fixed = patch.anchors[0]
        targets, ev = pr.reach(patch, fixed, 4, "numpy")
        assert len(targets) > 1000 and ev.valid.any()
        report = pr.check(patch, fixed, targets, ev)
        assert report["numpy"]["valid_differs"] == 0 and report["numba_valid_flags"] == 0
        assert report["numpy"]["max_clearance_diff"] < 1e-9 and report["numba"]["max_clearance_diff"] < 1e-9
        by_numba = pr.reach(patch, fixed, 4, "numba")[1]
        assert (by_numba.valid == ev.valid).all()
        counts = pr.representative_counts(patch, fixed, targets, ev)
        assert counts["valid"] == int(ev.valid.sum())
        assert 0 < counts["all"]["spots"] <= counts["valid"] and 0 < counts["all"]["longest"] <= 24
        assert len(pr.steep_points(patch)) == pr.OTHER_POINTS
    finally:
        patch.close()
