# Code map: the viewer and the 3D view

What the modules of this area hold, in detail: the viewer and the 3D view. Moved out of CLAUDE.md on 2026-11-12;
nothing loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync
and the pitfalls are in `.claude/rules/` (viewer, view3d, browser-tests, coverage-map).

## `viewer/`

The result viewer (TypeScript, Preact, Leaflet; `src/`: `map/main.tsx` a run's `map.html` (bundle `viewer.js`: the
app's result view, `result/view/ResultColumns.tsx`, loading the run's data.js itself (`loadRunFrom`; a map.html
written before 2026-11-04 loads it by a tag first, which it still takes), `#line=` in its hash, the way back to
`../index.html` from disk or to the app, none on a share link; the old map with popups and panels was removed on
2026-10-30), `filters.ts` filters and their ranges (`liftMax`/`liftNoZone`: the A-frame needed, on a run with the
options only), `endzone.ts` the zone's TypeScript twin of `helpers.zone_steps` and the chart's limit with the zone and
the lift (`limits`, `riggingNeed`, `liftChoices`), `labels.ts` the chart's label layout (`layoutLabels`: no two boxes
intersect, priority anchors > min clearance > A-frame > zone > highest, a label that does not fit is dropped),
`profilechart.ts` the chart's geometry, `Profile.tsx` the chart (the A-frame posts, the zone bands, the pill of the
rigging need), `list.ts` the sortable list of lines, `leaflet.ts` Leaflet's CSS and marker images for both bundles,
`layers.ts` the data credits and Esri's tile URL (no Leaflet: the 3D view imports it too), `baselayers.ts` the base
layers, `keys.ts` keys of lines, `favourites.ts` favourites, their folders' requests and their export, `folders.ts`
the folder tree, `shore.ts` the uncertain shore's pure parts (`segmentBox`, `metresInView`, `SHORE_COLOURS`) and
`shoreLayer.ts` its Leaflet overlay (in the layer control of `result/view/ResultColumns.tsx`, on by default) and the
control `.u-shore` at the map's top left: a legend of the two kinds with the metres of each in view and a "?" opening
`ui.shore.help`, shown only while the view holds some (`addShore`)), bundled by esbuild into `dist/` (committed);
copied to `runs/_viewer/` by every run. The app (`app/app.tsx`: the app's one interface, C (`app/c`); B and D were
removed on 2026-11-04, so `?ui=` chooses only the kits and a stale `b` or `d` gives C, `ui/choice.ts`; "Copy link"
gives no `?ui=`; the old app with tabs was removed on 2026-10-30; docs/roadmap.md, "UI prototypes B, C and D"): `ui/`
tokens, icons and components under a `.ui` root (`components.tsx` `Splitter`: a draggable, focusable separator,
WAI-ARIA's window splitter, our own (react-resizable-panels would need preact/compat, split.js is unmaintained);
`Sheet` the phones' bottom sheet (peek, half, full); no Rail, Toast or Tabs since B went; `Hint.tsx` the "?" of a
field and its bubble, the site's bounds added by `search/SearchPanel.tsx` from `hint.bounds.*`; `Intro.tsx` an intro
dialog shown once per browser (localStorage `findaline.intro.<name>`, `IntroLink` opens it again); `choice.ts` the
switch, `Gallery.tsx` `?ui=kit`; `pages.css` the server-rendered sign-in, privacy and about pages of `web.py`; `logo/`
the logo: `logo.svg` and `mark.svg` coloured by classes of `ui.css` (`Logo`/`LogoMark` in `icons.tsx` bundle them as
text), `logo.svg` and `favicon.svg` copied to `dist/` by `build.mjs` (`web.LOGO_SVG` reads `dist/logo.svg`; the
standalone files in `docs/logo/`)), `result/` a run in the app (`load.ts` `loadRun`/`loadRunFrom` its `data.js`: over
http(s) downloaded by `download.ts` (XMLHttpRequest: its progress counts the decoded bytes, against `SIZE_HEADER` =
`web.SIZE_HEADER`, which `web.RunFiles` sets: nginx's gzip drops Content-Length; the 3D view's patch too) and read by
`parseRunScript` (JSON.parse, about 30 % faster than the script), a file it refuses (NaN, Infinity) and every load
from disk as a script, `LoadProgress` to `RunLoading.tsx` (the phases and a bar; `model.ts buildModel` builds the
model after a paint, `paint.ts nextPaint`), `orthoForApp` its orthophoto's cache for the app's page; `model.ts`
`ResultModel`: filters → groups → rows, selection, next/previous spot, favourites; `ResultMap.ts` its Leaflet layer
(one canvas, no line interactive: a second canvas took every click of the map; a click takes the nearest line within
`REACH_MOUSE`, a finger's within `REACH_TOUCH`, known by the last pointerdown since WebKit's click after a tap is a
"mouse" one; spots within `TIE_*` of the nearest go to `onChoose`, the workspace's `view/LineChooser.tsx`); `view/`
the panel pieces (`ResultColumns.tsx`: C's result, shared by `app/c/ResultPage.tsx` and `map.html`: a header, the list
and the details as side panels (`Splitter` edges, a collapse tab beside each, 36 px rails, forced rails "auto" in a
narrow window, never kept), the map between them with `ProfileCard.tsx` over its bottom (`ProfileDock` in fill mode
with a compact head and a fold button; height by its top edge, width by its side edges; folded in a map lower than 420
px, nothing kept from there), the corners above the card only where it covers them (`corners.ts`
`useCornersAboveCard`), the run's data credits folded behind *Data credits* while the card is shown; on phones the
sheet; `layout.ts` the kept layout (localStorage `findaline.layout`, `sanitize`, `fitColumns`, `cardInsets`,
`moveCardEdge`, `LIMITS`) and `useLayout.ts` its state; `credits.ts` `useRunCredits`), `view/ResultIntro.tsx` "How to
read the result" (mounted by `FilterBar.tsx`), demo `?ui=kit-result`), `search/` the new search panel (`useSearch`:
modes, presets, live estimate; `PlaceBox.tsx` the place-name box; `SearchIntro.tsx` "How a search works" with the
user's limits from `/api/usage`; demo `?ui=kit-search`), `app/useJobs.ts`, `app/request.ts` (the search's request),
`app/areas.ts` and `app/files.ts` (areas of drawn shapes, area files) shared by the shells, `app/BetaNotice.tsx` (the
notice after a sign-in: the cookie `web.WELCOME_COOKIE`) and `app/ReportDialog.tsx` with `report.ts` (Report a
problem, opened by a window event from anywhere; both mounted by `app.tsx`), `app/c/` the app's shell (`AppC.tsx`: the
header, the pages and the phones' bottom navigation; hash routes in `route.ts`; `ResultPage.tsx` wraps
`result/view/ResultColumns.tsx`; `NewSearch.tsx` the search, whose panel `search/SearchPanel.tsx` has one layout since
its variant of B went (the demo `?ui=kit-search` shows it); `AdminC.tsx`, `OsmC.tsx` the admin and OSM pages;
`LayerPage.tsx` the highline layer (`#layer`; the local app and administrators, from the account menu; three columns,
`MapPage` with an `aside`: the filters, legend, level and selected cell on the left, the map, the histograms of the
counts in view on the right (`LayerHistograms.tsx`: a bar per bin, a click sets the length range or a threshold);
every country's cube whose box reaches the view at once, a study area (`CountryCube.study`) only alone
(`layerState.ts` `activeCubes`, `countriesFirst`; `LayerSource`: `countries`, `cells`, `histogram`, `outline`), the
level chosen by the client (`layerState.ts` `autoLevel`: at most `CELLS_FIRST` cells at first, then finer below
`CELLS_FINER`, coarser above `CELLS_COARSER`, and coarser while a cube's request would pass `REQUEST_CELLS_MAX`), the
cells of a padded box asked once and kept while the view stays inside it (no `/cells` request, the fitted breaks
kept), fetched 300 ms after a change and aborted; the right panel a second Preact tree rendered into the aside (never
`preact/compat`'s portal); `cellsLayer.ts` the cells on a `SafeCanvas`, each drawn and divided by its part inside the
country (`cellShape`, `cellKm2`: the server's `cut`), coloured by the density per km² in log classes (fixed
`CLASS_BREAKS`, or fitted to the padded box's 2nd-98th percentile, `quantileBreaks`, eased over `EASE_MS`; tokens
`--layer-1..5` of `ui/tokens.css`), the countries' outlines below `OUTLINE_MPP`; the view and every filter in the hash
(`layerState.ts` `parseState`/`stateParams`, written in place, `ShellC` ignores changes within `#layer`); "Search
here" opens `#new&cell=<id>:<band>:<level>:<i>:<j>`, `NewSearch` with `api.countryRequest` as its `initial`; demo
`?ui=kit-layer`: `ui/Gallery.tsx` `KitLayer`, two canned cubes); `FavouritesPage.tsx` the favourites in folders, drag
and drop with Pragmatic drag and drop), `result/view/FavouritePicker.tsx` the favourite button's folders; `coverage/`
the coverage map: `types.ts` (coverage.json, the outlines, contrast.json), `data.ts`, `i18n.ts` (`ct` of its own
catalogue `locales/coverage/`, `metres` with the language's decimal sign, `areaName`, `noteText`), `palette.ts` (the
colours of the page, the layer and the canvas), `page/` the page /coverage (flat d3 map, Leaflet, globe; card, legend
with three scales, list of the areas), `draw/` and `media/` the canvas of the animations and images (`media/main.ts`:
`window.FAL_MEDIA`; built only by `node build.mjs --media`, never in dist); `app/coverageLayer.ts` the place map's
*Data coverage*; `translator.ts` the `translator` of both catalogues (so coverage.js holds only its own);
`ui/fonts.css` Barlow Condensed (woff2 of weights 500-700, latin and latin-ext, flat hashed files in dist:
`install_viewer` copies dist file by file)

## `viewer/src/view3d/`

The 3D view of a line (bundle `view3d.js`, page `web.VIEW3D_HTML`, opened by the line's "3D view" button of the app's
result: `#run=<id>&line=<lat1,lon1,lat2,lon2>`, `?level=phone|full`; plain DOM and three.js, no Leaflet and no
data.js): `main.ts` the page (patch, then profile, then imagery and ring), `page.ts` its request, `decode.ts` the
patch body (`DecompressionStream`, the sha256 checked), `terrain.ts` with `martini.ts` (vendored @mapbox/martini,
licence in `viewer/licences/`) the chunks' meshes (forced samples at the anchors and the line's footprint, skirts, an
error raised until the vertex budget fits), `scene.ts`/`scene-api.ts`/`view.ts` the scene and its API for the modules
(drawn on demand only: `invalidate`, `onFrame` while an owner `keepDrawing`, `beforeDraw`; `preserveDrawingBuffer`),
`imagery.ts` with `tiles.ts` and `credits.ts` the imagery kinds (the run's orthophoto: our cache, then the service;
Esri with a key; shaded; edges), `shore.ts` the uncertain shore hatched on the chunks' canvases (`drawShore`: the
patch's kinds as texture rectangles, `hatchPattern`; on the Shaded look a lit texture of the terrain's colour with the
hatching, `Chunk.setTexture(..., lit)`, a `MeshLambertMaterial`; the Edges look draws none) with the note
`ui.view3d.shore_hatched`, and `detectWalls`, the same thing from the heights alone (a sample at the sea's level next
to one `WALL_DROP` higher; `agreement` with the data's kinds: on Ta' Cenc every wall it finds is in the data, which
also knows the faces from the surface model), `edges.ts` the Edges look (a screen-space pass of silhouettes and
creases, the mesh's feature edges, paper; the walls' edges, both faces steeper than `WALL_SLOPE`, drawn apart at
`WALL_OPACITY` 0.35: the user's choice), `line.ts`/`webbing.ts`/`geometry.ts` the webbing with `sag.ts` (the loaded
curve also drawn faintly through the terrain), `walker.ts`/`walk.ts`/`pin.ts` the walker, its walk and the pin over
it, `views.ts`/`look.ts` the views Orbit, Walker's eyes and Behind the walker (the camera's pose from the walker's,
the gaze dragged or turned by the phone: `DeviceOrientationEvent`, iOS's `requestPermission` inside the tap; the zoom:
Eyes' horizontal angle, 60° by default, from about 110° to ×8, Behind's distance 1.5-30 m),
`edit.ts`/`interact.ts`/`screen.ts` the anchors' editing at level full (a DOM overlay over the canvas, three-mesh-bvh
raycasts, `/api/profile` after a release), `ring.ts`/`ringmath.ts` the coarse ring of terrain (3d-tiles-renderer's
`TerrariumMeshPlugin`, behind `FINDALINE_3D_RING`; it clamps the plugin's private `_maxSourceLevel` of 0.5.3: check it
on an upgrade). Round 2 (2026-11-05; docs/3d-view-contract.md, "Round 2"): `chrome.ts` the activity pill and the tool
strip over the stage (`Scene3D.activity`, `Scene3D.tools`; the tools' ids and order in the contract), the card's slot
under the credits (`Scene3D.card`; opening the card folds the data credits, `Credits.fold`); `pin.ts` the walker's pin
over the unloaded webbing with a leader (`interact.ts` `pinPlacement`); `profilecard.tsx` the 2D result's
`Profile.tsx` in that card (a second Preact tree by `render` of `preact`), its cursor and the walker following each
other; `save.ts` the key of the line shown (`canonicalKey`: the 2D result's `keys.lineCoords`; `LineView.key` for a
line taken from outside) and saving it into the favourites; `reach.ts`/`overlay.ts` "Only valid lines" (the reach of
the staying anchor from `/api/reach` as `Scene3D.setOverlay`'s picture, a dragged handle on valid samples only;
`reachLane`: reach and profile requests one at a time); `canopymesh.ts`/`canopy.ts` trees and buildings
(`/api/patch?part=canopy`, a tool only when the patch's meta has `surface`); `others.ts`/`otherlines.ts` the address's
`&also=` lines and the user's other saved lines of the run (a click makes one the active line:
`Edit.setAnchors(anchors, key)`); `options.ts`/`fan.ts`/`optionlist.ts`/`point.ts` the lines from a clicked point (the
point's reach, its representatives the result's spots through `grouping.ts` with the meta's `group_distance`). The
contract of its waves and every decision: docs/3d-view-contract.md; the research: docs/3d-view.md
