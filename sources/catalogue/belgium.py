"""Belgium: Wallonia's lidar terrain and surface models 2021-2022 (SPW) as our own 2 km tiles at 1 m from the
project's data server or a local copy (tools/mirror_tiles.py). Flanders and Brussels keep FABDEM / Copernicus
(europe)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.gridtiles import GridTiles

# SPW's "Relief de la Wallonie" MNT and MNS 2021-2022 (lidar of 19/02/2021 to 05/03/2022, 0.5 m, heights in the
# Deuxième Nivellement Général, EPSG:5710; records a004e570... and 5a4c28fe... on geoportail.wallonie.be) are
# published only as ZIPs: five per model by province in EPSG:3812 (13.9 to 67.3 GB, 469.6 GB in all; the server
# ignores Range), each one raster of full-width strips with -9999 outside the province. tools/cdd_fetch.py fetch-list
# wallonia fetches them, tools/mirror_tiles.py cuts them at 1 m only (the user's decision of 2026-11-22), each pixel
# the mean of the valid 0.5 m pixels of its 2 x 2 block (Product.average), the provinces' shared pixels equal
# ("agree"), into the mirror (wallonia/dtm/1m, wallonia/dsm/1m: FINDALINE_MIRROR, or the data server); without either
# the source is unavailable and --source auto takes europe. A frozen survey: a versioned folder
WALLONIA_ORIGIN = (0.0, 0.0)  # the pixel edges on whole half-metres (tools/mirror_tiles.py DATASETS["wallonia"])
# Both records (read 2026-11-15): "Licence CC-BY 4.0 : L'utilisateur peut utiliser et modifier les données pour en
# dériver une œuvre. Il peut publier les données et l'œuvre dérivée à condition de citer les sources."; the credits
# verbatim as the records give them (the MNS's also in its ATOM feed, 2026-11-21)
WALLONIA_MNT_CREDIT = Credit(
    "Relief de la Wallonie MNT 2021-2022 (SPW, Wallonia)",
    "Source : Service public de Wallonie (SPW) - Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022 "
    "(2024-01-23) https://geodata.wallonie.be/id/a004e570-99d6-4fe5-b83d-49b774409278", *CC_BY)
WALLONIA_MNS_CREDIT = Credit(
    "Relief de la Wallonie MNS 2021-2022 (SPW, Wallonia)",
    "Source : Service public de Wallonie (SPW) - Relief de la Wallonie - Modèle Numérique de Surface (MNS) 2021-2022 "
    "(2024-01-23) https://geodata.wallonie.be/id/5a4c28fe-d30c-493e-861e-a80ebc703b64", *CC_BY)
# The tiles' sizes: Slovakia's 1 m tiles of terrain and surface (an estimate until the cut measures Wallonia's)
WALLONIA_DTM = GridTiles("Wallonia MNT 1 m (terrain)", [], "EPSG:3812", "belgium/wallonia-mnt/2022/epsg3812-1m-2km",
                         2000, 1.0, 4.8e6, mirror="wallonia/dtm/1m", origin=WALLONIA_ORIGIN,
                         tool="tools/mirror_tiles.py")
WALLONIA_DTM.credit = WALLONIA_MNT_CREDIT
WALLONIA_DSM = GridTiles("Wallonia MNS 1 m (trees, buildings)", [], "EPSG:3812",
                         "belgium/wallonia-mns/2022/epsg3812-1m-2km", 2000, 1.0, 5.7e6, mirror="wallonia/dsm/1m",
                         origin=WALLONIA_ORIGIN, tool="tools/mirror_tiles.py")
WALLONIA_DSM.credit = WALLONIA_MNS_CREDIT
# SPW's newest orthophotos (CC BY 4.0, record dfc9f3a2-adff-4b7f-ab77-8a890c4cabbb): the ArcGIS WMS of ORTHO_LAST,
# layer 0, asked in EPSG:4326 (fine at Freyr: the survey of 2026-10-31); yearly services of 2023-2026 exist beside it
SPW_ORTHO_RECORD = "https://geodata.wallonie.be/id/dfc9f3a2-adff-4b7f-ab77-8a890c4cabbb"
WALLONIA_ORTHO = OrthoService("Orthophoto SPW (most recent)",
                              "https://geoservices.wallonie.be/arcgis/services/IMAGERIE/ORTHO_LAST/MapServer/WMSServer",
                              "0", "belgium/wallonia-ortho/live",
                              "Source : Service public de Wallonie (SPW) - Orthophotos - Vues aériennes les plus "
                              f"récentes (2025-09-20) {SPW_ORTHO_RECORD}", attribution_url=SPW_ORTHO_RECORD)


SOURCES: List[Source] = [
    Source(
        id="wallonia", name="SPW Wallonia (MNT / MNS 2021-2022)",
        description="SPW (Wallonia, Belgium): lidar 2021-2022, terrain (MNT) and surface (MNS) models 0.5 m averaged "
                    "to 1 m, ETRS89 / Belgian Lambert 2008, DNG heights; our own tiles from the project's data server "
                    "or a local copy",
        nmt=WALLONIA_DTM, nmpt=WALLONIA_DSM, countries=("be",), regions=("be-wal",), crs="EPSG:3812",
        default_resolution=1.0, grid_origin=WALLONIA_ORIGIN, ortho=WALLONIA_ORTHO,
        credits=(WALLONIA_MNT_CREDIT, WALLONIA_MNS_CREDIT),
        # Flanders, Brussels and the sea from FABDEM / Copernicus
        fallback="europe",
        # Both ways (tests/test_neighbours.py): not France or Rhineland-Palatinate, which declare six already (the
        # country layer's most, countcube.PARTNERS); not North Rhine-Westphalia while its boxes hold only 71 % of
        # its land within 5 km of Wallonia (tools/border_study.py boxes, 2026-11-23: the Eifel west of 6.20 E
        # needs a border box of its own first)
        neighbours=("luxembourg", "netherlands"),
        listing=ReadmeRow("Wallonia (BE)", "SPW MNT 2021–2022, lidar 0.5 m averaged to 1 m",
                          "SPW MNS 2021–2022, lidar 0.5 m averaged to 1 m", "SPW orthophoto (most recent)"),
        # The region's box; after France, Luxembourg, the Netherlands and Germany in FAMILIES, whose boxes keep their
        # own land (Lille, Luxembourg, Aachen) where this box reaches over it
        offline=(("be-wal", (49.49, 50.82, 2.83, 6.41)),), sample=(50.2180, 4.8940),  # the Rochers de Freyr
        note="Wallonia's terrain and surface models (SPW, CC BY 4.0: lidar 2021-2022, 0.5 m, averaged to 1 m). Its "
             "tiles come from the project's data server or a local copy (tools/mirror_tiles.py).",
        coverage=Coverage(provider="SPW", added="2026-11-23", survey="2021–2022")),
]
