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
               "FINDALINE_PROGRESS": "text"}
SQUARE = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                              [19.7522, 50.1580], [19.7522, 50.1546]]]}
# Testland: the clip west of the tower's meridian (tests/test_border_study.py's BORDER_LON), so its lines from the
# tower to the rocks west of it cross the border; the clip's own data east of it are the partners (partner 7), and
# a strip west of it (the clip reprojected to EPSG:8353 reaches beyond the outline's west edge)
WEST = {"type": "Polygon", "coordinates": [[[19.7505, 50.1530], [19.7561, 50.1530], [19.7561, 50.1595],
                                            [19.7505, 50.1595], [19.7505, 50.1530]]]}
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
    area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": WEST}))
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
    core=None and a TileCounter over the band's whole grid, with the partner anchors beyond the
    outline as a border tile has them: the square lies inside the clip) built into a cube."""
    import dataclasses
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
        plan = dataclasses.replace(country.band_plan(c, band, folder, data), partners=float(band.lengths[1]))
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
    at least 2 x 2 tiles, the lines across the border too; cube.json as the contract gives it."""
    import country
    import countcube
    data, state = full["data"], full["state"]
    assert state["crs"] == "EPSG:8353" and state["cube_version"] == countcube.VERSION
    # the origin in cells of the global lattice (cube v2): south-west of the outline by its longest line
    west, south = state["bounds_wgs84"][:2]
    assert all(isinstance(v, int) and v % 8 == 0 for v in state["origin"])
    assert 0 < west * 120 - state["origin"][0] < 8 + 2 and 0 < south * 120 - state["origin"][1] < 8 + 2
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
    assert info["partial"] is False and info["dsm"] is False and info["water"] is False and info["study"] is False
    assert info["config"] == state["hash"] and info["origin"] == state["origin"]
    # across the border (the file's own data beyond the outline, partner 7): owned lines (a partner east of the
    # outline) and the partner's (one west of it), no neighbour of an elevation file, the profile's sha256, the
    # notes on the borders
    border = info["totals"]["border"]
    assert border["lines"]["owned"] > 0 and border["lines"]["partner"] > 0 and border["spots"]["owned"] > 0
    assert border["lines"]["owned"] + border["lines"]["partner"] < info["totals"]["lines"]
    assert info["neighbours"] == [] and info["profile"] == country.Country.from_config(state["config"]).profile.sha256
    assert any(n.startswith("Lines across the border are counted too") for n in info["notes"])
    # the square lies in Poland, far from its borders: no hard border (Poland is its own, not a neighbour)
    assert not any(n.startswith("No data of the neighbours") for n in info["notes"])
    keys = countcube.unpack_keys(countcube.Cube(os.path.join(folder, "cube")).array("lines", 1)[:, :2])
    assert set(keys["partner"][keys["border"] > 0].tolist()) == {7} and not keys["partner"][keys["border"] == 0].any()
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
    assert meta["profile"] == info["profile"] and meta["partners"] == 150.0  # a border tile of S (30-150 m)
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
    assert country.worker_count(38_500_000, 10 * 2 ** 30) == (6, per)  # Slovakia's S tiles, 10 GiB free
    assert country.worker_count(38_500_000, 100 * 2 ** 30)[0] == 12
    assert country.worker_count(38_500_000, 2 ** 30)[0] == 1


def test_worker_env_keeps_blas_to_one_thread(monkeypatch):
    """A worker process runs numpy's BLAS on one thread (OpenBLAS commits buffers per thread at
    import: 0.76 GiB on 24 logical cores, never used by a count), whatever the caller's setting."""
    import country
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "24")
    env = country._worker_env()
    assert env["OPENBLAS_NUM_THREADS"] == "1" and env["MKL_NUM_THREADS"] == "1"
    assert env["FINDALINE_PROGRESS"] == "text" and env["PYTHONIOENCODING"] == "utf-8"


def test_worker_env_lets_openmp_threads_sleep(monkeypatch):
    """A worker's OpenMP threads wait passively after a parallel region (numba's spinning threads took
    cores from the other workers), unless the caller's environment says otherwise."""
    import country
    monkeypatch.delenv("OMP_WAIT_POLICY", raising=False)
    assert country._worker_env()["OMP_WAIT_POLICY"] == "PASSIVE"
    monkeypatch.setenv("OMP_WAIT_POLICY", "ACTIVE")
    assert country._worker_env()["OMP_WAIT_POLICY"] == "ACTIVE"


