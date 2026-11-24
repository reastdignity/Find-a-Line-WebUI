"""`findaline.py cache status`' runs on changed data (update.changed_runs, the data record of wave 4 of the regression
failures task, the user's C5 "Exact now"): a run with the record by the checksums it noted against the index's now
(T1), files written again by `cache migrate` apart (T2), the coastline, the area's inputs, local files and a resumed
search's mark (T3), a run made before the record by fetch times and marked approximate (T4), nothing written to the
cache and one read-only pass per index (T5), one line per run in words (T6). Offline: tmp caches with index rows made
by cache.record_many (WAL, as a real index) and canned run.json files in the record's shape."""

import json
import os
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pytest
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


def _entry(cache_dir, paths, sums=None, newest=BEFORE):
    """A data entry with the record: the checksums the index holds now (or sums), and the range of the files' fetch
    times cache.touch gave in the same lookup (newest None: no `fetched`)."""
    entry = {"layer": "Terrain", "folder": paths[0].rsplit("/", 1)[0], "files": len(paths),
             "fetched": {"oldest": BEFORE, "newest": newest}, "paths": paths,
             "identity": {"sha256": sums if sums is not None else [_sha(cache_dir, p) for p in paths]}}
    if newest is None:
        del entry["fetched"]
    return entry


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


DURING = "2026-05-15T00:00:00+00:00"  # after the run read its files (fetched.newest: BEFORE), before its `created`


