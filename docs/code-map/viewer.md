# Code map: the viewer and the 3D view

What the modules of this area hold, in detail: the viewer and the 3D view. Moved out of CLAUDE.md on 2026-11-12;
nothing loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync
and the pitfalls are in `.claude/rules/` (viewer, view3d, browser-tests, coverage-map).

## `viewer/`

The result viewer (TypeScript, Preact, Leaflet; `src/`: `map/main.tsx` a run's `map.html` (bundle `viewer.js`: the
app's result view, `result/view/ResultColumns.tsx`, loading the run's store or data.js itself (`loadRunFrom`; a
map.html written before 2026-11-04 loads data.js by a tag first, which it still takes), `#line=` in its hash, the way
back to the app, none on a share link; the disk notice (store wave 4: `mapping.MAP_HTML`'s `#disk-notice`, `NOTICE`,
`map/notice.css`): over http(s) the page is marked `fal-served` by `map/served.ts` (the entry's first import, so a
later module that throws leaves the mark) before the notice is parsed, which hides it, and it is
removed once parsed; from disk a page with the notice shows it (the run's name, `ui.map.disk_notice`, `findaline.py
view <id>`) in the stored theme and loads nothing, one without it (written before) loads its data.js as a script and
goes back to `../index.html`, until the reader of data.js ends; the old map with popups and panels was removed on
2026-10-30), `types.ts` the run data's types and a run's lines as columns (`lineColumns` from data.js's or lines.js's rows: a
`NumberColumn` per value, the grouping's values as `Float64Array`, the others as the narrowest integers that give back
the very double (null, NaN and -0 kept), else doubles; `lineAt` a Line of a row, `LineCursor` its values without one;
`toLine` the reader of one row they must equal: tests/test_viewer.py `test_columns_give_the_rows_values`;
`storedColumns` the same columns over a store's own arrays, `NumberColumn.stored` with Arrow's validity bits instead of
codes, a missing value null or NaN as data.js shows it (`NULL_WHEN_MISSING`); `LineColumns.profiles` a `ProfileSource`;
`RunInfo.store` run.json's block `store`),
`grouping.ts` the grouping (`groupIndices` on typed arrays, `groupLines` over objects: the 3D view's fan, the tests),
`filters.ts` filters and their ranges (`liftMax`/`liftNoZone`: the A-frame needed, on a run with the
options only; `hideNeed*`: the classes of rigging of the head's "Why so many?" box, `needClass`, not kept),
`access.tsx` the access mark of a run made with `--access` (`types.ts` `ACCESS`, `Line.access1`/`access2`: 0 hard
access, 1 cannot tell, 2 easy access, null without): `AccessMark` (a dot of 20 px in the state's colour, tokens
`--acc-*` of `ui/tokens.css`, with its sign, `ACCESS_SIGNS` of `ui/icons.tsx`), `AccessPair` (a list row's two dots;
"–" for a line of a run without the mark), `accessMarkSvg` (the mark of 24 px on the map, in the map's colours),
`AccessKey` and `useAccessHelp` (the one help text of the result page and the search form: a "?" that opens a panel
in place, not a bubble); it hides and sorts nothing; `tight.ts`
the tight mark (`TIGHT` = 1 m, `clearanceText` rounds a tight clearance down, the mark's words with and without A-frames), `endzone.ts` the zone's TypeScript twin of `helpers.zone_steps` and the chart's limit with the zone and
the lift (`limits`, `riggingNeed`, `liftChoices`), `labels.ts` the chart's label layout (`layoutLabels`: no two boxes
intersect, priority anchors > min clearance > A-frame > zone > highest, a label that does not fit is dropped),
`profilechart.ts` the chart's geometry, `Profile.tsx` the chart (the A-frame posts, the zone bands, the pill of the
rigging need), `list.ts` the sortable list of lines (kept under `findaline.list.v2`, mean height first), `leaflet.ts` Leaflet's CSS and marker images for both bundles,
`layers.ts` the data credits and Esri's tile URL (no Leaflet: the 3D view imports it too), `baselayers.ts` the base
layers, `keys.ts` keys of lines, `favourites.ts` favourites, their folders' requests and their export, `folders.ts`
the folder tree, `shore.ts` the uncertain shore's pure parts (`segmentBox`, `metresInView`, `SHORE_COLOURS`) and
`shoreLayer.ts` its Leaflet overlay (in the layer control of `result/view/ResultColumns.tsx`, on by default) and the
control `.u-shore` at the map's top left: a legend of the two kinds with the metres of each in view and a "?" opening
`ui.shore.help`, shown only while the view holds some (`addShore`); on the phone layout (under 768 px) it starts
folded into a one-line chip (`.u-shore-ctl`: the kinds in view and `shoreTotal`) that unfolds into the box, whose
text then scrolls within the map; `coarser.ts` the pure parts of a run's
`terrain_sources` (where its land's terrain came from: `km2InView`, `warns` from `FALLBACK_WARN_SHARE` =
`search.FALLBACK_WARN_SHARE`, `sharesText`) and `coarserLayer.ts` the "Coarser terrain" overlay (the fallbacks'
regions hatched by an SVG pattern of their renderer, colour `--coarse-map`) with its box `.u-coarse` under the
shore's (each fallback's km² in view, `ui.coarse.help`; `addCoarser`, whose `fit` is `ResultModel.coarserFit`, the
"Show on map" of `ResultSummary`'s `CoarserNote`), the shares under More filters (`FilterBar`)), bundled by esbuild into `dist/` (committed);
copied to `runs/_viewer/` by every run. The app (`app/app.tsx`: the app's one interface, C (`app/c`); B and D were
removed on 2026-11-04, so `?ui=` chooses only the kits and a stale `b` or `d` gives C, `ui/choice.ts`; "Copy link"
gives no `?ui=`; the old app with tabs was removed on 2026-10-30; docs/roadmap.md, "UI prototypes B, C and D"): `ui/`
tokens, icons and components under a `.ui` root (`components.tsx` `Splitter`: a draggable, focusable separator,
WAI-ARIA's window splitter, our own (react-resizable-panels would need preact/compat, split.js is unmaintained);
`Sheet` the phones' bottom sheet (peek, half, full); `SidePanel.tsx` a side panel beside a map (its edge, collapse tab
and rail, `useWidthOf`; `sidepanel.css`: the result's and the highline layer's); no Rail, Toast or Tabs since B went;
`Hint.tsx` the "?" of a field and its bubble, the site's bounds added by `search/SearchPanel.tsx` from
`hint.bounds.*`; `Intro.tsx` an intro dialog shown once per browser (localStorage `findaline.intro.<name>`,
`IntroLink` opens it again); `choice.ts` the switch, `Gallery.tsx` `?ui=kit`; `pages.css` the server-rendered sign-in,
privacy and about pages of `web.py`; `logo/` the logo: `logo.svg` and `mark.svg` coloured by classes of `ui.css`
(`Logo`/`LogoMark` in `icons.tsx` bundle them as text), `logo.svg` and `favicon.svg` copied to `dist/` by `build.mjs`
(`web.LOGO_SVG` reads `dist/logo.svg`; the standalone files in `docs/logo/`)), `result/` a run in the app (`load.ts`
`loadRun`/`loadRunFrom` its `data.js`: over http(s) downloaded by `download.ts` (XMLHttpRequest: its progress counts
the decoded bytes, against `SIZE_HEADER` = `web.SIZE_HEADER`, which `web.RunFiles` sets: nginx's gzip drops
Content-Length; the 3D view's patch too) and read by `parseRunScript` (JSON.parse, about 30 % faster than the script),
a file it refuses (NaN, Infinity) and every load from disk as a script; then `columnsOf` reads the rows into columns
and drops them (`RunData.columns`; store wave 1, docs/performance.md "Columns in the page"); a body that arrives
empty although its bytes came (Chromium's longest string, about 537 M characters) fails as `TooLarge`, whose message
`ui.result.too_large` the page shows, and is never tried as a script (that crashed the tab); `LoadProgress` to
`RunLoading.tsx` (the phases and a bar; `model.ts buildModel` builds the model after a paint, `paint.ts nextPaint`),
over http(s) a run whose entry in runs.js holds run.json's block `store` (`storeOf`: the page's list, else
`../runs.js` beside the run's folder, loaded once; a run it does not name and a share link get `STORE_PROBE`: the store's files asked for directly, a 404 or a file not fetched reads data.js) is read from its
store instead (store wave 2,
docs/line-volume/spec-store.md 1.2): `lines.arrow` and `profiles.arrow` downloaded together as bytes, `readStore`
(apache-arrow `RecordBatchReader`: one record batch; the head from the schema's metadata `findaline`, `parseLoose` for
its NaN; the columns views of the downloaded bytes, int64/uint64 ones copied into doubles; a higher `format` than
`STORE_FORMAT` refused as `NewerStore`, `ui.result.newer_store`; a store's file answering 404 falls back to data.js;
another failure is `StoreFailed`, `ui.result.store_failed` on map.html; a null body `TooLarge`), `storedProfiles` a
profile made when it is asked for; `loadOtherRun` Compare's other run (`RunActions`) from its `lines.arrow` (or its
lines.js: no store, or the file missing), `loadRunLines` a mini map's (`app/c/Thumb.tsx`) the same way, and a run the
list does not name by its `lines.arrow` asked for directly (`STORE_PROBE`'s rule: a 404 or a file not fetched reads
lines.js, a newer format is refused); a run read from its store carries `RunData.fromStore` (not one whose
store answered 404), by which `view/RunActions.tsx` `mayExport` (with `api.canChange`: the page has the token,
the app's page, never a map.html) gives Download's two rows that ask the worker for the file (`Export`:
`api.exportRun`, "Preparing the file…" in the pressed row, the ring on the button while the menu is closed, the
browser saves the answered address, this run's export only, by a link's click, a failure one red line by the answer's code; the wait and the line kept per run id outside the component, so a layout switch or a run change keeps them); a run with
a store has no Download where the page may not ask, a run without one keeps its two links; `orthoForApp` its orthophoto's cache for the app's page; `model.ts` `ResultModel`: filters → groups → rows,
selection, next/previous spot, favourites, on columns: the runs shown are `Table`s of `types.ts` `LineColumns` (this
run's from index 0, each other run's from its own `start`, never given twice), a line is its index; the filters
(`filters.passes` through a `LineCursor`), the ranges (one pass, `filters.Ranger`), the counts and the grouping
(`grouping.groupIndices` on typed arrays gathered from the columns, other runs' in `others.localPlane`) read the
columns, a spot is a `LineGroup` (indices; `size`, `has`; `rep` and `members` make Lines when asked); a Line object
is made only by `lineAt` (`madeLines` counts them): each spot's shown line (`shownOf`/`bestOf`, which rank indices
by `byMean` through two cursors), the members of a spot asked for (`membersOf`/`linesOf`: the selected spot, an
unfolded row), a link's line (`linkedLine`), the favourites; kept by index while in use, the rest dropped after a
compute when they are many more than the rows (`prune`); a spot's first line and its order (`BY_MEAN` "Highest on
average", the default of "Show per spot": `bestOf`/`membersOf` by `byMean`, the groups and their members stay the
grouping's), `needCounts`, `hasAccess`: a run shown was made with the access mark (its head's `ends`); `ResultMap.ts` its
Leaflet layer (the selected line's two anchors of a marked run are the mark, markers' icons that take no pointer
events; else one canvas, no line interactive: a second canvas took every click of the
map; a click takes the nearest line within `REACH_MOUSE`, a finger's within `REACH_TOUCH`, known by the last
pointerdown since WebKit's click after a tap is a "mouse" one; spots within `TIE_*` of the nearest go to `onChoose`,
the workspace's `view/LineChooser.tsx`); `view/` the panel pieces (`ResultColumns.tsx`: C's result, shared by
`app/c/ResultPage.tsx` and `map.html`: a header, the list and the details as side panels (`ui/SidePanel.tsx`, shared
with the highline layer: `Splitter` edges, a collapse tab beside each, 36 px rails, forced rails "auto" in a narrow
window, never kept), the map between them with `ProfileCard.tsx` over its bottom (`ProfileDock` in fill mode with a
compact head and a fold button; height by its top edge, width by its side edges; folded in a map lower than 420 px,
nothing kept from there), the corners above the card only where it covers them (`corners.ts` `useCornersAboveCard`),
the run's data credits folded behind *Data credits* while the card is shown; on phones the sheet; the access mark of
a run that has it: the column "Anchors" of `LinesTable.tsx` (full from a list of 356 px, tighter below, left out
under 300 px; the list's default width is 372 px for it), "Reaching the anchors" of `LineDetails.tsx` (on a phone
the two dots also in the sheet's head), the legend's row `AccessLegend` of `ResultSummary.tsx` (on a phone above the
filters also while nothing is selected; its "?" stays with the last state; for a run whose head says
`access_skipped` (the mark asked for and left out, the area too wide) one muted line in the row's place and nothing
else of the mark); `tests/test_access_page.py` draws all of it in a browser; `layout.ts` the kept
layout (localStorage `findaline.layout`, `sanitize`, `fitColumns` and `maxColumnWidth` on the two panels'
`fitPanels`/`maxPanelWidth`, which the highline layer's panels share with their own `LAYER_LIMITS` and kept value,
`sanitizeLayer`, `findaline.layer.layout`; `cardInsets`, `moveCardEdge`, `LIMITS`) and `useLayout.ts` its state;
`credits.ts` `useRunCredits`), `view/ResultIntro.tsx` "How to read the result" (mounted by `FilterBar.tsx`), demo
`?ui=kit-result`), `search/` the new search panel (`useSearch`: the tabs Basic and Advanced, Basic's goal and the
rig in use, Advanced's values, Where's modes, the live estimate; `SearchPanel.tsx` the tabs, Where, Advanced (the goal
cards, a dot and "reset" for a value that differs from Basic's, "Save into" / "Save as a new rig" in Clearance
model) and `EstimateBar`, the bar of both tabs (the size word, the receipt, Start; a phone's compact bar);
`BasicPane.tsx` the Basic tab (with "Reaching the anchors": the access mark is on in every Basic search, `basic.ts`
`BASIC_ACCESS`, where the site's schema has the field; the schema's and the command line's default stays off, so
the form sends `access: true` as a changed value and Advanced, filled from Basic, shows it ticked; Advanced's field
takes the "?" of the same help through `Field`'s `hintButton`; the highline layer's "Search a cell" opens with the
mark on, `cellValues`; an estimate whose messages carry the code `access_skipped` turns the receipt's part into
"access not marked", `accessSkipped`), the rig's window
and the dialog of going back to Basic; `basic.ts` the form's rules
as pure functions (spec-search 1.2: `basicRequestValues` (every value explicit), `basicProblem` (a site that leaves
out a field Basic must send), `matchGoal`, `notInBasic`, `openingTab`, `receiptParts`, `sizeOf`, the rig's words and
checks with the site's bounds (`rigProblem`, `rigMax`), `whereForGoal`, `findaline.rig` the rig in use per browser),
tested in Node; Where is one element kept between the tabs' own parts (`BasicTop`/`BasicBottom`, `AdvancedTop`/
`AdvancedBottom`) in one tab panel (the WAI-ARIA tabs, manual activation); `useRigs.ts` the
saved rigs, `/api/rigs`; `PlaceBox.tsx` the place-name box; `SearchIntro.tsx` "How a search works" with the user's
limits from `/api/usage`; demo `?ui=kit-search`), `app/useJobs.ts`, `app/request.ts` (the search's request), `app/areas.ts` and `app/files.ts` (areas
of drawn shapes, area files) shared by the shells, `app/BetaNotice.tsx` (the notice after a sign-in: the cookie
`web.WELCOME_COOKIE`) and `app/ReportDialog.tsx` with `report.ts` (Report a problem, opened by a window event from
anywhere; both mounted by `app.tsx`), `app/c/` the app's shell (`AppC.tsx`: the header, the pages and the phones'
bottom navigation; hash routes in `route.ts`; `ResultPage.tsx` wraps `result/view/ResultColumns.tsx`; `NewSearch.tsx`
the search (it waits for the saved rigs: a request to edit opens Basic or Advanced by them), whose panel
`search/SearchPanel.tsx` has one layout since its variant of B went (the demo `?ui=kit-search` shows it); `AdminC.tsx`, `OsmC.tsx` the admin and OSM pages; `LayerPage.tsx` the highline layer (`#layer`; the local
app and administrators, from the account menu; `MapPage` with an `aside`: two side panels as the result's
(`ui/SidePanel.tsx`; `layout.ts` `fitPanels` with `LAYER_LIMITS`: left 320-560 px, right 300-640, the map at least
360; kept under `findaline.layer.layout`), each one's content in a scroll box, the rails' labels from the page
(`MapPageExtras`), a panel's change restarting the automatic level; phones one scrolling column, no edges; on the left
the filters (today's seven open, the cube's other dimensions of `kinds` in the fold "More filters" by topic, a closed
fold naming its set filters as chips; the A-frame pair disabled for a cube counted without the no-fall zone and the
A-frames, the clearance over trees without a surface model, each with its note), the legend (the partner cells'
hatched swatch), the totals in view of both modes with the lines across the border (`/histogram`'s `totals` and
`border`), the border switch (`border=all|own`: "All" and "Inside <country> only"), the levels 30″/1′/2′/4′ with their
sizes at the view's latitude, the selected cell (kept by its base cell across levels; its own counts by one
`/histogram` of a box inside it; "Search here" with the hint of a cut or a partner cell naming the neighbour by a
row's side) and the notes ("Across the borders" from cube.json's `neighbours`: a neighbour's own layer shown, or this
country's data until it has one), the map in the middle, on the right the sixteen histograms of the counts in view
(`LayerHistograms.tsx`: by topic, `layerState.ts` `TOPICS`, The line, Anchors and terrain, Rigging, the fold's order
too; a bar per bin, a click sets the length range or the limit by the dimension's kind; two a row while the panel's
content holds two of 220 px, a container query on its scroll box; the chart of the filter changed last ringed and
scrolled to, on phones a swiped strip per topic with that chart enlarged); every country's cube whose box reaches the
view at once, a study area (`CountryCube.study`) or a country of another layer profile (`profile`, R7) only alone
(`layerState.ts` `activeCubes`, `summedWith`, `countriesFirst`; `LayerSource`: `countries`, `cells`, `histogram`,
`outline`), the level chosen by the client in cells of `cell_deg` (`layerState.ts` `autoLevel`: at most `CELLS_FIRST`
cells at first and after a panel's change, then finer below `CELLS_FINER`, coarser above `CELLS_COARSER`, and coarser
while a cube's request would pass `REQUEST_CELLS_MAX`), the cells of a padded box asked once and kept while the view
stays inside it (no `/cells` request, the fitted breaks kept), fetched 300 ms after a change and aborted; the right
panel a second Preact tree rendered into the aside (never `preact/compat`'s portal); `cellsLayer.ts` the rows on a
`SafeCanvas`, each drawn and divided by its part of its cell (`cellShape`, `cellKm2`: the server's `cut` by `cutKey`,
else the lon/lat rectangle's km², `layerState.ts` `rectKm2`), the partner rows hatched (a canvas pattern) and left out
of the fitted scale, coloured by the density per km² in log classes (fixed `CLASS_BREAKS`, or fitted to the padded
box's 2nd-98th percentile, `quantileBreaks`, eased over `EASE_MS`; tokens `--layer-1..5` of `ui/tokens.css`), the
countries' outlines below `OUTLINE_MPP`; the view and every filter in the hash (`layerState.ts`
`parseState`/`stateParams`: each dimension by its name, `border`; written in place, `ShellC` ignores changes within
`#layer`); "Search here" opens `#new&cell=<id>:<band>:<level>:<i>:<j>`, `NewSearch` with `api.countryRequest` as its
`initial`; demo `?ui=kit-layer`: `ui/Gallery.tsx` `KitLayer`, two canned v2 cubes, `?pick=border` a cut cell);
`FavouritesPage.tsx` the favourites in folders, drag and drop with Pragmatic drag and drop; `Thumb.tsx` Home's mini
maps: an SVG of the run's area and lines over OpenTopoMap's tiles, a few loaded at a time when the card comes into
view, the lines from the run's `lines.arrow` (`load.ts` `loadRunLines`; lines.js for a run listed without a store), a
run of more than `MAX_LINES` lines its box and count only, a failure the card's placeholder),
`result/view/FavouritePicker.tsx` the favourite button's folders; `coverage/` the coverage map: `types.ts`
(coverage.json, the outlines, contrast.json), `data.ts`, `i18n.ts` (`ct` of its own catalogue `locales/coverage/`,
`metres` with the language's decimal sign, `areaName`, `noteText`), `palette.ts` (the colours of the page, the layer
and the canvas), `page/` the page /coverage (flat d3 map, Leaflet, globe; card, legend with three scales, list of the
areas), `draw/` and `media/` the canvas of the animations and images (`media/main.ts`: `window.FAL_MEDIA`; built only
by `node build.mjs --media`, never in dist); `app/coverageLayer.ts` the place map's *Data coverage*; `translator.ts`
the `translator` of both catalogues (so coverage.js holds only its own); `ui/fonts.css` Barlow Condensed (woff2 of
weights 500-700, latin and latin-ext, flat hashed files in dist: `install_viewer` copies dist file by file)

**The result view of mock-up 2** (docs/line-volume/spec-view.md part B, step 3b: built beside today's result page and
opened by `ResultColumns.tsx` only behind a flag, `view/SpotColumns.tsx` `viewWanted`: `?view=b` kept in localStorage
"findaline.view", `?view=today` ends it; a run that cannot be shown, `spots.ts` `viewOf`, opens today's page and the
console says why: also one whose head disagrees with its columns, the sectors' entries, the box of every anchor, the
lengths). `types.ts` `ViewColumns`/`hasView` and `load.ts` `readStore` give the store's `spot`, `top`,
`by_spot` (and the head's `sectors`, `box`, `lengths`) as they are; `ResultModel` built with `ungrouped` groups nothing
(only the filters' ranges). `result/viewgeom.ts` the pure parts (Auto's level with its band, in view as a segment
crossing a four-sided view, the squares on a typed grid and their breaks, a direction, and `gridFit`: the run's grid
from latitudes and longitudes by a polynomial of the lowest degree, 1 to 3, within `FIT_MAX` at the anchors, every
point clamped to the anchors' box and a margin). `result/spots.ts` `SpotView`: which lines pass (the model's filters,
"Top level only" as its own state), each spot's shown line, the order, the sectors, the picks, the lines not beaten,
the spots in view with the best N and their numbers (a view without an area, the map moved off the run, holds
none), the 5 000 limit, the selection, "Lines from here" (derived again only when the numbers its rows could carry
changed: `marksKey`, timed as "fal:view:refan"), one Esc.
`result/SpotMap.ts` the canvas (a Leaflet renderer without paths in a pane of its own: the lines are drawn from the
columns, projected by hand; squares, strokes, numbers placed clear of every control, the presses with a press held and
a right click, the hover; `legend()` what it drew; `drawn()` its own count, each line once). `view/SpotColumns.tsx` the
frame (today's columns and sheet, which opens low and holds from its top the handle, the hint, the head's row and the
body; the Leaflet map with quarter zoom steps, the toast, Esc; `data-choosing` on the map's column while the table of
spots is asked for; `window.FINDALINE_VIEW = {view, map}` once drawn, no `FINDALINE_RESULT`), `view/SpotPanels.tsx` its slots (`PANELS`: the list, the details, the sheet's head, the
hint, the table of spots), `view/MapBar.tsx` the switch, Best, the status line and the legend (a phone: two lines with
a fold, unfolded by itself while the sheet is low and there is room, folded at half or higher; a person's fold or
unfold holds until the sheet's next stop; "Legend" pressed without room lowers the sheet, and where even the low
stop has none opens the legend as a panel above the controls, as the access mark's key opens on a phone: `.v-over`), `view/Shape.tsx` the numbers' shapes for the legend and the rows, `mapbar.css`. Tests:
`tests/test_view_units.py` (Node on a made-up run, the frame in headless Edge through `viewer/test/spotmap_page.ts`),
`tests/test_shell_c_view_map.py` (Playwright on `clip_runs.view_clip`: the mock-up's checks ported).
Its panels (`view.css`, classes `vl-*`; what stands in the slots is `view/SpotDetails.tsx` `SLOTS`):
`view/SpotList.tsx` the list (the top block: "Start here" at Area, else "Best in view" with the B rows and the button
that raises Best, with All "In view"; "All spots": the sort and the tree of sectors, 20 rows a page and 40 more; a
row is a list item with ONE button, `aria-pressed`, one tab stop per list, read from the columns without a Line; the
panels' shared pieces `Cells`, `metres`, `useViewPanels`, `useHover`), `view/SpotSummary.tsx` the headline with
today's `WhyBox`, `view/ViewFilters.tsx` the chips (today's `MainEditor` and `MoreFilters` without the grouping,
"Top level only" and its sentence), `view/SpotDetails.tsx` a spot's details (the stepper, "Stands for", "Lines from
anchor A1 / A2", today's `AccessBlock` and `lineFacts`) and a phone's sheet head, `view/FanPanel.tsx` the panel of
"Lines from here" (the model sorts; "Far end"), `view/SpotChooser.tsx` the table of spots, `view/Hint.tsx` the hint
and its "?" (the frame's two places), `view/viewstate.ts` what is kept (`findaline.view.v1`: the sort and the hint
only) and the panels' state per view (open sectors, pages; it outlives the change between columns and phone). Tests:
`tests/test_view_list_units.py` (Node), `tests/test_shell_c_view_list.py` (Playwright, a desktop and two phones).

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
curve also drawn faintly through the terrain), `walker.ts`/`walk.ts`/`pin.ts` the athlete, its walk and the pin over
it, `views.ts`/`look.ts` the views Orbit, Athlete's eyes and Behind the athlete (the camera's pose from the
athlete's, the gaze dragged or turned by the phone: `DeviceOrientationEvent`, iOS's `requestPermission` inside the
tap; the zoom: Eyes' horizontal angle, 60° by default, from about 110° to ×8, Behind's distance 1.5-30 m),
`edit.ts`/`interact.ts`/`screen.ts` the anchors' editing at level full (a DOM overlay over the canvas, three-mesh-bvh
raycasts, `/api/profile` after a release), `ring.ts`/`ringmath.ts` the coarse ring of terrain (3d-tiles-renderer's
`TerrariumMeshPlugin`, behind `FINDALINE_3D_RING`; it clamps the plugin's private `_maxSourceLevel` of 0.5.3: check it
on an upgrade). Round 2 (2026-11-05; docs/3d-view-contract.md, "Round 2"): `chrome.ts` the activity pill and the tool
strip over the stage (`Scene3D.activity`, `Scene3D.tools`; the tools' ids and order in the contract), the card's slot
under the credits (`Scene3D.card`; opening the card folds the data credits, `Credits.fold`); `pin.ts` the athlete's
pin over the unloaded webbing with a leader (`interact.ts` `pinPlacement`); `profilecard.tsx` the 2D result's
`Profile.tsx` in that card (a second Preact tree by `render` of `preact`), its cursor and the athlete following each
other; `save.ts` the key of the line shown (`canonicalKey`: the 2D result's `keys.lineCoords`; `LineView.key` for a
line taken from outside) and saving it into the favourites; `reach.ts`/`overlay.ts` "Only valid lines" (the reach of
the staying anchor from `/api/reach` as `Scene3D.setOverlay`'s picture, a dragged handle on valid samples only;
`reachLane`: reach and profile requests one at a time); `canopymesh.ts`/`canopy.ts` trees and buildings
(`/api/patch?part=canopy`, a tool only when the patch's meta has `surface`); `others.ts`/`otherlines.ts` the address's
`&also=` lines and the user's other saved lines of the run (a click makes one the active line:
`Edit.setAnchors(anchors, key)`); `options.ts`/`fan.ts`/`optionlist.ts`/`point.ts` the lines from a clicked point (the
point's reach, its representatives the result's spots through `grouping.ts` with the meta's `group_distance`). The
contract of its waves and every decision: docs/3d-view-contract.md; the research: docs/3d-view.md
