# Code map: the search

What the modules of this area hold, in detail: the search. Moved out of CLAUDE.md on 2026-11-12; nothing loads this
file by itself, so read the entry of a module before a large change to it. What must stay in sync and the pitfalls are
in `.claude/rules/` (search-pipeline, line-test, run-files).

## `findaline.py`

Command line only: options from `params.py`, messages, questions, the list of spots, the matplotlib window, the
search's last line `View it: findaline.py view <id>` (`--html`, accepted for one release by store U10, is gone since
line volume's round 7: refused as any unknown option);
`cache`/`osm`/`web`/`worker` as first argument go to update.py / web.py / jobs.py. `export` (`export_main`): a run's
CSV or GeoJSON from its store. `view [RUN]` (`view_main`, `_run_folder`, `app_holds`): a run opened in the app at
`/#run=<id>`, the app on `--port` when it serves this run's run.json (the local app serves its runs folder as files),
else the app started as `web` runs it (`web.main(open_path=)`), never a second app beside another one.
`runs remove-old (--dry-run | --yes)` (`runs_main`, docs/line-volume/spec-store.md section 2): `runs.old_runs` under
`cache.runs_lock`, `jobs.run_facts` for the listing (owner's user id, shared, demo, favourites, the searches that leave
Home), `Jobs.delete_run` per old run with a jobs.sqlite (the folder alone without), the leftovers `runs/index.html`
and `findaline_map.html`, runs.js rewritten where it exists

## `params.py`

`SearchParams` (pydantic: fields, help, groups, validation) and `CliOptions`; argparse is generated from them; the
topic "rigging" holds `end_zone` (0-`END_ZONE_MAX` 20 m) and `anchor_lift` (0-`ANCHOR_LIFT_MAX` 3 m), both 0 by
default; the topic "lines" `same_line_square` (the square rule: 0, or `SAME_LINE_SQUARE_MIN` 2 to
`SAME_LINE_SQUARE_MAX` 20; `same_line_square_range`)

## `search.py`

