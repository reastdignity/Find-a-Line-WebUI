"""ÚGKK SR (Slovakia): our own tiles of DMR 5.0 and DMP 1.0."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.gridtiles import GridTiles

UGKK_CREDIT = Credit("DMR 5.0 / DMP 1.0 (ÚGKK SR, Slovakia)", "© ÚGKK SR", *CC_BY)
# Our own copy of ÚGKK SR's national ALS models (tools/sk_tiles.py): only the local mirror
# (FINDALINE_MIRROR) for now; the Hugging Face base goes here once the tiles are uploaded
SLOVAK_TILES: List[str] = []
ZBGIS_ORTHO = OrthoService("Orthophoto ZBGIS (ÚGKK SR)",
                           "https://zbgisws.skgeodesy.sk/zbgis_ortofoto_wms/service.svc/get", "1",
                           "slovakia/ortho/live", "© ÚGKK SR")


SOURCES: List[Source] = [
    Source(
        id="slovakia", name="ÚGKK SR (DMR 5.0 / DMP 1.0)",
        description="ÚGKK SR (Slovakia): ALS 2017-2023, DMR 5.0 terrain and DMP 1.0 surface, 1 m, "
                    "S-JTSK [JTSK03] / Bpv",
        # Published only as one ZIP of 155-200 GB per model: our own 2 km tiles of them
        # (tools/sk_tiles.py), on the national grid, pixel edges on whole metres
        nmt=GridTiles("DMR 5.0 (terrain)", [f"{base}/dmr5/1m" for base in SLOVAK_TILES], "EPSG:8353",
                      "slovakia/dmr5/5.0/epsg8353-1m-2km", 2000, 1.0, 4.8e6, mirror="slovakia/dmr5/1m"),
        nmpt=GridTiles("DMP 1.0 (trees, buildings)", [f"{base}/dmp1/1m" for base in SLOVAK_TILES], "EPSG:8353",
                       "slovakia/dmp1/1.0/epsg8353-1m-2km", 2000, 1.0, 5.7e6, mirror="slovakia/dmp1/1m"),
        countries=("sk",), crs="EPSG:8353", ortho=ZBGIS_ORTHO, credits=(UGKK_CREDIT,),
        listing=ReadmeRow("Slovakia", "ÚGKK SR DMR 5.0, ALS 1 m (2017–2023)", "ÚGKK SR DMP 1.0, 1 m",
                        "ZBGIS (ÚGKK SR)"),
        # Poland's box overlaps it in the north: Poland comes first in SOURCES
        offline=(("sk", (47.7, 49.65, 16.8, 22.6)),), sample=(49.1700, 18.5750),
        note="Data © ÚGKK SR, CC BY 4.0 (laser scanning 2017-2023)."),
]
