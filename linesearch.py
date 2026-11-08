"""
Fast search for valid lines between anchors (numba).

Three steps, none of which loses a valid line:
1. Free rings. For every anchor and each of SECTORS directions: how many rings of
   pixels around the anchor a line in that direction can cross before the terrain
   is certainly too high, using the weakest limit possible for any partner. Anchors
   with no open direction are dropped.
2. Pairs. Partners are found on a grid of buckets and must pass the length and
   height-difference limits, and both anchors must be open towards each other. Buckets
   that hold no partner to keep (lower indices, beyond the longest line, beyond what the
   anchor's rings can reach, outside its open sectors or with no partner open towards it)
   are skipped whole.
3. Exact check. The pixels of the line are checked from both anchors inwards and
   the check stops at the first pixel that is too high (most lines fail next to an
   anchor); lines of 130 to 1024 pixels test their middle in bit-reversal order after
   two pixels at each end (long lines over a valley or a bay fail in the middle too).
The kernels keep pairs within EPS of the limit; the pairs found are evaluated
once more by helpers.evaluate_line, which makes the final decision and gives the
clearances, so the results are exactly those of the plain pixel-by-pixel search.

The end zone and the lift (helpers.end_zone_rule; off by default) enter every step
only in the comparison with the limit, never in its arithmetic: a pixel passes when
its strict margin exceeds -lift - delta in the end zone and -lift outside it. The rings
take an offset per ring (ring_offsets: the zone uncapped, the sound side), _line_ok
tests the first strict step at each end first when a zone is set, and the evaluation
gives the rule's decision values as the clearances (and, with a ladder of zones, the
bucket minima of the strict margins: helpers.valid_at).
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Union

import numba
import numpy as np
from numba import njit, prange

import helpers as sh
import runs as rn
from progress import progress

SECTORS = 64   # direction sectors per anchor
HALF = SECTORS // 2  # the opposite sector is s + HALF
RINGS = 64     # rings of pixels around an anchor checked per sector
EPS = 1e-6     # metres; borderline pairs are passed on to evaluate_line
CHUNKS = 200   # anchors are processed in this many parts (progress updates)
RING_CHUNK = 1 << 16  # anchors per call of _free_rings (only the rows of the open ones are kept)
# _line_ok tests the middle of lines of more than LINE_ORDER_SPLIT and at most LINE_ORDER_MAX steps
# in bit-reversal order (longer ones lose more to the jumps along the line than they gain)
LINE_ORDER_SPLIT = 2 * RINGS + 1   # the rings screen about RINGS pixels at each end
LINE_ORDER_MAX = 1024
# pair_chunk: the pairs found by an anchor are held in a buffer of PAIR_BUFFER pairs per anchor of a
# chunk (99.96 % of the anchors with lines on the searches measured), at most PAIR_BUFFER_BYTES a chunk
PAIR_BUFFER = 1024
PAIR_BUFFER_BYTES = 16 << 20
# The pairs found are evaluated in parts of at least EVAL_PART pairs (and of at least 1/CHUNKS of
# them): the chunks' arrays as they are, small ones joined, large ones cut
EVAL_PART = 10_000
COVERED_PART = 1 << 16  # lines per part of covered_metres and covered_pixels
# find_valid_lines(sink=): the anchors go through pair_chunk in slices of SINK_CHUNK, and the pairs
# found are evaluated once EVAL_PART are pending, in parts of at most SINK_PART pairs, each handed
# to the sink at once (nothing is kept). A slice's buffer holds SINK_PAIR_BUFFER pairs per anchor
# (SINK_CHUNK of them fit SINK_PAIR_BUFFER_BYTES): more than any anchor of Slovakia's heaviest
# tiles found (6169 in M2's Tatras tile, 7887 in L's), whose anchors over PAIR_BUFFER held 76 % of
# their pairs and made the writing pass repeat 75-77 % of their pixel tests (13-14 % of the tile)
SINK_CHUNK = 2048
SINK_PART = 1 << 20
SINK_PAIR_BUFFER = 8192
SINK_PAIR_BUFFER_BYTES = 128 << 20
# evaluate_lines works out the values around its kernel (wall angles, which lines pass, the columns of the
# table) in blocks of at least VALUE_BLOCK pairs, VALUE_BLOCKS per thread numba may use, on a thread pool:
# numpy on one thread took 189 of the 1012 s of M2's heaviest tile and 151 of L's 729 (round 5, C4)
VALUE_BLOCK = 1 << 16
VALUE_BLOCKS = 2
# LazyAnchorValues: the values of the anchors of a part's lines are computed for that part this many
# times; the next part with an anchor not known yet has every useful anchor computed that a line of it or
# of a later part can still have (the rows from its first anchors' less the longest line on). A tile with
# lines in at most this many parts computes its lines' anchors only (most tiles with lines: a few lines,
# a few thousand anchors of a million); one with lines in many parts pays about one computation of all of
# them (the windows of a part's anchors overlap the next part's, so a computation per part would take
# several times that)
SUBSET_CALLS = 4


class LazyAnchorValues:
    """anchor_values of find_valid_lines computed when lines first need them, for the anchors of those
    lines (the count mode: most anchors of a tile never get a line). compute(indices) gives
    [prominence, drop] of anchors[indices] (indices increasing; a (k, 2) array), which must be the
    values these anchors have among all of them (terrain.prominence and terrain.drop of a subset).
    Called with the pairs of the passing lines (evaluate_lines), it computes the anchors among them
    not known yet, each anchor once, and returns the values of every anchor (NaN where not computed);
    after `calls` computations the next takes every anchor of `rest` not known yet whose row (`rows`)
    is at least floor() (find_valid_lines sets the useful anchors, the only ones a line can have, and
    their rows; _sink_lines the smallest row a line of the pairs evaluated from now on can reach).
    after: called after each computation (_sink_lines puts the bar of the pairs back). Held from the
    first line on: the values (16 bytes an anchor, as the array of before) and whether each is known
    (1 byte)."""

    def __init__(self, compute: Callable[[np.ndarray], np.ndarray], count: int, calls: Optional[int] = None):
        self.compute, self.count = compute, count
        self.calls = SUBSET_CALLS if calls is None else calls
        self.values: Optional[np.ndarray] = None
        self.known: Optional[np.ndarray] = None
        self.rest: Optional[np.ndarray] = None
        self.rows: Optional[np.ndarray] = None
        self.floor: Optional[Callable[[], int]] = None
        self.reach = 0  # rows a line's second anchor may lie above its first (find_valid_lines)
        self.after: Optional[Callable[[], None]] = None
        self.computed = 0  # computations so far

    def __call__(self, found: np.ndarray) -> np.ndarray:
        if self.values is None:  # the first line (most tiles have none)
            self.values = np.full((self.count, 2), np.nan)
            self.known = np.zeros(self.count, dtype=bool)
        need = np.unique(np.asarray(found, dtype=np.int64))
        need = need[~self.known[need]]
        if len(need):
            if self.computed >= self.calls and self.rest is not None:
                rest = np.asarray(self.rest, dtype=np.int64)
                rest = rest[~self.known[rest]]
                if self.floor is not None and self.rows is not None:
                    rest = rest[self.rows[rest] >= self.floor()]
                need = np.union1d(need, rest)
            values = np.asarray(self.compute(need), dtype=np.float64).reshape(len(need), 2)
            self.values[need] = values
            self.known[need] = True
            self.computed += 1
            if self.after is not None:
                self.after()
        return self.values


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
def _zone_steps(steps, length, end_zone, zone_cap):
    """helpers.zone_steps in numba, operation for operation (tests/test_end_zone.py compares them)."""
    d = min(end_zone, zone_cap * length)
    if not d > 0.0:
        return 0
    return int(math.ceil(d * steps / length))


@njit(cache=True)
def _margin_at(z, r1, c1, dr, dc, k, steps, length, e1, e2, emin, use_sag, i0, j0, a, b, table, points, fall_zone):
    """The margin limit - z of step k of a line as _line_ok computes it (the same float operations)."""
    t = k / steps
    r = r1 + int(np.rint(dr * t))
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
    return limit - np.float64(z[r, c])


@njit(cache=True)
def _line_ok(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone, end_zone, lift, delta, zone_cap):
    """Whether the terrain stays below the maximum safe elevation along the line.

    The same limit as helpers.max_safe_elevation (formula or sag table), within EPS. The
    pixels are tested from both ends inwards (most lines fail next to an anchor); lines of
    more than LINE_ORDER_SPLIT and at most LINE_ORDER_MAX steps test two pixels at each
    end first, then the others in bit-reversal order (a long line over a valley or a bay
    fails in its middle often). Every pixel is tested (the middle one of the ends-inward
    order twice), so the order changes only how soon a failing line is noticed.

    With an end zone or a lift (helpers.end_zone_rule) a pixel passes when its margin exceeds
    -EPS - lift - delta in the zone (_zone_steps), -EPS - lift outside it; with a zone the
    first step beyond it at each end is tested first (in the zone most lines pass, beyond it
    many fail). At end_zone 0 and lift 0 every comparison is the one of before (-EPS).
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
    kz = _zone_steps(steps, length, end_zone, zone_cap)
    strict, lenient = -EPS - lift - 0.0, -EPS - lift - delta
    if 0 < kz < steps:  # the first strict step at each end first
        for k in (kz, steps - kz):
            if k < kz or steps - k < kz:
                continue  # in the zone from the other end (a short line)
            m = _margin_at(z, r1, c1, dr, dc, k, steps, length, e1, e2, emin, use_sag, i0, j0, a, b, table, points,
                           fall_zone)
            if not (m > strict):
                return False
    rounds = 2 if LINE_ORDER_SPLIT < steps <= LINE_ORDER_MAX else steps
    lo, hi = 1, steps - 1
    while lo <= hi and lo <= rounds:
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
            bound = lenient if (k < kz or steps - k < kz) else strict
            if not (limit - np.float64(z[r, c]) > bound):  # NaN (no data) fails too
                return False
        lo += 1
        hi -= 1
    if lo > hi:
        return True
    # the pixels lo .. hi: the bit reversal of 0 .. 2^bits - 1 (bits: those of steps - 1)
    bits = 0
    while (steps - 1) >> bits:
        bits += 1
    top = 1 << (bits - 1)
    rev = 0
    for _ in range(1 << bits):
        k = rev
        bit = top  # the next number in bit-reversed counting
        while rev & bit:
            rev ^= bit
            bit >>= 1
        rev |= bit
        if lo <= k <= hi:
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
            bound = lenient if (k < kz or steps - k < kz) else strict
            if not (limit - np.float64(z[r, c]) > bound):  # NaN (no data) fails too
                return False
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


