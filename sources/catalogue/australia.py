"""Australia: Tasmania (the State's Tasmania 2 metre DEM, one cloud-optimized GeoTIFF read in blocks)."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks

# GDA94 / MGA zone 55, the CRS of the file: zone 55 spans 144-150° E, so King Island (143.8-144.2° E) lies just
# west of it; the scale error stays within about -0.04 % (the zone's centre, 147° E) and +0.04 % (King Island)
TAS_CRS = "EPSG:28355"

# The Tasmania 2 metre Digital Elevation Model of 14-08-2021 (NRE Tasmania / theLIST; data.gov.au dc463cd1-...,
# theLIST metadata 71619d6d-bb60-490c-a461-504e2b37e2f3): officially an ELVIS order only. Alex Leith put a
# verbatim copy on Source Cooperative (its README: "accessed zipped data on the 29th of November, 2023"; CC BY 3.0
# AU allows it): one cloud-optimized GeoTIFF, 457 618 x 284 791 px of 2 m (95 GB), float32, LZW, 512 px tiles,
# overviews 2-1024, nodata -FLT_MAX (the sea), AHD heights; read here in windows by HTTP range requests, never
# whole. A static copy: no maintenance promised, so the folder is dated (the DEM's own date).
TAS_DEM_URL = ("https://data.source.coop/alexgleith/tasmania-dem-2m/Tasmania_Statewide_2m_DEM_14-08-2021.tif")
TAS_COPY_PAGE = "https://source.coop/alexgleith/tasmania-dem-2m"
# The file's pixel edges lie off whole metres: its corner is (-30597.398268200195, 5687852.900000001), so the
# edges are on this origin + multiples of 2 m (blocks and the working grid both)
TAS_ORIGIN = (-30597.398268200195 % 2, 5687852.900000001 % 2)
TAS_EXTENT = (-30597.398268200195, 5118270.900000001, 884638.6017317998, 5687852.900000001)  # the file's bounds
# "with attribution to 'The LIST ©State of Tasmania'" (theLIST's metadata, data.gov.au and the copy's README)
TAS_CREDIT = Credit("Tasmania 2 metre DEM, 2021 (The LIST, State of Tasmania)", "The LIST © State of Tasmania",
                    "CC BY 3.0 AU", "https://creativecommons.org/licenses/by/3.0/au/",
                    notice="Tasmania 2 metre Digital Elevation Model (14-08-2021), The LIST © State of Tasmania, "
                           "licensed under the Creative Commons Attribution 3.0 Australia licence. Read from the "
                           f"verbatim copy published by Alex Leith on Source Cooperative ({TAS_COPY_PAGE}).")

# Blocks of 2 km (1000 x 1000 px of the file's 512 px tiles, which lie off them: 4-9 tiles a block, 2.2 tiles
# read per km² on average against 3.9 for 1 km blocks): about 2 MB each in the cache, 9 blocks read in 10 s with
# four at once (Mount Wellington, 2026-11-02)
TAS_BLOCK_M = 2000
TAS_DEM = FileBlocks("Tasmania 2 m DEM (terrain)", "tasmania/dem2m/20210814", TAS_CRS, 2.0, TAS_BLOCK_M,
                     TAS_DEM_URL, origin=TAS_ORIGIN, extent=TAS_EXTENT, year=2021, bytes_per_tile=2e6)

# theLIST's orthophoto compilation (the newest aerial photos of the State and councils, up to 0.3 m at zoom 19)
# as ArcGIS cache tiles in Web Mercator, no key. The LIST Web Services Terms and Conditions (December 2014,
# http://listdata.thelist.tas.gov.au/public/LISTWebServicesTermsConditions.pdf, read 2026-11-02) give no
# numbers and leave the licence to "the Copyright Text section of the relevant service": "Creative Commons
# BY-NC-ND 3.0 AU © State of Tasmania" (read 2026-11-02). So the tiles are shown unchanged, credited, on a
# non-commercial site, never composited into other imagery. Tiles without imagery (the sea) come as PNG.
TAS_ORTHO = OrthoService(
    "theLIST orthophoto (State of Tasmania)", None, "", "tasmania/ortho/live",
    "theLIST orthophoto: Creative Commons BY-NC-ND 3.0 AU © State of Tasmania",
    attribution_url="https://creativecommons.org/licenses/by-nc-nd/3.0/au/",
    base_url="https://services.thelist.tas.gov.au/arcgis/rest/services/Basemaps/Orthophoto/MapServer/tile"
             "/{z}/{y}/{x}", base_max_zoom=19)

# Tasmania with King Island and the Furneaux Group (Macquarie Island is not in the file)
TAS_BOX = (-43.70, -39.45, 143.75, 148.55)
TAS_NOTE = ("Data: The LIST © State of Tasmania, CC BY 3.0 AU, read from a copy on Source Cooperative. The 2 m "
            "DEM of 2021 joins 178 lidar surveys of 2008-2020; about a third of the State has none and is "
            "interpolated from 10 m contours there, which smooths real cliffs and can make false ones (theLIST's "
            "layer \"LiDAR Coverage Index - All Projects\" shows where lidar was flown). No surface model: trees "
            "and buildings are not in the data.")


SOURCES: List[Source] = [
    Source(
        id="tasmania", name="Tasmania 2 metre DEM (The LIST)",
        description="State of Tasmania (The LIST): Tasmania 2 metre DEM of 2021, from lidar of 2008-2020 or, "
                    "where there is none, from contours; GDA94 / MGA zone 55, AHD heights",
        # The file read in blocks on its own pixels, so the working grid is MGA zone 55 with its pixel edges
        nmt=TAS_DEM, countries=("au",), regions=("au-tas",), crs=TAS_CRS, grid_origin=TAS_ORIGIN,
        ortho=TAS_ORTHO, credits=(TAS_CREDIT,),
        listing=ReadmeRow("Tasmania (AU)", "Tasmania 2 metre DEM (2021; lidar 2008-2020, elsewhere contours)",
                          "–", "theLIST orthophoto"),
        offline=(("au-tas", TAS_BOX),), sample=(-42.893, 147.237),
        note=TAS_NOTE),
]
