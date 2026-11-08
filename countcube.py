"""The counter cube of a country (docs/country-precompute/contract.md, sections 2 and 6).

A country is searched in fixed tiles that keep only counts: for each cell of the global lattice
(30″ × 30″ by longitude and latitude, the same for every country) and each combination of filter
bins, the number of lines and of spots (pairs of 1.5″ anchor clusters with at least one line).
Each count is a row [key_a, key_b, count] of a sorted int64 array; the key is two words:

    word A: bits 0-1 water (bit 0: not over water, bit 1: over water), 2-3 trees (bit 2: not over
    trees or buildings, bit 3: over them), 4-6 height bin, 7-9 clearance bin, 10-12 wall bin,
    13-15 prominence bin (the weaker anchor's), 16-24 length mask (bit 16 + k: length bin k),
    25-26 border (0 interior, 1 across the border and owned, 2 across it and the partner's), 27-29
    partner (0 none, 1-6 an index into cube.json's neighbours, 7 unknown), 30-45 cell row j, 46-61
    cell column i (in cells from the country's origin);
    word B: 3-bit bins from bit 0, in the order of B_FIELDS: metres over water, the lower anchor's
    height, the upper anchor's, the webbing's mean height, the stronger anchor's prominence, the
    drop below both anchors, the share high above the terrain, the anchors' height difference, the
    clearance over trees and buildings, the A-frame needed with the no-fall zone and without it;
    bits 33-62 reserved (0).

All but the cell are a line's (or a spot's) record: RECORD_BITS of word A and all of word B. A
line sets one bit of each flag pair and one length bit; a spot's record merges those of its lines
(merge_spots: a floor's bin the largest, a ceiling's the smallest), so a spot passes one filter
exactly when some line of it does, and several filters as an upper bound. The border and the
partner are a spot's identity, not merged: a spot with lines of two border values is two spots.

TileCounter counts the lines search.count_tile hands it, save_tile/load_tile keep a tile's counts,
build sums the tiles into the cube (levels of 1, 2, 4 and 8 cells), Cube reads it for the web's
layer, cell_request gives the search of one cell. Pure numpy, pyproj and shapely: the web process
imports this module, so it never imports numba, linesearch, search or country.
"""
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import shape

import cache

VERSION = 2           # tile files and cubes of another version are refused (computed again, no migration)
CELLS_PER_DEGREE = 120  # the global lattice: cells of 30″
CELL_DEG = 1.0 / CELLS_PER_DEGREE
LEVELS = (1, 2, 4, 8)   # a level's cell: L × L cells of the lattice
ALIGN_CELLS = 8         # a country's origin: floored to a multiple of this many cells (1/15°)
CLUSTERS_PER_CELL = 20  # a spot's anchor clusters: 1.5″ (46 m north-south, 30 m east-west at 49°)
CLUSTERS_PER_DEGREE = CELLS_PER_DEGREE * CLUSTERS_PER_CELL
LENGTH_EDGES = (30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000)  # 9 bins [e_k, e_k+1); 5000 in the last
EDGES = {             # the edges of the 3-bit dimensions (KINDS: how they are binned and filtered)
    # word A
    "prominence": (0, 5, 10, 20, 50),   # of the weaker anchor: np.minimum(prom1, prom2)
    "wall": (0, 30, 45, 60, 90),        # of the steeper anchor: np.maximum(angle1, angle2)
    "clearance": (0, 2, 5, 10, 20),     # "clearance" over the terrain
    "height": (0, 10, 20, 50, 100),     # "height_max" of the webbing over the terrain
    # word B: working values of the contract (docs/country-precompute/contract.md, "The key v2"),
    # to be chosen by the user on the measurement of wave A
    "water_m": (0, 5, 20, 50, 100),          # "water_px" × the resolution
    "elevation_low": (0, 500, 1000, 1500, 2000),   # np.minimum(elev_a1, elev_a2)
    "elevation_high": (0, 500, 1000, 1500, 2000),  # np.maximum(elev_a1, elev_a2)
    "height_mean": (0, 10, 20, 50, 100),     # "height_mean" of the webbing over the terrain
    "prominence_high": (0, 5, 10, 20, 50),   # of the stronger anchor: np.maximum(prom1, prom2)
    "drop": (0, 20, 50, 100, 200),           # below both anchors: np.minimum(drop1, drop2)
    "high_pct": (0, 25, 50, 75, 90),         # "high_pct"
    "height_diff": (0, 5, 10, 20, 50),       # |elev_a1 - elev_a2|
    "clearance_trees": (0, 2, 5, 10, 20),    # "clearance_nmpt" (NaN without a surface model)
    "lift_needed": (0, 0.5, 1, 1.5, 2),      # "lift_needed" (absent without the options)
    "lift_no_zone": (0, 0.5, 1, 1.5, 2),     # "lift_no_zone"
}
UNKNOWN = 7           # a 3-bit dimension whose value is NaN (or absent)

# How a dimension is binned, merged and filtered:
#   floor:   bins [e_k, e_k+1) (below the first edge bin 0, the last open upwards); a filter passes
#            at or above its edge (the first edge: off); a spot takes its lines' largest bin
#   below:   binned as a floor; a filter passes below its edge (None: off; for the new ones the
#            first edge too, the wall keeps today's meaning of 0: nothing); a spot takes the smallest
#   at_most: bins (e_k-1, e_k] (at most the first edge bin 0, above the last bin len(edges)); a
#            filter passes at most its edge (None: off); a spot takes the smallest bin
KINDS = {"prominence": "floor", "wall": "below", "clearance": "floor", "height": "floor",
         "water_m": "floor", "elevation_low": "floor", "elevation_high": "below", "height_mean": "floor",
         "prominence_high": "floor", "drop": "floor", "high_pct": "floor", "height_diff": "below",
         "clearance_trees": "floor", "lift_needed": "at_most", "lift_no_zone": "at_most"}

# Word A's fields: (first bit, width)
WATER_BIT, TREES_BIT = 0, 2
SHIFT = {"height": 4, "clearance": 7, "wall": 10, "prominence": 13}  # word A's 3-bit dimensions
LENGTH_SHIFT = 16
LENGTH_BINS = len(LENGTH_EDGES) - 1
BORDER_SHIFT, PARTNER_SHIFT = 25, 27
BP_SHIFT, BP_MASK = 25, 31         # border and partner together: a spot's identity besides its id
RECORD_BITS = 30                   # word A's record; word B is all record
RECORD_MASK = (1 << RECORD_BITS) - 1
ROW_SHIFT, COL_SHIFT = 30, 46
CELL_BITS = 16        # rows and columns: up to 65536 cells of the lattice (546°)
CELL_MASK = (1 << CELL_BITS) - 1
# Word B's 3-bit dimensions, from bit 0
B_FIELDS = ("water_m", "elevation_low", "elevation_high", "height_mean", "prominence_high", "drop", "high_pct",
            "height_diff", "clearance_trees", "lift_needed", "lift_no_zone")
B_SHIFT = {name: 3 * k for k, name in enumerate(B_FIELDS)}
B_BITS = 3 * len(B_FIELDS)
# The bits merge_spots ORs: the flag pairs and the length mask
OR_MASK = 0xF | (((1 << LENGTH_BINS) - 1) << LENGTH_SHIFT)

# Spot ids: p.cx << 42 | p.cy << 22 | dx << 11 | (dy + 1024)
SPOT_CX_SHIFT, SPOT_CY_SHIFT = 42, 22
SPOT_C_BITS = 20                   # cx and cy (from the country's origin)
SPOT_D_BITS = 11                   # dx (0..2047) and dy + 1024 (dy -1024..1023)
SPOT_C_MASK = (1 << SPOT_C_BITS) - 1

PENDING_MAX = 4_000_000  # entries waiting before they are reduced (or the size of the reduced arrays, if larger)

# WGS84, for the km² of a cell and the metres of a buffer without pyproj
_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)
_B = _A * (1 - _F)


def _bins8(values: np.ndarray, edges, at_most: bool = False) -> np.ndarray:
    """The 3-bit bins of values (uint8), by comparisons with the edges (about three times faster
    than searchsorted over a few edges): over lower edges the count of edges after the first at or
    below the value (below the first bin 0, the last open upwards), over upper edges (at_most) the
    count of edges below it (at most the first bin 0, above the last len(edges)); NaN UNKNOWN."""
    values = np.asarray(values, dtype=np.float64)
    b = np.zeros(values.shape, dtype=np.uint8)
    for edge in (edges if at_most else edges[1:]):
        b += (values > edge) if at_most else (values >= edge)
    b[np.isnan(values)] = UNKNOWN
    return b


def _bin(values: np.ndarray, edges) -> np.ndarray:
    """The 3-bit bins of values over lower edges: below the first bin 0, the last open upwards,
    NaN UNKNOWN (int64)."""
    return _bins8(values, edges).astype(np.int64)


def _bin_at_most(values: np.ndarray, edges) -> np.ndarray:
    """The 3-bit bins of values over upper edges: at most the first bin 0, above the last
    len(edges), NaN UNKNOWN (int64)."""
    return _bins8(values, edges, at_most=True).astype(np.int64)


