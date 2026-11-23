"""tools/perf_access.py (the access grid's memory and seconds, run by hand): its counts on made-up masks whose answers
are known by construction (the pieces strip by strip, the shares of heights, area and blocks, the pixels that differ),
the three ways of keeping a mask giving equal windows, the parts of a stage from samples, the readers of a cgroup and
of /proc, and the commands `stages` and `pieces` on a small made-up search (offline): the keys of their JSON, the grid
in blocks equal to the grid at once, the work folder removed. The tool may hook private functions of access.py for
its split; this test relies only on access.access_grid, access.block_grid and access._answers (the build of the task
"An access grid that needs less memory" renames none of them), so no assertion here needs a hook."""

import hashlib
import json
import os
import sys

import numpy as np
import pytest
from scipy import ndimage

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import perf_access as pa  # noqa: E402

LEFT, TOP, RES, SIZE = 500000.0, 300000.0, 5.0, 400  # the made-up search: EPSG:2180, 5 m pixels, 2 km


def test_strip_pieces_by_construction():
    """Strips of 64 rows (0-63, 64-127, 128-191, 192-199): a bar through all four (4 pieces, 1 region), two lone
    pixels, a run crossing the first seam (2 pieces) and a diagonal pair across it (2 pieces, 1 region)."""
    m = np.zeros((200, 50), bool)
    m[:, 5] = True
    m[10, 20] = m[10, 30] = True
    m[60:70, 40] = True
    m[63, 45] = m[64, 46] = True
    rows = list(pa.strips(200, 50, strip_px=1))
    assert rows == [(0, 64), (64, 128), (128, 192), (192, 200)]
    got = pa.strip_pieces(m, rows)
    # strip 1: bar, 2 lone, run, diagonal's top = 5; last row 63: bar, run, diagonal = 3 labels
    assert got == {"pieces": 5 + 3 + 1 + 1, "most_in_a_strip": 5, "most_in_a_last_row": 3, "strips": 4}
    assert ndimage.label(m, structure=np.ones((3, 3), bool))[1] == 5  # the regions of the whole mask
    assert pa.strip_pieces(np.zeros((70, 9), bool), list(pa.strips(70, 9, 1)))["pieces"] == 0
    full = pa.strip_pieces(np.ones((130, 9), bool), list(pa.strips(130, 9, 1)))
    assert full == {"pieces": 3, "most_in_a_strip": 1, "most_in_a_last_row": 1, "strips": 3}


def test_shares_of_heights_area_and_blocks():
    """Heights in columns 30-39 of rows 0-99 of a 130 x 100 grid; strips of 64 rows with a halo of 16 rows and
    columns: the first two strips' span 14-55 (42 % of the width), the last strip (rows 128-129, its halo from 112)
    none."""
    z = np.full((130, 100), np.nan, np.float32)
    z[:100, 30:40] = 1.0
    mask = np.zeros((130, 100), bool)
    mask[:10, :10] = True
    rows = list(pa.strips(130, 100, 1))
    got = pa.data_shares(z, mask, rows, halo=16)
    assert got["with_heights"] == round(1000 / 13000, 4) and got["search_area"] == round(100 / 13000, 4)
    assert got["strip_width_with_heights_mean"] == round((0.42 + 0.42 + 0) / 3, 4)
    assert got["strips_without_heights"] == round(1 / 3, 4) and got["strips"] == 3
    # the land: the measure's data (not filled unless water) that is not water: columns 32-34, span 16-50
    water, filled = np.zeros(z.shape, bool), np.zeros(z.shape, bool)
    water[:100, 35:40] = True
    filled[:100, 30:32] = True
    filled[:100, 38:40] = True  # filled water stays water
    land = pa.data_shares(z, mask, rows, 16, water, filled)
    assert land["with_land"] == round(300 / 13000, 4) and land["with_heights"] == got["with_heights"]
    assert land["strip_width_with_land_mean"] == round((0.35 + 0.35 + 0) / 3, 4)
    assert land["strips_without_land"] == round(1 / 3, 4)
    z[:, 95:] = 2.0  # heights at the last column: the span clipped to the grid
    # 14..100 in the first two strips, 79..100 in the last
    assert pa.data_shares(z, None, rows, halo=16)["strip_width_with_heights_mean"] == round((0.86 * 2 + 0.21) / 3, 4)
    assert pa.blocks_holding(mask, 50) == {"block_px": 50, "blocks": 6, "holding": 1, "share": round(1 / 6, 4)}
    mask[129, 99] = True  # the corner block (rows 100-129, columns 50-99)
    assert pa.blocks_holding(mask, 50)["holding"] == 2
    assert pa.blocks_holding(mask, 200) == {"block_px": 200, "blocks": 1, "holding": 1, "share": 1.0}
    points = pa.blocks_holding_points(np.array([0, 3, 129]), np.array([0, 7, 99]), (130, 100), 50)
    assert points == {"block_px": 50, "blocks": 6, "holding": 2, "share": round(2 / 6, 4)}


