"""tools/record_check.py, the completeness check of the data record: offline, on a canned real cache and a canned
record, the harness's run stubbed. It places exactly the record's files (hard links) with their rows and the
"missing" marks of the folders it touches, never links a file written in place (a database, a lock, LAYOUT) whatever
names it and checks so after the build, refuses a name not relative to the cache and a file the real cache no longer
holds (or holds with other bytes), copies nothing silently, blocks the network (http and https, over the user's own
proxy variables) and the keys, and removes its scratch folder whatever stops it, without following a junction or
changing a shared attribute."""

import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import cache  # noqa: E402
import coast  # noqa: E402
import record_check as rc  # noqa: E402

EDITION = "2026-10-23"
WORLD = f"osm/water-polygons/{EDITION}/water-polygons-split-4326"
REVERSE = {"lat": 1.0, "lon": 2.0, "format": "jsonv2", "zoom": 3}


def _drop_link(link):
    """Remove a folder link a test made (regression.link: a junction on Windows, a symbolic link elsewhere, which
    os.rmdir refuses: "Not a directory")."""
    os.rmdir(link) if os.name == "nt" else os.unlink(link)


def _write(root, name, data: bytes) -> str:
    path = os.path.join(root, *name.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def _row(root, top, inner, status="ok", sha=None):
    db = cache._connect(root, top)
    with db:
        db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (inner, status, "https://example.invalid/x", "2026-11-01T00:00:00+00:00", None, None, None, None,
                    sha, None, 1))
    db.close()


@pytest.fixture
def real(tmp_path):
    """A real cache: land/dtm a.tif (recorded) and b.tif (not), c.tif "missing" there, d.tif "missing" in a folder
    the record does not touch; a stored index answer and a database below land/sheet-index; the world file of
    EDITION and an older one; Nominatim's answers X (recorded) and Y, two reverse lookups."""
    root = str(tmp_path / "real")
    os.makedirs(root)
    cache.check_layout(root)
    sums = {"a": _write(root, "land/dtm/a.tif", b"a-bytes"), "b": _write(root, "land/dtm/b.tif", b"b-bytes")}
    _row(root, "land", "dtm/a.tif", sha=sums["a"])
    _row(root, "land", "dtm/b.tif", sha=sums["b"])
    _row(root, "land", "dtm/c.tif", status="missing")
    _row(root, "land", "other/d.tif", status="missing")
    _write(root, "land/sheet-index/p/N1.json", b'{"sheets": []}')
    _row(root, "land", "sheet-index/p/N1.json")
    _write(root, "land/sheet-index/p/rate.sqlite", b"not a copy")
    for name in ("water_polygons.shp", "water_polygons.dbf"):
        _write(root, f"{WORLD}/{name}", b"world")
        _row(root, "osm", f"water-polygons/{EDITION}/water-polygons-split-4326/{name}")
    _write(root, "osm/water-polygons/2025-01-01/water-polygons-split-4326/water_polygons.shp", b"old")
    import osm
    db = osm._nominatim_db(root)
    with db:
        db.execute("INSERT INTO search VALUES (?, ?, ?)", ("X", '{"answer": "x"}', "2026-11-01"))
        db.execute("INSERT INTO search VALUES (?, ?, ?)", ("Y", '{"answer": "y"}', "2026-11-01"))
        db.execute("INSERT INTO reverse VALUES (?, ?, ?)", (json.dumps(REVERSE, sort_keys=True), "{}", "2026-11-01"))
        db.execute("INSERT INTO reverse VALUES (?, ?, ?)", (json.dumps({**REVERSE, "lat": 1.5}, sort_keys=True), "{}",
                                                            "2026-11-01"))
        db.execute("INSERT INTO reverse VALUES (?, ?, ?)", ("not json", "{}", "2026-11-01"))
    db.close()
    sums["X"] = hashlib.sha256('{"answer": "x"}'.encode("utf-8")).hexdigest()
    return root, sums


