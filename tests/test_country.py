"""The country driver (country.py, docs/country-precompute/contract.md, section 3): a small country
of the Żabi Koń clip reprojected to EPSG:8353 (negative coordinates), offline. Its cube equals the
counts of one grid, whether counted at once, resumed or by two worker processes; a tile failing
once is retried, twice it is failed; a partial cube needs --partial."""

import json
import os
import sqlite3
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8"}
SQUARE = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                              [19.7522, 50.1580], [19.7522, 50.1546]]]}
ID = "testland"


def _krovak_clip(folder) -> str:
    """The clip reprojected to EPSG:8353 (S-JTSK [JTSK03] / Krovak East North), 1 m."""
    import rasterio as rio
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    out = os.path.join(folder, "clip_8353.tif")
    with rio.open(CLIP) as src:
        transform, width, height = calculate_default_transform(src.crs, "EPSG:8353", src.width, src.height,
                                                               *src.bounds, resolution=1.0)
        profile = src.profile.copy()
        profile.update(crs="EPSG:8353", transform=transform, width=width, height=height, nodata=np.nan,
                       dtype="float32")
        with rio.open(out, "w", **profile) as dst:
            reproject(rio.band(src, 1), rio.band(dst, 1), src_nodata=src.nodata, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
    return out


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """The offline environment (also of the worker processes) and the test country's config: bands S
    and M in the layer, C a control band of S's [60, 150)."""
    saved = {k: os.environ.get(k) for k in OFFLINE_ENV}
    os.environ.update(OFFLINE_ENV)
    base = tmp_path_factory.mktemp("country")
    area = base / "square.geojson"
    area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    config = {"id": ID, "name": "Testland", "source": "files", "area": str(area),
              "bands": [{"name": "S", "lengths": [30, 150], "resolution": 1.0, "model": "formula",
                         "slope_threshold": 45, "core_m": 200, "layer": True},
                        {"name": "M", "lengths": [150, 300], "resolution": 2.0, "model": "sag",
                         "slope_threshold": 45, "core_m": 400, "layer": True},
                        {"name": "C", "lengths": [60, 150], "resolution": 2.0, "model": "formula",
                         "slope_threshold": 45, "core_m": 400, "layer": False}],
              "tension": [[30, 2.5], [300, 6.0]], "rig": {"webbing_weight": 41.0, "stretch": 2.1},
              "options": {"nmpt": "off", "water": "off", "coastline": "copernicus", "fill_gaps": "off",
                          "elevation_file": _krovak_clip(str(base))}}
    yield {"base": base, "config": config}
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _data_dir(env, name: str) -> str:
    """A data folder with the test country's country.json (its config only)."""
    data = env["base"] / name
    folder = data / "countries" / ID
    folder.mkdir(parents=True)
    (folder / "country.json").write_text(json.dumps({"config": env["config"]}))
    return str(data)


def _country(*args) -> int:
    import country
    return country.main(list(args))


def _cube(data: str) -> dict:
    folder = os.path.join(data, "countries", ID, "cube")
    out = {name: np.load(os.path.join(folder, name)) for name in os.listdir(folder) if name.endswith(".npy")}
    assert len(out) == 8
    return out


def _manifest(data: str):
    db = sqlite3.connect(os.path.join(data, "countries", ID, "manifest.sqlite"))
    try:
        return db.execute("SELECT band, name, status, attempts, error FROM tiles ORDER BY rowid").fetchall()
    finally:
        db.close()


def _assert_same_cube(a: dict, b: dict):
    assert sorted(a) == sorted(b)
    for name in a:
        assert np.array_equal(a[name], b[name]), name


@pytest.fixture(scope="module")
def full(env):
    """A whole run in this process, and the counts of one grid per layer band (count_tile with
    core=None and a TileCounter over the band's whole grid) built into a cube."""
    import country
    import countcube
    import search
    data = _data_dir(env, "full")
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--yes") == 0
    folder = os.path.join(data, "countries", ID)
    with open(os.path.join(folder, "country.json"), encoding="utf-8") as f:
        state = json.load(f)
    c = country.Country.from_config(state["config"])
    reference = os.path.join(env["base"], "reference")
    tiles = []
    for band in c.bands:
        if not band.layer:
            continue
        plan = country.band_plan(c, band, folder, data)
        os.makedirs(plan.paths.work, exist_ok=True)
        counter = countcube.TileCounter(plan.grid, tuple(state["origin"]), None, band.lengths, False)
        search.count_tile(plan, search.prepare_data(plan), None, counter, country.tension_table(c, band, plan))
        path = os.path.join(reference, f"{band.name}.npz")
        os.makedirs(reference, exist_ok=True)
        countcube.save_tile(path, counter.result(), {})
        tiles.append(path)
    countcube.build(tiles, os.path.join(reference, "cube"), {"origin": state["origin"], "crs": state["crs"]})
    return {"data": data, "state": state, "reference": _cube_folder(os.path.join(reference, "cube"))}


def _cube_folder(folder: str) -> dict:
    return {name: np.load(os.path.join(folder, name)) for name in os.listdir(folder) if name.endswith(".npy")}


def test_cube_equals_one_grid(env, full):
    """The cube of the tiles equals the counts of one grid, in a CRS of negative coordinates, with
    at least 2 x 2 tiles; cube.json as the contract gives it."""
    data, state = full["data"], full["state"]
    assert state["crs"] == "EPSG:8353" and state["origin"][0] < 0 and state["origin"][1] < 0
    rows = _manifest(data)
    assert sum(r[0] == "S" for r in rows) >= 4 and sum(r[0] == "M" for r in rows) >= 2
    assert all(r[2] == "done" for r in rows)
    assert all(r[1].startswith("E-") and "_N-" in r[1] for r in rows)
    cube = _cube(data)
    _assert_same_cube(cube, full["reference"])
    folder = os.path.join(data, "countries", ID)
    with open(os.path.join(folder, "cube", "cube.json"), encoding="utf-8") as f:
        info = json.load(f)
    assert info["totals"]["lines"] > 100 and info["totals"]["spots"] > 10
    assert info["partial"] is False and info["dsm"] is False and info["water"] is False
    assert info["config"] == state["hash"] and info["origin"] == state["origin"]
    assert [b["name"] for b in info["bands"]] == ["S", "M", "C"] and [b["layer"] for b in info["bands"]] == \
        [True, True, False]
    m = info["bands"][1]
    assert m["done"] == m["tiles"] and m["seconds"] > 0
    assert m["params"] == {"source": "files", "min_length": 150, "max_length": 300, "resolution": 2.0,
                           "model": "sag", "slope_threshold": 45, "nmpt": "off", "water": "off",
                           "coastline": "copernicus", "fill_gaps": "off", "pretension": 6.0, "stretch": 2.1,
                           "webbing_weight": 41.0}
    assert os.path.exists(os.path.join(folder, "cube", "area.geojson"))
    # every tile's meta: the config, the origin, the counts, the data used
    import countcube
    path = os.path.join(folder, "tiles", "S", rows[0][1] + ".npz")
    counts, meta = countcube.load_tile(path)
    assert meta["config"] == state["hash"] and meta["origin"] == state["origin"] and meta["band"] == "S"
    assert meta["lines"] == counts.lines and meta["spots"] == len(counts.spot_ids) and "dropped" in meta
    assert meta["seconds"]["count"] >= 0 and meta["threads"] >= 1 and meta["data"] and "peak_memory" in meta
    # its profile (`country profile`): seconds and CPU per stage, the counter, the memory, the file reads
    assert "finding anchors" in meta["stages"] and all(len(v) == 2 for v in meta["stages"].values())
    assert meta["memory"]["rss"] > 0 and meta["memory"]["private"] > 0 and meta["cpu_seconds"] > 0
    assert len(meta["sink"]) == 2 and meta["io"]["read"] >= 0 and meta["threads_max"] >= meta["threads"]


def test_status_and_compare(env, full, capsys):
    """status shows the bands; compare writes compare.json of the control band against S's part."""
    data = full["data"]
    capsys.readouterr()
    assert _country("status", ID, "--data-dir", data) == 0
    out = capsys.readouterr().out
    assert "Testland" in out and "Cube built" in out
    assert _country("compare", ID, "--data-dir", data, "--control", "C", "--against", "S") == 0
    with open(os.path.join(data, "countries", ID, "compare.json"), encoding="utf-8") as f:
        result = json.load(f)
    assert result["lengths"] == [60, 150] and result["lines"]["control"] > 0 and result["lines"]["against"] > 0
    assert set(result["cells"]) == {"1", "4"} and result["seconds"]["control"] > 0
    capsys.readouterr()
    assert _country("profile", ID, "--data-dir", data) == 0
    out = capsys.readouterr().out
    assert "Band S:" in out and "finding anchors" in out and "memory of a tile" in out


def test_resume(env, full):
    """--max-tiles 1, then the rest: the same cube."""
    data = _data_dir(env, "resume")
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--bands", "S,M", "--max-tiles", "1",
                    "--yes") == 0
    rows = _manifest(data)
    assert [r[2] for r in rows].count("done") == 1
    assert not os.path.exists(os.path.join(data, "countries", ID, "cube", "cube.json"))
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--bands", "S,M", "--yes") == 0
    _assert_same_cube(_cube(data), full["reference"])


