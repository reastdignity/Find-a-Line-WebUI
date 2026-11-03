"""The counter cube of a country (docs/country-precompute/contract.md, section 2).

A country is searched in fixed tiles that keep only counts: for each 1 km cell of the country's
CRS and each combination of filter bins, the number of lines and of spots (pairs of 50 m anchor
clusters with at least one line). Each count is a row [key, count] of a sorted int64 array; the
key packs the cell and the bins into 53 bits:

    bits 0-1 water (bit 0: not over water, bit 1: over water), 2-3 trees (bit 2: not over trees or
    buildings, bit 3: over them), 4-6 height bin, 7-9 clearance bin, 10-12 wall bin, 13-15
    prominence bin, 16-24 length mask (bit 16 + k: length bin k), 25-38 cell row j, 39-52 cell
    column i (from the country's origin).

The low RECORD_BITS are a line's (or a spot's) record. A line sets one bit of each flag pair and
one length bit; a spot's record merges those of its lines (merge_spots), so a spot passes one
filter exactly when some line of it does, and several filters as an upper bound.

TileCounter counts the lines search.count_tile hands it, save_tile/load_tile keep a tile's counts,
build sums the tiles into the cube (levels 1, 2, 4 and 8 km), Cube reads it for the web's layer,
cell_request gives the search of one cell. Pure numpy, pyproj and shapely: the web
process imports this module, so it never imports numba, linesearch, search or country.
"""
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box as shapely_box, shape

import cache

VERSION = 1           # tile files and cubes of another version are refused (computed again, no migration)
CELL_M = 1000.0
LEVELS = (1, 2, 4, 8)  # a level's cell: L * CELL_M
ALIGN_M = 8000.0      # a country's origin: its grid's left/bottom floored to a multiple of this
CLUSTER_M = 50.0      # a spot's anchor clusters
LENGTH_EDGES = (30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000)  # 9 bins [e_k, e_k+1); 5000 in the last
EDGES = {             # lower edges of the 3-bit dimensions; below the first: bin 0; the last bin open upwards
    "prominence": (0, 5, 10, 20, 50),   # of the weaker anchor: np.minimum(prom1, prom2)
    "wall": (0, 30, 45, 60, 90),        # of the steeper anchor: np.maximum(angle1, angle2)
    "clearance": (0, 2, 5, 10, 20),     # "clearance" over the terrain
    "height": (0, 10, 20, 50, 100),     # "height_max" of the webbing over the terrain
}
UNKNOWN = 7           # a 3-bit dimension whose value is NaN

# The key's fields: (first bit, width)
WATER_BIT, TREES_BIT = 0, 2
SHIFT = {"height": 4, "clearance": 7, "wall": 10, "prominence": 13}
LENGTH_SHIFT = 16
LENGTH_BINS = len(LENGTH_EDGES) - 1
RECORD_BITS = 25
RECORD_MASK = (1 << RECORD_BITS) - 1
ROW_SHIFT, COL_SHIFT = 25, 39
CELL_BITS = 14        # rows and columns: up to 16384 cells of CELL_M
CELL_MASK = (1 << CELL_BITS) - 1
# The bits merge_spots ORs: the flag pairs and the length mask
OR_MASK = 0xF | (((1 << LENGTH_BINS) - 1) << LENGTH_SHIFT)

# Spot ids: p.cx << 35 | p.cy << 16 | dx << 8 | (dy + 128)
SPOT_CX_SHIFT, SPOT_CY_SHIFT = 35, 16
SPOT_CY_BITS = 19
SPOT_CX_BITS = 18
CLUSTERS_PER_CELL = int(round(CELL_M / CLUSTER_M))  # 20

PENDING_MAX = 4_000_000  # entries waiting before they are reduced (or the size of the reduced arrays, if larger)
DENSIFY = 21             # points per edge when a box is projected


def _bin(values: np.ndarray, edges) -> np.ndarray:
    """The 3-bit bins of values over lower edges: below the first bin 0, the last open upwards,
    NaN UNKNOWN."""
    values = np.asarray(values, dtype=np.float64)
    b = np.searchsorted(np.asarray(edges, dtype=np.float64), values, side="right").astype(np.int64) - 1
    np.maximum(b, 0, out=b)
    b[np.isnan(values)] = UNKNOWN
    return b


