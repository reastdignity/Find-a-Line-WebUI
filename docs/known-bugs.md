# Known bugs

Open defects that are not a task of their own yet, with what was measured. Remove an entry when it is fixed
(and name the fix's commit in docs/roadmap.md if it mattered).

## The phone's sheet moves in steps with a long list

**The symptom**, on an iPhone (Chrome, so WebKit):
- With a spot far down its sector selected, moving the result view's sheet between its stops is jerky, by a drag
  (it follows the finger in steps) and by a tap (it jumps). An example is Gozo's spot 1.409: the tree opens every page
  down to it, about 420 rows.
- Scrolling the list is fluid.
- A spot near the top of its sector (1.2, about 20 rows) and today's page on the same spot's group are fluid.

**What the user's variant checks showed** (2026-11-22, a switch of test variants on the phone, spot 1.409):
- Only fewer rows cured every move: the tree cut to 40 rows a sector, no list, an empty sheet.
- The rows' hidden names (`u-sr`, about four a row, 1 700 in all) taken out cured the drag and a tap down, not a tap
  up.
- The rows positioned again, so their hidden names hang off their rows and not off the sheet's body, was "a bit
  better". That is what shipped.
- Not causes:
  - the scroller's `will-change` layer;
  - the script run at each frame of the move;
  - the sticky column heads and `container-type`;
  - the map under the sheet;
  - the rows' position alone with the layer taken out (as before the scroll fix).
- In headless WebKit with the iPhone profile, a frame that sets a new sheet height took a median of 76-77 ms on 1.409,
  62 ms on 1.2, and 62-66 ms on 1.409 with the hidden names taken out or hanging off their rows. A forced layout alone
  was 1-2 ms for 50 height changes. These are headless numbers (software drawing); the phone is the judge.

**The proper fix, options:**
- **A**, medium, the recommended one: the tree opens only around the selected row, about 60 rows a sector at most,
  with a button to show the earlier spots. The button's words are the user's to choose.
- **B**, high: a virtual list that draws only the rows in sight. Compare the libraries first.
- **C**, medium, partial: one hidden name a row instead of four.

Found at gate 2 of line volume round 6. The shipped mitigation: the rows positioned (the user's variant 41).

## The probe's tiles strategy still asks `Range: bytes=0-0`

`probe._read` (the "tiles" strategy of `IndexedTiles` sources) sends `Range: bytes=0-0`, which the source rules forbid
for new requests (some servers answer it with the whole file or an error). Batch 5's new kinds avoid it (`sheet`:
bytes 0-7; `zipfile`: the first KB without a Range). Found 2026-11-15 by agents AU and IT; not changed.

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
  asserts "2 checked, 1 failed": under load the fast source misses the 0.5 s too. Failed in batch 5 runs (agent CE)
  and twice on CI's Windows runners (2026-11-14, 2026-11-17). Since 2026-11-23 its timeout is 2 s (the user's
  choice: the number is the test's setting; the slow source's 3 s still never fit). The quick lane's 0.5 s above
  stays: it says how promptly the app answers.

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