def test_worker_env_dumps_a_fatal_error(monkeypatch):
    """A worker that dies of a fatal error (a heap corruption, 0xC0000374) writes its Python stack into its
    log: faulthandler on, unless the caller's environment sets it."""
    import country
    monkeypatch.delenv("PYTHONFAULTHANDLER", raising=False)
    assert country._worker_env()["PYTHONFAULTHANDLER"] == "1"


def test_config_hash_follows_the_obstacle_rule(monkeypatch):
    """The hash of the configuration, its profile's sha256 and the outline's; with the surface model
    another obstacle rule gives another hash, so its tiles are counted again."""
    import hashlib
    import country
    import obstacles
    config = {"id": "x", "options": {"nmpt": "off"}}
    value = {"config": config, "profile": country.PROFILE.sha256, "area_sha256": "a"}
    assert country.config_hash(config, "a") == hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()
    marked = {"id": "x", "options": {"nmpt": "mark"}}
    first = country.config_hash(marked, "a")
    assert first != country.config_hash({"id": "x", "options": {"nmpt": "off"}}, "a")
    monkeypatch.setattr(obstacles, "RULE", {"radius": 3, "min_height": 1.0})
    assert country.config_hash(marked, "a") != first


def test_border_notes(tmp_path):
    """cube.json's notes on the borders: a country's name none of its neighbours (the page #layer writes a
    sentence per neighbour of "neighbours" itself) and list the borders no neighbour's source covers (the
    coverage map's outline of Slovakia: Hungary and Ukraine, never Slovakia itself) by the countries'
    English names, two joined by "and", more by commas and "and"; a source without countries (an elevation
    file) counts the country holding its outline as its own; a study area keeps its sentence."""
    import country
    with open(country.SHAPES, encoding="utf-8") as f:
        sk = next(ft for ft in json.load(f)["features"] if ft["properties"]["id"] == "sk")
    (tmp_path / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": sk["geometry"]}))
    slovakia = country.Country(id="slovakia", name="Slovakia", source="slovakia", area="osm:Slovensko")
    notes = country._border_notes(slovakia, str(tmp_path))
    assert len(notes) == 2 and notes[0].startswith("Lines across the border are counted too: one anchor in Slovakia")
    assert not any(name in notes[0] for name in ("poland", "austria", "czechia", "Neighbours"))
    assert notes[1] == ("No data of the neighbours across the border with Hungary and Ukraine (no source here): "
                        "lines cross it only where Slovakia's own data reach beyond the border."), notes
    files = country.Country(id="testland", name="Testland", source="files", area="x")
    assert country._hard_borders(files, str(tmp_path)) == ["AT", "CZ", "HU", "PL", "UA"]
    assert country._names_text(["HU"]) == "Hungary"
    assert country._names_text(["UA", "AT", "HU"]) == "Austria, Hungary and Ukraine"
    assert country._names_text(["HU", "XX"]) == "Hungary and XX"  # a code without a name as it is
    study = country.Country(id="sk-part", name="Part", source="slovakia", area="osm:Slovensko",
                            options={"within": "48.5,19,49,19.5"})
    assert country._border_notes(study, str(tmp_path)) == ["Only lines with both anchors inside Part are counted."]


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


def _box(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


def _area(tmp_path, name, geometry, within=None):
    """An area set up in the data folder tmp_path: its country.json and area.geojson."""
    folder = tmp_path / "countries" / name
    folder.mkdir(parents=True)
    options = {"within": within} if within else {}
    (folder / "country.json").write_text(json.dumps({"config": {"id": name, "options": options}}))
    (folder / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": geometry}))
    return folder


def _named(tmp_path, name, geometry, **options):
    import country
    path = tmp_path / f"{name}.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": geometry}))
    return country.Country(id=name, name=name.title(), source="files", area=str(path), bands=(), tension=(), options=options)


def _outline(folder):
    with open(folder / "area.geojson", encoding="utf-8") as f:
        return json.load(f)


