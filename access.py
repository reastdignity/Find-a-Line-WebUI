"""Can a person walk to an anchor? The access mark of three states: can walk, cannot tell, cannot walk.

A port of part P3d's measure (the line-volume study, 2026-11-13; docs/line-volume/spec-search.md section 3), its
constants kept: the user judged its pictures and asked for it as it is (2026-11-15). It reads only the terrain: it
cannot see paths, fences, private land or trees, nor tell rock from grass, so "can walk" means "the ground allows a
walk", and "cannot walk" means "the ground offers none" (an anchor that hangs in the face).

Inputs: the search's filled terrain `z` (float32, NaN without data), its water, the pixels it filled (`filled`: no
data for the walk unless they are water; the search passes its gaps and the shore faces taken from the surface model)
and the resolution in metres. Output: a `uint8` grid of the same shape with an answer for every pixel (`access_grid`,
or `block_grid` in blocks); a line takes its two anchors' pixels from it, the measure's own answer there (an anchor on
a filled pixel or a shore face gets the answer of the data around it, as in the study; none lies on a NaN).

The measure:
- slope: the app's slope (np.gradient, degrees); a pixel beside a NaN along an axis has no slope and is neither
  open nor walkable (a filled gap has heights, so the pixels beside it keep theirs).
- open ground: below OPEN_DEG, not water, with data, in an 8-connected region of such pixels of at least
  OPEN_MIN_M2 (a meadow, a plateau, a field, a valley floor; not a ledge in a face or the top of a pillar).
- walkable ground, strict: slope <= WALK_DEG, not water, with data, not a crest (a pixel that falls away on both
  sides of one axis by more than WALK_DEG over 2 pixels: a knife edge whose middle the grid reads as flat);
  loose: slope <= LOOSE_DEG (scrambling), crests allowed.
- standing ground: a walkable pixel within STAND_M of the anchor, from STAND_BELOW_M below to STAND_ABOVE_M above
  its height (the foot of a wall a metre away does not count).
- the walk: the shortest path over walkable ground (8 neighbours, its length in metres) from open ground, at most
  REACH_M long, to the anchor's standing ground.
- the answers: CAN where the strict walk reaches it (on whole-metre heights also on lightly smoothed heights);
  CANNOT where the loose walk does not reach it and nothing below says the data cannot tell; UNSURE ("cannot tell
  here") otherwise: only the loose walk reaches it (ground of 40 to 50 degrees or a crest: it depends on the person
  and the rock); or the heights are whole metres (WHOLE_METRE_SHARE of a sample) and the strict walk on heights
  smoothed by a Gaussian of SMOOTH_SIGMA_PX pixel gives the other answer; or it is not reached and its loose
  walkable ground comes within REACH_M of the end of the data, so open ground may lie beyond. The end of the data:
  walkable pixels on the grid's edge or beside a pixel without data (8 neighbours); beside a filled gap that is its
  whole rim, beside a NaN only a diagonal neighbour (the pixels across an axis have no slope), as in the study.
- water: the app's water; on heights that are not whole metres also lakes held as flat data (FLAT_WATER_*: flat
  regions whose heights spread little).
- the alpine variant (on by default; `alpine=False` gives the study's main measure): "cannot walk" becomes "cannot
  tell" where open ground is under ALPINE_SHARE of the land (pixels with data, not water) in the square of
  +-OPEN_AROUND_M around the pixel: on alpine walls the measure is not sure enough to say "cannot".

Locality: every distance is in metres and bounded, so a window with a margin of MARGIN_M (and 6 pixels) around a
core gives the whole grid's answers in the core, except for the grid-wide judgements: the whole-metre test (a sample
of the grid), the flat lakes' and the open ground's regions (their size), and on whole metres the open ground's
regions on the smoothed heights. The search (search._access_grid) computes the grid at once when it fits its memory;
otherwise `block_grid` makes those judgements once on the whole grid, strip by strip, their masks memory-mapped, and
every block from its window with them: the whole grid's answers, whatever the blocks (0 pixels differed on the Gozo
coast, 126 Mpx). The search's tiles read their windows of that one grid.

Results never depend on the number of threads: the walk is serial, and the parallel kernel writes each pixel's own
answer. The study's numbers: about 0.3 s per megapixel (indicative).
"""
import math
import os

