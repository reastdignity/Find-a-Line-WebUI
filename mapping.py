"""
Converting results to GPS coordinates and displaying them on maps.
"""

import dataclasses
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from pyproj import Transformer

import cache
from grid import Grid
from helpers import END_VALUES, HIGH_ABOVE, LEASH_FALL, SLOPE, LineTable
from progress import progress
from runs import ACCESS, STANDS_FOR, round_floats
# A run's map page (its template, the disk notice, the viewer's folder) is runs.py's, where the web process may import
# it (a renamed run's map.html: runs.rename_run); mapping keeps the names for its users
from runs import DISK_NOTICE, MAP_HTML, VIEWER_FOLDER, map_page  # noqa: F401
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


# The result view's columns (view_columns; docs/line-volume/spec-view.md B.3, spec-store.md 1.3)
SECTORS_MAX = 10  # sectors of a run's spots at most
SECTOR_WORDS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
SECTOR_CENTRE_M = 150.0  # a sector whose shown lines' middle lies nearer the run's centre than this is "centre",
SECTOR_CENTRE_SHARE = 0.12  # or nearer than this share of the lines' extent in a small run
STACK_CELL = 8.0  # m: the plan cells of the top-level flag (K-17 'Higher wins on a face', tools/prune_study.py)
STACK_STEP = 10.0  # m: a stack spans this much mean anchor height or more; its top level is this thick
VIEW_COLUMNS = ("spot", "top", "by_spot")  # the store's columns view_columns gives (linestore.VIEW)
# Ward's clustering of the sectors takes memory by the square of its spots (scipy's linkage: about 16 B per pair, its
# distances and a copy): every spot up to this many, above it this many taken evenly (_ward_sectors). Measured
# 2026-11-16 (docs/performance.md, "The result view's columns"): the largest cap whose extra peak stays under 900 MB
# both at the cap (exact Ward) and above it (1.5 M lines in 200 000 spots); at least the goal case's 8 269 spots
SECTOR_WARD_SPOTS = 10_000
NEAREST_PART = 1 << 16  # spots per step of the nearest centroid (their distances to the centroids held meanwhile)


def _stored(values: np.ndarray, decimals: int) -> np.ndarray:
    """A value as the run's store holds it (linestore: round() to map_rows' decimals; NaN stays NaN)."""
    return round_floats(np.asarray(values, dtype=np.float64), decimals)


