# Line volume: the implementation specification

2026-11-14. The specification of what the line-volume task decided and did not build: the search finds far more
lines in the rig people really use than the site can keep, send or show, and these are the measures against it.
The bar: "complete enough that a later session's agents implement it without new decisions"; where a decision is
still missing, it is listed in section 6, never hidden.

## 1. How to read it
| File | Covers |
|---|---|
| `spec.md` (this file) | where the task stands, the path to the goal case, every solution, the order of building, the open choices, phase 4's findings |
| [spec-search.md](spec-search.md) | before and during the search: the Basic form with 'My rig' and goals, the size from a sample, the access mark, the lip anchors' measurement, findings, decided items |
| [spec-store.md](spec-store.md) | stored and sent: the Arrow store (the one schema of a run's lines), old runs, the ranges of a kept line, what is sent, renaming a run |
| [spec-view.md](spec-view.md) | shown: today's page ranked by mean height with the tight mark, the result view of mock-up 2, the audit's reading choices |

Every solution has eleven headings, in this order: 1 Decision (the gate's id and title, the user's words, the
tier); 2 Behaviour; 3 Data (with the stored-data decision, "automatic migration" or "none"); 4 Interfaces; 5 Files and
pairs (the "must stay in step" pairs of `.claude/rules/<area>.md`, by their words); 6 Screens; 7 Tests;
8 Acceptance; 9 Waves; 10 Risks and rollout; 11 Needs the user's word. Short solutions join some headings.

**Sources and how they are named.** The task's study (2026-11-10 to 2026-11-14) is not in the repository; its
numbers stand here with the part that measured them: parts E1-E6 (the evidence of phase 1), P1-P7 (the measurements
and the two mock-ups of phase 3), W2-W4 (phase 4's builds). A number with a part's name is measured there; "(estimate)"
marks the authors' arithmetic; seconds are indicative unless measured under the exclusive lock. The user's decisions
are quoted verbatim with their date. Three gates: gate 1 (2026-11-10: the effects, ids A1-E8 and N1-N2, and the
targets T1-T10), gate 2 (2026-11-13: decisions D-01 to D-14, needs N-01 to N-06), gate 3 (2026-11-14: G-01 to G-14).
Idea ids (F-, K-, O-, S-, T-, V-) are the study's idea board's and come with their title. Mock-up 1 is the Basic
search form (version 3 accepted on 2026-11-13); mock-up 2 is how a result is organised (version 7 accepted on
2026-11-14); both are described in words in the part that uses them. Effort is Claude effort: low, medium or high.

## 2. Where the task stands

### What phase 4 built (2026-11-14)
| Item | What | The record |
|---|---|---|
| Fall zone 6 m | The sag model's leash fall space (`--fall-zone`) defaults to 6 m (3 m before); stored sag requests without the value keep 3 m (migration 17 of `jobs.sqlite`) | `docs/roadmap.md` "Sag model's fall zone (2026-11-14)"; `docs/truth-check.md` "The fall zone of 6 m" |
| Refusal advice | The four `too_many_lines*` refusals name only the changes that apply, at most four, in the measured order; when the square rule is off they offer it first (`--same-line-square 5`; the user's closing answer "7. a)") | `docs/roadmap.md` "Advice of a refusal for too many lines (2026-11-14)" |
| The square rule | `--same-line-square M` (`SearchParams.same_line_square`, 0 = off, else 2 to 20; `params.same_line_side` in `run.json`); module `samelines.py` (`BestPerSquarePair`, `reduce_table`, `side`); per line `stands_for`, the last column of `lines.csv`; `summary.found`; the line limit counts kept lines; regression entry R65 | `docs/roadmap.md` "The same line: the square rule (2026-11-14)"; `docs/truth-check.md` "The square rule" |
| The audit tool | `tools/prune_study.py`: what a pruning rule keeps of a saved table of lines and what it drops (rules `higher_wins`, `best_per_cell_pair`) | `docs/code-map/tools.md` |

The names `--same-line-square` and `stands_for` are final (the user, 2026-11-14: "name is ok"). The square rule keeps
per pair of anchor squares the line that needs the least rigging (no no-fall zone and no A-frames, then no A-frames),
then the highest mean height, the longest, a fixed order of the anchors (G-02 a). An independent review checked it on
R65's search (60 002 found, 3 491 kept): a reference written from the rule's words alone gave the same kept lines and
counts (0 differences on unrounded values); one thread and 25 tiles gave the same `lines.csv`; with the option off
`lines.csv` is byte-equal to the code before the rule. The truth check at the 6 m fall zone: recall 17 % with the
option off, 16 % at 5 (306 and 283 known lines matched).

### The target rig and the reference cases
The target rig (the study's C4): the sag model, leash fall space 6 m, a no-fall zone of 5 m at the ends, A-frames of
2 m (of the goal case with the no-fall zone, the user: "that's the way we hang the lines"). Lines found in it
(part P1, measured; the public line limit is 1.5 M lines):

| Case | What it is | Lines in the target rig |
|---|---|---:|
| GZ1 | the goal case: the Gozo coast, sea cliffs | 24 480 100 (503 651 kept at `--same-line-square 5`) |
| GZ2 | the Gozo coast, a 100 m band, mean height at least 40 m | 12 294 564 |
| GZp | a 0.187 km² part of GZ2: sea cliffs | 2 226 934 |
| MG | Mała Gańkowa, an alpine area of 2.5 km² | 18 323 986 (467 866 kept at 5) |
| MG0 / MG5 | MG as first saved (41 377 lines) / a saved MG run of 3 057 204 lines, which crashes today's page | – |
| MGp | a 0.137 km² part of MG: alpine walls and ridges | 3 525 979 |
| BAH | Il-Bahrija, Malta, a 1 km circle (949 160 lines as saved, formula with zone and A-frames) | 2 010 351 |
| STR | Strelecka kotlina, a control | 9 833 076 |
| KOB | Kobylanka, Poland, a 1 km circle, a control | 605 729 |
| MLT | the Malta coast | 16 412 174 |
| BEL | Bełchatów, a quarry area | 1 543 686 |
| DOL | valleys near Kraków | 3 558 706 |
| SCH | Schneewigi | 86 363 830 |
| V1 / V2 | USA: an area of 9 km² / a circle of 2.45 km | 65 853 889 / 134 916 275 |
| V3 | Slovakia, 2 m data | 66 141 198 |
| V4 / V5 | Poland, a 300 m circle / Malta, a 1.1 km circle | 28 915 / 1 116 324 |

Without the square rule 3 of these 16 pass the public limits (KOB, V4, V5).

## 3. The path to the goal case
GZ1 in the target rig. "M" = measured (the part named), "E" = estimate. The store's and the view's steps change
nothing before saving: the search's seconds and memory stay those of row 2.

| Step | Lines | Search | Folder | Sent before usable | Opens | Kind |
|---|---|---|---|---|---|---|
| 1. Before phase 4 | 24 480 100 | count 77 s, peak 2 889 MB | – | – | refused on the public site (1.5 M lines); cannot be saved or opened (gate 1, T10) | M (P1) |
| 2. Square rule, `--same-line-square 5` (built) | 503 651 kept of 24 480 100, 8 269 spots | 89.8 s, peak 2 911 MB | 865 MB (`data.js` 137 MB) | `data.js` 137 MB raw; compressed not measured | under the browser's string limit and the public line limit; opening not measured | M (W4) |
| 3. + store waves 1-2: columns in the page, the store beside today's files | the same | the same | about 920 MB | about 19-26 MB of the store (nginx gzip) | desktop: about 1 s after the download; Pixel 7 profile ×4 about 2.5-3.5 s | E |
| 4. + store wave 4: text files and `file://` end; old runs removed on the user's word | the same | the same | about 60 MB | as step 3 | through the app only (`findaline.py view`) | E |
| 5. + store wave 6: brotli once at saving, immutable caching | the same | the same | about 75-80 MB | 17-23 MB br (2.7-3.7 s at 50 Mbit/s, 14-18 s at 10); a reopen sends nothing | as step 3 | E |
| 6. + view wave B1: spots, sectors, top level, the view's order in the store | the same | the same | about 80-85 MB | about 19-27 MB | as step 3 | E |
| 7. + store wave 7: the ranges of six values of a kept line (store U1 b) | the same | the same | about 115-120 MB | about 27-37 MB (4.3-5.9 s at 50 Mbit/s) | as step 3 | E |
| 8. + view waves B2-B5: the result view | the same | the same | as step 6 or 7 | as step 6 or 7 | at most 5 000 strokes drawn; no grouping at load; a filter change on 503 651 lines 55-62 ms (measured 2026-11-17, section 5) | E (mock-up 2) |

So T10 (the goal case opens on a desktop) is met by step 3 (estimate); T3 (a folder within the public limits at most
300 MB) by step 4; T4 (10-20 MB sent) only without ranges and only at the low end of the estimates: with the six
ranges the user chose (step 7) the goal case sends about 27-37 MB (estimate), above that guide. Sources: step 2
from W4; steps 3-7 from `spec-store.md` sections 4 and 6 (parts P5 and E2); step 3's gzip is br × 1.13, part P5's
gzip-6 to br-5 ratio on MG5 (estimate); step 7 adds 49 B a line raw and 8-10 MB sent (estimate, `spec-store.md` 3.3).

## 4. All solutions
| Solution | Decision | Tier | Where | Depends on | Effort |
|---|---|---|---|---|---|
| Basic form with 'My rig' and goals | G-11 a; D-10 a; N-01 | built (c8a079a) | search 1 | the square rule (built); count 5.5 a; the rigs' migration (next free number) | medium (server), high (page) |
| The size of a search from a sample | G-04 a; N-02, N-05 | built (4f468d3) | search 2 | measurement 5.5 b for searches with the square rule (search U-6) | high |
| Access mark of three states | G-09 a; D-08 c | built (53fe802); its later parts with the result view | search 3 | – | high |
| Lip anchors against the known lines | G-07 a; search U-12 (98 %) | measured (round 3): about 70 %, below the bar; not built | search 4 | – | medium |
| The memory constant `LINE_BYTES` | G-05 (finding) | built (0e711bb): 900 B a line | search 5.1 | – | medium |
| `count_tile`'s sag table per tile | finding | built (4f468d3) | search 5.2 | – | low |
| 'Sea cliffs' without its wall-angle limit | G-11 a | built (c8a079a) | search 5.4 | count 5.5 a; search U-2 | low |
| Owed counts: goals with the rule; a sample of kept lines | G-11, G-04 | measured (round 2) | search 5.5 | 5.3 | medium each |
| Columns in the page from `data.js` | G-06 a; D-05 c | built (31f16de) | store 1 (wave 1) | – | high |
| The Arrow store beside today's files | G-06 a; D-04 a | built (47c5fa7 the files, ef93df5 the page's reader) | store 1 (wave 2) | – | medium ×2 |
| Exports made per download, none kept | G-06 a; store U4 | structural | store 1 (wave 3) | wave 2 | medium |
| Text files and `file://` end; `view`; the reader of `data.js` goes | G-06 a; D-04 a | structural | store 1 (wave 4) | wave 3; view B1 | high |
| Old runs removed, not converted (a step of store wave 4) | G-06 a; store U5 | structural | store 2 | the user's word at that time, after a `--dry-run` list | in wave 4 |
| What is sent: brotli at saving, immutable, size, warning | G-06 a; F-10, F-12, F-30, T-34; store U12 | structural | store 4 (wave 6) | a small mock-up (the codec is settled: pyarrow's own brotli, no new package) | medium |
| The ranges of six values of a kept line | G-03 b; store U1 b | structural | store 3 (wave 7) | wave 2 | medium |
| Renaming a run | the user, 2026-11-13 | next | store 5 (wave 8) | a small mock-up | low |
| "Best" by mean height, tight mark, headline | gate 3 settled list; G-10 a | built (c5b07be) | view A | view A-1 | low ("kept") or medium |
| The result view of mock-up 2 | D-11 d, D-12 a, N-04, N-06; G-08 a, G-12 a; view B-1 (K-17) | structural | view B | store wave 2 | B1 medium, B2 high, B3-B5 medium |

## 5. The order of building
| Step | Work (part, wave) | Waits for | Parallel with | Effort |
|---|---|---|---|---|
| 0a | search 5.3, then 5.5 a: every goal with the square rule on 16 cases, 'Sea cliffs' variants | – | 0b, 1a | medium |
| 0b | search 5.5 b: an estimator of kept lines from a sample | – | 0a, 1a | medium |
| 0c | search 4: four truth-check passes with and without lip anchors; the bar is 98 % (search U-12) | the PC free | anything that does not measure | medium |
| 1a | view A: best by mean height, tight mark, headline | view A-1 (or the planner's default) | all of step 1 | low / medium |
| 1b | search 1, waves 1-2: the rigs' server, then the Basic page | 0a reported to the user before the review (wave 3) | 1a, 1d, 2a | medium, high |
| 1c | search 2: the sample in the worker | 0b (for Basic searches; without the square rule it may go first) | 1a, 1b | high |
| 1d | search 3: `access.py`, the search and files; the page after its mock-up | search U-9, U-11; a mock-up | 1a, 1b | high |
| 1e | search 5.1 (exclusive, the PC free), 5.2, 5.4 (after 0a); phase 4's findings (section 7) | as named | any | low-medium |
| 2a | store wave 1: columns in the page | – | store wave 2's Python half | high |
| 2b | store wave 2: Python store (B) at once; the page's reader (C) after 2a | 2a for C | 2a (B) | medium ×2 |
| 2c | store wave 3 (exports per download), then wave 4 (text files and the reader of `data.js` end; old runs removed in two deploys, `spec-store.md` section 2) | 2b; wave 4 also 3a, share links and runs outside `runs.js` reading the store (`spec-store.md` 1.10; both built in round 4), and the user's word on each host after the `--dry-run` list | 2d, 2e; wave 3 with 3a | medium, high |
| 2d | store wave 6: what is sent, brotli at saving | 2b; its mock-up (the codec is settled: pyarrow's own brotli, no new package) | 2c, 2e | medium |
| 2e | store wave 7: ranges of six values | 2b; store U2's mock-up for the page | 2c, 2d | medium |
| 2f | – (was store wave 5, old runs converted: the user chose removal, a step of 2c's wave 4) | – | – | – |
| 2g | store wave 8: renaming a run | its mock-up | anything | low |
| 3a | view B1: spots, sectors, `top` (K-17), `by_spot` into the store | 2b | 2c (wave 3), 2d, 2e | medium |
| 3b | view B2 (map core) and B3 (list, details, fan) | 3a; B3 once B2's model interface is fixed | each other | high, medium |
| 3c | view B4: today's features joined | 3b | 2g | medium |
| 3d | view B5: ported checks, `tools/ui_shots.py`, `viewer/dist` | 3c | – | medium |

Steps 0 and 1 hold the next tier; steps 2 and 3 the structural one. Tests and searches run one after another under
`tools/test_lock.py`; measurements that read seconds or memory wait until the user says the PC is free.

**State on 2026-11-15.** Done (round 2, in `main`): 0a and 0b (the measurements of every goal with the square rule
and of the estimator of kept lines); 1a (c5b07be: best by mean height, the tight mark, the headline); 1b (c8a079a:
the Basic form, saved rigs as migration 18, with 5.4); 1c with 5.2 (4f468d3: the 2 % sample in the web worker); and,
beside the plan, the shore chip on phones (c7ff76e) and the rig's factors at 6 m with the square rule (the size word's
"?" and the rig window's cost line). Round 3 (from 2026-11-15) builds 2a, 2b, 1d and phase 4's findings (section 7),
and measures 0c and 5.1. Open after it: 2c-2g and 3a-3d.

**State on 2026-11-16.** Done (round 3, in `main`): 2a (31f16de: the page keeps a run's lines as typed-array
columns); 2b (47c5fa7: every new run writes the Arrow store beside today's files; ef93df5: the result page reads it
over http, and nginx gzips it); 1d (53fe802: the access mark, `spec-search.md` 3 as built); 1e's rest (0e711bb:
`LINE_BYTES` 900 B a line; f49026a: section 7's first findings). 0c is measured and closed: lip anchors keep about
70 % of the matched known lines against the bar of 98 %, so they are not built (`spec-search.md` 4). Measured after
the store on BAH in the target rig (desktop Chromium; `docs/performance.md` "From the store"): T5's heap is
447-474 MB two frames after the first picture (met); the first picture comes after 3.06-3.37 s (the 3 s target is not
met: the grouping takes 1.8 s of it); T6 is unchanged (a filter change about 1.2 s, a grouping change about 1.5 s).
View B1's `by_spot` in the store (step 3a) is the planned answer to the grouping's seconds. Open: 2c, 2d, 2e, 2g and
3a-3d. The result view (3b-3d) also takes the access mark's later parts (`spec-search.md` 3.9). Round 4 (from
2026-11-16; the user's "1. a", "2. a") takes 3a and 2c's wave 3 side by side, then 3b; "Lines from here" comes with
3b as specified, not onto today's page first.

**State on 2026-11-17.** Done (round 4, in `main`): 3a (39785f8: the view's columns `spot`, `top`, `by_spot` and the
head's `sectors`, `box`, `lengths` computed at saving; Ward's clustering exact up to 10 000 spots, on an even sample
above); share links and runs outside `runs.js` read the store (b757bee: the gap 2c's wave 4 waited for,
`spec-store.md` 1.10); 2c's wave 3 (f2f8015: exports made per download, their rate, the Download menu); 3b's two
halves behind the flag `?view=b` (70bef24: B2, the map core; d0553d7: B3, the list, the details, "Lines from here"
and the table of spots); and, beside the plan, the sectors' term in `search.memory_needed` (dfb3fc3). Measured:
saving takes 1.1 s more on BAH with the square rule (2.24 → 3.32 s) and 0.8 s more on the goal case (5.04 → 5.88 s),
the process tree's peak unchanged (`docs/performance.md` "The result view's columns"); an export takes 12-30 s at
2.0-3.5 M lines (indicative, `spec-store.md` 1.10). T5/T6 of the view against today's page (one exclusive pass,
desktop Edge; `spec-view.md` B.8): the first picture 0.41 / 0.40 s on BAH with the square rule (43 127 lines),
0.98 / 1.48 s on the goal case (503 651), 2.22 / 3.41 s on BAH (2 010 351); the heap 20 / 26, 111 / 169 and
273 / 468 MB; a clearance filter turned on 33 / 45, 55 / 487 and 217 / 2 038 ms. So at BAH the view meets T5
(2.22 s, 273 MB) and T6 for a filter (217-263 ms), not for "Top level only" (335-404 ms). Open: 2c's wave 4 (what it
waited for is built, so it can be built now; only its removal of old runs needs the user's word on each host after
the `--dry-run` list), 2d, 2e, 2g, 3c (today's features joined, with the design review's list in `docs/roadmap.md`),
3d.

**State on 2026-11-18.** Rounds 3 and 4 are pushed and on the server (2026-11-17: `main` e88d69f3 deployed by the
user, the worker's memory 19g). Done (round 5): 2c's wave 4, first deploy (`main` 1b1f2f15, a0c511ac, a86b86e8;
pushed and deployed 2026-11-18): new runs keep no text files, `findaline.py view`, `runs remove-old`, the disk
notice, Home's mini maps and the tools from the store (`spec-store.md` 1.9 "Built (round 5)"); then the old runs
removed on the PC and on the server, each on the user's word after its dry run (`spec-store.md` 2 "As run"). The full
pytest on the stack: 3 231 passed; the regression set: 91 entries unchanged (R17 waited on Overpass and R70 on
basisdata.nl, neither on a run's files). Then 2c's wave 4, second deploy, in `main` once both hosts were cleared (the
end of the page's reader of `data.js`: `spec-store.md` 1.9). Open: 2d, 2e, 2g, 3c (after the UX session's design
pilot, the user's "a"), 3d.

**State on 2026-11-22.** Done (round 6, tag `history/view-3c`; started once the UX session's pilot was accepted): 3c and
3d. Step 3c joined today's features to the result view in the places of an interactive mock-up the user judged at
gate 1, with the design review's list of 2026-11-17 (`docs/roadmap.md`); step 3d listed every check of today's result
page and of the pages around it, ported each missing one to the view or recorded a decision (`spec-view.md` B.7), and
brought `tools/ui_shots.py` and `tools/ui_walks.py` to the view. Gate 2, the user's checks on an iPhone over the
local network (`tools/lan_app.py`), added six changes and fixed the store's load when a phone's screen goes off; then
the view became a run's page by default (`spec-view.md` B.10, on the user's "yes"). What was decided: section 6.8;
the looks: docs/DESIGN.md rows 100 to 130; left: docs/known-bugs.md ("Line volume, round 6") and docs/roadmap.md
("Line volume round 6: open"). Not met: T7 (`spec-view.md` B.8). Open: 2d, 2e, 2g.

**State on 2026-11-25.** Round 7 (planned 2026-11-23 against what had changed since this specification: the text
files gone, the store a run's only data, the result view the default page) closed the three steps left. 2g is built
as `spec-store.md` section 5 now says (the public site only, no command; Home's card menu and panel, the desktop
view's button; the name rule; the audit event without the name; the privacy page's two sentences). 2d was reduced by
the user to the run's size on Home's card, as stored, with the loading line counted in 10^6 bytes (section 4 "As
built in round 7"): brotli and the immutable cache are not built. 2e's server half was built, accepted on the six
cases and dropped by the user after its measured gain and cost (section 3 "Not taken"). Beside them the extras A3,
A4, A6, A7, A8 and B8 (`docs/roadmap.md`, "State on 2026-11-25"), and the readers handed a run reading its run.json
through `runs.read_meta`, as the rename does. The decisions: 6.9. Left: `docs/known-bugs.md` ("Line volume, round 7") and `docs/roadmap.md`
("Line volume round 7: open"). No step of this specification is open.

## 6. The user's choices
Classes: **before** = decide before building that work; **mock-up** = decided at that task's mock-up; **measure** =
decided by a measurement first; **planner** = taken as recommended by the planner unless the user objects.

### 6.1 Decided by the user's closing answers (2026-11-14)
The planner offered ten closing choices after phases 4 and 5; the user answered, verbatim: "1. c) 2. a) . Add a note
on it - it might be useful for increasing % of lines found from slack map 3. old runs removed - both on server and on
this pc 4. a) 5. c) - how does it work with regressions? 6. a) 7. a) 8. a) 9. a) 10. a)". The planner's list had its
own letters; its readings, told to the user, are these:

| Id | Decided | Where it is applied |
|---|---|---|
| store U1 | (b) a kept line carries the ranges of six values: length, clearance, highest point, A-frames needed with and without the no-fall zone, and the mean height (+49 B a line, estimate) | `spec-store.md` 3, 6, 8; section 3 step 7 |
| view B-1 | K-17 'Higher wins on a face' is the top-level flag, as the accepted mock-up. The user's note: K-18 'Higher wins unless clearance loses' kept 590 of the 592 matched known lines against K-17's 589 (part P3b), so it "might be useful for increasing % of lines found from slack map": a candidate to measure when the share of known lines found is worked on | `spec-view.md` B.3, B.11, E; `docs/roadmap.md` |
| store U5 | Old runs are **removed, not converted**, on the public site and on the PC, when the text files end; the removal deletes the user's data and runs only on the user's word at that time, after a `--dry-run` list; until then every run opens as today | `spec-store.md` 1.2, 1.3, 1.9, 2; sections 3, 4, 5 |
| store U12 | Brotli at saving; a new package: the building task compares the brotli packages first, as the project's rule on dependencies asks, and the user confirms the package. Settled in round 3: pyarrow's own codec, no new package (6.5) | `spec-store.md` 4, 8 |
| store U4 | An export (CSV, GeoJSON) is made for each download, none kept. The regression set never uses a kept file: `tests/regression.py` takes the sha256 of the CSV text the export makes from the run's store (the same bytes as today's `lines.csv`, so every checksum stays), and until the text files end it checks the export against the `lines.csv` the same run still writes, on every regression entry | `spec-store.md` 1.2, 1.4, 1.7, 1.10 |
| search U-12 | Lip anchors become an option only if they keep at least 98 % of the matched known lines | `spec-search.md` 4 |
| – | The refusal advice offers the square rule first when it is off: built now | section 2 |
| – | The tiled line limit's 0.2 % stays a known finding, with its fix written down | section 7; `docs/known-bugs.md` |
| – | The fall zone stays 6 m after the recall finding (17 % against 33 % at 3 m, sag alone, `docs/truth-check.md` "The fall zone of 6 m") | section 7 |
| – | The task is closed: the roadmap, the known bugs, one squash commit into `main` | `docs/roadmap.md` "Line volume" |

### 6.2 Taken as recommended (class "planner")
The user was offered the list of these 21 choices on 2026-11-14 and did not go through it: they stay taken as
recommended.

| Id | The question | Taken | Blocks |
|---|---|---|---|
| search U-1 | "Tension grows with the length" in the rig's window | (a) left out until an option exists | search 1 |
| search U-3 | Texts changed from mock-up 1 | 1.2's texts; "Can be very large: slow, may not open on a phone." on "Everything" | search 1 |
| search U-4 | The access row in Basic before the mark exists | (a) left out | search 1 |
| search U-5 | Where the rig in use is kept | per browser | search 1 |
| search U-7 | Who samples | (a) the web worker only | search 2 |
| search U-8 | The access mark's switch | (a) an option, on in the web form | search 3 |
| search U-10 | Where the access mark shows | a mock-up before code | search 3's page |
| store U3 | Water and filled metres in the ranges | (a) left out now | store wave 7 |
| store U6 | Circles' profiles of every line | (a) kept now | store wave 4 |
| store U7 | Light view, tiers, nested results (F-31, F-24, K-33) | (a) parked | – |
| store U8 | The phone warning's threshold | (a) none until a real-device test | store wave 6 |
| store U9 | Who may export | (a) owner, administrator, demo; since 2026-11-16 the user's own decision (6.6) | store wave 3 |
| store U10 | `--html` after `file://` ends | (a) accepted one release | store wave 4 |
| store U11 | Filtered exports, GeoPackage, KML (F-32) | (b) parked | – |
| view A-1 | Does "best" change the spots or only the line shown | (a) only the line | view A |
| view A-2 | "Highest on average" in "Show per spot" | add it first | view A |
| view A-3 | The tight words without A-frames | without the A-frame clause | view A |
| view B-3 | A favourite in a spot | today's rule | view B4 |
| view B-4 | Other runs (Compare) in the view | drawn apart | view B4 |
| view B-5 | "Open spot" before the cards' mock-up | hidden | view B3 |
| view B-6 | A number for T9 (local density) | none; the 5 000 limit and Best 10 stand in | – |

Decided by the planner (no question): "Top level only" comes with the result view (G-08 a); the top-level flag and
the sectors are computed in Python at saving.

### 6.3 Still open
| Id | The question | Options | Recommendation | Blocks | Class |
|---|---|---|---|---|---|
| store U2 | A line that passes only by its ranges; where ranges show | (a) drawn as any line, ranges in details; (b) a mark of its own | (a), with a details mock-up | store wave 7's page | mock-up; **closed 2026-11-23 as not built**: the ranges were dropped (6.9) |
| store U5's removal | The removal of old runs on each host (the PC, the VPS) | yes after the `--dry-run` list; not yet | – | store wave 4's second deploy | before; **decided 2026-11-18**: "remove on PC", "remove on server" (6.7) |

### 6.4 Decided on 2026-11-15 (rounds 2 and 3)
The user's answers, verbatim: round 2, on the counts of every goal and the estimator: "1. a) 2. 2% 3. a) 4. ok start
it"; on the rig's factors: "1. ok 2. ok c)"; round 3, on its scope questions: "1. a 2. a 3. a 4. a 5. a 6. a 7. c".

| Id | Decided | Where it is applied |
|---|---|---|
| search U-2 | (a) 'Sea cliffs' has no wall-angle limit | `main` c8a079a; `spec-search.md` 5.4 |
| search U-6 | Neither option: with the square rule the sample counts 2 % of the rule's squares (part M2's candidate 1b) | `main` 4f468d3; `spec-search.md` 2.2 |
| – | The sample is 2 %; no cap per spot (K-13 not built): the estimate refuses before the search, with the advice | `main` 4f468d3; `spec-search.md` 2.2, 6 |
| – | The size word's "?" and the rig window's cost line carry the measured factors at 6 m with the square rule (middle values: sag ×1.6, no-fall zone ×4.1, A-frames ×1.6); no "Lighter" hint | `main` c8a079a; `spec-search.md` 1.2 |
| search U-9 | (a) the alpine variant of the access measure is in | `spec-search.md` 3.2, 3.11 |
| search U-11 | The user looked at part P3d's five pictures: the colours match; the measure is ported as it is | `spec-search.md` 3.8, 3.11 |
| – | The store's libraries: pyarrow (Python) and apache-arrow 21.2.0 (the page) accepted ("2. a") | `spec-store.md` 1.5, 1.10 |