def _meta(sums) -> dict:
    """A run.json of a search that read land/dtm/a.tif, the world file and Nominatim's X."""
    return {"data": [{"layer": "DTM", "folder": "land/dtm", "paths": ["land/dtm/a.tif"],
                      "identity": {"sha256": [sums["a"]]}},
                     {"layer": coast.SOURCE_WORLD, "identity": {"edition": EDITION}}],
            "area": {"type": "polygon", "geometry": {"type": "Point", "coordinates": [0, 0]},
                     "identity": {"paths": [], "sha256": [],
                                  "nominatim": [{"table": "search", "query": "X", "sha256": sums["X"]}]}},
            "source": {"id": "land"}, "identity": {"v": 1, "gdal": "g", "proj": "p", "rasterio": "r"}}


def _rows(root, top):
    db = sqlite3.connect(os.path.join(root, top, "index.sqlite"))
    try:
        return {row[0]: row[1] for row in db.execute("SELECT path, status FROM files")}
    finally:
        db.close()


def _all_files(root):
    return sorted(os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/")
                  for d, _, names in os.walk(root) for n in names)


def _snapshot(root) -> dict:
    """Every file of a folder: its size, modification time and bytes' sha256."""
    found = {}
    for name in _all_files(root):
        path = os.path.join(root, *name.split("/"))
        st = os.stat(path)
        with open(path, "rb") as f:
            found[name] = (st.st_size, st.st_mtime_ns, hashlib.sha256(f.read()).hexdigest())
    return found


def _stub(tmp_path, lock, sums, seen, outcome="ok"):
    """The harness stubbed: what the scratch cache holds noted, a run log line, a log folder with a junction."""
    def run(entry, scratch, env):
        seen["files"] = _all_files(scratch)
        seen["land"], seen["osm"] = _rows(scratch, "land"), _rows(scratch, "osm")
        db = sqlite3.connect(os.path.join(scratch, "osm", "nominatim.sqlite"))
        seen["answers"] = [q for (q,) in db.execute("SELECT query FROM search")]
        db.close()
        root = seen["root"]
        seen["linked"] = os.path.samefile(os.path.join(scratch, "land", "dtm", "a.tif"),
                                          os.path.join(root, "land", "dtm", "a.tif"))
        seen["env"] = env
        work = Path(env["TEMP"]) / "findaline-regression-stub"  # the harness's mkdtemp, in the TEMP it was given
        (work / entry / "runs" / "run").mkdir(parents=True)
        (work / entry / "runs" / "run" / "run.json").write_text(json.dumps(_meta(sums)), encoding="utf-8")
        (work / entry / "output.log").write_text("Data: land\nWARNING: something tried\n", encoding="utf-8")
        rc.regression.link(root, str(work / entry / "cache"))  # as the harness links its cache
        line = {"cache": scratch, "entries": {entry: {"outcome": outcome, "reason": None, "data": "same",
                                                      "hosts": {}, "tiles": {"downloaded": 0, "cached": 1}}}}
        with open(lock / rc.regression.RUN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return subprocess.CompletedProcess([], 0, f"E: {outcome}\n\n1 ok, 0 different, 0 unverified, 0 skipped; "
                                                  f"logs in {work}\n", "")
    return run


@pytest.fixture
def lock(tmp_path, monkeypatch):
    folder = tmp_path / "locks"
    folder.mkdir()
    monkeypatch.setenv("FINDALINE_TEST_LOCK_DIR", str(folder))
    return folder


def test_the_scratch_cache_holds_only_the_record(real, tmp_path, monkeypatch, lock):
    """One entry end to end, the harness stubbed: exactly the record's files linked, their rows and the "missing"
    marks of the touched folder, Nominatim's recorded answer only; the network and the keys blocked; ok from the
    run log's line; the scratch folder and the harness's log folder removed, its junction to the real cache not
    followed; nothing of the real cache changed."""
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "the-real-key")
    monkeypatch.setenv("ESRI_API_KEY", "another-real-key")
    monkeypatch.setenv("FINDALINE_MIRROR", str(tmp_path / "the-real-mirror"))
    out = rc.prepare_out(str(tmp_path / "out"), root)
    before = _snapshot(root)
    seen = {"root": root}
    said = []
    tests = {"E": {"args": "--lat 0 --lon 0"}}
    ok, left = rc.check_entry("E", tests, {"E": record}, root, out, (), False, False,
                              run=_stub(tmp_path, lock, sums, seen), say=said.append)
    assert ok and left == []
    world = [f"{WORLD}/water_polygons.dbf", f"{WORLD}/water_polygons.shp"]
    assert seen["files"] == sorted(["LAYOUT", "land/dtm/a.tif", "land/index.sqlite", "osm/index.sqlite",
                                    "osm/nominatim.sqlite"] + world)
    assert seen["linked"]
    assert seen["land"] == {"dtm/a.tif": "ok", "dtm/c.tif": "missing"}  # not b (unrecorded), not d (untouched)
    assert set(seen["osm"]) == {name.partition("/")[2] for name in world}
    assert seen["answers"] == ["X"]
    env = seen["env"]
    assert env["HTTPS_PROXY"] == rc.DEAD and env["HTTP_PROXY"] == rc.DEAD and env["NO_PROXY"] == ""
    assert env["OPENTOPOGRAPHY_API_KEY"] == rc.DUMMY and env["DATAFORDELER_API_KEY"] == rc.DUMMY
    assert "ESRI_API_KEY" not in {k.upper() for k in env} and "FINDALINE_MIRROR" not in {k.upper() for k in env}
    assert "the-real-key" not in json.dumps(env)
    text = "\n".join(said)
    assert ("1 files checked against the record's checksum, 0 without a checksum in the record (linked unchecked), 2 "
            "of the world file taken by its edition's name, not by their bytes") in text
    assert "verdict: ok" in text and "LAYOUT" in text and '1 "missing" marks (land/dtm 1)' in text
    assert "the run's own record names the same data" in text and "first: WARNING: something tried" in text
    assert env["TEMP"] == os.path.join(out, "E", "tmp")
    assert os.listdir(out) == [rc.MARKER]  # the scratch cache and the harness's log folder with its junction
    assert _snapshot(root) == before
    rc.remove_tree(out)
    assert not os.path.exists(out)