import numpy as np
from numba import njit, prange
from scipy import ndimage

CAN, UNSURE, CANNOT = 2, 1, 0  # the grid's values: can walk, cannot tell, cannot walk
NAMES = {CAN: "can walk", UNSURE: "cannot tell", CANNOT: "cannot walk"}
OPEN_DEG = 30.0  # open ground: slope below this (degrees)
OPEN_MIN_M2 = 10000.0  # open ground: its connected region is at least this large (1 ha)
WALK_DEG = 40.0  # walkable ground, strict: slope at most this; also the crest's fall on both sides
LOOSE_DEG = 50.0  # walkable ground, loose (scrambling): slope at most this, crests allowed
STAND_M = 3.0  # standing ground: within this distance of the anchor
STAND_BELOW_M, STAND_ABOVE_M = 2.0, 3.0  # standing ground: its height from this much below to this much above
REACH_M = 500.0  # the longest walk from open ground (measured by the study: little changes past 500 m)
WHOLE_METRE_SHARE = 0.9  # heights are whole metres when this share of a sample is
WHOLE_METRE_SAMPLE = 200000  # about this many pixels in that sample
SMOOTH_SIGMA_PX = 1.0  # the light smoothing of whole-metre heights (a Gaussian, in pixels)
FLAT_WATER_DEG = 3.0  # a lake held as data: slope below this,
FLAT_WATER_MIN_M2 = 2000.0  # in a region at least this large,
FLAT_WATER_SPREAD_M = 0.3  # whose heights spread (p95 - p5) at most this
OPEN_AROUND_M = 250.0  # the alpine variant's square: +- this around the pixel
ALPINE_SHARE = 0.05  # the alpine variant: "cannot walk" becomes "cannot tell" below this share of open ground
MARGIN_M = REACH_M + STAND_M + 30.0  # a window's margin that gives the whole grid's answers in its core

_EIGHT = np.ones((3, 3), bool)


def slope_deg(z: np.ndarray, res: float) -> np.ndarray:
    """The slope in degrees (float32; NaN next to a pixel without data)."""
    gy, gx = np.gradient(np.asarray(z, np.float32), res)
    np.hypot(gx, gy, out=gx)
    return np.degrees(np.arctan(gx))