def test_re_encoded_files_apart(tmp_path):
    """T2 and the review's F0: `cache migrate` writes a tile of the older encoding again (sources.layer.reencode):
    its checksum changes, its fetch time stays (cache.reencoded), so it counts as re-encoded, not changed. Other
    content fetched after the run read its files is changed, also when that was before the run's `created` (a
    one-grid search notes its checksums in step 1 and is saved in step 5: d); another checksum with no fetch time
    cannot be told: changed."""
    rel = "poland/nmt/2020_N-34-1.tif"
    data, cache_dir = _cache(tmp_path, {"poland/nmt/b.tif": b"b", "poland/nmt/c.tif": b"c", "poland/nmt/d.tif": b"d"})
    path = os.path.join(cache_dir, rel)
    band = (np.cumsum(np.random.default_rng(1).normal(0, 0.3, (64, 64)), axis=1) + 500).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", height=64, width=64, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(500000, 300000, 1, 1), nodata=np.nan, compress="deflate", predictor=3,
                  tiled=True, blockxsize=32, blockysize=32) as dst:
        dst.write(band, 1)
    cache.record(cache_dir, path)
    _set(cache_dir, rel, fetched_at=BEFORE)
    names = [rel, "poland/nmt/b.tif", "poland/nmt/c.tif", "poland/nmt/d.tif"]
    _run(data, "migrated", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    was = _sha(cache_dir, rel)
    assert update.migrate(cache_dir, "poland") == 0
    assert _sha(cache_dir, rel) != was and update.cache.info(cache_dir, path)["fetched_at"] == BEFORE
    _write(cache_dir, "poland/nmt/b.tif", b"b again")  # b: replaced under its name, fetched after the run
    cache.record(cache_dir, os.path.join(cache_dir, "poland/nmt/b.tif"))
    _set(cache_dir, "poland/nmt/c.tif", sha256="0" * 64, fetched_at=None)  # c: no fetch time
    _write(cache_dir, "poland/nmt/d.tif", b"d again")  # d: new content between the run's read and its `created`
    cache.record(cache_dir, os.path.join(cache_dir, "poland/nmt/d.tif"))
    _set(cache_dir, "poland/nmt/d.tif", fetched_at=DURING)
    change = _changes(data)["migrated"]
    assert (change.files, change.changed, change.reencoded, change.unknown) == (4, 3, 1, 0)
    assert change.line() == "migrated: 3 of 4 files changed, 1 re-encoded"


def test_the_time_a_run_read_its_files(tmp_path):
    """F0: another checksum is re-encoded only when its fetch time is not later than the time the run had read the
    entry's files: the entry's `fetched.newest` (taken with the checksums), whatever `created` is; `created` only
    when the entry has no `newest`; without both it is changed (never re-encoded for want of a time). Per entry: of
    an entry's several files only the one fetched again counts."""
    names = [f"poland/nmt/{k}.tif" for k in "abcd"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    # "tiled": created before its step 1 (May 10), which then downloaded b and c itself (DURING) and read them: their
    # checksums of now, with the fetch times they had when read, are a re-encoding, not other content
    for name, newest, created in (("both", BEFORE, CREATED), ("tiled", DURING, "2026-05-10T00:00:00+00:00"),
                                  ("nocreated", BEFORE, None),
                                  ("nonewest", None, CREATED), ("neither", None, None)):
        meta = {"data": [_entry(cache_dir, names, newest=newest)], "identity": VERSIONS}
        _run(data, name, meta)
        if created != CREATED:
            path = os.path.join(data, "runs", name, "run.json")
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
            meta.pop("created") if created is None else meta.update(created=created)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
    for p, at in ((names[0], BEFORE), (names[1], DURING), (names[2], DURING)):  # a, b, c: other checksums
        _set(cache_dir, p, sha256="9" * 64, fetched_at=at)
    found = {name: (c.changed, c.reencoded) for name, c in _changes(data).items()}
    assert found == {"both": (2, 1), "tiled": (0, 3), "nocreated": (2, 1), "nonewest": (0, 3), "neither": (3, 0)}


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
    """F1: a checksum list that is not parallel to its paths, a data entry without the record in a run with it (a
    resume begun before), data entries that are no objects, `paths`, `identity`, `fetched` and `params` of other
    shapes, Nominatim items without a query or with one that is no text, a `created` that is no time: "not known"
    for that part, never a crash, never "changed"; a run with a gone file among them is still told."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    nominatim = [{"table": "search", "sha256": "1" * 64}, {"table": "search", "query": {"q": 1}, "sha256": "1" * 64},
                 {"table": "search", "query": None, "sha256": "1" * 64}, "x", None]
    odd = {"data": [_entry(cache_dir, names, ["1" * 64]), {"paths": names}, None, "x", 3,
                    {"paths": "poland/nmt/a.tif", "identity": "x"}, {"paths": [None, 3], "identity": {"sha256": 3}},
                    {"paths": names, "fetched": "x", "identity": {"sha256": [None, None]}},
                    {"file": 3, "identity": {"size": 1}}, {"identity": {"edition": 3}}, {"identity": {"paths": "x"}}],
           "area": {"identity": {"paths": names, "sha256": "x", "nominatim": nominatim}},
           "params": "x", "identity": VERSIONS}
    _run(data, "odd", odd)
    _run(data, "odd2", {**odd, "area": {"identity": {"nominatim": nominatim[:3]}}, "data": "x", "params": None})
    path = os.path.join(data, "runs", "odd3", "run.json")
    _run(data, "odd3", odd)
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["created"] = "not a time"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _run(data, "good", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    assert _changes(data) == {}
    os.remove(os.path.join(cache_dir, names[0]))
    changes = _changes(data)
    assert {name: c.line() for name, c in changes.items()} == {
        "odd": "odd: 3 of 6 files changed, 3 not known; area: 1 of 2 OSM tiles changed",
        "odd3": "odd3: 3 of 6 files changed, 3 not known; area: 1 of 2 OSM tiles changed",
        "good": "good: 1 of 2 files changed"}


def test_a_run_json_that_cannot_be_read_is_named(tmp_path, monkeypatch):
    """F1: a run.json that is no JSON, or no object, is named as not checked (never left out, never an error);
    a run whose judging raises an error nobody foresaw too; the other runs are told as ever."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "good", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    _run(data, "late", {"data": [_entry(cache_dir, names)], "identity": {**VERSIONS, "mixed": True}})
    for name, text in (("broken", "{"), ("list", "[1, 2]")):
        os.makedirs(os.path.join(data, "runs", name))
        with open(os.path.join(data, "runs", name, "run.json"), "w", encoding="utf-8") as f:
            f.write(text)
    os.remove(os.path.join(cache_dir, names[0]))
    real = update._exact

    def failing(cache_dir, meta, *args):
        if meta.get("identity", {}).get("mixed"):
            raise KeyError("a shape nobody foresaw")
        return real(cache_dir, meta, *args)
    monkeypatch.setattr(update, "_exact", failing)
    lines = [c.line() for c in update.changed_runs(os.path.join(data, "cache"), os.path.join(data, "runs"))]
    assert lines == ["broken: its run.json cannot be read (not checked)", "good: 1 of 2 files changed",
                     "late: its run.json cannot be read (not checked)",
                     "list: its run.json cannot be read (not checked)"]


def test_more_files_than_one_query_and_rows_not_ok(tmp_path):
    """Over _IN_CHUNK paths of one folder are asked in several queries, every row found; a row whose status is
    "missing" (the service had no data) is changed for a run that read the file."""
    names = [f"poland/t/{k:04d}.tif" for k in range(update._IN_CHUNK * 2 + 7)]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "many", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    assert _changes(data) == {}
    for p in (names[3], names[update._IN_CHUNK + 1], names[-1]):
        _set(cache_dir, p, status="missing")
    assert _changes(data)["many"].line() == f"many: 3 of {len(names)} files changed"


def test_the_world_file_gone_or_of_another_edition(tmp_path):
    world = "osm/water-polygons/{}/water-polygons-split-4326/water_polygons.shp"
    data, cache_dir = _cache(tmp_path, {"poland/nmt/a.tif": b"a"})
    entry = {"layer": "OpenStreetMap water polygons (world file)", "identity": {"edition": "2026-10-23"}}
    _run(data, "world", {"data": [entry], "identity": VERSIONS})
    assert _changes(data)["world"].line() == "world: coastline: the world file is gone"
    _write(cache_dir, world.format("2026-10-01"), b"older")
    assert _changes(data)["world"].line() == "world: coastline: another edition"
    _write(cache_dir, world.format("2026-10-23"), b"same")
    assert _changes(data) == {}


def test_a_relative_slope_file_is_not_checked(tmp_path, monkeypatch):
    """F6: params.slope_file is stored as given; a relative one cannot be found from another folder: no note
    (never "missing"); an absolute one is checked."""
    data, cache_dir = _cache(tmp_path, {"poland/nmt/a.tif": b"a"})
    slope = tmp_path / "slope.tif"
    slope.write_bytes(b"slope")
    monkeypatch.chdir(tmp_path)
    _run(data, "relative", {"params": {"slope_file": "slope.tif"},
                            "identity": {**VERSIONS, "slope_file": {"size": 1, "modified": BEFORE}}})
    _run(data, "absolute", {"params": {"slope_file": str(slope)},
                            "identity": {**VERSIONS, "slope_file": {"size": 1, "modified": BEFORE}}})
    assert {n: c.line() for n, c in _changes(data).items()} == {"absolute": "absolute: slope file may have changed"}


def test_an_immutable_read_that_fails_is_read_again(tmp_path, monkeypatch):
    """F2: an immutable read that fails (here a first connection whose query raises, as a checkpoint tearing the
    read would) is read once more read-only, whether or not a -wal is there now; a second failure is raised."""
    names = ["poland/nmt/a.tif", "poland/nmt/b.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _run(data, "r", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    _set(cache_dir, names[0], sha256="2" * 64, fetched_at=AFTER)
    real, modes, fail = update._read_only, [], [1]

    class Torn:
        def execute(self, *args):
            raise sqlite3.DatabaseError("database disk image is malformed")

        def close(self):
            pass

    def read_only(db_path, mode=None, timeout=60):
        modes.append(mode)
        return Torn() if len(modes) <= fail[0] else real(db_path, mode, timeout)
    monkeypatch.setattr(update, "_read_only", read_only)
    assert _changes(data)["r"].changed == 1 and modes == [None, "mode=ro"]
    modes[:], fail[0] = [], 2
    try:
        _changes(data)
        raise AssertionError("a second failure is raised")
    except sqlite3.DatabaseError:
        pass
    assert modes == [None, "mode=ro"]


def test_nominatim_answers_that_cannot_be_read(tmp_path, monkeypatch):
    """F3: osm/nominatim.sqlite locked by a writer over NOMINATIM_TIMEOUT, left with a hot journal by a killed
    writer, or no database: its answers are not known, the runs with answers get one note, the rest is told; no
    error."""
    import subprocess
    names = ["poland/nmt/a.tif"]
    data, cache_dir = _cache(tmp_path, {p: p.encode() for p in names})
    _nominatim(cache_dir, {("search", "Gozo"): "{}"})
    asked = {"nominatim": [{"table": "search", "query": "Gozo", "sha256": _text_sha("{}")}]}
    _run(data, "place", {"data": [_entry(cache_dir, names)], "area": {"identity": asked}, "identity": VERSIONS})
    _run(data, "plain", {"data": [_entry(cache_dir, names)], "identity": VERSIONS})
    os.remove(os.path.join(cache_dir, names[0]))
    told = {"place": "place: 1 of 1 file changed; area: the place name answers could not be read",
            "plain": "plain: 1 of 1 file changed"}
    assert _changes(data)["place"].line() == "place: 1 of 1 file changed"
    path = os.path.join(cache_dir, "osm", "nominatim.sqlite")
    monkeypatch.setattr(update, "NOMINATIM_TIMEOUT", 0.2)
    writer = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        assert {n: c.line() for n, c in _changes(data).items()} == told
    finally:
        writer.close()
    code = ("import sqlite3, os, sys\n"
            "db = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "db.execute('PRAGMA cache_size=1')\n"
            "db.execute('BEGIN')\n"
            "for k in range(2000): db.execute('INSERT INTO search VALUES (?, ?, ?)', (str(k), 'x' * 500, None))\n"
            "os._exit(0)\n")
    subprocess.run([sys.executable, "-c", code, path], check=True)
    assert os.path.exists(path + "-journal")
    before = _listing(cache_dir)
    assert {n: c.line() for n, c in _changes(data).items()} == told
    assert _listing(cache_dir) == before
    os.remove(path + "-journal")
    with open(path, "wb") as f:
        f.write(b"no database, " * 200)
    assert {n: c.line() for n, c in _changes(data).items()} == told


def test_sqlite_uris(tmp_path, monkeypatch):
    """F7: a drive path, a network path (\\\\server\\share: an empty authority, which SQLite takes; pathlib's
    file://server/... it refuses), a Linux path, spaces, "%", "#", "?" and letters outside ASCII."""
    assert update._uri(r"C:\a b\ł%#?\index.sqlite", "mode=ro") == "file:///C:/a%20b/%C5%82%25%23%3F/index.sqlite?mode=ro"
    assert update._uri(r"\\box\share\cache\osm\index.sqlite", "immutable=1") == \
        "file:////box/share/cache/osm/index.sqlite?immutable=1"
    monkeypatch.setattr(update.os.path, "abspath", lambda p: p)
    assert update._uri("/srv/data/cache/x y/index.sqlite", "mode=ro") == "file:///srv/data/cache/x%20y/index.sqlite?mode=ro"
    monkeypatch.undo()
    folder = tmp_path / "a b ł%#&=ż"
    data, cache_dir = _cache(folder, {"poland/nmt/a.tif": b"a"})
    _run(data, "r", {"data": [_entry(cache_dir, ["poland/nmt/a.tif"])], "identity": VERSIONS})
    _set(cache_dir, "poland/nmt/a.tif", sha256="2" * 64, fetched_at=AFTER)
    before = _listing(cache_dir)
    assert _changes(data)["r"].changed == 1 and _listing(cache_dir) == before
    with pytest.raises(sqlite3.OperationalError, match="authority"):
        sqlite3.connect(pathlib.Path(r"\\box\share\x.sqlite").as_uri() + "?mode=ro", uri=True)


def test_a_cache_on_a_network_path(tmp_path):
    """F7: the index read through \\\\localhost\\<drive>$ (the administrative share; skipped where this user cannot
    reach it)."""
    drive, rest = os.path.splitdrive(str(tmp_path))
    if os.name != "nt" or not drive.endswith(":"):
        pytest.skip("Windows drive paths only")
    unc = rf"\\localhost\{drive[0]}${rest}"
    if not os.path.isdir(unc):
        pytest.skip("the administrative share is not reachable for this user")
    data, cache_dir = _cache(tmp_path, {"poland/nmt/a.tif": b"a"})
    _run(data, "r", {"data": [_entry(cache_dir, ["poland/nmt/a.tif"])], "identity": VERSIONS})
    _set(cache_dir, "poland/nmt/a.tif", sha256="2" * 64, fetched_at=AFTER)
    changes = update.changed_runs(os.path.join(unc, "data", "cache"), os.path.join(unc, "data", "runs"))
    assert [c.line() for c in changes] == ["r: 1 of 1 file changed"]


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
    runs; an index another process has open (its WAL there, rows not yet in the file) is read with those rows.
    The concurrent part covers the read-only path only (the WAL is there before the look): a writer that begins
    between the look and the read, or a checkpoint during an immutable read, is not made here (the retry:
    test_an_immutable_read_that_fails_is_read_again)."""
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
