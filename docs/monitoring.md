# Monitoring

What to watch on the VPS of the public site and in the application, where each value comes
from, how it is stored and when it raises an alert. Planned 2026-10-31; phases 1 and 2 are built
(`deploy/monitoring/`, `metrics.py`, docs/deployment.md section 15), phase 3 is not. The public site and its server are described in
[deployment.md](deployment.md); the plans of the project in [roadmap.md](roadmap.md).

Today the operator checks by hand (`sudo deploy/vps.sh check`, the *Admin* page, `docker compose
ps`, `df -h /srv/docker`), and the only message that arrives by itself is the ntfy notice of a
failed backup (deployment.md, section 11).

## Decisions
| Topic | Decision (2026-10-31) |
| --- | --- |
| Collector and store | [Telegraf](https://docs.influxdata.com/telegraf/) writes the InfluxDB line protocol to [VictoriaMetrics](https://docs.victoriametrics.com/) (single node); Grafana reads it as a Prometheus data source (PromQL/MetricsQL). Moving to another store that takes the line protocol is one output section of Telegraf. |
| Telegraf | The official Docker image `telegraf`, pinned by digest, in the monitoring project with `network_mode: host`; it reads the host through read-only mounts. Ubuntu dropped its `telegraf` package in 24.04, and InfluxData's apt repository would have been the other way. What only root can read comes from a timer on the host (see "Architecture"). |
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

## Architecture
| Part | Where | What it does |
| --- | --- | --- |
| Telegraf | compose project `findaline-monitoring` (`deploy/monitoring/compose.yaml`), `network_mode: host` | Reads the host through read-only mounts (`/` as `/hostfs`, with `HOST_PROC`, `HOST_SYS`, `HOST_MOUNT_PREFIX`; `/var/log/nginx`; the D-Bus socket for systemd's units), the containers through the socket proxy, nginx (its metrics log and `stub_status`), the certificate and the site, the facts files and, in phase 2, the application's `/metrics`; writes to `http://127.0.0.1:8428`. A non-root user with the group `adm` (nginx's logs). |
| VictoriaMetrics | the same project, `127.0.0.1:8428` | Stores the samples; its own metrics are scraped by Telegraf too (G2). |
| Grafana | the same project, `127.0.0.1:3000` | Dashboards, alert rules and the ntfy contact point, all provisioned from files in the repository (the ntfy topic from a Docker secret); its own database holds nothing that cannot be provisioned again. |
| Docker socket proxy | the same project, `127.0.0.1:2375` (wollomatic/socket-proxy) | Lets Telegraf's `docker` input read the containers (GET of the container list, their stats and inspect, and `/info`; no logs, nothing else) without the Docker socket itself, which is equivalent to root. |
| Host facts | a systemd timer on the host, as root (`deploy/monitoring/facts.sh`, every 5 min) | Writes what only root can read as JSON into `/var/lib/findaline-monitoring/` (mounted read-only into Telegraf, input `file`): fail2ban's counts per jail, the holes of the disk image (`image_holes` of `deploy/vps.sh`), pending updates (`facts.json`); a second timer (`findaline-check.timer`, daily) writes the result of `vps.sh check` (`check.json`). `backup.sh` writes its own `backup.json` there. |
| Heartbeat | a systemd timer on the host, every minute | Asks the site (`https://<site>/` through nginx on the host) and, when it answers 200, pings healthchecks.io; the ping URL is in a root-only file (`/etc/findaline-monitoring.env`). |
| `/metrics` of the application (phase 2) | a thread of the `web` process on its own port, published as `127.0.0.1:8766`, never behind nginx | The Prometheus text format (`prometheus_client`); its collectors read `jobs.sqlite`, `accounts.sqlite` and `audit.sqlite` at every scrape (aggregates only). The web process already has the accounts volume, so the volumes stay as they are. |

**Why a project of its own:** monitoring is started, updated and stopped without touching the site,
and `tests/test_deploy.py` (which expects exactly the services `web` and `worker` in compose.yaml)
stays as it is.

**The firewall.** VictoriaMetrics, Grafana and the socket proxy share a network with the bridge name
`br-fal-mon`. The `DOCKER-USER` block of `deploy/firewall/ufw-after.rules` needs one more
`-i br-fal-mon -o br-fal-mon -j RETURN` line; the drops towards private ranges and the host
(`br-fal-+`) then apply to it as to the site's networks. VictoriaMetrics needs no egress; Grafana
only the ntfy server. Telegraf runs in the host's network namespace: it reaches the loopback ports
(VictoriaMetrics, the proxy, `/metrics`, `stub_status`) and the site's own address like a process
of the host, and needs no rule. On a network of its own, the rule of `ufw-before.rules` that drops
whatever the containers send to the host would cut it off from `stub_status`, the site and its
certificate (C4–C6), and it would have to join the site's network for `/metrics`.

**Hardening** as in compose.yaml: `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, a non-root
user, images pinned by digest, memory limits (about 1.2 GB for the four containers together).
Telegraf accepts no connections; its mounts are read-only. On the server, check that
`WORKER_MEMORY` in `.env` leaves this room (the VPS has 24 GB).

## Storage
- **Intervals:** 30 s for the host, the containers, nginx and the application; 5 min for the
  certificate, systemd units, fail2ban, the backup and `exec` inputs.
- **Only the fields used:** `percpu = false`, `fieldinclude` lists, no per-device series that no
  panel shows.
- **nginx aggregated in Telegraf:** the metrics log is turned into counts and quantiles every 30 s
  (`aggregators.basicstats` / `aggregators.quantile`, `drop_original = true`): no sample per request.
- **No high-cardinality labels:** no IP address, user, path or job id; routes only as groups
  (api, events, cache, s, auth, app), countries at most about 250.
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
| A7 | Reboot required, uptime, pending updates | info, once a day | `filestat` of `/hostfs/var/run/reboot-required`, `system`, the pending updates from the host facts | P2 | 1 |
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
| D4 | Successful SSH logins | info, each one | needs logs (the journal), not metrics | P3 | 3 |

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
| F4 | Duration of jobs: in total, waiting, downloading (until computing starts, so the wait for a compute slot too), computing (`findaline_job_phase_seconds`, a summary) | trend; close to the time limits | the total from `finished - created`; the phases need columns of their start times (migration 13 of `jobs.sqlite`) | P2 | 2 |
| F5 | The quick lane (estimates, profiles, places): waiting, age of the oldest, 503/504 answers | alert: the oldest waits > 30 s | table `quick`; counters in the memory of the web process | P2 | 2 |
| F6 | Accounts by status | info: a new account is pending approval | `accounts.sqlite` | P1 | 2 |
| F7 | Activity: sessions seen in 15 min and 24 h; sign-ins, sign-ups, jobs added, share links, refusals (rate, quota) in the last hour | alert: a sudden jump of refusals | `sessions.seen`; `audit` (a window of 1 h) | P2 | 2 |
| F8 | Open problem reports | info: a new report | table `reports` | P2 | 2 |
| F9 | Runs (number, size), the cache per top-level folder, free disk as the application sees it | days until full | `runs.bytes`; the cache measured by the worker's housekeeping | P2 | 2 |
| F10 | Version, and deployments marked on the charts | what changed after an update | `findaline_build_info`; `vps.sh update` adds a Grafana annotation | P2 | 2 |
| F11 | External services: Nominatim, Overpass, the data sources (MB, errors, retries) | alert: a jump of a source's errors | new counters in `osm.py` and `sources.py` | P3 | 3 |
| F12 | Requests of the application per endpoint, open event streams | finer than nginx's route groups | a middleware and counters | P3 | 3 |
| F13 | What the housekeeping removed | background | the counts it returns and throws away today | P3 | 3 |
| F14 | Area searched: km² of finished searches per day and in total, by country of the area | trend; the same numbers in the application | columns `area_km2` and `country` of `jobs` (see "The area searched"); counter `findaline_area_km2_total{country}`: daily bars (`increase(...[1d])`) and the total | P2 | 2 |
| F15 | Users by country | trend | `users.country` (variant B) and the users who searched in each country (variant A, from `jobs.country`); `COUNT(*) GROUP BY country` | P2 | 2 |
| F16 | Favourite lines: the total | trend | `COUNT(*)` of table `favourites` | P2 | 2 |
| F17 | Optional: coverage (km² searched at least once) and a map of searches in cells of 0.25° (Grafana's Geomap) | where people search | the union of the areas in the worker's housekeeping; cells without users | P3 | 3 |

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
| alert | A1, A2, A3, A4, A8, B1, B2, C1, C2, C5, C6, D1, D2, D3, E1, F1, F2, F3, F5, F7, F11, G1, G2 |
| info | A7, D4, F6, F8 |

## Dashboards
| Dashboard | Rows |
| --- | --- |
| VPS | A, B, G2 |
| Site | C, D, E, G1 |
| Find-a-Line | F (the queue and the worker first, then use: area, users by country, favourites) |

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
  `.github/workflows/ci.yml` (`docker compose config` of the project, `telegraf --test` of the
  configuration).
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

**Phase 3** (F11–F13, F17, D4): counters of the external services and the endpoints, coverage, logs
(VictoriaLogs for the containers' stderr and nginx's error log).

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
- **tecnativa/docker-socket-proxy:** opens whole sections of the API (`CONTAINERS=1` lets the
  containers' logs through too) and runs HAProxy as root in its container.
- **UptimeRobot** (an HTTP check from the internet every 5 min): it does not see the backup, and its
  free plan sends no webhook to ntfy, according to most sources.

## Open decisions
None for phases 1 and 2. The rows of phase 3 (F11–F13, F17, D4) are decided one by one when it
comes.
