# Performance of the public site under many jobs

Measured 2026-10-31 on the development PC (12 cores / 24 threads, Windows 11, NTFS, the cache on a
local SSD). The public worker runs in a container with `WORKER_CPUS` (default 3) and
`WORKER_MEMORY` (default 8g). The VPS of findaline.lukawski.org has 8 cores and 24 GB, so its
worker gets 7 cores (`WORKER_CPUS`: the cores minus one) and about 20 GB. "3 cores" and "7 cores"
below are this PC restricted to that many physical cores (CPU affinity and `--threads N`), which is
what `search.line_threads` gives the worker in its container.

The question: one worker runs one job downloading and one computing at a time
(`jobs.Scheduler`, `running` keyed by phase), the quick lane beside them, and claims jobs first in,
first out. What limits it when many people queue jobs?

## How to measure again

| Script | What it does |
| --- | --- |
| `tools/perf_profile.py --out <dir> --name <n> [--cores N] -- <findaline options> --data-dir <scratch>` | Runs a search in its own process, follows the progress bars and samples CPU time and memory every 0.1 s: a table per stage (wall s, CPU s, cores busy, peak memory) and a timeline chart |
| `tools/perf_download.py --out <dir> --osm-from cache/osm --threads 2 4 8 -- <findaline options>` | The download phase (`search.download_data`) on an empty cache (only the OSM themes and Nominatim answers copied), with `sources.layer.DOWNLOAD_THREADS` set |
| `tools/perf_sqlite.py --out <dir> --jobs 1 4 8 16 --pages 30 [--burst]` | `jobs.sqlite` with the real `jobs.Jobs` under K phase processes, the worker, the quick lane and M open pages |
| `tools/perf_profile.py ... --tracemalloc` | The same, with the peak of Python's heap per stage (numpy arrays included, memory-mapped grids not; several times slower) |
| `tools/perf_lines_memory.py --call <capture>/call-<k> --out <dir> [--repo <checkout>]` | A call captured by `tools/perf_line_funnel.py` through steps 3, 4 and 5 by the code of a checkout: the traced heap per line at the peaks of step 3, of step 4's coordinates, groups and profiles, held, and at the peak of step 5 (`search.LINE_BYTES`) |
| `tools/perf_lines_memory.py --tiles <run>/tiles --out <dir> [--repo <checkout> --legacy]` | The tiles of a tiled run joined as `search.search_lines` joins them, and (tile files written before wave 5, which still hold the pixel columns) their lines through steps 4 and 5 by the code of a checkout: bytes per line as found, at the peak of step 4, held, at the peak of step 5 |

The searches ran on cached data (a scratch data folder whose `cache` is a junction to the real one)
with `--ortho never`, one at a time. Their results equal the regression table: R13 566 lines / 143
spots, R9 85 671 / 3 972, Gozo 403 026 / 2 734 (the run of 2026-10-28).

## 1. Cores used by one job

| Job | Size | 24 threads | 7 cores (VPS) | 3 cores | peak memory |
| --- | --- | ---: | ---: | ---: | ---: |
| small: R13 Kasprowy Wierch | 5 m, r 500 m, 566 lines | 1.9 s, 3.5 cores | | 1.7 s, 1.1 cores | 0.2 GB |
| medium: R9 Montserrat | 5 m, r 1 km, 85 671 lines | 15.7 s, 2.3 cores | 15.7 s, 1.5 cores | 16.8 s, 1.2 cores | 1.0 GB |
| large: Gozo coast ±100 m, 1 m | 9.65 km², 6 tiles, 403 026 lines | 129-131 s, 2.3 cores | 125 s, 1.4 cores | 134-135 s, 1.2 cores | 5.6 GB |

(Wall time and the mean number of cores busy.)

(R4, the 1 m Dolina Będkowska, takes 3 s and behaves like R13.) Times are of the search alone; the
worker adds a spawned process per phase (about 1 s of imports each).

**The line search is not the problem.** It is the only parallel code (numba `prange` in
`linesearch.py`) and uses the cores well (21-22 of 24, 3 of 3), but it is 6 % of the Gozo job on 24
threads and 12 % on 3 cores; on R9 it takes 0.6 s of 16. Everything else runs on one core, so 24
threads make the large job only 5 % faster than 3 cores. A job keeps 1.2 of 3 cores busy, 1.4 of
the VPS's 7: **on the VPS about 80 % of the worker's cores are idle while one job computes.**

![Gozo on 24 threads](perf/gozo-24.png)

![Gozo on 3 cores](perf/gozo-3.png)

![R9 on 3 cores](perf/r9-3.png)

Where the large job spends its time (24 threads, all 6 tiles together; cProfile for the parts
between the bars):

| Stage | Wall s | Cores | Where |
| --- | ---: | ---: | --- |
| gap filling (`sources.fill_gaps`) | 44 | 1 | 19 s in `scipy.ndimage.median` over the whole tile, 7 s own numpy, 11 s the FABDEM/Copernicus mosaic |
| anchor prominence and drop (`terrain.py`) | 20 | 1 | union-find in plain `@njit` (12 s) and an `argsort` of every pixel (5 s) |
| mosaics (`build_mosaic`: terrain, surface, water mask) | 9 | 1 | half of it `rasterio.warp.reproject` with GDAL's one thread |
| saving results and the map (`runs.save_results`, `mapping.save_map`) | 14 | 1 | CSV, GeoJSON, `json` of 403 026 lines |
| grouping, coordinates, tile files | 9 | 1-1.5 | |
| filling sea and lakes, sea mask | 8 | 1 | |
| line search (free directions, pairs, checking) | 7 | 18-22 | numba `parallel=True` |

R9 (a circle) has a different profile: line profiles 7.1 s (one `line_profile` per line, all 85 671
lines of a circle), saving 5 s, line search 0.6 s.

**A cheap fix found on the way.** `fill_gaps` calls `ndimage.median(values, ring, index=...)` on the
whole tile; scipy sorts every pixel, label 0 included. Passing only the ring pixels
(`ndimage.median(diff[ring > 0], ring[ring > 0], index=...)`) gives identical medians: on a
7 600 × 7 600 tile with 2 958 gaps, 10.5 s → 0.15 s. That is about 15 % of the Gozo job, with
the same lines (the regression checksums would not move).

## 2. Downloads

