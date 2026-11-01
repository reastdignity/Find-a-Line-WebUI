"""The German Länder: Saxony-Anhalt (LVermGeo's DGM1 and DOM1 from WCS) and Lower Saxony (LGLN's DGM1
and DOM1 from STAC)."""

from typing import List

from ..credit import CC_BY, Credit
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
# downloaded is not kept, so the year of this declaration stands for it
LGLN_YEAR = 2026
LGLN_CREDIT = Credit("DGM1 / DOM1 (LGLN, Lower Saxony)", f"© GeoBasis-DE/LGLN {LGLN_YEAR}, Daten geändert",
                     *CC_BY)
# The items of LGLN's collections: dgm1_32_<E>_<N>_1_ni_<year> (E and N in km of EPSG:25832, the
# survey's year), one GeoTIFF asset each without a gsd or checksum
LGLN_ITEM = r"^d[go]m1_32_(?P<east>\d+)_(?P<north>\d+)_1_ni_(?P<year>\d{4})$"
# DOP20 of LGLN, a WMS in EPSG:4326; CC BY 4.0, credited "LGLN (<year of the download>)" (its
# AccessConstraints); no request limits published
LGLN_DOP = OrthoService("DOP20 Niedersachsen (LGLN)", "https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
                        "ni_dop20", "lower_saxony/ortho/live", f"LGLN ({LGLN_YEAR}), CC BY 4.0")


def _lgln(kind: str, description: str) -> StacTiles:
    """DGM1 or DOM1 of LGLN: 1 km COG tiles of 1 m (float32, LZW, about 5 MB) from its own STAC API."""
    return StacTiles(description, f"https://{kind}.stac.lgln.niedersachsen.de", f"{kind}1",
                     f"lower_saxony/{kind}1", "EPSG:25832", sizes={1.0: 5e6}, asset=f"{kind}1-tif", item=LGLN_ITEM)


SOURCES: List[Source] = [
    # Before Lower Saxony: their offline boxes overlap in the Harz (the first holding a point wins)
    Source(
        id="saxony_anhalt", name="LVermGeo (DGM1 / DOM1)",
        description="LVermGeo (Saxony-Anhalt, Germany): terrain and surface models 1 m from its WCS, "
                    "ETRS89 / UTM 32N, DHHN2016",
        nmt=_lvermgeo("dgm", "DGM1 (terrain)", True), nmpt=_lvermgeo("dom", "DOM1 (trees, buildings)", False),
        countries=("de",), regions=("de-st",), crs="EPSG:25832", ortho=LVERMGEO_DOP,
        credits=(LVERMGEO_CREDIT,),
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
        listing=ReadmeRow("Lower Saxony (DE)", "LGLN DGM1, 1 m; newest survey", "LGLN DOM1, 1 m",
                          "LGLN DOP20"),
        offline=(("de-ni", (51.29, 53.9, 6.65, 11.6)),), sample=(51.8770, 10.4460),
        note=f"Data © GeoBasis-DE/LGLN {LGLN_YEAR}, CC BY 4.0 (changed: mosaicked onto the working grid)."),
]
