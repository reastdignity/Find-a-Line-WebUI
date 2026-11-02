"""The sources of the United Kingdom (sources/catalogue/uk.py): England's WCS tiles (the Environment Agency's
float-minimum nodata, requests on the coverage's own pixels), Wales's blocks of one national COG, and
--source auto by region, also offline. No network: the WCS answers are made here."""

import os
import sys
from types import SimpleNamespace

import numpy as np
import rasterio as rio
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import osm  # noqa: E402
import sources as src  # noqa: E402
from sources.catalogue import uk  # noqa: E402

EA_NODATA = -3.4028234663852886e+38  # what the Environment Agency's WCS writes where it has no data


def _geotiff(left, top, band, nodata=EA_NODATA):
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                          crs="EPSG:27700", nodata=nodata, transform=from_origin(left, top, 1.0, 1.0)) as dst:
            dst.write(band.astype(np.float32), 1)
        return memfile.read()


def test_england_tile_on_the_coverage_pixels(tmp_path, monkeypatch):
    """A 2 km tile is asked on the coverage's own pixels (axes E and N, no SCALESIZE: the service
    does not resample) and its float-minimum nodata is cached as NaN; an answer narrower than
    the tile (the DSM's coverage starts at 133 000 m) lands on the tile's pixels."""
    layer = src.SOURCES["england"].nmpt
    assert layer.tile_px == 2000 and layer.fetch_res == 1.0  # 2 km of 1 m pixels, from 0 m: edges on whole metres
    band = np.full((2000, 1000), 12.5, dtype=np.float32)
    band[:, :10] = EA_NODATA  # the sea
    asked = []

    def get(url, params=None, **kwargs):
        asked.append((url, params))
        return SimpleNamespace(content=_geotiff(133000.0, 26000.0, band), url=url,
                               headers={"content-type": "image/tiff"})
    monkeypatch.setattr(src.net, "_get", get)
    path = str(tmp_path / "tile.tif")
    layer.download_tile((1.0, 66, 12), path)
    url, params = asked[0]
    assert url == "https://environment.data.gov.uk/spatialdata/" \
                  "lidar-composite-digital-surface-model-first-return-dsm-1m/wcs"
    assert ("SUBSET", "E(132000.000,134000.000)") in params and ("SUBSET", "N(24000.000,26000.000)") in params
    assert ("COVERAGEID", "df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m") in params
    assert not any(key == "SCALESIZE" for key, _ in params)
    with rio.open(path) as raster:
        assert raster.transform == from_origin(132000.0, 26000.0, 1.0, 1.0) and raster.shape == (2000, 2000)
        values = raster.read(1)
    assert np.isnan(values[:, :1010]).all() and (values[:, 1010:] == 12.5).all()


def test_wales_blocks_of_the_national_file():
    """Blocks of 1 km on the national COG's pixels (edges on whole metres), in the release's folder;
    one partly over the file reads it, one beyond its extent is missing without a request."""
    wales = next(s for s in uk.SOURCES if s.id == "wales")
    for layer, kind in ((wales.nmt, "dtm"), (wales.nmpt, "dsm")):
        url = f"https://dmwproductionblob.blob.core.windows.net/cogs/lidar/wales_{kind}_32bit_cog.tif"
        assert layer.folder == f"wales/lidar-{kind}/{uk.WALES_RELEASE}"
        request = layer.index.request((262, 356))
        assert request.files == [(url.rsplit("/", 1)[1], url, 2022)] and request.shape == (1000, 1000)
        assert request.transform == from_origin(262000.0, 357000.0, 1.0, 1.0)
        assert layer.index.request((164, 200)).files  # 164 000-165 000 m: the file starts at 164 993 m
        for outside in ((163, 200), (356, 200), (200, 163), (200, 397)):
            assert layer.index.request(outside).files == [], outside


def test_auto_by_region_offline(tmp_path, monkeypatch):
    """Offline, the region boxes decide: Wales's first where they overlap (the border), England's
    elsewhere in England; Scotland's own boxes in Scotland."""
    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    cache_dir = str(tmp_path)
    for (lat, lon), (sid, why) in {
            src.SOURCES["england"].sample: ("england", "the centre is in GB-ENG"),
            src.SOURCES["wales"].sample: ("wales", "the centre is in GB-WLS"),
            (51.2840, -2.7590): ("england", "the centre is in GB-ENG"),   # Cheddar Gorge (R26)
            (53.19, -2.89): ("wales", "the centre is in GB-WLS"),         # Chester: inside both boxes (offline only)
            (56.8, -5.0): ("scotland", "the centre is in GB-SCT")}.items():
        source, reason = src.choose_source("auto", lat, lon, cache_dir)
        assert (source.id, reason) == (sid, why), (lat, lon)