def smallest_need(min_length: float, res: float) -> int:
    """The rings a pair of at least min_length needs at least (its Chebyshev length in pixels is
    at least min_length / (res * sqrt 2)): an anchor with no sector open that far starts no pair,
    and a partner with none open towards the anchor passes no rings test."""
    return min(RINGS, int(min_length / (res * math.sqrt(2))) // 2)


def largest_need(min_length: float, max_length: float, res: float) -> int:
    """The rings a pair can need at most ((its Chebyshev length in pixels) // 2 for lines up to
    max_length, with a pixel to spare), at least the need of the shortest line: _free_rings
    stops there, which changes no decision of find_valid_lines."""
    return min(RINGS, max(smallest_need(min_length, res), (int(max_length / res) + 1) // 2))


def ring_offsets(offset: float, res: float, kmax: int, end_zone: float = 0.0, lift: float = 0.0,
                 delta: float = 0.0) -> np.ndarray:
    """The offset of each ring of _free_rings (index k = 1 .. kmax; offsets[0] = offset, unused):
    offset - lift - delta * [(k - 1) * res < end_zone]. The rings do not know a line's length, so
    the zone is end_zone uncapped (the sound side: step k of a line lies at least k * res from its
    anchor, so a step in the zone from the nearer anchor has k * res < end_zone; the rings a pair
    needs, up to half its steps, are never in the zone from the other anchor only). At lift 0 and
    end_zone 0 every value is offset itself."""
    return np.array([offset] + [offset - lift - (delta if (k - 1) * res < end_zone else 0.0)
                                for k in range(1, kmax + 1)], dtype=np.float64)


@njit(parallel=True, cache=True)
def _free_rings(z, anchors, res, gain, cap, offsets, kmax, masks):
    """For every anchor and sector: the number of rings a line can cross from the anchor, up
    to kmax (the largest need of a pair: larger values would change no decision; uint8).

    The k-th pixel of a line (DDA) lies on ring k (Chebyshev distance k) and at most
    half a pixel from the exact line, so its direction differs from the line's by at
    most asin(0.71 / k). A sector stays open at ring k if some pixel that may belong
    to a line in it is below e + min(gain * k * res, cap) - offsets[k], where e is the
    elevation of the anchor: no limit for any partner is weaker than that (ring_offsets).
    The sectors a pixel may belong to are its bits in masks (_sector_masks); a pixel none of
    whose sectors is open any more is not read.
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
            limit = e + min(gain * k * res, cap) - offsets[k] + EPS
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
                    min_length: float, max_length: float, end_zone: float = 0.0, lift: float = 0.0,
                    delta: float = 0.0):
    """Step 1: the anchors with an open direction (useful: those with a sector open up to the
    need of the shortest line), their rings (_free_rings, one uint8 row each, in the order of
    useful) and the row of every anchor (slot, int32; -1 for the others). _free_rings runs on
    RING_CHUNK anchors at a time, so the rings of the anchors without an open direction (most
    of them) are never held all at once. end_zone, lift, delta: the rule (ring_offsets)."""
    kmax, masks = largest_need(min_length, max_length, res), sector_masks()
    need_min = smallest_need(min_length, res)
    offsets = ring_offsets(float(offset), float(res), kmax, float(end_zone), float(lift), float(delta))
    useful, rows = [], []
    for start in range(0, len(anchors), RING_CHUNK):
        rings = _free_rings(z, anchors[start:start + RING_CHUNK], res, gain, cap, offsets, kmax, masks)
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


@njit(cache=True)
def _arc(r0, r1, c0, c1):
    """The angles from the origin of the corners of the box rows r0..r1, columns c0..c1 (the
    origin outside it, so they span less than pi): (lowest, highest), unwrapped."""
    a0 = math.atan2(r0, c0)
    lo, hi = 0.0, 0.0
    for n in range(3):
        dr = r0 if n == 0 else r1
        dc = c0 if n == 1 else c1
        d = math.atan2(dr, dc) - a0
        if d > np.pi:
            d -= 2 * np.pi
        elif d <= -np.pi:
            d += 2 * np.pi
        lo, hi = min(lo, d), max(hi, d)
    return a0 + lo, a0 + hi


@njit(cache=True)
def _cell_sectors(r0, r1, c0, c1):
    """The sectors (_sector) of the lines from the origin to the pixels of the box rows r0..r1,
    columns c0..c1 (the origin outside it): s_lo .. s_hi, unwrapped (take them modulo SECTORS),
    with one sector of margin at each end for the rounding of atan2."""
    alo, ahi = _arc(r0, r1, c0, c1)
    width = 2 * np.pi / SECTORS
    return int(math.floor(alo / width)) - 1, int(math.floor(ahi / width)) + 1


@njit(cache=True)
def _open_masks(rows, need):
    """Per row of rings: its sectors open for at least need rings as the bits of a uint64."""
    masks = np.zeros(rows.shape[0], dtype=np.uint64)
    one = np.uint64(1)
    for j in range(rows.shape[0]):
        m = np.uint64(0)
        for s in range(SECTORS):
            if rows[j, s] >= need:
                m |= one << np.uint64(s)
        masks[j] = m
    return masks


@njit(cache=True)
def _cell_open(rows, need, order, starts, slot):
    """Per cell of the pair search: the OR of the sectors open for at least need rings of its
    anchors (bit s: sector s; rows: the rings of free_directions, slot their row)."""
    cells = starts.size
    masks = np.zeros(cells, dtype=np.uint64)
    one = np.uint64(1)
    for g in range(cells):
        end = starts[g + 1] if g + 1 < cells else order.size
        m = np.uint64(0)
        for p in range(starts[g], end):
            row = slot[order[p]]
            for s in range(SECTORS):
                if rows[row, s] >= need:
                    m |= one << np.uint64(s)
        masks[g] = m
    return masks


@njit(parallel=True, cache=True)
def _pairs(z, anchors, elev, rings, slot, rmax, todo, order, starts, cell_open, open_mask, cell, cells_x, res,
           min_length, max_length, max_dh_ratio, max_dh, d0, far2, kmax, down, cos_limit, strong,
           use_sag, log_spans, ratios, table, fall_zone, first_only, end_zone, lift, delta, zone_cap,
           offsets, out, buf, counts):
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
    largest need of a pair): their need exceeds R; and (F8c) cells none of whose sectors from
    the anchor (_cell_sectors) is open for the need of the cell's nearest pixel, cells no
    anchor of which has a sector open for the need of the shortest line (cell_open, _cell_open)
    towards the anchor, partners whose need exceeds the anchor's largest ring in the sectors
    of their cell, and partners none of whose sectors towards their cell's sectors is open for
    the need of the shortest line (open_mask, _open_masks). Those fail the rings' test, which
    comes after the candidates are counted, so they are not counted as candidates.

    end_zone, lift, delta, zone_cap: the rule of _line_ok (helpers.end_zone_rule).

    counts[q] = [candidate pairs, pairs checked, lines] for todo[q]. With offsets None, the
    first buf.shape[1] pairs of todo[q] are written to buf[q] (the count goes on past them);
    otherwise all of them to out from offsets[q] on.
    """
    keep = buf.shape[1]
    reach = int(max_length / res) // cell + 1
    cells_y = starts.size // cells_x
    zero, one = np.uint64(0), np.uint64(1)
    for q in prange(todo.size):
        i = todo[q]
        ri, ci = anchors[i, 0], anchors[i, 1]
        cy, cx = ri // cell, ci // cell
        ei = elev[i]
        slot_i = slot[i]
        ri_max = rmax[slot_i]
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
                # F8c: the anchor's rings in the sectors towards the cell, and the cell's open
                # sectors towards the anchor (the anchor's own cell is never skipped)
                x0 = gx * cell
                dx = max(0, max(x0 - ci, ci - (x0 + cell - 1)))
                own_max, m = kmax, ~zero
                if dy > 0 or dx > 0:
                    s_lo, s_hi = _cell_sectors(y0 - ri, y0 + cell - 1 - ri, x0 - ci, x0 + cell - 1 - ci)
                    own_max = 0
                    for s in range(s_lo, s_hi + 1):
                        own_max = max(own_max, np.int64(rings[slot_i, s % SECTORS]))
                    if own_max < min(RINGS, max(dy, dx) // 2):
                        continue
                    m = zero
                    for s in range(s_lo + HALF, s_hi + HALF + 1):
                        m |= one << np.uint64(s % SECTORS)
                    if (cell_open[g] & m) == zero:
                        continue
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
                    if cheb > span or own_max < min(RINGS, cheb // 2):
                        continue
                    slot_j = slot[j]
                    rj_max = rmax[slot_j]
                    if rj_max < kmax and cheb > 2 * np.int64(rj_max) + 1:
                        continue
                    if (open_mask[slot_j] & m) == zero:
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
                                use_sag, log_spans, ratios, table, fall_zone, end_zone, lift, delta, zone_cap):
                        if offsets is not None:
                            out[offsets[q] + found, 0] = a
                            out[offsets[q] + found, 1] = b
                        elif found < keep:
                            buf[q, found, 0] = a
                            buf[q, found, 1] = b
                        found += 1
        counts[q, 0], counts[q, 1], counts[q, 2] = candidates, checked, found


def pair_arguments(z: np.ndarray, anchors: np.ndarray, elev: np.ndarray, useful: np.ndarray, rings: np.ndarray,
                   slot: np.ndarray, first: Optional[np.ndarray], res: float, min_length: float, max_length: float,
                   max_dh_ratio: float, max_dh: float, down: np.ndarray, cos_limit: float,
                   strong: Optional[np.ndarray], use_sag: bool, log_spans, ratios, table, fall_zone: float,
                   end_zone: float = 0.0, lift: float = 0.0, delta: float = 0.0, zone_cap: float = sh.ZONE_CAP):
    """The anchors pairs are searched from (the useful ones; with first, those of a tile's
    core) and _pairs' arguments before and after todo, with the useful anchors (the only
    partners) bucketed into cells of a quarter of max_length and the open sectors of every
    cell and of every useful anchor (_cell_open, _open_masks: for F8c). useful, rings, slot:
    those of free_directions; end_zone, lift, delta, zone_cap: the rule (at the tail's end)."""
    todo_all = useful if first is None else useful[np.asarray(first)[useful]]
    cell = max(1, int(max_length / res) // 4)
    cells_x = z.shape[1] // cell + 1
    cells_y = z.shape[0] // cell + 1
    keys = (anchors[useful, 0] // cell) * cells_x + anchors[useful, 1] // cell
    order = useful[np.argsort(keys, kind="stable")]
    starts = np.searchsorted(np.sort(keys), np.arange(cells_y * cells_x)).astype(np.int64)
    rmax = rings.max(axis=1).astype(np.uint8) if len(rings) else np.zeros(0, dtype=np.uint8)
    need_min = smallest_need(min_length, res)
    cell_open, open_mask = _cell_open(rings, need_min, order, starts, slot), _open_masks(rings, need_min)
    kmax = largest_need(min_length, max_length, res)
    d0 = min(float(max_dh_ratio) * float(max_length), float(max_dh))
    far2 = int(math.floor((max_length / res + 2) ** 2))
    head = (z, anchors, elev, rings, slot, rmax)
    tail = (order, starts, cell_open, open_mask, cell, cells_x, res, float(min_length), float(max_length),
            float(max_dh_ratio), float(max_dh), d0, far2, kmax, down, cos_limit,
            np.ones(len(anchors), dtype=np.bool_) if strong is None else np.asarray(strong, dtype=np.bool_),
            use_sag, log_spans, ratios, table, float(fall_zone), first is not None,
            float(end_zone), float(lift), float(delta), float(zone_cap))
    return todo_all, head, tail


@njit(cache=True)
def _copy_buffered(buf, found, offsets, out):
    """The pairs of the anchors whose pairs all fit into buf (found[q] <= buf.shape[1]) to out
    from offsets[q] on (on one thread: a few thousand pairs a chunk, less than starting threads)."""
    keep = buf.shape[1]
    for q in range(found.size):
        if found[q] <= keep:
            for k in range(found[q]):
                out[offsets[q] + k, 0] = buf[q, k, 0]
                out[offsets[q] + k, 1] = buf[q, k, 1]


def pair_chunk(args: tuple, todo: np.ndarray, tail: tuple, buffer: Optional[int] = None,
               per_anchor: Optional[int] = None, max_bytes: Optional[int] = None):
    """The pairs of the anchors in todo (_pairs' arguments before and after todo), in the order
    of todo: one pass over all of them holding the first pairs of each anchor in a buffer
    (buffer pairs per anchor; by default per_anchor (PAIR_BUFFER), fewer when the buffer would
    exceed max_bytes (PAIR_BUFFER_BYTES); the count mode passes SINK_PAIR_BUFFER and
    SINK_PAIR_BUFFER_BYTES), then a writing pass over the anchors that found more only. Either
    pass writes an anchor's pairs in the order of its visits, so the size of the buffer changes
    neither the pairs nor their order. Returns the counts and the pairs."""
    n = len(todo)
    index = np.int32 if len(args[1]) <= np.iinfo(np.int32).max else np.int64  # 8 B a pair
    per_anchor = PAIR_BUFFER if per_anchor is None else per_anchor
    max_bytes = PAIR_BUFFER_BYTES if max_bytes is None else max_bytes
    keep = buffer or max(1, min(per_anchor, max_bytes // (2 * np.dtype(index).itemsize * max(1, n))))
    buf = np.empty((n, keep, 2), dtype=index)
    counts = np.zeros((n, 3), dtype=np.int64)
    _pairs(*args, todo, *tail, None, np.zeros((0, 2), dtype=np.int64), buf, counts)
    found = counts[:, 2]
    offsets = (np.cumsum(found) - found).astype(np.int64)
    out = np.empty((int(found.sum()), 2), dtype=np.int64)
    if len(out):
        _copy_buffered(buf, found, offsets, out)
    more = np.flatnonzero(found > keep)
    if len(more):
        _pairs(*args, np.ascontiguousarray(todo[more]), *tail, np.ascontiguousarray(offsets[more]), out,
               np.zeros((0, 0, 2), dtype=index), np.zeros((len(more), 3), dtype=np.int64))
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


@njit(cache=True)
def _interp_forward(x, xp, fp, j):
    """_interp of x when x is not below the x of the call before on the same xp: j is the index
    that call returned (0 at the first). The same result to the last bit; the index (the last
    xp[j] <= x, searchsorted's) is found by walking forward from j instead of a binary search.
    Returns (value, index)."""
    n = xp.size
    if x != x:
        return x, j
    if x < xp[0]:
        return fp[0], j
    if x > xp[n - 1]:
        return fp[n - 1], j
    while j < n - 1 and xp[j + 1] <= x:
        j += 1
    if j == n - 1 or xp[j] == x:
        return fp[j], j
    slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j])
    result = slope * (x - xp[j]) + fp[j]
    if result != result:
        result = slope * (x - xp[j + 1]) + fp[j + 1]
        if result != result and fp[j] == fp[j + 1]:
            result = fp[j]
    return result, j


@njit(parallel=True, cache=True)
def _evaluate(z, s, has_s, anchors, found, res, use_sag, log_spans, span_index, ratios, ratio_index,
              sag, fractions, fall_zone, high_above, end_zone, lift, delta, zone_cap, zones, out, zone_kz,
              margins, margins_s):
    """helpers.evaluate_line for many lines, with the same arithmetic (identical results).

    out[k]: elev_a1, elev_a2, length, clearance, clearance over the surface (NaN: none),
    1 when the line has pixels between its anchors, then the largest and mean height of
    the webbing above the terrain and the % of pixels at least high_above. The clearances
    are the decision values of the end zone and the lift (helpers.decision_values; the
    margins at 0 / 0). With zones (the ladder, ascending from 0; empty: none) margins[k, j]
    (margins_s[k, j] with a surface) is the smallest strict margin of the steps of bucket j
    (helpers.zone_columns; np.min, np.nanmin for the surface; +inf when empty); zone_kz
    (lines x zones) is scratch for the zones' kz.
    """
    blend = np.empty(fractions.size)
    fall = fall_zone if use_sag else sh.LEASH_FALL  # helpers.fall_allowance
    nz = zones.size
    c_zone = lift + delta
    for k in prange(found.shape[0]):
        r1, c1 = anchors[found[k, 0], 0], anchors[found[k, 0], 1]
        r2, c2 = anchors[found[k, 1], 0], anchors[found[k, 1], 1]
        dr, dc = r2 - r1, c2 - c1
        steps = max(abs(dr), abs(dc))
        out[k, 5] = 0.0
        for j in range(nz):
            margins[k, j] = np.inf
            if has_s:
                margins_s[k, j] = np.inf
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
        at = 0  # _interp_forward's index: t only grows along the line
        if use_sag:
            for f in range(fractions.size):
                row[f] = ((1 - a) * (1 - b) * sag[i0, j0, f] + a * (1 - b) * sag[i0 + 1, j0, f]
                          + (1 - a) * b * sag[i0, j0 + 1, f] + a * b * sag[i0 + 1, j0 + 1, f])
        kz = _zone_steps(steps, length, end_zone, zone_cap)  # helpers.zone_offsets
        for j in range(nz):
            zone_kz[k, j] = _zone_steps(steps, length, zones[j], zone_cap)
        for i in range(1, steps):
            t = i / steps
            r = r1 + int(np.rint(dr * t))
            c = c1 + int(np.rint(dc * t))
            if use_sag:
                sagged, at = _interp_forward(t, fractions, row, at)
                limit = e1 + (e2 - e1) * t - sagged - fall_zone
            else:
                limit = emin - sh.SLOPE * min(t, 1 - t) * length - sh.LEASH_FALL
            margin = limit - np.float64(z[r, c])
            e = min(i, steps - i)
            offset = c_zone if e < kz else lift
            value = margin if offset == 0.0 else margin + offset  # helpers.decision_values
            if value != value or clearance != clearance:
                clearance = np.nan  # np.min: no data anywhere makes the line fail
            elif value < clearance:
                clearance = value
            height = margin + fall  # helpers.webbing_height: the lift added last, only when not 0
            if lift != 0.0:
                height = height + lift
            if height != height or height > height_max:  # np.max: NaN stays
                height_max = height
            height_sum += height
            if height >= high_above:
                high += 1
            column = nz - 1  # helpers.zone_columns
            for j in range(1, nz):
                if e < zone_kz[k, j]:
                    column = j - 1
                    break
            if nz > 0:
                if margin != margin:  # np.min of the bucket
                    margins[k, column] = np.nan
                elif margin < margins[k, column]:
                    margins[k, column] = margin
            if has_s:
                over = limit - np.float64(s[r, c])
                if over == over:  # np.nanmin
                    seen = True
                    value = over if offset == 0.0 else over + offset
                    if value < nmpt:
                        nmpt = value
                    if nz > 0 and over < margins_s[k, column]:
                        margins_s[k, column] = over
        out[k, 0], out[k, 1], out[k, 2], out[k, 3] = e1, e2, length, clearance
        out[k, 4] = nmpt if seen else np.nan
        out[k, 5] = 1.0
        out[k, 6], out[k, 7] = height_max, height_sum / (steps - 1)
        out[k, 8] = 100.0 * high / (steps - 1)


def evaluate_lines(found: np.ndarray, anchors: np.ndarray, elevation: np.ndarray, res: float,
                   surface: Optional[np.ndarray], sag_table, nmpt_mode: Optional[str],
                   high_above: float = sh.HIGH_ABOVE, limits: Optional[sh.LineLimits] = None,
                   down: Optional[np.ndarray] = None,
                   anchor_values: Union[np.ndarray, Callable[[], np.ndarray], LazyAnchorValues, None] = None,
                   end_zone: float = 0.0, lift: float = 0.0, end_clearance: float = 0.0,
                   zone_cap: float = sh.ZONE_CAP, zones=()) -> sh.LineTable:
    """The lines among the pairs found (indices into anchors) that pass helpers.evaluate_line
    and helpers.is_valid: the same decision and values, computed in parallel. With limits,
    only the lines that reach them (sh.LineLimits.passes). down: helpers.downslope of the
    anchors (computed here when not given); anchor_values: [prominence, drop] of every
    anchor (terrain.py; NaN when not given), or a callable giving them, asked only when some
    line passes, or a LazyAnchorValues, asked with the passing pairs (the values of their
    anchors computed then). end_zone, lift, end_clearance, zone_cap: the end zone and the lift
    (helpers.end_zone_rule); zones: a ladder of end zones, whose bucket minima become the
    columns "zone_margins" (lines x zones) and, with a surface, "zone_margins_nmpt"
    (helpers.valid_at); without zones the table has the columns of before."""
    delta, ladder = sh.end_zone_rule(sag_table, end_zone, lift, end_clearance, zone_cap, zones)
    if down is None:
        down = sh.downslope(elevation, anchors, res)
    found = np.asarray(found, dtype=np.int64).reshape(-1, 2)
    anchors = np.asarray(anchors, dtype=np.int64)
    blocks = _value_blocks(len(found))
    workers = min(len(blocks), max(1, numba.get_num_threads()))
    with ThreadPoolExecutor(workers) if workers > 1 else nullcontext() as pool:
        return _evaluated(found, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above, limits, down,
                          anchor_values, end_zone, lift, zone_cap, delta, ladder, blocks,
                          pool.map if pool else map)


def _value_blocks(n: int) -> List[Tuple[int, int]]:
    """The blocks of pairs (lo, hi) whose values evaluate_lines' numpy works out each on a thread of
    its pool: VALUE_BLOCKS per thread numba may use, of at least VALUE_BLOCK pairs; one block for
    fewer than two of them or one thread. Every value is an element's own (a ufunc of that row, or
    a copy), written at the row's place, so the blocks change none."""
    threads = max(1, numba.get_num_threads())
    if threads == 1 or n < 2 * VALUE_BLOCK:
        return [(0, n)]
    size = max(VALUE_BLOCK, -(-n // (VALUE_BLOCKS * threads)))
    return [(lo, min(n, lo + size)) for lo in range(0, n, size)]


def _evaluated(found, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above, limits, down, anchor_values,
               end_zone, lift, zone_cap, delta, ladder, blocks, each) -> sh.LineTable:
    """evaluate_lines' work: each(f, blocks) runs f on every block (the pool's map, or map)."""
    n = len(found)
    angles = (np.empty(n), np.empty(n))

    def wall(block):
        lo, hi = block
        f = found[lo:hi]
        angles[0][lo:hi], angles[1][lo:hi] = sh.wall_angles(anchors[f[:, 0]], anchors[f[:, 1]], down[f[:, 0]],
                                                            down[f[:, 1]])

    list(each(wall, blocks))
    out = np.zeros((len(found), 9))
    nz = len(ladder)
    margins = np.zeros((len(found), nz))
    margins_s = np.zeros((len(found), nz if surface is not None else 0))
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
                  span_index, ratios, ratio_index, sag, fractions, fall_zone, float(high_above), float(end_zone),
                  float(lift), delta, float(zone_cap), ladder, out, np.zeros((len(found), nz), dtype=np.int64),
                  margins, margins_s)
    # helpers.is_valid of every result, then the limits
    keeps = [None] * len(blocks)

    def valid(k):
        lo, hi = blocks[k]
        keep = (out[lo:hi, 5] != 0) & (out[lo:hi, 3] > 0)
        if nmpt_mode == "reject":
            keep &= ~(out[lo:hi, 4] <= 0)  # NaN: not measured, kept
        keeps[k] = keep

    list(each(valid, range(len(blocks))))
    if limits is not None:  # on all rows at once: it counts the lines it leaves out
        keep = limits.passes(out[:, 6], out[:, 7], out[:, 8], angles[0], angles[1], np.concatenate(keeps))
        keeps = [keep[lo:hi] for lo, hi in blocks]
    sizes = [int(k.sum()) for k in keeps]
    at = np.concatenate([[0], np.cumsum(sizes)]).astype(np.int64)
    kept = int(at[-1])
    if anchor_values is None:
        anchor_values = np.full((len(anchors), 2), np.nan)
    elif isinstance(anchor_values, LazyAnchorValues):  # asked with the passing pairs only
        anchor_values = anchor_values(found[np.concatenate(keeps)]) if kept else np.zeros((0, 2))
    elif callable(anchor_values):
        anchor_values = anchor_values() if kept else np.zeros((0, 2))
    anchor_values = np.asarray(anchor_values, dtype=np.float64)
    columns = {"a1": np.empty((kept, 2), dtype=np.int64), "a2": np.empty((kept, 2), dtype=np.int64)}
    columns.update((name, np.empty(kept)) for name in sh.LINE_VALUES)
    sources = (2, 0, 1, 3, 4, 6, 7, 8)  # the columns of out of the first LINE_VALUES

    def write(k):
        (lo, hi), keep = blocks[k], keeps[k]
        o0, o1 = int(at[k]), int(at[k + 1])
        f = found[lo:hi][keep]
        o = out[lo:hi][keep]
        columns["a1"][o0:o1] = anchors[f[:, 0]]
        columns["a2"][o0:o1] = anchors[f[:, 1]]
        for name, j in zip(sh.LINE_VALUES, sources):
            columns[name][o0:o1] = o[:, j]
        columns["angle1"][o0:o1] = angles[0][lo:hi][keep]
        columns["angle2"][o0:o1] = angles[1][lo:hi][keep]
        first, second = anchor_values[f[:, 0]], anchor_values[f[:, 1]]
        columns["prom1"][o0:o1], columns["prom2"][o0:o1] = first[:, 0], second[:, 0]
        columns["drop1"][o0:o1], columns["drop2"][o0:o1] = first[:, 1], second[:, 1]

    list(each(write, range(len(blocks))))
    if nz:
        keep = np.concatenate(keeps)
        columns["zone_margins"] = margins[keep]
        if surface is not None:
            columns["zone_margins_nmpt"] = margins_s[keep]
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


def covered_metres(a1: np.ndarray, a2: np.ndarray, res: float, mask: Optional[np.ndarray]) -> np.ndarray:
    """Metres of each line over the pixels of a mask (water, filled gaps): the values of
    helpers.line_profile ("water_m", "filled_m") without the rest of the profile (float64),
    COVERED_PART lines at a time: Python's round(count * length / steps, 1) of every line
    (runs.round_floats of the same float64 products and quotients), 0.0 where no pixel is set."""
    out = np.zeros(len(a1))
    if mask is None or len(a1) == 0:
        return out
    mask = np.ascontiguousarray(mask, dtype=np.bool_)
    for at in range(0, len(a1), COVERED_PART):
        p = np.ascontiguousarray(a1[at:at + COVERED_PART], dtype=np.int64)
        q = np.ascontiguousarray(a2[at:at + COVERED_PART], dtype=np.int64)
        counts = np.zeros(len(p), dtype=np.int64)
        _covered_pixels(p, q, mask, counts)
        d = q - p
        steps = np.maximum(np.abs(d[:, 0]), np.abs(d[:, 1]))
        lengths = np.hypot(d[:, 0], d[:, 1]) * res
        some = np.flatnonzero(counts)  # the others stay 0.0 (a line may have no pixel between its anchors)
        out[at + some] = rn.round_floats(counts[some] * lengths[some] / steps[some], 1)
    return out


def covered_pixels(a1: np.ndarray, a2: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
    """Pixels of each line set in a mask (water, filled gaps), anchors excluded: the pixels
    helpers.line_profile and covered_metres sample (int64; all zeros without a mask), COVERED_PART
    lines at a time. At a resolution of 0.5 m or more, covered_pixels > 0 where covered_metres > 0."""
    out = np.zeros(len(a1), dtype=np.int64)
    if mask is None or len(a1) == 0:
        return out
    mask = np.ascontiguousarray(mask, dtype=np.bool_)
    for at in range(0, len(a1), COVERED_PART):
        p = np.ascontiguousarray(a1[at:at + COVERED_PART], dtype=np.int64)
        q = np.ascontiguousarray(a2[at:at + COVERED_PART], dtype=np.int64)
        counts = np.zeros(len(p), dtype=np.int64)
        _covered_pixels(p, q, mask, counts)
        out[at:at + len(p)] = counts
    return out


def evaluation_parts(chunks: List[Optional[np.ndarray]], size: int) -> Iterator[np.ndarray]:
    """The pairs of the chunks (arrays of pairs, in their order) in parts of size pairs (the last
    one smaller): a part of one chunk is a view of it, the pieces of small ones are copied into
    one. Each chunk is released (its entry set to None) as soon as its pairs are handed out, so
    the pairs are held once, not twice as a concatenation of all of them would."""
    pending, held = [], 0
    for i in range(len(chunks)):
        chunk, chunks[i] = chunks[i], None
        start = 0
        while held + len(chunk) - start >= size:
            end = start + size - held
            if pending:
                pending.append(chunk[start:end])
                part, pending, held = np.concatenate(pending), [], 0
                yield part
            else:
                yield chunk[start:end]
            start = end
        if start < len(chunk):  # a copy: a view would keep the whole chunk
            pending.append(chunk[start:].copy())
            held += len(chunk) - start
        del chunk
    if pending:
        yield np.concatenate(pending)


def join_tables(parts: List[sh.LineTable]) -> sh.LineTable:
    """sh.LineTable.concat of tables without profiles, one column at a time: each part's column is
    released once copied, so at most one column is held twice."""
    parts = [t for t in parts if len(t)] or parts[:1] or [sh.LineTable.empty()]
    if len(parts) == 1:
        return parts[0]
    columns = {}
    for name in list(parts[0].columns):
        columns[name] = np.concatenate([t.columns[name] for t in parts])
        for t in parts:
            del t.columns[name]
    return sh.LineTable(columns)


def find_valid_lines(elevation: np.ndarray, surface: Optional[np.ndarray], anchors: np.ndarray,
                     res: float, min_length: float, max_length: float,
                     nmpt_mode: Optional[str] = None, threads: Optional[int] = None,
                     sag_table=None, max_dh_ratio: float = np.inf,
                     max_dh: float = np.inf, first: Optional[np.ndarray] = None,
                     high_above: float = sh.HIGH_ABOVE, limits: Optional[sh.LineLimits] = None,
                     anchor_values: Union[np.ndarray, Callable[[], np.ndarray], LazyAnchorValues, None] = None,
                     strong: Optional[np.ndarray] = None, stats: Optional[Dict[str, int]] = None,
                     check: Optional[Callable[[int], None]] = None,
                     sink: Optional[Callable[[sh.LineTable], None]] = None,
                     end_zone: float = 0.0, lift: float = 0.0, end_clearance: float = 0.0,
                     zone_cap: float = sh.ZONE_CAP, zones=()) -> Optional[sh.LineTable]:
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
        anchor_values: [prominence, drop] of every anchor (terrain.py), saved with the lines; with
            a sink also a callable giving them, asked once, by the first part with a valid line, or a
            LazyAnchorValues, computing those of the anchors of each part's lines (its rest: the
            useful anchors)
        strong: Optional mask of the anchors one of which every line must have (--min-prominence)
        stats: Optional dict the counts of this call are added to (the funnel of the line search,
            jobs.FUNNEL_STEPS): anchors with an open direction, those pairs start from, candidate
            pairs, pairs checked pixel by pixel, pairs found, valid lines, lines left out by limits
        check: Optional callable given the number of valid lines so far after each evaluated part
            of the pairs found; it raises to stop the search (the limit of lines: search._lines),
            after the "checking lines" bar is closed and the counts so far are added to stats
        sink: Optional callable given the valid lines part by part instead of returning them (the
            count mode: search.count_tile): the anchors go through pair_chunk SINK_CHUNK at a time,
            the pairs found are evaluated once EVAL_PART of them are pending, and each evaluated
            part (at most SINK_PART pairs; "a1", "a2" and the LINE_VALUES, in no particular order)
            goes to the sink at once; nothing is joined, sorted or kept. Not with check
        end_zone, lift, end_clearance, zone_cap: the end zone (metres at both ends, at most
            zone_cap of the length, where only the webbing less end_clearance must stay above the
            terrain) and the lift (A-frames of that height at both ends): helpers.end_zone_rule;
            0 / 0 is the search of before, bit for bit. The clearances are the rule's decision
            values; the heights those of the strict margin plus the lift (the webbing on the A-frames)
        zones: Optional ladder of end zones (ascending from 0): the lines get their bucket minima
            ("zone_margins", "zone_margins_nmpt"), from which helpers.valid_at decides at any
            ladder zone and lift up to the call's

    Returns:
        Valid lines, longest first; None with a sink
    """
    if sink is not None and check is not None:
        raise ValueError("find_valid_lines: sink and check cannot be used together")
    delta, ladder = sh.end_zone_rule(sag_table, end_zone, lift, end_clearance, zone_cap, zones)
    rule = dict(end_zone=end_zone, lift=lift, end_clearance=end_clearance, zone_cap=zone_cap, zones=ladder)
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
    useful, rings, slot = free_directions(z, anchors, res, gain, cap, offset, min_length, max_length, end_zone,
                                          lift, delta)
    progress.compute.finish()
    print(f"Anchors with an open direction: {len(useful)} of {len(anchors)}")

    # Step 2 + 3: bucket the useful anchors, then find and check the pairs
    down = sh.downslope(z, anchors, res)
    max_angle = limits.max_wall_angle if limits is not None and limits.max_wall_angle is not None else 180.0
    cos_limit = -2.0 if max_angle >= 180 else math.cos(math.radians(max_angle))
    todo_all, args, tail = pair_arguments(z, anchors, elev, useful, rings, slot, first, res, min_length, max_length,
                                          max_dh_ratio, max_dh, down, cos_limit, strong, use_sag, log_spans,
                                          ratios, table, fall_zone, end_zone, lift, delta, zone_cap)
    if sink is not None:
        if isinstance(anchor_values, LazyAnchorValues):
            anchor_values.rest, anchor_values.rows = useful, anchors[:, 0]
            anchor_values.reach = int(math.ceil(max_length / res)) + 2  # _pairs' far2: max_length / res + 2
        _sink_lines(sink, args, tail, todo_all, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above,
                    limits, down, anchor_values, len(useful), stats, start_time, rule)
        return None
    pairs, candidates, checked, found = [], 0, 0, 0
    progress.compute.start("anchor pairs", len(todo_all), unit="anchor")
    for todo in np.array_split(todo_all, min(CHUNKS, max(1, len(todo_all)))):
        counts, out = pair_chunk(args, todo, tail)
        pairs.append(out)
        found += len(out)
        candidates += int(counts[:, 0].sum())
        checked += int(counts[:, 1].sum())
        progress.compute.update(len(todo), pairs=f"{checked:,}", lines=found)
        del out
    progress.compute.finish()

    def add_stats(valid: int):
        _add_stats(stats, len(useful), len(todo_all), candidates, checked, found, valid, limits)

    # Final decision and clearances, exactly as in the pixel-by-pixel search (evaluate_line), part
    # by part from the chunks' pairs (each chunk released once evaluated); check may stop it after a part
    parts, valid = [], 0
    progress.compute.start("checking lines", found, unit="line")
    if not found:
        progress.compute.update(0, valid=0)  # as the one empty part did
    for part in evaluation_parts(pairs, max(EVAL_PART, -(-found // CHUNKS))):
        parts.append(evaluate_lines(part, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above,
                                    limits, down, anchor_values, **rule))
        valid += len(parts[-1])
        progress.compute.update(len(part), valid=valid)
        del part
        if check is not None:
            try:
                check(valid)
            except Exception:
                progress.compute.finish(f"{valid} valid, stopped")
                add_stats(valid)
                raise
    valid_lines = join_tables(parts)
    del parts
    progress.compute.finish(f"{len(valid_lines)} valid")
    _summary(start_time, candidates, checked, limits, len(valid_lines))
    add_stats(len(valid_lines))

    # Longest first; lines of the same length keep their order (as sorted(reverse=True) did), one
    # column after another
    return valid_lines.reorder(np.argsort(-valid_lines.columns["length"], kind="stable"))


def _add_stats(stats: Optional[Dict[str, int]], open_: int, todo: int, candidates: int, checked: int, found: int,
               valid: int, limits: Optional[sh.LineLimits]):
    """Add the counts of a find_valid_lines call to stats (when given)."""
    if stats is not None:
        for key, n in (("open", open_), ("todo", todo), ("candidates", candidates), ("checked", checked),
                       ("found", found), ("valid", valid), ("left_out", limits.left_out if limits is not None else 0)):
            stats[key] = stats.get(key, 0) + int(n)


def _summary(start_time: float, candidates: int, checked: int, limits: Optional[sh.LineLimits], valid: int):
    """The summary lines of find_valid_lines."""
    print(f"\n{'=' * 60}")
    print(f"Completed in {time.time() - start_time:.2f} seconds")
    print(f"Candidate pairs between anchors with an open direction: {candidates}")
    print(f"Checked pixel by pixel: {checked}")
    if limits is not None and limits.active:
        print(f"Left out by the line limits ({limits.describe()}): {limits.left_out}")
    print(f"Found {valid} valid lines")
    print(f"{'=' * 60}")


def _sink_lines(sink: Callable[[sh.LineTable], None], args: tuple, tail: tuple, todo_all: np.ndarray,
                anchors: np.ndarray, elevation: np.ndarray, res: float, surface: Optional[np.ndarray], sag_table,
                nmpt_mode: Optional[str], high_above: float, limits: Optional[sh.LineLimits], down: np.ndarray,
                anchor_values: Union[np.ndarray, Callable[[], np.ndarray], LazyAnchorValues, None], useful: int,
                stats: Optional[Dict[str, int]], start_time: float, rule: Optional[Dict] = None):
    """Steps 2 and 3 of find_valid_lines with a sink: the pairs of SINK_CHUNK anchors at a time,
    evaluated whenever EVAL_PART of them are pending (and after the last anchors), each evaluated
    part handed to the sink at once. One bar, "anchor pairs", with the valid lines as a postfix.
    A callable anchor_values is asked once, by the first part with a valid line, a LazyAnchorValues
    by every part whose lines have an anchor not known yet; either runs a bar of its own, so the bar
    of the pairs is put back where it stood. rule: evaluate_lines' end zone, lift, end clearance,
    zone cap and zones."""
    rule = rule or {}
    pending, held, candidates, checked, found, valid = [], 0, 0, 0, 0, 0
    at, known, values, pending_at = 0, None, anchor_values, 0

    def resume():
        progress.compute.start("anchor pairs", len(todo_all), unit="anchor")
        progress.compute.update(at, pairs=f"{checked:,}", lines=found, valid=valid)

    lazy = anchor_values if isinstance(anchor_values, LazyAnchorValues) else None
    if lazy is not None:
        # the first anchors of the pairs evaluated from now on: todo_all[pending_at:]; their partners lie at
        # most reach rows above them. Neither hook refers to lazy: a cycle through it would keep the grids its
        # computation reads (search._pair_search's data, memory-mapped) alive until the cyclic collector ran,
        # and Windows refuses to write a mapped file again (the next grid of a work path)
        reach = lazy.reach
        lazy.after = resume
        lazy.floor = lambda: int(anchors[todo_all[pending_at:], 0].min()) - reach
    elif callable(anchor_values):
        def values() -> np.ndarray:
            nonlocal known
            if known is None:
                known = anchor_values()
                resume()
            return known
    progress.compute.start("anchor pairs", len(todo_all), unit="anchor")
    for at in range(0, len(todo_all), SINK_CHUNK):
        todo = todo_all[at:at + SINK_CHUNK]
        counts, out = pair_chunk(args, todo, tail, per_anchor=SINK_PAIR_BUFFER, max_bytes=SINK_PAIR_BUFFER_BYTES)
        found += len(out)
        candidates += int(counts[:, 0].sum())
        checked += int(counts[:, 1].sum())
        if len(out):
            if not pending:
                pending_at = at  # the first anchors of the pending pairs: todo_all[pending_at] on
            pending.append(out)
            held += len(out)
        del out
        if pending and (held >= EVAL_PART or at + SINK_CHUNK >= len(todo_all)):
            for part in evaluation_parts(pending, SINK_PART):
                table = evaluate_lines(part, anchors, elevation, res, surface, sag_table, nmpt_mode, high_above,
                                       limits, down, values, **rule)
                del part
                valid += len(table)
                sink(table)
                del table
            pending, held = [], 0
        progress.compute.update(len(todo), pairs=f"{checked:,}", lines=found, valid=valid)
    if lazy is not None:
        lazy.after = lazy.floor = None
    progress.compute.finish(f"{valid} valid")
    _summary(start_time, candidates, checked, limits, valid)
    _add_stats(stats, useful, len(todo_all), candidates, checked, found, valid, limits)
