"""query_features: the features of an ArcGIS FeatureServer layer over a box (its REST API's query, JSON over plain
HTTP), as a listing needs them."""

import json
from typing import Dict, List, Sequence, Tuple

import requests

import cache
import servicecounts

from .. import net
from ..net import RETRIES
from .cached import IndexUnavailable

# ArcGIS REST API, Query (Feature Service/Layer) (https://developers.arcgis.com/rest/services-reference/enterprise/
# query-feature-service-layer/): GET <layer>/query with where, geometry (an envelope xmin,ymin,xmax,ymax in inSR),
# geometryType, spatialRel, outFields, returnGeometry, outSR, f=json answers {features: [{attributes, geometry}],
# exceededTransferLimit} (true while more features match than the page holds: the next page is asked with
# resultOffset, in the order of orderByFields); errors are {"error": {code, message, details}}, also with HTTP 200.
# A page holds at most the layer's maxRecordCount (1000 for LidarBC's layers)
QUERY_PAGE = 1000
QUERY_PAGES_MAX = 100   # a listing that never ends is an error (every waiting loop has a deadline)
QUERY_BYTES_MAX = 32_000_000  # an answer larger than this is no answer of a page (streamed and stopped)
WgsBox = Tuple[float, float, float, float]


def _query_answer(url: str, params: Dict[str, str]) -> Dict:
    """One JSON answer of the API; server errors (5xx, the connection) asked again up to RETRIES times;
    IndexUnavailable for anything else: another HTTP status, an answer that is not JSON or is larger than
    QUERY_BYTES_MAX, an error object (also with HTTP 200)."""
    for attempt in range(RETRIES):
        net.rate_turn(url)
        try:
            with servicecounts.request(url) as counted:
                response = counted.got(net.session().get(url, params=params, timeout=120,
                                                         headers=cache.http_headers(), stream=True), read=False)
                with response:
                    body = bytearray()
                    for chunk in response.iter_content(65536):
                        body += chunk
                        counted.add(len(chunk))
                        if len(body) > QUERY_BYTES_MAX:
                            raise IndexUnavailable(f"ArcGIS query: more than {QUERY_BYTES_MAX} bytes")
        except IndexUnavailable:
            raise
        except requests.RequestException as e:
            if attempt == RETRIES - 1:
                raise IndexUnavailable(f"ArcGIS query: {cache.clean_error(e)}") from e
        else:
            if response.status_code >= 500 and attempt < RETRIES - 1:
                net._sleep(attempt)
                continue
            if response.status_code != 200:
                raise IndexUnavailable(f"ArcGIS query: HTTP {response.status_code}")
            try:
                answer = json.loads(bytes(body))
            except ValueError as e:
                raise IndexUnavailable("ArcGIS query: not JSON") from e
            if not isinstance(answer, dict):
                raise IndexUnavailable("ArcGIS query: not a JSON object")
            if "error" in answer:
                error = answer["error"] if isinstance(answer["error"], dict) else {}
                raise IndexUnavailable(f"ArcGIS query: error {error.get('code', '?')}: {error.get('message', '')}")
            if not isinstance(answer.get("features"), list):
                raise IndexUnavailable("ArcGIS query: no features in the answer")
            return answer
        net._sleep(attempt)
    raise AssertionError("unreachable")


def query_features(layer_url: str, box: WgsBox, fields: Sequence[str], geometry: bool = True,
                   precision: int = 6) -> List[Dict]:
    """Every feature of a FeatureServer layer (its address, …/FeatureServer/<n>) intersecting a box (west, south,
    east, north in WGS84): its attributes of fields and, with geometry, its geometry in WGS84 rounded to precision
    decimals; in the order of their object ids, page by page while the service says more match. IndexUnavailable
    for an error answer or more than QUERY_PAGES_MAX pages: never a shorter listing."""
    found: List[Dict] = []
    url = layer_url.rstrip("/") + "/query"
    west, south, east, north = box
    for _ in range(QUERY_PAGES_MAX):
        params = {"where": "1=1", "geometry": f"{west},{south},{east},{north}",
                  "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                  "outFields": ",".join(fields), "returnGeometry": "true" if geometry else "false",
                  "orderByFields": "OBJECTID", "resultOffset": str(len(found)), "resultRecordCount": str(QUERY_PAGE),
                  "f": "json"}
        if geometry:
            params.update(outSR="4326", geometryPrecision=str(precision))
        answer = _query_answer(url, params)
        found += answer["features"]
        if not answer.get("exceededTransferLimit"):
            return found
        if not answer["features"]:
            raise IndexUnavailable("ArcGIS query: more features said to match, but an empty page")
    raise IndexUnavailable(f"ArcGIS query: more than {QUERY_PAGES_MAX} pages")


def ring_bounds(geometry: Dict) -> WgsBox:
    """The box (west, south, east, north) of an ArcGIS polygon's rings (x, y in its order)."""
    points = [p for ring in geometry.get("rings", []) for p in ring]
    if not points:
        raise ValueError("a geometry without points")
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)