### 6.5 Decided in round 3 (2026-11-15 and 2026-11-16)
The user's words, verbatim, each on the question named.

| Id | Decided | Where it is applied |
|---|---|---|
| store U12's package | Brotli at saving uses pyarrow's own codec (`pa.Codec("brotli", compression_level=5)`); no new package. The user, on the comparison of the packages: "a" | `spec-store.md` 1.9, 4.2, 8 |
| – | T5's heap is the peak after loading, read two frames after the first picture. The user: "a" | `spec-store.md` 1.8 |
| – | `search.LINE_BYTES` is 900 B a line, with no fixed term. The user: "a" | `main` 0e711bb; `spec-search.md` 5.1 |
| search U-10 | Where the access mark shows: the mock-up's version 8 ("current mockup looks good and can be implemented"). Its three layout answers: "Selected line only", "Two dots in every row", "+ 'From a top edge' pick" (the pick comes with the result view) | `main` 53fe802; `spec-search.md` 3.6, 3.9 |
| – | The three states are "easy access", "cannot tell" and "hard access" ("change `walkable` to `easy access`", "change `cannot tell here` to `cannot tell`", "something among \"hard access\""); the form says "No line is filtered out" ("17. it is ok"); hard access is drawn in slate, the signs are a walker and a person on a rope ("i like A slate with walker and rope"), as the project's own drawings ("use ours") | `main` 53fe802; `spec-search.md` 3.2, 3.6 |
| – | The phone legend of two lines with a fold, its fold mark the side panels' chevron ("Make it two line, and add option to collaps it", "18. ok"): with the result view; today's phone page has no legend that scrolls sideways | `spec-search.md` 3.9 |
| – | The access grid of a large area is computed in blocks ("Compute in blocks"); an anchor on a sea cliff's face taken from the surface model takes "The measure's own answer" | `main` 53fe802; `spec-search.md` 3.2 |
| – | A search too wide for the access grid runs without the mark: "1, and add to roadmap for better algorith with lower memory cost". On the public site its note has no memory figures: "remove it from message when --public flag is set" | `main` 53fe802; `spec-search.md` 3.2, 3.4; `docs/roadmap.md` |
| – | "Search a cell" of the highline layer: "open in advanced with mark on". Searches stored before the mark stay as they are: "does not matter - old runs will be removed everywhere" | `main` 53fe802 |
| – | A store of a newer format: the text keeps both sentences ("This result was made by a newer Find-a-Line. Update Find-a-Line to open it.") | `main` ef93df5 |
| search U-12 | Applied: lip anchors keep about 70 % of the matched known lines, below the bar of 98 %, so they are not built | `spec-search.md` 4; `docs/roadmap.md` |

