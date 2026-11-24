"""`findaline.py cache status` reads only (the user's D3 of 2026-11-24, "Yes, both"): on a canned data folder that
holds every kind of thing `status` prints, the command makes, changes and removes nothing (R1), prints what it printed
before but for the world file put there by hand (R2, R3), reads through update._query's read-only door (R4), reads an
index another connection is writing without failing it (R5); a data folder whose path holds "[" finds its world file
(R6); `cache update` adopts a world file put there by hand before it checks (R3). Offline: tmp caches only."""

import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import cache  # noqa: E402
import coast  # noqa: E402
import osm  # noqa: E402
import sources as src  # noqa: E402
import update  # noqa: E402
from sources.layers import tnmbucket as tb  # noqa: E402

OLD = "2023-01-02T00:00:00+00:00"      # a check long ago: due for everything that can change
FETCHED = "2026-05-01T00:00:00+00:00"  # every row's fetch time
CHECKED = "2026-11-01T00:00:00+00:00"  # a recent check: not due
USED = "2026-11-02T00:00:00+00:00"
CREATED = "2026-06-01T00:00:00+00:00"  # the runs' time
EARLY = "2026-04-01T00:00:00+00:00"    # a run made before its files were fetched (the rule before the record)
EDITION = "2026-10-23"
WORLD = f"osm/water-polygons/{EDITION}/water-polygons-split-4326"
SPAIN = src.SOURCES["spain"].nmt
MALTA = src.SOURCES["malta"].nmt


