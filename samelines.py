"""
The square rule (--same-line-square, off by default): of all valid lines between the same two anchor
squares one is kept, while the pair search runs.

The ground is cut into squares, a lattice with a corner at (0, 0) of the grid's CRS, so the same squares
for every tile, grid and area. Their side is the option's value in metres on data of 1 m or finer and
that many pixels on coarser data (side(): 5 gives 5 m at 1 m and 10 m at 2 m; a square of fixed metres
would hold too few pixels of a coarse grid to join anything). A line's key is the pair of its anchors'
squares without order.

BestPerSquarePair is the sink of step 3 (linesearch.find_valid_lines(sink=), search._pair_search): it
takes the evaluated parts and keeps per key the first line of a fixed order (the module's ORDER below),
with the number of found lines the key had (COLUMN, "stands_for": the kept line among them). The
dropped lines are never held beyond their own part. "The first of a key" and "the sum of a key" are
commutative and associative, so the parts, the tiles and the threads may come in any order and give the
same lines; reduce_table does the same on a tiled search's join, where a key may hold a line of each of
two tiles (a line belongs to the tile of its first anchor, its key to neither).

The order of the lines of a key: a line that needs neither the no-fall zone nor A-frames (lift_no_zone
0), then one that needs no A-frames (lift_needed 0), then the highest mean height above the terrain, then
the longest, then the anchors' coordinates (the first anchor's x, y, then the second's; the first anchor
is the one with the smaller x, then y, as mapping.first_anchor). Without the no-fall zone and A-frames
the first two steps do not exist. No two lines share both anchors, so the order is total.

Plain numpy (no numba): the reducer runs between the kernels' parts, on one thread.
"""

from typing import Callable, Dict, Optional

import numpy as np

import helpers as sh

COLUMN = "stands_for"      # the kept lines' column (int64): the found lines of the line's pair of squares
MERGE_ROWS = 1 << 20       # reduced parts are merged into the kept lines once this many rows wait (or as many
                           # as the kept lines, if more): each merge sorts the kept lines once
CHECK_ROWS = 1 << 16       # with a check: the rows that wait (or an eighth of the kept lines, if more) before
                           # the check is asked whether the rows held would be refused (then merged at once)
_KEYS = ("_ka", "_kb", "_xa", "_ya", "_xb", "_yb")  # the helper columns of a part and of the kept lines


def side(square: float, resolution: float) -> float:
    """The side of the squares in metres: `square` metres on data of 1 m or finer, `square` pixels on
    coarser data (the option's "5 pixels wide, at least 5 m")."""
    return float(square) * max(1.0, float(resolution))


def square_keys(xa: np.ndarray, ya: np.ndarray, xb: np.ndarray, yb: np.ndarray, side: float):
    """The two halves of a line's key from its ends in the grid's CRS: the squares of both ends, the
    smaller (square x, then square y) first; each square as one int64."""
    s = float(side)
    cxa, cya = np.floor(xa / s).astype(np.int64), np.floor(ya / s).astype(np.int64)
    cxb, cyb = np.floor(xb / s).astype(np.int64), np.floor(yb / s).astype(np.int64)
    first = (cxa < cxb) | ((cxa == cxb) & (cya <= cyb))
    one, two = (cxa << 32) + cya, (cxb << 32) + cyb
    return np.where(first, one, two), np.where(first, two, one)


def _keyed(table: sh.LineTable, x1: np.ndarray, y1: np.ndarray, x2: np.ndarray, y2: np.ndarray, side: float):
    """Give the table its helper columns (_KEYS) from the coordinates of its lines' anchors: the key's
    halves and the anchors in the order first, second (mapping.first_anchor's)."""
    first = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
    xa, ya = np.where(first, x1, x2), np.where(first, y1, y2)
    xb, yb = np.where(first, x2, x1), np.where(first, y2, y1)
    ka, kb = square_keys(xa, ya, xb, yb, side)
    table.columns.update(_ka=ka, _kb=kb, _xa=xa, _ya=ya, _xb=xb, _yb=yb)


def _reduce(table: sh.LineTable) -> sh.LineTable:
    """One row per key of a table with the helper columns and COLUMN (in place; returns it): the first
    by the module's order, its COLUMN the sum of the key's; the rows left in the order of the keys."""
    c = table.columns
    ranks = [c["_yb"], c["_xb"], c["_ya"], c["_xa"], -c["length"], -c["height_mean"]]
    if sh.END_VALUES[0] in c:  # with the no-fall zone or A-frames: the least rigging first
        needed, no_zone = (c[name] for name in sh.END_VALUES)
        ranks.append(np.where(no_zone == 0, 0, np.where(needed == 0, 1, 2)).astype(np.int8))
    index = np.lexsort(tuple(ranks) + (c["_kb"], c["_ka"]))
    del ranks
    ka, kb = c["_ka"][index], c["_kb"][index]
    new = np.ones(len(index), dtype=bool)
    new[1:] = (ka[1:] != ka[:-1]) | (kb[1:] != kb[:-1])
    del ka, kb
    starts = np.flatnonzero(new)
    count = np.add.reduceat(c[COLUMN][index], starts) if len(index) else c[COLUMN]
    table.reorder(index[starts])
    table.columns[COLUMN] = count
    return table


