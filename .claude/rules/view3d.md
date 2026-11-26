---
paths:
  - "viewer/src/view3d/**"
  - "tests/test_view3d*.py"
  - "tests/test_patch.py"
  - "tests/test_reach.py"
  - "tools/device_page.py"
  - "tools/perf_reach.py"
---
# The 3D view of a line

What each module holds: docs/code-map/viewer.md (`viewer/src/view3d/`); the contract of its waves and every decision:
docs/3d-view-contract.md. Its server side lives in `search.py` (`patch_of_line`, `encode_heights`, `encode_shore`,
`reach_of_anchor`, `canopy_of_line`) and `web.py` (`patch_body`, `page_csp`, `/api/patch`, `/api/reach`).

## Must stay in sync

- The 3D view's patch body: `search.encode_heights` (server), `viewer/src/view3d/decode.ts` (page) and the reference
  `encode`/`decode` of `tests/data/make_patch_fixture.py` (`patch_zabi_kon.bin`): int16 decimetres above `base_dm`,
  -32768 for no data, horizontal deltas with wrapping int16 arithmetic, deflate; the meta's fields
  (docs/3d-view-contract.md, "`/api/patch`") and `web.patch_body`'s framing go together (`tests/test_patch.py`, the
  Node decoder test of `tests/test_viewer.py`: the values' sha256). The meta's round-2 keys (`slope`, `leash_fall`:
  the profile chart's formula model; `surface`: the trees' tool; `group_distance`: the spots of the lines from a
  point) and the run's `end_zone`/`lift` (`search._end_keys`, only when not 0; the 3D view starts the webbing at
  terrain + lift and draws an A-frame post at each anchor, `view3d/geometry.ts` `raised`/`aFrame`, `line.ts`,
  `edit.ts`; the zone is not drawn in 3D) are `PatchMeta` of `decode.ts` and `tests/test_patch.py`.
- The 3D view's reach and canopy (docs/3d-view-contract.md, "Round 2"): `search.reach_of_anchor`'s answer (the meta's
  `lattice`, `res`, `left`, `top`, `anchor`, `as`; one uint8 a sample: 0 not valid, else the low 7 bits
  `ceil(clearance / 0.5)` and the high bit over trees) and `viewer/src/view3d/reach.ts` (decoding, a sample's class,
  the snap, the picture); `search.canopy_of_line`'s (uint8 half metres above the terrain, 0 below 1 m) and
  `canopymesh.ts`; both framed and checked by `web.patch_body` like the patch. A target is evaluated in the order the
  page asks `/api/profile` (`as`: the two directions differ, up to 1.7 m of clearance under the sag model), so the
  mask and the verdict after a release agree: `tests/test_reach.py` compares the mask with `search.profile_of_line` in
  both orders; a change of `helpers.evaluate_line`'s decision, of `linesearch._pairs`' limits of length and height
  difference or of `obstacles.obstacle_surface` reaches the mask too. The page sends one quick request at a time
  (`reach.ts` `reachLane`: the public site allows one waiting quick task a user); `tests/test_view3d_flow.py` runs the
  page against the app's own routes. The engine and the lattice were chosen on `tools/perf_reach.py`'s numbers: a
  change of either is measured again with it.