def _file(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _index(cache_dir, top):
    return os.path.join(cache_dir, top, "index.sqlite")


def _times(cache_dir, top, **columns):
    """Fixed times for every row of an index (or the columns given), so the printed text is the same every day."""
    columns = {"fetched_at": FETCHED, "checked_at": CHECKED, "last_used_at": USED, **columns}
    db = sqlite3.connect(_index(cache_dir, top))
    with db:
        db.execute(f"UPDATE files SET {', '.join(f'{c} = ?' for c in columns)}", tuple(columns.values()))
    db.close()


def _set(cache_dir, path, **columns):
    top, _, inner = cache.relative(cache_dir, path).partition("/")
    db = sqlite3.connect(_index(cache_dir, top))
    with db:
        db.execute(f"UPDATE files SET {', '.join(f'{c} = ?' for c in columns)} WHERE path = ?",
                   (*columns.values(), inner))
    db.close()


def _old_tile(path):
    """A float tile in the older encoding (deflate, not LERC)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    band = np.arange(400, dtype=np.float32).reshape(20, 20)
    with rio.open(path, "w", driver="GTiff", height=20, width=20, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(500000, 300000, 1, 1), nodata=np.nan, compress="deflate") as dst:
        dst.write(band, 1)
    return path


def _run(data, name, meta=None, text=None):
    folder = os.path.join(data, "runs", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as f:
        f.write(text if text is not None else json.dumps({"id": name, **meta}))


def canned(root):
    """A data folder holding every kind of thing `cache status` prints: indexed folders with rows due and not due
    (spain's live tiles, a Maltese release, an OSM theme tile, an OSM extract), an index in the rollback-journal mode
    (poland) and the others in WAL, a folder without an index (fabdem), an index without the table `files` (norway),
    a world file put there by hand without rows, an OSM extract, a tile in the older encoding (poland), the USA's
    list of unlisted files, Nominatim's answers (rollback journal), and runs with and without the data record and
    one that cannot be read. No database is left open: no -wal or -shm file is there. Returns (data, cache_dir)."""
    data = os.path.join(str(root), "data")
    cache_dir = os.path.join(data, "cache")
    cache.check_layout(cache_dir)
    due = _file(SPAIN.tile_path(cache_dir, (5.0, 100, 2000)))
    fresh = _file(SPAIN.tile_path(cache_dir, (5.0, 101, 2000)), b"y")
    release = _file(MALTA.tile_path(cache_dir, (1.0, 230, 1790)), b"z")
    sheet = _old_tile(os.path.join(cache_dir, "poland", "nmt", "2020_N-34-1.tif"))
    pbf = _file(os.path.join(cache_dir, "malta", "osm-extract", "malta.osm.pbf"), b"pbf")
    with open(pbf[:-len(".osm.pbf")] + ".geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "Polygon", "coordinates": [[[14.1, 35.8], [14.6, 35.8], [14.6, 36.1], [14.1, 35.8]]]}, f)
    theme = _file(os.path.join(cache_dir, "osm", "themes", "coastline", osm.tile_name(35.75, 14.25) + ".geojson"),
                  b'{"type": "FeatureCollection", "features": []}')
    for path in (due, fresh, release, sheet, theme):
        cache.record(cache_dir, path)
    cache.record(cache_dir, pbf, url="https://download.geofabrik.de/europe/malta-latest.osm.pbf",
                 source_date="2026-10-30T21:21:02+00:00")
    tb.write_list(tb.unlisted_path(cache_dir), {"made_at": "x", "files": 3, "listed": 1, "left_out": []}, [], "b", "a",
                  "d")
    cache.record(cache_dir, tb.unlisted_path(cache_dir), url="b")
    for top in ("spain", "malta", "poland", "osm", "usa"):
        _times(cache_dir, top)
    for path in (due, pbf, theme):
        _set(cache_dir, path, checked_at=OLD)
    _set(cache_dir, tb.unlisted_path(cache_dir), checked_at=cache.now_iso(5 * 86400))  # made 5 days ago: not due
    db = sqlite3.connect(_index(cache_dir, "poland"))
    db.execute("PRAGMA journal_mode=DELETE")
    db.close()
    _file(os.path.join(cache_dir, "norway", "t", "a.tif"))
    db = sqlite3.connect(_index(cache_dir, "norway"))  # made and never written: no table `files`
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE other (x)")
    db.close()
    _file(os.path.join(cache_dir, "fabdem", "v1-2", "N35E014.tif"))  # a folder without an index
    for name in ("water_polygons.shp", "water_polygons.dbf"):  # the world file put there by hand: no rows
        _file(os.path.join(cache_dir, *WORLD.split("/"), name), name.encode())
    db = sqlite3.connect(os.path.join(cache_dir, "osm", "nominatim.sqlite"))
    with db:
        for step in osm.MIGRATIONS:
            db.executescript(step)
        db.execute("INSERT INTO search VALUES (?, ?, ?)", ("Gozo", "{}", FETCHED))
    db.close()
    rel = lambda path: cache.relative(cache_dir, path)  # noqa: E731
    sums = {p: cache.info(cache_dir, p)["sha256"] for p in (fresh, release)}
    _run(data, "recorded", {"created": CREATED, "identity": {"v": 1},
                            "data": [{"layer": "Terrain", "paths": [rel(fresh), rel(release), "spain/t/gone.tif"],
                                      "fetched": {"oldest": FETCHED, "newest": FETCHED},
                                      "identity": {"sha256": [sums[fresh], sums[release], "1" * 64]}},
                                     {"layer": "Coastline", "identity": {"edition": EDITION}}],
                            "area": {"identity": {"nominatim": [{"table": "search", "query": "Gozo",
                                                                 "sha256": "2" * 64}]}}})
    _run(data, "same", {"created": CREATED, "identity": {"v": 1},
                        "data": [{"layer": "Terrain", "paths": [rel(fresh)],
                                  "fetched": {"oldest": FETCHED, "newest": FETCHED},
                                  "identity": {"sha256": [sums[fresh]]}}]})
    _run(data, "before", {"created": EARLY, "data": [{"layer": "Terrain", "paths": [rel(due), rel(sheet)]}]})
    _run(data, "broken", text="{")
    return data, cache_dir


def listing(root):
    """Every folder and file under root, a file with its bytes' sha256; an -shm file by its name only (SQLite's shared
    memory of the readers, where a reader of a database another connection has open notes itself)."""
    found = {}
    for folder, dirs, files in os.walk(root):
        found[os.path.relpath(folder, root)] = "folder"
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, root)] = "shm" if name.endswith("-shm") else hashlib.sha256(
                    f.read()).hexdigest()
    return found


def _journal(path):
    """The journal mode an SQLite file's header says: 1 rollback, 2 WAL."""
    with open(path, "rb") as f:
        return f.read(20)[18]


def _tripwire(monkeypatch):
    """The index's writing connection and any network connection fail the test (a canned cache cannot hold every
    kind of layer: what it lacks is covered by this)."""
    monkeypatch.setattr(cache, "_connect", lambda *a, **k: pytest.fail(f"a writing connection: {a}"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail(f"a network connection: {a}"))


def _status(data, *args):
    return update.main(["--data-dir", data, "cache", "status", *args])


def test_cache_status_writes_nothing(tmp_path, monkeypatch, capsys):
    """R1: the listing of the whole data folder (every folder, every file's bytes) is the same before and after
    `cache status`, with and without a folder argument: no folder, file, table or row is made, no journal mode
    changes, no world file is adopted; nothing connects for writing or to the network."""
    data, cache_dir = canned(tmp_path)
    modes = {top: _journal(_index(cache_dir, top)) for top in ("spain", "poland", "norway", "osm")}
    assert modes == {"spain": 2, "poland": 1, "norway": 2, "osm": 2}
    before = listing(data)
    assert not [name for name in before if name.endswith(("-wal", "-shm", "-journal"))]
    _tripwire(monkeypatch)
    for args in ([], ["spain"], ["osm"], ["usa"], ["malta"], ["norway"], ["fabdem"], ["poland"]):
        assert _status(data, *args) == 0
        assert listing(data) == before, args
    out = capsys.readouterr().out
    assert {top: _journal(_index(cache_dir, top)) for top in modes} == modes
    assert "OSM extracts:\n  malta:" in out and "Tiles in the older encoding: 1" in out
    assert "the list of the files its index does not list: made " in out
    assert "Runs computed on data that has changed since" in out


@pytest.mark.parametrize("empty", [False, True])
def test_cache_status_of_a_data_folder_without_a_cache(tmp_path, monkeypatch, capsys, empty):
    """R1: a data folder with no cache folder, or an empty one, gets none and no LAYOUT file (`cache status` used to
    mark it as a new cache)."""
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(data, "cache") if empty else data)
    before = listing(data)
    _tripwire(monkeypatch)
    assert _status(data) == 0
    assert listing(data) == before
    assert capsys.readouterr().out.startswith(f"Cache: {os.path.join(data, 'cache')}\n")
    with pytest.raises(SystemExit, match="No folder spain"):
        _status(data, "spain")
    assert listing(data) == before


# R2: the text of `main` (67eae626) on the canned folder but for R3's two changes: the world file's rows are no longer
# made (its osm row counted 3 files fetched up to the day the files were adopted, their modification time) and the
# line that names them instead
PRINTED = """Cache: <cache>
Folder              Size   Files  Fetched                  Last used   To check (stale)
fabdem            0.00GB       0  - - -                    -           -
malta             0.00GB       2  2026-05-01 - 2026-05-01  2026-11-02  OSM extract malta: 1
norway            0.00GB       0  - - -                    -           -
osm               0.00GB       1  2026-05-01 - 2026-05-01  2026-11-02  OSM coastline tiles (Overpass): 1
poland            0.00GB       1  2026-05-01 - 2026-05-01  2026-11-02  -
spain             0.00GB       2  2026-05-01 - 2026-05-01  2026-11-02  MDT05 (terrain) Spain: 1
usa               0.00GB       1  2026-05-01 - 2026-05-01  2026-11-02  -

The world water polygons in osm/water-polygons/2026-10-23 have no index rows yet (2 of 2 files): \
`findaline.py cache update` adopts them.

3DEP 1 m DEM (terrain), the list of the files its index does not list: made <day> (5 days ago, 3 files); made \
again after 28 days

OSM extracts:
  malta: 0.00 GB, data of 2026-10-30T21:21, checked 2023-01-02

Tiles in the older encoding: 1 (0.00 GB; poland). A search writes the ones it reads again; \
`findaline.py cache migrate` does all of them.

Runs computed on data that has changed since (run them again to use the new data):
  before: 2 of 2 files changed (approximate: a run made before the data record)
  broken: its run.json cannot be read (not checked)
  recorded: 1 of 3 files changed; area: 1 of 1 place name answer changed

`findaline.py cache update` checks what is stale; delete a folder to free its space (it is downloaded again when \
needed).
"""


def test_cache_status_prints_what_it_printed(tmp_path, monkeypatch, capsys):
    """R2, R3: the text is `main`'s line for line but for the world file put there by hand: no rows made for it, one
    line naming it instead (with or without the folder osm, not with another folder)."""
    data, cache_dir = canned(tmp_path)
    _tripwire(monkeypatch)
    assert _status(data) == 0
    out = re.sub(r"made \d{4}-\d\d-\d\d \(", "made <day> (", capsys.readouterr().out.replace(cache_dir, "<cache>"))
    assert out == PRINTED
    assert _status(data, "osm") == 0
    assert "The world water polygons in osm/water-polygons/2026-10-23 have no" in capsys.readouterr().out
    assert _status(data, "spain") == 0
    assert "world water polygons" not in capsys.readouterr().out


def _world_only(root):
    """A data folder whose cache holds only the world file, put there by hand (no index)."""
    data = os.path.join(str(root), "data")
    cache_dir = os.path.join(data, "cache")
    cache.check_layout(cache_dir)
    for name in ("water_polygons.shp", "water_polygons.dbf"):
        _file(os.path.join(cache_dir, *WORLD.split("/"), name), name.encode())
    return data, cache_dir


def _world_rows(cache_dir):
    return [cache.info(cache_dir, os.path.join(cache_dir, *WORLD.split("/"), name), update._query)
            for name in ("water_polygons.shp", "water_polygons.dbf")]


@pytest.mark.parametrize("args", [[], ["osm"], ["--point", "35.9,14.4"], ["--bbox", "35,14,36,15"]])
def test_cache_update_adopts_the_world_file(tmp_path, monkeypatch, capsys, args):
    """R3: every form of `cache update` adopts a world file put there by hand before it checks (as `status` did): its
    files get their rows (fetched and checked at their modification time, so not due), and `status` no longer names
    them. Nothing is asked of a provider."""
    data, cache_dir = _world_only(tmp_path)
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail(f"a network connection: {a}"))
    assert _status(data) == 0 and "have no index rows yet (2 of 2 files)" in capsys.readouterr().out
    assert _world_rows(cache_dir) == [None, None]
    assert update.main(["--data-dir", data, "cache", "update", *args]) == 0
    assert "Nothing to check" in capsys.readouterr().out
    assert all(row and row["status"] == "ok" and row["fetched_at"] for row in _world_rows(cache_dir))
    assert _status(data) == 0
    out = capsys.readouterr().out
    assert "world water polygons" not in out and re.search(r"\nosm +0\.00GB +2 ", out)


