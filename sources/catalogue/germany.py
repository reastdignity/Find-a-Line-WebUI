"""The German Länder: Saxony-Anhalt (LVermGeo's DGM1 and DOM1 from WCS), Lower Saxony (LGLN's DGM1
and DOM1 from STAC), Hesse (HVBG's DGM1 and DOM1 from WCS), Mecklenburg-Vorpommern (LAiV's DGM1 and
DOM1 from WCS), Saxony (GeoSN's DGM1 and DOM1, zipped 2 km GeoTIFFs) and Baden-Württemberg (LGL's DGM1
and DOM1, zipped 2 km tiles of 1 km XYZ grids or GeoTIFFs), Bavaria (LDBV's DGM1 and DOM20 listed by
Metalinks), Rhineland-Palatinate (LVermGeo RP's DGM1 and DOM1 listed by Metalinks), North Rhine-Westphalia
(Geobasis NRW's DGM1 and DOM1 from WCS), Brandenburg with Berlin (LGB's DGM1 and DOM1 from WCS),
Schleswig-Holstein (LVermGeo SH's DGM1, plain XYZ files listed by a GeoJSON index), Saarland (LVGL's DGM1
and DOM1, members of district ZIP archives read by HTTP Range), Hamburg (LGV's DGM1 and bDOM1, members of two ZIP
archives) and the Land Bremen's two cities, Bremen and Bremerhaven (the DGM1 and DOM1 of Landesamt GeoInformation
Bremen, XYZ members of a ZIP archive per city and model, on two grids: two sources)."""

from typing import List

from ..credit import CC_BY, DL_DE_BY, YEAR, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.stac import StacTiles
from ..layers.wcs import WcsTiles
from ..layers.zipped import ZippedTiles
from ..layers.metalink import MetalinkTiles
from ..layers.geojson import GeoJsonTiles
from ..layers.zipmembers import ZipMemberTiles
from ..readers.zipmember import TransformFix

# LVermGeo's terms of use (Nutzungsbedingungen V 5.0, 01.03.2024, no. 2): open data under dl-de/by-2.0,
# the provider named "© GeoBasis-DE / LVermGeo ST"; dl-de/by-2.0 §3 asks for a note of changes ("Daten
# geändert": a mosaic on our grid is one)
LVERMGEO_ATTRIBUTION = "© GeoBasis-DE / LVermGeo ST"
LVERMGEO_CREDIT = Credit("DGM1 / DOM1 (LVermGeo, Saxony-Anhalt)", f"{LVERMGEO_ATTRIBUTION}, Daten geändert",
                         *DL_DE_BY)
# The open-data WCS of the DGM1 and DOM1, the services LVermGeo's open-data page lists (ArcGIS, coverage
# Coverage1, extent 606000-790000 / 5646000-5882000). Until 2026-11-01 the INSPIRE WCS
# (ows_INSPIRE_LVermGeo_ATKIS_EL_DGM_WCS / _DOM_WCS) was read: three 2 km tiles of each (inside, at the
# edge and outside the Land) were equal to the last bit in both, with the same extent, format and
# multipart answer, so the cache folders stay
LVERMGEO_WCS = "https://geodatenportal.sachsen-anhalt.de/ows_WCS_ST_{}1"
# DOP20 of LVermGeo, its open-data WMS in EPSG:4326 (dl-de/by-2.0 like all its open data); no request
# limits published
LVERMGEO_DOP = OrthoService("DOP20 Sachsen-Anhalt (LVermGeo)",
                            "https://www.geodatenportal.sachsen-anhalt.de/wss/service/ST_LVermGeo_DOP_WMS_OpenData/guest",
                            "lsa_lvermgeo_dop20_2", "saxony_anhalt/ortho/live",
                            f"{LVERMGEO_ATTRIBUTION}, dl-de/by-2-0", attribution_url=DL_DE_BY[1])


def _lvermgeo(kind: str, description: str, zero_is_nodata: bool) -> WcsTiles:
    """DGM1 or DOM1 of LVermGeo from its open-data WCS (ArcGIS, coverage Coverage1 over the Land's
    extent): GeoTIFF float32 without a CRS tag in a multipart answer, pixel edges on whole metres;
    2 km tiles at the native 1 m (16 MB uncompressed, about 5 s; 3 km is refused with HTTP 400).
    Inside the extent but outside the Land the DGM answers 0 without nodata, the DOM -9999."""
    return WcsTiles(description, LVERMGEO_WCS.format(kind.upper()), "Coverage1", "EPSG:25832",
                    f"saxony_anhalt/{kind}1/live", native_res=1.0, fetch_res=1.0, tile_px=2000,
                    zero_is_nodata=zero_is_nodata)


# LGLN's AGNB, no. 7.2: open data are credited "© GeoBasis-DE/LGLN <year of the download>", with
# "Daten geändert" when the data were changed (a mosaic on our grid is); the year a run's tiles were
# downloaded is not kept, so the year of the run (YEAR) stands for it (the user's decision, 2026-11-01)
LGLN_CREDIT = Credit("DGM1 / DOM1 (LGLN, Lower Saxony)", f"© GeoBasis-DE/LGLN {YEAR}, Daten geändert", *CC_BY)
# The items of LGLN's collections: dgm1_32_<E>_<N>_1_ni_<year> (E and N in km of EPSG:25832, the
# survey's year), one GeoTIFF asset each without a gsd or checksum. LGLN replaced files in place in March
# 2026 (the same item, new content, no checksum to notice it), so the folders are "live": a tile is
# fetched again after cache.TTL_DAYS["live"]
LGLN_ITEM = r"^d[go]m1_32_(?P<east>\d+)_(?P<north>\d+)_1_ni_(?P<year>\d{4})$"
# DOP20 of LGLN, a WMS in EPSG:4326; CC BY 4.0, credited "LGLN (<year of the download>)" (its
# AccessConstraints); no request limits published
LGLN_DOP = OrthoService("DOP20 Niedersachsen (LGLN)", "https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
                        "ni_dop20", "lower_saxony/ortho/live", f"LGLN ({YEAR}), CC BY 4.0", attribution_url=CC_BY[1])


def _lgln(kind: str, description: str) -> StacTiles:
    """DGM1 or DOM1 of LGLN: 1 km COG tiles of 1 m (float32, LZW, about 5 MB) from its own STAC API."""
    return StacTiles(description, f"https://{kind}.stac.lgln.niedersachsen.de", f"{kind}1",
                     f"lower_saxony/{kind}1/live", "EPSG:25832", sizes={1.0: 5e6}, asset=f"{kind}1-tif",
                     item=LGLN_ITEM)


# HVBG's open data (since 2022-02-01, the WCS's Fees: Datenlizenz Deutschland - Zero - 2.0; § 18 HVGG):
# any use without condition, no attribution asked; a credit given must point out changes ("Daten
# geändert": a mosaic on our grid is one)
HVBG_CREDIT = Credit("DGM1 / DOM1 (HVBG, Hesse)", "HVBG, Daten geändert", "dl-de/zero-2.0",
                     "https://www.govdata.de/dl-de/zero-2-0")
# HVBG's free DOP WMS (EPSG:4326 offered; § 24 HVGG: automated retrieval free of charge, any use
# allowed); he_dop_rgb, the DOP at every scale (he_dop20_rgb alone is white below about zoom 14)
HVBG_DOP = OrthoService("DOP Hessen (HVBG)", "https://www.gds-srv.hessen.de/cgi-bin/lika-services/ogc-free-images.ows",
                        "he_dop_rgb", "hesse/ortho/live", "HVBG")


def _hvbg(kind: str, coverage: str, description: str, zero_is_nodata: bool) -> WcsTiles:
    """DGM1 or DOM1 of HVBG from its INSPIRE WCS (rasdaman, axes E/N, extent 411000-587000 /
    5471000-5724000): uncompressed GeoTIFF float32 with EPSG:25832, pixel edges on whole metres;
    2 km tiles at the native 1 m (16 MB, about 1 s; 5 km answered too). A request reaching beyond
    the extent is answered 404 (WcsReader clips it to the extent); inside the extent but outside
    the Land the DGM answers its nodata -9999, the DOM 0 without nodata."""
    return WcsTiles(description, f"https://inspire-hessen.de/raster/{kind}1/ows", coverage, "EPSG:25832",
                    f"hesse/{kind}1/live", native_res=1.0, fetch_res=1.0, tile_px=2000, axes=("E", "N"),
                    zero_is_nodata=zero_is_nodata)


