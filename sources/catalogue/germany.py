"""The German Länder: Saxony-Anhalt (LVermGeo's DGM1 and DOM1 from WCS), Lower Saxony (LGLN's DGM1
and DOM1 from STAC), Hesse (HVBG's DGM1 and DOM1 from WCS) and Mecklenburg-Vorpommern (LAiV's DGM1 and
DOM1 from WCS)."""

from typing import List

from ..credit import CC_BY, YEAR, Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.stac import StacTiles
from ..layers.wcs import WcsTiles

# LVermGeo's terms of use (Nutzungsbedingungen V 5.0, 01.03.2024, no. 2): open data under dl-de/by-2.0,
# the provider named "© GeoBasis-DE / LVermGeo ST"
LVERMGEO_ATTRIBUTION = "© GeoBasis-DE / LVermGeo ST"
DL_DE_BY = ("dl-de/by-2.0", "https://www.govdata.de/dl-de/by-2-0")
LVERMGEO_CREDIT = Credit("DGM1 / DOM1 (LVermGeo, Saxony-Anhalt)", LVERMGEO_ATTRIBUTION, *DL_DE_BY)
LVERMGEO_WCS = "https://geodatenportal.sachsen-anhalt.de/ows_INSPIRE_LVermGeo_ATKIS_EL_{}_WCS"
# DOP20 of LVermGeo, its open-data WMS in EPSG:4326 (dl-de/by-2.0 like all its open data); no request
# limits published
LVERMGEO_DOP = OrthoService("DOP20 Sachsen-Anhalt (LVermGeo)",
                            "https://www.geodatenportal.sachsen-anhalt.de/wss/service/ST_LVermGeo_DOP_WMS_OpenData/guest",
                            "lsa_lvermgeo_dop20_2", "saxony_anhalt/ortho/live", LVERMGEO_ATTRIBUTION)


