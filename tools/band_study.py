"""The band study (docs/country-precompute.md, "The band study"): which grid and anchor angle each
length range of the country layer needs, measured before the world is counted (the user's choice of
2026-11-03 after the Slovak pilot's control band).

Each study area is a country of its own (countries/<id>/, counted by `findaline.py country run <id>`):
a square of a source's country (its area spec within a box), with the surface model marking lines
over trees and buildings, every band of BANDS on it and the pilot's layer bands as its layer (its
cube shows the pilot's layer; the profile the study led to, country.PROFILE of 2026-11-12, is S, M, L1 and
L2: BANDS' S1m60 counted with the sag model, M2m60, L1-3m55 and L2-5m45). BANDS stay as they were counted: a
change makes setup refuse the areas counted already. A variant is compared with the reference of its lengths (PAIRS) by
where its spots and lines lie, never by their numbers alone: a coarser grid makes other spots.

    uv run python tools/band_study.py setup [AREA ...] [--data-dir D] [--reset]
    uv run python findaline.py country run <AREA> --data-dir D --yes
    uv run python tools/band_study.py analyse [AREA ...] --out <folder> [--data-dir D]

setup writes each area's country.json (its configuration and its pairs); a changed definition is
refused unless --reset, which removes the area's folder. analyse compares each pair of each area
over all lines and over the lines not over trees: the lines, the spots matched within TOLERANCE
clusters at both ends (either order), the cells of levels 1 and 4 of the cube's lattice (30" and 2',
about 0.6 x 0.9 and 2.4 x 3.7 km in Slovakia) with a spot that the variant loses and adds, the
Spearman correlation of spots per cell; per length bin of the cube within the pair's lengths; the
bands' tile seconds, CPU seconds and memory. It writes study.json, study.md and a picture of the
cells of each pair (pictures/<area>-<variant>.png).
"""
import argparse
import itertools
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import cache  # noqa: E402
import countcube as cc  # noqa: E402
import country  # noqa: E402
from country import Band  # noqa: E402

# Clusters an end of a spot may lie off its match, east-west and north-south: the lattice's clusters are
# 1.5" (30 x 46 m at 49°), so (2, 1) keeps about the +-50 m of cube v1's square clusters of 50 m
TOLERANCE = (2, 1)
LEVELS = (1, 4)  # the levels of the lattice the cells are compared on


@dataclass(frozen=True)
class Area:
    """A study area: a square of side_km around (lat, lon) within a source's country."""
    id: str
    name: str
    source: str
    country_area: str  # the area spec of the source's country, e.g. "osm:Slovensko"
    lat: float
    lon: float
    side_km: float


AREAS = {a.id: a for a in (
    Area("sk-tatry", "Vysoké a Belianske Tatry", "slovakia", "osm:Slovensko", 49.19, 20.15, 20),
    Area("sk-raj", "Slovenský raj", "slovakia", "osm:Slovensko", 48.93, 20.38, 20),
    Area("sk-fatra", "Malá Fatra", "slovakia", "osm:Slovensko", 49.21, 19.05, 20),
    Area("sk-sulov", "Súľovské skaly a Manínska tiesňava", "slovakia", "osm:Slovensko", 49.155, 18.56, 12),
)}

