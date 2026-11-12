# Find-a-Line

Finds possible highlines in elevation data: anchors on steep pixels, every pair checked for clearance under
the webbing, results on an interactive Leaflet map. A command line (`findaline.py`), a local web app
(`findaline.py web`) and a public site (Docker on a VPS: `web --public`, `worker --public`).

## Docs
Read the section you need, not the whole file (several are over 200 KB).
- [README.md](README.md): the user's reference (options, data sources, limits of the web app);
  [setup-for-regular-folk.md](setup-for-regular-folk.md): the step-by-step guide.
- [docs/roadmap.md](docs/roadmap.md): plans, decisions already made, their order, open checks. Before
  proposing a design read "Decisions" and the section of your area.
- [docs/regression-tests.md](docs/regression-tests.md): how a change is verified.
  [docs/known-bugs.md](docs/known-bugs.md): failures and findings that are known and not a regression.
- [docs/performance.md](docs/performance.md): where time and memory go, what was measured and decided.
- [docs/deployment.md](docs/deployment.md) (the VPS; kept in step with `deploy/`, compose.yaml and
  `tests/nginx_check.sh`), [docs/monitoring.md](docs/monitoring.md).
- [docs/data-sources.md](docs/data-sources.md) (adding a source), docs/3d-view-contract.md,
  docs/country-precompute/contract.md, docs/truth-check.md.
- docs/code-map/: what each module and tool holds, in detail, one file per area (table below).
- [docs/workflow.md](docs/workflow.md): the environment, finishing a task (squash, tag), the test lock's
  modes and the conventions, in full.

## Commands
- Python 3.12+. `uv sync`, `uv run findaline.py ...`; `--help` lists everything. After changing
  dependencies: `uv lock` and the full regression set.
- `pytest`: offline. The viewer's tests need Node and `npm install` in `viewer/`, the TUI's
  `uv sync --group tui`; without them they are skipped.
- `python tests/regression.py`: real searches (docs/regression-tests.md).
- After changing `viewer/src` or `locales/`: `cd viewer; npm run check; npm run build` (under the test
  lock: `node build.mjs`), and commit `viewer/dist`.
- A search: `python findaline.py --lat 50.1559508 --lon 19.7562722 --no-plot --yes`. `--no-plot` always
  without a desktop session (the matplotlib window blocks); `--yes` skips the questions.
- The web app for tests: `python findaline.py web --no-browser --port 8799 --data-dir <scratch>`, in the
  background.
- Long runs in the background, waiting for the notification. Tests and searches one after another.