# LAiV M-V's open data (CC BY 4.0; the WCS's AccessConstraints): a clearly visible "© GeoBasis-DE/M-V
# <year of the last delivery>"; the year of the run (YEAR) stands for it, as for LGLN. CC BY asks to say
# that the data were changed (a mosaic on our grid is): "Daten geändert" in the credit of the models
LAIV_ATTRIBUTION = f"© GeoBasis-DE/M-V {YEAR}"
LAIV_CREDIT = Credit("DGM1 / DOM1 (LAiV, Mecklenburg-Vorpommern)", f"{LAIV_ATTRIBUTION}, Daten geändert", *CC_BY)
# LAiV's DOP WMS (EPSG:4326, CC BY 4.0, the same notice); its images carry "© GeoBasis-DE/M-V" in
# their top left corner (in every tile), and nothing above 1:400000
LAIV_DOP = OrthoService("DOP Mecklenburg-Vorpommern (LAiV)", "https://www.geodaten-mv.de/dienste/adv_dop", "mv_dop",
                        "mecklenburg_vorpommern/ortho/live", f"{LAIV_ATTRIBUTION}, CC BY 4.0", attribution_url=CC_BY[1])


def _laiv(url: str, coverage: str, kind: str, description: str) -> WcsTiles:
    """DGM1 or DOM1 of LAiV from its WCS (MapServer, extent 200000-465000 / 5886000-6075000 in
    EPSG:25833): uncompressed GeoTIFF float32 with the CRS, pixel edges on whole metres; 2 km tiles
    at the native 1 m (16 MB, about 1.5 s; 5 km answered too). Sea, other water and the extent
    outside the Land are 0 without nodata (zero_is_nodata; land at exactly 0.000 m is a few
    hundred scattered pixels per 2 km tile on the lowest coasts, filled like gaps). A request
    partly beyond the extent is answered clipped, one wholly beyond it HTTP 400."""
    return WcsTiles(description, url, coverage, "EPSG:25833", f"mecklenburg_vorpommern/{kind}1/live",
                    native_res=1.0, fetch_res=1.0, tile_px=2000, zero_is_nodata=True)



# GeoSN's Allgemeine Nutzungsbedingungen (https://www.landesvermessung.sachsen.de/allgemeine-
# nutzungsbedingungen-8954.html, read 2026-11-02): dl-de/by-2.0 "unter Angabe des Quellenvermerks
# "Landesamt für Geobasisinformation Sachsen (GeoSN)" oder kurz "GeoSN"", for electronic media "Quelle:
# GeoSN, dl-de/by-2-0"; dl-de/by-2.0 §3 asks for a note of changes ("Daten geändert": a mosaic on our grid)
GEOSN_CREDIT = Credit("DGM1 / DOM1 (GeoSN, Saxony)", "Quelle: GeoSN, Daten geändert", *DL_DE_BY)
# The DGM1 and DOM1 of GeoSN's download service: one ZIP per 2 km tile on its Nextcloud (the public shares
# below, which GeoSN's own batch page and Produktdownload app build their links from; unchanged since the
# survey of 2026-10-31: the probe finds a change), <kind>1_33<E>_<N>_2_sn_tiff.zip with E and N the km of
# the south-west corner in EPSG:25833 (even). One GeoTIFF inside (2000 x 2000 px, float32, LZW, edges on
# whole metres, -9999 outside the Land; about 16 MB a ZIP) with its .tfw, .aux.xml and a CSV of the
# survey's date (2018-2025: tiles are re-surveyed, and the ZIPs were uploaded again on 2026-09-30, so the
# folders are "live"). A tile outside the Land answers 404 (a Sabre DAV error). No WCS for elevation, no
# request limits published.
GEOSN_DAV = "https://geocloud.landesvermessung.sachsen.de/public.php/dav/files"
GEOSN_SHARES = {"dgm": "JCcXyifaNdLDnxZ", "dom": "S6wwnFwX7882sZm"}
# GeoSN's DOP20 WMS (EPSG:4326 offered, "kostenfrei", the ANB's dl-de/by-2.0)
GEOSN_DOP = OrthoService("DOP20 Sachsen (GeoSN)", "https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest", "sn_dop_020",
                         "saxony/ortho/live", "Quelle: GeoSN, dl-de/by-2-0", attribution_url=DL_DE_BY[1])


def _geosn(kind: str, description: str) -> ZippedTiles:
    """DGM1 or DOM1 of GeoSN: zipped 2 km GeoTIFFs of 1 m named by their south-west corner."""
    def url(left: float, bottom: float) -> str:
        return f"{GEOSN_DAV}/{GEOSN_SHARES[kind]}/{kind}1_33{left / 1000:.0f}_{bottom / 1000:.0f}_2_sn_tiff.zip"
    return ZippedTiles(description, f"saxony/{kind}1/live", "EPSG:25833", 2000, 1.0, url,
                       rf"^{kind}1_33\d+_\d+_2_sn\.tif$", bytes_per_tile=16e6)


# LGL's Open GeoData (https://www.lgl-bw.de/Produkte/Open-Data/, "Rechtliches", and the portal's
# disclaimer, read 2026-11-02): dl-de/by-2.0, "Die Namensnennung hat in folgender Weise zu erfolgen:
# „Datenquelle: LGL, www.lgl-bw.de, dl-de/by-2-0“". The capabilities of LGL's WCS and WMS ask for "LGL-BW
# (<year>) ..." instead: the models come from the Open GeoData downloads, so their wording; the
# orthophoto from the WMS, so its. "Daten geändert" for dl-de/by-2.0 §3 (a mosaic on our grid)
LGL_CREDIT = Credit("DGM1 / DOM1 (LGL, Baden-Württemberg)", "Datenquelle: LGL, www.lgl-bw.de, Daten geändert",
                    *DL_DE_BY)
# The DGM1 and DOM1 of LGL's Open GeoData portal: one ZIP per 2 km tile, <kind>1_32_<E>_<N>_2_bw.zip with E
# (odd) and N (even) the km of the south-west corner in EPSG:25832, so the tiling starts at 1000 m east. In a
# DGM1 ZIP four 1 km XYZ grids (dgm1_32_<e>_<n>_1_bw_<year>.xyz: "x y z" with spaces, centimetres, pixel
# centres on x.5, i.e. edges on whole metres; 29 MB of text each) with a CSV of dates, the licence and a
# metadata text; in a DOM1 ZIP four 1 km GeoTIFFs (float32, LZW, -9999, a compound CRS of 25832 and
# DHHN2016). About 14.5 and 12 MB a ZIP. Tiles at the border hold data beyond it (Basel), kept as they
# come. The survey years differ per member (re-surveys: the folders are "live"). A tile outside the
# Land answers 404. LGL's DGM1 WCS answers whole metres on 1.002 m pixels: not used. No request limits
# published.
LGL_DATA = "https://opengeodata.lgl-bw.de/data"
# LGL's DOP20 WMS (EPSG:4326 offered); its capabilities ask for "LGL-BW (<year>)" with dl-de/by-2.0
LGL_DOP = OrthoService("DOP20 Baden-Württemberg (LGL)",
                       "https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LGL-BW_ATKIS_DOP_20_C", "IMAGES_DOP_20_RGB",
                       "baden_wurttemberg/ortho/live", f"LGL-BW ({YEAR}), dl-de/by-2-0", attribution_url=DL_DE_BY[1])


def _lgl(kind: str, folder: str, member: str, description: str, bytes_per_tile: float) -> ZippedTiles:
    """DGM1 or DOM1 of LGL: zipped 2 km tiles of four 1 km members (member: their extension)."""
    def url(left: float, bottom: float) -> str:
        return f"{LGL_DATA}/{folder}/{kind}1_32_{left / 1000:.0f}_{bottom / 1000:.0f}_2_bw.zip"
    return ZippedTiles(description, f"baden_wurttemberg/{kind}1/live", "EPSG:25832", 2000, 1.0, url,
                       rf"^{kind}1_32_\d+_\d+_1_bw_\d{{4}}\.{member}$", origin=(1000.0, 0.0),
                       bytes_per_tile=bytes_per_tile)


