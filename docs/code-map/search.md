# Code map: the search

What the modules of this area hold, in detail: the search. Moved out of CLAUDE.md on 2026-11-12; nothing loads this
file by itself, so read the entry of a module before a large change to it. What must stay in sync and the pitfalls are
in `.claude/rules/` (search-pipeline, line-test, run-files).

## `findaline.py`

Command line only: options from `params.py`, messages, questions, the list of spots, the matplotlib window;
`cache`/`osm`/`web`/`worker` as first argument go to update.py / web.py / jobs.py

## `params.py`

`SearchParams` (pydantic: fields, help, groups, validation) and `CliOptions`; argparse is generated from them; the
topic "rigging" holds `end_zone` (0-`END_ZONE_MAX` 20 m) and `anchor_lift` (0-`ANCHOR_LIFT_MAX` 3 m), both 0 by
default

## `search.py`

The search as a library: `plan_search`, `estimate_search` (the layers' indexes at once, as `download_layers`; the
working grids from `work_bytes`, the bytes per pixel `prepare_data` writes, for a tiled search those of the whole grid
plus `AREA_TEMP_BYTES` of step 1's temporaries and the largest tile's copies, `tile_bytes`:
`tests/test_offline.py::test_work_estimate_counts_the_grids_written`), `download_data` (cache only, for the web
worker; the coastline's theme tiles and the run's place name (`_run_name`: Nominatim's answers cached for step 5) in
threads alongside the tiles' pool), `prepare_data` (step 1; its surface is `obstacles.obstacle_surface` of the run's
rule, `Plan.obstacles`, in `work/obstacles.npy`; `Plan.border` False asks no neighbour, burns no outline (a full mask,
`_area_mask_rows(full=)`) and counts no coverage (the country layer's tiles inside the outline); the area mask
computed once per grid, `Data.mask`, also for step 2's anchors; the sea mask and the water body mask released once
their last use is done; the heights of the area's land with data counted before any filling,
`hypsometry.land_histogram` in the bar "terrain statistics", within a tile's core (`_core_window`: pixel centres,
half-open, as a line's first anchor) into `Data.terrain`; `statistics=False` for `profile_of_line`), `find_lines`
(2-4; step 2 is `_anchors(plan, data, quiet)` → `Anchors(anchors, prominence, drop, strong)` or None for a tile
(`count_tile` passes `deferred=True`: with no limit on them prominence and drop stay None and `_pair_search` gives
`find_valid_lines` a `linesearch.LazyAnchorValues` of `_anchor_values(crop=True)`: the anchors of each part's lines,
each once, after `SUBSET_CALLS` computations every useful anchor not known yet in the rows a later line can reach),
the shape the branch country-precompute shares; the seams of filled gaps and a neighbour's data tested at the anchors
only, `at_seams`: scipy's 3 × 3 dilation and not erosion read at the anchors,
`tests/test_units.py::test_seams_as_before`; `Lines.terrain` = `hypsometry.statistics`), `save_run` (5: the run and
the map, nothing downloaded; the line files of a run of `saving.MIN_LINES` lines or more by the children of
`saving.py` when `line_threads` gives 2 or more, the small files and `map.html` by itself between the two bars; below
that, or with one thread, in its own process as before), `orthophoto_lines` and `download_orthophoto` (the orthophoto
for offline use, a step after the run: the lines of the best groups by the detail rules, the tiles not cached yet, the
question over `CONFIRM_MINUTES`; `run_search` and the CLI call it right after `save_run`, the web worker after "done";
the map names the cache folder either way and loads a tile online until it is there), `run_search`; `patch_of_line`
(the 3D view's patch: the run's source, resolution and filling, its surface model only for the shore faces
(`plan.obstacles = None`: the terrain is drawn), the kinds of the uncertain shore deflated after the heights
(`encode_shore`, the meta's `shore_bytes` and `shore_sha256`; `web.patch_body` checks both blocks), on a square
polygon in the run's CRS of 512·n+1 samples a side, `step` 2 for phones; `encode_heights`, docs/3d-view-contract.md
"Body"); the kernels' modules (`linesearch`, `lineprofiles`, `terrain`: numba) imported inside `_lines` and
`line_coordinates` only, so the download phase never loads numba and the quick lane only at its first reach task
(`tests/test_units.py::test_search_imports_numba_only_to_compute`, `tests/test_patch.py::test_patch_loads_no_numba`);
`reach_of_anchor` (the 3D view's "only valid lines" and "lines from a point": the patch's square at step 1 with the
run's obstacle rule, one fixed pixel, every sample of a lattice within the run's limits of length and height
difference evaluated by `linesearch.evaluate_lines` on `REACH_THREADS` threads in the order the page asks the profile;
the lattice 1 up to `REACH_FULL_TARGETS` targets, else 2; one uint8 a sample: the clearance in `REACH_QUANTUM` steps
and `REACH_TREES`) and `canopy_of_line` (the run's obstacle surface less the terrain on the patch's grid, uint8 half
metres: the 3D view's trees and buildings); `Plan.funnel` the counts of the line search (`jobs.FUNNEL_STEPS`: `_lines`
adds grids, anchors, anchors kept and the lines of a tile's core, `find_valid_lines(stats=)` the rest; one dict for
the tiles through `dataclasses.replace`); messages via `on_event`, questions via `confirm`; optional `limits`
(`plan_search(limits=...)`, `Plan.limits`, `check_estimate`, anchors and lines in `_lines`: the lines of the tiles
done already count too, and lines that would not fit into `Plan.memory` (free at the start, or `plan_search(memory=)`:
a compute slot's budget, `slot_memory`, for every user, also for the tile size) with the grids are refused:
`memory_needed`, `PIXEL_BYTES`, `LINE_BYTES`, `PROFILE_POINT_BYTES` for a circle's profiles of every line, also the
tile size and `memory_warning` at the worker's start; `tile_core_size`: a tile's core from `TILE_MEMORY_SHARE` of the
budget at `PIXEL_BYTES` per pixel, at most `TILE_PX_MAX` pixels whatever the memory), off by default, so the CLI and
the regression checksums are unchanged; F7: `find_valid_lines(check=_early_check(...))` stops at `lines_max` (with
limits) or `Plan.memory` (for every user) after the first evaluated part over it (`Plan.early_stop`:
`Limits.lines_early_stop`, set by `jobs.run_phase` from the server's `Limits` for every job; codes
`too_many_lines_early`, `too_many_lines_memory_early`), the final `_check_lines` stays; step 4 before the groups works
on one table, in place (`line_coordinates`: `mapping.coordify` in `COORDINATE_PART`s, the core's lines through
`LineTable.reorder`, the metres over water and gaps: `linesearch.covered_metres`); `_lines` returns the lines without
their pixel columns (`LineTable.without_pixels`; `search_lines` takes them out of every tile it loads, of tile files
written before too) and `search_lines` runs step 1 once on the whole grid for a tiled search
(`prepare_data(strips=True)`: the area's grids memory-mapped in the work folder, the operations in strips of rows
(`filling.STRIP_PX`, `rows=`), the gap offsets, the lake levels and the border gaps the area's, `Data.tile_terrain`
the histogram of each tile's core (`_core_window` on the unfilled terrain, so the tiles' `.terrain.npz` and resuming
stay as they were), the area's grids made again on resume and removed after the last tile, `_remove_grids`), copies
each tile's window into contiguous memmaps of `work/tile<k>/` (`_tile_data`, `_tile_window`: nmt, surface, water,
filled, joined, slope, the mask in memory: steps 2-4 read what they read before, the kernels' argument types stay),
runs `_lines` per tile, computes the profiles at tile edges under `_silent_progress` (`profile_of_line`'s own step 1
leaves the bars and the step alone) and joins the tiles' lines column by column (`LineTable.join`); for the country
layer (docs/country-precompute/contract.md): `plan_search(tiled=False)` (an area without tiles), step 2 as `_anchors`
(`Anchors`) and step 3's arguments as `_pair_search`, both shared by `_lines` and `count_tile` (steps 2-3 into a sink,
each part with `water_px`; no step 4, no "no lines" errors, no `_early_check`/`_check_lines`; no "lines" funnel count,
the sink's `TileCounter.lines` instead; across a border, `Plan.partners` (the metres beyond the outline within which a
country's border tile pairs anchors on a neighbour's or its source's own data with those inside: `country.tile_plan`):
`Data.partner` (uint8 memory-mapped: `sources.filling.partner_zone`/`partner_grid` before the filling,
`fill_from_neighbours(partner=)` during it, `resolve_partners` with `Plan.territories` after it), `_anchors` takes the
anchors where it is not 0 too (`_with_partners`), `_pair_search` adds them to the first-anchor mask and marks them and
the country's anchors outside the core (`find_valid_lines(partner=)`: a partner pairs only with the core's anchors in
the country, so one tile finds a line across), `count_tile` adds each part's `partner` (uint8: at the anchor beyond
the outline, 0 inside) and `border` (int8: 0 inside, 1 the anchor in the country first by (lon, lat), else 2) by
`_BorderSides`, through countcube's transformer as `TileCounter` takes the first anchor), `fixed_tiles`/`FixedTile`
(cores at multiples of `core_m` in the plan's CRS, named `E<left>_N<bottom>`), `tile_grid` the grid of a tile for
`_tiles` and `fixed_tiles` and sums their histograms (`tiles/<k>.terrain.npz`, `TERRAIN_FILE`: saved before the tile
file, loaded with it on resuming; a finished tile without one makes the run's terrain None); `save_run` writes
`meta["terrain"]` and prints "Terrain of the search area: ..."; the uncertain shore
(`sources.filling.shore_segments`): `prepare_data(shore="segments")` into `Data.shore` after the water filling (the
bar "uncertain shore"; a `messages.Note` `shore_uncertain` from `SHORE_WARN_M`), `Lines.shore` (`find_lines`;
`search_lines` keeps the area's in the run folder's `SHORE_FILE` for a resumed search), `meta["shore"]` of run.json
and data.js; where the land's terrain came from (`sources.filling.terrain_origins`, `_terrain_sources`): after
the gap filling, only for a run's search (`shore="segments"`, `plan.border`), an info line of the shares and a
`messages.Note` `terrain_fallback` from `FALLBACK_WARN_SHARE` (10 %) of the land from fallbacks, into
`Data.terrain_sources`, `Lines.terrain_sources` (a tiled search's in `ORIGINS_FILE`, as the shore's),
`meta["terrain_sources"]` of run.json and the head of data.js only when known (not lines.js, not runs.js);
`shore="kinds"` for the 3D view's patch (`Data.shore_kinds`, `work/shore.npy`), `shore="none"` for a
profile and the country layer's tiles; `--min-elevation`/`--max-elevation` keep the anchors within the band in
`_anchors` right after they are found (float32 heights; before `ANCHORS_MAX`, the prominence and the drop, so the
funnel's `anchors_kept` counts it; `no_anchors_in_elevation_range`), `_search_hash` drops them when unset; the no-fall
zone and the A-frames (`Plan.end_zone`, `Plan.lift`, printed as "Ends: ..."): `_pair_search` hands them to
`find_valid_lines` (with `zones=(0, end_zone)`, whose bucket minima `zone_margins` become `lift_needed`/`lift_no_zone`
through `helpers.lift_values` and are dropped from the table, in count mode from each part before the sink gets it),
`_fixed_order` sorts exactly tied lines by their anchors' pixels only when one of them is set (tiles then give one
grid's rows in one order), `_run_values` reads a run's pair from run.json (0/0 for runs before) for `profile_of_line`,
`reach_of_anchor` and `patch_of_line` (`_end_keys` in the meta), `_search_hash` drops them at 0

## `area.py`

Search areas (`Circle`, `Polygon`): grid bounds, mask, shapes for maps and orthophoto; `from_spec` builds `--area`
(coast, cliffs, file, osm:name)

## `grid.py`

Working grid (metric CRS: the source's, or the UTM zone of the centre, `Source.local_crs`: NAD83 / UTM for the USA,
`nad83_utm_crs`; edges on the source's pixel edges, `Source.grid_origin`)

## `helpers.py`

Anchors (`find_significant_slopes`: blocks of 256 rows on a thread pool of `threads` (`search.line_threads`, or min(8,
CPUs)), the slope in place, the anchors joined in the blocks' order: row-major, exactly the single-threaded pass's,
`tests/test_units.py::test_significant_slopes_as_before`), line evaluation (DDA), line profiles, webbing heights, wall
angles, `LineLimits`; the no-fall zone and the A-frames (`end_zone_rule`: a pixel passes when its strict margin
`limit − terrain` exceeds `−lift − δ·[in the zone]`, `δ = end_delta(sag_table, end_clearance)` the fall allowance; the
zone `min(end_zone, ZONE_CAP·L)` from each anchor as `zone_steps` counts it (`kz`, a step k in it iff
`min(k, steps − k) < kz`); `evaluate_line`/`line_profile(..., end_zone=, lift=, end_clearance=, zone_cap=, zones=)`,
refusing a negative value and `end_clearance` over the fall; `zone_columns`/`valid_at`/`lift_values` the per-line
bucket minima of a `zones` ladder and the two saved values `lift_needed` (with the run's zone, at most the run's lift)
and `lift_no_zone` (`END_VALUES`); `webbing_height(margin, sag_table, lift)`: the heights with the A-frames, the lift
added last and only when not 0); `LineTable`: the lines as numpy columns (and the profiles of the rows that have one)
from `find_valid_lines` to the saved files, `row(k)` a line as a dict; `Profiles` (a batch of profiles as arrays) and
`Profile` (one line of it, the value of `LineTable.profiles`), `profile_dict` (either, or a dict of `line_profile`, as
that dict); `LineTable.reorder` (`take` in place, one column at a time), `LineTable.join` (`concat` of tables not
needed afterwards, one column at a time: the tiles of `search.search_lines`), `without_pixels` (drops the pixel
columns "a1"/"a2" at the end of `search._lines`: what comes later, step 5, the profiles at tile edges, the
orthophoto's spots and the command line's list, reads the coordinates)

## `terrain.py`

How far anchors stand out: prominence (union-find, numba, over the pixels within the span of an anchor only:
`_window`, the others cannot change it) and drop (separable van Herk minimum, numba parallel, the column pass at the
anchors only); both equal the old whole-grid versions bit for bit
(`tests/test_units.py::test_prominence_and_drop_match_the_whole_grid` keeps them); `prominence` skips its lexsort of
the anchors when they come row-major (from `find_significant_slopes`); any subset of the anchors gets the values it
has among all of them, and `crop=True` computes them on the part of the grid within reach of the subset (the grid's
own rows when that part spans its width, else a read-only float32 copy; the kernels' argument types unchanged either
way: the count mode's lines, `tests/test_units.py::test_prominence_and_drop_of_a_subset`)

## `obstacles.py`

Which pixels of the surface model are obstacles (trees, buildings) and not the terrain's own rock: `obstacle_surface`
keeps the surface only where it stands more than `MIN_HEIGHT` (1 m) above the terrain's `envelope` (the highest
terrain within `RADIUS` = 2 pixels, `scipy.ndimage.maximum_filter`), the terrain elsewhere and on `bare` pixels (water
filled where the terrain had no data), NaN without surface data; blocks of rows with a halo (`bare` may be
memory-mapped: a tiled search's `bare.npy` of `fill_water`); `RULE` (what a search applies and run.json records),
`reach`, `is_obstacle`, `slope_degrees` (as `helpers.find_significant_slopes`), `wall` (a wider envelope near steep
terrain: measured, not used); chosen with tools/obstacle_study.py (docs/roadmap.md); `tests/test_obstacles.py` (grids
made from a fine surface: terrain at the pixel's centre, surface its highest point)

## `hypsometry.py`

The terrain of a search area, for the viewer's percentile filters (docs/roadmap.md, "Elevation filters"): `Histogram`
(exact counts of 0.1 m bins (`BIN_CM`) from `LOW_CM` (-1000 m) to `HIGH_CM` (10 000 m), heights outside in the end
bins, and the sum in centimetres; tiles add up with `+` in any order), `land_histogram` (the land with data in the
area mask: the source's finite terrain before any filling, less `sources.filling.water_with_data`; centimetres
`np.rint(z * 100)` in float64, exactly the saved `round(e, 2)`; blocks of rows, a window for a tile's core: a tiled
search counts every core's window on the area's unfilled terrain, `search.Data.tile_terrain`), `statistics`
(`{"mean", "quantiles", "km2"}`: `quantiles[p]` the lower edge of the first bin whose cumulative count reaches max(1,
ceil(p·n/100)), p = 0..100; None without land), `save`/`load` (a tile's `.npz` without pickle; `load` None when
missing or of other bins); numpy only; `tests/test_hypsometry.py`

## `linesearch.py`

The pair search (numba): free directions per anchor (`free_directions`: `_free_rings` on `RING_CHUNK` anchors at a
time, the sectors of the ring pixels as bit masks (`_sector_masks`) instead of angles, rings up to `largest_need`,
kept as uint8 rows of the anchors with an open direction only, `slot` their row), bucketed pairs (`pair_arguments`;
`pair_chunk`: one pass of `_pairs` holding each anchor's first `PAIR_BUFFER` pairs in a buffer, at most
`PAIR_BUFFER_BYTES` a chunk, then a writing pass for the anchors that found more only; `_pairs` skips the cells and
partners that would fail the dedup, distance, height or rings test; F8c (2026-11-03): the cells outside the anchor's
open sectors (`_cell_sectors`: the sectors of a cell's corners with one of margin, `_arc`), the cells with no partner
open for `smallest_need` towards the anchor (`_cell_open` of `pair_arguments`, a uint64 per cell) the partners whose
need exceeds the anchor's largest ring in their cell's sectors and those with no sector open for `smallest_need`
towards their cell's sectors (`_open_masks`, a uint64 per useful anchor), all skipped before the candidates are
counted; the count mode across a border: the optional uint8 `partner` per anchor, the tail's last element
(`pair_arguments(partner=)`, `find_valid_lines(partner=)`), a pair of two marked anchors skipped before every other
test, empty the pairs of before bit for bit: `tests/test_units.py::test_pairs_with_partners_match_reference`),
early-exit line check (`_line_ok`: the comparison `strict = −EPS − lift`, `lenient = −EPS − lift − δ` inside the zone
(`_zone_steps`, `_margin_at`: helpers.end_zone_rule; with a zone the first strict step at each end is tested first),
the limit's arithmetic untouched, so at 0/0 today's bits; `_free_rings` takes
`ring_offsets(offset, res, kmax, end_zone, lift, delta)`, a ring k relaxed by δ iff `(k−1)·res < end_zone`, all less
the lift: sound, never too little; from both ends inwards, the middle of lines of more than `LINE_ORDER_SPLIT` and at
most `LINE_ORDER_MAX` steps in bit-reversal order); `find_valid_lines(stats=)` adds the funnel's counts of a call
(`jobs.FUNNEL_STEPS`); the pairs found are evaluated (`evaluate_lines`: the kernel `_evaluate`, the numpy around it,
wall angles, which lines pass and the table's columns, in blocks of at least `VALUE_BLOCK` pairs on a thread pool of
numba's threads, every value an element's own, so the blocks change none) straight from the chunks' arrays
(`evaluation_parts`: parts of at least `EVAL_PART` pairs, each chunk released once handed out), the parts joined
column by column (`join_tables`) and sorted in place (`LineTable.reorder`), `check=` called with the valid lines so
far after each part (F7: `search._early_check`); `covered_metres` returns a float64 array, `COVERED_PART` lines at a
time, rounded by `runs.round_floats`; `find_valid_lines(sink=)` the count mode (`search.count_tile`; `anchor_values`
may be a callable there, asked once by the first part with a valid line, or a `LazyAnchorValues`, asked by each part
with its passing pairs, so with the anchors of its lines (each anchor once; after `SUBSET_CALLS` computations every
useful anchor not known yet from the rows of the pending pairs' first anchors less the longest line, `floor`),
`_sink_lines` putting the bar of the pairs back after each): `SINK_CHUNK` anchors per `pair_chunk` with a buffer of
`SINK_PAIR_BUFFER` (8192) pairs per anchor within `SINK_PAIR_BUFFER_BYTES` (more than any anchor of Slovakia's
heaviest tiles finds, so they need no writing pass; the search path keeps `PAIR_BUFFER`), the pairs evaluated once
`EVAL_PART` are pending, parts of at most `SINK_PART` handed to the sink, nothing joined, sorted or kept (returns
None; not with `check`); `covered_pixels` (int64: the pixels of `covered_metres` set in a mask)

## `lineprofiles.py`

The profiles of many lines at once (numba, `prange` over the lines): `line_profiles` gives `helpers.line_profile` of
each line, exactly, as a `helpers.Profiles` (float64 `d`/`z`/`s` with NaN for None, uint8 `w`/`g`, the small values
per line, `flags`), about 26 B per point; the end zone and the lift as `line_profile` takes them
(`Profiles.zone`/`lift`, written into a profile only when not 0); thinned lines compacted in place (`_compact`),
rounded afterwards as `line_profile` rounds (`runs.round_floats`; `np.round` for the distances of "min", "min_nmpt",
"max_height"), part by part; used by `search._lines` for every wanted line (imports numba: never from the web process)

## `sag.py`

Sag estimator (elastic catenary + point load) and envelope table for `--model sag`; `parse_tension`, `tension_at`,
`TensionTable` (T(L) of the country layer: each span's envelopes solved with `tension_at(tension, span)`, through
`EnvelopeTable._rig_at`)

## `mapping.py`

Coordinates (`coordify` adds columns; each part's different anchor pixels transformed once and gathered), grouping
(`group_lines` → `Groups`: index arrays; its cell index `_cell_index`: one int64 key per line, a stable argsort, the
lines of a row of cells found by `searchsorted`; its loop `grouping.greedy`), matplotlib map; `save_map` writes a
run's (its orthophoto entry `ortho_entry`, also the 3D view's patch meta) `map.html` + `data.js` + `lines.js` for the
viewer, chunk by chunk from the columns (`files=` which of the three; `map_heads` the scripts' texts before the lines,
`write_map_scripts` the lines of `data.js` and/or `lines.js` from them: what the children of `saving.py` run; the
run's `terrain` in the heads of both scripts; `end_zone`, `lift` and `"ends": ["lift_needed", "lift_no_zone"]` in them
only when the run has the options, `map_rows` putting those values before the profile)

## `grouping.py`

The greedy loop of `mapping.group_lines` in numba (`greedy`: the representatives and their members over
`mapping._cell_index`, `GROUP_PART` lines per call between progress updates; `gather`: the members in the groups'
final order); imported inside `group_lines`, so `import mapping` stays free of numba

## `runs.py`

Saved runs (`runs/<date>_<time>_<place>_<random>/`, the place in ASCII by `anyascii`: `_slug`), `runs/index.html`,
`runs/runs.js` (`write_index`, after each run of the command line and the local app: `search.Plan.index_runs`, which
the public worker clears; `viewer=False` when the run's map installed the viewer; `_listed` leaves out the run's
`terrain`), run names, `params_summary` (a run's description: the elevation band first among the limits);
`save_results` writes `lines.csv` and `lines.geojson` `LINES_CHUNK` rows at a time, each part's rows in their order
computed alone (`row_order(groups, lo, hi, at)` with `rep_positions`); `files=` which of its four files;
`END_FIELDS`/`END_COLUMNS` (`lift_needed_m`, `lift_no_zone_m` after `clearance_nmpt_m`, in `lines.csv` and
`lines.geojson` only when the run has the options: `fields_of`, `feature_template`) (the children of `saving.py` write
the line files apart, `_rows(csv=, geojson=)` skips the join of the file not wanted)

## `saving.py`

Step 5 in processes of its own (`search.save_run` for runs of `MIN_LINES` (100 000) lines or more with
`processes(line_threads)` ≥ 2: `plan(count, map_files)` gives each child's files, one per file with 4, the results'
apart from the map's with 2 or 3): `hand_over` writes the lines' columns (the end values too), the groups' arrays and
the arrays of every `helpers.Profiles` batch the profiles come from as `.npy` into `<work>/saving/` (which line has
which profile of which batch; dict profiles, run.json's values and the map scripts' heads of `mapping.map_heads` in
`saving.json`), `load` memory-maps them back; `write_files` starts `python saving.py <folder> <run path> <files>` per
child (`subprocess`, never `multiprocessing`: the worker's phase process is daemonic; `kill_tree` ends them with a
cancelled job), each child calling `runs.save_results(files=)` / `mapping.write_map_scripts(files=)` and printing
`"<count>\t<file>"` per chunk, which the parent turns into the bars "saving results" and "saving the map" (totals the
lines, the count the slower file's) from its main thread (the listeners write SQLite); `between` runs the parent's
small files (ATTRIBUTION.txt, run.json, the tiled run's "done", the message) after the first bar; a non-zero exit
kills the others and raises `RuntimeError` with the child's stderr's last line (the whole on the parent's stderr; the
public `Redact` masks it as any error); `save` removes the folder afterwards, also on failure; the child imports
numpy, runs and mapping only (75 MiB, about a second), never `search`

## `progress.py`

Two tqdm bars (Download / Compute; `progress.bars()` puts back on exit the bars it found, as they were: it left bars
labelled "" for the rest of the process, which a listener that follows the bars by their label,
`tests/test_count_mode.py`'s, saw none of after `country.run` had run in the test's process,
`tests/test_units.py::test_bars_put_back_the_bars_they_found`); listeners (`progress.subscribe`) for the web worker;
`utf8_output` (stdout and stderr in UTF-8: every entry point, `jobs.run_quick`, `jobs.run_phase`;
`tests/test_entry_points.py`); `update(n, part=...)` names the part of a bar of a few steps that runs next (step 1:
`sources.filling._fill` slopes/rings/medians, `fill_water` sea/lakes/levels), which `tools/perf_profile.py` lists per
part; step 1's other bars: "area coverage", "sea mask (world file|coastline)", "shore zone", "terrain statistics",
"border gaps (<neighbour>)", "gap filling (<source>): terrain|surface", "surface coverage", "partner zone" and
"partner territories" (the count mode across a border only) (none of them in `jobs.STAGE_KEYS`)

## `warmup.py`

The worker's numba warm-up (`warm_up(data_dir)`, run by `jobs.Scheduler` at its start: the public worker's numba cache
is a tmpfs, compiled again after every start of its container): synthetic searches (`SCENES` `small` and `wide`,
GeoTIFFs written by `write_grids`, through `search.plan_search`, `prepare_data`, `find_lines` and `_lines(core=)`) in
every combination that gives the kernels other argument types (`SEARCHES`: surface model or none, the masks of water
and filled gaps (`MASKS`, read-only memory-mapped as a search's), a tile's core, `linesearch.PAIR_BUFFER` overflowing,
parts of one and of several anchors, thinned profiles, the sag estimator once); in a temporary data folder
`work/warmup/<id>` (never the cache, the runs or `jobs.sqlite`), output dropped, a failure printed to stderr;
`tests/test_public.py::test_numba_warm_up` (a search afterwards compiles nothing): a kernel's new argument type needs
a search here