# Every area counts every band: the reference of each length range (the finest grid at 60°), the
# pilot's layer (layer=True: S, M and L split at 2 km, so that each part has its own cost) and the
# variants. Band edges lie on the cube's length edges.
BANDS = (
    Band("S1m60", (30, 300), 1.0, "formula", 60, 5000, True),      # the pilot's S and its reference
    Band("S2m60", (30, 300), 2.0, "formula", 60, 10000, False),    # sources of 2 m
    Band("M1m60", (300, 1000), 1.0, "sag", 60, 5000, False),       # the reference of 300-1000 m
    Band("M2m60", (300, 1000), 2.0, "sag", 60, 10000, True),       # the pilot's M (PROFILE's M)
    Band("L1-2m60", (1000, 2000), 2.0, "sag", 60, 10000, False),   # the reference of 1-2 km (the pilot's M2)
    Band("L1-3m55", (1000, 2000), 3.0, "sag", 55, 10000, False),   # PROFILE's L1
    Band("L1-5m45", (1000, 2000), 5.0, "sag", 45, 20000, True),    # the pilot's L up to 2 km
    Band("L1-5m50", (1000, 2000), 5.0, "sag", 50, 20000, False),
    Band("L1-5m55", (1000, 2000), 5.0, "sag", 55, 20000, False),
    Band("L2-5m45", (2000, 5000), 5.0, "sag", 45, 20000, True),    # the pilot's L from 2 km, its reference (PROFILE's L2)
    Band("L2-10m45", (2000, 5000), 10.0, "sag", 45, 20000, False),
)
PAIRS = (("S2m60", "S1m60"), ("M2m60", "M1m60"), ("L1-5m45", "L1-2m60"), ("L1-5m50", "L1-2m60"),
         ("L1-5m55", "L1-2m60"), ("L1-3m55", "L1-2m60"), ("L2-10m45", "L2-5m45"))
TENSION = ((300, 2.5), (1500, 6.0), (5000, 15.0))  # T(L) and the rig of the Slovak pilot (Silk 99)
RIG = {"webbing_weight": 41.0, "stretch": 2.1}
# The surface model marks lines over trees and buildings (the user's choice: with the DSM)
OPTIONS = {"nmpt": "mark", "water": "fill", "coastline": "copernicus", "fill_gaps": "on"}
FILTERS = ("all", "open")  # every line; the lines not over trees or buildings (and the spots with one)


def box_of(lat: float, lon: float, side_km: float) -> str:
    """S,W,N,E of a square of side_km around (lat, lon), in degrees (on a sphere of 6371 km: near
    enough for a sample)."""
    half_lat = math.degrees(side_km / 2 / 6371.0)
    half_lon = half_lat / math.cos(math.radians(lat))
    return f"{lat - half_lat:.5f},{lon - half_lon:.5f},{lat + half_lat:.5f},{lon + half_lon:.5f}"


def area_config(area: Area) -> Dict:
    """The configuration of an area's country.json."""
    return country.Country(id=area.id, name=area.name, source=area.source, area=area.country_area, bands=BANDS,
                           tension=TENSION, rig=dict(RIG),
                           options={**OPTIONS, "within": box_of(area.lat, area.lon, area.side_km)}).config()


def setup(data_dir: str, ids: Sequence[str], reset: bool = False, say=print) -> int:
    """country.json of each area: its configuration and its pairs ("study"). An area whose
    configuration changed is refused unless reset, which removes its folder first."""
    for area_id in ids:
        area = AREAS[area_id]
        folder = country.folder_of(data_dir, area_id)
        path = os.path.join(folder, "country.json")
        config = area_config(area)
        state = country.read_state(folder) if os.path.exists(path) else {}
        if state.get("config") not in (None, config):
            if not reset:
                say(f"{area_id}: the definition changed since its tiles were counted: --reset removes {folder}")
                return 1
            say(f"{area_id}: --reset removes {folder}")
            shutil.rmtree(folder)
            state = {}
        os.makedirs(folder, exist_ok=True)
        state["config"] = config
        state["study"] = {"pairs": [list(p) for p in PAIRS],
                          "square": {"lat": area.lat, "lon": area.lon, "side_km": area.side_km}}
        with cache.replacing(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, ensure_ascii=False)
        say(f"{area_id}: {area.name}, {area.side_km:g} km around {area.lat}, {area.lon} "
            f"({config['options']['within']}); `findaline.py country run {area_id}` counts it")
    return 0


# --- the comparison ------------------------------------------------------------------------------

def _ends(ids: np.ndarray) -> Tuple[np.ndarray, ...]:
    """The clusters (x east, y north) of both ends of spots: p (the first) and q."""
    ids = np.asarray(ids, dtype=np.int64)
    px = ids >> cc.SPOT_CX_SHIFT
    py = (ids >> cc.SPOT_CY_SHIFT) & cc.SPOT_C_MASK
    d_mask, half = (1 << cc.SPOT_D_BITS) - 1, 1 << (cc.SPOT_D_BITS - 1)
    return px, py, px + ((ids >> cc.SPOT_D_BITS) & d_mask), py + (ids & d_mask) - half


