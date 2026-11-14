# Line volume: stored and sent (specification, part 2 of 3)

2026-11-14. One of the four files of `docs/line-volume/`; how to read them, the sources and the reference cases:
[spec.md](spec.md). Code: `file:function` after phase 4. `stands_for`: the square rule's count per kept line (the
found lines it stands for, itself included; the last column of `lines.csv`); `summary.found` in `run.json`: their sum.
Sections: 1 the store (its waves cover the whole part), 2 old runs, 3 the ranges of a kept line, 4 what is sent,
5 renaming a run, 6 the goal case, 7 contradictions, 8 the user's word (U1-U12, elsewhere cited as "store U1" …).

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
- **Old runs** open through the same columns: the page parses `data.js` into columns and drops the rows (section 2).
- **The files of a run** after all waves:

| File | Command line | Local app | Public site |
|---|---|---|---|
| `lines.arrow`, `profiles.arrow` | written | written | written |
| `lines.arrow.br`, `profiles.arrow.br` (section 4) | no | no | written by the worker |
| `run.json` (+ the block `store`, below) | written | written | written (never served) |
| `map.html` (the entry page, also of share links) | written | written | written |
| `ATTRIBUTION.txt` | written | written | written |
| `data.js`, `lines.js` | gone | gone | gone |
| `lines.csv`, `lines.geojson` | on request (`export`) | on request | on request |
| `runs/runs.js` | written as today | written as today (Compare, thumbnails) | not written (generated per user) |
| `runs/index.html`, the data folder's `findaline_map.html` | gone | gone | not written today |

- **From disk** (`file://`) `map.html` loads no data and shows "This map opens through Find-a-Line. Run: findaline.py
  view <run id>"; over http the viewer removes that paragraph.
- **`findaline.py view [RUN]`** starts the local app on the data folder as `findaline.py web` does (port 8765; when
  the app already answers there, it is used) and opens the browser at `/#run=<id>` (the app's result route,
  `app/c/ResultPage.tsx`). RUN: a run id, a run folder, or nothing for the latest run. A search ends by printing
  `View it: findaline.py view <id>` instead of the two paths it prints today (`findaline.py:main`).
- **`findaline.py export RUN --format csv|geojson [--out PATH]`** writes the text from the store, byte for byte what
  `runs.save_results` writes today (default: into the run folder as `lines.csv` / `lines.geojson`).
- **In the app**, "Download CSV" and "Download GeoJSON" (`RunActions.tsx`) ask the worker for the file (quick lane,
  kind `export`), show "Preparing the file…", then download `/runs/<id>/lines.csv`; a file once made is served as
  today (kept or not: U4).
- **Limits.** Unchanged (public 1.5 M lines). No string limit in the page: none found on a desktop up to 10 M lines
  (part P5); a phone's is unknown until the real-device test. No "off": old runs keep their files.

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
| `access1`, `access2` | uint8 | 0 / 1 / 2 | column absent without `--access` | `spec-search.md` 3.3 | with the access mark |
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
  713.6 MB of `data.js`. `stands_for` adds 4 B (estimate), the view's columns about 9 B.
- **Stored data:** waves 1-4 and view B1 "none" (new files and columns; old runs open as they are; jobs.sqlite,
  favourites, share links unchanged); wave 5 migrates old runs (U5). Favourites stay valid: an int32 of 1e-7 degree
  divided by 1e7 is the same double as today's parsed 7-decimal text, so `keys.lineCoords` gives the same key (a test
  asserts it). `file://` ends with wave 4.

### 1.4 Interfaces
- **Command line:** `findaline.py view [RUN]`, `findaline.py export RUN --format csv|geojson [--out PATH]`;
  `--no-html` skips `map.html` only (the store is always written); `--html` (the path of `findaline_map.html`): U10.
  No new `SearchParams` field; the search hash and `run.json`'s params do not change.
- **Routes:** `POST /api/runs/{run}/export` with `{"format": "csv"|"geojson"}`; access `run_access` (owner,
  administrator, demo run); queued in the quick lane as kind `export`, waited for as `web.quick` waits (at most
  `QUICK_WAIT_MAX`); answers `{"url": "/runs/<id>/lines.csv"}`, 503 without a worker; audit event `run_export` on
  the public site; who may export and how often: U9. `web.RUN_FILES` gains `lines.arrow`, `profiles.arrow`;
  `web.SIZED_FILES` gains both (the decoded size in `X-Findaline-Bytes`). Media type
  `application/vnd.apache.arrow.file` for both (also `mimetypes` locally).