The download phase (`search.download_data`) does only network and file work: the layers one after
another (terrain, then surface, then the water mask), each with a pool of `DOWNLOAD_THREADS = 4`.
It keeps 0.1-0.3 cores busy (1.8 at 8 threads on Malta's WCS).

| Area, service | 2 threads | 4 threads (today) | 8 threads |
| --- | ---: | ---: | ---: |
| Gozo coast, Malta WCS (50 tiles, 196 MB received) | 66 s | 25 s | 15 s |
| Jura r 2 km, geoportal.gov.pl sheets (18 sheets, 662 MB) | 285 s | 181 s | 121 s |
| two Jura areas at once, 4 threads each (17 + 18 sheets, 1 250 MB) | | 286 s and 315 s | |

- Each connection is slow: about 1 MB/s per geoportal sheet (earlier measurements gave 17 MB/s,
  docs/roadmap.md: the service varies), and Malta's WCS spends most of a request generating the
  tile. More threads help both, almost linearly up to 8.
- Two jobs downloading from geoportal at the same time got no more in total (1 250 MB in 315 s,
  4.0 MB/s) than one job with 8 threads (5.5 MB/s): the service (or the path to it) is the limit,
  not the number of jobs.
- The terrain and surface layers are downloaded one after the other, so a job waits for the slowest
  sheet of each layer twice.
- With one download slot, a slow download blocks everyone: the next job's download starts only when
  this one ends, even if it needs a different service or nothing at all (cached data).

Is it safe to run two download phases at once? Yes: each download writes its own `.part` file and
renames it (`cache.py`), `index.sqlite` is in WAL mode, and Nominatim and Overpass are already
limited across processes (`osm._ask`, `osm._overpass_turn`). What is missing is a lock per tile:
two jobs over the same area download the same tiles twice (correct, but wasted), and no limit per
host across jobs.

## 3. SQLite

| Database | Written by | Settings |
| --- | --- | --- |
| `jobs.sqlite` | worker (events, claims, heartbeat, quick lane), web (jobs, favourites, reports, usage) | WAL, `timeout=60`, a new connection per operation |
| `accounts.sqlite` | web (sign-ins, sessions: `seen`) | WAL |
| `audit.sqlite` | web and worker, one row per change | WAL |
| `cache/<top>/index.sqlite` | downloads, one row per tile | WAL |
| `cache/osm/nominatim.sqlite` | Nominatim answers | rollback journal (no WAL) |
| `cache/osm/nominatim-rate.sqlite` | pyrate-limiter's bucket | its own |

`jobs.sqlite` under load (`tools/perf_sqlite.py`, 30 s each; a phase writes a progress event every
0.3 s and an info event every 2 s, the worker its heartbeat every 5 s and its claims every 0.5 s,
the quick lane `quick_claim` every 0.05 s, each page reads its events and `worker_alive` every
0.5 s):

| Jobs at once | Pages | Events/s | event write, median / p99 | page read, median / p99 | errors |
| ---: | ---: | ---: | --- | --- | ---: |
| 1 | 30 | 4 | 2.3 / 18 ms | 14 / 22 ms | 0 |
| 4 | 30 | 17 | 6.6 / 60 ms | 6.8 / 23 ms | 0 |
| 16 | 30 | 66 | 5.1 / 117 ms | 4.4 / 24 ms | 0 |
| 4 | 100 | 17 | 12 / 85 ms | 17 / 175 ms | 0 |
| 4 | 400 | 17 | 11 / 86 ms | 122 / 307 ms | 0 |
| 4, no pauses | 30 | 429 | 5.0 / 114 ms | 17 / 30 ms | 0 |

- **SQLite is enough** for one machine, as decided (docs/roadmap.md: Postgres only with a second
  machine). The writes of 16 jobs at once are 66 events/s, a sixth of what four writers without
  pauses reach on this PC (429/s); no `database is locked` anywhere.
- **The limit is the web process, not the database:** every open page polls on its own (two
  queries every 0.5 s, each on a new connection with `PRAGMA journal_mode`). At 400 pages the
  reads queue behind the GIL of one process (median 122 ms) while the writes stay at 11 ms. The
  web container has one CPU (`WEB_CPUS=1`).
- The idle quick lane opens a write transaction (`BEGIN IMMEDIATE`) 20 times a second, the
  busiest writer when nothing happens; harmless now, but it competes with every other write.

## 4. Memory of a job

A search needs memory for its grids (step 1-3: the terrain, surface, water and gap grids of a
tile and their temporaries, `search.PIXEL_BYTES` per pixel) and for its lines (steps 4 and 5).
Until 2026-10-31 a line was a `helpers.Line` of Python floats and then a dict of its coordinates,
and step 5 built every row of `lines.csv` and `data.js` at once; the worker on the VPS was killed
at 3.7 million lines. Lines are now numpy columns (`helpers.LineTable`) from the line search to
the files, which are written chunk by chunk from them (the files are the same byte for byte:
R4, R9, R13 and the Gozo coast in tiles compared with the old code).

Bytes per line, the 403 026 lines of the Gozo coast through steps 4 and 5
(`tools/perf_lines_memory.py`, the grids apart):

| | a dict per line (before) | columns (now) |
| --- | ---: | ---: |
| the line search's output | 760 | 144 |
| peak of step 4 (coordinates, groups) | 2 213 | 421 |
| held between tiles | 1 605 | 236 |
| peak of step 5 (saving) | **3 050** | 382 |

Step 5 was the highest peak, above the 2.5 KB that `search.LINE_BYTES` counted; it is now
500 B (450 B since wave 5 of the line search). The whole search (no tracemalloc, tiles of 5 km, the same lines):

| Gozo coast, 403 026 lines | before | now |
| --- | ---: | ---: |
| peak memory of step 4 | 1.71 GB | 0.78 GB |
| peak memory of step 5 | 1.67 GB | 0.48 GB |
| peak memory of the job (step 1, the grids of a 50 Mpx tile) | 3.87 GB | 3.48 GB |
| wall time | 125 s | 112 s |

- **The grids now decide the peak** of an area: about 65-85 bytes per pixel at the gap filling of
  step 1 (50 Mpx: 3.5 GB, 65 Mpx: 5.6 GB), within the 100 B of `PIXEL_BYTES`. Recommendation 1
  (the median of the gap filling) also takes a full-size temporary out of that peak.
- **A circle keeps the profile of every line** (the map from disk shows each), about 100 B per
  point and up to 203 points: 3 KB on average at R9's 5 m, 19 KB at 1 m. R9's 85 671 lines hold
  about 0.45 GB of profiles (its peak 1.02 → 0.81 GB). The memory model counted none of this, so a
  public 1 m circle with a million lines would have needed about 20 GB; `search.memory_needed`
  now counts a circle's profile points (`PROFILE_POINT_BYTES`) and refuses lines that would not
  fit with them. Since 2026-11-01 a profile is held as arrays, 21-30 B per point ("Done, wave 3" of
  the order of elimination).
- **The largest public search** (`grid_mpx_max` 36 Mpx, `lines_max` 1.5 million) now needs
  3.6 + 0.75 = 4.35 GB where it needed 3.6 + 3.75 GB by the model (and about 8.2 GB in step 5);
  since wave 5 of the line search (`LINE_BYTES` 450 B, "Done, wave 5" below) 3.6 + 0.68 = 4.28 GB.

## The VPS: 8 cores, 24 GB

The worker gets 7 cores and about 20 GB (24 GB less the web service's 1 GB, the system, nginx and
the page cache that the memory-mapped grids rely on).

- **Cores.** One job at a time uses 1.4 of 7. Four compute slots would keep about 5-6 cores busy
  (each job 1.2-1.5, the line search of several jobs sharing the cores now and then), leaving
  room for the download slots and the quick lane.
- **Memory.** A worst-case public job (a 36 Mpx tile and 1.5 million lines) needs 4.28 GB (4.35
  GB before wave 5 of the line search), a
  job like Gozo about 3.5 GB, R9 0.8 GB, R13 0.2 GB. Beside the computing jobs the worker holds the
  quick lane (a profile measured on the map builds a grid of up to 6 000 × 6 000 px,
  `MAX_MEASURED_PX`: up to 3.6 GB) and its download processes (a few hundred MB each). Of about
  20 GB, some 15 GB are left for computing:
  - **three compute slots of 5 GB each** fit the worst case without any estimate; before the
    columns a worst-case job needed 7.4-8.2 GB, so only two would have fitted;
  - **four slots** fit only with admission by an estimate (the pixels of the largest tile are
    known when the job is planned, its lines are not: a slot reserves `memory_needed(pixels,
    lines_max)`, which for most jobs is far less than 5 GB).

  Each slot's search must then be checked against its own budget, not against the memory free
  when it starts (`Plan.memory = available_memory()` today): jobs started one after another would
  each count the same free memory.
- **Throughput.** With one slot, a Gozo-sized job (about 2 minutes on cached data) holds the
  queue; with four slots and fair claiming, three other users' small jobs pass it meanwhile.
  Jobs per hour grow about 3-4 times when the queue holds several jobs; one job alone is not
  faster (that needs recommendations 1, 4 and 5).

## Conclusions

1. **The worker wastes most of its cores.** A computing job keeps 1.2 of 3 cores busy, because only
   the line search is parallel. Even with more cores the job would barely be faster (Gozo: 129 s
   on 24 threads, 135 s on 3).
2. **Throughput is one computing job at a time**, and a large job blocks small ones (first in, first
   out, no fairness between users): behind a Gozo job (2-3 minutes with cached data), every small
   search waits.
3. **Downloads are limited by the services**, not by the worker; one slot means a slow service
   blocks the downloads of all other jobs.
4. **SQLite fits**; the web's polling per page is what grows with many users.
5. **Memory per job is now set by its grids**, not its lines: the lines as columns take about a
   seventh of the memory (500 B per line instead of 2.5-3 KB; 450 B since wave 5 of the line
   search), so a worst-case public job needs 4.28 GB instead of 7.4-8.2 GB, and three of them fit
   the VPS's worker. A circle's profiles of
   every line are the exception (about 19 KB per line at 1 m) and are now counted.

## Recommendations (ranked by gain against effort)

| # | Change | Gain | Effort |
| --- | --- | --- | --- |
| 1 | `fill_gaps`: the median over the ring pixels only | ~15 % of a large job, less memory; identical results | a few lines |
| 2 | Compute slots per worker, each with a memory budget that its search is checked against (`Plan.memory` = the slot's budget, also for the tile size): on the VPS three slots of 5 GB (or four admitted by `memory_needed(largest tile, lines_max)`), on the default 3 cores / 8 GB one slot, or two of about 2 GB with smaller tiles; and two or three download slots | ~3× jobs per hour on the VPS; small jobs no longer wait for a large one | `Scheduler.running` per slot, the budget into `plan_search`; medium |
| 3 | Fair claiming: the oldest job of the user with the fewest running jobs (round robin, already in docs/roadmap.md) | small jobs of other users are not stuck behind one user's queue | one SQL query; small |
| 4 | The tiles of a large area in parallel processes (each tile is independent until the merge) | large jobs ~N× faster with N tiles in memory | medium (memory as in 2) |
| 5 | Parallel single-core stages: `reproject(num_threads=...)`, the prominence's `argsort` (numba parallel or per band), profiles of a circle in numba `prange`, writing `lines.csv`/`lines.geojson`/`data.js` in parallel | 10-25 % each where they dominate | small to medium each |
| 6 | Downloads: one pool for both layers, 8 threads per job, a limit per host across all jobs (a file lock or a semaphore in SQLite, like Overpass), a lock per tile so two jobs never fetch the same tile | shorter downloads, politer to the services | small to medium |
| 7 | The web: one poller per process reading new events every 0.5 s and handing them to the open streams, instead of a query per page; the quick lane waits longer when idle | hundreds of open pages on one CPU | small |

The measurements apply to this PC; the VPS's cores are slower or faster per core, but the shape
(one busy core most of the time) does not depend on it. Worth checking on the VPS itself: the
`.env` there (`WORKER_CPUS`, `WORKER_MEMORY`) and one large search with `tools/perf_profile.py`.

## Done (2026-10-31)

Recommendations 1, 2, 3, 6 and 7, with the lines as numpy columns (section 4); 4 and 5 stay open.

| Branch | What | Measured |
| --- | --- | --- |
| `perf-concurrency` | lines as columns (`helpers.LineTable`, `mapping.Groups`), files written chunk by chunk, `LINE_BYTES` 500, a circle's profiles counted and kept only while they take at most `CIRCLE_PROFILES_BYTES` (500 MB) | section 4 |
| `gap-median` | 1: the median of the ring pixels only | Gozo 125 → 105 s, peak 3.9 → 3.2 GB |
| `compute-slots` | 2 and 3: `FINDALINE_LIMIT_COMPUTE_SLOTS` / `_DOWNLOAD_SLOTS` (default 1; the VPS: 3 and 2, docs/deployment.md), a memory budget per compute slot (`search.slot_memory`: the worker's memory less the quick lane's largest grid and 512 MiB per download slot, divided by the slots), `Jobs.claim` the oldest job of the user with the fewest running jobs | two jobs computing at once (tests) |
| `download-pools` | 6: one pool of 8 threads for the layers (their indexes listed in parallel), at most 8 tiles at once per host across all processes (`sources.host_slot`, filelock), a lock per tile (`sources.tile_lock`), a new `index.sqlite` opened by many threads at once no longer fails | Gozo 15.0 → 13.0 s and Jura 193 → 109-150 s at 8 threads; two Jura areas at once 411/388 → 219-244/322-343 s; the same area by two jobs downloaded once. The geoportal sheet index (12-150 s a run) is now the most variable part |
| `sse-poller` | 7: one event poller per web process (`web.EventHub`), the idle quick lane only reads | the web's CPU at 50 / 200 / 400 open streams 40 / 168 / 253 % → 3 / 12 / 32 %, the delay of an event bounded by TICK; idle quick lane 19 → 0 writes per second |

All together on the Gozo coast (cached data, tiles of 5 km): 125 → 95 s on 24 threads, 134 → 102 s on
3 cores, the peak memory of the job 3.9 → 2.7 GB; regression R1, R2, R4, R9, R10, R13-R16, R18, R19 ok.

## Recommendation 4 deferred (2026-10-31)

The tiles of a large area in parallel processes are left for later:
- **Memory.** The grids of a tile now set a job's peak (a public 36 Mpx tile about 3.6 GB), and a
  compute slot on the VPS has about 5.2 GB: one tile fits. Two tiles at once would mean fewer slots
  or smaller tiles.
- **Smaller tiles mean more work.** Each tile reads `--max-length` and the margin around its core:
  with a 5 km core and about 1 km around it a tile has about twice the pixels of its core, with a
  2.5 km core about 3.4 times.
- **It helps when the site is idle.** With the queue full the other slots already use the cores;
  only one large job alone would finish sooner.
- **Effort**: resuming, progress per tile, the same tiles in both phases, R14 (tiles equal one grid).

To reconsider if the site is mostly idle and large areas are common: lending free compute slots to
the tiles of a running job.

## Done, second wave (2026-10-31)

Recommendation 5 without the circles' profiles (only circles would gain, at the cost of a numba copy
of `line_profile` to keep in step):

| Branch | What | Measured |
| --- | --- | --- |
| `warp-threads` | GDAL's reprojection of a mosaic on `WARP_THREADS` (the cores numba may use, at most 8; the same values with any number) | the Gozo coast's gap fill mosaics 10.6 → 3.4 s |
| `terrain-speed` | the prominence only on the pixels within `span - 1` of an anchor (the union of their windows: equal values, `terrain.py`'s docstring has the reasoning), the drop a numba van Herk / Gil-Werman minimum evaluated at the anchors | the stage "anchor prominence and drop" 22.3 → 3.5 s, its peak memory 2.0 → 0.9 GB (the windows cover 17-32 % of Gozo's tiles) |
| `faster-saving` | step 5's line files built as text column by column (`csv.writer`, the texts shared by the files, rows built once, `runs.round_floats`: Python's `round()` on whole columns) | step 5 of the Gozo coast 20.4 → 4.7 s, R9 5.7 → 3.0 s; the files the same byte for byte |