def test_two_processes(env, full):
    """Two worker processes: the same cube, each with its log."""
    data = _data_dir(env, "two")
    assert _country("run", ID, "--data-dir", data, "--processes", "2", "--bands", "S,M", "--yes") == 0
    _assert_same_cube(_cube(data), full["reference"])
    logs = os.path.join(data, "countries", ID, "logs")
    assert {"run.log", "worker-0.log", "worker-1.log"} <= set(os.listdir(logs))
    timelines = [n for n in os.listdir(logs) if n.startswith("samples-") and n.endswith(".csv")]
    assert len(timelines) == 1
    with open(os.path.join(logs, timelines[0]), encoding="utf-8") as f:
        rows = f.read().splitlines()
    assert rows[0].startswith("time,seconds,machine_cpu_pct,") and len(rows) >= 3  # the start and the end
    db = sqlite3.connect(os.path.join(data, "countries", ID, "manifest.sqlite"))
    try:
        workers = {r[0] for r in db.execute("SELECT worker FROM tiles WHERE band IN ('S', 'M')")}
        control = {r[0] for r in db.execute("SELECT status FROM tiles WHERE band = 'C'")}
    finally:
        db.close()
    assert workers and workers <= {"slot-0", "slot-1"} and control == {"pending"}


def test_timeline_counts_the_process_tree(tmp_path):
    """The run's timeline counts each worker's process tree: on Windows a venv's python.exe only
    starts the interpreter as its child, so the worker's own process holds a few MB and no CPU."""
    import subprocess
    import time
    import psutil
    import country
    script = tmp_path / "busy.py"
    script.write_text("import subprocess, sys, time\n"
                      "if sys.argv[1:] == ['child']:\n"
                      "    held = b'x' * 300_000_000\n"
                      "    end = time.time() + 60\n"
                      "    while time.time() < end:\n"
                      "        pass\n"
                      "else:\n"
                      "    subprocess.run([sys.executable, __file__, 'child'])\n", encoding="utf-8")
    os.makedirs(tmp_path / "logs")
    m = country.Manifest(str(tmp_path))
    worker = subprocess.Popen([sys.executable, str(script)])
    try:
        deadline = time.monotonic() + 60
        while sum(p.memory_info().rss for p in psutil.Process(worker.pid).children(recursive=True)) < 3e8:
            assert time.monotonic() < deadline, "the child never held its 300 MB"
            time.sleep(0.2)
        samples = country._RunSamples(str(tmp_path))
        samples.sample([worker.pid], m)
        time.sleep(1)
        samples.sample([worker.pid], m)
        with open(samples.path, encoding="utf-8") as f:
            header, *rows = f.read().splitlines()
        last = dict(zip(header.split(","), rows[-1].split(",")))
        assert last["workers"] == "1" and float(last["workers_cores"]) > 0
        assert float(last["workers_rss_gib"]) >= 0.27 and float(last["workers_private_gib"]) >= 0.27
    finally:
        m.close()
        try:
            tree = psutil.Process(worker.pid)
            tree = [tree] + tree.children(recursive=True)
        except psutil.Error:
            tree = []
        for process in tree:
            try:
                process.kill()
            except psutil.Error:
                pass
        worker.wait(30)


