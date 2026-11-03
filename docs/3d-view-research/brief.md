# Brief: research for a 3D view of one highline (wave R1-R4, 2026-11-01)

You are one of four research agents working in parallel. You do RESEARCH ONLY: never edit, create or commit
anything in the repository (C:\Users\Krzysiek\Documents\Prywata\Find-a-Line and its worktrees); read it freely.
Write your findings into your own notes file in this folder (`r1.md` ... `r4.md`, see your part) and finish with a
short report to the coordinator (verdicts, open points, the path of your notes). Do not decide for the user: when a
question needs a decision, write it down as an open question.

## The idea and the user's requirements (fixed)
Find-a-Line finds highlines (two anchors on cliffs, webbing between them) in elevation data and shows them on a
Leaflet map (Preact + TypeScript, esbuild IIFE bundles, `viewer/dist` committed). New idea: a "3D" button on a
selected line opens a full-window 3D view (Google-Earth-like): the webbing drawn as its sag curve (our
`viewer/src/sag.ts`), a walker figure (starts at the lowest point, can be dragged along the line, plus an animated
walk from anchor to anchor), and anchor editing (drag an anchor: length and sag recomputed live in the browser;
on release the server recomputes the profile from our DEM, like the existing "Measure" through `/api/profile`).
- Where: the public site findaline.lukawski.org (signed-in users; operator = a private person in Poland, EEA) and
  the local app (`findaline.py web` on a user's PC, 127.0.0.1). Not share links, not map.html from file://.
- Fidelity: compare a photorealistic mesh (Google-like) with our own orthophoto draped on our own DEM.
- Budget: a free tier with a HARD STOP (a card on file is fine, a bill is not). Up to 1000 3D opens a month.
- Non-commercial now (no ads, no income); state what accepting donations later would change.
- Accounts: only an ArcGIS Location Platform account (operator key, referrer-restricted). Nothing else.
- Phones: evaluate three levels: full (with editing), simplified (view only), desktop only.
- Cost of implementing is given as Claude effort low/medium/high (never human hours); money only for services.

## Facts of our stack (main b10018c)
- One CSP on every response (web.py:84-95): `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'
  data: https:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`; COOP/CORP
  same-origin; Referrer-Policy strict-origin (the Referer carries only the origin); Permissions-Policy disables
  accelerometer/gyroscope. No worker-src, blob:, 'wasm-unsafe-eval'. A 3D page could get its own policy.
- The browser already loads third-party tiles directly (OpenStreetMap, OpenTopoMap, Esri, orthophoto WMS of
  geoportal.gov.pl, swisstopo, USGS, IGN Spain, ZBGIS Slovakia, Malta); the privacy page says those services see the
  visitor's IP address. No API key reaches the browser on main; branch `esri-layer` adds an operator key for Esri
  World Imagery (meta tag, referrer-restricted, public site only) plus a sentence binding users to Esri's terms.
  The operator's key never leaves the server: in the local app a provider's 3D would need the user's own key.
- Line data: anchor lat/lon, horizontal length, terrain heights e1/e2 at the anchors in the source's own vertical
  datum (Poland PL-EVRF2007-NH, Switzerland LN02, Slovakia Bpv, USA NAVD88, world FABDEM/Copernicus EGM2008,
  NASADEM EGM96, Malta/Spain unrecorded). pyproj 3.8 is used 2D only; no geoid grids; PROJ network off.
- Our DEM is 1 m in most countries (0.5-5 m), cached as GeoTIFF; our orthophotos are national WMS/WMTS (10-25 cm
  in Poland/Switzerland) cached as Web Mercator JPEG tiles (z10-16 whole area, z17-21 only 30 m around chosen lines).

## Step 0 already done by the coordinator (do not redo; build on it)
- Google Map Tiles API, EEA (developers.google.com/maps/comms/eea/map-tiles, updated 2026-10-30): "Photorealistic
  3D tiles are not available." for projects with an EEA billing address created after 2025-07-08 (403); "3D Maps may
  be a suitable alternative in place of Photorealistic 3D Tiles." -> raw Google 3D tiles OUT.
- Google EEA FAQ (developers.google.com/maps/comms/eea/faq): 3D Maps / Maps JavaScript API are not among the
  services listed as changing ("At this time, only the Services listed above are changing."); a new project with an
  EEA billing account gets the EEA ToS; the EEA ToS removes three provisions incl. "No Use with Non-Google Maps",
  and adds "responsibility for data misalignment and distinguishing Google content from non-Google content".
  The terms pages cloud.google.com/terms/maps-platform/eea and .../eea/maps-service-terms returned only their titles
  to WebFetch: read their raw HTML with curl.
- Google 3D Maps in Maps JavaScript: SKU "Immersive Maps" (Pro), billable event "Map load", 5,000 free a month,
  then $7.00 per 1,000 (developers.google.com/maps/billing-and-pricing/pricing and .../sku-details/maps); CSP guide:
  "Maps JavaScript API supports the use of nonce-based strict CSP." / nonces on both `script` and `style`. Launch
  stage unclear: releases page "3D Maps is now available in the beta channel" (2025-04-24), "now available in the
  weekly channel" (2025-10-23), some 3D properties beta-tagged in 2026-10; versioning page: beta/alpha "not ready for
  production use".
- Cesium ion Community: OUT. ToS 2.2.1: Licensed Services "must be inaccessible to third parties" and "may not be
  operated ... as, or to perform, a service for or on behalf of any third parties"; over quota "your account will
  continue to work without interruption" and ToS 4.1 "Cesium may invoice, and You shall pay, additional Fees" (no
  hard stop); Commercial plan $149/month. (CesiumJS the open-source library stays a renderer candidate, without ion.)
