"""
The numba kernels of tools/perf_line_funnel.py: frozen references of the line search and
instrumented copies of them that count where its work goes.

ref_line_ok, ref_sector, ref_free_rings and ref_pairs are copies of linesearch.py's
_line_ok, _sector, _free_rings and _pairs as of 2026-11-01 (975a1b7): the reference of
today's production. They must not change: a faster production kernel must give exactly
their rings, counts and pairs (the self-check of perf_line_funnel.py analyse).

funnel_rings and funnel_pairs repeat their decisions with counters. Every counter is an
int64 written at its anchor's own index (no sum across prange iterations, so the results
do not depend on the number of threads); the caller sums them per chunk.
"""

import math

import numpy as np
from numba import njit, prange

import helpers as sh

SECTORS = 64   # linesearch.SECTORS of 975a1b7
RINGS = 64     # linesearch.RINGS
EPS = 1e-6     # linesearch.EPS
HALF = SECTORS // 2


# ---------------------------------------------------------------------------------------------
# The references (copies of linesearch.py at 975a1b7; do not change)

@njit(cache=True)
def ref_index(x, xs):
    """linesearch._index."""
    n = xs.size
    if x <= xs[0]:
        return 0.0
    if x >= xs[n - 1]:
        return float(n - 1)
    k = np.searchsorted(xs, x, side="right") - 1
    return k + (x - xs[k]) / (xs[k + 1] - xs[k])


@njit(cache=True)
def ref_line_ok(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone):
    """linesearch._line_ok."""
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    if steps < 2:
        return False
    length = math.hypot(dr, dc) * res
    e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
    emin = min(e1, e2)
    i0, j0, a, b, points = 0, 0, 0.0, 0.0, table.shape[2]
    if use_sag:
        si = ref_index(math.log(length), log_spans)
        ri = ref_index((e1 - e2) / length, ratios)
        i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
        a, b = si - i0, ri - j0

    lo, hi = 1, steps - 1
    while lo <= hi:
        for k in (lo, hi):
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
            if not (limit - np.float64(z[r, c]) > -EPS):
                return False
        lo += 1
        hi -= 1
    return True


@njit(parallel=True, cache=True)
def ref_free_rings(z, anchors, res, gain, cap, offset):
    """linesearch._free_rings."""
    n = anchors.shape[0]
    h, w = z.shape
    rings = np.zeros((n, SECTORS), dtype=np.int32)
    width = 2 * np.pi / SECTORS
    for a in prange(n):
        r0, c0 = anchors[a, 0], anchors[a, 1]
        e = np.float64(z[r0, c0])
        alive = np.ones(SECTORS, dtype=np.bool_)
        below = np.zeros(SECTORS, dtype=np.bool_)
        for k in range(1, RINGS + 1):
            below[:] = False
            limit = e + min(gain * k * res, cap) - offset + EPS
            delta = math.asin(min(1.0, 0.7072 / k))
            for i in range(-k, k + 1):
                step = 1 if abs(i) == k else 2 * k
                for j in range(-k, k + 1, step):
                    rr, cc = r0 + i, c0 + j
                    if rr < 0 or cc < 0 or rr >= h or cc >= w:
                        continue
                    if not (np.float64(z[rr, cc]) < limit):
                        continue
                    angle = math.atan2(i, j)
                    for s in range(int(math.floor((angle - delta) / width)),
                                   int(math.floor((angle + delta) / width)) + 1):
                        below[s % SECTORS] = True
            open_any = False
            for s in range(SECTORS):
                if alive[s] and below[s]:
                    rings[a, s] = k
                    open_any = True
                else:
                    alive[s] = False
            if not open_any:
                break
    return rings


@njit(cache=True)
def ref_sector(dr, dc):
    """linesearch._sector."""
    return int(math.floor(math.atan2(dr, dc) / (2 * np.pi / SECTORS))) % SECTORS


