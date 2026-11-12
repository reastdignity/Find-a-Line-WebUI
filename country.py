"""
The country layer's driver (docs/country-precompute/contract.md, section 3): a whole country
searched offline in fixed tiles that keep only counts (countcube.py), then summed into its cube.

    findaline.py country run <id> [--processes K] [--bands S,M,L1,L2] [--max-tiles N] [--redo] [--yes]
    findaline.py country status <id>
    findaline.py country profile <id>
    findaline.py country build <id> [--partial]
    findaline.py country compare <id> [--control C] [--against S]   (a country with a control band)
    findaline.py country worker <id> --slot K      (started by run, one per process)

Lines are searched in length bands (Band), each on its own grid and in its own fixed tiles
(search.fixed_tiles): a tile's plan is its band's (search.plan_search(tiled=False) of the
country's outline) on the tile's grid, step 1 as a search's (search.prepare_data), steps 2 and 3
in count mode (search.count_tile) into a countcube.TileCounter, the counts saved per tile
(countcube.save_tile). A tile is the unit of work and of resuming: the manifest (manifest.sqlite,
one row per band and tile) says which are pending, running, done or failed; `run` starts worker
processes that claim tiles from it one at a time, so an interrupted run goes on where it stopped,
and the results never depend on the number of processes or on resuming.

Data (all under <data>/countries/<id>/, nothing else of the data folder changes but the cache and
the tiles' work folders <data>/work/country-<id>/<band>-<name>/):
    country.json   the configuration (Country as JSON), the sha256 of the outline and of both
                   (the config hash every tile file records), the CRS and the cube's origin
    area.geojson   the outline (WGS84), fetched once (osm:<name> through Nominatim)
    neighbours.geojson  the declared neighbours' territories near the outline (WGS84), fetched once
                   (ensure_neighbours): which one a pixel beyond the outline lies in names the partner of a
                   line across the border; its sha256 in every border tile's meta and in cube.json
    manifest.sqlite  the tiles (schema v2, cache.migrate; WAL, claims in BEGIN IMMEDIATE, the
                   heaviest first: their weight from the lines of the tiles done already, or from
                   the relief of Copernicus GLO-30 while a tile lies under none)
    run.lock       held by `run` (one run at a time; workers stop when it is free)
    logs/          run.log, worker-<k>.log, samples-<start>.csv (a run's timeline)
    tiles/<band>/<name>.npz   the counts of a tile (countcube.VERSION)
    cube/          the cube (countcube.build) and a copy of area.geojson
    compare.json   `compare`'s result
"""

import argparse
import dataclasses
import functools
import gc
import glob
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import psutil

import cache
import countcube

REPO = os.path.dirname(os.path.abspath(__file__))
PROGRESS_SECONDS = 30      # between the progress lines of a run
WORKER_PROGRESS_SECONDS = 600  # between the text progress lines of a worker's bars (its log)
ATTEMPTS = 2               # a tile that fails goes back to pending once, then stays failed
# The memory of a counting worker: WORKER_BASE plus COUNT_PIXEL_BYTES per pixel of its tile's grid.
# Measured on Slovakia's M2 band (2026-11-04, docs/performance.md "Round 4", stage 2): with step 1
# in strips (TileWork.count: prepare_data(strips=True)) and OpenBLAS on one thread (_worker_env) a
# worker's private bytes stand at 0.17 GiB before a tile and rise at most 0.87 GiB during one (the
# Tatras tile of 474 M lines at 24 threads: 16 B/px of its 53 Mpx, in the pair search; a tile of
# 61 M lines alone 0.54 GiB, 11 B/px, at the prominence and drop), the memory-mapped grids outside
# (file-backed, about 20 B/px in the working set, about 40 since a worker keeps their views, which
# count the same pages twice: TileWork._remove_grids); 32 B/px is twice that largest rise, and the
# prominence and drop inside the pair search (search._anchors(deferred=True)) keep a tile's private
# bytes under the budget (at most 1.15 GiB in M2, 1.23 in S, 2026-11-05). Before the
# strips a tile's gap filling peaked at 45-94 B/px, and every worker's private bytes also held about
# 1.5 GiB that OpenBLAS reserved and never touched (_worker_env). Not search.memory_needed: a count
# holds no table of lines, no profiles and no step 4, and that model follows the app's.
# With a surface model COUNT_SURFACE_PIXEL_BYTES instead (wave 19, 2026-11-12, from the meta of every tile of
# Slovakia's two profiles of round 5, all counted with the surface model marking and the no-fall zone of 5 m with
# A-frames of 2 m: local/country-perf-2026-11-07/stage3/P/results.md, A3): a tile's private peak lies in steps 2-3
# and follows its anchors, not its pixels (Spearman 0.62-0.76 with the anchors among a band's tenth of most, -0.12
# to -0.05 with the pixels over a band: its tiles have nearly one grid size), about 0.4 GiB and 350-1050 B per anchor
# at the heaviest; step 1 stays under 0.71 GiB (11-27 B/px with the worker's base). At 32 B/px four tiles were over:
# the user profile's S tile of the Tatras held 2.92 GiB against 2.22 (5.5 M anchors, 3.3 G lines), the lead
# profile's L1 tile 1.38 against 1.21 and its S tile 1.72 against 1.65; the steepest tile per band
# needs at most 45 B/px over WORKER_BASE (the user's S; the lead's L1 40, S 34, M 25, L2 24), so 48 keeps every
# measured tile under its budget. The share of steep pixels of a country's steepest tile sets that figure (about a
# tenth at 1 m in the Tatras): a steeper country may need more. Without a surface model no tile of these runs was
# measured: 32 stays.
COUNT_PIXEL_BYTES = 32
COUNT_SURFACE_PIXEL_BYTES = 48
WORKER_BASE = 512 << 20
RETHREAD_SECONDS = 10      # between the looks of a counting tile at the workers still busy (_Rethreading)
# A tile is heavy when its weight (_weights: the lines of the done tiles under its core) reaches
# HEAVY_SHARE of the largest weight of the run's tiles: its count is a long pair search, which takes
# every thread it gets, while a light tile spends its seconds in steps 1-2 on one core and in a short
# pair search. The heavy tiles share the logical cores left after LIGHT_CORES per light tile running,
# and a light tile keeps at most LIGHT_THREADS while a heavy one runs (_threads). Measured on
# Slovakia's M2 band (2026-11-04): 7 workers at 3 threads each left 7-9 of 24 logical cores idle
# through the run, and its heaviest tile (47 min) was the run's length. One core per light tile, not
# the two (a physical core) of before (2026-11-05, docs/performance.md "Round 4", W1): a light tile's
# worker used 1.2-1.4 logical cores on average, and with 12 workers on 12 physical cores two per
# light tile left the three heavy M2 tiles 2 threads each (1.8 cores, the heaviest at 16 M pairs a
# minute) until the light part ended at +15 min; with one they get 5-7 threads (3.4-6.6 cores, 29-69
# M pairs a minute) and the band took 32.5 and 32.7 min instead of 34.4 and 34.3, the L band 17.8
# instead of 18.3. None (the heavy tiles share every core, the light ones run on top): M2 32.8, the
# light tiles slower. The machine stood at 92-99 % in every run: the split moves the heavy tiles'
# work from the run's tail, where a tile's pair search on 24 threads checks 6 M pairs per core and
# minute, into the light part, where it checks 9-11. Measured on one country and one computer: how
# to fit the split and the workers to another is in that section of docs/performance.md.
HEAVY_SHARE = 0.05
LIGHT_CORES = 1
LIGHT_THREADS = 3
# The weights of a run whose tiles lie under no done tile (a new country's first run: _weights knows
# nothing yet) come from the relief (_relief_weights): RELIEF_LINES times the km² of slopes of
# RELIEF_DEGREES or more at 30 m in a tile's core (Copernicus GLO-30 in blocks of about 1 km,
# relief.steep_blocks) to the power RELIEF_EXPONENT, about the tile's lines. Measured on Slovakia's
# done tiles (2026-11-04, docs/performance.md "Round 4", stage 3's A3): that km² ranks each band's
# tiles by their lines as well as the lines of the other three bands do (Spearman 0.55, 0.75, 0.90,
# 0.74 in S, M, L, M2; the 5 tiles of most lines among its first 5: 4, 4, 5, 4), the exponent a fit
# of log lines on log km² over M's, L's and M2's tiles with lines (1.64), the factor the median at
# that exponent over their tiles of at least a million lines (6.8e6). The exponent alone decides which
# tiles are heavy (HEAVY_SHARE of the largest weight: a km² at least 0.16 of the largest), the km²
# alone the order of the claims. Slopes of 30° instead, the constants fitted again (2026-11-05): the
# same wall on a first run of M + L (29.2 min, 31.9 without weights), a worse ranking and 60 of its
# tiles heavy instead of 8.
RELIEF_DEGREES = 45
RELIEF_LINES = 7e6
RELIEF_EXPONENT = 1.65
TILE_SAMPLE_SECONDS = 0.5  # between the samples of a counting worker's memory (_MemorySampler)
RUN_SAMPLE_SECONDS = 5     # between the rows of a run's timeline (_RunSamples: logs/samples-<start>.csv)
# A tile's grids in its work folder: search.work_bytes of the band's plan (the float32 terrain, surface
# and gap fillers, the masks) plus search.AREA_TEMP_BYTES of step 1's temporaries in strips (_disk_bytes)
DISK_SPARE = 1 << 30       # free disk kept besides the work folders
# The prefetch reads the blocks of big remote files (sources/readers/windows.py) in squares of this many metres,
# each file once per square (sources.download_layers(group_m=)). 10 km (the user, 2026-11-04): the tiles at a
# square's edges read twice add 11 % to the files' bytes (5 km: 22 %, blocks of 1 km: 128 %), and a square of 1 m
# data takes about 0.9 GB (its window, the window's mask and the blocks: 9 bytes a pixel), about 10.5 GB with the
# pool's 8 threads and GDAL's block cache (measured; docs/performance.md, "Window reads"). Sized for 1 m data:
# tools/area_download.py scales it by the layers' native resolution (5 km for 0.5 m files), so a group holds the
# same pixels; a group's window is read on the files' own pixels, whatever the grid's resolution
PREFETCH_GROUP_M = 10000
RESPAWNS_PER_WORKER = 2    # workers that stopped abnormally are started again at most this often (on average)
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
OVERLAP_KM2 = 0.01         # two outlines overlapping by less only share a border (_say_overlaps)


@dataclass(frozen=True)
class Band:
    """A length band of a country: its lines searched on its own grid in its own fixed tiles."""
    name: str
    lengths: Tuple[float, float]  # [lo, hi): searched with min_length lo and max_length hi
    resolution: float
    model: str                    # "formula" or "sag" (T(L): Country.tension)
    slope_threshold: float
    core_m: float                 # the side of a tile's core
    layer: bool                   # in the cube; False: a control band (country compare)


@dataclass(frozen=True)
class Profile:
    """The layer's profile (docs/country-precompute/contract.md section 6, "The profile (R7)"): the bands,
    T(L) and the rig, one for every country, so that two countries' cubes count the same lines and add up
    (PROFILE); a study area (tools/band_study.py) or a test may have its own. Its sha256 (of config()) is
    cube.json's "profile" and part of every tile's config hash."""
    bands: Tuple[Band, ...]
    tension: Tuple[Tuple[float, float], ...]  # T(L): (span m, pretension kN), sag.tension_at
    rig: Dict[str, float]                     # SearchParams' fields of every band's search: the webbing's

    def config(self) -> Dict:
        return json.loads(json.dumps({"bands": [dataclasses.asdict(b) for b in self.bands],
                                      "tension": [list(p) for p in self.tension], "rig": dict(self.rig)}))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.config(), sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def from_config(cls, config: Dict) -> "Profile":
        """The profile of a country's configuration: its bands, tension and rig, PROFILE's where it has none."""
        bands = (tuple(Band(**{**b, "lengths": tuple(b["lengths"])}) for b in config["bands"])
                 if "bands" in config else PROFILE.bands)
        tension = tuple(tuple(p) for p in config["tension"]) if "tension" in config else PROFILE.tension
        rig = dict(config.get("rig") or {}) if "rig" in config else dict(PROFILE.rig)
        return cls(bands, tension, rig)


# The profile of every country, chosen by the user on 2026-11-12 (round 5's wave 17: two profiles counted on all
# of Slovakia and compared; the tables go into docs/performance.md, "Round 5 (2026-11-07/08): the country layer,
# continued", section "The recount: two profiles of Slovakia", written at the round's closing; until then
# local/country-perf-2026-11-07/stage3/R2/results.md): four bands, all in the layer, no control band, every one with the
# sag model; T(L) and Silk 99 (the other rigging fields at their defaults) as the pilot's. Against the profile of
# a 1 m band up to 1000 m it found 1.5 times the spots of 2-5 km and the same of 1-2 km, a third of those of
# 300-1000 m, at about a twelfth of the pair searches' CPU hours (18.7 against 228.8). A change of the profile is a
# change of this value, and every country is counted again (the config hash)
PROFILE = Profile(
    bands=(Band("S", (30, 300), 1.0, "sag", 60, 5000, True),
           Band("M", (300, 1000), 2.0, "sag", 60, 10000, True),
           Band("L1", (1000, 2000), 3.0, "sag", 55, 10000, True),
           Band("L2", (2000, 5000), 5.0, "sag", 45, 20000, True)),
    tension=((300, 2.5), (1500, 6.0), (5000, 15.0)),
    rig={"webbing_weight": 41.0, "stretch": 2.1})


@dataclass(frozen=True)
class Country:
    id: str
    name: str
    source: str
    area: str                     # an area spec of area.from_spec, e.g. "osm:Slovensko"
    bands: Tuple[Band, ...] = PROFILE.bands  # the profile's (PROFILE) unless a study area (or a test) has its own
    tension: Tuple[Tuple[float, float], ...] = PROFILE.tension  # T(L): (span m, pretension kN), sag.tension_at
    rig: Dict[str, float] = field(default_factory=lambda: dict(PROFILE.rig))  # SearchParams' webbing fields
    # nmpt, water, coastline, fill_gaps; end_zone, anchor_lift (metres, numbers: every band's search takes
    # them, form_params); within: a box S,W,N,E clipping the area (tools/band_study.py's squares);
    # elevation_file, surface_file: tests
    options: Dict[str, object] = field(default_factory=dict)

    def config(self) -> Dict:
        """The configuration as JSON values (country.json), the profile's bands, tension and rig with it."""
        return json.loads(json.dumps(dataclasses.asdict(self)))

    @classmethod
    def from_config(cls, config: Dict) -> "Country":
        profile = Profile.from_config(config)
        return cls(config["id"], config["name"], config["source"], config["area"], profile.bands, profile.tension,
                   profile.rig, dict(config.get("options") or {}))

    @property
    def profile(self) -> Profile:
        return Profile(self.bands, self.tension, self.rig)

    def band(self, name: str) -> Band:
        for band in self.bands:
            if band.name == name:
                return band
        raise CountryError(f"{self.id} has no band {name} (its bands: {', '.join(b.name for b in self.bands)})")

    @property
    def last_edge(self) -> float:
        return float(countcube.LENGTH_EDGES[-1])

    @property
    def study(self) -> bool:
        """A study area: a box of a country (the option "within"), not a country of the layer."""
        return bool(self.options.get("within"))


COUNTRIES = {
    "slovakia": Country(
        id="slovakia", name="Slovakia", source="slovakia", area="osm:Slovensko",
        # The recount (the user's decisions of 2026-11-07/08): the surface model marks the lines over trees and
        # buildings (the pilot of 2026-11-02 ran without it), and the no-fall zone of 5 m with A-frames of 2 m,
        # the superset a search with smaller ones filters (Country.options, form_params)
        options={"nmpt": "mark", "water": "fill", "coastline": "copernicus", "fill_gaps": "on",
                 "end_zone": 5, "anchor_lift": 2}),
}

