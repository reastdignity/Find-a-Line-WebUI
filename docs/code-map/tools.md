# Code map: tools run by hand

What the modules of this area hold, in detail: tools run by hand. Moved out of CLAUDE.md on 2026-11-12; nothing loads
this file by itself, so read the entry of a module before a large change to it. What must stay in sync and the
pitfalls are in `.claude/rules/` (the rule of the area a tool belongs to).

## `tools/check_source.py`

Run by hand: the data checks of a new source (docs/regression-tests.md) as one command: shift search against FABDEM /
Copernicus / a file, valid share at 1 and 5 m, cached tiles against their source files, alignment with `grid_origin`,
whole-metre heights, tiles without data (a ZIP member read again by Range through `net` and opened by GDAL, never
`/vsizip//vsicurl/`); on a grid of `search.plan_search(with_margin=False)`; PASS/WARN/FAIL, `--json`;
`tests/test_check_source.py`

## `tools/source_docs.py`

Writes README's "Data sources" table and the ids of the `--source` row from `Source.listing` and the catalogue
(`--check`); `tests/test_catalogue.py::test_docs_list_every_source`

## `tools/coverage_data.py`, `coverage_shapes.py`, `coverage_contrast.py`, `coverage_media.py`

The coverage map (/coverage): `coverage_data.py` writes `viewer/src/coverage/coverage.json` from `Source.coverage`
(`--check`; `tests/test_coverage.py`; no git read: `Coverage.added` holds the dates), `coverage_shapes.py` the
outlines `viewer/src/coverage/shapes.json` from Natural Earth 5.1.1 (sha256 pinned, downloads to the temp folder; a
country split at `Coverage.box` or its source's `bbox` into a `rest` feature at 30 m; a region without an admin-1 unit
cut from its country by a box, `CUT`: Jan Mayen; `small` under 10 000 km²). Run by hand: `coverage_contrast.py`
(`search` the nine places at 1 m and at 30 m with anchors from 40.5°, `write` docs/coverage/contrast/: hillshades,
spots, the 45 m check, the credits dated with the year of the searches), `coverage_media.py` (group `ui`: the media
bundle of `node build.mjs --media` in a temp folder with `contrast/`, served on 127.0.0.1 with `web.SECURITY_HEADERS`
and driven through `window.FAL_MEDIA` in headless Chromium, a page or console error stops it; PNG frames piped to
imageio-ffmpeg's ffmpeg, nothing stored between: the MP4 stories (H.264 yuv420p BT.709 30 fps CRF 18), the README's
GIFs (one palette) and images in docs/images/ (`readme`), the carousel, Stories and the A3 poster (PNG of 300 dpi, a
PDF of img2pdf holding the PNG's IDAT data); every output read back with `ffmpeg -i`; `tests/test_coverage_media.py`)

## `tools/sk_tiles.py`

Run by hand: ÚGKK SR's national ZIPs → 2 km COG tiles + `index.json` + dataset card (the local mirror, later Hugging
Face); `average <product>` writes the same tiles at 2 m and 5 m (`FACTORS`) into `<product>/2m`, `<product>/5m` with
their own `index.json` (resumable): each pixel the mean of the valid 1 m pixels of its block
(`sources.readers.download._block_means`, `Download(average=)`'s rule), float32 without further loss in
`AVERAGED_PROFILE` (ZSTD at `ZSTD_LEVEL` with the floating point predictor, 256 px tiles; deflate until 2026-11-08,
which took 1.6-1.8 times as long to decode: `tests/test_sources.py::test_slovak_tiles_averaged`);
`recompress <folder> ...` writes the averaged tiles made before in that profile, resumable (a file already ZSTD
skipped): each through a `.part` compared bit for bit (values, georeference, nodata, tags), then replaced; a file that
differs or stays open is listed and left, a LERC tile refused; a mirror's folder gets the new sha256 and encoding text
in its `index.json` and the dataset card, a cache's folder (a `LAYOUT` above it) the new sha256 in its index rows by
`cache.reencoded` under the tile's lock (`test_slovak_averaged_tiles_recompressed`)

## `tools/ui_shots.py`

Run by hand: screenshots of the app's pages for a visual review (Playwright, group `ui` of pyproject.toml): a desktop
(Chromium) and two phones (iPhone 13 on WebKit, Pixel 7 on Chromium) with their device profiles, light and dark, on a
public site of a scratch data folder (a temporary one is removed at the end) with an administrator signed in (and a
run's `map.html`, also by its share link) (the `-limited` pages: an approved user with the site's limits; HTTPS with a
certificate of the run: WebKit sends no Secure cookie to http://localhost); the pages `c-layer`, `c-layer-world` (both
cubes in view), `c-layer-study` (the study area alone), `c-layer-end` (the phones' column at its histograms) and
`c-layer-cell` (a cell selected) over three cubes; `--run <folder> --line <lat1,lon1,lat2,lon2>` shows a saved run
(copied into the shots' data folder) with that line open: the pages `c-result-rigging` (the rigging filter) and
`c-line-profile` (the profile card), with `c-line` and `view3d` of made-up counts of
`tests/test_country_web.py::sample_cube` (`slovakia` and `testland`, as its fixture, and the study area `sk-part`)

## `tools/perf_*.py`

Run by hand: the measurements of docs/performance.md: `perf_run_load.py` (a run's result and its first line's 3D view
opened in headless Chromium on the local app over a scratch data folder, the runs copied and the cache linked: the
page's User Timing measures, `viewer/src/perf.ts` "fal:run:*"/"fal:3d:*", the long tasks and heap, data.js as a script
against fetch + JSON.parse, gzipped sizes and their times at 10/50/200 Mbit/s; `tests/test_perf_run_load.py`),
`perf_profile.py` (cores and memory of a search per stage, a timeline chart; `--cores N` like a worker container;
`--memory BYTES` the budget of a compute slot (`search.available_memory` answers it), so an area's tiles are sized as
the web worker sizes them; a bar of parts (`progress.compute.update(n, part=...)`) is listed per part),
`perf_download.py` (the download phase on an empty cache with N threads), `perf_sqlite.py` (`jobs.sqlite` under K jobs
and M open pages), `perf_lines_memory.py` (bytes per line of steps 3, 4 and 5, from a capture of
`perf_line_funnel.py`: `--call`, or of the join of a tiled run's tiles and, for tile files that still hold the pixel
columns (written before 2026-11-01's wave 5), its steps 4 and 5: `--tiles`; `search.LINE_BYTES`);
`perf_profile.py --tracemalloc` the heap per stage; `perf_window_reads.py` (the bytes, requests, seconds and memory of
a window layer's blocks over a circle on an empty scratch cache, each mode in a child process: `blocks`, `group=<m>`,
`serial=0|1`, `order=squares|tasks`, `cache=<MB>`, `multirange=`, `gdalthreads=`; GDAL's network statistics through
ctypes into rasterio's GDAL library, our own range requests counted at `ranges.get_range`; the files' internal tiles
as the prediction, per block and each once; `tests/test_perf_window_reads.py`), `perf_reach.py` (the reach of one
anchor over a 3D patch's lattice by batched numpy and by `linesearch.evaluate_lines`, both checked against
`helpers.evaluate_line`: seconds, memory, numba's one-time costs, the representatives of three rules, an answer's
size; what `search.reach_of_anchor`'s engine was chosen on; `tests/test_perf_reach.py`)

## `tools/perf_country.py`

Run by hand: the measurements of docs/country-precompute.md (a country-wide offline layer of line and spot counts):
`bench` (an offline benchmark of a machine on the Żabi Koń clip mirrored into a 4800 × 4800 px mosaic: two fixed
searches through `perf_profile.py` and K searches at once, `bench.json`), `profile` (one search through
`perf_profile.py` with its plan, funnel and counts into `samples.json`; `--tension-by-length`: a pretension by span, a
`sag.TensionTable` assigned as `sag.EnvelopeTable` for the run), `compare` (lines and spots per cell and length band
against a reference run), `cube` (the keys of a sparse counter cube per km²), `relief` (Copernicus GLO-30 of the
catalogue's `europe` layer over each country's OSM outline and each sample: per block of about 1 km the share of 45°
pixels and the relief over windows of 1, 3 and 5 blocks, `relief.tile_blocks`; the countries' km² per bin, joint for
steep share × relief, and the samples' 1 km cells with their edge fraction; `virtual_cells` for a place measured only
at another grid) and `estimate` (country totals: strata of the steep share, the relief below 0.5 %, lines per km² from
the cells, a bootstrap over the places; times from `time_model` per band and grid; `inputs.json` names the strata,
machines, data and services); `tests/test_perf_country.py`

## `tools/perf_line_funnel.py`, `tools/line_funnel_kernels.py`

Run by hand: where the line search's work goes (docs/performance.md, "Order of elimination").
`capture -- <findaline options>` runs a search with `linesearch.find_valid_lines` wrapped and saves the inputs of its
calls (`call-<k>/inputs.npz`, `params.json`, `timings.json` of its three bars; `--calls`, one call per tile);
`analyse` rebuilds the kernels' arguments (`rebuild`, a mirror of `find_valid_lines`' set-up), checks that
`linesearch._free_rings` and `_pairs` still give exactly the results of the frozen references
`ref_free_rings`/`ref_pairs` (copies of 975a1b7) and counts the funnel: rings and pixel reads, every visit of a
partner and the test rejecting it, the visits candidate skip rules would save (none may skip a pair checked pixel by
pixel; F8c as production applies it since 2026-11-03), the work of the anchors with lines, the pixel tests of
`_line_ok` under other orders → `funnel.json`, `funnel.md`; integer counters per anchor, so any thread count;
`tests/test_perf_line_funnel.py`

## `tools/device_page.py`

Run by hand: the 3D view on a real phone (docs/3d-view-contract.md, "Wave 4"): `record` takes the `/api/patch` (steps
1 and 2) and `/api/profile` answers of a few lines of a data folder's runs from the local app in-process, `serve`
serves them again over HTTPS on the LAN (a self-signed certificate per start, the 3D page as `web.VIEW3D_HTML` gives
it with the app's headers and CSP, `/cache/` read-only, GET only, no accounts) with an iPhone checklist, `measure`
gives the data of one open per line and level (the imagery planned by the page's own `tiles.ts` run in Node, cached
tiles measured, service tiles sampled); `tests/test_device_page.py`

## `tools/obstacle_study.py`

Run by hand: which rule tells trees and buildings of the surface model from the terrain's own rock (docs/roadmap.md,
priority 1). `run <regression ids> --place NAME=OPTIONS --out <scratch>` searches each place in a child process
(`capture`) with its own data folder (cache/ linked, as tests/regression.py), `find_valid_lines` captured as
`perf_line_funnel.py` does (with `obstacles.RULE = None`: the raw surface) plus the grid's georeference and what its
layers came from (`grid.json` with `layer_meta`: `source`, `grid_origin`, the cached files under the grid
`nmt_files`/`nmpt_files`, `ortho`, `area_wgs84`) and the lines (`lines.npz`); a captured place is searched again only
with `--again`. `analyse` (`study.json`, `study.md` of a place): the pixels above each marked line's limit and which
of them each rule keeps (`rule_flags`: A<r> the envelope, A1+W<deg>/<px> the band around steep terrain (radius 1
given), A<r>+V<k> crowns around, B<k> slope tolerance, C<deg> slope mask, D<k> anchor zone, F and F-trees with CHMv2,
A2+T (CHMv2's trees on WorldCover's tree cover stay), A2+H<m> (`HEIGHT_CAPS`: a pixel stays while the surface stands
at most m above the terrain)); the kernel checks (`linesearch.evaluate_lines` over the raw surface gives the captured
clearances, over `obstacles.obstacle_surface` of radius 1 and 2 the marks of A1 and A2; A2 and the raw marks on every
variant); the surface model's own pixels where finer than the grid (`fine_grid`: `fine-nmpt.npy`/`fine-nmt.npy`
memmaps on the finest file's lattice by `sources.mosaic.build_mosaic`, then `warp_max` onto the grid, blocks of rows,
with GDAL's `Resampling.max` and `med` (`FINE_FILES`: `s-max`, `h-max` (surface less terrain), `s-med`, `h-med`),
`fine.json`; GDAL takes every fine pixel overlapping a grid pixel at all, also by half: one more row and column where
the files' edges lie half a fine pixel off), the surface variants avg/max/h/med/hmed (`VARIANTS`, `fine_surfaces`)
counted under `VARIANT_RULES`, with the table of the lines each variant adds over avg (`OVER_AVG_RULE` A2); Meta/WRI's
CHMv2 and ESA WorldCover (range requests here only, kept as `chmv2.npy`/`worldcover.npy` in the call folder), CHMv2's
shift (`chm_shift`) and CHMv2 against the surface's height above the terrain (`chm_against_surface`); the judges
unless `--no-judges` (`judge_layers`: `tools/study_landcover.py` and `tools/study_ortho.py` from the cache of
`analyse --data-dir`, by default the place's `data/`; the orthophoto's thresholds set on the reference masks
(`reference_masks`) into `ortho.json`; `pixel_classes`: green is a tree only on terrain gentler than `TREE_SLOPE` or
where CHMv2 at the pixel reaches `TREE`; `line_verdicts` tree/rock/unknown/none per line and variant; the verdicts of
what each rule un-marks and keeps, also of the lines whose pixels above the limit all lie within `ANCHOR_NEAR` steps
of an anchor; `judge_failure`/`judge_group`: a place summed under the orthophoto, under OSM only (no orthophoto split)
or failed (listed, never summed)); pictures of `--chips-rule`'s groups (A2 by default; with the judges those of
`VERDICT_GROUPS`) in `chips-<rule>/`, five panels (terrain, surface less terrain, CHMv2, the profile, the orthophoto
by `ortho_patch`), and contact sheets `sheets/<rule>-<group>.png`; `report` (`<out>/study.md`);
`tests/test_obstacle_study.py`

## `tools/study_landcover.py`

Run by hand (and by `tools/obstacle_study.py`): OSM's land cover on a captured call's grid (`grid.json`) →
`landcover.npy` (uint8: `NONE` 0, `FOREST` 1 (natural=wood, landuse=forest), `ROCK` 2 (natural=bare_rock,
natural=scree), rock painted after forest; a pixel is the class of the area holding its centre); `landcover_on_grid`
(`osm.theme("landcover")` over the grid's WGS84 box, `osm.polygons`, `area.project`, rasterio's `rasterize`),
`write_landcover` (an empty array, the reason printed, when the theme's tiles cannot be had: Overpass down,
`osm.OverpassDayMax`); Overpass only, one query per new 0.25° tile: the data folder's cap of 75 a day is the limit of
a study run; `tests/test_study_landcover.py`

## `tools/study_ortho.py`

Run by hand (through `tools/obstacle_study.py`): the orthophoto as a judge of trees and rock.
`greenness_on_grid(grid, source_id, lines, cache_dir, zoom=ZOOM)`: the source's orthophoto at `ZOOM` (19; a service of
base tiles only at its `base_max_zoom` at most) in `orthophoto.strip_tiles` around a call's lines, the missing tiles
downloaded by `orthophoto.download` into the data folder's cache (shared with the maps), the GLI (2G - R - B) / (2G +
R + B) and the luminance of each tile pixel put onto the working grid (`Resampling.average` per tile from its
`mercator_box`, a pixel on two tiles weighted by the valid pixels each covers, `Resampling.sum`; NaN outside the
strips or for a failed tile); `threshold(gli, lum, forest, rock)`: `tau` halfway between the median GLI of sure forest
and of sure rock, `overlap` (the share on the wrong side), `bright` (halfway between the luminance medians) and
`bright_overlap`, `dark` (the forest luminance's 5th percentile), None under `MIN_PIXELS` (50); `write_greenness` →
`ortho-gli.npy`, `ortho-lum.npy`, `ortho.json` in a call's folder; `tests/test_study_ortho.py`

## `tools/band_study.py`

Run by hand: which grid and anchor angle each length range of the country layer needs (docs/country-precompute.md, "8.
The band study"). `setup` writes the `country.json` of each study area (`AREAS`: squares of a country, `box_of` as the
option `within`; every band of `BANDS`, the current layer's as layer bands; `PAIRS` of a variant and its reference;
the surface model marking lines over trees), counted by `findaline.py country run <area>`; `analyse --out` compares
each pair over all lines and over those not over trees: lines, spots matched within `TOLERANCE` clusters at both ends
in either order (`matched`), the 1 and 4 km cells with a spot lost and added, Spearman of spots per cell, per length
bin of the cube, the bands' tile and CPU seconds and memory → `study.json`, `study.md`,
`pictures/<area>-<variant>.png`; `tests/test_band_study.py`

## `tools/border_study.py`

Run by hand: the lines the country layer loses at a border, where its outline is a hard limit for both anchors
(docs/roadmap.md, "Country layer", "Lines across a border"). `run <place>` (`PLACES`: boxes across the PL-SK border,
the Elbe Sandstone (DE-CZ), the Wetterstein (DE-AT) and the Zillertal ridge (AT-IT, a neighbour coarser than the
grid); `Place`, `Side`: a source and an outline each) counts each layer band of a country (`country.COUNTRIES`,
Slovakia's by default) over the box grown by the band's longest line with one source's data and grid (`--primary`; the
other side's data from the neighbour fill, `border=True` for every tile), in the layer's fixed tiles and count mode
(as `country.TileWork`), the first anchors in the box only (`counted_box`; so none misses a partner), each line into a
`countcube.TileCounter` of its class (`CLASSES`: both anchors in A, both in B, one in each, other; `BorderSink` reads
the outlines' masks on the tile's grid), `fill_check` where each side's heights came from; resumable per tile
(`<out>/<place>-<primary>/tiles/<band>/<tile>.json`); `exposure <cube>` a built cube's lines and spots within reach of
each neighbour's border (`near_border`: a bin's longest line plus half a cell's diagonal, each cell to its nearest
piece, `border_pieces`); `report` the classes per band and length bin, near the border and per km of it, the two
primaries' spots across the border matched after reprojection (`reframed_spots`, `band_study.matched`), the estimate
for the exposure's cube (the lines and spots across measured in the boxes plus the cube's within reach outside them
times a place's ratio, from bins of `MIN_NEAR` lines of A near the border: it carries over only to a border of the
same kind, a ridge or a gorge) and a run's lines of A against that cube in the cells deeper in the box than a bin's
longest line (`check_against_cube`: equal on Slovakia's) → `study.json`, `study.md`, `pictures/<run>.png`;
`run --resampling <method>` counts with the neighbour's data reprojected by a method of `sources.mosaic.RESAMPLINGS`
into `<place>-<primary>-<method>` (each tile's CPU seconds and peak memory in its meta, `_Peak`), and `report`
compares every run with the other primary's run without a method (`resampling_rows`: *side*, the lines and spots with
both anchors on that reference's side, which the run finds on resampled data and the reference on the data themselves,
and *across*; the cost of each run); `boxes` lists every declared pair of the catalogue (`Source.neighbours`) with the
share of the neighbour's land within `BOX_REACH` of the border that lies inside the neighbour's rough boxes
(`Source.rough_boxes`; `box_reach`, `strip_share`, from the coverage map's outlines, a country's less the regions
other sources cover, the USA's without Alaska: outside them `neighbour_window` never asks the neighbour, and the
border gap gets the fallback's data; every direction is at 98 % or more since the border boxes of 2026-11-06);
`tests/test_border_study.py`

## `tools/truth_study.py`

Run by hand: the truth check (docs/truth-check.md): the search measured against the highlines people have rigged,
SlackMap's known lines, read by `tools/slackmap_data.py` (the ISA's two GeoJSON files without authentication by a
conditional GET built from `sources/net.py`'s pieces (`net._get` sends no If-None-Match and raises on a 304), checked
again after `TTL_DAYS` (30), in the data folder's `cache/slackmap/` (`geojson/lines.geojson.gz`, `spots.geojson.gz`,
`details/<id>.json` one id a second (`DETAILS_INTERVAL`), an upper-case letter written as `^x`; a new top-level folder
under the existing layout, no migration), `KnownLine` with the flags `no_length`, `length_mismatch`, `coarse_anchor`;
`net.HOST_SLOTS_OF` `data.slackmap.com` 2, `api.slackmap.com` 1, a courtesy cap; no licence of the data is published:
nothing of them (ids, names, coordinates, a cluster's id or centre, pictures of a place) in the repository or on the
site until the ISA answers, the tests' lines synthetic, the docs aggregates only): `fetch`; `cluster` (highlines and
midlines, the user's decision: a midline a sub-class, every count total and per type; `--types`; per country in its
source's CRS, anchors within `LINK_M` (300 m) joined (`cKDTree.query_pairs`, union-find), a circle over `RADIUS_MAX`
(1500 m) bisected, the radius the farthest anchor + `MARGIN_M` and at least `RADIUS_MIN` (200 m); options
`--min-length max(15, 0.8 x shortest)`, `--max-length max(100, 1.1 x longest)`, `--source` of `choose_source` at the
centre (`--country-from-lines`: Nominatim only for regions), `--extra` (the pass: `--model sag`); `clusters.json`, ids
`<cc>-<lat>n<lon>e`); `places` (ranked per country and source with the nearest test of `tests/regression.json`,
"covered by" within `NEAR_M` 2 km: `places.md`); `run` (each cluster by `findaline.py` in a child, `search-child`,
with `search._lines`, `search._anchors` and `helpers.find_significant_slopes` wrapped to write the capture:
`grid.json`, `grids.npz`, `anchors.npy`, `lines.npz`, `capture.json` (done; no_lines, a result; failed, with the first
coded error and its message, the child's stderr in `output.log` after `--- stderr ---`), resumable (`--again`,
`--failed`, `--status`, `--ids @FILE`), one data folder `<out>/data` whose `cache/` `studylib.linked_data_folder`
links to the real cache, `--parallel N` children in it (each with its own work folder `work/truth-<time>-<hex>/`,
removed once its process tree ended, since findaline.py on Windows leaves the work folder of a search without lines;
`jobs.kill_tree` at `--timeout` and Ctrl+C), a run's line files (`RUN_FILES`: 31 GB on the first pass) deleted once
its capture is written, run.json kept (`--keep-runs` keeps them all); a pass under `tools/test_lock.py run --heavy`);
`analyse` and `report` call `tools/truth_analysis.py` (the match in the grid's CRS: both anchors within
`tol = max(TOL_M 10 m, TOL_SHARE 10 % of L)` either way round (raised to the coordinate quantum for coarse anchors:
matched with a doubtful geometry) and the length within it too, `tools/coverage_contrast.matched` with a radius per
line, `match` the nearest candidate, `best_match` the one of the highest clearance; one reason of `REASONS` per miss
on the captured grid, the first that holds (`structure_anchor`: the obstacle surface `STRUCTURE_M` 3 m above the
terrain at an end without a steep pixel; the ends' pairs, at most `MAX_END_ANCHORS` per end and `MAX_PAIRS`, through
the search's tests in its order: `length_range`, `height_difference`, `clearance_near_anchor`/`clearance_mid` by
`helpers.evaluate_line` with the run's model, sag table and fall zone, `surface_obstacle` under reject, `wall_angle`);
`zone_lift` of a clearance miss (`ZONES` 0-20 m x `LIFTS` 0-3 m by `helpers.valid_at` on the bucket minima, checked
against `evaluate_line`); `--profiles` (`search.profile_of_line` with the saved run's run.json); `study.json`,
`study.md` (recall, clean and terrain recall per type, country, source, length bin and resolution, the reasons, the
zone x lift tables, the failed searches; written from study.json alone), `pictures/`), and `tools/studylib.py` holds
the helpers moved from `tools/end_zone_study.py` (`to_pixel`, `pixels_wgs84`, `disc`, `slope_degrees`, `margins`,
`profile_chip`, imported there again) with `linked_data_folder` and `grid_namespace` (the object
`end_zone_study.diagnose_line` reads, from a capture); the outputs outside the repository (`local/`);
`tests/test_slackmap_data.py`, `tests/test_studylib.py`, `tests/test_truth_study.py` (the Żabi Koń clip offline, also
with `--parallel` and the sag model), `tests/test_truth_analysis.py` (synthetic captures whose lines are
`find_valid_lines`' on the same grid)

## `tools/area_download.py`

Run by hand: the elevation models of a whole area into a data folder's cache, nothing else (`country run` then finds
them cached), resumable and for weeks:
`run <name> --area osm:<name> --source <id> --resolution <m> --data-dir <data> --state-dir <state> [--host-slots host=N] [--min-free-gb G] [--max-memory-gb G] (`plan_of`: the outline clipped to `Source.coverage_boxes` by `area.clip_outline_file` into the pass's work folder, the km² left out printed; the stored outline unchanged)`
a supervisor (one per area, a `FileLock`) starting passes, each a process of its own below the normal priority with
`GDAL_CACHEMAX` 512 MB unless the environment sets it (`CachedIndex.tiles` remembers an index out of reach as None for
the process, which would skip the whole layer: a pass names that a failure). A pass plans the source (`plans_of`:
`plan_of`, and the stand-in's plan where `Source.instead_without_data` names one (alaska → alaska_ifsar, which
`choose_source` never applies to a source given by name), its layers labelled "terrain (alaska_ifsar)", the totals
over both: `Reporter.next_plan`), inside its `try`: a `SearchError`, `ValueError`, `RuntimeError` or `OSError` of
planning (Denmark's key, an unknown outline) is a `Stop` with its text; the window layers' groups are
`country.PREFETCH_GROUP_M` times the finest native resolution of the plan's grouped layers (`_group_m`: a group's
window is read on the files' own pixels, whatever the grid's; Luxembourg's and Scotland's 0.5 m float64 files at the
app's 1 m minimum took about 5 GB a thread in 10 km groups and the passes were OOM-killed on a 62 GB server; 5 km for
them). Exit codes: `EXIT_DONE` 0, `EXIT_FAILED` 3 (tiles that failed, in `<name>.failed.json`; a failed tile goes on:
`sources.download_layers(on_error=)`, `Failures`), `EXIT_STOPPED` 4 (`Stop`: the plan, an index out of reach,
`FAILURES_IN_A_ROW`, a disk under `--min-free-gb`), `EXIT_RESTART` 5 (`Stop(code=EXIT_RESTART)` at the first tile
after the beat saw the process over `--max-memory-gb` (`memory_gb`, a quarter of the machine's memory by default, 0 no
budget): the supervisor starts the next pass at once and counts `restarts` in the state), `EXIT_NOTHING` 6 (no tile
under the outline, or every tile without data). After the pool `_count_missing` (`cache.count_missing`: the rows
"missing", one query per top-level folder) puts each layer's tiles without data into the state (`layers[k].missing`,
`tiles_missing`: the table, the page and the window's row show them). The supervisor: `EXIT_DONE` ends; `EXIT_RESTART`
at once when the pass made progress (`tiles_done` or `mb` grew), else after `RETRY_SECONDS`, and `ATTENTION_PASSES`
restarts without progress in a row "needs attention" (the budget too small); a restart never counts towards the other
attention rows; `EXIT_NOTHING` "needs attention" (exit 2); any other code after `RETRY_SECONDS`, and
`ATTENTION_PASSES` passes in a row ending the same way (`EXIT_FAILED` with the same tiles; `EXIT_STOPPED` with the
same message: Slovenia looped 37 passes at "50 failures in a row", Denmark 13 on a missing key; a crash, any other
code, with the same last line of the log, `_last_line`) "needs attention". A pass without `FINDALINE_CONTACT` warns in
the log and in the state's message (`NO_CONTACT`) until its first tile. The `Reporter` (the listener of the bars and a
thread every `STATE_SECONDS`) writes `memory_gb`/`memory_peak_gb` and a fourth column of the history CSV (old rows
read as before); its index counter lists this area's 0.25° tiles once per pass (`sources.indexes.cached.index_tiles`
when present, else the grid's box) and counts only their answers in the shared folder (`_index_folders`,
`_index_counts`). `--host-slots` sets `net.HOST_SLOTS_OF` and `layer.DOWNLOAD_THREADS` of this process only; the
outline in the state folder, never in `countries/` (`country._partition` would take it off the next country's
outline); `status [--watch S]`, `stop <name>`, `<state>/status.html` (one page for every area of the folder, from
disk), `<name>.state.json`, `.history.csv`, `.log`. On a network share: the data folder local (SQLite's WAL does not
work over a share) and the tile folders symbolic links to it; `tui --settings <file>` the window below;
`tests/test_area_download.py`

## `tools/area_download_tui.py`, `tools/area_rows.py`

The window of the area download (`area_download.py tui --settings <file>`, Textual, the group `tui`: not in a plain
`uv sync` nor in the image; `area_download.py` imports it only for that command): the coverage map's areas
(`area_rows.catalogue`: `coverage.json`, continents and km² from `shapes.json`, a region takes its country's
continent; `COUNTRIES` the titles, `OSM_NAMES` each area's Nominatim name, each checked once against the outlines: an
administrative boundary of the area, larger on a coast by the territorial waters) plus the settings' `extra`, grouped
by continent (`Collapsible`s of rows of `Checkbox` subclasses: a `DataTable`'s first click only moves its cursor, a
`SelectionList` has no cell to click for the target). A checkbox only chooses; Start and Stop ask first (`Confirm`,
the focus on Cancel). A row's name is its name in the state folder (`slug` of the title: `poland`, `czechia`, as the
downloads started by hand). The settings (a JSON file outside the repository: the docstring of `area_rows.py`) name
the state folder, a contact (`FINDALINE_CONTACT` of what starts, never on a command line; an e-mail address with a
dotted domain or an http(s) address, `contact_ok`, else a `SettingsError`), the targets (`data_dir`, `min_free_gb`,
`max_memory_gb`, `tiles`: the folder on a share) and rows' targets, `host_slots` and `max_memory_gb` (the row's over
the target's, as `--max-memory-gb` of `command_of`; neither: the downloader's default); the target chosen in the
window is kept in `tui-targets.json` of the state folder. Start: `links_of` (a share's tile folders, `Layer.folder`,
as links from the data folder's cache; a real folder with tiles stops that row), `make_links` (LAYOUT first, or a new
cache with links in it is refused as another layout; `os.symlink`, else one UAC window on Windows without Developer
Mode: `_elevated`, a script with its BOM for PowerShell 5.1), then `start`: `area_download.py run` detached
(`_detached`: a hidden console of its own on Windows, a new session on Linux, so it outlives the window and its
terminal). State from the state folder (`ad.areas`), as `status`. Everything has a key (a text console has no mouse);
`tests/test_area_rows.py`, `tests/test_area_download_tui.py`

## `tools/job_stats.py`

Run by hand (also on the VPS host with its `python3`: standard library only): where the computing time of the finished
searches goes, read-only from a `jobs.sqlite` (`--immutable` for a copy): by model, resolution, longest line,
circle/area and preset, the computing seconds (sum, median, p90), seconds and CPU seconds per step and per stage, the
funnel's ratios; `--phases`: the seconds between a job's timestamps (the waits for a download and a compute slot, the
phases), the computing seconds outside its steps, the steps `orthophoto` and `other`, and the tiles of an area
(number, the largest one's Mpx) from its "--- Tile k of N" lines; jobs from before migration 16 from their info
events; no ids, titles or places; `tests/test_job_stats.py`

## `tools/test_lock.py`, `tools/test_lock_page.py`

The test lock of parallel sessions and agents:
`run [--exclusive | --heavy] [--memory GB] [--resource NAME] [--first] -- <command>` waits in one
first-come-first-served queue (SQLite in `<git common dir>/findaline-locks/`, an OS lock per entry, so a killed
wrapper leaves nothing behind; `PRAGMA user_version` 1: the kinds of `uv run --frozen ...` with uv's own options
skipped, older rows migrated; a new table by `SCHEMA`'s `CREATE TABLE IF NOT EXISTS`, a new column of `entries` by the
`ALTER TABLE` loop of `Queue.__init__`, so older wrappers keep working), `status` lists it (the user's state first,
then the RAM line: free, total, the lock's budget); three modes (`MODES`): shared commands (`SLOTS` 6, below the
normal priority, threads capped to cores / `THREAD_SHARE` 3 whatever the slots: chosen from the lock monitor's data of
2026-11-01..03, a median of 0.8 cores busy per shared command), heavy ones (`--heavy`: big runs that measure nothing,
one at a time beside the shared ones, no slot, normal priority and all threads; a waiting heavy one keeps no shared
one out, only later heavy and exclusive ones, which pass it by their estimate) or one exclusive (normal priority,
nothing beside it); `--first` waits ahead of the waiting ones, never of a running one; `startable` decides, with
backfill: a later command passes a waiting one when it is expected to end at most `SLACK` (120 s) after the running
ones holding that one up that did not pass it, so passing never adds up (`--expect S`, else the times of the same
command or its kind in the table `history`, to pass the longest of its kind's last runs; without an estimate, first
come first served); the RAM guard (psutil optional: without it nothing is sampled or guarded): each wrapper samples
its command tree's RSS every `POLL` (`_tree_rss`, the tree listed again at most every `TREE_EVERY`: 75 ms with 600
processes on Windows), writes it to `entries.rss_bytes` (`Queue.touch`, with the read of `stop`) and the peak to
`history.peak_bytes`; `Queue.peak` (`--memory GB`, else the largest of the same command's last peaks, else its kind's
90th percentile) against `memory_budget` (the smaller of available − `RAM_MARGIN` 2 GiB and `RAM_SHARE` 0.8 of all
memory (the user's setting, table `settings`, read at every look so a change reaches waiting wrappers at once:
`test_lock.py ram-share [90|--reset]`, the page's "RAM limit" choice, `POST /api/ram-share`; `SHARE_MIN`/`SHARE_MAX`
0.5-0.98; `status` and the page show the limit, what the running commands may still grow by, and the budget) − used,
less what the running ones with a peak may still grow by and the peaks admitted before): a shared or heavy one that
does not fit waits "for memory" (counted toward `--wait`) with a reservation from the running shared and heavy ones
with a peak, so a later shared one that fits passes it; exclusive ones and those without a peak are not guarded; the
default `--timeout` the mode's (`TIMEOUT`: 1 h shared, 3 h heavy and exclusive) or `TIMEOUT_FACTOR` 1.5 × the estimate
when longer (`_timeout`, said on stderr); the user's state (table `state`, row `user`: `free`, `heavy-ok`, `busy` or
`quiet`, `STATES`, none = free; `until` and `after` (free unless given) resolved by every reader,
`user_state`/`resolve_state`, no timer;
`state [free|heavy-ok|busy|quiet] [--until HH:MM|'YYYY-MM-DD HH:MM'|+2h|+90m] [--after S] [--note T]` prints or sets
it, from any checkout): `startable(state=)` holds a waiting exclusive while `busy` or `heavy-ok`, a heavy one while
`busy` (while `heavy-ok` it starts tamed, `tames`: below the normal priority, `HEAVY_TAMED_THREADS` 16 threads at
most, `FINDALINE_TEST_LOCK=heavy-tamed`, `entries.tamed`; one started while free keeps its threads and priority,
"running untamed" in `status` and on the page, `untamed`) and every waiting one while `quiet` (`held`: not admissible,
it holds nobody up and has no reservation, so the shared ones behind it start as if it were not there, without an
estimate; `blockers` never names it), never a running one, `--first` among the admissible ones; the time held does not
count toward `--wait`; the wrapper's "waits" lines name the state (`describe_state`: "the PC is in use (busy since
14:02, until 18:00, then free)") or the RAM guard's need ("waits for memory: needs ~12.0 GB, 7.3 GB free for it (RAM
48.1 of 64.0 GB used, limit 80 %)"); a stop from the page (`entries.stop`, `Queue.request_stop`): the wrapper waits
for its command in rounds of `POLL`, reads its row (`stop_requested`), kills the tree and exits 125 (`STOPPED`), a
code never recorded into `history` (no estimate shortened); the page (`test_lock_page.py`: standard library and
`test_lock` from its folder, a `ThreadingHTTPServer` on 127.0.0.1:8771 (`FINDALINE_LOCK_PAGE_PORT`), meant for an Edge
app window): `GET /`, `/page.css`, `/page.js` (CSP `default-src 'self'`, nothing inline, dark and light),
`GET /api/state` (the state with its text, `now`, `slots`, the live entries of `Queue.live()` with `expected_end`,
`held_by` (busy, quiet, memory: `Queue.admission`), `reason`, `stop`, `tamed`, `untamed`, `memory`, `rss`, `peak`; the
top-level `memory`: available, total, budget, or null without psutil), `POST /api/state`
`{value, until, after, note}`, `POST /api/stop` `{id}` (a running entry, else 404); a POST needs the header
`X-Test-Lock: 1` and an own or absent Origin, else 403, a Host other than 127.0.0.1/localhost at the port 403, other
methods 405, other paths 404, a failing request 500 with the server going on; the slots and the RAM line in its
header, the buttons Free / Heavy OK / Busy / Quiet, the "until" choices (1, 2, 4 h, 18:00, 07:00, any time, then a
state), Stop asked once, a refresh every 3 s; `serve [--port N]`, `install` (Windows: the scheduled task "Find-a-Line
test lock page" at logon, the main checkout's `.venv` pythonw and its copy of the script, restarted every minute on
failure, started at once, by PowerShell's `Register-ScheduledTask`; the desktop shortcut `Test lock.lnk` running
`msedge --app=http://127.0.0.1:8771/`, Edge from the registry's App Paths), `uninstall`, both with `--dry-run` (an
agent runs neither for real: the user installs it); `tests/test_test_lock.py`, `tests/test_test_lock_page.py`

