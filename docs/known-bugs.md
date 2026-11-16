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
- **A share link's page and a run outside the viewer's `runs.js` read `data.js`, not the store.** `/s/runs.js` lists
  no runs, so the page finds no store block there; an administrator who opens another user's run meets the same. No
  value differs; the download is the larger text. It must be solved before the text files end (store wave 4:
  docs/line-volume/spec-store.md 1.10).
- **Compare says "· no lines" for a store it refuses or cannot read** (a store of a newer format, a body too large,
  a server error): the run has lines. The result page and `map.html` show the right text; Compare does not. Needs a
  store format that does not exist yet, or a server error.
- **A run missing from the page's list costs `runs.js` twice**: `map.html` of an unlisted run loads `/runs/runs.js`
  two times before its `data.js`; in the app one fresh `runs.js` per open of such a run. Latency and server work
  only.
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