def test_what_the_adoption_is_for(tmp_path):
    """R3: the .shp's row is what makes `cache update` check the world file after its interval (_check); without it
    no update checks it. checks() itself adopts first, also with --all and with another folder named."""
    data, cache_dir = _world_only(tmp_path)
    os.makedirs(os.path.join(cache_dir, "spain"))
    assert update._world_without_rows(cache_dir) == (WORLD.rsplit("/", 1)[0], 2, 2)
    assert update.checks(cache_dir, "spain", update="all") == []
    assert update._world_without_rows(cache_dir) is None
    assert [c.what for c in update.checks(cache_dir, update="all")] == ["OSM water polygons (world)"]
    assert update.checks(cache_dir) == []  # adopted at its modification time: not due


def test_one_reading_door(tmp_path):
    """R4: cache.rows and cache.info read through update._query give the writing connection's rows, for an index in
    WAL and one in the rollback-journal mode; an index without the table or no index gives none, and nothing is
    made."""
    data, cache_dir = canned(tmp_path)
    before = listing(data)
    for top in ("spain", "poland", "malta", "osm", "usa"):
        read = cache.rows(cache_dir, top, update._query)
        assert read and all({**cache.info(cache_dir, os.path.join(cache_dir, row["path"]), update._query),
                             "path": row["path"]} == row for row in read)
        written = cache.rows(cache_dir, top) if top != "poland" else None  # the writer switches poland to WAL
        assert written is None or written == read
    assert cache.rows(cache_dir, "norway", update._query) == [] and cache.rows(cache_dir, "fabdem", update._query) == []
    assert cache.info(cache_dir, os.path.join(cache_dir, "norway", "t", "a.tif"), update._query) is None
    assert cache.info(cache_dir, os.path.join(cache_dir, "nowhere", "a.tif"), update._query) is None
    assert cache.info(cache_dir, os.path.join(cache_dir, "spain", "gone.tif"), update._query) is None
    assert listing(data) == before