@njit(parallel=True, cache=True)
def ref_pairs(z, anchors, elev, rings, todo, order, starts, cell, cells_x, res,
              min_length, max_length, max_dh_ratio, max_dh, down, cos_limit, strong,
              use_sag, log_spans, ratios, table, fall_zone, first_only, offsets, out, counts):
    """linesearch._pairs."""
    reach = int(max_length / res) // cell + 1
    cells_y = starts.size // cells_x
    for q in prange(todo.size):
        i = todo[q]
        ri, ci = anchors[i, 0], anchors[i, 1]
        cy, cx = ri // cell, ci // cell
        candidates, checked, found = 0, 0, 0
        for gy in range(max(0, cy - reach), min(cells_y, cy + reach + 1)):
            for gx in range(max(0, cx - reach), min(cells_x, cx + reach + 1)):
                g = gy * cells_x + gx
                end = starts[g + 1] if g + 1 < starts.size else order.size
                for p in range(starts[g], end):
                    j = order[p]
                    if first_only:
                        if anchors[j, 1] < ci or (anchors[j, 1] == ci and anchors[j, 0] >= ri):
                            continue
                    elif j <= i:
                        continue
                    if not (strong[i] or strong[j]):
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
                    if rings[a, ref_sector(dr, dc)] < need or rings[b, ref_sector(-dr, -dc)] < need:
                        continue
                    checked += 1
                    if ref_line_ok(z, anchors[a, 0], anchors[a, 1], anchors[b, 0], anchors[b, 1], res,
                                   use_sag, log_spans, ratios, table, fall_zone):
                        if offsets is not None:
                            out[offsets[q] + found, 0] = a
                            out[offsets[q] + found, 1] = b
                        found += 1
        counts[q, 0], counts[q, 1], counts[q, 2] = candidates, checked, found


# ---------------------------------------------------------------------------------------------
# Free rings, counted

RING_COUNTERS = ("rings", "pixel_reads", "atan2", "atan2_dead", "rings_beyond_need")


@njit(parallel=True, cache=True)
def funnel_rings(z, anchors, res, gain, cap, offset, big_k, counters, alive_sectors, reads, alive_scan):
    """ref_free_rings with counters; returns the same rings.

    counters[a] (RING_COUNTERS): rings processed, pixels read (inside the grid), atan2 calls,
    atan2 calls all of whose marked sectors were dead already, rings processed beyond
    big_k (the largest need of a pair). Per ring k (column k - 1, rings processed only):
    alive_sectors (alive when the ring starts), reads (pixels read) and alive_scan (pixels
    read whose sector range [angle - delta, angle + delta] meets an alive sector: what a
    scan of the alive sectors only would read).
    """
    n = anchors.shape[0]
    h, w = z.shape
    rings = np.zeros((n, SECTORS), dtype=np.int32)
    width = 2 * np.pi / SECTORS
    for a in prange(n):
        r0, c0 = anchors[a, 0], anchors[a, 1]
        e = np.float64(z[r0, c0])
        alive = np.ones(SECTORS, dtype=np.bool_)
        below = np.zeros(SECTORS, dtype=np.bool_)
        for k in range(1, RINGS + 1):
            counters[a, 0] += 1
            if k > big_k:
                counters[a, 4] += 1
            n_alive = 0
            for s in range(SECTORS):
                if alive[s]:
                    n_alive += 1
            alive_sectors[a, k - 1] = n_alive
            below[:] = False
            limit = e + min(gain * k * res, cap) - offset + EPS
            delta = math.asin(min(1.0, 0.7072 / k))
            for i in range(-k, k + 1):
                step = 1 if abs(i) == k else 2 * k
                for j in range(-k, k + 1, step):
                    rr, cc = r0 + i, c0 + j
                    if rr < 0 or cc < 0 or rr >= h or cc >= w:
                        continue
                    counters[a, 1] += 1
                    reads[a, k - 1] += 1
                    angle = math.atan2(i, j)
                    s_lo = int(math.floor((angle - delta) / width))
                    s_hi = int(math.floor((angle + delta) / width))
                    any_alive = False
                    for s in range(s_lo, s_hi + 1):
                        if alive[s % SECTORS]:
                            any_alive = True
                    if any_alive:
                        alive_scan[a, k - 1] += 1
                    if not (np.float64(z[rr, cc]) < limit):
                        continue
                    counters[a, 2] += 1
                    if not any_alive:
                        counters[a, 3] += 1
                    for s in range(s_lo, s_hi + 1):
                        below[s % SECTORS] = True
            open_any = False
            for s in range(SECTORS):
                if alive[s] and below[s]:
                    rings[a, s] = k
                    open_any = True
                else:
                    alive[s] = False
            if not open_any:
                break
    return rings


