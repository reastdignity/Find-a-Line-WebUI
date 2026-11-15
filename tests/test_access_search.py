"""The access mark through the search (--access; docs/line-volume/spec-search.md 3, step 1d-2): access.py's grid
computed once per search on step 1's grid, each line's two anchors' answers (access1, access2: 0 hard access, 1
cannot tell, 2 easy access), the four text files, the store and the favourites with them, a search without the
option as before, tiles that give one grid's answers, the store's coded note, the warm-up of the access kernels,
the web process that never imports access.py, and today's page reading a run made with the option as one made
without it."""

import dataclasses
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import access  # noqa: E402
import helpers as sh  # noqa: E402
import linestore  # noqa: E402
import messages  # noqa: E402
import runs as rn  # noqa: E402
import search  # noqa: E402
from params import SearchParams  # noqa: E402
from test_offline import DATA, OFFLINE_ENV, _square, _water_and_fallback, write_raster  # noqa: E402

VIEWER = os.path.join(REPO, "viewer")
LEFT, TOP, SIZE = 500000.0, 300000.0, 300  # the made-up scene: EPSG:2180, 1 m pixels
TOWER = (slice(140, 148), slice(146, 154))  # rows, columns of the tower's top
WEST_RIM, EAST_RIM = 129, 170  # the columns of the canyon's rims


def scene(whole: bool = False, no_data: bool = False) -> np.ndarray:
    """A canyon 40 m wide and 50 m deep with a tower of 8 x 8 m in it, standing as high as its rims. West of it a
    meadow of 3.9 ha (open ground: its rim reads easy access), east of it a shelf of 0.9 ha (not open ground) whose
    only way down is a slope of 45 degrees to a meadow (cannot tell: only the loose walk reaches it); the tower's
    top no walk reaches (hard access). The heights tilt 6 m from north to south, so no flat region reads as a lake
    held as data. whole: the heights in whole metres (their smoothed copy decides too); no_data: the west meadow
    beyond 20 m of its rim without data (an end of the data: its rim reads cannot tell)."""
    z = np.full((SIZE, SIZE), 150.0)
    z[:, 130:170] = 100.0  # the canyon floor (its rims: columns 129 and 170)
    z[TOWER] = 150.0
    z[:, 200:250] = 150.0 - (np.arange(200, 250) - 199)  # 45 degrees down to the east meadow
    z[:, 250:] = 100.0
    z += 0.02 * np.arange(SIZE)[:, None] + (0.0 if whole else 0.25)
    if whole:
        z = np.round(z)
    if no_data:
        z[:, :110] = np.nan
    return z.astype(np.float32)


def _plan(tmp_path, z: np.ndarray, name: str, events=None, **values) -> search.Plan:
    """The plan of a circle over the scene (its grid a window of the scene's pixels), offline."""
    write_raster(tmp_path / f"{name}.tif", z, LEFT, TOP)
    params = SearchParams(**{**dict(
        elevation_file=str(tmp_path / f"{name}.tif"), northing=TOP - SIZE / 2, easting=LEFT + SIZE / 2, radius=135,
        resolution=1, nmpt="off", water="off", fill_gaps="off", min_length=10, max_length=80, slope_threshold=60,
        prominence_span=10, drop_radius=10, ortho="never", name=name, access=True), **values})
    paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
    os.makedirs(paths.work, exist_ok=True)
    emit = (lambda kind, text: events.append((kind, text))) if events is not None else (lambda kind, text: None)
    plan = dataclasses.replace(search.plan_search(params, paths, emit), index_runs=False)
    grid = plan.grid
    r0, c0 = TOP - grid.top, grid.left - LEFT
    assert r0 == int(r0) >= 0 and c0 == int(c0) >= 0 and r0 + grid.height <= SIZE and c0 + grid.width <= SIZE
    return plan


