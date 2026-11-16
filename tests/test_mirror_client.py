"""The client of the project's data server (docs/mirror-hosting/spec.md, solution C): our own tiles read over HTTP
by the rules of a local mirror folder, the start check (`reach`) asked only by the first planning of a search, and
the later phases of a job on the source its first phase chose.

The tests use a fixture mirror made from tests/data/zabi_kon_nmt.tif (2 km tiles on its pixel edges, as
tools/mirror_tiles.py lays them out), served by tests/http_server.py at /v1/tiles/ as the data server serves them,
and two test sources of a made-up country "zz": one reading the mirror, one reading the file itself, its fall-back.
No test asks the real data server: FINDALINE_MIRROR_URL is empty or the local server. No test waits for a timeout:
the timeouts are asserted as the values passed, the pauses (net._sleep) are patched, the kept answers' clock too."""

import gc
import hashlib
import json
import os
import sys
import threading
import time
import warnings

import numpy as np
import pytest
import rasterio as rio
import requests
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import cache  # noqa: E402
import grid as gd  # noqa: E402
import params as pm  # noqa: E402  (its SOURCE_CHOICES built before the test sources exist)
import sources as src  # noqa: E402
from http_server import Answer  # noqa: E402
from sources import net  # noqa: E402
from sources.layer import _write_tile  # noqa: E402
from sources.layers.files import FileLayer  # noqa: E402
from sources.readers import tilebases  # noqa: E402
from sources.source import Source  # noqa: E402

DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")  # EPSG:2180, 1 m, pixel edges on half metres, 600 x 600 m
POINT = {"northing": 254608, "easting": 553966, "radius": 290}
CENTRE = (50.15623817402453, 19.755691432789234)  # POINT in WGS84
LINE = [50.1557974892899, 19.754284174553067, 50.156678841556854, 19.757098716754268]  # 2 x 100 m around it
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1"}
CRS, TILE_M, ORIGIN = "EPSG:2180", 2000, (0.5, 0.5)
MIRROR = "test/dtm/1m"  # the dataset's folder below the mirror (and below <url>/v1/tiles/)
# The index's extent: the clip lies in tiles (276, 127) and (277, 127); the others are null (outside the data)
EXTENT = (275, 126, 278, 128)
DATA_TILES = [(276, 127), (277, 127)]
# A grid over the clip and 7 km west of it: tiles beyond the extent (273, 274), a null one (275), the two with data
WIDE = (547000.5, 254400.5, 554200.5, 254800.5)


def set_url(value):
    """FINDALINE_MIRROR_URL for this test (None: unset, the default address; nothing asks it then). Not through
    monkeypatch: on Windows os.environ's "" deletes the variable for the processes started later (the CRT's
    putenv), so the empty value is put back as tests/conftest.py puts it."""
    if value is None:
        os.environ.pop("FINDALINE_MIRROR_URL", None)
        return
    os.environ["FINDALINE_MIRROR_URL"] = value
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetEnvironmentVariableW("FINDALINE_MIRROR_URL", value)


@pytest.fixture(autouse=True)
def no_mirror_settings(monkeypatch):
    """No mirror folder of this PC's (the user-level FINDALINE_MIRROR) and no data server unless a test sets one
    (set_url; empty again after it); net's pauses are not waited for (each recorded)."""
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    set_url("")
    pauses = []
    monkeypatch.setattr(net, "_sleep", pauses.append)
    yield pauses
    set_url("")


@pytest.fixture
def offline(monkeypatch):
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)