# ---------------------------------------------------------------------------------------------
# Cells of the pair search

@njit(cache=True)
def cell_summary(order, starts, elev, rings, need_min):
    """Per cell of the pair search: the OR of its anchors' sectors with rings >= need_min
    (bit s: sector s) and the lowest and highest elevation of its anchors (NaN left out;
    inf, -inf for a cell without one)."""
    cells = starts.size
    mask = np.zeros(cells, dtype=np.uint64)
    emin = np.full(cells, np.inf)
    emax = np.full(cells, -np.inf)
    one = np.uint64(1)
    for g in range(cells):
        end = starts[g + 1] if g + 1 < cells else order.size
        for p in range(starts[g], end):
            j = order[p]
            for s in range(SECTORS):
                if rings[j, s] >= need_min:
                    mask[g] |= one << np.uint64(s)
            e = np.float64(elev[j])
            if e == e:
                emin[g] = min(emin[g], e)
                emax[g] = max(emax[g], e)
    return mask, emin, emax


# ---------------------------------------------------------------------------------------------
# The pair search, counted

# Columns of funnel_pairs' counters (perf_line_funnel.PAIR_COUNTERS names them)
C_VISITS, C_DEDUP, C_STRONG, C_MAX_LENGTH, C_MIN_LENGTH, C_HEIGHT, C_WALL = 0, 1, 2, 3, 4, 5, 6
C_CANDIDATES, C_RINGS_A, C_RINGS_B, C_CHECKED, C_LINE_FAIL, C_FOUND, C_TESTS = 7, 8, 9, 10, 11, 12, 13
C_SKIP = 14         # 6 rules alone: F2a, F2b, N1, F8c, cell elevation, N3
C_CUM = 20          # the same, cumulative in that order
C_UNSAFE = 26       # checked pairs a rule would skip (must stay 0: a rule may skip only what fails before
                    # _line_ok, so that the lines and the counters of the regression stay as they are)
C_PREFIX = 32       # F2a with the within-cell prefix (order[p] <= i)
C_F8C_OWN = 33      # F8c by the anchor's own rings only
C_F8C_PARTNERS = 34  # F8c by the partners' sector masks only
C_SAMPLED = 35      # 1: the anchor's checked pairs were simulated
C_SAMPLED_TESTS = 36  # its counted _line_ok tests
C_SIM_MISMATCH = 37  # simulated decision != _line_ok's (must stay 0)
C_N1_CANDIDATES = 38  # candidates N1 skips (production skips them before counting the candidates)
N_COUNTERS = 39

ORDERS = ("ends_inward", "natural", "middle_out", "bit_reversal", "unscreened_first", "two_ends_bit_reversal")
N_ORDERS = 6
LOG_BINS = 16
# Columns of the histograms per anchor
H_PASS = 0                       # 3 length classes: checked pairs without a failing pixel
H_LOG = 3                        # 3 x LOG_BINS: first failure, floor(log2(distance from nearer end))
H_ZONE = H_LOG + 3 * LOG_BINS    # 3 x 2: first failure inside, outside the screened zone
H_END = H_ZONE + 6               # 3: at the higher end, the lower end, neither (middle, equal heights)
H_CHECKED = H_END + 3            # 3 length classes: checked pairs simulated
N_HIST = H_CHECKED + 3


@njit(cache=True)
def counted_line_ok(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone):
    """ref_line_ok, also returning the number of pixel tests it made."""
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    if steps < 2:
        return False, 0
    length = math.hypot(dr, dc) * res
    e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
    emin = min(e1, e2)
    i0, j0, a, b, points = 0, 0, 0.0, 0.0, table.shape[2]
    if use_sag:
        si = ref_index(math.log(length), log_spans)
        ri = ref_index((e1 - e2) / length, ratios)
        i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
        a, b = si - i0, ri - j0
    tests = 0
    lo, hi = 1, steps - 1
    while lo <= hi:
        for k in (lo, hi):
            tests += 1
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
            if not (limit - np.float64(z[r, c]) > -EPS):
                return False, tests
        lo += 1
        hi -= 1
    return True, tests


