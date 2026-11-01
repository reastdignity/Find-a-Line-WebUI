"""
Fast search for valid lines between anchors (numba).

Three steps, none of which loses a valid line:
1. Free rings. For every anchor and each of SECTORS directions: how many rings of
   pixels around the anchor a line in that direction can cross before the terrain
   is certainly too high, using the weakest limit possible for any partner. Anchors
   with no open direction are dropped.
2. Pairs. Partners are found on a grid of buckets and must pass the length and
   height-difference limits, and both anchors must be open towards each other. Buckets
   that hold no partner to keep (lower indices, beyond the longest line or beyond what
   the anchor's rings can reach) are skipped whole.
3. Exact check. The pixels of the line are checked from both anchors inwards and
   the check stops at the first pixel that is too high (most lines fail next to an
   anchor).
The kernels keep pairs within EPS of the limit; the pairs found are evaluated
once more by helpers.evaluate_line, which makes the final decision and gives the
clearances, so the results are exactly those of the plain pixel-by-pixel search.
"""

import math
import time
from typing import Dict, List, Optional

import numba
import numpy as np
from numba import njit, prange

import helpers as sh
from progress import progress

SECTORS = 64   # direction sectors per anchor
RINGS = 64     # rings of pixels around an anchor checked per sector
EPS = 1e-6     # metres; borderline pairs are passed on to evaluate_line
CHUNKS = 200   # anchors are processed in this many parts (progress updates)
RING_CHUNK = 1 << 16  # anchors per call of _free_rings (only the rows of the open ones are kept)


@njit(cache=True)
def _index(x, xs):
    """Fractional position of x in the increasing array xs, clamped to its ends."""
    n = xs.size
    if x <= xs[0]:
        return 0.0
    if x >= xs[n - 1]:
        return float(n - 1)
    k = np.searchsorted(xs, x, side="right") - 1
    return k + (x - xs[k]) / (xs[k + 1] - xs[k])


@njit(cache=True)
def _line_ok(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone):
    """Whether the terrain stays below the maximum safe elevation along the line.

    The same limit as helpers.max_safe_elevation (formula or sag table), within EPS.
    """
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    if steps < 2:
        return False
    length = math.hypot(dr, dc) * res
    e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
    emin = min(e1, e2)
    i0, j0, a, b, points = 0, 0, 0.0, 0.0, table.shape[2]
    if use_sag:
        si = _index(math.log(length), log_spans)
        ri = _index((e1 - e2) / length, ratios)
        i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
        a, b = si - i0, ri - j0

    lo, hi = 1, steps - 1
    while lo <= hi:
        for k in (lo, hi):
            t = k / steps
            r = r1 + int(np.rint(dr * t))  # the pixels of helpers.evaluate_line
            c = c1 + int(np.rint(dc * t))
            if use_sag:
                x = t * (points - 1)
                f = min(int(x), points - 2)
                w = x - f
                s0 = ((1 - a) * (1 - b) * table[i0, j0, f] + a * (1 - b) * table[i0 + 1, j0, f]
                      + (1 - a) * b * table[i0, j0 + 1, f] + a * b * table[i0 + 1, j0 + 1, f])
                s1 = ((1 - a) * (1 - b) * table[i0, j0, f + 1] + a * (1 - b) * table[i0 + 1, j0, f + 1]
                      + (1 - a) * b * table[i0, j0 + 1, f + 1] + a * b * table[i0 + 1, j0 + 1, f + 1])
                limit = e1 + (e2 - e1) * t - (s0 * (1 - w) + s1 * w) - fall_zone
            else:
                limit = emin - sh.SLOPE * min(t, 1 - t) * length - sh.LEASH_FALL
            if not (limit - np.float64(z[r, c]) > -EPS):  # NaN (no data) fails too
                return False
        lo += 1
        hi -= 1
    return True


