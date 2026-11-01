# Elevation sources: Europe (survey of 2026-10-31)

Notes of the survey in [../source-survey.md](../source-survey.md), one section per group of countries as researched; the rows are in [sources.json](sources.json).

Turkey and Russia have full rows in [asia.md](asia.md); the short notes below are from the first wave.

## Germany (g1-de): elevation sources, researched 2026-10-31

Germany has no open national 1 m model: the BKG's DGM1/DOM1 are fee products. Every Land publishes its own DGM1 as open data now (all 16; Saarland's download path unclear), under dl-de/zero-2.0 (NRW, Hessen, Berlin), dl-de/by-2.0 (BW, BB, RP, SN, ST, Saarland, Hamburg, Thuringia per some sources) or CC BY 4.0 (Bavaria, Lower Saxony, MV, SH, Bremen; Thuringia's own WMS). All allow commercial use and redistribution with attribution, so automatic download, caching and a public site are fine everywhere it works. All use ETRS89/UTM (zone 32, or 33 in BB, BE, MV, SN) with DHHN2016 heights, 1 m pixels with edges on whole metres (XYZ points at .5 m centres), cm or mm values.

**Shared delivery patterns (one driver could serve several Länder)**
- *Static 1 km GeoTIFF tiles + an index file*: the AdV naming `dgm1_32_<E>_<N>_1_<land>_<year>.tif` is used by NRW, RP, NI (and BB, TH in ZIPs). Index variants: **Metalink 4 (.meta4, URL + size + sha256)** in Bavaria and Rhineland-Palatinate (one "MetalinkTiles" class would serve both); an XML listing in NRW; a GeoJSON index in SH; STAC in NI; Apache listings in BB and RP.
- *2 km ZIP tiles on a fixed grid*: Baden-Württemberg (XYZ, odd E / even N), Saxony (GeoTIFF, even E/N, Nextcloud share), MV (ATOM-listed, also plain GeoTIFF), Berlin (ATOM, XYZ). A "remote GridTiles with ZIP members" class (with XYZ conversion) would cover BW, SN, BB.
- *INSPIRE WCS 2.0.1*: Hessen, Saxony-Anhalt, MV, NRW, BW, BB: `WcsTiles` as it is (axes `E N` or `x y`; ST answers multipart with a TIFF without CRS; MV encodes the sea as 0).
- *STAC*: Lower Saxony only (DGM1, DOM1, BDOM20 each with its own STAC API): `StacTiles`.

**Best candidates**: Bavaria (Alps + Franconian Jura; Metalink + GeoTIFF; DOM20), Saxony (Elbsandstein; fixed-grid ZIPs), Rhineland-Palatinate (Pfälzerwald; Metalink), Lower Saxony (STAC, effort S, Harz/Ith), Saxony-Anhalt (Harz Bodetal; WCS, effort S), Baden-Württemberg (Swabian Jura; XYZ ZIPs or WCS).

Helpers used to find endpoints (third-party, every claim checked against the Land's own server): the open-source projects `nico579/lidar2map` (providers/de_*.py) and `timohueser/OpenBikeComputer` (obc-dem sources/de.py). Scripts: `scripts/g1-de/probe.py` (remote raster / small ZIP), `local.py`, `wcs.py`, `wms.py`.

---

### Germany, national (BKG / AdV) – none
- **Data**: DGM1 and DOM1 for the whole country, compiled from the Länder. **Licence**: fee product, "Die Lizenzierung erfolgt gegen Entgelt über die Zentrale Stelle Geotopographie (ZSGT)"; shown price 8 000 EUR; free only for federal and state authorities. BKG open data has only DGM200/DGM1000. No HVD release of the national DGM1 found; the HVD obligation is met by the Länder. Use the Länder rows.
- **Links**: https://gdz.bkg.bund.de/index.php/default/digitales-gelandemodell-gitterweite-1-m-dgm1.html, https://sg.geodatenzentrum.de/web_public/gdz/dokumentation/deu/dgm1.pdf

### Bayern (LDBV) – high
- **Data**: DGM1 1 m statewide, replaced per lot ("losweise"); DOM20 (image-based, 20 cm, per flight, flight date in the TIFF tags), LAZ point clouds, DGM5. All OpenData products under CC BY 4.0 (`opengeodata_datensaetze.json`).
- **Access**: deterministic static files `https://download1.bayernwolke.de/a/dgm/dgm1/<E km>_<N km>.tif` (mirror `download2`), indexed by Metalinks per Gemeinde, Landkreis or the Land (`https://geodaten.bayern.de/odd/a/dgm/dgm1/meta/metalink/<key>.meta4`, sha256 + size + both mirrors) and a polygon-to-Metalink service (`geoservices.bayern.de/services/poly2metalink/metalink/dgm1?data=dgm1&service=polygon`, usage not checked); a REST Höhendienst. DOM20: `.../a/dom20/DOM/32<E>_<N>_20_DOM.tif` (Metalinks under `odd/a/dom20/meta/DOM/metalink/`).
- **Versions**: one file per tile, replaced in place, no year in the name: the sha256 of the Metalink (or Last-Modified) shows a change.
- **Licence**: "CC BY 4.0|https://creativecommons.org/licenses/by/4.0/deed.de" for every product; the WMS says "kostenfrei", "CC BY 4.0". Attribution wording on the Nutzungsbedingungen page (not read): expect "Bayerische Vermessungsverwaltung – www.geodaten.bayern.de".
- **Orthophoto**: WMS `https://geoservices.bayern.de/od/wms/dop/v1/dop20`, layer `by_dop20c`, EPSG:4326/3857/25832, CC BY 4.0, no watermark.
- **Quick tests**: DGM1 `673_5516` (Pottenstein) 2.65 MB, EPSG:25832 (horizontal only), origin (673000, 5517000), strips of 2 rows LZW, nodata -9999, cm (values 1 ulp off whole cm in float32), window 0.4 s; Metalink of Landkreis 09472: 1461 tiles; DOM20 `32674_5407_20_DOM.tif` 39.6 MB, compound 25832+DHHN2016, 256 px tiles (window reads work), cm, flight 23.05.2026; WMS GetMap 56 kB.
- **Fit**: a Metalink-indexed `IndexedTiles` subclass (shared with RP), or simply the URL pattern on the 1 km grid. DOM20 by `/vsicurl/` windows and local downsampling (5000 px tiles of 30–50 MB, never whole files).
- **Open questions**: Metalink per Kreis vs polygon service as the cached index; survey date per DGM tile (no year in the name; TIFF DATETIME only); DOM20 is photogrammetric (forest canopy fine, steep rock faces may be smoothed).

### Baden-Württemberg (LGL) – high
- **Data**: DGM1 and DOM1 (ALS, leaf-off, highest points) 1 m statewide; ALS of about an eighth of the Land per year, DGM updated 4×/year; bDOM only by e-mail.
- **Access**: static ZIPs `https://opengeodata.lgl-bw.de/data/dgm/dgm1_32_<E>_<N>_2_bw.zip` (2 km tiles at odd E, even N km) and `/data/dom1/dom1_32_<E>_<N>_2_bw.zip`; directory listing 403, so no index found (the portal's grid layer `zwei_km_gitter` was not located). INSPIRE WCS `https://owsproxy.lgl-bw.de/owsproxy/wcs/WCS_INSP_BW_Hoehe_Coverage_DGM1` (untested).
- **Format**: each ZIP (~15 MB) holds four 1 km XYZ grids (29 MB each unpacked, points at .5 m), a CSV per km tile (Aktualität, Fortführung, accuracy 0.15, DHHN2016/GCG2016) and the licence PDF.
- **Licence**: dl-de/by-2.0 (PDF in the ZIP; the DOP WMS: "Es gelten die Lizenzbedingungen dl-de/by-2-0 ... mit den dort geforderten Angaben zum Quellenvermerk").
- **Orthophoto**: WMS `https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LGL-BW_ATKIS_DOP_20_C`, layer `IMAGES_DOP_20_RGB`, 4326/3857, dl-de/by-2.0.
- **Quick tests**: Beuron: `dgm1_32_499_5322_2_bw.zip` 14.9 MB in 2.7 s, cm, survey 2016-04-06, updated 2022-03-24; DOM1 HEAD 200; WMS GetMap 82 kB.
- **Fit**: remote fixed-grid ZIP tiles with XYZ conversion (M), or `WcsTiles` if the WCS proves exact (S).
- **Open questions**: the WCS (limits, resampling); an index of existing tiles (or treat 404 as missing).

### Rheinland-Pfalz (LVermGeo) – high
- **Data**: DGM1 1 m (years 2022–2025 in names), DOM1, bDOM20 RGBI.
- **Access**: Metalink for the whole Land `https://geobasis-rlp.de/data/dgm1/current/meta4/dgm1_tif_07.meta4` (12 MB, ~21 160 tiles with sha256; also per Kreis/Gemeinde), files `.../dgm1/current/tif/dgm1_32_<E>_<N>_1_rp_<year>.tif` (+ .tfw), Apache listings; DOM1 `.../dom1/current/meta4/dom1_md_07.meta4`.
- **Licence**: dl-de/by-2.0 ("©GeoBasis-DE / LVermGeoRP <year>"); third-party code says zero-2.0, the GeoShop and the WMS say by-2.0.
- **Orthophoto**: WMS `https://geo4.service24.rlp.de/wms/rp_dop20.fcgi`, layer `rp_dop20`, 4326/3857, dl-de/by-2.0.
- **Quick tests**: `dgm1_32_412_5447_1_rp_2022.tif` (Dahner Felsenland) 1.8 MB, compound 25832+DHHN2016 (EPSG:7837), origin on whole km, LZW predictor 2, cm, 0.4 s; WMS GetMap 102 kB.
- **Fit**: the Metalink class shared with Bavaria (M).

### Niedersachsen (LGLN) – high
- **Data**: DGM1 and DOM1 1 m (ALS lots 2010–2025), BDOM 20 (2021–2026), several surveys per tile kept.
- **Access**: STAC APIs `https://dgm.stac.lgln.niedersachsen.de` (collection `dgm1`, asset `dgm1-tif`), `dom.stac...` (`dom1`), `bdom.stac...` (`BDOM`); COGs on IBM object storage `https://dgm1.s3.eu-de.cloud-object-storage.appdomain.cloud/<lot>/Vollkacheln/dgm1_32_<E>_<N>_1_ni_<year>.tif` with an XML of metadata (date, lot, accuracy 0.3, DHHN2016/GCG2016).
- **Licence**: STAC `license: CC-BY-4.0`; LGLN AGNB section 7 for open geodata.
- **Orthophoto**: `https://www.geobasisdaten.niedersachsen.de/doorman/noauth/wms_ni_dop` (in the portal's code) answered 400 "keine interne URL gefunden" to GetCapabilities: to recheck.
- **Quick tests**: STAC search at the Okertal 0.3 s; 2 items per point (2013, 2018); COG 4.8 MB, `LAYOUT=COG`, 512 px blocks, overview, mm, edges on whole metres; DOM1 2 items; BDOM items 2022-03-22 and 2025-04-03.
- **Fit**: `StacTiles` (new instance, newest per tile): S. "Vollkacheln" in the path suggests a survey replaces whole tiles.

### Sachsen (GeoSN) – high
- **Data**: DGM1, DOM1, nDOM 1 m in 2 km tiles, date per tile (Bastei: 2025-02-09).
- **Access**: public Nextcloud shares, `https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/JCcXyifaNdLDnxZ/dgm1_33<E>_<N>_2_sn_tiff.zip` (even km), DOM1 share `S6wwnFwX7882sZm`; the share ids and the municipality → tile grid (`grid_id`, `computed_not_existing`) are in `batchConfig.products` of the batch download page. GET works, HEAD and PROPFIND answer 401. INSPIRE ATOM only points to the web page.
- **Format**: ZIP ~15 MB: GeoTIFF 2000×2000 float32 LZW, EPSG:25833, values not rounded, + .tfw, .aux.xml, CSV with the date.
- **Licence**: "Datenlizenz Deutschland - Namensnennung - Version 2.0 (Namensnennung: Geodaten Sachsen)" (ATOM rights).
- **Orthophoto**: WMS `https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest`, layer `sn_dop_020`, 4326/3857, free; the Bastei sandstone towers are clearly visible.
- **Quick tests**: lattice at the Bastei (tiles 432/434 × 5644/5646), one ZIP 15.5 MB in 0.9 s, origin (434000, 5648000), 100% valid.
- **Fit**: remote fixed-grid ZIP tiles with a GeoTIFF member (M); the share token may change: read it from the batch page.

### Sachsen-Anhalt (LVermGeo LSA) – high
- **Data**: DGM1 1 m statewide; DOM/bDOM have a page, access not checked.
- **Access**: INSPIRE WCS `https://geodatenportal.sachsen-anhalt.de/ows_INSPIRE_LVermGeo_ATKIS_EL_DGM_WCS` (`Coverage1`, axes `x y`, EPSG:25832, extent 606000–790000 / 5646000–5882000); the portal gives 2 km tiles through an AJAX "prepare" link (5 at a time): not for scripts.
- **Licence**: WCS Fees: "Datenlizenz Deutschland Namensnennung 2.0 ... Quelle: © GeoBasis-DE / LVermGeo LSA".
- **Orthophoto**: WMS `https://www.geodatenportal.sachsen-anhalt.de/wss/service/ST_LVermGeo_DOP_WMS_OpenData/guest`, layer `lsa_lvermgeo_dop20_2`.
- **Quick tests**: 500 × 500 m at the Rosstrappe (Bodetal) in 1.0 s, multipart, GeoTIFF without CRS, 1 m, edges on whole metres, cm, 193–462 m.
- **Fit**: `WcsTiles` (multipart, CRS set by the source): S. Open: size limit, a DSM.

### Thüringen (TLBG / GDI-Th) – medium (untested)
- **Data**: DGM1 (period 2020–2025) and DGM1/DGM2 (2014–2019), DOM per period, 1 km ZIPs `https://geoportal.geoportal-th.de/hoehendaten/DGM/dgm_2020-2025/dgm1_32_<E>_<N>_1_th_2020-2025.zip`, ATOM `.../dienste/atom_th_hoehendaten_dgm` (17 127 entries per third parties).
- **Licence**: dl-de/by-2.0 per secondary sources; the TLBG DOP WMS says "Creative Commons BY 4.0 ... Namensnennung: © GDI-Th": to confirm on the download page (behind a CAPTCHA).
- **Quick tests**: the whole host `geoportal.geoportal-th.de` answered HTTP 200 with a 970-byte "Dieser Geodaten-Dienst ist im Moment leider noch nicht verfügbar" page (twice); DOP WMS `https://www.geoproxy.geoportal-th.de/geoproxy/services/DOP` worked.
- **Fit**: ATOM/URL pattern + ZIPs with two periods (M). A maintenance page with status 200 must never be cached as a tile.

### Nordrhein-Westfalen (Geobasis NRW) – medium
- **Data**: DGM1, DOM1 1 m (years 2020–2025 per tile), bDOM50 (LAS), nDOM50.
- **Access**: one XML index per product (`https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/`, 3.5 MB, 35 860 files with size and timestamp), files in the same folder; WCS `https://www.wcs.nrw.de/geobasis/wcs_nw_dgm`.
- **Licence**: dl-de/zero-2.0, "Jede Nutzung ist ohne Einschränkungen oder Bedingungen zulässig".
- **Orthophoto**: WMS `https://www.wms.nrw.de/geobasis/wms_nw_dop`, layer `nw_dop_rgb`.
- **Quick tests**: `dgm1_32_280_5652_1_nw_2022.tif` 2.4 MB, edges on whole km, cm, 0.4 s; WMS GetMap 36 kB.
- **Fit**: `IndexedTiles` over the index file (M).

### Hessen (HVBG) – medium
- **Data**: DGM1, DOM1 1 m; open data since 2022-02-01 "ohne Einschränkung oder Bedingung".
- **Access**: WCS `https://inspire-hessen.de/raster/dgm1/ows` (`he_dgm1`, coarser `he_dgm1_2`…`_32`), axes `E N`; files in the gds.hessen.de Downloadcenter (manual); no automatic DSM found.
- **Licence**: WCS Fees "Datenlizenz Deutschland – Zero – Version 2.0".
- **Quick tests**: 500 × 500 m at the Edersee in 0.5 s, GeoTIFF with CRS, mm, nodata -9999; DOP WMS `https://www.gds-srv.hessen.de/cgi-bin/lika-services/ogc-free-images.ows` (`he_dop20_rgb`) worked.
- **Fit**: `WcsTiles` as is (S).

### Mecklenburg-Vorpommern (LAiV) – medium
- **Data**: DGM1, DOM1 1 m in 2 km tiles (6407).
- **Access**: ATOM `https://www.geodaten-mv.de/dienste/dgm_atom` (dataset feed 15 MB with 6 formats per tile, e.g. `dgm_download?index=4&dataset=ca268792-s2q1-4a39-b34c-9ec5bf9a4469&file=dgm1_33_<E>_<N>_2_gtiff.tif`), `dom_atom` the same; WCS `inspire_el_dgm_wcs` (`mv_dgm`).
- **Licence**: CC BY 4.0 (LAiV fact sheets), "© GeoBasis-DE/M-V (Jahr der letzten Datenlieferung)".
- **Quick tests**: WCS at Königsstuhl (Jasmund) 0.7 s, mm, sea = 0 (no nodata); a GeoTIFF tile 16 MB uncompressed in 0.85 s; DOP WMS `https://www.geodaten-mv.de/dienste/adv_dop` worked.
- **Fit**: `WcsTiles` (S), sea 0 to be masked.

### Brandenburg (LGB) – low
- 1 km ZIPs (GeoTIFF, 25833+DHHN2016 compound, cm) in an Apache listing `https://data.geobasis-bb.de/geobasis/daten/dgm/tif/` (31 291) and bDOM `.../bdom/tif/` (31 896, 17–23 MB); WCS `el_dgm1_wcs`; dl-de/by-2.0 "GeoBasis-DE / LGB". Tested one ZIP (1.1 MB). Flat.

### Schleswig-Holstein (LVermGeo SH) – low
- GeoJSON index of 18 685 km tiles with direct links to plain XYZ text (27 MB per km; 3550 tiles still from 2005), bDOM 20 cm GeoTIFF index (17 614); CC BY 4.0 ("Jede Nutzung ist unter den Bedingungen ... CC-BY 4.0 zulässig"). Tested the Helgoland tile (2025, cm). Only Helgoland and some Baltic cliffs.

### Berlin – low
- DGM1 by ATOM `https://gdi.berlin.de/data/dgm1/atom` (2 km XYZ ZIPs per third parties), dl-de/zero-2.0. Our requests were answered "Request Rejected" by the WAF; stopped. Flat.

### Hamburg, Bremen – low
- Hamburg: DGM1 via the city's open data portal, dl-de/by-2.0 (metadata); Bremen: XYZ archives for Bremen (2017) and Bremerhaven (2015), CC BY 4.0. Not tested; flat.

### Saarland (LVGL) – low
- DGM1 from ALS 2016, dl-de/by-2.0 per metadata ("©LVGL 2022"), with HVD keywords; downloads generated from WMS GetMap calls (Mapbender ATOM) and other LVGL records still point to shop terms. Not tested (the GDI-DE catalogue did not answer). Few cliffs.

**Not tested**: Hamburg, Bremen, Saarland (low relevance), Berlin (WAF), Thuringia's data (server in maintenance), the WCSs of BW, NRW and BB, Bavaria's polygon Metalink service, the DSM downloads of HE and ST.

## Group g2-central: Austria, the Netherlands, Belgium, Luxembourg, Czechia, Slovenia, Hungary

Researched 2026-10-31. Scripts: `scripts/g2-central/` (`cog_probe.py`, `wcs_probe.py`, `multipart_tif.py`, `zipdir.py`, `las_header.py`); samples in `dl/g2-central/`.

### Austria (BEV): national 1 m DTM and DSM as COGs, yearly editions
- **Data**: ALS DTM and ALS DSM (DOM) "Höhenraster 1 m", whole country, built by BEV from the Länder's ALS flights (different years per area; re-flown "at intervals of up to 10 years"). Published as national editions with a reference date ("Stichtag") of 15 September: 2019, 2021, 2022, 2023, 2024, 2025. BEV says the Stichtag is not the survey date; the survey year per area is in a separate currency overview. Height accuracy ±0.5 m (more in high mountains).
- **Access**: 55 tiles of 50 × 50 km in EPSG:3035 per product and edition, static files at `https://data.bev.gv.at/download/ALS/{DTM|DSM}/<YYYYMMDD>/ALS_{DTM|DSM}_CRS3035RES50000mN<N>E<E>.tif`, listed by the INSPIRE ATOM feed (`.../geonetwork/srv/atom/describe/service?uuid=208cff7a-...`, 2 MB XML, one entry per tile and edition). Each file is a COG of 7–12 GB (50001 × 50001 px, float32, LZW with predictor 3, 512 px blocks in 2025, 256 px in older editions, overviews to 1:256); Apache with range requests. No key, no published limits.
- **Versions**: a full national edition per year at a dated path; a new edition replaces the whole tile (the newest edition is the right one, no composing needed). The edition date must be found (ATOM, or probing the newest folder).
- **Licence**: CC BY 4.0 ("Für dieses Produkt gilt die Standardlizenz CC-BY-4.0", BEV metadata); credit "Datenquelle: BEV".
- **Orthophoto**: basemap.at `bmaporthofoto30cm` (`https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg`, EPSG:3857, CC BY 4.0): z18 and z19 answer, z20 404.
- **Quick tests**: DSM 2023 tile E4550000 N2750000 (11.9 GB) and DTM 2025 tile E4400000 N2650000 (Tirol, 7.3 GB) open in 0.5 s through `/vsicurl/`; a 500 m window at the Martinswand near Innsbruck in 0.44 s, 100% valid, float (not cm-rounded), nodata -9999.
- **Fit**: window reads of big COGs on a fixed 50 km grid in EPSG:3035 (a `DegreeBlocks`-like subclass: URL from the tile name plus the edition date). Special: pixel centres on whole metres (origin 4399999.5: `grid_origin` 0.5); 50001 px, so neighbouring tiles overlap by one pixel; heights EVRF2000 Austria (EPSG:9274 per metadata, not named in the file), not the GHA heights of Austrian maps; the working grid could be EPSG:3035 (the files' CRS) or UTM 32/33 (resampling).
- **Länder**: Tirol publishes 0.5 m DGM/DOM (2nd statewide scan 2017–2023, free GeoTIFF per 1:2000 sheet and a WMS/WCS "Gelände Tirol"); Vorarlberg and others have similar 0.5 m data. Not given rows: the national 1 m product with DSM and yearly editions is as good for the 1 m default. Option for later: Tirol's 0.5 m for `--resolution 0.5`.
- **Open questions**: is the 3035 mosaic resampled from the Länder grids (compare with a Tirol sheet: half-pixel smoothing on cliffs)? Where is the currency overview (survey year per area) as data? Shift check against Copernicus.
- **Links**: https://data.bev.gv.at/geonetwork/srv/api/records/3726b0b8-3cfa-4cf4-a953-a4d32dc24484/formatters/xml, https://data.bev.gv.at/geonetwork/srv/atom/describe/service?uuid=208cff7a-c8aa-42fe-bf4f-2b8156e37528, https://basemap.at/, https://tirol.gv.at/sicherheit/geoinformationen-karten/freie-laserscandaten-und-orthofotos

### Netherlands (AHN via PDOK): 0.5 m, excellent access, almost no terrain
- **Data**: AHN4 DTM and DSM 0.5 m, whole country, flown 2020–2022. AHN5 flown 2023–2025; so far only parts are published (river sections on data.overheid.nl); the PDOK products are still AHN4.
- **Access**: WCS `https://service.pdok.nl/rws/ahn/wcs/v1_0` (coverages `dtm_05m`, `dsm_05m`, EPSG:28992, axes x y); ATOM `https://service.pdok.nl/rws/actueel-hoogtebestand-nederland/atom/dtm_05m.xml` with 1374 COG sheets (5 × 6.25 km, 40–330 MB, with bbox and length in the feed).
- **Licence**: CC0 (AHN); PDOK aerial photos CC BY 4.0.
- **Orthophoto**: `https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg`, z19–z21 answer.
- **Quick tests**: WCS 500 m at Sint-Pietersberg (ENCI quarry, Maastricht) 0.9 s, float32 DEFLATE, edges on whole metres, mm values, nodata 3.4e38 (the quarry lake); the COG sheet M_69AZ2 gives the same values (0.24 s to open, 512 px blocks, DEFLATE predictor 3).
- **Fit**: `IndexedTiles` with the ATOM feed as index + window reads, or `WcsTiles` as is. Effort S, but priority low: quarries in Limburg only.
- **Open questions**: when AHN5 replaces the PDOK sheets (versions).
- **Links**: https://service.pdok.nl/rws/ahn/atom/index.xml, https://www.ahn.nl/, https://data.overheid.nl/dataset/71500-nederrijn-lek-pannerdens-kanaal-0-5m-2025-dtm

### Belgium – Flanders (Digitaal Vlaanderen): DHMV II, flat
- **Data**: DHMV II (2013–2015) DTM 1 m and DSM 1 m; DHMV III flown in the winters of 2026 and 2026/27, products expected in 2028.
- **Access**: INSPIRE WCS `geo.api.vlaanderen.be/el-dtm/wcs` and `el-dsm/wcs`, only in EPSG:4258 (harmonised, resampled: 47% of values on whole cm), multipart answers; sheet ZIPs on download.vlaanderen.be (not tested). An Azure WAF answered 403 to a request with `subsettingCrs`/`outputCrs` (stopped there).
- **Licence**: Modellicentie Gratis Hergebruik (open, attribution). **Orthophoto**: WMS `geo.api.vlaanderen.be/omw/wms`, layer `OMWRGB25VL` (2025), EPSG:4326 works.
- **Fit / priority**: none – no highline terrain.

### Belgium – Wallonia (SPW): 0.5 m 2021–2022, but only huge ZIPs
- **Data**: "Relief de la Wallonie" MNT and MNS 2021–2022 at 0.5 m (also MNT/MNS 2013–2014 at 1 m), whole region.
- **Access**: no WCS or ImageServer (the RELIEF services are ArcGIS MapServers with "Map" capability only; WCSServer 400). Downloads only as ZIPs per province (EPSG:31370 or 3812) or the whole region (3812, 213 GB) through an ATOM feed. Namur 46 GB, Liège 45–49 GB, Luxembourg 56 GB. The server ignores Range requests (answered 200 with the whole file) and its HEAD timed out, so the central directory could not be read; about 3 MB/s observed.
- **Licence**: CC BY 4.0 ("L'utilisateur peut utiliser et modifier les données pour en dériver une œuvre. Il peut publier les données et l'œuvre dérivée à condition de citer les sources", Metawal record) – redistribution allowed, so own hosting is possible.
- **Orthophoto**: WMS `geoservices.wallonie.be/arcgis/services/IMAGERIE/ORTHO_LAST/MapServer/WMSServer`, layer `0`, EPSG:4326 at Freyr fine (yearly ortho 2023–2026 services exist); terms of the web services (LicServicesSPW.pdf) to read.
- **Fit**: own hosting (`GridTiles`), the Slovak pattern: download MNT and MNS once (~200 GB each at 0.5 m), cut into COG tiles. Effort L.
- **Highline**: Freyr and Dinant (Meuse), Marche-les-Dames, Ourthe/Amblève: the best of Belgium. Priority medium (access).
- **Open questions**: ZIP compression method (Deflate64?) and TIFF tiling (only known after a download); vertical datum (DNG/TAW expected); the 1 m 2013–2014 ZIPs might be smaller.
- **Links**: https://metawal.wallonie.be/geonetwork/srv/api/records/a004e570-99d6-4fe5-b83d-49b774409278, https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/a004e570-99d6-4fe5-b83d-49b774409278/atom_dataset.xml

### Belgium – Brussels
UrbIS DTM (2012 LiDAR) and a 2021 point cloud as ZIPs on datastore.brussels; a city without cliffs: nothing to do. https://geobru-geonetwork.irisnet.be/geonetwork/srv/api/records/e8a618a5-68dc-4a7b-9249-bde46f11c5c2

### Luxembourg (ACT): one 0.5 m COG for the whole country
- **Data**: BD-L-Lidar2024: MNT and MNS 0.5 m from the 2024 survey (> 30 points/m²), whole country; the 2019 survey before it.
- **Access**: one COG per model on data.public.lu (S3): `MNT_Lidar2024.tif` 40 GB, `MNS_Lidar2024.tif` 43 GB, 114617 × 163687 px, float64, LZW, 128 px blocks, 11 overviews. Point clouds as ZIPs per tile.
- **Licence**: CC0 (data.public.lu `cc-zero`).
- **Orthophoto**: `https://wmts1.geoportail.lu/opendata/wmts/ortho_latest/GLOBAL_WEBMERCATOR_4_V3/{z}/{x}/{y}.jpeg`, z19–z21 answer.
- **Quick tests**: both files open in 0.4 s; a 500 m window at Berdorf in 2.3 s (small float64 blocks), 100% valid, all values on whole cm.
- **Fit**: window reads of a single COG (a one-file `DegreeBlocks`-like layer); EPSG:2169; pixel edges on the 0.5 m lattice with origin 48880.5 (for a 1 m grid the x edges fall on half metres). Effort S.
- **Highline**: Mullerthal sandstone (Berdorf), medium.
- **Open questions**: vertical datum (NG95 expected; check doc-lidar2024 v1.1); whether a republication changes the dated URL folder.
- **Links**: https://data.public.lu/fr/datasets/lidar-2024-releve-3d-du-territoire-luxembourgeois/, https://download.data.public.lu/resources/lidar-2024-releve-3d-du-territoire-luxembourgeois/20250214-121729/doc-lidar2024-v-1-1.pdf

### Czechia (ČÚZK): 2 m effective, open, automatic; the sandstone towers
- **Data**: DMR 5G (ground points as TIN, ALS 2009–2013, updated per sheet from scans since 2016) and DMP 1G (surface points), whole country; DMR 4G a 5 m grid. Open data under CC BY 4.0 since July 2023. A new national ALS (2026+, ≥ 15 points/m², law 330/2025) is starting, which would bring finer products later.
- **Access**: (1) ArcGIS ImageServers `ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer` and `dmp1g/ImageServer` at 2 m pixel (dmr4g 5 m), exportImage in any bbox, float32 TIFF, max 15000 × 4100 px; (2) INSPIRE ATOM `atom.cuzk.gov.cz/DMR5G-SJTSK/DMR5G-SJTSK.xml` (16301 SM5 sheets of 2.5 × 2 km with georss polygons) → `openzu.cuzk.gov.cz/opendata/DMR5G/epsg-5514/<SHEET>.zip` with one LAZ (3–5 MB). The points are thinned: 0.18 points/m² (DMR 5G) and 0.22 (DMP 1G) at Adršpach, i.e. about 2 m spacing.
- **Versions**: one state per sheet, updated in place (DMR 5G file of 2026-07, DMP 1G file of 2023-06 at the same sheet).
- **Licence**: CC BY 4.0, ATOM rights "Žádné podmínky neplatí" (no conditions apply); credit "© ČÚZK".
- **Orthophoto**: `https://ags.cuzk.gov.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}` (EPSG:3857), z19/z20 answer.
- **Quick tests**: exportImage of 500 m at Adršpach (2 m, nearest) 0.25–0.35 s, 100% valid; LAZ headers of sheet MEZI69 (Adršpach) read from the ZIPs (LAS 1.4/1.2, cm scale).
- **Fit**: new driver for the ArcGIS ImageServer (WCS-like requests on a fixed 2 m grid in EPSG:5514; `LOCAL_CS` in the answer's TIFF, so set the CRS ourselves), or a new driver rasterising the LAZ sheets ourselves (laspy + lazrs, TIN to 1–2 m; the same as the US DSM idea). Heights Bpv.
- **Highline**: very high (Adršpach-Teplice, Prachov, Hruboskalsko, Bohemian Switzerland, Moravian Karst) – but towers a few metres wide are poorly resolved at 2 m; worth it now, better after the 2026+ survey.
- **Open questions**: the ImageServer's native grid and interpolation (TIN?) versus our own TIN of the points; when the new ALS products come and in which form; the licence of the ortho tile service.
- **Links**: https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer, https://atom.cuzk.gov.cz/DMR5G-SJTSK/DMR5G-SJTSK.xml, https://geoportal.cuzk.gov.cz/Dokumenty/TECHNICKA_ZPRAVA_DMR_5G.pdf, https://cuzk.gov.cz/Aktuality-resort/Aktuality-WEB/Analyza-vyskopisu.aspx

### Slovenia (GURS, ARSO): old 1 m files automatic, the new survey through a viewer only
- **Data**: LSS 2014–2015 (two blocks 2011): DMR 1 m (ARSO, "eVode"), whole country, no DSM raster. CLSS 2023–2025 (a third of the country per year, complete in 2026): per 1 km sheet the classified point cloud (GKOT), DMR and DMP as LAZ, nDMP and hillshade as TIFF, orthophoto; free, no registration.
- **Access**: LSS files at `http://gis.arso.gov.si/lidar/dmr1/b_<block>/D96TM/TM1_<E km>_<N km>.asc` (ASCII `x;y;z`, 1 m points on whole metres, about 25 MB per km², range requests); the block number must come from ARSO's index (a wrong block answers 404, folder listings 403). CLSS: only the clss.si viewer (Flycom LIFT, up to 10 sheets at once); no documented API (not reverse-engineered).
- **Licence**: free use with attribution ("Navedba vira" on e-prostor); CC BY 4.0 not stated for LSS.
- **Orthophoto**: GURS WMS `storitve.eprostor.gov.si/ows-pub-wms/SI.GURS.ZPDZ/ows`, layer `DOF5`; EPSG:4326 in WMS 1.3.0 expects lon,lat (lat,lon gives a white image) – use EPSG:3857 or 3794.
- **Fit**: a new driver for per-km XYZ ASCII with a block index (LSS, DTM only, `grid_origin` 0.5); CLSS would need GURS's consent to automate or a hosted copy rasterised from LAZ.
- **Highline**: very high (Julian Alps, Osp/Mišja peč, Kamnik-Savinja Alps). Priority medium (old data, no DSM, licence wording).
- **Open questions**: an official download API for CLSS (ask GURS: gp.gu@gov.si); the CLSS raster resolution; the licence text; vertical datum per survey (SVS2000 vs SVS2010).
- **Links**: https://www.gov.si/novice/2026-06-03-lidarski-podatki-za-celotno-slovenijo-dostopni-v-pregledovalniku-3d-podatkov/, https://clss.si/, https://gis.arso.gov.si/evode/, https://geodetski-vestnik.com/arhiv/68/3/377_Dougan.pdf

### Hungary: nothing open
A national airborne LiDAR survey is in progress (5 points/m², 73% in February 2025); the state data (Lechner) and the commercial Envimap shop sell DTM/DSM 1 m in EOV. No open elevation data found; keep FABDEM. Watch whether the HVD rules bring an open release. https://envimap.hu/, https://hte.hu/documents/10180/4968019/6_Tomor_Tamas__HTE_Dron_Szakmai_Nap.pdf

## Group g3-fr-pt: France, Monaco, Andorra, Portugal (researched 2026-10-31)

Rows: `fr`, `mc`, `ad`, `pt`, `pt-20` (Azores), `pt-30` (Madeira). Scripts in `scripts/g3-fr-pt/`, samples in `dl/g3-fr-pt/`.

### France (IGN): LiDAR HD MNT/MNS 0.5 m through the Géoplateforme WMS-R, indexed by a WFS
- **Data**: the LiDAR HD programme (2021–2026, ≥10 pts/m², 5 above 3200 m) gives MNT (terrain), MNS (surface) and MNH (canopy height) at 0.5 m in 1 km tiles, GeoTIFF, Lambert-93 (EPSG:2154) for the mainland **and Corsica**; heights NGF-IGN69 on the mainland, **NGF-IGN78 in Corsica** (the tile's `systeme_altimetrique`). The point-cloud index holds 524 687 tiles (mainland + Corsica + DROM). Coverage, measured: 63 of 67 points of a 1° lattice over land valid (MNT and MNS). Of the 4 misses, 2 are across the border (Saarland, Hainaut, inside RGE ALTI's buffer) and 2 are in France (48.5 N 1.5 E near Chartres, 49.5 N 3.5 E in the Aisne): ZICAD or blocks not edited yet. All 18 climbing places checked are valid. Acquisitions there were 2021 (south, Alps, Pyrenees, Corsica), 2024 (Fontainebleau) and 2025 (Étretat), all edited 2024-12 to 2025-10. ZICAD (restricted sites) are nodata. The programme's own status map: https://macarte.ign.fr/carte/mThSup/diffusionMNxLiDARHD. data.gouv.fr says the products cover the mainland and the DROM except French Guiana by 2026. A 5 m version is "announced".
- **RGE ALTI 1 m** (the older national DTM, mixed sources: LiDAR, radar, correlation; free under Licence Ouverte since 2021) is in the same WMS-R (`ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES`). At Verdon, 70% of horizontal neighbours are equal, so it was resampled there from a coarser source. It is useful only as a gap filler for ZICAD holes, and better than FABDEM for that.
- **Access**: there is no public WCS (`/wcs` answers 404), no STAC and no public tile-index WFS (`IGNF_LIDAR-HD_TA:*-dalle` lives on IGN's private route with the key `interface_catalogue`). Instead, the public WFS layer **`IGNF_LIDAR-HD_METADONNEE:metadata`** (https://data.geopf.fr/wfs/ows) gives for every 1 km tile:
  - the mission, acquisition dates and edition date;
  - the CRS and vertical datum;
  - `url_mnt`, `url_mns` and `url_mnh`: IGN's own "download" links, which are WMS-R GetMap requests (`https://data.geopf.fr/wms-r?...LAYERS=IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93&FORMAT=image/geotiff&STYLES=&CRS=EPSG:2154&BBOX=971999.75,6303000.25,972999.75,6304000.25&WIDTH=2000&HEIGHT=2000&FILENAME=LHD_FXX_0972_6304_MNT_O_0M50_LAMB93_IGN69.tif`);
  - `url_npl`, the COPC LAZ on `data.geopf.fr/telechargement`.

  The tile name gives the north-west corner in km. Limits, from the Géoplateforme CGU (Annexe 3):
  - WMS-Raster: 40 requests/s per IP (429, then a 5 s block);
  - WFS: 30 requests/s;
  - Téléchargement: 5 requests per 5 s, with a 5 min ban;
  - WMTS: no limit.
- **Versions**: one edition per tile today (`date_edition`). The 2025 re-editions show that tiles can be re-issued, so the edition date would be the cache key. No second cycle is announced.
- **Licence**: Licence Ouverte / Open Licence 2.0 (data.gouv.fr `lov2`). It allows reuse, including commercial use and redistribution, if the source and the date of the last update are mentioned. The CGU say: "A défaut, la Licence Ouverte / Open Licence – Etalab" applies. https://www.etalab.gouv.fr/licence-ouverte-open-licence, https://cartes.gouv.fr/cgu
- **Orthophoto**: BD ORTHO through the WMTS `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg`. PM is the EPSG:3857 XYZ grid, zoom 0–19 (z20 404, also for `HR.ORTHOIMAGERY.ORTHOPHOTOS`). JPEG ~12 kB, no watermark, WMTS without a rate limit, Licence Ouverte.
- **Quick tests** (2026-10-31):
  - WMS-R GetMap of 500 × 500 m at 0.5 m (Verdon, Bavella): `image/geotiff` float32, uncompressed in 2-row strips, 4 MB in about 1 s, nodata -9999, 100% valid. Only about 1% of the values fall on whole cm (true float precision).
  - A full tile (2000 × 2000 px, 16 MB) took 8.9 s.
  - A request shifted by one pixel gives identical values. One shifted by half a pixel gives the mean of the neighbours (bilinear). A 1 m request gives the exact 2 × 2 mean. So aligned requests return the stored pixels.
  - RGE ALTI 1 m: 0.5 s per 500 m, nodata -99999, pixel edges on whole metres.
  - The WFS answers in 0.13 s.
- **Fit**: a new subclass in the `WcsTiles` pattern. Requests are WMS-R GetMap `image/geotiff` on the fixed 1 km Lambert-93 grid, with exactly the tile bbox (edges on .25/.75), and `fetch_res` 0.5. The WFS metadata is the index (edition date per tile, for `cache update`). An alternative is `IndexedTiles` over the WFS, storing `url_mnt`/`url_mns` as files: the same thing.
- **What is special**:
  - **Half-pixel alignment**: pixel centres on whole and half metres (grid_origin 0.5 for 0.5 m pixels, as Poland's sheets).
  - Two vertical datums (IGN69 / IGN78), both orthometric.
  - Uncompressed 16 MB per km² per model (MNT + MNS about 32 MB/km²).
  - ZICAD nodata.
  - Both `https://data.geopf.fr/wms-r` and `/wms-r/wms` answer.
- **Open questions**:
  - Is there a public tile index of the MNT itself (`IGNF_LIDAR-HD_TA:mnt-dalle` on the public WFS seems withdrawn), or is the metadata layer the intended one?
  - Is the 5 m version coming?
  - Can the WMS-R deliver a compressed GeoTIFF (an option of `FORMAT` or `image/x-bil;bits=32`)?
  - When will the 2 French lattice holes be published?
- **Overseas in the Americas** (rows by another agent):
  - Guadeloupe: LiDAR HD exists (mission 24LHDGDP, RGAF09 / UTM 20N, GUAD88, edition 2025-02), but its `url_mnt` points to IGN's private WMS-R route.
  - Martinique, Saint-Martin, Saint-Barthélemy and Saint-Pierre-et-Miquelon: no LiDAR HD tiles in the WFS (2026-10-31). Only RGE ALTI as WMS-R layers (`RGEALTI-MNT_PYR-ZIP_MTQ/GLP_WGS84UTM20`, `SPM_RGSPM06U21`; source layers also for SBA and SMA).
  - Réunion has LiDAR HD (RGR92 / UTM 40S, REUN89).
- **Links**: https://cartes.gouv.fr/catalogue/dataset/IGNF_MNT-LIDAR-HD, https://www.data.gouv.fr/datasets/mnt-lidar-hd, https://www.data.gouv.fr/datasets/mns-lidar-hd, https://data.geopf.fr/wms-r/wms?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0, https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities, https://geoservices.ign.fr/rgealti, https://lidar.pages-forge.inrae.fr/lidarHD/reference/load_classified_ta.html

### Monaco: covered by IGN's LiDAR HD
- The WFS has Monaco's tiles (mission 21LHD8SP, acquired 2021-05, edited 2025-06, IGN69). A 1 km box on Monaco is 100% valid in the MNT, the MNS and RGE ALTI. Same access, licence and orthophoto as France. No data of Monaco's own was looked for further.
- **Fit**: the French source as is. Highline terrain is minor (the Rocher), so the priority is low. Risk: IGN might withdraw foreign territory.

### Andorra: nothing usable
- IDE Andorra (cartografia.ad) lists many WMS services, but none for elevation. The download portal https://www.ideandorra.ad/geodades needs a registration form, and no elevation product was confirmed. The catalogue did not answer. Spain's PNOA and IGN's LiDAR HD stop at the border.
- **Legal notice**: "Els usuaris dels webs només podran fer un ús privat i personal dels continguts". Reproduction needs "consentiment previ i per escrit del Govern", and commercial use is prohibited (https://www.cartografia.ad/avis-legal).
- **Orthophoto**: 2025 at 25 cm, WMS `https://www.ideandorra.ad/Serveis/wmsorto2025/wms`, layer `Andorra_orto_25cmGSD_2025`, EPSG:4326 / 3857 / 25831. The test gave a 512 px JPEG in 2.8 s, no watermark. Its licence for a public site is unclear.
- **To do outside the code**: ask the Àrea de Cartografia whether a LiDAR DTM exists and on what terms.

### Portugal, mainland (DGT): LiDAR 2024, 50 cm MDT/MDS on the CDD, behind a free login
- **Data**:
  - The national LiDAR survey of 2024 (to Q1 2025, PRR funding; 10 pts/m², 10 cm vertical): MDT and MDS at 50 cm and 2 m, and LAZ, in 1 km tiles in EPSG:3763 (PT-TM06).
  - The collections still say "Zona Noroeste ainda indisponível", but a tile at Ponte de Lima (41.70 N) exists, version 02 dated 2025-11 with overviews. So the north-west was apparently delivered late, as re-issued files.
  - **Vertical datum unconfirmed**: neither the item nor the SNIG metadata names it. DGT's standard is Cascais (EPSG:5780).
- **Access**:
  - The CDD (https://cdd.dgterritorio.gov.pt), with the API `https://cdd.dgterritorio.gov.pt/dgt-be/v1`: STAC-like, with answers wrapped as `{status, message, data}`.
  - Searching: `POST /search` with CQL2-JSON `s_intersects` (third-party tools note that `bbox` on `/items` is ignored). There are no limits or published terms of the API, and the "second version" of the CDD with an official API was promised for Q4 2025.
  - Downloading: the asset `/dgt-be/v1/download/<token>` needs the session of a **free CDD account** (Keycloak form login). Without it, the answer is `302 → /auth/login`.
  - Third-party downloaders log in with stored credentials (GMT.jl `dgt_lidar`, the QGIS plugin `dgtcd_downer`, lidar2map).
- **Versions**: item ids look like `MDT-50cm-<sheet>-MM-YYYY`, with a `version` of 01 or 02 (re-issues). Keep the newest per tile.
- **Files** (from the items; not downloaded): float32 in 2000 × 1 strips, uncompressed (16.0 MB per 1 km tile at 50 cm, 1 MB at 2 m), nodata -999, tile origins on whole km (`-110000, 0.5, …, -96000`), so pixel edges on whole metres. They are not COGs, so a whole tile is downloaded.
- **Licence**: CC BY 4.0 (the collections' `license`). The DGT webinar of 2025-07 says: "Dados abertos de acesso público sem restrições, com licença de uso CC-BY-4.0".
- **Orthophoto**:
  - The CDD has ortho collections up to ORTOS-2025 (25 cm RGBN), as files.
  - The MapProxy WMS/WMTS `https://cartografia.dgterritorio.gov.pt/ortos2021/service` (layer `Ortos2021-RGB`, EPSG:3857 / 3763) answered 200 with **blank PNGs** (1 114 B) at three scales in both CRSs, and in WMTS (1 611 B).
  - `ortos2023`–`2025` gave 404.
  - A working orthophoto service is still to be found.
- **Quick tests** (2026-10-31): the collections (81 kB) and three searches (Sintra, Arrábida, Ponte de Lima) each gave 1 item per collection in 0.3–0.4 s. The download without a session gave 302. The orthophoto was blank (above).
- **Fit**: a new `StacTiles`-like subclass for the CDD:
  - POST search with wrapped answers, cached per 0.25° like the other indexes;
  - versions per tile;
  - a login (session cookie from the operator's account, secrets like `ServiceKeys`).

  Effort M.
- **Open questions**:
  - The vertical datum.
  - The value precision.
  - The CDD terms for automated use with an account.
  - Will the promised API get tokens instead of a form login?
  - Is the north-west complete?
  - Where is a working orthophoto WMS/WMTS?

### Portugal, Azores (pt-20): 1 m MDE/MDS of 2024 on the same CDD
- Collections `ACORES-MDE-1`/`ACORES-MDS-1` (also at 5 and 10 m, and `ACORES-LAZ`), CC BY 4.0, acquired 2024-09 to 11.
- The search found tiles on São Miguel (Sete Cidades), São Jorge and Flores: 5–6.4 MB each, named `2024_SMG_PDL_27-1-4-5_01_MDE`.
- CRS: PTRA08 / UTM 25N (EPSG:5014) on Flores. The central and eastern groups probably use UTM 26N (EPSG:5015); their `projjson` is empty.
- To confirm: that "MDE" is the bare-earth model, and the vertical datums of the islands.
- **Fit**: the same CDD driver, with a CRS per island group. Priority medium (sea cliffs, calderas).

### Portugal, Madeira (pt-30): 5 m only, terms unknown
- The regional government (DROTe / IRIG-Madeira) lists an MDT of the RAM 2018/2019 at 5 m, an older 10 m MDT (2004) and Porto Santo at 10 m. dados.gov.pt says "License Not Specified". The SNIG record API answered 404, and the regional catalogue host did not resolve.
- Madeira is not part of DGT's 2024 LiDAR. Despite very high sea cliffs (Cabo Girão), the priority is low until a LiDAR survey appears. Ask DROTe (drote@madeira.gov.pt).

## Italy, San Marino, Vatican City (g4-it, researched 2026-10-31)

How: docs/data-sources.md. Scripts in `scripts/g4-it/` (`wcs.py`, `csw.py`, `imgsrv.py`, `zipdir.py`, `wmscover.py`, `make_json.py` writes [sources.json](sources.json)), samples in `dl/g4-it/`.

**Overview.** Italy has no national 1 m terrain model. The ministry's PST LiDAR (2008-2013) covers coasts, rivers and risk areas at 1-2 m. Its only download path is an interactive web app, which was down for maintenance during the research. The regions and autonomous provinces each publish on their own platform; no two share one, apart from the national WMS. The useful finds:
- **Trento**: 0.5 m DTM and DSM of the whole province as static 500 m ASCII tiles with an index and open directory listings. CC BY 4.0, ready for a `SheetTiles`-like layer. Best candidate.
- **Bolzano**: a WCS, CC0, but only 2.5 m (2004-2006) in the mountains; 0.5 m in the settlements. Ready for `WcsTiles`.
- **Sicily**: a 2 m DTM of the whole island (2012-2013) through an ArcGIS ImageServer. The licence is not stated.
- **Toscana**: 1-2 m LiDAR sheets (mostly the PST data) found through a WFS index; each file's URL must be asked with a GetFeatureInfo. CC BY 4.0 / CC BY-SA 3.0 IT.
- Elsewhere: 5 m regional DTMs (Liguria, Veneto, Lombardia, Piemonte, Emilia-Romagna) or nothing beyond the PST.

**CRS mix**: EPSG:25832 (Bolzano, Trento), 25833 (Sicily 2013), 32632 (Sardinia 1 m, TINITALY), 3003 Monte Mario zone 1 (Liguria, Toscana's sheets, Veneto's index, Sardinia 10 m), 3004 zone 2 (Sicily 2008), RDN2008 TM33 (FVG), RDN2008 / UTM 32N EPSG:7791 (Toscana 2019-2021). Vertical datums: Genova 1942 orthometric heights, through the ITALGEO geoid, where named (Sicily 2008: vcs 5214). Bolzano uses its own provincial geoid. FVG publishes both ellipsoidal and orthometric files. Most files name no vertical datum at all.

---

### Italy, national: MASE Geoportale Nazionale, PST LiDAR
- **Data**: the Piano Straordinario di Telerilevamento Ambientale (2008-2013). LiDAR DTM, DSM First and DSM Last at 1x1 m and 2x2 m in regional sets: Abruzzo, Area Dolomitica, Basilicata, Bolzano, Calabria, Campania, Emilia-Romagna, FVG, Lazio, Liguria, Lombardia, Marche, Molise, Piemonte, Puglia, Sardegna, Sicilia, Toscana, Trento, Umbria, Valle d'Aosta, Veneto. Coverage: coasts, main rivers (Toscana's index: "corsi d'acqua ... buffer pari ad 800 m"), risk areas; no newer national programme announced. Also multibeam/LiDAR land-sea DTMs of the marine protected areas (4 m).
- **Access**: "Download Banca Dati PST", a web app at https://sim.mase.gov.it/portalediaccesso/mappe/#/viewer/new. Areas are selected on a map, up to 6 GB per request, delivered as GeoTIFF. A tile index ("quadri di unione") is published as WFS `http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/wfs/QU_Lidar.map` (types `EL.QUADRO.UNIONE.LIDAR.0101` / `.0202`). The WMS per region is `.../servizi-LiDAR/LIDAR_<REGION>.map`. The WCS catalogue holds only the DTM 20/40/75 m (`http://wms.pcn.minambiente.it/wcs/dtm_20m`). No LiDAR WCS exists, and the servers are plain HTTP.
- **Licence**: the distribution page says "I dati sono distribuiti con licenza" CC BY 4.0, as high-value data, free of charge (https://gn.mase.gov.it/portale/distribuzione-dati-pst). The same MATTM sheets redistributed by Toscana carry CC BY-SA 3.0 IT: an older statement to reconcile.
- **Orthophoto**: national AGEA colour 2012 (`ortofoto_colore_12.map`, layers `OI.ORTOIMMAGINI.2012.32/.33`): GetMap failed (missing tile index on the server).
- **Quick tests**:
  - The portal answered 503: maintenance was announced from 29 October to 6 November.
  - The WFS index failed with a PostGIS connection error.
  - The WMS answers, so coverage was probed with transparent PNGs (`wmscover.py`):
    - **Data**: Finale Ligure (100%), the Aosta valley floor, the edge of the Supramonte (35%), San Vito lo Capo at 2 m (83%), and Civetta in the Area Dolomitica (a white image: probably values above the colour ramp).
    - **No data**: Cinque Torri, Sassolungo, Gran Sasso (1 m and 2 m), Cala Gonone, Amalfi, the Gargano, Arco and Bolzano. The layers may be scale-limited, so a zero is no proof.
- **Fit**: no automatic access today. Options:
  - (a) Once the portal is back, look at the API behind the web app. Stable per-tile URLs and the WFS index would make an `IndexedTiles` driver.
  - (b) Download chosen areas by hand and host them (`GridTiles`). CC BY 4.0 allows redistribution.
- **Open questions**:
  - The API behind the web app.
  - The CRS and vertical datum of the GeoTIFFs.
  - Real coverage at the climbing areas (the WFS index, once it works).
  - CC BY 4.0 against CC BY-SA 3.0 IT.
  - Whether the 1 m and 2 m sets overlap.

### Italy, national fallback: TINITALY 10 m (INGV)
- **Data**: TINITALY/1.1 (2023), 10 m DEM of all Italy, UTM 32N WGS84 for the whole country. **Licence**: CC BY 4.0, quote: "TINITALY is published with a CC BY 4.0 license and can be used freely, even partly". Cite doi:10.13127/tinitaly/1.1.
- **Access**: 193 ZIPs at `https://tinitaly.pi.ingv.it/data_1.1/<tile>/<tile>.zip`. The site's WMS, WMTS and WCS serve only derived images (hillshade, slope, openness), not heights.
- **Quick test**: `w51560_s10.zip` is 52 MB. Its central directory, read by range requests, holds one Deflate GeoTIFF (100 MB) and the notes PDF. The TIFF cannot be read in parts.
- **Fit**: whole-zip downloads (50 MB) or our own COG copy (`GridTiles`). At 10 m it is better than FABDEM only in licence and in the detail of flat areas: a low-priority fallback.

### Bolzano / South Tyrol (it-bz)
- **Data**:
  - DTM and DSM 2.5 m of the whole province (LiDAR 2004-2006).
  - DTM and DSM 0.5 m of the settlement areas only.
  - Glacier DEMs 0.5 m (2016-2017, 2023).
  - Etsch/Adige 0.2 m (2024).

  Heights from the province's own geoid. A provincial LiDAR project (unibz "LiDAR_ProvBZ", about 2023) has published nothing yet.
- **Access**: WCS 2.0.1 `https://geoservices9.civis.bz.it/geoserver/ows` (coverages `p_bz-Elevation__DigitalTerrainModel-2.5m`, `-0.5m`, `p_bz-Elevation__DigitalElevationModel-2.5m`, ...). EPSG:25832, axes E/N, nodata -9999, Fees and AccessConstraints NONE.
- **Licence**: CC0 1.0 (metadata use limitation `https://creativecommons.org/publicdomain/zero/1.0/deed.it`).
- **Orthophoto**: MapProxy WMTS `https://geoservices.buergernetz.bz.it/mapproxy/ows`, layer `p_bz-Orthoimagery:Aerial-2023-RGB` (20 cm, CC BY 4.0), matrix set `EPSG_3857` up to zoom 21. A zoom 18 tile at Sassolungo: a sharp JPEG, no watermark.
- **Quick tests** (500 x 500 m at Sassolungo):
  - 2.5 m DTM: 200x200 float32 in 0.5 s, 100% valid, 2413-3170 m.
  - 0.5 m DTM and DSM: 0% valid there (settlements only).
  - 0.5 m DTM at Bolzano town: 100% valid.

  Values are floats (6-8% on whole cm).
- **Fit**: `WcsTiles` as is. Coverage edges are at x.75 / y.25: pixel centres on whole or half metres, so `grid_origin` 0.5. A 0.5 m layer with the 2.5 m one as the gap filler would serve the valleys.
- **Open**: when the new provincial LiDAR is published; the geoid's name; a georeferencing check against Copernicus.

### Trento (it-tn): best candidate
- **Data**: "LiDAR PAT 2014 integrated with 2018 flights" (surveys 2013-2018), the whole province.
  - Products: DTM, DSM First, DSM Last and DBM, all at 0.5 m; LAZ point clouds; 5 m and 10 m DTM mosaics.
  - Older sets: PAT 2006/2009 (DSM 1 m), Campolongo 2011, small 2007 areas.
- **Access**: static files on nginx with open directory listings, published since 27 October 2020.
  - Files: `https://siatservices.provincia.tn.it/stemdata/2014_lidar_dtm_asc/<tile>_DTM.asc`, likewise `2014_lidar_dsmfirst_asc/<tile>_DSMFirst.asc`, `2014_lidar_dsmlast_asc`, `2014_lidar_dbm_asc`, `_xyz` (zipped) and `2014_lidar_laz`.
  - Tile index: a shapefile ZIP, `https://siatservices.provincia.tn.it/idt/vector/p_TN_9f2cc32d-1030-430d-be85-7f95c9cc24ea.zip` (25 201 tiles of 500 m, EPSG:25832, attribute `n_tavola` = `5h<E/100><N/100>`).
  - Catalogue: CSW `https://siat.provincia.tn.it/geonetwork/srv/eng/csw` (74 LiDAR records with these URLs).
- **Licence**: CC BY 4.0, from dati.trentino.it's record of the LiDAR download service. The geocatalogue records say "no limitations to public access" and "Copyright"/"Nessuna condizione applicabile".
- **Quick tests**:
  - Directory listing of the DTM: 3.1 MB, 25 266 entries.
  - File dates: 2015 (3920), 2016 (1508), 2018 (8318), 2019 (10 597), 2020 (859), 2024-2026 (63). Tiles were replaced in place, with no version in the name.
  - Tile `5h646050865` (Arco): 6.2 MB in 0.7 s; 1000x1000, cell 0.50, `xllcenter 646000.25`, so pixel edges on whole metres; nodata -9999; 100% valid; values on whole cm; no CRS in the file.
- **Fit**: a `SheetTiles`-like layer.
  - Index: the shapefile once, with the HTTP `Last-Modified` of each file as its version.
  - Files are ESRI ASCII, read by rasterio, with EPSG:25832 assigned.
  - Volume: about 6-8 MB per 500 m tile and product, about 30 MB per km² each for the DTM and the DSM. Store them as compressed GeoTIFF in the cache.
- **Orthophoto**: PAT 2015 as ECW downloads and a WMS (not tested).
- **Open**: the vertical datum (orthometric; Genova 1942 through ITALGEO?); what the 2024-2026 re-issued tiles changed; the orthophoto WMS.

### Veneto (it-34)
- **Data**: a 5 m regional DTM mosaicked from more than 40 LiDAR campaigns, 4729 index tiles. The 1 m originals are not published, except single areas (Cortina 2017, 2021).
- **Access**: the IDT2 geoportal by hand. The index is the WFS `rv:c0101071_lidar5m` (EPSG:3003, attributes `nome`, `fuso`). WCS is disabled on idt2-geoserver.
- **Licence**: IODL 2.0, attribution "Regione del Veneto – L.R. n. 28/76 - Formazione della Carta Tecnica Regionale".
- **Tests**: the PST WMS for Veneto shows no data at Civetta or Cinque Torri.
- **Fit**: none for now. The Belluno Dolomites (very high relevance) have only 5 m.

### Friuli-Venezia Giulia (it-36)
- **Data**: LiDAR RAFVG 2017-2020: DTM, DSM first/last and DBM at 0.5 m, the whole region, in RDN2008 / TM33, with ellipsoidal and orthometric versions.
- **Access**: Eagle.fvg "download basi cartografiche" (interactive). IRDAT says "Distribution not available".
- **Licence**: not stated (empty fields).
- **Tests**: metadata only. **Open**: licence; the download path (worth a mail to the Region); the geoid of the orthometric files.

### Valle d'Aosta (it-23)
- **Data**: the Region's DTM (LiDAR 2005-2008, about 2 m; details unclear), granted under CC BY 4.0 by DGR 899/2014. Required credit: "Dati estratti dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta".
- **Access**: the SCT geoportal (geonavigator). The partout.it catalogue hosts did not answer. The PST WMS shows 1 m data on the valley floor at Aosta.
- **Open**: resolution, coverage, any newer survey, and the download mechanism.

### Piemonte, Lombardia, Emilia-Romagna (it-21, it-25, it-45)
- **Piemonte**: DTM/DSM 5 m from the ICE 2009-2011 LiDAR (0.4 pt/m²), EPSG:32632, on Geoportale Piemonte; licence per dataset. Not tested.
- **Lombardia**: DTM 5x5 (2015): 1 m LiDAR along rivers, resampled, and the 20 m DTM elsewhere. The licence is IODL 2.0 or CC BY-NC-SA 3.0 IT per layer group (a 2014 statement). Not tested.
- **Emilia-Romagna**: WCS `https://servizigis.regione.emilia-romagna.it/wcs/dtm5x5` (coverage `DTM5X5_RDN32_RMD`, AccessConstraints "Nessuno"), 5 m. Coastal LiDAR 2019 and the 2023 flood DTM (CC BY 4.0 WCS) cover the plain. Only GetCapabilities was tested.
- All three are 5 m. Their high-mountain cliffs (Val di Mello, Orco) have no better open data unless the PST covers them.

### Liguria (it-42)
- **Data**: the regional DTM ed. 2023, 5 m, whole metres. 1 m only from the national PST, which covers Finale Ligure fully (WMS probe).
- **Access**: WCS per dataset workspace: `https://geoservizi.regione.liguria.it/geoserver/M2056/wcs`, coverage `M2056__L6952`, EPSG:3003.
- **Quick test**: 500 m at Finale: 100x100 int16 in 0.8 s, 84-267 m, 100% whole metres. Corners at x.19189 / y.40548, off whole metres.
- **Licence**: not stated for the 5 m DTM; PST: CC BY 4.0.
- **Fit**: `WcsTiles` works but is poor. Finale (very high relevance) depends on the national portal.

### Toscana (it-52)
- **Data**: LiDAR DTM and DSM per 1:2000 sheet, 1x1 or 2x2 m: 11 281 sheets, mostly the MATTM/PST surveys of 2008-2013 plus the Region's own (Elba 2012...). A 2019-2021 survey by Italian Remote Sensing (1851 sheets) is "solo uso enti pubblici": not open. The DSM 2021 at 1 m comes from image correlation.
- **Access**:
  - Index: WFS `https://www502.regione.toscana.it/wmsraster/com.rt.wms.RTmap/wms?map=wmscartoteca`, typename `rt_cartoteca.lidar2k` (attributes foglio, lotto, risoluz, anno, srid, dtmname, dsmname, rilievo).
  - Download URLs: they carry a hash (`.../geoscopio/download/altimetria/lidar/dtm/<dtmname>_<32 hex>.zip`), not the md5 of the name. Only the WMS GetFeatureInfo (text/html) on the same layer gives them.
- **Licence** (GetFeatureInfo text): "Per i dati di proprieta' di Regione Toscana la licenza e': ... Creative Commons Attribuzione 4.0" and "Per i dati di proprieta' del MATTM la licenza e': ... Creative Commons Attribuzione Condividi allo stesso modo 3.0 Italia".
- **Quick test**: a DTM zip at Elba (2 m, 2008): 1.19 MB in 0.5 s. It holds an ASCII grid (820x620, cell 2, `xllcenter 1615181`, so edges on whole even metres) and `licenza_dati_Lidar.pdf`.
- **Fit**: a new driver on the SheetTiles pattern: WFS index, then one GetFeatureInfo per sheet for the URL, then the zipped ASCII in EPSG:3003. Overlapping lots are versions.
- **Open**: share-alike for lines derived from MATTM sheets; coverage of the Apuan Alps.

### Marche, Umbria, Lazio, Abruzzo, Molise, Campania, Puglia, Basilicata, Calabria
No regional LiDAR download was found, so only the national PST covers parts of these regions. Lazio publishes a 5 m DTM as DXF (CTR 2002-2003), Puglia an 8 m DTM, Basilicata a 5 m DTM (RSDI); none was checked.
- **Abruzzo**: the PST WMS shows no data at Corno Grande, so Gran Sasso has nothing better than FABDEM or TINITALY.
- **Campania**: no data at Amalfi.
- **Puglia**: no data on the Gargano at the point tested.

Not tested: Marche, Umbria, Lazio, Molise, Calabria, Basilicata, and the regional services of Piemonte and Lombardia.

### Sicilia (it-82)
- **Data**: MDT 2 m of the whole island in two editions, 2007-2008 (`mdt_2008`, EPSG:3004 with Genova 1942 heights, vcs 5214) and 2012-2013 (`mdt_2013`, EPSG:25833, vcs 9389 as published: to check). PST 1 m and 2 m cover the coast. San Vito lo Capo has 2 m PST data.
- **Access**: ArcGIS ImageServer `https://map.sitr.regione.sicilia.it/gis/rest/services/modelli_digitali/mdt_2013/ImageServer`, with `exportImage` up to 15000x4100 px and bilinear by default (ask for `RSP_NearestNeighbor`).
- **Quick test**: 500 m at San Vito lo Capo: 250x250 float32 in 0.8 s, 100% valid, mm values. The origin is exactly on the requested whole metres (the extent is on even metres).
- **Orthophoto**: ImageServer `ortofoto/ortofoto_2022_20cm_sicilia`, `exportImage` in EPSG:3857 tested: clear, no watermark.
- **Licence**: not stated on the services. **Fit**: a new driver: ImageServer `exportImage` on a fixed grid in EPSG:25833 (the pattern considered for the USA 3DEP ImageServer). **Open**: licence (ask SITR); whether `mdt_2013` is LiDAR or photogrammetric; the vertical datum.

### Sardegna (it-88)
- **Data**:
  - DTM and DSM 1 m of urban centres, by WCS.
  - "Mosaico DTM 1m" (coastal strip LiDAR 2008-2010, towns): WMS, or the Sardegna Mappe download by hand.
  - DTM 10 m (EPSG:3003).
- **Access**: WCS `https://webgis.regione.sardegna.it/geoserver/ows` (`dbu__DTM_CENTRI_SAR`, `dbu__DSM_CENTRI_SAR`, `dbu__DTM_RAS`).
- **Quick test**: Cala Gonone gave an all-zero grid (no data, nodata unset); Cagliari 100% valid. The origin is x.0503, off whole metres. The PST WMS has no data at Cala Gonone and covers part of the Supramonte box.
- **Licence**: unclear ("Other restrictions", keyword opendata).
- **Fit**: little use. The cliffs of interest lie outside the 1 m coverage.

### San Marino, Vatican City
- **San Marino**: no national elevation data found; FABDEM, or Italian regional data at the border. Monte Titano is small.
- **Vatican City**: nothing to research (0.44 km², no cliffs).

### Not tested / blocked
- MASE portal (503) and its WFS index (database error): maintenance until 6 November (2026). Repeat the coverage and API checks afterwards.
- The INSPIRE geoportal's certificate had expired (2026-10-31), so its records could not be read directly; the regional catalogues were used instead.
- No vertical datum is confirmed from a file anywhere. No shift against Copernicus was checked (the data checks of a new source are still to do).

## Nordic and Baltic countries: elevation sources (survey 2026-10-31)

Group g5-nordic-baltic: Norway, Sweden, Finland (with Åland), Denmark, Faroe Islands, Iceland, Svalbard and Jan Mayen, Estonia, Latvia, Lithuania. Scripts: `scripts/g5-nordic-baltic/` (`rast.py`: GET and describe a raster or open one by `/vsicurl/` and read a window; `atom_find.py`: ATOM entries around a point; `pdftext.py`: crude PDF text). Samples: `dl/g5-nordic-baltic/`.

Best candidates: **Norway** (1 m DTM and DSM in tiled GeoTIFFs from an ATOM feed, CC BY 4.0, no key), **Sweden** (1 m DTM in COGs from STAC, CC BY 4.0, free login), **Estonia/Finland** (open files, little terrain). Denmark needs a free token. The Faroes and Iceland have the terrain but only satellite models at 2 m.

### Norway (Kartverket): ATOM tiles read in windows
- **Data**: Nasjonal høydemodell (NHM) DTM 1 and DOM 1 (DSM), 1 m, from the national laser scan (2016–2022) and later projects, whole mainland. 2033 tiles of 15 km each for both. The ATOM entries' `updated` dates: 1070 tiles 2021, 262 in 2022, 135 in 2023, 170 in 2024, 397 in 2025. The feed itself was last regenerated on 2025-09-02. The data.norge.no record says "no longer maintained or updated", so watch it.
- **Access**:
  - ATOM `https://nedlasting.geonorge.no/geonorge/ATOM/hoydedata/Hoydedata_ServiceFeed.atom` → `datasett/DTM1.atom` and `DOM1.atom` (5.4 MB each). Each entry has a georss polygon (lat lon), `length` and `updated`, and links `https://nedlasting.geonorge.no/hoydedata/DTM1/33-107-109.tif`. The server is nginx with `Accept-Ranges: bytes` and needs no key.
  - The files are 0.1–1.2 GB GeoTIFFs: float32, LZW, 512 px blocks, nodata −32767, 15010 × 15010 px (a 5 m overlap). They are all in **EPSG:25833**, west Norway (zone 32) included. Pixel edges fall on whole metres (origin x 5425 + n·15000).
  - WCS: `https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-<25832|25833|25835>` and `wcs.hoyde-dom-nhm-*` (ArcGIS Server, coverage `nhm_dtm_topo_<epsg>`). WCS 2.0.1 GetCoverage answered HTTP 400 to every syntax tried; **WCS 1.0.0 works** (`COVERAGE=nhm_dtm_topo_25832&CRS=EPSG:25832&BBOX=...&RESX=1&RESY=1&FORMAT=GeoTIFF`).
  - ImageServer `https://hoydedata.no/arcgis/rest/services/NHM_DTM_25833/ImageServer` (`maxDownloadSizeLimit` 2048, itemAccess false), plus `Prosjekt_DTM`/`Prosjekt_DOM` per project.
  - hoydedata.no: interactive exports.
- **Versions**: one file per tile; the national model is regenerated as projects arrive. `updated` (or Last-Modified) can drive `cache update`. Per-project models (older surveys) exist only behind the Prosjekt_* ImageServers.
- **Licence**: CC BY 4.0 per data.norge.no ("Creative Commons Attribution 4.0 International", open data); the ATOM feed links NLOD 2.0. Both allow redistribution with attribution "© Kartverket".
- **Orthophoto**: Norge i bilder is not open. `wms.geonorge.no/skwms1/wms.nib` answered "Bruker kan ikke autentiseres" (IP authorisation), and `tilecache.norgeibilder.no/wmts/...` answered "Token Required". `cache.kartverket.no` has topographic maps only. So there is no open national orthophoto.
- **Quick tests (2026-10-31)**:
  - WCS 1.0.0 at Kjerag, 500 × 500 m in 25832: DTM and DOM, 0.8 s each, float32 1 m, edges on whole metres, 100% valid, 79–989 m, values not on whole cm.
  - `/vsicurl/` DTM1 33-107-122 (1.18 GB) and DOM1 33-107-109 (Kjerag): a 500 m window in 0.8 s.
  - ATOM lookup by polygon: Kjerag is in 33-107-109 (2021), Lofoten in 33-134-175.
- **Fit**: a new `IndexedTiles` subclass. The index is the ATOM feed: one fetch of 5 MB per product, cached; tiles chosen by polygon. Blocks are read by range requests as in `TnmBlocks`, with no version composing (one file per tile). Working grid EPSG:25833 everywhere (scale error ≈0.3% in the far west, at 5°E). The simple alternative is `WcsTiles` on WCS 1.0.0 (a new request flavour: `WcsTiles` speaks 2.0), server-side in 25832/25835. Whether those are resampled from 25833 is unclear, so prefer 25833.
- **Open questions**: is the ATOM feed still refreshed (2025-09 last)? NN2000 is not named in the files. The WCS size limit was not tested. An open orthophoto: none national, Esri or other fallback.
- **Links**: [ATOM](https://nedlasting.geonorge.no/geonorge/ATOM/hoydedata/Hoydedata_ServiceFeed.atom), [data.norge DTM1](https://data.norge.no/en/datasets/1a7327eb-1fa5-3432-8dea-fc198a5ede13/hoyde-dtm1), [WCS caps](https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25833?service=WCS&request=GetCapabilities), [ImageServers](https://hoydedata.no/arcgis/rest/services), [WCS notices](https://register.geonorge.no/varsler/h%C3%B8yde-dtm-1-utm33-wcs/09547ecb-d9f8-473f-80f6-663af26b2c71).

### Sweden (Lantmäteriet): STAC with a login
- **Data**: Markhöjdmodell Nedladdning grid 1 (DTM 1 m), whole country, one item per 5 × 10 km tile, with the survey date (Kullaberg 2025-03-21) and `data_modified`. The DTM is updated as the new national laser scan (2019–) arrives. **No raster DSM.** The surface exists only as point clouds, "Laserdata skog" (STAC collection `dsm-skoglig-copc`, COPC), under their own terms (`anvandningsvillkor-for-laserdata-nedladdning-skog.pdf`).
- **Access**:
  - STAC `https://api.lantmateriet.se/stac-hojd/v1`, collection `dtm-cog`. The STAC itself is open: items at Kullaberg came back in 0.2 s.
  - Assets look like `https://dl1.lantmateriet.se/hojd/data/grid/mhm/62_3/m624_34.tif`: COG, 26.7 MB, `file:checksum` sha256 multihash (as swisstopo), `proj:code` EPSG:5845 (SWEREF99 TM + RH2000).
  - The files need **HTTP Basic auth**: a free Geotorget account with the product ordered. Lantmäteriet's guide says "Privata användare anger inloggningsuppgifter för Geotorget".
- **Licence**: CC BY 4.0. The catalogue says "avgiftsfria och tillgängliga för användning under Creative Commons licens CC BY 4.0", and the terms are "Användningsvillkor för värdefulla datamängder" (HVD).
- **Orthophoto**: Lantmäteriet's visning services need an account; their open-data status was not confirmed (not tested).
- **Quick tests (2026-10-31)**: STAC root, collections and an items query worked without login; HEAD and `/vsicurl/` of the COG answered 401 (Basic realm). The file's precision and alignment could not be checked. The tile edges are on whole km.
- **Fit**: `StacTiles` with credentials (a server secret, like the OpenTopography key). One item per tile, so newest per tile works. Credits "© Lantmäteriet".
- **Open questions**: rate limits for system accounts; whether a private account may serve a public site (the licence is CC BY, so likely yes); a DSM from COPC (a new mechanism, as for the USA); file precision.
- **Links**: [STAC](https://api.lantmateriet.se/stac-hojd/v1/), [product](https://lantmateriet.se/en/geodata/geodata-products/product-list/elevation-model-download), [download guide](https://www.lantmateriet.se/contentassets/6b85c93c6954407e855c896da5a415f2/guide_radiant_earth_markhojdmodell.pdf), [HVD terms](https://www.lantmateriet.se/globalassets/geodata/geodataprodukter/anvandningsvillkor_for_vardefulla_datamangder.pdf).

### Finland (Maanmittauslaitos) and Åland
- **Data**: Korkeusmalli 2 m (DTM 2 m), whole country "except parts of the outer archipelago or the eastern border", from laser scanning at 0.5 p/m², updated where terrain changed. The new 5 p/m² scanning (2020–) is published as point clouds. No open raster DSM was found. **Åland** is covered by the same model (a window at Mariehamn was 100% valid); the Åland government publishes no elevation data of its own.
- **Access**:
  - NLS: WCS `https://avoin-karttakuva.maanmittauslaitos.fi/ortokuvat-ja-korkeusmallit/wcs/v2` and OGC API Processes `https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1`. Both answered 401 without the free api-key.
  - **Funet mirror (CSC), no key**: `https://mirrors.nic.funet.fi/index/geodata/mml/dem2m/`. It holds `dem2m_direct.vrt` (4.6 MB, refreshed 2026-10-18) over 10 408 sheet files (`2008_latest/K2/K24/K2444F.tif`). Each sheet is 6 × 6 km, 3000 × 3000 px, float32, 256 px blocks, nodata −9999, EPSG:3067, heights N2000, pixel edges on whole metres.
- **Licence**: CC BY 4.0. Credit the NLS, name the dataset and give the date.
- **Orthophoto**: NLS WMTS (`avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts`, api-key, CC BY 4.0); not tested without a key.
- **Quick tests (2026-10-31)**: through the mirror's VRT, a 500 m window at Olhava took 2.2 s, 100% valid, mm values.
- **Fit**: sheets on a fixed grid of TM35 map sheets (`GridTiles`-like with the sheet name computed) or window reads through the VRT (the VRT as the index). With a key, `WcsTiles` too. 2 m only, so useful mainly for Lapland gorges (Korouoma, Julma-Ölkky) and Olhava.
- **Open questions**: does CSC's mirror have a usage policy for automated reads? Is a 1 m product or DSM planned from the 5 p scanning?
- **Links**: [mirror](https://mirrors.nic.funet.fi/index/geodata/mml/dem2m/), [product page](https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/datasets-and-interfaces/product-descriptions/elevation-model-2-m), [2016 spec](https://mirrors.nic.funet.fi/index/geodata/mml/dem2m/mml_korkeusmalli_2m_2016_eng.pdf).

### Denmark (Klimadatastyrelsen, Dataforsyningen): WCS with a token
- **Correction (2026-11-01, terms check)**: the services below are on Dataforsyningen's list of services to be closed ("Oversigt over tjenester der lukkes på Dataforsyningen", updated 2026-10-06: `dhm_wcs_DAF` row 53, `orto_foraar_DAF`/`_webm_DAF`/`_wmts_DAF` rows 81–83, all moving to Datafordeleren); the old Dataforsyningen is phased out in late 2026 and after 2027-01-15 data come only with an API key or OAuth from the modernised Datafordeler (`https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS`, `https://wms.datafordeler.dk/GeoDanmarkOrto/orto_foraar/1.0.0/WMS?apikey=…`). The licence is CC BY 4.0 since 2024-05-16 (credit the data owner, "CC BY 4.0" with a link, the dataset's link, "processed"); the 2022 terms quoted below apply only to data downloaded before that date. The source `denmark` uses Datafordeler.
- **Data**: Danmarks Højdemodel, DHM/Terræn and DHM/Overflade, 0.4 m, whole country (national scan 2014–15, updated since). EPSG:25832, DVR90.
- **Access**: WCS 1.0.0 `https://api.dataforsyningen.dk/dhm_wcs_DAF` (coverages `dhm_terraen`, `dhm_overflade`). GetCapabilities works without a token; GetCoverage answered `403 User not authorized`. A free Dataforsyningen user and token are needed. There are file downloads too (login). The old `wcs.datafordeler.dk` answered 401.
- **Licence**: "Vilkår for brug af frie geografiske data" (1 Dec 2022): "Myndigheden giver en verdensomspændende, gratis, ikke-eksklusiv og i øvrigt ubegrænset brugsret til data, som frit bl.a. kan: kopieres, distribueres og offentliggøres, ændres ..., bruges kommercielt og ikke-kommercielt". Attribution is required ("Indeholder data fra ..., Danmarks Højdemodel, <date>"). The terms may change at any time. Equivalent to CC BY in practice, not named so.
- **Orthophoto**: `orto_foraar` WMS/WMTS on the same token (not tested).
- **Quick tests (2026-10-31)**: capabilities only. Precision, alignment and the size limit are unknown until a token is available.
- **Fit**: `WcsTiles` (1.0.0 request style) with the token from a secret. Terrain: Møns Klint, Bornholm's granite (Jons Kapel, Hammeren).
- **Links**: [WCS caps](https://api.dataforsyningen.dk/dhm_wcs_DAF?service=WCS&request=GetCapabilities&version=1.0.0), [terms PDF](https://dataforsyningen.dk/asset/PDF/rettigheder_vilkaar/Vilk%C3%A5r%20for%20brug%20af%20frie%20geografiske%20data.pdf), [EMD wiki](https://help.emd.dk/mediawiki/index.php/Danish_Elevation_Model).

### Faroe Islands (Umhvørvisstovan)
- **Data**:
  - DSM "hæddarmodell" 2015 at 2, 5 and 10 m, made by SDFE from ArcticDEM (satellite stereo).
  - DTM 10 m from 2009 aerial photogrammetry by COWI, ArcticDEM in the gaps.
  - No lidar.
- **Access**: static files on `cdn.foroyakort.fo` (`FO_DSM_2015_FOTM_2M.tif` 1.3 GB, `FO_DTM_2009_10m.tif` 66 MB). They are tiled (128 px, LZW), so they read in windows. EPSG:5316 (Faroe TM), vertical datum unknown. The origin is not on whole metres (161177.79, 923243.74).
- **Licence**: Umhvørvisstovan's terms (2019) give a worldwide right to copy, distribute and publish, to modify, and to use commercially and non-commercially. Credit the agency, the dataset name and the download date.
- **Orthophoto**: `gis.us.fo/arcgis/rest/services/myndakort/myndakort_fotm/MapServer` (not tested).
- **Quick tests**: a 2 m DSM window near Tórshavn read in 1.0 s, 100% valid.
- **Fit**: windows of one big file (a fixed URL). Huge sea cliffs, but a satellite DSM smooths cliff edges and is not a ground model: medium.
- **Links**: [download page](https://www.foroyakort.fo/tak-datur-nidur/dsm-haeddarmodell/), [terms](https://foroyakort.fo/um-foeroyakort/terms-and-conditions-in-english), [EMD wiki](https://help.emd.dk/mediawiki/index.php/Faroe_Islands_Elevation_Models).

### Iceland (Náttúrufræðistofnun, formerly LMÍ)
- **Data**: ÍslandsDEM v1.0 (2020–21), 2 m. It is built mostly from ArcticDEM (WorldView and GeoEye stereo) with lidar in parts (a lidar-dates layer exists). Accuracy is stated as better than 2 m XY and 0.5 m Z. The 10, 20 and 50 m mosaics cover the whole country.
- **Access**:
  - 10/20/50 m single files on `https://ftp.lmi.is/gisdata/raster/`. The 10 m file is 3 GB, ZSTD-compressed in 512 px blocks, EPSG:8088, with edges on whole 10 m; it reads in windows.
  - 2 m only per grid tile (about 18 × 100 km) by clicking in `https://dem.gis.is/mapview/?application=DEM`. No index or URL pattern was found; the geoserver WFS has none. Staff folders on the ftp (`/stm/michaela/IslandsDEMv1/`) hold derivatives only.
- **Licence**: LMÍ data have been free since 2013. No licence text was found for ÍslandsDEM; the metadata says only "otherRestrictions". To confirm.
- **Orthophoto**: `https://gis.natt.is/mapcache/web-mercator/wms`, layer `grunnkort-loftmynd`. It works in **EPSG:3857 only** (4326: "no grid with suitable srs"). The image at Ásbyrgi was sharp, no watermark.
- **Quick tests**: a 10 m window of 2 km at Ásbyrgi in 2.8 s; the ortho GetMap as above.
- **Fit**: 10 m now (poor); 2 m needs the tile URLs (ask the agency) and then index plus static files. The terrain is excellent: basalt canyons, sea cliffs.
- **Links**: [metadata](https://gatt.lmi.is/geonetwork/srv/metadata/e6712430-a63c-4ae5-9158-c89d16da6361), [ftp](https://ftp.lmi.is/gisdata/raster/), [DEM viewer](https://dem.gis.is/mapview/?application=DEM), [announcement](https://eurogeographics.org/?p=8777).

### Svalbard and Jan Mayen (Norsk Polarinstitutt)
- S0 Terrengmodell DTM 5 (photogrammetry 2008–2012; Bjørnøya 2 m) and DTM 20, CC BY 4.0. Downloads are zipped "delmodell" files through Geonorge, NPI's page and ATOM. Jan Mayen has only 20 m. There is no elevation ImageServer on geodata.npolar.no.
- The orthophoto tiles in EPSG:3857 go to level 17: `https://geodata.npolar.no/arcgis/rest/services/Basisdata/NP_Ortofoto_Svalbard_WMTS_3857/MapServer/tile/{z}/{y}/{x}`.
- ArcticDEM (another group's row) is likely the better source at 2 m. Low priority: remote cliffs.

### Estonia (Maa- ja Ruumiamet)
- **Data**:
  - DTM 1 m on 5 km sheets (1:10 000). Two files per sheet: the current `<sheet>_dtm_1m.tif` and the cycle file `<sheet>_dem_1m_2017-2020.tif`.
  - DSM ("absolute height") and nDSM 1 m on 1 km sheets (1:2000). The sheet number is `<N km − 6000><E km>`, e.g. 541645.
  - Whole country, ALS in 4-year cycles.
- **Access**: `https://geoportaal.maaruum.ee/index.php?lang_id=2&plugin_act=otsing&page_id=664&kaardiruut=<sheet>&andmetyyp=<dem_1m_geotiff|ndsm_abs_1m_geotiff>` returns the links (`...&dl=1&f=64442_dtm_1m.tif`). The download supports Range (206), behind Cloudflare. The files are COG: DEFLATE, 512 px blocks, float32, mm values, EPSG:3301, edges on whole metres. A bulk-download guide exists.
- **Licence**: the board's open-data licence (2025; PDF not readable here). The page says the data are free for everyone with "Map data: Republic of Estonia Land and Spatial Development Board <year>".
- **Orthophoto**: TMS `https://tiles.maaamet.ee/tm/tms/1.0.0/foto@GMC/{z}/{x}/{y}.jpg` (y flipped), up to z18 (z19 404).
- **Fit**: a fixed sheet grid computed from coordinates (`GridTiles`-like with the PHP URL). Good data, little terrain (the North Estonian glint), so low priority.

### Latvia (LĢIA)
- Open (CC BY 4.0): the DTM at 20 m and the classified ALS points (LAS, ≥4 p/m², 1st cycle 2013–19; 2nd cycle ≥6 p/m², published from 2025), plus DSM basic data (2020). A 1 m DTM TIFF in 1 km tiles is offered, apparently free only to public bodies. lgia.gov.lv answered 403 to curl. Gauja sandstone only: low.

### Lithuania (NŽT / geoportal.lt)
- The LiDAR DTM (2012–2017; 5 m public per JRC) comes as ordered packages under a signed licence; release was restricted "due to the war in Ukraine" (2023). Nothing automatic: none.

## UK, Ireland and Crown dependencies (g6-uk-ie)

Researched 2026-10-31. Scripts: `scripts/g6-uk-ie/` (`wcs_get.py`, `cog_probe.py`, `s3tree.py`, `zipdir.py`, `ie_zip.py`). Samples: `dl/g6-uk-ie/`.

**Shared across the group**
- British data are in **EPSG:27700** (OSGB36 / British National Grid) with **ODN Newlyn heights (EPSG:5701)** via OSTN15/OSGM15; Ireland in **ITM EPSG:2157** with **Malin Head (EPSG:5731)**; Northern Ireland's OSNI data in Irish Grid (TM65, EPSG:29902) with Belfast Lough heights (EPSG:5732). All are metric: the working grid can be the files' CRS (`Source.crs`), as for Poland.
- **Orthophoto**: no national open (OGL / CC BY) orthophoto service anywhere in the group. APGB (Great Britain's aerial imagery) is licensed to the public sector only; the Environment Agency's own Vertical Aerial Photography is OGL but only as 5 km ECW downloads of patchy project areas (its WMS holds index layers only); Tailte Éireann's orthophotos are licensed. A fallback for all rows: EOX Sentinel-2 cloudless 2016 (`https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg`, EPSG:3857, CC BY 4.0 for the 2016 layer, 10 m imagery: tiles at zoom 13, 15 and 16 answered at Stanage, but only zoom ≤ 14 shows detail), or the default base map. A decision for the user.

### England (Environment Agency): WCS of the 1 m composite
- **Data**: LIDAR Composite DTM 2022 at 1 m (and 2 m), about 99% of England (data.gov.uk: ">95%"), merged from all EA surveys between 2000-06-06 and 2022-04-02, including the National LIDAR Programme (phase 1 2016–2022, the whole country). Built from the last return. Composite **First Return DSM** and Last Return DSM at 1 m, same coverage. Vertical accuracy of the surveys ±15 cm RMSE. Repeat NLP surveys of some blocks since 2023, but "not currently a plan to capture all the original phase 1 blocks over a rolling programme"; newer time-stamped survey tiles exist (Land's End: `lidar_tiles_dtm-2023`).
- **Access**:
  - WCS 2.0.1 (GeoServer) per product: `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs`, coverage `13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m`; DSM `.../lidar-composite-digital-surface-model-first-return-dsm-1m/wcs`, coverage `df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m` (last return: `9ba4d5ac-...__Lidar_Composite_Elevation_LZ_DSM_1m`). Axis labels `E N`, EPSG:27700, extent 80000–656000 / 4000–665000. Also WMS.
  - Survey tile API (what the DefraDataDownload page uses): `POST https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search` with a GeoJSON polygon (WGS84) returns `{product, year, resolution, tile, uri}` per 5 km OS quarter-sheet; `GET <uri>` streams a ZIP (TIFF + tfw + metadata GPKG; 78 MB for a 1 m DTM tile), chunked without Content-Length and ignoring Range: whole files only.
  - Index of the surveys in the composite: `https://gisrest.defra.gov.uk/server/rest/services/EA/LIDAR_Composite_Catalogues/MapServer`.
- **Versions**: the WCS has the 2022 composite only (static). The survey API lists every product/year/resolution per tile (at Stanage SK28sw: composite 2022, NLP 2021 DTM/DSM/first-return DSM/VOM/intensity/point cloud, lidar_tiles 2008 2 m; at Land's End: time-stamped tiles 1998–2023).
- **Licence**: OGL v3 ("free to copy, publish, distribute and transmit ... adapt ... commercially and non-commercially", GEE's copy of the terms); data.gov.uk lists "No Licence Provided" but the EA states OGL. Attribution: "© Environment Agency copyright and/or database right 2022. All rights reserved."
- **Orthophoto**: none open (see above).
- **Quick tests** (2026-10-31): GetCoverage of 500 × 500 m at Stanage Edge: 0.9 s, uncompressed float32 GeoTIFF (3.9 MB), origin on whole metres, 100% valid, values in mm (7–10% on whole cm); same box from the DSM WCS 1.0 s; 2 km in 2.9 s (10.6 MB), 5 km in 15 s (66 MB with `geotiff:compression=Deflate`). A Land's End box: 100% valid incl. intertidal values to −4 m. Nodata announced as −3.4e38. **Note**: one survey-tile GET ignored the Range header and the whole 78 MB ZIP arrived (deleted at once); the ZIP held a Deflate TIFF of 79 MB.
- **Fit**: `WcsTiles` as is (Spain/Malta pattern), DTM + first-return DSM, `fetch_res` 1, `grid_origin` 0, EPSG:27700. Later and optional: a survey-API driver (POST search, newest year per 5 km tile, whole ZIP) for surveys newer than 2022. Effort S.
- **Open questions**: does the composite get a 2024/2025 edition (and a new WCS coverage id)? Fair-use limits of the DSP (none found). Clip requests to the coverage (England only: Welsh and Scottish boxes answer what?).
- **Links**: [WCS capabilities](https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs?service=WCS&request=GetCapabilities&version=2.0.1), [data.gov.uk record](https://ckan.publishing.service.gov.uk/dataset/01b3ee39-da3f-47b6-83da-dc98e73a461f), [GEE catalogue (terms)](https://developers.google.com/earth-engine/datasets/catalog/UK_EA_ENGLAND_1M_TERRAIN_2022), [survey download](https://environment.data.gov.uk/DefraDataDownload/?Mode=survey), [composite extents](https://gisrest.defra.gov.uk/server/rest/services/EA/LIDAR_Composite_Catalogues/MapServer/2), [Vertical Aerial Photography](https://ckan.publishing.service.gov.uk/dataset/vertical-aerial-photography).

### Scotland (Scottish Government / SRSP): COGs on AWS, coverage growing
- **Data**: the **Scottish Land LiDAR Programme** (national, captured by Bluesky May 2025 – July 2027, 10 pts/m², releases about every 6 months; first release 2026-01-29, files on S3 of 2026-09-25): DTM and DSM at 50 cm in 1 km tiles; on 2026-10-31 5933 DTM tiles (89 GB), about 7.5% of Scotland: NX (Galloway, 2799), NR (Kintyre/Arran/Islay, 1097), NO, NK (Aberdeenshire coast), NY, NM, NG, NL, NW, NS. Older collections: LiDAR for Scotland phases 1–6 (2011–2022; phase 1 and 2 at 1 m in 10 km tiles, phases 3–6 at 50 cm in 5 km tiles: flood areas, SPEN power lines, cities), Outer Hebrides 2019 (25/50 cm), HES archaeology surveys, Orkney Islands Council 2023, coastal 2025–2026. The footprint WFS shows nothing at Ben Nevis or the Cuillin yet.
- **Access**: public S3 bucket `srsp-open-data` (eu-west-2, AWS Open Data Sponsorship): `https://srsp-open-data.s3.eu-west-2.amazonaws.com/lidar/<collection>/<dtm|dsm>/27700/gridded/<OS tile>_<res>_<DTM|DSM>_<suffix>.tif`, listable without sign-in (ListObjectsV2 with prefix). Collections: `national-lidar-programme`, `phase-1`..`phase-6`, `outer-hebrides/2019/<dtm|dsm>/<25cm|50cm>`, `hes/<survey>`, `orkney-islands-council-23`, `coastal/coastal-2025-2026`. Footprints: WFS `https://ows.remotesensing.data.gov.scot/geoserver/ows`, `scotland:dsm-footprint-aggregate` (19 multipolygons, one per collection; the NLP only as NR/NS/NX so far: it lags the bucket). The portal's WCS is disabled ("ServiceUnavailable"); its WMS has one layer per collection (pictures).
- **Versions**: one file per collection and tile; collections overlap (phase 4 and 5 both have NO10NE) and cover parts of tiles: compose newest first per block (the 3DEP pattern), the NLP first.
- **Licence**: OGL v3 for everything except the phase 2 LAZ point clouds (non-commercial government licence) (AWS registry). NLP attribution: "Crown copyright Scottish Government © Crown copyright and database right (2025)".
- **Orthophoto**: none open.
- **Quick tests** (2026-10-31): NLP `NG2104_50cm_DTM_ScotlandNationalLiDAR.tif`: COG, LZW, 528 px blocks, overviews 2/4, 2000 × 2000 px at 0.5 m, edges on whole metres, nodata −32767, open 0.3 s, 500 px window 0.4 s, 100% valid. Phase 4 `NO10NE_50CM_DSM_PHASE4.tif` (264 MB): 10000 × 10000 px, 256 px tiles, overviews to 32 (no COG layout tag, still window-readable), window 0.6 s. Phase 1 `HY21_1M_DTM_PHASE1.tif`: 1 m, 256 px tiles, no overviews, values on whole cm, top edge 1011999.997 (3 mm off). WFS footprints: 2 collections at Edinburgh, 2 in Orkney, none at Ben Nevis/Cuillin.
- **Fit**: a new subclass in the `TnmBlocks` pattern: the index from S3 listings per collection prefix (OS tile names give the extent; cached per 0.25° or per 100 km square) or the WFS footprints, windows of the tiled files cached as blocks in EPSG:27700, collections composed newest first (NLP 2025+ > coastal 2025 > Orkney 2023 > phases ...). Resolutions differ (1 m vs 0.5 m). Effort M.
- **Open questions**: the NLP coverage of the Highlands (Glen Coe, Ben Nevis, Skye) by 2027; vertical datums of the islands (Orkney, Shetland, Hebrides use local datums in OSGM15: check a file); whether the "-limited" Outer Hebrides layer has another licence; attribution wording of the phases.
- **Links**: [AWS registry](https://registry.opendata.aws/scottish-lidar/), [bucket listing](https://srsp-open-data.s3.eu-west-2.amazonaws.com/?list-type=2&delimiter=/&prefix=lidar/), [SRSP](https://remotesensingdata.gov.scot/), [NLP DTM record](https://www.data.gov.uk/dataset/3b97cedc-bd0e-4602-bf6a-dadae3c5b54d/scottish-land-lidar-programme-2025-capture-dtm), [first release blog](https://blogs.gov.scot/digital/2026/01/29/scotlands-lidar-revolution-first-data-release-to-reveal-scotlands-landscape-in-unprecedented-detail/), [Phase 1 DTM record](https://spatialdata.gov.scot/geonetwork/srv/api/records/40017f89-2857-49cb-a913-e0784f250769), [NLP metadata ZIP](https://maps.data.gov.scot/shapefiles/LiDAR/SG_NLP_Metadata.zip).

### Wales (Welsh Government): one national COG per model
- **Data**: Welsh Government LiDAR 2020–22 (survey by NRW; the tile catalogue says 2020–2023), DTM and DSM at 1 m for the whole of Wales. Older NRW archive tiles (1998–2019) in a separate catalogue.
- **Access**: one Cloud Optimized GeoTIFF per model on Azure Blob: `https://dmwproductionblob.blob.core.windows.net/cogs/lidar/wales_dtm_32bit_cog.tif` (48.6 GB) and `wales_dsm_32bit_cog.tif` (52.1 GB); 16-bit variants (3.6 GB) store whole metres: not usable. DataMapWales also offers 1 km tile downloads (WFS `geonode:welsh_government_lidar_tile_catalogue_2020_2023` with download links) and WMS layers.
- **Versions**: one release (blob dated 2024-10-04); a new release would probably replace the file in place (watch ETag/Last-Modified).
- **Licence**: OGL v3 (DataMapWales metadata of the LiDAR viewer and the tile index); no attribution statement given ("Copyright: None"); NRW's own data use "© Natural Resources Wales and Database Right". Suggested: "Contains Welsh Government information licensed under the Open Government Licence v3.0" (confirm with data@gov.wales).
- **Orthophoto**: none open: the APGB layers on DataMapWales carry the APGB public-sector licence; "APU Welsh Government Aerial Photography" has no licence stated.
- **Quick tests** (2026-10-31): both COGs: EPSG:27700, 191007 × 233000 px at 1 m, origin 164993 / 397000 (edges on whole metres), float32 Deflate, 256 px blocks, overviews 2–64, nodata −9999. 1 km windows: Llanberis Pass DTM 0.6 s (144–801 m, 100% valid), DSM 0.6 s; St Govan's Head DTM 0.4 s (63.6% valid: sea is nodata), DSM 0.3 s. Values on whole cm.
- **Fit**: windows of one big COG at a fixed URL: the `DegreeBlocks` mechanism with a single file (blocks of 1 km cached in EPSG:27700 as they are, `grid_origin` 0); no index needed. Effort S.
- **Open questions**: vertical datum (ODN assumed, not stated); attribution wording; update policy of the blob.
- **Links**: [LiDAR viewer metadata (COG URLs, OGL)](https://datamap.gov.wales/maps/4419/metadata_detail), [LiDAR viewer](https://datamap.gov.wales/maps/lidar-viewer/), [tile catalogue 2020–2023](https://datamap.gov.wales/layers/geonode:welsh_government_lidar_tile_catalogue_2020_2023/metadata_detail), [delivery index](https://datamap.gov.wales/layers/geonode:wg_lidar_2020_2022_delivery_index/metadata_detail), [NRW archive](https://datamap.gov.wales/layers/inspire-nrw:NRW_LIDAR_ARCHIVE_TILE_CATALOGUE/metadata_detail), [APGB dates flown](https://datamap.gov.wales/layers/geonode:apgb_dates_flown_wales/metadata_detail).

### Northern Ireland (OSNI, DAERA): nothing usable at Fair Head
- **Data**: OSNI Open Data 10 m DTM (national, from the Enhanced DTM 2014–2016, sheet ZIPs, OGL); River Basin LiDAR 2009–2012 at 1 m (DTM ASCII grids + DSM point clouds per area ZIP of 36–615 MB, about 14% of NI: river basins and towns); the **2021 NI 3D Coastal Survey** (DAERA, 0.25 m DTM/DSM, intertidal to about 200 m inland, OGL) is published only as a cached Web Mercator map service (TPK): pictures, not heights.
- **Access**: OpenDataNI CKAN (`https://admin.opendatani.gov.uk/api/3/action/package_show?id=...`), downloads redirected to signed Cloudflare R2 URLs (range requests work, HEAD does not).
- **Licence**: UK OGL.
- **Quick tests** (2026-10-31): the central directory of `ballycastle_15_03_2010.zip` (214 MB): 15 DTM_1M ASCII tiles of 1 km on the Irish Grid (D0939–D1340) and xyz point clouds; the tiles end about 5 km west of Fair Head (D17/D18). The coastal DTM's ArcGIS item: Map Service, "source resolution of 0.25m ... cached".
- **Fit**: none (europe). Ask DAERA (opendatani@nidirect.gov.uk) for the 2021 coastal rasters; with them, own hosting (GridTiles) of the coastal strip would cover Fair Head's lower crag only if the rim lies within ~200 m of the high-water mark.
- **Links**: [River Basin LiDAR 2010 (API)](https://admin.opendatani.gov.uk/api/3/action/package_show?id=osni-open-data-river-basin-lidar-2010-dtms-and-dsms), [2021 coastal DTM](https://www.data.gov.uk/dataset/b2f01fd0-7324-4438-b7b7-85535f48f172/2021-ni-3d-coastal-survey-topographic-lidar-digital-terrain-model21), [its ArcGIS item](https://www.arcgis.com/home/item.html?id=50b8b7bb178448afae08f8f0340552a3), [10 m DTM](https://www.nidirect.gov.uk/articles/10m-digital-terrain-model-height-data).

### Ireland (GSI Open Topographic Data): small tiles, patchy coverage
- **Data**: no national LiDAR. GSI publishes the LiDAR of its partners as 2 km tiles with DTM and DSM: OPW flood-risk surveys (2 m, 2011, ~4100 tiles incl. coasts), TII road corridors (2 m, 2567), GSI/Department of Housing/Discovery Programme (1 m and finer, 605), GSI Phase 2 (1 m, 2018, 144), Dublin (NYU, 1 m), Cork (OPW 12.5 cm), Westmeath (25 cm), photogrammetric DSM (25 cm). Years 2011–2021. **The Cliffs of Moher have no tile in any programme.**
- **Access**: index = ArcGIS FeatureServers `https://gsi.geodata.gov.ie/server/rest/services/Lidar/IE_GSI_LiDAR_Coverage_<programme>_IE26_ITM/FeatureServer/<layer>/query` (layer ids differ: 0, 3, 12) with `DATA_URL`, `RESOLUTION`, `DATECAPTUR`, `LICENCE`, `EXT_LEFT/TOP/RIGHT/BOTTOM`; files are static ZIPs (`https://gsi.geodata.gov.ie/downloads/LiDAR/OPW_NASC/OPW_<n>.zip`, `.../LIDAR/<id>.zip`) or 7z (Phase 2). The ImageServers under `imagehost/rest/services/Lidar` are hillshades only.
- **Formats**: OPW: GeoTIFF float32 uncompressed, 1000 × 1000 px at 2 m in strips, DTM + DSM + licence text, 2–4 MB per ZIP; GSI/DCHG: ESRI ASCII grids; Phase 2: 7z (a new dependency, py7zr).
- **CRS/heights**: ITM EPSG:2157 with Malin Head heights (service names `_ITM_MH_`), but the OPW files carry a MapInfo `_MI_0` CRS without EPSG code and an origin 3–5 mm off whole metres.
- **Licence**: CC BY 4.0 (data.gov.ie); the statement per tile, e.g. "Contains Irish Public Sector Data (Geological Survey Ireland & the Office of Public Works) licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) licence."
- **Orthophoto**: none open (Tailte Éireann imagery is licensed).
- **Quick tests** (2026-10-31): FeatureServer queries at the Cliffs of Moher (none), Dublin and Kerry (OPW_NASC 2 m 2011); `OPW_34.zip` (2 MB) read by range requests and opened through `/vsizip//vsicurl/`: 2 m, nodata −9999, 31% valid (coast); `560607.zip`: ASCII grids.
- **Fit**: new driver: an ArcGIS FeatureServer index (`IndexedTiles`) + one small ZIP per tile, programmes composed by resolution/year, CRS forced to EPSG:2157 and origins rounded. Effort M. Worth it only where the coverage reaches climbing areas (check Burren, Ailladie, Fair Head is NI, Donegal).
- **Links**: [data.gov.ie](https://data.gov.ie/dataset/open-topographic-lidar-data), [coverage services](https://gsi.geodata.gov.ie/server/rest/services/Lidar), [hillshade ImageServers](https://gsi.geodata.gov.ie/imagehost/rest/services/Lidar), [viewer](https://dcenr.maps.arcgis.com/apps/webappviewer/index.html?id=b7c4b0e763964070ad69bf8c1572c9f5), [GSI news](https://gsi.ie/en-ie/events-and-news/news/Pages/Open-Topographic-Data-Viewer.aspx), [OPW release](https://www.gov.ie/en/press-release/1c968-opw-releases-lidar-captured-as-part-of-flood-risk-management-projects-as-open-data).

### Isle of Man
LiDAR (DTM, DSM, point clouds) sold through Bluesky's Mapshop since 2016; no open release found. gov.im and data.gov.im answered automated requests with a CAPTCHA / "Request Rejected" (check by hand). FABDEM only. [GIM news](https://www.gim-international.com/content/news/first-online-3d-maps-of-isle-of-man).

### Jersey
A 2020 island LiDAR survey (Jersey Heritage, government co-funded) is not published as open data. FABDEM only. [JEP 2020](https://jerseyeveningpost.com/news/2020/04/22/mystery-of-low-flying-plane-finally-solved/).

### Guernsey
Digimap Guernsey data are commercial; no open elevation found. FABDEM only. [OKFN index](https://2015.index.okfn.org/place/guernsey/map).

### Gibraltar
Only a 2023 drone LiDAR of the Northern Defences announced; nothing published. Open question: whether Spain's PNOA LiDAR (already a source) reaches over the border onto the Rock. [Press release](https://www.gibraltar.gov.gi/press-releases/northern-defences-lidar-survey-and-current-works-8552023-9460).

## Group g7-southeast-east: elevation sources (researched 2026-10-31)

South-east Europe, the Black Sea and the Caucasus. Summary: **none of the EU members of this group (HR, RO, BG, CY, GR) publishes its LiDAR elevation as an open bulk/API download yet**, despite the HVD regulation. The nearest candidates:
- **Bulgaria**: an open WCS of the Ministry of Agriculture with a 1 m DTM over the whole country (three yearly bands 2023–2025). It is technically ready for `WcsTiles`, but the licence is unclear.
- **Croatia**: a 1 m LiDAR DMR/DMP of the whole country (2021–23), free on request under a licence that allows reuse. A clause in it ("no readable point heights") may not fit a public map.
- **Romania**: LAKI 0.5–1 m in parts of the country under OGL ROU, but its geoportal has been offline since the ransomware attack of 2026-07-14.

Scripts: `scripts/g7-southeast-east/` (`cog_probe.py`, `wcs_probe.py`); samples: `dl/g7-southeast-east/`.

---

### Croatia (DGU): 1 m LiDAR on request, open ATOM only 20 m
- **Data**: the project "Multisenzorsko zračno snimanje Republike Hrvatske" (EU-funded, 2020–2023; flights 2021–2023) covered the whole country with LiDAR. Group 1 (east and south, 50.5%) and group 2 (west, 49.5%), plus a corridor of the levees. Products: classified point cloud (LAS/LAZ), DMR (DTM) and DMP (DSM) at **1 × 1 m as TIFF + TFW per sheet of the 1:2000 grid** (the DOF2 sheets). Also a LiDAR orthophoto 1:5000 of 2022/23. No new cycle announced.
- **Access**: no service. A request form, "ZAHTJEV - LIDAR PODACI" (under "Podaci za ponovnu uporabu" on https://dgu.gov.hr/podnesite-zahtjev-91/91), goes by e-mail to izdavanje.podataka@dgu.hr with a sheet list or a boundary SHP; the sheet index is the ATOM file `podjele_na_listove.zip`. DGU sends a link or hands the data over on a disk in Zagreb (mjestoivrijeme.hr, 2024-05). No fee for the LiDAR data ("actual costs" may apply under NN 56/23, 106/25). The open INSPIRE ATOM "Visine" (`el-cov`) is a **20 m** DMR in 84 uncompressed float64 GeoTIFFs of 34 MB (EPSG:3045), marked "access limited per art. 13(1)(e)": useless. The photogrammetric DMR WMS needs an `authKey` (registered users).
- **Versions**: one survey.
- **Licence** (page 2 of the form): "Ova dozvola omogućava korisniku svaku uporabu informacija … besplatno, neisključivo …". It allows commercial use and redistribution ("reproducirati, distribuirati i stavljati na raspolaganje trećim osobama"), with conditions: name the source and the date of its last change, and link the dataset. The key extra condition: "kod javne objave prikazati podatke na način da nije moguće izravno dobiti podatak o pojedinoj koordinati i visini točke ili objekta". On publication the data must be shown so that no one can read the coordinate and height of a single point; third parties must be told the same. A map of lines with anchor heights might conflict with it, and so would hosting raw tiles.
- **Orthophoto**: anonymous WMS 1.3.0 `https://geoportal.dgu.hr/services/inspire/orthophoto_lidar_2022_2023/wms` (layer `OI.OrthoimageCoverage`; also `orthophoto_2021_2022`, `orthophoto_2019_2020` needs registration). Serves EPSG:4326/3765/3035/4258. A **large "GEOPORTAL" watermark** is in every image. Fees: "Naknada" per the Pravilnik; DGU's terms forbid copying it into a database.
- **Quick tests** (2026-10-31): ATOM feed and one 20 m file opened by `/vsicurl/` (strips, uncompressed, float64, 2073 px of 20.0136 m). Ortho GetMap 512 px over Paklenica: 99 kB in 1 s, sharp, watermarked. data.gov.hr: "Digitalni model reljefa" (WMS with authKey) and "Visine INSPIRE" (the ATOM) only.
- **Fit**: no automatic way. Options:
  1. Ask for the LiDAR sheets of chosen areas (Paklenica, Cetina, Biokovo) and import them by hand: own hosting (`GridTiles`), small areas.
  2. Ask DGU for the whole country as a bulk delivery and for a clarification of clause II for a public site that shows derived lines. Then host the data (Slovak pattern), if redistribution is allowed.
  Expect HTRS96/TM (EPSG:3765) and HVRS71 heights; check the half-pixel alignment of the TFWs.
- **Open questions**: does clause II forbid showing line heights on the public site? Is a bulk delivery of the whole country possible? CRS, vertical datum and alignment of the files? Does the September 2025 redesign of the geoportal plan a download service (HVD)?
- **Links**: https://dgu.gov.hr/multisenzorsko-zracno-snimanje-republike-hrvatske/5700, the form PDF (licence) https://dgu.gov.hr/UserDocsImages/dokumenti/Pristup%20informacijama/Podnesi%20zahtjev/PODACI%20ZA%20PONOVNU%20UPORABU/ZAHTJEV%20-%20LIDAR%20PODACI.pdf, https://www.mjestoivrijeme.hr/napokon-javno-dostupan-lidar-snimak-rh, https://geoportal.dgu.hr/services/atom/el-cov/xml, https://data.gov.hr/ckan/dataset/digitalni-model-reljefa

### Romania (ANCPI): LAKI 0.5–1 m under an open licence, geoportal offline
- **Data**:
  - LAKI LiDAR programmes. LAKI III zone A (Caraș-Severin, Gorj, Mehedinți, Dolj): **0.5 m DTM** in 1 km packages. LAKI II (west: Arad, Bihor, Hunedoara, part of Alba; Mureș, Harghita in scope): 1 m in 40 km blocks. LAKI III zone B (Suceava, Neamț, Bacău, Vrancea) is next; LAKI III targets about 50,000 km². This comes from a 2026 arXiv paper (RO-LiDAR GeoQuickView, an independent viewer that reuses the public ANCPI tiles), not from ANCPI.
  - The national "Modelul Numeric al Terenului": a mosaic of 2/5/10 m per county, mostly from 1:50k contours, with river-basin LiDAR of 1–2 m and LAKI II S1 (2019). Its accuracy follows the contours: 10 m in the mountains.
  - Whether a LAKI DSM is published is unclear.
- **Access**: the geoportal's download application (geoportal.ancpi.ro: choose a tile, a form with an e-mail address, a link by e-mail; ArcGIS folder `hosted_services/rest/services/Descarcare` with `LAKI` and `MNT_tiles` services). It is **offline**: a ransomware attack on 2026-07-14, with applications moved to the government cloud and restored in stages. geoportal.ancpi.ro and geoportal.gov.ro did not resolve on 2026-10-31 (www.ancpi.ro does). data.gov.ro holds only the MApN 25 m model (CC BY 4.0).
- **Licence** (MNT): an adapted OGL ROU 1.0, "Vă este permis să: Copiați, publicați, distribuiți informația; … re-folosiți informația în scop comercial sau necomercial". Attribution: "Date realizate de ANCPI" and www.geoportal.gov.ro. The LAKI licence text was not seen (probably the same family).
- **Orthophoto**: ANCPI WMS on the same geoportal (offline); not tested.
- **Quick tests**: none possible. DNS failure; the Wayback Machine was offline; its CDX listed `Descarcare/LAKI/MapServer` in 2023-05.
- **Fit**: unclear until the service is back. It looks like ArcGIS (MapServer/ImageServer, or the download app's predefined tiles): a new driver. OGL allows own hosting of the LAKI tiles if the download stays manual. Stereo 70 (EPSG:3844); the Black Sea 1975 heights are to be confirmed.
- **Open questions**: when does the geoportal return, and does the download app come back unchanged? Licence and format of the LAKI tiles (GeoTIFF? alignment?). Is there a LAKI DSM? Coverage map of LAKI II/III.
- **Links**: the licence PDF (copy) https://help.emd.dk/mediawiki/images/c/ca/Licen%C8%9Ba_deschisa_Modelul_numeric_al_terenului_v2_MNT.pdf, https://arxiv.org/html/2606.08876v1, https://ancpi.ro/laki3/en, https://www.digi24.ro/digieconomic/digital/ancpi-muta-aplicatiile-in-cloudul-guvernamental-dupa-atacul-cibernetic-cand-ar-putea-reveni-serviciile-110985

### Bulgaria (Ministry of Agriculture and Food): open WCS with a 1 m DTM, licence unclear
- **Data**: the LPIS aerial survey of the Ministry of Agriculture and Food (MZH; a third of the country per year) gives an orthophoto and a DEM per year:
  - `Dem_2023`, `Dem_2024`, `Dem_2025`: **1 m, called DTM** in the metadata ("DTM is presented in 2023 - 2025 while DSM was presented in previous years"; made "by interpolation … of raw altimetric data": photogrammetric, not LiDAR). Bounding boxes: 2023 the central-west band (y 4680–4800 km), 2024 the south (y 4566–4740 km), 2025 the north. Together they cover about the whole country (holes not checked).
  - `Dem_2020`–`Dem_2022`: 4 m (DSM); `Dem_Alternative`: 4.005 m.
  - The national mapping agency, AGKK, has nothing open; the military geographic service holds another DEM.
- **Access**: **open WCS 2.0.1** `http://inspire.mzh.government.bg:8080/geoserver/ows` (GeoServer, HTTP only, port 8080; capabilities: Fees NONE, AccessConstraints NONE). Coverages `RasterData__Dem_<year>` and `RasterData__Orthoimagery_<year>`, all in EPSG:32635 (UTM 35N even in the west, zone 34), axes E/N, float32 GeoTIFF. The INSPIRE download-service record points to a price list (`ceni.pdf`) instead of a download.
- **Versions**: one coverage per year, each a band; newest first, as with yearly bands.
- **Licence**: unclear and probably restrictive.
  - The dataset metadata says "public access limited according to Article 13(1)(d)" and "No conditions apply to use".
  - The download-service record says "no limitations to public access".
  - MZH sells the orthophoto per sheet under a contract with a **non-distribution declaration**.
  - No open licence was found. Ask the metadata contact (pddimitrov@mzh.government.bg).
- **Orthophoto**: WMS 1.3.0 on the same GeoServer, layers `RasterData:Orthoimagery_2020..2025` (and `_2025_TB`), many CRSs including EPSG:4326. A 512 px GetMap in 0.3 s with no watermark. Terms as above.
- **Quick tests** (2026-10-31):
  - DescribeCoverage: `Dem_2023` x 117320–460000, y 4680000–4800000, 1 m; nodata -3.4e38 (`Dem_2025`: 0).
  - 500 × 500 m GetCoverage in the Vratsa gorge (43.188 N, 23.517 E): 3.9 MB in 0.5 s, 100% valid, 458–594 m, **99% of values on whole cm**, pixel edges on whole metres.
  - 800 m box at 43.1975/23.5105: 697–1132 m, maximum slope 71.5° (1.2% of pixels above 60°). The 4 m 2020 DSM gives 85°, partly over trees.
  - `Dem_2025` at Vratsa town: all nodata; `Dem_2024` there: "Empty intersection".
- **Fit**: `WcsTiles` as is (fixed tiles in EPSG:32635, native 1 m). One layer per year composed newest first, or the three 1 m years as one source, since the bands hardly overlap. Effort S once the licence allows it. Check:
  - the vertical datum (shift against Copernicus);
  - how sharp the photogrammetric DTM is at the walls of Vratsa (it may smooth vertical cliffs);
  - the band edges and holes (valid pixels at 5 m over the country);
  - the size limit of a request.
- **Open questions**: may a public, non-commercial site use the WCS and show derived lines? (The non-distribution declaration applies to sold sheets; the WCS has no terms.) Vertical datum (Baltic 1982 or EVRS 2007)? Is the 1 m model really ground-only everywhere, and is there a 1 m DSM? The 2026 survey band?
- **Links**: http://inspire.mzh.government.bg:8080/geoserver/ows?service=WCS&version=2.0.1&request=GetCapabilities, the DEM metadata https://inspireportal.egov.bg/geonetwork/srv/eng/csw?service=CSW&version=2.0.2&request=GetRecordById&outputSchema=http://www.isotc211.org/2005/gmd&elementSetName=full&id=ac4118bf-b7b8-460b-822e-06757790a54e, https://www.mzh.government.bg/bg/politiki-i-programi/programi-za-finansirane/direktni-plashaniya/cifrova-ortofotokarta/, https://www.mzh.government.bg/bg/uslugi/administrativni-uslugi/izdavane-na-administrativni-aktove/kopiya-ot-cifrovata-ortofoto-karta/. The EU INSPIRE geoportal's certificate had expired; the national catalogue `inspireportal.egov.bg` answers.

### Cyprus (DLS): DTM/DSM behind a government login
- **Data**: DTM and DSM from photogrammetric surveys of "different time periods"; a 5 m 2014 mosaic of DLS tiles is mirrored on Zenodo (CC BY 4.0 claimed by the uploader). No LiDAR found.
- **Access**: e-services with a Cyprus government login, free up to 1 GB per user per day; beyond that a form and EUR 17/km² (areas over 50 km² need the Director's approval). The DLS API catalogue lists only contours (ArcGIS MapServer, access on request to the portal administrator). data.gov.cy has no CKAN API.
- **Licence**: not stated (a disclaimer page); unclear.
- **Orthophoto**: DLS ArcGIS services, access on request; paid TIF/JPEG.
- **Quick tests**: none (nothing anonymous).
- **Fit**: none (europe); own hosting only if DLS allows. **Highline**: a few sea cliffs (Akamas): low.
- **Links**: https://portal.dls.moi.gov.cy/en/application_forms/fotogrammetrika-dedomena/, https://portal.dls.moi.gov.cy/en/alles-ypiresies/katalogos-apis/, https://zenodo.org/records/6006664

### Greece (Hellenic Cadastre): unchanged, no distribution
- The LiDAR "High Definition Elevation Base Map" (DEM_HD, RRF; 1 m DTM/DSM, about 47% of the country) was shown at a EuroSDR quality-control workshop in November 2025 (Amorgos samples). Press of 2026 mentions a planned second phase for the whole country. **No distribution or licence announced.**
- The new data.gov.gr (CKAN, 2026) has no national elevation dataset (searches: lidar, DEM, DTM, elevation, υψομετρικό: only municipal WMS layers). data.ktimatologio.gr answers 403.
- The roadmap's decision stands. Keep watching (expect EGSA87 sheets).
- **Links**: https://eurogeographics.org/app/uploads/2025/06/04.-Lolonis-P-et-al.-2025-Quality-control-procedures-for-high-definition-aerial-LIDAR-data-in-Greece-SDQ-2025-5th-Int-Work-on-SDQ-EuroSDR-Eurogeographics-Athens-Nov-20-21.pdf

### Serbia (RGZ): not open
DTM from aerial photogrammetry on a 5/10/25 m grid (2007–2013) for the country; a 1 m LiDAR DTM only for flood areas (Tisa, 2020 km², 2012; more under way). It is issued by RGZ (paid); geoSrbija has views only. The OSM community reports laws and project contracts that prevent opening. https://www.rgz.gov.rs/digital-terrain-model

### Bosnia and Herzegovina: national LiDAR in verification, no distribution yet (one row)
An EU IPA II 2019 project, coordinated by the Ministry of Civil Affairs with FGU and the Republika Srpska agency, scans the whole country (5–10 pts/m², DTM and DSM). FENA reported verification under way on 2026-08-24. FGU plans an e-service for distribution; terms are unknown. One row, because both entities share the national project. **Watch it**: the Neretva and Rakitnica canyons. https://fgu.com.ba/en/the-surveying-project-of-bosnia-and-herzegovina-territory-lidar-ipa-ii-2019.html, https://fena.ba/article/1693414/bihs-first-lidar-mapping-nearing-completion-data-verification-underway

### Montenegro: nothing open
A DTM from laser scanning and photogrammetry of the whole country (Geofoto, 2010–11, Norwegian funds); a new orthophoto in 2025. No download or WCS found; geoportal.co.me did not answer. https://en.lider.media/?p=183365

### Kosovo (AKK): nothing open
The AKK report of 2023 names a DTM and a DSM; geoportal.rks-gov.net is a viewer (no OGC endpoints found). https://akk.rks-gov.net/storage/app/media/raporti-dhjetor-2023-web-view.pdf

### Albania (ASIG): DTM/DSM only as hillshade views; open orthophoto WMS
"MDT (2015-2017) 3D" and a DSM are published as hillshade layers (WMTS `Dtm_2015:Hillshade_2015_group`, `DSM:Dsm_Hill_Group`). ASIG's WCS has 164 coverages, none of them elevation. Orthophoto: WMS `https://geoportal.asig.gov.al/service/ows`, layer `ortofoto_2018:Ortofoto_2018`, EPSG:4326 (Tirana: 48 kB, sharp, no watermark; capabilities: Fees and AccessConstraints NONE, terms unclear). A possible map background for Albania even with FABDEM terrain. https://geoportal.asig.gov.al/service/wmts?request=getCapabilities

### North Macedonia (AREC): LiDAR for sale
LiDAR (Kartverket project): 46% covered by 2021, phase 2 under way. Classified points, DTM and DSM are sold through the AREC LiDAR portal (choose an area, buy). The katastar.gov.mk hosts did not answer from here. https://eurogeographics.org/?p=10319

### Moldova (AGCC): 5 m DTM of 2007, view only
WMS on geodata.gov.md; its GeoServer answers "Service WCS is disabled". https://data.source.coop/nlebovits/moldova-geodata/wms/dtm/README.md

### Ukraine: nothing open
No open elevation data; geodata restricted under martial law since 2022.

### Short rows: Turkey, Russia, Belarus, Georgia, Armenia, Azerbaijan
No open national elevation data found:
- **Turkey**: HGM sells DEMs. Pity for Geyikbayırı and Cappadocia.
- **Russia**: large-scale elevation is restricted.
- **Belarus**: flat, nothing open.
- **Georgia** (NAPR), **Armenia**, **Azerbaijan**: nothing found.

All stay on FABDEM/Copernicus.
