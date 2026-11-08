"""The tile counter's kernels (numba): countcube.TileCounter's engine "numba".

A tile's lines go into hash tables instead of being sorted part by part: the lines' keys (word A, word
B) with their counts, the spots by (id, border and partner) with their merged records, and the anchors'
pixels with their lon, lat and clusters (each pixel through pyproj once, by the caller). The tables grow
by doubling; a kernel stops before a table passes half full and the caller grows it and goes on. The
counts are those of the numpy engine, byte for byte: the same bins (comparisons with the edges), the
same first anchor by (lon, lat), the same spot ids and merge (countcube._MERGED), sorted at the end.

Imported by countcube.TileCounter on its first part only: the web process imports countcube, never
this module (numba).
"""
import numpy as np
from numba import njit

import countcube as cc

EMPTY = np.int64(-1)
MAX_LOAD = 0.5  # a table is grown before it passes this share of its slots
GROW_LINES = 1 << 16  # the first sizes of the tables
GROW_SPOTS = 1 << 16
GROW_PIXELS = 1 << 16

# The kernels' constants as arrays (numba reads module globals as compile-time constants; arrays are passed)
EDGES = np.zeros((len(cc.DIMS3), 5), dtype=np.float64)
AT_MOST = np.zeros(len(cc.DIMS3), dtype=np.bool_)
SHIFTS = np.zeros(len(cc.DIMS3), dtype=np.int64)
IN_B = np.zeros(len(cc.DIMS3), dtype=np.bool_)
for _k, _name in enumerate(cc.DIMS3):
    assert len(cc.EDGES[_name]) == 5, _name
    EDGES[_k] = cc.EDGES[_name]
    AT_MOST[_k] = cc.KINDS[_name] == "at_most"
    IN_B[_k] = _name in cc.B_SHIFT
    SHIFTS[_k] = cc.B_SHIFT[_name] if IN_B[_k] else cc.SHIFT[_name]
LENGTH_EDGES = np.asarray(cc.LENGTH_EDGES, dtype=np.float64)
assert tuple(cc.DIMS3[4:]) == tuple(cc.B_FIELDS)


@njit(cache=True, inline="always")
def _mix(a, b):
    """A 64-bit hash of two int64 (splitmix64's finaliser over a·φ + b)."""
    x = np.uint64(a) * np.uint64(0x9E3779B97F4A7C15) + np.uint64(b)
    x ^= x >> np.uint64(30)
    x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    return x


@njit(cache=True)
def pixel_lookup(codes, keys, values, out):
    """out[t]: the value index of pixel code codes[t] in the pixel table (keys, values), -1 when it is
    not there; returns how many are not."""
    mask = np.uint64(len(keys) - 1)
    missing = 0
    for t in range(len(codes)):
        code = codes[t]
        slot = _mix(code, 0) & mask
        while True:
            key = keys[slot]
            if key == code:
                out[t] = values[slot]
                break
            if key == -1:
                out[t] = -1
                missing += 1
                break
            slot = (slot + np.uint64(1)) & mask
    return missing


@njit(cache=True)
def pixel_insert(codes, first, keys, values):
    """Insert distinct codes (not in the table) with the value indices first, first + 1, ...: the table
    must have room for them below MAX_LOAD (the caller grows it)."""
    mask = np.uint64(len(keys) - 1)
    for t in range(len(codes)):
        slot = _mix(codes[t], 0) & mask
        while keys[slot] != -1:
            slot = (slot + np.uint64(1)) & mask
        keys[slot] = codes[t]
        values[slot] = first + t


@njit(cache=True)
def select(a1, a2, length, width, left, top, res, core, has_core, lo, hi, last, kept, codes1, codes2):
    """The lines a tile counts (TileCounter's rule: the length within lo, hi (<= hi when last) and the
    first anchor in pixel order, the smaller x then y, in core): their indices into kept and their
    anchors' pixel codes (row * width + col) into codes1, codes2; returns how many."""
    k = 0
    for t in range(len(length)):
        n = length[t]
        if not (n >= lo and ((n <= hi) if last else (n < hi))):
            continue
        if has_core:
            x1 = left + (a1[t, 1] + 0.5) * res
            y1 = top - (a1[t, 0] + 0.5) * res
            x2 = left + (a2[t, 1] + 0.5) * res
            y2 = top - (a2[t, 0] + 0.5) * res
            if x1 < x2 or (x1 == x2 and y1 <= y2):
                fx, fy = x1, y1
            else:
                fx, fy = x2, y2
            if not (fx >= core[0] and fx < core[2] and fy >= core[1] and fy < core[3]):
                continue
        kept[k] = t
        codes1[k] = a1[t, 0] * width + a1[t, 1]
        codes2[k] = a2[t, 0] * width + a2[t, 1]
        k += 1
    return k


