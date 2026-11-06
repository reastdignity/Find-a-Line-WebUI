"""
The numba kernels of tools/end_zone_study.py: copies of linesearch.py's _line_ok, _free_rings,
_pairs and _evaluate (main 41377c2) with the end-zone rule of the study, as small a diff as can
be, so they can become the production change later.

The rule: a pixel of a line passes when its strict margin s = limit - terrain satisfies

    s > -lift - delta * [the pixel lies in the end zone]

lift: an A-frame of that height at both ends (metres); delta = fall - end_clearance >= 0 (fall:
helpers.fall_allowance); the zone: the steps k (1 .. steps - 1) with k < kz or steps - k < kz,
kz = zone_steps(steps, length, end_zone, cap). The limit itself is computed as production
computes it, float operation by float operation; lift and delta enter the comparison only. At
end_zone = 0 and lift = 0 every comparison is production's (s > -0.0 is s > 0, and the
kernels' -EPS - 0.0 - 0.0 is -EPS).

Every change against production is marked "# end zone".
"""

import math

import numpy as np
from numba import njit, prange

import helpers as sh
from linesearch import (EPS, HALF, LINE_ORDER_MAX, LINE_ORDER_SPLIT, RINGS, SECTORS, _cell_sectors, _index,
                        _interp, _interp_forward, _isqrt, _sector)


@njit(cache=True)
def zone_steps(steps, length, end_zone, cap):
    """kz of a line of `steps` DDA steps and `length` metres: the number of steps k >= 0 (the
    anchor itself counted) whose distance k * length / steps from the nearer anchor is below
    min(end_zone, cap * length). Step k (1 .. steps - 1) lies in the zone iff k < kz or
    steps - k < kz. The one definition: every test of the zone calls this function."""
    d = min(end_zone, cap * length)
    if not d > 0.0:
        return 0
    return int(math.ceil(d * steps / length))


