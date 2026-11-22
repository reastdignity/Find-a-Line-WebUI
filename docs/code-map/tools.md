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

Batch 5 (wave 2): it also reads an INEGI sheet's whole ZIP (`_read_grid`: zipfile, the GRID cut as the layer cuts
it), a `ranged` layer's files through our own ranges (`_read_ranged`), a `warp` layer's files with its resampling, a
cartoteca sheet's grid inside its ZIP (`_gdal_path`: `<zip>/<member>` by `/vsizip/`), and LercTiles and
ZipSheetTiles as services (no source files to compare).

Batch 6: a ZIP member (`ZipMemberTiles`, `PackageTiles`) is read again by Range under its own rule, never through the
layer's `TransformFix` (`_zone_free`: an easting with the zone in front without it), so a wrong fix shows; an XYZ
member in columns with points missing read in rows (`zipmember.xyz_rows`); a `PackageTiles` tile's member taken in the
tile's own CRS (its zone's), as the layer writes it.

## `tools/au_coverage.py`

The static cells mask of Geoscience Australia's 5 m lidar DEM (`sources/catalogue/australia_dem5m_cells.npz`):
the WCS grid sampled every 88 × 80 of its pixels (about 485 ×
412 m) in 2 × 2 requests of at most 4096 px, a cell of 4 × 4 samples (about 1.9 × 1.65 km) has data when any sample
is non-zero; `GeoWcsTiles.has_data_near` reads it. Run it again when GA adds surveys and commit the file
(`tests/test_australia_uruguay.py` pins the places).

## `tools/lerc_coverage.py`

The static cells mask of an Esri elevation tile cache (a `LercTiles` source's `cells`:
`sources/catalogue/northern_ireland_dtm_cells.npz`, `rio_de_janeiro_dtm_cells.npz`): the cache walked from level 10
(`START_LEVEL`) to 13 (`LEVEL`) over the source's boxes, a tile with a valid sample opening its four children; at
level 13 each tile split into 8 × 8 cells (`PER_TILE`), a cell True when a valid sample lies in it; one request at a
time, 1.1 s apart, through the layer's reader; `--check-box` asks every level-13 tile of a box and counts the cells
the mask missed (must be 0). Read by `LercTiles.has_data_near` and `MercatorTiling` (no tile asked far from data).
Northern Ireland's took 795 tiles in 1 025 s (2026-11-15). Run it again when the provider adds surveys and commit
the file (`tests/test_lerc_tiles.py`).

## `tools/mx_sheets.py`

The static mask of the cells of INEGI's lattice that hold a 5 m sheet, per model
(`sources/catalogue/mexico_sheets.npz`, read by `InegiIndex`): the download viewer's two lists (`getFormato10k.do`,
mod T and S) read once; it stops if a centroid's cell does not carry its sheet's name. The models are frozen
(2006-2012): run it again only if INEGI publishes new sheets (`tests/test_mexico.py`).

## `tools/tokyo_sheets.py`

The static table of the Tokyo Digital Twin's 0.5 m grid sheets (`sources/catalogue/tokyo_sheets.npz`, read by the
`tokyo` layer: a sheet outside it is never asked, since the bucket answers 403, never 404, for a key it does not
have): every sheet with the folder it lies in (2023: Tama and the islands; 2024: the 23 wards; a sheet may be in
both), from the publisher's index vector tiles (Mapbox vector tiles at zoom 12, fields MESH_NO and URL) read with
GDAL's MVT driver through pyogrio. Every code must be a 1/500 sheet of zone IX (`japan.jp_cell`) and its URL the
folder's address of that code, or it stops. One request at a time, at least `PAUSE_S` apart; `--count` says how many
tiles a run asks without asking any. The surveys are frozen: run it again only when Tokyo publishes more sheets,
check the tests' places and commit the table (`tests/test_japan.py`).

## `tools/hong_kong_sheets.py`