## `tools/clean_temp.py`

Run by hand: what tests and sessions leave in the system's temporary folder, by kind with sizes (`-v` every path),
`--delete` removes it: `tests/regression.py`'s folders (kept after a difference or with `--keep`), `ui-shots-*` of
runs that did not end, the extension packages new browser profiles leave (`Cr24` `<uuid>.tmp`), and the scratchpads of
this repository's ended Claude Code sessions (`<temp>/claude/<project>/<session>/`: no running process in any
`~/.claude*/sessions/<pid>.json` names it; without such files none counts as ended); only what nothing wrote into for
`--hours` (2) / `--session-hours` (24); links inside removed as links, never followed (a regression test's `cache` is
a junction to the real cache: Windows PowerShell 5.1's `Remove-Item -Recurse` would empty it);
`tests/test_clean_temp.py`

## `tools/record_answers.py`, `tools/cache_diff.py`

Run by hand: record small real answers of the index services (WFS, STAC, TNM) into
`tests/data/recorded/<interface>/<case>/` with the index JSON the code writes for them (`expected.json`; served again
by `tests/http_server.py`, the fixture `http_server` of `tests/conftest.py`: Range requests, recorded answers, a
request log); compare two cache folders (files, bytes, `index.sqlite` rows but for the times): a search on an empty
cache with the old and the new code of a refactoring of `sources/`