All together on the Gozo coast (cached data, tiles of 5 km): 95 → 61 s on 24 threads, 102 → 74 s on
3 cores (from 125 and 134 s before the first wave); the peak memory of the job stays 2.7 GB (the gap
filling of step 1). R9 on 3 cores 16.8 → 14.9 s (its circle's profiles, one core). Regression R1,
R2, R4, R9-R11, R13-R16, R18-R20 ok; the four files of the Gozo coast the same as before.

## Still open (2026-10-31)

- The VPS's `.env`: `WORKER_CPUS=7`, `WORKER_MEMORY=20g`, `WORKER_COMPUTE_SLOTS=3`,
  `WORKER_DOWNLOAD_SLOTS=2` (docs/deployment.md), then one large search there with
  `tools/perf_profile.py` to check these numbers on its cores.
- The peak memory of a job is now the gap filling of step 1 (`sources.fill_gaps` and its mosaics).
- A circle's profiles of every line are computed on one core (R9: 7 s of 15). Done 2026-11-01
  ("Done, wave 3" of the order of elimination, below).
- The geoportal sheet index is the most variable part of a download (12-150 s a run).
- Four compute slots admitted by an estimate of each job's memory (three fixed slots now).
- Recommendation 4, the tiles of a large area in parallel: deferred, see above.

## Order of elimination (2026-11-01, branch `line-order`)

The question: is the order in which the line search drops potential lines optimal, how can that be
checked, and what should the server collect so the code can follow what users run?

### How it was measured

`tools/perf_line_funnel.py` (with `tools/line_funnel_kernels.py`) measures the line search without
changing it. `capture -- <findaline options>` runs a search with `linesearch.find_valid_lines`
wrapped and saves the inputs of each call (a grid, or one call per tile): copies of its grids,
anchors and masks, its parameters, and the wall and CPU seconds of the bars "free directions",
"anchor pairs" and "checking lines". `analyse` rebuilds the arguments the kernels get and first
checks that production's `_free_rings` and `_pairs` give the results of frozen reference copies
(rings, per-anchor counts and the pairs written: equal arrays). It then runs instrumented copies
with integer counters at each anchor's own index (so the counts do not depend on the threads):

- the free directions: rings, pixel reads and atan2 calls (also those whose sectors were all
  closed already), per ring the anchors and sectors still alive, and the reads a scan of the alive
  sectors only would make;
- the pair search: every visit of a partner slot and the test that rejects it, in today's order
  (dedup, strong, max and min length, height difference, wall angle, the rings of each anchor,
  `_line_ok`); on the same visits, without applying them, the visits candidate rules would skip,
  alone and cumulatively, and the pairs checked pixel by pixel each rule would skip (must be 0: a
  rule may skip only what fails before `_line_ok`, so the lines and the regression's counters
  stay); the share of the work held by the anchors that find lines;
- `_line_ok`: for every checked pair (every M-th anchor's with `--sample-every`) the test of every
  pixel, the tests until the first failure under six orders, and where the first failure lies.

The candidate rules: **F2a** cells with no partner the dedup rule keeps (the cell's largest index
<= i; in a tile the cells left of the anchor's), **F2b** cells whose nearest pixel is beyond
`max_length` + 2 px, **N1** partners beyond 2R+1 px of an anchor whose rings stop at R, **F8c**
cells entirely in closed sectors of the anchor or with no partner open towards it, **cell Δh**
cells whose anchors' heights all miss e ± D0 (D0 = min(ratio · L, `max_dh`)), **N3** the height
difference tested before `hypot`. **F1** is the writing pass of `_pairs` restricted to the anchors
that found lines (today both passes run over every anchor of a chunk).

15 searches on cached data: R4, R5, R9, R13, R14, R16, R21, R22 as in the regression set; the Gozo
coast at 1 m (`--area coast --buffer 100 --within osm:Gozo --slope-threshold 60 --tile-size 5000`, the
first two of six tiles); "swiss-long", a 1 m circle of 2 km in the Lauterbrunnen valley with lines
of 150-2500 m (`--lat 46.55 --lon 7.88 --radius 2000 --resolution 1 --min-length 150 --max-length
2500 --slope-threshold 60`); and the web form's presets `typical` (30-150 m, Δh 10 m) and `long`
(100-400 m) at R20's, R22's and the Gozo coast's places. Counts from shared runs of the test lock;
times from `--exclusive` runs of `tools/perf_profile.py`.

### The funnel today

| Search | anchors | open | visits | dedup kept | length kept | Δh kept | candidates | rings kept | checked | found of checked | pixel tests per checked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R13 | 2 797 | 86 % | 5.5 M | 50 % | 86 % | 7.5 % | 177 k | 4.9 % | 9 k | 6.6 % | 4.7 |
| R9 | 27 401 | 77 % | 399.8 M | 50 % | 61 % | 11.8 % | 14.5 M | 3.8 % | 549 k | 15.6 % | 8.5 |
| R4 | 20 460 | 14 % | 8.6 M | 50 % | 99 % | 57.2 % | 2.4 M | 1.5 % | 37 k | 5.3 % | 13.0 |
| R5 | 20 460 | 51 % | 109.9 M | 50 % | 99 % | 58.6 % | 31.9 M | 4.1 % | 1.3 M | 4.0 % | 20.7 |
| R14 | 129 270 | 14 % | 1.6 M | 50 % | 92 % | 55.6 % | 403 k | 3.5 % | 14 k | 9.0 % | 8.3 |
| R16 | 65 681 | 63 % | 35.3 M | 50 % | 75 % | 78.6 % | 10.3 M | 5.1 % | 528 k | 4.9 % | 12.8 |
| R21 | 62 990 | 4 % | 6.5 M | 50 % | 73 % | 8.3 % | 199 k | 3.6 % | 7 k | 23.0 % | 20.3 |
| R22 | 150 738 | 19 % | 752.2 M | 50 % | 72 % | 3.2 % | 8.5 M | 3.1 % | 262 k | 7.2 % | 8.7 |
| R20-typical | 27 953 | 7 % | 2.4 M | 50 % | 60 % | 5.7 % | 42 k | 7.9 % | 3 k | 22.3 % | 24.5 |
| R20-long | 27 953 | 7 % | 3.5 M | 50 % | 61 % | 7.2 % | 77 k | 11.4 % | 9 k | 22.3 % | 43.5 |
| R22-typical | 150 738 | 19 % | 371.7 M | 50 % | 57 % | 1.6 % | 1.7 M | 8.0 % | 136 k | 14.7 % | 10.2 |
| R22-long | 150 738 | 19 % | 749.2 M | 50 % | 60 % | 3.5 % | 7.9 M | 2.5 % | 200 k | 3.7 % | 7.5 |
| gozo | 166 351 | 31 % | 436.5 M | 53 % | 57 % | 54.0 % | 71.4 M | 8.1 % | 5.8 M | 4.4 % | 48.6 |
| gozo-typical | 123 673 | 33 % | 54.4 M | 49 % | 54 % | 14.0 % | 2.0 M | 6.8 % | 140 k | 17.2 % | 17.9 |
| swiss-long | 522 387 | 19 % | 9.8 G | 50 % | 75 % | 7.9 % | 289.5 M | 15.7 % | 45.4 M | 3.7 % | 45.9 |

(Visits: partner slots of the 11 × 11 cells around each anchor, one pass; the kept shares are of
what reaches each test.)

### Where the time goes

A least-squares fit of the bars' CPU seconds over seven captures gives about **3.8 ns per visit,
8.7 ns per pixel test of `_line_ok` and 5.7 ns per pixel read of the free directions**. The visits
are 97-100 % of the pair search's CPU on R9 and R22, 64-67 % on R5 and swiss-long, 40 % on the Gozo
coast (long lines over the sea: 48.6 pixel tests per checked pair). For the short lines of
`typical` the free directions are the largest part (R22 `typical`: 3.9 of 6.6 CPU-s on 7 cores):
they scan up to 64 rings whatever the lines' length.

The whole jobs (`tools/perf_profile.py`, cached data, `--exclusive`):

| Job | cores | wall s | CPU s | line search wall | line search CPU | free directions / pairs / checking, CPU s |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| R9 | 24 threads | 12.0 | 28.7 | 0.5 (4 %) | 12.7 (44 %) | 4.3 / 7.6 / 0.8 |
| R22 | 24 threads | 5.1 | 31.0 | 1.1 (22 %) | 21.2 (68 %) | 7.0 / 13.2 / 1.0 |
| R22 `typical` | 24 threads | 4.4 | 23.2 | 0.8 (18 %) | 14.0 (60 %) | 7.5 / 5.8 / 0.7 |
| R22 `typical` | 7 | 4.7 | 11.5 | 1.3 (28 %) | 6.6 (57 %) | 3.9 / 2.6 / 0.1 |
| Gozo coast | 24 threads | 69.3 | 201.9 | 3.8 (5 %) | 79.7 (39 %) | 27.8 / 45.7 / 6.2 |
| Gozo coast | 7 | 70.7 | 122.7 | 6.5 (9 %) | 41.3 (34 %) | 16.7 / 22.7 / 1.9 |
| swiss-long | 24 threads | 57.5 | 278.6 | 9.7 (17 %) | 211.8 (76 %) | 18.6 / 170.3 / 22.9 |
| swiss-long | 7 | 64.3 | 165.2 | 16.3 (25 %) | 111.4 (67 %) | 12.9 / 88.8 / 9.7 |

(R9 and R22 corrected the same day: their first runs had compiled numba's kernels, R9 those of steps
2 to 4 and R22 `_evaluate` without a surface model, about 11 s and 1 s of their wall time; these two
rows are of a second run with the cache warm, as the others were.)

The line search is the only parallel part of a job, so it is a small share of the wall time but
**a third to two thirds of a job's CPU on 7 cores**: on the VPS, where three compute slots share 7
cores, it is what limits the jobs per hour of these kinds. (On 24 threads the CPU seconds of the
hyperthreads inflate it; the 7-core rows are one thread per core.)

### Answers

1. **The order of the tests within a pair is right.** Cheap tests come first and `_line_ok` last.
   The height difference is the most selective after the length in the mountains (it keeps 1.6-14 %
   of the pairs that pass the length; 54-79 % in the Polish valleys and on the Gozo coast), so
   testing it before `hypot` (N3) makes most visits cheaper, but they remain visits.
2. **The order of the pixels is close to optimal.** 75-98 % of the checked pairs that fail, fail at
   the first pixel next to an anchor, mostly the higher one's (swiss-long: 1.63 M at the higher end,
   0.53 M at the lower; the limit follows the lower anchor's height, so the terrain beside the higher
   anchor is too high). Orders that start in the middle or run along the line need more tests
   (natural 1.2-6.7 times today's, middle-out 1.6-19 times; the unscreened middle first and a plain
   bit reversal are better only on R16 and R5, 72 %, and worse up to 14 times elsewhere). Only long
   lines across bays and valleys fail in the middle often enough to matter: two pixels at each end,
   then a bit-reversal order needs 35 % of today's tests on the Gozo coast, 46-63 % on R4, R5 and
   R16, 83-103 % elsewhere. The rings' screen covers the failures: 0-10 % lie
   outside the screened zone, so a screen beyond 64 rings would gain little.
3. **The time is lost in the enumeration and the repetition, not in the order.**

| Search | F2a | +F2b | +N1 | +F8c | +cell Δh | N3 alone | checked skipped | F1: visits / pixel tests of anchors with lines | ring reads in alive sectors | atan2 for dead sectors only | best pixel order vs today | first failure at the 1st pixel |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R13 | 37 % | 39 % | 39 % | 74 % | 77 % | 82 % | 0 | 10 % / 82 % | 23 % | 49 % | 85 % (two ends bit reversal) | 92 % |
| R9 | 42 % | 56 % | 67 % | 83 % | 89 % | 80 % | 0 | 38 % / 97 % | 19 % | 56 % | 98 % (two ends bit reversal) | 97 % |
| R4 | 39 % | 39 % | 51 % | 70 % | 70 % | 10 % | 0 | 9 % / 71 % | 26 % | 49 % | 63 % (two ends bit reversal) | 95 % |
| R5 | 39 % | 39 % | 40 % | 63 % | 63 % | 10 % | 0 | 19 % / 83 % | 31 % | 51 % | 46 % (two ends bit reversal) | 75 % |
| R14 | 37 % | 37 % | 68 % | 78 % | 78 % | 5 % | 0 | 20 % / 89 % | 21 % | 52 % | 85 % (two ends bit reversal) | 96 % |
| R16 | 44 % | 51 % | 57 % | 71 % | 71 % | 0 % | 0 | 20 % / 84 % | 37 % | 34 % | 58 % (two ends bit reversal) | 78 % |
| R21 | 41 % | 45 % | 51 % | 74 % | 80 % | 76 % | 0 | 8 % / 91 % | 25 % | 51 % | 93 % (two ends bit reversal) | 94 % |
| R22 | 42 % | 48 % | 49 % | 76 % | 79 % | 93 % | 0 | 10 % / 95 % | 33 % | 36 % | 94 % (two ends bit reversal) | 97 % |
| R20-typical | 44 % | 50 % | 50 % | 67 % | 67 % | 88 % | 0 | 11 % / 96 % | 38 % | 22 % | 100 % (ends inward) | 86 % |
| R20-long | 40 % | 40 % | 40 % | 56 % | 57 % | 77 % | 0 | 7 % / 98 % | 38 % | 22 % | 100 % (ends inward) | 91 % |
| R22-typical | 43 % | 55 % | 56 % | 82 % | 87 % | 97 % | 0 | 9 % / 97 % | 33 % | 36 % | 100 % (two ends bit reversal) | 98 % |
| R22-long | 42 % | 48 % | 49 % | 76 % | 79 % | 93 % | 0 | 6 % / 89 % | 33 % | 36 % | 91 % (two ends bit reversal) | 96 % |
| gozo | 32 % | 50 % | 60 % | 79 % | 79 % | 15 % | 0 | 19 % / 82 % | 38 % | 26 % | 35 % (two ends bit reversal) | 88 % |
| gozo-typical | 39 % | 50 % | 56 % | 73 % | 73 % | 78 % | 0 | 12 % / 96 % | 37 % | 25 % | 98 % (two ends bit reversal) | 94 % |
| swiss-long | 40 % | 45 % | 45 % | 71 % | 76 % | 90 % | 0 | 20 % / 95 % | 33 % | 32 % | 83 % (two ends bit reversal) | 97 % |

   Half of all visits are rejected by the dedup rule, which a cell's largest index decides before
   any of its partners is read; the cell rules together would skip 57-89 % of the visits, and no
   rule skipped a single checked pair in any of the 15 searches. The writing pass repeats the work
   of every anchor although the anchors with lines hold 6-38 % of the visits (but 71-98 % of the
   pixel tests). 62-81 % of the free directions' pixel reads lie in sectors closed already. The
   prominence and drop of the open anchors only (F4) give the same values in 0-43 % less time of
   that stage, at most 0.2 s a grid.

### Recommendations

All of them keep the lines, the order of the found pairs (the stable sorts carry it into
`lines.csv`) and the regression's counters; `analyse` checks each against the frozen references.
Effort as for an agent: low, medium, high.

| # | Change | What the measurements say it removes | Effort |
| --- | --- | --- | --- |
| F1 | the writing pass only for the anchors with lines | 62-94 % of the second pass's visits | low |
| F2 + N1 + N3 | cells skipped by the dedup rule (a `searchsorted` within the cell), the distance and the anchor's own reach; the height difference before `hypot` | 39-68 % of the visits skipped, most of the rest cheaper in the mountains | medium |
| F8a | the free directions over the alive sectors only (sector masks instead of atan2) | 62-81 % of the ring reads | medium |
| F6 | `_line_ok` from the higher anchor's end, two pixels at each end, then bit reversal | 0-65 % of the pixel tests (most on coasts) | low |
| F8c | cells outside the anchor's open sectors, or without a partner open towards it | a further 10-35 % of the visits | high |
| F1′ | one pass with a buffer per anchor | the second pass's pixel tests (95 % of all on swiss-long) | medium |
| L | the partners' data in cell order | the cost per visit (to be measured) | medium |

By the fit above, F1 with F2 + N1 takes about 45 % off the pair search of swiss-long and 70 % off
R22's (whose pairs are nearly all visits), F8a about two thirds off the free directions, and on the
Gozo coast F6 adds the most (65 % fewer pixel tests). Together, F1 + F2 + N1 + F8a (and F6 on
coasts) would take roughly 45-70 % off the line search's CPU and 15-40 % off these jobs' CPU (R22
and R22 `typical` about 40 %, R9 about 30 %, swiss-long 30-38 %, the Gozo coast 15-22 %, where step
1 is the larger part), with the same results. Not recommended: F4 (small); a screen beyond 64 rings
(few failures there, and it would change the counters); other SECTORS or RINGS (they change the
counters); other cell sizes (L/16 saves 0-25 % of the visits, less than the cell rules, and the
found pairs are written cell by cell, so their order and that of `lines.csv` would change); and an
order chosen at run time (the best order is the same in every search measured).

### Done (2026-11-01, branch `line-kernels`)

Waves 2-5 below came into `main` as one commit; their commits one by one, as the branches had
them, are kept under the tag `history/line-kernels` (`git log history/line-kernels`).

F1, F2 + N1 + N3, F8a with F5a, N4 and F6, one commit each in `linesearch.py`. Each was checked by
the self-check of `analyse` on the 15 captures (the rings equal to the references' capped at
`largest_need`, the useful anchors, the checked and found counts per anchor and the written pairs
equal); all of them together by `pytest` (`test_free_rings_match_reference`,
`test_pairs_match_reference`, `test_line_ok_matches_reference` and the tests before), the regression
set (R1-R5, R9, R13, R14, R16, R21, R22: the same checksums, open and checked counts) and byte for
byte (R9, R22, R22 `typical`, the Gozo coast with `--tile-size 5000` and swiss-long, on 24 threads
and on 7 cores).

| # | In the code |
| --- | --- |
| F1 | `pair_chunk`: the counting pass over a chunk, the writing pass over its anchors that found lines |
| F2 + N1 + N3 | `_pairs` skips the cells without a partner of a higher index (with a tile's `first`, those left of the anchor's) and starts within a cell at the first higher index (a binary search); per row of cells it visits the columns that can lie within `max_length` + 2 px only; it skips the partners farther than 2R + 1 px from an anchor whose largest ring R is below `largest_need`, and it tests the height difference against its bound at `max_length` before `hypot` |
| F8a + F5a | `_free_rings` with the sectors of every ring pixel as a bit mask (`_sector_masks`: the old atan2 and asin expressions, computed once), no read of a pixel none of whose sectors is open, rings up to `largest_need` (half the longest line in pixels, at most 64) |
| N4 | `free_directions`: `_free_rings` on 65 536 anchors at a time, the rings kept as uint8 for the anchors with an open direction only (`slot`: their row) |
| F6 | `_line_ok`: lines of more than 129 and at most 1024 steps test two pixels at each end, then the others in bit-reversal order; the other lines as before |

The kernels alone (the first call of each capture, 23 threads, median of 3, `--exclusive`; free
directions s / the two passes of the pair search s; about ±5 % from run to run):

| Change | Gozo coast | swiss-long | R9 | R22 | R22 `typical` | R5 |
| --- | --- | --- | --- | --- | --- | --- |
| before | 0.47 / 0.69 | 1.01 / 7.66 | 0.17 / 0.30 | 0.47 / 0.46 | 0.46 / 0.22 | 0.13 / 0.28 |
| F1 | 0.48 / 0.50 | 1.00 / 5.22 | 0.17 / 0.21 | 0.47 / 0.28 | 0.47 / 0.13 | 0.12 / 0.19 |
| + F2, N1, N3 | 0.48 / 0.42 | 1.00 / 2.93 | 0.17 / 0.12 | 0.47 / 0.08 | 0.47 / 0.03 | 0.12 / 0.20 |
| + F8a, F5a | 0.09 / 0.46 | 0.20 / 3.19 | 0.03 / 0.11 | 0.08 / 0.08 | 0.09 / 0.03 | 0.02 / 0.19 |
| + N4 | 0.10 / 0.42 | 0.22 / 2.88 | 0.04 / 0.12 | 0.08 / 0.09 | 0.08 / 0.04 | 0.02 / 0.23 |
| + F6 | 0.10 / 0.36 | 0.22 / 3.16 | 0.03 / 0.11 | 0.08 / 0.08 | 0.08 / 0.03 | 0.02 / 0.18 |
| less, both together | 60 % | 61 % | 70 % | 83 % | 84 % | 52 % |

The whole jobs (`tools/perf_profile.py`, cached data, `--exclusive`, numba's cache warm before and
after; the line search: its three bars):

| Job | cores | wall s | CPU s | line search CPU s | free directions / pairs / checking, CPU s | peak RSS MB |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| R9 | 24 threads | 12.0 → 11.6 | 28.7 → 21.6 (-25 %) | 12.7 → 5.1 (-60 %) | 4.3 / 7.6 / 0.8 → 1.2 / 3.1 / 0.8 | 817 → 820 |
| R22 | 24 threads | 5.1 → 4.1 | 31.0 → 14.3 (-54 %) | 21.2 → 4.6 (-78 %) | 7.0 / 13.2 / 1.0 → 1.9 / 2.3 / 0.4 | 388 → 411 |
| R22 `typical` | 24 threads | 4.4 → 3.7 | 23.0 → 13.8 (-40 %) | 14.2 → 4.0 (-72 %) | 7.4 / 6.4 / 0.4 → 2.2 / 1.4 / 0.4 | 345 → 342 |
| R22 `typical` | 7 | 4.8 → 3.6 | 11.9 → 6.4 (-46 %) | 6.9 → 1.5 (-78 %) | 3.9 / 2.9 / 0.1 → 0.9 / 0.5 / 0.1 | 341 → 343 |
| Gozo coast | 24 threads | 70.7 → 66.6 | 199.7 → 158.2 (-21 %) | 79.0 → 38.5 (-51 %) | 28.0 / 45.2 / 5.8 → 6.2 / 26.5 / 5.8 | 2775 → 2822 |
| Gozo coast | 7 | 71.9 → 66.1 | 124.4 → 99.0 (-20 %) | 41.7 → 17.2 (-59 %) | 16.9 / 22.8 / 2.0 → 3.0 / 12.3 / 1.9 | 2869 → 2736 |
| swiss-long | 24 threads | 58.0 → 51.6 | 283.7 → 163.6 (-42 %) | 215.4 → 97.2 (-55 %) | 19.0 / 171.9 / 24.5 → 5.3 / 67.4 / 24.5 | 1186 → 1192 |
| swiss-long | 7 | 66.1 → 54.3 | 169.7 → 98.6 (-42 %) | 114.1 → 44.1 (-61 %) | 13.1 / 91.1 / 9.9 → 2.4 / 32.0 / 9.7 | 1317 → 1114 |

- **CPU**: the line search takes 51-78 % less CPU, the jobs 20-54 % less (the forecast above: 45-70 %
  and 15-40 %). The wall time drops by 3-25 % only: the line search was a small part of it, and the
  rest of the steps is mostly on one core. "checking lines" (`_evaluate`) is unchanged and now a
  quarter of swiss-long's line search.
- **Memory**: the rings take 4 B per anchor and 65 B per open anchor instead of 256 B per anchor,
  plus 4 MB for a chunk of `_free_rings`. One `find_valid_lines` call peaks 119 MB lower on
  swiss-long's 522 000 anchors (psutil's peak working set, 960 → 841 MB) and 30 MB lower on the Gozo
  coast's first tile (142 000); a tile of 3 million anchors, the public site's `anchors_max`, would
  hold about 700 MB less. The jobs' peak RSS stays within the noise of its sampling (about ±100 MB):
  the rings were never its largest part.
- **F6**: production's order needs 35 % of the pixel tests of the order before on the Gozo coast,
  57-65 % on R4, R5 and R16, 99.5 % on swiss-long and 99.8 % on R9. Starting at the higher anchor's
  end saves nothing (99.4-99.9 % of the tests: the loop tested the first pixel of both ends first
  already), so it was left out. The bit reversal stops at lines of 1024 steps: on swiss-long's lines (up to 2500 px) it
  saved 18 % of the tests but cost 8 % more time, its jumps along a long line missing the cache. A
  helper function for the pixel test made the pair search 2-3 times slower, so `_line_ok` writes the
  test out twice.
- **"Candidate pairs"** no longer counts the pairs N1 skips (they fail the rings' test, which comes
  after the count): 46 % of the count before on R14, 77 % on R9, 80-86 % on R4, R16 and the Gozo
  coast, 97-99 % on R22, R22 `typical` and swiss-long. Open, checked and found are unchanged; F19's
  `candidates` changed alike (docs/monitoring.md).
- **Still open**: F8c (high effort); F1′ (the writing pass is still about a third of swiss-long's pair
  search); L; the middle of lines over 1024 px in an order kinder to the cache; `_evaluate`.

### Done, wave 3 (2026-11-01, branch `line-kernels`)

F1′, and the profiles of a search as arrays computed in parallel, one commit each; L was measured as
a prototype and left out. Both were checked as wave 2 was: the self-check of `analyse` on the 15
captures, `pytest` (also `test_pair_buffer_overflow_matches_reference`,
`test_line_profiles_match_line_profile` and `test_line_profiles_independent_of_threads`), the
regression set and byte for byte (R9, R22, R22 `typical`, the Gozo coast with `--tile-size 5000` and
swiss-long, on 24 threads and on 7 cores).

| # | In the code |
| --- | --- |
| F1′ | `pair_chunk`: one pass of `_pairs` over a chunk, each anchor's first `PAIR_BUFFER` (1024) pairs held in a buffer (int32, at most `PAIR_BUFFER_BYTES`, 16 MB, a chunk) and copied in the order of `todo`; the writing pass of before only for the anchors that found more |
| profiles | `lineprofiles.line_profiles`: the profiles of all wanted lines in one numba kernel (`prange` over the lines), held as numpy arrays (`helpers.Profiles`; one line of it is a `helpers.Profile`) and rounded as `helpers.line_profile` rounds; `line_profile` stays for `profile_of_line` (a profile measured on the map, the lines at tile edges) |

- **F1′, the buffer.** On the 15 captures the anchors with lines found a median of 2-31 pairs each,
  a p99 of 10-577 and at most 1221 (swiss-long). 1024 holds every pair of 99.96 % of swiss-long's
  anchors with lines (99.5 % of its pairs) and of all of them elsewhere; swiss-long's largest chunk
  (496 anchors) takes 4 MB. The 16 MB cap matters from 2048 anchors a chunk (more than about 410 000
  open anchors in one call): a tile of 3 million anchors with a fifth of them open would hold about
  700 pairs per anchor.
- **F1′, the pair search alone** (old and new interleaved in one process, chunk by chunk, median of
  3, `--exclusive`; 23 / 7 threads):

| Capture | before (two passes) | F1′ |
| --- | --- | --- |
| swiss-long | 3.06 / 4.90 s | 2.04 / 3.32 s (-33 / -32 %) |
| Gozo coast | 0.364 / 0.587 | 0.267 / 0.429 (-27 %) |
| R9 | 0.111 / 0.181 | 0.076 / 0.119 (-31 / -34 %) |
| R5 | 0.168 / 0.246 | 0.121 / 0.178 (-28 %) |
| R22 | 0.084 / 0.151 | 0.077 / 0.139 (-8 %) |
| R22 `typical` | 0.031 / 0.051 | 0.030 / 0.047 (-2 / -8 %) |

- **L, left out.** The partners' row, column, elevation, `strong`, `down`, rings and largest ring
  copied into cell order and read by position (the best of three variants) was exact and never
  slower, but only 3-11 % faster than F1′ (swiss-long -8 % on 23 threads and -10 % on 7, the Gozo
  coast -8 / -11 %, R9 and R22 -7 to -8 %), below the 10 % asked for. It would cost 29 B per open
  anchor, and 65 B more while the rings are held twice. To reconsider with F8c, which changes the
  same loop.
- **The profiles.** `helpers.line_profile` returned a dict of Python lists per line (83-129 B per
  point), and `search._lines` called it line by line on one core: R9 (a 5 m circle keeping the
  profile of each of its 85 671 lines) spent 7.0 of its 11.6 s there, and its profiles were about
  0.5 GB of its 820 MB peak. As arrays a point takes 21-30 B, up to 77 B while the profiles are
  computed (tracemalloc, 20 000 lines):

| Lines | dicts of lists, held | arrays, held | arrays, peak |
| --- | ---: | ---: | ---: |
| 40 points, surface and water | 129 B | 30 B | 77 B |
| 40 points, terrain only | 83 B | 21 B | 68 B |
| 101 points, surface and water | 115 B | 27 B | 51 B |

  The memory model is unchanged (`PROFILE_POINT_BYTES` 100, `CIRCLE_PROFILES_BYTES` 500 MB), so the
  same circles keep every profile; it now counts more than they hold.

The whole jobs, wave 2's code against wave 3's in one session (`tools/perf_profile.py`, cached data,
`--exclusive`; a warm-up run of each version first, then the two in turn, alternating which went
first; every run byte for byte the same as the reference runs):

| Job | cores | wall s | CPU s | anchor pairs CPU s | line search CPU s | line profiles wall / CPU s | peak RSS MB |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| R9 | 24 threads | 11.8 → 5.2 | 21.4 → 16.5 (-23 %) | 3.3 → 2.5 (-24 %) | 5.3 → 4.5 (-15 %) | 7.0 / 7.0 → 0.3 / 2.7 | 818 → 408 |
| R22 | 24 threads | 4.4 → 2.7 | 14.9 → 15.1 (+1 %) | 2.9 → 2.6 (-10 %) | 5.6 → 4.9 (-12 %) | 1.6 / 2.3 → 0.1 / 2.8 | 409 → 289 |
| R22 `typical` | 7 | 4.0 → 2.7 | 6.8 → 5.4 (-21 %) | 0.6 → 0.4 (-33 %) | 1.7 → 1.4 (-18 %) | 1.4 / 1.7 → 0.1 / 0.8 | 344 → 257 |
| Gozo coast | 7 | 72.4 → 66.7 | 106.9 → 101.3 (-5 %) | 14.1 → 10.5 (-26 %) | 19.7 → 15.8 (-20 %) | 0.6 / 0.7 → 0.1 / 0.3 | 2963 → 2717 |
| swiss-long | 24 threads | 62.4 → 51.5 | 173.7 → 147.7 (-15 %) | 69.0 → 48.7 (-29 %) | 99.5 → 80.1 (-19 %) | 2.8 / 2.8 → 0.2 / 2.9 | 1094 → 1219 |
| swiss-long | 7 | 55.6 → 52.3 | 106.5 → 93.3 (-12 %) | 37.1 → 25.5 (-31 %) | 51.8 → 39.6 (-24 %) | 2.3 / 2.3 → 0.2 / 0.9 | 1165 → 1192 |

- **Circles**: the profiles were most of R9's wall time and a third of R22's. R9 11.8 → 5.2 s (-56 %), R22
  4.4 → 2.7 s, R22 `typical` 4.0 → 2.7 s; their peak memory falls by a quarter to a half (R9 818 →
  408 MB, now in step 5, saving the map). On 24 threads the profiles take as much CPU as before,
  spread over the threads (R22 2.3 → 2.8 s); on 7 cores less (1.7 → 0.8 s).
- **The pair search** takes 24-33 % less CPU (R22's 10 %: its anchors find few pairs each, so its
  writing pass was small), the line search 12-24 %, the jobs up to 23 % (R22 on 24 threads the same).
- **Areas**: the Gozo coast and swiss-long take 5-15 % less CPU; their wall time is set by steps 1,
  4 and 5 on one core. The stages whose code did not change differ by up to 15 % between the runs
  (swiss-long's grouping 21.1 and 17.9 s, its saving 22.2 and 19.2 s), and so do these jobs' wall
  times; their peak RSS is within its noise too (swiss-long's, between the bars of step 3, where the
  lines are joined and sorted: 1090-1220 MB over nine runs of both versions; the Gozo coast's, step
  1: 2700-2960 MB).
- **Still open**: F8c; L (above); the middle of lines over 1024 px in an order kinder to the cache;
  `_evaluate` ("checking lines", now about a third of swiss-long's line search CPU). Planned next:
  the memory of steps 3 and 4 (the pairs and lines copied where they are joined and sorted),
  `LINE_BYTES` measured again, and F7 (the evaluation stops as soon as the lines are over
  `lines_max` or the memory).

### Done, wave 4 (2026-11-01, branch `lines-memory`)

The memory of steps 3 and 4 (M), the memory model measured again, and F7, one commit each. They
were checked as before: `pytest`, the regression set, the self-check of `analyse`, and byte for
byte (R9, R22, the Gozo coast with `--tile-size 5000` and swiss-long, the last two on 24 threads and
on 7 cores). The `pytest` tests include `test_valid_lines_in_parts_as_before`: it keeps the old end
of step 3 as the reference, and every column and dtype must be equal with parts of 1 to 10 000
pairs and 1 to 200 chunks. `test_evaluation_parts` and `test_early_stop_of_the_evaluation` are new
too.

| # | In the code |
| --- | --- |
| step 3 | `find_valid_lines` evaluates the found pairs straight from the chunks' arrays (`evaluation_parts`: parts of at least `EVAL_PART`, 10 000 pairs, each chunk released once handed out) instead of joining all of them first, then joins the valid lines' parts column by column (`join_tables`) and sorts them in place (`LineTable.reorder`) |
| step 4 | `search.line_coordinates`: `mapping.coordify` writes into the final columns `COORDINATE_PART` (131 072) lines at a time, a tile's core is taken in place, and `covered_metres` gives an array, `COVERED_PART` lines at a time |
| model | `tools/perf_lines_memory.py --call`: the traced heap of steps 3, 4 and 5 per line, from a capture of `tools/perf_line_funnel.py` |
| F7 | `find_valid_lines(check=)` after each evaluated part: `search._early_check` refuses as soon as the lines so far (with those of the tiles done already) are over `lines_max`, or would not fit with the grids into `Plan.memory`; `Limits.lines_early_stop` (`FINDALINE_LIMIT_LINES_EARLY_STOP`, true by default), carried by `Plan.early_stop` also for a user without limits, whose compute slot's budget still applies |

The traced heap per valid line (tracemalloc; "→": before → after, single values unchanged):

| Capture | lines | step 3 peak | step 4: coordinates, core, water | step 4: grouping | step 4: profiles | held | step 5 peak |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| swiss-long | 1 695 554 | 494 → 190 B | 350 → 234 B | 389 B | 306 B | 276 B | 327 B |
| Gozo coast, its large tile | 252 534 | 504 → 199 B | 553 → 287 B | 439 B | 311 B | 261 B | 459 B |
| R9 | 85 671 | 501 → 196 B | 306 → 305 B | 413 B | 389 B | 294 B | 834 B |

The peak RSS per step (MB, sampled, `tools/perf_profile.py` in one session, before and after in
turn):

| Job | step 3 | step 4 | job |
| --- | --- | --- | --- |
| R9 | 216 → 204 | 374 → 365 | 421 → 419 |
| R22 | 256 → 227 | 323 → 264 | 339 → 277 |
| Gozo coast | 827 → 826 | 867 → 813 | 2828 → 2911 (step 1) |
| Gozo coast, 7 cores | 756 → 742 | 858 → 797 | 2849 → 2804 (step 1) |
| swiss-long | 1087 → 697 | 1066 → 1073 | 1087 → 1073 |
| swiss-long, 7 cores | 1073 → 698 | 1071 → 1067 | 1073 → 1067 |

- **Step 3** holds about 195 B per line instead of 500: swiss-long's step 3 peaks at 697 MB instead
  of about 1080 (its heap 915 → 423 MB). Its job's peak, about 1.07 GB, is now set by step 4's
  grouping and by step 5, whose code did not change.
- **Step 4**'s coordinates keep one table: 234-305 B per line instead of 306-553 (the most on a
  tile, whose core's `take` copied the table). R9's fit into one part, so its number did not move.
  Step 4's peak is now `mapping.group_lines` (389-439 B per line: its cell index holds the cells of
  every line as Python lists of ints).
- **The model**: `LINE_BYTES` stays 500, 14 % over the largest peak (439 B, the Gozo tile's
  grouping); before wave 4, step 3 alone reached 500 B, so the old value had no margin. The found
  pairs need no term of their own: on all 15 captures there are as many as valid lines (at most
  1.0001 times), and a pair waiting for its check takes 16 B. `PROFILE_POINT_BYTES` (100 B, 30 % over
  the measured 77 B) and `CIRCLE_PROFILES_BYTES` are unchanged: the same circles keep every profile.
  R9's step 5 per line is mostly a fixed part of about 40 MiB (about 300 B per line on the larger
  captures).
- **Times** are unchanged within the noise: swiss-long's "checking lines" 1.1 → 1.2 s wall, its step
  4 19.1 s before and after. The jobs are within ±3 %, apart from two runs whose "before" was slow
  (R22: its "checking lines" took 3.7 CPU s).
- **F7**, on the swiss-long capture with `lines_max` 200 000:
  - The search is refused after 210 000 of its 1 695 554 lines were checked (12 %, 0.22 s instead
    of 1.17 s), without building the table of all of them (about 250 MB).
  - The pair search (8-16 s) still runs to its end.
  - The page says "More than 200000 lines found, the limit of this site: the search stopped there."
    Only the command line's text names the number checked so far: it depends on the size of the
    parts.
  - With the switch off, the search is refused once all its lines are checked ("1695554 lines
    found").
- **Still open**:
  - `group_lines`' cell index without Python lists: about 150 B per line less, after which
    `LINE_BYTES` could fall to about 400 B.
  - Step 5: about 300 B per line plus about 40 MiB.
  - F8c, the middle of lines over 1024 px in an order kinder to the cache, `_evaluate`.

### Done, wave 5 (2026-11-01, branches `group-memory` and `save-memory`)

The memory of step 4's grouping (G) and of step 5 and the join of a tiled search (S), one commit
each, checked as before: `pytest`, the regression set, and byte for byte (R9, R22, the Gozo coast
with `--tile-size 5000` and swiss-long, the last two on 24 threads and on 7 cores; 18 runs of the
two branches together, all the same). New tests keep the old code as the reference:
`test_grouping_as_before` (the dict version of `group_lines`, 64 cases: ranks with ties, lines
exactly `distance` apart, flipped lines, lines over obstacles, coordinates up to 5.4e6 m, parts of
7 lines), `test_row_order_in_parts_as_before` (the old lexsort, parts of 1 to 10 000 rows),
`test_join_of_tiles_as_concat` and `test_tiles_without_pixels`.

| # | In the code |
| --- | --- |
| grouping | `mapping.group_lines`: the cell index as arrays (`_cell_index`: one int64 key per line within the box of the first anchors' cells, a stable argsort, the lines of a row of cells found by `searchsorted`) instead of a dict of Python lists, and the greedy loop in numba (`grouping.greedy`, one thread; `GROUP_PART` lines between progress updates; `gather` writes the groups in their final order) |
| rows | `runs.row_order(groups, lo, hi, at)` gives the rows of one part only (`rep_positions`: where each representative stands, 8 B per group) instead of the order of every line (25 B per line held, about 60 B at its lexsort's peak) |
| chunks | `runs.LINES_CHUNK` and `mapping.LINES_CHUNK` 10 000 → 1 000 lines: a chunk's texts take about 4.5 KB per line (the features of lines.geojson alone 1.7 KB, joined and encoded once more) |
| join | `search_lines` joins the tiles with `LineTable.join`, one column at a time, each tile's column released (`concat` held every line twice, which the model did not know) |
| pixels | `search._lines` ends with `LineTable.without_pixels` ("a1"/"a2", 32 B per line, not read after the profiles); new tile files do not hold them, old ones lose them on loading (no migration) |
| model | `LINE_BYTES` 500 → 450 B |

The traced heap per line (tracemalloc, `tools/perf_lines_memory.py`, 746fa2f of the tag
`history/line-kernels` → both branches;
step 3, 181-199 B, and the coordinates, 225-305 B, did not change):

| Capture | lines | lines per group | step 4: grouping | step 4: profiles | held | step 5 peak |
| --- | ---: | ---: | --- | --- | --- | --- |
| swiss-long | 1 695 554 | 158 | 380 → 267 B | 297 → 306 B | 266 → 244 B | 318 → 246 B |
| Gozo coast, its large tile | 252 534 | 158 | 439 → 268 B | 311 B | 261 → 229 B | 459 → 246 B |
| R9 | 85 671 | 22 | 413 → 266 B | 389 B | 294 → 262 B | 834 → 315 B |
| the Gozo coast's 6 tiles (`--tiles`) | 689 150 | 167 | 426 → 266 B (step 4 peak) | | 234 → 202 B | 322 → 208 B |

The join of those 6 tiles peaks at 560 → 319 B per line (the tiles held 335 → 303 B).
swiss-long's values after are about 9 B higher in every mark, its unchanged step 3 too: what the
warm-up leaves behind.

Whole jobs (`tools/perf_profile.py` in one session, before and after in turn; R22's three more
pairs, since one run after had a slow "checking lines", 4.0 CPU s against 0.4-0.7, as runs before
had in wave 4: that stage did not change):

| Job | cores | wall s | CPU s | grouping wall / CPU s | step 4 wall / CPU s | step 5 wall / CPU s | peak RSS MB (step 4 / step 5 / job) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R9 | 24 threads | 5.1 → 4.5 (-12 %) | 16.0 → 15.7 | 0.5 / 2.5 → 0.0 / 1.1 | 0.8 / 6.4 → 0.3 / 6.1 | 2.9 / 2.9 → 2.9 / 2.9 | 376 / 410 / 410 → 375 / 370 / 375 |
| R22 | 24 threads | 2.7-2.8 → 2.5-2.7 | 14.7-15.4 → 14.4-14.5 | | | | job 280-300 → 270-297 |
| Gozo coast | 24 threads | 64.4 → 58.9 (-9 %) | 156.7 → 149.1 (-5 %) | 7.2 / 13.3 → 0.4 / 5.2 | 10.3 / 40.5 → 3.5 / 31.3 | 7.2 / 7.2 → 7.0 / 7.0 | 815 / 593 / 2722 → 818 / 515 / 2780 |
| Gozo coast | 7 | 70.3 → 65.1 (-7 %) | 103.8 → 97.9 (-6 %) | 8.1 / 10.2 → 0.4 / 1.7 | 11.3 / 19.6 → 3.3 / 10.6 | 7.6 / 7.6 → 7.7 / 7.7 | 804 / 577 / 2753 → 757 / 514 / 2714 |
| swiss-long | 24 threads | 56.0 → 34.2 (-39 %) | 155.6 → 135.4 (-13 %) | 20.9 / 22.7 → 0.9 / 2.9 | 22.9 / 39.2 → 2.7 / 18.5 | 20.9 / 20.9 → 19.1 / 18.8 | 1069 / 1037 / 1069 → 906 / 908 / 908 |
| swiss-long | 7 | 52.6 → 34.7 (-34 %) | 93.4 → 76.4 (-18 %) | 17.8 / 18.2 → 0.8 / 1.4 | 19.8 / 24.2 → 2.7 / 7.3 | 18.8 / 18.6 → 18.0 / 17.8 | 1067 / 1010 / 1067 → 908 / 887 / 908 |

- **The grouping** is 20-25 times faster (`group_lines` alone, warm: swiss-long 17.7 → 0.75 s,
  the Gozo tile 1.4 → 0.06 s, R9 0.5 → 0.03 s) and its own peak is 33-43 B per line instead of
  155-214. Loading its kernels takes about 21 MiB once per process (numba itself is loaded by the
  line search). swiss-long's job takes a third less time, and the Gozo coast's 7-9 % less.
- **Step 5** adds about 5 MiB above the lines it saves (`save_results`; `save_map` about 3 MiB),
  whatever their number; before it was 44-83 MiB and 18-19 MiB. It is also a little faster.
- **The join** of a tiled search holds at most one column twice (16 B per line) instead of every
  line.
- **The peaks**: swiss-long's job 1067-1069 → 906-908 MB, now steps 4 and 5 alike; R9's 410 →
  375 MB; the Gozo coast's is step 1's grids (about 2.7-2.8 GB), unchanged.
- **The model**: `LINE_BYTES` 500 → 450 B, 16 % over the largest peak (R9's profiles, 389 B) and
  about 40 % over the larger searches' (311-319 B). R9's groups are small (22 lines each), so its
  representatives' profiles weigh more per line. They are counted within `LINE_BYTES`, so a search
  of much smaller groups would hold more than the model says. The largest public search now needs
  3.6 + 0.68 = 4.28 GB (4.35 GB with 500 B): three of the VPS's compute slots still fit it (5.6 GB
  each), four still do not (4.2 GB each; `test_memory_of_compute_slots`).
- `tools/perf_lines_memory.py --tiles` now warms the grouping up before measuring. Without the
  warm-up, numba's import added 58 B per line on the Gozo tiles. Tile files written since this
  wave have no pixel columns, so for them it measures only the join.
- **Still open**:
  - The representatives' profiles counted apart from `LINE_BYTES`: their points are known after
    the grouping, so they could be checked as a circle's every profile is (`profile_points`).
  - F8c, the middle of lines over 1024 px in an order kinder to the cache, and `_evaluate`.

### What the server collects

Per job, since migration 16 (docs/monitoring.md, F19): the CPU seconds of every step, the seconds
and CPU seconds of the line search's stages and its funnel (`job_steps`, `job_stages`,
`job_funnel`), read by `tools/job_stats.py` (also on the VPS host) by model, resolution, longest
line, circle or area and preset. It does not tune the order: the best variant follows from the
terrain and the parameters, not from who asks, and the results are the same in any order. It
answers which kinds of searches use the site's CPU (the presets of the form or long lines at 1 m),
so it says which of the changes above to make first, whether `max_length_max`, `anchors_max` and
`compute_seconds` fit the cost, and which classes the local measurements should cover.

## Round 3 (2026-11-02): from the click to the saved lines

The question: what does a user of the web app wait for, from "Search" to the saved lines, and where
are the computing time and the peak memory now, after the two rounds above? Measured from the code,
the public site's `jobs.sqlite` (read on 2026-11-02: 9 finished jobs since 2026-10-29) and the
baseline runs below. The plan with the decisions is the user's plan file of 2026-11-02; the order:
stage 1 the time outside the computing, stage 2 the memory of step 1 and the tile size, stage 3 the
single-core parts of steps 2 to 5, stage 4 the changes that may change results.

### What the server showed

`tools/job_stats.py --phases` on the VPS's `jobs.sqlite` (whole seconds; the worker ran with 7 cores,
18 GiB, 3 compute and 2 download slots since 2026-11-02 07:22, with 1 + 1 slots and 8 GB before):

| Job (2026) | res | km² | download s | wait for a compute slot s | compute s | of it orthophoto | steps 1 / 2 / 3 / 4 / 5 | tiles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 11-01 23:25, sag area ≤ 1000 m | 1 | 14.96 | 3 | 0 | 186 | 85 | 10 / 29 / 35 / 16 / 9 | 4 of 3702² px |
| 11-02 01:16, `long` area, 2.07 M lines | 1 | 9.0 | 2 | 1 | 222 | 7 | 6 / 31 / 29 / 35 / 112 | 2 of 3568 × 3703 px |
| 11-02 02:07, 30 m circle `typical`, 4 lines | 30 | 0.64 | 4 | 0 | 48 | – | 1 / 14 / 14 / 14 / 2 | 1 |
| 11-02 07:19, `typical` area, 970 lines | 1 | 0.21 | 18 | 173 | 196 | 134 | 6 / 14 / 19 / 15 / 5 | 1 |
| 11-02 07:23, circle ≤ 400 m, 896 lines | 1 | 3.14 | 6 | 0 | 150 | 133 | 3 / 3 / 3 / 0 / 4 | 1 |

- **The orthophoto** is downloaded inside step 5, before the map is saved and before the job is
  "done", in the compute phase's process, which holds a compute slot meanwhile (`search.save_run`,
  `jobs.ortho_confirm` with the public `ortho_minutes` 10): 85-134 s of jobs that computed for
  15-60 s (median 109 s, 56 % of the compute phase of these jobs). 934-1416 tiles took 2m13s each
  time (0.1 s a tile with 4 threads; `ORTHO_SECONDS_PER_TILE` 0.3 overstates it 3 times, so the 10
  minute limit admits about 2 000 tiles, about 3.3 real minutes). Locally the worker answers yes to
  every question, so a circle downloads the detail strips of all its groups before "done".
- **A cold numba cache** after every restart of the worker's container (`NUMBA_CACHE_DIR` is a
  tmpfs there, by design): the first job after the restart of 07:22, a 30 m circle with 149
  anchors and 4 lines, took 48 s, steps 2, 3 and 4 about 14 s each: the compilation of the kernels
  of the line search, the profiles and the grouping (about 40 s on the VPS's cores).
- **The waits for a slot** were 0-1 s but for the job of 07:19 (173 s: the worker was being restarted).
  The compute phase outside its steps (the process's start, the imports, planning) is 1.4-3 s.
- **Step 5** took 112 s for 2.07 million lines (half of that job's compute phase).

### The tiles of an area on the public site

`search.tile_core_size` sizes a tile's core from the memory a compute slot has:
`side_px = sqrt(budget × TILE_MEMORY_SHARE (0.25) / PIXEL_BYTES (100))`, the core is the side less
twice the overlap (`_overlap` = `--max-length` + `_margin` (300 m: the prominence span) + 2 px on
each side), in steps of 500 m, at least 500 m. The VPS's slot is (18 GiB − 3.6 GB of the quick
lane's largest grid − 2 × 512 MiB of the download slots) / 3 = 4.89 GB, so 3 495 px of side:

| Lines up to | overlap | core at 1 m | tile | pixels per pixel of the core |
| ---: | ---: | ---: | ---: | ---: |
| 150 m (`typical`) | 452 m | 2 500 m | 3 404² = 11.6 Mpx | 1.85 |
| 400 m (`long`) | 702 m | 2 000 m | 3 404² = 11.6 Mpx | 2.9 |
| 1 000 m (the default) | 1 302 m | **500 m** | 3 104² = 9.6 Mpx | **38.5** |
| 2 000 m (the public maximum) | 2 302 m | 500 m | 5 104² = 26 Mpx | **104** |

Steps 1 and 2 run on every pixel of a tile, so at the default 1 000 m a 1 m area costs about 38
times its own pixels there; the jobs above show it as "anchor prominence and drop" of 13-60 s. The
measurements of the rounds before (the Gozo coast with `--tile-size 5000`: 7 604² px for 5 000 m
cores, 2.3 pixels per core pixel) did not show this. `tools/perf_profile.py --memory 4886000000`
now sizes the tiles as the VPS does.

### The memory of step 1

Counted from the code (the agent's audit of 2026-11-02; N the tile's pixels, "M" a memory-mapped
grid of `work/`, "R" an array in RAM) the peak of a job is `sources.filling._fill` of the surface
pair of the gap filling: about 41 B per pixel on Linux (45 on Windows, where numpy elides no
temporaries): 16 M (`nmt`, `nmpt`, `gap_nmpt`, `wbm` as float32 for a category of 0-3), 5 R held
from outside without a later use at that moment (the area mask, `sea`, `sea_zone`, `filled`,
`gaps`), 20-24 R of `_fill`'s own (`gy`/`gx` alive to the end though used only for `flat`, `flat`,
`both`, the labels, the dilation, `near`, the partition copy of `np.median`). The 65-85 B of
section 4 were measured before the median of the ring pixels; a job's peak of 2.7-2.9 GB on a
58 Mpx tile is 47-50 B per pixel with the imports. `PIXEL_BYTES` 100 therefore has room: stage 2
cuts the temporaries and the held arrays (the same values), measures again and resizes the tiles.

### How it was measured

- `tools/perf_profile.py --memory BYTES`: the tiles sized from a compute slot's budget; and the
  new Compute bars of step 1 (the gap filling's slopes, rings and medians as parts of one bar, the
  sea mask, the shore zone, the area and surface coverage, the border gaps), listed per part, so
  "Step 1: (between bars)" is gone from its tables.
- `tools/job_stats.py --phases`: the waits for a slot, the phases, the seconds outside the steps,
  the orthophoto and the tiles, from `jobs.sqlite` (also on the VPS host).

### Baseline (before stage 1)

`tools/perf_profile.py` on this PC, cached data, `--ortho never`, `--exclusive`; "24" all threads,
"7" `--cores 7` (one thread per core, as the VPS's worker); wall seconds per step (step 1 with its new
bars summed), the peak RSS of the job. The numba cache was warm (two runs before).

| Job | lines / spots | wall 24 / 7 | start | step 1 | step 2 | step 3 | step 4 | step 5 | peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R9 Montserrat (5 m circle, every profile kept) | 85 671 / 3 972 | 4.6 / 4.8 | 0.8 | 0.2 | 0.2 | 0.1 | 0.4 | **2.7** | 372 MB |
| R40 Preikestolen (1 m circle) | 125 054 / 417 | 4.6 / 4.6 | 0.8 | 1.4 | 0.5 | 0.5 | 0.2 | 1.3 | 339 MB |
| R44 Adršpach (2 m circle) | 37 687 / 1 976 | 4.0 / 4.0 | 0.9 | 0.7 | 0.3 | 0.2 | 0.3 | 1.5 | 323 MB |
| R16 Gozo north coast (sag, 2 m, 11 tiles of 800 m) | 25 906 / 657 | 45.6 / 44.4 | 1.0 | 13.5 | 1.2 | **28.7** (the sag table: 11 × 2.4 s) | 0.8 | 0.2 | 334 MB |
| swiss-long (1 m circle of 2 km, lines of 150-2 500 m) | 1 695 554 / 10 701 | 36.6 / 33.9 | 1.0 | 7.0 | 2.1 | 6.5 / 5.3 | 2.8 | **17.7** | 967 MB |
| Gozo coast, `--tile-size 5000` (6 tiles, the largest 7 604 × 6 602 px) | 689 150 / 4 131 | 72.1 / 73.0 | 1.3 | **50.8** | 7.7 | 1.7 / 3.4 | 3.5 | 6.9 | 2 487 MB |
| Gozo coast, the VPS's tiles (`--memory 4886000000`: 138 tiles of 3 104 × 2 102 px) | 689 150 / 4 131 | – / **436** | 0.5 | **349** | 54 | 8.5 | 12.5 | 11.7 | 753 MB |

- **Step 1 is 70 % of an area's job** with 5 km tiles and 80 % with the VPS's: the mosaics (terrain,
  surface, water mask, the gap fill's) 20 s of the 51, the gap filling's slopes, rings and medians
  15 s, the sea and lakes 5.6 s (its lake levels 4.3), the sea mask 2.4, the rest between bars 5.0
  (the NaN fills, `isnan`, saving the masks). Every one of them runs on one core.
- **The VPS's tiles cost 6 times the 5 km tiles** on the same area (436 against 73 s): 138 tiles of
  6.5 Mpx (898 Mpx in all for an area of 9.65 km², 93 pixels per pixel of the area, against 6 tiles
  of 41.7 Mpx = 250 Mpx with 5 km cores), and per tile fixed costs: the sea mask reads the world water
  polygons for every tile (85 s: `geopandas.read_file(bbox)` 0.6 s a tile), the mosaics open the same
  files again (28 s "stitching terrain"), the area mask (6.6 s), the surface coverage (8.4 s).
  "Anchor prominence and drop" 26 s and "finding anchors" 13 s follow the pixels too.
- **The sag table** (`sag.EnvelopeTable`, 82 lengths) is built for every tile of a sag area: 28.7 s
  of R16's 45.6 (`_sag_table` with `lru_cache` exists for `profile_of_line` and is not used here).
- **Step 5** is 48 % of swiss-long (17.7 s for 1.7 million lines: `lines.csv` + `lines.geojson` 9.1 s,
  `data.js` + `lines.js` 8.6 s) and 58 % of R9 (2.7 s, the profile of every line in `data.js`).
- **The peak**: the Gozo coast's 2 487 MB at the surface pair's medians of the gap filling (the largest
  tile 50.2 Mpx: about 49 B per pixel with the imports, 46 without), as counted above; swiss-long's
  967 MB at step 4's profiles; R9's at step 5.
- "Profiles at tile edges" took no measurable time on either Gozo run (0.0 s): not a target.
- The start (imports and planning) is 0.8-1.3 s on this PC in every run; the worker adds it twice.

### Done, wave 1 (stage 1: the time outside the computing; every result byte for byte)

Branch `perf-round3`, the agents' branches `perf-r3-ortho` (A: 1a, 1h), `perf-r3-worker` (B: 1b, 1d, 1e),
`perf-r3-index` (C: 1c); 1f by hand.

- **1a, the orthophoto after "done"** (A): Until now the compute phase selected and downloaded the orthophoto
  tiles inside step 5, before the map was saved and the job set "done", in the process the scheduler
  counted as an occupied compute slot (on the VPS 85-134 s per job against 15-60 s of computing;
  locally a circle downloads the detail strips of all its groups). Now `search.save_run` saves the run
  and the map and returns; the orthophoto is a step of its own (`search.orthophoto_lines`,
  `search.download_orthophoto`: the same selection rules, question and download), which the CLI
  runs right after `save_run` and the worker after "done" (`jobs.run_phase`: `save_run` → `add_run`
  → statistics → "done" → the lines released → `_orthophoto_after`). The map names the cache folder
  as before and loads a tile online until it is there, so the result is shown while the tiles
  arrive. `Scheduler._occupied` no longer counts a compute process whose job is done, so the next
  job starts beside it; the phase's time limit still ends such a process (the download only: the
  job's status is guarded by `when`), `stop()` kills it like the others, and it holds its imports
  only (the lines are released first), so `slot_memory` reserves nothing for it. Errors of the step
  never touch the job or its run (a warning event, a line on stderr). The orthophoto's seconds still
  land in `job_steps` (its row written after "done"; `tools/job_stats.py --phases` leaves that row
  out of `outside_steps`). Measured on the dev PC with the worker's `Scheduler` (R15's circle at 1 m
  with `--ortho-detail 2`: 87 tiles of Malta's WMS; the base commit against 1a, a scratch cache for
  the tiles, the elevation data cached): time to "done" 18.7 → 6.5 s, the compute phase 17.0 → 4.0 s;
  the orthophoto itself (now after "done") 11.7 → 1.7 s for the same tiles, thanks to 1h's keep-alive
  sessions. With a cold numba cache the same "before" job took 42.7 s to "done" (about 8 s of
  compilation in each of steps 2-4): what 1b removes.
- **1h, the orthophoto's tiles** (A): `orthophoto.tiles_to_cache` tested every tile of the union's
  bounding box at zooms 17-21 against the union of the strips: on a long coast most of that box is
  empty (50 strips spread over 15 km: 0.6 M `prepared.intersects` tests, 72 s). Each strip is now
  tested within its own bounding box, vectorised with shapely 2 (`_tiles_in`: `shapely.box` and
  `shapely.intersects` on the prepared shape, the same float operations per tile), and the set joins
  the strips' tiles: the same tiles in every case (`tests/test_offline.py::test_orthophoto_tiles_per_strip`
  keeps the old code as the reference), 0.03 s for those 50 strips; 60 clustered strips 0.17 →
  0.05 s. Each download thread keeps one `requests.Session` (`net.session`, keep-alive): 87 tiles
  of Malta's WMS 11.7 → 1.7 s. `cache.record_many` still hashes the tiles it records (the sha256
  keeps `fetched_at` for an unchanged file in `cache update`; milliseconds for a run's tiles).
- **1b, the numba warm-up** (B). The public worker's numba cache is a tmpfs, so the first job after
  each start of the container compiled every kernel (about 40 s on the VPS). `warmup.py` now runs
  synthetic searches in a process of its own at the worker's start (`Scheduler(warm_up=True)`:
  `findaline.py worker` and `web`; `FINDALINE_WARM_UP=0` turns it off), while jobs are already
  claimed. The searches cover every combination that gives the kernels other argument types, found
  by comparing numba's cache index after the warm-up with the index after real searches: a surface
  model or none, the water and gap masks memory-mapped or none, a tile's core, `pair_chunk`'s second
  pass, parts of one and of several anchors, thinned profiles and the sag estimator's int default.
  On the dev PC: cold 37 s, from numba's cache 3-5 s; afterwards the Żabi Koń clip's search compiles
  nothing (`tests/test_public.py::test_numba_warm_up`). The VPS's first job after a deploy: to be
  read from `job_stats.py --phases`.
