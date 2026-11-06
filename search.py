"""
A search as a library: from SearchParams to a saved run, without terminal input.

    plan = plan_search(params, paths, on_event)   # source, grid, resolution
    estimate = estimate_search(plan)               # what would be downloaded, disk use
    data = prepare_data(plan)                      # step 1: download, mosaics, water, gaps
    lines = find_lines(plan, data)                 # steps 2-4: anchors, lines, profiles, groups
    result = save_run(plan, lines)                 # step 5: the run and the map
    download_orthophoto(plan, orthophoto_lines(plan, lines), confirm)  # for offline use of the map
    # or all of it: run_search(params, paths, on_event, confirm)

Large areas (--area) are computed in square tiles (search_lines): each tile is a grid
with an overlap of --max-length around its core, and a line belongs to the tile whose
core holds its first anchor (the one with the smaller x, then y), so no line is found
twice. Each finished tile is saved in the run folder (tiles/<k>.table.pkl.gz); the same
command after an interruption finds the unfinished run and skips those tiles.

Messages go to on_event(kind, text) with kind "info" or "warning"; progress goes
through progress.py (progress.subscribe). Questions (an expensive run, orthophoto
downloads) go to confirm(kind, text) -> bool; without it the answer is yes.
A search that cannot go on raises SearchError with the message for the user.

Optional limits (settings.Limits, the web worker's; None, as on the command line, checks
nothing) refuse a search before its costly work: plan_search checks the request values,
the size of the `within` box and of a Nominatim area before OpenStreetMap is asked for
their themes, the area (a circle's too) and its bounding box before any other service is
asked, the bounding box of the grid, the pixels of the grid or of a tile, and the tiles;
check_estimate the download; _lines the anchors and lines found.
"""

import contextlib
import dataclasses
import gc
import glob
import gzip
import hashlib
import json
import math
import os
import pickle
import shutil
import threading
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import psutil
import requests

import area as ar
import cache
import coast
import grid as gd
import helpers as sh
import hypsometry as hy
import mapping as mp
import messages
import obstacles
import orthophoto as ortho
import osm
import runs as rn
import saving
import sag as sg
import sources as src
from settings import Limits
from params import SearchParams
from progress import progress

# Ask before continuing when a run looks this expensive
CONFIRM_DOWNLOAD_MB = 500
CONFIRM_DISK_GB = 4
CONFIRM_MINUTES = 30
ORTHO_SECONDS_PER_TILE = 0.3  # measured download rate with orthophoto.DOWNLOAD_THREADS
ORTHO_DETAIL = 50  # groups of an area with detailed orthophoto, unless the service or --ortho-detail says
# The memory of a search (memory_needed): its grids, this many bytes per pixel (terrain,
# surface, water, gaps, masks, temporaries), its lines, this many bytes per line (a line being
# checked in step 3, one of step 4 with its coordinates, values and group, one of a tile done
# already, or one being saved in step 5), and the profiles a circle keeps for every line, this
# many bytes per point.
# Measured 2026-11-03 (tools/perf_profile.py --cores 7, the RSS of a stage less the start's over
# the grid's pixels; docs/performance.md, round 3, wave 2): step 1 peaks at the medians of the
# surface pair's gap filling, 32 B per pixel on Windows (the Gozo coast's 50 Mpx tile, the
# memory-mapped grids read so far included) and 38 where a neighbour's data fills a border over
# half the grid first (a Tatras circle of 43.6 Mpx at 1 m); step 2 (the slopes, the prominence's
# union-find and the drop over the anchors' windows) at 25 with dense anchors (swiss-long, 2.5 %
# of the pixels; the Tatras' 2.65 million, 6.1 %), step 3 at 16; was 100 before the temporaries
# of step 1 were cut
PIXEL_BYTES = 50
# Measured 2026-10-31 (tools/perf_lines_memory.py, the 403 026 lines of the Gozo coast): as
# columns (helpers.LineTable) 421 B per line at the peak of step 4, 236 B held between tiles,
# 382 B at the peak of step 5; with a dict per line they were 2.2 KB, 1.6 KB and 3.1 KB (the
# worker killed on the VPS held 2.6 million lines of earlier tiles and 1.1 million of a tile).
# Again 2026-11-01 after wave 4 (perf_lines_memory.py --call of the captures of swiss-long, 1.7
# million lines, of the Gozo coast's large tile, 253 000, and of R9, 86 000): step 3 (the found
# pairs held once, the tables joined and sorted column by column) 190-199 B per line, was 494-504;
# step 4 at most 389-439 B (mapping.group_lines; its coordinates 234-305 B, was 306-553 with the
# core's second table), 261-294 B held; step 5 327-459 B (and about 40 MiB whatever the number
# of lines). After wave 5 (the same captures): the grouping 266-268 B (its cell index as arrays,
# its loop in numba: grouping.py), was 380-439; 229-262 B held (the pixel columns dropped after
# the profiles); step 5 246-315 B (the rows' order part by part, 1 000 lines a chunk: about 5 MiB
# whatever the number of lines); the join of a tiled search's lines 319 B (the Gozo coast's 6
# tiles column by column, was 560: concat held them twice). The largest is step 4's profiles,
# 306-389 B: R9's 389 B, plus 16 % (its 22 lines per group make the representatives' profiles
# weigh more per line than on the larger searches' 158-167; they are counted within this, so a
# search of smaller groups holds more). The found pairs need no term of their own: as many
# as the valid lines on all 15 captures (at most 1.0001 times; lines left out by --min-height or
# --max-wall-angle would add about 190 B per pair to step 3, still below step 4 up to 2.3 pairs
# per line)
LINE_BYTES = 450
# A profile takes up to PROFILE_POINTS points (its max_points, the anchors and the smallest
# clearances): as lists of Python floats (helpers.line_profile) 64-100 B per point; as arrays
# (lineprofiles.line_profiles, wave 3) 51-77 B per point at the peak of computing them, 21-30 B
# held. Kept at 100 B (30 % over the peak): CIRCLE_PROFILES_BYTES / PROFILE_POINT_BYTES (5
# million points) decides which circles keep every profile, so the two change only together
PROFILE_POINT_BYTES = 100
PROFILE_POINTS = 203
# A circle keeps the profile of every line (the map opened from disk shows each) while they take
# at most this; above, only the representatives' as an area does (a map served by the app computes
# the others when they are opened): about 26 000 lines of 1 m at most, R9's 85 671 at 5 m
CIRCLE_PROFILES_BYTES = 500e6
# Tiles of large areas: the grids of one tile may use this share of the free memory (the rest
# is for the lines of the tiles, which _check_lines refuses over the budget)
TILE_MEMORY_SHARE = 0.5
# A tile (its core with the overlap) has at most this many pixels whatever the memory: a PC
# with much memory would otherwise take one tile of hundreds of Mpx, whose grids alone hold
# gigabytes, to save little work (the overlap's share of a tile falls slowly once the core is a
# few overlaps wide: a 7 000 m core with 1 302 m of overlap, 92 Mpx at 1 m, computes 1.9 pixels
# per pixel of the core; 14 000 m, 280 Mpx, 1.4). A tile of 100 Mpx holds about 3.2 GB of grids
# at the 32 B per pixel measured (the user's choice of 2026-11-03 over 64 Mpx)
TILE_PX_MAX = 100e6
DOWNLOAD_MB_PER_S = 5  # for the time estimate of area searches
MAX_MEASURED_PX = 6000  # the longest line measured on the map, in pixels (profile_of_line builds a square grid around it)
# The terrain of the 3D view around a line (patch_of_line, docs/3d-view-contract.md): PATCH_BLOCK·n + 1
# samples on a side (the page meshes it in chunks of Martini(513)), at least PATCH_SIDE_MIN metres and
# the line's length + PATCH_SIDE_MARGIN; at most MAX_MEASURED_PX (the quick lane's largest grid)
PATCH_BLOCK = 512
PATCH_SIDE_MIN = 1536
PATCH_SIDE_MARGIN = 500
PATCH_NO_DATA = -32768  # the int16 value of a sample without data
# The uncertain shore (sources.filling.shore_segments) of a search this long or longer gets a warning
SHORE_WARN_M = 100
SHORE_FILE = "shore.json"  # a tiled search's shore in its run folder (search_lines: resuming keeps it)
PATCH_ROWS = 512  # rows encoded at a time (float64 temporaries of a block only)
# The reach of a fixed anchor (reach_of_anchor, docs/3d-view-contract.md, "/api/reach"): every sample of the
# patch is a target while at most REACH_FULL_TARGETS lie within the run's limits, else every second one;
# the numba kernel on REACH_THREADS threads, REACH_PART targets at a time; clearances in steps of
# REACH_QUANTUM metres in the low 7 bits of a byte, the high bit set for a line over trees or buildings
REACH_FULL_TARGETS = 300_000
REACH_THREADS = 2
REACH_PART = 1 << 18
REACH_QUANTUM = 0.5
REACH_STEPS_MAX = 127
REACH_TREES = 0x80
REACH_ROWS = 256  # lattice rows whose limits are tested at a time
# The trees and buildings of the 3D view (canopy_of_line): the obstacle surface less the terrain, in steps of
# CANOPY_QUANTUM metres (a byte), nothing below CANOPY_MIN_HEIGHT
CANOPY_QUANTUM = 0.5
CANOPY_MIN_HEIGHT = 1.0
# The memory a download phase's process takes at its peak (slot_memory keeps it free for each
# download slot): measured 2026-10-31 at 120 MiB after the imports, 240-400 MiB when it downloads
# (Montserrat at 1 m, 2 WCS tiles of 32 MB per layer; El Capitan, 3DEP blocks), and GDAL's cache of
# ranges that the layers reading range by range fill (sources.net.RANGE_CACHE_BYTES)
DOWNLOAD_PROCESS_BYTES = 512 * 2 ** 20 + 256 * 2 ** 20
CGROUP_ROOT = "/sys/fs/cgroup"  # cgroup v2 of this process inside a container (its own namespace)

OnEvent = Callable[[str, str], None]
Confirm = Callable[[str, str], bool]


class SearchError(messages.Coded, Exception):
    """The search cannot go on; the message is meant for the user: str() the command line's (option
    names), with a code the web page's text from the catalogue (messages.Coded: "error.<code>")."""

    def __init__(self, text: str, code: Optional[str] = None, **params):
        super().__init__(text)
        self.code, self.params = code, params

    @classmethod
    def of(cls, error: BaseException, text: Optional[str] = None, code: Optional[str] = None,
           **params) -> "SearchError":
        """A SearchError from another error: its code and parameters if it has them (a UserError of
        params.py, area.py, settings.py), else `code` and `params`; the text `text` or the error's."""
        inner = messages.user_error(error)
        if inner is not None and inner.code:
            code, params = inner.code, inner.params
        return cls(text if text is not None else cache.clean_error(error), code, **params)


@dataclass
class Paths:
    """The data folder (see cache.py) and the work folder of this search."""
    data: str
    work: str

    @property
    def cache(self) -> str:
        return os.path.join(self.data, "cache")

    @property
    def runs(self) -> str:
        return os.path.join(self.data, "runs")


@dataclass
class Plan:
    params: SearchParams
    paths: Paths
    area: ar.Area
    source: src.Source
    grid: gd.Grid
    resolution: float
    group_distance: float
    nmpt: Optional[str]
    rigging: sg.Rigging
    layers: List[src.Layer]
    emit: OnEvent
    crs: str
    center_xy: tuple
    limits: Optional["Limits"] = None  # what the web worker allows; None: no limits
    # Large areas: (core bounds, tile grid) per tile, with cores of tile_core metres; None: one grid
    tiles: Optional[List[Tuple[tuple, gd.Grid]]] = None
    tile_core: Optional[float] = None
    tile_label: str = ""  # "Tile 3/15 · " while a tile of a large area is computed
    # A tile's plan: the grid of the whole search (the world water polygons are read once for it)
    search_grid: Optional[gd.Grid] = None
    owner: Optional[int] = None  # the user of the web app's job (None: the local app, the command line)
    # The memory the search may use (_check_lines): its compute slot's budget, or the memory free
    # when a search with limits was planned; None: not checked
    memory: Optional[int] = None
    # Stop checking the pairs found at the limit of lines or of the memory (_early_check):
    # Limits.lines_early_stop of the server, also for a user without limits (the web worker sets it)
    early_stop: bool = True
    # Rewrite the runs folder's list (runs.write_index: runs.js and index.html) after saving the run:
    # not on the public site (the web worker clears it), where nothing reads them (web.py makes each
    # user's runs.js, index.html redirects to the app) and they grow with every run of the site
    index_runs: bool = True
    # The counts of the line search (jobs.FUNNEL_STEPS) added by _lines and find_valid_lines; the
    # tiles get the same dict (dataclasses.replace), so it sums over them. A tile of a resumed search
    # that was saved already adds nothing
    funnel: Dict[str, int] = field(default_factory=dict)
    # How obstacles are told from the terrain's own rock (obstacles.RULE, recorded in run.json);
    # None: the surface model as it is (no surface model, a source without the rule, runs before it)
    obstacles: Optional[Dict] = None
    # Whether the grid may hold a border of the source's data (Source.neighbours fill the gaps
    # there): the country layer sets False for a tile whose grid lies inside the country's outline,
    # whose area mask is then full without burning the outline and whose coverage is not counted
    # (prepare_data in strips)
    border: bool = True

    @property
    def end_zone(self) -> float:
        """The no-fall zone at the ends, metres (--end-zone; 0: off): helpers.end_zone_rule."""
        return float(self.params.end_zone)

    @property
    def lift(self) -> float:
        """The A-frames' height at both anchors, metres (--anchor-lift; 0: none)."""
        return float(self.params.anchor_lift)


STEPS = 5


def _step(plan: Plan, n: int, title: str):
    """Start a step of the search: a message, and the step the progress bars belong to."""
    plan.emit("info", f"\nStep {n}: {title[0].upper() + title[1:]}...")
    progress.set_step(f"{plan.tile_label}Step {n}/{STEPS}: {title}")


@dataclass
class Estimate:
    download_mb: float
    work_gb: float
    reasons: List[str] = field(default_factory=list)  # why the run looks expensive


@dataclass
class Data:
    """Step 1 results: memory-mapped grids in the work folder."""
    elevation: np.ndarray
    surface: Optional[np.ndarray]
    water: Optional[np.ndarray]
    filled: Optional[np.ndarray]
    slope: Optional[np.ndarray]
    # Pixels filled from the national data of a neighbour (Source.neighbours): not "filled gaps"
    # of less precise data (filled), but a seam of two surveys where they meet
    joined: Optional[np.ndarray] = None
    # The search area on the grid (plan.area.mask(grid), computed once in step 1); None: computed
    # where needed
    mask: Optional[np.ndarray] = None
    # The heights of the land with data of the search area (of a tile's core), hypsometry.py
    terrain: Optional[hy.Histogram] = None
    # The area of a tiled search (prepare_data(strips=True) with plan.tiles): the histogram of
    # each tile's core, in the order of plan.tiles (terrain is their sum)
    tile_terrain: Optional[List[hy.Histogram]] = None
    # The filled gaps and the shore faces taken from the surface model (sources.filling.fill_shore_from_surface):
    # what a line's filled_m counts. The faces are no seam (filled): the anchors at a cliff's top edge stand
    # right next to its face, and the surface model is the terrain's own survey there
    covered: Optional[np.ndarray] = None

    def filled_pixels(self) -> Optional[np.ndarray]:
        """The pixels of filled data a line's filled_m counts: the gaps and the shore faces."""
        return self.covered if self.covered is not None else self.filled
    # The uncertain shore (sources.filling.shore_segments): the segments for the run's files
    # (prepare_data(shore="segments")), or the kinds on the grid for the 3D view's patch
    # (shore="kinds", uint8 memory-mapped); None without water filling or when not asked
    shore: Optional[Dict] = None
    shore_kinds: Optional[np.ndarray] = None


@dataclass
class Lines:
    """Steps 2-4 results: every valid line (with the profiles it keeps) and the groups ("spots")."""
    results: sh.LineTable
    spot_groups: mp.Groups
    # The terrain of the whole search area (hypsometry.statistics), None when not known
    terrain: Optional[Dict] = None
    # The uncertain shore of the whole search area (sources.filling.shore_segments), None when not known
    shore: Optional[Dict] = None


@dataclass
class Result:
    results: sh.LineTable
    spot_groups: mp.Groups
    meta: Dict
    run: Dict
    map_path: Optional[str]


