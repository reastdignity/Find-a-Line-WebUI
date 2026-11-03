"""
Run by hand (through tools/obstacle_study.py): the orthophoto as a judge of what stands on the
surface model, one of the three proxies of the obstacle study (docs/roadmap.md, priority 1).

greenness_on_grid takes the orthophoto of a call's source (sources.SOURCES[id].ortho) in the
strips around its lines (orthophoto.strip_tiles at ZOOM only, about 0.2-0.3 m a pixel, no overview
zooms), downloads the tiles not cached yet with orthophoto.download into the data folder's cache
(the cache the maps share), and computes per tile pixel the green leaf index

    GLI = (2G - R - B) / (2G + R + B)    (NaN where the denominator is 0)

and the luminance (R + G + B) / 3. Both are warped from each tile's Web Mercator box onto the
call's working grid (grid.json) with rasterio's Resampling.average; a grid pixel on the edge of
two tiles takes their averages weighted by the part of it each covers (Resampling.sum of the
valid pixels), so the result is the average over the whole pixel. A pixel outside the strips, or
of a tile that could not be downloaded, is NaN. A service of base tiles only (no WMS) is asked at
its base_max_zoom at most.

threshold splits the GLI of a place into green and not green: tau halfway between the median GLI
of its sure forest and of its sure rock (the study tool knows those masks), with the share of both
sets on the wrong side of tau (overlap); the luminance likewise into bright and not (bright halfway
between the medians, bright_overlap: bare rock is bright where a leafless spring image gives forest
and rock the same GLI); and dark, the 5th percentile of the forest's luminance (darker pixels,
shadows on walls, tell nothing). write_greenness keeps ortho-gli.npy, ortho-lum.npy and ortho.json
in a call's folder.
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import orthophoto  # noqa: E402

ZOOM = 19
MIN_PIXELS = 50     # fewer pixels of forest or rock: no threshold
DARK_PERCENTILE = 5


def _transform(grid: Dict):
    from affine import Affine
    return Affine(grid["res"], 0, grid["left"], 0, -grid["res"], grid["top"])


def _latitude(grid: Dict) -> float:
    """The latitude of the grid's centre (Web Mercator's stretch for the strips)."""
    from pyproj import Transformer
    x = grid["left"] + grid["width"] * grid["res"] / 2
    y = grid["top"] - grid["height"] * grid["res"] / 2
    _, lat = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True).transform(x, y)
    return lat


def tile_indices(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """(GLI, luminance) of a cached tile's pixels, float32."""
    from PIL import Image
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    denominator = 2 * g + r + b
    with np.errstate(divide="ignore", invalid="ignore"):
        gli = np.where(denominator > 0, (2 * g - r - b) / denominator, np.nan).astype(np.float32)
    return gli, ((r + g + b) / 3).astype(np.float32)


def _window(grid: Dict, box: Tuple[float, float, float, float]) -> Optional[Tuple[int, int, int, int]]:
    """(row0, row1, col0, col1) of the grid's pixels a Web Mercator box may reach (a pixel more on
    each side), None when it misses the grid."""
    from rasterio.warp import transform_bounds
    left, bottom, right, top = transform_bounds("EPSG:3857", grid["crs"], *box, densify_pts=21)
    res = grid["res"]
    col0 = max(0, math.floor((left - grid["left"]) / res) - 1)
    col1 = min(grid["width"], math.ceil((right - grid["left"]) / res) + 1)
    row0 = max(0, math.floor((grid["top"] - top) / res) - 1)
    row1 = min(grid["height"], math.ceil((grid["top"] - bottom) / res) + 1)
    if col0 >= col1 or row0 >= row1:
        return None
    return row0, row1, col0, col1


