"""Iceland: ArcticDEM 2 m (the source `iceland`) with the Natural Science Institute of Iceland's (Natturufraedistofnun,
formerly LMI) IslandsDEM v1.0 10 m as its gap filler, one national COG read in blocks (also the source
`islandsdem10`), and the institute's aerial basemap (a WMS asked in Web Mercator)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import OrthoService, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks
from .arctic import ARCTIC_CREDIT, ARCTIC_DEM_2M, arctic_note
from .world import COPERNICUS_DISCLAIMER, COPERNICUS_NOTICE

# ISN2016 / Lambert 2016 (EPSG:8088): standard parallels 64.25 and 65.75 deg N, so its scale stays within
# -0.01 % (65 deg N) and +0.035 % (the south coast at 63.3 deg N) over Iceland
IS_CRS = "EPSG:8088"
# The open data page states CC BY 4.0 and the pattern of the credit: '"IS 50V Vatnafar" by Natturufraedistofnun is
# licensed under CC BY 4.0' (read 2026-11-03); no published usage limits (gis.natt.is and ftp.natt.is: courtesy
# caps in net.HOST_SLOTS_OF)
IS_OPEN_DATA = "https://www.natt.is/en/resources/open-data"

# IslandsDEM v1.0 (2021): 10 m, merged from co-registered ArcticDEM strips, lidar and Copernicus GLO-30 (its
# lineage), heights above sea level ("zmasl"), void-free on land. One COG for all of Iceland (3 GB: 52 000 x
# 37 000 px, float32, ZSTD with predictor 2, 512 px tiles, no overviews, nodata -3.4e38, pixel edges on whole 10 m
# from 2 440 000 / 480 000). Unchanged since 2021: a static folder.
IS_DEM_URL = "https://ftp.natt.is/gisdata/raster/IslandsDEMv1.0_10x10m_isn2016_zmasl.tif"
IS_DEM_EXTENT = (2440000.0, 110000.0, 2960000.0, 480000.0)  # the file's bounds: blocks outside make no request
# The provider's pattern, the Icelandic name kept (a credit's attribution is never printed to the console, only
# written to the run's files and the map, all UTF-8), and the Copernicus sentence its GLO-30 part asks for
# (as MRDEM-30's)
IS_DEM_CREDIT = Credit("IslandsDEM v1.0 10 m (Natural Science Institute of Iceland)",
                       "\"IslandsDEM v1.0\" by Náttúrufræðistofnun is licensed under CC BY 4.0. This product was in part "
                       f"{COPERNICUS_NOTICE}.", *CC_BY,
                       notice=f"Terms: {IS_OPEN_DATA}. {COPERNICUS_DISCLAIMER}")
# Blocks of 5 km (500 x 500 px, parts of at most four of the file's 512 px tiles), about 0.5 MB cached
IS_DEM_10M = FileBlocks("IslandsDEM v1.0 10 m (terrain)", "iceland/islandsdem-v1.0-10m", IS_CRS, 10.0, 5000,
                        IS_DEM_URL, extent=IS_DEM_EXTENT, year=2021, bytes_per_tile=5e5, credit=IS_DEM_CREDIT)

# The aerial basemap "Grunnkort - Loftmynd" (25 cm or better, a mosaic updated every year; not yet the whole
# country) from the institute's mapcache: a WMS 1.1.1 serving Web Mercator only (its WMTS matrix set "EPSG:3857"
# starts at 32 768 m/px, not Google's tiling), asked with each tile's Mercator box (OrthoService.wms_crs); it
# answers PNG also when JPEG is asked, transparent where it has no imagery (the sea). CC BY 4.0 (its metadata
# record bd0e7245-2f62-4b2a-82c3-3e6e10b7f9ee on gatt.natt.is), credited in the open data page's pattern
# Detailed tiles for the 20 best groups only, circles too (as swisstopo): the mapcache takes about 1 s a
# tile (R61's circle of 700 m wanted 12 498 tiles, 51 min)
IS_ORTHO = OrthoService(
    "Orthophoto Grunnkort - Loftmynd (Natural Science Institute of Iceland)",
    "https://gis.natt.is/mapcache/web-mercator/wms", "grunnkort-loftmynd", "iceland/grunnkort-loftmynd/live",
    "\"Grunnkort - Loftmynd\" by Náttúrufræðistofnun is licensed under CC BY 4.0", attribution_url=CC_BY[1],
    wms_version="1.1.1", wms_crs="EPSG:3857", detail=20)
IS_ORTHO_LISTING = "Grunnkort - Loftmynd (Natural Science Institute of Iceland), 25 cm"

# The source `iceland` (ArcticDEM 2 m, its gaps from IslandsDEM, then Copernicus): Iceland with its islands
# (Grimsey at 66.55 N, Vestmannaeyjar at 63.3 N, Kolbeinsey left out)
IS_BOXES = (("is", (63.2, 66.6, -24.6, -13.4)),)
IS_WHERE = "Iceland"
# Hafragil, the canyon of the Jokulsa a Fjollum below Dettifoss: basalt walls of up to 100 m
IS_SAMPLE = (65.8239, -16.3934)
IS_NOTE_ARCTICDEM = (arctic_note("IslandsDEM v1.0 10 m (Natural Science Institute of Iceland, CC BY 4.0), then "
                                 "from Copernicus GLO-30")
                     + " Orthophoto: Natural Science Institute of Iceland, CC BY 4.0.")

SOURCES: List[Source] = [
    Source(
        id="iceland", name="ArcticDEM v4.1 mosaic 2 m (Iceland)",
        description="ArcticDEM v4.1 mosaic (Polar Geospatial Center): a 2 m surface model from satellite stereo, "
                    "heights moved from the ellipsoid to EGM2008, resampled once onto UTM; gaps from IslandsDEM "
                    "v1.0 10 m, then Copernicus GLO-30; the Natural Science Institute of Iceland's orthophoto",
        nmt=ARCTIC_DEM_2M, countries=("is",), ortho=IS_ORTHO, credits=(ARCTIC_CREDIT,),
        # Both open: a run of Iceland never takes FABDEM's terms
        fallback="islandsdem10", more_fallbacks=("copernicus",),
        listing=ReadmeRow(IS_WHERE, "ArcticDEM v4.1 mosaic, 2 m (a surface model)", "–", IS_ORTHO_LISTING),
        offline=IS_BOXES, sample=IS_SAMPLE, note=IS_NOTE_ARCTICDEM),
    Source(
        id="islandsdem10", name="IslandsDEM v1.0 (10 m)",
        description="Natural Science Institute of Iceland's IslandsDEM v1.0: elevation model 10 m of all of Iceland "
                    "(ArcticDEM strips, lidar and Copernicus GLO-30 merged), ISN2016 / Lambert 2016 (EPSG:8088), "
                    "heights above sea level",
        # Read on the file's own pixels (edges on whole 10 m), so the working grid is EPSG:8088: no resampling
        nmt=IS_DEM_10M, crs=IS_CRS, ortho=IS_ORTHO, credits=(IS_DEM_CREDIT,),
        # It covers all of Iceland's land; the open Copernicus GLO-30 beyond it (a search reaching the sea)
        fallback="copernicus",
        listing=ReadmeRow(IS_WHERE, "IslandsDEM v1.0, 10 m", "–", IS_ORTHO_LISTING),
        sample=IS_SAMPLE,
        note="Data: Natural Science Institute of Iceland, CC BY 4.0; contains Copernicus WorldDEM-30. IslandsDEM "
             "is a surface model smoothed to 10 m (snow and ice are in it): walls come out less steep than they "
             "are, and only longer lines can be found reliably."),
]