def make_mirror(root) -> str:
    """The fixture mirror: <root>/test/dtm/1m with the tiles of the clip and an index.json listing every tile of
    EXTENT (null where no data) with its sha256, as tools/mirror_tiles.py writes them. Returns the root."""
    folder = os.path.join(str(root), *MIRROR.split("/"))
    tiles = {}
    with rio.open(CLIP) as clip:
        for j in range(EXTENT[1], EXTENT[3] + 1):
            for i in range(EXTENT[0], EXTENT[2] + 1):
                left, bottom = i * TILE_M + ORIGIN[0], j * TILE_M + ORIGIN[1]
                window = from_bounds(left, bottom, left + TILE_M, bottom + TILE_M, clip.transform)
                band = clip.read(1, window=window, boundless=True, fill_value=np.nan).astype(np.float32)
                if not np.isfinite(band).any():
                    tiles[f"{i}_{j}"] = None
                    continue
                path = os.path.join(folder, *src.grid_tile_name(i, j).split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                _write_tile(path, band, CRS, from_origin(left, bottom + TILE_M, 1.0, 1.0))
                tiles[f"{i}_{j}"] = _sha(path)
    _write_index(folder, tiles)
    return str(root)


def make_averaged(root, factor: int = 2):
    """The 1 m tiles of the fixture mirror averaged to factor metres beside them (<root>/test/dtm/<factor>m), with
    their index (the block means: what tools/sk_tiles.py average makes)."""
    fine = os.path.join(str(root), *MIRROR.split("/"))
    folder = os.path.join(os.path.dirname(fine), f"{factor}m")
    with open(os.path.join(fine, "index.json"), encoding="utf-8") as f:
        index = json.load(f)["tiles"]
    tiles = {}
    for key, sha in index.items():
        if sha is None:
            tiles[key] = None
            continue
        i, j = map(int, key.split("_"))
        with rio.open(os.path.join(fine, *src.grid_tile_name(i, j).split("/"))) as tile:
            band, transform = tile.read(1), tile.transform
        n = TILE_M // factor
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # the blocks without data: NaN
            coarse = np.nanmean(band.reshape(n, factor, n, factor), axis=(1, 3)).astype(np.float32)
        path = os.path.join(folder, *src.grid_tile_name(i, j).split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_tile(path, coarse, CRS, from_origin(transform.c, transform.f, factor, factor), max_z_error=None)
        tiles[key] = _sha(path)
    _write_index(folder, tiles)


def _sha(path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _write_index(folder, tiles, **more):
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"tiles": tiles, **more}, f)


class Mirror:
    """The fixture mirror served at <http_server>/v1/tiles/ from its folder (read at each request, so a test may
    change the files): `status` answers every request with it, `once` a path's next request, `delay` holds each
    answer that many seconds, `fail` a path's next n requests ({path: n}, with 503). `asked(kind)` lists the paths
    asked: "index", "tile" or all."""

    def __init__(self, http_server, root):
        self.server, self.root = http_server, root
        self.status, self.once, self.delay, self.fail = None, {}, 0.0, {}
        http_server.route("/v1/tiles/", self._answer)

    @property
    def url(self) -> str:
        return self.server.base

    def base(self, folder: str = MIRROR) -> str:
        return f"{self.server.base}/v1/tiles/{folder}"

    def _answer(self, request):
        if self.delay:
            time.sleep(self.delay)
        if self.fail.get(request.path):
            self.fail[request.path] -= 1
            return Answer(503, b"down", {"Content-Type": "text/plain"})
        status = self.once.pop(request.path, None) or self.status
        if status:
            return Answer(status, b"refused", {"Content-Type": "text/plain"})
        path = os.path.join(self.root, *request.path[len("/v1/tiles/"):].split("/"))
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            body = f.read()
        return Answer(200, body, {"Content-Type": "application/json" if path.endswith(".json") else "image/tiff"})

    def asked(self, kind: str = "") -> list:
        paths = [r.path for r in self.server.requests("/v1/tiles/")]
        if kind == "index":
            return [p for p in paths if p.endswith("index.json")]
        return [p for p in paths if p.endswith(".tif")] if kind == "tile" else paths


@pytest.fixture
def mirror(tmp_path, http_server, monkeypatch):
    """The fixture mirror on the local server, FINDALINE_MIRROR_URL naming it."""
    served = Mirror(http_server, make_mirror(tmp_path / "served"))
    set_url(served.url)
    return served


def mirrored_layer(urls=(), averaged=()):
    return src.GridTiles("Test DTM (mirrored)", list(urls), CRS, "test/mirrored/epsg2180-1m-2km", TILE_M, 1.0, 2e6,
                         mirror=MIRROR, origin=ORIGIN, averaged=averaged, tool="tests/test_mirror_client.py")


@pytest.fixture
def two_sources(monkeypatch):
    """The test sources of the country "zz": test_mirrored (our own tiles) before test_plain (the clip as a file),
    which --source auto takes when test_mirrored cannot be used. Returns the mirrored source."""
    common = dict(countries=("zz",), crs=CRS, default_resolution=1.0, grid_origin=ORIGIN, fallback=None,
                  sample=CENTRE)
    mirrored = Source(id="test_mirrored", name="Test mirrored", description="test tiles of the data server",
                      nmt=mirrored_layer(), **common)
    plain = Source(id="test_plain", name="Test plain", description="the clip as a file",
                   nmt=FileLayer("Terrain file", CLIP), **common)
    monkeypatch.setitem(src.SOURCES, mirrored.id, mirrored)
    monkeypatch.setitem(src.SOURCES, plain.id, plain)
    monkeypatch.setattr(pm, "SOURCE_CHOICES", pm.SOURCE_CHOICES + [mirrored.id, plain.id])  # a named one validates
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "zz")
    return mirrored


@pytest.fixture
def clock(monkeypatch):
    """The clock of the kept indexes and remembered failures: now[0] seconds."""
    now = [1000.0]
    monkeypatch.setattr(tilebases, "_clock", lambda: now[0])
    return now


def _download(layer, cache_dir, bounds=WIDE, res=1.0):
    grid = gd.make_grid(bounds, res, CRS, ORIGIN)
    layer.download(grid, str(cache_dir), None, "test")
    return grid