def test_cache_status_beside_a_writer(tmp_path, monkeypatch, capsys):
    """R5: an index another connection has open, its rows still in the WAL (no checkpoint) and more committed while
    `status` reads: they are read (the read-only path), `status` does not wait for the writer, and the writer goes
    on; a write transaction held open over the whole of `status` blocks neither side."""
    data, cache_dir = canned(tmp_path)
    index = _index(cache_dir, "spain")
    writer = sqlite3.connect(index, timeout=60, check_same_thread=False)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    insert = "INSERT INTO files (path, status, fetched_at, checked_at, last_used_at) VALUES (?, 'ok', ?, ?, ?)"
    with writer:
        writer.executemany(insert, [(f"w/{k}.tif", FETCHED, CHECKED, USED) for k in range(5)])
    assert os.path.getsize(index + "-wal") > 0
    _tripwire(monkeypatch)
    stop, errors, written = threading.Event(), [], []

    def write():
        try:
            while not stop.is_set():
                with writer:
                    writer.execute(insert, (f"w/{5 + len(written)}.tif", FETCHED, CHECKED, USED))
                written.append(1)
                time.sleep(0.005)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    thread = threading.Thread(target=write)
    thread.start()
    try:
        start = time.monotonic()
        assert _status(data, "spain") == 0
        seconds = time.monotonic() - start
    finally:
        stop.set()
        thread.join()
    files = int(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("spain ")).split()[2])
    assert not errors and written
    assert 2 + 5 <= files <= 2 + 5 + len(written) and seconds < 20, (files, seconds)
    count = 2 + 5 + len(written)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute(insert, ("w/held.tif", FETCHED, CHECKED, USED))
    start = time.monotonic()
    assert _status(data, "spain") == 0 and time.monotonic() - start < 20
    assert f"spain             0.00GB {count:>7}  " in capsys.readouterr().out  # the uncommitted row is not seen
    writer.commit()
    writer.close()
    assert "spain/w/held.tif" in {row["path"] for row in cache.rows(cache_dir, "spain", update._query)}