# LDBV's Nutzungsbedingungen (https://www.geodaten.bayern.de/odd/m/3/html/nutzungsbedingungen.html, read
# 2026-11-02): open data under CC BY 4.0, "Die Namensnennung der Bayerischen Vermessungsverwaltung als
# Rechteinhaberin hat in folgender Weise zu erfolgen: "Bayerische Vermessungsverwaltung – www.geodaten.bayern.de""; no
# request or agreement needed. CC BY asks to say what was changed: "Daten geändert" (a mosaic on our grid, the
# DOM20 averaged to 1 m)
BY_ATTRIBUTION = "Bayerische Vermessungsverwaltung – www.geodaten.bayern.de"
BY_CREDIT = Credit("DGM1 / DOM20 (LDBV, Bavaria)", f"{BY_ATTRIBUTION}, Daten geändert", *CC_BY)
# The DGM1 of LDBV's open-data downloads: 1 km GeoTIFFs of 1 m (float32, LZW, strips of 2 rows, not COG, -9999,
# EPSG:25832, edges on whole metres; about 3 MB) at download1.bayernwolke.de/a/dgm/dgm1/<Ekm>_<Nkm>.tif (the same
# on download2), listed with their size and SHA-256 by a Metalink of the Land (09.meta4: 22 MB, 4.2 MB gzipped,
# 71 979 tiles). No dates and no year in the names: files are replaced in place, so the SHA-256 is the version
BY_DGM1 = "https://geodaten.bayern.de/odd/a/dgm/dgm1/meta/metalink/09.meta4"
# The DOM20 (0.2 m, photogrammetric: image matching of the aerial photographs, LDBV states 0.4-0.6 m; 1 km files
# of 5000 x 5000 px, about 49 MB, LZW, 256 px tiles without overviews, not COG; flights every 2-3 years replace
# them in place), listed per Regierungsbezirk (091-097: 0.5-1.1 MB gzipped each, no statewide Metalink; they
# overlap at their borders). There is no open DOM1 (laser points only as LAZ)
BY_DOM20 = [f"https://geodaten.bayern.de/odd/a/dom20/meta/DOM/metalink/09{n}.meta4" for n in range(1, 8)]
# LDBV's DOP20 WMS (EPSG:4326 offered; Fees "kostenfrei", AccessConstraints "CC BY 4.0"), no key
BY_DOP = OrthoService("DOP20 Bayern (LDBV)", "https://geoservices.bayern.de/od/wms/dop/v1/dop20", "by_dop20c",
                      "bavaria/ortho/live", f"{BY_ATTRIBUTION}, CC BY 4.0", attribution_url=CC_BY[1])

# LVermGeo RP's open data (https://lvermgeo.rlp.de/geodaten-geoshop/open-data, read 2026-11-02): dl-de/by-2.0,
# credited "©GeoBasis-DE / LVermGeoRP<Jahr des Datenbezugs>, dl-de/by-2-0, www.lvermgeo.rlp.de [Daten
# bearbeitet]"; the year of the run (YEAR) stands for the year of the download, as for LGLN
RP_ATTRIBUTION = f"©GeoBasis-DE / LVermGeoRP {YEAR}, dl-de/by-2-0, www.lvermgeo.rlp.de"
RP_CREDIT = Credit("DGM1 / DOM1 (LVermGeo, Rhineland-Palatinate)", f"{RP_ATTRIBUTION} [Daten bearbeitet]",
                   *DL_DE_BY)
# The DGM1 and DOM1 of the GeoShop's open-data downloads: 1 km GeoTIFFs of 1 m (ALS; float32, LZW, strips, -9999,
# edges on whole metres, 1.5-3 MB) <kind>1_32_<Ekm>_<Nkm>_1_rp_<year>.tif, the survey year in the name (2022-2025:
# a quarter of the Land a year, the older file then gone), listed with size and SHA-256 by a Metalink of the Land
# (dgm1_tif_07.meta4: 12 MB, 21 160 tiles and their .tfw; dom1_tif_07.meta4: 7.6 MB). The DGM1's files name a
# compound CRS (ETRS89 / UTM 32N + DHHN2016 height): written in EPSG:25832's name. No WCS, no limits published
RP_META = "https://geobasis-rlp.de/data/{kind}1/current/meta4/{kind}1_tif_07.meta4"
# LVermGeo RP's DOP20 WMS (EPSG:4326 offered, dl-de/by-2.0 with the same notice), no key
RP_DOP = OrthoService("DOP20 Rheinland-Pfalz (LVermGeo)", "https://geo4.service24.rlp.de/wms/rp_dop20.fcgi", "rp_dop20",
                      "rhineland_palatinate/ortho/live", RP_ATTRIBUTION, attribution_url=DL_DE_BY[1])


def _rp(kind: str, description: str) -> MetalinkTiles:
    """DGM1 or DOM1 of LVermGeo RP: 1 km GeoTIFFs listed by the Land's Metalink, the newest survey per tile."""
    return MetalinkTiles(description, [RP_META.format(kind=kind)],
                         rf"^{kind}1_32_(?P<east>\d+)_(?P<north>\d+)_1_rp_(?P<year>\d{{4}})\.tif$",
                         f"rhineland_palatinate/{kind}1", "EPSG:25832", f"{kind}1", bytes_per_tile=2.5e6,
                         force_crs="EPSG:25832")


# Geobasis NRW's open data (Bezirksregierung Köln, Lizenzbedingungen Geobasis NRW, Stand 3/2020, and the WCS's
# Fees): dl-de/zero-2.0, "Jede Nutzung ist ohne Einschränkungen oder Bedingungen zulässig": no attribution asked; a
# credit given points out changes (as Hesse's)
NW_CREDIT = Credit("DGM1 / DOM1 (Geobasis NRW, North Rhine-Westphalia)", "Geobasis NRW, Daten geändert",
                   "dl-de/zero-2.0", "https://www.govdata.de/dl-de/zero-2-0")
# Geobasis NRW's DOP WMS (EPSG:4326 offered, AccessConstraints none, dl-de/zero-2.0, at most 5000 px)
NW_DOP = OrthoService("DOP Nordrhein-Westfalen (Geobasis NRW)", "https://www.wms.nrw.de/geobasis/wms_nw_dop",
                      "nw_dop_rgb", "north_rhine_westphalia/ortho/live", "Geobasis NRW")


def _nw(kind: str, description: str, zero_is_nodata: bool, params=()) -> WcsTiles:
    """DGM1 or DOM1 of Geobasis NRW from its WCS 2.0.1 (MapServer behind an "OGC Proxy", axes x/y, extent
    278000-536000 / 5560000-5828000, pixel edges on whole metres): 2 km tiles at the native 1 m (3 km and more are
    refused with HTTP 400), equal bit for bit to the 1 km files of the downloads (checked twice, 2026-11-02). The
    DGM answers LZW-compressed GeoTIFFs with -9999 outside the Land, the DOM uncompressed ones (DEFLATE asked)
    with 0 outside it, without nodata. The tiles are re-surveyed in turn (file years 2020-2025): "live"."""
    return WcsTiles(description, f"https://www.wcs.nrw.de/geobasis/wcs_nw_{kind}", f"nw_{kind}", "EPSG:25832",
                    f"north_rhine_westphalia/{kind}1/live", native_res=1.0, fetch_res=1.0, tile_px=2000,
                    zero_is_nodata=zero_is_nodata, params=params)


# LGB's open data (the WCS's AccessConstraints, also of its DOP WMS and in each file's metadata, read 2026-11-02):
# dl-de/by-2.0, "Namensnennung: "GeoBasis-DE/LGB" ... Hinweis: werden auch Daten des Bundeslandes Berlin genutzt, ist
# der Copyright-Vermerk um den Hinweis "© Geoportal Berlin, dl-de/by-2-0" zu ergänzen. Beispiel: „© GeoBasis-DE/LGB,
# dl-de/by-2-0; © Geoportal Berlin, dl-de/by-2-0 (Daten geändert)"": that example, word for word (one source for
# both Länder, so always with Berlin; "Daten geändert": a mosaic on our grid)
BB_ATTRIBUTION = "© GeoBasis-DE/LGB, dl-de/by-2-0; © Geoportal Berlin, dl-de/by-2-0"
BB_CREDIT = Credit("DGM1 / DOM1 (LGB, Brandenburg and Berlin)", f"{BB_ATTRIBUTION} (Daten geändert)", *DL_DE_BY)
# LGB's INSPIRE WCS 2.0.1 of the DGM1 and DOM1 (MapServer, coverage el_elevationgridcoverage, axes x/y, EPSG:25833,
# extent 248000-466000 / 5690000-5936000 given with 0.01 mm of noise: WcsReader rounds it), Brandenburg and Berlin
BB_WCS = "https://inspire.brandenburg.de/services/el_{kind}1_wcs"
# LGB's DOP20 of Berlin and Brandenburg, a MapProxy WMS in EPSG:4326 (dl-de/by-2.0, the same notice), no key
BB_DOP = OrthoService("DOP20 Berlin/Brandenburg (LGB)", "https://isk.geobasis-bb.de/mapproxy/dop20c/service/wms",
                      "bebb_dop20c", "brandenburg/ortho/live", BB_ATTRIBUTION, attribution_url=DL_DE_BY[1])


def _bb(kind: str, description: str, zero_is_nodata: bool) -> WcsTiles:
    """DGM1 or DOM1 of LGB from its INSPIRE WCS: GeoTIFF float32 with EPSG:25833, pixel edges on whole metres, equal
    bit for bit to LGB's 1 km files (Berlin's too); 2 km tiles at the native 1 m with DEFLATE (8 MB, 1.5 s; 4 km
    answered too). Inside the extent but outside the Länder the DGM answers 0 without nodata, the DOM -9999 without a
    nodata tag; a request beyond the extent is answered HTTP 400 (outside: missing once the extent is known).
    Files are republished every few months: "live"."""
    return WcsTiles(description, BB_WCS.format(kind=kind), "el_elevationgridcoverage", "EPSG:25833",
                    f"brandenburg/{kind}1/live", native_res=1.0, fetch_res=1.0, tile_px=2000,
                    zero_is_nodata=zero_is_nodata, params=(("GEOTIFF:COMPRESSION", "DEFLATE"),))


