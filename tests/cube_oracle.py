"""The oracle of the layer's answers: countcube's Cube.cells, Cube.histogram and what they called (select,
border_kept, _slice, reaching, _view_rows, with _range, corners and _field) as they were at b45b950, before the
lean code of the branch explorer-speed, frozen as functions of a Cube. The tests compare countcube's answers
with these (tests/test_countcube.py: the grid of queries; tests/test_country_web.py: the web's answers), so an
answer of the lean code that differs from today's code fails a test. Never imported by the app. A change of what
an answer means (Filters' semantics, the key) changes this copy in the same commit, on purpose; a change of
speed or memory never does. It reads the arrays through Cube._rows and the format's constants of countcube (the
cube's file format, countcube.VERSION)."""
import math
from typing import Dict, Optional, Tuple

import numpy as np

import countcube as cc


def _field(keys: np.ndarray, name: str) -> np.ndarray:
    if name in cc.SHIFT:
        return (keys[:, 0] >> cc.SHIFT[name]) & 7
    return (keys[:, 1] >> cc.B_SHIFT[name]) & 7


def border_kept(keys: np.ndarray, filters: cc.Filters) -> Optional[np.ndarray]:
    if filters.border == "all" and not filters.replaced:
        return None
    a = np.asarray(keys, dtype=np.int64).reshape(-1, 2)[:, 0]
    partner_line = ((a >> cc.BORDER_SHIFT) & 3) == 2
    if filters.border == "own":
        return ~partner_line
    return ~(partner_line & np.isin((a >> cc.PARTNER_SHIFT) & 7, np.asarray(filters.replaced, dtype=np.int64)))


def select(keys: np.ndarray, filters: cc.Filters, skip: Optional[str] = None) -> np.ndarray:
    if skip is not None and skip not in cc.DIMENSIONS:
        raise ValueError(f"skip must be one of {', '.join(cc.DIMENSIONS)}")
    keys = np.asarray(keys, dtype=np.int64).reshape(-1, 2)
    a = keys[:, 0]
    if skip == "length":
        mask = np.ones(len(keys), dtype=bool)
    else:
        mask = ((a >> cc.LENGTH_SHIFT) & filters.length_mask()) != 0
    for name, kind in cc.KINDS.items():
        if name == skip or not filters.active(name):
            continue
        b = _field(keys, name)
        index = cc.EDGES[name].index(getattr(filters, name))
        if kind == "floor":
            mask &= (b != cc.UNKNOWN) & (b >= index)
        elif kind == "below":
            mask &= (b != cc.UNKNOWN) & (b < index)
        else:
            mask &= (b != cc.UNKNOWN) & (b <= index)
    if filters.trees != "all":
        mask &= (a & (1 << (cc.TREES_BIT + (filters.trees == "only")))) != 0
    if filters.water != "all":
        mask &= (a & (1 << (cc.WATER_BIT + (filters.water == "water")))) != 0
    kept = border_kept(keys, filters)
    if kept is not None:
        mask &= kept
    return mask


def _range(cube: cc.Cube, level: int, box) -> Tuple[int, int, int, int]:
    if box[0] > box[2] or box[1] > box[3]:
        return (0, -1, 0, -1)
    i0, j0 = cube.origin
    e = cc.RANGE_EPSILON
    return (math.floor((box[0] * cc.CELLS_PER_DEGREE - i0) / level - e),
            math.floor((box[2] * cc.CELLS_PER_DEGREE - i0) / level + e),
            math.floor((box[1] * cc.CELLS_PER_DEGREE - j0) / level - e),
            math.floor((box[3] * cc.CELLS_PER_DEGREE - j0) / level + e))