def test_not_ok_without_the_run_logs_same_data():
    """An ok outcome whose data were not the record's, or that downloaded a tile, is not ok."""
    ok, words, _ = rc.verdict({"entries": {"E": {"outcome": "ok", "data": "differs", "tiles": {"downloaded": 0}}}},
                              "E")
    assert not ok and "data differs" in words
    ok, words, _ = rc.verdict({"entries": {"E": {"outcome": "ok", "data": "same", "tiles": {"downloaded": 2}}}}, "E")
    assert not ok and "2 tiles downloaded" in words
    assert rc.verdict(None, "E")[0] is False


def test_log_line_takes_this_runs_line(tmp_path):
    """The line after the start offset whose cache is this scratch cache: not an older line of the same cache, not a
    line of another cache appended after it."""
    scratch = str(tmp_path / "out" / "E" / "cache")
    os.makedirs(scratch)
    log = tmp_path / "runs.jsonl"
    log.write_text(json.dumps({"cache": scratch, "entries": {"E": {"outcome": "ok"}}}) + "\n", encoding="utf-8")
    start = os.path.getsize(log)
    mine = {"cache": scratch, "entries": {"E": {"outcome": "different"}}}
    other = {"cache": str(tmp_path / "elsewhere"), "entries": {"E": {"outcome": "ok"}}}
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(mine) + "\n" + json.dumps(other) + "\n")
    assert rc.log_line(str(log), start, scratch) == mine
    assert rc.log_line(str(log), start, str(tmp_path / "nothing")) is None
    assert rc.log_line(str(tmp_path / "no-log"), 0, scratch) is None


def test_a_file_gone_from_the_real_cache_is_named(real, tmp_path):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"]["land/dtm/gone.tif"] = None
    scratch = str(tmp_path / "scratch" / "cache")
    with pytest.raises(rc.RecordError, match="land/dtm/gone.tif"):
        rc.build(record, root, scratch)
    assert not os.path.exists(scratch)  # nothing placed before the check


def test_another_checksum_in_the_index_is_an_error(real, tmp_path):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"]["land/dtm/a.tif"] = "0" * 64
    with pytest.raises(rc.RecordError, match="index holds another checksum"):
        rc.build(record, root, str(tmp_path / "s1"))


def test_other_bytes_under_a_right_index_row_are_an_error(real, tmp_path):
    """The file replaced by hand: the index row still agrees with the record, the bytes do not."""
    root, sums = real
    _write(root, "land/dtm/a.tif", b"other bytes")
    scratch = str(tmp_path / "s1")
    with pytest.raises(rc.RecordError, match="land/dtm/a.tif: the real cache's file differs"):
        rc.build(rc.regression.record_of(_meta(sums)), root, scratch)
    assert not os.path.exists(scratch)