def test_outline_less_the_countries_before(tmp_path):
    """A point of the map is one country's: an outline loses what the countries set up before it hold, and names them.
    A shared border cuts nothing (the file's geometry as the area spec's), a study area neither cuts nor is cut, and an
    area wholly inside a country is refused."""
    import country
    from shapely.geometry import shape
    _area(tmp_path, "first", _box(19.0, 49.0, 19.1, 49.1))
    _area(tmp_path, "part", _box(19.3, 49.0, 19.4, 49.1), within="49.0,19.3,49.1,19.4")  # a study area of "next"
    said = []

    def write(c):
        folder = tmp_path / "countries" / c.id
        folder.mkdir(exist_ok=True)
        country._write_outline(c, str(folder), str(tmp_path), said.append)
        return _outline(folder)

    over = write(_named(tmp_path, "next", _box(19.05, 49.0, 19.5, 49.1)))
    assert shape(over["geometry"]).equals(shape(_box(19.1, 49.0, 19.5, 49.1)))  # the study area left alone
    assert over["properties"]["less"] == ["first"] and len(said) == 1 and "belong to first" in said[0]
    said.clear()
    beside = _box(19.1, 49.1, 19.2, 49.2)  # touches "first" at a corner and "next" along a side
    alone = write(_named(tmp_path, "beside", beside))
    assert alone["geometry"]["coordinates"] == [[list(p) for p in beside["coordinates"][0]]] or \
        shape(alone["geometry"]).equals(shape(beside))
    assert "less" not in alone["properties"] and not said
    study = _named(tmp_path, "study", _box(19.0, 49.0, 19.1, 49.1), within="49.02,19.02,49.08,19.08")
    assert study.study and shape(write(study)["geometry"]).equals(shape(_box(19.02, 49.02, 19.08, 49.08)))
    with pytest.raises(country.CountryError, match="lies inside first"):
        write(_named(tmp_path, "inner", _box(19.01, 49.01, 19.02, 49.02)))


def test_outline_asked_whole(tmp_path, monkeypatch):
    """The layer's outline of an osm: area is never simplified (osm.search(whole=True)); a search's is, as before."""
    import country
    import osm
    asked = []

    def search(name, cache_dir, whole=False):
        asked.append((name, whole))
        return {"name": name, "geojson": _box(19.0, 49.0, 19.1, 49.1)}
    monkeypatch.setattr(osm, "search", search)
    folder = tmp_path / "countries" / "named"
    folder.mkdir(parents=True)
    c = country.Country(id="named", name="Named", source="files", area="osm:Named", bands=(), tension=())
    country._write_outline(c, str(folder), str(tmp_path))
    assert asked == [("Named", True)]
    import area as ar
    ar.from_spec("osm:Named", 0.0, None, str(tmp_path))
    assert asked[-1] == ("Named", False)


def test_overlaps_said(tmp_path):
    """`country run` says which other areas an outline overlaps: a warning for two countries (only outlines set up
    before the partition can), a plain line for a study area, nothing for a shared border or an area without
    country.json."""
    import country
    first = _area(tmp_path, "first", _box(19.0, 49.0, 19.1, 49.1))
    _area(tmp_path, "over", _box(19.05, 49.0, 19.2, 49.1))
    _area(tmp_path, "part", _box(19.02, 49.02, 19.04, 49.04), within="49.02,19.02,49.04,19.04")
    _area(tmp_path, "beside", _box(19.2, 49.0, 19.3, 49.1))
    stray = tmp_path / "countries" / "stray"
    stray.mkdir()
    (stray / "area.geojson").write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": _box(19.0, 49.0, 19.1, 49.1)}))
    said = []
    c = country.Country(id="first", name="First", source="files", area="x", bands=(), tension=())
    country._say_overlaps(c, str(first), str(tmp_path), said.append)
    assert len(said) == 2, said
    assert said[0].startswith("WARNING: first and over overlap by") and "twice" in said[0]
    assert said[1].startswith("first and part overlap by") and "study area" in said[1]


def _tile(name, core):
    import types
    return types.SimpleNamespace(name=name, core=core)


def test_heaviest_tiles_first(tmp_path):
    """A manifest of schema v1 gets the column of the weights; a run claims the tiles under the
    most lines of the tiles done already first (_weights: the cores that overlap, not those that
    only touch), the others after them in their order; _weights counts the tiles under no done
    tile (whose work is unknown)."""
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
        # nothing done yet: every tile unknown
        assert country._weights(m, ["B"]) == ({("B", "b2"): 0.0, ("B", "b1"): 0.0, ("B", "b3"): 0.0}, 3)
        m.add_tiles("A", [_tile("a2", (10, 0, 20, 10)), _tile("a3", (0, 10, 10, 20))])
        m.db.execute("UPDATE tiles SET status = 'done', lines = CASE name WHEN 'a1' THEN 5 WHEN 'a2' THEN 100 "
                     "ELSE 0 END WHERE band = 'A'")
        weights, unknown = country._weights(m, ["B"])
        assert weights == {("B", "b2"): 0.0, ("B", "b1"): 105.0, ("B", "b3"): 0.0}
        assert unknown == 2  # b2 and b3 only touch a2 and a3; b1 lies under a1 and a2 (and a3 of 0 lines)
        m.set_weights(weights)
        m.set_run(["B"], None, 2)
        assert [m.claim("w", 24)[1] for _ in range(3)] == ["b1", "b2", "b3"] and m.claim("w", 24) is None
    finally:
        m.close()


