# Line volume: before and during the search (specification, part 1 of 3)

2026-11-14. One of the four files of `docs/line-volume/`; how to read them, the sources and the reference cases:
[spec.md](spec.md). Code is cited as `file:function` of the code after phase 4. The target rig: the sag model with a
leash fall space (`fall_zone`) of 6 m (the default since phase 4), a no-fall zone at the ends (`end_zone`) of 5 m and
A-frames (`anchor_lift`) of 2 m. The square rule (built in phase 4): `--same-line-square M`
(`SearchParams.same_line_square`; 0 = off, the default, else 2 to 20) keeps one line per pair of anchor squares of
M × max(1, resolution) m (`samelines.side`); the side really used is `params.same_line_side` in `run.json`; a kept line
carries `stands_for` (the found lines it stands for, itself included) and the run `summary.found`. Items that need the
user's word: U-1 to U-12 (cited from the other files as "search U-n"). The user's closing answers (2026-11-14) set
U-12 (lip anchors become an option only at 98 % of the matched known lines kept); the items of class "planner" are
taken as recommended (`spec.md` section 6).

## 1. The Basic search form with 'My rig' and goals

### 1.1 Decision
G-11 'The goals of the Basic form', answer a: "Basic always uses the square rule; the goals stay" (the user, gate 3,
2026-11-14); tier next, with the Basic form. It builds gate 2's D-10 a 'Who sets the rigging in Basic' ("My rig sets
the rigging; presets set the goal") and N-01 'The Basic search form itself' (yes). The form is mock-up 1, version 3,
accepted: "Basic search mockup looks good" (the user, 2026-11-13). The user's answers that bind it (2026-11-13,
verbatim): "Several, with names" (rigs); "Account" (where a rig is saved); "set 500m" (Basic's radius); "yes" (another
goal switches Where back after "Sea cliffs"); "add it" (Save as my rig in Advanced); "ok" (the size word follows the
rig); "to basic" (what "reset" restores); "for now always basic" (the tab a visit opens); "Try to make it more compact
- if possible" (the phone's bar); and on 2026-11-14 "Athlete sounds better. Change to it everywhere". G-12 a "No cap
in the search; the page shows the best" removes the mock-up's cap of 10 lines per spot.