def greenness_on_grid(grid: Dict, source_id: str, lines: List[Dict], cache_dir: str,
                      zoom: int = ZOOM) -> Tuple[np.ndarray, np.ndarray, int]:
    """GLI and luminance (float32, the grid's shape, NaN where no tile) of the orthophoto in the
    strips around lines ({"anchor1": (lat, lon), "anchor2": (lat, lon)}), and the number of tiles
    that were there; grid is a call's grid.json (crs, left, top, res, height, width)."""
    from affine import Affine
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    import sources

    shape = (grid["height"], grid["width"])
    gli, lum = np.full(shape, np.nan, dtype=np.float32), np.full(shape, np.nan, dtype=np.float32)
    service = sources.SOURCES[source_id].ortho
    if service is None or not lines:
        return gli, lum, 0
    if not service.url:  # base tiles only: never above their last zoom (an enlarged tile tells nothing)
        zoom = min(zoom, service.base_max_zoom)
    scale = 1 / math.cos(math.radians(_latitude(grid)))
    tiles = sorted(orthophoto.strip_tiles(lines, [zoom], scale))
    folder = orthophoto.cache_folder(cache_dir, service)
    missing = orthophoto.missing_tiles(tiles, folder)
    if missing:
        print(f"  Orthophoto: {len(missing)} of {len(tiles)} tiles of zoom {zoom} to download")
        orthophoto.download(service, missing, folder, cache_dir)

    transform = _transform(grid)
    # Weighted sums over the tiles: a pixel on a tile's edge gets each tile's average weighted by
    # the valid source pixels it covers there
    sums = np.zeros((4,) + shape, dtype=np.float64)  # GLI x weight, its weight, luminance x weight, weight
    found = 0
    for z, x, y in tiles:
        path = orthophoto.tile_path(folder, z, x, y)
        if not os.path.exists(path):
            continue  # its download failed: NaN
        found += 1
        window = _window(grid, orthophoto.mercator_box(z, x, y))
        if window is None:
            continue
        row0, row1, col0, col1 = window
        tile_gli, tile_lum = tile_indices(path)
        src_transform = from_bounds(*orthophoto.mercator_box(z, x, y), tile_gli.shape[1], tile_gli.shape[0])
        dst_transform = transform @ Affine.translation(col0, row0)
        part = (row1 - row0, col1 - col0)
        average = np.full((2,) + part, np.nan, dtype=np.float32)
        reproject(np.stack([tile_gli, tile_lum]), average, src_transform=src_transform, src_crs="EPSG:3857",
                  src_nodata=np.nan, dst_transform=dst_transform, dst_crs=grid["crs"], dst_nodata=np.nan,
                  resampling=Resampling.average)
        weight = np.zeros((2,) + part, dtype=np.float32)
        valid = np.stack([np.isfinite(tile_gli), np.ones(tile_gli.shape, bool)]).astype(np.float32)
        reproject(valid, weight, src_transform=src_transform, src_crs="EPSG:3857",
                  dst_transform=dst_transform, dst_crs=grid["crs"], resampling=Resampling.sum)
        for band in range(2):
            ok = np.isfinite(average[band]) & (weight[band] > 0)
            block = (slice(row0, row1), slice(col0, col1))
            sums[2 * band][block] += np.where(ok, average[band].astype(np.float64) * weight[band], 0)
            sums[2 * band + 1][block] += np.where(ok, weight[band], 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        for band, out in enumerate((gli, lum)):
            covered = sums[2 * band + 1] > 0
            out[covered] = (sums[2 * band][covered] / sums[2 * band + 1][covered]).astype(np.float32)
    return gli, lum, found


def threshold(gli: np.ndarray, lum: np.ndarray, forest: np.ndarray, rock: np.ndarray) -> Dict:
    """tau (halfway between the median GLI of the forest's pixels and of the rock's), dark (the
    DARK_PERCENTILE of the forest's luminance), both medians, and overlap (the forest's pixels
    below tau and the rock's above it, over both); bright (halfway between the median luminance of
    the forest's pixels and of the rock's) and bright_overlap (the forest's pixels at bright or
    above and the rock's below it, over both); a value is None when a set it needs has fewer than
    MIN_PIXELS pixels with a GLI (a luminance)."""
    forest_gli = gli[forest & np.isfinite(gli)]
    rock_gli = gli[rock & np.isfinite(gli)]
    forest_lum = lum[forest & np.isfinite(lum)]
    rock_lum = lum[rock & np.isfinite(lum)]
    out = {"tau": None, "dark": None, "forest_median": None, "rock_median": None, "overlap": None,
           "bright": None, "bright_overlap": None}
    if forest_gli.size >= MIN_PIXELS:
        out["forest_median"] = float(np.median(forest_gli))
    if forest_lum.size >= MIN_PIXELS:
        out["dark"] = float(np.percentile(forest_lum, DARK_PERCENTILE))
    if rock_gli.size >= MIN_PIXELS:
        out["rock_median"] = float(np.median(rock_gli))
    if out["forest_median"] is not None and out["rock_median"] is not None:
        tau = (out["forest_median"] + out["rock_median"]) / 2
        wrong = int((forest_gli < tau).sum()) + int((rock_gli > tau).sum())
        out.update(tau=float(tau), overlap=wrong / (forest_gli.size + rock_gli.size))
    if forest_lum.size >= MIN_PIXELS and rock_lum.size >= MIN_PIXELS:
        bright = (float(np.median(forest_lum)) + float(np.median(rock_lum))) / 2
        wrong = int((forest_lum >= bright).sum()) + int((rock_lum < bright).sum())
        out.update(bright=bright, bright_overlap=wrong / (forest_lum.size + rock_lum.size))
    return out


def write_greenness(call: str, grid: Dict, source_id: str, lines: List[Dict], cache_dir: str) -> Dict:
    """ortho-gli.npy, ortho-lum.npy (greenness_on_grid) and ortho.json (the zoom asked, the tiles;
    the threshold's values null: the study tool fills them in with its masks) in a call's folder;
    returns ortho.json's content."""
    import sources
    service = sources.SOURCES[source_id].ortho
    zoom = min(ZOOM, service.base_max_zoom) if service is not None and not service.url else ZOOM
    gli, lum, tiles = greenness_on_grid(grid, source_id, lines, cache_dir, zoom=zoom)
    np.save(os.path.join(call, "ortho-gli.npy"), gli)
    np.save(os.path.join(call, "ortho-lum.npy"), lum)
    info = {"zoom": zoom, "tiles": tiles, "tau": None, "dark": None, "forest_median": None,
            "rock_median": None, "overlap": None}
    with open(os.path.join(call, "ortho.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    return info
