"""
Elevation data sources.

A source provides a terrain model (NMT/DTM, ground only) and optionally a surface
model (NMPT/DSM, with trees and buildings), plus optionally an orthophoto service.
Every layer is downloaded in tiles into its own folder of the cache, so switching
between sources never downloads again what is already there.

Kinds of layers:
- WcsTiles: square tiles from an OGC WCS 2.0 service on a fixed grid in the
  service's coordinate system (Malta, IGN Spain).
- IndexedTiles: files found through an index, newest survey per sheet or tile:
  SheetTiles (map sheets from a WFS sheet index, geoportal.gov.pl) and StacTiles
  (tiles of a STAC collection, swisstopo).
- GridTiles: our own tiles on a fixed grid (Slovakia, made by tools/sk_tiles.py), from
  a local mirror (FINDALINE_MIRROR) or, once uploaded, from Hugging Face.
- TnmBlocks: blocks of the big files of The National Map (USGS 3DEP, the USA), found
  through its API and read by HTTP range requests, composed newest survey first; and
  DegreeBlocks: blocks of 1° files at a fixed URL (3DEP's 1/3″ DEM).
- DegreeTiles: 1°×1° GeoTIFF tiles in WGS84 (Copernicus DEM, FABDEM) and
  OpenTopography's global DEM API (NASADEM).
- FileLayer: a local raster file (GeoTIFF, ASC...), e.g. NASADEM from OpenTopography.

To add a national source, add a Source with WcsTiles layers to SOURCES (see the
Malta entries) and its country code to `countries`; see README, "Data sources".
The layers of a search are downloaded together (download_layers: one pool for all their
tiles). Searches of one data folder may download at once: each tile under its own lock
(tile_lock; the second search waits, then finds it cached) and at most HOST_SLOTS tiles
from one host at a time across all of them (host_slot), both lock files in cache/locks.

Every source and every layer used for filling (the water mask, the gap filling
source) names its licence and the notice its data must be shown with (`Credit`):
each run records them for the layers it used (run.json, the map, ATTRIBUTION.txt).
"""

import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio as rio
import requests
from affine import Affine
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

import cache
import osm
from grid import Grid, nad83_utm_crs
from progress import progress

from . import credit, layer, layers, net, source
from .layers import blocks, degree, files, gridtiles, indexed, sheets, stac, tnm, wcs
from .net import (HOST_SLOTS, HOST_SLOTS_OF, LOCK_WAIT_S, RETRIES, TILE_LOCKS, _gdal_http, _locks, _part, _remote,
                  host_slot, tile_lock)
from .credit import CC_BY, Credit, OSM_CREDIT
from .layer import Fetched, Layer, VALID_MIN, _clean, _hemi, _write_tile, download_layers
from .source import MIN_RESOLUTION, OrthoService, Source
from .layers.wcs import WcsTiles, _extract_multipart
from .layers.gridtiles import GridTiles, MIRROR_ENV, grid_tile_name
from .layers.degree import DegreeTiles, OpenTopographyTiles
from .layers.indexed import IndexedTiles, Sheet, _sheet_order
from .layers.sheets import SHEET_CRS, SHEET_FORMATS, SheetTiles, _xyz_grid
from .layers.stac import StacTiles
from .layers.blocks import DegreeBlocks, _read_block, _read_window, _same_crs
from .layers.tnm import Block, IfsarBlocks, TNM_API, TnmBlocks, Usgs1mBlocks, _survey_year, _utm_zone_of
from .layers.files import FileLayer


# Threads of GDAL's reprojection of a mosaic (the same values with any number: checked on FABDEM over
# a 7600 px grid, 2.6 s on one thread, 0.8 s on 4, 0.5 s on 8): the cores numba may use
# (NUMBA_NUM_THREADS, WORKER_CPUS in the container), at most 8
WARP_THREADS = max(1, min(8, int(os.environ.get("NUMBA_NUM_THREADS") or os.cpu_count() or 1)))


# Checked 2026-10-27 (docs/roadmap.md, "Before going public")
COPERNICUS_NOTICE = ("produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and "
                     "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
                     "all rights reserved")
COPERNICUS_DISCLAIMER = ("The organisations in charge of the Copernicus programme by law or by delegation do "
                         "not incur any liability for any use of the Copernicus WorldDEM-30.")
COPERNICUS_LICENCE = ("Copernicus DEM licence", "https://docs.sentinel-hub.com/api/latest/static/files/data/dem/"
                                                "resources/license/License-COPDEM-30.pdf")
GUGIK_CREDIT = Credit("NMT / NMPT (GUGiK, Poland)",
                      "Source: Główny Urząd Geodezji i Kartografii (GUGiK), geoportal.gov.pl",
                      "geoportal.gov.pl terms (free use, source stated)",
                      "https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/")
SWISSTOPO_CREDIT = Credit("swissALTI3D / swissSURFACE3D (swisstopo)", "© swisstopo",
                          "swisstopo OGD terms (free use, source stated)",
                          "https://www.swisstopo.admin.ch/en/conditions-geodata")