**Found on 2026-11-23: it is the app's, on Windows, not the test's.** Alone on `main` b1434458 it failed 5 of 46
runs with "disk I/O error"; in the three of them whose errors were recorded by name (six errors) it was SQLite's
extended code `SQLITE_IOERR_TRUNCATE` at a new connection's `PRAGMA journal_mode=WAL` (in `quick_take`,
`quick_forget` and the scheduler's `interrupted`, the last right after `kill_tree` and `join`): at the moment the
scheduler kills the quick lane's process for a task over its time, not at the app's end as such. The likely
mechanism (read from the error's name and SQLite's code for Windows, not shown): a connection that finds itself the
only one resets the database's shared-memory file (`jobs.sqlite-shm`), and Windows refuses that while the process
going away still has the file mapped. Shown with sqlite3 alone, no code of the repository: after the kill of a
process holding 600 MB the error came in 16 of 60, 9 of 40 and 15 of 60 rounds, up to 149 ms after the kill; after
the kill of one holding nothing in 0 of 60 rounds once and 3 of 60 another time; processes of 3 000 and 8 000 MB gave
none in 16 and 8 rounds (so the size does not decide it simply); none in 240 rounds once the pragma was tried again.
`cache.wal` now tries a connection's opening again after that one error (six pauses, 1.6 s in all; any other error
is raised at once; the pauses run in the web's thread pool for most calls, on the event loop where the web calls the
queue directly: `web.quick`'s `quick_forget` on its error path, the app's end with `scheduler.stop()`, `osm_job`).
With `Jobs._db` under the same kill: jobs.py as it was (`main` b1434458) 2 of 80 rounds with the error, with the
retry 0 of 80; the test alone 0 of 40 runs. **Every database opened in WAL mode has it** (the user's "try it", 2026-11-24): jobs.sqlite,
accounts.sqlite, audit.sqlite and a country's manifest through `cache.wal`; the cache's index (`cache._connect`) and
the test lock's queue (`tools/test_lock.py`, the retry written out: it imports nothing of the checkout) in their own
loops; `tests/test_web.py::test_no_module_switches_a_database_to_wal_on_its_own` keeps it so. At those two openings
the kill gave the error in 2 of 400 rounds each with `main`'s code and in 0 of 400 with the change: the error is
there, but too rare in this experiment for these counts to show that the wait removes it; that rests on each
opening's test and on the 240 rounds above.

## Two jobs added in one second could draw the same id (mended 2026-11-23)

`tests/test_web.py::test_status_events_in_the_order_of_the_changes` failed once (a full run of the USA's 1 m task,
2026-11-23) with `sqlite3.IntegrityError: UNIQUE constraint failed: jobs.id` in `jobs.add`: a job's id is its second
and six hex digits, and the test adds 150 jobs at once (about 1 run in 1 500 by the count of pairs). `Jobs.add` now
draws again while the id is taken (`test_a_job_whose_id_is_taken_gets_another`). The cause is read from the id's
form; no run of the old code was made to fail on it.

## `test_rclone_stderr_never_printed` failed when run at 22:22 UTC (mended 2026-11-23)

`tests/test_mirror_publish.py::test_rclone_stderr_never_printed` looks for five words of rclone's stderr in the tool's
output, the port "2222" among them, and the tool prints the trash folder's name at unpublish, with its time stamp:
in CI 45277159653 (Windows, 2026-11-23 22:22:01 UTC) that was `madeira-20261123T222201Z`, and the test failed with
nothing of the stderr printed. Any stamp with "2222" in it does that, about 100 seconds of a day. The test now holds
the stamp (`mirror_publish._stamp`, as `test_a_move_never_lands_on_an_existing_target` does); with the tool's clock
at that moment the test as it was fails and the new one passes.

## The download window's interval and a row without its cells (mended 2026-11-23)

Tests of `tests/test_area_download_tui.py` failed now and then with `NoMatches: No nodes match '.state' on
AreaRow(...)`: two tests once each on CI's Windows runners (2026-11-18) and
`test_a_continent_without_rows_has_no_group` in a full run here (2026-11-23), each passing alone; two more had
failed on CI on 2026-11-14 with the same error for '#summary', mended since (`Downloads._static`). The stack is the
window's own: its 2 s interval (`refresh_states`) called `AreaRow.show` on a row whose cells were gone, as widgets are
while the window closes; `Downloads._static` and `refresh_summary` already allowed for that, `AreaRow.show` did not,
so a window closed at such a moment ended with a traceback too. `AreaRow.show` now keeps the state and shows nothing
when the row has no cells (`test_a_row_without_its_cells_takes_a_state_quietly`; on a row never mounted the tool as
it was raises NoMatches, the new one returns).

## Two searches saved at once on Windows: one can fail reading the other's run.json

`tests/test_web.py::test_two_jobs_computing_at_once` failed once on CI's Windows runner (run 45285547602,
2026-11-23): one of its two jobs ended "failed" with `PermissionError: [Errno 13] Permission denied:
...\runs\<the other job's run>\run.json` at the `open` of `runs.list_runs`, called by `runs.write_index` at the end
of `search.save_run`. The trace shows no more than that refusal; the rest of the account is read from the code. The
listing runs under `cache.runs_lock`; the other slot's `runs.save_results` writes its run.json outside it
(`cache.replacing`: a temporary file moved to the name, the run's one write of it), so a listing can meet the file
at the moment it appears; the failed job's own run was saved by then (`write_index` comes after it in `save_run`).
If so, it is the app's, on Windows with two compute slots, not the test's. Shown on this PC (2026-11-24) with
`cache.replacing` in one process and `list_runs`' two steps (`os.path.isfile`, then `open`) in another that waits
for the file, two runs of 3 000 new files each: the open was refused 2 425 times in the first; in the second, which
also counted the files, 3 337 times at 1 816 of the files, each of them read on a later try, 7 ms after its first
refusal at the median and 29 ms at the longest; the writer was never refused. With one file replaced in place:
1 184 and 1 263 opens refused, and 1 697 and 1 621 of the writer's 3 000 moves. What holds the new file for those
milliseconds is not established (the move's own handle, opened for deleting, which Python's `open` does not share;
or a scanner opening a new file; the PC was loaded by other sessions' runs). `list_runs` is also what the web's
lists of runs call (`web.py`), without the lock. Not mended: a change of `runs.py` waits for the user's word. A red
`test_two_jobs_computing_at_once` on Windows with this error is this.

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

## Regression entries not checked: R70 and R17 (2026-11-24)

On the real cache every other entry is `ok` (92 of 94 on 2026-11-24, R48 after its re-baseline that day). The entries that differed "on `main`" in
rounds 4 and 5 of the line-volume task differed on fresh caches only: R56 and R87 on the Copernicus coastline
fallback (now `unverified`, and `--update` refuses such a run: docs/regression-tests.md), R48 because its provider
had replaced the survey of 2022 (re-baselined on the survey of 2026).
- **R70 (Sint Eustatius) has not run since 2026-11-15, and never with a store.** basisdata.nl blocks a development
  network since then (after about 18 parallel window reads per island at 4 connections; confirmed a block, not an
  outage, on 2026-11-23), and the real cache holds none of its blocks (its one pass was on a scratch cache). It runs
  again when Het Waterschapshuis frees the address (a mail asks; the user's decision of 2026-11-23: wait for the
  answer) or its 12 blocks are fetched through another network. The islands' files are read through our own ranges
  since 2026-11-24 (one connection, 54 requests a minute): that path has not met the real host yet.
- **R17 (the Malta extract against Overpass) has not completed since 2026-11-14.** Overpass answered 502 or 504 to
  nearly every try (55 skips of 68 runs seen in November). Its differences of 2026-10-27 and 2026-11-01 were OSM
  edits made after the extract; the three since the extract's update of 2026-11-07 were never traced to features.
  It now prints the ids that differ and writes `differences.json`. The extract was updated on 2026-11-24 (data of
  2026-11-23, 221 cliffs) and the run after it was skipped (502). It is out of `--all` since 2026-11-24
  (`"by_name": true`; the user's decision of that day, before the diagnosis: 12 Overpass queries and a standing skip
  in every full run), so it runs only by name or with `--set network`. Still owed: one run by name, at most once a
  day, until Overpass answers; then either its counts are stored again (OSM edits) or the two readers differ (a
  fault). Its stored counts (93 coastline features, 217 cliffs) are those of the extract before the update.

## Searches in Shizuoka and Hong Kong download a lot

Measured in batch 6 (2026-11-15/16): a 400 m search in Shizuoka's west reads 25 whole sheets, 453 MB, and an index
tile not cached yet lists for about 20 s; a 600 m search in Hong Kong reads 24 sheets, 137 MB, in over 6 minutes
(0.36 MB/s). The providers publish whole sheet ZIPs only; nothing is changed.

## A block's order can change while its name stays (two cases left open by the key rule)

A block's name holds what decides the order of its files only where a list file ties another on its year
(`versions.block_key`, wave A of the USA, part A-2, fix round 3). Two changes of order keep the name, so a cached
block stays composed in the order of before until its set of files or newest year changes:
- (1) A file of the list of unlisted files whose year changes, in any way that leaves it untied before and after:
  inside the list (a year taken from the project's listed siblings once they are listed), or when the index starts
  to list it with another year (a project whose folders name no year takes its publication year: 49 of the 1,410
  files of the shipped list of 2026-11-22 are of that kind, `counts.year_from_siblings`). The scene: files A of 2020,
  B of 2016 and U of 2018 from the list; the index lists U with 2015: the order changes (U after B) and the name
  does not (the third code review ran `block_key`: `d276e9a7` both ways; also when U's new year ties B, as no file
  is marked once U is listed). Two grids can see U from the list and from the index at the same time under one
  name; whichever composes first stays.
- (2) Older than wave A and on every layer: a listed file whose date the index changes while its name stays (a
  project published again): it can swap two files of one year, and where the year comes from the publication date
  (no year in the folders) it can move past files of other years.
Cost: the overlap pixels of the files in such blocks, until the block is read again. Not changed.

## Two views of one square name its block differently, and a reader can find its block pruned

Two processes whose views of one square differ (answers of different ages over a newly published file, or one
tile's answer lacking a file the other's holds while the list carries it, wave A part A-2) compose its block under
two names; each pass prunes the other's name. A reader between its download and its mosaic can then find its block
gone (`Layer.files` drops a path that no longer exists): the hole is filled from the fall-back for that run (the
third code review: a B-only reader's mosaic NaN in 1296 of 1296 pixels before the fall-back), and a country tile
counted then keeps it in the cube. It needs two processes in that window (two searches, or country workers whose
tiles share blocks). Without such a reader the two names only flip, one block read per flip. It ends once the
lacking tile is asked (a renewal over it, `cache update` after 28 days, or the settling of the carried files after
the next listing). Older than this branch in kind (answers of different ages); the carried files add a trigger.
Not changed (a possible remedy: `prune` sparing a block of another name younger than a few minutes).

## An IfSAR block's key can depend on the grid

`ComposedBlocks._blocks` clips each file to the grid's bounds before it finds the blocks a file covers, and Alaska's
IfSAR files are listed with the API's box projected (a little larger than the cell, not a whole number of blocks):
a narrow grid and a wide one can then give the same 1 km square different sets of files, so different keys (the
second code review of wave A part A-2, 2026-11-23, ran `_blocks` directly: narrow grid `6dcd4ce2 [A]`, wide grid
`02775184 [C, A]`). What it costs: the square's block cached twice under two names (one per grid width), each read
once. The 1 m DEM is not affected (its extents are the names' 10 km
squares, which the 1 km blocks divide). Older than wave A; not changed.

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
- **The search form shows an estimate's notes only as a count** ("1 warning", by the count since step 3d G5); the
  note that the anchors' access will not be marked reads in the receipt.

## Line volume, round 4: known and left (2026-11-17)

Found in the reviews and test runs of round 4 (the view's columns, the exports with the Download buttons, the store
read by share links, the result view then behind `?view=b`), none fixed:
- **A refused request counts against every rate of its list** (`web.within_rate`, every kind, older than round 4):
  the limiter takes a permit from each rate before it decides, so after many refusals inside one minute the hour's
  rate is used up too, while the refusal's text asks to wait a minute.
- **Three tests fail now and then under a loaded full pytest, each passing alone:**
  `tests/test_cdd_fetch.py::test_when_the_failing_step_comes_through_its_waits_restart` (waits [30, 60, 120, 240]
  instead of [30, 60, 30, 30]: the fake server's reset came as a ConnectionResetError before the headers) and
  `tests/test_cdd_fetch.py::test_a_login_page_broken_after_its_headers_is_a_failed_attempt` (the same fake server's
  reset racing under load); `tests/test_web.py::test_quick_lane` (found and mended on 2026-11-23: its entry above;
  `sqlite3.OperationalError: disk I/O error` at `PRAGMA journal_mode=WAL`, right after the quick lane's process
  was killed; also seen
  on `main` alone: "`test_quick_lane` fails at some times" above). Run them alone before calling a failure of one a
  regression. **The two cdd_fetch tests' cause was found on 2026-11-23** (Windows only): the fake reset the connection
  right after its headers and part of a body, and Windows drops what a socket received and nobody read yet when the
  reset arrives, so a client reading a moment late met the reset before the headers (on Linux the bytes are read
  first either way; shown with two sockets on both systems). The fake now waits 0.3 s before a reset (`Fake.reset`
  of `tests/test_cdd_fetch.py`): a pause, not a proof, so a much slower client can still lose. The action
  `slowreset` keeps its own reset without the pause: it sends its half body a piece every 10 ms, so the headers are
  long read.
- **Exports:** a real iPhone was not tried (only Playwright's WebKit profile); a worker that stops keeps a file made
  just before on disk until it starts again (the file is never sent after the hour); a failure that comes while
  another menu is open shows only at the menu's next opening; a signed-in user whose session ended while the page
  was open gets the general failure text on a press.
- **The store read by share links:** an old run without a store, opened by a share link or outside the page's list,
  makes two small 404 requests before `data.js` (in the logs' 4xx counts; until store wave 4 removes such runs). On
  a run's own `map.html` Compare's list of other runs stays as first loaded until a reload.
- **The result view** (then behind `?view=b`): its controls under 44 px on a phone and its text under 12 px against
  docs/DESIGN.md R1 and R2 (the level buttons 42 px high, Best's select 29, "Legend" 30, "Back to Auto" 18.8, the
  chips 36, the column heads' 10.5 px, the shapes' text 8.7 px), left to step 3c by the user ("2. a"); the design
  review's other findings are step 3c's list in docs/roadmap.md. Not run: a real phone, presses in WebKit or
  Firefox; the focus rules are tested in Chromium only. **Brought to R1 and R2 in round 6** (2026-11-22) in the
  states `tools/ui_shots.py` measures: no text under 12 px outside the credits, no control under the bound in the
  first view or with a line. The filter editor and More filters, which no state measures, are not; what is left is in
  "Line volume, round 6" below.

## Line volume, round 5 (store wave 4): known and left (2026-11-18)

Found in the reviews and checks of store wave 4's first deploy (`main` 1b1f2f15, a0c511ac, a86b86e8), none fixed:
- **Compare's list of other runs goes stale from Home on:** Home's mini maps load the list of runs (`runs.js`, once
  per page) for every run card, so a run finished in the same tab is not offered by Compare until a reload (it opens
  and draws through the store's probe); before, the same happened from the first opened result.
- **Two more cdd_fetch tests race on the CI's runners** (the same fake server as the two above):
  `test_fetch_resumes_and_records_every_file` on Linux in both runs since 74de19ae (CI 44170732371 and 44243858723:
  the fake's concurrent connections 2, not 1; read only: the fake counts a request as active until its handler
  returns, after the client may already have read the answer and sent the next) and, on 74de19ae,
  `test_a_file_whose_body_always_breaks_fails_and_the_rest_come` (waits [30, 30, 60, 60] on Windows). The Windows
  one is the reset race of round 4's entry above (the fake's pause, 2026-11-23). The Linux one failed in all four
  runs of `main` on 2026-11-17/18 and in none of the three jobs of 2026-11-23, with the test unchanged (another
  runner image, 20261116, and one more step in the job since). Since 2026-11-23 the fake counts a request out just
  before the bytes that complete its answer go out (`Fake.send`, `Fake.answered`), no longer when its handler
  returns: with a handler made 50 ms slow to return the test failed at `fake.most == 1` 3 times of 3 on the old
  count and passed 3 of 3 on the new one. What that costs: a second request is no longer counted when it arrives
  while those bytes are written (for a 200 its whole body), or after a 200's headers and before its body was read;
  two requests at once are seen only while the fake works on the first. And only the answers of `Fake.send` are
  counted out so: after a reset, a body sent in pieces or without its length, or a close without an answer, a
  request is counted out when its handler returns, as before, so a later test asserting `most` over such an answer
  would race as this one did.
- **The CI's view3d ring job timed out again** (`test_view3d_ring.py::test_ring_drawn_within_its_budget[full-None]`
  and `[full-edges]`, Edge stopped after 1 500 s, on 74de19ae and a86b86e8): the Windows 3D hang seen since
  CI 43618907225, nothing of store wave 4 in its path. Read on 2026-11-23 from the last 60 CI runs: the ring job
  was red in 7 of the 9 runs of `main` since 2026-11-14 (in 1 of 6 runs of `history/*` tags; no cause known for the
  difference). `main` b1434458 (57 min, red) and its tag's run (6.7 min, green) started two seconds apart on the
  same runner image (windows-2025-vs2026 20261116.315.1): the three Edge tests took 523, 1 355 and over 1 500 s
  against 75, 105 and 166 s, while the fixture's search (no browser) took 37 s in the red job and 49 s in the green
  one. So on some runners only Edge's WebGL in software is slow, not the machine as a whole (three jobs read; not
  even within a job: on 263b1268 `[full-edges]` took 327 s while `[full-None]` ran into 1 500 s). ci.yml's limits
  (1 500 s, 60 min) were set from the slow kind. Since 2026-11-23 the two 3D jobs print, before their tests, the
  runner's CPU and memory, Edge's version, and what Edge draws WebGL with and how fast (ci.yml's step "Runner and
  Edge", `.github/webgl-report.html`: on the dev PC the Microsoft Basic Render Driver through Direct3D 11, 10 frames
  in 130 ms): compare that line between a fast and a slow job before anything else. The step's failure does not
  fail the job, but its time counts against the job's limit: an Edge that has not ended after 15 s is stopped, so it
  costs a few seconds, about 40 s at most. **The lines of the first six jobs** (2026-11-23 and 24, CI runs
  45277159653, 45330246504, 45335814910; one runner image, the Microsoft Basic Render Driver, 2 cores, 4 threads and
  16 GB in all six): four jobs on AMD EPYC 7763 drew the 10 frames in 974 to 986 ms and passed (the ring in 18 and
  22 min, view3d in 10 and 16 min); one on AMD EPYC 9V45 in 664 and 666 ms (view3d in 7.5 min); and the one red job,
  the ring's of 45335814910 (`[phone-None]` 1 463 s, `[full-None]` over its 1 500 s, the job stopped at 60 min), on
  Intel Xeon Platinum 8573C in 1 076 and 1 122 ms. So the first slow job with the line ran on another CPU, where
  the ten frames were only a tenth slower while `[full-None]` ran over its 1 500 s against 114 and 187 s in the two
  green ring jobs, and `[phone-None]` 1 463 s against 220 and 904 s: the line's frame time does not show the
  slowness, the CPU's name may. But the two green ring jobs, both on the EPYC 7763, differ four times in a test
  themselves (`[phone-None]` 220 and 904 s, `[full-edges]` 702 and 186 s), so the CPU is a lead and no more. One
  red job: an observation, not a cause. The next red and green lines say whether every slow job is on that CPU
  (then: what the ring's page asks of Edge's software WebGL that the ten frames, a loop per pixel without a texture,
  do not).
- **Four tests failed once under round 5's loaded full runs on this PC and pass alone** (none in item 5's path; the
  first two passed 3 of 3 alone on the stack and on `main` a86b86e8): `test_web::test_basic_form_sea_cliffs_fills_the_limit`
  (twice; the limit's box and the map view's read before it differ by about 400 m north to south);
  `test_shell_c_download::test_ready_file_is_saved[iphone]` (the GeoJSON row's press waited 30 s for a stable button,
  WebKit); `test_tuscany::test_catalogue_source` (`src.SOURCES` with tuscany after tinitaly);
  `test_window_groups::test_a_layer_in_another_crs_fails[1000]` (it read a file in EPSG:32620, as
  `test_netherlands` serves at the same path `/files/other.tif`; read only: GDAL's `/vsicurl/` cache of a worker
  process keyed on the URL, when a later test's local server gets the same port). **The last two are found and
  mended (2026-11-23):** `test_tuscany`'s fails in every process that ran `tests/test_regions.py` before it: that
  file's fixture `without_regional` took the regional sources out with `monkeypatch.delitem`, whose undo puts each
  back at the end of the dict for the rest of the process; the fixture now puts the catalogue in its order again, and
  the file's last test checks it. `test_window_groups`'s was GDAL's cache as guessed: with every test server on one
  port, `tests/test_netherlands.py` and then the three `test_a_layer_in_another_crs_fails` in one process failed
  3 of 3 with "other is in EPSG:32620"; the test server now drops its files from GDAL's cache when it closes
  (`HttpServer.close` of tests/http_server.py, `rasterio.cache.invalidate`), the same run passes, and
  `test_a_later_server_on_the_same_port_serves_its_own_file` holds it.
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

## Line volume, round 6 (the result view as the default): known and left (2026-11-22)

Found in round 6's reviews, gates and the user's iPhone checks (the result view's step 3c, then step 3d and its flip
to the default); none fixed. The phone sheet's jerky move with a long list has its own entry at the top of this file.

**Safari and WebKit**
- **Safari's console shows one CSP line per dropdown**: "Refused to apply a stylesheet because its hash, its nonce,
  or 'unsafe-inline' does not appear in the style-src directive", once for every `<select>` a page makes (today's
  page one, the view two, Home too). It is WebKit's own bug 327212: an inline style on the button slot of the
  select's user-agent shadow tree, refused under `style-src 'self'` even on a bare page with one parsed `<select>`;
  the select is drawn the same, Edge reports nothing. No code of ours; the user, 2026-11-22: "Leave it, known bug".
  `tests/test_view_gate2.py::test_no_style_refused_in_webkit` allows exactly that message, one per `<select>`, while
  a bare `<select>` in the same WebKit is refused too, and nothing else.
- **WebKit reports "ResizeObserver loop completed with undelivered notifications."** as a page error at every change
  of the view's sheet stop (Playwright's iPhone 13; also without round 6's code, and on every run of the LAN test). A
  WebKit test of the view filters that one message.
- **WebKit lets a desktop list kept at 260 px overflow sideways by 2 px** (`scrollWidth` 261 against 259; Edge 259,
  and 372 px clean in both; C4's code review of gate 2's round: negligible).
- **`MediaQueryList.addEventListener` is missing in Safari before 14** and would throw in round 6's effect that uses
  it (read only, C4's code review); the other new rules of the round degrade gracefully in old browsers.
- **Safari on a Mac froze once while a run's line loaded** (the user, 2026-11-22; the Develop menu froze too). Not
  reproduced: on the Gozo run (717 044 lines) the view's main thread stalls about 0.8 s after the store arrives in
  desktop WebKit (about 80 ms of it redraws that could be saved) and about 0.2 s on the iPhone profile, against
  today's page's 1.6 s; the memory peak 1.07 GB against today's 1.50 GB. Look again if it recurs.

**What the design checks left** (the final design check and gate 2's, 2026-11-22; none breaks a user answer)
- **R2's leftovers**: a set filter chip's label button (19-20 px high) and its × (16 × 16 px) on every device: the kit's
  chip (the measured profile's number fields are 24 px high since step 3d G6).
- **The map's switch, Best and its "i" come after the nine credits links in the Tab order** (the switch stands at the
  map's top, the credits at its foot).
- **The sector's name scrolls away while its heads stick** (the design review's G2-F3): in a sector of 59 spots the
  rigger loses which sector the heads belong to.
- **Two word patterns and one icon for two steppers**: the spot's ‹ › in the head and the line's ‹ › share an icon
  (told apart by names and places); "Previous spot / Next spot" beside "The line before / The next line". With the
  tree smallest first, a sector's head still says "mean height up to …" while its first row is its smallest.
- **"Grouping the lines…"** shows while the view loads, whose model groups nothing (`model.ts buildModel`).
- **The screenshot gate's answers** (2026-11-21): (G-A a) on a 390 x 664 phone at half with a level held and both
  coast chips, the coarser chip wraps under the zoom row and hides the status line's count sentence and its "Back to
  Auto" (measured 2026-11-20: chip [8,172,219,216], status [8,200,281,248], "Back to Auto" from y 209; CSS px); Auto,
  the low stop, the Pixel's 412 x 839 and one chip alone are clear (`CHIPS_HALF_HELD` in `test_phone_chips` and
  `test_phone_controls_apart`). (G-D a) at 1024 x 768 with both coast boxes and a line selected the card opens (the
  map, 712 px, is above `LIMITS.low` as on today's page) and the shore box [328,187,617,303] covers the status line
  [328,221,529,249], the hint [328,257,627,289], "Legend" [328,297,419,329] and the "i" [427,297,459,329]; the
  coarser box [328,311,587,373] covers "Legend", the "i" and the scale [328,337,428,367]; folded by the person,
  nothing covers anything. Accepted, not a bug (G-C a): an opened coast box may cover the status line, "Legend", the
  "i" and "Back to Auto" until it is closed (on 390 x 664 at half the coarser box [8,172,248,252] and the shore box
  [8,172,248,259]). The phone held sideways (P c): the entry "A phone on its side at half" below.
- **A measured line on 390 x 664 at half**: never shorter than 120 px on the screen; a link's line at the run's centre
  is 126 px with its lower end under the "i"'s ring, 5 px right of the button (both chips shown), 124 px outside the
  run; on 412 x 839 both ends clear.

**The frame's moves** (the code reviews of B3 and C4; low risk, each read or probed)
- A selection the person did not press (a filter moving it to another line of the spot, the line stepper) can pull
  the map back over the person's pan; it ends with an end clear.
- A selected line given one end clear at the phone's low stop loses it when the person raises the sheet to half (the
  rest check acts only on a line with both anchors in sight); a press made in the same task as a sheet move gets no
  step; the measured line's next-frame step does not check again that the same line is still shown (read only, very
  unlikely); rare: the one-end step after the sheet's bring-back, or during a glide, can move the map in the middle
  of a gesture.
- An anchor's 18 px access icon can lie about half under a chip while its point, label and ring are clear (the rule
  counts the point; counting the icon would mean about 11 px more pan).
- A measured end lying wholly inside a number's box is not drawn (the numbers' clip); a first Measure point pressed on
  a number shows nothing until the second.
- A desktop list kept at 260 px on a touch screen cuts the Length values (280 px, or a mouse, are fine).
- P3's drop (a selection at full): a sheet held by its handle during the drop counts as resting; `footAbove` is stale
  after a rotation or a resize at full (only the drop's fit padding); a bring-back pan still animating when a drop
  starts counts as the person's move, so that drop's rest moves nothing; the first selection's "fit moved the map"
  flag carries to a later selection in the same drop (one extra end check).
- "Lines from A1" pressed with the phone's sheet at full zooms the hidden map out (16.75 to 15.5 on 390 px, 17.25 to
  15.5 on 412); the same before round 6's last fixes.
- At full the phone pill's own shadow is drawn faintly over the sheet's rounded top edge (cosmetic).
- **A selection's check can move an end off the map** (seen by step 3d G6, 2026-11-23; round 6's code, not G6's):
  `endsClear` (SpotColumns.tsx) counts an end that leaves the map as not under a control, and ranks "fewer under"
  before "fewer outside". At 1024 × 768 with the card open (the map 361 px wide, the coast boxes run), lines 5858 and
  6308 of `test_selection_check_moves_only_for_a_gain[1024-card]` start with both ends under the shore box and the
  hint. The check then pans so that one end is still under a control and the other lies off the map: x 441 on main
  (263b1268), x 409 on G6's tree. The test counts that as a gain (one end fewer under a control).
- The sideways notice's media query also matches a phone held upright whose page an on-screen keyboard shrinks in
  some Android browsers (not iOS Safari, not Chrome on Android).

**Loading a run** (gate 2's store retry, `result/load.ts`)
- Leaving a run right after the retry starts still downloads its whole store again.
- `navigator.onLine` can turn true before the phone's network link really carries traffic (a tunnel coming back), so
  the retry may still fail at once; then "Reload the page" as before.
- The 3D stage's `user-select: none` (the long press's fix) also makes the profile card's, the info box's and the
  credits' text unselectable on the desktop (one CSS line restores them if wanted).

**Tests and tools**
- **Flaky under a loaded parallel full run, each passing 3 of 3 alone:**
  `test_shell_c_view_map.py::test_landscape_phone_columns_fold_the_legend` (opening the page timed out once; another
  time the status against the zoom at 852 x 393), `test_view_link.py::test_sheet_moves` (the iPhone in WebKit),
  `test_shell_c_view_map.py::test_phone_controls_apart`, `test_lan_app.py::test_smoke_over_https`,
  `test_view_frame.py::test_measured_points_lie_under_the_numbers[412]`,
  `test_access_view.py::test_legend_lists_the_three_marks`, `test_shell_c_flows.py::test_shell_c_intros`. Run them
  alone before calling a failure a regression.
- `test_view_gaps.py::test_no_page_zoom_outside_the_map`'s double-tap step tests nothing in Chromium (its pinch step
  does).
- `test_store_share.py` (and `test_thumb_store.py`) still check that `runs.js` is asked at most once by the browser's
  resource-timing entries, which miss a second load of the same address in one page; `test_view_parity_pages.py`
  counts the requests sent (`page.on("request")`) since round 6's closing fixes.
- **`tools/lan_app.py`** (the LAN test of gate 2): `make_clip` has no test. While it serves, the local app's other routes stay open on the network (an estimate, a place's lookup,
  deleting a search or a run of the scratch folder, the rigs and the admin routes).

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
- **`ui_metrics.py` has no `--run`** (`ui_shots.py` has): the result view's five coast states, which need a coastal
  run, are not measured (line volume's round 6).

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
rules. On a phone one control stays under R2's 44 px (the place map's zoom and "Data coverage", the receipt's
parts in the phone's unfolded bar and the drawing tools were more until the user's picks of 2026-11-19: DESIGN.md
"The pilot's look", choices 34 to 36); on a touch tablet, which keeps the desktop's arrangement, also the drawing
tools (30 px; the coverage's own button, 32 px as drawn, has an invisible 44 px target since step 3d: DESIGN.md
row 83):

