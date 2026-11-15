"""A run's store (linestore.py: lines.arrow, profiles.arrow; docs/line-volume/spec-store.md 1.3 and 1.7):
written and read back value for value, exported as the run's lines.csv and lines.geojson byte for byte,
its schema, and the web process that never imports it."""

import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pyarrow as pa
import pytest

import helpers as sh
import linestore
import mapping as mp
import runs as rn
from test_units import HARD_FLOATS, _batch_profiles, _fake_lines

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "tests", "data")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
               "FINDALINE_PROGRESS": "text"}
# The scaled columns of lines.arrow: (store name, the LineTable's column, its index or None, decimals, nullable)
SCALED = [c for c in linestore.COLUMNS if isinstance(c[3], int)]
FLOATS = [c for c in linestore.COLUMNS if c[3] is None]


def _storable(decimals: int, bits: int = 53) -> np.ndarray:
    """The hard floats of test_saved_text_as_before an integer of `decimals` decimals holds (finite, within
    `bits`): halves, -0.0, values that round to -0.0, the tiny and the long ones."""
    hard = np.array(HARD_FLOATS)
    return hard[np.isfinite(hard) & (np.abs(hard) * 10.0 ** decimals < 2.0 ** (bits - 1) - 1)]


def _values(lines, column, index):
    values = lines.columns[column]
    return values if index is None else values[:, index]


def _assert_read_back(lines, back):
    """Every column of the store read back as write took it: the floats bit for bit, the scaled ones as
    round(value, decimals) (runs.round_floats: what data.js shows) bit for bit, -0.0 and NaN included, in the
    integer form and in the float64 form of a column no integer holds alike."""
    for name, column, index, decimals, _ in linestore.COLUMNS:
        if column not in lines.columns:
            assert column not in back.columns, name
            continue
        got = _values(back, column, index)
        want = _values(lines, column, index)
        if decimals == "bool":
            assert got.dtype == bool and np.array_equal(got, want), name
        elif decimals == "count":
            assert np.array_equal(got, want), name
        elif decimals == "mark":  # the access mark: uint8 as the search's column
            assert got.dtype == np.uint8 and np.array_equal(got, want), name
        else:
            if decimals is not None:
                want = rn.round_floats(want, decimals)
            same = (got.view(np.int64) == np.asarray(want, dtype=np.float64).view(np.int64)) | (
                np.isnan(got) & np.isnan(want))
            assert same.all(), (name, np.flatnonzero(~same)[:5], got[~same][:5], want[~same][:5])


def _hard_lines(n: int, ends: bool, square: bool, rng, access: bool = False) -> sh.LineTable:
    """n lines of _fake_lines with the hard floats in every column (those an integer of the column's decimals
    holds in the scaled ones, NaN only where a value may miss: clrN, hmean, highPct, angles, prom, drop),
    water and filled metres at 0.1 m as the search saves them, the A-frame heights (ends), the square
    rule's count (square) and the access mark's two uint8 columns (access)."""
    lines = _fake_lines(n)
    for name in sh.PIXEL_COLUMNS:  # gone before saving (LineTable.without_pixels)
        lines.columns.pop(name)
    hard = np.array(HARD_FLOATS)
    for shift, (name, column, index, decimals, nullable) in enumerate(SCALED + FLOATS):
        if column in rn.END_COLUMNS:
            continue
        values = hard if decimals is None else _storable(decimals, 32 if name in linestore.FIXED else 53)
        if decimals is not None and nullable:
            values = np.concatenate([values, [np.nan]])
        if column in ("water_m", "filled_m"):  # lines.csv prints them as they are: the search's are at 0.1 m
            values = rn.round_floats(values, 1)
        if column in ("a1_xy", "a2_xy"):  # the grouping's coordinates stay finite (group_lines)
            values = values[np.isfinite(values) & (np.abs(values) < 1e9)]
        target = _values(lines, column, index)
        target[:len(values)] = np.roll(values, shift)
    for name in ("water_m", "filled_m"):  # _fake_lines' k / 13 at 0.1 m too
        lines.columns[name] = rn.round_floats(lines.columns[name], 1)
    if ends:
        lines.columns["lift_needed"] = np.round(rng.random(n) * 2, 3)
        lines.columns["lift_no_zone"] = lines.columns["lift_needed"] + rng.random(n) * 5
        for shift, name in enumerate(rn.END_COLUMNS):
            values = _storable(2)
            lines.columns[name][:len(values)] = np.roll(values, 3 + shift)
    if square:
        lines.columns[rn.STANDS_FOR] = rng.integers(1, 5000, n).astype(np.int64)
        lines.columns[rn.STANDS_FOR][:2] = [1, 2 ** 32 - 1]
    if access:
        for name in rn.ACCESS:
            lines.columns[name] = rng.integers(0, 3, n).astype(np.uint8)
    return lines