- **1d, the download phase** (B). `search.py` imports the kernels' modules inside steps 2-4, so the
  download phase and the quick lane never load numba and llvmlite: on Windows an R13 download-phase
  process takes 112 MiB instead of 133 MiB (RSS after the phase) and imports in 0.75 s instead of
  0.95 s. `DOWNLOAD_PROCESS_BYTES` stays at 512 MiB: the download itself peaks at 240-400 MiB, so the
  plan's 256 MiB would be too little. `cache.due_many` answers a layer's tiles on one SQLite
  connection: 2 000 tiles in 0.055 s instead of 3.98 s (`due()` of one file opens one connection
  instead of two). The coastline's theme tiles are fetched in a thread alongside the tiles' pool,
  and the layers' estimates are listed at once (`sources.layer.estimate_layers`, which
  `estimate_search` uses).
- **1e, the runs list** (B). `runs.write_index` (`runs.js`, `index.html`) is rewritten after each run
  of the command line and the local app only (`Plan.index_runs`); the public worker skips it:
  nothing on the site reads those files, and the work grew with the site's runs. A run installs the
  viewer once instead of twice.
- **1c, the geoportal sheet index in parallel** (C). A new Polish area asked geoportal's WFS sheet
  index one request at a time: a GetCapabilities per layer and process, then one GetFeature per year
  layer (9 for the NMT, 8 for the NMPT) per 0.25° tile, each on a new HTTPS connection, with the NMT
  and the NMPT one after the other in `estimate_search`. Now `WfsSheets` sends a tile's year layers
  4 at a time on a keep-alive session per thread (`net.session()`), each under a slot of the host
  (`HOST_SLOTS_OF["mapy.geoportal.gov.pl"] = 4`, a courtesy cap: GUGiK publishes no limits),
  `NewestPerSheet` asks the tiles of a grid 4 at a time, and the year layers are kept on disk for
  30 days (`<top>/sheet-index/<prefix>.capabilities.json`: a new year layer is seen within a month).
  The answers are read in the old order, so the index JSON is byte for byte the same; the requests
  and bytes are unchanged. Measured on an empty cache (only `osm/` copied), `estimate_search` against
  the live service, 2026-11-02:

  | Area | Before | After |
  | --- | ---: | ---: |
  | R13, Kasprowy Wierch, r 500 m (one 0.25° tile, 19 requests) | 6.8 s | 2.0 s |
  | 50.0° N 20.0° E, r 3 km (four tiles, 70 requests, 10 MB) | 24.2-24.9 s | 3.5-3.8 s |

  The summed request time fell from 23-24 s to 12-13 s for the four tiles: keep-alive saves the
  handshakes, the rest is the overlap. The sheet downloads themselves (section 2) are unchanged.
