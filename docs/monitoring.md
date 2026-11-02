# Monitoring

What to watch on the VPS of the public site and in the application, where each value comes
from, how it is stored and when it raises an alert. Planned 2026-10-31; phases 1 and 2 are built
(`deploy/monitoring/`, `metrics.py`, docs/deployment.md section 15); phase 3 is built too (decisions
of 2026-11-01, see "Phases"), and the speed of downloads and computing (F18, F19, "Phase 4"). The public site and its server are described in
[deployment.md](deployment.md); the plans of the project in [roadmap.md](roadmap.md).

Today the operator checks by hand (`sudo deploy/vps.sh check`, the *Admin* page, `docker compose
ps`, `df -h /srv/docker`), and the only message that arrives by itself is the ntfy notice of a
failed backup (deployment.md, section 11).

## Decisions
| Topic | Decision (2026-10-31) |
| --- | --- |
| Collector and store | [Telegraf](https://docs.influxdata.com/telegraf/) writes the InfluxDB line protocol to [VictoriaMetrics](https://docs.victoriametrics.com/) (single node); Grafana reads it as a Prometheus data source (PromQL/MetricsQL). Moving to another store that takes the line protocol is one output section of Telegraf. |
| Telegraf (changed 2026-11-01) | On the host: InfluxData's `.deb` of a pinned version from `dl.influxdata.com`, checked against its sha256 in `deploy/vps.sh` (its signature checked once with InfluxData's package key), running as the package's user `telegraf` in the group `adm`, in a systemd sandbox (a drop-in). Not InfluxData's apt repository (any `apt upgrade` would update Telegraf, whose defaults change between versions), and Ubuntu dropped its own `telegraf` package in 24.04. First it ran as the official Docker image with `network_mode: host`: its uid had no user on the host, which the host's dbus-daemon refuses, so systemd's units (D1) failed in CI, and it read the host through a read-only mount of the whole `/` (`/home` too). The projects of host agents advise running them on the host. What only root can read comes from a timer on the host (see "Architecture"). |
| Docker's API | [wollomatic/socket-proxy](https://github.com/wollomatic/socket-proxy): an allowlist of regular expressions per HTTP method lets through only the GET requests Telegraf's `docker` input makes; it runs as a non-root user with the socket's group. |
| Outside check | [healthchecks.io](https://healthchecks.io): the host pings every minute while the site answers, `backup.sh` after each successful backup; a missing ping goes to the same ntfy topic. |
| Metrics of the application | [`prometheus_client`](https://github.com/prometheus/client_python), the official Prometheus client, chosen over OpenTelemetry's SDK (several packages, its Prometheus exporter still in beta versions, observable callbacks for values read at each scrape). |
| Order | Phase 1 (the infrastructure, no application code) first, then phase 2 (the application). The application's totals are counted from its database rows, so phase 2 also shows what happened before it. |
| Retention | Without a time limit: `-retentionPeriod=100y`, VictoriaMetrics' maximum. The open-source edition does not downsample, so the 30 s samples stay; about 1–2 GB a year (see "Storage"). |
| Viewing | Grafana listens on `127.0.0.1:3000` only and is opened through an SSH tunnel (`ssh -L 3000:127.0.0.1:3000 <server>`): no new site, name or certificate, nothing new open to the internet. |
| Alerts | Grafana's alert rules send to a secret [ntfy](https://ntfy.sh) topic (a webhook contact point): a push message on the phone, the channel deployment.md already uses for a failed backup. |
| Users by country | The country of the browser's time zone, stored with the account (variant B below), and the countries of the searched areas (variant A). |
| Area searched | Every user sees their own km² (today, the last 30 days, in total); the sign-in page shows the total of everyone; monitoring keeps the sums per day and country. |
| Privacy | Monitoring holds aggregates only: no IP addresses, user ids, titles or paths. The privacy page changes as described in "Privacy". |
| Counts of the outside services (F11, 2026-11-01) | The worker's processes count their requests per host and outcome in memory and add them to a table of `jobs.sqlite`; the web process's `/metrics` reads it, as everything else the two share. Rejected: `prometheus_client`'s multiprocess mode (a file per process, and every phase is a new process), a `/metrics` of the worker (a new port, counts lost at its restart). |
| Coverage (F17, 2026-11-01) | The worker keeps a simplified outline of every search's area; the housekeeping unions them (km² searched at least once) and counts the searches per cell of 0.25°, shown on Grafana's Geomap. |
| SSH logins (D4, 2026-11-01) | `pam_exec` in sshd's session sends a message to the ntfy topic at once, independent of the monitoring stack. |
| Downloads and computing apart (F18, F19, 2026-11-01) | The area of a day shows twice: computed (every search, repeats included) and downloaded (new terrain data; the rest is cached). Download speed per layer in Mpx/s of the data's own resolution (km²/s at 1 m: comparable between sources) and km²/s (what a user waits for); computing in Mpx (km² / resolution²), the measure of the compute quota (`mpx_day_max`), with its seconds per Mpx by class of resolution to check that the cost follows the pixels. |
| Logs (2026-11-01) | [VictoriaLogs](https://docs.victoriametrics.com/victorialogs/) in the monitoring project: the `web` and `worker` containers' output and nginx's error log (addresses masked), 30 days, read in Grafana. |

## Architecture
| Part | Where | What it does |
| --- | --- | --- |
| Telegraf | the host: `telegraf.service` of InfluxData's package with the drop-in `deploy/monitoring/systemd/telegraf.service.d/findaline.conf`, its configuration `deploy/monitoring/telegraf.conf` copied to `/etc/telegraf/telegraf.conf` (`vps.sh`, `telegraf_install`) | Reads the host (`/proc`, `/sys`, `/var/log/nginx`, systemd's units over D-Bus), the containers through the socket proxy, nginx (its metrics log and `stub_status`), the certificate and the site, the facts files and, in phase 2, the application's `/metrics`; writes to `http://127.0.0.1:8428` (and the logs to `127.0.0.1:9428`). The package's user `telegraf` with the group `adm` (nginx's logs). |
| VictoriaMetrics | the same project, `127.0.0.1:8428` | Stores the samples; its own metrics are scraped by Telegraf too (G2). |
| Grafana | the same project, `127.0.0.1:3000` | Dashboards, alert rules and the ntfy contact point, all provisioned from files in the repository (the ntfy topic from a Docker secret); its own database holds nothing that cannot be provisioned again. |
| Docker socket proxy | the same project, `127.0.0.1:2375` (wollomatic/socket-proxy) | Lets Telegraf's `docker` input read the containers (GET of the container list, their stats and inspect, and `/info`; from phase 3 also the logs of a container, which Telegraf asks only for `web` and `worker`; nothing else) without the Docker socket itself, which is equivalent to root. |
| Host facts | a systemd timer on the host, as root (`deploy/monitoring/facts.sh`, every 5 min) | Writes what only root can read as JSON into `/var/lib/findaline-monitoring/` (read by Telegraf, input `file`): fail2ban's counts per jail, the holes of the disk image (`image_holes` of `deploy/vps.sh`), pending updates (`facts.json`); a second timer (`findaline-check.timer`, daily) writes the result of `vps.sh check` (`check.json`). `backup.sh` writes its own `backup.json` there. |
| Heartbeat | a systemd timer on the host, every minute | Asks the site (`https://<site>/` through nginx on the host) and, when it answers 200, pings healthchecks.io; the ping URL is in a root-only file (`/etc/findaline-monitoring.env`). |
| VictoriaLogs (phase 3) | the same project, `127.0.0.1:9428` | Stores the log lines Telegraf sends (`inputs.docker_log` of `web` and `worker` through the socket proxy, `inputs.tail` of `findaline.error.log` with addresses, share tokens and the query of `/auth/...` masked) for 30 days; Grafana reads it with VictoriaMetrics' logs data source plugin. |
| SSH login notice (phase 3) | `pam_exec` in `/etc/pam.d/sshd` (`session optional`), a script of `deploy/monitoring/` | Posts "SSH login: user from address on server" to the ntfy topic (the URL from the checkout's `secrets/ntfy_url`, Grafana's secret, readable by root: one place for it) with a short timeout, and counts the logins in `ssh.json` of the facts folder. `optional`: a failure of the script never refuses a login. |
| `/metrics` of the application (phase 2) | a thread of the `web` process on its own port, published as `127.0.0.1:8766`, never behind nginx | The Prometheus text format (`prometheus_client`); its collectors read `jobs.sqlite`, `accounts.sqlite` and `audit.sqlite` at every scrape (aggregates only). The web process already has the accounts volume, so the volumes stay as they are. |

**Why a project of its own:** monitoring is started, updated and stopped without touching the site,
and `tests/test_deploy.py` (which expects exactly the services `web` and `worker` in compose.yaml)
stays as it is.

**The firewall.** VictoriaMetrics, Grafana and the socket proxy share a network with the bridge name
`br-fal-mon`. The `DOCKER-USER` block of `deploy/firewall/ufw-after.rules` needs one more
`-i br-fal-mon -o br-fal-mon -j RETURN` line; the drops towards private ranges and the host
(`br-fal-+`) then apply to it as to the site's networks. VictoriaMetrics needs no egress; Grafana
only the ntfy server. Telegraf runs on the host: it reaches the loopback ports (VictoriaMetrics,
VictoriaLogs, the proxy, `/metrics`, `stub_status`) and the site's own address, and needs no rule.
In a container on a network of its own, the rule of `ufw-before.rules` that drops whatever the
containers send to the host would cut it off from `stub_status`, the site and its certificate
(C4–C6), and it would have to join the site's network for `/metrics`.

**Hardening** as in compose.yaml: `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, a non-root
user, images pinned by digest, memory limits (about 2.1 GB for the four containers together,
VictoriaLogs included, 1.25 GB of it Grafana's, and 192 MB for Telegraf). Telegraf accepts no connections and runs in a
systemd sandbox (its drop-in): no capabilities, no new privileges, the file system read-only,
`/home` hidden, a private `/tmp`, no device opened, the system calls of `@system-service`, no
writable and executable memory, 192 MB without swap; `systemd-analyze security telegraf` rates it.
On the server, check that `WORKER_MEMORY` in `.env` leaves this room (the VPS has 24 GB).

## Storage
- **Intervals:** 30 s for the host, the containers, nginx and the application; 5 min for the
  certificate, systemd units, fail2ban, the backup and `exec` inputs.
- **Only the fields used:** `percpu = false`, `fieldinclude` lists, no per-device series that no
  panel shows.
- **nginx aggregated in Telegraf:** the metrics log is turned into counts and quantiles every 30 s
  (`aggregators.basicstats` / `aggregators.quantile`, `drop_original = true`): no sample per request.
- **No high-cardinality labels:** no IP address, user, path or job id; routes only as groups
  (api, events, patch, cache, s, auth, app), countries at most about 250.
- **Estimate:** 1 000–2 000 series at 30 s are 3–6 million samples a day; VictoriaMetrics keeps about
  1 byte per sample or less, so 1–2 GB a year. The store lives in a volume on Docker's data root,
  the same filesystem as the site's data, so it counts against the site's free-disk limit (G2
  watches it).
- **No backup** of VictoriaMetrics or Grafana: the configuration is in the repository, and lost
  samples do no harm.

## Privacy
**Never collected:** IP addresses, unique visitors, series per user, job titles, place names.
The metrics log of nginx is a second log without the address (`findaline.metrics.log`, JSON); the
existing `findaline.access.log` and its fail2ban filter stay as they are. Small counts (a country
with one user) are seen only by the administrator, who can read the databases anyway; a total per
country shown publicly would merge countries of fewer than 5 users into "other".

**The privacy page** (`web.privacy_page`, phase 2) changes in three places; wording accepted
2026-10-31:

| Where | Change |
| --- | --- |
| The facts | "No analytics, no advertising, no tracking cookies." becomes "No third-party analytics, no advertising, no tracking cookies. The operator keeps statistics of the site's operation without personal data (counts, sums and times, e.g. km² searched per day or users per country) without a time limit." |
| Searches | After "the options)": "its area in km² and the country it lies in,"; at the end: "Your totals of searched area are counted from these." The retention stays that of the search. |
| Your account | After "when you last signed in": ", and the country of your browser's time zone (only the country, e.g. PL), for statistics of where users come from; shown in your account menu". |

The total of everyone on the sign-in page and the total of favourites change nothing: they are one
number each.

**Phase 3** changes the privacy page in three more places (wording accepted 2026-11-01):

| Where | Change |
| --- | --- |
| Searches | "its area in km² and the country it lies in" becomes "its area in km², its outline and the country it lies in". The outline comes from what you search (for a coast, cliffs or a named place: the area the search covered) and is kept as long as the search. |
| A new item "Server logs" | "Messages of the application and errors of the web server, without IP addresses; they may name the place of a search. Why: to find faults. Deleted after 30 days; Docker's own copy is overwritten once it reaches 50 MB." |
| The facts | The example of the statistics gains "or the number of searches per area of about 25 km". |

**Phase 4** changes the item "Quotas" (wording accepted 2026-11-01): "How many km² your searches
covered and how many uncached Nominatim requests they made" becomes "How many km² your searches
covered (counted as pixels at their resolution), how many MB they downloaded and how many uncached
Nominatim requests they made". F18 and F19 are counts without users. So are the CPU seconds, the
stages and the funnel of the line search that F19 gained with migration 16 (2026-11-01, decided with
the user): the privacy page stays unchanged, as for F19.

F11, F12 and F13 are counts without users; D4 concerns the operator's own logins. The logs keep no
IP address: the application logs none (uvicorn's access log is off), and Telegraf masks the
`client:` field of nginx's error log before it is stored. nginx's own files are as before
(deployment.md, "What the logs of this site contain").

## What to monitor
Priority: P1 first. Phase 1 needs no change of the application's code, phase 2 does (see "Phases").
"Alert" conditions go to ntfy as alerts, "info" ones as quieter notices.

**A. The VPS**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| A1 | CPU: use, iowait, steal, load per core | alert: steal > 20 % for 15 min (the provider's other customers) | Telegraf `cpu` (`percpu = false`), `system` | P1 | 1 |
| A2 | Memory, OOM kills | alert: available < 5 % for 5 min; any OOM kill | `mem`, `kernel_vmstat` (field `oom_kill`) | P1 | 1 |
| A3 | Disk of `/` and `/srv/docker` (and inodes), days until full | alert: `/srv/docker` < 30 GB free (the site refuses searches below 20 GB, `FINDALINE_LIMIT_FREE_DISK_GB_MIN`), `/` < 10 GB | `disk`; `predict_linear` in Grafana | P1 | 1 |
| A4 | Holes in the disk image (`--disk-image`) | alert: > 1 GiB, as `vps.sh check` | the host facts (`image_holes` of `deploy/vps.sh`) → input `file` | P2 | 1 |
| A5 | Disk I/O of the loop device and the disk under it | queues during downloads | `diskio` | P2 | 1 |
| A6 | Network: traffic, errors, TCP connections | background for diagnosis | `net`, `netstat` | P2 | 1 |
| A7 | Reboot required, uptime, pending updates | info, once a day | `filestat` of `/run/reboot-required`, `system`, the pending updates from the host facts | P2 | 1 |
| A8 | Clock offset | alert: > 1 s | `chrony`, if chrony is the time daemon | P3 | 1 |

**B. Docker**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| B1 | `web` and `worker`: running, health, restarts, OOMKilled | alert: `web` unhealthy > 2 min; a restart; OOMKilled | `docker` through the socket proxy (wollomatic/socket-proxy) | P1 | 1 |
| B2 | CPU and memory of the containers against their limits (Telegraf reports no pids) | alert: `worker` > 90 % of `WORKER_MEMORY` for 5 min | `docker` | P1 | 1 |

**C. The site (nginx)**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| C1 | Requests per second by status class and route group (api, events, cache, s, auth, app) | alert: 5xx > 2 % for 5 min | a second `access_log` in JSON without the address (`findaline.metrics.log`; a `map $uri` gives the group) → `tail` + aggregator | P1 | 1 |
| C2 | Response time p50/p95/p99 (`$request_time`, `$upstream_response_time`) | alert: p95 of api > 2 s for 10 min | as C1, `aggregators.quantile` | P1 | 1 |
| C3 | Refusals of nginx's limits (429 per zone) | shows limits that are too tight | `$limit_req_status` in the metrics log | P2 | 1 |
| C4 | nginx's connections (active, reading, writing, waiting) | background for SSE and slow clients | `stub_status` on a loopback-only port → input `nginx` | P2 | 1 |
| C5 | Days until the certificate expires | alert: < 14 days (certbot renews from 30) | `x509_cert` of `https://<site>` | P1 | 1 |
| C6 | The site seen from the host: status and time | alert: not 200 | `http_response` | P1 | 1 |

**D. Services and security**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| D1 | systemd units: nginx, docker, fail2ban, ssh, `certbot.timer`, `findaline-backup.timer`, the facts and heartbeat timers, unattended-upgrades | alert: a unit in state failed | `systemd_units` through the D-Bus socket (mounted read-only) | P1 | 1 |
| D2 | fail2ban: banned now and bans per hour (jails `findaline`, `sshd`), counts only | alert: a sudden jump (an attack, or a legitimate user banned) | the host facts (`fail2ban-client status <jail>`, numbers only) → input `file` | P2 | 1 |
| D3 | `vps.sh check` once a day (the firewall from inside the containers, headers, SSH, the jail) | alert: any FAIL | the host facts (the number of FAIL lines and the time of the check) → input `file` | P2 | 1 |
| D4 | Successful SSH logins | info, each one (straight from the host to ntfy) | `pam_exec` in sshd's session: a message to ntfy and a count in `ssh.json` → input `file` | P3 | 3 |

**E. Backup**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| E1 | Age of the last successful backup, its duration and what it added | alert: no success for 26 h (healthchecks.io also reports a missing ping) | `deploy/backup.sh` writes `backup.json` → input `file` (JSON) | P1 | 1 |
| E2 | Size of the restic repository, number of snapshots | trend | `restic stats` in `backup.sh`, the same file | P2 | 1 |

**F. The application** (`/metrics`, aggregates only)
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| F1 | Worker alive: age of its lease, number of workers | alert: no live worker for 2 min (the worker healthcheck deferred in the roadmap) | table `workers`, as `Jobs.worker_alive` | P1 | 2 |
| F2 | Queue by status, age of the oldest waiting job, against `queue_max`; jobs per phase against `compute_slots` / `download_slots` | alert: the oldest waits > 30 min; > 80 % of `queue_max` | table `jobs` | P1 | 2 |
| F3 | Finished jobs by result and error code | alert: any internal error; > 30 % failed in 1 h | `error_info` code, or a category from the text (time limit, worker stopped, internal, interrupted); counters as `COUNT(*) GROUP BY` (job rows are kept) | P1 | 2 |
| F4 | Duration of jobs: in total, waiting, downloading, ready (downloaded, waiting for a compute slot), computing (`findaline_job_phase_seconds`, a summary) | trend; close to the time limits; which kind of slot is short | the total from `finished - created`; the phases from the columns of their start times (migration 13 of `jobs.sqlite`; `ready_at` migration 15: before it the download phase holds the wait for a compute slot) | P2 | 2, 4 |
| F5 | The quick lane (estimates, profiles, places): waiting, age of the oldest, 503/504 answers | alert: the oldest waits > 30 s | table `quick`; counters in the memory of the web process | P2 | 2 |
| F6 | Accounts by status | info: a new account is pending approval | `accounts.sqlite` | P1 | 2 |
| F7 | Activity: sessions seen in 15 min and 24 h; sign-ins, sign-ups, jobs added, share links, refusals (rate, quota) in the last hour | alert: a sudden jump of refusals | `sessions.seen`; `audit` (a window of 1 h) | P2 | 2 |
| F8 | Open problem reports | info: a new report | table `reports` | P2 | 2 |
| F9 | Runs (number, size), the cache per top-level folder, free disk as the application sees it | days until full | `runs.bytes`; the cache measured by the worker's housekeeping | P2 | 2 |
| F10 | Version, and deployments marked on the charts | what changed after an update | `findaline_build_info`; `vps.sh update` adds a Grafana annotation | P2 | 2 |
| F11 | External services: Nominatim, Overpass, Geofabrik, the orthophotos and the data sources: requests by host and outcome, MB, seconds (each retry is a request) | alert: > 20 % of a host's requests failed in 30 min (at least 10) | counters in the worker's processes, added to table `service_requests` of `jobs.sqlite` (see "Phases") | P3 | 3 |
| F12 | Requests of the application per route template, method and status class; time per route; open event streams | finer than nginx's route groups | the `guard` middleware of `web.py` and `EventHub`, counters in the web process | P3 | 3 |
| F13 | What the housekeeping removed, when it last ran and how long it took | alert: no round for 3 × `HOUSEKEEPING` | `work/housekeeping.json`, written as `cache-sizes.json` | P3 | 3 |
| F14 | Area searched: km² of finished searches per day and in total, by country of the area; beside it the km² of new terrain data (F18) | trend; the same numbers in the application; computed against downloaded shows the cache at work | columns `area_km2` and `country` of `jobs` (see "The area searched"); counter `findaline_area_km2_total{country}`: daily bars (`increase(...[1d])`) and the total | P2 | 2 |
| F15 | Users by country | trend | `users.country` (variant B) and the users who searched in each country (variant A, from `jobs.country`); `COUNT(*) GROUP BY country` | P2 | 2 |
| F16 | Favourite lines: the total | trend | `COUNT(*)` of table `favourites` | P2 | 2 |
| F17 | Coverage (km² searched at least once) and a map of searches in cells of 0.25° (Grafana's Geomap) | where people search | column `area_outline` of `jobs`; the union and the cells in the worker's housekeeping (`work/coverage.json`); cells without users | P3 | 3 |
| F18 | Tiles of the elevation layers per layer and role: downloaded (pixels, km², bytes, seconds in the host's slot), found in the cache, seconds waited for the tile's lock and a host slot | Mpx/s and km²/s per source (a service slowing down), the share of waiting (parallel downloads competing for `HOST_SLOTS`), the cache's share; new km² per day | `sources.layer.download_layers` counts through `servicecounts.tiles` (the pixels and km² from the cached file's header), table `layer_downloads` of `jobs.sqlite` (migration 15); `findaline_download_{tiles,tiles_cached,pixels,km2,bytes,seconds,wait_seconds}_total{layer,role}` | P3 | 4 |
| F19 | Computing: Mpx (km² / resolution²) and seconds of the finished searches by class of resolution (≤ 1, 2, 5, 10, 30 m); seconds and CPU seconds per step of the computing phase (1–5, the orthophoto tiles of step 5, other); seconds and CPU seconds of the stages of the line search (steps 2 and 3: finding anchors, anchor prominence and drop, sag estimator table, free directions, anchor pairs, checking lines); the funnel of the line search (grids, anchors, anchors kept after the prominence and drop limits, with an open direction, pairs started from, candidate pairs, checked pixel by pixel, found, valid, left out by the line limits, lines of the tiles' cores) | the Mpx a day (the compute quota's measure), whether the seconds follow the pixels at every resolution, which step and stage to speed up next and how many cores it keeps busy (CPU seconds over seconds), where the pairs are lost, the orthophoto held in a compute slot | columns `source` and `resolution` of `jobs` and table `job_steps` (migration 15; `jobs.StepClock` from the progress bars' states), `job_steps.cpu_seconds`, tables `job_stages` and `job_funnel` (migration 16; `search.Plan.funnel`, `linesearch.find_valid_lines(stats=)`); `findaline_computed_mpx_total{resolution}`, `findaline_computed_seconds_total{resolution}`, `findaline_compute_step_seconds{step}`, `findaline_compute_step_cpu_seconds{step}`, `findaline_compute_stage_seconds{stage}`, `findaline_compute_stage_cpu_seconds{stage}` (summaries), `findaline_line_funnel_total{level}`; per class of search: `tools/job_stats.py` | P3 | 4 |

**G. Monitoring of the monitoring**
| # | What | Why / alert | How | Priority | Phase |
| --- | --- | --- | --- | --- | --- |
| G1 | The VPS is alive and the site answers | alert: no ping for 5 min (Grafana on the same VPS cannot report its loss) | healthchecks.io: the heartbeat timer pings while the site answers 200, and sends to ntfy itself; problems seen only from outside (DNS, the route to the VPS) stay unseen | P1 | 1 |
| G2 | The monitoring itself: VictoriaMetrics' disk, Telegraf's write errors | alert: write errors | Telegraf's `internal` input, VictoriaMetrics' own metrics | P2 | 1 |

## Alerts
Every alert names the server and the row (A3, F1, ...) and links to its dashboard. Grafana evaluates
every minute; a condition must hold for its whole period before it fires, and a resolved alert sends
one message too.

| Level | Rows |
| --- | --- |
| alert | A1, A2, A3, A4, A8, B1, B2, C1, C2, C5, C6, D1, D2, D3, E1, F1, F2, F3, F5, F7, F11, F13, G1, G2 |
| info | A7, D4, F6, F8 |

## Dashboards
Every dashboard starts with a row of tiles ("at a glance", red needs attention) and links to all the
others, keeping the time range; the deployments (F10) are marked on all charts. Until 2026-11-02 the
rows F were one dashboard, *Find-a-Line*, of about 60 panels.

| Dashboard (uid) | Rows | Default range |
| --- | --- | --- |
| Overview (`overview`), Grafana's home page | One tile for every row with an alert rule, G1 and a few of the info rows (the site; the server: A, B, D1, D3, E1, G2; the application: F1-F3, F5-F8, F10, F11, F13, F14, F19), each with its alert's threshold and a link to its dashboard; the alerts firing; four charts (requests by status, searches by status, CPU and memory, error lines of the logs) | 24 h |
| VPS (`vps`) | A, F9 (the runs and the cache by folder), B, G2 | 24 h |
| Site (`site`) | C, F12 (the application's routes), D, E, G1 | 24 h |
| Searches (`searches`) | F1-F5, F13: the queue and the worker, the searches finished and their errors, the quick lane, the housekeeping | 24 h |
| Use (`use`) | F6-F8, F14-F17: accounts and activity, favourites, the area by day and country, users by country, the coverage map | 30 days |
| Data and computing (`performance`) | F11, F18, F19: the outside services, the downloads per layer and the cache, the Mpx computed, seconds per Mpx, steps, stages and the funnel of the line search | 7 days |
| Logs (`logs`, phase 3) | the lines of `web`, `worker` and nginx's error log, filtered by container and level, next to the rate of error lines | 24 h |

## The area searched
- **Data.** Migration 13 of `jobs.sqlite` (automatic) adds `area_km2` and `country` to `jobs`. The
  worker sets both where it plans the search, next to `charge_area` (a circle counts as π r², as in
  the km² quota); the country is `sources.country_code` of the area's centre (its Nominatim answer
  is usually cached already: the source `auto` asks it). Jobs of before get the area where the
  request gives it (a circle, a drawn area); coast, cliffs and `osm:` areas, and the country of
  every job of before, stay NULL (a migration asks no service). Only finished searches (`done`) count, repeats included (the sum of the
  work; coverage is F17).
- **For the user.** `/api/usage` gains `area`: the total km², the number of searches and the pairs
  (finished, km²) of the last 30 days; the page groups them by day in the viewer's time zone, like
  every other time. The account menu (`viewer/src/app/c/Account.tsx`) shows "today" and "in total"
  ("12 km² today · 1 230 km² in 48 searches"), the home page (`app/c/Home.tsx`) a card with the 30
  days as bars. Administrators and users without limits get theirs too; the quota table `usage` (2
  days) stays as it is.
- **For everyone.** The sign-in page (`web.signin_page`, server-rendered, no script) shows the total
  of all users, e.g. "48 300 km² searched in 1 234 searches": `SUM(area_km2)` and a count of the
  finished searches, kept in memory for a few minutes. Read-only, so no audit event.

## Users by country
- **B, the browser's time zone** (chosen). After a sign-in the app sends
  `Intl.DateTimeFormat().resolvedOptions().timeZone` (e.g. `Europe/Warsaw`) to a new endpoint; the
  server maps it to a country with IANA's `zone.tab` (shipped by `tzdata`, already in `uv.lock`
  through python-dateutil; made a direct dependency then) and stores only the code in a new column
  `users.country` (an automatic migration of `accounts.sqlite`). The sign-in page has no script,
  so the app does it. The endpoint changes state, so it records an audit event (the action added
  to `audit.ACTIONS`). The account menu shows the country. No IP address and no outside database;
  a VPN does not change it, a time zone set by hand does.
- **A, the countries of the searched areas** (chosen): `jobs.country` of F14 gives the users who
  searched in each country (one user may count in several) and the km² per country. No new
  personal data, but it measures where people travel, not where they live.
- **Not chosen:** GeoIP at sign-in (a local DB-IP Lite database: processes the IP address, needs
  DB-IP's attribution and a monthly update, a VPN misleads it); countries of requests from nginx's
  geoip2 module (counts requests, bots included, not users); a country typed in by the user (true,
  but few would). GitHub and Google give no country at sign-in (GitHub has a free-text location,
  Google a language).

## Phases
Each phase is one branch (or more), merged when its checks pass.

**Phase 1, the infrastructure** (A, B, C, D1–D3, E, G; the dashboards VPS and Site; the alerts of
these rows). No application code.
- `deploy/monitoring/`: `compose.yaml` (Telegraf, VictoriaMetrics, Grafana, the socket proxy, their
  digests), `telegraf.conf`, Grafana's provisioning (data source, dashboards, alert rules, contact
  point), `facts.sh` and the systemd units of the facts and heartbeat timers.
- `deploy/vps.sh`: a `monitoring` step in `setup`, `update` and `check`, idempotent on the running
  server (the units, `/var/lib/findaline-monitoring`, the ping URL's file, the project pulled and
  started with `--wait`).
- `deploy/nginx/findaline-http.conf` and `findaline.conf`: the metrics log format and log, the
  route `map`, `stub_status` on a loopback-only port.
- `deploy/firewall/ufw-after.rules` (`br-fal-mon`), `deploy/backup.sh` (`backup.json`, the healthchecks.io ping).
- Tests: `tests/nginx_check.sh` (the metrics log without addresses, `stub_status` not reachable from
  outside), `tests/test_deploy.py` (the monitoring project: ports on loopback only, hardening),
  `.github/workflows/ci.yml` (`docker compose config` of the project; the stack on the runner,
  with Telegraf installed as on the server since 2026-11-01).
- docs/deployment.md: a section "15. Monitoring" (the tunnel, the ntfy topic, the healthchecks.io
  check); CLAUDE.md (the code map, "Things that must stay in sync" for the nginx log formats).

**Phase 2, the application** (F1–F10, F14–F16).
- `prometheus_client` as a dependency (`uv lock`, the deprecation warnings visible in the tests).
- `metrics.py` (the collectors), the metrics thread of `web` (`start_http_server`) and its port (compose.yaml,
  `tests/test_deploy.py::test_compose_ports`, the CI docker job).
- Migration 13 of `jobs.sqlite`: the start times of the phases, `area_km2`, `country`.
- The area in the app (`/api/usage`, the account menu, the home page) and on the sign-in page; the
  country (B: the endpoint, `users.country`, the account menu, the audit action).
- The privacy page (the table in "Privacy"), the message catalogue, the dashboard Find-a-Line,
  `tests/test_metrics.py` (names and labels, no personal labels, the port not reachable through the
  public one) and the visual review of the changed pages (`tools/ui_shots.py`).

**Phase 3** (F11–F13, F17, D4, the logs; decided and built 2026-11-01). First `monitoring` is rebased onto
`main` (the `sources/` package of the sources refactor, where F11 counts). Then two agents in
parallel, as in phase 2: *app* (the Python modules, migration 14, the metrics, the privacy page,
their tests, README, CLAUDE.md) and *deploy* (`deploy/`, Grafana, Telegraf, VictoriaLogs, the
PAM script, `tests/test_monitoring.py`, `tests/test_deploy.py`, docs/deployment.md section 15).
- **Migration 14 of `jobs.sqlite`** (automatic): table `service_requests` (`host`, `outcome`,
  `requests`, `bytes`, `seconds`; key (`host`, `outcome`); running totals, never deleted: a few
  hundred rows at most) and column `jobs.area_outline` (GeoJSON in WGS84, simplified to about 50 m, less for small areas: `area.outline_geojson`).
  Jobs of before get an outline where the request gives it (a circle, a drawn area), as `area_km2`.
- **F11.** One small module (`servicecounts.py`, its writer `Jobs.add_service_requests`) counts requests in the memory of a process (host, outcome, bytes,
  seconds) and adds them to `service_requests` in one write transaction: at the end of every
  phase and quick task, and every 60 s during a phase. Only where the web worker sets the data
  folder (as `osm.BEFORE_REQUEST`): the CLI and the regression set count nothing. Counted at each
  request: `sources.net._get` (every attempt, so retries show), the listings of
  `sources/indexes/listings.py`, `WcsReader`'s DescribeCoverage, `osm._ask`, the queries under
  `osm._overpass_turn`, `osmextract`, `coast`'s world file, `orthophoto`; `Windows` per block read
  (GDAL's own HTTP requests and retries are not seen). Outcomes: `ok`, `not_found`, `http_4xx`,
  `http_5xx`, `timeout`, `connection`, `other`; the host is the URL's (fixed by the catalogue and
  the OSM services). Metrics `findaline_service_requests_total{host,outcome}`,
  `findaline_service_bytes_total{host}`, `findaline_service_seconds_total{host}`; the alert as in
  the table.
- **F12.** In `web.py`'s `guard`: `findaline_http_requests_total{route,method,status}` (the
  template of the matched route, `unmatched` without one; the status as a class `2xx`...`5xx`),
  `findaline_http_request_seconds{route}` (a summary, without the event stream), and
  `findaline_event_streams` from `EventHub`. Counters of the web process, from zero after a
  restart (`rate()` and `increase()` cope).
- **F13.** `Scheduler.housekeeping` collects what its calls return (`.part` files, events, quick
  answers, usage rows, audit events, work folders) and writes `work/housekeeping.json` (`time`,
  `seconds`, `removed`) atomically; metrics `findaline_housekeeping_removed{what}` (the last
  round), `findaline_housekeeping_last_run_timestamp_seconds`, `findaline_housekeeping_seconds`.
- **F17.** The worker sets `area_outline` with `area_km2` for every kind of area (for a coast, cliffs
  or `osm:` the region the search covered). The housekeeping unions the outlines of finished jobs
  (shapely; the area on the ellipsoid with `pyproj.Geod`) and counts the searches whose outline
  touches each 0.25° cell, into `work/coverage.json`; metrics `findaline_coverage_km2` and
  `findaline_searches_by_cell{lat,lon}` (the cell's south-west corner). The dashboard shows the
  number and a Geomap (a "labels to fields" transformation gives it the coordinates).
- **D4.** `deploy/monitoring/ssh-login.sh`, installed by `vps.sh monitoring` with one line in
  `/etc/pam.d/sshd` (`session optional pam_exec.so quiet ...`, idempotent; `check` looks for it):
  on `open_session` it posts to ntfy in the background with a 5 s timeout and counts the login in
  `ssh.json`; the Site dashboard shows the count. Tested on Ubuntu 26.04 in a container with sshd:
  a key login sends the message to a fake ntfy, and still works when ntfy cannot be reached or the
  script fails.
- **The logs.** VictoriaLogs (single node, pinned by digest, `127.0.0.1:9428`,
  `-retentionPeriod=30d`, a volume, hardened like the others). Telegraf: `inputs.docker_log` of
  `web` and `worker` (the socket proxy's allowlist gains a container's `logs`), `inputs.tail` of
  `findaline.error.log` with a processor masking `client: <address>`; logs routed only to
  VictoriaLogs and metrics only to VictoriaMetrics (`namepass`/`namedrop`), through the ingestion
  API VictoriaLogs' current docs give for Telegraf. Grafana: the plugin
  `victoriametrics-logs-datasource` (signed by Grafana Labs), downloaded by `vps.sh`
  (`grafana_plugins`: version and sha256 pinned) into `/var/lib/findaline-grafana-plugins`, mounted
  read-only as Grafana's plugins folder: Grafana fetches nothing itself (its preinstall option
  would add five default apps from grafana.com); a provisioned data source and the Logs dashboard.
  VictoriaLogs joins `br-fal-mon` like VictoriaMetrics; it is distroless, so `vps.sh check` asks
  its `/health` (Telegraf's healthcheck did while Telegraf was a container).
- **Tests:** `tests/test_metrics.py` (the new names and labels, no personal ones), units of
  migration 14, the counting module and the coverage (shapes with known areas),
  `tests/test_monitoring.py` (the rules, the dashboards, the routing of Telegraf's outputs, the
  proxy's allowlist), `tests/test_deploy.py` (VictoriaLogs on loopback only, the PAM line), the CI
  docker job replayed, the monitoring stack with a fake exporter and a log line, `vps.sh` on real
  Ubuntu 26.04 (stubs have let VPS bugs through before), and the visual review of the privacy
  page.

**Phase 4** (F18, F19, the compute quota in Mpx; decided and built 2026-11-01).
- **Why apart.** A download is paid once (the cache keeps a tile until its TTL), a computation by
  every search: the same place searched ten times with other values is ten computations and one
  download. And they depend on different resolutions: a download on the data's own (a 5 m search in
  Poland still downloads the 1 m sheets; only WCS layers without `fetch_res` and swisstopo's two
  resolutions follow the grid), a computation on the search's (pixels = km² / resolution²; most
  of its steps are linear in the pixels, docs/performance.md).
- **Migration 15 of `jobs.sqlite`** (automatic): `jobs.ready_at`, `jobs.source`, `jobs.resolution`,
  table `job_steps` (job, step, seconds) and table `layer_downloads` (running totals per layer and
  role, as `service_requests`). Jobs of before get none of them.
- **F18.** `Layer._download_and_record` measures the wait for the tile's lock and a host slot apart
  from the download in the slot; `download_layers` counts the tiles found in the cache, by the role
  of its label (terrain, surface, water mask, gap fill). `servicecounts.flush` writes them with the
  requests of F11, so the CLI and the regression set count nothing. The speed is that of one
  connection (the seconds of every tile summed), so it compares sources; the format still counts
  (zipped ASCII sheets, float32 COGs, whole metres), and the network alone is F11's MB/s per host.
- **F19.** The worker stores a job's source and resolution when it plans the download phase, and the
  seconds of the steps of its computing phase when it ends (`jobs.StepClock` listens to the
  progress bars: the step of their text, the orthophoto tiles while their bar runs).
- **Migration 16 of `jobs.sqlite`** (automatic, 2026-11-01, branch `line-order`): `job_steps.cpu_seconds`
  (the CPU seconds of a step: `time.process_time` of the phase's process, numba's threads included),
  table `job_stages` (job, stage, seconds, CPU seconds: the stages of the line search while their
  Compute bar runs, summed over the tiles) and table `job_funnel` (job, step, count:
  `search.Plan.funnel`, which `search._lines` and `linesearch.find_valid_lines(stats=)` fill, summed
  over the tiles; a tile a resumed search had saved already adds nothing). `run_phase` writes them
  after a computing phase that saved its run; a failed write never fails the search (a line to
  stderr). Jobs of before get none of these; `tools/job_stats.py` (read-only, standard library only,
  for the host's `python3`) reads their funnel and the stages' whole seconds from their info events.
  The dashboard Data and computing (row Computing) has three panels of them (mean CPU per step, seconds and CPU per stage,
  the funnel per day). Why: docs/performance.md, "Order of elimination" — which kind of search uses
  the site's CPU decides which part of the line search to speed up first.
- **The candidates of the funnel since the faster line search** (2026-11-01, branch `line-kernels`):
  the pair search now skips the partners beyond the reach of an anchor's rings before it counts the
  candidates (they fail the rings' test, which comes after the count), so `candidates` (and
  "Candidate pairs" in the info events) is smaller from the jobs computed with it on: 46-99 % of the
  count before in the searches measured. The panel of the funnel steps down there, and the share
  checked/candidates of `tools/job_stats.py` mixes both kinds in a class that holds jobs from before
  and after; the other steps of the funnel count as before.
- **The quota.** The daily quota of a user's searches counts Mpx (`mpx_day_max`), not km²: 250 km² is
  250 Mpx at 1 m but 10 Mpx at 5 m, so a quota in km² punished coarse overviews (the cheapest) and
  told fine searches from each other not at all. The downloads keep their quota in MB
  (`download_mb_day_max`): it follows the data's resolution and the cache already. Seconds of CPU
  were rejected as a quota: known only afterwards, dependent on the server's load and absent from the
  estimate; F19 shows them instead.

## Not collected, and approaches rejected
- **Not collected:** IP addresses, unique visitors, series per user (the privacy page: the
  application stores no addresses, rates are counted in memory only).
- **Grafana under a path of the site:** nginx refuses `Upgrade` for the whole server, and the
  fail2ban jail would count Grafana's 401s.
- **Telegraf in group `docker`:** equivalent to root on the host.
- **Telegraf reading SQLite directly** (`inputs.sql`): it would depend on the schemas, the accounts
  volume is the web service's only on purpose, and read-only WAL databases need care; the
  application knows its tables and exposes the numbers itself.
- **Telegraf on a network of its own:** cut off from the host by `ufw-before.rules` (see
  "Architecture").
- **Telegraf in a container** (until 2026-11-01): see "Decisions". Giving the container a user of
  the host would have fixed D-Bus, but not the mount of the whole `/`, and the host agent would
  still have needed the `/hostfs` paths.
- **tecnativa/docker-socket-proxy:** opens whole sections of the API (`CONTAINERS=1` lets the
  containers' logs through too) and runs HAProxy as root in its container.
- **UptimeRobot** (an HTTP check from the internet every 5 min): it does not see the backup, and its
  free plan sends no webhook to ntfy, according to most sources.

## Open decisions
None for phases 1 and 2. Phase 3: the threshold of F11 (20 %, at least 10 requests in 30 min) is a first guess, to be
tuned after a few weeks.
