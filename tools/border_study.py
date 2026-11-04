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

    uv run python tools/border_study.py run tatry [--primary geoportal] [--bands S,M,L] --out <folder> [--data-dir D]
    uv run python tools/border_study.py exposure slovakia --neighbours Polska=osm:Polska,... --out <folder> [--data-dir D]
    uv run python tools/border_study.py report --out <folder>

run counts a place into <out>/<place>-<primary>/, tile by tile (a tile whose meta exists is done, so a
run resumes; a changed definition is refused unless --reset). exposure reads a built cube
(countries/<id>/cube) and counts its lines and spots whose first anchor's 1 km cell lies within reach
of each neighbour's border (a bin's longest line plus half a cell's diagonal): the most a layer
across borders could add there. report writes study.json, study.md and pictures/<run>.png: per band
and length bin the lines of each class, the share across the border, the same within reach of the
border and per km of it, the spots of each class, where each side's data came from, the agreement of
a place's two primaries (spots across the border matched within TOLERANCE clusters after
reprojection), and with exposure.json the estimate for its cube (the place's lines across the
border per line of A within reach of the border, times the cube's lines within reach of B's border).
"""
import argparse
import dataclasses
import gc
import json
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

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
PLACES = {p.id: p for p in (
    Place("tatry", "Tatras: Kasprowy Wierch, Rysy, Gerlach", "49.16,19.98,49.25,20.20", SLOVAKIA, POLAND,
          "the main ridge"),
    Place("pieniny", "Pieniny: the Dunajec gorge", "49.39,20.36,49.44,20.48", SLOVAKIA, POLAND,
          "the river in the gorge"),
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


def run_place(place: Place, primary: str, out: str, data_dir: str, bands: Optional[Sequence[str]] = None,
              config: Optional[country.Country] = None, threads: Optional[int] = None, reset: bool = False,
              say=print) -> str:
    """Count a place's bands with the primary's data into <out>/<place>-<primary>/; returns the
    folder. A tile whose meta exists is skipped; a run of another definition is refused unless
    reset."""
    import area as ar
    import search
    import sources as src
    from shapely.geometry import box, mapping
    config = config or country.COUNTRIES["slovakia"]
    sides = {"a": place.a, "b": place.b}
    if primary not in (place.a.source, place.b.source):
        raise ValueError(f"the primary must be {place.a.source} or {place.b.source}")
    names = list(bands) if bands else [b.name for b in config.bands if b.layer]
    folder = os.path.join(out, f"{place.id}-{primary}")
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
        work = os.path.join(data_dir, "work", f"border-{place.id}-{primary}")
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
            say(f"\n--- {place.id} ({primary}), band {band.name}, tile {k + 1}/{len(tiles)} {tile.name} "
                f"({grid.width} x {grid.height} px) ---")
            src.used_data.clear()
            events.filled = []
            t0 = time.time()
            data = search.prepare_data(tile_plan, statistics=False, shore="none", strips=True)
            t1 = time.time()
            inside = {k2: ar.Polygon(g).mask(grid) if not g.is_empty else np.zeros((grid.height, grid.width), bool)
                      for k2, g in clipped.items()}
            sink = BorderSink(grid, origin, core, band.lengths, last, inside["a"], inside["b"])
            funnel = search.count_tile(tile_plan, data, core, sink, table)
            t2 = time.time()
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
    return {"bins": out}


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
              "a": place.a.name, "b": place.b.name, "a_source": place.a.source, "a_area": place.a.area,
              "b_area": place.b.area, "border": place.border, "crs": crs,
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
    for name in CLASSES:
        _, _, ids, _ = _merged(every[name])
        result["spots"][name] = int(len(ids))
    return result


def agreement(run_a: str, run_b: str, band: str) -> Optional[Dict]:
    """Two runs of one place with different primaries: the spots across the border of each with both
    ends inside the box (less 100 m) that the other has within TOLERANCE clusters (in run_a's frame)."""
    import band_study as bs
    states = [_read_json(os.path.join(r, "study.json"))["definition"] for r in (run_a, run_b)]
    within = _shrunk_box(states[0]["place"], 100.0)
    spots = []
    for r, d in zip((run_a, run_b), states):
        _, _, ids, _ = _merged(_class_tiles(r, band, "ab"))
        if not len(ids):
            return None
        spots.append(reframed_spots(ids, tuple(d["origin"]), d["crs"], tuple(states[0]["origin"]), states[0]["crs"],
                                    within))
    a, b = (np.unique(s) for s in spots)
    return {"band": band, "spots": [int(len(a)), int(len(b))],
            "matched_a": float(bs.matched(a, b, TOLERANCE).mean()) if len(a) else None,
            "matched_b": float(bs.matched(b, a, TOLERANCE).mean()) if len(b) else None,
            "primaries": [states[0]["primary"], states[1]["primary"]]}


def estimate(run: Dict, exposed: Dict) -> Optional[Dict]:
    """The cube's lines across the border to the run's B: per length bin, the run's lines across the
    border per line of A within reach of the border, times the cube's lines within reach of B's border;
    None when the run is no border of that cube."""
    neighbour = next((n for n, spec in exposed["neighbours"].items() if spec == run["b_area"]), None)
    if neighbour is None or exposed.get("area") != run["a_area"]:
        return None
    bins = []
    for k, (lo, hi) in enumerate(_bins()):
        ab = sum(e["classes"]["ab"]["bins"][k] for e in run["bands"].values())
        aa_near = sum(e["classes"]["aa"]["near"][k] for e in run["bands"].values())
        near = exposed["lines"]["bins"][k]["near"].get(neighbour, 0)
        ratio = ab / aa_near if aa_near else None
        bins.append({"lengths": [lo, hi], "ab": ab, "aa_near": aa_near, "ratio": ratio, "cube_near": near,
                     "estimate": round(ratio * near) if ratio is not None else None})
    total = sum(b["estimate"] or 0 for b in bins)
    return {"neighbour": neighbour, "bins": bins, "estimate": total,
            "cube_lines": sum(b["all"] for b in exposed["lines"]["bins"]),
            "cube_near": sum(b["cube_near"] for b in bins)}


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "-"


def report(runs: List[Dict], agreements: List[Dict], exposed: Optional[Dict], estimates: List[Dict]) -> str:
    """study.md."""
    out = ["# The border study", "",
           "Each line whose first anchor lies in a place's box, by the countries holding its anchors: A-A (what "
           "A's layer counts today), B-B (what B's would count), A-B (one anchor in each: what both lose today), "
           "other (an anchor in neither outline or in both). *Near*: the lines whose first anchor's 1 km cell lies "
           "within reach of the border (the bin's longest line plus half a cell's diagonal). The other side's data "
           "come from its national source, as a neighbour fills a border gap.", ""]
    for run in runs:
        out += [f"## {run['name']} ({run['run']})", "",
                f"Primary {run['primary']}, {run['crs']}; box {run['km2']} km² ({run['a']} {run['km2_a']}, "
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
        out += [f"## Estimate from {est['run']}: {exposed['name']}'s lines across the border to {est['neighbour']}", "",
                "| Lengths | A-B in the box | A-A near in the box | Ratio | Cube's lines near | Estimate |",
                "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for b in est["bins"]:
            ratio = "-" if b["ratio"] is None else f"{b['ratio']:.2f}"
            value = "-" if b["estimate"] is None else f"{b['estimate']:,}"
            out.append(f"| {b['lengths'][0]}-{b['lengths'][1]} m | {b['ab']:,} | {b['aa_near']:,} | {ratio} | "
                       f"{b['cube_near']:,} | {value} |")
        out += ["", f"Estimate {est['estimate']:,} lines across the border, {_pct(est['estimate'], est['cube_lines'])} "
                    f"of the cube's {est['cube_lines']:,}.", ""]
    return "\n".join(out)


def analyse(out: str, data_dir: str, say=print) -> int:
    """study.json, study.md and the pictures of every run in out."""
    cache_dir = os.path.join(data_dir, "cache")
    runs, folders = [], {}
    for name in sorted(os.listdir(out)):
        folder = os.path.join(out, name)
        if os.path.exists(os.path.join(folder, "study.json")):
            say(f"{name}: analysing")
            run = analyse_run(folder, cache_dir)
            run["picture"] = picture(folder, run, cache_dir, os.path.join(out, "pictures", f"{name}.png"))
            runs.append(run)
            folders.setdefault(run["place"], []).append((run["primary"], folder))
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
    for run in runs if exposed else []:
        found = estimate(run, exposed) if run["primary"] == run["a_source"] else None  # the cube's data and grid
        if found:
            estimates.append({"run": run["run"], **found})
    _write_json(os.path.join(out, "study.json"), {"runs": runs, "agreements": agreements, "exposure": exposed,
                                                  "estimates": estimates})
    with cache.replacing(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(report(runs, agreements, exposed, estimates))
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
    width = 7.5 * (i1 - i0) / max(1, j1 - j0)
    fig, axes = plt.subplots(1, 2, figsize=(min(14, 2 * width + 1), 6.2), dpi=120)
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
    bar = fig.colorbar(shown, ax=axes, orientation="horizontal", fraction=0.05, pad=0.04)
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lines of the country layer across a border (docs/roadmap.md)")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run", help="count a place's bands by the countries of their anchors")
    r.add_argument("place", choices=sorted(PLACES))
    r.add_argument("--primary", help="the source whose data and grid are used (default: the place's A)")
    r.add_argument("--bands", help="bands of the layer, comma-separated (default: its layer bands)")
    r.add_argument("--threads", type=int, help="threads of the line search (default: the search's)")
    r.add_argument("--reset", action="store_true", help="remove a run of another definition first")
    e = commands.add_parser("exposure", help="a cube's lines within reach of its neighbours' borders")
    e.add_argument("cube", help="a country id with a built cube (countries/<id>/cube)")
    e.add_argument("--neighbours", required=True, help="NAME=SPEC,... (area specs: osm:<name> or a file)")
    a = commands.add_parser("report", help="study.json, study.md and the pictures of the runs in --out")
    for sub in (r, e, a):
        sub.add_argument("--out", required=True, help="the folder of the runs and the report")
        sub.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    args = parser.parse_args(argv)
    data_dir = cache.data_dir(args.data_dir)
    if args.command == "run":
        place = PLACES[args.place]
        run_place(place, args.primary or place.a.source, args.out, data_dir,
                  args.bands.split(",") if args.bands else None, threads=args.threads, reset=args.reset)
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