## Where things are
| Area | Files | Rule | Detail in docs/code-map/ |
| --- | --- | --- | --- |
| The search (steps 1-5), options, areas, grids | `findaline.py`, `params.py`, `search.py`, `area.py`, `grid.py`, `progress.py`, `warmup.py` | search-pipeline | search.md |
| Anchors and the line test (numba kernels) | `helpers.py`, `linesearch.py`, `lineprofiles.py`, `terrain.py`, `obstacles.py`, `sag.py` | line-test | search.md |
| A run's files, grouping, terrain statistics | `mapping.py`, `grouping.py`, `runs.py`, `saving.py`, `hypsometry.py` | run-files | search.md |
| Data sources, cache, mosaic, filling | `sources/`, `cache.py`, `update.py`, `orthophoto.py` | sources, providers | sources.md |
| OSM, coastline | `osm.py`, `osmextract.py`, `coast.py` | osm | sources.md |
| Web app, job queue, accounts, limits, texts | `web.py`, `jobs.py`, `accounts.py`, `audit.py`, `settings.py`, `messages.py`, `locales/` | web-app | web.md |
| Metrics, monitoring | `metrics.py`, `servicecounts.py`, `deploy/monitoring/` | metrics | web.md, deploy.md |
| Viewer (TypeScript, Preact, Leaflet), 3D view | `viewer/src/`, `viewer/dist/` (committed) | viewer, view3d, browser-tests | viewer.md |
| Coverage map | `viewer/src/coverage/`, `tools/coverage_*.py` | coverage-map | viewer.md, tools.md |
| Country layer | `country.py`, `countcube.py`, `countkernels.py`, `relief.py` | country-layer | country.md |
| Docker, the VPS, CI | `Dockerfile`, `compose.yaml`, `deploy/`, `.github/workflows/ci.yml` | deploy | deploy.md |
| Tools run by hand | `tools/` (each tool's docstring says what it does) | the rule of its area | tools.md |

## Rules of an area
`.claude/rules/<name>.md` hold what must stay in sync in an area and its pitfalls. Claude Code puts a rule
into context by itself when a file it names is read or edited (a worktree's copy of the file too), not
before. Planning without opening those files, or briefing a subagent: read the rule, or name it in the brief.

## Always
- Results are pinned: the regression set compares the counts and the sha256 of `lines.csv`. A change that
  should not change results leaves every checksum as it was; one that should says so and re-baselines.
- Kernels may pass too much, never too little; `helpers.evaluate_line` decides. Results never depend on
  the number of threads.
- The web process does no search work and never imports `search` or `numba`: heavy work and network only
  in the worker.
- Stored data (cache layout, runs, SQLite databases): every change decides "automatic migration" or
  "none" and states it in the commit message.
- Keys, tokens and personal data never in the repository, a run's files, a printed text or a log.
- Before adding a dependency: the current docs of the version that gets installed, and the tests with
  deprecation warnings visible.
- Libraries first: before an own implementation look for a popular, maintained library and present a
  comparison; the user decides.

## This PC (Windows, Git Bash and PowerShell)
- Never pipe a search's output into `head`: it kills the search before the map is saved.
- Multi-line scripts: write the file with the Write tool, not a heredoc; `cat > file` without a
  here-document waits forever.
- A script run through the Bash tool prints in cp1250: `PYTHONIOENCODING=utf-8` in front of it.
- Headless Edge started from Git Bash prints an empty page: browser tests from PowerShell. Stop only test
  browsers (`msedge.exe` filtered by the test's `--user-data-dir`), never all of the user's.
- pytest's `--basetemp` short (`C:\fal\<name>`): a long path makes Edge exit at once.
- Docker Desktop is not on PATH:
  `export PATH="/c/Users/Krzysiek/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"`.

## Verifying changes
- Follow [docs/regression-tests.md](docs/regression-tests.md): run the affected locations and compare with the expected numbers.
- Speed or memory: before and after with the tools of docs/performance.md, one search at a time, and show
  that the results are the same.
- Viewer or page changes: `tests/test_viewer.py`, then a visual review with `tools/ui_shots.py` on the
  desktop and both phones before calling them done.
- A new source or download path: `tools/check_source.py`, `findaline.py sources check <id>`, on an empty
  scratch cache.
- Anchors, the line test or the obstacle rule: also the truth check (docs/truth-check.md).

## Conventions
- Code, comments, docs, commit messages and conversation in English. Match the existing style. Commit
  messages end with the `Co-Authored-By` line.
- One branch per task from the current `main`, in its own worktree (`.claude/worktrees/<task>`); never
  commit to `main` directly. Nothing is pushed unless the user asks.
- A finished task goes into `main` as one squash commit, its commits kept under the tag
  `history/<branch>`; a branch of one commit is rebased and fast-forwarded. Steps: docs/workflow.md.
- Tests, builds and searches run under `tools/test_lock.py run -- <command>` (from the main checkout's
  path). Shared by default; `--heavy` for big runs that measure nothing; `--exclusive` when seconds or
  memory are read; `--resource data|docker|opentopo`; `--first` only with the user's permission. The
  user's state in the lock decides when heavy and exclusive commands start: queue them and let them wait.
- Generated data (`cache/`, `runs/`, `work/`, `jobs.sqlite`) is git-ignored. The user's private files:
  `local/` of the main checkout, never committed.
- Temporary files in the session's scratchpad; large data there deleted when the task ends.
- Where knowledge goes: what a module does, into its docstring; a decision or a measurement, into `docs/`
  and the commit message; something a later change must keep in step or must not do, one short bullet in
  the area's rule; this file only what every session needs. `tests/test_instructions.py` keeps the sizes.