@njit(cache=True, inline="always")
def _low(a, b):
    """np.minimum: NaN when either is."""
    if a != a or b != b:
        return np.nan
    return a if a < b else b


@njit(cache=True, inline="always")
def _high(a, b):
    """np.maximum: NaN when either is."""
    if a != a or b != b:
        return np.nan
    return a if a > b else b


@njit(cache=True, inline="always")
def _bin(value, edges, k, at_most):
    """countcube._bins8 of one value."""
    if value != value:
        return 7
    b = 0
    if at_most:
        for e in range(5):
            if value > edges[k, e]:
                b += 1
    else:
        for e in range(1, 5):
            if value >= edges[k, e]:
                b += 1
    return b


@njit(cache=True)
def count(start, kept, idx1, idx2, lon, lat, cx, cy,
          length, clearance, clearance_nmpt, height_max, height_mean, high_pct, angle1, angle2, prom1, prom2,
          drop1, drop2, elev_a1, elev_a2, water_px, lift_needed, lift_no_zone, border, partner, res,
          edges, at_most, shifts, in_b, length_edges, merged,
          line_a, line_b, line_n, line_used, spot_id, spot_bp, spot_flags, spot_bins, spot_used, used):
    """Count the kept lines from index start: each line's key into the lines' table and its spot into
    the spots' table (TileCounter's rules; countcube.line_records' bins, cluster_spot_ids, _merge_bins).
    used[0], used[1]: the lines' and spots' entries. Returns the index it stopped at: len(kept) when
    done, before when a table would pass MAX_LOAD (grown by the caller, then called again from there)."""
    line_mask = np.uint64(len(line_a) - 1)
    spot_mask = np.uint64(len(spot_id) - 1)
    line_limit = int(len(line_a) * 0.5)
    spot_limit = int(len(spot_id) * 0.5)
    has_lift_needed = len(lift_needed) > 0
    has_lift_no_zone = len(lift_no_zone) > 0
    has_border = len(border) > 0
    has_partner = len(partner) > 0
    bins = np.empty(15, dtype=np.int64)
    for t in range(start, len(kept)):
        if used[0] + 1 > line_limit or used[1] + 1 > spot_limit:
            return t
        r = kept[t]
        i1, i2 = idx1[t], idx2[t]
        # the cell: the first anchor by (lon, lat); the spot: the clusters, p the smaller (cx, cy)
        lo1, la1, lo2, la2 = lon[i1], lat[i1], lon[i2], lat[i2]
        if lo1 < lo2 or (lo1 == lo2 and la1 <= la2):
            ci, cj = cx[i1] // 20, cy[i1] // 20
        else:
            ci, cj = cx[i2] // 20, cy[i2] // 20
        if ci > 65535 or cj > 65535:
            raise ValueError("a cell lies outside the cube: check the country's origin")
        x1, y1, x2, y2 = cx[i1], cy[i1], cx[i2], cy[i2]
        if x1 < x2 or (x1 == x2 and y1 <= y2):
            px, py, qx, qy = x1, y1, x2, y2
        else:
            px, py, qx, qy = x2, y2, x1, y1
        dx, dy = qx - px, qy - py
        if dx >= 2048 or dy < -1024 or dy >= 1024:
            raise ValueError("a line spans more than 2047 anchor clusters east-west or 1023 north-south: "
                             "too long for a spot id (keep the band's longest line shorter at this latitude)")
        sid = (px << 42) | (py << 22) | (dx << 11) | (dy + 1024)
        # the flags and the bins (countcube._line_bins)
        water = water_px[r]
        trees = clearance_nmpt[r] <= 0.0
        n = length[r]
        if n != n:
            lb = 8
        else:
            lb = -1
            for e in range(10):
                if length_edges[e] <= n:
                    lb += 1
            lb = min(max(lb, 0), 8)
        flags = (np.int64(1) << (1 if water > 0 else 0)) | (np.int64(1) << (3 if trees else 2)) | (np.int64(1) << (16 + lb))
        bp = 0
        if has_border:
            bp |= border[r] & 3
        if has_partner:
            bp |= (partner[r] & 7) << 2
        flags |= np.int64(bp) << 25
        e1, e2 = elev_a1[r], elev_a2[r]
        bins[0] = _bin(height_max[r], edges, 0, at_most[0])
        bins[1] = _bin(clearance[r], edges, 1, at_most[1])
        bins[2] = _bin(_high(angle1[r], angle2[r]), edges, 2, at_most[2])
        bins[3] = _bin(_low(prom1[r], prom2[r]), edges, 3, at_most[3])
        bins[4] = _bin(water * res, edges, 4, at_most[4])
        bins[5] = _bin(_low(e1, e2), edges, 5, at_most[5])
        bins[6] = _bin(_high(e1, e2), edges, 6, at_most[6])
        bins[7] = _bin(height_mean[r], edges, 7, at_most[7])
        bins[8] = _bin(_high(prom1[r], prom2[r]), edges, 8, at_most[8])
        bins[9] = _bin(_low(drop1[r], drop2[r]), edges, 9, at_most[9])
        bins[10] = _bin(high_pct[r], edges, 10, at_most[10])
        bins[11] = _bin(abs(e1 - e2), edges, 11, at_most[11])
        bins[12] = _bin(clearance_nmpt[r], edges, 12, at_most[12])
        bins[13] = _bin(lift_needed[r] if has_lift_needed else np.nan, edges, 13, at_most[13])
        bins[14] = _bin(lift_no_zone[r] if has_lift_no_zone else np.nan, edges, 14, at_most[14])
        word_a = flags
        word_b = np.int64(0)
        for k in range(15):
            if in_b[k]:
                word_b |= bins[k] << shifts[k]
            else:
                word_a |= bins[k] << shifts[k]
        key_a = (ci << 46) | (cj << 30) | word_a
        # the line's key
        slot = _mix(key_a, word_b) & line_mask
        while True:
            if not line_used[slot]:
                line_used[slot] = True
                line_a[slot], line_b[slot], line_n[slot] = key_a, word_b, 1
                used[0] += 1
                break
            if line_a[slot] == key_a and line_b[slot] == word_b:
                line_n[slot] += 1
                break
            slot = (slot + np.uint64(1)) & line_mask
        # the spot: the flags ORed, each bin's merged value the largest (countcube._MERGED)
        slot = _mix(sid, bp) & spot_mask
        while True:
            if not spot_used[slot]:
                spot_used[slot] = True
                spot_id[slot], spot_bp[slot], spot_flags[slot] = sid, bp, flags & 0x1FF000F
                for k in range(15):
                    spot_bins[slot, k] = merged[k, bins[k]]
                used[1] += 1
                break
            if spot_id[slot] == sid and spot_bp[slot] == bp:
                spot_flags[slot] |= flags & 0x1FF000F
                for k in range(15):
                    m = merged[k, bins[k]]
                    if m > spot_bins[slot, k]:
                        spot_bins[slot, k] = m
                break
            slot = (slot + np.uint64(1)) & spot_mask
    return len(kept)


