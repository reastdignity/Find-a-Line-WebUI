# Line volume: shown (specification, part 3 of 3)

2026-11-14. One of the four files of `docs/line-volume/`; how to read them, the sources and the reference cases:
[spec.md](spec.md). Code is cited as `file:function` of the code after phase 4. "The mock-up" is mock-up 2, version 7,
accepted by the user on 2026-11-14 ("Open points from mockup: 1. ok 2. ok 3. ok 4. ok 5. ok 6. ok"); its behaviour is
stated here in words. Its open point 5 is stale: the kept line of a pair of squares is G-02 a (the least rigging, then
the mean height), as built in phase 4. Parts: **A** today's page, next tier; **B** the result view (structural), with
what it reads from the store; **C** the audit's reading choices; **D** the evidence of parts E2 and E3, answered or
not; **E** contradictions. Items for the user: A-1 to A-3, B-1, B-3 to B-6 (cited from the other files as "view A-n").
The user's closing answers (2026-11-14) set B-1 (the top-level flag is K-17, with a note on K-18); A-1 to A-3 and
B-3 to B-6 are of class "planner" and taken as recommended (`spec.md` section 6).

## A. Today's page, the next tier

### A.1 Decision
- "What 'best' is ranked by" (gate 3, settled list): the mean height. The user: "mean" (2026-11-13), then "Use mean"
  (2026-11-14). Clearance stays the test, a number in every row and a sorting key. Tier: next.
- G-10 a "Mark under 1 m; hide nothing", tier "next (with the rank by mean height)"; the user's "ok" on the mock-up's
  open point 4 (the tight mark). The 1 m stays a working value (G-10's recommendation).
- The headline: phase 4 built the least of it: the head "385 spots / 18,593 lines · 900,880 found" (`ResultSummary.tsx`,
  `ui.result.found` with the tooltip `ui.result.found_title`) and a line's details "Stands for: 38 found lines between
  the same two anchor squares" (`LineDetails.tsx`, `ui.details.stands_for_n`). This part specifies the rest.
- **Decided (the planner):** G-08 a "Top level only" (a view filter) comes with the result view, as G-08 a's tier
  "structural (with the result view)" says; not to today's page before it. Specified in B.

### A.2 Behaviour
**"Best" by mean height.** A spot's best line is its line with the highest `height_mean`; ties by clearance, then
length, then the line's row in the run (the mock-up's order: mean height, clearance, length, row). Every part of
today's page or files that decides "best" or a spot's first line, and the change:

1. `mapping.py:_rank`, `group_lines`; `viewer/src/grouping.ts:compare`, `groupLines`. Today the greedy order
   (default `by` "clearance": clearance, then length) picks the representative and so the spot's members. Change:
   item A-1 (kept, the mock-up's way; or a new rank "mean").
2. `viewer/src/result/model.ts:ResultModel.shownOf`: today the chosen line, else a favourite, else the
   representative. Change: else the member with the highest mean height (ties as above).
3. The members' order (`groupLines` gives them in the grouping's order): the stepper "N of M similar lines" and
   `model.ts:alsoOf` (the 3D view's `&also=`, first 20). Change: by mean height; the 3D view gets the 20 highest.
4. `viewer/src/list.ts:LIST_DEFAULTS` (`sort: "len"`) and `result/view/ResultColumns.tsx` (`{sort: "clr"}` when
   nothing is kept). Change: `hmean` first, descending.
5. `list.ts:savedList` (localStorage `findaline.list`): a kept "clr" or "len" would hide the new order. Change: a new
   key `findaline.list.v2`; `inView` and `open` taken over from the old key, `sort` not (as the mock-up did with a
   key of its own).
6. `result/view/LinesTable.tsx:COLUMNS` (Length, Clear., Height, Lines). Change: Length, Mean height, Clear., Lines
   (the user's "yes" on the row's four columns, 2026-11-14); sorted by the highest point, that value takes the mean
   height's column and heading; the ranking column keeps its arrow.
7. `result/view/LineDetails.tsx` ("up to … m, mean … m" in the facts). Change: the mean height as a stat beside
   length, clearance and highest point (the mock-up's four values).
8. `result/view/LineChooser.tsx` (the spots under a press). Change: length, mean height, clearance.
9. `findaline.py:print_lines` ("largest clearance") and `lines.csv`'s `representative` and row order
   (`runs.row_order`): follow item 1. Kept: unchanged, and README.md says in one sentence that the page's first line
   of a spot is the highest on average, not the file's representative.

A line whose mean height is not known (`hmean` NaN: lines of the Measure tool, `result/measured.ts`) ranks last in
its spot, as `list.ts:sortRows` already puts unknown values last.

**The tight mark.** A line with clearance under `TIGHT = 1` m (one constant in `viewer/src`) carries a small ring with
"!" before its clearance (colour `--warn`) in every list row, in the spot's unfolded rows, in the table of spots under
a press, and a line in its details. A tight line's clearance is rounded down to 0.1 m on the screen, so no row reads
"! 1.0 m". Under a list that holds a tight row, one key line. Nothing is hidden and nothing on the map is marked (the
mock-up has no mark on the map, and it was not tested). Words, by the run's A-frame height `lift` (the head):
- with A-frames of h m (the target rig: 2 m): key "Tight: under 1 m clear at the tightest point, with the h m A-frames
  up."; details "Tight: 0.8 m clear at its tightest point, with the h m A-frames up." (the mock-up's words);
- without A-frames: the same without ", with the … A-frames up" (derived here; item A-3).
What the mark means in the target rig, in the page's words: the clearance already has the 2 m A-frames in it, so a
clearance under 2 m means "needs the A-frames" (0 exceptions on 12.4 M lines, G-10's evidence; counted on the
mock-up's lines: 6 871 and 31 079 exactly). A tight line is one that, with the A-frames up, still has under 1 m under
the webbing at its tightest point; the mark claims no more than that. A person who wants a margin lowers the A-frame
height (G-10 a's "means").

**The headline** (`result/view/ResultSummary.tsx`), with thousands separators as a no-break space (the mock-up's way;
part E3's finding 10: "949160 lines" before phase 4; phase 4's head uses commas: changed to the mock-up's):
- grouped: "{spots} spots · {lines} lines", small "{hidden} hidden by filters" when filters hide lines; not grouped:
  "{lines} lines" as today;
- a run made with the square rule (`found` in the head): a second line "{found} found. **Why so many?**", in place of
  phase 4's "· {found} found". The link opens a box "Why so many lines?" with "Each line stands for the found lines a
  few metres from it: {found} in all. Of all {N} lines of the result:" and three rows with a "Show" checkbox each:
  "{a} need no no-fall zone and no A-frames" (`lift_no_zone` 0), "{b} need the no-fall zone" (`lift_no_zone` > 0,
  `lift_needed` 0), "{c} need A-frames" (`lift_needed` > 0), and a bar of the three shares. A cleared box hides that
  class (a filter like the others: counted in "hidden by filters", cleared by "Clear all"). A run without the zone and
  the A-frames shows the first sentence only. A run without the square rule has no second line and no box.

### A.3 Data
Reads only values stored today (`height_mean` = `Line.hmean`, data.js row `d[17]`; `clearance`; `lift_needed`,
`lift_no_zone`) and phase 4's `stands_for` per line and `found` in the head (`summary.found` of `run.json`). Stored
data: **none** with item A-1 "kept"; with A-1 "a new rank": none in format, but a new run's `group`, `representative`
and row order change (re-baseline, A.7). Old runs: the same page rules apply (their `height_mean` is stored: gate 3's
settled list). Old favourites: unchanged (known by anchors, `keys.lineCoords`). `file://`: unchanged. Browser storage:
the list's key changes (row 5).

### A.4 Interfaces
No command-line option and no `SearchParams` field with A-1 "kept"; with "a new rank", `params.py:group_by` gains
`"mean"` (and its default changes), `findaline.py --group-by`, the web form's grouping field. Texts above go into
`locales/en.json` where the summary's texts live today (the headline's other texts are hard-coded in
`ResultSummary.tsx` now: moving them is in scope). The "Show per spot" choice of More filters: item A-2.

### A.5 Files and pairs
`viewer/src/result/model.ts`, `list.ts`, `result/view/{LinesTable,LineDetails,LineChooser,ResultSummary,
ResultColumns,FilterBar}.tsx`, `locales/en.json`, `viewer/dist`; with A-1 "a new rank" also `mapping.py:_rank`,
`grouping.ts:compare`, `params.py`, `findaline.py:print_lines`. Pairs of `.claude/rules/run-files.md` touched:
"`mapping.group_lines` (Python) and `groupLines` … the same order of the lines (`_rank` / `compare`: clearance,
longest, height)" (only with "a new rank": both get "mean"); "The viewer may show another line of a group than its
representative … but never changes the members of a group" (what "kept" relies on). `.claude/rules/viewer.md`: "the
address's `&also=` lines (`page.ts`, `app/c/ResultPage.tsx` `view3dOf`, the model's `alsoOf`)" (row 3's order).

### A.6 Screens
Today's page; from the mock-up only its rows, tight mark, headline and box. Desktop and both phone profiles.

### A.7 Tests
- `tests/test_viewer.py` (the model in Node): a spot's shown line is its highest mean height (ties: clearance,
  length); the stepper walks in that order; `alsoOf` gives the highest 20; a kept "clr" under `findaline.list` does
  not decide the new list's order; NaN mean height ranks last.
- Tight mark: 0.99 m marked and shown "0.9 m", 1.0 m not marked; the key line appears only with a tight row; the
  words with and without A-frames.
- Headline: separators; the "found" line and the box only on a run with `found` in the head; the three counts add up
  to N; a cleared box hides its class.
- With A-1 "kept": `tests/test_units.py::test_grouping_as_before`, `test_grouping_matches_python` unchanged, every
  regression checksum unchanged. With "a new rank": both tests get "mean"; every regression entry whose run groups by
  the default re-baselined, said in the commit.
- `tools/ui_shots.py` on the result page, desktop and both phones, light and dark, looked at.

### A.8 Acceptance
- Effect E2 "The headline count misleads" and E3 "No place to start" (gate 1, section 3). Checked on a target-rig run
  of BAH made with `--same-line-square 5`: the first list row is the spot whose shown line has the highest mean
  height; every row shows mean height and clearance; every row under 1 m is marked and no other.
- For reference (counted on the mock-up's lines, kept by K-01 'One best line per pair of anchor cells', not by
  G-02 a): tight lines 2 622 of 43 127 (BAH) and 15 554 of 79 821 (MGp); part P3f: 14-60 % of a spot's first 10 lines
  are under 1 m when ranked by the mean (G-10: 14-57 %). Recount on the app's run; no number is a target.

### A.9 Waves
One wave: one agent owns `viewer/src` and `locales/en.json` (and, with "a new rank", `mapping.py`, `params.py`,
`findaline.py`). Effort: low with "kept", medium with "a new rank" (re-baseline).

### A.10 Risks and rollout
Tight lines come to the top (part P3f: 14-60 % of a spot's first 10 under 1 m): the mark is the answer (G-10). A
person's kept list order is dropped once (row 5). With "kept", Python's printed representative and the page's first
line can differ: said in README.md. Rollout: viewer only; deploy with `viewer/dist`; no migration.

### A.11 Needs the user's word
- **A-1. Does "best" change the spots or only the line shown?** (a) Keep the grouping by clearance; the page shows each
  spot's highest-on-average line and orders its lines so (the mock-up's way: its spots are production's grouping;
  D-12 a "Spots are fixed"); no stored change, no re-baseline. (b) A new grouping rank "mean" as the default: the
  greedy groups form around high lines; every regression run's checksum changes; old runs keep their groups.
  Measured: nothing on (b)'s spots. Recommendation: (a).
- **A-2. "Show per spot" (Most clearance / Longest / Highest)** in More filters regroups the lines today. With A-1 (a):
  add "Highest on average" first and as the default, which keeps the groups and only changes the shown line; or
  leave the three. Recommendation: add it (so the page's own control names the rank in use).
- **A-3. The tight words on a run without A-frames** (formula runs, or sag without `lift`): the mock-up shows only the
  2 m rig. Recommendation: the words without the A-frame clause, as above.

## B. The result view of mock-up 2, version 7 (structural)

### B.1 Decision
D-11 d 'How a result is organised' (three levels, the list as a tree), D-12 a 'From a place to one line' (spots fixed,
a door), N-04 'The Best step of the map's switch' (yes), N-06 'A crowded tap on a phone zooms in' (yes), the four
dialog answers and every answer on versions 1 to 7 (the user, 2026-11-13 and 2026-11-14: "Keep `spot`", "pale lines",
"both", "2 and 0.6 looks good here", "10m is ok", "default on", "lines not beaten", "Use mean", "yes" (in view, the
row, the pick's name), "Keep a)", "It's okey as now", and "1. ok … 6. ok"). Gate 3: G-08 a (a filter in the view, on
at the start), G-12 a ("No cap in the search; the page shows the best"), both "structural (with the result view)";
it is built on G-06 a (the Arrow store, columns in the page: `spec-store.md`). Tier: structural.

### B.2 Behaviour (each item: the mock-up's state by its name)
The frame is today's ("Today's page stays as the frame"): list left, map, details right; on a phone the map above the
sheet, the details at the sheet's top. The phone layout is used under today's narrow rule (the mock-up: under 760 px,
and its phone frames). Every count below is of the lines that pass the filters.

1. **Levels and the switch** (all states). On the map's top: a segmented control Auto / Area / Spots / Lines, help
   "How much the map draws. Auto follows the zoom.", and "Best" with 10 / 30 / 100 / All (disabled at Area). Auto:
   Area above 2 m per pixel, Lines below 0.6, Spots between; it changes level only past 7 % beyond a threshold (enter
   below 0.93 × it, leave above 1.07 ×); pressing Auto picks the level from the zoom at once. Another button holds its
   level at every zoom ("Lines held, far out"); the status line then adds "Held by you." and "Back to Auto". Start:
   Auto, Best 10. A small result opens without the area (Tatras at Spots on a desktop: "ok").
2. **In view.** A spot is in view when its shown line, as a segment, crosses the map's view rectangle (a line under a
   control counts; a line touching one point does not). The spots in view in the list's order; the best N are the
   first N; with Best 10/30/100 they carry B1 … BN (no numbers with All, when refused, or above 100).
3. **Area** ("First view"). Sharp squares of 25, 50, 100 or 200 m: the smallest whose side is at least 26 px, else
   200. A line counts in the squares of both anchors (once when both lie in one); a spot once per square. Colour by (a
   select heading the legend): "Spots anchored in a square" (start), "Lines anchored in a square", "Best clearance, m",
   "Longest line, m"; five classes `--layer-1..5`, four breaks evenly in log10 between the 2nd and 98th percentile
   (whole and rising for counts), fill 62 %, the value inside a square of 26 px or more. Legend note: "A spot is
   counted in every square where one of its lines is anchored." (hidden on a phone, whose legend is one row scrolling
   sideways). The picks of "Start here" are drawn as bold lines with P1 … P4. A press on a square zooms to it, under
   Auto to at most 0.96 m per pixel (so Auto lands on Spots). Status: "Area. Zoom in for spots." ("Area." when held).
4. **Start here** (list at Area). "Highest on average" (highest mean height), "Longest with at least 3 m clear",
   "Highest above the ground" (highest point), "Most lines in one spot" (that spot's shown line); a pick in the spot of
   an earlier pick, or whose middle lies within 100 m of an earlier pick's, is left out. A pick's row: its name on a
   line of its own, then the four numbers. "From a top edge" waits for the access mark (`spec-search.md` section 3).
5. **Spots** ("Zoomed in: spots"). The best N spots' shown lines bold (3 px) and numbered; every other spot in view as
   its shown line, pale (1.5 px, 24 %). Status "Spots: best 10 of 283 in view" / "Spots: all 283 in view".
6. **Lines** ("Close: lines"; "Best 30"). Each best spot's lines not beaten that cross the screen, thin (1 px, 30 %),
   its shown line bold with a halo; other spots pale. **Not beaten**: in a spot's order (mean height, clearance,
   length), a line is hidden when an earlier line not hidden is at least as long and at least as clear (so at least
   as high on average): mean height, length, clearance, choice (a) ("Keep a)"). With All: every passing line that
   crosses the screen, of every spot, thin (22 %), no bold, no numbers. Status "Lines: 10 of 95 spots in view" /
   "Lines: all {n} in view". A numbered spot is in view by its shown line only.
7. **The limit** ("All: too many"). Above 5 000 lines to draw no bold or thin line is drawn, only the pale lines of
   every spot in view; the status, marked: "Too many lines to draw here: 7 278. Zoom in, or choose 100." (100 for
   All, 30 for 100, 10 for 30, only "Zoom in." for 10).
8. **Numbers and shapes.** B: a box with round corners; P: a diamond; L: a six-sided tag; A: a circle; "here": a ring
   of dashes; another spot: a pale line. A B or P number sits on the longest piece of its line that is on the map with
   the whole shape 2 px clear of the switch, zoom buttons, credits (button and open text), status line, hint and its
   "?", and legend; tried at 0.5, 0.36, 0.64, 0.24, 0.76, 0.14, 0.86 of the piece (then the next piece); the first
   position at least one box (32 × 23 px) from every earlier number wins, else the farthest; nearer than a quarter
   box: left out (the better spot keeps its number). No free piece: no number on the map, the row keeps it. Numbers
   are placed best first, measured at every full redraw and placed again (at most twice) when a control changed its
   size. L numbers: at 82 % of the free piece toward the far end. A1, A2: on the anchors. The legend lists exactly
   the shapes and colours on the map now.
9. **Presses** (open point 2 "ok"). A number's shape is a target first (its box + 2 px with a mouse, at least 40 ×
   40 px with a finger; of several, the nearest middle): B and P select their spot's bold line, L its line, A opens
   "Lines from here". Else lines within 8 px (mouse) or 20 px (finger), per spot its nearest; ranks bold (numbered,
   pick, selected), thin, pale: bold wins where it is within the tie (3 px / 8 px) of the nearest thin line; a thin
   line where clearly nearer; pale only alone. The spots within the tie of the nearest, at most 6: one selects;
   several with a mouse open the table "{n} spots here: which one?" (numbered first by number with their shapes, then
   by distance as "1.3"; length, mean height, clearance; a numbered row selects the bold line); with a finger
   ("Crowded tap (phone)") the map zooms in one level around the point, flashes the lines 1.8 s and says "Several
   spots here. Zoomed in. Tap again."; at the last zoom the table opens. A finger is the last pointer type, or the
   phone layout. Nothing hit at Area: a square zooms; elsewhere a press ends a selection. A mouse hover thickens the
   line under it; a long press on a shape is a press.