# LVermGeo SH's licence of its open data (https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/
# lizenz.html, Stand 01.08.2022, read 2026-11-02): CC BY 4.0, "(4) Veränderungen ... sind im Quellenvermerk mit Hinweis
# zu versehen, dass die Daten geändert wurden", the notice "©GeoBasis-DE/LVermGeo SH/CC BY 4.0" with "(Quelle
# verändert)": word for word (a mosaic on our grid is a change)
SH_ATTRIBUTION = "©GeoBasis-DE/LVermGeo SH/CC BY 4.0"
SH_CREDIT = Credit("DGM1 (LVermGeo SH, Schleswig-Holstein)", f"{SH_ATTRIBUTION} (Quelle verändert)", *CC_BY)
# The whole Land's index of the DGM1 (9 MB, 18 685 features of 1 km in EPSG:25832, 2026-11-02): each feature's
# link_data a massen.php link naming the file dgm1_32_<Ekm>_<Nkm>_1_sh_<year>.xyz, the survey's year (2005-2025) in it;
# an outdated link (another year) answers HTTP 200 with an HTML page "Die verwendete Massendownload-Datei ist
# veraltet". The files are plain "x y z" text of the cell centres (on x.5: edges on whole metres), centimetres,
# 1000 x 1000 points, 27 MB, no Range, no compression. The server's TLS chain lacks its intermediate (net.HOST_CA_OF).
# The 0.2 m bDOM is published as uncompressed GeoTIFFs of about 105 MB per km² without Range: no surface model
# The sea has no gaps: the North Sea of the newer surveys is a constant 1.30 m written by the provider, not a measured
# surface (one value, flat to the centimetre: Helgoland and Büsum 2025 100 % of a tile at sea, Sylt 2024; reason
# unpublished, 2026-11-03), so it counts as water (sea_fill) and keeps its height; the Baltic and the surveys of
# 2005-2007 give the sea about 0 m (-0.4 to +0.6 m), which counts as water by filling.SEA_LEVEL_TOLERANCE
SH_SEA_FILL = 1.30
SH_INDEX = ("https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/single.php"
            "?file=DGM1_SH__Massendownload.geojson&id=4")
SH_NAME = r"^dgm1_32_(?P<east>\d+)_(?P<north>\d+)_1_sh_(?P<year>\d{4})\.xyz$"
# LVermGeo SH's DOP20 WMS of the GDI-SH (EPSG:4326 offered; its Fees "© GeoBasis-DE/LVermGeo SH/CC BY 4.0"), no key
SH_DOP = OrthoService("DOP20 Schleswig-Holstein (LVermGeo SH)", "https://service.gdi-sh.de/WMS_SH_DOP20col_OpenGBD",
                      "sh_dop20_rgb", "schleswig_holstein/ortho/live", SH_ATTRIBUTION, attribution_url=CC_BY[1])


# LVGL's open data (the shop's page "Offene Geobasisdaten", https://www.shop.lvgl.saarland.de/index.php?option=
# com_content&view=article&id=18, read 2026-11-03): dl-de/by-2.0, "Vorgabe des Lizenzgebers zum Quellenvermerk:
# „© GeoBasis DE/LVGL-SL (Jahr der Bereitstellung)“" (the ISO metadata of the DGM1, DOM1 and DOP: "© GeoBasis
# DE/LVGL-SL (Jahr)"); the year of the run (YEAR) stands for the year of the download, as for LGLN and LVermGeo RP;
# "Daten geändert" for dl-de/by-2.0 §3 (a mosaic on our grid, the 0 m patches taken out)
SL_ATTRIBUTION = f"© GeoBasis DE/LVGL-SL {YEAR}"
SL_CREDIT = Credit("DGM1 / DOM1 (LVGL, Saarland)", f"{SL_ATTRIBUTION}, dl-de/by-2-0, Daten geändert", *DL_DE_BY)
# The DGM1 and DOM1 of 2025 (lidar, "Laserscanbefliegung 2025"): 1 km GeoTIFFs of 1 m (float32 in centimetres,
# uncompressed, strips of 2 rows, -9999, EPSG:25832, DHHN2016, edges on whole metres) d[go]m1_32_<Ekm>_<Nkm>_1_SL_2025
# .tif in one ZIP per Landkreis and model (deflated members of 0.8-2.8 MB; ZIPs of 0.56-1.17 GB, 5.5 and 6.2 GB in all)
# on LVGL's Nextcloud share "Opendata". The share's token was reissued once (Mapterhorn's wWELJP3D5aRsrqi of 2025 is
# gone): it comes from the stable link the shop's page gives, which redirects to .../index.php/s/<token> (to http:
# the redirect is not followed, the archives are read over https), resolved again with every reading of the
# directories. The twelve archives are named here (WebDAV listing is not used): a new survey brings new names, set by
# hand (the probe sees a missing archive). 294 tiles lie in two districts' ZIPs (identical): the first named wins.
# No WCS (the INSPIRE WMS's TIFF is an RGB picture), no limits published (net.HOST_SLOTS_OF)
SL_SHARE = "https://www.shop.lvgl.saarland.de/cloud/freiegeobasisdaten"
SL_DAV = "https://www.shop.lvgl.saarland.de/cloud/public.php/dav/files/{token}"
SL_DISTRICTS = ("MZG", "NK", "SB", "SLS", "SPK", "WND")  # Merzig-Wadern, Neunkirchen, Regionalverband Saarbrücken,
                                                        # Saarlouis, Saarpfalz-Kreis, St. Wendel
SL_RELEASE = "2025"
# Pixels below SL_FLOOR metres, and those within SL_RING pixels of one, are no data (the user's decisions of
# 2026-11-03): the survey holds patches at 0 m that would make a pit with walls of 100 m and more, their rims
# falling from the ground to the patch: tile 327_5485 near Mettlach (DGM1 109 px, DOM1 91 px at 0.00 m, a rim of
# one pixel from ground at about 205 m) and 343_5457 in Saarbrücken (DGM1 135 px down to -0.26 m, a ramp of five
# pixels from ground at 184 m: 101-166 m at 1-5 px, the ground from 6 px), so 6 px: the ramp and a pixel more. No
# ground of the Land lies below about 137 m (the Moselle at Perl 140.5 m). The source's gap filler fills them
SL_FLOOR = 100.0
SL_RING = 6
# LVGL's DOP WMS (MapServer, layer sl_dop: the newest DOP, 2025, DOP20; EPSG:4326 offered; Fees none,
# AccessConstraints noLimitations; white beyond the Land), dl-de/by-2.0 with the same notice
SL_DOP = OrthoService("DOP20 Saarland (LVGL)", "https://geoportal.saarland.de/freewms/dop", "sl_dop",
                      "saarland/ortho/live", f"{SL_ATTRIBUTION}, dl-de/by-2-0", attribution_url=DL_DE_BY[1])


def _sl(kind: str, description: str, bytes_per_tile: float) -> ZipMemberTiles:
    """DGM1 or DOM1 of LVGL: members of the six district ZIPs of the release, read by HTTP Range."""
    upper = kind.upper()
    archives = [f"{SL_DAV}/OD_{upper}1_{SL_RELEASE}_tif_LK/{upper}1_tif_{district}_EPSG-25832_Entstehung-{SL_RELEASE}.zip"
                for district in SL_DISTRICTS]
    return ZipMemberTiles(description, archives,
                          rf"(?i)(?:^|/){kind}1_32_(?P<east>\d+)_(?P<north>\d+)_1_sl_(?P<year>\d{{4}})\.tif$",
                          f"saarland/{kind}1-{SL_RELEASE}", "EPSG:25832", f"{kind}1", share=SL_SHARE,
                          bytes_per_tile=bytes_per_tile, floor=SL_FLOOR, ring=SL_RING)


