# Known bugs

Open defects that are not a task of their own yet, with what was measured. Remove an entry when it is fixed
(and name the fix's commit in docs/roadmap.md if it mattered).

## The probe's tiles strategy still asks `Range: bytes=0-0`

`probe._read` (the "tiles" strategy of `IndexedTiles` sources) sends `Range: bytes=0-0`, which the source rules forbid
for new requests (some servers answer it with the whole file or an error). Batch 5's new kinds avoid it (`sheet`:
bytes 0-7; `zipfile`: the first KB without a Range). Found 2026-11-15 by agents AU and IT; not changed.

## A GDAL read of a host that never answers blocks for over 10 minutes

When basisdata.nl stopped answering TCP (2026-11-15), `tools/check_source.py` on a Caribbean Netherlands source
waited more than 10 min (GDAL's connect timeout times its retries) before failing; the probe gave up at its 120 s.
A shorter connect timeout for `/vsicurl/` in `net._gdal_http` would bound it. Found by agent NL.

## `tests/regression.py --update` cannot add a new entry without "expected", nor one without lines

A new entry in `tests/regression.json` without an `"expected"` object crashes `--update` with a `KeyError`
(`compare(test["expected"], found)` runs before the update), so a new entry needs `"expected": {}` by hand; and a
search that finds no lines stops with `SearchError` "no_lines" (no map, an exit code or problems), so `--update`
stores nothing for it and says nothing about it beyond the comparison's output. Found 2026-11-15 by agent CE (batch 5 wave 2, R78 and R79); not changed.

## The test lock fails with a relative path to the program

`tools/test_lock.py run -- .venv\Scripts\python.exe ...` (a relative executable path) fails, while the same command
with an absolute path runs. Seen 2026-11-15 by agents LT and TO (batch 5 wave 2), not reproduced or traced; give the program by its
absolute path.

## Clock-bound tests fail under a parallel full pytest

Two tests assert wall-clock times that a loaded PC misses; each passed when run alone (2026-11-15, batch 5 wave 2:
not caused by its changes; the tests are unchanged):
- `tests/test_web.py::test_quick_lane_idle_and_prompt` asserts each of five quick-lane answers within 0.5 s
  (`time.monotonic() - started < 0.5`): 0.85 s in the CE agent's full suite and again in the merged wave 2 suite.
- `tests/test_probe.py::test_timeout` runs the probe with `timeout=0.5` over a slow source (3 s) and a fast one and
  asserts "2 checked, 1 failed": under load the fast source misses the 0.5 s too. Failed in batch 5 runs (agent CE).

## `test_search_panel_on_a_phone` fails under a full pytest

`tests/test_web.py::test_search_panel_on_a_phone` sometimes fails in a parallel full pytest with `KeyError: 'phone'`
(seen 2026-11-15 and 2026-11-16 on several trees of the line-volume task, also on a tree without the task's page
changes); alone it passed 3 of 3. The cause is not found. Run it alone before calling a failure of it a
regression.

## `test_access_mark_in_the_form` fails at some times on `main` itself

`tests/test_web.py::test_access_mark_in_the_form` (Edge through Playwright) failed on 2026-11-16, late evening: after
the click on Basic's "?" of "Reaching the anchors" it presses Esc and waits for the help to go
(`wait_for_selector(".s-access .ac-help", state="detached")`), and the help stayed for the whole 30 s. It failed in a
full pytest of the ui-shots-speed branch, alone 3 of 3 there, and alone on a clean checkout of `main` (ee67bd1), so
it was not that branch's (which touches neither the test nor the viewer). The same test had passed two hours earlier
in a full pytest of the same branch. The cause is not found; the test relies on the keyboard focus being on the "?"
after the click, so the state of the PC (which window has the focus, a locked screen) is the first thing to check.
Before calling a failure of it a regression, run it alone on a clean checkout of `main`.

In the same evening's first full pytest `tests/test_web.py::test_search_panel_estimate_rate` (headless Edge) timed
out once, with other sessions running under the test lock; alone it passed 4 of 4.

## `test_quick_lane` fails at some times with "disk I/O error"

`tests/test_web.py::test_quick_lane` failed on 2026-11-17 in a full pytest of the ui-shots-waits branch with
`sqlite3.OperationalError: disk I/O error` at `jobs.py:447`, raised while the test client shuts the app down (the
scheduler and its worker still running beside it, a proxy set in the environment). Alone it failed 2 of 5 runs on a
clean checkout of `main` (bca2aa6) and 2 of 5 on that branch, which touches neither `jobs.py`, `web.py` nor the test;
it passed at f2f8015 and 2a04f84 in single runs, so no commit is known to have brought it in. The disk had 200 GB
free. The cause is not found: an SQLite file of the test's `tmp_path` held or removed by another process while the
app closes is the first thing to check. Before calling a failure of it a regression, run it alone a few times on a
clean checkout of `main`.

## The 3D view's "Only valid lines" shows an empty scene in WebKit's screenshots

`tools/ui_shots.py`'s page `view3d-valid` (the 3D view at `?level=full`, the tool "Only valid lines" clicked, then a
wait for `data-reach="1"`) on the iPhone 13 profile (Playwright's WebKit on Windows) has no terrain and no line, only
the anchors' handles: in both themes and in both whole-set runs of 2026-11-16 (the clip's run, `main` 2f019d6). The
same page on the Pixel 7 and the desktop (Chromium) is drawn, and so are the iPhone's other twelve 3D pages
(`view3d-full`, `view3d-trees`, `view3d-point` among them). In one of the two runs the pill "Checking valid lines…"
was still shown although `data-reach` was already "1". Not looked into: either the reach overlay's pass leaves
WebKit's canvas empty (a fault a real iPhone would show too), or WebKit's screenshot misses the frame drawn after
it. The first check: the page on a real iPhone (`tools/device_page.py`).