def _in_process(monkeypatch):
    """run_phase in the test's process: what it changes here is put back after the test."""
    import osm
    import progress
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(progress, "TEXT_INTERVAL", progress.TEXT_INTERVAL)
    monkeypatch.setattr(progress, "_listeners", list(progress._listeners))
    monkeypatch.setattr(osm, "BEFORE_REQUEST", osm.BEFORE_REQUEST)


def _request(**values):
    return {"params": {"source": "auto", "water": "off", "fill_gaps": "off", "nmpt": "off", "ortho": "never",
                       **POINT, **values}, "geometry": None}


def _run_json(data_dir, job_row) -> dict:
    with open(os.path.join(str(data_dir), "runs", job_row["run_id"], "run.json"), encoding="utf-8") as f:
        return json.load(f)


def _phases(monkeypatch, data_dir, request, between=lambda: None):
    """A web job's two phases (jobs.run_phase), `between` called after the download phase; the compute phase's plan
    is kept (search.search_lines spied). Returns (the job's row, the compute phase's plan, its events' texts)."""
    import jobs as jb
    import search
    _in_process(monkeypatch)
    planned = []
    lines = search.search_lines
    monkeypatch.setattr(search, "search_lines", lambda plan: (planned.append(plan), lines(plan))[1])
    os.makedirs(str(data_dir), exist_ok=True)
    jobs = jb.Jobs(str(data_dir))
    job = jobs.add(request, "mirror")
    jobs.claim("queued", "downloading", "w1")
    jb.run_phase(str(data_dir), job, "download")
    assert jobs.get(job)["status"] == "ready", jobs.get(job)["error"]
    between()
    jobs.claim("ready", "computing", "w1")
    jb.run_phase(str(data_dir), job, "compute")
    row = jobs.get(job)
    assert row["status"] == "done", row["error"]
    said = [e["data"] for e in jobs.events(0, job) if e["kind"] == "info" and isinstance(e["data"], str)]
    gc.collect()
    return row, planned[-1], said


# Where the tiles come from

def test_the_bases_and_the_setting(tmp_path, monkeypatch):
    """The local folder (when it holds the dataset), then the data server (MIRROR_URL, or FINDALINE_MIRROR_URL; empty
    turns it off), then the catalogue's URLs; with none of them the text names both settings."""
    layer = mirrored_layer(["https://other.example/test/dtm/1m"])
    reader = layer.readers[1.0]
    set_url(None)
    assert tilebases.mirror_url() == tilebases.MIRROR_URL == "https://mirror.findaline.lukawski.org"  # no request
    assert reader.bases() == [f"{tilebases.MIRROR_URL}/v1/tiles/test/dtm/1m", "https://other.example/test/dtm/1m"]
    set_url("http://127.0.0.1:8080/")  # http:// accepted (P28), the slash dropped
    assert reader.bases()[0] == "http://127.0.0.1:8080/v1/tiles/test/dtm/1m"
    root = make_mirror(tmp_path / "local")
    monkeypatch.setenv("FINDALINE_MIRROR", root)
    assert reader.bases()[0] == os.path.join(root, "test", "dtm", "1m") and len(reader.bases()) == 3
    set_url("")
    monkeypatch.delenv("FINDALINE_MIRROR")
    alone = mirrored_layer()
    assert alone.bases() == [] and alone.remote_base() is None
    why = alone.unavailable()
    assert "set FINDALINE_MIRROR" in why and "FINDALINE_MIRROR_URL" in why and "data server" in why


def test_the_same_files_as_from_the_folder(tmp_path, mirror):
    """Over HTTP the cache gets the very files a local folder gives (byte for byte, the same rows); tiles beyond the
    index's extent and those it lists as null are missing without a request; the index is asked once; the tiles
    with the data server's timeouts."""
    asked = []
    get = net._get
    net_get = lambda url, **kw: (asked.append((url, kw)), get(url, **kw))[1]  # noqa: E731
    layer = mirrored_layer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(net, "_get", net_get)
        grid = _download(layer, tmp_path / "http")
    tiles = layer.tiles(grid)
    assert {t[1] for t in tiles} == {273, 274, 275, 276, 277}
    assert sorted(mirror.asked("tile")) == sorted(f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*t)}" for t in DATA_TILES)
    assert mirror.asked("index") == [f"/v1/tiles/{MIRROR}/index.json"]
    timeouts = {url.rsplit("/", 1)[1]: kw["timeout"] for url, kw in asked}
    assert timeouts["index.json"] == tilebases.MIRROR_TIMEOUT == (10, 300)
    assert all(t == (10, 300) for t in timeouts.values())
    assert [kw.get("binary_types") for url, kw in asked if url.endswith("index.json")] == [("json",)]

    local = mirrored_layer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("FINDALINE_MIRROR", mirror.root)
        patch.setattr(net, "_get", lambda *a, **k: pytest.fail("the local folder first: no request"))
        _download(local, tmp_path / "folder")
    for tile in tiles:
        a, b = layer.tile_path(str(tmp_path / "http"), tile), local.tile_path(str(tmp_path / "folder"), tile)
        assert cache.state(str(tmp_path / "http"), a) == cache.state(str(tmp_path / "folder"), b)
        assert os.path.exists(a) == os.path.exists(b) == (tile[1:] in DATA_TILES)
        if os.path.exists(a):
            assert _sha(a) == _sha(b)


