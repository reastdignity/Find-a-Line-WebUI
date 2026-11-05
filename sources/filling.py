"""Water and gaps: the water body mask, water filled to the surface level, gaps from fallback sources."""

import math
import os
import shutil
from typing import Callable, Iterable, List, Optional, Tuple

import numpy as np
import requests
from rasterio.warp import transform_bounds

import cache
from grid import Grid
from progress import progress

from .source import Source
from .catalogue.world import WATER_MASK
from .mosaic import NODATA, build_mosaic, flush_grid, prepare_layer, used_data

# Copernicus water body mask, 1°×1° tiles next to the DEM tiles: 1 ocean, 2 lake, 3 river
OCEAN, LAKE = 1, 2
GAP_RING = 3  # pixels around a gap used to match the filling source's heights
GAP_MATCH_SLOPE = 15  # degrees; only gentler ground is used to match heights
GAP_MAX_LOCAL_SHIFT = 3  # m; local height offsets differing more from the overall one are ignored
SHORE_BUFFER = 45  # m around water in the mask that may still be water (the mask is 30 m)
SEA_LEVEL_TOLERANCE = 1.0  # m; data at most this high inside the sea counts as water
SEA_FILL_EPS = 0.005  # m; data this close to a source's sea fill (Source.sea_fill) inside the sea counts as water
# A shore face the terrain model lacks is taken from the surface model (fill_shore_from_surface) one
# pixel at a time from the terrain's data edge downwards: each pixel at most this much above the
# neighbour it is reached from (a ship or a boulder standing up from the water is never reached)
FACE_TOLERANCE = 1.5  # m
# The uncertain shore (shore_rows, shore_segments): SHORE_SURFACE where the terrain's face came from the surface
# model, SHORE_SEA where the sea fill stands in for a cliff's foot (a water pixel with a neighbour of the
# terrain's own data, not a face, more than SHORE_RIM_MIN higher: the terrain model ends above the water there)
SHORE_SURFACE, SHORE_SEA = 1, 2
SHORE_RIM_MIN = 5.0  # m
SHORE_SIMPLIFY = 2.0  # pixels: the tolerance the segments' outlines are simplified with (shore_segments)
SHORE_BAND = 2  # pixels: the shore's pixels grown by this much each way before they are outlined (shore_segments)
SHORE_MIN_M = 10  # m: a segment shorter than this is left out of the run's list (counted in its totals)
# A neighbour (Source.neighbours) fills gaps reaching the edge of the search's footprint at
# least this large (a sliver of another country at the edge is left to the fallback)
NEIGHBOUR_MIN_GAP_M2 = 2500
NEIGHBOUR_PAD = GAP_RING + 3  # pixels of the neighbour's data around its gaps (offsets, slopes)
# How a neighbour's data are reprojected onto the grid (fill_from_neighbours). At about the grid's
# resolution (mosaic.FINER to mosaic.SAME of it) by NEIGHBOUR_SAME_RESOLUTION, not bilinearly: at one
# resolution a bilinear reprojection smooths every cliff edge (the half-pixel pitfall), and on the
# neighbour's side of the Tatras and the Wetterstein it lost 25-42 % of the lines the neighbour's own
# grid finds, nearest 0-4 % (measured 2026-11-05 with tools/border_study.py: docs/performance.md, "The
# resampling of a neighbour's data"; the user's decision). Finer data are averaged and coarser data
# reprojected bilinearly, as every mosaic (nearest would copy a coarse pixel onto several of ours, a
# staircase of false walls: measured on the Zillertal ridge). NEIGHBOUR_RESAMPLING, when set, is the method for all of a
# neighbour's rasters instead (one of mosaic.RESAMPLINGS: tools/border_study.py's --resampling)
NEIGHBOUR_SAME_RESOLUTION: Optional[str] = "nearest"
NEIGHBOUR_RESAMPLING: Optional[str] = None
# Step 1 of a tiled search (search.search_lines) runs once on the whole area: its operations then
# work on strips of rows of about this many pixels (each with a halo of its reach), never on a
# temporary of the whole grid; the functions take `rows` (None: the whole grid at once, as a
# search of one grid does) and give the same values (tests/test_units.py, the *_rows_* tests)
STRIP_PX = 1 << 22


