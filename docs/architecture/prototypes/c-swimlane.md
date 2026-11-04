# Prototype C: swimlanes of processes and stores

Time flows down. The lanes are the processes and the stores, so every arrow answers "who writes what,
when". Mermaid's sequence diagrams render on GitHub too; the grid of processes against stores below
is a hand-drawn picture (an SVG in the HTML version, a table here).

## 1. A web job, from the form to the map

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant W as web.py
    participant J as jobs.sqlite
    participant S as worker: Scheduler
    participant P as phase process
    participant D as disk

    B->>W: POST /api/jobs (the form)
    W->>W: checked_request: SearchParams, Limits.check_params, precheck
    W->>J: Jobs.add(queued, check=admission)
    W-->>B: 202, the job's id
    B->>W: GET /api/events (SSE)
    loop every TICK
        S->>J: claim the oldest waiting job (a download slot)
        J-->>S: downloading
    end
    S->>P: spawn run_phase("download")
    P->>D: plan_search, estimate_search, download_data → cache/
    P->>J: progress events, note_area
    P->>J: set ready
    S->>J: claim (a compute slot)
    S->>P: spawn run_phase("compute")
    P->>D: search_lines → work/jobs/id/, save_run → runs/run/
    P->>J: add_run, _write_statistics, set done
    P->>D: download_orthophoto (no slot) → cache/ortho/
    W->>J: EventHub polls the new events once per TICK
    W-->>B: the job's events (seen_by the owner)
    B->>W: GET /runs/run/map.html (RunFiles: may_open)
```

## 2. The quick lane beside it

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as web.py
    participant J as jobs.sqlite (table quick)
    participant Q as worker: run_quick

    B->>W: POST /api/estimate | /api/profile | /api/patch | /api/place
    W->>W: within_rate, checked_request
    W->>J: insert the task (kind, request)
    loop asyncio.sleep until the answer or QUICK_WAIT_MAX
        W->>J: is the answer there?
    end
    Q->>J: quick_take (one task at a time)
    Q->>Q: plan_search + estimate_search | profile_of_line | patch_of_line | osm.places
    Q->>J: quick_answer (Redact on the public site)
    W-->>B: the answer, or 503 without a worker
```

## 3. The country layer's run

```mermaid
sequenceDiagram
    participant U as country run <id>
    participant M as manifest.sqlite
    participant K as country worker (K processes)
    participant D as disk

    U->>D: country.json, area.geojson (the outline, once)
    U->>M: every band's fixed_tiles as pending rows
    U->>D: _prefetch: download_layers per resolution → cache/
    U->>U: _warm_up (numba)
    U->>K: start K workers (worker_count from the largest tile's memory)
    loop until no pending tile
        K->>M: claim the heaviest pending tile (BEGIN IMMEDIATE)
        K->>D: tile_grid → prepare_data → count_tile → tiles/band/name.npz
        K->>M: done (or pending once more after a failure)
    end
    U->>D: countcube.build → cube/cube.json, lines_L.npy, spots_L.npy
```

## 4. Who writes where

| Process \ Store | `cache/` | `work/` | `runs/` | `countries/<id>/` | `jobs.sqlite` |
| --- | --- | --- | --- | --- | --- |
| CLI search | tiles, indexes, OSM | `work/<id>/` grids and tiles | the run, `runs.js` | | |
| web.py | | | reads (`RunFiles`), `runs.js` per user | | jobs, quick tasks, favourites, runs' owners |
| worker: phase process | tiles, orthophoto | `work/jobs/<job>/<phase>` | the run | | events, status, statistics |
| worker: quick lane | OSM answers | `work/quick/` | | | answers |
| saving.py children | | reads `<work>/saving/` | the line files, `data.js`, `lines.js` | | |
| country run / worker | tiles (prefetch) | `work/country-<id>/` | | tiles, `manifest.sqlite`, `cube/`, `logs/` | |

## For and against

- **For**: the only form that shows the hand-over between processes (web, worker, quick lane, children)
  and the stores they share; resuming, leases and slots have a place.
- **Against**: a poor fit for the five steps of the search itself and for the hierarchy; a complement to
  A or B, not a replacement.
