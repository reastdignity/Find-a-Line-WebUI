"""The client of the project's data server (docs/mirror-hosting/spec.md, solution C): our own tiles read over HTTP
by the rules of a local mirror folder, the start check (`reach`) asked only by the first planning of a search, and
the later phases of a job on the source its first phase chose.

The tests use a fixture mirror made from tests/data/zabi_kon_nmt.tif (2 km tiles on its pixel edges, as
tools/mirror_tiles.py lays them out), served by tests/http_server.py at /v1/tiles/ as the data server serves them,
and two test sources of a made-up country "zz": one reading the mirror, one reading the file itself, its fall-back.
No test asks the real data server: FINDALINE_MIRROR_URL is off (as tests/conftest.py sets it), empty, or the local server. No test waits for a timeout:
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
# Served indexes the client cannot read (the data server's fault, or a publish gone wrong)
MALFORMED = {"a key": b'{"tiles": {"a_b": null}, "block": 10}', "tiles null": b'{"tiles": null, "block": 10}',
             "not JSON": b"<html>not an index</html>", "no block": b'{"tiles": {}}',
             "not a sha256": b'{"tiles": {"276_127": 123}, "block": 10}'}
# A flat dataset of 3 x 2 small tiles (200 m) for the connections' tests
FLAT, FLAT_BOUNDS = "test/flat/1m", (554000.5, 254000.5, 554599.5, 254399.5)


def _os_level_url():
    """FINDALINE_MIRROR_URL as a process started now inherits it (None: unset). On Windows that is the process's
    environment block, which os.environ's "" deletes."""
    if os.name != "nt":
        return os.environ.get("FINDALINE_MIRROR_URL")
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(4096)
    if not kernel32.GetEnvironmentVariableW("FINDALINE_MIRROR_URL", buffer, 4096) and ctypes.get_last_error() == 203:
        return None  # ERROR_ENVVAR_NOT_FOUND
    return buffer.value


AT_COLLECTION = _os_level_url()  # when pytest imports this module: only tests/conftest.py has acted on it then


def set_url(value):
    """FINDALINE_MIRROR_URL for this test (None: unset, the default address; nothing asks it then). The autouse
    fixture puts "off" back after each test, as tests/conftest.py sets it (an empty value would be deleted for the
    processes started later on Windows: the CRT's putenv)."""
    if value is None:
        os.environ.pop("FINDALINE_MIRROR_URL", None)
        return
    os.environ["FINDALINE_MIRROR_URL"] = value


@pytest.fixture(autouse=True)
def no_mirror_settings(monkeypatch):
    """No mirror folder of this PC's (the user-level FINDALINE_MIRROR) and no data server unless a test sets one
    (set_url; off again after it); net's pauses are not waited for (each recorded)."""
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    set_url("off")
    pauses = []
    monkeypatch.setattr(net, "_sleep", pauses.append)
    monkeypatch.setattr(net, "LIMITS_AS", {})  # the addresses a test named take no other host's manners later
    yield pauses
    set_url("off")


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
    """An index.json as tools/sk_tiles.py writes it (the fields the client reads: tiles, block, partial)."""
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"tiles": tiles, "block": 10, **more}, f)


def flat_layer(urls=()):
    return src.GridTiles("Flat test", list(urls), CRS, "test/flat/epsg2180-1m-200m", 200, 1.0, 1e5, mirror=FLAT,
                         origin=ORIGIN, tool="tests/test_mirror_client.py")


