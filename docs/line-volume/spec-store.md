# Line volume: stored and sent (specification, part 2 of 3)

2026-11-14. One of the four files of `docs/line-volume/`; how to read them, the sources and the reference cases:
[spec.md](spec.md). Code: `file:function` after phase 4. `stands_for`: the square rule's count per kept line (the
found lines it stands for, itself included; the last column of `lines.csv`); `summary.found` in `run.json`: their sum.
Sections: 1 the store (its waves cover the whole part), 2 old runs, 3 the ranges of a kept line, 4 what is sent,
5 renaming a run, 6 the goal case, 7 contradictions, 8 the user's word (U1-U12, elsewhere cited as "store U1" …).
The user's closing answers of 2026-11-14 settle U1 (six ranges), U4 (exports per download), U5 (old runs removed)
and U12 (brotli); the choices of class "planner" are taken as recommended (section 8).
**State on 2026-11-18:** waves 1 to 3 are built (`main` 31f16de, 47c5fa7, ef93df5; wave 3 f2f8015), share links
and runs outside the page's list read the store (b757bee), and wave 4's first deploy is built and on the server
(1b1f2f15, a0c511ac, a86b86e8: new runs keep no text files, `findaline.py view`, `runs remove-old`, the disk notice);
old runs were removed on the PC and on the server on the user's word (2026-11-18, section 2 "As run"); "as built"
notes stand in 1.2, 1.3, 1.4, 1.8, 1.9, 1.10 and 2. Wave 4's second deploy followed in `main` once both hosts were
cleared (1.9 "Built (round 5)"): the page reads a run from its store alone, and nothing writes or reads `data.js` or
`lines.js`; on the server on the user's word. Open: waves 6, 7, 8.
**State on 2026-11-25 (round 7):** wave 8 (renaming a run) is built, section 5 "As built in round 7"; wave 6 was
reduced by the user to the run's size on Home's card, section 4 "As built in round 7" (no brotli, no immutable
cache); wave 7 (the ranges): its server half was built on a branch, accepted, and not taken: section 3 "Not
taken". Nothing of this part is open.

## 1. One store of a run's lines, columns in the page, text files on request