# LGV Hamburg's open data (the Transparenzportal's records gelaendemodelle-hamburg-dgm2 and
# digitales-hoehenmodell-hamburg-bdom8, read 2026-11-15): dl-de/by-2.0, "attribution_text": "Freie und Hansestadt
# Hamburg, Landesbetrieb Geoinformation und Vermessung (LGV)"; "Daten geändert" for dl-de/by-2.0 §3 (a mosaic on
# our grid), as for LVGL Saarland
HH_ATTRIBUTION = "Freie und Hansestadt Hamburg, Landesbetrieb Geoinformation und Vermessung (LGV)"
HH_CREDIT = Credit("DGM1 / bDOM1 (LGV, Hamburg)", f"{HH_ATTRIBUTION}, dl-de/by-2-0, Daten geändert", *DL_DE_BY)
# The DGM1 (laser scanning) and the bDOM1 (image matching of the aerial photographs) of 2022: 1 km GeoTIFFs of 1 m
# (float32, centimetres, LZW, EPSG:25832, DHHN2016, edges on whole metres) d[go]m1_32_<Ekm>_<Nkm>_1_hh_2022.tif, the
# city (E 548-588, N 5916-5955) and Neuwerk (E 466-468, N 5973-5976), in one ZIP each (deflated members of 0.01-3.7
# MB; 1.36 and 1.34 GB) on the open-data server, read by Range (no WCS of the heights; the INSPIRE services are
# pictures). The DGM1's members say their origin with float noise (552999.9999999999, 5935000.000000001), so their
# transforms are rounded to whole metres (HH_FIX); the bDOM1's are exact. Both declare nodata -3.4e38 (the DGM1) or
# none (the bDOM1) and write -9999 beyond the city: below layer.VALID_MIN, no data either way. The Elbe and the
# harbour basins are a constant 2.00 m in the DGM1 (measured water level, not a fill of ours). New releases come
# under new names (the date in each archive's name): set by hand. No limits published (net.HOST_SLOTS_OF)
HH_DGM1 = "https://www.daten-hamburg.de/opendata/fernerkundung_hoehenmodelle/dgm/dgm1_hh_2022-04-30.zip"
HH_BDOM1 = "https://www.daten-hamburg.de/opendata/Digitales_Hoehenmodell_bDOM/dom1_hh_2022-11-21.zip"
HH_FIX = TransformFix(snap=1.0)


def _hh(kind: str, archive: str, description: str, bytes_per_tile: float) -> ZipMemberTiles:
    """DGM1 or bDOM1 of LGV Hamburg: members of its archive, read by HTTP Range."""
    folder = {"dgm": "dgm1", "dom": "bdom1"}[kind]
    return ZipMemberTiles(description, [archive],
                          rf"(?i)(?:^|/){kind}1_32_(?P<east>\d+)_(?P<north>\d+)_1_hh_(?P<year>\d{{4}})\.tif$",
                          f"hamburg/{folder}-2022", "EPSG:25832", folder, bytes_per_tile=bytes_per_tile, fix=HH_FIX)


# Landesamt GeoInformation Bremen's open data (MetaVer's record "ATKIS - DGM1 Land Bremen - Downloaddienst",
# https://metaver.de/trefferanzeige?docuuid=C448202A-0F15-413A-99E6-F22F10E190C9, read 2026-11-15: "Nutzungsbedingungen
# Creative Commons Namensnennung 4.0 International Quellenvermerk: Landesamt GeoInformation Bremen", "Es gelten keine
# Zugriffsbeschränkungen"; the DOM1 has no record of its own: the open-data decree of 22.05.2024,
# https://geo.bremen.de/sixcms/media.php/13/2024-05-22_Verf%C3%BCgung_BetroffeneGeobasisdaten_DVO_hvD.pdf, names "Digitale
# Geländemodelle (DGM1 und DGM5)" and "Digitale Oberflächenmodelle (DOM1, DOM5)" among the open geobasis data, under CC BY
# 4.0 instead of the AGNB); "Daten geändert" for CC BY (a mosaic on our grid), as for LGLN
HB_ATTRIBUTION = "Landesamt GeoInformation Bremen"
HB_CREDIT = Credit("DGM1 / DOM1 (Landesamt GeoInformation Bremen)", f"{HB_ATTRIBUTION}, Daten geändert", *CC_BY)
# The DGM1 and DOM1 of the Land's two cities from laser scanning (the record: Bremerhaven 2015, Bremen 2017; the height
# system not named), one ZIP per city and model on the INSPIRE download server (1.09 / 1.24 GB for Bremen, 0.61 / 0.32 GB
# for Bremerhaven), each member a 1 km tile of plain "x y z" text with a header line and CRLF (deflated, 2.7-4.1 MB; 21
# to 29 MB inflated), read by Range; GDAL's XYZ driver reads every layout below from memory. The archives' names hold
# the survey year: a new survey is set by hand (the probe sees a missing archive). The two cities lie on grids half a
# pixel apart (the user's decision of 2026-11-15: two sources, each on its own grid):
# - Bremen (dgm1_32<E>_<N>_1_hb.xyz, 395 tiles of E 465-499, N 5873-5897 in both): whole-metre coordinates without
#   the zone, rows north to south, centimetres; the values are samples at those points (against LGLN's DGM1 and DOM1 of
#   2017 at 483_5876, 2026-11-15: RMS 0.079 m at no shift, 0.150 at half a pixel; NCC 0.982 / 0.888 at no shift),
#   so pixel centres lie on whole metres (grid_origin 0.5) in both models; the tiles hold Lower Saxony's land in them
# - Bremerhaven: eastings with the zone (32466000.5: TransformFix's offset). The DGM1 (dgm1_32<E>__<N>_1_hb.xyz, a
#   double underscore; 188 tiles, E 466-477, N 5924-5940, Lower Saxony's land around the city in them) at x.5, columns
#   north to south, millimetres: its values are samples at those points (against LGLN's DGM1 of 2020-2025 on five
#   tiles: at 474_5936 RMS 0.150 m at no shift, 0.19-0.24 at half a pixel), so its edges lie on whole metres (grid_origin
#   0). The DOM1 (dom1_32<E>_<N>_1_hb.xyz, one underscore; 114 tiles of the city only, 41 with fewer points than a
#   full km: the 12 read so far each a rectangle of part of it; a full one 1001 x 1000 points) at whole metres, columns
#   south to north: its values sit at those points (against LGLN's DOM1 of 2025, the NCC of the high-passed rasters at
#   no shift and the best at half a pixel on both axes: 474_5936 0.400 / 0.371, 472_5938 0.282 / 0.265, 471_5938
#   0.165 / 0.159; two small partial tiles of NCC 0.12-0.17 scatter, neither peak at half a pixel on both axes), half a
#   pixel off its own terrain: written as it lies and interpolated onto the terrain's grid by the mosaic (bilinear, as
#   any off-grid raster; a choice for the user). Outside the city each partial tile's rectangle is filled with
#   constant planes (475_5937: 3.19 m over 23 ha, 1.4 m below the terrain, and 17.35 m over 15 ha, 13 m above it),
#   left as they are
HB_DATA = "https://gdi2.geo.bremen.de/inspire/download/{kind}/data/Gitternetz_{kind}1_{year}_{city}_ASCII_XYZ.zip"
HB_NAME = r"(?i)(?:^|/){kind}1_32(?P<east>\d{{3}})_{{1,2}}(?P<north>\d{{4}})_1_hb\.xyz$"
BHV_ZONE = -32_000_000.0  # Bremerhaven's eastings less the zone 32's prefix
BHV_FIX = {"dgm": TransformFix(offset=(BHV_ZONE, 0.0), snap=1.0), "dom": TransformFix(offset=(BHV_ZONE, 0.0), snap=0.5)}
# The Land's DOP10 of 2025, a WMS (EPSG:4326 offered; Fees "Creative Commons Namensnennung (CC-BY), Quellenvermerk:
# Landesamt GeoInformation Bremen", AccessConstraints "Es gelten keine Zugriffsbeschränkungen"), one layer per city
HB_WMS = "https://geodienste.bremen.de/wms_dop_lb"


def _hb_dop(city: str) -> OrthoService:
    return OrthoService(f"DOP10 2025 {city} (Landesamt GeoInformation Bremen)", HB_WMS,
                        f"dop10_2025_{'HB' if city == 'Bremen' else 'BHV'}", f"{city.lower()}/ortho/2025",
                        f"{HB_ATTRIBUTION}, CC BY 4.0", attribution_url=CC_BY[1])


def _hb(kind: str, city: str, year: str, description: str, bytes_per_tile: float) -> ZipMemberTiles:
    """DGM1 or DOM1 of one of the Land's cities (city: HB or BHV): members of its archive, read by HTTP Range."""
    top = {"HB": "bremen", "BHV": "bremerhaven"}[city]
    return ZipMemberTiles(description, [HB_DATA.format(kind=kind.upper(), year=year, city=city)],
                          HB_NAME.format(kind=kind), f"{top}/{kind}1-{year}", "EPSG:25832", f"{kind}1",
                          bytes_per_tile=bytes_per_tile, fix=BHV_FIX[kind] if city == "BHV" else None)