def make_flat(root, keys):
    """The flat dataset's tiles (i, j) of keys under <root>/test/flat/1m, with their index."""
    folder = os.path.join(str(root), *FLAT.split("/"))
    tiles = {}
    for i, j in keys:
        path = os.path.join(folder, *src.grid_tile_name(i, j).split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_tile(path, np.full((200, 200), 300.0, np.float32), CRS,
                    from_origin(i * 200 + ORIGIN[0], (j + 1) * 200 + ORIGIN[1], 1.0, 1.0))
        tiles[f"{i}_{j}"] = _sha(path)
    _write_index(folder, tiles)


class Mirror:
    """The fixture mirror served at <http_server>/v1/tiles/ from its folder (read at each request, so a test may
    change the files): `status` answers every request with it, `once` a path's next request, `delay` holds each
    answer that many seconds, `fail` a path's next n requests ({path: n}, with 503). `asked(kind)` lists the paths
    asked: "index", "tile" or all."""

    def __init__(self, http_server, root):
        self.server, self.root = http_server, root
        self.status, self.once, self.delay, self.fail = None, {}, 0.0, {}
        self.gate = None  # a threading.Event the answers to index.json wait for (at most 10 s)
        self.statuses = {}  # path -> the status every request to it gets
        http_server.route("/v1/tiles/", self._answer)

    @property
    def url(self) -> str:
        return self.server.base

    def base(self, folder: str = MIRROR) -> str:
        return f"{self.server.base}/v1/tiles/{folder}"

    def _answer(self, request):
        if self.gate is not None and request.path.endswith("index.json"):
            assert self.gate.wait(10), "the threads never met"
        if self.delay:
            time.sleep(self.delay)
        if self.fail.get(request.path):
            self.fail[request.path] -= 1
            return Answer(503, b"down", {"Content-Type": "text/plain"})
        status = self.once.pop(request.path, None) or self.statuses.get(request.path) or self.status
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
    which --source auto takes when test_mirrored cannot be used; test_other (the clip too) of the country "yy", which
    a search would choose if the place's lookup answered "yy". Returns the mirrored source."""
    common = dict(countries=("zz",), crs=CRS, default_resolution=1.0, grid_origin=ORIGIN, fallback=None,
                  sample=CENTRE)
    mirrored = Source(id="test_mirrored", name="Test mirrored", description="test tiles of the data server",
                      nmt=mirrored_layer(), **common)
    plain = Source(id="test_plain", name="Test plain", description="the clip as a file",
                   nmt=FileLayer("Terrain file", CLIP), **common)
    other = Source(id="test_other", name="Test other", description="the clip as a file, of the country yy",
                   nmt=FileLayer("Terrain file", CLIP), **{**common, "countries": ("yy",)})
    for source in (mirrored, plain, other):
        monkeypatch.setitem(src.SOURCES, source.id, source)
    monkeypatch.setattr(pm, "SOURCE_CHOICES", pm.SOURCE_CHOICES + [mirrored.id, plain.id, other.id])  # named: valid
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
    """The local folder (when it holds the dataset), then the data server (MIRROR_URL, or FINDALINE_MIRROR_URL; "off"
    in any case, or empty, turns it off: U37), then the catalogue's URLs; with none of them the text names both
    settings and the word off. A value that is no http(s) address nor off is an error with a clear text, never the
    default and never off, refused at a search's start (choose_source, so plan_search's "no_source")."""
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
    monkeypatch.delenv("FINDALINE_MIRROR")
    alone = mirrored_layer()
    for off in ("off", "OFF", " Off ", ""):
        set_url(off)
        assert tilebases.mirror_url() is None and alone.bases() == [] and alone.remote_base() is None, off
    why = alone.unavailable()
    assert "set FINDALINE_MIRROR" in why and "FINDALINE_MIRROR_URL" in why and "data server" in why
    assert why.endswith("FINDALINE_MIRROR_URL, the project's data server, is off)")
    import search
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "zz")  # offline, whatever happens
    for wrong in ("mirror.findaline.lukawski.org", "ftp://example.org", "none", "http://"):
        set_url(wrong)
        with pytest.raises(tilebases.MirrorUrlError, match="must be an http:// or https:// address, or off"):
            alone.bases()
        with pytest.raises(ValueError, match="FINDALINE_MIRROR_URL is"):
            src.choose_source("auto", *CENTRE, str(tmp_path))
    paths = search.Paths(str(tmp_path / "data"), str(tmp_path / "data" / "work"))
    set_url("mirror.example.org")
    with pytest.raises(search.SearchError, match="FINDALINE_MIRROR_URL is 'mirror.example.org': it must be") as refused:
        search.plan_search(search.SearchParams(**POINT), paths, lambda kind, text: None)
    assert refused.value.code == "no_source"


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
    server is not paid once per thread. The server holds the index's answer until all eight threads have come to
    the base's lock (each has read which fetch it waits for by then), so none can come after the fetch ended."""
    class Meeting:
        """The base's lock, counting the threads that came to it; the eighth opens the server's gate."""

        def __init__(self, gate):
            self.lock, self.gate, self.came, self.counting = threading.Lock(), gate, 0, threading.Lock()

        def __enter__(self):
            with self.counting:
                self.came += 1
                if self.came == 8:
                    self.gate.set()
            return self.lock.__enter__()

        def __exit__(self, *exc):
            return self.lock.__exit__(*exc)

    def together(layer):
        reader, results = layer.readers[1.0], []
        mirror.gate = threading.Event()
        reader._kept_of(mirror.base()).lock = Meeting(mirror.gate)

        def ask():
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
    results = together(mirrored_layer())
    assert len(results) == 8 and all(isinstance(r, dict) and r for r in results)
    assert len(mirror.asked("index")) == 1
    mirror.status = 503
    results = together(mirrored_layer())
    assert len(results) == 8 and all(isinstance(r, RuntimeError) and "HTTP 503" in str(r) for r in results)
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
    """With the local folder holding the dataset its tiles come from there, each without a host slot (N1: the slot
    is taken for a host, and the folder has none); the start check asks nothing (the folder answers), however the
    data server is."""
    import contextlib
    import sources.layer as layer_module
    slots = []
    real = layer_module.host_slot

    @contextlib.contextmanager
    def counted(cache_dir, url):
        slots.append(url)
        with real(cache_dir, url):
            yield
    monkeypatch.setattr(layer_module, "host_slot", counted)
    monkeypatch.setenv("FINDALINE_MIRROR", make_mirror(tmp_path / "local"))
    mirror.status = 503
    layer = mirrored_layer()
    assert layer.reach() is None and layer.remote_base() is None
    _download(layer, tmp_path / "cache")
    assert len(slots) == 5 and not any(net._host(url) for url in slots), slots  # every tile: the folder, no host
    assert src.choose_source("auto", *CENTRE, str(tmp_path), reach=True)[0].id == "test_mirrored"
    assert mirror.asked() == []


