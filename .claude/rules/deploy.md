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

- CI: `.github/workflows/ci.yml` (GitHub Actions: `pytest` on Linux and Windows (on Linux the runner's unused SDKs
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