def _pair_keys(px, py, qx, qy, base: Tuple[int, int], bits: int) -> np.ndarray:
    """Keys of unordered pairs of clusters: the smaller end (x, then y) first, from base."""
    first = (px < qx) | ((px == qx) & (py <= qy))
    ax, ay = np.where(first, px, qx) - base[0], np.where(first, py, qy) - base[1]
    bx, by = np.where(first, qx, px) - base[0], np.where(first, qy, py) - base[1]
    return (ax << (3 * bits)) | (ay << (2 * bits)) | (bx << bits) | by


def matched(ids: np.ndarray, others: np.ndarray, tolerance=TOLERANCE) -> np.ndarray:
    """Which spots of ids have a spot among others whose two clusters each lie within tolerance
    clusters of theirs, in either order; tolerance: (east-west, north-south), or one number for both."""
    found = np.zeros(len(ids), dtype=bool)
    if not len(ids) or not len(others):
        return found
    tx, ty = (tolerance, tolerance) if isinstance(tolerance, int) else tolerance
    a, b = _ends(ids), _ends(others)
    xs, ys = (a[0], a[2], b[0], b[2]), (a[1], a[3], b[1], b[3])
    base = (int(min(v.min() for v in xs)) - tx, int(min(v.min() for v in ys)) - ty)
    span = max(int(max(v.max() for v in xs)) - base[0], int(max(v.max() for v in ys)) - base[1]) + max(tx, ty) + 1
    bits = max(1, span.bit_length())
    if 4 * bits > 62:
        raise ValueError("the spots lie too far apart for one comparison")
    keys = np.unique(_pair_keys(*b, base, bits))
    sx, sy = range(-tx, tx + 1), range(-ty, ty + 1)
    for dpx, dpy, dqx, dqy in itertools.product(sx, sy, sx, sy):
        candidates = _pair_keys(a[0] + dpx, a[1] + dpy, a[2] + dqx, a[3] + dqy, base, bits)
        at = np.minimum(np.searchsorted(keys, candidates), len(keys) - 1)
        found |= keys[at] == candidates
    return found


@dataclass
class Counts:
    """A band's lines (keys and counts) and spots (ids and records) within some lengths; keys and
    records (n, 2), cube v2's two words."""
    keys: np.ndarray
    n: np.ndarray
    ids: np.ndarray
    records: np.ndarray

    def where(self, line_keep: np.ndarray, spot_keep: np.ndarray) -> "Counts":
        return Counts(self.keys[line_keep], self.n[line_keep], self.ids[spot_keep], self.records[spot_keep])

    def bits(self, mask: int) -> "Counts":
        """The lines and spots with any bit of mask in word A of their key or record."""
        return self.where((self.keys[:, 0] & mask) != 0, (self.records[:, 0] & mask) != 0)


def load_band(folder: str, band: str, lengths: Tuple[float, float]) -> Tuple[Counts, List[Dict]]:
    """A band's counts within lengths (the cube's length bins) from its done tiles, with the tiles'
    metas; KeyError when a tile of the band is not done."""
    manifest = country.Manifest(folder)
    try:
        rows = manifest.rows(band)
    finally:
        manifest.close()
    if not rows or any(r["status"] != "done" for r in rows):
        raise KeyError(f"band {band}: {sum(r['status'] == 'done' for r in rows)} of {len(rows)} tiles done")
    parts, metas = [], []
    for r in rows:
        counts, meta = cc.load_tile(os.path.join(folder, "tiles", band, f"{r['name']}.npz"))
        parts.append(counts)
        metas.append(meta)
    keys, n = cc.sum_keys(np.concatenate([p.line_keys for p in parts]), np.concatenate([p.line_counts for p in parts]))
    ids, records = cc.merge_spots(np.concatenate([p.spot_ids for p in parts]),
                                  np.concatenate([p.spot_records for p in parts]))
    whole = Counts(keys, n, ids, records)
    return whole.bits(cc.Filters(length=lengths).length_mask() << cc.LENGTH_SHIFT), metas