def _highest_first(values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two lexsort keys (the second the more significant) that put values highest first and NaN after every
    number, infinities included."""
    missing = np.isnan(values)
    return np.where(missing, 0.0, -values), missing


def _in_spot_order(spot: np.ndarray, mean: np.ndarray, clearance: np.ndarray, length: np.ndarray) -> np.ndarray:
    """The rows by spot, inside a spot by mean height, clearance, length (each highest first; NaN after every
    number), then the row."""
    keys = [key for v in (length, clearance, mean) for key in _highest_first(v)]
    return np.lexsort((np.arange(len(spot)), *keys, spot))


def _nearest(points: np.ndarray, centres: np.ndarray) -> np.ndarray:
    """The index of each point's nearest centre (squared distance; a tie to the lower index), NEAREST_PART points
    at a time."""
    out = np.empty(len(points), dtype=np.int64)
    for at in range(0, len(points), NEAREST_PART):
        part = points[at:at + NEAREST_PART]
        out[at:at + len(part)] = np.argmin(((part[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2), axis=1)
    return out


def _ward_sectors(ends: np.ndarray) -> np.ndarray:
    """A sector per spot (0 .. k-1, unnumbered; a number may be unused) from the ends of the spots' shown lines (a
    row per spot: west end x, y, east end x, y): Ward's clustering (scipy) cut into at most SECTORS_MAX clusters;
    a run of at most SECTORS_MAX spots has a sector per spot (the accepted mock-up's data, P7's tree_lib.sectors).
    Above SECTOR_WARD_SPOTS spots Ward's clustering takes that many spots evenly in their order (group_lines':
    a fixed choice, no random draw) and every spot joins the cluster whose mean of the taken spots' ends is the
    nearest (the user's choice of 2026-11-16, "Sample")."""
    n = len(ends)
    if n <= SECTORS_MAX:
        return np.arange(n, dtype=np.int64)
    from scipy.cluster.hierarchy import fcluster, linkage
    cut = lambda points: fcluster(linkage(points, method="ward"), SECTORS_MAX,  # noqa: E731
                                  criterion="maxclust").astype(np.int64) - 1
    if n <= SECTOR_WARD_SPOTS:
        return cut(ends)
    taken = np.unique(np.linspace(0, n - 1, SECTOR_WARD_SPOTS).round().astype(np.int64))
    label = cut(ends[taken])
    sizes = np.bincount(label)
    centres = np.column_stack([np.bincount(label, ends[taken, k]) for k in range(ends.shape[1])])
    centres = centres[sizes > 0] / sizes[sizes > 0, None]
    return _nearest(ends, centres)


def top_level(x1: np.ndarray, y1: np.ndarray, x2: np.ndarray, y2: np.ndarray, e1: np.ndarray, e2: np.ndarray,
              cell: float = STACK_CELL, step: float = STACK_STEP) -> np.ndarray:
    """The top-level flag of every line (K-17 'Higher wins on a face', tools/prune_study.py's rule
    higher_wins): the lines whose two ends fall into the same plan cells (`cell` m, a corner at (0, 0), the
    ends in the order of stack_buckets) form a bucket; in a bucket whose mean anchor heights ((e1 + e2) / 2)
    span `step` m or more, a line whose mean anchor height lies `step` m or more below the bucket's highest is
    not top level. Every other line is. Neighbouring buckets are not compared."""
    n = len(x1)
    if not n:
        return np.zeros(0, dtype=bool)
    swap = (x1 > x2) | ((x1 == x2) & (y1 < y2))
    cell_of = lambda v: np.floor(v / float(cell)).astype(np.int64)  # noqa: E731
    cx1, cy1, cx2, cy2 = cell_of(x1), cell_of(y1), cell_of(x2), cell_of(y2)
    keys = (np.where(swap, cx2, cx1), np.where(swap, cy2, cy1), np.where(swap, cx1, cx2), np.where(swap, cy1, cy2))
    del cx1, cy1, cx2, cy2
    order = np.lexsort(keys[::-1])
    new = np.zeros(n, dtype=bool)
    for key in keys:
        s = key[order]
        new[1:] |= s[1:] != s[:-1]
    starts = np.flatnonzero(np.concatenate([[True], new[1:]]))
    bucket = np.empty(n, dtype=np.int64)
    bucket[order] = np.cumsum(new)
    height = (np.asarray(e1, dtype=np.float64) + np.asarray(e2, dtype=np.float64)) / 2
    highest = np.maximum.reduceat(height[order], starts)[bucket]
    lowest = np.minimum.reduceat(height[order], starts)[bucket]
    return ~(((highest - lowest) >= float(step)) & (height <= highest - float(step)))


def view_columns(lines: LineTable, groups: Groups, centre: Tuple[float, float]) -> Tuple[Dict[str, np.ndarray], Dict]:
    """The result view's columns of a run's lines (docs/line-volume/spec-store.md 1.3, spec-view.md B.3), computed
    once at saving from the values as the run's store holds them (mean height and the anchors' elevations at
    map_rows' 2 decimals, the rest unrounded), so the page that reads them sees the same order; deterministic
    and the same on every number of threads (numpy and scipy, no threads of their own here).

    lines: a LineTable after coordify; groups: its spots (group_lines at the run's distance and value: their
    members never change, only their numbers); centre: the run's centre (run.json's center x, y) in the grid
    CRS. Returns ({"spot", "top", "by_spot"}, {"sectors", "box", "lengths"}):
      spot     uint32 per line: its spot's number. The spots are numbered from 0 in the order of their sectors,
               inside a sector by their first line's mean height, highest first (NaN last), then group_lines'
               order; a spot's label is "<sector>.<k>" (k = its number less its sector's first, plus one).
      top      uint8 per line: 1 when it is top level (top_level).
      by_spot  uint32: the rows by spot, inside a spot by mean height, clearance, length (each highest first,
               NaN last), then the row: a spot's lines are one run of it, its first line the spot's shown line.
      sectors  [{"word": ..., "spots": n}, ...] in sector order, none empty: Ward's clustering of each spot's
               shown line's ends (the west end first; _ward_sectors) into at most SECTORS_MAX sectors (above
               SECTOR_WARD_SPOTS spots Ward's clustering of that many taken evenly, every spot then to the nearest
               cluster's mean), numbered by their best
               spot's mean height (then group_lines' order); the word one of SECTOR_WORDS by the bearing from
               the centre to the mean of its shown lines' middles, "centre" within min(SECTOR_CENTRE_M,
               SECTOR_CENTRE_SHARE x the lines' extent), the extent the larger side of the box.
      box      [x min, y min, x max, y max] of every anchor (m, grid CRS); lengths [shortest, longest] (m).
    A run without lines: empty columns, no sectors, box and lengths None."""
    c, n = lines.columns, len(lines)
    head: Dict = {"sectors": [], "box": None, "lengths": None}
    if not n:
        empty = np.zeros(0, dtype=np.uint32)
        return {"spot": empty, "top": np.zeros(0, dtype=np.uint8), "by_spot": empty.copy()}, head
    x1, y1 = c["a1_xy"][:, 0], c["a1_xy"][:, 1]
    x2, y2 = c["a2_xy"][:, 0], c["a2_xy"][:, 1]
    mean = _stored(c["height_mean"], 2)
    clearance, length = np.asarray(c["clearance"], dtype=np.float64), np.asarray(c["length"], dtype=np.float64)
    top = top_level(x1, y1, x2, y2, _stored(c["elev_a1"], 2), _stored(c["elev_a2"], 2))
    count = len(groups)
    group = np.empty(n, dtype=np.int64)  # group_lines' number of each line's spot
    group[groups.members] = np.repeat(np.arange(count, dtype=np.int64), groups.sizes())
    order = _in_spot_order(group, mean, clearance, length)
    first = order[groups.start[:-1]]  # each group's shown line (its first in the spot's order)
    west = (x1[first] < x2[first]) | ((x1[first] == x2[first]) & (y1[first] <= y2[first]))
    ends = np.column_stack([np.where(west, x1[first], x2[first]), np.where(west, y1[first], y2[first]),
                            np.where(west, x2[first], x1[first]), np.where(west, y2[first], y1[first])])
    cluster = _ward_sectors(ends)
    del ends
    value, missing = _highest_first(mean[first])  # a spot's score: its first line's mean height, NaN after all
    # Each cluster's best spot (highest score, then the lower group), the clusters numbered by it
    by_score = np.lexsort((np.arange(count), value, missing, cluster))
    leaders = by_score[np.flatnonzero(np.concatenate([[True], np.diff(cluster[by_score]) != 0]))]
    numbered = leaders[np.lexsort((leaders, value[leaders], missing[leaders]))]
    sector_of_cluster = np.empty(int(cluster.max()) + 1, dtype=np.int64)
    sector_of_cluster[cluster[numbered]] = np.arange(len(numbered))
    sector = sector_of_cluster[cluster]
    spot_of_group = np.empty(count, dtype=np.int64)
    spot_of_group[np.lexsort((np.arange(count), value, missing, sector))] = np.arange(count)
    spot = spot_of_group[group]
    by_spot = order[np.argsort(spot_of_group[group[order]], kind="stable")]  # the order inside a spot is kept
    xs, ys = np.concatenate([x1, x2]), np.concatenate([y1, y2])
    box = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
    del xs, ys
    centre_m = min(SECTOR_CENTRE_M, SECTOR_CENTRE_SHARE * max(box[2] - box[0], box[3] - box[1]))
    middle_x, middle_y = (x1[first] + x2[first]) / 2, (y1[first] + y2[first]) / 2
    sectors = []
    for s in range(len(numbered)):
        mine = sector == s
        dx, dy = float(np.mean(middle_x[mine])) - centre[0], float(np.mean(middle_y[mine])) - centre[1]
        bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360
        word = "centre" if math.hypot(dx, dy) < centre_m else SECTOR_WORDS[int((bearing + 22.5) // 45) % 8]
        sectors.append({"word": word, "spots": int(mine.sum())})
    finite = length[np.isfinite(length)]
    head.update(sectors=sectors, box=box if all(map(math.isfinite, box)) else None,
                lengths=[float(finite.min()), float(finite.max())] if len(finite) else None)
    return {"spot": spot.astype(np.uint32), "top": top.astype(np.uint8), "by_spot": by_spot.astype(np.uint32)}, head


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


def _relative_url(folder: str, html_path: str) -> str:
    """URL of a folder as seen from the HTML file (relative when possible)."""
    try:
        return os.path.relpath(folder, os.path.dirname(os.path.abspath(html_path))).replace(os.sep, "/")
    except ValueError:  # different drive on Windows
        return Path(os.path.abspath(folder)).as_uri()


def ortho_entry(ortho_service, ortho_cache: Optional[str], html_path: str) -> Optional[Dict]:
    """The `ortho` entry of a run's head (map_head; also the 3D view's patch, search.patch_of_line): the
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


def save_map(run_path: str, runs_dir: str, run: Dict) -> str:
    """Save the interactive map of a run, its map.html (map_page: with the disk notice), and install the viewer (the
    same bundle for every run in runs/_viewer), which reads the run's store over http(s) (viewer/src/result/load.ts;
    the head of the store is map_head's). Returns the path of map.html. Since store wave 4 a run keeps no data.js or
    lines.js (tests/old_scripts.py keeps a frozen copy of their writers for the tests)."""
    path = os.path.join(run_path, "map.html")
    install_viewer(runs_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(map_page(run))
    return path


def _ends(run: Dict) -> Dict:
    """The keys of a run's end zone, A-frames, access mark and square rule in its head (map_head): "end_zone" and
    "lift" each only when set, then "ends", the names of the line values after the drop below anchor 2 (helpers.
    END_VALUES: the A-frame heights each line needs; runs.ACCESS: each anchor's answer; runs.STANDS_FOR last, with
    "square" and "found" of the square rule); "access_skipped" of a mark asked but left out."""
    params = run.get("params") or {}
    ends = {key: params[name] for key, name in (("end_zone", "end_zone"), ("lift", "anchor_lift"))
            if params.get(name)}
    if ends:
        ends["ends"] = list(END_VALUES)
    if params.get("access"):  # the access mark: named only (the page reads a value by its name in "ends")
        ends["ends"] = ends.get("ends", []) + ACCESS
    if run.get("access_skipped"):  # the mark asked but left out ("memory": the area too wide): no columns
        ends["access_skipped"] = run["access_skipped"]
    if params.get("same_line_side"):
        ends.update(square=params["same_line_side"], found=run["summary"]["found"],
                    ends=ends.get("ends", []) + [STANDS_FOR])
    return ends


def map_head(area, path: str, run: Dict, crs: str, group_distance: float = 20, group_by: str = "clearance",
             ortho_cache: Optional[str] = None, ortho_service=None, model: str = "formula",
             rigging: Optional[Rigging] = None, high_above: float = HIGH_ABOVE) -> Dict:
    """The head of a run's store (linestore.write, the schema's metadata; data.js's head before store wave 4), which
    the search writes with or without a map."""
    ends = _ends(run)
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
    }
    if run.get("terrain_sources"):  # where the area's terrain came from (sources.filling.terrain_origins), when known
        data["terrain_sources"] = run["terrain_sources"]
    return data
