# Wording: the words to use and the words not to use

For anyone who writes a text the user reads (the message catalogues `locales/en.json` and `locales/coverage/*.json`,
the server's pages) or the docs' prose: agents first, the user too. It gathers what the user decided; it invents
nothing, and each row names its source:

- **user-inputs**: `local/ux-design-2026-11-16/user-inputs.md`, the user's words of the UX/UI design task, verbatim
  and dated (local, not in the repository), by the date and the title of its section.
- **G5's rows**: the wording review of step 3d, group G5 (2026-11-21): `local/ux-design-2026-11-16/3d/g5/proposal.json`
  with the user's answers in `3d/g5/answers/decisions/`, by row id; each row the user answered took "Use proposed"
  or "(a) Written out" (user-inputs, "Step 3d G5: the wording review page"), not a row's (b) variant.
- **DESIGN**: [DESIGN.md](DESIGN.md)'s rules (R9, R10) and its choices by number.

`tests/test_words.py` reads the "Not" column of the first table (each word in backticks, every form listed: the
test matches whole words as written, in any case) and fails when a value of `locales/en.json` or
`locales/coverage/en.json`, or the text of a server page (sign-in, about, privacy), holds one, its `{{placeholders}}`
and its `<b>`/`<i>` left out. It lets pass only what [Exceptions](#exceptions) lists. Names in code stay as they are
(keys, variables, classes, options, stored values): these are the words a person reads.

## Words to use and words not to use

| Use | Not | Where | Source |
| --- | --- | --- | --- |
| athlete (the person on the line) | `walker`, `walkers`, `slackliner`, `slackliners` | UI texts and the docs' prose; names in code stay (`athlete_mass`, `walk.ts`, `walker.gltf`, the keys `ui.view3d.walker*`), and so do the docs where they quote them | the user, 2026-11-13 (main d40469e: "slackliner" first, then "athlete" by the user's later choice) |
| chart (the layer's counts of lines by a value) | `histogram`, `histograms` | UI texts; the data and the code keep "histogram" (`/api/countries/<id>/histogram`, `LayerHistograms.tsx`), and so do the docs on them | the user, 2026-11-21: "Chart and limit (Recommended)" (user-inputs, "four wording questions after the reviews"); the right panel's name and its folded rail ("Charts: 62 M lines in view"): the user, 2026-11-21: "1. charts" (user-inputs, "G5's four open points after the fix round") |
| limit (what a filter sets) | `threshold`, `thresholds` | UI texts; the option `slope_threshold` and the docs on it stay | the same answer |
| waiting (an account the administrator has not approved yet) | `pending` | UI texts; the stored status `pending` stays | the user, 2026-11-21: "Badge "Waiting" (Recommended)" (the same section) |
| How a search works (the search's intro: its title and its link) | `How searching works` | UI texts | the user, 2026-11-21: "Link = title (Recommended)" (the same section) |
| About and data licences | `About / data licences` | UI texts: the footer, the about page, the account menu, the coverage page's link (Polish "O stronie i licencjach danych") | G5's row left-06 (R9: "/" for "and"; one wording); the coverage page's link: the user, 2026-11-21: "2. change" (user-inputs, "G5's four open points after the fix round"; the Polish words the planner's) |

## Words chosen for one place

Not checked by the test: the old word is common elsewhere, or was a sign.

| Use | Instead of | Where | Source |
| --- | --- | --- | --- |
| over 2 ("over" and the chart's last value, as its bar's title says it) | "more" | an at-most chart's last tick on the highline layer | the user, 2026-11-21: "over 2" (user-inputs, "four wording questions after the reviews") |
| A1, A2 | "Anchor 1", "Anchor 2" in every row | the anchors' column heads of a line's details | the user, 2026-11-17: "D1 - usage of A1/A2 instead of full text anchor 1" (user-inputs, "the comps D1 to D5") |
| low, half height, full height | "peek", "half", "full" | a phone's sheet: its height in its handle's name, which a screen reader reads; the code's snaps keep their names | G5's row left-10 |
| Report a problem… | "Report a problem" | a menu item that opens the dialog (the account's menu and a search card's); the dialog's title without "…" | G5's row left-07 |

## Characters written out

R9 (DESIGN, the user's pick "R9 b", 2026-11-17): in a text the user reads no character stands for a word.

| Character | Written | Example | Source |
| --- | --- | --- | --- |
| ≤ (also "<=") | up to | "≤ 1 m" -> "up to 1 m"; the form's "up to 10 m"; Polish "do 1 m" | G5's rows char-12 to char-16; the 3D view's "<=": the user, 2026-11-19 ("Keep "x1", replace "<=""; user-inputs, "Step 3c group B ... three scope questions") |
| ≥ | at least; a chart's last bin "or more"; a legend's class "from" | "at least 60 m", "20 m or more", "from 22k" | G5's rows char-15 to char-17, char-19 |
| < | under | "under 45°", "under 8" | G5's rows char-15, char-16, char-19 |
| > | over | "over 2 m"; an at-most chart's last tick "over 2" | G5's row char-17; the user, 2026-11-21 ("over 2") |
| × (a multiplier) | times | "×1.6 to ×36" -> "1.6 to 36 times the lines"; "at least {{factor}} times the grid size"; "1.2–3.8 times as many" | G5's rows char-01 to char-04 |
| × (a size) | by | "0.6 × 0.9 km" -> "0.6 by 0.9 km" | G5's rows char-05, char-20, char-21 |
| ≈ | about | "Polyester ≈ 1–3 %" -> "Polyester about 1–3 %" | G5's row char-06 |
| → | the words of the step it stood for | "{{cliffs}} → {{coast}}" -> "{{cliffs}} on the {{coast}}" | G5's row char-09 |
| "+ " (for "and" or "more") | left out; before a command the kit's plus icon | "+ 2 more settings" -> "2 more settings"; "+ Add a rig" -> the icon and "Add a rig" | G5's rows char-07, char-08 |
| " · " between values | a label with a colon, the parts joined by "; " | "page: …; interface: …; window: …" | G5's row left-08 |
| "/" for "and" | and | "About and data licences" | G5's row left-06 |
| a sign in a chart's tick | the bare value, the word in the chart's title | "≥10", "<2", "≤1" -> "10", "2", "1" under a title that says "at least", "under" or "up to" | G5's row char-18 |

Kept, where a sign stays:

| Where | Kept | Why | Source |
| --- | --- | --- | --- |
| everywhere | units (m, km, °, %), an en dash in a range ("30–300 m") | R9 allows them | R9 |
| a filter's chip (the result view) | ≤, ≥ | R9 allows them in a filter's chip | R9; G5's row kept-01 |
| a one-line meta line, a browser tab's title | " · " (a date and a count under a name; "{title} · Find-a-Line") | R9 allows `·` in a meta line | R9; G5's rows kept-06, left-09 |
| the 3D view's speed and zoom | "×1", "×8" | a multiplier the user kept like a unit | the user, 2026-11-19 ("Keep "x1""); DESIGN choice 47; G5's row kept-02 |
| the sign of a number | "+2 m" | a sign, not a word | G5's row kept-03 |
| the coverage map's images and videos | "≤ 1 m", the stars' character | rendered by hand and rarely: left for now | step 3d's scope Q16 a (`local/ux-design-2026-11-16/3d/scope.md`); G5's row kept-04 |
| round 6's coarser box | " · " between the sources' shares | after line volume's round 6 | G5's row kept-05 |
| today's result page | "→" in its intro (`intro.result.spots`, `easy_within`), ≥ and ≤ in its filter bar | the page goes with line volume's round 6 | the user, 2026-11-19 (known-bugs.md, step 3d G5) |

## Style rules

Each rule lives where it is linked; it is not copied here.

- **R9** (characters as icons, dense strings) and **R10** (a help at most 40 words, an intro paragraph 30, a hint
  25, an error 30; at most 400 visible words before a first search): [DESIGN.md](DESIGN.md), part 2.
- **The wording rule** of the search's texts: [roadmap.md](roadmap.md), "UI texts (2026-10-30, the user)":
  simplified technical English with the highliners' words (webbing, athlete, leash fall, anchors), never a command
  line's option or a snake_case name, a "?" on every setting.
- **Approved wording** (legal, privacy, safety): changed only with the user's yes on the exact sentence; the keys in
  [.claude/rules/web-app.md](../.claude/rules/web-app.md), "Must stay in sync", and the privacy page's words.
- **Plurals by the count**: a text with a number is a plural key (`_one`, `_other`), its caller gives `count`; never
  "(s)" or one form for every number ("1 folders"). DESIGN choice 95; G5's rows left-01 to left-05.
- **"…" only on a command that opens a dialog** (a menu item, a button); the dialog's title without it. G5's row
  left-07; DESIGN choice 95.
- **Sentence case**: no capitalised titles or labels (the user, 2026-11-17: "D5 - capitalized text (title, spots,
  lines, etc)" under "I do not like"; user-inputs, "the comps D1 to D5"). A badge or status chip starts with a
  capital by the CSS, its word lower case in the catalogue (DESIGN choice 51).
- **A label that leads a count takes a colon**: "Filters: 0 set", not "Filters, 0 set" (the user, 2026-11-20:
  "A colon, as the result view (Recommended)"; user-inputs, "Steps 3c groups B and C: answers after their reviews").
- **Spelling**: British, as the catalogue writes it (counted 2026-11-21: colour 4, centre 14, metres 8, favourite 10,
  licences 8, cancelled 5; no American form). "meters" in `intro.search.limit_meters` are the gauges, not the unit.
  Not a decision of the user's: what the catalogue does.

## Exceptions

Texts that hold a word of the first table's "Not" column and stay for now; the test fails on a hit not listed here,
and on a row here whose text no longer holds its word.

None today (the three of the first build went by the user's answers of 2026-11-21: "1. charts", "2. change").

| Text | Word | Why |
| --- | --- | --- |

## How a word is added

1. The user's yes on the word (and on the exact sentence where the wording is approved wording), recorded with its
   date: in the task's user-inputs, or in the commit that changes the texts.
2. One row in the table it belongs to, with its source. A word never to be written again goes into the first table's
   "Not" column in backticks, each form that may appear (singular and plural); a word chosen for one place goes into
   the second table.
3. The texts changed in the same commit; a text that keeps the word for a reason gets a row in
   [Exceptions](#exceptions); `tests/test_words.py` then passes.
