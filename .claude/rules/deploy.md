---
paths:
  - "Dockerfile"
  - "compose.yaml"
  - ".dockerignore"
  - "deploy/**"
  - ".github/workflows/**"
  - "tests/nginx_check.sh"
  - "tests/test_deploy.py"
---
# Docker, the VPS and CI

What each part holds: docs/code-map/deploy.md; the steps on the server: docs/deployment.md. `.claude/rules/metrics.md`
loads with `deploy/monitoring/` too.

## Running it

- CI: `.github/workflows/ci.yml` (GitHub Actions: `pytest` on Linux and Windows (Windows in three jobs: the 3D page
  tests serially, the ring's alone, the rest on 4 workers; a new `tests/test_view3d*.py` file joins the serial job by
  its name; never on workers there: 18 of 31 ran into 900 s on 4, 2026-11-14; on Linux the runner's unused SDKs
  removed first: `tests/test_public.py` needs the public limits' 20 GB free; `--durations=25` lists the slowest
  tests), `pip-audit` and `npm audit`, and `docker`: the image built, a search and both services run in it,
  `docker compose config`, the source address of the published port, nginx and fail2ban through
  `tests/nginx_check.sh`); keep its steps in line with these commands.
- Docker (the public site): `Dockerfile` (uv build stage, python-slim runtime without uv, uid 10001; base images
  pinned by digest, how to update them is in its header) and `compose.yaml` (`web --public` and `worker --public`, one
  data volume at `/data`, read-only root, `/tmp` tmpfs, settings in `findaline.env`, secrets in `secrets/`, resources
  in `.env`). Docker Desktop is installed on the dev PC but not on PATH
  (`export PATH="/c/Users/Krzysiek/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"` in Git Bash); test
  stacks get their own project name (`docker compose -p <name>`), settings and dummy secrets outside the repo
  (`--project-directory <scratch>` with an override setting `build.context` to the checkout), and are removed
  afterwards (`down -v`). A missing system library shows only at run time: after changing dependencies or the base
  image, `ldd` every `.so` of the venv in the image (numba's optional `omppool`/`tbbpool` may stay unresolved). `web`
  publishes `127.0.0.1:${WEB_PORT:-8765}` only (test stacks: another `WEB_PORT`, 8765 is often the user's local app);
  the app trusts `X-Forwarded-For` from the gateway of its network `web` (`172.30.0.1`, fixed in compose.yaml:
  connections to a published port arrive from it). `tests/nginx_check.sh` installs `deploy/nginx` and
  `deploy/fail2ban` with the functions of `deploy/vps.sh` (sourced: `nginx_files`, `fail2ban_files`, also `ufw_files`
  on ufw's stock rules) on Ubuntu 26.04's packages and checks nginx in front of the running web service
  (`docker run --rm --network <project>_web -v <checkout>:/src:ro ubuntu:26.04@<digest of ci.yml> bash /src/tests/nginx_check.sh`;
  Ubuntu's `nginx.conf` already sets `server_tokens`, `ssl_protocols` and `gzip` in its `http` block: such directives
  go per server, never into `conf.d/`). Anything written at run time must go to the data folder or `/tmp` (`HOME`,
  `NUMBA_CACHE_DIR`, `MPLCONFIGDIR` point into `/data/home`); a file the image needs at run time must not be excluded
  by `.dockerignore` (it keeps only the scripts and `viewer/dist`).

## The project's data server (`deploy/mirror/`, docs/mirror-hosting/spec.md)

- Not on the VPS: the home server, two projects (`findaline-mirror`: one service, no port; `findaline-mirror-publish`:
  the SFTP door in a Husarnet sidecar's namespace, no port either). The repository names its host
  (`mirror.findaline.lukawski.org`) and SWAG and Unraid as setups it supports, never a fact of the user's own
  server (platform, uplink, addresses, other services, power).
- Must stay in step (`tests/test_mirror_deploy.py`, `tests/test_mirror_pairs.py`): the base images' digests of
  `Dockerfile`, `test/*`, `publish/Dockerfile`, `test/sshclient.Dockerfile` and `mirror_check.sh`'s `CURL_IMAGE`; the
  served patterns and `grid_tile_name`, `res_name`, the publish tool's layout and `DATASET_NAME`; the limits of
  `nginx.conf` and the client's `net.HOST_SLOTS_OF`/`HOST_RATES_OF` (at most half of one visitor's); the log's keys
  `t s b rt ds a lim v` and 14 days, `mirror_publish.py stats`, the privacy texts (spec section 7, README, the landing
  page, `mirror_check.sh`'s `PRIVACY`, CLAUDE.md's exception): another key or period changes the texts, with the
  user's yes; the `$mirror_version` map, `mirror_publish.CLIENT_VERSION` and pyproject's version form; the door's
  rclone settings in `deploy/mirror/README.md` (`shell_type`, `hashes`, `sha256sum_command`, `known_hosts_file`, the
  top `/mirror`) and `mirror_publish.NO_SHA256`'s text.
- The door (`publish/`, U68): `sftp` runs in the namespace of the sidecar `husarnet` (`network_mode:
  service:husarnet`). The check never runs the real sidecar: `test/compose.door-check.yaml` replaces it with a
  stand-in (`test/door-standin.Dockerfile`: socat holds a tun `hnet0` with D36's fc94 address, gone with the process
  like the daemon's) by `!override`/`!reset` (its `build` too) and keeps its `ports`, `networks` and sysctl (D29 reads
  the ports; D37 the namespace's IPv6 switch, the sysctl's presence only the static test). sftp's healthcheck judges
  a lost namespace by `hnet0` by name, never "anything but lo" (fallback tunnel devices stay: D35, D38). A change to
  the sidecar's network, its interface or the door's namespace changes the stand-in, D28/D29/D34-D38 and the static
  test together. The code goes only to the
  CLI's `husarnet claim`, never into the daemon's environment; its status needs no token. `publish/husarnet.sh`
  reads the nightly daemon's (2.0.349, U80) status keys with jq; `_daemon_status` in tests/test_mirror_deploy.py
  copies them: a new HUSARNET_VERSION changes both, after the door's real-daemon checks. The image is built by
  `publish/husarnet-sidecar.Dockerfile` (Debian digest, key fingerprint, nightly version), updated with the door's
  base; its daemon is never started in CI.
- SWAG is attached by `docker network connect findaline-mirror_mirror swag`, again after every SWAG update (the
  monthly item of docs/deployment.md). `mirror_check.sh --self-test` takes about 90 min: `--timeout 7200` under the lock;
  in CI it is the job `mirror` of its own workflow `.github/workflows/mirror.yml` (when the mirror's files, the
  script, `tests/test_mirror_deploy.py` or the workflow change, and by hand; 150 minutes).
- Test stacks never ask the real data server: CI's docker job appends `FINDALINE_MIRROR_URL=off` to its findaline.env
  (a local replay copies that step), the tests' processes get `off` from conftest; the VPS leaves it unset. CI's
  rclone (test parts, by sha256) stays at `mirror_publish.MIN_VERSION` or newer; no `RCLONE_*` name in its step.
