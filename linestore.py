"""
A run's store: its lines and their profiles as two Arrow IPC files beside the other files of the run
(docs/line-volume/spec-store.md 1.3; written since store wave 2, 2026-11-15, beside data.js and the text
files, which wave 4 ends).

    lines.arrow     a row per line, in the search's table order (data.js's): the columns of COLUMNS
    profiles.arrow  a row per saved profile: `row` (into lines.arrow) and the profile's values

Both are Arrow IPC files (not streams), uncompressed (the page reads their buffers without a copy; zstd
inside the file made apache-arrow copy them, part P5), each one record batch. The values data.js prints
unrounded for the grouping (x1..y2, len, clr, hmax) are float64 as they are. Every other value is an
integer of value x 10^decimals, the decimals mapping.map_rows prints (the field's metadata `decimals`), in
the narrowest of int8/16/32/64 that holds the run's values (the anchors int32): the double a reader gets
by dividing it by 10^decimals is the one Python's round(value, decimals) gives, so the text of lines.csv
and data.js comes back byte for byte. A missing value (NaN) is a null (validity bit) where the column may
miss one; a value that rounds to -0.0 is listed in the schema's metadata (`negative_zero`), since an
integer has no sign of zero and lines.csv prints "-0.0". A column whose values no integer holds exactly
(beyond 2^53 once scaled, an infinity, NaN where a value never misses: e.g. undeclared no-data of
3.4e38 in a terrain file) is float64 of round(value, decimals), without `decimals`; a count
beyond uint32 is uint64: the store never refuses a run's values. The schema metadata `findaline` (JSON) holds
{"format": FORMAT, "head": the head of data.js without the lines (mapping.map_head), "negative_zero":
{column: [rows]}}; a reader refuses a higher format.

write(run_path, lines, head) writes both files and gives the block run.json keeps as "store";
read(run_path) gives the lines back as a helpers.LineTable (with the profiles as dicts of
helpers.line_profile) and the head; export(run_path, fmt, out) writes lines.csv or lines.geojson from the
store through mapping.group_lines and runs.save_results, the bytes the run's own files hold.

Plain numpy and pyarrow at import: runs (Python's round() of a column, runs.round_floats) only inside
write and export, mapping (numba's grouping) only inside export, so reading a store is cheap; the web
process never imports this module.
"""

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa

FORMAT = 1  # of the store; a reader refuses a higher one ("made by a newer Find-a-Line")
LINES_FILE = "lines.arrow"
PROFILES_FILE = "profiles.arrow"
FILES = (LINES_FILE, PROFILES_FILE)
PART = ".part"  # the files' names while write writes them
META_KEY = b"findaline"  # the schema metadata's key of both files
MEDIA_TYPE = "application/vnd.apache.arrow.file"  # of both files (web.py serves them with it)
END_COLUMNS = ("lift_needed", "lift_no_zone")  # runs.END_COLUMNS = helpers.END_VALUES (tests/test_linestore.py)
STANDS_FOR = "stands_for"  # runs.STANDS_FOR = samelines.COLUMN

# The columns of lines.arrow in their order: (name, the LineTable's column and its index in a pair or None,
# decimals: None for float64 as it is, "bool" for 0/1 uint8, "count" for uint32, an int for an integer of
# that many decimals; whether a missing value is a null). Those of END_COLUMNS only with the no-fall zone or
# the A-frames, STANDS_FOR only with the square rule (the LineTable has them then).
COLUMNS = [
    ("lat1", "anchor1", 0, 7, False), ("lon1", "anchor1", 1, 7, False),
    ("lat2", "anchor2", 0, 7, False), ("lon2", "anchor2", 1, 7, False),
    ("x1", "a1_xy", 0, None, False), ("y1", "a1_xy", 1, None, False),
    ("x2", "a2_xy", 0, None, False), ("y2", "a2_xy", 1, None, False),
    ("len", "length", None, None, False), ("clr", "clearance", None, None, False),
    ("hmax", "height_max", None, None, False),
    ("clrN", "clearance_nmpt", None, 2, True),
    ("e1", "elev_a1", None, 2, False), ("e2", "elev_a2", None, 2, False),
    ("over", "over_obstacles", None, "bool", False),
    ("water", "water_m", None, 1, False), ("filled", "filled_m", None, 1, False),
    ("hmean", "height_mean", None, 2, True), ("highPct", "high_pct", None, 1, True),
    ("angle1", "angle1", None, 1, True), ("angle2", "angle2", None, 1, True),
    ("prom1", "prom1", None, 1, True), ("prom2", "prom2", None, 1, True),
    ("drop1", "drop1", None, 1, True), ("drop2", "drop2", None, 1, True),
    *[(name, name, None, 2, False) for name in END_COLUMNS],
    (STANDS_FOR, STANDS_FOR, None, "count", False),
]
FIXED = {name: pa.int32() for name in ("lat1", "lon1", "lat2", "lon2")}  # the anchors: int32 whatever the run
INTS = (pa.int8(), pa.int16(), pa.int32(), pa.int64())
# The profile's values of a row of profiles.arrow besides the lists (helpers.Profiles' small: distance and value)
PAIRS = ("min", "min_nmpt", "max_height")
PROFILE_KEYS = ("min", "min_nmpt", "max_height", "d", "z", "s", "w", "water_m", "g", "filled_m", "zone", "lift")


