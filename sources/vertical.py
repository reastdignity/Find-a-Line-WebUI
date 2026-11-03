"""Vertical references: a geoid grid that turns heights above the ellipsoid into heights above the geoid.

ArcticDEM's heights are above the WGS84 ellipsoid; every other model of the app, the sea at 0 m of the water
filling (filling.fill_water) and the heights shown to users are above the sea. A layer of ellipsoidal heights
names a Geoid (FileBlocks(..., geoid=EGM2008)): its blocks are cached as h - N, orthometric heights, so nothing
downstream changes.

The grid is PROJ's (cdn.proj.org), downloaded once into the cache (<folder>/<file>, a static edition: never
checked again), checked against its sha256 and read here with rasterio, bilinear on its points. PROJ itself is
never asked: pyproj's transformation to EGM2008 heights silently gives N = 0 when it cannot find the grid
(PROJ_NETWORK off, no grid in its data folder). Without the grid (offline, a failed download) a layer that needs
it fails with GeoidMissing, never with N = 0.
"""

import hashlib
import math
import os
import threading
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio as rio
import requests
from affine import Affine
from filelock import FileLock, Timeout
from pyproj import Transformer
from rasterio.windows import Window

import cache
import servicecounts
from progress import progress

from . import net

# Points of the lattice per side of a block (corners included) at which N is computed from the grid, then
# interpolated bilinearly to every pixel: over a 2 km block of ArcticDEM (250 m between the points) the lattice
# stays within 2 mm of N computed at every pixel (tests/test_vertical.py, measured on the grid at 60-82° N)
LATTICE = 9


class GeoidMissing(RuntimeError):
    """The geoid grid a layer needs is not in the cache and could not be downloaded."""


