"""CartotecaFile: one file of a survey of a Tuscan lidar sheet (Regione Toscana's cartoteca), whose URL carries a hash
no index gives: a WMS GetFeatureInfo (HTML) at a point of the survey's own part of the sheet names it, kept in a small
JSON file per survey (both models' URLs at once) and asked again after a 404 of the file. The file is a Deflate ZIP of
an ARC/INFO ASCII grid without a CRS (EPSG:3003 imposed) and the licence of its owner (licenza_dati_Lidar.pdf), which
decides the owner written into the cached tile (OWNER_TAG): the run's credits follow it. Every answer is read in a
stream up to a cap (capped_get), never held whole beyond it."""

import io
import json
import os
import re
import threading
import time
import zipfile
from typing import Dict, Optional, Sequence, Tuple

import requests

import cache
import servicecounts

from .. import net
from ..composed import Reader
from ..layer import Fetched, _clean, _write_tile
from .sheetfile import _ascii_grid

# The tag of a cached tile naming the owner of its survey: "RT" (Regione Toscana, CC BY 4.0) or "MATTM" (the
# Ministry of the Environment, CC BY-SA 3.0 IT)
OWNER_TAG = "FINDALINE_OWNER"
OWNERS = ("RT", "MATTM")
# The licence links in the owners' PDFs (link annotations, plain bytes in the file; read 2026-11-15): Regione
# Toscana's "Il dataset è rilasciato con licenza CC BY 4.0", the Ministry's "... CC BY-SA 3.0 Italia". The file's
# own licence wins over the GetFeatureInfo's "Proprieta'": the 351 MATTM sheets "in cofinanziamento e comproprietà
# con comuni pisani" are "RT" there but carry the Ministry's licence (16e05, lot 006, 2008)
LICENCE_LINKS = ((b"creativecommons.org/licenses/by-sa/3.0/it", "MATTM"),
                 (b"creativecommons.org/licenses/by/4.0", "RT"))
LICENCE_MEMBER = "licenza_dati_Lidar.pdf"
# Only links to the cartoteca's own download folder are taken from a GetFeatureInfo's HTML
DOWNLOADS = "https://www502.regione.toscana.it/geoscopio/download/altimetria/lidar/"
LINK = re.compile(r"href=[\"']?(https?://[^\s\"'>]+?/(dtm|dsm)/([0-9a-z_]+?)_([0-9a-f]{32})\.zip)", re.IGNORECASE)
GFI_OWNER = re.compile(r"Proprieta'\s*:\s*<b>\s*([A-Z]+)\s*</b>")
GFI_HALF_M = 50  # the GetFeatureInfo's box: 100 m around the point, 101 x 101 px (the point at its middle pixel)
GFI_BYTES = 2_000_000  # the most a GetFeatureInfo's answer may have (about 3.7 kB each, 2026-11-15)
# Tries to save the URLs' file when another process holds it open (Windows refuses os.replace then), a second apart
SAVE_TRIES = 5


class SheetUnresolved(RuntimeError):
    """No GetFeatureInfo names a survey's file: an error of this search (the sheet left out, nothing cached)."""


class _TooLarge(Exception):
    """An answer longer than its cap."""


def capped_get(url: str, limit: int, params=None, binary_types: Sequence[str] = ("octet",),
               timeout: int = 300) -> Tuple[Optional[bytes], Optional[requests.Response]]:
    """GET as net._get (its retries and backoff, the app's headers, a turn of the host's rate, counted), the body read
    in a stream and never beyond limit bytes: more is an error at once (not tried again). (None, response) for a
    404; RuntimeError for any other failure. The response comes back closed, for its headers."""
    last: Optional[Exception] = None
    for attempt in range(net.RETRIES):
        slow_down = False
        try:
            net.rate_turn(url)
            with servicecounts.request(url) as counted:
                response = counted.got(net.session().get(url, params=params, timeout=timeout, stream=True,
                                                         headers=cache.http_headers(), verify=net.verify(url)),
                                       read=False)
                try:
                    if response.status_code == 404:
                        return None, response
                    kind = response.headers.get("content-type", "")
                    if response.status_code != 200 or not any(t in kind for t in binary_types):
                        if response.status_code == 200:
                            counted.outcome = "other"
                        slow_down = response.status_code in (429, 503)
                        start = next(response.iter_content(300), b"").decode("utf-8", "replace")
                        raise RuntimeError(f"HTTP {response.status_code}: {start}")
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > limit:
                            raise _TooLarge(f"the answer has more than {limit} bytes")
                        chunks.append(chunk)
                    counted.add(size)
                    return b"".join(chunks), response
                finally:
                    response.close()
        except _TooLarge as e:
            raise RuntimeError(str(e)) from None
        except (requests.RequestException, RuntimeError) as e:
            last = e
            net._sleep(attempt + 3 if slow_down else attempt)
    raise RuntimeError(cache.clean_error(last))