def bin_of(name: str, values: np.ndarray, edges=None) -> np.ndarray:
    """The bins of a dimension's values (its KINDS rule; edges: EDGES[name] unless given)."""
    edges = EDGES[name] if edges is None else edges
    return _bin_at_most(values, edges) if KINDS[name] == "at_most" else _bin(values, edges)


def bins_of(name: str) -> int:
    """How many bins a dimension has besides UNKNOWN: its edges, one more for an at_most."""
    return len(EDGES[name]) + (KINDS[name] == "at_most")


def length_bin(lengths: np.ndarray) -> np.ndarray:
    """The length bin k of each length: [e_k, e_k+1), 5000 (the last edge) in the last bin; lengths
    off the edges go to the nearest bin."""
    b = np.searchsorted(np.asarray(LENGTH_EDGES, dtype=np.float64), np.asarray(lengths, dtype=np.float64),
                        side="right").astype(np.int64) - 1
    return np.clip(b, 0, LENGTH_BINS - 1)


def dimension_values(columns: Mapping[str, np.ndarray], res: float) -> Dict[str, np.ndarray]:
    """The value of each dimension of word B per line, from a part's columns (float64; NaN: unknown;
    the A-frame fields NaN when the part has no such column)."""
    c = columns

    def column(name):
        return np.asarray(c[name], dtype=np.float64)

    e1, e2 = column("elev_a1"), column("elev_a2")
    out = {"water_m": column("water_px") * float(res), "elevation_low": np.minimum(e1, e2),
           "elevation_high": np.maximum(e1, e2), "height_mean": column("height_mean"),
           "prominence_high": np.maximum(column("prom1"), column("prom2")),
           "drop": np.minimum(column("drop1"), column("drop2")), "high_pct": column("high_pct"),
           "height_diff": np.abs(e1 - e2), "clearance_trees": column("clearance_nmpt")}
    n = len(e1)
    for name in ("lift_needed", "lift_no_zone"):
        out[name] = column(name) if name in c else np.full(n, np.nan)
    return out


# The 3-bit dimensions in the order of _line_bins' rows: word A's, then word B's
DIMS3 = ("height", "clearance", "wall", "prominence") + B_FIELDS


def _line_bins(columns: Mapping[str, np.ndarray], res: float) -> Tuple[np.ndarray, np.ndarray]:
    """A part's lines as their flags (int64: the water and trees bits, the length bit, border and
    partner) and the bins of DIMS3 ((15, n) uint8, a row a dimension)."""
    c = columns
    water = np.asarray(c["water_px"]) > 0
    with np.errstate(invalid="ignore"):
        trees = np.asarray(c["clearance_nmpt"], dtype=np.float64) <= 0  # NaN: not over
    flags = np.left_shift(1, WATER_BIT + water.astype(np.int64))
    flags |= np.left_shift(1, TREES_BIT + trees.astype(np.int64))
    flags |= np.left_shift(1, LENGTH_SHIFT + length_bin(c["length"]))
    if "border" in c:
        flags |= (np.asarray(c["border"]).astype(np.int64) & 3) << BORDER_SHIFT
    if "partner" in c:
        flags |= (np.asarray(c["partner"]).astype(np.int64) & 7) << PARTNER_SHIFT
    values = {"height": c["height_max"], "clearance": c["clearance"],
              "wall": np.maximum(c["angle1"], c["angle2"]), "prominence": np.minimum(c["prom1"], c["prom2"]),
              **dimension_values(c, res)}
    bins = np.empty((len(DIMS3), len(flags)), dtype=np.uint8)
    for k, name in enumerate(DIMS3):
        bins[k] = _bins8(values[name], EDGES[name], KINDS[name] == "at_most")
    return flags, bins


def _pack(flags: np.ndarray, bins: np.ndarray) -> np.ndarray:
    """Records ((n, 2) int64) of flags and the bins of DIMS3."""
    n = len(flags)
    out = np.empty((n, 2), dtype=np.int64)
    a, b = flags.copy(), np.zeros(n, dtype=np.int64)
    shifted = np.empty(n, dtype=np.int64)
    for k, name in enumerate(DIMS3):
        word, shift = (a, SHIFT[name]) if name in SHIFT else (b, B_SHIFT[name])
        np.left_shift(bins[k], shift, out=shifted, dtype=np.int64)
        word |= shifted
    out[:, 0], out[:, 1] = a, b
    return out


def line_records(columns: Mapping[str, np.ndarray], res: float = 1.0) -> np.ndarray:
    """The records of lines given as columns (the LINE_VALUES and "water_px"; "lift_needed",
    "lift_no_zone", "border" and "partner" when present): (n, 2) int64, word A's RECORD_BITS and
    word B. res: the grid's resolution (the metres over water are water_px × res)."""
    return _pack(*_line_bins(columns, res))


def pack_keys(i: np.ndarray, j: np.ndarray, records: np.ndarray) -> np.ndarray:
    """Keys of cells (i, j) with their records ((n, 2): word A's record and word B): (n, 2) int64."""
    i, j = np.asarray(i, dtype=np.int64), np.asarray(j, dtype=np.int64)
    records = np.asarray(records, dtype=np.int64).reshape(-1, 2)
    if len(i) and (i.min() < 0 or j.min() < 0 or i.max() > CELL_MASK or j.max() > CELL_MASK):
        raise ValueError("a cell lies outside the cube: check the country's origin")
    out = np.empty((len(i), 2), dtype=np.int64)
    out[:, 0] = (i << COL_SHIFT) | (j << ROW_SHIFT) | (records[:, 0] & RECORD_MASK)
    out[:, 1] = records[:, 1]
    return out


def unpack_keys(keys: np.ndarray) -> Dict[str, np.ndarray]:
    """The fields of keys ((n, 2)): "i", "j", "record" (word A's), "border", "partner", the bins of
    every dimension of EDGES, "length" (the mask), "water" and "trees" (their two bits)."""
    keys = np.asarray(keys, dtype=np.int64).reshape(-1, 2)
    a, b = keys[:, 0], keys[:, 1]
    out = {"i": a >> COL_SHIFT, "j": (a >> ROW_SHIFT) & CELL_MASK, "record": a & RECORD_MASK,
           "length": (a >> LENGTH_SHIFT) & ((1 << LENGTH_BINS) - 1), "water": a & 3, "trees": (a >> TREES_BIT) & 3,
           "border": (a >> BORDER_SHIFT) & 3, "partner": (a >> PARTNER_SHIFT) & 7}
    out.update({name: (a >> shift) & 7 for name, shift in SHIFT.items()})
    out.update({name: (b >> shift) & 7 for name, shift in B_SHIFT.items()})
    return out


def _field(keys: np.ndarray, name: str) -> np.ndarray:
    """The 3-bit bin of a dimension in keys or records ((n, 2))."""
    if name in SHIFT:
        return (keys[:, 0] >> SHIFT[name]) & 7
    return (keys[:, 1] >> B_SHIFT[name]) & 7


def _metres_per_degree(lat: float) -> Tuple[float, float]:
    """Metres per degree of longitude and of latitude at a latitude (WGS84)."""
    s = math.sin(math.radians(lat))
    w = math.sqrt(1 - _E2 * s * s)
    return (_A / w * math.cos(math.radians(lat)) * math.pi / 180,
            _A * (1 - _E2) / w ** 3 * math.pi / 180)


def cell_size_km(level: int, lat: float) -> Tuple[float, float]:
    """The size (east-west, north-south) in km of a level's cell at a latitude."""
    east, north = _metres_per_degree(lat)
    return east * level / CELLS_PER_DEGREE / 1000, north * level / CELLS_PER_DEGREE / 1000


def cluster_size_m(lat: float) -> Tuple[float, float]:
    """The size (east-west, north-south) in metres of a spot's anchor cluster at a latitude."""
    east, north = _metres_per_degree(lat)
    return east / CLUSTERS_PER_DEGREE, north / CLUSTERS_PER_DEGREE


def origin_of(bounds_wgs84: Tuple[float, float, float, float], reach_m: float) -> Tuple[int, int]:
    """A country's origin (I0, J0) in cells of the lattice: the south-west corner of its outline's box
    (WGS84: west, south, east, north) less reach_m (the longest line of its layer, so an anchor
    beyond the outline still lies inside the cube), floored to a multiple of ALIGN_CELLS cells."""
    west, south, east, north = (float(v) for v in bounds_wgs84)
    pole = min(max(abs(south), abs(north)), 89.0)
    dlat = reach_m / _metres_per_degree(0.0)[1]  # the fewest metres per degree of latitude
    dlon = reach_m / _metres_per_degree(min(pole + dlat, 89.5))[0]
    i0 = math.floor((west - dlon) * CELLS_PER_DEGREE / ALIGN_CELLS) * ALIGN_CELLS
    j0 = math.floor((south - dlat) * CELLS_PER_DEGREE / ALIGN_CELLS) * ALIGN_CELLS
    return int(i0), int(j0)