10. **A selected spot** ("A spot selected"). Details: "Spot 7.1 · 104 lines"; long, mean height, clear, highest
    point; the tight line; "‹ Line 1 of 104 ›" stepping through every passing line of the spot by mean height; the
    line's `stands_for` in phase 4's words ("Stands for: 41 found lines between the same two anchor squares", or
    "this line only: no other was found between its two anchor squares"; the mock-up's "Stands for 41 found lines a
    few metres apart."); "Open spot ›", "Lines from anchor A1", "Lines from anchor A2". On the map the spot's other
    lines thin (all of them, 80 %), the line with a dark halo, A1 and A2; the rest dimmed to 30 % (squares 60 %). Its
    sector opens and pages until its row; the desktop list scrolls to the row, the phone sheet to its top. A row
    moves the map only when its line is not inside the view less 8 % or is under 60 px long ("ok"). The selected row
    pressed again, ×, or Esc ends the selection.
11. **Lines from here** ("Lines from here"; open point 3 "ok"). Opened by a right click (desktop), press and hold
    (phone), a press on A1/A2, or the two buttons. The passing lines with an end within 10 m ("here"); none: the
    message "No line starts within 10 m of this point." (an open fan stays). By mean height; lines whose far ends lie
    within 20 m form one row under the highest; at most 40 rows ("The best 40 are shown."). A line that is a B or P
    line now and starts within 10 m comes first with its number (nearest start first, then the lower number); the
    others are L1, L2 …. Text "648 lines start within 10 m of this point, to 29 far ends." Sort: Mean height (start),
    Clearance, Length, Height diff. (smallest first), Direction (by bearing); numbered rows stay first. Row: shape,
    length, mean height, clearance, height difference (signed, near end to far end, 0.1 m), direction ("SE 141°").
    Map: the fan's lines with halos, their numbers, the dashed ring; it moves only when a far end is outside the view.
    A line or row selects that line; a press on an empty point closes the fan and keeps the spot; a second ends the
    selection ("It's okey as now"); a right click or long press elsewhere moves it; "Close"; Esc.
12. **The hint.** "Right click the map: the lines from that point" with a mouse, "Press and hold the map: the lines
    from that point" with a finger or pen and always in the phone layout. Desktop: on the map beside the status line;
    phone: the sheet's first line under the map. Its × hides it and leaves a round "?" beside the status line that
    shows it again; kept in browser storage. Before any press the word follows `pointer: coarse`.
13. **The list.** Top block: "Start here" at Area; else "Best in view: 10 of 283" with rows B1 … and a button "Show
    30" / "Show 100" / "Show all" (raises Best); with All "In view: 95 spots", at most 100 rows, "The first 100 of N.
    The tree below has them all."; "No spots in view." Below, "All spots" with "Sort by" mean height (start),
    clearance, length, highest point, lines; about ten sectors ("A sector open"), the first open: "Sector 3 ·
    north-west", "{k} spots · up to {x} m mean height", "{n} lines · {a}–{b} m", a button "Show on the map" (fits the
    sector's shown lines, flashes them 2.4 s); 20 rows a page, "Show more (27 more)" adds 40. A row: the B/P shape or
    the spot's label "sector.n" (fixed), the line colour (clear / over trees or buildings), length, mean height (the
    highest point when sorted by it), clearance with the tight mark, lines, a door "›". The ranking column's heading is
    marked "▾". Keys: Enter, Space, arrows. "No line passes the filters."
