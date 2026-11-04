# Processes and stores

The second level: the commands of [findaline.py](../../findaline.py), the processes each starts, and
the stores they share. A search itself is [search.md](search.md); a web job's life is
[web-jobs.md](web-jobs.md); the country layer is [search-vs-country.md](search-vs-country.md).

## In plain words

The program can run as a one-off command, as a small web server with a worker that does the
searches one after another, or as a long run over a whole country. All of them read and write the
same folders on disk, so a search from the command line and one from the browser share the
downloaded height maps.

```mermaid
flowchart LR
    cmd["One command:<br/>a search, then the map"]
    web["The web page<br/>and its worker"]
    country["A whole country,<br/>tile after tile"]
    disk[("The same folders on disk:<br/>height maps, saved searches, counts")]
    cmd --> disk
    web --> disk
    country --> disk
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class cmd,web,country step
    class disk file
```

## The commands

`findaline.py` looks at its first argument. Everything else is a search from the command line.

```mermaid
flowchart LR
    fal["findaline.py<br/>first argument"]
    fal -- "lat, lon or an area" --> search["A search<br/>params.parse_cli → search.run_search"]
    fal -- "web" --> web["web.main<br/>FastAPI on 127.0.0.1, the worker in-process"]
    fal -- "worker" --> worker["jobs.main<br/>a Scheduler of its own (the public site)"]
    fal -- "country" --> country["country.main<br/>run, status, profile, build, compare, worker"]
    fal -- "cache, osm, sources" --> update["update.main<br/>cache status, cache update, osm download, osm update, sources check"]
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class fal,search,web,worker,country,update step
```

## The processes of the web app and the worker

The web process validates and queues; it never searches, downloads or imports numba. The worker
(in the same process locally, its own process on the public site) runs each job's phase in a spawned
process and the quick answers in one long-lived process. They talk only through `jobs.sqlite`.

```mermaid
flowchart LR
    subgraph webp["web process"]
        api["web.py<br/>routes, validation, RunFiles, EventHub"]
    end
    subgraph workerp["worker: jobs.Scheduler"]
        sched["Scheduler._check<br/>every TICK: claim, start, kill, housekeeping"]
        phase["run_phase<br/>one spawn process per job and phase"]
        quick["run_quick<br/>one long-lived process: estimate, profile, place, patch"]
        warm["warmup.warm_up<br/>numba compiled at the start"]
        saving["saving.py children<br/>step 5 of runs of MIN_LINES lines or more"]
    end
    jobsdb[("jobs.sqlite<br/>jobs, events, leases, quick, runs")]
    cache[("cache/")]
    work[("work/jobs/&lt;job&gt;/&lt;phase&gt;")]
    runs[("runs/&lt;run&gt;/")]
    browser["Browser"]
    browser -- "POST /api/jobs, /api/estimate ..." --> api
    api -- "SSE /api/events" --> browser
    api -- "jobs, quick tasks" --> jobsdb
    jobsdb -- "new events" --> api
    sched -- "claims, leases, cancel_requested" --> jobsdb
    sched -- "spawn" --> phase
    sched -- "start once" --> quick
    sched -- "start once" --> warm
    phase -- "events, status, statistics" --> jobsdb
    quick -- "answers" --> jobsdb
    phase -- "tiles" --> cache
    phase -- "grids, tiles" --> work
    phase -- "the run" --> runs
    phase -- "subprocess" --> saving
    saving -- "line files" --> runs
    api -- "serves (may_open)" --> runs
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class api,sched,phase,quick,warm,saving step
    class jobsdb,cache,work,runs file
    class browser actor
```

Rules that keep this safe, all in [jobs.py](../../jobs.py): a status change and its event go in one
write transaction; a phase ends a job only while it is still in that phase's status (`when=`); a job
is failed as interrupted only when its worker's lease (`LEASE`, renewed every `HEARTBEAT`) has
expired; the phase process gets its `Limits` as an argument and prints nothing to a terminal (its
stdout becomes `info` events).

## The processes of the country layer