def test_compare_counts_the_pixels_that_differ():
    rng = np.random.default_rng(5)
    a = rng.integers(0, 3, (300, 70)).astype(np.uint8)
    assert pa.compare_grids(a, a.copy()) == {"differ": 0, "first": [], "pixels": 21000}
    b = a.copy()
    for r, c in ((250, 3), (7, 60), (7, 2)):
        b[r, c] = (b[r, c] + 1) % 3
    got = pa.compare_grids(a, b, first=2)
    assert got["differ"] == 3 and got["first"] == [[7, 2], [7, 60]]
    with pytest.raises(ValueError):
        pa.compare_grids(a, b[:-1])


def _expected_hashes(mask: np.ndarray, block: int, margin: int) -> str:
    h, w = mask.shape
    parts = [hashlib.sha1(np.ascontiguousarray(mask[a:b, c:d]).view(np.uint8)).hexdigest()[:16]
             for a, b, c, d in pa.windows(h, w, block, margin)]
    return hashlib.sha1("".join(parts).encode()).hexdigest()[:16]


@pytest.mark.parametrize("source", ["made-up", "file"])
def test_three_ways_of_a_mask_give_its_windows(tmp_path, source):
    """memmap, bits and file, each in a child process: the windows of the block layout equal the mask's own (their
    hashes), and the bytes kept are what each way keeps."""
    h, w = 300, 257
    if source == "file":
        rng = np.random.default_rng(2)
        mask = ndimage.binary_opening(rng.random((h, w)) < 0.4)
        path = tmp_path / "mask.npy"
        np.save(path, mask)
        extra = ["--mask", str(path)]
    else:
        src = pa.MaskSource(None, (h, w))
        mask = np.concatenate([src.rows(r0, r1) for r0, r1 in pa.strips(h, w)])
        extra = ["--made-up", str(h), str(w)]
    out = pa.main(["masks", "--out", str(tmp_path / "out"), "--name", "m", "--res", "5", "--block-px", "40", *extra])
    import access
    margin = int(np.ceil((access.MARGIN_M + 6 * 5) / 5))
    assert pa.MARGIN_M() == access.MARGIN_M and out["margin_px"] == margin == access.margin_px(5.0)
    assert out["windows_equal"] and not out["first_unequal_window"]
    expected = _expected_hashes(mask, 40, margin)
    n = len(list(pa.windows(h, w, 40, margin)))
    for way, m in out["ways"].items():
        assert m["hash_of_hashes"] == expected, way
        assert m["windows"] == n and m["window_px_read"] == sum((b - a) * (d - c)
                                                                for a, b, c, d in pa.windows(h, w, 40, margin))
    assert out["ways"]["bits"]["kept_bytes"] == h * ((w + 7) // 8)
    assert out["ways"]["file"]["kept_bytes"] == h * w
    assert h * w < out["ways"]["memmap"]["kept_bytes"] <= h * w + 4096  # the .npy header
    assert json.load(open(tmp_path / "out" / "m.json"))["command"] == "masks"
    assert not os.path.exists(tmp_path / "out" / "m-masks")  # the children's files removed


def test_parts_from_samples():
    """summarise: each part's seconds, samples, longest gap, peaks above the stage's start, the work folder's files at
    its peak; a part without a sample takes the nearest one."""
    def sample(t, rss, private=None, disk=0, cg=None):
        return [t, rss, private, None, cg, 10 if cg else None, 20 if cg else None, 5 if cg else None, 1 if cg else None,
                disk]
    samples = [sample(0.5, 150, 120), sample(1.2, 300, 140, disk=7, cg=1000), sample(1.8, 200, 180, cg=900)]
    listings = [(0.1, {"a.npy": 3}), (1.1, {"a.npy": 3, "b.npy": 4})]
    parts = pa.summarise(samples, listings, [(0.0, "a"), (1.0, "b"), (1.95, "c")], 2.0, {"rss": 100, "private": 100},
                         {"current": 400})
    a, b, c = parts["a"], parts["b"], parts["c"]
    assert a["peak_rss_above_start"] == 50 and a["peak_private_above_start"] == 20 and a["samples"] == 1
    assert a["max_gap_s"] == 0.5 and a["files_at_peak"] == {"a.npy": 3}
    assert b["peak_rss_above_start"] == 200 and b["peak_private_above_start"] == 80 and b["samples"] == 2
    assert b["max_gap_s"] == 0.6 and b["files_at_peak"] == {"a.npy": 3, "b.npy": 4} and b["peak_disk"] == 7
    assert b["cg_peak_above_start"] == 600 and b["cg_split_at_peak"]["anon"] == 10
    assert c["samples"] == 0 and c["peak_rss_above_start"] == 100  # the nearest sample (1.8 s)
    assert pa.merge(parts, "")["peak_part"] == "b"


def test_cgroup_and_proc_readers(tmp_path):
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "memory.current").write_text("1234\n")
    (cg / "memory.peak").write_text("2000\n")
    (cg / "memory.stat").write_text("anon 100\nfile 200\nkernel 9\nfile_mapped 50\nfile_dirty 5\nshmem 0\n")
    (cg / "memory.events").write_text("low 0\nhigh 0\nmax 3\noom 0\noom_kill 1\n")
    (cg / "memory.max").write_text("max\n")
    assert pa.cgroup_sample(str(cg)) == {"current": 1234, "peak": 2000, "anon": 100, "file": 200, "file_mapped": 50,
                                         "file_dirty": 5, "shmem": 0}
    assert pa.cgroup_events(str(cg)) == {"low": 0, "high": 0, "max": 3, "oom": 0, "oom_kill": 1, "memory.max": -1}
    (cg / "memory.max").write_text("4947666944\n")
    assert pa.cgroup_events(str(cg))["memory.max"] == 4947666944
    assert pa.cgroup_sample(str(tmp_path / "none")) is None and pa.cgroup_events(str(tmp_path / "none")) is None
    (tmp_path / "123").mkdir()
    (tmp_path / "123" / "status").write_text("Name:\tpython\nVmHWM:\t    2048 kB\nVmRSS:\t    1024 kB\n"
                                             "RssAnon:\t     512 kB\nRssFile:\t     256 kB\n")
    assert pa.proc_status(123, str(tmp_path)) == {"VmHWM": 2048 * 1024, "VmRSS": 1024 * 1024, "RssAnon": 512 * 1024,
                                                  "RssFile": 256 * 1024}
    assert pa.proc_status(9, str(tmp_path)) is None


