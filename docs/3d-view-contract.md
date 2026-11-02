# 3D view: the contract of the waves

The shared names and formats of the agents that build the 3D view of a line (plan: `docs/3d-view.md`,
"Decisions"; the coordinator's plan file holds the waves). Every agent reads this first. Anything not settled here
is asked of the coordinator, not decided alone. The coordinator updates this file between waves.

## Branches and ownership
- Integration branch `line-3d-view` (never `main`). Each agent works in its own worktree
  `.claude/worktrees/l3d-w<N>-<name>` on branch `l3d-w<N>-<name>` made from `line-3d-view`; the coordinator merges.
- Never edited by agents: `locales/en.json` (every text below is already there), `docs/3d-view*.md`, `CLAUDE.md`,
  `tests/data/patch_zabi_kon.*`, `tests/data/make_patch_fixture.py`. Need a new text or a change here: report it.

| Wave 1 agent | Owns |
| --- | --- |
| S1 server | `search.py` (`patch_of_line`), `jobs.py` (`quick_patch`, `QUICK`, the exemption in `Redact`), `web.py` (`/api/patch`, `/view3d`, `VIEW3D_HTML`, the per-path CSP and Cache-Control in `guard`, `RATE_NAMES`), `settings.py` (`patch_rate`), `README.md` (the limits row), `deploy/nginx/*` (the group), new `tests/test_patch.py`, and the needed rows in `tests/test_public.py`, `tests/test_web.py`, `tests/test_units.py`, `tests/test_deploy.py`, `tests/test_metrics.py`, `tests/test_monitoring.py`, `deploy/monitoring/*` where groups are listed |
| V1 viewer | `viewer/package.json` and its lock, `viewer/build.mjs`, new `viewer/licences/`, new `viewer/src/view3d/`, the button in `viewer/src/result/view/ResultWorkspace.tsx`, `LineDetails.tsx` and `viewer/src/app/d/AppD.tsx`, `viewer/dist` (rebuilt), the Node tests in `tests/test_viewer.py` |

## Names
| What | Name |
| --- | --- |
| Page | `GET /view3d`, its hash `#run=<id>&line=<lat1>,<lon1>,<lat2>,<lon2>` (as `/api/profile`'s `line`, 7 decimals) |
| Template | `web.VIEW3D_HTML`: `<div id="view3d" class="ui"></div>`, `/app/view3d.css`, `/app/view3d.js`, the favicon, `<meta name="findaline-user">` (as `APP_HTML`), `key_meta` (`findaline-esri-key`), `<meta name="findaline-3d-ring" content="on|off">` (off until wave 3), no token (the page only GETs) |
| Bundle | esbuild entry `view3d: "src/view3d/main.ts"` → `dist/view3d.js` and `dist/view3d.css` |
| Data | `GET /api/patch?run=<id>&line=<4 numbers>&step=<1|2>` with the request header `X-Findaline-Patch: 1` |
| Quick kind | `patch` (`jobs.QUICK`), `search.patch_of_line` |
| Rate | `Limits.patch_rate`, public default `"10/minute;120/hour"`, `web.RATE_NAMES` "patch", code `rate_patch` |
| Ring switch (wave 3) | `FINDALINE_3D_RING` (`on`/`off`, default off) |
| Phone level | `(pointer: coarse)` → phone; override `?level=phone` or `?level=full` before the hash |

## `/api/patch`
- **Checks**, in `/api/profile`'s order (`web.py` `/api/profile`): `run_access` (another user's run 404),
  `current_user`, the header (403), four finite numbers (400 `patch_line`), on the public site the bounds of
  `profile_problem` with the patch codes (`patch_outside`, `patch_admin_only` for `ADMIN_SOURCES`), the rate (429
  `rate_patch`), then the quick lane. One quick task at a time per user (the page sends patch and profile one after
  another).
- **Grid**: the run's source, resolution, filling and water settings rebuilt from run.json as `profile_of_line`
  does, surface model off; a square polygon (`SearchParams(geometry=...)`) centred on the line's middle, its corners
  on the run's pixel edges (`Source.grid_origin`). Side in samples at step 1: `512·n + 1` with
  `n = ceil(side_m / res / 512)`, `side_m = max(1536, length + 500)`; refused above `MAX_MEASURED_PX`
  (`patch_too_large`, params `km`, `max`); another CRS than the run's: `patch_crs`; no finite height: `patch_no_data`;
  relief above 3276.7 m: `patch_relief`. `step=2` takes every second sample of rows and columns, starting with the
  first (`[::2, ::2]`).
- **Answer** (200, `Content-Type: application/octet-stream`, `Cache-Control: no-store` as every `/api/*`):
  `uint32 little-endian N` | `N bytes of UTF-8 JSON meta` | `the deflated heights`.
- **Meta** (JSON object):

  | Key | Value |
  | --- | --- |
  | `width`, `height` | samples in a row, rows |
  | `step` | 1 or 2 |
  | `res` | metres between samples (the run's resolution × step) |
  | `crs` | the run's CRS as data.js writes it |
  | `left`, `top` | the outer edges of the sampled grid in the run's CRS: sample (row i, column j) has its centre at `x = left + (j + 0.5)·res`, `y = top − (i + 0.5)·res` |
  | `base_dm` | integer decimetres the values are relative to |
  | `anchors` | `[{"x", "y", "h"}, {…}]`: the line's anchor pixels in grid metres (pixel centres, as data.js `x1…y2`) and the DEM's height there in metres (2 decimals, as `e1`/`e2`) |
  | `affine` | `[a0, a1, a2, b0, b1, b2]`: `lon = a0 + a1·x + a2·y`, `lat = b0 + b1·x + b2·y` (x, y grid metres), least squares over a 5 × 5 lattice of the patch |
  | `rigging`, `model` | the run's, as data.js |
  | `ortho` | the run's `ortho` entry exactly as `mapping.save_map` writes it into data.js (`null` without one) |
  | `attribution` | the run's data credits as data.js `attribution` |
  | `sha256` | hex sha256 of the deflated heights |

- **In the quick table** the answer is `{"meta": {...}, "heights": "<base64url, no padding>"}`; `Redact` must leave
  the `heights` field alone (it masks secrets inside strings); the endpoint checks the sha256 before sending
  (mismatch: 500 with code `patch_damaged`).

## Body: the heights
Reference implementation and fixture: `tests/data/make_patch_fixture.py` (`encode`, `decode_values`, `decode`),
`tests/data/patch_zabi_kon.bin` and `.json` (513 × 513, the last 16 × 16 samples no data, `values_sha256`).
- Values: `v = rint(h · 10) − base_dm` as int16 (decimetres above `base_dm = floor(min(h) · 10)`), `−32768` for no
  data; heights back: `h = (v + base_dm) / 10` (error ≤ 0.05 m).
- Row-major from the top row; within a row horizontal deltas `d[0] = v[0]`, `d[j] = v[j] − v[j−1]`, int16 wrapping;
  little-endian; zlib format (RFC 1950: Python `zlib.compress`, the browser's `DecompressionStream("deflate")`).
- Decoder in JS: `acc = 0; for each j: acc = ((acc + d[j]) << 16) >> 16; v[j] = acc` per row.
- Equal means equal decoded values (`values_sha256`), not equal deflated bytes.

## Geometry in the page
- **Scene axes**: the local origin is the patch centre `(cx, cy)` in grid metres and the height `h0 = base_dm / 10`;
  `X = x − cx` (east), `Y = h − h0` (up), `Z = −(y − cy)` (south). Keeps float32 exact to centimetres.
- **Chunks**: the decoded grid is padded with no data to `512·k + 1` on both sides and meshed in chunks of 513 × 513
  samples with one shared `Martini(513)` (vendored `@mapbox/martini` 0.2.0, ISC); no triangles over no data; skirts at
  chunk edges; the anchors' and the line's footprint samples forced into the mesh (their errors set to `Infinity`
  before `getMesh`).
- **Webbing**: `geometry.ts` (pure, tested in Node): from the two anchors `(x, y, h)` and the meta's rigging,
  `span = hypot(Δx, Δy)`, `dh = h1 − h2`; `sag.ts` `estimate(span, dh, rigging)`, `athlete(x)`; a point at distance
  `s` along the span with drop `d` is `(x1 + Δx·s/span, y1 + Δy·s/span, h1 − d)`. The walker starts at the largest
  sag of the envelope (`f`, `sag`).
- **Lat/lon**: grid metres → lon/lat with the meta's affine; lon/lat → Web Mercator for texture UVs.

## Texts (already in `locales/en.json`)
`ui.view3d.open`, `.title`, `.back`, `.loading_terrain`, `.loading_imagery`, `.loading_profile`, `.error_title`,
`.no_webgl`, `.context_lost`, `.reload`, `.imagery`, `.imagery_ortho`, `.imagery_esri`, `.imagery_shaded`,
`.no_imagery`, `.walker`, `.walker_position`, `.walk`, `.stop`, `.speed`, `.speed_value` (`{{times}}`),
`.reduced_motion`, `.length` (`{{m}}`), `.sag` (`{{m}}`), `.clearance` (`{{m}}`), `.over_trees`, `.edit_hint`,
`.edited`, `.reset`, `.phone_level`, `.level_full`, `.credits`, `.preview_note`; errors `error.patch_line`,
`patch_admin_only` (`{{source}}`), `patch_outside`, `patch_too_large` (`{{km}}`, `{{max}}`), `patch_crs`,
`patch_no_data`, `patch_relief`, `patch_damaged`, `rate_patch`. The page renders them with `viewer/src/i18n.ts`
`t`; server errors come as `{message, code, params}` (`api.ts` `ApiError`).

## Budgets
- Per open: about 1–1.5 MB of heights at 1.5 km and 1 m (desktop), a quarter at step 2; all data ≤ ~4 MB desktop,
  ≤ ~1.5 MB phone.
- Phone: ≤ 130k vertices, ≤ 18 MB of textures, `devicePixelRatio` ≤ 2; desktop: ≤ 300k vertices, ≤ 60 MB.
- Code: `view3d.js` about 0.2 MB gzip (three.js and martini; 3DTilesRendererJS joins in wave 3).

## After wave 1 (2026-11-02)
- **Versions** (each at least two weeks old): `three` 0.186.1, `@types/three` 0.186.0, `three-mesh-bvh` 0.9.16,
  `3d-tiles-renderer` 0.5.3 (its optional React/Babylon peers not installed); martini vendored in
  `viewer/src/view3d/martini.ts`, its licence through `viewer/licences/martini.txt`.
- **Server:** `search.patch_of_line` (+ `encode_heights`), `mapping.ortho_entry` (factored out of `save_map`),
  `jobs.quick_patch` with `Redact.RAW = {"heights"}`, `web.patch_body`, `PAGE_CSP` chosen per path in `guard`,
  `/view3d` in `PUBLIC_ROUTES` treating visitors as `/`. Codes: `patch_line` also stands for a run without an area
  box and for a line longer than the run's longest line; a `step` other than 1 or 2 is a plain 400.
- **`ortho.cache`** is set whenever the source has an orthophoto (run.json does not record `--ortho`), so a run made
  with `--ortho never` answers 404 from `/cache/`. 404s are harmless for fail2ban (it counts 401, 403 and 429, and
  ignores 429 of `/cache/`), but avoid them where the cache cannot have tiles: zoom ≤ 16 cache first; zoom 17 over
  the patch straight from the service; zoom 19 in the corridor of ±60 m along the line cache first (the run caches
  zoom 17–21 only 30 m around its best groups).
- **Affine:** a plane over the projection: about 2 cm at the corners of 513 m, 17 cm at 1.5 km, growing with the side
  squared; fine for texture UVs, the found line's anchors come exact from `anchors`.
- **Page (V1):** `main.ts`, `page.ts`, `decode.ts`, `terrain.ts`, `view.ts`, `geometry.ts`, `martini.ts`,
  `view3d.css`; Martini's error 0.5 m desktop, 1.5 m phone (to tune within the budgets); only chunk (0, 0) drawn
  so far, no skirts, no forced vertices, `meta.sha256` not checked in the browser yet (wave 2). On a level line
  the envelope has two equal maxima: either is the walker's start.

## Wave 2
Two agents in parallel on the page; the shared types are in `viewer/src/view3d/scene-api.ts` (`Scene3D`, `Chunk`,
`Credits`) and the imagery's entry point in `viewer/src/view3d/imagery.ts` (`createImagery`, a stub with the final
signature): change neither signature without the coordinator.

| Agent | Owns |
| --- | --- |
| V2a scene core | `main.ts`, `view.ts`, `terrain.ts`, `page.ts`, `geometry.ts`, `view3d.css`, new `scene.ts` (implements `Scene3D`), new modules for the webbing and the walker, the Node tests it adds to `tests/test_viewer.py`, new `tests/test_view3d.py` (Edge) |
| V2b imagery | `imagery.ts` (replaces the stub), new `tiles.ts` (tile URLs, coverage, UVs) and `credits.ts` (the credits' HTML), pure helpers split out of `viewer/src/layers.ts` if needed (`PROCESSED_NOTE` stays defined in `layers.ts`, a test reads it there), new `tests/test_view3d_tiles.py` (Node tests through `test_viewer.run_ts`) |

Both rebuild `viewer/dist`; at the merge the coordinator rebuilds it again.

**V2a, the scene core**
- `scene.ts` builds every chunk (padded grid, one shared `Martini(513)`), skirts along chunk edges, the anchors' and
  the line's footprint samples forced into the mesh (their errors `Infinity` before `getMesh`; the footprint: every
  sample the straight line between the anchors crosses), no triangles over no data. Martini's error within the
  budgets (desktop ≤ 300k vertices, phone ≤ 130k): start at 0.25 m desktop, 1.5 m phone.
- Each chunk's material takes a texture through `Chunk.setTexture(texture, uv)`: UVs from each vertex's grid metres.
  Without one: shaded terrain (the 2D map's terrain colour `--terrain`, lit from the north-west).
- Drawing on demand only (`invalidate`, `onFrame`, `keepDrawing`), `devicePixelRatio` ≤ 2, `webglcontextlost`
  handled (`ui.view3d.context_lost`, Reload), everything disposed on `pagehide`.
- After the patch, `/api/profile` for the found line (header `X-Findaline-Profile: 1`, as `result/model.ts`
  `fetchProfile`, one request at a time): the webbing in the 2D map's colours (`--clear`, `--trees` of
  `viewer/src/ui/tokens.css`), the readout (`ui.view3d.length`, `.sag`, `.clearance`, `.over_trees`); until it
  answers, a neutral colour and `ui.view3d.loading_profile`.
- The webbing: `Line2` (`three/examples/jsm/lines`) whose 61 points are written in place (no new buffer per change),
  the loaded curve with the walker at s (`geometry.ts` `loadedAt`), the unloaded one faint.
- The walker: a 1.7 m mannequin of three.js primitives standing on the webbing at s, facing along the line; it
  starts at the envelope's largest sag; a slider (`ui.view3d.walker_position`) in `scene.toolbar` moves it. The
  walk itself and dragging come in wave 3.
- The camera: an oblique view across the line framing it, orbit/pan/zoom (`OrbitControls` or `MapControls`),
  never below the horizon.
- Calls `createImagery(scene, {runId, esriKey})` once the terrain is drawn; `esriKey` from
  `<meta name="findaline-esri-key">` or null. Shows `ui.view3d.preview_note` in the page.
- Phone level: step 2 (already in `page.ts`), the coarser error, no anchor dragging later.
- Tests: Node tests of the pure parts (chunks, skirts, forced vertices, the walker's placement); `tests/test_view3d.py`:
  the local app with a run of the clip (the fixtures of `tests/test_patch.py`), `/view3d#run=…&line=…` in headless
  Edge (`--disable-gpu`), a ready marker set by the page, triangles drawn, no CSP violation (the `CSP_STUB` way of
  `tests/test_web.py`), the readout filled from `/api/profile`.

**V2b, the imagery**
- `createImagery`: the kinds available (`ortho` when `meta.ortho`, `esri` when a key, `shaded` always; default the
  first), a segmented control (`ui.view3d.imagery`, `.imagery_ortho`, `.imagery_esri`, `.imagery_shaded`) in
  `scene.toolbar`, `ui.view3d.no_imagery` when only `shaded`; switching re-textures every chunk.
- Textures per chunk: chunks with `hasLine` at the zoom whose tiles fit 2048 px (zoom 19 at 1 m data, else lower),
  the others at zoom 17; on phones zoom 17 everywhere; one canvas per chunk, ≤ 2048 px, ≤ 60 MB of textures on the
  desktop, ≤ 18 MB on phones. `crossOrigin = "anonymous"` set before `src`; a tile failing CORS is retried once with
  a cache-busting query parameter (responses the 2D map cached without `Vary: Origin`).
- Orthophoto tiles as the 2D map asks for them (`viewer/src/layers.ts` `createCachedTile`, `CachedTiles`,
  `CachedWMS`; `result/load.ts` `orthoForApp` resolves `meta.ortho.cache` for the run): our cache
  `<cache>/{z}/{x}/{y}.jpg` first for chunks with the line (zoom 19), the service straight for zoom 17; base tiles
  `{z}/{x}/{y}` with the WMS (1.3.0, EPSG:4326, `bbox=south,west,north,east`) drawn over them where both exist.
- Esri: `https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=<key>`,
  native zoom ≤ 19 (as `layers.ts`).
- Credits through `scene.credits`: the run's data credits (`meta.attribution`, as `layers.ts` `creditsHtml` shows
  them on the 2D map, without importing Leaflet into `view3d.js`), the orthophoto's attribution (and its link), for
  Esri "Powered by Esri" and its source line (`layers.ts` `ESRI_NAME`, `ESRI_SOURCE`).
- Tests: Node tests of the pure parts (which tiles cover a chunk at a zoom, their URLs for cache, WMS, base and Esri,
  the UVs, the zoom choice within 2048 px, the credits' HTML).

**At the merge (coordinator):** `tools/ui_shots.py` pages of `/view3d` (a `{line}` placeholder, `?level=`), the
visual review on the desktop and both phones, and the privacy/About wording proposals for the user.

## After wave 2 (2026-11-02)
- **Scene core (V2a):** `scene.ts` (`createScene` → `SceneCore`, which implements `Scene3D`), `terrain.ts` (every
  chunk from one `Martini(513)`, skirts, forced samples: the anchors, the line's footprint and the edges of no data;
  the error raised ×1.5 until the vertices fit the budget, the page's `data-max-error`), `view.ts`, `line.ts` (the
  readout), `webbing.ts` (`Line2`, 61 points written in place), `walker.ts` (the mannequin), `main.ts` (the body's
  sha256 checked; `/api/profile` after the patch; `createImagery` after the first frame).
- **`onFrame(fn)`:** `fn(seconds)` gets the seconds since the previous frame drawn (0 on the first) and runs only
  while some owner keeps drawing: an animation calls `keepDrawing(owner, true)` while it runs and `false` after.
- **Imagery (V2b):** `imagery.ts`, `tiles.ts` (the tiles of a chunk at a zoom, their URLs, the UVs,
  `planTextures`), `credits.ts`. `viewer/src/layers.ts` has no Leaflet any more (the credits' HTML, `esriKey`,
  `ESRI_*`, `esriTileUrl`, `PROCESSED_NOTE`); the base layers moved to `viewer/src/baselayers.ts`, imported by the
  2D map's modules. The line's chunks take zoom 18 at 50° N (zoom 19 does not fit 2048 px). `view3d.js` holds no
  Leaflet: 695 KB, 185 KB gzip.
- **At the merge:** `main.ts` takes `esriKey` from `layers.ts`; `lookAcross` (scene.ts) also fits the line into
  the view's width (on a Pixel 7 held upright both anchors were cut off); `tools/ui_shots.py` pages `d-line`,
  `view3d`, `view3d-shaded`, `view3d-phone`, `view3d-full` (a `wait:` step, the `{line}` placeholder). WebGL works in
  Playwright on Windows, WebKit too.
- **Visual review, for wave 3:** the walker is hard to find at the framing distance (about 6 px tall at 190 m;
  invisible on phones); on phones the bar below the canvas takes about 40 % of the screen (the readout on two
  lines, the slider, the imagery control and two notes on rows of their own); the sky is the page's flat
  background. Decisions on these: the user's, at the wave-2 checkpoint.

## How to work
- Python: the main checkout's venv, `C:\Users\Krzysiek\Documents\Prywata\Find-a-Line\.venv\Scripts\python.exe`, run
  from your worktree (no editable install; `uv.lock` unchanged). Node: `npm ci` in your worktree's `viewer`, then
  `node node_modules/typescript/bin/tsc --noEmit` and `node build.mjs`.
- Tests, builds and searches under the test lock, from your worktree:
  `"C:\Users\Krzysiek\Documents\Prywata\Find-a-Line\.venv\Scripts\python.exe" "C:\Users\Krzysiek\Documents\Prywata\Find-a-Line\tools\test_lock.py" run --owner <your branch> --timeout 1800 -- <command>`.
  Anything that starts Edge (most of `tests/test_web.py`, `tests/test_public.py`, the shell tests) from PowerShell:
  headless Edge prints nothing from Git Bash. Stop only test browsers (by their `--user-data-dir`).
- Commits: English, the repository's style, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  stored-data decisions stated (none expected). Never push, never touch `main`, never merge: the coordinator does.
  `viewer/dist` is always rebuilt, never edited by hand.
- Report at the end (at most ~400 words): what was built, the files, the tests run with their results, deviations
  from this contract and open questions. Stop and report instead of deciding anything outside this contract.
