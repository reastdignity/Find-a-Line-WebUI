"""The Arctic on ArcticDEM v4.1 (Polar Geospatial Center): Greenland, Svalbard and Jan Mayen, Nunavut. Its 2 m mosaic
is read in blocks from the COGs of PGC's bucket on AWS (no key), its heights moved from the ellipsoid to EGM2008."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import OrthoService, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks
from ..vertical import EGM2008

# ArcticDEM v4.1 mosaic (PGC, August 2023; strips of 2007-2022 registered and merged), the current release
# (pgc.umn.edu/data/arcticdem and its news, read 2026-11-02: no v5 announced, nothing closing). AWS Open Data
# bucket pgc-opendata-dems (us-west-2), no published request limits: the default HOST_SLOTS. One COG per 50 km
# subtile of a 100 km tile of EPSG:3413 (WGS 84 / NSIDC Sea Ice Polar Stereographic North), named
# <RR>_<CC>_<ys>_<xs>_2m_v4.1_dem.tif with RR = floor((y + 4 100 000) / 100 km), CC likewise from x, ys/xs = 1 + the
# 50 km half (checked against PGC's STAC items, 2026-11-02); 25 100 px each (100 m of overlap on every side),
# float32, LZW, 512 px tiles, nodata -9999, pixel edges on even metres from 0, 1.28 GB a file: read in windows
# only. A subtile not in the set answers 404 (its blocks are missing). Heights above the WGS84 ellipsoid (the sea
# lies at the geoid: 27 m at Uummannaq, 32 m at Longyearbyen), multiples of 1/128 m; a photogrammetric surface
# (snow, ice, the few trees and buildings in it), with voids on the steepest faces (Mt Thor's west face). The
# blocks are cached as heights above EGM2008 (sources/vertical.py), in a static folder (an edition).
ARCTIC_CRS = "EPSG:3413"
ARCTIC_URL = "https://pgc-opendata-dems.s3.us-west-2.amazonaws.com/arcticdem/mosaics/v4.1/2m"
ARCTIC_OFFSET = 4100000      # metres from the tiles' origin to the projection's
ARCTIC_TILE_M = 100000
ARCTIC_SUBTILE_M = 50000
ARCTIC_TILES = 82            # rows and columns of 100 km tiles (-4 100 km to +4 100 km)
ARCTIC_EXTENT = (-ARCTIC_OFFSET, -ARCTIC_OFFSET, ARCTIC_OFFSET, ARCTIC_OFFSET)
# Blocks of 2 km (1000 x 1000 px, about four of the files' 512 px tiles, 2-3 MB cached): 25 to a subtile, so every
# block lies inside one subtile's core
ARCTIC_BLOCK_M = 2000

# PGC's acknowledgement policy (https://www.pgc.umn.edu/guides/user-services/acknowledgement-policy/, 2026-02-17,
# read 2026-11-02): "users agree to cite PGC and its sponsorship by the NSF", the acknowledgement verbatim and the
# dataset's citation; CC BY 4.0 (the STAC collections and the AWS registry), so "processed" for the changes
ARCTIC_ACKNOWLEDGEMENT = ("DEMs provided by the Polar Geospatial Center under NSF-OPP awards 1043681, 1559691, "
                          "1542736, 1810976, and 2129685.")
ARCTIC_CITATION = ("Porter, C., Howat, I., Noh, M.J., et al., 2023, \"ArcticDEM - Mosaics, Version 4.1\", "
                   "https://doi.org/10.7910/DVN/3VDC4W, Harvard Dataverse, V1.")
ARCTIC_CREDIT = Credit("ArcticDEM v4.1 mosaic 2 m (Polar Geospatial Center)",
                       "ArcticDEM, Polar Geospatial Center, CC BY 4.0, processed", *CC_BY,
                       notice=f"{ARCTIC_ACKNOWLEDGEMENT} {ARCTIC_CITATION} Heights moved from the WGS84 ellipsoid "
                              f"to EGM2008 with PROJ's grid us_nga_egm08_25.tif, derived from work by NGA "
                              f"(public domain).")


def arcticdem_files(block_m: float):
    """The subtile of a block of block_m (a divisor of 50 km) of the 2 m mosaic, from the block's position; none
    outside the tiles. The survey years are not in the files (0)."""
    def files(i: int, j: int):
        x, y = i * block_m + ARCTIC_OFFSET, j * block_m + ARCTIC_OFFSET  # the block's lower-left corner
        row, col = int(y // ARCTIC_TILE_M), int(x // ARCTIC_TILE_M)
        if not (0 <= row < ARCTIC_TILES and 0 <= col < ARCTIC_TILES):
            return []
        ys = 1 + int(y % ARCTIC_TILE_M // ARCTIC_SUBTILE_M)
        xs = 1 + int(x % ARCTIC_TILE_M // ARCTIC_SUBTILE_M)
        tile = f"{row:02d}_{col:02d}"
        name = f"{tile}_{ys}_{xs}_2m_v4.1_dem.tif"
        return [(name, f"{ARCTIC_URL}/{tile}/{name}", 0)]
    return files


ARCTIC_DEM_2M = FileBlocks("ArcticDEM v4.1 mosaic 2 m (surface, EGM2008)", "arcticdem/mosaic-v4.1-2m-egm08",
                           ARCTIC_CRS, 2.0, ARCTIC_BLOCK_M, arcticdem_files(ARCTIC_BLOCK_M), extent=ARCTIC_EXTENT,
                           bytes_per_tile=2.5e6, credit=ARCTIC_CREDIT, geoid=EGM2008)

def arctic_note(filled_from: str) -> str:
    """The note of a source on ArcticDEM whose voids are filled from filled_from."""
    return ("Data: ArcticDEM, Polar Geospatial Center, CC BY 4.0 (processed). " + ARCTIC_ACKNOWLEDGEMENT
            + " ArcticDEM is a surface model from satellite stereo images: snow and ice, the few trees and the "
              "buildings are part of it (there is no terrain model without them, so the check of trees is "
              f"off), and the steepest faces have voids, filled from {filled_from}. Its heights above the "
              "ellipsoid are moved to the EGM2008 geoid (heights above the sea).")


ARCTIC_NOTE = arctic_note("30 m data")
ARCTIC_NO_ORTHO = "– (no open orthophoto service)"

# Greenland in boxes along the Davis Strait, Baffin Bay and the Nares Strait in the west (the first box holding a
# point wins: these come before Canada's, whose box (60-83.2° N, -141° to -61° W) holds north-western Greenland)
# and the Denmark Strait in the east (Iceland, west to 24.6° W, stays out of them)
GL_BOXES = (("gl", (59.7, 67.5, -58.0, -30.0)), ("gl", (67.5, 73.0, -58.0, -18.0)),
            ("gl", (73.0, 76.0, -70.0, -15.0)), ("gl", (76.0, 79.0, -73.3, -11.3)),
            ("gl", (79.0, 80.5, -68.0, -11.3)), ("gl", (80.5, 83.7, -62.0, -11.3)))

# Norsk Polarinstitutt's orthophoto of Svalbard as ArcGIS cache tiles in Web Mercator (levels 0-17, JPEG, no
# key). Its terms (https://geodata.npolar.no/bruksvilkar, read 2026-11-02): "the free map products are licensed
# under ... CC BY 4.0, except the service NP_Ortofoto_Svalbard_WMTS_25833, which is licensed under ... CC BY-NC
# 4.0" (the 25833 service is not used here; this 3857 one is "derived from" it but not excepted); "© Norwegian
# Polar Institute. When practicable, a link to the Norwegian Polar Institute website should be provided".
SV_ORTHO = OrthoService(
    "Svalbard orthophoto (Norwegian Polar Institute)", None, "", "svalbard/ortho/npolar-3857",
    "© Norwegian Polar Institute, CC BY 4.0", attribution_url="https://www.npolar.no/",
    base_url="https://geodata.npolar.no/arcgis/rest/services/Basisdata/NP_Ortofoto_Svalbard_WMTS_3857/MapServer"
             "/tile/{z}/{y}/{x}", base_max_zoom=17)
# Svalbard (NO-21) and Jan Mayen (NO-22): region boxes (they give Norway and the region offline)
SV_BOXES = (("no-21", (74.3, 80.9, 10.0, 34.0)), ("no-22", (70.8, 71.2, -9.1, -7.9)))

# Nunavut in boxes inside Canada's (they come first): the islands and Kivalliq east of 110° W north of 64° N
# (Victoria and Melville Islands are split at 110° W), Kivalliq and the Hudson Bay south of 64° N east of the
# boundary at 102° W and west of Nunavik, southern Baffin and Hudson Strait east of Nunavik's tip (62.6° N).
# Greenland's boxes come before them
NU_BOXES = (("ca-nu", (64.0, 83.2, -110.0, -61.0)), ("ca-nu", (60.0, 64.0, -102.0, -79.5)),
            ("ca-nu", (62.6, 64.0, -79.5, -61.0)))

SOURCES: List[Source] = [
    Source(
        id="greenland", name="ArcticDEM v4.1 mosaic 2 m (Greenland)",
        description="ArcticDEM v4.1 mosaic (Polar Geospatial Center): a 2 m surface model from satellite stereo, "
                    "heights moved from the ellipsoid to EGM2008, resampled once onto UTM; gaps from Copernicus "
                    "GLO-30",
        nmt=ARCTIC_DEM_2M, countries=("gl",), credits=(ARCTIC_CREDIT,), fallback="copernicus",
        listing=ReadmeRow("Greenland", "ArcticDEM v4.1 mosaic, 2 m (a surface model)", "–", ARCTIC_NO_ORTHO),
        offline=GL_BOXES, sample=(60.3786, -44.5502),  # Tasermiut fjord (R58)
        note=ARCTIC_NOTE + " No open orthophoto of Greenland: the map shows its own base layers."),
    Source(
        id="svalbard", name="ArcticDEM v4.1 mosaic 2 m (Svalbard, Jan Mayen)",
        description="ArcticDEM v4.1 mosaic (Polar Geospatial Center): a 2 m surface model from satellite stereo, "
                    "heights moved from the ellipsoid to EGM2008, resampled once onto UTM; gaps from Copernicus "
                    "GLO-30; Norwegian Polar Institute's orthophoto",
        nmt=ARCTIC_DEM_2M, countries=("no",), regions=("no-21", "no-22"), ortho=SV_ORTHO, credits=(ARCTIC_CREDIT,),
        fallback="copernicus",
        listing=ReadmeRow("Svalbard and Jan Mayen (NO)", "ArcticDEM v4.1 mosaic, 2 m (a surface model)", "–",
                          "Norwegian Polar Institute orthophoto (Svalbard)"),
        offline=SV_BOXES, sample=(78.1913, 15.1801),  # near Longyearbyen (R59)
        note=ARCTIC_NOTE),
    Source(
        id="nunavut", name="ArcticDEM v4.1 mosaic 2 m (Nunavut)",
        description="ArcticDEM v4.1 mosaic (Polar Geospatial Center): a 2 m surface model from satellite stereo, "
                    "heights moved from the ellipsoid to EGM2008 (within centimetres of CGVD2013 there), resampled "
                    "once onto UTM; gaps from NRCan's MRDEM-30",
        nmt=ARCTIC_DEM_2M, countries=("ca",), regions=("ca-nu",), credits=(ARCTIC_CREDIT,), fallback="mrdem30",
        neighbours=("canada",),
        listing=ReadmeRow("Nunavut (CA)", "ArcticDEM v4.1 mosaic, 2 m (a surface model)", "–",
                          "– (no national orthophoto service)"),
        offline=NU_BOXES, sample=(70.7175, -71.4268),  # Sam Ford fjord (R60)
        note=ARCTIC_NOTE + " NRCan's lidar around the communities is not used (the source canada, NRCan's "
                           "HRDEM mosaic, has it); the map shows its own base layers."),
]