def test_a_listed_tile_not_on_the_server(tmp_path, mirror, no_mirror_settings):
    """A 404 for a tile the index lists is an error, never "no data": no row and no file; after the pause the index
    is taken again once and the tile asked once more."""
    layer = mirrored_layer()
    name = f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*DATA_TILES[0])}"
    os.remove(os.path.join(mirror.root, *name[len("/v1/tiles/"):].split("/")))
    path = layer.tile_path(str(tmp_path / "cache"), (1.0, *DATA_TILES[0]))
    with pytest.raises(RuntimeError, match=r"Could not download Test DTM \(mirrored\) tile .*HTTP 404.*also after"):
        layer._download_and_record((1.0, *DATA_TILES[0]), str(tmp_path / "cache"))
    assert cache.state(str(tmp_path / "cache"), path) is None and not os.path.exists(path)
    assert mirror.asked() == [f"/v1/tiles/{MIRROR}/index.json", name] * 2
    assert no_mirror_settings == [tilebases.HEAL_PAUSE]


def test_a_wrong_hash(tmp_path, mirror):
    """A tile that does not match its index (and an index that does not match its tile) is refused before it is
    written, after one more try."""
    layer = mirrored_layer()
    tile = (1.0, *DATA_TILES[0])
    served = os.path.join(mirror.root, *MIRROR.split("/"), *src.grid_tile_name(*DATA_TILES[0]).split("/"))
    with open(served, "ab") as f:
        f.write(b"x")
    path = str(tmp_path / "t.tif")
    with pytest.raises(RuntimeError, match="does not match the sha256 of its index, also after"):
        layer.download_tile(tile, path)
    assert not os.path.exists(path) and not [p for p in os.listdir(tmp_path) if p.endswith(".part")]
    make_mirror(tmp_path / "served")  # the tile as it was, its index's sha256 wrong now
    index = os.path.join(mirror.root, *MIRROR.split("/"), "index.json")
    with open(index, encoding="utf-8") as f:
        tiles = json.load(f)["tiles"]
    _write_index(os.path.dirname(index), {**tiles, "276_127": "0" * 64})
    with pytest.raises(RuntimeError, match="does not match"):
        mirrored_layer().download_tile(tile, path)
    assert not os.path.exists(path)


def test_a_swap_heals(tmp_path, mirror, no_mirror_settings):
    """A dataset swapped on the server (the same values, other bytes) after the index was kept: the tile does not
    match the kept index, the index is taken again once after the pause, and the tile once more."""
    layer = mirrored_layer()
    cache_dir = str(tmp_path / "cache")
    layer._download_and_record((1.0, *DATA_TILES[0]), cache_dir)  # the index is kept now
    folder = os.path.join(mirror.root, *MIRROR.split("/"))
    served = os.path.join(folder, *src.grid_tile_name(*DATA_TILES[1]).split("/"))
    with rio.open(served) as tile:
        band, transform = tile.read(1), tile.transform
    _write_tile(served, band, CRS, transform, tags={"edition": "re-encoded"})
    with open(os.path.join(folder, "index.json"), encoding="utf-8") as f:
        tiles = json.load(f)["tiles"]
    _write_index(folder, {**tiles, "277_127": _sha(served)})
    before = len(mirror.asked())
    layer._download_and_record((1.0, *DATA_TILES[1]), cache_dir)
    name = f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*DATA_TILES[1])}"
    assert mirror.asked()[before:] == [name, f"/v1/tiles/{MIRROR}/index.json", name]
    assert _sha(layer.tile_path(cache_dir, (1.0, *DATA_TILES[1]))) == _sha(served)
    assert no_mirror_settings == [tilebases.HEAL_PAUSE]


def test_an_index_missing_for_a_moment(tmp_path, mirror, no_mirror_settings):
    """The index 404 for a moment (a publish between its two moves) heals after the pause."""
    mirror.once[f"/v1/tiles/{MIRROR}/index.json"] = 404
    assert mirrored_layer().download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif")).received > 0
    assert mirror.asked("index") == [f"/v1/tiles/{MIRROR}/index.json"] * 2 and no_mirror_settings == [2]


