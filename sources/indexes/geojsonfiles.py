"""GeoJSON indexes: the files of a download service listed by one GeoJSON document for a whole Land, a
feature per file with its link (LVermGeo SH's "Massendownload" index of the DGM1), read once per TTL and
kept like a Metalink document (MetalinkFiles), its files picked per 0.25° tile."""

import json
import os
from typing import Dict, Optional, Sequence
from urllib.parse import parse_qs, urlsplit

import requests

import cache
import servicecounts

from .. import net
from .cached import IndexUnavailable
from .metalink import MetalinkFiles

# The largest GeoJSON document read (LVermGeo SH's of the DGM1: 9 MB with 18 685 features, 2026-11-02)
GEOJSON_MAX_BYTES = 100_000_000


def file_name(link: str) -> str:
    """The name of the file a link gives: its query's `file` (massen.php?file=dgm1_..._2025.xyz&...),
    else the last part of its path."""
    parts = urlsplit(link)
    named = parse_qs(parts.query).get("file")
    return named[0] if named else parts.path.rsplit("/", 1)[-1]


def parse_features(body: bytes, link: str) -> Dict[str, str]:
    """{file name: link} of the features of a GeoJSON FeatureCollection, the link the property `link`
    of each (file_name gives its name), in the order of the document, a name once (the first);
    features without a link are left out. ValueError when the body is no FeatureCollection (an
    error page, an HTML answer)."""
    try:
        document = json.loads(body)
    except ValueError as e:
        raise ValueError(f"not JSON ({str(e)[:100]})") from e
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection" \
            or not isinstance(document.get("features"), list):
        raise ValueError("not a GeoJSON FeatureCollection")
    files: Dict[str, str] = {}
    for feature in document["features"]:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        url = properties.get(link) if isinstance(properties, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            files.setdefault(file_name(url), url)
    return files


class GeoJsonFiles(MetalinkFiles):
    """The files of one or more GeoJSON documents that list a whole region, a feature per file whose
    property `link` is its URL (the file's name in its query's `file` or at the end of its path),
    each file a square tile named by its corner as for MetalinkFiles: name, a regular expression of
    the file names with the groups east and north (in tile_m units of crs) and, if the names carry
    it, year. The documents are asked once per TTL ("sheet-index") for all 0.25° tiles and the files
    matching name kept in <top>/geojson/<key>.json.gz; a document that cannot be had (an error, more
    than GEOJSON_MAX_BYTES, no FeatureCollection) is IndexUnavailable, and nothing is kept then.
    The listed files carry no checksum or size: a file is known by its URL (ShaPerTile)."""

    def __init__(self, urls: Sequence[str], name: str, crs: str, res: float, top: str, key: str,
                 tile_m: float = 1000, link: str = "link_data"):
        super().__init__(urls, name, crs, res, top, key, tile_m)
        self.link = link

    def table_path(self, cache_dir: str) -> str:
        return os.path.join(cache_dir, self.top, "geojson", f"{self.key}.json.gz")

    def _document(self, url: str) -> bytes:
        """The body of one document, at most GEOJSON_MAX_BYTES read."""
        net.rate_turn(url)
        try:
            with servicecounts.request(url) as counted, \
                    requests.get(url, timeout=300, headers=cache.http_headers(), verify=net.verify(url),
                                 stream=True) as response:
                counted.got(response, read=False)
                if response.status_code != 200:
                    raise IndexUnavailable(f"GeoJSON {cache.clean_url(url)}: HTTP {response.status_code}")
                body = bytearray()
                for chunk in response.iter_content(1 << 20):
                    counted.add(len(chunk))
                    body += chunk
                    if len(body) > GEOJSON_MAX_BYTES:
                        raise IndexUnavailable(f"GeoJSON {cache.clean_url(url)}: more than "
                                               f"{GEOJSON_MAX_BYTES} bytes")
                return bytes(body)
        except IndexUnavailable:
            raise
        except requests.RequestException as e:
            raise IndexUnavailable(f"GeoJSON {cache.clean_url(url)}: {cache.clean_error(e)}") from e

    def _download(self) -> Dict:
        """The files of every document, as kept."""
        files: Dict[str, Dict] = {}
        for url in self.urls:
            try:
                listed = parse_features(self._document(url), self.link)
            except ValueError as e:
                raise IndexUnavailable(f"GeoJSON {cache.clean_url(url)}: {e}") from e
            for name, link in listed.items():
                if self.name.search(name) and name not in files:
                    files[name] = {"name": name, "url": link, "sha256": None, "size": None}
        return {"documents": list(self.urls), "files": list(files.values())}

    def forget(self, cache_dir: Optional[str]):
        """Forget the kept files (a link they gave is out of date): the documents are asked again
        by the next search, in this process too."""
        if cache_dir:
            path = self.table_path(cache_dir)
            cache.forget(cache_dir, [path])
            self._asked.discard(path)
            self._tables.pop(path, None)