def test_failing_tiles(env, full, monkeypatch, capsys):
    """A tile failing once is counted again; failing twice it is failed, status shows it, and build
    refuses the partial cube without --partial."""
    import search
    data = _data_dir(env, "failing")
    original = search.count_tile
    failures = {"left": 1, "core": None}

    def flaky(plan, tile_data, core, sink, sag_table=None):
        if failures["core"] is None:
            failures["core"] = core
        if core == failures["core"] and failures["left"]:
            failures["left"] -= 1
            raise RuntimeError("a test failure")
        return original(plan, tile_data, core, sink, sag_table)

    monkeypatch.setattr(search, "count_tile", flaky)
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--bands", "S", "--yes") == 0
    rows = [r for r in _manifest(data) if r[0] == "S"]
    assert all(r[2] == "done" for r in rows) and rows[0][3] == 2 and all(r[3] == 1 for r in rows[1:])

    data = _data_dir(env, "failed")
    failures.update(left=10, core=None)
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--bands", "S", "--yes") == 1
    rows = [r for r in _manifest(data) if r[0] == "S"]
    assert rows[0][2] == "failed" and rows[0][3] == 2 and "a test failure" in rows[0][4]
    assert all(r[2] == "done" for r in rows[1:])
    capsys.readouterr()
    assert _country("status", ID, "--data-dir", data) == 0
    out = capsys.readouterr().out
    assert "failed" in out and "a test failure" in out and rows[0][1] in out
    assert _country("build", ID, "--data-dir", data) == 1
    assert "--partial" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(data, "countries", ID, "cube", "cube.json"))
    assert _country("build", ID, "--data-dir", data, "--partial") == 0
    with open(os.path.join(data, "countries", ID, "cube", "cube.json"), encoding="utf-8") as f:
        info = json.load(f)
    assert info["partial"] is True and any("Partial" in n for n in info["notes"])