def test_a_partial_index_goes_to_the_next_base(tmp_path, mirror, http_server):
    """A tile a "partial" index does not list is looked for in the next base (here a second copy among the
    catalogue's URLs); without one it is an error, never "no data"."""
    folder = os.path.join(mirror.root, *MIRROR.split("/"))
    with open(os.path.join(folder, "index.json"), encoding="utf-8") as f:
        tiles = json.load(f)["tiles"]
    _write_index(folder, {k: v for k, v in tiles.items() if k != "277_127"}, partial=True)
    full = make_mirror(tmp_path / "second")
    http_server.add_folder("/second", full)
    layer = mirrored_layer([http_server.url(f"/second/{MIRROR}")])
    assert layer.download_tile((1.0, *DATA_TILES[1]), str(tmp_path / "t.tif")).received > 0
    assert [r.path for r in http_server.requests("/second/")] == [
        f"/second/{MIRROR}/index.json", f"/second/{MIRROR}/{src.grid_tile_name(*DATA_TILES[1])}"]
    with pytest.raises(RuntimeError, match="not in .* yet"):
        mirrored_layer().download_tile((1.0, *DATA_TILES[1]), str(tmp_path / "u.tif"))
    # a tile beyond the keys of a partial index is not known to be outside the data either
    with pytest.raises(RuntimeError, match="not in .* yet"):
        mirrored_layer().download_tile((1.0, 300, 127), str(tmp_path / "v.tif"))


