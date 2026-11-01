"""
The greedy loop of mapping.group_lines in numba (imported inside it: `import mapping` stays free
of numba).

The same arithmetic and order as the numpy loop it replaced (and as viewer/src/grouping.ts): the
lines sorted best first, each line still free becomes a representative and takes every free line
whose anchors both lie within `distance` of its own (or of its own the other way round), the
squares of the differences in x and y added in that order and compared with `d2` in float64; the
candidates are the lines of the 3 x 3 cells around each of its anchors (mapping._cell_index), its
members in ascending order.
"""

import math

import numpy as np
from numba import njit


@njit(cache=True)
def _close(px, py, qx, qy, d2):
    dx = px - qx
    dy = py - qy
    return dx * dx + dy * dy <= d2


@njit(cache=True)
def greedy(a1, a2, rows, order, keys, low, high, width, distance, d2, free, begin, end,
           reps, members, sizes, n_reps, n_members):
    """Groups of the lines at positions begin..end-1 of rows (best first) that are still free.

    a1, a2: the anchors (x, y) of all lines, rows: the lines of this part in their order; order,
    keys, low, high, width: mapping._cell_index of a1[rows]. A representative's position goes to
    reps[n_reps], its members' positions (ascending) to members from n_members on and their count
    to sizes[n_reps]; free is cleared for every member. Returns the new n_reps and n_members.
    """
    for i in range(begin, end):
        if not free[i]:
            continue
        r = rows[i]
        first = n_members
        for p in range(2):
            px = a1[r, 0] if p == 0 else a2[r, 0]
            py = a1[r, 1] if p == 0 else a2[r, 1]
            cx = np.int64(math.floor(px / distance))
            cy = np.int64(math.floor(py / distance))
            y0 = max(cy - 1, low[1])
            y1 = min(cy + 1, high[1])
            if y0 > y1:
                continue
            for x in range(max(cx - 1, low[0]), min(cx + 1, high[0]) + 1):
                row = (x - low[0]) * width - low[1]  # the key of cell (x, y) is row + y
                lo = np.searchsorted(keys, row + y0, side="left")
                hi = np.searchsorted(keys, row + y1, side="right")
                for s in range(lo, hi):
                    k = order[s]
                    if not free[k]:
                        continue  # taken already, or met before through the other anchor's cells
                    q = rows[k]
                    same = (_close(a1[q, 0], a1[q, 1], a1[r, 0], a1[r, 1], d2)
                            and _close(a2[q, 0], a2[q, 1], a2[r, 0], a2[r, 1], d2))
                    flipped = (_close(a1[q, 0], a1[q, 1], a2[r, 0], a2[r, 1], d2)
                               and _close(a2[q, 0], a2[q, 1], a1[r, 0], a1[r, 1], d2))
                    if same or flipped:
                        free[k] = False
                        members[n_members] = k
                        n_members += 1
        members[first:n_members] = np.sort(members[first:n_members])
        reps[n_reps] = i
        sizes[n_reps] = n_members - first
        n_reps += 1
    return n_reps, n_members


@njit(cache=True)
def gather(members, start, order, out):
    """The members of the groups in `order` one after another: group g's are members[start[g]:start[g + 1]]."""
    n = 0
    for g in order:
        for s in range(start[g], start[g + 1]):
            out[n] = members[s]
            n += 1
