"""geoportal.gov.pl (GUGiK, Poland): NMT and NMPT sheets."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.sheets import SheetTiles

GUGIK_CREDIT = Credit("NMT / NMPT (GUGiK, Poland)",
                      "Source: Główny Urząd Geodezji i Kartografii (GUGiK), geoportal.gov.pl",
                      "geoportal.gov.pl terms (free use, source stated)",
                      "https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/")


GEOPORTAL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK"


SOURCES: List[Source] = [
    Source(
        id="geoportal", name="geoportal.gov.pl",
        description="GUGiK (Poland): NMT and NMPT sheets of 1 m or finer, newest survey, PL-EVRF2007-NH",
        # Sheet files from opendata.geoportal.gov.pl, found through the EVRF2007 sheet
        # indexes: about 2 s per sheet, while the WCS spends 30-50 s generating each ASCII
        # tile, its downsampling loses data at coarse resolutions (Tatras at 5 m) and its
        # PL-KRON86-NH coverages hold surveys up to 2019 only.
        nmt=SheetTiles("NMT (digital terrain model)", f"{GEOPORTAL}/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze",
                       "SkorowidzNMT", "poland/nmt", native_res=1.0),
        nmpt=SheetTiles("NMPT (digital surface model: trees, buildings)",
                        f"{GEOPORTAL}/NumerycznyModelPokryciaTerenuEVRF2007/WFS/Skorowidze",
                        "SkorowidzNMPT", "poland/nmpt", native_res=1.0),
        countries=("pl",), crs="EPSG:2180", grid_origin=(0.5, 0.5), credits=(GUGIK_CREDIT,),
        listing=ReadmeRow("Poland", "GUGiK NMT sheets, 1 m, newest survey",
                        "GUGiK NMPT sheets, 0.5–1 m (about 85% of Poland)", "geoportal.gov.pl"),
        offline=(("pl", (49.0, 54.9, 14.1, 24.2)),), sample=(50.1559508, 19.7562722),
        ortho=OrthoService("Orthophoto (geoportal.gov.pl)", f"{GEOPORTAL}/ORTO/WMS/HighResolution",
                           "Raster", "poland/ortho/live", "GUGiK",
                           # the WMS of StandardResolution answers about half of the requests
                           # with 404 (2026-10-25); its WMTS answers all
                           base_url=f"{GEOPORTAL}/ORTO/WMTS/StandardResolution?SERVICE=WMTS&REQUEST=GetTile"
                                    "&VERSION=1.0.0&LAYER=ORTOFOTOMAPA&STYLE=default&FORMAT=image/jpeg"
                                    "&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}")),
]