UGKK_CREDIT = Credit("DMR 5.0 / DMP 1.0 (ÚGKK SR, Slovakia)", "© ÚGKK SR", *CC_BY)
# IGN's form of a credit for a derived work (Orden FOM/2807/2015): "Obra derivada de <product> CC-BY 4.0 ign.es"
IGN_CREDIT = Credit("MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)", "Obra derivada de MDT05 / MDS05 CC-BY 4.0 ign.es",
                    CC_BY[0], "https://www.ign.es/web/en/politica-datos")
MSDI = "https://msdi.data.gov.mt/geonetwork/"
MALTA_CREDITS = {
    2018: Credit("Malta LiDAR 2018 (Planning Authority, MSDI)", "Planning Authority Malta (MSDI), LiDAR 2018",
                 "no conditions on access and use (INSPIRE metadata)", MSDI),
    # The MSDI records were reported as CC BY-NC-ND 4.0, the INSPIRE ones as without conditions
    2012: Credit("Malta LiDAR 2012 (Planning Authority, MSDI)", "Planning Authority Malta (MSDI), LiDAR 2012",
                 "unresolved (CC BY-NC-ND 4.0 or no conditions)", MSDI),
}
COPERNICUS_CREDIT = Credit("Copernicus DEM GLO-30", COPERNICUS_NOTICE[0].upper() + COPERNICUS_NOTICE[1:],
                           *COPERNICUS_LICENCE, notice=COPERNICUS_DISCLAIMER)
WATER_MASK_CREDIT = Credit("Copernicus DEM GLO-30 water body mask", COPERNICUS_CREDIT.attribution,
                           *COPERNICUS_LICENCE, notice=COPERNICUS_DISCLAIMER)
# The record at data.bris.ac.uk states CC BY-NC-SA 4.0 in its description and its
# license.txt (its licence field says "Non-Commercial Government Licence"; both are non-commercial)
FABDEM_CREDIT = Credit(
    "FABDEM V1-2", "FABDEM V1-2 © University of Bristol; FABDEM is " + COPERNICUS_NOTICE,
    "CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    notice="Neal, J., Hawker, L. (2023): FABDEM V1-2. https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn. "
           "Non-commercial use only; results computed from FABDEM are adapted material, shared under "
           "the same licence. " + COPERNICUS_DISCLAIMER)
NASADEM_CREDIT = Credit("NASADEM", "NASADEM: NASA JPL (2020), NASA LP DAAC, via OpenTopography",
                        "NASA open data (no restrictions)",
                        "https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
                        notice="Data accessed through OpenTopography (opentopography.org).")
# All 3DEP products are public domain; USGS asks for a credit (copyrights-and-credits page)
USGS_TERMS = ("public domain (USGS)",
              "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits")
