"""`findaline.py cache status`' runs on changed data (update.changed_runs, the data record of wave 4 of the regression
failures task, the user's C5 "Exact now"): a run with the record by the checksums it noted against the index's now
(T1), files written again by `cache migrate` apart (T2), the coastline, the area's inputs, local files and a resumed
search's mark (T3), a run made before the record by fetch times and marked approximate (T4), nothing written to the
cache and one read-only pass per index (T5), one line per run in words (T6). Offline: tmp caches with index rows made
by cache.record_many (WAL, as a real index) and canned run.json files in the record's shape."""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import cache  # noqa: E402
import update  # noqa: E402

BEFORE = "2026-05-01T00:00:00+00:00"   # the files' fetch time, before the runs
CREATED = "2026-06-01T00:00:00+00:00"  # the runs' time
AFTER = "2026-07-01T00:00:00+00:00"
VERSIONS = {"v": 1, "gdal": "3.12.2", "proj": "9.7.0", "rasterio": "1.5.2"}


def _cache(tmp_path, files):
    """A cache with files {path relative to the cache: bytes}, each recorded with its sha256 and fetched BEFORE."""
    data = tmp_path / "data"
    cache_dir = str(data / "cache")
    os.makedirs(cache_dir)
    cache.check_layout(cache_dir)
    for rel, content in files.items():
        _write(cache_dir, rel, content)
    cache.record_many(cache_dir, [os.path.join(cache_dir, rel) for rel in files])
    for rel in files:
        _set(cache_dir, rel, fetched_at=BEFORE)
    return str(data), cache_dir


def _write(cache_dir, rel, content):
    path = os.path.join(cache_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _set(cache_dir, rel, **columns):
    top, _, inner = rel.partition("/")
    db = sqlite3.connect(os.path.join(cache_dir, top, "index.sqlite"))
    with db:
        db.execute(f"UPDATE files SET {', '.join(f'{c} = ?' for c in columns)} WHERE path = ?",
                   (*columns.values(), inner))
    db.close()


def _sha(cache_dir, rel):
    top, _, inner = rel.partition("/")
    db = sqlite3.connect(os.path.join(cache_dir, top, "index.sqlite"))
    try:
        return db.execute("SELECT sha256 FROM files WHERE path = ?", (inner,)).fetchone()[0]
    finally:
        db.close()


def _run(data, name, meta):
    folder = os.path.join(data, "runs", name)
    os.makedirs(folder, exist_ok=True)
    meta = {"id": name, "created": CREATED, **meta}
    with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)


def _entry(cache_dir, paths, sums=None):
    """A data entry with the record: the checksums the index holds now (or sums)."""
    return {"layer": "Terrain", "folder": paths[0].rsplit("/", 1)[0], "files": len(paths), "paths": paths,
            "identity": {"sha256": sums if sums is not None else [_sha(cache_dir, p) for p in paths]}}


def _changes(data):
    return {c.name: c for c in update.changed_runs(os.path.join(data, "cache"), os.path.join(data, "runs"))}


def _stat(path):
    st = os.stat(path)
    return {"size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")}


