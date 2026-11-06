"""
The profiles of many lines at once (numba, parallel over the lines).

helpers.line_profile gives the profile of one line as a dict of Python lists; line_profiles
gives exactly those values for many lines as a helpers.Profiles: numpy arrays of all their
points one line after another, about 26 bytes per point where the lists took about 100.
The kernel samples the same pixels (r1 + rint(dr * t)) and repeats the arithmetic of
helpers.max_safe_elevation and webbing_height (formula and sag, as linesearch._evaluate);
the values are rounded afterwards with runs.round_floats, which is Python's round().
"""

import math
from typing import Optional

import numpy as np
from numba import njit, prange

import helpers as sh
import linesearch as ls
import runs as rn

# The rounding of the saved values (helpers.line_profile): distances to 0.1 m, heights to 1 cm,
# per column of Profiles.small; line_profile rounds the distances of "min", "min_nmpt" and
# "max_height" as numpy floats, whose round() is np.round (2.675 -> 2.68), the rest as Python
# floats (2.675 -> 2.67, runs.round_floats)
SMALL_DIGITS = (1, 2, 1, 2, 1, 2, 1, 1)
NUMPY_ROUNDED = (0, 2, 4)
ROUND_PART = 1 << 20  # points rounded at once (runs.round_floats takes several temporaries of each)


@njit(cache=True)
def _first_min(values, lo, hi, largest):
    """np.nanargmin (largest: nanargmax) of values[lo:hi] plus lo; -1 when all are NaN."""
    best, at = np.nan, -1
    for i in range(lo, hi):
        v = values[i]
        if v != v:
            continue
        if at < 0 or (v > best if largest else v < best):
            best, at = v, i
    return at


