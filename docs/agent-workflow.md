# Planned work with agents: scope, contract, workers, reviewers

The general rule for work larger than a few edits (the user's decision of 2026-11-14, after the line-volume task of
2026-11-10 to 2026-11-14, where it was worked out). One session plans, delegates and reviews; worker agents build or
measure; reviewer agents check; the user decides. The session itself does not do the heavy coding or research: its
output is the scope, the plan, the briefs, the reviews and the reports. Small fixes found in a review (a few lines)
it may make itself. The mechanics of branches, tags and the test lock are in [workflow.md](workflow.md).

## 1. Scope first, with the user's answers as design guides
- **Restate the goal** in a few lines and ask what the session must deliver (decisions, built parts, a
  specification). Show the plan with every option before asking which scope (plan mode, `ExitPlanMode`).
- **Ask, then record.** Questions go to the user in batches, each with its options, what each costs (Claude effort
  low / medium / high and machine load, never hours) and a recommendation first. Many items at once: an interactive
  page (an idea board) where the user marks keep / maybe / drop; a few: one dialog.
- **The user's words are the design guides.** Every statement of the user goes, verbatim and dated, into
  `local/<task>-<date>/user-inputs.md` (private, never committed), with the session's reading beside it when the
  words need one. It is the yardstick for everything after: where a report, a specification, a reviewer or an agent
  differs from the user's words, the user's words hold. Briefs and specifications quote them.
- **Gates.** The work runs in phases that end at a gate where the user decides: evidence (effects with numbers and
  targets), ideas (wide, then pruned), evaluation (measured alternatives, mock-ups), build, specification, close.
  Each gate's decisions get an id, the options, what was measured, the recommendation and the user's answer
  (`local/<task>-<date>/gate<n>/decisions.json`). Parked ideas go to the roadmap, not evaluated.
- **Measure before a rule.** A guessed threshold becomes a measuring tool first; the user picks from the numbers,
  with the obvious alternatives measured too.
- **UI:** an interactive mock-up first (an artifact page), one change per publish, the user's answers recorded; code
  only after the user's "ok"; the built page's screenshots (desktop and both phones, light and dark) go to the user
  before it goes into `main`.
- **The plan** names a definition of done (what is delivered, how each part is verified) and a short list of
  "assumptions to correct when you approve": the session's readings of the request that the user can fix in one word.
