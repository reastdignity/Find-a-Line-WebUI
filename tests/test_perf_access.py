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
# the code measured: this checkout's, or a tree of before (PERF_ACCESS_REPO, as the tool takes it) under this file
CODE = os.environ.get("PERF_ACCESS_REPO") or REPO
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, CODE)

import perf_access as pa  # noqa: E402


def test_the_code_measured_is_the_tree_asked():
    """The tool and this test import access and search from PERF_ACCESS_REPO when it is set (a tree of before), else
    from this checkout: a module imported from the other tree would measure the wrong code."""
    import access
    import search
    for module in (access, search):
        assert os.path.normcase(os.path.dirname(os.path.abspath(module.__file__))) == os.path.normcase(CODE)
    assert os.path.normcase(pa.HERE) == os.path.normcase(CODE)

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
    # own data: heights less the filled pixels that are not water (30-31 off, 38-39 kept as water); filled: 4 columns
    assert land["with_own_data"] == round(800 / 13000, 4) and land["filled"] == round(400 / 13000, 4)
    z[:, 95:] = 2.0  # heights at the last column: the span clipped to the grid
    # 14..100 in the first two strips, 79..100 in the last
    assert pa.data_shares(z, None, rows, halo=16)["strip_width_with_heights_mean"] == round((0.86 * 2 + 0.21) / 3, 4)
    assert pa.blocks_holding(mask, 50) == {"block_px": 50, "blocks": 6, "holding": 1, "share": round(1 / 6, 4)}
    mask[129, 99] = True  # the corner block (rows 100-129, columns 50-99)
    assert pa.blocks_holding(mask, 50)["holding"] == 2
    assert pa.blocks_holding(mask, 200) == {"block_px": 200, "blocks": 1, "holding": 1, "share": 1.0}
    points = pa.blocks_holding_points(np.array([0, 3, 129]), np.array([0, 7, 99]), (130, 100), 50)
    assert points == {"block_px": 50, "blocks": 6, "holding": 2, "share": round(2 / 6, 4)}


def test_rule_a_and_the_masks_bits_by_construction(tmp_path):
    """Rule (a) on hand-made grids: a pixel left out (255) is not compared, one that differs where computed is
    counted, a 255 in the area is counted apart; a mask of packed bits (wave 2b's _Mask file) reads back as the bool
    grid it was, and so does a bool one; save_bool writes a bool .npy."""
    once = np.zeros((6, 10), np.uint8)
    blocks = once.copy()
    blocks[:, 7:] = pa.NOT_COMPUTED  # a block left out: 18 pixels
    blocks[0, 0] = 3  # differs where computed
    area = np.zeros((6, 10), bool)
    area[:, :5] = True
    a = pa.compare_rule_a(once, blocks, area)
    assert (a["differ"], a["left_out_px"], a["left_out_in_area"], a["computed_px"], a["first"]) == (1, 18, 0, 42,
                                                                                                    [[0, 0]])
    area[2, 8] = True
    assert pa.compare_rule_a(None, blocks, area)["left_out_in_area"] == 1
    assert pa.compare_rule_a(None, blocks, area)["differ"] is None
    rng = np.random.default_rng(5)
    mask = rng.random((7, 13)) < 0.4
    np.save(tmp_path / "bits.npy", np.packbits(mask, axis=1))
    np.save(tmp_path / "bool.npy", mask)
    assert (pa.mask_as_bool(str(tmp_path / "bits.npy"), mask.shape) == mask).all()
    assert (pa.mask_as_bool(str(tmp_path / "bool.npy"), mask.shape) == mask).all()
    pa.save_bool(str(tmp_path / "saved.npy"), lambda r0, r1: mask[r0:r1], mask.shape)
    got = np.load(tmp_path / "saved.npy")
    assert got.dtype == bool and (got == mask).all()
    with pytest.raises(ValueError):
        pa.mask_as_bool(str(tmp_path / "bits.npy"), (7, 30))


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
    for m in out["ways"].values():  # the headline: the larger of the sampled peak and the OS's counter
        assert m["peak_rss_above_start"] >= m["sampled_peak_rss_above_start"]
        if m["os_peak_rss_above_start"] is not None:
            assert m["peak_rss_above_start"] >= m["os_peak_rss_above_start"]
    assert pa.headline({"peak_rss_above_start": 74, "os_peak_rss_above_start": 132, "peak_private_above_start": 5,
                        "os_peak_private_above_start": None})["peak_rss_above_start"] == 132
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
    # a part without a sample has no peaks and no files, never the next part's sample (1.8 s lies in b)
    assert c["samples"] == 0 and c["peak_rss_above_start"] is None and c["peak_private_above_start"] is None
    assert "files_at_peak" not in c and c["peak_disk"] is None
    assert pa.merge(parts, "")["peak_part"] == "b"
    # every sampled peak below the stage's start (memory given back): the sampled part still wins over one without
    low = pa.summarise(samples, listings, [(0.0, "a"), (1.95, "c")], 2.0, {"rss": 1000, "private": 1000}, None)
    assert low["a"]["peak_rss_above_start"] == -700 and low["c"]["peak_rss_above_start"] is None
    assert pa.merge(low, "")["peak_rss_above_start"] == -700 and pa.merge(low, "")["peak_part"] == "a"


