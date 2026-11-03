"""Denmark: Klimadatastyrelsen's Danmarks Hojdemodel (DHM), terrain and surface models 0.4 m, from
Datafordeler's WCS with the server's own API key (settings.ServiceKeys.datafordeler_api_key)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import ReadmeRow, Source
from ..layers.wcs import WcsTiles

# DHM is open data under CC BY 4.0 since 16 May 2024 (the fixed sentence of the 2022 terms is for data
# downloaded before). KDS leaves the wording to the user, but it names the data owner, says CC BY 4.0
# with a link to the licence, links the datasets and says that the data was processed (a mosaic on
# our grid is): the attribution names the owner, the licence and the processing, the notice
# (ATTRIBUTION.txt) the datasets
DHM_ATTRIBUTION = "Danmarks Højdemodel (Terræn / Overflade), Klimadatastyrelsen, CC BY 4.0, processed"
DHM_DATASETS = ("Datasets: DHM/Terræn https://dataforsyningen.dk/data/930, "
                "DHM/Overflade https://dataforsyningen.dk/data/928 (Klimadatastyrelsen).")
DHM_CREDIT = Credit("Danmarks Højdemodel, DHM/Terræn and DHM/Overflade (Klimadatastyrelsen)", DHM_ATTRIBUTION,
                    *CC_BY, notice=DHM_DATASETS)
# Datafordeler's modernised WCS of DHM (KDS's "WMS-, WMTS- og WCS-tjenester", confluence.kds.dk/x/lIGjDQ,
# July 2026: WCS 1.0.0 only, the key as the query parameter apikey; the old api.dataforsyningen.dk
# dhm_wcs_DAF closes in 2026). Every request without a valid key, GetCapabilities too, is answered 401
# (problem+json, DAF-AUTH-0005), and an API key works only from an address on its IT-system's allowlist.
# The path's "Nedboer" (precipitation) is the service's name in that list: the only current DHM WCS there
DHM_WCS = "https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS"
DHM_KEY = (("apikey", "datafordeler_api_key"),)


def _dhm(coverage: str, folder: str, description: str) -> WcsTiles:
    """DHM/Terraen or DHM/Overflade from the WCS, in ETRS89 / UTM 32N with DVR90 heights. As the live
    service answered on 2026-11-01 (GetCapabilities, DescribeCoverage, GetCoverage with a key): the
    coverages dhm_terraen and dhm_overflade, GeoTIFF as "GTiff" (float32, uncompressed, no nodata
    value), the extent 441000-894000 E / 6049000-6403000 N on a 0.4 m grid whose pixel edges lie on
    whole metres (origin (0, 0) fits), the requested BBOX answered on exactly the requested pixels
    (nearest neighbour by default), 4000 px tiles accepted (2000 px tiles at the working resolution:
    2 km at 1 m, 16 MB). The sea, Germany and everything outside the data are 0.0, never nodata, so
    zero is nodata here: otherwise the fallback could not fill across the border and the sea would
    be land at 0 m (the land's heights carry millimetres: a pixel of exactly 0.000 m on land is
    rare, and the water filling takes it like the sea). Names, descriptions and notes are printed
    to a console, so they are ASCII ("Terraen", "Hojdemodel"); the credit keeps the Danish letters."""
    return WcsTiles(description, DHM_WCS, coverage, "EPSG:25832", f"denmark/{folder}/live", native_res=0.4,
                    tile_px=2000, fmt="GTiff", zero_is_nodata=True, version="1.0.0", key_params=DHM_KEY)


SOURCES: List[Source] = [
    Source(
        id="denmark", name="Klimadatastyrelsen (DHM)",
        description="Klimadatastyrelsen (Denmark): Danmarks Hojdemodel, terrain and surface models 0.4 m from "
                    "Datafordeler's WCS, ETRS89 / UTM 32N, DVR90",
        nmt=_dhm("dhm_terraen", "dhm-terraen", "DHM/Terraen 0.4 m (terrain)"),
        nmpt=_dhm("dhm_overflade", "dhm-overflade", "DHM/Overflade 0.4 m (trees, buildings)"),
        countries=("dk",), crs="EPSG:25832", credits=(DHM_CREDIT,), neighbours=("schleswig_holstein",),
        listing=ReadmeRow("Denmark", "Klimadatastyrelsen DHM/Terræn, 0.4 m (WCS, API key)",
                          "Klimadatastyrelsen DHM/Overflade, 0.4 m (WCS, API key)"),
        # Jutland and the islands north of the border, the southern islands (Aero, Langeland, Lolland,
        # Falster) east of Angeln, then Bornholm with Ertholmene: one box would hold northern
        # Schleswig-Holstein and much of Skane (Mecklenburg-Vorpommern's box, before it, still takes
        # the southern tip of Lolland and Falster)
        offline=(("dk", (54.90, 57.76, 8.07, 12.70)), ("dk", (54.56, 54.90, 10.15, 12.70)),
                 ("dk", (54.98, 55.32, 14.68, 15.21))),
        sample=(54.9700, 12.5500),  # on the cliff of Mons Klint (R38)
        note="Data: Klimadatastyrelsen, Danmarks Hojdemodel, CC BY 4.0 (processed: mosaicked onto the "
             "working grid)."),
]