def test_worker_count(monkeypatch):
    """The processes of a run from the measured memory of a count (WORKER_BASE plus
    COUNT_PIXEL_BYTES per pixel of the largest tile), at most the physical cores, at least one."""
    import country
    monkeypatch.setattr(country.psutil, "cpu_count", lambda logical=True: 24 if logical else 12)
    per = country.WORKER_BASE + country.COUNT_PIXEL_BYTES * 38_500_000
    assert country.worker_count(38_500_000, 31 * 2 ** 30) == (11, per)  # Slovakia's S tiles, 31 GiB free
    assert country.worker_count(38_500_000, 100 * 2 ** 30)[0] == 12
    assert country.worker_count(38_500_000, 2 ** 30)[0] == 1


def test_config_hash_follows_the_obstacle_rule(monkeypatch):
    """Without the surface model the hash is the one of before (Slovakia's tiles keep theirs); with
    it, another obstacle rule gives another hash, so its tiles are counted again."""
    import hashlib
    import country
    import obstacles
    config = {"id": "x", "options": {"nmpt": "off"}}
    before = hashlib.sha256(json.dumps({"config": config, "area_sha256": "a"}, sort_keys=True).encode("utf-8"))
    assert country.config_hash(config, "a") == before.hexdigest()
    marked = {"id": "x", "options": {"nmpt": "mark"}}
    first = country.config_hash(marked, "a")
    assert first != country.config_hash({"id": "x", "options": {"nmpt": "off"}}, "a")
    monkeypatch.setattr(obstacles, "RULE", {"radius": 3, "min_height": 1.0})
    assert country.config_hash(marked, "a") != first