class BestPerSquarePair:
    """The reducer: call it with every evaluated part (a sink of linesearch.find_valid_lines), then
    table(). grid: the grid of the parts' pixels ("a1", "a2"). core (left, bottom, right, top): only the
    lines whose first anchor lies in it (a tile's own lines: search.line_coordinates' test). check: a
    callable given a number of lines that raises when the search may not hold that many
    (search._early_check); it is called with the kept lines after a merge, which only grow, so a search
    it stops would be refused at its end too. To bound the rows held between two merges it is also
    asked, without stopping, about the kept and the waiting rows together once CHECK_ROWS wait: a yes
    merges them at once."""

    def __init__(self, side: float, grid, core: Optional[tuple] = None,
                 check: Optional[Callable[[int], None]] = None):
        self.side, self.grid, self.core, self.check = float(side), grid, core, check
        self.found = 0            # the lines handed in (within core)
        self.kept: Optional[sh.LineTable] = None
        self.waiting, self.rows_waiting = [], 0
        self.peak_rows = 0        # the most rows held at once (kept and waiting)

    def __call__(self, part: sh.LineTable):
        if not len(part):
            return
        c = part.columns
        x1, y1 = self.grid.pixel_to_xy(c["a1"][:, 0], c["a1"][:, 1])
        x2, y2 = self.grid.pixel_to_xy(c["a2"][:, 0], c["a2"][:, 1])
        _keyed(part, x1, y1, x2, y2, self.side)
        del x1, y1, x2, y2
        if self.core is not None:
            left, bottom, right, top = self.core
            xa, ya = c["_xa"], c["_ya"]
            inside = (left <= xa) & (xa < right) & (bottom <= ya) & (ya < top)
            if not inside.all():
                part.reorder(inside)
                if not len(part):
                    return
        self.found += len(part)
        part.columns[COLUMN] = np.ones(len(part), dtype=np.int64)
        self.waiting.append(_reduce(part))
        self.rows_waiting += len(part)
        kept = len(self.kept) if self.kept is not None else 0
        self.peak_rows = max(self.peak_rows, kept + self.rows_waiting)
        if self.rows_waiting >= max(MERGE_ROWS, kept) or (
                self.check is not None and self.rows_waiting >= max(CHECK_ROWS, kept // 8)
                and self._refused(kept + self.rows_waiting)):
            self._merge()
            if self.check is not None:
                self.check(len(self.kept))

    def _refused(self, rows: int) -> bool:
        try:
            self.check(rows)
        except Exception:
            return True
        return False

    def _merge(self):
        tables = ([self.kept] if self.kept is not None else []) + self.waiting
        self.waiting, self.rows_waiting = [], 0
        if tables:
            self.kept = tables[0] if len(tables) == 1 else _reduce(sh.LineTable.join(tables))

    def table(self) -> sh.LineTable:
        """The kept lines, one per key, in the order of the keys (the same for every order of the parts),
        with COLUMN; an empty table when no line came. The reducer is empty afterwards."""
        self._merge()
        if self.kept is None:
            table = sh.LineTable.empty()
            table.columns[COLUMN] = np.zeros(0, dtype=np.int64)
            return table
        table, self.kept = self.kept, None
        for name in _KEYS:
            table.columns.pop(name)
        return table

    def counts(self) -> Dict[str, int]:
        """found (the lines handed in), kept (the keys so far), peak_rows (the most rows held at once)."""
        self._merge()
        return {"found": self.found, "kept": len(self.kept) if self.kept is not None else 0,
                "peak_rows": self.peak_rows}


def reduce_table(table: sh.LineTable, side: float) -> sh.LineTable:
    """One line per key of a table of kept lines with coordinates ("a1_xy", "a2_xy": after
    mapping.coordify) and COLUMN, in place: the join of a tiled search's tiles. The lines left stand as
    one grid's: in the order of the keys, then the longest first (a stable sort, as the pair search's)."""
    if not len(table):
        return table
    c = table.columns
    a1, a2 = c["a1_xy"], c["a2_xy"]
    _keyed(table, a1[:, 0], a1[:, 1], a2[:, 0], a2[:, 1], side)
    del a1, a2
    _reduce(table)
    for name in _KEYS:
        c.pop(name)
    return table.reorder(np.argsort(-c["length"], kind="stable"))
