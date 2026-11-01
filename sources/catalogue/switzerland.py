"""swisstopo (Switzerland, Liechtenstein): swissALTI3D and swissSURFACE3D from STAC."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.stac import StacTiles

SWISSTOPO_CREDIT = Credit("swissALTI3D / swissSURFACE3D (swisstopo)", "© swisstopo",
                          "swisstopo OGD terms (free use, source stated)",
                          "https://www.swisstopo.admin.ch/en/conditions-geodata")
SWISSTOPO_STAC = "https://data.geo.admin.ch/api/stac/v1"
# SWISSIMAGE in the map's own tiling (CDN), imagery up to zoom 20; there is no WMS step.
# Fewer detailed tiles than elsewhere: swisstopo's terms ask for no bulk downloads.
SWISSIMAGE = OrthoService("SWISSIMAGE (swisstopo)", None, "", "switzerland/ortho/live", "© swisstopo",
                          base_url="https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current"
                                   "/3857/{z}/{x}/{y}.jpeg", base_max_zoom=20, detail=20)


SOURCES: List[Source] = [
    Source(
        id="swisstopo", name="swisstopo (swissALTI3D / swissSURFACE3D)",
        description="swisstopo (Switzerland, Liechtenstein): swissALTI3D terrain 0.5/2 m and swissSURFACE3D "
                    "Raster surface 0.5 m, newest survey per 1 km tile, LV95 / LN02",
        # 1 km COG tiles from the STAC API (swisstopo's download service): no elevation WCS
        # exists. The 2 m terrain files serve grids of 2 m and coarser; the surface model
        # is published at 0.5 m only (about 17 MB per km²).
        nmt=StacTiles("swissALTI3D (terrain)", SWISSTOPO_STAC, "ch.swisstopo.swissalti3d",
                      "switzerland/swissalti3d", "EPSG:2056", sizes={0.5: 20e6, 2.0: 1.3e6}),
        nmpt=StacTiles("swissSURFACE3D Raster (trees, buildings)", SWISSTOPO_STAC,
                       "ch.swisstopo.swisssurface3d-raster", "switzerland/swisssurface3d", "EPSG:2056",
                       sizes={0.5: 17e6}),
        countries=("ch", "li"), crs="EPSG:2056", ortho=SWISSIMAGE, credits=(SWISSTOPO_CREDIT,),
        neighbours=("austria", "south_tyrol"),
        listing=ReadmeRow("Switzerland, Liechtenstein",
                        "swissALTI3D, 2 m tiles for grids of 2 m or more, 0.5 m below; newest survey",
                        "swissSURFACE3D Raster, 0.5 m", "SWISSIMAGE (swisstopo)"),
        offline=(("ch", (45.8, 47.85, 5.9, 10.5)),), sample=(46.5960, 7.9070),
        note="Data © swisstopo."),
]