def test_a_gone_edition_and_a_link_in_the_world_folder_are_errors(real, tmp_path):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["coastline"] = {"edition": "2020-01-01"}
    with pytest.raises(rc.RecordError, match="2020-01-01"):
        rc.build(record, root, str(tmp_path / "s2"))
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = os.path.join(root, *WORLD.split("/"), "linked")
    rc.regression.link(str(target), link)
    try:
        with pytest.raises(rc.RecordError, match="is a link"):
            rc.world_files(root, EDITION)
    finally:
        _drop_link(link)


@pytest.mark.parametrize("name", ["../land/dtm/a.tif", "/land/dtm/a.tif", "C:/real/land/dtm/a.tif",
                                  "land\\dtm\\a.tif", "land//dtm/a.tif"])
def test_a_name_not_relative_to_the_cache_is_refused(real, tmp_path, name):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"][name] = None
    with pytest.raises(rc.RecordError, match="not relative to the cache"):
        rc.build(record, root, str(tmp_path / "scratch"))


IN_PLACE_NAMES = ["land/index.sqlite", "land/INDEX.SQLITE", "land/index.sqlite.", "land/index.sqlite ",
                  "land/index.sqlite-wal", "land/index.SQLITE-shm", "osm/nominatim.sqlite", "osm/Nominatim.Sqlite",
                  "LAYOUT", "layout", "locks/tiles/1.lock", "land/dtm/a.tif.part", "land/sheet-index/p/N1.json.retry"]


@pytest.mark.parametrize("name", IN_PLACE_NAMES)
def test_a_file_written_in_place_is_never_linked(real, tmp_path, name):
    """A database (any letter case, a trailing dot or space as Windows reads it), its side files, LAYOUT, a lock, a
    .part, a .retry marker: refused by --also, by a record naming it and by place_file itself, and nothing of the real
    cache changes (a link would let the scratch cache's writes reach it)."""
    root, sums = real
    before = _snapshot(root)
    scratch = str(tmp_path / "out" / "E" / "cache")
    with pytest.raises(rc.RecordError, match="written in place"):
        rc.build(rc.regression.record_of(_meta(sums)), root, scratch, also=[name])
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"][name] = None
    if rc.regression.cache_name(name):
        with pytest.raises(rc.RecordError, match="written in place"):
            rc.build(record, root, scratch)
    with pytest.raises(rc.RecordError, match="written in place"):
        rc.place_file(root, scratch, name)
    assert not os.path.exists(scratch)
    assert _snapshot(root) == before


def test_main_refuses_also_naming_a_database(monkeypatch):
    monkeypatch.setattr(rc, "check_block", lambda env: pytest.fail("asked the block before refusing"))
    with pytest.raises(SystemExit) as e:
        rc.main(["R1", "--also", "poland/index.SQLITE"])
    assert e.value.code == 2


@pytest.mark.parametrize("keep", [False, True])
def test_a_database_shared_after_the_build_stops_the_entry(real, tmp_path, monkeypatch, lock, keep):
    """The check after the build: a scratch index that is the real one (however it came there) is found, the entry
    is not run, its scratch folder removed whatever --keep says, and the real cache unchanged."""
    root, sums = real
    build = rc.build

    def build_and_link(*args, **kwargs):
        built = build(*args, **kwargs)
        scratch = args[2]
        os.remove(os.path.join(scratch, "land", "index.sqlite"))
        os.link(os.path.join(root, "land", "index.sqlite"), os.path.join(scratch, "land", "index.sqlite"))
        return built
    monkeypatch.setattr(rc, "build", build_and_link)
    out = rc.prepare_out(str(tmp_path / "out"), root)
    before = _snapshot(root)
    assert rc.shared_with_real(root, str(tmp_path / "nothing")) == []
    with pytest.raises(rc.RecordError, match="land/index.sqlite"):
        rc.check_entry("E", {"E": {"args": ""}}, {"E": rc.regression.record_of(_meta(sums))}, root, out, (), False,
                       keep, run=lambda *a: pytest.fail("ran the entry"), say=lambda *a: None)
    assert not os.path.exists(os.path.join(out, "E"))
    assert _snapshot(root) == before


