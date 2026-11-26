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
  the page (name and summary each; "Add a rig", disabled at 10: "You have 10 rigs: the most you can keep. Delete one
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
height · trees marked · <rig>: sag, no-fall zone 5 m, A-frames 2 m · access marked, no line filtered out" (built
with the access mark; "filtered out" is the user's word of 2026-11-15, the mock-up had "left out"); <rig> is the
saved rig's name, "Rig" (the starting rig) or "Rig for this search"; "+ N more settings" counts other fields off the
app's default, `same_line_square` at 5 counting as covered; "named “…”". A Where problem ("Select the centre of the
search: click the map.", …) replaces it and disables Start. "access marked": U-4. Phones: the compact bar: one line
"<goal or Custom> · <lengths> · <rig>" that unfolds the receipt, km², source and grid.

**The size word** (N-05 'A rough size word in the form'; G-04 a "the word in the form as a hint"): "Light",
"Heavier", "Heavy", "Very heavy": one step each for sag, a no-fall zone, A-frames, and one for lines spanning 900 m or
more, else an area above 3.2 km²; the causes named ("sag, no-fall zone 5 m, A-frames 2 m"). Its "?", as built (the
user, 2026-11-15: "1. ok 2. ok c)"), with the factors of the lines the search keeps, measured again with a leash fall
space of 6 m and the square rule of 5 (part M3 of round 2: the reference cases with the goals 'best' and
'everything', ranges by part P4's rule): "Against the simple formula: sag 1.2–3.8 times as many (1.6 in the middle), a
5 m no-fall zone 1.6–36 times (4.1), 2 m A-frames 1.2–3.4 times (1.6), a 6 m leash fall space instead of 3 m 0.14–0.82
times (0.52)."; "One 1 km circle in Poland: 531 lines with the simple formula, 25 349 with sag, a no-fall
zone of 5 m and A-frames of 2 m." (KOB, 'everything', kept lines, part M3); "This is a rough guide from other places,
not a count for this one." The rig's window names the same factors: "With this rig: sag gives about 1.2 to 3.8 times
the lines of the simple formula. The no-fall zone multiplies them by 1.6 to 36. A-frames multiply them by 1.2 to 3.4."
(only the parts the rig has), and beside its fields "on: 1.6 to 36 times the lines" and "on: 1.2 to 3.4 times the lines". There is no
"Lighter" hint (the user, 2026-11-15, "c"): the bar, the "?" and the phones offer no shortcut to the simple formula.
The mock-up's note "Measured with 3 m of leash fall space" goes. Changed texts: U-3. **Start** posts `/api/jobs` as
today.

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
- **U-2** 'Sea cliffs' without its wall-angle limit: 5.4. Decided (a) on 2026-11-15 (`spec.md` 6.4).
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
  5.5 b's numbers. Decided on 2026-11-15: neither; 5.5 b found one (the rule's squares sampled, 2.2), built in
  4f468d3 (`spec.md` 6.4).
- **U-7** (a) the web worker only (this file); (b) also the command line, printing the estimate. Rec.: (a).

## 3. Access mark of three states

### 3.1 Decision
G-09 'Ease of access to the anchors', answer a: "A mark of three states, no limit"; tier next; gate 2 D-08 c 'Ease of
access to the anchors'. The form says "The result marks anchors you can walk to. No line is filtered out." (the
user's words for the second sentence, 2026-11-15, in place of the mock-up's "No line is left out"). No filter
removes lines.

**Built** in round 3 (`main` 53fe802, 2026-11-16). This section states the mark as built; where it differs from the
text of 2026-11-14, the user's words of round 3 decided (`spec.md` 6.5). What is left for the result view: 3.9.

### 3.2 Behaviour
- **The three states** and their words (the user, 2026-11-15): "easy access" (the grid's 2; the study's "can walk"),
  "cannot tell" (1; the study's "cannot tell here"), "hard access" (0; the study's "cannot walk": an anchor that
  hangs in the face).