```mermaid
flowchart LR
    run["country run &lt;id&gt;<br/>the driver: run.lock, the manifest, prefetch, warm-up"]
    workers["country worker --slot k<br/>K processes, one tile at a time"]
    manifest[("countries/&lt;id&gt;/manifest.sqlite<br/>tiles pending, running, done, failed")]
    cache[("cache/")]
    workdir[("work/country-&lt;id&gt;/&lt;band&gt;-&lt;name&gt;/<br/>a tile's grids, removed after it")]
    tiles[("countries/&lt;id&gt;/tiles/&lt;band&gt;/&lt;name&gt;.npz")]
    cube[("countries/&lt;id&gt;/cube/<br/>cube.json, lines_L.npy, spots_L.npy")]
    web["web.Countries<br/>/api/countries, the page #layer"]
    run -- "fixed_tiles as rows" --> manifest
    run -- "_prefetch per resolution" --> cache
    run -- "starts K" --> workers
    workers -- "claim, done, failed" --> manifest
    workers -- "reads tiles" --> cache
    workers -- "prepare_data" --> workdir
    workers -- "save_tile" --> tiles
    run -- "countcube.build when every layer band is done" --> cube
    cube --> web
    classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c
    classDef q fill:#fbefd9,stroke:#995500,color:#17201c
    classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c
    classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c
    class run,workers,web step
    class manifest,cache,workdir,tiles,cube file
```

## The public site

The same two programs in two containers behind nginx on the host; the monitoring beside them is
[monitoring.md](monitoring.md).

| Piece | Runs as | Talks to |
| --- | --- | --- |
| nginx, fail2ban, ufw, certbot | the host's packages (`deploy/vps.sh`) | the browser; `127.0.0.1:8765` of the web container |
| `web --public` | the container `web` of `compose.yaml`, uid 10001, read-only root | `jobs.sqlite`, `accounts.sqlite`, `audit.sqlite` on the volume `/data`; the sign-in providers |
| `worker --public` | the container `worker`, no published port | the same `/data`; the data providers and OpenStreetMap |
| `metrics.serve` | a thread of `web`, `127.0.0.1:8766` on the host | Telegraf |

## Where in the code

| Node | File | Function or name |
| --- | --- | --- |
| findaline.py, first argument | [findaline.py](../../findaline.py) | the dispatch in `__main__`: `cache`, `osm`, `sources`, `web`, `worker`, `country` |
| A search | [params.py](../../params.py), [search.py](../../search.py) | `parse_cli`, `run_search` |
| web.main | [web.py](../../web.py) | `main`, `create_app` |
| jobs.main | [jobs.py](../../jobs.py) | `main`, `Scheduler` |
| country.main | [country.py](../../country.py) | `main`: `run`, `status`, `profile`, `build`, `compare`, `worker` |
| update.main | [update.py](../../update.py) | `main` |
| Scheduler._check | [jobs.py](../../jobs.py) | `Scheduler._check`, `TICK`, `housekeeping` |
| run_phase | [jobs.py](../../jobs.py) | `run_phase` |
| run_quick | [jobs.py](../../jobs.py) | `run_quick`, `QUICK` |
| warmup.warm_up | [warmup.py](../../warmup.py) | `warm_up`, `Scheduler(warm_up=True)` |
| saving.py children | [saving.py](../../saving.py) | `write_files`, `MIN_LINES` |
| RunFiles, EventHub | [web.py](../../web.py) | `RunFiles`, `EventHub`, `may_open` |
| LEASE, HEARTBEAT | [jobs.py](../../jobs.py) | `LEASE`, `HEARTBEAT`, `Jobs.set(when=)` |
| country run, country worker | [country.py](../../country.py) | `_run`, `_run_workers`, `Manifest`, `TileWork` |
| countcube.build | [countcube.py](../../countcube.py) | `build` |
| web.Countries | [web.py](../../web.py) | `Countries` |
| compose.yaml, deploy/vps.sh | [compose.yaml](../../compose.yaml), [deploy/vps.sh](../../deploy/vps.sh) | the services `web` and `worker`; `setup`, `update`, `check` |
| metrics.serve | [metrics.py](../../metrics.py), [web.py](../../web.py) | `serve`, `web.METRICS_PORT` |