- **Files of a run:** the table of 1.2. The `runs` row's `bytes` is updated after an export is written.
- **Texts** (`locales/en.json`, plain words): `ui.result.export_preparing` "Preparing the file…";
  `error.export_failed` "The file could not be made. Try again in a moment."; `map.html`'s paragraph "This map opens
  through Find-a-Line. Run: findaline.py view {run}" (in the HTML, so it shows without the bundle).

### 1.5 Files and pairs
- **New `linestore.py`** (numpy and pyarrow only): `write(run_path, lines, head)` (a `LineTable`, its profiles and,
  from view B1, the view's columns), `read(run_path) -> (LineTable, head)`, `export(run_path, fmt, out)`
  (`mapping.group_lines`, then `runs.save_results(files=…)`: numba, so exports run in the worker or the command line;
  the web process needs no pyarrow). Precompression `write_br` (section 4).
- **Python:** `search.save_run` (the store instead of the scripts and text files); `saving.py` (text files only, kept
  for exports of more than 100 000 lines if wave 3's timing asks for it); `mapping.save_map` (map.html only),
  `mapping.map_heads` (the head, into the store); `runs.list_runs` (`has_lines`: `lines.arrow` or `lines.js`),
  `runs.write_index` (no `index.html`); `findaline.py` (`view`, `export`, the last lines); `jobs.py` (quick kind
  `export`, `runs.bytes`); `web.py` (`RUN_FILES`, `SIZED_FILES`, the route, section 4); `pyproject.toml`, `uv.lock`.
- **Viewer:** `types.ts` (the columns, `toLine` from columns), `result/load.ts` (the store reader; `data.js` filling
  columns; no script-tag fallback over http), `result/model.ts`, `filters.ts`, `grouping.ts`, `others.ts` and
  `app/c/Thumb.tsx` (Compare, thumbnails), `RunActions.tsx`, `package.json` (apache-arrow 21.2.0, Apache-2.0, 50 KB
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
No accepted mock-up covers this part. The Download buttons, `map.html`'s disk notice, the size on Home's cards and
the warning before a heavy run (section 4) get a small mock-up first.
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
- Regression: `measure` takes the sha256 of the CSV text that `linestore.export` makes from the run's store, which is
  the same bytes as today's `lines.csv`, so **every checksum in `tests/regression.json` stays as it is** (R65, the
  square rule's entry, included); wave 2 adds a check that this export equals the `lines.csv` the same run still
  writes (both exist until wave 4). `check_map`: store rows = CSV rows; profiles one per spot, or every line for a
  circle with `summary.profiles` "all"; the `lines.js` check goes. `same_as` compares exported texts. `--browser`
  opens the run through the local app over http.

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

### 1.9 Waves (of the whole part; each wave ships alone and leaves every regression checksum as it is)
| Wave | What | Agents and the files each owns | After | Effort |
|---|---|---|---|---|
| 1 | Columns in the page from today's `data.js` (F-19, first, as the user asked); an empty body over http shows "This result is too large for this browser" instead of the script-tag fallback that crashes (part E2); measures T5/T6 on BAH and a 2.29 M cut and reports | A: `types.ts`, `result/load.ts`, `result/model.ts`, `filters.ts`, `grouping.ts`, `list.ts`, `result/view/*`, `favourites.ts`, `test_viewer.py`, `test_shell_c.py`, `viewer/dist` | – | high |
| 2 | The store written beside today's files; the page prefers it | B (Python): `linestore.py`, `search.save_run`, `mapping.map_heads`, `runs.list_runs`, `web.RUN_FILES`/`SIZED_FILES`, `pyproject.toml`, `uv.lock`, the unit and public tests, `regression.py` (export = `lines.csv`); C (page): the store reader in `load.ts`, `package.json`, `viewer/dist` | B: –, in parallel with 1; C: 1 | medium each |
| 3 | Exports on request; regression's checksum from the export | D: `jobs.py` (kind `export`), `web.py` (route), `RunActions.tsx`, `findaline.py export`, `locales/en.json`, `regression.py`, tests | 2 | medium |
| 4 | Text files and `file://` end; `view`; Compare and thumbnails from the store | E: `search.save_run`, `saving.py`, `mapping.save_map`, `runs.write_index`, `findaline.py`, tools, README, setup guide, CLAUDE.md, rules, `docs/`; F: `others.ts`, `Thumb.tsx`, the disk notice, `test_web.py` | 3 | high |
| 5 | Old runs converted (section 2) | G: `findaline.py runs migrate`, `docs/deployment.md`, `deploy/vps.sh` (if U5 says automatic) | 4 | medium |
| 6 | What is sent (section 4) | H: `web.RunFiles`, `web.cache_control`, `linestore.write_br`, `deploy/nginx/findaline.conf`, `tests/nginx_check.sh`, `docs/deployment.md`, Home's size and the warning (after their mock-up) | 2 | medium |
| 7 | The ranges of a kept line (section 3) | I: `samelines.py`, `linestore.py`, `filters.ts`, `LineDetails.tsx`, tests | 2 | medium |
| 8 | Renaming a run (section 5) | J: `web.py`, `runs.py`, `RunActions.tsx` or Home, tests | – (simplest after 4) | low |

The view's columns (`spot`, `top`, `by_spot`, the head's `sectors`, `box`, `lengths`) come with view B1, after wave 2.
A run converted by wave 5 after view B1 gets them too; one converted before gets them by a second `runs migrate`.

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
  GeoJSON about 1.3 times the CSV's seconds (BAH 5.47 against 4.29 s, part P5). A kept GeoJSON of a 1.5 M-line run is
  about 1.3 GB (estimate at 880 B a line, part E5).
- **Disk and quotas.** `runs_gb_max` (5 GB) counts the folder; about 107 B a line instead of 1.5 KB (parts E1,
  P5): a quota holds about 14 times the lines (estimate); exports kept count too (U4). No limit changes.
- **Rollout on the VPS:** wave by wave with `deploy/vps.sh update`; wave 6's nginx files by `docs/deployment.md`
  section 4 before the code that sends `Content-Encoding: br`; wave 5's migration after wave 4 (U5). Old runs open
  at every step (section 2). A browser with an old viewer revalidates it (`cache_control`: "no-cache").

### 1.11 Needs the user's word
U4 (exports kept), U6 (circles' profiles), U9 (who may export), U10 (`--html`), U11 (exports' formats), U12: section 8.
## 2. Old runs

### 2.1 Decision
G-06 a (as 1.1); CLAUDE.md: every change decides "automatic migration" or "none"; phase 4: "Old runs must open".

### 2.2 Behaviour
| Kind of run on disk today (where) | Opens | Converted (wave 5, U5) | Cost | Never lost |
|---|---|---|---|---|
| A run with `data.js`, `lines.js`, `lines.csv`, `lines.geojson` (local and VPS; most runs) | as it is: `data.js` → columns (wave 1) | store from `data.js` (lossless for what it holds, part P5), then the export compared with `lines.csv`'s sha256; on equality `data.js`, `lines.js`, `lines.geojson`, `lines.csv` deleted | folder −93 % (BAH 1 437.6 → 99.6 MB, part P5); seconds: BAH about 10 s, MG5 about 40 s (estimate: part P5's 4.3-12.5 s per CSV plus the parse) | lines, values, profiles, favourites' keys, share links, owners, `run.json` |
| Its `map.html` loads `data.js` by a script tag (before 2026-11-04, `main.tsx`) | as it is | `map.html` rewritten to today's template | none | the same |
| Variants of the first row: no terrain statistics (before 2026-11-03), shore (before 2026-11-05) or `terrain_sources`; `ends` (zone, A-frames); NaN or Infinity in `data.js`; every line's profile (circles); `stands_for` (phase 4) | as it is (the script tag over http only for a non-empty body) | the head keeps what `data.js` had; `ends` → named columns; Python's `json` reads NaN; all profiles; `stands_for`, `square`, `found` kept | none | the same |
| Larger than Chromium's string (MG5, 3.06 M lines; `data.js` over 536 870 888 characters, part E2) | "too large for this browser" (wave 1) | as the first row; then it opens (part P5: MG5's Arrow file loads in 0.35 s on a desktop; 0.40 s is part P5's plain-columns variant) | Python's parse of a 714 MB `data.js` needs several GB (estimate): one run at a time | the same |
| Saved with `--no-html` (no `data.js`, `lines.js`, `map.html`) | not in the app today (`has_map` false) | **not converted**: `lines.csv` lacks the unrounded x/y and the profiles; listed as "kept as it is" | none | `lines.csv` |
| A tiled run with `tiles/`, `progress.json`, `shore.json` left (part E5) | as it is | the store only; work state untouched (its clean-up is a roadmap item) | none | the same |
| A run being saved, or a search running in its folder | – | skipped (no `run.json`, or `progress.json` "running"); under `cache.runs_lock` | none | – |
| Demo and shared runs (VPS) | as they are | as their kind above; rows in `runs` untouched | none | links (`map.html` stays) |

- The VPS on 2026-11-10: 21 runs in 7.95 GB, one of 2.07 M lines (gate 1, B3 and A5). After conversion about
  0.6-2.2 GB (estimate: −72 to −93 %, part P5's folders without the two text files and with the store alone).
- A conversion that fails (export ≠ `lines.csv`) deletes nothing and is listed; a run then opens as it is.
- Once view B1 is built, a conversion also writes the view's columns (1.3), so an old run opens in the result view.

### 2.3-2.10
- **Data:** the store of 1.3; `run.json` gains `store` and `"converted": "<date>"`. Stored data: U5.
- **Interfaces:** `findaline.py runs migrate [--dry-run] [--keep-text]` and `runs status`, as `cache migrate` /
  `cache status` (`docs/deployment.md`, "The cache's tile encoding"). **Files and pairs:** `runs.py`, `findaline.py`,
  `update.py`; "web.RUN_FILES and what save_map writes" (old files stay in `RUN_FILES` until no run has them).
- **Tests:** a run made by today's code, converted: the text files gone, the export equal to the old `lines.csv`,
  the page's columns equal; a `--no-html` run and a running run untouched; a second migrate does nothing (or adds
  only the view's columns). **Acceptance:** on a copy of the user's runs folder every converted run's export equals
  its old `lines.csv` (sha256), and MG5 opens on a desktop. Wave 5, medium. Risk: deleting text files the user
  copied elsewhere by habit: `--keep-text` and the README say so. **Needs the user's word:** U5.

## 3. The ranges of a kept line

### 3.1 Decision
G-03 b, "The count and the ranges" (the user, gate 3, 2026-11-14; not the recommended a; tier: "specified, structural
(with the new store)"). The option's words: "176 B a line. Filters answer from the ranges and never miss a line."
Phase 4 built the count (`stands_for`) only.

### 3.2 Behaviour
- While the pair search runs, the square rule's reducer (`samelines.BestPerSquarePair`) keeps per pair of squares,
  beside the kept line and `stands_for`, the least and the most of each ranged value over every found line of the
  pair. Min and max are commutative and associative like the count: tiles give one grid's result, threads do not
  matter, no found line is held beyond its part.
- **The ranged values** (which of them: U1) are read as `filters.ts` reads them, per found line: `length`,
  `clearance`, `clearance_nmpt`, `height_max`, `height_mean`, `high_pct`, `lift_needed`, `lift_no_zone`, and derived
  `dh` = |e1 − e2|, lower anchor = min(e1, e2), upper anchor = max(e1, e2), wall angle = max(angle1, angle2),
  prominence of the more and of the less prominent anchor, drop = min(drop1, drop2). All are in the evaluated parts
  (`helpers.LINE_VALUES`, `END_VALUES`). NaN is skipped; all NaN gives null. `over_obstacles` is `clearance_nmpt <= 0`
  in mark mode (`mapping.coordify`), so it follows from that range. `water_m` and `filled_m` are not in the parts:
  they are computed after the join for the kept lines only (`search.line_coordinates` → `linesearch.covered_metres`):
  U3.
- **The page:** a kept line passes a filter when some line it stands for could pass it by the range (`lenMin <=
  len_hi`, `lenMax >= len_lo`, `clrMin <= clr_hi`, the percentiles through `percentileRank` of the lower and upper
  ranges); `clrN`: also when some copy has no surface value. A filter without a range tests the kept line. So
  combined filters never miss and name 1-17 % too many on their worst filter (part P3a). Group sizes count kept
  lines (as phase 4). How such a line is drawn and where the ranges show: U2 (no mock-up shows ranges). Runs
  without the square rule have no ranges; runs made with it before this wave: `stands_for` only.

### 3.3 Data
Per ranged value two float32 columns in `lines.arrow`, `<name>_lo` and `<name>_hi`, cast with `lo` rounded toward
−∞ and `hi` toward +∞ (a range never shrinks by the cast, so a filter never misses), null when all copies are NaN;
plus `copy_flags` uint8 (bit 0: some copy has no `clearance_nmpt`; bits 1-2 for water and filled if U3 says so).
8 B per ranged value + 1 B a line: 41 B for part P3a's five, 121 B for all fifteen (estimate, part P3a's model).
Exports (CSV, GeoJSON) carry no range columns, so the checksum of the square rule's regression entry (R65) stays.
Stored data: none (new columns in new runs only).

### 3.4-3.11
- **Interfaces:** no new option; the ranges come with `--same-line-square`. Line details: U2.
- **Files and pairs:** `samelines.py` (`_reduce`: `np.minimum.reduceat` / `np.maximum.reduceat` beside the count's
  `np.add.reduceat`; the ranges carried with the helper columns `_KEYS`; `reduce_table` for the join of tiles),
  `linestore.py`, `filters.ts`, `types.ts`, `result/view/LineDetails.tsx`. Pairs: `search-pipeline.md`'s tiles equal
  one grid and results independent of threads (CLAUDE.md "Always"); `run-files.md`'s store ↔ `types.ts`. Memory:
  each waiting and kept row carries 8 B more per ranged value (`samelines.MERGE_ROWS`, 1 M waiting rows: 40-120 MB
  more at the peak, estimate); the memory constant of a kept line (`spec-search.md` 5.1) grows by the same.
- **Tests:** ranges equal a plain reference (min and max per pair of squares over the full table) on a small table;
  any order of parts, any tile split, 1 and many threads give equal ranges; for random filters every found line
  that passes has its kept line shown.
- **Acceptance:** on part P1's six tables at 5 m (BAH, GZp, MGp, KOB, BEL, DOL) and part P3a's combined filters: no
  found line missed; the share named too many within part P3a's 0-17 %; the goal case's bytes as section 6 says.
  Measured with `tools/prune_study.py` given a "ranges" report (new in wave 7).
- **Waves:** wave 7 (1.9), medium. **Risks:** bytes sent (section 6: all fifteen ranges break T4 on the goal case,
  estimate); the reducer's memory.
- **Needs the user's word:** U1, U2, U3.

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
  store (which method: U12). `web.RunFiles` answers a request with `Accept-Encoding: br` from the `.br` file with
  `Content-Encoding: br`, `Vary: Accept-Encoding` and the decoded size in `X-Findaline-Bytes`; nginx leaves a
  response that has a Content-Encoding alone. `deploy/nginx/findaline.conf`: `application/vnd.apache.arrow.file`
  joins `gzip_types` for clients without br. The local app sends the files as they are (loopback).
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
- **Acceptance:** T4 ≤ 20 MB sent for the goal case (section 6), the response's bytes; a reopen of BAH sends no data
  bytes. Wave 6, medium. **Risks:** a cache entry refused for its size (a 200 again, no harm); br's CPU at saving.
- **Needs the user's word:** U7, U8, U12.

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

## 6. The path to the goal case
The Gozo coast (GZ1) in the target rig with `--same-line-square 5` (phase 4, measured): 24 480 100 lines found,
503 651 kept in 8 269 spots, 89.8 s, peak 2 911 MB, folder 865 MB, `data.js` 137 MB. The store changes nothing before
saving: the seconds and the memory of the search stay.
| Quantity | Without ranges | With five ranges (U1 a) | With fifteen (U1 c) | Kind |
|---|---:|---:|---:|---|
| Store, raw | 55-56 MB (105-107 B + 4 B `stands_for` a line); +4.5 MB with the view's columns | +21 MB | +61 MB | estimate (part P5's B a line) |
| Folder (store, br copy, small files) | about 75-80 MB | about 105 MB | about 160 MB | estimate |
| Sent, br-5 | 17-23 MB (34-46 B a line, part P5's BAH and MG5); about 19-27 MB with the view's columns | 24-32 MB | 37-49 MB | estimate (ranges compressing as the columns, 0.33-0.42) |
| Download at 50 / 10 Mbit/s | 2.7-3.7 / 14-18 s | 3.8-5.1 / 19-26 s | 5.9-7.8 / 30-39 s | arithmetic |
| Desktop, after the download | about 1 s (loading 0.06 s scaled from part P5's 0.17 s at 1.5 M; grouping 0.5-0.7 s from part E2's GZ2 and GZ1) | about the same | about the same | estimate |
| Pixel 7 profile ×4 | about 2.5-3.5 s | – | – | estimate (part P5 loading; part E2's ×4 ratio) |
| iPhone 13 profile | about 1-1.5 s | – | – | estimate (part P5 loading; part E2's ratio 1.6-1.8) |

So T10 (opens on a desktop) is met by wave 2 (estimate); T3 (≤ 300 MB) by wave 4; T4 (10-20 MB) only without
ranges, at the low end of the estimate. A further saving: F-36 'Anchors as grid pixels' (parked: most of the 32 B of
x/y, part P5's estimate). A real phone's memory per tab is unknown.

## 7. Contradictions found, and what is not covered
- **G-03 b's "176 B a line"** is part P3a's model of five ranges *and* per end a bitmap of the square's pixels and
  the anchors' height range, which option c names as its own; G-03's evidence says "the range of every value a filter
  reads". Without the patches a record is about 152 B with five ranges, 232 B with fifteen (estimate).
- **"Never miss a line"** (G-03 b) holds only for the values that have a range: not water and filled metres (U3).
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

## 8. Needs the user's word
- **U1, which ranges.** (a) part P3a's five: length, clearance, largest height, A-frame needed with and without the
  zone (+41 B a line); (b) the five and the mean height, by which "best" is ranked (+49 B); (c) every value a filter
  reads, fifteen (+121 B). Measured: combined filters never miss and name 1-17 % too many (part P3a); the goal case
  sends 24-32 MB with (a), 37-49 MB with (c) (estimate). Rec.: (b): nearest T4; other filters test the kept line.
- **U2, a line that passes only by its ranges.** (a) drawn as any line, its details say "a line it stands for
  passes: clearance up to 6.2 m"; (b) a mark of its own; ranges in the details as "length 180-210 m · mean height
  31-44 m". Not in mock-up 2. Rec.: (a), with the ranges in the details; a mock-up of the details first.
- **U3, water and filled metres in the ranges.** (a) left out (those filters test the kept line); (b) computed per
  found line in the reducer (cost not measured). Rec.: (a) now; (b) after a measurement on the goal case.
- **U4, an export once made.** (a) kept and counted in the quota (a 1.5 M-line GeoJSON about 1.3 GB, estimate);
  (b) made per download into `work/` and deleted. Rec.: (a) for CSV, (b) for GeoJSON.
- **U5, old runs.** (a) automatic: `runs migrate` by `deploy/vps.sh update` after the services start, as `cache
  migrate`; (b) by hand; (c) none. Measured: −93 % of BAH's folder (part P5); each conversion checked by the CSV's
  sha256 before a file is deleted. Rec.: (a) on the VPS, (b) on the PC (the user's MG5 and test runs).
- **U6, circles' profiles of every line** (up to 500 MB a run, `search.CIRCLE_PROFILES_BYTES`, kept only because a
  disk map cannot compute one). (a) kept; (b) representatives only, the rest from `/api/profile` (changes
  `check_map`'s rule, not a checksum). Rec.: (a) now, (b) as its own task.
- **U7, F-31, F-24, K-33** (each a partial or staged loading). (a) parked with F-20; (b) a further wave. Rec.: (a):
  columns hold 10 M lines on a desktop (part P5).
- **U8, the phone warning's threshold.** (a) none until the real-device test, the size always shown (F-30); (b) a
  provisional one (part P5's estimate: about 5 M lines in Chromium, 2-3 M in Safari at 1 GB a tab). Rec.: (a).
- **U9, who may export.** (a) the owner, an administrator, a demo run's visitors, not share links, within the quick
  lane's rates; (b) share links too. Rec.: (a).
- **U10, `--html`** after `file://` ends. (a) accepted for one release, prints the `view` command; (b) removed.
  Rec.: (a).
- **U11, filtered exports, GeoPackage, KML** (F-32 'Exports people can open'). (a) a wave after wave 3 (pyogrio is a
  dependency already); (b) parked. Rec.: (b) until wave 3 shows how exports are used.
- **U12, compression at saving.** (a) br-5 with `brotli` (new dependency; BAH's store 32.4 MB, 1.6 s); (b) gzip-6,
  standard library (36.0 MB, 3.6 s); (c) zstd-3, Python's `compression.zstd` (35.9 MB, 0.4 s; Safari's support not
  known); (d) none, nginx gzip-5 as today (part P5). Rec.: (a), after the libraries' comparison goes to the user.
