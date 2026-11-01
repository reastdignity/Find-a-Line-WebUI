# 3D view of a line

Research of 2026-11-01 for a Google-Earth-like 3D view of one selected line: the webbing drawn with its sag over the
terrain, a walker on it, and anchors the user can drag. Nothing is built yet; this report is the basis for the
decision. It lives on branch `line-3d-view` (from `main` 983d148) and is not merged into `main` until the work on the
idea ends. Code references point to that commit.

The terms of the services were read on 2026-11-01; the deciding sentences are quoted in the appendix with their
URLs. This is a reading of the terms and the law, not legal advice: where the text leaves a question open, the
report says so and names whom to ask. Costs of implementing are given as Claude effort (low, medium, high), money
only for the services.

## Summary
The mock (an orange sagging line and a mannequin over the photorealistic cliffs of Dolina Bolechowicka) can be
built, but not with Google's 3D tiles: since 8 July 2025 Google refuses Photorealistic 3D Tiles to projects with an
EEA billing address. Four variants remain.

| | Variant | What you see | Works in | Money a month at ≤ 1000 opens | Hard stop | Effort | Legal load | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | **KML + links**: "Open in Google Earth" | Google's own 3D (mesh where Google has one), the line and the walker's spot | Google Earth Web/Pro, any site or app; no editing | 0 | not needed | low | very light | **do first** |
| B | **Our own data**: the run's DEM around the line + our orthophoto, in our 3D page | exact heights (1 m, 0.5 m in CH), orthophoto draped: cliff walls smeared | public site and local app, no key | 0 outside; about 3 GB a month from our server | not needed | high | light | **the embedded view** |
| C | **Esri**: Terrain 3D + World Imagery, in the same 3D page | national orthophoto on Esri's ~1.5 m ground | public site (operator key); local app only with the user's key | 0 within 2M tiles (shared with the 2D satellite layer) | yes (pay-as-you-go off) | low–medium on top of B | medium (terms to pass on) | **add-on to B** |
| D | **Google 3D Maps** (`Map3DElement`) | Google's photorealistic mesh where it exists, satellite on terrain elsewhere | public site (operator key); local app only with the user's own billed key | 0 within 5,000 loads (card on file) | yes (per-day quota) | high | heavy (consent gate, terms page, high-risk clause) | **optional, later** |

Out at the first gate: Google's Map Tiles API 3D tiles (EEA block), Cesium ion's free plan (no third-party access,
no hard stop), Mapbox (no cap), MapTiler (non-commercial plan, 30 m terrain), Azure, Apple, HERE, Stadia, Bing,
Sentinel-2, Esri's resold Google 3D (internal use only). Details: [Gates](#gates).

**Recommendation.**
1. **A first** (low effort): a KML of the line (the sag curve at absolute heights, both anchors, the walker's spot,
   the credits) and links to Google Earth, to swisstopo's 3D viewer for Swiss lines and to Google Maps' satellite
   view on phones. It shows exactly the Google look of the mock, today, at no cost, with no key, consent or terms
   page. It cannot edit anchors or animate the walker, and it leaves our app.
