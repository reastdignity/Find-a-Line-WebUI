"""
Saving every run (map, results, parameters) so earlier runs can be browsed.

Layout:
    runs/<id>/lines.arrow     its lines, a row per line (linestore.py, the run's store)
    runs/<id>/profiles.arrow  the saved profiles, a row per profile (the store)
    runs/<id>/map.html        interactive map (the viewer, see mapping.save_map; not with --no-html)
    runs/<id>/run.json        parameters and summary, with the block "store"; written last
    runs/<id>/ATTRIBUTION.txt  licences and notices of the data used (run.json "attribution")
A run's lines.csv and lines.geojson are made from its store on request (`findaline.py export`, a
download in the app: linestore.export through save_results), never kept in the run folder. Runs saved
before store wave 4 (2026-11-17) also hold data.js, lines.js, lines.csv and lines.geojson (and
earlier ones no store): `findaline.py runs remove-old` lists and removes them (old_runs).
The id of a run is <date>_<time>_<place>_<random>: unique and not guessable (older runs
have no random part and keep their ids).
    runs/runs.js                       list of all runs, loaded by every map and the local app
    runs/_viewer/                      the viewer bundle shared by every map
runs.js is rewritten after every run (write_index).
"""

import contextlib
import json
import math
import os
import re
import secrets
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import numpy as np
import requests
from anyascii import anyascii

import cache
import osm

MAX_FEATURE_DEG = 0.2  # about 20 km; larger natural features are not used in run names


def _reverse(lat: float, lon: float, cache_dir: str, **params) -> Dict:
    return osm.reverse(lat, lon, cache_dir, **{"accept-language": "pl"}, **params)


def _nearest_feature(lat: float, lon: float, cache_dir: str) -> Optional[str]:
    """Name of the nearest natural feature: rock, peak, valley, river...

    Very large features (a peninsula, a sea strait) say nothing about the spot
    and are skipped.
    """
    data = _reverse(lat, lon, cache_dir, zoom=18, layer="natural")
    try:
        south, north, west, east = map(float, data.get("boundingbox", []))
        if north - south > MAX_FEATURE_DEG or (east - west) * math.cos(math.radians(lat)) > MAX_FEATURE_DEG:
            return None
    except ValueError:
        pass
    return data.get("name") or None


def _locality(lat: float, lon: float, cache_dir: str) -> Optional[str]:
    """Hamlet, village or town at the point."""
    data = _reverse(lat, lon, cache_dir, zoom=14)
    if data.get("category") in ("place", "boundary") and data.get("name"):
        return data["name"]
    address = data.get("address", {})
    return next((address[k] for k in ("hamlet", "village", "town", "city", "municipality")
                 if k in address), None)


def place_name(lat: float, lon: float, cache_dir: str) -> Optional[str]:
    """Name of the place from OpenStreetMap, e.g. "Żabi Koń, Gaj Kobylański".

    The nearest named natural feature plus the locality; None if offline.
    """
    parts = []
    for lookup in (_nearest_feature, _locality):
        try:
            parts.append(lookup(lat, lon, cache_dir))
        except (requests.RequestException, ValueError, KeyError):
            pass
    parts = list(dict.fromkeys(p for p in parts if p))  # drop empty and duplicates
    return ", ".join(parts) or None


def _slug(text: str) -> str:
    """A run's name as a folder name: ASCII by anyascii (ħ -> h, ø -> o, ß -> ss, Γαύδος -> Gaydos, where
    the Unicode decomposition of before dropped the letters), the rest as dashes, at most 40 characters."""
    return re.sub(r"[^A-Za-z0-9]+", "-", anyascii(text)).strip("-")[:40] or "run"


def new_run(runs_dir: str, name: str, created: datetime) -> Dict:
    """Create the folder for a run and return its id and path.

    The random part (64 bits) makes the id unique, also between searches started in the
    same second, and not guessable: whoever has a run's address was given it.
    """
    run_id = f"{created:%Y-%m-%d_%H%M%S}_{_slug(name)}_{secrets.token_hex(8)}"
    path = os.path.join(runs_dir, run_id)
    os.makedirs(path, exist_ok=False)  # never two searches in one folder
    return {"id": run_id, "path": path}


