"""tools/perf_country.py: the mirrored mosaic, the T(L) patch of the sag estimator (equal to the
plain search at a constant tension), compare and cube on synthetic lines.csv (offline)."""

import csv
import glob
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import perf_country as pc  # noqa: E402
import runs  # noqa: E402
from test_offline import DATA, OFFLINE_ENV  # noqa: E402


def test_mosaic(tmp_path):
    import rasterio as rio
    nmt, nmpt, (easting, northing) = pc.mosaic(str(tmp_path), 3)
    with rio.open(pc.CLIP_NMT) as clip:
        band, transform, crs = clip.read(1), clip.transform, clip.crs
    for path in (nmt, nmpt):
        with rio.open(path) as m:
            assert (m.width, m.height) == (1800, 1800) and m.transform == transform and m.crs == crs
            assert m.compression.name == "deflate"
            whole = m.read(1)
        for k in (600, 1200):  # every seam joins equal pixels
            assert np.array_equal(whole[:, k - 1], whole[:, k]) and np.array_equal(whole[k - 1], whole[k])
    with rio.open(nmt) as m:
        whole = m.read(1)
    assert np.array_equal(whole[:600, :600], band) and np.array_equal(whole[600:1200, 600:1200], band[::-1, ::-1])
    assert (easting, northing) == (transform.c + 900, transform.f - 900)


def test_tension_interpolation():
    points = pc.parse_tension("1500:6,300:2.5,5000:15")
    assert points == [(300, 2.5), (1500, 6), (5000, 15)]
    assert pc.tension_at(points, 100) == 2.5 and pc.tension_at(points, 9000) == 15  # clamped
    assert pc.tension_at(points, 900) == pytest.approx(4.25)
    assert pc.tension_at(points, 3250) == pytest.approx(10.5)


def test_constant_tension_table_is_the_original():
    import sag
    rig = sag.Rigging(pretension=4)
    table = pc.tension_table([(100, 4)])(rig, 20, 300)
    original = sag.EnvelopeTable(rig, 20, 300)
    assert np.array_equal(table.sag, original.sag) and np.array_equal(table.spans, original.spans)
    longer = pc.tension_table([(20, 4), (300, 10)])(rig, 20, 300)
    assert np.array_equal(longer.sag[0], original.sag[0])  # the shortest span at 4 kN
    assert (longer.sag[-1, :, 1:-1] < original.sag[-1, :, 1:-1]).all()  # more tension, less sag


