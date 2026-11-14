---
paths:
  - "tests/test_web.py"
  - "tests/test_viewer.py"
  - "tests/test_view3d*.py"
  - "tests/test_shell_c*.py"
  - "tests/test_layout.py"
  - "tests/test_country_web.py"
  - "tests/test_coverage_page.py"
  - "tests/test_test_lock_page.py"
---
# Tests that start a browser

Why browser tests were unstable and how they wait now. Headless Edge prints an empty page when started from Git Bash:
run them from PowerShell (CLAUDE.md, "This PC").

## Pitfalls

- **Unstable browser tests** (2026-11-05, `history/flaky-tests`; the headless-Edge harness:
  `msedge --headless --dump-dom --virtual-time-budget=…` against a thread-hosted uvicorn): (1) the page is live from
  its synchronous first render, but Preact runs `useEffect` only after the next frame (or ~35 ms of page time): a
  subscription that must not miss an event (`hashchange` in `AppC`, once added after the paint, so a "New search"
  clicked at once changed the hash unseen and the page stayed on Home) goes in `useLayoutEffect`, and a test that
  reads state an effect sets waits for it (`ProfileDock`'s "Computing…" before its chart: `[aria-busy]`); the same
  hashchange-in-`useEffect` pattern is left in `map/main.tsx`, `FavouritesPage.tsx`, `LayerPage.tsx` and
  `KitResult.tsx`, which no test hits. (2) Virtual time moves on only while the page is idle, and
  `requestAnimationFrame` runs in real time: a page that animates all the time (the coverage globe's spin, on a busy
  machine) freezes it with every `setTimeout`-polled wait, so the test hangs until msedge's 180 s (await such a view
  with a `MutationObserver` and leave it); a page whose first frame never comes inside a plain timer's budget (the 3D
  view's mesh build and the ring's rAF-scheduled tile queue) is waited for by `test_view3d.UNTIL_JS`: polls that each
  span one of the browser's own animation frames while a small file keeps loading (which holds the virtual time) and a
  1 virtual-ms guard timer bounds what leaks between two loads, so a wait counts frames and never virtual time (a
  pause of t ms is t / 100 frames; the page's and a poll's frame callbacks run in the same frame), with
  `VIRTUAL_BUDGET` only a ceiling and `EDGE_SECONDS` the real-time hang guard (`FINDALINE_EDGE_SECONDS`: CI's own per
  job); "settled" means ten polls with no frame drawn and none pending. (3) A `--user-data-dir` under a long path
  (pytest's `--basetemp` in a deep scratchpad) makes Edge exit in 0.1 s with an empty DOM (the profile passes
  MAX_PATH): keep `--basetemp` short (`C:\fal\<name>`). (4) A
  test that measures a rate limiter takes the time each granted permit carries (`SQLiteBucket.put`,
  `tests/test_rates.py`), never a clock read after the call returned (a descheduled thread read 164 ms for 100 ms
  turns), and `net.rate_turn`/`osm._nominatim_turn` keep `timeout=0`; a limiter whose keys expire on the real clock
  gets a clock the test moves (`test_rate_limiters_forget`); a reader of an event stream stops at the line it needs
  (the worker's), not at the first keep-alive; a loop that claims jobs stops only after a claim begun with every job
  ready. (5) State a test's code leaves in the process (module globals, a module fixture running `country.run`
  in-process) shows only in the full suite's order: run a pair of files in that order before blaming the test
  (`pytest tests/test_band_study.py tests/test_count_mode.py`), and fix the code that leaves the state
  (`progress.bars()`), not the test that meets it. (6) Every 3D page test (`tests/test_view3d*.py`, tag
  `history/flaky-3d2`) waits through `test_view3d.UNTIL_JS` (`until`, `settledOn`; `_with_until`), never through a
  copy of its own: under `--dump-dom` animation frames come in real time while timers run in virtual time, so a wait
  counted in virtual ms, or "a virtual second without a frame", let a frame the page had asked for come later (up to
  6.7 virtual seconds measured at load). A synthetic drag starts only after the page settled: the handles are placed
  when a frame is drawn and trail the line by one frame, and a drag from their earlier place lands elsewhere
  (`test_view3d_only_valid_lines` passed only while a frame lagged). `test_view3d_lines_from_a_point[phone]` missed
  once in 18 runs under load (the page's first script, `stubs.js`, apparently never ran): add access logging to the
  test server's static files if it recurs.
- **Full runs are parallel** (pytest-xdist under the test lock and in CI, 2026-11-14): a module's tests stay on one
  worker in their order, but which modules share a process and come first changes from run to run, and the machine is
  loaded: a test that waits a fixed time for a page, or reads a rate limiter's clock, fails now and then (waits for
  the event that ends what it measures; limiters on a held clock: `test_public._hold_rate_clock`). Each worker's
  basetemp is `<basetemp>/popen-gwN`: keep `--basetemp` short (point 3). A test that starts a nested pytest drops
  `PYTEST_XDIST_WORKER`/`_COUNT` from the child's environment.
- **A run of the Żabi Koń clip** comes from the fixtures `clip_data`, `clip_run`, `big_clip` or
  `clip_runs.data_copy`, never from a module's own `findaline.py` call: each distinct search runs once per session
  (shared by the workers) and every module gets its own copy of the data folder (`tests/clip_runs.py`).
