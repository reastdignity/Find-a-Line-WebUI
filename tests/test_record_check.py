"""tools/record_check.py, the completeness check of the data record: offline, on a canned real cache and a canned
record, the harness's run stubbed. It places exactly the record's files (hard links) with their rows and the
"missing" marks of the folders it touches, refuses a name not relative to the cache and a file the real cache no
longer holds (or holds with other bytes), blocks the network and the keys, and removes its scratch folder without
following a junction."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import cache  # noqa: E402
import coast  # noqa: E402
import record_check as rc  # noqa: E402

EDITION = "2026-10-23"
WORLD = f"osm/water-polygons/{EDITION}/water-polygons-split-4326"


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
    the record does not touch; the world file of EDITION and an older one; Nominatim's answers X (recorded) and Y."""
    root = str(tmp_path / "real")
    os.makedirs(root)
    cache.check_layout(root)
    sums = {"a": _write(root, "land/dtm/a.tif", b"a-bytes"), "b": _write(root, "land/dtm/b.tif", b"b-bytes")}
    _row(root, "land", "dtm/a.tif", sha=sums["a"])
    _row(root, "land", "dtm/b.tif", sha=sums["b"])
    _row(root, "land", "dtm/c.tif", status="missing")
    _row(root, "land", "other/d.tif", status="missing")
    for name in ("water_polygons.shp", "water_polygons.dbf"):
        _write(root, f"{WORLD}/{name}", b"world")
        _row(root, "osm", f"water-polygons/{EDITION}/water-polygons-split-4326/{name}")
    _write(root, "osm/water-polygons/2025-01-01/water-polygons-split-4326/water_polygons.shp", b"old")
    import osm
    db = osm._nominatim_db(root)
    with db:
        db.execute("INSERT INTO search VALUES (?, ?, ?)", ("X", '{"answer": "x"}', "2026-11-01"))
        db.execute("INSERT INTO search VALUES (?, ?, ?)", ("Y", '{"answer": "y"}', "2026-11-01"))
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


def test_the_scratch_cache_holds_only_the_record(real, tmp_path, monkeypatch):
    """One entry end to end, the harness stubbed: exactly the record's files linked, their rows and the "missing"
    marks of the touched folder, Nominatim's recorded answer only; the network and the keys blocked; ok from the
    run log's line; the scratch folder and the harness's log folder removed, its junction to the real cache not
    followed."""
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    lock = tmp_path / "locks"
    lock.mkdir()
    monkeypatch.setenv("FINDALINE_TEST_LOCK_DIR", str(lock))
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "the-real-key")
    monkeypatch.setenv("ESRI_API_KEY", "another-real-key")
    monkeypatch.setenv("FINDALINE_MIRROR", str(tmp_path / "the-real-mirror"))
    out = rc.prepare_out(str(tmp_path / "out"), root)
    seen = {}

    def run(entry, scratch, env):
        seen["files"] = _all_files(scratch)
        seen["land"], seen["osm"] = _rows(scratch, "land"), _rows(scratch, "osm")
        db = sqlite3.connect(os.path.join(scratch, "osm", "nominatim.sqlite"))
        seen["answers"] = [q for (q,) in db.execute("SELECT query FROM search")]
        db.close()
        seen["linked"] = os.path.samefile(os.path.join(scratch, "land", "dtm", "a.tif"),
                                          os.path.join(root, "land", "dtm", "a.tif"))
        seen["env"] = env
        work = tmp_path / "findaline-regression-stub"
        (work / entry / "runs" / "run").mkdir(parents=True)
        (work / entry / "runs" / "run" / "run.json").write_text(json.dumps(_meta(sums)), encoding="utf-8")
        (work / entry / "output.log").write_text("Data: land\nWARNING: something tried\n", encoding="utf-8")
        rc.regression.link(root, str(work / entry / "cache"))  # as the harness links its cache
        line = {"cache": scratch, "entries": {entry: {"outcome": "ok", "reason": None, "data": "same",
                                                      "hosts": {}, "tiles": {"downloaded": 0, "cached": 1}}}}
        with open(lock / rc.regression.RUN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"cache": "elsewhere", "entries": {}}) + "\n" + json.dumps(line) + "\n")
        return subprocess.CompletedProcess([], 0, f"E: ok\n\n1 ok, 0 different, 0 unverified, 0 skipped; logs in "
                                                  f"{work}\n", "")

    said = []
    tests = {"E": {"args": "--lat 0 --lon 0"}}
    assert rc.check_entry("E", tests, {"E": record}, root, out, (), False, False, run=run, say=said.append)
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
    assert "verdict: ok" in text and "LAYOUT" in text and '1 "missing" marks (land/dtm 1)' in text
    assert "the run's own record names the same data" in text and "first: WARNING: something tried" in text
    assert not os.path.exists(os.path.join(out, "E")) and not os.path.exists(tmp_path / "findaline-regression-stub")
    assert _all_files(root).count("land/dtm/a.tif") == 1 and os.path.isfile(os.path.join(root, WORLD,
                                                                                         "water_polygons.shp"))
    rc.remove_tree(out)
    assert not os.path.exists(out)