def test_the_tools_own_writes_never_go_into_a_shared_database(real, tmp_path):
    """copy_rows and copy_answers refuse a scratch database that is a link of the real one before opening it (the
    check after the build is the second line); the real cache unchanged."""
    root, sums = real
    before = _snapshot(root)
    scratch = str(tmp_path / "s" / "cache")
    for name in ("land/index.sqlite", "osm/nominatim.sqlite"):
        os.makedirs(os.path.dirname(os.path.join(scratch, *name.split("/"))), exist_ok=True)
        os.link(os.path.join(root, *name.split("/")), os.path.join(scratch, *name.split("/")))
    with pytest.raises(rc.RecordError, match="land/index.sqlite is shared"):
        rc.copy_rows(root, scratch, ["land/dtm/a.tif"], ["land/dtm"])
    with pytest.raises(rc.RecordError, match="osm/nominatim.sqlite is shared"):
        rc.copy_answers(root, scratch, {"search": {"X": sums["X"]}})
    assert rc.shared_with_real(root, scratch) == ["land/index.sqlite", "osm/nominatim.sqlite"]
    assert _snapshot(root) == before


def _short_name(path: str):
    """The 8.3 short name of a path where the volume makes one, else None."""
    if os.name != "nt":
        return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 1024)
    short = os.path.basename(buffer.value) if n else None
    return short if short and short.lower() != os.path.basename(path).lower() else None


def test_place_file_refuses_a_database_by_its_resolved_path(real, tmp_path):
    """Names that do not look like a database but resolve to one: refused by place_file's second check (the path
    resolved), never linked."""
    root, _ = real
    names = ["land/index.sqlite/."]
    short = _short_name(os.path.join(root, "land", "index.sqlite"))
    if short:
        names.append(f"land/{short}")
    scratch = str(tmp_path / "s")
    for name in names:
        assert rc.regression.cache_name(name) and not rc.written_in_place(name)
        with pytest.raises(rc.RecordError, match="written in place"):
            rc.place_file(root, scratch, name)
    assert not os.path.exists(scratch)


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyboardInterrupt()])
@pytest.mark.parametrize("keep", [False, True])
def test_whatever_stops_an_entry_its_folder_and_the_harness_logs_go(real, tmp_path, lock, error, keep):
    """The harness stopped mid-run, its log folder made in the TEMP it was given (with its junction to the scratch
    cache): the entry's folder, the harness's log folder inside it, is removed, or with --keep kept and named; the
    real cache untouched."""
    root, sums = real
    out = rc.prepare_out(str(tmp_path / "out"), root)
    before = _snapshot(root)

    def run(entry, scratch, env):
        work = Path(env["TEMP"]) / "findaline-regression-x" / entry
        work.mkdir(parents=True)
        rc.regression.link(scratch, str(work / "cache"))
        (work / "output.log").write_text("half a search", encoding="utf-8")
        raise error
    said = []
    with pytest.raises(type(error)):
        rc.check_entry("E", {"E": {"args": ""}}, {"E": rc.regression.record_of(_meta(sums))}, root, out, (), False,
                       keep, run=run, say=said.append)
    if keep:
        assert f"    kept: {os.path.join(out, 'E')}" in said
        assert os.path.isdir(os.path.join(out, "E", "tmp", "findaline-regression-x"))
        assert rc.remove_tree(out) == []
    else:
        assert os.listdir(out) == [rc.MARKER]
    assert _snapshot(root) == before


