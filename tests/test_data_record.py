"""A run's record of the data it read (`identity`: run.json's data entries, its area and its top level; the
checksums from the cache's index), offline: the merge of a layer's entries, the one exit that drops the key, the
coastline's and the area's inputs, local files, a resumed tiled search."""

import glob
import json
import os
import shutil

import numpy as np
import pytest
import rasterio as rio

import cache
import osm
import runs as rn
import search
import sources as src
from grid import make_grid

A, B, C = "a" * 64, "b" * 64, "c" * 64
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _walk(value, path=()):
    """Every (path, key) of the dicts in a JSON value."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield path, k
            yield from _walk(v, path + (k,))
    elif isinstance(value, list):
        for k, v in enumerate(value):
            yield from _walk(v, path + (k,))


def _identities(value) -> list:
    return [path for path, key in _walk(value) if key == rn.IDENTITY]


def _theme_tiles(cache_dir, theme, box, features):
    """Theme tiles of a WGS84 box with the features (GeoJSON dicts, put into every tile) and their index rows (as
    osm.fetch_tile records them, with their checksums)."""
    cache.check_layout(cache_dir)
    paths = []
    for lat, lon in osm.tiles(*box):
        path = osm.theme_path(cache_dir, theme, lat, lon)
        osm.write_tile(path, features)
        paths.append(path)
    cache.record_many(cache_dir, paths, url="https://overpass.example/api")
    return sorted(cache.relative(cache_dir, p) for p in paths)


def _merged(entries, monkeypatch):
    monkeypatch.setattr(src.mosaic, "used_data", entries)
    monkeypatch.setattr(src, "used_data", entries)
    return search._merged_data()


def test_merging_keeps_the_checksums_in_step(monkeypatch):
    """search._merged_data unites the paths of a layer's entries and keeps `identity.sha256` parallel to them: a
    path met with two different checksums gets null, also when a third entry knows one of them; a checksum one
    entry knows and the other does not (null) is kept; an entry of before without `identity` counts as not
    known; entries without paths and without `identity` merge as before."""
    first = {"layer": "T", "folder": "f", "files": 2, "paths": ["f/1", "f/2"], "identity": {"sha256": [A, None]}}
    second = {"layer": "T", "folder": "f", "files": 2, "paths": ["f/2", "f/3"], "identity": {"sha256": [B, C]}}
    third = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/3"], "identity": {"sha256": [A]}}
    again = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/3"], "identity": {"sha256": [C]}}
    (merged,) = _merged([first, second], monkeypatch)
    assert merged["paths"] == ["f/1", "f/2", "f/3"] and merged["files"] == 3
    assert merged["identity"] == {"sha256": [A, B, C]}
    (merged,) = _merged([first, second, third, again], monkeypatch)
    assert merged["identity"] == {"sha256": [A, B, None]}  # f/3 met with C and A: changed in the run
    old = {"layer": "T", "folder": "f", "files": 1, "paths": ["f/0"]}
    (merged,) = _merged([old, second], monkeypatch)
    assert merged["paths"] == ["f/0", "f/2", "f/3"] and merged["identity"] == {"sha256": [None, B, C]}
    plain = [{"layer": "T", "folder": "f", "files": 1, "paths": ["f/0"]},
             {"layer": "T", "folder": "f", "files": 1, "paths": ["f/1"]}]
    assert _merged(plain, monkeypatch) == [{"layer": "T", "folder": "f", "files": 2, "paths": ["f/0", "f/1"]}]
    coast = {"layer": "OSM", "credit": {"data": "OSM"}, "identity": {"edition": "2026-10-23"}}
    assert _merged([coast, dict(coast)], monkeypatch) == [coast]
    assert first["identity"] == {"sha256": [A, None]}  # the record itself is never changed


def test_without_identity_drops_the_key_at_any_depth():
    """runs.without_identity: every key named `identity`, at any depth, and nothing else; the order of the other
    keys kept; public_meta and _listed go through it."""
    meta = {"id": "r", "area": {"type": "polygon", "geometry": {"type": "Point", "coordinates": [14.2, 36.0]}, "identity": {"paths": []}},
            "data": [{"layer": "L", "paths": ["a"], "identity": {"sha256": [A]}}, {"layer": "F", "file": "/x/f.tif",
                                                                                    "identity": {"size": 1}}],
            "params": {"slope_file": None, "area": None}, "store": {"lines": 1},
            "nested": [[{"identity": 1, "keep": {"identity": 2, "x": 3}}]], "identity": {"v": 1}}
    stripped = rn.without_identity(meta)
    assert not _identities(stripped) and _identities(meta)  # the record itself is never changed
    assert list(stripped) == [k for k in meta if k != "identity"] and stripped["nested"] == [[{"keep": {"x": 3}}]]
    assert stripped["data"] == [{"layer": "L", "paths": ["a"]}, {"layer": "F", "file": "/x/f.tif"}]
    assert not _identities(rn.public_meta(meta)) and not _identities(rn._listed({**meta, "center": {}}))
    assert rn.public_meta(meta)["data"] == [{"layer": "L"}, {"layer": "F", "file": "f.tif"}]
    assert rn.without_identity([1, "identity", None]) == [1, "identity", None]


def test_local_file_identity(tmp_path):
    """A local file's record (--elevation-file, --surface-file, --slope-file): its size and modification time,
    UTC to the second as run.json's `created` is written; None for a file that cannot be read."""
    path = tmp_path / "f.tif"
    path.write_bytes(b"x" * 123)
    os.utime(path, (1_790_000_000.7, 1_790_000_000.7))
    assert cache.file_identity(str(path)) == {"size": 123, "modified": "2026-09-21T14:13:20+00:00"}
    assert cache.file_identity(str(tmp_path / "gone.tif")) is None
    layer = src.FileLayer("Terrain", os.path.join(DATA, "zabi_kon_nmt.tif"))
    used = layer.used(None, str(tmp_path))
    assert list(used) == ["layer", "file", "identity"]
    assert used["identity"] == cache.file_identity(os.path.join(DATA, "zabi_kon_nmt.tif"))


