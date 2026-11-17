---
version: alpha
name: Find-a-Line, the interface as built (main 2f019d6)
description: >-
  Today's tokens of viewer/src/ui/tokens.css and the kit of viewer/src/ui/ui.css, as the code has them, not a
  target. The rules the user picked on 2026-11-17 are in the last section. A "-dark" name is the dark theme's value of the
  token without it; a token the dark theme does not redefine keeps its light value.
colors:
  bg: "#f3f5f2"
  surface: "#ffffff"
  surface-2: "#e9eee9"
  ink: "#17201c"
  ink-2: "#45524b"
  muted: "#6c7a73"
  line: "#d2dad4"
  accent: "#2350c8"
  accent-soft: "#e1e8fa"
  on-accent: "#ffffff"
  ok: "#1d7a47"
  ok-soft: "#e0f1e6"
  warn: "#995500"
  warn-soft: "#fbefd9"
  bad: "#b3261e"
  bad-soft: "#fbe4e1"
  map-bg: "#ecebdf"
  water: "#93c3e3"
  rock: "#8a7b63"
  clear: "#e10fd6"
  trees: "#ef8300"
  fav: "#f0c400"
  halo: "#ffffff"
  terrain: "#bba680"
  tree-fill: "#80ae6b"
  limit: "#d62728"
  coarse: "#3b3f5c"
  coarse-map: "#3b3f5c"
  layer-1: "#86b6ef"
  layer-2: "#3987e5"
  layer-3: "#256abf"
  layer-4: "#184f95"
  layer-5: "#0d366b"
  acc-easy: "#1a994f"
  acc-tell: "#ed8c0d"
  acc-hard: "#2f3a45"
  acc-easy-sign: "#ffffff"
  acc-tell-sign: "#2b1a00"
  acc-hard-sign: "#ffffff"
  acc-map-easy: "#1a994f"
  acc-map-tell: "#ed8c0d"
  acc-map-hard: "#2f3a45"
  acc-map-tell-sign: "#2b1a00"
  acc-map-edge: "#4d4538"
  bg-dark: "#0e1311"
  surface-dark: "#161c19"
  surface-2-dark: "#1f2723"
  ink-dark: "#e5ebe7"
  ink-2-dark: "#b1bcb6"
  muted-dark: "#85928b"
  line-dark: "#2c3631"
  accent-dark: "#86a4ff"
  accent-soft-dark: "#1f2a48"
  on-accent-dark: "#0a1020"
  ok-dark: "#62c78e"
  ok-soft-dark: "#163023"
  warn-dark: "#e6a94f"
  warn-soft-dark: "#382a12"
  bad-dark: "#ff8a80"
  bad-soft-dark: "#3a1a18"
  map-bg-dark: "#1a201c"
  water-dark: "#24475e"
  rock-dark: "#948a72"
  clear-dark: "#ff4cf4"
  trees-dark: "#ff9f30"
  fav-dark: "#ffd84a"
  halo-dark: "#0e1311"
  terrain-dark: "#6e5f44"
  tree-fill-dark: "#3f6b36"
  limit-dark: "#ff6b6b"
  coarse-dark: "#c9cdf0"
  layer-1-dark: "#9ec5f4"
  layer-2-dark: "#6da7ec"
  layer-3-dark: "#3987e5"
  layer-4-dark: "#256abf"
  layer-5-dark: "#184f95"
  acc-easy-dark: "#35b56e"
  acc-tell-dark: "#f5a233"
  acc-hard-dark: "#9aa7b5"
  acc-easy-sign-dark: "#06170d"
  acc-tell-sign-dark: "#2b1a00"
  acc-hard-sign-dark: "#0e1318"
typography:
  body:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.45
  heading:
    fontFamily: '"Barlow Condensed", "Arial Narrow", "Roboto Condensed", system-ui, sans-serif'
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.01em
  heading-xl:
    fontFamily: '"Barlow Condensed", "Arial Narrow", "Roboto Condensed", system-ui, sans-serif'
    fontSize: 30px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.01em
  heading-4:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 14px
    fontWeight: 600
  small:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 12.5px
  button:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 14px
    fontWeight: 500
  button-large:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 15.5px
    fontWeight: 500
  chip:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 13px
  segmented:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 13.5px
    fontWeight: 500
  input-coarse:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 16px
  field-value:
    fontFamily: 'ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace'
    fontSize: 13px
    fontWeight: 500
  badge:
    fontFamily: 'ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace'
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1
  status:
    fontFamily: 'ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace'
    fontSize: 11.5px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.03em
  stat-value:
    fontFamily: '"Barlow Condensed", "Arial Narrow", "Roboto Condensed", system-ui, sans-serif'
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.1
    fontFeature: '"tnum"'
  stat-label:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 11.5px
  nav-item:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 11.5px
    fontWeight: 500
  hint-mark:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 11.5px
    fontWeight: 600
    lineHeight: 1
  hint-bubble:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
rounded:
  shore-note: 6px
  control: 8px
  control-large: 10px
  segmented: 10px
  stat: 10px
  split-tab: 11px
  panel: 14px
  sheet: 20px
  full: 999px