# The cube of each source the catalogue names as some source's neighbour (Source.neighbours): the id of the
# layer counted from its data (a country's, or a region's where the catalogue's source is a region's). A
# country's cube.json lists its source's neighbours' cube ids in their order ("neighbours"), the partner
# index 1-6 of a line across its border (no source declares more than six); such a line is counted from this
# country's data until the neighbour has a cube of its own (docs/country-precompute/contract.md section 6)
NEIGHBOUR_CUBES = {
    "alaska": "alaska", "alaska_ifsar": "alaska", "austria": "austria", "baden_wurttemberg": "baden_wurttemberg",
    "bavaria": "bavaria", "brandenburg": "brandenburg", "british_columbia": "british_columbia", "canada": "canada",
    "czechia": "czechia", "denmark": "denmark", "england": "england", "finland": "finland", "france": "france",
    "geoportal": "poland", "hesse": "hesse", "lower_saxony": "lower_saxony", "luxembourg": "luxembourg",
    "mecklenburg_vorpommern": "mecklenburg_vorpommern", "north_rhine_westphalia": "north_rhine_westphalia",
    "norway": "norway", "nunavut": "nunavut", "rhineland_palatinate": "rhineland_palatinate", "saarland": "saarland",
    "saxony": "saxony", "saxony_anhalt": "saxony_anhalt", "schleswig_holstein": "schleswig_holstein",
    "scotland": "scotland", "slovakia": "slovakia", "slovenia": "slovenia", "south_tyrol": "south_tyrol",
    "spain": "spain", "swisstopo": "switzerland", "trento": "trento", "usa": "usa", "wales": "wales"}


def neighbour_cubes(source_id: str) -> List[str]:
    """The cube ids of a source's neighbours in the order of Source.neighbours (cube.json's "neighbours": a
    line's partner index k is the k-th); [] for a source outside the catalogue (an elevation file)."""
    import sources as src
    source = src.SOURCES.get(source_id)
    return [NEIGHBOUR_CUBES[n] for n in (source.neighbours or ())] if source is not None else []


# The declared neighbours' territories (docs/country-precompute/contract.md section 6, "The borders"): which one a
# partner pixel lies in names the partner of a line across the border (sources.filling.resolve_partners). Fetched
# once per country folder at `run`'s set-up, as area.geojson is, and kept clipped to what the tiles can reach
NEIGHBOURS_FILE = "neighbours.geojson"
TERRITORY_MARGIN_M = 1000.0  # beyond the farthest partner pixel a band's zone can hold (territory_reach)


def territory_specs(cube_id: str) -> List[str]:
    """The area specs (osm:<name>) of a neighbour's territory: the outline its own cube would be cut by, made of
    the map areas (Source.map_areas, named by sources.AREA_NAMES) of every catalogue source whose cube
    (NEIGHBOUR_CUBES) is cube_id, each once, in the catalogue's order: brandenburg Brandenburg and Berlin, usa the
    United States, Puerto Rico and the U.S. Virgin Islands, alaska Alaska (also for alaska_ifsar, which has no
    areas of its own). [] for a cube no source names."""
    import sources as src
    specs: List[str] = []
    for source in src.SOURCES.values():
        if NEIGHBOUR_CUBES.get(source.id) == cube_id:
            for area in source.map_areas():
                spec = f"osm:{src.AREA_NAMES[area]}"
                if spec not in specs:
                    specs.append(spec)
    return specs


def territory_reach(bands: Sequence[Band]) -> float:
    """How far beyond the outline the territories are kept (neighbours.geojson's "reach_m"): the farthest a
    partner pixel's centre may lie from it in any band, plus TERRITORY_MARGIN_M. A tile's partner zone
    (sources.filling.partner_zone, Plan.partners = the band's longest line L) is near()'s square of ceil(L / res)
    pixels around the outline's pixels, whose centres lie inside it: its corner lies sqrt(2) times that away."""
    return max(math.sqrt(2) * math.ceil(b.lengths[1] / b.resolution) * b.resolution for b in bands) \
        + TERRITORY_MARGIN_M


def _neighbour_outline(spec: str, cache_dir: str):
    """The outline (WGS84) of an area spec as a country's own is fetched (area.from_spec(whole=True): never
    simplified, Nominatim's answer cached in the data folder's cache)."""
    import area as ar
    return ar.from_spec(spec, 0.0, None, cache_dir, whole=True).geometry


def write_neighbours(country: Country, folder: str, cache_dir: str, crs: str, reach: float, say=print,
                     outline_of: Optional[Callable] = None) -> str:
    """neighbours.geojson of a country (not a study area): a FeatureCollection in WGS84 with the country's id,
    source, CRS and "reach_m", and a feature per declared neighbour (Source.neighbours, in their order) with its
    partner index (n + 1), source, cube (NEIGHBOUR_CUBES), area specs (territory_specs), the km² of its whole
    outline on the ellipsoid (resolve_partners: of two territories holding a pixel the smaller wins) and its
    geometry: the territory within `reach` of the country's outline (area.geojson grown in its CRS and taken back
    to WGS84), null when none of it lies there. The territory is cut there by GEOS in WGS84, which keeps the
    vertices of the border it shares with the country's outline as they are: the tiles project both alike
    (area.project) and burn both by the pixels' centres, so the border leaves no sliver to neither. A source
    outside the catalogue (an elevation file): no features. An outline that cannot be fetched stops with a
    CountryError naming the neighbour, before anything is written. outline_of(spec, cache_dir): the outline of a
    spec (_neighbour_outline). Returns the path."""
    import pyproj
    import area as ar
    import sources as src
    from shapely.geometry import mapping
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    outline_of = outline_of or _neighbour_outline
    source = src.SOURCES.get(country.source)
    names = list(source.neighbours or ()) if source is not None else []
    clip = None
    if names:
        clip = ar.project(ar.project(_read_outline(folder), "EPSG:4326", crs).buffer(reach), crs, "EPSG:4326")
    geod = pyproj.Geod(ellps="WGS84")
    fetched: Dict[str, object] = {}
    features = []
    for k, name in enumerate(names, 1):
        neighbour, cube = src.SOURCES[name], NEIGHBOUR_CUBES[name]
        specs = territory_specs(cube)
        if not specs:
            raise CountryError(f"No territory is known for {neighbour.name} (cube {cube}, partner {k}): its source "
                               f"has no area of the coverage map")
        parts = []
        for spec in specs:
            if spec not in fetched:
                say(f"Territory of {neighbour.name} (partner {k}): {spec}")
                try:
                    fetched[spec] = outline_of(spec, cache_dir)
                except Exception as e:  # Nominatim down, no such name, no network: never 7 everywhere by accident
                    raise CountryError(f"The outline of {neighbour.name} ({spec}, the territory of partner {k}) could "
                                       f"not be fetched: {cache.clean_error(e)}. Nothing was counted: run again "
                                       f"when it can be") from e
            parts.append(fetched[spec])
        whole = parts[0] if len(parts) == 1 else unary_union(parts)
        whole = whole if whole.is_valid else make_valid(whole)
        km2 = abs(geod.geometry_area_perimeter(whole)[0]) / 1e6
        near = whole.intersection(clip)
        features.append({"type": "Feature",
                         "properties": {"index": k, "source": name, "cube": cube, "areas": specs, "km2": round(km2, 3)},
                         "geometry": None if near.is_empty else mapping(near)})
    path = os.path.join(folder, NEIGHBOURS_FILE)
    _write_json(path, {"type": "FeatureCollection", "country": country.id, "source": country.source, "crs": crs,
                       "reach_m": reach, "features": features})
    return path


def _neighbours_fit(collection: Dict, country: Country, crs: str, reach: float) -> bool:
    """Whether a neighbours.geojson serves the country as it is configured: its id, source and CRS, a feature per
    declared neighbour in their order, kept at least `reach` beyond the outline."""
    import sources as src
    source = src.SOURCES.get(country.source)
    names = list(source.neighbours or ()) if source is not None else []
    try:
        return (collection.get("country") == country.id and collection.get("source") == country.source
                and collection.get("crs") == crs and float(collection.get("reach_m", 0.0)) >= reach - 1e-6
                and [(f["properties"]["index"], f["properties"]["source"]) for f in collection.get("features", [])]
                == list(enumerate(names, 1)))
    except (AttributeError, KeyError, TypeError, ValueError):  # not such a file
        return False


def ensure_neighbours(country: Country, folder: str, cache_dir: str, crs: str, say=print) -> Optional[str]:
    """`run`'s set-up: the sha256 of neighbours.geojson, written first when it is missing or does not serve the
    country (_neighbours_fit: another source, CRS or list of neighbours, a reach too short for the bands); a file
    that serves it is used as it is and nothing is fetched. None for a study area (no partners, no file)."""
    if country.study:
        return None
    path = os.path.join(folder, NEIGHBOURS_FILE)
    reach = territory_reach(country.bands)
    collection = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                collection = json.load(f)
        except ValueError:  # cut short: written again
            collection = {}
    if collection is None or not _neighbours_fit(collection, country, crs, reach):
        say(f"The neighbours' territories of {country.name} within {reach / 1000:.1f} km of its outline "
            f"({NEIGHBOURS_FILE}" + (", written again: it no longer fits the configuration)" if collection else ")"))
        write_neighbours(country, folder, cache_dir, crs, reach, say)
    return _sha256_file(path)


def load_territories(folder: str, crs: str) -> Tuple[str, List]:
    """The sha256 of neighbours.geojson and its territories (sources.filling.Territory) in the CRS of the tiles'
    grids, projected as the area mask projects the outline (area.project, vertex by vertex): once per worker
    process (TileWork), never per tile. CountryError when the file is missing."""
    import area as ar
    from shapely.geometry import shape
    from sources.filling import Territory
    path = os.path.join(folder, NEIGHBOURS_FILE)
    if not os.path.exists(path):
        raise CountryError(f"{folder} has no {NEIGHBOURS_FILE} (the neighbours' territories, which name the partner "
                           f"of a line across the border): `findaline.py country run` writes it before its workers")
    with open(path, encoding="utf-8") as f:
        collection = json.load(f)
    territories = []
    for feature in collection["features"]:
        geometry = feature["geometry"]
        territories.append(Territory(int(feature["properties"]["index"]), float(feature["properties"]["km2"]),
                                     None if geometry is None else ar.project(shape(geometry), "EPSG:4326", crs)))
    return _sha256_file(path), territories


class CountryError(Exception):
    """A command cannot go on; the message is meant for the user."""


# --- country.json, the outline -------------------------------------------------------------------

def folder_of(data_dir: str, country_id: str) -> str:
    if not ID_PATTERN.match(country_id):
        raise CountryError(f"{country_id!r} is not a country id (lower case letters, digits, - and _)")
    return os.path.join(data_dir, "countries", country_id)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def config_hash(config: Dict, area_sha256: str) -> str:
    """What every tile file records (meta "config"): the configuration, its profile's sha256 (Profile:
    cube.json's "profile") and the outline, and with the surface model the obstacle rule (obstacles.RULE:
    tiles of another rule are counted again)."""
    value = {"config": config, "profile": Profile.from_config(config).sha256, "area_sha256": area_sha256}
    if (config.get("options") or {}).get("nmpt", "off") != "off":
        import obstacles
        value["obstacles"] = obstacles.RULE
    text = json.dumps(value, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_state(folder: str) -> Dict:
    """country.json."""
    path = os.path.join(folder, "country.json")
    if not os.path.exists(path):
        raise CountryError(f"{folder} has no country.json: start with `findaline.py country run <id>`")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, value: Dict):
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)


def _read_outline(folder: str):
    """The outline of an area.geojson (WGS84)."""
    from shapely.geometry import shape
    from shapely.validation import make_valid
    with open(os.path.join(folder, "area.geojson"), encoding="utf-8") as f:
        outline = shape(json.load(f)["geometry"])
    return outline if outline.is_valid else make_valid(outline)


def _other_areas(data_dir: str, country_id: str) -> List[Tuple[str, bool, object]]:
    """The other areas set up in the data folder: (id, a study area (Country.study), its outline)."""
    root = os.path.join(data_dir, "countries")
    found = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else ():
        folder = os.path.join(root, name)
        if name != country_id and os.path.exists(os.path.join(folder, "area.geojson")) \
                and os.path.exists(os.path.join(folder, "country.json")):
            options = read_state(folder).get("config", {}).get("options") or {}
            found.append((name, bool(options.get("within")), _read_outline(folder)))
    return found


def _partition(country: Country, outline, data_dir: str, say) -> Tuple[object, List[str]]:
    """The outline less the countries set up before it, and their ids: a point of the map is one
    country's, the first to hold it. Outlines of one OSM share their borders exactly, so nothing is
    cut between them; an outline of another date or a hand-made one loses what it lays over a
    neighbour. Gaps between outlines stay, and a study area keeps its outline (Country.study)."""
    import area as ar
    less = []
    for other, study, taken in _other_areas(data_dir, country.id):
        if study or not outline.intersects(taken):
            continue
        overlap = outline.intersection(taken)
        if overlap.area <= 0:  # a shared border
            continue
        say(f"Outline of {country.name}: {ar.size_km2(overlap):,.2f} km² belong to {other}, set up before it")
        outline = outline.difference(taken)
        less.append(other)
    if outline.is_empty:
        raise CountryError(f"{country.id} lies inside {', '.join(less)}: an area of a country counted already is a "
                           f"study area (the option \"within\")")
    return outline, less


def _write_outline(country: Country, folder: str, data_dir: str, say=print):
    """area.geojson: the outline of the country's area spec (clipped to the box of its option
    "within", if any), never simplified and less the countries set up before it (_partition),
    in WGS84."""
    import area as ar
    from shapely.geometry import mapping
    from shapely.validation import make_valid
    outline = ar.from_spec(country.area, 0.0, country.options.get("within"), os.path.join(data_dir, "cache"),
                           whole=True).geometry
    properties = {"id": country.id, "name": country.name, "area": country.area}
    if not country.study:
        outline, less = _partition(country, outline if outline.is_valid else make_valid(outline), data_dir, say)
        if less:
            properties["less"] = less
    feature = {"type": "Feature", "properties": properties, "geometry": mapping(outline)}
    _write_json(os.path.join(folder, "area.geojson"), feature)


def _say_overlaps(country: Country, folder: str, data_dir: str, say):
    """`country run`: the other areas this outline overlaps by OVERLAP_KM2 or more. A study area lies
    in its country by design and the layer shows it alone; two countries would count the part twice
    (only outlines set up before _partition can)."""
    import area as ar
    outline = _read_outline(folder)
    for other, study, taken in _other_areas(data_dir, country.id):
        km2 = ar.size_km2(outline.intersection(taken)) if outline.intersects(taken) else 0.0
        if km2 >= OVERLAP_KM2 and (study or country.study):
            say(f"{country.id} and {other} overlap by {km2:,.1f} km²: the layer shows a study area alone, never "
                f"added to a country")
        elif km2 >= OVERLAP_KM2:
            say(f"WARNING: {country.id} and {other} overlap by {km2:,.1f} km²: the layer counts that part twice")


def _remove_results(folder: str):
    """--redo: the tiles, the cube, the manifest and the comparison."""
    for name in ("tiles", "cube"):
        shutil.rmtree(os.path.join(folder, name), ignore_errors=True)
    for name in ("manifest.sqlite", "manifest.sqlite-wal", "manifest.sqlite-shm", "compare.json"):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            os.remove(path)