class Geoid:
    """A geoid model as a grid of N (metres of the geoid above the ellipsoid) on points of longitude and latitude
    (pixel-is-point, as PROJ's grids), cached as <cache>/<folder>/<file of url>. tag names the vertical
    reference in a layer's folder (-<tag>), name in its cached files' tags ("vertical")."""

    def __init__(self, name: str, tag: str, url: str, sha256: str, size: int, folder: str, credit: str):
        self.name, self.tag, self.url, self.sha256, self.size = name, tag, url, sha256, size
        self.folder, self.credit = folder, credit
        self.file = url.rstrip("/").rsplit("/", 1)[-1]
        self._lock = threading.Lock()
        self._ready: Dict[str, str] = {}  # cache folder -> the grid's path, checked in this process
        self.grid: Optional[str] = None   # the grid undulation reads by default: the last one made ready

    def path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, *self.folder.split("/"), self.file)

    def located(self, cache_dir: str) -> Optional[str]:
        """The grid's path when it is in the cache whole (its size; its sha256 was checked when it came), else
        None; nothing is downloaded."""
        path = self.path(cache_dir)
        try:
            return path if os.path.getsize(path) == self.size else None
        except OSError:
            return None

    def ensure(self, cache_dir: str) -> str:
        """The grid's path, downloaded first if it is not in the cache (once: under a lock of the data folder,
        so two processes or threads never fetch it twice); it becomes the grid undulation reads. Raises
        GeoidMissing when it cannot be had."""
        with self._lock:
            known = self._ready.get(cache_dir)
            if known and os.path.exists(known):
                self.grid = known
                return known
            path = self.located(cache_dir)
            if path is None:
                lock = FileLock(os.path.join(net._locks(cache_dir, "geoid"), f"{self.tag}.lock"))
                try:
                    lock.acquire(timeout=net.LOCK_WAIT_S)
                except Timeout:
                    raise GeoidMissing(f"the {self.name} geoid grid is being downloaded by another search "
                                       f"(waited {net.LOCK_WAIT_S // 60} min); try again later") from None
                try:
                    path = self.located(cache_dir) or self._download(cache_dir)
                finally:
                    lock.release()
            self._ready[cache_dir] = path
            self.grid = path
            return path

    def _download(self, cache_dir: str) -> str:
        """The grid streamed to a .part next to its place (at most size bytes), checked against the sha256,
        then moved there and recorded in the cache's index; RETRIES attempts."""
        path = self.path(cache_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        last: Optional[BaseException] = None
        for attempt in range(net.RETRIES):
            try:
                self._fetch(path)
                cache.record(cache_dir, path, "ok", self.url)
                return path
            except (requests.RequestException, RuntimeError, OSError) as e:
                last = e
                net._sleep(attempt)
        raise GeoidMissing(f"the {self.name} geoid grid could not be downloaded ({cache.clean_error(last)}); "
                           f"heights above the ellipsoid cannot be used without it")

    def _fetch(self, path: str):
        net.rate_turn(self.url)
        digest = hashlib.sha256()
        with servicecounts.request(self.url) as counted, \
                requests.get(self.url, stream=True, timeout=120, headers=cache.http_headers(),
                             verify=net.verify(self.url)) as response:
            counted.got(response, read=False)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            length = int(response.headers.get("content-length") or 0)
            if length and length != self.size:
                counted.outcome = "other"
                raise RuntimeError(f"{length} bytes announced, {self.size} expected")
            progress.download.start(f"{self.name} geoid grid", self.size / 1e6, unit="MB")
            received = 0
            with cache.replacing(path) as f:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    received += len(chunk)
                    counted.add(len(chunk))
                    if received > self.size:
                        raise RuntimeError(f"more than {self.size} bytes")
                    digest.update(chunk)
                    f.write(chunk)
                    progress.download.update(len(chunk) / 1e6)
                if received != self.size or digest.hexdigest() != self.sha256:
                    raise RuntimeError(f"{received} bytes with another sha256 than expected")
            progress.download.finish(f"{received / 1e6:.0f} MB")

    def at(self, lon: np.ndarray, lat: np.ndarray, grid: Optional[str] = None) -> np.ndarray:
        """N at points of longitude and latitude (degrees, WGS84), bilinear between the grid's points (float64).
        A grid around the whole earth wraps the longitude past its last column (179.958° E to 180°, Chukotka);
        a smaller grid (the tests' windows) must hold the points."""
        grid = grid or self.grid
        if grid is None:
            raise GeoidMissing(f"the {self.name} geoid grid is not in the cache: it is downloaded by a search "
                               f"that needs it ({self.size / 1e6:.0f} MB)")
        lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        with rio.open(grid) as src:
            t, width, height = src.transform, src.width, src.height
            # The pixel (c, r) of a pixel-is-point grid as GDAL gives it is centred on the point: its point is at
            # t * (c + 0.5, r + 0.5)
            fc = (lon - t.c) / t.a - 0.5
            fr = (lat - t.f) / t.e - 0.5
            around = math.isclose(width * abs(t.a), 360.0, rel_tol=1e-9)
            if around:
                fc = np.mod(fc, width)
            c0 = np.floor(fc).astype(np.int64)
            r0 = np.clip(np.floor(fr).astype(np.int64), 0, height - 2)
            wc, wr = fc - c0, np.clip(fr - r0, 0.0, 1.0)
            c1 = c0 + 1
            if around:
                c1 = np.mod(c1, width)
            r_lo, r_hi = int(r0.min()), int(r0.max()) + 2
            if around and (c1 < c0).any():  # the points reach past the last column: the rows' whole width
                c_lo, c_hi = 0, width
            else:
                c_lo, c_hi = int(min(c0.min(), c1.min())), int(max(c0.max(), c1.max())) + 1
                if c_lo < 0 or c_hi > width or (not around and (fr < 0).any() | (fr > height - 1).any()):
                    raise ValueError(f"points outside the geoid grid {grid}")
            values = src.read(1, window=Window(c_lo, r_lo, c_hi - c_lo, r_hi - r_lo)).astype(np.float64)
            scale, offset = (src.scales or (1.0,))[0] or 1.0, (src.offsets or (0.0,))[0] or 0.0
        values = values * scale + offset

        def v(r, c):
            return values[r - r_lo, c - c_lo]
        return (v(r0, c0) * (1 - wc) * (1 - wr) + v(r0, c1) * wc * (1 - wr)
                + v(r0 + 1, c0) * (1 - wc) * wr + v(r0 + 1, c1) * wc * wr)

    def undulation(self, crs: str, transform: Affine, shape: Tuple[int, int], grid: Optional[str] = None,
                   lattice: int = LATTICE) -> np.ndarray:
        """N (float32) at the pixel centres of a block (its CRS, transform and shape): at a lattice of lattice x
        lattice points over the block (corner pixels' centres included) from the grid (at), then bilinear to
        every pixel. lattice 0: at every pixel (for comparisons)."""
        rows, cols = shape
        if lattice:
            pr = np.linspace(0.5, rows - 0.5, min(lattice, rows))
            pc = np.linspace(0.5, cols - 0.5, min(lattice, cols))
        else:
            pr, pc = np.arange(rows) + 0.5, np.arange(cols) + 0.5
        cc, rr = np.meshgrid(pc, pr)
        t = transform
        xs, ys = t.a * cc + t.b * rr + t.c, t.d * cc + t.e * rr + t.f
        lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(xs, ys)
        values = self.at(lon, lat, grid)
        if not lattice:
            return values.astype(np.float32)
        values = _along(values, pc, np.arange(cols) + 0.5, axis=1)
        return _along(values, pr, np.arange(rows) + 0.5, axis=0).astype(np.float32)


def _along(values: np.ndarray, at: np.ndarray, to: np.ndarray, axis: int) -> np.ndarray:
    """values given at the positions at (increasing) along an axis, interpolated linearly to the positions to."""
    if len(at) == 1:
        return np.repeat(values, len(to), axis=axis)
    k = np.clip(np.searchsorted(at, to, side="right") - 1, 0, len(at) - 2)
    w = (to - at[k]) / (at[k + 1] - at[k])
    if axis == 1:
        return values[:, k] * (1 - w) + values[:, k + 1] * w
    return values[k, :] * (1 - w)[:, None] + values[k + 1, :] * w[:, None]


# EGM2008 on PROJ's CDN: 2.5' (8640 x 4321 points, -180° to 179.958° E, 90° N to 90° S), float32, DEFLATE,
# 256 px tiles, EPSG:4979, 80.6 MB; size and sha256 from PROJ's files.geojson (2026-11-02). cdn.proj.org is the
# AWS Public Dataset program behind CloudFront, without published limits ("you are encouraged to mirror the
# grids"); the file's TIFFTAG_COPYRIGHT: "Derived from work by NGA. Public Domain"
EGM2008 = Geoid("EGM2008", "egm08", "https://cdn.proj.org/us_nga_egm08_25.tif",
                "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a", 80585622, "geoid/egm2008",
                "EGM2008 geoid grid: derived from work by NGA, public domain (PROJ's us_nga_egm08_25.tif)")