def clusters_of(lon: np.ndarray, lat: np.ndarray, origin: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
    """The anchor clusters (cx, cy) of points from the country's origin (in cells): 1/2400° each."""
    i0, j0 = int(origin[0]), int(origin[1])
    cx = np.floor(np.asarray(lon, dtype=np.float64) * CLUSTERS_PER_DEGREE).astype(np.int64) - CLUSTERS_PER_CELL * i0
    cy = np.floor(np.asarray(lat, dtype=np.float64) * CLUSTERS_PER_DEGREE).astype(np.int64) - CLUSTERS_PER_CELL * j0
    if len(cx) and (cx.min() < 0 or cy.min() < 0 or cx.max() > SPOT_C_MASK or cy.max() > SPOT_C_MASK):
        raise ValueError("an anchor lies outside the cube: check the country's origin")
    return cx, cy


def cluster_spot_ids(cx1, cy1, cx2, cy2) -> np.ndarray:
    """The spot of each line from its anchors' clusters: p the smaller (cx, cy), q the other,
    p.cx << 42 | p.cy << 22 | dx << 11 | (dy + 1024). ValueError for a line spanning more than
    2047 clusters east-west or 1023 north-south (a 5 km line at 78°: 520 east-west)."""
    cx1, cy1, cx2, cy2 = (np.asarray(v, dtype=np.int64) for v in (cx1, cy1, cx2, cy2))
    first = (cx1 < cx2) | ((cx1 == cx2) & (cy1 <= cy2))
    pcx, pcy = np.where(first, cx1, cx2), np.where(first, cy1, cy2)
    dx, dy = np.where(first, cx2, cx1) - pcx, np.where(first, cy2, cy1) - pcy
    half = 1 << (SPOT_D_BITS - 1)
    if len(dx) and (dx.max() >= 1 << SPOT_D_BITS or dy.min() < -half or dy.max() >= half):
        raise ValueError("a line spans more than 2047 anchor clusters east-west or 1023 north-south: "
                         "too long for a spot id (keep the band's longest line shorter at this latitude)")
    return (pcx << SPOT_CX_SHIFT) | (pcy << SPOT_CY_SHIFT) | (dx << SPOT_D_BITS) | (dy + half)


def spot_ids(lon1, lat1, lon2, lat2, origin: Tuple[int, int]) -> np.ndarray:
    """The spot of each line: the pair of the clusters of its anchors (lon, lat in degrees)."""
    cx1, cy1 = clusters_of(lon1, lat1, origin)
    cx2, cy2 = clusters_of(lon2, lat2, origin)
    return cluster_spot_ids(cx1, cy1, cx2, cy2)


def spot_cells(ids: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The cell (i, j) of each spot: that of its first cluster p."""
    ids = np.asarray(ids, dtype=np.int64)
    return ((ids >> SPOT_CX_SHIFT) // CLUSTERS_PER_CELL,
            ((ids >> SPOT_CY_SHIFT) & SPOT_C_MASK) // CLUSTERS_PER_CELL)


def _rows_order(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The order sorting rows (a, b) of non-negative int64 words lexicographically, and the starts
    of the runs of equal rows in that order. One int64 sort when a's distinct values and b's range
    fit 63 bits together (np.unique's inverse of a, then b), else np.lexsort."""
    ua, inverse = np.unique(a, return_inverse=True)
    lo = int(b.min())
    width = (int(b.max()) - lo).bit_length()
    if (len(ua) - 1).bit_length() + width <= 62:
        code = (inverse.astype(np.int64).reshape(-1) << width) | (b - lo)
        order = np.argsort(code)
        code = code[order]
        starts = np.flatnonzero(np.concatenate(([True], code[1:] != code[:-1])))
        return order, starts
    order = np.lexsort((b, a))
    sa, sb = a[order], b[order]
    starts = np.flatnonzero(np.concatenate(([True], (sa[1:] != sa[:-1]) | (sb[1:] != sb[:-1]))))
    return order, starts


def sum_keys(keys: np.ndarray, counts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted unique keys ((n, 2): by word A, then word B; or int64 of one dimension) and their
    summed counts."""
    keys = np.asarray(keys, dtype=np.int64)
    counts = np.asarray(counts, dtype=np.int64)
    if not len(keys):
        return keys.copy(), counts.copy()
    if keys.ndim == 1:
        order = np.argsort(keys)
        sk = keys[order]
        starts = np.flatnonzero(np.concatenate(([True], sk[1:] != sk[:-1])))
        return sk[starts], np.add.reduceat(counts[order], starts)
    order, starts = _rows_order(keys[:, 0], keys[:, 1])
    return keys[order[starts]], np.add.reduceat(counts[order], starts)


def count_keys(keys: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted unique keys ((n, 2), or int64 of one dimension) and how often each occurs."""
    keys = np.asarray(keys, dtype=np.int64)
    if keys.ndim == 1:
        u, n = np.unique(keys, return_counts=True)
        return u, n.astype(np.int64)
    if not len(keys):
        return keys.copy(), np.zeros(0, dtype=np.int64)
    a, b = keys[:, 0], keys[:, 1]
    ua, inverse = np.unique(a, return_inverse=True)
    lo = int(b.min())
    width = (int(b.max()) - lo).bit_length()
    if (len(ua) - 1).bit_length() + width <= 62:
        code, n = np.unique((inverse.astype(np.int64).reshape(-1) << width) | (b - lo), return_counts=True)
        out = np.empty((len(code), 2), dtype=np.int64)
        out[:, 0] = ua[code >> width]
        out[:, 1] = (code & ((1 << width) - 1)) + lo
        return out, n.astype(np.int64)
    return sum_keys(keys, np.ones(len(keys), dtype=np.int64))


# A bin as a value whose largest is the spot's (a floor's largest bin, a ceiling's smallest), 0 for
# UNKNOWN (so UNKNOWN only when every line's is), and back: one np.maximum.reduceat a dimension
_MERGED = np.zeros((len(DIMS3), 8), dtype=np.uint8)
_UNMERGED = np.zeros((len(DIMS3), 10), dtype=np.int64)
for _k, _name in enumerate(DIMS3):
    _floor = KINDS[_name] == "floor"
    for _b in range(8):
        _MERGED[_k, _b] = 0 if _b == UNKNOWN else (_b + 1 if _floor else 8 - _b)
    for _m in range(10):
        _UNMERGED[_k, _m] = UNKNOWN if _m == 0 else (_m - 1 if _floor else 8 - _m)


def _merge_bins(ids: np.ndarray, flags: np.ndarray, bins: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """merge_spots of lines given as flags and the bins of DIMS3 (_line_bins)."""
    bp = (flags >> BP_SHIFT) & BP_MASK
    if bp.any():
        order, starts = _rows_order(ids, bp)
    else:
        order = np.argsort(ids)
        sid = ids[order]
        starts = np.flatnonzero(np.concatenate(([True], sid[1:] != sid[:-1])))
    sorted_flags = flags[order]
    a = np.bitwise_or.reduceat(sorted_flags & OR_MASK, starts) | (sorted_flags[starts] & (BP_MASK << BP_SHIFT))
    b = np.zeros(len(starts), dtype=np.int64)
    for k, name in enumerate(DIMS3):
        merged = np.maximum.reduceat(_MERGED[k][bins[k][order]], starts)
        value = _UNMERGED[k][merged]
        if name in SHIFT:
            a |= value << SHIFT[name]
        else:
            b |= value << B_SHIFT[name]
    out = np.empty((len(starts), 2), dtype=np.int64)
    out[:, 0], out[:, 1] = a, b
    return ids[order[starts]], out


def merge_spots(ids: np.ndarray, records: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Spots of one (id, border, partner) merged: the ids and records ((m, 2)) sorted by id, then by
    border and partner. Word A: the length mask and the flag bits ORed, prominence, clearance and
    height the largest bin (UNKNOWN only when every one is), the wall the smallest (UNKNOWN
    likewise); word B: a floor's bin the largest, a ceiling's the smallest (KINDS). Commutative and
    associative, so partial merges may be merged again."""
    ids = np.asarray(ids, dtype=np.int64)
    records = np.asarray(records, dtype=np.int64).reshape(-1, 2)
    if not len(ids):
        return ids.copy(), records.copy()
    bins = np.empty((len(DIMS3), len(ids)), dtype=np.uint8)
    for k, name in enumerate(DIMS3):
        word, shift = (records[:, 0], SHIFT[name]) if name in SHIFT else (records[:, 1], B_SHIFT[name])
        bins[k] = (word >> shift) & 7
    return _merge_bins(ids, records[:, 0] & (OR_MASK | (BP_MASK << BP_SHIFT)), bins)


class _Reducer:
    """Pairs of (keys, values) collected part by part and reduced by `reduce` whenever more than
    PENDING_MAX entries (or as many as the reduced arrays hold) wait: amortised, bounded memory.
    keys: int64 of one dimension (spot ids) or (n, 2) (the keys of lines); values likewise."""

    def __init__(self, reduce):
        self.reduce = reduce
        self.keys: Optional[np.ndarray] = None
        self.values: Optional[np.ndarray] = None
        self.pending: List[Tuple[np.ndarray, np.ndarray]] = []
        self.waiting = 0

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        if not len(keys):
            return
        self.pending.append((keys, values))
        self.waiting += len(keys)
        if self.waiting > max(PENDING_MAX, 0 if self.keys is None else len(self.keys)):
            self.flush()

    def flush(self) -> Tuple[np.ndarray, np.ndarray]:
        if self.pending:
            held = [] if self.keys is None else [(self.keys, self.values)]
            keys = np.concatenate([k for k, _ in held + self.pending])
            values = np.concatenate([v for _, v in held + self.pending])
            self.pending, self.waiting = [], 0
            self.keys, self.values = self.reduce(keys, values)
        if self.keys is None:
            return None, None
        return self.keys, self.values


@dataclass
class TileCounts:
    line_keys: np.ndarray     # (n, 2) int64, sorted, unique
    line_counts: np.ndarray   # int64
    spot_ids: np.ndarray      # int64, sorted (with the border and partner of the records), unique with them
    spot_records: np.ndarray  # (m, 2) int64: word A's RECORD_BITS and word B
    lines: int                # lines counted
    dropped: int              # lines left out: outside lengths or with the first anchor outside core


def _empty_counts(lines: int = 0, dropped: int = 0) -> TileCounts:
    return TileCounts(np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64),
                      np.zeros((0, 2), dtype=np.int64), lines, dropped)


_TRANSFORMERS: Dict[str, Transformer] = {}


def _to_wgs84(crs: str) -> Transformer:
    """A transformer of a CRS to WGS84 (lon, lat), one per CRS and process."""
    found = _TRANSFORMERS.get(crs)
    if found is None:
        found = _TRANSFORMERS[crs] = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return found


# How a TileCounter counts: "numba", hash tables (countkernels.py, imported at the first part, never by
# the web process), or "numpy", the parts sorted and merged as they come (the reference of the tests)
ENGINE = "numba"
VALUE_COLUMNS = ("length", "clearance", "clearance_nmpt", "height_max", "height_mean", "high_pct", "angle1", "angle2",
                 "prom1", "prom2", "drop1", "drop2", "elev_a1", "elev_a2")  # countkernels.count's order

# The columns a TileCounter reads of a part (those of OPTIONAL_COLUMNS when present)
RECORD_COLUMNS = ("length", "clearance", "clearance_nmpt", "height_max", "height_mean", "high_pct", "angle1",
                  "angle2", "prom1", "prom2", "drop1", "drop2", "elev_a1", "elev_a2", "water_px")
OPTIONAL_COLUMNS = ("lift_needed", "lift_no_zone", "border", "partner")


class TileCounter:
    """The counts of one tile, fed part by part by search.count_tile (a LineTable with "a1", "a2",
    the LINE_VALUES and "water_px"; "lift_needed", "lift_no_zone", "border" and "partner" when the
    count gives them).

    A line is counted when its first anchor in pixel order (the smaller x, then y, as
    mapping.first_anchor) lies in `core` (left <= x < right, bottom <= y < top in the grid's CRS;
    None: everywhere) and its length within `lengths` (lo <= length < hi, or <= hi when `last`); a
    line across a border (its "border" not 0) skips the core's test: search.count_tile hands only
    those whose anchor in the country lies in the core.
    Its cell is that of its first anchor by (lon, lat) (the smaller lon, then lat) on the global
    lattice from `origin` (I0, J0) in cells: i = cx // 20 with cx = floor(lon × 2400) - 20 I0, which
    is floor(lon × 120) - I0 but for the rounding at a cell's edge, so a line and the cluster of its
    first anchor share a cell. Each anchor pixel of the tile goes to WGS84 once (pyproj). engine: ENGINE
    unless given; both give the same counts."""

    def __init__(self, grid, origin: Tuple[int, int], core: Optional[Tuple[float, float, float, float]],
                 lengths: Tuple[float, float], last: bool, engine: Optional[str] = None):
        self.engine = engine or ENGINE
        if self.engine not in ("numba", "numpy"):
            raise ValueError("the engine must be numba or numpy")
        self._tables = None  # countkernels.Tables of the engine numba, made at the first part
        self.grid = grid
        self.origin = (int(origin[0]), int(origin[1]))
        self.core = core
        self.lengths = (float(lengths[0]), float(lengths[1]))
        self.last = last
        self._transformer = _to_wgs84(grid.crs)
        self._lines = _Reducer(sum_keys)
        self._spots = _Reducer(merge_spots)
        self.lines = 0
        self.dropped = 0
        self.transform_seconds = 0.0  # the anchors' pixels to (lon, lat) and their clusters
        # The pixels transformed so far (sorted codes row * width + col) and their lon, lat, cx, cy:
        # each anchor of the tile goes through pyproj once, whatever the parts it is in
        self._codes = np.zeros(0, dtype=np.int64)
        self._lon = np.zeros(0, dtype=np.float64)
        self._lat = np.zeros(0, dtype=np.float64)
        self._cx = np.zeros(0, dtype=np.int64)
        self._cy = np.zeros(0, dtype=np.int64)

    def _lookup(self, unique: np.ndarray):
        """lon, lat, cx, cy of sorted distinct pixel codes: the ones not seen yet transformed (pyproj,
        point by point: a pixel's values do not depend on the batch) and kept."""
        codes = self._codes
        pos = np.searchsorted(codes, unique)
        seen = pos < len(codes)
        seen[seen] = codes[pos[seen]] == unique[seen]
        if not seen.all():
            new = unique[~seen]
            width = self.grid.width
            x, y = self.grid.pixel_to_xy(new // width, new % width)
            lon, lat = self._transformer.transform(x, y)
            lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
            cx, cy = clusters_of(lon, lat, self.origin)
            at = pos[~seen]
            self._codes = np.insert(codes, at, new)
            self._lon, self._lat = np.insert(self._lon, at, lon), np.insert(self._lat, at, lat)
            self._cx, self._cy = np.insert(self._cx, at, cx), np.insert(self._cy, at, cy)
            pos = np.searchsorted(self._codes, unique)
        return self._lon[pos], self._lat[pos], self._cx[pos], self._cy[pos]

    def anchors(self, a1: np.ndarray, a2: np.ndarray):
        """lon, lat, cx, cy of both anchors of each line (pixels [row, col]): the part's distinct
        pixels (a1's runs first: a part holds the pairs of one first anchor together) looked up in
        the tile's transformed pixels (_lookup)."""
        k = len(a1)
        width = self.grid.width
        code1 = a1[:, 0].astype(np.int64) * width + a1[:, 1]
        code2 = a2[:, 0].astype(np.int64) * width + a2[:, 1]
        heads = np.flatnonzero(np.concatenate(([True], code1[1:] != code1[:-1])))
        if 2 * len(heads) <= k:
            unique, inverse = np.unique(np.concatenate([code1[heads], code2]), return_inverse=True)
            inverse = inverse.reshape(-1)
            first = np.repeat(inverse[:len(heads)], np.diff(np.append(heads, k)))
            second = inverse[len(heads):]
        else:
            unique, inverse = np.unique(np.concatenate([code1, code2]), return_inverse=True)
            inverse = inverse.reshape(-1)
            first, second = inverse[:k], inverse[k:]
        lon, lat, cx, cy = self._lookup(unique)
        return (lon[first], lat[first], cx[first], cy[first]), (lon[second], lat[second], cx[second], cy[second])

    def _transform(self, codes: np.ndarray):
        """lon, lat, cx, cy of distinct pixel codes (row * width + col), through pyproj."""
        width = self.grid.width
        x, y = self.grid.pixel_to_xy(codes // width, codes % width)
        lon, lat = self._transformer.transform(x, y)
        lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        cx, cy = clusters_of(lon, lat, self.origin)
        return lon, lat, cx, cy

    def _count_numba(self, part) -> None:
        """A part into the tile's hash tables (countkernels)."""
        import countkernels as ck
        if self._tables is None:
            self._tables = ck.Tables()
        tables = self._tables
        c = part.columns
        a1 = np.ascontiguousarray(c["a1"], dtype=np.int64)
        a2 = np.ascontiguousarray(c["a2"], dtype=np.int64)
        n = len(a1)
        if not n:
            return
        g = self.grid
        core = np.asarray(self.core if self.core is not None else (0.0, 0.0, 0.0, 0.0), dtype=np.float64)
        kept, codes1, codes2 = (np.empty(n, dtype=np.int64) for _ in range(3))
        across = np.asarray(c["border"]).astype(np.int64) if "border" in c else np.empty(0, dtype=np.int64)
        k = ck.select(a1, a2, np.asarray(c["length"], dtype=np.float64), int(g.width), float(g.left), float(g.top),
                      float(g.res), core, self.core is not None, across, self.lengths[0], self.lengths[1],
                      bool(self.last), kept, codes1, codes2)
        self.dropped += n - k
        if not k:
            return
        self.lines += k
        kept = kept[:k]
        t = time.perf_counter()
        index = tables.indices(np.concatenate([codes1[:k], codes2[:k]]), self._transform)
        self.transform_seconds += time.perf_counter() - t
        values = [np.asarray(c[name], dtype=np.float64) for name in VALUE_COLUMNS]
        water = np.asarray(c["water_px"], dtype=np.float64)
        none_f, none_i = np.empty(0, dtype=np.float64), np.empty(0, dtype=np.int64)
        lifts = [np.asarray(c[name], dtype=np.float64) if name in c else none_f for name in ("lift_needed", "lift_no_zone")]
        sides = [np.asarray(c[name]).astype(np.int64) if name in c else none_i for name in ("border", "partner")]
        start = 0
        while True:
            start = ck.count(start, kept, index[:k], index[k:], tables.lon, tables.lat, tables.cx, tables.cy, *values,
                             water, *lifts, *sides, float(g.res), ck.EDGES, ck.AT_MOST, ck.SHIFTS, ck.IN_B,
                             ck.LENGTH_EDGES, _MERGED, tables.line_a, tables.line_b, tables.line_n, tables.line_used,
                             tables.spot_id, tables.spot_bp, tables.spot_flags, tables.spot_bins, tables.spot_used,
                             tables.used)
            if start == k:
                break
            tables.grow()

    def _result_numba(self) -> TileCounts:
        keys, lines, ids, bps, flags, bins = self._tables.counts()
        a, b = flags | (bps << BP_SHIFT), np.zeros(len(ids), dtype=np.int64)
        for k, name in enumerate(DIMS3):
            value = _UNMERGED[k][bins[:, k]]
            if name in SHIFT:
                a |= value << SHIFT[name]
            else:
                b |= value << B_SHIFT[name]
        records = np.empty((len(ids), 2), dtype=np.int64)
        records[:, 0], records[:, 1] = a, b
        return TileCounts(keys, lines, ids.astype(np.int64), records, self.lines, self.dropped)

    def __call__(self, part) -> None:
        if self.engine == "numba":
            self._count_numba(part)
            return
        c = part.columns
        a1, a2 = np.asarray(c["a1"]), np.asarray(c["a2"])
        n = len(a1)
        if not n:
            return
        length = np.asarray(c["length"], dtype=np.float64)
        lo, hi = self.lengths
        keep = (length >= lo) & ((length <= hi) if self.last else (length < hi))
        if self.core is not None:
            x1, y1 = self.grid.pixel_to_xy(a1[:, 0], a1[:, 1])
            x2, y2 = self.grid.pixel_to_xy(a2[:, 0], a2[:, 1])
            first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
            fx, fy = np.where(first, x1, x2), np.where(first, y1, y2)
            left, bottom, right, top = self.core
            in_core = (fx >= left) & (fx < right) & (fy >= bottom) & (fy < top)
            if "border" in c:  # across a border: search.count_tile handed it to the tile holding its own anchor
                in_core |= np.asarray(c["border"]) != 0
            keep &= in_core
            del x1, y1, x2, y2, first, fx, fy, in_core
        kept = int(np.count_nonzero(keep))
        self.dropped += n - kept
        if not kept:
            return
        self.lines += kept
        if kept < n:
            a1, a2 = a1[keep], a2[keep]
            columns = {name: np.asarray(c[name])[keep] for name in RECORD_COLUMNS + OPTIONAL_COLUMNS if name in c}
        else:
            columns = c
        flags, bins = _line_bins(columns, self.grid.res)
        records = _pack(flags, bins)
        t = time.perf_counter()
        (lon1, lat1, cx1, cy1), (lon2, lat2, cx2, cy2) = self.anchors(a1, a2)
        self.transform_seconds += time.perf_counter() - t
        first = (lon1 < lon2) | ((lon1 == lon2) & (lat1 <= lat2))
        i = np.where(first, cx1, cx2) // CLUSTERS_PER_CELL
        j = np.where(first, cy1, cy2) // CLUSTERS_PER_CELL
        self._lines.add(*count_keys(pack_keys(i, j, records)))
        self._spots.add(*_merge_bins(cluster_spot_ids(cx1, cy1, cx2, cy2), flags, bins))

    def result(self) -> TileCounts:
        if self.engine == "numba":
            return self._result_numba() if self._tables is not None else _empty_counts(self.lines, self.dropped)
        keys, counts = self._lines.flush()
        ids, records = self._spots.flush()
        empty = _empty_counts()
        if keys is None:
            keys, counts = empty.line_keys, empty.line_counts
        if ids is None:
            ids, records = empty.spot_ids, empty.spot_records
        return TileCounts(keys, counts, ids, records, self.lines, self.dropped)


def save_tile(path: str, counts: TileCounts, meta: Dict) -> None:
    """A tile's counts and its meta (JSON text) as a compressed .npz, written atomically."""
    with cache.replacing(path) as f:
        np.savez_compressed(f, version=np.int64(VERSION), meta=np.array(json.dumps(meta)),
                            line_keys=np.asarray(counts.line_keys, dtype=np.int64).reshape(-1, 2),
                            line_counts=counts.line_counts, spot_ids=counts.spot_ids,
                            spot_records=np.asarray(counts.spot_records, dtype=np.int64).reshape(-1, 2),
                            lines=np.int64(counts.lines), dropped=np.int64(counts.dropped))


def load_tile(path: str) -> Tuple[TileCounts, Dict]:
    """A tile's counts and meta; ValueError for a file of another VERSION."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"]) if "version" in z.files else None
        if version != VERSION:
            raise ValueError(f"{path}: a tile file of version {version}, not {VERSION}: count it again")
        counts = TileCounts(z["line_keys"].astype(np.int64).reshape(-1, 2), z["line_counts"].astype(np.int64),
                            z["spot_ids"].astype(np.int64), z["spot_records"].astype(np.int64).reshape(-1, 2),
                            int(z["lines"]), int(z["dropped"]))
        return counts, json.loads(str(z["meta"]))


def _level_keys(keys: np.ndarray, counts: np.ndarray, level: int) -> Tuple[np.ndarray, np.ndarray]:
    """Level-1 keys summed into cells of `level` × `level` cells."""
    if level == 1:
        return keys, counts
    a = keys[:, 0]
    i = (a >> COL_SHIFT) // level
    j = ((a >> ROW_SHIFT) & CELL_MASK) // level
    out = np.empty_like(keys)
    out[:, 0] = (i << COL_SHIFT) | (j << ROW_SHIFT) | (a & RECORD_MASK)
    out[:, 1] = keys[:, 1]
    return sum_keys(out, counts)


def _save_npy(path: str, keys: np.ndarray, counts: np.ndarray) -> None:
    with cache.replacing(path) as f:
        np.save(f, np.column_stack([keys.reshape(-1, 2), counts]).astype(np.int64))


def _border_totals(keys: np.ndarray, counts: np.ndarray) -> Dict[str, int]:
    border = (keys[:, 0] >> BORDER_SHIFT) & 3 if len(keys) else np.zeros(0, dtype=np.int64)
    return {"owned": int(counts[border == 1].sum()), "partner": int(counts[border == 2].sum())}


def build(tiles: Iterable[str], out_dir: str, info: Dict) -> Dict:
    """The cube of the tile files given (the caller picks the layer bands' tiles): lines summed per
    key, spots merged per (id, border, partner) over all tiles and bands and then counted per key,
    the levels 2, 4 and 8 summed from level 1; writes out_dir/lines_<L>.npy and spots_<L>.npy
    ((n, 3) int64 [key_a, key_b, count], sorted by key) and cube.json last (removed first, so a
    half-built cube is never read). info's "origin" is the country's (I0, J0) in cells. Returns
    cube.json's content."""
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(out_dir, "cube.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)
    lines, spots = _Reducer(sum_keys), _Reducer(merge_spots)
    for path in tiles:
        counts, _ = load_tile(path)
        lines.add(counts.line_keys, counts.line_counts)
        spots.add(counts.spot_ids, counts.spot_records)
    empty = _empty_counts()
    line_keys, line_counts = lines.flush()
    if line_keys is None:
        line_keys, line_counts = empty.line_keys, empty.line_counts
    ids, records = spots.flush()
    if ids is None:
        ids, records = empty.spot_ids, empty.spot_records
    i, j = spot_cells(ids)
    spot_keys, spot_counts = count_keys(pack_keys(i, j, records))
    del ids, records, i, j
    keys_total = {}
    for mode, keys, counts in (("lines", line_keys, line_counts), ("spots", spot_keys, spot_counts)):
        for level in LEVELS:
            k, n = _level_keys(keys, counts, level)
            _save_npy(os.path.join(out_dir, f"{mode}_{level}.npy"), k, n)
            keys_total[f"{mode}_{level}"] = int(len(k))
    cube = {**info, "version": VERSION, "cell_deg": CELL_DEG, "levels": list(LEVELS),
            "clusters_per_cell": CLUSTERS_PER_CELL,
            "edges": {"length": list(LENGTH_EDGES), **{k: list(v) for k, v in EDGES.items()}},
            "kinds": dict(KINDS), "neighbours": list(info.get("neighbours", [])),
            "totals": {"lines": int(line_counts.sum()), "spots": int(spot_counts.sum()), "keys": keys_total,
                       "border": {"lines": _border_totals(line_keys, line_counts),
                                  "spots": _border_totals(spot_keys, spot_counts)}},
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if "origin" in info:
        cube["origin"] = [int(round(float(v))) for v in info["origin"]]
    with cache.replacing(meta_path, "w", encoding="utf-8") as f:
        json.dump(cube, f, indent=1)
    return cube


TREES = ("all", "no", "only")
WATERS = ("all", "land", "water")
CEILINGS = tuple(name for name, kind in KINDS.items() if kind != "floor")


def _edges_text(edges) -> str:
    return ", ".join(f"{e:g}" for e in edges)


@dataclass(frozen=True)
class Filters:
    """The filters of the layer, on the bins' edges (KINDS): a line passes when its length bin lies
    within `length`, each floor (the weaker anchor's prominence, the clearance, the webbing's height,
    the metres over water, the lower anchor's height, the mean height, the stronger anchor's
    prominence, the drop, the high share, the clearance over trees) at or above its value, each
    ceiling below its value (the steeper anchor's wall angle, the upper anchor's height, the height
    difference) or at most it (the two A-frame fields), and over trees and water as asked. A floor
    at its first edge is off, a ceiling at None (and the upper anchor's height and the height
    difference at their first edge); an UNKNOWN value passes only a filter that is off."""
    length: Tuple[float, float] = (30, 5000)  # metres, both edges of LENGTH_EDGES
    prominence: float = 0      # >= (0: no filter, UNKNOWN passes only then)
    wall: Optional[float] = None  # < (None: no filter, UNKNOWN passes only then)
    clearance: float = 0       # >=
    height: float = 0          # >=
    trees: str = "all"         # all | no (some line not over trees) | only (some line over them)
    water: str = "all"         # all | land (some line not over water) | water (some line over water)
    water_m: float = 0         # >=
    elevation_low: float = 0   # >=
    elevation_high: Optional[float] = None  # <
    height_mean: float = 0     # >=
    prominence_high: float = 0  # >=
    drop: float = 0            # >=
    high_pct: float = 0        # >=
    height_diff: Optional[float] = None  # <
    clearance_trees: float = 0  # >=
    lift_needed: Optional[float] = None  # <= (0: lines that stand without A-frames)
    lift_no_zone: Optional[float] = None  # <=

    def __post_init__(self):
        lo, hi = self.length
        if lo not in LENGTH_EDGES or hi not in LENGTH_EDGES or not lo < hi:
            raise ValueError(f"the length range must be two different lengths of {_edges_text(LENGTH_EDGES)} m, "
                             "the shorter first")
        for name, kind in KINDS.items():
            value = getattr(self, name)
            if kind == "floor":
                if value not in EDGES[name]:
                    raise ValueError(f"{name} must be one of {_edges_text(EDGES[name])}")
            elif value is not None and value not in EDGES[name]:
                raise ValueError(f"{name} must be one of {_edges_text(EDGES[name])}, or left out")
        if self.trees not in TREES:
            raise ValueError(f"trees must be one of {', '.join(TREES)}")
        if self.water not in WATERS:
            raise ValueError(f"water must be one of {', '.join(WATERS)}")

    @classmethod
    def parse(cls, query: Mapping[str, str]) -> "Filters":
        """Filters from the web's query strings (length "<lo>-<hi>", every dimension of KINDS by its
        name, trees, water; others ignored, absent or empty ones off); ValueError with a plain message
        for a value off the edges."""
        def number(name: str, text: str) -> float:
            try:
                value = float(text)
            except ValueError:
                raise ValueError(f"{name} must be a number, not {text[:20]!r}") from None
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a number, not {text[:20]!r}")
            return value

        args = {}
        text = query.get("length") or ""
        if text:
            parts = text.split("-")
            if len(parts) != 2:
                raise ValueError("length must be given as <shortest>-<longest>, for example 30-5000")
            args["length"] = (number("length", parts[0]), number("length", parts[1]))
        for name in KINDS:
            text = query.get(name) or ""
            if text:
                args[name] = number(name, text)
        for name in ("trees", "water"):
            text = query.get(name) or ""
            if text:
                args[name] = text
        return cls(**args)

    def length_mask(self) -> int:
        """The bits of the length bins within the range."""
        lo, hi = self.length
        return sum(1 << k for k in range(LENGTH_BINS) if LENGTH_EDGES[k] >= lo and LENGTH_EDGES[k + 1] <= hi)

    def active(self, name: str) -> bool:
        """Whether the filter of a dimension of KINDS is on."""
        value = getattr(self, name)
        kind = KINDS[name]
        if kind == "floor":
            return value != EDGES[name][0]
        if value is None:
            return False
        return not (kind == "below" and name != "wall" and value == EDGES[name][0])


DIMENSIONS = ("length",) + tuple(KINDS)  # the dimensions a histogram counts


def select(keys: np.ndarray, filters: Filters, skip: Optional[str] = None) -> np.ndarray:
    """A boolean mask of the keys ((n, 2), of lines or spots) passing the filters; `skip`, one of
    DIMENSIONS, leaves that dimension's condition out (for "length" the length mask's)."""
    if skip is not None and skip not in DIMENSIONS:
        raise ValueError(f"skip must be one of {', '.join(DIMENSIONS)}")
    keys = np.asarray(keys, dtype=np.int64).reshape(-1, 2)
    a = keys[:, 0]
    if skip == "length":
        mask = np.ones(len(keys), dtype=bool)
    else:
        mask = ((a >> LENGTH_SHIFT) & filters.length_mask()) != 0
    for name, kind in KINDS.items():
        if name == skip or not filters.active(name):
            continue
        b = _field(keys, name)
        index = EDGES[name].index(getattr(filters, name))
        if kind == "floor":
            mask &= (b != UNKNOWN) & (b >= index)
        elif kind == "below":
            mask &= (b != UNKNOWN) & (b < index)
        else:
            mask &= (b != UNKNOWN) & (b <= index)
    if filters.trees != "all":
        mask &= (a & (1 << (TREES_BIT + (filters.trees == "only")))) != 0
    if filters.water != "all":
        mask &= (a & (1 << (WATER_BIT + (filters.water == "water")))) != 0
    return mask


def _authalic(lat: np.ndarray) -> np.ndarray:
    """(b² / 2) × q(φ) of WGS84: the area between the equator and φ per radian of longitude is its
    value, so (λ in radians, this) is a cylindrical projection of equal area (m²)."""
    s = np.sin(np.radians(np.asarray(lat, dtype=np.float64)))
    return _B * _B / 2 * (s / (1 - _E2 * s * s) + np.log((1 + _E * s) / (1 - _E * s)) / (2 * _E))


def _equal_area(geometry):
    """A WGS84 (lon, lat) geometry on the cylindrical projection of equal area (its area in m²)."""
    return shapely.transform(geometry, lambda xy: np.column_stack([np.radians(xy[:, 0]), _authalic(xy[:, 1])]))


def lattice_km2(level: int, origin_j: int, j: np.ndarray) -> np.ndarray:
    """The km² of a whole cell of a level in row j (from the origin's row origin_j, in cells): the
    ellipsoid's area between its parallels over its longitudes."""
    j = np.asarray(j, dtype=np.int64)
    south = (origin_j + j * level) / CELLS_PER_DEGREE
    north = (origin_j + (j + 1) * level) / CELLS_PER_DEGREE
    return (_authalic(north) - _authalic(south)) * math.radians(level / CELLS_PER_DEGREE) / 1e6


Box = Tuple[float, float, float, float]
OUTLINE_TOLERANCE = 0.005  # degrees: the simplification of the outline a map draws (Slovakia: 43k points to about 600)
OUTLINE_DECIMALS = 4       # of its coordinates (about 10 m)
CUT_SIMPLIFY = 250         # a cut cell's shape on a map, simplified by its side over this (Slovakia: 4 m, 11 points a cell)
CUT_DECIMALS = 6           # of its coordinates (about 0.1 m): the corners of /api/countries/<id>/cells
CUT_FULL = 1 - 1e-9        # a cell with this share of it inside the outline is whole
RANGE_EPSILON = 1e-4       # cells: more than the corners' rounding to CUT_DECIMALS (1e-6°: 1.2e-4 of a 30" cell)


class Cube:
    """A built cube: cube.json and the .npy files, each read into memory when first used (not
    memory-mapped: a mapped file stays open, and Windows would refuse the next build's replacing
    it while the app shows the layer). Its cells are the lattice's: lon/lat rectangles of
    level / 120 degrees from the origin (I0, J0) in cells, so nothing of it needs pyproj."""

    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "cube.json"), encoding="utf-8") as f:
            self.info: Dict = json.load(f)
        if self.info.get("version") != VERSION:
            raise ValueError(f"{folder}: a cube of version {self.info.get('version')}, not {VERSION}: build it again")
        self.origin = (int(self.info["origin"][0]), int(self.info["origin"][1]))
        self.crs = self.info.get("crs")
        self.levels = tuple(self.info.get("levels", LEVELS))
        self._arrays: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self._outlines: Dict[float, Dict] = {}  # outline_simplified per tolerance
        self._cuts: Optional[Dict[int, Dict[Tuple[int, int], Dict]]] = None  # cut's cells per level

    def array(self, mode: str, level: int) -> np.ndarray:
        """The (n, 3) [key_a, key_b, count] rows of a mode ("lines" or "spots") and level."""
        keys, counts = self._rows(mode, level)
        return np.column_stack([keys, counts])

    def _rows(self, mode: str, level: int) -> Tuple[np.ndarray, np.ndarray]:
        """The keys ((n, 2), C-contiguous) and counts of a mode and level, read once."""
        if mode not in ("lines", "spots"):
            raise ValueError("mode must be lines or spots")
        if level not in self.levels:
            raise ValueError(f"level must be one of {', '.join(map(str, self.levels))}")
        name = f"{mode}_{level}"
        if name not in self._arrays:
            rows = np.load(os.path.join(self.folder, name + ".npy")).reshape(-1, 3)
            self._arrays[name] = (np.ascontiguousarray(rows[:, :2]), np.ascontiguousarray(rows[:, 2]))
        return self._arrays[name]

    def box(self, west: float, south: float, east: float, north: float) -> Box:
        """A WGS84 box clipped to the country's bounds_wgs84 with a margin of a degree, so a view of
        half the world stays finite; a view away from the country gives an empty box (west > east)."""
        values = (west, south, east, north)
        if not all(math.isfinite(v) for v in values) or west > east or south > north:
            raise ValueError("the box must be west,south,east,north in degrees")
        west, east = max(west, -180.0), min(east, 180.0)
        south, north = max(south, -90.0), min(north, 90.0)
        bounds = self.info.get("bounds_wgs84")
        if bounds:
            west, south = max(west, bounds[0] - 1), max(south, bounds[1] - 1)
            east, north = min(east, bounds[2] + 1), min(north, bounds[3] + 1)
            if west > east or south > north:
                return (1.0, 1.0, 0.0, 0.0)
        return (float(west), float(south), float(east), float(north))

    def _range(self, level: int, box: Box) -> Tuple[int, int, int, int]:
        """The columns and rows (inclusive) of the level's cells touching box, edges included within
        RANGE_EPSILON (may be empty): a box's edge on the lattice (19.9° is 2388 cells) touches the cells
        on both sides, as their corners rounded to 6 decimals reach it for the page."""
        if box[0] > box[2] or box[1] > box[3]:
            return (0, -1, 0, -1)
        i0, j0 = self.origin
        e = RANGE_EPSILON
        return (math.floor((box[0] * CELLS_PER_DEGREE - i0) / level - e),
                math.floor((box[2] * CELLS_PER_DEGREE - i0) / level + e),
                math.floor((box[1] * CELLS_PER_DEGREE - j0) / level - e),
                math.floor((box[3] * CELLS_PER_DEGREE - j0) / level + e))

    def auto_level(self, box: Box, most: int = 4000) -> int:
        """The finest level with at most `most` cells over box (by its geometry), else the coarsest."""
        for level in sorted(self.levels):
            if self.cell_count(level, box) <= most:
                return level
        return max(self.levels)

    def cell_count(self, level: int, box: Box) -> int:
        """The number of the level's cells over box (by its geometry)."""
        i0, i1, j0, j1 = self._range(level, box)
        return max(i1 - i0 + 1, 0) * max(j1 - j0 + 1, 0)

    def _slice(self, mode: str, level: int, box: Optional[Box]) -> Tuple[np.ndarray, np.ndarray]:
        """The keys ((n, 2), sorted) and counts of the level's rows in the cells touching box (None:
        all): the columns' range by searchsorted on word A, the rows' by a mask."""
        keys, counts = self._rows(mode, level)
        empty = np.zeros(0, dtype=np.int64)
        if box is None:
            return keys, counts
        i0, i1, j0, j1 = self._range(level, box)
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, CELL_MASK), min(j1, CELL_MASK)
        if i0 > i1 or j0 > j1:
            return empty.reshape(0, 2), empty
        a = keys[:, 0]
        lo = int(np.searchsorted(a, i0 << COL_SHIFT, side="left"))
        hi = int(np.searchsorted(a, (i1 + 1) << COL_SHIFT, side="left"))
        keys, counts = keys[lo:hi], counts[lo:hi]
        j = (keys[:, 0] >> ROW_SHIFT) & CELL_MASK
        mask = (j >= j0) & (j <= j1)
        return keys[mask], counts[mask]

    def cells(self, mode: str, level: int, box: Optional[Box], filters: Filters
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """i, j and count of the level's cells inside box (None: all) passing filters, count > 0."""
        empty = np.zeros(0, dtype=np.int64)
        keys, counts = self._slice(mode, level, box)
        if not len(keys):
            return empty, empty, empty
        mask = select(keys, filters)
        cell = (keys[:, 0] >> ROW_SHIFT)[mask]  # sorted, as the keys are
        counts = counts[mask]
        if not len(cell):
            return empty, empty, empty
        starts = np.flatnonzero(np.concatenate(([True], cell[1:] != cell[:-1])))
        total = np.add.reduceat(counts, starts)
        cell = cell[starts]
        keep = total > 0
        cell, total = cell[keep], total[keep]
        return cell >> (COL_SHIFT - ROW_SHIFT), cell & CELL_MASK, total.astype(np.int64)

    def reaching(self, level: int, keys: np.ndarray, view: Tuple[float, float, float, float],
                 decimals: Optional[int] = None) -> np.ndarray:
        """A mask of the keys ((n, 2)) whose cell reaches a WGS84 view (west, south, east, north): the
        box of the cell's corners (rounded to `decimals`, as /api/countries/<id>/cells gives them)
        intersects the view, edges included, as Leaflet's LatLngBounds.intersects: the page's total
        in view."""
        west, south, east, north = view
        keys = np.asarray(keys, dtype=np.int64).reshape(-1, 2)
        cell = keys[:, 0] >> ROW_SHIFT
        if not len(cell):
            return np.zeros(0, dtype=bool)
        unique, inverse = np.unique(cell, return_inverse=True)
        corners = self.corners(level, unique >> (COL_SHIFT - ROW_SHIFT), unique & CELL_MASK)
        if decimals is not None:
            corners = np.round(corners, decimals)
        lat, lon = corners[:, :, 0], corners[:, :, 1]
        ok = (lat.max(1) >= south) & (lat.min(1) <= north) & (lon.max(1) >= west) & (lon.min(1) <= east)
        return ok[inverse.reshape(-1)]

    def histogram(self, mode: str, level: int, box: Optional[Box], filters: Filters,
                  view: Optional[Tuple[float, float, float, float]] = None, decimals: Optional[int] = None) -> Dict:
        """The counts over box (None: all) per bin of each dimension, each dimension counted under every
        filter but its own (select(skip=)): {"total": the sum under all filters, "length": [9 ints, one
        per length bin], every dimension of KINDS: [the bins 0 .. bins_of(name) - 1, then UNKNOWN]: 6
        ints, 7 for an at_most}. With `view` (the WGS84 box that gave box), only the cells reaching it
        (`reaching`: by their corners rounded as /cells rounds them; box is grown by a cell first, so
        no cell reaching the view is missed). A line carries one length bit, so a mode's length bins
        partition its total (under the other filters); a spot's record ORs the length bits of its
        lines (merge_spots), so a spot counts in every bin of its lines: per-bin spot counts are upper
        bounds and may sum above the total."""
        if view is not None and box is not None and box[0] <= box[2] and box[1] <= box[3]:
            size = level * CELL_DEG
            box = (box[0] - size, box[1] - size, box[2] + size, box[3] + size)
        keys, counts = self._slice(mode, level, box)
        if view is not None and len(keys):
            near = self.reaching(level, keys, view, decimals)
            keys, counts = keys[near], counts[near]
        out: Dict = {"total": int(counts[select(keys, filters)].sum()) if len(keys) else 0}
        if not len(keys):
            out["length"] = [0] * LENGTH_BINS
            for name in KINDS:
                out[name] = [0] * (bins_of(name) + 1)
            return out
        weights = counts.astype(np.float64)  # exact below 2^53
        mask = select(keys, filters, skip="length")
        bits = (keys[:, 0] >> LENGTH_SHIFT)[mask]
        out["length"] = [int(round(weights[mask][(bits & (1 << k)) != 0].sum())) for k in range(LENGTH_BINS)]
        for name in KINDS:
            mask = select(keys, filters, skip=name)
            h = np.bincount(_field(keys, name)[mask], weights=weights[mask], minlength=8)
            out[name] = [int(round(v)) for v in (*h[:bins_of(name)], h[UNKNOWN])]
        return out

    def corners(self, level: int, i: np.ndarray, j: np.ndarray) -> np.ndarray:
        """(n, 4, 2) [lat, lon] of the cells' corners: SW, SE, NE, NW (a lon/lat rectangle)."""
        i, j = np.asarray(i, dtype=np.int64), np.asarray(j, dtype=np.int64)
        west = (self.origin[0] + i * level) / CELLS_PER_DEGREE
        east = (self.origin[0] + (i + 1) * level) / CELLS_PER_DEGREE
        south = (self.origin[1] + j * level) / CELLS_PER_DEGREE
        north = (self.origin[1] + (j + 1) * level) / CELLS_PER_DEGREE
        out = np.empty((len(i), 4, 2))
        out[:, :, 0] = np.stack([south, south, north, north], axis=1)
        out[:, :, 1] = np.stack([west, east, east, west], axis=1)
        return out

    def cell_km2(self, level: int, j: np.ndarray) -> np.ndarray:
        """The km² of a whole cell of a level in row j (a cut cell's part inside the outline: cut)."""
        return lattice_km2(level, self.origin[1], j)

    def outline(self):
        """The country's outline (area.geojson of the cube folder) as a shapely geometry, WGS84."""
        with open(os.path.join(self.folder, "area.geojson"), encoding="utf-8") as f:
            value = json.load(f)
        if value["type"] == "FeatureCollection":
            geometries = [ft["geometry"] for ft in value["features"]]
        elif value["type"] == "Feature":
            geometries = [value["geometry"]]
        else:
            geometries = [value]
        return shapely.union_all([shape(g) for g in geometries if g is not None])

    def outline_simplified(self, tolerance: float = OUTLINE_TOLERANCE) -> Dict:
        """The outline for a map: {"tolerance": degrees, "area_km2": of the original outline on the
        ellipsoid, "geometry": the outline simplified by `tolerance` (topology preserved, made valid
        when needed), its coordinates rounded to OUTLINE_DECIMALS, as a GeoJSON mapping}; kept per
        tolerance."""
        tolerance = float(tolerance)
        found = self._outlines.get(tolerance)
        if found is not None:
            return found
        outline = self.outline()
        area = _equal_area(outline).area / 1e6
        simple = outline.simplify(tolerance, preserve_topology=True)
        simple = shapely.transform(simple, lambda xy: np.round(xy, OUTLINE_DECIMALS))
        if not simple.is_valid:
            simple = shapely.make_valid(simple)
            if simple.geom_type == "GeometryCollection":  # the polygons only, not a rounding's slivers of lines
                simple = shapely.union_all([g for g in simple.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
        found = {"tolerance": tolerance, "area_km2": round(float(area), 1),
                 "geometry": json.loads(shapely.to_geojson(simple))}
        self._outlines[tolerance] = found
        return found

    def cut(self, level: int) -> Dict[Tuple[int, int], Dict]:
        """The level's cells the country's outline cuts, by (i, j): {"km2": the cell's part inside the
        outline (the exact outline, its area on the ellipsoid: the true divisor of its density),
        "shape": that part for a map: polygons of rings of [lat, lon], simplified by the cell's side
        over CUT_SIMPLIFY}. A cell not listed lies wholly inside or wholly outside (cell_km2 gives a
        whole one's km²). All levels are worked out at the first call and kept; without an outline no
        cell is cut."""
        if self._cuts is None:
            self._cuts = self._cut_cells()
        return self._cuts[level]

    def _cut_cells(self) -> Dict[int, Dict[Tuple[int, int], Dict]]:
        """cut's cells of every level: a quadtree of the lattice's rectangles from a cell holding the
        whole outline down to the finest level. A cell's piece is cut out of its parent's, so an
        intersection sees the few points of the outline near it, and a branch ends at a cell wholly
        inside or outside (by its area in square degrees: whole when it is the rectangle's)."""
        out: Dict[int, Dict[Tuple[int, int], Dict]] = {level: {} for level in self.levels}
        try:
            outline = self.outline()
        except (OSError, ValueError, KeyError):  # a cube without its area.geojson
            return out
        if not outline.is_valid:
            outline = shapely.make_valid(outline)
        i0, j0 = self.origin
        level = max(self.levels)
        bounds = outline.bounds
        while level < max(bounds[2] * CELLS_PER_DEGREE - i0, bounds[3] * CELLS_PER_DEGREE - j0):
            level *= 2
        i, j = np.zeros(1, dtype=np.int64), np.zeros(1, dtype=np.int64)
        pieces = np.array([outline], dtype=object)

        def lat_lon(xy):
            return np.round(xy[:, ::-1], CUT_DECIMALS)

        while True:
            side = level / CELLS_PER_DEGREE
            area = shapely.area(pieces)
            keep = (area > 0) & (area < side * side * CUT_FULL)
            i, j, pieces = i[keep], j[keep], pieces[keep]
            if level in out and len(pieces):
                km2 = shapely.area(_equal_area(shapely.segmentize(pieces, side / 8))) / 1e6
                shapes = shapely.transform(shapely.simplify(pieces, side / CUT_SIMPLIFY, preserve_topology=True), lat_lon)
                out[level] = {(a, b): {"km2": max(round(float(k), 6), 1e-6), "shape": _polygon_rings(s)}
                              for a, b, k, s in zip(i.tolist(), j.tolist(), km2, shapes)}
            if level <= min(self.levels):
                return out
            level //= 2
            i, j = np.repeat(2 * i, 4) + np.tile((0, 1, 0, 1), len(i)), np.repeat(2 * j, 4) + np.tile((0, 0, 1, 1), len(j))
            boxes = shapely.box((i0 + i * level) / CELLS_PER_DEGREE, (j0 + j * level) / CELLS_PER_DEGREE,
                                (i0 + (i + 1) * level) / CELLS_PER_DEGREE, (j0 + (j + 1) * level) / CELLS_PER_DEGREE)
            pieces = shapely.intersection(np.repeat(pieces, 4), boxes)


def _polygon_rings(geometry) -> List:
    """The polygons of a geometry, each a list of rings of coordinates (an intersection may hold lines too)."""
    polygons, rest = [], [geometry]
    while rest:
        part = rest.pop()
        if part.geom_type == "Polygon" and not part.is_empty:
            polygons.append([shapely.get_coordinates(ring).tolist() for ring in (part.exterior, *part.interiors)])
        elif hasattr(part, "geoms"):
            rest.extend(part.geoms)
    return polygons


REQUEST_DECIMALS = 6   # degrees of a cell request's geometry (about 0.1 m)
REQUEST_SEGMENT_M = 100.0  # its edges densified to this before they go back to WGS84


def cell_request(cube: Cube, band: str, level: int, i: int, j: int) -> Dict:
    """The search of one cell (a SearchRequest: {"params", "geometry"}): the level's rectangle
    buffered by the band's max_length (in metres of a local plane at the cell's centre, no pyproj),
    as a WGS84 GeoJSON Polygon or MultiPolygon; the band's params from cube.json. Not cut by the
    country's outline: the layer counts the lines across the border too (a line's cell is that of its
    first anchor, whichever country holds it), and the app's search fills the neighbour's data at the
    border as the count does. ValueError for a band not in the layer, a level not in the cube or a
    cell outside the country."""
    found = [b for b in cube.info.get("bands", []) if b.get("name") == band and b.get("layer")]
    if not found:
        names = [b["name"] for b in cube.info.get("bands", []) if b.get("layer")]
        raise ValueError(f"band must be one of {', '.join(names)}")
    if level not in cube.levels:
        raise ValueError(f"level must be one of {', '.join(map(str, cube.levels))}")
    b = found[0]
    params = dict(b.get("params", {}))
    reach = float(params.get("max_length", b["lengths"][1]))
    (south, west), _, (north, east), _ = cube.corners(level, np.array([i]), np.array([j]))[0]
    rectangle = shapely.box(west, south, east, north)
    outline = cube.outline()
    if i < 0 or j < 0 or not rectangle.intersects(outline):
        raise ValueError("the cell lies outside the country")
    lon0, lat0 = (west + east) / 2, (south + north) / 2
    kx, ky = _metres_per_degree(lat0)

    def to_plane(xy):
        return np.column_stack([(xy[:, 0] - lon0) * kx, (xy[:, 1] - lat0) * ky])

    def to_degrees(xy):
        return np.column_stack([xy[:, 0] / kx + lon0, xy[:, 1] / ky + lat0])

    region = shapely.transform(rectangle, to_plane).buffer(reach)
    region = shapely.segmentize(region, REQUEST_SEGMENT_M)
    back = shapely.transform(region, lambda xy: np.round(to_degrees(xy), REQUEST_DECIMALS))
    if not back.is_valid:
        back = shapely.make_valid(back)
    polygons = [g for g in getattr(back, "geoms", [back]) if g.geom_type in ("Polygon", "MultiPolygon")]
    parts = [p for g in polygons for p in getattr(g, "geoms", [g])]
    if not parts:
        raise ValueError("the cell lies outside the country")
    geometry = parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts)
    geometry = shapely.orient_polygons(geometry)  # RFC 7946: exteriors counterclockwise
    return {"params": params, "geometry": json.loads(shapely.to_geojson(geometry))}