def _grid_answers(plan: search.Plan, z: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """access.access_grid (the alpine variant on) of the search's grid, a window of the scene z, at scene pixels."""
    grid = plan.grid
    r0, c0 = int(TOP - grid.top), int(grid.left - LEFT)
    answers = access.access_grid(z[r0:r0 + grid.height, c0:c0 + grid.width], None, 1.0, alpine=True)
    return answers[rows - r0, cols - c0]


def _pixels(xy: np.ndarray) -> tuple:
    """Rows and columns of the scene of [easting, northing] pixel centres."""
    return (np.round(TOP - xy[:, 1] - 0.5).astype(int), np.round(xy[:, 0] - LEFT - 0.5).astype(int))


def _ends(lines: sh.LineTable) -> tuple:
    """(rows, columns, answers) of every line end."""
    c = lines.columns
    r1, c1 = _pixels(c["a1_xy"])
    r2, c2 = _pixels(c["a2_xy"])
    return np.concatenate([r1, r2]), np.concatenate([c1, c2]), np.concatenate([c["access1"], c["access2"]])


def _search(tmp_path, z, name, events=None, **values):
    plan = _plan(tmp_path, z, name, events, **values)
    lines, run = search.search_lines(plan)
    return plan, lines, run


@pytest.fixture(scope="module")
def offline():
    with pytest.MonkeyPatch.context() as patch:
        for key, value in OFFLINE_ENV.items():
            patch.setenv(key, value)
        yield


def test_marks_through_the_search(tmp_path, offline):
    """Each line end's answer is the access grid's at its pixel (access.access_grid of the search's terrain, the
    alpine variant on), uint8: the west rim by the meadow easy access (2), the east rim above the slope of 45
    degrees cannot tell (1), the tower's top hard access (0); the search prints no note of filled anchors."""
    z = scene()
    events = []
    plan, lines, _ = _search(tmp_path, z, "float", events)
    rows, cols, answers = _ends(lines.results)
    assert lines.results.columns["access1"].dtype == lines.results.columns["access2"].dtype == np.uint8
    assert len(rows) > 50 and np.array_equal(answers, _grid_answers(plan, z, rows, cols))
    tower = (rows >= 140) & (rows < 148) & (cols >= 146) & (cols < 154)
    assert tower.any() and set(answers[tower].tolist()) == {access.CANNOT}
    assert (cols == WEST_RIM).any() and set(answers[cols == WEST_RIM].tolist()) == {access.CAN}
    assert (cols == EAST_RIM).any() and set(answers[cols == EAST_RIM].tolist()) == {access.UNSURE}
    assert not [text for _, text in events if "on filled data" in str(text)]


def test_whole_metres_and_the_end_of_the_data(tmp_path, offline):
    """On whole-metre heights the smoothed copy decides too (access.access_grid's whole_metres: the rim by the
    meadow cannot tell where the float heights say easy access), and beside the end of the data a rim no walk
    reaches cannot tell (never hard access): through the search as the grid says."""
    whole = scene(whole=True)
    assert access.whole_metres(whole.ravel()) and not access.whole_metres(scene().ravel())
    plan, lines, _ = _search(tmp_path, whole, "whole")
    rows, cols, answers = _ends(lines.results)
    assert np.array_equal(answers, _grid_answers(plan, whole, rows, cols))
    assert (cols == WEST_RIM).any() and access.UNSURE in answers[cols == WEST_RIM].tolist()
    ended = scene(no_data=True)
    plan, lines, _ = _search(tmp_path, ended, "ended")
    rows, cols, answers = _ends(lines.results)
    assert np.array_equal(answers, _grid_answers(plan, ended, rows, cols))
    assert (cols == WEST_RIM).any() and set(answers[cols == WEST_RIM].tolist()) == {access.UNSURE}


def test_anchors_on_filled_data_cannot_tell():
    """search._access_columns: an anchor the measure takes for no data (Data.filled_pixels and not water)
    reads cannot tell whatever the grid holds there, with a note of how many; one on filled water or on the
    source's data keeps the grid's answer."""
    grid = np.zeros((4, 4), np.uint8)  # every pixel hard access
    grid[0, 0] = access.CAN
    filled = np.zeros((4, 4), bool)
    filled[1, 1] = filled[2, 2] = filled[0, 0] = True
    water = np.zeros((4, 4), bool)
    water[2, 2] = True
    data = search.Data(np.full((4, 4), 5.0, np.float32), None, water, filled, None, access=grid)
    lines = sh.LineTable({"a1": np.array([[1, 1], [2, 2], [3, 3], [0, 0]]),
                          "a2": np.array([[3, 3], [1, 1], [0, 0], [1, 1]])})
    events = []
    plan = type("Plan", (), {"emit": staticmethod(lambda kind, text: events.append((kind, text)))})
    search._access_columns(plan, lines, data)
    assert lines.columns["access1"].tolist() == [1, 0, 0, 1] and lines.columns["access2"].tolist() == [0, 1, 1, 1]
    assert lines.columns["access1"].dtype == np.uint8
    assert events == [("info", 'Access: 5 line ends on filled data or shore faces (no data for the walk) read '
                                       '"cannot tell"')]


@pytest.fixture(scope="module")
def scene_runs(tmp_path_factory, offline):
    """The float scene searched without and with --access, each saved by search.save_run: {name: run folder}."""
    folder = tmp_path_factory.mktemp("scene-runs")
    runs = {}
    for name, on in (("off", False), ("on", True)):
        plan = _plan(folder, scene(), name, access=on)
        lines, _ = search.search_lines(plan)
        path = folder / name / "runs" / name
        path.mkdir(parents=True)
        search.save_run(plan, lines, {"id": name, "path": str(path), "created": datetime(2026, 11, 15, 12),
                                      "name": name})
        runs[name] = path
    return runs


def _script(path) -> dict:
    text = open(path, encoding="utf-8").read()
    return json.loads(text[text.index(" = {") + 3:].rstrip().rstrip(";"))


def test_files_with_the_option_and_without(scene_runs):
    """Off: no column, no "ends", run.json's params and the search's key without "access". On: lines.csv and
    lines.geojson hold access1, access2 after the anchors' columns (the rest byte for byte the run without the
    option), data.js and lines.js two values before the profile named by "ends", run.json's params "access": true,
    the store two uint8 columns read back as the search's and exported as lines.csv byte for byte."""
    off, on = scene_runs["off"], scene_runs["on"]
    meta = {name: json.loads((folder / "run.json").read_text(encoding="utf-8")) for name, folder in scene_runs.items()}
    assert "access" not in meta["off"]["params"] and meta["on"]["params"]["access"] is True
    assert meta["on"]["summary"]["lines"] == meta["off"]["summary"]["lines"] > 50
    # lines.csv: the on run's less its two columns is the off run's, byte for byte
    table = (on / "lines.csv").read_bytes().decode("utf-8-sig").split("\r\n")
    header = table[0].split(",")
    assert header[-2:] == rn.ACCESS and header[:-2] == rn.FIELDS
    cut = "\r\n".join(",".join(row.split(",")[:-2]) for row in table[:-1]) + "\r\n"
    assert cut.encode("utf-8-sig") == (off / "lines.csv").read_bytes()
    assert {row.split(",")[-1] for row in table[1:-1]} <= {"0", "1", "2"}
    # lines.geojson: the same features with two properties more, the same "findaline" but its params
    geo = {name: json.loads((folder / "lines.geojson").read_text(encoding="utf-8"))
           for name, folder in scene_runs.items()}
    for feature in geo["on"]["features"]:
        assert list(feature["properties"])[-2:] == rn.ACCESS
        for name in rn.ACCESS:
            assert feature["properties"].pop(name) in (0, 1, 2)
    assert geo["on"]["features"] == geo["off"]["features"]
    # data.js and lines.js: two values before the profile, "ends" names them; nothing else differs
    for file, profiles in (("data.js", True), ("lines.js", False)):
        heads = {name: _script(folder / file) for name, folder in scene_runs.items()}
        assert "ends" not in heads["off"] and heads["on"]["ends"] == rn.ACCESS
        rows = heads["on"].pop("lines")
        cut = [row[:-3] + row[-1:] if profiles else row[:-2] for row in rows]
        assert cut == heads["off"].pop("lines")
        assert {v for row in rows for v in (row[-3:-1] if profiles else row[-2:])} <= {0, 1, 2}
        heads["on"].pop("ends")
        for head in heads.values():
            head.pop("run", None)
        assert heads["on"] == heads["off"], file
    # the store: two uint8 columns, read back as the search wrote them, exported as the run's lines.csv
    import pyarrow as pa
    with pa.OSFile(str(on / linestore.LINES_FILE), "rb") as source:
        schema = pa.ipc.open_file(source).schema
    assert [schema.field(name).type for name in rn.ACCESS] == [pa.uint8(), pa.uint8()]
    with pa.OSFile(str(off / linestore.LINES_FILE), "rb") as source:
        assert not set(rn.ACCESS) & set(pa.ipc.open_file(source).schema.names)
    lines, _ = linestore.read(str(on), profiles=False)
    assert lines.columns["access1"].dtype == np.uint8
    linestore.export(str(on), "csv", str(on / "export.csv"))
    assert (on / "export.csv").read_bytes() == (on / "lines.csv").read_bytes()
    linestore.export(str(on), "geojson", str(on / "export.geojson"))
    assert (on / "export.geojson").read_bytes() == (on / "lines.geojson").read_bytes()


def test_search_key_without_the_option(tmp_path, offline):
    """The search's key (the hash a tiled search resumes by, and the 2 % sample's seed) has no "access" when the
    option is off, so unfinished searches of before resume; with it on the key holds it and the hash differs."""
    z = scene()
    on = _plan(tmp_path, z, "key-on")
    off = _plan(tmp_path, z, "key-off", access=False, elevation_file=str(tmp_path / "key-on.tif"))  # one file
    assert "access" not in search._search_key(off)["params"] and search._search_key(on)["params"]["access"] is True
    assert search._search_hash(off) != search._search_hash(on)
    key = search._search_key(on)
    key["params"].pop("access")
    assert search._hash_of(key) == search._search_hash(off)


def test_tiles_give_one_grids_answers(tmp_path, monkeypatch):
    """With --access an area computed in tiles gives exactly the lines of one grid, their access too, with the sea
    and a lake filled and gaps on land filled from a fallback (the clip of
    test_offline.py::test_area_in_tiles_with_water_and_gaps): the access grid is computed once on the whole grid
    (access.npy in the work folder, removed after the last tile) and each tile reads its window."""
    import rasterio as rio
    import sources as src
    from scipy import ndimage
    with rio.open(os.path.join(DATA, "zabi_kon_nmt.tif")) as s:
        terrain, left, top = s.read(1), s.bounds.left, s.bounds.top
    with rio.open(os.path.join(DATA, "zabi_kon_nmpt.tif")) as s:
        surface = s.read(1)
    fallback = (ndimage.uniform_filter(terrain, 5) + 1.5).astype(np.float32)
    size = terrain.shape[0]
    terrain[:, :80] = surface[:, :80] = np.nan  # the sea in the west, without data
    terrain[200:260, 300:360] = surface[200:260, 300:360] = np.nan  # a lake
    terrain[400:430, 150:190] = surface[400:430, 150:190] = np.nan  # gaps on land
    terrain[290:310, 240:260] = surface[290:310, 240:260] = np.nan
    write_raster(tmp_path / "nmt.tif", terrain, left, top)
    write_raster(tmp_path / "nmpt.tif", surface, left, top)
    water = np.zeros((size, size), np.uint8)
    water[:, :85] = src.OCEAN
    water[195:265, 295:365] = src.LAKE
    _water_and_fallback(tmp_path, monkeypatch, water, fallback, left, top)
    area = _square(tmp_path / "square.geojson", left + 40, top - size + 60, left + size - 60, top - 40)
    computed = []
    grid_of = search._access_grid
    monkeypatch.setattr(search, "_access_grid", lambda *a, **k: computed.append(a[2] if len(a) > 2 else None)
                        or grid_of(*a, **k))
    runs = {}
    for name, tile_size in (("one", None), ("tiled", 150)):
        params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                              area=area, max_length=150, water="fill", fill_gaps="on", coastline="copernicus",
                              ortho="never", tile_size=tile_size, access=True, name=name)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = dataclasses.replace(search.plan_search(params, paths, lambda kind, text: None), index_runs=False)
        assert bool(plan.tiles) == (tile_size is not None)
        lines, run = search.search_lines(plan)
        c = lines.results.columns
        assert (c["water_m"] > 0).any() and (c["filled_m"] > 0).any()
        assert len(set(c["access1"].tolist()) | set(c["access2"].tolist())) >= 2
        result = search.save_run(plan, lines, run)
        runs[name] = result.run["path"]
        if plan.tiles:
            assert not glob.glob(os.path.join(paths.work, "*.npy"))  # access.npy too, after the tiles
    assert computed == [None, os.path.join(str(tmp_path / "tiled" / "work"), search.ACCESS_FILE)]  # once each
    read = lambda name, file: open(os.path.join(runs[name], file), "rb").read()  # noqa: E731
    assert read("one", "lines.csv") == read("tiled", "lines.csv") and b",access1,access2" in read("one", "lines.csv")
    for file in ("data.js", "lines.js"):
        rows = {name: _script(os.path.join(runs[name], file))["lines"] for name in ("one", "tiled")}
        assert sorted(map(json.dumps, rows["one"])) == sorted(map(json.dumps, rows["tiled"])), file
    assert len(glob.glob(os.path.join(runs["tiled"], "tiles", "*.table.pkl.gz"))) > 1
    # with the square rule too: the access columns pass the reducer and the join of the tiles' kept lines
    kept = {}
    for name, tile_size in (("one-square", None), ("tiled-square", 150)):
        params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                              area=area, max_length=150, water="fill", fill_gaps="on", coastline="copernicus",
                              ortho="never", tile_size=tile_size, access=True, same_line_square=5, name=name)
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = dataclasses.replace(search.plan_search(params, paths, lambda kind, text: None), index_runs=False)
        lines, run = search.search_lines(plan)
        kept[name] = search.save_run(plan, lines, run).run["path"]
    table = open(os.path.join(kept["one-square"], "lines.csv"), "rb").read()
    assert table == open(os.path.join(kept["tiled-square"], "lines.csv"), "rb").read()
    assert b",access1,access2,stands_for\r\n" in table[:2000]