@njit(cache=True)
def _sector_masks():
    """For every pixel (i, j) of the rings, i and j in [-RINGS, RINGS] (index (i + RINGS) *
    (2 RINGS + 1) + j + RINGS): the sectors a line through it may lie in, as the bits of a
    uint64 (bit s: sector s). The pixel at angle atan2(i, j) on ring k = max(|i|, |j|) marks
    the sectors from floor((angle - delta) / width) to floor((angle + delta) / width) with
    delta = asin(0.71 / k) (see _free_rings)."""
    side = 2 * RINGS + 1
    masks = np.zeros(side * side, dtype=np.uint64)
    width = 2 * np.pi / SECTORS
    one = np.uint64(1)
    for i in range(-RINGS, RINGS + 1):
        for j in range(-RINGS, RINGS + 1):
            k = max(abs(i), abs(j))
            if k == 0:
                continue
            delta = math.asin(min(1.0, 0.7072 / k))
            angle = math.atan2(i, j)
            m = np.uint64(0)
            for s in range(int(math.floor((angle - delta) / width)),
                           int(math.floor((angle + delta) / width)) + 1):
                m |= one << np.uint64((s % SECTORS + SECTORS) % SECTORS)
            masks[(i + RINGS) * side + j + RINGS] = m
    return masks


_MASKS = []


def sector_masks() -> np.ndarray:
    """_sector_masks, computed once."""
    if not _MASKS:
        _MASKS.append(_sector_masks())
    return _MASKS[0]