def _per_cell(c: Counts, level: int) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Lines and spots per cell of a level of the lattice (i << CELL_BITS | j)."""
    i, j = (c.keys[:, 0] >> cc.COL_SHIFT) // level, ((c.keys[:, 0] >> cc.ROW_SHIFT) & cc.CELL_MASK) // level
    cells, n = cc.sum_keys((i << cc.CELL_BITS) | j, c.n)
    si, sj = cc.spot_cells(c.ids)
    spot_cells, spots = cc.count_keys(((si // level) << cc.CELL_BITS) | (sj // level))
    return dict(zip(cells.tolist(), n.tolist())), dict(zip(spot_cells.tolist(), spots.tolist()))


def compare_counts(ref: Counts, var: Counts) -> Dict:
    """A variant against its reference: lines, spots matched both ways, and per cell of the lattice's
    levels 1 and 4 (LEVELS) the cells with a spot lost and added and the Spearman correlation of spots
    per cell (over the cells with a line of either, zeros included)."""
    from scipy.stats import spearmanr
    ref_lines, var_lines = int(ref.n.sum()), int(var.n.sum())
    recall, precision = matched(ref.ids, var.ids), matched(var.ids, ref.ids)
    out = {"lines": {"reference": ref_lines, "variant": var_lines,
                     "ratio": var_lines / ref_lines if ref_lines else None},
           "spots": {"reference": int(len(ref.ids)), "variant": int(len(var.ids)),
                     "ratio": len(var.ids) / len(ref.ids) if len(ref.ids) else None,
                     "recall": float(recall.mean()) if len(recall) else None,
                     "precision": float(precision.mean()) if len(precision) else None},
           "cells": {}}
    for level in LEVELS:
        ref_cells, ref_spots = _per_cell(ref, level)
        var_cells, var_spots = _per_cell(var, level)
        cells = sorted(set(ref_cells) | set(var_cells))
        x = np.array([ref_spots.get(c, 0) for c in cells], dtype=float)
        y = np.array([var_spots.get(c, 0) for c in cells], dtype=float)
        rho = float(spearmanr(x, y)[0]) if len(cells) > 1 and x.std() > 0 and y.std() > 0 else None
        with_ref, with_var = set(ref_spots), set(var_spots)
        out["cells"][str(level)] = {
            "reference": len(with_ref), "variant": len(with_var),
            "lost": len(with_ref - with_var) / len(with_ref) if with_ref else None,
            "added": len(with_var - with_ref) / len(with_var) if with_var else None,
            "spearman": rho}
    return out


def band_cost(metas: List[Dict], km2: float) -> Dict:
    """A band's tiles: their number, seconds and CPU seconds (also per km² of the area) and the
    largest private memory of one."""
    seconds = sum(m["seconds"]["prepare"] + m["seconds"]["count"] for m in metas)
    cpu = sum(m.get("cpu_seconds") or 0.0 for m in metas)
    memory = [m["memory"]["private"] for m in metas if m.get("memory")]
    return {"tiles": len(metas), "seconds": round(seconds, 1), "cpu_seconds": round(cpu, 1),
            "seconds_per_km2": round(seconds / km2, 3) if km2 else None,
            "memory_gib": round(max(memory) / 2 ** 30, 2) if memory else None,
            "lines": sum(m["lines"] for m in metas), "spots": sum(m["spots"] for m in metas)}


def _length_bins(lengths: Tuple[float, float]) -> List[Tuple[int, int]]:
    """The cube's length bins within lengths."""
    edges = cc.LENGTH_EDGES
    return [(edges[k], edges[k + 1]) for k in range(cc.LENGTH_BINS)
            if lengths[0] <= edges[k] and edges[k + 1] <= lengths[1]]