_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _urls_lock(path: str) -> threading.Lock:
    """The lock of one survey's URLs file in this process (the DTM's and the DSM's downloads share the file)."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(os.path.normcase(os.path.abspath(path)), threading.Lock())


class CartotecaFile(Reader):
    """A survey's file of one model (kind "dtm" or "dsm") of the cartoteca's lidar, written as a float32 GeoTIFF in
    EPSG:3003 with its owner (OWNER_TAG). A survey no GetFeatureInfo names at any of its points (also when asked
    again after a 404) raises SheetUnresolved: the layer leaves it out of the search, nothing cached; a file that
    answers 404 after a fresh GetFeatureInfo has no data (missing); any other failure is an error (nothing cached).
    At most max_bytes downloaded, GFI_BYTES of a GetFeatureInfo, member_bytes unpacked per member."""
    rewrites = True  # the cached tile is written by _write_tile (its tags kept by reencode)

    def __init__(self, description: str, wms_url: str, layer: str, kind: str, base: str = DOWNLOADS,
                 max_bytes: int = 60_000_000, member_bytes: int = 150_000_000):
        self.description, self.wms_url, self.layer, self.kind, self.base = description, wms_url, layer, kind, base
        self.max_bytes, self.member_bytes = max_bytes, member_bytes

    def _read_urls(self, path: str) -> Optional[Dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):  # none yet, or another process replacing it now
            return None

    def _save_urls(self, path: str, urls: Dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = net._part(path)
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump(urls, out)
        for _ in range(SAVE_TRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: another process reads it this moment
                time.sleep(1)
        os.remove(tmp)  # used for this download only; the next search asks again

    def url(self, request) -> Optional[str]:
        """The file's resolved URL if known, else the GetFeatureInfo's service (the same host: its slot)."""
        urls = self._read_urls(request.urls) or {}
        return urls.get(self.kind) or self.wms_url

    def gfi(self, x: float, y: float) -> str:
        """The GetFeatureInfo's HTML at a point (EPSG:3003), at most GFI_BYTES."""
        h = GFI_HALF_M
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "LAYERS": self.layer,
                  "QUERY_LAYERS": self.layer, "STYLES": "", "CRS": "EPSG:3003",
                  "BBOX": f"{x - h:.1f},{y - h:.1f},{x + h:.1f},{y + h:.1f}", "WIDTH": "101", "HEIGHT": "101",
                  "I": "50", "J": "50", "INFO_FORMAT": "text/html", "FEATURE_COUNT": "20"}
        try:
            body, _ = capped_get(self.wms_url, GFI_BYTES, params, ("html",), timeout=120)
        except RuntimeError as e:
            raise RuntimeError(f"GetFeatureInfo: {e}") from None
        if body is None:
            raise RuntimeError("the GetFeatureInfo answered 404")
        return body.decode("utf-8", "replace")

    def resolve(self, request) -> Optional[Dict]:
        """The survey's URLs ({"dtm", "dsm", "owner"}) from a GetFeatureInfo at its points, the first whose answer
        names its files; None when none does. Written to request.urls."""
        sheet = request.sheet
        names = {"dtm": sheet.dtm.lower(), "dsm": sheet.dsm.lower()}
        for x, y in sheet.points:
            html = self.gfi(x, y)
            found = {}
            for url, kind, name, _ in LINK.findall(html):
                if url.lower().startswith(self.base.lower()) and name.lower() == names[kind.lower()]:
                    found[kind.lower()] = url
            if found.get(self.kind):
                owner = GFI_OWNER.search(html)
                urls = {**found, "owner": owner.group(1) if owner else None, "asked_at": cache.now_iso()}
                self._save_urls(request.urls, urls)
                return urls
        return None

    def _urls(self, request, again: bool = False) -> Tuple[Dict, bool]:
        """The survey's URLs and whether they were asked now (again: after a 404, asked whatever is saved), under
        the survey's lock; SheetUnresolved when no GetFeatureInfo names the file."""
        with _urls_lock(request.urls):
            urls = None if again else self._read_urls(request.urls)
            fresh = False
            if not (urls or {}).get(self.kind):
                urls, fresh = self.resolve(request), True
        if not (urls or {}).get(self.kind):
            raise SheetUnresolved(f"no GetFeatureInfo names {request.name} (sheet {request.godlo}, "
                                  f"{request.sheet.version})")
        return urls, fresh

    def _download(self, url: str, where: str) -> Tuple[Optional[bytes], Optional[requests.Response]]:
        try:
            return capped_get(url, self.max_bytes, binary_types=("zip", "octet"))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {where}: {e}") from None

    def fetch(self, request, path: str) -> Fetched:
        where = f"{self.description} sheet {request.godlo} ({request.sheet.version})"
        urls, fresh = self._urls(request)
        url = urls[self.kind]
        data, response = self._download(url, where)
        if data is None and not fresh:  # its link changed: asked again
            urls, _ = self._urls(request, again=True)
            if urls[self.kind] != url:
                url = urls[self.kind]
                data, response = self._download(url, where)
        if data is None:
            print(f"{where}: the file answers 404; no data")
            return Fetched(0, url)
        band, transform, owner = self.read(data, request, where, urls.get("owner"))
        _write_tile(path, _clean(band), request.crs, transform, tags={OWNER_TAG: owner})
        return Fetched(len(data), url, response.headers.get("ETag"), response.headers.get("Last-Modified"))

    def read(self, data: bytes, request, where: str, gfi_owner: Optional[str]) -> Tuple:
        """The grid of a survey's ZIP and its owner (the licence in the ZIP, else the GetFeatureInfo's, else MATTM:
        the stricter licence)."""
        if len(data) > self.max_bytes:
            raise RuntimeError(f"{where}: the file has {len(data)} bytes, more than {self.max_bytes}")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = {i.filename.rsplit("/", 1)[-1].lower(): i for i in archive.infolist() if not i.is_dir()}
                grids = [i for n, i in members.items() if n.endswith(".asc")]
                if len(grids) != 1:
                    raise RuntimeError(f"{where}: {len(grids)} ASCII grids in the file ({sorted(members)[:10]})")
                content = self._member(archive, grids[0])
                licence = self._member(archive, members[LICENCE_MEMBER.lower()]) \
                    if LICENCE_MEMBER.lower() in members else b""
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"{where}: not a ZIP file ({e})")
        owner = next((o for link, o in LICENCE_LINKS if link in licence), None)
        if owner is None:
            owner = gfi_owner if gfi_owner in OWNERS else "MATTM"
            print(f"{where}: no licence link in the file; credited to {owner}")
        try:
            band, transform = _ascii_grid(content, request.res, request.crs, where)
        except Exception as e:
            raise RuntimeError(f"{where}: {str(e) or type(e).__name__}") from e
        if abs(transform.a - request.res) > 1e-6 or abs(transform.e + request.res) > 1e-6:
            raise RuntimeError(f"{where}: cells of {transform.a} m, {request.res} m listed")
        return band, transform, owner

    def _member(self, archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
        if info.file_size > self.member_bytes:
            raise RuntimeError(f"{info.filename} has {info.file_size} bytes unpacked, more than {self.member_bytes}")
        with archive.open(info) as member:  # the header's size is not trusted
            content = member.read(self.member_bytes + 1)
        if len(content) > self.member_bytes:
            raise RuntimeError(f"{info.filename} unpacks to more than {self.member_bytes} bytes")
        return content