def test_outline_within_a_box(tmp_path):
    """The option "within" clips the outline of the area spec to its box (S,W,N,E)."""
    import country
    from shapely.geometry import shape
    area = tmp_path / "square.geojson"
    area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}))
    c = country.Country(id="boxed", name="Boxed", source="files", area=str(area), bands=(), tension=(),
                        options={"within": "50.1500,19.7500,50.1600,19.7556"})
    country._write_outline(c, str(tmp_path), str(tmp_path))
    with open(tmp_path / "area.geojson", encoding="utf-8") as f:
        bounds = shape(json.load(f)["geometry"]).bounds
    assert bounds == pytest.approx((19.7522, 50.1546, 19.7556, 50.1580))


def _tile(name, core):
    import types
    return types.SimpleNamespace(name=name, core=core)


def test_heaviest_tiles_first(tmp_path):
    """A manifest of schema v1 gets the column of the weights; a run claims the tiles under the
    most lines of the tiles done already first (_weights: the cores that overlap, not those that
    only touch), the others after them in their order."""
    import cache
    import country
    db = sqlite3.connect(tmp_path / "manifest.sqlite")
    cache.migrate(db, country.MIGRATIONS[:1])
    db.execute("INSERT INTO tiles (band, name, core) VALUES ('A', 'a1', '[0, 0, 10, 10]')")
    db.commit()
    db.close()
    m = country.Manifest(str(tmp_path))
    try:
        assert "weight" in [r[1] for r in m.db.execute("PRAGMA table_info(tiles)")]
        m.add_tiles("B", [_tile("b2", (20, 0, 40, 20)), _tile("b1", (0, 0, 20, 20)), _tile("b3", (0, 20, 20, 40))])
        assert country._weights(m, ["B"]) == {}  # nothing done yet: the order they were added
        m.add_tiles("A", [_tile("a2", (10, 0, 20, 10)), _tile("a3", (0, 10, 10, 20))])
        m.db.execute("UPDATE tiles SET status = 'done', lines = CASE name WHEN 'a1' THEN 5 WHEN 'a2' THEN 100 "
                     "ELSE 0 END WHERE band = 'A'")
        weights = country._weights(m, ["B"])
        assert weights == {("B", "b2"): 0.0, ("B", "b1"): 105.0, ("B", "b3"): 0.0}
        m.set_weights(weights)
        m.set_run(["B"], None, 2)
        assert [m.claim("w", 24)[1] for _ in range(3)] == ["b1", "b2", "b3"] and m.claim("w", 24) is None
    finally:
        m.close()


def test_threads_follow_the_busy_workers(tmp_path, monkeypatch):
    """A tile claimed while every worker is busy gets the cores they share; as the others end, its
    count takes theirs (_Rethreading sets numba's threads between the parts, at most every
    RETHREAD_SECONDS); the parts reach the counter unchanged."""
    import numba
    import country
    m = country.Manifest(str(tmp_path))
    try:
        m.add_tiles("B", [_tile(f"b{k}", (k, 0, k + 1, 1)) for k in range(6)])
        m.set_run(["B"], None, 4)
        assert m.claim("w", 24)[3] == 6  # 4 workers busy
        m.db.execute("UPDATE tiles SET status = 'done' WHERE status = 'pending'")
        assert m.threads(24) == 24  # the last tile alone
    finally:
        m.close()
    clock, calls, parts = [0.0], [], []
    monkeypatch.setattr(numba, "set_num_threads", calls.append)
    most = numba.config.NUMBA_NUM_THREADS
    sink = country._Rethreading(parts.append, lambda: most, 1, clock=lambda: clock[0])
    sink("part 1")
    assert parts == ["part 1"] and calls == []
    clock[0] = country.RETHREAD_SECONDS
    sink("part 2")
    assert parts == ["part 1", "part 2"] and calls == ([most] if most > 1 else []) and sink.most == most