def setup(country_id: str, folder: str, data_dir: str, redo: bool, say) -> Tuple[Dict, Country]:
    """country.json (written the first time, from COUNTRIES or a country.json holding only "config"),
    and area.geojson (fetched once). A configuration or outline other than the tiles' is refused
    unless redo, which removes the tiles, the cube and the manifest."""
    path = os.path.join(folder, "country.json")
    state = read_state(folder) if os.path.exists(path) else {}
    if country_id in COUNTRIES:
        config = COUNTRIES[country_id].config()
    elif "config" in state:
        config = state["config"]
    else:
        raise CountryError(f"Unknown country {country_id!r}: one of {', '.join(sorted(COUNTRIES))}")
    if config["id"] != country_id:
        raise CountryError(f"{path} describes {config['id']!r}, not {country_id!r}")
    country = Country.from_config(config)
    stored = state.get("config")
    if stored is not None and stored != config and not redo:
        raise CountryError(f"The configuration of {country_id} changed since its tiles were counted: run again with "
                           f"--redo to count everything again")
    outline = os.path.join(folder, "area.geojson")

    def within(c):
        return (c.get("options") or {}).get("within")

    if not os.path.exists(outline) or (stored is not None and (stored.get("area") != config["area"]
                                                               or within(stored) != within(config))):
        say(f"Outline of {country.name}: {country.area}")
        _write_outline(country, folder, data_dir, say)
    area_sha = _sha256_file(outline)
    digest = config_hash(config, area_sha)
    if state.get("hash") not in (None, digest):
        if not redo:
            raise CountryError(f"The configuration or outline of {country_id} changed since its tiles were counted: "
                               f"run again with --redo to count everything again")
    if redo or state.get("hash") not in (None, digest):
        say("--redo: the tiles, the cube and the manifest are removed")
        _remove_results(folder)
        state.pop("origin", None)
    if "origin" in state and state.get("cube_version") != countcube.VERSION:
        raise CountryError(f"The tiles of {country_id} were counted for another version of the cube: run again "
                           f"with --redo to count everything again")
    state.update(config=config, area_sha256=area_sha, hash=digest)
    state.setdefault("created", _now())
    return state, country


def _finish_state(state: Dict, folder: str, plans: Dict):
    """The CRS, the cube's origin (once: countcube.origin_of the outline's WGS84 bounds less the
    longest line of the bands, in cells of the lattice) and the outline's WGS84 bounds, then
    country.json."""
    plan = next(iter(plans.values()))
    state["crs"] = plan.crs
    if "origin" not in state:
        reach = max(float(p.params.max_length) for p in plans.values())
        state["origin"] = list(countcube.origin_of(plan.area.geometry.bounds, reach))
        state["cube_version"] = countcube.VERSION
    state["bounds_wgs84"] = [round(v, 6) for v in plan.area.geometry.bounds]
    _write_json(os.path.join(folder, "country.json"), state)


# --- the plans of the bands ----------------------------------------------------------------------

def form_params(country: Country, band: Band) -> Dict:
    """SearchParams fields of a band, as the app's form takes them (cube.json's "params"): for a sag
    band the pretension is T at its max_length (the most tension and the least sag, so a search of a
    cell finds a superset of the lines T(L) gives)."""
    import sag as sg
    lo, hi = band.lengths
    params = {"source": country.source, "min_length": lo, "max_length": hi, "resolution": band.resolution,
              "model": band.model, "slope_threshold": band.slope_threshold}
    params.update({k: v for k, v in country.options.items()
                   if k in ("nmpt", "water", "coastline", "fill_gaps", "end_zone", "anchor_lift")})
    params["pretension"] = sg.tension_at(country.tension, hi)
    params.update(country.rig)
    return params


def band_plan(country: Country, band: Band, folder: str, data_dir: str, emit=None):
    """The band's plan over the whole outline (search.plan_search(tiled=False), area.geojson)."""
    import search
    from params import SearchParams
    values = form_params(country, band)
    values["area"] = os.path.join(folder, "area.geojson")
    for key in ("elevation_file", "surface_file"):
        if country.options.get(key):
            values[key] = country.options[key]
    paths = search.Paths(data_dir, os.path.join(data_dir, "work", f"country-{country.id}"))
    try:
        plan = search.plan_search(SearchParams(**values), paths, emit or (lambda kind, text: None), tiled=False)
    except search.SearchError as e:
        raise CountryError(f"Band {band.name}: {e}") from e
    return plan if country.study else _grown(plan)


def _grown(plan):
    """A country's band plan with its grid grown by the band's longest line beyond the outline's box:
    search.tile_grid clips a tile's grid to the band's, so a border tile at that box's edge reaches the
    partner anchors (Plan.partners) beyond it too. The cores (search.fixed_tiles, from the outline) stay;
    a tile's grid grows only where it was clipped."""
    import grid as gd
    g, res = plan.grid, plan.resolution
    reach = math.ceil(float(plan.params.max_length) / res) * res
    left, bottom, right, top = g.bounds
    wide = gd.make_grid((left - reach, bottom - reach, right + reach, top + reach), res, g.crs,
                        plan.source.grid_origin)
    wide.area_shape = g.area_shape
    return dataclasses.replace(plan, grid=wide)


def reach_shape(outline, grid, reach: float):
    """The outline (the grid's CRS) grown by reach, within the grid: a border tile's footprint
    (grid.area_shape: the data tiles mosaicked under it, the border gaps a neighbour fills), so the
    partner anchors' side has the source's own data and the neighbours' as a search over both sides
    would have them. Only the outline's part within reach of the grid is grown (the same shape within
    the grid: a point's nearest piece of the outline lies within reach of it)."""
    from shapely.geometry import box
    from shapely.validation import make_valid
    left, bottom, right, top = grid.bounds
    near = outline.intersection(box(left - reach, bottom - reach, right + reach, top + reach))
    grown = near.buffer(reach)
    return grown if grown.is_valid else make_valid(grown)


def tension_table(country: Country, band: Band, plan):
    """The sag table of a sag band (sag.TensionTable of T(L) over its lengths); None for the formula."""
    if band.model != "sag":
        return None
    import sag as sg
    return sg.TensionTable(plan.rigging, band.lengths[0], band.lengths[1], country.tension)


# --- the manifest --------------------------------------------------------------------------------

MIGRATIONS = [
    """
    CREATE TABLE tiles (
        band TEXT NOT NULL,
        name TEXT NOT NULL,
        core TEXT NOT NULL,                       -- JSON [left, bottom, right, top] in the country's CRS
        status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed
        attempts INTEGER NOT NULL DEFAULT 0,      -- claims that ended (or are running), not counting interruptions
        worker TEXT, started_at TEXT, finished_at TEXT,
        seconds REAL, lines INTEGER, spots INTEGER, error TEXT,
        PRIMARY KEY (band, name));
    CREATE INDEX tiles_status ON tiles (status, band);
    -- what the workers of the current run may claim: its bands, the tiles it may still start
    -- (--max-tiles; NULL: all) and its processes (for the threads of a tile)
    CREATE TABLE run (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        bands TEXT NOT NULL, tiles_left INTEGER, processes INTEGER NOT NULL, started_at TEXT);
    """,
    # v2: the work a pending tile is expected to take (_weights, set by each run): claimed heaviest
    # first, so the long tiles never come last; NULL (nothing known) after the others, in rowid order
    """
    ALTER TABLE tiles ADD COLUMN weight REAL;
    """,
]


class Manifest:
    """manifest.sqlite: the tiles of a country and their state (WAL: workers claim while the run reads)."""

    def __init__(self, folder: str):
        self.db = sqlite3.connect(os.path.join(folder, "manifest.sqlite"), timeout=120, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=120000")
        cache.migrate(self.db, MIGRATIONS)

    def close(self):
        self.db.close()

    def _write(self, work):
        """work(db) in one write transaction (BEGIN IMMEDIATE)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = work(self.db)
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def add_tiles(self, band: str, tiles) -> None:
        self._write(lambda db: db.executemany(
            "INSERT OR IGNORE INTO tiles (band, name, core) VALUES (?, ?, ?)",
            [(band, t.name, json.dumps(list(t.core))) for t in tiles]))

    def release_running(self, worker: Optional[str] = None) -> int:
        """Running tiles (of one worker, or all) back to pending: an interruption, not a failure."""
        where, args = ("status = 'running'", ()) if worker is None else ("status = 'running' AND worker = ?", (worker,))
        return self._write(lambda db: db.execute(
            f"UPDATE tiles SET status = 'pending', attempts = MAX(attempts - 1, 0), worker = NULL, started_at = NULL "
            f"WHERE {where}", args).rowcount)

    def set_run(self, bands: Sequence[str], tiles_left: Optional[int], processes: int):
        self._write(lambda db: db.execute(
            "INSERT OR REPLACE INTO run (id, bands, tiles_left, processes, started_at) VALUES (1, ?, ?, ?, ?)",
            (json.dumps(list(bands)), tiles_left, processes, _now())))

    def claim(self, worker: str, cores: int) -> Optional[Tuple[str, str, Tuple[float, ...], int]]:
        """The next pending tile of the run's bands (the heaviest first, by weight; then in the
        order they were added: bands as configured, rows from the north), marked running; with the
        threads its count may use (_threads) and whether it is heavy (_heavy_weight). None when
        nothing is left to claim."""
        def work(db):
            row = db.execute("SELECT bands, tiles_left, processes FROM run WHERE id = 1").fetchone()
            if row is None or (row[1] is not None and row[1] <= 0):
                return None
            bands = json.loads(row[0])
            marks = ",".join("?" * len(bands))
            tile = db.execute(f"SELECT band, name, core, weight FROM tiles WHERE status = 'pending' "
                              f"AND band IN ({marks}) ORDER BY weight IS NULL, weight DESC, rowid LIMIT 1",
                              bands).fetchone()
            if tile is None:
                return None
            db.execute("UPDATE tiles SET status = 'running', attempts = attempts + 1, worker = ?, started_at = ?, "
                       "error = NULL WHERE band = ? AND name = ?", (worker, _now(), tile[0], tile[1]))
            if row[1] is not None:
                db.execute("UPDATE run SET tiles_left = tiles_left - 1 WHERE id = 1")
            heavy = tile[3] is not None and tile[3] >= _heavy_weight(db, bands)
            return tile[0], tile[1], tuple(json.loads(tile[2])), _threads(db, bands, row[2], cores, heavy), heavy
        return self._write(work)

    def threads(self, cores: int, heavy: bool = False) -> int:
        """The threads a counting tile (heavy: _heavy_weight) may use now (_threads; one when no
        run is set)."""
        row = self.db.execute("SELECT bands, processes FROM run WHERE id = 1").fetchone()
        return 1 if row is None else _threads(self.db, json.loads(row[0]), row[1], cores, heavy)

    def set_weights(self, weights: Dict[Tuple[str, str], float]) -> None:
        """The weights of pending tiles by (band, name) (_weights)."""
        self._write(lambda db: db.executemany(
            "UPDATE tiles SET weight = ? WHERE band = ? AND name = ? AND status = 'pending'",
            [(w, band, name) for (band, name), w in weights.items()]))

    def requeue(self, band: str, names: Sequence[str]) -> int:
        """Done tiles back to pending, to be counted again (_requeue_border_tiles): no attempt taken; their
        lines and seconds of before stay in the row until the new count replaces them."""
        return self._write(lambda db: sum(db.execute(
            "UPDATE tiles SET status = 'pending', attempts = 0, worker = NULL, started_at = NULL, error = NULL "
            "WHERE band = ? AND name = ? AND status = 'done'", (band, name)).rowcount for name in names))

    def done(self, band: str, name: str, seconds: float, lines: int, spots: int):
        self._write(lambda db: db.execute(
            "UPDATE tiles SET status = 'done', finished_at = ?, seconds = ?, lines = ?, spots = ?, error = NULL "
            "WHERE band = ? AND name = ?", (_now(), seconds, lines, spots, band, name)))

    def fail(self, band: Optional[str], name: Optional[str], error: str, worker: Optional[str] = None) -> int:
        """A tile (or the running tiles of a worker that stopped) failed: back to pending after its
        first attempt, failed after ATTEMPTS."""
        where, args = (("band = ? AND name = ?", (band, name)) if worker is None
                       else ("status = 'running' AND worker = ?", (worker,)))
        return self._write(lambda db: db.execute(
            f"UPDATE tiles SET status = CASE WHEN attempts < {ATTEMPTS:d} THEN 'pending' ELSE 'failed' END, "
            f"worker = NULL, finished_at = ?, error = ? WHERE {where}", (_now(), error[-2000:], *args)).rowcount)

    def rows(self, band: Optional[str] = None) -> List[sqlite3.Row]:
        self.db.row_factory = sqlite3.Row
        try:
            if band is None:
                return self.db.execute("SELECT * FROM tiles ORDER BY rowid").fetchall()
            return self.db.execute("SELECT * FROM tiles WHERE band = ? ORDER BY rowid", (band,)).fetchall()
        finally:
            self.db.row_factory = None

    def counts(self) -> Dict[str, Dict[str, int]]:
        """Tiles per band and status."""
        out: Dict[str, Dict[str, int]] = {}
        for band, status, n in self.db.execute("SELECT band, status, COUNT(*) FROM tiles GROUP BY band, status"):
            out.setdefault(band, {})[status] = n
        return out


def _heavy_weight(db, bands: Sequence[str]) -> float:
    """The weight from which a tile of these bands is heavy: HEAVY_SHARE of the largest weight;
    infinite without weights (the first band of a country: nothing done yet)."""
    marks = ",".join("?" * len(bands))
    most = db.execute(f"SELECT MAX(weight) FROM tiles WHERE band IN ({marks})", list(bands)).fetchone()[0]
    return math.inf if not most else HEAVY_SHARE * most


def _threads(db, bands: Sequence[str], processes: int, cores: int, heavy: bool = False) -> int:
    """The threads of a counting tile: the logical cores shared by the workers still busy (the
    running and pending tiles of the run's bands, at most its processes). A heavy tile (the
    one asking is counted among the running) takes instead its share of the cores left after
    LIGHT_CORES per light tile running, when that is more; a light tile keeps at most
    LIGHT_THREADS while a heavy one runs."""
    marks = ",".join("?" * len(bands))
    running, pending, heavy_running = db.execute(
        f"SELECT SUM(status = 'running'), SUM(status = 'pending'), SUM(status = 'running' AND weight >= ?) "
        f"FROM tiles WHERE band IN ({marks})", [_heavy_weight(db, bands), *bands]).fetchone()
    running, pending, heavy_running = running or 0, pending or 0, heavy_running or 0
    busy = max(1, min(processes, running + pending))
    share = max(1, cores // busy)
    if not heavy:
        return share if heavy_running == 0 else min(share, LIGHT_THREADS)
    light = max(0, min(busy, running) - heavy_running)
    return max(share, (cores - LIGHT_CORES * light) // max(1, heavy_running))


def _weights(manifest: Manifest, bands: Sequence[str]) -> Tuple[Dict[Tuple[str, str], float], int]:
    """The expected work of the pending tiles of these bands: the lines of the tiles done already
    (of any band) whose core overlaps theirs (0 under done tiles without lines: a real 0, those tiles
    are light), and how many of them lie under no done tile (their work unknown: the run weighs every
    tile by the relief instead, _relief_weights). Beyond its grid, a tile's time goes to the pair
    search of its lines, and the lines of every band lie where the terrain is steep (Slovakia: the
    Tatras' tiles took 14 and 35 min, most others seconds)."""
    rows = manifest.db.execute("SELECT band, name, core, status, lines FROM tiles").fetchall()
    done = [(json.loads(core), lines or 0) for _, _, core, status, lines in rows if status == "done"]
    cores = np.array([c for c, _ in done], dtype=np.float64).reshape(-1, 4)
    lines = np.array([n for _, n in done], dtype=np.float64)
    out, unknown = {}, 0
    for band, name, core, status, _ in rows:
        if status == "pending" and band in bands:
            left, bottom, right, top = json.loads(core)
            over = (cores[:, 0] < right) & (left < cores[:, 2]) & (cores[:, 1] < top) & (bottom < cores[:, 3])
            out[(band, name)] = float(lines[over].sum())
            unknown += not over.any()
    return out, unknown


def _relief_weights(manifest: Manifest, bands: Sequence[str], outline, crs: str,
                    cache_dir: str) -> Tuple[Dict[Tuple[str, str], float], int]:
    """The weights of the pending tiles of these bands from the relief: RELIEF_LINES times the km² of
    slopes of RELIEF_DEGREES or more at 30 m whose block's centre lies inside the outline (WGS84) and
    the tile's core (crs), to the power RELIEF_EXPONENT; and the GLO-30 tiles read."""
    import relief
    blocks = relief.steep_blocks(outline, crs, cache_dir, RELIEF_DEGREES)
    out = {}
    for band in bands:
        rows = manifest.db.execute("SELECT name, core FROM tiles WHERE band = ? AND status = 'pending' "
                                   "ORDER BY rowid", (band,)).fetchall()
        steep = relief.per_core(blocks.x, blocks.y, blocks.steep, [json.loads(core) for _, core in rows])
        out.update({(band, name): float(RELIEF_LINES * km2 ** RELIEF_EXPONENT) for (name, _), km2 in zip(rows, steep)})
    return out, blocks.tiles


class _Rethreading:
    """The sink of a tile's count that sets numba's threads as the other workers end: after a part
    (search.count_tile hands the parts over between the line search's chunks, in the thread that
    starts its kernels), at most every RETHREAD_SECONDS, the threads threads_now() gives (the
    manifest's _threads). So the tiles counted last take the cores of the workers that are done;
    the counts never depend on the threads (tests/test_units.py::test_kernels_independent_of_threads)."""

    def __init__(self, sink, threads_now: Callable[[], int], threads: int, clock=time.monotonic):
        self.sink, self.threads_now, self.threads, self.clock = sink, threads_now, threads, clock
        self.most = threads  # the most threads the count got (the tile's meta: threads_max)
        self.looked = clock()

    def __call__(self, part):
        self.sink(part)
        if self.clock() - self.looked < RETHREAD_SECONDS:
            return
        self.looked = self.clock()
        try:
            threads = self.threads_now()
        except sqlite3.Error:  # the manifest busy for longer than its timeout: the next look
            return
        if threads != self.threads:
            import numba
            self.threads = max(1, min(threads, numba.config.NUMBA_NUM_THREADS))
            numba.set_num_threads(self.threads)
            self.most = max(self.most, self.threads)


# --- the work of a tile --------------------------------------------------------------------------

def _peak_memory() -> Optional[int]:
    """The peak memory of this process so far, in bytes (Windows: the peak working set)."""
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):
        return int(info.peak_wset)
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)
    except (ImportError, OSError):
        return None