def corners(cube: cc.Cube, level: int, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    i, j = np.asarray(i, dtype=np.int64), np.asarray(j, dtype=np.int64)
    west = (cube.origin[0] + i * level) / cc.CELLS_PER_DEGREE
    east = (cube.origin[0] + (i + 1) * level) / cc.CELLS_PER_DEGREE
    south = (cube.origin[1] + j * level) / cc.CELLS_PER_DEGREE
    north = (cube.origin[1] + (j + 1) * level) / cc.CELLS_PER_DEGREE
    out = np.empty((len(i), 4, 2))
    out[:, :, 0] = np.stack([south, south, north, north], axis=1)
    out[:, :, 1] = np.stack([west, east, east, west], axis=1)
    return out


def _slice(cube: cc.Cube, mode: str, level: int, box) -> Tuple[np.ndarray, np.ndarray]:
    keys, counts = cube._rows(mode, level)
    empty = np.zeros(0, dtype=np.int64)
    if box is None:
        return keys, counts
    i0, i1, j0, j1 = _range(cube, level, box)
    i0, j0 = max(i0, 0), max(j0, 0)
    i1, j1 = min(i1, cc.CELL_MASK), min(j1, cc.CELL_MASK)
    if i0 > i1 or j0 > j1:
        return empty.reshape(0, 2), empty
    a = keys[:, 0]
    lo = int(np.searchsorted(a, i0 << cc.COL_SHIFT, side="left"))
    hi = int(np.searchsorted(a, (i1 + 1) << cc.COL_SHIFT, side="left"))
    keys, counts = keys[lo:hi], counts[lo:hi]
    j = (keys[:, 0] >> cc.ROW_SHIFT) & cc.CELL_MASK
    mask = (j >= j0) & (j <= j1)
    return keys[mask], counts[mask]


def cells(cube: cc.Cube, mode: str, level: int, box, filters: cc.Filters, sides: bool = False
          ) -> Tuple[np.ndarray, ...]:
    empty = np.zeros(0, dtype=np.int64)
    keys, counts = _slice(cube, mode, level, box)
    if not len(keys):
        return (empty,) * (4 if sides else 3)
    mask = select(keys, filters)
    a = keys[:, 0][mask]
    cell = a >> cc.ROW_SHIFT
    counts = counts[mask]
    if not len(cell):
        return (empty,) * (4 if sides else 3)
    if sides:
        side = np.where(((a >> cc.BORDER_SHIFT) & 3) == 2, (a >> cc.PARTNER_SHIFT) & 7, 0)
        group = (cell << 3) | side
        order = np.argsort(group, kind="stable")
        group, counts = group[order], counts[order]
    else:
        group = cell
    starts = np.flatnonzero(np.concatenate(([True], group[1:] != group[:-1])))
    total = np.add.reduceat(counts, starts)
    group = group[starts]
    keep = total > 0
    group, total = group[keep], total[keep]
    if not sides:
        return group >> (cc.COL_SHIFT - cc.ROW_SHIFT), group & cc.CELL_MASK, total.astype(np.int64)
    cell = group >> 3
    return cell >> (cc.COL_SHIFT - cc.ROW_SHIFT), cell & cc.CELL_MASK, group & 7, total.astype(np.int64)


def reaching(cube: cc.Cube, level: int, keys: np.ndarray, view, decimals: Optional[int] = None) -> np.ndarray:
    west, south, east, north = view
    keys = np.asarray(keys, dtype=np.int64).reshape(-1, 2)
    cell = keys[:, 0] >> cc.ROW_SHIFT
    if not len(cell):
        return np.zeros(0, dtype=bool)
    unique, inverse = np.unique(cell, return_inverse=True)
    c = corners(cube, level, unique >> (cc.COL_SHIFT - cc.ROW_SHIFT), unique & cc.CELL_MASK)
    if decimals is not None:
        c = np.round(c, decimals)
    lat, lon = c[:, :, 0], c[:, :, 1]
    ok = (lat.max(1) >= south) & (lat.min(1) <= north) & (lon.max(1) >= west) & (lon.min(1) <= east)
    return ok[inverse.reshape(-1)]


def _view_rows(cube: cc.Cube, mode: str, level: int, box, view, decimals: Optional[int]):
    if view is not None and box is not None and box[0] <= box[2] and box[1] <= box[3]:
        size = level * cc.CELL_DEG
        box = (box[0] - size, box[1] - size, box[2] + size, box[3] + size)
    keys, counts = _slice(cube, mode, level, box)
    if view is not None and len(keys):
        near = reaching(cube, level, keys, view, decimals)
        keys, counts = keys[near], counts[near]
    return keys, counts


class OracleCube(cc.Cube):
    """A Cube answering cells and histogram with the oracle (the web's answers of today's code)."""

    def cells(self, mode, level, box, filters, sides=False, check=None):
        return cells(self, mode, level, box, filters, sides)

    def histogram(self, mode, level, box, filters, view=None, decimals=None, summary=False, check=None):
        return histogram(self, mode, level, box, filters, view, decimals, summary)


def histogram(cube: cc.Cube, mode: str, level: int, box, filters: cc.Filters, view=None,
              decimals: Optional[int] = None, summary: bool = False) -> Dict:
    keys, counts = _view_rows(cube, mode, level, box, view, decimals)
    out: Dict = {"total": int(counts[select(keys, filters)].sum()) if len(keys) else 0}
    if summary:
        out["totals"] = {mode: out["total"]}
        for other in ("lines", "spots"):
            if other == mode:
                continue
            k, n = _view_rows(cube, other, level, box, view, decimals)
            out["totals"][other] = int(n[select(k, filters)].sum()) if len(k) else 0
        out["totals"] = {m: out["totals"][m] for m in ("lines", "spots")}
        k, n = (keys, counts) if mode == "lines" else _view_rows(cube, "lines", level, box, view, decimals)
        mask = select(k, filters) if len(k) else np.zeros(0, dtype=bool)
        split = np.bincount((k[:, 0][mask] >> cc.BORDER_SHIFT) & 3, weights=n[mask].astype(np.float64), minlength=3)
        out["border"] = {name: int(round(split[b])) for b, name in enumerate(("interior", "owned", "partner"))}
    if not len(keys):
        out["length"] = [0] * cc.LENGTH_BINS
        for name in cc.KINDS:
            out[name] = [0] * (cc.bins_of(name) + 1)
        return out
    weights = counts.astype(np.float64)  # exact below 2^53
    mask = select(keys, filters, skip="length")
    bits = (keys[:, 0] >> cc.LENGTH_SHIFT)[mask]
    out["length"] = [int(round(weights[mask][(bits & (1 << k)) != 0].sum())) for k in range(cc.LENGTH_BINS)]
    for name in cc.KINDS:
        mask = select(keys, filters, skip=name)
        h = np.bincount(_field(keys, name)[mask], weights=weights[mask], minlength=8)
        out[name] = [int(round(v)) for v in (*h[:cc.bins_of(name)], h[cc.UNKNOWN])]
    return out