def _lvermgeo(kind: str, description: str, zero_is_nodata: bool) -> WcsTiles:
    """DGM1 or DOM1 of LVermGeo from its INSPIRE WCS (ArcGIS, coverage Coverage1 over the Land's
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
# survey's year), one GeoTIFF asset each without a gsd or checksum
LGLN_ITEM = r"^d[go]m1_32_(?P<east>\d+)_(?P<north>\d+)_1_ni_(?P<year>\d{4})$"
# DOP20 of LGLN, a WMS in EPSG:4326; CC BY 4.0, credited "LGLN (<year of the download>)" (its
# AccessConstraints); no request limits published
LGLN_DOP = OrthoService("DOP20 Niedersachsen (LGLN)", "https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
                        "ni_dop20", "lower_saxony/ortho/live", f"LGLN ({YEAR}), CC BY 4.0")


def _lgln(kind: str, description: str) -> StacTiles:
    """DGM1 or DOM1 of LGLN: 1 km COG tiles of 1 m (float32, LZW, about 5 MB) from its own STAC API."""
    return StacTiles(description, f"https://{kind}.stac.lgln.niedersachsen.de", f"{kind}1",
                     f"lower_saxony/{kind}1", "EPSG:25832", sizes={1.0: 5e6}, asset=f"{kind}1-tif", item=LGLN_ITEM)


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
# <year of the last delivery>"; the year of the run (YEAR) stands for it, as for LGLN
LAIV_ATTRIBUTION = f"© GeoBasis-DE/M-V {YEAR}"
LAIV_CREDIT = Credit("DGM1 / DOM1 (LAiV, Mecklenburg-Vorpommern)", LAIV_ATTRIBUTION, *CC_BY)
# LAiV's DOP WMS (EPSG:4326, CC BY 4.0, the same notice); its images carry "© GeoBasis-DE/M-V" in
# their top left corner (in every tile), and nothing above 1:400000
LAIV_DOP = OrthoService("DOP Mecklenburg-Vorpommern (LAiV)", "https://www.geodaten-mv.de/dienste/adv_dop", "mv_dop",
                        "mecklenburg_vorpommern/ortho/live", f"{LAIV_ATTRIBUTION}, CC BY 4.0")


def _laiv(url: str, coverage: str, kind: str, description: str) -> WcsTiles:
    """DGM1 or DOM1 of LAiV from its WCS (MapServer, extent 200000-465000 / 5886000-6075000 in
    EPSG:25833): uncompressed GeoTIFF float32 with the CRS, pixel edges on whole metres; 2 km tiles
    at the native 1 m (16 MB, about 1.5 s; 5 km answered too). Sea, other water and the extent
    outside the Land are 0 without nodata (zero_is_nodata; land at exactly 0.000 m is a few
    hundred scattered pixels per 2 km tile on the lowest coasts, filled like gaps). A request
    partly beyond the extent is answered clipped, one wholly beyond it HTTP 400."""
    return WcsTiles(description, url, coverage, "EPSG:25833", f"mecklenburg_vorpommern/{kind}1/live",
                    native_res=1.0, fetch_res=1.0, tile_px=2000, zero_is_nodata=True)


SOURCES: List[Source] = [
    # Hesse and Mecklenburg-Vorpommern before Lower Saxony: their offline boxes overlap Lower
    # Saxony's (northern Hesse, western M-V with Schwerin), and the first box holding a point wins
    Source(
        id="hesse", name="HVBG (DGM1 / DOM1)",
        description="HVBG (Hesse, Germany): terrain and surface models 1 m from its WCS, ETRS89 / UTM 32N, "
                    "DHHN2016",
        nmt=_hvbg("dgm", "he_dgm1", "DGM1 (terrain)", False), nmpt=_hvbg("dom", "dom1", "DOM1 (trees, buildings)", True),
        countries=("de",), regions=("de-he",), crs="EPSG:25832", ortho=HVBG_DOP,
        neighbours=("lower_saxony",),
        credits=(HVBG_CREDIT,),
        listing=ReadmeRow("Hesse (DE)", "HVBG DGM1, 1 m (WCS)", "HVBG DOM1, 1 m (WCS)", "HVBG DOP"),
        offline=(("de-he", (49.39, 51.66, 7.77, 10.24)),), sample=(51.1830, 9.0500),
        note="Data HVBG, dl-de/zero-2.0 (changed: mosaicked onto the working grid). The WCS names no "
             "survey years."),
    Source(
        id="mecklenburg_vorpommern", name="LAiV M-V (DGM1 / DOM1)",
        description="LAiV (Mecklenburg-Vorpommern, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 33N, DHHN2016",
        nmt=_laiv("https://www.geodaten-mv.de/dienste/inspire_el_dgm_wcs", "mv_dgm", "dgm", "DGM1 (terrain)"),
        nmpt=_laiv("https://www.geodaten-mv.de/dienste/dom_wcs", "mv_dom1", "dom", "DOM1 (trees, buildings)"),
        countries=("de",), regions=("de-mv",), crs="EPSG:25833", ortho=LAIV_DOP,
        neighbours=("lower_saxony", "geoportal"),
        credits=(LAIV_CREDIT,),
        listing=ReadmeRow("Mecklenburg-Vorpommern (DE)", "LAiV DGM1, 1 m (WCS)", "LAiV DOM1, 1 m (WCS)",
                          "LAiV DOP"),
        offline=(("de-mv", (53.1, 54.7, 10.59, 14.42)),), sample=(54.5735, 13.6640),
        note=f"Data {LAIV_ATTRIBUTION}, CC BY 4.0. The sea is stored as 0 m, taken as no data. The WCS "
             f"names no survey years."),
    # Before Lower Saxony: their offline boxes overlap in the Harz (the first holding a point wins)
    Source(
        id="saxony_anhalt", name="LVermGeo (DGM1 / DOM1)",
        description="LVermGeo (Saxony-Anhalt, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 32N, DHHN2016",
        nmt=_lvermgeo("dgm", "DGM1 (terrain)", True), nmpt=_lvermgeo("dom", "DOM1 (trees, buildings)", False),
        countries=("de",), regions=("de-st",), crs="EPSG:25832", ortho=LVERMGEO_DOP,
        credits=(LVERMGEO_CREDIT,),
        neighbours=("lower_saxony",),
        listing=ReadmeRow("Saxony-Anhalt (DE)", "LVermGeo DGM1, 1 m (WCS)", "LVermGeo DOM1, 1 m (WCS)",
                          "LVermGeo DOP20"),
        offline=(("de-st", (50.94, 53.05, 10.56, 13.19)),), sample=(51.7340, 11.0200),
        note=f"Data {LVERMGEO_ATTRIBUTION}, dl-de/by-2.0. The WCS names no survey years."),
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
        neighbours=("saxony_anhalt", "hesse", "mecklenburg_vorpommern"),
        listing=ReadmeRow("Lower Saxony (DE)", "LGLN DGM1, 1 m; newest survey", "LGLN DOM1, 1 m",
                          "LGLN DOP20"),
        offline=(("de-ni", (51.29, 53.9, 6.65, 11.6)),), sample=(51.8770, 10.4460),
        note=f"Data © GeoBasis-DE/LGLN {YEAR}, CC BY 4.0 (changed: mosaicked onto the working grid)."),
]
