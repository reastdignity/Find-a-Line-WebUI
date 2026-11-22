"""
Where rasters of one pixel grid overlap, and how low their values go (run by hand, read-only): the measurements a
dataset's cut waits for (docs/new-sources-6/spec.md, section 2: Wallonia's provinces, gates G1 and G2).

Given two or more single-band rasters on one pixel grid (the same pixel size and CRS, their edges a whole number of
pixels apart; plain files, /vsizip/ paths, or a .zip holding exactly one .tif member, read as /vsizip/):

1. for every pair whose boxes overlap, over their shared box: the pixels valid in both, valid in the first only and
   in the second only, the largest absolute difference where both are valid, and a histogram of those differences
   (exactly 0, at most 5 mm, 5 cm, 0.5 m, 5 m, and above 5 m): a seam of equal pixels allows the cut's overlap rule
   "agree" (tools/mirror_tiles.py), and a pair that differs shows where;
2. for every raster: its valid pixels, its lowest value and where (the pixel's centre), and per threshold (--below,
   by default 0 and 10 m) the valid pixels below it and the box holding them, for a floor's decision.

Valid is finite and none of the file's nodata tag and the --nodata values. Everything is read in bands of rows
within --max-memory-gb (BYTES_PER_PX for each pixel of a band in flight, GDAL's cache a quarter of the bound), so a
province of 250 000 x 195 000 px is measured in bands of a few hundred rows; full-width strips make GDAL read each
strip once per band. GDAL's /vsizip/ reads a ZIP member about 60 times slower than Python's zipfile unpacks it
(.claude/rules/providers.md, the Slovak tiles): for the large files unpack first (tools/mirror_tiles.py extract).

    uv run python tools/raster_overlap.py A.tif B.tif [C.tif ...] [--nodata -9999] [--below 0 10]
                                          [--max-memory-gb 1] [--json FILE]

Prints a text table (progress lines every PROGRESS_SECONDS on stderr); --json writes the same numbers to FILE.
Exit 0, or 2 for rasters that are not on one grid. It writes nothing else and makes no request.
"""

import argparse
import itertools
import json
import math
import os
import sys
import time
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import rasterio as rio
from rasterio.windows import Window

EDGES = (0.005, 0.05, 0.5, 5.0)  # the histogram's upper edges (metres) after "exactly 0"; above the last: "> 5 m"
BINS = ("0", "<= 5 mm", "<= 5 cm", "<= 0.5 m", "<= 5 m", "> 5 m")
BELOW = (0.0, 10.0)        # default thresholds of the low values (metres)
MAX_MEMORY_GB = 1.0
BYTES_PER_PX = 40          # a pixel of a band in flight: two windows as float64, their masks and the differences
PROGRESS_SECONDS = 30.0


class NotOneGrid(ValueError):
    """The rasters do not share one pixel grid."""


@dataclass(frozen=True)
class Raster:
    """A raster's place: what it was given as, the path read, its CRS, pixel size, corner, size and nodata tag."""
    name: str
    path: str
    crs: Optional[str]
    res: float
    left: float
    top: float
    width: int
    height: int
    nodata: Optional[float]

    @property
    def box(self) -> Tuple[float, float, float, float]:
        """(left, bottom, right, top)."""
        return self.left, self.top - self.height * self.res, self.left + self.width * self.res, self.top


def readable_path(path: str) -> str:
    """The path GDAL opens: a .zip of exactly one .tif member as its /vsizip/ path, anything else as given."""
    if not path.lower().endswith(".zip"):
        return path
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith((".tif", ".tiff"))]
    if len(members) != 1:
        raise ValueError(f"{path}: {len(members)} .tif members, one expected (name it as /vsizip/<zip>/<member>)")
    return f"/vsizip/{path}/{members[0]}"


def open_raster(name: str) -> Raster:
    path = readable_path(name)
    with rio.open(path) as src:
        t = src.transform
        if src.count != 1 or t.b or t.d or t.e >= 0 or not math.isclose(t.a, -t.e, rel_tol=1e-9):
            raise NotOneGrid(f"{name}: one band of square pixels, north up, without rotation expected")
        crs = src.crs.to_string() if src.crs else None
        return Raster(name, path, crs, float(t.a), float(t.c), float(t.f), src.width, src.height, src.nodata)


def check_one_grid(rasters: Sequence[Raster]):
    """NotOneGrid unless every raster has the first's pixel size and CRS (when both name one) and its edges lie a
    whole number of pixels from the first's."""
    first = rasters[0]
    for r in rasters[1:]:
        if not math.isclose(r.res, first.res, rel_tol=1e-9):
            raise NotOneGrid(f"{r.name}: {r.res:g} m pixels, {first.name} {first.res:g} m")
        if r.crs and first.crs and r.crs != first.crs:
            from rasterio.crs import CRS
            if CRS.from_user_input(r.crs) != CRS.from_user_input(first.crs):
                raise NotOneGrid(f"{r.name}: {r.crs}, {first.name} {first.crs}")
        for what, a, b in (("left", r.left, first.left), ("top", r.top, first.top)):
            steps = (a - b) / first.res
            if abs(steps - round(steps)) > 1e-6:
                raise NotOneGrid(f"{r.name}: its {what} edge {a} is not a whole number of pixels from {first.name}'s")


