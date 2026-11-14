---
paths:
  - "findaline.py"
  - "params.py"
  - "search.py"
  - "area.py"
  - "grid.py"
  - "progress.py"
  - "warmup.py"
  - "tests/regression.py"
---
# The search: steps 1-5, options, areas, grids

What each module holds: docs/code-map/search.md. `search.py` is also guarded by other rules, which do not load with
it: read `.claude/rules/line-test.md` before changing what the kernels are given (`_pair_search`, the limits),
`run-files.md` before `save_run` and what a run's files hold, `view3d.md` before `patch_of_line`, `encode_heights`,
`encode_shore`, `reach_of_anchor` or `canopy_of_line`, `country-layer.md` before `_anchors`, `_pair_search`,
`count_tile`, `fixed_tiles` or `tile_grid`, and `sources.md` before step 1 (the mosaic, the filling).

## Must stay in sync

- `params.py` help texts and the options table in README.md describe the same options. The web form is generated from
  `SearchParams` too (`web.schema`): a new field that takes a file path or a secret must be `cli_only`, or the web
  would accept it. `web_only` fields (`geometry`, a drawn area checked by `area.check_geometry`) are set by the
  server, left out of the form, argparse and README.
- Tiled areas (`search.search_lines`): a line belongs to the tile whose core holds its first anchor (smaller x, then
  y); the overlap is `--max-length` + `search._margin` (max of `--prominence-span` and `--drop-radius`, what
  `terrain.py` looks at around an anchor) + 2 pixels so slopes at the edge and the anchor values match one grid; every
  search grid also reaches `_margin` beyond its area (not `profile_of_line`: `with_margin=False`). The pair search of
  a tile starts only from the anchors in its core and takes partners after them in that order
  (`find_valid_lines(first=...)`, `_pairs` with `first_only`), the same rule as the filter in `search._lines`. The web
  worker keeps the tile size of the download phase (`tile_core.json` in the job folder), so both phases announce the
  same tiles. Step 1 runs once on the whole grid (`prepare_data(strips=True)`, the same grid as a search of one grid:
  the gap offsets, the lake levels and the border gaps are the area's) and each tile takes its window (`_tile_data`),
  so R14, `tests/test_offline.py::test_area_in_tiles` and `test_area_in_tiles_with_water_and_gaps` check that tiles
  give exactly the lines of one grid, with the sea, a lake and gaps filled too, and the same terrain statistics
  (counted per tile core, `search._core_window`, on the area's unfilled terrain, and summed); only a cross-CRS mosaic
  warped in strips may differ from one grid's within GDAL's approximate transformer (`test_mosaic_rows_as_whole`). The
  country layer's tiles keep their own step 1, in strips too since 2026-11-04 (`country.TileWork`:
  `prepare_data(strips=True)` on the tile's grid, a plan without tiles, so no `_tile_data` copy: the same
  memory-mapped read-only files and argument types as the plain path,
  `tests/test_country.py::test_tile_in_strips_as_plain`); the cross-CRS caveat applies to them as well: a tile whose
  gaps FABDEM fills, or whose water mask flips a pixel, may count a few lines differently from a count before the
  strips (Slovakia's M2 tiles measured: FABDEM-filled pixels off by up to 0.66 m, median 6 mm, outside the outline; 10
  of 50 M water pixels; the counts of the three tiles equal). A new search field leaves `_search_hash` as before when
  unset (`min_elevation`/`max_elevation` are dropped when None), so unfinished tiled searches of before resume.
- A compute slot's budget (`search.slot_memory`) reserves the quick lane's largest grid (`MAX_MEASURED_PX` squared,
  `memory_needed`) and `DOWNLOAD_PROCESS_BYTES` per download slot (with GDAL's cache of ranges,
  `sources.net.RANGE_CACHE_BYTES`): a change of what the quick lane or a download process may hold changes these. With
  one compute slot nothing is reserved (the memory free at the search's start, as before); the budget is taken once,
  when the `Scheduler` is made, so a phase's tiles never depend on the other jobs running.
- The memory of the grids (`search.PIXEL_BYTES`) is the largest per-pixel peak of steps 1-3 of a tile with a margin
  (`tools/perf_profile.py --cores 7`: a stage's peak RSS less the start's over the tile's pixels, on the Gozo coast
  with `--tile-size 5000`, swiss-long and a Tatras circle of 36 Mpx at 1 m; after wave 2 of round 3: 32 B in step 1 on
  Windows, so 50): a change of what step 1 holds per pixel (`sources/filling.py`, `sources/mosaic.py`, `coast.py`,
  `prepare_data`) or step 2 per pixel or per anchor (`helpers.find_significant_slopes`, `terrain.py`) is measured
  again with it. Since 2026-11-04 step 1 of a tiled search runs once on the whole grid in strips
  (`prepare_data(strips=True)`): its memory no longer follows the tile but the area, about 23 B per pixel of the area
  of RSS on Windows (the Gozo coast, 126 Mpx: 2 850 MB at the surface pair's medians of the gap filling), of which 4 B
  the int32 labels in memory and the rest the resident pages of the memory-mapped grids (file-backed, reclaimable; a
  tile's copies are read through mappings of their own, `_tile_data`, so steps 2-4 of a tile stay at the tile's own
  grids); a change of what the strips hold (`filling.STRIP_PX`) or of the full-grid arrays of step 1 is measured again
  with `tools/perf_profile.py`; it sizes the tiles (`tile_core_size` with `TILE_MEMORY_SHARE` and `TILE_PX_MAX`), the
  quick lane's reserve of `slot_memory` and the refusals of lines, and README's `GRID_MPX_MAX` row and
  `settings.Limits.grid_mpx_max`'s description name its value.
- The memory of the lines (`search.LINE_BYTES`) is the largest per-line peak of steps 3, 4 and 5 with a margin
  (`tools/perf_lines_memory.py --call` on swiss-long, the Gozo coast's large tile and R9, and `--tiles` for the join
  of a tiled search; after wave 5 of 2026-11-01: 389 B, R9's representatives' profiles in step 4, so 450 B; with the
  no-fall zone or the A-frames +16 B of `lift_needed`/`lift_no_zone` through steps 4-5 and +16-24 B of `zone_margins`
  in step 3's join, within the margin, not measured): a change of what steps 3-5 hold per line (`find_valid_lines`'
  parts, `search.line_coordinates`, `mapping.group_lines`, the profiles, `LineTable.join`, the saving) is measured
  again with it. `search._early_check` refuses only what `_check_lines` would refuse too (the same tests without the
  profile points: a lower bound of the need), so a refusal never depends on the size of the evaluated parts: change
  both together.

## Pitfalls

- **Named areas are land**: Nominatim's `osm:Gozo` is the island only (no islets, no sea). `--within osm:<name>`
  therefore selects the coastline/cliffs within `--max-length` of it (`area._near`) instead of clipping to it.
- Grid snapping and the circle mask make results sensitive to the exact centre: a centre 0.4 m away changes a few
  lines at the edge.
- **Memory-mapped files on Windows**: a written page goes to the disk when the last view that wrote it closes, within
  seconds, also for a file deleted soon after; a view kept open until just before the delete writes nothing (4 grids
  of 150 MB: 600 MB against 2, with `flush` 600 MB too). So a temporary grid is deleted right after its view closes
  (`del` every array that still looks into it, or `remove_grid` fails and the file waits for the folder) and a grid
  kept longer goes through `mosaic.flush_grid`, or a tile of the country layer writes its 270-510 MB again.
  `psutil.Process().io_counters()` sees none of it (the tile meta's `io`): the machine's `psutil.disk_io_counters()`
  does. `file.truncate` to make a new grid is no gain: it zero-fills the file on Windows (0.18 s per 150 MB),
  `numpy.memmap`'s byte at the end costs nothing.
- **Search limits** (`Limits`, the worker's) must refuse before the cost they guard: the bounding box (`bbox_km_max`)
  of the area before the source is chosen and before any index, Overpass or data request, then of the grid; the region
  size in `area.region` comes before `osm.theme`, the pixel and tile checks before `_tiles` and `layer.estimate`, the
  line limit before the profiles. They only refuse (or make tiles smaller to fit `grid_mpx_max`): with `limits=None`
  (CLI, regression) nothing changes. The worker passes its `Limits` to its spawned processes as an argument;
  `jobs.ortho_confirm` sets `search.CONFIRM_MINUTES` there (as `pg.TEXT_INTERVAL`).

## Running it

- `python findaline.py --lat 50.1559508 --lon 19.7562722` (Żabi Koń, Poland). `--help` lists everything. Other
  commands (first argument): `cache status|update`, `osm download|update`, `sources check [ID ...] [--deep]`
  (update.py; the probe of every source's services: sources/probe.py), `web` (web.py; runs the worker in-process
  unless `--no-worker`), `worker` (jobs.py: the worker as its own process),
  `country run|status|profile|build|compare <id>` (country.py: the country layer, below; `country worker` is started
  by `run`).
- `--no-plot` is required when running without a desktop session (the matplotlib window blocks). `--yes` skips the
  confirmation questions; without a terminal they default to "no".
- Long runs: start them in the background and wait for the notification. Each search has its own `work/<id>/` (a web
  job `work/jobs/<job>/<phase>`, removed when the job ends or is killed) and downloads write unique `.part` files (the
  worker deletes those older than a day), so searches may overlap, but tests run one after another (each search uses
  all cores).
- Data folder (`--data-dir`, `FINDALINE_DATA`, default the repo): `cache/`, `runs/`, `work/`, `countries/<id>/` (the
  country layer: `country.json`, `area.geojson`, `manifest.sqlite`, `run.lock`, `logs/`, `tiles/<band>/<name>.npz`,
  `cube/`, `compare.json`; the tiles' grids in `work/country-<id>/<band>-<name>/`, removed after each tile); a tiled
  search's work folder holds the area's grids of step 1 (`nmt.npy`, `nmpt.npy`, `obstacles.npy`, `wbm.npy`,
  `water.npy`, `filled.npy`, `joined.npy`, `gap_*.npy`, `mask.npy`; its temporaries `sea.npy`, `sea_zone.npy`,
  `lake.npy`, `bare.npy`, `border.npy`, `footprint.npy`, `edge.npy`, `*_gaps.npy`, `both.npy` while they are used),
  removed after the last tile, and each tile's copies in `tile<k>/` while it is computed; layout and index in
  `cache.py`. `country run` from a worktree needs `--data-dir` of the real data folder (the worktree's own cache is
  empty). A cache without the current `cache/LAYOUT` is refused (decided for the cache layout: no migration code, the
  user moves or deletes the folders by hand).
- Without a terminal, progress is printed as `[Download] ...` / `[Compute] ...` lines every 10 s;
  `FINDALINE_PROGRESS=bars|text` forces a mode.

## Verifying changes

- Speed or memory changes: measure before and after with the tools of docs/performance.md (`tools/perf_profile.py`,
  also `--cores N` like the worker's container and `--tracemalloc`; `tools/perf_lines_memory.py` for the bytes per
  line, `search.LINE_BYTES`), one search at a time, and show that the results are the same: `lines.csv` whole,
  `lines.geojson` up to its `"findaline"` part, `lines.js` and `data.js` from their `"lines":[` (the run's id and time
  differ; `lines.js` names its run before that). A tiled area only with a fixed `--tile-size`: the tiles follow the
  free memory, which moves lines between tiles and reorders `data.js`. The web worker runs each phase in a daemonic
  process, which may not start a process pool: speed a step up inside its process (numpy, numba `prange`, GDAL's
  threads). A country band is compared with its own base commit, on the same day, one run after the other, on a band's
  whole wall: one ended by a single tile moves by about a minute between runs of equal code (Slovakia's L band 16.6
  and 17.4 min), and its tile seconds rise when tiles compete, so its CPU seconds measure the work. A replay of the
  claims with fixed tile seconds overstates a change of order (37 % promised, 8 % measured).
- The Polish set (R13, R1–R5) takes about 3 min with an empty geoportal cache; run the tests one after another, never
  two searches at once.