def test_eight_threads_ask_for_the_index_once(tmp_path, mirror):
    """The download threads that need a base's index at the same moment get one fetch, also its failure: a dead
    server is not paid once per thread."""
    def together(layer):
        reader, results = layer.readers[1.0], []
        barrier = threading.Barrier(8)

        def ask():
            barrier.wait()
            try:
                results.append(reader._remote_index(mirror.base())[0])
            except RuntimeError as e:
                results.append(e)
        threads = [threading.Thread(target=ask) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results
    mirror.delay = 0.2
    results = together(mirrored_layer())
    assert len(results) == 8 and all(isinstance(r, dict) and r for r in results)
    assert len(mirror.asked("index")) == 1
    mirror.status = 503
    results = together(mirrored_layer())
    assert all(isinstance(r, RuntimeError) and "HTTP 503" in str(r) for r in results)
    assert len(mirror.asked("index")) == 1 + net.RETRIES  # one fetch of three attempts for all eight


def test_the_index_is_kept_for_its_time(tmp_path, mirror, clock):
    """An index is kept in memory INDEX_SECONDS (300 s), then taken again."""
    layer = mirrored_layer()
    reader = layer.readers[1.0]
    reader._remote_index(mirror.base())
    clock[0] += 299
    reader._remote_index(mirror.base())
    assert len(mirror.asked("index")) == 1
    clock[0] += 2
    reader._remote_index(mirror.base())
    assert len(mirror.asked("index")) == 2 and tilebases.INDEX_SECONDS == 300


def test_averaged_tiles_over_http(tmp_path, mirror):
    """A grid of an averaged resolution reads that resolution's folder of the data server (available whenever a remote
    base is set: the same choice in every phase); its index missing is an error with a clear text, never a switch to
    the 1 m tiles."""
    layer = mirrored_layer(averaged=(2,))
    assert layer.resolution(2.0) == 2.0
    with pytest.raises(RuntimeError, match=r"test/dtm/2m/index.json is not on the server \(HTTP 404\): this dataset "
                                           r"or resolution is not published there"):
        _download(layer, tmp_path / "none", res=2.0)
    assert mirror.asked() and all("/test/dtm/2m/" in p for p in mirror.asked())
    make_averaged(mirror.root)
    before = len(mirror.asked())
    grid = _download(mirrored_layer(averaged=(2,)), tmp_path / "cache", res=2.0)
    assert all("/test/dtm/2m/" in p for p in mirror.asked()[before:]) and mirror.asked("tile")
    assert all(t[0] == 2.0 for t in layer.tiles(grid))


# The start check (reach)

def test_reach_answers(tmp_path, mirror, clock, two_sources):
    """reach asks the native index (kept then for the downloads); a 429 answers (busy); a 503, any 5xx and a 404 of
    the index do not; a failure is remembered 60 s for later start checks only; nothing asks without reach=True."""
    layer = mirrored_layer()
    assert layer.reach() is None and len(mirror.asked("index")) == 1
    _download(layer, tmp_path / "cache")  # the kept index: no second request
    assert len(mirror.asked("index")) == 1

    mirror.status = 429
    assert mirrored_layer().reach() is None  # busy: it is there
    for status, detail in ((503, "HTTP 503"), (500, "HTTP 500"), (404, "HTTP 404: not published there")):
        mirror.status = status
        why = mirrored_layer().reach()
        assert why == f"Test DTM (mirrored): the data copy at 127.0.0.1 does not answer ({detail})", status
    mirror.status = 503
    remembered = mirrored_layer()
    asked = len(mirror.asked())
    assert remembered.reach() and len(mirror.asked()) == asked + tilebases.REACH_ATTEMPTS
    mirror.status = None
    clock[0] += 59
    assert "does not answer" in remembered.reach() and len(mirror.asked()) == asked + 2  # remembered: no request
    # ... for the start checks only: a download asks (and works) meanwhile
    assert remembered.download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif")).received > 0
    clock[0] += 2
    assert remembered.reach() is None and tilebases.UNANSWERED_SECONDS == 60


def test_reach_without_an_answer(tmp_path, mirror, monkeypatch, two_sources):
    """No HTTP answer at all (a dead home server): the start check's timeouts (10 s to connect, 20 s per read) and
    two attempts, then "does not answer"; auto takes the next source with the reason, a named source is an error;
    without reach=True nothing is asked and the source is used."""
    calls = []

    def dead(url, **kwargs):
        calls.append((url, kwargs["timeout"]))
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(requests, "get", dead)
    lat, lon = CENTRE
    source, why = src.choose_source("auto", lat, lon, str(tmp_path))  # reach off: no request
    assert source.id == "test_mirrored" and why == "the centre is in ZZ" and not calls
    source, why = src.choose_source("auto", lat, lon, str(tmp_path), reach=True)
    assert source.id == "test_plain"
    assert why == "the centre is in ZZ, but Test DTM (mirrored): the data copy at 127.0.0.1 does not answer (no answer)"
    assert calls == [(f"{mirror.base()}/index.json", (10, 20))] * 2
    with pytest.raises(ValueError, match="does not answer"):
        src.choose_source("test_mirrored", lat, lon, str(tmp_path), reach=True)
    assert len(calls) == 2  # remembered
    assert src.choose_source("test_mirrored", lat, lon, str(tmp_path))[0].id == "test_mirrored"
    assert src.choose.source_unreachable(two_sources) and src.choose.source_unavailable(two_sources) is None


def test_the_local_folder_wins(tmp_path, mirror, monkeypatch, two_sources):
    """With the local folder holding the dataset its tiles come from there; the start check asks nothing (the folder
    answers), however the data server is."""
    monkeypatch.setenv("FINDALINE_MIRROR", make_mirror(tmp_path / "local"))
    mirror.status = 503
    layer = mirrored_layer()
    assert layer.reach() is None and layer.remote_base() is None
    _download(layer, tmp_path / "cache")
    assert src.choose_source("auto", *CENTRE, str(tmp_path), reach=True)[0].id == "test_mirrored"
    assert mirror.asked() == []


def test_no_data_server(tmp_path, http_server, monkeypatch, two_sources):
    """FINDALINE_MIRROR_URL empty and no folder: the source is unavailable as before, nothing is asked."""
    Mirror(http_server, make_mirror(tmp_path / "served"))
    source, why = src.choose_source("auto", *CENTRE, str(tmp_path), reach=True)
    assert source.id == "test_plain" and "FINDALINE_MIRROR_URL" in why
    assert two_sources.nmt.reach() is None and http_server.log == []


def test_the_estimate(tmp_path, mirror, monkeypatch):
    """An estimate from the data server counts only the tiles a kept index lists with data; without a kept index
    every tile not cached (an upper bound); a local folder's estimate as before."""
    grid = gd.make_grid(WIDE, 1.0, CRS, ORIGIN)
    layer = mirrored_layer()
    assert layer.estimate(grid, str(tmp_path / "a"), None) == (5, 5, 5 * 2.0)
    assert layer.reach() is None
    assert layer.estimate(grid, str(tmp_path / "a"), None) == (5, 2, 2 * 2.0)
    monkeypatch.setenv("FINDALINE_MIRROR", mirror.root)
    local = mirrored_layer()
    assert local.estimate(grid, str(tmp_path / "b"), None) == (5, 5, 5 * 2.0)


# The phases of a job and the finished runs

def test_a_job_that_fell_back_computes_on_the_fallback(tmp_path, monkeypatch, offline, two_sources):
    """A job whose first phase fell back (its mirror could not be used then) computes on the fall-back's source
    although the mirror is back by the later phase: the later phase never chooses again. The search's params keep
    the source as the user gave it ("auto"), so its hash is that of the request and the first phase's source, and
    run.json's source is the one the first phase stored."""
    import search
    mirror = make_mirror(tmp_path / "mirror")
    data = tmp_path / "data"
    row, plan, _ = _phases(monkeypatch, data, _request(),
                           between=lambda: monkeypatch.setenv("FINDALINE_MIRROR", mirror))  # the mirror is back
    assert row["source"] == "test_plain"  # stored by the download phase: the fall-back
    meta = _run_json(data, row)
    assert meta["source"]["id"] == "test_plain" == plan.source.id
    assert plan.params.source == "auto"  # run.json's params hold no source; the hash's params do
    key = search._search_key(plan)
    assert key["params"]["source"] == "auto" and key["source"] == "test_plain"


def test_later_phases_and_finished_runs_with_the_server_down(tmp_path, monkeypatch, offline, mirror, two_sources):
    """The first phase chose the mirrored source over HTTP; with the data server down after it, the compute phase
    completes from the cache on that source ("chosen when the search started"), the hash's params as given. Then, in
    the same process (the quick lane's), a failed estimate's remembered failure never touches the finished run's
    profile and 3D patch, which work from the cache."""
    import jobs as jb
    import search
    data = tmp_path / "data"
    request = _request(radius=650)  # its grid holds every tile the 3D patch below needs (the run's cache)
    row, plan, said = _phases(monkeypatch, data, request, between=lambda: setattr(mirror, "status", 503))
    assert row["source"] == "test_mirrored" == _run_json(data, row)["source"]["id"] == plan.source.id
    assert search._search_key(plan)["params"]["source"] == "auto"
    assert any(text.startswith("Data: Test mirrored (chosen when the search started) - ") for text in said), said
    asked = len(mirror.asked())
    two_sources.nmt.readers[1.0]._kept.clear()  # the quick lane is another process: no index kept from the phases
    estimate = jb.quick_estimate(str(data), request)  # reach: the server does not answer, auto falls back
    assert estimate["source"] == "Test plain" and len(mirror.asked()) == asked + tilebases.REACH_ATTEMPTS
    asked = len(mirror.asked())
    profile = jb.quick_profile(str(data), {"run": row["run_id"], "line": LINE})
    patch = jb.quick_patch(str(data), {"run": row["run_id"], "line": LINE})
    assert profile and patch["heights"] and len(mirror.asked()) == asked  # all from the cache, nothing asked
    with pytest.raises(search.SearchError, match="does not answer"):  # the remembered failure: for start checks only
        search.plan_search(search.SearchParams(**{**request["params"], "source": "test_mirrored"}),
                           search.Paths(str(data), str(tmp_path / "w")), lambda kind, text: None, reach=True)


def test_down_in_the_middle(tmp_path, mirror, offline, two_sources):
    """The data server answers the start check, then fails a tile: the download fails with "Could not download"
    (the phase's error, U6) and keeps what came; run again, it asks only for what is missing."""
    import search
    paths = search.Paths(str(tmp_path / "data"), str(tmp_path / "work"))
    os.makedirs(paths.work)
    params = search.SearchParams(**{**_request()["params"], "radius": 290})
    plan = search.plan_search(params, paths, lambda kind, text: None, reach=True)
    assert plan.source.id == "test_mirrored"
    tiles = [t for t in plan.source.nmt.tiles(plan.grid)]
    assert {t[1:] for t in tiles} == set(DATA_TILES)
    second = f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*DATA_TILES[1])}"
    mirror.fail[second] = net.RETRIES  # every attempt of net._get
    with pytest.raises(search.SearchError, match=rf"Download failed: Could not download Test DTM \(mirrored\) tile "
                                                 rf"{src.grid_tile_name(*DATA_TILES[1])}: HTTP 503"):
        search.download_data(plan)
    assert [cache.state(paths.cache, plan.source.nmt.tile_path(paths.cache, t)) for t in sorted(tiles)] == ["ok", None]
    before = len(mirror.asked("tile"))
    search.download_data(search.plan_search(params, paths, lambda kind, text: None, reach=True))
    assert mirror.asked("tile")[before:] == [second]