- **1f, the sag table once per process.** `_lines` takes the envelope table of a sag search from
  `_sag_table` (by rigging and the lengths; at most `SAG_TABLES_MAX` kept) instead of building a new
  `sag.EnvelopeTable` for every tile, and a tile just computed is not read back from its gzip file
  (`found.without_pixels()`, what loading gives). R16 (11 tiles): 45.6 s → 21.7 s, the same files.
- **1g, the place name in the download phase.** `download_data` asks Nominatim for a circle's or a
  drawn area's place (`_run_name`) in a thread alongside the tiles' pool: the answers land in
  `osm`'s cache, where step 5 (or the run folder of a tiled area) finds them without the 1-3 s in
  Nominatim's queue (more when it is busy). The CLI is unchanged; the worker's Nominatim quota
  counts the lookups as before, in the other phase.
- **Checks.** Full offline `pytest`, `tests/regression.py` (R1, R9, R13, R14, R15, R16, R18) on cached data: every checksum and
  the open and checked counts unchanged.

### Done, wave 2 (stage 2: the memory of step 1 and the size of the tiles; every result byte for byte)

Branch `perf-r3-step1` (agent D: 2b, 2a bis, 2a, 2d; 2c by hand). Measured on this PC with
`tools/perf_profile.py --cores 7` under the exclusive lock, cached data, the code of each commit
exported; the wall times vary by ±10 s between identical runs (medians given), the peaks were stable.