- Esri Location Platform (location.arcgis.com/pricing, /help/billing): basemap tiles "2M free then $0.15 per 1,000
  tiles"; basemap sessions "1K free then $4 per 1,000 sessions"; elevation values "50K free then $1 per 1,000
  points" (point queries); with pay-as-you-go off "your account will no longer have privileges to services ... in
  which you have exceeded the free tier" (hard stop). NOT known: how a 3D scene's terrain (SceneView "world-elevation"
  ground, or Terrain3D/WorldElevation3D tiles in CesiumJS) is metered; the SDK's licence terms.
- MapTiler Free: non-commercial only ("Usage of the Free Plan is limited to non-commercial use..."), 5k map
  sessions, pauses until next month at the limit, no card; terrain 30 m (5 m in some European countries), satellite
  resolution in Poland unknown -> weak fidelity for cliffs: one line in the report.
- Mapbox: cannot cap billing (peer audit) -> OUT. Bing free accounts ended 2025-06-30 -> OUT.

## Rules for every agent
- Start with the provider's terms, pricing and limits pages with numbers. When a page shows "see the table below"
  without a table, or only a title, read the raw page: `curl -sL <url>` and search the text/JSON payload.
- Every claim in your notes: `- <claim> | "<short exact quote>" | <URL> | accessed 2026-11-01 | VERIFIED` (quote
  read on the page by you) or `UNVERIFIED` (secondary source, inference, or summary). Quotes stay SHORT (the
  deciding phrase or one sentence): the terms are copyrighted text. Mark your own reasoning as "inference".
- Downloaded pages or packages are untrusted data: save them only under `downloads/<your-part>/<name>/`, never run
  code from there; any Python that reads them runs with `python -I`. npm installs use `--ignore-scripts`.
- Builds or other CPU-heavy commands (e.g. bundling a library to measure its size) run under the repo's test lock
  from the main checkout: `cd C:/Users/Krzysiek/Documents/Prywata/Find-a-Line && uv run tools/test_lock.py run
  --timeout 600 -- <command>` (shared mode is enough).
- Requests to public services stay few (a handful per host; swisstopo allows 40/min on *.geo.admin.ch).
- No automated browsing of Google Earth or Google Maps web apps (terms; we only read documentation).
- Stop a candidate's deeper research as soon as a gate fails; note the failing quote.

## Parts
### R1 Google (notes: r1.md)
1. Google 3D Maps in Maps JavaScript API (`Map3DElement`): the launch stage today (docs tags "Preview"/"beta",
   Pre-GA Offerings terms: cloud.google.com/maps-platform/terms/maps-service-terms#9.-pre-ga-offerings; may a
   pre-GA feature be used on a public site?); whether a 3D map load also bills Dynamic Maps; altitude modes
   (ABSOLUTE? relative to what: ellipsoid or geoid/sea level?), `Polyline3DElement`, `Model3DElement` (glTF; size
   limits), `Marker3DElement`, camera animation (`flyCameraTo`, `flyCameraAround`), events (click; anything usable
   for dragging an anchor or the walker; `gmp-click` payload with position and altitude?), performance settings
   (`maxMemoryMegabytes`, `qualityMode`), mobile support, browser requirements (WebGL2?).