def test_no_data_server(tmp_path, http_server, monkeypatch, two_sources):
    """FINDALINE_MIRROR_URL off and no folder: the source is unavailable as before, nothing is asked."""
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
    """The first phase chose the mirrored source over HTTP. After it the data server is down and the place's lookup
    answers another country ("yy": a phase choosing again would take test_other): the compute phase computes on the
    first phase's source from the cache ("chosen when the search started"). The search's hash is the same in both
    phases and equal to that of the same search with the mirror off (its tiles from a local folder, no start check,
    no stored source: the path of before). Then, in the same process (the quick lane's), a failed estimate's
    remembered failure never touches the finished run's profile and 3D patch, which work from the cache."""
    import jobs as jb
    import search
    data = tmp_path / "data"
    request = _request(radius=650)  # its grid holds every tile the 3D patch below needs (the run's cache)
    downloaded = []
    download = search.download_data
    monkeypatch.setattr(search, "download_data", lambda plan: (downloaded.append(plan), download(plan))[1])

    def between():
        mirror.status = 503
        monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "yy")
    row, plan, said = _phases(monkeypatch, data, request, between=between)
    assert downloaded[-1].source.id == plan.source.id == "test_mirrored"  # not test_other: never chosen again
    assert row["source"] == "test_mirrored" == _run_json(data, row)["source"]["id"]
    assert any(text.startswith("Data: Test mirrored (chosen when the search started) - ") for text in said), said
    assert search._search_key(plan)["params"]["source"] == "auto"
    hashes = {search._search_hash(downloaded[-1]), search._search_hash(plan)}
    assert len(hashes) == 1
    # The same search with the mirror off: the local folder, choose_source as before
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "zz")
    set_url("off")
    monkeypatch.setenv("FINDALINE_MIRROR", make_mirror(tmp_path / "local"))
    os.makedirs(tmp_path / "off" / "work")
    off = search.plan_search(jb.search_params(request), search.Paths(str(tmp_path / "off"), str(tmp_path / "off" / "work")),
                             lambda kind, text: None)
    assert off.source.id == "test_mirrored" and hashes == {search._search_hash(off)}
    monkeypatch.delenv("FINDALINE_MIRROR")
    set_url(mirror.url)

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


