# Code map: Docker, the VPS, the monitoring

What the modules of this area hold, in detail: Docker, the VPS, the monitoring. Moved out of CLAUDE.md on 2026-11-12;
nothing loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync
and the pitfalls are in `.claude/rules/` (deploy, metrics).

## `Dockerfile`, `compose.yaml`

The image and the two services of the public site; `.dockerignore`, `findaline.env.example`, `.env.example`,
`secrets/README.md`; `web` publishes `127.0.0.1:8765` (nginx on the host); networks: `web` (egress for OAuth, fixed
gateway `172.30.0.1` = `FINDALINE_TRUSTED_PROXY`), `worker` (egress), bridges named `br-fal-*` for the host firewall

## `deploy/`

The VPS (docs/deployment.md), nginx on the host from Ubuntu's packages: `vps.sh` (`setup`, `update`, `check`: the
commands of docs/deployment.md, each step idempotent; sourced, it only defines its functions; `shellcheck` clean),
`nginx/findaline-http.conf` (`conf.d/`: the upstream, zones, the masked log format, the metrics log format
`findaline_metrics` and its route groups `$findaline_group`, slow-client timeouts, `stub_status` on `127.0.0.1:8081`),
`nginx/findaline-tls.conf` (`snippets/`: Mozilla intermediate), `nginx/findaline-acme.conf` (port 80: certbot's
webroot, redirect, 444 for other names), `nginx/findaline.conf` (port 443: limits, SSE, gzip, own log and the metrics
log, HSTS at the server level, handshake refused for other names), `fail2ban/` (filter and jail, `jail.d/`),
`firewall/ufw-after.rules` (`DOCKER-USER`, also the monitoring's `br-fal-mon`) and `ufw-before.rules`,
`secrets.example/` (empty secret files), `push-cube.sh` (a built country cube to the data volume over `ssh`, for the
highline explorer; no address or key in it; docs/deployment.md, section 10), `backup.sh` (`sqlite3 .backup` as uid
10001 + restic; at every end, also a failed one, `backup.json` and the healthchecks.io ping from an exit trap;
docs/deployment.md, "Backups"); `tests/test_deploy.py` checks the filter, the masking with Python's `re`, the
published ports, the metrics log format and groups, the firewall's bridges and the monitoring's units;
`tests/nginx_check.sh` (CI) runs the nginx and fail2ban files

## `deploy/monitoring/`

The monitoring of the public site (docs/monitoring.md the plan, docs/deployment.md section 15): `compose.yaml`
(project `findaline-monitoring`: VictoriaMetrics `127.0.0.1:8428`, Grafana `127.0.0.1:3000`, the socket proxy
`127.0.0.1:2375`, bridge `br-fal-mon`), `telegraf.conf` (Telegraf on the host since 2026-11-01: InfluxData's `.deb`,
`TELEGRAF_VERSION` and a sha256 per architecture in `vps.sh`, installed by `telegraf_install` (also called by the CI's
monitoring job) with the config in `/etc/telegraf/telegraf.conf` and the sandbox drop-in
`systemd/telegraf.service.d/findaline.conf`; it runs as the package's user `telegraf`, never a `DynamicUser` or a
container's uid: dbus-daemon refuses a uid without a user, and `systemd_units` then stops Telegraf), `grafana/`
(provisioning: data source, dashboards, alert rules, the ntfy contact point); on the host, as root: `facts.sh`
(fail2ban's counts, the disk image's holes with `image_holes` of the sourced `vps.sh`, pending updates →
`/var/lib/findaline-monitoring/facts.json`; `facts.sh check` runs `vps.sh check` → `check.json`), `heartbeat.sh` (the
site through nginx, then `HEARTBEAT_URL` of `/etc/findaline-monitoring.env`), `systemd/` (`findaline-facts`, `-check`,
`-heartbeat` services and timers, `@REPO@` replaced by `vps.sh`'s `monitoring` step, which also writes the env file,
Grafana's secrets `grafana_admin_password` and `ntfy_url` (uid 472) and `.env` (`DOCKER_GID`), then pulls and starts
the project (`--remove-orphans`) and installs Telegraf; `check_monitoring` in `vps.sh check`). Phase 3: VictoriaLogs
(`127.0.0.1:9428`, 30 days; distroless, so no healthcheck of its own: `vps.sh check` asks its `/health`, and
`disable: true` would break `up --wait`); Telegraf's `docker_log` (web, worker) and the tail of `findaline.error.log`
go only to VictoriaLogs (`namepass`/`namedrop` of the two `outputs.http`, the `/insert/jsonline` API) after a regex
processor masks addresses, `/s/<token>` and `/auth/...?<query>`; Grafana's logs plugin is downloaded by `vps.sh`'s
`grafana_plugins` (version and sha256 pinned there) into `/var/lib/findaline-grafana-plugins`, mounted read-only as
`GF_PATHS_PLUGINS` (Grafana's preinstall stays off: it would fetch default apps too); `ssh-login.sh` →
`/usr/local/sbin/findaline-ssh-login` and `session optional pam_exec.so quiet` in `/etc/pam.d/sshd` (D4: ntfy from
`secrets/ntfy_url`, a detached `curl -m 5`, `ssh.json` under `flock`, always exit 0)
