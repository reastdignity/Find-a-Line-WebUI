# Code map: the viewer and the 3D view

What the modules of this area hold, in detail: the viewer and the 3D view. Moved out of CLAUDE.md on 2026-11-12;
nothing loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync
and the pitfalls are in `.claude/rules/` (viewer, view3d, browser-tests, coverage-map).

## `viewer/`

The result viewer (TypeScript, Preact, Leaflet; `src/`: `map/main.tsx` a run's `map.html` (bundle `viewer.js`: the
app's result view, `result/view/ResultColumns.tsx`, loading the run's store itself over http(s) (`loadRunFrom("./")`),
`#line=` in its hash, the way back to the app, none on a share link; while the store loads and when it failed (line
volume's round 7, A6) a Back button "Find-a-Line" to "/" (none on a share link) and "Try again" where a new try can
help (`result/view/RunLoading.tsx`: `onRetry`; `more` a share link's visitor's second sentence; `main` the box as the
page's main region); the run's name from the page's `<title>` (`titleName`), which a rename rewrites; the disk notice (store wave 4: `runs.MAP_HTML`'s `#disk-notice`, `NOTICE`,
`map/notice.css`): over http(s) the page is marked `fal-served` by `map/served.ts` (the entry's first import, so a
later module that throws leaves the mark) before the notice is parsed, which hides it, and it is
removed once parsed; from disk a page with the notice shows it (the run's name, `ui.map.disk_notice`, `findaline.py
view <id>`) in the stored theme and loads nothing, one without it (written before) gets the same notice built by the
bundle (`diskNotice`: the id from the folder, the name from `../runs.js` or the title; store wave 4's item 5: no run
is read from disk); the old map with popups and panels was removed on 2026-10-30), `types.ts` the run data's types and
a run's lines as columns (`storedColumns` over a store's own arrays: a `NumberColumn` per value, `NumberColumn.stored`
with Arrow's validity bits, a missing value null or NaN as data.js showed it (`NULL_WHEN_MISSING`); `lineAt` a Line of
a row, `LineCursor` its values without one, `emptyColumns` the model's cursors' start; `LineColumns.profiles` a
`ProfileSource`; `RunInfo.store` run.json's block `store`), `test/rows.ts` the rows of data.js and lines.js as the page
read them before item 5, for the tests only (`toLine`, `lineColumns` with `ColumnBuilder`: the narrowest integers that
give back the very double, else doubles; `runData`; tests/test_viewer.py `test_columns_give_the_rows_values`), which
the Node units bundle through `test/types_rows.ts` and `test/model_rows.ts` (its `ResultModel` reads made-up rows),
`grouping.ts` the grouping (`groupIndices` on typed arrays, `groupLines` over objects: the 3D view's fan, the tests),
`filters.ts` filters and their ranges (`liftMax`/`liftNoZone`: the A-frame needed, on a run with the
options only; `hideNeed*`: the classes of rigging of the head's "Why so many?" box, `needClass`, not kept),
`access.tsx` the access mark of a run made with `--access` (`types.ts` `ACCESS`, `Line.access1`/`access2`: 0 hard
access, 1 cannot tell, 2 easy access, null without): `AccessMark` (a dot of 20 px in the state's colour, tokens
`--acc-*` of `ui/tokens.css`, with its sign, `ACCESS_SIGNS` of `ui/icons.tsx`), `AccessPair` (a list row's two dots;
"–" for a line of a run without the mark), `accessMarkSvg` (the mark of 24 px on the map, in the map's colours),
`AccessKey` and `useAccessHelp` (the one help text of the result page and the search form: a "?", or the kit's info
icon with `icon` as in the result view, that opens a panel
in place, not a bubble); it hides and sorts nothing; `size.ts` a run's size as a person reads it (line volume's
round 7: `sizeText` Home's card, "2.1 MB", "under 0.1 MB", "" for none; `downloadSizes` the loading line's two
numbers in the total's unit and cut, two decimals for a total under 50 000 bytes; a MB 10^6 bytes; `RunLoading.tsx`
`loadingText`, the card's lines in `app/c/Home.tsx`, the size `api.ts` `RunListed.bytes` from `/api/runs`); `tight.ts`
the tight mark (`TIGHT` = 1 m, `clearanceText` rounds a tight clearance down, the mark's words with and without A-frames), `endzone.ts` the zone's TypeScript twin of `helpers.zone_steps` and the chart's limit with the zone and
the lift (`limits`, `riggingNeed`, `liftChoices`), `labels.ts` the chart's label layout (`layoutLabels`: no two boxes
intersect, priority anchors > min clearance > A-frame > zone > highest, a label that does not fit is dropped),
`profilechart.ts` the chart's geometry, `Profile.tsx` the chart (the A-frame posts, the zone bands, the pill of the
rigging need; its text `TEXT_PX`, 12 px, and its labels laid out with `LABEL_BOXES`, the glyphs' cells at that size
with 2 px of pad, through `profilechart.ts` `chartLabels`' `options`; `needBelow`: the need row under the chart, for
a compact dock), `list.ts` the sortable list of lines (kept under `findaline.list.v2`, mean height first), `leaflet.ts` Leaflet's CSS and marker images for both bundles,
`layers.ts` the data credits and Esri's tile URL (no Leaflet: the 3D view imports it too), `baselayers.ts` the base
layers, `keys.ts` keys of lines, `favourites.ts` favourites, their folders' requests and their export, `folders.ts`
the folder tree, `shore.ts` the uncertain shore's pure parts (`segmentBox`, `metresInView`, `SHORE_COLOURS`) and
`shoreLayer.ts` its Leaflet overlay (in the layer control of `result/view/ResultColumns.tsx`, on by default) and the
control `.u-shore` at the map's top left: a legend of the two kinds with the metres of each in view and the kit's
info icon opening `ui.shore.help` (`helpButton`, shared with the coarser box; its `INFO_ICON` is a copy of
`ui/icons.tsx` `ICONS.info`, as this file is also bundled without the logo's `.svg` loader in a test page), shown only
while the view holds some (`addShore`); on the phone layout (under 768 px) it starts
folded into a one-line chip (`.u-shore-ctl`: the kinds in view and `shoreTotal`) that unfolds into the box, whose
text then scrolls within the map; `coarser.ts` the pure parts of a run's
`terrain_sources` (where its land's terrain came from: `km2InView`, `warns` from `FALLBACK_WARN_SHARE` =
`search.FALLBACK_WARN_SHARE`, `sharesText`) and `coarserLayer.ts` the "Coarser terrain" overlay (the fallbacks'
regions hatched by an SVG pattern of their renderer, colour `--coarse-map`) with its box `.u-coarse` under the
shore's (each fallback's km² in view, `ui.coarse.help`; `addCoarser`, whose `fit` is `ResultModel.coarserFit`, the
"Show on map" of `ResultSummary`'s `CoarserNote`; under 768 px folded at first into a chip like the shore's,
`coarserControl`, with the shore's classes `.u-shore-ctl` and `.u-coarse-ctl`: docs/DESIGN.md row 105), the shares
under More filters (`FilterBar`)), `layersControl.ts` the maps' layers control (Leaflet's `L.Control.Layers` with the
kit's "layers" icon, `options.afterUpdate` after every redraw of its rows, an opened box fitted above the map's
credits; a disclosure for the keyboard, its rows the kit's boxes `.u-check`/`.u-radio`, a finger's second tap guarded
for `OPEN_GUARD_MS`; `pressMarks`: the map's own ring only after a key: docs/DESIGN.md rows 132, 136), used by the place map (`app/PlaceMap.ts`) and the result view's frame (`result/view/SpotColumns.tsx`); a
module of its own so that the result view's bundles (map.html's `viewer.js` too) take it without `PlaceMap.ts`'
Leaflet-Geoman; bundled by esbuild into `dist/` (committed);
copied to `runs/_viewer/` by every run. The app (`app/app.tsx`: the app's one interface, C (`app/c`); B and D were
removed on 2026-11-04, so `?ui=` chooses only the kits and a stale `b` or `d` gives C, `ui/choice.ts`; "Copy link"
gives no `?ui=`; the old app with tabs was removed on 2026-10-30; docs/roadmap.md, "UI prototypes B, C and D"): `ui/`
tokens (`tokens.css`: the colours, the type and radius steps, the layers `--z-*` and elevation `--shadow*`, which the
free CSS names: docs/DESIGN.md rows 87 to 91; `ui.css` the kit's look, a legend's `.u-legend-*` among it: row 90; one
control family: a text action `.u-link`, a row `.u-item`, a close `.u-ib.u-x` (`components.tsx` `CloseButton`; the 3D view's plain DOM the same classes by hand), a badge,
the checkbox `.u-check`, the collapse tab: rows 96 to 99),
icons and components under a `.ui` root (`components.tsx` `Splitter`: a draggable, focusable separator,
WAI-ARIA's window splitter, our own (react-resizable-panels would need preact/compat, split.js is unmaintained);
`Sheet` the phones' bottom sheet (peek, half, full); `SidePanel.tsx` a side panel beside a map (its edge, collapse tab
and rail, `useWidthOf`; `sidepanel.css`: the result's and the highline layer's); no Rail, Toast or Tabs since B went;
`Hint.tsx` the "?" of a field and its bubble, the site's bounds added by `search/SearchPanel.tsx` from
`hint.bounds.*`; `Intro.tsx` an intro dialog shown once per browser (localStorage `findaline.intro.<name>`,
`IntroLink` opens it again), or only from its link (`useIntro(name, false)`: the search's, step 3d G5);
`radios.ts` the keys of a radio group (WAI-ARIA's: one Tab stop, the arrows move and choose; no Preact, so the
3D view's switches use it too); `choice.ts` the switch, `bars.ts` the browser's bars (line volume's round 7:
`themeBars`, the head's two `theme-color` lines in the ground of the theme a page shows, "auto" their own values
back; `Screen`, the coverage page and the disk notice call it), `Gallery.tsx` `?ui=kit`; `pages.css` the server-rendered sign-in,
privacy and about pages of `web.py`; `logo/` the logo: `logo.svg` and `mark.svg` coloured by classes of `ui.css`
(`Logo`/`LogoMark` in `icons.tsx` bundle them as text), `logo.svg` and `favicon.svg` copied to `dist/` by `build.mjs`
(`web.LOGO_SVG` reads `dist/logo.svg`; the standalone files in `docs/logo/`); since line volume's round 7 `build.mjs`
also copies the home-screen icons `viewer/home-screen/*.png` (`tools/home_screen_icons.py`; beside `src/`, as tests
read every file under it as text) and writes `dist/manifest.webmanifest` itself (`homeScreenManifest`: "Find-a-Line",
standalone, portrait, from "/", the light `--bg` of `tokens.css` its one colour; written, not copied, so the
checkout's line endings never reach dist)), `result/` a run in the app (`load.ts`
`loadRun`/`loadRunFrom` a run by its folder (store wave 4's item 5: its store only, over http(s); no data.js, no
script tag): `lines.arrow` and `profiles.arrow` downloaded by `download.ts` (XMLHttpRequest: its progress counts the
decoded bytes, against `SIZE_HEADER` = `web.SIZE_HEADER`, which `web.RunFiles` sets: nginx's gzip drops Content-Length;
the 3D view's patch too; a store cut while the page was hidden, as iOS does when the screen goes off, is fetched again
whole once the page is visible, `watchHidden` and `whenVisible`, one try a visible spell, the other file's request
ended at the cut through an `AbortSignal`, the try after a cut ended as `StoreFailed` after `STALL_MS` of visible time
without a byte, and started once `navigator.onLine` or after `ONLINE_WAIT_MS`: today's page, map.html, Compare and the
mini maps share it, `tests/test_store_retry.py`); `LoadProgress` to `RunLoading.tsx` (the phases and a bar; `model.ts buildModel` builds the
model after a paint, `paint.ts nextPaint`); the store named by the run's entry in runs.js (`storeOf`: the page's list,
else `../runs.js` beside the run's folder, loaded once; a run it does not name or names without the block, and a share
link, get `STORE_PROBE`: the store's files asked for directly; docs/line-volume/spec-store.md 1.2): `readStore`
(apache-arrow `RecordBatchReader`: one record batch; the head from the schema's metadata `findaline`, `parseLoose` for
its NaN; the columns views of the downloaded bytes, int64/uint64 ones copied into doubles; a higher `format` than
`STORE_FORMAT` refused as `NewerStore`, `ui.result.newer_store`; a file not fetched (a 404: a run without a store)
or not readable is `StoreFailed`, `ui.result.store_failed`; a null body `TooLarge`, `ui.result.too_large`;
`failureOf` the failed page's sentence and whether a new try can help: not for `NewerStore` or `TooLarge`), the name the list of
runs gives over the store's head (`fromServer` with `listedOf`: a rename changes run.json's name, never the head's;
`renamedRun` puts a new name into a loaded run, and with `forgetRunList` the list is read again by its next reader,
Compare among them: a search's end, a rename and a delete on the page call it),
`storedProfiles` a profile made when it is asked for; `loadOtherRun` Compare's other run (`RunActions`) from its
`lines.arrow` alone, `loadRunLines` a mini map's (`app/c/Thumb.tsx`) the same way, and a run the list does not name by
its `lines.arrow` asked for directly (`STORE_PROBE`'s rule); a run read from its store carries `RunData.fromStore`, by
which `view/RunActions.tsx` `mayExport` (with `api.canChange`: the page has the token,
the app's page, never a map.html) gives Download's two rows that ask the worker for the file (`Export`:
`api.exportRun`, "Preparing the file…" in the pressed row, the ring on the button while the menu is closed, the
browser saves the answered address, this run's export only, by a link's click, a failure one red line by the answer's code; the wait and the line kept per run id outside the component, so a layout switch or a run change keeps them); a run with
a store has no Download where the page may not ask; `orthoForApp` its orthophoto's cache for the app's page; `model.ts` `ResultModel`: filters → groups → rows,
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
nothing kept from there; its `onClose` goes to the dock, so a given line's close can be the view's
`model.closeProfile`; `ProfileDock`'s `compact`, default off, is the result view's phone docks' form: no head row, the
close at the bar's end, the legend and the 1:1 scale under "Rigging and layers", the need row and the words on
reading the chart under it, `.r-hint-under`; today's page never gives it; `ProfileDock`/`ProfileCard` type their map as
`ProfileMap`, `hoverAt`, `RunActions` as `RunActionsMap`, Measure's mode and points and Compare's `areaBounds`, and
`ResultMap` satisfies both; `RunActions`' `tip`, below: today's page, beside: the view's header, none: the view's
phone, with `useMeasureTip`, and `plain`, the icons without a box for the view's pill; Measure numbers each start and
cancel per run's model and reads the frame's `selections`, so an answer of an older measurement, or one after a new
selection, is dropped), the corners above the card only where it covers them (`corners.ts` `useCornersAboveCard`;
with `onCredits` the attribution stays at the map's bottom, the view's card standing on it, and only the scale goes
above the card),
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
bottom navigation; hash routes in `route.ts`; `ResultPage.tsx` wraps `result/view/ResultColumns.tsx`; `Home.tsx` the
runs' cards, a card's menu (since line volume's round 7 "Rename…" after "Share…" for the owner on the public site,
opening a panel under the card with `result/view/RunRename.tsx` `RenameForm`; the menu scrolled into view above a
phone's bottom bar); `NewSearch.tsx`
the search (it waits for the saved rigs: a request to edit opens Basic or Advanced by them), whose panel
`search/SearchPanel.tsx` has one layout since its variant of B went (the demo `?ui=kit-search` shows it); `AdminC.tsx`, `OsmC.tsx` the admin and OSM pages; `LayerPage.tsx` the highline layer (`#layer`; the local
app and administrators, from the account menu; `MapPage` with an `aside`: two side panels as the result's
(`ui/SidePanel.tsx`; `layout.ts` `fitPanels` with `LAYER_LIMITS`: left 320-560 px, right 300-640, the map at least
360, the defaults 340 and 485; kept under `findaline.layer.layout`, version 2, a version 1 value's old default widths read as the defaults), each one's content in a scroll box, the rails' labels from the page
(`MapPageExtras`), a panel's change restarting the automatic level; phones one scrolling column, no edges, the map sticky at its top on a screen 600 px high or more; on the left
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
content holds two of 210 px, a container query on its scroll box, the length chart across both; a chart with 32 px or more of its width per bar shows the bars' counts and every tick, a narrower one no counts and every other tick (`data-bars`, a container rule per count of bars in `c.css`); the ticks the bare values a pick sets, the chart's title with the word they need (`chartTitle`: "(at least)", "(under)", "(up to)"), the filters' and chips' limits in words (`limitWords`, `ui.layer.limit.*`: step 3d G5); the chart of the filter changed last ringed and
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
view, the lines from the run's `lines.arrow` (`load.ts` `loadRunLines`), a
run of more than `MAX_LINES` lines its box and count only, a failure the card's placeholder),
`result/view/FavouritePicker.tsx` the favourite button's folders; `coverage/` the coverage map: `types.ts`
(coverage.json, the outlines, contrast.json), `data.ts`, `i18n.ts` (`ct` of its own catalogue `locales/coverage/`,
`metres` with the language's decimal sign, `areaName`, `noteText`), `palette.ts` (the colours of the page, the layer
and the canvas), `page/` the page /coverage (flat d3 map, Leaflet, globe; card, legend with three scales and drawn stars, list of the
areas: a table, on a phone one row per area with the card as a sheet over the list, which keeps its place, and a
header that scrolls away; a row too for a country covered only in some regions), `draw/` and `media/` the canvas of the animations and images (`media/main.ts`: `window.FAL_MEDIA`; built only
by `node build.mjs --media`, never in dist); `app/coverageLayer.ts` the place map's *Data coverage* (a box of its own with a button on a desktop, a row of the layers' box on a phone: `place`; on while its group is on the map, remembered but for the map's own removal); `app/PlaceMap.ts` the app's place map (the search page, the OSM page, the highline layer's page) with two arrangements of its controls by the media query `PHONE` (a desktop or tablet: zoom, layers and the coverage's box at one corner; a phone: zoom across at the top left, the layers' button at the top right, its box closed, the drawing tools in a row beside the zoom), their look from `result/view/mapbar.css` (`.c-placemap`); tests `tests/test_shell_c_search_page.py`; `translator.ts`
the `translator` of both catalogues (coverage.js carries the app's too: `ui/components.tsx` imports `ui/Hint.tsx`,
which reads `i18n.ts`); `i18n.ts` the app's `t`, `label` and `parts` (a text with an icon, a link or a value as a part
of its own; the words of the files `tests/test_texts_in_catalogue.py` names come from `locales/en.json`, the result
view's files and the parts of today's page it borrows among them since step 3d G6, while today's result page's own
components and the kit's demo pages still hold English in code: known-bugs.md);
`ui/fonts.css` Barlow Condensed (woff2 of
weights 500-700, latin and latin-ext, flat hashed files in dist: `install_viewer` copies dist file by file)

**The result view of mock-up 2** (docs/line-volume/spec-view.md part B: step 3b built it beside today's result page,
step 3c joined today's features, step 3d ported today's checks; a run's page by default since line volume's round 6,
2026-11-22). Which page a run opens is `view/SpotColumns.tsx` `VIEW_DEFAULT` (true) and `viewWanted(byDefault)`:
`?view=b` asks for the view and `?view=today` for today's page, and localStorage "findaline.view" keeps only an answer
other than the default ("today" now) and forgets one equal to it; a run that cannot be shown, `spots.ts` `viewOf`,
opens today's page whatever the default, and the console says why: also one whose head disagrees with its columns,
the sectors' entries, the box of every anchor, the lengths. `types.ts` `ViewColumns`/`hasView` and `load.ts`
`readStore` give the store's `spot`, `top`, `by_spot` (and the head's `sectors`, `box`, `lengths`) as they are;
`ResultModel` built with `ungrouped` groups nothing (only the filters' ranges). `result/viewgeom.ts` the pure parts
(Auto's level with its band, in view as a segment crossing a four-sided view, the squares on a typed grid and their
breaks, a direction, and `gridFit`: the run's grid from latitudes and longitudes by a polynomial of the lowest degree,
1 to 3, within `FIT_MAX` at the anchors, every point clamped to the anchors' box and a margin). `result/spots.ts`
`SpotView`: which lines pass (the model's filters, "Top level only" as its own state; `topOnlyHides`, a link's line
that only the chip hides), each spot's shown line, the order (with `desc`, the tree's direction), the sectors, the
picks, the lines not beaten, the spots in view with the best N and their numbers (a view without an area, the map
moved off the run, holds none), the 5 000 limit, the selection, "Lines from here" (derived again only when the numbers
its rows could carry changed: `marksKey`, timed as "fal:view:refan"), one Esc; `isFavourite` (a spot's shown line),
the closed profile through the model (`profileClosed`, `closeProfile`, `showProfile`; a selection and a step open it
again). `result/SpotMap.ts` the canvas (a Leaflet renderer without paths in a pane of its own: the lines are drawn
from the columns, projected by hand; squares, strokes, numbers placed clear of every control, the presses with a press
held and a right click, the hover; `legend()` what it drew; `drawn()` its own count, each line once, and the values
with their boxes, moved or left out; `valueAt` where a square's value goes at Area: the square's middle, else the
first clear place of eight inside it, else left out, clear of the controls and of the picks' numbers, found before
the squares are drawn; numbers left out nearer than `APART_MIN`, a third of a box, the fan's too; step 3c: the
search area's outline, the favourites' gold halo, Compare's other runs, one line per spot where the other run has the
view's columns, else every passing line, in a kept layer, by `ResultModel.runColumns`, and Measure: the members of
`RunActionsMap`, `drawMeasured`, `zoomToLine`, the measured line's points in the dashes' clip under the numbers;
`setCovered(px)` takes the desktop card's part out of "in view"; Esc while measuring is taken before the frame's
`useEscape`; `hoverAt` draws nothing for the point already shown; the legend's `fav`, `area`, `measure`, `ends` and
`runs`; nothing of today's features is pressable or counted in the view).

`view/SpotColumns.tsx` the frame (today's columns and sheet, which opens low and holds from its top the handle, the
hint, the head's row and the body; the Leaflet map with quarter zoom steps, the zoom's icons, the layers button
(`layersControl.ts`), a phone's scale at the bottom right, the toast (a desktop's; a phone's message is MapBar's
`message`), Esc; `data-choosing` on the map's column while the table of spots is asked for; `window.FINDALINE_VIEW =
{view, map}` once drawn, no `FINDALINE_RESULT`). Step 3c's parts: the run's actions (`RunActions`: in the header
after the caller's, Measure's tip beside "Cancel"; a phone's pill, plain icons, no Compare, the tip as the status
line's first line; `useOwnRun` the run as the user's list has it when it is their own on the public site, one
request for Share and Rename; Compare says why a run cannot be shown, `CAUSE_TEXT`, its box `u-off`, kept in the Tab
order with `aria-disabled` while it holds the focus, and makes its rows anew only once the list was read again:
line volume's round 7); the run's name in the desktop header's Title with the Rename button after it for its owner
(round 7: `RunRename.tsx` `RunRename`, the view's `Popover` (`common.tsx`) with `RenameForm`: `storedForm` and `nothingToSave` judge
a name as the server would store it, `answeredName` takes the server's, `renameFailure` a failure's line: "in use" for
a 409, else the request's own words, else `FAILED_TEXT`, "The run was not renamed. Try again in a moment."); the profile's card over the desktop map (`ProfileCard`: the selected line's until
`model.closeProfile`, or the measured line's; it stands on the credits' line, `--v-card-bottom`; its height goes to the
canvas's `setCovered`; MapBar's short foot while it is open; a desktop's `padding()` counts the card ahead,
`cardHeightAhead`, and the short foot above it, `shortFoot`; `keepFree` fits the selected line only where an anchor
lies under the card); the measured line (Measure's or a link's, kept across the phone's width, drawn by
`drawMeasured`, fitted by `zoomToLine`: a link's always, Measure's where it is not in sight; first in a phone's sheet
at half, a compact dock; fitted, and a phone's sheet raised to half, once per line in the frame that shows it first,
`useMeasuredShown`, `firstShow`); `useNewSelections` counts the new selections for RunActions' `selections`; the
sheet low while measuring. Every move of the map goes into the bar's room (the canvas's own, a selection's fit, a
measured line's fit, the sheet's room); a selected line's fit (viewlink's `showRow`, the panels' `PanelProps.padding`,
`keepFree`) is checked at the next microtask (`selectedFit`) and `endsClear` brings an end that lies under a control
clear, only for a strictly better state and never shorter than `LINE_LEAST`, 120 px; on a phone a selected or measured
line with no end clear in the bar's room gets one by the least pan at the same zoom (`oneEndInView`, `clearingPan`;
never a zoom), made once more at the next frame where the controls answered the pan; the map column's
`data-measured-rests` and `data-measured-fits` count a phone's rests. On a phone `useSheetKeeps` brings back a selected
line (or a shown measured line) that the sheet covers when its stop changes: the least pan at the same zoom, never
after the person moved the map, nothing at full; the sheet counts as at rest only once the credits' corner
(`corners.ts`) stands above it; a check of a stop already left does nothing; `useNoteAfterCrossing` raises a phone's
sheet for a link's measurement that fails after the window crossed the phone's width. P3: a selection made at full
drops the sheet to half (`drop`: until it rests, `bar()` and the canvas's `free()` count the sheet at half and the
fit's ends check waits for the rest); at full the list keeps the in-view set of the last stop below full. Gate 2:
`Upright`, the notice over the page on a touch phone held sideways (`SIDEWAYS`; the frame behind it inert, the focus
back after it); `useNoPageZoom` (with the frame's `touch-action`: no page zoom outside the map); the layers menu opened
by a press drops a raised sheet to its low stop (`useLayersLowerTheSheet`). `view/viewlink.ts` a line's link in the
view (`#line=`), as today's `useLinkedLine` on the view's selection: a passing line of the run is selected in its
spot and put in view; a line that "Top level only" alone hides turns the chip off (`SpotView.topOnlyHides`); a line
other filters hide gets today's note with "clear filters"; a line not among the run's goes through `model.openLinked`
(measured where the page may ask profiles); the notes' words are the catalogue's (`ui.link.*`); a link that ends in a
note raises a phone's sheet to half (`onNote`); the selection goes into the hash by `history.replaceState`; the route
is opened once per (line, nav) and view. `view/SpotPanels.tsx` its slots (`PANELS`: the list, the details, the sheet's
head, the hint, the table of spots, the selected line's actions `lineActions`; `PanelProps` also carries the caller's
`linkOf` and `view3dOf` and the frame's `measured` line; a new slot is optional), `view/MapBar.tsx` the switch, Best,
the status line and the legend (a phone, the pilot's arrangement: from the bottom up beside the scale the row of
"Legend", the map's "i" and the hint's button, the legend, the status line holding the map's message; where the map is
too low for that column, `inline`, the status line beside the row; the legend two lines with a fold, unfolded by
itself while the sheet is low and there is room, folded at half or higher; a person's fold or unfold holds until the
sheet's next stop; "Legend" pressed without room lowers the sheet, and where even the low stop has none opens the
legend as a panel above the controls: `.v-over`; one "i" for the map, `useMapHelp`: a desktop's at the switch's end,
`HelpAll`, both texts under the switch, a phone's in the foot's row, `HelpParts`, "Auto, Area, Spots, Lines", "Best"
and "Anchors" in a marked run, one open at a time, opening on "Anchors", closed by `HelpClose`, its "i" or Esc, the
focus back on the "i", a phone's closing at the sheet's full stop; the legend's rows of what the canvas draws besides
the spots, `LegendItems`, `FavSign`, and the access rows only with `shapes.ends`; `short`, the card open; `tip`, a
phone's measuring tip; the status "No line passes the filters." while no line passes; a legend shown or folded
refreshes the canvas at once), `view/Shape.tsx` the numbers' shapes for the legend and the rows, `mapbar.css` (also
the look of Leaflet's own controls on the app's place map: its selectors name `.c-placemap` beside the view's map; the
upright notice, the pill's menus, the 2D credits pill).

Its panels (`view.css`, classes `vl-*`; what stands in the slots is `view/SpotDetails.tsx` `SLOTS`):
`view/SpotList.tsx` the list (the model's note first, `ListNote`, in the mock-up's look with today's ×; the top block:
"Start here" at Area, else "Best in view" with the B rows and the button that raises Best, with All "In view"; "All
spots": the sort, its direction beside it ("Largest first" / "Smallest first", the tree only: "Best in view" and the B
numbers stay best first), and the tree of sectors, 20 rows a page and 40 more; the tree's heads are buttons that sort
it, `SortHead`, a second press reverses, the pressed head kept in its place, and stick to the list's top with their
block; a row is a list item with ONE button, `aria-pressed`, one tab stop per list, read from the columns without a
Line; a row's star, `RowStar`, is the row button's sibling with tabIndex -1, reached through `rowKeys` by ArrowRight,
named with its row's label, and opens the details' folder picker in its place, `RowPicker`, made whole in the list;
"No line passes the filters." with "Clear all"; the list's two help buttons, the kit's info icon, opening their text
in place; the panels' shared pieces `Cells`, `metres`, `useViewPanels`, `useHover`), `view/SpotSummary.tsx` the
headline with today's `WhyBox`, `view/ViewFilters.tsx` the chips (today's `MainEditor` and `MoreFilters` without the
grouping, "Top level only" and its sentence, none while no line passes), `view/SpotDetails.tsx` a spot's details (the
spot's head: the title, the star, "Previous spot" / "Next spot", the tree's spots top to bottom, `treeSpots`,
`stepSpot`, and ×; the four tiles, a tight line's in the warning colour with "Tight", "Reaching the anchors" with A1
and A2, the stepper, "Stands for", "Lines from anchor A1 / A2", the facts as a table, `viewFacts`; today's page keeps
`AccessBlock` and `lineFacts`) and a phone's sheet head, `view/SpotActions.tsx` the selected line's own controls (the
head's star, `LineStar`, with today's picker, `FavouritePicker`; "3D view" with the spot's passing lines as `&also=`;
Copy link; Profile once closed; "Report this line" below the facts; a phone's dock under the four values, `LineDock`,
ProfileDock `compact`; today's words, LineDetails' and LinesTable's; it imports `report.ts`, which reads the page at
load, so the panels' Node bundle leaves it out, as it leaves SpotDetails), `view/FanPanel.tsx` the panel of "Lines
from here" (the model sorts; "Far end"), `view/SpotChooser.tsx` the table of spots, `view/Hint.tsx` the hint and its
button (the kit's "rope" icon; the frame's two places), `view/viewstate.ts` what is kept (`findaline.view.v1`: the
sort, its direction (optional, `desc`, written only when not the key's first: `FIRST_DESC`) and the hint only; the
view also reads and writes today's `findaline.lastFolder`, the folder a new favourite goes to) and the panels' state
per view (open sectors, pages; it outlives the change between columns and phone).

Tests: `tests/test_view_units.py` (Node on a made-up run, the frame in headless Edge through
`viewer/test/spotmap_page.ts`), `tests/test_view_list_units.py` (Node), `tests/test_shell_c_view_map.py` and
`tests/test_shell_c_view_list.py` (Playwright on `clip_runs.view_clip`, a desktop and two phones: the mock-up's checks
ported); step 3c: `tests/test_view_seams.py` (the frame's seams as step 3c fills them: the run's actions, the card,
the details' slots, and main's elements around them; today's page keeps its actions, card and dock), `test_view_values.py` (a square's values,
the numbers' rule and its copy), `test_access_view.py` (the access mark's parts in the view, the boxes' info icon),
`test_view_link.py` (links, the sheet's moves), `test_view_numbers.py` (`tools/view_numbers.py`), `test_view_map_3c.py`
(the canvas's outline, halo, other runs, measurement, what is in view under the sheet), `test_view_details.py` (the
details and the list's controls), `test_view_frame.py` (the run's actions, the card, the measured line, the fits and
the one-end pan, the narrow lists), `test_view_actions_public.py` (the actions on the public site),
`test_view3d_profile_sizes.py` (the profile's 12 px and 44 px on the 3D card); step 3d: `tests/test_view_parity.py`
(today's result page's checks made again of the view where no view test made them, in seven walks: the desktop's
header and map, its kept layout, a narrow and low window, a line's details and profile, the filters, a phone's frame,
the loading's failures with the flag; each assertion names its row id of the planner's parity list, kept outside the
repository), `test_view_parity_pages.py`
(today's checks of the pages around a result: Download, the access list's kept widths, a run's own map.html, a share
link's page, the public site's people; today's side opened by `?view=today`; each assertion names its row),
`test_view_default.py` (both settings of `VIEW_DEFAULT`, built by esbuild with a plugin, served by Playwright routes),
`test_view_gaps.py` (wave C's gaps P1, P3, P4, the final design check's fixes and gate 2's answers),
`test_view_gate2.py` (the 3D view's other lines pass the filters, WebKit's CSP refusals, one map draw a step),
`test_view_scroll_layer.py` (the scrollers' layer and the rows that hold their hidden names), `test_store_retry.py`,
`test_view3d_press.py` (the 3D view after a long press).

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
raycasts, `/api/profile` after a release; the bar held by `holdBar`/`releaseBar` while handles are dragged and until
the profile answers), `ring.ts`/`ringmath.ts` the coarse ring of terrain (3d-tiles-renderer's
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
point's reach, its representatives the result's spots through `grouping.ts` with the meta's `group_distance`). Step
3c, group B (2026-11-19; docs/DESIGN.md rows 40 to 49): `icon.ts` the kit's icons for the plain DOM (`kitIcon`: the
notice's dismiss, the sorted head, a favourite's star); `screen.ts` `pressedMark`/`nearestMark`, the mark a press goes to
(the mark whose drawn box holds it; else the nearest centre of the marks whose invisible targets, 44 px on a touch
screen, hold it: the fan's dots, the labels), `targetInside` (a mark's target kept inside the stage: the fan's dots, the anchors' handles, the other lines' labels, by their half-sizes and how far a target may move) and `draggable`'s
`fromCentre` (a handle's drag keeps the press's offset). The
phone's layout (rows 37 to 39): `chrome.ts` `stepAside`, the profile card's slot right of the tool strip where the
card would reach it; `info.ts` the phone's "About this view" button and its box of the bar's notes (the credits'
box hidden where the open box would overlap it); the one-row bar of a phone held sideways and a touch tablet is
`chrome.ts` `oneRow` (the class `v3-row`, the one place of its condition) and its rules in `view3d.css`
(`tests/test_view3d_layout.py`). Gate 2 of line volume's round 6 (2026-11-22): the stage (canvas, overlay, labels,
card) selects no text and shows no iOS callout (`view3d.css` `.v3-stage`), and a press on it ends a selection left
anywhere and takes the focus from a control outside the stage (`views.ts`), so a long press no longer leaves the view
deaf to gestures (`tests/test_view3d_press.py`). The
contract of its waves and every decision: docs/3d-view-contract.md; the research: docs/3d-view.md