- **The measure** (part P3d, its constants kept). Open
  ground: under 30°, not water, with data, in a connected area of 1 ha or more. Standing ground: walkable within 3 m of
  the anchor, 2 m below to 3 m above it. Walkable: ≤ 40°, not water, no knife-edge crest (strict); ≤ 50°, crests
  allowed (loose). Easy access: the strict walk of ≤ 500 m from open ground reaches it (whole-metre heights, 90 % of a
  sample: also on lightly smoothed ones). Cannot tell: only the loose walk reaches it; or smoothing changes a
  whole-metre answer; or unreached while its walkable ground comes within 500 m of the end of the data. Else hard
  access. Flat lakes held as data count as water unless the heights are whole metres. **The alpine variant is in**
  (U-9 a): hard access becomes cannot tell where open ground is under 5 % of the land within 250 m.
- **Where the study's script says more than these words, the port follows the script** (U-11: "port the measure as
  it is"; `access.py`'s docstring has each): filled gaps are no data for the walk; "within 250 m" is a square of
  ±250 m; the rim of a hole without data is not an end of the data, a filled gap and the grid's edge are; the
  smoothing is a Gaussian of 1 pixel; the whole-metre and the flat-lake judgements are made over the whole grid;
  open ground may include crests; the flat lake's constants are under 3°, at least 2 000 m², heights spread at most
  0.3 m; a window that cuts a thin open strip would differ, so the search computes one grid.