def test_the_store_note_is_coded(tmp_path, offline, monkeypatch):
    """A store that cannot be written: the warning is a coded note (error.store_failed) whose page text holds no
    exception text (it may hold paths); the command line's text names the error as before."""
    events = []
    plan = _plan(tmp_path, scene(), "note", events, access=False)
    lines, _ = search.search_lines(plan)

    def failing(run_path, lines, head):
        raise MemoryError(r"no memory at C:\secret\path")
    monkeypatch.setattr(linestore, "write", failing)
    folder = tmp_path / "note" / "runs" / "note"
    folder.mkdir(parents=True)
    search.save_run(plan, lines, {"id": "note", "path": str(folder), "created": datetime(2026, 11, 15), "name": "n"})
    notes = [text for kind, text in events if kind == "warning" and "store" in str(text)]
    assert len(notes) == 1 and isinstance(notes[0], messages.Note) and notes[0].code == "store_failed"
    assert str(notes[0]) == r"The run is saved without its store (lines.arrow): MemoryError: no memory at C:\secret\path"
    assert notes[0].web_text() == messages.text("error.store_failed") and "secret" not in notes[0].web_text()
    assert "store" not in json.loads((folder / "run.json").read_text(encoding="utf-8"))


def test_favourite_keeps_the_access_mark():
    """web.FavouriteLine: access1 and access2 optional (0, 1 or 2; kept only when given, as the A-frame heights);
    anything else refused."""
    import web
    values = {"len": 50.0, "clr": 2.0, "clrN": None, "e1": 10.0, "e2": 11.0, "over": False, "water": 0.0,
              "filled": 0.0, "hmax": 5.0, "hmean": 3.0, "highPct": 40.0, "angle1": 10.0, "angle2": 12.0,
              "prom1": None, "prom2": None, "drop1": None, "drop2": None}
    request = lambda data: {"line": "50.1,19.1,50.2,19.2", "favourite": True, "data": data}  # noqa: E731
    _, stored = web.checked_favourite(request(values))
    assert "access1" not in stored and "access2" not in stored
    _, stored = web.checked_favourite(request({**values, "access1": 2, "access2": 0}))
    assert (stored["access1"], stored["access2"]) == (2, 0)
    _, stored = web.checked_favourite(request({**values, "access1": None, "access2": 1}))
    assert "access1" not in stored and stored["access2"] == 1
    for wrong in (3, -1, 1.5, True, "2"):
        with pytest.raises(ValueError):
            web.checked_favourite(request({**values, "access1": wrong}))