def folder_bytes(path: str) -> int:
    """The size of a run's folder on disk (its files, also those of its tiles)."""
    total = 0
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass
    return total


def without_paths(meta: Dict) -> Dict:
    """run.json without the paths of the computer that made it: local files (--elevation-file and
    --surface-file, --slope-file, an --area file) by their names only, also in the description of
    the source of a run from before this rule. run.json keeps the paths (profiles read the files)."""
    meta = dict(meta)
    if isinstance(meta.get("data"), list):
        meta["data"] = [{**entry, "file": os.path.basename(entry["file"])} if entry.get("file") else entry
                        for entry in meta["data"]]
    source = meta.get("source")
    if isinstance(source, dict) and source.get("id") == "files" and meta.get("data"):
        names = [entry["file"] for entry in meta["data"] if entry.get("file")]
        meta["source"] = {**source, "description": "local files: " + ", ".join(names)}
    params = meta.get("params")
    if isinstance(params, dict):
        params = dict(params)
        if params.get("slope_file"):
            params["slope_file"] = os.path.basename(params["slope_file"])
        area = params.get("area")
        if isinstance(area, dict) and _is_file(area.get("area")):
            params["area"] = {**area, "area": os.path.basename(area["area"])}
        meta["params"] = params
    return meta


def _is_file(area) -> bool:
    """Whether an --area is a file (not coast, cliffs, osm:<name> or a drawn area)."""
    return isinstance(area, str) and area not in ("coast", "cliffs", "drawn area") and not area.startswith("osm:")


def public_meta(meta: Dict) -> Dict:
    """The part of run.json that goes into lines.geojson, a file meant to be passed on:
    without the list of cache files each data layer used, and without server paths."""
    meta = without_paths(meta)
    if "data" not in meta:
        return meta
    return {**meta, "data": [{k: v for k, v in entry.items() if k != "paths"} for entry in meta["data"]]}


FIELDS = ["group", "representative", "group_size", "length_m", "clearance_m",
          "clearance_nmpt_m", "over_trees_buildings", "water_m", "filled_m",
          "height_max_m", "height_mean_m", "high_pct",
          "anchor1_lat", "anchor1_lon", "anchor1_elev_m", "anchor1_northing", "anchor1_easting",
          "anchor1_wall_angle", "anchor1_prominence_m", "anchor1_drop_m",
          "anchor2_lat", "anchor2_lon", "anchor2_elev_m", "anchor2_northing", "anchor2_easting",
          "anchor2_wall_angle", "anchor2_prominence_m", "anchor2_drop_m"]


# The A-frame heights of a run with --end-zone or --anchor-lift (helpers.END_VALUES, in that order), after
# clearance_nmpt_m; a run without the options has none of them (the FIELDS of before)
END_FIELDS = ["lift_needed_m", "lift_no_zone_m"]
END_COLUMNS = ("lift_needed", "lift_no_zone")  # helpers.END_VALUES (runs is imported without helpers)
# The found lines each line stands for, of a run made with --same-line-square (the square rule: samelines.COLUMN;
# runs is imported without samelines): the last column of lines.csv, the last property of a feature of
# lines.geojson and, in data.js and lines.js, the last value before the profile (their heads' "ends" names it);
# a run without the option has none of them (the FIELDS and the rows of before)
STANDS_FOR = "stands_for"
# The access mark of a run made with --access (access.py: 0 hard access, 1 cannot tell, 2 can walk) at anchor 1
# and anchor 2: after the anchors' columns of lines.csv and the properties of a feature of lines.geojson, before
# STANDS_FOR; in data.js and lines.js values before the profile (their heads' "ends" names them, after the A-frame
# heights and before STANDS_FOR); a run without the option has none of them (the FIELDS and the rows of before)
ACCESS = ["access1", "access2"]