class NewerStore(ValueError):
    """A store of a format this code does not read."""


def _narrowest(values: np.ndarray) -> pa.DataType:
    """The narrowest of INTS that holds every value (int64 values, each below 2^53 in size)."""
    lo, hi = (int(values.min()), int(values.max())) if len(values) else (0, 0)
    return next(kind for kind in INTS if np.iinfo(kind.to_pandas_dtype()).min <= lo
                and hi <= np.iinfo(kind.to_pandas_dtype()).max)


def _scaled(name: str, values: np.ndarray, decimals: int, nullable: bool) -> Tuple[pa.Array, List[int], bool]:
    """A column's values as integers of value x 10^decimals (round() of each: runs.round_floats), the rows
    whose value rounds to -0.0, and True; or, when no integer holds them exactly (NaN where a value never
    misses, an infinity, beyond 2^53 once scaled, an anchor beyond int32), round(value, decimals) as float64
    (what data.js shows), no rows and False."""
    import runs as rn
    rounded = rn.round_floats(values, decimals)
    missing = np.isnan(rounded)
    scaled = np.where(missing, 0.0, rounded) * 10.0 ** decimals
    # Beyond 2^53 an integer is no longer exact as a double (nor its quotient by 10^decimals)
    exact = (nullable or not missing.any()) and bool(np.all(np.isfinite(scaled) & (np.abs(scaled) < 2.0 ** 53)))
    if exact:
        integers = np.rint(scaled).astype(np.int64)
        kind = _narrowest(integers[~missing])
        if name in FIXED:
            exact = kind.bit_width <= FIXED[name].bit_width
            kind = FIXED[name]
    if not exact:  # round(value, decimals) as a double: what data.js shows, and lines.csv's text again
        return pa.array(rounded, type=pa.float64()), [], False
    negative_zero = np.flatnonzero((rounded == 0) & np.signbit(rounded)).tolist()
    array = pa.array(integers.astype(kind.to_pandas_dtype()), type=kind, mask=missing if missing.any() else None)
    return array, negative_zero, True


def _field_values(lines, column: str, index: Optional[int]) -> np.ndarray:
    values = lines.columns[column]
    return values if index is None else values[:, index]