def test_not_ok_without_the_run_logs_same_data(real, tmp_path, monkeypatch):
    """An ok outcome whose data were not the record's, or that downloaded a tile, is not ok."""
    ok, words, _ = rc.verdict({"entries": {"E": {"outcome": "ok", "data": "differs", "tiles": {"downloaded": 0}}}},
                              "E")
    assert not ok and "data differs" in words
    ok, words, _ = rc.verdict({"entries": {"E": {"outcome": "ok", "data": "same", "tiles": {"downloaded": 2}}}}, "E")
    assert not ok and "2 tiles downloaded" in words
    assert rc.verdict(None, "E")[0] is False


def test_a_file_gone_from_the_real_cache_is_named(real, tmp_path):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"]["land/dtm/gone.tif"] = None
    scratch = str(tmp_path / "scratch" / "cache")
    with pytest.raises(rc.RecordError, match="land/dtm/gone.tif"):
        rc.build(record, root, scratch)
    assert not os.path.exists(scratch)  # nothing placed before the check


def test_other_bytes_and_a_gone_edition_are_errors(real, tmp_path):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"]["land/dtm/a.tif"] = "0" * 64
    with pytest.raises(rc.RecordError, match="land/dtm/a.tif"):
        rc.build(record, root, str(tmp_path / "s1"))
    record = rc.regression.record_of(_meta(sums))
    record["coastline"] = {"edition": "2020-01-01"}
    with pytest.raises(rc.RecordError, match="2020-01-01"):
        rc.build(record, root, str(tmp_path / "s2"))


@pytest.mark.parametrize("name", ["../land/dtm/a.tif", "/land/dtm/a.tif", "C:/real/land/dtm/a.tif",
                                  "land\\dtm\\a.tif", "land//dtm/a.tif"])
def test_a_name_not_relative_to_the_cache_is_refused(real, tmp_path, name):
    root, sums = real
    record = rc.regression.record_of(_meta(sums))
    record["folders"]["land/dtm"]["files"][name] = None
    with pytest.raises(rc.RecordError, match="not relative to the cache"):
        rc.build(record, root, str(tmp_path / "scratch"))


def test_out_is_never_the_real_cache_or_a_folder_of_others(real, tmp_path):
    root, _ = real
    for out in (root, os.path.join(root, "land")):
        with pytest.raises(rc.RecordError):
            rc.prepare_out(out, root)
    other = tmp_path / "other"
    other.mkdir()
    (other / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(rc.RecordError):
        rc.prepare_out(str(other), root)


def test_remove_tree_removes_links_as_links(tmp_path):
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "file.txt").write_text("x", encoding="utf-8")
    gone = tmp_path / "gone"
    (gone / "sub").mkdir(parents=True)
    rc.regression.link(str(keep), str(gone / "sub" / "link"))
    os.link(keep / "file.txt", gone / "hard.txt")
    rc.remove_tree(str(gone))
    assert not gone.exists() and (keep / "file.txt").read_text(encoding="utf-8") == "x"


def test_the_mirror_stand_in_holds_needs_path_and_recorded_resolutions(tmp_path):
    """Empty folders only: the entry's needs_path and the mirror folder of a recorded tiled layer's resolution."""
    record = {"folders": {"slovakia/dmr5/5.0/epsg8353-1m-2km": {"files": {}, "layers": []}}}
    made = rc.mirror_stand_in(record, {"needs_path": ["madeira/dtm/2m"]}, str(tmp_path / "mirror"))
    assert made == ["madeira/dtm/2m", "slovakia/dmr5/1m"]
    assert _all_files(str(tmp_path / "mirror")) == []


def test_the_block_holds():
    """requests, urllib and GDAL's /vsicurl/ all stop at the dead port under block_env (no request leaves)."""
    assert rc.check_block(rc.block_env()) == {}
