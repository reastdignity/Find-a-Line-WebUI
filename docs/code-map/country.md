# Code map: the country layer

What the modules of this area hold, in detail: the country layer. Moved out of CLAUDE.md on 2026-11-12; nothing loads
this file by itself, so read the entry of a module before a large change to it. What must stay in sync and the
pitfalls are in `.claude/rules/` (country-layer).

## `countcube.py`

The counter cube of the country layer (docs/country-precompute/contract.md, section 2): int64 keys of 53 bits (the
cell's column and row of `CELL_M` from the country's origin, a length mask on `LENGTH_EDGES`, 3-bit bins of
prominence, wall, clearance and height on `EDGES` (`UNKNOWN` for NaN), the flag pairs of trees and water; the low
`RECORD_BITS` a line's or a spot's record); spots as pairs of `CLUSTER_M` anchor clusters (`spot_ids`, `merge_spots`:
OR, the largest bins, the smallest wall); `TileCounter` fed by `search.count_tile` (the core and band filters, reduced
as it goes), `save_tile`/`load_tile` (npz, `VERSION`), `build` (lines summed, spots merged over all tiles and bands,
levels 1/2/4/8, `lines_<L>.npy`/`spots_<L>.npy` [key, count] sorted, `cube.json` last), `Filters` (+ `parse` of the
web's query) and `select` (`skip=` one of `DIMENSIONS` leaves that dimension's condition out), `Cube` (arrays read
into memory when first used, not mapped: Windows would refuse the next build's replacing them; `box`, `auto_level`,
`cell_count`, `_slice` the rows of a view, `cells`, `histogram` (the counts per bin of each dimension, each under
every filter but its own: a line's one length bit partitions the total, a spot's ORed bits make its bins upper bounds;
`view=` only the cells reaching a WGS84 view, `reaching`: their rounded corners' box intersects it, as the page counts
its total in view), `corners`, `outline_simplified` (the outline for a map at `OUTLINE_TOLERANCE`, coordinates of
`OUTLINE_DECIMALS`, with the original's km², kept per tolerance), `cut` (the level's cells the outline cuts: the km²
inside, from the exact outline, and that part as polygons of rings of [lat, lon], simplified by the cell's side over
`CUT_SIMPLIFY`; all levels at the first call by a quadtree, `_cut_cells`, each piece cut out of its parent's: Slovakia
0.3 s; kept; none without an outline)), `cell_request` (the search of one cell for the app's form); numpy, pyproj and
shapely only (the web process imports it: no numba)

## `country.py`

The country layer's driver (`findaline.py country run|status|profile|build|compare|worker <id>`,
docs/country-precompute/contract.md section 3): `Band`/`Country`, `COUNTRIES` (Slovakia: bands S, M, L and the control
band M2, T(L), Silk 99, no DSM); `country.json` (the config, `hash` = sha256 of the config and of `area.geojson`'s
sha256, with the surface model also of `obstacles.RULE` (another rule counts the tiles again), `crs`, `origin` =
`countcube.origin_of` of the outline, once; a country outside `COUNTRIES` from a `country.json` holding its config,
tools/band_study.py's areas), the outline fetched once (`area.from_spec(whole=True)`: never simplified; clipped to the
box of the option `within`, which makes it a study area, `Country.study`; a country's less the countries set up before
it, `_partition`, their ids in the file's `less`; `_say_overlaps`: `run` names the areas it overlaps by `OVERLAP_KM2`
or more) and every band's `search.plan_search(tiled=False)` over that file (`band_plan`, `form_params`: the band's
`SearchParams` fields, cube.json's `params`, the pretension T at its `max_length`; `end_zone`/`anchor_lift` of
`Country.options` go into every band's search: a country counted with them finds the superset); `Manifest`
(`manifest.sqlite`, `MIGRATIONS` v1-v2 through `cache.migrate`, WAL: `tiles` per (band, name)
pending/running/done/failed, a failure back to pending once (`ATTEMPTS`), an interruption takes no attempt, claims in
`BEGIN IMMEDIATE`, the heaviest first (v2's `weight`, set by each run before its prefetch (`_set_weights`):
`_weights`, the lines of the done tiles whose core overlaps (a real 0 under done tiles without lines); while a pending
tile of the run's bands lies under no done tile (a new country's first run, one stopped before it reached them) every
one by the relief instead, `_relief_weights`: `RELIEF_LINES` × (km² of slopes of `RELIEF_DEGREES` (45°) or more at 30
m in its core, `relief.steep_blocks`/`per_core`) ^ `RELIEF_EXPONENT`, fitted on Slovakia's tiles (docs/performance.md
"Round 4", stage 3's A3); a failure of the relief leaves them as they were; without weights in rowid order), with the
threads of `_threads` (the logical cores shared by the workers still busy; a heavy tile, its weight at least
`HEAVY_SHARE` of the run's largest (`_heavy_weight`), takes instead its share of the cores left after `LIGHT_CORES`
(1: a light tile's worker uses 1.2-1.4 logical cores; 2 left M2's heavy tiles 2 threads beside 9-10 light ones at 12
workers) per light tile running, and a light tile at most `LIGHT_THREADS` while a heavy one runs: measured on
Slovakia's M2 band, docs/performance.md "Round 4"); `_at_border`: a tile whose grid lies inside the outline asks no
neighbour (`Plan.border` False); `run` one row: the bands, the tiles `--max-tiles` still allows, the processes); `run`
(`run.lock`, the bands' `search.fixed_tiles` into the manifest, stale rows back to pending, the free disk, `_prefetch`
per resolution with `sources.download_layers` (terrain, surface when used, the water mask; the blocks of big remote
files in groups of `PREFETCH_GROUP_M`: `group_m`), the numba warm-up `_warm_up`, K `country worker` processes from the
memory of the largest tile (`worker_count`: `WORKER_BASE` + `COUNT_PIXEL_BYTES` per pixel (32 since step 1 runs in
strips and the workers run OpenBLAS on one thread, 64 before: measured on Slovakia's M2 band, docs/performance.md
"Round 4"), not `search.memory_needed`; at most the physical cores, no cap below them (Slovakia's M2 and L at 8, 10
and 12 workers within 3 %: the machine full, fewer workers only move cores from the light tiles to the heaviest; S,
light tiles only, 29.3 min at 12 and 32.6 at 8; the user's choice with `LIGHT_CORES` 1, and how to fit both to a
country's relief and a computer: docs/performance.md, "Round 4"); `--processes 0` in-process; the workers' environment
`_worker_env`: `OPENBLAS_NUM_THREADS=1`, since numpy's and SciPy's copies of OpenBLAS each commit about 32 MB per
logical core when loaded (1.5 GiB of a worker's private bytes on 24 logical cores, reserved and never in its working
set: Windows' commit limit, not the RAM; a count calls no large BLAS routine), so `--processes 0` and a worker started
by hand keep that commit; and `OMP_WAIT_POLICY=PASSIVE` unless the caller's environment sets it (numba's OpenMP
threads spin after each parallel region and take cores from the other workers: sk-sulov's four layer bands −19 % CPU
seconds and −6 % tile seconds, Slovakia's first all-bands run −5.4 % CPU seconds at a wall within the spread, counts
identical; docs/performance.md, "Round 5"); and `PYTHONFAULTHANDLER=1` unless the caller's environment sets it (a
worker that dies of a fatal error writes each thread's Python stack into its log: the pitfall "GDAL's warper on
Windows"); the free disk from `_disk_bytes`: `search.work_bytes` of the band's plan + `AREA_TEMP_BYTES` per pixel of
the largest tile, per worker, plus `DISK_SPARE`) in their own process group, logs in `logs/`, a progress line every
`PROGRESS_SECONDS`, the run's timeline (`_RunSamples`: `logs/samples-<start>.csv` every `RUN_SAMPLE_SECONDS`: the
machine's CPU and memory, the workers' cores, working set and private bytes (each worker's process tree: a venv's
python.exe on Windows runs the interpreter as its child), the tiles being counted, the disks' MB/s), Ctrl+C:
`jobs.kill_tree` and the tiles back to pending, the cube built when every layer band is done; workers stop when
`run.lock` is free, crashed ones are started again; a worker keeps a tile's grids open until they are deleted,
`sources.mosaic.HELD_GRIDS` and `TileWork._remove_grids`, so they never reach the disk, and freezes what its first
tile left alive, `TileWork.loop(freeze=True)`); `TileWork` (a tile: `search.tile_grid` of its core,
`prepare_data(strips=True)` on the tile's own grid (round 3's wave 4's strips for one tile: the grids memory-mapped in
the work folder as the plain path writes them, one int32 array of labels and a strip's temporaries in memory at a
time, no `_tile_data` copy since the window is the grid, the world file's polygons read once per band through
`search_grid`), `count_tile` into a `countcube.TileCounter` through `_Rethreading` (numba's threads set between the
sink's parts to `Manifest.threads`, at most every `RETHREAD_SECONDS`: the tiles counted last take the cores of the
workers that are done) with the band's `sag.TensionTable` made once per process, `countcube.save_tile` with meta:
config, origin, lines, spots, dropped, funnel, seconds, threads (claimed) and `threads_max`, `peak_memory`, commit,
data, and the tile's profile: `stages` ({stage: [seconds, CPU seconds]}, `_StageClock` on the progress bars, "other"
between them), `sink` (`_TimedSink`: the counter), `cpu_seconds`, `memory` (`_MemorySampler` every
`TILE_SAMPLE_SECONDS`: the peak working set and private bytes, `_private`, also per stage), `io` (the process's file
reads and writes, through the system's cache, no memory-mapped grid: the disks are the timeline's)); `build` (every
tile's config and origin checked, `--partial`, cube.json's bands, params, credits as
`search._merged_data`/`_dated_data` plus OSM for an `osm:` outline, notes; a copy of `area.geojson` in `cube/`);
`profile` (per band and stage: hours, share, cores = CPU / wall seconds; the counter's share; the memory, file reads
and threads of a tile; the sums of the last timeline, the machine's disks in GB); `compare` (the control band against
the same length bins of another band per 1 and 4 km cell: lines, spots, ratios, Spearman of spots per cell, "lost",
seconds → `compare.json`); `tests/test_country.py`

## `relief.py`

The relief of a country from Copernicus GLO-30 (the catalogue's `europe` surface layer, the layer's cached reads;
moved from `tools/perf_country.py`, which imports it): `tile_blocks` (a degree tile in blocks of about `BLOCK_M`:
their km², the share of pixels of 30° and 45° or more and the relief over windows of 1, 3 and 5 blocks),
`degree_tiles`, `fetch_relief_tiles`, `proxies_at`; `steep_blocks` (the blocks inside an outline, their centres in a
CRS and their steep km²) and `per_core` (sums per core of a fixed lattice): `country._relief_weights`; numpy, SciPy,
rasterio, pyproj and shapely, no numba; `tests/test_relief.py`
