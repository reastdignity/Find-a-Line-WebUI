# Code map: the country layer

What the modules of this area hold, in detail: the country layer. Moved out of CLAUDE.md on 2026-11-12; nothing loads
this file by itself, so read the entry of a module before a large change to it. What must stay in sync and the
pitfalls are in `.claude/rules/` (country-layer).

## `countcube.py`

The counter cube of the country layer, v2 (docs/country-precompute/contract.md, sections 2 and 6): rows
`[key_a, key_b, count]`, word A the flag pairs of water and trees, the 3-bit bins of height, clearance, wall and the
weaker anchor's prominence, the length mask on `LENGTH_EDGES`, the border (0 interior, 1 across and owned, 2 across
and the partner's) and partner fields (1-6 an index into cube.json's `neighbours`, 7 unknown) and the cell's row and
column, word B the 3-bit bins of `B_FIELDS` (metres over water, both anchors' heights, mean height, stronger
prominence, drop, high share, height difference, clearance over trees, the A-frame with and without the no-fall zone),
all on `EDGES` by `KINDS` (floor, below, at_most; `UNKNOWN` for NaN; word B's edges chosen by the user on 2026-11-08
from wave A's measurement, docs/country-precompute/contract.md "The key v2"); cells of one global lattice
(`CELLS_PER_DEGREE` 120: 30″, levels 1/2/4/8 of it; a line's cell that of its first anchor by (lon, lat); the
country's `origin_of` in cells, floored to `ALIGN_CELLS`); spots as pairs of 1.5″ anchor clusters (`spot_ids`,
`merge_spots` on word B: a floor's largest bin, a ceiling's smallest; the border and partner a spot's identity);
`TileCounter` fed by `search.count_tile` (the core and band filters, a line across a border (its `border` not 0)
skipping the core's test in both engines, `countkernels.select(border=)`: `count_tile` hands only the lines whose
anchor in the country lies in the core; the parts' optional `partner` and `border` columns, absent 0; each anchor
pixel through pyproj once; `ENGINE` numba, the hash tables of `countkernels.py` imported at its first part, or numpy,
the reference), `save_tile`/`load_tile` (npz, `VERSION` 2), `build` (lines summed, spots merged over all tiles and
bands, the levels, `lines_<L>.npy`/`spots_<L>.npy` [key_a, key_b, count] sorted, `cube.json` last: `cell_deg`,
`edges`, `kinds`, `neighbours`, `totals.border`), `Filters` (+ `parse` of the web's query; `border` all or own and
`replaced`, the partners whose own cube replaces their partner lines: `border_kept`) and `select` (`skip=` one of
`DIMENSIONS` leaves that dimension's condition out, never the border's; `_conditions` each condition's mask of rows,
the flags' apart), `Cube` (arrays read into memory when first used, once: keys and counts views of the (n, 3) rows,
one array read at a time; not mapped: Windows would refuse the next build's replacing them; lon/lat rectangles without
pyproj: `box`, `auto_level`, `cell_count`, `_cells_of` a request's cells (a rectangle: the box's; with a view those
reaching it, `_reach` by column and row), `_ranges` their rows (two binary searches on word A per column: the rows
are sorted by cell), `_chunks` (`CHUNK_ROWS` rows at a time, a request's `check` called before each: where
`web.LayerSlots` stops it), `cells` (`sides=True`: a row per cell and side, 0 the country's own lines, else the
partner index of its partner lines; the side 0 rows summed by runs of cells), `histogram` (the counts per bin of each
dimension, each under every filter but its own: a line's one length bit partitions the total, a spot's ORed bits make
its bins upper bounds; one pass in chunks, the masks of all conditions but one only for the active ones,
`_all_but_one`, the dimensions without a filter by `GROUPS` of up to four adjacent fields in one bincount each;
`view=` only the cells reaching a WGS84 view, `reaching`: their rounded corners' box intersects it, as the page counts
its total in view; `summary=True` adds both modes' `totals` and the lines' `border` split; their answers are those of
`tests/cube_oracle.py`, the code of b45b950 frozen as the tests' oracle), `corners`,
`cell_km2` (`lattice_km2`: a whole cell's on the ellipsoid), `outline_simplified` (the outline for a map at
`OUTLINE_TOLERANCE`, coordinates of `OUTLINE_DECIMALS`, with the original's km², kept per tolerance), `cut` (the
level's cells the outline cuts: the km² inside, from the exact outline, and that part as polygons of rings of [lat,
lon], simplified by the cell's side over `CUT_SIMPLIFY`; all levels at the first call by a quadtree, `_cut_cells`,
each piece cut out of its parent's: Slovakia 0.3 s; kept, the exact pieces too; none without an outline),
`cut_outside` (a partner row's part of its cell: beyond the outline within the layer's reach, `reach_m` (its layer
bands' longest line): the rectangle less the exact part inside, clipped to the outline grown by the reach in the
cube's CRS, `_reach_zone` (simplified by `ZONE_SIMPLIFY_M` first); a whole part not listed; kept per cell)),
`cell_request` (the search of one cell for the app's form: the level's rectangle buffered by the band's `max_length`,
not cut by the outline, a cell farther than that from it refused: a partner row's cell beyond the border is searched
too); numpy, pyproj and shapely only (the web process imports it: no numba)

## `country.py`

The country layer's driver (`findaline.py country run|status|profile|build|compare|worker <id>`,
docs/country-precompute/contract.md section 3): `Band`/`Country`, `Profile`/`PROFILE` (the layer's profile, R7, the
user's choice of 2026-11-12: S 30-300 m at 1 m, M 300-1000 m at 2 m, L1 1-2 km at 3 m, L2 2-5 km at 5 m, all sag and
in the layer, no control band, `tests/test_country.py::test_profile_is_the_chosen_one`; T(L), Silk 99, one for every
country; its sha256 is cube.json's `profile`, part of `config_hash` and of every tile's meta, and `build` refuses a
tile of another; `Country.bands`/`tension`/`rig` default to it, a `country.json` may override them: a study area, a
test), `COUNTRIES` (Slovakia with the recount's options of 2026-11-07/08: the surface model marking, `end_zone` 5 and
`anchor_lift` 2, `tests/test_country.py::test_slovakia_counted_with_the_recount_options`); `NEIGHBOUR_CUBES` (the cube
id of every source some `Source.neighbours` names: `tests/test_country.py::test_neighbour_cubes`) and
`neighbour_cubes` (cube.json's `neighbours` in the order of `Source.neighbours`: a line's partner index k is the k-th;
[] for a study area or an elevation file); the territories that name a line's partner (`territory_specs`: a cube's
outline specs from `sources.AREA_NAMES`; `neighbours.geojson`, `ensure_neighbours`/`write_neighbours` at `run`'s
set-up: each declared neighbour's outline within `territory_reach` of the outline, fetched once, a failed fetch stops
the run; `load_territories` once per worker; its sha256 in each border tile's meta and in cube.json,
`_requeue_border_tiles` sends a border tile, decided from its grid by `_at_border`, with another back to pending,
`build` refuses one); `country.json` (the config, `hash` = sha256 of the config and of `area.geojson`'s sha256, with
the surface model also of `obstacles.RULE` (another rule counts the tiles again), `crs`, `origin` =
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
neighbour (`Plan.border` False); `tile_plan` a tile's plan (`search.tile_grid` of its core within the band's grid, the
band's grid as its `search_grid`), at a country's border (not a study area's) with `Plan.partners` the band's
`max_length` and the footprint (`grid.area_shape`) the outline grown by `partner_reach` (the band's longest line and
two pixels: the overlap's terrain margin changed no count of Slovakia's 367 S border tiles and cost 27 % more tile
seconds, `reach_shape`), so the neighbours fill beyond the outline; a country's band grid grown by its `max_length`
(`_grown`: a tile at the outline box's edge keeps its partners); `_prefetch(across=)` and `_disk_bytes(across=)` (the
partner grid and its zone) on that footprint, and `_prefetch(tiles=)` the neighbours' terrain (and surface model when
the bands use one; their fill reads no water mask) over the windows the pending border tiles may ask, in the same pool
(`_neighbour_layers`: a grid per neighbour over `neighbour_shapes`, the bands' boxes on their footprints;
`neighbour_boxes`: per border tile the footprint's strip beyond the outline within its grid under the neighbour's
rough boxes, grown by `NEIGHBOUR_PAD` and two pixels, which holds every `filling.neighbour_window` of the tile while
the source's own data cover the outline: `tests/test_country.py::test_prefetch_holds_every_neighbour_window`), else
each border tile fetched them in its step 1 block by block under its own host slots; `run` one row: the bands, the
tiles `--max-tiles` still allows, the processes); `run` (`run.lock`, the bands' `search.fixed_tiles` into the
manifest, stale rows back to pending, the free disk, `_prefetch` per resolution with `sources.download_layers`
(terrain, surface when used, the water mask; the blocks of big remote files in groups of `PREFETCH_GROUP_M`:
`group_m`), the numba warm-up `_warm_up`, K `country worker` processes from the memory of the largest tile
(`worker_count`: `WORKER_BASE` + `COUNT_PIXEL_BYTES` per pixel (32 since step 1 runs in strips and the workers run
OpenBLAS on one thread, 64 before: measured on Slovakia's M2 band, docs/performance.md "Round 4";
`COUNT_SURFACE_PIXEL_BYTES` 48 with a surface model: a tile's peak follows its anchors, its steepest tile sets the
figure), not `search.memory_needed`; at most the physical cores, no cap below them (Slovakia's M2 and L at 8, 10 and
12 workers within 3 %: the machine full, fewer workers only move cores from the light tiles to the heaviest; S, light
tiles only, 29.3 min at 12 and 32.6 at 8; the user's choice with `LIGHT_CORES` 1, and how to fit both to a country's
relief and a computer: docs/performance.md, "Round 4"); `--processes 0` in-process; the workers' environment
`_worker_env`: `OPENBLAS_NUM_THREADS=1`, since numpy's and SciPy's copies of OpenBLAS each commit about 32 MB per
logical core when loaded (1.5 GiB of a worker's private bytes on 24 logical cores, reserved and never in its working
set: Windows' commit limit, not the RAM; a count calls no large BLAS routine), so `--processes 0` and a worker started
by hand keep that commit; and `OMP_WAIT_POLICY=PASSIVE` unless the caller's environment sets it (numba's OpenMP
threads spin after each parallel region and take cores from the other workers: sk-sulov's four layer bands −19 % CPU
seconds and −6 % tile seconds, Slovakia's first all-bands run −5.4 % CPU seconds at a wall within the spread, counts
identical; docs/performance.md, "Round 5"); and `PYTHONFAULTHANDLER=1` unless the caller's environment sets it (a
worker that dies of a fatal error writes each thread's Python stack into its log: the pitfall "GDAL's warper on
Windows"); the free disk from `_disk_bytes`: `search.work_bytes` of the band's plan + `AREA_TEMP_BYTES` per pixel of
the largest tile, per worker, plus `DISK_SPARE`, and the cache's growth: `prefetch_bytes`, the layers' `estimate` on
the grids the prefetch fetches (`_prefetch_groups`, also `_prefetch`'s), each tile once over the resolutions; refused
before any download with both parts named; `tests/test_country.py::test_disk_check_counts_the_prefetch`) in their own
process group, logs in `logs/`, a progress line every `PROGRESS_SECONDS`, the run's timeline (`_RunSamples`:
`logs/samples-<start>.csv` every `RUN_SAMPLE_SECONDS`: the machine's CPU and memory, the workers' cores, working set
and private bytes (each worker's process tree: a venv's python.exe on Windows runs the interpreter as its child), the
tiles being counted, the disks' MB/s), Ctrl+C: `jobs.kill_tree` and the tiles back to pending, the cube built when
every layer band is done; workers stop when `run.lock` is free, crashed ones are started again; a worker keeps a
tile's grids open until they are deleted, `sources.mosaic.HELD_GRIDS` and `TileWork._remove_grids`, so they never
reach the disk, and freezes what its first tile left alive, `TileWork.loop(freeze=True)`); `TileWork` (a tile:
`search.tile_grid` of its core, `prepare_data(strips=True)` on the tile's own grid (round 3's wave 4's strips for one
tile: the grids memory-mapped in the work folder as the plain path writes them, one int32 array of labels and a
strip's temporaries in memory at a time, no `_tile_data` copy since the window is the grid, the world file's polygons
read once per band through `search_grid`), `count_tile` into a `countcube.TileCounter` through `_Rethreading` (numba's
threads set between the sink's parts to `Manifest.threads`, at most every `RETHREAD_SECONDS`: the tiles counted last
take the cores of the workers that are done) with the band's `sag.TensionTable` made once per process,
`countcube.save_tile` with meta: config, profile, origin, partners (the metres of `Plan.partners`, None inside),
neighbours_sha256 (None inside), lines, spots, dropped, funnel, seconds, threads (claimed) and `threads_max`,
`peak_memory`, commit, data, and the tile's profile: `stages` ({stage: [seconds, CPU seconds]}, `_StageClock` on the
progress bars, "other" between them), `sink` (`_TimedSink`: the counter), `cpu_seconds`, `memory` (`_MemorySampler`
every `TILE_SAMPLE_SECONDS`: the peak working set and private bytes, `_private`, also per stage), `io` (the process's
file reads and writes, through the system's cache, no memory-mapped grid: the disks are the timeline's)); `build`
(every tile's config, profile and origin checked, a border tile's `neighbours_sha256` too, `--partial`, cube.json's
bands, params, `profile`, `neighbours`, `neighbours_sha256`, credits as `search._merged_data`/`_dated_data` plus OSM
for an `osm:` outline, notes (`_border_notes`: a country's lines across the border and its hard borders,
`_hard_borders`: the coverage map's outlines next to the outline that no neighbour's source covers, ISO codes, the
country holding the outline its own, named in the note by tzdata's `iso3166.tab` with its odd names replaced by the
page's (`COUNTRY_NAMES`: the browser's `Intl.DisplayNames`, "Czechia", "United Kingdom"),
`_country_names`/`_names_text`: "Hungary and Ukraine"; never a sentence per neighbour, which the page writes from
`neighbours`; a study area "Only lines with both anchors inside <name> are counted."); a copy of `area.geojson` in
`cube/`); `profile` (per band and stage: hours, share, cores = CPU / wall seconds; the counter's share; the memory,
file reads and threads of a tile; the sums of the last timeline, the machine's disks in GB); `compare` (a country's
control band, none in `PROFILE` (`_compared_bands`: a plain message then), against the same length bins of another
band per 1 and 4 km cell: lines, spots, ratios, Spearman of spots per cell, "lost", seconds → `compare.json`);
`tests/test_country.py`

## `relief.py`

The relief of a country from Copernicus GLO-30 (the catalogue's `europe` surface layer, the layer's cached reads;
moved from `tools/perf_country.py`, which imports it): `tile_blocks` (a degree tile in blocks of about `BLOCK_M`:
their km², the share of pixels of 30° and 45° or more and the relief over windows of 1, 3 and 5 blocks),
`degree_tiles`, `fetch_relief_tiles`, `proxies_at`; `steep_blocks` (the blocks inside an outline, their centres in a
CRS and their steep km²) and `per_core` (sums per core of a fixed lattice): `country._relief_weights`; numpy, SciPy,
rasterio, pyproj and shapely, no numba; `tests/test_relief.py`