def test_a_neighbour_whose_server_is_down_is_skipped(tmp_path, mirror, two_sources, capsys):
    """A neighbour read from the data server that does not answer is skipped with today's text (P5): no start check
    of its own (only the download's attempts)."""
    grid = gd.make_grid((553700.5, 254400.5, 554200.5, 254800.5), 1.0, CRS, ORIGIN)
    band = np.full((grid.height, grid.width), 100.0, np.float32)
    band[:, :100] = np.nan  # a gap reaching the grid's edge: a border gap
    path = str(tmp_path / "nmt.npy")
    np.save(path, band)
    mirror.status = 503
    filled, counts = src.filling.fill_from_neighbours(path, None, grid, [two_sources], str(tmp_path / "cache"),
                                                      str(tmp_path / "joined.npy"))
    out = capsys.readouterr().out
    assert filled is None and "Gaps at the border not filled from Test mirrored: Could not download" in out
    assert len(mirror.asked("index")) >= net.RETRIES and not mirror.asked("tile")


def test_a_country_run_reaches_once(tmp_path, mirror, two_sources, monkeypatch):
    """A country run's main process asks once whether its own source answers, before the band plans, and does not
    start when it does not (a resume with every tile cached too); its band plans (the workers') never ask."""
    import country
    calls = []
    reach = tilebases.TileBases.reach
    monkeypatch.setattr(tilebases.TileBases, "reach", lambda self: (calls.append(1), reach(self))[1])
    mirror.status = 503
    lat, lon = CENTRE
    area = tmp_path / "area.geojson"
    d = 0.001
    area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[
        [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]]}}))
    config = {"id": "zz", "name": "Testland", "source": "test_mirrored", "area": str(area),
              "bands": [{"name": "S", "lengths": [30, 150], "resolution": 1.0, "model": "formula",
                         "slope_threshold": 45, "core_m": 200, "layer": True}],
              "tension": [[30, 2.5], [300, 6.0]], "rig": {"webbing_weight": 41.0, "stretch": 2.1, "fall_zone": 3.0},
              "options": {"nmpt": "off", "water": "off", "fill_gaps": "off"}}
    c = country.Country.from_config(config)
    with pytest.raises(country.CountryError, match=r"test_mirrored cannot be used now: .*does not answer \(HTTP 503\)"):
        country._check_reach(c)
    assert calls == [1]
    country._check_reach(country.Country.from_config({**config, "options": {"elevation_file": CLIP}}))
    assert calls == [1]  # local files: nothing to ask

    # The run: one start check, before any band plan; it does not start
    data = tmp_path / "data"
    (data / "countries" / "zz").mkdir(parents=True)
    (data / "countries" / "zz" / "country.json").write_text(json.dumps({"config": config}))
    planned = []
    with monkeypatch.context() as patch:
        patch.setattr(country, "band_plan", lambda *a, **k: planned.append(1))
        two_sources.nmt.readers[1.0]._unanswered.clear()  # a new process: nothing remembered
        assert country.run("zz", str(data), processes=0, yes=True) == 1
    assert calls == [1, 1] and not planned

    # A worker's plan (band_plan): no start check, no request, though the server does not answer
    asked = len(mirror.asked())
    plan = country.band_plan(c, c.bands[0], str(data / "countries" / "zz"), str(data))
    assert plan.source.id == "test_mirrored" and calls == [1, 1] and len(mirror.asked()) == asked


