"""WmsrReader: a tile of raw heights from a WMS GetMap answered as a GeoTIFF (IGN's Géoplateforme WMS-R)."""

from typing import List, NamedTuple, Optional, Tuple

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from .. import net
from ..layer import Fetched, _clean, _write_tile
from ..composed import Reader

# The first bytes of a TIFF (little- or big-endian; BigTIFF too): anything else is no raster
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


class MapRequest(NamedTuple):
    """A box (left, bottom, right, top in the reader's CRS) and its size in pixels."""
    left: float
    bottom: float
    right: float
    top: float
    width: int
    height: int


def _number(value: float) -> str:
    """A coordinate as the request writes it: at most 6 decimals, no float noise, no trailing zeros
    (970339.75, 6302000, -0.25)."""
    text = f"{round(value, 6):.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


class WmsrReader(Reader):
    """GetMap (OGC WMS 1.3.0, 06-042, 7.3) of a box of a raster layer whose GeoTIFF answer holds the
    heights themselves, not a picture: IGN's WMS-R on data.geopf.fr serves its LiDAR HD MNT/MNS and RGE
    ALTI so (the Géoplateforme's documentation of the WMS-R; FORMAT=image/geotiff, float32 with its nodata
    value). The request: SERVICE=WMS, VERSION=1.3.0, REQUEST=GetMap, LAYERS, STYLES (empty: the default),
    CRS, BBOX in the CRS's own axis order (EPSG:2154: easting, northing), WIDTH, HEIGHT, FORMAT, and params
    (IGN's vendor FORMAT_OPTIONS=compression:deflate: a DEFLATE GeoTIFF of the same values, 11 MB a km² at
    0.5 m instead of 16). Coordinates are written exactly (_number: no float noise in a BBOX).

    The answer is kept as it comes, on the box's own pixels (the tile's grid: the request lies on the
    service's pixel edges, so these are its stored pixels): an answer of another size or on another grid
    is an error, never resampled. Its CRS is forced to the reader's (IGN's answers name a broken
    PROJCS["EPSG:2154"] on an unknown datum). Errors never become data: an answer that is not a TIFF
    (an exception report, also when labelled image/geotiff) is an error, and so is a
    ServiceExceptionReport with HTTP 400 (IGN's answer to a bad request: net._get raises after its
    retries); a 404 and an answer whose every pixel is nodata (IGN answers HTTP 200 with -9999 at sea,
    outside France, on restricted sites and where a block is not published yet) are missing: no file.
    A request larger than max_px a side (IGN's MaxWidth/MaxHeight, 5010) is refused before it is made.
    """

    def __init__(self, description: str, url: str, layer: str, crs: str,
                 params: Tuple[Tuple[str, str], ...] = (("FORMAT_OPTIONS", "compression:deflate"),),
                 fmt: str = "image/geotiff", max_px: int = 5010):
        self.description, self.service_url, self.layer, self.crs = description, url, layer, crs
        self.params, self.fmt, self.max_px = tuple(params), fmt, max_px

    def url(self, request) -> Optional[str]:
        return self.service_url

    def getmap_params(self, request: MapRequest) -> List[Tuple[str, str]]:
        """The parameters of the GetMap of a box."""
        bbox = ",".join(_number(v) for v in (request.left, request.bottom, request.right, request.top))
        return [("SERVICE", "WMS"), ("VERSION", "1.3.0"), ("REQUEST", "GetMap"), ("LAYERS", self.layer),
                ("STYLES", ""), ("CRS", self.crs), ("BBOX", bbox), ("WIDTH", str(request.width)),
                ("HEIGHT", str(request.height)), ("FORMAT", self.fmt)] + list(self.params)

    def fetch(self, request: MapRequest, path: str) -> Fetched:
        if max(request.width, request.height) > self.max_px:
            raise ValueError(f"{self.description}: {request.width} x {request.height} px is more than the "
                             f"service's {self.max_px} px a side")
        try:
            response = net._get(self.service_url, self.getmap_params(request))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {self.description} tile {self._name(request)}: {e}")
        if response is None:
            return Fetched(0, self.service_url)
        data = response.content
        if data[:4] not in TIFF_MAGIC:
            text = data[:300].decode("utf-8", "replace").strip()
            raise RuntimeError(f"Could not download {self.description} tile {self._name(request)}: not a GeoTIFF "
                               f"({response.headers.get('content-type', '')}): {text}")
        res_x = (request.right - request.left) / request.width
        res_y = (request.top - request.bottom) / request.height
        transform = from_origin(request.left, request.top, res_x, res_y)
        with MemoryFile(data, ext=".tif") as memfile, memfile.open() as src:
            if (src.height, src.width) != (request.height, request.width) or \
                    not src.transform.almost_equals(transform, precision=1e-6 * min(res_x, res_y)):
                raise RuntimeError(f"{self.description} tile {self._name(request)}: the answer is "
                                   f"{src.width} x {src.height} px on another grid ({src.transform}), not the size "
                                   f"{request.width} x {request.height} px asked")
            band = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        band = _clean(band)
        if not np.isfinite(band).any():  # all nodata: the service has no data there
            return Fetched(0, self.service_url)
        _write_tile(path, band, self.crs, transform)
        return Fetched.of(response, self.service_url)

    @staticmethod
    def _name(request: MapRequest) -> str:
        return f"{_number(request.left)}_{_number(request.bottom)}"