@njit(cache=True)
def _limit_at(z, r1, c1, dr, dc, k, steps, length, e1, e2, emin, use_sag, i0, j0, a, b, table, points, fall_zone):
    """The margin limit - z of step k, as _line_ok computes it (the same float operations)."""
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
def line_ok_v(z, r1, c1, r2, c2, res, use_sag, log_spans, ratios, table, fall_zone, lift, delta, end_zone, cap):
    """linesearch._line_ok with the end-zone rule: a pixel passes when limit - z > -EPS - lift
    - delta * [in the zone]. The first strict step at each end (kz, steps - kz) is tested first
    (in the zone most lines pass now, beyond it they fail), then production's order."""
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
    kz = zone_steps(steps, length, end_zone, cap)  # end zone
    strict, lenient = -EPS - lift - 0.0, -EPS - lift - delta  # end zone
    if 0 < kz < steps:  # end zone: the first strict step at each end first
        for k in (kz, steps - kz):
            if k < kz or steps - k < kz:
                continue  # in the zone from the other end (a short line)
            m = _limit_at(z, r1, c1, dr, dc, k, steps, length, e1, e2, emin, use_sag, i0, j0, a, b, table, points,
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
            bound = lenient if (k < kz or steps - k < kz) else strict  # end zone
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
            bound = lenient if (k < kz or steps - k < kz) else strict  # end zone
            if not (limit - np.float64(z[r, c]) > bound):  # NaN (no data) fails too
                return False
    return True


def ring_offsets(offset: float, kmax: int, res: float, lift: float, delta: float, end_zone: float) -> np.ndarray:
    """offsets[k] of free_rings_v (k = 1 .. kmax; offsets[0] = offset, unused): offset - lift - delta
    * [(k - 1) * res < end_zone].
    The rings do not know a line's length, so the zone is end_zone uncapped (the sound side: step
    k of a line lies at least k * res from its anchor, and k < kz means k * res < end_zone). At
    lift = 0 and end_zone = 0 every value is offset itself."""
    return np.array([offset] + [offset - lift - (delta if (k - 1) * res < end_zone else 0.0)
                                for k in range(1, kmax + 1)], dtype=np.float64)


@njit(parallel=True, cache=True)
def free_rings_v(z, anchors, res, gain, cap, offsets, kmax, masks):
    """linesearch._free_rings with an offset per ring (ring_offsets) instead of one."""
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
            limit = e + min(gain * k * res, cap) - offsets[k] + EPS  # end zone: offsets[k]
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


@njit(parallel=True, cache=True)
def pairs_v(z, anchors, elev, rings, slot, rmax, todo, order, starts, cell_open, open_mask, cell, cells_x, res,
            min_length, max_length, max_dh_ratio, max_dh, d0, far2, kmax, down, cos_limit, strong,
            use_sag, log_spans, ratios, table, fall_zone, first_only, lift, delta, end_zone, zone_cap,
            offsets, out, buf, counts):
    """linesearch._pairs whose line check is line_ok_v (lift, delta, end_zone, zone_cap: the rule)."""
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
                    if line_ok_v(z, anchors[a, 0], anchors[a, 1], anchors[b, 0], anchors[b, 1], res,
                                 use_sag, log_spans, ratios, table, fall_zone, lift, delta, end_zone,
                                 zone_cap):  # end zone
                        if offsets is not None:
                            out[offsets[q] + found, 0] = a
                            out[offsets[q] + found, 1] = b
                        elif found < keep:
                            buf[q, found, 0] = a
                            buf[q, found, 1] = b
                        found += 1
        counts[q, 0], counts[q, 1], counts[q, 2] = candidates, checked, found


@njit(cache=True)
def _copy_buffered(buf, found, offsets, out):
    """linesearch._copy_buffered."""
    keep = buf.shape[1]
    for q in range(found.size):
        if found[q] <= keep:
            for k in range(found[q]):
                out[offsets[q] + k, 0] = buf[q, k, 0]
                out[offsets[q] + k, 1] = buf[q, k, 1]


@njit(parallel=True, cache=True)
def evaluate_v(z, s, has_s, anchors, found, res, use_sag, log_spans, span_index, ratios, ratio_index,
               sag, fractions, fall_zone, high_above, lift, delta, end_zone, zone_cap, zones, out, terrain, surface):
    """linesearch._evaluate (out[k, 0..8] the same values to the last bit), plus:

    out[k, 9]: 1 when every pixel passes the rule (end_zone, lift, delta; no EPS, as the final
    decision), out[k, 10]: 1 when a pixel of the surface model fails it (NaN pixels skipped,
    as np.nanmin); terrain[k, j], surface[k, j]: the smallest strict margin of the pixels of
    bucket j (j < zones.size: the steps first in the zone of zones[j], kz of zone_steps with
    zone_cap; j = zones.size: the rest), +inf when a bucket is empty (NaN pixels skipped: a NaN
    of the terrain makes out[k, 3] NaN)."""
    blend = np.empty(fractions.size)
    fall = fall_zone if use_sag else sh.LEASH_FALL  # helpers.fall_allowance
    nz = zones.size
    for k in prange(found.shape[0]):
        r1, c1 = anchors[found[k, 0], 0], anchors[found[k, 0], 1]
        r2, c2 = anchors[found[k, 1], 0], anchors[found[k, 1], 1]
        dr, dc = r2 - r1, c2 - c1
        steps = max(abs(dr), abs(dc))
        out[k, 5] = 0.0
        out[k, 9], out[k, 10] = 0.0, 0.0  # end zone
        for j in range(nz + 1):  # end zone
            terrain[k, j], surface[k, j] = np.inf, np.inf
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
        # end zone: kz of the rule and of the ladder's zones
        kz = zone_steps(steps, length, end_zone, zone_cap)
        strict, lenient = -lift - 0.0, -lift - delta
        kzs = np.empty(nz, dtype=np.int64)
        for j in range(nz):
            kzs[j] = zone_steps(steps, length, zones[j], zone_cap)
        ok, surface_fails = True, False
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
            # end zone: the rule, and the bucket of the step
            e = min(i, steps - i)
            bound = lenient if e < kz else strict
            if not (margin > bound):
                ok = False
            bucket = nz
            for j in range(nz):
                if e < kzs[j]:
                    bucket = j
                    break
            if margin < terrain[k, bucket]:
                terrain[k, bucket] = margin
            if has_s:
                over = limit - np.float64(s[r, c])
                if over == over:  # np.nanmin
                    seen = True
                    if over < nmpt:
                        nmpt = over
                    if over <= bound:  # end zone
                        surface_fails = True
                    if over < surface[k, bucket]:  # end zone
                        surface[k, bucket] = over
        out[k, 0], out[k, 1], out[k, 2], out[k, 3] = e1, e2, length, clearance
        out[k, 4] = nmpt if seen else np.nan
        out[k, 5] = 1.0
        out[k, 6], out[k, 7] = height_max, height_sum / (steps - 1)
        out[k, 8] = 100.0 * high / (steps - 1)
        out[k, 9] = 1.0 if ok else 0.0  # end zone
        out[k, 10] = 1.0 if surface_fails else 0.0