def test_down_in_the_middle(tmp_path, monkeypatch, mirror, offline, two_sources):
    """The data server answers the start check of a job's download phase, then fails a tile at every attempt: the
    phase fails with "Could not download" (U6's "in the middle"), the job is "failed" with that text, saying the data
    server does not answer by its host alone, the tile that came is cached; the search run again (a new job, as the
    page's "run again" makes one) asks the server for the missing tile only and completes on the same source."""
    import jobs as jb
    _in_process(monkeypatch)
    data = tmp_path / "data"
    os.makedirs(data)
    jobs = jb.Jobs(str(data))
    second = f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*DATA_TILES[1])}"
    mirror.fail[second] = net.RETRIES  # every attempt of net._get
    job = jobs.add(_request(), "first")
    jobs.claim("queued", "downloading", "w1")
    jb.run_phase(str(data), job, "download")
    row = jobs.get(job)
    assert row["status"] == "failed" and row["source"] == "test_mirrored"
    assert (f"Could not download Test DTM (mirrored) tile {src.grid_tile_name(*DATA_TILES[1])}: the data server at "
            f"127.0.0.1 does not answer (HTTP 503)") in row["error"], row["error"]
    cache_dir, layer = str(data / "cache"), two_sources.nmt
    assert [cache.state(cache_dir, layer.tile_path(cache_dir, (1.0, *t))) for t in DATA_TILES] == ["ok", None]
    assert not os.path.exists(layer.tile_path(cache_dir, (1.0, *DATA_TILES[1])))
    before = len(mirror.asked("tile"))
    row, plan, _ = _phases(monkeypatch, data, _request())
    assert row["source"] == plan.source.id == "test_mirrored" and mirror.asked("tile")[before:] == [second]


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
    its index lists with data; with --deep that tile downloaded whole and checked; a server that does not answer
    fails the index with the reason."""
    from sources import probe
    folder = str(tmp_path / "probe")
    os.makedirs(folder)
    row = probe.probe_layer(two_sources, two_sources.nmt, "terrain", str(tmp_path / "cache"), folder, False)
    assert (row.index, row.read) == (probe.OK, probe.OK), row.notes
    ranged = [r for r in mirror.server.requests("/v1/tiles/") if r.path.endswith(".tif")]
    assert [r.headers.get("range") for r in ranged] == ["bytes=0-0"]
    assert ranged[0].path.rsplit("/", 1)[1][:-4] in {f"{i}_{j}" for i, j in DATA_TILES}
    row = probe.probe_layer(two_sources, two_sources.nmt, "terrain", str(tmp_path / "cache"), folder, True)
    assert (row.index, row.read) == (probe.OK, probe.OK) and row.notes[0].endswith("% with data"), row.notes
    whole = [r for r in mirror.server.requests("/v1/tiles/") if r.path.endswith(".tif")][1:]
    assert [r.headers.get("range") for r in whole] == [None] and whole[0].path == ranged[0].path
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
    """The index's requests (and the tiles') take the host's rate turn (net.rate_turn through net._get). The index
    takes no host slot of its own: the start check takes none, and a download one per tile (the index is fetched
    inside the first tile's)."""
    import contextlib
    import sources.layer as layer_module
    turns, slots = [], []
    monkeypatch.setattr(net, "rate_turn", lambda url, share=1.0: turns.append(url))
    real = layer_module.host_slot

    @contextlib.contextmanager
    def counted(cache_dir, url):
        slots.append(url)
        with real(cache_dir, url):
            yield
    monkeypatch.setattr(layer_module, "host_slot", counted)
    monkeypatch.setattr(net, "host_slot", counted)
    layer = mirrored_layer()
    assert layer.reach() is None and turns == [f"{mirror.base()}/index.json"] and slots == []
    _download(layer, tmp_path / "cache")
    tiles = layer.tiles(gd.make_grid(WIDE, 1.0, CRS, ORIGIN))
    assert slots == [mirror.base()] * len(tiles)  # the tiles' host; never the index's own
    assert sum(u.endswith(".tif") for u in turns) == len(DATA_TILES) and sum(u.endswith("index.json") for u in turns) == 1
    assert layer.tile_url((1.0, *DATA_TILES[0])) == mirror.base()


def test_the_processes_of_the_tests_ask_no_data_server():
    """Guards tests/conftest.py's line: when pytest imported this module (before any test ran, so before this
    module's set_url), a process started then would have inherited FINDALINE_MIRROR_URL "off", never unset (the
    default address) nor what the calling shell had. Without conftest's line AT_COLLECTION is the shell's value
    (unset, or empty: Git Bash keeps it, PowerShell cannot set it), and this fails, unless the shell itself had "off".
    The child started below runs after this module's set_url("off"): that half guards set_url, not conftest."""
    import subprocess
    assert AT_COLLECTION == "off"
    code = "import os; print(repr(os.environ.get('FINDALINE_MIRROR_URL', 'unset')))"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "'off'"


def test_a_job_falls_back_when_the_server_does_not_answer(tmp_path, monkeypatch, offline, mirror, two_sources):
    """A web job's download phase is a first planning (reach=True): the data server answering 503 at its start, it
    falls back to the next source of the place, the reason in that phase's messages; the compute phase computes on
    that source although the server answers again by then (and asks it nothing)."""
    data = tmp_path / "data"
    mirror.status = 503
    row, plan, said = _phases(monkeypatch, data, _request(), between=lambda: setattr(mirror, "status", None))
    assert row["source"] == plan.source.id == _run_json(data, row)["source"]["id"] == "test_plain"
    reason = ("Data: Test plain (the centre is in ZZ, but Test DTM (mirrored): the data copy at 127.0.0.1 does not "
              "answer (HTTP 503)) - ")
    assert any(text.startswith(reason) for text in said), said
    assert mirror.asked() == [f"/v1/tiles/{MIRROR}/index.json"] * tilebases.REACH_ATTEMPTS  # the start check only


def test_no_request_with_the_url_empty(tmp_path, monkeypatch, offline, two_sources):
    """FINDALINE_MIRROR_URL off, or empty: no request at all to a data server, through a first planning (reach=True), an
    estimate and a download, the request functions themselves failing the test on any call: net._get on any call
    (these searches have no other remote data), requests' sessions on any URL of a data server (its host, or a
    /v1/tiles/ path; the run's place name still asks Nominatim, through the dead proxy): with no folder (the source
    falls back) and with a local folder giving the tiles."""
    import search

    def refuse(url, *args, **kwargs):
        pytest.fail(f"a request with the data server off: {url}")
    send = requests.Session.send

    def guarded(self, request, **kwargs):
        if tilebases.MIRROR_HOST in request.url or "/v1/tiles/" in request.url:
            refuse(request.url)
        return send(self, request, **kwargs)
    monkeypatch.setattr(net, "_get", refuse)
    monkeypatch.setattr(requests.Session, "send", guarded)  # requests.get goes through it too
    params = search.SearchParams(**_request()["params"])
    local = make_mirror(tmp_path / "local")
    for setting, folder, expected in (("off", None, "test_plain"), ("", None, "test_plain"),
                                      ("off", local, "test_mirrored"), ("", local, "test_mirrored")):
        set_url(setting)
        if folder:
            monkeypatch.setenv("FINDALINE_MIRROR", folder)
        name = f"{expected}-{setting or 'empty'}"
        paths = search.Paths(str(tmp_path / name), str(tmp_path / name / "work"))
        os.makedirs(paths.work)
        plan = search.plan_search(params, paths, lambda kind, text: None, reach=True)
        assert plan.source.id == expected and two_sources.nmt.reach() is None
        search.estimate_search(plan)
        search.download_data(plan)
    assert os.path.exists(two_sources.nmt.tile_path(paths.cache, (1.0, *DATA_TILES[0])))


def test_the_command_line_asks(monkeypatch, tmp_path):
    """The command line's search is a first planning: findaline.main plans with reach=True."""
    import findaline
    import search
    seen = []

    def plan_search(*args, **kwargs):
        seen.append(kwargs)
        raise search.SearchError("planned")
    monkeypatch.setattr(search, "plan_search", plan_search)
    with pytest.raises(SystemExit, match="planned"):
        findaline.main(pm.SearchParams(**POINT), pm.CliOptions(yes=True, no_plot=True),
                       search.Paths(str(tmp_path), str(tmp_path / "work")))
    assert seen == [{"reach": True}]


@pytest.mark.parametrize("shape", sorted(MALFORMED))
def test_a_malformed_index(tmp_path, mirror, http_server, two_sources, no_mirror_settings, shape):
    """An index the client cannot read is treated as a mismatch: at the start check the server "does not answer"
    with the reason (auto falls back); at a download it is an error naming the index and the server after one more
    try, with no file and no "missing" row, and the next base is asked."""
    with open(os.path.join(mirror.root, *MIRROR.split("/"), "index.json"), "wb") as f:
        f.write(MALFORMED[shape])
    source, why = src.choose_source("auto", *CENTRE, str(tmp_path), reach=True)
    assert source.id == "test_plain", why
    assert "Test DTM (mirrored): the data copy at 127.0.0.1 does not answer (its index is not readable: " in why
    before, cache_dir = len(mirror.asked("index")), str(tmp_path / "cache")
    tile = (1.0, *DATA_TILES[0])
    layer = mirrored_layer()
    with pytest.raises(RuntimeError, match=rf"{mirror.base()}/index.json cannot be read: .*also after taking the index"):
        layer._download_and_record(tile, cache_dir)
    path = layer.tile_path(cache_dir, tile)
    assert cache.state(cache_dir, path) is None and not os.path.exists(path)
    assert len(mirror.asked("index")) == before + 2 and no_mirror_settings == [tilebases.HEAL_PAUSE]
    http_server.add_folder("/second", make_mirror(tmp_path / "second"))
    assert mirrored_layer([http_server.url(f"/second/{MIRROR}")]).download_tile(tile, path).received > 0


def test_two_connections_whatever_address(tmp_path, http_server, monkeypatch):
    """The data server under another address than its own (a mirror on a LAN, the local test stack: here the test
    server) keeps its host's manners: never more than 2 tile requests at once from the 8 download threads, and the
    default host's rate; net's two entries stay those of the default host (net.LIMITS_AS maps the address)."""
    layer, grid = flat_layer(), gd.make_grid(FLAT_BOUNDS, 1.0, CRS, ORIGIN)
    keys = [t[1:] for t in layer.tiles(grid)]
    served = Mirror(http_server, str(tmp_path / "served"))
    make_flat(served.root, keys)
    set_url(http_server.base)
    served.delay = 0.1  # the answers overlap when the client lets them
    layer.download(grid, str(tmp_path / "cache"), None, "test")
    assert len(keys) == 6 and len(served.asked("tile")) == 6
    assert http_server.peak("/v1/tiles/", ".tif") == 2
    address = http_server.base.split("//", 1)[1]
    assert net.LIMITS_AS == {address: tilebases.MIRROR_HOST} == {address: "mirror.findaline.lukawski.org"}
    assert net.limits_host(f"{http_server.base}/v1/tiles/x") == tilebases.MIRROR_HOST
    assert "127.0.0.1" not in net.HOST_SLOTS_OF and net.HOST_SLOTS_OF[tilebases.MIRROR_HOST] == 2
    turns = []
    monkeypatch.setattr(net, "HOST_RATES_OF", {tilebases.MIRROR_HOST: 600})  # conftest empties it in this module
    monkeypatch.setattr(net, "_turn", lambda host, per_minute: turns.append((host, per_minute)))
    net.rate_turn(f"{http_server.base}/v1/tiles/x")
    assert turns == [("127.0.0.1", 600)]


def test_a_tile_falling_through_a_local_folder_takes_a_slot(tmp_path, http_server, monkeypatch):
    """A tile the local folder does not hold yet (its index "partial") comes from the data server under one of the
    server's 2 slots: TileBases.url names the base it comes from, not the folder."""
    layer, grid = flat_layer(), gd.make_grid(FLAT_BOUNDS, 1.0, CRS, ORIGIN)
    keys = [t[1:] for t in layer.tiles(grid)]
    served = Mirror(http_server, str(tmp_path / "served"))
    make_flat(served.root, keys)
    set_url(http_server.base)
    local = tmp_path / "local" / "test" / "flat" / "1m"
    local.mkdir(parents=True)
    _write_index(str(local), {}, partial=True)
    monkeypatch.setenv("FINDALINE_MIRROR", str(tmp_path / "local"))
    assert layer.bases()[0] == str(local) and layer.tile_url((1.0, *keys[0])) == served.base(FLAT)
    served.delay = 0.1
    layer.download(grid, str(tmp_path / "cache"), None, "test")
    assert len(served.asked("tile")) == 6 and http_server.peak("/v1/tiles/", ".tif") == 2


def test_a_busy_server_answers_at_once(tmp_path, mirror, monkeypatch, no_mirror_settings):
    """A 429 at the start check answers at once (U39): one request, no pause, no other attempt; a source whose two
    layers are both busy costs two requests in all. Every other caller of net._get keeps its attempts and pauses: a
    tile's 429 is asked RETRIES times with the long back-off (_sleep(attempt + 3)) between them."""
    mirror.status = 429
    layer = mirrored_layer()
    assert layer.reach() is None
    assert mirror.asked() == [f"/v1/tiles/{MIRROR}/index.json"] and no_mirror_settings == []
    two = Source(id="test_two", name="Test two layers", description="two layers of our own tiles", nmt=mirrored_layer(),
                 nmpt=mirrored_layer(), countries=("zz",), crs=CRS, default_resolution=1.0, grid_origin=ORIGIN)
    assert src.choose.source_unreachable(two) is None
    assert len(mirror.asked()) == 1 + 2 and no_mirror_settings == []
    with pytest.raises(RuntimeError) as busy:  # the default of net._get, unchanged
        net._get(f"{mirror.base()}/index.json", binary_types=("json",))
    assert busy.value.status == 429 and len(mirror.asked()) == 3 + net.RETRIES
    assert no_mirror_settings == [3, 4, 5]
    with pytest.raises(RuntimeError, match=r"the data server at 127.0.0.1 is busy \(HTTP 429\)"):
        mirrored_layer().download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif"))  # the downloads: as before


def test_the_mixed_case(tmp_path, mirror, monkeypatch, no_mirror_settings):
    """U38, as built: a local folder holding the 1 m tiles but not the averaged ones answers the start check without
    a request; a grid of the averaged resolution then reads it from the data server (C.5: the same values), and with
    the server down that download fails the phase ("does not answer"), never a fall-back to the 1 m tiles."""
    make_averaged(mirror.root)
    monkeypatch.setenv("FINDALINE_MIRROR", make_mirror(tmp_path / "local"))  # 1 m only
    layer = mirrored_layer(averaged=(2,))
    assert layer.reach() is None and mirror.asked() == []
    assert layer.resolution(2.0) == 2.0 and layer.readers[2.0].bases() == [mirror.base("test/dtm/2m")]
    _download(layer, tmp_path / "cache", res=2.0)
    assert mirror.asked("tile") and all("/test/dtm/2m/" in p for p in mirror.asked())
    mirror.status = 503
    down = mirrored_layer(averaged=(2,))
    assert down.reach() is None  # the folder answers for the layer
    with pytest.raises(RuntimeError, match=r"the data server at 127.0.0.1 does not answer \(HTTP 503\)"):
        _download(down, tmp_path / "other", res=2.0)


def test_a_3d_view_with_the_server_down(tmp_path, monkeypatch, offline, mirror, two_sources):
    """U40: a finished run's 3D patch that needs a tile not in the cache while the data server does not answer fails
    through the patch's error path with a text saying so, by the host's name alone (no address, no path); no
    fall-back."""
    import jobs as jb
    import messages
    import search
    data = tmp_path / "data"
    row, _, _ = _phases(monkeypatch, data, _request())  # radius 290: the patch's square reaches tiles not cached
    mirror.status = 503
    two_sources.nmt.readers[1.0]._kept.clear()  # the quick lane is another process: no index kept from the phases
    with pytest.raises(search.SearchError) as failed:
        jb.quick_patch(str(data), {"run": row["run_id"], "line": LINE})
    detail = messages.user_error(failed.value).detail()
    assert detail["code"] == "download_failed", detail
    assert "the data server at 127.0.0.1 does not answer (HTTP 503)" in detail["message"], detail
    assert "/v1/tiles" not in str(detail) and "http" not in str(detail), detail


def test_the_tools_indexes_pass_the_check(tmp_path, monkeypatch):
    """N2: one rule for an index's "block" on both sides. The indexes tools/sk_tiles.py writes (cut, then average)
    and tools/mirror_tiles.py writes (cut) all say block 10 and pass the client's check (_checked_index), their
    tiles and extent as a local folder reads them."""
    import test_sources
    import test_mirror_tiles as tmt
    import sk_tiles
    import mirror_tiles as mt
    (tmp_path / "sk").mkdir()
    mirror, root, _, _, _ = test_sources._cut(tmp_path / "sk", monkeypatch)
    sk_tiles.average("test", str(mirror / "slovakia"), (2,))
    tmt._spec(monkeypatch, "asc", url="https://example.org/dl/test.zip", member="T.ASC")
    work, out = tmp_path / "mt" / "work", tmp_path / "mt" / "mirror"
    tmt._zip(work, "T.ASC", tmt._asc_text(tmt._asc_values()), "test.zip")
    mt.extract("asc", str(work))
    mt.cut("asc", str(work), str(out))
    paths = [root / "index.json", root.parent / "2m" / "index.json", out / "aosta" / "dtm" / "2m" / "index.json"]
    for path in paths:
        index = json.loads(path.read_text(encoding="utf-8"))
        assert index["block"] == tilebases.BLOCK == 10, path
        tiles, extent = tilebases._checked_index(index)
        assert tiles == index["tiles"] and any(tiles.values()) and extent is not None, path


def test_an_address_with_a_user_or_password(tmp_path, mirror, monkeypatch, two_sources, capsys):
    """R1: an address with a user or a password is refused (the data server is anonymous, U1), and no text, cache
    row or file holds the password: the refusal masks what stands before the "@", also of a mistyped value."""
    import search
    from sources import probe
    port = mirror.url.rsplit(":", 1)[1]
    set_url(f"http://user:secret@127.0.0.1:{port}")
    layer = mirrored_layer()
    with pytest.raises(tilebases.MirrorUrlError) as refused:
        layer.bases()
    assert "secret" not in str(refused.value) and "'http://***@127.0.0.1:" in str(refused.value)
    assert "a user or a password is not supported" in str(refused.value)
    with pytest.raises(ValueError) as chosen:
        src.choose_source("auto", *CENTRE, str(tmp_path))
    paths = search.Paths(str(tmp_path / "data"), str(tmp_path / "data" / "work"))
    with pytest.raises(search.SearchError) as planned:
        search.plan_search(search.SearchParams(**_request()["params"]), paths, lambda kind, text: None, reach=True)
    with pytest.raises(tilebases.MirrorUrlError) as downloaded:
        _download(layer, tmp_path / "cache")
    assert probe.run(str(tmp_path / "probe"), ["test_mirrored"]) == 1
    texts = [str(chosen.value), str(planned.value), str(downloaded.value), capsys.readouterr().err]
    assert all("***@" in text and "secret" not in text for text in texts), texts
    assert mirror.asked() == [] and net.LIMITS_AS == {}
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert not any(b"secret" in p.read_bytes() for p in written)
    for wrong, shown in (("htps://user:secret@host", "'htps://***@host'"), ("user:secret@host", "'***@host'")):
        set_url(wrong)
        with pytest.raises(tilebases.MirrorUrlError, match="must be an http") as refused:
            tilebases.mirror_url()
        assert shown in str(refused.value) and "secret" not in str(refused.value)


def test_addresses_at_the_edges(tmp_path, mirror):
    """R5: a value with no host is refused like any other wrong value; the scheme in any case is an address."""
    for wrong in ("https://?x", "https:///path", "http://", "https:// host"):
        set_url(wrong)
        with pytest.raises(tilebases.MirrorUrlError, match="must be an http:// or https:// address"):
            tilebases.mirror_url()
    set_url(mirror.url.replace("http://", "HTTP://"))
    assert tilebases.mirror_url() == mirror.url
    assert mirrored_layer().download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif")).received > 0


def test_a_tiles_429_keeps_its_attempts(tmp_path, mirror, no_mirror_settings):
    """R2: only the start check stops at the first 429; a tile's 429 keeps net._get's three attempts and the longer
    back-off between them (_sleep(attempt + 3)), as every download did before."""
    name = f"/v1/tiles/{MIRROR}/{src.grid_tile_name(*DATA_TILES[0])}"
    mirror.statuses[name] = 429
    with pytest.raises(RuntimeError, match=r"the data server at 127.0.0.1 is busy \(HTTP 429\)"):
        mirrored_layer().download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif"))
    assert mirror.asked() == [f"/v1/tiles/{MIRROR}/index.json"] + [name] * net.RETRIES
    assert no_mirror_settings == [3, 4, 5]
    mirror.statuses[f"/v1/tiles/{MIRROR}/index.json"] = 429
    assert mirrored_layer().reach() is None and mirror.asked()[-1].endswith("index.json")
    assert len(mirror.asked()) == 1 + net.RETRIES + 1 and no_mirror_settings == [3, 4, 5]


def _broken(kind):
    """The error requests.get raises for a kind of failure (the text holds the URL, as requests' own do)."""
    from urllib3.exceptions import ProtocolError
    text = "HTTPConnectionPool(host='127.0.0.1'): Max retries exceeded with url: /v1/tiles/secret/path"
    return {"refused": requests.ConnectionError(text), "timeout": requests.ReadTimeout(text),
            "certificate": requests.exceptions.SSLError(text),
            "broken": requests.ConnectionError(ProtocolError("Connection aborted.", ConnectionResetError())),
            "cut short": requests.exceptions.ChunkedEncodingError(text)}[kind]


@pytest.mark.parametrize("kind, words", [("refused", "no answer"), ("timeout", "no answer in time"),
                                         ("certificate", "its certificate was refused"),
                                         ("broken", "the connection broke"), ("cut short", "the connection broke"),
                                         ("turn", "waited too long for its turn"),
                                         ("not data", "its answer was not the data")])
def test_the_kind_of_failure(tmp_path, mirror, monkeypatch, kind, words):
    """R3: a download from the server that fails says which kind of failure in a few fixed words, by the host's
    name: never a path, a query or the library's text."""
    if kind == "turn":
        def no_turn(url, share=1.0):
            raise net.TurnTimeout("127.0.0.1 is busy with the requests of other searches (waited 10 min); try again")
        monkeypatch.setattr(net, "rate_turn", no_turn)
    elif kind == "not data":
        mirror.statuses = {}
        http_text = b"<html>a login page</html>"
        mirror.server.route("/v1/tiles/", lambda request: Answer(200, http_text, {"Content-Type": "text/html"}))
        mirror.server.routes.reverse()  # before the mirror's own route
    else:
        def broken(url, **kwargs):
            raise _broken(kind)
        monkeypatch.setattr(requests, "get", broken)
    with pytest.raises(RuntimeError) as failed:
        mirrored_layer().download_tile((1.0, *DATA_TILES[0]), str(tmp_path / "t.tif"))
    text = str(failed.value)
    assert text.endswith(f"the data server at 127.0.0.1 does not answer ({words})"), text
    assert "/v1/tiles" not in text and "http" not in text.lower() and "Pool" not in text and "login" not in text


def test_a_wrong_setting_ends_with_its_text(tmp_path, two_sources, capsys):
    """R4: with a FINDALINE_MIRROR_URL that is neither an address nor off, `sources check` and a country run end
    with the clear text and a non-zero exit, as a search does, never a traceback."""
    import country
    from sources import probe
    set_url("mirror.example.org")
    assert probe.run(str(tmp_path / "probe"), ["test_mirrored"]) == 1
    assert capsys.readouterr().err.strip() == ("FINDALINE_MIRROR_URL is 'mirror.example.org': it must be an http:// "
                                               "or https:// address, or off (or empty) for no data server")
    lat, lon = CENTRE
    area = tmp_path / "area.geojson"
    d = 0.001
    area.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[
        [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]]}}))
    config = {"id": "zz", "name": "Testland", "source": "test_mirrored", "area": str(area),
              "bands": [{"name": "S", "lengths": [30, 150], "resolution": 1.0, "model": "formula",
                         "slope_threshold": 45, "core_m": 200, "layer": True}],
              "options": {"nmpt": "off", "water": "off", "fill_gaps": "off"}}
    (tmp_path / "data" / "countries" / "zz").mkdir(parents=True)
    (tmp_path / "data" / "countries" / "zz" / "country.json").write_text(json.dumps({"config": config}))
    assert country.run("zz", str(tmp_path / "data"), processes=0, yes=True) == 1
    out = capsys.readouterr()
    assert "FINDALINE_MIRROR_URL is 'mirror.example.org': it must be" in out.out + out.err
    assert "Traceback" not in out.out + out.err

