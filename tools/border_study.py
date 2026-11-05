"""The border study (docs/roadmap.md, "Country layer", "Lines across a border"): how many lines the
country layer loses at the border of two countries, where its outline is a hard limit for both
anchors, measured before a layer of several countries is designed (the user's question of
2026-11-04).

A place is a box across the border of two countries A and B (each a source and an outline). Each band
of a country's layer (country.COUNTRIES, Slovakia's by default: its bands, T(L), rig and options) is
searched once over the box grown by the band's longest line, with the data of one source (the
primary; the other's national data fill its side as a neighbour's fill a border gap,
sources.filling.fill_from_neighbours), in the layer's fixed tiles and count mode (search.count_tile,
as country.TileWork counts a tile). Only the lines whose first anchor lies in the box (its bounds in
the primary's CRS) are counted, so none misses a partner at the grown box's edge. Each line goes by
the outlines holding its anchors into one of CLASSES, each class into a countcube.TileCounter of its
own: both anchors in A (what A's layer counts), both in B (what B's would count), one in each (what
both lose today), any other (an anchor in neither outline or in both).

    uv run python tools/border_study.py run tatry [--primary geoportal] [--bands S,M,L] [--resampling cubic]
                                                  --out <folder> [--data-dir D]
    uv run python tools/border_study.py exposure slovakia --neighbours Polska=osm:Polska,... --out <folder> [--data-dir D]
    uv run python tools/border_study.py report --out <folder>
    uv run python tools/border_study.py boxes [--reach 5000] [--write <file.md>]

run counts a place into <out>/<place>-<primary>/, tile by tile (a tile whose meta exists is done, so a
run resumes; a changed definition is refused unless --reset). --resampling: the neighbour's data
reprojected onto the primary's grid with that method instead of the mosaic's own choice
(sources.filling.NEIGHBOUR_RESAMPLING), into <out>/<place>-<primary>-<method>/: the report compares
each run with the run of the other primary, whose grid holds that side's data as they are
(docs/country-precompute/contract.md, section 6, step 0). exposure reads a built cube
(countries/<id>/cube) and counts its lines and spots whose first anchor's 1 km cell lies within reach
of each neighbour's border (a bin's longest line plus half a cell's diagonal): the most a layer
across borders could add there. report writes study.json, study.md and pictures/<run>.png: per band
and length bin the lines of each class, the share across the border, the same within reach of the
border and per km of it, the spots of each class, where each side's data came from, the agreement of
a place's two primaries (spots across the border matched within TOLERANCE clusters after
reprojection), the resampling methods of a place (the spots of the resampled side and those across
the border against the other primary's, with each run's seconds, CPU seconds and memory), and with
exposure.json the estimate for its cube (the place's lines across the
border per line of A within reach of the border, times the cube's lines within reach of B's border).
boxes lists every declared pair of the catalogue (Source.neighbours) with the share of the neighbour's
land along the border that lies inside the neighbour's rough boxes: outside them a border gap never
asks the neighbour and gets the fallback's data (offline: the coverage map's outlines).
"""
import argparse
import dataclasses
import gc
import json
import math
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import psutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import cache  # noqa: E402
import countcube as cc  # noqa: E402
import country  # noqa: E402

CLASSES = ("aa", "bb", "ab", "other")  # both anchors in A, both in B, one in each, any other
PART_COLUMNS = ("a1", "a2") + cc.RECORD_COLUMNS  # what a TileCounter reads of a part
CELL_HALF_DIAGONAL = cc.CELL_M / math.sqrt(2)  # a line's first anchor lies this far from its cell's centre at most
BORDER_SNAP_M = 200.0  # a piece of one outline within this of the other's is their common border
TOLERANCE = 1  # clusters (CLUSTER_M) an end of a spot may lie off its match after reprojection
SEGMENT_M = 200.0  # edges densified to this before an outline or a box changes its CRS


@dataclass(frozen=True)
class Side:
    """A country of a place: its source (the primary's data, or the neighbour's) and its outline."""
    source: str
    area: str  # an area spec of area.from_spec: osm:<name> or a file
    name: str


@dataclass(frozen=True)
class Place:
    """A box across the border of A and B: the first anchors counted lie in it."""
    id: str
    name: str
    box: str  # S,W,N,E in degrees
    a: Side
    b: Side
    border: str  # what the border follows there (the report's note)


SLOVAKIA = Side("slovakia", "osm:Slovensko", "Slovakia")
POLAND = Side("geoportal", "osm:Polska", "Poland")
SAXONY = Side("saxony", "osm:Sachsen", "Saxony")
CZECHIA = Side("czechia", "osm:Česko", "Czechia")
BAVARIA = Side("bavaria", "osm:Bayern", "Bavaria")
AUSTRIA = Side("austria", "osm:Österreich", "Austria")
SOUTH_TYROL = Side("south_tyrol", "osm:Südtirol", "South Tyrol")
PLACES = {p.id: p for p in (
    Place("tatry", "Tatras: Kasprowy Wierch, Rysy, Gerlach", "49.16,19.98,49.25,20.20", SLOVAKIA, POLAND,
          "the main ridge"),
    Place("pieniny", "Pieniny: the Dunajec gorge", "49.39,20.36,49.44,20.48", SLOVAKIA, POLAND,
          "the river in the gorge"),
    # The places of step 0 (the resampling of the neighbour's data): other pairs of grids
    Place("elbe", "Elbe Sandstone: Schmilka, Hřensko, Großer Winterberg", "50.84,14.19,50.92,14.34", SAXONY, CZECHIA,
          "the Elbe in its canyon, then the sandstone plateau"),
    Place("wetterstein", "Wetterstein: Zugspitze, Hochwanner, Dreitorspitze", "47.37,10.94,47.44,11.18", BAVARIA,
          AUSTRIA, "the main ridge"),
    # A neighbour coarser than the grid: South Tyrol's 2.5 m data on Austria's grid
    Place("zillertal", "Zillertal Alps: Hochfeiler, Schwarzenstein, Großer Löffler", "46.95,11.70,47.04,11.92", AUSTRIA,
          SOUTH_TYROL, "the main ridge"),
)}


def box_polygon(text: str):
    """The WGS84 polygon of a box S,W,N,E."""
    from shapely.geometry import box
    south, west, north, east = map(float, text.split(","))
    return box(west, south, east, north)


def _project(geometry, src_crs: str, dst_crs: str):
    """A geometry in another CRS, its edges densified first (in the source CRS's units)."""
    import area as ar
    import shapely
    step = SEGMENT_M if src_crs != "EPSG:4326" else SEGMENT_M / 111_000
    return ar.project(shapely.segmentize(geometry, step), src_crs, dst_crs)


def counted_box(place: Place, crs: str) -> Tuple[float, float, float, float]:
    """The bounds of the place's box in crs: the first anchors counted lie in it."""
    return tuple(float(v) for v in _project(box_polygon(place.box), "EPSG:4326", crs).bounds)


def study_origin(counted: Tuple[float, ...], config: country.Country) -> Tuple[float, float]:
    """One origin for every band of a run (spots merge over the bands): the counted box grown by
    twice the longest line of the layer, floored to countcube.ALIGN_M, below every anchor."""
    grow = 2 * max(b.lengths[1] for b in config.bands)
    return cc.origin_of((counted[0] - grow, counted[1] - grow, counted[2], counted[3]))


def line_classes(k1: np.ndarray, k2: np.ndarray) -> np.ndarray:
    """The index in CLASSES of lines by the codes of their anchors (1: in A only, 2: in B only;
    0 and 3, in neither or both: other)."""
    out = np.full(len(k1), 3, dtype=np.int8)
    out[(k1 == 1) & (k2 == 1)] = 0
    out[(k1 == 2) & (k2 == 2)] = 1
    out[((k1 == 1) & (k2 == 2)) | ((k1 == 2) & (k2 == 1))] = 2
    return out