- The orthophoto of a service with a WMS and base tiles is composed alike by the server for the 2D map's cache
  (`orthophoto.tile_content`, `_white_blocks`) and by the 3D view in the browser (`viewer/src/view3d/tiles.ts`
  `orthoComposed`, `whiteBlocks`, `imagery.ts` `drawComposed`): the WMS as JPEG first; all white → the base tile; any
  white 8×8 block → the transparent PNG over the base; else the JPEG (white: grey == 255 on the server, every channel
  ≥ `WHITE_MIN` 250 in browsers' decoders; `tests/test_view3d_tiles.py::test_white_blocks_match_python`). A
  transparent PNG over every tile took 13 MB an open at R2 (~1.7 MB now). Both ask a WMS in its version and CRS
  (`OrthoService.wms_version` 1.1.1: SRS in lon-lat order; `wms_crs` EPSG:3857: the tile's Mercator box):
  `orthophoto._get_map`, `tiles.ts` `wmsTile` (`test_wms_versions_and_crs_as_the_cache_asks`), the ring's
  `ringmath.ts` `overlaySpecs`; a PNG answered for a JPEG lies on white (`orthophoto._on_white`, `TileImage.white`).
- The 3D page's Content-Security-Policy (`web.page_csp`): with the ring on, `connect-src` adds the ring's origin,
  Esri's tiles and the catalogue's orthophoto origins (`web.ortho_origins`, pinned in
  `tests/test_public.py::RING_ORIGINS`): a new orthophoto service changes that list. The Mapterhorn privacy fact and
  about line show only while `ViewSettings.ring` is on and name Mapterhorn: another `FINDALINE_3D_RING_URL` needs its
  own approved texts. `viewer/src/layers.ts` has no Leaflet (the 3D bundle imports it); Leaflet's layers are
  `baselayers.ts`. Its Permissions-Policy (`web.PAGE_PERMISSIONS`, chosen per path by `guard` as the CSP is) allows
  the accelerometer, gyroscope and magnetometer to its own origin for *Phone motion* (`views.ts`); every other page
  keeps `SECURITY_HEADERS`' (all off). The page has two addresses, `/view3d` and a share link's `/s/<token>/view3d`
  (2026-11-26): its CSP, permissions and `no-store` follow both; link mode is read from the path (`sharelink.ts`), and
  every computed fetch (patch, canopy, profile, reach) goes with `computedHeaders` and through `sharelink.ts`' wait
  after a 429 (`checkBackoff`/`noteRefusal`): a new one too. The readings never leave the browser, so the privacy page names none: code that
  sends them changes it.

## Pitfalls

- **The 3D view in WebKit and Playwright**: drawn on demand, the canvas showed the frame before the last until another
  was drawn (Playwright's WebKit, 2 opens in 4): the renderer keeps `preserveDrawingBuffer`. Under the app's CSP (no
  `unsafe-eval`) Playwright's `wait_for_function` needs a function string (`"() => (...)"`); its screenshots in WebKit
  report a refused stylesheet (its own caret style), not the page's. A DOM overlay (the anchors' handles) is never
  hidden by terrain while the webbing near an anchor can be.
- **Sizes on a touch screen** (DESIGN.md rows 43, 45): keyed on `@media (pointer: coarse)`, never on `.v3-phone` (the
  desktop's `?level=phone` has a mouse, a phone's `?level=full` a finger). A mark over the stage (fan dot, label, handle)
  grows its target with a positioned `::after`, never its own size or margins: those place it on its point
  (`screen.ts` `place`; `tests/test_view3d_touch.py`); near the stage's edge `targetInside` moves the target inside
  (`--v3-tx`/`--v3-ty`, the mark's half-sizes and how far it may move; `tests/test_view3d_keyboard.py`).
- **The tool strip** holds its tools in the DOM in their order (`chrome.ts` `createTools`, `data-order`), so the Tab
  order is the order on screen: never a CSS `order` (the bar's switch under 600 px: `views.ts` keeps it the toolbar's
  last child). While handles are dragged the bar gets neither higher nor lower, and no lower until the profile answers
  (`edit.ts` `holdBar`, a count): a row the drag adds to the bar shows at the release, never during it.
- **A new note in the bar** (DESIGN.md row 39): one that explains goes behind the phone's "About this view" button by
  itself (`info.ts` `INFO_NOTES`); one that says what failed or answers a tap gets the class `v3-alert` and stays in
  sight, as the safety sentence does (`.v3-check`, `INFO_KEPT`: the user's word, never into the box). The button and
  the box are for touch and the phone level: a mouse window keeps its lines at every width. A size that depends on the card (`chrome.ts` `stepAside`) is tested with its own effect off, never from the
  state it made (`tests/test_view3d_layout.py`).
- **The one-row bar** (DESIGN.md row 37: a phone held sideways, a touch tablet) keys on the class `v3-row`, whose
  condition lives in `chrome.ts` `oneRow` alone; a media query of the viewer never takes the range syntax
  (`width > 600px`: WebKit before Safari 16.4 drops the whole query; `test_viewer_media_queries_older_webkit`).
- **A long press on the stage** (line volume round 6, gate 2): the stage selects no text and shows no iOS callout
  (`view3d.css` `.v3-stage`), and a press on it ends a selection and takes the focus from a control outside it
  (`views.ts`); a new control inside the stage that needs its text selectable sets it back itself
  (`tests/test_view3d_press.py`).