### 1.2 Behaviour
**Where.** New search (`viewer/src/app/c/NewSearch.tsx`, `search/useSearch.ts`, `search/SearchPanel.tsx`) gets the
switch "Basic · Advanced". Every visit and every new search open Basic. "Edit & run again" opens Basic when the job's
request fits a goal and the rig in use (all eleven goal fields equal one goal's, the seven rig values equal the rig's,
the square rule is 5, every other field is at the app's default), else Advanced (T-04 'Switch Basic and Advanced
without losing values'); a job made before the form has no `same_line_square`, so it opens Advanced. The command line
has no Basic. **Basic, top to bottom:** "What are you looking for?" (five goal cards, "The best lines here" chosen);
"Where" (today's block; the radius starts at **500 m** in both tabs, `SearchParams.radius` stays 1000 m); "Reaching the
anchors" (U-4); "Rigged as"; "Show every setting ›". The bar: the size word, km², source and grid (from today's
`/api/estimate`), the receipt line, "Start search ›".

**What Basic sends:** an ordinary search request (N-01), every field at the app's default except:

| Goal (id) | Values (mock-up 1, version 3) |
|---|---|
| The best lines here (`best`) | `min_length` 30, `max_length` 300, `max_anchor_diff_m` 10 (no cap per spot: G-12 a) |
| Long and exposed (`long`) | `min_length` 100, `max_length` 600, `max_anchor_diff_m` 30, `min_height` 30, `min_high_share` 50 |
| First highline (`first`) | `min_length` 15, `max_length` 60, `max_anchor_diff_m` 3, `nmpt` "reject" |
| Sea cliffs (`sea`) | `min_length` 30, `max_length` 300, `min_drop` 30, `max_wall_angle` 30 (a fault: 5.4); Where: Along cliffs → Coast, band 100 m |
| Everything (`everything`) | nothing (30-1000 m, 50 m: the defaults) |

Every Basic request also carries, explicitly: `model` "sag"; the rig's seven values (`pretension`, `stretch`,
`webbing_weight`, `athlete_mass`, `fall_zone`, `end_zone`, `anchor_lift`); `same_line_square` **5** (G-11 a; "5 pixels
wide, at least 5 m", G-01 a). Explicit, because the form otherwise stores only values that differ from a default, and
a stored request would change meaning when a default moves (as the fall zone's did in phase 4, which needed a
migration of stored sag requests). The goals' fields (`GOAL_FIELDS`): `min_length`, `max_length`,
`max_anchor_diff_m`, `max_anchor_diff`, `nmpt`, `high_above`, `min_height`, `min_mean_height`, `min_high_share`,
`max_wall_angle`, `min_drop`; a goal sets all eleven (its value or the default); values "fit a goal" when all eleven
equal it. **"Sea cliffs"** remembers Where's mode and switches to Along cliffs → Coast (band 100 m); another goal puts
the mode back; a mode chosen by hand forgets it. Hint: "Sea cliffs searches along the coast. Say where, under Where."
(+ "Another goal brings your point back." while remembered).

**The rig:** a name (1-30 characters, spaces collapsed, no control characters, each once per account, compared
casefolded) and seven values: `end_zone` 0-20 m, `anchor_lift` 0-3 m, `fall_zone` ≥ 0, `pretension` and
`stretch` > 0, `webbing_weight` and `athlete_mass` ≥ 0 (`SearchParams.check`'s bounds). At most **10** per account.
- Without a saved rig Basic uses the starting rig, never stored: sag, no-fall zone 5 m, no A-frames, leash fall space
  6 m, 2.5 kN, 5 %, 70 g/m, 80 kg (mock-up 1, the dialog's answer 2). The row: "Used until you set yours:", the
  summary, "Is this how you rig?", "Yes, save it" (saved as "My rig"), "Change". Start is never blocked.
- With rigs: "Rigged as" and "N rigs" (", the most you can keep" at 10); the name of the rig in use opens the list in
  the page (name and summary each; "+ Add a rig", disabled at 10: "You have 10 rigs: the most you can keep. Delete one
  to add another."); "Change". Under it "sag · no-fall zone 5 m · A-frames 2 m" and "2.5 kN pretension, 5 % stretch
  at 10 kN, 70 g/m webbing, athlete 80 kg, 6 m leash fall space". The rig in use: U-5 (this file: per browser).
- The rig's window (a dialog over Basic; titles "My rig", "Change a rig", "A new rig"): "Say once how you rig. Every
  Basic search uses the rig you choose. Advanced can change it for one search."; Name; No-fall zone at the ends;
  A-frame height; Leash fall space; under "More: pretension, webbing, athlete" Pretension, Webbing stretch at 10 kN,
  Webbing weight, Athlete mass; the cost line; "Saved with your account."; "Delete this rig" (then "Delete “name”?",
  "No, keep it", "Yes, delete it"), "Cancel", "Save as a new rig", "Save" ("Save my rig" for a first or new rig). New
  names offered: "My rig", then the first free "Rig 2", "Rig 3" …. Errors: "Give the rig a name.", "You already have
  a rig named “name”.", "Give the copy a new name: “name” is taken.", "You can keep 10 rigs. Delete one first." and
  the bounds in the words of `SearchParams`' errors. Esc, Cancel or a press outside close it unsaved; focus goes
  back. "Tension grows with the length" is left out: U-1.

**Advanced** is today's form with: Where shared with Basic; "Lines to look for" as the five goal cards and "Custom"
(replacing 'Typical highline', 'Long lines', 'Short & low': the dialog's answer 4), a card setting its eleven fields
and Basic's goal; the field "One line per pair of anchor squares" (`same_line_square`, built) at Basic's 5. Note on
top: "Filled from Basic: <goal>, <rig>." and "N values differ from Basic's: they have a dot. “reset” puts Basic's value
back." (or "Nothing differs from Basic yet. A value you change gets a dot."). A dot marks a value that differs from
Basic's (the goal and the rig in use); a topic's badge counts them; "reset" restores Basic's value. The topic
"Clearance model" ends with "Save into “name”" (the seven values into the rig in use at once; disabled when equal;
"Saved into “name”. Every Basic search uses it now.") and "Save as a new rig" ("Save as my rig" without rigs: the
window, filled; disabled at 10). The formula model is in Advanced only; Advanced changes the rigging for one search
unless saved.
**Between the tabs.** To Advanced (tab, "Show every setting", a part of the receipt, which opens its field): Basic's
values. To Basic: silent when the values fit a goal and the rig, else "Basic cannot show N of your settings", the
list in words, "Stay in Advanced to keep them. Or reset them to Basic's values: <goal>; <rig>: <summary>.", "Stay in
Advanced" (focused), "Reset them to Basic's values".

**The receipt line** (T-05 'A receipt line: what Basic chose'), without the cap: "30–300 m · anchors within 10 m of
height · trees marked · <rig>: sag, no-fall zone 5 m, A-frames 2 m · access marked, no line left out"; <rig> is the
saved rig's name, "Rig" (the starting rig) or "Rig for this search"; "+ N more settings" counts other fields off the
app's default, `same_line_square` at 5 counting as covered; "named “…”". A Where problem ("Select the centre of the
search: click the map.", …) replaces it and disables Start. "access marked": U-4. Phones: the compact bar: one line
"<goal or Custom> · <lengths> · <rig>" that unfolds the receipt, km², source and grid; "Lighter: …" moves into "?".

**The size word** (N-05 'A rough size word in the form'; G-04 a "the word in the form as a hint"): "Light",
"Heavier", "Heavy", "Very heavy": one step each for sag, a no-fall zone, A-frames, and one for lines spanning 900 m or
more, else an area above 3.2 km²; the causes named ("sag, no-fall zone 5 m, A-frames 2 m"). Its "?" with the factors
measured in the study (part P4): "sag ×7 to ×113 (×15 in the middle), the no-fall zone of 5 m ×2 to ×25 (×4.5),
A-frames of 2 m ×1.3 to ×4.6 (×1.9); a leash fall space of 6 m instead of 3 m ×0.08 to ×0.75 (×0.56)"; "One 1 km
circle in Poland: 2 015 lines with the simple formula, 605 729 with sag, a no-fall zone of 5 m and A-frames of 2 m"
(KOB, parts E1 and P1); "This is a rough guide from other places, not a count for this one." At "Very heavy" with
sag: "Lighter: the simple formula, in Advanced. Usually about 15 times fewer lines (7 to 113)." The mock-up's note
"Measured with 3 m of leash fall space" goes. Changed texts: U-3. **Start** posts `/api/jobs` as today.

### 1.3 Data
- **The rigs** in `jobs.sqlite` (beside the favourites), by the next free migration number when it is built (17 is
  taken by the fall zone of stored sag requests, phase 4): `CREATE TABLE rigs (id INTEGER PRIMARY KEY, user_id
  INTEGER, name TEXT NOT NULL, name_key TEXT NOT NULL, rig TEXT NOT NULL); CREATE UNIQUE INDEX rigs_name ON rigs
  (IFNULL(user_id, 0), name_key);` `user_id` = users.id, NULL the local app's user; `name_key` the name casefolded;
  `rig` JSON of the seven values (kN, %, g/m, kg, m, m, m). No times (the approved privacy entry names only the name
  and the values). Order by id. **Stored-data decision: automatic migration** (a new empty table).
- `Jobs.adopt_runs` gives the local user's rigs to the first administrator as it does the favourites, while that
  account holds fewer than 10 and no rig of the same name; the rest stay with NULL.
- A Basic job's request is an ordinary one. Old jobs, runs, favourites, run.json, the search hash: unchanged;
  `file://` not concerned. The browser keeps `findaline.rig` (the id in use) in `localStorage`, inside try/catch; a
  missing or unknown id takes the first rig, none the starting rig; deleting the rig in use takes the first.

### 1.4 Interfaces
- Routes, each with `Depends(current_user)`, own rigs only (another's id: 404): `GET /api/rigs` → `{"rigs": [{"id",
  "name", "values"}], "max": 10}`; `POST /api/rigs` `{"name", "values"}` → `{"id"}`; `POST /api/rigs/{id}` `{"name"?,
  "values"?}`; `DELETE /api/rigs/{id}`. Codes: `rigs_max` (409, `QuotaExceeded`, `refused(user, "rigs", …)`),
  `rig_name`, `rig_name_taken` (400), the bounds as `SearchParams`' codes (`end_zone_range`, `anchor_lift_range`,
  `positive`, `not_negative`) through one `params.check_rig`. Audit action **`rig`** `{"do": "add"|"change"|"delete"}`,
  no name or value. `jobs.Jobs.rigs/add_rig/change_rig/delete_rig`; `RIGS_MAX = 10`, `RIG_NAME_MAX = 30`.
- `params.PRESETS` becomes the goals (`best`, `long`, `first`, `sea`, `everything`, `custom` None), `PRESET_FIELDS`
  the eleven fields; `web.presets` as today. The Where rule of "Sea cliffs" lives in the page.
- `locales/en.json`: `preset.<id>` = "The best lines here", "Long and exposed", "First highline", "Sea cliffs",
  "Everything", "Custom"; `goal.<id>.text` = "30–300 m, anchors within 10 m of height.", "100–600 m, at least 30 m
  above the ground over half the line.", "15–60 m, anchors at the same height, clear of trees.", "Lines that leave the
  cliff over the water, 30–300 m.", "Every line your rig allows, 30–1000 m." (mark "heavy"), "your own values";
  1.2's texts as `basic.*`, `rig.*`; the three `error.*`. `preset.typical`, `preset.short` go;
  `intro.search.example_forest` names "First highline".
- Privacy page, word for word as the user approved it (2026-11-13, with "athlete" of 2026-11-14): a new entry
  **"Rigs"**: "The rigs you save for your searches: the name you give each and its values (no-fall zone, A-frame
  height, leash fall space, pretension, webbing stretch and weight, athlete mass); at most 10. Why: to fill your
  searches with them. Kept until you delete them." "Audit log" adds "rigs saved, changed and deleted (not their names
  or values)". "10" from `jb.RIGS_MAX`. `audit.py`'s docstring and `ACTIONS` follow. No new `SearchParams` field,
  option or run file.

### 1.5 Files and pairs
`params.py`, `web.py`, `jobs.py`, `audit.py`, `locales/en.json`, `viewer/src/search/*` (with `matchGoal` and
`notInBasic`: does a request fit a goal and the rig; what Basic cannot show), `app/c/NewSearch.tsx` ("best"),
`app/api.ts`, `search/SearchIntro.tsx`, `viewer/dist`, `README.md`, `docs/code-map/web.md`, `viewer.md`.
`web-app.md` pairs touched: "`locales/en.json` and its users" (preset titles, `t()` keys, `error.<code>`); "the form"
(bounds from `web.schema`; no new limit: 10 rigs is a safeguard like `FAVOURITES_MAX`); "The privacy page … a new
stored field … changes it too"; "Every state-changing endpoint … records an `audit` event"; the pitfalls "Every
endpoint checks who asks" and "number fields: `defaultValue`". `search-pipeline.md`: none.

### 1.6 Screens
The accepted mock-up 1's states, desktop (form 460 px, map beside, bar across) and phones (map on top, compact bar),
light and dark: first visit, saved rig, rigs, rig chooser, ten rigs, each goal (best, long, first, sea, everything),
the rig's window, Advanced, the return dialog, "Try a search" (filled with a search location and "The best lines
here"; its Home button belongs to another mock-up), the compact bar. Not taken: the bar before the compact one; "The
best 10 lines of each spot." and "Best lines kept per spot" (G-12 a); "Tension grows with the length" (U-1); "(In
this mock-up: kept in this browser.)"; the drawn map and made-up km², source, grid; the 3 m note.

### 1.7 Tests
- Server: the routes round-trip; the 11th rig `rigs_max` with an audit `refused`; a name taken in another case; 404
  for another user's; audit rows without names or values; the new migration keeps the previous version's rows;
  `adopt_runs` as 1.3; the privacy sentences verbatim; `test_every_route_has_its_access_rule`;
  `test_labels_topics_and_presets` with `goal.<id>.text`; `check_rig` refuses what `SearchParams` does; each goal's
  `preset_values` validates.
- Viewer (Node): each goal × the starting and a saved rig gives the table's request (model, seven values,
  `same_line_square` 5); `matchGoal`/`notInBasic`; dot and reset; the receipt; the size word of every state. Browser
  (Edge, from PowerShell): first visit → Start; save, choose, rename, copy, delete; the return dialog; "Edit & run
  again" of a Basic and an old job. `tools/ui_shots.py` on the desktop and both phones. Regression: no entry changes.

### 1.8 Acceptance
Every state of 1.6 as on the accepted page; 1.7's requests exact; at 390 px the form keeps at least the 396 px of the
mock-up's version 2 (part P6). Effects A2 'Small searches hit the limit' and T1 (all 16 reference cases end with a
usable result) of gate 1: with the square rule, 15 of 16 reference cases are predicted under the line limit (G-14's
evidence, a prediction); the owed count 5.5 a gives the number per goal and is reported to the user before the form
ships (G-11: "with one count before the form is built").

### 1.9 Waves
1. Server (Opus, medium): `jobs.py`, `web.py`, `audit.py`, `params.py`, server keys, tests. 2. Page (Opus, high),
overlapping 1 once 1.4's shapes are frozen: `viewer/src/search/*` and the rest, `npm run check`, `node build.mjs`,
`viewer/dist`. 3. The planner: full pytest, browser tests, `tools/ui_shots.py` sheets. 5.5 a before 3.

### 1.10 Risks and rollout
Before section 2 is built, a Basic search is refused only at the line limit, as today; a second device starts with
the first rig. VPS: deploy; `jobs.sqlite` migrates at the web's start; old jobs keep their requests.

### 1.11 Needs the user's word
- **U-1 "Tension grows with the length"**: shown in the accepted window ("ok, it will be set as a default later", the
  user, 2026-11-13) but no search option exists (the country layer's `sg.TensionTable` only) and the approved privacy
  entry omits it. Measured: nothing below 300 m, +15 to +26 % lines on GZ2 above (part P3c, banded). (a) leave it out
  until a task builds the option; (b) build it with the form (field, stored value, privacy entry reworded). Rec.: (a).
- **U-2** 'Sea cliffs' without its wall-angle limit: 5.4.
- **U-3 Texts changed from the accepted page:** the card of "The best lines here" without its cap sentence; the "?"
  with the target rig's factors and the KOB example; "about 15 times fewer lines (7 to 113)"; with the square rule
  "Can be millions of lines" on "Everything" is no longer true for most areas (2-4 % of the lines remain, G-11):
  keep it, or "Can be very large: slow, may not open on a phone." Rec.: 1.2's texts and that sentence.
- **U-4 The access row**: false until the mark (section 3) exists. (a) leave the row and "access marked" out until
  the mark ships; (b) build the mark first. Rec.: (a).
- **U-5 The rig in use**: per browser (`localStorage`, like the app's other preferences) or with the account (a stored
  value the approved entry does not name). Rec.: per browser.

## 2. The size of a search before it starts, from a sample

### 2.1 Decision
G-04 'The size of a search before it runs', answer a: "The sample on the server, the word in the form as a hint";
tier next. Gate 2: N-02 'Estimate the lines before the long search' (yes; S-03 'Sample anchors to estimate the
lines'), N-05 (yes: the word, 1.2).

### 2.2 Behaviour
- **Where:** in the worker's computing phase, inside `search` (the web process does no search work): after step 1 and
  step 2's anchors, before step 3's full pair search. Not in `/api/estimate` (it runs before the download; the sample
  needs the terrain). The form's word stays a hint; the number comes after Start.
- **When:** where today's early check exists: `plan.early_stop` and (`limits.lines_max` or `plan.memory`)
  (`search:_early_check`). The command line and the regression set never sample (files and seconds as before); the
  web worker does (U-7). `Limits.lines_early_stop` switches both off.
- **How** (part P4's method with the production kernel): the useful anchors of a tile's core (one grid: all) are
  ordered by `numpy.random.default_rng([seed, tile])`, seed = the first 8 hex digits of `_search_hash(plan)` (the same
  request, the same estimate); the sample is the first k = max(1, round(0.02 × N)). `_pair_search` runs with `first`
  = the sample's mask and a counting sink (no line held): each valid line counts once, from its first anchor.
  Estimate = Σ over tiles of lines(sample) × N / k; standard error from the per-anchor counts (Horvitz-Thompson); shown
  as ± 2 standard errors (96 % coverage, part P4). A tiled area samples every tile (window by `_tile_data`, its
  anchors, not kept) before the first tile's step 3.
- **The decision** (part P4's band; at 2 %, 1 wrong of 390): above 1.25 × `lines_max` (1.875 M) refused at once, code
  `too_many_lines_estimate` (n, lo, hi, max) with phase 4's refusal advice in its order; below 0.8 × (1.2 M) it goes
  on; between, it goes on with "close to the limit". The memory budget: the same band on `_check_lines`' `fits`,
  `too_many_lines_memory_estimate`. The full search's checks stay and decide at the end.
- **Seen** (job messages through `Jobs(public=True)`): "About 3.2 million lines (2.6 to 3.9 million) with these
  settings."; close: "That is close to this site's limit of 1.5 million: the search goes on and stops if it passes
  it."; refused: "About 24 million lines (21 to 28 million) with these settings, at most 1.5 million on this site:
  <the refusal advice>."
- **Disagreement:** accepted but over the limit: today's early check refuses. Refused although under it: measured once
  in 390 at 2 %. Estimate and final count go to `job_funnel` to watch the rate.
- **Square rule on** (every Basic search): built as sampled squares, since the line limit counts kept lines: 2 % of
  the rule's squares holding a useful anchor of the core, a pair of squares counted only from its first square, which
  estimates the kept lines (part M2's candidate 1b: at 2 % worst x1.19 on the rows of 1 M kept or more, the band 0
  wrong of 485; the user's "2%" of 2026-11-15, so U-6 needs neither of its options).
- **Cost** (indicative, part P4): 1 % takes 4-11 s where the full count takes 8-181 s untiled; tiled, step 1
  dominates (GZ1 50 s with the sample against 93 s). 2 % untimed: between the 1 % and 5 % columns (0.1-16.7 s for
  steps 2-3; an estimate). An accepted search pays it on top.

### 2.3 Data
No new stored data: messages (deleted with the job's events) and the step `"estimate"` of the existing table
`job_funnel` (`jobs.FUNNEL_STEPS`, counts without users). Stored-data decision: none. Old jobs, runs, `file://`: as
before.

### 2.4 Interfaces
`search.SAMPLE_FRACTION = 0.02`, `REFUSE_FACTOR = 1.25`, `ACCEPT_FACTOR = 0.8`; `search.sample_estimate(plan, data,
found, core, sag_table, tile) -> (lines, variance, k, n)`; `search._estimate_check(plan, estimate, se, pixels)`; the
two codes (`error.*`, no option names); notes `estimate_lines`, `estimate_close`; README's `LINES_MAX` row: "estimated
from 2 % of the anchors before the search's pairs; a search far above it is refused then". No option, field or route.

### 2.5 Files and pairs
`search.py`, `jobs.py`, `messages.py`, `locales/en.json`, `README.md`, `docs/code-map/search.md`, tests, and
`tools/estimate_study.py` (part P4's sampling study as a tool with a test: per case, fraction and seed, the estimate,
its interval and the exact count). Pairs: `search-pipeline.md` "`_early_check` refuses only what `_check_lines` would
refuse too": the estimate's refusal is a prediction, not a lower bound; one bullet names it apart; "Search limits …
must refuse before the cost they guard". `web-app.md`: codes and texts through `Jobs(public=True)`.
`country-layer.md`: `_pair_search`'s arguments unchanged but `first`. Threads: an exact count.

### 2.6 Screens
None: the messages appear in today's job page.
### 2.7 Tests
A fraction of 1 gives the exact count; seed s gives the tool's estimate on a small grid; 1 and many threads equal;
the band's three outcomes and codes; no sample with `limits=None` (R entries' `lines.csv` byte-equal) or with
`same_line_square` set. The tool reproduces part P4's table (78 rows × 5 seeds, its seed rule). Regression: none
change.

### 2.8 Acceptance
T2 (gate 1: "told before the pair search"): every target-rig case refused for lines in part P1's table (MG, BAH, STR,
GZ2, GZ1, MLT, V1, V2, V3) is refused by the estimate before step 3 with the public limits. At 2 %, part P4's rows of
1 M lines or more: worst ×1.34, 99 % within ×1.25; the band at most 1 wrong of 390. Seconds within part P4's
(indicative).

### 2.9 Waves
0. 5.5 b. 1. `search.py` and the tool (Opus, high). 2. Texts, README, docs (Opus, low), parallel. 3. Review: full
pytest, R13 and R1-R5, the acceptance runs.

### 2.10 Risks and rollout
A wrong refusal (1 in 390); seconds on every public search; step 2 twice per tile; another hash, another sample. VPS:
deploy, no migration; compare `job_funnel` "estimate" with "lines" for some weeks.

### 2.11 Needs the user's word
- **U-6** If 5.5 b finds no estimator of kept lines as accurate as part P4's, Basic searches are never sampled:
  (a) ship for searches without the square rule only; (b) a band on found lines times a measured kept share. On
  5.5 b's numbers.
- **U-7** (a) the web worker only (this file); (b) also the command line, printing the estimate. Rec.: (a).

## 3. Access mark of three states

### 3.1 Decision
G-09 'Ease of access to the anchors', answer a: "A mark of three states, no limit"; tier next; gate 2 D-08 c 'Ease of
access to the anchors'. The accepted form says "The result marks anchors you can walk to. No line is left out." No
filter removes lines.

### 3.2 Behaviour
- **The measure** (part P3d, its constants kept): per anchor "can walk", "cannot tell here", "cannot walk". Open
  ground: under 30°, not water, with data, in a connected area of 1 ha or more. Standing ground: walkable within 3 m of
  the anchor, 2 m below to 3 m above it. Walkable: ≤ 40°, not water, no knife-edge crest (strict); ≤ 50°, crests
  allowed (loose). Can walk: the strict walk of ≤ 500 m from open ground reaches it (whole-metre heights, 90 % of a
  sample: also on lightly smoothed ones). Cannot tell: only the loose walk reaches it; or smoothing changes a
  whole-metre answer; or unreached while its walkable ground comes within 500 m of the end of the data. Else cannot
  walk. Flat lakes held as data count as water unless the heights are whole metres.
- **Computed** once on step 1's grid of the whole area (filled terrain, water) as a `uint8` grid (`access.npy` in a
  tiled search's work folder, in memory for one grid); each tile takes its window (`_tile_data`): one grid's answers.
  Each line takes its two anchors' answers after the pair search (as `water_px`). The measure needs 533 m around an
  anchor; the grid reaches `_margin` (300 m by default) beyond the area, so edge anchors read "cannot tell" more often.
- **Cost:** about 0.3 s per megapixel (part P3d, indicative): the Gozo coast's 126 Mpx about 40 s (estimate).
- **When:** a search option, off by default; the web form sends it on (U-8). Old runs show no mark.
- **Shown:** three colours and a legend; part P3d's proposal: green "you can walk to it", amber "cannot tell here",
  dark purple "hangs in the face: cannot walk to it" (agrees with V-35 'Anchors coloured by place on the wall' on
  78-95 % of sure ends). Where: U-10.
- **Worth** (part P3d): known ends against random steep pixels 0.47 (0.5 = none), 0.70 on gentle pixels. Line ends
  can / cannot tell / cannot: KOB 23.7/21.8/54.5 %, BAH 12.6/19.7/67.7 %, BEL 37.7/14.1/48.2 %, DOL 36.5/26.5/37.1 %,
  MGp 0.0/1.1/98.9 %, GZp 1.7/6.8/91.5 %.

### 3.3 Data
Option on: `access1`, `access2` (0 cannot walk, 1 cannot tell, 2 can walk) in `lines.csv`, `lines.geojson`, `data.js`,
`lines.js` (before the profile; the head names them, as `END_FIELDS`), and, once the store of `spec-store.md` exists,
two uint8 columns there; `run.json`'s params hold the option. Off: no column, today's bytes. `Line` and favourites get
optional `access1`/`access2` (null without). Stored-data decision: none (new runs only; old runs, jobs, favourites and
`file://` as before).

### 3.4 Interfaces
`SearchParams.access: bool = False` ("mark whether a person can walk to each anchor: can, cannot, cannot tell"),
`--access`, topic "anchors", `field.access.*`, a README row; unset, `_search_hash` as before. Line details: "Anchor 1:
you can walk to it" ….

### 3.5 Files and pairs
New `access.py` (numpy/scipy/numba, a port of part P3d's measure), `search.py`, `runs.py`, `mapping.py`, `saving.py`,
`params.py`, `web.py` (`FavouriteLine`), `viewer/src/types.ts`, `favourites.ts`, the page (after U-10), README, docs.
Pairs: `run-files.md` "A new column goes into that reference too", "new columns go before it" (the profile), the
favourites' trio; `search-pipeline.md` "tiles give exactly the lines of one grid", `PIXEL_BYTES` measured again, "A
new search field leaves `_search_hash` as before when unset". `country-layer.md`: not in the cube (it needs computing
beyond the count: the user's rule of 2026-11-05); it would fit with a 0.53 km margin (part P3d).

### 3.6 Screens
None accepted: a mock-up first (the user's rule for UI work): the marks on the map, the line's details, the legend,
desktop and both phones.
### 3.7 Tests
Made-up terrain: meadow and wall (can), mid-face ledge (cannot), 45° (cannot tell), whole metres, the data's end;
tiles = one grid; option off byte-equal (`test_saved_text_as_before`, the R entries); the four files and
`test_saved_by_children_as_in_process` with the columns; one new R entry with the option; part P3d's shares (3.2,
"Worth") reproduced on its six target-rig tables by the repository's `access.py`.

### 3.8 Acceptance
Part P3d's answers equal on the six tables; about 0.3 s per megapixel (indicative); checksums unchanged with the
option off. E7 'Trust' (gate 1): no number set; the user judges part P3d's pictures (U-11).

### 3.9 Waves
1. `access.py` and tests (Opus, high). 2. Search and files (Opus, high). 3. Mock-up, then the page after the user's
"ok". 4. Review: full pytest, the new R entry, `tools/ui_shots.py`.

### 3.10 Risks and rollout
The weak separation may mislead (the help says the site cannot see "paths, fences, private land or trees"); edge
anchors read "cannot tell"; memory per pixel grows. VPS: deploy, no migration.

### 3.11 Needs the user's word
- **U-8** (a) an option, off by default, on in the web form (this file; checksums stay); (b) always on (every R entry
  re-baselined). Rec.: (a).
- **U-9 The alpine variant** ("cannot walk" becomes "cannot tell" where open ground is under 5 % of the land within
  250 m; MGp's ends then 99.9 % "cannot tell"): (a) in; (b) out (part P3d's main measure). Rec.: (a), no confident
  "cannot walk" on alpine walls.
- **U-10** Where the mark shows: a mock-up before code. **U-11** The user looks at part P3d's pictures of five cases
  (BAH, MGp, BEL, DOL and a quarry) before building (G-09's recommendation).

## 4. Lip anchors measured against the known lines (a measurement, not a feature)
**Decision.** G-07 'Fewer, better anchors', answer a: "Today's anchors; measure the lips against the known lines";
tier next. Nothing changes in the search.
**The pass.** The prototype `--lip-anchors off|only|add` (K-26 'Rim anchors: the lip, steep pixel or not'; commit
3280032 on the branch `line-volume-p3b`: `helpers.py`, `params.py`, `search.py`) rebased onto the code after phase 4,
on a branch never merged. Four truth-check passes (`docs/truth-check.md` section 4: the first pass's `clusters.json`,
SlackMap's data of 2026-11-08 from the cache; `run --parallel 4` under `--heavy`; `analyse`; `report --no-pictures`),
each `--extra "--model sag --end-zone 5 --anchor-lift 2"` (the target rig, where lips matter: the user's note on K-26),
the fall zone at its default of 6 m: P-A today's anchors; P-B `--lip-anchors only`; P-C, P-D the same with
`--same-line-square 5` (lips and squares were never counted together, G-07). The phase 4 pass of
`docs/truth-check.md` "The square rule" ran in the default rig, not the target rig, so it is not P-C.
**Compared** per type (highline, midline, all): known lines matched, recall, terrain recall, the reasons of P-B's new
misses, lines found. By count too (part P3a's route): lips with the square rule on BAH, GZ2, MG, DOL (lips alone
131 641, 527 901, 1 022 189, 195 324: part P3b).
**The number that decides** is the user's (U-12, decided 2026-11-14, "6. a)"): lip anchors become an option only if
P-B and P-D keep at least 98 % of P-A's and P-C's matched known lines; else they go to the roadmap as measured and
not taken. For scale, of 592 known lines matched in the first pass's setting:
the square rule keeps 581 (G-02), the whole-metre guard 580, a 3 m thinning 499, both ends on a rim 338 (part P3b).
**Privacy:** counts only, through the project's tools; outputs outside the repository (the main checkout's
git-ignored private folder), never committed; docs get aggregates only (`docs/truth-check.md` section 1). **Cost:**
from the cache 5-8 min with 4 at once, about 40 min one at a time, per pass (`docs/truth-check.md` section 4). Files:
none in `main`; tests: none. **Waves:** one agent (Opus, medium), when the PC is free; the planner reviews. **Risk:**
the prototype's files conflict with phase 4 and with the branch `structure-anchors` (part P3b's review).
- **U-12 The bar: decided** (the user, 2026-11-14, "6. a)", the recommendation): lip anchors become an option only
  if P-B and P-D keep at least 98 % of P-A's and P-C's matched known lines (the share the square rule keeps: 581 of
  592); else they go to the roadmap.

## 5. Findings to fix

### 5.1 The memory check's constant (`search.LINE_BYTES`)
**Decision:** G-05: "The memory check's constant goes to the specification as a finding, not changed blindly".
**Behaviour:** 450 B is a traced heap per line of steps 3-5 (`tools/perf_lines_memory.py`); part P4 fitted the
process's peak at 558 MB + 1 082 B a line on 9 runs (0.7-3.5 M lines): the check admits 2.4 times the lines that fit;
gate 1's A6: saving's process tree 1.2-1.4 KB a line. Phase 4 left `LINE_BYTES` at 450 (a row of the square rule's
reducer is 216 B, counted from its dtypes, not measured). The fix measures a slot's peak RSS per line (the search and
saving's children; with the square rule on, per kept line and per waiting reducer row) and sets the constant from it;
only the web worker's refusals change (`plan.memory`), and `memory_warning`, `slot_memory`.
**Files and pairs:** `search.py`, `tools/perf_country.py` (its copy), `docs/performance.md`; `search-pipeline.md`'s
`LINE_BYTES` bullet. **Tests:** `memory_needed`'s. **Waves:** Opus, medium; exclusive runs only when the PC is free.

### 5.2 `count_tile` builds a sag table per tile
**Decision:** part P4's finding (1-3 s a tile; BEL's 24-37 min counts mostly that); not in parts P1 or P3a (searched).
**Behaviour:** with `sag_table=None` and sag, `search:count_tile` takes `_sag_table(dataclasses.astuple(plan.rigging),
min_length, max_length)` (`_lines`' per-process cache). The country layer passes its own table per band
(`country.py` `TileWork._band`, `self.tables`): unaffected; the counts of 5.5 gain. **Pair:** `country-layer.md`
(`_lines` and `count_tile` share step 3's arguments). **Tests:** counts equal with and without a table. **Waves:**
low, any time.

### 5.3 The counting script of 5.5 writes its results safely
**Decision:** a finding of part P3c: the study's counting script wrote partial results under the final file name and
once overwrote a finished count. **Behaviour:** the script that runs 5.5's counts writes partial results to
`count-<case>-<config with suffixes>.partial.json` and the final file whole, then `os.replace`s it. Not a repository
change unless the script becomes a tool. **Waves:** low, by 5.5's agent, first.

### 5.4 'Sea cliffs' and its wall-angle limit
**Decision:** G-11 a: "'Sea cliffs' loses its wall-angle limit (or gets a wide one), after a count"; "a fault to fix,
whatever you choose". **Behaviour:** 30° keeps 2 298 of 354 586 GZp lines of 30-300 m (median wall angle 68°), 18.6 %
at BAH; the goal in the target rig: GZ1 84 416, GZ2 83 351, BAH 148 056 (part P3c). **Files:**
`params.PRESETS["sea"]`, `goal.sea.text`; pair: `web-app.md`'s catalogue (no new key). **Waves:** counted without the
limit and at 45°, 60°, 75°, with the square rule, in 5.5 a. **U-2:** (a) no wall-angle limit; (b) a wide one from that
count. Rec.: (a): the coast area and `min_drop` 30 carry "Lines that leave the cliff over the water".

### 5.5 Owed measurements (before the Basic form and the sample are built)
- **a. Every goal with the square rule on**, 16 reference cases, the target rig (G-11): part P3c's goal
  configurations (each goal's values of 1.2 on each case) with `--same-line-square 5`; found lines by part P1's count
  route (5.3 first), kept lines by a search with the option (the count mode, `count_tile` with a sink, ignores the
  rule); per case and goal: found, kept, the public verdict (the public limits at plan, then the line limits); 5.4's
  variants. A table as part P3c's.
- **b. The sample with the square rule on** (G-04): an estimator of kept lines. Candidates: (1) sample squares, not
  anchors (count the pairs of squares whose first square is sampled); (2) the found estimate times a kept share
  measured on the sample. As part P4's study (78 rows × 5 seeds, 0.5-5 %) against the built option's exact kept
  counts; it passes at part P4's accuracy (2 %: worst ×1.34 at 1 M or more; the band 1 wrong of 390 or better). Each
  medium; through the test lock.

## 6. Recorded as decided (nothing to build)
- **No cap in the search (G-12 a).** "10 per spot" keeps 0.2-1.7 % of a goal's lines and every spot but costs known
  lines (inside 'The best lines here': 392 of 592 by mean height, 470 with the square rule alone); no cap fits the
  country count (each needs the spot, made after grouping a whole table); after the square rule the goal case needs
  none (503 651 lines). The page shows the best (mock-up 2). If searches are still refused, K-13 'Beaten by a margin,
  not by a hair' is the cap to take (407 known lines, never empties a spot). Part P3c, G-12.
- **No heavy lane (G-05 a).** Two slots would hold about 8.6 M lines in a circle, 5.8 M in a tiled area (a model); no
  lane holds the Gozo coast, Malta, Mała Gańkowa or V1-V3 in the target rig; with the square rule the Gozo coast needs
  none (503 651 lines, 89.8 s, 2 911 MB, phase 4); keeping step 1 halves a retry (63 → 36 s) for 3-13 GB, but the
  retry is refused again. The advice was re-ranked instead (phase 4). Part P4, G-05.
- **Today's anchors (G-07 a).** No anchor rule is safe as a default: both ends on a rim keeps 338 of 592 known lines,
  a 3 m thinning 499; the whole-metre guard is safe (580) but cuts about 7 %; lips only keep 4.3 % of the Gozo
  coast's lines (527 901 of 12.3 M) and are measured first (section 4). Part P3b, G-07.
