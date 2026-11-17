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

- `viewer/src/Profile.tsx` with `viewer/src/profile.css` serves two bundles: the 2D result and the 3D view's card
  (`view3d/profilecard.tsx`, which gives it `cursorAt`/`onCursor`; without them the chart behaves as in the result). A
  change of its props, classes or CSS is checked in both (`tests/test_view3d_profile.py`, the result's tests). The 3D
  view's key of a line is the 2D result's (`save.ts` `canonicalKey` = `keys.lineCoords`' text of the same numbers): a
  favourite saved in one shows in the other; the address's `&also=` lines (`page.ts`, `app/c/ResultPage.tsx`
  `view3dOf`, the model's `alsoOf`) are such keys.

- The page keeps a run's lines as columns (`types.ts` `lineColumns`, store wave 1): a new value of a line goes into
  `ROW_FIELDS` or `EXTRA_FIELDS` (with the scale map_rows' decimals give), `lineAt` and `LineCursor` beside `toLine`
  (`tests/test_viewer.py::test_columns_give_the_rows_values` compares every value with toLine's), and a store's
  column into `storedColumns` (run-files.md: the store's reader and `linestore`'s schema); the result's
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
  `search.py`'s note) and the run's heads the key `access_skipped` (`types.ts` `RunHead` = `mapping.map_heads`).

## Pitfalls

- **The viewer** works from `file://`: no `fetch`, so a run's data is a script (`data.js`, downloaded only over
  http(s); a run with a store over http(s) its `lines.arrow`/`profiles.arrow` as bytes, `result/load.ts`) and the
  list of runs too (`runs.js`); a download with progress is an XMLHttpRequest (`download.ts`), never
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
  placeholders use `--muted`, which holds 4.5:1 on every light and dark surface (`test_secondary_text_contrast`).
- **The map's corners** (`result/view/corners.ts`): the scale goes above the credits wherever they run under it,
  re-checked when the scale's or the credits' size changes (`keepScaleAboveAttribution` for a map with no sheet or
  card).

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