def _commit() -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                             timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _private(memory) -> int:
    """The private bytes of a psutil memory_info: what the system cannot drop (Windows' commit; else
    the resident pages less the shared ones). The memory-mapped grids are file pages: they count in
    the working set (rss) only."""
    private = getattr(memory, "private", None)
    return int(private if private is not None else memory.rss - getattr(memory, "shared", 0))


def _io_counters() -> Tuple[int, int]:
    """Bytes read and written by this process so far (its file reads and writes, most served by the
    system's cache; the pages of the memory-mapped grids are not among them: a tile's disk is the
    machine's counters of the run's timeline, _RunSamples)."""
    try:
        io = psutil.Process().io_counters()
        return int(io.read_bytes), int(io.write_bytes)
    except (psutil.Error, AttributeError):
        return 0, 0


class _StageClock:
    """A progress listener (progress.subscribe) summing the wall and CPU seconds of a tile per
    stage: the label of the bar running, "other" between the bars. CPU: time.process_time, every
    thread of the process, so the CPU over the wall seconds is the cores a stage used."""

    def __init__(self, clock=time.monotonic, cpu=time.process_time):
        self.clock, self.cpu = clock, cpu
        self.current = "other"
        self.since, self.cpu_since = clock(), cpu()
        self.times: Dict[str, List[float]] = {}
        self.lock = threading.Lock()  # bars may be updated from the threads of a pool

    def _add(self):
        now, cpu = self.clock(), self.cpu()
        times = self.times.setdefault(self.current, [0.0, 0.0])
        times[0] += now - self.since
        times[1] += cpu - self.cpu_since
        self.since, self.cpu_since = now, cpu

    def __call__(self, state: Dict):
        if not state.get("bar"):
            return  # the text of a step
        stage = state.get("stage") or "other"
        with self.lock:
            if not state.get("done"):
                if stage != self.current:
                    self._add()
                    self.current = stage
            elif stage == self.current:
                self._add()
                self.current = "other"

    def result(self) -> Dict[str, List[float]]:
        """{stage: [seconds, CPU seconds]} up to now."""
        with self.lock:
            self._add()
            return {name: [round(s, 3), round(c, 3)] for name, (s, c) in self.times.items()}


class _TimedSink:
    """The counter's wall and CPU seconds (numpy on one thread, between the line search's chunks
    and at its end): a sink, and its result()."""

    def __init__(self, counter):
        self.counter, self.seconds, self.cpu = counter, 0.0, 0.0

    def _timed(self, call, *args):
        t, c = time.monotonic(), time.process_time()
        try:
            return call(*args)
        finally:
            self.seconds += time.monotonic() - t
            self.cpu += time.process_time() - c

    def __call__(self, part):
        self._timed(self.counter, part)

    def result(self):
        return self._timed(self.counter.result)


class _MemorySampler(threading.Thread):
    """This process's memory while a tile is counted, every TILE_SAMPLE_SECONDS: the peak working
    set (rss) and private bytes (_private), and the peak private bytes per stage of clock."""

    def __init__(self, clock: _StageClock):
        super().__init__(daemon=True)
        self.clock, self.process, self.halt = clock, psutil.Process(), threading.Event()
        self.rss = self.private = 0
        self.stages: Dict[str, int] = {}

    def run(self):
        while not self.halt.is_set():
            self.sample()
            self.halt.wait(TILE_SAMPLE_SECONDS)

    def sample(self):
        try:
            memory = self.process.memory_info()
        except psutil.Error:
            return
        private, stage = _private(memory), self.clock.current
        self.rss, self.private = max(self.rss, int(memory.rss)), max(self.private, private)
        self.stages[stage] = max(self.stages.get(stage, 0), private)

    def stop(self) -> Dict:
        self.halt.set()
        self.join()
        self.sample()
        return {"rss": self.rss, "private": self.private, "stages": dict(self.stages)}