def fields_of(lines) -> List[str]:
    """The columns of lines.csv (and properties of lines.geojson) of lines (a helpers.LineTable):
    FIELDS, with END_FIELDS after clearance_nmpt_m when the lines have the A-frame heights, ACCESS
    after the anchors' columns when they have the access mark and STANDS_FOR at the end when they have
    the count of the square rule."""
    fields = _with_ends(FIELDS) if END_COLUMNS[0] in lines.columns else FIELDS
    if ACCESS[0] in lines.columns:
        fields = fields + ACCESS
    return fields + [STANDS_FOR] if STANDS_FOR in lines.columns else fields


def _with_ends(fields: List[str]) -> List[str]:
    at = fields.index("clearance_nmpt_m") + 1
    return fields[:at] + END_FIELDS + fields[at:]


def rounded(value: float, digits: int):
    """round(), with None (an empty cell) for NaN."""
    return None if value != value else round(value, digits)


def round_floats(values: np.ndarray, digits: int) -> np.ndarray:
    """round(v, digits) of every value (as float64) exactly as Python's round() gives it, which
    rounds the exact binary value correctly (2.675 -> 2.67) where np.round(2.675, 2) gives 2.68.

    rint(x * 10**digits) / 10**digits is that value whenever x * 10**digits, rounded once, is
    more than an ulp away from a half: the integer is then the right one, and dividing it by
    the exact power of ten is correctly rounded like the conversion of round()'s decimal. The
    others (halves, NaN, infinities, values beyond 2**52 that round() leaves as they are) go
    through round() itself."""
    assert 0 <= digits <= 22  # 10**digits exact
    x = np.asarray(values, dtype=np.float64)
    scale = 10.0 ** digits
    with np.errstate(over="ignore", invalid="ignore"):
        p = x * scale
        y = np.rint(p) / scale
        size = np.abs(p)
        sure = (size < 2.0 ** 52) & (np.abs(np.abs(p - np.trunc(p)) - 0.5) > 2 * np.spacing(size))
    other = np.flatnonzero(~sure)
    if len(other):
        y[other] = [round(v, digits) for v in x[other].tolist()]
    return y


_JSON = json.JSONEncoder(ensure_ascii=False)
_SPECIAL_CSV = {"nan": "nan", "inf": "inf", "-inf": "-inf"}
_SPECIAL_JSON = {"nan": "NaN", "inf": "Infinity", "-inf": "-Infinity"}


def column_texts(values: np.ndarray, digits: Optional[int] = None, empty_nan: bool = False) -> tuple:
    """The texts of a column's values in lines.csv (as csv.writer writes them) and in JSON (as
    json.JSONEncoder does): (csv texts, JSON texts), the same list when they agree. digits: as
    round(v, digits) (rounded() with empty_nan: NaN is an empty cell and null)."""
    kind = values.dtype.kind
    if kind == "b" and digits is None:
        flags = values.tolist()
        return ["True" if v else "False" for v in flags], ["true" if v else "false" for v in flags]
    if kind in "iu":
        texts = list(map(str, values.tolist()))  # round() leaves integers as they are
        return texts, texts
    if kind != "f":  # anything else value by value, as before (round(True, 1) is 1)
        items = values.tolist()
        if digits is not None:
            items = [rounded(v, digits) if empty_nan else round(v, digits) for v in items]
        return (["" if v is None else repr(v) if isinstance(v, float) else str(v) for v in items],
                [_JSON.encode(v) for v in items])
    floats = round_floats(values, digits) if digits is not None else values.astype(np.float64, copy=False)
    texts = list(map(float.__repr__, floats.tolist()))
    special = np.flatnonzero(~np.isfinite(floats)).tolist()
    if not special:
        return texts, texts
    as_csv, as_json = texts, texts.copy()
    for k in special:
        if empty_nan and texts[k] == "nan":
            as_csv[k], as_json[k] = "", "null"
        else:
            as_csv[k], as_json[k] = _SPECIAL_CSV[texts[k]], _SPECIAL_JSON[texts[k]]
    return as_csv, as_json


def _group_of(groups, lo: int, hi: int) -> tuple:
    """The positions lo..hi of groups.members and the group of each."""
    at = np.arange(lo, hi, dtype=np.int64)
    return at, np.searchsorted(groups.start, at, "right") - 1