def _relief_country(tmp_path):
    """A manifest of two bands in UTM 34N over a synthetic GLO-30 tile (N48E019, a 50° slope in its
    eastern quarter, from 19.75°), the outline the tile's middle (19.2-19.9°, 48.2-48.8°), and the
    plans _set_weights reads (one band's: the outline, the CRS, the cache)."""
    import math
    import types
    from pyproj import Transformer
    from shapely.geometry import box
    import country
    from test_relief import cached_tile
    cache_dir = str(tmp_path / "cache")
    cached_tile(cache_dir, 48, 19, slope_from=0.75)
    xs, ys = Transformer.from_crs("EPSG:4326", "EPSG:32634", always_xy=True).transform(19.75, 48.5)
    x0, y0 = math.floor((xs - 1500) / 20000) * 20000, math.floor(ys / 20000) * 20000 + 10000
    # B: 20 km cores, the eastern one holding the slope (from about x0 + 8 km); C: 10 km cores, the
    # eastern two on it (c-east 2 km of it, c-far 9 km)
    m = country.Manifest(str(tmp_path))
    m.add_tiles("B", [_tile("west", (x0 - 40000, y0 - 10000, x0 - 20000, y0 + 10000)),
                      _tile("middle", (x0 - 20000, y0 - 10000, x0, y0 + 10000)),
                      _tile("east", (x0, y0 - 10000, x0 + 20000, y0 + 10000))])
    m.add_tiles("C", [_tile("c-w2", (x0 - 30000, y0, x0 - 20000, y0 + 10000)),
                      _tile("c-west", (x0 - 10000, y0, x0, y0 + 10000)),
                      _tile("c-east", (x0, y0, x0 + 10000, y0 + 10000)),
                      _tile("c-far", (x0 + 10000, y0, x0 + 20000, y0 + 10000))])
    plan = types.SimpleNamespace(area=types.SimpleNamespace(geometry=box(19.2, 48.2, 19.9, 48.8)), crs="EPSG:32634",
                                 paths=types.SimpleNamespace(cache=cache_dir))
    return m, {"B": plan, "C": plan}


def test_relief_weights_of_a_first_run(tmp_path):
    """With no tile done, every pending tile of the run's bands is weighed by the km² of slopes of
    45° or more at 30 m in its core (RELIEF_LINES times its power RELIEF_EXPONENT): the core holding
    the slope first, the flat ones 0 (in their order after it); the heavy tiles follow (HEAVY_SHARE
    of the largest weight)."""
    import country
    m, plans = _relief_country(tmp_path)
    said = []
    try:
        weights, tiles = country._relief_weights(m, ["B", "C"], plans["B"].area.geometry, "EPSG:32634",
                                                 plans["B"].paths.cache)
        assert tiles == 1  # N48E019
        assert weights[("B", "west")] == weights[("B", "middle")] == weights[("C", "c-west")] == 0
        assert weights[("B", "east")] > weights[("C", "c-far")] > weights[("C", "c-east")] > 0
        # the slope from 19.75° to the outline's 19.9°: about 11 km wide, 20 km of it in B's core
        km2 = (weights[("B", "east")] / country.RELIEF_LINES) ** (1 / country.RELIEF_EXPONENT)
        assert 150 < km2 < 300
        country._set_weights(m, ["B", "C"], plans, said.append)
        assert "by the relief" in said[-1] and "no tile is done yet" in said[-1]
        m.set_run(["B", "C"], None, 7)
        claims = [m.claim("w", 24) for _ in range(7)]
        assert [c[1] for c in claims] == ["east", "c-far", "c-east", "west", "middle", "c-w2", "c-west"]
        # c-far's km² about 0.4 of east's: 0.22 of its weight; c-east's about 0.1: 0.02, light
        assert [c[4] for c in claims] == [True, True, False, False, False, False, False]
    finally:
        m.close()


