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
highline explorer: cube.json, area.geojson and the build folder cube.json names (`arrays`, checked against
`countcube.BUILD_PATTERN`; a cube built before: the fixed-name arrays beside cube.json), extracted beside the old cube,
swapped in, every copied file's sha256 compared; no address or key in it; docs/deployment.md, section 10), `backup.sh` (`sqlite3 .backup` as uid
10001 + restic; at every end, also a failed one, `backup.json` and the healthchecks.io ping from an exit trap;
docs/deployment.md, "Backups"); `tests/test_deploy.py` checks the filter, the masking with Python's `re`, the
published ports, the metrics log format and groups, the firewall's bridges and the monitoring's units;
`tests/nginx_check.sh` (CI) runs the nginx and fail2ban files

## `deploy/mirror/`

The project's data server ("the mirror", docs/mirror-hosting/spec.md; runs on the home server, never on the VPS;
install and checks: its `README.md`). Two compose projects: `findaline-mirror` (`compose.yaml`: one service `files`
built by `Dockerfile` from nginx's unprivileged image pinned by digest, `nginx.conf` (the served patterns of `/v1/`,
the limits per class keyed on `X-Real-IP`, the JSON log of eight keys, one file a UTC day), `start.sh` (entry point
`serve|check|health|cleanup`: the trusted list, the landing page with `MIRROR_CONTACT`, the log's day switch, the
hourly cleanup by 14 days and `LOG_CAP_BYTES`, 2 GB, the heartbeat), `landing/index.html`, `robots.txt`; no port, one
internal network that SWAG joins by `docker network connect findaline-mirror_mirror swag`;
`swag/findaline-mirror.subdomain.conf` for SWAG; `compose.test.yaml` a stand-in for SWAG on `127.0.0.1:8790`; `test/`
the check script's fixture, stand-in and door-check files) and `findaline-mirror-publish` (`publish/`: the SFTP door,
Alpine + OpenSSH with a command gate `gate.sh`, in the network namespace of a Husarnet sidecar `husarnet`, the
image `husarnet/husarnet` pinned by digest, entry point and healthcheck `husarnet.sh`: no published port, reached
over the door's own Husarnet network; the check script replaces the sidecar with a stand-in). `tests/mirror_check.sh` runs every
behaviour and, with `--self-test`, each switched off (CI's job `mirror` of its own workflow
`.github/workflows/mirror.yml`: when the mirror's files, the script, its static test or the workflow change, and by
hand; 150 minutes; `--live <url>` against a running mirror: LV15's cap check from 1 MB tiles, LV17's held
downloads from 16 MB);
`tests/test_mirror_deploy.py` reads it all statically; `tests/test_mirror_pairs.py` the pairs with the client and the
publish tool.

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
`secrets/ntfy_url`, a detached `curl -m 5`, `ssh.json` under `flock`, always exit 0). The data server (C7, C8):
Telegraf's `mirror_http_response` (its `/v1/datasets.json` every minute) and `mirror_x509_cert`, measurements of their
own beside the site's, the rules `c7-mirror-down` and `c8-mirror-certificate`, a row of *Site* and two Overview tiles
