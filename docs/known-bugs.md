# Known bugs

Open defects that are not a task of their own yet, with what was measured. Remove an entry when it is fixed
(and name the fix's commit in docs/roadmap.md if it mattered).

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