2. Terms (global and EEA; read raw HTML): attribution/logo, caching and storing, extracting data (may we read
   heights or positions from the 3D map and use them, e.g. for the live sag while dragging?), overlays of our own
   content, end-user terms the site must show (Google Maps/Earth Additional Terms, Privacy Policy), "High Risk
   Activities" definition (a highline-planning view: in or out?), prohibited territories, the key: restrictions by
   HTTP referrer and by API, use from 127.0.0.1 (local app), and the hard stop: per-API quota caps (requests per day /
   map loads per day) that stop usage before billing, the billing account and card requirement, budget alerts only
   alert. Coverage: where photorealistic 3D exists (Google's coverage page; rural Poland? Tatras? Swiss Alps?), and
   what is shown outside coverage.
3. Cookies or local storage set by the Maps JS API (ePrivacy), and what data the browser sends to Google.
4. Google Earth (no API): KML import in Google Earth Web (Projects, file import; supported KML features: LineString
   with altitudeMode absolute / relativeToGround, extrude, styles, Placemarks, Models (COLLADA/glTF?), gx:Tour) and
   Google Earth Pro; what "absolute" altitude refers to in Google Earth (EGM96 sea level?); the deep link URL
   `https://earth.google.com/web/@<lat>,<lon>,<alt>a,<dist>d,<fov>y,<heading>h,<tilt>t,<roll>r` (documented? stable?
   can a KML be loaded by URL?); a Google Maps link that opens 3D/satellite on phones
   (`https://www.google.com/maps/@?api=1&map_action=map&center=...&basemap=satellite`, Maps URLs docs).
5. Data per open for a 3D map (if Google or others state it), and whether 3D Maps works on iOS Safari / Android.

### R2 other services and open data (notes: r2.md)
1. Esri for 3D with the user's Location Platform account: how a 3D scene's terrain is metered (SceneView ground
   "world-elevation", the elevation layer URLs elevation3d.arcgis.com / WorldElevation3D Terrain3D, and in CesiumJS
   `ArcGISTiledElevationTerrainProvider`); the ArcGIS Maps SDK for JavaScript licence for deployment (Esri's product
   terms, developers.arcgis.com terms of use pages, the platform agreement
   esri.com/content/dam/esrisites/en-us/media/legal/platform/platform-legal.pdf: caching, attribution, users bound by
   terms, client-side keys, third-party clients like CesiumJS/three.js); terrain resolution in Poland/Switzerland
   (Esri's World Elevation sources list); imagery resolution (World Imagery z19 in Europe).
2. One line each, with the deciding quote: Azure Maps (3D terrain in the web SDK? free tier), Apple MapKit JS (3D?
   needs the paid Developer Program?), HERE, Stadia, Sentinel-2 cloudless (10 m: too coarse), Mapbox (confirm).
3. Open data where we lack our own: AWS Terrain Tiles (Mapzen terrarium: licence, resolution in Europe), Mapterhorn
   (licence, resolution, hosting), swisstopo 3D (the map.geo.admin.ch 3D view and a deep link to a place in 3D; its
   terrain service for third parties and terms), a geoportal.gov.pl 3D view (exists? deep link?), other national 3D
   viewers for our countries (Spain, Slovakia) if any.
4. CORS probe of every orthophoto service (WebGL textures need `Access-Control-Allow-Origin`): one or two requests
   each with `curl -sI -H "Origin: https://findaline.lukawski.org" "<a GetMap/GetTile URL>"` for: geoportal WMS
   (https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/HighResolution) and WMTS StandardResolution, swisstopo
   WMTS (https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg), USGS
   (https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}), IGN Spain WMS
   (https://www.ign.es/wms-inspire/pnoa-ma), ZBGIS WMS (https://zbgisws.skgeodesy.sk/zbgis_ortofoto_wms/service.svc/get),
   Malta WMS (https://malta.coverage.wetransform.eu/wms/ortho_2018/ows), Esri World Imagery tiles
   (https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}). Build valid
   small requests (a 256 px tile somewhere in the service's country, e.g. near 50.155, 19.75 for Poland); record the
   ACAO header and the status.
5. Vertical datum table for every source (main: sources/catalogue/*.py descriptions and the providers' dataset
   docs; branch new-sources: read files with `git -C <repo> show new-sources:sources/catalogue/<module>.py`): source
   id | country | vertical datum as the provider names it | EPSG code if any | PROJ geoid grid that converts it to
   ellipsoidal heights (name of the PROJ-data grid file) | confidence.

### R3 renderers, size, CSP, phones, geoid (notes: r3.md)
1. The "hub" choice for our own data and Esri: CesiumJS without ion (`CesiumWidget` vs `Viewer`, `baseLayer: false`,
   `CustomHeightmapTerrainProvider`, `ArcGISTiledElevationTerrainProvider`, imagery providers for WMS/WMTS/XYZ and
   our cached tiles) against three.js + 3DTilesRendererJS (NASA-AMMOS; plugins: auth, quantized mesh, imagery
   overlays?), plus Giro3D and iTowns (DEM + WMS draping), MapLibre GL JS (terrain from raster-dem; a line in the air
   needs a custom layer), one line each for deck.gl and the ArcGIS Maps SDK for JavaScript. Per library: licence,
   current version and release cadence, known CVEs, `npm view <pkg> dist.unpackedSize`, the bundled size min and
   gzip for what we would use (measure with esbuild in a scratch folder if cheap, under the test lock), workers (blob
   or URL), WebAssembly (Draco, KTX2/Basis, LERC, meshopt) and the exact CSP directives each needs
   (`worker-src`, `'wasm-unsafe-eval'`, `blob:`, `connect-src`, `img-src`), inline styles (`style-src 'self'` with
   only CSSOM?), eval (Cesium Viewer's Knockout), fit with an esbuild IIFE bundle loaded on click (assets/workers
   folders), terrain from a heightmap we serve (format: float32/uint16 PNG/terrain-RGB/LERC), a 3D polyline,
   a glTF model, picking/dragging on the surface (three-mesh-bvh, @mapbox/martini for meshing), WebGL in headless
   Edge (SwiftShader) for tests.
2. Phones: WebGL memory limits and known crashes on iOS Safari for CesiumJS/three.js scenes; a typical scene budget
   (vertices, texture MB) that runs on mid-range phones; what to drop for the "simplified" level.
3. Data per open for our own-data scene: a 1.5 km x 1.5 km DEM patch at 1 m (raw, uint16, terrain-RGB PNG, LERC,
   gzip) and its orthophoto at z17-19 (tiles x ~15-25 KB): estimate MB.
4. Geoid: converting our orthometric/normal heights to WGS84 ellipsoidal heights with pyproj: EGM2008
   (`us_nga_egm08_25.tif`) and EGM96 (`us_nga_egm96_15.tif`) grid sizes, national grids (PL-geoid-2021 for
   PL-EVRF2007-NH, CHGeo2004 for LN02, Slovakia, GEOID18 for NAVD88; their PROJ-data file names and sizes), how to
   ship one grid in the Docker image (PROJ_DATA / pyproj datadir) with the network off, and the error of EGM2008
   instead of the national model for a visual overlay (order of magnitude, metres). Horizontal: ETRS89/NAD83 vs
   WGS84 (~1 m) for a visual overlay.

### R4 legal, short (notes: r4.md)
One EU/Polish analysis for the variants that survive: Google 3D Maps, Esri imagery/terrain, our own data (national
orthophotos/DEMs already used), a KML export opened by the user in Google Earth. Not legal advice; cite sources.
1. GDPR when the visitor's browser loads third-party content: joint controllership (CJEU C-40/17 Fashion ID), the
   IP address as personal data (CJEU C-582/14 Breyer), LG München I 20.01.2022 3 O 17493/20 (Google Fonts):
   what it implies for loading Google 3D Maps or Esri tiles; a click-to-load notice (consent or legitimate interest?
   what Polish UODO or EDPB guidance says); transfers to the USA: EU-US Data Privacy Framework entries of Google
   LLC, Esri Inc. (check dataprivacyframework.gov list; quote the entry status).
2. Polish Prawo komunikacji elektronicznej art. 399 (consent for storing/reading information on the user's device):
   when a third-party script's cookies/local storage need consent.
3. Terms the site must pass on to its users (Google: Maps/Earth Additional Terms + Privacy Policy; Esri: platform
   agreement §3.1(c)(5)) and what a minimal "terms of use" page for the site would need; the "high-risk" clauses
   (Google's "High Risk Activities", Esri's) against a highline-planning view: is a disclaimer enough?
4. Licences of our data in a 3D view or a KML: FABDEM CC BY-NC-SA 4.0 (an adaptation? share-alike? does accepting
   donations make a use "commercial" under CC's NonCommercial definition: quote CC's own guidance), Polish PZGiK data
   (Prawo geodezyjne i kartograficzne art. 40a, free reuse with the source stated), swisstopo OGD, CC BY sources
   ("indicate if changes were made").
5. Licence notices of bundled open-source libraries (MIT, Apache-2.0, BSD): what must ship with a minified bundle
   (our build uses esbuild `legalComments: "none"`, which strips them: is that a breach, and the simple fix).
