"""
The terrain of a search area: how high its land lies (the mean and the 101 percentiles),
which the map's filters compare the anchors with.

Land with data is the area mask's pixels with a height of the search's own source before
any filling (the neighbours', the fallbacks' and the water's pixels are still NaN then),
less the water the search counts among pixels with data (sources.filling.water_with_data:
lakes of the water body mask, the sea zone at about sea level). Its heights are counted in
an exact integer histogram: centimetres as np.rint(z * 100) (the round(e, 2) of the saved
anchor heights), bins of BIN_CM from LOW_CM to HIGH_CM (heights outside go into the first
or last bin), and the exact sum of the centimetres. Histograms of the cores of a tiled
search add up to that of one grid, in any order, so a tiled area gets the same statistics.

    h = land_histogram(z, area_mask, wbm, sea_zone, window)   # row blocks of about block_px
    terrain = statistics(h, res)   # {"mean", "quantiles" (101), "km2"} or None

numpy only (never numba: the quick lane's profiles call search.prepare_data too).
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from sources.filling import water_with_data

BIN_CM = 10  # 0.1 m
LOW_CM = -100_000  # -1000 m
HIGH_CM = 1_000_000  # 10 000 m
BINS = (HIGH_CM - LOW_CM) // BIN_CM  # 110 000 counts, 880 kB


@dataclass
class Histogram:
    """Counts of the heights in bins of BIN_CM from LOW_CM, and their exact sum in centimetres."""
    counts: np.ndarray  # int64, BINS
    sum_cm: int  # exact (Python int)

    @property
    def n(self) -> int:
        return int(self.counts.sum())

    def __add__(self, other: "Histogram") -> "Histogram":
        return Histogram(self.counts + other.counts, self.sum_cm + other.sum_cm)

    @staticmethod
    def empty() -> "Histogram":
        return Histogram(np.zeros(BINS, np.int64), 0)


def land_histogram(z: np.ndarray, area_mask: np.ndarray, wbm: Optional[np.ndarray] = None,
                   sea_zone: Optional[np.ndarray] = None, window: Optional[Tuple[slice, slice]] = None,
                   block_px: int = 1_000_000) -> Histogram:
    """The histogram of the land with data (see above) of the grid z (raw terrain, NaN without
    data) inside area_mask, within window (rows, columns) of the grid when given. Read in blocks
    of rows of about block_px pixels: no temporary array of the whole grid."""
    rows, cols = window or (slice(None), slice(None))
    part = lambda a: None if a is None else a[rows, cols]
    z, area_mask, wbm, sea_zone = part(z), part(area_mask), part(wbm), part(sea_zone)
    height, width = z.shape
    step = max(1, block_px // max(width, 1))
    h = Histogram.empty()
    for r in range(0, height, step):
        block = lambda a: None if a is None else a[r:r + step]
        zb = np.asarray(block(z))
        keep = np.asarray(block(area_mask)) & np.isfinite(zb)
        if wbm is not None or sea_zone is not None:
            keep &= ~water_with_data(zb, block(wbm), block(sea_zone))
        cm = np.rint(zb[keep].astype(np.float64) * 100).astype(np.int64)
        del keep
        h.sum_cm += int(cm.sum())
        h.counts += np.bincount(np.clip((cm - LOW_CM) // BIN_CM, 0, BINS - 1), minlength=BINS)
    return h


def statistics(h: Optional[Histogram], res: float) -> Optional[Dict]:
    """The terrain of a run: {"mean": m, "quantiles": [q0 .. q100] (m), "km2": land with data},
    None without land with data. q_p is the lower edge of the first bin whose cumulative count
    reaches max(1, ceil(p * n / 100)), all in integers."""
    if h is None:
        return None
    n = h.n
    if n == 0:
        return None
    cum = np.cumsum(h.counts)
    needs = np.array([max(1, (p * n + 99) // 100) for p in range(101)], np.int64)
    bins = np.searchsorted(cum, needs).tolist()
    return {"mean": round(h.sum_cm / n / 100, 2),
            "quantiles": [round((LOW_CM + k * BIN_CM) / 100, 1) for k in bins],
            "km2": round(n * res ** 2 / 1e6, 4)}


def save(path: str, h: Histogram):
    """Save h as .npz (no pickle): the counts from the first to the last bin used, the first's
    index, the bins' parameters and the sum; written whole, then moved over path."""
    used = np.flatnonzero(h.counts)
    first, last = (int(used[0]), int(used[-1]) + 1) if used.size else (0, 0)
    with open(path + ".part", "wb") as f:
        np.savez(f, counts=h.counts[first:last], first=np.int64(first), sum_cm=np.array(str(h.sum_cm)),
                 bin_cm=np.int64(BIN_CM), low_cm=np.int64(LOW_CM), high_cm=np.int64(HIGH_CM))
    os.replace(path + ".part", path)


def load(path: str) -> Optional[Histogram]:
    """The histogram saved by save, None when the file is missing or has other bins."""
    if not os.path.exists(path):
        return None
    with np.load(path, allow_pickle=False) as f:
        if (int(f["bin_cm"]), int(f["low_cm"]), int(f["high_cm"])) != (BIN_CM, LOW_CM, HIGH_CM):
            return None
        counts = np.zeros(BINS, np.int64)
        first, part = int(f["first"]), f["counts"]
        counts[first:first + len(part)] = part
        return Histogram(counts, int(str(f["sum_cm"])))