def test_a_wal_and_shm_left_by_a_killed_writer(tmp_path, monkeypatch):
    """R1's limit, seen on the real cache: an index with a -wal (empty after its checkpoint) and a -shm left by a
    writer that was killed is read read-only. Asserted: the database and the -wal keep their bytes and their
    modification times, every other file its bytes, no file is made (the listing; the -shm by its name only); the
    next writer's open and close removes the -wal and the -shm (main's `status`, which opened every index for
    writing, removed them itself). Not asserted, seen (2026-11-24, the reviews too): SQLite's reader writes into the
    -shm it finds (its bytes and time change)."""
    data, cache_dir = canned(tmp_path)
    index = _index(cache_dir, "spain")
    killed = (f"import os, sqlite3; db = sqlite3.connect({index!r}); db.execute(\"UPDATE files SET url = 'u'\"); "
              "db.commit(); db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); os._exit(0)")
    subprocess.run([sys.executable, "-c", killed], check=True)
    assert os.path.getsize(index + "-wal") == 0 and os.path.exists(index + "-shm")
    assert update._mode(index) == "mode=ro"
    before, times = listing(data), [os.stat(index + suffix).st_mtime_ns for suffix in ("", "-wal")]
    _tripwire(monkeypatch)
    assert _status(data) == 0
    after = listing(data)
    assert after == before  # the -shm by its name only
    assert [os.stat(index + suffix).st_mtime_ns for suffix in ("", "-wal")] == times
    with open(index + "-wal", "rb") as f:
        assert f.read() == b""
    monkeypatch.undo()
    cache.info(cache_dir, os.path.join(cache_dir, "spain", "t.tif"))  # a writer's open and close
    assert not os.path.exists(index + "-wal") and not os.path.exists(index + "-shm")