14. **Headline, filters, "Top level only"** ("All levels", "Why so many"). Headline and "Why so many?" as in A.2.
    Chips: Length (range), Clearance (at least), Height (highest point at least), "Top level only" (pressed at the
    start), More filters (today's others), "Clear all" (leaves "Top level only"). Under the chips: "Top level only is
    on: 6 831 of 43 127 lines hang lower on the same face and are hidden. Press the chip to see them." / "… is off:
    the 6 831 lines that hang lower on the same face are shown too." The chip hides every line whose `top` is 0
    (B.3), everywhere: squares, counts, picks, list, shown lines.
15. **The tight mark**: as A.2, in rows, the table of spots, "Lines from here" and details; key lines under each list.
16. **Empty**: "No spots in view. Zoom out or move the map." on the map.

**What the app needs that the mock-up does not have** (the mock-up says "Fake" or "Not here"): loading the run (G-06
a: `spec-store.md`; the load progress of `RunLoading.tsx` stays); the map's real projection (in-view and squares in
the run's CRS metres, as the lines are stored); base layers, orthophoto, the shore and coarser overlays (their boxes
join the controls of item 8); the profile card, the 3D view and a line's links (today's, on the selected line);
favourites (the star, their filter; whether a favourite is a spot's shown line: item B-3); Compare (other runs: item
B-4); Measure; Download (the store's exports); "Open spot" (the next mock-up, D-12's cards: until then item B-5);
`#line=` links (select the line, open its spot); the share page.