The static table of CEDD's 2020 lidar sheets of Hong Kong (`sources/catalogue/hong_kong_sheets.npz`, read by the
`hong_kong` layers: a sheet outside it is never asked, a 404 for one in it is that tile's error), from the CSDI
Portal's FeatureServer (layers 0 DTM_2020 and 1 DSM_2020: TILE_NAME, Filename, URL and the footprint, paged by
3 000: four requests). Every row is checked (the code a sheet of the scheme, `hong_kong.hk_cell`, whose box is the
footprint; the URL the layer's folder and its file name; the name starting with the code), else it stops; the file
names are kept as published (map 17's kilometre pairs are not those of the sheet's box). One request at a time, at
least `PAUSE_S` apart, each under one of the host's slots of the data folder (`net.host_slot`); the answers kept in the
work folder; `--count`. The survey is frozen (2020): run it again only when CEDD publishes more sheets
(`tests/test_hong_kong.py`).

## `tools/mirror_tiles.py`

Run by hand under the test lock with `--resource data` (or in a container of the project's image on another
machine: the docstring's example mounts the clone's `tools/`, which `.dockerignore` keeps out of the image): own
copies of elevation models that cannot be read in parts from their provider, for the mirror. `DATASETS` holds
`Dataset` records (a folder of products `<dataset>/<product>/<res>m`, names in `[a-z0-9_-]+`, each `Product` with its
CRS, `origin`, inputs, masks and overlap rule) and two dicts of before that `dataset()` makes records of (`madeira`,
DROTe's MDT 2 m, one ZIP of one BigTIFF; `aosta`, Valle d'Aosta's DTM 2005/2008 2 m, one Deflate64 ZIP of an ASCII
grid with decimal commas: their index keys and published cards `MADEIRA_CARD`/`AOSTA_CARD` stay; a fixed card covers
one product). Madeira's 5 m ZIP gives three datasets: `porto-santo` (EPSG:3061, the sea 0), `desertas` (EPSG:5016
over the file's EPSG:3061 label) and `selvagens`, both with a floor of -1 m. Inputs: `Url` (one GET at a time under a
lock in `--work`, through the app's headers, rate and counting; a resume by `Range: bytes=N-` only below
`resume_below`; a 200 to a Range rewrites from the start; never past the known size, `SizeChanged`), `Placed` (one file
matching a glob in `--inputs`, either case), `Fetched` (a folder tools/cdd_fetch.py fills: manifest.jsonl's rows of a
collection, or a fetch-list group counted in status.json, each file an input once done.jsonl records it whole, its
sha256 checked when read), each with its ZIP `members`. A product is cut once, when `resolve` finds it complete
(`--without <ids>`: sheets never delivered, recorded as `missing_inputs`), in a staging folder (`staging_folder`:
`--work/staging/...`, or `<out>/.staging/...` when a folder does not rename from `--work` into `--out`), with an
append-only journal (`Journal`, `--work/journals/`, one per mirror folder: a line per finished tile after its file is
synced, with its feeders in order and the product's rule, `product_rule`); a restart keeps a tile whose file matches
its line, whose feeders and rule are the same, and cuts every other one again (`_cut_staged`);
`_finalize` writes index.json, renames the folder into the mirror in one `os.replace`, then writes the card. A final
product is never cut again. `WRITE_SITES` names every write a stop could interrupt (`_site`, `HOOK`: the tests stop
the run at each). `assemble` reads every raster covering a tile, masks it (`mask`) and joins them by `overlap`;
`--threads` writers and GDAL's cache within `--max-memory-gb` (an estimate, `_workers`); tools/sk_tiles.py's encoding.
Caches only: `State` (footprints, checked files) and `WorkFiles` (unpacked members, tiled copies of ASCII grids and of
wide strips, made again when their source changed; `clean` removes only these, through `_remove`). `check_folders`
keeps `--work`, `--inputs` and `--out` apart. `verify` (final products): every sha256, unlisted files, the tiles the
inputs' own bounds touch against the index, the inputs against the journal's feeders, sampled tiles (1 %, 8 to 500,
`--seed`) re-assembled and `POINTS` pixels read straight from the inputs (`_point_problems`), judged against the
inputs the cut read (`inputs.jsonl` in the final folder, `INPUTS_FILE`: an input that came later is no part of the
edition); tiles whose inputs are gone or changed are not checkable, and a verify that compares no tile with data is
"not checkable" (keeping an earlier passing `verify.json` of the same index); the result in `verify.json` beside the
index. A journal line's rule carries `CUT_VERSION` (raised by hand when a change could change a cut's output).
`status` (final / cutting / ready / waiting; every staging folder listed), `all` (cuts every complete product, a
waiting one is no failure; a final verified one skipped), `clean` (a final product's staging folder, or with
`--staging` one no run cuts now). One run at a time per `--work` and per product (`_locked`, the product's lock in
`<out>/.locks`, never inside a dataset's folder: `Busy`). A product's `crs`, `res` and `origin` equal the catalogue layer's (`GridTiles(origin=)`), its source's default
resolution a whole multiple of its pixel and at least 1 m (`tests/test_mirror_tiles.py`).

## `tools/cdd_fetch.py`

Runs on another machine (a home server, a stock Python container), not in the app: standard library only, no
import of the project. Bulk copies for the mirror into `downloads/` beside the script: `plan` walks the CDD's public
search (Portugal's MDT/MDS 50 cm and the Azores' 1 m models; pages by the `next` body's token; the newest version of
each sheet; no address stored: a search mints a new one each time), `fetch` signs in through the Keycloak form
(`CDD_USER`, `CDD_PASSWORD`; only https to the site's and the realm's hosts, at most 6 an hour, 60 s apart, kept
across restarts in `signins.json`), resolves addresses 20 ids per search and fetches one file at a time, 1.5 s
between requests to a host, https only, none after a stop (TIFF magic and stated size, sha256 into `done.jsonl`; a
session lost means one sign-in and one retry, three credential sendings without a file stop; 429/503 wait; an error
before an answer's headers is an outage of the step that failed (sign-in, address search, download; waits
doubling, up to `--outage-hours`, ended only by that step coming through), one after them that file's attempt (three, then failed); no proxy; five failures in a row, low disk or SIGTERM stop cleanly; `fetch.lock`: one fetch per
folder, `--no-lock` for a filesystem without locks), `fetch-list wallonia` the embedded list of SPW's ten province
ZIPs (no Range: a broken file starts again), `status` both. Secrets are masked in every output (`Scrub`);
`tests/test_cdd_fetch.py` runs it against a fake CDD.

## `tools/mirror_publish.py`