### 1.1 Decision
G-06 a, "Arrow store, columns in the page, text files on request" (gate 3; structural), on top of gate 2's D-04 a
'The files a run keeps' ("Only the binary store; the rest on request": every run opens through the app, the command
line gets `view`, opening by double-click ends) and D-05 c 'Large runs in the browser', its condition met by part P5
(F-21 'Data and grouping in a Web Worker', F-20 'Grouping core first, details later', F-13 'Keep opened runs in the
browser' parked at gate 3). The user (2026-11-11): "We are droping saving text files", "I'm thinking about dropping
file:// opening", "If binary table is used also on client side, than it is no longer needed"; (2026-11-10):
"10-20MB sounds good as a target" (bytes sent before a run is usable).

### 1.2 Behaviour
- **One copy.** Every new run (command line, local app, public site) keeps its lines once: `lines.arrow` (a row per
  line) and `profiles.arrow` (a row per saved profile).
- **Opening.** The page downloads both files together (`download.ts`, XHR `arraybuffer`, today's progress bar and
  `SIZE_HEADER`), reads them with apache-arrow into typed arrays without copying, and keeps the lines as columns.
  A `Line` object is made only for a line that is drawn, listed, selected or saved as a favourite (F-19 'Lines as
  typed-array columns in the page'). Filters and grouping read the columns. Nothing loads in stages (F-20 parked).
  Later, on demand, only what is on demand today: `/api/profile` for a line without a saved profile, the 3D view,
  and the exports below.
- **Old runs** open through the same columns until wave 4: the page parses `data.js` into columns and drops the rows
  (wave 1). Wave 4 removes them on the user's word and the page's reader of `data.js` goes with them (section 2).
- **The files of a run** after all waves:

| File | Command line | Local app | Public site |
|---|---|---|---|
| `lines.arrow`, `profiles.arrow` | written | written | written |
| `lines.arrow.br`, `profiles.arrow.br` (section 4) | no | no | written by the worker |
| `run.json` (+ the block `store`, below) | written | written | written (never served) |
| `map.html` (the entry page, also of share links) | written | written | written |
| `ATTRIBUTION.txt` | written | written | written |
| `data.js`, `lines.js` | gone | gone | gone |
| `lines.csv`, `lines.geojson` | made by `export` where `--out` says, never in the run folder | made per download, not kept | made per download, not kept |
| `runs/runs.js` | written as today | written as today (Compare, thumbnails) | not written (generated per user) |
| `runs/index.html`, the data folder's `findaline_map.html` | gone | gone | not written today |

- **From disk** (`file://`) `map.html` loads no data and shows "This map opens through Find-a-Line. Run: findaline.py
  view <run id>"; over http the viewer removes that paragraph.
- **`findaline.py view [RUN]`** starts the local app on the data folder as `findaline.py web` does (port 8765; when
  the app already answers there, it is used) and opens the browser at `/#run=<id>` (the app's result route,
  `app/c/ResultPage.tsx`). RUN: a run id, a run folder, or nothing for the latest run. A search ends by printing
  `View it: findaline.py view <id>` instead of the two paths it prints today (`findaline.py:main`).
- **`findaline.py export RUN --format csv|geojson [--out PATH]`** writes the text from the store, byte for byte what
  `runs.save_results` writes today (default `--out`: `<run id>.csv` / `<run id>.geojson` in the current folder;
  nothing is written into the run folder, so no run keeps an export: U4).
- **In the app**, "Download CSV" and "Download GeoJSON" (`RunActions.tsx`) ask the worker for the file (quick lane,
  kind `export`) and show "Preparing the file…". The worker writes it into `work/exports/` under a random name; the
  browser downloads it once from the route of 1.4, which deletes it after sending. **An export is made for each
  download and none is kept** (U4, the user, 2026-11-14: "5. c)"): a second download makes it again.
  **As the accepted mock-up shows it** (version 1; the user, 2026-11-16): "Preparing the file…" stands in the pressed
  row, the menu stays open and a turning ring replaces the row's icon; with the menu closed the ring sits on the
  Download button; the other row is off meanwhile; when the file is ready the download starts and nothing else is
  said. A failure is a small red line in the menu under the two rows, and the rows work again at once. A share
  link's page has no Download for a run with a store, and neither has a demo run's page for a visitor who is not
  signed in (U9). A run without a store keeps today's links to its kept files until wave 4 removes such runs.
  **As built** (f2f8015): Download shows where the page can send changes and the run was read from its store
  (`mayExport` in `RunActions.tsx`, `RunData.fromStore`): the app's result page. A run's own `map.html` holds no
  token, so it has no Download for a run with a store either (the user, 2026-11-17: "1.a"). The wait is kept per run
  outside the menu: it survives the layout's switch at 768 px and a change of run. A failure that comes while another
  menu is open shows at the menu's next opening.
- **Limits.** Unchanged (public 1.5 M lines). No string limit in the page: none found on a desktop up to 10 M lines
  (part P5); a phone's is unknown until the real-device test. No "off". Old runs open as today until wave 4, which
  removes them (section 2).

### 1.3 Data
`lines.arrow`: an Arrow IPC **file** (not stream), uncompressed, **one record batch** (so each column is one typed
array, the form part P5 measured), rows in the search's table order (as `data.js` today; `lines.csv` keeps its grouped
order through the export; the result view's order is the column `by_spot`, so no export depends on it). Integer
columns hold `value × 10^decimals` in the narrowest of int8/16/32/64 that holds the run's values; the field's metadata
`decimals` gives the scale, so the reader needs no table of its own. The decimals are those `mapping.map_rows` prints
today, which equal or exceed those of `lines.csv` (part P5: CSV identical from the store on BAH and MG5).
This is the one schema of a run's lines: every column the result view reads (`spec-view.md` B.3) is here, with the
wave that adds it (waves: 1.9; "view B1" is the first wave of the result view, `spec-view.md` B.9).

| Column | Type | Unit (decimals) | Missing value | From | Wave |
|---|---|---|---|---|---|
| `lat1`, `lon1`, `lat2`, `lon2` | int32 | degree (7) | never | `LineTable` `anchor1`, `anchor2` | 2 |
| `x1`, `y1`, `x2`, `y2` | float64 | m in the grid CRS, unrounded | never | `a1_xy`, `a2_xy` | 2 |
| `len`, `clr`, `hmax` | float64 | m, unrounded (grouping values) | NaN as today | `length`, `clearance`, `height_max` | 2 |
| `clrN` | int (narrowest) | m (2) | null (validity bit): no surface model there | `clearance_nmpt` | 2 |
| `e1`, `e2` | int | m (2) | never | `elev_a1`, `elev_a2` | 2 |
| `over` | uint8 | 0 / 1 | never | `over_obstacles` | 2 |
| `water`, `filled` | int | m (1) | never | `water_m`, `filled_m` | 2 |
| `hmean`, `highPct` | int | m (2), % (1) | null when NaN | `height_mean`, `high_pct` | 2 |
| `angle1`, `angle2` | int | degree (1) | null when NaN | `angle1`, `angle2` | 2 |
| `prom1`, `prom2`, `drop1`, `drop2` | int | m (1) | null: not known | the same | 2 |
| `lift_needed`, `lift_no_zone` | int | m (2) | column absent without zone and A-frames | `END_VALUES` | 2 |
| `stands_for` | uint32 | found lines | column absent with the square rule off | `samelines.COLUMN` (int64 in `LineTable`) | 2 |
| `access1`, `access2` | uint8 ("mark": read with scale 1) | 0 hard access / 1 cannot tell / 2 easy access | column absent without `--access`, and when the mark was left out (the head's `access_skipped`) | `spec-search.md` 3.3 | built with the access mark (53fe802) |
| `spot` | uint32 | spot number from 0 | never (every line has a spot) | `mapping.group_lines` at the run's distance, renumbered | view B1 |
| `top` | uint8 | 0 / 1: the top-level flag | never | the rule of `spec-view.md` B.3 | view B1 |
| `by_spot` | uint32 | a row index | never | the view's order (below) | view B1 |
| ranges (section 3) | float32 pairs | as the value | absent with the square rule off | section 3 | 7 |

- **Spots, sectors and the view's order** (view B1, computed in Python at saving: once, the same on every number of
  threads). Spots are numbered from 0 in the order of their sectors, inside a sector by their first line's mean
  height, highest first; a spot's label is "<sector>.<k>", k = its number less the first number of its sector, plus
  one. `by_spot` lists the rows by `spot`, inside a spot by mean height, clearance, length (each highest first), then
  the row; a spot's lines are a run of `by_spot`, found by one pass in the page. Derived in the page, not stored: `dh`
  (`e2 − e1`) and `need` (0: `lift_no_zone` 0; 1: `lift_needed` 0; 2: else). About 9 B a line (estimate).
- **Schema metadata** `findaline` (JSON): `{"format": 1, "head": …, "negative_zero": {column: [rows]}}`. `head` is
  today's `data.js` head (`mapping.map_heads`: run, center, area, crs, ortho, attribution, distance, by, model,
  rigging, slope, leash_fall, end_zone/lift/ends, high_above, max_zoom, terrain, shore, terrain_sources, and since
  phase 4 `square` and `found` for a run made with the square rule) without `lines`; from view B1 also `sectors`
  (`[{"word": "north-west", "spots": 812}, …]` in sector order), `box` (the lines' extent in the grid CRS, m) and
  `lengths` ([shortest, longest], m). `negative_zero` lists the rows whose integer column was a negative value that
  rounds to zero ("-0.0" in the text): without it BAH's `lines.csv` differs in 8 rows of `clearance_nmpt` (part P5).
  A reader refuses a higher `format` ("made by a newer Find-a-Line").
- **`profiles.arrow`**: one row per line with a saved profile: `row` uint32 (index into `lines.arrow`); `d`, `z`, `s`
  list<float64> (`s` absent without a surface model; NaN where today's JSON has null); `w`, `g` list<uint8>, null
  when absent; `min`, `min_nmpt`, `max_height` fixed_size_list<float64, 2> (`min_nmpt` nullable); `water_m`,
  `filled_m` float64; `zone`, `lift` float64, null when absent (`helpers.Profiles` and `types.ts` `Profile`).
- **`run.json`** gains `"store": {"format": 1, "lines": <rows>, "bytes": <lines.arrow + profiles.arrow>, "sha256":
  <of lines.arrow, first 16 hex>}`; the sha256 versions the URL (section 4).
- **Bytes** (part P5): 105-107 B a line on BAH and MG5, 158 on MG0 (more profiles per line); MG5 327.2 MB against
  713.6 MB of `data.js`. `stands_for` adds 4 B (estimate), the view's columns about 9 B. As built (round 3,
  `docs/performance.md` "From the store"): BAH in the target rig 207.8 MB (`lines.arrow` + `profiles.arrow`)
  against 448.8 MB of `data.js`; gzipped at nginx's level 5, 89.5 MB against 143.9 MB.
- **As built, beyond the table (wave 2, round 3):**
  - A scaled column whose values no integer type holds exactly (beyond int64 after scaling, an infinity, a NaN in a
    column that "never" misses) is written as float64 without the `decimals` metadata, holding the values rounded
    as `data.js` shows them; a count beyond uint32 as uint64. The reader takes either form and the export stays
    byte-equal to `lines.csv`. The store so never costs a run.
  - The store is written after today's text files, under temporary names (`lines.arrow.part`,
    `profiles.arrow.part`) renamed only when both are whole; `run.json` is rewritten whole too. If the store still
    fails, the run is kept without one: no `store` block, a warning logged and printed (not a coded message yet),
    and the page reads its `data.js` as for an old run.
  - `web.RUN_FILES` is one list for `/runs` and `/s`: a share link, an administrator and a demo run's visitors are
    sent the store as they are sent `data.js` (1.7's "to the owner only" means "not to other users").
- **Stored data:** waves 1-3 and view B1 "none" (new files and columns; old runs open as they are; jobs.sqlite,
  favourites, share links unchanged). Wave 4 "none" for the format, and old runs are **removed, not migrated** (U5,
  section 2): the removal is a command run on the user's word, and that wave's commit message says so. Favourites of
  new runs: an int32 of 1e-7 degree divided by 1e7 is the same double as today's parsed 7-decimal text, so
  `keys.lineCoords` gives the same key from the store as from `data.js` (a test asserts it). `file://` ends with
  wave 4.

### 1.4 Interfaces
- **Command line:** `findaline.py view [RUN]`, `findaline.py export RUN --format csv|geojson [--out PATH]`;
  `--no-html` skips `map.html` only (the store is always written); `--html` (the path of `findaline_map.html`): U10.
  No new `SearchParams` field; the search hash and `run.json`'s params do not change.
- **Routes:** `POST /api/runs/{run}/export` with `{"format": "csv"|"geojson"}`; access `run_access` (owner,
  administrator, demo run); queued in the quick lane as kind `export`, waited for as `web.quick` waits (at most
  `QUICK_WAIT_MAX`); the worker writes `work/exports/<run id>-<token>.<csv|geojson>` (token: 16 random bytes,
  URL-safe) and answers `{"url": "/api/runs/<id>/export/<token>.<ext>"}`; 503 without a worker; audit event
  `run_export` on the public site; who may export and how often: U9 (the owner, an administrator, a demo run's
  visitors; not share links). `GET /api/runs/{run}/export/{name}` (access `run_access`) sends the file with
  `Content-Disposition: attachment; filename="<run name>.<ext>"` and deletes it when sent; the worker deletes
  files of `work/exports/` older than one hour at its start and before each export (a download never fetched).
  `web.RUN_FILES` gains `lines.arrow`, `profiles.arrow`; `web.SIZED_FILES` gains both (the decoded size in
  `X-Findaline-Bytes`). Media type `application/vnd.apache.arrow.file` for both (also `mimetypes` locally).
- **As built** (wave 3, f2f8015): the worker's kind is `jobs.quick_export`. The file is sent once and deleted, also
  when the client breaks off (`web.SentOnce`); a Range request gets the whole file and HEAD answers 405; the file's
  name is the run's name, else its id; a run without a store answers 409 `export_failed`. Before it writes, the
  worker estimates the file's size from the store's lines (`jobs.EXPORT_LINE_BYTES`: 250 B a line of CSV, 1 000 of
  GeoJSON; measured 193-198 and 881-890) and refuses with `export_disk_full` when the disk would fall under
  `free_disk_gb_min`. The worker sweeps `work/exports/` at its start, before each export, every 60 s in its loop and
  first in its housekeeping, so a file is gone 3 540.5 s after it was made at the latest (`jobs.export_sweep_age`),
  and a file older than the hour is never sent: "for one hour at most" holds. The rate is the setting `export_rate`
  (429 `rate_export`). The audit event `run_export` (the format only) is recorded only for an export that was made.
- **Files of a run:** the table of 1.2. An export never counts in the `runs` row's `bytes` (none is kept).
- **Texts** (`locales/en.json`, plain words): `ui.result.export_preparing` "Preparing the file…";
  `error.export_failed` "The file could not be made. Try again in a moment."; `map.html`'s paragraph "This map opens
  through Find-a-Line. Run: findaline.py view {run}" (in the HTML, so it shows without the bundle).
  With the mock-up (the user, 2026-11-16: "looks good do as recomended"), for the cases where the file is refused:
  no worker on the public site "The file cannot be made now: the search service does not run. Try again later.";
  in the local app "The file cannot be made now: the search service does not run. Start it with: findaline.py
  worker"; another request of the same user still waits "Your last estimate, profile, place search or file is not
  finished. Try again when it is done." (today's text with "or file"); the disk is short "The server is short of
  disk space. The file cannot be made now. Try again later."; the site is busy: today's text. The screen reader's
  label of the button while it waits: "Download: preparing the file". Over the exports' limit (U9; the setting
  `export_rate`, on the public site 4 a minute and 30 an hour): "Too many downloads in a short time. Wait a minute
  and try again." The privacy page (the user, 2026-11-16: "Yes, both as written"): its audit list gains "exports of
  a run's lines made (CSV or GeoJSON: the format, not the content)," and it says "A file made for a download is
  kept on the server until it is fetched, for one hour at most."

### 1.5 Files and pairs
- **New `linestore.py`** (numpy and pyarrow only): `write(run_path, lines, head)` (a `LineTable`, its profiles and,
  from view B1, the view's columns), `read(run_path) -> (LineTable, head)`, `export(run_path, fmt, out)`
  (`mapping.group_lines`, then `runs.save_results(files=…)`: numba, so exports run in the worker or the command line;
  the web process needs no pyarrow). Precompression `write_br` (section 4).
- **Python:** `search.save_run` (the store instead of the scripts and text files); `saving.py` (text files only, kept
  for exports of more than 100 000 lines if wave 3's timing asks for it); `mapping.save_map` (map.html only),
  `mapping.map_heads` (the head, into the store); `runs.list_runs` (`has_lines`: `lines.arrow`, or `lines.js` until
  wave 4), `runs.write_index` (no `index.html`); `findaline.py` (`view`, `export`, `runs remove-old`, the last
  lines); `jobs.py` (quick kind `export`, the clean-up of `work/exports/`); `web.py` (`RUN_FILES`, `SIZED_FILES`, the
  two export routes, section 4); `pyproject.toml`, `uv.lock`.
- **Viewer:** `types.ts` (the columns, `toLine` from columns), `result/load.ts` (the store reader; `data.js` filling
  columns until wave 4, then gone; no script-tag fallback over http), `result/model.ts`, `filters.ts`,
  `grouping.ts`, `others.ts` and `app/c/Thumb.tsx` (Compare, thumbnails), `RunActions.tsx`, `package.json` (apache-arrow 21.2.0, Apache-2.0, 50 KB
  gzip, part P5), `viewer/dist` with `THIRD-PARTY-LICENSES.txt`.
- **Tests, tools, docs:** `tests/regression.py`, `test_units.py`, `test_offline.py`, `test_viewer.py`, `test_web.py`,
  `test_public.py`, `test_shell_c.py`; `tools/ui_shots.py`, `perf_run_load.py`, `device_page.py`, `perf_reach.py`,
  `perf_country.py` read through `linestore.read`; README, `setup-for-regular-folk.md`, `docs/regression-tests.md`,
  `docs/code-map/`, `CLAUDE.md` and `docs/roadmap.md` (their `file://` promises and decisions).
- **Pairs, by the rules' words:** `run-files.md` "Values used for grouping are passed to the viewer unrounded":
  holds (float64, same row order). "The run data written by mapping.save_map (data.js, lines.js …) … and their types
  in viewer/src/types.ts": becomes the store's schema ↔ the reader (`types.ts`, `load.ts`). "The text of lines.csv,
  lines.geojson … built column by column (runs._rows …)": the same code, run by the export
  (`test_saved_text_as_before` stays). "the head's `ends` … `END_VALUES`": named columns; `END_FIELDS` =
  `END_VALUES` = `types.ts` still pinned, and `stands_for` (`runs.STANDS_FOR` = `types.ts` `STANDS_FOR`) a named
  column. Terrain, shore, `terrain_sources`: into the store's head. "a change of how mapping.save_map rounds the
  anchors loses everyone's favourites": kept (1.3). `web-app.md` "`web.RUN_FILES` … and what mapping.save_map and
  runs.save_results write", "`web.SIZED_FILES` carry `web.SIZE_HEADER`", "Heavy work and network only in the worker"
  (exports), "Every endpoint checks who asks", "records an `audit` event" (`run_export`). `viewer.md` "The viewer
  works from `file://`: no `fetch` … a download with progress is an XMLHttpRequest": the first half ends, the XHR
  stays; "THIRD-PARTY-LICENSES": changes with apache-arrow. `search.CIRCLE_PROFILES_BYTES` exists only for disk maps
  (part P5): U6.

### 1.6 Screens
The Download buttons: the mock-up of round 4, version 1, accepted (the user, 2026-11-16: "The Download buttons'
mock-up, version 1 - looks good do as recomended"). `map.html`'s disk notice, the size on Home's cards and the
warning before a heavy run (section 4) get a small mock-up first.
### 1.7 Tests
- `test_store_round_trip` (unit): the Żabi Koń clip and 50 000 synthetic lines with the hard floats of
  `test_saved_text_as_before` (halfway cases, NaN, nulls, -0.0 in every integer column, both end columns,
  `stands_for`): `linestore.write` then `export` gives the bytes `runs.save_results` writes from the `LineTable`
  itself, for CSV and GeoJSON; the profiles read back equal `helpers.Profiles`' dicts.
- `test_store_schema`: types, decimals and nulls as 1.3; a reader refuses `format` 2. `test_viewer.py`: the clip's
  store and its `data.js` give equal `Line` values and `keys.lineCoords`; grouping equals Python's.
  `test_public.py`: the store to the owner only, `X-Findaline-Bytes`, the export route's access rule, audit event,
  503 without a worker. `test_web.py`: the disk page shows the notice and loads nothing (replaces
  `test_run_map_from_disk`); `view` opens `/#run=<id>`.
- **Regression, with exports per download** (the user asked, 2026-11-14: "how does it work with regressions?").
  The regression set never reads a kept export, since none exists. `tests/regression.py` `measure` takes the sha256
  of the CSV text that `linestore.export` makes from the run's store into memory (or a scratch file), which is the
  same bytes as today's `lines.csv`, so **every checksum in `tests/regression.json` stays as it is** (R65, the
  square rule's entry, included). From wave 2 until wave 4 every run still writes its `lines.csv` too: on every
  regression entry `measure` then also checks that the export equals that `lines.csv` byte for byte, so a slip of
  the store (decimals, `negative_zero`) shows before wave 4 ends the text files. `check_map`: store rows = CSV rows;
  profiles one per spot, or every line for a circle with `summary.profiles` "all"; the `lines.js` check goes.
  `same_as` compares exported texts. `--browser` opens the run through the local app over http.

### 1.8 Acceptance (targets of gate 1; measured with `tools/perf_run_load.py` and the page's `fal:run:*` marks,
exclusive mode only when the user says the PC is free)
| Target | Today | Must meet | Reference case |
|---|---|---|---|
| T3 folder of a run within the public limits ≤ 300 MB | about 2.3 GB at 1.5 M lines (part E1, estimate) | store + br copy ≤ 300 MB | BAH (part P5: store 99.6 MB) and a 1.5 M cut (estimate 160 MB + about 55 MB br) |
| T4 bytes sent before usable, 10-20 MB | 3.1-249 MB gzip (part E2) | ≤ 20 MB | GZ1 with the square rule (section 6) |
| T5 first picture ≤ 3 s, heap < 500 MB, never a crash | BAH 5.0 s, 754 MB heap; crash at 2.3 M (part E2) | ≤ 3 s, < 500 MB at BAH; no crash at MG5 | BAH, MG5 (desktop Chromium) |
| T6 filter or grouping change ≤ 0.3 s | BAH 1.0 s; 2.29 M 3.5 s (part E2) | ≤ 0.3 s at BAH | BAH |
| T8 saving's share ≤ 20 % | 40-55 % (part E6) | ≤ 20 % | BAH (store 0.14 s against 4.3-5.5 s per text file, part P5) |
| T10 goal case opens on a desktop | not measured since phase 4 (`data.js` 137 MB) | opens | GZ1 with the square rule (section 6) |

T5 and T6 depend on grouping and drawing from columns (not measured in part P5): wave 1 measures them, then reports.

**T5's heap, defined** (the user, 2026-11-15: "a"): the peak after loading, read two frames after the first picture
(`usedJSHeapSize`, which counts the typed arrays' backing stores); the page's own `gc()` reading and the reading
after a full collection are reported beside it.
**Measured after wave 2** (round 3; one exclusive pass, desktop Chromium over loopback, three rounds;
`docs/performance.md` "From the store"; BAH in the target rig):

| Target | From `data.js` (wave 1) | From the store (wave 2) | Verdict |
|---|---|---|---|
| T5 heap < 500 MB at BAH | 1 732-1 733 MB | 447-474 MB (236 MB after a full collection) | met |
| T5 first picture ≤ 3 s at BAH | 5.91-6.49 s | 3.06-3.37 s (download 0.64 s, the grouping 1.78 s) | not met, by a little |
| T5 never a crash | a 2.5 M cut: "This result is too large for this browser." | the 2.5 M cut opens (4.25-4.55 s) | met on the desktop |
| T6 filter / grouping change ≤ 0.3 s at BAH | 1.13-1.22 s / 1.52-1.60 s | 1.16-1.19 s / 1.54 s | not met, unchanged |

What is left of T5's seconds and all of T6 is the greedy grouping: view B1's stored spots and `by_spot`
(`spec-view.md` B.3, B.9) take it out of the load and of a filter change. The iPhone was measured only as a WebKit
profile on Windows (the 2.5 M cut showed after 10.6 s there), never on a device.

### 1.9 Waves (of the whole part; each wave ships alone and leaves every regression checksum as it is)
| Wave | What | Agents and the files each owns | After | Effort |
|---|---|---|---|---|
| 1 | Columns in the page from today's `data.js` (F-19, first, as the user asked); an empty body over http shows "This result is too large for this browser" instead of the script-tag fallback that crashes (part E2); measures T5/T6 on BAH and a 2.29 M cut and reports | A: `types.ts`, `result/load.ts`, `result/model.ts`, `filters.ts`, `grouping.ts`, `list.ts`, `result/view/*`, `favourites.ts`, `test_viewer.py`, `test_shell_c.py`, `viewer/dist` | – | high |
| 2 | The store written beside today's files; the page prefers it | B (Python): `linestore.py`, `search.save_run`, `mapping.map_heads`, `runs.list_runs`, `web.RUN_FILES`/`SIZED_FILES`, `pyproject.toml`, `uv.lock`, the unit and public tests, `regression.py` (export = `lines.csv`); C (page): the store reader in `load.ts`, `package.json`, `viewer/dist` | B: –, in parallel with 1; C: 1 | medium each |
| 3 | Exports per download, none kept; regression's checksum from the export | D: `jobs.py` (kind `export`, the clean-up), `web.py` (the two routes), `RunActions.tsx`, `findaline.py export`, `locales/en.json`, `regression.py`, tests | 2 | medium |
| 4 | Text files and `file://` end; `view`; Compare and thumbnails from the store; the reader of `data.js` goes; old runs removed on the user's word (section 2) | E: `search.save_run`, `saving.py`, `mapping.save_map`, `runs.write_index`, `findaline.py` (`view`, `runs remove-old`), `docs/deployment.md`, tools, README, setup guide, CLAUDE.md, rules, `docs/`; F: `result/load.ts`, `others.ts`, `Thumb.tsx`, the disk notice, `test_web.py` | 3 and view B1 | high |
| 5 | – (was: old runs converted; the user chose removal, which is a step of wave 4) | – | – | – |
| 6 | What is sent (section 4), brotli at saving | H: `web.RunFiles`, `web.cache_control`, `linestore.write_br`, `pyproject.toml`, `uv.lock` (no entry for brotli: pyarrow's own codec, section 4), `deploy/nginx/findaline.conf`, `tests/nginx_check.sh`, `docs/deployment.md`, Home's size and the warning (after their mock-up) | 2 | medium |
| 7 | The ranges of six values of a kept line (section 3) | I: `samelines.py`, `linestore.py`, `filters.ts`, `LineDetails.tsx`, tests | 2 | medium |
| 8 | Renaming a run (section 5) | J: `web.py`, `runs.py`, `RunActions.tsx` or Home, tests | – (simplest after 4) | low |

**Built (round 3):** wave 1 (`main` 31f16de) and wave 2 (47c5fa7 the Python half, ef93df5 the page's reader). Wave
2 took three things early: Compare reads a run with a store from its store (`RunActions.tsx`; the wave table puts
"Compare and thumbnails from the store" in wave 4: thumbnails are still to do); `runs.list_runs`' `has_lines` is
"`lines.arrow` or `lines.js`"; and `application/vnd.apache.arrow.file` joined nginx's `gzip_types` (section 4 has
it in wave 6), so the public site sends the store gzipped until wave 6 sends brotli.

**Built (round 4):** wave 3 (`main` f2f8015: the command `export`, the quick kind, the two routes, the rate, the
Download buttons) and, before it, the store read by share links and by runs outside the page's list (b757bee: 1.10),
which wave 4 waited for. View B1 is built too (39785f8), so wave 4 can be built now; only its removal of old runs
needs the user's word on each host (section 2).

**Built (round 5):** wave 4's first deploy (`main` 1b1f2f15 the tools, a0c511ac the Python side, a86b86e8 the page;
tags `history/store-wave4-tools`, `history/store-wave4`, `history/store-wave4-page`; pushed and deployed
2026-11-18). A new run writes `lines.arrow`, `profiles.arrow`, `ATTRIBUTION.txt`, `map.html` (not with `--no-html`)
and `run.json` last and whole, nothing else; `saving.py` is gone. A store that cannot be written ends the search with
`run_not_saved` and no folder (a tiled run keeps its work state); view columns that fail leave a store without them,
the note `view_columns_failed` and `view_columns_failed` in run.json, and such a run is current (the planner's
correction of 2026-11-17: never removed). `findaline.py view` (A1, A2 of the round's plan), the disk notice (the
user's accepted preview, "2. a"), Home's mini maps from `lines.arrow`, and the nine tools of `tools/` reading the
store (old runs from their files) are in; section 2 has the removal as built and as run.
Wave 4's second deploy (item 5, after the removal on both hosts): the page reads a run only from its store over
http(s) (`result/load.ts`, keyed on the run's folder; a store that cannot be fetched or read shows
`ui.result.store_failed`, "This result could not be loaded. Reload the page to try again.", the user's "b" of
2026-11-18, with the reason in the console); `mapping.save_map` writes `map.html` alone, `web.RUN_FILES` is `map.html`,
`ATTRIBUTION.txt` and the two store files, `has_lines` means `lines.arrow`. From disk every `map.html` shows the disk
notice, one written before wave 4 too (the viewer builds it: the run's id from its folder, its name from `runs.js` or
the page's title). The old writers of `data.js` and `lines.js` live on, frozen, in `tests/old_scripts.py` for the
tools' tests of old runs; `index.css` (of the removed `runs/index.html`) is gone.

The view's columns (`spot`, `top`, `by_spot`, the head's `sectors`, `box`, `lengths`) come with view B1, after wave 2.
Wave 4 waits for view B1, so that from wave 4 on every new run carries them; a run saved between wave 2 and view B1
has a store without them and counts as an old run (section 2). Nothing converts a run.

### 1.10 Risks and rollout
- **The dependency.** pyarrow 26.0.1 (Apache-2.0) is about 89 MB installed (part P5); nanoarrow 0.9.0 (1.8 MB) has no
  Windows wheel for Python 3.15, which the project runs, so pyarrow is the writer the sources leave. The Docker image
  grows by about that much (estimate); `ldd` its `.so` files (deploy rule). CLAUDE.md's procedure applies: the
  installed version's docs, the tests with deprecation warnings visible.
- **Zero copy needs aligned buffers:** zstd inside the file made apache-arrow fail unless copied (part P5): never
  compress inside the file. **The store's own bytes** may change with a library upgrade: never pin them; the pin is
  the exported CSV. **A missed `negative_zero` row or a decimals slip** changes a checksum: wave 2's check (export =
  `lines.csv`) runs on every regression entry before wave 4 removes `lines.csv`.
- **The view's order costs bytes:** `by_spot` and `spot` compress poorly (estimate: 2-4 MB more sent on the goal
  case). Rows stored in the view's order would save `by_spot`, but only if `mapping.group_lines` gives the same
  groups and `lines.csv` the same bytes whatever the input's row order: not checked; view B1 checks it first and
  keeps `by_spot` if not.
- **Exports in the quick lane** (120 s on the public site): MG5's CSV took 12.5 s plus 2.3 s of grouping (part P5);
  GeoJSON about 1.3 times the CSV's seconds (BAH 5.47 against 4.29 s, part P5). Every download costs these seconds
  again (none kept): two downloads of one file cost the worker twice. A GeoJSON of a 1.5 M-line run is about
  1.3 GB in `work/exports/` while it is sent (estimate at 880 B a line, part E5): the export refuses below
  `free_disk_gb_min` as a search does. **Measured** (wave 3, indicative, the shared lane): BAH (2 010 351 lines)
  CSV 12.3 s (388 MB), GeoJSON 16.8 s (1.77 GB); MGp (3 525 979 lines) 26.5 s (700 MB) and 30.3 s (3.14 GB); another
  quick task waited 11-28 s meanwhile. So an export of 2 M lines takes 12-17 s and one of 3.5 M about twice that
  (the public limit is 1.5 M lines), and while it runs everyone's estimates and profiles wait.
- **Disk and quotas.** `runs_gb_max` (5 GB) counts the folder; about 107 B a line instead of 1.5 KB (parts E1,
  P5): a quota holds about 14 times the lines (estimate); exports never count (none kept). No limit changes.
- **Rollout on the VPS:** wave by wave with `deploy/vps.sh update`; wave 6's nginx files by `docs/deployment.md`
  section 4 before the code that sends `Content-Encoding: br`. Old runs open at every step until wave 4; wave 4's
  removal runs on the user's word after its `--dry-run` listing (section 2). A browser with an old viewer
  revalidates it (`cache_control`: "no-cache").

- **What still reads `data.js` although the run has a store** (found in round 3; to solve before wave 4, which
  ends `data.js`; no wave above owns it yet): a share link's page (`/s/runs.js` lists no runs, so the page finds no
  store and reads `data.js`), and a run that is not in the viewer's `runs.js`. **Closed** (round 4, b757bee; no
  server change): a run the page's list does not name (a share link, another user's run opened by an administrator,
  a run saved after the list was read) asks for `lines.arrow` and `profiles.arrow` directly (`STORE_PROBE` in
  `result/load.ts`); a 404 or a fetch that fails reads `data.js`; a store fetched but of a newer format is still
  refused. An old run without a store opened that way makes two small 404 requests first, until wave 4 removes such
  runs. The list of runs is loaded once.

