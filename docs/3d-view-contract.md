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
| V1 viewer | `viewer/package.json` and its lock, `viewer/build.mjs`, new `viewer/licences/`, new `viewer/src/view3d/`, the button in `viewer/src/result/view/ResultWorkspace.tsx`, `LineDetails.tsx` and `viewer/src/app/d/AppD.tsx` (the first and the last removed with interface D on 2026-11-04: C's `ResultPage` gives `LineDetails` the button), `viewer/dist` (rebuilt), the Node tests in `tests/test_viewer.py` |

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
  does, the run's surface model only for the shore faces the terrain lacks (`sources.filling.fill_shore_from_surface`), no obstacle surface; a square polygon (`SearchParams(geometry=...)`) centred on the line's middle, its corners
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
- **The uncertain shore** (since 2026-11-05, runs with water filling): after the heights the body carries the kinds of the
  patch's samples (`sources.filling.shore_rows`: 0 none, 1 the face from the surface model, 2 the sea fill standing in
  for a cliff's foot), one byte a sample row-major from the top, deflated (zlib) by `search.encode_shore`; the meta's
  `shore_bytes` is their length (the heights are the body less them) and `shore_sha256` their sha256; the meta's
  `sha256` stays that of the heights alone. Without water filling neither field is set and the body is the heights.
  The page (`decode.ts` `decodePatch`) keeps them as `Patch.shore` when any is set and hatches them (`view3d/shore.ts`).

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
  background (kept).

## Decisions at the wave-2 checkpoint (2026-11-02, the user's)
The approved texts go in word for word (English, as below); nothing else on these pages changes.
- **Privacy page** (`web.privacy_page`, the bullet of the facts on public services): its last sentence becomes
  "Maps in your browser and the 3D view of a line load background tiles and imagery (OpenStreetMap, OpenTopoMap,
  Esri, orthophoto services) directly: those services see your IP address. The 3D view's terrain comes from this
  site; it is computed for the view and not stored."
- **About page, Esri** (`web.esri_terms`; its first sentence stays): "By using the satellite imagery (in the map or
  in the 3D view of a line) you agree to comply with Esri's terms of use for it (<the link as now>). In particular,
  it may only be viewed in this map and in the 3D view of a line: it may not be downloaded, stored, copied or
  passed on."
- **About page, Software:** "The maps, the app and the 3D view include open-source libraries (Leaflet, Preact,
  i18next, three.js and others); their licences and copyright notices: <the link as now>."