def test_a_blocks_peaks_above_the_stage_and_the_level():
    """block_rows / stage_report: a block's peak above the blocks stage's start (as 2026-11-15 counted) and above the
    level when the blocks begin, per pixel of its window; none above its own start."""
    mb = 2 ** 20
    stage = {"stage": "blocks", "run": 1, "s": 9.0, "windows": [100 * mb, 100 * mb, 25 * mb], "window_px": 100 * mb,
             "start": {"rss": 1000 * mb, "private": 500 * mb},
             "readings": {"blocks: block 1": {"rss": 1300 * mb, "private": 510 * mb},
                          "blocks: block 2": {"rss": 1500 * mb, "private": 520 * mb},
                          "blocks: block 3": {"rss": 1700 * mb, "private": 530 * mb}}}

    def part(rss, private, samples=3):
        return {"s": 1.0, "samples": samples, "max_gap_s": 0.02, "peak_rss_above_start": rss,
                "peak_private_above_start": private, "peak_disk": 0}
    parts = {"grid-wide: whole-metre sample": part(200 * mb, 30 * mb), "blocks: block 1": part(900 * mb, 4410 * mb),
             "blocks: block 2": part(1200 * mb, 4410 * mb), "blocks: block 3": part(None, None, 0)}
    rep = pa.stage_report(stage, parts, 1000 * mb)
    b1, b2, b3 = rep["blocks_list"]
    assert (b1["stage_rss"], b1["level_rss"]) == (900 * mb, 600 * mb)
    assert (b2["stage_rss"], b2["level_rss"]) == (1200 * mb, 900 * mb)
    assert (b2["stage_private"], b2["level_private"]) == (4410 * mb, 4400 * mb)
    assert b2["stage_rss_b_per_window_px"] == 12.0 and b2["level_rss_b_per_window_px"] == 9.0
    assert b2["level_private_b_per_window_px"] == 44.0
    assert b3["samples"] == 0 and b3["stage_rss"] is None and b3["level_rss"] is None  # no sample, no peak
    assert not any(k.startswith("own") for k in b2)  # no figure above a block's own start (code review N1)
    b = rep["blocks_part"]
    assert b["stage_rss_b_per_largest_window_px"] == 12.0 and b["level_rss_b_per_largest_window_px"] == 9.0
    assert b["level_private_b_per_largest_window_px"] == 44.0 and not any(k.startswith("own") for k in b)
    assert rep["grid_wide"]["rss_b_per_grid_px"] == 0.2


