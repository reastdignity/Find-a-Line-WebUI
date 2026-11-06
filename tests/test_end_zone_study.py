"""tools/end_zone_study.py: its harness at zone 0 / lift 0 against find_valid_lines, the variants of a
call, the rule's checks, and a capture/variants/diagnose/report of the Żabi Koń clip (offline). The
rule itself is production's since wave 1: tests/test_end_zone.py."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import end_zone_study as ezs  # noqa: E402
import perf_line_funnel as plf  # noqa: E402
from test_offline import DATA, OFFLINE_ENV  # noqa: E402


def canyon(rng):
    """A canyon across the columns with rounded rims (the strict rule fails next to most anchors),
    gentle ramps along the rows and on the floor, a little noise and a few NaNs."""
    rows, cols = np.mgrid[0:110, 0:130].astype(np.float64)
    edge = lambda c, c0, w: 0.5 - 0.5 * np.cos(np.pi * np.clip((c - c0) / w, 0, 1))  # noqa: E731
    z = 100 - 45 * edge(cols, 28, 8) + 50 * edge(cols, 92, 6)  # a 45 m drop and a 50 m rise
    z += 0.04 * rows + 0.02 * np.abs(cols - 65) + rng.random(z.shape) * 0.6
    z[rng.random(z.shape) < 0.002] = np.nan
    return z.astype(np.float32)


def capture_call(folder, model, nmpt, first):
    """The canyon's line search, captured as perf_line_funnel captures it; production's lines."""
    import helpers as sh
    import linesearch as ls
    import sag
    rng = np.random.default_rng(5)
    z = canyon(rng)
    surface = (z + (rng.random(z.shape) < 0.05) * rng.random(z.shape) * 12).astype(np.float32)
    steep = sh.find_significant_slopes(z, 1.0, 20, np.ones(z.shape, dtype=bool))
    anchors = np.vstack([steep[rng.choice(len(steep), 170, replace=False)], rng.integers(0, 110, (20, 2))])
    first_mask = rng.random(len(anchors)) < 0.7 if first else None
    table = sag.EnvelopeTable(sag.Rigging(), 20, 120) if model == "sag" else None
    wrapper = plf.Capture(str(folder), None)
    wrapper.install()
    try:
        lines = ls.find_valid_lines(z, surface, anchors, 1.0, 20, 120, nmpt_mode=nmpt, threads=2, sag_table=table,
                                    max_dh_ratio=0.4, first=first_mask)
    finally:
        wrapper.uninstall()
    return os.path.join(str(folder), "call-0"), lines, (z, surface, anchors, table, first_mask)


CASES = [("formula", "mark", True), ("sag", "reject", False)]


@pytest.fixture(scope="module", params=CASES, ids=[c[0] for c in CASES])
def call(request, tmp_path_factory):
    folder, lines, raw = capture_call(tmp_path_factory.mktemp("call"), *request.param)
    return ezs.setup(folder), lines, raw, request.param


def test_zero_rule_is_production(call):
    """run_rule at zone 0, lift 0 is find_valid_lines on the captured call: its lines and funnel."""
    import linesearch as ls
    a, lines, raw, (model, nmpt, first) = call
    assert len(lines) > 20
    base = ezs.run_rule(a, threads=2)
    assert ezs.same_lines(lines, base.table)
    np.testing.assert_array_equal(base.table.columns["clearance"], lines.columns["clearance"])
    z, surface, anchors, table, first_mask = raw
    stats = {}
    ls.find_valid_lines(z, surface, anchors, 1.0, 20, 120, nmpt_mode=nmpt, threads=2, sag_table=table,
                        max_dh_ratio=0.4, first=first_mask, stats=stats)
    assert base.funnel == {"anchors": len(anchors), **{k: stats[k] for k in ("open", "todo", "candidates",
                                                                          "checked", "found", "valid")}}


def test_variants_of_a_call(call):
    a = call[0]
    r = ezs.variants_call(a, [0, 5, 20], [0, 1], 0.25, 0.0, 2, True, 20.0, "clearance")
    t = r["table"]
    assert t["0,0"]["lines"] == len(call[1]) and t["0,0"]["new"] == 0
    assert t["20,1"]["lines"] == r["funnel"]["superset"]["valid"]
    assert all(e["lines"] - e["new"] == t["0,0"]["lines"] for e in t.values())  # monotone: nothing lost
    assert t["5,0"]["lines"] <= t["20,0"]["lines"] <= t["20,1"]["lines"]
    assert set(r["seconds"]["baseline"]) == set(ezs.STAGES) == set(r["seconds"]["superset"])


def test_rule_checked():
    from types import SimpleNamespace
    fake = SimpleNamespace(sag_table=None)  # the formula: a fall allowance of 6 m
    assert ezs.check_rule(fake, 1.0, 5.0, 2.0, 0.25) == 4.0
    for bad in ((-1.0, 0.0, 0.0, 0.25), (0.0, -1.0, 0.0, 0.25), (0.0, 0.0, 7.0, 0.25), (0.0, 0.0, 0.0, 0.8)):
        with pytest.raises(ValueError):
            ezs.check_rule(fake, *bad)


def test_zabi_kon_clip(tmp_path):
    """capture (without a cache link), variants, diagnose of a found line, report with pictures."""
    env = {**os.environ, **OFFLINE_ENV}
    tool = os.path.join("tools", "end_zone_study.py")
    result = subprocess.run(
        [sys.executable, tool, "capture", "zk", "--out", str(tmp_path), "--no-cache-link", "--",
         "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"),
         "--northing", "254608", "--easting", "553966", "--radius", "290", "--slope-threshold", "45",
         "--water", "off", "--fill-gaps", "off"],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    place = tmp_path / "zk"
    assert result.returncode == 0, result.stdout + result.stderr + open(place / "output.log", encoding="utf-8").read()
    data = ezs.variants(str(place), [0, 5], [0, 1], 0.25, 0.0, None)
    assert data["table"]["0,0"]["lines"] == 1301 and data["table"]["5,1"]["new"] > 0  # test_offline's ZABI_KON
    assert data["slope_threshold"] == 45 and all(data["checks"].values())
    grid = json.load(open(place / "capture" / "call-0" / "grid.json"))
    lines = np.load(place / "capture" / "call-0" / "lines.npz")
    from pyproj import Transformer
    to_wgs = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True)
    ends = []
    for pixel in (lines["a1"][0], lines["a2"][0]):
        lon, lat = to_wgs.transform(grid["left"] + (pixel[1] + 0.5) * grid["res"],
                                    grid["top"] - (pixel[0] + 0.5) * grid["res"])
        ends.append([lat, lon])
    with open(tmp_path / "lines.json", "w") as f:
        json.dump([{"name": "longest", "a": ends[0], "b": ends[1]}], f)
    d = ezs.diagnose(str(place), str(tmp_path / "lines.json"), 3.0, [0, 5, 10], 0.25, 0.0, [45, 30])
    line = d["lines"][0]
    assert line["best"]["accepted"] and line["best"]["clearance"] >= lines["clearance"][0]
    assert line["staircase"][0]["lift"] == 0.0 and line["ends"][0]["anchor_within"] == 0.0
    text = ezs.report(str(tmp_path / "out"), [str(place)])
    assert "zk" in text and os.path.exists(tmp_path / "out" / "pictures" / "zk-map.png")
    assert os.path.exists(tmp_path / "out" / "pictures" / "zk-line-1.png")
    assert json.load(open(tmp_path / "out" / "study.json"))["places"][0]["variants"]["place"] == "zk"