def length_bin(lengths: np.ndarray) -> np.ndarray:
    """The length bin k of each length: [e_k, e_k+1), 5000 (the last edge) in the last bin; lengths
    off the edges go to the nearest bin."""
    b = np.searchsorted(np.asarray(LENGTH_EDGES, dtype=np.float64), np.asarray(lengths, dtype=np.float64),
                        side="right").astype(np.int64) - 1
    return np.clip(b, 0, LENGTH_BINS - 1)


def line_records(columns: Mapping[str, np.ndarray]) -> np.ndarray:
    """The records (RECORD_BITS) of lines given as columns: the LINE_VALUES and "water_px"."""
    c = columns
    water = np.asarray(c["water_px"]) > 0
    with np.errstate(invalid="ignore"):
        trees = np.asarray(c["clearance_nmpt"], dtype=np.float64) <= 0  # NaN: not over
    rec = np.left_shift(1, WATER_BIT + water.astype(np.int64))
    rec |= np.left_shift(1, TREES_BIT + trees.astype(np.int64))
    rec |= _bin(c["height_max"], EDGES["height"]) << SHIFT["height"]
    rec |= _bin(c["clearance"], EDGES["clearance"]) << SHIFT["clearance"]
    rec |= _bin(np.maximum(c["angle1"], c["angle2"]), EDGES["wall"]) << SHIFT["wall"]
    rec |= _bin(np.minimum(c["prom1"], c["prom2"]), EDGES["prominence"]) << SHIFT["prominence"]
    rec |= np.left_shift(1, LENGTH_SHIFT + length_bin(c["length"]))
    return rec.astype(np.int64)


def pack_keys(i: np.ndarray, j: np.ndarray, records: np.ndarray) -> np.ndarray:
    """Keys of cells (i, j) with their records."""
    i, j = np.asarray(i, dtype=np.int64), np.asarray(j, dtype=np.int64)
    if len(i) and (i.min() < 0 or j.min() < 0 or i.max() > CELL_MASK or j.max() > CELL_MASK):
        raise ValueError("a cell lies outside the cube: check the country's origin")
    return (i << COL_SHIFT) | (j << ROW_SHIFT) | (np.asarray(records, dtype=np.int64) & RECORD_MASK)


def unpack_keys(keys: np.ndarray) -> Dict[str, np.ndarray]:
    """The fields of keys: "i", "j", "record", the bins "height", "clearance", "wall", "prominence",
    "length" (the mask), "water" and "trees" (their two bits)."""
    keys = np.asarray(keys, dtype=np.int64)
    out = {"i": keys >> COL_SHIFT, "j": (keys >> ROW_SHIFT) & CELL_MASK, "record": keys & RECORD_MASK,
           "length": (keys >> LENGTH_SHIFT) & ((1 << LENGTH_BINS) - 1),
           "water": keys & 3, "trees": (keys >> TREES_BIT) & 3}
    out.update({name: (keys >> shift) & 7 for name, shift in SHIFT.items()})
    return out