def test_top_level_identity(tmp_path):
    """run.json's top-level `identity`: the record's version and the running GDAL, PROJ (GDAL's) and rasterio
    versions; the slope file's size and time with --slope-file; "mixed" only when the run says so."""
    from types import SimpleNamespace
    slope = tmp_path / "slope.tif"
    slope.write_bytes(b"s" * 7)
    plan = SimpleNamespace(params=SimpleNamespace(slope_file=None))
    versions = {"v": 1, "gdal": rio.__gdal_version__, "proj": rio.__proj_version__, "rasterio": rio.__version__}
    assert search._run_identity(plan, {}) == versions and all(isinstance(v, str) for v in list(versions.values())[1:])
    plan.params.slope_file = str(slope)
    assert search._run_identity(plan, {"mixed": True}) == {**versions, "slope_file": cache.file_identity(str(slope)),
                                                            "mixed": True}
    plan.params.slope_file = str(tmp_path / "gone.tif")
    assert search._run_identity(plan, {"mixed": False}) == versions


def test_coastline_identity(tmp_path, monkeypatch):
    """The coastline's record: the world file's edition (its folder's name); the OSM coastline tiles of the grid's
    box (with coast.MARGIN_DEG) with their stored checksums, exactly the tiles the sea mask read (an offline sea
    mask on a canned cache of coastline tiles and their index rows); nothing for the Copernicus mask or no sea."""
    import coast
    from shapely.geometry import LineString, mapping
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((500000, 300000, 502000, 302000), 10.0, "EPSG:2180")
    west, south, east, north = coast._grid_bbox_wgs84(grid)
    middle = (west + east) / 2
    line = {"type": "Feature", "properties": {"id": "w1", "natural": "coastline"},
            "geometry": mapping(LineString([(middle, south - 0.1), (middle, north + 0.1)]))}
    written = _theme_tiles(cache_dir, "coastline", (west - 0.3, south - 0.3, east + 0.3, north + 0.3), [line])
    read = []
    path_of = osm.theme_path
    monkeypatch.setattr(osm, "theme_path", lambda *args: read.append(path_of(*args)) or read[-1])
    monkeypatch.setattr(osm, "fetch_tile", lambda *args: pytest.fail("a tile was asked"))
    copernicus = np.zeros((grid.height, grid.width), bool)
    copernicus[:, :80] = True
    sea, source, warning = coast.sea_mask(grid, cache_dir, "overpass", copernicus)
    assert source == coast.SOURCE_OVERPASS and warning is None and sea.any() and not sea.all()
    monkeypatch.setattr(osm, "theme_path", path_of)
    identity = coast.identity(grid, cache_dir, source)
    assert identity["paths"] == sorted({cache.relative(cache_dir, p) for p in read}) and set(identity["paths"]) < \
        set(written)
    assert identity["sha256"] == [cache.info(cache_dir, os.path.join(cache_dir, p))["sha256"] for p in identity["paths"]]
    assert all(len(s) == 64 for s in identity["sha256"])
    assert all(p.startswith("osm/themes/coastline/") for p in identity["paths"])
    for source in (coast.SOURCE_FALLBACK, coast.SOURCE_COPERNICUS, coast.SOURCE_NO_SEA, coast.SOURCE_NO_COAST):
        assert coast.identity(grid, cache_dir, source) is None
    assert coast.identity(grid, cache_dir, coast.SOURCE_WORLD) is None  # no world file
    folder = os.path.join(cache_dir, "osm", "water-polygons", "2026-10-23", "water-polygons-split-4326")
    os.makedirs(folder)
    open(os.path.join(folder, "water_polygons.shp"), "wb").close()
    assert coast.identity(grid, cache_dir, coast.SOURCE_WORLD) == {"edition": "2026-10-23"}