- **2b, `near()` in two passes.** The shore zone and the lakes' shores were n = ceil(metres / res)
  iterations of a 3 × 3 dilation; now a running maximum along the columns, then the rows
  (`scipy.ndimage.maximum_filter1d`, size 2n + 1, 0 beyond the grid): the same Chebyshev ball for
  any n (`tests/test_units.py::test_near_matches_the_dilation`: random, edge, empty and full masks,
  n 1-50). On a 7 600² grid: 0.26 s at 2 B per pixel, against 0.31-0.41 s for the dilation and
  0.33-0.45 s at 13 B per pixel for `distance_transform_cdt` (the contract's first idea, which
  also gives -1 everywhere for an empty mask).
- **2a bis, the world water polygons once per search.** `coast.sea_mask` read the world file
  (`read_file(bbox)`, `to_crs`) for every tile. Now `coast._world_water` reads it once for the
  whole search's grid (`Plan.search_grid`, the `extent` of a tile) and each tile rasterizes the
  polygons whose box reaches it: the same pixels (all 138 VPS tiles of the Gozo coast compared).
  Inside `sea_mask` 0.05 s a tile instead of 0.375; the stage on the VPS's tiles 83 → 31-33 s.
  The coastline mode of Overpass and the extracts (0.06 s a tile) was left as it was.