@njit(cache=True)
def rehash_lines(a, b, n, used, new_a, new_b, new_n, new_used):
    mask = np.uint64(len(new_a) - 1)
    for s in range(len(a)):
        if used[s]:
            slot = _mix(a[s], b[s]) & mask
            while new_used[slot]:
                slot = (slot + np.uint64(1)) & mask
            new_used[slot] = True
            new_a[slot], new_b[slot], new_n[slot] = a[s], b[s], n[s]


@njit(cache=True)
def rehash_spots(ids, bps, flags, bins, used, new_ids, new_bps, new_flags, new_bins, new_used):
    mask = np.uint64(len(new_ids) - 1)
    for s in range(len(ids)):
        if used[s]:
            slot = _mix(ids[s], bps[s]) & mask
            while new_used[slot]:
                slot = (slot + np.uint64(1)) & mask
            new_used[slot] = True
            new_ids[slot], new_bps[slot], new_flags[slot] = ids[s], bps[s], flags[s]
            new_bins[slot] = bins[s]


assert cc.OR_MASK == 0x1FF000F
assert cc.VALUE_COLUMNS == ("length", "clearance", "clearance_nmpt", "height_max", "height_mean", "high_pct", "angle1",
                            "angle2", "prom1", "prom2", "drop1", "drop2", "elev_a1", "elev_a2")