### 6.6 Decided in round 4 (2026-11-16 and 2026-11-17)
The user's words, verbatim, each on the question named. On 2026-11-17 the user answered the planner's open questions
by number and letter in several messages; a number names a different question in each message, so every row below
says which question it answers.

| Id | Decided | Where it is applied |
|---|---|---|
| – | Round 4's scope: view B1 and the exports per download side by side, then the result view's map core and its list, details and "Lines from here" as specified ("1. a 2. a 3. PC is set free; run tasks as required 4. a 5. a") | `spec.md` 5 |
| store U9 | A share link's page has no Download for a run with a store ("No Download there (Recommended)"): share links may not export. A visitor of a demo run who is not signed in gets no Download button either ("No Download button (Recommended)"). Exports have a limit of their own, 4 a minute and 30 an hour on the public site ("Yes, 4 a minute, 30 an hour (Recommended)") | `spec-store.md` 1.2, 1.4, 8 |
| – | The privacy page names exports ("Yes, both as written"): in the audit list "exports of a run's lines made (CSV or GeoJSON: the format, not the content)," and the sentence "A file made for a download is kept on the server until it is fetched, for one hour at most." | `spec-store.md` 1.4 |
| – | The Download buttons: "Preparing the file…" in the pressed row ("In the pressed row (Recommended)"); a failure as a red line in the menu ("Red line in the menu (Recommended)"); the mock-up's version 1 with its proposed texts ("The Download buttons' mock-up, version 1 - looks good do as recomended") | `spec-store.md` 1.2, 1.4, 1.6 |
| – | The unfinished result view lives in `main` in new files behind a flag, `?view=b` ("1.a") | `spec-view.md` B.5, B.10 |
| – | The view's map zooms in quarter steps ("2. b") | `spec-view.md` B.2 item 1 |
| – | The 5 000 limit counts the thin lines at the Lines level, as the accepted mock-up ("3. a") | `spec-view.md` B.2 item 7, B.8 |
| – | The selected row pressed again ends the selection on every row ("Ends the selection everywhere (Recommended)") | `spec-view.md` B.2 item 10 |
| – | "Only clear" only in More filters; "How to read the result" hidden in the view until its text is rewritten ("5. a") | `spec-view.md` B.2 item 14 |
| – | A link to a line that "Top level only" hides also lifts the chip ("6. a") | `spec-view.md` B.2 item 14 |
| – | On a phone a spot is in view by the part of the map a person sees ("Only the map you can see (Recommended)") | `spec-view.md` B.2 item 2 |
| – | The real map's controls take the mock-up's places, judged on the first build's screenshots ("8. a") | `spec-view.md` B.2 |
| – | The crowded tap's table opens at 0.25 m per pixel ("9.b") | `spec-view.md` B.2 item 9 |
| – | The sectors of a run with more spots than a cap: Ward on an even sample, every other spot to the nearest sector ("Sample (Recommended)") | `spec-view.md` B.3 |
| store U9 | 2026-11-17, on a run's own `map.html`: no Download for a run with a store, since the page holds no token and the server would refuse every export from it; Download stays on the app's result page ("1.a") | `spec-store.md` 1.2, 8 |
| – | On the view's phone layout: it opens with the sheet low, and the legend folds itself while the sheet stands at half or higher ("2.a") | `spec-view.md` B.2 |
| – | On the thin lines between map tiles at the view's quarter zoom steps: accepted for now ("3. a - and remind me to give opinion about it"); after trying the view, "ok, looks good" (below) answered the reminder | `spec-view.md` B.10 |
| – | On the search area's dashed outline: drawn in the view with today's other features, step 3c ("4. a") | `spec-view.md` B.2, B.9 |
| – | The singular forms of the two "Top level only" sentences, as proposed ("6. ok") | `spec-view.md` B.2 item 14 |
| – | On the regression entries the services could not confirm (R56, R70, R80, R85, R87): the merges of 3a and the exports do not wait for them; they run again when Overpass and basisdata.nl answer ("7. a"). R80 and R85 were confirmed on `main` later that day; R56, R87 and R70 stay open | `docs/known-bugs.md` |
| – | On the fit between a run's grid and the map: the polynomial fit stays, no projection library ("8. fit") | `spec-view.md` B.5, B.10 |
| – | The exclusive pass for the view's T5/T6 at the end of B3's work ("9. exclusive ok") | `spec-view.md` B.8 |
| – | On the sectors' clustering in a search's memory estimate: first "10. c" (decide before the next deploy, after one read-only look at the server's memory settings), then "10: term + …" (the rest names the server's setting, not written here): `search.memory_needed` counts 8 B × min(lines, 10 000)² (dfb3fc3, 2026-11-17). The worker's memory for the next deploy is the user's decision too ("3. b"); it changes only at a deploy | `docs/performance.md` "The sectors' term" |
| – | On the view's texts without a source in this specification: approved as listed ("1. ok") | `spec-view.md` B.4 |
| – | On the view's controls under 44 px on a phone (docs/DESIGN.md R2): the view goes into `main` as it is, and they are brought to the rule in step 3c ("2. a") | `docs/roadmap.md`; `docs/known-bugs.md` |
| – | On how the view goes into `main`: B2 and B3 together, as two squash commits, after B3's reviews ("3. a") | section 5 |
| – | After trying the view in a test app: into `main` behind the flag ("ok, looks good. Stop app and merge") | section 5; `spec-view.md` B.10 |