- **2a, the temporaries and held arrays of step 1.** `_fill` computes the slope in place in one
  gradient and releases both gradients after the flat mask; the median of the overall offset
  partitions its temporary; the ring of labels is multiplied in place. `fill_gaps` releases the
  terrain pair's grid before the surface pair's mosaic; `fill_from_neighbours` computes the border
  gaps again only after a neighbour's `fill_gaps` ran. The mosaics read each window once
  (`_read_band`, `_clean(copy=False)`) and put it in place (`np.copyto`). The water body mask is
  uint8 with `mosaic.NODATA` 255 (reprojected in float32 as before: GDAL's warper chunks a window
  by its bytes per pixel, so a uint8 warp might pick another nearest pixel at a chunk edge).
  `prepare_data` computes the area mask once per grid (`Data.mask`, also step 2's) and releases
  the sea mask and the water body mask after their last use. The code of before is kept in
  `test_gap_fill_as_before` and `test_mosaics_as_before`.
- **2d, the disk estimate.** `search.work_bytes` counts what `prepare_data` writes: float32 the
  terrain, the surface, the obstacles, a slope file and each fallback's terrain and surface; uint8
  the water body mask; boolean the water, filled and joined masks. About 23 B per pixel instead
  of 4 per layer (`tests/test_offline.py::test_work_estimate_counts_the_grids_written` compares
  it with the files of a search).

| Job | wall before → after | step 1 | step 1's peak RSS | B per pixel of step 1 (the largest tile, 7 604 × 6 602 = 50.2 Mpx, the start's 135 MB taken off) |
| --- | ---: | ---: | ---: | ---: |
| Gozo coast, `--tile-size 5000` (5 runs before, 2 after) | 62-85 (76) → 60-68 s | 41-63 (55) → 38-46 (42) s | 2 387-2 552 (2 530) → 1 704-1 805 MB | **47.7 → 32.3** |
| the same with `--tracemalloc` | 138 → 131 s | 41.0 → 37.5 s | 2 533 → 1 977 MB (traced heap 1 673 → 1 344 MB) | heap only: 33.3 → 26.8 |
| Gozo coast, the VPS's tiles (`--memory 4886000000`, 138 tiles) | 409 → 351 (2a bis) → 347 s | 332 → 275 → 275 s | 767 → 761 → 680 MB | – |
| R16 (3 runs before, 2 after) | 19.3-21.4 → 15.1-16.9 s | 13.4-15.2 → 9.7-10.4 s | 327-337 → 291-307 MB | – |
| R9 | 4.6 → 4.6 s | 0.2 → 0.2 s | 373 → 369 MB | – |