## Five tests fail on macOS (arm64) on `main` itself

Seen 2026-11-08 on a MacBook (Apple silicon, macOS 26.6.1; Python 3.15.2 from uv, numpy 2.5.4, numba 0.68.0,
scipy 1.18.1, rasterio 1.5.2) at `main` d466347 and at 7aeadc4, so before any branch of that day; the Windows PC,
where the tests and the regression baselines were made, passes them. The full offline `pytest` ends with
`5 failed, 13xx passed, 163 skipped`:

| Test | What it compares | What fails on the Mac |
| --- | --- | --- |
| `tests/test_end_zone.py::test_search_equals_brute_force[sag-reject-False-False-150.0]` and `[sag-mark-True-True-None]` | `linesearch.find_valid_lines` against the brute force over `helpers.evaluate_line` with the sag model, every value of every line equal | the sorted lists differ at rule `(0.0, 0.0, 0.0)` (no zone, no lift): the kernel and the brute force disagree on at least one line's values |
| `tests/test_end_zone.py::test_evaluate_lines_matches_evaluate_line` | `linesearch.evaluate_lines` against `helpers.evaluate_line` with `==` (the sag model among the cases); passes alone, fails when the file runs | `fast.lines() == slow` is False for a sag case |
| `tests/test_end_zone.py::test_heights_include_the_lift[sag]` | the heights of `evaluate_lines` at a lift equal `evaluate_line`'s (`height_max`, `height_mean`, `high_pct`) | a line's values differ (the assertion names anchors `[56, 96]`, `[98, 36]`) |
| `tests/test_neighbours.py::test_neighbours_resampled_as_set[30]` | the neighbour fill at the grid's own resolution: `nearest` leaves every pixel on the synthetic ramp's values, `bilinear` almost none | `np.isin(results["nearest"], ramp).all()` or the bilinear share fails: GDAL's cross-CRS warp lands on other values |

What they have in common: float-exact comparisons of numba kernels (the sag model's `_evaluate`/`_interp` against
Python's `np.interp` and the catenary of `sag.py`) and of a GDAL warp between two CRSs. The formula model's cases
pass, so the difference lies in the sag table's arithmetic (libm on arm64 against x86-64, or numba's fast-math
choices) and in PROJ/GDAL's transformer on this platform, not in the search's logic. The regression set's checksums
are the Windows PC's: a run on the Mac (R16, 2026-11-08) gave another `lines.csv` checksum with the old code too,
while R9, R18, R26, R29-R32, R40, R50 and R55 were equal.

To do, as a task of its own: run the four sag cases with the difference printed (which line, which value, how many
ULP), decide whether the kernels or the tests should tolerate it, and check the warp's resampling flags on macOS.
Until then a full run on the Mac that fails exactly these five is not a regression of the branch under test.