class Tables:
    """A tile's hash tables: lines, spots and the anchors' pixels (with their lon, lat and clusters)."""

    def __init__(self):
        self.used = np.zeros(2, dtype=np.int64)
        self._lines(GROW_LINES)
        self._spots(GROW_SPOTS)
        self.pixel_keys = np.full(GROW_PIXELS, -1, dtype=np.int64)
        self.pixel_values = np.zeros(GROW_PIXELS, dtype=np.int64)
        self.pixels = 0
        self.lon = np.zeros(GROW_PIXELS, dtype=np.float64)
        self.lat = np.zeros(GROW_PIXELS, dtype=np.float64)
        self.cx = np.zeros(GROW_PIXELS, dtype=np.int64)
        self.cy = np.zeros(GROW_PIXELS, dtype=np.int64)

    def _lines(self, size):
        self.line_a = np.zeros(size, dtype=np.int64)
        self.line_b = np.zeros(size, dtype=np.int64)
        self.line_n = np.zeros(size, dtype=np.int64)
        self.line_used = np.zeros(size, dtype=np.bool_)

    def _spots(self, size):
        self.spot_id = np.zeros(size, dtype=np.int64)
        self.spot_bp = np.zeros(size, dtype=np.int64)
        self.spot_flags = np.zeros(size, dtype=np.int64)
        self.spot_bins = np.zeros((size, len(cc.DIMS3)), dtype=np.uint8)
        self.spot_used = np.zeros(size, dtype=np.bool_)

    def grow(self):
        """Double a table that passed MAX_LOAD (or both)."""
        if self.used[0] + 1 > int(len(self.line_a) * MAX_LOAD):
            old = (self.line_a, self.line_b, self.line_n, self.line_used)
            self._lines(2 * len(old[0]))
            rehash_lines(*old, self.line_a, self.line_b, self.line_n, self.line_used)
        if self.used[1] + 1 > int(len(self.spot_id) * MAX_LOAD):
            old = (self.spot_id, self.spot_bp, self.spot_flags, self.spot_bins, self.spot_used)
            self._spots(2 * len(old[0]))
            rehash_spots(*old, self.spot_id, self.spot_bp, self.spot_flags, self.spot_bins, self.spot_used)

    def indices(self, codes: np.ndarray, transform) -> np.ndarray:
        """The value indices of pixel codes; the codes not seen yet go through transform(unique codes) ->
        (lon, lat, cx, cy) first and into the table."""
        out = np.empty(len(codes), dtype=np.int64)
        if not pixel_lookup(codes, self.pixel_keys, self.pixel_values, out):
            return out
        new = np.unique(codes[out < 0])
        lon, lat, cx, cy = transform(new)
        need = self.pixels + len(new)
        if need > len(self.lon):
            size = len(self.lon)
            while size < need:
                size *= 2
            for name in ("lon", "lat", "cx", "cy"):
                old = getattr(self, name)
                grown = np.zeros(size, dtype=old.dtype)
                grown[:self.pixels] = old[:self.pixels]
                setattr(self, name, grown)
        self.lon[self.pixels:need], self.lat[self.pixels:need] = lon, lat
        self.cx[self.pixels:need], self.cy[self.pixels:need] = cx, cy
        if need > len(self.pixel_keys) * MAX_LOAD:
            size = len(self.pixel_keys)
            while need > size * MAX_LOAD:
                size *= 2
            known = self.pixel_keys != -1
            codes_known, values_known = self.pixel_keys[known], self.pixel_values[known]
            self.pixel_keys = np.full(size, -1, dtype=np.int64)
            self.pixel_values = np.zeros(size, dtype=np.int64)
            _insert_values(codes_known, values_known, self.pixel_keys, self.pixel_values)
        pixel_insert(new, self.pixels, self.pixel_keys, self.pixel_values)
        self.pixels = need
        pixel_lookup(codes, self.pixel_keys, self.pixel_values, out)
        return out

    def counts(self):
        """The lines' keys ((n, 2), sorted) and counts, the spots' ids, border and partner, flags and
        merged bins (sorted by id, then border and partner)."""
        used = self.line_used
        a, b, n = self.line_a[used], self.line_b[used], self.line_n[used]
        order = np.lexsort((b, a))
        keys = np.empty((len(order), 2), dtype=np.int64)
        keys[:, 0], keys[:, 1] = a[order], b[order]
        lines = n[order]
        used = self.spot_used
        ids, bps = self.spot_id[used], self.spot_bp[used]
        order = np.lexsort((bps, ids))
        return keys, lines, ids[order], bps[order], self.spot_flags[used][order], self.spot_bins[used][order]


@njit(cache=True)
def _insert_values(codes, values, keys, slots):
    mask = np.uint64(len(keys) - 1)
    for t in range(len(codes)):
        slot = _mix(codes[t], 0) & mask
        while keys[slot] != -1:
            slot = (slot + np.uint64(1)) & mask
        keys[slot] = codes[t]
        slots[slot] = values[t]
