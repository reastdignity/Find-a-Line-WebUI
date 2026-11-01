"""tools/perf_line_funnel.py: the self-check against the frozen kernels, the funnel's counts
on a synthetic canyon, and a capture of the Żabi Koń clip (offline)."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import perf_line_funnel as plf  # noqa: E402
from test_offline import DATA, OFFLINE_ENV, ZABI_KON  # noqa: E402


def canyon_call(folder, model):
    """The canyon of tests/test_units.py::test_kernels_independent_of_threads (anchors not in
    row-major order, a first mask, NaNs, a wall-angle limit), captured through the wrapper."""
    import helpers as sh
    import linesearch as ls
    import sag
    rng = np.random.default_rng(11)
    z = (rng.random((160, 160)) * 3 + 100).astype(np.float32)
    z[:, :20] += 60
    z[:, 140:] += 55 + rng.random((160, 20)).astype(np.float32) * 10
    z[rng.random((160, 160)) < 0.003] = np.nan
    surface = (z + rng.random((160, 160)) * 20).astype(np.float32)
    anchors = np.vstack([np.column_stack([np.arange(0, 160, 2), np.full(80, 19)]),
                         np.column_stack([np.arange(1, 160, 2), np.full(80, 140)]),
                         rng.integers(0, 160, (60, 2))])
    first = rng.random(len(anchors)) < 0.7
    table = sag.EnvelopeTable(sag.Rigging(), 20, 200) if model == "sag" else None
    wrapper = plf.Capture(str(folder), None)
    wrapper.install()
    try:
        lines = ls.find_valid_lines(z, surface, anchors, 1.0, 20, 150, nmpt_mode="mark", threads=2,
                                    sag_table=table, max_dh_ratio=0.3, first=first,
                                    limits=sh.LineLimits(max_wall_angle=60))  # 120 in test_units: rejects none
    finally:
        wrapper.uninstall()
    assert ls.find_valid_lines is wrapper.original
    return os.path.join(str(folder), "call-0"), len(lines)


def without_timings(data):
    return {name: {k: v for k, v in r.items() if k != "timings"} for name, r in data["calls"].items()}


@pytest.mark.parametrize("model", ["formula", "sag"])
def test_canyon(tmp_path, model):
    import numba
    call, lines = canyon_call(tmp_path / "capture", model)
    timings = json.load(open(os.path.join(call, "timings.json")))
    assert timings["lines"] == lines and set(timings["stages"]) == set(plf.STAGES)
    most = numba.config.NUMBA_NUM_THREADS
    try:
        one = plf.analyse([call], str(tmp_path / "one"), 1, 1)
        three = plf.analyse([call], str(tmp_path / "three"), 1, min(3, most))
    finally:
        numba.set_num_threads(most)
    assert without_timings(one) == without_timings(three)  # integers at the anchors' own indices
    r = one["calls"]["call-0"]
    p = r["pairs"]
    assert p["found"] >= lines > 50 and p["checked"] > p["found"]
    assert p["visits"] == sum(p[name] for _, name in plf.REJECTIONS) + p["found"]
    assert p["sampled_anchors"] == r["todo"] and p["sampled_line_ok_tests"] == p["line_ok_tests"]
    assert r["orders"]["ends_inward"] == p["line_ok_tests"]
    assert all(n == 0 for n in r["skip_unsafe"].values())
    assert r["box_visits"]["L/4"] == p["visits"]
    cumulative = list(r["skip_cumulative"].values())
    assert cumulative == sorted(cumulative) and cumulative[-1] <= p["visits"]
    assert r["skip_alone"]["F2a"] > 0 and r["skip_alone"]["F2b"] > 0 and p["wall_angle"] > 0
    f = r["first_failure"]
    assert sum(f["checked"].values()) == p["checked"]
    assert sum(f["passed"].values()) == p["found"]
    assert sum(f["end"].values()) == p["line_ok_fail"]
    assert all(n > 0 for n in r["orders"].values())
    assert r["rings"]["rings"] == sum(r["rings"]["per_ring"]["alive_anchors"])
    assert r["rings"]["alive_sector_scan_reads"] <= r["rings"]["pixel_reads"]
    assert sum(r["rings"]["rings_max_histogram"]) == r["anchors"]
    assert os.path.exists(tmp_path / "one" / "funnel.md")
    # Sampling simulates the orders for fewer anchors and leaves the funnel as it was
    sampled = plf.analyse([call], str(tmp_path / "sampled"), 4, None)["calls"]["call-0"]
    assert sampled["pairs"]["visits"] == p["visits"] and sampled["pairs"]["sampled_anchors"] < r["todo"]


def test_self_check_fails_on_a_changed_kernel(tmp_path, monkeypatch):
    import linesearch as ls
    call, _ = canyon_call(tmp_path / "capture", "formula")
    original = ls._free_rings

    def fewer(*args):
        rings = original(*args)
        rings[0] = 0
        return rings
    monkeypatch.setattr(ls, "_free_rings", fewer)
    with pytest.raises(plf.SelfCheckError):
        plf.analyse([call], str(tmp_path / "out"), 1, None)


def test_zabi_kon_capture(tmp_path):
    """The clip of tests/test_offline.py::test_zabi_kon_clip, captured and analysed."""
    env = {**os.environ, **OFFLINE_ENV}
    result = subprocess.run(
        [sys.executable, os.path.join("tools", "perf_line_funnel.py"), "capture", "--out", str(tmp_path / "zk"),
         "--", "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"),
         "--northing", "254608", "--easting", "553966", "--radius", "290",
         "--water", "off", "--fill-gaps", "off", "--data-dir", str(tmp_path / "data")],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "find_valid_lines called 1 times" in result.stdout
    data = plf.analyse([str(tmp_path / "zk" / "call-0")], str(tmp_path / "out"), 1, None)
    r = data["calls"]["call-0"]
    assert (r["anchors"], r["open"], r["pairs"]["checked"]) == \
        (ZABI_KON["anchors"], ZABI_KON["open"], ZABI_KON["checked"])
    assert all(n == 0 for n in r["skip_unsafe"].values())
    assert set(r["timings"]["stages"]) == set(plf.STAGES)
