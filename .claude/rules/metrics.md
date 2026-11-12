---
paths:
  - "metrics.py"
  - "servicecounts.py"
  - "tools/job_stats.py"
  - "deploy/monitoring/**"
  - "tests/test_metrics.py"
  - "tests/test_monitoring.py"
---
# Metrics and the monitoring

What each part holds: docs/code-map/web.md (`metrics.py`, `servicecounts.py`), docs/code-map/deploy.md
(`deploy/monitoring/`); the plan and its decisions: docs/monitoring.md.

## Must stay in sync

- The monitoring's inputs and their parsing in `deploy/monitoring/telegraf.conf`: the nginx metrics log
  (`log_format findaline_metrics` and the groups of `$findaline_group` in `deploy/nginx/findaline-http.conf`: its
  fields, their JSON types, the group names), `stub_status` on `127.0.0.1:8081`, and the JSON files of
  `/var/lib/findaline-monitoring/` (`facts.json` of `facts.sh`, `check.json` of `facts.sh check`, `backup.json` of
  `backup.sh`: their keys, numbers only); a new field or group goes into both, and Grafana's panels and alerts that
  use it. The metrics log never holds an address, path, query, Referer or User-Agent
  (`tests/test_deploy.py::test_metrics_log_format`, `tests/nginx_check.sh`); the existing `findaline` format and the
  fail2ban filter that reads it stay apart from it.
- The application's metrics (`metrics.py`: names, labels and their values, as `tests/test_metrics.py::CONTRACT` lists
  them) and their users: the dashboards *Searches*, *Use* and *Data and computing*, the rows F9 and F12 of *VPS* and
  *Site*, the tiles of *Overview* and the alert rules of phase 2 in `deploy/monitoring/grafana/`, and the
  `inputs.prometheus` of `http://127.0.0.1:8766/metrics` in `deploy/monitoring/telegraf.conf`; a metric renamed, a
  label changed or the port moved (`web.METRICS_PORT`, compose.yaml's `METRICS_PORT`) changes them too. Totals come
  from the database rows (counters that only grow while rows are kept: jobs and favourites deleted with their run
  shrink `findaline_favourites`, a gauge); `findaline_job_duration_seconds` and `findaline_job_phase_seconds` are
  summaries (`_sum`/`_count`, no quantiles). Label values come from small fixed sets: a new label value from the
  database (an error code, a country) must never carry a user id, IP address, title, place name or path. A new request
  to an outside service in the worker goes through `servicecounts` (`get`, `request` or `call`), or F11 does not see
  it; its host comes from the catalogue or the OSM services, never from user input.
- The labels F18 and F19 read from the search's texts: `servicecounts.ROLES` are the labels `download_layers` and
  `prepare_layer` get ("terrain", "surface", "water mask", "gap fill (<source>)": `role_of`), and `jobs.StepClock`
  parses `search._step`'s "Step <n>/" in the progress bars' `step` and the stage "orthophoto tiles" of
  `orthophoto.download`'s Download bar (after "done" since 2026-11-02, so `run_phase` adds its row to `job_steps`
  after it): a new label or a renamed step or stage counts as "other" until both change
  (`tests/test_metrics.py::test_step_clock_and_ready_time`, `tests/test_servicecounts.py::test_tiles_of_the_layers`).
- The stages and the funnel of F19 (migration 16): `jobs.STAGE_KEYS` are the names of the Compute bars of steps 2 and
  3 (`progress.compute.start("<name>"` in helpers.py, search.py, sag.py, linesearch.py;
  `tests/test_metrics.py::test_stage_keys_are_compute_bars`) and the `stage` values of the Grafana panels;
  `jobs.STEP_KEYS`/`STAGE_KEYS`/`FUNNEL_STEPS` have copies in `tools/job_stats.py`, with its `DEFAULTS` and `PRESETS`
  of `params` (`tests/test_job_stats.py::test_tables_match_the_app`); its patterns for jobs from before migration 16
  follow the printed lines of `linesearch.find_valid_lines` and `search._lines` (as `tests/regression.py` `PATTERNS`)
  and the "[Compute] <stage>: ... - done in <duration>" text of `progress._Bar._print_text`/`_duration`: a change of
  those texts changes the tool and `OLD_OUTPUT` of its test.
- The masking of Telegraf's log processor (`processors.regex` of `deploy/monitoring/telegraf.conf`) and what the logs
  it reads may hold (nginx's error log, the app's stderr): a new field naming an address, a token or a query needs a
  pattern and a line in `tests/test_monitoring.py::LOG_LINES`. The metric names of the dashboards and rules follow
  `metrics.py` (`APP_METRICS` in `tests/test_monitoring.py`). The Grafana plugin is updated by changing
  `GRAFANA_PLUGIN_VERSION` and `GRAFANA_PLUGIN_SHA256` of `deploy/vps.sh` together (`packages.any.sha256` of
  `grafana.com/api/plugins/<id>/versions`).
- The units on the host and Grafana's alert on failed units (D1 of docs/monitoring.md, in
  `deploy/monitoring/grafana/`): `nginx.service`, `docker.service`, `fail2ban.service`, `ssh.service`,
  `certbot.timer`, `findaline-backup.timer`, `findaline-facts.timer`, `findaline-check.timer`,
  `findaline-heartbeat.timer`, `unattended-upgrades.service` (not `telegraf.service`: stopped, it cannot report
  itself; G2's alert on missing samples does); a unit renamed or added in `deploy/monitoring/systemd/` or `vps.sh`
  (`MONITORING_TIMERS`, `backups`) changes the alert too.

## Pitfalls

- **Testing the monitoring's host side**: systemd does not start in a container on Docker Desktop (cgroup v1): test
  `vps.sh`'s monitoring step in a privileged ubuntu:26.04 with dockerd started by hand and a `systemctl` stand-in; the
  CI runner has real systemd. The WSL distribution `Ubuntu-24.04` of this PC runs systemd: Telegraf's sandbox can be
  tried there without installing anything (`systemd-run --wait --pipe` with the drop-in's lines as `-p`,
  `User=nobody`, the binary unpacked from the `.deb` outside `/tmp`, `telegraf --test` without the `docker` input,
  which panics in test mode when the proxy is missing), compared with a run without the sandbox. VictoriaLogs' JSON
  answers write `<` as `\u003c`. Telegraf leaves Go's `$1` in a regex replacement alone; `${...}` would be an
  environment variable.