def largest_need(min_length: float, max_length: float, res: float) -> int:
    """The rings a pair can need at most ((its Chebyshev length in pixels) // 2 for lines up to
    max_length, with a pixel to spare), at least the need of the shortest line: _free_rings
    stops there, which changes no decision of find_valid_lines."""
    need_min = min(RINGS, int(min_length / (res * math.sqrt(2))) // 2)
    return min(RINGS, max(need_min, (int(max_length / res) + 1) // 2))


@njit(parallel=True, cache=True)
def _free_rings(z, anchors, res, gain, cap, offset, kmax, masks):
    """For every anchor and sector: the number of rings a line can cross from the anchor, up
    to kmax (the largest need of a pair: larger values would change no decision; uint8).

    The k-th pixel of a line (DDA) lies on ring k (Chebyshev distance k) and at most
    half a pixel from the exact line, so its direction differs from the line's by at
    most asin(0.71 / k). A sector stays open at ring k if some pixel that may belong
    to a line in it is below e + min(gain * k * res, cap) - offset, where e is the
    elevation of the anchor: no limit for any partner is weaker than that. The sectors a
    pixel may belong to are its bits in masks (_sector_masks); a pixel none of whose
    sectors is open any more is not read.
    """
    n = anchors.shape[0]
    h, w = z.shape
    rings = np.zeros((n, SECTORS), dtype=np.uint8)
    side = 2 * RINGS + 1
    zero, one = np.uint64(0), np.uint64(1)
    for a in prange(n):
        r0, c0 = anchors[a, 0], anchors[a, 1]
        e = np.float64(z[r0, c0])
        alive = ~zero
        for k in range(1, kmax + 1):
            below = zero
            limit = e + min(gain * k * res, cap) - offset + EPS
            for i in range(-k, k + 1):
                rr = r0 + i
                if rr < 0 or rr >= h:
                    continue
                step = 1 if abs(i) == k else 2 * k  # whole top/bottom rows, two ends otherwise
                row = (i + RINGS) * side + RINGS
                for j in range(-k, k + 1, step):
                    cc = c0 + j
                    if cc < 0 or cc >= w:
                        continue
                    m = masks[row + j]
                    if (m & alive) == zero:
                        continue
                    if np.float64(z[rr, cc]) < limit:
                        below |= m
            alive &= below
            if alive == zero:
                break
            for s in range(SECTORS):
                if (alive >> np.uint64(s)) & one:
                    rings[a, s] = np.uint8(k)
    return rings


def free_directions(z: np.ndarray, anchors: np.ndarray, res: float, gain: float, cap: float, offset: float,
                    min_length: float, max_length: float):
    """Step 1: the anchors with an open direction (useful: those with a sector open up to the
    need of the shortest line), their rings (_free_rings, one uint8 row each, in the order of
    useful) and the row of every anchor (slot, int32; -1 for the others). _free_rings runs on
    RING_CHUNK anchors at a time, so the rings of the anchors without an open direction (most
    of them) are never held all at once."""
    kmax, masks = largest_need(min_length, max_length, res), sector_masks()
    need_min = min(RINGS, int(min_length / (res * math.sqrt(2))) // 2)
    useful, rows = [], []
    for start in range(0, len(anchors), RING_CHUNK):
        rings = _free_rings(z, anchors[start:start + RING_CHUNK], res, gain, cap, offset, kmax, masks)
        keep = np.flatnonzero(rings.max(axis=1) >= need_min)
        useful.append(keep + start)
        rows.append(rings[keep])
    useful = np.concatenate(useful).astype(np.int64) if useful else np.zeros(0, dtype=np.int64)
    rows = np.concatenate(rows) if rows else np.zeros((0, SECTORS), dtype=np.uint8)
    slot = np.full(len(anchors), -1, dtype=np.int32)
    slot[useful] = np.arange(len(useful), dtype=np.int32)
    return useful, rows, slot


@njit(cache=True)
def _sector(dr, dc):
    return int(math.floor(math.atan2(dr, dc) / (2 * np.pi / SECTORS))) % SECTORS


@njit(cache=True)
def _isqrt(n):
    """The largest integer whose square is at most n (n >= 0)."""
    r = int(math.sqrt(n))
    while r * r > n:
        r -= 1
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r


@njit(parallel=True, cache=True)
def _pairs(z, anchors, elev, rings, slot, rmax, todo, order, starts, cell, cells_x, res,
           min_length, max_length, max_dh_ratio, max_dh, d0, far2, kmax, down, cos_limit, strong,
           use_sag, log_spans, ratios, table, fall_zone, first_only, offsets, out, counts):
    """Partners of the anchors in todo that pass all tests: only partners with a higher index,
    or with first_only those for which the anchor is the first (smaller x, then y; a tile
    keeps the lines whose first anchor lies in its core). A pair is always checked and
    written from its lower index: the pixels sampled depend on the direction (rint).
    With cos_limit > -1, the line must leave both anchors within the wall angle whose
    cosine it is (down: helpers.downslope; within EPS, evaluate_lines decides). One of the
    two anchors must be strong (--min-prominence; all are without it). The rings and their
    largest value (rmax) of an anchor are rows slot[anchor] (the anchors with an open
    direction only: todo and the partners are all such).

    The partners are visited cell by cell in the order of the cells and of order (by index
    within a cell), skipping only partners that fail a test: cells all of whose anchors have
    a lower index (with first_only the cells left of the anchor's), cells whose nearest pixel
    is farther than sqrt(far2) pixels (beyond max_length), partners differing in height by
    more than d0 (the largest difference any length allows) and partners farther (Chebyshev)
    than 2 R + 1 pixels from either anchor when its largest ring R = rmax is below kmax (the
    largest need of a pair): their need exceeds R. Those fail the rings' test, which comes
    after the candidates are counted, so they are not counted as candidates.

    With offsets None, counts[q] = [candidate pairs, pairs checked, lines] for todo[q].
    Otherwise the pairs are written to out from offsets[q] on.
    """
    reach = int(max_length / res) // cell + 1
    cells_y = starts.size // cells_x
    for q in prange(todo.size):
        i = todo[q]
        ri, ci = anchors[i, 0], anchors[i, 1]
        cy, cx = ri // cell, ci // cell
        ei = elev[i]
        ri_max = rmax[slot[i]]
        span = 2 * np.int64(ri_max) + 1 if ri_max < kmax else np.int64(1) << 40  # Chebyshev reach
        candidates, checked, found = 0, 0, 0
        gy0 = max(max(0, cy - reach), max(0, ri - span) // cell)
        gy1 = min(min(cells_y - 1, cy + reach), (ri + span) // cell)
        for gy in range(gy0, gy1 + 1):
            y0 = gy * cell
            dy = max(0, max(y0 - ri, ri - (y0 + cell - 1)))
            rest = far2 - dy * dy
            if rest < 0:
                continue
            dx_max = min(_isqrt(rest), span)
            gx0 = max(max(0, cx - reach), max(0, ci - dx_max) // cell)
            if first_only:
                gx0 = max(gx0, cx)
            gx1 = min(min(cells_x - 1, cx + reach), (ci + dx_max) // cell)
            for gx in range(gx0, gx1 + 1):
                g = gy * cells_x + gx
                p0 = starts[g]
                end = starts[g + 1] if g + 1 < starts.size else order.size
                if p0 >= end:
                    continue
                if not first_only:  # the first partner with a higher index
                    if order[end - 1] <= i:
                        continue
                    lo, hi = p0, end - 1
                    while lo < hi:
                        mid = (lo + hi) // 2
                        if order[mid] > i:
                            hi = mid
                        else:
                            lo = mid + 1
                    p0 = lo
                for p in range(p0, end):
                    j = order[p]
                    if first_only:
                        if anchors[j, 1] < ci or (anchors[j, 1] == ci and anchors[j, 0] >= ri):
                            continue
                    if not (strong[i] or strong[j]):
                        continue
                    if abs(elev[j] - ei) > d0:  # the height test below at the longest length
                        continue
                    cheb = max(abs(anchors[j, 0] - ri), abs(anchors[j, 1] - ci))
                    if cheb > span:
                        continue
                    rj_max = rmax[slot[j]]
                    if rj_max < kmax and cheb > 2 * np.int64(rj_max) + 1:
                        continue
                    a, b = (i, j) if i < j else (j, i)
                    dr, dc = anchors[b, 0] - anchors[a, 0], anchors[b, 1] - anchors[a, 1]
                    length = math.hypot(dr, dc) * res
                    if length > max_length or length < min_length:
                        continue
                    if not (abs(elev[b] - elev[a]) <= min(max_dh_ratio * length, max_dh)):
                        continue
                    if cos_limit > -1.0:
                        n = math.hypot(dr, dc)
                        if (dr * down[a, 0] + dc * down[a, 1]) / n < cos_limit - EPS or \
                                -(dr * down[b, 0] + dc * down[b, 1]) / n < cos_limit - EPS:
                            continue
                    candidates += 1
                    need = min(RINGS, max(abs(dr), abs(dc)) // 2)
                    if rings[slot[a], _sector(dr, dc)] < need or rings[slot[b], _sector(-dr, -dc)] < need:
                        continue
                    checked += 1
                    if _line_ok(z, anchors[a, 0], anchors[a, 1], anchors[b, 0], anchors[b, 1], res,
                                use_sag, log_spans, ratios, table, fall_zone):
                        if offsets is not None:
                            out[offsets[q] + found, 0] = a
                            out[offsets[q] + found, 1] = b
                        found += 1
        counts[q, 0], counts[q, 1], counts[q, 2] = candidates, checked, found


def pair_arguments(z: np.ndarray, anchors: np.ndarray, elev: np.ndarray, useful: np.ndarray, rings: np.ndarray,
                   slot: np.ndarray, first: Optional[np.ndarray], res: float, min_length: float, max_length: float,
                   max_dh_ratio: float, max_dh: float, down: np.ndarray, cos_limit: float,
                   strong: Optional[np.ndarray], use_sag: bool, log_spans, ratios, table, fall_zone: float):
    """The anchors pairs are searched from (the useful ones; with first, those of a tile's
    core) and _pairs' arguments before and after todo, with the useful anchors (the only
    partners) bucketed into cells of a quarter of max_length. useful, rings, slot: those of
    free_directions."""
    todo_all = useful if first is None else useful[np.asarray(first)[useful]]
    cell = max(1, int(max_length / res) // 4)
    cells_x = z.shape[1] // cell + 1
    cells_y = z.shape[0] // cell + 1
    keys = (anchors[useful, 0] // cell) * cells_x + anchors[useful, 1] // cell
    order = useful[np.argsort(keys, kind="stable")]
    starts = np.searchsorted(np.sort(keys), np.arange(cells_y * cells_x)).astype(np.int64)
    rmax = rings.max(axis=1).astype(np.uint8) if len(rings) else np.zeros(0, dtype=np.uint8)
    kmax = largest_need(min_length, max_length, res)
    d0 = min(float(max_dh_ratio) * float(max_length), float(max_dh))
    far2 = int(math.floor((max_length / res + 2) ** 2))
    head = (z, anchors, elev, rings, slot, rmax)
    tail = (order, starts, cell, cells_x, res, float(min_length), float(max_length),
            float(max_dh_ratio), float(max_dh), d0, far2, kmax, down, cos_limit,
            np.ones(len(anchors), dtype=np.bool_) if strong is None else np.asarray(strong, dtype=np.bool_),
            use_sag, log_spans, ratios, table, float(fall_zone), first is not None)
    return todo_all, head, tail


def pair_chunk(args: tuple, todo: np.ndarray, tail: tuple):
    """The pairs of the anchors in todo (_pairs' arguments before and after todo): a counting
    pass over all of them, then a writing pass over those that found a line only, in the
    order of todo. Returns the counts of the counting pass and the pairs."""
    counts = np.zeros((len(todo), 3), dtype=np.int64)
    _pairs(*args, todo, *tail, None, np.zeros((0, 2), dtype=np.int64), counts)
    with_lines = counts[:, 2] > 0
    found = counts[with_lines, 2]
    out = np.empty((int(found.sum()), 2), dtype=np.int64)
    if len(found):
        offsets = np.concatenate([[0], np.cumsum(found)[:-1]]).astype(np.int64)
        _pairs(*args, np.ascontiguousarray(todo[with_lines]), *tail, offsets, out,
               np.zeros((len(found), 3), dtype=np.int64))
    return counts, out


@njit(cache=True)
def _interp(x, xp, fp):
    """np.interp of one value, with numpy's arithmetic (the same result to the last bit)."""
    n = xp.size
    if x != x:
        return x
    if x < xp[0]:
        return fp[0]
    if x > xp[n - 1]:
        return fp[n - 1]
    j = np.searchsorted(xp, x, side="right") - 1
    if j == n - 1 or xp[j] == x:
        return fp[j]
    slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j])
    result = slope * (x - xp[j]) + fp[j]
    if result != result:
        result = slope * (x - xp[j + 1]) + fp[j + 1]
        if result != result and fp[j] == fp[j + 1]:
            result = fp[j]
    return result


@njit(parallel=True, cache=True)
def _evaluate(z, s, has_s, anchors, found, res, use_sag, log_spans, span_index, ratios, ratio_index,
              sag, fractions, fall_zone, high_above, out):
    """helpers.evaluate_line for many lines, with the same arithmetic (identical results).

    out[k]: elev_a1, elev_a2, length, clearance, clearance over the surface (NaN: none),
    1 when the line has pixels between its anchors, then the largest and mean height of
    the webbing above the terrain and the % of pixels at least high_above.
    """
    blend = np.empty(fractions.size)
    fall = fall_zone if use_sag else sh.LEASH_FALL  # helpers.fall_allowance
    for k in prange(found.shape[0]):
        r1, c1 = anchors[found[k, 0], 0], anchors[found[k, 0], 1]
        r2, c2 = anchors[found[k, 1], 0], anchors[found[k, 1], 1]
        dr, dc = r2 - r1, c2 - c1
        steps = max(abs(dr), abs(dc))
        out[k, 5] = 0.0
        if steps < 2:
            continue
        length = np.hypot(np.float64(dr), np.float64(dc)) * res
        e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
        emin = min(e1, e2)
        i0, j0, a, b = 0, 0, 0.0, 0.0
        if use_sag:  # sag.EnvelopeTable.__call__
            si = _interp(math.log(length), log_spans, span_index)
            ri = _interp((e1 - e2) / length, ratios, ratio_index)
            i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
            a, b = si - i0, ri - j0
        clearance, nmpt, seen = np.inf, np.inf, False
        height_max, height_sum, high = -np.inf, 0.0, 0
        row = np.empty(fractions.size) if use_sag else blend
        if use_sag:
            for f in range(fractions.size):
                row[f] = ((1 - a) * (1 - b) * sag[i0, j0, f] + a * (1 - b) * sag[i0 + 1, j0, f]
                          + (1 - a) * b * sag[i0, j0 + 1, f] + a * b * sag[i0 + 1, j0 + 1, f])
        for i in range(1, steps):
            t = i / steps
            r = r1 + int(np.rint(dr * t))
            c = c1 + int(np.rint(dc * t))
            if use_sag:
                limit = e1 + (e2 - e1) * t - _interp(t, fractions, row) - fall_zone
            else:
                limit = emin - sh.SLOPE * min(t, 1 - t) * length - sh.LEASH_FALL
            margin = limit - np.float64(z[r, c])
            if margin != margin or clearance != clearance:
                clearance = np.nan  # np.min: no data anywhere makes the line fail
            elif margin < clearance:
                clearance = margin
            height = margin + fall  # helpers.webbing_height
            if height != height or height > height_max:  # np.max: NaN stays
                height_max = height
            height_sum += height
            if height >= high_above:
                high += 1
            if has_s:
                over = limit - np.float64(s[r, c])
                if over == over:  # np.nanmin
                    seen = True
                    if over < nmpt:
                        nmpt = over
        out[k, 0], out[k, 1], out[k, 2], out[k, 3] = e1, e2, length, clearance
        out[k, 4] = nmpt if seen else np.nan
        out[k, 5] = 1.0
        out[k, 6], out[k, 7] = height_max, height_sum / (steps - 1)
        out[k, 8] = 100.0 * high / (steps - 1)


def evaluate_lines(found: np.ndarray, anchors: np.ndarray, elevation: np.ndarray, res: float,
                   surface: Optional[np.ndarray], sag_table, nmpt_mode: Optional[str],
                   high_above: float = sh.HIGH_ABOVE, limits: Optional[sh.LineLimits] = None,
                   down: Optional[np.ndarray] = None, anchor_values: Optional[np.ndarray] = None
                   ) -> sh.LineTable:
    """The lines among the pairs found (indices into anchors) that pass helpers.evaluate_line
    and helpers.is_valid: the same decision and values, computed in parallel. With limits,
    only the lines that reach them (sh.LineLimits.passes). down: helpers.downslope of the
    anchors (computed here when not given); anchor_values: [prominence, drop] of every
    anchor (terrain.py; NaN when not given)."""
    if down is None:
        down = sh.downslope(elevation, anchors, res)
    if anchor_values is None:
        anchor_values = np.full((len(anchors), 2), np.nan)
    anchor_values = np.asarray(anchor_values, dtype=np.float64)
    found = np.asarray(found, dtype=np.int64).reshape(-1, 2)
    angles = sh.wall_angles(anchors[found[:, 0]], anchors[found[:, 1]], down[found[:, 0]], down[found[:, 1]])
    out = np.zeros((len(found), 9))
    if len(found):
        if sag_table is None:
            log_spans = span_index = ratios = ratio_index = fractions = np.zeros(2)
            sag, fall_zone = np.zeros((2, 2, 2)), 0.0
        else:
            log_spans = np.log(sag_table.spans)  # as in EnvelopeTable.__call__
            span_index = np.arange(len(sag_table.spans)).astype(np.float64)
            ratios = sag_table.RATIOS.astype(np.float64)
            ratio_index = np.arange(len(ratios)).astype(np.float64)
            sag, fractions = np.ascontiguousarray(sag_table.sag), sag_table.fractions.astype(np.float64)
            fall_zone = float(sag_table.rig.fall_zone)
        z = np.asarray(elevation)
        s = np.asarray(surface) if surface is not None else np.zeros((1, 1), dtype=z.dtype)
        _evaluate(z, s, surface is not None, np.ascontiguousarray(anchors, dtype=np.int64),
                  np.ascontiguousarray(found, dtype=np.int64), float(res), sag_table is not None, log_spans,
                  span_index, ratios, ratio_index, sag, fractions, fall_zone, float(high_above), out)
    # helpers.is_valid of every result, then the limits
    clearance, nmpt = out[:, 3], out[:, 4]
    keep = (out[:, 5] != 0) & (clearance > 0)
    if nmpt_mode == "reject":
        keep &= ~(nmpt <= 0)  # NaN: not measured, kept
    if limits is not None:
        keep = limits.passes(out[:, 6], out[:, 7], out[:, 8], angles[0], angles[1], keep)
    found, out = found[keep], out[keep]
    first, second = anchor_values[found[:, 0]], anchor_values[found[:, 1]]
    columns = {"a1": np.asarray(anchors, dtype=np.int64)[found[:, 0]],
               "a2": np.asarray(anchors, dtype=np.int64)[found[:, 1]]}
    for name, value in zip(sh.LINE_VALUES, (out[:, 2], out[:, 0], out[:, 1], out[:, 3], out[:, 4], out[:, 6],
                                            out[:, 7], out[:, 8], angles[0][keep], angles[1][keep], first[:, 0],
                                            second[:, 0], first[:, 1], second[:, 1])):
        columns[name] = np.ascontiguousarray(value, dtype=np.float64)
    return sh.LineTable(columns)


@njit(parallel=True, cache=True)
def _covered_pixels(a1, a2, mask, out):
    """Pixels of each line (anchors excluded, the pixels of helpers.line_profile) that are set in mask."""
    for k in prange(a1.shape[0]):
        r1, c1, r2, c2 = a1[k, 0], a1[k, 1], a2[k, 0], a2[k, 1]
        dr, dc = r2 - r1, c2 - c1
        steps = max(abs(dr), abs(dc))
        n = 0
        for i in range(1, steps):
            t = i / steps
            if mask[r1 + int(np.rint(dr * t)), c1 + int(np.rint(dc * t))]:
                n += 1
        out[k] = n


def covered_metres(a1: np.ndarray, a2: np.ndarray, res: float, mask: Optional[np.ndarray]) -> List[float]:
    """Metres of each line over the pixels of a mask (water, filled gaps): the values of
    helpers.line_profile ("water_m", "filled_m") without the rest of the profile."""
    if mask is None or len(a1) == 0:
        return [0.0] * len(a1)
    a1, a2 = np.ascontiguousarray(a1, dtype=np.int64), np.ascontiguousarray(a2, dtype=np.int64)
    counts = np.zeros(len(a1), dtype=np.int64)
    _covered_pixels(a1, a2, np.ascontiguousarray(mask, dtype=np.bool_), counts)
    d = a2 - a1
    steps = np.maximum(np.abs(d[:, 0]), np.abs(d[:, 1]))
    lengths = np.hypot(d[:, 0], d[:, 1]) * res
    return [round(float(n) * length / s, 1) if n else 0.0
            for n, length, s in zip(counts.tolist(), lengths.tolist(), steps.tolist())]


def find_valid_lines(elevation: np.ndarray, surface: Optional[np.ndarray], anchors: np.ndarray,
                     res: float, min_length: float, max_length: float,
                     nmpt_mode: Optional[str] = None, threads: Optional[int] = None,
                     sag_table=None, max_dh_ratio: float = np.inf,
                     max_dh: float = np.inf, first: Optional[np.ndarray] = None,
                     high_above: float = sh.HIGH_ABOVE, limits: Optional[sh.LineLimits] = None,
                     anchor_values: Optional[np.ndarray] = None, strong: Optional[np.ndarray] = None,
                     stats: Optional[Dict[str, int]] = None) -> sh.LineTable:
    """Finds valid lines between anchors.

    Args:
        elevation: NMT elevation grid
        surface: NMPT grid (trees, buildings), or None
        anchors: [row, col] anchor coordinates
        res: Pixel size in metres
        min_length, max_length: Line length limits in metres
        nmpt_mode: None, "mark" or "reject"
        threads: Number of threads (defaults to CPU count - 1)
        sag_table: sag.EnvelopeTable to use the sag estimator instead of the formula
        max_dh_ratio, max_dh: The anchors may differ in elevation by at most
            max_dh_ratio of the line length, and never more than max_dh
        first: Optional mask of the anchors whose lines are wanted when they are the
            first anchor (smaller x, then y): the anchors in the core of a tile
        high_above: Height above the terrain from which a pixel of a line counts as high
        limits: Optional limits of the heights above the terrain and the wall angle; lines
            that do not reach them are left out (counted in limits.left_out)
        anchor_values: [prominence, drop] of every anchor (terrain.py), saved with the lines
        strong: Optional mask of the anchors one of which every line must have (--min-prominence)
        stats: Optional dict the counts of this call are added to (the funnel of the line search,
            jobs.FUNNEL_STEPS): anchors with an open direction, those pairs start from, candidate
            pairs, pairs checked pixel by pixel, pairs found, valid lines, lines left out by limits

    Returns:
        Valid lines, longest first
    """
    numba.set_num_threads(max(1, min(threads or numba.config.NUMBA_NUM_THREADS - 1,
                                     numba.config.NUMBA_NUM_THREADS)))
    start_time = time.time()
    z = np.asarray(elevation)
    anchors = np.ascontiguousarray(anchors, dtype=np.int64)
    elev = np.asarray(z[anchors[:, 0], anchors[:, 1]])

    if sag_table is None:
        use_sag, log_spans, ratios, table, fall_zone = False, np.zeros(2), np.zeros(2), np.zeros((2, 2, 2)), 0.0
        gain, cap, offset = -sh.SLOPE, np.inf, sh.LEASH_FALL
    else:
        use_sag = True
        log_spans, ratios = np.log(sag_table.spans), sag_table.RATIOS.astype(np.float64)
        table, fall_zone = np.ascontiguousarray(sag_table.sag), sag_table.rig.fall_zone
        # chord rises by at most the allowed height difference; the sag is never negative
        gain, cap = max_dh_ratio * math.sqrt(2), max_dh
        offset = fall_zone + min(0.0, float(table.min()))

    # Step 1: open directions of every anchor
    progress.compute.start("free directions", 1, unit="step")
    useful, rings, slot = free_directions(z, anchors, res, gain, cap, offset, min_length, max_length)
    progress.compute.finish()
    print(f"Anchors with an open direction: {len(useful)} of {len(anchors)}")

    # Step 2 + 3: bucket the useful anchors, then find and check the pairs
    down = sh.downslope(z, anchors, res)
    max_angle = limits.max_wall_angle if limits is not None and limits.max_wall_angle is not None else 180.0
    cos_limit = -2.0 if max_angle >= 180 else math.cos(math.radians(max_angle))
    todo_all, args, tail = pair_arguments(z, anchors, elev, useful, rings, slot, first, res, min_length, max_length,
                                          max_dh_ratio, max_dh, down, cos_limit, strong, use_sag, log_spans,
                                          ratios, table, fall_zone)
    pairs, candidates, checked = [], 0, 0
    progress.compute.start("anchor pairs", len(todo_all), unit="anchor")
    for todo in np.array_split(todo_all, min(CHUNKS, max(1, len(todo_all)))):
        counts, out = pair_chunk(args, todo, tail)
        pairs.append(out)
        candidates += int(counts[:, 0].sum())
        checked += int(counts[:, 1].sum())
        progress.compute.update(len(todo), pairs=f"{checked:,}", lines=sum(len(p) for p in pairs))
    progress.compute.finish()

    # Final decision and clearances, exactly as in the pixel-by-pixel search (evaluate_line)
    found = np.concatenate(pairs) if pairs else np.zeros((0, 2), dtype=np.int64)
    parts, valid = [], 0
    progress.compute.start("checking lines", len(found), unit="line")
    for part in np.array_split(found, max(1, min(CHUNKS, len(found) // 10000))):
        parts.append(evaluate_lines(part, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above,
                                    limits, down, anchor_values))
        valid += len(parts[-1])
        progress.compute.update(len(part), valid=valid)
    valid_lines = sh.LineTable.concat(parts)
    progress.compute.finish(f"{len(valid_lines)} valid")
    print(f"\n{'=' * 60}")
    print(f"Completed in {time.time() - start_time:.2f} seconds")
    print(f"Candidate pairs between anchors with an open direction: {candidates}")
    print(f"Checked pixel by pixel: {checked}")
    if limits is not None and limits.active:
        print(f"Left out by the line limits ({limits.describe()}): {limits.left_out}")
    print(f"Found {len(valid_lines)} valid lines")
    print(f"{'=' * 60}")
    if stats is not None:
        for key, n in (("open", len(useful)), ("todo", len(todo_all)), ("candidates", candidates),
                       ("checked", checked), ("found", len(found)), ("valid", len(valid_lines)),
                       ("left_out", limits.left_out if limits is not None else 0)):
            stats[key] = stats.get(key, 0) + int(n)

    # Longest first; lines of the same length keep their order (as sorted(reverse=True) did)
    return valid_lines.take(np.argsort(-valid_lines.columns["length"], kind="stable"))