def _metadata(value: Dict) -> Dict[bytes, bytes]:
    return {META_KEY: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")}


def lines_table(lines, head: Dict) -> pa.Table:
    """lines.arrow's table of lines (a helpers.LineTable after mapping.coordify) with the run's head."""
    fields, arrays, negative_zero = [], [], {}
    for name, column, index, decimals, nullable in COLUMNS:
        if column not in lines.columns:
            if column in END_COLUMNS or column == STANDS_FOR:
                continue
            raise ValueError(f"the lines have no column {column}")
        values = _field_values(lines, column, index)
        metadata = None
        if decimals is None:
            array = pa.array(np.ascontiguousarray(values, dtype=np.float64), type=pa.float64())
        elif decimals == "bool":
            array = pa.array(np.asarray(values, dtype=bool).astype(np.uint8), type=pa.uint8())
        elif decimals == "count":  # uint32; uint64 beyond it, int64 for a negative one (none is)
            values = np.asarray(values)
            kind = pa.uint32()
            if len(values) and values.min() < 0:
                kind = pa.int64()
            elif len(values) and values.max() > np.iinfo(np.uint32).max:
                kind = pa.uint64()
            array = pa.array(values.astype(kind.to_pandas_dtype()), type=kind)
        else:
            array, zeros, exact = _scaled(name, np.asarray(values, dtype=np.float64), decimals, nullable)
            metadata = {"decimals": str(decimals)} if exact else None
            if zeros:
                negative_zero[name] = zeros
        fields.append(pa.field(name, array.type, nullable=nullable, metadata=metadata))
        arrays.append(array)
    schema = pa.schema(fields, metadata=_metadata({"format": FORMAT, "head": head, "negative_zero": negative_zero}))
    return pa.Table.from_arrays(arrays, schema=schema)


def _ranges(starts: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """The indices starts[k] .. starts[k] + lengths[k] - 1 of every k, one after another."""
    total = int(lengths.sum())
    if not total:
        return np.zeros(0, dtype=np.int64)
    before = np.cumsum(lengths) - lengths
    return np.repeat(starts.astype(np.int64) - before, lengths) + np.arange(total, dtype=np.int64)


def _as_batch(profiles: List[Dict]):
    """Profiles given as dicts of helpers.line_profile (tile edges, tile files of before) as one
    helpers.Profiles (None for a value: NaN; "s" of each, None where a dict has none, in `s_rows`)."""
    import helpers as sh
    for p in profiles:
        unknown = set(p) - set(PROFILE_KEYS)
        if unknown or not all(len(p[k]) == len(p["d"]) for k in ("z", "s", "w", "g") if p.get(k) is not None):
            raise ValueError(f"a profile the store cannot hold: {sorted(unknown) or 'lists of unequal length'}")
    sizes = np.array([len(p["d"]) for p in profiles], dtype=np.int64)
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    flat = lambda key, default: np.array([default if v is None else v  # noqa: E731
                                          for p in profiles for v in (p.get(key) or [default] * len(p["d"]))],
                                         dtype=np.float64)
    nan = float("nan")
    pair = lambda value: [nan, nan] if value is None else list(value)  # noqa: E731
    small = np.array([pair(p.get("min")) + pair(p.get("min_nmpt")) + pair(p.get("max_height"))
                      + [p.get("water_m", nan), p.get("filled_m", nan)] for p in profiles],
                     dtype=np.float64).reshape(len(profiles), 8)
    flags = np.array([(p.get("w") is not None) | 2 * (p.get("g") is not None) for p in profiles], dtype=np.uint8)
    has_s = np.array([p.get("s") is not None for p in profiles], dtype=bool)
    has_zone = np.array(["zone" in p for p in profiles], dtype=bool)
    batch = sh.Profiles(offsets, flat("d", nan), flat("z", nan), flat("s", nan),
                        flat("w", 0).astype(np.uint8), flat("g", 0).astype(np.uint8), small, flags,
                        np.array([p.get("zone", nan) for p in profiles], dtype=np.float64))
    lifts = np.array([p.get("lift", nan) if p.get("lift") is not None else nan for p in profiles], dtype=np.float64)
    return batch, has_s, has_zone, lifts


def profiles_table(lines) -> pa.Table:
    """profiles.arrow's table: a row per line with a profile (lines.profiles: helpers.Profile of a batch
    or the dict of helpers.line_profile), by the line's row."""
    import helpers as sh
    rows = sorted(lines.profiles)
    sources: Dict[int, int] = {}  # id of a batch -> its number
    batches, source, index, dicts = [], np.empty(len(rows), dtype=np.int64), np.empty(len(rows), dtype=np.int64), []
    for k, row in enumerate(rows):
        p = lines.profiles[row]
        if isinstance(p, sh.Profile):
            number = sources.setdefault(id(p.batch), len(batches))
            if number == len(batches):
                batches.append(p.batch)
            source[k], index[k] = number, p.index
        else:
            source[k], index[k] = -1, len(dicts)
            dicts.append(sh.profile_dict(p))
    # Per batch: has it s, zones; the dicts' batch says it per row
    parts = [(b, np.full(len(b), b.s is not None), np.full(len(b), b.zone is not None),
              np.full(len(b), np.nan if b.lift is None else float(b.lift))) for b in batches]
    if dicts:
        parts.append(_as_batch(dicts))
        source[source == -1] = len(parts) - 1
    n = len(rows)
    lengths = np.zeros(n, dtype=np.int64)
    starts = np.zeros(n, dtype=np.int64)
    small = np.zeros((n, 8), dtype=np.float64)
    flags = np.zeros(n, dtype=np.uint8)
    has_s, has_zone = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    zone, lift = np.full(n, np.nan), np.full(n, np.nan)
    for j, (b, s_of, zone_of, lift_of) in enumerate(parts):
        mine = np.flatnonzero(source == j)
        i = index[mine]
        starts[mine], lengths[mine] = b.offsets[i], b.offsets[i + 1] - b.offsets[i]
        small[mine], flags[mine] = b.small[i], b.flags[i]
        has_s[mine], has_zone[mine], lift[mine] = s_of[i], zone_of[i], lift_of[i]
        if b.zone is not None:
            zone[mine] = b.zone[i]
    offsets = np.concatenate([[0], np.cumsum(lengths)])
    if offsets[-1] >= 2 ** 31:
        raise ValueError("too many profile points for the store")

    def gather(field: str, dtype, wanted: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """The points of `field` of the rows wanted (the others none), and their offsets."""
        size = np.where(wanted, lengths, 0)
        out = np.empty(int(size.sum()), dtype=dtype)
        at = np.concatenate([[0], np.cumsum(size)])
        for j, (b, *_) in enumerate(parts):
            mine = np.flatnonzero((source == j) & wanted)
            values = getattr(b, field)
            if len(mine):
                out[_ranges(at[mine], size[mine])] = values[_ranges(starts[mine], size[mine])]
        return out, at

    def listed(field: str, dtype, wanted: np.ndarray, kind: pa.DataType) -> pa.Array:
        values, at = gather(field, dtype, wanted)
        return pa.ListArray.from_arrays(pa.array(at.astype(np.int32), type=pa.int32()), pa.array(values, type=kind),
                                        mask=None if wanted.all() else pa.array(~wanted))

    def pair(k: int, nullable: bool) -> pa.Array:
        values = small[:, k:k + 2]
        mask = np.isnan(values[:, 0]) if nullable else None
        return pa.FixedSizeListArray.from_arrays(pa.array(np.ascontiguousarray(values).reshape(-1), type=pa.float64()),
                                                 2, mask=None if mask is None or not mask.any() else pa.array(mask))

    everyone = np.ones(n, dtype=bool)
    columns = [("row", pa.array(np.asarray(rows, dtype=np.uint32), type=pa.uint32()), False),
               ("d", listed("d", np.float64, everyone, pa.float64()), False),
               ("z", listed("z", np.float64, everyone, pa.float64()), False)]
    if has_s.any():
        columns.append(("s", listed("s", np.float64, has_s, pa.float64()), True))
    columns += [("w", listed("w", np.uint8, (flags & 1) > 0, pa.uint8()), True),
                ("g", listed("g", np.uint8, (flags & 2) > 0, pa.uint8()), True),
                ("min", pair(0, False), False), ("min_nmpt", pair(2, True), True), ("max_height", pair(4, False), False),
                ("water_m", pa.array(small[:, 6], type=pa.float64()), False),
                ("filled_m", pa.array(small[:, 7], type=pa.float64()), False)]
    # The end zone's metres and the A-frames' lift: null where a profile has none (every profile of a run without them)
    columns += [("zone", pa.array(zone, type=pa.float64(), mask=~has_zone), True),
                ("lift", pa.array(lift, type=pa.float64(), mask=~has_zone), True)]
    schema = pa.schema([pa.field(name, array.type, nullable=nullable) for name, array, nullable in columns],
                       metadata=_metadata({"format": FORMAT}))
    return pa.Table.from_arrays([array for _, array, _ in columns], schema=schema)


def _write_file(path: str, table: pa.Table):
    """An Arrow IPC file of one record batch, uncompressed."""
    batch = table.combine_chunks().to_batches()
    with pa.OSFile(path, "wb") as sink, pa.ipc.new_file(sink, table.schema,
                                                         options=pa.ipc.IpcWriteOptions(compression=None)) as writer:
        if batch:
            assert len(batch) == 1
            writer.write_batch(batch[0])
        else:  # no rows: one empty batch all the same (the page reads batch 0)
            writer.write_batch(pa.RecordBatch.from_arrays(
                [pa.array([], type=f.type) for f in table.schema], schema=table.schema))


def write(run_path: str, lines, head: Dict) -> Dict:
    """lines.arrow and profiles.arrow of a run (lines: a helpers.LineTable after mapping.coordify, its
    profiles those the map keeps; head: mapping.map_head's). Returns run.json's block "store": the
    format, the lines, the bytes of both files and the first 16 hex digits of lines.arrow's sha256.
    Both are written under temporary names (PART) and take their names only when both are whole,
    profiles.arrow first: a process stopped meanwhile leaves no half store under the files' names."""
    paths = [os.path.join(run_path, name) for name in FILES]
    parts = [path + PART for path in paths]
    try:
        _write_file(parts[0], lines_table(lines, head))
        _write_file(parts[1], profiles_table(lines))
        digest = hashlib.sha256()
        with open(parts[0], "rb") as f:
            for block in iter(lambda: f.read(1 << 24), b""):
                digest.update(block)
        size = sum(os.path.getsize(p) for p in parts)
        os.replace(parts[1], paths[1])
        os.replace(parts[0], paths[0])
    finally:
        for part in parts:
            with contextlib.suppress(OSError):
                os.remove(part)
    return {"format": FORMAT, "lines": len(lines), "bytes": size, "sha256": digest.hexdigest()[:16]}


def _meta_of(schema: pa.Schema, path: str) -> Dict:
    raw = (schema.metadata or {}).get(META_KEY)
    if raw is None:
        raise ValueError(f"{path} is not a store of Find-a-Line")
    meta = json.loads(raw.decode("utf-8"))
    if not isinstance(meta.get("format"), int) or meta["format"] > FORMAT:
        raise NewerStore(f"{os.path.basename(path)} was made by a newer Find-a-Line (store format "
                         f"{meta.get('format')}; this one reads {FORMAT} and before)")
    return meta


def _read_file(path: str) -> Tuple[pa.Table, Dict]:
    """The table of a store's file and its metadata `findaline` (a newer format refused before its
    batch is read). Read into memory, not mapped: nothing holds the file afterwards (Windows)."""
    with pa.OSFile(path, "rb") as source:
        reader = pa.ipc.open_file(source)
        meta = _meta_of(reader.schema, path)
        return reader.read_all(), meta


def _decoded(array: pa.ChunkedArray, decimals, negative_zero: List[int]) -> np.ndarray:
    array = array.combine_chunks()
    if decimals is None:
        return array.to_numpy(zero_copy_only=False).astype(np.float64, copy=True)
    if decimals == "bool":
        return array.to_numpy(zero_copy_only=False).astype(bool)
    if decimals == "count":
        return array.to_numpy(zero_copy_only=False).astype(np.int64)
    values = array.fill_null(0).to_numpy(zero_copy_only=False).astype(np.float64) / 10.0 ** decimals
    if array.null_count:
        values[array.is_null().to_numpy(zero_copy_only=False)] = np.nan
    if negative_zero:
        values[np.asarray(negative_zero, dtype=np.int64)] = -0.0
    return values


def _profile_dicts(table: pa.Table) -> Dict[int, Dict]:
    """The profiles of profiles.arrow as dicts of helpers.line_profile, by their line's row."""
    names = table.schema.names

    def lists(name):
        if name not in names:
            return None, None, None
        column = table.column(name).combine_chunks()
        return (column.offsets.to_numpy(), column.values.to_numpy(zero_copy_only=False),
                column.is_valid().to_numpy(zero_copy_only=False))

    def pairs(name):
        column = table.column(name).combine_chunks()
        values = column.values.to_numpy(zero_copy_only=False).reshape(-1, 2).tolist()
        valid = column.is_valid().to_numpy(zero_copy_only=False).tolist()
        return [v if ok else None for v, ok in zip(values, valid)]

    rows = table.column("row").to_numpy().tolist()
    d_at, d, _ = lists("d")
    z_at, z, _ = lists("z")
    s_at, s, s_valid = lists("s")
    w_at, w, w_valid = lists("w")
    g_at, g, g_valid = lists("g")
    gaps = lambda at, values: (np.concatenate([[0], np.cumsum(np.isnan(values))])[at[1:]]  # noqa: E731
                               - np.concatenate([[0], np.cumsum(np.isnan(values))])[at[:-1]]) > 0
    z_gaps = gaps(z_at, z).tolist()
    s_gaps = gaps(s_at, s).tolist() if s is not None else None
    least, nmpt, highest = pairs("min"), pairs("min_nmpt"), pairs("max_height")
    water, filled = (table.column(k).to_numpy().tolist() for k in ("water_m", "filled_m"))
    zone = lift = None
    if "zone" in names:
        zone, lift = (table.column(k).to_pylist() for k in ("zone", "lift"))
    points = lambda values, lo, hi, gap: ([None if v != v else v for v in values[lo:hi].tolist()]  # noqa: E731
                                          if gap else values[lo:hi].tolist())
    out = {}
    for k, row in enumerate(rows):
        lo, hi = int(d_at[k]), int(d_at[k + 1])
        missing = z_gaps[k] or (s_gaps is not None and s_valid[k] and s_gaps[k])  # helpers.Profiles' flag 4
        profile = {"min": least[k], "min_nmpt": nmpt[k], "max_height": highest[k], "d": d[lo:hi].tolist(),
                   "z": points(z, int(z_at[k]), int(z_at[k + 1]), missing),
                   "s": points(s, int(s_at[k]), int(s_at[k + 1]), missing) if s is not None and s_valid[k] else None,
                   "w": w[int(w_at[k]):int(w_at[k + 1])].tolist() if w_valid[k] else None, "water_m": water[k],
                   "g": g[int(g_at[k]):int(g_at[k + 1])].tolist() if g_valid[k] else None, "filled_m": filled[k]}
        if zone is not None and zone[k] is not None:
            profile.update(zone=zone[k], lift=lift[k])
        out[row] = profile
    return out


def read(run_path: str, profiles: bool = True):
    """(helpers.LineTable, head) of a run's store: the columns write took, the decoded values (NaN for a
    null, -0.0 where it was), the profiles as dicts of helpers.line_profile (profiles=False: none)."""
    import helpers as sh
    table, meta = _read_file(os.path.join(run_path, LINES_FILE))
    zeros = meta.get("negative_zero") or {}
    columns: Dict[str, np.ndarray] = {}
    pairs: Dict[str, List[np.ndarray]] = {}
    for name, column, index, decimals, _ in COLUMNS:
        if name not in table.schema.names:
            continue
        field = table.schema.field(name)
        if decimals not in (None, "bool", "count"):  # float64 as it is where no integer held the values
            places = (field.metadata or {}).get(b"decimals")
            decimals = int(places) if places is not None else None
        values = _decoded(table.column(name), decimals, zeros.get(name) or [])
        if index is None:
            columns[column] = values
        else:
            pairs.setdefault(column, [None, None])[index] = values
    for column, (first, second) in pairs.items():
        columns[column] = np.column_stack([first, second])
    lines = sh.LineTable(columns)
    if profiles:
        table, _ = _read_file(os.path.join(run_path, PROFILES_FILE))
        lines.profiles = _profile_dicts(table)
    return lines, meta["head"]


EXPORTS = {"csv": "lines.csv", "geojson": "lines.geojson"}


def export(run_path: str, fmt: str, out: str):
    """lines.csv (fmt "csv") or lines.geojson ("geojson") of a run made from its store into the file
    `out`: the lines grouped as the search grouped them (mapping.group_lines with run.json's distance
    and value), written by runs.save_results with run.json's values without its "store" (search.save_run
    writes the store after the text files, so lines.geojson's "findaline" never held it), so the bytes
    are those the run's own text file holds."""
    import mapping as mp
    import runs as rn
    if fmt not in EXPORTS:
        raise ValueError(f"no export of the format {fmt!r}")
    with open(os.path.join(run_path, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    meta.pop("store", None)
    params = meta.get("params") or {}
    lines, _ = read(run_path, profiles=False)
    groups = mp.group_lines(lines, params["group_distance"], params.get("group_by", "clearance"))
    folder = tempfile.mkdtemp(prefix=".export-", dir=os.path.dirname(os.path.abspath(out)))
    try:
        rn.save_results(folder, lines, groups, meta, files=(EXPORTS[fmt],))
        os.replace(os.path.join(folder, EXPORTS[fmt]), out)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