def rep_positions(groups) -> np.ndarray:
    """Where each group's representative stands in groups.members (mapping.Groups), its group's start
    when it is not among the members; read LINES_CHUNK members at a time (8 bytes per group, none
    per line). A representative found twice in its group is an error: row_order moves one only."""
    starts = groups.start[:-1].astype(np.int64)
    at, seen = starts.copy(), np.zeros(len(starts), dtype=bool)
    n = len(groups.members)
    for lo in range(0, n, LINES_CHUNK):
        position, group = _group_of(groups, lo, min(n, lo + LINES_CHUNK))
        hit = np.flatnonzero(groups.members[lo:lo + LINES_CHUNK] == groups.rep[group])
        group, position = group[hit], position[hit]
        if seen[group].any() or len(np.unique(group)) < len(group):
            raise ValueError("a representative is twice among the members of its group")
        seen[group] = True
        at[group] = position
    return at


def row_order(groups, lo: int, hi: int, at: np.ndarray) -> tuple:
    """The rows lo..hi of lines.csv: (line, its group's number, whether it represents the group, the
    group's size), group by group, each representative first and then the other members in their
    order (mapping.Groups; at: its rep_positions). The rows of a stable sort of each group on "not
    the representative", computed for these rows only."""
    position, group = _group_of(groups, lo, hi)
    start, rep_at = groups.start[group], at[group]
    # The representative to the group's first row, the members before it one row further
    source = np.where(position == start, rep_at, np.where(position <= rep_at, position - 1, position))
    lines = groups.members[source]
    return lines, group + 1, lines == groups.rep[group], groups.start[group + 1] - start


def feature_template(fields: List[str]) -> str:
    """A feature of lines.geojson as json.dumps(..., ensure_ascii=False) writes it, its values as %s."""
    return ('{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[%s, %s], [%s, %s]]}, '
            '"properties": {' + ", ".join(f"{json.dumps(name)}: %s" for name in fields) + "}}")


_TEMPLATES: Dict[tuple, str] = {}  # feature_template of the lists of fields met (fields_of: at most eight)


def _rows(lines, order: np.ndarray, number: np.ndarray, is_rep: np.ndarray, size: np.ndarray,
          csv: bool = True, geojson: bool = True) -> tuple:
    """The text of rows of lines.csv and of their features in lines.geojson (joined by ", ") of
    lines (a helpers.LineTable): a part of row_order. The same text as csv.writer and json.dumps
    of the rows as dicts of Python values (round() of each), built column by column; "" for a
    file not wanted (csv, geojson: the texts of the values are made for both anyway)."""
    c = lines.columns
    pick = lambda name, k=None: c[name][order] if k is None else c[name][order, k]
    ends = END_COLUMNS[0] in c
    columns = [  # (csv, JSON) texts in the order of FIELDS (fields_of: with END_FIELDS)
        column_texts(number), column_texts(is_rep), column_texts(size),
        column_texts(pick("length"), 1), column_texts(pick("clearance"), 2),
        column_texts(pick("clearance_nmpt"), 2, empty_nan=True),
        *([column_texts(pick(name), 2) for name in END_COLUMNS] if ends else []),  # rounded as the clearances
        column_texts(pick("over_obstacles")),
        column_texts(pick("water_m")), column_texts(pick("filled_m")),
        column_texts(pick("height_max"), 2), column_texts(pick("height_mean"), 2),
        column_texts(pick("high_pct"), 1)]
    count = [column_texts(pick(STANDS_FOR))] if STANDS_FOR in c else []  # after the anchors' columns
    for a, xy, elev, angle, prom, drop in (("anchor1", "a1_xy", "elev_a1", "angle1", "prom1", "drop1"),
                                           ("anchor2", "a2_xy", "elev_a2", "angle2", "prom2", "drop2")):
        columns += [column_texts(pick(a, 0), 7), column_texts(pick(a, 1), 7), column_texts(pick(elev), 2),
                    column_texts(pick(xy, 1), 2), column_texts(pick(xy, 0), 2), column_texts(pick(angle), 1),
                    column_texts(pick(prom), 1, empty_nan=True), column_texts(pick(drop), 1, empty_nan=True)]
    if ACCESS[0] in c:  # the access mark: after the anchors' columns, before the count
        columns += [column_texts(pick(name)) for name in ACCESS]
    columns += count
    if not len(order):
        return "", ""
    table = "\r\n".join(map(",".join, zip(*(t for t, _ in columns)))) + "\r\n" if csv else ""
    if not geojson:
        return table, ""
    values = [j for _, j in columns]
    fields = fields_of(lines)
    lat1, lon1, lat2, lon2 = (values[fields.index(name)] for name in
                              ("anchor1_lat", "anchor1_lon", "anchor2_lat", "anchor2_lon"))
    template = _TEMPLATES.get(tuple(fields)) or _TEMPLATES.setdefault(tuple(fields), feature_template(fields))
    features = ", ".join(template % row for row in zip(lon1, lat1, lon2, lat2, *values))
    return table, features