def _nominatim(monkeypatch, outlines):
    """osm._ask answering searches by name with their outlines (WGS84 boxes); returns the names asked."""
    asked = []

    def ask(url, params, timeout, cache_dir):
        asked.append(params.get("q"))
        box = outlines.get(params.get("q"))
        if box is None:
            return []
        w, s, e, n = box
        return [{"geojson": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}]
    monkeypatch.setattr(osm, "_ask", ask)
    return asked


def test_area_identity(tmp_path, monkeypatch):
    """An area built from OSM carries what it was built from in run.json's `area` block: the theme tiles osm.theme
    read (sorted, with their stored checksums) and each stored Nominatim answer used ({"table", "query", "sha256"
    of the stored answer's text}, sorted by table and query); a circle, a file and a drawn area without an OSM name
    get none; each area object its own (one built on another cache carries that cache's record)."""
    import area as ar
    cache_dir = str(tmp_path / "cache")
    island = (14.20, 36.00, 14.30, 36.05)
    _nominatim(monkeypatch, {"Isle": island, "Bay": (14.22, 36.01, 14.24, 36.02)})
    coast_line = {"type": "Feature", "properties": {"id": "w1", "natural": "coastline"},
                  "geometry": {"type": "LineString", "coordinates": [[14.19, 36.0], [14.25, 36.06], [14.31, 36.0]]}}
    tiles = _theme_tiles(cache_dir, "coastline", (13.9, 35.7, 14.6, 36.4), [coast_line])
    read = []
    path_of = osm.theme_path
    monkeypatch.setattr(osm, "theme_path", lambda *args: read.append(path_of(*args)) or read[-1])
    monkeypatch.setattr(osm, "fetch_tile", lambda *args: pytest.fail("a tile was asked"))
    area = ar.from_spec("coast", 50.0, "osm:Isle", cache_dir, 300.0)
    monkeypatch.setattr(osm, "theme_path", path_of)
    described = area.describe()
    assert list(described) == ["type", "spec", "geometry", "identity"]
    identity = described["identity"]
    assert list(identity) == ["paths", "sha256", "nominatim"]
    assert identity["paths"] == sorted({cache.relative(cache_dir, p) for p in read}) and set(identity["paths"]) <= \
        set(tiles)
    assert identity["sha256"] == [cache.info(cache_dir, os.path.join(cache_dir, p))["sha256"] for p in identity["paths"]]
    import sqlite3
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    stored = db.execute("SELECT answer FROM search WHERE query = 'Isle'").fetchone()[0]
    db.close()
    import hashlib
    isle = {"table": "search", "query": "Isle", "sha256": hashlib.sha256(stored.encode("utf-8")).hexdigest()}
    assert identity["nominatim"] == [isle]
    # a box as --within: the tiles of the box, no answer
    boxed = ar.from_spec("coast", 50.0, "36.0,14.2,36.05,14.3", cache_dir).describe()["identity"]
    assert boxed["paths"] == osm.theme_files(cache_dir, "coastline", 14.2, 36.0, 14.3, 36.05) and \
        boxed["nominatim"] == []
    # a name, clipped by another name: two answers in order, no tiles
    named = ar.from_spec("osm:Isle", 0.0, "osm:Bay", cache_dir).describe()["identity"]
    assert named["paths"] == named["sha256"] == [] and [a["query"] for a in named["nominatim"]] == ["Bay", "Isle"]
    # a drawn area within a name: its answer; drawn alone, a file and a circle: none
    drawn = {"type": "Polygon", "coordinates": [[[14.22, 36.01], [14.23, 36.01], [14.23, 36.015], [14.22, 36.01]]]}
    assert ar.from_geometry(drawn, 0.0, "osm:Isle", cache_dir).describe()["identity"]["nominatim"] == [isle]
    assert "identity" not in ar.from_geometry(drawn, 0.0, None, cache_dir).describe()
    path = tmp_path / "area.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": drawn}))
    assert "identity" not in ar.from_spec(str(path), 0.0, None, cache_dir).describe()
    assert "identity" not in ar.Circle(36.0, 14.2, 100.0).describe()
    # another cache, the same name: that cache's own answer; the first area keeps its own
    other = str(tmp_path / "other")
    _nominatim(monkeypatch, {"Isle": (14.20, 36.00, 14.30, 36.06)})
    elsewhere = ar.from_spec("osm:Isle", 0.0, None, other).describe()["identity"]["nominatim"]
    assert elsewhere[0]["sha256"] != isle["sha256"] and area.describe()["identity"]["nominatim"] == [isle]
    assert osm.stored_answer(cache_dir, "search", "Nowhere") == {"table": "search", "query": "Nowhere",
                                                                  "sha256": None}


