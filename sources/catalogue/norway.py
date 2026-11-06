"""Norway: Kartverket's national elevation models DTM 1 and DOM 1 (Nasjonal detaljert hoydemodell, 1 m) from
Geonorge's WCS 1.0.0 in ETRS89 / UTM 33N (no key)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.wcs import WcsTiles

# Kartverket's terms of use (https://www.kartverket.no/en/api-and-data/terms-of-use, read 2026-11-02): open data
# under CC BY 4.0, "the name of the Norwegian Mapping Authority will appear ... in the following way: ©Kartverket.
# It should also be linked to our websites where this is possible." The map links the licence, so the link to
# Kartverket goes into the notice (ATTRIBUTION.txt); CC BY asks to say that the data were changed: "processed"
KARTVERKET_ATTRIBUTION = "©Kartverket, CC BY 4.0, processed"
KARTVERKET_CREDIT = Credit("Nasjonal detaljert høydemodell, DTM 1 / DOM 1 (Kartverket)", KARTVERKET_ATTRIBUTION,
                           *CC_BY, notice="©Kartverket, https://www.kartverket.no/ (data: https://hoydedata.no/).")

# Geonorge's WCS of the national 1 m models, the successor of "Hoyde DTM 1 (UTM33) WCS" (removed 2021-09-01).
# As the services answered on 2026-11-02 (GetCapabilities, DescribeCoverage, GetCoverage): WCS 1.0.0 behind
# ArcGIS Server, the coverages nhm_dtm_topo_25833 and nhm_dom_topo_25833 in EPSG:25833 for the whole country
# (the west, UTM zone 32, too), the envelope -100275..1150255 E / 6399725..8000275 N on a 1 m grid whose pixel
# edges lie on whole metres (origin (0, 0) fits); GeoTIFF float32, uncompressed (no format option compresses it;
# the answer comes gzipped when asked, as requests does), no nodata value, the stored values exactly where the
# BBOX lies on whole metres (nearest neighbour by default). The server takes at most 4096 px a side (its
# DescribeCoverage says 3840 x 2160) and refuses more with HTTP 200 and an XML exception report, which fails as
# a raster (an error, never data); 2000 px tiles: 2 km at 1 m, 16 MB, about 2.5 s. No published request limit
# (the capabilities: fees "free", access constraints "None"): HOST_SLOTS_OF caps it as a courtesy.
NHM_DTM_WCS = "https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25833"
NHM_DOM_WCS = "https://wcs.geonorge.no/skwms1/wcs.hoyde-dom-nhm-25833"
UTM33 = "EPSG:25833"


def _nhm(url: str, coverage: str, folder: str, description: str) -> WcsTiles:
    """DTM 1 or DOM 1 from Geonorge's WCS. The sea, Sweden, Finland and everything without data are 0.0, never
    nodata (the source files too: their nodata value -32767 is not used), so zero is nodata, as in Denmark: the
    heights carry centimetres, and a land pixel of exactly 0.00 m is taken as water. The models are updated as
    new laser projects come in: the folder is "live"."""
    return WcsTiles(description, url, coverage, UTM33, f"norway/{folder}/live", native_res=1.0, tile_px=2000,
                    fmt="GeoTIFF", zero_is_nodata=True, version="1.0.0")


NO_DTM = _nhm(NHM_DTM_WCS, "nhm_dtm_topo_25833", "nhm-dtm1", "NHM DTM 1 1 m (terrain)")
NO_DOM = _nhm(NHM_DOM_WCS, "nhm_dom_topo_25833", "nhm-dom1", "NHM DOM 1 1 m (trees, buildings)")

SOURCES: List[Source] = [
    Source(
        id="norway", name="Kartverket (NHM DTM 1 / DOM 1)",
        description="Kartverket (Norway): national elevation models DTM 1 and DOM 1, 1 m from Geonorge's WCS, "
                    "ETRS89 / UTM 33N for the whole country (lengths up to +0.3 % too long in the west and "
                    "+0.4 % in the far east)",
        nmt=NO_DTM, nmpt=NO_DOM, countries=("no",), crs=UTM33, credits=(KARTVERKET_CREDIT,),
        listing=ReadmeRow("Norway (mainland)", "Kartverket NHM DTM 1, 1 m (WCS)", "Kartverket NHM DOM 1, 1 m (WCS)",
                          "– (Norge i bilder needs a token)"),
        # The mainland in boxes along the Swedish border, so little of Sweden falls into them; Finland's box
        # (before it in SOURCES) holds Troms and Finnmark between 19.3 and 31.6 E south of 70.1 N, so offline
        # those points are taken for Finland (the neighbours fill each other's border gaps). The northern box
        # first: it touches Finland's (tests/test_neighbours.py)
        offline=(("no", (69.00, 71.20, 15.50, 31.20)), ("no", (57.90, 59.10, 4.50, 11.00)),
                 ("no", (59.10, 60.00, 4.50, 11.80)), ("no", (60.00, 62.00, 4.50, 12.30)),
                 ("no", (62.00, 63.50, 4.50, 12.00)),
                 ("no", (63.50, 64.50, 7.00, 13.00)), ("no", (64.50, 65.50, 9.00, 14.00)),
                 ("no", (65.50, 66.50, 11.50, 14.50)), ("no", (66.50, 68.00, 11.50, 15.60)),
                 ("no", (68.00, 69.00, 11.50, 17.50))),
        border_boxes=((68.5, 69.0, 21.0, 26.0),),  # Finnmark's south (Kautokeino) down to the Finnish border
        neighbours=("finland",),
        sample=(58.9864, 6.1904),  # Preikestolen (R40)
        note="Data: Kartverket, CC BY 4.0 (processed: mosaicked onto the working grid). The working grid is "
             "ETRS89 / UTM 33N for the whole country: lengths are up to 0.3 % too long in the west and 0.4 % "
             "in the far east.",
        coverage=Coverage(provider="Kartverket", added="2026-11-02", box=(57.8, 71.5, 4.0, 31.5))),
]
