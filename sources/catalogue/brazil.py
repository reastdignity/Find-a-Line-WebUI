"""Brazil: the city of Rio de Janeiro (Instituto Pereira Passos' 5 m lidar DTM, an Esri elevation tile cache)."""

import os
from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.lerc import LercTiles

# The city of Rio de Janeiro: Instituto Pereira Passos' (IPP, the city's planning institute) "Modelo Digital de
# Terreno (MDT)", the city's 2019 lidar DTM degraded to 5 m ("derivado de levantamento altimétrico a laser (LiDAR),
# com 5 metros de resolução espacial"; vertical datum not stated), published only as an Esri elevation tile cache
# (ArcGIS item 4dd8af31ff8f4486802613a8d1a22f33, service Painel_de_Monitoramento_3D_Reviver_Centro__23032022__WEL,
# created on 2022-03-23 for the city's "Painel 3D Reviver Centro"): LERC1 tiles in Web Mercator to level 15 (4.78 m,
# 4.40 m on the ground; level 16 answers 404), lercError 0.05 m. It is a project's layer, not a published dataset:
# it may vanish or change without notice (IPP's own MapServer pgeo3 shows the same model only as pictures), so the
# folder is live and the source falls back to europe wherever its tiles are gone. At sea the tiles hold artefacts
# down to -348 m (41 samples below -2 m in the city's tiles, wave 0 of 2026-11-15): below RJ_FLOOR no data. Read at
# level 15 for the 5 m grid and reprojected once onto SIRGAS 2000 / UTM zone 23S (EPSG:31983: SIRGAS 2000 is ITRF2000,
# which PROJ takes as WGS84 like Web Mercator's datum; zone 23S spans 48-42° W, the city lies at 43.1-43.8° W).
# Limits: none published (the item and the service, read 2026-11-15); tiles.arcgis.com is ArcGIS Online's shared
# tile host (CloudFront, max-age 3600): two at once (net.HOST_SLOTS_OF).
RJ_DTM_URL = ("https://tiles.arcgis.com/tiles/OlP4dGNtIcnD3RYf/arcgis/rest/services/"
              "Painel_de_Monitoramento_3D_Reviver_Centro__23032022__WEL/ImageServer")
RJ_EXTENT = (-4875440.139568845, -2642643.245298926, -4797071.023591221, -2601291.8207240254)  # its fullExtent
RJ_FLOOR = -5.0
# The cells with data (tools/lerc_coverage.py): --source auto takes europe where the DTM has nothing within 1 km of
# the centre (Niterói's shore and the other towns inside the city's box), and a search asks no tile far from data
RJ_CELLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rio_de_janeiro_dtm_cells.npz")
RJ_DTM = LercTiles("IPP Rio de Janeiro lidar DTM 5 m (terrain)", RJ_DTM_URL, "brazil/rio-mdt5m/live",
                   native_res=5.0, max_level=15, floor=RJ_FLOOR, extent=RJ_EXTENT, cells=RJ_CELLS, near_m=1000)
RIO_CRS = "EPSG:31983"
# The item's licenseInfo and accessInformation, verbatim (read 2026-11-15)
RJ_CREDIT = Credit("Modelo Digital de Terreno (MDT) 5 m, município do Rio de Janeiro (Instituto Pereira Passos)",
                   "Instituto Pereira Passos (PCRJ)", *CC_BY,
                   notice="This work is licensed under a Creative Commons Attribution 4.0 International License "
                          "(ArcGIS item 4dd8af31ff8f4486802613a8d1a22f33, read from its elevation tile service).")
# The city of Rio de Janeiro (the service's extent: 43.797-43.093 W, 23.088-22.746 S); Nominatim's region of the
# city is the whole State (BR-RJ), so the box decides
RJ_BOX = (-23.09, -22.75, -43.80, -43.09)

SOURCES: List[Source] = [
    Source(
        id="rio_de_janeiro", name="IPP Rio de Janeiro lidar DTM 5 m",
        description="Instituto Pereira Passos (city of Rio de Janeiro): the 2019 lidar DTM degraded to 5 m, from its "
                    "elevation tile cache, reprojected onto SIRGAS 2000 / UTM zone 23S",
        nmt=RJ_DTM, countries=("br",), bbox=RJ_BOX, crs=RIO_CRS, default_resolution=5.0, credits=(RJ_CREDIT,),
        listing=ReadmeRow("Rio de Janeiro city (BR)", "Instituto Pereira Passos lidar DTM 2019, 5 m (elevation tiles)"),
        offline=(("br", RJ_BOX),), sample=(-22.9519, -43.2105),
        instead_without_data="europe",
        note="Data: Instituto Pereira Passos (PCRJ), CC BY 4.0. The city's 2019 lidar DTM, degraded to 5 m by IPP "
             "(cliff edges are softened), is published only as a layer of a city project that may disappear; "
             "the vertical datum is not stated. No surface model: trees and buildings are not in the data.",
        # On the map: Brazil's part of the city's box at 5 m, the rest of the country at 30 m
        coverage=Coverage(provider="Instituto Pereira Passos", added="2026-11-15", survey="2019",
                          notes=("smoothed",), box=RJ_BOX)),
]