def _print(kind: str, text: str):
    print(text)


def plan_search(params: SearchParams, paths: Paths, on_event: Optional[OnEvent] = None,
                with_margin: bool = True, limits: Optional[Limits] = None, memory: Optional[int] = None,
                tiled: bool = True) -> Plan:
    """Choose the source and the grid, and describe the search. The grid covers the area
    and _margin around it, unless with_margin is False (a profile needs no anchor values).
    With limits, a search over them is refused (SearchError) before anything costly.
    `memory`: the bytes this search may use (a compute slot of the web worker: slot_memory),
    for its tiles and Plan.memory, with or without limits; None: the memory free now (with
    limits; without them Plan.memory stays None). tiled=False: an area gets no tiles (its grid
    has its area_shape; the country layer cuts it into fixed_tiles itself)."""
    emit = on_event or _print
    src.used_data.clear()  # several searches may run in one process
    cache.check_layout(paths.cache)
    _check_params(limits, params)
    region_km2 = limits.region_km2_max if limits else None
    if params.area is not None or params.geometry is not None:
        try:
            if params.geometry is not None:  # drawn or uploaded in the web app
                area = ar.from_geometry(params.geometry, params.buffer, params.within, paths.cache, region_km2)
            else:
                area = ar.from_spec(params.area, params.buffer, params.within, paths.cache, params.max_length,
                                    region_km2)
        except (ValueError, requests.RequestException) as e:
            raise SearchError.of(e, f"Area: {cache.clean_error(e)}", "area_failed", reason=cache.clean_error(e))
        if limits and limits.area_km2_max and ar.size_km2(area.geometry) > limits.area_km2_max:
            km2 = ar.size_km2(area.geometry)
            raise SearchError(f"The area covers {km2:.1f} km², at most "
                              f"{limits.area_km2_max:g} km² on this site: draw a smaller one, or a smaller --buffer",
                              "area_too_large", km2=round(km2, 1), max=limits.area_km2_max)
        center_lat, center_lon = area.center
    else:
        if params.lat is not None:
            center_lat, center_lon = params.lat, params.lon
        else:
            center_lat, center_lon = mp.pl1992_to_wgs84(params.easting, params.northing)
        area = ar.Circle(center_lat, center_lon, params.radius)
        km2 = math.pi * params.radius ** 2 / 1e6
        if limits and limits.area_km2_max and km2 > limits.area_km2_max:
            raise SearchError(f"The circle covers {km2:.1f} km², at most {limits.area_km2_max:g} km² on this site: "
                              f"a smaller --radius", "circle_too_large", km2=round(km2, 1), max=limits.area_km2_max)
    _check_box(limits, *_area_box(area))  # before the source is chosen (its country) and any data

    try:
        source, reason = src.choose_source(params.source, center_lat, center_lon, paths.cache,
                                           params.elevation_file, params.surface_file)
    except ValueError as e:
        raise SearchError.of(e, code="no_source", reason=cache.clean_error(e))
    src.OpenTopographyTiles.api_key = params.opentopo_key
    nmpt = params.nmpt_mode
    if nmpt and source.nmpt is None:
        emit("info", f"Note: {source.name} has no surface model (trees/buildings), NMPT check is off")
        nmpt = None
    resolution = params.resolution or source.default_resolution
    _check_params(limits, params, resolution)  # the source's resolution when none was given
    group_distance = params.group_distance or max(20.0, 2 * resolution)
    native = source.nmt.native_res
    if isinstance(source.nmt, src.WcsTiles) and source.nmt.fetch_res is None and resolution < native:
        raise SearchError(f"--resolution cannot be finer than the {source.name} data ({native:g} m)",
                          "resolution_finer_than_data", source=source.name, native=native)

    crs = source.working_crs(center_lat, center_lon)
    x, y = ar._to(crs)(center_lon, center_lat)
    margin = _margin(params, resolution) if with_margin else 0.0
    left, bottom, right, top = area.bounds(crs)
    grid = gd.make_grid((left - margin, bottom - margin, right + margin, top + margin), resolution, crs,
                        source.grid_origin)
    if limits and limits.bbox_km_max:  # the box the data, the indexes and OpenStreetMap are asked for
        from rasterio.warp import transform_bounds
        _check_box(limits, *transform_bounds(crs, "EPSG:4326", *grid.bounds))
    tiles = core = None
    max_px = limits.grid_mpx_max * 1e6 if limits and limits.grid_mpx_max else None
    if isinstance(area, ar.Polygon):
        grid.area_shape = ar.project(area.geometry, "EPSG:4326", crs)
        if tiled:
            core = tile_core_size(params, resolution, max_px, memory)
            if limits:
                _check_tiles(grid, params, resolution, core, limits)
            tiles = _tiles(grid, params, resolution, source.grid_origin, core)
    elif max_px and grid.width * grid.height > max_px:
        raise SearchError(f"The grid would have {grid.width * grid.height / 1e6:.0f} million pixels, at most "
                          f"{limits.grid_mpx_max:g} million on this site: a smaller --radius or a coarser "
                          f"--resolution", "circle_grid_too_large", mpx=round(grid.width * grid.height / 1e6),
                          max=limits.grid_mpx_max)
    rigging = sg.Rigging(params.pretension, params.stretch, params.webbing_weight,
                         params.athlete_mass, params.fall_zone)
    layers = [source.nmt] + ([source.nmpt] if nmpt else [])

    lines = ["=" * 60, "Find-a-Line - Highline Location Finder", "=" * 60,
             f"Centre: {center_lat:.6f}, {center_lon:.6f} (WGS84) / E {x:.0f}, N {y:.0f} ({crs})",
             f"Data: {source.name} ({reason}) - {source.description}"]
    if source.note:
        lines.append(f"Note: {src.dated(source.note, datetime.now().year)}")  # the year of a run made now
    if isinstance(area, ar.Circle):
        lines.append(f"Radius: {params.radius:.0f}m, resolution: {resolution:g}m ({grid.width} x {grid.height} px)")
    else:
        lines.append(f"Area: {_area_text(params)}, {ar.size_km2(area.geometry):.2f} km², resolution: "
                     f"{resolution:g}m ({grid.width} x {grid.height} px, "
                     + (f"{len(tiles)} tiles)" if tiles else "one grid)"))
    if resolution < native * 0.99:
        lines.append(f"Note: the resolution is finer than the data ({native:g} m), which is interpolated")
    lines += [f"Length constraints: {params.min_length:g}m - {params.max_length:g}m",
              f"Anchor height difference: at most {params.max_anchor_diff:g}% of the length "
              f"and {params.max_anchor_diff_m:g}m",
              f"Slope threshold: {params.slope_threshold:g} degrees"]
    lo, hi = params.min_elevation, params.max_elevation
    if lo is not None and hi is not None:
        lines.append(f"Anchor elevation: {lo:g}–{hi:g} m a.s.l.")
    elif lo is not None:
        lines.append(f"Anchor elevation: at least {lo:g} m a.s.l.")
    elif hi is not None:
        lines.append(f"Anchor elevation: at most {hi:g} m a.s.l.")
    lines.append(f"NMPT (trees/buildings): {nmpt or 'not used'}")
    if params.model == "sag":
        lines.append(f"Clearance model: sag estimator ({params.pretension:g} kN, {params.stretch:g}% @ 10 kN, "
                     f"{params.webbing_weight:g} g/m, athlete {params.athlete_mass:g} kg, "
                     f"fall zone {params.fall_zone:g} m)")
    else:
        lines.append("Clearance model: maximum elevation formula")
    if params.end_zone or params.anchor_lift:  # unset: the lines of before
        lines.append(f"Ends: no-fall zone {params.end_zone:g} m, A-frames {params.anchor_lift:g} m")
    lines.append("=" * 60)
    for line in lines:
        emit("info", line)
    for note in getattr(area, "notes", []):
        emit("warning", note)
    return Plan(params, paths, area, source, grid, resolution, group_distance, nmpt, rigging, layers,
                emit, crs, (x, y), limits, tiles, core,
                memory=memory if memory is not None else available_memory() if limits else None,
                early_stop=limits.lines_early_stop if limits else True,
                obstacles=dict(obstacles.RULE) if nmpt and source.obstacles and obstacles.RULE else None)


def _check_params(limits: Optional[Limits], params: SearchParams, resolution: Optional[float] = None):
    """The bounds of the request values again (the web checks them first): the worker refuses a
    request that skipped them (Limits.check_params, on the validated values)."""
    if limits:
        try:
            limits.check_params(params, resolution, allowed=False, min_resolution=src.MIN_RESOLUTION)
        except ValueError as e:
            raise SearchError.of(e, str(e))


def _area_box(area: ar.Area) -> Tuple[float, float, float, float]:
    """(west, south, east, north) of an area in degrees (a circle's from its radius)."""
    if isinstance(area, ar.Circle):
        lat, lon = area.center
        dlat = area.radius / 111320
        dlon = dlat / max(math.cos(math.radians(min(abs(lat) + dlat, 89.9))), 0.01)
        return lon - dlon, lat - dlat, lon + dlon, lat + dlat
    return area.geometry.bounds


def _check_box(limits: Optional[Limits], west: float, south: float, east: float, north: float):
    """Refuse a search whose bounding box (WGS84) has a side over Limits.bbox_km_max: two small
    areas far apart, a huge circle. Data, sheet indexes and Overpass are asked over the box."""
    if not limits or not limits.bbox_km_max:
        return
    lat = 0.0 if south <= 0 <= north else min(abs(south), abs(north))  # where the box is widest
    width = (east - west) * 111.32 * math.cos(math.radians(lat))
    height = (north - south) * 110.57
    if max(width, height) > limits.bbox_km_max:
        raise SearchError(f"The search spans {width:.0f} × {height:.0f} km (its bounding box), at most "
                          f"{limits.bbox_km_max:g} km on a side on this site: a smaller area, or areas far apart "
                          f"as separate searches", "box_too_large", width=round(width), height=round(height),
                          max=limits.bbox_km_max)


def _check_tiles(grid: gd.Grid, params: SearchParams, res: float, core: float, limits: Limits):
    """Refuse an area whose tiles (with their overlap) would be over the pixel limit, or that would
    take more tiles than allowed; the tiles over the bounding box are counted, before _tiles. An
    area within one core is one grid (_tiles): its own pixels count."""
    margin = _margin(params, res)
    width, height = grid.width * res - 2 * margin, grid.height * res - 2 * margin
    count = 1 if max(width, height) <= core else math.ceil(width / core) * math.ceil(height / core)
    side = (core + 2 * _overlap(params, res)) / res
    pixels = grid.width * grid.height if count == 1 else side * side
    if limits.grid_mpx_max and pixels > limits.grid_mpx_max * 1e6:
        raise SearchError(f"A {'grid' if count == 1 else 'tile'} would have {pixels / 1e6:.0f} million pixels with "
                          f"its overlap, at most {limits.grid_mpx_max:g} million on this site: a shorter "
                          f"--max-length, a smaller --prominence-span or a coarser --resolution", "grid_too_large",
                          mpx=round(pixels / 1e6), max=limits.grid_mpx_max)
    if limits.tiles_max and count > limits.tiles_max:
        raise SearchError(f"The area spans {count} tiles of {core:g} m, at most {limits.tiles_max} on this site: "
                          f"a smaller area or a coarser --resolution", "too_many_tiles", n=count, max=limits.tiles_max)


def check_estimate(plan: Plan, estimate: Estimate):
    """Refuse a search whose download is over the limit of plan.limits."""
    limits = plan.limits
    if limits and limits.download_mb_max and estimate.download_mb > limits.download_mb_max:
        raise SearchError(f"About {estimate.download_mb:.0f} MB to download, at most {limits.download_mb_max:g} MB "
                          f"on this site: a smaller area or a coarser --resolution (or --nmpt off)",
                          "download_too_large", mb=round(estimate.download_mb), max=limits.download_mb_max)


def _area_text(params: SearchParams) -> str:
    """E.g. "coast ±100 m within osm:Gozo", "osm:Gozo", "area.geojson", "drawn area"."""
    a = params.area
    if params.geometry is not None:
        text = ar.DRAWN
    elif a in ("coast", "cliffs"):
        text = f"{a} ±{params.buffer:g} m"
    else:
        text = a if a.startswith("osm:") else os.path.basename(a)
    return text + (f" within {params.within}" if params.within else "")


def _margin(params: SearchParams, res: float) -> float:
    """Terrain around the anchors that their prominence and drop look at (terrain.py):
    the grid covers this much around the area, so the values do not depend on its edge."""
    return math.ceil(max(params.prominence_span, params.drop_radius) / res) * res


def _overlap(params: SearchParams, res: float) -> float:
    """Margin around a tile core: the longest line, the terrain around its far anchor
    (_margin), plus pixels for the slope at the edge."""
    return math.ceil(params.max_length / res) * res + _margin(params, res) + 2 * res


@dataclass
class CgroupLimits:
    """What a container (cgroup v2) lets this process use; None: no limit."""
    memory: Optional[int] = None  # bytes still free below memory.max
    cpus: Optional[int] = None  # CPUs the quota of cpu.max and the affinity allow


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="ascii") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return None


def cgroup_limits(root: Optional[str] = None) -> CgroupLimits:
    """Memory and CPU limits of a container (Docker's mem_limit and cpus), from the
    cgroup v2 files under root. Missing files (Windows, macOS, cgroup v1, no
    container) or "max" mean no limit; nothing changes outside a container then."""
    root = root or CGROUP_ROOT
    limits = CgroupLimits()
    limit, used = _read(os.path.join(root, "memory.max")), _read(os.path.join(root, "memory.current"))
    if limit and limit != "max" and used:
        try:
            used_bytes = int(used)
            # The page cache that may be dropped counts as free, as in docker stats
            for line in (_read(os.path.join(root, "memory.stat")) or "").splitlines():
                key, _, value = line.partition(" ")
                if key == "inactive_file":
                    used_bytes -= int(value)
            limits.memory = max(0, int(limit) - max(0, used_bytes))
        except ValueError:
            pass
    quota = (_read(os.path.join(root, "cpu.max")) or "max").split()
    if quota[0] != "max":
        try:
            period = int(quota[1]) if len(quota) > 1 else 100000
            limits.cpus = max(1, math.ceil(int(quota[0]) / period))
        except ValueError:
            pass
    if hasattr(os, "sched_getaffinity") and limits.cpus is not None:
        limits.cpus = min(limits.cpus, len(os.sched_getaffinity(0)))
    return limits


def memory_needed(pixels: float, lines: float, profile_points: float = 0) -> float:
    """Bytes a search needs for grids of this many pixels, this many lines and profiles of this
    many points in all (the peak of step 4 of a tile: its grids, its lines and those of the
    tiles done already; a circle's profiles of every line)."""
    return pixels * PIXEL_BYTES + lines * LINE_BYTES + profile_points * PROFILE_POINT_BYTES


def profile_points(lines: sh.LineTable) -> int:
    """The points of the profiles of these lines (helpers.line_profile: every pixel between the
    anchors and both anchors, at most PROFILE_POINTS)."""
    steps = np.abs(lines.columns["a2"] - lines.columns["a1"]).max(axis=1) if len(lines) else np.zeros(0)
    return int(np.minimum(steps + 1, PROFILE_POINTS).sum())


