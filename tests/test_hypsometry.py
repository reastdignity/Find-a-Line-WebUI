"""The terrain statistics of a search area (hypsometry.py): which pixels count, the histogram's
independence of blocks and windows, the quantile rule, the saved files, and where the
statistics go (run.json, the headers of data.js and lines.js, not runs.js)."""

import json
import math

import numpy as np
import pytest

import hypsometry as hy
from sources import filling


def _reference(values, res=1.0):
    """The statistics of these heights by sorting, written apart from hypsometry.statistics."""
    cm = [int(np.rint(np.float64(v) * 100)) for v in values]
    bins = sorted(min(max((c - hy.LOW_CM) // hy.BIN_CM, 0), hy.BINS - 1) for c in cm)
    n = len(bins)
    quantiles = [round((hy.LOW_CM + bins[max(1, math.ceil(p * n / 100)) - 1] * hy.BIN_CM) / 100, 1)
                 for p in range(101)]
    return {"mean": round(sum(cm) / n / 100, 2), "quantiles": quantiles, "km2": round(n * res ** 2 / 1e6, 4)}


def test_pixels_counted():
    """NaN, pixels outside the area, lakes with data and the sea zone at about sea level are left
    out; the sea zone higher up (a cliff's edge) counts; heights beyond the bins go into the end bins."""
    z = np.array([[100.0, np.nan, 200.0, 300.0],
                  [0.5, 5.0, 400.0, -2000.0],
                  [20000.0, 50.0, 60.0, 70.0]], np.float32)
    mask = np.ones(z.shape, bool)
    mask[2, 3] = False  # outside the area
    wbm = np.zeros(z.shape, np.uint8)
    wbm[0, 3] = filling.LAKE  # a lake with data
    wbm[2, 2] = filling.OCEAN  # the mask's ocean alone does not make water
    sea_zone = np.zeros(z.shape, bool)
    sea_zone[1, :2] = True  # 0.5 m: water, 5 m: land
    h = hy.land_histogram(z, mask, wbm, sea_zone)
    kept = [100.0, 200.0, 5.0, 400.0, -2000.0, 20000.0, 50.0, 60.0]
    assert h.n == len(kept) and h.sum_cm == round(sum(kept) * 100)
    assert h.counts[0] == 1 and h.counts[-1] == 1  # -2000 m and 20 000 m clipped
    assert hy.statistics(h, 2.0) == _reference(kept, 2.0)
    # without masks every finite pixel of the area counts
    assert hy.land_histogram(z, mask).n == len(kept) + 2  # the lake and the sea at 0.5 m too
    # a float32 height in centimetres through float64, as round(e, 2) of the saved anchors
    assert hy.land_histogram(np.array([[0.29]], np.float32), np.ones((1, 1), bool)).sum_cm == 29


def test_blocks_and_windows():
    """The histogram does not depend on the size of its row blocks, and the windows of a partition
    of the grid add up to the whole grid's, in any order."""
    rng = np.random.default_rng(1)
    z = (rng.random((57, 43)) * 3000 - 50).astype(np.float32)
    z[rng.random(z.shape) < 0.1] = np.nan
    mask = rng.random(z.shape) < 0.8
    wbm = np.where(rng.random(z.shape) < 0.05, filling.LAKE, 0).astype(np.uint8)
    sea_zone = rng.random(z.shape) < 0.2
    z[sea_zone & (rng.random(z.shape) < 0.5)] = 0.3
    whole = hy.land_histogram(z, mask, wbm, sea_zone)
    for block_px in (1, 43, 100, 10 ** 6):
        h = hy.land_histogram(z, mask, wbm, sea_zone, block_px=block_px)
        assert np.array_equal(h.counts, whole.counts) and h.sum_cm == whole.sum_cm
    windows = [(slice(r0, r1), slice(c0, c1)) for r0, r1 in ((0, 20), (20, 21), (21, 57))
               for c0, c1 in ((0, 13), (13, 43))]
    for order in (windows, windows[::-1]):
        total = hy.Histogram.empty()
        for window in order:
            total = total + hy.land_histogram(z, mask, wbm, sea_zone, window, block_px=50)
        assert np.array_equal(total.counts, whole.counts) and total.sum_cm == whole.sum_cm
    assert hy.statistics(whole, 1.0) == _reference(z[mask & np.isfinite(z) & ~(
        (wbm == filling.LAKE) | (sea_zone & (z <= filling.SEA_LEVEL_TOLERANCE)))])


def test_quantiles_with_a_plateau():
    """Known data: a plateau holding most pixels, a few heights below and above; each quantile is the
    lower edge of the bin where the cumulative count reaches ceil(p n / 100)."""
    values = [812.34] * 70 + [400.05, 400.09, 1287.0] + [950.5] * 27 + [-3.21]
    z = np.array(values, np.float32).reshape(1, -1)
    terrain = hy.statistics(hy.land_histogram(z, np.ones(z.shape, bool)), 5.0)
    assert terrain == _reference(np.asarray(values, np.float32), 5.0)
    q = terrain["quantiles"]
    assert len(q) == 101 and q == sorted(q)
    assert (q[0], q[1], q[2], q[3], q[50], q[99], q[100]) == (-3.3, 400.0, 400.0, 812.3, 812.3, 950.5, 1287.0)
    assert terrain["km2"] == round(101 * 25 / 1e6, 4) and list(terrain) == ["mean", "quantiles", "km2"]
    assert all(type(v) is float for v in q) and type(terrain["mean"]) is float
    json.dumps(terrain)  # plain Python values
    one = hy.statistics(hy.land_histogram(np.array([[7.0]], np.float32), np.ones((1, 1), bool)), 1.0)
    assert one["quantiles"] == [7.0] * 101 and one["mean"] == 7.0


def test_no_land():
    assert hy.statistics(None, 1.0) is None
    assert hy.statistics(hy.Histogram.empty(), 1.0) is None
    z = np.full((3, 3), np.nan, np.float32)
    assert hy.statistics(hy.land_histogram(z, np.ones(z.shape, bool)), 1.0) is None


def test_save_and_load(tmp_path):
    z = np.array([[100.0, 101.25, -5.0, 2500.0]], np.float32)
    h = hy.land_histogram(z, np.ones(z.shape, bool))
    path = str(tmp_path / "0.terrain.npz")
    hy.save(path, h)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["0.terrain.npz"]  # no .part left
    loaded = hy.load(path)
    assert np.array_equal(loaded.counts, h.counts) and loaded.sum_cm == h.sum_cm and loaded.counts.dtype == np.int64
    with np.load(path, allow_pickle=False) as f:
        assert len(f["counts"]) == (2500 - -5) * 10 + 1  # trimmed to the bins used
    empty = str(tmp_path / "1.terrain.npz")
    hy.save(empty, hy.Histogram.empty())
    assert hy.load(empty).n == 0
    assert hy.load(str(tmp_path / "missing.terrain.npz")) is None
    big = hy.Histogram(h.counts.copy(), 2 ** 70)  # the sum stays exact
    hy.save(path, big)
    assert hy.load(path).sum_cm == 2 ** 70
    with np.load(path, allow_pickle=False) as f:
        other = {k: f[k] for k in f.files}
    other["bin_cm"] = np.int64(20)
    with open(path, "wb") as f:
        np.savez(f, **other)
    assert hy.load(path) is None


def test_water_with_data_is_fill_waters_rule(tmp_path):
    """fill_water's saved water mask, on the pixels that had data, is water_with_data."""
    from grid import Grid
    rng = np.random.default_rng(3)
    z = (rng.random((40, 50)) * 30 - 2).astype(np.float32)
    z[:, :10] = np.nan  # the sea without data
    z[:, 10:14] = rng.choice([0.2, 0.9, 1.0, 1.1, 4.0], (40, 4))  # the shore, about sea level and above
    z[5:9, 30:35] = np.nan  # a lake without data
    z[20:24, 30:35] = 3.0  # a lake measured
    z[30:32, 40:42] = np.nan  # a gap on land
    wbm = np.zeros(z.shape, np.uint8)
    wbm[:, :12] = filling.OCEAN
    wbm[4:10, 29:36] = filling.LAKE
    wbm[20:24, 30:35] = filling.LAKE
    sea_zone = np.zeros(z.shape, bool)
    sea_zone[:, :16] = True
    path = str(tmp_path / "nmt.npy")
    np.save(path, z)
    grid = Grid(500000.0, 300000.0, 1.0, z.shape[0], z.shape[1], "EPSG:2180")
    water = np.load(filling.fill_water(path, None, grid, wbm, sea_zone, str(tmp_path / "water.npy")))
    rule = filling.water_with_data(z, wbm, sea_zone)
    assert np.array_equal(water & np.isfinite(z), rule)
    assert rule[:, 10:14].any() and not rule[:, 10:14].all() and rule[20:24, 30:35].all()
    assert not filling.water_with_data(z, None, None).any()
    # A provider's constant over the sea (Source.sea_fill, 1.30 m in Schleswig-Holstein): water within
    # SEA_FILL_EPS of it in the sea zone, in fill_water's mask and out of the statistics alike
    z[:, 10:14] = rng.choice([0.2, 1.3, 1.304, 1.31, 4.0], (40, 4))
    np.save(path, z)
    water = np.load(filling.fill_water(path, None, grid, wbm, sea_zone, str(tmp_path / "water.npy"), sea_value=1.3))
    rule = filling.water_with_data(z, wbm, sea_zone, 1.3)
    assert np.array_equal(water & np.isfinite(z), rule)
    extra = rule & ~filling.water_with_data(z, wbm, sea_zone)
    band = z[:, 10:14]
    assert np.array_equal(extra[:, 10:14], (band == np.float32(1.3)) | (band == np.float32(1.304)))
    mask = np.ones(z.shape, bool)
    assert hy.land_histogram(z, mask, wbm, sea_zone, sea_value=1.3).n == \
        hy.land_histogram(z, mask, wbm, sea_zone).n - int(extra.sum())


def test_terrain_in_the_map_and_not_in_runs_js(tmp_path):
    """The terrain goes into the headers of data.js and lines.js (right before "lines"); runs.js
    leaves it out."""
    from shapely.geometry import Point
    import helpers as sh
    import mapping as mp
    import runs as rn

    class Area:
        center = (50.0, 19.1)

        @staticmethod
        def shape_wgs84():
            return Point(19.1, 50.0).buffer(0.01)

    terrain = {"mean": 803.0, "quantiles": [float(p) for p in range(101)], "km2": 12.34}
    for value in (terrain, None):
        run = {"id": "r", "name": "Test", "created": "2026-11-03T10:00:00+00:00", "terrain": value}
        mp.save_map(sh.LineTable({"length": np.zeros(0)}), Area, str(tmp_path), str(tmp_path / "runs"), run,
                    "EPSG:2180")
        for name in ("data.js", "lines.js"):
            text = (tmp_path / name).read_text(encoding="utf-8")
            head = json.loads(text[text.index("= {") + 2:].rstrip().rstrip(";"))
            assert head["terrain"] == value and list(head)[-2:] == ["terrain", "lines"], name
        assert list(json.loads((tmp_path / "lines.js").read_text(encoding="utf-8").partition("] = ")[2]
                               .rstrip().rstrip(";"))) == ["crs", "area", "terrain", "lines"]
    meta = {"id": "r", "name": "Test", "summary": {"lines": 0}, "terrain": terrain}
    assert "terrain" not in rn._listed(meta)


@pytest.mark.parametrize("width", [1, 7])
def test_core_window(width):
    """The windows of a tiled search's cores split the grid's pixels by their centres, half-open."""
    import search
    from grid import Grid
    grid = Grid(100.0, 200.0, 2.0, 10, width, "EPSG:2180")
    left, bottom, right, top = grid.bounds
    cores = [(left, bottom, left + 4, top), (left + 4, bottom, right, top - 7), (left + 4, top - 7, right, top)]
    seen = np.zeros((grid.height, grid.width), int)
    for core in cores:
        rows, cols = search._core_window(grid, core)
        seen[rows, cols] += 1
    assert (seen == 1).all()