### 6.7 Decided in round 5 (2026-11-17 and 2026-11-18)
The user's words, verbatim, each on the question named.

| Id | Decided | Where it is applied |
|---|---|---|
| – | Round 5's scope: store wave 4 only, step 3c after the UX session's pilot ("2c wave 4 then wait till ux sessions ends it work"); the dry run on the PC on the real runs folder ("On runs/ itself (Recommended)"); no loose ends ("No, wave 4 only") | section 5 |
| store U5's removal | Where the end of the `data.js` reader waits: "1. we can deploy right now": the server deployed first, so it goes into `main` once both hosts are cleared | `spec-store.md` 2.2 |
| – | The disk notice: the planner's preview (the run's name, "This map opens through Find-a-Line. Run:", `findaline.py view <id>`) is its mock-up ("2. a") | `spec-store.md` 1.2, 1.6 |
| – | R70, never run with a store (basisdata.nl unreachable), does not block the merges ("3. a") | `docs/known-bugs.md` |
| – | A store that cannot be written: the search fails, no run kept (Q1a "1. a"); the removed runs' searches leave Home (Q3 "2. a"); the dry run's words as drafted (Q4 "3. a") | `spec-store.md` 1.9, 2.2, 2 "As built" |
| – | Push and deploy today's `main` before wave 4 ("a"; "VPS is depleyed already"), then wave 4's first deploy ("a") | section 5 |
| – | Before the PC's removal: `perf_reach`'s three named runs moved to a reference folder ("1. a"); the two favourite lines let go ("2. c"); the three stopped tiled folders deleted too ("b"); then "remove on PC" | `spec-store.md` 2 "As run" |
| – | On the server: "remove on server"; its stopped tiled folders left ("2. a"); no demo for now ("3.b") | `spec-store.md` 2 "As run" |

