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
| Refusal advice | The four `too_many_lines*` refusals name only the changes that apply, at most four, in the measured order | `docs/roadmap.md` "Advice of a refusal for too many lines (2026-11-14)" |
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
| 4. + store wave 4: text files and `file://` end | the same | the same | about 60 MB | as step 3 | through the app only (`findaline.py view`) | E |
| 5. + store wave 6: br once at saving, immutable caching | the same | the same | about 75-80 MB | 17-23 MB br (2.7-3.7 s at 50 Mbit/s, 14-18 s at 10); a reopen sends nothing | as step 3 | E |
| 6. + view wave B1: spots, sectors, top level, the view's order in the store | the same | the same | about 80-85 MB | about 19-27 MB | as step 3 | E |
| 7. + store wave 7: the ranges of a kept line (store U1) | the same | the same | about 105 MB (five ranges), 160 MB (fifteen) | 24-32 MB (five), 37-49 MB (fifteen) | as step 3 | E |
| 8. + view waves B2-B5: the result view | the same | the same | as step 6 or 7 | as step 6 or 7 | at most 5 000 strokes drawn; no grouping at load; a filter change on 503 651 lines not measured | E (mock-up 2) |

So T10 (the goal case opens on a desktop) is met by step 3 (estimate); T3 (a folder within the public limits at most
300 MB) by step 4; T4 (10-20 MB sent) only without ranges and only at the low end of the estimates. Sources: step 2
from W4; steps 3-7 from `spec-store.md` sections 4 and 6 (parts P5 and E2); step 3's gzip is br × 1.13, part P5's
gzip-6 to br-5 ratio on MG5 (estimate).

## 4. All solutions
| Solution | Decision | Tier | Where | Depends on | Effort |
|---|---|---|---|---|---|
| Basic form with 'My rig' and goals | G-11 a; D-10 a; N-01 | next | search 1 | the square rule (built); count 5.5 a; the rigs' migration (next free number) | medium (server), high (page) |
| The size of a search from a sample | G-04 a; N-02, N-05 | next | search 2 | measurement 5.5 b for searches with the square rule (search U-6) | high |
| Access mark of three states | G-09 a; D-08 c | next | search 3 | a mock-up of where it shows; search U-9, U-11 | high |
| Lip anchors against the known lines | G-07 a | a measurement first | search 4 | the PC free; search U-12 | medium |
| The memory constant `LINE_BYTES` | G-05 (finding) | next | search 5.1 | exclusive runs when the PC is free | medium |
| `count_tile`'s sag table per tile | finding | next | search 5.2 | – | low |
| 'Sea cliffs' without its wall-angle limit | G-11 a | next | search 5.4 | count 5.5 a; search U-2 | low |
| Owed counts: goals with the rule; a sample of kept lines | G-11, G-04 | a measurement first | search 5.5 | 5.3 | medium each |
| Columns in the page from `data.js` | G-06 a; D-05 c | structural | store 1 (wave 1) | – | high |
| The Arrow store beside today's files | G-06 a; D-04 a | structural | store 1 (wave 2) | pyarrow as a new dependency | medium ×2 |
| Exports on request | G-06 a | structural | store 1 (wave 3) | wave 2; store U4, U9 | medium |
| Text files and `file://` end; `view` | G-06 a; D-04 a | structural | store 1 (wave 4) | wave 3 | high |
| Old runs converted | G-06 a | structural | store 2 (wave 5) | wave 4; store U5 | medium |
| What is sent: br, immutable, size, warning | G-06 a; F-10, F-12, F-30, T-34 | structural | store 4 (wave 6) | wave 2; store U12; a small mock-up | medium |
| The ranges of a kept line | G-03 b | structural | store 3 (wave 7) | wave 2; store U1 | medium |
| Renaming a run | the user, 2026-11-13 | next | store 5 (wave 8) | a small mock-up | low |
| "Best" by mean height, tight mark, headline | gate 3 settled list; G-10 a | next | view A | view A-1 | low ("kept") or medium |
| The result view of mock-up 2 | D-11 d, D-12 a, N-04, N-06; G-08 a, G-12 a | structural | view B | store wave 2; view B-1 | B1 medium, B2 high, B3-B5 medium |