def test_a_stopped_harness_ends_its_whole_process_tree(tmp_path, monkeypatch):
    """run_harness on Ctrl+C: the harness and the process below it (the search) are ended before it passes on."""
    import psutil
    pids = tmp_path / "pids.txt"
    child = f"import os, time; open(r'{pids}', 'a').write(str(os.getpid()) + chr(10)); time.sleep(120)"
    parent = (f"import os, subprocess, sys, time; open(r'{pids}', 'a').write(str(os.getpid()) + chr(10)); "
              f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(120)")
    monkeypatch.setattr(rc, "harness_command", lambda entry, scratch: [sys.executable, "-c", parent])
    original = subprocess.Popen.communicate

    def interrupted(self, *args, **kwargs):
        deadline = time.time() + 60
        while time.time() < deadline and (not pids.exists() or len(pids.read_text().split()) < 2):
            time.sleep(0.1)
        raise KeyboardInterrupt
    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        rc.run_harness("E", "scratch", dict(os.environ))
    monkeypatch.setattr(subprocess.Popen, "communicate", original)
    found = [int(p) for p in pids.read_text().split()]
    assert len(found) == 2
    assert not any(psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE for pid in found)
    monkeypatch.setattr(rc, "harness_command", lambda entry, scratch: [sys.executable, "-c", "print('done')"])
    done = rc.run_harness("E", "scratch", dict(os.environ))
    assert done.returncode == 0 and done.stdout.strip() == "done"


@pytest.fixture
def main_env(real, tmp_path, monkeypatch):
    """main on the canned real cache, the block taken as holding."""
    root, _ = real
    monkeypatch.setattr(rc, "check_block", lambda env: {})
    monkeypatch.setattr(rc.regression, "real_cache_dir", lambda: root)
    return str(tmp_path / "out")


@pytest.mark.parametrize("outcome, code", [((True, []), 0), ((False, []), 1), ((True, ["x"]), 3),
                                           (rc.RecordError("refused"), 1), (OSError("disk"), 1),
                                           (KeyboardInterrupt(), 1)])
def test_main_exit_codes_and_the_out_folder_removed(main_env, monkeypatch, capsys, outcome, code):
    def check(*args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    monkeypatch.setattr(rc, "check_entry", check)
    assert rc.main(["R1", "R2", "--out", main_env]) == code
    assert not os.path.exists(main_env)
    if code == 1 and isinstance(outcome, BaseException):
        assert "not checked" in capsys.readouterr().out


@pytest.mark.parametrize("ids", [["R999"], ["R17"], ["R70"]])
def test_main_refuses_an_entry_without_a_record(monkeypatch, ids):
    monkeypatch.setattr(rc, "check_block", lambda env: pytest.fail("asked the block before refusing"))
    with pytest.raises(SystemExit) as e:
        rc.main(ids)
    assert e.value.code == 2


def test_main_stops_before_any_entry_when_the_block_does_not_hold(real, tmp_path, monkeypatch):
    root, _ = real
    monkeypatch.setattr(rc, "check_block", lambda env: {"gdal https": "answered"})
    monkeypatch.setattr(rc.regression, "real_cache_dir", lambda: root)
    monkeypatch.setattr(rc, "check_entry", lambda *a, **k: pytest.fail("ran an entry"))
    with pytest.raises(SystemExit) as e:
        rc.main(["R1", "--out", str(tmp_path / "out")])
    assert e.value.code == 2 and not os.path.exists(tmp_path / "out")


def test_the_harness_command_never_seeds_or_updates(monkeypatch):
    command = rc.harness_command("R1", "C:/scratch/cache")
    assert command[1].endswith(os.path.join("tests", "regression.py")) and command[2:5] == ["R1", "--cache",
                                                                                          "C:/scratch/cache"]
    assert {"--cold", "--no-seed", "--keep"} <= set(command)
    assert not {"--update", "--update-data", "--all", "--set"} & set(command)
    calls = []

    class NoProcess:  # never a real process: the harness on a made-up cache must not start
        returncode = 0

        def __init__(self, args, **kw):
            calls.append((args, kw))

        def communicate(self):
            return "", ""
    monkeypatch.setattr(rc.subprocess, "Popen", NoProcess)
    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **k: pytest.fail("a process started"))
    rc.run_harness("R1", "C:/scratch/cache", {"X": "1"})
    assert calls[0][0] == command and calls[0][1]["env"] == {"X": "1"}


def test_nothing_is_copied_silently(real, tmp_path, monkeypatch):
    """Another volume: refused before anything is placed, with the size it would copy; --copy copies. A link that
    fails (a path too long, too many links) names the file; --copy copies it."""
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    monkeypatch.setattr(rc, "_volume", lambda path: 1 if os.path.abspath(path).startswith(root) else 2)
    scratch = str(tmp_path / "s1")
    with pytest.raises(rc.RecordError, match="another volume.*MB would be copied"):
        rc.build(record, root, scratch)
    assert not os.path.exists(scratch)
    monkeypatch.setattr(rc, "_volume", lambda path: 1)

    def no_link(source, target):
        raise OSError(206, "The filename or extension is too long")
    monkeypatch.setattr(rc.os, "link", no_link)
    with pytest.raises(rc.RecordError, match="land/dtm/a.tif cannot be linked"):
        rc.place_file(root, str(tmp_path / "s2"), "land/dtm/a.tif")
    assert rc.place_file(root, str(tmp_path / "s3"), "land/dtm/a.tif", copy=True) == "copied"
    copied = os.path.join(tmp_path, "s3", "land", "dtm", "a.tif")
    assert not os.path.samefile(copied, os.path.join(root, "land", "dtm", "a.tif"))


def test_files_below_and_reverse_answers(real):
    """--also: a folder's files without its databases (counted), one file, a link or a gone name refused; --reverse:
    the stored reverse lookups of the point only."""
    root, _ = real
    assert rc._files_below(root, "land/sheet-index") == (["land/sheet-index/p/N1.json"], 1)
    assert rc._files_below(root, "land/sheet-index/p/N1.json") == (["land/sheet-index/p/N1.json"], 0)
    with pytest.raises(rc.RecordError, match="not in the real cache"):
        rc._files_below(root, "land/nothing")
    with pytest.raises(rc.RecordError, match="written in place"):
        rc._files_below(root, "land/sheet-index/p/rate.sqlite")
    link = os.path.join(root, "land", "alias")
    rc.regression.link(os.path.join(root, "land", "dtm"), link)
    try:
        with pytest.raises(rc.RecordError, match="is a link"):
            rc._files_below(root, "land/alias")
    finally:
        _drop_link(link)
    assert rc.reverse_answers(root, 1.0, 2.0) == {"reverse": {json.dumps(REVERSE, sort_keys=True): None}}
    assert rc.reverse_answers(root, 9.0, 9.0) == {}


def test_a_nominatim_answer_not_the_records_is_an_error(real, tmp_path):
    root, _ = real
    scratch = str(tmp_path / "s")
    with pytest.raises(rc.RecordError, match="differs from the record's"):
        rc.copy_answers(root, scratch, {"search": {"X": "0" * 64}})
    with pytest.raises(rc.RecordError, match="not in the real cache"):
        rc.copy_answers(root, scratch, {"search": {"Z": None}})
    assert not os.path.exists(os.path.join(scratch, "osm", "nominatim.sqlite"))


def test_unchanged_names_a_real_file_that_moved(real):
    root, _ = real
    path = os.path.join(root, "land", "dtm", "a.tif")
    st = os.stat(path)
    placed = {"land/dtm/a.tif": (st.st_size, st.st_mtime_ns), "land/dtm/gone.tif": (1, 1)}
    assert rc.unchanged(root, placed) == ["land/dtm/gone.tif"]
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
    assert rc.unchanged(root, placed) == ["land/dtm/a.tif", "land/dtm/gone.tif"]


def test_record_words_name_what_differs(real):
    _, sums = real
    stored = rc.regression.record_of(_meta(sums))
    assert rc.record_words(stored, None) == "the run made no run.json"
    other = json.loads(json.dumps(stored))
    other["source"] = "elsewhere"
    assert rc.record_words(stored, other).startswith("the run's own record differs in source (the source")


def test_out_is_never_the_real_cache_or_a_folder_of_others(real, tmp_path):
    root, _ = real
    for out in (root, os.path.join(root, "land"), str(tmp_path)):
        with pytest.raises(rc.RecordError):
            rc.prepare_out(out, root)
    to_real = str(tmp_path / "to-real")
    rc.regression.link(root, to_real)
    try:
        for out in (to_real, os.path.join(to_real, "new")):
            with pytest.raises(rc.RecordError, match="real cache"):
                rc.prepare_out(out, root)
    finally:
        _drop_link(to_real)
    other = tmp_path / "other"
    other.mkdir()
    (other / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(rc.RecordError):
        rc.prepare_out(str(other), root)
    assert not os.path.exists(os.path.join(root, rc.MARKER))


def test_remove_tree_removes_links_as_links(tmp_path):
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "file.txt").write_text("x", encoding="utf-8")
    gone = tmp_path / "gone"
    (gone / "sub").mkdir(parents=True)
    rc.regression.link(str(keep), str(gone / "sub" / "link"))
    os.link(keep / "file.txt", gone / "hard.txt")
    assert rc.remove_tree(str(gone)) == []
    assert not gone.exists() and (keep / "file.txt").read_text(encoding="utf-8") == "x"


@pytest.mark.skipif(os.name != "nt", reason="the read-only attribute shared by hard links: Windows")
def test_a_read_only_link_is_deleted_without_changing_the_attribute(tmp_path, monkeypatch):
    """The real file's read-only attribute is shared with its link: the link is deleted by the delete that ignores
    it, the attribute never cleared; where that delete fails the link is left and named."""
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "f.tif").write_bytes(b"x")
    os.chmod(keep / "f.tif", stat.S_IREAD)
    try:
        gone = tmp_path / "gone"
        gone.mkdir()
        os.link(keep / "f.tif", gone / "f.tif")
        assert rc.remove_tree(str(gone)) == []
        assert not gone.exists() and (keep / "f.tif").read_bytes() == b"x"
        assert os.stat(keep / "f.tif").st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        gone.mkdir()
        os.link(keep / "f.tif", gone / "f.tif")
        monkeypatch.setattr(rc, "delete_ignoring_read_only", lambda path: False)
        assert rc.remove_tree(str(gone)) == [str(gone / "f.tif")]
        assert (gone / "f.tif").exists()
        assert os.stat(keep / "f.tif").st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        monkeypatch.undo()
        assert rc.remove_tree(str(gone)) == [] and not gone.exists()
    finally:
        os.chmod(keep / "f.tif", stat.S_IREAD | stat.S_IWRITE)