def test_a_run_with_the_record_by_checksum(tmp_path):
    """T1: per file, changed when its row or the file is gone or the index's checksum differs (here: new content
    fetched after the run); the same checksum is unchanged whatever the fetch times say; a recorded null or a row
    without a checksum is "not known", never "changed"."""
    names = [f"poland/nmt/{k}.tif" for k in "abcdefg"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    a, b, c, d, e, f, g = names
    sums = [_sha(cache_dir, p) for p in names]
    sums[4] = None                              # e: adopted by hand when the run read it
    _run(data, "exact", {"data": [_entry(cache_dir, names, sums)], "identity": VERSIONS})
    _write(cache_dir, b, b"new content")        # b: other content, fetched again after the run
    cache.record(cache_dir, os.path.join(cache_dir, b))
    os.remove(os.path.join(cache_dir, c))       # c: the file gone
    db = sqlite3.connect(os.path.join(cache_dir, "poland", "index.sqlite"))
    with db:
        db.execute("DELETE FROM files WHERE path = ?", (d.partition("/")[2],))  # d: its row gone
    db.close()
    _set(cache_dir, f, sha256=None)             # f: a row without a checksum
    _set(cache_dir, g, fetched_at=AFTER)        # g: fetched again after the run, the same content
    _set(cache_dir, a, checked_at=AFTER)
    change = _changes(data)["exact"]
    assert (change.files, change.changed, change.reencoded, change.unknown, change.approximate) == (7, 3, 0, 2, False)
    assert change.line() == "exact: 3 of 7 files changed, 2 not known"


def test_the_same_checksums_list_nothing(tmp_path):
    """T1: a run whose files all have their checksums is not named, although every file was fetched after the run
    (a command-line tiled run's own downloads: the rule before the record counted them all); nor is a run with
    only files "not known"."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "own", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    _run(data, "unknown", {"data": [_entry(cache_dir, names, [None, None])], "identity": VERSIONS})
    for p in names:
        _set(cache_dir, p, fetched_at=AFTER)
    assert _changes(data) == {}


def test_re_encoded_files_apart(tmp_path):
    """T2: `cache migrate` writes a tile of the older encoding again (sources.layer.reencode): its checksum
    changes, its fetch time stays (cache.reencoded), so it counts as re-encoded, not changed. Other content with a
    fetch time after the run is changed; another checksum with no fetch time cannot be told: changed."""
    rel = "poland/nmt/2020_N-34-1.tif"
    data, cache_dir = _cache(tmp_path, {"poland/nmt/b.tif": b"b", "poland/nmt/c.tif": b"c"})
    path = os.path.join(cache_dir, rel)
    band = (np.cumsum(np.random.default_rng(1).normal(0, 0.3, (64, 64)), axis=1) + 500).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", height=64, width=64, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(500000, 300000, 1, 1), nodata=np.nan, compress="deflate", predictor=3,
                  tiled=True, blockxsize=32, blockysize=32) as dst:
        dst.write(band, 1)
    cache.record(cache_dir, path)
    _set(cache_dir, rel, fetched_at=BEFORE)
    names = [rel, "poland/nmt/b.tif", "poland/nmt/c.tif"]
    _run(data, "migrated", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    was = _sha(cache_dir, rel)
    assert update.migrate(cache_dir, "poland") == 0
    assert _sha(cache_dir, rel) != was
    _write(cache_dir, "poland/nmt/b.tif", b"b again")  # b: replaced under its name, fetched after the run
    cache.record(cache_dir, os.path.join(cache_dir, "poland/nmt/b.tif"))
    _set(cache_dir, "poland/nmt/c.tif", sha256="0" * 64, fetched_at=None)  # c: no fetch time
    change = _changes(data)["migrated"]
    assert (change.files, change.changed, change.reencoded, change.unknown) == (3, 2, 1, 0)
    assert change.line() == "migrated: 2 of 3 files changed, 1 re-encoded"


def test_runs_made_before_the_record_are_approximate(tmp_path):
    """T4: a run.json without `identity`: the rule before the record (gone, or fetched after the run), its line
    marked approximate; such a run with nothing changed by that rule is not named."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif", "poland/nmt/c.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    old = [{k: v for k, v in _entry(cache_dir, names).items() if k != "identity"}]
    _run(data, "before", {"data": old})
    _run(data, "quiet", {"data": [{"paths": ["poland/nmt/c.tif"]}]})
    _set(cache_dir, names[0], fetched_at=AFTER)  # fetched again with the same content: counted all the same
    os.remove(os.path.join(cache_dir, names[1]))
    changes = _changes(data)
    assert list(changes) == ["before"]
    change = changes["before"]
    assert (change.files, change.changed, change.approximate) == (3, 2, True)
    assert change.line() == "before: 2 of 3 files changed (approximate: a run made before the data record)"


def _nominatim(cache_dir, rows):
    """osm/nominatim.sqlite with osm's schema and rows {(table, query): answer text}."""
    import osm
    path = os.path.join(cache_dir, "osm", "nominatim.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path)
    with db:
        for step in osm.MIGRATIONS:
            db.executescript(step)
        for (table, query), answer in rows.items():
            db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)", (query, answer, BEFORE))
    db.close()


def _text_sha(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_other_inputs(tmp_path):
    """T3: the world file's edition against the newest in the cache; the coastline's and the area's OSM tiles by
    checksum; Nominatim's answers by the sha256 of their stored text (a row gone counts too); local files by size
    and modification time ("may have changed", "missing", never "changed"); a resumed search's mark."""
    coast_tiles = ["osm/themes/coastline/N35.50_E013.75.geojson", "osm/themes/coastline/N36.00_E013.75.geojson"]
    area_tiles = ["osm/themes/cliff/N35.50_E013.75.geojson"]
    world = "osm/water-polygons/2026-10-23/water-polygons-split-4326/water_polygons.shp"
    data, cache_dir = _cache(tmp_path, {**{p: p.encode() for p in coast_tiles + area_tiles},
                                        "poland/nmt/a.tif": b"a"})
    _write(cache_dir, world, b"shp")
    _nominatim(cache_dir, {("search", "Gozo"): '{"name": "Gozo"}', ("search", "Comino"): '{"name": "Comino"}',
                           ("reverse", '{"lat": 36.0}'): '{"address": {}}'})
    terrain, surface, slope = (tmp_path / "terrain.tif", tmp_path / "surface.tif", tmp_path / "slope.tif")
    for f in (terrain, surface, slope):
        f.write_bytes(b"raster")
    world_entry = {"layer": "OpenStreetMap water polygons (world file)", "identity": {"edition": "2026-10-23"}}
    tiles_entry = {"layer": "OpenStreetMap coastline (Overpass)",
                   "identity": {"paths": coast_tiles, "sha256": [_sha(cache_dir, p) for p in coast_tiles]}}
    nominatim = [{"table": "reverse", "query": '{"lat": 36.0}', "sha256": _text_sha('{"address": {}}')},
                 {"table": "search", "query": "Comino", "sha256": _text_sha('{"name": "Comino"}')},
                 {"table": "search", "query": "Gozo", "sha256": _text_sha('{"name": "Gozo"}')},
                 {"query": "no table", "sha256": "1" * 64}, {"table": "sqlite_master", "query": "x", "sha256": "1" * 64}]
    area = {"type": "osm", "identity": {"paths": area_tiles, "sha256": [_sha(cache_dir, p) for p in area_tiles],
                                        "nominatim": nominatim}}
    local = [{"layer": "Terrain file", "file": str(terrain), "identity": _stat(terrain)},
             {"layer": "Surface file", "file": str(surface), "identity": _stat(surface)}]
    _run(data, "inputs", {"data": [_entry(cache_dir, ["poland/nmt/a.tif"]), world_entry, tiles_entry] + local,
                          "area": area, "params": {"slope_file": str(slope)},
                          "identity": {**VERSIONS, "slope_file": _stat(slope), "mixed": True}})
    _run(data, "steady", {"data": [_entry(cache_dir, ["poland/nmt/a.tif"]), world_entry, tiles_entry] + local,
                          "area": area, "params": {"slope_file": str(slope)},
                          "identity": {**VERSIONS, "slope_file": _stat(slope), "mixed": False}})
    changes = _changes(data)  # nothing changed yet: only the mark of a resumed search
    assert list(changes) == ["inputs"]
    assert changes["inputs"].line() == "inputs: its sessions read different data (a resumed search)"
    _write(cache_dir, world.replace("2026-10-23", "2026-11-20"), b"newer")
    _write(cache_dir, coast_tiles[1], b"edited")
    cache.record(cache_dir, os.path.join(cache_dir, coast_tiles[1]))
    _write(cache_dir, area_tiles[0], b"edited")
    cache.record(cache_dir, os.path.join(cache_dir, area_tiles[0]))
    _nominatim(cache_dir, {("search", "Gozo"): '{"name": "Gozo", "edited": 1}'})
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    with db:
        db.execute("DELETE FROM reverse")
    db.close()
    terrain.write_bytes(b"raster, edited")
    surface.unlink()
    os.utime(slope, (0, 1_000_000_000))
    changes = _changes(data)
    assert changes["inputs"].line() == (
        "inputs: coastline: newer edition; coastline: 1 of 2 OSM tiles changed; terrain file may have changed; "
        "surface file missing; area: 1 of 1 OSM tile changed; area: 2 of 3 place name answers changed; "
        "slope file may have changed; its sessions read different data (a resumed search)")
    assert "its sessions" not in changes["steady"].line()
    assert (changes["inputs"].files, changes["inputs"].changed) == (1, 0)


def test_a_record_of_another_shape_is_not_known(tmp_path):
    """A checksum list that is not parallel to its paths, a data entry without the record in a run with it (a
    resume begun before): "not known", never a crash and never "changed"."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "odd", {"data": [_entry(cache_dir, names, ["1" * 64]), {"paths": names}],
                       "area": {"identity": {"paths": names, "sha256": "x", "nominatim": "x"}},
                       "identity": VERSIONS})
    assert _changes(data) == {}


def _listing(root):
    """Every folder and file under root, a file with its bytes' hash (the index files and a WAL too); an -shm file
    by its name only: SQLite's shared memory of the readers, where any reader of a database in use notes itself."""
    import hashlib
    found = {}
    for folder, dirs, files in os.walk(root):
        found[os.path.relpath(folder, root)] = "folder"
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, root)] = "shm" if name.endswith("-shm") else hashlib.sha256(
                    f.read()).hexdigest()
    return found