def _profile_dicts():
    """Two profiles of helpers.line_profile on made-up terrain: with a surface (some points without one),
    water, a filled gap, an end zone and A-frames; and terrain alone."""
    rng = np.random.default_rng(3)
    terrain = 300 + np.cumsum(rng.normal(0, 2, (60, 60)), axis=1)
    surface = terrain + rng.random((60, 60)) * 3
    surface[20:25, 10:30] = np.nan
    water, filled = np.zeros((60, 60), dtype=bool), np.zeros((60, 60), dtype=bool)
    water[30:40, :], filled[5:15, :] = True, True
    full = sh.line_profile((5, 5), (50, 40), terrain, 1.0, surface, water=water, filled=filled, end_zone=5, lift=2)
    plain = sh.line_profile((2, 50), (55, 3), terrain, 1.0)
    assert full["s"] and None in full["s"] and full["w"] and full["g"] and "zone" in full
    assert plain["s"] is None and plain["w"] is None and "zone" not in plain
    return full, plain


def _profiles(n: int, rng) -> dict:
    """The profiles of n lines: two batches interleaved by row (one with an end zone and A-frames), a third
    without a surface model, dicts of helpers.line_profile; every seventh line without one."""
    batch, zoned, bare = _batch_profiles(n, rng), _batch_profiles(n, rng), _batch_profiles(n, rng)
    zoned.zone, zoned.lift = np.round(np.minimum(5.0, rng.random(n) * 30), 1), 2.0
    bare.s = None
    profiles = {k: (zoned, batch, bare)[k % 3][k] for k in range(n) if k % 7}
    full, plain = _profile_dicts()
    profiles.update({7: full, 14: plain, n - 1: full})
    return profiles


def _meta(lines, ends: bool, square: bool, by: str, access: bool = False) -> dict:
    params = {"group_distance": 20, "group_by": by}
    if access:
        params["access"] = True
    if ends:
        params.update(end_zone=5, anchor_lift=2)
    if square:
        params["same_line_side"] = 5
    meta = {"id": "r", "name": "Żabi Koń „ß”", "created": "2026-11-15T10:00:00+00:00",
            "summary": {"lines": len(lines)}, "attribution": [], "source": {"id": "files"}, "params": params,
            "data": [{"file": "C:/a/b.tif"}], "terrain": {"km2": 0.1, "mean": float("nan")}}
    if square:
        meta["summary"]["found"] = int(lines.columns[rn.STANDS_FOR].sum())
    return meta


def _exports_match(tmp_path, folder, lines, meta):
    """export of the store == runs.save_results of the LineTable itself, CSV and GeoJSON."""
    expected = tmp_path / "expected"
    expected.mkdir(exist_ok=True)
    groups = mp.group_lines(lines, meta["params"]["group_distance"], meta["params"]["group_by"])
    text_meta = {k: v for k, v in meta.items() if k != "store"}  # the text files are written before the store
    rn.save_results(str(expected), lines, groups, text_meta, files=("lines.csv", "lines.geojson"))
    for fmt, name in linestore.EXPORTS.items():
        out = tmp_path / f"exported-{name}"
        linestore.export(str(folder), fmt, str(out))
        assert out.read_bytes() == (expected / name).read_bytes(), name
    assert not [p for p in os.listdir(tmp_path) if p.startswith(".export-")]  # its temporary folder removed


@pytest.mark.parametrize("ends, square, by, access", [(False, False, "clearance", False),
                                                      (True, False, "longest", False), (False, True, "height", False),
                                                      (True, True, "clearance", False), (False, False, "height", True),
                                                      (True, True, "longest", True)],
                         ids=["plain", "end-zone", "square", "end-zone-square", "access", "all"])