def test_record_differs():
    """Two sessions' records differ (C6's mark) when an entry is in one only, an entry's files differ, a file both
    name has two known checksums, or the coastline's edition or tiles or a local file's size or time differ; a
    checksum not known (null) never marks, nor does a record of before without files or `identity`."""
    layer = {"layer": "T", "folder": "f", "files": 2, "paths": ["f/1", "f/2"], "identity": {"sha256": [A, B]}}
    world = {"layer": "OSM world", "identity": {"edition": "2026-10-23"}}
    tiles = {"layer": "OSM tiles", "identity": {"paths": ["osm/t/1"], "sha256": [A]}}
    local = {"layer": "F", "file": "/x/f.tif", "identity": {"size": 5, "modified": "2026-11-24T10:00:00+00:00"}}
    record = [layer, world, tiles, local]
    differs = search._record_differs
    assert not differs(record, json.loads(json.dumps(record)))
    assert differs(record, [{**layer, "identity": {"sha256": [A, C]}}, world, tiles, local])
    assert not differs(record, [{**layer, "identity": {"sha256": [None, B]}}, world, tiles, local])
    assert not differs([{**layer, "identity": {"sha256": [None, None]}}], [layer])
    assert differs(record, [{**layer, "paths": ["f/1", "f/3"]}, world, tiles, local])
    assert differs(record, [layer, {**world, "identity": {"edition": "2026-11-01"}}, tiles, local])
    assert differs(record, [layer, world, {**tiles, "identity": {"paths": ["osm/t/1"], "sha256": [B]}}, local])
    assert differs(record, [layer, world, {**tiles, "identity": {"paths": ["osm/t/2"], "sha256": [A]}}, local])
    assert not differs(record, [layer, world, {**tiles, "identity": {"paths": ["osm/t/1"], "sha256": [None]}}, local])
    assert differs(record, [layer, world, tiles, {**local, "identity": {"size": 6, "modified": local["identity"]
                                                                          ["modified"]}}])
    assert not differs(record, [layer, world, tiles, {"layer": "F", "file": "/x/f.tif"}])
    assert differs(record, [layer, tiles, local])  # the world file, then the Copernicus mask
    assert not differs([{"layer": "stale"}], record)  # nothing known of before
    old = [{k: v for k, v in e.items() if k != "identity"} for e in record]  # a list of before: paths, no checksums
    assert not differs(old, record) and differs(old, [{**layer, "paths": ["f/1"]}, world, tiles, local])


def _resume(tmp_path, monkeypatch):
    """The tests' tiled clip search (test_offline's) on a copy of its elevation file, and its first session stopped
    with every tile done (not saved): (params, the run's folder, the copy)."""
    from test_offline import _resume_scene, _tiled_search
    params = _resume_scene(tmp_path, monkeypatch, "clip")
    copy = tmp_path / "nmt.tif"
    shutil.copy(params.elevation_file, copy)
    params = params.model_copy(update={"elevation_file": str(copy)})
    folder = _tiled_search(params, tmp_path / "data", save=False)
    return params, folder, copy


