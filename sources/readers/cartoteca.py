"""CartotecaFile: one file of a survey of a Tuscan lidar sheet (Regione Toscana's cartoteca), whose URL carries a hash
no index gives: a WMS GetFeatureInfo (HTML) at a point of the survey's own part of the sheet names it, kept in a small
JSON file per survey (both models' URLs at once) and asked again after a 404 of the file. The file is a Deflate ZIP of
an ARC/INFO ASCII grid without a CRS (EPSG:3003 imposed) and the licence of its owner (licenza_dati_Lidar.pdf), which
decides the owner written into the cached tile (OWNER_TAG): the run's credits follow it."""

import io
import json
import os
import re
import zipfile
from typing import Dict, Optional, Tuple

import cache

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


class CartotecaFile(Reader):
    """A survey's file of one model (kind "dtm" or "dsm") of the cartoteca's lidar, written as a float32 GeoTIFF in
    EPSG:3003 with its owner (OWNER_TAG). A survey a GetFeatureInfo does not name at any of its points has no data
    (missing); a GetFeatureInfo that fails is an error (nothing cached). At most max_bytes downloaded, at most
    member_bytes unpacked."""
    rewrites = True  # the cached tile is written by _write_tile (its tags kept by reencode)

    def __init__(self, description: str, wms_url: str, layer: str, kind: str, base: str = DOWNLOADS,
                 max_bytes: int = 60_000_000, member_bytes: int = 150_000_000):
        self.description, self.wms_url, self.layer, self.kind, self.base = description, wms_url, layer, kind, base
        self.max_bytes, self.member_bytes = max_bytes, member_bytes

    def _read_urls(self, path: str) -> Optional[Dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def url(self, request) -> Optional[str]:
        """The file's resolved URL if known, else the GetFeatureInfo's service (the same host: its slot)."""
        urls = self._read_urls(request.urls) or {}
        return urls.get(self.kind) or self.wms_url

    def gfi(self, x: float, y: float) -> str:
        """The GetFeatureInfo's HTML at a point (EPSG:3003)."""
        h = GFI_HALF_M
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "LAYERS": self.layer,
                  "QUERY_LAYERS": self.layer, "STYLES": "", "CRS": "EPSG:3003",
                  "BBOX": f"{x - h:.1f},{y - h:.1f},{x + h:.1f},{y + h:.1f}", "WIDTH": "101", "HEIGHT": "101",
                  "I": "50", "J": "50", "INFO_FORMAT": "text/html", "FEATURE_COUNT": "20"}
        response = net._get(self.wms_url, params=params, timeout=120, binary_types=("html",))
        if response is None:
            raise RuntimeError("the GetFeatureInfo answered 404")
        if len(response.content) > 2_000_000:
            raise RuntimeError(f"the GetFeatureInfo's answer has {len(response.content)} bytes")
        return response.content.decode("utf-8", "replace")

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
                os.makedirs(os.path.dirname(request.urls), exist_ok=True)
                tmp = net._part(request.urls)
                with open(tmp, "w", encoding="utf-8") as out:
                    json.dump(urls, out)
                os.replace(tmp, request.urls)
                return urls
        return None

    def fetch(self, request, path: str) -> Fetched:
        where = f"{self.description} sheet {request.godlo} ({request.sheet.version})"
        urls, fresh = self._read_urls(request.urls), False
        if not (urls or {}).get(self.kind):
            urls, fresh = self.resolve(request), True
        if not (urls or {}).get(self.kind):
            print(f"{where}: no GetFeatureInfo names its file; no data")
            return Fetched(0, self.wms_url)
        url = urls[self.kind]
        try:
            response = net._get(url, binary_types=("zip", "octet"))
            if response is None and not fresh:  # its link changed: asked again
                urls = self.resolve(request) or {}
                if urls.get(self.kind) and urls[self.kind] != url:
                    url = urls[self.kind]
                    response = net._get(url, binary_types=("zip", "octet"))
        except RuntimeError as e:
            raise RuntimeError(f"Could not download {where}: {e}")
        if response is None:
            print(f"{where}: the file answers 404; no data")
            return Fetched(0, url)
        band, transform, owner = self.read(response.content, request, where, (urls or {}).get("owner"))
        _write_tile(path, _clean(band), request.crs, transform, tags={OWNER_TAG: owner})
        return Fetched.of(response, url)

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
