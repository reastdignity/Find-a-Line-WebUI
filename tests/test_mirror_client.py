"""The client of the project's data server (docs/mirror-hosting/spec.md, solution C): our own tiles read over HTTP
by the rules of a local mirror folder, the start check (`reach`) asked only by the first planning of a search, and
the later phases of a job on the source its first phase chose.

The tests use a fixture mirror made from tests/data/zabi_kon_nmt.tif (2 km tiles on its pixel edges, as
tools/mirror_tiles.py lays them out) and two test sources of a made-up country "zz": one reading the mirror, one
reading the file itself, its fall-back. No test asks the real data server: FINDALINE_MIRROR_URL is empty or a
local server (tests/http_server.py)."""

import gc
import hashlib
import json
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sources as src  # noqa: E402
from sources.layer import _write_tile  # noqa: E402
from sources.layers.files import FileLayer  # noqa: E402
from sources.source import Source  # noqa: E402

DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")  # EPSG:2180, 1 m, pixel edges on half metres, 600 x 600 m
POINT = {"northing": 254608, "easting": 553966, "radius": 290}
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1"}
CRS, TILE_M, ORIGIN = "EPSG:2180", 2000, (0.5, 0.5)
MIRROR = "test/dtm/1m"  # the dataset's folder below the mirror (and below <url>/v1/tiles/)
# The index's extent: the clip lies in tiles (276, 127) and (277, 127); the others are null (outside the data)
EXTENT = (275, 126, 278, 128)


@pytest.fixture(autouse=True)
def no_mirror_settings(monkeypatch):
    """No mirror folder of this PC's (the user-level FINDALINE_MIRROR) and no data server unless a test sets one."""
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    monkeypatch.setenv("FINDALINE_MIRROR_URL", "")


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
                with open(path, "rb") as f:
                    tiles[f"{i}_{j}"] = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"tiles": tiles}, f)
    return str(root)


def mirrored_layer(urls=()):
    return src.GridTiles("Test DTM (mirrored)", list(urls), CRS, "test/mirrored/epsg2180-1m-2km", TILE_M, 1.0, 2e6,
                         mirror=MIRROR, origin=ORIGIN, tool="tests/test_mirror_client.py")


@pytest.fixture
def two_sources(monkeypatch):
    """The test sources of the country "zz": test_mirrored (our own tiles) before test_plain (the clip as a file),
    which --source auto takes when test_mirrored cannot be used. Returns the mirrored source."""
    common = dict(countries=("zz",), crs=CRS, default_resolution=1.0, grid_origin=ORIGIN, fallback=None)
    mirrored = Source(id="test_mirrored", name="Test mirrored", description="test tiles of the data server",
                      nmt=mirrored_layer(), **common)
    plain = Source(id="test_plain", name="Test plain", description="the clip as a file",
                   nmt=FileLayer("Terrain file", CLIP), **common)
    monkeypatch.setitem(src.SOURCES, mirrored.id, mirrored)
    monkeypatch.setitem(src.SOURCES, plain.id, plain)
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "zz")
    return mirrored


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
    is kept (search.search_lines spied). Returns (the job's row, the compute phase's plan)."""
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
    gc.collect()
    return row, planned[-1]


@pytest.mark.xfail(strict=True, reason="the later phase chooses its source again (solution C not built yet)")
def test_a_job_that_fell_back_computes_on_the_fallback(tmp_path, monkeypatch, offline, two_sources):
    """A job whose first phase fell back (its mirror could not be used then) computes on the fall-back's source
    although the mirror is back by the later phase: the later phase never chooses again. The search's params keep
    the source as the user gave it ("auto"), so its hash and run.json's params are as given, and run.json's source
    is the one the first phase stored."""
    import search
    mirror = make_mirror(tmp_path / "mirror")
    data = tmp_path / "data"
    row, plan = _phases(monkeypatch, data, _request(),
                        between=lambda: monkeypatch.setenv("FINDALINE_MIRROR", mirror))  # the mirror is back
    assert row["source"] == "test_plain"  # stored by the download phase: the fall-back
    meta = _run_json(data, row)
    assert meta["source"]["id"] == "test_plain" == plan.source.id
    assert meta["params"]["source"] == "auto" == plan.params.source
    key = search._search_key(plan)
    assert key["params"]["source"] == "auto" and key["source"] == "test_plain"