- The peak of step 1 is still at the surface pair's medians of the gap filling (1 805 MB); the
  rings part fell from 2 266 to 1 553 MB, "(between bars)" from 1 562 to 1 077 MB. The 25-30 B
  the plan hoped for was not reached: the rest is the memory-mapped grids read so far (16 B)
  and `_fill`'s labels and ring (int32).
- Byte for byte: `lines.csv`, `lines.geojson` (up to its "findaline" part), `data.js` and
  `lines.js` (from their "lines") of R9, R16 and the Gozo coast with 5 km tiles and with the
  VPS's tiles; every grid of step 1 per tile of R9, R16 and the Gozo coast 5 km by sha256 (nmt,
  nmpt, obstacles, wbm, water, filled, gap_nmt, gap_nmpt, the sea mask, every `near()` and the
  area mask); the world-file sea masks of all 138 VPS tiles read once against read per tile;
  `tests/regression.py` R1 R2 R4 R9 R13 R14 R15 R16 R18 on cached data, every checksum and the
  open and checked counts unchanged.

#### 2c: the memory model and the tiles (by hand, after the measurements)

- `PIXEL_BYTES` 100 → **50**: step 1 peaks at 32 B per pixel on Windows (above) and at 38 where
  a neighbour's data fills a border first (a Tatras circle at 1 m, 49.188° N 20.06° E, r 3 km:
  6 601² = 43.6 Mpx, 49 % from geoportal.gov.pl and 24 km² joined from Slovakia's DMR 5.0:
  1 785 MB at the surface medians of that border fill, the highest measured: the neighbour's
  windowed grids over half the grid); step 2 at 25 with dense anchors: swiss-long (21.2 Mpx,
  522 000 anchors, 2.5 % of the pixels: the prominence and drop at 670 MB over the start's 140)
  and the Tatras (2.65 million anchors, 6.1 %: 1 192 MB, 24.7 B per pixel); step 3 at 16 (the
  Tatras: 815 MB). The quick lane's reserve of a compute slot's budget (`slot_memory`: a grid of
  `MAX_MEASURED_PX`² at `PIXEL_BYTES`) falls from 3.6 to 1.8 GB, so the VPS's three slots get
  about 5.5 GB each instead of 4.89.
- `TILE_MEMORY_SHARE` 0.25 → **0.5**: the grids of a tile may take half the budget (the lines
  the rest; a search over it is refused by `_check_lines`, early with F7).
- `TILE_PX_MAX` (new): a tile has at most this many pixels with its overlap, whatever the
  memory; a PC with much memory would otherwise take one tile of hundreds of Mpx (this PC: 280
  Mpx, 9 GB of grids) to save little work: the overlap's share of a tile falls slowly once the
  core is a few overlaps wide. A site's `grid_mpx_max` below it applies as before, `--tile-size`
  too. Merged at 64 Mpx (about 2 GB of grids); the user chose **100 Mpx** (3.2 GB) on 2026-11-03,
  and raised the public `grid_mpx_max` from 36 to **64 Mpx** at once (3.2 GB of grids at
  `PIXEL_BYTES` and `LINES_MAX` × 450 B = 0.7 GB of lines in a slot of about 6 GB). A cap on the
  core's overlaps (the plan's "4 overlaps") was tried first and dropped: it cut the cores of
  short lines (`typical` 5 000 → 1 500 m) where the memory allows large ones. With these, at 1 m:

| Lines up to | overlap | VPS before: core, pixels per pixel of the core | VPS after (64 Mpx; 36 Mpx would give) | this PC after (100 Mpx; before: about 70 Mpx tiles) |
| ---: | ---: | ---: | ---: | ---: |
| 150 m (`typical`) | 452 m | 2 500 m, 1.85 | 6 500 m, 1.30 (5 000 m, 1.39) | 9 000 m, 1.21 |
| 400 m (`long`) | 702 m | 2 000 m, 2.9 | 6 000 m, 1.52 (4 500 m, 1.72) | 8 500 m, 1.36 |
| 1 000 m (the default) | 1 302 m | 500 m, **38.5** | **4 500 m, 2.5** (3 000 m, 3.5) | 7 000 m, 1.9 |
| 2 000 m (the public maximum) | 2 302 m | 500 m, **104** | 2 500 m, 8.1 (1 000 m, 31) | 5 000 m, 3.7 |

- The Gozo coast with 3 000 m cores (`--memory 3140000000`, what the VPS would get for the
  default lines with the site's 36 Mpx) against its 500 m cores (138 tiles, 347 s after 2a): 17 tiles of at most 5 104² px (26 Mpx) in 96.5 s (step 1 67.5 s, step 2 13.5 s), the peak 1 115 MB: 3.6 times faster than the 500 m cores (347 s: step 1 275 s, step 2 48.5 s; 680 MB) and 1.6 times slower than this PC's 5 km cores (60 s, 1 704 MB).
- A circle of the public maximum radius (3 500 m) at 1 m is 7 601² = 57.8 Mpx with the margin:
  allowed with 64 Mpx, refused before (a coarser resolution was needed).
- `tests/test_units.py::test_tile_at_most_tile_px_max` and the cgroup test (the tiles follow the
  container's memory up to the cap), `tests/test_public.py::test_memory_of_compute_slots` (the
  budget per slot, the warning when the largest public search does not fit).