def test_relief_weights_only_for_unknown_tiles(tmp_path, monkeypatch):
    """The relief stands in when a pending tile lies under no done tile (then for every pending
    tile: one scale); when every pending tile lies under done tiles, their lines (a real 0 too), and
    the relief is not read. A failure of the relief leaves the tiles in their order."""
    import country
    import relief
    m, plans = _relief_country(tmp_path)
    said = []
    try:
        m.db.execute("UPDATE tiles SET status = 'done', lines = 7 WHERE name = 'c-east'")
        country._set_weights(m, ["B"], plans, said.append)  # B's west and middle under no done tile
        assert "by the relief" in said[-1] and "2 lie under no done tile" in said[-1]
        relief_east = m.db.execute("SELECT weight FROM tiles WHERE name = 'east'").fetchone()[0]
        assert relief_east > 1e6
        m.db.execute("UPDATE tiles SET status = 'done', lines = 0 WHERE name IN ('c-w2', 'c-west', 'c-far')")

        def no_relief(*args, **kwargs):
            raise AssertionError("the relief was read")

        monkeypatch.setattr(relief, "steep_blocks", no_relief)
        country._set_weights(m, ["B"], plans, said.append)  # every B tile under a done C tile
        assert said[-1].startswith("The heaviest tiles first: 1 of 3")
        assert dict(m.db.execute("SELECT name, weight FROM tiles WHERE band = 'B'").fetchall()) == {
            "west": 0.0, "middle": 0.0, "east": 7.0}  # west and middle under C tiles of 0 lines: a real 0
        m.db.execute("UPDATE tiles SET status = 'pending', weight = NULL")

        def failing(*args, **kwargs):
            raise RuntimeError("no network")

        monkeypatch.setattr(relief, "steep_blocks", failing)
        country._set_weights(m, ["B", "C"], plans, said.append)
        assert said[-1].startswith("WARNING: the tiles' weights from the relief failed (no network)")
        assert {w for (w,) in m.db.execute("SELECT weight FROM tiles")} == {None}
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
        assert m.threads(24, heavy=True) == 11  # (24 - 1 * 2 light) // 2 heavy
        assert m.threads(24, heavy=False) == 3
        m.db.execute("UPDATE tiles SET status = 'done' WHERE name IN ('b1', 'b2')")
        assert m.threads(24, heavy=True) == 23  # one heavy and one light left running
        m.db.execute("UPDATE tiles SET status = 'done' WHERE name != 'b0'")
        assert m.threads(24, heavy=True) == 24
    finally:
        m.close()


def test_light_tiles_leave_the_heavy_ones_their_cores(tmp_path):
    """A light tile counts as one logical core (LIGHT_CORES; its worker used 1.2-1.4 on average):
    Slovakia's M2 band at 12 workers on 12 physical / 24 logical cores, its three heavy tiles beside
    nine light ones, gives them 5 threads each (2 when a light tile counted two), 7 each for two
    beside ten, while a light tile keeps 2 (24 // 12 workers); at 8 workers 6 and 9; on 6 workers
    of 12 logical cores (the 5650G) one heavy tile beside five light ones takes 7."""
    import country
    m = country.Manifest(str(tmp_path))
    try:
        m.add_tiles("B", [_tile(f"b{k:03d}", (k, 0, k + 1, 1)) for k in range(100)])
        m.set_weights({("B", "b000"): 600.0, ("B", "b001"): 440.0, ("B", "b002"): 290.0})

        def running(heavy: int, light: int, processes: int):
            m.db.execute("UPDATE tiles SET status = 'pending', worker = NULL")
            m.db.execute("UPDATE tiles SET status = 'running' WHERE name IN "
                         f"(SELECT name FROM tiles ORDER BY name LIMIT {heavy})")
            m.db.execute(f"UPDATE tiles SET status = 'running' WHERE name IN "
                         f"(SELECT name FROM tiles ORDER BY name LIMIT {light} OFFSET 3)")
            m.set_run(["B"], None, processes)

        running(3, 9, 12)
        assert (m.threads(24, heavy=True), m.threads(24)) == (5, 2)  # (24 - 9) // 3
        running(2, 10, 12)
        assert (m.threads(24, heavy=True), m.threads(24)) == (7, 2)  # (24 - 10) // 2
        running(3, 5, 8)
        assert (m.threads(24, heavy=True), m.threads(24)) == (6, 3)
        running(2, 6, 8)
        assert m.threads(24, heavy=True) == 9
        running(1, 5, 6)
        assert (m.threads(12, heavy=True), m.threads(12)) == (7, 2)
        running(1, 11, 12)  # the light part's last tiles beside the heaviest one
        assert m.threads(24, heavy=True) == 13
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