### 6.8 Decided in round 6 (2026-11-20 to 2026-11-22)
The user's words, verbatim, each on the question named; the planner's decisions within them are in the task's notes.

| Id | Decided | Where it is applied |
|---|---|---|
| – | The plan's fifteen questions: "1.a 2a 3a 4a 5. a … 15. a" (3c, then 3d, the default at its own gate; one interactive mock-up; B-3 as built; B-4 drawn apart; B-5 hidden; all of today's run actions; the hint first on a phone; the numbers measured first; help on touch; the words picked at gate 1; the kit's layers icon; the profile's leftovers fixed; the focus rings left to the UX task; today's page kept behind `?view=today`; no later point) | section 5; `spec-view.md` B.2 "As built in round 6"; DESIGN.md rows 100 to 124 |
| view B-3, B-4, B-5 | Applied as taken in 6.2: a favourite is its spot's shown line; Compare's lines drawn apart in each run's colour, not counted; "Open spot" hidden | DESIGN.md rows 112, 113 |
| – | Gate 1 on the mock-up: "4D a, 4P d, 7D b, 7P b, 10 a, N1 b, N2 a, W1 a … W14 a, S c, P c, L b, R a, T a, K a, H a", and question 11 "a: accept as shown" | `spec-view.md` B.2, B.8; DESIGN.md rows 100 to 107, 115 |
| – | The coarser box on a small phone: "Chip, like the shore"; both chips at half with a level held: "Known bug for now" | DESIGN.md row 105; `docs/known-bugs.md` |
| – | The screenshot gate of wave B: "GA a, GB b, GC a, GD a, GE a, GF a, GG a, M1 keep … M14 keep" | DESIGN.md rows 107, 118, 119, 123; `docs/known-bugs.md` |
| – | Wave C's parity gaps: P1 "a: add it" (its place "A: arrows in the head"), P2 "b: known difference", P3 "a: as today, drop to half", P4 "a: add a direction button", P5 "b: known difference now" | `spec-view.md` B.2, B.7; DESIGN.md rows 113, 116, 121, 122, 124 |
| – | A press after a pinch: first "thats fine" for a zoom out, then "yes" to a pan at the same zoom | DESIGN.md row 123 |
| – | Gate 2's triage: 1 a, 2 a, 3 a, 10 a (bugs); 4 a ("Turn your phone upright to use this page."), 6 b, 8 a, 9 a, 11 a, 12 a, 13 a (decisions); finding 1 "Keep as is, recheck"; the 3D view's photos "Roadmap only"; "Top level" per spot "add it to road map as a possible search filter" | DESIGN.md rows 125 to 129; `docs/roadmap.md` |
| – | Gate 2's second check: Safari's CSP line "Leave it, known bug"; the long list's sheet "Implement 41, and create a bug report for fixing it properly"; the 2D credits pill and R2: "(a) Accept 14 px"; the flip: "yes" | `docs/known-bugs.md`; DESIGN.md row 130 and R2; `spec-view.md` B.10 |

