"""Cyprus: the Department of Lands and Surveys' (DLS) 2019 lidar DTM of 1 m and DSM of 0.5 m, tiles of 2.5 km that
DLS reprojected into ETRS89 degrees, read by range requests and warped back onto blocks of CGRS93 / Cyprus LTM."""

from functools import lru_cache
from typing import FrozenSet, List, Tuple

from rasterio.warp import Resampling

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks

# CGRS93 / Cyprus Local Transverse Mercator (central meridian 33 E, scale factor 0.99995, false easting 200 km,
# false northing -3 500 km): the CRS DLS made the models in, so the working CRS here
CY_LTM = "EPSG:6312"

# DLS's INSPIRE download folder of elevation (an IIS server, no login, no published limits; the dataset
# "Υψομετρία (INSPIRE)" of data.gov.cy, its resource "INSPIRE - Elevation (Download Data Service)"). The 2019 DTM
# ("Pancyprian DTM of Area1 & Area2 (2014 & 2019) (CGRS93_LTM)", 1 m lidar, the files of 2024-12-13) and DSM (the
# same areas, 0.5 m, files of 2024-12-16/22): one GeoTIFF per 2.5 km tile of the LTM grid, ETRS89_<x>_<y>.tif with
# x, y = floor(E / 2500) * 25, floor(N / 2500) * 25 (the tile's lower-left corner in hectometres of LTM). DLS clipped
# each tile in LTM to its square and to the coast, then reprojected it into ETRS89 degrees (EPSG:4258) by nearest
# neighbour ("ProjectRaster", NO_VERTICAL), each file on a grid of its own (square pixels of 9.94e-06 to 1.005e-05
# degrees, about 0.91 x 1.11 m; the DSM's half that): LZW, 128 px tiles, nodata -3.4028e38 (the sea and outside
# the square), centimetres, the directory at the end of the file (one request more than a COG). Only the
# government-controlled area: a tile of the north answers 404 (the tables below avoid asking). The heights are
# above the sea (no vertical datum named; the shore at 0.01 m): checked against Copernicus with
# tools/check_source.py.
CY_DATA = "https://eservices.dls.moi.gov.cy/inspire_downloads/EL/rasters"

# Each tile is read onto blocks of 1.25 km of LTM on whole metres (a quarter of a tile, inside it: no block needs a
# second file) through GDAL's warper (Windows(warp=)): the DTM by nearest from its ~0.91 x 1.11 m pixels onto 1 m
# (a second resampling after DLS's: on a wall about 5 % of the north-south steps between rows come out zero and as
# many doubled, measured at Kakopetria on 2026-11-15; bilinear would smooth them, and the project keeps data of
# the grid's resolution by nearest), the DSM by average from 0.5 m. Along a few tiles' edges a row of 1 m pixels
# falls in neither file (DLS's clip by pixel centre: 238 px of tile 1900_3725's southern edge, which its southern
# neighbour lacks too); those go to the gap filler.
CY_BLOCK_M = 1250
CY_TILE_M = 2500


def _cells(text: str) -> FrozenSet[Tuple[int, int]]:
    """The tiles (x, y) of a table of runs "<y>:<x0>-<x1>,<x2> ..." (x, y in hectometres, steps of 25)."""
    found = set()
    for row in text.split():
        y, runs = row.split(":")
        for run in runs.split(","):
            first, _, last = run.partition("-")
            found.update((x, int(y)) for x in range(int(first), int(last or first) + 1, 25))
    return frozenset(found)


@lru_cache(maxsize=None)
def cy_tiles(model: str) -> FrozenSet[Tuple[int, int]]:
    """The tiles (x, y) DLS publishes of a model ("DTM" or "DSM")."""
    return _cells(CY_DTM_TILES if model == "DTM" else CY_DSM_TILES)


