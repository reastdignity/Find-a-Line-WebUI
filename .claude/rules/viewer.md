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

## Pitfalls

- **The viewer** works from `file://`: no `fetch`, so a run's data is a script (`data.js`, downloaded only over
  http(s)) and the list of runs too (`runs.js`); a download with progress is an XMLHttpRequest (`download.ts`), never
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
  naming it; the About page links it (`web.THIRD_PARTY_LICENCES`): a new runtime dependency changes it.

## Verifying changes

- UI changes (viewer/src, the server-rendered pages): a visual review before calling them done: `uv sync --group ui`,
  `uv run playwright install chromium webkit` (once),
  `uv run tools/ui_shots.py --out <scratch> --only <pages> --dark`, look at every screen the change touches on the
  desktop and both phones, and show the screenshots with recommendations. Phones need the device profiles: a narrow
  headless window is not a phone (no viewport meta, pixel ratio or touch; headless Edge on Windows does not go below
  about 500 px), and WebKit on Windows has Windows' fonts, not San Francisco.
- Map/JS changes: `tests/test_viewer.py`, then generate a small map (the Żabi Koń clip in `tests/data`, offline),
  append a test `<script>` to a copy and run headless Edge (`msedge --headless --dump-dom` for checks, `--screenshot`
  for a look; `window.FINDALINE_MAP` is the Leaflet map; in the app page `window.FINDALINE_PLACE` is its `PlaceMap`,
  and `tests/test_web.py` has `_edge_page` with stubs for the event stream). Synthetic `mousemove` works; headless
  screenshots don't keep hover state. "Other runs" across coordinate systems: reproject the clip to UTM (rasterio) and
  run it as a second run.