USGS_1M_CREDIT = Credit("3DEP 1 m DEM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)
USGS_IFSAR_CREDIT = Credit("3DEP Alaska IfSAR 5 m DTM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)
USGS_13_CREDIT = Credit("3DEP 1/3 arc-second DEM (USGS)", "USGS 3D Elevation Program (3DEP)", *USGS_TERMS)


GEOPORTAL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK"
MALTA = "https://malta.coverage.wetransform.eu"
SPAIN_MDT = "https://servicios.idee.es/wcs-inspire/mdt"
SPAIN_MDS = "https://wcs-mds.idee.es/mds"
SPAIN_ORTHO = OrthoService("Orthophoto PNOA (IGN Spain)", "https://www.ign.es/wms-inspire/pnoa-ma",
                           "OI.OrthoimageCoverage", "spain/ortho/live", "PNOA © IGN")
SWISSTOPO_STAC = "https://data.geo.admin.ch/api/stac/v1"
# SWISSIMAGE in the map's own tiling (CDN), imagery up to zoom 20; there is no WMS step.
# Fewer detailed tiles than elsewhere: swisstopo's terms ask for no bulk downloads.
SWISSIMAGE = OrthoService("SWISSIMAGE (swisstopo)", None, "", "switzerland/ortho/live", "© swisstopo",
                          base_url="https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current"
                                   "/3857/{z}/{x}/{y}.jpeg", base_max_zoom=20, detail=20)
# Our own copy of ÚGKK SR's national ALS models (tools/sk_tiles.py): only the local mirror
# (FINDALINE_MIRROR) for now; the Hugging Face base goes here once the tiles are uploaded
SLOVAK_TILES: List[str] = []
ZBGIS_ORTHO = OrthoService("Orthophoto ZBGIS (ÚGKK SR)",
                           "https://zbgisws.skgeodesy.sk/zbgis_ortofoto_wms/service.svc/get", "1",
                           "slovakia/ortho/live", "© ÚGKK SR")
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
FABDEM = "https://huggingface.co/buckets/links-ads/fabdem/resolve/tiles"
COPERNICUS = "https://copernicus-dem-30m.s3.amazonaws.com"


def _fabdem_url(lat: int, lon: int) -> str:
    g_lat, g_lon = lat // 10 * 10, lon // 10 * 10
    group = (f"{_hemi(g_lat, 'N', 'S', 2)}{_hemi(g_lon, 'E', 'W', 3)}-"
             f"{_hemi(g_lat + 10, 'N', 'S', 2)}{_hemi(g_lon + 10, 'E', 'W', 3)}")
    return f"{FABDEM}/{group}_FABDEM_V1-2/{_hemi(lat, 'N', 'S', 2)}{_hemi(lon, 'E', 'W', 3)}_FABDEM_V1-2.tif"


def _copernicus_url(lat: int, lon: int, aux: Optional[str] = None) -> str:
    """URL of a Copernicus DEM tile, or of one of its auxiliary files (e.g. aux="WBM")."""
    name = f"Copernicus_DSM_COG_10_{_hemi(lat, 'N', 'S', 2)}_00_{_hemi(lon, 'E', 'W', 3)}_00"
    if aux:
        return f"{COPERNICUS}/{name}_DEM/AUXFILES/{name}_{aux}.tif"
    return f"{COPERNICUS}/{name}_DEM/{name}_DEM.tif"


# The 2012 Malta services are georeferenced about 56 m east and 196 m north of the
# true position: measured against Copernicus DEM and the 2018 survey at Dingli
# (-56, -196 m), Valletta (-50, -190) and Gozo (-60, -190).
MALTA_2012_SHIFT = (-56.0, -196.0)


def _spain(canary: bool) -> Source:
    """IGN Spain: MDT05 (terrain) and MDS05 (surface), 5 m from PNOA-LiDAR, via WCS.

    The peninsula and the Balearic Islands are in ETRS89 / UTM 30N (extended zone),
    the Canary Islands in REGCAN95 / UTM 28N; MDS05 covers both in UTM 30N. The ASCII
    grid format keeps centimetres (the GeoTIFF output is rounded to whole metres).
    """
    crs, coverage = ("EPSG:4083", "Elevacion4083_5") if canary else ("EPSG:25830", "Elevacion25830_5")
    where = "Canary Islands" if canary else "Spain"
    return Source(
        id="spain_canarias" if canary else "spain", name=f"IGN {where} (MDT05/MDS05)",
        description=f"IGN Spain PNOA-LiDAR, MDT05 terrain and MDS05 surface, 5 m ({where})",
        nmt=WcsTiles(f"MDT05 (terrain) {where}", SPAIN_MDT, coverage, crs,
                     "spain/mdt05/live", native_res=5.0, fetch_res=5.0,
                     fmt="application/asc", bytes_per_px=8),
        # MDS05's grid is 5.0045 m; tiles are resampled to 5 m on download
        nmpt=WcsTiles(f"MDS05 (trees, buildings) {where}", SPAIN_MDS, "mds05", "EPSG:25830",
                      "spain/mds05/live", native_res=5.0, fetch_res=5.0, fmt="application/asc", bytes_per_px=8),
        countries=("es",), crs=crs, ortho=SPAIN_ORTHO, credits=(IGN_CREDIT,),
        bbox=(27.0, 29.6, -18.6, -13.0) if canary else None,
        note="IGN Spain data is available at 5 m: lines shorter than about 30 m are not reliable.")


def _malta(year: int, note: str = "") -> Source:
    crs = "EPSG:25833" if year == 2012 else "EPSG:32633"
    layer = lambda kind, desc: WcsTiles(
        f"{desc} Malta {year}", f"{MALTA}/{kind}_1m_{year}/ows", f"{kind}_1m_{year}", crs,
        f"malta/{kind}/{year}", native_res=1.0 if year == 2012 else 0.15, fetch_res=1.0, axes=("E", "N"),
        shift=MALTA_2012_SHIFT if year == 2012 else (0.0, 0.0), bytes_per_px=0.8)  # measured: ~3 MB per tile
    return Source(
        id="malta" if year == 2018 else f"malta{year}", name=f"Malta {year} (MSDI)",
        description=f"Malta Planning Authority LiDAR {year}, DTM and DSM 1 m",
        nmt=layer("dtm", "DTM (terrain)"), nmpt=layer("dsm", "DSM (trees, buildings)"),
        countries=("mt",) if year == 2018 else (), crs=crs,
        fallback="malta" if year == 2012 else "europe", credits=(MALTA_CREDITS[year],),
        ortho=OrthoService("Orthophoto Malta 2018 (MSDI)", f"{MALTA}/wms/ortho_2018/ows",
                           "OI.OrthoimageCoverage", "malta/ortho/2018", "Planning Authority Malta"),
        note=note)


SOURCES: Dict[str, Source] = {s.id: s for s in [
    Source(
        id="geoportal", name="geoportal.gov.pl",
        description="GUGiK (Poland): NMT and NMPT sheets of 1 m or finer, newest survey, PL-EVRF2007-NH",
        # Sheet files from opendata.geoportal.gov.pl, found through the EVRF2007 sheet
        # indexes: about 2 s per sheet, while the WCS spends 30-50 s generating each ASCII
        # tile, its downsampling loses data at coarse resolutions (Tatras at 5 m) and its
        # PL-KRON86-NH coverages hold surveys up to 2019 only.
        nmt=SheetTiles("NMT (digital terrain model)", f"{GEOPORTAL}/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze",
                       "SkorowidzNMT", "poland/nmt", native_res=1.0),
        nmpt=SheetTiles("NMPT (digital surface model: trees, buildings)",
                        f"{GEOPORTAL}/NumerycznyModelPokryciaTerenuEVRF2007/WFS/Skorowidze",
                        "SkorowidzNMPT", "poland/nmpt", native_res=1.0),
        countries=("pl",), crs="EPSG:2180", grid_origin=(0.5, 0.5), credits=(GUGIK_CREDIT,),
        ortho=OrthoService("Orthophoto (geoportal.gov.pl)", f"{GEOPORTAL}/ORTO/WMS/HighResolution",
                           "Raster", "poland/ortho/live", "GUGiK",
                           # the WMS of StandardResolution answers about half of the requests
                           # with 404 (2026-10-25); its WMTS answers all
                           base_url=f"{GEOPORTAL}/ORTO/WMTS/StandardResolution?SERVICE=WMTS&REQUEST=GetTile"
                                    "&VERSION=1.0.0&LAYER=ORTOFOTOMAPA&STYLE=default&FORMAT=image/jpeg"
                                    "&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}")),
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
        note="Data © swisstopo."),
    Source(
        id="slovakia", name="ÚGKK SR (DMR 5.0 / DMP 1.0)",
        description="ÚGKK SR (Slovakia): ALS 2017-2023, DMR 5.0 terrain and DMP 1.0 surface, 1 m, "
                    "S-JTSK [JTSK03] / Bpv",
        # Published only as one ZIP of 155-200 GB per model: our own 2 km tiles of them
        # (tools/sk_tiles.py), on the national grid, pixel edges on whole metres
        nmt=GridTiles("DMR 5.0 (terrain)", [f"{base}/dmr5/1m" for base in SLOVAK_TILES], "EPSG:8353",
                      "slovakia/dmr5/5.0/epsg8353-1m-2km", 2000, 1.0, 4.8e6, mirror="slovakia/dmr5/1m"),
        nmpt=GridTiles("DMP 1.0 (trees, buildings)", [f"{base}/dmp1/1m" for base in SLOVAK_TILES], "EPSG:8353",
                       "slovakia/dmp1/1.0/epsg8353-1m-2km", 2000, 1.0, 5.7e6, mirror="slovakia/dmp1/1m"),
        countries=("sk",), crs="EPSG:8353", ortho=ZBGIS_ORTHO, credits=(UGKK_CREDIT,),
        note="Data © ÚGKK SR, CC BY 4.0 (laser scanning 2017-2023)."),
    _malta(2018, note="Malta 2018 heights are published in whole metres, which makes slopes and "
                      "clearances coarser; --source malta2012 has centimetre precision but gaps "
                      "along the coast (filled from 2018)."),
    _malta(2012),
    _spain(canary=True),
    _spain(canary=False),
    Source(
        id="alaska", name="USGS 3DEP (1 m DEM, Alaska)",
        description="USGS 3DEP (Alaska): 1 m lidar DEM where there is one, newest survey first; gaps from "
                    "the 5 m IfSAR DTM, then the 1/3 arc-second DEM; NAD83 / NAVD88",
        nmt=USGS_1M, countries=("us",), bbox=ALASKA_BOX, local_crs=nad83_utm_crs, ortho=USGS_ORTHO,
        fallback="alaska_ifsar", more_fallbacks=("usgs10m",), instead_without_data="alaska_ifsar",
        credits=(USGS_1M_CREDIT,), note=USA_NOTE),
    Source(
        id="alaska_ifsar", name="USGS 3DEP (Alaska IfSAR 5 m)",
        description="USGS 3DEP (Alaska): IfSAR DTM 5 m (radar, 2012-2019), gaps from the 1/3 arc-second DEM",
        nmt=USGS_IFSAR, local_crs=nad83_utm_crs, ortho=USGS_ORTHO, fallback="usgs10m",
        credits=(USGS_IFSAR_CREDIT,),
        note=USA_NOTE + " Alaska's IfSAR is a radar model at 5 m: lines shorter than about 30 m are not reliable."),
    Source(
        id="usa", name="USGS 3DEP (1 m DEM)",
        description="USGS 3DEP (USA, Puerto Rico, US Virgin Islands): 1 m lidar DEM, newest survey first, "
                    "NAD83 / UTM, NAVD88; gaps from the 1/3 arc-second DEM",
        # 10 km files of 10-450 MB per project: blocks of 1 km read by HTTP range requests
        nmt=USGS_1M, countries=("us", "pr", "vi"), local_crs=nad83_utm_crs, ortho=USGS_ORTHO,
        fallback="usgs10m", credits=(USGS_1M_CREDIT,), note=USA_NOTE),
    Source(
        id="usgs10m", name="USGS 3DEP (1/3 arc-second DEM)",
        description="USGS 3DEP seamless 1/3 arc-second DEM (about 10 m): the USA, Hawaii and the territories",
        nmt=USGS_13, local_crs=nad83_utm_crs, ortho=USGS_ORTHO, credits=(USGS_13_CREDIT,),
        note="The 1/3 arc-second DEM has pixels of about 10 m: lines shorter than about 60 m are not reliable."),
    Source(
        id="europe", name="FABDEM + Copernicus DEM",
        description="FABDEM V1-2 (terrain, trees and buildings removed) and Copernicus GLO-30 (surface), 30 m",
        nmt=DegreeTiles("FABDEM (terrain)", "fabdem/v1-2", _fabdem_url, native_res=30, bytes_per_tile=20e6,
                        credit=FABDEM_CREDIT),
        nmpt=DegreeTiles("Copernicus DEM GLO-30 (surface)", "copernicus30/2021/dem", _copernicus_url,
                         native_res=30, bytes_per_tile=20e6, credit=COPERNICUS_CREDIT),
        fallback=None, credits=(FABDEM_CREDIT, COPERNICUS_CREDIT),
        note="FABDEM is licensed for non-commercial use only (CC BY-NC-SA 4.0): results made from it may "
             "be shared only under the same terms. At 30 m only long lines can be found reliably."),
    Source(
        id="nasadem", name="NASADEM (OpenTopography)",
        description="NASADEM 30 m (SRTM, includes some vegetation), from the OpenTopography API",
        nmt=OpenTopographyTiles("NASADEM", "nasadem/v1", "NASADEM"), credits=(NASADEM_CREDIT,),
        note="NASADEM is a radar surface model at 30 m: only long lines can be found reliably."),
]}

# Rough boxes used when the country cannot be looked up (offline)
OFFLINE_BOXES = [("mt", (35.78, 36.10, 14.15, 14.60)), ("pl", (49.0, 54.9, 14.1, 24.2)),
                 ("es", (27.0, 43.9, -18.6, 4.4)), ("sk", (47.7, 49.65, 16.8, 22.6)),
                 ("ch", (45.8, 47.85, 5.9, 10.5)), ("us", (24.4, 49.4, -125.0, -66.9)), ("us", ALASKA_BOX),
                 ("pr", (17.8, 18.6, -67.4, -65.2))]


def country_code(lat: float, lon: float, cache_dir: str) -> Optional[str]:
    """ISO country code of a point (OpenStreetMap), or a rough guess when offline."""
    try:
        code = osm.reverse(lat, lon, cache_dir, zoom=3).get("address", {}).get("country_code")
        if code:
            return code.lower()
    except (requests.RequestException, ValueError):
        pass
    for code, (s, n, w, e) in OFFLINE_BOXES:
        if s <= lat <= n and w <= lon <= e:
            return code
    return None


def choose_source(name: str, lat: float, lon: float, cache_dir: str, elevation_file: Optional[str] = None,
                  surface_file: Optional[str] = None) -> Tuple[Source, str]:
    """The source to use and why."""
    if elevation_file or name == "files":
        if not elevation_file:
            raise ValueError("--source files needs --elevation-file")
        # File names only: the description goes into the run's files (runs.js, lines.geojson, ATTRIBUTION.txt)
        source = Source(id="files", name="local files", description=f"local files: {os.path.basename(elevation_file)}"
                        + (f", {os.path.basename(surface_file)}" if surface_file else ""),
                        nmt=FileLayer("Terrain file", elevation_file),
                        nmpt=FileLayer("Surface file", surface_file) if surface_file else None)
        with rio.open(elevation_file) as src:
            if src.crs is not None and src.crs.is_projected and src.crs.linear_units in ("metre", "meter"):
                source.crs = src.crs.to_string()
                # The grid is in the file's CRS: put its edges on the file's pixel edges
                source.grid_origin = (src.transform.c % abs(src.res[0]), src.transform.f % abs(src.res[1]))
        native = source.nmt.native_res
        source.default_resolution = float(round(native)) if native >= 5 else max(MIN_RESOLUTION, round(native, 1))
        return source, "--elevation-file given"
    if name != "auto":
        why = source_unavailable(SOURCES[name])
        if why:
            raise ValueError(why)
        return SOURCES[name], f"--source {name}"
    code = country_code(lat, lon, cache_dir)
    for source in SOURCES.values():
        if code and code in source.countries and source.covers(lat, lon):
            why = source_unavailable(source)
            if why:  # e.g. our own Slovak tiles without a copy set up
                return SOURCES["europe"], f"the centre is in {code.upper()}, but {why}"
            if source.instead_without_data and source.nmt.has_data_near(lat, lon, cache_dir) is False:
                return (SOURCES[source.instead_without_data],
                        f"the centre is in {code.upper()}, but {source.id} has no terrain data near it")
            return source, f"the centre is in {code.upper()}"
    return SOURCES["europe"], f"no national source for {code.upper() if code else 'this place'}"


def source_unavailable(source: Source) -> Optional[str]:
    """Why a source cannot be used here, or None."""
    for layer in (source.nmt, source.nmpt):
        why = layer.unavailable() if layer else None
        if why:
            return why
    return None


# What the layers prepared in this process came from (Layer.used), saved with the run
used_data: List[Dict] = []


def prepare_layer(layer: Layer, grid: Grid, cache_dir: str, out_path: str, label: str,
                  update: Optional[str] = None, download: bool = True) -> str:
    """Download what is missing (unless done already: download False) and bring the layer
    onto the working grid (.npy)."""
    if download:
        layer.download(grid, cache_dir, update, label)
    tiles = (layer.tiles(grid) or []) if layer.folder else []  # local files are not in the cache
    empty = sum(cache.state(cache_dir, layer.tile_path(cache_dir, t)) == "missing" for t in tiles)
    if empty:  # normal over the sea; on land a sign of a lost tile (see the regression tests)
        print(f"{layer.description}: {empty} of {len(tiles)} tiles without data (the service has none there)")
    build_mosaic(layer.files(grid, cache_dir), grid, out_path, label, shift=layer.shift)
    used_data.append(layer.used(grid, cache_dir))
    return out_path


def build_mosaic(files: List[str], grid: Grid, out_path: str, label: str,
                 categorical: bool = False, shift: Tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """Stitch rasters into a memory-mapped array covering the grid.

    Tiles already on the grid are copied; others are reprojected, averaging when
    the data is finer than the grid and interpolating bilinearly when it is coarser
    (categorical rasters, such as a water mask, use the nearest value instead).
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mosaic = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                       shape=(grid.height, grid.width))
    mosaic[:] = np.nan
    progress.compute.start(f"stitching {label}", len(files), unit="tile")
    for path in files:
        progress.compute.update(1)
        with rio.open(path) as src:
            _place(src, grid, mosaic, categorical, shift)
    mosaic.flush()
    progress.compute.finish()
    return mosaic


def _place(src, grid: Grid, mosaic: np.ndarray, categorical: bool = False,
           shift: Tuple[float, float] = (0.0, 0.0)):
    clean = (lambda band: band.astype(np.float32)) if categorical else _clean
    grid_crs = rio.crs.CRS.from_user_input(grid.crs)
    src_crs = src.crs or grid_crs
    moved = Affine.translation(*shift)
    src_bounds = rio.coords.BoundingBox(src.bounds.left + shift[0], src.bounds.bottom + shift[1],
                                        src.bounds.right + shift[0], src.bounds.top + shift[1])
    same_grid = src_crs == grid_crs and shift == (0.0, 0.0) and math.isclose(abs(src.res[0]), grid.res) \
        and math.isclose(abs(src.res[1]), grid.res)
    if same_grid:
        row_off = int(round((grid.top - src.bounds.top) / grid.res))
        col_off = int(round((src.bounds.left - grid.left) / grid.res))
        if abs(row_off * grid.res - (grid.top - src.bounds.top)) < grid.res / 100:
            r0, c0 = max(row_off, 0), max(col_off, 0)
            r1, c1 = min(row_off + src.height, grid.height), min(col_off + src.width, grid.width)
            if r0 < r1 and c0 < c1:
                window = rio.windows.Window(c0 - col_off, r0 - row_off, c1 - c0, r1 - r0)
                values = clean(src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan))
                target = mosaic[r0:r1, c0:c1]
                mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)
            return

    # Part of the grid covered by this raster
    left, bottom, right, top = transform_bounds(src_crs, grid.crs, *src_bounds)
    c0 = max(0, int(math.floor((left - grid.left) / grid.res)))
    c1 = min(grid.width, int(math.ceil((right - grid.left) / grid.res)))
    r0 = max(0, int(math.floor((grid.top - top) / grid.res)))
    r1 = min(grid.height, int(math.ceil((grid.top - bottom) / grid.res)))
    if r0 >= r1 or c0 >= c1:
        return
    src_res = abs(src.res[0]) * (111320 if src_crs.is_geographic else 1)
    if categorical:
        resampling = Resampling.nearest
    else:
        resampling = Resampling.average if src_res < grid.res * 0.75 else Resampling.bilinear
    window_transform = from_origin(grid.left + c0 * grid.res, grid.top - r0 * grid.res, grid.res, grid.res)
    values = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)

    # Read only the part of the raster under the grid (plus a margin for resampling)
    area = transform_bounds(grid.crs, src_crs, *grid.bounds)
    area = (area[0] - shift[0], area[1] - shift[1], area[2] - shift[0], area[3] - shift[1])
    margin = 3 * max(abs(src.res[0]), abs(src.res[1]))
    window = from_bounds(area[0] - margin, area[1] - margin, area[2] + margin, area[3] + margin,
                         src.transform).round_offsets().round_lengths()
    window = window.intersection(rio.windows.Window(0, 0, src.width, src.height))
    band = src.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
    reproject(clean(band), values, src_transform=moved * src.window_transform(window), src_crs=src_crs,
              dst_transform=window_transform, dst_crs=grid.crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling, num_threads=WARP_THREADS)
    target = mosaic[r0:r1, c0:c1]
    mosaic[r0:r1, c0:c1] = np.where(np.isnan(target), values, target)


# Copernicus water body mask, 1°×1° tiles next to the DEM tiles: 1 ocean, 2 lake, 3 river
OCEAN, LAKE = 1, 2
GAP_RING = 3  # pixels around a gap used to match the filling source's heights
GAP_MATCH_SLOPE = 15  # degrees; only gentler ground is used to match heights
GAP_MAX_LOCAL_SHIFT = 3  # m; local height offsets differing more from the overall one are ignored
SHORE_BUFFER = 45  # m around water in the mask that may still be water (the mask is 30 m)
SEA_LEVEL_TOLERANCE = 1.0  # m; data at most this high inside the sea counts as water
WATER_MASK = DegreeTiles("Copernicus water body mask", "copernicus30/2021/wbm",
                         lambda lat, lon: _copernicus_url(lat, lon, "WBM"), native_res=30,
                         bytes_per_tile=1e5, credit=WATER_MASK_CREDIT)


def water_body_mask(grid: Grid, cache_dir: str, out_path: str, update: Optional[str] = None,
                    download: bool = True) -> np.ndarray:
    """Copernicus water body mask on the grid (OCEAN, LAKE...), open sea where tiles are missing
    (downloaded first unless done already: download False)."""
    if download:
        WATER_MASK.download(grid, cache_dir, update, "water mask")
    wbm = build_mosaic(WATER_MASK.files(grid, cache_dir), grid, out_path, "water mask", categorical=True)
    used_data.append(WATER_MASK.used(grid, cache_dir))
    for tile in WATER_MASK.tiles(grid):
        if cache.state(cache_dir, WATER_MASK.tile_path(cache_dir, tile)) == "missing":
            lat, lon = tile
            left, bottom, right, top = transform_bounds("EPSG:4326", grid.crs, lon, lat, lon + 1, lat + 1)
            c0, c1 = max(0, int((left - grid.left) // grid.res)), min(grid.width, int((right - grid.left) // grid.res) + 1)
            r0, r1 = max(0, int((grid.top - top) // grid.res)), min(grid.height, int((grid.top - bottom) // grid.res) + 1)
            if r0 < r1 and c0 < c1:
                block = wbm[r0:r1, c0:c1]
                block[np.isnan(block)] = OCEAN
    return np.asarray(wbm)


def near(mask: np.ndarray, metres: float, res: float) -> np.ndarray:
    """The mask grown by about `metres` (square neighbourhood)."""
    from scipy import ndimage
    if metres <= 0:
        return mask
    return ndimage.binary_dilation(mask, structure=np.ones((3, 3)), iterations=max(1, math.ceil(metres / res)))


def fill_water(elevation_path: str, surface_path: Optional[str], grid: Grid, wbm: np.ndarray,
               sea_zone: np.ndarray, out_path: str) -> str:
    """Give the sea and lakes an elevation where the data has none.

    National LiDAR models have no data over water, so lines across the sea (and
    the edges of sea cliffs, whose slope needs the neighbouring pixels) would be
    missed. Pixels without data in sea_zone (the sea mask of coast.py grown by
    --shore-buffer, see near) get 0 m. Pixels without data next to lakes of the
    Copernicus mask (within SHORE_BUFFER, as the mask is 30 m) get the level of
    the lake's shore (the median elevation around it). The exact shoreline comes
    from the elevation data itself; gaps in the data on land stay without data.
    Saves a boolean water mask (filled pixels, and lakes that have data) to out_path.
    """
    from scipy import ndimage

    elevation = np.load(elevation_path, mmap_mode="r+")
    surface = np.load(surface_path, mmap_mode="r+") if surface_path else None
    progress.compute.start("filling sea and lakes", 3, unit="step")
    empty = np.isnan(elevation)
    sea_fill = empty & sea_zone
    progress.compute.update(1)
    lake = empty & near(wbm == LAKE, SHORE_BUFFER, grid.res) & ~sea_fill
    progress.compute.update(1)

    elevation[sea_fill] = 0.0
    if surface is not None:
        surface[sea_fill & np.isnan(surface)] = 0.0
    water = sea_fill.copy()
    lake_px = 0
    labels, _ = ndimage.label(lake, structure=np.ones((3, 3)))
    for index, region in enumerate(ndimage.find_objects(labels), 1):
        if region is None:
            continue
        rows = slice(max(region[0].start - 1, 0), region[0].stop + 1)
        cols = slice(max(region[1].start - 1, 0), region[1].stop + 1)
        area = labels[rows, cols] == index
        shore = ndimage.binary_dilation(area) & ~empty[rows, cols]
        heights = elevation[rows, cols][shore]
        heights = heights[np.isfinite(heights)]
        if heights.size == 0:
            continue
        level = float(np.median(heights))
        block = elevation[rows, cols]
        block[area] = level
        if surface is not None:
            sblock = surface[rows, cols]
            sblock[area & np.isnan(sblock)] = level
        water[rows, cols] |= area
        lake_px += int(area.sum())
    # Water that the elevation data covers: lakes measured by LiDAR, and sea given as
    # about 0 m by the data itself (e.g. IGN Spain)
    water |= (wbm == LAKE) & ~empty
    water |= sea_zone & ~empty & (np.asarray(elevation) <= SEA_LEVEL_TOLERANCE)
    elevation.flush()
    if surface is not None:
        surface.flush()
    np.save(out_path, water)
    progress.compute.update(1)
    km2 = lambda px: px * grid.res ** 2 / 1e6
    progress.compute.finish(f"sea {km2(int(sea_fill.sum())):.2f} km², lakes {km2(lake_px):.2f} km²")
    return out_path


def fill_gaps(elevation_path: str, surface_path: Optional[str], grid: Grid, fallback: "Source",
              cache_dir: str, out_path: str, update: Optional[str] = None,
              exclude: Optional[np.ndarray] = None, name: str = "gap") -> Tuple[str, int]:
    """Fill the remaining gaps in the data on land from another source.

    Each gap gets the other source shifted by the median height difference in a
    ring of pixels around that gap, so it joins its surroundings without a step
    (different surveys and height systems differ by up to a few metres). Only
    gentle slopes are used for this: on a cliff, a shift of a metre between two
    surveys changes the height by tens of metres. A local offset more than
    GAP_MAX_LOCAL_SHIFT from the overall median is not trusted.
    Saves a boolean mask of the filled pixels to out_path; returns
    (out_path, number of filled pixels). Pixels in `exclude` (the sea) are left alone.
    The fallback's grids are saved next to out_path as <name>_nmt.npy and <name>_nmpt.npy.
    """
    from scipy import ndimage

    work = os.path.dirname(out_path)
    elevation = np.load(elevation_path, mmap_mode="r+")
    filled = np.isnan(elevation)
    if exclude is not None:
        filled &= ~exclude
    if not filled.any():
        np.save(out_path, filled)
        return out_path, 0
    pairs = [(elevation, fallback.nmt, f"{name}_nmt.npy")]
    if surface_path:
        surface = np.load(surface_path, mmap_mode="r+")
        pairs.append((surface, fallback.nmpt or fallback.nmt, f"{name}_nmpt.npy"))
    for target, layer, name in pairs:
        gaps = np.isnan(target) if exclude is None else np.isnan(target) & ~exclude
        if not gaps.any():
            continue
        other = np.asarray(np.load(prepare_layer(layer, grid, cache_dir, os.path.join(work, name),
                                                 f"gap fill ({fallback.name})", update), mmap_mode="r"))
        values = np.asarray(target)
        gy, gx = np.gradient(np.where(np.isfinite(values), values, other), grid.res)
        flat = np.degrees(np.arctan(np.hypot(gx, gy))) < GAP_MATCH_SLOPE
        both = ~gaps & np.isfinite(values) & np.isfinite(other) & flat
        overall = float(np.median(values[both] - other[both])) if both.any() else 0.0
        # Offset of every gap from the ring of pixels around it
        labels, count = ndimage.label(gaps, structure=np.ones((3, 3)))
        ring = ndimage.grey_dilation(labels, size=(GAP_RING * 2 + 1,) * 2) * (both & (labels == 0))
        offsets = np.full(count + 1, overall)
        if ring.any():
            # Only the ring pixels: scipy sorts every pixel it is given (10 s for a 58 Mpx tile)
            near = ring > 0
            local = ndimage.median(values[near] - other[near], ring[near], index=np.arange(1, count + 1))
            local = np.asarray(local, dtype=float)
            # A local offset far from the overall one comes from misaligned edges, not heights
            usable = np.isfinite(local) & (np.abs(local - overall) <= GAP_MAX_LOCAL_SHIFT)
            offsets[1:] = np.where(usable, local, overall)
        target[gaps] = other[gaps] + offsets[labels[gaps]]
        target.flush()
    filled &= np.isfinite(elevation)
    np.save(out_path, filled)
    return out_path, int(filled.sum())


def fill_gaps_chain(elevation_path: str, surface_path: Optional[str], grid: Grid, fallbacks: List["Source"],
                    cache_dir: str, out_path: str, update: Optional[str] = None,
                    exclude: Optional[np.ndarray] = None) -> Tuple[str, List[Tuple["Source", int]]]:
    """Fill the gaps on land from each fallback in turn (fill_gaps), each only what the ones
    before it left (most sources have one; Alaska: its IfSAR, then the 1/3″ DEM). Saves the
    mask of all filled pixels to out_path; returns (out_path, [(fallback, filled pixels)])."""
    filled, counts = None, []
    for n, fallback in enumerate(fallbacks):
        step = out_path if n == 0 else f"{os.path.splitext(out_path)[0]}{n}.npy"
        _, pixels = fill_gaps(elevation_path, surface_path, grid, fallback, cache_dir, step, update,
                              exclude=exclude, name="gap" if n == 0 else f"gap{n}")
        counts.append((fallback, pixels))
        if n == 0:
            filled = np.load(step)
        elif pixels:
            filled |= np.load(step)
            np.save(out_path, filled)
    return out_path, counts


def load_slope_file(slope_file: str, grid: Grid, out_path: str) -> str:
    """Resample a user supplied slope raster (degrees) onto the working grid."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    slope = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32,
                                      shape=(grid.height, grid.width))
    slope[:] = np.nan
    with rio.open(slope_file) as src:
        src_crs = src.crs
        if src_crs is None:
            print(f"  {slope_file} has no coordinate system, assuming {grid.crs}")
            src_crs = grid.crs
        reproject(rio.band(src, 1), slope, src_crs=src_crs, src_transform=src.transform,
                  src_nodata=src.nodata, dst_transform=grid.transform, dst_crs=grid.crs,
                  dst_nodata=np.nan, resampling=Resampling.average)
    slope.flush()
    return out_path