def memory_warning(limits: Optional[Limits], budget: Optional[int] = None) -> Optional[str]:
    """A warning when the largest search the limits allow (a tile of grid_mpx_max pixels and
    lines_max lines) needs more memory than is free now (the container's limit in the worker),
    or than `budget` (one compute slot's: slot_memory)."""
    if not limits or not limits.lines_max:
        return None
    free = available_memory() if budget is None else budget
    pixels = (limits.grid_mpx_max or 0) * 1e6
    need = memory_needed(pixels, limits.lines_max)
    if need <= free:
        return None
    fits = max(0, int((free - memory_needed(pixels, 0)) // LINE_BYTES))
    room = "free" if budget is None else f"for each of {limits.compute_slots} compute slots"
    return (f"WARNING: the largest search the limits allow ({limits.lines_max} lines, grids of "
            f"{pixels / 1e6:g} million pixels) needs about {need / 2 ** 30:.1f} GiB, {free / 2 ** 30:.1f} GiB "
            f"{room}: such searches are refused for memory; FINDALINE_LIMIT_LINES_MAX={fits} would fit"
            + ("" if budget is None else " (or fewer FINDALINE_LIMIT_COMPUTE_SLOTS)"))


def available_memory() -> int:
    """Free memory in bytes: the machine's, or less when a container limits it."""
    free = psutil.virtual_memory().available
    limit = cgroup_limits().memory
    return free if limit is None else min(free, limit)


def slot_memory(limits: Limits, total: Optional[int] = None) -> Optional[int]:
    """The memory budget of one compute slot of the web worker (limits.compute_slots of them), in
    bytes: `total` (the memory free at the worker's start, the container's limit) less what the
    quick lane may take (a profile measured on the map: a grid of MAX_MEASURED_PX squared pixels)
    and the download slots' processes (DOWNLOAD_PROCESS_BYTES each), shared by the compute slots.
    None with one compute slot: its search takes the memory free when it starts, as before."""
    if limits.compute_slots <= 1:
        return None
    total = available_memory() if total is None else total
    reserve = memory_needed(MAX_MEASURED_PX ** 2, 0) + limits.download_slots * DOWNLOAD_PROCESS_BYTES
    return max(0, int((total - reserve) // limits.compute_slots))


def line_threads(params: SearchParams) -> Optional[int]:
    """Threads of the line search: --threads, or at most the CPUs of a container's
    quota (numba itself takes the affinity, and NUMBA_NUM_THREADS when it is set, as
    compose.yaml sets it to the quota: then all of them); None leaves the default of
    find_valid_lines (CPU count - 1)."""
    if params.threads:
        return params.threads
    cpus = cgroup_limits().cpus
    if cpus is None:
        return None
    import numba
    spare = 0 if "NUMBA_NUM_THREADS" in os.environ else 1
    return max(1, min(cpus, numba.config.NUMBA_NUM_THREADS - spare))


def tile_core_size(params: SearchParams, res: float, max_px: Optional[float] = None,
                   memory: Optional[int] = None) -> float:
    """Side of a tile core in metres: --tile-size, or what the free memory (or `memory`, a compute
    slot's budget) allows and max_px, the pixels a tile may have with its overlap (a site's
    limit; TILE_PX_MAX at most either way); in steps of 500 m, so the tiles stay the same when
    the free memory changes a little."""
    if params.tile_size:
        core = params.tile_size
    else:
        free = available_memory() if memory is None else memory
        side_px = math.sqrt(free * TILE_MEMORY_SHARE / memory_needed(1, 0))
        side_px = min(side_px, math.sqrt(min(max_px or TILE_PX_MAX, TILE_PX_MAX)))
        core = max(500.0, math.floor((side_px * res - 2 * _overlap(params, res)) / 500) * 500)
    return max(res, math.floor(max(core, 10 * res) / res) * res)


def _tiles(grid: gd.Grid, params: SearchParams, res: float, origin, core: float) -> Optional[list]:
    """(core bounds, grid with overlap) of each tile under the area; None if one grid will do."""
    from shapely.geometry import box
    # Cores over the area (the grid without its _margin); the margin is for the overlaps
    margin = _margin(params, res)
    g_left, g_bottom, g_right, g_top = grid.bounds
    left, bottom, right, top = g_left + margin, g_bottom + margin, g_right - margin, g_top - margin
    if max(right - left, top - bottom) <= core:
        return None
    overlap = _overlap(params, res)
    tiles = []
    for j in range(math.ceil((top - bottom) / core)):
        for i in range(math.ceil((right - left) / core)):
            c = (left + i * core, max(bottom, top - (j + 1) * core), min(right, left + (i + 1) * core), top - j * core)
            if not grid.area_shape.intersects(box(*c)):
                continue
            tiles.append((c, tile_grid(grid, c, overlap, res, origin)))
    return tiles


def tile_grid(grid: gd.Grid, core: tuple, overlap: float, res: float, origin) -> gd.Grid:
    """The grid of a tile: its core (bounds) with overlap around it, clipped to the search's grid,
    on the source's pixel edges (origin), with the area's outline."""
    g_left, g_bottom, g_right, g_top = grid.bounds
    ext = (max(g_left, core[0] - overlap), max(g_bottom, core[1] - overlap),
           min(g_right, core[2] + overlap), min(g_top, core[3] + overlap))
    tile = gd.make_grid(ext, res, grid.crs, origin)
    tile.area_shape = grid.area_shape
    return tile


@dataclass
class FixedTile:
    """A tile of the country layer: a core at whole multiples of its size in the plan's CRS."""
    name: str                                # "E<left>_N<bottom>": the core's corner in whole metres of the CRS
    core: Tuple[float, float, float, float]  # left, bottom, right, top
    grid: gd.Grid                            # the core with _overlap around it, clipped to plan.grid


def fixed_tiles(plan: Plan, core_m: float) -> List[FixedTile]:
    """The tiles of an untiled plan (plan_search(tiled=False)) on a fixed lattice: square cores of
    core_m at whole multiples of core_m in plan.crs (so a band's tiles never depend on the area's
    edge), only those intersecting the area (plan.grid.area_shape), never clipped; each grid is
    the core with _overlap around it, clipped to plan.grid (tile_grid). Rows from the north, west
    to east."""
    from shapely.geometry import box
    grid, res = plan.grid, plan.resolution
    shape = grid.area_shape if grid.area_shape is not None else box(*grid.bounds)
    left, bottom, right, top = shape.bounds
    overlap = _overlap(plan.params, res)
    tiles = []
    for j in range(math.floor(top / core_m), math.floor(bottom / core_m) - 1, -1):
        for i in range(math.floor(left / core_m), math.floor(right / core_m) + 1):
            core = (i * core_m, j * core_m, (i + 1) * core_m, (j + 1) * core_m)
            cell = box(*core)
            if not shape.intersects(cell) or shape.touches(cell):  # no area in common
                continue
            tiles.append(FixedTile(f"E{round(core[0])}_N{round(core[1])}", core,
                                   tile_grid(grid, core, overlap, res, plan.source.grid_origin)))
    return tiles


def estimate_search(plan: Plan) -> Estimate:
    """What the search would download and how much disk its working grids take."""
    p, emit = plan.params, plan.emit
    download_mb = 0.0
    # The layers' indexes asked at the same time (as download_layers does: a WFS query of
    # geoportal.gov.pl takes seconds), each layer once; the lines in the order of the layers
    estimated = src.layer.estimate_layers(plan.layers, plan.grid, plan.paths.cache, p.update)
    for layer, (n_tiles, n_missing, mb) in zip(plan.layers, estimated):
        download_mb += mb
        emit("info", f"{layer.description}: {n_tiles} tiles, {n_missing} to download (~{mb:.0f} MB)")
    if p.water == "fill" and p.coastline == "world" and coast.world_file(plan.paths.cache) is None:
        download_mb += coast.WORLD_MB
        emit("info", f"OpenStreetMap water polygons (world): one download of ~{coast.WORLD_MB} MB")
    work = plan.grid.width * plan.grid.height * work_bytes(plan)
    if plan.tiles:
        # The area's grids with step 1's temporaries, and the copies of one tile at a time (the
        # largest one's: a tile's folder is removed before the next tile's are made)
        largest = max((t for _, t in plan.tiles), key=lambda t: t.width * t.height)
        work += plan.grid.width * plan.grid.height * AREA_TEMP_BYTES + largest.width * largest.height * tile_bytes(plan)
    work_gb = work / 1e9
    estimate = Estimate(download_mb, work_gb)
    if isinstance(plan.area, ar.Polygon):  # areas are always confirmed: they can be large
        estimate.reasons.append(
            f"area of {ar.size_km2(plan.area.geometry):.2f} km² in {len(plan.tiles) if plan.tiles else 1} "
            f"tile(s); about {download_mb:.0f} MB to download (~{download_mb / DOWNLOAD_MB_PER_S / 60:.0f} min)")
    elif download_mb > CONFIRM_DOWNLOAD_MB:
        estimate.reasons.append(f"about {download_mb:.0f} MB to download ({plan.source.name})")
    if work_gb > CONFIRM_DISK_GB:
        estimate.reasons.append(f"working grids take about {work_gb:.1f} GB of disk in {plan.paths.work}")
    return estimate


def work_bytes(plan: Plan) -> int:
    """The bytes per pixel that step 1 (prepare_data) writes into the work folder at most: float32
    the terrain (nmt.npy) and surface models (nmpt.npy), the surface of the obstacles (obstacles.npy),
    a slope file (slope.npy) and each fallback's terrain and surface (gap_nmt.npy, gap_nmpt.npy,
    gap1_nmt.npy ...: made only where there are gaps, counted always); uint8 the water body mask
    (wbm.npy); bool the water (water.npy), the shore faces from the surface model with the gaps
    (covered.npy, with a surface model and the water filled) and the pixels filled by each fallback
    (filled.npy, filled1.npy ...) and by each neighbour (joined0.npy ..., joined.npy). The neighbours'
    own grids (border0_nmt.npy ...) cover the gaps at the border only and are not counted."""
    p, source = plan.params, plan.source
    surface = bool(plan.nmpt)
    floats = 1 + surface + (surface and bool(plan.obstacles)) + bool(p.slope_file)
    masks = _water_mask(plan) + (p.water == "fill") + (p.water == "fill" and surface)
    if _fills_gaps(plan):
        floats += len(source.fallbacks) * (1 + surface)
        masks += len(source.fallbacks) + (len(source.neighbours) + 1 if source.neighbours else 0)
    return 4 * floats + masks


# Bytes per pixel of the area that step 1 in strips (prepare_data(strips=True)) holds in temporary
# boolean grids of the work folder at most at one time, on top of work_bytes: the area mask, the
# shore zone, and the gaps and the matched pixels of the pair of grids being filled
AREA_TEMP_BYTES = 4


def tile_bytes(plan: Plan) -> int:
    """The bytes per pixel of a tile's copies of the area's grids (search_lines: _tile_data): float32
    the terrain, the surface (or the obstacles) and a slope file; bool the water, the filled, the
    joined and the covered masks (the gaps with the shore faces) when the search makes them."""
    p, source = plan.params, plan.source
    floats = 1 + bool(plan.nmpt) + bool(p.slope_file)
    masks = (p.water == "fill") + (_fills_gaps(plan) and (bool(source.fallback) + bool(source.neighbours)))
    masks += p.water == "fill" and bool(plan.nmpt)
    return 4 * floats + masks


def _water_mask(plan: Plan) -> bool:
    """Whether the search needs the Copernicus water body mask."""
    return plan.params.water == "fill" or _fills_gaps(plan)


def _fills_gaps(plan: Plan) -> bool:
    """Whether the search fills gaps on land (from neighbours at a border, then fallbacks)."""
    return plan.params.fill_gaps == "on" and bool(plan.source.fallback or plan.source.neighbours)


def _download_layers(plan: Plan):
    """The tiles of the search's layers (terrain, surface, the water mask) in one pool."""
    layers = list(zip(plan.layers, ("terrain", "surface")))
    if _water_mask(plan):
        layers.append((src.WATER_MASK, "water mask"))
    src.download_layers(layers, plan.grid, plan.paths.cache, plan.params.update)


def download_data(plan: Plan):
    """Download what the search area needs into the cache, without building grids.

    The web worker does this for the next job while the current one computes; the
    search itself then finds the data cached. Gap filling data is left to the search
    (whether it is needed shows only on the grid).
    """
    p, grid, cache_dir = plan.params, plan.grid, plan.paths.cache
    coastline = None
    if p.water == "fill" and p.coastline == "overpass" and coast.world_file(cache_dir) is None:
        # The coastline's theme tiles (from the extracts, or Overpass: up to minutes) in a thread
        # alongside the tiles' pool: it shares only the cache's index and servicecounts with it,
        # both safe between threads (osm's limits are file locks and SQLite); a daemon, so a
        # failed download of the tiles does not wait for it
        coastline = _Background(lambda: osm.theme("coastline", *coast._grid_bbox_wgs84(grid), cache_dir, p.update))
    # The run's name too (_run_name: two Nominatim lookups of a circle or a drawn area, 1-3 s in
    # their queue, more when it is busy): their answers land in osm's cache, where step 5 (or the
    # run folder of a tiled area) finds them; a failure is cached as well and never fails the download
    name = _Background(lambda: _run_name(plan))
    try:
        _download_layers(plan)
        if coastline is not None:
            try:
                coastline.result()
            except requests.RequestException:
                pass  # the search falls back to the Copernicus mask with a warning
    except RuntimeError as e:
        raise SearchError.of(e, f"Download failed: {e}", "download_failed", reason=cache.clean_error(e))
    try:
        name.result()
    except Exception:
        pass


class _Background:
    """A call in a daemonic thread of its own; result() waits for it and returns its value or
    raises its exception."""

    def __init__(self, call: Callable):
        self._value = self._error = None
        self._thread = threading.Thread(target=self._run, args=(call,), daemon=True)
        self._thread.start()

    def _run(self, call: Callable):
        try:
            self._value = call()
        except BaseException as e:  # handed to result()
            self._error = e

    def result(self):
        self._thread.join()
        if self._error is not None:
            raise self._error
        return self._value


def _core_window(grid, core: tuple) -> Tuple[slice, slice]:
    """The rows and columns of grid whose pixel centres lie in core (left, bottom, right, top),
    half-open like a line's first anchor in _lines: the cores of a tiled search lie on pixel
    edges, so their windows split the area's pixels between the tiles."""
    left, bottom, right, top = core
    x, _ = grid.pixel_to_xy(0, np.arange(grid.width))
    _, y = grid.pixel_to_xy(np.arange(grid.height), 0)
    span = lambda inside: (slice(int(inside[0]), int(inside[-1]) + 1) if inside.size else slice(0, 0))
    return (span(np.flatnonzero((bottom <= y) & (y < top))), span(np.flatnonzero((left <= x) & (x < right))))


def _area_mask_rows(area: ar.Area, grid: gd.Grid, path: str, rows: int, full: bool = False) -> np.ndarray:
    """area.mask(grid) into a boolean grid memory-mapped at path: a circle's pixels by the same
    test in strips of rows, a polygon burned into the mapping (sources.filling.rasterize_into).
    full: the grid lies inside the area (Plan.border False), so every pixel is set without a burn."""
    out = src.filling.new_mask(path, (grid.height, grid.width))
    if full:
        for r0, r1, _, _ in src.filling.strips(grid.height, rows):
            out[r0:r1] = True
        return out
    if isinstance(area, ar.Polygon):
        return src.filling.rasterize_into([ar.project(area.geometry, "EPSG:4326", grid.crs)], grid, out)
    x, y = area._xy(grid.crs)
    center_row = (grid.top - y) / grid.res - 0.5
    center_col = (x - grid.left) / grid.res - 0.5
    for r0, r1, _, _ in src.filling.strips(grid.height, rows):
        r, c = np.ogrid[r0:r1, :grid.width]
        out[r0:r1] = (r - center_row) ** 2 + (c - center_col) ** 2 <= (area.radius / grid.res) ** 2
    return out


def _share_rows(numerator: Callable[[int, int], np.ndarray], denominator: Callable[[int, int], np.ndarray],
                height: int, rows: int) -> float:
    """numerator's pixels among denominator's, both masks given by rows [r0, r1), summed in strips
    (the mean of a boolean selection as one grid takes it: the counts' quotient); 0.0 of nothing."""
    above = below = 0
    for r0, r1, _, _ in src.filling.strips(height, rows):
        above += int(numerator(r0, r1).sum())
        below += int(denominator(r0, r1).sum())
    return above / below if below else 0.0


def prepare_data(plan: Plan, core: Optional[tuple] = None, statistics: bool = True, strips: bool = False,
                 shore: str = "segments") -> Data:
    """Step 1: download what is missing and build the grids (terrain, surface, water, gaps).

    statistics: count the heights of the land with data in the search area (Data.terrain,
    hypsometry.py), within core (a tile's bounds) when given.
    strips: the grids made in strips of rows of about filling.STRIP_PX pixels (the area of a
    tiled search, search_lines: its masks memory-mapped in the work folder, one int32 array of
    labels of the whole grid at a time), the same values as the whole grid at once; with
    plan.tiles the heights are counted per tile core (Data.tile_terrain).
    shore: the uncertain shore after the water filling (sources.filling.shore_rows): "segments" into
    Data.shore (the run's files), "kinds" into Data.shore_kinds (the 3D view's patch), "none" (a profile,
    the country layer's tiles).
    """
    p, grid, source, emit = plan.params, plan.grid, plan.source, plan.emit
    cache_dir, work = plan.paths.cache, plan.paths.work
    rows = src.filling.strip_rows(grid.width) if strips else None
    temporary = lambda name: os.path.join(work, name)  # a mask of step 1 in strips, removed after its use
    _step(plan, 1, f"downloading elevation data ({source.name})")
    try:
        _download_layers(plan)
        elevation_path = src.prepare_layer(source.nmt, grid, cache_dir, os.path.join(work, "nmt.npy"), "terrain",
                                           p.update, download=False, rows=rows)
        progress.compute.start("area coverage", 1, unit="step")
        if rows is None:
            mask = plan.area.mask(grid)
            with_data = float(np.isfinite(np.load(elevation_path, mmap_mode="r")[mask]).mean()) if mask.any() else 0.0
        else:
            mask = _area_mask_rows(plan.area, grid, temporary("mask.npy"), rows, full=not plan.border)
            with_data = None  # its line alone needs it, and a tile inside the country has no reader for that
            if plan.border:
                z = np.load(elevation_path, mmap_mode="r")
                with_data = _share_rows(lambda r0, r1: np.isfinite(z[r0:r1]) & mask[r0:r1],
                                        lambda r0, r1: mask[r0:r1], grid.height, rows)
                del z
        progress.compute.update(1)
        progress.compute.finish()
        if with_data is not None:
            emit("info", f"Elevation data: {100 * with_data:.2f}% of the search area from {source.name}")
        surface_path = None
        if plan.nmpt:
            surface_path = src.prepare_layer(source.nmpt, grid, cache_dir, os.path.join(work, "nmpt.npy"), "surface",
                                             p.update, download=False, rows=rows)
        # Order matters: where the sea is, then gaps on land (outside the sea), then the water
        water_path = filled_path = covered_path = joined_path = sea_zone = wbm = terrain = tile_terrain = None
        face_path = shore_segments = shore_kinds_path = None
        if p.water == "fill":
            wbm = src.water_body_mask(grid, cache_dir, os.path.join(work, "wbm.npy"), p.update, download=False,
                                      rows=rows)
            if rows is None:
                sea, coast_source, warning = coast.sea_mask(grid, cache_dir, p.coastline, wbm == src.OCEAN, p.update,
                                                            extent=plan.search_grid)
            else:
                sea, coast_source, warning = coast.sea_mask_rows(
                    grid, cache_dir, p.coastline, lambda r0, r1: wbm[r0:r1] == src.OCEAN, p.update,
                    np.lib.format.open_memmap(temporary("sea.npy"), mode="w+", dtype=bool, shape=wbm.shape), rows,
                    extent=plan.search_grid)
            emit("info", f"Coastline: {coast_source}")
            if coast_source.startswith("OpenStreetMap"):
                src.used_data.append({"layer": coast_source, "credit": src.OSM_CREDIT.as_dict()})
            if warning:
                emit("warning", warning)
            progress.compute.start("shore zone", 1, unit="step")
            if rows is None:
                sea_zone = src.near(sea, p.shore_buffer, grid.res)
            else:
                sea_zone = src.filling.near_rows(lambda r0, r1: sea[r0:r1], p.shore_buffer, grid.res,
                                                 src.filling.new_mask(temporary("sea_zone.npy"), wbm.shape), rows)
            del sea  # only the zone is used from here on
            if rows is not None:
                src.filling.remove_grid(temporary("sea.npy"))
            progress.compute.update(1)
            progress.compute.finish()
        elif _fills_gaps(plan):
            # Without --water fill the sea stays without data; keep the gap filling off it too
            wbm = src.water_body_mask(grid, cache_dir, os.path.join(work, "wbm.npy"), p.update, download=False,
                                      rows=rows)
            progress.compute.start("shore zone", 1, unit="step")
            if rows is None:
                sea_zone = src.near(wbm == src.OCEAN, src.SHORE_BUFFER, grid.res)
            else:
                sea_zone = src.filling.near_rows(lambda r0, r1: wbm[r0:r1] == src.OCEAN, src.SHORE_BUFFER, grid.res,
                                                 src.filling.new_mask(temporary("sea_zone.npy"), wbm.shape), rows)
            progress.compute.update(1)
            progress.compute.finish()
        if statistics:
            # The source's own terrain, before any filling (filled pixels are NaN still)
            progress.compute.start("terrain statistics", 1, unit="step")
            z = np.load(elevation_path, mmap_mode="r")
            if strips and plan.tiles:  # each tile's core: the tiles' files and resuming as before
                tile_terrain = [hy.land_histogram(z, mask, wbm, sea_zone, _core_window(grid, c), sea_value=source.sea_fill)
                                for c, _ in plan.tiles]
                terrain = sum(tile_terrain, hy.Histogram.empty())
            else:
                terrain = hy.land_histogram(z, mask, wbm, sea_zone, _core_window(grid, core) if core is not None else None,
                                            sea_value=source.sea_fill)
            del z
            progress.compute.update(1)
            progress.compute.finish()
        if p.water != "fill":
            wbm = None  # used for the zone and the statistics only
        if _fills_gaps(plan):
            # The neighbours' national data at a border first, then the fallbacks
            joined_path, joined = src.filling.fill_from_neighbours(
                elevation_path, surface_path, grid, [src.SOURCES[n] for n in source.neighbours] if plan.border else [],
                cache_dir, os.path.join(work, "joined.npy"), p.update, exclude=sea_zone, rows=rows)
            filled = []
            if source.fallback:
                filled_path, filled = src.fill_gaps_chain(elevation_path, surface_path, grid,
                                                          [src.SOURCES[f] for f in source.fallbacks], cache_dir,
                                                          os.path.join(work, "filled.npy"), p.update, exclude=sea_zone,
                                                          rows=rows)
            for fallback, filled_px in joined + filled:
                if filled_px:
                    emit("info", f"Filled {filled_px * plan.resolution ** 2 / 1e6:.2f} km² of gaps in the data "
                                 f"from {fallback.name}")
        bare = bare_path = None
        if p.water == "fill":
            if surface_path:
                # The shore faces the terrain model lacks (no ground returns on a sea cliff's face) from the
                # surface model, downwards from the terrain's data edge; the rest of the zone is the sea below
                face_path, face_px = src.fill_shore_from_surface(elevation_path, surface_path, grid, sea_zone,
                                                                 os.path.join(work, "face.npy"), sea_value=source.sea_fill,
                                                                 rows=rows)
                if face_px:
                    emit("info", f"Filled {face_px * plan.resolution ** 2:.0f} m² of shore faces without terrain data "
                                 f"from {source.nmpt.description if source.nmpt else 'the surface model'}")
                    # Filled data with the gaps' for filled_m and the map's filter (Data.covered), but no seam:
                    # the anchors at the cliff's top edge stand right next to its face
                    covered_path = os.path.join(work, "covered.npy")
                    shutil.copyfile(face_path, covered_path)  # the face mask itself stays for the shore below
                    if filled_path is not None:
                        src.filling._or_rows(covered_path, filled_path, rows or grid.height)
                else:
                    src.filling.remove_grid(face_path)  # an empty mask: nothing to count
                    face_path = None
            if surface_path and plan.obstacles:
                if rows is None:
                    bare = np.isnan(np.load(elevation_path, mmap_mode="r"))  # filled as water below
                else:
                    bare_path = temporary("bare.npy")  # fill_water writes what it filled there
            water_path = src.fill_water(elevation_path, surface_path, grid, wbm, sea_zone,
                                        os.path.join(work, "water.npy"), sea_value=source.sea_fill, rows=rows,
                                        bare_path=bare_path)
            del wbm
            if bare is not None:
                bare &= np.load(water_path)  # water the terrain model lacked: no obstacles there
            elif bare_path:
                bare = np.load(bare_path, mmap_mode="r")
            if shore != "none":
                # The uncertain shore: the faces from the surface model and the sea fill standing in for
                # a cliff's foot (the terrain model ends above the water); segments for the run's files,
                # or the kinds on the grid for the 3D view's patch
                progress.compute.start("uncertain shore", 1, unit="step")
                if shore == "kinds":
                    shore_path = os.path.join(work, "shore.npy")
                    kinds = np.lib.format.open_memmap(shore_path, mode="w+", dtype=np.uint8, shape=(grid.height, grid.width))
                    z, wet = np.load(elevation_path, mmap_mode="r"), np.load(water_path, mmap_mode="r")
                    face = np.load(face_path, mmap_mode="r") if face_path else None
                    for r0, r1, _, _ in src.filling.strips(grid.height, rows or grid.height):
                        kinds[r0:r1] = src.filling.shore_rows(z, wet, face, r0, r1)
                    kinds.flush()
                    del kinds, z, wet, face
                    shore_kinds_path = shore_path
                    progress.compute.update(1)
                    progress.compute.finish()
                else:
                    shore_segments = src.filling.shore_segments(elevation_path, water_path, face_path, grid, rows=rows)
                    totals = shore_segments["totals"]
                    progress.compute.update(1)
                    progress.compute.finish(f"{totals['surface_m'] + totals['sea_m']} m")
                    if totals["surface_m"] + totals["sea_m"] >= SHORE_WARN_M:
                        emit("warning", messages.Note(
                            f"the terrain model has no data at the foot of about {totals['surface_m'] + totals['sea_m']} m "
                            "of shore (the map shows where); lines ending or passing there are less certain",
                            "shore_uncertain", surface=totals["surface_m"], sea=totals["sea_m"]))
            if face_path:
                src.filling.remove_grid(face_path)
        del sea_zone
        if rows is not None:
            src.filling.remove_grid(temporary("sea_zone.npy"))
    except RuntimeError as e:
        raise SearchError.of(e, f"Download failed: {e}", "download_failed", reason=cache.clean_error(e))
    elevation = np.load(elevation_path, mmap_mode="r")
    surface = np.load(surface_path, mmap_mode="r") if surface_path else None
    if surface is not None:
        progress.compute.start("surface coverage", 1, unit="step")
        if rows is None:
            land = mask & ~np.isnan(elevation)
            no_surface = (np.isnan(surface) & land).sum() / max(land.sum(), 1)
        else:
            land = lambda r0, r1: mask[r0:r1] & ~np.isnan(elevation[r0:r1])
            no_surface = _share_rows(lambda r0, r1: np.isnan(surface[r0:r1]) & land(r0, r1), land, grid.height, rows)
        progress.compute.update(1)
        progress.compute.finish()
        if no_surface > 0.01:
            emit("warning", messages.Note(f"no surface model (trees, buildings) for {no_surface:.0%} of the search "
                                          "area.\nLines there are checked against the bare terrain only: trees and "
                                          "buildings under\nthem are not marked.", "no_surface",
                                          percent=round(100 * no_surface)))
    if surface is not None and plan.obstacles:
        # Trees and buildings, not the terrain's own rock (obstacles.py): what every line is checked against
        obstacles_path = os.path.join(work, "obstacles.npy")
        out = np.lib.format.open_memmap(obstacles_path, mode="w+", dtype=np.float32, shape=surface.shape)
        obstacles.obstacle_surface(elevation, surface, plan.resolution, out, bare=bare, **plan.obstacles)
        src.mosaic.flush_grid(out)
        del out, bare
        if bare_path:
            src.filling.remove_grid(bare_path)
        surface = np.load(obstacles_path, mmap_mode="r")
    slope = None
    if p.slope_file:
        slope_path = src.load_slope_file(p.slope_file, grid, os.path.join(work, "slope.npy"))
        slope = np.load(slope_path, mmap_mode="r")
    return Data(elevation, surface,
                np.load(water_path, mmap_mode="r") if water_path else None,
                np.load(filled_path, mmap_mode="r") if filled_path else None, slope,
                np.load(joined_path, mmap_mode="r") if joined_path else None, mask, terrain, tile_terrain,
                covered=np.load(covered_path, mmap_mode="r") if covered_path else None, shore=shore_segments,
                shore_kinds=np.load(shore_kinds_path, mmap_mode="r") if shore_kinds_path else None)


def find_lines(plan: Plan, data: Data) -> Lines:
    """Steps 2-4: anchors, line search, coordinates and profiles, groups."""
    results, groups = _lines(plan, data)
    return Lines(results, groups, hy.statistics(data.terrain, plan.resolution), data.shore)


def _lines(plan: Plan, data: Data, core: Optional[tuple] = None, before: int = 0) -> Tuple[sh.LineTable, mp.Groups]:
    """Steps 2-4: the lines and their groups; with core (bounds), only lines whose first
    anchor (smaller x, then y) lies in it. before: the lines of the tiles done already, which
    count towards the limit of lines with these (held in memory together in step 4).

    Every line gets its metres over water and over filled gaps. Circles keep the profile
    of every line (the map shows each) while they fit into CIRCLE_PROFILES_BYTES; areas (and
    larger circles) only that of the line shown for each group, as the profiles of millions
    of lines would take long and fill the memory.
    """
    # The kernels (numba) only inside the functions that run them (here, _anchors, _pair_search,
    # count_tile and line_coordinates): the download phase and the quick lane, which import this
    # module too, never load numba and llvmlite (their time and memory)
    import lineprofiles as lp

    p, grid, emit = plan.params, plan.grid, plan.emit
    found = _anchors(plan, data, quiet=core is not None)
    if found is None:  # a tile of a large area: nothing here
        return sh.LineTable.empty(), mp.Groups.each_alone(0)

    # Step 3: Compare each promising anchor to every other anchor
    _step(plan, 3, "evaluating anchor pairs")
    sag_table = None
    if p.model == "sag":
        key = (dataclasses.astuple(plan.rigging), p.min_length, p.max_length)
        if key not in _SAG_TABLES:  # once per process: the tiles of an area share it
            emit("info", "Precomputing the sag estimator for all line lengths...")
        sag_table = _sag_table(*key)
    valid_lines = _pair_search(plan, data, found, core, sag_table,
                               check=_early_check(plan, before, grid.width * grid.height))
    points = profile_points(valid_lines) if isinstance(plan.area, ar.Circle) else 0
    every_profile = 0 < points * PROFILE_POINT_BYTES <= CIRCLE_PROFILES_BYTES
    if points and not every_profile:
        emit("info", f"Profiles of the line shown for each spot only: those of all {len(valid_lines)} lines "
                     f"would take about {points * PROFILE_POINT_BYTES / 1e6:.0f} MB")
    _check_lines(plan, before + len(valid_lines), grid.width * grid.height, points if every_profile else 0)
    if not valid_lines and core is None:
        raise SearchError("No lines found matching elevation requirements.", "no_lines")

    # Step 4: coordinates, water and gaps, groups, profiles
    _step(plan, 4, "coordinates, groups and profiles")
    results = line_coordinates(valid_lines, grid, plan.nmpt, plan.resolution, data.water, data.filled_pixels(), core)
    del valid_lines  # the same table (in place)
    _count(plan, "lines", len(results))
    a1, a2 = results.columns["a1"], results.columns["a2"]
    groups = mp.group_lines(results, plan.group_distance, p.group_by)
    wanted = np.arange(len(results)) if every_profile else np.unique(groups.rep)
    progress.compute.start("line profiles", len(wanted), unit="line")
    batch = lp.line_profiles(a1[wanted], a2[wanted], data.elevation, plan.resolution, data.surface,
                             sag_table=sag_table, water=data.water, filled=data.filled_pixels(),
                             on_part=progress.compute.update, end_zone=plan.end_zone,
                             lift=plan.lift)  # helpers.line_profile of each, in parallel
    results.profiles.update(zip(wanted.tolist(), map(batch.__getitem__, range(len(wanted)))))
    progress.compute.finish()
    del a1, a2
    return results.without_pixels(), groups  # nothing reads the pixels from here on


def at_seams(gaps: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    """Which anchors ([row, col]) lie at a seam of the mask `gaps` (filled gaps, a neighbour's
    data): binary_dilation(gaps) & ~binary_erosion(gaps) of scipy with a 3 x 3 structure, read
    at the anchors only. The dilation is "a gap within the anchor's 3 x 3 neighbourhood", the
    erosion "all 9 pixels gaps" with the outside of the grid as no gap (border_value 0): an
    anchor is at a seam when its neighbourhood, clipped at the grid's edges, holds a gap and
    either a pixel that is not a gap or a place outside the grid. Nine gathers at the anchors
    instead of two operations over the whole grid (tests/test_units.py::test_seams_as_before)."""
    h, w = gaps.shape
    rows, cols = anchors[:, 0], anchors[:, 1]
    any_gap = np.zeros(len(anchors), dtype=bool)
    all_gaps = np.ones(len(anchors), dtype=bool)
    for dr in (-1, 0, 1):
        r = rows + dr
        r_in = (r >= 0) & (r < h)
        r = np.clip(r, 0, h - 1)
        for dc in (-1, 0, 1):
            c = cols + dc
            gap = np.asarray(gaps[r, np.clip(c, 0, w - 1)], dtype=bool) & r_in & (c >= 0) & (c < w)
            any_gap |= gap
            all_gaps &= gap
    return any_gap & ~all_gaps


@dataclass
class Anchors:
    """Step 2's results: the anchors ([row, col]), their prominence and drop (terrain.py; None: not
    computed, _pair_search leaves them to the first line), and the mask of the strong ones
    (--min-prominence; None: every anchor)."""
    anchors: np.ndarray
    prominence: Optional[np.ndarray]
    drop: Optional[np.ndarray]
    strong: Optional[np.ndarray]


def _anchor_values(plan: Plan, data: Data, anchors: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """How far each anchor stands out (terrain.py): its prominence and its drop."""
    import terrain  # numba: only when computing (test_search_imports_numba_only_to_compute)

    progress.compute.start("anchor prominence and drop", 2, unit="step")
    prom = terrain.prominence(data.elevation, anchors, plan.resolution, plan.params.prominence_span)
    progress.compute.update(1)
    drop = terrain.drop(data.elevation, anchors, plan.resolution, plan.params.drop_radius)
    progress.compute.finish()
    return prom, drop


def _anchors(plan: Plan, data: Data, quiet: bool = False, deferred: bool = False) -> Optional[Anchors]:
    """Step 2: the steep pixels of the area (not at the seams of filled gaps or a neighbour's
    data) within the elevation band (--min/--max-elevation), with their prominence and drop and
    the limits on them. Too few anchors: None when quiet (a tile, a count), else SearchError.
    limits.anchors_max refuses too many either way. deferred: prominence and drop left to the
    first line when no limit needs them (a count: most tiles of a country have no line)."""
    p, grid, emit = plan.params, plan.grid, plan.emit
    _step(plan, 2, "finding significant slopes")
    anchors = sh.find_significant_slopes(data.elevation, plan.resolution, p.slope_threshold,
                                         plan.area.mask(grid) if data.mask is None else data.mask, data.slope,
                                         threads=line_threads(p))
    for seams in (data.filled, data.joined):
        if seams is not None:  # slopes across the edge of a filled gap mix two surveys: not reliable anchors there
            anchors = anchors[~at_seams(seams, anchors)]
    emit("info", f"Found {len(anchors)} potential anchors to evaluate")
    _count(plan, "anchors", len(anchors))
    # --min-elevation / --max-elevation: both anchors of a line within the band, so anchors
    # outside it are no partners either (compared in float32, the grid's type)
    banded = False
    if p.min_elevation is not None or p.max_elevation is not None:
        z = data.elevation[anchors[:, 0], anchors[:, 1]]
        inside = np.ones(len(anchors), dtype=bool)
        if p.min_elevation is not None:
            inside &= z >= np.float32(p.min_elevation)
        if p.max_elevation is not None:
            inside &= z <= np.float32(p.max_elevation)
        if not inside.all():
            banded = True
            anchors = anchors[inside]
            emit("info", f"Anchors within the elevation limits: {len(anchors)}")
    if plan.limits and plan.limits.anchors_max and len(anchors) > plan.limits.anchors_max:
        raise SearchError(f"{len(anchors)} anchors, at most {plan.limits.anchors_max} on this site: a higher "
                          f"--slope-threshold, narrower --min-elevation/--max-elevation, a coarser --resolution "
                          f"or a smaller area", "too_many_anchors", n=len(anchors), max=plan.limits.anchors_max)
    if len(anchors) < 2:
        if quiet:
            return None
        if banded:
            raise SearchError("Not enough steep terrain within the elevation limits. Try a wider "
                              "--min-elevation/--max-elevation or a lower --slope-threshold.",
                              "no_anchors_in_elevation_range")
        raise SearchError("Not enough steep terrain. Try a lower --slope-threshold or a larger --radius.",
                          "no_steep_terrain")

    if deferred and p.min_prominence is None and p.min_prominence_both is None and p.min_drop is None:
        return Anchors(anchors, None, None, None)
    # How far each anchor stands out (terrain.py); the limits for both anchors leave anchors out
    prom, drop = _anchor_values(plan, data, anchors)
    keep = np.ones(len(anchors), dtype=bool)
    if p.min_prominence_both is not None:
        keep &= prom >= p.min_prominence_both
    if p.min_drop is not None:
        keep &= drop >= p.min_drop
    if not keep.all():
        emit("info", f"Anchors left after the prominence and drop limits: {int(keep.sum())}")
        anchors, prom, drop = anchors[keep], prom[keep], drop[keep]
    # --min-prominence: one anchor of each line; the others stay as partners
    strong = None if p.min_prominence is None else prom >= p.min_prominence
    if len(anchors) < 2 or (strong is not None and not strong.any()):
        if quiet:
            return None
        raise SearchError("No anchors stand out enough. Try a lower --min-prominence, --min-prominence-both "
                          "or --min-drop.", "no_prominent_anchors")
    return Anchors(anchors, prom, drop, strong)


def _pair_search(plan: Plan, data: Data, found: Anchors, core: Optional[tuple], sag_table,
                 check: Optional[Callable[[int], None]] = None,
                 sink: Optional[Callable[[sh.LineTable], None]] = None) -> Optional[sh.LineTable]:
    """Step 3's line search (linesearch.find_valid_lines) with the arguments of the plan: with
    core (bounds), pairs only from the anchors in it (the overlap is for partners)."""
    import linesearch as ls

    p, grid = plan.params, plan.grid
    anchors = found.anchors
    first = None
    if core is not None:  # pairs only from the anchors in the core: the overlap is for partners
        left, bottom, right, top = core
        x, y = grid.pixel_to_xy(anchors[:, 0], anchors[:, 1])
        first = (left <= x) & (x < right) & (bottom <= y) & (y < top)
    _count(plan, "grids", 1)
    _count(plan, "anchors_kept", len(anchors))  # what the line search gets
    values = ((lambda: np.column_stack(_anchor_values(plan, data, anchors))) if found.prominence is None
              else np.column_stack([found.prominence, found.drop]))
    return ls.find_valid_lines(data.elevation, data.surface, anchors, plan.resolution,
                               p.min_length, p.max_length, plan.nmpt, line_threads(p),
                               sag_table, p.max_anchor_diff / 100, p.max_anchor_diff_m, first,
                               p.high_above, sh.LineLimits(p.min_height, p.min_mean_height,
                                                           p.min_high_share, p.max_wall_angle),
                               values, found.strong, stats=plan.funnel, check=check, sink=sink,
                               end_zone=plan.end_zone, lift=plan.lift)


def count_tile(plan: Plan, data: Data, core: Optional[tuple], sink: Callable[[sh.LineTable], None],
               sag_table=None) -> Dict[str, int]:
    """Steps 2 and 3 of a tile in count mode (the country layer): the valid lines go to sink part
    by part (linesearch.find_valid_lines(sink=)), each part with "a1", "a2", the LINE_VALUES and
    "water_px" (int64: linesearch.covered_pixels of data.water), and nothing is kept. The same
    anchors, first mask (core), line limits and arguments as _lines; no step 4 (the sink decides
    which first anchors lie in core), no "no steep terrain"/"no lines" errors (an empty grid hands
    the sink nothing), no _early_check or _check_lines (limits.anchors_max stays). The model "sag"
    uses sag_table, or an EnvelopeTable of plan.rigging when None. Returns plan.funnel with this
    call's counts added."""
    import linesearch as ls

    p, emit = plan.params, plan.emit
    found = _anchors(plan, data, quiet=True, deferred=True)
    if found is None:
        return plan.funnel
    _step(plan, 3, "evaluating anchor pairs")
    if p.model != "sag":
        sag_table = None
    elif sag_table is None:
        emit("info", "Precomputing the sag estimator for all line lengths...")
        sag_table = sg.EnvelopeTable(plan.rigging, p.min_length, p.max_length)
    water = data.water

    def with_water(part: sh.LineTable):
        part.columns["water_px"] = ls.covered_pixels(part.columns["a1"], part.columns["a2"], water)
        sink(part)

    _pair_search(plan, data, found, core, sag_table, sink=with_water)
    return plan.funnel


def line_coordinates(lines: sh.LineTable, grid, nmpt: Optional[str], res: float, water: Optional[np.ndarray],
                     filled: Optional[np.ndarray], core: Optional[tuple] = None) -> sh.LineTable:
    """Step 4 before the groups, in place (no second table of the lines): their coordinates
    (mapping.coordify), only the lines whose first anchor lies in core (a tile's bounds) when
    given, and their metres over water and over filled gaps. Returns the lines."""
    import linesearch as ls  # numba (see _lines)
    results = mp.coordify(lines, grid, nmpt)
    if core is not None:
        left, bottom, right, top = core
        x, y = mp.first_anchor(results).T
        inside = (left <= x) & (x < right) & (bottom <= y) & (y < top)
        del x, y
        results.reorder(inside)
        del inside
    a1, a2 = results.columns["a1"], results.columns["a2"]
    progress.compute.start("over water and filled gaps", 2, unit="mask")
    results.columns["water_m"] = ls.covered_metres(a1, a2, res, water)
    progress.compute.update(1)
    results.columns["filled_m"] = ls.covered_metres(a1, a2, res, filled)
    progress.compute.finish()
    return results


def _count(plan: Plan, key: str, n: int):
    """Add to a count of the line search's funnel (Plan.funnel)."""
    plan.funnel[key] = plan.funnel.get(key, 0) + int(n)


def _check_lines(plan: Plan, count: int, pixels: int = 0, points: int = 0):
    """Refuse more lines than plan.limits allows, or than fit with grids of this many pixels (and
    profiles of this many points: a circle's) into the memory free when the search started
    (before their coordinates, profiles, groups and files)."""
    if plan.limits and plan.limits.lines_max and count > plan.limits.lines_max:
        raise SearchError(f"{count} lines, at most {plan.limits.lines_max} on this site: a higher --min-prominence "
                          f"(or --min-height, --min-drop), a coarser --resolution or a smaller area", "too_many_lines",
                          n=count, max=plan.limits.lines_max)
    if plan.memory is not None and memory_needed(pixels, count, points) > plan.memory:
        per_line = memory_needed(0, 1, points / max(count, 1))  # with the mean profile of these lines
        fits = max(0, int((plan.memory - memory_needed(pixels, 0)) // per_line))
        raise SearchError(f"{count} lines, at most {fits} fit into the memory of this site: a higher --min-prominence "
                          f"(or --min-height, --min-drop), a coarser --resolution or a smaller area",
                          "too_many_lines_memory", n=count, max=fits)


def _early_check(plan: Plan, before: int, pixels: int) -> Optional[Callable[[int], None]]:
    """The check find_valid_lines makes after each part of the pairs it evaluates (F7, with
    Plan.early_stop): the valid lines so far and those of the tiles done already against lines_max
    (with limits), and against Plan.memory with grids of this many pixels but no profiles (for a
    user without limits too: a compute slot's budget is a safeguard; a lower bound of what
    _check_lines asks for these lines, so it refuses only what that would refuse). None with the
    switch off or nothing to check: _check_lines decides on the exact count."""
    lines_max = plan.limits.lines_max if plan.limits else None
    if not plan.early_stop or (not lines_max and plan.memory is None):
        return None

    def check(count: int):
        total = before + count
        if lines_max and total > lines_max:
            raise SearchError(f"more than {lines_max} lines (the search stopped at {total}), at most "
                              f"{lines_max} on this site: a higher --min-prominence (or --min-height, "
                              f"--min-drop), a coarser --resolution or a smaller area", "too_many_lines_early",
                              n=total, max=lines_max)
        if plan.memory is not None and memory_needed(pixels, total) > plan.memory:
            fits = max(0, int((plan.memory - memory_needed(pixels, 0)) // LINE_BYTES))
            raise SearchError(f"more than {fits} lines (the search stopped at {total}), at most {fits} fit into the "
                              f"memory of this site: a higher --min-prominence (or --min-height, --min-drop), a "
                              f"coarser --resolution or a smaller area", "too_many_lines_memory_early",
                              n=total, max=fits)
    return check


def _run_name(plan: Plan) -> str:
    p = plan.params
    if p.name:
        return p.name
    if p.area and p.area.startswith("osm:"):
        return p.area[4:]
    if p.area:
        return _area_text(p)
    lat, lon = plan.area.center
    return rn.place_name(lat, lon, plan.paths.cache) or (ar.DRAWN if p.geometry is not None else f"{lat:.5f}, {lon:.5f}")


def _search_hash(plan: Plan) -> str:
    """What identifies the same tiled search, to resume it."""
    p = plan.params.model_dump(exclude={"name", "update", "no_html", "ortho", "ortho_detail", "threads",
                                        "opentopo_key", "tile_size", "group_distance", "group_by"})
    for name in ("min_elevation", "max_elevation"):  # unset: the hash of before (its tiles resume)
        if p[name] is None:
            del p[name]
    for name in ("end_zone", "anchor_lift"):  # 0: the hash of before
        if p[name] == 0:
            del p[name]
    key = {"params": p, "source": plan.source.id, "resolution": plan.resolution}
    if plan.owner is not None:  # a user resumes only their own search (locally the hash of before)
        key["owner"] = plan.owner
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _open_run(plan: Plan) -> Dict:
    """The run folder of a tiled search: an unfinished one of the same search (whose tile
    size is then used again, so its finished tiles fit), or a new one."""
    key = _search_hash(plan)
    for path in sorted(glob.glob(os.path.join(plan.paths.runs, "*", "progress.json")), reverse=True):
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("status") == "running" and state.get("search") == key:
            folder = os.path.dirname(path)
            if state["tile_core"] != plan.tile_core:
                plan.tile_core = state["tile_core"]
                plan.tiles = _tiles(plan.grid, plan.params, plan.resolution, plan.source.grid_origin, plan.tile_core)
            done = len(glob.glob(os.path.join(folder, "tiles", TILE_FILE.format("*"))))
            plan.emit("info", f"Resuming run {os.path.basename(folder)}: {done} of {len(plan.tiles)} tiles done")
            return {"id": os.path.basename(folder), "path": folder, "name": state["name"],
                    "created": datetime.fromisoformat(state["created"]), "search": key,
                    "tile_core": state["tile_core"]}
    created = datetime.now()
    name = _run_name(plan)
    run = rn.new_run(plan.paths.runs, name, created)
    run.update(name=name, created=created, search=key, tile_core=plan.tile_core)
    _progress(run, "running")
    return run


def _progress(run: Dict, status: str):
    """progress.json of a tiled run: its state while running (run.json is written at the end)."""
    with open(os.path.join(run["path"], "progress.json"), "w", encoding="utf-8") as f:
        json.dump({"status": status, "search": run["search"], "tile_core": run["tile_core"],
                   "name": run["name"], "created": run["created"].isoformat()}, f)


TILE_FILE = "{}.table.pkl.gz"  # a finished tile's lines; "<k>.pkl.gz" of before held a dict per line
TERRAIN_FILE = "{}.terrain.npz"  # its terrain's histogram (hypsometry.save), saved before the tile file


def _save_tile(path: str, lines: sh.LineTable):
    """A finished tile's lines: the pickle of its LineTable (its columns and profiles), gzipped.

    Level 1: level 9 took 23 times as long for 21% less (the floats hardly compress),
    11 minutes for a tile of 12.5 million lines (as dicts).
    """
    progress.compute.start("saving tile lines", len(lines), unit="line")
    with gzip.open(path + ".part", "wb", compresslevel=1) as f:
        pickle.dump(lines, f, pickle.HIGHEST_PROTOCOL)
    os.replace(path + ".part", path)
    progress.compute.update(len(lines))
    progress.compute.finish()


def _load_tile(path: str) -> sh.LineTable:
    """The lines of a tile saved by _save_tile."""
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def _tile_window(grid: gd.Grid, tile: gd.Grid) -> Tuple[slice, slice]:
    """The rows and columns of the search's grid under a tile's grid (tile_grid: on the same
    pixel edges, within it)."""
    r0, c0 = int(round((grid.top - tile.top) / grid.res)), int(round((tile.left - grid.left) / grid.res))
    if not (0 <= r0 and r0 + tile.height <= grid.height and 0 <= c0 and c0 + tile.width <= grid.width):
        raise ValueError(f"the tile {tile.bounds} lies outside the grid {grid.bounds}")
    return slice(r0, r0 + tile.height), slice(c0, c0 + tile.width)


def _tile_data(data: Data, grid: gd.Grid, tile: gd.Grid, work: str, terrain: Optional[hy.Histogram]) -> Data:
    """The grids of a tile of a tiled search: its window of the area's grids of step 1 (data, on
    grid) copied, strip by strip, into contiguous memory-mapped grids of its work folder
    (nmt.npy and the others, as a tile's own step 1 wrote them), so steps 2-4 read what they read
    before; the area mask's window in memory; terrain the histogram of the tile's core."""
    rows, cols = _tile_window(grid, tile)
    step = src.filling.strip_rows(tile.width)

    def window(array: np.ndarray, r0: int, r1: int) -> np.ndarray:
        """Rows [r0, r1) of the tile's window of an area grid, read through a mapping of its own:
        the pages read leave the process's working set with it (the area's mappings of `data`
        would keep them resident through steps 2-4 of every tile)."""
        source = np.load(array.filename, mmap_mode="r")
        try:
            return np.array(source[rows.start + r0:rows.start + r1, cols])
        finally:
            del source

    def copy(array: Optional[np.ndarray], name: str) -> Optional[np.ndarray]:
        if array is None:
            return None
        path = os.path.join(work, name)
        out = np.lib.format.open_memmap(path, mode="w+", dtype=array.dtype, shape=(tile.height, tile.width))
        for r0 in range(0, tile.height, step):
            r1 = min(tile.height, r0 + step)
            out[r0:r1] = window(array, r0, r1)
        out.flush()
        del out
        return np.load(path, mmap_mode="r")

    return Data(copy(data.elevation, "nmt.npy"), copy(data.surface, "surface.npy"), copy(data.water, "water.npy"),
                copy(data.filled, "filled.npy"), copy(data.slope, "slope.npy"), copy(data.joined, "joined.npy"),
                window(data.mask, 0, tile.height), terrain, covered=copy(data.covered, "covered.npy"))


def _remove_grids(work: str):
    """Remove the grids of step 1 from the work folder (its own files; the subfolders of the
    tiles, the profiles at tile edges and the saving stay as they are)."""
    for path in glob.glob(os.path.join(work, "*.npy")):
        src.filling.remove_grid(path)


class _SilentBar:
    """A progress bar that shows nothing (start, update and finish do nothing)."""

    def start(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass

    def finish(self, *args, **kwargs):
        pass


@contextlib.contextmanager
def _silent_progress():
    """The bars and the step left as they are while a search runs inside a step of another: a
    profile at a tile edge (search_lines) runs profile_of_line, whose prepare_data would start
    its own bars under "Step 1" and move the step, breaking the bar "profiles at tile edges"
    and listing its seconds under step 1 (tools/perf_profile.py, jobs.StepClock)."""
    bars = progress.download, progress.compute
    progress.download = progress.compute = _SilentBar()
    progress.set_step = lambda text: None  # shadows the class's method on the instance
    try:
        yield
    finally:
        progress.download, progress.compute = bars
        del progress.set_step


def search_lines(plan: Plan) -> Tuple[Lines, Optional[Dict]]:
    """Steps 1-4 for one grid or, for a large area, tile by tile (resumable).

    A tiled search runs step 1 once, on the whole grid (prepare_data(strips=True): the gap
    offsets, the lake levels and the border gaps are the area's, in strips of rows); each tile
    then takes its window of the area's grids (_tile_data) for steps 2-4. The area's grids
    are made again when a search resumes (the work folder does not outlive a job) and removed
    once the last tile is done.
    Returns the lines and, for a tiled search, its run (to be completed by save_run).
    """
    if not plan.tiles:
        lines = find_lines(plan, prepare_data(plan))
        progress.set_step("")
        return lines, None
    run = _open_run(plan)
    folder = os.path.join(run["path"], "tiles")
    os.makedirs(folder, exist_ok=True)
    tables, count = [], 0
    terrain: Optional[hy.Histogram] = hy.Histogram.empty()  # of the tiles' cores; None once one is not known
    todo = [k for k in range(len(plan.tiles)) if not os.path.exists(os.path.join(folder, TILE_FILE.format(k)))]
    area = prepare_data(plan, strips=True) if todo else None  # step 1 once, on the whole grid
    shore_path = os.path.join(run["path"], SHORE_FILE)  # the area's uncertain shore, kept for a resumed search
    if area is not None and area.shore is not None:
        with open(shore_path, "w", encoding="utf-8") as f:
            json.dump(area.shore, f, separators=(",", ":"))
    for k, (core, tile) in enumerate(plan.tiles):
        path = os.path.join(folder, TILE_FILE.format(k))
        terrain_path = os.path.join(folder, TERRAIN_FILE.format(k))
        if not os.path.exists(path):
            plan.emit("info", f"\n--- Tile {k + 1} of {len(plan.tiles)} ({tile.width} x {tile.height} px) ---")
            work = os.path.join(plan.paths.work, f"tile{k}")
            os.makedirs(work, exist_ok=True)
            tile_plan = dataclasses.replace(plan, grid=tile, paths=Paths(plan.paths.data, work), tiles=None,
                                            tile_label=f"Tile {k + 1}/{len(plan.tiles)} · ")
            data = _tile_data(area, plan.grid, tile, work, area.tile_terrain[k] if area.tile_terrain else None)
            found, _ = _lines(tile_plan, data, core, before=count)
            histogram = data.terrain
            del data
            gc.collect()  # close the memory-mapped grids before deleting them (Windows)
            shutil.rmtree(work, ignore_errors=True)
            progress.set_step(f"{tile_plan.tile_label}Step 4/{STEPS}: saving the tile's lines")
            hy.save(terrain_path, histogram)  # before the tile file, which marks the tile done
            _save_tile(path, found)
            table = found.without_pixels()  # what loading the file gives, without the round trip
            del found
        else:
            progress.set_step(f"Step 4/{STEPS}: loading tile {k + 1}/{len(plan.tiles)}")
            table = _load_tile(path).without_pixels()  # tile files of before, tiles without anchors
            histogram = hy.load(terrain_path)  # None for a tile saved before the statistics
        terrain = terrain + histogram if terrain is not None and histogram is not None else None
        tables.append(table)
        count += len(tables[-1])
        _check_lines(plan, count)
    if area is not None:
        del area
        gc.collect()  # close the area's memory-mapped grids before deleting them (Windows)
        _remove_grids(plan.paths.work)
    if not count:
        raise SearchError("No lines found matching elevation requirements.", "no_lines")
    results = sh.LineTable.join(tables)  # column by column, each tile's column released once joined
    del tables
    progress.set_step(f"Step 4/{STEPS}: groups of all tiles")
    groups = mp.group_lines(results, plan.group_distance, plan.params.group_by)
    # A line shown for a group is the best of its tile's group too, except near the edge of a
    # tile, where a group may join lines of two tiles: those get their profile now
    missing = [k for k in groups.rep.tolist() if k not in results.profiles]
    if missing:
        meta = {"params": _run_params(plan), "source": {"id": plan.source.id}, "center": {"crs": plan.crs},
                "data": json.loads(json.dumps(src.used_data))}
        used = list(src.used_data)  # plan_search starts a new record of the data used
        progress.compute.start("profiles at tile edges", len(missing), unit="line")
        for k in missing:
            paths = Paths(plan.paths.data, os.path.join(plan.paths.work, "edge"))
            os.makedirs(paths.work, exist_ok=True)
            with _silent_progress():  # its own step 1 (prepare_data) must not move the step or the bar
                results.profiles[k] = profile_of_line(meta, paths, tuple(results.columns["anchor1"][k].tolist()),
                                                      tuple(results.columns["anchor2"][k].tolist()))
            shutil.rmtree(paths.work, ignore_errors=True)
            progress.compute.update(1)
        progress.compute.finish()
        src.used_data[:] = used
    progress.set_step("")
    shore = None
    if os.path.isfile(shore_path):
        with open(shore_path, encoding="utf-8") as f:
            shore = json.load(f)
    return Lines(results, groups, hy.statistics(terrain, plan.resolution), shore), run


def _merged_data() -> List[Dict]:
    """src.used_data with the entries of several tiles merged per layer."""
    merged: Dict[tuple, Dict] = {}
    for entry in src.used_data:
        key = (entry.get("layer"), entry.get("folder"), entry.get("file"))
        if key not in merged:
            merged[key] = json.loads(json.dumps(entry))
            continue
        m = merged[key]
        if "paths" in entry:  # files shared by tiles are listed once
            m["paths"] = sorted(set(m["paths"]) | set(entry["paths"]))
            m["files"] = len(m["paths"])
        for k, pick in (("oldest", min), ("newest", max)):
            values = [v for v in (m.get("fetched", {}).get(k), entry.get("fetched", {}).get(k)) if v]
            if values:
                m.setdefault("fetched", {})[k] = pick(values)
        if entry.get("survey_years") and m.get("survey_years"):
            m["survey_years"] = [min(m["survey_years"][0], entry["survey_years"][0]),
                                 max(m["survey_years"][1], entry["survey_years"][1])]
    return list(merged.values())


def _credits(plan: Plan, data: List[Dict]) -> List[Dict]:
    """Licences and notices of the data a run used (sources.Credit), each once: its layers,
    the OSM coastline, and OSM when the search area came from it (--area coast, cliffs,
    osm:<name> or --within osm:<name>). data: its entries' credits dated already (_dated_data)."""
    credits = [entry["credit"] for entry in data if entry.get("credit")]
    spec = getattr(plan.area, "spec", None) or {}
    if spec.get("area") in ("coast", "cliffs") or any(str(spec.get(k) or "").startswith("osm:")
                                                       for k in ("area", "within")):
        credits.append(src.OSM_CREDIT.as_dict())
    unique: Dict[str, Dict] = {}
    for credit in credits:
        unique.setdefault(json.dumps(credit, sort_keys=True), credit)
    return list(unique.values())


def _dated_data(data: List[Dict], year: int) -> List[Dict]:
    """The data a run used with sources.YEAR in their credits filled with the run's year."""
    return [{**entry, "credit": src.dated_credit(entry["credit"], year)} if entry.get("credit") else entry
            for entry in data]


def _run_params(plan: Plan) -> Dict:
    """The parameters run.json records (also what profile_of_line needs)."""
    p, circle = plan.params, isinstance(plan.area, ar.Circle)
    params = {"radius": p.radius if circle else None,
            "area": None if circle else {"area": ar.DRAWN if p.geometry is not None else p.area,
                                         "buffer": p.buffer, "within": p.within},
            "resolution": plan.resolution,
            "min_length": p.min_length, "max_length": p.max_length,
            "max_anchor_diff": p.max_anchor_diff,
            "max_anchor_diff_m": p.max_anchor_diff_m,
            "slope_threshold": p.slope_threshold, "slope_file": p.slope_file,
            "min_elevation": p.min_elevation, "max_elevation": p.max_elevation, "high_above": p.high_above,
            "min_height": p.min_height, "min_mean_height": p.min_mean_height, "min_high_share": p.min_high_share,
            "max_wall_angle": p.max_wall_angle, "min_prominence": p.min_prominence,
            "min_prominence_both": p.min_prominence_both, "prominence_span": p.prominence_span,
            "min_drop": p.min_drop, "drop_radius": p.drop_radius,
            "nmpt": plan.nmpt, "obstacles": plan.obstacles, "water": p.water, "coastline": p.coastline,
            "shore_buffer": p.shore_buffer, "fill_gaps": p.fill_gaps,
            "group_distance": plan.group_distance,
            "group_by": p.group_by, "model": p.model,
            "rigging": dataclasses.asdict(plan.rigging)}
    # The end zone and the A-frames only when set: run.json of before, and a run without them reads as 0
    if plan.end_zone:
        params["end_zone"] = p.end_zone
    if plan.lift:
        params["anchor_lift"] = p.anchor_lift
    return params


def save_run(plan: Plan, lines: Lines, run: Optional[Dict] = None) -> Result:
    """Step 5: save the run (results, parameters, data used) and the map. The orthophoto for
    offline use is a step of its own after it (orthophoto_lines, download_orthophoto): the map
    reads its tiles from the cache as they arrive and loads the rest online.

    run: the run folder of a tiled search (search_lines); otherwise a new one is made.
    """
    p, emit = plan.params, plan.emit
    results, spot_groups = lines.results, lines.spot_groups
    _step(plan, 5, "saving the run and the map")
    terrain = lines.terrain
    if terrain is None:
        emit("info", "Terrain of the search area: not known")
    else:
        q = terrain["quantiles"]
        emit("info", f"Terrain of the search area: {q[0]:.0f}–{q[100]:.0f} m, mean {terrain['mean']:.0f} m, "
                     f"median {q[50]:.0f} m ({terrain['km2']:.2f} km² of land with data)")
    center_lat, center_lon = plan.area.center
    x, y = plan.center_xy
    if run is None:
        created = datetime.now()
        name = _run_name(plan)
        run = rn.new_run(plan.paths.runs, name, created)
    else:
        created, name = run["created"], run["name"]
    circle = isinstance(plan.area, ar.Circle)
    meta = {
        "id": run["id"],
        "name": name,
        "created": created.astimezone(timezone.utc).isoformat(timespec="seconds"),  # local time in its id
        "center": {"lat": center_lat, "lon": center_lon, "x": x, "y": y, "crs": plan.crs},
        "area": plan.area.describe(),
        "source": {"id": plan.source.id, "name": plan.source.name, "description": plan.source.description},
        "data": _dated_data(_merged_data(), created.year),  # folders, files and fetch times of the data used
        "params": _run_params(plan),
        "summary": {"lines": len(results), "spots": len(spot_groups),
                    "clear_spots": int((~results.columns["over_obstacles"][spot_groups.rep]).sum()),
                    # which lines have a profile in the map (runs before 2026-11: all of a circle's)
                    "profiles": "all" if circle and len(results.profiles) == len(results) else "representatives"},
        "terrain": lines.terrain,  # the land with data of the search area (hypsometry.statistics)
        "shore": lines.shore,  # the uncertain shore (sources.filling.shore_segments), None when not known
    }
    meta["description"] = rn.params_summary(meta)
    meta["attribution"] = _credits(plan, meta["data"])  # also ATTRIBUTION.txt and the map
    if not circle:
        # Large areas: only the group representatives carry a profile in the map
        representatives = set(spot_groups.rep.tolist())
        results.profiles = {k: v for k, v in results.profiles.items() if k in representatives}

    def on_lines(n: int, file: str):
        progress.compute.update(n, file=file)

    def saved():
        """After the results' files: a tiled run is done (not resumed again), the message."""
        if "search" in run:
            _progress(run, "done")
        emit("info", f"Run \"{name}\" saved to {os.path.abspath(run['path'])}")

    ortho_cache = ortho_service = None
    if not p.no_html:
        source = plan.source
        # The folder the map reads the orthophoto tiles from (download_orthophoto fills it after
        # the run, earlier runs did too), falling back to the service for a tile not there
        ortho_cache = ortho.cache_folder(plan.paths.cache, source.ortho) if _orthophoto(plan) else None
        ortho_service = _dated_ortho(source, created.year)
    map_args = (results, plan.area, run["path"], plan.paths.runs, meta, plan.crs, plan.group_distance, p.group_by,
                ortho_cache, ortho_service, p.model, plan.rigging, on_lines, p.high_above)
    map_path = None
    # The line files of a large run are written by processes of their own (saving.py: one per file
    # with 4 or more threads of the line search, the results' apart from the map's with 2 or 3)
    children = (saving.plan(saving.processes(line_threads(p)), map_files=not p.no_html)
                if len(results) >= saving.MIN_LINES else [])
    if not children:
        progress.compute.start("saving results", len(results), unit="line")
        rn.save_results(run["path"], results, spot_groups, meta, on_lines)
        progress.compute.finish()
        saved()
        if not p.no_html:
            progress.compute.start("saving the map", len(results), unit="line")
            map_path = mp.save_map(*map_args)
            progress.compute.finish()
    else:
        heads = None if p.no_html else mp.map_heads(
            plan.area, os.path.join(run["path"], "map.html"), meta, plan.crs, plan.group_distance, p.group_by,
            ortho_cache, ortho_service, p.model, plan.rigging, p.high_above)

        def between():  # once the results' files are written, before the map's bar
            rn.save_results(run["path"], results, spot_groups, meta, files=("ATTRIBUTION.txt", "run.json"))
            saved()
        saving.save(plan.paths.work, run["path"], results, spot_groups, meta, heads, children, between)
        if not p.no_html:
            map_path = mp.save_map(*map_args, files=("map.html",))  # and the viewer installed
    if plan.index_runs:
        rn.write_index(plan.paths.runs, viewer=p.no_html)  # save_map installed the viewer already
    progress.set_step("")
    return Result(results, spot_groups, meta, run, map_path)


def _dated_ortho(source: src.Source, year: int) -> Optional[src.OrthoService]:
    """The orthophoto service of a run's map (None without one): its attribution may name the year
    of the run too (sources.YEAR)."""
    return source.ortho and dataclasses.replace(source.ortho, attribution=src.dated(source.ortho.attribution, year))


def _orthophoto(plan: Plan) -> bool:
    """Whether the run gets the orthophoto for offline use: a service, --ortho other than never, a map."""
    p = plan.params
    return bool(plan.source.ortho) and p.ortho != "never" and not p.no_html


def orthophoto_lines(plan: Plan, lines: Lines) -> List[Dict]:
    """The lines the orthophoto is cached around in detail (download_orthophoto): one per group
    (its variants lie within the strip), the best groups first, as many as --ortho-detail, the
    service's fair use (OrthoService.detail) or ORTHO_DETAIL for an area allow (a circle: every
    group). Their anchors only ("anchor1", "anchor2" as (lat, lon)): small enough to keep after
    the lines are released (the web worker downloads the orthophoto after "done")."""
    p, source = plan.params, plan.source
    detail = p.ortho_detail if p.ortho_detail is not None else (source.ortho.detail if source.ortho else None)
    if detail is None and not isinstance(plan.area, ar.Circle):
        detail = ORTHO_DETAIL
    columns = lines.results.columns
    reps = lines.spot_groups.rep[:detail]
    return [{"anchor1": tuple(a1), "anchor2": tuple(a2)}
            for a1, a2 in zip(columns["anchor1"][reps].tolist(), columns["anchor2"][reps].tolist())]


def download_orthophoto(plan: Plan, spots: List[Dict], confirm: Optional[Confirm] = None) -> int:
    """The orthophoto for offline use of the map, after the run is saved: the tiles of the search
    area at the overview zooms and of a strip around each line of `spots` (orthophoto_lines) at
    the detail zooms, those not cached yet (with --update: or due for a check), downloaded into
    the source's cache folder, which the map reads tile by tile (the rest it loads online).
    Nothing without an orthophoto service, with --ortho never or --no-html; with --ortho auto a
    download of more than CONFIRM_MINUTES asks confirm("ortho", ...), and no means none. Returns
    the tiles downloaded."""
    p, source, emit = plan.params, plan.source, plan.emit
    if not _orthophoto(plan):
        return 0
    confirm = confirm or (lambda kind, text: True)
    folder = ortho.cache_folder(plan.paths.cache, source.ortho)
    max_zoom = ortho.DETAIL_ZOOMS[-1] if source.ortho.url else source.ortho.base_max_zoom
    tiles = ortho.missing_tiles(ortho.tiles_to_cache(spots, plan.area, max_zoom), folder, plan.paths.cache,
                               p.update, source.ortho.ttl_days)
    minutes = len(tiles) * ORTHO_SECONDS_PER_TILE / 60
    emit("info", f"Orthophoto for offline use: {len(tiles)} tiles to download "
                 f"(~{len(tiles) * ortho.APPROX_TILE_KB / 1000:.0f} MB, ~{minutes:.0f} min)")
    if p.ortho == "auto" and minutes > CONFIRM_MINUTES and not confirm(
            "ortho", "Download now? Otherwise the map loads the orthophoto online. [y/N] "):
        return 0
    saved, received = ortho.download(source.ortho, tiles, folder, plan.paths.cache)
    if tiles:
        emit("info", f"Orthophoto for offline use: {saved} of {len(tiles)} tiles saved ({received / 1e6:.0f} MB)")
    return saved


_SAG_TABLES: Dict[tuple, "sg.EnvelopeTable"] = {}  # by (rigging, min_length, max_length); at most SAG_TABLES_MAX
SAG_TABLES_MAX = 16


def _sag_table(rigging: Tuple[float, ...], min_length: float, max_length: float) -> "sg.EnvelopeTable":
    """The envelope table of a rigging and the lengths of its lines, built once per process: the
    tiles of a sag area (2-3 s each before 2026-11-02), and profile_of_line's next profiles of the
    same run (at most SAG_TABLES_MAX tables, the oldest dropped)."""
    key = (tuple(rigging), min_length, max_length)
    table = _SAG_TABLES.get(key)
    if table is None:
        if len(_SAG_TABLES) >= SAG_TABLES_MAX:
            del _SAG_TABLES[next(iter(_SAG_TABLES))]
        table = _SAG_TABLES[key] = sg.EnvelopeTable(sg.Rigging(*rigging), min_length, max_length)
    return table


def profile_of_line(meta: Dict, paths: Paths, anchor1: Tuple[float, float], anchor2: Tuple[float, float]) -> Dict:
    """The profile of a line of a saved run (meta: its run.json), computed again from the cache.

    Maps of areas keep a profile only for the line shown for each group; this gives any
    other line its profile, and any two points measured on the map (at most MAX_MEASURED_PX
    pixels apart) theirs. A small grid around the line is built with the run's source,
    resolution and filling, on the same pixel grid as the search, so terrain and surface
    are the same; offsets of filled gaps may differ a little (they come from a smaller
    surrounding). anchor1, anchor2: (lat, lon) of the anchors as the run saved them.
    """
    p = meta["params"]
    values = _run_values(meta)
    to_xy = ar._to(meta["center"]["crs"])
    (x1, y1), (x2, y2) = to_xy(anchor1[1], anchor1[0]), to_xy(anchor2[1], anchor2[0])
    length = math.hypot(x2 - x1, y2 - y1)
    if length > MAX_MEASURED_PX * p["resolution"]:
        raise SearchError(f"the points are {length / 1000:.1f} km apart; at the {p['resolution']:g} m resolution "
                          f"of this run profiles reach {MAX_MEASURED_PX * p['resolution'] / 1000:g} km",
                          "profile_too_far", km=round(length / 1000, 1), max=MAX_MEASURED_PX * p["resolution"] / 1000)
    if length < 2 * p["resolution"]:
        raise SearchError("the points are too close", "profile_too_close")
    lat, lon = (anchor1[0] + anchor2[0]) / 2, (anchor1[1] + anchor2[1]) / 2
    values.update(lat=lat, lon=lon, radius=length / 2 + 10 * p["resolution"] + 20)
    plan = plan_search(SearchParams(**values), paths, lambda kind, text: None, with_margin=False)
    if plan.crs != meta["center"]["crs"]:
        raise SearchError(f"the run used {meta['center']['crs']}, a search here would use {plan.crs}", "profile_crs")
    plan.obstacles = p.get("obstacles")  # the run's rule; runs before it compared the surface model as it is
    data = prepare_data(plan, statistics=False, shore="none")
    grid, res = plan.grid, plan.resolution
    pixel = lambda x, y: (int(round((grid.top - y) / res - 0.5)), int(round((x - grid.left) / res - 0.5)))
    sag_table = None
    if p["model"] == "sag":
        # The same table as the search, so the same limits; a line measured on the map
        # may be shorter or longer than the search allowed: a table that reaches it
        spans = (min(p["min_length"], 0.99 * length), max(p["max_length"], 1.01 * length))
        if p["min_length"] <= length <= p["max_length"]:
            spans = (p["min_length"], p["max_length"])
        sag_table = _sag_table(dataclasses.astuple(plan.rigging), *spans)
    profile = sh.line_profile(pixel(x1, y1), pixel(x2, y2), data.elevation, res, data.surface,
                              sag_table=sag_table, water=data.water, filled=data.filled_pixels(),
                              end_zone=plan.end_zone, lift=plan.lift)  # the run's (0 and 0 before them)
    del data
    gc.collect()  # close the memory-mapped grids before the work folder is deleted (Windows)
    return profile


def _run_values(meta: Dict) -> Dict:
    """The parameters of a search on the run's source, resolution, filling and water settings
    (meta: its run.json), without the area: profile_of_line and patch_of_line."""
    p = meta["params"]
    values = {k: p[k] for k in ("resolution", "min_length", "max_length", "max_anchor_diff", "max_anchor_diff_m",
                                "slope_threshold", "water", "coastline", "shore_buffer", "fill_gaps", "model")}
    values.update(p["rigging"], nmpt=p["nmpt"] or "off", source=meta["source"]["id"], ortho="never", no_html=True)
    # the run's end zone and A-frames (Plan.end_zone, Plan.lift); a run saved without them: 0 and 0
    values.update(end_zone=p.get("end_zone", 0), anchor_lift=p.get("anchor_lift", 0))
    if values["source"] == "files":
        files = {d.get("layer"): d.get("file") for d in meta.get("data", [])}
        values.update(elevation_file=files.get("Terrain file"), surface_file=files.get("Surface file"))
    return values


def patch_of_line(meta: Dict, paths: Paths, anchor1: Tuple[float, float], anchor2: Tuple[float, float],
                  step: int = 1, side_m: Optional[float] = None) -> Tuple[Dict, bytes]:
    """The terrain of the 3D view around a line of a saved run (docs/3d-view-contract.md, "/api/patch"):
    (meta, the deflated heights). The run's source, resolution, filling and water settings (meta: its
    run.json), the surface model only for the shore faces the terrain lacks (no obstacle surface: the
    terrain is drawn), on a square of PATCH_BLOCK·n + 1 samples centred on the
    line's middle, its edges on the run's pixel edges, so the heights are those the search used.
    side_m: the metres it must span (default: PATCH_SIDE_MIN, or the line's length + PATCH_SIDE_MARGIN);
    step 2: every second sample of rows and columns. anchor1, anchor2: (lat, lon) as the run saved them.
    """
    from pyproj import Transformer
    if step not in (1, 2):
        raise ValueError("step: 1 or 2")
    p = meta["params"]
    values = _run_values(meta)  # the run's surface model too: the shore faces come from it (prepare_data)
    crs, res = meta["center"]["crs"], float(p["resolution"])
    to_xy = ar._to(crs)
    (x1, y1), (x2, y2) = to_xy(anchor1[1], anchor1[0]), to_xy(anchor2[1], anchor2[0])
    length = math.hypot(x2 - x1, y2 - y1)
    if side_m is None:
        side_m = max(PATCH_SIDE_MIN, length + PATCH_SIDE_MARGIN)
    size = PATCH_BLOCK * max(1, math.ceil(side_m / res / PATCH_BLOCK)) + 1
    if size > MAX_MEASURED_PX:
        raise SearchError(f"the 3D view of this line needs {side_m / 1000:.1f} km on a side; at the {res:g} m "
                          f"resolution of this run it shows at most {MAX_MEASURED_PX * res / 1000:g} km",
                          "patch_too_large", km=round(side_m / 1000, 1), max=MAX_MEASURED_PX * res / 1000)
    source, _ = src.choose_source(values["source"], anchor1[0], anchor1[1], paths.cache,
                                  values.get("elevation_file"), values.get("surface_file"))
    # The pixel holding the line's middle and half the samples on each side, on the run's pixel edges
    ox, oy = source.grid_origin
    half = size // 2
    left = ox + (math.floor(((x1 + x2) / 2 - ox) / res) - half) * res
    bottom = oy + (math.floor(((y1 + y2) / 2 - oy) / res) - half) * res
    right, top = left + size * res, bottom + size * res
    # The polygon a quarter of a pixel inside these edges: make_grid snaps it out onto them
    to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    inset = res / 4
    corners = [(left + inset, bottom + inset), (right - inset, bottom + inset), (right - inset, top - inset),
               (left + inset, top - inset)]
    ring = [list(to_lonlat(x, y)) for x, y in corners]
    values["geometry"] = {"type": "Polygon", "coordinates": [ring + [ring[0]]]}
    plan = plan_search(SearchParams(**values), paths, lambda kind, text: None, with_margin=False)
    if plan.crs != crs:
        raise SearchError(f"the run used {crs}, a search here would use {plan.crs}", "patch_crs")
    grid = plan.grid
    if (grid.width, grid.height) != (size, size) or abs(grid.left - left) > res / 100 or abs(grid.top - top) > res / 100:
        raise RuntimeError(f"the patch's grid ({grid.width} x {grid.height} at {grid.left}, {grid.top}) is not "
                           f"the square asked for ({size} x {size} at {left}, {top})")
    plan.obstacles = None  # the 3D view draws the terrain: no obstacle surface, the surface model fills the shore faces only
    data = prepare_data(plan, statistics=False, shore="kinds")  # the heights and the uncertain shore, no hypsometry
    anchors = []
    for x, y in ((x1, y1), (x2, y2)):
        row, col = int(round((grid.top - y) / res - 0.5)), int(round((x - grid.left) / res - 0.5))
        inside = 0 <= row < size and 0 <= col < size
        h = float(data.elevation[row, col]) if inside else math.nan
        anchors.append({"x": grid.left + (col + 0.5) * res, "y": grid.top - (row + 0.5) * res,
                        "h": round(h, 2) if math.isfinite(h) else None})
    heights = np.array(data.elevation[::step, ::step])  # a copy: the grids go with the work folder
    kinds = np.array(data.shore_kinds[::step, ::step]) if data.shore_kinds is not None else None
    del data
    gc.collect()  # close the memory-mapped grids before the work folder is deleted (Windows)
    body, base_dm = encode_heights(heights)
    shore = encode_shore(kinds) if kinds is not None else b""
    # The sampled grid's outer edges: sample (i, j) has its centre at left + (j + 0.5)·res·step
    sampled = res * step
    s_left, s_top = grid.left + res / 2 - sampled / 2, grid.top - res / 2 + sampled / 2
    # lon, lat as an affine function of the grid metres, fitted over a 5 x 5 lattice of the patch
    cx, cy = (grid.left + right) / 2, (bottom + grid.top) / 2
    xs, ys = (a.ravel() for a in np.meshgrid(np.linspace(left, right, 5), np.linspace(bottom, top, 5)))
    lon, lat = to_lonlat(xs, ys)
    design = np.column_stack([np.ones(xs.size), xs - cx, ys - cy])
    (a0, a1, a2), (b0, b1, b2) = (np.linalg.lstsq(design, np.asarray(v), rcond=None)[0] for v in (lon, lat))
    affine = [a0 - a1 * cx - a2 * cy, a1, a2, b0 - b1 * cx - b2 * cy, b1, b2]
    created = datetime.fromisoformat(meta["created"]).astimezone() if meta.get("created") else datetime.now()
    ortho_cache = ortho.cache_folder(paths.cache, source.ortho) if source.ortho else None
    patch = {
        "width": int(heights.shape[1]), "height": int(heights.shape[0]), "step": step, "res": sampled, "crs": plan.crs,
        "left": s_left, "top": s_top, "base_dm": base_dm, "anchors": anchors, "affine": [float(v) for v in affine],
        "rigging": dataclasses.asdict(plan.rigging), "model": p["model"],
        # the formula model's constants as data.js writes them (mapping.map_heads), for the page's profile chart
        "slope": sh.SLOPE, "leash_fall": sh.LEASH_FALL,
        **_end_keys(plan.end_zone, plan.lift),
        # the run has a surface model: the page may ask the block of trees and buildings (part "canopy")
        "surface": bool(plan.nmpt),
        # the run's grouping distance: the page groups the lines from a clicked point into spots as the result does
        "group_distance": p.get("group_distance") or plan.group_distance,
        # as the run's data.js (mapping.save_map), its cache seen from the run's map.html
        "ortho": mp.ortho_entry(_dated_ortho(source, created.year), ortho_cache,
                                os.path.join(paths.runs, meta["id"], "map.html")),
        "attribution": meta.get("attribution", []),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    if shore:
        # The uncertain shore's kinds after the heights (docs/3d-view-contract.md, "Body"): the page splits them off
        patch["shore_bytes"] = len(shore)
        patch["shore_sha256"] = hashlib.sha256(shore).hexdigest()
    return patch, body + shore


def _end_keys(end_zone: float, lift: float) -> Dict[str, float]:
    """The end zone and the A-frames as the heads of data.js and the patch meta name them (mapping.map_heads):
    "end_zone" and "lift", each only when not 0 (runs without them: the keys of before)."""
    return {**({"end_zone": end_zone} if end_zone else {}), **({"lift": lift} if lift else {})}


def encode_shore(kinds: np.ndarray) -> bytes:
    """The uncertain shore of the 3D view's patch (sources.filling.shore_rows on the patch's samples:
    0 none, 1 the face from the surface model, 2 the sea fill standing in for a cliff's foot), one
    byte a sample row-major from the top, deflated (zlib, as the heights); the page draws hatching
    there (viewer/src/view3d/shore.ts)."""
    import zlib
    return zlib.compress(np.ascontiguousarray(kinds, dtype=np.uint8).tobytes(), 6)


def encode_heights(heights: np.ndarray) -> Tuple[bytes, int]:
    """The body of the 3D view's heights (docs/3d-view-contract.md, "Body"; the reference is
    tests/data/make_patch_fixture.py encode): decimetres above base_dm as int16 (PATCH_NO_DATA
    without data), row by row from the top as horizontal deltas (int16 wrapping), little-endian,
    deflated in the zlib format. Returns (body, base_dm). SearchError patch_no_data without a
    finite height, patch_relief for a relief above 3276.7 m."""
    finite_min = np.nanmin(heights) if np.isfinite(heights).any() else math.nan
    if not math.isfinite(finite_min):
        raise SearchError("no elevation data around this line", "patch_no_data")
    base_dm = int(math.floor(float(finite_min) * 10))
    compressor = zlib.compressobj(6)
    parts = []
    for start in range(0, heights.shape[0], PATCH_ROWS):
        block = heights[start:start + PATCH_ROWS].astype(np.float64)
        finite = np.isfinite(block)
        values = np.full(block.shape, PATCH_NO_DATA, dtype=np.int64)
        values[finite] = np.rint(block[finite] * 10).astype(np.int64) - base_dm
        if finite.any() and values[finite].max() > 32767:
            raise SearchError("the relief around this line exceeds 3276.7 m", "patch_relief")
        values = values.astype(np.int16)
        deltas = values.copy()
        deltas[:, 1:] = values[:, 1:] - values[:, :-1]  # int16 arithmetic wraps, the decoder wraps back
        parts.append(compressor.compress(deltas.astype("<i2").tobytes()))
    parts.append(compressor.flush())
    return b"".join(parts), base_dm


def _patch_plan(meta: Dict, paths: Paths, anchor1: Tuple[float, float], anchor2: Tuple[float, float],
                side_m: Optional[float] = None):
    """The plan of the 3D view's patch of a line at step 1 (patch_of_line's square: PATCH_BLOCK·n + 1 samples
    centred on the line's middle, its edges on the run's pixel edges, the run's source, resolution, filling and
    water settings), for the other requests that name a patch (reach_of_anchor, canopy_of_line): (plan, source,
    the run's lon/lat -> x/y). Its obstacles are the plan's own (the caller sets the run's rule). SearchError
    patch_too_large, patch_crs."""
    from pyproj import Transformer
    values = _run_values(meta)
    crs, res = meta["center"]["crs"], float(meta["params"]["resolution"])
    to_xy = ar._to(crs)
    (x1, y1), (x2, y2) = to_xy(anchor1[1], anchor1[0]), to_xy(anchor2[1], anchor2[0])
    length = math.hypot(x2 - x1, y2 - y1)
    if side_m is None:
        side_m = max(PATCH_SIDE_MIN, length + PATCH_SIDE_MARGIN)
    size = PATCH_BLOCK * max(1, math.ceil(side_m / res / PATCH_BLOCK)) + 1
    if size > MAX_MEASURED_PX:
        raise SearchError(f"the 3D view of this line needs {side_m / 1000:.1f} km on a side; at the {res:g} m "
                          f"resolution of this run it shows at most {MAX_MEASURED_PX * res / 1000:g} km",
                          "patch_too_large", km=round(side_m / 1000, 1), max=MAX_MEASURED_PX * res / 1000)
    source, _ = src.choose_source(values["source"], anchor1[0], anchor1[1], paths.cache,
                                  values.get("elevation_file"), values.get("surface_file"))
    ox, oy = source.grid_origin
    half = size // 2
    left = ox + (math.floor(((x1 + x2) / 2 - ox) / res) - half) * res
    bottom = oy + (math.floor(((y1 + y2) / 2 - oy) / res) - half) * res
    right, top = left + size * res, bottom + size * res
    to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    inset = res / 4  # the polygon a quarter of a pixel inside these edges: make_grid snaps it out onto them
    corners = [(left + inset, bottom + inset), (right - inset, bottom + inset), (right - inset, top - inset),
               (left + inset, top - inset)]
    ring = [list(to_lonlat(x, y)) for x, y in corners]
    values["geometry"] = {"type": "Polygon", "coordinates": [ring + [ring[0]]]}
    plan = plan_search(SearchParams(**values), paths, lambda kind, text: None, with_margin=False)
    if plan.crs != crs:
        raise SearchError(f"the run used {crs}, a search here would use {plan.crs}", "patch_crs")
    grid = plan.grid
    if (grid.width, grid.height) != (size, size) or abs(grid.left - left) > res / 100 or abs(grid.top - top) > res / 100:
        raise RuntimeError(f"the patch's grid ({grid.width} x {grid.height} at {grid.left}, {grid.top}) is not "
                           f"the square asked for ({size} x {size} at {left}, {top})")
    return plan, source, to_xy


def _reach_candidates(z: np.ndarray, res: float, fixed: Tuple[int, int], lattice: int, min_length: float,
                      max_length: float, max_dh_ratio: float, max_dh: float):
    """The samples of the lattice (every `lattice`-th row and column from the first) a line from the fixed
    pixel may reach, REACH_ROWS lattice rows at a time, as (rows, columns) in the grid, row-major: the length
    and height tests of linesearch._pairs (min_length <= length <= max_length with length = hypot(dr, dc) · res;
    the float32 heights differ by at most min(max_dh_ratio · length, max_dh); a sample without data never
    passes)."""
    height, width = z.shape
    fixed_z = z[fixed[0], fixed[1]]
    reach = int(max_length / res) + 2
    end = min(height, fixed[0] + reach + 1)
    first = max(0, fixed[0] - reach)
    first -= first % lattice
    columns = np.arange(0, width, lattice)
    for r0 in range(first, end, lattice * REACH_ROWS):
        r1 = min(end, r0 + lattice * REACH_ROWS)
        rows = np.arange(r0, r1, lattice)
        length = np.hypot(rows[:, None] - fixed[0], columns[None, :] - fixed[1]) * res
        near = (length <= max_length) & (length >= min_length)
        with np.errstate(invalid="ignore"):  # NaN compares False
            difference = np.abs(np.asarray(z[r0:r1:lattice, ::lattice]) - fixed_z)
            near &= difference <= np.minimum(max_dh_ratio * length, max_dh)
        i, j = np.nonzero(near)
        yield rows[i], columns[j]


def _reach_lattice(z: np.ndarray, res: float, fixed: Tuple[int, int], limits: Dict) -> int:
    """1 while at most REACH_FULL_TARGETS samples of the grid are targets of the fixed pixel, else 2."""
    total = 0
    for rows, _ in _reach_candidates(z, res, fixed, 1, **limits):
        total += len(rows)
        if total > REACH_FULL_TARGETS:
            return 2
    return 1


def reach_of_anchor(meta: Dict, paths: Paths, anchor1: Tuple[float, float], anchor2: Tuple[float, float],
                    fixed: Tuple[float, float], which: int, side_m: Optional[float] = None) -> Tuple[Dict, bytes]:
    """Where the other anchor of a line of a saved run may stand, with one end fixed (the 3D view's "only valid
    lines", docs/3d-view-contract.md, "/api/reach"): (meta, the deflated values). The patch of the line
    (anchor1, anchor2: (lat, lon) as the run saved them) at step 1 with the run's obstacle rule (as
    profile_of_line), the fixed point (lat, lon) in its pixel, and each sample of a lattice within the run's
    limits of length and height difference evaluated as linesearch.evaluate_lines decides a line (helpers.
    evaluate_line, the run's sag model and surface mode, none of the search's anchor rules), in the order the
    page asks the profile: which = 1 the fixed point first, 2 the target first. One uint8 a sample of the
    lattice, row-major from the top: 0 not valid; else the low 7 bits min(127, ceil(clearance /
    REACH_QUANTUM)) (at least 1) and REACH_TREES when the line passes over trees or buildings. The meta's
    `res` is the run's resolution; value (i, j) is the patch's sample (i · lattice, j · lattice). Imports numba
    (the quick lane loads it at its first reach). SearchError reach_anchor for a point outside the patch or
    over no data."""
    if which not in (1, 2):
        raise ValueError("as: 1 or 2")
    p = meta["params"]
    plan, _, to_xy = _patch_plan(meta, paths, anchor1, anchor2, side_m)
    plan.obstacles = p.get("obstacles")  # the run's rule, as profile_of_line
    data = prepare_data(plan, statistics=False, shore="none")
    grid, res = plan.grid, plan.resolution
    limits = {"min_length": float(p["min_length"]), "max_length": float(p["max_length"]),
              "max_dh_ratio": float(p["max_anchor_diff"]) / 100, "max_dh": float(p["max_anchor_diff_m"])}
    try:
        z = np.asarray(data.elevation)
        s = np.asarray(data.surface) if data.surface is not None else None
        x, y = to_xy(fixed[1], fixed[0])
        row, col = int(round((grid.top - y) / res - 0.5)), int(round((x - grid.left) / res - 0.5))
        if not (0 <= row < z.shape[0] and 0 <= col < z.shape[1]) or not math.isfinite(float(z[row, col])):
            raise SearchError("the point is outside the terrain of the 3D view or has no elevation data",
                              "reach_anchor")
        sag_table = None
        if p["model"] == "sag":
            sag_table = _sag_table(dataclasses.astuple(plan.rigging), p["min_length"], p["max_length"])
        mask, lattice = _reach_mask(z, s, res, (row, col), which, limits, sag_table, plan.nmpt,
                                    plan.end_zone, plan.lift)  # the run's end zone and A-frames
        height_here = float(z[row, col])
    finally:
        z = s = data = None
        gc.collect()  # close the memory-mapped grids before the work folder is deleted (Windows)
    body = zlib.compress(np.ascontiguousarray(mask).tobytes(), 6)
    reach = {
        "width": int(mask.shape[1]), "height": int(mask.shape[0]), "lattice": lattice, "res": res,
        "left": grid.left, "top": grid.top,
        "anchor": {"x": grid.left + (col + 0.5) * res, "y": grid.top - (row + 0.5) * res, "h": round(height_here, 2)},
        "as": which, "min_length": limits["min_length"], "max_length": limits["max_length"],
        "valid": int(np.count_nonzero(mask)), "trees": int(np.count_nonzero(mask & REACH_TREES)),
        "quantum": REACH_QUANTUM, "sha256": hashlib.sha256(body).hexdigest(),
    }
    return reach, body


def _reach_mask(z: np.ndarray, s: Optional[np.ndarray], res: float, fixed: Tuple[int, int], which: int,
                limits: Dict, sag_table, nmpt_mode: Optional[str], end_zone: float = 0.0,
                lift: float = 0.0) -> Tuple[np.ndarray, int]:
    """(the lattice of reach_of_anchor's values, the lattice step) for a fixed pixel of the grids z (terrain)
    and s (the obstacle surface or None); end_zone, lift: the run's end zone and A-frames
    (helpers.end_zone_rule), as profile_of_line applies them."""
    import numba

    import linesearch as ls
    lattice = _reach_lattice(z, res, fixed, limits)
    columns = -(-z.shape[1] // lattice)
    mask = np.zeros((-(-z.shape[0] // lattice), columns), dtype=np.uint8)
    flat = mask.reshape(-1)  # a view
    threads = numba.get_num_threads()
    numba.set_num_threads(max(1, min(REACH_THREADS, numba.config.NUMBA_NUM_THREADS)))  # the quick lane's one process
    try:
        for block_rows, block_cols in _reach_candidates(z, res, fixed, lattice, **limits):
            for lo in range(0, len(block_rows), REACH_PART):
                rows, cols = block_rows[lo:lo + REACH_PART], block_cols[lo:lo + REACH_PART]
                n = len(rows)
                anchors = np.empty((n + 1, 2), dtype=np.int64)
                anchors[0] = fixed
                anchors[1:, 0], anchors[1:, 1] = rows, cols
                target, fixed_index = np.arange(1, n + 1), np.zeros(n, dtype=np.int64)
                found = np.column_stack([fixed_index, target] if which == 1 else [target, fixed_index])
                lines = ls.evaluate_lines(found, anchors, z, res, s, sag_table, nmpt_mode, down=np.zeros((n + 1, 2)),
                                          end_zone=end_zone, lift=lift)
                other = lines.columns["a2" if which == 1 else "a1"]  # the target's pixel
                with np.errstate(invalid="ignore"):
                    over = lines.columns["clearance_nmpt"] <= 0  # NaN: no surface there
                steps = np.clip(np.ceil(lines.columns["clearance"] / REACH_QUANTUM), 1, REACH_STEPS_MAX).astype(np.uint8)
                flat[(other[:, 0] // lattice) * columns + other[:, 1] // lattice] = steps | np.where(
                    over, REACH_TREES, 0).astype(np.uint8)
    finally:
        numba.set_num_threads(threads)
    return mask, lattice


def canopy_of_line(meta: Dict, paths: Paths, anchor1: Tuple[float, float], anchor2: Tuple[float, float],
                   step: int = 1, side_m: Optional[float] = None) -> Tuple[Dict, bytes]:
    """The trees and buildings of the 3D view around a line of a saved run (docs/3d-view-contract.md, "The
    block of trees and buildings"): (meta, the deflated values) on the grid of patch_of_line for that step.
    One uint8 a sample, row-major from the top: the run's obstacle surface (obstacles.obstacle_surface of its
    rule; the surface model as it is without one) less the terrain in steps of CANOPY_QUANTUM metres, 0 below
    CANOPY_MIN_HEIGHT, over no data and on bare pixels, at most 255. SearchError patch_no_surface for a run
    without a surface model."""
    if step not in (1, 2):
        raise ValueError("step: 1 or 2")
    plan, _, _ = _patch_plan(meta, paths, anchor1, anchor2, side_m)
    if not plan.nmpt:
        raise SearchError("this result has no surface model, so there are no trees or buildings to show",
                          "patch_no_surface")
    plan.obstacles = meta["params"].get("obstacles")  # the run's rule (None: the surface model as it is)
    data = prepare_data(plan, statistics=False, shore="none")
    try:
        if data.surface is None:
            raise SearchError("this result has no surface model, so there are no trees or buildings to show",
                              "patch_no_surface")
        terrain, surface = data.elevation[::step, ::step], data.surface[::step, ::step]
        values = np.zeros(terrain.shape, dtype=np.uint8)
        for r0 in range(0, values.shape[0], PATCH_ROWS):
            height = np.asarray(surface[r0:r0 + PATCH_ROWS], dtype=np.float64) \
                - np.asarray(terrain[r0:r0 + PATCH_ROWS], dtype=np.float64)
            with np.errstate(invalid="ignore"):  # NaN: no data, 0
                tall = height >= CANOPY_MIN_HEIGHT
            values[r0:r0 + PATCH_ROWS] = np.where(tall, np.minimum(np.rint(height / CANOPY_QUANTUM), 255), 0)
        terrain = surface = None
    finally:
        data = None
        gc.collect()  # close the memory-mapped grids before the work folder is deleted (Windows)
    grid, res = plan.grid, plan.resolution
    body = zlib.compress(np.ascontiguousarray(values).tobytes(), 6)
    sampled = res * step
    return {
        "part": "canopy", "width": int(values.shape[1]), "height": int(values.shape[0]), "step": step, "res": sampled,
        "left": grid.left + res / 2 - sampled / 2, "top": grid.top - res / 2 + sampled / 2,
        "quantum": CANOPY_QUANTUM, "min_height": CANOPY_MIN_HEIGHT, "rule": plan.obstacles,
        "cells": int(np.count_nonzero(values)), "sha256": hashlib.sha256(body).hexdigest(),
    }, body


def run_search(params: SearchParams, paths: Paths, on_event: Optional[OnEvent] = None,
               confirm: Optional[Confirm] = None) -> Result:
    """The whole search; confirm("expensive", reasons) is asked before downloading."""
    plan = plan_search(params, paths, on_event)
    estimate = estimate_search(plan)
    if estimate.reasons and confirm and not confirm("expensive", "\n".join(estimate.reasons)):
        raise SearchError("Stopped.")
    lines, run = search_lines(plan)
    result = save_run(plan, lines, run)
    download_orthophoto(plan, orthophoto_lines(plan, lines), confirm)
    return result