Run by hand on the PC that holds the master (docs/mirror-hosting/spec.md, solution B): publishes the mirror's datasets
to the home server's `<root>` over rclone (1.76 or newer, `PATH` or `FINDALINE_RCLONE`; an SFTP remote of the user's
own rclone config with `hashes = sha256`, `sha256sum_command = sha256sum`). `verify` (a folder: hashed here, `readme_notes` noting a dataset's `README.md` that is not the served card,
U57; a
remote: `rclone checksum sha256` by the server), `publish` (refusals first, then under the lock `staging/.lock` with a
token read back: the server's sha256 proven on the lock file (U35), "published already" unless `--same-values`, free
space; the listed files copied into `staging/`, the card, the staged copy verified, two checked moves through
`trash/`, `datasets.json` through a hidden name), `unpublish` (a takedown), `clean` (trash older than `KEEP_DAYS`),
`stats` (the server's log: requests and bytes per day and dataset, refusals per limit, client versions by
`client_version`; never an address). `PUBLISHABLE`: one approved row per dataset (Slovakia,
Madeira, Valle d'Aosta, Porto Santo, the Desertas, the Selvagens; the attribution from the catalogue), `cards()` the cutting tools' texts, `required_folders` from `GridTiles(averaged=)`.
Prints its own lines only, never rclone's or the remote's name. `tests/test_mirror_publish.py` (rclone's local backend
as the server; skipped without rclone), `tests/test_mirror_pairs.py`.

## `tools/mirror_watch.py`

Run by hand or by the monthly workflow `.github/workflows/mirror-watch.yml` (docs/mirror-hosting/watch.md; standard
library only, no import of the project): whether the providers of the mirror's datasets replaced a file or published
a successor. `WATCH`: per dataset its signals, `File` (a HEAD: size, Last-Modified, ETag), `Feed` (an ATOM feed's
matching entries: `updated`, enclosure lengths) and `Listing` (the set of strings patterns extract from a page, feed
or record); `Http` asks each address once a run, 1.5 s after the host's previous answer, without redirects, cookies
or a proxy. `check` (one line per dataset, exit 0/1/3/2; `--json`, `--json-out`, `--previous`: a first "not
checkable" does not make exit 3), `adopt` (rewrites the datasets' records in the committed `tools/mirror_watch.json`,
refusing a signal not checkable), `list`. `tests/test_mirror_watch.py` (against `tests/http_server.py`, the real rows
on cuts of the providers' answers, the workflow's YAML), `tests/test_mirror_pairs.py`.

## `tools/mirror_sizes.py`

Run by hand (M1 of the mirror hosting; under the test lock with `--resource data` on the mirror; standard library
only, so also on the mirror's server): read-only sizes of a mirror folder (`--mirror`, default `FINDALINE_MIRROR`)
from its `index.json` files and one `os.scandir` per block folder, never opening a tile: per product folder the
tiles with data and null, bytes, tile sizes (min, median, mean, p90, p99, max), files not listed and listed tiles
missing; the tiles and MB a square search of 2, 5, 10, 20 km asks of the mirror over every placement on a `--step`
lattice whose centre lies in data (`axis_groups` and summed-area tables; a square covers every tile it touches from
the index's `origin`), per product and the products of a dataset together (products on different grids: a line
saying they were left out); whole-dataset totals. A "partial" folder is listed and left out of the rest; so is one
without index.json, with an unreadable one or one without "tiles", with a note, and the exit code is then 1. Table on
stdout, `--json` (the mirror named `<mirror>`; refused inside the mirror by any spelling: `inside`, realpath and
normcase); `tests/test_mirror_sizes.py` (a brute-force walk over the lattice, `weighted_rank` by hand)

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
cubes in view), `c-layer-study` (the study area alone), `c-layer-end` (the phones' column at its histograms),
`c-layer-cell` (a cell selected), `c-layer-collapsed` (the left panel a rail, `LAYER_LAYOUTS`), `c-layer-chips` and
`c-layer-fold` (two filters of the fold set: its chips, then opened) and `c-layer-border` (a cell the border cuts
selected, its card and the notes: `border_view`) over three cubes v2; `--run <folder> --line <lat1,lon1,lat2,lon2>`
shows a saved run (copied into the shots' data folder) with that line open: the pages `c-result-rigging` (the rigging
filter) and `c-line-profile` (the profile card), with `c-line` and `view3d` of made-up counts of
`tests/test_country_web.py::sample_cube` (`slovakia` and `testland`, as its fixture, and the study area `sk-part`).
A page whose feature the run lacks (`NEEDS`: `c-result-rigging` a no-fall zone or A-frames, the `c-result-shore*` pages
an uncertain shore, `c-result-why` the square rule; `run_features` reads run.json before any browser) is left out
without a load, and a page whose step `need:<expression>` is false once the result is drawn as well. Selection:
`--only`, `--exclude` (substrings), `--themes light|dark|both` (`--dark` = both), `--list` (the pages and which the run
leaves out, no browser). No fixed sleeps: after a load and after each step `settled` waits for a quiet time with no
request in flight (Playwright's events, the event stream ignored), no tile loading (a failed one is not waited
for), map move, CSS animation, busy spinner, animation frame or short timer (`WATCH`, an init script) and the mark of
the page's family (`page_family`, `PAGE_STATE`), at most 30 s after a load and 10 s after a step, then shot and noted "not settled"; a `wait:` waits at
most 10 s, a first-draw mark (`FIRST_DRAW`) 30 s, `c-basic-sea`'s estimate 240 s (`SLOW_MARKS`); a mark that can no
longer come (`GIVE_UP`: the estimate "unavailable" or "refused") ends its wait at once, as a timeout. Each picture is
printed with its seconds, then a summary (set-up parts, passes, the ten slowest pages, the pages left out, timeouts,
failed steps, the pages not settled); `--timings <file>` the same as JSON; a timed-out wait
gets a quarter of its limit for the rest of the pass, a step that raises fails only its page, `--strict` stops at
the first; exit code 1 after a timeout or a failed step (a page whose click finds nothing after a wait timed out is
"timed out", not "left out"); a whole page too tall at the device's pixel ratio (WebKit's
32767 px) is taken at one pixel per CSS pixel, a note. For a caller that measures the prepared pages: `shoot_all` (the
passes' loop, rows kept as made, `on_row` called with each), `pass_context` (a pass's context, the caller's options passed on) and `shoot_page`'s
`act` (in place of the screenshot, its dict in the row). A `--data-dir` used before can be used again: its marker
`ui-shots.json` (the clip run shown and `data_key`, a sha256 of the root `*.py`, the tool, the cubes' test module, the
clip's files and the checkout's path, which the clip run's files name) keeps the clip run and the cubes while the key is the same (`--fresh` makes them anew and removes the
clip run made before: one in the folder, a failed removal retried at every start, the problem report made again);
each start ends the tool's users' sessions before making theirs (one run at a time per folder); the Basic
form's riggers get only the rigs they do not have yet, the problem report is added once. The runs open from their
store over http (no `file://`): the clip run's credits go into run.json and the store's head (`with_credits`; a
run's data.js only when it has one: a `--run` of a run saved before store wave 4), and the lines naming the 3D
view's pages come from the store (`first_line`; data.js for such an old run; printed: `lines_read`)

The result view's map states (`c-view*`: the first view, Area, Spots, Lines, Best 30, All refused, Lines held, several
spots under one press, the map's controls open, a phone's sheet raised to half) open with the page's flag: `VIEWS` names the
pages whose `findaline.view` `page_storage` sets (removed for every other page of the pass), each waits for
`window.FINDALINE_VIEW` (`VIEW_READY`), and a run whose store has no column `spot` leaves them out (`NEEDS` "view":
`store_has_view`); `tests/test_ui_shots_view.py`. Its panels' states: `c-view-selected` (a phone: the low
sheet's head; `-half`: its details), `c-view-fan`, `c-view-sector`, `c-view-all-levels`, `c-view-why`, `c-view-start` (a
phone's sheet at full height for the list's states: `VIEW_HALF` twice); their steps are scripts and waits only.

## `tools/shots_diff.py`

Run by hand: two folders of screenshots (`tools/ui_shots.py`'s, before and after a change) compared file by file:
only in one, sizes that differ, or the share of pixels whose largest channel difference exceeds `--threshold` (8 of
255) and the largest difference; a table sorted by that share and a line of totals, exit code 0 always (it reports,
map tiles differ from run to run); `--out` a difference picture per file that differs (the first picture dimmed, the
changed pixels red). Pillow and numpy (`tests/test_shots_diff.py`)

## `tools/ui_metrics.py`

Run by hand: counts and measurements of the UI for design work, with no pass or fail (the user picks thresholds from
the numbers; the bounds are parameters). `static` reads the source only: viewer/src's CSS by its own scanner (no
nested rules), the .ts/.tsx code without comments and regular expressions, `locales/en.json`: distinct font sizes
(`var()`/`calc()` "unresolved"), radii, z-index values, the px lengths of padding, margins and gaps with those off R7's
steps and their places (`R7_STEPS`; a length inside `calc()` or `env()` not counted), normalised colour literals
outside `ui/tokens.css` (in the CSS also its 148 named colours, `CSS_COLOUR`), the monospace font and its uppercase, "the same grey box" per selector, characters used as
icons or joints (those in an `aria-label` or `title` apart, the demo pages left out unless `--with-demos`), dense
strings per literal, the catalogue's words per group with the texts over R10's limits (`r10_over`: `R10_LIMITS` by the
key's kind, `R10_BY_ROLE` by role, the coverage page's catalogues too; `tests/test_words.py` fails on the same lists),
.tsx files with English text and no `t(`. `pages` measures every state of
`ui_shots.PAGES` through `ui_shots.serve`, `select_pages`, `left_out_by_run` and one `shoot_all(act=,
bypass_csp=True)` per device and theme (axe-core cannot be injected under the app's CSP; the screenshot tool's own
contexts never bypass it), on a `--data-dir` of its own (one run per data folder; `--fresh` builds it anew; a kept
folder is only safe while the checkout that made it exists). Per state, where the screenshot would be taken: every
control's target size (with an absolutely positioned `::before`/`::after` that grows it, a checkbox or radio by its
largest label, the part no ancestor clips, per axis and from the containing block up; unreachable ones apart; covered
ones marked with the element hit at the centre of their seen part, still counted; a link or button in a sentence
apart: inline, and its block holds words outside controls; signatures without state classes, `BASE_CLASSES` kept by
hand); every visible text's rendered size (SVG scaled) with its zone (a map's credits or scale) and nearest named
ancestor; the document's width; elements that scroll sideways; rendered grey boxes among containers; axe-core's
violations and "incomplete" by impact (`viewer/node_modules/axe-core/axe.min.js`, a development dependency; without it
the axe part is left out with one line). `pages-states.jsonl` keeps every size and a `definitions` number, so
`--summarise --controls 40 --text 11` cuts at other bounds without a pass and names a log of older definitions; a
state whose wait timed out or that failed is "not measured" with its reason and never counted; a state a device or
the run cannot show is "left out" with its reason; a stopped pass leaves its remaining states recorded. `pages.json`
and `pages.md`: totals per device and theme, page families by name prefix, lists by signature; `pages-run.json`: the
seconds and whether each pass finished. Exit code 1 when a state was not measured or a pass did not finish. Known and
left: docs/known-bugs.md, "The UI measuring tools" (`tests/test_ui_metrics.py`)

