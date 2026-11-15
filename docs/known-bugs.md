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

## An unfinished tiled sag job starts over after migration 17

Seen 2026-11-14 (the sag model's fall zone default of 6 m): migration 17 of `jobs.sqlite` writes 3 into stored sag
requests that had no `fall_zone`, and the worker validates it as the float 3.0, while the job's hash of before
(`search._search_hash`) was taken with the default's int 3. The hashes differ, so a tiled sag job of the web app that
was unfinished at the deploy, searched again, starts over instead of resuming from its finished tiles; its results
are the same. Not normalised: that would move the hash of command-line sag searches given `--fall-zone 3`. Only jobs
unfinished at that one deploy are affected.

## A search stopped early by the square rule's check writes no funnel counts for that grid

Seen 2026-11-14 (the line-volume task): when the early check inside the square rule's reducer refuses a search
(the line limit or the memory budget during the pair search), `Plan.funnel` of that grid is not filled, so the job's
`job_funnel` rows lack the line search's counts for it. The refusal itself is right. A fix would add the counts
reached so far before the refusal is raised.

## The truth check has no reason for a known line the square rule dropped

Seen 2026-11-14 in the truth check's pass with `--same-line-square 5` (docs/truth-check.md, "The square rule"):
`tools/truth_analysis.py` gives a known line that no found line matches a reason from the line's tests (clearance,
height difference, a structure as an anchor …); a line whose valid pair was found and then dropped by the square
rule (another line of the same pair of squares kept) fails none of them, so it reads `unexplained` (20 known lines
in that pass). A fix gives such a line its own reason, for example
`square_rule`, found by applying the rule's key to the best valid pair.