def test_a_data_folder_with_brackets(tmp_path, monkeypatch, capsys):
    """R6: in a data folder whose path holds "[" and "]" the world file is found (coast.world_file), its folder's
    files listed (coast._world_files: what `cache update` adopts and a newer edition's check stamps), `status` names
    them and `cache update` adopts them; a run on that world file reads no change."""
    root = tmp_path / "x[1]"
    data, cache_dir = _world_only(root)
    shapefile = coast.world_file(cache_dir)
    assert shapefile == os.path.join(cache_dir, *WORLD.split("/"), "water_polygons.shp")
    assert len(coast._world_files(os.path.dirname(os.path.dirname(shapefile)))) == 2
    _run(data, "r", {"created": CREATED, "identity": {"v": 1},
                     "data": [{"layer": "Coastline", "identity": {"edition": EDITION}}]})
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail(f"a network connection: {a}"))
    assert _status(data) == 0
    out = capsys.readouterr().out
    assert "have no index rows yet (2 of 2 files)" in out and "Runs computed" not in out
    assert update.main(["--data-dir", data, "cache", "update"]) == 0
    assert all(_world_rows(cache_dir))


def _spy_modes(monkeypatch):
    """The modes update._read_only opens with, in order."""
    modes, real = [], update._read_only
    monkeypatch.setattr(update, "_read_only",
                        lambda path, mode=None, timeout=60: modes.append(mode) or real(path, mode, timeout))
    return modes


def test_an_immutable_read_a_writer_may_have_torn_is_made_again(tmp_path, monkeypatch):
    """G1 (the code review's D1): an index at rest is read immutable, with no lock. A search's writer that opens it,
    commits and closes between the stamp before the read and its end (here inside the read: the test's ask) writes
    its WAL into the file under the read; the file's stamp differs afterwards, so the read is made again read-only,
    and its rows are those a read-only read gives (the writer's row among them). Without a writer the immutable
    read is kept (one connection)."""
    data, cache_dir = canned(tmp_path)
    index = _index(cache_dir, "spain")
    assert update._mode(index) == "immutable=1"
    modes = _spy_modes(monkeypatch)
    rows = lambda db: sorted(r[0] for r in db.execute("SELECT path FROM files"))  # noqa: E731
    assert update._query(index, rows) == [p.split("/", 1)[1] for p in sorted(
        r["path"] for r in cache.rows(cache_dir, "spain"))] and modes == ["immutable=1"]
    calls = []

    def ask(db):
        calls.append(len(modes))
        if len(calls) == 1:
            writer = sqlite3.connect(index)
            with writer:
                writer.execute("INSERT INTO files (path, status) VALUES ('w/new.tif', 'ok')")
            writer.close()  # the WAL into the file, the -wal removed
            assert not os.path.exists(index + "-wal")
        return rows(db)
    modes.clear()
    found = update._query(index, ask)
    assert modes == ["immutable=1", "mode=ro"] and len(calls) == 2
    monkeypatch.undo()
    assert "w/new.tif" in found and found == update._query(index, rows)


def test_reads_beside_a_writer_that_opens_commits_and_closes(tmp_path):
    """G1, the code review's probe kept short: a 200 000-row index; a writer process opens it, inserts 300 paths,
    commits, closes and pauses 0.1 s, again and again for 10 s; meanwhile `status`' reader (cache.rows through
    update._query) reads every row again and again. No read holds a path twice or lacks one that was always there.
    Before the stamp check the review's probe found such reads in 4 to 20 % of the immutable ones (13 % here: 23 of
    183 in 60 s); 10-s runs of the unfixed code failed this test as the report of round 1 says."""
    cache_dir = os.path.join(str(tmp_path), "cache")
    os.makedirs(os.path.join(cache_dir, "spain"))
    index = _index(cache_dir, "spain")
    db = sqlite3.connect(index)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(cache.SCHEMA)
    with db:
        db.executemany("INSERT INTO files (path, status) VALUES (?, 'ok')",
                       ((f"base/{k:07d}.tif",) for k in range(200_000)))
    db.close()
    base = {f"spain/base/{k:07d}.tif" for k in range(200_000)}
    writer = (f"import random, sqlite3, time\nend = time.monotonic() + 10\nwhile time.monotonic() < end:\n"
              f"    db = sqlite3.connect({index!r}, timeout=60)\n    with db:\n"
              "        db.executemany(\"INSERT OR IGNORE INTO files (path, status) VALUES (?, 'ok')\", "
              "[(f'new/{random.random():.15f}.tif',) for _ in range(300)])\n"
              "    db.close()\n    time.sleep(0.1)\n")
    process = subprocess.Popen([sys.executable, "-c", writer])
    reads, bad = 0, []
    try:
        while process.poll() is None:
            paths = [row["path"] for row in cache.rows(cache_dir, "spain", update._query)]
            reads += 1
            if len(paths) != len(set(paths)) or not base <= set(paths):
                bad.append((len(paths), len(set(paths)), len(base - set(paths))))
    finally:
        process.wait(60)
    assert process.returncode == 0 and reads >= 5
    assert not bad, f"{len(bad)} of {reads} reads torn: {bad[:5]}"