class TileWork:
    """Counts the tiles one process claims: the bands' plans and sag tables made once per process."""

    def __init__(self, folder: str, data_dir: str, slot: int):
        self.folder, self.data_dir = folder, data_dir
        self.state = read_state(folder)
        self.country = Country.from_config(self.state["config"])
        self.origin = tuple(self.state["origin"])
        self.worker = f"slot-{slot}"
        self.plans: Dict[str, object] = {}
        self.tables: Dict[str, object] = {}
        self.commit = _commit()
        self.cores = os.cpu_count() or 1
        # The neighbours' territories, read and projected once per process (a study area has none)
        self.neighbours_sha, self.territories = ((None, None) if self.country.study
                                                 else load_territories(folder, self.state["crs"]))

    def _band(self, name: str):
        band = self.country.band(name)
        if name not in self.plans:
            plan = band_plan(self.country, band, self.folder, self.data_dir)
            self.plans[name] = plan
            self.tables[name] = tension_table(self.country, band, plan)
        return band, self.plans[name], self.tables[name]

    def tile_path(self, band: str, name: str) -> str:
        return os.path.join(self.folder, "tiles", band, f"{name}.npz")

    def count(self, band_name: str, name: str, core: Tuple[float, ...], threads: int,
              threads_now: Optional[Callable[[], int]] = None) -> Dict:
        """One tile: step 1, the count, its file; returns its meta. threads_now: the threads the
        count may take as it goes on (_Rethreading), else threads throughout."""
        import search
        import sources as src
        from progress import progress
        band, plan, table = self._band(band_name)
        started = _now()
        res = plan.resolution
        work = os.path.join(self.data_dir, "work", f"country-{self.country.id}", f"{band.name}-{name}")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        tile_plan_ = tile_plan(self.country, plan, core, search.Paths(self.data_dir, work), threads,
                               territories=self.territories, tile_label=f"{band.name} {name} · ", emit=_print_event)
        grid, partners = tile_plan_.grid, tile_plan_.partners
        print(f"\n--- Band {band.name}, tile {name} ({grid.width} x {grid.height} px, {threads} threads) ---",
              flush=True)
        src.used_data.clear()
        # The profile of the tile (`country profile`): seconds and CPU per stage, the counter's
        # share, the memory sampled while it runs, its file reads and writes
        clock = _StageClock()
        sampler = _MemorySampler(clock)
        cpu0, (read0, written0) = time.process_time(), _io_counters()
        progress.subscribe(clock)
        sampler.start()
        try:
            t0 = time.time()
            # Step 1 in strips of rows on the tile's own grid (round 3's wave 4 for a tiled area): the
            # grids memory-mapped in the work folder as the plain path writes them, one int32 array of
            # labels and a strip's temporaries in memory at a time, so the private memory of a worker
            # is not the whole tile's gap filling any more (COUNT_PIXEL_BYTES); steps 2-3 read the same
            # files with the same argument types (warmup.SEARCHES), so no copy of a tile's window
            # (search._tile_data) is needed: the window is the grid. No terrain histogram and no shore:
            # the cube holds none.
            data = search.prepare_data(tile_plan_, statistics=False, shore="none", strips=True)
            t1 = time.time()
            counter = _TimedSink(countcube.TileCounter(grid, self.origin, core, band.lengths,
                                                       float(band.lengths[1]) >= self.country.last_edge))
            sink = counter if threads_now is None else _Rethreading(counter, threads_now, threads)
            funnel = search.count_tile(tile_plan_, data, core, sink, table)
            counts = counter.result()
            t2 = time.time()
        finally:
            memory = sampler.stop()
            progress.unsubscribe(clock)
        read1, written1 = _io_counters()
        del data
        self._remove_grids(work)
        meta = {"version": countcube.VERSION, "config": self.state["hash"], "profile": self.country.profile.sha256,
                "origin": list(self.origin), "country": self.country.id, "band": band.name, "tile": name,
                "core": list(core), "partners": partners,
                "neighbours_sha256": self.neighbours_sha if partners is not None else None,
                "grid": {"width": grid.width, "height": grid.height, "res": res, "left": grid.left, "top": grid.top},
                "lines": counts.lines, "spots": int(len(counts.spot_ids)), "dropped": counts.dropped,
                "funnel": dict(funnel), "seconds": {"prepare": round(t1 - t0, 3), "count": round(t2 - t1, 3)},
                "stages": clock.result(), "sink": [round(counter.seconds, 3), round(counter.cpu, 3)],
                "cpu_seconds": round(time.process_time() - cpu0, 3), "memory": memory,
                "io": {"read": read1 - read0, "write": written1 - written0},
                "threads": threads, "threads_max": getattr(sink, "most", threads), "peak_memory": _peak_memory(),
                "commit": self.commit,
                "data": json.loads(json.dumps(src.used_data)), "started": started, "finished": _now()}
        path = self.tile_path(band.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        countcube.save_tile(path, counts, meta)
        print(f"Tile {band.name} {name}: {counts.lines} lines, {len(counts.spot_ids)} spots, "
              f"{t2 - t0:.1f} s", flush=True)
        return meta

    def _remove_grids(self, work: str):
        """A tile's work folder removed: its memory-mapped grids closed first (Windows), the views a
        worker kept (sources.mosaic.HELD_GRIDS) too, and the files deleted right after them, before
        the system writes their pages."""
        import sources.mosaic
        if sources.mosaic.HELD_GRIDS:
            sources.mosaic.HELD_GRIDS.clear()
        gc.collect()
        shutil.rmtree(work, ignore_errors=True)

    def cleanup(self, band: str, name: str):
        import sources as src
        self._remove_grids(os.path.join(self.data_dir, "work", f"country-{self.country.id}", f"{band}-{name}"))
        src.used_data.clear()

    def loop(self, manifest: Manifest, run_gone=None, freeze: bool = False) -> int:
        """Claim and count tiles until none is left (or the run is gone); returns the tiles done.
        freeze: what is alive after the first tile (the modules, numba's kernels, the band's plan)
        kept out of the collections of the next tiles (gc.freeze): count and cleanup each collect
        to close the memory-mapped grids, about 45 ms alone and 120 ms beside eleven workers over
        everything a worker has loaded."""
        done = 0
        while True:
            if run_gone is not None and run_gone():
                print("The run is gone: this worker stops", flush=True)
                break
            claimed = manifest.claim(self.worker, self.cores)
            if claimed is None:
                break
            band, name, core, threads, heavy = claimed
            try:
                meta = self.count(band, name, core, threads,
                                  threads_now=lambda: manifest.threads(self.cores, heavy))
            except Exception as e:  # the tile fails (pending again once, then failed); the others go on
                traceback.print_exc()
                sys.stdout.flush()
                self.cleanup(band, name)
                manifest.fail(band, name, f"{type(e).__name__}: {cache.clean_error(e)}")
                continue
            seconds = meta["seconds"]["prepare"] + meta["seconds"]["count"]
            manifest.done(band, name, seconds, meta["lines"], meta["spots"])
            self.cleanup(band, name)
            done += 1
            if freeze and done == 1:
                gc.freeze()
        return done


def partner_reach(plan) -> float:
    """How far a border tile's footprint (reach_shape) reaches beyond the outline: the band's longest line and two
    pixels, the terrain under every line across the border and the slope at its far anchor. Not the whole overlap
    (which adds the terrain margin of the prominence and the drop): the partners' windows reaching beyond it see
    the fallback's data there, which changed no count and no key of Slovakia's 367 border tiles of the S band and
    saved 27 % of their tile seconds against the overlap (wave B, 2026-11-08)."""
    res = plan.resolution
    return math.ceil(float(plan.params.max_length) / res) * res + 2 * res


def tile_plan(country: Country, plan, core: Tuple[float, ...], paths, threads: Optional[int] = None,
              territories: Optional[List] = None, **changes):
    """The plan of a tile of a band (TileWork.count): its grid (search.tile_grid: the core with the band's
    overlap, within the band's grid), the band's grid as its search grid (as search_lines gives its tiles:
    the world file's water polygons read once per band, coast.sea_mask's extent), Plan.border from
    _at_border, and at a country's border (not a study area's) the partner anchors within the band's
    longest line beyond the outline (Plan.partners; docs/country-precompute/contract.md section 6, "The
    borders") on the footprint grown by partner_reach (reach_shape: the source's own data beyond the outline,
    the neighbours' fill), with the territories that name a partner pixel's neighbour (load_territories; None:
    every partner 7, a source without neighbours). changes: other fields of the plan."""
    import search
    res = plan.resolution
    overlap = search._overlap(plan.params, res)
    grid = search.tile_grid(plan.grid, core, overlap, res, plan.source.grid_origin)
    border = _at_border(grid)
    partners = None
    if border and not country.study:
        partners = float(plan.params.max_length)
        grid.area_shape = reach_shape(plan.grid.area_shape, grid, partner_reach(plan))
    params = plan.params if threads is None else plan.params.model_copy(update={"threads": threads})
    return dataclasses.replace(plan, params=params, grid=grid, paths=paths, tiles=None, funnel={},
                               search_grid=plan.grid, border=border, partners=partners,
                               territories=territories if partners is not None else None, **changes)


def _at_border(grid, outline=None) -> bool:
    """Whether a tile's grid may hold a border of the country's data: False when it lies inside
    the outline (grid.area_shape, in the grid's CRS; or the outline given: the same shape prepared
    for many tiles, _border_tiles), where no neighbour has data to fill a gap with (the border gaps
    and the neighbours' attempts cost about 1.7 s per tile otherwise). A country's tile at its border
    counts the lines across it (tile_plan: Plan.border and Plan.partners)."""
    from shapely.geometry import box
    outline = getattr(grid, "area_shape", None) if outline is None else outline
    return outline is None or not box(*grid.bounds).within(outline)


def neighbour_boxes(plan, tiles, footprint) -> Dict[str, List[Tuple[str, Tuple[float, float, float, float]]]]:
    """Per neighbour of the band's source (Source.neighbours) the box (left, bottom, right, top in the plan's
    CRS) of each border tile (_at_border) that holds every window the neighbour may fill in it
    (sources.filling.neighbour_window): the strip of the footprint (reach_shape of the band's grid with its
    partner_reach, as a border tile's) beyond the outline, within the tile's grid and under the neighbour's rough
    boxes (their
    bounds in the CRS, as filling._box_ranges takes them, a pixel larger for its pixel ranges), grown by
    NEIGHBOUR_PAD and two pixels (a pixel the footprint touches, the window's pad), within the tile's grid. The
    border gaps (filling.border_gaps) lie in that strip while the source's own data cover the outline: a gap of
    its own data inside the outline reaching the strip could make a window larger (the tile then downloads the
    rest itself, as before). A neighbour without rough boxes may fill any border gap: the strip within the
    tile's grid. Asks nothing of the neighbours' services."""
    import shapely
    import sources as src
    from rasterio.warp import transform_bounds
    res = plan.resolution
    strip = footprint.difference(plan.grid.area_shape)
    rects = {}
    for n in plan.source.neighbours or ():
        boxes = src.SOURCES[n].rough_boxes()
        rects[n] = None if not boxes else [
            (left - res, bottom - res, right + res, top + res)
            for left, bottom, right, top in (transform_bounds("EPSG:4326", plan.crs, west, south, east, north)
                                             for south, north, west, east in boxes)]
    pad = (src.filling.NEIGHBOUR_PAD + 2) * res
    found: Dict[str, List[Tuple[str, Tuple[float, float, float, float]]]] = {n: [] for n in rects}
    for tile in tiles:
        if not _at_border(tile.grid):
            continue
        g_left, g_bottom, g_right, g_top = tile.grid.bounds
        for n, boxes in rects.items():
            near = None
            for left, bottom, right, top in boxes or [tile.grid.bounds]:
                left, bottom, right, top = max(left, g_left), max(bottom, g_bottom), min(right, g_right), min(top, g_top)
                if left >= right or bottom >= top:
                    continue
                piece = shapely.clip_by_rect(strip, left, bottom, right, top)
                if piece.is_empty:
                    continue
                b = piece.bounds
                near = b if near is None else (min(near[0], b[0]), min(near[1], b[1]), max(near[2], b[2]),
                                               max(near[3], b[3]))
            if near is not None:
                found[n].append((tile.name, (max(g_left, near[0] - pad), max(g_bottom, near[1] - pad),
                                             min(g_right, near[2] + pad), min(g_top, near[3] + pad))))
    return found


def _print_event(kind: str, text: str):
    print(("WARNING: " if kind == "warning" else "") + str(text), flush=True)


def worker(country_id: str, data_dir: str, slot: int) -> int:
    """`country worker`: a process of a run, claiming tiles until none is left. It reads only
    country.json and the manifest, and stops when the run's lock is free (the run is gone)."""
    import progress as pg
    import sources.mosaic
    from filelock import FileLock, Timeout
    from progress import progress
    folder = folder_of(data_dir, country_id)
    pg.TEXT_INTERVAL = WORKER_PROGRESS_SECONDS
    sources.mosaic.HELD_GRIDS = []  # a tile's grids never reach the disk (TileWork._remove_grids)
    lock_path = os.path.join(folder, "run.lock")

    def run_gone() -> bool:
        lock = FileLock(lock_path)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            return False
        lock.release()
        return True

    print(f"Worker {slot} of {country_id} started (pid {os.getpid()}, {_now()})", flush=True)
    work = TileWork(folder, data_dir, slot)
    manifest = Manifest(folder)
    try:
        with progress.bars():
            done = work.loop(manifest, run_gone, freeze=True)
    finally:
        manifest.close()
    print(f"Worker {slot} done: {done} tiles ({_now()})", flush=True)
    return 0


# --- run -----------------------------------------------------------------------------------------

class _Log:
    """The run's lines: printed and appended to logs/run.log."""

    def __init__(self, folder: str):
        self.path = os.path.join(folder, "logs", "run.log")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def __call__(self, text: str):
        print(text, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write("".join(f"{stamp} {line}\n" for line in str(text).splitlines() or [""]))


def _duration(seconds: float) -> str:
    from progress import _duration as text
    return text(seconds)


def _disk_bytes(plan, across: bool = False) -> int:
    """The bytes per pixel a tile's work folder holds at most: the grids step 1 writes for the
    band's plan and its temporaries in strips; across (a country's border tile): the partner grid
    (uint8), its zone (bool) and the territories' grid (uint8; both temporaries)."""
    import search
    return search.work_bytes(plan) + search.AREA_TEMP_BYTES + (3 if across else 0)


def worker_count(largest_px: int, available: Optional[int] = None, surface: bool = False) -> Tuple[int, float]:
    """The processes of a run (at most the physical cores, each with the memory of the largest
    tile: WORKER_BASE plus COUNT_PIXEL_BYTES per pixel, COUNT_SURFACE_PIXEL_BYTES with a surface model)
    and the bytes each needs. No cap below the
    physical cores: on this PC (12 physical, 24 logical cores) Slovakia's M2 band took 31.7, 32.1
    and 32.5-32.7 min at 8, 10 and 12 workers (LIGHT_CORES 1; 33.5, 33.7 and 34.3-34.4 with 2), its
    L band 17.8, 18.2 and 18.3 at 8, 10 and 12 (2026-11-05, docs/performance.md "Round 4", W1): the
    machine stood at 91-99 % of its logical cores in those runs, and fewer workers only moved cores
    from the light tiles to the heaviest ones, the band's end (_threads). A band of light tiles takes
    every worker it gets: the S band (every tile under 40 s) 29.3 min at 12 workers, 32.6 at 8 (the
    machine at 80 and 62 %)."""
    import search
    per = WORKER_BASE + (COUNT_SURFACE_PIXEL_BYTES if surface else COUNT_PIXEL_BYTES) * largest_px
    available = search.available_memory() if available is None else available
    cores = psutil.cpu_count(logical=False) or os.cpu_count() or 1
    return max(1, min(cores, int(available // per))), per


def _ask(question: str) -> bool:
    from progress import progress
    try:
        answer = progress.ask(question)
    except EOFError:
        answer = ""
    return answer.strip().lower() in ("y", "yes", "t", "tak")


def neighbour_shapes(plans: Dict, tiles: Dict[str, Sequence]) -> Dict[str, object]:
    """Per neighbour of the source the area (the plans' CRS) of every window a border tile of the bands may ask
    of it: each band's boxes (neighbour_boxes, with its partner_reach) on its footprint grown by a pixel, joined
    over the bands (plans of one resolution, whose tiles ask the neighbour's layers on grids of that resolution).
    tiles: the FixedTiles of each band to cover (a band without any: none)."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    parts: Dict[str, list] = {}
    for name, plan in plans.items():
        if not tiles.get(name):
            continue
        footprint = reach_shape(plan.grid.area_shape, plan.grid, partner_reach(plan))
        for n, boxes in neighbour_boxes(plan, tiles[name], footprint).items():
            if boxes:
                parts.setdefault(n, []).append(
                    footprint.buffer(plan.resolution).intersection(unary_union([box(*b) for _, b in boxes])))
    return {n: unary_union(shapes) for n, shapes in parts.items()}


def _neighbour_layers(plans: Dict, tiles: Dict[str, Sequence]) -> List[Tuple[object, str, object]]:
    """The neighbours' layers the border tiles of the bands (plans of one resolution) may fill their gaps from,
    each (layer, label, grid) over its own grid (sources.download_layers): the terrain, and the surface model when
    the bands use one (filling.fill_gaps fills a neighbour's surface gaps from its own surface model only; it
    reads no water mask), over neighbour_shapes on a grid of the plans' (their CRS, resolution and pixel edges:
    the tiles each tile's window asks are among them), its box made square where it is taller than wide
    (indexes/tilings.WcsTiling looks for an area's tiles over a square of the grid's width here: main's 04e91b0
    of 2026-11-08 scans the whole box, tests/test_sources.py::test_wcs_tiles_of_a_tall_area; the square can go
    once this branch has merged it). An unavailable neighbour is left to the tiles, which say why
    (fill_from_neighbours)."""
    import grid as gd
    import sources as src
    from sources.choose import source_unavailable
    first = next(iter(plans.values()))
    found = []
    for n, shape in neighbour_shapes(plans, tiles).items():
        neighbour = src.SOURCES[n]
        if shape.is_empty or source_unavailable(neighbour):
            continue
        left, bottom, right, top = shape.bounds
        if top - bottom > right - left:
            middle, half = (left + right) / 2, (top - bottom) / 2
            left, right = middle - half, middle + half
        grid = gd.make_grid((left, bottom, right, top), first.resolution, first.crs, first.source.grid_origin)
        grid.area_shape = shape
        label = f"gap fill ({neighbour.name})"
        found.append((neighbour.nmt, label, grid))
        if first.nmpt and neighbour.nmpt is not None:
            found.append((neighbour.nmpt, label, grid))
    return found


def _prefetch_groups(plans: Dict, across: bool = False,
                     tiles: Optional[Dict[str, Sequence]] = None) -> List[Tuple[float, list, object]]:
    """What _prefetch fetches, per resolution: (resolution, the entries of sources.download_layers, the grid
    of the source's own layers). The terrain, the surface when used and the water mask on the band's grid of
    that resolution (the largest: its tiles lie within it); across (a country, not a study area) on its
    footprint, the outline grown by partner_reach as a border tile's (reach_shape), and the neighbours' layers
    on their own grids over the windows the border tiles among `tiles` (each band's to count) may ask of them
    (_neighbour_layers)."""
    import copy
    import search
    import sources as src
    largest = {}
    for plan in plans.values():
        best = largest.get(plan.resolution)
        if best is None or plan.grid.width * plan.grid.height > best.grid.width * best.grid.height:
            largest[plan.resolution] = plan
    groups = []
    for res, plan in sorted(largest.items()):
        layers = list(zip(plan.layers, ("terrain", "surface")))
        if plan.params.water == "fill" or search._fills_gaps(plan):
            layers.append((src.WATER_MASK, "water mask"))
        if across and tiles and search._fills_gaps(plan):
            layers += _neighbour_layers({n: p for n, p in plans.items() if p.resolution == res}, tiles)
        grid = plan.grid
        if across:
            grid = copy.copy(plan.grid)
            grid.area_shape = reach_shape(plan.grid.area_shape, plan.grid, partner_reach(plan))
        groups.append((res, layers, grid))
    return groups


def prefetch_bytes(groups: Sequence[Tuple[float, list, object]], cache_dir: str) -> int:
    """The bytes the prefetch (_prefetch_groups) would still download into the cache, as its layers estimate them
    (Layer.estimate on the grids the prefetch fetches: the tiles not cached yet times their size, the copies of a
    source's mirror too), each tile once over the resolutions (the water mask and the neighbours' tiles are the
    same tiles on every band's grid). The indexes are asked (each layer's at once, as download_layers asks
    them), no tile is downloaded."""
    import sources as src
    sizes: Dict[str, float] = {}
    for _, entries, grid in groups:
        grids: Dict[int, object] = {}
        for entry in entries:
            grids.setdefault(id(entry[0]), entry[2] if len(entry) > 2 else grid)
        layers = list({id(entry[0]): entry[0] for entry in entries}.values())
        found = src.layer.each_layer(layers, lambda layer: (layer.estimate(grids[id(layer)], cache_dir, None),
                                                            layer.missing(grids[id(layer)], cache_dir, None)))
        for layer, ((_, todo, mb), missing) in zip(layers, found):
            each = mb * 1e6 / todo if todo else 0.0
            for tile in missing:
                sizes.setdefault(layer.tile_path(cache_dir, tile), each)
    return int(sum(sizes.values()))


def _prefetch(plans: Dict, say, across: bool = False, tiles: Optional[Dict[str, Sequence]] = None,
              groups: Optional[Sequence[Tuple[float, list, object]]] = None):
    """The data over the whole country into the cache before the workers start (_prefetch_groups, or the groups
    given: what _run's free-disk check estimated), sources.download_layers per resolution, the neighbours' layers
    in the same pool: otherwise each border tile downloads them in its step 1, block by block under the host
    slots (BEV allows 2 connections), its count waiting; the blocks of big remote files in squares of
    PREFETCH_GROUP_M, each file read once per square. The fallbacks' data stay with the tiles."""
    import sources as src
    if groups is None:
        groups = _prefetch_groups(plans, across, tiles)
    cache_dir = next(iter(plans.values())).paths.cache
    for res, layers, grid in groups:
        say(f"Prefetch at {res:g} m: {', '.join(dict.fromkeys(entry[1] for entry in layers))}")
        try:
            src.download_layers(layers, grid, cache_dir, None, group_m=PREFETCH_GROUP_M)
        except RuntimeError as e:
            say(f"WARNING: the prefetch failed ({cache.clean_error(e)}): the tiles download what they need")


class _Everywhere:
    """The area of the warm-up: every pixel."""

    def mask(self, grid):
        return np.ones((grid.height, grid.width), dtype=bool)


def _warm_up(country: Country, plans: Dict, folder: str, data_dir: str, say):
    """Compile the numba kernels once (cached in __pycache__) before the workers start: a tiny
    count of each model on a synthetic canyon, with the arrays as step 1 gives them (memory-mapped,
    read-only)."""
    import grid as gd
    import sag as sg
    import search
    work = os.path.join(data_dir, "work", f"country-{country.id}", "warm-up")
    os.makedirs(work, exist_ok=True)
    size = 64
    elevation = np.full((size, size), 100.0, dtype=np.float32)
    elevation[:, 20:44] = 0.0
    np.save(os.path.join(work, "nmt.npy"), elevation)
    np.save(os.path.join(work, "water.npy"), np.zeros((size, size), dtype=bool))
    data = search.Data(np.load(os.path.join(work, "nmt.npy"), mmap_mode="r"), None,
                       np.load(os.path.join(work, "water.npy"), mmap_mode="r"), None, None)
    models = {}
    for name, plan in plans.items():
        models.setdefault(plan.params.model, (country.band(name), plan))
    for model, (band, plan) in models.items():
        grid = gd.make_grid((0.0, 0.0, size * 1.0, size * 1.0), 1.0, plan.crs)
        params = plan.params.model_copy(update={"min_length": 10, "max_length": 40, "resolution": 1.0})
        small = dataclasses.replace(plan, params=params, grid=grid, resolution=1.0, area=_Everywhere(), funnel={},
                                    emit=lambda kind, text: None, paths=search.Paths(data_dir, work))
        table = sg.TensionTable(plan.rigging, 10, 40, country.tension) if model == "sag" else None
        found = []
        search.count_tile(small, data, None, found.append, table)
        # the counter's kernels (countkernels) on the parts as the count hands them
        from pyproj import Transformer
        bounds = Transformer.from_crs(plan.crs, "EPSG:4326", always_xy=True).transform_bounds(0.0, 0.0, size, size)
        counter = countcube.TileCounter(grid, countcube.origin_of(bounds, 0.0), None, (10, 40), True)
        for part in found:
            counter(part)
        counter.result()
        say(f"Warm-up of the {model} model: {sum(len(p) for p in found)} lines")
    del data
    gc.collect()
    shutil.rmtree(work, ignore_errors=True)


def _progress_line(manifest: Manifest, bands: Sequence[str], processes: int, started: float) -> str:
    rows = manifest.db.execute("SELECT band, status, COUNT(*), SUM(lines), SUM(seconds) FROM tiles "
                               "GROUP BY band, status").fetchall()
    total: Dict[str, int] = {}
    done: Dict[str, int] = {}
    lines, left = 0, 0.0
    seconds: Dict[str, float] = {}
    for band, status, n, n_lines, n_seconds in rows:
        total[band] = total.get(band, 0) + n
        if status == "done":
            done[band] = n
            lines += n_lines or 0
            seconds[band] = (n_seconds or 0.0) / max(n, 1)
    known = True
    for band in bands:
        remaining = total.get(band, 0) - done.get(band, 0)
        if remaining:
            if band in seconds:
                left += remaining * seconds[band]
            else:
                known = False
    parts = [f"{b} {done.get(b, 0)}/{total.get(b, 0)}" for b in total]
    eta = f"~{_duration(left / max(processes, 1))} left" if known else "time left unknown yet"
    return (f"[{datetime.now():%H:%M:%S}] tiles {', '.join(parts)} · {lines:,} lines · "
            f"{_duration(time.time() - started)} elapsed, {eta}")


def _worker_env() -> Dict[str, str]:
    """The environment of a `country worker` process: text progress, UTF-8 output, and one BLAS
    thread. numpy and SciPy each load their own OpenBLAS, and each commits about 32 MB of buffers per
    thread when it is loaded, one thread per logical core unless OPENBLAS_NUM_THREADS says otherwise:
    0.76 GiB of a worker's private bytes after numpy on 24 logical cores, 1.5 GiB after SciPy. The
    buffers are reserved, never touched (never in the working set): they count against Windows' commit
    limit, not the RAM, and made the private bytes a worker_count model is measured on 1.5 GiB larger.
    A count calls no BLAS routine on anything large (helpers.downslope's 3-vector products at the
    anchors, sag's 3 x 3 solves).

    OMP_WAIT_POLICY=PASSIVE unless the caller's environment sets it: numba's OpenMP layer (vcomp on
    Windows) keeps its threads spinning after each parallel region, through the counter's numpy and
    step 1 between the kernels, so a tile's threads take cores from the other workers and its CPU
    seconds count the spinning. With PASSIVE sk-sulov's four layer bands took 19 % fewer CPU seconds
    and 6 % fewer tile seconds, Slovakia's first all-bands run 5.4 % fewer CPU seconds at a wall within
    the spread of equal runs, the counts the same (2026-11-07, docs/performance.md "Round 5").

    PYTHONFAULTHANDLER=1 unless the caller's environment sets it: a worker that dies of a fatal error
    writes the Python stack of its threads into its log (the heap corruptions of GDAL's warper,
    0xC0000374, left a log that stopped mid-tile without a word: CLAUDE.md, "GDAL's warper on Windows")."""
    return {"OMP_WAIT_POLICY": "PASSIVE", "PYTHONFAULTHANDLER": "1", **os.environ, "FINDALINE_PROGRESS": "text", "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


def _worker_process(country_id: str, data_dir: str, folder: str, slot: int) -> subprocess.Popen:
    """A `country worker` process, logging to logs/worker-<k>.log, in a process group of its own (a
    Ctrl+C of the console reaches the run only, which stops the workers itself)."""
    log = open(os.path.join(folder, "logs", f"worker-{slot}.log"), "ab")
    env = _worker_env()
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen([sys.executable, os.path.join(REPO, "findaline.py"), "country", "worker", country_id,
                                 "--slot", str(slot), "--data-dir", data_dir],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=REPO, env=env,
                                **kwargs)
    finally:
        log.close()  # the child has its own handle


def run(country_id: str, data_dir: str, processes: Optional[int] = None, bands: Optional[Sequence[str]] = None,
        max_tiles: Optional[int] = None, redo: bool = False, yes: bool = False) -> int:
    """`country run`: count the tiles still pending, then build the cube when every layer band is
    done. Returns the exit code (0 done or more to do, 1 failed tiles or refused, 130 interrupted)."""
    from filelock import FileLock, Timeout
    folder = folder_of(data_dir, country_id)
    os.makedirs(os.path.join(folder, "logs"), exist_ok=True)
    lock = FileLock(os.path.join(folder, "run.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(f"Another run of {country_id} is going on (its lock: {lock.lock_file})")
        return 1
    say = _Log(folder)
    try:
        return _run(country_id, data_dir, folder, processes, bands, max_tiles, redo, yes, say)
    except CountryError as e:
        say(str(e))
        return 1
    finally:
        lock.release()


def _set_weights(manifest: Manifest, bands: Sequence[str], plans: Dict, say):
    """The weights of the pending tiles of the run's bands (claimed heaviest first): the lines of the
    tiles done already over them (_weights), or, when one of them lies under no done tile, every one
    by the relief (_relief_weights; a failure leaves them in their order)."""
    weights, unknown = _weights(manifest, bands)
    if not weights:
        return
    if not unknown:
        manifest.set_weights(weights)
        say(f"The heaviest tiles first: {sum(w > 0 for w in weights.values())} of {len(weights)} pending tiles "
            f"lie under the lines of the tiles done already")
        return
    plan = next(iter(plans.values()))
    started = time.monotonic()
    try:
        weights, tiles = _relief_weights(manifest, bands, plan.area.geometry, plan.crs, plan.paths.cache)
    except Exception as e:  # no network for a missing tile, an unreadable file: the order of before
        say(f"WARNING: the tiles' weights from the relief failed ({cache.clean_error(e)}): they keep the weights "
            f"they had (none in a first run: claimed in their order)")
        return
    manifest.set_weights(weights)
    say(f"The heaviest tiles first, by the relief: {sum(w > 0 for w in weights.values())} of {len(weights)} pending "
        f"tiles hold slopes of {RELIEF_DEGREES}° or more at 30 m (Copernicus GLO-30, {tiles} tiles, "
        f"{time.monotonic() - started:.0f} s); " + ("no tile is done yet" if unknown == len(weights) else
                                                     f"{unknown} lie under no done tile"))


def _border_tiles(plan, tiles) -> set:
    """The names of the tiles at the country's border (_at_border, the predicate of tile_plan's Plan.border and
    Plan.partners), the band's outline prepared once for all of them (a copy: the plan's own stays as it is)."""
    import copy
    import shapely
    outline = getattr(plan.grid, "area_shape", None)
    if outline is not None:
        outline = copy.copy(outline)
        shapely.prepare(outline)
    return {t.name for t in tiles if _at_border(t.grid, outline)}


def _requeue_border_tiles(manifest: Manifest, country: Country, plans: Dict, band_tiles: Dict[str, Sequence],
                          folder: str, neighbours_sha: Optional[str], say) -> int:
    """The done border tiles whose meta's "neighbours_sha256" is not the sha256 of neighbours.geojson, back to
    pending: a country's tile at its border is decided from the tile's grid by the predicate that gives it
    partners (_border_tiles), never from what an old meta holds. So a new neighbours.geojson counts the border
    tiles again and only them, as does a border tile counted before the territories (no such key); the config
    hash and countcube.VERSION stay. Only the border tiles' meta is read (3435 metas took 22 s cold on Slovakia's
    lead folder): a tile inside the outline is expected to hold None and nothing of an unchanged outline gives it
    a sha256, and a study area has no file and no partners; `build` checks every tile. A tile file that cannot be
    read is left to `build`. Returns how many."""
    total = 0
    if country.study or neighbours_sha is None:
        return total
    for band in country.bands:
        done = sorted(r["name"] for r in manifest.rows(band.name) if r["status"] == "done")
        if not done:
            continue
        border = _border_tiles(plans[band.name], band_tiles[band.name])
        stale = []
        for name in (n for n in done if n in border):
            try:
                found = _tile_meta(os.path.join(folder, "tiles", band.name, f"{name}.npz")).get("neighbours_sha256")
            except (OSError, ValueError, KeyError):
                continue
            if found != neighbours_sha:
                stale.append(name)
        if stale:
            n = manifest.requeue(band.name, stale)
            total += n
            say(f"Band {band.name}: {n} border tiles counted with other territories of the neighbours (or before "
                f"them) are pending again")
    return total


def _run(country_id, data_dir, folder, processes, bands, max_tiles, redo, yes, say) -> int:
    import search
    from progress import progress
    say(f"=== country run {country_id} ({_now()}) ===")
    state, country = setup(country_id, folder, data_dir, redo, say)
    _say_overlaps(country, folder, data_dir, say)
    names = [b.name for b in country.bands]
    selected = list(bands) if bands else names
    for name in selected:
        country.band(name)
    plans = {b.name: band_plan(country, b, folder, data_dir) for b in country.bands}
    first = next(iter(plans.values()))
    neighbours_sha = ensure_neighbours(country, folder, first.paths.cache, first.crs, say)
    if neighbours_sha is None:
        state.pop("neighbours_sha256", None)
    else:
        state["neighbours_sha256"] = neighbours_sha
    _finish_state(state, folder, plans)
    manifest = Manifest(folder)
    try:
        largest = disk = 0
        band_tiles = {}
        for band in country.bands:
            tiles = band_tiles[band.name] = search.fixed_tiles(plans[band.name], band.core_m)
            manifest.add_tiles(band.name, tiles)
            if band.name in selected and tiles:
                largest = max(largest, max(t.grid.width * t.grid.height for t in tiles))
                disk = max(disk, max(t.grid.width * t.grid.height for t in tiles)
                           * _disk_bytes(plans[band.name], across=not country.study))
        stale = manifest.release_running()
        if stale:
            say(f"{stale} tiles of an interrupted run are pending again")
        _requeue_border_tiles(manifest, country, plans, band_tiles, folder, neighbours_sha, say)
        shutil.rmtree(os.path.join(data_dir, "work", f"country-{country.id}"), ignore_errors=True)
        counts = manifest.counts()
        todo = sum(counts.get(b, {}).get("pending", 0) for b in selected)
        k, per = worker_count(largest, surface=any(plans[n].nmpt for n in selected))
        if processes is not None:
            k = processes
        elif max_tiles is not None or todo:
            k = max(1, min(k, todo, max_tiles if max_tiles is not None else todo))
        k_eff = max(1, k)  # the processes counting at once (0: this one)
        need = k_eff * disk + DISK_SPARE  # the work folders
        free = shutil.disk_usage(data_dir).free  # the cache's drive too (<data>/cache)
        for band in country.bands:
            c = counts.get(band.name, {})
            say(f"Band {band.name} {band.lengths[0]:g}-{band.lengths[1]:g} m at {band.resolution:g} m "
                f"({band.model}, {band.slope_threshold:g}°, cores of {band.core_m:g} m"
                f"{'' if band.layer else ', control'}): {sum(c.values())} tiles, {c.get('done', 0)} done, "
                f"{c.get('pending', 0)} pending, {c.get('failed', 0)} failed")
        say(f"Selected bands: {', '.join(selected)}; {todo} tiles to count"
            + (f" (at most {max_tiles} now)" if max_tiles is not None else "")
            + (f"; {k} worker processes, about {per / 2 ** 30:.1f} GiB of memory each" if k else
               "; in this process"))
        groups, download = None, 0
        if todo:  # what the prefetch will download into the cache, before any download (the indexes are asked)
            pending = {(r["band"], r["name"]) for r in manifest.rows() if r["status"] == "pending"}
            groups = _prefetch_groups({n: plans[n] for n in selected}, across=not country.study,
                                      tiles={n: [t for t in band_tiles[n] if (n, t.name) in pending] for n in selected})
            download = prefetch_bytes(groups, plans[selected[0]].paths.cache)
            say(f"The prefetch downloads about {download / 2 ** 30:.1f} GiB into the cache (the tiles not cached yet, "
                f"as their layers estimate them)")
        if todo and free < need + download:
            say(f"Not enough free disk in {data_dir}: {free / 2 ** 30:.1f} GiB, the work folders need about "
                f"{need / 2 ** 30:.1f} GiB and the prefetch about {download / 2 ** 30:.1f} GiB in the cache "
                f"({(need + download) / 2 ** 30:.1f} GiB in all). Free some, or use fewer --processes.")
            return 1
        if todo and not yes and not _ask("Start? [y/N] "):
            say("Not started (--yes skips this question)")
            return 1
        started = time.time()
        if todo:
            _set_weights(manifest, selected, plans, say)
            with progress.bars():
                _prefetch({n: plans[n] for n in selected}, say, groups=groups)
                if k:
                    _warm_up(country, {n: plans[n] for n in selected}, folder, data_dir, say)
            manifest.set_run(selected, max_tiles, k_eff)
            code = (_run_workers(country_id, data_dir, folder, manifest, k, selected, say, started) if k
                    else _run_here(folder, data_dir, manifest, say))
            if code:
                return code
            say(_progress_line(manifest, selected, k_eff, started))
        return _after(country, data_dir, manifest, selected, say)
    finally:
        manifest.close()


def _run_here(folder: str, data_dir: str, manifest: Manifest, say) -> int:
    """--processes 0: the tiles counted in this process."""
    from progress import progress
    work = TileWork(folder, data_dir, 0)
    try:
        with progress.bars():
            work.loop(manifest)
    except KeyboardInterrupt:
        n = manifest.release_running()
        say(f"Stopped: {n} tiles being counted are pending again")
        return 130
    return 0


def _disk_counters() -> Tuple[int, int]:
    """Bytes read and written by the machine's disks so far."""
    try:
        disk = psutil.disk_io_counters()
        return (int(disk.read_bytes), int(disk.write_bytes)) if disk else (0, 0)
    except (psutil.Error, RuntimeError):
        return 0, 0


class _RunSamples:
    """A run's timeline: logs/samples-<start>.csv, a row every RUN_SAMPLE_SECONDS (and at the start
    and the end) with the machine's CPU % and memory, the workers' cores (their CPU seconds over
    the interval), working set and private bytes (_private), each of a worker's process tree (a
    venv's python.exe on Windows runs the interpreter as its child), the tiles being counted, and
    the disks' read and write MB/s. `country profile` sums up the last one."""

    COLUMNS = ("time", "seconds", "machine_cpu_pct", "ram_used_gib", "ram_available_gib", "workers",
               "workers_cores", "workers_rss_gib", "workers_private_gib", "running_tiles", "disk_read_mbs",
               "disk_write_mbs")

    def __init__(self, folder: str):
        self.path = os.path.join(folder, "logs", f"samples-{datetime.now():%Y%m%d-%H%M%S}.csv")
        self.started = self.last = time.monotonic()
        psutil.cpu_percent(None)  # the first call only starts the interval
        self.disk = _disk_counters()
        self.cpu: Dict[Tuple[int, float], float] = {}
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(",".join(self.COLUMNS) + "\n")

    def sample(self, pids: Sequence[int], manifest: Manifest):
        now = time.monotonic()
        interval = max(now - self.last, 1e-6)
        alive, cores, rss, private = 0, 0.0, 0, 0
        for pid in pids:
            try:
                worker = psutil.Process(pid)
                tree = [worker] + worker.children(recursive=True)
            except psutil.Error:
                continue
            alive += 1
            for process in tree:
                try:
                    key = (process.pid, process.create_time())
                    times, memory = process.cpu_times(), process.memory_info()
                except psutil.Error:
                    continue
                cpu = times.user + times.system
                cores += (cpu - self.cpu.get(key, cpu)) / interval  # nothing before a process's first sample
                self.cpu[key] = cpu
                rss, private = rss + int(memory.rss), private + _private(memory)
        disk, ram = _disk_counters(), psutil.virtual_memory()
        try:
            running = manifest.db.execute("SELECT COUNT(*) FROM tiles WHERE status = 'running'").fetchone()[0]
        except sqlite3.Error:
            running = ""
        row = (datetime.now().isoformat(timespec="seconds"), f"{now - self.started:.1f}",
               f"{psutil.cpu_percent(None):.1f}", f"{ram.used / 2 ** 30:.2f}", f"{ram.available / 2 ** 30:.2f}",
               alive, f"{cores:.2f}", f"{rss / 2 ** 30:.2f}", f"{private / 2 ** 30:.2f}", running,
               f"{(disk[0] - self.disk[0]) / interval / 1e6:.1f}", f"{(disk[1] - self.disk[1]) / interval / 1e6:.1f}")
        self.disk, self.last = disk, now
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(",".join(map(str, row)) + "\n")


def _run_workers(country_id, data_dir, folder, manifest: Manifest, k: int, selected, say, started) -> int:
    """K worker processes until none is left; a progress line every PROGRESS_SECONDS, a row of the
    run's timeline every RUN_SAMPLE_SECONDS; on Ctrl+C the workers killed (jobs.kill_tree) and
    their tiles pending again."""
    import jobs
    procs = {slot: _worker_process(country_id, data_dir, folder, slot) for slot in range(k)}
    samples = _RunSamples(folder)
    say(f"Started {k} workers (logs in {os.path.join(folder, 'logs')}, the timeline in "
        f"{os.path.basename(samples.path)})")
    samples.sample([p.pid for p in procs.values()], manifest)
    respawns, last, sampled = 0, time.time(), time.time()
    try:
        while procs:
            time.sleep(1)
            if time.time() - sampled >= RUN_SAMPLE_SECONDS:
                sampled = time.time()
                samples.sample([p.pid for p in procs.values()], manifest)
            for slot, proc in list(procs.items()):
                code = proc.poll()
                if code is None:
                    continue
                del procs[slot]
                if code == 0:
                    continue
                n = manifest.fail(None, None, f"worker {slot} stopped with exit code {code}", worker=f"slot-{slot}")
                say(f"Worker {slot} stopped with exit code {code} ({n} tiles back to pending or failed; "
                    f"see logs/worker-{slot}.log)")
                marks = ",".join("?" * len(selected))
                pending = manifest.db.execute(f"SELECT COUNT(*) FROM tiles WHERE status = 'pending' "
                                              f"AND band IN ({marks})", list(selected)).fetchone()[0]
                if pending and respawns < RESPAWNS_PER_WORKER * k:
                    respawns += 1
                    procs[slot] = _worker_process(country_id, data_dir, folder, slot)
            if time.time() - last >= PROGRESS_SECONDS:
                last = time.time()
                say(_progress_line(manifest, selected, k, started))
    except KeyboardInterrupt:
        for proc in procs.values():
            jobs.kill_tree(proc.pid)
        n = manifest.release_running()
        say(f"Stopped: the workers were stopped, {n} tiles being counted are pending again")
        return 130
    samples.sample([], manifest)  # the end
    return 0


def _after(country: Country, data_dir: str, manifest: Manifest, selected, say) -> int:
    """The end of a run: the cube when every layer band is done, else what is left."""
    counts = manifest.counts()
    failed = sum(counts.get(b, {}).get("failed", 0) for b in selected)
    layer = [b.name for b in country.bands if b.layer]
    missing = sum(n for b in layer for status, n in counts.get(b, {}).items() if status != "done")
    if failed:
        say(f"{failed} tiles failed (see `findaline.py country status {country.id}`); "
            f"`country build {country.id} --partial` builds the cube without them")
        return 1
    if missing:
        say(f"{missing} tiles of the layer bands are left: run again to go on")
        return 0
    if not all(counts.get(b) for b in layer):
        say("The layer bands have no tiles: nothing to build")
        return 1
    return build(country.id, data_dir, say=say)


# --- status, build, compare ----------------------------------------------------------------------

def status(country_id: str, data_dir: str) -> int:
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    manifest = Manifest(folder)
    try:
        print(f"{country.name} ({country.id}): config {state.get('hash', '?')[:12]}, origin {state.get('origin')}, "
              f"{state.get('crs', '?')}")
        header = f"{'Band':<5} {'Tiles':>6} {'Done':>6} {'Run':>4} {'Pend':>6} {'Fail':>5} {'Lines':>14} " \
                 f"{'Spots':>12} {'Seconds':>10} {'Median s':>9}"
        print(header)
        errors = []
        for band in country.bands:
            rows = manifest.rows(band.name)
            by = {}
            for r in rows:
                by[r["status"]] = by.get(r["status"], 0) + 1
            done = [r for r in rows if r["status"] == "done"]
            secs = [r["seconds"] or 0.0 for r in done]
            print(f"{band.name:<5} {len(rows):>6} {by.get('done', 0):>6} {by.get('running', 0):>4} "
                  f"{by.get('pending', 0):>6} {by.get('failed', 0):>5} {sum(r['lines'] or 0 for r in done):>14,} "
                  f"{sum(r['spots'] or 0 for r in done):>12,} {sum(secs):>10.0f} "
                  f"{(float(np.median(secs)) if secs else 0.0):>9.1f}")
            errors += [r for r in rows if r["error"]]
        if errors:
            print("Errors:")
            for r in errors:
                print(f"  {r['band']} {r['name']} ({r['status']}, {r['attempts']} attempts): {r['error']}")
        cube = os.path.join(folder, "cube", "cube.json")
        if os.path.exists(cube):
            with open(cube, encoding="utf-8") as f:
                info = json.load(f)
            totals = info.get("totals", {})
            print(f"Cube built {info.get('built')}" + (" (partial)" if info.get("partial") else "")
                  + f": {totals.get('lines', 0):,} lines, {totals.get('spots', 0):,} spots")
    finally:
        manifest.close()
    return 0


def _quantiles(values) -> str:
    values = np.asarray(values, dtype=np.float64)
    return f"median {np.median(values):.2f}, p90 {np.percentile(values, 90):.2f}, max {values.max():.2f}"


def profile(country_id: str, data_dir: str) -> int:
    """`country profile`: where the time and the memory of the counted tiles went, per band and
    stage (the tiles' meta: stages, sink, cpu_seconds, memory, io, threads), and the sums of the
    last run's timeline (logs/samples-*.csv)."""
    from collections import Counter
    folder = folder_of(data_dir, country_id)
    country = Country.from_config(read_state(folder)["config"])
    gib = 2 ** 30
    for band in country.bands:
        paths = sorted(glob.glob(os.path.join(folder, "tiles", band.name, "*.npz")))
        if not paths:
            continue
        metas = [_tile_meta(p) for p in paths]
        walls = np.array([m["seconds"]["prepare"] + m["seconds"]["count"] for m in metas])
        print(f"Band {band.name}: {len(metas)} tiles, {walls.sum() / 3600:.2f} h of tile time; seconds per tile "
              f"{_quantiles(walls)}")
        profiled = [m for m in metas if "stages" in m]
        if len(profiled) < len(metas):
            print(f"  {len(metas) - len(profiled)} tiles counted before their stages were measured")
        if not profiled:
            continue
        stages: Dict[str, List[float]] = {}
        for m in profiled:
            for name, (seconds, cpu) in m["stages"].items():
                total = stages.setdefault(name, [0.0, 0.0])
                total[0] += seconds
                total[1] += cpu
        whole = sum(seconds for seconds, _ in stages.values()) or 1.0
        print(f"  {'Stage':<48} {'Hours':>7} {'Share':>6} {'Cores':>6}")
        for name, (seconds, cpu) in sorted(stages.items(), key=lambda item: -item[1][0]):
            print(f"  {name[:48]:<48} {seconds / 3600:>7.2f} {seconds / whole:>6.1%} "
                  f"{cpu / seconds if seconds else 0.0:>6.2f}")
        sink = np.array([m["sink"] for m in profiled], dtype=np.float64)
        print(f"  the counter (in 'anchor pairs' and after it): {sink[:, 0].sum() / 3600:.2f} h, "
              f"{sink[:, 0].sum() / whole:.1%} of the time")
        claimed = Counter(m["threads"] for m in profiled)
        most = Counter(m.get("threads_max", m["threads"]) for m in profiled)
        print(f"  cores of a tile on average {sum(m['cpu_seconds'] for m in profiled) / whole:.2f}; threads claimed "
              f"{dict(sorted(claimed.items()))}, at most {dict(sorted(most.items()))}")
        print(f"  memory of a tile (GiB): private {_quantiles([m['memory']['private'] / gib for m in profiled])}; "
              f"working set {_quantiles([m['memory']['rss'] / gib for m in profiled])}")
        print(f"  file reads of a tile (MB, through the system's cache) {_quantiles([m['io']['read'] / 1e6 for m in profiled])}; "
              f"writes {_quantiles([m['io']['write'] / 1e6 for m in profiled])}; what reaches the disks: the "
              "last run's timeline below (these see no memory-mapped grid)")
    timelines = sorted(glob.glob(os.path.join(folder, "logs", "samples-*.csv")))
    if timelines:
        _profile_timeline(timelines[-1])
    return 0


def _profile_timeline(path: str):
    """The sums of a run's timeline (_RunSamples)."""
    import csv
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["running_tiles"] != ""]
    if len(rows) < 2:
        return

    def column(key):
        return np.array([float(r[key]) for r in rows])

    workers, running, cores = column("workers"), column("running_tiles"), column("workers_cores")
    busy = workers.max()
    steps = np.diff(column("seconds"), prepend=0.0)
    print(f"The last run's timeline ({os.path.basename(path)}): {column('seconds')[-1] / 60:.1f} min, "
          f"{busy:.0f} workers; machine CPU {column('machine_cpu_pct').mean():.0f} % on average; the workers' cores "
          f"{cores.mean():.1f} on average, {cores.max():.1f} at most; memory used up to "
          f"{column('ram_used_gib').max():.1f} GiB (the workers' private bytes up to "
          f"{column('workers_private_gib').max():.1f} GiB); fewer tiles than workers {np.mean(running < busy):.0%} "
          f"of the time; the machine's disks {np.sum(column('disk_read_mbs') * steps) / 1e3:.1f} GB read and "
          f"{np.sum(column('disk_write_mbs') * steps) / 1e3:.1f} GB written, {column('disk_read_mbs').mean():.0f} and "
          f"{column('disk_write_mbs').mean():.0f} MB/s on average (at most {column('disk_read_mbs').max():.0f} "
          f"and {column('disk_write_mbs').max():.0f})")


def _tile_meta(path: str) -> Dict:
    """A tile file's meta only (an .npz member is read when asked for); ValueError for another VERSION."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"]) if "version" in z.files else None
        if version != countcube.VERSION:
            raise ValueError(f"{path}: a tile file of version {version}, not {countcube.VERSION}: count it again")
        return json.loads(str(z["meta"]))


def _credits(metas: List[Dict], area_spec: str, year: int) -> List[Dict]:
    """The credits of the data the tiles used: merged per layer as search._merged_data does, years
    filled, each once (search._credits), and OSM for an outline from OpenStreetMap."""
    import search
    import sources as src
    saved = list(src.used_data)
    try:
        src.used_data[:] = [entry for meta in metas for entry in meta.get("data") or []]
        merged = search._merged_data()
    finally:
        src.used_data[:] = saved
    credits = [entry["credit"] for entry in search._dated_data(merged, year) if entry.get("credit")]
    if area_spec.startswith("osm:"):
        credits.append(src.OSM_CREDIT.as_dict())
    unique: Dict[str, Dict] = {}
    for credit in credits:
        unique.setdefault(json.dumps(credit, sort_keys=True), credit)
    return list(unique.values())


SHAPES = os.path.join(REPO, "viewer", "dist", "coverage-shapes.json")  # the coverage map's outlines (Natural Earth)
BORDER_NEAR_DEG = 0.01  # a country of SHAPES within this of the outline is its neighbour (_hard_borders)


def _hard_borders(country: Country, folder: str) -> List[str]:
    """The countries (ISO codes, upper case) of the coverage map's outlines (SHAPES) next to the outline
    that no neighbour of the country's source covers (Source.neighbours' countries and regions): across
    their borders lines are counted only where the source's own data reach beyond the outline (partner
    7). The country holding the outline is its own (a source without countries: an elevation file). []
    when the outlines cannot be read."""
    import sources as src
    from shapely.geometry import shape
    try:
        with open(SHAPES, encoding="utf-8") as f:
            features = json.load(f)["features"]
        exact = _read_outline(folder)
        outline = exact.buffer(BORDER_NEAR_DEG)
    except (OSError, ValueError, KeyError):
        return []
    centre = exact.representative_point()
    source = src.SOURCES.get(country.source)
    own = set(source.countries or ()) if source is not None else set()
    covered = set()
    for name in (source.neighbours or ()) if source is not None else ():
        other = src.SOURCES[name]
        covered |= set(other.countries or ()) | set(other.regions or ())
    found = set()
    for feature in features:
        code = feature["properties"]["id"]
        if feature["properties"].get("kind") != "country" or code in own or code in covered or code in found:
            continue
        geometry = shape(feature["geometry"])
        if geometry.intersects(outline) and not geometry.contains(centre):
            found.add(code)
    return sorted(code.upper() for code in found)


# The names of iso3166.tab that read oddly in a sentence (abbreviated, inverted, parenthesised or older), as the
# page names the same countries: the browser's Intl.DisplayNames(["en"], {type: "region"}) (CLDR; checked with
# Node's ICU 76.1 on 2026-11-08). The table's other differences from it stay as tzdata writes them: "St" without
# its full stop and without accents (BL, KN, LC, PM, SH, ST), Hong Kong and Macau without "SAR China", Palestine,
# Pitcairn, and the long names of GS and HM.
COUNTRY_NAMES = {
    "AS": "American Samoa", "BQ": "Caribbean Netherlands", "CD": "Congo - Kinshasa", "CF": "Central African Republic",
    "CG": "Congo - Brazzaville", "CZ": "Czechia", "GB": "United Kingdom", "KP": "North Korea", "KR": "South Korea",
    "MF": "St. Martin", "SX": "Sint Maarten", "SZ": "Eswatini", "TC": "Turks & Caicos Islands",
    "TF": "French Southern Territories", "TL": "Timor-Leste", "TR": "Türkiye", "UM": "U.S. Outlying Islands",
    "VC": "St. Vincent & Grenadines", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "WS": "Samoa"}


@functools.lru_cache(maxsize=1)
def _country_names() -> Dict[str, str]:
    """ISO 3166-1 alpha-2 codes (upper case) -> the usual English names of tzdata's iso3166.tab ("HU"
    Hungary, "UA" Ukraine; the tzdata package, which accounts.country_of_zone reads too), the odd ones
    replaced by COUNTRY_NAMES. The coverage map's outlines carry codes only, and tools/area_rows.py's
    COUNTRIES names only the catalogue's countries, which a hard border lacks by definition. Only
    COUNTRY_NAMES when the table cannot be read."""
    from importlib import resources
    names = {}
    try:
        text = resources.files("tzdata").joinpath("zoneinfo", "iso3166.tab").read_text(encoding="utf-8")
    except (OSError, ModuleNotFoundError):
        text = ""
    for line in text.splitlines():
        if line and not line.startswith("#"):
            code, name = line.split("\t")[:2]
            names[code] = name
    names.update(COUNTRY_NAMES)
    return names


def _names_text(codes: Sequence[str]) -> str:
    """The countries of ISO codes in words, by name: "Hungary and Ukraine", "Austria, Hungary and
    Ukraine" (a code without a name as it is)."""
    names = sorted(_country_names().get(code, code) for code in codes)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _border_notes(country: Country, folder: str) -> List[str]:
    """cube.json's notes on the borders: which lines are counted across them, which borders stay hard.
    The page #layer writes a sentence per neighbour of cube.json's "neighbours" itself (counted from this
    country's data, or the neighbour's own layer shown), so these name none of them; the hard borders by
    the countries' English names (_names_text)."""
    if country.study:
        return [f"Only lines with both anchors inside {country.name} are counted."]
    notes = [f"Lines across the border are counted too: one anchor in {country.name}, the other within the band's "
             f"longest line beyond the border, on the neighbours' data or on {country.name}'s own data there."]
    hard = _hard_borders(country, folder)
    if hard:
        notes.append(f"No data of the neighbours across the border with {_names_text(hard)} (no source here): lines "
                     f"cross it only where {country.name}'s own data reach beyond the border.")
    return notes


def build(country_id: str, data_dir: str, partial: bool = False, say=print) -> int:
    """`country build`: the cube of the layer bands' tiles (countcube.build). Refused while tiles are
    missing unless partial; every tile must have the country's origin and config."""
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    if "origin" not in state:
        say(f"{country_id} has no tiles yet: `findaline.py country run {country_id}`")
        return 1
    manifest = Manifest(folder)
    try:
        rows = {b.name: manifest.rows(b.name) for b in country.bands}
    finally:
        manifest.close()
    paths, metas, missing, total = [], [], 0, 0
    bands_info = []
    for band in country.bands:
        done = 0
        seconds = 0.0
        for r in rows[band.name]:
            path = os.path.join(folder, "tiles", band.name, f"{r['name']}.npz")
            if r["status"] == "done" and os.path.exists(path):
                done += 1
                seconds += r["seconds"] or 0.0
                if band.layer:
                    paths.append(path)
        if band.layer:
            total += len(rows[band.name])
            missing += len(rows[band.name]) - done
        bands_info.append({"name": band.name, "lengths": list(band.lengths), "resolution": band.resolution,
                           "model": band.model, "slope_threshold": band.slope_threshold, "core_m": band.core_m,
                           "layer": band.layer, "tiles": len(rows[band.name]), "done": done,
                           "seconds": round(seconds, 1), "params": form_params(country, band)})
    if not total:
        say(f"{country_id}: the layer bands have no tiles yet")
        return 1
    if missing and not partial:
        say(f"{missing} of the {total} tiles of the layer bands are not done: run `findaline.py country run "
            f"{country_id}`, or build a partial cube with --partial")
        return 1
    origin = [float(v) for v in state["origin"]]
    profile = country.profile.sha256
    neighbours_sha = None
    if not country.study:
        neighbours_path = os.path.join(folder, NEIGHBOURS_FILE)
        if not os.path.exists(neighbours_path):
            say(f"{country_id} has no {NEIGHBOURS_FILE}: `findaline.py country run {country_id}` writes it and counts "
                f"the border tiles with it")
            return 1
        neighbours_sha = _sha256_file(neighbours_path)
    for path in paths:
        try:
            meta = _tile_meta(path)
        except ValueError as e:
            say(str(e))
            return 1
        if meta.get("profile") != profile:
            say(f"{path} was counted with another profile of the layer (its bands, T(L) or rig): count it again "
                f"(`country run {country_id} --redo` counts everything again)")
            return 1
        if meta.get("config") != state["hash"] or [float(v) for v in meta.get("origin", [])] != origin:
            say(f"{path} was counted with another configuration or origin: count it again "
                f"(`country run {country_id} --redo` counts everything again)")
            return 1
        if meta.get("neighbours_sha256") != (neighbours_sha if meta.get("partners") is not None else None):
            say(f"{path} was counted with other territories of the neighbours than {NEIGHBOURS_FILE}'s (or before "
                f"them): `country run {country_id}` counts the border tiles again")
            return 1
        metas.append(meta)
    year = datetime.now().year
    dsm = country.options.get("nmpt", "off") != "off"
    neighbours = [] if country.study else neighbour_cubes(country.source)
    notes = _border_notes(country, folder)
    if not dsm:
        notes.append("The surface model (trees, buildings) was not used: every line counts as not over trees "
                     "or buildings.")
    if missing:
        notes.append(f"Partial: {total - missing} of {total} tiles of the layer bands.")
    info = {"id": country.id, "name": country.name, "crs": state["crs"], "origin": origin, "study": country.study,
            "profile": profile, "neighbours": neighbours, "neighbours_sha256": neighbours_sha,
            "bounds_wgs84": state["bounds_wgs84"], "bands": bands_info, "dsm": dsm,
            "water": country.options.get("water") == "fill", "partial": bool(missing), "config": state["hash"],
            "credits": _credits(metas, country.area, year), "notes": notes}
    out = os.path.join(folder, "cube")
    os.makedirs(out, exist_ok=True)
    with cache.replacing(os.path.join(out, "area.geojson")) as f, \
            open(os.path.join(folder, "area.geojson"), "rb") as source:
        shutil.copyfileobj(source, f)
    cube = countcube.build(paths, out, info)
    say(f"Cube of {country.name} built in {out}" + (" (partial)" if missing else "")
        + f": {cube['totals']['lines']:,} lines, {cube['totals']['spots']:,} spots")
    return 0


def _band_counts(folder: str, rows, band: str, mask: Optional[int]):
    """The line keys and spots of a band's done tiles, the lines and spots of the length bins of
    mask only (None: all)."""
    lines, spots = countcube._Reducer(countcube.sum_keys), countcube._Reducer(countcube.merge_spots)
    for r in rows:
        if r["status"] != "done":
            continue
        counts, _ = countcube.load_tile(os.path.join(folder, "tiles", band, f"{r['name']}.npz"))
        lines.add(counts.line_keys, counts.line_counts)
        spots.add(counts.spot_ids, counts.spot_records)
    keys, n = lines.flush()
    ids, records = spots.flush()
    if keys is None:
        keys, n = np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64)
    if ids is None:
        ids, records = np.zeros(0, dtype=np.int64), np.zeros((0, 2), dtype=np.int64)
    if mask is not None:
        keep = ((keys[:, 0] >> countcube.LENGTH_SHIFT) & mask) != 0
        keys, n = keys[keep], n[keep]
        keep = ((records[:, 0] >> countcube.LENGTH_SHIFT) & mask) != 0
        ids = ids[keep]
    return keys, n, ids


def _per_cell(keys, n, ids, level: int) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Lines and spots per cell of a level: {cell: count} with cell = i << 16 | j."""
    i = (keys[:, 0] >> countcube.COL_SHIFT) // level
    j = ((keys[:, 0] >> countcube.ROW_SHIFT) & countcube.CELL_MASK) // level
    cells, counts = countcube.sum_keys((i << countcube.CELL_BITS) | j, n)
    si, sj = countcube.spot_cells(ids)
    spot_cells, spot_counts = countcube.count_keys(((si // level) << countcube.CELL_BITS) | (sj // level))
    return dict(zip(cells.tolist(), counts.tolist())), dict(zip(spot_cells.tolist(), spot_counts.tolist()))


def _compared_bands(country: Country, control: Optional[str], against: Optional[str]) -> Tuple[Band, Band]:
    """The bands `compare` takes: the control band given, else the country's first band outside the layer
    (Band.layer False); the band given to compare it with, else the layer band whose lengths hold the
    control's. CountryError when there is none: PROFILE has no control band since 2026-11-12, a study area
    or a test may have one."""
    if control is None:
        controls = [b for b in country.bands if not b.layer]
        if not controls:
            raise CountryError(f"{country.id} has no control band (a band outside the layer: its bands "
                               f"{', '.join(b.name for b in country.bands)} are all in the layer): nothing to compare")
        control = controls[0].name
    c_band = country.band(control)
    if against is None:
        lo, hi = c_band.lengths
        holding = [b for b in country.bands
                   if b.layer and b.name != control and b.lengths[0] <= lo and hi <= b.lengths[1]]
        if not holding:
            raise CountryError(f"No layer band of {country.id} holds the lengths of {control} "
                               f"({lo:g}-{hi:g} m): give --against")
        against = holding[0].name
    return c_band, country.band(against)


def compare(country_id: str, data_dir: str, control: Optional[str] = None, against: Optional[str] = None) -> int:
    """`country compare`: the control band against its lengths' part of the other band, per cell of
    1 and 4 km (lines, spots, their ratio, the Spearman correlation of spots per cell over the cells
    with a line of either, zeros included, and "lost": the share of the control's cells with a spot
    where the other has none), with the seconds of both bands' tiles; compare.json. The bands as
    _compared_bands takes them (a country without a control band: a message, exit code 1)."""
    from scipy.stats import spearmanr
    folder = folder_of(data_dir, country_id)
    state = read_state(folder)
    country = Country.from_config(state["config"])
    c_band, a_band = _compared_bands(country, control, against)
    control, against = c_band.name, a_band.name
    lo, hi = c_band.lengths
    try:
        mask = countcube.Filters(length=(lo, hi)).length_mask()
    except ValueError as e:
        print(f"The control band's lengths {lo:g}-{hi:g} m are not on the cube's length edges: {e}")
        return 1
    manifest = Manifest(folder)
    try:
        c_rows, a_rows = manifest.rows(control), manifest.rows(against)
    finally:
        manifest.close()
    for band, rows in ((control, c_rows), (against, a_rows)):
        done = sum(r["status"] == "done" for r in rows)
        if done < len(rows):
            print(f"Note: {done} of {len(rows)} tiles of {band} are done; the comparison covers those")
    c_keys, c_n, c_ids = _band_counts(folder, c_rows, control, None)
    a_keys, a_n, a_ids = _band_counts(folder, a_rows, against, mask)
    c_lines, a_lines = int(c_n.sum()), int(a_n.sum())
    result = {"control": control, "against": against, "lengths": [lo, hi],
              "lines": {"control": c_lines, "against": a_lines, "ratio": a_lines / c_lines if c_lines else None},
              "spots": {"control": int(len(c_ids)), "against": int(len(a_ids)),
                        "ratio": len(a_ids) / len(c_ids) if len(c_ids) else None},
              "seconds": {"control": round(sum(r["seconds"] or 0.0 for r in c_rows if r["status"] == "done"), 1),
                          "against": round(sum(r["seconds"] or 0.0 for r in a_rows if r["status"] == "done"), 1)},
              "tiles": {"control": sum(r["status"] == "done" for r in c_rows),
                        "against": sum(r["status"] == "done" for r in a_rows)},
              "cells": {}}
    for level in (1, 4):
        c_cells_lines, c_cells_spots = _per_cell(c_keys, c_n, c_ids, level)
        a_cells_lines, a_cells_spots = _per_cell(a_keys, a_n, a_ids, level)
        cells = sorted(set(c_cells_lines) | set(a_cells_lines))
        x = np.array([c_cells_spots.get(c, 0) for c in cells], dtype=float)
        y = np.array([a_cells_spots.get(c, 0) for c in cells], dtype=float)
        rho = None
        if len(cells) > 1 and x.std() > 0 and y.std() > 0:
            rho = float(spearmanr(x, y)[0])
        with_spot = [c for c in cells if c_cells_spots.get(c, 0)]
        lost = sum(1 for c in with_spot if not a_cells_spots.get(c, 0))
        result["cells"][str(level)] = {
            "cell_deg": level * countcube.CELL_DEG, "cells": len(cells),
            "control_cells": sum(1 for c in cells if c_cells_lines.get(c, 0)),
            "against_cells": sum(1 for c in cells if a_cells_lines.get(c, 0)),
            "spearman_spots": rho, "lost": lost / len(with_spot) if with_spot else None}
    _write_json(os.path.join(folder, "compare.json"), result)

    def ratio(v):
        return "-" if v is None else f"{v:.3f}"

    print(f"{country.name}: {control} ({c_band.resolution:g} m) against {against} ({a_band.resolution:g} m), "
          f"lengths {lo:g}-{hi:g} m")
    print(f"{'':<14} {control:>14} {against:>14} {'ratio':>8}")
    print(f"{'lines':<14} {c_lines:>14,} {a_lines:>14,} {ratio(result['lines']['ratio']):>8}")
    print(f"{'spots':<14} {len(c_ids):>14,} {len(a_ids):>14,} {ratio(result['spots']['ratio']):>8}")
    print(f"{'seconds':<14} {result['seconds']['control']:>14,.0f} {result['seconds']['against']:>14,.0f}")
    print(f"{'Cell':<9} {'cells':>8} {'Spearman':>9} {'lost':>7}")
    for level, row in result["cells"].items():
        print(f"{row['cell_deg'] * 3600:>4g} sec {row['cells']:>8} {ratio(row['spearman_spots']):>9} {ratio(row['lost']):>7}")
    print(f"Saved to {os.path.join(folder, 'compare.json')}")
    return 0


# --- the command line ----------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="findaline.py country",
                                     description="The country layer: a whole country searched in fixed tiles "
                                                 "that keep only counts, summed into a cube for the app's map.")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run", help="count the tiles still pending (resumable), then build the cube")
    r.add_argument("--processes", type=int, help="worker processes (default: as many as the memory and the "
                                                 "physical cores allow; 0: in this process)")
    r.add_argument("--bands", help="only these bands, e.g. S,M (default: all)")
    r.add_argument("--max-tiles", type=int, help="start at most this many tiles in this run")
    r.add_argument("--redo", action="store_true", help="remove the tiles, the cube and the manifest and count "
                                                       "everything again (needed after a change of the configuration)")
    r.add_argument("--yes", action="store_true", help="do not ask before starting")
    commands.add_parser("status", help="the tiles of each band by status, lines, spots, seconds, errors")
    commands.add_parser("profile", help="where the time and the memory of the counted tiles went, per band and "
                                        "stage, and the last run's timeline")
    b = commands.add_parser("build", help="the cube of the layer bands' tiles")
    b.add_argument("--partial", action="store_true", help="build while tiles are missing")
    c = commands.add_parser("compare", help="a control band (outside the layer) against the same lengths of a layer "
                                            "band; the layer's profile has none since 2026-11-12, a study area may")
    c.add_argument("--control", help="the control band (default: the country's first band outside the layer)")
    c.add_argument("--against", help="the band it is compared with (default: the layer band holding the control's "
                                     "lengths)")
    w = commands.add_parser("worker", help="a worker process of a run (started by run)")
    w.add_argument("--slot", type=int, required=True, help="the worker's number")
    for sub in commands.choices.values():
        sub.add_argument("id", help=f"the country ({', '.join(sorted(COUNTRIES))})")
        sub.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    args = parser.parse_args(argv)
    data_dir = cache.data_dir(args.data_dir)
    try:
        if args.command == "run":
            if args.processes is not None and args.processes < 0:
                parser.error("--processes must be 0 or more")
            bands = [s.strip() for s in args.bands.split(",") if s.strip()] if args.bands else None
            return run(args.id, data_dir, args.processes, bands, args.max_tiles, args.redo, args.yes)
        if args.command == "status":
            return status(args.id, data_dir)
        if args.command == "profile":
            return profile(args.id, data_dir)
        if args.command == "build":
            return build(args.id, data_dir, args.partial)
        if args.command == "compare":
            return compare(args.id, data_dir, args.control, args.against)
        return worker(args.id, data_dir, args.slot)
    except CountryError as e:
        print(e)
        return 1
