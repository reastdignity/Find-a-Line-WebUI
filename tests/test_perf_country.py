"""tools/perf_country.py: the mirrored mosaic, the T(L) patch of the sag estimator (equal to the
plain search at a constant tension), compare and cube on synthetic lines.csv, the relief blocks and
sample cells, the strata of estimate (offline)."""

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
    # --lean: lines.npz instead of lines.csv and lines.geojson, the same lines read back
    lean = subprocess.run([sys.executable, os.path.join("tools", "perf_country.py"), "profile", "--lean",
                           "--out", str(tmp_path / "out"), "--name", "lean", "--", *common,
                           "--data-dir", str(tmp_path / "lean")],
                          cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert lean.returncode == 0, lean.stdout + lean.stderr
    run = json.load(open(tmp_path / "out" / "samples.json"))["lean"]["run"]
    assert sorted(os.listdir(run)) == ["lines.npz", "run.json"]
    a, b = pc.read_lines(sample["run"]), pc.read_lines(run)
    assert a["group"].tolist() == b["group"].tolist() and a["representative"].tolist() == b["representative"].tolist()
    assert np.allclose(a["length_m"], b["length_m"], atol=0.05) and np.allclose(a["anchor1_easting"],
                                                                                 b["anchor1_easting"], atol=0.01)


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


def test_edge_fraction():
    circle = pc.sample_geometry(["--radius", "2000"])
    assert pc.edge_fraction(circle, 0) == 1.0
    assert pc.edge_fraction(circle, 5) > 0.99
    assert 0.5 < pc.edge_fraction(circle, 2000) < 0.65  # a disc as wide as the area: about 0.58
    assert pc.edge_fraction(circle, 500) > pc.edge_fraction(circle, 1000) > pc.edge_fraction(circle, 2000)


def _bench(tmp_path, name, saving, pairs_cpu, pairs_wall, physical):
    stages = [{"stage": "Step 5: Compute saving results", "wall_s": saving, "cpu_s": saving},
              {"stage": "Step 2: Compute anchor prominence and drop", "wall_s": saving / 2, "cpu_s": saving},
              {"stage": "Step 3: Compute anchor pairs", "wall_s": pairs_wall, "cpu_s": pairs_cpu}]
    with open(tmp_path / name, "w") as f:
        json.dump({"machine": {"physical_cores": physical}, "searches": {"M": {"stages": stages}}}, f)
    return name


def _stages(cpu):
    return [{"stage": "Step 1: Download terrain tiles", "wall_s": 50.0, "cpu_s": 1.0},
            {"stage": "Step 1: (between bars)", "wall_s": 9.0, "cpu_s": 1.0},  # index answers: left out
            {"stage": "Step 1: Compute stitching terrain", "wall_s": 4.0, "cpu_s": 4.0},
            {"stage": "Step 3: Compute anchor pairs", "wall_s": 1.0, "cpu_s": cpu},
            {"stage": "Step 4: Compute grouping lines", "wall_s": 0.5, "cpu_s": 0.5},
            {"stage": "Step 5: Compute saving results", "wall_s": 9.0, "cpu_s": 9.0}]


def test_estimate_of_a_small_country(tmp_path):
    def sample(lines, cpu):
        return {"args": ["--radius", "2000"], "grid": {"width": 4600, "height": 4600, "area_km2": np.pi * 4},
                "summary": {"lines": lines, "spots": lines // 10}, "stages": _stages(cpu)}

    columns = ["km2", "edge", "lines", "spots", "relief1", "steep45_1"]
    # The country: 940 km² without steep pixels and of a relief below 100 m, 60 km² with 2-5 % of
    # steep pixels; its outline holds 40 km² of a lake too, which the flattest stratum loses
    joint = {"steep_edges": [0, 0.01, 0.02, 0.05, "inf"], "relief_edges": [0, 100, 200, "inf"],
             "bins": [[0, 0, 980], [2, 2, 60]]}
    relief = {"proxies": ["relief1", "steep45_1"], "countries": {"X": {"joint": {"1": joint}}},
              "samples": {"flat-S-1m": {"place": "flat", "band": "S", "res": 1.0, "columns": columns,
                                        # the second cell lies at the edge of the sample: left out
                                        "cells": [[1, 1, 10, 1, 20, 0], [1, 0.4, 5, 0, 30, 0]]},
                          "rock-S-1m": {"place": "rock", "band": "S", "res": 1.0, "columns": columns,
                                        "cells": [[1, 1, 200, 10, 400, 0.03], [1, 1, 0, 0, 50, 0]]}}}
    with open(tmp_path / "relief.json", "w") as f:
        json.dump(relief, f)
    inputs = {"bands": {"S": [30, 300]}, "variants": {"30-300 m": ["S"]},
              "strategies": {"1 m": {"S": 1}, "2 m": {"S": 2}}, "cores_km": [5, 10], "pixel_bytes": 100,
              "margin_m": 300, "link_mb_s": 100, "reference": "ref", "relief": "relief.json", "bootstrap": 60,
              "min_edge": {"S": 0.5},
              "strata": {"S": {"res": 1, "window": 1, "relief_edges": [100], "steep_edges": [0.01]}},
              "machines": {"ref": {"bench": _bench(tmp_path, "ref.json", 4.0, 200.0, 10.0, 12), "memory_gb": 50},
                           "slow": {"bench": _bench(tmp_path, "slow.json", 6.0, 220.0, 25.0, 6), "memory_gb": 40}},
              "countries": {"X": {"name": "X", "area_km2": 1000,
                                  "data": {"1": {"terrain": {"download_mb_km2": 8, "cache_mb_km2": 2, "files_per_km2": 1},
                                                 "surface": {"download_mb_km2": 8, "cache_mb_km2": 2, "files_per_km2": 1}}},
                                  "service": {"mb_s": 10, "requests_per_min": 30, "index_s": 0}}}}
    samples = {"flat-S-1m": sample(100, 20.0), "rock-S-1m": sample(1000, 110.0), "rock-S-1m-45": sample(9, 1.0)}
    result = pc.estimate(inputs, samples, str(tmp_path))
    assert result["factors"]["ref"] == {"serial": 1.0, "cpu": 1.0, "parallel_cores": 20.0, "physical_cores": 12}
    assert result["factors"]["slow"]["serial"] == 1.5 and result["factors"]["slow"]["parallel_cores"] == 8.8
    assert sorted(result["metrics"]) == ["flat-S-1m", "rock-S-1m"]  # a variant is no place of the strata
    strata = result["strata"]["X S"]
    assert strata["km2"] == [940, 0, 60] and strata["places"] == ["flat", "rock"]
    assert strata["strata"] == ["steep < 1 %, relief 0-100 m", "steep < 1 %, relief >= 100 m", "steep >= 1 %"]
    assert strata["lines_per_km2"] == [5, None, 200] and strata["spots_per_km2"] == [0.5, None, 10]
    rows = {(r["strategy"], r["dsm"], r["machine"], r["scenario"]): r for r in result["rows"]}
    assert len(rows) == 24
    ref, slow = rows[("1 m", True, "ref", "mid")], rows[("1 m", True, "slow", "mid")]
    assert ref["lines"] == 940 * 5 + 60 * 200 and ref["spots"] == 940 * 0.5 + 60 * 10
    # The bootstrap: both places twice (flat: 10 lines per km² in the flattest stratum; rock: none) or one each
    assert rows[("1 m", True, "ref", "low")]["lines"] == 940 * 0 + 60 * 200
    assert rows[("1 m", True, "ref", "high")]["lines"] == 940 * 10 + 60 * 200
    assert ref["download_tb"] == 0.016 and ref["cache_tb"] == 0.004
    assert ref["download_days"] == round(2000 * 60 / 30 / 86400, 2)  # the rate of requests decides
    assert rows[("1 m", False, "ref", "mid")]["download_tb"] == 0.008  # without the surface model
    model = result["models"]["S 1 m"]
    m = result["metrics"]
    assert model["places"] == 2 and model["grid_s_per_mpx"] == pytest.approx(4.0 / 21.16)  # download, index left out
    slope = (m["rock-S-1m"]["line_cpu_per_km2"] - m["flat-S-1m"]["line_cpu_per_km2"]) / \
        (m["rock-S-1m"]["lines_per_km2"] - m["flat-S-1m"]["lines_per_km2"])
    assert model["cpu_b"] == pytest.approx(slope) and model["cpu_a"] > 0
    [band] = ref["bands"]
    side = band["core_km"] * 1000 + 2 * (300 + 300 + 2)
    serial = model["grid_s_per_mpx"] * 1000 * (side / (band["core_km"] * 1000)) ** 2 + \
        model["count_s_per_line"] * ref["lines"]
    assert band["serial_s"] == round(serial)
    assert band["line_wall_s"] == round((model["cpu_a"] * 1000 + model["cpu_b"] * ref["lines"]) / 20)
    assert slow["bands"][0]["wall_s"] > band["wall_s"] > 0 and ref["compute_hours"] == round(band["wall_s"] / 3600, 2)
    # No sample at 2 m and no place measured at both resolutions: no estimate
    assert rows[("2 m", True, "ref", "mid")]["compute_days"] is None


def test_strata_helpers():
    spec = {"window": 3, "relief_edges": [100, 300], "steep_edges": [0.005, 0.05]}
    steep = np.array([0, 0, 0, 0.004, 0.005, 0.04, 0.05, 0.9])
    relief = np.array([0, 99, 100, 2000, 0, 50, 10, 900])
    assert pc.strata_of(steep, relief, spec).tolist() == [0, 0, 1, 2, 3, 3, 4, 4]
    assert pc.strata_labels(spec) == ["steep < 0.5 %, relief 0-100 m", "steep < 0.5 %, relief 100-300 m",
                                      "steep < 0.5 %, relief >= 300 m", "steep 0.5-5 %", "steep >= 5 %"]
    joint = {"steep_edges": pc.HIST_EDGES["steep"], "relief_edges": pc.HIST_EDGES["relief"],
             "bins": [[0, 0, 1.0], [0, 4, 2.0], [0, 12, 3.0], [11, 0, 4.0], [12, 30, 5.0], [len(pc.HIST_EDGES["steep"]) - 2, 0, 6.0]]}
    # the fine bins: no steep pixel and relief 0, 100 or 300 m; steep from 0.005 and 0.0055; the open last one
    assert pc.HIST_EDGES["steep"][11] == pytest.approx(0.005) and pc.HIST_EDGES["relief"][12] == 300
    assert pc.strata_areas({"joint": {"3": joint}}, spec).tolist() == [1, 2, 3, 9, 6]
    filled = pc._filled(np.array([np.nan, 2.0, np.nan, np.nan, 8.0, np.nan]))
    assert filled.tolist() == [2, 2, 2, 8, 8, 8]  # a gap as near to both takes the lower one
    assert pc.band_of("ch-alps-area-L-10m") == ("ch-alps-area", "L", 10.0) and pc.band_of("bench") is None


def test_tile_blocks(tmp_path):
    """A 0.1° GeoTIFF at 1″, flat in its west half and a 50° slope in its east half: blocks of
    about 1 km, relief and steep shares per block and over windows."""
    import rasterio as rio
    from rasterio.transform import from_origin
    lat0, lon0, n = 46.0, 7.0, 360
    dy = 1 / 3600 * pc.EARTH_M_PER_DEG
    dx = dy * np.cos(np.radians(lat0 + 0.05))
    z = np.zeros((n, n))
    z[:, n // 2:] = np.tan(np.radians(50)) * dx * np.arange(n - n // 2)[None, :]
    path = str(tmp_path / "t.tif")
    with rio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs="EPSG:4326",
                  transform=from_origin(lon0, lat0 + 0.1, 1 / 3600, 1 / 3600)) as out:
        out.write(z.astype(np.float32), 1)
    b = pc.tile_blocks(path)
    rows, cols = b["km2"].shape
    assert rows == round(n * dy / 1000) and cols == round(n * dx / 1000)
    assert b["km2"].sum() == pytest.approx(n * dy * n * dx / 1e6, rel=1e-3)
    assert b["relief1"][:, 0].max() == 0 and b["steep30_1"][:, 0].max() == 0  # the flat west
    assert b["steep45_1"][:, -1].min() > 0.95 and b["relief1"][:, -1].min() > 900  # 50°, about 0.8 km a block
    assert (b["relief3"] >= b["relief1"] - 1e-9).all() and (b["relief5"] >= b["relief3"] - 1e-9).all()
    found = pc.proxies_at({(46, 7): b}, np.array([7.01, 7.09, 8.5]), np.array([46.05, 46.05, 46.05]))
    assert found["steep45_1"][0] == 0 and found["steep45_1"][1] > 0.95 and np.isnan(found["steep45_1"][2])


def test_sample_cells(tmp_path):
    """A circle of 1.5 km in EPSG:2180: its 1 km cells (area inside, edge fraction for the band's
    lines), the lines and spots of each by its first anchor, scaled lines from another run."""
    import area as ar
    from shapely.geometry import Point
    centre = ar.project(Point(554000, 254000), "EPSG:2180", "EPSG:4326")
    rows = [line(1, True, 40, 554100, 254100), line(1, False, 45, 554200, 254300),
            line(2, True, 80, 553100, 254100)]
    run = write_run(tmp_path / "run", rows)
    sample = {"args": ["--lat", str(centre.y), "--lon", str(centre.x), "--radius", "1500"], "run": run,
              "grid": {"crs": "EPSG:2180"}}
    found = pc.sample_cells(sample, 30, 300, {})
    cells = [dict(zip(found["columns"], r)) for r in found["cells"]]
    km2 = sum(c["km2"] for c in cells)
    assert km2 == pytest.approx(np.pi * 1.5 ** 2, rel=0.01)
    assert sum(c["lines"] for c in cells) == 3 and sum(c["spots"] for c in cells) == 2
    inner = [c for c in cells if c["km2"] > 0.99]
    assert inner and all(c["edge"] > 0.85 for c in inner)  # lines up to 300 m from a whole cell inside
    assert min(c["edge"] for c in cells) < min(c["edge"] for c in inner) - 0.1  # a sliver at the edge
    assert all(c["relief1"] is None for c in cells)  # no relief tiles given
    scaled = pc.sample_cells(sample, 30, 300, {}, pc.read_lines(run), (10.0, 2.0))
    assert sum(r[2] for r in scaled["cells"]) == 30 and sum(r[3] for r in scaled["cells"]) == 4


def test_virtual_cells_of_a_place_measured_at_another_resolution():
    """Zion's M band ran out of memory at 2 m: its 5 m cells stand at 2 m, times the median ratio of
    the places measured at both."""
    columns = ["km2", "edge", "lines", "spots", "relief3", "steep45_3"]
    found = {"a-M-2m": {"place": "a", "band": "M", "res": 2.0, "columns": columns, "cells": [[1, 1, 100, 10, 50, 0]]},
             "a-M-5m": {"place": "a", "band": "M", "res": 5.0, "columns": columns, "cells": [[1, 1, 5, 4, 50, 0]]},
             "b-M-2m": {"place": "b", "band": "M", "res": 2.0, "columns": columns, "cells": [[1, 1, 60, 6, 80, 0]]},
             "b-M-5m": {"place": "b", "band": "M", "res": 5.0, "columns": columns, "cells": [[1, 1, 2, 2, 80, 0]]},
             "z-M-5m": {"place": "z", "band": "M", "res": 5.0, "columns": columns,
                        "cells": [[1, 1, 10, 3, 300, 0.2], [0.5, 0.8, 0, 0, 20, 0]]}}
    samples = {"a-M-2m": {"summary": {"lines": 100, "spots": 10}}, "a-M-5m": {"summary": {"lines": 5, "spots": 4}},
               "b-M-2m": {"summary": {"lines": 60, "spots": 6}}, "b-M-5m": {"summary": {"lines": 2, "spots": 2}}}
    inputs = {"strata": {"M": {"res": 2, "window": 3, "relief_edges": [100], "steep_edges": [0.005]}}}
    added = pc.virtual_cells(found, samples, inputs)
    assert list(added) == ["z-M-2m"]
    z = added["z-M-2m"]
    # lines 20 and 30 times (median 25), spots 2.5 and 3 times (median 2.75)
    assert z["res"] == 2.0 and z["place"] == "z" and z["cells"] == [[1, 1, 250, 8.25, 300, 0.2], [0.5, 0.8, 0, 0, 20, 0]]
    assert z["cells_from"].startswith("z-M-5m × 25 lines, × 2.75 spots")
    assert pc.virtual_cells({k: v for k, v in found.items() if k != "z-M-5m"}, samples, inputs) == {}