def origin_of(bounds: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """A country's origin: the (left, bottom) of its grid's bounds floored to a multiple of ALIGN_M."""
    left, bottom = bounds[0], bounds[1]
    return (math.floor(left / ALIGN_M) * ALIGN_M, math.floor(bottom / ALIGN_M) * ALIGN_M)


def spot_ids(x1, y1, x2, y2, origin: Tuple[float, float]) -> np.ndarray:
    """The spot of each line: the pair of the CLUSTER_M clusters of its anchors (in CRS metres)."""
    x0, y0 = origin
    cx1 = np.floor((np.asarray(x1) - x0) / CLUSTER_M).astype(np.int64)
    cy1 = np.floor((np.asarray(y1) - y0) / CLUSTER_M).astype(np.int64)
    cx2 = np.floor((np.asarray(x2) - x0) / CLUSTER_M).astype(np.int64)
    cy2 = np.floor((np.asarray(y2) - y0) / CLUSTER_M).astype(np.int64)
    first = (cx1 < cx2) | ((cx1 == cx2) & (cy1 <= cy2))
    pcx, pcy = np.where(first, cx1, cx2), np.where(first, cy1, cy2)
    dx, dy = np.where(first, cx2, cx1) - pcx, np.where(first, cy2, cy1) - pcy
    if len(pcx) and (pcx.min() < 0 or pcy.min() < 0 or pcx.max() >= 1 << SPOT_CX_BITS
                     or pcy.max() >= 1 << SPOT_CY_BITS):
        raise ValueError("an anchor lies outside the cube: check the country's origin")
    if len(dx) and (dx.max() > 255 or np.abs(dy).max() > 127):
        raise ValueError("a line is too long for a spot id")
    return (pcx << SPOT_CX_SHIFT) | (pcy << SPOT_CY_SHIFT) | (dx << 8) | (dy + 128)


def spot_cells(ids: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """The cell (i, j) of each spot: that of its first cluster p."""
    ids = np.asarray(ids, dtype=np.int64)
    return ((ids >> SPOT_CX_SHIFT) // CLUSTERS_PER_CELL,
            ((ids >> SPOT_CY_SHIFT) & ((1 << SPOT_CY_BITS) - 1)) // CLUSTERS_PER_CELL)


def merge_spots(ids: np.ndarray, records: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted unique ids and their merged records: the length mask and the flag bits ORed,
    prominence, clearance and height the largest bin (UNKNOWN only when every one is), wall the
    smallest (UNKNOWN likewise). Commutative and associative, so partial merges may be merged again."""
    ids = np.asarray(ids, dtype=np.int64)
    records = np.asarray(records, dtype=np.int64)
    if not len(ids):
        return ids.copy(), records.copy()
    order = np.argsort(ids, kind="stable")
    ids, records = ids[order], records[order]
    starts = np.flatnonzero(np.concatenate(([True], ids[1:] != ids[:-1])))
    out = np.bitwise_or.reduceat(records & OR_MASK, starts)
    for name in ("prominence", "clearance", "height"):
        b = (records >> SHIFT[name]) & 7
        b[b == UNKNOWN] = -1
        m = np.maximum.reduceat(b, starts)
        m[m < 0] = UNKNOWN
        out |= m << SHIFT[name]
    b = (records >> SHIFT["wall"]) & 7
    b[b == UNKNOWN] = 8
    m = np.minimum.reduceat(b, starts)
    m[m == 8] = UNKNOWN
    out |= m << SHIFT["wall"]
    return ids[starts], out


def sum_keys(keys: np.ndarray, counts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted unique keys and their summed counts."""
    keys = np.asarray(keys, dtype=np.int64)
    counts = np.asarray(counts, dtype=np.int64)
    if not len(keys):
        return keys.copy(), counts.copy()
    order = np.argsort(keys, kind="stable")
    keys, counts = keys[order], counts[order]
    starts = np.flatnonzero(np.concatenate(([True], keys[1:] != keys[:-1])))
    return keys[starts], np.add.reduceat(counts, starts)


def count_keys(keys: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted unique keys and how often each occurs."""
    u, n = np.unique(np.asarray(keys, dtype=np.int64), return_counts=True)
    return u, n.astype(np.int64)


class _Reducer:
    """Pairs of (keys, values) collected part by part and reduced by `reduce` whenever more than
    PENDING_MAX entries (or as many as the reduced arrays hold) wait: amortised, bounded memory."""

    def __init__(self, reduce):
        self.reduce = reduce
        self.keys = np.zeros(0, dtype=np.int64)
        self.values = np.zeros(0, dtype=np.int64)
        self.pending: List[Tuple[np.ndarray, np.ndarray]] = []
        self.waiting = 0

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        if not len(keys):
            return
        self.pending.append((keys, values))
        self.waiting += len(keys)
        if self.waiting > max(PENDING_MAX, len(self.keys)):
            self.flush()

    def flush(self) -> Tuple[np.ndarray, np.ndarray]:
        if self.pending:
            keys = np.concatenate([self.keys] + [k for k, _ in self.pending])
            values = np.concatenate([self.values] + [v for _, v in self.pending])
            self.pending, self.waiting = [], 0
            self.keys, self.values = self.reduce(keys, values)
        return self.keys, self.values


@dataclass
class TileCounts:
    line_keys: np.ndarray     # int64, sorted, unique
    line_counts: np.ndarray   # int64
    spot_ids: np.ndarray      # int64, sorted, unique
    spot_records: np.ndarray  # int64 (RECORD_BITS)
    lines: int                # lines counted
    dropped: int              # lines left out: outside lengths or with the first anchor outside core


class TileCounter:
    """The counts of one tile, fed part by part by search.count_tile (a LineTable with "a1", "a2",
    the LINE_VALUES and "water_px").

    A line is counted when its first anchor (the smaller x, then y, as mapping.first_anchor) lies in
    `core` (left <= x < right, bottom <= y < top; None: everywhere) and its length within `lengths`
    (lo <= length < hi, or <= hi when `last`)."""

    def __init__(self, grid, origin: Tuple[float, float], core: Optional[Tuple[float, float, float, float]],
                 lengths: Tuple[float, float], last: bool):
        self.grid = grid
        self.origin = (float(origin[0]), float(origin[1]))
        self.core = core
        self.lengths = (float(lengths[0]), float(lengths[1]))
        self.last = last
        self._lines = _Reducer(sum_keys)
        self._spots = _Reducer(merge_spots)
        self.lines = 0
        self.dropped = 0

    def __call__(self, part) -> None:
        c = part.columns
        a1, a2 = np.asarray(c["a1"]), np.asarray(c["a2"])
        n = len(a1)
        if not n:
            return
        x1, y1 = self.grid.pixel_to_xy(a1[:, 0], a1[:, 1])
        x2, y2 = self.grid.pixel_to_xy(a2[:, 0], a2[:, 1])
        length = np.asarray(c["length"], dtype=np.float64)
        lo, hi = self.lengths
        keep = (length >= lo) & ((length <= hi) if self.last else (length < hi))
        first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
        fx, fy = np.where(first, x1, x2), np.where(first, y1, y2)
        if self.core is not None:
            left, bottom, right, top = self.core
            keep &= (fx >= left) & (fx < right) & (fy >= bottom) & (fy < top)
        kept = int(np.count_nonzero(keep))
        self.dropped += n - kept
        if not kept:
            return
        self.lines += kept
        if kept < n:
            x1, y1, x2, y2, fx, fy = (v[keep] for v in (x1, y1, x2, y2, fx, fy))
            columns = {name: np.asarray(c[name])[keep] for name in RECORD_COLUMNS}
        else:
            columns = c
        records = line_records(columns)
        x0, y0 = self.origin
        i = np.floor((fx - x0) / CELL_M).astype(np.int64)
        j = np.floor((fy - y0) / CELL_M).astype(np.int64)
        self._lines.add(*count_keys(pack_keys(i, j, records)))
        self._spots.add(*merge_spots(spot_ids(x1, y1, x2, y2, self.origin), records))

    def result(self) -> TileCounts:
        keys, counts = self._lines.flush()
        ids, records = self._spots.flush()
        return TileCounts(keys, counts, ids, records, self.lines, self.dropped)


RECORD_COLUMNS = ("length", "clearance", "clearance_nmpt", "height_max", "angle1", "angle2", "prom1", "prom2",
                  "water_px")


def save_tile(path: str, counts: TileCounts, meta: Dict) -> None:
    """A tile's counts and its meta (JSON text) as a compressed .npz, written atomically."""
    with cache.replacing(path) as f:
        np.savez_compressed(f, version=np.int64(VERSION), meta=np.array(json.dumps(meta)),
                            line_keys=counts.line_keys, line_counts=counts.line_counts,
                            spot_ids=counts.spot_ids, spot_records=counts.spot_records,
                            lines=np.int64(counts.lines), dropped=np.int64(counts.dropped))


def load_tile(path: str) -> Tuple[TileCounts, Dict]:
    """A tile's counts and meta; ValueError for a file of another VERSION."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"]) if "version" in z.files else None
        if version != VERSION:
            raise ValueError(f"{path}: a tile file of version {version}, not {VERSION}: count it again")
        counts = TileCounts(z["line_keys"].astype(np.int64), z["line_counts"].astype(np.int64),
                            z["spot_ids"].astype(np.int64), z["spot_records"].astype(np.int64),
                            int(z["lines"]), int(z["dropped"]))
        return counts, json.loads(str(z["meta"]))


def _level_keys(keys: np.ndarray, counts: np.ndarray, level: int) -> Tuple[np.ndarray, np.ndarray]:
    """Level-1 keys summed into cells of `level` km."""
    if level == 1:
        return keys, counts
    i = (keys >> COL_SHIFT) // level
    j = ((keys >> ROW_SHIFT) & CELL_MASK) // level
    return sum_keys((i << COL_SHIFT) | (j << ROW_SHIFT) | (keys & RECORD_MASK), counts)


def _save_npy(path: str, keys: np.ndarray, counts: np.ndarray) -> None:
    with cache.replacing(path) as f:
        np.save(f, np.column_stack([keys, counts]).astype(np.int64))


def build(tiles: Iterable[str], out_dir: str, info: Dict) -> Dict:
    """The cube of the tile files given (the caller picks the layer bands' tiles): lines summed per
    key, spots merged per id over all tiles and bands and then counted per key, the levels 2, 4 and
    8 summed from level 1; writes out_dir/lines_<L>.npy and spots_<L>.npy ((n, 2) int64 [key,
    count], sorted by key) and cube.json last (removed first, so a half-built cube is never read).
    Returns cube.json's content."""
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(out_dir, "cube.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)
    lines, spots = _Reducer(sum_keys), _Reducer(merge_spots)
    for path in tiles:
        counts, _ = load_tile(path)
        lines.add(counts.line_keys, counts.line_counts)
        spots.add(counts.spot_ids, counts.spot_records)
    line_keys, line_counts = lines.flush()
    ids, records = spots.flush()
    i, j = spot_cells(ids)
    spot_keys, spot_counts = count_keys(pack_keys(i, j, records))
    del ids, records, i, j
    keys_total = {}
    for mode, keys, counts in (("lines", line_keys, line_counts), ("spots", spot_keys, spot_counts)):
        for level in LEVELS:
            k, n = _level_keys(keys, counts, level)
            _save_npy(os.path.join(out_dir, f"{mode}_{level}.npy"), k, n)
            keys_total[f"{mode}_{level}"] = int(len(k))
    cube = {**info, "version": VERSION, "cell_m": CELL_M, "levels": list(LEVELS), "cluster_m": CLUSTER_M,
            "edges": {"length": list(LENGTH_EDGES), **{k: list(v) for k, v in EDGES.items()}},
            "totals": {"lines": int(line_counts.sum()), "spots": int(spot_counts.sum()), "keys": keys_total},
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with cache.replacing(meta_path, "w", encoding="utf-8") as f:
        json.dump(cube, f, indent=1)
    return cube


TREES = ("all", "no", "only")
WATERS = ("all", "land", "water")


def _edges_text(edges) -> str:
    return ", ".join(f"{e:g}" for e in edges)


@dataclass(frozen=True)
class Filters:
    """The filters of the layer, on the bins' edges: a line passes when its length bin lies within
    `length`, its weaker anchor's prominence >= `prominence`, its steeper anchor's wall angle <
    `wall`, its clearance >= `clearance`, its webbing height >= `height`, and over trees and water
    as asked. An UNKNOWN value passes only a filter that is off (0, or None for the wall)."""
    length: Tuple[float, float] = (30, 5000)  # metres, both edges of LENGTH_EDGES
    prominence: float = 0      # >= (0: no filter, UNKNOWN passes only then)
    wall: Optional[float] = None  # < (None: no filter, UNKNOWN passes only then)
    clearance: float = 0       # >=
    height: float = 0          # >=
    trees: str = "all"         # all | no (some line not over trees) | only (some line over them)
    water: str = "all"         # all | land (some line not over water) | water (some line over water)

    def __post_init__(self):
        lo, hi = self.length
        if lo not in LENGTH_EDGES or hi not in LENGTH_EDGES or not lo < hi:
            raise ValueError(f"the length range must be two different lengths of {_edges_text(LENGTH_EDGES)} m, "
                             "the shorter first")
        for name in ("prominence", "clearance", "height"):
            if getattr(self, name) not in EDGES[name]:
                raise ValueError(f"{name} must be one of {_edges_text(EDGES[name])}")
        if self.wall is not None and self.wall not in EDGES["wall"]:
            raise ValueError(f"wall must be one of {_edges_text(EDGES['wall'])}, or left out")
        if self.trees not in TREES:
            raise ValueError(f"trees must be one of {', '.join(TREES)}")
        if self.water not in WATERS:
            raise ValueError(f"water must be one of {', '.join(WATERS)}")

    @classmethod
    def parse(cls, query: Mapping[str, str]) -> "Filters":
        """Filters from the web's query strings (length "<lo>-<hi>", prominence, wall, clearance,
        height, trees, water; others ignored, absent or empty ones off); ValueError with a plain
        message for a value off the edges."""
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
        for name in ("prominence", "clearance", "height", "wall"):
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


def select(keys: np.ndarray, filters: Filters) -> np.ndarray:
    """A boolean mask of the keys (of lines or spots) passing the filters."""
    keys = np.asarray(keys, dtype=np.int64)
    mask = ((keys >> LENGTH_SHIFT) & filters.length_mask()) != 0
    for name in ("prominence", "clearance", "height"):
        value = getattr(filters, name)
        if value != EDGES[name][0]:
            b = (keys >> SHIFT[name]) & 7
            mask &= (b != UNKNOWN) & (b >= EDGES[name].index(value))
    if filters.wall is not None:
        b = (keys >> SHIFT["wall"]) & 7
        mask &= (b != UNKNOWN) & (b < EDGES["wall"].index(filters.wall))
    if filters.trees != "all":
        mask &= (keys & (1 << (TREES_BIT + (filters.trees == "only")))) != 0
    if filters.water != "all":
        mask &= (keys & (1 << (WATER_BIT + (filters.water == "water")))) != 0
    return mask


Box = Tuple[float, float, float, float]


class Cube:
    """A built cube: cube.json and the .npy files, each read into memory when first used (not
    memory-mapped: a mapped file stays open, and Windows would refuse the next build's replacing
    it while the app shows the layer)."""

    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "cube.json"), encoding="utf-8") as f:
            self.info: Dict = json.load(f)
        if self.info.get("version") != VERSION:
            raise ValueError(f"{folder}: a cube of version {self.info.get('version')}, not {VERSION}: build it again")
        self.origin = (float(self.info["origin"][0]), float(self.info["origin"][1]))
        self.crs = self.info["crs"]
        self.levels = tuple(self.info.get("levels", LEVELS))
        self._arrays: Dict[str, np.ndarray] = {}
        self._to_crs = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        self._to_wgs84 = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)

    def array(self, mode: str, level: int) -> np.ndarray:
        """The (n, 2) [key, count] rows of a mode ("lines" or "spots") and level."""
        if mode not in ("lines", "spots"):
            raise ValueError("mode must be lines or spots")
        if level not in self.levels:
            raise ValueError(f"level must be one of {', '.join(map(str, self.levels))}")
        name = f"{mode}_{level}"
        if name not in self._arrays:
            self._arrays[name] = np.load(os.path.join(self.folder, name + ".npy"))
        return self._arrays[name]

    def box(self, west: float, south: float, east: float, north: float) -> Box:
        """A WGS84 box in the cube's CRS (its edges densified). It is clipped first to the country's
        bounds_wgs84 with a margin of a degree, so a view of half the world stays finite; a view
        away from the country gives an empty box (left > right)."""
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
                return (self.origin[0], self.origin[1], self.origin[0] - 1, self.origin[1] - 1)
        out = self._to_crs.transform_bounds(west, south, east, north, densify_pts=DENSIFY)
        if not all(math.isfinite(v) for v in out):
            raise ValueError("the box lies outside the country's coordinate system")
        return tuple(float(v) for v in out)

    def _range(self, level: int, box: Box) -> Tuple[int, int, int, int]:
        """The columns and rows (inclusive) of the level's cells touching box (may be empty)."""
        size = level * CELL_M
        x0, y0 = self.origin
        return (math.floor((box[0] - x0) / size), math.floor((box[2] - x0) / size),
                math.floor((box[1] - y0) / size), math.floor((box[3] - y0) / size))

    def auto_level(self, box: Box, most: int = 4000) -> int:
        """The finest level with at most `most` cells over box (by its geometry), else the coarsest."""
        for level in sorted(self.levels):
            i0, i1, j0, j1 = self._range(level, box)
            if max(i1 - i0 + 1, 0) * max(j1 - j0 + 1, 0) <= most:
                return level
        return max(self.levels)

    def cell_count(self, level: int, box: Box) -> int:
        """The number of the level's cells over box (by its geometry)."""
        i0, i1, j0, j1 = self._range(level, box)
        return max(i1 - i0 + 1, 0) * max(j1 - j0 + 1, 0)

    def cells(self, mode: str, level: int, box: Optional[Box], filters: Filters
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """i, j and count of the level's cells inside box (None: all) passing filters, count > 0."""
        rows = self.array(mode, level)
        empty = np.zeros(0, dtype=np.int64)
        if box is None:
            part = np.asarray(rows)
            j0, j1 = 0, CELL_MASK
        else:
            i0, i1, j0, j1 = self._range(level, box)
            i0, j0 = max(i0, 0), max(j0, 0)
            i1, j1 = min(i1, CELL_MASK), min(j1, CELL_MASK)
            if i0 > i1 or j0 > j1:
                return empty, empty, empty
            keys = rows[:, 0]
            lo = int(np.searchsorted(keys, i0 << COL_SHIFT, side="left"))
            hi = int(np.searchsorted(keys, (i1 + 1) << COL_SHIFT, side="left"))
            part = np.asarray(rows[lo:hi])
        if not len(part):
            return empty, empty, empty
        keys, counts = part[:, 0], part[:, 1]
        j = (keys >> ROW_SHIFT) & CELL_MASK
        mask = select(keys, filters)
        if box is not None:
            mask &= (j >= j0) & (j <= j1)
        cell = (keys >> ROW_SHIFT)[mask]  # sorted, as the keys are
        counts = counts[mask]
        if not len(cell):
            return empty, empty, empty
        starts = np.flatnonzero(np.concatenate(([True], cell[1:] != cell[:-1])))
        total = np.add.reduceat(counts, starts)
        cell = cell[starts]
        keep = total > 0
        cell, total = cell[keep], total[keep]
        return cell >> (COL_SHIFT - ROW_SHIFT), cell & CELL_MASK, total.astype(np.int64)

    def corners(self, level: int, i: np.ndarray, j: np.ndarray) -> np.ndarray:
        """(n, 4, 2) [lat, lon] of the cells' corners: SW, SE, NE, NW."""
        size = level * CELL_M
        i, j = np.asarray(i, dtype=np.float64), np.asarray(j, dtype=np.float64)
        west, south = self.origin[0] + i * size, self.origin[1] + j * size
        xs = np.stack([west, west + size, west + size, west], axis=1)
        ys = np.stack([south, south, south + size, south + size], axis=1)
        lon, lat = self._to_wgs84.transform(xs.ravel(), ys.ravel())
        out = np.empty((len(i), 4, 2))
        out[:, :, 0] = np.asarray(lat).reshape(-1, 4)
        out[:, :, 1] = np.asarray(lon).reshape(-1, 4)
        return out

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


def _project(geometry, transformer: Transformer):
    return shapely.transform(geometry, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))


REQUEST_DECIMALS = 6   # degrees of a cell request's geometry (about 0.1 m)
REQUEST_SEGMENT_M = 100.0  # its edges densified to this before they go back to WGS84


def cell_request(cube: Cube, band: str, level: int, i: int, j: int) -> Dict:
    """The search of one cell (a SearchRequest: {"params", "geometry"}): the level's square buffered
    by the band's max_length, intersected with the country's outline, as a WGS84 GeoJSON Polygon or
    MultiPolygon; the band's params from cube.json. ValueError for a band not in the layer, a level
    not in the cube or a cell outside the country."""
    found = [b for b in cube.info.get("bands", []) if b.get("name") == band and b.get("layer")]
    if not found:
        names = [b["name"] for b in cube.info.get("bands", []) if b.get("layer")]
        raise ValueError(f"band must be one of {', '.join(names)}")
    if level not in cube.levels:
        raise ValueError(f"level must be one of {', '.join(map(str, cube.levels))}")
    b = found[0]
    params = dict(b.get("params", {}))
    reach = float(params.get("max_length", b["lengths"][1]))
    size = level * CELL_M
    x, y = cube.origin[0] + i * size, cube.origin[1] + j * size
    square = shapely_box(x, y, x + size, y + size)
    outline = _project(cube.outline(), cube._to_crs)
    if i < 0 or j < 0 or not square.intersects(outline):
        raise ValueError("the cell lies outside the country")
    region = square.buffer(reach).intersection(outline)
    region = shapely.segmentize(region, REQUEST_SEGMENT_M)
    back = _project(region, cube._to_wgs84)
    back = shapely.transform(back, lambda xy: np.round(xy, REQUEST_DECIMALS))
    if not back.is_valid:
        back = shapely.make_valid(back)
    polygons = [g for g in getattr(back, "geoms", [back]) if g.geom_type in ("Polygon", "MultiPolygon")]
    parts = [p for g in polygons for p in getattr(g, "geoms", [g])]
    if not parts:
        raise ValueError("the cell lies outside the country")
    geometry = parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts)
    geometry = shapely.orient_polygons(geometry)  # RFC 7946: exteriors counterclockwise
    return {"params": params, "geometry": json.loads(shapely.to_geojson(geometry))}