def test_tiles_with_their_grids_held(env, full, tmp_path, monkeypatch):
    """Tiles whose grids stay open until they are deleted (sources.mosaic.HELD_GRIDS, as `country worker`
    sets it): no grid flushed, none left held and no work folder after a tile, and the counts of the run
    that flushed them, step 1's values read back through other mappings of the same files; flush_grid
    does flush by default (the app)."""
    import countcube
    import sources.mosaic
    flushed = []
    real = np.memmap.flush
    monkeypatch.setattr(np.memmap, "flush", lambda self: (flushed.append(self.filename), real(self))[1])
    grid = np.lib.format.open_memmap(str(tmp_path / "a.npy"), mode="w+", dtype=np.uint8, shape=(2, 2))
    sources.mosaic.flush_grid(grid)
    assert flushed
    flushed.clear()
    held = []
    monkeypatch.setattr(sources.mosaic, "HELD_GRIDS", held)
    sources.mosaic.flush_grid(grid)
    assert not flushed and held == [grid]
    held.clear()
    del grid
    seen = []
    import country
    clear = country.TileWork._remove_grids

    def remove_grids(work, path):
        seen.append(len(held))
        clear(work, path)
        assert not held and not os.path.exists(path)

    monkeypatch.setattr(country.TileWork, "_remove_grids", remove_grids)
    data = _data_dir(env, "unflushed")
    assert _country("run", ID, "--data-dir", data, "--processes", "0", "--bands", "S", "--yes") == 0
    assert not flushed and any(seen)
    tiles = os.path.join(data, "countries", ID, "tiles", "S")
    names = os.listdir(tiles)
    assert len(names) >= 4 and sorted(names) == sorted(os.listdir(os.path.join(full["data"], "countries", ID, "tiles", "S")))
    for name in names:
        counted, _ = countcube.load_tile(os.path.join(tiles, name))
        saved, _ = countcube.load_tile(os.path.join(full["data"], "countries", ID, "tiles", "S", name))
        assert counted.lines == saved.lines
        for a, b in ((saved.line_keys, counted.line_keys), (saved.line_counts, counted.line_counts),
                     (saved.spot_ids, counted.spot_ids), (saved.spot_records, counted.spot_records)):
            assert np.array_equal(a, b), name