@pytest.mark.skipif(os.name != "nt", reason="EmptyWorkingSet is Windows'")
def test_the_working_set_is_emptied():
    """empty_working_set: the call succeeds and the working set drops (a page of a large array touched just before is
    no longer resident)."""
    big = np.ones(50 * 2 ** 20 // 8)  # 50 MiB touched
    got = pa.empty_working_set()
    assert got["done"], got
    assert got["after"]["rss"] < got["before"]["rss"] - 40 * 2 ** 20
    del big


def test_the_constant_needed_on_hand_made_numbers():
    """constant_needed: the pass's peak per pixel of the grid, and the blocks' peak less the window bytes (the tree's,
    given) times the largest window, per pixel of the grid; the larger decides. Numbers chosen by hand: a grid of
    100 Mpx, the pass 450 MB above the start, the blocks 1 100 MB with a largest window of 10 Mpx."""
    mb = 1_000_000
    st = {"grid_wide": {"peak_rss_above_start": 450 * mb, "peak_private_above_start": 12 * 2 ** 20},
          "blocks_part": {"peak_rss_above_start": 1100 * mb, "largest_window_px": 10 * mb,
                          "peak_private_above_level": 430 * mb},
          "parts": {"a": {"peak_disk": 900 * mb}, "b": {"peak_disk": 1300 * mb}}, "work_bytes_at_start": 900 * mb}
    n = pa.constant_needed(st, 100 * mb)
    assert n["pass_ws_b_per_px"] == 4.5 and n["blocks_beyond_50_b_per_px"] == 6.0  # (1100 - 500) / 100
    assert n["constant_needed"] == 6.0 and n["decided_by"] == "blocks beyond their window"
    assert n["blocks_beyond_private_b_per_px"] == 6.7 and n["pass_private_mib"] == 12.0
    assert n["mark_files_bytes"] == 400 * mb and n["mark_files_b_per_px"] == 4.0
    n = pa.constant_needed(st, 100 * mb, window_bytes=60)  # the tree's window bytes, not a fixed 50
    assert n["blocks_beyond_50_b_per_px"] == 5.0 and n["constant_needed"] == 5.0 and n["window_bytes"] == 60
    st["blocks_part"]["peak_rss_above_start"] = 900 * mb
    n = pa.constant_needed(st, 100 * mb)
    assert n["constant_needed"] == 4.5 and n["decided_by"] == "grid-wide pass"


def test_the_pass_parts_on_hand_made_labels():
    """pass_parts: per pass mask, regions (with its sub-parts) and after, the rest, their sum, and the judged span =
    regions + after of the two open-ground passes; a label of neither cut is shown under "other"."""
    def r(sec):
        return {"s": sec}
    parts = {"grid-wide: whole-metre sample": r(1.0), "grid-wide: water (copy, flush)": r(0.5),
             "grid-wide: flat lakes: mask": r(2.0), "grid-wide: flat lakes: regions: forward": r(3.0),
             "grid-wide: flat lakes: regions: backward": r(0.25), "grid-wide: flat lakes: after: B": r(1.5),
             "grid-wide: open ground: mask": r(4.0), "grid-wide: open ground: regions: labels": r(2.0),
             "grid-wide: open ground: after: write": r(1.0), "grid-wide: smoothed open ground: mask": r(6.0),
             "grid-wide: smoothed open ground: regions: forward": r(1.25),
             "grid-wide: smoothed open ground: after: visits": r(0.75), "grid-wide: masks opened": r(0.125),
             "blocks: block 1": r(9.0)}
    parts["grid-wide: open ground: after: write"]["s_raw"] = 1.0004  # unrounded seconds are summed as they are
    pp = pa.pass_parts(parts, 23.375)
    assert abs(pp["pass_s_raw"] - 23.3754) < 1e-9 and abs(pp["judged_span_s_raw"] - 5.0004) < 1e-9
    assert pp["flat lakes"] == {"mask": 2.0, "regions": 3.25, "after": 1.5,
                                "sub": {"forward": 3.0, "backward": 0.25, "B": 1.5}}
    assert pp["open ground"]["regions"] == 2.0 and pp["open ground"]["after"] == 1.0
    assert pp["rest"] == {"whole-metre sample": 1.0, "water (copy, flush)": 0.5, "masks opened": 0.125}
    assert pp["sum_s"] == 23.375 == pp["pass_s"] and "other" not in pp
    assert pp["judged_span_s"] == 2.0 + 1.0 + 1.25 + 0.75
    parts["grid-wide: something new"] = r(1.0)
    assert pa.pass_parts(parts, 24.375)["other"] == {"something new": 1.0}


def test_b_passes_counted_once_when_the_selection_calls_itself(monkeypatch):
    """B's passes: filling._select calls itself again (through the module) when a pair splits; each read of the
    region's heights is one pass, not one per nesting (code review 2a-3)."""
    import types
    from sources import filling

    def fake_select(chunks, depth=0):  # reads the heights once, then once more through a call of itself
        list(chunks())
        if depth == 0:
            return filling._select(chunks, depth=1)
        return 0.0
    monkeypatch.setattr(filling, "_select", fake_select)

    class Regions:
        questions = {"pixels": [5], "first": [0], "last": [1], "lowest": [0.0], "highest": [1.0]}

    def _spread_large(regions, z, q):
        return filling._select(lambda: iter([np.zeros(5, np.float32)]))
    fake = types.SimpleNamespace(_spread_large=_spread_large)
    marks = pa.Marks()
    marks.hook(fake)
    fake._spread_large(Regions(), None, 0)
    marks.unhook(fake)
    assert marks.large[0]["passes"] == 2 and filling._select is fake_select


def test_the_blocks_hook_keeps_no_window_alive():
    """Marks.hook's _answers: the open ground's windows reach the measure without a reference of the hook, so the
    measure's own `del og` / `del og2` free them as in a call without the hook (a wrapper of *args kept them)."""
    import types
    import weakref
    freed = []

    def _answers(z, water, data, res, wm, og, alpine, og2=None, s=None):
        refs = weakref.ref(og), weakref.ref(og2)
        del og
        del og2
        freed.append((refs[0]() is None, refs[1]() is None))
        return np.zeros(z.shape, np.uint8)

    fake = types.SimpleNamespace(_answers=_answers)
    marks = pa.Marks()
    marks.hook(fake)
    assert marks.found == ["_answers"] and fake._answers is not _answers
    z = np.zeros((4, 5), np.float32)
    fake._answers(z, None, None, 1.0, False, np.zeros(9, bool), True, og2=np.zeros(9, bool))
    assert freed == [(True, True)] and marks.windows == [20]
    assert marks.events[-1][1] == "blocks: block 2" and "blocks: block 2" in marks.readings
    marks.unhook(fake)
    assert fake._answers is _answers

    def other(z, og):  # another signature: no per-block parts, the measure left as it is
        return None
    fake = types.SimpleNamespace(_answers=other)
    marks = pa.Marks()
    marks.hook(fake)
    assert fake._answers is other and marks.found == []


def test_cgroup_and_proc_readers(tmp_path):
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "memory.current").write_text("1234\n")
    (cg / "memory.peak").write_text("2000\n")
    (cg / "memory.stat").write_text("anon 100\nfile 200\nkernel 9\nfile_mapped 50\nfile_dirty 5\nshmem 0\n")
    (cg / "memory.events").write_text("low 0\nhigh 0\nmax 3\noom 0\noom_kill 1\n")
    (cg / "memory.max").write_text("max\n")
    assert pa.cgroup_sample(str(cg)) == {"v": 2, "current": 1234, "peak": 2000, "anon": 100, "file": 200,
                                         "file_mapped": 50, "file_dirty": 5, "shmem": 0}
    assert pa.cgroup_events(str(cg)) == {"v": 2, "low": 0, "high": 0, "max": 3, "oom": 0, "oom_kill": 1,
                                         "memory.max": -1}
    (cg / "memory.max").write_text("4947666944\n")
    assert pa.cgroup_events(str(cg))["memory.max"] == 4947666944
    assert pa.cgroup_sample(str(tmp_path / "none")) is None and pa.cgroup_events(str(tmp_path / "none")) is None
    v1 = tmp_path / "v1" / "memory"  # cgroup v1 (Docker Desktop on WSL2): the same names
    v1.mkdir(parents=True)
    (v1 / "memory.usage_in_bytes").write_text("3000\n")
    (v1 / "memory.max_usage_in_bytes").write_text("3500\n")
    (v1 / "memory.stat").write_text("cache 9\nrss 8\ntotal_cache 300\ntotal_rss 200\ntotal_mapped_file 70\n"
                                    "total_dirty 6\ntotal_shmem 1\n")
    (v1 / "memory.limit_in_bytes").write_text("4947666944\n")
    (v1 / "memory.failcnt").write_text("12\n")
    (v1 / "memory.memsw.failcnt").write_text("81419\n")
    (v1 / "memory.oom_control").write_text("oom_kill_disable 0\nunder_oom 0\noom_kill 0\n")
    assert pa.cgroup_sample(str(tmp_path / "v1")) == {"v": 1, "current": 3000, "peak": 3500, "anon": 200,
                                                      "file": 300, "file_mapped": 70, "file_dirty": 6, "shmem": 1}
    assert pa.cgroup_events(str(tmp_path / "v1")) == {"v": 1, "oom_kill_disable": 0, "under_oom": 0, "oom_kill": 0,
                                                      "failcnt": 12, "memsw.failcnt": 81419,
                                                      "memory.max": 4947666944}
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
    import types
    out_dir = tmp_path / "out"
    out = pa.main(["stages", "--out", str(out_dir), "--name", "s", "--order", "blocks,once,blocks,full",
                   "--block-px", "60", *made_up_search])
    saved = json.load(open(out_dir / "s.json"))
    assert saved["command"] == "stages" and saved["order"] == ["blocks", "once", "blocks", "full"]
    for key in ("machine", "plan", "rule", "step1", "stages", "samples", "work", "argv"):
        assert key in saved, key
    assert saved["plan"]["grid_px"] == saved["plan"]["grid"][0] * saved["plan"]["grid"][1] > 100_000
    assert saved["machine"]["numba_threads"] >= 1
    step1 = saved["step1"]
    for key in ("s", "start", "end", "parts", "peak_rss_above_start", "peak_private_above_start", "rss_b_per_grid_px",
                "work_after"):
        assert key in step1, key
    assert any(name.endswith("nmt.npy") for name in step1["work_after"])
    assert [st["stage"] for st in saved["stages"]] == ["blocks", "once", "blocks", "full"]
    import access
    takes_needed = hasattr(access, "NOT_COMPUTED")  # E (wave 2b): the blocks made with the search area
    full = saved["stages"][3]  # rule (b): every block, without the area, against the grid at once at every pixel
    assert full["untimed"] and full["left_out"] == 0 and full["rule_b"]["differ"] == 0
    for st in saved["stages"]:
        for key in ("s", "run", "start", "end", "parts", "peak_rss_above_start", "rss_b_per_grid_px"):
            assert key in st, key
        assert st["s"] > 0 and st["parts"]
        for row in st["parts"].values():
            for key in ("s", "samples", "max_gap_s", "peak_rss_above_start", "peak_private_above_start",
                        "peak_disk"):
                assert key in row, key
        if st["stage"] == "blocks":
            assert st["block_px"] == 60 and st["blocks"] > 9
            a = st["rule_a"]  # rule (a): 0 differ where computed, no pixel of the area left out
            assert a["differ"] == 0 and a["left_out_in_area"] == 0 and a["once_not_computed"] == 0
            assert st["compare_with_once"] == a and st["left_out_px"] == a["left_out_px"]
            assert (a["left_out_px"] > 0) == (st["left_out"] > 0)
            assert st["needed_passed"] == ("search area" if takes_needed else "a tree without needed")
            if takes_needed:  # the circle of 900 m in its 2 km box: the corner blocks of 300 m hold none of it
                assert st["left_out"] > 0 and "needed: the search area's blocks" in st["parts"]
            assert st["left_in_work"] == []
            assert st["grid_wide"]["s"] > 0 and st["blocks_part"]["largest_window_px"] == st["window_px"]
            assert "stage_rss_b_per_largest_window_px" in st["blocks_part"]
            labels = set(st["parts"])
            if "_Regions.__init__" in st["hooks"]:  # S: the regions' forward and backward sweep, then the visits
                assert {"grid-wide: open ground: mask", "grid-wide: open ground: regions: forward",
                        "grid-wide: open ground: regions: backward", "grid-wide: open ground: after: visits"} <= labels
                c = st["counts"]["open ground"]
                assert c["scratch_bytes"] > 0 and c["record_bytes"] == 32 * c["records"]
                import access
                assert st["labels_dtypes"] == [str(access._Regions._label(
                    types.SimpleNamespace(strips=[(0, 4)], mask=types.SimpleNamespace(
                        rows=lambda r0, r1: np.ones((4, 4), bool))), 0)[0].dtype)]  # as the tree labels a strip
            elif "_region_areas" in st["hooks"]:  # the base: the labels file, then the write; no S's counts
                assert st["labels_dtypes"] == []
                assert {"grid-wide: open ground: mask", "grid-wide: open ground: regions: labels",
                        "grid-wide: open ground: after: write"} <= labels, labels
                assert not any(k.startswith("grid-wide: flat lakes: after: gather") for k in labels)
                assert all("questions_in_sweep" not in c for c in st["counts"].values())
            pp = st["pass_parts"]  # the cut sums to the pass, nothing left outside it
            assert "other" not in pp and abs(pp["sum_s"] - st["grid_wide"]["s"]) < 1e-6
            assert pp["judged_span_s"] == round(pp["open ground"]["regions"] + pp["open ground"]["after"], 3)
            n = st["needed"]
            assert n["constant_needed"] == max(v for v in (n["pass_ws_b_per_px"], n.get("blocks_beyond_50_b_per_px"))
                                               if v is not None)
            assert n["mark_files_b_per_px"] > 0 and n["pass_private_mib"] is not None
            if "_answers" in st["hooks"]:  # every block's part, with the windows block_grid lays out
                import access
                h, w = saved["plan"]["grid"]
                expected = [(b - a) * (d - c) for a, b, c, d in pa.windows(h, w, 60, access.margin_px(5.0))]
                assert st["blocks"] + st["left_out"] == len(expected)
                if not st["left_out"]:
                    assert st["windows"] == expected
                else:  # the blocks computed, in block_grid's order: a part of the layout's windows, in its order
                    it = iter(expected)
                    assert all(any(x == e for e in it) for x in st["windows"])
                assert len(st["windows"]) == len(st["blocks_list"]) == st["blocks"]
                assert "blocks: block 1" in st["readings"] and len(st["readings"]) == st["blocks"] + 1
                assert all(r["window_px"] == e for r, e in zip(st["blocks_list"], st["windows"]))
                # the level's figure exactly when the blocks got a sample (a part without one has no peak: the
                # blocks of this small grid take a fraction of a second, and a busy machine may sample none)
                b = st["blocks_part"]
                assert (b["peak_rss_above_level"] is None) == (b["samples"] == 0), (b["samples"], b)
    assert not os.path.exists(saved["work"])
    assert not os.listdir(out_dir / "samples")  # the sidecar's files removed
    assert out["stages"][0]["compare_with_once"]["differ"] == 0