## `tools/ui_walks.py`

Run by hand: task walks through the app, counted. Each walk of `WALKS` (a user of `ui_shots.serve()`, a device of
`ui_shots.DEVICES`, what the browser remembers, a start address, its steps) is driven with Playwright on `serve()`'s
public site. Before each action it counts the surface's visible, enabled controls and words, then times the action to
its expected state and checks for feedback within 300 ms. Per walk: screens, taps or clicks, keystrokes, changes
between pointer and keyboard, decision points (an action among more than 4 controls), words, waits, dead ends. Writes
a screenshot per step (share links masked), `walks.json` and `walks.md`; `compare` checks two runs' counts; `probe`
lists a surface. No walk starts a search. The data folder must be a fresh one: a folder that holds a job or a
favourite is refused (R4 saves a favourite, and Home then counts differently) (`tests/test_ui_walks.py`)

## `tools/perf_*.py`

Run by hand: the measurements of docs/performance.md: `perf_run_load.py` (a run's result and its first line's 3D view
opened in headless Chromium on the local app over a scratch data folder, the runs copied and the cache linked: the
page's User Timing measures, `viewer/src/perf.ts` "fal:run:*"/"fal:3d:*", the long tasks and heap, data.js as a script
against fetch + JSON.parse (a run saved since store wave 4 has no data.js: left out, said in the report), gzipped
sizes and their times at 10/50/200 Mbit/s; a run needs run.json and its store or data.js, its first line from the
store (`first_line`, data.js for a run saved before it; `line_read` says which); `tests/test_perf_run_load.py`),
`perf_profile.py` (cores and memory of a search per stage, a timeline chart; `--cores N` like a worker container;
`--memory BYTES` the budget of a compute slot (`search.available_memory` answers it), so an area's tiles are sized as
the web worker sizes them; a bar of parts (`progress.compute.update(n, part=...)`) is listed per part),
`perf_download.py` (the download phase on an empty cache with N threads), `perf_sqlite.py` (`jobs.sqlite` under K jobs
and M open pages), `perf_lines_memory.py` (bytes per line of steps 3, 4 and 5, from a capture of
`perf_line_funnel.py`: `--call`, or of the join of a tiled run's tiles and, for tile files that still hold the pixel
columns (written before 2026-11-01's wave 5), its steps 4 and 5: `--tiles`; the traced heap of one process; step 5
`save_step5`: what `save_run` writes since store wave 4, `mapping.view_columns` and `linestore.write`, or a
`--repo` without linestore.py (a checkout before the store) its text files; `tests/test_perf_lines_memory.py`),
`perf_slot_memory.py` (the memory of one search's whole process tree, as `search.LINE_BYTES` counts it: the search
through `perf_profile.py` in a child process with hooks (the stages, `mapping.view_columns`, `linestore.write`,
the plan's pixels, the square rule's `peak_rows`; `saving.py`'s hooks and hand-over term went with it in store wave
4), the tree sampled every 0.2 s (working sets, private bytes, `--uss` unique sets, the machine's used memory); the
peaks and where they fell, and the unique sets' peak (`peak_tree_uss_mb`, the measure);
`--cores`, `--memory`, `--worker` for a compute slot's shape (the search's own plan only); a refusal as its code, a
missing record or run as a warning; `tests/test_perf_slot_memory.py`, which also pins `perf_country.py`'s copy of
`LINE_BYTES`);
`perf_profile.py --tracemalloc` the heap per stage; `perf_window_reads.py` (the bytes, requests, seconds and memory of
a window layer's blocks over a circle on an empty scratch cache, each mode in a child process: `blocks`, `group=<m>`,
`serial=0|1`, `order=squares|tasks`, `cache=<MB>`, `multirange=`, `gdalthreads=`; GDAL's network statistics through
ctypes into rasterio's GDAL library, our own range requests counted at `ranges.get_range`; the files' internal tiles
as the prediction, per block and each once; `tests/test_perf_window_reads.py`), `perf_reach.py` (the reach of one
anchor over a 3D patch's lattice by batched numpy and by `linesearch.evaluate_lines`, both checked against
`helpers.evaluate_line`: seconds, memory, numba's one-time costs, the representatives of three rules, an answer's
size; what `search.reach_of_anchor`'s engine was chosen on; a run's lines through `run_rows`: the CSV export of its
store into a temporary folder by a child process (the measuring process stays as before step 1), or the lines.csv
of a run saved before the store (its three named cases, `find_run`: in `<data>/runs/`, then in
`--reference-dir`, default `<data>/local/reference-runs`), the results' `lines_read`; `tests/test_perf_reach.py`),
`perf_cached_check.py` (where the time between the start of an area download's pass and its first tile goes, for one
area of a state folder on its real data folder: the plan (`area_download.plan_of(area, work)`, its work folder a
scratch one), `layer.tiles`, the paths, the files asked one by one and by one listing per folder, the index rows
asked one by one and in one query, each pair's answers compared, then `layer.to_download` as a search asks it or,
with `--by-folder`, as a pass does (`sources.layer.EXISTING`), and the prune at a pass's end with `cache.forget`
replaced by a counter (`dry_prune`: nothing deleted); `--only <step>`; it stops when an index answer is not cached;
the cache is written only where a file without a row is adopted by `check`; `tests/test_perf_cached_check.py`)

`perf_run_load.py --view` opens the result view (the page's flag) and reports its phases ("fal:view:*") and which page
drew the run; `--interact` times changes on the open page from the call to two frames later, with their part in script
(the view: a filter, "Top level only", Best, a held level, "Lines from here"; today's page: a filter, the grouping
distance); `tests/test_perf_run_load_view.py`.

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
machines, data and services); a run's lines (`read_lines`) from its lines.npz (`profile --lean` until store wave 4;
`--lean` is accepted and does nothing since), its store (`linestore.read`'s columns in memory, grouped and in
lines.csv's order: length, clearance, height and the first anchor's coordinates unrounded, so a line at a band's or
cell's edge may take another key than its lines.csv's rounding) or the lines.csv of a run saved before the store,
`lines_from` in compare's, cube's and relief's results; a lines.csv over 200 MB packed once into
`perf_country_cache` in the system's temporary folder, never beside the run;
`tests/test_perf_country.py`

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
1 and 2) and `/api/profile` answers of a few lines of a data folder's runs (`run_anchors`: from the store, or the
data.js of a run saved before it; the index's `lines_read`) from the local app in-process, `serve`
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
`jobs.kill_tree` at `--timeout` and Ctrl+C), a run's line files (`RUN_FILES`: the store, map.html, ATTRIBUTION.txt
and the text files of a run saved before store wave 4; 31 GB on the first pass) deleted once its capture is written, run.json kept (`--keep-runs` keeps them all); a pass under `tools/test_lock.py run --heavy`);
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

