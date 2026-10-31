"""USGS 3DEP (the USA): the 1 m DEM, Alaska's IfSAR and the 1/3 arc-second DEM."""

from typing import List

from grid import nad83_utm_crs

from ..credit import Credit
from ..source import Listing, OrthoService, Source
from ..layers.blocks import DegreeBlocks
from ..layers.tnm import IfsarBlocks, Usgs1mBlocks

# All 3DEP products are public domain; USGS asks for a credit (copyrights-and-credits page)
USGS_TERMS = ("public domain (USGS)",
              "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits")
USGS_1M_CREDIT = Credit("3DEP 1 m DEM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)
USGS_IFSAR_CREDIT = Credit("3DEP Alaska IfSAR 5 m DTM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)
USGS_13_CREDIT = Credit("3DEP 1/3 arc-second DEM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)
# USGS 3DEP (the USA): blocks read from the files on S3 by HTTP range requests; the 1 m
# DEM per project (newest first), Alaska's IfSAR DTM, and the 1/3″ DEM for the gaps
USGS_3DEP = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation"
USGS_1M = Usgs1mBlocks("3DEP 1 m DEM (terrain)", "Digital Elevation Model (DEM) 1 meter", "dem1m",
                       "usa/3dep-1m", native_res=1.0, block_m=1000, bytes_per_tile=2e6)
USGS_1M.credit = USGS_1M_CREDIT
USGS_IFSAR = IfsarBlocks("3DEP Alaska IfSAR 5 m DTM (terrain)", "Alaska IFSAR 5 meter DEM", "ifsar5m",
                         "usa/ifsar-5m", native_res=5.0, block_m=5000, bytes_per_tile=2e6)
USGS_IFSAR.credit = USGS_IFSAR_CREDIT
USGS_13 = DegreeBlocks("3DEP 1/3 arc-second DEM (terrain)", "usa/3dep-13/live",
                       lambda name: f"{USGS_3DEP}/13/TIFF/current/{name}/USGS_13_{name}.tif",
                       "EPSG:4269", px_per_degree=10800, native_res=10.0, credit=USGS_13_CREDIT)
# NAIP in the map's own tiling; the cached tiles end at zoom 16 (enlarged above it)
USGS_ORTHO = OrthoService("USGS Imagery (USDA NAIP)", None, "", "usa/ortho/live",
                          "USGS The National Map: Orthoimagery (USDA NAIP)",
                          base_url="https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer"
                                   "/tile/{z}/{y}/{x}", base_max_zoom=16)
USA_NOTE = ("USGS 3DEP data, public domain. There is no surface model (trees, buildings) for the USA yet: "
            "lines over trees or buildings are not recognised. The orthophoto ends at zoom 16.")
# Alaska for --source auto (the Aleutians west of 180° are left to the usa source)
ALASKA_BOX = (51.0, 71.5, -180.0, -129.9)


SOURCES: List[Source] = [
    Source(
        id="alaska", name="USGS 3DEP (1 m DEM, Alaska)",
        description="USGS 3DEP (Alaska): 1 m lidar DEM where there is one, newest survey first; gaps from "
                    "the 5 m IfSAR DTM, then the 1/3 arc-second DEM; NAD83 / NAVD88",
        nmt=USGS_1M, countries=("us",), bbox=ALASKA_BOX, local_crs=nad83_utm_crs, ortho=USGS_ORTHO,
        fallback="alaska_ifsar", more_fallbacks=("usgs10m",), instead_without_data="alaska_ifsar",
        credits=(USGS_1M_CREDIT,), note=USA_NOTE,
        listing=Listing("Alaska, where it has 1 m data", "USGS 3DEP 1 m DEM",
                        "–", "USGS Imagery"),
        offline=(("us", ALASKA_BOX),), sample=None),  # no 1 m DEM in Alaska yet (2026-10)
    Source(
        id="alaska_ifsar", name="USGS 3DEP (Alaska IfSAR 5 m)",
        description="USGS 3DEP (Alaska): IfSAR DTM 5 m (radar, 2012-2019), gaps from the 1/3 arc-second DEM",
        nmt=USGS_IFSAR, local_crs=nad83_utm_crs, ortho=USGS_ORTHO, fallback="usgs10m",
        credits=(USGS_IFSAR_CREDIT,),
        note=USA_NOTE + " Alaska's IfSAR is a radar model at 5 m: lines shorter than about 30 m are not reliable.",
        listing=Listing("Alaska", "USGS 3DEP IfSAR DTM, 5 m (radar, 2012–2019)", "–",
                        "USGS Imagery"),
        sample=(58.3093, -134.3890)),
    Source(
        id="usa", name="USGS 3DEP (1 m DEM)",
        description="USGS 3DEP (USA, Puerto Rico, US Virgin Islands): 1 m lidar DEM, newest survey first, "
                    "NAD83 / UTM, NAVD88; gaps from the 1/3 arc-second DEM",
        # 10 km files of 10-450 MB per project: blocks of 1 km read by HTTP range requests
        nmt=USGS_1M, countries=("us", "pr", "vi"), local_crs=nad83_utm_crs, ortho=USGS_ORTHO,
        fallback="usgs10m", credits=(USGS_1M_CREDIT,), note=USA_NOTE,
        listing=Listing("USA, Puerto Rico, US Virgin Islands",
                        "USGS 3DEP 1 m DEM (lidar), newest project first", "–",
                        "USGS Imagery (NAIP, up to zoom 16)"),
        offline=(("us", (24.4, 49.4, -125.0, -66.9)), ("pr", (17.8, 18.6, -67.4, -65.2))),
        sample=(38.5610, -109.5680)),
    Source(
        id="usgs10m", name="USGS 3DEP (1/3 arc-second DEM)",
        description="USGS 3DEP seamless 1/3 arc-second DEM (about 10 m): the USA, Hawaii and the territories",
        nmt=USGS_13, local_crs=nad83_utm_crs, ortho=USGS_ORTHO, credits=(USGS_13_CREDIT,),
        note="The 1/3 arc-second DEM has pixels of about 10 m: lines shorter than about 60 m are not reliable.",
        listing=Listing("USA and its territories", "USGS 3DEP seamless 1/3 arc-second DEM (about 10 m)", "–",
                        "USGS Imagery"),
        sample=(38.5610, -109.5680)),
]