spacing:
  touch: 36px
  touch-coarse: 44px
  chip-gap: 6px
  row-gap: 8px
  column-gap: 12px
  panel-padding-y: 14px
  panel-padding-x: 16px
  button-padding-x: 14px
  sheet-padding: 16px
  split: 12px
  split-coarse: 24px
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    height: "{spacing.touch}"
    padding: 0 14px
  button-hover:
    backgroundColor: "{colors.surface-2}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.ink-2}"
  button-danger:
    textColor: "{colors.bad}"
  button-large:
    typography: "{typography.button-large}"
    rounded: "{rounded.control-large}"
    height: 46px
    padding: 0 20px
  icon-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    size: "{spacing.touch}"
  icon-button-on:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    typography: "{typography.chip}"
    rounded: "{rounded.full}"
    height: 30px
    padding: 0 11px
  chip-on:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
  chip-coarse:
    height: 36px
  segmented:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.segmented}"
    padding: 3px
  segmented-option:
    textColor: "{colors.ink-2}"
    typography: "{typography.segmented}"
    rounded: "{rounded.control}"
  segmented-option-on:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: 14px 16px
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: 38px
    padding: 0 12px
  input-coarse:
    typography: "{typography.input-coarse}"
    height: "{spacing.touch-coarse}"
  status-done:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ok}"
    typography: "{typography.status}"
    rounded: "{rounded.full}"
  status-running:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
  status-waiting:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-2}"
  status-failed:
    backgroundColor: "{colors.bad-soft}"
    textColor: "{colors.bad}"
  status-shared:
    backgroundColor: "{colors.warn-soft}"
    textColor: "{colors.warn}"
  badge:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.badge}"
    rounded: "{rounded.full}"
    padding: 3px 6px
  badge-neutral:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-2}"
  stat:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.stat}"
    padding: 8px 10px
  hint-mark:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    typography: "{typography.hint-mark}"
    size: 18px
  hint-bubble:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    typography: "{typography.hint-bubble}"
    rounded: "{rounded.control}"
    padding: 8px 11px
  sheet:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.sheet}"
  bottom-nav:
    backgroundColor: "{colors.surface}"
    height: 64px
  bottom-nav-item:
    textColor: "{colors.muted}"
    typography: "{typography.nav-item}"
  bottom-nav-item-on:
    textColor: "{colors.accent}"
---

# Find-a-Line: the design language

**Status: part 1 describes; part 2 holds the rules the user picked on 2026-11-17, in force except R4.1.**
Two parts:

- **Part 1, "Today"** (the eight sections from Overview to Do's and Don'ts): the design language as the code has it
  at `main` 2f019d6, described, not judged. The token header above holds these values only. The numbers are of
  that commit; later changes of the code move them.
- **Part 2, "Rules"** (the last section): rules that do not depend on the new look, each with the user's pick,
  today's number, how it is checked and the options not picked.

