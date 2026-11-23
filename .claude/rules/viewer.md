---
paths:
  - "viewer/**"
  - "locales/**"
  - "tools/ui_shots.py"
---
# The viewer (TypeScript, Preact, Leaflet)

What each part holds: docs/code-map/viewer.md. Rules that load with their own files: `run-files.md` (`types.ts`,
`grouping.ts`, `keys.ts`, `favourites.ts`, `folders.ts`, `shore*.ts`), `line-test.md` (`sag.ts`, `endzone.ts`),
`view3d.md`, `coverage-map.md`, `country-layer.md` (the `#layer` page), `web-app.md` (`locales/en.json`: the message
catalogue), `browser-tests.md`.

## Must stay in sync

- The words of the files `tests/test_texts_in_catalogue.py` names (`MOVED`) are texts of `locales/en.json` (`t`): its
  guard catches any word put back in their JSX text or text attributes and a phrase in their code, and checks that a
  call gives each `{{name}}` of its text. Today's result page's own components (`FilterBar`'s bar, `LineDetails`,
  `LinesTable`, `ResultColumns`) and the kit's demo pages still hold English in code (docs/known-bugs.md, step 3d G4,
  G6). A sentence with an icon or a link
  inside is one key drawn by `i18n.parts`, and a value that stood as a text node of its own stays one (Chromium places
  a line's glyphs by its text nodes: merged nodes change pixels).

- `viewer/src/Profile.tsx` with `viewer/src/profile.css` serves two bundles: the 2D result and the 3D view's card
  (`view3d/profilecard.tsx`, which gives it `cursorAt`/`onCursor`; without them the chart behaves as in the result). A
  change of its props, classes or CSS is checked in both (`tests/test_view3d_profile.py`, the result's tests). The 3D
  view's key of a line is the 2D result's (`save.ts` `canonicalKey` = `keys.lineCoords`' text of the same numbers): a
  favourite saved in one shows in the other; the address's `&also=` lines (`page.ts`, `app/c/ResultPage.tsx`
  `view3dOf`, the model's `alsoOf`) are such keys.

- The page keeps a run's lines as columns (`types.ts` `storedColumns`): a new value of a line goes into
  `ROW_FIELDS` or `EXTRA_FIELDS` (with the scale of its decimals), `lineAt` and `LineCursor`, the tests' row reader
  `viewer/test/rows.ts` (`toLine`, `lineColumns`: `tests/test_viewer.py::test_columns_give_the_rows_values`), and
  `storedColumns` (run-files.md: the store's reader and `linestore`'s schema); the Node units bundle
  `test/types_rows.ts` or `test/model_rows.ts` (src with the rows' reader) for made-up runs; the result's
  page makes a Line only through `ResultModel.lineAt`, so code that goes through every line reads the columns
  (`forEachLine`, a `LineCursor`), never `rep`/`members` of every spot (each makes Lines).

- The access mark (`access.tsx`; run-files.md for the files' side): its values (`types.ts` `ACCESS_HARD` 0,
  `ACCESS_CANNOT_TELL` 1, `ACCESS_EASY` 2 = `access.py`'s) and the names in a head's `ends` (`ACCESS` = `runs.ACCESS`);
  the three states' words (`ui.access.*`) are the accepted mock-up's (2026-11-15) and stand in the legend, the
  details, the help's key and A2's `field.access.help`: change them together; the colours are the tokens `--acc-*`
  (`ui/tokens.css`: light, dark, and `--acc-map-*` for the map, whose tiles stay light). The form's default lives in
  `search/basic.ts` (`basicValues`: on), never in `SearchParams` or the schema: the form sends what differs from the
  schema's default, so a default moved there would drop the ticked value from the request. A search too wide for the
  access grid runs without the mark: the estimate's note has the code `access_skipped` (`basic.ts` `ACCESS_SKIPPED` =
  `search.py`'s note) and the run's head the key `access_skipped` (`types.ts` `RunHead` = `mapping.map_head`).

- The result view (a run's page by default since line volume's round 6; docs/code-map/viewer.md): `result/spots.ts`
  reads the store's `spot`, `top`, `by_spot` as written (run-files.md: the order inside a spot is Python's); its
  interface (`SpotView`, `SpotMap`, the slots of `view/SpotPanels.tsx`) is shared with the panels: add to it, never
  rename. The panels (`view/Spot*.tsx`, `FanPanel.tsx`, `Hint.tsx`, `ViewFilters.tsx`) import only types from
  `SpotPanels.tsx` (it imports their slots, and the Node units bundle them without Leaflet), make no Line for a row
  (`view.values`, the columns' `at`), keep a row as a list item with one button and its other controls as siblings,
  and keep in the browser only the sort, its direction and the hint (`viewstate.ts`; "Top level only" is on at every
  start), and today's `findaline.lastFolder` through the folder picker; a new slot of the frame is optional in
  `SpotPanels`.
  `SpotMap.ts` draws from the columns (no Leaflet layer per line) and the legend lists `legend()`'s shapes;
  a number is placed clear of every `[data-map-control]`, `.leaflet-control` and the frame's obstacles: a new box
  over the map carries `data-map-control`, and one that takes no press (a desktop's toast, the bar's rows) has
  `pointer-events: none`; on a phone the map's message is the status line's first line (`MapBar` `message`). The
  view's look lives in tokens (`ui/tokens.css`: the accent, the neutrals (the whole app's since step 3c), `--fs-*`, `--r-*`) and single
  rules, each listed in docs/DESIGN.md "The pilot's look": change a choice there, not by a copy of its value. No
  control may cover another at any stop of a phone's sheet
  (`tests/test_shell_c_view_map.py::test_phone_controls_apart` names them by their own classes: add a new one there);
  Leaflet's own controls lie above the bar (`.v-map > .c-leaflet` makes no stacking context). The
  phone's sheet has no height at the first draw (`covered` counts its state's height until then), and Preact 11 runs
  an unmounted frame's effect cleanups after the paint, before the next frame's effects.

- The result view's pairs (round 6): which page opens is `SpotColumns.tsx` `VIEW_DEFAULT` with `viewWanted` (only an
  answer other than the default is kept in `findaline.view`); a test or tool that checks today's page pins it with
  `tools/today_page.py`, never by leaving the flag out. `SpotMap.ts`'s placement of the numbers (`APART_MIN`, the
  seven fractions, the 32 × 23 box, the fan's 0.82, `markSize`) has a copy in `tools/view_numbers.py`;
  `SpotView.topOnlyHides` reads the filters as `pass()` does (`test_view_link.py`'s `K.topRule`); `shoreLayer.ts` `INFO_ICON`
  copies `ICONS.info` (`test_access_view.py`): change each pair together. The canvas also draws today's features
  (outline, halo, other runs, a measurement), none pressable or counted.
- The frame's geometry: the view's card stands on the credits (`--v-card-bottom`, `corners.ts` `onCredits`), the foot
  above it (`useFootClear`'s cover) and the canvas's `setCovered` takes its height: change the three; `useSheetKeeps`
  counts the sheet at rest only once the credits' corner stands above it. Every move goes into the bar's room, a
  selection's fit through `selectedFit`; no move's padding grows for the controls. While P3's drop runs (a selection
  at full), `bar()` and `free()` count the sheet at half.
- `Profile.tsx` draws at `TEXT_PX` with `LABEL_BOXES` (measured at 12 px): a size change changes both; `labels.ts`'
  defaults stay its Node test's 11 px. `ProfileDock`'s `compact` is the view's phone docks' only; today's page and
  the cards never pass it. `layersControl.ts` holds the maps' layers control: the view never imports
  `app/PlaceMap.ts` (its Leaflet-Geoman would join `viewer.js`). `coarserLayer.ts` takes the shore chip's classes:
  a change of that look changes both. The narrow desktop list on touch shares its columns by measured widths (39 /
  43 / 53 / 28 px): new words or units re-measure them (`test_list_at_1024_keeps_heads_and_values_apart`).
  `SpotActions.tsx` imports `report.ts`, which reads the page at load: the panels' Node bundle leaves it out.

## Pitfalls

- **The disk notice** (store wave 4): a run's map.html written since then (`mapping.MAP_HTML`, `DISK_NOTICE` =
  `map/main.tsx` `NOTICE`) stands after the viewer's script, so the viewer marks a served page (`fal-served`, by
  `map/served.ts`, which stays the entry's first import; hidden by `map/notice.css` in the head's viewer.css) before
  the notice is parsed: no frame shows it over http(s), even when a later module throws; from disk it
  loads nothing. Its sentence is `ui.map.disk_notice`, filled by Python (`mapping.map_page`); the page shows it without
  the bundle too (`tests/test_disk_notice.py`). A map.html written before (no notice) gets the same notice from the
  bundle from disk (`map/main.tsx` `diskNotice`: no run is read from disk since store wave 4's item 5).
- **The viewer** reads a run over http(s) only, its `lines.arrow`/`profiles.arrow` as bytes (`result/load.ts`), and
  the list of runs as a script (`runs.js`); a download with progress is an XMLHttpRequest (`download.ts`), never
  a fetch's streamed body: headless Edge's `--dump-dom` runs its virtual time ahead of a stream (with no timer left it
  jumps to the budget's end, and 16 tests saw no run), while it waits for an XHR as for a script; everything it needs
  (Leaflet, its CSS and marker images) is in the bundle, no CDN. The app serves it with `style-src 'self'`: no
  `style=` attributes or `<style>` in HTML strings (classes, or the CSSOM: `element.style`, Preact's `style` prop);
  `tests/test_web.py` counts CSP violations in headless Edge. Never import `preact/compat` (not even for
  `createPortal`): it changes Preact's options for the whole bundle, every input's `onChange` then listens to `input`
  events (the result's filter editor stopped reacting to a change: `tests/test_shell_c.py::test_shell_c_desktop`); a
  second tree goes in with `render` of `preact` (LayerPage's right panel). After changing `viewer/src` or
  `locales/en.json` (the message catalogue is bundled into `app.js`): `cd viewer; npm install` (once), `npm run check`
  (types), `npm run build` (under `tools/test_lock.py` on Windows `npm` is not found: `node build.mjs`), and commit
  `dist/`. Users need no Node.
- **viewer/dist is committed**: the global `dist/` rule of `.gitignore` has an exception (`!viewer/dist/`), and
  `.gitattributes` marks it `-text`, so git never changes its line endings (the test compares it byte for byte with a
  fresh build). Start scripts keep their line endings (`*.sh`/`*.command` LF, `*.bat` CRLF). `build.mjs` also writes
  `dist/THIRD-PARTY-LICENSES.txt` (`generate-license-file` over the runtime dependencies, LF, without TypeScript and
  `@types/*`, which are never bundled and would make it differ per platform) and starts every bundle with a comment
  naming it; the About page links it (`web.THIRD_PARTY_LICENCES`): a new runtime dependency changes it
  (apache-arrow, 2026-11-15: with flatbuffers and json-with-bigint; its `@types/node` stays out).
- **`.ui button, .ui input, ... { font: inherit }`** (`ui/ui.css`) outranks a rule of one class: a control's own
  font rule needs two classes (`.n-coverage .n-coverage-btn`), or the control is drawn at its parent's size.
- **Touch texts**: a text that names a click or a key has a `<key>_touch` twin in the catalogue, chosen by
  `ui/components.tsx` `TOUCH` (`(pointer: coarse)`; code without Preact asks `matchMedia` itself). Secondary text and
  placeholders use `--muted`, which holds 4.5:1 on every light and dark surface and on the selected fill `--accent-soft`
  (4.90 / 4.56:1; `test_secondary_text_contrast`): compute a text's pair on a fill before using it. What the
  canvas draws on the tiles in the accent takes `--accent-map` (the light value in every theme: the tiles stay light).
- **Keyboard rings and radio groups** (docs/DESIGN.md rows 81, 82): a ring is a shadow (`--focus`), which forced
  colours do not draw (`ui.css`'s outline rule stands in); a ring a box clips is drawn inside (`--focus-in`) with a
  forced-colours `outline-offset: -2px` beside it; no `outline: none` in a control's focus rule (it hides the forced
  outline); a page's own `scroll-margin` wins over the kit's `:where` rule. A radio group takes `ui/radios.ts`
  (`radioKeys` on the group, its checked radio the one Tab stop; `radioFocusKeys` where a choice costs more than a look,
  the goal cards), no keys of its own.
- **The map's corners** (`result/view/corners.ts`): the scale goes above the credits wherever they run under it,
  re-checked when the scale's or the credits' size changes (`keepScaleAboveAttribution` for a map with no sheet or
  card).
- **Scrollers of many rows on iOS** (gate 2): positioned rows holding absolute children (`u-sr`) made iOS WebKit scroll
  the view's sheet on the main thread (1-3 fps on 420 rows); the view's scrollers carry `will-change: transform`
  (view.css) for that. The rows stay positioned: absolute boxes hanging off the resizing sheet body cost every frame of
  a sheet's move (headless WebKit 77 against 63 ms a frame on 420 rows). Nothing `position: fixed` inside such a
  scroller (it would be placed against the layer). The move is still jerky on a long list: docs/known-bugs.md.

## Verifying changes

- UI changes (viewer/src, the server-rendered pages): a visual review before calling them done: `uv sync --group ui`,
  `uv run playwright install chromium webkit` (once),
  `uv run tools/ui_shots.py --out <scratch> --only <pages> --dark --data-dir <scratch>/ui-data` (the data folder kept:
  a later start skips the clip's search and cubes; `--list` shows which pages `--only` picks), look at every screen
  the change touches on the desktop and both phones, and show the screenshots with recommendations. Phones need the device profiles: a narrow
  headless window is not a phone (no viewport meta, pixel ratio or touch; headless Edge on Windows does not go below
  about 500 px), and WebKit on Windows has Windows' fonts, not San Francisco.
- Map/JS changes: `tests/test_viewer.py`, then generate a small map (the Żabi Koń clip in `tests/data`, offline),
  append a test `<script>` to a copy and run headless Edge (`msedge --headless --dump-dom` for checks, `--screenshot`
  for a look; `window.FINDALINE_MAP` is the Leaflet map; in the app page `window.FINDALINE_PLACE` is its `PlaceMap`,
  and `tests/test_web.py` has `_edge_page` with stubs for the event stream). Synthetic `mousemove` works; headless
  screenshots don't keep hover state. "Other runs" across coordinate systems: reproject the clip to UTM (rasterio) and
  run it as a second run.
