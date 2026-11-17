# The design reviewer's checklist

A design reviewer checks every change of a screen, of a text the user reads or of a style, and every mock-up,
beside the scope and code reviewers (docs/agent-workflow.md; DESIGN.md, R12). The user's decision of 2026-11-17 ("4. a"):
keep a fixed frame of scores, checks and the product's two users as the reviewer's checklist, with nothing installed.
The frame makes rounds comparable: the same scores and checks every time.

## What it reads

- [PRODUCT.md](PRODUCT.md) (the users, the aims, the principles) and [DESIGN.md](DESIGN.md) (the rules in force).
- The user's words of the task (`local/<task>-<date>/user-inputs.md`): where anything differs from them, they hold.
- The screenshots before and after, on the desktop and both phones, in the light and the dark theme
  (`tools/ui_shots.py`), and the measured numbers before and after (`tools/ui_metrics.py` on the pages the change
  touches, `tools/ui_walks.py` for the walks it touches).
- The source of the changed screens where a state is not pictured. Never the worker's report.

## The frame

**1. Ten usability heuristics** (Nielsen's ten), each scored 0 to 4: 0 missing or blocking, 1 a major problem,
2 works with clear problems, 3 good with small problems, 4 nothing to improve; "n/a" where the change does not touch
it. One line of reason each, with a screenshot's name or a file and line. The total (of 40) is compared with the
last round's, not with a band.

| # | Heuristic | What to look for in this app |
| --- | --- | --- |
| 1 | Visibility of system status | A search's place in the queue and its progress, the size word, what a filter hides, what is loading |
| 2 | Match with the real world | Highliners' words (webbing, athlete, anchors), never the engine's or the code's; touch words on phones |
| 3 | User control and freedom | Back, cancel, close and undo everywhere; a sheet or panel that can be left; nothing fires without a way back |
| 4 | Consistency and standards | One word for one thing (count, height, best), one look per kind of control, the platform's habits |
| 5 | Error prevention | A guard before what cannot be taken back (cancel a search, delete, remove a favourite); Start's reason when off |
| 6 | Recognition rather than recall | The sorted value visible, the settings of a search on its card, the selected line kept in sight |
| 7 | Flexibility and efficiency | The rigger's repeated tasks short: edit and run again, filters, sorting, comparing, the keyboard |
| 8 | Aesthetic and minimalist design | The three tells: "Same grey box everywhere, Long explaining texts, Symbols and dense strings" |
| 9 | Recovering from errors | "Nothing found", a refused search, a failed lookup: what went wrong and the next step, in plain words |
| 10 | Help and documentation | A "?" on every setting, short; the intros reopenable, not in the way |

**2. Eight checks of cognitive load**, each yes or no for the screens the change touches; the count of "no" is
reported, with every decision point that shows more than four choices at once (screen and count):

1. One focus: the screen serves one task.
2. Chunks: groups of at most four items.
3. Grouping: what belongs together is seen together.
4. Hierarchy: the next step and the most important value are the first things seen.
5. One thing at a time: steps come in order, not all at once.
6. Few choices: no more than four options at a decision, or a default that makes the choice easy.
7. Working memory: nothing must be carried in the head from an earlier screen.
8. Progressive disclosure: depth is one step away, not on the first view.

**3. Two walks, in the product's two users**, a few lines each: what helps, where it stalls, what scares.
- **The experienced rigger at a desk**: the repeated tasks on the desktop (edit a search and run it again; from a
  result to the best lines of a wanted length and height; compare; save, sort and share).
- **The first-timer on a phone**: from the sign-in page to a first search, understanding the first result,
  recovering from "nothing found".
- **A keyboard-only pass** of the changed screens: every control reached, a visible focus, no trap, a sensible
  order.

## What it writes

`local/<task>-<date>/<agent>/design-review.md`:
1. The rules in force that the change touches, one row each: met / partly / not met / not checkable, with the
   number (before and after) or the screenshot as evidence.
2. The ten scores, the eight checks with the decision points, the two walks and the keyboard pass.
3. What the numbers say got better and what got worse.
4. Findings, most important first, each marked **blocks a task**, **should be fixed** or **polish**, with its
   evidence, the user it hurts (the rigger, the first-timer, both) and the user's aim or concern it touches.
5. What could not be judged from still pictures (a drag, a transition, timing, what a screen reader says).
6. The verdict: **conforms**, **conforms with findings** (rows) or **does not conform** (rows).

Its final message (at most 40 lines): the verdict line, the counts of rows by verdict, the scores' total against the
last round's, the findings that block a task, and its file's path.

## What it must not do

- Judge against its taste: the measure is PRODUCT.md, DESIGN.md and the user's words. A look the user accepted on a
  mock-up is not a finding; a decision of the repository (the C frame, the wording rule, a "?" on every setting) is
  not a finding by itself, though its cost may be noted.
- Set or move a threshold: a rule's number is the user's pick.
- Change anything, install anything, or run more than the measuring tools on the changed pages.
- Name a finding without evidence (a screenshot, a number, a file and line).

## Sources

- The ten usability heuristics: Jakob Nielsen, Nielsen Norman Group.
- The scoring frame (0 to 4 per heuristic) and the cognitive-load checks are adapted from the critique reference of
  the open-source design skill "Impeccable" (Apache-2.0). It is not installed in this project and not required; the
  checklist above stands on its own.