## The test lock's timeout does not count the time the Mac sleeps

`tools/test_lock.py run --timeout S` kills the command after S seconds of `subprocess.Popen.wait`, which counts
monotonic time; macOS stops that clock in sleep. On 2026-11-08 a full `pytest` run under `--timeout 2400` sat
94 minutes while the Mac slept from 15:40 to 16:27 with maintenance wakes: a test's TCP connection to the test
server broke in sleep (`tests/test_windows.py`'s cut-short answers, waiting in GDAL with no socket timeout) and the
wrapper's 40 minutes never ran out. Run long suites under `caffeinate -i` on a Mac, or keep the lid open. A fix
would compare wall-clock time in the wrapper's poll and give the range reads a socket timeout.

## A search without lines cannot delete its work folder on Windows

Seen 2026-11-08 by the truth check (docs/truth-check.md), also on the Żabi Koń clip: `findaline.py` on Windows
prints "Could not delete the work folder" after a search that stops without lines (no anchors, no lines). The
memory-mapped grids of step 1 are still referenced by the exception in flight when the folder is removed, and
Windows refuses to delete a file with an open mapping. The search's result is right; `work/<id>/` stays on the disk
with its grids (tens to hundreds of MB a search) until someone removes it. `tools/truth_study.py run` removes the
folders its children leave; the command line and the web worker do not (the worker's housekeeping removes old work
folders later). A fix would release the grids (drop the references, close the views) before the removal, or remove
the folder after the exception has been handled.

## The end zone's 25 % cap is one step too long on some diagonal lines

Seen 2026-11-08 by the truth check: `helpers.zone_steps` takes the `ceil` of `min(end_zone, ZONE_CAP·L)·steps/L`.
On a slightly diagonal line under the cap the product is 15.000000000000002 for an exact 15, so the zone gets 16
steps, one more than 25 % of the line. Its twins repeat the arithmetic (`linesearch._zone_steps`, the viewer's
`endzone.ts` `zoneSteps`), so the three agree with each other and the tests comparing them pass. A fix changes all
three together and the results of searches with a no-fall zone (the relaxed test reaches one pixel less at each
end), so it needs the checks of `.claude/rules/line-test.md`, "Must stay in sync", for the end zone.

## A tiled area on a grid not exact in binary crashes

Seen 2026-11-14 by the line-volume task's review of the square rule, on a grid made for it, and older than the rule
(already on `line-volume` before it): a tiled area search on a grid whose resolution or origin is not exact in binary
(an own elevation file with 1.2 m pixels, corners on 0.6 + 1.2 k) always stops with "the tile … lies outside the
grid", raised by `search._tile_window`: the tile's clipped right edge is rounded up one pixel, so the tile reaches
past the area's grid. Grids whose resolution and origin are exact in binary (1, 2 or 2.5 m on whole or half metres)
are not concerned. A fix would place a tile's edges by the area grid's pixel indices (whole numbers) instead of by
coordinates.

## The square rule: a tiled search's line limit counts a pair of squares twice

Seen 2026-11-14 (the line-volume task, confirmed by a run): with `--same-line-square`, a tiled search checks the
line limit against the lines each tile kept, before the tiles are joined; a pair of anchor squares with lines in two
tiles then counts once per tile until the join keeps one. R65 searched as an area in 400 m tiles counted 3 497
against 3 491 after the join (a limit of exactly 3 491 refused the tiled search and accepted the one-grid search);
the Gozo coast 503 718 against 503 651. So a search within about 0.2 % under the line limit can be refused when
tiled, and the refusal names the larger count. The memory check is right to count those lines (they are held until
the join). Kept as a known finding by the user's choice (2026-11-14). A fix counts distinct pairs of squares across
the tiles for the line limit (each tile's keys kept, also in the early check) and leaves the memory check as it is.

## The square rule: a tile's squares can differ from one grid's on grids not exact in binary (latent)

Found 2026-11-14 by computing, not by a search: the square of an anchor comes from `grid.pixel_to_xy` in a tile's
reducer and from `a1_xy` on the join. On grids of 1, 2, 2.5 and 3 m the two are bit-identical; on a 1.2 m grid with
origin 0.6, 12 804 pixel centres differ and 3 408 fall into another square, so a tiled search could keep other lines
than the same search on one grid. Not reachable today: such a tiled search crashes first (the entry above). A fix,
before that crash is fixed: the squares from coordinates rounded to the millimetre, or from whole-lattice pixel
indices.

## Réunion's LiDAR HD holds wrong heights at the offshore edge of its data

Seen 2026-11-15 (batch 6): where IGN's LiDAR HD of La Réunion ends offshore, about 1 km out at Cap Méchant, its edge
holds heights of -40 to 975 m in the 0.5 m pixels (-235 to 644 m in the service's 1 m answers), 353 pixels above
100 m in tile 367_7635; a 1200 m search there finds 288 anchors on them, and no line used them. Left as they are by
the user's decision of 2026-11-15 (`france_reunion`'s note says so). A fix would mask the data's offshore edge.

## The sea floor rule: what it leaves behind

`Layer.nodata_below` (-1 m on IGN's overseas RGE ALTI 1 m layers, 2026-11-15; on Tokyo's island sheets through
`Layer.floor_of`, 2026-11-16) and `Layer.height_offset` (Hong Kong's -1.30 m, 2026-11-16) are applied where tiles are
read onto the grid, so:
- a run saved before a rule shows the terrain of after it in its 3D view and in a profile computed again: the
  heights there are no longer those its search used (Hong Kong's 1.30 m lower; no such run exists outside the
  batch's scratch folders);
- `tools/check_source.py`'s files, alignment and precision checks read the raw tiles, without the floor or the
  offset (its checks against Copernicus read the grid, with both);
- floored pixels outside the search's sea zone (OSM's sea plus 20 m) become gaps on land, filled from the fallback
  model, not 0 m: measured only at Fort-de-France (4 851 px, 1.8 % of the area, filled at about 1.5 m, steps of up to
  2.8 m);
- reef flats between -1 and -1.7 m off Mayotte are cut and filled at 0 m.

## Tokyo's island sheets hold seabed: floored at -1 m

Seen 2026-11-15 (batch 6): near the Izu islands' coasts the Tokyo Digital Twin's grids hold seabed heights below 0 m.
By the user's decision of 2026-11-16 heights below -1 m are no data on the island sheets only (those whose top edge
lies at or below y -90 000 in zone IX: 3 254 of the table's 18 891; the mainland's southernmost sheet ends at
-55 500, Oshima's northernmost starts at -132 900); the eastern wards' real land down to -4.42 m stays. At Mikurajima
(33.886, 139.585, radius 800 m, 2026-11-16) 47 of 310 lines had both anchors on the sea's 0 m fill across the seabed;
with the floor 263 lines in 20 spots are left, the same lines with the same clearances, none with an anchor on the
fill (R92). An earlier count there (341 lines, 49 false, 292 left; wave 1, its options not recorded) was not
reproduced. Left behind: seabed between -1 and 0 m stays in the data, and floored pixels outside the search's sea
zone are filled from the fallback model (the section above).

## Hong Kong's heights: HKPD lowered by 1.30 m

`hong_kong`'s data are heights above the Hong Kong Principal Datum; LandsD's explanatory notes (read 2026-11-16): "the
mean sea level is about 1.30m above HKPD". By the user's decision of 2026-11-16 every height of both models is lowered
by 1.30 m where the tiles are read onto the grid (`Layer.height_offset`; the cache keeps CEDD's values). R91's 8
lines are the same, each anchor 1.30 m lower. At Cape D'Aguilar (radius 400 m) the same 8 lines stay, with 1 988
anchors fewer (26 075 to 24 087). What changes at a shore: data in the search's sea zone at most 1.0 m high count as
water (`filling.SEA_LEVEL_TOLERANCE`), which is now 2.30 m above HKPD, the rule every source has at mean sea level:
in that circle the water with data went from 1 328 to 15 071 px (the data's own water fringe at +1.1 to +1.3 m above
HKPD is 877 of them), so low shore land within the 20 m shore buffer counts as water there, as it does elsewhere.
The 1.30 m is the Lands Department's round figure for 1997-2015, not a geoid. No floor: real land below -1 m exists in
Kowloon (down to about -6 m among heights of 5-6 m).

## Bremerhaven's surface model: shifted half a pixel, and constant planes

Read 2026-11-16 (batch 6): Bremerhaven's DOM1 lies on whole metres, half a pixel off its own terrain (x.5). By the
user's decision of 2026-11-16 it is shifted (+0.5, +0.5) m onto the terrain's grid and copied, not interpolated
(`TransformFix.shift`): heights stay as measured, objects lie up to 0.7 m off their place. The direction is a
convention, not a measurement: against the city's own DGM1 on seven tiles (four of them full) no shift led by more
than 1.7 % of the RMS on the full ones; the rows (y 0..999) settle +0.5 m north, the columns (x 0..1000) only by
reading a file's first point as its kilometre's south-west corner. Each tile keeps its own kilometre only (the files'
shared edge column differs between neighbours: a median of 0.29-1.81 m on three pairs), so a tile without an east
neighbour (18 of the 114, read from the directory) leaves the 1 m beyond its east edge without surface.
`tools/check_source.py`'s files check takes the shift from the layer's fix and names it in its line: a wrong shift
passes it. The 41 partial tiles hold 402 ha of exactly constant planes of 1 ha or more, 245 ha of them beyond the
Land; inside it 23.85 m over 13 ha (468_5937) and 88.14 m over 2.5 ha (469_5935) in the port and on the Weser: left as
they are, a known finding (the user's decision of 2026-11-16; the source's note says so).

## Coastal regression entries on the Copernicus fallback

A coastal entry whose search cannot reach Overpass for the coastline takes the Copernicus water body mask (its log
says "Coastline: Copernicus water body mask (fallback)") and gives another checksum. In batch 6 the first baselines of
R85 (158 lines against 1 002 on OSM) and R86 (7 052 against 7 184) were written on the fallback and re-baselined on
2026-11-16; R87 failed once the same way and passed on the rerun. `tests/regression.py --update` stores such a run
without a word. A guard (refuse or warn when the log names the fallback) was proposed to the user as a separate
small change; not built.

## Searches in Shizuoka and Hong Kong download a lot

Measured in batch 6 (2026-11-15/16): a 400 m search in Shizuoka's west reads 25 whole sheets, 453 MB, and an index
tile not cached yet lists for about 20 s; a 600 m search in Hong Kong reads 24 sheets, 137 MB, in over 6 minutes
(0.36 MB/s). The providers publish whole sheet ZIPs only; nothing is changed.

## Line volume, the store and the access mark: known and left (2026-11-16)

Found in the reviews of the line-volume task's round 3 (store waves 1-2 and the access mark), none fixed:
- **Compare says "· no lines" for a store it refuses or cannot read** (a store of a newer format, a body too large,
  a server error): the run has lines. The result page and `map.html` show the right text; Compare does not. Needs a
  store format that does not exist yet, or a server error.
- **Nothing cleans an orphan "running" tiled folder**: a tiled run interrupted and never resumed keeps its work
  folder, for example a run interrupted under one choice of the access mark (marked or left out) whose search then
  runs under the other. As for any interrupted tiled run whose hash never returns.
- **Whether a wide search is marked depends on the memory free when it starts** (the command line and the local
  app): the same search may carry the access mark on one day and not on another. R83, the regression entry with
  `--access`, would fail its `access_ends` on a PC too short of memory for its grid (not seen).
- **Without a test:** the disk estimate of a search whose mark was left out; Compare of a run without the mark
  (left out) with a marked run (read as correct).
- **The search form shows an estimate's notes only as a count** ("1 warning(s)"); the note that the anchors' access
  will not be marked reads in the receipt.

## Line volume, round 4: known and left (2026-11-17)

Found in the reviews and test runs of round 4 (the view's columns, the exports with the Download buttons, the store
read by share links, the result view behind `?view=b`), none fixed:
- **R48 differs on `main`** since before round 4: 1 252 lines and 39 spots against the baseline's 1 541 and 44
  (sha256 985a5cb3…), with every tile from the cache and no fallback. Its source keeps the newest survey per 1 km
  tile (survey years 2022-2025), so a newer survey of some tiles since the baseline is the likely cause (a guess, not
  checked). Needs a look at the tiles' survey years, then a re-baseline.
- **R56, R87 and R70 not confirmed** after the view's columns and the exports (the user: "7. a", the merges did not
  wait): Overpass answered 502, so R56 and R87 ran on the Copernicus fallback ("Coastal regression entries on the
  Copernicus fallback", above: R56's `water_lines` 3 427 → 3 423, R87 784 → 772 lines); basisdata.nl did not answer,
  so R70 did not run. R80 and R85 were right on `main` with the OSM coastline. Run the three again when the services
  answer.
- **A refused request counts against every rate of its list** (`web.within_rate`, every kind, older than round 4):
  the limiter takes a permit from each rate before it decides, so after many refusals inside one minute the hour's
  rate is used up too, while the refusal's text asks to wait a minute.
- **Three tests fail now and then under a loaded full pytest, each passing alone:**
  `tests/test_cdd_fetch.py::test_when_the_failing_step_comes_through_its_waits_restart` (waits [30, 60, 120, 240]
  instead of [30, 60, 30, 30]: the fake server's reset came as a ConnectionResetError before the headers) and
  `tests/test_cdd_fetch.py::test_a_login_page_broken_after_its_headers_is_a_failed_attempt` (the same fake server's
  reset racing under load); `tests/test_web.py::test_quick_lane` (`sqlite3.OperationalError: disk I/O error` at
  `PRAGMA journal_mode=WAL` while the app shut down, right after the test killed the quick lane's process; also seen
  on `main` alone: "`test_quick_lane` fails at some times" above). Run them alone before calling a failure of one a
  regression.
- **Exports:** a real iPhone was not tried (only Playwright's WebKit profile); a worker that stops keeps a file made
  just before on disk until it starts again (the file is never sent after the hour); a failure that comes while
  another menu is open shows only at the menu's next opening; a signed-in user whose session ended while the page
  was open gets the general failure text on a press.
- **The store read by share links:** an old run without a store, opened by a share link or outside the page's list,
  makes two small 404 requests before `data.js` (in the logs' 4xx counts; until store wave 4 removes such runs). On
  a run's own `map.html` Compare's list of other runs stays as first loaded until a reload.
- **The result view** (behind `?view=b`): its controls under 44 px on a phone and its text under 12 px against
  docs/DESIGN.md R1 and R2 (the level buttons 42 px high, Best's select 29, "Legend" 30, "Back to Auto" 18.8, the
  chips 36, the column heads' 10.5 px, the shapes' text 8.7 px), left to step 3c by the user ("2. a"); the design
  review's other findings are step 3c's list in docs/roadmap.md. Not run: a real phone, presses in WebKit or
  Firefox; the focus rules are tested in Chromium only.

## Line volume, round 5 (store wave 4): known and left (2026-11-18)

Found in the reviews and checks of store wave 4's first deploy (`main` 1b1f2f15, a0c511ac, a86b86e8), none fixed:
- **R70 has never run with a store, and R17 not on wave 4's code:** basisdata.nl did not answer since round 3 (the
  user: "3. a", the merges did not wait); Overpass answered 502/504 in both of round 5's passes, so R17 (the Malta
  extract against Overpass: no run's files involved) was skipped. Run both when the services answer.
- **Compare's list of other runs goes stale from Home on:** Home's mini maps load the list of runs (`runs.js`, once
  per page) for every run card, so a run finished in the same tab is not offered by Compare until a reload (it opens
  and draws through the store's probe); before, the same happened from the first opened result.
- **Two more cdd_fetch tests race on the CI's runners** (the same fake server as the two above):
  `test_fetch_resumes_and_records_every_file` on Linux in both runs since 74de19ae (CI 44170732371 and 44243858723:
  the fake's concurrent connections 2, not 1; read only: the fake counts a request as active until its handler
  returns, after the client may already have read the answer and sent the next) and, on 74de19ae,
  `test_a_file_whose_body_always_breaks_fails_and_the_rest_come` (waits [30, 30, 60, 60] on Windows).
- **The CI's view3d ring job timed out again** (`test_view3d_ring.py::test_ring_drawn_within_its_budget[full-None]`
  and `[full-edges]`, Edge stopped after 1 500 s, on 74de19ae and a86b86e8): the Windows 3D hang seen since
  CI 43618907225, nothing of store wave 4 in its path.
- **Four tests failed once under round 5's loaded full runs on this PC and pass alone** (none in item 5's path; the
  first two passed 3 of 3 alone on the stack and on `main` a86b86e8): `test_web::test_basic_form_sea_cliffs_fills_the_limit`
  (twice; the limit's box and the map view's read before it differ by about 400 m north to south);
  `test_shell_c_download::test_ready_file_is_saved[iphone]` (the GeoJSON row's press waited 30 s for a stable button,
  WebKit); `test_tuscany::test_catalogue_source` (`src.SOURCES` with tuscany after tinitaly);
  `test_window_groups::test_a_layer_in_another_crs_fails[1000]` (it read a file in EPSG:32620, as
  `test_netherlands` serves at the same path `/files/other.tif`; read only: GDAL's `/vsicurl/` cache of a worker
  process keyed on the URL, when a later test's local server gets the same port).
- **`tools/perf_country.py` decodes all 29 columns of a store** (`linestore.read`) though it uses 10: about 350 B a
  line at its peak plus the Arrow table, so a machine smaller than the one that made a very large run may not read it
  back; a column selection in `linestore.read` would cut it.
- **`runs remove-old`:** two removals finishing the same `runs/_removing-<id>` at once may report it "Left on disk"
  although it is gone (cosmetic); the first scan's folder sizes run under the runs lock; a search cancelled or killed
  while "saving results" leaves a folder without `run.json` that nothing removes (older than store wave 4), as does a
  tiled search stopped part-way (its `tiles/` and `progress.json` "running": the server kept 7 such folders, the
  user's "2. a").
- **A bundle that does not load at all over http** leaves the disk notice of a run's `map.html` shown, as the
  specification asks ("in the HTML, so it shows without the bundle"); a `map.html` written before store wave 4 has no
  notice of its own, so from disk without the bundle it stays blank.
- **Wave 4's second deploy:** a `runs/_viewer/index.css` installed before stays there (`install_viewer` adds files and
  never deletes; nothing loads it); a run's `map.html` whose store cannot be loaded shows one sentence and no way back
  to the app (as before wave 4; roadmap "Later").

## The UI measuring tools: known and left (2026-11-17)

Found in the reviews of `tools/ui_metrics.py` and `tools/ui_walks.py`, none fixed; none changes a count on today's
pages (checked by the last reviewer against the baseline pass):
- **`--summarise` after a hard kill**: a run killed without a chance to finish leaves a cut last line and no
  `pages-run.json`; the summary then carries no mark of the unfinished pass and exits 0, and in an `--out` folder used
  before it reads the earlier run's `pages-run.json`. A run stopped by an exception or Ctrl+C is marked.
- **A cover is named by the element hit**, so one cover appears under several names in the "covers" list (the open
  coverage card under nine); a cover drawn by one of the control's own ancestors reads "not covered". The counts of
  controls are not affected (covered controls are counted).
- **"In a sentence" is wide for buttons**: a default (inline-block) button in a block beside any letter or digit
  counts as in a sentence (a stepper beside "12" or "m"). No such control exists in the viewer today.
- **`strip_comments` drops characters after a closing tag whose name uses only regular-expression flag letters**
  (`</div>`, `</i>`, `</s>`, `</g>`, `</svg>`, `</dd>` followed by a "/" on the line). No line of the tree is hit.
- **Dense strings per literal** miss JSX text with an apostrophe, the middle lines of a template that spans lines and
  strings with an escaped quote; a line with two literals is listed twice.
- **The walks' guard reads only the favourites**: a run stopped after R4 began but before it saved its favourite
  leaves a folder that passes.
- **One browser per device and theme**; a `browser.close` that raises after a complete pass marks that pass
  unfinished (exit 1).
- **`BASE_CLASSES` is a hand list**: a new base class that ends in a state word is merged into its tag until it is
  added. The containing-block rule does not look at `will-change`, `perspective`, `backdrop-filter`, `container-type`.
- **`c-basic-sea` on the desktop** can time out waiting for the search bar's estimate (once in the baseline pass of
  2026-11-17): the state is then "not measured" and the pass exits 1.

## The Cancelled state on Home: known and left (2026-11-17)

Found in the reviews of the Cancelled state (migration 19, `jobs.removed_at`); none fixed:
- **An administrator's Home shows other users' searches without their mini maps** (a clock instead): a card's mini
  map reads `GET /api/jobs/<id>`, which is `own_job` (the owner only), so another user's job answers 404. Older than
  this change; only administrators see it.
- **A run gone by hand** (deleted on the server, moved away) takes its search off its owner's list with no "removed"
  mark and no time (`Jobs.all` tells it at listing: `run_gone`; the admin page says "run deleted"). The privacy page
  names Remove and Delete…, which mark it; the app removes runs no other way (no retention).
- **Delete… that fails part way** after `run.json` is gone leaves the job unmarked and the run's row, but no card to
  try again from (neither `/api/jobs` nor `/api/runs` lists it). Rare (a file held open, on Windows); older.
- **The Playwright tests of Home** (`test_shell_c_public_remove_and_delete`, `test_shell_c_remove_question_on_phones`)
  skip in CI, which installs only `--group tui`.
- `tests/test_web.py::test_basic_form_on_a_phone` failed once in a parallel run of the affected files and passed
  alone on the same tree; run it alone before calling a failure of it a regression.

## Step 3c, group A (the first-timer's screens): controls left under R2, and what the probes found (2026-11-19)

Group A brought the sign-in page, Home, the search forms, the account, Favourites and the OSM page to DESIGN.md's
rules. One control stays under R2's 44 px on a touch screen (the place map's zoom and "Data coverage" and the
receipt's parts in the phone's unfolded bar were two more until the user's picks of 2026-11-19: DESIGN.md "The
pilot's look", choices 34 to 36):

- **The place's pin** (Leaflet's marker, 25 x 41 px): a mark of the map; it is moved by a tap on the map, the pin
  itself needs no press.

Outside group A, by the kit's sizes and accepted (that page is being replaced by the new result view): on today's
result page on a phone the filter chips are 44 px high and "More filters" stands on a row of its own, so the list
starts about 40 px lower.

With the place map's phone arrangement (choice 34): on a phone held sideways in the narrow frame (667 x 375, a
128 px map) the opened layers' box shows 104 px of its 143 px of rows and scrolls inside; "Data coverage", its last
row, is reached by that scroll. The drawing tools (Advanced, "Area") keep Leaflet-Geoman's own look and 30 px
buttons at the map's bottom right (no `ui_shots` state shows them on a phone; not measured). On a tablet in the
columns with a finger the coverage's own box keeps its 32 px button (the desktop's arrangement: the user picked on
phone frames).

Found by the probes on short screens and left, as on main (not made by the branch; measured on both codes,
`local/ux-design-2026-11-16/3c-a/probes2/tables-compare.md`): on a phone the last rows of a page scroll under the
bottom bar before the page is scrolled (the account's "Sign out", Home's cards); "Stay in Advanced" in the dialog
of going back to Basic is cut on the left on a 390 px phone (5.6 px; 19.6 px on main); the keyboard's ring is cut
where a control stands at the edge of a scrolling column (an input at the form's bottom edge after the focus's
scroll, the map's credits' links by 2 px, the map itself on its right edge): step 3d's item on `scroll-margin`.
The search page's bottom bar is higher in a short mouse window, so the map is that much lower: its receipt's lines
are 24 px there (R2 on a desktop). Measured at 1024 x 480 with the longest receipt: 137 px where main has 115 (89
and 77.5 px with the usual one); on touch screens the bar is within 2 px of main's.

Characters that the rules count and that stay (R9), for the planner: "+ Add a rig" and "+ 2 more settings"
(`basic.add_rig`, `basic.receipt.more`), the multipliers in the rig's window and the size word's help ("x1.6 to
x36 lines", `rig.fx.*`, `basic.size.factors`), the browser's own triangle of the rig window's "More", the stroke
between a path's folders in Favourites, "Open map ›" on the sign-in page's example cards (`web.py`: outside the
viewer).

## A phone on its side at half: an uncertain shore's chip on the status line

On a phone held sideways in the phone's layout (667 x 375) the zoom and the layers stand in the level switch's row
(the user's Q2 a, 2026-11-18). With the sheet at half the map shows 135 px below the top bar, room for two rows of
controls. The shore's chip (195 px; only in a run with an uncertain shore) fits in neither: after the switch, Best,
the zoom and the layers 164 px are left in the first row, and the second holds "Legend", the key's "i" and the
status line, with the scale at its right end. With a level held, the status line's longer sentence ("Area. Held
by you. Back to Auto") reaches under the chip. Measured with the test's stand-in on the test site's run: the
status line at 159-387 x 137-165 px, the chip at 347-542 x 112-156. `test_phone_on_its_side` excepts this pair
by name. Under Auto, and at the low stop, nothing covers another. Found 2026-11-18 (the UX pilot's Q2 probes).