def test_the_probe(tmp_path, mirror, two_sources):
    """The probe's row of our own tiles on the data server: the start check as its index, one byte of the first tile
    its index lists with data; a server that does not answer fails the index with the reason."""
    from sources import probe
    folder = str(tmp_path / "probe")
    os.makedirs(folder)
    row = probe.probe_layer(two_sources, two_sources.nmt, "terrain", str(tmp_path / "cache"), folder, False)
    assert (row.index, row.read) == (probe.OK, probe.OK), row.notes
    ranged = [r for r in mirror.server.requests("/v1/tiles/") if r.path.endswith(".tif")]
    assert [r.headers.get("range") for r in ranged] == ["bytes=0-0"]
    assert ranged[0].path.rsplit("/", 1)[1][:-4] in {f"{i}_{j}" for i, j in DATA_TILES}
    mirror.status = 503
    two_sources.nmt.readers[1.0]._unanswered.clear()
    two_sources.nmt.readers[1.0]._kept.clear()
    row = probe.probe_layer(two_sources, two_sources.nmt, "terrain", str(tmp_path / "cache"), folder, False)
    assert row.index == probe.FAILED and "does not answer (HTTP 503)" in row.notes[0]


def test_the_web_pages_make_no_request(tmp_path, http_server, monkeypatch):
    """The web process asks no data server: the form's schema, the about page, the privacy page and the orthophotos'
    origins are built from the catalogue's names and credits alone (FINDALINE_MIRROR_URL naming a local server,
    which sees nothing, and no socket connects)."""
    import socket
    import web
    from settings import Limits
    set_url(http_server.base)
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("a connection from the web process"))
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("a request from the web process"))
    assert web.schema(Limits()) and web.schema()
    assert web.about_page("contact@example.org") and web.privacy_page("contact@example.org", 30)
    assert web.ortho_origins()
    assert http_server.log == []


def test_the_hosts_manners():
    """The data server's host: 2 connections and 600 requests a minute (half of what its limits allow an address),
    the start check's timeouts and attempts (docs/mirror-hosting/spec.md C.3, C.6)."""
    host = "mirror.findaline.lukawski.org"
    assert tilebases.MIRROR_URL == f"https://{host}"
    assert net.HOST_SLOTS_OF[host] == 2
    assert tilebases.REACH_TIMEOUT == (10, 20) and tilebases.REACH_ATTEMPTS == 2
    assert tilebases.MIRROR_TIMEOUT == (10, 300)
    assert tilebases.UNANSWERED_SECONDS == 60 and tilebases.INDEX_SECONDS == 300


def test_index_requests_take_their_turn(tmp_path, mirror, monkeypatch):
    """The index's requests (and the tiles') take the host's rate turn (net.rate_turn through net._get); the
    tiles also a slot of the host (net.host_slot), the index none."""
    turns = []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(url))
    layer = mirrored_layer()
    _download(layer, tmp_path / "cache")
    assert f"{mirror.base()}/index.json" in turns
    assert sum(u.endswith(".tif") for u in turns) == len(DATA_TILES)
    assert layer.tile_url((1.0, *DATA_TILES[0])) == mirror.base()  # the host the tiles' slots are of


def test_the_processes_of_the_tests_ask_no_data_server():
    """A process a test starts (a worker's phase, the quick lane, a search) inherits the empty FINDALINE_MIRROR_URL
    of tests/conftest.py, also on Windows, where os.environ's "" alone would leave it unset (the default address)."""
    import subprocess
    code = "import os; print(repr(os.environ.get('FINDALINE_MIRROR_URL', 'unset')))"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "''"