## 5. The order of building
| Step | Work (part, wave) | Waits for | Parallel with | Effort |
|---|---|---|---|---|
| 0a | search 5.3, then 5.5 a: every goal with the square rule on 16 cases, 'Sea cliffs' variants | – | 0b, 1a | medium |
| 0b | search 5.5 b: an estimator of kept lines from a sample | – | 0a, 1a | medium |
| 0c | search 4: four truth-check passes with and without lip anchors | the PC free; search U-12 set | anything that does not measure | medium |
| 1a | view A: best by mean height, tight mark, headline | view A-1 (or the planner's default) | all of step 1 | low / medium |
| 1b | search 1, waves 1-2: the rigs' server, then the Basic page | 0a reported to the user before the review (wave 3) | 1a, 1d, 2a | medium, high |
| 1c | search 2: the sample in the worker | 0b (for Basic searches; without the square rule it may go first) | 1a, 1b | high |
| 1d | search 3: `access.py`, the search and files; the page after its mock-up | search U-9, U-11; a mock-up | 1a, 1b | high |
| 1e | search 5.1 (exclusive, the PC free), 5.2, 5.4 (after 0a); phase 4's findings (section 7) | as named | any | low-medium |
| 2a | store wave 1: columns in the page | – | store wave 2's Python half | high |
| 2b | store wave 2: Python store (B) at once; the page's reader (C) after 2a | 2a for C | 2a (B) | medium ×2 |
| 2c | store wave 3, then wave 4 | 2b; store U4, U9 for wave 3 | 2d, 2e, 3a | medium, high |
| 2d | store wave 6: what is sent | 2b; store U12; its mock-up | 2c, 2e | medium |
| 2e | store wave 7: ranges | 2b; store U1; store U2's mock-up for the page | 2c, 2d | medium |
| 2f | store wave 5: old runs converted | 2c (wave 4); best after 3a, so conversions carry the view's columns; store U5 | 3b-3d | medium |
| 2g | store wave 8: renaming a run | its mock-up | anything | low |
| 3a | view B1: spots, sectors, `top`, `by_spot` into the store | 2b; view B-1 | 2c-2e | medium |
| 3b | view B2 (map core) and B3 (list, details, fan) | 3a; B3 once B2's model interface is fixed | each other | high, medium |
| 3c | view B4: today's features joined | 3b; view B-3, B-4, B-5 | 2f, 2g | medium |
| 3d | view B5: ported checks, `tools/ui_shots.py`, `viewer/dist` | 3c | – | medium |

Steps 0 and 1 hold the next tier; steps 2 and 3 the structural one. Tests and searches run one after another under
`tools/test_lock.py`; measurements that read seconds or memory wait until the user says the PC is free.

## 6. The choices still open for the user
Classes: **before** = decide before building that work; **mock-up** = decided at that task's mock-up; **measure** =
decided by a measurement first; **planner** = taken as recommended by the planner unless the user objects.

| Id | The question | Options | Recommendation | Blocks | Class |
|---|---|---|---|---|---|
| search U-1 | "Tension grows with the length" in the rig's window | (a) left out until an option exists; (b) built with the form | (a) | search 1 | planner |
| search U-2 | 'Sea cliffs' wall-angle limit | (a) none; (b) a wide one from the count | (a) | search 5.4 | measure (5.5 a) |
| search U-3 | Texts changed from mock-up 1 | 1.2's texts; "Can be very large: slow, may not open on a phone." on "Everything" | as listed | search 1 | planner |
| search U-4 | The access row in Basic before the mark exists | (a) left out; (b) build the mark first | (a) | search 1 | planner |
| search U-5 | Where the rig in use is kept | per browser; with the account | per browser | search 1 | planner |
| search U-6 | The sample for searches with the square rule | (a) only searches without it; (b) found estimate × kept share | on 5.5 b's numbers | search 2 | measure (5.5 b) |
| search U-7 | Who samples | (a) the web worker only; (b) also the command line | (a) | search 2 | planner |
| search U-8 | The access mark's switch | (a) an option, on in the web form; (b) always on | (a) | search 3 | planner |
| search U-9 | The alpine variant of the access measure | (a) in; (b) out | (a) | search 3 | before |
| search U-10 | Where the access mark shows | a mock-up before code | a mock-up | search 3's page | planner |
| search U-11 | The access study's pictures | the user looks at them first | look first | search 3 | before |
| search U-12 | The bar for lip anchors | at least 98 % of the matched known lines kept | 98 % | search 4's verdict | before |
| store U1 | Which ranges a kept line carries | (a) five; (b) five and mean height; (c) fifteen | (b) | store wave 7 | before |
| store U2 | A line that passes only by its ranges; where ranges show | (a) drawn as any line, ranges in details; (b) a mark of its own | (a), with a details mock-up | store wave 7's page | mock-up |
| store U3 | Water and filled metres in the ranges | (a) left out; (b) computed per found line | (a) now | store wave 7 | planner |
| store U4 | An export once made | (a) kept; (b) made per download | (a) CSV, (b) GeoJSON | store wave 3 | before |
| store U5 | Old runs | (a) automatic; (b) by hand; (c) none | (a) VPS, (b) PC | store wave 5 | before |
| store U6 | Circles' profiles of every line | (a) kept; (b) representatives only | (a) now | store wave 4 | planner |
| store U7 | Light view, tiers, nested results (F-31, F-24, K-33) | (a) parked; (b) a further wave | (a) | – | planner |
| store U8 | The phone warning's threshold | (a) none until a real-device test; (b) provisional | (a) | store wave 6 | planner |
| store U9 | Who may export | (a) owner, administrator, demo; (b) share links too | (a) | store wave 3 | planner |
| store U10 | `--html` after `file://` ends | (a) accepted one release; (b) removed | (a) | store wave 4 | planner |
| store U11 | Filtered exports, GeoPackage, KML (F-32) | (a) a wave after wave 3; (b) parked | (b) | – | planner |
| store U12 | Compression at saving | br-5 (`brotli`, new); gzip-6; zstd-3; none | br-5, after the libraries' comparison | store wave 6 | before |
| view A-1 | Does "best" change the spots or only the line shown | (a) only the line; (b) a new grouping rank | (a) | view A | planner |
| view A-2 | "Highest on average" in "Show per spot" | add it first; leave the three | add it | view A | planner |
| view A-3 | The tight words without A-frames | without the A-frame clause | as specified | view A | planner |
| view B-1 | The rule of the top-level flag | K-17 'Higher wins on a face'; K-18 'Higher wins unless clearance loses' | K-17 | view B1 | before |
| view B-3 | A favourite in a spot | today's rule (shown); the best shown, the favourite marked | today's rule | view B4 | planner |
| view B-4 | Other runs (Compare) in the view | counted in levels and best N; drawn apart | drawn apart | view B4 | planner |
| view B-5 | "Open spot" before the cards' mock-up | hidden; selects the spot | hidden | view B3 | planner |
| view B-6 | A number for T9 (local density) | none set | the 5 000 limit and Best 10 stand in | – | planner |

Decided by the planner (no question): "Top level only" comes with the result view (G-08 a); the top-level flag and
the sectors are computed in Python at saving.

## 7. Findings of phase 4 to fix later
- **The fall zone's migration and unfinished jobs:** an unfinished tiled sag job of the web app starts over after
  migration 17: the int 3 against the float 3.0 in the search's hash (`_search_hash`), so the hash differs.
- **The early check of the square rule:** a search stopped early by it writes no funnel counts for that grid.
- **The truth check's analysis:** `tools/truth_analysis.py` has no reason for a line the rule dropped (20 known lines
  read `unexplained` in the square rule's pass).
- **The refusal advice** does not offer the square rule.
- **The memory constant** `search.LINE_BYTES` (450 B; a reducer row 216 B, counted, not measured): `spec-search.md`
  5.1. **`count_tile`'s sag table**, built per tile: `spec-search.md` 5.2.
- **A tiled search's line limit counts twice:** it counts the lines the tiles kept before the join, so a pair of
  squares with lines of two tiles counts twice until then: R65 searched as an area in 400 m tiles 3 497 against 3 491
  after the join, and a limit of exactly 3 491 refused the tiled search and accepted the one-grid search (confirmed by
  a run); the Gozo coast 503 718 against 503 651. A search within about 0.2 % under the limit can be refused when
  tiled, and the refusal shows the larger count. The memory check is right to count those lines (they are held until
  the join). Fix: count distinct pairs of squares across the tiles for the line limit (keep each tile's keys); the
  memory check unchanged.
- **Squares on grids not exact in binary** (latent): on a grid whose resolution or origin is not exact in binary (an
  own elevation file with 1.2 m pixels, for example) a tile's pixel coordinates and the whole grid's are not
  bit-identical, so an anchor can fall into another square in a tile than in one grid (3 408 of the centres on such a
  test grid); on grids of 1, 2, 2.5 and 3 m none differ. Not reachable today because of the next finding. Fix: the
  squares from coordinates rounded to the millimetre, or from whole-lattice pixel indices.
- **For `docs/known-bugs.md`** (outside the task, older than the square rule): a tiled area on such a grid crashes
  ("the tile … lies outside the grid" from `search._tile_window`: the clipped right edge is rounded up one pixel).
- Also noticed by phase 4: CLAUDE.md's table does not name `samelines.py`; `helpers.LineTable`'s docstring is to be
  brought in step; `tools/prune_study.py` was not checked with the extra column `stands_for`.