@njit(parallel=True, cache=True)
def _profiles(z, s, has_s, water, has_w, filled, has_g, a1, a2, res, use_sag, log_spans, span_index, ratios,
              ratio_index, sag, fractions, fall_zone, max_points, end_zone, lift, delta, zone_cap, starts, d_out,
              z_out, s_out, w_out, g_out, counts, small, flags):
    """helpers.line_profile of every line, unrounded, into the rows starts[k].. of the outputs.

    counts[k]: the points kept (-1: no pixel between the anchors, -2: no data there); small[k]:
    min distance and clearance, min_nmpt's (NaN: none), max_height's, water_m, filled_m; flags[k]:
    1 water on the line, 2 filled pixels on it, 4 a point kept without terrain or surface data.
    "min" and "min_nmpt" follow the decision values of the end zone and the lift (end_zone,
    lift, delta, zone_cap: helpers.decision_values), "max_height" the strict margin.
    """
    fall = fall_zone if use_sag else sh.LEASH_FALL  # helpers.fall_allowance
    c_zone = lift + delta
    for k in prange(a1.shape[0]):
        r1, c1, r2, c2 = a1[k, 0], a1[k, 1], a2[k, 0], a2[k, 1]
        dr, dc = r2 - r1, c2 - c1
        steps = max(abs(dr), abs(dc))
        counts[k] = -1
        flags[k] = 0
        if steps < 2:
            continue
        n = steps + 1
        length = np.hypot(np.float64(dr), np.float64(dc)) * res
        rows = np.empty(n, dtype=np.int64)
        cols = np.empty(n, dtype=np.int64)
        terrain = np.empty(n)
        for i in range(n):
            t = i / steps
            rows[i] = r1 + int(np.rint(dr * t))
            cols[i] = c1 + int(np.rint(dc * t))
            terrain[i] = np.float64(z[rows[i], cols[i]])
        e1, e2 = terrain[0], terrain[steps]
        emin = min(e1, e2)
        row = np.empty(fractions.size)
        if use_sag:  # sag.EnvelopeTable.__call__, as linesearch._evaluate
            si = ls._interp(math.log(length), log_spans, span_index)
            ri = ls._interp((e1 - e2) / length, ratios, ratio_index)
            i0, j0 = min(int(si), log_spans.size - 2), min(int(ri), ratios.size - 2)
            a, b = si - i0, ri - j0
            for f in range(fractions.size):
                row[f] = ((1 - a) * (1 - b) * sag[i0, j0, f] + a * (1 - b) * sag[i0 + 1, j0, f]
                          + (1 - a) * b * sag[i0, j0 + 1, f] + a * b * sag[i0 + 1, j0 + 1, f])
        limit = np.empty(n)
        margin = np.empty(n)
        value = np.empty(n)  # the decision values (helpers.decision_values; the margin at 0 / 0)
        offset = np.empty(n)
        kz = ls._zone_steps(steps, length, end_zone, zone_cap)  # helpers.zone_offsets
        for i in range(n):  # helpers.max_safe_elevation
            t = i / steps
            if use_sag:
                limit[i] = e1 + (e2 - e1) * t - ls._interp(t, fractions, row) - fall_zone
            else:
                limit[i] = emin - sh.SLOPE * min(t, 1 - t) * length - sh.LEASH_FALL
            margin[i] = limit[i] - terrain[i]
            offset[i] = c_zone if min(i, steps - i) < kz else lift
            value[i] = margin[i] if offset[i] == 0.0 else margin[i] + offset[i]
        i_min = _first_min(value, 1, steps, False)
        i_max = _first_min(margin, 1, steps, True)
        if i_min < 0:
            counts[k] = -2
            continue
        keep = np.zeros(n, dtype=np.bool_)
        keep[0] = keep[steps] = keep[i_min] = keep[i_max] = True
        obstacles = np.empty(n if has_s else 1)
        j_min = -1
        if has_s:
            for i in range(n):
                obstacles[i] = np.float64(s[rows[i], cols[i]])
            over = np.empty(n)
            for i in range(n):
                over[i] = limit[i] - obstacles[i]
                if offset[i] != 0.0:
                    over[i] += offset[i]
            j_min = _first_min(over, 1, steps, False)  # -1: no surface data between the anchors
            if j_min >= 0:
                keep[j_min] = True
                small[k, 2], small[k, 3] = j_min / steps * length, over[j_min]
        if j_min < 0:
            small[k, 2], small[k, 3] = np.nan, np.nan
        # np.linspace(0, steps, min(max_points, steps + 1)).round()
        num = min(max_points, n)
        if num == 1:
            keep[0] = True
        elif num > 1:
            step = np.float64(steps) / (num - 1)
            for i in range(num - 1):
                keep[int(np.rint(np.float64(i) * step))] = True
            keep[steps] = True
        small[k, 0], small[k, 1] = i_min / steps * length, value[i_min]
        small[k, 4], small[k, 5] = i_max / steps * length, margin[i_max] + fall  # helpers.webbing_height
        # Water and filled gaps: flags at the points kept, metres over the pixels between the anchors
        on_water = on_filled = 0
        any_water = any_filled = False
        for i in range(n):
            if has_w and water[rows[i], cols[i]]:
                any_water = True
                if 0 < i < steps:
                    on_water += 1
            if has_g and filled[rows[i], cols[i]]:
                any_filled = True
                if 0 < i < steps:
                    on_filled += 1
        small[k, 6] = np.float64(on_water) * length / steps
        small[k, 7] = np.float64(on_filled) * length / steps
        missing = False
        m = starts[k]
        for i in range(n):
            if not keep[i]:
                continue
            d_out[m] = i / steps * length
            z_out[m] = terrain[i]
            missing |= terrain[i] != terrain[i]
            if has_s:
                s_out[m] = obstacles[i]
                missing |= obstacles[i] != obstacles[i]
            if has_w:
                w_out[m] = 1 if water[rows[i], cols[i]] else 0
            if has_g:
                g_out[m] = 1 if filled[rows[i], cols[i]] else 0
            m += 1
        counts[k] = m - starts[k]
        flags[k] = (1 if any_water else 0) | (2 if any_filled else 0) | (4 if missing else 0)


@njit(cache=True)
def _compact(values, starts, offsets, counts):
    """Move the counts[k] values of line k from starts[k] to offsets[k] (offsets[k] <= starts[k])."""
    for k in range(counts.size):
        src, dst = starts[k], offsets[k]
        if src != dst:
            for i in range(counts[k]):
                values[dst + i] = values[src + i]


def _sag_arguments(sag_table):
    """The arrays of a sag.EnvelopeTable for the kernel (linesearch.evaluate_lines' preparation)."""
    if sag_table is None:
        return np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2), np.zeros((2, 2, 2)), np.zeros(2), 0.0
    ratios = sag_table.RATIOS.astype(np.float64)
    return (np.log(sag_table.spans), np.arange(len(sag_table.spans)).astype(np.float64), ratios,
            np.arange(len(ratios)).astype(np.float64), np.ascontiguousarray(sag_table.sag),
            sag_table.fractions.astype(np.float64), float(sag_table.rig.fall_zone))