def shared_box(a: Raster, b: Raster) -> Optional[Tuple[float, float, float, float]]:
    """The box both cover (left, bottom, right, top), None when they only touch or lie apart."""
    (al, ab, ar, at), (bl, bb, br, bt) = a.box, b.box
    left, bottom, right, top = max(al, bl), max(ab, bb), min(ar, br), min(at, bt)
    return (left, bottom, right, top) if left < right and bottom < top else None


def rows_per_band(width: int, max_memory_gb: float) -> int:
    """Rows of a band of that width within the bound, three quarters of it (GDAL's cache takes the rest)."""
    return max(1, int(max_memory_gb * 1e9 * 0.75) // max(1, width * BYTES_PER_PX))


def valid(values: np.ndarray, raster: Raster, nodata: Sequence[float]) -> np.ndarray:
    """Finite, and none of the file's nodata tag and the given values (compared in the raster's type)."""
    ok = np.isfinite(values)
    for value in tuple(nodata) + ((raster.nodata,) if raster.nodata is not None else ()):
        if not np.isnan(value):
            ok &= values != np.array(value, dtype=values.dtype)
    return ok


def _window(r: Raster, box: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    """(column, row, width, height) of a box on a raster's pixels."""
    left, bottom, right, top = box
    return (round((left - r.left) / r.res), round((r.top - top) / r.res), round((right - left) / r.res),
            round((top - bottom) / r.res))


class _Progress:
    def __init__(self, what: str, total: int):
        self.what, self.total, self.start, self.last = what, total, time.time(), time.time()

    def __call__(self, done: int):
        if time.time() - self.last >= PROGRESS_SECONDS:
            self.last = time.time()
            print(f"{self.what}: rows {done} of {self.total}, {time.time() - self.start:.0f} s", file=sys.stderr,
                  flush=True)


def compare(a: Raster, b: Raster, nodata: Sequence[float] = (), max_memory_gb: float = MAX_MEMORY_GB) -> Optional[Dict]:
    """Two rasters over their shared box (None when their boxes do not overlap): valid in both, in one only, the
    largest absolute difference where both are valid and the histogram of the differences (BINS)."""
    box = shared_box(a, b)
    if box is None:
        return None
    ac, ar, width, height = _window(a, box)
    bc, br, _, _ = _window(b, box)
    both = only_a = only_b = 0
    worst, counts = 0.0, np.zeros(len(BINS), dtype=np.int64)
    step = rows_per_band(width, max_memory_gb)
    progress = _Progress(f"{a.name} x {b.name}", height)
    with rio.Env(GDAL_CACHEMAX=max(64, int(max_memory_gb * 250))), rio.open(a.path) as fa, rio.open(b.path) as fb:
        for r0 in range(0, height, step):
            h = min(step, height - r0)
            va = fa.read(1, window=Window(ac, ar + r0, width, h))
            vb = fb.read(1, window=Window(bc, br + r0, width, h))
            ma, mb = valid(va, a, nodata), valid(vb, b, nodata)
            m = ma & mb
            both += int(m.sum())
            only_a += int((ma & ~mb).sum())
            only_b += int((mb & ~ma).sum())
            if m.any():
                d = np.abs(va[m].astype(np.float64) - vb[m].astype(np.float64))
                worst = max(worst, float(d.max()))
                counts[0] += int((d == 0).sum())  # then (0, 5 mm], (5 mm, 5 cm], ..., above 5 m
                counts[1:] += np.bincount(np.searchsorted(EDGES, d[d > 0], side="left"), minlength=len(EDGES) + 1)
            progress(r0 + h)
    return {"a": a.name, "b": b.name, "box": list(box), "valid_both": both, "valid_a_only": only_a,
            "valid_b_only": only_b, "max_abs_diff_m": worst, "histogram": dict(zip(BINS, counts.tolist()))}


def low_values(r: Raster, below: Sequence[float] = BELOW, nodata: Sequence[float] = (),
               max_memory_gb: float = MAX_MEMORY_GB) -> Dict:
    """A raster's valid pixels, its lowest value and where (the pixel's centre), and per threshold the valid pixels
    below it with the box holding them (left, bottom, right, top; None when there are none)."""
    total, lowest, where = 0, math.inf, None
    found = {t: [0, None] for t in below}  # threshold: [count, (row0, row1, col0, col1)]
    step = rows_per_band(r.width, max_memory_gb)
    progress = _Progress(r.name, r.height)
    with rio.Env(GDAL_CACHEMAX=max(64, int(max_memory_gb * 250))), rio.open(r.path) as src:
        for r0 in range(0, r.height, step):
            h = min(step, r.height - r0)
            values = src.read(1, window=Window(0, r0, r.width, h))
            ok = valid(values, r, nodata)
            if not ok.any():
                progress(r0 + h)
                continue
            total += int(ok.sum())
            masked = np.where(ok, values.astype(np.float64), math.inf)
            k = int(np.argmin(masked))
            if masked.flat[k] < lowest:
                lowest = float(masked.flat[k])
                row, col = divmod(k, r.width)
                where = (r.left + (col + 0.5) * r.res, r.top - (r0 + row + 0.5) * r.res)
            for t, entry in found.items():
                hit = masked < t
                n = int(hit.sum())
                if n:
                    rows, cols = np.nonzero(hit.any(axis=1))[0], np.nonzero(hit.any(axis=0))[0]
                    span = (r0 + rows[0], r0 + rows[-1] + 1, cols[0], cols[-1] + 1)
                    old = entry[1]
                    entry[0] += n
                    entry[1] = span if old is None else (min(old[0], span[0]), max(old[1], span[1]),
                                                         min(old[2], span[2]), max(old[3], span[3]))
            progress(r0 + h)

    def box(span):
        if span is None:
            return None
        r0, r1, c0, c1 = span
        return [r.left + c0 * r.res, r.top - r1 * r.res, r.left + c1 * r.res, r.top - r0 * r.res]
    return {"name": r.name, "valid": total, "lowest_m": None if where is None else lowest,
            "lowest_at": None if where is None else list(where),
            "below": [{"threshold_m": t, "valid_below": n, "box": box(span)} for t, (n, span) in found.items()]}


def measure(names: Sequence[str], nodata: Sequence[float] = (), below: Sequence[float] = BELOW,
            max_memory_gb: float = MAX_MEMORY_GB) -> Dict:
    """Every pair whose boxes overlap, and every raster's low values; NotOneGrid for rasters off one grid."""
    if len(names) < 2:
        raise ValueError("two rasters or more")
    rasters = [open_raster(n) for n in names]
    check_one_grid(rasters)
    pairs = [found for a, b in itertools.combinations(rasters, 2)
             if (found := compare(a, b, nodata, max_memory_gb)) is not None]
    return {"crs": rasters[0].crs, "res": rasters[0].res, "nodata": list(nodata), "pairs": pairs,
            "rasters": [low_values(r, below, nodata, max_memory_gb) for r in rasters]}


def report(result: Dict) -> List[str]:
    """The text table of a measure()."""
    lines = [f"Pixels of {result['res']:g} m ({result['crs']}); valid: finite, not the files' nodata"
             + (f" nor {', '.join(f'{v:g}' for v in result['nodata'])}" if result["nodata"] else ""), "",
             "Pairs whose boxes overlap (over their shared box):", "",
             "| A | B | valid in both | A only | B only | max abs diff, m | " + " | ".join(BINS) + " |",
             "| --- | --- | ---: | ---: | ---: | ---: | " + " | ".join("---:" for _ in BINS) + " |"]
    for p in result["pairs"]:
        lines.append(f"| {p['a']} | {p['b']} | {p['valid_both']:,} | {p['valid_a_only']:,} | {p['valid_b_only']:,} | "
                     f"{p['max_abs_diff_m']:.4f} | " + " | ".join(f"{p['histogram'][b]:,}" for b in BINS) + " |")
    if not result["pairs"]:
        lines.append("| (no two boxes overlap) | | | | | | " + " | ".join("" for _ in BINS) + " |")
    lines += ["", "Low values:", "",
              "| raster | valid | lowest, m | at (x, y) | threshold, m | valid below | their box |",
              "| --- | ---: | ---: | --- | ---: | ---: | --- |"]
    for r in result["rasters"]:
        at = "-" if r["lowest_at"] is None else f"{r['lowest_at'][0]:.2f}, {r['lowest_at'][1]:.2f}"
        lowest = "-" if r["lowest_m"] is None else f"{r['lowest_m']:.3f}"
        for n, b in enumerate(r["below"]):
            box = "-" if b["box"] is None else ", ".join(f"{v:.1f}" for v in b["box"])
            head = f"| {r['name']} | {r['valid']:,} | {lowest} | {at} |" if n == 0 else "| | | | |"
            lines.append(f"{head} {b['threshold_m']:g} | {b['valid_below']:,} | {box} |")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Where rasters of one pixel grid overlap, and their low values "
                                                 "(read-only)")
    parser.add_argument("rasters", nargs="+", help="two or more rasters (files, /vsizip/ paths, or ZIPs of one .tif)")
    parser.add_argument("--nodata", type=float, nargs="*", default=[], help="values that are no data besides each "
                                                                           "file's tag")
    parser.add_argument("--below", type=float, nargs="*", default=list(BELOW),
                        help="thresholds of the low values, metres (default: 0 10)")
    parser.add_argument("--max-memory-gb", type=float, default=MAX_MEMORY_GB, help="the bound of a band in flight and "
                                                                                    "GDAL's cache (default: 1)")
    parser.add_argument("--json", help="write the numbers to this file as well")
    args = parser.parse_args(argv)
    try:
        result = measure(args.rasters, args.nodata, args.below, args.max_memory_gb)
    except (NotOneGrid, ValueError) as e:
        print(f"raster_overlap: {e}", file=sys.stderr)
        return 2
    print("\n".join(report(result)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (a raster's name may hold any letter)
    sys.exit(main())