def test_stage_clock():
    """_StageClock sums the wall and CPU seconds per stage of the bars, "other" between them; the
    updates of a stage and the states of the steps do not move it."""
    import country
    t, c = [0.0], [0.0]
    clock = country._StageClock(clock=lambda: t[0], cpu=lambda: c[0])

    def at(seconds, cpu, state):
        t[0], c[0] = seconds, cpu
        clock(state)

    at(1, 1, {"bar": "Compute", "stage": "stitching terrain", "done": False})
    at(3, 2, {"bar": "Compute", "stage": "stitching terrain", "done": False})  # an update
    at(4, 3, {"bar": "Compute", "stage": "stitching terrain", "done": True})
    at(5, 3.5, {"bar": "", "stage": "", "done": True, "step": "Step 3/3: evaluating anchor pairs"})
    at(6, 4, {"bar": "Compute", "stage": "anchor pairs", "done": False})
    at(10, 20, {"bar": "Compute", "stage": "anchor pairs", "done": True})
    t[0], c[0] = 11, 21
    assert clock.result() == {"other": [4.0, 3.0], "stitching terrain": [3.0, 2.0], "anchor pairs": [4.0, 16.0]}


def test_heavy_tiles_take_the_spare_cores(tmp_path):
    """A heavy tile (its weight at least HEAVY_SHARE of the run's largest) shares the cores left
    after LIGHT_CORES per light tile running with the other heavy ones; a light tile keeps at most
    LIGHT_THREADS while a heavy one runs, and the share of before when none does (the first band
    of a country has no weights: every tile light, the rule of before)."""
    import country
    m = country.Manifest(str(tmp_path))
    try:
        m.add_tiles("B", [_tile(f"b{k}", (k, 0, k + 1, 1)) for k in range(8)])
        m.set_run(["B"], None, 4)
        assert m.claim("w", 24)[3:] == (6, False)  # no weights: 24 // 4, as before
        m.db.execute("UPDATE tiles SET status = 'pending', worker = NULL")
        m.set_weights({("B", "b0"): 1000.0, ("B", "b1"): 60.0, ("B", "b2"): 40.0, ("B", "b3"): 1.0})
        band, name, _, threads, heavy = m.claim("w0", 24)
        assert (name, heavy, threads) == ("b0", True, 24)  # the heaviest first, alone: every core
        assert m.claim("w1", 24)[1:] == ("b1", (1, 0, 2, 1), 12, True)  # (24 - 0) // 2 heavy running
        assert m.claim("w2", 24)[1:] == ("b2", (2, 0, 3, 1), 3, False)  # 40 < 5 % of 1000: light, 3 at most
        assert m.claim("w3", 24)[1:] == ("b3", (3, 0, 4, 1), 3, False)
        assert m.threads(24, heavy=True) == 10  # (24 - 2 * 2 light) // 2 heavy
        assert m.threads(24, heavy=False) == 3
        m.db.execute("UPDATE tiles SET status = 'done' WHERE name IN ('b1', 'b2')")
        assert m.threads(24, heavy=True) == 22  # one heavy and one light left running
        m.db.execute("UPDATE tiles SET status = 'done' WHERE name != 'b0'")
        assert m.threads(24, heavy=True) == 24
    finally:
        m.close()


def test_no_neighbours_for_a_tile_inside_the_outline():
    """A tile's grid inside the country's outline holds no border: the plan's border flag is off
    (search.prepare_data asks no neighbour); a tile reaching the outline keeps it."""
    import country
    import grid as gd
    from shapely.geometry import box
    g = gd.make_grid((1000, 1000, 2000, 2000), 10, "EPSG:2180")
    assert country._at_border(g)  # no outline known: a border is possible
    g.area_shape = box(0, 0, 5000, 5000)
    assert not country._at_border(g)
    g.area_shape = box(1500, 0, 5000, 5000)
    assert country._at_border(g)
