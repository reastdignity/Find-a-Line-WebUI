"""
The worker's warm-up of numba: tiny synthetic searches at its start, so the kernels of the line
search are compiled (or loaded from numba's cache) before the first job needs them.

On the public site numba's cache is in the worker's /tmp (a tmpfs, compose.yaml), so after every
start of the container the first search compiled every kernel (about 40 s on the VPS for a trivial
search). jobs.Scheduler runs warm_up in a process of its own at its start (Scheduler(warm_up=True):
`findaline.py worker` and `web`, unless FINDALINE_WARM_UP=0), while it already claims jobs: numba
writes its cache files atomically, so a job compiling the same kernel meanwhile is safe.

Each signature of a kernel is compiled once, and a signature is the types of its arguments: an
optional grid passed as None becomes a small writable array of the kernel (linesearch.evaluate_lines,
lineprofiles.line_profiles), not the read-only memory-mapped grid of a search, and a view of a
column is not a contiguous array. So the synthetic searches go through the code of a real one
(search.plan_search on local files, prepare_data, find_lines, whose grids are memory-mapped like a
search's) in every combination that gives the kernels other types: with and without a surface
model, with and without the masks of water and filled gaps, a circle and a tile's core, an anchor
with more pairs than linesearch.pair_chunk's buffer (its second pass), parts of the pair search of
one anchor and of several (`small` has few anchors, `wide` more than linesearch.CHUNKS), and
profiles thinned to their max_points (lines of more than 205 pixels, in `wide`). The sag estimator
gives the kernels arrays of the types of the formula's (float64, C order), but its default
--max-anchor-diff-m is an int: one search of it. Not covered: grids of 2**31 pixels or more
(terrain.prominence's int64 indices), compiled by the first such search.

It never writes to the cache, the runs or jobs.sqlite: its data folder is a temporary folder under
work/ (removed afterwards, or after a day by the housekeeping when it was killed); its output is
dropped, and a failure is only printed to stderr.
"""

import contextlib
import dataclasses
import gc
import os
import shutil
import sys
import traceback
import uuid

import numpy as np

FOLDER = "warmup"  # under work/
LEFT, TOP = 500000.0, 300000.0  # PL-1992 (EPSG:2180), 1 m pixels
MASKS = ((False, False), (True, False), (False, True), (True, True))  # (water, filled gaps) of a search


def _small() -> np.ndarray:
    """Two plateaus 30 m above a 20 m wide floor: a few hundred anchors, short lines."""
    terrain = np.full((120, 120), 230.0)
    terrain[:, 50:70] = 200.0
    return terrain


def _wide() -> np.ndarray:
    """Two blocks 120 m high, 60 m long and 210 m apart: more anchors than linesearch.CHUNKS with
    pairs, lines of more than 205 pixels (their profiles thinned to max_points)."""
    terrain = np.full((300, 300), 100.0)
    terrain[120:180, 5:45] = 220.0
    terrain[120:180, 255:295] = 220.0
    return terrain


SCENES = {"small": (_small, dict(radius=45, min_length=15, max_length=60)),
          "wide": (_wide, dict(radius=140, min_length=206, max_length=230))}


def write_grids(folder: str, scene: str = "small") -> tuple:
    """A scene's terrain and surface model as GeoTIFFs, the surface with "trees" 5 m above the
    highest terrain in its northern third. Returns the paths of the terrain and the surface and
    the centre (easting, northing)."""
    import rasterio as rio
    from rasterio.transform import from_origin

    terrain = SCENES[scene][0]()
    surface = terrain.copy()
    surface[:len(surface) // 3] = np.maximum(surface[:len(surface) // 3], terrain.max() + 5)
    paths = []
    for name, band in ((f"{scene}-nmt.tif", terrain), (f"{scene}-nmpt.tif", surface)):
        path = os.path.join(folder, name)
        with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1,
                      dtype="float32", crs="EPSG:2180", transform=from_origin(LEFT, TOP, 1, 1)) as dst:
            dst.write(band.astype(np.float32), 1)
        paths.append(path)
    return paths[0], paths[1], (LEFT + terrain.shape[1] / 2, TOP - terrain.shape[0] / 2)


def _masks(folder: str, shape: tuple, tag: str) -> tuple:
    """Masks of water and filled gaps as a search has them: boolean .npy files, memory-mapped
    read-only (sources.filling saves them with np.save, search.prepare_data loads them so)."""
    masks = []
    for name in (f"water-{tag}.npy", f"filled-{tag}.npy"):  # new files: the last ones may still be mapped
        mask = np.zeros(shape, dtype=bool)
        mask[:, shape[1] // 2] = True  # under the lines' middle
        path = os.path.join(folder, name)
        np.save(path, mask)
        masks.append(np.load(path, mmap_mode="r"))
    return tuple(masks)


# The searches: (scene, with a surface model, model, mask variants, also a tile's core)
SEARCHES = (("small", True, "formula", MASKS, True), ("small", False, "formula", MASKS, True),
            ("small", True, "sag", MASKS[-1:], False), ("wide", True, "formula", MASKS[-1:], False))


def run(folder: str):
    """The synthetic searches, in a data folder of their own (`folder`)."""
    import linesearch
    import progress as pg
    import search
    from params import SearchParams

    pg.TEXT_INTERVAL = float("inf")
    os.makedirs(folder, exist_ok=True)
    grids = {scene: write_grids(folder, scene) for scene in SCENES}
    paths = search.Paths(folder, os.path.join(folder, "work"))
    for k, (scene, surface, model, variants, core) in enumerate(SEARCHES):
        nmt, nmpt, (easting, northing) = grids[scene]
        params = SearchParams(elevation_file=nmt, easting=easting, northing=northing, resolution=1,
                              prominence_span=10, drop_radius=10, water="off", fill_gaps="off", ortho="never",
                              no_html=True, threads=1, model=model, **SCENES[scene][1],
                              **({"surface_file": nmpt} if surface else {"nmpt": "off"}))
        plan = search.plan_search(params, paths, lambda kind, text: None)
        data = search.prepare_data(plan)
        water, filled = _masks(paths.work, data.elevation.shape, str(k))
        for with_water, with_filled in variants:
            search.find_lines(plan, dataclasses.replace(data, water=water if with_water else None,
                                                        filled=filled if with_filled else None))
        if core:
            # A tile's core (the anchors' mask, the lines reordered) and the second pass of
            # pair_chunk for the anchors whose pairs overflow its buffer
            buffer = linesearch.PAIR_BUFFER
            linesearch.PAIR_BUFFER = 1
            try:
                search._lines(plan, data, core=plan.grid.bounds)
            finally:
                linesearch.PAIR_BUFFER = buffer
        del data, water, filled
        gc.collect()  # the memory-mapped grids closed before the next plan's are written (Windows)


def warm_up(data_dir: str):
    """Compile the kernels of a search (see the module's docstring) in a temporary folder under
    the data folder's work/; prints only a failure (to stderr)."""
    folder = os.path.join(data_dir, "work", FOLDER, uuid.uuid4().hex)
    if hasattr(os, "nice"):
        with contextlib.suppress(OSError):
            os.nice(10)  # the jobs claimed meanwhile come first
    try:
        with open(os.devnull, "w", encoding="utf-8") as quiet, contextlib.redirect_stdout(quiet):
            run(folder)
    except Exception:
        print("numba warm-up failed (the first search compiles instead):", file=sys.stderr)
        traceback.print_exc()
    finally:
        gc.collect()
        shutil.rmtree(folder, ignore_errors=True)