def _expected(replace=(), drop=()):
    """PRINTED with lines replaced ({start of a line: the new line}) and lines dropped (by their start), the blank
    line before a dropped section too."""
    lines = []
    for line in PRINTED.split("\n"):
        if any(line.startswith(d) for d in drop):
            if lines and lines[-1] == "":
                lines.pop()
            continue
        lines.append(next((new for old, new in replace if line.startswith(old)), line))
    return "\n".join(lines)


def _printed(out, cache_dir):
    return re.sub(r"made \d{4}-\d\d-\d\d \(", "made <day> (", out.replace(cache_dir, "<cache>"))


def test_an_index_with_a_hot_journal_is_named(tmp_path, monkeypatch, capsys):
    """G2 (the code review's D3): a rollback-journal index (poland's) whose writer was killed in the middle of its
    transaction, after it had written into the file (a hot journal: a read-only reader cannot roll it back and
    raises). `status` names that folder with the error's class in its row, leaves it out of the tiles in the older
    encoding, names the run that read its files as not checked, lists the rest as ever and ends with 0; nothing is
    written (the hot journal is left for the next writer)."""
    data, cache_dir = canned(tmp_path)
    index = _index(cache_dir, "poland")
    killed = (f"import os, sqlite3; db = sqlite3.connect({index!r}); db.execute('PRAGMA cache_size=1'); "
              "db.execute('BEGIN IMMEDIATE'); db.executemany(\"INSERT INTO files (path, status) VALUES (?, 'ok')\", "
              "[(f'x/{k}.tif',) for k in range(20000)]); os._exit(0)")
    subprocess.run([sys.executable, "-c", killed], check=True)
    assert os.path.getsize(index + "-journal") > 0 and _journal(index) == 1
    with pytest.raises(sqlite3.Error):
        update._query(index, lambda db: db.execute("SELECT * FROM files").fetchall())
    before = listing(data)
    _tripwire(monkeypatch)
    assert _status(data) == 0
    out = _printed(capsys.readouterr().out, cache_dir)
    error = re.search(r"\npoland +0\.00GB  its index cannot be read now \((\w+)\)\n", out)
    assert error, out
    assert out == _expected(
        replace=[("poland ", f"poland            0.00GB  its index cannot be read now ({error[1]})"),
                 ("  before:", f"  before: not checked (the index of poland cannot be read now: {error[1]})")],
        drop=["Tiles in the older encoding"])
    assert listing(data) == before


def test_an_index_that_cannot_be_read_now_is_named(tmp_path, monkeypatch, capsys):
    """G2: one folder's index raises sqlite3.Error on every read (a writer's lock held over the timeout, made here):
    its row, the runs that read its files and nothing else change; it is asked once, never again."""
    data, cache_dir = canned(tmp_path)
    real, asked = update._query, []

    def query(db_path, ask, timeout=60):
        if os.sep + "spain" + os.sep in db_path:
            asked.append(db_path)
            raise sqlite3.OperationalError("database is locked")
        return real(db_path, ask, timeout)
    monkeypatch.setattr(update, "_query", query)
    _tripwire(monkeypatch)
    assert _status(data) == 0
    out = _printed(capsys.readouterr().out, cache_dir)
    gone = "not checked (the index of spain cannot be read now: OperationalError)"
    assert out == _expected(
        replace=[("spain ", "spain             0.00GB  its index cannot be read now (OperationalError)"),
                 ("  before:", f"  before: {gone}"), ("  recorded:", f"  recorded: {gone}\n  same: {gone}")])
    assert len(asked) == 1
