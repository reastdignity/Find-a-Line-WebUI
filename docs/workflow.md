# Working on this repository

The full text of what CLAUDE.md sums up in a few lines: the documents, the environment, this PC and the conventions.
Moved out of CLAUDE.md on 2026-11-12; CLAUDE.md is loaded into every session, this file is read when a step needs it
(finishing a task, the test lock's modes).

## The documents

Finds possible highlines in elevation data: anchors on steep pixels, every pair checked for clearance under the
webbing, results shown on an interactive Leaflet map. User-facing docs: [README.md](README.md) (reference),
[setup-for-regular-folk.md](setup-for-regular-folk.md) (step-by-step guide) and
[docs/deployment.md](docs/deployment.md) (the public site on a VPS with Ubuntu 26.04, nginx, certbot and fail2ban on
the host: SSH, firewall, OAuth, backups, checks; keep it in step with `deploy/` (`deploy/vps.sh` runs its commands),
compose.yaml and `tests/nginx_check.sh`). Plans, decisions already made, their order and open checks:
[docs/roadmap.md](docs/roadmap.md); read it before proposing a design. Where the time and memory of a search go, the
worker's slots and what was measured and decided about speed: [docs/performance.md](docs/performance.md). The
monitoring of the VPS and the app (phases 1 to 4 built: `deploy/monitoring/`, `metrics.py`, `servicecounts.py`):
[docs/monitoring.md](docs/monitoring.md).

## Environment and tests

- Python 3.12+ (scipy 1.18 needs it); `.python-version` names 3.15, the version CI and the image run, so uv builds
  a new `.venv` on it and rebuilds one made on another version at its next `uv sync` or `uv run` (another
  interpreter: `--python <version>`; a worktree reads its own copy of the file, never the main checkout's).
  Dependencies in `pyproject.toml`, pinned in `uv.lock` (`uv sync`,
  `uv run findaline.py ...`; the user's `.venv` is git-ignored). For a session environment outside the repo:
  `UV_PROJECT_ENVIRONMENT=<dir> uv sync --frozen` (uv itself can be pip-installed into any venv: `python -m uv`).
  After changing dependencies run `uv lock` and the full regression set.
- Tests: `pytest` (offline: synthetic canyon + Żabi Koń clip in `tests/data`, units, the viewer against Python, the
  web app; about 1780 tests, 36-48 min in one process on this PC, measured 2026-11-13) and
  `python tests/regression.py` (real searches, see docs/regression-tests.md; its temporary folder is removed unless a
  test differs or `--keep`). `tests/test_viewer.py` is skipped without Node and `npm install` in `viewer/`,
  `tests/test_area_download_tui.py` without the group `tui` (`uv sync --group tui`; CI has it), five tests without the
  group `ui`. Failures that are known and not a regression (five float-exact kernel and warp tests on macOS):
  [docs/known-bugs.md](docs/known-bugs.md).
- The suite in parallel processes (pytest-xdist, a dev dependency): `pytest -n 8 --dist loadfile` runs each test file
  whole on one worker, in its order, so module fixtures are built once per file as in one process. Under the test lock
  (`tools/test_lock.py run -- <venv python> -m pytest`) a full run gets this by itself: 4 workers in shared mode, 8
  with `--heavy` or `--exclusive`, 3 threads of numba, OpenMP, BLAS and GDAL each; the lock prints a line saying so,
  `-n 0` asks for a serial full run, an own `-n` is kept, and a pytest of chosen files stays serial. Its kind in the
  lock's history and the lock monitor is `pytest-all-xdist` (serial full runs stay `pytest-all`). Measured on
  2026-11-13 (24 cores, not exclusive): 4 x 3 about 640 s and 8 GB, 8 x 3 304-368 s and 9.4-9.8 GB, against 2870 s
  serial; at 8 workers and more `tests/test_web.py` alone (250-310 s) sets the floor. CI runs `-n 4` with 2 threads.
  `tools/test_times.py` reads the JUnit files of runs (`--junitxml`): seconds per file and test, and `compare A B` id
  by id (a serial and a parallel run write the same ids).
- Before adding a dependency, check the current docs of the version that gets installed (Starlette 1.x: no
  `add_event_handler`, use `lifespan`; its TestClient wants `httpx2`, not `httpx`) and run the tests with deprecation
  warnings visible.

## This PC

- **Pipes and heredocs**: piping the script's output into `head` kills it before the map is saved. Complex multi-line
  edits are safer as a Python script written to the scratchpad than as a bash heredoc.
- **Shell on this PC**: `cat > file` without a here-document waits for input forever; nested quotes in
  `python - <<EOF` scripts break easily (write the script with the Write tool instead; a Python string with `\n`
  written through a heredoc can land in the file as a real line break). A script of a session run through the Bash
  tool has its output in a pipe, so in cp1250: a "²" or "→" stops it with a `UnicodeEncodeError`
  (`PYTHONIOENCODING=utf-8` in front of it, or `progress.utf8_output()`). Headless Edge started from the Bash tool
  (Git Bash) prints an empty page: run pytest's browser tests (and anything else starting Edge) from PowerShell. Stop
  only test browsers: filter `msedge.exe` by the `--user-data-dir` of the test (PowerShell
  `Get-CimInstance Win32_Process`), never all Edge processes of the user.

## Conventions

- Code, comments, docs and commit messages in English; conversation with the user and reports in English too (the
  user's word of 2026-11-05; Polish before that).
- Match the existing style (docstrings, comment density). Commit messages end with the `Co-Authored-By` line.
- One branch per task, started from the current `main` and named after it (e.g. `cliff-angles`, `source-austria`);
  never commit to `main` directly. Parallel agents each work in their own worktree (`.claude/worktrees/<task>`,
  `git worktree add`), so they never share a checkout. A finished task goes into `main` as one commit, its commits
  kept under a tag (the user's default since 2026-11-01): an annotated tag `history/<branch>` on the task's branch
  (its commits stay reachable, `git log <base>..history/<branch>`, and hashes named in the docs still resolve);
  `git merge --squash <branch>` on a new branch from the current `main` in its own worktree (conflicts three-way
  against the merge base, long rows of CLAUDE.md and README word by word; `viewer/dist` rebuilt when either side
  changed `viewer/src` or `locales/`); one commit whose message sums the task up, states the stored-data decisions of
  its commits and lists them (hash and subject) with the tag's name, its files naming only commits of `main`'s history
  or the tag; the full checks on that commit, then `main` fast-forwarded to it. A branch of one commit is rebased onto
  `main` and fast-forwarded (nothing to squash, no tag). Then the task's branches and worktrees are deleted; the tag
  stays. Nothing is pushed unless the user asks; pushing `main` pushes its new `history/*` tags too.
- Parallel tasks share the data folder and the cores: downloads may overlap; tests, builds and searches run under
  `tools/test_lock.py run` (from the main checkout's path; `--timeout` for anything that may hang; `--expect S` for a
  new command that is short, so it may use slots left free while an exclusive one waits; `--first` only with the
  user's explicit permission). The user's state in the lock says whether they are using the PC (the test lock page,
  `tools/test_lock_page.py`, or `tools/test_lock.py state`): while it is `busy` an exclusive or heavy command waits,
  while it is `heavy-ok` an exclusive one waits and a heavy one starts tamed (below the normal priority, at most 16
  threads), shared ones keep running below the normal priority in both, while it is `quiet` every new command waits,
  and that waiting does not count toward `--wait`; so agents queue their measurements and whole-band runs and let them
  wait, and no longer ask the user whether the PC is free. Shared (the default, below the normal priority) is enough
  for results compared by value or checksum: `pytest`, `npm run build`, `tests/regression.py` read for its checksums,
  small searches. `--heavy` for big runs that measure nothing: production `country run`s, large searches or
  `run_batch` compared by checksum, the CI replay in Docker Desktop (with `--resource docker`); a new one with
  `--memory GB` (its peak until the history knows it; the RAM guard holds a shared or heavy command whose peak does
  not fit). `--exclusive` for anything whose seconds or memory are read: times (the regression's recorded seconds,
  `tools/perf_*.py`), memory (`--tracemalloc`), tiled areas compared without a fixed `--tile-size`. `--resource data`
  for changes of the real data folder (`cache update`, `osm update`, migrations), `--resource docker` for test stacks,
  `--resource opentopo` for calls with an OpenTopography key. Two tasks touching the same "Things that must stay in
  sync" pair will conflict: split such work differently.
- Generated data (`cache/`, `runs/`, `work/`, `jobs.sqlite`, `findaline_map.html`) is git-ignored. The app has many
  potential users (the public site of stage 4): for every change of stored data (cache layout, runs, SQLite databases)
  decide explicitly whether it gets an automatic migration (SQLite schema versions with `PRAGMA user_version`) or
  none, and state the decision in the commit message.
- Private files of the user (drafts of e-mails to providers, notes, exports): the `local/` folder at the root of the
  main checkout, git-ignored (`/local/` in `.gitignore`, and in `.git/info/exclude` until `new-sources` reaches
  `main`), never committed; worktrees have their own (empty) `local/`. Drafts go to `local/mail-drafts.md` (one
  section per recipient: address, subject, status, text).
- Temporary files of a session go into its scratchpad, never straight into the system's temporary folder; when its
  task ends it deletes its large data there (data folders, venvs, captures), results the user needs moved to `local/`
  first. `tools/clean_temp.py` removes what tests and ended sessions left (270 GB had piled up by 2026-11-03).
- Libraries first: before writing an own implementation, look for a popular, maintained library (current version,
  release cadence, known CVEs) and present a comparison to the user, who decides. Own code stays only where libraries
  fit worse, with the reason recorded (docs/roadmap.md, "Stage 4").
