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
| `tools/perf_window_reads.py --out <dir> --source <id> --lat .. --lon .. --radius 800 --mode blocks --mode group=5000 ...` | The blocks of a layer read by windows of big remote files on an empty scratch cache, each mode in a child process: bytes and requests (GDAL's network statistics and our own range requests), seconds, peak memory, and what the files' internal tiles predict ("Window reads") |
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
| F8c | cells outside the anchor's open sectors, or without a partner open towards it; per partner the anchor's largest ring in the cell's sectors and the partner's open sectors | a further 10-35 % of the visits; done 2026-11-03 (wave 4 of round 3): 55-73 % of the visits left after F2 + N1, the pair search 17-52 % faster | high |
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
  `_evaluate` ("checking lines", now about a third of swiss-long's line search CPU). (Wave 4 of round
  3, 2026-11-03: F8c done; L not needed for its mask; the long lines' order and `_evaluate` measured
  and left: "Done, wave 4" of round 3.) Planned next:
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

### Done, wave 3 (stage 3: the one-core parts of steps 2-5; every result byte for byte)

Branch `perf-r3-wave3`: the merges of `perf-r3-step2` (agent F: 3a, 3e), `perf-r3-step5` (agent G:
3b) and `perf-r3-step34` (agent H: 3c, 3d), all from a432d15. Each agent measured on this PC with
`tools/perf_profile.py` under the exclusive lock, cached data, the code of a432d15 exported as the
base, base and new interleaved, numba warm. The wall of a whole run moves by ±10 s between
identical runs on this busy PC; the stages are what counts.

- **3a, step 2** (F). Step 2 of `_lines` is `_anchors(plan, data, quiet)` → `Anchors(anchors,
  prominence, drop, strong)`, the shape the branch `country-precompute` shares (None for a tile
  without anchors; the same `SearchError`s otherwise). The seams of filled gaps and a neighbour's
  data are tested at the anchors only (`search.at_seams`: nine gathers at the anchors instead of
  scipy's 3 × 3 dilation and erosion over the whole grid, with the outside of the grid as no gap;
  `test_seams_as_before` keeps the old expression on 30 shapes with edge, corner, empty and full
  masks). `helpers.find_significant_slopes` runs its blocks (256 rows now, 512 before) on a thread
  pool of `line_threads` (numpy releases the GIL; the slope in place, about 3 float32 copies of a
  block in flight per thread) and joins the anchors in the blocks' order, exactly the one pass's
  row-major order (`test_significant_slopes_as_before`: block sizes 1-2000, 1-8 threads, NaN, a
  slope raster; numpy 2.5.4's float32 `hypot`/`arctan`/`degrees` give the same values for any
  slice offset and in place). `terrain.prominence` skips its lexsort when the anchors come
  row-major (0.24 s at the Tatras' 2.65 million anchors). On the Gozo coast with 5 km tiles step 2
  fell 7.7-8.2 → 3.8-4.1 s (finding anchors 2.4 → 0.5 s, the seams 1.8 → 0 s) and the peak by
  50-130 MB (the two full-grid seam masks are gone).
- **The prominence's sort and union-find** were measured and left as they are. On the Gozo coast
  (6 tiles, 52 M window pixels): the window 0.3 s, the argsort 0.9 s, the union-find 2.0 s, the
  drop 0.35 s; under 0.2 s each on R40 and R41. The sort is 1.5 % of the job; the union of the
  windows is one 8-connected component per tile (two on two tiles, the largest holding 89-93 %),
  so a union-find per component would have nothing to run in parallel.
- **3e, the mosaics' decoding** (F). `build_mosaic` opens the cached files with `GDAL_NUM_THREADS`
  = `WARP_THREADS` (GDAL reads it when a file is opened), so their DEFLATE blocks decode on several
  threads: 60 of Malta's 2 000 px tiles 3.6-3.9 → 1.2 s on 7 threads, FABDEM's 36 tiles 6.8-7.1 →
  2.4 s (the arrays' hashes equal). The Gozo coast's mosaics 15.6-15.8 → 12.2-12.7 s on 7 cores
  (the terrain's stitching 3.3-4.6 → 1.6-2.3 s; the surface and gap-fill mosaics are mostly the
  reprojection, threaded already). Remote reads keep one thread (`net._gdal_http`).

| Job (F) | cores | wall before → after | step 1 | all mosaics | finding anchors | seams | prominence and drop | step 2 | peak RSS MB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gozo coast, `--tile-size 5000` | 7 | 68.7-71.4 → 61.8-63.3 | 47.5-48.6 → 43.3-45.8 | 15.6-15.8 → 12.2-12.7 | 2.4 → **0.5** | 1.7-1.8 → **0.0** | 3.6-4.0 → 3.5-3.6 | **7.7-8.2 → 4.0-4.1** | 1 784-1 850 → 1 705-1 720 |
| Gozo coast, `--tile-size 5000` | all (24) | 69.4-70.5 → 59.4-63.6 | 47.3-48.9 → 43.0-46.3 | 14.0-17.7 → 13.4-13.8 | 2.4-2.6 → 0.5-0.6 | 1.9 → 0.0 | 3.6 → 3.3-3.5 | 7.9-8.1 → 3.8-4.1 | 1 790-1 871 → 1 753-1 761 |
| R41 | 7 | 6.1-8.1 → 5.8-6.6 | 2.5-3.2 → 2.3-3.2 | 0.6-1.2 → 0.5-0.9 | 0.1 → 0.0 | 0.0-0.1 → 0.0 | 0.5-0.7 → 0.5 | 0.6-0.9 → 0.5 | 371-390 → 358-374 |
| R40 | 7 | 4.4-4.9 → 4.2-4.5 | 1.2-1.4 → 1.0 | 0.3-0.4 → 0.1 | 0.0 | 0.0 | 0.4 | 0.4 | 316-332 → 311-313 |

- **3b, step 5 in processes of its own** (G). The texts of `lines.csv`, `lines.geojson`,
  `data.js` and `lines.js` were built on one core (18-20 s of swiss-long's 37 on this PC, 112 s
  for 2.07 million lines on the VPS). A run of `saving.MIN_LINES` (100 000) lines or more hands
  its lines to children when the line search has 2 or more threads (`saving.processes`: 2 and 3
  threads two children, the results' files apart from the map's; 4 or more four, one per file).
  `saving.hand_over` writes the columns of the `LineTable`, the groups' arrays and the arrays of
  every `helpers.Profiles` batch the profiles come from as `.npy` in the search's work folder,
  plus run.json's values, the dict profiles of tile edges and the scripts' heads
  (`mapping.map_heads`) as JSON; each child (`python saving.py <folder> <run> <files>`, a plain
  subprocess: the worker's phase process is daemonic and may not start multiprocessing's) maps
  them and runs the same writing functions (`runs.save_results(files=)`,
  `mapping.write_map_scripts`), so every file is byte for byte the one process's. A child's
  progress reaches the bars through its stdout (the parent reads "<count>\t<file>" lines; "saving
  results" shows the slower of csv and geojson, the parent writes ATTRIBUTION.txt, run.json and
  the tiled run's "done" between the bars as before, then "saving the map"); its stderr fails the
  step as a `RuntimeError` (redacted on the public site as every error); the hand-over folder is
  removed afterwards, also on failure. Measured on 7 cores: swiss-long's step 5 19.8-20.3 →
  12.7-13.1 s (the slowest child, lines.geojson, sets it: each child makes the texts of its values
  itself, and a child takes about 1.2 s to start and import numpy, runs, mapping and rasterio
  through grid, never `search`); with the children forced R9's 3.0-3.1 → 3.4 s and R44's 1.8 → 2.3
  s, hence the threshold. With all 24 threads swiss-long gave 18.4-18.8 s, unexplained (five
  processes on SMT siblings?). The VPS's core is about 4 times slower per line (112 s / 2.07 M
  against 12 µs a line here), so its break-even lies lower, perhaps 50 000: to read from
  `tools/job_stats.py` after a deploy. Memory: the parent holds the table as before (`LINE_BYTES`
  counts it); each child about 75 MiB of imports plus the mapped pages, file-backed and shared
  (about 200 B per line of page cache in all, reclaimable in a cgroup): swiss-long's tree peaks at
  2 469 MB of RSS (4 × 340 MB for the children) over the parent's 906-938, physically about 350 MB
  plus the imports. `tests/test_units.py::test_saved_by_children_as_in_process` (50 000 synthetic
  lines with a profiles batch, dict profiles, lines without one, the hard floats; 4 and 2
  children; the bars; a failing child) and `tests/test_offline.py::test_run_saved_by_children_as_in_process`
  (the Żabi Koń clip through `save_run` with 1, 4 and 2 processes: every file equal).

| Search (G, lines) | threads | step 5 before → after | job peak RSS MB | tree peak after |
| --- | --- | ---: | ---: | ---: |
| swiss-long (1 695 554) | 7 cores | 19.8-20.3 → **12.7-13.1** | 906-938 | 2 469 (4 children of about 340) |
| swiss-long | all (24) | 20.9-21.3 → 18.4-18.8 | 901-922 | 2 479 |
| R9 (85 671, every profile; the children forced) | 7 cores | 3.0-3.1 → 3.4 | 360-365 | 790 |
| R44 (37 687; forced) | 7 cores | 1.8 → 2.3 | 327-332 | 686 |

- **3c, the exact fixes of steps 3-4** (H). `linesearch.covered_metres` rounds whole parts with
  `runs.round_floats` instead of Python's `round()` per line (the same float64 products and
  quotients, 0.0 where no pixel is set; `test_covered_metres_as_before` keeps the old code, with
  the halfway cases of lines along a row or a column at 0.25 and 1.25 m): 0.86 → 0.17 s per mask
  for swiss-long's 1.7 million lines. `mapping.coordify` transforms each part's different anchor
  pixels once (`np.unique` on a pixel key, the coordinates gathered back; a part of 2¹⁷ lines of
  swiss-long holds about 7 000 different pixels of its 262 144 anchors; `test_coordify_as_before`:
  five CRSs, the grid's corners, parts of 1, 777 and 2¹⁷ lines, compared by `tobytes`): 1.14 →
  0.18 s, swiss-long's step 4 2.7-2.9 → 1.6-1.7 s. `linesearch._evaluate` walks the sag table's
  index forward along a line (`_interp_forward`: the index of `searchsorted` and the arithmetic of
  `_interp`, `test_interp_forward_matches_interp`) instead of a binary search per pixel: a bench of
  237 625 sag pairs 0.18-0.22 → 0.16 s; the "checking lines" stage of R16 and R5 (0.0-0.1 s) is
  too short to show it. The `row` buffer per line stays (42 floats; a per-thread buffer needs
  numba's thread ids for no measurable gain).
- **3d, the profiles at tile edges** (H): measured and left. None on the Gozo coast's 5 km tiles;
  10 on its 9 tiles of a VPS slot (`--memory 4886000000` after wave 2's tiles), 5.0 s in all (0.5
  s each, about 6 % of an 81 s run). About one per tile, so no batch of extra profiles inside
  `_lines`. The baseline's 0.0 s for "profiles at tile edges" was a measuring artefact:
  `profile_of_line` runs `prepare_data`, whose `_step` moves the progress step to step 1, so
  `tools/perf_profile.py` lists those seconds under step 1's stitching and filling stages. With
  the 138 tiles the VPS had before wave 2 the count was likely larger.

| Run (H) | threads | wall before → after | step 4 | coordinates | over water and gaps | checking lines | peak RSS MB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| swiss-long | 7 cores | 42.4 → 40.5 | **2.7 → 1.6** | 1.1 → 0.2 | 0.6 → 0.4 | 1.8 → 1.9 | 937 → 903 |
| swiss-long | all (24) | 36.4 → 36.3 | 2.9 → 1.7 | 1.1 → 0.2 | 0.7 → 0.3 | 1.2 → 1.2 | 928 → 904 |
| Gozo coast, `--tile-size 5000` | 7 | 58.4 → 61.0 | 2.8 → 2.5 | 0.2 → 0.1 | 0.3 → 0.1 | 0.3 → 0.3 | 1 826 → 1 697 |
| Gozo coast, the VPS's tiles (`--memory 4886000000`, 9 tiles) | 7 | 97.5 → 80.9 | 3.4 → 2.9 | 0.2 → 0.1 | 0.3 → 0.1 | 0.4 → 0.3 | 1 426 → 1 512 |
| R16 (sag) | 7 / 24 | 24.4 → 15.9 / 16.6 → 16.7 | 0.7 → 0.6 | 0.0 | 0.0 | 0.0 | about 300 |
| R5 (sag) | 7 / 24 | 6.3 → 6.3 / 6.3 → 6.1 | 0.0 | 0.0 | 0.0 | 0.1 | 270-300 |

- Byte for byte (each agent, base against new): `lines.csv` whole, `lines.geojson` up to its
  "findaline" part, `data.js` and `lines.js` from their "lines": F's 12 pairs of R40, R41 and the
  Gozo coast with 5 km tiles (7 cores and all threads, two rounds); G's 29 runs of swiss-long, R9
  and R44; H's swiss-long (7 and 24 threads), R5, R9, R13, R16 and the Gozo coast with 5 km tiles
  and with the VPS's tiles. `tests/regression.py` on cached data: F R1 R4 R9 R13 R14 R16 R22 R40
  R41, G R9 R13 R16 R40 R44, H R5 R9 R14 R16 R22, every checksum and the open and checked counts
  unchanged. The full offline `pytest` from PowerShell on each branch (784-785 passed).
- Not done: a measurement on Linux (the process start and the per-line cost of 3b differ there);
  `locales/en.json`'s help of `--threads` does not name the children (the CLI's text does).

### Done, wave 4 (stage 4: the pair search, byte for byte; step 1 once per area, which may change the results of tiled areas)

Two branches from 42adde3, each measured on this PC with `tools/perf_profile.py` under the exclusive
lock, cached data, the code of 42adde3 exported as the base, base and new interleaved (two rounds),
numba warm; "7" `--cores 7` (the VPS's worker), "all" 24 threads. The wall of a whole run moves by
±10 s between identical runs on this busy PC; the stages are what counts.

- **4c, F8c** (agent P, branch `perf-r4-pairs`, one commit in `linesearch.py`; every result byte for
  byte). `_pairs` skips, before a partner's data is read: the cells none of whose sectors from the
  anchor is open for the need of the cell's nearest pixel (`_cell_sectors`: the sectors of a cell's
  corners with one of margin for atan2's rounding, `_arc`; the rings as production holds them,
  capped at `largest_need`), the cells no anchor of which has a sector open for the shortest line's
  need (`smallest_need`) towards the anchor (`_cell_open`: a uint64 of open sectors per cell), and
  per partner those whose need exceeds the anchor's largest ring in the cell's sectors and those
  with no sector open towards the cell (`_open_masks`: a uint64 per useful anchor, 8 B each; the
  mask is read by `slot[j]`, which N1 reads already, so L's cell-order layout is not needed for it).
  All of them fail the rings test, so the written pairs, their order and the checked and found
  counts are the frozen references' (`analyse`'s self-check on six captures: R13, R9, R4, R22, the
  Gozo coast's tiles 1-2, swiss-long; `test_f8c_skips_only_rings_failures` on random grids with
  raised blocks, `test_cell_sectors_hold_every_pixel`), while the candidates counted fall to 20-49 %
  of before (F19's note in docs/monitoring.md). The per-partner mask went in after it was measured
  as a variant: never slower, 3-13 points more. `_pairs` gained two array arguments of a shape every
  search gives, so `warmup.SEARCHES` is unchanged (`test_numba_warm_up` passes).
- **Measured and left** (P): the middle of lines over 1024 px (`LINE_ORDER_MAX`): 94 % of
  swiss-long's checked lines over 500 px fail at their first three pixels and 1.6 % between 64 and
  1023 px from an end, so the best order for them (a full bit reversal, +8 % of time for its cache
  misses in wave 2) would save 17.7 % of swiss-long's pixel tests, about 7 % of its pair search's
  CPU and 3 % of the job's, 3.4 % of R4's tests and nothing elsewhere (no other search measured has
  such lines; "R22-long" is not cached beyond 400 m, R4 stood in): below the noise, the order stays.
  `_evaluate` ("checking lines"): 19-21 % of swiss-long's CPU on 7 cores but 6 % of its wall (1.7 M
  found pairs of up to 2 500 px, about 1.4 G pixel visits at 17 ns each with a surface model: two
  grid reads per pixel of a line that crosses a row per pixel, memory-bound), 2.5 % of the Gozo
  coast's CPU, under 0.1 s of wall elsewhere; not changed.

| Search (P, `analyse`) | visits | skipped by F2a + F2b + N1 (wave 2) | + F8c (cumulative) | F8c of the visits left after wave 2 | of it the anchor's own cell rule | candidates counted before → after |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| R13 | 5.5 M | 39.0 % | 83.3 % | 72.6 % | 50.0 % | 176 k → 49 k (28 %) |
| R9 | 399.8 M | 66.5 % | 90.9 % | 72.9 % | 71.6 % | 11.2 M → 2.2 M (20 %) |
| R4 | 8.6 M | 51.0 % | 77.8 % | 54.8 % | 52.5 % | 1.9 M → 0.42 M (21 %) |
| R22 | 752.2 M | 49.5 % | 83.3 % | 66.9 % | 59.4 % | 8.3 M → 1.6 M (20 %) |
| Gozo coast (tiles 1-2) | 436.5 M | 60.3 % | 83.9 % | 59.5 % | 60.8 % | 57.3 M → 16.4 M (29 %) |
| swiss-long | 9 801.9 M | 45.2 % | 78.0 % | 59.8 % | 47.9 % | 287.5 M → 141.0 M (49 %) |

The per-partner mask skips 5-8 % of all visits but 45-98 % of the candidates F8c removes (each sparing
two atan2 calls). The pair search alone (`pair_chunk` over a capture's chunks, each version in its own
process, medians of 3 runs in two rounds; 23 / 7 threads): swiss-long 2.04 / 4.62 → 1.69 / 3.64 s
(-17 / -21 %), the Gozo coast 0.25 / 0.58 → 0.18 / 0.28 (-30 / -52 %), R9 0.072 / 0.131 → 0.050 /
0.075, R22 0.070 / 0.118 → 0.047 / 0.074; R4 and R13 within noise. Whole jobs: the "anchor pairs"
bar's CPU -18 % on swiss-long (24.0 / 21.7 → 20.3 / 17.1 s on 7 cores, 45.9 → 38.7 / 36.6 on all),
-35 / -24 % on the Gozo coast with 5 km tiles (9.8 / 9.5 → 6.2 on 7 cores), -40 % on R22 and R9 on 7
cores; the jobs' CPU 0-9 % less, their wall within noise (steps 1, 4 and 5 on one core set it), the
peak RSS within noise. Byte for byte on all 26 base / new pairs (R13, R9, R4, R22, swiss-long, the
Gozo coast with 5 km tiles; 7 cores and all threads, both rounds and the warm-ups): `lines.csv`
whole, `lines.geojson` up to "findaline", `data.js` and `lines.js` from "lines". A pitfall for the
record: a module copy loaded with `importlib` under another name poisons numba's on-disk cache of
that file with a `<dynamic>` module name (every later import fails with "No module named
'<dynamic>'"): time each version in its own process with a normal import.

- **4a, step 1 once per area** (agent S, branch `perf-r4-step1`; the results of tiled areas may
  change). Step 1 of a tiled search (the mosaics, the sea mask, the shore zone, the gap and water
  filling, the obstacles, the terrain statistics) ran for every tile on the tile's grid with its
  overlap, so an area cost 2.5-8 pixels of step 1 per pixel of its area (38 with the VPS's tiles at
  the default length, "The tiles of an area on the public site" above) and every tile decoded the
  same cached files again. `search_lines` now runs step 1 once on the whole grid
  (`prepare_data(strips=True)`: the grid a search of one grid would use, so an area's gap offsets,
  lake levels and border gaps are the area's) in strips of rows of about 4 Mpx (`filling.STRIP_PX`)
  with a halo of each operation's reach, the grids memory-mapped in the work folder, one int32
  array of labels in memory at a time (the lakes, the border gaps, each gap pair in turn), the gap
  filling's overall offset an exact selection on the float32 bits of the matched differences
  (`_median_of`, `_select`: np.median's value, the mean of two middle values, without holding
  them), the ring medians from the ring pixels only, the rasterizations (the polygon area mask,
  the world water polygons, the coastline's faces, the border gaps' footprint) burned whole into
  memory-mapped masks (`rasterize_into`: GDAL's all_touched burn is not strip-invariant at a
  polygon's tangent row), the mosaics warped in destination strips (`_warp`: same-CRS rasters bit
  for bit; a cross-CRS warp, FABDEM, Copernicus, the water mask, within rasterio's approximate
  transformer (`tolerance=0.125`), as a tile's extent made it differ from one grid before). Each
  tile then copies its window into contiguous memmaps of `work/tile<k>/` (`_tile_data`, through a
  mapping opened for the copy, so the area's pages leave the working set) and runs steps 2-4 as
  before (the kernels' argument types unchanged, `warmup.py` untouched); the terrain histograms are
  counted per tile core on the unfilled terrain (`Data.tile_terrain`), so the tiles' files and
  resuming are as they were (the area's grids are made again on resume, removed after the last
  tile). `estimate_search` counts the area's grids, `AREA_TEMP_BYTES` (4) of temporaries and the
  largest tile's copies (`tile_bytes`, about 10 B/px): the Gozo coast at 1 m writes about 3.4 GB
  for 126 Mpx (1.15 GB for its largest tile before); the CLI's disk question applies. The data
  lines of a tiled search are the area's now ("Elevation data: X % of the search area", "Filled
  … km²", "N of M tiles without data": once, not per tile), and `profile_of_line`'s own step 1
  during "profiles at tile edges" leaves the step and the bars alone (`_silent_progress`: wave 3's
  measuring artefact, its seconds listed under step 1, is gone; they sit in step 4's bar now). The
  country layer keeps its step 1 per tile (`country.TileWork`). Tests: `test_near_rows_as_near`,
  `test_median_of_rows_is_np_median`, `test_fill_rows_as_before` (4 seeds × strip heights 1-500,
  with and without a neighbour's window), `test_fill_water_rows_as_before`,
  `test_border_gaps_rows_as_whole`, `test_rasterize_into_as_whole`, `test_mosaic_rows_as_whole`
  and `test_area_in_tiles_with_water_and_gaps` (the Żabi Koń clip with a sea, a lake, gaps on land
  and of the surface, an offline water mask and a fallback source: tiles against one grid,
  `lines.csv` byte for byte, the same terrain); the old `test_area_in_tiles` passes unchanged.

| Job (S) | cores | wall base → new | step 1 | step 2 | step 3 | step 4 | step 5 | peak RSS MB base → new |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gozo coast, `--tile-size 5000` (126 Mpx, 6 tiles, the largest 50.2 Mpx) | 7 | 48.4 / 48.4 → 36.5 / 39.1 | 34.0 / 33.8 → 20.7 / 21.3 | 3.9 → 3.9 / 4.0 | 2.2 → 2.2 / 2.3 | 2.5 → 3.9 / 4.9 | 4.7 → 4.7 / 5.5 | 1 853 / 1 784 → 2 851 / 2 852 (step 1); step 2 1 028 → 1 287 |
| Gozo coast, `--tile-size 5000` | all | 50.6 → 42.6 | 35.9 → 25.2 | 4.0 → 4.8 | 1.6 → 1.8 | 2.7 → 4.5 | 5.2 → 5.2 | 1 801 → 2 851 |
| Gozo coast, the VPS's tiles (`--memory 4886000000`: 9 tiles, the largest 37.4 Mpx) | 7 | 59.4 / 60.2 → 47.8 / 48.0 | 44.5 / 44.9 → 24.3 / 23.8 | 4.7 / 5.0 → 6.0 / 5.7 | 2.2 → 2.5 / 2.4 | 2.7 → 9.8 / 10.9 | 4.8 → 4.7 | 1 492 / 1 477 → 2 869 / 2 855; step 2 884 / 835 → 1 369 |
| R16 (3 452 × 1 069 px, 11 tiles) | 7 | 13.2 / 13.5 → 9.0 / 9.0 | 8.0 / 8.3 → 1.7 / 1.6 | 0.7 → 0.7 | 2.7 → 2.7 | 0.7 / 0.5 → 2.8 / 2.9 | 0.3 → 0.3 | 319 / 317 → 321 / 299 |
| R14 (1 301 × 1 300 px, 15 tiles) | 7 | 9.9 → 4.1 | 7.1 → 0.8 | 1.1 → 1.1 | 0.1 → 0.1 | 0.6 → 1.2 | 0.0 | 319 → 299 |
| Tatras, a 3 km circle as a polygon at 1 m with `--tile-size 2500` (43.5 Mpx, 9 tiles, the largest 26 Mpx; the border filled from ÚGKK SR) | 7 | 102.9 / 101.9 → 73.9 / 75.7 | 58.3 / 57.5 → 21.9 / 23.3 | 16.5 / 16.6 → 17.4 | 16.9 / 16.7 → 17.0 / 17.2 | 3.7 → 10.2 / 10.6 | 6.1 / 6.0 → 6.0 / 5.8 | 1 801 / 1 742 → 2 288 / 2 019 (step 3) |
| swiss-long (one grid, the control) | 7 / all | 25.2 → 25.4 / 25.2 → 25.2 | 3.5 → 3.5 | 1.6 → 1.7 | 7.1 → 7.3 / 3.7 → 3.7 | 1.4 → 1.4 | 10.3 → 10.2 / 13.7 → 13.9 | 898 → 898 |

- Step 1 by stage on the Gozo coast with 5 km tiles (7 cores, base → new): the stitching of the
  terrain and surface 1.3 / 1.3 → 0.7 / 0.7 s, the water mask 1.1 → 0.7, the sea mask (world file)
  1.0 → 0.7, the shore zone 0.9 → 0.4, the gap fill's mosaic 3.3 → 2.1, the gap filling of both pairs
  12.6 → 8.5 (the strip medians cost about what the whole did; the slopes and rings less), the sea
  and lakes 4.0 → 2.1, the surface coverage 0.7 → 0.4, between bars 7.0 → 3.7; with the VPS's tiles
  the world-file sea mask 4.4 → 0.7 s and between bars 9.5 → 4.2; the Tatras' ÚGKK mosaic 16.6 → 9.9
  s, between bars 13.1 → 2.2. Step 4 grew where there are profiles at tile edges (R16 3, the VPS's
  tiles about 10, the Tatras): those seconds were listed under step 1 before; the total did not grow.
- **Memory.** Step 1 no longer peaks per tile but per area: about 23 B per pixel of the area of
  RSS on Windows (the Gozo coast's 126 Mpx: 2 850 MB at the surface pair's medians, against 1 850
  MB for its 50 Mpx tile before; the VPS's tiles 22.7 B/px of the area, base 11.2; the Tatras 24.2,
  base 23.3; R16 32.7, base 45.5), of which 4 B the int32 labels and the rest the resident pages of
  the memory-mapped grids written and read in strips (file-backed, reclaimable under a cgroup's
  pressure, counted as RSS on Windows; `--tracemalloc` was not run). Steps 2-3 of a tile stay at the
  tile's grids (the 50 Mpx tile 1 287 MB in step 2, about 23 B per pixel of the tile, within
  `PIXEL_BYTES` 50, since a tile's window is read through a mapping of its own). Disk: the area's
  grids (23 B/px plus 4 of temporaries at the peak) and one tile's copies (about 10 B/px) in the work
  folder. Whether the tiles may now grow (step 1 costs no more per tile, only steps 2-4's overlap
  does) is an open decision; `PIXEL_BYTES` and `TILE_MEMORY_SHARE` are unchanged.
- **The results.** The Gozo coast (both tile sizes) and R14 are byte for byte the base's, both rounds
  (the new code is deterministic: two Tatras runs equal). R16 keeps its 25 906 lines and 421 spots;
  12 lines near 36.0795° N 14.2497° E have `height_max` / `height_mean` moved by 1-3 cm (the FABDEM
  gap offsets are the area's). The Tatras area with the Slovak border fill changed on its Slovak
  side: the base filled the Slovak part per tile (nine fills of 4-14 km², each tile's piece of the
  border gap with its own ring median), the new code once (19.51 km²) with one ring median per
  connected border gap, the FABDEM fill likewise (6.62 km² once against 1.4-3.0 per tile): 898 658 →
  877 081 lines, 12 606 → 11 982 spots, 46 477 lines only in the base, 24 900 only new, 505 714 with
  other values (clearances, anchor heights by 0.01-1.2 m, wall angles, 7 232 `over_trees` flips),
  495 k of the 506 k changed and all of the lost at a lower anchor south of 49.185° (the Slovak
  side; north of 49.19° 97 k of 112 k lines unchanged). One offset per gap is consistent at tile
  borders (no steps between tiles any more) but ignores a trend of the height difference along a
  long border: open (a per-strip or distance-weighted offset would be a new design). Re-baselined
  (bf0cd6f): R14's `filled_km2` 0.24 → 0.74 (the whole area's FABDEM fill, the first tile's before),
  its lines still R1's (`same_as`); R16's checksum, coverage 51.53 → 49.48 %, filled 0.98 → 2.58 km²,
  sea 1.87 → 6.08 km² (counted once over the area), the counts unchanged; R18 is one grid on this PC.
- Checks: each agent's full offline `pytest` from PowerShell (1022 passed, 56 skipped) and
  `tests/regression.py` on cached data (P: R1 R4 R5 R9 R13 R14 R16 R22 R40, 9 ok; S: R1 R9 R14 R16
  R18 R40 R41, R14 = R1), repeated by the session on both branches (1022 passed each; P's set and R1
  R9 R14 R16 R18 R40 on S, all ok). Not done: a measurement on Linux, `--tracemalloc` of 4a's
  mapped pages, 4b (the tiles in parallel, next round), the `bytes` plan of the contract (the
  one-grid path is covered by the checksums and swiss-long's four files byte for byte).

## Round 4 (2026-11-04): the country layer

The runs of Slovakia's pilot (`countries/slovakia`: 3435 tiles of the bands S, M, L and M2, counted
on 2026-11-02/03 on this PC, 12 cores / 24 threads and 61.6 GiB of which other programs held 35 GiB,
the code of 1f3ad11, before F8c), read from the manifest, the tiles' meta, the logs and the timeline
of the M2 run (the scripts: `local/country-perf-2026-11-04/scripts/`). Three dimensions as in round 3:
the wall of a run from its start to its end, the CPU of its tiles, the memory of a worker.

### What the runs showed

| Run | Bands | Workers | Wall | Tile seconds | Workers busy | Tail |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-11-02 evening | S | 7 | 45.6 min | 5.17 h | 97 % | none: every tile light, rows from the north |
| 2026-11-03 morning | M, L | 6 | 60.5 min | 4.36 h | 72 % | L E-360000_N-1200000 (2101 s) started at +25 min and ended at +60: one tile running from +41 (no weights yet: they came with v2 of the manifest) |
| 2026-11-03 noon | M2 | 7 | 46.8 min | 4.14 h | 76 % | the heaviest tile (2804 s) claimed first, by weight, and the run's length; 1-2 tiles running from +33 |

- Per run besides the tiles: the prefetch 20-50 s (the first run at 1 m 5.5 min from the mirror),
  the numba warm-up 1 s, the cube 6-18 s. Together 2.55 h for 13.66 h of tile seconds; at 7 workers
  busy throughout, 1.95 h.
- The critical path is the heaviest tile of each band (the Tatras): M2 E-350000_N-1190000 took 46
  min (2.1 billion pairs, 474 M lines, 17 686 s of CPU: 6.3 cores on average, since `_Rethreading`
  gave it 12-24 threads only once the others were done), L E-360000_N-1200000 35 min, M 14.5 min.
  `_threads` gave every tile 24 // 7 = 3 threads while all seven workers were busy, and the machine
  stood at 62-70 % of its 24 threads through those 33 minutes (7-9 idle), at 88 % in the tail.

| Band | Tiles | Tile seconds | Median s | prepare (step 1) | count (steps 2-3) | Tiles with 0 lines | Pixels of a tile / its core |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S 1 m, cores of 5 km | 2122 | 5.17 h | 8.6 | 51 % | 49 % | 1700 = 76 % of the seconds (3.9 h) | 1.54 |
| M 2 m, 10 km | 575 | 2.18 h | 9.4 | 56 % | 44 % (max 860 s) | 336 = 42 % | 1.59 |
| L 5 m, 20 km | 163 | 2.17 h | 25.9 | 43 % (22 s) | 57 % (max 2070 s) | 75 = 19 % | 2.34 |
| M2 2 m, 10 km | 575 | 4.14 h (11.85 h CPU) | 13.8 | 40 % | 60 % | 385 = 35 % | 2.13 |

- The stages of M2 (the one band counted with them): anchor pairs 44.7 % (4.8 cores), stitching
  terrain 16.1 % (1.5), other 8.6 %, prominence and drop 6.1 %, sea and lakes 3.9 %, anchors 3.4 %,
  gap filling 3.2 %, area coverage 2.8 %, water mask 2.2 %, border gaps 3 × 1.8 %, shore zone 1.7 %.
  Its 22 tiles of more than a million lines spend 93 % in the pairs (318 s each); the two Tatras
  tiles are 35 % of the band.
- A tile with no line (385 of M2's, 13.8 s each) is step 1: stitching 4.1 s, other 2.3, gap filling
  1.1, sea and lakes 1.0, anchors 0.9, coverage 0.7, prominence 0.6, water mask 0.6, border gaps 3 ×
  0.57 (inland too: a no-data patch touching the tile's edge is a "border gap", each neighbour whose
  rough box holds the tile is tried, finds nothing, and the gaps are labelled again for the next),
  shore zone 0.4. Such tiles have anchors (a median of 1126 in S, 2513 in M2), so they cannot be
  told apart before the pair search: they can only be made cheaper.
- Coarse grids read fine data: L stitches 5 m pixels from the 1 m tiles of the mirror (25 times the
  pixels needed), M at 2 m 4 times: step 1 took a median 22.2 s of L's 26 s per tile and 6.5 s of
  M's against S's 3.7 at the same pixels (corrected after stage 2: these are step 1's medians, not
  the stitching's, which was about half of L's step 1, 11 s for one tile alone, and 4.6 s of M2's
  8.9; B2 saved about 0.5 h of L, not the 1.0 h this line said).
- Memory: 2.2-2.3 GiB private per tile of 38-40 Mpx (about 60 B/px, the peak in step 1's gap
  filling), 2.9 GiB for M2's 53 Mpx; `worker_count` = min(12 physical cores, 26 GiB free / 3.7 GiB)
  = 7: the memory, not the cores, set the workers on this PC. Disk: 266 MB read and 107 MB written
  per tile, 200-236 MB/s of writes with 7 workers (an SSD; the Unraid array of docs/country-precompute.md
  would not keep up). The timeline's `workers_cores` and `workers_private_gib` were 0.0 through the
  run (the workers' process trees not found), so `country profile` knew no worker memory.
- F8c (bcefaf8, after these runs) makes the pair kernel 17-52 % faster: the heaviest tiles about
  30 % shorter on the next run, before any of the below.

### The plan: stages 1-3 (the user's choice, 2026-11-04)

| Stage | Item | Dimension | Effort | Expected |
| --- | --- | --- | --- | --- |
| 1 | A1 threads for the heavy tiles from the start (`_threads`: a heavy tile, `HEAVY_SHARE` of the run's largest weight, takes the cores left after `LIGHT_CORES` per light tile running; a light one at most `LIGHT_THREADS` while a heavy one runs) | wall | low | M2 47 → 33-35 min, M + L 60 → 45 |
| 1 | A2 all bands in one `country run` (no code: one manifest, the weights of every band, one tail) | wall | none | one tail instead of three |
| 1 | B1 the border gaps once per tile (again only after a neighbour wrote pixels), none for a tile inside the outline (`Plan.border`, `country._at_border`) | CPU | low | about 10 % of the tile seconds |
| 1 | C2 the timeline's worker samples | measurement | low | `country profile` with the workers' memory |
| 2 | C1 step 1 in strips per tile (`prepare_data(strips=True)` of round 3's wave 4 on the tile's own grid, the grids memory-mapped) | RAM | low-medium | about 60 → 25-30 B/px private, `COUNT_PIXEL_BYTES` 64 → about 32: twice the workers where the memory sets them (this PC 7 → 12) |
| 2 | B2 an averaged copy of the mirror at 2 m and 5 m (as `Download(average=)` of Bavaria's DOM20) | CPU | medium | L 22 → about 2 s per tile; about 2 h of 13.7 |
| 3 | A3 the weights of a first band from the relief of Copernicus 30 m (`perf_country.py relief`) | wall | low-medium | no tail in the first band of a new country |
| 3 | B4 measure "other" (2.3 s per tile between the bars) | CPU | low | to be seen |
| 3 | B3 step 1 once per group of tiles (round 3's wave 4 for the country layer: the overlaps repeat 1.5-2.3 times the pixels) | CPU, consistency | medium-high | 20-25 % of the tile seconds; one median per border gap |
| 3 | W1, added after stage 2: the worker count of this PC (M2 and L with C1 and B2 at 8, 10 and 12 workers; A1 gives the heaviest tile 2 threads beside 11 light tiles at 12 workers and 10 beside 7 at 8), then a cap if fewer are faster | wall | low | up to about 10 % of a band's wall with the memory free |

Not taken: skipping empty tiles by the relief at 30 m (it changes the counts: cliffs of 1 m are not
seen at 30 m), splitting the heaviest cores (A1 should do).

Stage 3's order (the user, 2026-11-04, after stage 2): W1 first, A3 beside it, then B4, and B3 last,
after the user's decision on counting every band again (B3 changes the counts: the gaps' offsets
and the lakes' levels of a group of tiles). After stages 1 and 2 step 1 is 27-39 % of a band's tile
seconds, so B3's gain is about 15-20 % of them, and only where the light tiles set the wall: a run
of the whole country, not one band, whose end is its heaviest tile.

### Step by step: Slovakia's M2 and L bands

Every step's numbers in one place; the details and the reasons are in the "Done" sections below, and
each step of stage 3 adds its column. Measured on this PC (12 cores / 24 threads, 61.6 GiB) under the
exclusive lock, on a scratch copy of `countries/slovakia` but for the base runs and the L band's
recount, which counted the user's folder; the counts compared tile by tile with the base
(`countcube.load_tile`). Memory: "private" is what a process has reserved (Windows' private bytes,
its commit charge, untouched pages included: OpenBLAS's 1.5 GiB per worker until 3ade88e, see
"Done, stage 2"), "working set" what it holds in RAM (the memory-mapped grids' pages included, which
Windows can drop and read again); "per tile" from the tiles' meta (`memory`), "all workers" from the
run's timeline (`logs/samples-*.csv`). An empty cell was not measured: the scratch tiles of stage 1
and of B2's runs were removed after their comparison, the base M2 run's timeline sampled no worker
and the base L run had no timeline.

| M2 band (2 m, cores of 10 km, 575 tiles) | Base (2026-11-03) | Stage 1 | Stage 1 + C1 | Stage 1 + B2 | C1 + B2, 8 workers | C1 + B2, 12 workers | + W1 (`LIGHT_CORES` 1), 12 workers | + B4, 12 workers | + B5, 12 workers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the base | | 575/575 | 575/575 | 575/575 | 575/575 | 575/575 | 575/575 | 575/575 | 575/575 |
| Wall of the tiles | 46.8 min | 35.0 min | 37.9 min | 31.8 min | 33.5 min | 34.4 min | 32.5 min | 31.9 min | 30.4 min |
| Workers × budget of each (`worker_count`) | 7 × 3.7 GiB | 8 × 3.7 GiB | 11 × 2.5 GiB | 8 × 3.7 GiB | 8 × 2.1 GiB | 12 × 2.1 GiB | 12 × 2.1 GiB | 12 × 2.1 GiB | 12 × 2.1 GiB |
| Tile seconds | 4.14 h | 3.38 h | 4.12 h | 2.76 h | 3.02 h | 3.50 h | 3.73 h | 3.40 h | 3.12 h |
| CPU seconds of the tiles | 11.85 h | 11.25 h | 11.51 h | 10.01 h | 10.15 h | 10.44 h | 10.43 h | 10.24 h | 10.13 h |
| Step 1 / "stitching terrain" | 1.64 / 0.67 h | | 1.92 / 0.74 h | 1.07 / 0.21 h | 1.24 / 0.21 h | 1.41 / 0.24 h | 1.67 / 0.24 h | 1.33 / 0.23 h | 1.22 / 0.22 h |
| Median tile / an empty tile | 13.8 / 13.6 s | 11.9 / 11.5 s | 13.8 / 14.8 s | 8.9 / 8.3 s | 9.3 / 9.9 s | 10.5 / 11.4 s | 12.3 / 13.5 s | 10.5 / 11.3 s | 9.5 / 9.7 s |
| The heaviest tile, E-350000_N-1190000 | 2804 s | 2097 s | 2271 s | 1908 s | 2009 s | 2063 s | 1951 s | 1913 s | 1826 s |
| The light part done at | +33 min | +24 min | +20 min | +18 min | +21 min | +15 min | +17 min | +15 min | +13 min |
| Machine CPU, mean | 75 % | 92 % | 90 % | 92 % | 93 % | 92 % | 95 % | 95 % | 94 % |
| Free RAM: at the start / the least | 26.0 / 19.5 GiB | 32.6 / 24.7 GiB | 27.2 / 13.2 GiB | 30.6 / 23.3 GiB | 29.5 / 21.4 GiB | 31.7 / 17.5 GiB | 33.2 / 21.2 GiB | 33.5 / 18.7 GiB | 30.2 / 16.7 GiB |
| Private per tile: median / max | 2.24 / 3.75 GiB | | 1.89 / 2.46 GiB | | 0.45 / 1.03 GiB | 0.45 / 0.97 GiB | 0.45 / 1.02 GiB | 0.45 / 0.99 GiB | 0.45 / 1.15 GiB |
| Working set per tile: median / max | 1.21 / 2.80 GiB | | 0.89 / 1.36 GiB | | 0.88 / 1.36 GiB | 0.88 / 1.31 GiB | 0.91 / 1.36 GiB | 1.22 / 2.28 GiB | 1.21 / 2.41 GiB |
| All workers, private: peak / mean | | 19.5 / 11.6 GiB | 28.3 / 12.1 GiB | 20.0 / 10.5 GiB | 6.9 / 2.5 GiB | 13.5 / 2.7 GiB | 10.9 / 3.0 GiB | 12.2 / 2.8 GiB | 10.4 / 2.7 GiB |
| All workers, working set: peak / mean | | 8.7 / 4.5 GiB | 14.6 / 4.7 GiB | 9.7 / 4.1 GiB | 8.7 / 4.2 GiB | 15.4 / 4.5 GiB | 13.0 / 5.0 GiB | 20.6 / 7.8 GiB | 21.6 / 7.5 GiB |
| Written to the disks | 346 GB | 254 GB | 290 GB | 258 GB | 290 GB | 288 GB | 290 GB | 6 GB | 6 GB |

Stage 1 + C1 ran 105fff2, with OpenBLAS's reservations still in. C1 and B2 together, main of
2026-11-04 (`LIGHT_CORES` 2), measured by stage 3's W1: against B2 alone at the same 8 workers C1's
strips cost step 1 0.17 h (an empty tile 8.3 → 9.9 s, the band 31.8 → 33.5 min) on this PC with its
memory free; at 12 workers again 34.3 min, with W1's rule again 32.7.

| L band (5 m, cores of 20 km, 163 tiles) | Base (2026-11-03, the M + L run) | Stage 1 + B2 | C1 + B2 (the recount) | + W1 (`LIGHT_CORES` 1), 12 workers | + B4, 12 workers | + B5, 12 workers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the base | | 162/163 | 162/163 | 162/163 | 162/163 | 162/163 |
| Wall of the L tiles | 38.2 min (M's tiles beside) | 18.6 min | 18.3 min | 17.8 min | 16.6 min | 17.6 min |
| Workers × budget of each (`worker_count`) | 6 × 4.7 GiB | 12 × 2.7 GiB | 12 × 1.6 GiB | 12 × 1.6 GiB | 12 × 1.6 GiB | 12 × 1.6 GiB |
| Tile seconds | 2.17 h | 1.51 h | 1.52 h | 1.74 h | 1.56 h | 1.61 h |
| CPU seconds of the tiles | | 5.41 h | 5.44 h | 5.40 h | 5.40 h | 5.34 h |
| Step 1 / "stitching terrain" | 0.94 h / not recorded | 0.38 / 0.08 h | 0.40 / 0.08 h | 0.50 / 0.09 h | 0.38 / 0.10 h | 0.38 / 0.11 h |
| Median tile / an empty tile | 25.9 / 20.1 s | 11.0 / 9.7 s | 12.5 / 10.9 s | 14.9 / 12.8 s | 12.1 / 10.2 s | 12.1 / 9.8 s |
| The heaviest tile, E-360000_N-1200000 | 2101 s | 1116 s | 1094 s | 1069 s | 996 s | 1055 s |
| The light part done at | +19 min | +6 min | +6 min | +8 min | +7 min | +7 min |
| Machine CPU, mean | | 86 % | 86 % | 88 % | 87 % | 88 % |
| Free RAM: at the start / the least | | 34.1 / 25.6 GiB | 33.0 / 23.2 GiB | 33.3 / 23.7 GiB | 34.2 / 24.9 GiB | 30.9 / 21.1 GiB |
| Private per tile: median / max | | | 0.40 / 0.91 GiB | 0.40 / 0.87 GiB | 0.40 / 0.87 GiB | 0.40 / 0.91 GiB |
| Working set per tile: median / max | | | 0.78 / 1.16 GiB | 0.76 / 1.12 GiB | 1.08 / 1.77 GiB | 1.14 / 1.81 GiB |
| A worker's working set, its peak over the run | 2.35 GiB | | 1.68 GiB |  |  |  |
| All workers, private: peak / mean | | 25.7 / 9.0 GiB | 8.5 / 2.0 GiB | 8.8 / 2.2 GiB | 6.6 / 2.1 GiB | 6.6 / 2.0 GiB |
| All workers, working set: peak / mean | | 10.0 / 3.1 GiB | 10.5 / 3.2 GiB | 10.9 / 3.4 GiB | 14.8 / 5.8 GiB | 14.7 / 5.6 GiB |
| Written to the disks | | 60 GB | 66 GB | 65 GB | 1 GB | 2 GB |

The L tile that differs, E-360000_N-1200000, has 6 of its 402 225 769 lines in other keys of the
cube, its lines, spots and spot records equal (B2's 5 m mosaic lies one float32 ULP from GDAL's in
7 ppm of the pixels); the recount on the code of C1 and B2 moved exactly those 6 lines, so C1's
strips moved no count of L. The recount's 12 workers held 8.5 GiB of private bytes at most against
25.7 with B2 alone: most of that is OpenBLAS's reservations, while the workers' working set, the RAM
they held, stayed at about 10 GiB. The L band's wall moved by a minute between runs of equal code (B4's
16.6 min and 17.4 the same afternoon: wave 3 of stage 3).

S, the band of light tiles, which the plan left out: its wall is their seconds over the workers, so
what ends M2 and L does not end it. The base is the user's run of 2026-11-03.

| S band (1 m, cores of 5 km, 2122 tiles) | Base (2026-11-03) | + W1 (`LIGHT_CORES` 1), 8 workers | + W1, 12 workers | + B4, 12 workers | + B5, 12 workers |
| --- | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the base | | 2122/2122 | 2122/2122 | 2122/2122 | 2122/2122 |
| Wall of the tiles | 45.6 min | 32.6 min | 29.3 min | 24.5 min | 18.6 min |
| Workers × budget of each (`worker_count`) | 7 workers | 8 × 1.6 GiB | 12 × 1.6 GiB | 12 × 1.6 GiB | 12 × 1.6 GiB |
| Tile seconds | 5.17 h | 4.17 h | 5.63 h | 4.86 h | 3.66 h |
| CPU seconds of the tiles | | 5.27 h | 6.49 h | 6.13 h | 4.86 h |
| Step 1 / "stitching terrain" | 2.66 h / not recorded | 2.37 / 0.39 h | 3.02 / 0.48 h | 2.18 / 0.35 h | 2.31 / 0.41 h |
| Prominence and drop | | | 2.32 h | 2.37 h | 0.99 h |
| "other" | | | 0.56 h | 0.29 h | 0.37 h |
| Area coverage | | | 0.38 h | 0.38 h | 0.09 h |
| Median tile / an empty tile | 8.6 / 8.3 s | 6.7 / 6.7 s | 9.1 / 9.0 s | 7.8 / 7.7 s | 3.6 / 4.8 s |
| The light part done at | +45 min | +32 min | +29 min | +24 min | +18 min |
| Machine CPU, mean | | 62 % | 80 % | 83 % | 84 % |
| Free RAM: at the start / the least | | 34.0 / 23.3 GiB | 33.7 / 16.2 GiB | 33.2 / 16.2 GiB | 29.2 / 12.4 GiB |
| Private per tile: median / max | | 0.46 / 1.02 GiB | 0.46 / 0.98 GiB | 0.46 / 1.07 GiB | 0.28 / 1.23 GiB |
| Working set per tile: median / max | | 0.76 / 1.26 GiB | 0.76 / 1.23 GiB | 1.08 / 1.86 GiB | 0.79 / 2.09 GiB |
| All workers, private: peak / mean | | 11.7 / 4.4 GiB | 17.9 / 6.9 GiB | 17.1 / 7.7 GiB | 17.4 / 6.4 GiB |
| All workers, working set: peak / mean | | 11.2 / 5.7 GiB | 18.5 / 8.8 GiB | 22.1 / 12.5 GiB | 22.1 / 11.0 GiB |
| Written to the disks | | 679 GB | 685 GB | 4 GB | 5 GB |

"Written to the disks" is the machine's counters over the run (the timeline, `logs/samples-*.csv`):
in every step but B4 mostly the tiles' grids, deleted seconds later. What the runs read follows the
system's cache: 50 GB in S, 19-25 GB in M2, 0.4-5 GB in L, with W1 and with B4. With B4 the working
set counts pages twice (stage 3's part below): the workers' went 8.8 → 12.5 GiB on average in S, the
machine's memory in use 35.4 → 36.6 GiB, at the same peak of 45.4 GiB.

A first run of a new country, M + L together on the code of main 6cf9dd7 (C1, B2, `LIGHT_CORES` 1):
a scratch copy with every band pending and no weights, 12 workers, the exclusive lock, one run after
another. The order of the claims is all that differs: the rowid order of before, and the relief's
weights (A3) from slopes of 45° (main) and of 30°. Stage 3's part below says why.

| M + L, a first run (738 tiles) | Rowid order | Relief 45° (main) | Relief 30° |
| --- | ---: | ---: | ---: |
| Counts identical to the user's, M | 575/575 | 575/575 | 575/575 |
| Counts identical to the user's, L | 163/163 | 163/163 | 163/163 |
| Wall of the tiles | 31.9 min | 29.2 min | 29.2 min |
| The run from its start, relief and prefetch included | 32.7 min | 30.3 min | 30.3 min |
| Workers × budget of each (`worker_count`) | 12 × 1.7 GiB | 12 × 1.7 GiB | 12 × 1.7 GiB |
| Tile seconds | 3.86 h | 4.40 h | 4.34 h |
| CPU seconds of the tiles | 8.87 h | 8.71 h | 8.65 h |
| Step 1 / "stitching terrain" | 1.46 / 0.28 h | 1.70 / 0.33 h | 1.72 / 0.34 h |
| Median tile / an empty tile | 8.9 / 8.8 s | 10.3 / 10.5 s | 10.3 / 10.7 s |
| The heaviest tile, L's E-360000_N-1200000 | +10.9 → +31.9 min, 1259 s | +0.0 → +29.2 min, 1751 s | +0.0 → +29.2 min, 1753 s |
| M's heaviest tile, E-350000_N-1190000 | +1.7 → +21.7 min, 1197 s | +0.0 → +19.6 min, 1177 s | +1.0 → +20.3 min, 1156 s |
| The light part done at | +17.6 min | +21.7 min | +21.5 min |
| One tile alone at the end | 9.7 min | 7.4 min | 7.7 min |
| Tiles heavy by their weight | 0 | 8 | 60 |
| Machine CPU, mean | 90 % | 94 % | 94 % |
| Free RAM: at the start / the least | 32.0 / 22.9 GiB | 33.3 / 24.6 GiB | 33.7 / 21.7 GiB |
| Private per tile: median / max | 0.40 / 0.92 GiB | 0.41 / 0.90 GiB | 0.41 / 0.89 GiB |
| Working set per tile: median / max | 0.73 / 1.19 GiB | 0.74 / 1.17 GiB | 0.74 / 1.15 GiB |
| All workers, private: peak / mean | 9.7 / 2.9 GiB | 8.0 / 3.6 GiB | 11.8 / 3.6 GiB |
| All workers, working set: peak / mean | 11.6 / 4.6 GiB | 10.3 / 5.7 GiB | 13.1 / 5.6 GiB |

### Done, stage 1 (2026-11-04, branch `country-perf-1`: the counts byte for byte)

- **A1, the threads of the heavy tiles** (`country._threads`, `_heavy_weight`): a tile whose weight
  reaches `HEAVY_SHARE` (5 %) of the run's largest takes its share of the logical cores left after
  `LIGHT_CORES` (2) per light tile running; a light tile keeps at most `LIGHT_THREADS` (3) while a
  heavy one runs; without weights (the first band of a country) the rule of before, `cores // busy`.
  The heaviness goes with the claim and into `_Rethreading`'s looks.
- **B1, the border gaps once** (`sources.filling.fill_from_neighbours`): labelled again only after
  a neighbour wrote pixels into either grid (`fill_gaps` returns `(path, terrain pixels filled,
  pixels written)`) or failed midway, not after every attempt; and none for a tile whose grid lies
  inside the country's outline (`country._at_border` → `Plan.border` False: no neighbour has data
  there). The app's searches keep every value: a neighbour that filled nothing left the grids as
  they were, and `Plan.border` stays True outside the country layer.
- **A2**: nothing to code; `country run <id>` without `--bands` counts every band in one manifest,
  so the weights of every band order one queue and the run has one tail.
- **C2**: not reproduced. The M2 run of 2026-11-04 sampled the workers' cores (up to 22.7) and
  private bytes (up to 19.5 GiB) in 399 of its 402 rows with the code as it was; the zeros of
  2026-11-03 stay unexplained (the same sampler, `_RunSamples`, finds the interpreter under the
  venv's launcher in `tests/test_country.py` too).

Measured: Slovakia's M2 band counted again on a copy of `countries/slovakia` (its M2 tiles pending,
the weights from the other bands' tiles), the real cache and mirror, this PC, under the exclusive
lock; the base is the run of 2026-11-03 (7 workers; this run got 8, since other programs held less
memory: `worker_count`), and the new run has F8c (bcefaf8) as well. All 575 tiles' counts are
identical to the base's.

| | Base (2026-11-03) | Stage 1 (2026-11-04) |
| --- | ---: | ---: |
| Wall of the run | 46.8 min | 35.0 min (−25 %) |
| Workers | 7 | 8 |
| Tile seconds | 4.14 h | 3.38 h (−18 %) |
| CPU seconds of the tiles | 11.85 h | 11.25 h |
| Machine CPU, mean | 75 % | 92 % |
| Workers busy | 76 % | 73 % (fewer than 8 running from +24 min of 35) |
| The heaviest tile, E-350000_N-1190000 (474 M lines) | 2804 s at 3 threads (12-24 in the tail) | 2097 s at 24 threads from the claim (F8c as well) |
| E-340000_N-1190000 (318 M lines) | 2418 s | 1736 s |
| Anchor pairs, all tiles | 1.86 h | 1.41 h |
| "other" | 0.36 h | 0.20 h |
| Border gaps, the second and third neighbour | 0.08 + 0.08 h | 0.00 + 0.00 h (the first 0.07 → 0.07: the border tiles) |
| An empty tile | 13.6 s | 11.5 s |
| Median tile | 13.8 s | 11.9 s |

The run is its heaviest tile again: 2097 s = 35 min, while the other 574 tiles were done at +24
min (8 workers) — A1 moved that tile from 47 to 35 min together with F8c, and the rest of the band
no longer waits for it from +33 but from +24. What is left of the tail is the pair search of one
tile on the whole machine (its 2.1 billion pairs): splitting such a core (A4) or the count mode's
parts over two processes would be the next step for it, not taken in this round. The CPU of the
machine is at 92 % now, so stage 2's extra workers (C1) pay only where the memory, not the cores,
set `worker_count` (this PC with other programs open).

**Where the gain comes from** (the user's question: not the eighth worker?). The light part of the
band (3.38 h less the two heaviest tiles' 1.06 h = 2.32 h) took 23 min on 6 light workers and would
take about 28 on 5: under the heaviest tile's 35 min either way, so the eighth worker moved the end
of the light part, not the run's end; and the tile seconds are work per tile, which more workers
make slower, not faster (the machine at 92 %). To split the heavy tiles' gain between F8c and A1,
the tile E-360000_N-1190000 (61 M lines, 667 s in the base run at 3 threads beside 6 workers) was
counted alone with the stage 1 code (`local/country-perf-2026-11-04/stage1/one_tile.log`):

| Threads, alone | Wall | Anchor pairs | CPU seconds | Cores used |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 356 s | 340 s | 1033 | 2.9 |
| 12 | 149 s | 134 s | 1585 | 10.6 |
| 24 | 129 s | 115 s | 2433 | 18.9 (12 physical) |

Alone, the pair search of a heavy tile scales 2.4 times from 3 to 12 threads and 2.8 to 24; the
same tile at 3 threads went 667 → 356 s between the base and stage 1 (F8c and no neighbours
competing), and in the stage 1 run it took 496 s at 12 threads beside 7 workers. So inside a run
on a full machine the threads of A1 bought the heaviest tiles little (2804 → 2097 s is mostly
F8c): 8 workers on 12 physical cores leave a heavy tile no idle cores to take; A1 pays where
cores are idle: the last third of a run, a machine with more cores than workers (the memory sets
`worker_count`), a run of one heavy band. The run's floor is max(the heaviest tile beside the
others, the light part on the light workers): 35 and 24 min here; the heavy tile alone would take
about a quarter of that, so a schedule that runs the heaviest tiles before or after the light ones
is no better (10-20 min of heavy tiles plus 23 of light ones). Lower means a shorter light part
(stage 2's B2, stage 3's B3) and then a split of the heaviest cores (A4).

### Done, stage 2 (2026-11-04, branches `country-perf-2-strips` and `country-perf-2-coarse`)

- **C1, step 1 of a tile in strips** (`country.TileWork.count`: `search.prepare_data(strips=True)`
  on the tile's own grid, round 3's wave 4): the grids memory-mapped in the tile's work folder, one
  int32 array of labels and a strip's temporaries in memory at a time. No copy of the tile's window
  (`search._tile_data`): the window is the grid, and both paths hand steps 2-3 read-only memmaps,
  the kernels' argument types of `warmup.SEARCHES`. `coast.sea_mask_rows(extent=)` reads the world
  file's polygons once per band for a coastal country. The strips' cross-CRS warps (the FABDEM gap
  filler, the Copernicus water mask) differ from a whole-grid warp within GDAL's approximate
  transformer (wave 4's caveat: up to 0.66 m, a median of 6 mm, in the filled pixels of a border
  tile), which the user accepted for the country layer: a tile counted again may differ by a few
  lines where FABDEM fills a gap inside the outline. Slovakia's M2 band counted again: all 575
  tiles identical.
- **OpenBLAS's reservations** (found while measuring C1): numpy and SciPy each load their own
  OpenBLAS, the library of their vector and matrix routines (`libscipy_openblas64_` with `import
  numpy`, `libscipy_openblas` with the first SciPy module), and each starts a thread per logical core
  and commits a buffer of about 32 MB for each: 758 MiB of private bytes after `import numpy` and
  1520 MiB after SciPy on this PC's 24 logical cores, 19 and 42 MiB with `OPENBLAS_NUM_THREADS=1`,
  the working set 30-60 MiB in every case (measured in a bare process, 2026-11-04). A count calls no
  BLAS routine on anything large (3-vectors and 3 × 3 systems), so the buffers are never touched:
  reserved memory, counted against Windows' commit limit (the RAM and the page file), never in RAM.
  They made every worker's private bytes about 1.5 GiB larger in the runs before 3ade88e: the
  analysis' 60 B/px, the whole private bytes over the tile's pixels, was mostly them (corrected:
  without them the median M2 tile held about 15 B/px before the strips, the largest 45), and the
  timelines' `workers_private_gib` overstate by them. `country._worker_env` gives the workers `OPENBLAS_NUM_THREADS=1` and
  `MKL_NUM_THREADS=1`: it frees reservations, not RAM. On Linux such untouched pages count neither
  in a process's RSS nor in a container's memory limit.
- **`COUNT_PIXEL_BYTES` 64 → 32**: in strips and without those buffers a worker stands at 0.17 GiB
  of private bytes before a tile and rose at most 0.87 GiB during one (the Tatras tile of 474 M
  lines at 24 threads: 16 B/px, in the pair search); 32 is twice that. A 53 Mpx tile needs 2.1 GiB
  per worker instead of 3.7. In the L band's recount a worker's working set peaked at 1.68 GiB
  against its budget of 1.6: the memory-mapped grids' pages, which Windows can drop, while its
  private bytes stayed under 0.91 GiB. The free-disk check takes `_disk_bytes(plan)`
  (`search.work_bytes` + `AREA_TEMP_BYTES` of the band's plan) instead of `DISK_PIXEL_BYTES`.
- **B2, the Slovak tiles averaged to 2 m and 5 m** (`tools/sk_tiles.py average`,
  `GridTiles(averaged=(2, 5))`): a grid of exactly 2 or 5 m reads the mirror's `dmr5/2m` and
  `dmr5/5m` (and `dmp1/...`), each pixel the mean of the valid 1 m pixels of its block (the rule of
  `Download(average=)`); any other grid, and a mirror without those folders, reads the 1 m tiles as
  before. At 2 m the mosaic is byte for byte the one GDAL averaged from the 1 m tiles; at 5 m 274 of
  an L tile's 37.5 M pixels lie one float32 ULP from it (GDAL's weights are not exactly 1.0; the
  averaged tile holds the correctly rounded mean). The averaged folders take 23.6 + 4.4 GB beside the
  DMR's 64.6 GB of 1 m tiles and 26.7 + 4.9 GB beside the DMP's 77.9 (6.3 and 6.5 min on all cores):
  1.6-1.8 times the estimate, since they are deflated float32 and the 1 m tiles LERC with 5 mm of
  error. The cache keeps a copy of what a run reads, as of the 1 m tiles (dmr5's 23.4 + 4.3 GB after
  the two runs).
- The user's decisions: the L band of `countries/slovakia` counted again with the averaged tiles
  (below), and R13 re-baselined (2 804 → 2 801 anchors, 2 407 → 2 405 open, its lines unchanged:
  docs/regression-tests.md).

Measured on this PC while nothing else used its cores (other programs still held 28-36 GiB of its
61.6), under the exclusive lock, the bands on a scratch copy of `countries/slovakia`, each branch on
its own (C1's runs without B2, B2's without C1; `local/country-perf-2026-11-04/stage2/`; the memory
of every run in "Step by step" above):

| M2 band | Base (2026-11-03) | Stage 1 | Stage 1 + C1 | Stage 1 + B2 |
| --- | ---: | ---: | ---: | ---: |
| Counts against the base | | 575/575 identical | 575/575 identical | 575/575 identical |
| Wall of the tiles | 46.8 min | 35.0 min | 37.9 min | 31.8 min |
| Workers (`worker_count`) | 7 | 8 | 11 | 8 |
| Tile seconds | 4.14 h | 3.38 h | 4.12 h | 2.76 h |
| CPU seconds of the tiles | 11.85 h | 11.25 h | 11.51 h | 10.01 h |
| Step 1 (`prepare`) | 1.64 h | | 1.92 h | 1.07 h |
| "stitching terrain" | 0.67 h (median 4.6 s) | | 0.74 h | 0.21 h (median 1.2 s) |
| Median tile / an empty tile | 13.8 / 13.6 s | 11.9 / 11.5 s | 13.8 / 14.8 s | 8.9 / 8.3 s |
| The heaviest tile, E-350000_N-1190000 | 2804 s | 2097 s | 2271 s | 1908 s |
| Machine CPU, mean | 75 % | 92 % | 90 % | 92 % |
| The light part done at | +33 min | +24 min | +20 min | +18 min |
| A worker's private peak per tile, median / max | 2.24 / 3.75 GiB | | 1.89 / 2.46 GiB (OpenBLAS's buffers still in) | |

With OpenBLAS on one thread too, the tile E-360000_N-1190000 (61 M lines) peaked at 714 MiB of
private bytes (2.81 GiB in the user's run), 173 MiB of them before its step 1.

| L band | Base (2026-11-03, the M + L run) | Stage 1 + B2 |
| --- | ---: | ---: |
| Counts against the base | | 162/163 identical (E-360000_N-1200000: 6 of its 402 225 769 lines in other keys, its lines, spots and spot records equal) |
| Wall of the L tiles | 38.2 min (M's tiles beside, 6 workers) | 18.6 min (12 workers) |
| Tile seconds | 2.17 h | 1.51 h |
| Step 1, median per tile / total | 22.2 s / 0.94 h | 8.3 s / 0.38 h |
| "stitching terrain" | not recorded (one tile alone: 11 s) | 0.08 h (median 1.9 s; one tile alone: 3 s) |
| Median tile / an empty tile | 25.9 / 20.1 s | 11.0 / 9.7 s |
| The heaviest tile, E-360000_N-1200000 | 2101 s at 4 threads | 1116 s at 24 threads (A1 and F8c too) |
| Tile files read, E-460000_N-1240000 | 1435 MB | 91 MB |

One tile alone (exclusive, 3 threads), before and after B2: L E-460000_N-1240000 24 → 12 s
(stitching 11 → 3 s), M2 E-300000_N-1230000 20 → 12 s (4 → under 2 s), the counts equal. The strips
of C1 cost step 1 0.7-1.0 s more on a tile whose gaps FABDEM fills (its gap filling and stitching
in strips) and nothing on a tile without gaps (two interleaved rounds per tile, exclusive).

What it shows:
- B2 did what it should: M2's tile seconds 3.38 → 2.76 h and its wall 35.0 → 31.8 min with the same
  8 workers, L's step 1 0.94 → 0.38 h (with stage 1's border gaps: the base L run had neither), an
  empty tile 11.5 → 8.3 s in M2 and 20.1 → 9.7 s in L.
- C1 did what it should for the memory: a tile's working set peak, the RAM it holds, 1.21 / 2.80 →
  0.89 / 1.36 GiB (median / max, M2); its private bytes 2.2-3.1 → 0.7-0.9 GiB with the OpenBLAS fix,
  most of that drop the reservations. But on this PC, with 27-34 GiB free, the cores, not the
  memory, bound the run: `worker_count` gave 11 workers on 12 physical cores, which slowed every
  tile (3.38 → 4.12 h, the strips' extra second on border tiles included) and the run (37.9 min
  against 35.0 with 8). It pays on a machine whose memory sets fewer workers than cores: this PC
  with its programs open (26 GiB free give 12 workers instead of 7). With 32 B/px, `worker_count`
  gives 12 workers here whenever 25 GiB are free; how many workers these 12 cores carry best is for
  stage 3 to measure (a cap below the physical cores would follow from it, not a guess).
- The floor of a band is still its heaviest tile (M2 1908 s, L 1116 s); with B2 the light part ends
  earlier (+18 min), so the heavy tile gets the idle cores sooner.

**The L band counted again** in the user's `countries/slovakia` with C1 and B2 together (the user's
decision; the old tiles, cube and manifest kept in `local/country-perf-2026-11-04/stage2/L-before-recount/`):
162 of 163 tiles identical to before and the same 6 lines of E-360000_N-1200000 in other keys as in
B2's run alone, so C1's strips moved no count; 18.3 min with 12 workers (`worker_count` at 32 B/px:
1.6 GiB each), 1.52 h of tile seconds, step 1 0.40 h (a median of 8.9 s; FABDEM's gap filling in
strips 0.05 → 0.09 h against B2 alone), the heaviest tile 1094 s; the cube built again with the
totals of before (1 183 773 337 lines, 3 679 609 spots).

Open: the worker count of this PC (above: stage 3's W1); the app's phase and quick-lane processes
reserve the same OpenBLAS buffers, which costs them no RAM (and on the VPS, Linux, no limit either);
the tiles' `io` counters, the process's file reads and writes, do not see memory-mapped files: with
step 1 in strips a tile writes 0 MB by them (the L band's recount: a median of 168 MB read, 0
written), and with B2 the reads barely moved in M2 (a median of 266 → 256 MB per tile) while the
tile files read fell to a third, so a tile's disk is to be measured another way (stage 3's B4); the
Hugging Face upload of the Slovak tiles carries the averaged folders (about 42 % more bytes).

### Done, stage 3 (2026-11-05, wave 1: branches `country-perf-3-relief` and `country-perf-3-workers`)

- **A3, the weights of a first band from the relief** (`country._set_weights`, `_relief_weights`; the
  module `relief.py`, moved from `tools/perf_country.py`, which calls it now): when a pending tile of
  a run's bands lies under no done tile (a new country's first run, or a first run stopped and run
  again), every pending tile of the run weighs `RELIEF_LINES` (7e6) × (the km² of slopes of
  `RELIEF_DEGREES` (45°) or more at 30 m in its core) ^ `RELIEF_EXPONENT` (1.65), from Copernicus
  GLO-30 (the catalogue's `europe` layer) in blocks of about 1 km whose centre lies inside the
  outline and the core; otherwise the line weights of before, a tile under done tiles of 0 lines
  keeping its real 0. Set after the run's question and before the prefetch, since the relief may
  download GLO-30 tiles: 9-13 s for Slovakia (15 cached tiles, 653 MB). A failure leaves the order
  of before, with a warning; no schema change (manifest v2's `weight`).

Choosing the proxy on the user's done tiles; each cell: Spearman of the proxy against the tiles'
lines, the 5 tiles of most lines among the proxy's first 5, the 10 among its first 10:

| Band (tiles) | Line weights of before | km² of 45° slopes (chosen) | relief × that km² | pairs at 40° | relief, max |
| --- | ---: | ---: | ---: | ---: | ---: |
| S (2122) | 0.511 | 0.546, 4/5, 6/10 | 0.545, 4/5, 6/10 | 0.539, 4/5, 6/10 | 0.487, 2/5, 5/10 |
| M (575) | 0.760 | 0.749, 4/5, 8/10 | 0.747, 4/5, 8/10 | 0.764, 4/5, 9/10 | 0.709, 4/5, 5/10 |
| L (163) | 0.899 | 0.896, 5/5, 8/10 | 0.897, 5/5, 9/10 | 0.889, 4/5, 9/10 | 0.875, 4/5, 7/10 |
| M2 (575) | 0.731 | 0.741, 4/5, 7/10 | 0.744, 4/5, 7/10 | 0.740, 4/5, 7/10 | 0.718, 4/5, 5/10 |

The relief ranks a band's tiles as well as the lines of the other three bands did, and better at
the top (M2's second heaviest tile, 318 M lines, is 5th by the line weights and 2nd by the relief);
60°, the anchors' angle of S, M and M2, hardly occurs at 30 m. The exponent is a fit of log lines on
log km² over M's, L's and M2's tiles with lines (1.64), the factor the median at that exponent over
their tiles of a million lines or more; the km² alone decides the claims' order and the exponent
alone which tiles are heavy (`HEAVY_SHARE` of the largest weight: a km² of at least 0.16 of the
largest). Heavy, each band as its own run: S 9 (8 of the 41 heavy by their own lines; by the line
weights 32, 8 of the 41), M 4 (4 of 5; 8, 3 of 5), L 4 (3 of 3; 2, 2 of 3), M2 4 (3 of 3; 9, 3 of 3).

Measured: the L band of a scratch copy with every band pending and no weights (a new country), 12
workers, the exclusive lock:

| L band, a first run | Rowid order (main b39841b) | Relief weights (A3) |
| --- | ---: | ---: |
| Counts identical to the user's | 163/163 | 163/163 |
| Weights at the start | none | 112 of 163 tiles above 0, in 13 s |
| Wall of the tiles | 19.6 min | 18.8 min |
| The heaviest tile, E-360000_N-1200000 | claimed 37th: +0.9 → +19.6 min, 1121 s | claimed first: +0.0 → +18.8 min, 1127 s |
| E-340000_N-1200000 | 38th: +1.1 → +10.1 min | first: +0.0 → +9.9 min |
| Tile seconds / CPU seconds | 1.56 / 5.42 h | 1.61 / 5.45 h |
| The light part done at | +6 min | +7 min |
| Free RAM: at the start / the least | 31.9 / 23.3 GiB | 31.2 / 21.4 GiB |
| All workers, private / working set: peak | 7.4 / 9.7 GiB | 9.4 / 11.2 GiB |

On L alone the rowid order reaches the heaviest tile early (37th of 163), so the gain is 0.8 min.
On M + L, where the rowid order claims every M tile first, it is 2.7 min: 31.9 → 29.2 min, L's
heaviest tile starting at once instead of at +10.9 min (the table in "Step by step").

That is the relief's whole gain, and a replay had promised far more. Replaying each claim order with
the user's tile seconds gave M + L at 12 workers 29.5 → 18.6 min and all four bands 92.7 → 65.1 min.
A replay keeps each tile's seconds, and they are not fixed: L's heaviest tile took 1094 s in L's own
run, 1259 s in the rowid M + L run, its last 9.7 min alone, and 1751 s with the relief, beside 10-11
other tiles for its first 22 min. The tiles' CPU stays 8.7-8.9 h in any order, so a better order only
fills the machine sooner (90 → 94 %, the median tile 8.9 → 10.3 s) and shortens the tail of one tile
(9.7 → 7.4 min). A first run of all four bands was not measured; the replay is no estimate of it.

45° or 30° (the user's request, 2026-11-05: on the done tiles, then by those M + L runs, with the
constants fitted again for 30°: `RELIEF_LINES` 1.2e4, `RELIEF_EXPONENT` 1.85). **45° stays.** The two
angles tie on the wall, and 30° is worse on everything else:

| | km² of 45° slopes | km² of 30° slopes |
| --- | ---: | ---: |
| Wall of the tiles, M + L | 29.2 min | 29.2 min |
| Spearman against the lines: S, M, L, M2 | 0.546, 0.749, 0.896, 0.741 | 0.503, 0.723, 0.869, 0.715 |
| The 5 tiles of most lines among the first 5: S, M, L, M2 | 4, 4, 5, 4 | 2, 2, 1, 2 |
| The 10 tiles of most lines among the first 10: S, M, L, M2 | 6, 8, 8, 7 | 3, 6, 6, 5 |
| The 20 tiles of most lines among M + L's first 12 claims | 12 | 6 |
| The exponent: pooled (M, L, M2 each) | 1.64 (1.47, 1.84, 1.78) | 1.83 (1.48, 2.58, 2.13) |
| The factor: pooled (M, L, M2 each) | 6.8e6 (6.7e6, 7.6e6, 6.5e6) | 1.2e4 (1.9e4, 5.9e3, 1.5e4) |
| The largest tile as predicted, M lines: L (402 counted), M (202) | 452, 298 | 34, 10 |
| Heavy tiles of M + L | 8 | 60 |
| Heavy tiles of all four bands in one run (9 by their own lines, all among them) | 16 | 86 |

Slopes of 30° at 30 m lie over every mountain range, so most of the hills reach a fifth of the
largest km², where the heavy line falls at exponent 1.85; the Tatras' walls stand out only at 45°.
The tie is L's heaviest tile: it ends the run at both angles, and both claim it in the first second,
30° as the 6th by chance, since the L tiles' four times the area put them first on M + L. In a run
of all four bands the replay's order puts M2's two heaviest tiles 19th and 80th at 30°, 3rd and 6th
at 45°.

Open: one factor for every band over-predicts S (in a run of all bands four S tiles of the Tatras are
heavy for their 25 s each: harmless); the fit is Slovakia's (the claims follow the km² anywhere, the
heavy set depends on the exponent); `_heavy_weight` takes the largest weight of the run's bands over
their done tiles too, so after a first run stopped midway a later run's line weights are compared
with the done tiles' relief weights (both about lines, within a factor of 2 at the top).

- **W1, the light tiles' cores** (`LIGHT_CORES` 2 → 1 in `_threads`; `worker_count` unchanged: no
  cap below the physical cores). 19 band runs on scratch copies (2026-11-04 20:17 to 11-05 06:37,
  the exclusive lock, repeats within 0.2 min), every tile's counts identical to the user's: M2
  575/575 in 9 runs (the first check of C1 and B2 together on M2), L 163/163 in 3, S 2122/2122 in 2
  (C1 on S). The machine stood at 91-99 % of its 24 logical cores in every M2 and L run, so the
  worker count moved the wall by 3 % at most (M2 33.5 / 33.7 / 34.4 min at 8 / 10 / 12 workers, L
  17.8 / 18.2 / 18.3): fewer workers only move cores from the light tiles to the heaviest ones, which
  end the band. A light tile's worker used 1.2-1.4 logical cores on average (about 2 in step 1's
  bursts), while A1 reserved 2 per light tile: at 12 workers M2's three heavy tiles got 2 threads
  each (the heaviest at 1.8 cores, 16 M pairs a minute) until the light part ended at +15 min. Their
  tail alone checks 6-7 M pairs per core and minute against 9-11 beside light tiles, so the wall
  follows the heavy tiles' pairs done when the light part ends; with one core per light tile they
  get 5-7 threads.

| Choice (this PC, scratch copies) | M2 | L | S |
| --- | ---: | ---: | ---: |
| Main of 2026-11-04: 12 workers, `LIGHT_CORES` 2 | 34.4 / 34.3 min | 18.3 min | |
| A cap at 8 workers, `LIGHT_CORES` 2 | 33.5 min | 17.8 min | |
| **`LIGHT_CORES` 1, no cap (taken)** | **32.5 / 32.7 min** | **17.8 min** | **29.3 min** |
| `LIGHT_CORES` 1 and a cap at 8 workers | 31.7 min | | 32.6 min |
| `LIGHT_CORES` 0 (the heavy tiles share every core), 12 workers | 32.8 min, the light tiles slower | | |

| M2's heaviest tile, per 10 min of its pair search: threads / cores used / M pairs a minute | Main, 12 workers | `LIGHT_CORES` 1, 12 workers |
| --- | ---: | ---: |
| 1st 10 min | 2.0 / 1.8 / 16 | 5.2 / 3.5 / 30 |
| 2nd 10 min | 8.1 / 6.7 / 66 | 9.2 / 6.6 / 69 |
| 3rd 10 min | 14.9 / 11.7 / 84 | 17.0 / 13.5 / 90 |
| The rest, alone | 24 / 19.2 / 119 | 24 / 19.4 / 117 |
| Its pairs checked when the light part ended (of 2101 M) | 446 M at +15 min | 725 M at +17 min |

A cap is not taken: on top of the new split it saves M2 another 0.8-1.0 min but costs the S band 3.3
min (a band of light tiles takes every worker it gets: 29.3 min at 12 workers, 32.6 at 8, the
machine at 80 and 62 %), and a run of the whole country is mostly light tiles (S is 2122 of its 3435).
Open: more workers than physical cores for a band of light tiles (S at 12 workers left the machine at
80 %); holding light claims back while heavy tiles run (by the measured rates at most about 3 min of
M2); the heaviest tile stays the floor (M2 1901-2063 s, L 1069-1094 s), so splitting it (A4) is the
next lever.

### The recommendation: one core per light tile and no cap, and how to fit it to a country and a computer

**The recommendation, the user's choice of 2026-11-05 among the options above: `LIGHT_CORES` 1 and the
workers `worker_count` gives, with no cap.** The reasons:

- A country is mostly light tiles (S is 2122 of Slovakia's 3435), and a band of light tiles takes
  every worker it gets: a cap at 8 wins 0.8-1.0 min of M2 and loses 3.3 min of S.
- The split costs a band without heavy tiles nothing (`_threads` reads it only for a heavy tile), and
  in a band with heavy tiles it moves their pairs out of the tail, where a core checks 6-7 M pairs a
  minute, into the light part, where it checks 9-11.
- Beyond it nothing is left to win: with `LIGHT_CORES` 0 the heavy tiles got more threads but no more
  cores, since the system shares a full machine thread by thread, and the light tiles ran slower.
- It is scheduling only: no count depends on it, so a wrong value costs minutes, never results.

These values come from one country and one computer: Slovakia, whose lines gather in the Tatras, on
12 physical and 24 logical cores with 25 GiB or more free. The tables say what is measured; the rest
is read from how `_threads` and `worker_count` work, to be checked with one band (below) before a
long run.

| A country's relief | What ends a band | What to expect | What to do |
| --- | --- | --- | --- |
| Lines gathered in a few massifs: a few heavy tiles among many light ones (Slovakia: measured) | The heaviest tile | The split pays a few %, the worker count hardly matters | The defaults |
| Gentle everywhere, no tile heavy (measured on a band like that, S) | The light tiles: their seconds over the workers | The split plays no part, every worker counts, the machine stays below full (S at 12 workers: 80 %) | Every worker the memory and the cores allow, no cap; more workers than physical cores are untested |
| High relief in most tiles: more heavy tiles than workers, the Alps or Norway (not measured) | The heavy tiles together: their CPU seconds over the cores | No light tile holds cores back, so the split plays little part; each tile runs on few threads, where a core checks the most pairs | No cap; check one band |

Which row a country is shows at the start of its first run: `manifest.sqlite` holds each tile's
`weight`, from the relief, and the tiles of at least `HEAVY_SHARE` of the largest are the heavy ones
(Slovakia: 4 of M2's 575). A handful is the first row, none the second, more than the workers the
third. The relief's constants are fitted on Slovakia: in another country the order of the claims
holds (it follows the km² of steep slopes), while which tiles are heavy depends on `RELIEF_EXPONENT`.
A tile without slopes of 45° at 30 m weighs 0, so in a gentle country most tiles keep the rowid order
among them. Later bands weigh by the lines counted, so a poor fit costs one band's order at most, and
the order is worth little in any case: 4-8 % of the wall in Slovakia, measured.

| A computer | What sets the workers | What to expect | What to do |
| --- | --- | --- | --- |
| Memory for a worker on every physical core (this PC with 25 GiB free for M2, 12 × 2.1 GiB: measured) | The physical cores | A full machine: the split matters, and 8 to 12 workers lie within 3 % | The defaults |
| Less memory: `worker_count` below the physical cores (7-8 workers before 32 B/px: measured) | The memory free when the run starts | The idle cores go to the heavy tiles under either split (6 threads instead of 5 at 7 workers of M2); a band of light tiles gains from every worker added | Close other programs before a run |
| Fewer cores, two logical per physical (the 5650G: 6 workers, 12 logical; not measured) | The physical cores | A heavy tile beside five light ones takes 7 threads instead of 2 | The defaults; check one band |
| One logical core per physical one (not measured) | The physical cores | Every tile gets 1 thread, a heavy one too: `LIGHT_CORES` 1 leaves it nothing, so here a cap below the cores may pay | Measure a cap on one band |
| A slow disk for `work/` (the Unraid array: `bench` on the 5650G) | The disk | Step 1 waits on I/O, the machine stays well below full, and more workers do not help | The data and `work/` on an SSD |

`COUNT_PIXEL_BYTES` is measured on bands without a surface model; a country with one holds about
twice the grids in its work folders (`_disk_bytes` counts them): compare the tiles' private bytes with
the budget after its first band, and the machine's free RAM in the timeline. A tile's working set may
pass the budget harmlessly since a worker keeps its grids' views (M2's largest: 2.28 against 2.1 GiB),
which count the same pages twice.

To check a country or a computer before a long run: count one band that holds a heavy tile, the
smallest that does (L in Slovakia: 18 min), on a scratch copy of the country's folder, at the default
workers and at about two thirds of them:

    python findaline.py country run <id> --bands L --processes <N> --yes --data-dir <scratch>

Compare the walls, not the tile seconds, which grow with the workers as the tiles slow each other
down. The timeline `logs/samples-*.csv` tells the rest. A machine at 90 % or more with both walls
within a few % is bound by its cores: leave the defaults. Well below that, look at the disks' MB/s and
the free RAM before adding workers. A band that ends on one tile long after the light part
(`running_tiles` at 1-3 for most of the run) gains from the split, not from more workers:
`LIGHT_CORES` is a constant of `country.py`, and each value is one more run of that band.

### Done, stage 3 (2026-11-05, wave 2: branch `country-perf-3-other`)

- **B4, what "other" holds and what a tile writes** (on `LIGHT_CORES` 1; the counts of S, M2 and L
  identical to the user's tiles; R13, R14 and R16 unchanged). S 29.3 → 24.5 min, M2 32.5 → 31.9, L
  17.8 → 16.6 min, and what a band writes to the disks 685 → 4 GB, 290 → 6, 65 → 1 GB. S
  gains most since its wall is its light tiles' seconds over the workers; M2's and L's end is their
  heaviest tile, which gains only the cores the light tiles free sooner.

"other" is the time of a tile between the progress bars: in W1's runs a median of 0.88 s in S, 1.61 in
M2 and 2.77 in L, about twice what a tile takes alone. Its parts, from cProfile while no bar runs, 12
processes at once on this PC, seconds per tile before → after:

| Part of "other" | S | M2 | L |
| --- | ---: | ---: | ---: |
| The cache index: SQLite, a connection per data tile in `cache.state` | 0.116 → 0.029 | 0.458 → 0.038 | 1.279 → 0.047 |
| The outline's test of each data tile, 0.7 ms each | 0.021 → 0.026 | 0.114 → 0.036 | 0.372 → 0.047 |
| `gc.collect` before the folder goes | 0.118 → 0.001 | 0.126 → 0.003 | 0.107 → 0.001 |
| The gaps' scan (`_gaps_rows`) | 0.124 → 0.088 | 0.163 → 0.134 | 0.103 → 0.087 |
| The flush of the filled mask | 0.051 → 0 | 0.107 → 0 | 0.061 → 0 |
| The mosaics' NaN or NODATA fill before the bar | 0.097 → 0.092 | 0.106 → 0.155 | 0.091 → 0.106 |
| Memmaps created, `np.load` | 0.051 → 0.049 | 0.073 → 0.052 | 0.077 → 0.050 |
| Paths, `exists` | 0.020 → 0.015 | 0.064 → 0.040 | 0.163 → 0.085 |
| Thread pools (`each_layer`) | 0.025 → 0.017 | 0.110 → 0.032 | 0.062 → 0.011 |
| The sea's check | 0.022 → 0.002 | 0.034 → 0.002 | 0.019 → 0.002 |
| The CRS, `transform_bounds` | 0.015 → 0.015 | 0.016 → 0.016 | 0.015 → 0.016 |
| The rest (after: closing the views kept and deleting, moved in from the cleanup) | 0.064 → 0.091 | 0.087 → 0.122 | 0.109 → 0.132 |
| Sum in cProfile | 0.72 → 0.43 | 1.46 → 0.63 | 2.46 → 0.58 |

Without cProfile, the same tiles under the same load: "other" a median of 0.78 → 0.39 s in S, 1.37 →
0.61 in M2, 2.80 → 0.52 in L, whole tiles 127 → 108 s, 99 → 84 and 98 → 84. Around the clock a tile
takes 0.002 s before it and 0.005 s after it, the cleanup 0.16 s → 0; a worker's first tile of a band
costs 1-3 s once more for its plan. What is left is inherent or small.

What changed: `cache.states` (the tiles' answers on one connection per top-level folder, for
`prepare_layer` and `water_body_mask`); `tilings._outline` (`shapely.prepare` on the copy `project`
makes); a new mask is all False, so strips with nothing to mark are not written (`_gaps_rows`,
`near_rows`, `_fill_water_rows`, `_border_gaps_rows`, `coast.sea_mask_rows` inland), and no lake to
fill labels nothing; `TileWork.loop(freeze=True)` (what a worker's first tile left alive is frozen,
so a collection walks that tile's objects only); and the disk:

| A tile alone (the machine's disk counters, the idle rate taken off, 30 s of settling included) | S | M2 | L |
| --- | ---: | ---: | ---: |
| The process's own writes (the meta's `io`) | 0.1 MB | 0.2 MB | 0.3 MB |
| Written, before | 270-282 MB | 376 MB | 509-570 MB |
| Written, with the flushes off and nothing else | 231-319 MB | 320-335 MB | 269-589 MB |
| Written, with the views held | 0-0.5 MB | 0.2-0.8 MB | 2-6 MB |
| Read: from the disks / by `io` | 50 / 62-73 MB | 71 / 195 MB | 37-42 / 63-128 MB |
| The work folder | 308 MB | 427 MB | 488 MB |

On Windows a mapped file's written pages go to the disk within seconds of the last view that wrote
them closing, also for a file deleted soon after: four grids of 150 MB wrote 600 MB with their views
closed 3 s before the delete, and 2 MB with the views open until just before it. So a worker keeps
each grid's view (`mosaic.flush_grid`, `HELD_GRIDS`, set by `country worker` only) until
`TileWork._remove_grids` closes them and deletes the folder at the end of `count`; the app and
`--processes 0` flush as before. `file.truncate` is no way out: extending a file with it zero-fills on
Windows and is slower. The meta's `io` stays as it is: it counts what GDAL reads through the system's
cache and never saw a mapped grid; `country profile` says so and gives the run's disks in GB. A Linux
worker was not measured.

The cost is in the working set: a tile's at most 1.36 → 2.28 GiB in M2, 1.23 → 1.86 in S, 1.12 → 1.77
in L, the workers' peak 13.0 → 20.6, 18.5 → 22.1 and 10.9 → 14.8 GiB. A process's working set counts a
page once per view: a grid of 400 MB written through a view kept open and read through a second took
the working set 0.40 → 0.78 GiB and the machine's memory in use 31.05 → 31.06 GiB. So the machine
moved far less: memory in use 35.4 → 36.6 GiB on average in S with the same peak of 45.4 GiB, the
least free RAM unchanged at 16.2 GiB; M2's fell to 18.7 from 19.8-21.2 GiB. A tile's working set now
passes its budget (S 1.86 against 1.6 GiB, M2 2.28 against 2.1) while its private bytes stay at half of
it, so `COUNT_PIXEL_BYTES` stays. Under memory pressure the system should write those pages out as it
did before; that case was not measured.

The surface model, which Slovakia's bands have not, went through real `country worker` processes on a
scratch copy of the band study's `sk-fatra` (surface model, water and gaps filled), with the views held
against main's flushed ones: the bands L1-5m55, S1m60 and M2m60, 39 tiles and 3 735 026 lines, every
tile's counts identical and no tile failed. Its largest tiles, 38.5 Mpx at 1 m with a budget of 1.65
GiB, held 0.82 GiB of private bytes and a working set of 2.16 GiB (1.05 with the views flushed).

Open, both outside B4's brief, and both done in wave 3 below:

| The time of a stage that a tile may not need | S | M2 | L |
| --- | ---: | ---: | ---: |
| Prominence and drop, of the band's tile seconds | 2.37 h, 49 % | 0.40 h, 12 % | 0.10 h, 6 % |
| Of it in tiles with no line (S 1700 of 2122, M2 385 of 575, L 75 of 163) | 1.55 h | 0.13 h | 0.02 h |
| Area coverage (a tile inside the outline has a mask all True) | 0.38 h | 0.15 h | 0.03 h |

`search._anchors` computes prominence and drop for every anchor before the pair search, and
Slovakia's bands set no limit on them, so a tile with no line never uses them.

### Done, stage 3 (2026-11-05, wave 3: branch `country-perf-3-lazy`)

- **B5, the two cheap changes of wave 2's open list**, both in the count only, the app's search on its
  old path. The anchors' values at a tile's first line: with no limit on them (`min_prominence`,
  `min_prominence_both`, `min_drop`) `search._anchors(deferred=True)` leaves prominence and drop out,
  and `find_valid_lines` takes a callable, asked once by the first evaluated part with a valid line
  (`_sink_lines` puts the bar of the pairs back after it). A full mask inside the country: a tile
  whose grid lies inside the outline (`Plan.border` False) skips the burn, and skips the count of its
  coverage, which only one line of its log read. Every tile's counts identical to the user's: S
  2122/2122, M2 575/575, L 163/163. No stored data changes.

| Hours of tile seconds | S, B4 | S, B5 | M2, B4 | M2, B5 | L, B4 | L, B5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Prominence and drop | 2.37 | 0.99 | 0.40 | 0.28 | 0.10 | 0.08 |
| Area coverage | 0.38 | 0.09 | 0.15 | 0.05 | 0.03 | 0.02 |
| All the other stages | 2.14 | 2.62 | 2.87 | 2.81 | 1.43 | 1.51 |
| Sum | 4.89 | 3.70 | 3.42 | 3.14 | 1.56 | 1.61 |

What it shows:

- **S** takes 18.6 min against 24.5 (-24 %), its CPU 6.13 → 4.86 h (-21 %). The estimate was about 15
  min, for two reasons. The two stages lost 1.67 h of 4.89, 34 % against the estimate's 40 %. And the
  other stages rose 0.48 h, as tile seconds do when tiles compete, since a worker now spends most of
  its time in step 1 beside eleven others doing the same.
- **M2** takes 30.4 min against 31.9, its heaviest tile 1826 s against 1913: the light part ends two
  minutes sooner and leaves that tile the cores. Its CPU barely moves, 10.24 → 10.13 h.
- **L** does not move. Its first run took 17.6 min against B4's 16.6, so the code before was counted
  again that afternoon on the same copy: 17.4 min, then this code again, 17.1 min. All three have the
  same counts and 5.34-5.37 h of CPU. Equal code moved by a minute within the day, so B4's 16.6 min was
  a good run, and a band ended by one tile should be compared over more than one run. The last run
  shared the machine with another session's code and came out the fastest.
- **Memory**: the prominence's peak now stands beside the pair search's instead of before it. A tile's
  private bytes reach 1.23 GiB in S (1.07 before) and 1.15 in M2 (0.99), under the budgets of 1.6
  and 2.1 GiB; its working set 2.09 and 2.41 GiB (1.86, 2.28), the pages counted once per view.

Left of the stage: 0.99 h of S, 0.28 h of M2 and 0.08 h of L in tiles with lines, where only the
anchors of those lines need the values.

## Round 5 (2026-11-07/08): the country layer, continued

Slovakia's pilot again, on this PC (12 cores / 24 threads, 61.6 GiB), from main d466347 (round 4's end with the
no-fall zone and the A-frames, which change nothing at 0 / 0). Three stages: measurements without code (stage 1),
count-preserving code in five branches, each measured against its own base (stage 2), and the recount bundle
(stage 3: cube v2, step 1 per group of tiles, the surface model, the superset; docs/roadmap.md, "Country layer").
Every run under the exclusive lock on a scratch copy of `countries/slovakia` or `countries/sk-sulov`, the cache a
junction to the real one, a dead proxy in the runs' environment (the cache's index unchanged by every run), the
counts compared tile by tile with the user's tiles (`countcube.load_tile`, every array). The runs, their logs and
timelines are in `local/country-perf-2026-11-07/` (`stage1/<item>/`, `stage2/<item>/`).

### The user's decisions (2026-11-07)

- **The superset goes into Slovakia's cube** (the no-fall zone of 5 m and A-frames of 2 m): the count mode takes the
  ladder of zones in stage 2 (Z1 below), cube v2's word B keeps the two values per line (stage 3, wave A), and the
  recount counts with `options.end_zone` 5 and `options.anchor_lift` 2, so no tile is counted twice.
- **The band study is unblocked**: its areas counted in the PC's idle time between the measurements, so its profile
  is ready for the recount.
- **The order**: stage 1, then 2, then 3. The PC was free for 40 hours: every measurement under the exclusive lock,
  A/B on the same day and the same base commit.
- **The surface model (the DMP)**: in the recount bundle, with its cost measured first (D1 below).
- **A report page at the end of the round**, for the user and anyone outside the project.

### Stage 1: what was measured (main d466347, no code)

| Item | Measured | Result |
| --- | --- | --- |
| W1 | The first run of all four bands in one `country run` (3435 tiles pending, relief weights for all, 12 workers) | 64.7 min from its start, 64.0 of tiles, 11.93 tile hours, 22.27 CPU hours, the machine at 98 %; twelve tiles running until +60.1 min, then M2's Tatras tile E-350000_N-1190000 alone for 4.1 min (3840 s, 16 425 CPU s); counts identical (S 2122/2122, M 575/575, L 163/163, M2 575/575); 1 183 773 337 lines, 3 679 609 spots |
| D1 | sk-sulov's four layer bands with the surface model (`nmpt: mark`) and without, A/B/A/B | 1.30× the tile seconds (175.2 against 134.7 s), 1.18× the CPU seconds, 1.22-1.24× the wall; all of it in step 1 (2.0×: the obstacle surface in "other" +12.6 s, the surface's gap filling +8.0, its stitching +6.0); the same lines and spots, only the trees flag moves (89-98 % of the lines over trees per band); a tile's private peak the same, its working set +36 % in S |
| C4 | Where M2's and L's heaviest tiles spend their seconds, each alone on 24 threads, timers in a worktree | M2's 1012 s: `_pairs`' first pass 27 %, its second pass (the anchors over 1024 pairs, all again) 13 %, `_evaluate` 35 %, the numpy around it 10 %, `covered_pixels` 2 %, the counter 9 %; L's 729 s alike; a valid line's pixels walked about 3.75 times; numba's OpenMP threads spinning through the serial numpy: 19 % of the tile's CPU (21 % in L) |
| C5 | The counter's share of the tiles (W1's meta, no run) | 1.69 % of all tile seconds (S 0.01 %, M 1.69, L 2.89, M2 2.42 %); 4-5 % of the heaviest tiles, 6-7 % when M2 runs alone: 120-190 s of serial numpy on the critical path |
| I1 | The S band of a 30 × 30 km box near Opole (210 sheets) read from the network share Z: against the local disk | Not bound by the link at 12 workers (36-43 MB/s on average of the 150-170 MB/s 12 readers get); the stitching per tile 1.36 s on a first read, 0.85 s again, 0.71 s locally, tile seconds +10 % and +3 %; the counts equal; the one real cost the prefetch's `prune`: 1503 `os.path.exists` in 18.5 s with the share's metadata cold (I2). LERC_ZSTD decodes 3.3-4× faster than deflate on one thread, 1.2-1.8× on eight, `build_mosaic` 13-25 % faster |
| W2 | The S band at 16 workers against 12 (`--processes 16`) | 18.3 min both, the wall to the second; tile seconds 3.61 → 4.80 h, CPU +11 %, all workers' private peak 17.4 → 23.7 GiB: no rule for `worker_count` |
| W4 | W1 again with `OMP_WAIT_POLICY=PASSIVE`, and sk-sulov without and with it | below: the item "omp" |

What the stage told: an all-bands run is the work of 24 busy logical cores, its tail one tile of 4.1 minutes, so
the split of the heaviest core (W3) was not taken and the work itself became the target: the heavy tiles' second
pass and their single-threaded numpy (C4), the spinning threads (W4), prominence and drop of every anchor (round
4's leftover), and step 1 of the light tiles (S: 63 % of its tile seconds).

### Stage 2: the five branches (each count-preserving, the counts identical tile by tile)

- **omp** (tag `history/perf5-omp`): numba's OpenMP layer (vcomp140 on Windows) keeps its threads spinning after
  each parallel region: through 15 s of serial numpy between two kernels a tile's 7 other threads burnt 6.2 CPU
  seconds, none with `OMP_WAIT_POLICY=PASSIVE`. With PASSIVE (or `NUMBA_THREADING_LAYER=workqueue`, the same within
  one run) sk-sulov's four layer bands took 19 % fewer CPU seconds and 6 % fewer tile seconds with cores free, and
  the first all-bands run 5.4 % fewer CPU seconds (22.27 → 21.08 h, all in the heavy tiles' pair search) at a wall
  within the spread of equal runs (64.7 → 63.7 min). PASSIVE is set in the workers' environment
  (`country._worker_env`, the caller's own value wins). Until then a tile's CPU seconds held the spinning, so
  compare CPU seconds of runs at the same load only (the same S tiles: 4.86 CPU-h alone at 84 % against 3.93 inside
  the all-bands run at 98 %).
- **C1 and Z1** (tag `history/perf5-anchors`): prominence and drop of the lines' anchors only.
  `linesearch.LazyAnchorValues` computes, part by part, the anchors of the part's passing lines not known yet, each
  once; after `SUBSET_CALLS` (4) computations the next takes every useful anchor not known yet in the rows a line of
  the pairs still to be evaluated can reach. `terrain.prominence` and `terrain.drop` take `crop=True` (the part of
  the grid within reach of the given anchors), and a crop across the grid's width is a row slice of the grid, not a
  copy. A subset gets the values it has among all the anchors, bit for bit. Z1: the count mode passes the search's
  ladder of end zones, so each sink part carries `lift_needed` and `lift_no_zone` for cube v2 (nothing changes at
  0 / 0; on sk-sulov-ends at 5 m / 2 m no cost beyond the spread: 274-276 tile seconds with the ladder against
  268-295 without it). A third commit breaks a reference cycle that kept a count's memory-mapped grids alive until
  the cyclic collector ran (Windows then refuses to open the file for writing: tests/test_country.py's module
  fixture failed). In the squash, C9's blocks no longer filter the found pairs before the values are asked, so the
  merge asks the lazy values with the passing pairs only, as C1's branch did (`linesearch._evaluated`; without it
  `tests/test_count_mode.py::test_count_tile_without_a_line_computes_no_anchor_values` fails).
- **C2 and C7** (tag `history/perf5-step1`), step 1 of the light tiles (`sources/filling.py`). C2, a dry tile: the
  water body mask written without its reprojection when one tile of the mask holds one category all around the
  grid (858 of 2122 S tiles, 62 of 575 M, 42 of 575 M2, 1 of 163 L, each equal to the built mask), and the strips
  with no sea zone and no lake left out of `fill_water`. C7, a border tile's gap filling: the median's two middle
  values in the same passes, the rings' dilation only near the gaps, int32 keys, and no border gaps while no
  neighbour's rough boxes reach the grid (148 of S's 345 border tiles with gaps: the Hungarian and Ukrainian
  border).
- **C3** (tag `history/perf5-stitch`), the stitching (`sources/mosaic.py`): a float32 band with NaN as its nodata
  read without GDAL's mask, which decoded every block a second time with `GDAL_NUM_THREADS` above 1; no listing of
  a file's folder on its opening (`GDAL_DISABLE_READDIR_ON_OPEN=TRUE`); where no raster wrote before, such a raster
  on the grid read by GDAL straight into the mosaic's window. On the real cache 0 of 8 008 reads differ.
- **C8, C9 and I2** (tag `history/perf5-sink`). C8: the count mode's pair buffer holds 8192 pairs per anchor
  (`SINK_PAIR_BUFFER`, within `SINK_PAIR_BUFFER_BYTES` 128 MB a slice), so the heavy tiles' anchors need no
  writing pass; the search keeps 1024. C9: the numpy around `evaluate_lines`' kernel (wall angles, which lines
  pass, the table's columns) in blocks of `VALUE_BLOCK` pairs on a thread pool, the table the one of before bit
  for bit. I2: `NewestPerSheet.prune` answers from one listing per folder (`existing`, from `LISTING_FROM` paths
  in a folder) instead of a question per file.

### Step by step: Slovakia's S, M2 and L bands

Each column is one step's own A/B against its own base, measured on this PC under the exclusive lock with 12 workers
on a scratch copy of `countries/slovakia`. Both sides ran on Python 3.15.2, each base in a detached worktree with
its own venv; C3's first runs, which compared main's 3.13 venv with the branch's 3.15, are left out
(`stage2/C3/CONFOUNDED.md`).

- A cell reads "base → step". Several runs of a side are separated by commas; one value stands for all when every
  run gave it.
- The base is d466347 unless the column names another. Both sides ran one after the other unless the column says
  otherwise.
- The first column is round 4's end measured again in this round: every run of d466347 of the band, so its range is
  the spread of equal code.
- "W1 → W4" is PASSIVE inside the all-bands run, its only measurement per band, and so is the last column: the band's
  tiles ran beside the other bands', so their wall and the workers' peak are the run's.
- "The step's stages" are the stages the step works on: C1 prominence and drop, C2 the water mask with sea and lakes,
  C7 the terrain's gap filling with the border gaps, C3 the stitching of the terrain, C8 and C9 the pairs.
- Every run's manifest and tiles' meta are read the same way (`stage2/SQUASH/numbers.json`), and the counts are
  compared with the user's tiles.

| S | Round 4's end (d466347), 6 runs | W1 → W4 (in the all-bands run) | C1 + Z1 (743f8ef) | C2 (385c7b9) | C7 (4f54f28, base C2) | C3 (0b9e402; the runs over two days) | C8 (03d23fb) | C9 (54c1af6, base C8) | All five (318b9a2): W1 → ALL, in the all-bands run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the user's | 2122/2122 | 2122/2122 → 2122/2122 | 2122/2122 → 2122/2122 | 2122/2122 → 2122/2122 | 2122/2122 → 2122/2122 | 2122/2122 → 2122/2122 | not measured | not measured | 2122/2122 → 2122/2122 |
| Wall of the band's tiles, min | 18.2-18.7 | 52.2 → 51.8 | 18.3 → 15.7 | 18.2 → 16.5, 16.6 | 17.0, 16.9 → 15.6, 15.5 | 18.5, 18.7 → 17.5, 16.9, 17.0 | not measured | not measured | 52.2 → 40.3 |
| Tile hours | 3.59-3.67 | 3.40 → 3.40 | 3.60 → 3.06 | 3.59 → 3.24, 3.25 | 3.34, 3.31 → 3.07, 3.05 | 3.65, 3.67 → 3.43, 3.32, 3.33 | not measured | not measured | 3.40 → 2.08 |
| CPU hours | 4.80-4.85 | 3.93 → 3.93 | 4.81 → 4.25 | 4.81, 4.80 → 4.36, 4.37 | 4.40, 4.39 → 4.11 | 4.81, 4.85 → 4.43, 4.32, 4.32 | not measured | not measured | 3.93 → 2.26 |
| The step's stages, h |  |  | 0.958 → 0.078 | 0.702, 0.706 → 0.385, 0.387 | 0.679, 0.681 → 0.420, 0.423 | 0.420, 0.425 → 0.227, 0.223, 0.223 | not measured | not measured |  |
| Private per tile: median / max, GiB | 0.28-0.29 / 1.23 | 0.31 / 1.23 → 0.31 / 1.23 | 0.29 / 1.23 → 0.28 / 1.09 | 0.28 / 1.23 → 0.28 / 1.23 | 0.28 / 1.23 → 0.28 / 1.23 | 0.29 / 1.23 → 0.28 / 1.23 | not measured | not measured | 0.31 / 1.23 → 0.30 / 0.99 |
| All workers, private peak, GiB | 17.1-19.7 | 11.9 → 11.3 | 19.7 → 5.7 | 17.9, 17.1 → 19.9, 17.6 | 20.2, 19.9 → 18.0, 18.8 | 17.4, 18.1 → 17.1, 19.9, 19.2 | not measured | not measured | 11.9 → 8.7 |

| M2 | Round 4's end (d466347), 3 runs | W1 → W4 (in the all-bands run) | C1 + Z1 (743f8ef) | C2 (385c7b9; base: round 4's B5, 2026-11-05) | C7 (4f54f28; base: C2's run, the day before) | C3 (0b9e402) | C8 (03d23fb) | C9 (54c1af6, base C8) | All five (318b9a2): W1 → ALL, in the all-bands run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the user's | 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 | 575/575 → 575/575 |
| Wall of the band's tiles, min | 30.9-31.8 | 64.0 → 63.0 | 31.8 → 31.2 | 30.4 → 30.8 | 30.8 → 30.6 | 30.9 → 30.6 | 31.0 → 27.4 | 27.4 → 26.5 | 64.0 → 51.9 |
| Tile hours | 3.11-3.25 | 4.15 → 4.08 | 3.25 → 3.02 | 3.12 → 3.01 | 3.01 → 2.89 | 3.11 → 2.96 | 3.11 → 2.92 | 2.96 → 2.93 | 4.15 → 3.40 |
| CPU hours | 10.46-10.51 | 10.21 → 9.35 | 10.51 → 10.39 | 10.13 → 10.48 | 10.48 → 10.30 | 10.46 → 10.35 | 10.48 → 9.23 | 9.18 → 8.89 | 10.21 → 7.47 |
| The step's stages, h |  |  | 0.277 → 0.110 | 0.301 → 0.247 | 0.414 → 0.254 | 0.215 → 0.106 | 1.477 → 1.321 | 1.328 → 1.304 |  |
| Private per tile: median / max, GiB | 0.44-0.45 / 1.12 | 0.46 / 1.12 → 0.46 / 1.12 | 0.44 / 1.12 → 0.29 / 1.48 | 0.45 / 1.15 → 0.45 / 1.12 | 0.45 / 1.12 → 0.43 / 1.12 | 0.45 / 1.12 → 0.45 / 1.12 | 0.45 / 1.12 → 0.44 / 1.12 | 0.45 / 1.12 → 0.44 / 1.11 | 0.46 / 1.12 → 0.32 / 1.24 |
| All workers, private peak, GiB | 10.6-12.7 | 11.9 → 11.3 | 12.7 → 10.1 | 10.4 → 11.6 | 11.6 → 12.8 | 12.1 → 11.6 | 10.6 → 10.9 | 12.2 → 12.5 | 11.9 → 8.7 |

| L | Round 4's end (d466347), 3 runs | W1 → W4 (in the all-bands run) | C1 + Z1 (743f8ef) | C2 (385c7b9; base: round 4's B5, 2026-11-05) | C7 (4f54f28) | C3 (0b9e402) | C8 (03d23fb) | C9 (54c1af6, base C8) | All five (318b9a2): W1 → ALL, in the all-bands run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Counts identical to the user's | 163/163 | 163/163 → 163/163 | 163/163 → 163/163 | 163/163 → 163/163 | not measured | 163/163 → 163/163 | 163/163 → 163/163 | 163/163 → 163/163 | 163/163 → 163/163 |
| Wall of the band's tiles, min | 17.5-18.2 | 57.0 → 56.8 | 17.5 → 17.6 | 17.4, 17.1 → 17.4 | not measured | 18.2 → 17.3 | 17.5 → 15.2 | 15.3 → 14.4 | 57.0 → 48.0 |
| Tile hours | 1.59-1.65 | 2.29 → 2.27 | 1.59 → 1.57 | 1.57 → 1.57 | not measured | 1.65 → 1.51 | 1.59 → 1.46 | 1.49 → 1.46 | 2.29 → 2.02 |
| CPU hours | 5.51-5.54 | 4.82 → 4.62 | 5.53 → 5.53 | 5.36, 5.37 → 5.55 | not measured | 5.51 → 5.51 | 5.54 → 4.78 | 4.77 → 4.51 | 4.82 → 3.80 |
| The step's stages, h |  |  | 0.079 → 0.046 | 0.067, 0.070 → 0.061 | not measured | 0.104 → 0.045 | 1.059 → 0.966 | 0.971 → 0.957 |  |
| Private per tile: median / max, GiB | 0.39-0.40 / 0.92 | 0.42 / 0.92 → 0.41 / 0.92 | 0.39 / 0.92 → 0.39 / 1.15 | 0.40 / 0.89, 0.40 / 0.91 → 0.40 / 0.92 | not measured | 0.39 / 0.92 → 0.39 / 0.92 | 0.40 / 0.92 → 0.39 / 0.92 | 0.39 / 0.91 → 0.39 / 0.88 | 0.42 / 0.92 → 0.40 / 0.94 |
| All workers, private peak, GiB | 6.1-7.7 | 11.9 → 11.3 | 6.1 → 6.5 | 7.5, 6.5 → 6.6 | not measured | 6.8 → 7.1 | 7.7 → 7.1 | 7.3 → 6.9 | 11.9 → 8.7 |

### The heavy tile alone, and the prefetch on Z:

M2's heaviest tile, E-350000_N-1190000 (474 M lines), counted alone on 24 threads (`--bands M2 --max-tiles 1`, only
that tile pending): each pair of columns one A/B of the same day (`stage2/C8/tile-M2-*`, `stage2/C9/tile-M2-*`,
`stage2/C1/slice/H-*`).

| M2 E-350000_N-1190000 alone | d466347 | C8 (03d23fb) | C8 again | C9 (54c1af6) | C1 (743f8ef) | C1 + the row slice (1db3ca5) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tile seconds | 990.5 | 857.3 | 857.4 | 786.8 | 1004.2 | 1009.0 |
| CPU seconds | 19 510 | 16 582 | 16 491 | 15 006 | 19 621 | 19 583 |
| Private peak / working set, GiB | 1.120 / 2.371 | 1.118 / 2.369 | 1.117 / 2.368 | 1.106 / 2.357 | 1.484 / 2.744 | 1.298 / 2.559 |
| Counts | equal | equal | equal | equal | equal | equal |

C1 does not shorten this tile (its values took 4.1 s of it); its memory is the row slice's subject: the copy of a crop
spanning the grid's width came on top of the pair search's memory, 1.119 GiB before C1 (stage 1's and the sink's
runs of the tile), 1.484 with C1, 1.298 with the slice. The 0.18 GiB left over the base are the prominence's
temporaries over the whole tile beside the pending pairs, after `SUBSET_CALLS` parts instead of at the first line
(the anchors agent's reading, not measured further). Every tile's peak stays under its budget of `WORKER_BASE` + 32 B
per pixel (2.1 GiB for M2's 7304 × 7304 px).

I2, the prefetch of the study area pl-opole (210 sheets of the 30 km box of I1) on the network share Z:, reads only;
"cold" the first question to the share after it idled for hours, "warm" seconds after another run
(`stage2/I2/results.md`):

| Run | Code | Share | Prefetch s | `prune` s | File system questions |
| --- | --- | --- | ---: | ---: | --- |
| I1, 2026-11-07 | d466347 | cold | 21.87 | 17.88 | 1503 `os.path.exists`, 18.46 s |
| hold 2 | d466347 | cold | 22.01 | 17.75 | 1503 `os.path.exists`, 18.43 s |
| hold 3 | 31483e1 | cold | 3.95 | 1.97 | one `os.scandir`, 1.94 s |
| holds 2 and 3, three runs each | d466347 / 31483e1 | warm | 1.10-1.15 / 1.07-1.12 | 0.069-0.087 / 0.030-0.031 | |

One listing of the share's folder (13 606 sheets on Z: that day) costs about 1.9 s cold and 0.03 s warm and grows with
the folder; the questions of before grew with the grid (a country's prefetch asks about all its sheets).

### All five together: the first run of all bands again (2026-11-08)

The five squashed onto d466347 (318b9a2), Slovakia's four bands in one `country run` as W1:

- every tile pending and no weights, so the relief weights for all;
- 12 workers, the exclusive lock, a dead proxy;
- W1's driver on the squash's worktree, Python 3.15.2 as W1's (`stage2/ALL/results.md`).

The cache's index stayed unchanged, and no worker tried a neighbour's data, as in W1.

| | W1 (d466347) | W4 (d466347, PASSIVE) | ALL (318b9a2) |
| --- | ---: | ---: | ---: |
| Counts identical to the user's tiles | S 2122/2122, M 575/575, L 163/163, M2 575/575 | the same | the same |
| The run from its start | 64.7 min | 63.7 min | 52.5 min |
| Wall of the tiles | 64.0 min | 63.0 min | 51.9 min |
| Tile hours, all bands | 11.93 | 11.83 | 9.33 |
| CPU hours of the tiles, all bands | 22.27 | 21.08 | 16.20 |
| Twelve tiles running until | +60.1 min | +59.8 min | +47.0 min |
| One tile alone (M2 E-350000_N-1190000) | 4.1 min | 3.5 min | 3.9 min |
| Machine CPU, mean | 98 % | 96 % | 96 % |
| Free RAM: at the start / the least | 35.2 / 22.4 GiB | 33.4 / 20.3 GiB | 27.1 / 18.0 GiB |
| All workers, private: peak / mean | 11.9 / 5.4 GiB | 11.3 / 5.5 GiB | 8.7 / 4.7 GiB |
| All workers, working set: peak | 19.9 GiB | 20.7 GiB | 17.1 GiB |
| The machine's disks: read / written | 90.5 / 10.7 GB | 92.2 / 10.8 GB | 96.3 / 13.0 GB |
| The cube | 1 183 773 337 lines, 3 679 609 spots | the same | the same |

| | S: W1 → ALL | M: W1 → ALL | L: W1 → ALL | M2: W1 → ALL |
| --- | ---: | ---: | ---: | ---: |
| Wall of the band's tiles, min | 52.2 → 40.3 | 55.2 → 42.7 | 57.0 → 48.0 | 64.0 → 51.9 |
| Tile hours | 3.40 → 2.08 | 2.09 → 1.84 | 2.29 → 2.02 | 4.15 → 3.40 |
| CPU hours | 3.93 → 2.26 | 3.31 → 2.67 | 4.82 → 3.80 | 10.21 → 7.47 |
| Step 1, h | 2.15 → 1.63 | 0.80 → 0.67 | 0.36 → 0.31 | 1.15 → 0.91 |
| Anchor pairs, h | 0.01 → 0.01 | 0.97 → 0.95 | 1.79 → 1.59 | 2.56 → 2.22 |
| Prominence and drop, h | 0.89 → 0.06 | 0.20 → 0.08 | 0.07 → 0.04 | 0.26 → 0.09 |
| Stitching terrain, h | 0.40 → 0.24 | 0.15 → 0.10 | 0.11 → 0.09 | 0.18 → 0.13 |
| Gap filling: terrain, h | 0.43 → 0.29 | 0.21 → 0.15 | 0.09 → 0.06 | 0.34 → 0.21 |
| Median tile, s | 3.3 → 2.7 | 6.2 → 4.0 | 11.3 → 9.1 | 9.0 → 5.4 |
| Heaviest tile, s (CPU s) | 37 (43) → 32 (37) | 1432 (3172) → 1391 (2662) | 3414 (9685) → 2875 (7244) | 3840 (16 425) → 3109 (11 225) |
| Private per tile: median / max, GiB | 0.31 / 1.23 → 0.30 / 0.99 | 0.41 / 0.94 → 0.32 / 1.00 | 0.42 / 0.92 → 0.40 / 0.94 | 0.46 / 1.12 → 0.32 / 1.24 |

What it shows:

- **The run**: 64.7 → 52.5 min (−19 %), the tile hours 11.93 → 9.33 (−22 %), the CPU hours 22.27 → 16.20 (−27 %),
  every count the same. One run of each, so the spread is not known for this run; round 4 measured about a minute
  for a band ended by one tile.
- **The tail is still one tile**: M2's Tatras tile alone for 3.9 min, the machine at 61-66 % meanwhile. The light
  part ends 13 minutes sooner (+47.0 instead of +60.1), so the three heaviest tiles now run from the start nearly
  to the end: M2's E-340000_N-1190000 until +48.0 min, L's E-360000_N-1200000 until +48.2, M2's E-350000_N-1190000
  until +52.1. They are what the next step of the wall is about (the split of a core, W3, or more cores for the
  heavy tiles at the end).
- **Memory**: the M2 band's tiles reach 1.24 GiB of private bytes at most (1.12 in W1: C1's switch to every useful
  anchor, after the row slice), under their budget of 2.1 GiB; the workers' private peak falls 11.9 → 8.7 GiB.
  Other programs held 8 GiB more of the RAM that morning (27.1 GiB free at the start against 35.2).

### Memory

- **C8**: the buffer commits 128 MB instead of 16 MB while a slice's first pass runs. The private bytes sampled in
  the "anchor pairs" stage rose by it (median 0.257 → 0.365 GiB on M2, 0.263 → 0.367 on L); a tile's peak stays in
  step 1 (M2 at most 1.119 → 1.117 GiB, L 0.916 → 0.915). `country.WORKER_BASE` stays: a worker's budget for these
  bands is 512 MiB + 32 B per pixel, 2.1 GiB for M2's 53 Mpx tiles and 1.6 GiB for L's, against peaks of 1.12 and
  0.92 GiB. S was not measured with C8: its pairs stage gets the same 112 MB, its step-1 peak was at most 1.23 GiB.
- **C1**: with every useful anchor computed at once after `SUBSET_CALLS` parts, a crop spans the grid's width,
  and its float32 copy came on top of the pair search's memory: M2's heaviest tile 1.12 → 1.48 GiB private at its
  peak, L's 0.92 → 1.15 (C1's band runs). The row slice (1db3ca5) brought the heavy tile alone to 1.298 GiB (1.484
  with 743f8ef, 1.119 before C1); in the all-bands run on the five together the M2 band's tiles reached 1.24 GiB at
  most. Every peak stays under its budget, so `COUNT_PIXEL_BYTES` and `WORKER_BASE` stay.
- **The surface model** (D1): a tile's private peak the same (the extra grids are memory-mapped), its working set
  +36 % in S (median 0.85 → 1.16 GiB), all workers' private peak 4.1 → 5.4 GiB on sk-sulov.

### Measured and not taken

- **16 workers** (W2): the S band's wall the same to the second, 11 % more CPU seconds, 6.3 GiB more private bytes
  at the peak: the band is short of physical cores, not of workers. No rule in `worker_count`.
- **Splitting the heaviest core** (W3): W1's tail is one tile of 4.1 minutes beside a full machine for 60, and on the
  five together one of 3.9 minutes beside a full machine for 47; C8 and C9 took 20 % off that tile alone. Not built.
- **The fused walk** (C4): `_evaluate` and `covered_pixels` folded into `_pairs`' walk of a found pair, bit for bit
  possible (shown on 55.3 M lines), saves 10-12 % of the three walks on the same pairs (about 55 s of M2's
  heaviest tile, *est.*), high effort. Not built.
- **The counter** (C5): 1.69 % of all tile seconds, 4-5 % of the heaviest; measure again with cube v2's two int64.
- **The partners' data in cell order** (C4, "L"): 1.4-5.7 % of `_pairs`' first pass, about 1 % of a heavy tile
  (*est.*). Dynamic chunks for `_pairs`: no measurable change.
- **The surface model's ratio** (D1): 1.30× the tile seconds on sk-sulov, all in step 1; for Slovakia about 1.7×
  in S, 1.3× in M and M2, 1.2× in L (*est.*, sk-sulov's ratios on W1's shares of step 1). Decided: counted in the
  recount bundle; the DMP not copied into the cache before it.

### The workers' crashes (wave 10, 2026-11-08)

A `country worker` died now and then with exit code 3221226356 (0xC0000374, a heap corruption), was started again
and counted its tile again with the same bits: 32 times in 81 550 tiles of rounds 4 and 5 (0.39 per 1000; S 0.16,
M2 1.18, L 1.28, M 0), always inside a stitch of two or four degree tiles of another CRS (the water mask 23 times,
FABDEM 9), never at a stitch of one, about 1.4-2.1 per 1000 such stitches. The cause is GDAL's
(OSGeo/gdal#15452, fixed on GDAL's master by #15451 on 2026-11-03, in no release of 3.12 or 3.13): rasterio's
`reproject(num_threads > 1)` runs `ChunkAndWarpMulti`, which starts a joinable thread per chunk, and on Windows
a thread that ends before `CreateThread` has returned frees its own record, which `CPLJoinThread` frees again. A
strip its source covers only in part is split by the warper's fill-ratio heuristic into 40-55 chunks, many without
a source pixel: 212 such threads for a stitch of two tiles of an S tile against 20 for one tile. A stress of 12
processes stitching one crashed tile's water mask and FABDEM over and over crashed 41 times in 2686 rounds (15
minutes); with `num_threads=1` and the warp option `NUM_THREADS=8` (`mosaic.WARP_KWARGS`: rasterio's
`ChunkAndWarpImage`, GDAL's kernel still on 8 threads of its pool) 0 times in 2486. The mosaics are the same bit for
bit (12 of the crashed tiles' mosaics, every variant), the 31 crashed tiles and sk-sulov's 22 count as the user's
tiles. It costs nothing: the stitches of two or four tiles got faster without a thread per chunk (water mask 0.80
→ 0.52 s and FABDEM 1.16 → 0.72 s on S's E-395000_N-1205000, 0.69 → 0.51 and 0.98 → 0.82 s on L's
E-500000_N-1200000, medians of 5, shared lock), one tile's the same (0.32 / 0.33 s); sk-sulov's stitching stages
within the spread of two runs each (`local/country-perf-2026-11-07/stage2/CRASH/`).

### Lessons

- **Two interpreters**: the main checkout's venv is Python 3.13.7, every worktree's (`uv sync --frozen`) 3.15.2. C3's
  first runs compared main on 3.13 with the branch on 3.15, which mixed the interpreter with the code (a process's
  private bytes before any stitching: 111-112 MiB on 3.13, 121-122 on 3.15); they were run again with the base in a
  detached worktree of its own (`stage2/C3/CONFOUNDED.md`). An A/B runs both sides on one interpreter.
- **CPU seconds move with the load**: the same S tiles took 4.86 CPU-h alone at 84 % and 3.93 inside the all-bands
  run at 98 %, much of the difference numba's spinning threads (W1, W4). CPU seconds compare runs of the same load.
- **A bound is not a gain**: C4 measured 189 s of single-threaded numpy around M2's heaviest tile's kernel; C9's
  blocks took 70 s off it, the rest memory-bound gathers and copies.
- **What a stage measures alone and in a band**: the stitching of one tile alone fell 0.30 → 0.18 s in S (C3), and
  0.42 → 0.22 h over the band; a tile alone on 24 threads (C4, 1012 s) is not its seconds beside eleven others
  (1826 s in round 4, 3840 s in W1).
- **Reference cycles hold memory-mapped files**: a lambda closing over the object it was stored on kept a count's
  grids mapped until the cyclic collector ran, and Windows refused to open them for writing again (281a301).
- **The contract and the code**: `--processes 16` was not refused (W2: only `worker_count`'s default stops at the
  physical cores); no complete mountain box of Poland was on Z: (13 606 of 86 446 sheets when the download stopped),
  so I1 took the Opole box.

## The terrain statistics of step 1 (2026-11-03, branch `elevation-filter`)

The viewer's percentile filters need the heights of each search area's land (docs/roadmap.md,
"Elevation filters"). `prepare_data` counts them right after the shore zone, in the Compute bar
"terrain statistics" (`hypsometry.land_histogram`): an exact histogram of 0.1 m bins over blocks
of about 1 Mpx of rows, within a tile's core only, summed over the tiles. The anchors' band of
`--min-elevation`/`--max-elevation` in `_lines` is a mask over the anchors (milliseconds).

Measured with `tools/perf_profile.py --cores 7` under the exclusive lock on cached data, with
main's code (6d9d2c2) against the branch's (26adeea), both exported:
- four pairs on the Gozo coast with `--tile-size 5000` (6 tiles, the largest 50.2 Mpx), one of
  them with `--tracemalloc`;
- one pair of R40 (a 1 m circle of 600 m).

| | main | the branch |
| --- | ---: | ---: |
| the bar "terrain statistics", Gozo coast (6 tiles) | – | 0.3 s in every run (about 0.05 s a tile) |
| the bar, R40 | – | 0.0 s |
| step 1's wall time, Gozo coast | 39.0-41.9 s | 40.0-41.6 s |
| step 1's peak RSS, Gozo coast (the surface pair's medians of the gap filling) | 1 710-1 925 MB (mean 1 815) | 1 704-1 904 MB (mean 1 806) |
| step 1's peak of the traced heap (`--tracemalloc`) | 1 344 MB | 1 347 MB (the bar's own: 296 MB) |

- The peak RSS of identical runs varies by about ±110 MB here. The traced heap shows no array
  held past the bar, so `PIXEL_BYTES` stays 50.
- The results are byte for byte in every pair: `lines.csv`, `lines.geojson` up to its
  "findaline" part, and `data.js` and `lines.js` from their "lines". The terrain goes into
  their heads, before "lines".
- `tests/regression.py`'s sets water and search, and R56, gave every checksum unchanged.
- The viewer ranks each line's anchors once when a run is loaded: a binary search in 101
  quantiles per anchor.

## Window reads (2026-11-04, branch `window-reads`)

The layers read by windows of big remote files (`sources/readers/windows.py`: FileBlocks, the USGS blocks,
Scotland's and British Columbia's) cached about a third of what they downloaded. The estimate of the data of every
current source (docs/country-precompute.md, section 2) put the difference at about 37 of its 49.5 TB.

### How it was measured

`tools/perf_window_reads.py` downloads a layer's blocks over a circle into an empty scratch cache, each mode in a
child process (GDAL's settings must be in the environment before it starts), and counts:
- the bytes and requests of GDAL's /vsicurl/ from GDAL's network statistics (`CPL_VSIL_NETWORK_STATS_ENABLED`,
  read through ctypes from the GDAL library that rasterio carries);
- the bytes and requests of our own range requests (`ranges.get_range`);
- the seconds and the process's peak memory;
- what the files' internal tiles predict (`BLOCK_SIZE_x_y` of their headers), summed per block and each tile once.

### Why a block costs 2.35 times its tiles

A block of 1000 px over a file's tiles of 512 px touches 2.95 x 2.95 tiles on average: 2.28 times its own pixels.
GDAL reads every touched tile whole, and the next block reads the tiles it shares with this one again. The
prediction from the headers matched the measured bytes to 0.2 % (Austria: 65.7 MB predicted, 65.8 MB downloaded for
12 blocks; Canada: 111.5 / 111.6 MB).

| 12 blocks of 1 km | Downloaded | Each tile once (the file's density) | Cached | Downloaded / cached |
| --- | ---: | ---: | ---: | ---: |
| Austria (Innsbruck) | 5.5 MB/km² | 2.3 MB/km² | 1.85 MB/km² | 3.0 |
| Canada (Squamish) | 9.3 MB/km² | 3.9 MB/km² | 2.4 MB/km² | 4.0 |

The rest of the difference is the files' compression (LZW without a predictor) against the cache's (DEFLATE with
the floating-point predictor).

### What GDAL does (measured)

- **GDAL's cache of ranges** (`CPL_VSIL_CURL_CACHE_SIZE`) never serves a block that the app reads with
  `GDAL_HTTP_MULTIRANGE=YES`: a multi-range request bypasses it, and so do `PARALLEL` and the default. With 256 MB
  and one thread, a block-by-block read still downloaded 88.0 of 88.0 MB. Only `SERIAL`, each range a request of its
  own, goes through it: then 50.0 MB, equal to "each tile once" (49.8 MB).
- **A big window through /vsicurl/** is fetched exactly, tiles only and in 1-2 requests, only with
  `GDAL_NUM_THREADS` > 1 (48.01 MB for tiles of 47.99 MB). With one thread GTiff reads it tile by tile with
  read-ahead: 1.2-1.45 times the bytes and many requests.
- **With `GDAL_NUM_THREADS` > 1 an answer cut short goes unseen.** A tile range cut short once or every time
  (`tests/http_server.py`, `truncate`) left wrong values and no error in `net.gdal_errors()`; with one thread GDAL
  asked again or raised. So the app keeps one thread, and the grouped reads fetch their bytes themselves (below).
- **Through rasterio's opener** (`rasterio.abc.MultiByteRangeResourceContainer`) GTiff asks a window's tiles in
  one `get_byte_ranges` call, a range per row of tiles, only up to some size. A window of 6000 x 4000 px of
  Luxembourg's float64 went tile by tile in plain reads: 831 requests whole, 36 in strips of 512 rows, the same
  bytes. Even in strips, Canada's and the USA's files went partly tile by tile (417 and 844 requests for 72
  blocks), so each strip's tiles are now fetched beforehand from the header's offsets (`RangeFile.prefetch`, a
  request per row of tiles) and GDAL's reads served from them. A COG's tiles in a row lie a few bytes apart (each
  tile's size before it, its last bytes after it), so the ranges are merged across gaps of up to 16 KB; GDAL asks a
  row 4 bytes beyond the last tile's trailer, so each tile is prefetched with 64 bytes on either side (without
  them every row was fetched twice: Canada 382 MB instead of 274).

### C: range by range through GDAL's cache, the blocks in squares

`Windows(serial=True)`: GDAL_HTTP_MULTIRANGE SERIAL and a cache of 256 MB (`sources.net.RANGE_CACHE_BYTES`, set in
the environment when `sources.net` is imported), and `download_layers` hands the layer's blocks to its pool in
squares of 4 x 4, each square's blocks read one after another by one thread. Squares as plain tasks of the pool did
not reuse much (8 threads read neighbours at the same time: Canada -32 %, Austria -40 % at 16 blocks).

| Blocks (one circle each) | Today: MB / GET / s | C: MB / GET / s |
| --- | --- | --- |
| Austria, 36 | 199 / 39 / 12.6 | 105 / 81 / 7.2 |
| Luxembourg, 12 | 136 / 85 / 8.1 | 124 / 239 / 4.2 |
| British Columbia at Fernie (1:20 000 sheets of one-row strips), 16 | 559 / 483 / 57.7 | 236 / 132 / 28.4 |
| British Columbia at McIntyre Bluff (1:2 500 tiles), 9 | 53 / 61 / 19.4 | 48 / 50 / 23.0 |
| Wales, 16 | 55 / 27 / 2.4 | 39 / 76 / 3.4 |
| New Zealand, 16 | 51 / 17 / 9.3 | 30 / 37 / 11.1 |
| Finland (2 km blocks), 12 | 50 / 18 / 6.1 | 42 / 58 / 7.7 |
| Tasmania (2 km blocks), 9 | 85 / 14 / 10.0 | 52 / 26 / 18.3 |
| Svalbard (ArcticDEM, 2 km blocks), 16 | 26 / 19 / 5.3 | 15 / 39 / 6.9 |
| Scotland (a file per block), 12 | 176 / 72 / 4.5 | 176 / 36 / 12.0 |
| Canada, 36 | 296 / 50 / 15.0 | 149 / 88 / 23.2 |
| USA (Zion), 30 | 169 / 32 / 8.7 | 118 / 128 / 26.0 |

C saves bytes nearly everywhere but asks more requests, one after another, and where each request waits long (S3
across the ocean) it is slower. **Decided (the user, 2026-11-04): C only where it was faster too**: Austria,
Luxembourg and British Columbia (its strip sheets gain far more than its tiles lose). With 64 MB of cache instead
of 256: Austria -43 % instead of -47 %, Canada -42 % instead of -50 %. `search.DOWNLOAD_PROCESS_BYTES` holds the
cache (768 MiB).

### B: the country prefetch in groups

`download_layers(group_m=)` (`country._prefetch` with `PREFETCH_GROUP_M`): each square of group_m is one task of
the pool. `windows.read_group` opens each file once through `sources/readers/ranges.py` and reads one window over the
blocks that need it, in strips whose tiles are fetched beforehand. Every range is asked by requests and taken only whole: HTTP 206 with the
Content-Range asked and as many bytes, else asked again. The blocks are composed as `_read_block` composes each, so
the cache is the same byte for byte. Checked with `tools/cache_diff.py` against block-by-block caches of Austria,
Canada, Wales, New Zealand, Luxembourg, Scotland, British Columbia (strips; tiles with PixelIsPoint files),
Finland, Tasmania and Svalbard (the geoid), and offline in `tests/test_window_groups.py`.

#### The size of a group

A group of G px over a file's tiles of T px reads (1 + T/G)² times the file's own bytes (each tile once, the tiles at
its edges once more with the neighbouring group), against 2.28 for blocks of 1000 px over tiles of 512. The model
below takes the measured factor of today's blocks per source; its window held whole costs about 8 bytes a pixel
(the values and mask, the strip being read, the blocks' arrays), times the pool's 8 threads:

| | Today (blocks of 1 km) | 5 km | 10 km | 20 km | 50 km (a file) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Canada's lidar, both models (TB) | 29.8 | 15.2 | 13.8 | 13.2 | 12.8 |
| USA, 3DEP 1 m (TB) | 21.4 | 16.4 | 15.6 | 15.2 | 15.0 |
| ArcticDEM (TB) | 4.4 | 3.6 | 3.0 | 2.8 | 2.6 |
| New Zealand, both models (TB) | 2.1 | 1.5 | 1.3 | 1.3 | 1.2 |
| Austria, both models (TB) | 0.9 | 0.5 | 0.4 | 0.4 | 0.4 |
| The other window sources (TB) | 0.9 | 0.8 | 0.7 | 0.7 | 0.7 |
| **Together (TB)** | **59.5** | **38.0** | **35.0** | **33.6** | **32.7** |
| Requests a km² and file (tiles of 512 px) | 1 | 0.43 | 0.21 | 0.10 | 0.04 |
| Memory, 8 threads, 1 m data (the model; measured below) | ~0.3 GiB | 1.5 GiB | 6 GiB | 24 GiB | 149 GiB |

**Decided (the user, 2026-11-04): 10 km.** Groups larger than that need the blocks composed row of blocks by row of
blocks as the strips come in, so that the memory grows with G and not G² (about 0.15 GiB a thread at 20 km): a
later step worth 4-7 % of the window sources' bytes.

#### Measured (the prefetch of each strip and its padding in place)

One thread, the same 72 blocks (a circle of 3.5 km; a group of 10 km is not full there), MB / GET / seconds / peak
memory of the process:

| | Blocks | Groups of 5 km | Groups of 10 km |
| --- | --- | --- | --- |
| Canada (Squamish) | 483 / 86 / 77.8 s / 180 MB | 289 / 62 / 58.6 s / 585 MB | 274 / 54 / 52.5 s / 751 MB |
| USA (Zion) | 385 / 88 / 112.1 s / 162 MB | 282 / 158 / 77.4 s / 553 MB | 266 / 112 / 89.9 s / 1187 MB |

A thread reads a km² 1.3-1.5 times as fast in groups: fewer bytes, and one request per row of tiles instead of
one per block. With 8 threads the groups are as fast only where there are enough of them for the threads: on the
circle of 3.5 km, 1-9 squares, groups of 10 km took longer than the blocks (Canada 32.5 s, USA 55.3 s against 17.7
and 21.9 s). On a circle of 7.5 km with groups of 5 km (9-16 squares; the blocks' rate from the circle of 3.5 km):

| 8 threads | Blocks | Groups of 5 km |
| --- | --- | --- |
| Canada | 9.6 MB/km², 244 blocks a minute | 5.1 MB/km², 380 blocks a minute, 2.1 GB peak |
| USA | 5.4 MB/km², 197 blocks a minute | 3.7 MB/km², 253 blocks a minute, 2.4 GB peak |
| Austria | 5.5 MB/km², 190 blocks a minute (C: 2.8 MB/km², 325) | 3.0 MB/km², 660 blocks a minute, 0.8 GB peak |

A country holds thousands of groups, so its threads stay busy and a group of 10 km reads as fast per thread as its
measurement on one thread. One full group of 10 km (Canada, a circle of 10 km on one thread, 484 blocks: 1311 MB,
4.85 MB/km², 192 GET, 233 s (193 s in a second run), 124-150 blocks a minute) peaked at 1.84 GB: 17 bytes a pixel,
not the model's 8. The window and its mask (5 B), the blocks being composed (4 B), every block's slice held until the
window was done (4 B) and GDAL's block cache holding the window's decoded tiles while its file is open (4 B; one
cache for the process, at most `GDAL_CACHEMAX`, 5 % of the memory: 3.1 GB on this PC). The slices are now applied one
by one (`_group_values` yields them): 1.50 GB, the same 1311 MB in 192 requests. Eight threads at 10 km: 8 times
about 0.9 GB and GDAL's cache, about 10.5 GB, well within the 45-50 GB of either machine (docs/country-precompute.md,
4.1); the prefetch runs before the country's workers start.

## Loading a run in the browser (2026-11-04, branch `run-loading-progress`)

A large run opened with no feedback: the result page said "Loading the run…" while data.js came in as a
`<script>` (no progress events), then froze while the model was built; the 3D view showed one spinner from the
request to the mesh. `tools/perf_run_load.py` measured where the time goes, before any change, on the five runs
below (the local app on a scratch data folder, headless Chromium 156, three rounds per run in fresh profiles,
medians; the downloads over loopback, so the gzipped size of each data.js, as nginx sends it at level 5, gives the
time on a real line). The page's phases are User Timing measures (`viewer/src/perf.ts`, "fal:run:*", "fal:3d:*").

| Run | Lines | data.js / gzip MB | gzip at 10 / 50 Mbit/s (s) | script: download and parse (s) | toLine | group | result shown | longest task | JS heap MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gozo-brzeg-2 (2026-10-25) | 695 142 | 115 / 28.6 | 24.0 / 4.8 | 1.03 | 0.05 | 0.60 | 2.16 | 0.90 | 595 |
| coast-100-m within Gozo (2026-10-28) | 403 026 | 90.5 / 24.7 | 20.7 / 4.1 | 0.84 | 0.03 | 0.26 | 1.49 | 0.51 | 441 |
| Bełchatów | 338 694 | 51.8 / 11.2 | 9.4 / 1.9 | 0.46 | 0.02 | 0.19 | 1.00 | 0.34 | 242 |
| Schneewigi | 187 987 | 40.3 / 10.4 | 8.7 / 1.8 | 0.35 | 0.02 | 0.13 | 0.92 | 0.28 | 202 |
| Ta' Għammar | 3 241 | 5.6 / 0.5 | 0.5 / 0.1 | 0.09 | 0.00 | 0.00 | 0.32 | 0.06 | 30 |

- The download is the cost on a real line: 24 s for the largest run at 10 Mbit/s with nothing on the screen. The
  work after it is short on a desktop (0.7 s, most of it the grouping; the longest task 0.9 s): no Web Worker now.
- fetch + JSON.parse of data.js from the HTTP cache took 0.68 s where the script took 0.98 s (0.53 / 0.76 s,
  0.28 / 0.41 s for the next two runs), and JSON.parse read all five files (no NaN or Infinity in them).

The 3D view of each run's first line (seconds; the server's part is the patch's request until its first byte):

| Run | Level | Server | Patch MB | Mesh | Profile | Imagery (tiles) | Terrain and profile ready |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Bełchatów | full | 0.89 | 1.50 | 0.38 | 2.25 | 10.29 (260) | 3.78 |
| Schneewigi | full | 2.43 | 3.85 | 1.63 | 1.02 | 4.97 (310) | 5.38 |
| Ta' Għammar | full | 1.10 | 0.18 | 0.40 | 4.14 | 1.36 (111) | 5.86 |
| Gozo, two runs | full | 0.78-1.43 | 0.16 | 0.35 | 0.72-1.06 | 1.66-2.37 (129) | 2.3-2.7 |
| all five | phone | 0.77-1.54 | 0.06-1.24 | 0.09-0.26 | 0.34-0.90 | 0.6-4.3 (64-96) | 1.4-2.9 |

The imagery is the longest stage, then the server's patch (the profile waits for it: the quick lane takes one task
at a time); the mesh blocks the page up to 1.6 s. Not measured: phones.

The VPS, read from the monitoring on 2026-11-05 (VictoriaMetrics, nginx's metrics log; a 30 s window holds about one
request at this traffic, so the windows' medians are about the requests): 6 patches, all answered, all within the last
day, of 242 kB on average.

| `/api/patch` on the VPS (s) | Median | 90 % | Largest | Mean |
| --- | ---: | ---: | ---: | ---: |
| The app's answer (`upstream_time`: the quick lane's queue and step 1) | 1.69 | 7.71 | 11.45 | |
| The whole request (`request_time`) | 1.69 | 7.74 | 11.45 | 3.62 |

Nearly all of it is the server's: the stage "server" can last 11 s there, and sending the answer about 0.03 s. Six
requests say little, so the moving bar stays and no estimate of the time was added. data.js cannot be told apart: it
falls in the group "app" with the bundles, whose windows reached 21 s at their 99th percentile (of 392 requests); that
fits a large run's download but does not show it.

### What was done

- The result: data.js is downloaded over http(s) by XMLHttpRequest (`viewer/src/download.ts`: a fetch's streamed
  body left headless Edge's tests without the run) and its bytes counted against `X-Findaline-Bytes` (`web.SIZE_HEADER`,
  set by `web.RunFiles`: nginx's gzip drops Content-Length), then read by JSON.parse; a file JSON.parse refuses is
  loaded as a script from the HTTP cache (`viewer/src/result/load.ts`). The page names the phase with a bar
  (`result/view/RunLoading.tsx`: downloading x of y MB, reading the lines, grouping them), the model built after a
  paint (`model.ts buildModel`, `paint.ts nextPaint`). A run's map.html loads data.js through the viewer
  (`map/main.tsx`), so served maps and share links get the bar; from disk the script, with the phases only.
- The 3D view: the status names the stage with a bar (the server, the download x of y MB, unpacking, building the
  mesh: `view3d/main.ts`, the root's `data-stage`), and the imagery counts its tiles.
- Not done (the user's choice): storing the data in the browser; the HTTP cache keeps data.js (ETag, 304).

### After the change (the same five runs, `tools/perf_run_load.py`)

Measured from the request of data.js to the result shown (the medians of "shown" moved with the app's own start in
a fresh profile, up to 0.7 s from round to round), and the main thread's long tasks from that request on:

| Run | Request to result shown (s) | Main thread blocked (s) | Longest task (s) |
| --- | ---: | ---: | ---: |
| gozo-brzeg-2 | 2.02 -> 1.76 | 0.90 -> 1.25 | 0.90 -> 0.91 |
| coast-100-m within Gozo | 1.39 -> 1.23 | 0.51 -> 0.81 | 0.51 -> 0.52 |
| Bełchatów | 0.89 -> 0.89 | 0.34 -> 0.52 | 0.34 -> 0.38 |
| Schneewigi | 0.82 -> 0.65 | 0.28 -> 0.39 | 0.28 -> 0.24 |
| Ta' Għammar | 0.21 -> 0.17 | 0.06 -> 0.00 | 0.06 -> 0.00 |

The result shows as soon or up to 0.26 s sooner. The main thread is blocked up to 0.35 s longer in all: Chromium
parsed the script on a background thread, while JSON.parse runs on the main thread (0.35 s for 115 MB). That time is
a task of its own with "Reading the lines…" painted before it, and the longest task (the grouping) stayed as it was.
The 3D view's stages took the same time as before (the server 0.7-2.0 s, the mesh up to 1.3 s).

## The resampling of a neighbour's data (2026-11-05, tag `history/partner-resampling`)

Step 0 of the cube v2 contract (docs/country-precompute/contract.md, section 6). At a border a grid
holds the neighbour's data reprojected onto it (`sources.filling.fill_from_neighbours`), and a line
across the border is tested on them. `sources.mosaic._place` reprojects by the **average** where the
data are finer than 0.75 of the grid's resolution and **bilinearly** otherwise. The question: which
method gives what the neighbour's own grid gives.

### How it was measured

`tools/border_study.py run <place> --primary <source> --resampling <method>` counts the layer's S band
(1 m) and M band (2 m) over a box across a border on one source's grid, the other side's data from the
neighbour fill reprojected by the method (`filling.NEIGHBOUR_RESAMPLING`, `mosaic.RESAMPLINGS`; "own"
is the run without a method, the code of `main` 5c8261e, before the decisions at the end of this
section). The reference of a run is the run on the other
source's grid. The measure is the class **side**: the lines with both anchors on the neighbour's
side, which the run finds on the reprojected data and the reference on the data themselves. A spot
(a pair of 50 m anchor clusters) is found when the other run has one within 1 cluster at both ends
after reprojection, both ends in the box less 100 m (`band_study.matched`); many spots may match
one, so the number of spots is given beside the shares. The places: the Tatras (Poland and
Slovakia, both 1 m, the grids turned by 4.4 degrees), the Wetterstein (Bavaria and Austria, both
1 m, hardly turned, shifted), the Elbe Sandstone (Saxony's 1 m data on Czechia's 2 m grid) and, for
a neighbour coarser than the grid, the Zillertal ridge (South Tyrol's 2.5 m data on Austria's grid).

What limits the reading:
- **A part of the neighbour's side lies on the run's own data**, which reach beyond the border: 14.4 %
  of the Polish side on Slovakia's grid, 3.9 % of the Slovak side on Poland's, 6.0 % of the Austrian
  side on Bavaria's, 1.9 % of the Bavarian side on Austria's, 3.1 % of the Saxon side on Czechia's
  (the tiles' `fill`). Those pixels are the same for every method and lie along the border, on a
  ridge the richest strip: the methods' differences are understated there, never reversed, and where
  the two sources differ the run may find more than the reference (Bavaria's data find 1.4 times the
  lines of Austria's across the Wetterstein's border in the S band).
- **The runs shared the PC** (the shared test lock: 8 threads, below the normal priority, other
  sessions' tests beside them), so the seconds are not comparable between the columns: two runs of
  about the same CPU seconds (6 766 and 6 311) took 1 096 s and 2 323 s. The CPU seconds measure the work (they too rise by some percent
  when the cores are shared). The first run of a place holds its downloads (the Elbe's "own").
- Memory as in "Round 4": "private" is what the process reserved (Windows' commit), "working set"
  what it holds in RAM with the pages of the memory-mapped grids; the peak over a band's tiles,
  counted one after another in one process.
- The Elbe the other way gave nothing: Czechia's rough boxes (`CZ_OFFLINE`) end south of Hřensko, so
  the neighbour fill never asked Czechia and the Saxon grid's Czech side is the 30 m fallback (93.7 %
  of its pixels). Its "across" rows have no reference for the same reason. (Since 2026-11-06 Czechia
  has border boxes, `Source.border_boxes`, and the Saxon grid gets its data there; these runs are of
  before.)

### Step by step: the same resolution (the S band, 1 m data on a 1 m grid)

The mosaic's own choice is bilinear here.

| Tatras, S band: Poland's 1 m data on Slovakia's 1 m grid | Reference (its own grid) | own (bilinear) | average | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 128 660 | 90 798 (70.6 %) | 93 702 (72.8 %) | 111 030 (86.3 %) | 138 922 (108.0 %) |
| Their spots | 2 482 | 1 716 (69.1 %) | 1 775 (71.5 %) | 2 068 (83.3 %) | 2 690 (108.4 %) |
| Reference's spots the run has |  | 92.5 % | 93.7 % | 96.1 % | 98.8 % |
| Run's spots the reference has |  | 97.9 % | 98.0 % | 98.0 % | 97.3 % |
| Lines across the border | 599 | 637 | 637 | 637 | 637 |
| Their spots | 25 | 38 | 38 | 38 | 38 |
| Across: reference's the run has / run's the reference has |  | 92.0 % / 76.3 % | 92.0 % / 76.3 % | 92.0 % / 76.3 % | 92.0 % / 76.3 % |
| Seconds of the tiles (shared lock) / of them step 1 | 242 / 128 | 147 / 66 | 124 / 57 | 309 / 131 | 127 / 58 |
| CPU seconds / of them step 1 | 326 / 137 | 272 / 76 | 253 / 70 | 333 / 88 | 254 / 69 |
| Peak private / working set, GiB | 1.81 / 1.67 | 1.78 / 1.62 | 1.77 / 1.62 | 1.77 / 1.62 | 1.78 / 1.62 |

| Tatras, S band: Slovakia's 1 m data on Poland's 1 m grid | Reference (its own grid) | own (bilinear) | cubic | nearest |
| --- | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 530 215 | 306 397 (57.8 %) | 393 951 (74.3 %) | 530 468 (100.0 %) |
| Their spots | 8 759 | 4 966 (56.7 %) | 6 549 (74.8 %) | 9 803 (111.9 %) |
| Reference's spots the run has |  | 88.8 % | 94.1 % | 98.3 % |
| Run's spots the reference has |  | 99.6 % | 99.3 % | 97.9 % |
| Lines across the border | 637 | 599 | 599 | 599 |
| Their spots | 38 | 25 | 25 | 25 |
| Across: reference's the run has / run's the reference has |  | 76.3 % / 92.0 % | 76.3 % / 92.0 % | 76.3 % / 92.0 % |
| Seconds of the tiles (shared lock) / of them step 1 | 147 / 66 | 242 / 128 | 155 / 91 | 144 / 85 |
| CPU seconds / of them step 1 | 272 / 76 | 326 / 137 | 285 / 114 | 260 / 93 |
| Peak private / working set, GiB | 1.78 / 1.62 | 1.81 / 1.67 | 1.82 / 1.67 | 1.84 / 1.68 |

| Wetterstein, S band: Bavaria's 1 m data on Austria's 1 m grid | Reference (its own grid) | own (bilinear) | cubic | nearest |
| --- | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 1 603 003 | 1 194 327 (74.5 %) | 1 399 201 (87.3 %) | 1 543 037 (96.3 %) |
| Their spots | 12 962 | 8 700 (67.1 %) | 10 682 (82.4 %) | 12 772 (98.5 %) |
| Reference's spots the run has |  | 96.1 % | 98.2 % | 99.4 % |
| Run's spots the reference has |  | 100.0 % | 99.9 % | 99.8 % |
| Lines across the border | 9 682 | 6 993 | 7 351 | 7 776 |
| Their spots | 182 | 82 | 84 | 86 |
| Across: reference's the run has / run's the reference has |  | 69.2 % / 100.0 % | 69.2 % / 100.0 % | 69.2 % / 100.0 % |
| Seconds of the tiles (shared lock) / of them step 1 | 118 / 55 | 217 / 122 | 100 / 45 | 111 / 52 |
| CPU seconds / of them step 1 | 268 / 70 | 332 / 116 | 231 / 59 | 249 / 65 |
| Peak private / working set, GiB | 1.83 / 1.68 | 1.87 / 1.69 | 1.60 / 1.42 | 1.60 / 1.42 |

| Wetterstein, S band: Austria's 1 m data on Bavaria's 1 m grid | Reference (its own grid) | own (bilinear) | average | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 158 838 | 177 160 (111.5 %) | 177 184 (111.6 %) | 189 237 (119.1 %) | 195 468 (123.1 %) |
| Their spots | 2 003 | 2 655 (132.6 %) | 2 656 (132.6 %) | 2 827 (141.1 %) | 3 016 (150.6 %) |
| Reference's spots the run has |  | 97.2 % | 97.2 % | 98.9 % | 99.5 % |
| Run's spots the reference has |  | 90.5 % | 90.5 % | 90.9 % | 90.6 % |
| Lines across the border | 6 993 | 9 682 | 9 682 | 9 683 | 9 682 |
| Their spots | 82 | 182 | 182 | 183 | 182 |
| Across: reference's the run has / run's the reference has |  | 100.0 % / 69.2 % | 100.0 % / 69.2 % | 100.0 % / 69.4 % | 100.0 % / 69.2 % |
| Seconds of the tiles (shared lock) / of them step 1 | 217 / 122 | 118 / 55 | 312 / 108 | 138 / 59 | 133 / 59 |
| CPU seconds / of them step 1 | 332 / 116 | 268 / 70 | 329 / 82 | 279 / 76 | 280 / 70 |
| Peak private / working set, GiB | 1.87 / 1.69 | 1.83 / 1.68 | 1.83 / 1.68 | 1.83 / 1.68 | 1.83 / 1.68 |

Where the run's own data do not hide it, bilinear loses 25-42 % of the neighbour's lines and 31-43 %
of its spots, and 4-11 % of the reference's spots have no match; cubic recovers about half;
**nearest finds 96-108 % of the lines and 98.3-99.5 % of the reference's spots**, with at most 1.7
points fewer of its own spots present in the reference than bilinear's. It is the half-pixel pitfall of CLAUDE.md again: at the same resolution a bilinear
reprojection is a smoothing of every cliff edge. The lines across the border are the same for every
method, but for one line, in three of the four directions (the run's own data reach farther beyond the border than the
band's longest line, 300 m); on Austria's grid, whose data stop sooner, they rise from 6 993 to
7 776 with nearest, towards the 9 682 of Bavaria's grid.

### Step by step: finer data (the M band, 1 m data on a 2 m grid)

The mosaic's own choice is the average here.

| Tatras, M band: Poland's 1 m data on Slovakia's 2 m grid | Reference (its own grid) | own (average) | bilinear | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 74 004 281 | 73 543 167 (99.4 %) | 74 185 082 (100.2 %) | 74 371 453 (100.5 %) | 71 023 975 (96.0 %) |
| Their spots | 63 480 | 62 520 (98.5 %) | 60 509 (95.3 %) | 64 686 (101.9 %) | 70 097 (110.4 %) |
| Reference's spots the run has |  | 99.7 % | 99.6 % | 99.8 % | 99.9 % |
| Run's spots the reference has |  | 99.9 % | 99.9 % | 99.8 % | 99.5 % |
| Lines across the border | 251 392 | 251 900 | 251 829 | 251 985 | 252 048 |
| Their spots | 1 309 | 1 561 | 1 554 | 1 572 | 1 586 |
| Across: reference's the run has / run's the reference has |  | 97.9 % / 89.3 % | 97.9 % / 89.4 % | 97.9 % / 89.2 % | 97.9 % / 88.9 % |
| Seconds of the tiles (shared lock) / of them step 1 | 1383 / 60 | 1096 / 25 | 2323 / 39 | 2178 / 40 | 1534 / 22 |
| CPU seconds / of them step 1 | 6280 / 60 | 6766 / 34 | 6311 / 37 | 6527 / 38 | 6774 / 30 |
| Peak private / working set, GiB | 1.46 / 1.21 | 1.62 / 1.40 | 1.61 / 1.39 | 1.62 / 1.40 | 1.58 / 1.36 |

| Wetterstein, M band: Austria's 1 m data on Bavaria's 2 m grid | Reference (its own grid) | own (average) | bilinear | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 43 764 512 | 43 551 595 (99.5 %) | 44 074 390 (100.7 %) | 43 349 198 (99.1 %) | 42 401 207 (96.9 %) |
| Their spots | 24 809 | 24 986 (100.7 %) | 24 089 (97.1 %) | 25 817 (104.1 %) | 27 221 (109.7 %) |
| Reference's spots the run has |  | 99.6 % | 99.3 % | 99.7 % | 99.8 % |
| Run's spots the reference has |  | 99.8 % | 99.9 % | 99.6 % | 99.0 % |
| Lines across the border | 890 616 | 883 518 | 885 228 | 886 231 | 889 104 |
| Their spots | 2 114 | 2 240 | 2 233 | 2 248 | 2 272 |
| Across: reference's the run has / run's the reference has |  | 99.1 % / 97.0 % | 99.1 % / 97.0 % | 99.1 % / 97.0 % | 99.2 % / 97.1 % |
| Seconds of the tiles (shared lock) / of them step 1 | 945 / 48 | 871 / 29 | 1984 / 80 | 1836 / 57 | 1489 / 46 |
| CPU seconds / of them step 1 | 5448 / 62 | 5188 / 50 | 4802 / 56 | 5038 / 60 | 5247 / 50 |
| Peak private / working set, GiB | 1.73 / 1.48 | 1.62 / 1.41 | 1.61 / 1.39 | 1.63 / 1.40 | 1.64 / 1.41 |

| Elbe, M band: Saxony's 1 m data on Czechia's 2 m grid | Reference (its own grid) | own (average) | bilinear | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 13 525 515 | 14 039 352 (103.8 %) | 14 537 229 (107.5 %) | 14 102 367 (104.3 %) | 12 608 663 (93.2 %) |
| Their spots | 29 315 | 27 495 (93.8 %) | 26 499 (90.4 %) | 28 716 (98.0 %) | 32 155 (109.7 %) |
| Reference's spots the run has |  | 99.2 % | 98.6 % | 99.3 % | 99.7 % |
| Run's spots the reference has |  | 99.7 % | 99.8 % | 99.5 % | 98.4 % |
| Lines across the border | 1 817 323 | 2 520 291 | 2 554 296 | 2 518 302 | 2 330 837 |
| Their spots | 5 293 | 5 567 | 5 481 | 5 653 | 5 842 |
| Across: reference's the run has / run's the reference has |  | 97.7 % / 87.0 % | 97.7 % / 86.8 % | 97.8 % / 86.8 % | 98.0 % / 86.6 % |
| Seconds of the tiles (shared lock) / of them step 1 | 81 / 17 | 290 / 133 | 196 / 57 | 191 / 46 | 145 / 46 |
| CPU seconds / of them step 1 | 321 / 19 | 616 / 95 | 588 / 55 | 583 / 55 | 556 / 49 |
| Peak private / working set, GiB | 1.02 / 0.75 | 1.33 / 1.15 | 1.33 / 1.13 | 1.16 / 0.96 | 1.15 / 0.94 |

Every method keeps 98.6-99.9 % of the reference's spots and 98.4-99.9 % the other way; the own
choice (the average) is within 0.5 points of the best in both columns at the three places. Nearest
gives 10 % more spots than the reference with the lowest share present in it (a point sample of
finer data aliases), bilinear the fewest spots. The lines across the border differ by under 1 %
between the methods in the Tatras and the Wetterstein (9 % on the Elbe, where they have no
reference), and their spots' shares by at most 0.5 points: the difference between the two grids
measured before (2-11 % of the spots across) does not come from the method. No method costs more:
the CPU seconds stay within about 10 % (they follow the number of lines), step 1 within the noise of the
shared PC, the memory within 0.2 GiB.

### Step by step: a neighbour coarser than the grid (the Zillertal ridge)

South Tyrol's 2.5 m data on Austria's grid (the user's order of 2026-11-05: "we have such cases in the
data"), the box 46.95-47.04 N, 11.70-11.92 E across the main ridge. The reference is South Tyrol's
own grid, which holds its 2.5 m data reprojected bilinearly onto the band's resolution: what a layer
of South Tyrol would count. 1.3 % of the South Tyrol side lies on Austria's own data. The mosaic's
own choice is bilinear in both bands (the data are not finer than 0.75 of the grid).

| Zillertal, M band: South Tyrol's 2.5 m data on Austria's 2 m grid | Reference (its own grid) | own (bilinear) | average | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 37 708 860 | 37 369 244 (99.1 %) | 38 625 467 (102.4 %) | 39 045 005 (103.5 %) | 63 191 086 (167.6 %) |
| Their spots | 20 097 | 20 999 (104.5 %) | 25 472 (126.7 %) | 22 905 (114.0 %) | 49 898 (248.3 %) |
| Reference's spots the run has |  | 99.7 % | 99.7 % | 99.9 % | 99.9 % |
| Run's spots the reference has |  | 98.6 % | 96.4 % | 97.8 % | 86.6 % |
| Lines across the border | 33 437 | 97 790 | 98 699 | 99 616 | 117 877 |
| Their spots | 105 | 652 | 687 | 666 | 823 |
| Across: reference's the run has / run's the reference has |  | 100.0 % / 36.7 % | 100.0 % / 35.2 % | 100.0 % / 36.0 % | 100.0 % / 35.8 % |
| Seconds of the tiles (shared lock) / of them step 1 | 234 / 27 | 266 / 35 | 237 / 24 | 266 / 48 | 294 / 25 |
| CPU seconds / of them step 1 | 1378 / 35 | 1530 / 40 | 1421 / 30 | 1455 / 33 | 1808 / 35 |
| Peak private / working set, GiB | 1.77 / 1.57 | 1.66 / 1.51 | 1.65 / 1.50 | 1.65 / 1.50 | 1.69 / 1.53 |

| Zillertal, S band: South Tyrol's 2.5 m data on Austria's 1 m grid | Reference (its own grid) | own (bilinear) | average | cubic | nearest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 28 | 33 | 15 044 | 64 | 73 867 |
| Their spots | 2 | 4 | 314 | 4 | 846 |
| Lines across the border | 0 | 1 | 3 | 1 | 7 |
| Seconds of the tiles (shared lock) / of them step 1 | 172 / 116 | 116 / 70 | 99 / 54 | 99 / 56 | 105 / 57 |
| CPU seconds / of them step 1 | 188 / 92 | 170 / 75 | 160 / 62 | 156 / 65 | 173 / 60 |
| Peak private / working set, GiB | 1.89 / 1.75 | 1.57 / 1.42 | 1.57 / 1.42 | 1.57 / 1.42 | 1.57 / 1.42 |

For coarser data **nearest is wrong and bilinear right**. A coarse pixel copied onto several fine ones
is a staircase: every step between two coarse pixels becomes a wall one fine pixel wide. On the 1 m
grid, where 2.5 m data hold next to no line of 30-300 m (28 on their own grid), nearest makes 73 867
and the average 15 044 (for coarser data the average too copies the pixels it touches); on the 2 m
grid nearest gives 1.7 times the lines and 2.5 times the spots, 13 % of them without a match.
Bilinear follows the reference in both bands (99.1 % of the lines, 99.7 % of its spots found, 98.6 %
of the run's present in it), cubic a little less closely. The lines across the border are three
times those of South Tyrol's grid under every method (97 790 to 99 616 against 33 437; nearest
117 877): Austria's side of the ridge is 1 m data on Austria's grid, while 16 % of it is South
Tyrol's 2.5 m data on South Tyrol's grid, another case of the two grids' data, not of the method.
So nearest applies only at the grid's own resolution: `mosaic.SAME` is 1.1, between the measured
1.0 (nearest right) and 1.25 (nearest wrong).

### Slovakia's averaged tiles on a grid of another CRS

Slovakia's side on Poland's 2 m grid lost more than any other M case (87.7 % of the spots). The
reason is not the method: `GridResolutions.resolution` gives a grid of exactly 2 m (or 5 m) the tiles
averaged to that resolution whatever the grid's CRS, so Poland's grid got the 2 m tiles reprojected
bilinearly (the same resolution): averaged, then smoothed. With the 1 m tiles forced (a run of
`local/partner-resampling-2026-11-05/scripts/run_native_neighbour.py`, which patches that method)
the mosaic averages them onto the grid as it does every other 1 m source:

| Tatras, M band: Slovakia's data on Poland's 2 m grid | Reference (its own grid) | own (bilinear of the 2 m tiles) | average of the 1 m tiles |
| --- | ---: | ---: | ---: |
| Lines, both anchors on the neighbour's side | 343 179 313 | 308 265 987 (89.8 %) | 302 836 611 (88.2 %) |
| Their spots | 206 074 | 180 663 (87.7 %) | 197 183 (95.7 %) |
| Reference's spots the run has |  | 99.3 % | 99.7 % |
| Run's spots the reference has |  | 100.0 % | 99.9 % |
| Lines across the border | 251 900 | 251 392 | 250 946 |
| Their spots | 1 561 | 1 310 | 1 318 |
| Across: reference's the run has / run's the reference has |  | 89.2 % / 97.9 % | 89.2 % / 98.0 % |
| Seconds of the tiles (shared lock) / of them step 1 | 1096 / 25 | 1383 / 60 | 1559 / 49 |
| CPU seconds / of them step 1 | 6766 / 34 | 6280 / 60 | 5876 / 56 |
| Peak private / working set, GiB | 1.62 / 1.40 | 1.46 / 1.21 | 1.44 / 1.19 |

The spots return to 95.7 % of the reference's and the found share to 99.7 %; the lines stay at 88-90 %
(probably the two grids' pixels: the reference's 2 m pixels are the aligned block means, the run's the
average over a turned pixel; the number of lines of a band with 300 M of them over 200 k spots
follows the anchors per wall, not the spots). Done on the user's word (2026-11-05):
`GridResolutions.resolution` gives the averaged tiles only to a grid of the tiles' CRS (the country
layer's own bands); R13 of the regression set, a 5 m search in Poland with its Slovak side filled, is
back at its anchors of before the averaged tiles (2 804).

### What was decided and built (the user, 2026-11-05; contract, section 6, step 0)

- Finer data (the M and L bands against 1 m sources): the average stays.
- The grid's own resolution (the S band against a 1 m neighbour; `mosaic.FINER` 0.75 to `mosaic.SAME`
  1.1 of it): nearest instead of bilinear, `filling.NEIGHBOUR_SAME_RESOLUTION`, for a neighbour's
  rasters in every search. R34 of the regression set (Mięguszowieckie Szczyty at 1 m, its Slovak side
  from the neighbour) gained 162 anchors and 3 spots; no other test of the set changed.
- A neighbour coarser than the grid: bilinear stays (the Zillertal ridge above).
- Native anchors for the partner's side (the contract's next step) are not needed: with nearest at
  the grid's resolution, the average for finer data and bilinear for coarser data the reference's
  spots are found to 98.3-99.7 %.

## The no-fall zone and the A-frames (2026-11-06/07, branch `end-zone`)

The rule (docs/roadmap.md, "Done: the no-fall zone at the ends and the A-frames"): a pixel passes when its
strict margin `limit − terrain` exceeds `−lift − δ·[in the zone]`, the zone `min(end_zone, L/4)` from each
anchor, `δ` the fall allowance. The limit's arithmetic is untouched; the kernels get the comparison and the ring
screen per-ring offsets (`linesearch.ring_offsets`: a ring k relaxed by δ where `(k−1)·res < end_zone`, every
ring less the lift). At 0/0 the comparison subtracts exact zeros.

### What the options cost (wave 0, `tools/end_zone_study.py`, shared slot: indicative)

Captured calls of `find_valid_lines` (the Żabi Koń clip and the user's quarry lake, 49.80640, 19.57644,
r 300 m, 1 m, formula, lines 30-1000 m, `--nmpt mark`, 8 threads), every (zone, lift) of 0/5/10/20 m × 0/1/2 m
run through the production kernels (wave 1; the study's numbers equal wave 0's prototype):

| Place, anchors | Setting | Open anchors | Candidates | Checked | Lines (spots) | Step 3 wall / CPU s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Żabi Koń 45°, 39 050 | today | 1 493 (3.8 %) | 129 046 | 26 672 | 1 664 (66) | 0.02 / 0.12 |
| | lift 2 m | | | | 10 059 (199) | 0.04 |
| | zone 5 m | | | | 146 484 (340) | 0.39 / 3.0 |
| | zone 5 m, lift 2 m | | | | 664 391 (671) | 1.05 / 8.3 |
| | zone 10 m | | | | 434 346 (602) | 1.0 |
| | zone 20 m, lift 2 m | 39 045 (100 %) | 101 084 809 | 27 373 059 | 2 566 835 (1 275) | 2.5 / 19.8 |
| Żabi Koń 35°, 130 618 | today | 1 504 (1.2 %) | 129 871 | 26 795 | 1 680 (66) | 0.03 / 0.25 |
| | zone 20 m, lift 2 m | 130 599 (100 %) | 717 848 402 | 150 787 964 | 11 725 800 (2 267) | 12.5 / 99.5 |
| Quarry 45°, 5 039 | today | 9 (0.2 %) | 5 | 0 | 0 | 0.00 |
| | zone 5 m | | | | 992 (8); 206 of 250 m+ | |
| | zone 5 m, lift 2 m | | | | 11 849 (22); 3 321 of 250 m+ | |
| | zone 20 m, lift 2 m | 5 039 (100 %) | 1 477 114 | 583 547 | 62 991 (55) | 0.10 / 0.83 |

- The ring screen decides nothing once the zone reaches the first rings of a 1 m grid: every anchor becomes
  open (3.8 % → 100 %), the candidates grow ×780 and the checked pairs ×1 000 at Żabi Koń; the kernel's time
  ×15 at zone 5 m and ×125 at 20 m / 2 m, in a search whose step 3 takes a hundredth of its seconds today.
  The lines grow ×88 (zone 5 m) to ×1 540 (20 m / 2 m): the lines, not the kernel, are the cost of a large
  search with the options (the public site's `lines_max` and the memory budget refuse it sooner), and the
  reason the public limits are 5 m and 2 m.
- A-frames alone (2 m, no zone) give ×6 at Żabi Koń and nothing at the quarry: there every line needs the
  zone (the first strict failure lies 1 m from an anchor with a deficit of 4-5.6 m).
- The plan's estimate before the measurement (step 3 ×1.05 best, ×10-30 worst) was far too low for the
  kernel at 20 m and said nothing about the lines; the measured numbers replaced it before wave 1.
- Memory per line (`search.LINE_BYTES` 450 B, measured 389 B): with the options two float64 columns per line
  (`lift_needed`, `lift_no_zone`, +16 B) are held through steps 4-5, and the bucket minima (`zone_margins`,
  2 or 3 float64 columns, +16-24 B) through step 3's join until they are dropped right after
  `find_valid_lines`; within the margin, not measured again.

### At the defaults (exclusive, `tools/perf_profile.py --cores 7`, cached data)

main's code (41377c2) against the branch's (c9b4cae), both exported, each search once per code to warm numba's
cache and then three pairs in turn, main and the branch: the Gozo coast (`--area coast --buffer 100 --within
osm:Gozo --slope-threshold 60 --tile-size 5000`, 6 tiles), R22 (El Capitan, 1 m, 400 m) and R40 (Preikestolen,
1 m, 600 m). The results are byte for byte main's (the regression set: 63 ok, R17 skipped for Overpass).

| Search | Value | main | the branch |
| --- | --- | ---: | ---: |
| Gozo coast (6 tiles, 126 Mpx) | step 3 wall s (free directions / pairs / checking) | 2.0 (0.5 / 1.0 / 0.3) | 2.0-2.1 (0.5 / 1.0 / 0.3-0.4) |
| | step 3 CPU s | 13.5-14.2 | 14.0-14.6 |
| | the whole search, wall s | 42.6-43.8 | 42.7-42.9 |
| | the whole search, CPU s | 67.3-69.2 | 67.5-68.5 |
| | peak RSS, MB | 2 851-2 860 | 2 851-2 866 |
| R22 (18 990 lines) | step 3 wall s / CPU s | 0.2 / 1.8-1.9 | 0.2-0.3 / 1.9-2.1 |
| | the whole search, wall s / CPU s | 3.0-3.1 / 5.7-5.9 | 3.1 / 5.6-5.9 |
| | peak RSS, MB | 262-275 | 266-298 |
| R40 (125 032 lines) | step 3 wall s / CPU s | 0.4 / 3.3-3.4 | 0.4-0.5 / 3.2-3.4 |
| | the whole search, wall s / CPU s | 4.8-4.9 / 7.3-7.7 | 4.9-5.0 / 7.5-7.7 |
| | peak RSS, MB | 297-312 | 309-314 |

Nothing measurable: step 3 of the Gozo coast at 2.0 s on both, its CPU seconds 0.5 s apart (the three pairs of
each overlap), the whole searches within their own runs' spread; the `lines.csv` of the eight runs of each search
have one checksum. The kernels' new arguments (scalars and an offsets array of 64 floats) cost nothing seen.

### The country layer (exclusive, `findaline.py country run`, 12 workers)

sk-sulov (the band study's 12 km square of the Súľov rocks and the Manín gorge, 144 km², the surface model
marking lines over trees) counted on the layer's bands S1m60 (1 m, formula, 60°, cores of 5 km), M2m60 (2 m, sag,
60°), L1-5m45 and L2-5m45 (5 m, sag, 45°), as it is and as `sk-sulov-ends` with `end_zone` 5 and `anchor_lift` 2
in its `options` (`country.form_params` passes them to every band's search), the same code and day, one run after
the other:

| Band (tiles) | Lines: as is → with 5 m / 2 m | Spots | Tile seconds (median a tile) | CPU s (seconds × mean cores) | Private bytes of a tile, max |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1m60 (10) | 44 215 → 7 330 820 (×166) | 759 → 6 845 (×9.0) | 83 → 113 (8.0 → 11.4) | 101 → 180 | 0.59 → 0.62 GiB |
| M2m60 (4) | 3 734 998 → 10 366 250 (×2.8) | 9 307 → 14 318 (×1.5) | 43 → 66 (7.8 → 11.5) | 120 → 212 | 0.38 → 0.51 |
| L1-5m45 (4) | 1 177 437 → 1 963 585 (×1.7) | 12 853 → 17 072 (×1.3) | 27 → 28 (3.6 → 3.6) | 39 → 44 | 0.27 → 0.27 |
| L2-5m45 (4) | 2 523 275 → 3 845 915 (×1.5) | 31 883 → 40 356 (×1.3) | 48 → 64 (10.5 → 13.8) | 92 → 120 | 0.34 → 0.37 |
| all | 7 479 925 → 23 506 570 (×3.1) | 54 127 → 77 201 (×1.4) | 201 → 271 (×1.35); the run's wall 29 → 41 s | 352 → 556 (×1.6) | |

- Far below the circle study's factors: the layer's anchors are 60° (S, M) and 45° (L) over whole tiles,
  most of them in forest and fields where an anchor has no partner whatever the zone, and the 5 m zone leaves
  the long bands' rings almost as they are (L: lines ×1.5-1.7, seconds ×1.0-1.3). The S band, nearly empty
  here as it is (44 k lines in 144 km²), is where the zone finds most: ×166 lines, ×9 spots, +36 % seconds.
- Memory per tile unchanged (the count keeps no lines); the cube's spots ×1.4.
- Carried to Slovakia (13.57 CPU-h, about 48 min on 12 workers; 1.18 G lines, 3.68 M spots at the last
  count): about ×1.6 of CPU and of wall (22 CPU-h, 65-75 min), spots ×1.4, lines ×3 if the Súľov square
  stands for the country, which one square of 144 km² cannot show (the plan's estimate was a line factor
  of 1.5-5, which it is here, with the time ×1.35-1.6 instead of ×F). A count of the superset also needs
  the count mode to keep the bucket minima (`zones`, docs/country-precompute/contract.md, section 6:
  not measured, a few per cent of step 3's work by the circle study's kernels). The decision is the
  user's (extra computing: the rule of 2026-11-05).