def strip_rows(width: int) -> int:
    """Rows of a strip of about STRIP_PX pixels on a grid this wide (at least 16)."""
    return max(16, STRIP_PX // max(width, 1))


def strips(height: int, rows: int, halo: int = 0) -> Iterable[Tuple[int, int, int, int]]:
    """(r0, r1, h0, h1) of each strip of `rows` rows: its rows [r0, r1) and those with `halo`
    rows around them, clipped to the grid, [h0, h1)."""
    for r0 in range(0, height, rows):
        r1 = min(height, r0 + rows)
        yield r0, r1, max(0, r0 - halo), min(height, r1 + halo)


def water_body_mask(grid: Grid, cache_dir: str, out_path: str, update: Optional[str] = None,
                    download: bool = True, rows: Optional[int] = None) -> np.ndarray:
    """Copernicus water body mask on the grid (OCEAN, LAKE...) as uint8, open sea where tiles are
    missing, mosaic.NODATA where no tile reaches (downloaded first unless done already: download False).
    rows: the mosaic built and the missing tiles' blocks set in strips of that many rows."""
    if download:
        WATER_MASK.download(grid, cache_dir, update, "water mask")
    wbm = build_mosaic(WATER_MASK.files(grid, cache_dir), grid, out_path, "water mask", categorical=True, rows=rows)
    used_data.append(WATER_MASK.used(grid, cache_dir))
    tiles = WATER_MASK.tiles(grid)
    for tile, state in zip(tiles, cache.states(cache_dir, [WATER_MASK.tile_path(cache_dir, t) for t in tiles])):
        if state == "missing":
            lat, lon = tile
            left, bottom, right, top = transform_bounds("EPSG:4326", grid.crs, lon, lat, lon + 1, lat + 1)
            c0, c1 = max(0, int((left - grid.left) // grid.res)), min(grid.width, int((right - grid.left) // grid.res) + 1)
            r0, r1 = max(0, int((grid.top - top) // grid.res)), min(grid.height, int((grid.top - bottom) // grid.res) + 1)
            if r0 < r1 and c0 < c1:
                for s0, s1, _, _ in strips(r1 - r0, rows or r1 - r0):
                    block = wbm[r0 + s0:r0 + s1, c0:c1]
                    block[block == NODATA] = OCEAN
    return np.asarray(wbm)


def near(mask: np.ndarray, metres: float, res: float) -> np.ndarray:
    """The mask grown by about `metres` (square neighbourhood): every pixel within n = ceil(metres / res)
    pixels of it along both axes (the Chebyshev distance), nothing beyond the grid's edges. A running
    maximum along the columns, then the rows (two passes of any n): exactly the n iterations of a 3 x 3
    dilation it replaced (tests/test_units.py::test_near_matches_the_dilation), 2 bytes a pixel."""
    from scipy import ndimage
    if metres <= 0:
        return mask
    size = 2 * max(1, math.ceil(metres / res)) + 1
    grown = ndimage.maximum_filter1d(np.asarray(mask, dtype=bool), size, axis=0, mode="constant", cval=0)
    return ndimage.maximum_filter1d(grown, size, axis=1, mode="constant", cval=0)


def near_rows(mask_rows: Callable[[int, int], np.ndarray], metres: float, res: float, out: np.ndarray,
              rows: int) -> np.ndarray:
    """near() in strips of `rows` rows into out (a new boolean grid, memory-mapped, all False: a strip
    with nothing near it is left as it is), returned: mask_rows(r0, r1) gives the rows [r0, r1) of the
    mask; each strip is computed from the rows within n of it, so every pixel gets what near() gives on
    the whole grid (tests/test_units.py::test_near_rows_as_near)."""
    from scipy import ndimage
    n = max(1, math.ceil(metres / res)) if metres > 0 else 0
    size = 2 * n + 1
    for r0, r1, h0, h1 in strips(out.shape[0], rows, n):
        block = np.asarray(mask_rows(h0, h1), dtype=bool)
        if not block.any():
            continue
        if n:
            block = ndimage.maximum_filter1d(block, size, axis=0, mode="constant", cval=0)[r0 - h0:r1 - h0]
            block = ndimage.maximum_filter1d(block, size, axis=1, mode="constant", cval=0)
        out[r0:r1] = block
    return out


def water_with_data(z: np.ndarray, wbm: Optional[np.ndarray], sea_zone: Optional[np.ndarray],
                    sea_value: Optional[float] = None) -> np.ndarray:
    """The water among the pixels of z that have data (fill_water's mask keeps it, the terrain's
    statistics leave it out, hypsometry.py): lakes of the water body mask wbm (measured by LiDAR),
    and the sea zone where the data give the sea: at most SEA_LEVEL_TOLERANCE high (about 0 m,
    e.g. IGN Spain) or within SEA_FILL_EPS of sea_value (the provider's constant, Source.sea_fill).
    None for a mask: none of that water."""
    water = np.zeros(z.shape, bool)
    if wbm is not None:
        water |= wbm == LAKE
    if sea_zone is not None:
        with np.errstate(invalid="ignore"):
            sea_level = z <= SEA_LEVEL_TOLERANCE
            if sea_value is not None:
                sea_level |= (z >= sea_value - SEA_FILL_EPS) & (z <= sea_value + SEA_FILL_EPS)
        water |= sea_zone & sea_level
    return water & np.isfinite(z)


def fill_shore_from_surface(elevation_path: str, surface_path: str, grid: Grid, sea_zone: np.ndarray,
                            out_path: str, sea_value: Optional[float] = None, rows: Optional[int] = None) -> Tuple[str, int]:
    """Give the shore faces the terrain model lacks the heights of the surface model.

    LiDAR terrain models often have no data on the lower part of a sea cliff (no ground
    returns on the face), while the surface model has it, and on bare rock it is the
    terrain (Malta 2018: within 1 m on 84% of the coast's pixels). Left to fill_water, the
    face would be sea at 0 m, a wall from the terrain's last pixel straight down (26 500
    pixels above 20 m along Malta's and Gozo's coasts, 2026-11-04). In sea_zone (the sea
    mask grown by --shore-buffer), where the terrain has no data:
    - the surface model's sea surface (water_with_data on it: at most SEA_LEVEL_TOLERANCE,
      or sea_value) stays for fill_water: that is the exact shoreline, more exact than the
      mapped coastline, which runs along the cliff's top edge at times;
    - the pixels above it are reached from the terrain's data edge one pixel at a time
      (8 neighbours), each at most FACE_TOLERANCE above the neighbour it is reached from:
      a face runs down from the edge; a ship at a quay, a mole or a boulder standing up
      from the water is never reached and stays for fill_water too.
    Writes the reached pixels' surface heights into the terrain and saves their mask to
    out_path (they are filled data, not water: search.prepare_data joins the mask with the
    gaps' for the lines' filled_m, never for the seams without anchors: the anchors at a
    cliff's top edge stand right next to its face). Returns (out_path, pixels filled).
    The candidates are found strip by strip (rows: step 1 in strips, the mask memory-mapped;
    None: the grid at once, the mask saved) and the rest works on their indices: numpy only
    (the quick lane runs it too). Nothing without a surface model (prepare_data calls it with one).
    """
    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r")
    progress.compute.start("shore from surface", 1, unit="step")
    height, width = elevation.shape
    # The candidates' flat indices: no terrain, in the zone, the surface model above its sea surface
    parts = []
    for r0, r1, _, _ in strips(height, rows or height):
        z, s = np.asarray(elevation[r0:r1]), np.asarray(surface[r0:r1])
        zone = np.asarray(sea_zone[r0:r1], dtype=bool)
        candidates = np.isnan(z) & zone & np.isfinite(s) & ~water_with_data(s, None, zone, sea_value)
        parts.append(np.flatnonzero(candidates) + r0 * width)
        del z, s, zone, candidates
    idx = np.concatenate(parts) if parts else np.zeros(0, np.int64)
    del parts
    count = 0
    done = None
    if idx.size:
        ri, ci = np.divmod(idx, width)
        h = np.asarray(surface).ravel()[idx].astype(np.float64)
        z = np.asarray(elevation).ravel()
        offsets = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]
        # Each candidate's neighbours: their flat index, and their position among the candidates
        neighbours = []
        for dr, dc in offsets:
            ok = (ri + dr >= 0) & (ri + dr < height) & (ci + dc >= 0) & (ci + dc < width)
            flat = np.where(ok, idx + dr * width + dc, 0)
            at = np.searchsorted(idx, flat)
            at[at == idx.size] = 0
            inside = ok & (idx[at] == flat)
            neighbours.append((ok, flat, np.where(inside, at, -1)))
        # The terrain's data edge: the highest terrain next to each candidate
        reached = np.full(idx.size, -np.inf)
        for ok, flat, at in neighbours:
            edge = np.where(ok, z[flat], np.nan)
            edge = np.where(np.isfinite(edge) & (at < 0), edge, -np.inf)
            np.maximum(reached, edge, out=reached)
        del z
        done = h <= reached + FACE_TOLERANCE
        while True:
            # Downwards from the pixels accepted so far
            best = np.full(idx.size, -np.inf)
            for ok, flat, at in neighbours:
                place = np.maximum(at, 0)
                np.maximum(best, np.where((at >= 0) & done[place], h[place], -np.inf), out=best)
            new = ~done & (h <= best + FACE_TOLERANCE)
            if not new.any():
                break
            done |= new
        count = int(done.sum())
    face = new_mask(out_path, (height, width)) if rows is not None else np.zeros((height, width), bool)
    if count:
        elevation[ri[done], ci[done]] = h[done].astype(elevation.dtype)
        flush_grid(elevation)
        face[ri[done], ci[done]] = True
    if rows is not None:
        flush_grid(face)
        del face
    else:
        np.save(out_path, face)
    progress.compute.update(1)
    progress.compute.finish(f"{count} px")
    return out_path, count


def shore_rows(elevation: np.ndarray, water: np.ndarray, face: Optional[np.ndarray], r0: int, r1: int,
               rim_min: float = SHORE_RIM_MIN) -> np.ndarray:
    """The kinds of the uncertain shore in rows [r0, r1) of the grids after fill_water (uint8):
    SHORE_SURFACE on the pixels of `face` (the face taken from the surface model by
    fill_shore_from_surface), SHORE_SEA on the water pixels (`water`, the filled sea and lakes
    and the water with data) whose neighbour (8) with the terrain's own data (not a face: the
    foot of a face taken from the surface model is as good as the data get) stands more than
    rim_min above them: the terrain model ends on a cliff above the water, and the fill stands in
    for its foot (the sea cliffs of sources without a surface model; what a person sees in the 3D
    view as a wall straight down to the water), 0 elsewhere. The rows next to the strip are read
    for the neighbours."""
    from scipy import ndimage
    h0, h1 = max(0, r0 - 1), min(elevation.shape[0], r1 + 1)
    z = np.asarray(elevation[h0:h1], dtype=np.float32)
    wet = np.asarray(water[h0:h1], dtype=bool)
    own = np.isfinite(z) & ~wet
    faces = np.asarray(face[h0:h1], dtype=bool) if face is not None else None
    if faces is not None:
        own &= ~faces
    highest = ndimage.maximum_filter(np.where(own, z, -np.inf), 3, mode="constant", cval=-np.inf)
    kinds = np.zeros(z.shape, np.uint8)
    with np.errstate(invalid="ignore"):
        kinds[wet & np.isfinite(z) & (highest - z > rim_min)] = SHORE_SEA
    if faces is not None:
        kinds[faces] = SHORE_SURFACE
    return kinds[r0 - h0:r1 - h0]


def shore_segments(elevation_path: str, water_path: str, face_path: Optional[str], grid: Grid,
                   rows: Optional[int] = None, rim_min: float = SHORE_RIM_MIN) -> dict:
    """The uncertain shore of a search as segments for its run (run.json and data.js "shore"):
    the regions of each kind of shore_rows grown by SHORE_BAND pixels each way (so a shore's
    scattered pixels join into one band and draw as a stroke), 8-connected, found strip by strip
    and joined, their outlines simplified by SHORE_SIMPLIFY pixels in WGS84, with the band's
    pixels and its length in metres: the band taken as a rectangle of its area and outline, the
    longer side less the growth (about the length along the shore). Segments shorter than
    SHORE_MIN_M are left out (the totals count every pixel of a kind, and the segments listed).
    {"rim_min": rim_min, "segments": [{"kind": "surface"|"sea", "px", "m", "ring": [[lon, lat], ...]}, ...]
    (the longest first), "totals": {"surface_m", "sea_m", "surface_px", "sea_px"}}."""
    from pyproj import Transformer
    from rasterio.features import shapes
    from rasterio.transform import Affine
    from shapely import normalize
    from shapely.geometry import shape
    from shapely.ops import unary_union

    elevation = np.load(elevation_path, mmap_mode="r")
    water = np.load(water_path, mmap_mode="r")
    face = np.load(face_path, mmap_mode="r") if face_path else None
    height, width = elevation.shape
    names = {SHORE_SURFACE: "surface", SHORE_SEA: "sea"}
    polygons = {kind: [] for kind in names}
    pixels = {kind: 0 for kind in names}
    from scipy import ndimage
    size = 2 * SHORE_BAND + 1
    for r0, r1, _, _ in strips(height, rows or height):
        h0, h1 = max(0, r0 - SHORE_BAND), min(height, r1 + SHORE_BAND)
        kinds = shore_rows(elevation, water, face, h0, h1, rim_min)
        if not kinds.any():
            continue
        for kind in names:
            pixels[kind] += int((kinds[r0 - h0:r1 - h0] == kind).sum())
        transform = grid.transform @ Affine.translation(0, r0)
        for kind in names:  # each kind's band: its pixels grown SHORE_BAND each way
            band = ndimage.maximum_filter(kinds == kind, size, mode="constant", cval=0)[r0 - h0:r1 - h0]
            if band.any():
                for geometry, _ in shapes(band.astype(np.uint8), mask=band, transform=transform, connectivity=8):
                    polygons[kind].append(shape(geometry))
    to_wgs = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform
    segments = []
    grown = 2 * SHORE_BAND * grid.res
    for kind, name in names.items():
        if not polygons[kind]:
            continue
        joined = normalize(unary_union(polygons[kind]))  # the strips' pieces of one band joined, canonical
        for polygon in (joined.geoms if hasattr(joined, "geoms") else [joined]):
            # The band as a rectangle of its area A and outline P: the longer side is P/4 + sqrt(P^2/16 - A)
            quarter = polygon.length / 4
            longer = quarter + math.sqrt(max(quarter * quarter - polygon.area, 0.0))
            metres = max(0, int(round(longer - grown)))
            if metres < SHORE_MIN_M:
                continue
            simple = polygon.simplify(SHORE_SIMPLIFY * grid.res, preserve_topology=True)
            if simple.is_empty or simple.geom_type != "Polygon":
                simple = polygon
            ring = [[round(lon, 6), round(lat, 6)] for lon, lat in (to_wgs(x, y) for x, y in simple.exterior.coords)]
            segments.append({"kind": name, "px": int(round(polygon.area / grid.res ** 2)), "m": metres, "ring": ring})
    segments.sort(key=lambda s: -s["m"])
    totals = {f"{name}_m": sum(s["m"] for s in segments if s["kind"] == name) for name in names.values()}
    totals.update({f"{name}_px": pixels[kind] for kind, name in names.items()})
    return {"rim_min": rim_min, "segments": segments, "totals": totals}


def fill_water(elevation_path: str, surface_path: Optional[str], grid: Grid, wbm: np.ndarray,
               sea_zone: np.ndarray, out_path: str, sea_value: Optional[float] = None,
               rows: Optional[int] = None, bare_path: Optional[str] = None) -> str:
    """Give the sea and lakes an elevation where the data has none.

    National LiDAR models have no data over water, so lines across the sea (and
    the edges of sea cliffs, whose slope needs the neighbouring pixels) would be
    missed. Pixels without data in sea_zone (the sea mask of coast.py grown by
    --shore-buffer, see near) get 0 m. Pixels without data next to lakes of the
    Copernicus mask (within SHORE_BUFFER, as the mask is 30 m) get the level of
    the lake's shore (the median elevation around it). The exact shoreline comes
    from the elevation data itself; gaps in the data on land stay without data.
    Saves a boolean water mask (filled pixels, lakes that have data, and the sea where
    the data give it: at most SEA_LEVEL_TOLERANCE, or the source's constant sea_value)
    to out_path.
    rows: in strips of that many rows (wbm and sea_zone memory-mapped grids), the lakes' labels
    the one array of the whole grid; bare_path then gets the mask of the pixels filled (water
    where the terrain model had none: obstacles.py's bare pixels). The same values
    (tests/test_units.py::test_fill_water_rows_as_before).
    """
    from scipy import ndimage

    if rows is not None:
        return _fill_water_rows(elevation_path, surface_path, grid, wbm, sea_zone, out_path, sea_value, rows,
                                bare_path)
    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r+") if surface_path else None
    progress.compute.start("filling sea and lakes", 3, unit="step")
    progress.compute.update(0, part="sea")
    empty = np.isnan(elevation)
    sea_fill = empty & sea_zone
    progress.compute.update(1, part="lakes")
    lake = empty & near(wbm == LAKE, SHORE_BUFFER, grid.res) & ~sea_fill
    progress.compute.update(1, part="levels")

    elevation[sea_fill] = 0.0
    if surface is not None:
        surface[sea_fill & np.isnan(surface)] = 0.0
    water = sea_fill.copy()
    lake_px = 0
    labels, _ = ndimage.label(lake, structure=np.ones((3, 3)))
    for index, region in enumerate(ndimage.find_objects(labels), 1):
        if region is None:
            continue
        rows = slice(max(region[0].start - 1, 0), region[0].stop + 1)
        cols = slice(max(region[1].start - 1, 0), region[1].stop + 1)
        area = labels[rows, cols] == index
        shore = ndimage.binary_dilation(area) & ~empty[rows, cols]
        heights = elevation[rows, cols][shore]
        heights = heights[np.isfinite(heights)]
        if heights.size == 0:
            continue
        level = float(np.median(heights))
        block = elevation[rows, cols]
        block[area] = level
        if surface is not None:
            sblock = surface[rows, cols]
            sblock[area & np.isnan(sblock)] = level
        water[rows, cols] |= area
        lake_px += int(area.sum())
    # Water that the elevation data covers: lakes measured by LiDAR, and sea given as
    # about 0 m by the data itself (e.g. IGN Spain) or as the provider's constant (sea_value, Source.sea_fill)
    water |= water_with_data(np.asarray(elevation), wbm, sea_zone, sea_value) & ~empty
    flush_grid(elevation)
    if surface is not None:
        flush_grid(surface)
    np.save(out_path, water)
    progress.compute.update(1)
    km2 = lambda px: px * grid.res ** 2 / 1e6
    progress.compute.finish(f"sea {km2(int(sea_fill.sum())):.2f} km², lakes {km2(lake_px):.2f} km²")
    return out_path


def new_mask(path: str, shape: Tuple[int, int]) -> np.ndarray:
    """A boolean grid memory-mapped at path (a temporary of step 1 in strips), False everywhere."""
    return np.lib.format.open_memmap(path, mode="w+", dtype=bool, shape=shape)


def rasterize_into(geometries, grid: Grid, out: np.ndarray, all_touched: bool = False) -> np.ndarray:
    """The pixels of the geometries (shapely, the grid's CRS) burned into out, a boolean grid of the
    grid memory-mapped (set True there, the rest left as it is; empty geometries skipped): what
    rasterio.features.rasterize gives for the whole grid, written into the mapping (no array of
    the grid in memory). all_touched as rasterize's (geometry_mask's footprint of border_gaps)."""
    from rasterio.features import rasterize
    from shapely.geometry import mapping
    shapes = [(mapping(g), 1) for g in geometries if not g.is_empty]
    if shapes:
        rasterize(shapes, out=out.view(np.uint8), transform=grid.transform, all_touched=all_touched)
    return out


def remove_grid(path: str):
    """Remove a temporary grid; on Windows a mapping still open keeps it (the work folder goes anyway)."""
    try:
        os.remove(path)
    except OSError:
        pass


def _fill_water_rows(elevation_path: str, surface_path: Optional[str], grid: Grid, wbm: np.ndarray,
                     sea_zone: np.ndarray, out_path: str, sea_value: Optional[float], rows: int,
                     bare_path: Optional[str]) -> str:
    """fill_water in strips of rows (its values): the sea and the lake mask strip by strip, the
    lakes' labels over the whole grid (none without a lake to fill), each lake's level from its own
    box as before, the water with data strip by strip. Masks start all False: a strip with nothing
    to mark is not written (a tile of the country layer without water writes neither)."""
    from scipy import ndimage

    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r+") if surface_path else None
    shape = elevation.shape
    progress.compute.start("filling sea and lakes", 3, unit="step")
    progress.compute.update(0, part="sea")
    water = new_mask(out_path, shape)
    lake_path = os.path.join(os.path.dirname(out_path), "lake.npy")
    lake = new_mask(lake_path, shape)
    n = max(1, math.ceil(SHORE_BUFFER / grid.res))
    size = 2 * n + 1
    sea_px = 0
    any_lake = False
    for r0, r1, h0, h1 in strips(shape[0], rows, n):
        empty = np.isnan(elevation[r0:r1])
        sea_fill = empty & np.asarray(sea_zone[r0:r1], dtype=bool)
        # near(wbm == LAKE, SHORE_BUFFER) of the strip from the rows within n of it (near_rows)
        shore = np.asarray(wbm[h0:h1]) == LAKE
        if shore.any():
            shore = ndimage.maximum_filter1d(shore, size, axis=0, mode="constant", cval=0)[r0 - h0:r1 - h0]
            shore = ndimage.maximum_filter1d(shore, size, axis=1, mode="constant", cval=0)
            here = empty & shore & ~sea_fill
            if here.any():
                lake[r0:r1] = here
                any_lake = True
        del empty, shore
        if sea_fill.any():
            block = elevation[r0:r1]
            block[sea_fill] = 0.0
            if surface is not None:
                sblock = surface[r0:r1]
                sblock[sea_fill & np.isnan(sblock)] = 0.0
            water[r0:r1] = sea_fill
            sea_px += int(sea_fill.sum())
    progress.compute.update(1, part="lakes")
    if any_lake:
        labels = np.zeros(shape, np.int32)  # the one array of the whole grid
        ndimage.label(lake, structure=np.ones((3, 3)), output=labels)
    del lake
    remove_grid(lake_path)
    progress.compute.update(1, part="levels")
    lake_px = 0
    for index, region in enumerate(ndimage.find_objects(labels) if any_lake else (), 1):
        if region is None:
            continue
        box_rows = slice(max(region[0].start - 1, 0), region[0].stop + 1)
        cols = slice(max(region[1].start - 1, 0), region[1].stop + 1)
        area = labels[box_rows, cols] == index
        # The pixels empty before any filling: without data still, or filled so far (the sea, the
        # lakes done: water holds exactly those)
        empty = np.isnan(elevation[box_rows, cols]) | np.asarray(water[box_rows, cols])
        shore = ndimage.binary_dilation(area) & ~empty
        heights = elevation[box_rows, cols][shore]
        heights = heights[np.isfinite(heights)]
        if heights.size == 0:
            continue
        level = float(np.median(heights))
        block = elevation[box_rows, cols]
        block[area] = level
        if surface is not None:
            sblock = surface[box_rows, cols]
            sblock[area & np.isnan(sblock)] = level
        water[box_rows, cols] |= area
        lake_px += int(area.sum())
    labels = None
    bare = new_mask(bare_path, shape) if bare_path else None
    for r0, r1, _, _ in strips(shape[0], rows):
        if bare is not None:
            bare[r0:r1] = water[r0:r1]  # what was filled: the sea and the lakes without data
        # Water that the elevation data covers (as fill_water: the pixels filled are in water already)
        with_data = water_with_data(np.asarray(elevation[r0:r1]), wbm[r0:r1], sea_zone[r0:r1], sea_value)
        if with_data.any():
            water[r0:r1] |= with_data
    flush_grid(elevation)
    if surface is not None:
        flush_grid(surface)
    flush_grid(water)
    if bare is not None:
        flush_grid(bare)
    del water, bare
    progress.compute.update(1)
    km2 = lambda px: px * grid.res ** 2 / 1e6
    progress.compute.finish(f"sea {km2(sea_px):.2f} km², lakes {km2(lake_px):.2f} km²")
    return out_path


def fill_gaps(elevation_path: str, surface_path: Optional[str], grid: Grid, fallback: "Source",
              cache_dir: str, out_path: str, update: Optional[str] = None,
              exclude: Optional[np.ndarray] = None, name: str = "gap",
              window: Optional[Tuple[slice, slice]] = None, surface_from_terrain: bool = True,
              rows: Optional[int] = None, resampling: Optional[str] = None,
              same_resolution: Optional[str] = None) -> Tuple[str, int, int]:
    """Fill the remaining gaps in the data on land from another source.

    Each gap gets the other source shifted by the median height difference in a
    ring of pixels around that gap, so it joins its surroundings without a step
    (different surveys and height systems differ by up to a few metres). Only
    gentle slopes are used for this: on a cliff, a shift of a metre between two
    surveys changes the height by tens of metres. A local offset more than
    GAP_MAX_LOCAL_SHIFT from the overall median is not trusted.
    Saves a boolean mask of the filled pixels to out_path; returns (out_path, the terrain
    pixels filled, the pixels written to either grid). Pixels in `exclude` (the sea) are left alone.
    The fallback's grids are saved next to out_path as <name>_nmt.npy and <name>_nmpt.npy.
    window (rows, columns): the fallback is brought onto that part of the grid only (a
    neighbour: around the gaps at the border), nothing is filled outside it. Without a surface
    model of its own the fallback fills the surface gaps from its terrain, unless
    surface_from_terrain is False (a neighbour: they are left to the next source). A layer
    that filled no pixel is left out of the record of the data used (used_data).
    rows: in strips of that many rows (exclude a memory-mapped grid; the gap masks memory-mapped
    next to out_path while a pair is filled, the labels of its gaps the one array of the whole
    grid: _fill), the same values. resampling, same_resolution: how the fallback's rasters are
    reprojected (mosaic.build_mosaic's; None: its own choice).
    """
    if rows is not None:
        return _fill_gaps_rows(elevation_path, surface_path, grid, fallback, cache_dir, out_path, update, exclude,
                               name, window, surface_from_terrain, rows, resampling, same_resolution)
    work = os.path.dirname(out_path)
    elevation = np.load(elevation_path, mmap_mode="r+")
    filled = np.isnan(elevation)
    if exclude is not None:
        filled &= ~exclude
    if not filled.any():
        np.save(out_path, filled)
        return out_path, 0, 0
    written = 0
    pairs = [(elevation, fallback.nmt, f"{name}_nmt.npy", "terrain")]
    if surface_path:
        surface = np.load(surface_path, mmap_mode="r+")
        layer = fallback.nmpt or (fallback.nmt if surface_from_terrain else None)
        if layer is not None:
            pairs.append((surface, layer, f"{name}_nmpt.npy", "surface"))
    sub = _subgrid(grid, window) if window is not None else grid
    for target, layer, name, which in pairs:
        gaps = np.isnan(target) if exclude is None else np.isnan(target) & ~exclude
        if not gaps.any():
            continue
        # A neighbour has no data beyond its border: no line about its tiles without data
        path = prepare_layer(layer, sub, cache_dir, os.path.join(work, name), f"gap fill ({fallback.name})", update,
                             quiet=window is not None, resampling=resampling, same_resolution=same_resolution)
        record = used_data[-1]  # prepare_layer's
        if window is None:
            other = np.asarray(np.load(path, mmap_mode="r"))
        else:
            other = np.full(target.shape, np.nan, np.float32)
            other[window] = np.load(path, mmap_mode="r")
        count = _fill(target, other, gaps, grid.res, f"gap filling ({fallback.name}): {which}")
        written += count
        if count == 0:
            used_data[:] = [entry for entry in used_data if entry is not record]  # no credit either
        del other, gaps  # before the next pair's mosaic
    filled &= np.isfinite(elevation)
    np.save(out_path, filled)
    return out_path, int(filled.sum()), written


def _gaps_rows(target: np.ndarray, exclude: Optional[np.ndarray], out: np.ndarray, rows: int) -> bool:
    """The gaps of target (NaN, outside exclude) into out (a new mask: a strip without gaps stays
    pages nothing ever wrote), strip by strip; whether there is any."""
    found = False
    for r0, r1, _, _ in strips(target.shape[0], rows):
        gaps = np.isnan(target[r0:r1])
        if exclude is not None:
            gaps &= ~np.asarray(exclude[r0:r1], dtype=bool)
        if gaps.any():
            out[r0:r1] = gaps
            found = True
    return found


def _fill_gaps_rows(elevation_path: str, surface_path: Optional[str], grid: Grid, fallback: "Source",
                    cache_dir: str, out_path: str, update: Optional[str], exclude: Optional[np.ndarray],
                    name: str, window: Optional[Tuple[slice, slice]], surface_from_terrain: bool,
                    rows: int, resampling: Optional[str] = None,
                    same_resolution: Optional[str] = None) -> Tuple[str, int, int]:
    """fill_gaps in strips of rows (its values)."""
    work = os.path.dirname(out_path)
    elevation = np.load(elevation_path, mmap_mode="r+")
    filled = new_mask(out_path, elevation.shape)
    if not _gaps_rows(elevation, exclude, filled, rows):
        flush_grid(filled)
        return out_path, 0, 0
    written = 0
    pairs = [(elevation, fallback.nmt, f"{name}_nmt.npy", "terrain", filled)]  # the terrain's gaps: filled so far
    if surface_path:
        surface = np.load(surface_path, mmap_mode="r+")
        layer = fallback.nmpt or (fallback.nmt if surface_from_terrain else None)
        if layer is not None:
            pairs.append((surface, layer, f"{name}_nmpt.npy", "surface", None))
    sub = _subgrid(grid, window) if window is not None else grid
    for target, layer, file, which, gaps in pairs:
        gaps_path = None
        if gaps is None:
            gaps_path = os.path.join(work, f"{name}_{which}_gaps.npy")
            gaps = new_mask(gaps_path, target.shape)
            if not _gaps_rows(target, exclude, gaps, rows):
                del gaps
                remove_grid(gaps_path)
                continue
        # A neighbour has no data beyond its border: no line about its tiles without data
        path = prepare_layer(layer, sub, cache_dir, os.path.join(work, file), f"gap fill ({fallback.name})", update,
                             quiet=window is not None, rows=rows, resampling=resampling,
                             same_resolution=same_resolution)
        record = used_data[-1]  # prepare_layer's
        other = np.load(path, mmap_mode="r")
        count = _fill(target, other, gaps, grid.res, f"gap filling ({fallback.name}): {which}", rows=rows,
                      window=window, work=work)
        written += count
        if count == 0:
            used_data[:] = [entry for entry in used_data if entry is not record]  # no credit either
        del other, gaps  # before the next pair's mosaic
        if gaps_path:
            remove_grid(gaps_path)
    count = 0
    for r0, r1, _, _ in strips(elevation.shape[0], rows):
        block = filled[r0:r1]
        block &= np.isfinite(elevation[r0:r1])
        count += int(block.sum())
    flush_grid(filled)
    del filled
    return out_path, count, written


def _subgrid(grid: Grid, window: Tuple[slice, slice]) -> Grid:
    """The part of the grid in window (rows, columns), its tiles those under the grid's own
    footprint (the area, or the circle inscribed in the grid) within that part."""
    from shapely.geometry import box
    rows, cols = window
    sub = Grid(left=grid.left + cols.start * grid.res, top=grid.top - rows.start * grid.res, res=grid.res,
               height=rows.stop - rows.start, width=cols.stop - cols.start, crs=grid.crs)
    sub.area_shape = box(*sub.bounds).intersection(_footprint_shape(grid))
    return sub


def _footprint_shape(grid: Grid):
    """The outline the grid's data tiles are picked under (sources/indexes/tilings.py): its area,
    or the circle inscribed in its box."""
    from shapely.geometry import Point
    if grid.area_shape is not None:
        return grid.area_shape
    left, bottom, right, top = grid.bounds
    return Point((left + right) / 2, (bottom + top) / 2).buffer(min(right - left, top - bottom) / 2)


def _fill(target: np.ndarray, other: np.ndarray, gaps: np.ndarray, res: float, label: str = "gap filling",
          rows: Optional[int] = None, window: Optional[Tuple[slice, slice]] = None,
          work: Optional[str] = None) -> int:
    """Fill the gaps of target (a memory-mapped grid) from other, each gap shifted to the heights
    around it (fill_gaps); returns the number of pixels filled. A Compute bar `label` of three
    parts: the slopes (where the offsets may be matched), the rings around the gaps, the medians.
    rows: in strips of that many rows (_fill_rows: other the grid of `window` (rows, columns) of
    target, or of the whole grid; gaps a memory-mapped mask; a mask of the matched pixels
    memory-mapped in `work` meanwhile): the same values (tests/test_units.py::test_fill_rows_as_before)."""
    from scipy import ndimage

    if rows is not None:
        return _fill_rows(target, other, gaps, res, label, rows, window, work)
    values = np.asarray(target)
    progress.compute.start(label, 3, unit="step")
    progress.compute.update(0, part="slopes")
    finite = np.isfinite(values)
    gy, gx = np.gradient(np.where(finite, values, other), res)
    # The slope in degrees, computed in place in gx (the same ufuncs on the same float32 values as
    # np.degrees(np.arctan(np.hypot(gx, gy))), one array less); the gradients serve only this
    np.hypot(gx, gy, out=gx)
    np.arctan(gx, out=gx)
    np.degrees(gx, out=gx)
    flat = gx < GAP_MATCH_SLOPE
    del gx, gy
    both = ~gaps & finite & np.isfinite(other) & flat
    del finite, flat
    # The differences are a temporary: the median may partition them in place
    overall = float(np.median(values[both] - other[both], overwrite_input=True)) if both.any() else 0.0
    # Offset of every gap from the ring of pixels around it
    progress.compute.update(1, part="rings")
    labels, count = ndimage.label(gaps, structure=np.ones((3, 3)))
    ring = ndimage.grey_dilation(labels, size=(GAP_RING * 2 + 1,) * 2)
    ring *= both & (labels == 0)  # integers, in place
    del both
    offsets = np.full(count + 1, overall)
    progress.compute.update(1, part="medians")
    if ring.any():
        # Only the ring pixels: scipy sorts every pixel it is given (10 s for a 58 Mpx tile)
        near = ring > 0
        local = ndimage.median(values[near] - other[near], ring[near], index=np.arange(1, count + 1))
        local = np.asarray(local, dtype=float)
        # A local offset far from the overall one comes from misaligned edges, not heights
        usable = np.isfinite(local) & (np.abs(local - overall) <= GAP_MAX_LOCAL_SHIFT)
        offsets[1:] = np.where(usable, local, overall)
    count = int((gaps & np.isfinite(other)).sum())
    target[gaps] = other[gaps] + offsets[labels[gaps]]
    flush_grid(target)
    progress.compute.update(1)
    progress.compute.finish(f"{count} px")
    return count


def _window_rows(other: np.ndarray, window: Optional[Tuple[slice, slice]], r0: int, r1: int, width: int) -> np.ndarray:
    """Rows [r0, r1) of a layer brought onto the grid: other, a grid of the whole grid, or of
    window (rows, columns) of it, NaN outside (fill_gaps' window of a neighbour); float32."""
    if window is None:
        return np.asarray(other[r0:r1])
    wr, wc = window
    block = np.full((r1 - r0, width), np.nan, np.float32)
    a, b = max(r0, wr.start), min(r1, wr.stop)
    if a < b:
        block[a - r0:b - r0, wc] = other[a - wr.start:b - wr.start]
    return block


def _fill_rows(target: np.ndarray, other: np.ndarray, gaps: np.ndarray, res: float, label: str, rows: int,
               window: Optional[Tuple[slice, slice]], work: Optional[str]) -> int:
    """_fill in strips of rows: the slopes with a row of halo, the matched pixels (`both`) kept
    memory-mapped, the overall offset an exact selection over the strips (_median_of), the
    rings with GAP_RING rows of halo and only their pixels collected for the medians, the gaps
    filled strip by strip; the labels of the gaps the one array of the whole grid."""
    from scipy import ndimage

    height, width = target.shape
    other_rows = lambda r0, r1: _window_rows(other, window, r0, r1, width)
    both_path = os.path.join(work or os.path.dirname(getattr(target, "filename", "") or "."), "both.npy")
    both = new_mask(both_path, (height, width))
    progress.compute.start(label, 3, unit="step")
    progress.compute.update(0, part="slopes")
    keys = _KeyRange()
    for r0, r1, h0, h1 in strips(height, rows, 1):
        values = np.asarray(target[h0:h1])
        o = other_rows(h0, h1)
        finite = np.isfinite(values)
        gy, gx = np.gradient(np.where(finite, values, o), res)
        np.hypot(gx, gy, out=gx)  # the slope in place, as _fill
        np.arctan(gx, out=gx)
        np.degrees(gx, out=gx)
        flat = gx < GAP_MATCH_SLOPE
        del gx, gy
        matched = (~np.asarray(gaps[h0:h1], dtype=bool) & finite & np.isfinite(o) & flat)[r0 - h0:r1 - h0]
        del finite, flat
        both[r0:r1] = matched
        with np.errstate(invalid="ignore"):
            keys.add((values[r0 - h0:r1 - h0] - o[r0 - h0:r1 - h0])[matched])
        del values, o, matched

    def diffs():  # the differences of the matched pixels, strip by strip (read again per pass)
        for r0, r1, _, _ in strips(height, rows):
            matched = np.asarray(both[r0:r1])
            if matched.any():
                with np.errstate(invalid="ignore"):
                    yield (np.asarray(target[r0:r1]) - other_rows(r0, r1))[matched]

    overall = _median_of(diffs, keys) if keys.n else 0.0
    # Offset of every gap from the ring of pixels around it
    progress.compute.update(1, part="rings")
    labels = np.zeros((height, width), np.int32)  # the one array of the whole grid
    count = ndimage.label(gaps, structure=np.ones((3, 3)), output=labels)
    ring_labels, ring_diffs = [], []
    for r0, r1, h0, h1 in strips(height, rows, GAP_RING):
        ring = ndimage.grey_dilation(labels[h0:h1], size=(GAP_RING * 2 + 1,) * 2)[r0 - h0:r1 - h0]
        ring *= np.asarray(both[r0:r1]) & (labels[r0:r1] == 0)  # integers, in place
        near = ring > 0
        if near.any():
            ring_labels.append(ring[near])
            with np.errstate(invalid="ignore"):
                ring_diffs.append((np.asarray(target[r0:r1]) - other_rows(r0, r1))[near])
        del ring, near
    del both
    remove_grid(both_path)
    offsets = np.full(count + 1, overall)
    progress.compute.update(1, part="medians")
    if ring_labels:
        local = ndimage.median(np.concatenate(ring_diffs), np.concatenate(ring_labels), index=np.arange(1, count + 1))
        local = np.asarray(local, dtype=float)
        # A local offset far from the overall one comes from misaligned edges, not heights
        usable = np.isfinite(local) & (np.abs(local - overall) <= GAP_MAX_LOCAL_SHIFT)
        offsets[1:] = np.where(usable, local, overall)
    del ring_labels, ring_diffs
    filled = 0
    for r0, r1, _, _ in strips(height, rows):
        g = np.asarray(gaps[r0:r1], dtype=bool)
        if not g.any():
            continue
        o = other_rows(r0, r1)
        filled += int((g & np.isfinite(o)).sum())
        block = target[r0:r1]
        block[g] = o[g] + offsets[labels[r0:r1][g]]
    flush_grid(target)
    progress.compute.update(1)
    progress.compute.finish(f"{filled} px")
    return filled


def _keys(values: np.ndarray) -> np.ndarray:
    """The float32 values as int64 keys in their order (-0.0 just below 0.0): the bits, those of
    a negative value reversed."""
    bits = np.asarray(values, dtype=np.float32).view(np.int32).astype(np.int64)
    return np.where(bits < 0, -(bits & 0x7FFFFFFF) - 1, bits)


def _key_value(key: int) -> np.float32:
    """The float32 value of a key of _keys."""
    bits = key if key >= 0 else (-(key + 1)) | -0x80000000
    return np.array([bits], np.int32).view(np.float32)[0]


class _KeyRange:
    """How many values _keys saw and the smallest and largest key."""

    def __init__(self):
        self.n, self.lo, self.hi = 0, None, None

    def add(self, values: np.ndarray):
        if values.size:
            keys = _keys(values)
            self.n += values.size
            lo, hi = int(keys.min()), int(keys.max())
            self.lo = lo if self.lo is None else min(self.lo, lo)
            self.hi = hi if self.hi is None else max(self.hi, hi)


def _median_of(chunks: Callable[[], Iterable[np.ndarray]], keys: _KeyRange) -> float:
    """np.median of the float32 values that chunks() yields (read again for each pass, never held
    whole): the middle value(s) by _select on their keys, the mean of two as np.median takes it."""
    k0, k1 = (keys.n - 1) // 2, keys.n // 2
    v0 = _select(chunks, k0, keys.lo, keys.hi)
    if k1 == k0:
        return float(v0)
    return float(np.median(np.array([v0, _select(chunks, k1, keys.lo, keys.hi)], np.float32)))


SELECT_BINS = 1 << 16   # bins of a pass of _select over the keys' range
SELECT_COLLECT = 1 << 22  # values of a bin collected and sorted at once (the last pass)


def _select(chunks: Callable[[], Iterable[np.ndarray]], k: int, lo: int, hi: int) -> np.float32:
    """The k-th smallest (from 0) of the float32 values chunks() yields, whose keys (_keys) lie in
    [lo, hi]: a histogram of SELECT_BINS bins over the keys' range finds the bin of the k-th, the
    range narrows to it until its values can be collected (SELECT_COLLECT) and sorted."""
    while lo < hi:
        width = -(-(hi - lo + 1) // SELECT_BINS)  # keys per bin, at least 1
        counts = np.zeros(SELECT_BINS, np.int64)
        for values in chunks():
            keys = _keys(values)
            keys = keys[(keys >= lo) & (keys <= hi)]
            counts += np.bincount((keys - lo) // width, minlength=SELECT_BINS)
        cum = np.cumsum(counts)
        b = int(np.searchsorted(cum, k, side="right"))  # the first bin whose count reaches past k
        k -= int(cum[b - 1]) if b else 0
        lo, hi = lo + b * width, min(hi, lo + (b + 1) * width - 1)
        if counts[b] <= SELECT_COLLECT:
            found = []
            for values in chunks():
                keys = _keys(values)
                found.append(np.asarray(values, dtype=np.float32)[(keys >= lo) & (keys <= hi)])
            return np.sort(np.concatenate(found))[k]
    return _key_value(lo)


def _or_rows(out_path: str, more_path: str, rows: int):
    """The mask at out_path |= the mask at more_path, strip by strip (both memory-mapped)."""
    out, more = np.load(out_path, mmap_mode="r+"), np.load(more_path, mmap_mode="r")
    for r0, r1, _, _ in strips(out.shape[0], rows):
        out[r0:r1] |= more[r0:r1]
    flush_grid(out)


def fill_gaps_chain(elevation_path: str, surface_path: Optional[str], grid: Grid, fallbacks: List["Source"],
                    cache_dir: str, out_path: str, update: Optional[str] = None,
                    exclude: Optional[np.ndarray] = None, rows: Optional[int] = None) -> Tuple[str, List[Tuple["Source", int]]]:
    """Fill the gaps on land from each fallback in turn (fill_gaps), each only what the ones
    before it left (most sources have one; Alaska: its IfSAR, then the 1/3″ DEM). Saves the
    mask of all filled pixels to out_path; returns (out_path, [(fallback, filled pixels)]).
    rows: in strips (fill_gaps), the masks joined strip by strip."""
    filled, counts = None, []
    for n, fallback in enumerate(fallbacks):
        step = out_path if n == 0 else f"{os.path.splitext(out_path)[0]}{n}.npy"
        _, pixels, _ = fill_gaps(elevation_path, surface_path, grid, fallback, cache_dir, step, update,
                                 exclude=exclude, name="gap" if n == 0 else f"gap{n}", rows=rows)
        counts.append((fallback, pixels))
        if rows is not None:
            if n and pixels:
                _or_rows(out_path, step, rows)
        elif n == 0:
            filled = np.load(step)
        elif pixels:
            filled |= np.load(step)
            np.save(out_path, filled)
    return out_path, counts


def _border_gaps_rows(elevation_path: str, surface_path: Optional[str], grid: Grid, exclude: Optional[np.ndarray],
                      out: np.ndarray, rows: int) -> np.ndarray:
    """border_gaps in strips of rows into out (a new boolean grid, memory-mapped, all False, returned):
    the footprint burned into a mapping, its edge strip by strip (a row of halo for the erosion; both
    kept memory-mapped next to out meanwhile), the labels of the gaps the one array of the whole grid."""
    from scipy import ndimage

    elevation = np.load(elevation_path, mmap_mode="r")
    surface = np.load(surface_path, mmap_mode="r") if surface_path else None
    height, width = elevation.shape
    found = False
    for r0, r1, _, _ in strips(height, rows):
        gaps = np.isnan(elevation[r0:r1])
        if surface is not None:
            gaps |= np.isnan(surface[r0:r1])
        if exclude is not None:
            gaps &= ~np.asarray(exclude[r0:r1], dtype=bool)
        if gaps.any():
            out[r0:r1] = gaps
            found = True
    if not found:
        return out
    # The footprint burned whole into a mapping (geometry_mask's pixels: GDAL's all_touched burn is
    # not the same strip by strip), its edge strip by strip (a row of halo for the erosion)
    footprint_path = os.path.join(os.path.dirname(out.filename), "footprint.npy")
    footprint = rasterize_into([_footprint_shape(grid)], grid, new_mask(footprint_path, (height, width)),
                               all_touched=True)
    edge_path = os.path.join(os.path.dirname(out.filename), "edge.npy")
    edge = new_mask(edge_path, (height, width))
    for r0, r1, h0, h1 in strips(height, rows, 1):
        block = np.asarray(footprint[h0:h1])
        inner = ndimage.binary_erosion(block, border_value=0)
        edge[r0:r1] = (block & ~inner)[r0 - h0:r1 - h0]
        out[r0:r1] &= block[r0 - h0:r1 - h0]
    del footprint, block  # the view closed before the delete, which would fail, and the grid go to the disk
    remove_grid(footprint_path)
    labels = np.zeros((height, width), np.int32)  # the one array of the whole grid
    count = ndimage.label(out, structure=np.ones((3, 3)), output=labels)
    if count:
        size = np.zeros(count + 1, np.int64)
        at_edge = np.zeros(count + 1, bool)
        for r0, r1, _, _ in strips(height, rows):
            part = labels[r0:r1]
            size += np.bincount(part.ravel(), minlength=count + 1)
            at_edge[np.unique(part[np.asarray(edge[r0:r1]) & np.asarray(out[r0:r1])])] = True
        keep = at_edge & (size * grid.res ** 2 >= NEIGHBOUR_MIN_GAP_M2)
        keep[0] = False
        for r0, r1, _, _ in strips(height, rows):
            out[r0:r1] = keep[labels[r0:r1]]
    del edge
    remove_grid(edge_path)
    return out


def border_gaps(elevation_path: str, surface_path: Optional[str], grid: Grid,
                exclude: Optional[np.ndarray] = None, rows: Optional[int] = None,
                out: Optional[np.ndarray] = None) -> np.ndarray:
    """The gaps on land (no terrain or no surface data, outside exclude: the sea) that may lie
    across a border: those reaching the edge of the grid's footprint (the area or the circle
    its tiles are picked under, and the edge of a tile of a large area), at least
    NEIGHBOUR_MIN_GAP_M2 large. A hole inside the data (a lake, a lost tile) is no border.
    rows: in strips of that many rows into out (a boolean grid, memory-mapped), the same pixels
    (tests/test_units.py::test_border_gaps_rows_as_whole)."""
    from rasterio.features import geometry_mask
    from scipy import ndimage

    if rows is not None:
        return _border_gaps_rows(elevation_path, surface_path, grid, exclude, out, rows)
    gaps = np.isnan(np.load(elevation_path, mmap_mode="r"))
    if surface_path:
        gaps |= np.isnan(np.load(surface_path, mmap_mode="r"))
    if exclude is not None:
        gaps &= ~exclude
    if not gaps.any():
        return gaps
    footprint = geometry_mask([_footprint_shape(grid)], (grid.height, grid.width), grid.transform,
                              invert=True, all_touched=True)
    gaps &= footprint
    edge = footprint & ~ndimage.binary_erosion(footprint, border_value=0)
    labels, count = ndimage.label(gaps, structure=np.ones((3, 3)))
    if not count:
        return gaps
    size = np.bincount(labels.ravel(), minlength=count + 1)
    keep = np.zeros(count + 1, bool)
    keep[np.unique(labels[edge & gaps])] = True
    keep &= size * grid.res ** 2 >= NEIGHBOUR_MIN_GAP_M2
    keep[0] = False
    return keep[labels]


def _box_ranges(neighbour: Source, grid: Grid) -> Optional[List[Tuple[int, int, int, int]]]:
    """The rows and columns (r0, r1, c0, c1) of the grid under each rough box of a neighbour
    (Source.offline, bbox); None for a neighbour without boxes (it may fill any border gap)."""
    boxes = [box for _, box in neighbour.offline] + ([neighbour.bbox] if neighbour.bbox else [])
    if not boxes:
        return None
    ranges = []
    for south, north, west, east in boxes:
        left, bottom, right, top = transform_bounds("EPSG:4326", grid.crs, west, south, east, north)
        c0, c1 = max(0, int((left - grid.left) // grid.res)), min(grid.width, int((right - grid.left) // grid.res) + 1)
        r0, r1 = max(0, int((grid.top - top) // grid.res)), min(grid.height, int((grid.top - bottom) // grid.res) + 1)
        if r0 < r1 and c0 < c1:
            ranges.append((r0, r1, c0, c1))
    return ranges


def neighbour_window(neighbour: Source, grid: Grid, gaps: np.ndarray,
                     rows: Optional[int] = None) -> Optional[Tuple[slice, slice]]:
    """The part of the grid (rows, columns) a neighbour fills: the border gaps (border_gaps)
    inside its rough boxes (Source.offline, bbox), with NEIGHBOUR_PAD pixels around them for
    the heights the offsets are matched with; None when no such gap lies inside them. Asks
    nothing of the neighbour's services: a neighbour far away is never queried. A neighbour
    without boxes may fill any border gap. rows: gaps read in strips of that many rows."""
    ranges = _box_ranges(neighbour, grid)
    if rows is None:
        inside = np.ones_like(gaps) if ranges is None else np.zeros_like(gaps)
        for r0, r1, c0, c1 in ranges or []:
            inside[r0:r1, c0:c1] = True
        reached = gaps & inside
        rows_, cols = np.flatnonzero(reached.any(axis=1)), np.flatnonzero(reached.any(axis=0))
        if not rows_.size:
            return None
        first_row, last_row, first_col, last_col = int(rows_[0]), int(rows_[-1]), int(cols[0]), int(cols[-1])
    else:
        first_row = last_row = first_col = last_col = None
        for r0, r1, _, _ in strips(grid.height, rows):
            reached = np.asarray(gaps[r0:r1], dtype=bool)
            if ranges is not None:
                inside = np.zeros_like(reached)
                for b0, b1, c0, c1 in ranges:
                    a, b = max(r0, b0), min(r1, b1)
                    if a < b:
                        inside[a - r0:b - r0, c0:c1] = True
                reached = reached & inside
            rows_, cols = np.flatnonzero(reached.any(axis=1)), np.flatnonzero(reached.any(axis=0))
            if rows_.size:
                first_row = r0 + int(rows_[0]) if first_row is None else first_row
                last_row = r0 + int(rows_[-1])
                first_col = int(cols[0]) if first_col is None else min(first_col, int(cols[0]))
                last_col = int(cols[-1]) if last_col is None else max(last_col, int(cols[-1]))
        if first_row is None:
            return None
    return (slice(max(0, first_row - NEIGHBOUR_PAD), min(grid.height, last_row + 1 + NEIGHBOUR_PAD)),
            slice(max(0, first_col - NEIGHBOUR_PAD), min(grid.width, last_col + 1 + NEIGHBOUR_PAD)))


def fill_from_neighbours(elevation_path: str, surface_path: Optional[str], grid: Grid, neighbours: List[Source],
                         cache_dir: str, out_path: str, update: Optional[str] = None,
                         exclude: Optional[np.ndarray] = None,
                         rows: Optional[int] = None) -> Tuple[Optional[str], List[Tuple[Source, int]]]:
    """Fill the gaps on land at a border from the national data of the neighbours, in turn,
    before the fallbacks (fill_gaps_chain): each only what the ones before it left, the same
    offset per gap as fill_gaps, its surface gaps from its surface model only. A neighbour
    is used where its boxes reach a border gap (neighbour_window) and while it is available
    (choose.source_unavailable; a line says why not); one whose download fails leaves its
    gaps to the next. Saves the mask of the terrain pixels filled to out_path; returns
    (out_path, or None when they filled nothing, [(neighbour, filled pixels)]).
    rows: in strips of that many rows (the border gaps memory-mapped next to out_path
    meanwhile, the masks joined strip by strip). The border gaps are found once, and again only
    after a neighbour wrote pixels into either grid or failed midway (an attempt that found no
    data of its own under the gaps leaves them as they were). The neighbours' rasters are
    reprojected as NEIGHBOUR_SAME_RESOLUTION and NEIGHBOUR_RESAMPLING say."""
    from .choose import source_unavailable

    if not neighbours:
        return None, []
    joined, counts = None, []
    gaps = None  # border_gaps, computed again only after a neighbour's fill_gaps may have changed the grids
    border_path = os.path.join(os.path.dirname(out_path), "border.npy")
    for n, neighbour in enumerate(neighbours):
        progress.compute.start(f"border gaps ({neighbour.name})", 1, unit="step")
        if gaps is None:
            if rows is None:
                gaps = border_gaps(elevation_path, surface_path, grid, exclude)
            else:
                shape = (grid.height, grid.width)
                gaps = border_gaps(elevation_path, surface_path, grid, exclude, rows=rows,
                                   out=new_mask(border_path, shape))
        window = neighbour_window(neighbour, grid, gaps, rows=rows)
        progress.compute.update(1)
        progress.compute.finish()
        if window is None:
            continue
        why = source_unavailable(neighbour)
        if why:
            print(f"Gaps at the border not filled from {neighbour.name}: {why}")
            continue
        step = f"{os.path.splitext(out_path)[0]}{n}.npy"
        try:
            _, pixels, written = fill_gaps(elevation_path, surface_path, grid, neighbour, cache_dir, step, update,
                                           exclude=exclude, name=f"border{n}", window=window,
                                           surface_from_terrain=False, rows=rows, resampling=NEIGHBOUR_RESAMPLING,
                                           same_resolution=NEIGHBOUR_SAME_RESOLUTION)
        except (RuntimeError, requests.RequestException) as e:
            gaps = None  # some of its pixels may have been filled before the failure
            print(f"Gaps at the border not filled from {neighbour.name}: {cache.clean_error(e)}")
            continue
        if written:
            gaps = None  # its terrain or surface pixels were filled: the border gaps again for the next one
        counts.append((neighbour, pixels))
        if pixels:
            if rows is not None:
                if joined is None:
                    joined = out_path
                    shutil.copyfile(step, out_path)
                else:
                    _or_rows(out_path, step, rows)
            else:
                joined = np.load(step) if joined is None else joined | np.load(step)
    if rows is not None:
        del gaps
        remove_grid(border_path)
    if joined is None:
        return None, counts
    if rows is None:
        np.save(out_path, joined)
    return out_path, counts