- **The place's pin** (Leaflet's marker, 25 x 41 px): a mark of the map; it is moved by a tap on the map, the pin
  itself needs no press.

Outside group A, by the kit's sizes and accepted (that page is being replaced by the new result view): on today's
result page on a phone the filter chips are 44 px high and "More filters" stands on a row of its own, so the list
starts about 40 px lower.

With the place map's phone arrangement (choice 34): on a phone held sideways in the narrow frame (667 x 375, a
128 px map) the opened layers' box ends 4 px above the credits and shows 90 px of its 143 px of rows (two rows;
measured): it scrolls inside, and "Data coverage", its last row, is reached by that scroll; the list ends in the
middle of a row (66 px), so that more is seen to be there. The drawing tools (Advanced, "Area") stand in one row
beside the zoom on a phone, 44 px each (as Geoman's column under the zoom two lay over the scale and the credits
at 390 x 664 and three under the map held sideways; on main all five were above the map's top); at 844 x 390 the
row's last tool ends where the layers' button begins (0 px between them, no overlap), and on a map narrower than
338 px the row wraps under the zoom (measured at 360 x 640: the last three tools on a second row; there a drawing
tool's actions, which open under the first row, lie over the last of them by 36 x 40 px, and the polygon's three
actions reach 10 px past the map's right edge). The tools are links without a name for a screen reader
(Leaflet-Geoman's own markup: axe `link-name`, 5 nodes, in the new `ui_shots` state `c-new-area`; the same
markup on main). On a tablet in the columns with a finger the coverage's own box keeps its
32 px button (with a 44 px target since step 3d) and the tools Geoman's 30 px column (the desktop's arrangement: the
user picked on phone frames; the tools wait for line volume's round 6); a tap
on the coverage button while the layers' box is open closes the box and misses the button, which moves 56 px down
as the box (rows of 44 px now) closes: the second tap takes. An earlier note here, that the layers' box does not
open while the tools are shown, was the test harness's doing (the emulated mouse left over the Advanced tab makes
Leaflet close the box on a late mouseout; with taps only it opens, on main too: `3c-a/probes-r5`).

The layers' box and the keyboard (measured 2026-11-19): mended in step 3d G6 (DESIGN.md row 132): Escape closes the
box, Enter or Space opens it with the focus on its chosen row, a second tap where the button stood no longer switches
the base map. Kept by the user's decisions of 2026-11-23: on a desktop the Tab order in the map's corner is coverage,
layers, zoom, their order on the screen from the top ("a: screen order"; WCAG 2.4.3 asks for that order); the
tools' 30 px column on a touch tablet ("a: leave, in known-bugs": five buttons one under another leave no room for
invisible 44 px targets that do not overlap, so 44 px would be visible). The tools have names since G6 (axe
`link-name`: 0).
The coverage's 83 outlines are out of the Tab order since DESIGN.md row 81.