def test_web_process_never_imports_access(tmp_path):
    """The web app (create_app) imports neither access.py nor numba nor search (heavy work only in the worker)."""
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            f"web.create_app({str(tmp_path)!r}, token='t', start_scheduler=False)\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in ('access', 'numba', 'search'))))")
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                            timeout=300, env={**os.environ, **OFFLINE_ENV})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_warm_up_compiles_the_access_kernels(tmp_path):
    """warmup.warm_up compiles access.py's kernels too (on the read-only memory-mapped terrain and on the smoothed
    heights of whole metres): afterwards a search with --access compiles nothing (no new file in numba's cache)."""
    numba_dir = tmp_path / "numba"
    env = {**os.environ, **OFFLINE_ENV, "NUMBA_CACHE_DIR": str(numba_dir)}
    result = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {REPO!r}); import warmup; "
                                                   f"warmup.warm_up({str(tmp_path / 'data')!r})"],
                            capture_output=True, text=True, encoding="utf-8", timeout=900, env=env)
    assert result.returncode == 0 and "warm-up failed" not in result.stderr, result.stdout + result.stderr
    files = lambda pattern: {os.path.basename(p) for p in glob.glob(str(numba_dir / "**" / pattern),  # noqa: E731
                                                                  recursive=True)}
    kernels = {name.split("-")[0] for name in files("*.nbi")}
    assert {"access._walk", "access._stands_near"} <= kernels, kernels
    compiled = files("*.nbc")
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--surface-file", os.path.join(DATA, "zabi_kon_nmpt.tif"), "--northing", "254608", "--easting", "553966",
         "--radius", "290", "--water", "off", "--fill-gaps", "off", "--ortho", "never", "--no-plot", "--yes",
         "--access", "--data-dir", str(tmp_path / "clip")],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert files("*.nbc") == compiled