def _digest(data_dir) -> str:
    [path] = glob.glob(os.path.join(str(data_dir), "runs", "*", "lines.csv"))
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_profile_with_constant_tension_equals_the_search(tmp_path):
    common = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--northing", "254608",
              "--easting", "553966", "--radius", "120", "--min-length", "20", "--max-length", "150",
              "--model", "sag", "--pretension", "3", *pc.OFFLINE, "--no-html"]
    env = {**os.environ, **OFFLINE_ENV}
    plain = subprocess.run([sys.executable, "findaline.py", *common, "--no-plot", "--yes", "--ortho", "never",
                            "--data-dir", str(tmp_path / "plain")],
                           cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert plain.returncode == 0, plain.stdout + plain.stderr
    patched = subprocess.run([sys.executable, os.path.join("tools", "perf_country.py"), "profile",
                              "--out", str(tmp_path / "out"), "--name", "clip", "--tension-by-length", "50:3,400:3",
                              "--", *common, "--data-dir", str(tmp_path / "patched")],
                             cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert patched.returncode == 0, patched.stdout + patched.stderr
    assert _digest(tmp_path / "plain") == _digest(tmp_path / "patched")
    sample = json.load(open(tmp_path / "out" / "samples.json"))["clip"]
    assert sample["tension_by_length"] == "50:3,400:3" and sample["summary"]["lines"] > 0
    assert sample["grid"]["crs"] == "EPSG:2180" and sample["grid"]["tiles"] == 1 and sample["grid"]["res"] == 1
    assert sample["grid"]["area_km2"] == pytest.approx(np.pi * 0.12 ** 2, rel=1e-3)
    assert sample["funnel"] and sample["stages"] and sample["total"]["wall_s"] > 0
    assert os.path.dirname(sample["run"]) == os.path.abspath(tmp_path / "patched" / "runs")


def test_profile_of_a_search_without_lines(tmp_path):
    """A search that finds no lines saves no run: the sample has zero counts, its stages and funnel,
    and compare and cube read it as empty."""
    args = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--northing", "254608", "--easting", "553966",
            "--radius", "120", "--min-length", "200", "--max-length", "230", *pc.OFFLINE, "--no-html",
            "--data-dir", str(tmp_path / "data")]
    done = subprocess.run([sys.executable, os.path.join("tools", "perf_country.py"), "profile", "--out",
                           str(tmp_path / "out"), "--name", "none", "--", *args],
                          cwd=REPO, env={**os.environ, **OFFLINE_ENV}, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)
    assert done.returncode == 0, done.stdout + done.stderr
    samples = json.load(open(tmp_path / "out" / "samples.json"))
    sample = samples["none"]
    assert sample["run"] is None and sample["summary"] == {"lines": 0, "spots": 0} and "note" in sample
    assert sample["stages"] and sample["grid"]["tiles"] == 1
    samples["full"] = synthetic(tmp_path)["a"]
    rows = pc.compare(samples, "full", ["none"], [1000], [(30, 60)])["rows"]
    assert {r["band"]: r["other_lines"] for r in rows} == {"all": 0, "30-60": 0}
    [row] = pc.cube(samples, ["none"], 1000, ["length"])["rows"]
    assert row["lines"] == 0 and row["line_keys"] == 0 and row["spot_keys"] == 0


def write_run(folder, rows, crs="EPSG:2180"):
    """A run folder with a lines.csv of rows (dicts of some FIELDS, the rest empty) and its run.json."""
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "lines.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, runs.FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in runs.FIELDS})
    with open(os.path.join(folder, "run.json"), "w") as f:
        json.dump({"center": {"crs": crs}, "summary": {"lines": len(rows)}}, f)
    return str(folder)


def line(group, rep, length, east, north, **values):
    row = {"group": group, "representative": rep, "length_m": length, "anchor1_easting": east,
           "anchor1_northing": north, "clearance_m": 3, "height_max_m": 15, "water_m": 0,
           "over_trees_buildings": False, "anchor1_wall_angle": 20, "anchor2_wall_angle": 20,
           "anchor1_prominence_m": 6, "anchor2_prominence_m": 6}
    row.update(values)
    return row


def synthetic(tmp_path):
    rows = [line(1, True, 40, 100, 100), line(1, False, 45, 120, 110), line(2, True, 80, 1700, 300),
            line(3, True, 400, 2600, 2400), line(3, False, 410, 2610, 2400), line(4, True, 50, 900, 900),
            line(5, True, 35, 300, 200)]
    run = write_run(tmp_path / "run", rows)
    return {"a": {"run": run, "grid": {"area_km2": 4.0}}, "b": {"run": run, "grid": {"area_km2": 4.0}}}


def test_compare_a_run_with_itself(tmp_path):
    samples = synthetic(tmp_path)
    result = pc.compare(samples, "a", ["b"], [500, 1000], pc.BANDS)
    rows = {(r["cell"], r["band"]): r for r in result["rows"]}
    assert rows[(500, "all")]["ref_lines"] == 7 and rows[(500, "all")]["ref_spots"] == 5
    assert rows[(1000, "30-60")]["ref_lines"] == 4 and rows[(1000, "30-60")]["ref_spots"] == 3
    for r in result["rows"]:
        if r["ref_lines"]:
            assert r["lines_ratio"] == 1 and r["spots_ratio"] in (1, None)
        if r["ref_spots"]:
            assert r["lost"] == 0 and r["new"] == 0
        assert r["spearman"] is None or r["spearman"] == pytest.approx(1)  # None: the same count in every cell
    assert rows[(500, "all")]["spearman"] == pytest.approx(1) and rows[(500, "all")]["cells"] == 4
    other = write_run(tmp_path / "utm", [line(1, True, 40, 100, 100)], crs="EPSG:32634")
    with pytest.raises(SystemExit, match="different coordinate systems"):
        pc.compare({**samples, "c": {"run": other}}, "a", ["c"], [500], pc.BANDS)


def test_cube_counts_the_keys(tmp_path):
    samples = synthetic(tmp_path)
    result = pc.cube(samples, ["a"], 1000, ["length"])
    row = result["rows"][0]
    assert row["lines"] == 7 and row["spots"] == 5
    assert row["line_keys"] == 3  # cells of 1 km: (0,0) 30-60 (four lines), (1,0) 60-100, (2,2) 300-600
    assert row["line_keys_km2"] == 0.75 and row["line_bytes_km2"] == 9
    assert row["spot_keys"] == 3  # groups 1, 4 and 5 share (0,0) 30-60
    # A member's better values make a spot's bins: group 1 over trees only with its first line
    rows = [line(1, True, 40, 100, 100, clearance_m=1, over_trees_buildings=True, anchor1_wall_angle=50),
            line(1, False, 45, 1500, 100, clearance_m=12, over_trees_buildings=False),
            line(2, True, 40, 200, 100, clearance_m=1, over_trees_buildings=True, anchor1_wall_angle=50,
                 anchor1_prominence_m="", height_max_m=60)]
    run = write_run(tmp_path / "best", rows)
    sample = {"x": {"run": run, "grid": {"area_km2": 2.0}}}
    row = pc.cube(sample, ["x"], 1000, list(pc.DIMS))["rows"][0]
    assert row["line_keys"] == 3 and row["spot_keys"] == 2  # group 1: clearance 10-20, not over trees, wall 0-30
    lines = pc.read_lines(run)
    values = pc.line_values(lines)
    rep, best = pc.spot_values(lines, values)
    assert rep.tolist() == [0, 2] and best["clearance"].tolist() == [12, 1] and best["trees"].tolist() == [False, True]
    assert best["wall"].tolist() == [20, 50] and values["prominence"][2] == 6  # the other anchor's
    assert pc.bins(np.array([-1, 0, 2, 4.9, 25, np.inf, np.nan]), pc.EDGES["clearance"]).tolist() == [0, 0, 1, 1, 4,
                                                                                                    4, -1]
    with pytest.raises(SystemExit, match="unknown dimensions"):
        pc.cube(sample, ["x"], 1000, ["colour"])