- **Mapterhorn, only while `FINDALINE_3D_RING` is on** (otherwise the pages stay as they are):
  - privacy page, a fact after the one above: "When the 3D view shows the terrain around its patch, your browser
    loads it from Mapterhorn (tiles.mapterhorn.com), which logs each request with its IP address, referrer and
    browser for up to 30 days."
  - about page: "Terrain around the 3D view: © Mapterhorn (mapterhorn.com/attribution), from open elevation data
    under the licences of its sources." ("mapterhorn.com/attribution" links to https://mapterhorn.com/attribution);
  - the 3D view's credits: "© Mapterhorn" linking to https://mapterhorn.com/attribution (their TileJSON's
    attribution).
  - Their privacy policy (https://mapterhorn.com/privacy-policy/, updated 2026-07-07, read 2026-11-02) logs the
    source IP, referrer, user agent and more for up to 30 days; no usage policy or limit is published.
- **The walker:** always at true scale; when it is smaller than about 20 px on the screen, a contrasting marker
  (a pin) shows above it, gone again when the camera comes closer.
- **The phone bar** (the coordinator's default, not objected to): the readout on one line, the walker's slider and
  the imagery control in one row, the notes in small type.

## Wave 3
Three agents in parallel (the plan's V3b split in two, so that no file has two owners), each in its own worktree
`.claude/worktrees/<branch>` on a branch from `line-3d-view`:

| Agent | Branch | Owns |
| --- | --- | --- |
| V3a scene interaction | `l3d-w3-scene` | `viewer/src/view3d/` `main.ts`, `view.ts`, `scene.ts`, `terrain.ts`, `page.ts`, `geometry.ts`, `line.ts`, `webbing.ts`, `walker.ts`, `view3d.css`, new modules of its own (e.g. `edit.ts`, `walk.ts`, `pin.ts`); new `ui.view3d.*` texts in `locales/en.json` if one is missing (none expected: wave 0 wrote them); its Node tests in `tests/test_viewer.py`; `tests/test_view3d.py` |
| V3b ring (viewer) | `l3d-w3-ring` | `viewer/src/view3d/` `ring.ts` (replaces the stub), `imagery.ts`, `tiles.ts`, `credits.ts`, new modules of the ring; `tests/test_view3d_tiles.py`, new `tests/test_view3d_ring.py`, test data it makes under `tests/data/` |
| V3c server and texts | `l3d-w3-server` | `settings.py` (`ViewSettings`), `web.py`, `README.md`, `findaline.env.example`, the 3D page's and the pages' rows in `tests/test_public.py`, `tests/test_web.py`, `tests/test_units.py` |

The coordinator's only: `viewer/src/view3d/scene-api.ts`, `docs/`, `CLAUDE.md`, `package.json` and its lock (no new
dependency: `three-mesh-bvh` 0.9.16 and `3d-tiles-renderer` 0.5.3 are pinned already; a need for another: report).
Every agent rebuilds `viewer/dist`; at the merge the coordinator rebuilds it again. `tests/test_view3d.py` keeps
`READY_SCRIPT` and `_page(data, run_id)` as they are (V3b's test imports them); add new helpers beside them.

**In the base already (the coordinator, for all three):** `Scene3D.beforeDraw(fn)` (before every frame drawn, on
demand or not), `Scene3D.camera` and `Scene3D.renderer` (read-only for the modules); `ring.ts` a stub with the
final signature (`ringUrl()`, `createRing(scene, imagery, url)`, `Ring.dispose()`), called by `main.ts` after the
imagery when `ringUrl()` gives a URL, disposed on `pagehide`.

**Names shared by the three**
- The meta `findaline-3d-ring` of `web.VIEW3D_HTML`: `off`, or the ring's tile URL template with `{z}`, `{x}` and
  `{y}` (HTML-escaped by the server); `ring.ts` `ringUrl()` reads it.
- `settings.ViewSettings` (pydantic-settings, the environment only, no Docker secret, `extra="ignore"`):
  `ring: bool = False` from `FINDALINE_3D_RING`; `ring_url: str = "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"`
  from `FINDALINE_3D_RING_URL` (https; http only to 127.0.0.1 or localhost; holding `{z}`, `{x}` and `{y}`);
  `ViewSettings.load()`, read once by `web.create_app`.
- The 3D page's Content-Security-Policy: with the ring off as every page's (SECURITY_HEADERS'); with it on,
  `connect-src` adds the ring URL's origin, `https://ibasemaps-api.arcgis.com` and the origins of every orthophoto
  service of the catalogue (`OrthoService.url` and `.base_url` of `sources.SOURCES`). Nothing else is added: a need
  for `blob:`, `worker-src`, `wasm-unsafe-eval` or more is reported, not added.
- The ring's credit in `scene.credits`: id `"ring"`, order 3 (the data credits are 1, the imagery's 2), the HTML
  `<a href="https://mapterhorn.com/attribution">© Mapterhorn</a>` built from constants (approved).
- `Imagery.onChange(fn: (kind: ImageryKind) => void): () => void` (V3b adds it to `imagery.ts`; V3a does not use it).
- No request to `tiles.mapterhorn.com` or to Mapterhorn's downloads while building: the maintainer has not been
  asked yet (draft 7 of the user's mails). Tests make their own Terrarium tiles. Esri's and the orthophotos'
  services are not asked by tests either (the visual review is the coordinator's).

**V3a, scene interaction**
- Anchor editing at level `full` only: a handle at each anchor; dragged with the pointer over the terrain (a
  raycast on `pickTargets` with `three-mesh-bvh`'s `acceleratedRaycast`/`computeBoundsTree`), the orbit controls off
  while dragging; the anchor's height from `heightAt`, never off the patch (over no data it stays where it was). The
  webbing re-solved on every move with the code of the found line (`geometry.ts`, `webbing.ts`); while edited the
  readout shows `ui.view3d.edited` and the webbing a neutral colour. On release, after 300 ms without another
  release, `/api/profile?run=…&line=<lat1>,<lon1>,<lat2>,<lon2>` for the new anchors (through `scene.lonLat`; the
  header `X-Findaline-Profile: 1` as `fetchProfile` of `main.ts`; at most one request in flight: releases during
  it wait and only the newest is sent), then `setProfile` (colour and readout as for the found line); an error
  answer (e.g. 429) shows its message (`detailMessage`) and the line stays neutral. `ui.view3d.reset` ("Back to
  the found line") brings back the found anchors and their profile, kept from the start (not asked again);
  `ui.view3d.edit_hint` says how. Nothing is saved.
- The walker: dragged along the line at level `full` (from the pointer to the nearest point of the span); the slider
  on both levels. The walk: a `ui.view3d.walk` / `ui.view3d.stop` button, from the walker's place towards the second
  anchor at 1 m/s along the span, `ui.view3d.speed` switching ×1/×4 (`ui.view3d.speed_value`), stopping at the
  end; Walk at the end starts again from the first anchor. `keepDrawing("walk", …)` only while it walks, `onFrame`
  seconds advance it. Under `prefers-reduced-motion: reduce` no walk: `ui.view3d.reduced_motion` instead; the slider
  stays.
- The pin (approved): the walker always at true scale; while its height on the screen is under 20 CSS px a
  contrasting pin shows above it (a sprite with `sizeAttenuation: false`, or a DOM marker moved each frame drawn:
  no style attributes, the CSSOM only), gone when it is larger; readable over imagery, shaded terrain, light and
  dark.
- The phone bar (approved): at level `phone` and on narrow screens the readout on one line, the slider and the
  imagery control (the `.u-row` V3b keeps in `scene.toolbar`) in one row, the notes in small type; the canvas gets
  the rest.
- Tests: Node tests of the pure parts (the walk's stepping, a pointer's place along the span, the request queue);
  `tests/test_view3d.py`: level `full` has the handles and the walk button, level `phone` neither handle; the pin's
  state at the first framing as a data attribute of the root (e.g. `data-pin="1"`); no CSP violation; an edit by
  synthetic pointer events if they work in headless Edge, else its logic in Node.

**V3b, the ring (viewer)**
- `createRing(scene, imagery, url)`: a `TilesRenderer` of `3d-tiles-renderer` 0.5.3 over the Terrarium tiles at
  `url` (Mapterhorn: Terrarium-encoded WebP of 512 px in Web Mercator, z0–17) through the package's plugin for such
  elevation tiles (look in the installed package's exports and docs; report which), updated only when the camera
  changes (`UpdateOnChangePlugin` or the like) with `tiles.update()` in `scene.beforeDraw`, `keepDrawing("ring",
  true)` while tiles load, `invalidate()` per tile loaded.
- Extent and budget: about 6 km from the patch's centre at level `full`, 3 km at `phone`; coarse levels only; at
  most ~1.5 MB of tiles per open on the desktop and ~0.6 MB on a phone (Terrain and imagery together; measured in the
  Edge test from `PerformanceResourceTiming.transferSize` or the plugin's events; report the numbers).
- Placement: from the tiles' frame into the scene's (`toScene`: origin at the patch's centre, X east, Y up, Z
  south) through `meta.affine` and `geometry.ts` (`mercator`, `lonLat`); heights as the tiles give them (report the
  offset to the patch's heights along its edge, median and p90, on the test tiles and from the code's reasoning for
  Mapterhorn's datums).
- Cut out under the patch: no ring triangle over the patch's rectangle (clipping planes with `clipIntersection` and
  `renderer.localClippingEnabled`, or a discard in the shader); the patch's skirts hide the seam.
- Imagery: the ring's overlay follows `imagery.current` and `onChange`: Esri through the package's XYZ overlay
  (`layers.ts` `esriTileUrl`, zoom ≤ `ESRI_MAX_ZOOM`), the orthophoto through its base tiles (`{z}/{x}/{y}` in Web
  Mercator) or its WMS where the package has a WMS overlay, shaded without one (the ring's material in `--terrain`
  as the patch's). Our cache is not used for the ring.
- Credits: `"ring"` as in "Names", set when the ring is created, removed by `dispose`.
- `Ring.dispose()`: the tiles disposed, listeners and the credit removed.
- Tests: Node tests of the pure parts (the placement, the cut-out, the overlay's URLs per imagery);
  `tests/test_view3d_ring.py`: `test_view3d`'s page with the meta set to a same-origin template of a few Terrarium
  tiles the test makes from the clip (PNG or WebP through Pillow, served from the run's folder), the ring drawn
  (a data attribute of the root, e.g. `data-ring="loaded"`), its bytes within the budget, no CSP violation.
- Report the bundle's size (`view3d.js` gzip): above ~0.35 MB the coordinator decides about a bundle of its own.

**V3c, server and texts**
- `settings.ViewSettings` as in "Names", with the README's rows of the settings.
- `web.create_app` reads it once: `/view3d` gets `html.escape(ring_url)` or `off` in its meta; the 3D page's CSP from
  the ring's state (built in `create_app` and used by `guard`; the module's `PAGE_CSP` may stay as the ring-off
  default), the catalogue's orthophoto origins computed from `sources.SOURCES`.
- The approved texts word for word ("Decisions at the wave-2 checkpoint"): the privacy fact and the about page's
  Esri and Software sentences always; the Mapterhorn fact and line only while the ring is on (`privacy_page(...,
  ring=)`, `about_page(..., ring=)`).
- README: a section on the 3D view of a line (what it shows, the levels and `?level=`, the data per open, the
  imagery, `FINDALINE_3D_RING`/`_URL`: off until Mapterhorn's maintainer agrees) and one on the local app's satellite
  imagery with the user's own ArcGIS Location Platform key in `ESRI_API_KEY` (read what README says today first).
- `findaline.env.example`: `FINDALINE_3D_RING` commented out, with one line on why it is off.
- Tests: the meta off and on, the 3D page's CSP off (= SECURITY_HEADERS') and on (the origins), the origins equal to
  the catalogue's, the privacy and about texts with the ring off and on, `ViewSettings`' checks; `/` and `/api/jobs`
  keep their headers.

## After wave 3 (2026-11-02)
- **V3a** (`edit.ts`, `walk.ts`, `pin.ts`, `interact.ts` pure and Node-tested, `screen.ts` the overlay): handles on
  a DOM overlay over the canvas, the pin and the walker's grip there too; `SceneCore.stage`, `View.setControls`;
  the root's `data-edit`, `data-walk`, `data-pin`, the readout's `data-verdict`, `data-colour` for tests. A line's
  verdict (`webbing.ts` `verdictOf`): `fits` (`--clear`), `terrain_only` (`--trees`), `no_fit` (`--bad`, the new
  text `ui.view3d.does_not_fit`: a moved anchor can give a negative clearance).
- **V3b** (`ring.ts`, `ringmath.ts`, `tiles-plugins.d.ts`): `TerrariumMeshPlugin` from `3d-tiles-renderer/three/plugins`
  (its types leave it out), a level of detail of our own by the distance from the patch's centre (the same tiles
  wherever one looks: `RING` in ringmath.ts, 6 km at zoom 12 on the desktop, 3 km at zoom 10 on phones),
  `ImageOverlayPlugin` with `XYZTilesOverlay`/`WMSTilesOverlay`, clipping planes over the patch's data rectangle,
  `Imagery.onChange`; the root's `data-ring`, `data-ring-tiles`, `data-ring-offset`. **Depends on 0.5.3's
  internals:** `RingTerrain` clamps the plugin's private `_maxSourceLevel`; check it on an upgrade. On the test
  tiles (from the clip): 8 terrain tiles 132 KB and 36 imagery tiles 27 KB on the desktop, the edge's offset
  0.21 m median, 0.95 m p90 (phones 1.2 / 5.5 m). Mapterhorn's own sizes are unknown: at more than ~165 KB a WebP
  tile the desktop's 9 tiles pass 1.5 MB (the knob: `RING`); about 100k vertices more on the desktop.
- **V3c**: `settings.ViewSettings` (`ring_origin`), `create_app(view=)`, `web.page_csp`, `web.ortho_origins`
  (13 origins today, pinned in `tests/test_public.py::RING_ORIGINS`), `ESRI_TILES_ORIGIN`,
  `MAPTERHORN_ATTRIBUTION`; the approved texts in; README's two sections; `docs/deployment.md` section 8 (the
  coordinator's line). The Mapterhorn texts assume the default `FINDALINE_3D_RING_URL`: another server needs its own
  approved texts.
- **At the merge:** the loaded webbing drawn once more through the terrain, faint (a slope hid the last ~11 m at
  the second anchor, whose handle the overlay draws above the canvas); `preserveDrawingBuffer` (Playwright's WebKit
  showed the frame before the last until another was drawn: the webbing grey after its profile, 2 opens in 4);
  `ui_shots`' `wait:` step as a function (an expression needs eval: the CSP). `view3d.js` 979 KB, 270 KB gzip.
  Full pytest 634 passed (3 skipped: platform), the 3D tests 40 passed after the fixes.
- **For wave 4:** the phone bar at 390 px: the readout's one line scrolls (cut after "clear of the ter…") and the
  imagery control touches the right edge; the iPhone test of the walk's smoothness with `preserveDrawingBuffer`;
  the ring's bytes with Mapterhorn's tiles once its maintainer agrees; CLAUDE.md (code map: view3d's modules, the
  patch endpoint, `ViewSettings`; sync rules: the body's encoder and decoder, the page's CSP and the catalogue's
  orthophoto origins, `RING_ORIGINS`, the Mapterhorn texts behind the switch, the 0.5.3 internals of the ring).

## Wave E: the "Edges" look (2026-11-02, the user's decisions)
A fourth kind of imagery, `edges` (`ui.view3d.imagery_edges` = "Edges"), after `shaded` in the control; the default
stays the first available kind. The look is the prototype's variant M (branch `l3d-edges-proto`, deleted after wave E: its
`viewer/src/view3d/edges.ts` and its changes of `view.ts` and `scene.ts` are the reference; the renders:
https://claude.ai/artifact/G9VFV9yjC3mNNZ4ojWAE5z):
- the terrain on paper: light grey `#eceae4` in the light theme, dark grey `#4a504c` in the dark one (a `--paper`
  token of the page), lit as `shaded`;
- bold lines from a screen-space pass (silhouettes: the distance from the camera jumps, relative 0.012–0.035;
  creases: the normals differ, 1 − dot 0.10–0.28; creases at 0.75 strength) in `--ink` (dark on light, light on dark),
  over the terrain alone (a layer of the chunks; the webbing, walker and overlay never make edges);
- thin feature edges of the mesh (`EdgesGeometry`, faces turning by more than 28°) in `--muted`, made when the look is
  first chosen and hidden in the other kinds;
- the ring (when on) takes the same look: its tiles on the terrain's layer, on paper, without an overlay.
One agent (VE) on `l3d-wE-edges`; it owns, for this wave: `edges.ts` (new), `view.ts`, `scene.ts`, `scene-api.ts`
(add what the imagery and the ring need, e.g. `setEdges(on)`, the terrain's layer, the paper's colour), `imagery.ts`,
`ring.ts`, `ringmath.ts`, `view3d.css` (the `--paper` token only), `locales/en.json` (`ui.view3d.imagery_edges`), one
sentence in README's "The 3D view of a line", the pages `view3d-edges` (and its dark and phone screenshots come from
`--dark` and the devices) in `tools/ui_shots.py`, the Edges tests in `tests/test_view3d.py` and
`tests/test_view3d_ring.py`, Node tests of pure parts in `tests/test_viewer.py`. Not `main.ts`, `line.ts`,
`walk.ts`, `edit.ts`, `pin.ts`, `screen.ts` (wave 4). Lines one CSS pixel wide at every pixel ratio (the pass samples
at `devicePixelRatio` texels, at most 2); the colour target multisampled at level `full` only; drawn on demand only
(one more render of the terrain and one full-screen pass a frame while Edges is on); disposed, resized and freed on
context loss with the rest. Tests: switching to Edges draws (the root's `data-imagery="edges"`), only on demand, no
CSP violation, back to Shaded removes the pass; the ring's Edge test once with Edges.

## Wave 4 (2026-11-02, started without a stop after wave E: the user's word)
- **V4b, the device test page** (in parallel with wave E; branch `l3d-w4-device`): `tools/device_page.py` with a test
  `tests/test_device_page.py`. `record`: from a scratch data folder with runs (R2 Dolina Bolechowicka and R19
  Lauterbrunnen of `tests/regression.json`, searched there by the agent), the answers of `/api/patch` (steps 1 and 2)
  and `/api/profile` for a few lines of each run, taken from the local app in-process (as the tests do), saved with
  their headers. `serve`: HTTPS on `0.0.0.0` (a self-signed certificate whose SANs hold the PC's LAN addresses, made
  per start, as `tools/ui_shots.py` makes its own), the 3D page as `web.VIEW3D_HTML` gives it with the app's headers
  and CSP (`web.SECURITY_HEADERS`, the page's own), `/app/view3d.js|css` from `viewer/dist`, the recorded answers by
  run, line and step (anything else 404), `/cache/` read-only from the data folder, an index page of the recorded
  lines with links for both levels; `ESRI_API_KEY` put into the page when set (never into a file); GET only, no
  accounts, nothing else of the app. A checklist for the user's iPhone in its docstring (and printed at start): the
  certificate warning, Windows' firewall prompt, open/orbit/zoom, the walker's slider and the walk, both levels,
  imagery kinds incl. Edges once wave E is in, five minutes without a reload, rotate the phone. It also reports the
  data per open of each recorded line: the patch's bytes per step, the profile's, and the imagery's tiles counted
  by `tiles.ts`' plan with their bytes (cached tiles measured, service tiles sampled): R2 and R19, desktop and phone.
  It owns only those two files (and `.gitignore` if it needs a line); it changes nothing of the app or the viewer.
- **V4a, the phone bar** (after wave E, so with four kinds of imagery): at 390 px the readout fits (shorter readout
  on narrow screens or two lines, never a hidden scroll), the imagery control fits (four kinds: e.g. a native select
  under 600 px), "No imagery" and the notes never overlap the buttons; owns `main.ts`, `line.ts`, `walk.ts`,
  `view3d.css` and the imagery control's markup in `imagery.ts`.
- **The coordinator**: the data per open at R2 and R19 (from V4b's tool), the Edges thresholds on those real patches,
  the visual review, CLAUDE.md (code map, sync rules), `docs/3d-view.md`'s status, full checks, the report.
- **Measured (V4b's `measure`, 2026-11-02)**: R2 took 13.3 MB of imagery a desktop open (5.8 MB a phone open):
  geoportal.gov.pl's HighResolution WMS as a transparent PNG (~83 KB a tile) over every WMTS base tile (~5 KB).
  A WMS limited to the line's corridor (4b3da63) gave 1.6 MB but a patchwork of two flights (the base's darker,
  blurrier imagery around the corridor's): rejected. The same WMS tile as JPEG is ~11 KB (zooms 16-18 at R2).
- **V4c, the orthophoto as the 2D map's cache composes it** (in parallel with V4a; branch `l3d-w4-ortho`): for a
  service with a WMS and base tiles, each tile mirrors `orthophoto.tile_content`: the WMS as JPEG first; all white
  (no imagery there) → the base tile; any white 8×8 block (the coverage's edge) → the transparent PNG over the base;
  else the JPEG alone. The browser's white test (a pure function over the decoded pixels, a small tolerance for
  decoders) matches `orthophoto._white_blocks` on the same pixels; the WMS everywhere again (the corridor rule out);
  a WMS without base tiles as now; our cache first as now. Owns `tiles.ts`, the tile drawing of `imagery.ts`
  (`compose`, the loader; not the control's markup, which is V4a's), `tests/test_view3d_tiles.py`, the imagery
  estimate of `tools/device_page.py measure` (JPEG sizes sampled; base and PNG counted for the white shares) and its
  test. Measure R2 and R19 again; screenshots of R2's orthophoto for a uniform look.

## After wave E and wave 4 (2026-11-02)
- **E (VE)**: `edges.ts` (the pass; thresholds as the prototype's constants; `featureEdges` of our own instead of
  `EdgesGeometry`, which drew the outline and the skirts along chunk seams; the normals from `MeshNormalMaterial`
  per source material, so the ring's displaced and clipped tiles take part; a half-float colour target against
  banding on dark paper: the look needs `EXT_color_buffer_float` or `_half_float` and is offered only then);
  `Scene3D.edgesSupported`, `setEdges`, `edgesOn`, `terrainLayer`, `paper`; the root's `data-edges`,
  `data-imagery`. On real patches: R2's rocks read well; R19's 2 m walls take dense hatching from the mesh's
  feature edges (28°): a higher angle is the knob if wanted.
- **4b (V4b)**: `tools/device_page.py` (`record`, `serve`, `measure`), its test; the recordings of R2 and R19 in the
  coordinator's scratch folder.
- **4c (V4c)**: the orthophoto composed as `orthophoto.tile_content` composes the 2D map's cache (JPEG first,
  `whiteBlocks` with `WHITE_MIN` 250; the corridor rule of 4b3da63 reverted); data of an open (`measure`): R2 2.5-2.6
  MB desktop, 1.2 MB phone (imagery 1.7 / 0.9 MB, was 13.3 / 5.8); R19 3.1-3.2 MB and 0.75-0.85 MB. No white or edge
  tile turned up in R2's samples: the base and PNG path is checked by tests only.
- **4a (V4a)**: under 600 px a short readout (`ui.view3d.*_short`), the imagery as a native select (`.v3-select`),
  notes on lines of their own, narrower buttons; the data credits fold behind the 2D map's "Data credits" toggle
  below ui.css's 767 px (the imagery's and the ring's never fold); `tools/ui_shots.py` writes the clip's credits
  into its run.json too.
- **Open after wave 4**: the user's iPhone test (`tools/device_page.py serve` and its checklist: the walk's
  smoothness with `preserveDrawingBuffer`, Edges on a phone's GPU); Mapterhorn's answer and then the ring's bytes;
  the 2D map's Edges (roadmap). When the user ends the idea: the tag `history/line-3d-view` and one squash commit
  into `main` (CLAUDE.md, conventions).

## Wave F: the walker's view (2026-11-02, the user's decisions)
Two camera views besides the orbit one, chosen with a switch in the bar (`ui.view3d.view_orbit` "Orbit",
`view_eyes` "Walker's eyes", `view_behind` "Behind the walker"; the orbit stays the default and the only view
where anchors are dragged):
- **Eyes**: the camera at the walker's eyes (its feet on the loaded webbing + 1.6 m), looking along the line
  towards anchor 2 and a little down at first; the mannequin, its pin and grip hidden; a wider field of view
  (about 70°). **Behind**: the camera a few metres behind and above the walker, the mannequin in view, looking
  ahead along the line. Both follow the walker: the slider, dragging it in the orbit view and the walk (the
  webbing's sag moves the camera, as walking would); leaving either view gives back the orbit camera as it was.
- **Looking around by dragging** (mouse or finger) in both views: yaw and pitch of the gaze (eyes) or of the
  camera around the walker (behind), the orbit controls off meanwhile; the pitch clamped (never upside down).
- **Phone motion** on top (the user's choice; tested later on the user's iPhone): a button (`ui.view3d.motion`
  "Phone motion") shown where `DeviceOrientationEvent` exists; iOS asks for permission
  (`DeviceOrientationEvent.requestPermission()`) inside the button's click; turning the phone turns the gaze,
  relative to how it was held when switched on, the screen's orientation (portrait or landscape) taken into
  account; dragging still adds to it; denied or absent: a short note (`ui.view3d.motion_denied`), dragging only.
- **The server**: the 3D page's own `Permissions-Policy` (every page's sets `accelerometer=()`, `gyroscope=()`,
  `magnetometer=()`): for `/view3d` `accelerometer=(self), gyroscope=(self), magnetometer=(self)`, everything else
  as every page's, chosen per path as `PAGE_CSP` is (`web.py`, a test as the CSP's: other pages unchanged). The
  sensors' readings never leave the browser: nothing stored or sent, so the privacy page stays as it is.
- One agent (VF) on `l3d-wF-walkerview`; it owns `viewer/src/view3d/` modules of the views (new, e.g. `views.ts`,
  `look.ts`, `motion.ts`), `view.ts` (switching the controls), `walker.ts`, `main.ts`, `walk.ts`, `pin.ts`,
  `edit.ts` (only to stay out of the walker views), `view3d.css`, `scene-api.ts` (what it needs), new `ui.view3d.*`
  texts in `locales/en.json`, the `Permissions-Policy` of `/view3d` in `web.py`, the tests of all that
  (`tests/test_viewer.py` Node tests of the pure parts: the camera poses from a walker pose, the gaze from a drag
  and from device angles; `tests/test_view3d.py` an Edge check of each view, `data-view`, no CSP violation;
  `tests/test_public.py` or `tests/test_web.py` the header). Not `edges.ts`, not the feature lines of `scene.ts`
  (the coordinator changes the Edges look in parallel), not `imagery.ts`, `ring.ts`, `tiles.ts`.

## Wave F2: zoom in the walker's views (2026-11-02, the user's decisions)
- **Eyes' field of view as a horizontal angle**, the same on every screen: 60° by default (the user's choice: the
  perspective closest to judging distances on the spot; 70° vertical had made about 106° horizontal on a desktop,
  about 52° on an upright phone). The camera's vertical angle follows from the canvas's aspect
  (2·atan(tan(h/2)/aspect)), again on every resize.
- **Zoom**: Eyes narrows the horizontal angle like binoculars, from about 110° (wide) to about 8° (×8 of the
  default; the indicator shows the factor against 60°, e.g. "×2"); Behind moves the camera nearer or farther
  along its line to the walker, 1.5 to 30 m (default 5 m; the indicator in metres, the camera still at least 1 m
  above the terrain). Mouse wheel, two-finger pinch, and +/− buttons with the indicator beside the view switch
  (shown in the walker's views only); each view keeps its zoom while the page is open; the orbit view unchanged.
- One agent (VF2) on `l3d-wF2-zoom`; it owns `look.ts`, `views.ts`, `view.ts` (only what the zoom needs),
  `view3d.css`, new `ui.view3d.*` texts (`zoom_in`, `zoom_out`, the indicators), the tests of all that (Node:
  the vertical angle from a horizontal one and an aspect, the zoom's clamps and steps, the pinch's factor; Edge:
  wheel and buttons change `data-camera`'s angle in Eyes and its distance in Behind, no CSP violation, the phone
  bar still fits at 390-412 px).

## After waves F and F2 (2026-11-02/03)
- **VF** (`look.ts` pure and Node-tested, `views.ts` the switch, the drag and the motion): the view switch first
  in the bar (icons, their names from 600 px on; under 600 px on a row of its own with the phone's motion); the
  eyes 1.6 m over the walker's feet on the loaded webbing (its mannequin, pin and grip hidden), behind 5 m back
  from its chest along the gaze, never under the terrain; both placed before every frame, so they draw on demand
  as the rest; leaving them gives back the orbit's camera (`View.setOrbit`, `place`). The phone's motion is a
  toggle where `DeviceOrientationEvent` exists and the pointer is coarse; a note when denied or silent for 2 s;
  changes under 0.15° draw nothing. The root's `data-view`, `data-motion`, `data-camera`; `ui_shots` pages
  `view3d-eyes`, `view3d-behind`, `view3d-motion` (Chromium given the sensors' permissions). `web.PAGE_PERMISSIONS`
  as decided; the privacy page unchanged (the readings stay in the page).
- **VF2**: `look.ts` `zoomRange`, `zoomStep`, `zoomBy`, `wheelFactor`, `pinchFactor`, `eyesAngle`,
  `behindDistance`, `verticalFov`, `cameraFov`, `zoomLabel`; the eyes from 110° to ×8 of 60° (about 8.3°); the
  wheel kept from the page in the walker's views only; a pinch turns nothing until every finger is lifted; a drag
  in the eyes turns by the camera's vertical angle per stage height, so the world follows the finger at every
  zoom; `data-camera` adds the horizontal angle and the distance to the point looked at.
- **At the merges**: the Edges' walls back at 35 % (`WALL_OPACITY`, the user's choice from the orbit videos);
  `test_view3d_interaction[full]` failed once under load (wave P); the walker's slider about 95 px on a Pixel 7
  in the walker's views (wave P).
- **`main` merged into the branch on 2026-11-03** (1056134: new sources batch 2, obstacles on rock, performance
  round 3's wave 1): the ring's orthophoto origins 13 → 21 (`RING_ORIGINS`), `tests/test_patch.py::
  test_patch_loads_no_numba` (the quick lane never loads numba, the patch neither); the profile of a run saved
  after 212c7a0 applies its obstacle rule (`Plan.obstacles` in run.json), so the 3D view's verdict follows it.
  Later that day the branch was rebased onto `main`, a432d15 and then edca9a1 (also line picking on the map,
  performance round 3's wave 2, the test lock's slots, the public grid limit, new sources batch 3), which left
  no merge commits: the merge's own changes are the commit 390c051.

## Wave P: polish after wave F2 (2026-11-03)
The coordinator merges `main` into the branch meanwhile (new sources, obstacles on rock, performance round 3; none
of this wave's files) and writes the docs. One agent (VP) on `l3d-wP-polish`:
- **The phone bar in the walker's views**: since F2 the walker's slider is about 95 px wide at 412 px (Pixel 7)
  beside the zoom's −, indicator and +. Give it back at least the width it had in those views before F2 (measure
  at eaea8fd), keeping the user's decision (the zoom's buttons and indicator beside the view switch, in the
  walker's views only), at 390-412 px without a horizontal scroll; the orbit view's bar and the desktop's as they
  are.
- **The look hint names the zoom**: `ui.view3d.look_hint` becomes "Drag to look around, scroll to zoom." and a new
  `ui.view3d.look_hint_touch` "Drag to look around, pinch to zoom." is shown where the pointer is coarse (the test
  the page's level uses); `motion_denied` stays.
- **The iPhone checklist** (`tools/device_page.py` `CHECKLIST`): the walker's views (Eyes and Behind, dragging to
  look, the slider and the walk carrying the camera), Phone motion (iOS asks inside the button's tap; turning the
  phone turns the gaze, in landscape too; a denial shows the note; with the self-signed certificate iOS may refuse
  the sensors: to be noted, not a failure of the page), the zoom (pinch and +/− in both views, the indicator), and
  Edges without "(once wave E is in)".
- **The flaky `test_view3d_interaction`**: `[full]` failed once on 2026-11-03 while three sessions ran pytest and
  passed alone; its assertion was not kept (an earlier failure, on 2026-11-02, was the walk's: `walked` 0 after
  half a second, no frame drawn). Reproduce it under load (several copies at once), then wait for conditions with
  deadlines instead of fixed times; never loosen what it checks.
- It owns `view3d.css`, `views.ts` and `look.ts` (for the hint and the bar only), the two texts in
  `locales/en.json`, `tools/device_page.py` and its test, `tests/test_view3d.py` and `tests/test_viewer.py` (where a
  Node test needs it); `viewer/dist` rebuilt. Not `web.py`, `jobs.py`, `search.py`, `CLAUDE.md`, `README.md` or this
  contract (the coordinator's, merged with `main` meanwhile). Checks: tsc, `node build.mjs`, `tests/test_viewer.py`,
  `tests/test_view3d.py`, `tests/test_device_page.py`, and `tools/ui_shots.py`'s 3D pages on both phones in Eyes and
  Behind, light and dark (the screenshots' folder in the report; never with Esri's imagery chosen).

## After wave P (2026-11-03)
- **VP** (52edd35): under 600 px a break before the views' switch (`.v3-toolbar::before`, the rows' gap as margins,
  so it adds no height); the walker's slider at 412 px (Pixel 7) 73.7 px before F2 and at e340305 (the switch
  shared its row, F2 had not shrunk it), 187.7 px in the walker's views after; at 390 px (iPhone 13, WebKit) 159.7
  px throughout. The look hint names the zoom (`look_hint`, `look_hint_touch` where the pointer is coarse).
  `tools/device_page.py` served `/view3d` with every page's Permissions-Policy, which turned the motion sensors
  off: now `web.PAGE_PERMISSIONS` (its test checks it); its checklist has the walker's views, Phone motion and the
  zoom. `test_view3d_interaction` was not reproduced under load (12/12 and 24/24 with CPU burners); its script
  polled with plain timers, under which headless Edge draws no frame unless something loads (the canvas's redraw
  after the readout fills in places the handles it drags): it polls with a small fetch and drags once no frame
  came for a second (15 s limit, `settled` asserted).
- **At the merge (fbed384, the coordinator)**: the break in the orbit too (its slider 74 px at 412 px beside the
  switch; now as wide as in the walker's views, the bar as high in every view); the look hint at the phone level
  as well, in place of its note (`v3-phone-note`, hidden in the walker's views as the anchors' hint is), so the
  bar keeps its height when the view changes.
- **To watch on the iPhone** (checklist item h): in Playwright's WebKit a bar 4 px higher after a view switch left
  the canvas blank while frames were counted (fixed by the constant height); a resize of the canvas, e.g. turning
  the phone, deserves a look.

## After the rebase onto main edca9a1 (2026-11-03)
New sources batch 3 (main 07207a6) brought two options of an orthophoto's WMS, `OrthoService.wms_version` ("1.1.1":
EPSG:4326 in lon-lat order only, Slovenia's and Iceland's services) and `wms_crs` ("EPSG:3857": Iceland's
gis.natt.is serves Web Mercator only, and answers PNG when JPEG is asked). The 3D view asks them as
`orthophoto._get_map` does:
- `tiles.ts` `wmsTile`: version 1.3.0 with `crs` EPSG:4326 in lat-lon order, 1.1.1 with `srs` in lon-lat order;
  EPSG:3857 the tile's Mercator box (`mercatorBox`, `orthophoto.mercator_box`), x before y in both;
  `tests/test_view3d_tiles.py::test_wms_versions_and_crs_as_the_cache_asks` compares the four combinations with the
  server's parameters. The JPEG asked is drawn over white (`TileImage.white`, `imagery.ts` `drawImage`; the white
  test's probe too), as the server lays a PNG answer on white (`orthophoto._on_white`): its parts without imagery are
  white in our cache and in the service's tiles alike (`test_wms_tiles_drawn_over_white`).
- The ring: `ringmath.ts` `overlaySpecs` gives a WMS's `version` and `crs`, which 3d-tiles-renderer's
  `WMSTilesOverlay` takes (its `WMSImageSource` writes SRS or CRS and the axis order of each). A PNG answer's
  transparent parts show the ring's own colour there (the library composes the overlays; the far field only).
- `mapping.ortho_entry` (data.js and the patch's meta) writes both options as `save_map` does since 07207a6;
  `RING_ORIGINS` 21 → 27 (Svalbard's npolar, Iceland, Brandenburg, Schleswig-Holstein, Queensland, Slovenia).

## The iPhone test (2026-11-03)
The user opened the device page (`tools/device_page.py serve`, at 1428dfe) on their iPhone (iOS 18) over the
home network: 15 lines recorded from five runs (Dolina Bolechowicka, Gryffenbach, Mürren's rim, Kozie Czuby,
Serra de Bernia), each at the levels phone and full, with the checklist of wave P (the walker's views, Phone
motion, the zoom, the phone turned, five minutes open). The user's verdict: "Looks good. Everything works."

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