def analyse_area(data_dir: str, area_id: str, pictures: Optional[str] = None) -> Dict:
    """Every pair of an area (its country.json's "study" pairs) and the cost of its bands."""
    import area as ar
    from shapely.geometry import shape
    folder = country.folder_of(data_dir, area_id)
    state = country.read_state(folder)
    config = country.Country.from_config(state["config"])
    with open(os.path.join(folder, "area.geojson"), encoding="utf-8") as f:
        outline = shape(json.load(f)["geometry"])
    km2 = ar.size_km2(outline)
    lat = outline.centroid.y
    result = {"id": area_id, "name": config.name, "km2": round(km2, 1), "square": state.get("study", {}).get("square"),
              "lat": round(lat, 4), "cell_km": {str(level): [round(v, 3) for v in cc.cell_size_km(level, lat)]
                                                for level in LEVELS},
              "cluster_m": [round(v, 1) for v in cc.cluster_size_m(lat)], "bands": {}, "pairs": []}
    loaded: Dict[str, Tuple[Counts, List[Dict]]] = {}

    def band(name):
        if name not in loaded:
            loaded[name] = load_band(folder, name, config.band(name).lengths)
            result["bands"][name] = band_cost(loaded[name][1], km2)
        return loaded[name][0]

    for variant, reference in state.get("study", {}).get("pairs", PAIRS):
        r_band, v_band = config.band(reference), config.band(variant)
        entry = {"variant": variant, "reference": reference, "lengths": list(r_band.lengths)}
        if v_band.lengths != r_band.lengths:
            raise ValueError(f"{area_id}: {variant} {v_band.lengths} and {reference} {r_band.lengths} "
                             "differ in lengths")
        try:
            ref, var = band(reference), band(variant)
        except KeyError as e:
            entry["missing"] = str(e)
            result["pairs"].append(entry)
            continue
        open_bit = 1 << cc.TREES_BIT  # word A
        entry["all"] = compare_counts(ref, var)
        entry["open"] = compare_counts(ref.bits(open_bit), var.bits(open_bit))
        bins = _length_bins(r_band.lengths)
        if len(bins) > 1:
            entry["bins"] = {}
            for lo, hi in bins:
                mask = cc.Filters(length=(lo, hi)).length_mask() << cc.LENGTH_SHIFT
                entry["bins"][f"{lo}-{hi}"] = compare_counts(ref.bits(mask), var.bits(mask))
        if pictures:
            entry["picture"] = picture(state, outline, ref, var, entry,
                                       os.path.join(pictures, f"{area_id}-{variant}.png"))
        result["pairs"].append(entry)
    return result


# Colours of the cells: the two sides Okabe-Ito's vermillion and blue (apart for every common colour
# vision deficiency, 3:1 on white), the cells of both a neutral grey between them
BOTH, LOST, ADDED = "#858585", "#d55e00", "#0072b2"