### 1.11 Needs the user's word
U4, U9 and U12 are decided (section 8); U6, U10, U11 are taken as recommended. The brotli codec is settled too
(2026-11-15: pyarrow's own, section 4).
## 2. Old runs: removed, not converted

### 2.1 Decision
G-06 a (as 1.1) and the user's closing answer on U5 (2026-11-14), verbatim: "3. old runs removed - both on server
and on this pc". Old runs are **removed** when the text files end, on the public site and on the user's PC; nothing
converts them. So there is no `runs migrate` and no reader of `data.js` once the text files end. The removal deletes
the user's data: it is a step of wave 4, run **only on the user's word at that time**, after a `--dry-run` listing
the user has seen. Nothing is deleted before. Until then every run opens as today, and wave 1's columns from
`data.js` stay the first step of this part. CLAUDE.md asks every change of stored data to say "automatic migration"
or "none": the removal is neither, and wave 4's commit message says "Stored data: old runs removed on the user's
word, no migration".

### 2.2 Behaviour
- **Until wave 4** every run opens as it does today: through wave 1's columns parsed from `data.js`, and from wave 2
  on through the store when the run has one. Phase 4's demand "old runs must open" holds until then.
- **An old run** at wave 4 is every run folder with a `run.json` and no `lines.arrow` of the current `format` with
  the view's columns: the runs with `data.js` (all runs saved before wave 2, also those over Chromium's string limit,
  such as MG5), the runs saved with `--no-html` (only `lines.csv`, `has_map` false), tiled runs with their work state
  (`tiles/`, `progress.json`, `shore.json`), and the runs saved between wave 2 and view B1 (a store without `spot`,
  `top`, `by_spot`). Skipped: a folder without `run.json` (being saved) and a run whose `progress.json` says
  "running"; the whole removal holds `cache.runs_lock`.