The about page's long address ("ARSO's terms of use of its lidar data: http://...", plain text in a credit's notice)
ran wider than its box on a phone: fixed by group D (DESIGN.md choice 53).

Found by the probes on short screens and left, as on main (not made by the branch; measured on both codes,
`local/ux-design-2026-11-16/3c-a/probes2/tables-compare.md`): on a phone the last rows of a page scroll under the
bottom bar before the page is scrolled (the account's "Sign out", Home's cards). Step 3d measured it again: at the
end of the page's scroll no row rests under the bar (the iPhone, the Pixel and 360 px; the page's bottom padding is
the bar's height), before it a row lies there as on any page longer than the screen, which padding cannot change;
a focused control or a card's panel scrolled into view stops above the bar (DESIGN.md row 81). "Stay in Advanced"
(cut at 390 px) and the rings cut at a scrolling column's edge or the map's credits were mended by step 3d
(DESIGN.md rows 81 and 83); the map's own ring, on its right edge, waits for line volume's round 6 (`PlaceMap.ts`).
In Playwright's WebKit (Safari's engine) a text or number field that Tab focuses at a scroll box's foot is scrolled in
only to about 12 px above its own foot (the kit's scroll-margin aside; why is not traced: perhaps the caret's line),
so the search form's fields at the column's foot kept 11.8 to 15.7 px and their ring below it, at every size (the
iPhone, an iPad's 1024 px, the desktop's 1400 px); 24 px of `scroll-padding-bottom` on the column while a field that
takes text has the focus mends it, and no other scroll there moves (step 3d's fix round, DESIGN.md row 81: `test_webkit_fields_whole_at_the_column_foot`). Another scroll box with fields at its foot
would need the same. In Advanced the goal cards' arrows move the focus only and Space or Enter chooses (the planner,
2026-11-21, DESIGN.md row 82): before, an arrow from "Custom" applied a goal's values over the user's own; a click on a
card still does, with no way back to the own values but to type them again (`useSearch.ts` `applyPreset`).
The search page's bottom bar is higher in a short mouse window, so the map is that much lower: its receipt's lines
are 24 px there (R2 on a desktop). Measured at 1024 x 480 with the longest receipt: 137 px where main has 115 (89
and 77.5 px with the usual one); on touch screens the bar is within 2 px of main's.