SOURCES: List[Source] = [
    # Hesse and Mecklenburg-Vorpommern before Lower Saxony: their offline boxes overlap Lower
    # Saxony's (northern Hesse, western M-V with Schwerin), and the first box holding a point wins
    Source(
        id="hesse", name="HVBG (DGM1 / DOM1)",
        description="HVBG (Hesse, Germany): terrain and surface models 1 m from its WCS, ETRS89 / UTM 32N, "
                    "DHHN2016",
        nmt=_hvbg("dgm", "he_dgm1", "DGM1 (terrain)", False), nmpt=_hvbg("dom", "dom1", "DOM1 (trees, buildings)", True),
        countries=("de",), regions=("de-he",), crs="EPSG:25832", ortho=HVBG_DOP,
        neighbours=("lower_saxony", "baden_wurttemberg", "bavaria", "rhineland_palatinate", "north_rhine_westphalia"),
        credits=(HVBG_CREDIT,),
        listing=ReadmeRow("Hesse (DE)", "HVBG DGM1, 1 m (WCS)", "HVBG DOM1, 1 m (WCS)", "HVBG DOP"),
        offline=(("de-he", (49.39, 51.66, 7.77, 10.24)),), sample=(51.1830, 9.0500),
        note="Data HVBG, dl-de/zero-2.0 (changed: mosaicked onto the working grid). The WCS names no "
             "survey years.",
        coverage=Coverage(provider="HVBG", added="2026-11-01")),
    Source(
        id="mecklenburg_vorpommern", name="LAiV M-V (DGM1 / DOM1)",
        description="LAiV (Mecklenburg-Vorpommern, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 33N, DHHN2016",
        nmt=_laiv("https://www.geodaten-mv.de/dienste/inspire_el_dgm_wcs", "mv_dgm", "dgm", "DGM1 (terrain)"),
        nmpt=_laiv("https://www.geodaten-mv.de/dienste/dom_wcs", "mv_dom1", "dom", "DOM1 (trees, buildings)"),
        countries=("de",), regions=("de-mv",), crs="EPSG:25833", ortho=LAIV_DOP,
        neighbours=("lower_saxony", "geoportal", "brandenburg", "schleswig_holstein"),
        credits=(LAIV_CREDIT,),
        listing=ReadmeRow("Mecklenburg-Vorpommern (DE)", "LAiV DGM1, 1 m (WCS)", "LAiV DOM1, 1 m (WCS)",
                          "LAiV DOP"),
        offline=(("de-mv", (53.1, 54.7, 10.59, 14.42)),), sample=(54.5735, 13.6640),
        note=f"Data {LAIV_ATTRIBUTION}, CC BY 4.0. The sea is stored as 0 m, taken as no data. The WCS "
             f"names no survey years.",
        coverage=Coverage(provider="LAiV M-V", added="2026-11-01")),
    # Before Lower Saxony: their offline boxes overlap in the Harz (the first holding a point wins)
    Source(
        id="saxony_anhalt", name="LVermGeo (DGM1 / DOM1)",
        description="LVermGeo (Saxony-Anhalt, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 32N, DHHN2016",
        nmt=_lvermgeo("dgm", "DGM1 (terrain)", True), nmpt=_lvermgeo("dom", "DOM1 (trees, buildings)", False),
        countries=("de",), regions=("de-st",), crs="EPSG:25832", ortho=LVERMGEO_DOP,
        credits=(LVERMGEO_CREDIT,),
        neighbours=("lower_saxony", "saxony", "brandenburg"),
        listing=ReadmeRow("Saxony-Anhalt (DE)", "LVermGeo DGM1, 1 m (WCS)", "LVermGeo DOM1, 1 m (WCS)",
                          "LVermGeo DOP20"),
        offline=(("de-st", (50.94, 53.05, 10.56, 13.19)),), sample=(51.7340, 11.0200),
        note=f"Data {LVERMGEO_ATTRIBUTION}, dl-de/by-2.0. The WCS names no survey years.",
        coverage=Coverage(provider="LVermGeo ST", added="2026-11-01")),
    # Hamburg before Lower Saxony and Schleswig-Holstein: both their offline boxes hold the whole city (the first box
    # holding a point wins)
    Source(
        id="hamburg", name="LGV (DGM1 / bDOM1)",
        description="LGV (Hamburg, Germany): terrain model 1 m (laser scanning) and image-matching surface model 1 m "
                    "of 2022, members of two ZIP archives read by HTTP Range, ETRS89 / UTM 32N, DHHN2016",
        nmt=_hh("dgm", HH_DGM1, "DGM1 (terrain)", 1.5e6), nmpt=_hh("dom", HH_BDOM1, "bDOM1 (trees, buildings)", 3.0e6),
        countries=("de",), regions=("de-hh",), crs="EPSG:25832",
        credits=(HH_CREDIT,),
        # Lower Saxony declares six neighbours already (the most a source may: countcube.PARTNERS), so the two do not
        # name each other: Hamburg's gaps along that border are filled by FABDEM / Copernicus
        neighbours=("schleswig_holstein",),
        listing=ReadmeRow("Hamburg (DE)", "LGV DGM1, 1 m (2022)", "LGV bDOM1, 1 m (2022; image matching)"),
        # A staircase of boxes inside the city (lattice cells of 0.01 degrees at least 75 % inside its OSM outline, in
        # bands of 0.04 degrees: they hold 77 % of it and 0.2 % of other land), so Lower Saxony's and
        # Schleswig-Holstein's towns at its edges keep their own sources offline; then Neuwerk and Scharhörn. The
        # city's whole box is a border box (the neighbour fill along Schleswig-Holstein)
        offline=(("de-hh", (53.43, 53.47, 9.92, 10.02)), ("de-hh", (53.43, 53.47, 10.10, 10.27)),
                 ("de-hh", (53.47, 53.51, 9.80, 10.22)), ("de-hh", (53.51, 53.55, 9.78, 10.15)),
                 ("de-hh", (53.55, 53.59, 9.77, 9.81)), ("de-hh", (53.55, 53.59, 9.83, 10.15)),
                 ("de-hh", (53.59, 53.63, 9.89, 10.19)), ("de-hh", (53.63, 53.67, 9.99, 10.17)),
                 ("de-hh", (53.67, 53.71, 10.08, 10.14)), ("de-hh", (53.88, 53.98, 8.40, 8.56))),
        border_boxes=((53.39, 53.75, 9.72, 10.33),),
        sample=(53.5585, 9.8070),  # Blankenese, above the Elbe
        note=f"Data {HH_ATTRIBUTION}, dl-de/by-2.0 (changed: mosaicked onto the working grid). Surveys of 2022. The "
             f"surface model comes from image matching of aerial photographs, not from laser scanning: smoother over "
             f"trees and less exact. The terrain model gives the Elbe and the harbour basins a constant 2.00 m.",
        coverage=Coverage(provider="LGV", added="2026-11-15", survey="2022")),
    # Bremen and Bremerhaven before Lower Saxony, whose offline box holds both: offline, a staircase of boxes inside
    # each city (bands of 0.02 degrees of latitude, the runs of 0.01-degree columns at least 75 % inside the city's OSM
    # outline: Bremen's 14 hold 85 % of it and 1.9 % other land, Bremerhaven's 7 76 % and 3.4 %), so Delmenhorst,
    # Lilienthal, Stuhr or Nordenham keep Lower Saxony's source. Nominatim names both cities DE-HB: each is chosen by its
    # bbox, the city's own box (the Land's outline, relation 62559, south and north of 53.3 degrees; the city of Bremen's
    # overseas port lies in Bremerhaven's). Lower Saxony declares six neighbours already (countcube.PARTNERS), so neither
    # names it: their gaps beyond their tiles are filled by FABDEM / Copernicus
    Source(
        id="bremen", name="GeoInformation Bremen (DGM1 / DOM1, Bremen)",
        description="Landesamt GeoInformation Bremen (the city of Bremen, Germany): terrain and surface models 1 m of "
                    "2017 (laser scanning), XYZ members of two ZIP archives read by HTTP Range, ETRS89 / UTM 32N",
        nmt=_hb("dgm", "HB", "2017", "DGM1 (terrain)", 2.8e6), nmpt=_hb("dom", "HB", "2017", "DOM1 (trees, buildings)", 3.1e6),
        countries=("de",), regions=("de-hb",), bbox=(53.01, 53.23, 8.48, 9.00), crs="EPSG:25832", grid_origin=(0.5, 0.5),
        ortho=_hb_dop("Bremen"), credits=(HB_CREDIT,),
        listing=ReadmeRow("Bremen, the city (DE)", "GeoInformation Bremen DGM1, 1 m (2017)",
                          "GeoInformation Bremen DOM1, 1 m (2017)", "GeoInformation Bremen DOP10"),
        offline=(("de-hb", (53.02, 53.04, 8.82, 8.86)), ("de-hb", (53.02, 53.04, 8.88, 8.94)),
                 ("de-hb", (53.04, 53.06, 8.71, 8.76)), ("de-hb", (53.04, 53.06, 8.77, 8.97)),
                 ("de-hb", (53.06, 53.08, 8.71, 8.96)), ("de-hb", (53.08, 53.10, 8.69, 8.96)),
                 ("de-hb", (53.10, 53.12, 8.66, 8.95)), ("de-hb", (53.12, 53.14, 8.65, 8.86)),
                 ("de-hb", (53.12, 53.14, 8.90, 8.97)), ("de-hb", (53.14, 53.16, 8.63, 8.84)),
                 ("de-hb", (53.16, 53.18, 8.62, 8.73)), ("de-hb", (53.18, 53.20, 8.54, 8.58)),
                 ("de-hb", (53.18, 53.20, 8.62, 8.63)), ("de-hb", (53.20, 53.22, 8.50, 8.54))),
        sample=(53.0760, 8.8075),  # the Marktplatz
        note=f"Data {HB_ATTRIBUTION}, CC BY 4.0 (changed: mosaicked onto the working grid). Laser scanning of 2017.",
        # One area for the Land's two cities (ISO 3166-2 has none of its own for either): Bremerhaven's source has no
        # entry of its own
        coverage=Coverage(provider="GeoInformation Bremen", added="2026-11-15", areas=("de-hb",), survey="2015–2017")),
    Source(
        id="bremerhaven", name="GeoInformation Bremen (DGM1 / DOM1, Bremerhaven)",
        description="Landesamt GeoInformation Bremen (the city of Bremerhaven, Germany): terrain and surface models 1 m "
                    "of 2015 (laser scanning), XYZ members of two ZIP archives read by HTTP Range, ETRS89 / UTM 32N",
        nmt=_hb("dgm", "BHV", "2015", "DGM1 (terrain)", 3.2e6), nmpt=_hb("dom", "BHV", "2015", "DOM1 (trees, buildings)", 2.8e6),
        countries=("de",), regions=("de-hb",), bbox=(53.47, 53.62, 8.49, 8.66), crs="EPSG:25832",
        ortho=_hb_dop("Bremerhaven"), credits=(HB_CREDIT,),
        listing=ReadmeRow("Bremerhaven (DE)", "GeoInformation Bremen DGM1, 1 m (2015)",
                          "GeoInformation Bremen DOM1, 1 m (2015; the city only)", "GeoInformation Bremen DOP10"),
        offline=(("de-hb", (53.48, 53.50, 8.51, 8.56)), ("de-hb", (53.50, 53.52, 8.55, 8.64)),
                 ("de-hb", (53.52, 53.54, 8.56, 8.64)), ("de-hb", (53.54, 53.56, 8.55, 8.63)),
                 ("de-hb", (53.56, 53.58, 8.53, 8.62)), ("de-hb", (53.58, 53.60, 8.51, 8.59)),
                 ("de-hb", (53.58, 53.60, 8.60, 8.63))),
        sample=(53.5400, 8.5800),  # the centre, by the Geeste
        note=f"Data {HB_ATTRIBUTION}, CC BY 4.0 (changed: mosaicked onto the working grid; the surface model, whose "
             f"pixels lie half a pixel off the terrain's, interpolated onto it). Laser scanning of 2015. The surface "
             f"model covers the city only: beyond it lines are checked against the bare terrain."),
    Source(
        id="lower_saxony", name="LGLN (DGM1 / DOM1)",
        description="LGLN (Lower Saxony, Germany): ALS terrain and surface models 1 m, newest survey per "
                    "1 km tile, ETRS89 / UTM 32N, DHHN2016",
        # Several surveys per tile (2013 and 2018 in the Harz): each newer one covers whole tiles
        # ("Vollkacheln", checked 2026-11-01 at the edges of lots in the Harz, the Weserbergland and
        # on the Ems), so the newest per tile is enough. Pixel centres on x.5: edges on whole metres.
        nmt=_lgln("dgm", "DGM1 (terrain)"), nmpt=_lgln("dom", "DOM1 (trees, buildings)"),
        countries=("de",), regions=("de-ni",), crs="EPSG:25832", ortho=LGLN_DOP,
        credits=(LGLN_CREDIT,),
        neighbours=("saxony_anhalt", "hesse", "mecklenburg_vorpommern", "north_rhine_westphalia", "brandenburg",
                    "schleswig_holstein"),
        listing=ReadmeRow("Lower Saxony (DE)", "LGLN DGM1, 1 m; newest survey", "LGLN DOM1, 1 m",
                          "LGLN DOP20"),
        offline=(("de-ni", (51.29, 53.9, 6.65, 11.6)),), sample=(51.8770, 10.4460),
        note=f"Data © GeoBasis-DE/LGLN {YEAR}, CC BY 4.0 (changed: mosaicked onto the working grid).",
        coverage=Coverage(provider="LGLN", added="2026-11-01", survey="newest")),
    # Saxony and Baden-Württemberg last: their offline boxes overlap Saxony-Anhalt's (Leipzig) and Hesse's
    # (the Neckar at Heidelberg), which take those points offline; online the regions decide
    Source(
        id="saxony", name="GeoSN (DGM1 / DOM1)",
        description="GeoSN (Saxony, Germany): terrain and surface models 1 m from zipped 2 km tiles, "
                    "ETRS89 / UTM 33N, DHHN2016",
        nmt=_geosn("dgm", "DGM1 (terrain)"), nmpt=_geosn("dom", "DOM1 (trees, buildings)"),
        countries=("de",), regions=("de-sn",), crs="EPSG:25833", ortho=GEOSN_DOP,
        credits=(GEOSN_CREDIT,),
        neighbours=("geoportal", "saxony_anhalt", "czechia", "bavaria", "brandenburg"),
        listing=ReadmeRow("Saxony (DE)", "GeoSN DGM1, 1 m (2 km tiles)", "GeoSN DOM1, 1 m (2 km tiles)",
                          "GeoSN DOP20"),
        offline=(("de-sn", (50.15, 51.72, 11.79, 15.06)),), sample=(50.9200, 14.2100),
        note="Data: Quelle: GeoSN, dl-de/by-2.0 (changed: mosaicked onto the working grid). Survey dates "
             "2018-2025 per 2 km tile, not recorded.",
        coverage=Coverage(provider="GeoSN", added="2026-11-02", survey="2018–2025")),
    Source(
        id="baden_wurttemberg", name="LGL (DGM1 / DOM1)",
        description="LGL (Baden-Württemberg, Germany): terrain and surface models 1 m from zipped 2 km tiles, "
                    "ETRS89 / UTM 32N, DHHN2016",
        nmt=_lgl("dgm", "dgm", "xyz", "DGM1 (terrain)", 14.5e6),
        nmpt=_lgl("dom", "dom1", "tif", "DOM1 (trees, buildings)", 12e6),
        countries=("de",), regions=("de-bw",), crs="EPSG:25832", ortho=LGL_DOP,
        credits=(LGL_CREDIT,),
        neighbours=("hesse", "swisstopo", "france", "bavaria", "rhineland_palatinate"),
        listing=ReadmeRow("Baden-Württemberg (DE)", "LGL DGM1, 1 m (2 km tiles)", "LGL DOM1, 1 m (2 km tiles)",
                          "LGL DOP20"),
        offline=(("de-bw", (47.52, 49.83, 7.44, 10.54)),), sample=(48.0530, 8.9710),
        note="Data: Datenquelle: LGL, www.lgl-bw.de, dl-de/by-2.0 (changed: mosaicked onto the working grid). "
             "Survey years per 1 km tile, not recorded.",
        coverage=Coverage(provider="LGL", added="2026-11-02")),
    Source(
        id="bavaria", name="LDBV (DGM1 / DOM20)",
        description="LDBV (Bavaria, Germany): terrain model 1 m and photogrammetric surface model 0.2 m averaged "
                    "to 1 m, 1 km tiles listed by Metalinks, ETRS89 / UTM 32N, DHHN2016",
        nmt=MetalinkTiles("DGM1 (terrain)", [BY_DGM1], r"^(?P<east>\d{3})_(?P<north>\d{4})\.tif$", "bavaria/dgm1",
                          "EPSG:25832", "dgm1", bytes_per_tile=3.1e6),
        nmpt=MetalinkTiles("DOM20 averaged to 1 m (trees, buildings)", BY_DOM20,
                           r"^32(?P<east>\d{3})_(?P<north>\d{4})_20_DOM\.tif$", "bavaria/dom20-1m", "EPSG:25832",
                           "dom20", bytes_per_tile=49e6, average=5),
        countries=("de",), regions=("de-by",), crs="EPSG:25832", ortho=BY_DOP,
        credits=(BY_CREDIT,),
        neighbours=("austria", "hesse", "saxony", "baden_wurttemberg", "czechia"),
        listing=ReadmeRow("Bavaria (DE)", "LDBV DGM1, 1 m (1 km tiles)", "LDBV DOM20 averaged to 1 m (image matching)",
                          "LDBV DOP20"),
        offline=(("de-by", (47.27, 50.57, 8.97, 13.84)),), sample=(49.7700, 11.4100),
        note=f"Data: {BY_ATTRIBUTION}, CC BY 4.0 (changed: mosaicked onto the working grid, the DOM20's 0.2 m "
             f"averaged to 1 m). The surface model comes from image matching of aerial photographs, not from "
             f"laser scanning: smoother over trees and less exact (0.4-0.6 m). The files name no survey years.",
        coverage=Coverage(provider="LDBV", added="2026-11-02")),
    # Saarland before Rhineland-Palatinate: RP's offline box holds the whole Land
    Source(
        id="saarland", name="LVGL (DGM1 / DOM1)",
        description="LVGL (Saarland, Germany): terrain and surface models 1 m of 2025, members of district ZIP "
                    "archives read by HTTP Range, ETRS89 / UTM 32N, DHHN2016",
        nmt=_sl("dgm", "DGM1 (terrain)", 1.8e6), nmpt=_sl("dom", "DOM1 (trees, buildings)", 2.0e6),
        countries=("de",), regions=("de-sl",), crs="EPSG:25832", ortho=SL_DOP,
        credits=(SL_CREDIT,),
        neighbours=("rhineland_palatinate", "france", "luxembourg"),
        listing=ReadmeRow("Saarland (DE)", "LVGL DGM1, 1 m (2025)", "LVGL DOM1, 1 m (2025)", "LVGL DOP20"),
        # The Land, then Perl east of the Moselle (Luxembourg's box, later in SOURCES, reaches 6.54° E); the first box
        # also holds a strip of Lorraine, as RP's does
        offline=(("de-sl", (49.11, 49.64, 6.54, 7.41)), ("de-sl", (49.38, 49.52, 6.36, 6.54))),
        border_boxes=((49.38, 49.64, 6.33, 6.54),),  # Perl and Mettlach up to the Moselle and the Saar
        sample=(49.4611, 6.8573),  # the Michelbach quarry at Schmelz
        note=f"Data {SL_ATTRIBUTION}, dl-de/by-2.0 (changed: mosaicked onto the working grid, heights below "
             f"{SL_FLOOR:.0f} m and {SL_RING} pixels around them taken out: patches at 0 m in the survey, filled "
             f"like gaps). Survey 2025.",
        coverage=Coverage(provider="LVGL", added="2026-11-03", survey="2025")),
    Source(
        id="rhineland_palatinate", name="LVermGeo RP (DGM1 / DOM1)",
        description="LVermGeo (Rhineland-Palatinate, Germany): terrain and surface models 1 m, newest survey per "
                    "1 km tile listed by Metalinks, ETRS89 / UTM 32N, DHHN2016",
        nmt=_rp("dgm", "DGM1 (terrain)"), nmpt=_rp("dom", "DOM1 (trees, buildings)"),
        countries=("de",), regions=("de-rp",), crs="EPSG:25832", ortho=RP_DOP,
        credits=(RP_CREDIT,),
        neighbours=("hesse", "luxembourg", "france", "baden_wurttemberg", "north_rhine_westphalia", "saarland"),
        listing=ReadmeRow("Rhineland-Palatinate (DE)", "LVermGeo RP DGM1, 1 m; newest survey",
                          "LVermGeo RP DOM1, 1 m", "LVermGeo RP DOP20"),
        # Two boxes: Luxembourg's (to 6.54° E) comes later in SOURCES and would lose its points to one box
        offline=(("de-rp", (48.96, 50.95, 6.54, 8.51)), ("de-rp", (50.19, 50.95, 6.11, 6.54))), sample=(49.1500, 7.7800),
        border_boxes=((49.44, 50.19, 6.08, 6.54),),  # the Eifel down to the Our, the Sauer and the Moselle
        note=f"Data {RP_ATTRIBUTION} [Daten bearbeitet] (changed: mosaicked onto the working grid). Survey years "
             f"2022-2025, the newest per 1 km tile.",
        coverage=Coverage(provider="LVermGeo RP", added="2026-11-02", survey="2022–2025")),
    Source(
        id="north_rhine_westphalia", name="Geobasis NRW (DGM1 / DOM1)",
        description="Geobasis NRW (North Rhine-Westphalia, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 32N, DHHN2016",
        nmt=_nw("dgm", "DGM1 (terrain)", False),
        nmpt=_nw("dom", "DOM1 (trees, buildings)", True, (("GEOTIFF:COMPRESSION", "DEFLATE"),)),
        countries=("de",), regions=("de-nw",), crs="EPSG:25832", ortho=NW_DOP,
        credits=(NW_CREDIT,),
        neighbours=("hesse", "lower_saxony", "rhineland_palatinate", "netherlands"),
        listing=ReadmeRow("North Rhine-Westphalia (DE)", "Geobasis NRW DGM1, 1 m (WCS)", "Geobasis NRW DOM1, 1 m (WCS)",
                          "Geobasis NRW DOP"),
        # Aachen and the north, then the Eifel east of the Belgian border (not Belgium's East Cantons)
        offline=(("de-nw", (50.75, 52.53, 5.86, 9.46)), ("de-nw", (50.32, 50.75, 6.20, 8.25))), sample=(51.3200, 8.5400),
        note="Data Geobasis NRW, dl-de/zero-2.0 (changed: mosaicked onto the working grid). The WCS names no "
             "survey years.",
        coverage=Coverage(provider="Geobasis NRW", added="2026-11-02")),
    # Brandenburg (with Berlin inside its box) and Schleswig-Holstein after their neighbours: their offline boxes
    # overlap Saxony-Anhalt's, Saxony's and Mecklenburg-Vorpommern's (Lower Saxony's and M-V's), which take those
    # points offline (and Poland's, before them, the east of Brandenburg); online the regions decide
    Source(
        id="brandenburg", name="LGB (DGM1 / DOM1)",
        description="LGB (Brandenburg and Berlin, Germany): terrain and photogrammetric surface models 1 m from its "
                    "WCS, ETRS89 / UTM 33N, DHHN2016",
        nmt=_bb("dgm", "DGM1 (terrain)", True),
        nmpt=_bb("dom", "DOM1, lowest of the 0.2 m bDOM (trees, buildings)", False),
        countries=("de",), regions=("de-bb", "de-be"), crs="EPSG:25833", ortho=BB_DOP,
        credits=(BB_CREDIT,),
        neighbours=("geoportal", "saxony", "saxony_anhalt", "mecklenburg_vorpommern", "lower_saxony"),
        listing=ReadmeRow("Brandenburg and Berlin (DE)", "LGB DGM1, 1 m (WCS)",
                          "LGB DOM1, 1 m (WCS; image matching)", "LGB DOP20"),
        offline=(("de-bb", (51.36, 53.56, 11.26, 14.77)),), sample=(52.4745, 13.7965),
        note=f"Data {BB_ATTRIBUTION} (changed: mosaicked onto the working grid). The surface model comes from "
             f"image matching of aerial photographs (the lowest of each 5 x 5 pixels of the 0.2 m bDOM), not from "
             f"laser scanning: tree crowns come out lower and less exact. The WCS names no survey years.",
        coverage=Coverage(provider="LGB", added="2026-11-03")),
    Source(
        id="schleswig_holstein", name="LVermGeo SH (DGM1)",
        description="LVermGeo SH (Schleswig-Holstein, Germany): terrain model 1 m, plain XYZ files of 1 km listed by "
                    "a GeoJSON index, newest survey, ETRS89 / UTM 32N, DHHN2016",
        nmt=GeoJsonTiles("DGM1 (terrain)", [SH_INDEX], SH_NAME, "schleswig_holstein/dgm1", "EPSG:25832", "dgm1"),
        countries=("de",), regions=("de-sh",), crs="EPSG:25832", ortho=SH_DOP, sea_fill=SH_SEA_FILL,
        credits=(SH_CREDIT,),
        neighbours=("lower_saxony", "mecklenburg_vorpommern", "denmark", "hamburg"),
        listing=ReadmeRow("Schleswig-Holstein (DE)", "LVermGeo SH DGM1, 1 m (XYZ); newest survey", "–",
                          "LVermGeo SH DOP20"),
        # The Land south of the Danish islands, Angeln and North Frisia west of the Flensburg Fjord, then Sylt (one
        # box would hold Als, Aero and Langeland, which come later in SOURCES)
        offline=(("de-sh", (53.36, 54.56, 7.85, 11.32)), ("de-sh", (54.56, 54.84, 7.85, 10.15)),
                 ("de-sh", (54.84, 55.06, 8.27, 8.60))),
        border_boxes=((54.84, 54.93, 8.55, 9.5),),  # North Frisia and Flensburg's north up to the Danish border
        sample=(54.1840, 7.8820),  # Helgoland's cliffs (R56)
        note=f"Data {SH_ATTRIBUTION} (Quelle verändert; changed: mosaicked onto the working grid). Terrain model "
             f"only: the surface model is published only as uncompressed 0.2 m files. Survey years 2005-2025, the "
             f"newest per 1 km tile. Over the North Sea the newer surveys give a constant 1.30 m instead of the "
             f"water: it counts as water, and lines over it are measured from 1.30 m.",
        coverage=Coverage(provider="LVermGeo SH", added="2026-11-03", survey="2005–2025")),
]
