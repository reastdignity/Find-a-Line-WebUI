"""Australia: Tasmania (the State's Tasmania 2 metre DEM, one cloud-optimized GeoTIFF read in blocks) and Queensland
(the State's DEM time series ImageServer: its lidar projects, newest first, and Geoscience Australia's DEM-H for
the gaps)."""

from typing import List

from ..credit import Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks
from ..layers.imageserver import ImageServerTiles

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


# --- Queensland ---
# The State's "Queensland Elevation DEM Public Time Series Service" (ArcGIS Server 11.5, an ImageServer of 536
# rasters, one per project): 1 m and 0.5 m lidar DTMs of the Coordinated LiDAR Program (product_type 8, with a
# few photogrammetric "ODEM" DEMs of 5-25 m and a 3 m bathymetry of the same type, left out by res_value),
# Geoscience Australia's DEM-H (product_type 1), bathymetry (19). Every raster is stored in Web Mercator
# (EPSG:3857) at 1.13-1.14 m (about 1 m on the ground; GDA2020 projects moved onto GDA94 by the service's
# seven-parameter transformation), so its own pixels lie in no metric CRS: the tiles are asked for in GDA94 /
# MGA of the working grid at 1 m, nearest neighbour (deterministic: a box equals its halves; 0.67 MB and about
# 4 s for 400 m at Tibrogargan, wave 0 of 2026-11-02), i.e. the data are resampled once by the service. No key,
# no published request limits (QSpatial's "Elevation and LiDAR" page and the services, 2026-11-02): four
# connections at once as a courtesy (net.HOST_SLOTS_OF).
QLD_SERVICES = "https://spatial-img.information.qld.gov.au/arcgis/rest/services"
QLD_DEM_URL = f"{QLD_SERVICES}/Elevation/DEM_TimeSeries_AllUsers/ImageServer"
# Queensland spans MGA zones 54-56 (138-156° E): the working grid is the zone of the centre (mga_crs) and the
# tiles are asked for in it; zone 56 (south-east Queensland, the sample) is the default
QLD_ZONES = ("EPSG:28356", "EPSG:28355", "EPSG:28354")