def test_listing_the_runs_writes_nothing(tmp_path, monkeypatch):
    """T5: changed_runs makes no folder, index, table or side file in the cache (a run naming a folder the cache
    lacks, Nominatim's file absent and present); it reads each index with one read-only connection for all the
    runs; an index another process has open (its WAL there, rows not yet in the file) is read with those rows."""
    names = [f"{top}/t/{k}.tif" for top in ("poland", "spain", "usa") for k in range(30)]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    for k in range(40):
        chosen = sorted(set(names[k % 30::30] + names[k % 7::30]))
        _run(data, f"run{k:02d}", {"data": [_entry(cache_dir, chosen), {"paths": ["slovakia/t/gone.tif"]}],
                                   "area": {"identity": {"nominatim": [{"table": "search", "query": "Gozo",
                                                                        "sha256": "1" * 64}]}},
                                   "identity": VERSIONS})
    _run(data, "old", {"data": [{"paths": ["norway/t/gone.tif", names[0]]}]})
    connects = []
    real = sqlite3.connect
    monkeypatch.setattr(update.sqlite3, "connect", lambda *a, **k: connects.append(a[0]) or real(*a, **k))
    before = _listing(cache_dir)
    first = _changes(data)
    assert _listing(cache_dir) == before
    assert sorted(first) == ["old"] + [f"run{k:02d}" for k in range(40)]  # the Nominatim row is gone everywhere
    assert len(connects) == 3 and all("immutable=1" in c for c in connects), connects
    _nominatim(cache_dir, {("search", "Gozo"): "{}"})
    before, connects[:] = _listing(cache_dir), []
    assert len(_changes(data)) == 41 and _listing(cache_dir) == before and len(connects) == 4
    # another process writing poland's index: its WAL holds a change the file does not have yet
    writer = real(os.path.join(cache_dir, "poland", "index.sqlite"))
    try:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        with writer:
            writer.execute("UPDATE files SET sha256 = ?, fetched_at = ? WHERE path = ?", ("2" * 64, AFTER, "t/0.tif"))
        before, connects[:] = _listing(cache_dir), []
        changes = _changes(data)
        assert _listing(cache_dir) == before
        assert [c for c in connects if "mode=ro" in c] == [c for c in connects if "/poland/" in c or "nominatim" in c]
        assert len(connects) == 4
        assert changes["run00"].changed == 2 and changes["run01"].changed == 1  # and slovakia/t/gone.tif
    finally:
        writer.close()