def test_store_round_trip(tmp_path, ends, square, by, access):
    """50 000 lines with the hard floats (halfway cases, NaN, nulls, -0.0 in every integer column, both end
    columns, stands_for, the access mark's uint8 columns): linestore.write, then read gives every value back
    (round(value, decimals) of the scaled ones) and the profiles as helpers.Profiles' dicts; export gives the bytes
    runs.save_results writes from the LineTable itself, CSV and GeoJSON (run.json's block "store" left out of
    "findaline")."""
    rng = np.random.default_rng(5)
    n = 50_000
    lines = _hard_lines(n, ends, square, rng, access)
    lines.profiles = _profiles(n, rng)
    meta = _meta(lines, ends, square, by, access)
    folder = tmp_path / "run"
    folder.mkdir()
    head = {"run": {"id": "r", "name": meta["name"]}, "terrain": meta["terrain"], "distance": 20}
    store = linestore.write(str(folder), lines, head)
    sizes = sum((folder / name).stat().st_size for name in linestore.FILES)
    assert store["format"] == 1 and store["lines"] == n and store["bytes"] == sizes and len(store["sha256"]) == 16
    meta["store"] = store
    with open(folder / "run.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    back, got_head = linestore.read(str(folder))
    assert json.dumps(got_head) == json.dumps(head)  # NaN as NaN
    _assert_read_back(lines, back)
    assert back.profiles == {k: sh.profile_dict(p) for k, p in lines.profiles.items()}
    zeros = json.loads(pa.ipc.open_file(str(folder / linestore.LINES_FILE)).schema.metadata[b"findaline"])
    assert {name for name, *_ in SCALED if name in zeros["negative_zero"]} == \
        {name for name, column, *_ in SCALED if column in lines.columns}  # -0.0 in every integer column
    _exports_match(tmp_path, folder, lines, meta)
    assert linestore.read(str(folder), profiles=False)[0].profiles == {}


def _clip_run(tmp_path, monkeypatch, elevation: str, surface=None, radius: float = 290):
    """A search of the clip's place saved by search.save_run into <tmp_path>/runs/clip: (the folder, its
    LineTable, the events (kind, text) the search emitted)."""
    import dataclasses
    from datetime import datetime
    import search
    from params import SearchParams
    for name, value in OFFLINE_ENV.items():
        monkeypatch.setenv(name, value)
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    values = dict(elevation_file=elevation, water="off", fill_gaps="off", northing=254608, easting=553966,
                  radius=radius, **({"surface_file": surface} if surface else {"nmpt": "off"}))
    events = []
    plan = dataclasses.replace(search.plan_search(SearchParams(**values), paths,
                                                  lambda kind, text: events.append((kind, str(text)))),
                               index_runs=False)
    lines = search.find_lines(plan, search.prepare_data(plan))
    folder = tmp_path / "runs" / "clip"
    folder.mkdir(parents=True)
    search.save_run(plan, lines, {"id": "clip", "path": str(folder), "created": datetime(2026, 11, 15, 12),
                                  "name": "clip"})
    return folder, lines.results, events


def test_store_round_trip_of_the_clip(tmp_path, monkeypatch):
    """The Żabi Koń clip (a circle with a surface model: every line's profile, of lineprofiles' batch) through
    search.save_run: the store beside the text files, its head data.js's, its lines read back as the search's
    and exported as the run's lines.csv and lines.geojson byte for byte; run.json's block "store" (written
    after the text files: lines.geojson has none)."""
    folder, results, _ = _clip_run(tmp_path, monkeypatch, os.path.join(DATA, "zabi_kon_nmt.tif"),
                                   os.path.join(DATA, "zabi_kon_nmpt.tif"))
    back, head = linestore.read(str(folder))
    _assert_read_back(results, back)
    assert len(back.profiles) == len(results) and back.profiles == {
        k: sh.profile_dict(p) for k, p in results.profiles.items()}
    text = (folder / "data.js").read_text(encoding="utf-8")
    assert head == {k: v for k, v in json.loads(text[text.index(" = {") + 3:].rstrip().rstrip(";")).items()
                    if k != "lines"}
    for fmt, name in linestore.EXPORTS.items():
        linestore.export(str(folder), fmt, str(tmp_path / name))
        assert (tmp_path / name).read_bytes() == (folder / name).read_bytes(), name
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["store"] == {"format": 1, "lines": len(results), "sha256": meta["store"]["sha256"],
                             "bytes": sum((folder / n).stat().st_size for n in linestore.FILES)}
    import hashlib
    assert meta["store"]["sha256"] == hashlib.sha256((folder / linestore.LINES_FILE).read_bytes()).hexdigest()[:16]
    assert b'"store"' not in (folder / "lines.geojson").read_bytes()


def test_store_of_values_no_integer_holds(tmp_path, monkeypatch):
    """Undeclared no-data of float32's largest value (3.4e38) in two stripes of the clip's terrain: lines
    between them have e1/e2/prom/drop near 3.4e38 (the code review's input). The run saves with its store:
    those columns float64 as they are (no `decimals`), read back as written, and the export is the run's
    lines.csv and lines.geojson byte for byte; the float64 columns hold round(value, decimals), data.js's values."""
    import rasterio
    with rasterio.open(os.path.join(DATA, "zabi_kon_nmt.tif")) as src:
        profile, z = src.profile, src.read(1)
        r, c = src.index(553966, 254608)
        k = lambda m: int(round(m / src.res[0]))  # noqa: E731
    z[r - k(40):r + k(40), c - k(60):c - k(50)] = np.float32(3.4028235e38)
    z[r - k(40):r + k(40), c + k(50):c + k(60)] = np.float32(3.4028235e38)
    profile.update(nodata=None)
    stripes = tmp_path / "stripes.tif"
    with rasterio.open(stripes, "w", **profile) as dst:
        dst.write(z, 1)
    folder, results, events = _clip_run(tmp_path, monkeypatch, str(stripes), radius=150)
    assert (results.columns["elev_a1"] > 1e38).any() and not [e for e in events if "without its store" in e[1]]
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["store"]["lines"] == len(results)
    with pa.OSFile(str(folder / linestore.LINES_FILE), "rb") as f:
        schema = pa.ipc.open_file(f).schema
    for name in ("e1", "e2"):
        assert schema.field(name).type == pa.float64() and not (schema.field(name).metadata or {}), name
    assert schema.field("lat1").type == pa.int32() and schema.field("lat1").metadata == {b"decimals": b"7"}
    back, _ = linestore.read(str(folder))
    _assert_read_back(results, back)
    for fmt, name in linestore.EXPORTS.items():
        linestore.export(str(folder), fmt, str(tmp_path / name))
        assert (tmp_path / name).read_bytes() == (folder / name).read_bytes(), name
    assert b"e+38" in (folder / "lines.csv").read_bytes()


def test_store_access_mark_kind(tmp_path):
    """The access mark's columns ("mark" in linestore.COLUMNS, linestore.ACCESS = runs.ACCESS): uint8 fields
    without decimals, only when the lines have them, read back as uint8; a value beyond uint8 is refused, not
    wrapped."""
    assert linestore.ACCESS == tuple(rn.ACCESS)
    assert [c for c in linestore.COLUMNS if c[3] == "mark"] == [(n, n, None, "mark", False) for n in rn.ACCESS]
    rng = np.random.default_rng(9)
    lines = _hard_lines(200, False, False, rng, access=True)
    table = linestore.lines_table(lines, {})
    for name in rn.ACCESS:
        field = table.schema.field(name)
        assert field.type == pa.uint8() and not field.nullable and not field.metadata
    assert set(rn.ACCESS).isdisjoint(linestore.lines_table(_hard_lines(200, False, False, rng), {}).schema.names)
    lines.columns["access2"] = lines.columns["access2"].astype(np.int64)
    lines.columns["access2"][3] = 256
    with pytest.raises(ValueError):
        linestore.lines_table(lines, {})


def test_store_written_whole_or_not_at_all(tmp_path, monkeypatch):
    """linestore.write writes under temporary names and gives both files their names only when both are whole:
    a failure between the two files (profiles.arrow's table) leaves neither name, nor a temporary file."""
    lines = _fake_lines(40)
    for name in sh.PIXEL_COLUMNS:
        lines.columns.pop(name)
    def failing(lines):
        assert (tmp_path / (linestore.LINES_FILE + linestore.PART)).is_file()  # lines.arrow written meanwhile
        raise MemoryError("no memory for the profiles")
    monkeypatch.setattr(linestore, "profiles_table", failing)
    with pytest.raises(MemoryError):
        linestore.write(str(tmp_path), lines, {})
    assert os.listdir(tmp_path) == []
    monkeypatch.undo()
    store = linestore.write(str(tmp_path), lines, {})
    assert sorted(os.listdir(tmp_path)) == sorted(linestore.FILES) and store["lines"] == 40


def test_a_store_that_fails_never_costs_the_run(tmp_path, monkeypatch):
    """A store that cannot be written (here linestore.write raising) leaves the run saved as a run of before:
    its text files and map, run.json without "store", no lines.arrow or profiles.arrow (a half-written one
    removed), and a warning."""
    def failing(run_path, lines, head):
        (tmp_path / "runs" / "clip" / linestore.LINES_FILE).write_bytes(b"half")
        raise MemoryError("no memory for the store")
    monkeypatch.setattr(linestore, "write", failing)
    folder, results, events = _clip_run(tmp_path, monkeypatch, os.path.join(DATA, "zabi_kon_nmt.tif"), radius=150)
    assert sorted(os.listdir(folder)) == ["ATTRIBUTION.txt", "data.js", "lines.csv", "lines.geojson", "lines.js",
                                          "map.html", "run.json"]
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert "store" not in meta and meta["summary"]["lines"] == len(results) > 0
    assert ("warning", "The run is saved without its store (lines.arrow): MemoryError: no memory for the store") \
        in events


def test_store_schema(tmp_path):
    """lines.arrow and profiles.arrow as spec-store.md 1.3 says: an Arrow IPC file of one record batch,
    uncompressed; the anchors int32 at 7 decimals, the grouping's values float64, every other value in the
    narrowest integer type with its decimals in the field's metadata, nulls by validity bits where a value
    may miss; the end columns only with them, stands_for (uint32) only with the square rule; the profiles'
    lists, pairs and nulls. A store of a newer format is refused; values no integer holds exactly are float64
    of round(value, decimals) (without decimals) and a count beyond uint32 is uint64, read back as written."""
    lines = _fake_lines(40)
    for name in sh.PIXEL_COLUMNS:
        lines.columns.pop(name)
    rng = np.random.default_rng(2)
    lines.profiles = {k: p for k, p in _profiles(40, rng).items() if k % 3 != 2}  # no batch without a surface
    folder = tmp_path / "plain"
    folder.mkdir()
    linestore.write(str(folder), lines, {"run": {"id": "x"}})
    with pa.OSFile(str(folder / linestore.LINES_FILE), "rb") as f:
        reader = pa.ipc.open_file(f)
        assert reader.num_record_batches == 1
        table = reader.read_all()
    schema = table.schema
    raw = (folder / linestore.LINES_FILE).read_bytes()
    assert np.ascontiguousarray(lines.columns["a1_xy"][:, 0]).tobytes() in raw  # uncompressed, float64 as it is
    assert schema.names == [name for name, column, *_ in linestore.COLUMNS if column in lines.columns]
    types = {f.name: f.type for f in schema}
    decimals = {f.name: (f.metadata or {}).get(b"decimals") for f in schema}
    nullable = {f.name: f.nullable for f in schema}
    for name in ("lat1", "lon1", "lat2", "lon2"):
        assert types[name] == pa.int32() and decimals[name] == b"7" and not nullable[name]
    for name in ("x1", "y1", "x2", "y2", "len", "clr", "hmax"):
        assert types[name] == pa.float64() and decimals[name] is None and not nullable[name]
    assert types["over"] == pa.uint8() and decimals["over"] is None
    # The narrowest: e1 400-404 m at 0.01 (int32), filled 0-3 m at 0.1 (int8), hmean 20-22 m at 0.01 (int16)
    assert (types["e1"], types["filled"], types["hmean"], types["water"]) == (pa.int32(), pa.int8(), pa.int16(),
                                                                              pa.int8())
    for name, _, _, places, may_miss in SCALED:
        if name in types:
            assert decimals[name] == str(places).encode() and nullable[name] == may_miss, name
    nulls = {name: table.column(name).null_count for name in types}
    assert nulls["clrN"] == 20 and nulls["prom1"] == 30 and sum(nulls.values()) == 50
    assert not set(rn.END_COLUMNS) & set(types) and rn.STANDS_FOR not in types
    meta = json.loads(schema.metadata[b"findaline"])
    assert meta["format"] == linestore.FORMAT == 1 and meta["head"] == {"run": {"id": "x"}}

    with pa.OSFile(str(folder / linestore.PROFILES_FILE), "rb") as f:
        reader = pa.ipc.open_file(f)
        assert reader.num_record_batches == 1
        profiles = reader.read_all()
    types = {f.name: f.type for f in profiles.schema}
    assert types == {"row": pa.uint32(), "d": pa.list_(pa.float64()), "z": pa.list_(pa.float64()),
                     "s": pa.list_(pa.float64()), "w": pa.list_(pa.uint8()), "g": pa.list_(pa.uint8()),
                     "min": pa.list_(pa.float64(), 2), "min_nmpt": pa.list_(pa.float64(), 2),
                     "max_height": pa.list_(pa.float64(), 2), "water_m": pa.float64(), "filled_m": pa.float64(),
                     "zone": pa.float64(), "lift": pa.float64()}
    assert profiles.column("row").to_pylist() == sorted(lines.profiles)
    assert profiles.column("min_nmpt").null_count == sum(sh.profile_dict(p)["min_nmpt"] is None
                                                         for p in lines.profiles.values())
    assert profiles.column("w").null_count == sum(sh.profile_dict(p)["w"] is None for p in lines.profiles.values())

    # With the end columns and the square rule; profiles without a surface model or an end zone
    lines.columns["lift_needed"], lines.columns["lift_no_zone"] = np.zeros(40), np.full(40, 2.5)
    lines.columns[rn.STANDS_FOR] = np.arange(1, 41, dtype=np.int64)
    batch = _batch_profiles(40, rng)
    batch.s = None
    lines.profiles = {k: batch[k] for k in range(0, 40, 2)}
    folder = tmp_path / "options"
    folder.mkdir()
    linestore.write(str(folder), lines, {})
    schema = pa.ipc.open_file(pa.OSFile(str(folder / linestore.LINES_FILE), "rb")).schema
    assert schema.names[-3:] == [*rn.END_COLUMNS, rn.STANDS_FOR] and schema.field(rn.STANDS_FOR).type == pa.uint32()
    assert schema.field("lift_needed").type == pa.int8() and schema.field("lift_no_zone").type == pa.int16()
    with pa.OSFile(str(folder / linestore.PROFILES_FILE), "rb") as f:
        profiles = pa.ipc.open_file(f).read_all()
    assert "s" not in profiles.schema.names  # absent without a surface model; zone and lift null where absent
    assert profiles.column("zone").null_count == profiles.column("lift").null_count == profiles.num_rows == 20
    back, _ = linestore.read(str(folder))
    assert back.columns[rn.STANDS_FOR].dtype == np.int64 and back.profiles[0]["s"] is None
    assert "zone" not in back.profiles[0] and back.profiles == {k: p.as_dict() for k, p in lines.profiles.items()}

    # No lines: one empty batch
    empty = tmp_path / "empty"
    empty.mkdir()
    linestore.write(str(empty), lines.take(np.zeros(0, dtype=np.int64)), {})
    back, _ = linestore.read(str(empty))
    assert len(back) == 0 and back.profiles == {}
    assert pa.ipc.open_file(pa.OSFile(str(empty / linestore.LINES_FILE), "rb")).num_record_batches == 1

    # A newer format: refused, by read and by export
    newer = tmp_path / "newer"
    shutil.copytree(folder, newer)
    path = str(newer / linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[b"findaline"])
    table = table.replace_schema_metadata({b"findaline": json.dumps({**meta, "format": 2}).encode()})
    with pa.OSFile(path, "wb") as sink, pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    with pytest.raises(linestore.NewerStore, match="made by a newer Find-a-Line"):
        linestore.read(str(newer))
    (newer / "run.json").write_text(json.dumps({"params": {"group_distance": 20}}), encoding="utf-8")
    with pytest.raises(linestore.NewerStore):
        linestore.export(str(newer), "csv", str(tmp_path / "x.csv"))
    with pytest.raises(ValueError, match="no export"):
        linestore.export(str(folder), "kml", str(tmp_path / "x.kml"))

    # Values no integer holds exactly: float64 as they are (no decimals), read back as written, exported as
    # runs.save_results writes them; a count beyond uint32: uint64 (int64 for a negative one)
    for column, value, name in (("elev_a1", np.nan, "e1"), ("elev_a1", np.inf, "e1"), ("angle1", 1e300, "angle1"),
                                ("prom1", np.inf, "prom1"), ("water_m", 2.0 ** 53, "water"),
                                ("anchor1", 215.0, "lat1"), (rn.STANDS_FOR, 2 ** 32, rn.STANDS_FOR),
                                (rn.STANDS_FOR, -1, rn.STANDS_FOR)):
        wide = lines.take(np.arange(40))
        for metres in ("water_m", "filled_m"):  # at 0.1 m as the search saves them (lines.csv prints them as they are)
            wide.columns[metres] = rn.round_floats(wide.columns[metres], 1)
        wide.columns[column] = wide.columns[column].copy()
        if column == "anchor1":
            wide.columns[column][3, 0] = value
        else:
            wide.columns[column][3] = value
        target = tmp_path / f"wide-{name}-{value}"
        target.mkdir()
        linestore.write(str(target), wide, {})
        field = pa.ipc.open_file(pa.OSFile(str(target / linestore.LINES_FILE), "rb")).schema.field(name)
        kinds = {rn.STANDS_FOR: pa.uint64() if value > 0 else pa.int64()}
        assert field.type == kinds.get(name, pa.float64()) and not (field.metadata or {}), (name, value)
        back, _ = linestore.read(str(target))
        _assert_read_back(wide, back)
        if column not in (rn.STANDS_FOR,):
            meta = {"params": {"group_distance": 20, "group_by": "clearance"}, "summary": {"lines": 40}}
            (target / "run.json").write_text(json.dumps(meta), encoding="utf-8")
            _exports_match(target, target, wide, meta)
    assert (linestore.END_COLUMNS, linestore.STANDS_FOR) == (rn.END_COLUMNS, rn.STANDS_FOR)  # copies of runs'



def test_web_process_never_imports_the_store(tmp_path_factory, tmp_path):
    """The web process serves a run's store (the local app: its media type) without importing linestore or
    pyarrow (the store is read by the page, exported by the worker), as it never imports search or numba;
    list_runs: a run with the store has its lines, an old run (lines.js only) too, a run without both not."""
    import clip_runs
    import runs
    data = clip_runs.data_copy(tmp_path_factory, "clip", [
        "--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"),
        "--northing", "254608", "--easting", "553966", "--radius", "150", "--water", "off", "--fill-gaps", "off",
        "--no-plot", "--yes", "--ortho", "never", "--nmpt", "off"])
    run_id = next(d for d in os.listdir(data / "runs") if (data / "runs" / d / "run.json").is_file())
    folder = data / "runs" / run_id
    assert all((folder / name).is_file() for name in linestore.FILES)
    for name, remove in (("old", linestore.FILES), ("bare", linestore.FILES + ("lines.js",)),
                         ("store", ("lines.js",))):
        shutil.copytree(folder, data / "runs" / name)
        meta = json.loads((data / "runs" / name / "run.json").read_text(encoding="utf-8"))
        (data / "runs" / name / "run.json").write_text(json.dumps({**meta, "id": name}), encoding="utf-8")
        for file in remove:
            os.remove(data / "runs" / name / file)
    listed = {r["id"]: r["has_lines"] for r in runs.list_runs(str(data / "runs"))}
    assert listed == {run_id: True, "old": True, "bare": False, "store": False}  # lines.js (until 2b-C)
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(data)!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "answers = [c.get('/api/runs')] + [c.get(f'/runs/{run}/{name}') for run in ("
            f"{run_id!r}, 'old') for name in ('lines.arrow', 'profiles.arrow', 'data.js')]\n"
            "print(json.dumps([[a.status_code, a.headers.get('content-type'), len(a.content)] for a in answers]))\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('linestore', 'pyarrow', 'numba', 'search'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                            env={**os.environ, **OFFLINE_ENV})
    assert result.returncode == 0, result.stderr
    answers, modules = (json.loads(line) for line in result.stdout.strip().splitlines()[-2:])
    assert modules == []
    assert answers[0][0] == 200
    arrow = (folder / linestore.LINES_FILE).stat().st_size, (folder / linestore.PROFILES_FILE).stat().st_size
    assert answers[1] == [200, linestore.MEDIA_TYPE, arrow[0]] and answers[2] == [200, linestore.MEDIA_TYPE, arrow[1]]
    assert [a[0] for a in answers[3:]] == [200, 404, 404, 200]  # an old run: no store, its data.js as before