PAGE_SCRIPT = r"""
const fs = require("fs");
const read = (path) => { const t = fs.readFileSync(path, "utf-8"); return JSON.parse(t.slice(t.indexOf(" = {") + 3).trim().replace(/;$/, "")); };
const off = read(process.argv[2]), on = read(process.argv[3]);
const lines = (d) => d.lines.map((r) => m.toLine(r, undefined, d.terrain, d.ends));
const columns = (d) => { const c = m.lineColumns(d.lines, d.terrain, d.ends); return d.lines.map((_, i) => m.lineAt(c, i)); };
const text = (ls) => JSON.stringify(ls);
console.log(JSON.stringify({n: on.lines.length, rows: text(lines(on)) === text(lines(off)),
                            cols: text(columns(on)) === text(columns(off)), same: text(columns(on)) === text(lines(on))}));
"""


@pytest.mark.skipif(shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                    reason="needs Node and `npm install` in viewer/")
def test_todays_page_reads_the_run_as_without_the_option(tmp_path, scene_runs):
    """Today's page (viewer/src/types.ts toLine and lineColumns/lineAt, what the result's page reads a run with)
    gives every line of a run made with --access the very values of the run made without it: the access values,
    named by the head's "ends", are values it does not read (the page that shows them is step 1d-P's)."""
    bundle = tmp_path / "types.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: ['src/types.ts'], bundle: true, "
                                  f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    for file in ("data.js", "lines.js"):
        script = tmp_path / "page-test.cjs"
        script.write_text(f"const m = require({json.dumps(str(bundle))});\n{PAGE_SCRIPT}", encoding="utf-8")
        result = subprocess.run(["node", str(script), str(scene_runs["off"] / file), str(scene_runs["on"] / file)],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        out = json.loads(result.stdout)
        assert out == {"n": out["n"], "rows": True, "cols": True, "same": True} and out["n"] > 50, (file, out)
        assert re.search(r'"ends":\["access1","access2"\]', (scene_runs["on"] / file).read_text(encoding="utf-8"))