def picture(state: Dict, outline, ref: Counts, var: Counts, entry: Dict, path: str) -> str:
    """The lattice's level-1 cells (30") with a spot of the reference, the variant or both, over the
    area's outline (WGS84, drawn in cells of the lattice, its east-west shrunk by the latitude's
    cosine); returns the path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    _, ref_spots = _per_cell(ref, 1)
    _, var_spots = _per_cell(var, 1)
    cells = set(ref_spots) | set(var_spots)
    x0, y0 = state["origin"]  # in cells of the lattice
    west, south, east, north = outline.bounds
    i0, j0 = math.floor(west * cc.CELLS_PER_DEGREE) - x0, math.floor(south * cc.CELLS_PER_DEGREE) - y0
    i1, j1 = math.floor(east * cc.CELLS_PER_DEGREE) - x0 + 1, math.floor(north * cc.CELLS_PER_DEGREE) - y0 + 1
    image = np.zeros((j1 - j0, i1 - i0), dtype=np.int8)
    for cell in cells:
        i, j = cell >> cc.CELL_BITS, cell & cc.CELL_MASK
        if i0 <= i < i1 and j0 <= j < j1:
            image[j - j0, i - i0] = 1 if cell in ref_spots and cell in var_spots else 2 if cell in ref_spots else 3
    aspect = 1 / math.cos(math.radians((south + north) / 2))  # a cell's north-south over its east-west
    fig, ax = plt.subplots(figsize=(7, 7 * aspect * (j1 - j0) / max(1, i1 - i0) + 0.8), dpi=120)
    extent = (i0, i1, j0, j1)
    ax.imshow(np.ma.masked_equal(image, 0), origin="lower", extent=extent, interpolation="nearest",
              cmap=ListedColormap([BOTH, LOST, ADDED]), vmin=1, vmax=3)
    geoms = getattr(outline, "geoms", [outline])
    for g in geoms:
        xs, ys = g.exterior.xy
        ax.plot(np.asarray(xs) * cc.CELLS_PER_DEGREE - x0, np.asarray(ys) * cc.CELLS_PER_DEGREE - y0, color="#222222",
                linewidth=1)
    n_both = int((image == 1).sum())
    n_lost, n_added = int((image == 2).sum()), int((image == 3).sum())
    ax.legend(handles=[Patch(color=BOTH, label=f"both ({n_both})"),
                       Patch(color=LOST, label=f"only {entry['reference']}: lost ({n_lost})"),
                       Patch(color=ADDED, label=f"only {entry['variant']}: added ({n_added})")],
              loc="upper center", bbox_to_anchor=(0.5, -0.04), ncol=3, frameon=False, fontsize=8)
    lo, hi = entry["lengths"]
    ew, ns = cc.cell_size_km(1, (south + north) / 2)
    ax.set_title(f"{state['config']['name']}: {entry['variant']} against {entry['reference']}, {lo:g}-{hi:g} m, "
                 f"30\" cells ({ew:.2f} x {ns:.2f} km) with a spot", fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect(aspect)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# --- the report ----------------------------------------------------------------------------------

def _pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{100 * v:.1f} %"


def _num(v: Optional[float], digits: int = 2) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def _cell(res: Dict, level: int) -> str:
    """A level's cell by its size in km at the area's latitude."""
    ew, ns = res["cell_km"][str(level)]
    return f"{ew:.1f}x{ns:.1f} km"


def report(results: List[Dict]) -> str:
    """study.md: per area its pairs (all lines and those not over trees), the length bins of the
    pairs with several, the cost of its bands; then each pair across the areas."""
    tx, ty = TOLERANCE
    sizes = "; ".join(f"{r['id']} {tx * r['cluster_m'][0]:.0f} x {ty * r['cluster_m'][1]:.0f} m" for r in results)
    lines = ["# The band study", "",
             "Each variant against the reference of its lengths, by where its spots lie: *recall* is the share of "
             f"the reference's spots with a spot of the variant within {tx} clusters east-west and {ty} north-south "
             f"(the lattice's 1.5\" clusters: {sizes}) at both ends, *precision* the share of the variant's spots "
             "with one of the reference; *lost* the share of the reference's cells with a spot where the variant has "
             "none, *added* the share of the variant's cells with a spot where the reference has none (cells of the "
             "cube's lattice, levels 1 and 4: 30\" and 2', their size in km at the area's latitude); *time* the tile "
             "seconds of the variant's band against the reference's. \"Not over trees\": only the lines not over "
             "trees or buildings (the layer's filter).", ""]
    rule = "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"

    def row(entry, part, bands):
        v, r = bands.get(entry["variant"]), bands.get(entry["reference"])
        time = f"{v['seconds'] / r['seconds']:.2f}x" if v and r and r["seconds"] else "-"
        c1, c4 = part["cells"]["1"], part["cells"]["4"]
        spots = part["spots"]
        return (f"| {entry['variant']} | {entry['reference']} | {_num(part['lines']['ratio'])}x | "
                f"{_num(spots['ratio'])}x | {_pct(spots['recall'])} | {_pct(spots['precision'])} | "
                f"{_pct(c1['lost'])} | {_pct(c1['added'])} | {_pct(c4['lost'])} | {_num(c1['spearman'], 3)} | {time} |")

    for res in results:
        lines += [f"## {res['name']} ({res['id']}), {res['km2']:g} km²", ""]
        one, four = _cell(res, 1), _cell(res, 4)
        header = (f"| Variant | Reference | Lines | Spots | Recall | Precision | Lost {one} | Added {one} | Lost {four} | "
                  f"Spearman {one} | Time |")
        for part, title in (("all", "All lines"), ("open", "Not over trees")):
            lines += [f"{title}:", "", header, rule]
            for entry in res["pairs"]:
                if "missing" in entry:
                    lines.append(f"| {entry['variant']} | {entry['reference']} | {entry['missing']} |||||||||")
                else:
                    lines.append(row(entry, entry[part], res["bands"]))
            lines.append("")
        binned = [e for e in res["pairs"] if "bins" in e]
        if binned:
            lines += ["By length (all lines):", "", f"| Variant | Lengths | Recall | Lost {one} | Added {one} |",
                      "| --- | --- | ---: | ---: | ---: |"]
            for entry in binned:
                for name, part in entry["bins"].items():
                    lines.append(f"| {entry['variant']} | {name} m | {_pct(part['spots']['recall'])} | "
                                 f"{_pct(part['cells']['1']['lost'])} | {_pct(part['cells']['1']['added'])} |")
            lines.append("")
        lines += ["Bands:", "", "| Band | Tiles | Tile hours | CPU hours | s/km² | Memory GiB | Lines | Spots |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for name, b in res["bands"].items():
            lines.append(f"| {name} | {b['tiles']} | {b['seconds'] / 3600:.2f} | {b['cpu_seconds'] / 3600:.2f} | "
                         f"{_num(b['seconds_per_km2'])} | {_num(b['memory_gib'])} | {b['lines']:,} | {b['spots']:,} |")
        pictures = [e["picture"] for e in res["pairs"] if e.get("picture")]
        if pictures:
            lines += ["", "Pictures: " + ", ".join(f"[{os.path.basename(p)}](pictures/{os.path.basename(p)})"
                                                    for p in pictures)]
        lines.append("")
    if len(results) > 1:
        lines += ["## Across the areas (all lines)", "", "| Variant | Reference | " +
                  " | ".join(f"{r['id']} recall / lost ({_cell(r, 1)})" for r in results) + " |",
                  "| --- | --- |" + " ---: |" * len(results)]
        for variant, reference in ((e["variant"], e["reference"]) for e in results[0]["pairs"]):
            cells = []
            for res in results:
                entry = next((e for e in res["pairs"] if e["variant"] == variant and e["reference"] == reference), None)
                cells.append("-" if entry is None or "all" not in entry else
                             f"{_pct(entry['all']['spots']['recall'])} / {_pct(entry['all']['cells']['1']['lost'])}")
            lines.append(f"| {variant} | {reference} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def analyse(data_dir: str, ids: Sequence[str], out: str, say=print) -> int:
    """study.json, study.md and the pictures of the areas into out."""
    os.makedirs(out, exist_ok=True)
    results = []
    for area_id in ids:
        say(f"{area_id}: comparing")
        results.append(analyse_area(data_dir, area_id, os.path.join(out, "pictures")))
    with cache.replacing(os.path.join(out, "study.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    with cache.replacing(os.path.join(out, "study.md"), "w", encoding="utf-8") as f:
        f.write(report(results))
    say(f"Written {os.path.join(out, 'study.md')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="The band study of the country layer (docs/country-precompute.md)")
    commands = parser.add_subparsers(dest="command", required=True)
    s = commands.add_parser("setup", help="write each area's country.json")
    s.add_argument("--reset", action="store_true", help="remove an area whose definition changed, then write it")
    a = commands.add_parser("analyse", help="compare the variants with their references")
    a.add_argument("--out", required=True, help="the folder of study.json, study.md and the pictures")
    for sub in (s, a):
        sub.add_argument("areas", nargs="*", help=f"the areas (default: all: {', '.join(AREAS)})")
        sub.add_argument("--data-dir", help="data folder (default: FINDALINE_DATA or the folder of the scripts)")
    args = parser.parse_args(argv)
    data_dir = cache.data_dir(args.data_dir)
    if args.command == "setup":
        unknown = [a for a in args.areas if a not in AREAS]
        if unknown:
            parser.error(f"unknown areas {', '.join(unknown)}: one of {', '.join(AREAS)}")
        return setup(data_dir, args.areas or list(AREAS), args.reset)
    return analyse(data_dir, args.areas or list(AREAS), args.out)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