LINES_CHUNK = 1_000  # lines written between two progress updates (their texts, ~4.5 KB a line, are held)


def attribution_text(meta: Dict) -> str:
    """ATTRIBUTION.txt of a run: the licence and the notice of every dataset it used, then that the
    results are made from changed data (sources.credit.PROCESSED_NOTE)."""
    lines = [f"Find-a-Line run \"{meta.get('name', '')}\" ({meta.get('created', '')})", "",
             "Data used for this run, its licence and the notice it must be shown with:", ""]
    credits = meta.get("attribution") or []
    for credit in credits:
        lines.append(credit["data"])
        lines.append(f"  Notice: {credit['attribution']}")
        lines.append(f"  Licence: {credit['licence']}" + (f" ({credit['url']})" if credit.get("url") else ""))
        if credit.get("notice"):
            lines.append(f"  {credit['notice']}")
        lines.append("")
    source = meta.get("source") or {}
    if source.get("id") == "files":
        lines += [source.get("description", "local files"), "  Credit these as their own licences require.", ""]
    elif not credits:
        lines += ["Not recorded for this run.", ""]
    if credits or source.get("id") == "files":
        from sources.credit import PROCESSED_NOTE  # here: the web process imports runs, not sources
        lines += [PROCESSED_NOTE, ""]
    return "\n".join(lines)


RESULT_FILES = ("lines.csv", "lines.geojson", "ATTRIBUTION.txt", "run.json")  # what save_results writes