def line_profiles(a1: np.ndarray, a2: np.ndarray, elevation: np.ndarray, res: float,
                  surface: Optional[np.ndarray] = None, max_points: int = 200, sag_table=None,
                  water: Optional[np.ndarray] = None, filled: Optional[np.ndarray] = None,
                  on_part=None, parts: int = 20, end_zone: float = 0.0, lift: float = 0.0,
                  end_clearance: float = 0.0, zone_cap: float = sh.ZONE_CAP) -> sh.Profiles:
    """helpers.line_profile of the lines a1[k] -> a2[k] ([row, col] each), all at once: the same
    values, as a helpers.Profiles. on_part(n) is called after each of about `parts` parts with
    the lines done in it (progress). Raises ValueError where line_profile would (a line without
    pixels between its anchors, or without data there). end_zone, lift, end_clearance, zone_cap:
    the end zone and the lift, as line_profile's."""
    delta, _ = sh.end_zone_rule(sag_table, end_zone, lift, end_clearance, zone_cap)
    a1 = np.ascontiguousarray(np.asarray(a1).reshape(-1, 2), dtype=np.int64)
    a2 = np.ascontiguousarray(np.asarray(a2).reshape(-1, 2), dtype=np.int64)
    steps = np.abs(a2 - a1).max(axis=1) if len(a1) else np.zeros(0, dtype=np.int64)
    room = np.where(steps >= 2, np.minimum(steps + 1, max(max_points, 0) + 5), 0)  # the most a line keeps
    starts = np.concatenate([[0], np.cumsum(room)]).astype(np.int64)
    total = int(starts[-1])
    d, zs = np.empty(total), np.empty(total)
    ss = np.empty(total if surface is not None else 0)
    ws = np.zeros(total if water is not None else 0, dtype=np.uint8)
    gs = np.zeros(total if filled is not None else 0, dtype=np.uint8)
    counts = np.zeros(len(a1), dtype=np.int64)
    small = np.zeros((len(a1), len(SMALL_DIGITS)))
    flags = np.zeros(len(a1), dtype=np.uint8)
    z = np.asarray(elevation)
    blank = np.zeros((1, 1), dtype=np.bool_)
    s = np.asarray(surface) if surface is not None else np.zeros((1, 1), dtype=z.dtype)
    w = np.ascontiguousarray(water, dtype=np.bool_) if water is not None else blank
    g = np.ascontiguousarray(filled, dtype=np.bool_) if filled is not None else blank
    sag_args = _sag_arguments(sag_table)
    size = max(1, -(-len(a1) // max(parts, 1)))
    for lo in range(0, len(a1), size):
        hi = min(lo + size, len(a1))
        part = slice(lo, hi)
        _profiles(z, s, surface is not None, w, water is not None, g, filled is not None, a1[part], a2[part],
                  float(res), sag_table is not None, *sag_args, int(max_points), float(end_zone), float(lift), delta,
                  float(zone_cap), starts[part], d, zs, ss, ws, gs, counts[part], small[part], flags[part])
        if on_part is not None:
            on_part(hi - lo)
    if (counts == -1).any():
        raise ValueError("attempt to get argmin of an empty sequence")  # np.nanargmin of no pixels
    if (counts == -2).any():
        raise ValueError("All-NaN slice encountered")
    # Only the points kept, moved to the front in place (a line keeps fewer than its room when
    # it is thinned), then rounded as line_profile rounds them, part by part: the arrays of
    # all points are never copied, so the peak stays near what the profiles hold
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    kept = int(offsets[-1])
    for values, digits in ((d, 1), (zs, 2), (ss, 2), (ws, None), (gs, None)):
        if not values.size:
            continue
        if kept < total:
            _compact(values, starts, offsets, counts)
            values.resize(kept, refcheck=False)
        if digits is not None:
            for lo in range(0, kept, ROUND_PART):
                values[lo:lo + ROUND_PART] = rn.round_floats(values[lo:lo + ROUND_PART], digits)
    for k, digits in enumerate(SMALL_DIGITS):
        small[:, k] = np.round(small[:, k], digits) if k in NUMPY_ROUNDED else rn.round_floats(small[:, k], digits)
    zone, lifted = None, None
    if end_zone or lift:  # line_profile's "zone" (min(end_zone, zone_cap * length) to 0.1 m) and "lift"
        lengths = np.hypot(*(a2 - a1).T.astype(np.float64)) * float(res)
        zone, lifted = rn.round_floats(np.minimum(float(end_zone), zone_cap * lengths), 1), float(lift)
    return sh.Profiles(offsets, d, zs, ss if surface is not None else None, ws if water is not None else None,
                       gs if filled is not None else None, small, flags, zone, lifted)