What the app is for and for whom: [PRODUCT.md](PRODUCT.md). The new look itself (colours beyond the kept anchors,
the body font, shapes, the containers' look, the label style) is not settled here: it is settled on the pilot's
mock-up.

**Sources of the numbers** (the baseline of 2026-11-16), marked in brackets:
- **[S]** the source counts of `tools/ui_metrics.py static` over `viewer/src` and `locales/en.json` (21 CSS files,
  164 `.ts`/`.tsx` files; two runs on one tree gave the same output). The tool is in `main`.
- **[P]** the rendered pass of `tools/ui_metrics.py pages` (pass 2: the light theme, 251 states of
  `tools/ui_shots.py` on the desktop, iPhone 13 and Pixel 7 profiles; axe-core 4.14.1). Counts of what a browser
  draws, per state.
- **[W]** the task walks of `tools/ui_walks.py` (R1 to R4 on the desktop, F1 to F3 on the iPhone profile; two runs
  gave the same counts). A control there is a visible, enabled control of the surface in view.
- **[O]** counts made for this draft from the same raw per-state log of [P] and from the sources at 2f019d6 (the
  method is written beside each).
- **[C]** a line of the code, named.

## Overview

Today the interface is one kit for the whole app, the run's own map and the kit's demo pages, all under a root
element of the class `ui` (never `:root`, so other pages keep their look) [C `ui/tokens.css`]. Its look:

- A pale green-grey ground (`--bg`), white raised panels with a 1 px border, a 14 px radius and one soft shadow, a
  blue accent (`--accent`) for links, the primary button, chips and segments that are on.
- Headings in Barlow Condensed (`--display`, bundled, weights 500 to 700), text in the system's font (`--font`),
  values, status chips, column heads and some labels in the system's monospace (`--mono`).
- 34 stroked icons of its own (24 × 24, drawn at 18 px), the logo with the magenta line writing "line".
- Two themes: the system's, or the one chosen (`data-theme`); the map's tiles stay light in the dark theme.
- Touch: `--touch` 36 px for buttons and inputs, 44 px on coarse pointers [C `ui/tokens.css`].

Surfaces with their own class families beside the kit: the server-rendered pages (sign-in, privacy, about;
`ui/pages.css`, `p-*`), the coverage page (`cov-*`), the 3D view (`v3-*`), the highline layer (`c-layer-*`). The CSP
of the app allows styles from its own files only (`style-src 'self'`).

## Colors

**The tokens** (`ui/tokens.css`, both themes, in the header): neutrals (`bg`, `surface`, `surface-2`, `ink`,
`ink-2`, `muted`, `line`), the accent (`accent`, `accent-soft`, `on-accent`), three states with a soft background
each (`ok`, `warn`, `bad`), the map's own (`map-bg`, `water`, `rock`, `terrain`, `tree-fill`, `limit`), the lines
(`clear` magenta, `trees` orange, `fav` yellow, `halo`), the coarser terrain (`coarse`, `coarse-map`), the highline
layer's five density classes (`layer-1` to `layer-5`) and the access mark's states (`acc-*`, `acc-map-*`).

**Contrast of the text tokens** [O: the WCAG ratio computed from the token values, four decimals]:

| Text token | Light: on bg | on surface | on surface-2 | Dark: on bg | on surface | on surface-2 |
| --- | --- | --- | --- | --- | --- | --- |
| ink | 15.2040 | 16.6693 | 14.1857 | 15.5091 | 14.3041 | 12.6527 |
| ink-2 | 7.4775 | 8.1981 | 6.9767 | 9.5884 | 8.8434 | 7.8225 |
| muted | **4.1024** | **4.4977** | **3.8276** | 5.7876 | 5.3380 | 4.7217 |
| accent | 6.2739 | 6.8786 | 5.8537 | 7.8290 | 7.2208 | 6.3871 |
| ok | 4.8775 | 5.3475 | 4.5508 | 9.0001 | 8.3008 | 7.3425 |
| warn | 5.2421 | 5.7473 | 4.8910 | 9.0656 | 8.3613 | 7.3959 |
| bad | 5.9619 | 6.5365 | 5.5626 | 8.2141 | 7.5759 | 6.7013 |

In bold: under 4.5:1. The pairs of a soft background and its state colour are 4.5567 (ok, light) to 6.8606 (bad,
dark); `on-accent` on `accent` 6.8786 (light) and 7.9141 (dark).

As rendered [P]: axe-core's `color-contrast` rule fails on 99 of the 251 light states (964 elements): the 3D view's
tree labels, the coverage page's labels and small texts, small grey texts on Home, Favourites and Account; it leaves
the contrast of 172 states' text over the map or a picture undecided. Not seen by it, the profile chart's labels
[O: `Profile.tsx`'s `PROFILE` colours against `--surface`]: in the dark theme "highest … above terrain" 2.2623:1,
"min. clearance" 3.9583:1, "over trees" 4.2757:1; in the light theme "min. clearance" 4.3692:1 and "over trees"
4.0449:1. Inputs' placeholders have no rule of their own (no `::placeholder` in the CSS); their contrast was not
measured here.

**Colours outside the tokens** [S]: 50 distinct values in 80 places of the CSS (18 of them the sign-in buttons'
brand colours, kept after the providers' guidelines [C `ui/pages.css`]) and 60 distinct in 83 places of the code
(the coverage map's palette 32, the profile chart 17, the other runs' colours 8, the result map 8, the other 18 in
10 files).

## Typography

**Families** (tokens): `--display` Barlow Condensed for headings and the large numbers of a stat; `--font` the
system's sans-serif for text; `--mono` the system's monospace. The kit's levels are in the header (`ui/ui.css`):
text 14 px / 1.45, headings 20 and 30 px, small text 12.5 px in `--muted`, chips 13, segments 13.5, a large button
15.5, inputs 16 px on coarse pointers (so iOS does not zoom), badges 11 px in the monospace, status chips 11.5 px
in monospace capitals, stats' numbers 22 px with tabular figures.

**Sizes in use** [S]: 25 distinct px values over 183 declarations (and 2 `inherit`), from 8 to 32 px:

| px | 8 | 9 | 9.5 | 10 | 10.5 | 11 | 11.5 | 12 | 12.5 | 13 | 13.5 | 14 | 14.5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| declarations | 1 | 5 | 2 | 3 | 1 | 15 | 19 | 13 | 35 | 39 | 3 | 9 | 1 |

| px | 15 | 15.5 | 16 | 17 | 18 | 19 | 20 | 22 | 24 | 26 | 30 | 32 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| declarations | 6 | 1 | 5 | 2 | 4 | 1 | 3 | 7 | 1 | 2 | 4 | 1 |

46 declarations are under 12 px. These are counts of CSS declarations, not of what is drawn. Which values a scale
would keep and which it would fold into a step: R5 (below).

**Text as drawn** [P] (share of the visible characters under a size; in pass 1 the two themes differed by at most
12 characters):

| Device (states, characters) | Under 12 px | Under 11 px | Under 10 px |
| --- | --- | --- | --- |
| Desktop (81, 191 853) | 21 187 (11.0 %) | 16 039 (8.4 %) | 13 666 (7.1 %) |
| iPhone 13 (85, 178 479) | 22 705 (12.7 %) | 13 010 (7.3 %) | 5 450 (3.1 %) |
| Pixel 7 (85, 178 354) | 22 703 (12.7 %) | 13 010 (7.3 %) | 5 450 (3.1 %) |

Where it is: the map's credits and scale (9.8 px on the desktop, 10 px on phones, on nearly every state with a map),
the "Data coverage" button (9.75 px: the rule `.ui button { font: inherit }` overrides its own 13 px), the highline
layer's bar numbers (9 px; 8 px on the iPhone) and chart names (11.5 px), the 3D view's notes (11 px), the list's
column heads (11 px), the bottom bar's labels on phones (11.5 px), the eyebrow lines and the "?" (11.5 px), the
profile chart's labels (11 px).

**Monospace** [S]: 22 rules set it, 13 of them also in capitals (status chips, the list's column heads, eyebrow
lines, the size word, the side panel's rail, field values, the coverage page's labels and pills).

## Layout

- **The C frame** (desktop, `result/view/ResultColumns.tsx`, `ui/SidePanel.tsx`): the list on the left and the
  selected line's details on the right as side panels with a draggable edge (260–560 and 300–600 px, the map at
  least 360 px); a panel folds to a 36 px rail with a vertical label; the profile is a card over the bottom of the
  map. The width that switches to the phone layout is 768 px (`DESKTOP` in `ui/components.tsx`).
- **Phones**: a bottom sheet over the map (peek, 120 px by default; half; full), a bottom bar of 64 px with the
  safe area under it; the search form under the map.
- **Kit spacing** (header): gaps of 6 (chips), 8 (rows) and 12 px (columns), panels padded 14 × 16 px, buttons
  14 px on the sides.
- **Spacing in use** [O: every px length in `padding`, `margin`, `gap`, `row-gap`, `column-gap` and their sides in
  the 21 CSS files, comments removed, signs dropped; a unitless `0` and `inset` not counted]: 24 distinct lengths in
  785 uses over 689 declarations. The most used: 8 px 163, 6 px 101, 10 px 97, 4 px 86, 12 px 76, 2 px 47, 14 and
  16 px 44 each; also 1, 3, 5, 7, 9, 11, 18, 20, 22, 24, 28, 32, 34, 40 and 64 px. Kept and folded by a scale:
  R7 (below).
- **Sideways scroll** [P]: no state's page is wider than its window; one element scrolls sideways by itself on
  phones (the highline layer's charts, 9 states).

## Elevation & Depth

- **One shadow token**, `--shadow` (two layers, darker in the dark theme), and a focus ring `--focus` (3 px of the
  accent at 45 %), drawn on `:focus-visible` only [C `ui/tokens.css`, `ui/ui.css`].
- **Shadows in use** [O: every `box-shadow` declaration of the CSS, its value as written]: 63 declarations, 25
  distinct values; 27 use `var(--shadow)`, 5 `var(--focus)`, 8 `none`, the rest are single literal shadows (the
  segment that is on, the splitter's tab, the sheet's upward shadow, the 3D view's marks and others). What a
  scale would keep: the token, the focus ring and `none` (40 of the 63); what it would fold: the other 23 (three of
  them combine the token with a ring).
- **Layers** [S]: 17 distinct z-index values (1, 2, 4, 5, 6, 7, 8, 9, 10, 900, 1000, 1001, 1002, 1100, 1150,
  1200, 1300), no named scale. They fall into two bands: 1 to 10 inside a page's own parts (panels, the sheet, the
  splitter, the bottom bar) and 900 to 1300 for what goes over the map (Leaflet's corners of controls sit at
  1000). A named scale would keep the bands, not the 17 values; no proposal is made here.
- **"The same grey box"** [S]: 18 selectors draw a container with all four of an opaque surface, a 1 px border, a
  radius of 8 px or more and a shadow; 21 more with three of the four, 28 with two. As rendered [P], by the same
  four (and at least 40 px): 65 of 1 364 containers on the desktop, 31 of 1 706 on the iPhone (the coverage page's
  cards and legends, the 3D view's credits, Home's panels, the profile card, the dialogs). **This strict count does
  not measure the user's tell, "Same grey box everywhere"**. A reading, not the user's words: most of that look is
  boxes without a shadow (grey tiles, side panels, chips). A count that does needs the user's marks on screenshots
  first.

## Shapes

- **Kit radii** (header): 8 px for controls, 10 for the large button, the segmented track and stats, 14 for panels
  and cards, 20 for the sheet's top corners, full (999 px) for chips, badges and status chips, 50 % for round icon
  buttons and dots.
- **Radii in use** [S]: 17 distinct lengths: 8 px 30, 50 % 22, 0 20, 14 px 20, 10 px 16, 999 px 15, 2 px 13,
  3 px 11, 12 px 10, 4 px 8, 6 px 8, 20 px 6, 1 px 2, and 5, 11, 15 px and `inherit` once each. Kept and folded
  by a scale: R6 (below).

## Components

**The kit** (`ui/components.tsx`, styles `ui/ui.css`, classes `u-*`): `Screen` (the root and its theme), `Button`
(default, primary, ghost, danger; large; full width; a link that looks like one), `IconButton` (a toggle, an
opener, plain, round, the favourite's star), `Chip` and `Chips` (a toggle, a removable value, a dashed "add"),
`Segmented` (a radio group), `Panel` (a raised card), `Field` (label, "?" hint, value, control, help text), `Range`
and `RangePair`, `StatusChip` (running, done, waiting, failed, shared), `Progress`, `Stat` and `Stats`,
`BottomNav`, `Sheet` (the phones' bottom sheet), `Splitter` (a draggable edge after WAI-ARIA's window splitter).
Beside them: `Hint` (the "?" and its bubble), `Intro` (the intros' dialog), `SidePanel` (the C frame's panels and
their rail). The kit's demo pages: `?ui=kit` (logo and icons, buttons, chips, segmented, panel, fields and ranges,
status, progress and stats, sheet and bottom bar), `?ui=kit-result`, `?ui=kit-search`, `?ui=kit-layer`.

**Kinds of container, and what tells them apart today**:

| Kind | Where | Look |
| --- | --- | --- |
| Page ground | behind everything | `--bg` |
| Side panel | the C frame's list and details | `--surface`, a 1 px line on one side, no radius, no shadow |
| Panel, card | Home's panels, cards, the sign-in card, the profile card, popovers | `--surface`, 1 px border, 14 px, `--shadow` |
| Dialog | intros, the rig window, confirmations | as a panel, over a scrim |
| Sheet | phones' result | `--surface`, 20 px top corners, its own upward shadow |
| Tile | stats, the segmented track | `--surface-2`, 10 px, no border |
| Chip, input, button | controls | `--surface`, 1 px border, 8 px or full |
| Map controls and notes | zoom, layers, legends, credits, the shore note | `--surface` (some at 80–92 %), border, shadow |

Panels, cards, dialogs, popovers and legends share one look: what sets them apart is their place, not their
container.

**Icons** (`ui/icons.tsx`): 34 icons (search, folder, pin, poly, file, cliff, layers, share, download, star, back,
next, down, filter, bars, ruler, user, close, plus, check, clock, list, home, link, zoom, compare, edit, more,
locate, info, rope, warn, menu, refresh), stroked with the text's colour; the access mark's three signs; the logo
and its mark (`ui/logo/`).

**Characters used beside the icons** [S] (shown in the code / drawn by the CSS / in the catalogue): `·` 77 / 0 / 5
(a joint of parts), `×` 4 / 1 / 20 (a close mark and multipliers), `★` 5 / 0 / 0, `↑` `↓` 2 each (sort), `→` 2 / 0 /
2, `›` 2 / 1 / 0, `Δ` 2, `▾` 1 / 1, `⋯` 1, `▸` and `•` 1 each in the CSS. 83 dense strings (two such characters or
more, or a `·` joint): 75 in the code, 8 in the catalogue, for example the line's facts "prominence 0 m / 1 m · drop
44 m / 41 m" (as shown) and the profile's head, built as `"A1 " + … + " m → A2 " + … + " m"` and `"Δh " + … + " m"`
(`Profile.tsx`).

**Link-like buttons** [O: class names ending in `link` in the CSS and the code]: `c-link`, `cov-link`, `r-link`,
`s-link`, `n-intro-link`, `r-intro-link`, `r-why-link`, beside the credits' toggle (`u-credits-toggle`).

**Legends** [O: CSS classes with `legend` in their name]: 10 classes in 5 families (`c-layer-legend*`,
`cov-legend*`, `fal-profile-legend`, `n-coverage-legend`, `r-legend*`).

**Label styles**: a field's label in the text's font at weight 500; its value in the monospace in the accent; the
list's column heads and the eyebrow lines in monospace capitals (11 and 11.5 px); status chips in monospace
capitals; the rail's vertical label in monospace capitals; a stat's caption at 11.5 px; small text 12.5 px in
`--muted`.

**Texts** [S]: 948 keys in `locales/en.json` (16 empty), 7 857 words. Help texts 54 (a median of 24.5 words, the
longest 113), errors 152 (median 14, longest 44), intro texts 51 (median 6, longest 56), hints 13 (median 6,
longest 39). 25 page files hold English texts in the code and do not use the catalogue.

### Where the code disagrees with itself

- **The lines' colours**: the map draws them from `style.ts` (`#FF10F0`, `#FF8C00`, `#FFD400`), the legend and the
  logo from the tokens (`--clear` `#e10fd6`, `--trees` `#ef8300`, `--fav` `#f0c400`).
- **Copies of the tokens**: the coverage map's palette (`coverage/palette.ts`), `coverage/page/page.css` and
  `app/coverageLayer.css` repeat token values as literals (`#17201c`, `#2350c8`, `#6c7a73`, `#d2dad4`, `#e9eee9`, `#f3f5f2`, `#0e1311`).
- **The profile chart**: 17 colour literals in `Profile.tsx`, not themed (hence the dark theme's 2.26:1 label).
- **One shadow token, 25 shadow values** (above), and the segment, the splitter's tab and the sheet each with a
  literal shadow of its own.
- **Heights of controls**: `--touch` 36 px for buttons, inputs at 38 px, chips 30 px (36 on coarse pointers), the
  "?" drawn at 18 px with a larger invisible target (measured at 32 px on the desktop, 40 px on the phones [P]).
- **Three ways to draw a close or remove "×"**: the `close` icon (chips), a `×` drawn by the CSS (the 3D view's
  activity note), a `×` character as a button's text (the profile's close button, `Profile.tsx`); the same character
  also stands for "times" (a scale factor, an area's width × height).
- **Disclosure arrows**: the `down` and `next` icons beside the characters `▾`, `▸`, `›` (code and CSS).
- **A button that loses its size**: `.ui button { font: inherit }` beats the "Data coverage" button's own 13 px.

## Do's and Don'ts

Only rules the repository already states (the files named); the rules the user picked are in the next section.

- Do scope styles under the root class `ui` and its `u-*` classes, never `:root` (`ui/tokens.css`, `ui/ui.css`).
- Do style through classes or the CSSOM (`element.style`, Preact's `style` prop); don't write `style=` attributes
  or `<style>` in HTML strings: the CSP allows `style-src 'self'` only (`.claude/rules/viewer.md`).
- Don't import `preact/compat` (`.claude/rules/viewer.md`).
- Do bundle fonts, scripts and pictures: no CDN; the viewer also works from `file://` (`.claude/rules/viewer.md`).
- Don't nest buttons: a removable chip is a span with two buttons (`ui/components.tsx`, `Chip`).
- Do give an icon-only button its name, which is also its tooltip (`IconButton`); an icon is hidden from screen
  readers unless it has a title (`Icon`).
- Do keep a draggable edge reachable by keys: arrows, Shift, Home and End, Enter (`Splitter`).
- Do honour reduced motion (`ui/ui.css`).
- Do write UI texts in simplified technical English with highliners' words, never command-line options or code
  names, with a "?" on every setting; texts go into `locales/en.json` (docs/roadmap.md, UI texts).
- Do change the access mark's words and colours together (`.claude/rules/viewer.md`).
- Do show a UI change as an interactive mock-up first, and the built page's screenshots (desktop and both phones,
  light and dark) before it goes into `main` (docs/agent-workflow.md; `.claude/rules/viewer.md`).

## Rules (part 2: picked by the user on 2026-11-17)

The user picked from the proposed options on 2026-11-17 with the answer line "R1 a, R2 a, R2-desktop a, R3 a,
R4-map c, R4-trees b, R5 a, R6 a, R7 c, R8 a, R8-d yes, R9 b, R10-text a, R10-flow a, R11 b, R12 a." and the note
"R11 explain it more to me". Each rule below quotes its pick; what was weighed and not picked stays in one line.

**In force since 2026-11-17**: R1, R2 (phones and desktop), R3, R4.2, R5, R6, R7, R8, R9, R10, R11, R12. **Picked,
not yet in force**: R4.1 (waits for its measurement).

**A rule in force binds new and changed screens; today's screens are brought to it screen by screen in the
improvement rounds, not at once** (the pilot screen first).

**Today's numbers** in this part come from **[B]**, the baseline of record: one full pass of the final measuring
code (`tools/ui_metrics.py pages`) over every state of `tools/ui_shots.py`, both themes, on the desktop, iPhone 13
and Pixel 7 profiles (84 states a phone and 79 on the desktop in the light theme: states a device or the sample run
cannot show are left out, one state timed out). It marks the map's credits and scale as a zone of their own and
keeps every control's size. [S], [W] and [O] as above. **How a rule is checked**: the command named under it, or
the design reviewer ([design-review.md](design-review.md)) where no number exists. Both tools run by hand, through
the test lock (docs/workflow.md), each with an output folder of its own:
- `uv run tools/ui_metrics.py static --out <folder>`
- `uv run tools/ui_metrics.py pages --out <folder> --data-dir <folder> [--only <pages>] [--dark]`; on a kept log,
  `uv run tools/ui_metrics.py pages --out <folder> --summarise --controls 44,40,24 --text 12,11,10` cuts at other
  bounds without a new pass.
- `uv run tools/ui_walks.py --out <folder> --data-dir <fresh folder> [--only F1,F2]`

Under each rule, `ui_metrics.py static`, `ui_metrics.py pages` and `ui_walks.py` stand for these commands, with
their `--out` and data folders.

### R1 The smallest text

- **In force**: no text a user reads is drawn under 12 px. The map's credits and scale are a named exception with a
  floor of 10 px. The user's pick: "R1 a".
- **Today** [B; light theme]:

| Device (states, characters) | Under 12 px: all | outside the credits and scale | Under 11 px: all | outside | Under 10 px: all | outside |
| --- | --- | --- | --- | --- | --- | --- |
| iPhone 13 (84, 177 181) | 22 461 (12.7 %) | 14 256 (8.0 %) | 12 878 (7.3 %) | 4 902 (2.8 %) | 5 439 (3.1 %) | 4 878 (2.8 %) |
| Desktop (79, 188 623) | 20 241 (10.7 %) | 9 533 (5.1 %) | 15 261 (8.1 %) | 4 883 (2.6 %) | 12 888 (6.8 %) | 2 510 (1.3 %) |

  Between 11 and 12 px outside the zone on the iPhone [O on [B]'s log]: 9 354 characters, among them the layer's
  chart names 2 313, the 3D view's notes about 3 300, the layer legend's note 544, the list's column heads 510, the
  bottom bar 336, the profile chart's labels about 600, the "?" 140, the eyebrow lines 125, the size word 125. Inside
  the zone under 10 px: the scale (9.8 px; 561 characters on the iPhone); on the desktop also the credits (9.8 px;
  10 378 characters with the scale).
- **Checked by**: `ui_metrics.py pages`: text under 12 px outside the zone; the zone's text under 10 px is "all
  minus outside the zone" of its under-10 px column.
- Not picked: b. 11 px with the same exception; c. 12 px with no exception; d. no rule.

### R2 The smallest control

- **In force**: on touch screens no control is smaller than 44 px in either direction; on the desktop none is
  smaller than 24 px. Links and buttons inside a sentence are exempt. The user's picks: "R2 a", "R2-desktop a".
  This is wider than the option's words ("Links inside a sentence"), for three reasons: WCAG 2.5.8 exempts any
  target inside a sentence; the measuring tool exempts a link or a button in a sentence; and the numbers the user
  picked from already left those buttons out (30 on the iPhone and 18 on the desktop, beside 436 and 452 links).
- **Excepted by name** (the user, 2026-11-17, "yes" to the planner's recommendation to except them): drawn marks
  that can be pressed, namely the coverage page's map areas and the highline layer's chart bars, each with a list or
  a table beside it that says the same. They count as controls in the measuring tool (2 106 of the iPhone's 3 508
  controls under 44 px), so R2's numbers are read without the coverage page and the highline layer ("the rest"
  below).
- **Today** [B; light theme; links and buttons in a sentence left out; "the rest" leaves out the coverage page and
  the highline layer, where every map area and chart bar is a small control]:

| iPhone 13 | Controls | Under 44 px | Under 40 px | Under 24 px |
| --- | --- | --- | --- | --- |
| All 84 states | 4 592 | 3 508 | 2 737 | 2 103 |
| The rest, 65 states | 2 335 | 1 402 | 781 | 380 |
| Sign-in | 8 | 8 | 5 | 5 |
| Basic search, first visit | 29 | 16 | 7 | 2 |
| Result | 65 | 45 | 30 | 19 |
| Result, a line selected | 79 | 50 | 33 | 19 |

  Desktop [B]: of 4 239 controls over 79 states, 1 349 under 24 px; the rest (60 states): 446 of 2 127.
- **Checked by**: `ui_metrics.py pages`: controls under 44 px on the two phone profiles, under 24 px on the
  desktop, links and buttons in a sentence apart.
- Not picked: phones b. 40 px, c. 24 px; desktop b. no floor.

### R3 The contrast of text

- **In force**: text and its background reach 4.5:1, large text 3:1 (WCAG 2.2 AA), in both themes, including
  secondary text, chart labels and placeholders. The user's pick: "R3 a". Proposed details, not on the page the user
  picked from: "large" read as 24 px, or 18.7 px bold (WCAG's definition), and text over a picture included.
- **Today** [B, O]: axe-core's `color-contrast` fails on 99 states (964 elements; the light theme); it leaves text
  over the map or a picture undecided on 333 states (both themes). `--muted` is under 4.5:1 on all three light
  surfaces (4.1024, 4.4977, 3.8276); the profile chart's labels 2.2623 to 4.3692 (Colors, above); placeholders not
  measured.
- **Checked by**: `ui_metrics.py pages` (axe-core's `color-contrast` violations); text axe leaves undecided,
  in a drawing or on the map: the design reviewer, with the ratio computed from the colours.
- Not picked: b. 7:1 for body text; c. AA plus a stricter bar outdoors later.

### R4 Lines on the map

- **R4.1, picked, not in force**: a line reaches 3:1 against the map right beside it for a stated share of its
  length, measured per base map, and gets a casing (a dark or light edge) only on the base maps where it falls
  short. The user's pick: "R4-map c". It waits for its measurement, which waits for the choice of the 2D map's look
  (that choice changes what lies under the lines). Today: not measured; the map's line colours differ from the
  legend's tokens (Components, above). Not picked: a. 3:1 without casings; b. a casing on every line; decide after
  the measurement.
- **R4.2, in force**: lines over trees are told apart from clear lines by colour only; the list is the alternative
  that does not rest on colour. The user's pick: "R4-trees b". This leaves WCAG 1.4.1 (use of colour) to the list:
  the list must say "over trees" in words (a line's details too: a proposed detail). Today: by colour on the map.
  Checked by the design
  reviewer. Not picked: a. a second cue on the map (a dash or a casing pattern).

### R5 A type scale

- **In force**: font sizes come from a scale of seven steps, 12, 13, 14, 16, 20, 24 and 30 px (a proposed detail:
  a value off the scale needs a reason in a comment). The number of steps and the smallest step (R1) are the rule; the steps from
  13 px up (text, headings) depend on the body font and may move on the pilot's mock-up. The user's pick: "R5 a".
- **Today** [S]: 25 distinct px values over 183 declarations. Mapped to the nearest step (a tie goes up) [O], 109
  of 183 declarations change (103 up, 6 down): 8–11.5 → 12; 12.5 → 13; 13.5, 14.5 → 14; 15, 15.5, 17 → 16; 18,
  19 → 20; 22, 26 → 24; 32 → 30. Counts of CSS declarations, not of text drawn.
- **Checked by**: `ui_metrics.py static` (the font sizes in use).
- Not picked: b. eight steps from 11 px; c. six steps (12, 13, 14, 16, 20, 30); d. five steps (12, 14, 16, 20, 30).

### R6 A radius scale

- **In force**: radii come from four steps, 3, 8, 14 and 20 px, plus "full" (pills) and "round" (50 %). The number
  of steps is the rule; the values belong to the look and may move on the pilot's mock-up. The user's pick: "R6 a".
- **Today** [S]: 17 distinct lengths. Mapped to the nearest step [O], 60 of the 127 px declarations change: 1–5 →
  3; 6, 10 → 8; 11, 12, 15 → 14; 20 stays (the sheet); 999 px and 50 % stay as full and round, 0 as none.
- **Checked by**: `ui_metrics.py static` (the radii in use).
- Not picked: b. 4, 8, 14 px; c. 6, 12 px.

### R7 A spacing scale

- **In force**: padding, margins and gaps come from a 4 px grid of seven steps: 0, 4, 8, 12, 16, 24 and 32 px.
  Spacing is open for the mock-ups ("Keep anchors, open the rest"), so the values may move on the pilot's mock-up;
  the number of steps is the rule. The user's pick: "R7 c".
- **Today** [O]: 24 distinct px lengths in 785 uses (Layout, above). Mapped to the nearest step (a tie goes up), 386
  of the 781 uses up to 32 px change (346 up, 40 down):

| Step | Today's values (uses) |
| --- | --- |
| 0 | 0 (8), 1 (7) |
| 4 | 2 (47), 3 (18), 4 (86), 5 (6) |
| 8 | 6 (101), 7 (11), 8 (163), 9 (12) |
| 12 | 10 (97), 11 (8), 12 (76) |
| 16 | 14 (44), 16 (44), 18 (15) |
| 24 | 20 (16), 22 (3), 24 (17) |
| 32 | 28 (1), 32 (1) |

  The four uses above 32 px (34 twice, 40, 64) are layout lengths outside the scale (the user, 2026-11-17: "yes").
- **Checked by**: the design reviewer reads the change's CSS; the measuring tool does not count spacing yet (the
  count above is this file's own).
- Not picked: a. eleven steps (0, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32; 125 uses change); b. nine steps (0, 2, 4, 6,
  8, 12, 16, 24, 32; 238 change).

### R8 Levels of container

- **In force**: three levels, each with one purpose. **Ground**: the page's own sections (groups of a form, the
  parts of a side panel). **Raised**: what floats over the map or over other content (the sheet, popovers, dialogs,
  the profile card, map controls). **Inset**: a value or a control set into its container (inputs, tiles, the
  segmented track). And: no box around a single sentence; a group gets a box only when it can be moved or folded,
  or lies over something else. The levels' look is the pilot mock-up's. The user's picks: "R8 a", "R8-d yes".
- **Today** [S, B]: panels, cards, dialogs, popovers and legends share one look (Components); 18 selectors use all
  four of surface, border, radius and shadow; as rendered, 65 of 1 345 containers on the desktop and 31 of 1 699 on
  the iPhone by that strict definition, which does not measure the user's tell (Elevation).
- **Checked by**: the design reviewer (no number measures it yet).
- Not picked: b. two levels (ground and raised); c. four levels (ground, band, raised, overlay).

### R9 Characters as icons, and dense strings

- **In force**: in a text the user reads, no character stands for a word or an icon. A value is written as its
  label, the value and its unit ("Clearance 0.1 m"), several values as a table or a list of such pairs. Allowed:
  units (m, km, °, %), an en dash in a range ("30–300 m"), ≤ and ≥ in a filter's chip, and `·` in one-line meta
  lines (a date and a count under a title), never between values; everything else from the icon set (sort
  direction, disclosure, close, favourite) or written out. The user's pick: "R9 b".
- **Today** [S, B]: 84 dense strings (counted per literal; 83 per line before); `·` as a joint 77 times in the code;
  21 arrow and mark characters shown in the code and 5 drawn by the CSS; `×` 20 times in the catalogue
  (multipliers). In the image sketches of 2026-11-16 all five directions turned the line's dense facts into
  labelled values, the shortest as a table with one column per anchor.
- **Checked by**: `ui_metrics.py static` (characters and dense strings); whether a `·` stands in a meta line:
  the design reviewer.
- Not picked: a. no `·` at all; c. only the values follow the rule.

### R10 Text length

- **In force, per text**: a help text (a "?") at most 40 words, an intro paragraph 30, a hint 25, an error 30; the
  longer story goes behind a link or a "?". The user's pick: "R10-text a".
- **In force, for the flow**: at most 400 visible words before a first search (the sign-in page to Start on a
  phone). The user's pick: "R10-flow a".
- **Today** [S; O for the counts over a limit, words split on spaces as [S] does]:

| Kind | Texts | Median | Longest | Over the limit |
| --- | --- | --- | --- | --- |
| Help (a "?"), 40 | 54 | 24.5 | 113 | 6 |
| Intro paragraph, 30 | 51 | 6 | 56 | 6 |
| Hint, 25 | 13 | 6 | 39 | 2 |
| Error, 30 | 152 | 14 | 44 | 8 |

  Before a first search [W, F1 on the iPhone]: 568 visible words over its screens: the sign-in page 58, the beta
  notice 140, Home 37, the search's intro 183 (of its 425: the rest is scrolled out), the form 75, the form with the
  place set 75 (the same screen counted again). Without the beta notice and the intro: 245; within 400, the notice
  and the intro together keep at most about 155 visible words.
- **Checked by**: per text, `ui_metrics.py static` gives each group's median and longest and the 25 longest
  texts, not the count over each limit: today the count is made from `locales/en.json` (each text's words split on
  spaces, as [S] does, against its group's limit), a gap of the tool. For the flow, `ui_walks.py --only F1` (the
  words over its screens).
- Not picked: per text b. 30, 25, 20, 25 and c. help 60 only; for the flow b. 250 and c. no limit.

### R11 Controls on a first-timer's screens

- **In force**: a screen of the first-timer's way (sign-in, Home on a first visit, the Basic form, the first result
  and a line's details on a phone; the beta notice too, a proposed detail) shows at most 25 controls at once. The
  user's pick: "R11 b", with the note "R11 explain it more to me"; after the explanation, the same day: "it stands".
  The rule is for the first-timer's way on a phone only; the rigger's desktop is not bound by it.
- **The measure**: [W]'s count, the visible, enabled controls of the surface in view (not [B]'s, which counts the
  whole page: 35 for the Basic form where [W] sees 20 to 22).
- **Today** [W]: F1 (sign-in to Start): 8, 4, 6, 3, 20, 22. F2 (the first result): Home 13, the intro 2, the result
  34, the details 24, the profile 20. At 25 the Basic form stays as it is and the phone's result loses 9 (each row of
  its list is three controls today).
- **Where the rigger's depth goes instead**: the Advanced tab and "More settings", the desktop's side panels and
  their columns, sorting and filters one step away, the keyboard.
- **Checked by**: `ui_walks.py --only F1,F2` (the most controls on a screen).
- Not picked: a. 20; c. no number, decision points per walk instead.

### R12 What a UI change shows before `main`

- **In force**: a change of a screen comes to review with the numbers of `tools/ui_metrics.py` before and after on
  the pages it touches (text under R1, controls under R2, axe-core's violations, containers, dense strings), the
  walks it touches (`tools/ui_walks.py`), and the screenshots (desktop and both phones, light and dark). A design
  reviewer reads them with PRODUCT.md and this file and gives a verdict: [design-review.md](design-review.md). The
  user's pick: "R12 a".
- **Checked by**: the reviewers' steps of docs/agent-workflow.md, section 4 (the scope, code and design reviewers
  before the session's review and the user's word).
- Not picked: b. screenshots and the design reviewer only; c. a, plus a check that fails on a number that got worse.

### Waiting for the pilot's mock-up

The parts of the look the user left open are settled on the pilot screen's mock-up, then written here.

#### Colours beyond the anchors

Settled on the pilot's mock-up.

#### Body font

Settled on the pilot's mock-up (the type scale's steps from 13 px up: R5).

#### Corner and edge shapes

Settled on the pilot's mock-up (the number of radius steps: R6).

#### Spacing values

Settled on the pilot's mock-up (the number of steps: R7).

#### The containers' look

Settled on the pilot's mock-up (the levels: R8).

#### The label style

Settled on the pilot's mock-up.