Characters that the rules count and that stay (R9): the browser's own triangle of the rig window's "More", the
stroke between a path's folders in Favourites ("Open map ›" on the sign-in page's example cards was one until group
D: DESIGN.md choice 55). "+ Add a rig", "+ 2 more settings" and the multipliers of the rig's window and the size
word's help are written out since step 3d G5 (DESIGN.md choice 92).

## Step 3c, group D (admin, privacy, about): known and left (2026-11-19)

- **axe's `skip-link` on the admin page** (3 nodes on `c-admin` in every device and theme, axe's example
  `.c-report-context > a`; measured 0 on `c-admin-end`, the same page scrolled to its end): a false
  finding. With the `ui_shots` data the page has three hash links, all routes of the app, not anchors: a run's
  "Open" and a problem report's run link (`#run=<id>`, `AdminC.tsx` `runHash`) and "OpenStreetMap extracts"
  (`#osm`); axe's best-practice rule reads such a link as a same-page link to an element that does not exist. The
  same on the base before group D.
- **"All searches" with content is not in `tools/ui_shots.py`**: the tool's site has no job (a job would show on
  the administrator's Home too and change that page's pictures). Group D pictured it with a probe in a folder of its
  own (`local/ux-design-2026-11-16/3c-d/probes/`, three finished searches; its rows hold only a status chip and
  kit buttons). The probe also gave the pending user a session: three buttons in one row on a phone, the checkbox on
  its own line under them (DESIGN.md choice 50).
