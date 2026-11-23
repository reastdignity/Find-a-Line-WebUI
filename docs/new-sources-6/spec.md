# Batch 6 of the new sources: what stays unbuilt

Written 2026-11-16 at the end of batch 6 (docs/roadmap.md, "Batch 6"), so that a later session builds each source
below without new decisions. Each section gives the user's decision in his words with its date, the data and their
licence as the batch's research read them (wave 0, 2026-11-15, unless another date is given), the access, what is
built already, the catalogue entry to write as far as the facts settle it, the tests and the acceptance numbers, and
what blocks it today. A point the facts do not settle is marked **open** with what settles it. Mails are numbered as
in the user's private drafts (`local/mail-drafts.md`, never in the repository): only their numbers and subjects are
named here.

Rules every section follows (the repository's, not new): a mirror dataset's product has the CRS, pixel size and
origin of its catalogue layer, and its source's default resolution is a whole multiple of the pixel, at least 1 m,
with `grid_origin` equal to the product's origin and the source working in the product's CRS
(`tests/test_mirror_tiles.py::test_datasets_match_the_catalogue`); `tools/mirror_tiles.py` cuts a product once, when
every input is there, and a changed input is a new edition; the public site reads mirror datasets only through the
hosted mirror (its specification: `docs/mirror-hosting/` in `main`); a new source gets `tools/check_source.py`, the
probe (`findaline.py sources check <id>`), a regression entry where its terrain holds a line (the user's rule of
2026-11-15: otherwise coverage-only, guarded by unit tests and data checks), its coverage area and a row of the area
download window, and every quirk a later change must keep goes into `.claude/rules/providers.md`.

## 1. Portugal: the mainland and the Azores (mirror datasets)

**Decision.** The user, 2026-11-15: "Portugal envs are set. I choose my mirror"; on the extent, "option b)" (the whole
mainland and the Azores, terrain and surface); on the cutting, "do it there"; on the server plan, "server fetches and
cut all", "folder where script will be placed", "hosted mirror", "i will delete them by hand", "start and mail in
parallel". So: fetched with the user's CDD account by `tools/cdd_fetch.py` and cut by `tools/mirror_tiles.py` on the
user's home server, everything under the folder of the script; this PC and the site read the tiles only through the
hosted mirror; the tools delete no fetched file (the user does, once a product is final and verified).

**Data.** DGT's data centre (CDD, https://cdd.dgterritorio.gov.pt), the national lidar survey of 2024 and the Azores'
of 2024 (docs/source-survey/europe.md, "Portugal"):

| Collection | What | Pixel | CRS | Files |
| --- | --- | --- | --- | --- |
| MDT-50cm, MDS-50cm | the mainland's terrain and surface | 0.5 m | EPSG:3763 (PT-TM06) | 1 km sheets ("Seccionamento de 1000 m x 1000 m"), float32, nodata -999, strips of 2000 × 1, uncompressed: Sintra's MDT-50cm-090203-07-2024 v01 16 012 379 B; pixel edges on whole metres |
| ACORES-MDE-1, ACORES-MDS-1 | the Azores' terrain and surface | 1 m | per island group (below) | float32, nodata -32767, strips of 1600 × 1 (1.6 × 1.0 km at Sete Cidades: 2024_SMG_PDL_27-1-4-5_01_MDE, 6 408 586 B) |

The whole fetch: 186 034 GeoTIFFs, 2.94 TB (`cdd_fetch.py plan`, 2026-11-15); est. about 1 TB as mirror tiles.
The Azores' CRS: Flores EPSG:5014, PTRA08 / UTM 25N (the survey of 2026-10-31); São Miguel's file carries a BOUNDCRS
"PTRA08 / UTM zone 26N" with the ID EPSG:32626 (wave 0, to confirm; the survey: the central and eastern groups
probably EPSG:5015). **Open**, settled by the first fetched files: each island group's CRS and the island codes the
manifest holds (the fetch names folders by island code: SMG, TER, GRA appear in `tests/test_cdd_fetch.py`). The
vertical datum is stated nowhere (DGT's standard is Cascais, EPSG:5780); **open**, to learn from DGT (mail 36) or by
a comparison with FABDEM on flat ground (as Austria's, docs/roadmap.md).

**Licence.** Every collection's `license` field: "CC-BY-4.0" (GET https://cdd.dgterritorio.gov.pt/dgt-be/v1/collections,
2026-11-15). The CDD's "Sobre": "The geographic information downloaded from the Data Center is subject to a CC-BY 4.0
usage license, which allows the free use of the data with the sole requirement of acknowledging that the owner of the
information is the Directorate-General for Territory." SNIG record 077a8c94-8b46-4a8a-8796-0d7fc4662f0c: "Acesso
público sem restrições"; "Licença de utilização - CC-BY-4.0". No numeric limits were found; the legal notices: "A DGT
reserva-se o direito de recusar ou retirar o acesso ao seu site, em qualquer momento e sem aviso prévio, aos
utilizadores que não cumpram os Avisos legais." The Azores have no SNIG record: their CC BY 4.0 rests on the
collections' field (**open**, to confirm with DGT, mail 36).

**Access.** `tools/cdd_fetch.py` (built; `tests/test_cdd_fetch.py`): `plan` walks the public search, `fetch` signs in
through the Keycloak form with `CDD_USER` and `CDD_PASSWORD` from an env file beside it (at most 6 sign-ins an hour),
one file at a time with a pause, 1.5 s between requests to a host; in a stock Python container whose restart policy
stays "no". Then `tools/mirror_tiles.py` on the same server in a container of the project's image with the clone's
`tools/` mounted (`.dockerignore` keeps it out of the image), `--inputs` the fetch's `downloads/`. The fetch takes the
collections in order (mainland terrain, mainland surface, Azores), so a mainland model can be cut while the next is
fetched. Est. two weeks of fetching.

**Built.** `tools/cdd_fetch.py`; `tools/mirror_tiles.py` with `Fetched` inputs (a collection of `manifest.jsonl`, each
file an input once `done.jsonl` records it whole); `GridTiles(origin=)`; the `portugal` catalogue module (Madeira and
its islets); FAMILIES has `portugal` before `spain`, whose offline box holds Portugal.

**To build.**
1. `DATASETS` in `tools/mirror_tiles.py`:
   - dataset `portugal`: products `dtm` and `dsm` at 0.5 m in EPSG:3763, origin (0, 0) (pixel edges on whole metres;
     confirm on the first files), `nodata=(-999.0,)`, inputs `Fetched("portugal", collection="MDT-50cm")` and
     `"MDS-50cm"`, overlap "first" (one sheet per place: the fetch keeps the newest version of each sheet);
   - the Azores: one product per island group in its own CRS, at 1 m, `nodata=(-32767.0,)`, inputs from
     `ACORES-MDE-1` and `ACORES-MDS-1`. `Fetched` selects a whole collection today, so it gains a filter by the
     fetch's folder (the island code) to split a collection by CRS: a small change of the tool, with its test.
   - Each dataset's record: provider DGT, licence CC BY 4.0, attribution from the CDD's sentence above, the changes
     made (cut into 2 km tiles, LERC within 5 mm), `not_endorsed` "DGT".
2. Catalogue (`sources/catalogue/portugal.py`): today the mainland and the Azores take `europe` (FABDEM / Copernicus,
   30 m); the new sources replace it there, Madeira's sources stay as they are.
   - The mainland: a source (id **open**: `portugal` is the module's name; ids are English names) with mirror
     `GridTiles` for both models (`portugal/dtm/0.5m`, `portugal/dsm/0.5m`), countries ("pt",), CRS EPSG:3763,
     default resolution 1 m, fallback `europe`; offline box (36.95, 42.16, -9.56, -6.19) (wave 0); sample and
     regression place at Sintra (38.787, -9.39) or Arrábida (38.47, -8.98) (wave 0, approximate); orthophoto the WMS
     https://geo.dgterritorio.gov.pt/wms/ortos2025 (layer `Ortos2025-RGB`, "no conditions apply", found 2026-11-14).
     Neighbours **open** (`spain` is the candidate: `tools/border_study.py boxes` decides).
   - The Azores: region pt-20 (the survey's code), a source per island group's CRS (a source works in one CRS), each
     chosen by its boxes; São Miguel's offline box (37.69, 37.92, -25.88, -25.12) (wave 0), the others' from their
     tiles; sample Sete Cidades (37.86, -25.79).
   - Credits from DGT's sentence; the README rows by `tools/source_docs.py`; coverage areas (the Azores' groups need
     outlines: `tools/coverage_shapes.py` `CUT` from PT-20 by boxes, as Madeira's groups).
3. Tests: `tests/test_mirror_tiles.py` (the datasets against the catalogue), `tests/test_catalogue.py` (declared
   sources and paths), a cut of a small fake `Fetched` folder per product; regression entries with `needs_path`.

**Acceptance.** `plan` ends near 186 034 files and 2.94 TB (2026-11-15); every product final and `verify` ok;
`tools/check_source.py` PASS at the samples (shift against FABDEM and Copernicus, valid share, tiles against the
mirror's files, alignment); the probe answers; regression entries on the OSM coastline (docs/regression-tests.md,
item 5), skipped without their folders.

**Blocks today.** The fetch and the cut on the user's server; the hosted mirror (this PC reads these datasets only
through it). DGT's answer to mail 36 does not block the bulk copy, which CC BY 4.0 covers.

## 2. Wallonia (mirror datasets)

**Decision.** The user's pick, 2026-11-15: "Wallonia"; the approved plan's choice 1 a (no letter given, so the
recommended option stands): the five province ZIPs per model in EPSG:3812; on the server: "Also i would like do it
with wallonia", "server fetches and cut all". So: fetched by `cdd_fetch.py fetch-list wallonia` and cut on the
user's server, read through the hosted mirror. Changed on 2026-11-21: the server only fetched (all ten ZIPs and the
fetch's state files, 2026-11-20); the cut and the publish run on the PC that holds the master. On 2026-11-22: "lets
change, and cut it to 1m resolution", and on which resolutions: "1 m only"; the publishing row: "Approve this
wording". So both products are cut and published at 1 m only, each pixel the mean of the valid 0.5 m pixels of its
2 x 2 block.

**Data.** SPW, "Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022" (record
https://geoportail.wallonie.be/catalogue/a004e570-99d6-4fe5-b83d-49b774409278.html) and "... Modèle Numérique de
Surface (MNS) 2021-2022" (record .../5a4c28fe-d30c-493e-861e-a80ebc703b64.html): 0.5 m, lidar of 19/02/2021 to
05/03/2022, EPSG:3812, heights "Deuxième Nivellement Général (EPSG:5710)", "précision altimétrique ... de l'ordre de
0,12 m", the MNT "brute, non lissée". Ten ZIPs (the province ZIPs in EPSG:3812, addresses and sizes in
`tools/cdd_fetch.py` `LISTS`, read 2026-11-15): 13.9 to 67.3 GB each, 469.6 GB together. Not the EPSG:31370 files
(three provinces only, older than the corrections of 2024-01-23) nor the whole-region ZIPs. **Inspected** on
2026-11-21 (three of the ten ZIPs): Deflate (zipfile unpacks it, no 7-Zip); one raster per ZIP,
`RELIEF_WALLONIE_MNT_50CM_2021_2022.tif` or `..._MNS_...` (the same member name in every province's ZIP of a model),
beside a .tfw, an .aux.xml, a .lyr, a .qml, the licence page and a PDF; float32, LZW, full-width strips of 5-8 rows
(131 208 x 62 818 px Brabant wallon, 250 833 x 195 069 px Hainaut), no overviews, AREA_OR_POINT=Point; EPSG:3812;
0.5 m pixels with edges on whole half-metres (origin (0, 0); the MNT and MNS of one province on one transform); nodata
-9999 (the tag and READ_ME.txt). The provinces are rectangles whose boxes overlap, nodata outside the province: the
MNS of Brabant wallon and Hainaut over their whole shared box hold 104 507 pixels valid in both, every one identical
(largest difference 0.0). The .aux.xml histograms reach -136.7 m (Brabant wallon's MNT, whose lowest ground is about
30 m): artifacts may exist, not measured yet (gate G2).

**Licence.** Both records: "Licence CC-BY 4.0 : L'utilisateur peut utiliser et modifier les données pour en dériver
une œuvre. Il peut publier les données et l'œuvre dérivée à condition de citer les sources."
(https://creativecommons.org/licenses/by/4.0/; read 2026-11-15). The MNT record: "Les réutilisations sont autorisées
moyennant citation de la source et mention explicite des modifications apportées à la donnée." Credit, verbatim:
"Source : Service public de Wallonie (SPW) - Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022
(2024-01-23) https://geodata.wallonie.be/id/a004e570-99d6-4fe5-b83d-49b774409278" (the MNS's the same with its title
and id). The MNS record's ordering text asks for a hard disk above 20 Go, against the direct ZIPs on the same page;
mail 32 is a notice to SPW of the download.

**Access.** `tools/cdd_fetch.py fetch-list wallonia` (built): no login; the server ignores Range, so a broken file
starts again; each size must equal the list's.

**Built** (2026-11-23, the task of local/wallonia-2026-11-21):
1. `DATASETS["wallonia"]` (`tools/mirror_tiles.py`): products `dtm` and `dsm` at 1 m in EPSG:3812, origin (0, 0),
   inputs `Fetched("wallonia", group="MNT", members=("*.tif",))` and `group="MNS"`, `nodata=(-9999.0,)`,
   `overlap="agree"`, no floor, `average=2`: the tool's new `Product.average` (the inputs' pixel is res / average;
   footprints, masks and the overlap rule on the 0.5 m pixels, then each pixel the mean of the valid ones of its
   block, `_block_means`; the products of before cut bit for bit as before). The card names every change (the mean,
   the cut, the join, the masks, LERC) as the MNT record asks; `PUBLISHABLE["wallonia"]` (`tools/mirror_publish.py`)
   with the approved wording.
2. Catalogue `sources/catalogue/belgium.py`: the source `wallonia` (country "be", region be-wal, Nominatim's
   "Wallonie"), mirror `GridTiles` at `wallonia/dtm/1m` and `wallonia/dsm/1m`, default resolution 1 m, each layer its
   record's credit; `bbox` the region's rectangle (49.49, 50.82, 2.83, 6.41: the neighbours' fill and the area
   download over all of Wallonia), offline a staircase of 38 boxes inside the region's outline, so French and
   Flemish places keep their choice of before offline; `belgium` after Luxembourg in FAMILIES (Arlon and Martelange
   stay in Luxembourg's box offline); orthophoto SPW's ORTHO_LAST as its WMS (checked live on 2026-11-23: the
   capabilities and a JPEG of Freyr)
   (https://geoservices.wallonie.be/arcgis/services/IMAGERIE/ORTHO_LAST/MapServer/WMSServer, layer 0, EPSG:4326),
   credit "Source : Service public de Wallonie (SPW) - Orthophotos - Vues aériennes les plus récentes (2025-09-20)
   https://geodata.wallonie.be/id/dfc9f3a2-adff-4b7f-ab77-8a890c4cabbb"; sample the Rochers de Freyr (50.218, 4.894).
   Neighbours by `tools/border_study.py boxes` (2026-11-23): every candidate touches, each direction at 100 % but
   Wallonia's grid towards North Rhine-Westphalia (71 %: its boxes stop at 6.20 E between 50.32 and 50.75 N; a
   border box (50.38, 50.75, 6.00, 6.20) gives 99.8 %). Declared both ways (each lists it last): `luxembourg`,
   `north_rhine_westphalia` with that border box (the user, 2026-11-23: "Add NRW") and `netherlands`; not `france`
   and `rhineland_palatinate` (six each, the cap; the user, 2026-11-23: "Leave it, note in roadmap": docs/roadmap.md,
   batch 6).
3. The coverage area be-wal (Natural Earth's five Walloon provinces, `tools/coverage_shapes.py` `MERGED`), README's
   rows, `tools/raster_overlap.py` (the seams and low values of the inputs, for G1 and G2), the tests.

**Left.** G1 (`raster_overlap.py` on every neighbouring province pair of each model) and G2 (the low values per
province; a floor only on the user's word after them, which changes the publishing row's sentence); the cut on the
PC (`tools/mirror_tiles.py all wallonia`), `verify`, the publish; then `tools/check_source.py` and the probe at
Freyr, and the regression entry (R94: the Rochers de Freyr, radius 800 m, lines 20-150 m, `needs_path`; Rocher
Bayard, Marche-les-Dames, Comblain-au-Pont and Hotton for the checks).

**Acceptance.** Ten ZIPs of the listed sizes; both products final and `verify` ok; `check_source` PASS at Freyr; the
regression entry's lines checked on the map (Freyr's walls over the Meuse).

**Blocks today.** The gates G1 and G2, then the cut and the publish from the PC (the inputs complete since
2026-11-22). Mail 32 is a courtesy notice, not a condition.

## 3. Valle d'Aosta's surface model

**Decision.** The user's pick, 2026-11-15: "Valle d'Aosta, surface model"; gate 0, 2026-11-15, "5. a": mail 29 asks
the region for one file, as for the terrain (not the sections clicked by hand, option b).

**Data.** "DSM 2005 /2008 AGGREGATO - QUOTA ORTOMETRICA"
(https://metadati.partout.it/metadata_documents/DSM_2005_2008_ORTOMETRICA.pdf): "Formato: *asc e *xyz (passo 2)
*geotiff (passo 10 e 25)", EPSG:23032; the 2005 0.5 m DSM degraded to 2 m in the Dora valley joined with the 2008
2 m DSM. Today only one ZIP per map section, `https://geoprodotti.regione.vda.it/download/DSM0508_002/DSM0508_002_<sezione>.zip`,
found through an Identify on the region's QDU MapServer (layer 8); `DSM0508_002_UNICO.zip` answered 404 (one HEAD,
2026-11-15). Count and sizes of the sections unknown.

**Licence.** CC_BY_DSM_v2.pdf (http://metadati.partout.it/metadata_documents/CC_BY_DSM_v2.pdf; CC BY 4.0 by DGR 1620
of 25 November 2016 and DGR 899 of 27 June 2014): "Modificare - remixare, trasformare il materiale e basarsi su di
esso per le sue opere; per qualsiasi fine, anche commerciale."; "Deve riconoscere una menzione di paternità adeguata
su tutti gli elaborati che utilizzeranno dati estratti dal Modello Digitale delle Superfici (DSM), apponendo la
seguente dicitura: Dati estratti dal Modello Digitale delle Superfici (DSM) della Regione Autonoma Valle d’Aosta.";
"Deve fornire un link alla licenza e indicare se sono state effettuate delle modifiche." Limits as the DTM's ("non
per download massivi"). **Open**: the server holds two licence PDFs for the DTM (CC BY 4.0 and a CC BY 2.5 Italia
one): check which one the DSM's record links before publishing.

**Built.** `aosta_valley` (the DTM only, mirror `aosta/dtm/2m`, `GridTiles` origin (0, 1)) and the `aosta` dataset of
`tools/mirror_tiles.py` (a dict of before: one URL, one product, its published card `AOSTA_CARD`, which says "The DSM
follows later").

**To build.** A second product `dsm` at 2 m under `aosta`: the dataset becomes a `Dataset` record with two products
whose one card covers both and states the changes per product, the DTM's index keys and tiles unchanged; input a
`Url` of the one file (or `Placed` if it comes by hand), the ASCII grid copied into a tiled GeoTIFF first as the DTM;
origin probably (0, 1) like the DTM (**open**: from the file). `aosta_valley` gains its `nmpt` (mirror
`aosta/dsm/2m`), credit with the DSM's sentence.

**Acceptance.** `verify` ok; `check_source` PASS for the surface at Arnad; R81 run again: its lines over trees marked,
re-baselined in the same commit with the reason.

**Blocks today.** The answer to mail 29 (the user sends it).

## 4. Thuringia

**Decision.** Gate 0, 2026-11-15, "7. a": mail 16 completed with four additions, the user sends it; built when the
server answers.

**Data.** TLBG / GDI-Th: DGM1 (2020-2025) and DGM1/DGM2 (2014-2019), a DOM per period, 1 km ZIPs such as
`https://geoportal.geoportal-th.de/hoehendaten/DGM/dgm_2020-2025/dgm1_32_<E>_<N>_1_th_2020-2025.zip`, an ATOM feed
`.../dienste/atom_th_hoehendaten_dgm` (17 127 entries per third parties; docs/source-survey/europe.md). On
2026-11-15 the feed and a ZIP's HEAD answered 200 with a 970 B HTML page ("*** Serviceinformation ***"), and
tlbg.thueringen.de and geoportal.thueringen.de answered "Link11 - CAPTCHA". **Licence** **open**: dl-de/by-2.0 "(c)
GDI-Th" per a third party; SAGA's documentation names both CC BY 4.0 and dl-de/by-2.0
(https://saga-gis.sourceforge.io/saga_tool_doc/9.13.0/io_webservices_13.html); the TLBG's DOP WMS says CC BY 4.0,
"Namensnennung: © GDI-Th". Also **open**, to learn from TLBG (mail 16): the DOM1's path, a path without the CAPTCHA
(or permission for scripts), whether the 2020-2025 period replaces whole tiles, and whether Range or HEAD may be
used.

**To build.** `ZippedTiles` as Saxony's, with a check of the answer's content type and the ZIP magic (a maintenance
page with status 200 must never be cached as a tile); the newest period per tile (or both, newest first, if 2020-2025
covers tiles in part); region de-th; neighbours the Länder whose boxes touch (`tools/border_study.py boxes`, the
six-neighbour cap). Regression place: none chosen yet (the truth check's `tools/truth_study.py places` ranks known
highlines per country).

**Acceptance.** Nothing settled beyond the standing checks (`check_source` PASS, the probe, the tiles' content type
and magic) until the host answers.

**Blocks today.** The host (maintenance page, CAPTCHA) and the answer to mail 16.

## 5. New South Wales, the ACT and South Australia's coast (ELVIS orders)

**Decision.** The user's pick, 2026-11-15: "New South Wales" and "ACT, South Australia's coast"; gate 0, 2026-11-15:
"manual download limitted to 15GB per request. Write mail including question about bulk download permision /
methods, i will send it." So no order until mail 34 (NSW Spatial Services: a re-tiled copy, the licence, bulk
download) and mail 35 (ELVIS: bulk download) are answered.

**Data.** ELVIS (https://elevation.fsdf.org.au/), orders by a drawn box, delivered by e-mail as a ZIP; per request at
most 15 GB (the user). NSW: one ZIP with folders 1m, 2m, 5m of TIFFs in 2 km tiles named with the MGA zone and AHD
(`Penrith201904-LID1-AHD_2806276_56_0002_0002_1m.tif`); "Each 1:100k map area ranges from around 2GB to 6GB"; "The
Sydney basin and Blue Mountains is around 50GB all up" (third-party figures); GDA94 or GDA2020 per file not confirmed.
ACT: 1 m DEMs of 2015 and 2020, MGA 55, AHD. SA: 1 m DTMs per survey (downloads.md's datasets of Fleurieu MGA54,
Kangaroo Island, Eyre Peninsula and the Yorke Peninsula MGA53). The boxes (south, north, west, east) chosen in wave 0
where Geoscience Australia's 5 m DEM (`australia`) has no data: ACT Booroomba Rocks (-35.58, -35.54, 148.95, 149.01),
Gibraltar Peak (-35.50, -35.46, 148.91, 148.97); NSW Blue Mountains (-33.80, -33.52, 150.20, 150.42), Bungonia
(-34.85, -34.77, 149.97, 150.06), the Warrumbungles (-31.33, -31.23, 148.93, 149.07; its lidar coverage not
checkable); SA's sea cliffs at Second Valley, Deep Creek, Granite Island, Admirals Arch, Cape Cassini, Cape
Willoughby, Whalers Way, Elliston, Point Labatt and Cape Spencer.

**Licence.** NSW (product description of 2018,
https://data.nsw.gov.au/data/dataset/8f73f5ca-4f7f-4707-bfe2-0efbb9027107/resource/c4d76ca7-70c7-42e0-b821-74627ea1d878/download/datasetproducttitle_digital-elevation-model.pdf):
"Spatial Services has applied the Creative Commons Attribution 3.0 Australia Licence. Spatial Services asserts the
right to be attributed as author of the original material in the following manner: © Spatial Services [date of
extraction]"; "All Intellectual Property which is owned by Spatial Services should only be loaded on any external
cloud platforms if Spatial Services’ Intellectual Property remains unchanged, maintained and preserved." So no
re-cut copy of NSW's data in a hosted mirror without Spatial Services' yes (mail 34); use on the user's own PC is not
in question. ACT (data.gov.au "2015 LiDAR"): "Creative Common By Attribution 4.0 (Australian Capital Territory)",
credit "(c) Australian Capital Territory and Aerometrex Limited". SA (data.sa.gov.au, "ELVIS Digital Elevation Model
Imagery Catalog"): "Information contained in this file is licensed under a Creative Commons By Attribution 4.0
Australia Licence"; per dataset the LICENSE field: the 2011 sets "SA GOVT", the 2007 south-east set "RESTRICTED TO SA
GOVT ONLY", the rest "Unrestricted, available for resale" (use only those).

**To build.** Mirror datasets from the delivered ZIPs as `Placed` inputs, one product per MGA zone (a product has one
CRS; a source works in one CRS, so a state with two zones has two sources or keeps to one zone's places); regions
au-nsw, au-act, au-sa (the pattern of `au-tas` and `au-qld`); fallback `europe` as `tasmania`'s, or `australia`
(GA's 5 m) first where it has data (**open**: `australia` has no data at the chosen places); ids **open** (English
names, as `tasmania`, `queensland`). Credits as quoted (NSW's with the date of extraction).

**Acceptance.** `check_source` PASS per dataset (the shift against FABDEM, the valid share); a regression entry at
Booroomba Rocks or the Blue Mountains and one of SA's sea cliffs, the coastal one on the OSM coastline.

**Blocks today.** Mails 34 and 35 (the user sends them); then the orders, at most 15 GB each.

## 6. Saint Vincent

**Decision.** The user's pick, 2026-11-15: "Saint Vincent"; a manual download, low priority (downloads.md), not made
yet.

**Data and licence.** USGS data release "Airborne lidar survey of St Vincent, Eastern Caribbean, following the
2020-21 eruption of La Soufrière Volcano" (Diefenbach, A., 2024, https://doi.org/10.5066/P13ZHRG3): "Rights This work
is marked with CC0 1.0 Universal"; the metadata: "Acknowledgement of the U.S. Geological Survey would be appreciated
for products derived from these data." `SVG_bare_earth_0.6m.tif` (49 874 rows × 31 089 columns, 6.2 GB as
uncompressed float32) and `SVG_bare_earth_1m.tif`; hydro-flattened bare earth; UTM 20N on WGS84 / ITRF2008 (taken as
EPSG:32620); heights EGM2008, 0.01 m; captured 2021-12-04 to 2022-02-17; "Ground voids exist due to cloud cover";
nodata not stated (metadata https://data.usgs.gov/datacatalog/metadata/USGS.65baeb12d34e18c6baf2df6c.xml).

**Access.** ScienceBase (https://www.sciencebase.gov/catalog/item/65baeb12d34e18c6baf2df6c) answers scripts with a
Cloudflare challenge (403): the user downloads the file in a browser; its file list was not seen.

**To build.** A mirror dataset from the placed file (`Placed`), CRS EPSG:32620, origin from the file. **Open**: the
0.6 m file needs a default resolution of 1.2 m (a whole multiple of the pixel, at least 1 m); the release's own 1 m
file fits a 1 m search; "native resolution" (the user's words of 2026-11-15) points to the 0.6 m one. A source for
the country "vc" (id **open**), offline box (13.11, 13.39, -61.29, -61.10), sample and regression place La
Soufrière's crater rim (13.335, -61.181), radius 1000 m, lines 30-300 m (wave 0, approximate), fallback `europe`, no
surface model; credit CC0 with the USGS acknowledgement.

**Blocks today.** The user's download.

## 7. Italy's national lidar (PST)

**Decision.** The user's pick, 2026-11-15: "Italy's national lidar - give link i will check": the user tries the
portal; nothing is built until he reports. What the user saw on the portal (also for Sicily) is not recorded in the
batch's notes.

**Data and licence** (docs/source-survey/europe.md, "Italy, national: MASE Geoportale Nazionale, PST LiDAR"): the
Piano Straordinario di Telerilevamento Ambientale (2008-2013), LiDAR DTM, DSM First and DSM Last at 1 × 1 m and
2 × 2 m in regional sets, mostly coasts, main rivers and risk areas; "Download Banca Dati PST"
(https://sim.mase.gov.it/portalediaccesso/mappe/#/viewer/new): areas selected on a map, up to 6 GB a request,
GeoTIFF. Licence: "I dati sono distribuiti con licenza" CC BY 4.0 (https://gn.mase.gov.it/portale/distribuzione-dati-pst),
while Toscana redistributes the Ministry's sheets under CC BY-SA 3.0 IT (to reconcile: `tuscany` credits MATTM's
sheets CC BY-SA). Products to tick (downloads.md): "LiDAR DTM Mosaic (Grid 1x1)" and "LiDAR DSM First Mosaic (Grid
1x1)", where they have no data the "Grid 2x2" ones; not DSM Last, Bathymetric, Terramare or InSAR. A trial area
first: San Vito lo Capo or Monte Pellegrino.

**To build** (after the trial's files are looked at): mirror datasets per region set from `Placed` files (CRSs differ
per region: EPSG:25832, 25833, 3003, 3004 and others are named in the survey), as the region's source or as a filler
before `tinitaly`. Nothing settled beyond that.

**Blocks today.** The user's trial on the portal.

## 8. Open decisions that would add work if answered "yes"

Each is the user's, recorded as open in docs/known-bugs.md or docs/roadmap.md ("Batch 6").

1. **Tokyo's island floor**, 2. **Hong Kong's datum**, 3. **Bremerhaven's surface model**: decided on 2026-11-16
   ("3. a", "5. a", "2. a" and "4. a") and built: a floor of -1 m on the island sheets only (`Layer.floor_of`, R92),
   every height lowered by 1.30 m on the grid (`Layer.height_offset`, R91 re-baselined), the surface shifted half a
   pixel onto the terrain's grid with the constant planes left (`TransformFix.shift`). The decisions:
   docs/roadmap.md, "Batch 6"; what each leaves behind: docs/known-bugs.md.
4. **A Deflate64 reader for Ontario's two projects.** CLOCA 2018's and SNC 2018-19's terrain packages (1 404
   members) are Deflate64, which zlib and zipfile do not read: their tiles come from older surveys or `canada`. A
   library is needed: the candidates are compared first (CLAUDE.md, "Libraries first") and the user decides; then
   `packages._readable` lists them and `ZipMember` inflates them per member by Range. Acceptance: their members
   listed and read; `check_source` PASS at a place of each project; R90 unchanged.
5. **A guard in `tests/regression.py --update`** against a baseline taken on the coastline fallback (the log line
   "Coastline: Copernicus water body mask (fallback)", docs/regression-tests.md item 5): refuse or warn unless the
   entry asks for `--coastline copernicus`. Acceptance: a test with a fake log; no checksum changes.

Also waiting, not a decision of the user's: **Hong Kong in the hosted mirror** needs CEDD's written yes (mail 33):
the CSDI terms allow to "browse, download, distribute, reproduce" but do not name modifying (portal.csdi.gov.hk,
read 2026-11-15). Until then `hong_kong` reads CEDD's files on demand and the public site has no copy.

## 9. Ireland: dropped

**Decision.** Gate 0, 2026-11-15: "2. c", dropped again (batch 5's gate 0 had dropped it; the user's pick of
2026-11-15 had brought it back).

**Why** (wave 0, 2026-11-15). The open lidar (GSI's Open Topographic Lidar, CC BY 4.0, "Contains Irish Public Sector
Data (Geological Survey Ireland) licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0)
licence") is nine programmes in five formats (mostly 2 m of 2006-2011; 0.125-1 m in one programme of 2007-2017).
Steep ground was found only at Howth (58 m within 14 m), the Copper Coast (55 m) and Dalkey (31 m); Bray Head and
Wicklow Head reach 21 and 27 m; nothing in the west: no tiles at the Old Head of Kinsale, Ailladie, Glendalough,
Ballykeefe, Black Head or Inis Oírr.
The road-corridor programme (TII, 5 767 km² of its own) holds no crag and lies 0.29 m off the grid; Phase 2's 144
tiles are 7z archives of lowlands (py7zr would bring 9 packages under LGPL). Composing the programmes needs new code.

**Reopen only with new facts**, for example a survey covering the western crags (Ailladie, Black Head).