### B.3 Data: what the view reads
Every column, its type and the wave that adds it are in the one schema of a run's lines: `spec-store.md` 1.3. The
view reads the anchors `x1, y1, x2, y2` (unrounded, as `keys.lineCoords` needs), `len`, `clr`, `hmax`, `hmean`,
`e1`/`e2` (for `dh`, derived), `stands_for`, `over`, `lift_needed`/`lift_no_zone` (for `need`, derived), and today's
columns for More filters, favourites and the profile; from the result view's first wave `spot`, `top`, `by_spot` and
the head's `sectors`, `box`, `lengths`; `found` from the head.
**Decided (the planner): computed in Python at saving** (once, deterministic, the same on every number of threads, as
the mock-up's data was made): the spots (`mapping.group_lines`, item A-1); the order inside a spot (`by_spot`); the
sectors: Ward clustering (scipy) of each spot's shown line's ends into at most 10 sectors, west end first; numbered by
their best spot's mean height; the word by 8 directions from the run's centre to the mean of the shown lines' middles,
"centre" within min(150 m, 12 % of the lines' extent); the spots numbered by their first line's mean height; `top` by
the rule of item B-1 (decided: K-17 'Higher wins on a face', as the accepted mock-up; `tools/prune_study.py`'s rule
`higher_wins`: plan buckets of 8 m cells from (0, 0), both ends; a bucket whose mean anchor elevations span 10 m or
more keeps only the lines within 10 m of its highest). One new function `mapping.view_columns` gives them to
`linestore.write`, called by `search.save_run` (old runs are not converted: they are removed at store wave 4,
`spec-store.md` section 2).
In the browser, at every filter or view change: the shown line per spot (its first passing line), not beaten, in
view, best N, squares, picks, numbers, the fan, the table of spots.
Pairs (`.claude/rules/run-files.md`): "`mapping.group_lines` … and `groupLines` …: the browser must produce the same
groups": the result view does not group (spots are fixed, D-12 a; the distance slider leaves with the checkbox the
switch replaces), so the pair holds only while today's page reads old runs. New pairs to write into the rule: the
order inside a spot (Python, `by_spot`) and the page's "first line" and "not beaten" (which assume it); `top`
(Python) and the chip's count text.

### B.4 Interfaces
No command-line option, no `SearchParams` field, no route of its own (the store's routes are in `spec-store.md`).
Texts: every quoted text of B.2 into `locales/en.json`, the word "spot", "athlete" for the person on the line. Browser
storage: the list's sort and the hint's state under a new key (try/catch).

### B.5 Files and pairs
`viewer/src/result/` (`model.ts` for spots, order, filters, the shown line; `ResultMap.ts` the canvas: levels,
squares, strokes, numbers, presses; `view/` the list, tree, details, fan, chooser, hint, summary), `viewer/src/
list.ts`, `filters.ts`, `locales/en.json`, `viewer/dist`; Python: `mapping.view_columns` and `linestore.py`. Rules:
`viewer.md` (`style-src 'self'`: no `style=` in HTML strings: the mock-up's HTML rows become components; the `&also=`
pair), `run-files.md` (above; favourites by `keys.lineCoords`), `browser-tests.md`, `view3d.md` (the 3D link of the
selected line), `coverage-map.md` (the squares' `--layer-1..5` tokens are the layer's).

### B.6 Screens (the mock-up's states; desktop 1400 × 900, phones 390 and 412, light and dark)
First view, Zoomed in: spots, Close: lines, Best 30, All: too many, Lines held far out, A spot selected, Lines from
here, A sector open, All levels, Why so many, Crowded tap (phone): each as in the accepted mock-up's state of that
name (B.2 states each in words). Not taken from the mock-up: its strip, notes and fake buttons; its frame sizes
(today's layout and sheet); the relief picture.

### B.7 Tests
The mock-up's own checks, ported to Playwright tests of the result page on a target-rig run with the square rule:
- ranking: best first; line 1 and the steps down; the start's sorting and clearance as a choice; mean height and
  clearance in every row; the tight mark and details; "not beaten" equals a count by mean height, length, clearance;
  the fan's order;
- view: every numbered line crosses the screen; numbered = the best of those that cross; "of M in view" equals a
  count;
- numbers: a number whole on the map, under no control, within 3 px of its line; none for a line without a free part;
  no two within 4 px;
- presses: a shape, a long press, a line, "here", the table, a table row;
- the fan: the hint, the hint again, empty, a fan line, moving it;
- states: each state of B.6, the 5 000 limit, the legend lists the shapes on the map, storage blocked, the Area
  squares.
Unit tests in `tests/test_viewer.py` for the pure parts (in view, squares, breaks, picks, not beaten, fan groups).
Python: sectors and `top` equal `tools/prune_study.py`'s rule on a made-up table. Regression entries: none change
(the view and new columns only; exports unchanged). Truth check: not asked (no anchor or line rule).

### B.8 Acceptance (targets of gate 1, section 4; the mock-up's numbers are the mock-up's, not the app's)
- T7 (at most 3 steps from a spot to a line of a chosen direction, phone): press a B number (1), press and hold an
  anchor or A1 (2: the fan has a direction column), press the row (3) (estimate from the behaviour; part E3 counted
  6-8 today). Measured by a Playwright script on BAH, phone 390 and 412.
- Lines drawn in the first view: the mock-up draws on BAH (desktop, far) 44 strokes at Area, 622 at Spots, 772 at
  Lines Best 10; MGp 219 / 758 / 878; never more than 5 000 (counted on version 7 by the mock-up's agent). Target:
  never above 5 000 strokes in any state; counted by the page's own count in the test.
- T6 (a filter or grouping change at most 0.3 s, desktop) and redraw: the mock-up's redraw script time 0.2-1.6 ms
  desktop, 1.2-6.4 ms phone 390 slowed 4 times; to the second frame 26-31 ms desktop, 27-137 ms phone (indicative).
  On the goal case (GZ1 with the square rule, 503 651 lines) a filter change recomputes every line: measure with
  `fal:run:*` marks under the exclusive lock.
- T5 (first picture within 3 s, heap under 500 MB, never a crash) and T4 (10-20 MB sent): `spec-store.md`.
- T9 (local density): not set in the sources (gate 1: "to be set once measured"); item B-6.

### B.9 Waves (after the store of G-06 a, `spec-store.md` wave 2)
1. Python: spots' order, sectors, `top` (`mapping.view_columns`), written to the store (one agent: those files and
   their tests). Medium.
2. The view's core in `ResultMap.ts` and `model.ts` (levels, in view, squares, best N, strokes, numbers, presses).
   High. Parallel with 3 once the model's interface is fixed.
3. The list, tree, details, fan, chooser, hint, summary in `view/` and `locales/en.json`. Medium.
4. Today's features joined (profile card, 3D link, favourites, Compare, `#line=`, share page, overlays). Medium.
5. The ported checks, `tools/ui_shots.py` review on the desktop and both phones, `viewer/dist`. Medium.

### B.10 Risks and rollout
- The mock-up held at most 79 821 lines; the goal case keeps 503 651: the per-change loops (recompute, squares) are
  O(lines); measure before the wave closes.
- The real map's projection and overlays (more controls, numbers with fewer free positions: on a phone 1 to 10 of 10
  numbers showed in the mock-up).
- A real long press and WebKit were never tested on the mock-up; a real phone test is the user's gate-1 "yes, later".
- Rollout with the store: a run without the view's columns (every run before view B1) opens in today's page; store
  wave 4 removes such runs on the user's word (`spec-store.md` section 2) and drops the reader of `data.js`. Today's
  page, which reads the store from store wave 2, stays until the result view is complete (B5).

### B.11 Needs the user's word
- **B-1. Which rule is the top-level flag: decided, K-17 'Higher wins on a face'** (the user, 2026-11-14: "2. a) .
  Add a note on it - it might be useful for increasing % of lines found from slack map"), as on the accepted mock-up
  and in part P3b's count for V-20 'Top level only: switch and height slider' (BAH 70.6 % kept). **The user's note:**
  K-18 'Higher wins unless clearance loses' kept 590 of the 592 matched known lines against K-17's 589 (part P3b;
  BAH 70.7 % kept), so it "might be useful for increasing % of lines found from slack map": a candidate to measure
  when the share of known lines found is worked on (a line in `docs/roadmap.md`), not a change of this view.
- **B-3. A favourite in a spot:** today it is the spot's shown line (`shownOf`); the mock-up has no favourites.
  Options: keep that; or the best line stays shown and the favourite is marked. Recommendation: keep today's rule.
- **B-4. Other runs (Compare):** their lines in the levels, the squares and best N, or drawn apart. Not measured
  (gate 1's D4). Recommendation: drawn apart as today's overlay, not counted in best N.
- **B-5. "Open spot" before the cards' mock-up:** the door hidden, or it selects the spot. Recommendation: hidden.
- **B-6. A number for T9 (local density of the first view):** none set; the 5 000-line limit and Best 10 stand in.

## C. The audit's reading choices (part P2, the audit tool's report) against the page and the view

| # | The tool's reading (`tools/prune_study.py`) | Today's page | The result view | Differ? |
|---|---|---|---|---|
| 0 | A spot: production's grouping at max(20 m, 2 px), by clearance | the same, regrouped in the browser at the slider's distance | the same spots, fixed (A-1 a) | no (A-1 a); yes (A-1 b) |
| 1 | "Not worse": saved value at least the dropped line's, no tolerance; clearance, height, length, share high | no such notion; the grouping ranks | "not beaten": at least as long and as clear, earlier by mean height; no tolerance | yes: mean height, not highest point; no share high |
| 2 | Length: "not shorter" is not worse | - | the same (≥) | no |
| 3 | Exposure = the share of the line high | sort key `highPct` | not shown, not a sort key | yes |
| 4 | A violation: no kept line within 8 m | - | "Stands for N found lines" (5 m squares) | yes: squares, not a radius |
| 5 | Best line per sort key: 12 keys of the page | 13 sort keys (`list.ts`) | 5 sort keys | yes: 8 keys not offered |
| 6 | Top of a stack: within 10 m of the highest, 8 m cells | none | the same rule (K-17) for "Top level only" | no (B-1 K-17) |
| 7 | Sectors of direction: 30° from grid north | no direction in 2D (part E3, finding 5) | direction only in "Lines from here" (8 words and degrees); "sector" is a group of spots by location | yes: two meanings of "sector" |
| 8 | Known lines: the truth check's tolerance; 8 m | - | not concerned | - |

Two more radii meet here: "here" 10 m and a fan row's far ends within 20 m (B.2 item 11), against the tool's 8 m.
What follows: the audit protects the best line per 12 keys, the view offers 5 (row 5): a rule audited "no loss"
on `highPct` or prominence is not seen through the view's sorting. Recommendation for the roadmap, not a decision
here: name the tree's groups "sectors" and the tool's "direction sectors" in the docs, so the two do not mix.

## D. The evidence (parts E2, E3) and the part that answers each

| Problem (source) | Answered by |
|---|---|
| One string of at most 536 870 888 characters; 2.3 M lines crash silently, the script fallback kills the tab (E2) | `spec-store.md` (G-06 a: columns, no data.js) |
| Heap 2.5 GB at 2.29 M lines; WebKit 1.5-2.5 × Chromium (E2) | `spec-store.md`; B draws at most 5 000 lines; a phone's limit unknown: not answered (real device, gate 1) |
| First picture 0.5-11.2 s (E2; T5) | `spec-store.md`; B adds no grouping at load (spots stored) |
| Every filter change regroups: 1.0-3.5 s (E2; T6) | B: no regrouping; per-change loops stay O(lines): not measured at 0.5 M (B.8) |
| Whole-view coverage a poor measure (E2; T9) | not answered: no local density number (B-6) |
| no-cache and gzip at every open (E2) | `spec-store.md` section 4 |
| MG5 crashes with no message (E3) | `spec-store.md` |
| Home offers the crashing run first, no size on its card (E3) | the size: `spec-store.md` section 4 (F-30); the order of Home's offer: not answered |
| The mat of lines (E3) | B: levels, best N, pale lines, not beaten, the 5 000 limit |
| The grouping slider cannot reach 200 or 500 m (E3) | B: spots fixed, slider gone (D-12 a; V-18 'Grouping distance follows the zoom' parked) |
| A line of a chosen direction by trial, 4-8 steps (E3) | B item 11: "Lines from here" with a direction column (T7: 3 steps, estimate) |
| The 3D fan is off on phones (E3) | B item 11 in 2D on phones; the 3D view itself not changed |
| Choosing another line moves the spot in the list (E3) | B items 10, 13: a row keeps its label and position; rows sort by the spot's best line, and stepping changes only the selected line |
| Unfolding a 150 539-line spot freezes 15 s (E3) | B: no unfolded rows; the stepper walks one line at a time |
| The chooser at every attempt on phones (E3) | B item 9 (shapes first, bold wins, crowded tap zooms) |
| Headline without separators; "a few metres" against 3 714 lines in 5 bearings (E3) | A.2 headline; the square rule (phase 4) makes "a few metres" true |
| Filters need knowledge: 23 controls, 13 sort keys (E3) | B: four chips first, 5 sort keys; More filters as today |
| A phone's free map is small, the shore legend covers a third (E3) | B: the numbers avoid the controls (item 8); the shore box joins them; the sheet's size not changed: not answered |
| Old runs list orange lines first, Height "–" (E3) | A: mean height first; orange first: not answered |
| Share link: the same mat, no size (E3) | B applies to the share page (B.2, the app needs); its size: `spec-store.md` section 4 |
| The search form gives no volume warning (E3) | `spec-search.md` sections 1 and 2 (G-04) |
| Legend shows "Favourite" without any; pill over the star (E3) | B: the legend lists only what is on the map (item 8) |

## E. Contradictions found between the sources
- G-08's evidence names K-18 for "Top level only"; the mock-up computes K-17, as does part P3b's count for V-20
  (70.6 % at BAH = K-17's). Settled by the user on 2026-11-14: K-17 (item B-1), K-18 kept as a note.
- The mock-up's lines are kept by K-01 (the most clearance per pair of 5 m squares); gate 3's G-02 a, as built, keeps
  the least rigging, then the mean height. Every mock-up count (tight 2 622, top level 6 831, strokes) is therefore of
  other lines than the app's; the behaviour holds, the numbers are recounted on runs made with `--same-line-square`.
- "Top level only" was once listed under the next tier; G-08 a's tier "structural (with the result view)" holds
  (decided, A.1).
- Mock-up 2's first version had "Top level only" off at the start; the user later said "default on" (2026-11-13):
  the user's words hold (B.2 item 14).
- Phase 4's head separates thousands with commas and its details say "between the same two anchor squares"; the
  mock-up uses a no-break space and "a few metres apart". This file takes the mock-up's separator (A.2) and phase 4's
  words for the details (B.2 item 10).