- **A specification** for what is decided but not built: complete enough that a later session's agents implement it
  without new decisions. Each solution: decision (with the user's words), behaviour, data (the stored-data decision),
  interfaces, files and the "must stay in step" pairs, screens, tests, acceptance numbers, waves, risks and rollout,
  and what still needs the user's word (options with a recommendation, never hidden). Where the task has a goal case,
  the specification shows the path to it, step by step, with predicted numbers marked as measured or estimated.
  Example: [line-volume/spec.md](line-volume/spec.md).

## 2. Contract and briefs
- **The contract** (`local/<task>-<date>/contract.md`, one per wave) has the table of agents: the work, the worktree
  and branch, the files each owns, the model and effort. It has the order and the gates. And it has the rules for
  all, written out so an agent needs nothing else:
  - Results are pinned; every commit message has the stored-data line and the `Co-Authored-By` line.
  - The area's rule (`.claude/rules/<area>.md`) is read before its files are touched, and its pairs are kept.
  - Everything that runs tests, builds or searches goes through the test lock from the main checkout. Workers use
    the shared lane or `--heavy`, never `--first` or `--exclusive`. A full pytest runs without `ESRI_API_KEY` in
    its environment (never printed); more than 30 skips means the viewer tests did not run; `--basetemp` is short
    (`C:\fal\<name>`) and removed at the end. Searches use `--no-plot --yes` and are never piped into `head`.
  - The user's `runs/`, the cache and the app on port 8765 are read-only. Scratch data goes in a folder of the
    agent's own (`C:\fal\<task>-<agent>`) with the cache linked by a junction, removed at the end with
    `cmd /c rmdir`, never through the link.
  - Private data: no coordinates of production cases, known highlines only as counts through the project's tools,
    keys and personal data never in a file, a text or a log.
  - No new dependency, no change outside the owned files: stop and report instead.
  - Commit on the own branch only. Never merge, never rebase a shared branch, never push, deploy or publish; workers
    use no artifact or database tools.
  - A progress file kept current; the stuck rule (section 3).
  - The report (the final message, at most about 120 lines): what changed (files, functions), the commits, the tests
    and their last lines, the stored-data line, every "must stay in step" pair touched, what was not done or not
    tested, every choice the brief does not settle, anything noticed outside the task. A measurement's report: the
    tables, how each number was made, what is indicative, what the agent re-derived to check itself.
- **A brief per agent** (`local/<task>-<date>/briefs/<agent>.md`): what to read (the rules of its area by name: an
  agent gets a rule only when it opens one of its files), the user's decisions it builds (quoted, "do not widen
  them"), what must hold (each with a test), what to measure, tests and builds, docs, commits, its milestones with an
  expected duration (the stuck rule needs both), and the report.
- **One worktree per agent**, from `main` or the task's branch: `git worktree add .claude/worktrees/<name> -b
  <branch> <base>`, its exit status checked, never piped. `npm ci` in the worktree's `viewer` when needed, never
  through a junction. Two agents never own the same file in one wave.

## 3. Workers
- **Models:** Opus 5.5 by default, the effort chosen per task by the session (medium; high where measurements have
  pitfalls or the change touches the search, stored data or a "must stay in step" pair). Fable only where the
  session judges it necessary (a hard design core). An agent may start subagents of its own, on Opus 5.5 at most,
  for clearly separable work, and says what it delegated.
- **Progress and limits:** each agent keeps `local/<task>-<date>/<agent>/progress.md` current and commits small. An
  agent stopped by a usage limit is resumed with `SendMessage` after the reset (not a new agent); its runs in the
  test lock survive it. Waiting in the lock is normal, not stuck. `SendMessage` resumes an agent on its own model: a
  dead agent of another model is replaced by a new agent given its notes, its worktree and its running processes.
- **Stuck** means one of four things: it says it cannot meet a point of its brief; it fails the review on the same
  point twice; it is at twice its expected time without a new milestone; it repeats a failing step three times.
  Cause in the brief or the environment: fix it and resume the same agent. Cause in capability: one replacement by
  Fable with the notes and the worktree; a second failure goes to the user with options. Every replacement is
  reported to the user with its cause.

## 4. Reviews before any merge
The steps after every hand-back: worker → scope reviewer, for a build also the code reviewer, for a change of a
screen also the design reviewer → the session's review → merge. The reviewers run in parallel. Each is a separate Opus agent that reads the output, never the
worker's report. A requirement "not met" or a finding "fix before merge" goes back to the same worker first.
- **Scope reviewer** (every task, builds, measurements and mock-ups): compares the contract, the brief, the
  specification and the user's words with the output itself (the branch's diff and files, a measurement's scripts
  and tables, a page). One row per requirement: met / partly / not met / not checkable, with file and line, a commit,
  a table row or a test's name as evidence; work outside the scope or the owned files; choices the sources do not
  settle; contradictions with the user's words; a one-line verdict. Its instructions: appendix A.
- **Code reviewer** (every build; Opus 5.5 at medium effort, high for the search, stored data or a "must stay in
  step" pair): correctness with a concrete failing input for each finding (confirmed by a run, or read only); a map
  of every changed function to the test that runs it ("no test" named); tests that do not test (pass with the change
  reverted, fixed waits, loosened assertions); a one-line verdict. Its instructions: appendix B. The project has no
  coverage tool; adding one is a new dependency (libraries compared, the user decides).
- **Design reviewer** (every change of a screen, of a text the user reads or of a style, and every mock-up; the
  user's decision of 2026-11-17): reads docs/PRODUCT.md, docs/DESIGN.md, the task's user's words, the screenshots
  before and after (desktop and both phones, light and dark) and the numbers of `tools/ui_metrics.py` and
  `tools/ui_walks.py` before and after, never the worker's report, and writes `<agent>/design-review.md` with its
  verdict ("conforms", "conforms with findings", "does not conform"). What it checks, what it writes and what it
  must not do: [design-review.md](design-review.md).
- **An independent reference** for the riskiest changes (a rule that drops results, a kernel): an agent writes its
  own reference from the brief's words before it reads the code, and compares results on a real search.
- **The session's review:** read the core of the diff, re-derive two or three numbers from the raw outputs, run the
  full pytest on the final tree itself, look at the screenshots, and write `local/<task>-<date>/<agent>/report.md`:
  the agent's report condensed, the reviewers' verdicts, the planner's review (what was checked, what was not).

## 5. Into `main`, and the close
- `main` moves only on the user's word, item by item (an "ok" on screenshots, a gate's answer). One squash commit per
  task with its commits under `history/<branch>` ([workflow.md](workflow.md)), the full pytest on that tree first.
  Nothing is pushed or deployed unless the user asks.
- A change that other sessions must act on (a default, a migration number, a cube's meaning): tell their sessions
  directly, or leave the note in memory when none is running.
- The close: roadmap (decisions, parked ideas), known bugs, the area's rules, a handoff in `local/<task>-<date>/`,
  memory updated, worktrees and scratch data removed (junctions with `cmd /c rmdir` first).

## 6. Reporting to the user
Plain, short English. The result first, then what is still running. Every number with its source; an estimate marked
as one. A failure stated as a failure, with what was done about it. One report per wave or hand-back; the user's
open choices as one list with a recommendation each, answerable with letters ("1 b, 2 a").

## Appendix A: the scope reviewer's instructions
Copy into `local/<task>-<date>/scope-review.md` and name the paths. The reviewer reads four things:
- the contract and the worker's brief (the scope);
- the specification sections the brief names, and the user's words;
- the rules the brief names;
- the output: the branch (`git log`, `git diff`, `git show <branch>:<path>`), or the measurement's folder.
It does not read the worker's report, its final message, or the conclusions in its progress file (the progress file
only to find where the outputs are). Evidence is a file and line, a commit, a table row or a test's name, never "the
worker says". It writes `<agent>/scope-review.md` (at most 150 lines):
1. a requirements table: every requirement of the brief and of the specification it builds, in the source's order,
   with the verdict and evidence; the contract's rules visible in the output (commit messages with the stored-data
   and Co-Authored-By lines, only owned files touched, no new dependency, texts in `locales/`, `viewer/dist`
   committed apart, the tests the brief asks for exist and assert what it says);
2. outside the scope: changes not asked for, each harmless, needed or a risk;
3. not settled by the sources: choices the worker took (names, bounds, texts, orders, defaults), marking those the
   user would want to see;
4. against the user's words: any contradiction with a quoted decision;
5. the verdict: "conforms", "conforms with gaps" (rows) or "does not conform" (rows).
Rules: it changes nothing. It may run one small test or script through the test lock to check a requirement, never a
full pytest or a long search. It judges against the sources, not its taste. Private data as in the contract: no
coordinates, known highlines only as counts, no key printed. Its final message (at most 40 lines): the verdict
line, the counts of rows by verdict, the rows that are not "met", and its file's path.

## Appendix B: the code reviewer's instructions
Copy into `local/<task>-<date>/code-review.md` and name the branch. The reviewer reads every changed source file in
full where it changed, and the callers and callees of what changed. It reads the brief only to know the intended
behaviour, and the rules of the touched areas and CLAUDE.md "Always". It does not read the worker's report. It
writes `<agent>/code-review.md`:
1. findings, most severe first: file and function, what goes wrong, a concrete input or sequence, the consequence,
   confirmed or read only; looking at edge cases (empty, zero, NaN, very large, negative, exact boundaries), error
   paths, state across a move, reload, resize or second call, threads, tiles and event order, cleanup, the "must
   stay in step" pairs, access rules and personal data, the keyboard and labels of new controls; no style findings;
2. a test map: each changed function or behaviour with the test that runs it and what it asserts, or "no test";
3. tests that do not test, and what each no longer protects;
4. the verdict: "no findings", "findings of low risk" or "fix before merge".
Rules: it changes nothing. To confirm a finding it may run one test, or a script or test of its own kept in the
task's private folder, through the test lock; never a full pytest or a long search. It judges correctness, not
taste: no finding without a failure it causes; a behaviour the user decided is not a finding. Private data as in
the contract; no key printed. Its final message (at most 40 lines): the verdict line, the findings in one line each
with confirmed or read only, the count of changed functions without a test, and its file's path.