- **An anchor on a filled pixel or on a sea cliff's face taken from the surface model** gets the measure's own
  answer there (the user, 2026-11-15: "The measure's own answer"): those pixels are no ground to walk on, and the
  answer is that of the ground around them. A first build read such anchors as "cannot tell"; with the measure's own
  answer R83's line ends read cannot tell 4.2 % (19.4 % before) and BAH's hard access 59.5 % (48.0 % before; round
  3's counts).
- **Computed** once on step 1's grid of the whole area (filled terrain, water) as a `uint8` grid, a tiled search's
  too (`access.npy` in its work folder); each tile takes its window: one grid's answers. Each line takes its two
  anchors' answers after the pair search. **At once** (`access.access_grid`) when 50 B per pixel of the grid fit the
  search's memory; **else in blocks** (`access.block_grid`; the user, 2026-11-15: "Compute in blocks"): the
  grid-wide judgements (the whole-metre sample, the flat lakes, the open regions on the heights and the smoothed
  heights) once on the whole grid, strip by strip, their regions with no label array of the grid and their masks as
  bits in files (since 2026-11-26; memory-mapped before); every block from its window of 533 m and 6 pixels around it,
  and only the blocks whose core holds a pixel of the search area (the others are never read: every anchor lies in
  the area). The answers are the whole grid's (0 pixels differed on the Gozo coast, the Tatras circle and R83).
  Blocks need 4 B per pixel of the grid, 0.14 GB for the grid-wide pass and 50 B per pixel of a block's window
  (`search.ACCESS_AREA_BYTES`, `ACCESS_FIXED_BYTES`, `ACCESS_WINDOW_BYTES`; blocks at least 500 m wide; 12 B and no
  fixed term until 2026-11-26: docs/performance.md, "Less memory for the grid in blocks"). The measure needs 533 m
  around an anchor; the grid reaches `_margin` (300 m by default) beyond the area, so edge anchors read "cannot tell"
  more often.
- **A search too wide for the access grid runs without the mark** (the user, 2026-11-16: "1, and add to roadmap for
  better algorith with lower memory cost"). It replaces the refusal `access_memory` of a first build: no search is
  refused for a mark that filters nothing. `search._check_access` decides before step 1, when not even the smallest
  blocks fit the search's memory (a compute slot's on the site; on the command line and in the local app the memory
  free when the search starts, so the same search may be marked on one day and not on another). The run is then the
  run of a search without the option, plus `"access_skipped": "memory"` (3.3) and the coded note `access_skipped`
  (3.4). The request's hash stays, so its 2 % sample is the marked request's. On the public site this starts where
  the box around the area is larger than about 34.2 by 34.2 km at 1 m data, about 69.1 km at 2 m (computed from the
  rule for a compute slot of 4.95 GB; about 20.0 and 40.5 km until 2026-11-26).
- **Cost** (measured, exclusive; `docs/performance.md` "The access grid's memory"): at once about 0.25-0.35 s per
  megapixel, in blocks about 0.4 s. The whole Gozo coast search in a VPS slot's memory: 44.0 s without the option,
  91.7 s with it (the grid in six blocks); its peak 3 636 MB against 2 869 MB. A Basic point search: about 1 s more.
- **When:** a search option, off by default on the command line; the web form sends it on (U-8 a): every Basic
  search, and Advanced's ticked field "Mark anchors you can walk to". "Search a cell" of the highline layer opens
  Advanced with the mark on (the user, 2026-11-16). Runs made without the option show no mark; a search stored
  before the mark reopens without it (the user: "does not matter - old runs will be removed everywhere").
- **Shown:** 3.6.
- **Worth** (part P3d): known ends against random steep pixels 0.47 (0.5 = none), 0.70 on gentle pixels. Line ends
  easy / cannot tell / hard, the study's main measure: KOB 23.7/21.8/54.5 %, BAH 12.6/19.7/67.7 %, BEL
  37.7/14.1/48.2 %, DOL 36.5/26.5/37.1 %, MGp 0.0/1.1/98.9 %, GZp 1.7/6.8/91.5 %. With the alpine variant MGp's ends
  read 0 / 37 831 / 25.

### 3.3 Data
Option on: `access1`, `access2` (0 hard access, 1 cannot tell, 2 easy access; `runs.ACCESS` = `linestore.ACCESS`):
after the anchors' columns of `lines.csv` and in a feature's properties of `lines.geojson`, before `stands_for`; in
`data.js` and `lines.js` before the profile, named in the heads' `ends` after the A-frame heights and before
`stands_for`; two uint8 columns of the store (`spec-store.md` 1.3); `run.json`'s params hold the option. Off: no
column, today's bytes. `Line` and favourites get optional `access1`/`access2` (null without; a favourite carries
them only when its line has them). A mark asked for and left out: `"access_skipped": "memory"` in `run.json`, in
every head (`data.js`, `lines.js`, the store's) and in a tiled run's `progress.json`, which keeps its tiles from a
run of the other choice. Stored-data decision: none (new runs only; old runs, jobs, favourites and `file://` as
before).

### 3.4 Interfaces
`SearchParams.access: bool = False`, `--access`, topic "anchors", `field.access.*` (label "Mark anchors you can walk
to"), a README row and its paragraph "Access to the anchors"; unset, `_search_hash` as before. The coded note
`access_skipped`: "The anchors' access will not be marked: this search's area is too wide for it (about N GiB of
memory needed, M GiB here). The search itself is not affected."; on the public site without the bracket
(`error.access_skipped_public`; the user, 2026-11-16: "remove it from message when --public flag is set"). A coded
message may so have a public reading: `error.<code>_public`, without params; the page words a coded message from its
own catalogue by the code, so a text the server chose reaches it through the info's `key`
(`.claude/rules/web-app.md`). The texts of the page: `ui.access.*`.

### 3.5 Files and pairs
`access.py` (numpy/scipy/numba, a port of part P3d's measure; `access_grid`, `block_grid`, `at`), `search.py`
(`_check_access`, `_access_grid`, `_access_columns`, the `ACCESS_*` constants), `runs.py`, `mapping.py` (`_ends`),
`saving.py`, `linestore.py`, `params.py`, `messages.py` (a coded message's public reading), `jobs.py`, `web.py`
(`FavouriteLine`), `viewer/src/types.ts`, `access.tsx`, `favourites.ts`, `search/basic.ts`, the result page's list,
details, legend and map, README, docs; tests `test_access.py`, `test_access_search.py`, `test_access_page.py`.
Pairs, as written into the rules: `run-files.md` "The access mark" (the columns' place, `runs.ACCESS` =
`linestore.ACCESS` = `types.ts` `ACCESS`, `access_skipped` in run.json and every head = `RunHead.access_skipped`);
`search-pipeline.md` "The access mark" (one grid per search, at once or in blocks, never a refusal; a change of
`access.py`'s arrays is measured again); `viewer.md` "The access mark" (the values, the three states' words in the
legend, the details, the help and `field.access.help` changed together; the tokens `--acc-*`; `basic.ts`
`ACCESS_SKIPPED` = the search's note). `country-layer.md`: not in the cube (it needs computing beyond the count: the
user's rule of 2026-11-05); it would fit with a 0.53 km margin (part P3d).

### 3.6 Screens
The mock-up of where the mark shows (U-10) is accepted at version 8 (the user, 2026-11-15: "current mockup looks
good and can be implemented"); its notes hold the settled proposals 1-20. Built on today's page:
- **The list:** a column "Anchors" with two dots in every row (anchor 1, anchor 2 of the spot's shown line; the
  user: "Two dots in every row"). The list's default width is 372 px. The column is tight under a list of 356 px and
  left out under 300 px; the marks stay in the details. With Compare, a line of a run without the mark shows "–".
- **The details:** a block "Reaching the anchors" with a row per anchor (the dot, "Anchor 1", the state); on a phone
  the sheet's head repeats the two dots.
- **The map:** only the selected line's two anchors become marks (the user: "Selected line only").
- **The legend:** one row "Anchors" with a "?" whose help explains the three states. On a phone the row stands above
  the filter chips and the list whenever the run has the mark (the mock-up does not settle the place).
- **The dots:** green with a walking person (easy access), amber with "?" (cannot tell), slate with a person on a
  rope (hard access; the user: "i like A slate with walker and rope"); 20 px in rows, details and legend, 24 px on
  the map. The drawings are the project's own (the user: "use ours"), the walker inside the dot.
- **The search form:** Basic's row "Reaching the anchors" with the note "The result marks anchors you can walk to.
  No line is filtered out.", and the receipt's "access marked, no line filtered out" (on a phone "access marked");
  the phone bar's fold mark is the side panels' chevron; a skipped mark reads in the receipt and, on the result
  page, as the muted line "Anchors' access not marked: the search area was too wide."
- Not settled by the mock-up, built so: the form shows an estimate's notes only as a count ("1 warning").
### 3.7 Tests
Made-up terrain: meadow and wall (can), mid-face ledge (cannot), 45° (cannot tell), whole metres, the data's end;
tiles = one grid; option off byte-equal (`test_saved_text_as_before`, the R entries); the four files and
`test_saved_by_children_as_in_process` with the columns; one new R entry with the option (R83: R16 with `--access`;
`lines.csv` less its two columns is R16's, and the marks of the line ends are counted); part P3d's shares (3.2,
"Worth") reproduced on its six target-rig tables by the repository's `access.py`. As built also: blocks equal one
grid (`tests/test_access_search.py`), the skipped mark, the page (`tests/test_access_page.py`). Known gaps: the
skipped mark's disk estimate and Compare of a skipped with a marked run have no test; R83's mark depends on the
memory free when the regression set runs (`docs/known-bugs.md`).

### 3.8 Acceptance
Part P3d's answers equal: with the alpine variant off on its six tables (KOB, BAH, BEL, DOL, MGp, GZp), with it on
on the two where the study ran it (KOB, MGp); a check script outside the repository, since the study's grids are
recomputed from its runs and its comparison used known lines (counts only). About 0.3 s per megapixel (indicative);
checksums unchanged with the option off. E7 'Trust' (gate 1): no number set; the user judged part P3d's pictures
(U-11, 2026-11-15: the colours match). **Met** (round 3's private check): per line end the port equals part P3d's
stored answers on all six tables with the variant off (157 012 ends, 0 differences) and on the two with it on (0).

### 3.9 Waves
Built (round 3): 1. `access.py` and tests. 2. Search and files, the blocks, the skip. 3. The mock-up (version 8),
then the page. 4. Review: full pytest, R83, `tools/ui_shots.py`.
**Later, with the result view** (`spec-view.md` B; the mock-up's notes "Later, with the result view"):
- A1 and A2 on the map carry the state (proposal 12); the rows of "Lines from here" get a column "Far end" with the
  far anchor's dot, and the three marks stand in the result view's map legend (proposal 13).
- The fifth "Start here" pick, "From a top edge: walk to both anchors": the highest line on average whose two
  anchors read easy access; shown last, also within 100 m of an earlier pick; no such line, no pick (proposal 14;
  the user: "+ 'From a top edge' pick").
- The phone legend of two lines, short labels, unfolded at the start, with a fold whose mark is the side panels'
  chevron (proposals 18, 20; the user: "need to scroll legend is silly. Make it two line, and add option to collaps
  it."). Today's phone page has no legend that scrolls sideways, so nothing of it is built yet.
- Not in the mock-up, and so not part of these later parts (its notes: "Not in this mock-up (say if you want one of
  them)"): a mark on the profile's labels A1 and A2, in the 3D view or on the favourites page; sorting by the mark
  ("your answer left it out"). A filter by the mark is not offered: no line is hidden.

### 3.10 Risks and rollout
The weak separation may mislead (the help says the site cannot see "paths, fences, private land or trees"); edge
anchors read "cannot tell"; memory per pixel grows; whether a wide search on the command line or in the local app is
marked depends on the memory free that day. A tiled run interrupted under one choice of the mark and never resumed
leaves its "running" folder (as any interrupted tiled run whose hash never returns); so does one whose choice the
constants of 2026-11-26 changed (the same request then starts a new run). The grid needs less memory since
2026-11-26 (`docs/roadmap.md`, "An access grid that needs less memory", closed; blocks without an anchor are a
possible option there). VPS: deploy, no migration; the mark
is then on in every Basic search (the seconds and the peak of 3.2).

### 3.11 Needs the user's word
Nothing is open; the round-3 answers are in `spec.md` 6.5.
- **U-8** (a) an option, off by default, on in the web form (this file; checksums stay); (b) always on (every R entry
  re-baselined). Rec.: (a). **Built as (a)** (`viewer/src/search/basic.ts`).
- **U-9 The alpine variant** ("cannot walk" becomes "cannot tell" where open ground is under 5 % of the land within
  250 m; MGp's ends then 99.9 % "cannot tell"): (a) in; (b) out (part P3d's main measure). Rec.: (a), no confident
  "cannot walk" on alpine walls. **Decided (a)** on 2026-11-15 ("3. a").
- **U-10** Where the mark shows: a mock-up before code. **Decided** on 2026-11-15: the mock-up's version 8 (3.6).
  **U-11** The user looks at part P3d's pictures of five cases
  (BAH, MGp, BEL, DOL and a quarry) before building (G-09's recommendation). **Decided** on 2026-11-15 ("4. a"): the
  colours match; the measure is ported as it is.

## 4. Lip anchors measured against the known lines (a measurement, not a feature)
**Result (round 3, 2026-11-15): lip anchors fail the bar and are not built.** All types, counts only, 1 912 known
lines in the target rig at the 6 m fall zone:

| Pair | Today's matched | Lips' matched | Today's still matched with lips | Share kept (the bar: 98 %) |
|---|---:|---:|---:|---:|
| P-B (lips) against P-A (today's anchors) | 802 | 577 | 561 | 69.95 % |
| P-D (lips, square rule 5) against P-C (today's, square rule 5) | 757 | 551 | 537 | 70.94 % |

By type the share is 68.90 / 69.64 % for highlines and 77.23 / 80.00 % for midlines. Lips match 16 and 14 known
lines that today's anchors miss. Recall in the target rig, all types: P-A 44.3 %, P-B 31.9 %, P-C 41.8 %, P-D
30.5 %. P-B's 241 new misses by the analysis' reason: clearance near the anchor 96, height difference 85, anchor
filtered 49, others 11 (the analysis does not know lips: these are labels for "no lip pair passes here", not
measured causes). Kept lines with the square rule at 5 m, lips against today's anchors: BAH 15 490 / 43 127
(35.9 %), GZ2 75 394 / 236 147 (31.9 %), MG 175 901 / 467 866 (37.6 %), DOL 34 276 / 101 568 (33.7 %). By U-12 they
go to the roadmap as measured and not taken (`docs/roadmap.md` "Line volume"); the prototype is kept under the tag
`history/lip-anchors-p3`, never merged. The text below is the measurement as it was specified.

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
**Done** (round 3, `main` 0e711bb; the user's "a", 2026-11-15): `LINE_BYTES` is **900 B a line**, with no fixed
term. Measured under the exclusive lock as a slot's whole process tree (`tools/perf_slot_memory.py`; 35 searches of
0.7-3.5 M lines): the unique sets plus the hand-over files once fit 399 MiB + 440 B a line without the square rule;
the largest slope between two runs is 762 B a kept line with the square rule, and 900 is that with 18 % on top. A
reducer row of the square rule measured 181-287 B (216 B counted before). Method and tables:
`docs/performance.md` "The memory constant". Large searches are so refused for memory a little earlier. The text
below is the finding as it was specified.
**Behaviour (before the fix):** 450 B is a traced heap per line of steps 3-5 (`tools/perf_lines_memory.py`); part
P4 fitted the
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
count. Rec.: (a): the coast area and `min_drop` 30 carry "Lines that leave the cliff over the water". **Decided
(a)** on 2026-11-15; built in c8a079a.

### 5.5 Owed measurements (before the Basic form and the sample are built; both done in round 2, 2026-11-14/15)
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