def mga_crs(lat: float, lon: float) -> str:
    """GDA94 / MGA zone of a point in Queensland (54-56; a point outside them takes the nearest), e.g. EPSG:28356."""
    zone = min(56, max(54, int((lon + 180) // 6) + 1))
    return f"EPSG:{28300 + zone}"


# The lidar DTMs newest first: the service's own order (allowedMosaicMethods "ByAttribute" on ZOrder only; the
# newest project of a place has the smallest ZOrder, 1-2, older ones 3-7: a handful of exceptions, e.g. Surat
# 2012 above Surat 2023, are the provider's choice and kept). Within a project the pixels the survey did not
# cover are -9999 (noData), so an older project shows through.
QLD_LIDAR_RULE = {"mosaicMethod": "esriMosaicAttribute", "sortField": "ZOrder", "sortValue": "0", "ascending": True,
                  "where": "product_type = 8 AND res_value <= 1"}
QLD_DEMH_RULE = {"mosaicMethod": "esriMosaicAttribute", "sortField": "ZOrder", "sortValue": "0", "ascending": True,
                 "where": "product_type = 1"}
# 1 km tiles of 1 m; the DEM-H (1 second, about 30 m) in 15 km tiles of 30 m
QLD_LIDAR = ImageServerTiles("Queensland lidar DEM 1 m (terrain)", QLD_DEM_URL, QLD_ZONES[0],
                             "queensland/dem-lidar/live", 1.0, tile_px=1000, mosaic_rule=QLD_LIDAR_RULE,
                             zones=QLD_ZONES)
QLD_DEMH = ImageServerTiles("Queensland DEM-H 30 m (terrain)", QLD_DEM_URL, QLD_ZONES[0],
                            "queensland/dem-h/live", 30.0, tile_px=500, mosaic_rule=QLD_DEMH_RULE, zones=QLD_ZONES)

# The terms, as the service's item info (info/iteminfo, "licenseInfo") stated them on 2026-11-02: "The use of
# this service and elevation data contained is available publically under Creative Commons
# Attribution-Share-Alike licence (CC BY-SA)" (no version; data.qld.gov.au's record of the same service,
# "Queensland Elevation DEM Public Time Series Service", names Creative Commons Attribution 3.0, CC-BY-3.0); the
# attribution text of its 'Copyright Text' field "must be included on any copies of the licensed data however
# they are altered, reformatted or redisplayed", and an acknowledgement "must also be displayed on any hardcopy
# or digital products based on or containing the supplied data" (both verbatim below). The terms also have the
# user indemnify the State (accepted by the operator on 2026-11-02). Never combined with FABDEM (CC BY-NC-SA,
# which could not be combined with BY-SA): the gaps come from the same service's DEM-H.
QLD_TERMS_URL = f"{QLD_DEM_URL}/info/iteminfo"
# The service's 'Copyright Text' (copyrightText of its description), verbatim as read on 2026-11-02
QLD_COPYRIGHT = ("Includes material © State of Queensland (Department of Natural Resources and Mines, "
                 "Manufacturing, and Regional and Rural Development); © Commonwealth of Australia (Geoscience "
                 "Australia, The Australian Hydrographic Office); © www.deepreef.org 2026")
QLD_ACKNOWLEDGEMENT = ("In consideration of the State of Queensland permitting use of this data you acknowledge and "
                       "agree that the State gives no warranty in relation to the data (including accuracy, "
                       "reliability, completeness, currency or suitability) and accepts no liability (including "
                       "without limitation, liability in negligence) for any loss, damage or costs (including "
                       "consequential damage) relating to any use of the data.")
QLD_LIDAR_CREDIT = Credit("Queensland elevation DEM time series, lidar DTMs (State of Queensland)", QLD_COPYRIGHT,
                          "CC BY-SA", QLD_TERMS_URL, notice=QLD_ACKNOWLEDGEMENT)
QLD_DEMH_CREDIT = Credit("DEM-H 1 second (Geoscience Australia), from the Queensland elevation DEM time series",
                         QLD_COPYRIGHT, "CC BY-SA", QLD_TERMS_URL, notice=QLD_ACKNOWLEDGEMENT)

# The State's latest aerial imagery (Spatial Imagery Subscription Plan; Planet's satellite mosaic where there is
# none) as ArcGIS cache tiles in Web Mercator to level 20, no key; the same terms (CC BY-SA, the acknowledgement)
# and its own 'Copyright Text', verbatim as read on 2026-11-02
QLD_ORTHO_URL = f"{QLD_SERVICES}/Basemaps/LatestStateProgram_AllUsers/ImageServer"
QLD_ORTHO_COPYRIGHT = ("Includes material © State of Queensland (Department of Natural Resources and Mines, "
                       "Manufacturing and Regional and Rural Development); © Planet Labs Netherlands B.V. "
                       "reproduced under licence from Planet and Geoplex, all rights reserved, 2026.")
QLD_ORTHO = OrthoService(
    "Queensland latest State imagery (State of Queensland)", None, "", "queensland/ortho/live",
    f"Queensland imagery, CC BY-SA: {QLD_ORTHO_COPYRIGHT}", attribution_url=f"{QLD_ORTHO_URL}/info/iteminfo",
    base_url=f"{QLD_ORTHO_URL}/tile/{{z}}/{{y}}/{{x}}", base_max_zoom=20)

# Queensland with the Torres Strait islands, in three boxes along the border with New South Wales (29° S to the
# west, the Dumaresq River, then the McPherson Range to Point Danger)
QLD_BOXES = (("au-qld", (-29.00, -9.10, 138.00, 151.00)), ("au-qld", (-28.60, -9.10, 151.00, 152.50)),
             ("au-qld", (-28.20, -9.10, 152.50, 153.60)))
QLD_NOTE = ("Data: State of Queensland, CC BY-SA. Results derived from Queensland's elevation data are shared "
            "under CC BY-SA where they are an adaptation of it. The lidar DTMs of the State's projects (2006-2024), "
            "newest first, are stored by the service in Web Mercator and resampled once onto the working grid "
            "(nearest neighbour); where no project covers the area, the gaps are filled from DEM-H (30 m). No "
            "surface model: trees and buildings are not in the data.")


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
        note=TAS_NOTE,
        # Partial: about a third of the State has no lidar and is interpolated from contours
        coverage=Coverage(provider="Tasmanian Government", added="2026-11-02", partial=True, survey="2008–2020")),
    Source(
        id="queensland", name="Queensland elevation DEM time series (lidar 1 m)",
        description="State of Queensland: the lidar DTMs of its DEM time series service (projects of 2006-2024, "
                    "newest first, 1 m), resampled by the service from Web Mercator to GDA94 / MGA of the place "
                    "(zones 54-56), AHD heights; gaps from DEM-H 30 m of the same service",
        nmt=QLD_LIDAR, countries=("au",), regions=("au-qld",), local_crs=mga_crs, ortho=QLD_ORTHO,
        credits=(QLD_LIDAR_CREDIT,), fallback="queensland_demh",
        listing=ReadmeRow("Queensland (AU), where it has lidar",
                          "State of Queensland DEM time series: lidar DTMs 1 m (2006-2024, ImageServer)", "–",
                          "Queensland latest State imagery"),
        offline=QLD_BOXES, sample=(-26.927, 152.947),
        note=QLD_NOTE,
        # Partial: lidar in parts of the State, DEM-H 30 m elsewhere
        coverage=Coverage(provider="State of Queensland", added="2026-11-03", partial=True, rest=(30.0,),
                          survey="2006–2024")),
    Source(
        id="queensland_demh", name="DEM-H 30 m (Geoscience Australia, Queensland's service)",
        description="Geoscience Australia's DEM-H (1 second SRTM, hydrologically enforced, 30 m) from the State of "
                    "Queensland's DEM time series service, GDA94 / MGA of the place",
        # Only the gaps of queensland's lidar: no fallback of its own (FABDEM's BY-NC-SA cannot be combined
        # with BY-SA)
        nmt=QLD_DEMH, local_crs=mga_crs, credits=(QLD_DEMH_CREDIT,), fallback=None,
        listing=ReadmeRow("Queensland (AU)", "Geoscience Australia DEM-H 30 m (from Queensland's service)"),
        sample=(-26.927, 152.947),
        note="Data: Geoscience Australia and the State of Queensland, CC BY-SA. DEM-H is SRTM of 2000 (30 m): only "
             "long lines can be found, its cliffs are smoothed."),
]