def whole_metres(heights: np.ndarray) -> bool:
    """Whether the heights (a flat array of the pixels with data) are whole metres: WHOLE_METRE_SHARE of a sample."""
    if not heights.size:
        return False
    sample = heights[:: max(1, heights.size // WHOLE_METRE_SAMPLE)]
    return bool(np.mean(sample == np.round(sample)) >= WHOLE_METRE_SHARE)


def flat_water(z: np.ndarray, slope: np.ndarray, res: float) -> np.ndarray:
    """Lakes held as flat data: 8-connected regions below FLAT_WATER_DEG of at least FLAT_WATER_MIN_M2 whose heights
    spread (p95 - p5) at most FLAT_WATER_SPREAD_M."""
    flat = np.isfinite(z) & (slope < FLAT_WATER_DEG)
    labels, n = ndimage.label(flat, structure=_EIGHT)
    if n == 0:
        return np.zeros(z.shape, bool)
    area = np.bincount(labels.ravel(), minlength=n + 1) * res * res
    big = np.nonzero(area >= FLAT_WATER_MIN_M2)[0]
    big = big[big > 0]
    keep = np.zeros(n + 1, bool)
    if len(big):
        lab = labels.ravel()
        sel = np.isin(lab, big)
        zl, ll = z.ravel()[sel], lab[sel]
        order = np.argsort(ll, kind="stable")
        zl, ll = zl[order], ll[order]
        starts, ends = np.searchsorted(ll, big), np.searchsorted(ll, big, side="right")
        for b, s0, s1 in zip(big, starts, ends):
            v = zl[s0:s1]
            if np.percentile(v, 95) - np.percentile(v, 5) <= FLAT_WATER_SPREAD_M:
                keep[b] = True
    return keep[labels]


def crest(z: np.ndarray, res: float, deg: float = WALK_DEG) -> np.ndarray:
    """Pixels that fall away on both sides of one axis (of four) by more than `deg` over 2 pixels."""
    h, w = z.shape
    out = np.zeros(z.shape, bool)
    zz = np.where(np.isfinite(z), z, np.inf).astype(np.float32)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        lim = 2 * res * np.hypot(dr, dc) * np.tan(np.radians(deg))
        a = np.full(z.shape, np.inf, np.float32)
        b = np.full(z.shape, np.inf, np.float32)
        r0, r1 = max(0, 2 * dr), h + min(0, 2 * dr)
        c0, c1 = max(0, 2 * dc), w + min(0, 2 * dc)
        # a[r, c] = z[r - 2dr, c - 2dc]; b[r, c] = z[r + 2dr, c + 2dc]
        a[r0:r1, c0:c1] = zz[r0 - 2 * dr:r1 - 2 * dr, c0 - 2 * dc:c1 - 2 * dc]
        rb0, rb1 = max(0, -2 * dr), h - max(0, 2 * dr)
        cb0, cb1 = max(0, -2 * dc), w - max(0, 2 * dc)
        b[rb0:rb1, cb0:cb1] = zz[rb0 + 2 * dr:rb1 + 2 * dr, cb0 + 2 * dc:cb1 + 2 * dc]
        with np.errstate(invalid="ignore"):  # inf - inf beside no data: NaN, not a crest
            out |= ((zz - a) > lim) & ((zz - b) > lim) & np.isfinite(a) & np.isfinite(b)
    return out & np.isfinite(z)


def _open_ground(slope: np.ndarray, water: np.ndarray, data: np.ndarray, res: float) -> np.ndarray:
    g = (slope < OPEN_DEG) & ~water & data
    labels, n = ndimage.label(g, structure=_EIGHT)
    area = np.bincount(labels.ravel(), minlength=n + 1) * res * res
    big = area >= OPEN_MIN_M2
    big[0] = False
    return big[labels]


@njit(cache=True)
def _sift_up(heap, pos, dist, j):
    node = heap[j]
    d = dist[node]
    while j > 0:
        p = (j - 1) // 2
        if dist[heap[p]] <= d:
            break
        heap[j] = heap[p]
        pos[heap[j]] = j
        j = p
    heap[j] = node
    pos[node] = j


@njit(cache=True)
def _walk(walk, source, res, limit):
    """Whether the shortest path over walkable pixels from a source pixel (walkable too) is at most `limit` metres
    long (8 neighbours, steps of res and res * sqrt(2), summed in float64 from the source as the study's walk).
    Dijkstra with an indexed heap: a pixel's distance is the least sum over its paths whatever the order of equal
    keys, so the answer is the study's. A source whose walkable neighbours are all sources starts nowhere new and
    stays out of the heap."""
    h, w = walk.shape
    n = h * w
    wf = walk.ravel()
    sf = source.ravel()
    dist = np.full(n, np.inf)
    heap = np.empty(n, np.int32)
    pos = np.full(n, -1, np.int32)
    dr = np.array([-1, -1, -1, 0, 0, 1, 1, 1])
    dc = np.array([-1, 0, 1, -1, 1, -1, 0, 1])
    step = np.array([1.4142135623730951, 1.0, 1.4142135623730951, 1.0, 1.0, 1.4142135623730951, 1.0,
                     1.4142135623730951]) * res
    for i in range(n):
        if sf[i] and wf[i]:
            dist[i] = 0.0
    size = 0
    for i in range(n):
        if dist[i] != 0.0:
            continue
        r = i // w
        c = i - r * w
        for k in range(8):
            rr = r + dr[k]
            cc = c + dc[k]
            if rr < 0 or rr >= h or cc < 0 or cc >= w:
                continue
            q = rr * w + cc
            if wf[q] and dist[q] != 0.0:
                heap[size] = i  # all keys are 0: any order is a heap
                pos[i] = size
                size += 1
                break
    while size > 0:
        i = heap[0]
        pos[i] = -2  # settled
        size -= 1
        if size > 0:
            last = heap[size]
            dl = dist[last]
            j = 0
            while True:
                lc = 2 * j + 1
                if lc >= size:
                    break
                m = lc
                if lc + 1 < size and dist[heap[lc + 1]] < dist[heap[lc]]:
                    m = lc + 1
                if dist[heap[m]] < dl:
                    heap[j] = heap[m]
                    pos[heap[j]] = j
                    j = m
                else:
                    break
            heap[j] = last
            pos[last] = j
        d = dist[i]
        r = i // w
        c = i - r * w
        for k in range(8):
            rr = r + dr[k]
            cc = c + dc[k]
            if rr < 0 or rr >= h or cc < 0 or cc >= w:
                continue
            q = rr * w + cc
            if not wf[q]:
                continue
            nd = d + step[k]
            if nd < dist[q] and nd <= limit:
                dist[q] = nd
                if pos[q] < 0:  # new, or settled and shorter after all (as the study's heap, which pushes again)
                    heap[size] = q
                    pos[q] = size
                    size += 1
                _sift_up(heap, pos, dist, pos[q])
    out = np.empty(n, np.bool_)
    for i in range(n):
        out[i] = dist[i] <= limit
    return out.reshape(h, w)


@njit(parallel=True, cache=True)
def _stands_near(reached, walk, z, odr, odc, below, above):
    """Per pixel: a reached walkable pixel at one of the offsets (the disc of STAND_M) whose height is from `below`
    under to `above` over the pixel's (float32 difference, as the study's). Each pixel writes its own answer."""
    h, w = z.shape
    out = np.zeros((h, w), np.bool_)
    for r in prange(h):
        for c in range(w):
            zp = z[r, c]
            for k in range(odr.size):
                rr = r + odr[k]
                cc = c + odc[k]
                if rr < 0 or rr >= h or cc < 0 or cc >= w:
                    continue
                if not (walk[rr, cc] and reached[rr, cc]):
                    continue
                dz = z[rr, cc] - zp
                if dz >= -below and dz <= above:
                    out[r, c] = True
                    break
    return out


def _offsets(res: float):
    """The offsets (rows, columns) within STAND_M of a pixel."""
    m = int(np.floor(STAND_M / res))
    rows, cols = [], []
    for dr in range(-m, m + 1):
        for dc in range(-m, m + 1):
            if res * np.hypot(dr, dc) <= STAND_M:
                rows.append(dr)
                cols.append(dc)
    return np.array(rows, np.int64), np.array(cols, np.int64)


def _reaches(walk: np.ndarray, source: np.ndarray, z: np.ndarray, res: float, offsets) -> np.ndarray:
    """Per pixel: the walk from `source` over `walk` of at most REACH_M reaches its standing ground."""
    walk = np.ascontiguousarray(walk)
    reached = _walk(walk, np.ascontiguousarray(source), float(res), float(REACH_M))
    return _stands_near(reached, walk, z, offsets[0], offsets[1], STAND_BELOW_M, STAND_ABOVE_M)


def _smoothed(z: np.ndarray, data: np.ndarray) -> np.ndarray:
    """The lightly smoothed heights of whole metres: a pixel without data takes its nearest data pixel's height
    (local: the same in every window), a Gaussian of SMOOTH_SIGMA_PX, NaN again without data."""
    near = ndimage.distance_transform_edt(~data, return_distances=False, return_indices=True)
    zs = ndimage.gaussian_filter(z[near[0], near[1]].astype(np.float32), SMOOTH_SIGMA_PX)
    del near
    return np.where(data, zs, np.nan).astype(np.float32)


WALK_PX_MAX = np.iinfo(np.int32).max  # the walk indexes its grid with int32


def _check_size(pixels: int):
    """A grid (or a block's window) of WALK_PX_MAX pixels or more is refused: the walk's indices are int32."""
    if pixels >= WALK_PX_MAX:
        raise ValueError("grid too large for the access measure's walk")


def access_grid(z: np.ndarray, water, res: float, filled=None, alpine: bool = True) -> np.ndarray:
    """The answer for every pixel of the grid (uint8: CANNOT 0, UNSURE 1, CAN 2), the grid in memory at once.

    z: the filled terrain (float32, NaN without data); water: bool or None; res: metres per pixel; filled: the
    pixels filled from a coarser model (bool or None); alpine: the alpine variant (the user's choice: on)."""
    z = np.ascontiguousarray(z, np.float32)
    _check_size(z.size)
    water = np.zeros(z.shape, bool) if water is None else np.asarray(water, bool)
    data = np.isfinite(z)
    if filled is not None:
        data &= ~(np.asarray(filled, bool) & ~water)
    s = slope_deg(z, res)
    wm = whole_metres(z[data])
    if not wm:
        water = water | flat_water(z, s, res)
    s = np.where(data, s, 90.0)
    og = _open_ground(s, water, data, res)
    return _answers(z, water, data, res, wm, og, alpine, s=s)


def _answers(z: np.ndarray, water: np.ndarray, data: np.ndarray, res: float, wm: bool, og: np.ndarray, alpine: bool,
             og2=None, s=None) -> np.ndarray:
    """The answers of a grid or a block's window, the grid-wide judgements given: wm (the heights are whole metres),
    water (with the flat lakes on float heights), og (the open ground) and, on whole metres, og2 (the open ground on
    the smoothed heights; None: computed here, as on a whole grid). s: the slope with 90 where there is no data."""
    if s is None:
        s = np.where(data, slope_deg(z, res), 90.0)
    offsets = _offsets(res)
    strict = (s <= WALK_DEG) & ~water & data & ~crest(z, res, WALK_DEG)
    loose = (s <= LOOSE_DEG) & ~water & data
    del s
    share = None
    if alpine:
        big = 2 * int(round(OPEN_AROUND_M / res)) + 1
        num = ndimage.uniform_filter(og.astype(np.float32), size=big, mode="constant", cval=0.0)
        den = ndimage.uniform_filter((data & ~water).astype(np.float32), size=big, mode="constant", cval=0.0)
        share = num / np.maximum(den, 1e-6)
        del num, den
    can = _reaches(strict, og, z, res, offsets)
    del strict
    reach_loose = _reaches(loose, og, z, res, offsets)
    del og
    # the end of the data: loose walkable pixels next to a pixel without data or on the grid's (window's) border
    edge = ndimage.binary_dilation(~data, structure=_EIGHT) & loose
    edge[0, :] |= loose[0, :]
    edge[-1, :] |= loose[-1, :]
    edge[:, 0] |= loose[:, 0]
    edge[:, -1] |= loose[:, -1]
    near_edge = _reaches(loose, edge, z, res, offsets)
    del loose, edge
    smooth_disagree = np.zeros(z.shape, bool)
    if wm:
        zs = _smoothed(z, data)
        ss = np.where(data, slope_deg(zs, res), 90.0)
        strict2 = (ss <= WALK_DEG) & ~water & data & ~crest(zs, res, WALK_DEG)
        if og2 is None:
            og2 = _open_ground(ss, water, data, res)
        del ss
        smooth_disagree = _reaches(strict2, og2, zs, res, offsets) != can
        del strict2, og2, zs
    out = np.full(z.shape, UNSURE, np.uint8)
    out[can & ~smooth_disagree] = CAN
    out[~reach_loose & ~near_edge & ~smooth_disagree] = CANNOT
    if share is not None:
        out[(out == CANNOT) & (share < ALPINE_SHARE)] = UNSURE
    return out


def at(grid: np.ndarray, pixels) -> np.ndarray:
    """The answers at `pixels` (int (n, 2): rows, columns); a pixel outside the grid is refused (ValueError), never
    read from the other end of a row as a negative index would be."""
    pixels = np.asarray(pixels, np.int64).reshape(-1, 2)
    h, w = grid.shape
    if ((pixels < 0) | (pixels >= (h, w))).any():
        raise ValueError("a pixel outside the access grid")
    return grid[pixels[:, 0], pixels[:, 1]]


# --- The grid in blocks (the search's: docs/line-volume/spec-search.md 3.2, the user's choice of 2026-11-15) ---

STRIP_PX = 4_000_000  # pixels of a strip of the grid-wide pass
HALO = 16  # rows around a strip for the smoothed heights (the nearest data pixel, the Gaussian's 4 pixels, the slope)


def margin_px(res: float) -> int:
    """A block's window reaches this many pixels beyond the block: MARGIN_M and 6 pixels (the window margin that gives
    the whole grid's answers in its core up to the coarsest grids the search makes)."""
    return int(math.ceil((MARGIN_M + 6 * res) / res))


def _strips(h: int, w: int):
    rows = max(64, STRIP_PX // max(w, 1))
    for r0 in range(0, h, rows):
        yield r0, min(h, r0 + rows)


def _data_rows(z, water, filled, r0: int, r1: int):
    """Rows r0..r1 of the heights (float32, in memory) and of the pixels with data (access_grid's `data`)."""
    zz = np.asarray(z[r0:r1], np.float32)
    data = np.isfinite(zz)
    if filled is not None:
        wet = np.asarray(water[r0:r1], bool) if water is not None else np.zeros(zz.shape, bool)
        data &= ~(np.asarray(filled[r0:r1], bool) & ~wet)
    return zz, data


def _slope_rows(z, r0: int, r1: int, res: float) -> np.ndarray:
    """slope_deg of rows r0..r1 of the whole grid (a row around them: the same central differences)."""
    a, b = max(0, r0 - 1), min(z.shape[0], r1 + 1)
    return slope_deg(np.asarray(z[a:b], np.float32), res)[r0 - a:r1 - a]


def _new(path: str, shape, dtype):
    return np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=shape)


def _remove(path: str):
    """A grid of the work folder, removed right after its views are closed (Windows: until then it is held)."""
    import gc
    import time
    gc.collect()
    for _ in range(50):
        try:
            os.remove(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.1)


def _region_areas(mask_path: str, labels_path: str, shape, res: float):
    """The 8-connected regions of a memory-mapped mask: their labels (int32, memory-mapped), their count and their
    pixels (by label)."""
    mask = np.load(mask_path, mmap_mode="r")
    labels = _new(labels_path, shape, np.int32)
    n = ndimage.label(mask, structure=_EIGHT, output=labels)
    del mask
    count = np.zeros(n + 1, np.int64)
    for r0, r1 in _strips(*shape):
        count += np.bincount(np.asarray(labels[r0:r1]).ravel(), minlength=n + 1)
    return labels, n, count


def _whole_metres_rows(z, water, filled) -> bool:
    """whole_metres(z[data]) of the whole grid, strip by strip: the count of the pixels with data, then every k-th of
    them in the same order (the very sample of whole_metres)."""
    h, w = z.shape
    n = sum(int(_data_rows(z, water, filled, r0, r1)[1].sum()) for r0, r1 in _strips(h, w))
    if not n:
        return False
    step = max(1, n // WHOLE_METRE_SAMPLE)
    seen, picked = 0, []
    for r0, r1 in _strips(h, w):
        zz, data = _data_rows(z, water, filled, r0, r1)
        v = zz[data]
        picked.append(v[(-seen) % step::step])
        seen += len(v)
    sample = np.concatenate(picked)
    return bool(np.mean(sample == np.round(sample)) >= WHOLE_METRE_SHARE)


GATHER_PX = 4_000_000  # heights of flat regions gathered at a time for their exact percentiles (a larger region alone)


def _region_bounds(labels, z, big: np.ndarray, n: int):
    """The lowest and highest height of each region marked in `big` (float64, by label), strip by strip; every strip's
    labels copied out of the map, so no view of it outlives the loop (Windows could not remove the file)."""
    lo, hi = np.full(n + 1, np.inf), np.full(n + 1, -np.inf)
    for r0, r1 in _strips(*z.shape):
        lab = np.array(labels[r0:r1]).ravel()
        sel = big[lab]
        zz = np.asarray(z[r0:r1], np.float32).ravel()[sel]
        np.minimum.at(lo, lab[sel], zz)
        np.maximum.at(hi, lab[sel], zz)
    return lo, hi


def _batches(regions: np.ndarray, count: np.ndarray):
    """The regions in batches of at most GATHER_PX pixels (a larger region alone), in label order."""
    batch, size = [], 0
    for b in regions.tolist():
        if batch and size + count[b] > GATHER_PX:
            yield np.array(batch)
            batch, size = [], 0
        batch.append(b)
        size += int(count[b])
    if batch:
        yield np.array(batch)


def _spread_flat(labels, z, regions: np.ndarray, count: np.ndarray, keep: np.ndarray):
    """flat_water's test of the regions' heights (p95 - p5 at most FLAT_WATER_SPREAD_M) for `regions`, setting keep:
    a batch's heights gathered into one float32 array, each region's judged in place (np.percentile with
    overwrite_input: no copy; two calls with scalar q, as flat_water, whose spread they give to the last bit) and
    released with its batch."""
    n = len(count) - 1
    for batch in _batches(regions, count):
        sizes = count[batch]
        start = np.concatenate([[0], np.cumsum(sizes)])
        slot = np.full(n + 1, -1, np.int64)
        slot[batch] = np.arange(len(batch))
        heights = np.empty(int(start[-1]), np.float32)
        filled = np.zeros(len(batch), np.int64)
        for r0, r1 in _strips(*z.shape):
            k = slot[np.array(labels[r0:r1]).ravel()]
            sel = k >= 0
            if not sel.any():
                continue
            k = k[sel]
            zz = np.asarray(z[r0:r1], np.float32).ravel()[sel]
            order = np.argsort(k, kind="stable")
            k, zz = k[order], zz[order]
            got = np.bincount(k, minlength=len(batch))
            first = np.cumsum(got) - got  # where each region's pixels begin in this strip's sorted k
            heights[start[k] + filled[k] + np.arange(len(k)) - first[k]] = zz
            filled += got
            del k, zz, order, sel
        for j, b in enumerate(batch.tolist()):
            v = heights[start[j]:start[j + 1]]
            p95 = np.percentile(v, 95, overwrite_input=True)
            if p95 - np.percentile(v, 5, overwrite_input=True) <= FLAT_WATER_SPREAD_M:
                keep[b] = True
        del heights


def _flat_lakes_rows(z, res: float, work: str, out) -> None:
    """flat_water of the whole grid, strip by strip, ORed into `out` (a memory-mapped bool grid): the regions'
    areas by their labels, their spreads from each region's lowest and highest height, the exact percentiles of
    flat_water only for the regions whose highest less lowest is over FLAT_WATER_SPREAD_M (_spread_flat: their
    heights GATHER_PX at a time, a larger region alone)."""
    h, w = z.shape
    flat_path, labels_path = os.path.join(work, "access_flat.npy"), os.path.join(work, "access_flat_labels.npy")
    flat = _new(flat_path, (h, w), bool)
    for r0, r1 in _strips(h, w):
        flat[r0:r1] = np.isfinite(np.asarray(z[r0:r1], np.float32)) & (_slope_rows(z, r0, r1, res) < FLAT_WATER_DEG)
    flat.flush()
    del flat
    labels, n, count = _region_areas(flat_path, labels_path, (h, w), res)
    big = count * res * res >= FLAT_WATER_MIN_M2
    big[0] = False
    lo, hi = _region_bounds(labels, z, big, n)
    keep = big & (hi - lo <= FLAT_WATER_SPREAD_M - 1e-6)  # p95 - p5 lies within the lowest and highest
    unsure = np.flatnonzero(big & ~keep)
    if len(unsure):
        _spread_flat(labels, z, unsure, count, keep)
    for r0, r1 in _strips(h, w):
        out[r0:r1] |= keep[np.array(labels[r0:r1])]
    del labels
    _remove(labels_path)
    _remove(flat_path)


def _open_ground_rows(z, water, filled, wet, res: float, work: str, name: str, smoothed: bool) -> str:
    """_open_ground of the whole grid (on the smoothed heights with `smoothed`), strip by strip, into a memory-mapped
    bool grid of the work folder; wet: the memory-mapped water with the flat lakes. Returns its path."""
    h, w = z.shape
    g_path, labels_path = os.path.join(work, f"access_{name}_g.npy"), os.path.join(work, f"access_{name}_labels.npy")
    g = _new(g_path, (h, w), bool)
    for r0, r1 in _strips(h, w):
        _, data = _data_rows(z, water, filled, r0, r1)
        if smoothed:
            a, b = max(0, r0 - HALO), min(h, r1 + HALO)
            za, da = _data_rows(z, water, filled, a, b)
            s = slope_deg(_smoothed(za, da), res)[r0 - a:r1 - a]
        else:
            s = _slope_rows(z, r0, r1, res)
        s = np.where(data, s, 90.0)
        g[r0:r1] = (s < OPEN_DEG) & ~np.asarray(wet[r0:r1]) & data
    g.flush()
    del g
    labels, n, count = _region_areas(g_path, labels_path, (h, w), res)
    big = count * res * res >= OPEN_MIN_M2
    big[0] = False
    path = os.path.join(work, f"access_{name}.npy")
    out = _new(path, (h, w), bool)
    for r0, r1 in _strips(h, w):
        out[r0:r1] = big[np.asarray(labels[r0:r1])]
    out.flush()
    del out, labels
    _remove(labels_path)
    _remove(g_path)
    return path


def block_grid(z, water, res: float, filled, path: str, work: str, block_px: int, alpine: bool = True,
               on_part=lambda name: None) -> dict:
    """The answers of access_grid for every pixel of a grid too large to hold at once, written into the uint8 grid
    `path` (memory-mapped): the grid-wide judgements once on the whole grid, strip by strip, their masks
    memory-mapped in `work` (the whole-metre sample, the flat lakes on float heights, the open ground on the heights
    and on whole metres on the smoothed heights); then every block of block_px x block_px pixels from its window of
    margin_px(res) around it, by access_grid's own code (_answers) on the windows of those masks. Every other
    distance of the measure is bounded by MARGIN_M, so each block's answers are the whole grid's, whatever the
    blocks' size (tests/test_access_search.py). on_part(name): "grid-wide", then "blocks" (a progress bar's parts).
    Returns the blocks' count and their largest window (pixels)."""
    h, w = z.shape
    margin = margin_px(res)
    block_px = max(1, int(block_px))
    _check_size(min(h, block_px + 2 * margin) * min(w, block_px + 2 * margin))
    os.makedirs(work, exist_ok=True)
    on_part("grid-wide")
    wm = _whole_metres_rows(z, water, filled)
    wet_path = os.path.join(work, "access_water.npy")
    wet = _new(wet_path, (h, w), bool)
    for r0, r1 in _strips(h, w):
        wet[r0:r1] = np.asarray(water[r0:r1], bool) if water is not None else False
    if not wm:
        _flat_lakes_rows(z, res, work, wet)
    wet.flush()
    og_path = _open_ground_rows(z, water, filled, wet, res, work, "og", smoothed=False)
    og2_path = _open_ground_rows(z, water, filled, wet, res, work, "og2", smoothed=True) if wm else None
    og = np.load(og_path, mmap_mode="r")
    og2 = np.load(og2_path, mmap_mode="r") if og2_path else None
    out = _new(path, (h, w), np.uint8)
    on_part("blocks")
    blocks = largest = 0
    for r0 in range(0, h, block_px):
        for c0 in range(0, w, block_px):
            r1, c1 = min(h, r0 + block_px), min(w, c0 + block_px)
            a, b, c, d = max(0, r0 - margin), min(h, r1 + margin), max(0, c0 - margin), min(w, c1 + margin)
            zz = np.array(z[a:b, c:d], np.float32)
            data = np.isfinite(zz)
            if filled is not None:
                dry = np.asarray(water[a:b, c:d], bool) if water is not None else np.zeros(zz.shape, bool)
                data &= ~(np.asarray(filled[a:b, c:d], bool) & ~dry)
            answers = _answers(zz, np.array(wet[a:b, c:d]), data, res, wm, np.array(og[a:b, c:d]), alpine,
                               og2=np.array(og2[a:b, c:d]) if og2 is not None else None)
            out[r0:r1, c0:c1] = answers[r0 - a:r1 - a, c0 - c:c1 - c]
            del zz, data, answers
            blocks += 1
            largest = max(largest, (b - a) * (d - c))
    out.flush()
    del out, wet, og, og2
    for p in (wet_path, og_path, og2_path):
        if p:
            _remove(p)
    return {"blocks": blocks, "window_px": largest, "whole_metres": wm}