# --- the commands on a small made-up search (offline) ---

def _terrain() -> np.ndarray:
    """400 x 400 pixels at 5 m: hills with a canyon, a meadow and a hole without data."""
    rng = np.random.default_rng(11)
    z = ndimage.gaussian_filter(rng.normal(0, 1, (SIZE, SIZE)), 20) * 4000 + 400
    z[:, 150:166] -= 80
    z[40:120, 250:330] = 450.0 + 0.3 * np.arange(80)[:, None]
    z[300:320, 60:90] = np.nan
    return (z + 0.37).astype(np.float32)


@pytest.fixture
def made_up_search(tmp_path, monkeypatch):
    import rasterio as rio
    from rasterio.transform import from_origin
    from test_offline import OFFLINE_ENV
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)
    path = tmp_path / "hills.tif"
    with rio.open(path, "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(LEFT, TOP, RES, RES), nodata=np.nan) as dst:
        dst.write(_terrain(), 1)
    return ["--", "--elevation-file", str(path), "--northing", str(TOP - 1000), "--easting", str(LEFT + 1000),
            "--radius", "900", "--resolution", "5", "--nmpt", "off", "--water", "off", "--fill-gaps", "off",
            "--min-length", "50", "--max-length", "300", "--slope-threshold", "55", "--prominence-span", "10",
            "--drop-radius", "10", "--access", "--data-dir", str(tmp_path / "data")]


def test_stages_on_a_made_up_search(tmp_path, made_up_search):
    """stages: step 1, the grid in blocks of 60 pixels, at once, in blocks again: the keys of the JSON, the blocks'
    grids equal to the grid at once, nothing left of the pass, the work folder removed."""
    out_dir = tmp_path / "out"
    out = pa.main(["stages", "--out", str(out_dir), "--name", "s", "--order", "blocks,once,blocks",
                   "--block-px", "60", *made_up_search])
    saved = json.load(open(out_dir / "s.json"))
    assert saved["command"] == "stages" and saved["order"] == ["blocks", "once", "blocks"]
    for key in ("machine", "plan", "rule", "step1", "stages", "samples", "work", "argv"):
        assert key in saved, key
    assert saved["plan"]["grid_px"] == saved["plan"]["grid"][0] * saved["plan"]["grid"][1] > 100_000
    assert saved["machine"]["numba_threads"] >= 1
    step1 = saved["step1"]
    for key in ("s", "start", "end", "parts", "peak_rss_above_start", "peak_private_above_start", "rss_b_per_grid_px",
                "work_after"):
        assert key in step1, key
    assert any(name.endswith("nmt.npy") for name in step1["work_after"])
    assert [st["stage"] for st in saved["stages"]] == ["blocks", "once", "blocks"]
    for st in saved["stages"]:
        for key in ("s", "run", "start", "end", "parts", "peak_rss_above_start", "rss_b_per_grid_px"):
            assert key in st, key
        assert st["s"] > 0 and st["parts"]
        for row in st["parts"].values():
            for key in ("s", "samples", "max_gap_s", "peak_rss_above_start", "peak_private_above_start",
                        "peak_disk"):
                assert key in row, key
        if st["stage"] == "blocks":
            assert st["block_px"] == 60 and st["blocks"] > 9 and len(st["blocks_list"]) in (0, st["blocks"])
            assert st["compare_with_once"]["differ"] == 0
            assert st["left_in_work"] == []
            assert st["grid_wide"]["s"] > 0 and st["blocks_part"]["largest_window_px"] == st["window_px"]
            assert "rss_b_per_largest_window_px" in st["blocks_part"]
    assert not os.path.exists(saved["work"])
    assert not os.listdir(out_dir / "samples")  # the sidecar's files removed
    assert out["stages"][0]["compare_with_once"]["differ"] == 0


def test_pieces_and_compare_on_a_made_up_search(tmp_path, made_up_search):
    out_dir = tmp_path / "out"
    out = pa.main(["pieces", "--out", str(out_dir), "--name", "p", "--anchors", "--capture", str(tmp_path / "masks"),
                   *made_up_search])
    sh = out["shares"]
    assert 0.9 < sh["with_heights"] < 1 and 0.6 < sh["search_area"] < 0.85  # a circle of 900 m in its box
    assert sh["strips"] >= 1 and 0 < sh["strip_width_with_heights_mean"] <= 1
    assert set(out["blocks_with_area"]) >= {"2 km", "4 km", "8 km"}
    assert all(b["holding"] >= 1 for b in out["blocks_with_area"].values())
    assert out["anchors"] > 10 and set(out["blocks_with_anchor"]) == set(out["blocks_with_area"])
    if "_region_areas" in out["hooks"]:  # today's pass: the masks' pieces (never fewer than the regions)
        assert out["masks"] and all(m["pieces"] >= m["regions"] for m in out["masks"].values())
        assert os.path.exists(out["captured"]["og"])
    assert not os.path.exists(os.path.join(str(tmp_path / "data"), "work", "perf-access-p"))
    got = pa.main(["compare", "--out", str(out_dir), "--name", "c", "--block-px", "50", *made_up_search])
    assert got["differ"] == 0 and got["blocks"] > 9 and got["pixels"] > 100_000