- **The admin page's texts** moved into `locales/en.json` in step 3d (group G4, `ui.admin.*`; its plurals by the
  catalogue's forms). A problem report's context line reads "page: …; interface: …; window: …" since step 3d G5
  (labelled values, parts joined by "; " as the run's link holds a comma); it still wraps to 2 lines on a 390 px phone
  and 3 at 360 px.
- **Left on the admin page, inherited** (the design review's F6): a wrapped ghost "End sessions" set in by its
  padding. The solid-accent badges, "Open" with its arrow before the word and the page's title the size of its
  section titles were mended in step 3d G3 (DESIGN.md rows 98, 99).
- **The about page shows "<year of the run>" literally**: not a credit's own text. A credit names the year of the run
  as `sources.YEAR` ("{year}"); where no run exists, the about page fills it with `sources.credit.YEAR_TEXT` (web.py
  `about_page`, `src.dated(..., src.YEAR_TEXT)`): deliberate, left.

## Step 3c, group B (the 3D view): left, inherited, and what the probes found (2026-11-19)

Group B brought the 3D view of a line to DESIGN.md's rules with its layout kept (rows 40 to 49). Left as it is:

- **Inherited from the profile chart** (`Profile.tsx`, `profile.css`: shared with today's result page and line
  volume's round 6, not changed here): the card's facts joined by " · ", "→" and "Δh" (R9) were put in words by step 3d
  G6 (DESIGN.md row 136). Its text at 11 px and
  the controls of "Rigging and layers" under 44 px on a touch screen were mended by line volume's round 6 (the user's
  12 a: the chart's text 12 px, every control of the profile 44 px on touch, on both pages and the 3D card;
  DESIGN.md row 104).
- **The phone's three layout questions** were answered on a mock-up and built (DESIGN.md rows 37 to 39: the bar in
  one row held sideways, the card stepping aside, the notes behind "About this view" with the safety sentence kept
  in the bar). What they leave, measured after the fix round of 2026-11-20 (`local/ux-design-2026-11-16/3c-b/fixes/`: `tip/`,
  `probe-misc/`, `probe-pointcard/`):
  - Held sideways the open card covers most of the stage and scrolls inside (165 of 244 px shown at 844 x 390, 150
    of 244 px at 667 x 375; the mock-up's extra option A2 was not picked).
  - Held sideways at 844 x 390 the data credits start open, as everywhere from 768 px (the user, 2026-11-20: "Open
    as before", and after the design review's second look "Keep open, as you chose"): 560 x 139 px of the stage's
    844 x 233 px (60 % of its height) until they are folded, over the found line and its pin
    (`local/ux-design-2026-11-16/3c-b/fixes2/corner-1/S844-loaded.png`).
  - The list of "Lines from a point" (the full level on a phone: by its address only) keeps its least height of
    80 px. With the card open it lies over the credits' box by 34 px at 390 x 664 and is left with its head and
    21 px of its first row (`probe-pointcard/point-upright-list-card.png`); held sideways it lies over the card by
    72 px (`point-sideways-list-card.png`), where it lay before too.
  - On a touch screen 601 to under 620 px wide with the one row (held sideways, or a tablet's window at the phone
    level) the row wraps in the athlete's views (measured at 610 x 360: the bar 159.6 px there, 115.6 px in the
    orbit; at 601 and 610 x 900: 140.1 and 96.1 px; one row, 96.1 px, at 620 and 640 px).
  - A strip with its labels still lies over a card that reaches it (the card steps aside of a strip of icons only,
    row 38): a touch tablet at `?level=full` (1024 x 600: four tools over the card,
    `probe-misc/T1024full-card.png`) and a short desktop window (1280 x 500: four tools,
    `probe-misc/D1280short-card.png`; 844 x 390: the strip in two columns, three tools over the card,
    `probe-misc/D844short-card.png`).
  - The phone level's bar with words, since 2026-11-20 only the desktop's `?level=phone` (a mouse: a touch tablet
    has the one row of row 37, the user's "C: the one-row bar of a phone held sideways"), is longer than the window
    in the athlete's views in a narrower window, as on main. Measured 2026-11-20 (the tests' clip,
    `local/ux-design-2026-11-16/3c-b/fixes2/row-1/`): at 844 x 390 "Edges" stands outside with two kinds of
    imagery, three kinds with four and the speed under "Satellite (Esri)"; at 1024 x 600 "Edges" outside with four
    kinds.
  - At 360 px of width the title is cut to 97 of its 115 px ("3D view of a…") between the two buttons (its 20 px
    of row 46).
  - On the narrower card beside the strip (the chart 298 px against 350 px) the chart's own labels "min.
    clearance" and "highest … above terrain" stood on touching lines (`Profile.tsx`: inherited; since line volume's
    round 6 its labels are laid out 2 px apart at 12 px, `LABEL_BOXES`, so this is mended unless a picture shows it again;
    `local/ux-design-2026-11-16/3c-b-review/design/mock/sheets/390x664-s2A-five-tools-card-light__chromium-390x664-full-card-light.png`).
  - While "About this view" is open, the credits' box, its button with it, is hidden where the box would overlap it
    (the design review's P9) until the box is closed ("Close", Escape, a press beside it, Tab or, since step 3d,
    Shift+Tab out of it); where the credits stand clear above it (above an open card) they stay, with the pressed
    button.
  - A fan dot near the stage's edge keeps its whole 44 px target (`screen.ts` `targetInside`: on the Pixel of
    `ui_shots` the 312 m line's dot stood 19 px off the right edge, which cut its target to 41.4 px); the labels of
    other lines and the anchors' handles too since step 3d (DESIGN.md row 84). A mark whose own drawn box the edge
    cuts keeps a cut target (no target can cover it and stay inside).
- **An anchor's handle jumped at the first move of a drag on a phone**, mended by step 3d (DESIGN.md row 84): the
  first edit makes the bar 44 px higher ("Back to the found line" appears and the readout gains "Moved, not saved"),
  which made the stage 44 px lower under the finger and put the handle 24 px off it ((11.4, -21.1) px at anchor 1 on
  the Pixel, `local/ux-design-2026-11-16/3c-b/fixes/probe-drag-before/drag.json`; the cause measured by
  `3c-b-review/code-review-r2.md`). While handles are dragged (a count: two fingers hold it till the last release)
  the bar gets neither higher nor lower and its new row waits for the release; after it the bar gets no lower until
  the new profile is in (`edit.ts` `holdBar`, `releaseBar`, `settled`): the handle stays under the finger (0.1 px on
  the Pixel, 0.2 px in WebKit's iPhone at the first 1 px), nothing of the bar leaves the window, and a later release
  that leaves the readout as it was changes no size (`test_view3d_handle_stays_under_the_finger`,
  `test_view3d_two_fingers_hold_the_bar`). Left, as the planner chose: at the first release the bar's row appears, the
  stage gets 44 px lower (on the iPhone once more when the profile's line comes in) and the handles move with the
  scene. A turn of the window during a drag keeps the bar's old height until the new profile is in; Escape does not end a drag
  (as on main). A press on the rim of the handle's 44 px target adds no offset
  (`test_view3d_handle_drag_keeps_its_offset`).
- **The marks' targets** (row 43) take presses from the stage: in "Lines from a point" on a phone the targets cover
  3.3 to 5.1 % of the stage (6.5 % sideways), where a press reaches a dot or a handle instead of the terrain (orbit,
  pinch, a new point). Where a fan's dot stands on an anchor's handle (the found line's other end among the
  representatives) the dot, drawn later, takes the press, as before. Two labels closer than 44 px share part of
  their targets (31.9 px apart in `ui_shots`' "view3d-others" on an iPhone): a press on a label's own drawn box is
  that label's, and where only the targets overlap the nearer centre wins. The two
  handles' targets overlap only when the anchors stand under 44 px apart on the screen (the camera far out): there
  anchor 2's, drawn later, takes the press. Dots under the list or the open credits stay under them (as before).
- **Measured from states the tools do not have**: the imagery notice is made by a script in the probes (the clip's
  run has no orthophoto and the probes run without an Esri key), its words the catalogue's.

## A phone on its side at half: an uncertain shore's chip on the status line

On a phone held sideways in the phone's layout (667 x 375) the zoom and the layers stand in the level switch's row
(the user's Q2 a, 2026-11-18). With the sheet at half the map shows 135 px below the top bar, room for two rows of
controls. The shore's chip (195 px; only in a run with an uncertain shore) fits in neither: after the switch, Best,
the zoom and the layers 164 px are left in the first row, and the second holds "Legend", the key's "i" and the
status line, with the scale at its right end. With a level held, the status line's longer sentence ("Area. Held
by you. Back to Auto") reaches under the chip. Measured with the test's stand-in on the test site's run: the
status line at 159-387 x 137-165 px, the chip at 347-542 x 112-156. `test_phone_on_its_side` excepts this pair
by name. Under Auto nothing covers another. Found 2026-11-18 (the UX pilot's Q2 probes).

Measured again 2026-11-20: the status line at 159-387 x 141-169 px, its "Back to Auto" target 294-375 x 133-177, the
chip at 347-542 x 112-156. Since round 6's words (W1: "Kept while you zoom.", longer than "Held by you.") the pair
shows at the low stop too ("Back to Auto" wraps under the chip: back [340.6,133,422.2,177], chip [347,112,541.7,156]);
the user's P c of 2026-11-20 keeps it a known bug, and the test excepts the pair at both stops. The cause: MapBar's
`inline` is measured once per state and never checked again once the foot stands in a row; a fix tried in round 6
(end the row left of the control it still reaches, the status on two lines) was not taken. The coarser terrain's
chip (DESIGN.md row 105) ends at x 558 and the scale starts at 559 (the sheet low): no longer over the scale. Since
gate 2 (the user's 4 a) a touch phone held sideways sees the notice to turn it upright over this layout (DESIGN.md
row 127), so the pair lies behind the notice there.

## Step 3c, group C (the coverage page, the highline layer): what is left, and what the probes found (2026-11-20)

Group C brought the coverage page and the layer explorer to DESIGN.md's rules with the user's seven picks and, after
its reviews, five answers more ("The pilot's look", choices 60 to 77). Measured after (`tools/ui_metrics.py pages`):
no text under 12 px outside a map's credits and scale; no control under the bound on the desktop; on the phones the
layer's chart bars only (excepted by name in R2). Known and left:

- **The stars in the images and videos**: `coverage/draw/layout.ts` writes "★★★ Best" as text for the canvas, so the
  images and videos of `tools/coverage_*.py` keep the character while the page draws its stars (the user's pick,
  2026-11-19: the page first).
- **A star not reached and a filled one are close in lightness** (1.37:1 light, 1.33:1 dark): the price of the
  grey that holds 3:1 on every ground (the user's pick, 2026-11-20; DESIGN.md, choice 63). The hue and the mark's
  name ("2/3") tell them apart.
- **The legend's "≤ 1 m", the charts' ticks, "0.6 × 0.9 km"** and the texts over R10's limits (the coverage page's
  `page.lead`, the layer's notes): written out and shortened in step 3d G5 (DESIGN.md choices 92 and 93). The images
  and videos keep "≤ 1 m" with their stars (`coverage/draw/layout.ts`, left for now).
- **axe's `skip-link` on the layer's selected cell** (3 nodes): its "Search here" links are hash links
  (`#new&cell=…`), which the rule takes for skip links to a missing target. A false finding.
- **The chart rule's range**: `c.css` holds a rule per count of bars from 1 to 24 (32 px a bar); a chart of more
  bars would show no counts at any width. On a phone an enlarged chart is at most the screen's width less 32 px, so
  it shows its counts up to 10 bars at 360 px of width (328 px of chart) and up to 11 at 390 px (358 px); today's
  cubes have 6, 7 and 9 bars. The charts' text was built and checked on the test cube only, not on a real cube's
  numbers (docs/roadmap.md, "The page's readability on a real cube").
- **The coverage page's zoom buttons at 360 px of width** wrap onto two rows (96 px over the map), in English and
  Polish; at 390 px they hold one row.
- **A touch tablet and a phone held sideways at 768 px or more keep the desktop's arrangement** of the layer: a
  collapsed panel's rail is 36 px wide there (under 44 px in one direction), as in the result view; the panels'
  collapse tab, 24 x 44 px as drawn, has an invisible 44 px target since step 3d (DESIGN.md row 83; the result
  view's tab waits for line volume's round 6). On the layer page's map the coverage box's right edge stands under
  the right panel's splitter (24 px wide on a touch screen): a tap on the box's last 2 px reaches the splitter
  (measured at 1024 x 768 and 1180 x 820, before and after step 3d). On the coverage page at 844 x 390 a card opened
  from the map is taller than what is left of the screen and scrolls inside.
- **A collapsed panel's rail**: the tab at its middle lies over a long label ("Charts: 62 M lines in view" at
  390 px of height), as before.
- **On a phone's strip the small charts stand bottom-aligned beside the enlarged one**, which leaves a blank band
  above their names (the build's `align-items: flex-end`, as before).
- **Inherited and left** (the design review's F10): on the coverage map a selected country stays drawn above its
  regions after its card closes (`flat.ts`); the map's shapes take no keyboard focus (every card is reached from
  the list). The switches take the arrows since step 3d (DESIGN.md row 82).
- **The layer's map and the keyboard's ring** (the design review's F10, inherited): mended in step 3d G6 for the
  place map of all three pages and the result view's map (DESIGN.md row 136): an outline 2 px inside the box, only
  after a key (a press marks the box: `layersControl.ts` `pressMarks`).
- **`test_layer_page_in_edge`'s cut step** picks the cut cell whose two parts are deepest: with the panels' new widths
  the map in headless Edge's window is 425 x 649 px (360 before) and the first lattice points of the first cut cell
  lay 3 px apart at the shared edge. Its points lie 2 px inside their parts, so another change of the map's size may
  need new points.
- **The scrolls of a row's press on a wide screen** (to the map, and back on closing) are eased unless the system
  asks for reduced motion; the tests run with reduced motion, so the eased scroll itself is untested.

## Step 3d, group G1 (keyboard, focus and touch): known and left (2026-11-21)

Found by the reviews of G1 and left (DESIGN.md rows 81 to 84 hold what was mended):

- **The layer page on a phone**: with the column scrolled to 500 px a press on the sticky map scrolls it to 222 px
  (Leaflet focuses its container on a press, and the column's `scroll-padding-top` of the map's height brings the
  focused map's top under itself); as on main.
- **The 3D view on a desktop**: a Tab focus on another line's label that lies off the stage scrolls the marks' layer
  (`.v3-overlay`, `overflow: hidden`) by 787 to 904 px, which moves every mark off its point until the next frame; as
  on main.
- **Today's result page takes the kit's new rules** (the focus's `scroll-margin`, the credits' inside ring and its
  room, the forced-colours outline): keyboard only; none of its pictures changed (the whole `ui_shots` set compared).
- **A press on a coverage outline** now leaves the focus on the map in every engine (its default prevented: WebKit as
  on main). In Chromium it focused the outline on main (its tooltip then stayed after a tap, the arrows did not pan
  after a click); keeping that in Chromium alone would need the engine told apart. In WebKit's iPhone profile at its
  own 390 x 664 a tap on an outline now moves the search point and keeps the outline's tooltip open, where on main it
  did neither (at 1024 x 900 both builds behave alike): taken as an improvement, left.
- **The layer's strip on a phone**: a chart's name focused by Tab comes into view whole; on the Pixel 7 one of the 16
  names still has 4 px of its ring past the window's edge (none on the iPhone).
- **The arrows choose in every radio group but the goal cards** (WAI-ARIA's pattern, the planner's decision): each
  arrow on the 3D view's imagery starts that imagery's tiles (Esri's with the key), each on the layer's "Cells",
  "Count" or "Lines across the border" a recount (30 to 46 requests in 9 to 12 presses on the sample cubes), and one on
  the coverage page's "EN" switches the page to Polish.
- **The coverage page's brand link on a phone**: its ring's top 4 px lie above the window (the header at the top of
  the page); as before.
- **The map credits' ring and the credits' brackets**: the ring is clear of its link's own letters (no pixel under it
  at device scale 1 and 2, light and dark), and a "p"'s descender ends on the pixel row above its bottom side (the map's
  edge leaves no more room). Where a bracket adjoins the link with no space, "(report a map issue)" and "(CC-BY-SA)",
  the ring's side lies on that "(" or ")": a 2 px side between them needs room the line does not have without moving
  (judged acceptable by the design review; a 1 px side ring would be the cheapest remedy).
- Firefox was not run (by the code: a coverage outline was never focusable there, and a press keeps the map's focus).

## Step 3d, group G2 (tokens and scales): known and left (2026-11-21)

G2 put the free CSS's layers, shadows, type and radius steps, spacing and colours on the tokens and scales (DESIGN.md
rows 87 to 91; `tests/test_viewer.py::test_free_css_on_the_scales` and its `OFF_THE_SCALES`). Left:

- **The drawings drawn as shadows** (16 declarations: the accent's rings, inset edges, the 3D view's marks' rims and
  shadows, the sheet head's scroll cue) stay literal, named with their reasons: the planner's decision of three
  elevation tokens does not cover them; tokens for a ring, an inset edge and a mark's rim are the planner's to decide.
  The 3D marks' values differ a little (an edge of 55, 60 and 65 % black; the pin's shadow offset turned against its
  rotation, so that it falls straight down).
- **Today's result page's files** (`result.css`, `columns.css`, `ui/sidepanel.css`) stay outside the scale test (its
  page goes); the parts the result view borrows were put on the kit in G6 and `columns.css` on the layers' names.
  Round 6's own files and the shore block are checked since G6 (DESIGN.md rows 134, 135).
- **The kit's demo pages** (`?ui=kit`, `?ui=kit-search`: the gallery's rules, `.u-stub`, `.ui.s-kit`) keep their own
  type, corners and spacing (developers' pages); their layers are tokens.
- **The dialogs' scrim** has its value twice, the token and `::backdrop`'s fallback (a browser before Safari 17.4,
  Chrome 122 and Firefox 120 gives `::backdrop` no custom property); a test keeps them the same.
- **The page's 13 px on html** (`app/base.css`) stays written out: no token reaches html and body, and Leaflet's rem
  sizes (the map's credits before R1's rules) come from it.
- **One legend** (DESIGN.md row 90): the coverage page's legend keeps one item a line (the picture's); the kit
  alone would pair its items where two fit. Its swatches (16 x 12 px, an inset edge) and the list's (22 x 14 px, a
  `--line` border) are two sizes for one level: left by the user's "Leave for now (Recommended)", 2026-11-22 (the
  design review's F4). The access mark's help panel, 28 px higher (13 px type, R7's padding), is cut by 37 px at
  rest in the result view's key on the iPhone (round 6's `.v-over`, 277 px high; 9 px before); it scrolls and reads
  whole: room for it in `.v-over` was offered to G6 as T3 and left by the user (2026-11-23). The result view's and the
  profile's legends are on the kit's since G6 (DESIGN.md row 133).

## Step 3d, group G3 (one control family): known and left (2026-11-22)

G3 put the free screens' text actions, rows, closes, badges and checkboxes on the kit's (DESIGN.md rows 96 to 99;
`tests/test_controls_kit.py`). Left:

- **The kit's rules reach round 6's view and today's result page** where they use the kit's classes: the "More
  filters" count badge is neutral there too (Q8 a: the accent only for the bottom bar's count), "How to read the
  result" (`ui/Intro.tsx`, the kit's text action) takes a label's weight, today's page's tab the kit's look and its ring.
- **"The account" of C6**: stage 1's note named the account's title, but the h1 of `Account.tsx` is `MapPage`'s (the OSM
  page's and the layer explorer's titles); the account page's "Account" is a Panel's title. "24 px, every page" was built
  on every page's h1 (Admin, Home's searches, the OSM page, the layer explorer) and, after the reviews (the user,
  "Yes, every page 24 px"), on the account's and Favourites' Panel titles (`Panel`'s `page`) and New search's title.
- **"How to read the result" is 44 px high on a touch screen** wherever the kit's text action stands (the user,
  2026-11-22: "Keep the 44 px target"): on today's result page on the Pixel the list starts 25 to 28 px lower than
  before; round 6's view takes the same where it shows the intro's link.
- **The admin page on an iPhone at load**: the 24 px title puts the waiting user's "Approve" and "Block…" partly under
  the bottom bar in the first screen (ui_metrics' "covered" 1 -> 3 a theme); they scroll into view; the operator's page,
  accepted by the design review (F2).
- **The coverage page's table**: its countries' names are the kit's text action, 500 and not underlined at rest (they
  were the row header's 600 and underlined): Q7 a's look for a standalone action.
- **The close mark** still marks the search form's Clear and the cancelled status chip (no sheet or answer moved them).
- **Hooks kept for tests and ui_shots**: `n-intro-link`, `cov-link`, `cov-name-link`, `s-reset`, `c-menu-item`,
  `c-fav-star`, `c-fav-open`, `c-tree-name`, `s-more-head`, `s-rig-item`, `c-layer-hist-name`, `c-account-btn`, `cov-x`,
  `v3-activity-dismiss`, `v3-infobox-close`, `c-check`, `s-check`, `c-user-*`: each beside the kit's class, with no look
  of its own but its place or size. Two rows keep a difference from the kit's row under the mouse: a favourite's line
  (its words take the accent, no fill) and a chart's name (no fill), as before.

## Step 3d, group G5 (the words): what stays (2026-11-21)

G5 built the words the user approved on the wording review (DESIGN.md choices 92 to 95; `local/ux-design-2026-11-16/
3d/g5/`). Left, by the user's answers or as named:

- **Today's result page** keeps its intro (`intro.result.spots` 80 words, `filters` 48, `check` 38: over R10) and its
  "→" (`intro.result.easy_within`, `spots`), and its filter bar's ≥ and ≤ in code (`result/view/FilterBar.tsx`): the
  page goes with line volume's round 6 (the user, 2026-11-19). `tests/test_words.py` names them.
- **The profile's 1:1 scale** keeps "×1.6" (the user's answer to G6's w-04, 2026-11-23: as the 3D view's "×1").
- **The images and videos of the coverage map** keep "≤ 1 m" and the stars' character (`coverage/draw/layout.ts`):
  rendered by hand and rarely (the user, 2026-11-19).
- **The layer's small charts on a phone** show their title on two lines where the word the bare ticks need
  ("(at least)", "(under)", "(up to)") does not fit one (inside the title's 44 px target: `.ui.c-narrow
  .c-layer-hist-name`); the desktop's two-a-row charts keep one line.
- **A browser that put the search's intro away before** keeps its `findaline.intro.search` in localStorage, unused
  since the intro opens from its link only (no migration: nothing reads it).
- **The coverage legend at 360 px** shows "Very detailed" and its tag "up to 1 m" on two lines (one line on 390 px and
  wider; "≤ 1 m" fit beside the name): the legend one line taller, nothing cut.
- **`ui_metrics.py pages` counts three more covered controls** on the iPhone's "c-layer-chart" (67 -> 70 in the
  family), traced by the design review (`local/ux-design-2026-11-16/3d/g5-review/design-review.md`): the same three
  chart names lie under the bottom bar at both commits; at the tip a 0.17 px sliver of them shows above the column's
  edge (the shorter notes above move them 0.84 px up), so the tool counts them. Not a rise.

## Step 3d, group G4 (the texts into the catalogue): what stays in code, and why (2026-11-20)

G4 moved the English of the app's pages, the kit, the side panels and web.py's sign-in, examples, area total, about
page and footer into `locales/en.json`, word for word (DESIGN.md choice 85; `tests/test_texts_in_catalogue.py`).
What still shows English from the code:

- **Python texts outside web.py's moved pages**, not counted by step 3d's scope and not moved (each needs its own way
  into the catalogue, a code as the coded errors have): the job's progress line on Home's cards ("Tile 3/15 · Step
  3/5: evaluating anchor pairs", the search's progress through the worker's events, `useJobs.ts` `step`), a job's
  messages and an error without a code (its str()), the examples' settings line on the sign-in page
  (`runs.params_summary`), web.py's HTTP errors without a code ("no such sign-in", "too many sign-in attempts:
  try again later"), and the coverage page's shell (`web.COVERAGE_HTML`: its title "Data coverage · Find-a-Line", its
  description and its noscript line; the page's own words are `locales/coverage/`).
- **The privacy page** (`web.privacy_page`): its words are the user's to approve (the plan); its code is untouched and
  its HTML byte for byte as before (the footer it shares now comes from the catalogue with the same bytes).
- **The kit's demo pages** (`ui/Gallery.tsx`, `search/KitSearch.tsx`, `result/view/KitResult.tsx`): developer pages
  (the plan, Q13 a). **Line volume round 6's files and today's result page's** (`result/view/*`, `Profile.tsx`,
  `result/model.ts`, `list.ts`, …): after round 6, or out. The side panels' labels ("Collapse the …") take the panel's
  name from the caller: the layer page's from the catalogue (`ui.panel.filters`, `ui.panel.histograms`), round 6's
  `ResultColumns.tsx` and `SpotColumns.tsx` pass their side's identifier ("list", "details") as the word.
  `coarser.ts` ("under 0.001", the shares) is shown in round 6's coarser box.
- **Formats and values**: `time.ts`' month names and the numbers' `toLocaleString("en")` (a language would format them
  with `Intl`, not the catalogue); unit symbols.
- **Names and required wording**: Find-a-Line, OpenStreetMap, OpenTopoMap, SRTM, GeoJSON, CSV; Esri's attribution and
  "Powered by Esri" (its terms); the processed-data note (`layers.ts` `PROCESSED_NOTE`, word for word with
  `sources.credit.PROCESSED_NOTE`: `tests/test_catalogue.py`).
- **Developer diagnostics**: the store's reading errors (`result/load.ts`, `types.ts`: written to the console; the
  page shows `ui.result.store_failed`) and the vendored `view3d/martini.ts`.
- **The same words under several keys** ("Cancel" `rig.cancel` and `ui.common.cancel`, "Close" five times, "Remove",
  "Try again", "Auto", "All", "Done"; `local/ux-design-2026-11-16/3d/g4/same-words.md`): a key for each sense, the
  older ones named for their component (the planner's ruling, 2026-11-20). The one-form plurals, the two about
  wordings and "Report a problem…" in the two menus were G5's (closed: DESIGN.md choice 95, step 3d G5).
- **The coverage page's bundle carries the app's catalogue** (before G4 too: `ui/components.tsx` imports `ui/Hint.tsx`,
  which imports `i18n.ts`), so it grows with it: `coverage.js` 435 to 452 KB with G4's 337 keys (main's
  `ui.card.cancelled` went: the kit's key says the same).
- **Text nodes and pixels**: Chromium places a line's glyphs by its text nodes, so the same words in other nodes can
  differ by a shade (seen on the search's "Centre …" line, the mini maps' credit, Admin's user line, and in the
  reviews on Favourites' "Export this folder" and its 0-line delete question). `i18n.parts` keeps a text's values as
  nodes of their own where they were; the pictures of `tools/ui_shots.py`'s states and of the states it has no page for
  (Favourites with rows, menus, "Move to", the delete question with 0, 1 and 2 lines; Admin's "All searches" rows; the
  estimate paused and unavailable; the area file's six errors; the report dialog's kinds; the beta notice; a card's
  Share and Delete panels) are pixel-identical to main's on the desktop, the iPhone and the Pixel but for live map
  tiles and shades of 1/255 on a control's corners that main against main shows too
  (`local/ux-design-2026-11-16/3d/g4/fix/`). Two lines keep the same words with a space in another node than main's
  (the delete question's " and" " ", the trip list's empty line): the same pixels.
- **The map credits' catalogue words go into HTML unescaped** (`baselayers.ts` `osmCredit` and the OpenTopoMap
  credit, `layers.ts` `creditsHtml`: `ui.map.*`, `ui.credits.data`, `ui.credits.notices`), as Leaflet's attribution
  takes HTML; `web.page_text` escapes its texts' &, < and >. No word holds either today; a later word (G5, a language)
  with "&" or "<" needs escaping there.

## Step 3d, group G6 (the themes in round 6's files): known and left (2026-11-23)

G6 put the result view and the place map on the kit's controls, legend, layers, scales and words (DESIGN.md rows 131
to 136; `tests/test_view_kit.py`). Left:

- **Today's result page follows the shared parts** (the user's G6-Q1 a and G6-Q2 a): its closes, text actions,
  checkboxes, More filters' heads, the dock's buttons and the profile's words are the view's now; its own components
  (`FilterBar`'s bar, `LineDetails`, `LinesTable`, `ResultColumns`) keep their English and looks.
- **The drawing tools on a touch tablet** keep Geoman's 30 px column, and the place map's corner keeps the screen's
  Tab order: the user's decisions of 2026-11-23, not open items (group A's entry above).
- **"Data credits" on a phone** (T7): left as it is, the user's decision of 2026-11-23 ("a: leave, in known-bugs"),
  not an open item. A hit test over the folded
  pill's 44 px band (`elementFromPoint`, the fix round of 2026-11-23): at the sheet's low stop and at half a press
  reaches it on 27 px of the 44 on the iPhone (390 x 664) and at 360 px, 35 px on the Pixel: the credits' links of
  the line above take up to 8 px (round 6 put them over the target on purpose) and the sheet's handle under it 9 px.
  In `ui_metrics`' other 12 states a pass (`c-view-sector`, `-report`, `-picker` ...) the sheet stands over the pill:
  none of its band is pressable and none needs to be (hidden). The whole 44 px without moving anything drawn: the
  target moved above the pill (19 px over it, none under it) and laid over the links. Measured: 43 px of the band on
  the three phones (its last half pixel lies under the sheet's edge), but at 360 px the link "report a map issue" lies
  wholly inside it and no press reaches that link; with the target moved but the links kept over it, 43 px where no
  link lies above, 26 px under a link (and 5 px above it).
  Either costs a link's press or needs something drawn to move.
- **The desktop card with "Rigging and layers" open** (the design review's F1, mended by the user's F1 a of
  2026-11-23: the profile's key at 12 px with 12 px gaps, DESIGN.md row 133): the key and the 1:1 scale on one row
  again; the card is 358 px in the view and 361 px on today's page against main's 344 and 345 (the kit's 32 px button and the rigging rows' 24 px fields and 20 px
  boxes). The row fits with 3 px to spare on the card (1 px on today's page, 594 px wide) for a search with the default
  line model ("safety limit (formula)"; `tests/test_view_kit.py::test_card_key_and_scale_on_one_row`). It still takes
  two rows, as on main, with the sag model ("safety limit (sag model)": the legend 409 px, 607 of 596) and with the
  no-fall zone or A-frames (two more items: the legend alone 581 px).
- `LineDetails.tsx` `ordinal` writes the English ordinal ("76th" percentile) in code, and the view shows it (an
  anchor's percentile in a line's details): inherited English, unguarded (`LineDetails.tsx` is today's page's file,
  outside `MOVED`); a catalogue's ordinal needs plural rules per language (i18next's `ordinal`).
- `CoarserNote` joins the fallbacks' names with " and " in code. Today's page's own English the view never shows:
  `FilterBar`'s bar (its chips and "Close the filter") and `ResultNote`'s "Close" (`ResultSummary.tsx`); the guard
  (`tests/test_texts_in_catalogue.py` `MOVED`) covers the parts the view borrows (`MainEditor`, `MoreFilters`,
  `CoarserNote`, `WhyBox`, `AccessLegend`, `ResultSummary`).
- **More filters' heads** differ from their labels by weight and grey only (13 px, 600, `--ink-2` over 13 px, 400,
  `--ink`; the design review's P1): left. No one token mends it: a larger size token (`--fs-3`) would undo T5's
  "the text's 13 px", and `--ink` would take the grey away as well.
- **The access help cut in a phone's `.v-over`** (37 px at rest) and the map's switch after the credits in the Tab
  order: left by the user (T3, T2).