def _again(params, tmp_path, folder, tile: bool, save: bool):
    """Resume the search, with its last tile removed first (tile: one tile left) or not."""
    from test_offline import _tiled_search
    if tile:
        os.remove(sorted(glob.glob(os.path.join(folder, "tiles", search.TILE_FILE.format("*"))))[-1])
    return _tiled_search(params, tmp_path / "data", save=save)


def _kept(folder):
    with open(os.path.join(folder, search.USED_FILE), encoding="utf-8") as f:
        return json.load(f)


def test_resumed_on_the_same_data(tmp_path, monkeypatch):
    """A tiled search resumed with a tile left on unchanged data: its state file is {"data", "mixed": false} with the
    record's `identity` (the elevation file's size and time), and its run.json has no mark."""
    params, folder, copy = _resume(tmp_path, monkeypatch)
    kept = _kept(folder)
    assert list(kept) == ["data", "mixed"] and kept["mixed"] is False
    assert kept["data"][0]["identity"] == cache.file_identity(str(copy))
    run = _again(params, tmp_path, folder, tile=True, save=True)
    meta = json.load(open(os.path.join(run, "run.json"), encoding="utf-8"))
    assert "mixed" not in meta["identity"] and meta["data"][0]["identity"] == cache.file_identity(str(copy))


def test_resumed_on_other_data_is_marked(tmp_path, monkeypatch):
    """A tiled search resumed with a tile left after the data it read changed (the elevation file's time) is
    marked "mixed" in run.json's identity; the mark stays through every later session, with tiles left and without;
    a resume with no tile left takes the stored record and makes no mark of its own."""
    params, folder, copy = _resume(tmp_path, monkeypatch)
    os.utime(copy, (os.stat(copy).st_atime, os.stat(copy).st_mtime + 3600))
    _again(params, tmp_path, folder, tile=True, save=False)
    assert _kept(folder)["mixed"] is True
    _again(params, tmp_path, folder, tile=True, save=False)  # the same data as the session before: still marked
    assert _kept(folder)["mixed"] is True
    run = _again(params, tmp_path, folder, tile=False, save=True)
    meta = json.load(open(os.path.join(run, "run.json"), encoding="utf-8"))
    assert meta["identity"]["mixed"] is True


def test_resumed_with_no_tile_left_makes_no_mark(tmp_path, monkeypatch):
    """Resumed with no tile left after the data changed: the stored record, no mark (no step 1 read anything); a
    state file of before (a list) is read as its entries, not marked."""
    params, folder, copy = _resume(tmp_path, monkeypatch)
    before = _kept(folder)["data"]
    os.utime(copy, (os.stat(copy).st_atime, os.stat(copy).st_mtime + 3600))
    run = _again(params, tmp_path, folder, tile=False, save=True)
    meta = json.load(open(os.path.join(run, "run.json"), encoding="utf-8"))
    assert "mixed" not in meta["identity"] and meta["data"][0]["identity"] == before[0]["identity"]
    (tmp_path / "list").mkdir()
    params, folder, copy = _resume(tmp_path / "list", monkeypatch)
    old = rn.without_identity(_kept(folder)["data"])  # as a run begun before wrote it: a list, no record
    with open(os.path.join(folder, search.USED_FILE), "w", encoding="utf-8") as f:
        json.dump(old, f)
    assert search._read_used(os.path.join(folder, search.USED_FILE))[1] is False
    os.utime(copy, (os.stat(copy).st_atime, os.stat(copy).st_mtime + 3600))
    run = _again(params, tmp_path / "list", folder, tile=True, save=True)
    assert "mixed" not in json.load(open(os.path.join(run, "run.json"), encoding="utf-8"))["identity"]