def test_surface_model_with_its_grids_held(env, tmp_path, monkeypatch):
    """Tiles with a surface model, which Slovakia's bands have not: its mosaic and the obstacle surface
    of search.prepare_data held as `country worker` holds them, the counts of the run that flushes
    them."""
    import countcube
    import rasterio as rio
    import country
    import sources.mosaic
    with rio.open(env["config"]["options"]["elevation_file"]) as src:
        profile, z = src.profile, src.read(1)
    height, width = z.shape
    z[height // 3:height // 2, width // 3:width // 2] += 15.0  # a wood
    surface = str(tmp_path / "surface.tif")
    with rio.open(surface, "w", **profile) as dst:
        dst.write(z, 1)
    config = {**env["config"], "options": {**env["config"]["options"], "nmpt": "mark", "surface_file": surface}}
    held_names = set()
    clear = country.TileWork._remove_grids

    def remove_grids(work, path):
        held_names.update(os.path.basename(view.filename) for view in sources.mosaic.HELD_GRIDS or [])
        clear(work, path)

    monkeypatch.setattr(country.TileWork, "_remove_grids", remove_grids)

    def tiles(name, held):
        monkeypatch.setattr(sources.mosaic, "HELD_GRIDS", held)
        folder = tmp_path / name / "countries" / ID
        folder.mkdir(parents=True)
        (folder / "country.json").write_text(json.dumps({"config": config}))
        assert _country("run", ID, "--data-dir", str(tmp_path / name), "--processes", "0", "--bands", "S", "--yes") == 0
        return {n: countcube.load_tile(str(folder / "tiles" / "S" / n))[0] for n in os.listdir(folder / "tiles" / "S")}

    flushed, held = tiles("flushed", None), tiles("held", [])
    assert {"nmt.npy", "nmpt.npy", "obstacles.npy"} <= held_names
    assert sorted(flushed) == sorted(held) and sum(t.lines for t in held.values()) > 0
    for name, counted in held.items():
        saved = flushed[name]
        assert counted.lines == saved.lines
        for a, b in ((saved.line_keys, counted.line_keys), (saved.line_counts, counted.line_counts),
                     (saved.spot_ids, counted.spot_ids), (saved.spot_records, counted.spot_records)):
            assert np.array_equal(a, b), name


def test_tile_inside_the_outline_has_a_full_mask(tmp_path):
    """A tile whose grid lies inside the country's outline (country._at_border False, Plan.border)
    gets the mask the burn gives, without burning it: every pixel set."""
    import area as ar
    import country
    import search
    from grid import Grid
    from shapely.geometry import box
    crs = "EPSG:32634"
    grid = Grid(crs=crs, left=500_000.0, top=5_000_200.0, width=300, height=200, res=1.0)
    inside = box(20.9, 45.1, 21.1, 45.25)
    outline = ar.project(inside, "EPSG:4326", crs)
    assert outline.contains(box(*grid.bounds))
    grid.area_shape = outline
    assert not country._at_border(grid)
    burned = search._area_mask_rows(ar.Polygon(inside), grid, str(tmp_path / "burned.npy"), 64)
    full = search._area_mask_rows(ar.Polygon(inside), grid, str(tmp_path / "full.npy"), 64, full=True)
    assert full.dtype == burned.dtype and full.shape == burned.shape and type(full) is type(burned)
    assert full.all() and np.array_equal(full, burned)


def test_worker_keeps_the_grids_from_the_disk(monkeypatch, tmp_path):
    """`country worker`: the grids held, and what the first tile left alive frozen, once, after its
    cleanup (TileWork.loop(freeze=True)); not without freeze."""
    import country
    import sources.mosaic
    monkeypatch.setattr(sources.mosaic, "HELD_GRIDS", None)
    events = []

    class Work(country.TileWork):
        def __init__(self):
            self.cores, self.worker = 1, "slot-0"

        def count(self, band, name, core, threads, threads_now=None):
            return {"seconds": {"prepare": 0.0, "count": 0.0}, "lines": 0, "spots": 0}

        def cleanup(self, band, name):
            events.append(name)

    class Claims:
        def __init__(self, names):
            self.names = iter(names)

        def claim(self, worker, cores):
            name = next(self.names, None)
            return None if name is None else ("S", name, (0, 0, 1, 1), 1, False)

        def done(self, *args):
            pass

    monkeypatch.setattr(country.gc, "freeze", lambda: events.append("freeze"))
    assert Work().loop(Claims(["a", "b", "c"]), freeze=True) == 3
    assert events == ["a", "freeze", "b", "c"]
    events.clear()
    assert Work().loop(Claims(["a", "b"])) == 2
    assert events == ["a", "b"]
    seen = {}

    class Stop:
        def __init__(self, *args):
            pass

        def loop(self, manifest, run_gone=None, freeze=False):
            seen.update(held=sources.mosaic.HELD_GRIDS, freeze=freeze)
            return 0

    class NoManifest:
        def __init__(self, folder):
            pass

        def close(self):
            pass

    monkeypatch.setattr(country, "TileWork", Stop)
    monkeypatch.setattr(country, "Manifest", NoManifest)
    assert country.worker(ID, str(tmp_path), 0) == 0
    assert seen == {"held": [], "freeze": True}


def test_tile_in_strips_as_plain(env, full):
    """A tile counted with step 1 in strips (country.TileWork.count: prepare_data(strips=True) on
    the tile's own grid) gives the counts of the plain path and the same grids, both read back
    memory-mapped and read-only (the kernels' argument types of warmup.SEARCHES); the run's tile
    file holds those counts."""
    import country
    import countcube
    import dataclasses
    import search
    data, state = full["data"], full["state"]
    folder = os.path.join(data, "countries", ID)
    c = country.Country.from_config(state["config"])
    band = c.band("S")
    plan = country.band_plan(c, band, folder, data)
    db = sqlite3.connect(os.path.join(folder, "manifest.sqlite"))
    try:
        name, core = db.execute("SELECT name, core FROM tiles WHERE band = 'S' AND lines > 0 ORDER BY lines DESC").fetchone()
    finally:
        db.close()
    core = tuple(json.loads(core))
    results, grids = {}, {}
    for mode in ("plain", "strips"):
        work = os.path.join(data, "work", f"strips-test-{mode}")
        os.makedirs(work, exist_ok=True)
        tile_plan = country.tile_plan(c, plan, core, search.Paths(data, work))
        grid = tile_plan.grid
        assert tile_plan.border and tile_plan.partners == 150.0
        tile = search.prepare_data(tile_plan, statistics=False, strips=mode == "strips")
        for field in ("elevation", "surface", "water", "filled", "slope", "joined", "covered", "partner"):
            array = getattr(tile, field)
            if array is not None:
                assert isinstance(array, np.memmap) and not array.flags.writeable, (mode, field)
        grids[mode] = {f: None if getattr(tile, f) is None else np.array(getattr(tile, f))
                       for f in ("elevation", "surface", "water", "filled", "slope", "joined", "covered", "mask",
                                 "partner")}
        counter = countcube.TileCounter(grid, tuple(state["origin"]), core, band.lengths, False)
        search.count_tile(tile_plan, tile, core, counter, country.tension_table(c, band, plan))
        results[mode] = counter.result()
        del tile
    for f, plain in grids["plain"].items():
        strips = grids["strips"][f]
        assert (plain is None) == (strips is None), f
        if plain is not None:
            assert np.array_equal(plain, strips, equal_nan=plain.dtype.kind == "f"), f
    plain, strips = results["plain"], results["strips"]
    assert plain.lines > 0
    for f in dataclasses.fields(plain):
        a, b = getattr(plain, f.name), getattr(strips, f.name)
        assert np.array_equal(a, b) if isinstance(a, np.ndarray) else a == b, f.name
    saved, meta = countcube.load_tile(os.path.join(folder, "tiles", "S", name + ".npz"))
    assert saved.lines == plain.lines and np.array_equal(saved.line_keys, plain.line_keys)
    assert np.array_equal(saved.line_counts, plain.line_counts) and np.array_equal(saved.spot_ids, plain.spot_ids)
    assert np.array_equal(saved.spot_records, plain.spot_records)


def test_neighbour_cubes():
    """NEIGHBOUR_CUBES names a cube for every source the catalogue declares as a neighbour (no source
    declares more than six: the partner indices 1-6), a country of COUNTRIES its own id; a source's
    cube.json neighbours in the order of Source.neighbours; none for an elevation file."""
    import country
    import sources as src
    named = {n for s in src.SOURCES.values() for n in (s.neighbours or ())}
    assert named == set(country.NEIGHBOUR_CUBES)
    assert max(len(s.neighbours or ()) for s in src.SOURCES.values()) <= 6
    assert all(country.ID_PATTERN.match(cube) for cube in country.NEIGHBOUR_CUBES.values())
    for c in country.COUNTRIES.values():
        assert country.NEIGHBOUR_CUBES.get(c.source, c.id) == c.id
    assert country.neighbour_cubes("slovakia") == ["poland", "austria", "czechia"]
    assert country.neighbour_cubes("files") == []


def test_profile_of_a_country_and_of_a_study_area():
    """A country without bands of its own has the profile's (PROFILE: its bands, T(L) and rig); a study
    area (or a test) may override them, which gives another profile sha256 and config hash; config()
    and from_config keep either; the profile's sha256 is that of its JSON."""
    import hashlib
    import country
    plain = country.Country(id="land", name="Land", source="slovakia", area="osm:Land")
    assert plain.bands == country.PROFILE.bands and plain.tension == country.PROFILE.tension
    assert plain.rig == country.PROFILE.rig and plain.profile.sha256 == country.PROFILE.sha256
    assert country.COUNTRIES["slovakia"].profile.sha256 == country.PROFILE.sha256
    config = {"id": "land", "name": "Land", "source": "slovakia", "area": "osm:Land", "options": {}}
    assert country.Country.from_config(config) == plain and country.Country.from_config(plain.config()) == plain
    text = json.dumps(country.PROFILE.config(), sort_keys=True).encode("utf-8")
    assert country.PROFILE.sha256 == hashlib.sha256(text).hexdigest()
    bands = [{"name": "S", "lengths": [30, 150], "resolution": 1.0, "model": "formula", "slope_threshold": 45,
              "core_m": 200, "layer": True}]
    study = country.Country.from_config({**config, "id": "box", "bands": bands, "tension": [[30, 2.5]],
                                         "options": {"within": "49.0,19.0,49.1,19.1"}})
    assert study.study and [b.name for b in study.bands] == ["S"] and study.tension == ((30, 2.5),)
    assert study.rig == country.PROFILE.rig  # the profile's where it has none
    assert study.profile.sha256 != country.PROFILE.sha256
    assert country.Country.from_config(study.config()) == study
    assert country.config_hash(study.config(), "a") != country.config_hash({**study.config(), "bands": []}, "a")


def test_build_refuses_a_tile_of_another_profile(env, full, tmp_path, capsys):
    """build refuses a tile counted with another profile of the layer (its meta's "profile"), as it
    refuses another configuration or origin."""
    import shutil
    import countcube
    data = str(tmp_path / "data")
    shutil.copytree(os.path.join(full["data"], "countries"), os.path.join(data, "countries"))
    folder = os.path.join(data, "countries", ID, "tiles", "S")
    name = sorted(os.listdir(folder))[0]
    counts, meta = countcube.load_tile(os.path.join(folder, name))
    countcube.save_tile(os.path.join(folder, name), counts, {**meta, "profile": "another"})
    capsys.readouterr()
    assert _country("build", ID, "--data-dir", data) == 1
    assert "another profile" in capsys.readouterr().out