def cy_files(model: str):
    """files(i, j) of FileBlocks: the tile under block (i, j) of CY_BLOCK_M, if DLS has it."""
    def files(i: int, j: int):
        x, y = (i * CY_BLOCK_M // CY_TILE_M) * 25, (j * CY_BLOCK_M // CY_TILE_M) * 25
        if (x, y) not in cy_tiles(model):
            return []
        name = f"ETRS89_{x}_{y}"
        return [(name, f"{CY_DATA}/2019_{model}/{name}.tif", 2019)]
    return files


# The tiles' extent in LTM (x 1325-2975, y 3250-3950): outside it no block asks anything
CY_EXTENT = (132_500.0, 325_000.0, 300_000.0, 397_500.0)
CY_DTM = FileBlocks("DLS DTM 2019 1 m (terrain)", "cyprus/dtm/2019", CY_LTM, 1.0, CY_BLOCK_M, cy_files("DTM"),
                    extent=CY_EXTENT, year=2019, bytes_per_tile=3.5e6, warp=Resampling.nearest)
CY_DSM = FileBlocks("DLS DSM 2019 0.5 m averaged to 1 m (trees, buildings)", "cyprus/dsm/2019", CY_LTM, 1.0,
                    CY_BLOCK_M, cy_files("DSM"), extent=CY_EXTENT, year=2019, bytes_per_tile=11.5e6,
                    warp=Resampling.average)

# data.gov.cy names the dataset's licence "Creative Commons Attribution 4.0 International (CC BY 4.0)" (the dataset
# page, modified 16/03/2026, read 2026-11-15); DLS publishes no wording of its own (asked by mail): the provider,
# the dataset and the licence
CY_DATASET = "https://www.data.gov.cy/el/dataset/ypsometria-inspire"
CY_CREDIT = Credit("Elevation (INSPIRE) 2019 DTM 1 m / DSM 0.5 m (DLS, Cyprus)",
                   "Department of Lands and Surveys, Cyprus (DLS), Elevation (INSPIRE) 2019, CC BY 4.0", *CC_BY,
                   notice=f"Dataset: {CY_DATASET} (INSPIRE - Elevation, Download Data Service).")

# The island's government-controlled area with the Sovereign Base Areas (which have files); the north, inside the
# box too, has none: a search there finds every tile missing and gets the 30 m fallback
CY_BOX = (34.55, 35.20, 32.25, 34.10)

SOURCES: List[Source] = [
    Source(
        id="cyprus", name="DLS DTM 2019 1 m (Cyprus)",
        description="Department of Lands and Surveys (DLS): lidar DTM 1 m and DSM 0.5 m of 2014/2019, tiles DLS "
                    "reprojected into ETRS89 degrees, warped back onto CGRS93 / Cyprus LTM",
        nmt=CY_DTM, nmpt=CY_DSM, countries=("cy",), crs=CY_LTM, credits=(CY_CREDIT,),
        listing=ReadmeRow("Cyprus (government-controlled area)", "DLS DTM 2019, 1 m (resampled twice)",
                          "DLS DSM 2019, 0.5 m"),
        offline=(("cy", CY_BOX),), sample=(34.9850, 32.9000),  # Kakopetria, Troodos
        note="Data: Department of Lands and Surveys, Cyprus (DLS), CC BY 4.0. DLS publishes its 1 m models "
             "reprojected into degrees by nearest neighbour; read back onto a 1 m grid, some steps on walls are a "
             "pixel off. The north has no data: 30 m data there.",
        coverage=Coverage(provider="DLS", added="2026-11-15", survey="2014–2019")),
]

# The tiles of each model in the folder listings of 2019_DTM and 2019_DSM (read 2026-11-15: 1 070 and 1 068 files),
# as runs "<y>:<x0>-<x1>,<x2> ..." in steps of 25; the DTM's ETRS89_2000_3250 (one pixel, 4 453 bytes) left out.
# The models are frozen (files of 2024-12); a tile outside a table is missing without a request
CY_DTM_TILES = (
    "3250:1925-1975,2025 3275:1925-2025 3300:1925-2000 3325:1700-1725,1900-2000 3350:1625-2025 3375:1600-2075 "
    "3400:1500-2225 3425:1475-2325 3450:1450-2375 3475:1425-2450 3500:1425-2475 3525:1425-2550 3550:1425-2550 "
    "3575:1375-2575 3600:1375-2575 3625:1350-2575 3650:1350-2575 3675:1350-2600,2750-2800 "
    "3700:1350-2875,2925-2975 3725:1350-2975 3750:1325-2975 3775:1325-2400,2450-2950 "
    "3800:1325-1400,1475-2500,2725-2925 3825:1325-1375,1500-2425 3850:1325-1350,1525-1825,1875-2425 "
    "3875:1550-1800,1975-2375 3900:1550-1750,1975-2375 3925:1575-1725,2100-2375 "
    "3950:1625-1700,2125-2200,2325-2350 "
)
CY_DSM_TILES = (
    "3250:1925-2025 3275:1925-2000 3300:1925-2000 3325:1700-1725,1900-2000 3350:1650-2025 3375:1600-2075 "
    "3400:1500-2275 3425:1475-2325 3450:1450-2375 3475:1450-2450 3500:1425-2475 3525:1425-2550 3550:1425-2550 "
    "3575:1375-2575 3600:1375-2575 3625:1350-2575 3650:1375-2575 3675:1350-2600,2750-2800 "
    "3700:1350-2875,2925-2975 3725:1350-2975 3750:1325-2975 3775:1325-2400,2450-2950 "
    "3800:1325-1400,1475-2500,2725-2925 3825:1325-1375,1500-2425 3850:1325-1350,1525-1825,1875-2425 "
    "3875:1550-1800,1975-2375 3900:1550-1750,1975-2375 3925:1575-1725,2100-2375 "
    "3950:1625-1700,2125-2200,2325-2350 "
)