def test_an_index_without_rows_writes_nothing(tmp_path):
    """T5: an index file that is empty, or holds no table `files`, has no rows (its files count as gone), and is
    left as it was: no table made, no side file; Nominatim's file is read read-only (a rollback journal: no side
    file either)."""
    data, cache_dir = _cache(tmp_path, {"poland/nmt/a.tif": b"a"})
    _write(cache_dir, "spain/index.sqlite", b"")
    _write(cache_dir, "spain/t/a.tif", b"a")
    os.makedirs(os.path.join(cache_dir, "usa"))
    db = sqlite3.connect(os.path.join(cache_dir, "usa", "index.sqlite"))
    with db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE other (x)")
    db.close()
    _write(cache_dir, "usa/t/a.tif", b"a")
    _nominatim(cache_dir, {("search", "Gozo"): "{}"})
    _run(data, "empty", {"data": [_entry(cache_dir, ["poland/nmt/a.tif"]),
                                  {"paths": ["spain/t/a.tif", "usa/t/a.tif"], "identity": {"sha256": ["1" * 64] * 2}}],
                         "area": {"identity": {"nominatim": [{"table": "search", "query": "Gozo",
                                                              "sha256": _text_sha("{}")}]}},
                         "identity": VERSIONS})
    before = _listing(cache_dir)
    change = _changes(data)["empty"]
    assert _listing(cache_dir) == before
    assert change.line() == "empty: 2 of 3 files changed"


def test_status_prints_a_line_per_run(tmp_path, capsys):
    """T6: `cache status` names each run on changed data in one line, under the heading and before the closing
    sentence of before."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "changed", {"data": [_entry(cache_dir, names, [None, _sha(cache_dir, names[1])])],
                           "identity": VERSIONS})
    _run(data, "before", {"data": [{"paths": names}]})
    _write(cache_dir, names[1], b"new")
    cache.record(cache_dir, os.path.join(cache_dir, names[1]))
    update.status(cache_dir, os.path.join(data, "runs"))
    out = capsys.readouterr().out
    assert ("Runs computed on data that has changed since (run them again to use the new data):\n"
            "  before: 1 of 2 files changed (approximate: a run made before the data record)\n"
            "  changed: 1 of 2 files changed, 1 not known\n") in out
    assert out.rstrip().endswith("(it is downloaded again when needed).")