The search as a library: `plan_search` (`reach=True` only in the first planning of a search: the command line's,
a web job's download phase, the quick lane's estimate, which then ask whether the project's data server answers;
`source_id=` the source a job's first phase chose, which a later phase takes without choosing again;
docs/mirror-hosting/spec.md C.3), `estimate_search` (the layers' indexes at once, as `download_layers`; the
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
the map, nothing downloaded: the view's columns and the store (`linestore.write`) in the Compute stage "saving
results", then `map.html` (not with --no-html), `ATTRIBUTION.txt` and `run.json` last with its block `store`; no text
file since store wave 4; anything that fails between the folder and run.json raises `SearchError` `run_not_saved` (`_not_saved` removes the run's
folder (a tiled run keeps its tiles), view columns that fail leave a store without them and the note
`view_columns_failed`), `orthophoto_lines` and `download_orthophoto` (the orthophoto
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
`memory_needed`, `PIXEL_BYTES`, `LINE_BYTES`, `PROFILE_POINT_BYTES` for a circle's profiles of every line,
`WARD_SPOT_BYTES` x min(lines, `mapping.SECTOR_WARD_SPOTS`)² for the sectors' clustering at saving; `lines_fitting`,
its one inversion, names the lines that fit in the refusals and the warning; also the tile size and `memory_warning`
at the worker's start; `tile_core_size`: a tile's core from `TILE_MEMORY_SHARE` of the budget at `PIXEL_BYTES` per
pixel, at most `TILE_PX_MAX` pixels whatever the memory), off by default, so the CLI and the regression checksums are
unchanged; F7: `find_valid_lines(check=_early_check(...))` stops at `lines_max` (with
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
and the store's head (data.js's in old runs); where the land's terrain came from (`sources.filling.terrain_origins`, `_terrain_sources`): after
the gap filling, only for a run's search (`shore="segments"`, `plan.border`), an info line of the shares and a
`messages.Note` `terrain_fallback` from `FALLBACK_WARN_SHARE` (10 %) of the land from fallbacks, into
`Data.terrain_sources`, `Lines.terrain_sources` (a tiled search's in `ORIGINS_FILE`, as the shore's),
`meta["terrain_sources"]` of run.json and the store's head (data.js's in old runs) only when known (not lines.js,
not runs.js);
`shore="kinds"` for the 3D view's patch (`Data.shore_kinds`, `work/shore.npy`), `shore="none"` for a
profile and the country layer's tiles; `--min-elevation`/`--max-elevation` keep the anchors within the band in
`_anchors` right after they are found (float32 heights; before `ANCHORS_MAX`, the prominence and the drop, so the
funnel's `anchors_kept` counts it; `no_anchors_in_elevation_range`), `_search_hash` drops them when unset; the no-fall
zone and the A-frames (`Plan.end_zone`, `Plan.lift`, printed as "Ends: ..."): `_pair_search` hands them to
`find_valid_lines` (with `zones=(0, end_zone)`, whose bucket minima `zone_margins` become `lift_needed`/`lift_no_zone`
through `helpers.lift_values` and are dropped from the table, in count mode from each part before the sink gets it),
`_fixed_order` sorts exactly tied lines by their anchors' pixels only when one of them is set (tiles then give one
grid's rows in one order), `_run_values` reads a run's pair from run.json (0/0 for runs before) for `profile_of_line`,
`reach_of_anchor` and `patch_of_line` (`_end_keys` in the meta), `_search_hash` drops them at 0; the square rule
(`Plan.square`: `samelines.side` of `--same-line-square` on the plan's resolution, 0: off): `_pair_search` gives
`find_valid_lines` a `samelines.BestPerSquarePair` as its sink (never in count mode) with the tile's core and
`_early_check`'s check, and returns its table (the column `stands_for`), longest first; `search_lines` reduces the
join of the tiles (`samelines.reduce_table`); `_check_lines` and the early check count kept lines; `_run_params`
(`same_line_square`, `same_line_side`) and `_search_hash` hold the option only when set, `save_run` adds
`summary.found`; the size of a search before its pairs (docs/line-volume/spec-search.md section 2): where
`_early_check` checks (`_samples`: the web worker; never the command line or the regression set) `_lines` (one
grid) after step 2 and `search_lines` (a tiled area: `_estimate_tiles`, every tile's window, its anchors and its
sample before the first tile's step 3, in `work/sample<k>/`) estimate the lines with `sample_estimate` (the useful
anchors of the core, `_open_anchors`: `free_directions` with `find_valid_lines`' set-up repeated, ordered by
`default_rng([first 8 hex digits of _search_hash, tile])`, the first `max(1, round(SAMPLE_FRACTION N))`; without
the square rule anchors, `_pair_search(first=)` with a counting sink, lines x N/k; with it the rule's squares, the
distinct `samelines.square_keys` seen from their first square x M/k, the lines kept; Horvitz-Thompson variance;
returns `(lines, variance, k, n)`), and `_estimate_check` decides: over `REFUSE_FACTOR` (1.25) times `lines_max`
or the lines that fit into `Plan.memory` refused (`too_many_lines_estimate`, `too_many_lines_memory_estimate`,
with the advice and the page's words, `_lines_text`/`_shown`: two digits, plain under a million, else millions),
from `ACCEPT_FACTOR` (0.8) the warning `estimate_close`, else the note `estimate_lines`; the funnel's `estimate`
(a search refused for its lines: `jobs._write_refusal`'s rows); the full search's checks stay; the progress labels
"Step 3/5: estimating the lines" and "Estimate, tile k/n · ..." are a phase of their own on the job page (`useJobs.ts`
`jobProgress`); `count_tile` without a sag table takes `_sag_table`'s of the process; the access mark (`--access`,
docs/line-volume/spec-search.md 3): `_access_grid` (the alpine variant on, from step 1's filled terrain, water
and `Data.filled_pixels`; the bar "access to anchors", parts "grid-wide" and "blocks") once per search on its whole
grid, `Data.access`, after the cheap refusals (one grid: in `_lines` after the anchors' limit and the estimate; a
tiled search: in `search_lines` after `_estimate_tiles`): at once (`access.access_grid`, in memory) when
`ACCESS_WINDOW_BYTES` per pixel of the grid fit `_access_budget` (`Plan.memory`, else the memory free), else in
blocks (`access.block_grid`, `_access_block_px`: the largest square block whose window fits what
`ACCESS_AREA_BYTES` per pixel of the grid leave, at least `ACCESS_BLOCK_MIN_M`, under 2^31 pixels; the same
answers), `ACCESS_FILE` (`access.npy`) in the work folder for blocks and for a tiled search (removed with step 1's
grids), each tile's window copied by `_tile_data` (a tile reads one grid's answers); `_check_access` (from
`plan_search`, against `_access_budget`) leaves the mark out of a search whose `access_memory` (the grid at once, or
the grid-wide pass and the smallest block's window) does not fit: `Plan.access_skipped` "memory" (`Plan.access_on`
false: no stage, no columns, no disk counted), the coded note `access_skipped`, run.json's and the heads'
`access_skipped`, `progress.json`'s too (a tiled run resumes only for the same choice); `_lines` after
`line_coordinates` calls `_access_columns`: `access1`, `access2` (uint8, `access.at` of the anchors' pixels, the
measure's own answer; an anchor on a pixel without heights asserted impossible); `_run_params` (`access`) and
`_search_hash` hold the option only when set; `tile_bytes` (1 B) and `estimate_search` (`ACCESS_DISK_BYTES` of the
whole grid) count its files (docs/performance.md, "The access grid's memory"); `save_run`'s
`SearchError` `run_not_saved` and note `view_columns_failed` hold the exception's text on the command line only

The data record (2026-11-24; the user's "do it once and correct"): what a search read, under the one key name
`identity`, so that with every `identity` removed a run.json is what it was. Each `data` entry with `paths` holds
`identity.sha256`, parallel to `paths`: the cache index's stored checksum of each file, read in `cache.touch`'s own
lookup (`Layer.used`, cartoteca's and s3sheets' entries: `cache.identity_of`) after the read and kept only where the
note before the read agrees, the checksum and the file's identity on disk (`os.stat`) both (`mosaic.noted_before`,
`read_window`: in `prepare_layer` for every builder's entries, in `filling.water_body_mask`; else null, the file
changed while it was read); the coastline's entry the world
file's edition or the OSM coastline tiles of the grid's box (`coast.identity`); a local file's entry its size and
modification time (`cache.file_identity`); the `area` block the OSM theme tiles and Nominatim answers an area by
coast, cliffs or name was built from (`area.Inputs`, carried by the area object: `osm.theme_files`,
`osm.stored_answer`); the top level `v`, the versions of GDAL, PROJ and rasterio, `slope_file` and `mixed`
(`_run_identity`). `_merged_data` keeps the checksums in step with the united paths (also of a layer prepared twice in
a run): a path keeps one only when every entry with `identity` that lists it gives that same one (two different
ones or a null in any: null). A tiled search keeps the record in its run folder between sessions (`USED_FILE`: `data`, `mixed`,
`area`, `slope_file`, `_session_record`); a resuming session that finds a tile of an earlier one compares its
record with the kept one (`_record_differs`) and marks the run `mixed`; with no tile left it takes the kept record
whole. One exit: `runs.without_identity` (`public_meta`, `_listed`, `country._credits`); a country tile's record
keeps the key, nothing built from the tiles does. Read by `tests/regression.py` (the side file
`tests/regression-data.json`, the line under an entry that differs), `update.changed_runs` (`cache status`) and
`tools/record_check.py` (the completeness check); its limits: docs/known-bugs.md, "The data record".

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

## `samelines.py`

The square rule (`--same-line-square`): one line per pair of anchor squares, kept while the pair search runs.
`side` (the option's metres, on data coarser than 1 m as many pixels), `square_keys` (a lattice with a corner at
(0, 0) of the grid's CRS; the key is the two squares without order), `BestPerSquarePair` (the sink of
`linesearch.find_valid_lines`: per key the first line of the order "needs neither the no-fall zone nor A-frames,
needs no A-frames, highest mean height, longest, the anchors' coordinates" and the number of the key's lines,
`COLUMN` = `stands_for`; reduced parts wait and are merged into the kept lines every `MERGE_ROWS` rows or as many as
are kept; with a check, asked after each merge about the kept lines, and about the rows held once `CHECK_ROWS` wait),
`reduce_table` (the same on a table with coordinates: a tiled search's join). Plain numpy

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
run's `map.html` (`map_page` and `MAP_HTML` with the disk notice, kept in `runs.py` since line volume's round 7 and
imported here under their names: the web process rewrites a renamed run's page and never imports `mapping`) and
installs the viewer (its orthophoto entry
`ortho_entry`, also the 3D view's patch meta, is in the store's head); `map_head` the store's head as a dict
(`linestore.write`; data.js's head in old runs): the run's `terrain`; `end_zone`, `lift` and `"ends":
["lift_needed", "lift_no_zone"]` only when the run has the options (`_ends`); a run made with the square rule has
`square`, `found` and `stands_for` as the last name of `ends`; the writers of data.js and lines.js went with store wave
4's item 5 (a frozen copy for the tests: `tests/old_scripts.py`);
`view_columns(lines, groups, centre)` the result view's columns of a new run's store (view B1, docs/line-volume/
spec-store.md 1.3, from the values as the store holds them): `spot` (`group_lines`' groups renumbered by sector, then
by their first line's mean height), `by_spot` (rows by spot, inside a spot by mean height, clearance, length, then
the row; NaN last), `top` (`top_level`: K-17 'Higher wins on a face', `tools/prune_study.py`'s `higher_wins` with
`STACK_CELL`/`STACK_STEP`) and the head's `sectors` (`_ward_sectors`: Ward's clustering, scipy, of the spots' shown
lines' ends into at most `SECTORS_MAX`; above `SECTOR_WARD_SPOTS` spots (10 000, memory by their square) Ward's of
that many taken evenly in group order, every spot then to the nearest cluster's mean, `_nearest`; a word of
`SECTOR_WORDS` or "centre"), `box`, `lengths`; NaN after every number in each order (`_highest_first`)

## `grouping.py`

The greedy loop of `mapping.group_lines` in numba (`greedy`: the representatives and their members over
`mapping._cell_index`, `GROUP_PART` lines per call between progress updates; `gather`: the members in the groups'
final order); imported inside `group_lines`, so `import mapping` stays free of numba

## `runs.py`

Saved runs (`runs/<date>_<time>_<place>_<random>/`, the place in ASCII by `anyascii`: `_slug`),
`runs/runs.js` (`write_index`, after each run of the command line and the local app: `search.Plan.index_runs`, which
the public worker clears; `_listed` leaves out the run's `terrain`; no `runs/index.html` since store wave 4),
`old_runs` (the runs of `findaline.py runs remove-old`: old, current, skipped with the reason, the folders a
removal left; by `run_state`: `linestore.store_state` and run.json's `VIEW_FAILED`), `park_run` and `finish_removal`
(a removal: the folder renamed to `_removing-<id>` under the runs lock, then deleted), run names, `params_summary` (a run's description: the elevation band first among the limits);
a rename (line volume's round 7, the public site's `POST /api/runs/<id>`): `run_name` (the name as stored: NFC, each
run of whitespace one space, trimmed, 1 to `params.MAX_NAME` characters, one of them visible; refused with `UserError`
"run_name": control and format characters but the two joiners `JOINERS`, line and paragraph separators) and
`rename_run` (under the runs lock, each file whole through `cache.replacing`: ATTRIBUTION.txt's first line when it
is the one `attribution_text` wrote, map.html from `map_page` (`MAP_HTML`, `DISK_NOTICE`), run.json
last, read through `read_meta`; the id, folder, store and links stay); `read_meta` (run.json opened again after each
of `READ_PAUSES` while Windows refuses it); `HOME_SCREEN_HEAD` (round 7's home-screen app: the manifest's and the
iPhone icon's links and `theme-color` in `GROUND_LIGHT` and `GROUND_DARK`, the light and dark `--bg`), in `MAP_HTML` and
in web.py's five pages;
`save_results` writes `lines.csv` and `lines.geojson` (for `linestore.export`; the search writes only its
`ATTRIBUTION.txt` and `run.json`) `LINES_CHUNK` rows at a time, each part's rows in their order
computed alone (`row_order(groups, lo, hi, at)` with `rep_positions`); `files=` which of its four files;
`END_FIELDS`/`END_COLUMNS` (`lift_needed_m`, `lift_no_zone_m` after `clearance_nmpt_m`, in `lines.csv` and
`lines.geojson` only when the run has the options: `fields_of`, `feature_template`), `STANDS_FOR` (`stands_for`, the
last column and property, only in a run made with the square rule) (`_rows(csv=, geojson=)` skips the join of
the file not wanted)

## `linestore.py`

A run's store (docs/line-volume/spec-store.md 1.3; since 2026-11-15 written by `search.save_run` on every new run,
after and beside the text files; a store that fails leaves the run without one, with a warning): `lines.arrow` (a row per line in the search's order) and `profiles.arrow` (a row
per saved profile, `row` into `lines.arrow`), Arrow IPC files (pyarrow), uncompressed, one record batch each.
`COLUMNS` names each column with its `LineTable` column and its decimals: the anchors int32 at 7, the grouping's
values (`x1`…`y2`, `len`, `clr`, `hmax`) float64 as they are, the others integers of data.js's decimals in
the narrowest int type (field metadata `decimals`), nulls where a value may miss, the end columns and `stands_for`
(uint32) only when the lines have them; the schema metadata `findaline` holds `format` (`FORMAT`, a higher one is
refused: `NewerStore`), the head (`mapping.map_head`) and `negative_zero` (the rows of each integer column whose value
rounds to -0.0). Since view B1 (2026-11-16) `VIEW` (`spot` uint32, `top` uint8, `by_spot` uint32, after `COLUMNS`) and
the head's `VIEW_HEAD` (`sectors`, `box`, `lengths`): `mapping.view_columns`' values, which `save_run` computes in
the store's `try` (a failure: the run without a store); the format stays 1. `write(run_path, lines, head, view)` →
run.json's block `store` (format, lines, bytes, the first 16 hex of
`lines.arrow`'s sha256); `lines_table`/`profiles_table` the two tables (a profile from any number of
`helpers.Profiles` batches and dicts of `line_profile`); a scaled column whose values no integer holds exactly (beyond
2^53 once scaled, an infinity, a NaN where none may miss, an anchor beyond int32) is float64 of round(value,
decimals), without `decimals`, and a count beyond uint32 uint64, so a store never refuses a run's values; both files under `.part` names until both are
whole. `read(run_path,
profiles=True, columns=None)` → (`LineTable`, head), the profiles as dicts of `line_profile`, the view's columns by
their names when the store has them; `columns` (line volume's round 7): only those `LineTable` columns decoded (a
pair such as `anchor1` whole, the view's by their names; one the store lacks left out, one no store knows a
ValueError), the file still read whole, each equal to the full read's (`tests/test_linestore.py::test_read_of_chosen_columns`); `export(run_path, "csv"|"geojson",
out)` regroups (`mapping.group_lines` with run.json's distance and value) and writes with `runs.save_results`
with run.json's values without its `store`: the bytes the run's `lines.csv`/`lines.geojson` held before store
wave 4. `store_state(run_path)`: "current", "no_view", "old", "missing", "unreadable", "newer" or "cannot_read" (an
error while reading: never "unreadable") from the schema alone (what
`findaline.py runs remove-old` counts as an old run). numpy and pyarrow
only at module level (`runs` inside `write` and `export`, `mapping`, which groups with numba, inside `export`): never
imported by the web process (`tests/test_linestore.py`)

## `access.py`

The access mark of three states (docs/line-volume/spec-search.md 3; part P3d's measure ported, its constants kept;
the module's docstring has the whole measure): `access_grid(z, water, res, filled=None, alpine=True)` → uint8 per
pixel, `CAN` 2 ("easy access"), `UNSURE` 1 ("cannot tell"), `CANNOT` 0 ("hard access"); a filled pixel or a shore face
gets the answer of the data around it (its standing ground), as in the study; `at(grid, pixels)` refuses pixels
outside the grid; `access_grid` and the blocks share `_answers` (the local part, the grid-wide judgements given);
`block_grid(z, water, res, filled, path, work, block_px)`: the grid-wide judgements once on the whole grid in strips
(`_whole_metres_rows`, `_flat_lakes_rows`, `_open_ground_rows` on the heights and the smoothed heights; masks and
int32 labels memory-mapped in `work`, removed after), then every block from its window of `margin_px(res)`
(`MARGIN_M` + 6 pixels): the whole grid's answers; a grid or window of 2^31 pixels refused (`_check_size`: the
walk's int32 indices). numba kernels (`_walk`, an indexed Dijkstra; `_stands_near`,
parallel, each pixel its own answer: the answers never depend on the threads), compiled by `warmup`; never imported
by the web process (`tests/test_access_search.py`). Tests: `tests/test_access.py` (made-up terrain),
`tests/test_access_search.py` (through the search, the files, tiles)

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
parts of one and of several anchors, thinned profiles, the sag estimator once; the first search also
computes the access grid, `search._access_grid`: `access.py`'s kernels on the read-only memory-mapped
terrain and on the smoothed heights of whole metres); in a temporary data folder
`work/warmup/<id>` (never the cache, the runs or `jobs.sqlite`), output dropped, a failure printed to stderr;
`tests/test_public.py::test_numba_warm_up` (a search afterwards compiles nothing): a kernel's new argument type needs
a search here
