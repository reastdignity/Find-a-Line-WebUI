"""
Converting results to GPS coordinates and displaying them on maps.
"""

import contextlib
import dataclasses
import html
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from pyproj import Transformer

import cache
from grid import Grid
from helpers import END_VALUES, HIGH_ABOVE, LEASH_FALL, SLOPE, LineTable, profile_dict
from progress import progress
from runs import column_texts
from sag import Rigging

MAX_ZOOM = 21  # about 5 cm per pixel, the detail of the best geoportal orthophotos
COORDINATE_PART = 1 << 17  # lines per part of coordify

COLOR_VALID = "#FF10F0"     # neon pink
COLOR_OBSTACLE = "#FF8C00"  # orange: line passes too close to trees/buildings (NMPT)

PL1992 = "EPSG:2180"  # Polish national grid, accepted by --northing/--easting
_to_wgs84 = Transformer.from_crs(PL1992, "EPSG:4326", always_xy=True)


def pl1992_to_wgs84(easting: float, northing: float):
    """Return (lat, lon)."""
    lon, lat = _to_wgs84.transform(easting, northing)
    return lat, lon


def coordify(lines: LineTable, grid: Grid, nmpt_mode: Optional[str]) -> LineTable:
    """Add the coordinates of the anchors to the lines (in place): "anchor1", "anchor2" (lat, lon),
    "a1_xy", "a2_xy" (easting, northing in metres of the grid CRS, used for grouping) and
    "over_obstacles" (the line passes over trees/buildings with --nmpt mark). Returns the lines.
    Lines share anchors (a part of 2**17 lines on swiss-long holds about 7 000 different ones), so
    each part transforms its different anchor pixels once and gathers their coordinates: the same
    float64 values (a pixel's coordinates do not depend on the others transformed with it)."""
    c, n = lines.columns, len(lines)
    progress.compute.start("coordinates", n, unit="line")
    names = ("anchor1", "anchor2", "a1_xy", "a2_xy")
    out = {name: np.empty((n, 2)) for name in names}
    transformer = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True) if n else None
    for at in range(0, n, COORDINATE_PART):  # in parts: the temporaries of all lines would be ~130 B a line
        end = min(n, at + COORDINATE_PART)
        rows = np.column_stack([c["a1"][at:end, 0], c["a2"][at:end, 0]]).ravel()
        cols = np.column_stack([c["a1"][at:end, 1], c["a2"][at:end, 1]]).ravel()
        low = int(cols.min())
        span = int(cols.max()) - low + 1
        pixels, inverse = np.unique(rows * span + (cols - low), return_inverse=True)  # the part's anchor pixels
        del rows, cols
        easting, northing = grid.pixel_to_xy(pixels // span, pixels % span + low)
        lon, lat = transformer.transform(easting, northing)
        easting, northing, lon, lat = (np.asarray(v, dtype=np.float64)[inverse] for v in (easting, northing, lon, lat))
        del pixels, inverse
        for name, (a, b, first) in zip(names, ((lat, lon, 0), (lat, lon, 1), (easting, northing, 0),
                                               (easting, northing, 1))):
            out[name][at:end, 0] = a[first::2]
            out[name][at:end, 1] = b[first::2]
        progress.compute.update(end - at)
    c.update(out)
    c["over_obstacles"] = (c["clearance_nmpt"] <= 0) if nmpt_mode == "mark" else np.zeros(n, dtype=bool)
    progress.compute.finish()
    return lines


def first_anchor(lines: LineTable) -> np.ndarray:
    """(x, y) of the first anchor of every line (the smaller x, then y): the one that decides
    which tile of a large area a line belongs to."""
    a1, a2 = lines.columns["a1_xy"], lines.columns["a2_xy"]
    first = (a1[:, 0] < a2[:, 0]) | ((a1[:, 0] == a2[:, 0]) & (a1[:, 1] <= a2[:, 1]))  # min() of the tuples
    return np.where(first[:, None], a1, a2)


@dataclass
class Groups:
    """Groups of near-identical lines ("spots") of a LineTable, clear lines first and best first:
    group g has the representative row rep[g] and the member rows members[start[g]:start[g + 1]]
    (the representative among them)."""
    rep: np.ndarray
    members: np.ndarray
    start: np.ndarray

    def __len__(self) -> int:
        return len(self.rep)

    def of(self, g: int) -> np.ndarray:
        return self.members[self.start[g]:self.start[g + 1]]

    def sizes(self) -> np.ndarray:
        return np.diff(self.start)

    @classmethod
    def each_alone(cls, n: int) -> "Groups":
        """Every line a group of its own (--all-lines)."""
        rows = np.arange(n, dtype=np.int64)
        return cls(rows, rows, np.arange(n + 1, dtype=np.int64))


def _rank(lines: LineTable, by: str) -> Tuple[np.ndarray, np.ndarray]:
    """The columns that order the lines, best representative first (both descending)."""
    c = lines.columns
    if by == "longest":
        return c["length"], c["clearance"]
    if by == "height":
        return c["height_max"], c["clearance"]
    return c["clearance"], c["length"]


GROUP_PART = 1 << 14  # lines (best first) per call of grouping.greedy, between progress updates


def _cell_index(xy: np.ndarray, rows: np.ndarray, distance: float):
    """The lines rows by the cell (of size `distance`) of their first anchor xy[rows], as numpy arrays.

    The cell numbers are those of `np.floor(xy / distance)`; one int64 key per line numbers the
    cells within the box of the lines' cells (x, then y), so the cells (x, y0) to (x, y1) have
    consecutive keys. Returns the positions in rows sorted by key (stably: the lines of a cell in
    their order), the sorted keys, the lowest and highest cell numbers and the width of a row of
    cells.
    """
    cell = []
    for axis in (0, 1):
        v = xy[rows, axis] / distance
        np.floor(v, out=v)
        cell.append(v.astype(np.int64))
        del v
    low = np.array([c.min() for c in cell], dtype=np.int64)
    high = np.array([c.max() for c in cell], dtype=np.int64)
    width = int(high[1] - low[1]) + 1
    key = cell[0]
    key -= low[0]
    key *= width
    key += cell[1]
    key -= low[1]
    del cell
    order = np.argsort(key, kind="stable")
    return order, key[order], low, high, width


def group_lines(lines: LineTable, distance: float, by: str = "clearance") -> Groups:
    """Group near-identical lines (both anchors within `distance` metres).

    Greedy grouping around a representative: the best remaining line (by length
    or clearance) takes every remaining line whose anchors are close to its own,
    so no member is further than `distance` from the representative. Lines over
    trees/buildings are grouped separately from clear lines.
    The same algorithm runs in the interactive map (viewer/src/grouping.ts); lines that
    rank the same keep their order (a stable sort, as sorted(reverse=True) there).
    Lines by the cell (of size `distance`) of their first anchor: a member's first anchor
    lies within `distance` of one of the representative's anchors, so in one of the 3 x 3
    cells around it. The loop is grouping.greedy (numba).
    """
    import grouping

    first, second = _rank(lines, by)
    over_all = lines.columns["over_obstacles"]
    a1, a2 = lines.columns["a1_xy"], lines.columns["a2_xy"]
    n = len(lines)
    members = np.empty(n, dtype=np.int64)  # every line is the member of one group
    reps = sizes = np.zeros(0, dtype=np.int64)
    n_reps = n_members = 0
    progress.compute.start("grouping lines", n, unit="line")
    for over in (False, True):
        rows = np.flatnonzero(over_all == over)
        if not len(rows):
            continue
        rows = rows[np.lexsort((-second[rows], -first[rows]))]
        order, keys, low, high, width = _cell_index(a1, rows, distance)
        free = np.ones(len(rows), dtype=bool)
        r0, m0 = n_reps, n_members
        for begin in range(0, len(rows), GROUP_PART):
            end = min(begin + GROUP_PART, len(rows))
            if len(reps) < n_reps + end - begin:  # room for a representative per line
                grown = max(2 * len(reps), n_reps + end - begin)
                reps, sizes = (np.concatenate([v[:n_reps], np.zeros(grown - n_reps, dtype=np.int64)])
                               for v in (reps, sizes))
            before = n_members
            n_reps, n_members = grouping.greedy(a1, a2, rows, order, keys, low, high, width, float(distance),
                                                float(distance ** 2), free, begin, end, reps, members, sizes,
                                                n_reps, n_members)
            progress.compute.update(n_members - before, spots=n_reps)
        del order, keys, free
        reps[r0:n_reps] = rows[reps[r0:n_reps]]  # positions in rows to rows of the table
        members[m0:n_members] = rows[members[m0:n_members]]
    progress.compute.finish(f"{n_reps} spots")
    # Clear lines first, then lines over trees/buildings; best first within each
    rep, sizes = reps[:n_reps], sizes[:n_reps]
    order = np.lexsort((-second[rep], -first[rep], over_all[rep])) if n_reps else np.zeros(0, dtype=np.int64)
    start = np.concatenate([[0], np.cumsum(sizes, dtype=np.int64)]).astype(np.int64)
    out = np.empty(n_members, dtype=np.int64)
    grouping.gather(members, start, order, out)
    del members
    return Groups(rep[order], out, np.concatenate([[0], np.cumsum(sizes[order], dtype=np.int64)]).astype(np.int64))


def _search_area(area):
    """The search area (area.Area) as a polygon in WGS84 (geopandas)."""
    import geopandas as gpd

    return gpd.GeoSeries([area.shape_wgs84()], crs="EPSG:4326")


def mapify(results: List[Dict], area):
    """Visualize lines on a static map (matplotlib + OpenTopoMap)."""
    import contextily as ctx
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from shapely.geometry import LineString

    if not results:
        print("No lines to display.")
        return

    lines = [LineString([(r["anchor1"][1], r["anchor1"][0]), (r["anchor2"][1], r["anchor2"][0])])
             for r in results]
    colors = [COLOR_OBSTACLE if r["over_obstacles"] else COLOR_VALID for r in results]
    gdf = gpd.GeoDataFrame({"color": colors}, geometry=lines, crs="EPSG:4326")

    fig, ax = plt.subplots(figsize=(10, 10))
    _search_area(area).boundary.plot(
        ax=ax, color="black", linestyle="--", linewidth=0.8)
    gdf.plot(ax=ax, color=gdf["color"], linewidth=0.8, alpha=0.9)

    # Show circles at line midpoints
    midpoints = gpd.GeoDataFrame({"color": colors}, crs="EPSG:4326",
                                 geometry=[line.interpolate(0.5, normalized=True) for line in lines])
    midpoints.plot(ax=ax, color=midpoints["color"], markersize=100, marker="o", alpha=0.6, zorder=3)

    ctx.add_basemap(ax, crs=gdf.crs, source=ctx.providers.OpenTopoMap)
    plt.show()


VIEWER_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer", "dist")
VIEWER_FOLDER = "_viewer"  # in runs/: the viewer bundle shared by every map


def _relative_url(folder: str, html_path: str) -> str:
    """URL of a folder as seen from the HTML file (relative when possible)."""
    try:
        return os.path.relpath(folder, os.path.dirname(os.path.abspath(html_path))).replace(os.sep, "/")
    except ValueError:  # different drive on Windows
        return Path(os.path.abspath(folder)).as_uri()


def ortho_entry(ortho_service, ortho_cache: Optional[str], html_path: str) -> Optional[Dict]:
    """The `ortho` entry of a run's data.js (also the 3D view's patch, search.patch_of_line): the
    orthophoto service (a sources.OrthoService, None: no entry) and its cache folder as seen from
    the run's map.html."""
    if ortho_service is None:
        return None
    return {
        "name": ortho_service.name, "url": ortho_service.url, "layer": ortho_service.layer,
        "attribution": ortho_service.attribution,
        "base": {"url": ortho_service.base_url, "max_zoom": ortho_service.base_max_zoom}
                if ortho_service.base_url else None,
        "cache": _relative_url(ortho_cache, html_path) if ortho_cache else None,
        # a link for the attribution, when the service has one (a licence page, the provider's site)
        **({"attribution_url": url} if (url := getattr(ortho_service, "attribution_url", None)) else {}),
        # a WMS taking EPSG:4326 in lon-lat order only (OrthoService.wms_version; absent: 1.3.0)
        **({"wms_version": v} if (v := getattr(ortho_service, "wms_version", "1.3.0")) != "1.3.0" else {}),
        # a WMS asked in Web Mercator (OrthoService.wms_crs; absent: EPSG:4326)
        **({"wms_crs": c} if (c := getattr(ortho_service, "wms_crs", "EPSG:4326")) != "EPSG:4326" else {})}


def install_viewer(runs_dir: str):
    """Copy the viewer bundle (viewer/dist, built from viewer/src) into runs/_viewer when it changed;
    one process at a time (cache.runs_lock: compute slots saving their runs at once)."""
    target = os.path.join(runs_dir, VIEWER_FOLDER)
    os.makedirs(target, exist_ok=True)
    with cache.runs_lock(runs_dir):
        for name in os.listdir(VIEWER_DIST):
            source, copy = os.path.join(VIEWER_DIST, name), os.path.join(target, name)
            with open(source, "rb") as f:
                content = f.read()
            if os.path.exists(copy):
                with open(copy, "rb") as f:
                    if f.read() == content:
                        continue
            with cache.replacing(copy) as f:
                f.write(content)


# A run's map: the viewer loads the run's data.js itself (viewer/src/map/main.tsx: fetched with a progress bar
# from a server, a script from disk); maps written before 2026-11-04 load it by a tag before the viewer, which
# the viewer still takes
MAP_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Find-a-Line</title>
<link rel="stylesheet" href="../{viewer}/viewer.css">
</head><body><div id="map"></div>
<script src="../runs.js"></script>
<script src="../{viewer}/viewer.js"></script>
</body></html>
"""


LINES_CHUNK = 1_000  # lines written between two progress updates (their texts held meanwhile)


def _script_head(target: str, value: Dict) -> str:
    """The start of a script that assigns value (pages opened from disk cannot fetch JSON) with
    its last key "lines" still open: the text of json.dump of the whole value up to its first line."""
    assert list(value)[-1] == "lines"
    head = json.JSONEncoder(separators=(",", ":")).encode({k: v for k, v in value.items() if k != "lines"})
    return f"{target} = {head[:-1]},\"lines\":["


def map_rows(lines: LineTable, start: int, stop: int) -> List[str]:
    """The JSON texts of the rows of lines.js of lines start..stop (viewer/src/types.ts, toLine),
    without the profile that data.js adds as its last value (with the END_VALUES before it when the
    lines have them: map_heads' "ends"). The same text as json.dumps of the
    row as a list of Python values (round() of each, rounded() for those that may be missing),
    built column by column. Values used for grouping are not rounded, so the browser groups
    exactly like group_lines()."""
    c = {name: column[start:stop] for name, column in lines.columns.items()}
    text = lambda values, digits=None, empty_nan=False: column_texts(values, digits, empty_nan)[1]
    columns = [text(c["anchor1"][:, 0], 7), text(c["anchor1"][:, 1], 7), text(c["anchor2"][:, 0], 7),
               text(c["anchor2"][:, 1], 7), text(c["a1_xy"][:, 0]), text(c["a1_xy"][:, 1]), text(c["a2_xy"][:, 0]),
               text(c["a2_xy"][:, 1]), text(c["length"]), text(c["clearance"]), text(c["clearance_nmpt"], 2, True),
               text(c["elev_a1"], 2), text(c["elev_a2"], 2), text(c["over_obstacles"]), text(c["water_m"], 1),
               text(c["filled_m"], 1), text(c["height_max"]), text(c["height_mean"], 2), text(c["high_pct"], 1),
               text(c["angle1"], 1), text(c["angle2"], 1), text(c["prom1"], 1, True), text(c["prom2"], 1, True),
               text(c["drop1"], 1, True), text(c["drop2"], 1, True)]
    if END_VALUES[0] in c:  # with an end zone or A-frames: the heads' "ends", before the profile
        columns += [text(c[name], 2) for name in END_VALUES]
    return list(map(",".join, zip(*columns))) if stop > start else []


MAP_FILES = ("data.js", "lines.js")  # the scripts of a map (write_map_scripts); save_map adds map.html


def save_map(lines: LineTable, area, run_path: str, runs_dir: str, run: Dict, crs: str,
             group_distance: float = 20, group_by: str = "clearance", ortho_cache: Optional[str] = None,
             ortho_service=None, model: str = "formula", rigging: Optional[Rigging] = None,
             on_lines=lambda n, file: None, high_above: float = HIGH_ABOVE,
             files: tuple = MAP_FILES + ("map.html",)) -> str:
    """Save the interactive map of a run: map.html, data.js and lines.js in its folder.

    The map is the viewer (viewer/src, TypeScript), the same bundle for every run in
    runs/_viewer; data.js holds the run's lines with their profiles
    (window.FINDALINE_RUN, read by viewer/src/types.ts), lines.js the same lines
    without profiles, which other maps load to show this run with theirs
    (window.FINDALINE_LINES[id]). Lines are grouped in the
    browser like group_lines. Orthophoto tiles are read from ortho_cache (a
    {z}/{x}/{y}.jpg folder) when present there, and from the WMS of ortho_service
    (a sources.OrthoService) otherwise. Both scripts are written together, LINES_CHUNK
    lines at a time, never all rows at once (write_map_scripts; the children of saving.py
    write them apart); on_lines(n, file) reports progress after each chunk. `files`: only
    those of the three; map.html also installs the viewer. Returns the path of map.html.
    """
    path = os.path.join(run_path, "map.html")
    if "map.html" in files:
        install_viewer(runs_dir)
    scripts = tuple(name for name in MAP_FILES if name in files)
    if scripts:
        heads = map_heads(area, path, run, crs, group_distance, group_by, ortho_cache, ortho_service, model,
                          rigging, high_above)
        write_map_scripts(lines, run_path, heads, on_lines, scripts)
    if "map.html" in files:
        with open(path, "w", encoding="utf-8") as f:
            f.write(MAP_HTML.format(title=html.escape(run["name"]), viewer=VIEWER_FOLDER))
    return path


def map_heads(area, path: str, run: Dict, crs: str, group_distance: float = 20, group_by: str = "clearance",
              ortho_cache: Optional[str] = None, ortho_service=None, model: str = "formula",
              rigging: Optional[Rigging] = None, high_above: float = HIGH_ABOVE) -> Tuple[str, str]:
    """The heads of data.js and lines.js of a run (save_map's arguments; `path` its map.html,
    which the orthophoto cache's URL is relative to): everything before the lines. The run's end
    zone and A-frames (run.json's params "end_zone", "anchor_lift") go into both heads as
    "end_zone" and "lift", each only when set (a run without them: the heads of before), and then
    "ends": the names of the values its rows hold after the drop below anchor 2 and before the
    profile (helpers.END_VALUES: the A-frame heights each line needs, map_rows)."""
    params = run.get("params") or {}
    ends = {key: params[name] for key, name in (("end_zone", "end_zone"), ("lift", "anchor_lift"))
            if params.get(name)}
    if ends:
        ends["ends"] = list(END_VALUES)
    data = {
        "run": {"id": run["id"], "name": run["name"], "created": run["created"],
                "description": run.get("description", "")},
        "center": list(area.center),
        "area": area.shape_wgs84().__geo_interface__,
        "crs": crs,
        "ortho": ortho_entry(ortho_service, ortho_cache, path),
        "attribution": run.get("attribution", []),  # credits of the data used (sources.Credit)
        "distance": group_distance, "by": group_by, "model": model,
        "rigging": dataclasses.asdict(rigging or Rigging()),
        "slope": SLOPE, "leash_fall": LEASH_FALL, **ends, "high_above": high_above, "max_zoom": MAX_ZOOM,
        "terrain": run.get("terrain"),  # the search area's (hypsometry.statistics), None when not known
        "shore": run.get("shore"),  # the uncertain shore (sources.filling.shore_segments), None when not known
        "lines": None,
    }
    if run.get("terrain_sources"):  # where the area's terrain came from (sources.filling.terrain_origins), when known
        data = {**{k: v for k, v in data.items() if k != "lines"}, "terrain_sources": run["terrain_sources"], "lines": None}
    target = f"(window.FINDALINE_LINES = window.FINDALINE_LINES || {{}})[{json.dumps(run['id'])}]"
    return (_script_head("window.FINDALINE_RUN", data),
            _script_head(target, {"crs": crs, "area": data["area"], "terrain": data["terrain"], **ends,
                                  "lines": None}))


def write_map_scripts(lines: LineTable, run_path: str, heads: Tuple[str, str], on_lines=lambda n, file: None,
                      files: tuple = MAP_FILES):
    """data.js and lines.js (`files`: only one of them) of a run: their heads (map_heads), then
    the lines LINES_CHUNK at a time (map_rows; data.js with each line's profile, or null)."""
    encoder = json.JSONEncoder(separators=(",", ":"))
    want_full, want_short = "data.js" in files, "lines.js" in files
    label = ", ".join(name for name in MAP_FILES if name in files)
    with contextlib.ExitStack() as stack:
        full = short = None
        if want_full:
            full = stack.enter_context(open(os.path.join(run_path, "data.js"), "w", encoding="utf-8"))
            full.write(heads[0])
        if want_short:
            short = stack.enter_context(open(os.path.join(run_path, "lines.js"), "w", encoding="utf-8"))
            short.write(heads[1])
        for start in range(0, len(lines), LINES_CHUNK):
            stop = min(start + LINES_CHUNK, len(lines))
            separator = "," if start else ""
            rows = map_rows(lines, start, stop)
            profiles = lines.profiles
            if full is not None:
                full.write(separator + ",".join(
                    f"[{row},{encoder.encode(profile_dict(profiles[k])) if k in profiles else 'null'}]"
                    for k, row in enumerate(rows, start)))
            if short is not None:
                short.write(separator + ",".join(f"[{row}]" for row in rows))
            on_lines(stop - start, label)
        if full is not None:
            full.write("]};\n")
        if short is not None:
            short.write("]};\n")