class BorderSink:
    """The sink of a tile's count: each line, by the outlines holding its anchors (masks of A and B
    on the tile's grid, as the area mask is burned), into the countcube.TileCounter of its class."""

    def __init__(self, grid, origin: Tuple[float, float], core: Tuple[float, float, float, float],
                 lengths: Tuple[float, float], last: bool, inside_a: np.ndarray, inside_b: np.ndarray):
        self.code = inside_a.astype(np.uint8) | (inside_b.astype(np.uint8) << 1)
        self.counters = {name: cc.TileCounter(grid, origin, core, lengths, last) for name in CLASSES}

    def __call__(self, part) -> None:
        c = part.columns
        a1, a2 = np.asarray(c["a1"]), np.asarray(c["a2"])
        if not len(a1):
            return
        classes = line_classes(self.code[a1[:, 0], a1[:, 1]], self.code[a2[:, 0], a2[:, 1]])
        for k, name in enumerate(CLASSES):
            chosen = classes == k
            n = int(np.count_nonzero(chosen))
            if n == len(a1):
                self.counters[name](part)
            elif n:
                self.counters[name](SimpleNamespace(columns={key: np.asarray(c[key])[chosen] for key in PART_COLUMNS}))


def fill_check(data, inside: Dict[str, np.ndarray], window: Tuple[slice, slice]) -> Dict[str, Dict[str, int]]:
    """Where the heights of each side's pixels in the counted window came from: the primary's own
    data, a neighbour's (data.joined), a fallback (data.filled), none (NaN after the filling)."""
    rows, cols = window
    z = np.asarray(data.elevation[rows, cols])
    none = np.isnan(z)
    joined = np.asarray(data.joined[rows, cols], dtype=bool) if data.joined is not None else np.zeros(z.shape, bool)
    filled = np.asarray(data.filled[rows, cols], dtype=bool) if data.filled is not None else np.zeros(z.shape, bool)
    out = {}
    for side, mask in inside.items():
        m = np.asarray(mask[rows, cols], dtype=bool)
        neighbour, fallback, missing = m & joined, m & filled & ~joined, m & none
        out[side] = {"pixels": int(m.sum()), "neighbour": int(neighbour.sum()), "fallback": int(fallback.sum()),
                     "none": int(missing.sum()), "own": int((m & ~joined & ~filled & ~none).sum())}
    return out


class _Events:
    """The plan's events printed (as country._print_event), the lines naming filled gaps kept."""

    def __init__(self):
        self.filled: List[str] = []

    def __call__(self, kind: str, text: str):
        text = str(text)
        if text.startswith("Filled "):
            self.filled.append(text)
        print(("WARNING: " if kind == "warning" else "") + text, flush=True)


def _band_plan(config: country.Country, band: country.Band, primary: str, area_path: str, data_dir: str,
               work: str, emit):
    """A band's plan over an area file with the primary's data (country.band_plan's fields)."""
    import search
    from params import SearchParams
    values = country.form_params(dataclasses.replace(config, source=primary), band)
    values["area"] = area_path
    for key in ("elevation_file", "surface_file"):
        if config.options.get(key):
            values[key] = config.options[key]
    return search.plan_search(SearchParams(**values), search.Paths(data_dir, work), emit, tiled=False)


def _write_json(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)


def _read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def outline_of(side: Side, cache_dir: str):
    """A side's outline (WGS84), as country.py fetches a country's (area.from_spec)."""
    import area as ar
    return ar.from_spec(side.area, 0.0, None, cache_dir).geometry


def run_folder(out: str, place_id: str, primary: str, resampling: Optional[str] = None) -> str:
    """The folder of a run: <out>/<place>-<primary>, with -<method> for a resampling method."""
    return os.path.join(out, f"{place_id}-{primary}" + (f"-{resampling}" if resampling else ""))


