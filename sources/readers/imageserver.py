"""ImageServerReader: a tile from an ArcGIS ImageServer by its "Export Image" operation (exportImage), on the
service's own pixels.

Written from Esri's ArcGIS REST API reference, "Export Image"
(https://developers.arcgis.com/rest/services-reference/enterprise/export-image/): GET
<service>/exportImage with bbox (xmin,ymin,xmax,ymax), bboxSR and imageSR (a WKID), size (width,height,
at most the service's maxImageWidth x maxImageHeight), format, pixelType, noData, interpolation,
compression, mosaicRule (a JSON object) and f=image (the image itself; f=json would answer its address).
An error is the JSON object {"error": {"code", "message", "details"}}; ArcGIS Server 12 sends it with HTTP
200 under the content type of the image asked for (ČÚZK's: image/tiff), so an answer is data only when it
is a TIFF (its magic bytes).
"""

import json
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader
from . import TIFF_MAGIC


def number(value: float) -> str:
    """A coordinate as written into a request: to a tenth of a millimetre, without float noise or trailing
    zeros (-615999.6, not -615999.6000000001; the services' grids lie on centimetres)."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class ImageServerReader(Reader):
    """exportImage of a tile (res, i, j) of a WcsTiling with the same tile_px and origin: the box of the
    tile in crs, at res, read exactly as the service sends it (no resampling on our side: an answer on other
    pixels than the tile's is an error). Ask for the tiles on the service's own grid (origin, res =
    native_res) with interpolation RSP_NearestNeighbor and the stored values come back unchanged.

    sr: the WKID of bboxSR and imageSR (by default the code of crs: "5514" of "EPSG:5514"). The answer's CRS
    is not read: ArcGIS writes a LOCAL_CS for some projections (ČÚZK's S-JTSK / Krovak East North), so the
    tile is saved in crs, as asked. nodata: the value asked for where there are no data (noData; without it
    ČÚZK's service answers 0 outside the country, untagged); those pixels become NaN, and a tile without a
    pixel of data is missing (no file). zero_is_nodata: 0 is no data too.

    pixel_type, interpolation, compression (LZ77: LZW in the TIFF): the request's parameters. mosaic_rule: a
    mosaicRule (a dict, sent as compact JSON with sorted keys) for a service of several rasters;
    lock_raster_ids: the rasters to use, newest first (mosaicMethod esriMosaicLockRaster; merged into
    mosaic_rule). params: more parameters of every request.
    """

    def __init__(self, description: str, url: str, crs: str, native_res: float, tile_px: int,
                 origin: Tuple[float, float] = (0.0, 0.0), sr: Optional[str] = None, nodata: float = -9999.0,
                 pixel_type: str = "F32", interpolation: str = "RSP_NearestNeighbor", compression: str = "LZ77",
                 mosaic_rule: Optional[Dict] = None, lock_raster_ids: Sequence[int] = (),
                 params: Tuple[Tuple[str, str], ...] = (), zero_is_nodata: bool = False):
        self.description, self.service_url, self.crs = description, url.rstrip("/"), crs
        self.native_res, self.tile_px, self.origin = native_res, tile_px, origin
        self.sr = sr or crs.split(":")[-1]
        self.nodata, self.pixel_type, self.interpolation = nodata, pixel_type, interpolation
        self.compression, self.params, self.zero_is_nodata = compression, tuple(params), zero_is_nodata
        rule = dict(mosaic_rule or {})
        if lock_raster_ids:
            rule.update(mosaicMethod="esriMosaicLockRaster", lockRasterIds=list(lock_raster_ids))
        self.mosaic_rule = rule or None

    def url(self, tile) -> Optional[str]:
        return self.service_url

    @property
    def export_url(self) -> str:
        return f"{self.service_url}/exportImage"

    def edges(self, tile) -> Tuple[float, float, float, float]:
        """(left, bottom, right, top) of a tile (res, i, j) in crs."""
        res, i, j = tile
        size = self.tile_px * res
        return (i * size + self.origin[0], j * size + self.origin[1], (i + 1) * size + self.origin[0],
                (j + 1) * size + self.origin[1])

    def export_params(self, left: float, bottom: float, right: float, top: float,
                      res: float) -> List[Tuple[str, str]]:
        """The parameters of the exportImage of a box at res."""
        params = [("bbox", ",".join(number(v) for v in (left, bottom, right, top))),
                  ("bboxSR", self.sr), ("imageSR", self.sr),
                  ("size", f"{round((right - left) / res)},{round((top - bottom) / res)}"),
                  ("format", "tiff"), ("pixelType", self.pixel_type), ("noData", number(self.nodata)),
                  ("interpolation", self.interpolation), ("compression", self.compression)]
        if self.mosaic_rule:
            params.append(("mosaicRule", json.dumps(self.mosaic_rule, separators=(",", ":"), sort_keys=True)))
        return params + list(self.params) + [("f", "image")]

    def export(self, left: float, bottom: float, right: float, top: float, res: float):
        """The answer to the exportImage of a box (None: HTTP 404), a TIFF; RuntimeError with the service's
        message when it answered an error, also one sent with HTTP 200 as an image. A 200 error whose code is
        not 400 (a request the server could not do now) is asked again, net.RETRIES times in all."""
        for attempt in range(net.RETRIES):
            response = net._get(self.export_url, self.export_params(left, bottom, right, top, res))
            if response is None or response.content[:4] in TIFF_MAGIC:
                return response
            code, text = service_error(response.content)
            if code == 400 or attempt == net.RETRIES - 1:
                raise RuntimeError(f"the service answered an error instead of an image: {text}")
            net._sleep(attempt)

    def fetch(self, tile, path: str) -> Fetched:
        res, i, j = tile
        left, bottom, right, top = self.edges(tile)
        px = self.tile_px
        try:
            response = self.export(left, bottom, right, top, res)
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} tile {i}_{j}: {e}")
        if response is None:
            return Fetched(0, self.service_url)
        with MemoryFile(response.content, ext=".tif") as memfile, memfile.open() as src:
            band = src.read(1).astype(np.float32)
            transform, nodata = src.transform, src.nodata
        expected = from_origin(left, top, res, res)
        if band.shape != (px, px) or not transform.almost_equals(expected, precision=res / 1000):
            raise RuntimeError(f"Could not download {self.description} tile {i}_{j}: the answer is "
                               f"{band.shape[1]} x {band.shape[0]} px from ({transform.c:.3f}, {transform.f:.3f}), "
                               f"not the tile's {px} x {px} px from ({left:.3f}, {top:.3f})")
        for value in {self.nodata, nodata} - {None}:
            band[band == np.float32(value)] = np.nan
        band = _clean(band, self.zero_is_nodata)
        if not np.isfinite(band).any():  # outside the data (the service's extent or the country)
            return Fetched(0, self.service_url)
        _write_tile(path, band, self.crs, expected)
        return Fetched.of(response)


def service_error(body: bytes) -> Tuple[Optional[int], str]:
    """(code, text) of an ArcGIS error answer ({"error": {"code", "message", "details"}}); (None, the start of
    the body) for anything else that is not an image."""
    try:
        error = json.loads(body.decode("utf-8"))["error"]
        details = [d for d in error.get("details") or [] if isinstance(d, str)]
        code = error.get("code")
        text = " ".join([f"{code}" if code is not None else "", str(error.get("message", "")), *details]).strip()
        return (code if isinstance(code, int) else None), text
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, body[:200].decode("utf-8", "replace").strip()