def test_the_mirror_stand_in_holds_needs_path_and_recorded_resolutions(tmp_path):
    """Empty folders only: the entry's needs_path and the mirror folder of a recorded tiled layer's resolution."""
    record = {"folders": {"slovakia/dmr5/5.0/epsg8353-1m-2km": {"files": {}, "layers": []}}}
    made = rc.mirror_stand_in(record, {"needs_path": ["madeira/dtm/2m"]}, str(tmp_path / "mirror"))
    assert made == ["madeira/dtm/2m", "slovakia/dmr5/1m"]
    assert _all_files(str(tmp_path / "mirror")) == []


USERS_PROXIES = {"GDAL_HTTPS_PROXY": "http://proxy.example:3128", "no_proxy": "*", "https_proxy": "http://p.example:1",
                 "Http_Proxy": "http://p.example:2", "GDAL_HTTP_PROXYUSERPWD": "user:secret", "REQUEST_METHOD": "GET",
                 "FINDALINE_OVERPASS_URL": "https://overpass.example/api", "PATH": os.environ.get("PATH", ""),
                 "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}


def test_block_env_overrides_the_users_proxy_variables():
    env = rc.block_env(USERS_PROXIES)
    proxies = {k: v for k, v in env.items() if "PROXY" in k.upper()}
    expected = dict(rc.PROXIES) if os.name == "nt" else {**rc.PROXIES, **{k.lower(): v for k, v in rc.PROXIES.items()}}
    assert proxies == expected
    assert "REQUEST_METHOD" not in {k.upper() for k in env}
    assert env["FINDALINE_OVERPASS_URL"].startswith(rc.DEAD)
    assert "secret" not in json.dumps(env) and "example" not in json.dumps(env)


def test_the_block_check_counts_only_the_dead_ports_refusal(monkeypatch):
    """A refusal by another local port (a proxy that is not the dead one) is no block, for each client and scheme;
    an answer, another text or a client not asked is named."""
    env = rc.block_env()
    for name in list(env):
        if "PROXY" in name.upper() and env[name]:
            env[name] = env[name].replace("127.0.0.1:9", "127.0.0.1:8")
    every = {f"{client} {scheme}" for client in ("requests", "urllib", "gdal") for scheme in ("http", "https")}
    assert set(rc.check_block(env)) == every
    canned = {key: "blocked" for key in every - {"gdal https"}}
    canned["urllib http"] = "answered"
    monkeypatch.setattr(rc.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps(canned) + "\n", ""))
    assert rc.check_block({}) == {"urllib http": "answered", "gdal https": "not asked"}


def test_the_block_holds_for_http_and_https_over_the_users_proxies():
    """requests, urllib and GDAL's /vsicurl/ all stop at the dead port, over http and https, under block_env of the
    process's environment and of one whose own proxy variables would let GDAL out (no request leaves)."""
    assert rc.check_block(rc.block_env()) == {}
    assert rc.check_block(rc.block_env({**os.environ, **USERS_PROXIES})) == {}
