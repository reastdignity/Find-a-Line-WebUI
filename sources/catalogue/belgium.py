"""Belgium: Wallonia's lidar terrain and surface models 2021-2022 (SPW) as our own 2 km tiles at 0.5 m from the
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
# wallonia fetches them, tools/mirror_tiles.py cuts them at their own 0.5 m pixels only, nothing averaged (the user's
# decision of 2026-11-26, "store native", "0.5 m only", which replaced the 1 m only of 2026-11-22), the provinces'
# shared pixels equal ("agree"), into the mirror (wallonia/dtm/0.5m, wallonia/dsm/0.5m: FINDALINE_MIRROR, or the data
# server); without either the source is unavailable and --source auto takes europe. The 1 m working grid (edges on
# whole metres) averages 2 x 2 of the tiles' pixels, as Luxembourg's and the Netherlands'. A frozen survey: a
# versioned folder
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
# The tiles' sizes: four times Slovakia's 1 m tiles of terrain and surface (estimates until the cut measures
# Wallonia's)
WALLONIA_DTM = GridTiles("Wallonia MNT 0.5 m (terrain)", [], "EPSG:3812",
                         "belgium/wallonia-mnt/2022/epsg3812-0.5m-2km", 2000, 0.5, 19.2e6, mirror="wallonia/dtm/0.5m",
                         origin=WALLONIA_ORIGIN, tool="tools/mirror_tiles.py")
WALLONIA_DTM.credit = WALLONIA_MNT_CREDIT
WALLONIA_DSM = GridTiles("Wallonia MNS 0.5 m (trees, buildings)", [], "EPSG:3812",
                         "belgium/wallonia-mns/2022/epsg3812-0.5m-2km", 2000, 0.5, 22.8e6, mirror="wallonia/dsm/0.5m",
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


WALLONIA_BOX = (49.49, 50.82, 2.83, 6.41)  # the region's rectangle (wave 0; Nominatim's box of BE-WAL)
# Offline (no lookup) the region by bands of 0.05 degrees, in each the runs of 0.01-degree cells lying inside the
# coverage map's be-wal outline (Natural Earth) shrunk by 0.01 degrees and 0.015 degrees off every other country's:
# tools/offline_boxes.py be-wal (its defaults; checked against Natural Earth's unsimplified admin-1 units: no box
# holds another unit's land). They keep off France (Givet, Charleville, Sedan, Maubeuge), Flanders (Ronse, Tongeren),
# the Netherlands, Germany and Luxembourg, so a point there is chosen as before (europe, or its own source); 84 % of
# the outline's area; the strip along the borders (Bouillon, Comines, Kelmis) takes europe offline, as all of Belgium
# did before (online, Nominatim's region and the bbox choose wallonia there). Arlon and Martelange lie in
# Luxembourg's box, which comes first (as before)
WALLONIA_OFFLINE = (
    (49.55, 49.60, 5.49, 5.74), (49.60, 49.65, 5.42, 5.82), (49.65, 49.70, 5.35, 5.80), (49.70, 49.75, 5.27, 5.76),
    (49.75, 49.80, 5.10, 5.71), (49.80, 49.85, 4.90, 4.92), (49.80, 49.85, 5.00, 5.71), (49.85, 49.90, 4.87, 5.70),
    (49.90, 49.95, 4.87, 5.71), (49.95, 50.00, 4.83, 5.74), (50.00, 50.05, 4.22, 4.58), (50.00, 50.05, 4.85, 5.79),
    (50.05, 50.10, 4.22, 4.65), (50.05, 50.10, 4.87, 5.83), (50.10, 50.15, 4.21, 4.69), (50.10, 50.15, 4.88, 5.85),
    (50.15, 50.20, 4.18, 4.77), (50.15, 50.20, 4.88, 5.93), (50.20, 50.25, 4.21, 6.14), (50.25, 50.30, 4.21, 6.18),
    (50.30, 50.35, 4.11, 6.27), (50.35, 50.40, 3.69, 3.73), (50.35, 50.40, 3.97, 6.33), (50.40, 50.45, 3.66, 6.30),
    (50.45, 50.50, 3.66, 6.17), (50.50, 50.55, 3.57, 6.15), (50.55, 50.60, 3.28, 6.15), (50.60, 50.65, 3.27, 6.12),
    (50.65, 50.70, 3.25, 3.88), (50.65, 50.70, 4.08, 4.19), (50.65, 50.70, 4.32, 5.05), (50.65, 50.70, 5.19, 6.04),
    (50.70, 50.75, 3.25, 3.29), (50.70, 50.75, 3.45, 3.52), (50.70, 50.75, 3.68, 3.75), (50.70, 50.75, 4.66, 4.90),
    (50.70, 50.75, 4.97, 4.99), (50.70, 50.75, 5.53, 5.68))


SOURCES: List[Source] = [
    Source(
        id="wallonia", name="SPW Wallonia (MNT / MNS 2021-2022)",
        description="SPW (Wallonia, Belgium): lidar 2021-2022, terrain (MNT) and surface (MNS) models 0.5 m, "
                    "ETRS89 / Belgian Lambert 2008, DNG heights; our own tiles from the project's data server or a "
                    "local copy",
        # 0.5 m tiles; the 1 m working grid (edges on whole metres) averages 2 x 2 of them (as Luxembourg's)
        nmt=WALLONIA_DTM, nmpt=WALLONIA_DSM, countries=("be",), regions=("be-wal",), crs="EPSG:3812",
        default_resolution=1.0, grid_origin=WALLONIA_ORIGIN, ortho=WALLONIA_ORTHO,
        credits=(WALLONIA_MNT_CREDIT, WALLONIA_MNS_CREDIT),
        # Flanders, Brussels and the sea from FABDEM / Copernicus
        fallback="europe",
        # Both ways (tests/test_neighbours.py), each declaring it last; North Rhine-Westphalia with its border box
        # of the Eifel (the user's decision of 2026-11-23). Not France or Rhineland-Palatinate, which declare six
        # already (the country layer's most, countcube.PARTNERS; the user's decision of 2026-11-23: docs/roadmap.md)
        neighbours=("luxembourg", "north_rhine_westphalia", "netherlands"),
        listing=ReadmeRow("Wallonia (BE)", "SPW MNT 2021–2022, lidar 0.5 m", "SPW MNS 2021–2022, lidar 0.5 m",
                          "SPW orthophoto (most recent)"),
        # The region's rectangle chooses nothing (it holds French, Flemish, Dutch, German and Luxembourg land): it
        # keeps the neighbours' fill and the area download over all of Wallonia; offline the staircase inside it
        bbox=WALLONIA_BOX, offline=tuple(("be-wal", box) for box in WALLONIA_OFFLINE),
        sample=(50.2180, 4.8940),  # the Rochers de Freyr
        note="Wallonia's terrain and surface models (SPW, CC BY 4.0: lidar 2021-2022, 0.5 m). Its tiles come from "
             "the project's data server or a local copy (tools/mirror_tiles.py).",
        coverage=Coverage(provider="SPW", added="2026-11-23", survey="2021–2022")),
]