def test_coastline_tiles_in_a_run(tmp_path, monkeypatch):
    """A search whose sea comes from OSM coastline tiles (a canned cache: the tiles and their index rows, no world
    file) records them in its coastline's data entry, the tiles of its step-1 grid's box with their checksums; the
    water mask file and the elevation files their size and time."""
    from rasterio.warp import transform
    from test_offline import _resume_scene, _tiled_search
    params = _resume_scene(tmp_path, monkeypatch, "water").model_copy(update={"coastline": "overpass"})
    with rio.open(params.elevation_file) as s:
        left, top, bottom = s.bounds.left, s.bounds.top, s.bounds.bottom
    lons, lats = transform("EPSG:2180", "EPSG:4326", [left + 82.5] * 2, [top + 500, bottom - 500])
    line = {"type": "Feature", "properties": {"id": "w1", "natural": "coastline"},
            "geometry": {"type": "LineString", "coordinates": [[lons[0], lats[0]], [lons[1], lats[1]]]}}
    lon, lat = lons[0], (lats[0] + lats[1]) / 2
    _theme_tiles(str(tmp_path / "data" / "cache"), "coastline", (lon - 0.4, lat - 0.4, lon + 0.4, lat + 0.4), [line])
    monkeypatch.setattr(osm, "fetch_tile", lambda *args: pytest.fail("a tile was asked"))
    run = _tiled_search(params, tmp_path / "data")
    meta = json.load(open(os.path.join(run, "run.json"), encoding="utf-8"))
    (entry,) = [e for e in meta["data"] if e["layer"] == "OpenStreetMap coastline (Overpass or extracts)"]
    assert list(entry) == ["layer", "credit", "identity"] and list(entry["identity"]) == ["paths", "sha256"]
    cache_dir = str(tmp_path / "data" / "cache")
    assert entry["identity"]["paths"] and all(p.startswith("osm/themes/coastline/") for p in entry["identity"]["paths"])
    assert entry["identity"]["sha256"] == cache.stored_checksums(cache_dir, entry["identity"]["paths"])
    assert all(len(s) == 64 for s in entry["identity"]["sha256"])
    files = {e["layer"]: e for e in meta["data"] if "file" in e}
    assert files and all(e["identity"] == cache.file_identity(e["file"]) for e in files.values())


def test_what_leaves_a_run_holds_no_record(tmp_path):
    """An offline search of the clip (local files, a map): run.json holds the record (`identity` in its data entry
    and at its top level, its keys and order those of before plus `identity`), and nothing that leaves the run
    holds a key named `identity`: the export's lines.geojson ("findaline") and CSV, the rows of runs.js, the
    store's head and the store file's bytes, map.html."""
    import subprocess
    import sys
    import linestore
    from test_offline import OFFLINE_ENV, REPO
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
         "--lat", "50.15624", "--lon", "19.75569", "--radius", "150", "--water", "off", "--fill-gaps", "off",
         "--no-plot", "--yes", "--data-dir", str(tmp_path)],
        cwd=REPO, env={**os.environ, **OFFLINE_ENV}, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    (run,) = glob.glob(str(tmp_path / "runs" / "*" / "run.json"))
    folder = os.path.dirname(run)
    meta = json.load(open(run, encoding="utf-8"))
    assert list(meta) == ["id", "name", "created", "center", "area", "source", "data", "params", "summary", "terrain",
                          "shore", "terrain_sources", "description", "attribution", "store", "identity"]
    assert [list(e) for e in meta["data"]] == [["layer", "file", "identity"]]
    assert list(meta["area"]) == ["type", "lat", "lon", "radius"]
    assert list(meta["identity"]) == ["v", "gdal", "proj", "rasterio"]
    assert _identities(meta) == [("data", 0), ()]
    for fmt in ("geojson", "csv"):
        out = tmp_path / f"export.{fmt}"
        linestore.export(folder, fmt, str(out))
        text = out.read_text(encoding="utf-8")
        assert "identity" not in text
    exported = json.loads((tmp_path / "export.geojson").read_text(encoding="utf-8"))["findaline"]
    assert exported["data"] == [{"layer": meta["data"][0]["layer"], "file": "zabi_kon_nmt.tif"}]
    index = (tmp_path / "runs" / "runs.js").read_text(encoding="utf-8")
    assert meta["id"] in index and "identity" not in index
    rows = json.loads(index[index.index("["):index.rindex("]") + 1])
    assert rows and not _identities(rows)
    head = linestore.read(folder, profiles=False)[1]
    assert head and not _identities(head)
    for name in ("lines.arrow", "profiles.arrow", "map.html", "ATTRIBUTION.txt"):
        if os.path.exists(os.path.join(folder, name)):
            assert b"identity" not in open(os.path.join(folder, name), "rb").read(), name
    assert os.path.exists(os.path.join(folder, "map.html"))