## `tools/prune_study.py`

Run by hand: what a pruning rule keeps of a saved table of lines and an audit of what it drops (line-volume study,
K-49), offline, nothing written beside the run: `<run folder> --rule <name> [--param k=v] [--rules-file F.py]
[--radius M] [--known <truth-check pass folder>] [--terrain F.npz] [--pictures] --out <folder>`; rules are functions
from the table to a mask of kept lines, registered with `rule` (`higher_wins`, `best_per_cell_pair` shipped);
`table.terrain` the grid under the anchors for rules that judge an anchor by the ground; the table of a run's store
(the CSV export in a temporary folder, the search's order and unrounded values from `linestore.read`: `Table.source`
"store") or of a run saved before it (lines.csv, with lines.js "lines.js"); places by `mapping.group_lines`; `audit.json`, `audit.md`, `violations.csv`, the same on every run and number of threads; known
lines as counts only; `tests/test_prune_study.py`

## `tools/estimate_study.py`

Run by hand: the size of a search estimated from a sample before its pairs (`search.sample_estimate`, the web
worker's estimate, docs/line-volume/spec-search.md section 2) against the exact count, per case, fraction and seed,
in both designs (anchors: the lines found, part P4; the square rule's squares: the lines kept, part M2), offline from
the cache: `[--fractions F,..] [--seeds N] [--seed-rule study|search] [--owner USER] [--designs anchors,squares]
[--square M] [--exact] [--limit N] [--name NAME] [--out F.json] -- <findaline.py options>`; step 1 once, each tile's
window and anchors as the search's, one `sample_estimate` per design, fraction, seed and tile; seeds of the studies
(`default_rng([1000 + s, tile])` anchors, `[2000 + s, tile]` squares) or the search's own (its hash, with the job's
owner); `--exact` the lines found, kept after the join, kept per tile before it and the keys seen from their first
square; `--limit` the band's verdict; JSON written whole then renamed, no coordinates; `study()` in Python;
`tests/test_estimate_study.py`

## `tools/area_download.py`

Run by hand: the elevation models of a whole area into a data folder's cache, nothing else (`country run` then finds
them cached), resumable and for weeks:
`run <name> --area osm:<name> --source <id> --resolution <m> --data-dir <data> --state-dir <state> [--host-slots host=N] [--min-free-gb G] [--max-memory-gb G] [--queue key] (`plan_of`: the outline clipped to `Source.coverage_boxes` by `area.clip_outline_file` into the pass's work folder, the km² left out printed; the stored outline unchanged)`
a supervisor (one per area, a `FileLock`) starting passes, each a process of its own below the normal priority with
`GDAL_CACHEMAX` 512 MB unless the environment sets it (`CachedIndex.tiles` remembers an index out of reach as None for
the process, which would skip the whole layer: a pass names that a failure). A pass plans the source (`plans_of`:
`plan_of`, and the stand-in's plan where `Source.instead_without_data` names one (alaska → alaska_ifsar, which
`choose_source` never applies to a source given by name), its layers labelled "terrain (alaska_ifsar)", the totals
over both: `Reporter.next_plan`; a pass asks each layer's `to_download` for its counts and hands the first plan's
answers to `download_layers(listed=)`, so the source's own layers are asked once (a stand-in's ask again before
their download, hours later), and asks about the files by folder, `run_pass` setting `sources.layer.EXISTING` for
the pass and giving it back: docs/performance.md, "The check of cached tiles"), inside its `try`: a `SearchError`, `ValueError`, `RuntimeError` or `OSError` of
planning (Denmark's key, an unknown outline) is a `Stop` with its text; the window layers' groups are
`country.PREFETCH_GROUP_M` times the finest native resolution of the plan's grouped layers (`_group_m`: a group's
window is read on the files' own pixels, whatever the grid's; Luxembourg's and Scotland's 0.5 m float64 files at the
app's 1 m minimum took about 5 GB a thread in 10 km groups and the passes were OOM-killed on a 62 GB server; 5 km for
them). Exit codes: `EXIT_DONE` 0, `EXIT_FAILED` 3 (tiles that failed, in `<name>.failed.json`; a failed tile goes on:
`sources.download_layers(on_error=)`, `Failures`), `EXIT_STOPPED` 4 (`Stop`: the plan, an index out of reach,
`FAILURES_IN_A_ROW`, a disk under `--min-free-gb`), `EXIT_RESTART` 5 (`Stop(code=EXIT_RESTART)` at the first tile
after the beat saw the process over `--max-memory-gb` (`memory_gb`, a quarter of the machine's memory by default, 0 no
budget), or holding `BIG_PASS_GB` (2) or more while the machine has less available than `machine_free_gb` keeps
(`MACHINE_FREE_SHARE` 5 %, at least 2 GB: four big areas at once filled the Unraid server, 2026-11-14), and only
when it is the largest running pass of the state folder (`biggest_running`: the other areas' states written within
`RUNNING_STATE_S`, stage listing or downloading; a tie by name), so big areas restart one a beat; the message
keeps the sample that crossed: the supervisor starts the next pass at once and counts `restarts` in the state),
`EXIT_NOTHING` 6 (no tile under the outline, or every tile without data). After the pool `_count_missing` (`cache.count_missing`: the rows
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

The queue (`run --queue <key>`, `Area.queue`; the window passes the source of a row whose source has parts): the
areas of one key download one at a time, in the order their supervisors were started. Before each pass a supervisor
takes its turn (`_take_turn`: the `FileLock` `<key>.queue.lock` of the state folder, the key's characters unfit for
a file name replaced; an OS lock on a local disk, so a killed supervisor's is free at once; the state folder is
never on a share, where filelock may fall back to a lock file that a kill leaves behind): its state says `queued`
with its ticket (`queue`, `queued_at`: `_ticket`, the starter's time in `FINDALINE_QUEUE_TICKET`, which
`area_rows.start` sets so that rows started in a loop keep the rows' order, else the supervisor process's creation
time; then the name), written again every `STATE_SECONDS`. It tries the lock every `POLL_SECONDS` and, holding it,
keeps it only when no area waits in the same queue with an earlier ticket (`_ahead`: a state `queued` written within
`RUNNING_STATE_S`, so one killed while it waited is passed over; the other states are read only with the lock in
hand, never while another area downloads: fifty waiting supervisors read nothing), else gives it back. With the
turn its state says `listing`, so no later area takes it for waiting (a state left at `queued` held the next area
back for `RUNNING_STATE_S` and made the tests pass without the lock: the code review of 2026-11-18). The first time
it waits `QUEUE_SETTLE_SECONDS` before trying, so supervisors started together have written their places: the
one-at-a-time rule is the lock's, the order as good as those states. The turn is kept for a pass started again at
once (`EXIT_RESTART` with progress) and given up for a wait of `RETRY_SECONDS` and at the end (`rest`); the ticket
stays, so the area is the next again. The stop file ends a queued area as a running one. `summary` gives a queued
area no speed or time left; the window calls it live (`LIVE`), so Stop works on it and Start does not start it twice,
and counts it apart ("1 downloading, 49 queued").

## `tools/area_download_tui.py`, `tools/area_rows.py`

The window of the area download (`area_download.py tui --settings <file>`, Textual, the group `tui`: not in a plain
`uv sync` nor in the image; `area_download.py` imports it only for that command): the coverage map's areas
(`area_rows.catalogue`: `coverage.json`, continents and km² from `shapes.json`, a region takes its country's
continent; `COUNTRIES` the titles, `sources.AREA_NAMES` each area's Nominatim name (also the country layer's
territories), each checked once against the outlines: an administrative boundary of the area, larger on a coast by the
territorial waters), the parts of the country-wide sources (`area_rows.parts`, `PARTS`: the 50 states of `usa`,
"United States: Texas" / `united-states-texas`, and the 13 provinces and territories of `canada`,
"Canada: Alberta (NRCan)" / `canada-alberta-nrcan` showing "Alberta · canada" beside the regions of the map of the
same provinces; rows only, no areas of the map; their km² a table of land areas; Nominatim's name
"<part>, <country>" unless the table gives another: "New York State", "Washington State", since the plain names give
the city and the District of Columbia, each checked against its outline on 2026-11-18; `PART_NAMES` keeps the name a
part's download ran under before, Utah's `utah`; the country-wide row of such a source keeps its place with
"(slow)" after its label, `SLOW`, and the Start question says why, `slow_note`: the user's word of 2026-11-18)
plus the settings' `extra` (one of a part's name replaces the
part), grouped Continent → Country → area (`Group`, a `Collapsible`, per
continent holding one per country of two or more rows, with rows of `Checkbox` subclasses: a `DataTable`'s first click
only moves its cursor, a `SelectionList` has no cell to click for the target). A country of one row (after `PARENTS`
and the extra rows) has no group: its row sits in the continent by its title, in the countries' order, so nothing moves
when it gains a second row (`SINGLE_ROW_COUNTRY_LEVEL`, False by the user's word of 2026-11-15). `Row.country` is
`COUNTRIES`' name after `PARENTS` (a territory under its country: Saint-Barthélemy, Saint-Martin,
Saint-Pierre-et-Miquelon under France, Puerto Rico and the US Virgin Islands under the United States, Åland under
Finland; an empty table gives each code its own country). A row's continent is where it lies (the user's word of
2026-11-15): its own outline's, else `REGION_CONTINENTS` (Guadeloupe, Martinique and the Caribbean Netherlands in North
America, French Guiana in South America, Réunion and Mayotte in Africa, Tokyo and Shizuoka in Asia), else its
country's; so a country may have a group under two continents
(`group-europe-france`, `group-north-america-france`). `Row.label` is what a row in a
country's group shows (the region's or territory's name, a country-wide row "Whole country · <source>"); the title and
name stay the full ones. An extra row's country is its `"country"`, else its title's part before ": " when that is a
known name, else its title (a territory's name through `PARENTS`); continents, and countries within one, whose names
slug alike are one (`_one_spelling`: the group ids are slugs). Sorted by `CONTINENTS`, country, the country-wide row first, label. Each group's title
carries its count and ticked count; at start the continents open and a country's group only when one of its rows has a
state (`FOLD_AT_START`); the filter matches title and country, opens the groups with a match, hides the others and
gives the folds back when cleared; up and down walk the visible titles and boxes. A checkbox
only chooses; Start and Stop ask first (`Confirm`, the focus on Cancel). A finished row can be ticked and
started again (the user's word of 2026-11-18; its box was disabled before): the question says "again"
(`start_word`) and that only what is missing or new is downloaded, which is how a row gets a layer or a
stand-in its source gained after it was done. A row's name is its name in the state folder
(`slug` of the title: `poland`, `czechia`, as the downloads started by hand). The settings (a JSON file outside the
repository: the docstring of `area_rows.py`) name the state folder, a contact (`FINDALINE_CONTACT` of what starts,
never on a command line; an e-mail address with a dotted domain or an http(s) address, `contact_ok`, else a
`SettingsError`), the targets (`data_dir`, `min_free_gb`, `max_memory_gb`, `tiles`: the folder on a share) and rows'
targets, `host_slots` and `max_memory_gb` (the row's over the target's, as `--max-memory-gb` of `command_of`; neither:
the downloader's default); the target chosen in the window is kept in `tui-targets.json` of the state folder. Start:
`links_of` (a share's tile folders, `Layer.folder`, as links from the data folder's cache; a real folder with tiles
stops that row; the folders of the source's stand-in by the same rule, `link_folders`: a download fetches the stand-in as well, `usa/3dep-13/live` for a state, `usa/ifsar-5m` for Alaska, and a stand-in's folder left on this disk would keep every later row of the source there; a row whose stand-in's link could not be made is not started either), `make_links` (LAYOUT first, or a new cache with links in it is refused as another layout;
`os.symlink`, else one UAC window on Windows without Developer Mode: `_elevated`, a script with its BOM for PowerShell
5.1), then `start`: `area_download.py run` detached (`_detached`: a hidden console of its own on Windows, a new
session on Linux, so it outlives the window and its terminal); a row of a source with parts (`usa`, `canada`: the
states, the country-wide row, Puerto Rico, the US Virgin Islands and an extra of that source) in the queue of its
source (`command_of`: `--queue <source>`; a row whose turn has not come shows "queued"), the rows of every other
source at once as before (Finland and Åland, one source, still start together). State from the state folder (`ad.areas`), as `status`.
Everything has a key (a text console has no mouse); `tests/test_area_rows.py`, `tests/test_area_download_tui.py`

## `tools/job_stats.py`

Run by hand (also on the VPS host with its `python3`: standard library only): where the computing time of the finished
searches goes, read-only from a `jobs.sqlite` (`--immutable` for a copy): by model, resolution, longest line,
circle/area and goal of the form (its copy of `params.PRESETS`; the three presets before the goals as "typical (old)",
"long (old)", "short (old)" for the searches made with them), the computing seconds (sum, median, p90), seconds and CPU seconds per step and per stage, the
funnel's ratios; `--phases`: the seconds between a job's timestamps (the waits for a download and a compute slot, the
phases), the computing seconds outside its steps, the steps `orthophoto` and `other`, and the tiles of an area
(number, the largest one's Mpx) from its "--- Tile k of N" lines; jobs from before migration 16 from their info
events; no ids, titles or places; `tests/test_job_stats.py`

## `tools/test_lock.py`, `tools/test_lock_page.py`

The test lock of parallel sessions and agents:
`run [--exclusive | --heavy] [--memory GB] [--resource NAME] [--first] -- <command>` waits in one
first-come-first-served queue (SQLite in `<git common dir>/findaline-locks/`, an OS lock per entry, so a killed
wrapper leaves nothing behind; `PRAGMA user_version` 1: the kinds of `uv run --frozen ...` with uv's own options
skipped, 2: full pytest runs with -n of kind `pytest-all-xdist`, older rows migrated each time (`_migrate`); a new table by `SCHEMA`'s `CREATE TABLE IF NOT EXISTS`, a new column of `entries` by the
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
agent runs neither for real: the user installs it); a full pytest in parallel processes (pytest-xdist): a command
of kind `pytest-all` gets `-n MODE_WORKERS[mode] --dist loadfile` after the word pytest when it is queued
(`parallel_command`; 6 workers shared, 8 heavy and exclusive), unless it names its own `-n`/`--numprocesses`/
`--dist`/`--tx`/`--maxprocesses` or `-p no:xdist` (`-n 0`: a serial full run), gives one of `SERIAL_ONLY` (--pdb,
--trace, -s, --collect-only, --looponfail, --stepwise) or its Python has no xdist (`xdist_available`: a probe import;
a line says it runs serially); kind `pytest-all-xdist` (`PARALLEL_KIND`, `pytest_workers`), so its estimates and
peaks stay apart; `WORKER_THREADS` 3 threads a worker (`_environment(workers=)`; tamed: `tamed_workers`, at most
`HEAVY_TAMED_THREADS` in all, the entry's command rewritten, `Queue.set_command`); a shared one counts
`slot_weight` = ceil(workers / `WORKERS_PER_SLOT` 2) slots and, waiting for them, keeps them reserved in `startable`
(a later shared one passes it only by the backfill rule, so it is never starved); with no history its peak is
`MEMORY_BASE_GB` 6.0 + `MEMORY_PER_WORKER_GB` 0.65 a worker; `status` adds "6 workers x 3 threads, 3 slots"
(`_parallel_text`); `tests/test_test_lock.py`, `tests/test_test_lock_parallel.py`, `tests/test_test_lock_page.py`

## `tools/test_times.py`

Run by hand: where a pytest run's time goes, from its JUnit files (`show`: seconds per file and per test with shares,
the counts at ≥ 1/5/10/30 s), two runs compared id by id (`compare A B`: ids in one only, outcomes that differ,
seconds per file side by side; exit 1 on a difference; a serial and a pytest-xdist run write the same ids), and setup
/ call / teardown from pytest's `--durations` lines (`durations LOG`); standard library only;
`tests/test_test_times.py`

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
