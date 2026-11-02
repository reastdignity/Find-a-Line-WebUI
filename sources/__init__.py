"""
Elevation data sources.

A source provides a terrain model (NMT/DTM, ground only) and optionally a surface
model (NMPT/DSM, with trees and buildings), plus optionally an orthophoto service.
Every layer is downloaded in tiles into its own folder of the cache, so switching
between sources never downloads again what is already there.

Kinds of layers (sources/layers/, a module each):
- WcsTiles: square tiles from an OGC WCS 2.0 service on a fixed grid in the
  service's coordinate system (Malta, IGN Spain).
- ImageServerTiles: square tiles from an ArcGIS ImageServer (exportImage) on the
  service's own pixels (Czechia).
- IndexedTiles: files found through an index, newest survey per sheet or tile:
  SheetTiles (map sheets from a WFS sheet index, geoportal.gov.pl) and StacTiles
  (tiles of a STAC collection, swisstopo).
- GridTiles: our own tiles on a fixed grid (Slovakia, made by tools/sk_tiles.py), from
  a local mirror (FINDALINE_MIRROR) or, once uploaded, from Hugging Face.
- TnmBlocks: blocks of the big files of The National Map (USGS 3DEP, the USA), found
  through its API and read by HTTP range requests, composed newest survey first; and
  DegreeBlocks: blocks of 1° files at a fixed URL (3DEP's 1/3″ DEM); FileBlocks: blocks of
  big fixed files in a metric CRS (a grid of COGs, or one national COG).
- DegreeTiles: 1°×1° GeoTIFF tiles in WGS84 (Copernicus DEM, FABDEM) and
  OpenTopography's global DEM API (NASADEM).
- FileLayer: a local raster file (GeoTIFF, ASC...), e.g. NASADEM from OpenTopography.

To add a national source, add a module with its Source objects to sources/catalogue/ (see
malta.py) and the module to FAMILIES there, its country code in `countries`; see README,
"Data sources". The layers of a search are downloaded together (download_layers: one pool
for all their tiles). Searches of one data folder may download at once: each tile under its
own lock (tile_lock; the second search waits, then finds it cached) and at most HOST_SLOTS
tiles from one host at a time across all of them (host_slot), both lock files in cache/locks.

Every source and every layer used for filling (the water mask, the gap filling
source) names its licence and the notice its data must be shown with (`Credit`):
each run records them for the layers it used (run.json, the map, ATTRIBUTION.txt).

The modules, each importing only those before it: net (HTTP, host slots, tile locks),
credit, layer, composed (a layer of an index and a reader), readers/, indexes/, source,
layers/, catalogue/, choose (the source of a search), mosaic (layers on the working grid),
filling (water and gaps). This package re-exports what the rest of the app uses. The names
tests patch (net._get, net._sleep, choose.country_code, layer.DOWNLOAD_THREADS) are not
re-exported: call and patch them through their module.
"""

from . import catalogue, choose, composed, credit, filling, indexes, layer, layers, mosaic, net, readers, source
from .readers import download, imageserver, sheetfile, tilebases, wcsreader, windows
from .indexes import cached, listings, tilings, versions
from .indexes import osgrid, s3listing
from .layers import blocks, degree, fileblocks, files, gridtiles, imageserver, indexed, sheets, stac, tnm, wcs, zipped
from .layers import s3blocks
from .catalogue import austria, canada, czechia, denmark, finland, france, germany, italy, luxembourg, malta, new_zealand, norway, poland, slovakia, spain, switzerland, uk, usa, world
from .catalogue import australia
from .net import HOST_SLOTS_OF, host_slot, tile_lock
from .credit import CC_BY, YEAR, YEAR_TEXT, Credit, OSM_CREDIT, dated, dated_credit
from .layer import Fetched, Layer, download_layers
from .source import MIN_RESOLUTION, Coverage, OrthoService, Source
from .layers.wcs import WcsTiles
from .layers.imageserver import ImageServerTiles
from .readers.tilebases import MIRROR_ENV, grid_tile_name
from .layers.gridtiles import GridTiles
from .layers.degree import DegreeTiles, OpenTopographyTiles
from .indexes.versions import Block, Sheet
from .layers.indexed import IndexedTiles
from .layers.sheets import SheetTiles
from .layers.stac import StacTiles
from .readers.windows import _same_crs
from .layers.blocks import DegreeBlocks
from .layers.fileblocks import FileBlocks
from .layers.tnm import IfsarBlocks, TnmBlocks, Usgs1mBlocks, _survey_year, _utm_zone_of
from .layers.files import FileLayer
from .layers.zipped import ZippedTiles
from .layers.metalink import MetalinkTiles
from .layers.s3blocks import S3Blocks
from .catalogue.poland import GUGIK_CREDIT
from .catalogue.malta import MALTA_CREDITS
from .catalogue.usa import USGS_1M
from .catalogue.world import COPERNICUS_DISCLAIMER, FABDEM_CREDIT, WATER_MASK, WATER_MASK_CREDIT
from .catalogue import SOURCES
from .choose import OFFLINE_BOXES, choose_source, source_unavailable
from .mosaic import build_mosaic, load_slope_file, prepare_layer, used_data
from .filling import LAKE, OCEAN, SHORE_BUFFER, fill_gaps, fill_gaps_chain, fill_water, near, water_body_mask

__all__ = ["SOURCES", "MIN_RESOLUTION", "Source", "Coverage", "OrthoService", "Credit", "CC_BY", "OSM_CREDIT", "Layer",
           "Fetched", "download_layers", "HOST_SLOTS_OF", "host_slot", "tile_lock", "WcsTiles", "ImageServerTiles", "GridTiles",
           "MIRROR_ENV", "grid_tile_name", "DegreeTiles", "OpenTopographyTiles", "IndexedTiles", "Sheet",
           "SheetTiles", "StacTiles", "DegreeBlocks", "FileBlocks", "Block", "TnmBlocks", "Usgs1mBlocks",
           "IfsarBlocks", "FileLayer", "GUGIK_CREDIT", "USGS_1M", "FABDEM_CREDIT", "COPERNICUS_DISCLAIMER", "MALTA_CREDITS",
           "WATER_MASK", "WATER_MASK_CREDIT", "OFFLINE_BOXES", "choose_source", "source_unavailable", "used_data",
           "prepare_layer", "build_mosaic", "load_slope_file", "water_body_mask", "near", "fill_water",
           "fill_gaps", "fill_gaps_chain", "OCEAN", "LAKE", "SHORE_BUFFER", "_same_crs", "_utm_zone_of",
           "_survey_year", "MetalinkTiles", "S3Blocks"]