### 6.9 Decided in round 7 (2026-11-23 to 2026-11-25)
The user's words, verbatim, each on the question named (`local/line-volume-7-2026-11-23/user-inputs.md`, with the
planner's own decisions in `planner-decisions.md` beside it).

| Id | Decided | Where it is applied |
|---|---|---|
| S1 to S5 | The extras: "A6 way back from map.html, A7 Compare's two faults, A8 remove --html" (A1, the warning before a heavy run, left out); "A3 filter screenshots, A4 read chosen columns"; the long list's proper fix "No, a later round"; "B8 add to home screen"; a cut download resumed (A2) "Leave on the roadmap" | `docs/roadmap.md` "Line volume" |
| S6, S7 | 2d after the user's question on its gains: "Size on Home only" (the size on Home's cards and the unit; no brotli, no copies on disk, no change to nginx or the deploy); a run's store cached as immutable: "No, keep asking the server" | `spec-store.md` 4 |
| D2 to D4, D6 | Renaming: "Public site only"; no command ("No, the page only"); a name left empty: "Refuse it"; the privacy page's two sentences: "Yes, as proposed" (both) | `spec-store.md` 5 |
| D1, D5 | 2e's acceptance on "All six of the specification"; the square rule's unfinished tiled searches: "Deploy on an empty queue" (the planner's reading: void since 2e was dropped) | `spec-store.md` 3 |
| – | 2e, after the measured gain and cost: "Drop the ranges" (G-03 b stands as the count; store U1 and U2 closed as not built) | `spec-store.md` 3, 8; 6.3 |
| – | The mock-up MU-1 (2026-11-23): "Size as stored (Recommended)", "A panel under the card (Recommended)", "Desktop icon, phone via Home (Recommended)", "Back button and Try again (Recommended)"; its 28 points (2026-11-24): "go with recomeneded", (a) at each, with the texts T1 to T6, T9 to T15 and T21 | `spec-store.md` 4, 5; DESIGN.md rows 22, 98, 100, 108, 137 and R9 |
| – | The rename on Windows (2026-11-24): "d" (the option worded "those readers wait too: they read through the same waiting function") | `docs/known-bugs.md` "Two searches saved at once on Windows" |
| – | The ten answers of 2026-11-25: 1 a failed rename's text "The run was not renamed…" (T22); 2 "Keep portrait" (replaced on 2026-11-26 by "Drop the lock"); 3 a tiny run's loading line "Two decimals"; 4 the bars by the chosen theme "Keep it"; 5 Compare's off boxes "One look for all"; 6 the tablet header "Known bug, design later"; 7 Home's Favourite lines "Known bug"; 8 the three filter faults "Known bugs + roadmap"; 9 the run.json absent for a moment "Known limit"; 10 the rename's own read "Yes, it waits too" | DESIGN.md rows 98, 137; `docs/known-bugs.md` and `docs/roadmap.md` "Line volume, round 7" |

## 7. Findings of phase 4 to fix later
Each is also an entry of `docs/known-bugs.md` (the "Line volume" entries) unless it is a measurement.
- **The fall zone's migration and unfinished jobs:** an unfinished tiled sag job of the web app starts over after
  migration 17: the int 3 against the float 3.0 in the search's hash (`_search_hash`), so the hash differs.
  **Fixed** (f49026a): such a job resumes.
- **The fall zone stays 6 m** after the recall finding: the truth check at 6 m matched 306 known lines against 592 at
  3 m (recall 17 % against 33 %, sag alone, without the no-fall zone and A-frames; `docs/truth-check.md` "The fall
  zone of 6 m"); the user's closing answer "9. a)" keeps the default.
- **The early check of the square rule:** a search stopped early by it writes no funnel counts for that grid.
  **Fixed** (f49026a): the counts are written at the early stop.
- **The truth check's analysis:** `tools/truth_analysis.py` has no reason for a line the rule dropped (20 known lines
  read `unexplained` in the square rule's pass). **Fixed** (f49026a): the analysis names `same_line_square`.
- **The memory constant** `search.LINE_BYTES` (450 B; a reducer row 216 B, counted, not measured): `spec-search.md`
  5.1. **Done** (0e711bb): 900 B a line, from a slot's measured process tree; a reducer row measured at 181-287 B
  (`docs/performance.md` "The memory constant"). **`count_tile`'s sag table**, built per tile: `spec-search.md` 5.2.
  **Done** (4f468d3).
- **A tiled search's line limit counts twice** (kept as a known finding: the user's closing answer "8. a)"): it
  counts the lines the tiles kept before the join, so a pair of squares with lines of two tiles counts twice until
  then: R65 searched as an area in 400 m tiles 3 497 against 3 491 after the join, and a limit of exactly 3 491
  refused the tiled search and accepted the one-grid search (confirmed by a run); the Gozo coast 503 718 against
  503 651. A search within about 0.2 % under the limit can be refused when tiled, and the refusal shows the larger
  count. The memory check is right to count those lines (they are held until the join). Fix: count distinct pairs of
  squares across the tiles for the line limit (keep each tile's keys); the memory check unchanged.
- **Squares on grids not exact in binary** (latent): on a grid whose resolution or origin is not exact in binary (an
  own elevation file with 1.2 m pixels, for example) a tile's pixel coordinates and the whole grid's are not
  bit-identical, so an anchor can fall into another square in a tile than in one grid (3 408 of the centres on such a
  test grid); on grids of 1, 2, 2.5 and 3 m none differ. Not reachable today because of the next finding. Fix: the
  squares from coordinates rounded to the millimetre, or from whole-lattice pixel indices.
- **Outside the task, older than the square rule:** a tiled area on such a grid crashes ("the tile … lies outside
  the grid" from `search._tile_window`: the clipped right edge is rounded up one pixel). In `docs/known-bugs.md`.
- Done at the task's close: CLAUDE.md's table names `samelines.py`; `helpers.LineTable`'s docstring names the
  column `stands_for`; `tools/prune_study.py` reads a `lines.csv` with `stands_for` (it reads only the columns it
  names, so the extra column is skipped; it audits the kept lines and does not weigh them by `stands_for`).
- **Findings of round 4** (2026-11-17): in `docs/known-bugs.md` "Line volume, round 4: known and left"; the design
  review's findings on the result view are step 3c's list in `docs/roadmap.md`.