- **The command:** `findaline.py runs remove-old --dry-run` lists every old run (id, created, lines, size on disk;
  on the public site also the owner's user id, never a name or an e-mail; shared or not; demo or not; how many
  favourite lines point into it) and the totals, and deletes nothing. `findaline.py runs remove-old --yes` deletes
  the same list. On a data folder with a `jobs.sqlite` (the local app, the public site) each run goes through
  `jobs.Jobs.delete_run` (the folder, then its `runs` row, then every favourite line in it), so the database never
  keeps a row of a missing run; on a plain runs folder (the command line alone) only the folders go. Locally
  `runs.write_index` then rewrites `runs.js`. On the VPS it runs in the worker's container, as `cache migrate` does
  (`docs/deployment.md`).
- **The order, so that runs open until the user's word:** wave 4 ships in two deploys. First the code that writes
  no text files for new runs and carries `runs remove-old`, while the page still reads `data.js`. Then, after the
  user's word and the removal on that host, the code without the reader of `data.js` (`result/load.ts`, the
  script-tag fallback, `others.ts`' `lines.js`). If the user does not give the word on a host, the second deploy
  waits there. The PC and the VPS are asked separately ("both on server and on this pc").

**What happens to everything that refers to a run** (read from the code after phase 4):
| What | Where it lives (code) | What the removal does | Lost or kept |
|---|---|---|---|
| The run's lines, values, profiles, `map.html`, credits, `lines.csv`, `lines.geojson` | the run folder; `search.save_run`, `runs.save_results` | deleted | **lost**; the job's request can make the run again (below) |
| Owner, demo flag, share link, size | `jobs.sqlite` table `runs` (`user_id`, `visibility`, `share_hash`, `bytes`); `Jobs.delete_run` | the row deleted | **lost** with the run |
| Share links `/s/<token>/…` | `Jobs.shared_run` finds the run by `share_hash` | answer 404 (no row) | **lost**; the owner makes a new link on a new run |
| Favourite lines in the run (their key and the values the map sent) | table `favourites` (`run_id`, `line`, `data`); `Jobs.delete_run` deletes them | deleted | **lost**. Before the removal a user can save them with the existing "Export for the trip" (GeoJSON, CSV: `Trip.tsx`, `favourites.exportFavourites`); the dry run counts them per run. Rows left behind would be hidden (`web.all_favourites` lists only runs it finds) yet count toward `FAVOURITES_MAX`, so they are deleted |
| Folders of favourites | table `favourite_folders` | untouched | kept (a folder may become empty) |
| The demo run(s) | `runs.visibility` "demo"; the sign-in page's `web.demo_list`, `jobs.demo_runs` | deleted with the row | **lost**; the page shows no demo until an administrator runs the demo search again with the new code and marks the new run (`POST /api/runs/<id>/demo`): a step of the VPS rollout |
| Jobs | table `jobs` (`request`, `run_id`) | **as built:** marked removed (`removed_at`, since `main` e88d69f3: `Jobs.delete_run` marks the jobs that saved the run) | kept as rows (they count as before), but the cards leave Home; the dry run counts them ("N searches leave the list on Home") and the README says so (the user, 2026-11-17, Q3: "2. a"). A new search makes a new run with a new id, by the code of that day |
| `runs.js` and Compare ("Other runs", `others.ts`), thumbnails (`Thumb.tsx`), the 3D view's `&also=` lines | `runs.write_index` locally; `web.runs_js` per user on the public site, both from the folders | rewritten locally; nothing to do on the public site | the removed runs drop out of the lists |
| Problem reports with a run in their context | table `reports` | untouched | kept; their run link leads nowhere |
| Audit events naming the run | `audit` (kept `audit.KEEP_DAYS`) | untouched | kept |
| Usage and quotas | table `usage`; `runs_gb_max` counts folders | untouched | km² used stay used; the disk quota is freed |
| The tile cache, orthophotos, accounts | `cache/`, `accounts.sqlite` | untouched | kept |
| The regression set's and the truth check's runs | made again by their tools each time, outside the data folder | untouched | – |