class _Peak(threading.Thread):
    """This process's largest working set and private bytes while a tile is counted (as
    country._MemorySampler samples a worker's)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.process, self.halt, self.rss, self.private = psutil.Process(), threading.Event(), 0, 0

    def sample(self):
        try:
            memory = self.process.memory_info()
        except psutil.Error:
            return
        self.rss, self.private = max(self.rss, int(memory.rss)), max(self.private, country._private(memory))

    def run(self):
        while not self.halt.is_set():
            self.sample()
            self.halt.wait(country.TILE_SAMPLE_SECONDS)

    def stop(self) -> Dict[str, int]:
        self.halt.set()
        self.join()
        self.sample()
        return {"rss": self.rss, "private": self.private}


def run_place(place: Place, primary: str, out: str, data_dir: str, bands: Optional[Sequence[str]] = None,
              config: Optional[country.Country] = None, threads: Optional[int] = None, reset: bool = False,
              say=print, resampling: Optional[str] = None) -> str:
    """Count a place's bands with the primary's data into its folder (run_folder); returns the
    folder. A tile whose meta exists is skipped; a run of another definition is refused unless
    reset. resampling: the neighbour's data reprojected with that method of
    sources.mosaic.RESAMPLINGS (None: the mosaic's own choice)."""
    import sources.filling as filling
    import sources.mosaic as mosaic
    if resampling is not None and resampling not in mosaic.RESAMPLINGS:
        raise ValueError(f"the resampling must be one of {', '.join(mosaic.RESAMPLINGS)}")
    before = filling.NEIGHBOUR_RESAMPLING
    filling.NEIGHBOUR_RESAMPLING = resampling
    try:
        return _run_place(place, primary, out, data_dir, bands, config, threads, reset, say, resampling)
    finally:
        filling.NEIGHBOUR_RESAMPLING = before


def _run_place(place: Place, primary: str, out: str, data_dir: str, bands: Optional[Sequence[str]],
               config: Optional[country.Country], threads: Optional[int], reset: bool, say,
               resampling: Optional[str]) -> str:
    import area as ar
    import search
    import sources as src
    from shapely.geometry import box, mapping
    config = config or country.COUNTRIES["slovakia"]
    sides = {"a": place.a, "b": place.b}
    if primary not in (place.a.source, place.b.source):
        raise ValueError(f"the primary must be {place.a.source} or {place.b.source}")
    names = list(bands) if bands else [b.name for b in config.bands if b.layer]
    folder = run_folder(out, place.id, primary, resampling)
    cache_dir = os.path.join(data_dir, "cache")
    south, west, north, east = map(float, place.box.split(","))
    lat, lon = (south + north) / 2, (west + east) / 2
    # The working CRS as plan_search chooses it (also for --source files, which no catalogue holds)
    source, _ = src.choose_source(primary, lat, lon, cache_dir, config.options.get("elevation_file"),
                                  config.options.get("surface_file"))
    crs = source.working_crs(lat, lon)
    counted = counted_box(place, crs)
    definition = {"place": dataclasses.asdict(place), "primary": primary, "crs": crs, "counted": list(counted),
                  "origin": list(study_origin(counted, config)), "config": config.config()}
    if resampling:  # a run without one keeps the definition of the runs before the option
        definition["resampling"] = resampling
    path = os.path.join(folder, "study.json")
    if os.path.exists(path) and _read_json(path)["definition"] != definition:
        if not reset:
            raise ValueError(f"{folder} was counted with another definition: --reset removes it")
        say(f"--reset: {folder} is removed")
        shutil.rmtree(folder)
    origin = tuple(definition["origin"])
    outlines = {k: outline_of(s, cache_dir) for k, s in sides.items()}
    state = _read_json(path) if os.path.exists(path) else {"definition": definition, "bands": {}}
    _write_json(path, state)
    for name in names:
        band = config.band(name)
        last = float(band.lengths[1]) >= config.last_edge
        events = _Events()
        # The area: the counted box grown by the longest line and a pixel's slope, so every partner of
        # a first anchor in it is an anchor too (the plan's grid adds the terrain margin around it)
        grow = band.lengths[1] + 2 * band.resolution
        grown = box(counted[0] - grow, counted[1] - grow, counted[2] + grow, counted[3] + grow)
        area_path = os.path.join(folder, f"area-{band.name}.geojson")
        _write_json(area_path, {"type": "Feature", "properties": {"band": band.name},
                                "geometry": mapping(_project(grown, crs, "EPSG:4326"))})
        work = os.path.join(data_dir, "work", "border-" + os.path.basename(folder))
        plan = _band_plan(config, band, primary, area_path, data_dir, work, events)
        clipped = {k: g.intersection(_project(grown.buffer(10 * band.resolution), crs, "EPSG:4326"))
                   for k, g in outlines.items()}
        table = country.tension_table(config, band, plan)
        tiles = [t for t in search.fixed_tiles(plan, band.core_m)
                 if t.core[0] < counted[2] and counted[0] < t.core[2] and t.core[1] < counted[3] and counted[1] < t.core[3]]
        state["bands"][band.name] = {"tiles": len(tiles), "lengths": list(band.lengths),
                                     "resolution": band.resolution, "km2": round(box(*counted).area / 1e6, 2)}
        _write_json(path, state)
        for k, tile in enumerate(tiles):
            meta_path = os.path.join(folder, "tiles", band.name, f"{tile.name}.json")
            if os.path.exists(meta_path):
                continue
            core = (max(tile.core[0], counted[0]), max(tile.core[1], counted[1]),
                    min(tile.core[2], counted[2]), min(tile.core[3], counted[3]))
            grid = tile.grid
            tile_work = os.path.join(work, f"{band.name}-{tile.name}")
            shutil.rmtree(tile_work, ignore_errors=True)
            os.makedirs(tile_work, exist_ok=True)
            params = plan.params.model_copy(update={"threads": threads}) if threads else plan.params
            # border=True for every tile: the counted box is no country, the other side's data come
            # from the neighbour wherever the primary's data end (country.TileWork asks it at the outline)
            tile_plan = dataclasses.replace(plan, params=params, grid=grid, paths=search.Paths(data_dir, tile_work),
                                            tiles=None, funnel={}, tile_label=f"{band.name} {tile.name} · ",
                                            search_grid=plan.grid, border=True)
            say(f"\n--- {os.path.basename(folder)}, band {band.name}, tile {k + 1}/{len(tiles)} {tile.name} "
                f"({grid.width} x {grid.height} px) ---")
            src.used_data.clear()
            events.filled = []
            peak = _Peak()
            peak.start()
            t0, c0 = time.time(), time.process_time()
            data = search.prepare_data(tile_plan, statistics=False, shore="none", strips=True)
            t1, c1 = time.time(), time.process_time()
            inside = {k2: ar.Polygon(g).mask(grid) if not g.is_empty else np.zeros((grid.height, grid.width), bool)
                      for k2, g in clipped.items()}
            sink = BorderSink(grid, origin, core, band.lengths, last, inside["a"], inside["b"])
            funnel = search.count_tile(tile_plan, data, core, sink, table)
            t2, c2 = time.time(), time.process_time()
            memory = peak.stop()
            fill = fill_check(data, inside, search._core_window(grid, core))
            del data
            gc.collect()  # close the memory-mapped grids before their folder is removed (Windows)
            shutil.rmtree(tile_work, ignore_errors=True)
            results = {name2: counter.result() for name2, counter in sink.counters.items()}
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            for name2, counts in results.items():
                cc.save_tile(os.path.join(folder, "tiles", band.name, f"{tile.name}.{name2}.npz"), counts,
                             {"band": band.name, "tile": tile.name, "class": name2})
            meta = {"band": band.name, "tile": tile.name, "core": list(core),
                    "grid": {"width": grid.width, "height": grid.height},
                    "lines": {n2: r.lines for n2, r in results.items()},
                    "spots": {n2: int(len(r.spot_ids)) for n2, r in results.items()},
                    "dropped": results["aa"].dropped, "fill": fill, "filled": events.filled, "funnel": dict(funnel),
                    "seconds": {"prepare": round(t1 - t0, 2), "count": round(t2 - t1, 2)},
                    "cpu_seconds": {"prepare": round(c1 - c0, 2), "count": round(c2 - c1, 2)}, "memory": memory,
                    "data": json.loads(json.dumps(src.used_data))}
            _write_json(meta_path, meta)
            lines = meta["lines"]
            say(f"{band.name} {tile.name}: A-A {lines['aa']:,}, B-B {lines['bb']:,}, A-B {lines['ab']:,}, "
                f"other {lines['other']:,} lines; {t2 - t0:.0f} s")
        shutil.rmtree(work, ignore_errors=True)
    return folder


# --- what a cube could gain ----------------------------------------------------------------------

def _bins() -> List[Tuple[int, int]]:
    edges = cc.LENGTH_EDGES
    return [(edges[k], edges[k + 1]) for k in range(cc.LENGTH_BINS)]


def _cell_centres(keys: np.ndarray, origin: Tuple[float, float]) -> np.ndarray:
    i, j = keys >> cc.COL_SHIFT, (keys >> cc.ROW_SHIFT) & cc.CELL_MASK
    return np.column_stack([origin[0] + (i + 0.5) * cc.CELL_M, origin[1] + (j + 0.5) * cc.CELL_M])


def border_pieces(own, others: Dict[str, object]) -> Dict[str, object]:
    """The pieces of own's boundary (a geometry in a metric CRS) within BORDER_SNAP_M of each other
    outline: their common borders."""
    return {name: own.boundary.intersection(other.buffer(BORDER_SNAP_M)) for name, other in others.items()}


def near_border(keys: np.ndarray, counts: np.ndarray, origin: Tuple[float, float],
                pieces: Dict[str, object]) -> Dict:
    """The counts of keys (lines or spots) per length bin, and of those whose cell's centre lies within
    reach of a border piece (the bin's longest line plus CELL_HALF_DIAGONAL), each to its nearest piece."""
    import shapely
    unique, inverse = np.unique(keys >> cc.ROW_SHIFT, return_inverse=True)
    inverse = inverse.ravel()
    centres = _cell_centres(unique << cc.ROW_SHIFT, origin)
    points = shapely.points(centres)
    names = list(pieces)
    distance = np.full((len(names), len(unique)), np.inf)
    for k, name in enumerate(names):
        if not pieces[name].is_empty:
            distance[k] = shapely.distance(pieces[name], points)
    nearest = distance.argmin(axis=0) if names else np.zeros(len(unique), int)
    lowest = distance.min(axis=0) if names else np.full(len(unique), np.inf)
    lengths = (keys >> cc.LENGTH_SHIFT) & ((1 << cc.LENGTH_BINS) - 1)
    out = []
    for k, (lo, hi) in enumerate(_bins()):
        in_bin = (lengths & (1 << k)) != 0
        reach = hi + CELL_HALF_DIAGONAL
        close = in_bin & (lowest[inverse] <= reach)
        entry = {"lengths": [lo, hi], "reach": round(reach), "all": int(counts[in_bin].sum()),
                 "near": {name: int(counts[close & (nearest[inverse] == n)].sum()) for n, name in enumerate(names)}}
        out.append(entry)
    # Each key once, within the reach of its longest length bin (a spot may have lines of several)
    longest = np.frexp(np.maximum(lengths, 1).astype(np.float64))[1] - 1
    reach = np.array([hi for _, hi in _bins()], dtype=np.float64)[longest] + CELL_HALF_DIAGONAL
    close = lowest[inverse] <= reach
    return {"bins": out, "total": int(counts.sum()),
            "near_total": {name: int(counts[close & (nearest[inverse] == n)].sum()) for n, name in enumerate(names)}}


def spot_keys(ids: np.ndarray, records: np.ndarray) -> np.ndarray:
    """Spots as keys of their cell (that of the first cluster) and record, as the cube counts them."""
    i, j = cc.spot_cells(ids)
    return cc.pack_keys(i, j, records)


def exposure(cube_dir: str, neighbours: Dict[str, str], cache_dir: str) -> Dict:
    """A cube's lines and spots within reach of each neighbour's border (border_pieces, near_border)."""
    import area as ar
    cube = cc.Cube(cube_dir)
    own = _project(cube.outline(), "EPSG:4326", cube.crs)
    others = {name: _project(ar.from_spec(spec, 0.0, None, cache_dir).geometry, "EPSG:4326", cube.crs)
              for name, spec in neighbours.items()}
    pieces = border_pieces(own, others)
    with open(os.path.join(cube_dir, "area.geojson"), encoding="utf-8") as f:
        own_spec = (json.load(f).get("properties") or {}).get("area")
    result = {"cube": cube.info.get("id"), "name": cube.info.get("name"), "area": own_spec, "crs": cube.crs,
              "neighbours": dict(neighbours),
              "border_km": {n: round(p.length / 1000, 1) for n, p in pieces.items()},
              "boundary_km": round(own.boundary.length / 1000, 1), "km2": round(own.area / 1e6)}
    for mode in ("lines", "spots"):
        rows = cube.array(mode, 1)
        result[mode] = near_border(rows[:, 0], rows[:, 1], cube.origin, pieces)
    return result


# --- the report ----------------------------------------------------------------------------------

def _class_tiles(folder: str, band: str, name: str) -> List[str]:
    """The tile files of a class of a band's done tiles."""
    tiles = os.path.join(folder, "tiles", band)
    if not os.path.isdir(tiles):
        return []
    done = [f[:-5] for f in sorted(os.listdir(tiles)) if f.endswith(".json")]
    return [os.path.join(tiles, f"{t}.{name}.npz") for t in done]


def _merged(paths: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Line keys and counts summed, spot ids and records merged, over tile files."""
    loaded = [cc.load_tile(p)[0] for p in paths]
    if not loaded:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, empty, empty
    keys, counts = cc.sum_keys(np.concatenate([c.line_keys for c in loaded]),
                               np.concatenate([c.line_counts for c in loaded]))
    ids, records = cc.merge_spots(np.concatenate([c.spot_ids for c in loaded]),
                                  np.concatenate([c.spot_records for c in loaded]))
    return keys, counts, ids, records


def _length_counts(keys: np.ndarray, counts: np.ndarray) -> List[int]:
    lengths = (keys >> cc.LENGTH_SHIFT) & ((1 << cc.LENGTH_BINS) - 1)
    return [int(counts[(lengths & (1 << k)) != 0].sum()) for k in range(cc.LENGTH_BINS)]


def spot_points(ids: np.ndarray, origin: Tuple[float, float]) -> Tuple[np.ndarray, ...]:
    """The centres (x1, y1, x2, y2) of both clusters of spots."""
    ids = np.asarray(ids, dtype=np.int64)
    px = ids >> cc.SPOT_CX_SHIFT
    py = (ids >> cc.SPOT_CY_SHIFT) & ((1 << cc.SPOT_CY_BITS) - 1)
    qx, qy = px + ((ids >> 8) & 0xFF), py + (ids & 0xFF) - 128
    half = cc.CLUSTER_M / 2
    return (origin[0] + px * cc.CLUSTER_M + half, origin[1] + py * cc.CLUSTER_M + half,
            origin[0] + qx * cc.CLUSTER_M + half, origin[1] + qy * cc.CLUSTER_M + half)


def reframed_spots(ids: np.ndarray, origin: Tuple[float, float], crs: str, to_origin: Tuple[float, float],
                   to_crs: str, within=None) -> np.ndarray:
    """Spots of one run as spot ids of another run's CRS and origin (their clusters' centres moved),
    only those with both ends inside within (a WGS84 geometry) when given."""
    import shapely
    from pyproj import Transformer
    x1, y1, x2, y2 = spot_points(ids, origin)
    if within is not None:
        back = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon1, lat1 = back.transform(x1, y1)
        lon2, lat2 = back.transform(x2, y2)
        keep = shapely.contains_xy(within, lon1, lat1) & shapely.contains_xy(within, lon2, lat2)
        x1, y1, x2, y2 = x1[keep], y1[keep], x2[keep], y2[keep]
    if crs != to_crs:
        move = Transformer.from_crs(crs, to_crs, always_xy=True)
        x1, y1 = move.transform(x1, y1)
        x2, y2 = move.transform(x2, y2)
    return cc.spot_ids(np.asarray(x1), np.asarray(y1), np.asarray(x2), np.asarray(y2), to_origin)


def _shrunk_box(place: Dict, metres: float):
    """The place's box (WGS84) shrunk by about metres on every side."""
    south, west, north, east = map(float, place["box"].split(","))
    dlat = metres / 111_000
    dlon = dlat / math.cos(math.radians((south + north) / 2))
    from shapely.geometry import box
    return box(west + dlon, south + dlat, east - dlon, north - dlat)


def analyse_run(folder: str, cache_dir: str) -> Dict:
    """A run's classes per band and length bin, near the border and per km of it, its spots, the data
    of each side and the seconds."""
    from shapely.geometry import box
    state = _read_json(os.path.join(folder, "study.json"))
    d = state["definition"]
    place = Place(**{**d["place"], "a": Side(**d["place"]["a"]), "b": Side(**d["place"]["b"])})
    crs, origin, counted = d["crs"], tuple(d["origin"]), tuple(d["counted"])
    outlines = {k: _project(outline_of(s, cache_dir), "EPSG:4326", crs) for k, s in (("a", place.a), ("b", place.b))}
    region = box(*counted)
    whole = border_pieces(outlines["a"], {"b": outlines["b"]})["b"]
    # The border within reach of the box: a cell at the box's edge may lie nearer the border outside it
    piece = whole.intersection(region.buffer(cc.LENGTH_EDGES[-1] + CELL_HALF_DIAGONAL))
    border_km = whole.intersection(region).length / 1000
    result = {"run": os.path.basename(folder), "place": place.id, "name": place.name, "primary": d["primary"],
              "resampling": d.get("resampling"), "a": place.a.name, "b": place.b.name, "a_source": place.a.source, "a_area": place.a.area,
              "b_area": place.b.area, "border": place.border, "crs": crs, "counted": list(counted),
              "km2": round(region.area / 1e6, 1), "border_km": round(border_km, 1),
              "km2_a": round(outlines["a"].intersection(region).area / 1e6, 1),
              "km2_b": round(outlines["b"].intersection(region).area / 1e6, 1), "bands": {}, "spots": {}}
    every = {name: [] for name in CLASSES}
    for band, info in state.get("bands", {}).items():
        metas = []
        tiles = os.path.join(folder, "tiles", band)
        for f in sorted(os.listdir(tiles)) if os.path.isdir(tiles) else []:
            if f.endswith(".json"):
                metas.append(_read_json(os.path.join(tiles, f)))
        entry = {"lengths": info["lengths"], "resolution": info["resolution"], "tiles": info["tiles"],
                 "done": len(metas), "seconds": round(sum(m["seconds"]["prepare"] + m["seconds"]["count"]
                                                          for m in metas), 1)}
        timed = [m for m in metas if "cpu_seconds" in m]  # the tiles counted since the option of the resampling
        if timed and len(timed) == len(metas):
            entry["prepare_seconds"] = round(sum(m["seconds"]["prepare"] for m in metas), 1)
            entry["cpu_seconds"] = round(sum(m["cpu_seconds"]["prepare"] + m["cpu_seconds"]["count"] for m in metas), 1)
            entry["prepare_cpu_seconds"] = round(sum(m["cpu_seconds"]["prepare"] for m in metas), 1)
            entry["memory"] = {k: max(m["memory"][k] for m in metas) for k in ("rss", "private")}
        fill = {side: {k: sum(m["fill"][side][k] for m in metas) for k in ("pixels", "own", "neighbour", "fallback", "none")}
                for side in ("a", "b")}
        entry["fill"] = fill
        classes = {}
        for name in CLASSES:
            paths = _class_tiles(folder, band, name)
            every[name] += paths
            keys, counts, ids, records = _merged(paths)
            near = near_border(keys, counts, origin, {"b": piece})["bins"] if len(keys) else None
            classes[name] = {"lines": int(counts.sum()), "spots": int(len(ids)),
                             "bins": _length_counts(keys, counts),
                             "near": [b["near"]["b"] for b in near] if near else [0] * cc.LENGTH_BINS}
        entry["classes"] = classes
        result["bands"][band] = entry
    result["spots_near"] = {}
    for name in CLASSES:
        _, _, ids, records = _merged(every[name])
        result["spots"][name] = int(len(ids))
        result["spots_near"][name] = (near_border(spot_keys(ids, records), np.ones(len(ids), dtype=np.int64), origin,
                                                  {"b": piece})["near_total"]["b"] if len(ids) else 0)
    return result


def check_against_cube(folder: str, cube_dir: str) -> Optional[Dict]:
    """A run's lines of A against the cube of A (counted with the same bands and data) in the cells
    whose whole square lies deeper in the counted box than each bin's longest line (nearer its edge
    the box misses partners the cube has): the lines per length bin of both; None in another CRS or
    on cells of another lattice."""
    state = _read_json(os.path.join(folder, "study.json"))
    d = state["definition"]
    cube = cc.Cube(cube_dir)
    offset = ((d["origin"][0] - cube.origin[0]) / cc.CELL_M, (d["origin"][1] - cube.origin[1]) / cc.CELL_M)
    if cube.crs != d["crs"] or any(abs(v - round(v)) > 1e-9 for v in offset):
        return None
    di, dj = int(round(offset[0])), int(round(offset[1]))
    rows = cube.array("lines", 1)
    cube_keys, cube_counts = rows[:, 0], rows[:, 1]
    left, bottom, right, top = d["counted"]
    out = []
    for band in state.get("bands", {}):
        keys, counts, _, _ = _merged(_class_tiles(folder, band, "aa"))
        for k, (lo, hi) in enumerate(_bins()):
            lengths = state["bands"][band]["lengths"]
            if not (lengths[0] <= lo and hi <= lengths[1]):
                continue
            # the cells (of the run's origin) at least hi metres inside the box on every side
            i0 = math.ceil((left + hi - d["origin"][0]) / cc.CELL_M)
            i1 = math.floor((right - hi - d["origin"][0]) / cc.CELL_M)  # exclusive
            j0 = math.ceil((bottom + hi - d["origin"][1]) / cc.CELL_M)
            j1 = math.floor((top - hi - d["origin"][1]) / cc.CELL_M)
            if i0 >= i1 or j0 >= j1:
                continue

            def inside(ks, shift_i, shift_j):
                i, j = (ks >> cc.COL_SHIFT) - shift_i, ((ks >> cc.ROW_SHIFT) & cc.CELL_MASK) - shift_j
                bit = ((ks >> cc.LENGTH_SHIFT) & (1 << k)) != 0
                return bit & (i >= i0) & (i < i1) & (j >= j0) & (j < j1)

            ours = int(counts[inside(keys, 0, 0)].sum())
            theirs = int(cube_counts[inside(cube_keys, di, dj)].sum())
            out.append({"band": band, "lengths": [lo, hi], "cells": (i1 - i0) * (j1 - j0), "run": ours, "cube": theirs})
    return {"cube": cube.info.get("id"), "bins": out}


def agreement(run_a: str, run_b: str, band: str, name: str = "ab") -> Optional[Dict]:
    """Two runs of one place with different primaries: the spots of a class (across the border,
    unless named) of each with both ends inside the box (less 100 m) that the other has within
    TOLERANCE clusters (in run_a's frame)."""
    import band_study as bs
    states = [_read_json(os.path.join(r, "study.json"))["definition"] for r in (run_a, run_b)]
    within = _shrunk_box(states[0]["place"], 100.0)
    spots = []
    for r, d in zip((run_a, run_b), states):
        _, _, ids, _ = _merged(_class_tiles(r, band, name))
        if not len(ids):
            return None
        spots.append(reframed_spots(ids, tuple(d["origin"]), d["crs"], tuple(states[0]["origin"]), states[0]["crs"],
                                    within))
    a, b = (np.unique(s) for s in spots)
    return {"band": band, "spots": [int(len(a)), int(len(b))],
            "matched_a": float(bs.matched(a, b, TOLERANCE).mean()) if len(a) else None,
            "matched_b": float(bs.matched(b, a, TOLERANCE).mean()) if len(b) else None,
            "primaries": [states[0]["primary"], states[1]["primary"]]}


def resampling_rows(runs: List[Dict], folders: Dict[str, str]) -> List[Dict]:
    """Every run of a place against each run of its other primary that has no resampling method
    (the reference: its grid holds that primary's side as the data are), per common band and for
    two classes: the lines with both anchors on the reference's side, found by the run on that
    side's data resampled and by the reference on the data themselves, and the lines across the
    border, for which each run has one side resampled. A row: the spots of each (both ends in the
    box less 100 m), the share of the reference's that the run has and of the run's that the
    reference has, the lines of the class, and the run's seconds, CPU seconds and memory."""
    rows = []
    for run in runs:
        for ref in runs:
            if ref["place"] != run["place"] or ref["primary"] == run["primary"] or ref["resampling"]:
                continue
            side = "aa" if ref["primary"] == ref["a_source"] else "bb"
            for band in sorted(set(run["bands"]) & set(ref["bands"])):
                for name in (side, "ab"):
                    found = agreement(folders[run["run"]], folders[ref["run"]], band, name)
                    entry = run["bands"][band]
                    rows.append({"place": run["place"], "band": band, "run": run["run"], "primary": run["primary"],
                                 "resampling": run["resampling"], "reference": ref["run"], "class": name,
                                 "lines": [entry["classes"][name]["lines"], ref["bands"][band]["classes"][name]["lines"]],
                                 "spots": found["spots"] if found else None,
                                 "reference_found": found["matched_b"] if found else None,
                                 "run_found": found["matched_a"] if found else None,
                                 "seconds": entry["seconds"], "prepare_seconds": entry.get("prepare_seconds"),
                                 "cpu_seconds": entry.get("cpu_seconds"),
                                 "prepare_cpu_seconds": entry.get("prepare_cpu_seconds"),
                                 "memory": entry.get("memory")})
    return rows


MIN_NEAR = 1000  # a place's ratio is carried over only from a bin with at least this many lines of A near the border


def _outside_near(keys: np.ndarray, counts: np.ndarray, origin: Tuple[float, float], piece,
                  boxes: List[Sequence[float]]) -> np.ndarray:
    """The counts of keys within reach of a border piece (their longest bin's) whose cell's centre
    lies in none of boxes, per length bin (a key in each bin of its mask)."""
    import shapely
    unique, inverse = np.unique(keys >> cc.ROW_SHIFT, return_inverse=True)
    inverse = inverse.ravel()
    centres = _cell_centres(unique << cc.ROW_SHIFT, origin)
    distance = shapely.distance(piece, shapely.points(centres))[inverse]
    lengths = (keys >> cc.LENGTH_SHIFT) & ((1 << cc.LENGTH_BINS) - 1)
    longest = np.frexp(np.maximum(lengths, 1).astype(np.float64))[1] - 1
    reach = np.array([hi for _, hi in _bins()], dtype=np.float64)[longest] + CELL_HALF_DIAGONAL
    keep = distance <= reach
    x, y = centres[inverse, 0], centres[inverse, 1]
    for left, bottom, right, top in boxes:
        keep &= ~((x >= left) & (x < right) & (y >= bottom) & (y < top))
    return np.array([int(counts[keep & ((lengths & (1 << k)) != 0)].sum()) for k in range(cc.LENGTH_BINS)] +
                    [int(counts[keep].sum())])


def estimate(run: Dict, measured: List[Dict], exposed: Dict, cube_dir: str, cache_dir: str) -> Optional[Dict]:
    """The cube's lines (and spots) across the border to the run's B: those measured in the boxes of
    the runs of that border on the cube's data (measured), plus the cube's lines within reach of B's
    border outside those boxes times the run's lines across the border per line of A within reach of
    it, per length bin (only from bins with MIN_NEAR such lines: the ratio carries over only to a
    border of the run's kind, a ridge or a gorge). None when the run is no border of that cube."""
    import area as ar
    neighbour = next((n for n, spec in exposed["neighbours"].items() if spec == run["b_area"]), None)
    if neighbour is None or exposed.get("area") != run["a_area"]:
        return None
    cube = cc.Cube(cube_dir)
    own = _project(cube.outline(), "EPSG:4326", cube.crs)
    other = _project(ar.from_spec(run["b_area"], 0.0, None, cache_dir).geometry, "EPSG:4326", cube.crs)
    piece = border_pieces(own, {"b": other})["b"]
    boxes = [m["counted"] for m in measured if m["crs"] == cube.crs]
    rows = cube.array("lines", 1)
    rest = _outside_near(rows[:, 0], rows[:, 1], cube.origin, piece, boxes)
    bins = []
    for k, (lo, hi) in enumerate(_bins()):
        ab = sum(e["classes"]["ab"]["bins"][k] for e in run["bands"].values())
        aa_near = sum(e["classes"]["aa"]["near"][k] for e in run["bands"].values())
        known = sum(e["classes"]["ab"]["bins"][k] for m in measured for e in m["bands"].values())
        ratio = ab / aa_near if aa_near and aa_near >= MIN_NEAR else None
        bins.append({"lengths": [lo, hi], "ab": ab, "aa_near": aa_near, "ratio": ratio, "measured": known,
                     "rest": int(rest[k]), "estimate": known + (round(ratio * rest[k]) if ratio is not None else 0),
                     "carried": ratio is not None})
    srows = cube.array("spots", 1)
    spots_rest = int(_outside_near(srows[:, 0], srows[:, 1], cube.origin, piece, boxes)[-1])
    aa_spots_near = run["spots_near"]["aa"]
    spots_ratio = run["spots"]["ab"] / aa_spots_near if aa_spots_near and aa_spots_near >= MIN_NEAR else None
    spots_known = sum(m["spots"]["ab"] for m in measured)
    spots = {"ab": run["spots"]["ab"], "aa_near": aa_spots_near, "ratio": spots_ratio, "measured": spots_known,
             "rest": spots_rest, "cube": int(srows[:, 1].sum()),
             "estimate": spots_known + (round(spots_ratio * spots_rest) if spots_ratio is not None else 0)}
    return {"neighbour": neighbour, "bins": bins, "estimate": sum(b["estimate"] for b in bins),
            "measured": sum(b["measured"] for b in bins), "rest": int(rest[-1]),
            "cube_lines": int(rows[:, 1].sum()), "boxes": [m["run"] for m in measured], "spots": spots}


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "-"


def _gib(value: Optional[int]) -> str:
    return f"{value / 2 ** 30:.2f}" if value else "-"


def _resampling_report(rows: List[Dict]) -> List[str]:
    """The report's section of the resampling methods (resampling_rows)."""
    out = ["## The resampling of the neighbour's data", "",
           "Each run against the run of the place's other primary without a method (the reference). *Side*: the "
           "lines with both anchors on the reference's side, which the run finds on that side's data resampled onto "
           "its grid and the reference on the data themselves. *Across*: the lines across the border (each run has "
           "one side resampled). Spots with both ends in the box (less 100 m); found: within "
           f"{TOLERANCE} cluster ({cc.CLUSTER_M:g} m) at both ends after reprojection. Method *own*: the mosaic's "
           "choice (the average of finer data, bilinear otherwise).", "",
           "| Place | Band | Run | Method | Class | Lines: run / reference | Spots: run / reference | "
           "Reference's spots the run has | Run's spots the reference has |",
           "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for r in rows:
        spots = f"{r['spots'][0]:,} / {r['spots'][1]:,}" if r["spots"] else "-"
        shares = [_pct(r[k], 1) if r[k] is not None else "-" for k in ("reference_found", "run_found")]
        out.append(f"| {r['place']} | {r['band']} | {r['run']} | {r['resampling'] or 'own'} | "
                   f"{'across' if r['class'] == 'ab' else 'side'} | {r['lines'][0]:,} / {r['lines'][1]:,} | {spots} | "
                   f"{shares[0]} | {shares[1]} |")
    out += ["", "The runs' cost (a band's tiles one after another in one process; step 1 holds the resampling; the "
                "private bytes are Windows' commit, the working set the RAM with the memory-mapped grids):", "",
            "| Place | Band | Run | Method | Seconds | of them step 1 | CPU seconds | of them step 1 | "
            "Peak private GiB | Peak working set GiB |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    seen = set()
    for r in rows:
        if (r["run"], r["band"]) in seen:
            continue
        seen.add((r["run"], r["band"]))
        number = lambda v: f"{v:,.0f}" if v is not None else "-"
        memory = r["memory"] or {}
        out.append(f"| {r['place']} | {r['band']} | {r['run']} | {r['resampling'] or 'own'} | {number(r['seconds'])} | "
                   f"{number(r['prepare_seconds'])} | {number(r['cpu_seconds'])} | {number(r['prepare_cpu_seconds'])} | "
                   f"{_gib(memory.get('private'))} | {_gib(memory.get('rss'))} |")
    out.append("")
    return out


def report(runs: List[Dict], agreements: List[Dict], exposed: Optional[Dict], estimates: List[Dict],
           resampling: Sequence[Dict] = ()) -> str:
    """study.md."""
    out = ["# The border study", "",
           "Each line whose first anchor lies in a place's box, by the countries holding its anchors: A-A (what "
           "A's layer counts today), B-B (what B's would count), A-B (one anchor in each: what both lose today), "
           "other (an anchor in neither outline or in both). *Near*: the lines whose first anchor's 1 km cell lies "
           "within reach of the border (the bin's longest line plus half a cell's diagonal). The other side's data "
           "come from its national source, as a neighbour fills a border gap.", ""]
    for run in runs:
        out += [f"## {run['name']} ({run['run']})", "",
                f"Primary {run['primary']}, {run['crs']}" +
                (f", the neighbour's data resampled {run['resampling']}" if run.get("resampling") else "") +
                f"; box {run['km2']} km² ({run['a']} {run['km2_a']}, "
                f"{run['b']} {run['km2_b']}); border in it {run['border_km']} km, along {run['border']}.", "",
                "| Band | Lengths | A-A | B-B | A-B | Other | A-B of all | A-B per A-A near | A-B per km of border |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for band, e in run["bands"].items():
            for k, (lo, hi) in enumerate(_bins()):
                if not (e["lengths"][0] <= lo and hi <= e["lengths"][1]):
                    continue
                n = {c: e["classes"][c]["bins"][k] for c in CLASSES}
                near = e["classes"]["aa"]["near"][k]
                ratio = f"{n['ab'] / near:.2f}" if near else "-"
                per_km = f"{n['ab'] / run['border_km']:,.0f}" if run["border_km"] else "-"
                out.append(f"| {band} | {lo}-{hi} m | {n['aa']:,} | {n['bb']:,} | {n['ab']:,} | {n['other']:,} | "
                           f"{_pct(n['ab'], sum(n.values()))} | {ratio} | {per_km} |")
        totals = {c: sum(e["classes"][c]["lines"] for e in run["bands"].values()) for c in CLASSES}
        all_lines = sum(totals.values())
        out += ["", f"All bands: A-A {totals['aa']:,}, B-B {totals['bb']:,}, A-B {totals['ab']:,} "
                    f"({_pct(totals['ab'], all_lines)}), other {totals['other']:,} lines. Spots: A-A "
                    f"{run['spots']['aa']:,}, B-B {run['spots']['bb']:,}, A-B {run['spots']['ab']:,} "
                    f"({_pct(run['spots']['ab'], sum(run['spots'].values()))}), other {run['spots']['other']:,}.", "",
                "| Band | Tiles | Seconds | Data of A: own / neighbour / fallback / none | Data of B: own / neighbour / fallback / none |",
                "| --- | ---: | ---: | --- | --- |"]
        for band, e in run["bands"].items():
            cells = []
            for side in ("a", "b"):
                f = e["fill"][side]
                cells.append(" / ".join(_pct(f[k], f["pixels"]) for k in ("own", "neighbour", "fallback", "none")))
            out.append(f"| {band} | {e['done']}/{e['tiles']} | {e['seconds']:,.0f} | {cells[0]} | {cells[1]} |")
        if run.get("picture"):
            out += ["", f"![{run['run']}](pictures/{os.path.basename(run['picture'])})"]
        out.append("")
    if agreements:
        out += ["## The two primaries of a place", "",
                f"The spots across the border with both ends in the box (less 100 m) that the other run has within "
                f"{TOLERANCE} cluster ({cc.CLUSTER_M:g} m) at both ends, after reprojection.", "",
                "| Place | Band | Spots (each primary) | Matched of the first | Matched of the second |",
                "| --- | --- | --- | ---: | ---: |"]
        for a in agreements:
            out.append(f"| {a['place']} | {a['band']} | {a['primaries'][0]} {a['spots'][0]:,}, {a['primaries'][1]} "
                       f"{a['spots'][1]:,} | {_pct(a['matched_a'] or 0, 1)} | {_pct(a['matched_b'] or 0, 1)} |")
        out.append("")
    if resampling:
        out += _resampling_report(list(resampling))
    if exposed:
        names = list(exposed["neighbours"])
        out += [f"## What {exposed['name']}'s cube could gain", "",
                "Its lines whose first anchor's cell lies within reach of a neighbour's border (each to the nearest); "
                "borders: " + ", ".join(f"{n} {exposed['border_km'][n]} km" for n in names) +
                f" of {exposed['boundary_km']} km.", "",
                "| Lengths | Lines | " + " | ".join(names) + " | Near any |", "| --- | ---: |" + " ---: |" * (len(names) + 1)]
        for b in exposed["lines"]["bins"]:
            near = sum(b["near"].values())
            out.append(f"| {b['lengths'][0]}-{b['lengths'][1]} m | {b['all']:,} | " +
                       " | ".join(f"{b['near'][n]:,}" for n in names) + f" | {_pct(near, b['all'])} |")
        lines_all = sum(b["all"] for b in exposed["lines"]["bins"])
        lines_near = sum(sum(b["near"].values()) for b in exposed["lines"]["bins"])
        out += ["", f"All: {lines_near:,} of {lines_all:,} lines ({_pct(lines_near, lines_all)}) within reach of a "
                    f"border.", ""]
    for est in estimates:
        out += [f"## Estimate with the ratio of {est['run']}: {exposed['name']}'s lines across the border to "
                f"{est['neighbour']}", "",
                f"Measured: the lines across the border in the boxes of {', '.join(est['boxes'])}. The rest: the cube's "
                f"lines within reach of that border outside those boxes, times this run's lines across the border per "
                f"line of A within reach of it (only from bins with {MIN_NEAR:,} such lines). The ratio carries over only "
                f"to a border of the same kind as this run's ({est['border']}).", "",
                "| Lengths | A-B in the box | A-A near in the box | Ratio | Measured | Cube's rest near | Estimate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for b in est["bins"]:
            ratio = "-" if b["ratio"] is None else f"{b['ratio']:.3f}"
            out.append(f"| {b['lengths'][0]}-{b['lengths'][1]} m | {b['ab']:,} | {b['aa_near']:,} | {ratio} | "
                       f"{b['measured']:,} | {b['rest']:,} | {b['estimate']:,}{'' if b['carried'] else ' (measured only)'} |")
        out += ["", f"Estimate {est['estimate']:,} lines across the border ({est['measured']:,} measured), "
                    f"{_pct(est['estimate'], est['cube_lines'])} of the cube's {est['cube_lines']:,}."]
        s = est.get("spots") or {}
        if s:
            ratio = "-" if s["ratio"] is None else f"{s['ratio']:.3f}"
            out += ["", f"Spots: {s['measured']:,} measured across the border; the cube's {s['rest']:,} within reach of "
                        f"it outside the boxes times {ratio} ({s['ab']:,} across per {s['aa_near']:,} of A near it): "
                        f"{s['estimate']:,} spots, {_pct(s['estimate'], s['cube'])} of the cube's {s['cube']:,}."]
        check = est.get("check")
        if check and check["bins"]:
            out += ["", f"Check: the run's lines of A against the cube {check['cube']} in the cells deeper in the box "
                        "than each bin's longest line (the same bands and data):", "",
                    "| Band | Lengths | Cells | Run | Cube | Run / cube |", "| --- | --- | ---: | ---: | ---: | ---: |"]
            for b in check["bins"]:
                ratio = f"{b['run'] / b['cube']:.4f}" if b["cube"] else "-"
                out.append(f"| {b['band']} | {b['lengths'][0]}-{b['lengths'][1]} m | {b['cells']} | {b['run']:,} | "
                           f"{b['cube']:,} | {ratio} |")
        out.append("")
    return "\n".join(out)


def analyse(out: str, data_dir: str, say=print) -> int:
    """study.json, study.md and the pictures of every run in out."""
    cache_dir = os.path.join(data_dir, "cache")
    runs, folders, paths = [], {}, {}
    for name in sorted(os.listdir(out)):
        folder = os.path.join(out, name)
        if os.path.exists(os.path.join(folder, "study.json")):
            say(f"{name}: analysing")
            run = analyse_run(folder, cache_dir)
            run["picture"] = picture(folder, run, cache_dir, os.path.join(out, "pictures", f"{name}.png"))
            runs.append(run)
            if not run["resampling"]:
                folders.setdefault(run["place"], []).append((run["primary"], folder))
            paths[run["run"]] = folder
    methods = resampling_rows(runs, paths) if any(r["resampling"] for r in runs) else []
    agreements = []
    for place, pair in folders.items():
        if len(pair) == 2:
            common = set(_read_json(os.path.join(pair[0][1], "study.json"))["bands"]) & \
                     set(_read_json(os.path.join(pair[1][1], "study.json"))["bands"])
            for band in sorted(common):
                found = agreement(pair[0][1], pair[1][1], band)
                if found:
                    agreements.append({"place": place, **found})
    exposed_path = os.path.join(out, "exposure.json")
    exposed = _read_json(exposed_path) if os.path.exists(exposed_path) else None
    estimates = []
    cube_dir = os.path.join(country.folder_of(data_dir, exposed["cube"]), "cube") if exposed else None
    if cube_dir and os.path.exists(os.path.join(cube_dir, "cube.json")):
        # the runs on the cube's data and grid (the primary is A's source) of each border
        own = [r for r in runs if r["primary"] == r["a_source"] and not r["resampling"]]
        for run in own:
            measured = [r for r in own if (r["a_area"], r["b_area"]) == (run["a_area"], run["b_area"])]
            found = estimate(run, measured, exposed, cube_dir, cache_dir)
            if found:
                found["check"] = check_against_cube(os.path.join(out, run["run"]), cube_dir)
                estimates.append({"run": run["run"], "border": run["border"], **found})
    _write_json(os.path.join(out, "study.json"), {"runs": runs, "agreements": agreements, "exposure": exposed,
                                                  "estimates": estimates, "resampling": methods})
    with cache.replacing(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(report(runs, agreements, exposed, estimates, methods))
    say(f"Written {os.path.join(out, 'study.md')}")
    return 0


# A sequential ramp of one hue, light to dark (the dataviz skill's reference blue, steps 100-700):
# the lines per cell on one log scale in both panels
RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
INK, MUTED = "#222222", "#8a8a8a"


def picture(folder: str, run: Dict, cache_dir: str, path: str) -> Optional[str]:
    """The run's 1 km cells: the lines counted today (A-A or B-B) and those across the border (A-B),
    with the border and the counted box, on one log scale; returns the path (None without lines)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, LogNorm
    from shapely.geometry import box
    d = _read_json(os.path.join(folder, "study.json"))["definition"]
    x0, y0 = d["origin"]
    counted = d["counted"]
    bands = _read_json(os.path.join(folder, "study.json")).get("bands", {})
    groups = {"today": ("aa", "bb"), "across": ("ab",)}
    cells = {}
    for group, names in groups.items():
        paths = [p for band in bands for name in names for p in _class_tiles(folder, band, name)]
        keys, counts, _, _ = _merged(paths)
        cells[group] = cc.sum_keys(keys >> cc.ROW_SHIFT, counts) if len(keys) else (keys, counts)
    if not any(len(c[0]) for c in cells.values()):
        return None
    i0, j0 = int((counted[0] - x0) // cc.CELL_M), int((counted[1] - y0) // cc.CELL_M)
    i1, j1 = int((counted[2] - x0) // cc.CELL_M) + 1, int((counted[3] - y0) // cc.CELL_M) + 1
    images = {}
    for group, (cell, n) in cells.items():
        image = np.full((j1 - j0, i1 - i0), np.nan)
        i, j = cell >> cc.CELL_BITS, cell & cc.CELL_MASK
        inside = (i >= i0) & (i < i1) & (j >= j0) & (j < j1)
        image[j[inside] - j0, i[inside] - i0] = n[inside]
        image[image == 0] = np.nan
        images[group] = image
    top = max(np.nanmax(v) if np.isfinite(v).any() else 1 for v in images.values())
    norm = LogNorm(vmin=1, vmax=max(top, 10))
    cmap = LinearSegmentedColormap.from_list("ramp", RAMP)
    crs = d["crs"]
    a = _project(outline_of(Side(**d["place"]["a"]), cache_dir), "EPSG:4326", crs)
    b = _project(outline_of(Side(**d["place"]["b"]), cache_dir), "EPSG:4326", crs)
    piece = border_pieces(a, {"b": b})["b"].intersection(box(*counted).buffer(cc.CELL_M))
    panel = 6.5  # inches of a panel's width; the height follows the box's shape
    fig, axes = plt.subplots(1, 2, figsize=(2 * panel, panel * (j1 - j0) / max(1, i1 - i0) + 1.4), dpi=120,
                             layout="constrained")
    titles = {"today": f"Counted today (A-A, B-B): {run_total(run, groups['today']):,} lines",
              "across": f"Across the border (A-B): {run_total(run, groups['across']):,} lines"}
    shown = None
    for ax, group in zip(axes, groups):
        shown = ax.imshow(images[group], origin="lower", extent=(i0, i1, j0, j1), cmap=cmap, norm=norm,
                          interpolation="nearest")
        for g in getattr(piece, "geoms", [piece]):
            if g.is_empty or not hasattr(g, "xy"):
                continue
            xs, ys = g.xy
            ax.plot((np.asarray(xs) - x0) / cc.CELL_M, (np.asarray(ys) - y0) / cc.CELL_M, color=INK, linewidth=1.6)
        bx = (np.array([counted[0], counted[2], counted[2], counted[0], counted[0]]) - x0) / cc.CELL_M
        by = (np.array([counted[1], counted[1], counted[3], counted[3], counted[1]]) - y0) / cc.CELL_M
        ax.plot(bx, by, color=MUTED, linewidth=0.8)
        ax.set_xlim(i0, i1)
        ax.set_ylim(j0, j1)
        ax.set_title(titles[group], fontsize=9, color=INK)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for spine in ax.spines.values():
            spine.set_visible(False)
    bar = fig.colorbar(shown, ax=axes, orientation="horizontal", fraction=0.06, shrink=0.5, aspect=40)
    bar.set_label("lines per 1 km cell (log scale); the black line is the border, the grey box the counted area",
                  fontsize=8, color=INK)
    bar.outline.set_visible(False)
    fig.suptitle(f"{run['name']}: {run['a']} (A) and {run['b']} (B), data and grid of {run['primary']}",
                 fontsize=10, color=INK)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def run_total(run: Dict, names: Sequence[str]) -> int:
    """The lines of some classes over a run's bands."""
    return sum(e["classes"][name]["lines"] for e in run["bands"].values() for name in names)


# --- The neighbours' rough boxes along the borders (docs/country-precompute/contract.md, section 6) ---------
SHAPES = os.path.join(REPO, "viewer", "src", "coverage", "shapes.json")
BOX_REACH = 5000.0  # metres beyond a border: the layer's longest line


def strip_share(a, b, boxes: Sequence[Tuple[float, float, float, float]], reach: float = BOX_REACH) -> Optional[Dict]:
    """Of b's land within reach of a (two WGS84 shapes), the km² and the share inside boxes
    ((south, north, west, east) each, as Source.offline's and bbox): where a grid of a's source
    with a border gap asks b's source (sources.filling.neighbour_window). None when b has no land
    within reach of a. A shape lying inside the other (a region of a country) is taken out of it
    first."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    common = a.intersection(b).area
    if common > 0.5 * b.area:
        a = a.difference(b)
    elif common > 0.5 * a.area:
        b = b.difference(a)
    west, south, east, north = b.bounds
    near = box(west - 1, south - 1, east + 1, north + 1)
    a = a.intersection(near)
    if a.is_empty or b.is_empty:
        return None
    west, south, east, north = a.bounds
    b = b.intersection(box(west - 1, south - 1, east + 1, north + 1))
    if b.is_empty:
        return None
    centre = a.union(b).centroid
    local = f"+proj=laea +lat_0={centre.y} +lon_0={centre.x} +datum=WGS84 +units=m"
    strip = _project(b, "EPSG:4326", local).buffer(0).intersection(_project(a, "EPSG:4326", local).buffer(0).buffer(reach))
    if strip.area < 1e6:
        return None
    covered = unary_union([_project(box(w, s, e, n).segmentize(0.05), "EPSG:4326", local) for s, n, w, e in boxes])
    return {"km2": round(strip.area / 1e6, 1), "share": min(1.0, strip.intersection(covered).area / strip.area)}


def box_reach(reach: float = BOX_REACH, shapes_path: str = SHAPES) -> List[Dict]:
    """Every declared pair of the catalogue (Source.neighbours, each direction): of the
    neighbour's land within reach of the source's, the share inside the neighbour's rough boxes
    (strip_share; the outlines of the coverage map, Natural Earth). share None: a neighbour without
    boxes, which may fill any border gap; a direction without an outline or without land within
    reach is left out."""
    import sources as src
    from shapely.geometry import shape
    from shapely.ops import unary_union
    with open(shapes_path, encoding="utf-8") as f:
        # A country split at its source's box keeps its id twice: the covered part, and the `rest`
        features = {x["properties"]["id"]: x for x in json.load(f)["features"] if not x["properties"].get("rest")}
    by_id = {s.id: s for s in (src.SOURCES.values() if isinstance(src.SOURCES, dict) else src.SOURCES)}

    def outline(source):
        ids = list((source.coverage.areas if source.coverage else ()) or source.regions or source.countries or ())
        parts = [shape(features[i]["geometry"]).buffer(0) for i in ids if i in features]
        return unary_union(parts) if source.coverage and parts else None

    rows = []
    for source in by_id.values():
        for name in source.neighbours or ():
            neighbour = by_id[name]
            a, b = outline(source), outline(neighbour)
            if a is None or b is None:
                continue
            boxes = [b_ for _, b_ in neighbour.offline or ()] + ([neighbour.bbox] if neighbour.bbox else [])
            found = strip_share(a, b, boxes, reach)
            if found is not None:
                rows.append({"source": source.id, "neighbour": name, "km2": found["km2"], "boxes": len(boxes),
                             "share": found["share"] if boxes else None})
    return sorted(rows, key=lambda r: (1.0 if r["share"] is None else r["share"], r["source"], r["neighbour"]))


def box_reach_report(rows: List[Dict], reach: float = BOX_REACH) -> List[str]:
    lines = [f"Of the neighbour's land within {reach / 1000:g} km of the source's, the share inside the neighbour's "
             "rough boxes (`Source.offline`, `bbox`): only there a border gap of the source's grid asks the neighbour "
             "(`sources.filling.neighbour_window`; a window spans the gaps it reaches, so the real share is a little "
             "higher).", "",
             "| Grid of | Neighbour | Its land within reach, km² | In its boxes |", "| --- | --- | ---: | ---: |"]
    for r in rows:
        share = "any gap (no boxes)" if r["share"] is None else f"{100 * r['share']:.0f} %"
        lines.append(f"| {r['source']} | {r['neighbour']} | {r['km2']:,.0f} | {share} |")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lines of the country layer across a border (docs/roadmap.md)")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run", help="count a place's bands by the countries of their anchors")
    r.add_argument("place", choices=sorted(PLACES))
    r.add_argument("--primary", help="the source whose data and grid are used (default: the place's A)")
    r.add_argument("--bands", help="bands of the layer, comma-separated (default: its layer bands)")
    r.add_argument("--threads", type=int, help="threads of the line search (default: the search's)")
    r.add_argument("--reset", action="store_true", help="remove a run of another definition first")
    r.add_argument("--resampling", choices=("nearest", "bilinear", "cubic", "average"),
                   help="how the neighbour's data are reprojected onto the primary's grid (default: the mosaic's "
                        "own choice, the average of finer data and bilinear otherwise)")
    e = commands.add_parser("exposure", help="a cube's lines within reach of its neighbours' borders")
    e.add_argument("cube", help="a country id with a built cube (countries/<id>/cube)")
    e.add_argument("--neighbours", required=True, help="NAME=SPEC,... (area specs: osm:<name> or a file)")
    a = commands.add_parser("report", help="study.json, study.md and the pictures of the runs in --out")
    for sub in (r, e, a):
        sub.add_argument("--out", required=True, help="the folder of the runs and the report")
        sub.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    b = commands.add_parser("boxes", help="how far each declared neighbour's rough boxes reach along the borders")
    b.add_argument("--reach", type=float, default=BOX_REACH, help="metres beyond the border (default: 5000)")
    b.add_argument("--write", help="write the table to this Markdown file as well")
    args = parser.parse_args(argv)
    if args.command == "boxes":
        text = box_reach_report(box_reach(args.reach), args.reach)
        print("\n".join(text))
        if args.write:
            with open(args.write, "w", encoding="utf-8") as f:
                f.write("\n".join(text) + "\n")
        return 0
    data_dir = cache.data_dir(args.data_dir)
    if args.command == "run":
        place = PLACES[args.place]
        run_place(place, args.primary or place.a.source, args.out, data_dir,
                  args.bands.split(",") if args.bands else None, threads=args.threads, reset=args.reset,
                  resampling=args.resampling)
        return 0
    if args.command == "exposure":
        neighbours = dict(item.split("=", 1) for item in args.neighbours.split(","))
        result = exposure(os.path.join(country.folder_of(data_dir, args.cube), "cube"), neighbours,
                          os.path.join(data_dir, "cache"))
        _write_json(os.path.join(args.out, "exposure.json"), result)
        print(f"Written {os.path.join(args.out, 'exposure.json')}")
        return 0
    return analyse(args.out, data_dir)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