2. **B, with C as an add-on**, as the 3D view inside the app: it meets every requirement (editing, walker, public
   site and local app, hard stop, no new account) and keeps the line on the very heights the search used. Drawn
   with three.js it runs under the site's current CSP unchanged (measured) and costs about 3 MB per open from our
   server; CesiumJS instead only if the view must show the far field (see [Rendering library](#rendering-library)).
3. **D only later and only if** the coverage check below shows Google's mesh at typical spots, the site gets a terms
   page and a consent gate, and Google answers the "High Risk Activities" question. It cannot share B's renderer:
   it would be a second 3D implementation.

**Decisions for the user.**
1. The variants and their order (above).
2. The rendering library for B/C, decided by one question: must the view show the far field (horizon, valleys
   around), as Google Earth does? Yes: CesiumJS (a relaxed CSP on its page, about 1.3 MB of code). A patch of about
   1.5 km with a coarse ring is enough: three.js (no CSP change, about 0.2 MB).
3. Where the orthophoto of the patch comes from: our server fills its cache (the services' limits apply to us) or the
   browser loads it from the services (they see the IP, as the 2D map already says).
4. The mesh: built in the browser (`@mapbox/martini`, unchanged since 2020) or on the server.
5. A terms page for the site (needed by D, and the solid way to bind users to Esri's terms for C), its wording.
6. The privacy-page sentences proposed in [Privacy](#privacy-sentences-for-approval) (not applied).
7. Questions to providers: Google (high-risk), Esri (Terrain 3D from a non-Esri renderer, heights while dragging),
   Fathom (donations and FABDEM), GUGiK (the legal basis of NMPT).
8. The local app: a provider's 3D only with the user's own key (a setting), or our own data only.
9. Which phone level to aim for, and who tests on an iPhone of the 11/SE class under iOS 18.

## What was asked and agreed
Fixed with the user on 2026-11-01:
- The view of a found line **plus anchor editing**: while an anchor is dragged, length and sag are computed live in
  the browser; on release the server computes the profile from our DEM like *Measure*. The edit is not saved.
- **The walker** starts at the lowest point, can be dragged along the line, and can walk from anchor to anchor.
- A "3D" button among the line's actions opens a full-window view with a way back. The first version shows the
  sagging line, the walker and the editing (not the mock's values panel, webbing length or height inputs, minimap,
  compass or readout).
- **Where**: the public site (signed-in users) and the local app; not share links, not `map.html` from disk.
- **Fidelity**: compare a photorealistic mesh with our orthophoto draped on our DEM.
- **Budget**: a free tier with a **hard stop** (a card on file is fine, a bill is not); up to 1000 opens a month.
- **Commercial**: non-commercial now; also what accepting donations would change.
- **Accounts**: only the ArcGIS Location Platform account of the satellite layer.
- **Phones**: three levels examined: full, simplified (view only), desktop only.
- Extra points: KML and Google Earth, height alignment, privacy and CSP, size and performance.

## Gates
Checked in the order that eliminates cheapest: availability in the EEA, a hard stop without bills, the plan's
permitted use (non-commercial, donations), keys, then the terms that shape the design.

| Service | EEA | Hard stop | Permitted use, donations | Key in the browser, local app | Terms that shape the design | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Google Map Tiles API, Photorealistic 3D Tiles | "Photorealistic 3D tiles are not available." (403 for new EEA projects) | – | – | – | – | **out** |
| Google 3D Maps in Maps JS (`Map3DElement`) | not among the services changed for the EEA; the EEA terms drop "No Use with Non-Google Maps" | per-day quota: "requests to that API fail for the rest of the day"; budgets only alert | no non-commercial clause: donations change nothing | website-restricted key; local app needs the user's own billed key | no caching or extraction ("terrain data" is Google content); we answer for misalignment; "High Risk Activities" forbidden; no Pre-GA features "with or near a non-Google Map"; terms page with Google's links; consent before loading | **passes, heavy** |
| Cesium ion, Community plan | not mentioned | no: "continue to work without interruption" and "Cesium may invoice" | "Personal and non-commercial use", "Individual account only"; licensed services "must be inaccessible to third parties" | no client-token rules found | "Cesium ion" logo on the main window | **out** (Commercial $149/month) |
| Esri ArcGIS Location Platform (imagery; Terrain 3D) | – | yes: with pay-as-you-go off "no longer have privileges" until the cycle resets | "both non-revenue generating and revenue-generating" apps: donations change nothing | referrer-restricted key (exists); local app: the user's own Location Platform key | "visualization purposes" only; one request serves one user; users bound by Esri's terms; "Powered by Esri"; high-risk disclaimer (8.3) | **passes** |
| Esri's resold Google Photorealistic 3D | – | – | "internal business purposes" only | – | – | **out** |
| MapTiler Cloud Free | – | pauses until next month | "limited to non-commercial use", commercial undefined | – | logo; no server-side cache | out: terrain 30 m (5 m in some countries), another account |
| Mapbox | – | no: overage is invoiced, email alerts only | – | – | – | **out** |
| Azure Maps | – | no spending limit with pay-as-you-go | – | – | elevation and DEM tiles retired in 2023 | **out** |
| Apple MapKit JS | – | – | needs the $99 a year developer membership | – | – | **out** |
| HERE | – | free plan retired 2025-08-31 | – | – | – | **out** |
| Stadia Maps | – | – | satellite from $80 a month | – | – | **out** |
| Bing Maps | – | – | free accounts ended 2025-06-30 | – | – | **out** |
| Sentinel-2 cloudless | – | – | non-commercial; 10 m pixels | – | – | out (fidelity) |
| Mapterhorn terrain tiles | – | – | each source's licence; no usage policy published | – | – | far background only, ask first |
| AWS Terrain Tiles | – | – | per-source attribution | – | 30 m in our countries, frozen since 2017 | far background only |
| swisstopo 3D (terrain, 3D Tiles) | – | – | free, fair use up to 20,000 users a day | – | source mandatory | usable in Switzerland |
| Our own DEM and orthophotos | – | – | already licensed for the site | none | credits with "processed" | **passes** |

## Variants

### A. KML and links ("Open in Google Earth")
- **What it gives.** A KML file built in the browser from the selected line: the unloaded webbing (51 points of
  `sag.ts`) as a `LineString` at absolute heights, both anchors as placemarks, the walker's spot (the lowest point of
  the envelope) as a placemark, the data credits in `<description>`. Plus links: Google Earth Web at the line, for a
  Swiss line swisstopo's 3D viewer, on phones Google Maps' satellite view (opens the app).
- **What Google Earth does with it.** Earth Web opens a local KML "even if you're not signed in" and shows lines,
  placemarks, ground overlays and simple tours, not 3D models; Earth Pro shows COLLADA models and tours, but
  "will no longer be available for download beginning June 25, 2027" (installed copies keep working). KML "absolute"
  is "above sea level", which the OGC standard defines as the EGM96 geoid (see [Height alignment](#height-alignment)).
- **Limits.** No anchor editing, no animated walker (Earth Web's simple tours fly the camera only; a moving
  placemark needs Earth Pro), outside our app. The `earth.google.com/web/@lat,lon,…` camera link (Google documents
  sharing a view by link, not its syntax) and swisstopo's `3d`/`camera` parameters (in its code, not its docs) are
  undocumented and were not tried here; there is no documented way to load a KML by URL.
- **Legal.** The file holds only our data; Google's end-user terms say a local KML "is not uploaded or submitted to
  Google". The links are the user's own choice to open Google's site. No consent gate, no terms page.
- **Effort: low** (a KML writer in TypeScript saved with the favourites export's `download`,
  `viewer/src/favourites.ts:157`, a menu in `LineDetails`, the geoid offset of
  [Height alignment](#height-alignment) for metre-true heights).

### B. Our own data
- **What it gives.** The run's DEM around the line (the same 1 m grid the search used; 0.5 m data in Switzerland
  averaged to 1 m) as a terrain mesh, our orthophoto draped on it, the webbing and the walker on the very heights of
  the search: no datum conversion, no misalignment. Nadir orthophotos stretch over vertical walls: cliffs look
  smeared where the mock shows textured rock.
- **Data.** A DEM patch from a new quick-lane request (see [Anchor editing](#anchor-editing-and-the-walker)).
  Textures from our cached tiles (`/cache/<folder>/wm256/…`, same origin: z10-16 over the whole search, z17-21 only
  30 m around the best groups) and from the national orthophoto services directly: all 20 probed services answer
  with `Access-Control-Allow-Origin`, which WebGL textures need (only Saxony-Anhalt's sends none to `http://127.0.0.1`,
  so the local app takes its tiles from our cache). Runs without an orthophoto (the world sources) take Esri's
  imagery (variant C) on the public site, or plain shading.
- **Where it works.** Public site and local app alike; no key; nothing new reaches a third party when the textures
  come from our cache. With three.js the page needs no change of the CSP (measured).
- **Money.** None outside; our server sends the patch and the tiles: about 2.2–4.2 MB per open, about 3 GB a month
  at 1000 opens (see [Size](#size-performance-and-phones)).
- **Effort: high** (the core parts below, the rendering library, the patch endpoint, the texture assembly).

### C. Esri: Terrain 3D and World Imagery
- **What it gives.** Esri's Terrain 3D as the ground and World Imagery as the drape. At zoom 19–21 World Imagery is
  the national orthophoto (GUGiK, swisstopo, GKÚ/NLC, IGN/ICGC, Land Salzburg); Malta, South Tyrol and the USA get
  Vantor imagery. Native tiles reach zoom 20 at Żabi Koń and 21 at Lauterbrunnen.
- **Terrain 3D** is public and unmetered: the price list bills tiles only from `basemaps-api`, `ibasemaps-api` and
  `static-map-tiles-api.arcgis.com`, and Esri's own SDK never sends the key to `elevation3d.arcgis.com`. Its tiles
  end at level 16 (2.39 m in Web Mercator, about 1.5 m on the ground at 50° N): coarser than our DEM, built from the
  same national lidar in PL, CH and SK (2 m in Spain, 24 m in Malta). Its heights are orthometric in the national
  datums: our anchors sit on it without a geoid (to confirm in a test).
- **Best use:** as a layer of B: Esri imagery where we have no orthophoto, Terrain 3D or Mapterhorn for the far
  surroundings beyond the patch. Esri documents CesiumJS for both (`ArcGisMapServerImageryProvider`,
  `ArcGISTiledElevationTerrainProvider`); its FAQ allows "open source libraries". Esri's own SDK
  (`@arcgis/core`, 84 MB unpacked, proprietary, assets from `js.arcgis.com` unless self-hosted) is not needed.
- **Money.** 0 within 2,000,000 basemap tiles a month, **shared with the 2D satellite layer**; above it the account
  loses the service until the next billing cycle, and with it the 2D satellite layer too.
- **Legal.** Esri is our processor (its DPA, to countersign). Users must be bound by the agreement's terms (3.1(c)(5))
  and the approved About-page sentence says the imagery "may only be viewed in this map": it needs "or in the 3D view"
  (wording for approval). Visualization only (3.1(d)(3)): whether the browser may read Esri's ground heights while
  an anchor is dragged is a grey zone, so live heights come from our patch. "Powered by Esri" and the data credits.
- **Effort: low–medium** on top of B (two adapters, the existing `WebKeys` key, the sentence).

### D. Google 3D Maps
- **What it gives.** Google's 3D map in a web component: the photorealistic mesh where Google has "3D surface data"
  (a coverage map in Google's docs, updated daily), satellite imagery on terrain elsewhere. Our line as a
  `Polyline3DElement`, the walker as a `Model3DElement` (`.glb` with "No extensions": no Draco), camera flights with
  `flyCameraTo`/`flyCameraAround`.
- **Status.** In the weekly (default) channel since 23 Oct 2025; no 3D page carries a pre-GA tag; Maps JavaScript
  API is a GA core service: GA in practice. Alpha or beta features (e.g. `autofitsCamera`) must stay out: the EEA
  terms forbid "Pre-GA Offerings with or near a non-Google Map", and our app is full of Leaflet maps.
- **Editing is weaker.** The map reports clicks with lat/lng/altitude ("at coarser levels, less accurate data"), but
  has no screen-to-ground method and no drag events on the ground: an anchor is moved by clicking its new spot, or
  by our own controls; the walker moves with a slider or its animation. Heights must come from our patch: "terrain
  data" is Google content, which may not be extracted.
- **Money and hard stop.** Billed as "Immersive Maps" per map load, 5,000 free a month, then $7.00 per 1,000. A
  per-day quota is the documented hard cap; Google's rule (free cap ÷ 31) gives 161 a day, so about 150 a day leaves
  room for counting differences. A Google Cloud billing account with a card is required; budgets only alert.
- **Keys.** Restricted to the site's address and to Maps JavaScript API; our `strict-origin` Referer fits Google's
  check. The local app would need each user's own Google Cloud project with billing.
- **Legal.** The heaviest: a consent gate before anything loads (the site is a joint controller of the transmission
  to Google, and Google's script may store data on the device), a terms page with Google's notice and links, the
  "High Risk Activities" clause (a highline view nobody should trust for safety is arguably outside it: ask Google),
  responsibility for misalignment and for telling Google's content from ours (see [Legal](#legal)).
- **CSP.** Google's script comes from its CDN; its strict policy needs a nonce on every script and style element,
  `'unsafe-eval'` and `worker-src blob:`: the 3D page gets a per-request nonce.
- **Effort: high** (its own renderer, click editing, consent gate, terms page, nonce CSP, alignment).

## How a 3D view joins the app
- **Entry.** `LineDetails` (`viewer/src/result/view/LineDetails.tsx:154-163`) gets an optional `onView3d` prop like
  `onZoom` (`:157`), passed only by the app's shell: the same component is bundled into `viewer.js` for a run's
  `map.html`, which offers no 3D view.
- **Route.** A hash route beside the existing `#run=…&line=…` (e.g. `&view=3d`): Back returns to the 2D map and a
  reload reopens the view.
- **Bundle.** A third esbuild entry built as its own IIFE file and injected on the first click, as
  `viewer/src/result/load.ts:11-33` injects a run's `data.js`; it exports an imperative `mount(element, line, run)`
  (two bundles cannot share Preact hooks). `app.js` does not grow.
- **Vendor files outside `viewer/dist`.** Workers, wasm decoders or a library's asset folders cannot go into
  `viewer/dist`: `mapping.install_viewer` copies every entry of `dist` into each run's `runs/_viewer` and opens each
  as a file, so a subfolder would break every search's save step, and `tests/test_viewer.py` compares `dist` as a
  flat folder. They get their own versioned folder, served next to `/app` (`web.py:1513`) with long-lived caching,
  and stay out of runs.
- **Its own CSP.** The 3D page gets its own policy; every other response keeps `SECURITY_HEADERS` (`web.py:84`),
  which `tests/test_public.py` asserts exactly (see [CSP](#csp)).
- **Keys.** A provider's key is one more field of `settings.WebKeys` (delivered in a meta tag, restricted to the
  site's address, public site only). The operator's key never leaves the server: in the local app a provider's 3D
  view needs the local user's own key; B and A need none.
- **Texts** in `locales/en.json` (`ui.view3d.*`). **Tests**: the geometry in Node like `sag.ts`; the page in headless
  Edge with a software WebGL renderer; the 3D page's headers in `tests/test_public.py`; a visual review with
  `tools/ui_shots.py` on the desktop and both phones.

## Anchor editing and the walker
- **The webbing in 3D.** `viewer/src/sag.ts` already solves it: `estimate(span, dh, rigging)` (span = horizontal
  distance, dh = e1 − e2) gives the unloaded webbing (51 points) and the envelope (sag at 42 positions);
  `athlete(x)` gives the loaded webbing with the walker at x (61 points, warm-started from the nearest envelope
  solution). Each point (x, drop) maps to 3D as A1 + (x / span)·(A2 − A1) horizontally and e1 − drop vertically.
- **The walker** starts where the envelope's sag is largest, follows a drag along the line (the pointer projected on
  the span gives x, one `athlete(x)` per animation frame) and walks from A1 to A2 when asked (x growing at walking
  pace; still under `prefers-reduced-motion`). The figure: a low-poly mannequin of 1.7 m standing on the webbing at
  x, facing along the line (a CC0 glTF or our own few hundred triangles; for D a `.glb` without extensions).
- **Dragging an anchor** (B, C): the picked ground point gives the new lat/lon; its height comes from **our DEM
  patch**, never from a provider's mesh (Google forbids extracting its "terrain data", Esri allows visualization
  only, and both are in other datums). Each pointer move recomputes `estimate` (42 small solves) and redraws the
  curve. In D an anchor moves by a click on its new spot.
- **On release** the app asks `GET /api/profile?run=…&line=lat1,lon1,lat2,lon2` (on the public site 30 a minute and
  500 an hour per limited user, `settings.py:58`, within `profile_problem`'s bounds, `web.py:209`) and turns the answer
  into a line with `measuredLine` (`viewer/src/result/model.ts:97`): clearance, trees and buildings, water, as *Measure*
  does on the 2D map. The webbing takes the 2D map's colours (clear or over trees). Nothing is saved.
- **The DEM patch** is a new kind of the quick lane beside `estimate`, `profile` and `place` (`jobs.py:1506`), built
  like `search.profile_of_line`: a square around the line on the run's source and grid, at most `MAX_MEASURED_PX`
  pixels on a side (`search.py:95`, so the memory the compute slots reserve for the lane stays right), the checks of
  `profile_problem`, its own rate beside `profile_rate`. It lies on the run's grid, rotated from true north by the
  grid convergence, so it comes with an affine from grid metres to lat/lon. It goes out as binary or base64url:
  standard base64 would be damaged on the public site, where `Redact`'s `ABSOLUTE_PATH` (`jobs.py:280`) rewrites a
  `/` that follows a `+`. Every embedded variant needs the patch for live heights; B also draws it.

## Height alignment
Our anchor heights e1, e2 are the terrain of the anchor pixel in the source's own vertical datum; no datum is
recorded in the code, and pyproj is used for 2D only (PROJ's network is off).

| Variant | Its heights | What our line needs |
| --- | --- | --- |
| B, our data | ours | nothing: line and ground share one DEM |
| C, Esri Terrain 3D | orthometric, built from the same national DEMs (Esri tags: EVRF2007-PL, LN02, Baltic 1957, Alicante) | nothing in PL, CH, SK, ES (to confirm in a test; ~1.5 m tiles smooth the cliff edge); Malta: Esri has 24 m WorldDEM4Ortho on EGM2008 |
| D, Google 3D Maps | `ABSOLUTE`: "relative to the mean sea level, calculated using EGM96" | our height + the source's geoid − EGM96's geoid at the line |
| A, KML | "absolute" = above sea level = "WGS84 EGM96 Geoid" (OGC) | the same as D |

- **The conversion** for A and D: ellipsoidal height = our height + the national geoid (PROJ grid), then minus
  EGM96's geoid; one value at the line's middle is enough for a line under 2 km. Grids exist for most sources (see
  the table below); Malta (datum unknown), South Tyrol, Luxembourg and Hawaii have none, where EGM2008 stands in.
- **How much it matters** (measured at the national grids' nodes): the geoid itself is 22–58 m in our European
  countries (+39.98 m at Żabi Koń, +51.82 m at Lauterbrunnen), so a line placed on an ellipsoidal surface without a
  grid would hang tens of metres off. Leaving out only the national model costs less:

  | Region | EGM2008 − national model (p1…p99, mean) | EGM96 − national model (p1…p99, mean) |
  | --- | --- | --- |
  | Poland (PL-geoid2021) | +0.06 … +0.26 m, +0.17 | −0.56 … +0.74 m, +0.14 |
  | Switzerland (CHGeo2004, LN02) | −0.41 … +0.65 m, +0.26 | −2.54 … +0.34 m, −0.86 |
  | Slovakia (Baltic 1957) | −0.37 … +0.49 m, +0.01 | −0.40 … +0.64 m, +0.18 |
  | Spain (EGM08-REDNAP) | +0.44 … +0.66 m, +0.56 | −0.62 … +1.17 m, +0.37 |
  | USA, CONUS (GEOID18) | −1.87 … +1.11 m, −0.35 | −2.09 … +1.29 m, −0.47 |

  So for A and D, our heights taken as EGM96 heights are off by up to about 1 m in Poland and 3 m in the Alps; the
  national grid plus EGM96's removes that. Horizontally ETRS89 is about 1.0 m and NAD83 about 1.5 m from WGS 84 at
  2026.8 (NAD83 heights also −0.6 to −0.8 m): visible at an anchor, not in the overview.
- **Shipping the grids.** pyproj's wheels contain none, and PROJ's network is off. The European national grids are
  0.3–1.5 MB each (about 6 MB together), EGM96 2.7 MB, the USA 16.7 + 11.3 MB, EGM2008 80.6 MB. pyproj reads its own
  data folder before `PROJ_DATA`, so the image keeps them in a folder added with `pyproj.datadir.append_data_dir()`
  (fetched in the build stage against the sha256 of `files.geojson`). **Pitfall, measured:** without its grid,
  pyproj silently returns a "ballpark" transformation with N = 0 (only a warning; `only_best` and `errcheck` do not
  stop it); an explicit `+proj=vgridshift +grids=<file>` pipeline fails loudly instead, so the code uses that.
- **Not a datum question:** Google's mesh is a surface model (trees, buildings), our anchors are bare ground (DTM),
  and Google's terrain outside its mesh is coarse. A line drawn on our heights can pass through Google's trees or
  float above its smoothed rim. The EEA terms make us "responsible for any misalignment": the view says the line
  is ours and the imagery Google's.

| Source | Vertical datum | PROJ grid to ellipsoidal heights |
| --- | --- | --- |
| geoportal (PL) | PL-EVRF2007-NH | `pl_gugik_geoid2021-PL-EVRF2007-NH.tif` (1.0 MB) |
| swisstopo (CH, LI) | LN02 | `ch_swisstopo_chgeo2004_ETRS89_LN02.tif` (0.3 MB) |
| slovakia | Baltic 1957 (Bpv) | `sk_gku_Slovakia_ETRS89h_to_Baltic1957.tif` (0.5 MB) |
| usa | NAVD88 (PR, VI: local mean sea level) | `us_noaa_g2018u0.tif` (16.7 MB); PR/VI `us_noaa_g2018p0.tif` |
| alaska, alaska_ifsar | NAVD88 (IfSAR: assumed) | `us_noaa_g2012ba0.tif` (11.3 MB) |
| usgs10m | NAVD88; Hawaii local mean sea level | CONUS as `usa`; Hawaii none |
| europe (FABDEM, Copernicus) | EGM2008 | `us_nga_egm08_25.tif` (80.6 MB) |
| nasadem | EGM96 | `us_nga_egm96_15.tif` (2.7 MB) |
| malta, malta2012 | not stated | none |
| spain, spain_canarias | Alicante; Balearics and Canaries local | `es_ign_egm08-rednap.tif`, `es_ign_egm08-rednap-canarias.tif` |
| austria | EVRF2000 Austria | `at_bev_GEOID_GRS80_Oesterreich.tif` |
| denmark | DVR90 | `dk_sdfi_dvr90_2023.tif` |
| finland | N2000 | `fi_nls_fin2023n2000.tif` |
| hesse, lower_saxony, saxony_anhalt, mecklenburg_vorpommern | DHHN2016 | `de_bkg_gcg2016.tif` |
| england, wales | ODN | `uk_os_OSGM15_GB.tif` |
| south_tyrol | the province's orthometric heights | none (Italy's grid is not open) |
| luxembourg | NG95 | none |

## Rendering library
B and C need one library to draw the scene (D brings Google's). Each candidate was bundled with our esbuild settings
(IIFE, es2020) and the two finalists ran a test scene in headless Edge under our real headers: a 1025 px tile of the
Żabi Koń DEM, our cached orthophoto tiles, a sagging polyline updated live, a glTF walker and picking.

| | three.js (+ 3DTilesRendererJS) | CesiumJS (`CesiumWidget`, no ion) | Giro3D | iTowns | MapLibre GL JS |
| --- | --- | --- | --- | --- | --- |
| Licence, version | MIT 0.187 (+ Apache-2.0, 0.5.3, pre-1.0) | Apache-2.0, 1.146 (engine 26.4) | MIT 2.0.6 | CeCILL-B/MIT 2.46 | BSD-3 6.16 |
| Releases in 12 months | 12 (15) | 13, monthly; classes moving to `@cesium/core`, removals due in 1.150 | 9 | 0 | 38 |
| Bundle, min / gzip | 722 / 188 KB (+ globe 817 / 219 KB) | 3,902 / 1,044 KB + 881 / 275 KB of workers and assets at run time | 1,570 / 492 KB | 1,326 / 374 KB | 1,082 + 507 / 291 + 145 KB |
| Under today's CSP | **0 violations, 0 errors** | 9 violations: WebAssembly at load, three inline styles | blob workers | `import.meta` breaks relative URLs in an IIFE | ESM only, WebGL2 required |
| Our DEM | own mesh (`@mapbox/martini`, or built on the server) | `CustomHeightmapTerrainProvider` (no availability: `sampleTerrainMostDetailed` refuses it) | elevation layers | elevation layers | `raster-dem` |
| Esri | imagery as an XYZ texture; Terrain 3D (LERC) needs our own decoder code | imagery and Terrain 3D built in (LERC decoder in pure JS) | via OpenLayers | WMTS | raster only |
| Line in the air, model, picking | `Line2`, `GLTFLoader`, raycast with `three-mesh-bvh`: measured | entities with `CallbackProperty`, `Model`, `globe.pick`: measured | three objects | three objects | needs a three.js custom layer |
| Far field (horizon, valleys around) | with 3DTilesRendererJS (terrain-RGB, Terrarium, quantized mesh; XYZ/WMS/WMTS overlays) | built in (globe) | yes | yes | yes |

- **three.js** fits B best: it runs under the site's current CSP unchanged, is small, and every part of the scene
  was measured working. The costs: no globe unless 3DTilesRendererJS is added (+31 KB gzip; it has no Esri LERC
  terrain), and our own camera controls and credits.
- **CesiumJS** fits if the view must show the far field like Google Earth (horizon, Esri's terrain around the
  patch): it has the globe, Esri's imagery and terrain built in. The costs: about 1.3 MB gzip of code, folders of
  workers and assets to ship outside `viewer/dist`, a relaxed CSP on its page (below), monthly releases, and reports
  of WebGL context loss in Cesium scenes on iPhone 11, XR and SE under iOS 18. Only `CesiumWidget`: the `Viewer`'s
  widgets need `'unsafe-eval'` (Knockout).
- **One line each:** Giro3D (good DEM and WMS draping, but 492 KB gzip, blob workers, pins three 0.180); iTowns (no
  release in 12 months, pins three 0.174); MapLibre v6 (ESM only, a line in the air needs a three.js layer); deck.gl
  (loads its workers from unpkg unless self-hosted); Esri's ArcGIS Maps SDK (proprietary, its FAQ asks for
  `'wasm-unsafe-eval'`, `style-src-attr 'unsafe-inline'` and `worker-src blob:`). No open advisories for three,
  3d-tiles-renderer, CesiumJS, Giro3D or iTowns; MapLibre's one is fixed in 6.4.1.
- **The question that decides it:** is a far field part of "Google-Earth-like"? Yes: CesiumJS. A patch of about
  1.5 km with a coarse ring around it is enough: three.js.

## CSP
Every variant gets its 3D page on its own route, so only that page's header changes; the rest of the site keeps
today's policy.

| Variant and library | Additions to today's `script-src 'self'; style-src 'self'; img-src 'self' data: https:; connect-src 'self'` |
| --- | --- |
| A | none |
| B with three.js, data from our server | none (measured) |
| B/C with three.js, tiles straight from the services | none for `TextureLoader` (`<img>`, already `img-src https:`); with 3DTilesRendererJS (it uses `fetch`) each tile host in `connect-src` |
| B/C with `CesiumWidget` | `script-src 'wasm-unsafe-eval'` (meshoptimizer compiles WebAssembly when the bundle loads); `style-src 'unsafe-inline'`, or a build-time patch of three places (a style attribute, a `<style>` element, credits through `innerHTML`); each tile host in `connect-src` (imagery comes by XHR). Workers are same-origin and need nothing more |
| D | a per-request nonce on every script and style element, `'unsafe-eval'`, `worker-src blob:`, Google's hosts in `connect-src` (Google's sample strict policy) |

## Size, performance and phones
- **Code**, once per browser: three.js 188 KB gzip (219 KB with the globe), CesiumJS about 1.3 MB gzip with its
  run-time files; for scale, `app.js` is 811 KB minified. The 3D bundle loads only on the first click.
- **Data per open** of a 1.5 km × 1.5 km patch at 1 m (measured on our caches): the DEM as terrain-RGB at 0.1 m
  0.90 MB in Poland, 1.40 MB in Switzerland (LERC at 1 cm 2.17 / 2.65 MB, raw float32 9 MB); our cached orthophoto
  tiles average 7 KB (PL) and 16–18 KB (CH). The recommended mix (terrain-RGB + zoom 17 over the patch + zoom 19 in
  a corridor around the line) is about **2.2 MB (PL) to 4.2 MB (CH)**; the worst case 9–17 MB. 1000 opens a month
  are about 3 GB from the VPS.
- **Orthophoto coverage:** today zoom 17–21 is cached only 30 m around the chosen lines, so a 3D open needs about
  120–180 more tiles from the national services: fetched by our server into the cache (the services' limits apply,
  e.g. swisstopo's 1200 a minute on WMTS) or by the browser (the services see the IP, as the 2D map already says).
- **Mesh:** a 1 km tile of our DEM at 0.25 m error is 88k vertices in Poland and 293k in the Alps; at 0.5 m 42k and
  134k; the full grid would be 1.05 M.
- **Phones**, three levels:

  | Level | What | GPU budget |
  | --- | --- | --- |
  | Full, with editing | three.js, mesh at 0.5 m error (~95k vertices PL, ~300k CH for 1.5 km), zoom 17 over the patch + zoom 19 in a corridor, drag by raycast | ~45–60 MB textures |
  | Simplified, view only | mesh at 1–2 m error, zoom 17 only, no dragging | 16–18 MB textures, ~1.5–2.5 MB per open |
  | Desktop only | zoom 19 over the whole patch, fine meshes, or CesiumJS with the far field | 225–248 MB textures |

  WebGL2 is in iOS Safari since 15. iOS kills texture-heavy pages without any event (WebKit bug 300782) and loses
  the WebGL context in some Cesium scenes on iPhone 11, XR and SE under iOS 18 (WebKit: too much GPU work at once):
  keep textures small, handle `webglcontextlost`, flush between large uploads, and test on such a phone before
  promising the full level. D has `maxMemoryMegabytes` and a `PERFORMANCE` quality mode for phones.
- **Tests:** on Windows headless Edge with `--disable-gpu` already has WebGL2 (WARP); the Linux CI needs
  `--enable-unsafe-swiftshader`; CesiumJS needs `requestRenderMode` under virtual time or the run never ends.

## Privacy sentences, for approval
Not applied: the privacy page's wording is the user's decision. Today (`web.py:1666`): "Maps in your browser load
background tiles (OpenStreetMap, OpenTopoMap, Esri, orthophoto services) directly: those services see your IP
address."
- **A**: no change (a link and a file the user opens elsewhere).
- **B**: no change while textures come from our cache or the orthophoto services already named.
- **C**: "Maps in your browser, the 3D view of a line included, load background tiles (OpenStreetMap, OpenTopoMap,
  Esri, orthophoto services) and Esri's elevation tiles directly: those services see your IP address." The About
  page's Esri sentence: "…its imagery may only be viewed in this map **and in the 3D view of a line**: …".
- **D**, on the privacy page: "The 3D view of a line can show Google's 3D map. It loads only after you choose it in
  that view: your browser then contacts Google, which receives your IP address, browser data and the place you look
  at, uses them under its own Privacy Policy and may transfer them to the USA (EU-US Data Privacy Framework). The
  choice is remembered in this browser until you withdraw it in the view." In the view, before anything loads:
  "Google 3D map: loading it sends your IP address and this place to Google, which uses them under its Privacy
  Policy. [Show Google's 3D map] [Use the site's own 3D view] [ ] Remember in this browser."
- **Terms page** (for D, and the firmer footing for C), suggested headings: what the site is and that results and the
  3D view are previews to check on the spot; the Google notice with links to the Google Maps End User Additional
  Terms and the Google Privacy Policy (D); Esri's terms and "view only" (C); the data licences and the Copernicus
  liability sentence; accounts, quotas, no harvesting; no warranty as far as Polish law allows; contact; accepted at
  sign-in.

## Legal
- **GDPR roles.** The public site is a controller even without income (C-101/01 Lindqvist: publication to "an
  indefinite number of people"). Embedding Google's map makes it a joint controller of "the collection and
  disclosure by transmission" (C-40/17 Fashion ID), and any consent "must be given prior", obtained by the site.
  Google calls itself an independent controller (its Controller Terms), which does not undo that. Esri is our
  processor ("Customer is the Controller and Esri is the Processor", its DPA). The local app is the user's own
  household use.
- **The Munich Google Fonts judgment** (LG München I, 3 O 17493/20, €100): passing the IP address to Google "ohne
  Zustimmung" when an alternative without the transfer existed. German, first instance, not binding in Poland; no
  Polish ruling or UODO guidance on click-to-load found. For D: nothing from Google before the user's click.
- **Transfers.** Google LLC and Esri are "Active" on the EU-US Data Privacy Framework list (next dates 2027-09-13 and
  2027-10-23); the fallback is standard contractual clauses in both providers' terms.
- **Device storage** (Prawo komunikacji elektronicznej art. 399): consent unless "konieczne" for the service the user
  asked for; Google's EEA terms put cookie compliance on us; the D consent gate covers it. Fines up to 15 000 zł for
  an operator without revenue (art. 446 ust. 3).
- **High-risk clauses.** Google forbids use "for High Risk Activities" (failure "would reasonably be expected to
  result in death, serious personal injury…"): a disclaimer does not lift a ban on us, so D shows no safety number
  taken from Google content, labels itself a visual preview, and the question goes to Google. Esri only disclaims
  ("at Customer's own risk", 8.3): a disclaimer in our terms fits. Under Polish law an exclusion of liability for
  intent is void (KC art. 473 § 2).
- **Data licences.** PZGiK's NMT and orthophotos are free without a licence, the source stated (Prawo geodezyjne
  art. 40a ust. 2, 40c ust. 3 and 5); NMPT is not on that list (ask GUGiK on what basis it is free). swisstopo: "A
  reference to the source is mandatory." CC BY sources: say the data was processed (the site's processed note does).
  FABDEM (CC BY-NC-SA): a 3D patch of a `europe` run is shared adapted material, non-commercial and share-alike;
  never export it combined with Esri imagery (Esri 3.1(a)(4)).
- **Donations.** No change for Google, Esri, PZGiK, swisstopo, Copernicus or CC BY data. FABDEM's non-commercial
  clause is a grey zone (CC: "depends on the specifics of the situation"): ask Fathom in writing before donations.
  Outside the licences, donations may matter for the duty of a regulamin (UŚUDE: "działalność zarobkowa"), the DSA,
  consumer law and the new product-liability rules (from 9 December 2026).
- **Library notices.** MIT, BSD and Apache-2.0 require their notices with every copy; `viewer/build.mjs` strips
  them (`legalComments: "none"`) and `viewer/dist` holds no licence text. A 3D library adds its own notices
  (CesiumJS ships a third-party list). See [Side findings](#side-findings-for-main).

## Effort and money
| Part | Needed by | Effort |
| --- | --- | --- |
| Rendering library, three.js: bundle entry, own controls and credits, mesh (martini or server) | B, C | medium |
| Rendering library, CesiumJS instead: worker and asset folders outside `dist`, `CESIUM_BASE_URL`, CSP or patch | B, C | high (adapters then low) |
| KML writer, links, menu | A | low |
| Geoid offset at the line (pyproj with shipped grids) | A (metre-true), D | low–medium |
| 3D button, hash route, lazy bundle, vendor folder | B, C, D | medium |
| The 3D page's own CSP and its tests | B, C, D (D: per-request nonce) | low (B, C) – medium (D) |
| Webbing and walker in 3D (drag, animation), tested in Node | B, C, D | low |
| Anchor editing: picking, live sag, profile on release | B, C (D: click-to-place) | medium |
| DEM patch in the quick lane (rate, checks, affine, encoding) | B, C, D | medium |
| Textures: cached tiles + orthophoto services; optional fill of z18–19 on the server | B | medium (high with the fill) |
| Esri imagery and Terrain 3D adapters, key, sentence | C | low–medium |
| Google 3D Maps page (its own renderer), consent gate, quota and key setup | D | high |
| Terms page (wording approved first) | D (C: firmer) | low–medium |
| Tests in headless Edge (software WebGL), visual review on the desktop and two phones | B, C, D | medium |
| Texts, credits, docs | all | low |

| Variant | Money a month at ≤ 1000 opens | What users see at the stop | Card |
| --- | --- | --- | --- |
| A | 0 | – | no |
| B | 0 outside; about 3 GB a month from our server | – | no |
| C | 0 within 2M basemap tiles, shared with the 2D satellite layer | Esri imagery (3D and 2D) gone until the next billing cycle; Terrain 3D stays | on the Esri account already |
| D | 0 within 5,000 loads (per-day cap ~150) | Google's map fails for the rest of the day (Pacific time) | yes (Google Cloud billing) |

Recurring: keys and their restrictions, quota alarms, library upgrades (each rewrites a committed bundle), watching
the providers' terms (Google's EEA terms, Esri's agreement, Earth Pro's end).

## Order of work, checks and questions
1. **A** as one small task.
2. **Before B/C**: the rendering-library decision, then a prototype at R2 (Dolina Bolechowicka) and R19
   (Lauterbrunnen) that counts bytes and tiles per open and runs on both phones.
3. **D** only after the checks below say yes.

**Checks a person does by hand** (no automated browsing of Google's apps):
- Google's coverage: the map on <https://developers.google.com/maps/documentation/javascript/3d/coverage> or Google
  Earth Web at R1 Żabi Koń
  [@50.15595,19.75627](https://earth.google.com/web/@50.15595,19.75627,420a,900d,35y,0h,65t,0r),
  R2 Dolina Bolechowicka [@50.15286,19.78462](https://earth.google.com/web/@50.15286,19.78462,400a,900d,35y,0h,65t,0r),
  R13 Kasprowy Wierch [@49.23200,19.98170](https://earth.google.com/web/@49.232,19.9817,1900a,1500d,35y,0h,65t,0r),
  R19 Lauterbrunnen [@46.59600,7.90700](https://earth.google.com/web/@46.596,7.907,900a,1500d,35y,90h,65t,0r),
  R6 Dingli [@35.85650,14.38300](https://earth.google.com/web/@35.8565,14.383,150a,900d,35y,0h,65t,0r),
  R23 Moab [@38.56100,-109.56800](https://earth.google.com/web/@38.561,-109.568,1300a,1200d,35y,0h,65t,0r)
  (the `@…a,…d,…y,…h,…t,…r` syntax is undocumented): is it a textured mesh or imagery on terrain?
- The look side by side: Google Earth Web, swisstopo's 3D viewer at R19
  (<https://map.geo.admin.ch/#/map?lang=en&3d=true&camera=7.907,46.596,2500,-35,0,>, undocumented parameters) and
  ArcGIS Scene Viewer (signed in with the Location Platform account, it counts against the free tiles).

**Questions to providers** (drafts on request):
- Google: is a highline "visual preview" with our own numbers a High Risk Activity?
- Esri: is Terrain 3D used anonymously from CesiumJS or three.js covered (Esri documents it for CesiumJS; the Master
  Agreement 3.2(a) ties data to Esri products)? May the browser read its ground heights while an anchor is dragged?
- Fathom (fabdem@fathom.global): do donations make our FABDEM use commercial?
- GUGiK: the legal basis for reusing NMPT (and the 3D mesh) free of charge.

## Side findings for `main`
- **Licence notices** of the bundled libraries are stripped (`viewer/build.mjs:17`, `legalComments: "none"`): a
  `THIRD-PARTY-LICENSES.txt` built from esbuild's metafile into `dist`, a banner pointing to it and a link from the
  About page would fix it (the tool is the user's choice: generate-license-file, license-checker-rseidelsohn,
  esbuild-plugin-license, or a short script).
- **Base64 through `Redact`:** `ABSOLUTE_PATH` (`jobs.py:280`) turns `+/…` in a quick-lane answer into `<path>` on
  the public site only; any future binary payload must be base64url.
- **NMPT's legal basis** is not in Prawo geodezyjne art. 40a ust. 2 (NMT and orthophotos are); ask GUGiK.
- **Saxony-Anhalt's orthophoto** sends no CORS header to `http://` origins (the local app); irrelevant for Leaflet's
  `<img>` tiles, relevant for any WebGL use.

## Appendix: sources
All read on 2026-11-01; quotes are short excerpts of the deciding sentences.

**Google**
- Map Tiles API in the EEA: "Photorealistic 3D tiles are not available." / "3D Maps may be a suitable alternative in
  place of Photorealistic 3D Tiles." — <https://developers.google.com/maps/comms/eea/map-tiles>
- EEA FAQ: "At this time, only the Services listed above are changing."; the EEA terms remove "No Use with
  Non-Google Maps" — <https://developers.google.com/maps/comms/eea/faq>
- 3D Maps channel: "3D Maps is now available in the weekly channel." (23 Oct 2025) —
  <https://developers.google.com/maps/documentation/javascript/releases>; "Features in non-GA stages are tagged as
  such in the documentation with icons and notes." — <https://developers.google.com/maps/launch-stages>
- Pre-GA next to other maps: "Customer will not use Pre-GA Offerings with or near a non-Google Map in a Customer
  Application." — <https://cloud.google.com/terms/maps-platform/eea/maps-service-terms>
- Billing: SKU "Immersive Maps", billable event "Map load", "Successful map load request to 3D Maps in Maps
  JavaScript API" — <https://developers.google.com/maps/billing-and-pricing/sku-details/maps>; 5,000 free, then
  $7.00 per 1,000 — <https://developers.google.com/maps/billing-and-pricing/pricing>
- Hard stop: "To put a hard cap on usage of an API, lower its per-day quota." / "requests to that API fail for the
  rest of the day" / "divide the free usage cap by 31" / "Setting a budget does not automatically cap" —
  <https://developers.google.com/maps/billing-and-pricing/manage-costs>
- Card: "you must provide a credit card or other payment method" — <https://cloud.google.com/free/docs/free-cloud-features>
- Altitude: "ABSOLUTE: Renders the object relative to the mean sea level, calculated using EGM96." —
  <https://developers.google.com/maps/documentation/javascript/3d/altitude-modes>
- Coverage: "3D terrain data is available worldwide. 3D surface data is limited to the areas highlighted in blue" —
  <https://developers.google.com/maps/documentation/javascript/3d/coverage>
- Models: `.glb` with "No extensions" — <https://developers.google.com/maps/documentation/javascript/3d/models>;
  click altitude "at coarser levels, less accurate data" —
  <https://developers.google.com/maps/documentation/javascript/reference/3d-map>
- CSP: "Maps JavaScript API supports the use of nonce-based strict CSP." —
  <https://developers.google.com/maps/documentation/javascript/content-security-policy>
- EEA terms: "responsible for any misalignment"; end users told of Google Maps content and the "Google Maps End
  User Additional Terms of Service" and the "Google Privacy Policy" (3.2.2); "High Risk Activities": "would
  reasonably be expected to result in death, serious personal injury…"; no End User personal data to Google (4.2);
  cookie compliance on the customer (4.1) — <https://cloud.google.com/terms/maps-platform/eea>
- Keys: "If you don't specify a port number, then requests from any port number are matched." —
  <https://cloud.google.com/docs/authentication/api-keys>; "Clear any APIs that this key doesn't need" —
  <https://developers.google.com/maps/documentation/javascript/get-api-key>
- Google Earth: "You can open local KML files in Google Earth even if you're not signed in." —
  <https://developers.google.com/maps/documentation/earth/import-data>; "Simple KML tours without audio" —
  <https://developers.google.com/maps/documentation/earth/projects-kml>; "Google Earth Pro on desktop will no
  longer be available for download beginning June 25, 2027." — <https://www.google.com/earth/about/versions/>;
  a local KML "is not uploaded or submitted to Google" — <https://maps.google.com/help/terms_maps-earth/>
- KML altitude: "absolute - Interprets the <altitude> as a value in meters above sea level." —
  <https://developers.google.com/kml/documentation/kmlreference>; "the WGS84 EGM96 Geoid" —
  <https://docs.ogc.org/is/12-007r2/12-007r2.html>
- Maps URLs: "You don't need a Google API key to use Maps URLs." —
  <https://developers.google.com/maps/documentation/urls/get-started>

**Esri**
- Price list: basemap tiles "2M free then $0.15 per 1,000 tiles", metered on `basemaps-api`, `ibasemaps-api`,
  `static-map-tiles-api.arcgis.com`; basemap sessions "1K free then $4 per 1,000 sessions"; elevation points "50K
  free then $1 per 1,000 points" — <https://location.arcgis.com/pricing/>
- Hard stop: "your account will no longer have privileges to services … in which you have exceeded the free tier";
  "Free tiers refresh at the start of your billing cycle." — <https://location.arcgis.com/help/billing/>
- Terrain 3D: public item; "Heights are orthometric (in meters) and are based on multiple sources."; LERC tiles to
  level 16 — <https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer?f=json>;
  sources at our places (Poland_DTM1m EVRF2007-PL, swissALTI3D 50 cm LN02, Slovakia_DTM1m Baltic_1957, Spain_DTM2m
  Alicante, WorldDEM4Ortho 24 m EGM2008 in Malta) —
  <https://elevation.arcgis.com/arcgis/rest/services/WorldElevation/DataExtents/MapServer>
- The SDK sends no key to `elevation3d.arcgis.com` — `support/apiKeyUtils.js` of `@arcgis/core` 5.1.27; CesiumJS
  guide with `ArcGISTiledElevationTerrainProvider` — <https://developers.arcgis.com/cesiumjs/scenes/>; "You can use
  ArcGIS Maps SDKs, open source libraries, and scripting APIs to access location services." —
  <https://developers.arcgis.com/documentation/mapping-and-location-services/faq/>
- Location Platform Agreement (revised 21 Nov 2025): 3.1(c)(1) "both non-revenue generating and revenue-generating";
  3.1(c)(5) users bound by its terms; 3.1(d)(2) "A single request for Resultant Output may not be used to serve
  multiple users."; 3.1(d)(3) "only use Resultant Output for visualization purposes"; 3.1(a)(4) no open-source or
  open-database terms; 8.3 high-risk "at Customer's own risk" —
  <https://www.esri.com/content/dam/esrisites/en-us/media/legal/platform/platform-legal.pdf>
- Resold Google 3D: "May be used for the internal business purposes of Customer's organization." (E300 fn 72) —
  <https://www.esri.com/content/dam/esrisites/en-us/media/legal/product-specific-terms-of-use/e300.pdf>
- DPA: "Customer is the Controller and Esri is the Processor" —
  <https://www.esri.com/content/dam/esrisites/en-us/media/legal/gdpr-data-processing-addendums/data-process-addend.pdf>
- World Imagery sources at zoom 19+ — <https://static.arcgis.com/attribution/World_Imagery?f=json>

**Cesium ion, MapTiler and the excluded**
- Cesium ion: "Personal and non-commercial use"; "Individual account only"; Google 3D Tiles "1,000 root tiles /
  month"; Commercial "$149/month" — <https://cesium.com/platform/cesium-ion/pricing/>; 2.2.1 "must be inaccessible to
  third parties"; 4.1 "Cesium may invoice, and You shall pay, additional Fees" — <https://cesium.com/legal/terms-of-service/>;
  "Once over quota, your account will continue to work without interruption." —
  <https://cesium.com/learn/ion/optimizing-quotas/>
- MapTiler: "Usage of the Free Plan is limited to non-commercial use…" — <https://www.maptiler.com/cloud/terms/>;
  "service will pause until the next month" — <https://www.maptiler.com/cloud/pricing/>; terrain "30x30 meters" —
  <https://www.maptiler.com/terrain/>
- Mapbox: usage beyond the free tier invoiced, email alerts only — <https://docs.mapbox.com/accounts/guides/signup.md>
- Azure: "The spending limit isn't available for subscriptions with … pay-as-you-go pricing." —
  <https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit>
- Apple: "a free daily limit … per Apple Developer Program membership" — <https://developer.apple.com/maps/web/>
- HERE: "The Limited Plan will be officially retired on August 31, 2025." —
  <https://www.here.com/learn/blog/july-2025-platform-release-notes/>
- Stadia: satellite from the $80 Standard plan — <https://stadiamaps.com/pricing/>

**Open data**
- Mapterhorn: terrarium WebP tiles to z17; coverage by country; code BSD-3, data under each source's licence —
  <https://mapterhorn.com/>, <https://mapterhorn.com/data-access>
- AWS Terrain Tiles: EU-DEM 30 m in most of Europe; "Regular updates are not planned." —
  <https://github.com/tilezen/joerd/blob/master/docs/data-sources.md>
- swisstopo: quantized-mesh terrain "fully compliant with the Cesium Quantized Mesh 1.0 specification" —
  <https://docs.geo.admin.ch/visualize-data/terrain-service.html>; fair use "an average of 20,000 users per day" —
  <https://www.geo.admin.ch/en/general-terms-of-use-fsdi>
- PROJ geoid grids and sizes — <https://cdn.proj.org/files.geojson> and `proj.db` of pyproj 3.8; "pyproj 3 wheels do
  not include any transformation grids." — <https://pyproj4.github.io/pyproj/stable/transformation_grids.html>;
  the data-directory order — <https://pyproj4.github.io/pyproj/stable/api/datadir.html>

**Libraries, browsers, phones** (sizes and CSP results measured with our esbuild and headless Edge)
- Cesium and CSP: "@cesium/engine which is a widget-less build of CesiumJS" —
  <https://community.cesium.com/t/using-cesium-with-csp-settings/12663>; `CustomHeightmapTerrainProvider`: "no water
  mask, no vertex normals, and no availability" (`@cesium/engine` 26.4.0 source)
- 3DTilesRendererJS plugins (ImageOverlayPlugin, QuantizedMeshPlugin, TerrainRGBMeshPlugin, GoogleCloudAuthPlugin) —
  `3d-tiles-renderer` 0.5.3, `src/three/plugins/API.md`
- MapLibre v6: "ships as ES modules only", "WebGL2 is now required" —
  <https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/>
- deck.gl: "By default, the worker code is loaded from … unpkg.com" — <https://deck.gl/docs/developer-guide/loading-data>
- ArcGIS Maps SDK CSP: "requires the inclusion of wasm-unsafe-eval in the script-src directive" —
  <https://developers.arcgis.com/javascript/latest/faq/>
- Esri scenes: "only support gravity-related coordinate systems" —
  <https://doc.esri.com/en/arcgis-pro/latest/help/sharing/analyzer-warning-messages/24176-3d-layer-will-draw-in-gravity-related-heights.html>
- iOS: WebGL 2 in Safari since 15 — <https://caniuse.com/webgl2>; Cesium context loss on iOS 18 —
  <https://community.cesium.com/t/crashing-on-ios-18-2-and-18-3-on-specific-devices/39615>; "Pages with heavy WebGL
  usage and many textures get terminated by iOS memory pressure" — <https://bugs.webkit.org/show_bug.cgi?id=300782>;
  "We cannot use that much memory on iOS without getting killed." — <https://bugs.webkit.org/show_bug.cgi?id=227636>
- SwiftShader in headless Chromium needs the opt-in `--enable-unsafe-swiftshader` —
  <https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/swiftshader.md>

**Law**
- C-101/01 Lindqvist para 47; C-40/17 Fashion ID operative parts 2–4 and para 102; C-582/14 Breyer; C-673/17 Planet49;
  C-300/21 — CELLAR, e.g. <http://publications.europa.eu/resource/celex/62017CJ0040>
- LG München I, 20.01.2022, 3 O 17493/20 — <https://www.gesetze-bayern.de/Content/Document/Y-300-Z-BECKRS-B-2022-N-612>
- EDPB Guidelines 05/2020 on consent (paras 83, 90, 114) and 2/2023 on Art. 5(3) ePrivacy — <https://www.edpb.europa.eu/>
- EU-US Data Privacy Framework list: Google LLC (5780), Environmental Systems Research Institute, Inc. (5738), both
  "Active" — <https://www.dataprivacyframework.gov/>
- Prawo komunikacji elektronicznej art. 399, 444, 446 — <https://api.sejm.gov.pl/eli/acts/DU/2024/1221/text.html>
- Prawo geodezyjne i kartograficzne art. 40a, 40c (Dz.U. 2026 poz. 1389) —
  <https://api.sejm.gov.pl/eli/acts/DU/2026/1389/text.pdf>; Kodeks cywilny art. 473 § 2
- Creative Commons: BY-NC-SA 4.0 legal code; FAQ "depend on the specifics of the situation" —
  <https://creativecommons.org/faq/>
- swisstopo OGD: "A reference to the source is mandatory." —
  <https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices>
- esbuild legal comments: "none Do not preserve any legal comments." — <https://esbuild.github.io/api/>