- **Sizes:** the VPS on 2026-11-10 held 21 runs in 7.95 GB, one of 2.07 M lines (gate 1, B3 and A5); the removal
  frees all of it. The user's PC: not counted in the sources.

### 2.3-2.10
- **Data:** nothing new; Stored data: old runs removed on the user's word, no migration (2.1).
- **Interfaces:** `findaline.py runs remove-old (--dry-run | --yes) [--data-dir DIR]`; the text of the list in plain
  words. **Files and pairs:** `runs.py` (finding old runs), `findaline.py`, `jobs.Jobs.delete_run` (reused, not
  changed), `docs/deployment.md` (the two deploys); `web-app.md`'s "web.RUN_FILES and what save_map writes": the old
  files leave `RUN_FILES` with the second deploy; `run-files.md`'s favourites pair: "a change of how mapping.save_map
  rounds the anchors loses everyone's favourites (decide their migration)": here the favourites of old runs are lost
  by the user's decision, not by a rounding.
- **Tests:** on a scratch data folder with a run of each kind of 2.2, a running run and a new run: `--dry-run`
  deletes nothing and lists exactly the old ones; `--yes` deletes those folders, their `runs` rows and favourites,
  keeps folders of favourites, jobs, reports and the new run; locally `runs.js` no longer lists them; a second run
  finds nothing. No personal data in the listing.
- **Acceptance:** the dry run on a copy of the user's runs folder lists every run without a current store and none
  with one. Wave 4, part of its effort.
- **Risks:** the user's own copies of `lines.csv` or of favourites: the dry run's list and the README say what goes
  and how to keep favourites first. A demo missing on the sign-in page until it is made again.