def test_the_rules_constants_for_one_run_only(tmp_path, made_up_search):
    """plan with --area-bytes and --area-fixed: the rule's answer with them (recorded), and search's names as before
    once the command ends (a second command in the process starts from the tree's constants)."""
    import search
    before = (search.ACCESS_AREA_BYTES, search._access_budget, search.available_memory)
    out = pa.main(["plan", "--out", str(tmp_path / "out"), "--name", "r", "--memory", "3000000", "--area-bytes", "7",
                   "--area-fixed", "1000", *made_up_search])
    r = out["rule"]
    assert r["ACCESS_AREA_BYTES"] == 7 and r["area_fixed"] == 1000 and r["budget"] == 3_000_000
    if r["block_px"]:
        assert r["counts_bytes"] == int(7 * out["plan"]["grid_px"] + 1000 + 50 * r["window_px_max"])
    assert (search.ACCESS_AREA_BYTES, search._access_budget, search.available_memory) == before


def test_pieces_and_compare_on_a_made_up_search(tmp_path, made_up_search):
    out_dir = tmp_path / "out"
    out = pa.main(["pieces", "--out", str(out_dir), "--name", "p", "--anchors", "--capture", str(tmp_path / "masks"),
                   *made_up_search])
    sh = out["shares"]
    assert 0.9 < sh["with_heights"] < 1 and 0.6 < sh["search_area"] < 0.85  # a circle of 900 m in its box
    assert sh["strips"] >= 1 and 0 < sh["strip_width_with_heights_mean"] <= 1
    assert set(out["blocks_with_area"]) >= {"0.5 km", "1 km", "2 km", "4 km", "8 km"}
    assert out["blocks_with_area"]["0.5 km"]["block_px"] == 100 and out["anchors_s"] >= 0
    assert all(b["holding"] >= 1 for b in out["blocks_with_area"].values())
    assert out["anchors"] > 10 and set(out["blocks_with_anchor"]) == set(out["blocks_with_area"])
    if out["hooks"]:  # the real pass: each mask as its regions are found, its pieces and regions exactly
        import access
        assert out["masks"] and os.path.exists(out["captured"]["og"])
        for name, m in out["masks"].items():
            mask = np.load(m["captured"])
            h, w = mask.shape
            rows = list(pa.strips(h, w, access.STRIP_PX))
            assert {k: m[k] for k in ("pieces", "most_in_a_strip", "most_in_a_last_row")} == \
                {k: v for k, v in pa.strip_pieces(mask, rows).items() if k != "strips"}, name
            assert m["regions"] == ndimage.label(mask, structure=np.ones((3, 3), bool))[1] > 3, name
            assert m["true_pixels"] == int(mask.sum()), name
            if "regions_by_tables" in m:  # wave 1's _Regions: its own counts agree, its scratch file was there
                assert m["regions_by_tables"] == m["regions"] and m["pieces_by_regions"] == m["pieces"], name
                assert m["scratch_file_bytes"] > 0, name
    assert not os.path.exists(os.path.join(str(tmp_path / "data"), "work", "perf-access-p"))
    got = pa.main(["compare", "--out", str(out_dir), "--name", "c", "--block-px", "50", *made_up_search])
    assert got["differ"] == 0 and got["blocks"] > 9 and got["pixels"] > 100_000