def save_results(run_path: str, lines, groups, meta: Dict, on_lines=lambda n, file: None,
                 files: tuple = RESULT_FILES):
    """Write lines.csv, lines.geojson, ATTRIBUTION.txt and run.json for a run (`files`: only
    those, in that order; the search writes only ATTRIBUTION.txt and run.json, linestore.export a
    line file from the store): the lines (a
    helpers.LineTable) group by group (mapping.Groups).

    The line files are written together, LINES_CHUNK rows at a time, never all rows at once;
    on_lines(n, file) reports progress after each chunk, then run.json with n=0.
    """
    want_csv, want_geojson = "lines.csv" in files, "lines.geojson" in files
    if want_csv or want_geojson:
        label = ", ".join(name for name in ("lines.csv", "lines.geojson") if name in files)
        # lines.geojson: the same text as json.dump of the whole collection, written in chunks of features
        with contextlib.ExitStack() as stack:
            table = geojson = None
            if want_csv:
                table = stack.enter_context(open(os.path.join(run_path, "lines.csv"), "w", newline="",
                                                 encoding="utf-8-sig"))
                table.write(",".join(fields_of(lines)) + "\r\n")  # csv.writer's header: no name needs quotes
            if want_geojson:
                geojson = stack.enter_context(open(os.path.join(run_path, "lines.geojson"), "w", encoding="utf-8"))
                geojson.write('{"type": "FeatureCollection", "features": [')
            at, n = rep_positions(groups), len(groups.members)
            for start in range(0, len(lines), LINES_CHUNK):
                part = row_order(groups, min(start, n), min(start + LINES_CHUNK, n), at)
                rows, features = _rows(lines, *part, csv=want_csv, geojson=want_geojson)
                if table is not None:
                    table.write(rows)
                if geojson is not None:
                    geojson.write((", " if start else "") + features)
                on_lines(len(part[0]), label)
            if geojson is not None:
                geojson.write('], "findaline": ' + _JSON.encode(public_meta(meta)) + "}")

    if "ATTRIBUTION.txt" in files:
        with open(os.path.join(run_path, "ATTRIBUTION.txt"), "w", encoding="utf-8") as f:
            f.write(attribution_text(meta))
    if "run.json" in files:
        with open(os.path.join(run_path, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        on_lines(0, "run.json")


def _local_time(created: str) -> str:
    """A run's time (UTC) as this computer's local time, "2026-10-31 07:17"."""
    try:
        return datetime.fromisoformat(created).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return created[:16].replace("T", " ")


def list_runs(runs_dir: str, only: Optional[Iterable[str]] = None) -> List[Dict]:
    """All saved runs (or those of `only`, ids), newest first."""
    runs = []
    if os.path.isdir(runs_dir):
        for run_id in os.listdir(runs_dir) if only is None else set(only):
            path = os.path.join(runs_dir, run_id, "run.json")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    run = json.load(f)
                run["created"] = cache.utc_iso(run.get("created")) or ""  # without an offset before 2026-10-31
                run["has_map"] = os.path.isfile(os.path.join(runs_dir, run_id, "map.html"))
                # Lines another map can show (Compare): its store (linestore.LINES_FILE) or, before it, its lines.js
                run["has_lines"] = any(os.path.isfile(os.path.join(runs_dir, run_id, name))
                                       for name in ("lines.arrow", "lines.js"))
                runs.append(run)
    return sorted(runs, key=lambda r: r["created"], reverse=True)


def params_summary(meta: Dict) -> str:
    p = meta["params"]
    nmpt = f"NMPT {p['nmpt']}" if p["nmpt"] else "no NMPT"
    if p.get("area"):
        a = p["area"]
        where = (a["area"] if a["area"] == "drawn area" else
                 f"area {os.path.basename(a['area']) if _is_file(a['area']) else a['area']}") + (f" ±{a['buffer']:g} m" if a["area"] in ("coast", "cliffs") else "") \
            + (f" within {a['within']}" if a.get("within") else "")
    else:
        where = f"radius {p['radius']:g} m"
    text = (f"{where}, {p['resolution']:g} m grid, slope ≥{p['slope_threshold']:g}°, "
            f"{p['min_length']:g}–{p['max_length']:g} m, {nmpt}")
    if "source" in meta:
        text = f"{meta['source']['name']}, {text}"
    if "max_anchor_diff" in p:
        text += f", Δh ≤{p['max_anchor_diff']:g}% / {p['max_anchor_diff_m']:g} m"
    limits = [f"{text}{p[key]:g}{unit}" for key, text, unit in (
        ("min_elevation", "anchors ≥", " m a.s.l."), ("max_elevation", "anchors ≤", " m a.s.l."),
        ("min_height", "height ≥", " m"), ("min_mean_height", "mean height ≥", " m"),
        ("min_high_share", f"≥{p.get('high_above', 20):g} m high over ≥", "%"),
        ("max_wall_angle", "wall angle ≤", "°"), ("min_prominence", "an anchor prominent ≥", " m"),
        ("min_prominence_both", "both anchors prominent ≥", " m"), ("min_drop", "drop ≥", " m"))
        if p.get(key) is not None]
    if limits:
        text += ", " + ", ".join(limits)
    if p.get("model") == "sag":
        r = p["rigging"]
        text += (f", sag model ({r['pretension']:g} kN, {r['stretch']:g}%, {r['webbing_weight']:g} g/m, "
                 f"{r['athlete_mass']:g} kg, fall {r['fall_zone']:g} m)")
    if p.get("end_zone"):
        text += f", no-fall zone {p['end_zone']:g} m at the ends"
    if p.get("anchor_lift"):
        text += f", A-frames {p['anchor_lift']:g} m"
    if p.get("same_line_side"):
        text += f", one line per pair of {p['same_line_side']:g} m anchor squares"
    return text


def _bbox(run: Dict) -> Optional[List[float]]:
    """(west, south, east, north) of a run's search area."""
    area = run.get("area") or {}
    if area.get("type") == "polygon":
        from shapely.geometry import shape
        return list(shape(area["geometry"]).bounds)
    if area.get("type") == "circle":
        dlat = area["radius"] / 111320
        dlon = dlat / max(math.cos(math.radians(area["lat"])), 0.01)
        return [area["lon"] - dlon, area["lat"] - dlat, area["lon"] + dlon, area["lat"] + dlat]
    return None


def _listed(run: Dict) -> Dict:
    """A run as runs.js lists it: without the data files, their credits, the area outline and its
    terrain (in the run's data.js and lines.js), its shore and where its terrain came from (data.js), with
    its box."""
    listed = {k: v for k, v in without_paths(run).items()
              if k not in ("data", "area", "attribution", "terrain", "shore", "terrain_sources")}
    listed["bbox"] = _bbox(run)
    return listed


RUNNING = "a tiled search still running"
BEING_SAVED = "being saved: no run.json"
NEWER = "made by a newer Find-a-Line"
UNREADABLE_META = "its run.json cannot be read"


def old_runs(runs_dir: str) -> Dict[str, list]:
    """The runs of a runs folder sorted for `findaline.py runs remove-old` (docs/line-volume/spec-store.md 2.2): "old"
    (a dict per run: id, created, lines, bytes, unreadable) are the folders with run.json and no store of today
    (linestore.store_state: missing, old or unreadable, the last marked "unreadable"); "current" the ids of the runs
    with today's store; "skipped" (id, reason): a folder without run.json (being saved: save_run writes it last), a
    tiled search whose progress.json says "running", a store of a newer Find-a-Line, a run.json that cannot be read.
    Folders starting with "." or "_" (the viewer, the lock) are no runs. Reads only: the caller holds
    cache.runs_lock. linestore (pyarrow) is imported here, never by importing runs (the web process imports runs)."""
    import linestore
    found = {"old": [], "current": [], "skipped": []}
    if not os.path.isdir(runs_dir):
        return found
    for entry in sorted(os.scandir(runs_dir), key=lambda e: e.name):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        meta_path = os.path.join(entry.path, "run.json")
        if not os.path.isfile(meta_path):
            found["skipped"].append((entry.name, BEING_SAVED))
            continue
        try:
            with open(os.path.join(entry.path, "progress.json"), encoding="utf-8") as f:
                running = json.load(f).get("status") == "running"
        except (OSError, ValueError, AttributeError):
            running = False
        if running:
            found["skipped"].append((entry.name, RUNNING))
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            lines = int((meta.get("summary") or {}).get("lines") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            found["skipped"].append((entry.name, UNREADABLE_META))
            continue
        state = linestore.store_state(entry.path)
        if state == "current":
            found["current"].append(entry.name)
        elif state == "newer":
            found["skipped"].append((entry.name, NEWER))
        else:
            found["old"].append({"id": entry.name, "created": cache.utc_iso(meta.get("created")) or "",
                                 "lines": lines, "bytes": folder_bytes(entry.path),
                                 "unreadable": state == "unreadable"})
    return found


def write_index(runs_dir: str):
    """Rewrite runs.js (used by the maps and the local app) from the saved runs. One process at a
    time (cache.runs_lock), so of two runs saved at once the later lists both."""
    with cache.runs_lock(runs_dir):
        _write_index(runs_dir)


def _write_index(runs_dir: str):
    runs = list_runs(runs_dir)
    # Written whole, then moved over the old file: a map or the app never reads half a list
    with cache.replacing(os.path.join(runs_dir, "runs.js"), "w", encoding="utf-8") as f:
        f.write("window.FINDALINE_RUNS = ")
        json.dump([_listed(r) for r in runs], f, ensure_ascii=False)
        f.write(";\n")