- **As built** (round 5, `main` a0c511ac): an old run is a folder of `runs/` with `run.json` whose `lines.arrow` is
  missing, of a lower format, without the view's columns (unless run.json records `view_columns_failed`), or does
  not parse (listed "(store unreadable)"); skipped and listed apart: no `run.json` (being saved; also a tiled search
  stopped part-way), a running tiled search, a store that cannot be read now (an OS error), a newer format. The dry
  run reads `jobs.sqlite` from a checked copy in a temporary folder (a read-only open left `-wal`/`-shm` beside it).
  `--yes` rechecks each run under `cache.runs_lock`, prints what it deleted and goes on past a failure (exit 1).
  `Jobs.delete_run` (also the app's Delete…) renames the folder to `runs/_removing-<id>` under the lock, then deletes
  the rows (renamed back if that fails), then the folder outside the lock; a removal that stopped is finished by the
  next `--yes` and by the worker's housekeeping after an hour (`Jobs.finish_removals`). The words of the list: the
  user's accepted draft (Q4: "3. a").
- **As run** (2026-11-18, each on the user's word after its dry run): on the PC 39 runs (7 874 050 lines, 11.4 GB, 2
  favourite lines, 23 searches), `runs/index.html` and `findaline_map.html`; `tools/perf_reach.py`'s three named
  cases moved before into the PC's `local/reference-runs` (the user: "1. a"; `--reference-dir`); the three stopped
  tiled folders the command skips (836 MB) deleted by hand ("b"). On the server 24 runs (5 504 253 lines, 8.5 GB, 2
  favourite lines, 22 searches, the demo run) and `runs/index.html`; its 7 stopped tiled folders left ("2. a"); no
  demo for now ("3.b"). Both dry runs changed no run folder.

## 3. The ranges of a kept line

### 3.1 Decision
G-03 b, "The count and the ranges" (the user, gate 3, 2026-11-14; not the recommended a; tier: "specified, structural
(with the new store)"). The option's words: "176 B a line. Filters answer from the ranges and never miss a line."
Phase 4 built the count (`stands_for`) only. Which ranges (U1), the user's closing answer (2026-11-14): "1. c)" of
the planner's list, read as the specification's option b: **six values**, length, clearance, highest point, A-frames
needed with and without the no-fall zone, and the mean height, by which "best" is ranked.

### 3.2 Behaviour
- While the pair search runs, the square rule's reducer (`samelines.BestPerSquarePair`) keeps per pair of squares,
  beside the kept line and `stands_for`, the least and the most of each ranged value over every found line of the
  pair. Min and max are commutative and associative like the count: tiles give one grid's result, threads do not
  matter, no found line is held beyond its part.
- **The ranged values** (U1 b, decided): `length`, `clearance`, `height_max`, `lift_needed`, `lift_no_zone` and
  `height_mean`, read as `filters.ts` reads them, per found line; the two lift values only in a run with the no-fall
  zone or the A-frames. All six are in the evaluated parts (`helpers.LINE_VALUES`, `END_VALUES`). NaN is skipped;
  all NaN gives null. Every other filter tests the kept line itself: `clearance_nmpt`, `high_pct`, `dh`, the anchors'
  heights, the wall angle, prominence, drop, `over_obstacles`; and `water_m`, `filled_m`, which are not in the parts
  (computed after the join for the kept lines only, `search.line_coordinates` → `linesearch.covered_metres`: U3).
  The other values the earlier draft listed (fifteen in all) stay a later option (U1 c).
- **The page:** a kept line passes a filter when some line it stands for could pass it by the range (`lenMin <=
  len_hi`, `lenMax >= len_lo`, `clrMin <= clr_hi`, and so on for the six). A filter without a range tests the kept
  line. So the ranged filters never miss and name 1-17 % too many on their worst filter (part P3a, measured on five
  ranges; the mean height's range was not counted there). Group sizes count kept lines (as phase 4). How such a
  line is drawn and where the ranges show: U2 (no mock-up shows ranges). Runs without the square rule have no
  ranges; runs made with it before this wave: `stands_for` only.

### 3.3 Data
Per ranged value two float32 columns in `lines.arrow`, `<name>_lo` and `<name>_hi`, cast with `lo` rounded toward
−∞ and `hi` toward +∞ (a range never shrinks by the cast, so a filter never misses), null when all copies are NaN;
plus `copy_flags` uint8 (reserved: bit 0 for "some copy has no `clearance_nmpt`" and bits 1-2 for water and filled,
if later ranges need them). 8 B per ranged value + 1 B a line: **49 B for the six chosen** (estimate, part P3a's
model; 41 B for five, 121 B for fifteen).
Exports (CSV, GeoJSON) carry no range columns, so the checksum of the square rule's regression entry (R65) stays.
Stored data: none (new columns in new runs only).

### 3.4-3.11
- **Interfaces:** no new option; the ranges come with `--same-line-square`. Line details: U2.
- **Files and pairs:** `samelines.py` (`_reduce`: `np.minimum.reduceat` / `np.maximum.reduceat` beside the count's
  `np.add.reduceat`; the ranges carried with the helper columns `_KEYS`; `reduce_table` for the join of tiles),
  `linestore.py`, `filters.ts`, `types.ts`, `result/view/LineDetails.tsx`. Pairs: `search-pipeline.md`'s tiles equal
  one grid and results independent of threads (CLAUDE.md "Always"); `run-files.md`'s store ↔ `types.ts`. Memory:
  each waiting and kept row carries 8 B more per ranged value, 48 B for the six (`samelines.MERGE_ROWS`, 1 M waiting
  rows: about 48 MB more at the peak, estimate); the memory constant of a kept line (`spec-search.md` 5.1) grows by
  the same.
- **Tests:** ranges equal a plain reference (min and max per pair of squares over the full table) on a small table;
  any order of parts, any tile split, 1 and many threads give equal ranges; for random filters on the six ranged
  values every found line that passes has its kept line shown.
- **Acceptance:** on part P1's six tables at 5 m (BAH, GZp, MGp, KOB, BEL, DOL) and part P3a's combined filters with
  the mean height added: no found line missed on a ranged filter; the share named too many reported beside part
  P3a's 0-17 %; the goal case's bytes as section 6 says. Measured with `tools/prune_study.py` given a "ranges"
  report (new in wave 7).
- **Waves:** wave 7 (1.9), medium. **Risks:** bytes sent (section 6: with the six ranges the goal case sends more
  than T4's 20 MB, estimate); the reducer's memory.
- **Needs the user's word:** U1 decided (b); U2 at the details' mock-up; U3 taken as recommended (a).

### Not taken (round 7, 2026-11-23)
The user, after the measured gain and cost: "Drop the ranges". Filters test the kept line as before; G-03 b stands
as the count (`stands_for`); U1 and U2 are closed as not built.
- **What was built** (the branch kept under the tag `history/line-ranges`, never merged): the reducer's twelve values
  (lo and hi of the six), carried as float32 and cast outward at a part's entry (lo down, hi up), `np.fmin`/`np.fmax`
  (`minimum`/`maximum` would carry a NaN); a `"ranges"` mark in a tiled search's `progress.json`;
  `tools/prune_study.py --ranges`. The page's half was not started (it would have passed a kept line by its own value
  or its range: the stored mean height and A-frame values are rounded to 2 decimals, the reducer's are not). `linestore.read` of chosen columns was taken out of it and built
  alone (round 7's A4).
- **Acceptance, measured** (all six cases, as the user chose: BAH, GZp, MGp, KOB, BEL, DOL, rig C4, `--same-line-square
  5`): found and kept equal parts P1's and P3a's counts; every lo and hi the outward float32 of its pair's least and
  most stored value; no found line missed under 311 filters (300 random, P3a's 8 combined, 3 with the mean height);
  named too many on P3a's worst filter 0.07 to 3.88 % of the kept lines; the exports of KOB and DOL equal byte for
  byte and R65 unchanged.
- **The bytes of `lines.arrow`** (gzip level 5, MB = 10^6 B): without ranges 1.42 to 5.95 MB on the six cases; with
  the seven columns today's filters read 30 to 34 % more (28 B a kept line raw), with all twelve 51 to 57 % more (48 B
  raw), on every run made with the square rule.
- **What it would give** (`docs/roadmap.md`, "Line volume round 7: open", measured on four cases): with a strict
  "Clearance at least" 16 to 62 % more spots shown than the kept line's own test, "A-frame at most" without the zone up
  to 40 % at middle limits, the other filters 0 to 17 %; and rows whose own value contradicts the filter.

## 4. What is sent

### 4.1 Decision
G-06 a; kept at gate 2 and not parked at gate 3: 'Compress once at saving, serve precompressed' (F-10), 'Run files
cached as immutable' (F-12), 'Show a run's size before opening it' (F-30), 'Warn before opening a heavy run'
(T-34). Gate 1's T4: "10-20MB sounds good as a target" (the user, 2026-11-10).

### 4.2 Behaviour and numbers
Bytes sent and download seconds over the network (MB = 10^6 B). "Today" is `data.js` gzip-6 (part E2; nginx sends
gzip-5); "store" is br-5 of the store (part P5) or, marked, today's br-5 × 0.64-0.73 (part P5's store/`data.js`
ratio on MG0, BAH, MG5). Seconds = MB × 8 / Mbit/s.
| Case | Lines | Today | Store | 50 Mbit/s today → store | 10 Mbit/s today → store |
|---|---:|---:|---:|---:|---:|
| MG0 | 41 377 | 3.1 | 1.9 | 0.5 → 0.3 s | 2.5 → 1.5 s |
| GZ1 (an October run) | 695 142 | 29.7 | 12.6-14.4 (estimate) | 4.8 → 2.0-2.3 s | 24 → 10-12 s |
| BAH | 949 160 | 57.2 | 32.4 | 9.1 → 5.2 s | 46 → 26 s |
| MG5 | 3 057 204 | 249.3, crash | 137.3 | 40 → 22 s | 199 → 110 s |
| GZ1, target rig, square rule | 503 651 | `data.js` 137 MB raw (phase 4) | 17-23 (estimate, section 6) | – → 2.7-3.7 s | – → 14-18 s |

Seconds to a usable view, desktop Chromium over loopback: today MG0 0.5, GZ1 2.6, BAH 5.0 s, MG5 a crash (part E2).
With the store: loading BAH 0.18 s, MG5 0.35 s (part P5, the Arrow file) plus grouping and drawing, not measured
(part E2's grouping, BAH 1.17 s, an upper bound: BAH about 1.5-2 s, estimate). Emulated phone profiles: loading BAH
0.31 s Pixel 7 ×4, 0.41 s iPhone 13 (part P5); with grouping about 5 s and 2.5 s (estimate, part E2's ratios).

- **Compression once at saving (F-10):** the public worker writes `lines.arrow.br` and `profiles.arrow.br` after the
  store, brotli at quality 5 (U12, the user, 2026-11-14: "4. a)"). **The codec is pyarrow's own**
  (`pa.Codec("brotli", compression_level=5)`): the maintained brotli packages were compared in round 3 and the user
  chose it (2026-11-15: "a"), so no new package enters `pyproject.toml`. The builder checks
  `pa.Codec.is_available("brotli")` in the Docker image, always passes the quality, and checks a round trip through
  a real browser. `web.RunFiles` answers a request with
  `Accept-Encoding: br` from the `.br` file with `Content-Encoding: br`, `Vary: Accept-Encoding` and the decoded size in `X-Findaline-Bytes`; nginx leaves a
  response that has a Content-Encoding alone. `deploy/nginx/findaline.conf`: `application/vnd.apache.arrow.file`
  joins `gzip_types` for clients without br (done with wave 2, `main` ef93df5). The local app sends the files as
  they are (loopback).
- **Caching (F-12):** the page asks for `lines.arrow?v=<run.json store.sha256>`; `web.cache_control` answers such a
  versioned run file with "private, max-age=31536000, immutable" (others as today). A reopen then costs no request.
  Open, not measured: whether Chromium's cache keeps an entry of hundreds of MB.
- **The size before opening (F-30):** runs.js and `/api/runs` carry `summary.lines`, `summary.spots`, `store.bytes`
  (compressed when a `.br` exists); Home's cards and the share page: "949 160 lines in 645 spots · 32 MB".
- **A phone** gets the same two files (no light view: U7), the size first, and above a threshold (U8) the warning
  (T-34): "This result is large: {lines} lines, {mb} MB to download. It may take {s} seconds to open, longer on a
  phone." [Open] [Back].
- **Files and pairs:** `web.py` (`RunFiles`, `cache_control`, `/api/runs`, `runs_js`), `runs._listed`, `load.ts`,
  Home; `deploy/nginx/findaline.conf` with `tests/nginx_check.sh` and `docs/deployment.md` (the deploy rule keeps the
  three in step). Stored data: none. **Tests:** `test_public.py` (br with and without `Accept-Encoding`, `Vary`, the
  decoded size, immutable only on a versioned URL); `nginx_check.sh` (br passed through, gzip otherwise).
- **Acceptance:** the goal case's bytes sent measured against T4's 10-20 MB (section 6: about 25-33 MB expected with
  the six ranges), the response's bytes; a reopen of BAH sends no data bytes. Wave 6, medium. **Risks:** a cache
  entry refused for its size (a 200 again, no harm); br's CPU at saving (BAH 1.6 s, part P5).
- **Needs the user's word:** U12 decided (brotli, by pyarrow's own codec); U7, U8 taken as recommended.

### As built in round 7 (2026-11-23 to 2026-11-25)
The user reduced this wave to its one visible part after asking what it gains ("Size on Home only"; "No, keep
asking the server" for the immutable cache). Since the specification `data.js` was gone and nginx already gzipped the
store at level 5 (about 2.3 times smaller, the comment in `deploy/nginx/findaline.conf` says), so brotli would have
saved about 10 % of the bytes (this section's own figures, part P5's BAH store of 99.6 MB: 32.4 against 36.0 MB) for a
second copy on disk (35 to 45 % more a run, estimate) and a second way to send a file; and a reopen already costs one
request answered "not changed" without data (read in Starlette's code; not tried through the real nginx), which the
immutable cache would save, with the server's access check.
- **Built:** `/api/runs` gives each run `bytes`, run.json's `store.bytes` (the two store files as written; null for a
  run without a store block); Home's card shows it as stored (the user's "Size as stored") on the second of two fixed
  lines, "24 Nov 2026, 21:14 · 2.1 MB" (one decimal below 10 MB, whole MB to 999, then GB with one decimal; "under
  0.1 MB" below 50 000 bytes; no size on the example tile), on the public site and locally; the loading line counts
  in 10^6 bytes with the card's cut ("41 of 247 MB"; two decimals for a total under 50 000 bytes, the user's answer 3
  of 2026-11-25); `viewer/src/size.ts`; DESIGN.md row 22.
- **Not built:** brotli and its `.br` copies, `X-Findaline-Bytes`, the versioned addresses and "immutable", any change
  to nginx or the deploy; the size on a share link (a share link opens the map at once: there is no page before it);
  the warning before a heavy run (U8; A1, left out by the user); a size as sent (the bytes really downloaded are
  known nowhere: nginx compresses on the way).

## 5. Renaming a run (short)
- **Decision:** the user, on mock-up 1's open point 10 (2026-11-13): "ok, add option to rename a run". Not found in
  parts E3 or E5 (searched for "renam" and "name").
- **What breaks today:** nothing renames a run. Its name lives in `run.json` (`name`: Home, Admin, `/api/runs`,
  `runs.js`), in the folder id's slug (`runs.new_run`: date, slug, random part), in `data.js`'s head (`run.name`: the
  result page's title in `ResultColumns.tsx` and `KitResult.tsx`, a report's "about"), in `map.html`'s `<title>`, in
  `ATTRIBUTION.txt`'s first line and in `lines.geojson`'s `findaline` part. Changing `run.json` alone leaves the
  result page and the map's title with the old name. The id must never change: share links, the `runs` and
  `favourites` rows, `#run=` and `/runs/<id>/` use it.
- **Smallest fix:** `PATCH /api/runs/{run}` with `{"name": …}`, access `own_run`; the name checked by the rule of
  `--name` (`params.MAX_NAME`, no control characters); `run.json` rewritten whole (`cache.replacing`) under
  `cache.runs_lock`, locally `runs.write_index`; `map.html`'s title and `ATTRIBUTION.txt` rewritten (small files);
  audit event `run_rename`. The page shows the listed name (`/api/runs`, `runs.js`; `/s/runs.js` gains its run's
  name) before the head's. The store's head and the slug keep the name of the saving (documented as such); exports
  read `run.json`. The job's request keeps its name ("search again" names the new run by it). Stored data: none.
- **Files, pairs, tests, wave:** `web.py`, `runs.py`, `mapping.py` (title), Home's card menu, `locales/en.json`
  ("Rename"); `web-app.md`'s audit pair; a small mock-up first. Tests: round trip (list, page, title, credits),
  another user's run 404, bounds, id and links unchanged. Wave 8, low.
- **As built in round 7** (2026-11-23 to 2026-11-25; where it differs from the lines above, this holds):
  - **Where:** the public site only, no command (the user's "Public site only", "No, the page only"). Home's card
    menu ("Rename…" after "Share…", the pencil) opens a panel under the card; on a desktop the result view's header
    has the pencil after the run's name for its owner, opening a box with the field, Save and Cancel; a phone renames
    through Home (the user's answers of 2026-11-23 on the mock-up MU-1, and its 28 points "(a)" of 2026-11-24).
    Today's result page (`?view=today`, and runs the view cannot show) has no button.
  - **The route:** `POST /api/runs/{run}` (not PATCH: folders and rigs rename by POST), `own_run`; 200 `{"ok": true,
    "name": <as stored>}`, 400 `run_name`, 404 for another's run and in the local app, 409 "the run is in use" when a
    file cannot be replaced now; no rate limit; audit `run_rename` without the name.
  - **The name** (`runs.run_name`, a rule of its own, not `--name`'s): NFC, each run of whitespace one space, trimmed,
    1 to 100 characters, at least one not a space, a mark or a format character; every character of a "C" category
    (control, format, surrogate, private use, unassigned) refused but the joiners ZWNJ and ZWJ, line and paragraph
    separators too; an empty name refused (the user's
    "Refuse it"). The page sends the name as typed and shows the answered one; one text for every refusal (T6).
  - **What a rename changes** (`runs.rename_run`, under the runs lock, each file whole through `cache.replacing`):
    ATTRIBUTION.txt's first line, `map.html` (its `<title>` and the disk notice's heading, from today's template:
    `runs.map_page`, moved there from `mapping` so the web process can write it), run.json's `name` last; its own read
    of run.json through `runs.read_meta` (the user's answer 10 of 2026-11-25). Not changed: the id and folder, the
    store's head, share links, favourites, the search's own title.
  - **Where the page takes the name:** the app from the list of runs over the store's head (`result/load.ts`
    `fromServer`; `runs.js` and `/s/runs.js` did not change); a `map.html`, own or a share link's, from its `<title>`;
    the loaded run, Home, Compare and a report follow a rename at once (`renamedRun`, `forgetRunList`). An
    administrator who opens another user's renamed run sees the saving's name (docs/known-bugs.md).
  - **The privacy page** (the user's "Yes, as proposed", both): the audit list "… share links made, renewed and
    revoked, runs renamed (not their names) and deleted, exports of a run's lines made …"; the "Runs" entry "The
    results of your searches (lines, maps, parameters, the place's name from OpenStreetMap or the name you give) and
    their size. …".
  - **Stored data:** none (run.json's `name` changes on a request; no new key). Left: docs/known-bugs.md, "Line
    volume, round 7".

## 6. The path to the goal case
The Gozo coast (GZ1) in the target rig with `--same-line-square 5` (phase 4, measured): 24 480 100 lines found,
503 651 kept in 8 269 spots, 89.8 s, peak 2 911 MB, folder 865 MB, `data.js` 137 MB. The store changes nothing before
saving: the seconds and the memory of the search stay.
| Quantity | Without ranges | With the six ranges (U1 b, chosen) | Kind |
|---|---:|---:|---|
| Store, raw | 55-56 MB (105-107 B + 4 B `stands_for` a line); +4.5 MB with the view's columns | +25 MB (49 B a line) | estimate (part P5's B a line; 3.3) |
| Folder (store, br copy, small files) | about 75-80 MB; 80-85 MB with the view's columns | about 110-115 MB; 115-120 MB with the view's columns | estimate |
| Sent, br-5 | 17-23 MB (34-46 B a line, part P5's BAH and MG5); about 19-27 MB with the view's columns | 25-33 MB; about 27-37 MB with the view's columns | estimate (ranges compressing as the columns, 0.33-0.42: +8-10 MB) |
| Download at 50 / 10 Mbit/s | 2.7-3.7 / 14-18 s | 4.0-5.3 / 20-26 s (without the view's columns) | arithmetic |
| Desktop, after the download | about 1 s (loading 0.06 s scaled from part P5's 0.17 s at 1.5 M; grouping 0.5-0.7 s from part E2's GZ2 and GZ1) | about the same | estimate |
| Pixel 7 profile ×4 | about 2.5-3.5 s | – | estimate (part P5 loading; part E2's ×4 ratio) |
| iPhone 13 profile | about 1-1.5 s | – | estimate (part P5 loading; part E2's ratio 1.6-1.8) |

For comparison (estimates of the earlier draft): five ranges sent 24-32 MB, fifteen 37-49 MB. So T10 (opens on a
desktop) is met by wave 2 (estimate); T3 (≤ 300 MB) by wave 4; T4 (10-20 MB) only without ranges, at the low end of
the estimate: with the six ranges the user chose, the goal case sends about 25-33 MB (estimate), above T4, which the
user set as a guide ("10-20MB sounds good as a target"). A further saving: F-36 'Anchors as grid pixels' (parked:
most of the 32 B of x/y, part P5's estimate). A real phone's memory per tab is unknown.

## 7. Contradictions found, and what is not covered
- **G-03 b's "176 B a line"** is part P3a's model of five ranges *and* per end a bitmap of the square's pixels and
  the anchors' height range, which option c names as its own; G-03's evidence says "the range of every value a filter
  reads". Without the patches a record is about 152 B with five ranges, 232 B with fifteen (estimate).
- **"Never miss a line"** (G-03 b) holds only for the six values that have a range (U1 b); every other filter tests
  the kept line, water and filled metres included (U3).
- **Phase 4's "old runs must open"** holds until wave 4; the user's U5 ends it there (section 2). A run saved
  between wave 2 and view B1 counts as old by the rule of 2.2: the dry run shows those runs before the user decides.
- **G-06's "lines.csv … byte-equal"** holds only with the sign of -0.0 kept (1.3 keeps it).
- **D-04's evidence** "about 40-45 bytes per line" (F-05 'One binary columnar store per run', an estimate) against
  part P5's measured 105-107 B: part P5 holds. Part E5's "the viewer must still open a run from file://": D-04 a and
  G-06 a hold.
- **G-14 parks "the worker and staged loading in the page"**, but F-31 'Light view for share links and phones',
  F-24 'Tiered result for tens of millions of lines' and K-33 'Three nested results by rigging', kept at gate 2, rest
  on partial or staged loading: U7.
- **The row order** (joined at assembly): this part kept the search's order, the view's part stored lines "by spot".
  Joined in 1.3: rows in the search's order, the view's order as the column `by_spot`.
- **Not covered:** grouping and drawing from columns (wave 1 measures); a real phone; the country layer (G-06: "not
  concerned"); exclusive timings.

## 8. The user's word
**Decided by the user's closing answers (2026-11-14,** quoted in `spec.md` section 6**):**
- **U1, which ranges: (b)**, "1. c)" of the planner's list: the six values of section 3 (+49 B a line). Measured for
  five ranges: the ranged filters never miss and name 1-17 % too many (part P3a). The goal case sends about 25-33 MB
  (estimate, section 6). Left as later options: (a) five (+41 B), (c) fifteen (+121 B). **Not built**: the user
  dropped the ranges on 2026-11-23 (section 3 "Not taken").
- **U4, exports: made for each download, none kept** ("5. c) - how does it work with regressions?"): 1.2, 1.4; the
  regression set: 1.7.
- **U5, old runs: removed, not converted**, "both on server and on this pc": section 2, on the user's word at wave 4.
- **U12, compression at saving: brotli** ("4. a)"), br-5 (BAH's store 32.4 MB, 1.6 s, part P5; the others measured
  there: gzip-6 36.0 MB, 3.6 s; zstd-3 35.9 MB, 0.4 s). The packages were compared in round 3 and the user chose
  pyarrow's own codec (2026-11-15: "a"): no new package (section 4). **Not built**: round 7 reduced wave 6 to the
  size on Home (the user, 2026-11-23: "Size on Home only"; section 4 "As built in round 7").

**Taken as recommended** (class "planner": the user was offered the list on 2026-11-14 and did not go through it):
- **U3** water and filled metres: (a) left out of the ranges; (b) per found line after a measurement on the goal case.
- **U6** circles' profiles of every line (up to 500 MB a run, `search.CIRCLE_PROFILES_BYTES`): (a) kept now;
  representatives only as a task of its own.
- **U7** F-31 'Light view for share links and phones', F-24 'Tiered result for tens of millions of lines', K-33 'Three
  nested results by rigging': (a) parked with F-20 (columns hold 10 M lines on a desktop, part P5).
- **U8** the phone warning's threshold: (a) none until the real-device test; the size always shown (F-30).
- **U9** who may export: (a) the owner, an administrator, a demo run's visitors, not share links, within the quick
  lane's rates. **Decided by the user, 2026-11-16** ("No Download there (Recommended)"): a share link's page has no
  Download for a run with a store. A demo run's visitor who is not signed in gets no Download button ("No Download
  button (Recommended)"): the server makes a file only for a signed-in user. Exports have a rate of their own, as
  every other kind of the quick lane: 4 a minute and 30 an hour on the public site ("Yes, 4 a minute, 30 an hour
  (Recommended)"; both reviewers of wave 3 showed that without it one user can fill the disk and hold the lane).
  **Final, 2026-11-17:** a run's own `map.html` has no Download for a run with a store either ("1.a"): the page holds
  no token, so only the app's result page exports. Built in f2f8015.
- **U10** `--html` after `file://` ends: (a) accepted for one release, prints the `view` command.
- **U11** filtered exports, GeoPackage, KML (F-32 'Exports people can open'): (b) parked until wave 3 shows how
  exports are used.

**Still open:**
- **U2, a line that passes only by its ranges.** (a) drawn as any line, its details say "a line it stands for
  passes: clearance up to 6.2 m"; (b) a mark of its own; ranges in the details as "length 180-210 m · mean height
  31-44 m". Not in mock-up 2. Rec.: (a), with the ranges in the details; decided on a mock-up of the details first.
- **The removal itself** (U5): on each host, after its `--dry-run` list, at wave 4.