@njit(cache=True)
def line_fails(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone, fail):
    """fail[k] for every pixel k = 1 .. steps - 1 of the line: _line_ok's test fails there
    (the same arithmetic). Returns steps."""
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    length = math.hypot(dr, dc) * res
    e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
    emin = min(e1, e2)
    i0, j0, a, b, points = 0, 0, 0.0, 0.0, table.shape[2]
    if use_sag:
        si = ref_index(math.log(length), log_spans)
        ri = ref_index((e1 - e2) / length, ratios)
        i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
        a, b = si - i0, ri - j0
    for k in range(1, steps):
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
        fail[k] = not (limit - np.float64(z[r, c]) > -EPS)
    return steps


@njit(cache=True)
def _bits(v):
    b = 0
    while v > 0:
        b += 1
        v >>= 1
    return b


@njit(cache=True)
def _reverse(m, bits):
    rev = 0
    for _ in range(bits):
        rev = (rev << 1) | (m & 1)
        m >>= 1
    return rev


@njit(cache=True)
def order_tests(fail, steps, kind):
    """Pixel tests until the first failing pixel (all of them when none fails) under an
    order of ORDERS; ends_inward counts as _line_ok does (the middle pixel twice), the
    others test every pixel once. Returns (tests, the first failing pixel or -1)."""
    tests = 0
    if kind == 0:  # ends inward: today's loop
        lo, hi = 1, steps - 1
        while lo <= hi:
            tests += 1
            if fail[lo]:
                return tests, lo
            tests += 1
            if fail[hi]:
                return tests, hi
            lo += 1
            hi -= 1
        return tests, -1
    if kind == 1:  # natural 1 .. steps - 1
        for k in range(1, steps):
            tests += 1
            if fail[k]:
                return tests, k
        return tests, -1
    if kind == 2:  # middle out: m, m - 1, m + 1, m - 2, m + 2, ...
        m = steps // 2
        tests += 1
        if fail[m]:
            return tests, m
        d = 1
        while m - d >= 1 or m + d <= steps - 1:
            for k in (m - d, m + d):
                if 1 <= k <= steps - 1:
                    tests += 1
                    if fail[k]:
                        return tests, k
            d += 1
        return tests, -1
    if kind == 3:  # bit reversal of 0 .. 2^B - 1 (B: the bits of steps - 1), outside 1 .. steps - 1 dropped
        bits = _bits(steps - 1)
        for m in range(1 << bits):
            k = _reverse(m, bits)
            if 1 <= k <= steps - 1:
                tests += 1
                if fail[k]:
                    return tests, k
        return tests, -1
    if kind == 4:  # the unscreened middle first (ends inward), then the screened zones (ends inward)
        need = min(RINGS, steps // 2)
        lo, hi = need + 1, steps - need - 1
        while lo <= hi:
            tests += 1
            if fail[lo]:
                return tests, lo
            if hi != lo:
                tests += 1
                if fail[hi]:
                    return tests, hi
            lo += 1
            hi -= 1
        for d in range(1, need + 1):
            tests += 1
            if fail[d]:
                return tests, d
            if steps - d != d:
                tests += 1
                if fail[steps - d]:
                    return tests, steps - d
        return tests, -1
    # kind 5: pixels 1, steps - 1, 2, steps - 2, then the bit reversal of the others
    first = (1, steps - 1, 2, steps - 2)
    for n in range(4):
        k = first[n]
        dup = False
        for n2 in range(n):
            if first[n2] == k:
                dup = True
        if dup or k < 1 or k > steps - 1:
            continue
        tests += 1
        if fail[k]:
            return tests, k
    bits = _bits(steps - 1)
    for m in range(1 << bits):
        k = _reverse(m, bits)
        if 1 <= k <= steps - 1 and k != 1 and k != 2 and k != steps - 1 and k != steps - 2:
            tests += 1
            if fail[k]:
                return tests, k
    return tests, -1


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


@njit(parallel=True, cache=True)
def funnel_pairs(z, anchors, elev, rings, todo, order, starts, cell, cells_x, res,
                 min_length, max_length, max_dh_ratio, max_dh, down, cos_limit, strong,
                 use_sag, log_spans, ratios, table, fall_zone, first_only,
                 rmax, big_k, cell_mask, cell_emin, cell_emax, d0, far2, sample, counters, sim, hist):
    """ref_pairs (its counting pass) with counters per todo anchor q (columns C_*), the
    visits a candidate rule would skip (alone and cumulatively in the order F2a, F2b, N1,
    F8c, cell elevation, N3), and for the anchors with sample[q] the simulated pixel tests
    of every checked pair under each of ORDERS (sim[q]) and where it fails first (hist[q]).

    The rules (each one only skips visits that fail a test of ref_pairs):
    F2a: the cell holds no anchor after i (its last, largest index <= i; first_only:
    gx < cx); F2b: the cell's nearest pixel is farther than far2 (squared, in pixels);
    N1: the Chebyshev distance > 2 R + 1 for R = rmax of i or of the partner, when R < big_k;
    F8c: all sectors of i towards the cell (its corners' angles, one sector of margin) have
    fewer rings than the need at the cell's nearest Chebyshev distance, or no anchor of the
    cell is open (rings >= need_min, cell_mask) in the opposite sectors; cell elevation:
    [cell_emin, cell_emax] misses e_i -+ (d0 + 1e-3); N3: |e_j - e_i| > d0 + 1e-3.
    """
    reach = int(max_length / res) // cell + 1
    cells_y = starts.size // cells_x
    width = 2 * np.pi / SECTORS
    zero, one = np.uint64(0), np.uint64(1)
    maxsteps = int(max_length / res) + 3
    for q in prange(todo.size):
        i = todo[q]
        ri, ci = anchors[i, 0], anchors[i, 1]
        cy, cx = ri // cell, ci // cell
        ei = elev[i]
        fail = np.zeros(maxsteps + 1 if sample[q] else 1, dtype=np.bool_)
        counters[q, C_SAMPLED] = 1 if sample[q] else 0
        for gy in range(max(0, cy - reach), min(cells_y, cy + reach + 1)):
            y0 = gy * cell
            y1 = y0 + cell - 1
            dy = max(0, max(y0 - ri, ri - y1))
            for gx in range(max(0, cx - reach), min(cells_x, cx + reach + 1)):
                g = gy * cells_x + gx
                end = starts[g + 1] if g + 1 < starts.size else order.size
                if starts[g] >= end:
                    continue
                x0 = gx * cell
                x1 = x0 + cell - 1
                dx = max(0, max(x0 - ci, ci - x1))
                # The rules that decide for the whole cell
                f2a = gx < cx if first_only else order[end - 1] <= i
                f2b = dy * dy + dx * dx > far2
                f8_own, f8_partners = False, False
                if dy > 0 or dx > 0:
                    alo, ahi = _arc(y0 - ri, y1 - ri, x0 - ci, x1 - ci)
                    s_lo = int(math.floor(alo / width)) - 1
                    s_hi = int(math.floor(ahi / width)) + 1
                    need_c = min(RINGS, max(dy, dx) // 2)
                    if need_c > 0:
                        f8_own = True
                        for s in range(s_lo, s_hi + 1):
                            if rings[i, s % SECTORS] >= need_c:
                                f8_own = False
                                break
                    m = zero
                    for s in range(s_lo + HALF, s_hi + HALF + 1):
                        m |= one << np.uint64(s % SECTORS)
                    f8_partners = (cell_mask[g] & m) == zero
                f8c = f8_own or f8_partners
                er = cell_emax[g] < ei - d0 - 1e-3 or cell_emin[g] > ei + d0 + 1e-3
                for p in range(starts[g], end):
                    j = order[p]
                    counters[q, C_VISITS] += 1
                    drj, dcj = anchors[j, 0] - ri, anchors[j, 1] - ci
                    cheb = max(abs(drj), abs(dcj))
                    n1 = (rmax[i] < big_k and cheb > 2 * rmax[i] + 1) or \
                        (rmax[j] < big_k and cheb > 2 * rmax[j] + 1)
                    n3 = abs(elev[j] - ei) > d0 + 1e-3
                    rules = (f2a, f2b, n1, f8c, er, n3)
                    cum = False
                    for r in range(6):
                        if rules[r]:
                            counters[q, C_SKIP + r] += 1
                        cum = cum or rules[r]
                        if cum:
                            counters[q, C_CUM + r] += 1
                    if f2a or (not first_only and j <= i):
                        counters[q, C_PREFIX] += 1
                    if f8_own:
                        counters[q, C_F8C_OWN] += 1
                    if f8_partners:
                        counters[q, C_F8C_PARTNERS] += 1
                    # Today's tests, in their order
                    if first_only:
                        dedup = anchors[j, 1] < ci or (anchors[j, 1] == ci and anchors[j, 0] >= ri)
                    else:
                        dedup = j <= i
                    if dedup:
                        counters[q, C_DEDUP] += 1
                        continue
                    if not (strong[i] or strong[j]):
                        counters[q, C_STRONG] += 1
                        continue
                    a, b = (i, j) if i < j else (j, i)
                    dr, dc = anchors[b, 0] - anchors[a, 0], anchors[b, 1] - anchors[a, 1]
                    length = math.hypot(dr, dc) * res
                    if length > max_length:
                        counters[q, C_MAX_LENGTH] += 1
                        continue
                    if length < min_length:
                        counters[q, C_MIN_LENGTH] += 1
                        continue
                    if not (abs(elev[b] - elev[a]) <= min(max_dh_ratio * length, max_dh)):
                        counters[q, C_HEIGHT] += 1
                        continue
                    if cos_limit > -1.0:
                        n = math.hypot(dr, dc)
                        if (dr * down[a, 0] + dc * down[a, 1]) / n < cos_limit - EPS or \
                                -(dr * down[b, 0] + dc * down[b, 1]) / n < cos_limit - EPS:
                            counters[q, C_WALL] += 1
                            continue
                    counters[q, C_CANDIDATES] += 1
                    if n1:
                        counters[q, C_N1_CANDIDATES] += 1
                    need = min(RINGS, max(abs(dr), abs(dc)) // 2)
                    if rings[a, ref_sector(dr, dc)] < need:
                        counters[q, C_RINGS_A] += 1
                        continue
                    if rings[b, ref_sector(-dr, -dc)] < need:
                        counters[q, C_RINGS_B] += 1
                        continue
                    counters[q, C_CHECKED] += 1
                    for r in range(6):
                        if rules[r]:
                            counters[q, C_UNSAFE + r] += 1
                    r1, c1, r2, c2 = anchors[a, 0], anchors[a, 1], anchors[b, 0], anchors[b, 1]
                    ok, tests = counted_line_ok(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table,
                                                fall_zone)
                    counters[q, C_TESTS] += tests
                    if ok:
                        counters[q, C_FOUND] += 1
                    else:
                        counters[q, C_LINE_FAIL] += 1
                    if sample[q]:
                        counters[q, C_SAMPLED_TESTS] += tests
                        steps = line_fails(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table,
                                           fall_zone, fail)
                        today = -1
                        for kind in range(N_ORDERS):
                            t_kind, at = order_tests(fail, steps, kind)
                            sim[q, kind] += t_kind
                            if kind == 0:
                                today = at
                        if (today < 0) != ok:
                            counters[q, C_SIM_MISMATCH] += 1
                        cls = 0 if steps <= 129 else (1 if steps <= 500 else 2)
                        hist[q, H_CHECKED + cls] += 1
                        if today < 0:
                            hist[q, H_PASS + cls] += 1
                        else:
                            d = min(today, steps - today)
                            hist[q, H_LOG + cls * LOG_BINS + min(LOG_BINS - 1, _bits(d) - 1)] += 1
                            need_s = min(RINGS, steps // 2)
                            hist[q, H_ZONE + cls * 2 + (0 if d <= need_s else 1)] += 1
                            e1, e2 = np.float64(z[r1, c1]), np.float64(z[r2, c2])
                            if 2 * today == steps or not (e1 > e2 or e2 > e1):
                                hist[q, H_END + 2] += 1
                            elif (2 * today < steps) == (e1 > e2):
                                hist[q, H_END] += 1
                            else:
                                hist[q, H_END + 1] += 1
