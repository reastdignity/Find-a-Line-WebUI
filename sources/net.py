"""HTTP requests with retries, the download slots of a host and the locks of cached tiles."""

import contextlib
import hashlib
import logging
import math
import os
import random
import re
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import rasterio as rio
import requests
from filelock import FileLock, Timeout

import cache
import servicecounts

# Tile downloads from one host at a time across all processes of a data folder (several jobs
# of the web worker download at once), through lock files in cache/locks/hosts (host_slot);
# HOST_SLOTS_OF holds the hosts that need another number: connections at once. A slot is held
# for a whole tile; a block of a FileBlocks/TnmBlocks layer is one slot however many range
# requests GDAL makes for it (merged, several ranges per request: GDAL_HTTP_MULTIRANGE).
HOST_SLOTS = 8
# GDAL's cache of the ranges it downloaded (CPL_VSIL_CURL_CACHE_SIZE, 16 MB by default), in each
# process: the layers that read their windows range by range (Windows(serial=True), GDAL_HTTP_MULTIRANGE
# SERIAL: a multi-range request bypasses the cache) find the tiles a neighbouring block read there.
# GDAL reads it when it first uses /vsicurl/, so it is set here, at import, unless the environment
# sets it; search.DOWNLOAD_PROCESS_BYTES counts it (docs/performance.md, "Window reads")
RANGE_CACHE_BYTES = 256 * 2 ** 20
os.environ.setdefault("CPL_VSIL_CURL_CACHE_SIZE", str(RANGE_CACHE_BYTES))
HOST_SLOTS_OF: Dict[str, int] = {
    # BEV's terms (AGB section 10) call "massenhafte Abfragen ... sowie das automatisierte
    # Herunterladen von Datenbankinhalten" misuse, without a number: two at once until BEV answers
    "data.bev.gv.at": 2,
    # Funet's README: "we had to limit the maximum connections from one IP address to 10 or even
    # block them": well below that (Paituli's files, Finland; www is Paituli's documented base and
    # the catalogue's host, mirrors the old host of the same servers, capped too for old links)
    "www.nic.funet.fi": 4,
    "mirrors.nic.funet.fi": 4,
    # National and INSPIRE download services without published numbers (INSPIRE guarantees 10
    # requests a second to a download service): a courtesy cap below our default of 8
    "servicios.idee.es": 4,
    "wcs-mds.idee.es": 4,
    "malta.coverage.wetransform.eu": 4,
    # LAiV's DOM WCS is meant for small areas; a provincial server (South Tyrol): the same courtesy
    "www.geodaten-mv.de": 4,
    "geoservices9.civis.bz.it": 4,
    # Kartverket's WCS (Norway): no published limit (its terms: "technical limitations ... will be
    # stated for each service"; the service states none, 2026-11-02): courtesy
    "wcs.geonorge.no": 4,
    # ČÚZK's ImageServers and orthophoto tiles (Czechia): its terms of network services name no number
    # ("Podmínky poskytování síťových služeb ČÚZK", 4.3.2016, read 2026-11-02: use "pokud rozsah užití není na
    # újmu poskytovatele"; one who overloads the infrastructure may be stopped): courtesy
    "ags.cuzk.gov.cz": 4,
    # GeoSN's Nextcloud (Saxony's 2 km ZIPs) and LGL's Open GeoData (Baden-Württemberg's): no published
    # limits (their terms and portals, read 2026-11-02, give no numbers; the portals' selection caps are
    # of their pages only): courtesy
    "geocloud.landesvermessung.sachsen.de": 4,
    "opengeodata.lgl-bw.de": 4,
    # Geobasis NRW's WCS behind an "OGC Proxy" and the province of Trento's download server (nginx; its directory
    # listings are slow): no published limits (Lizenzbedingungen Geobasis NRW 3/2020 and the WCS's Fees; the
    # province's LiDAR and open-data pages, read 2026-11-02): courtesy
    "www.wcs.nrw.de": 4,
    "siatservices.provincia.tn.it": 4,
    # Source Cooperative (the copy of the Tasmania 2 metre DEM): no terms page or limits published (2026-11-02;
    # its files are served through Cloudflare): courtesy
    "data.source.coop": 4,
    # geoportal.gov.pl's WFS sheet indexes (GetCapabilities, GetFeature per year layer, asked in
    # parallel: WfsSheets): GUGiK publishes no request limits (its terms and the geoportal's pages,
    # docs/data-sources.md section 1): a courtesy cap; its orthophoto tiles take no slot
    "mapy.geoportal.gov.pl": 4,
    # ARSO's lidar files (Slovenia): no published limits (its eVode page asks for large areas to be fetched on a disk
    # at ARSO, read 2026-11-02): courtesy, two at once
    "gis.arso.gov.si": 2,
    # LGB's INSPIRE WCS (Brandenburg and Berlin; its Fees "Nutzung erfolgt derzeit kostenfrei", no number) and
    # LVermGeo SH's download server (Schleswig-Holstein; its terms and pages, read 2026-11-02, give no numbers):
    # courtesy
    "inspire.brandenburg.de": 4,
    "geodaten.schleswig-holstein.de": 4,
    # Queensland's spatial-img ImageServers (the DEM time series and the State imagery): no published limits
    # (QSpatial's "Elevation and LiDAR" page, updated 18 Nov 2024, and the services' item info, read
    # 2026-11-02): courtesy
    "spatial-img.information.qld.gov.au": 4,
    # The Natural Science Institute of Iceland's file server (IslandsDEM) and mapcache (its aerial basemap): no
    # published limits (its open data page, read 2026-11-03, says nothing on automated use): courtesy
    "ftp.natt.is": 4,
    "gis.natt.is": 4,
    # Norsk Polarinstitutt's map services (Svalbard's orthophoto tiles): its terms (https://geodata.npolar.no/
    # bruksvilkar, read 2026-11-02) reserve "the right ... to limit use (limiting number of service calls etc.)"
    # without a number: courtesy
    "geodata.npolar.no": 4,
    # LVGL Saarland's Nextcloud (the open-data share's district ZIPs, read by Range: Saarland): no published limits
    # (the shop's articles 18 "Offene Geobasisdaten", 19 "Anleitung Open Data" and 4 "Benutzerhinweise", the DGM and
    # DOM category pages 1060 and 1066 of https://www.shop.lvgl.saarland.de, the DOP WMS's capabilities (Fees none,
    # AccessConstraints noLimitations) and the share's capabilities (downloadlimit default -1), read 2026-11-03):
    # courtesy for a small server, two at once
    "www.shop.lvgl.saarland.de": 2,
    # GeoBC's object storage (LidarBC's files, British Columbia): no published limits (the OGL-BC API Terms of Use,
    # v1.1 of 2025-04-11, https://www2.gov.bc.ca/gov/content/data/policy-standards/data-policies/open-data/
    # api-terms-of-use-for-ogl-information: the provider "may, without notice, impose and or adjust limits on your
    # access or use of the API"; LidarBC's pages and catalogue records, read 2026-11-03, give no numbers); a
    # provincial server shared with other ministries' buckets: courtesy
    "nrs.objectstore.gov.bc.ca": 4,
    # SlackMap's GeoJSON files and its API of a line's details (tools/slackmap_data.py, the truth check, not the
    # catalogue; read 2026-11-08: no terms or numbers on slackmap.com, its repositories or the ISA's pages): no
    # published limit: a courtesy cap
    "data.slackmap.com": 2,
    "api.slackmap.com": 1,
    # Geoscience Australia's WCS of the national 5 m lidar DEM (Australia): no published limits (the WCS's
    # capabilities, https://services.ga.gov.au/gis/services/DEM_LiDAR_5m_2025/MapServer/WCSServer?service=WCS&
    # request=GetCapabilities, its eCat record and https://www.ga.gov.au/copyright, read 2026-11-15; CloudFront's
    # firewall guards the server): courtesy, two at once
    "services.ga.gov.au": 2,
    # IDE Uruguay's file server (the national 2.5 m DTM's sheets, about 20 MB each): no published limits (its
    # Licencia de Datos Abiertos and the download pages, https://visualizador.ide.uy/descargas/datos/, read
    # 2026-11-15): courtesy, two at once
    "visualizador.ide.uy": 2,
    # INGV's GeoServer of TINITALY (Italy's 10 m WCS): no published limits (the WCS's capabilities, Fees and
    # AccessConstraints NONE; https://tinitaly.pi.ingv.it/ and its Download_Area1_1.html, read 2026-11-15): a
    # research institute's server, two at once
    "tinitaly.pi.ingv.it": 2,
    # Regione Sardegna's GeoServer (the WFS of the coastal lidar's tiles) and its download folder on the same host
    # (the tiles' ZIPs): no published limits (the WFS's capabilities, Fees and AccessConstraints none; the
    # geoportal's legal notes, https://www.sardegnageoportale.it/note-legali/, and the record R_SARDEG:BFPNM, read
    # 2026-11-15): courtesy, two at once
    "webgis.regione.sardegna.it": 2,
    # PDOK (the Netherlands' AHN4 WCS): no published limits (the WCS's Fees "NONE" and AccessConstraints CC0;
    # https://www.pdok.nl/Serviceniveau, /how-to-faq1 (a limit of 1 000 features for its WFS only) and /copyright,
    # read 2026-11-15); its MapServer refuses more than 4000 px a side: courtesy
    "service.pdok.nl": 4,
    # Het Waterschapshuis' basisdata.nl (Caribbean Netherlands' whole-island AHN files, redirected to Hetzner's
    # fsn1.your-objectstorage.com): no published limits (the dataroom page https://www.beeldmateriaal.nl/
    # dataroom-caribisch-nederland and https://www.ahn.nl/dataroom, read 2026-11-15). It stopped answering this
    # PC's connections on 2026-11-15 after about 18 parallel window reads per island at 4 connections (an outage or
    # a block, unknown): two at once
    "basisdata.nl": 2,
    # Umhvørvisstovan's file server (the Faroe Islands' DSM): its terms (https://www.foroyakort.fo/um-foeroyakort/
    # terms-and-conditions-in-english, June 2019, read 2026-11-15) give no numbers and do "not guarantee the
    # continued provision of data": courtesy, two at once
    "cdn.foroyakort.fo": 2,
    # INEGI's site (Mexico's 5 m lidar sheets: the download viewer's JSON per sheet and the ZIPs): no published limits
    # (its terms, https://www.inegi.org.mx/inegi/terminos.html, read 2026-11-15, ask for "buen uso del sitio ... y a no
    # causar daños en el mismo"; robots.txt allows /app and /contenidos/productos): courtesy, two at once
    "www.inegi.org.mx": 2,
    # DLS's INSPIRE download folder (Cyprus' 2019 DTM and DSM tiles): no published limits (the dataset's page on
    # data.gov.cy, https://www.data.gov.cy/el/dataset/ypsometria-inspire, and the folder, read 2026-11-15; DLS's
    # e-service limits of 1 GB a day are of another channel); a slow server (about 0.8 MB/s): two at once
    "eservices.dls.moi.gov.cy": 2,
    # The Estonian geoportal's download address (the DTM and DSM sheets; Cloudflare): no limit in numbers; its guide
    # to mass downloads (https://geoportaal.maaruum.ee/est/abi-ja-juhised/andmed/kuidas-on-voimalik-palju-
    # kaardilehti-korraga-alla-laadida/86, updated 15.05.2026, read 2026-11-15) says "Piirangut kaardilehtede arvus
    # ei ole" (no limit on the number of sheets), at one's own risk: courtesy, two at once (the catalogue uses this
    # host only: geoportaal.maaamet.ee answers 302 to it)
    "geoportaal.maaruum.ee": 2,
    # Regione Toscana's cartoteca (Tuscany's lidar sheets: the WFS index, the GetFeatureInfo of their URLs and the
    # ZIPs, all on one host): no published limits (the WMS's and WFS's capabilities, Fees and AccessConstraints
    # none; the GetFeatureInfo's licence notes and licenza_dati_Lidar.pdf of the ZIPs, read 2026-11-15): courtesy,
    # two at once
    "www502.regione.toscana.it": 2,
    # DAERA's tile caches on ArcGIS Online (Northern Ireland's 2021 coastal DTM, Full_NI_Elevation, and its
    # orthophoto): no published limits (the items 442cbde42ebe49a3b0d46cd7ce5c8ea2 and 9c0fd3d15cfd446a9678cd6ea4d54dc7,
    # the services and OpenDataNI's pages, read 2026-11-15); the mail to DAERA of 2026-11-15 promises "at most one
    # request per second": two at once (and HOST_RATES_OF) until DAERA answers
    "tiles-eu1.arcgis.com": 2,
    # ArcGIS Online's shared tile host (Rio de Janeiro's 5 m DTM, IPP's elevation tiles): no published limits (the
    # item 4dd8af31ff8f4486802613a8d1a22f33 and its service, read 2026-11-15): courtesy, two at once
    "tiles.arcgis.com": 2,
    # OpenDataNI's downloads (OSNI's 10 m DTM archives; the stable links redirect to signed URLs on Cloudflare R2,
    # read by Range): no published limits (the packages and OpenDataNI's terms, read 2026-11-15): two at once
    "admin.opendatani.gov.uk": 2,
    # LGV Hamburg's open-data downloads (the DGM1 and bDOM1 archives, read by Range: Hamburg): no published limits
    # (the Transparenzportal's records https://suche.transparenz.hamburg.de/dataset/gelaendemodelle-hamburg-dgm2
    # and https://suche.transparenz.hamburg.de/dataset/digitales-hoehenmodell-hamburg-bdom8, as CKAN's
    # https://suche.transparenz.hamburg.de/api/3/action/package_show?id=<name>: dl-de/by-2.0, "is_free_to_use", no
    # limits; https://www.daten-hamburg.de/robots.txt answers 404; read 2026-11-15): courtesy, two at once
    "www.daten-hamburg.de": 2,
    # Landesamt GeoInformation Bremen's INSPIRE downloads (the DGM1 and DOM1 archives of Bremen and Bremerhaven, read by
    # Range): no published limits (MetaVer's record https://metaver.de/trefferanzeige?docuuid=C448202A-0F15-413A-99E6-
    # F22F10E190C9: CC BY 4.0, "Es gelten keine Zugriffsbeschränkungen"; the open-data decree of 22.05.2024; the DOP
    # WMS's capabilities, https://geodienste.bremen.de/wms_dop_lb: Fees CC BY, no AccessConstraints;
    # https://gdi2.geo.bremen.de/robots.txt answers 404; read 2026-11-15): courtesy, two at once
    "gdi2.geo.bremen.de": 2,
    # Tokyo's bucket of the Tokyo Digital Twin (its 0.5 m grid sheets and their index tiles): no published limits
    # (the Tokyo Open Data terms, https://portal.data.metro.tokyo.lg.jp/terms/, and the catalogue's records
    # t000029d0000000019, 20 and 24, read 2026-11-15); Tokyo pays the egress (not an AWS Open Data bucket):
    # two at once
    "gic-tokyo.s3.ap-northeast-1.amazonaws.com": 2,
    # VIRTUAL SHIZUOKA's bucket (AWS Open Data; Shizuoka's LP grid sheets): no published limits (the README,
    # https://github.com/aigidjp/opendata_virtualshizuoka, the AWS registry's virtual_shizuoka.yaml and the
    # prefecture's page https://www.pref.shizuoka.jp/machizukuri/1049255/1052183.html, read 2026-11-15): two at once
    "virtual-shizuoka.s3.ap-northeast-1.amazonaws.com": 2,
}
TILE_LOCKS = 4096  # lock files of tiles (tile_lock): a tile's lock is one of these, by its path
LOCK_WAIT_S = 3600  # longest wait for a host slot or a tile's lock (a download in another job)
# Longest wait of a thread for its turn among the threads of its own process (host_slot's _Queue): they take turns in
# order, so it waits for a few downloads ahead of it; this long only a download that hangs (review of 2026-11-14)
QUEUE_WAIT_S = 6 * 3600
RETRIES = 3

# Requests per minute to a host, for the hosts whose provider publishes a limit (rate_turn): one
# request admitted every 60/n s, shared by every process of the machine (or container). What
# counts as a request is one we make: an attempt of _get, a page of a STAC search, an orthophoto
# tile, a request of the probe; a window or block read through GDAL counts as one (its range
# requests are GDAL's, merged and retried inside GDAL where nothing can wait between them; none
# of these hosts is read that way now). The values stay about 10 % below the published ones.
HOST_RATES_OF: Dict[str, int] = {
    # FSDI, "Fair use" limits of the federal geoservices (https://www.geo.admin.ch/de/allgemeine-
    # nutzungsbedingungen-bgdi, read 2026-11-01; the German page binds): "API Rest Services
    # (general), *.geo.admin.ch ... 40 Requests / Minute"; data.geo.admin.ch (STAC API and its COG
    # files) has no row of its own, so it is taken to fall under it until swisstopo says otherwise
    "data.geo.admin.ch": 36,
    # The same table: "WMTS, wmts.geo.admin.ch ... 1'200 Requests / Minute" (SWISSIMAGE tiles)
    "wmts.geo.admin.ch": 1080,
    # Defra Data Services Platform (DSP), Fair Use Policy, "4. Automated Access and Rate Limits"
    # (https://environment.data.gov.uk/support/faqs/275808874, read 2026-11-01): "Up to 200
    # requests per minute" for standard users and automated services (the EA's LIDAR WCS)
    "environment.data.gov.uk": 180,
    # The Géoplateforme's CGU (https://cartes.gouv.fr/cgu, version of 15 October 2024, annex 3, art. 3.2 "Limite
    # d'usage (Fair use)", read 2026-11-02, French only): limits "en nombre de requêtes par seconde et par IP", per
    # API ("WMS-Raster 40", WMTS "Non soumis à limite d'usage", WFS 30, Téléchargement "5 requêtes/5s avec
    # bannissement de 5 minutes"), HTTP 429 above them for 5 s. Our turns are per host: the WMS-R's 40/s less
    # 10 %, which the orthophoto's WMTS on the same host shares (France's tiles; no WFS or download API is used)
    "data.geopf.fr": 2160,
    # Not a published limit: DAERA's tile caches (Northern Ireland, tiles-eu1.arcgis.com) at the rate the mail to DAERA
    # of 2026-11-15 promises, "at most one request per second" (less 10 %), until DAERA answers (no limits published:
    # the items, the services and OpenDataNI's pages, read 2026-11-15)
    "tiles-eu1.arcgis.com": 54,
}
RATES_DB: Optional[str] = None  # the bucket of rate_turn; None: findaline-rates.sqlite in the system's temporary folder
RATE_WAIT_S = 600  # longest wait for a turn of rate_turn
_rate_limiters: Dict[Tuple[str, str, int], object] = {}  # (database, host, rate) -> pyrate_limiter.Limiter
_rate_lock = threading.Lock()


_sessions = threading.local()


def session() -> requests.Session:
    """The requests.Session of this thread: its connections stay open for the thread's next
    requests (keep-alive, no new TLS handshake per request). One per thread, as requests'
    sessions are not meant to be shared between threads; dropped with its thread."""
    found = getattr(_sessions, "session", None)
    if found is None:
        found = _sessions.session = requests.Session()
    return found


def _host(url: Optional[str]) -> Optional[str]:
    return urlsplit(url).hostname if url and re.match(r"https?://", url) else None


def rate_turn(url: Optional[str], share: float = 1.0):
    """Wait for this request's turn when the host of url has a rate (HOST_RATES_OF), the turns
    spread evenly (one every 60/n s) over every thread and process of the machine: a pyrate-limiter
    SQLite bucket per host in RATES_DB, its writes serialised by a file lock (as osm's Nominatim
    turns). The limits are per client address, so the bucket is in the system's temporary folder,
    not in a data folder (in a container its /tmp: the worker's container is the one that asks).
    RuntimeError after RATE_WAIT_S. Other hosts, and local paths, return at once.

    share < 1: a kind of request that must go slower than the host's rate (the pieces of a split WCS
    tile) also takes a turn of a bucket of its own at that share of the rate (at least 1 a minute), after
    the host's turn: the host's rate still bounds every request, and these stay under their share."""
    host = _host(url)
    per_minute = HOST_RATES_OF.get(host) if host else None
    if not per_minute:
        return
    _turn(host, per_minute)
    if share < 1:
        _turn(host, max(1, int(per_minute * share)))


def _turn(host: str, per_minute: int):
    """A turn of the bucket of host at per_minute requests a minute (rate_turn)."""
    path = RATES_DB or os.path.join(tempfile.gettempdir(), "findaline-rates.sqlite")
    key = (path, host, per_minute)
    with _rate_lock:
        limiter = _rate_limiters.get(key)
        if limiter is None:
            from pyrate_limiter import Limiter, Rate, SQLiteBucket
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            table = "rate_" + re.sub(r"\W", "_", host) + f"_{per_minute}"
            bucket = SQLiteBucket.init_from_file([Rate(1, math.ceil(60000 / per_minute))], table=table,
                                                 db_path=path, use_file_lock=True)
            limiter = _rate_limiters[key] = Limiter(bucket)
    # Asked with no wait (timeout 0), polled: pyrate-limiter's own wait (4.5.1) stamps the permit
    # with the time it planned to wake at (item.timestamp += delay), not the time it woke, so after
    # an oversleep (Windows' timer) the next permit came early, two at once in tests/test_rates.py;
    # a permit asked now is stamped with the bucket's clock (SQLite's) now. (blocking=False fails
    # with a file lock: the limiter passes False to FileLock.acquire as its timeout.) A timeout of
    # 0 also gives up when another process holds the bucket's file lock: the next poll asks again.
    interval = 60 / per_minute
    deadline = time.monotonic() + RATE_WAIT_S
    while not limiter.try_acquire(host, timeout=0):
        if time.monotonic() > deadline:
            raise RuntimeError(f"{host} is busy with the requests of other searches "
                               f"(waited {RATE_WAIT_S // 60} min); try again later")
        time.sleep(interval * (0.1 + 0.2 * random.random()))  # waiters spread; late, never early


# Hosts whose servers send an incomplete TLS chain (only their own certificate, without the intermediate that
# issued it): host -> a file of sources/certs/ with the missing intermediate, which requests to that host trust
# on top of certifi's roots (verify). Browsers and curl on Windows fetch such an intermediate themselves (the
# leaf's Authority Information Access); OpenSSL, so Python and the worker's container, does not.
# geodaten.schleswig-holstein.de (Schleswig-Holstein's index and XYZ files) left out D-TRUST BR CA 1-20-1 2020
# on 2026-11-02 (its leaf valid to 2027-04-15); the file says where it came from, its fingerprint and expiry
CERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
HOST_CA_OF: Dict[str, str] = {
    "geodaten.schleswig-holstein.de": "d-trust-br-ca-1-20-1-2020.pem",
}
_bundles: Dict[str, str] = {}  # file of HOST_CA_OF -> the bundle written (verify)
_bundles_lock = threading.Lock()


def verify(url: Optional[str]):
    """requests' `verify` for a request to url: True (certifi's roots) for every host but those of
    HOST_CA_OF, whose requests verify against a bundle of certifi's roots and the host's missing
    intermediate: written once per process into the system's temporary folder (/tmp in the
    container; named by its content, so processes and versions never mix bundles). The roots stay
    the only anchors: the intermediate only completes a chain to one of them."""
    host = _host(url)
    name = HOST_CA_OF.get(host) if host else None
    if not name:
        return True
    with _bundles_lock:
        path = _bundles.get(name)
        if path is None or not os.path.exists(path):
            with open(requests.certs.where(), "rb") as f:
                roots = f.read()
            with open(os.path.join(CERTS, name), "rb") as f:
                extra = f.read()
            data = roots.rstrip(b"\n") + b"\n\n" + extra
            path = os.path.join(tempfile.gettempdir(), f"findaline-ca-{hashlib.sha256(data).hexdigest()[:16]}.pem")
            if not os.path.exists(path):
                tmp = _part(path)
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            _bundles[name] = path
        return path


def _get(url: str, params=None, timeout: int = 300, binary_types=("image", "octet", "tiff", "multipart"),
         final: Tuple[int, ...] = ()):
    """GET with retries; raises RuntimeError with the server message on failure (without the
    query of the URL or a key's value: cache.clean_error). Every attempt waits for its turn
    (rate_turn) and is counted (servicecounts, the host only; a 200 that is not data counts as
    `other`). A 429 or 503 (the server asks us to slow down) backs off longer: _sleep(attempt + 3),
    about 8, 16 and 32 s. A status in final is an error at once, never asked again (an S3 bucket that
    denies listing answers 403 for a key it does not have: SheetFile(listed=True))."""
    last_error = None
    for attempt in range(RETRIES):
        slow_down = False
        try:
            rate_turn(url)
            with servicecounts.request(url) as counted:
                response = counted.got(requests.get(url, params=params, timeout=timeout,
                                                    headers=cache.http_headers(), verify=verify(url)))
                content_type = response.headers.get("content-type", "")
                if response.status_code == 404:
                    return None
                if response.status_code != 200 or not any(t in content_type for t in binary_types):
                    if response.status_code == 200:
                        counted.outcome = "other"
                    slow_down = response.status_code in (429, 503)
                    if response.status_code in final:
                        raise _Final(f"HTTP {response.status_code}: {response.text[:300]}")
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
            return response
        except _Final as e:
            last_error = e
            break
        except (requests.RequestException, RuntimeError) as e:
            last_error = e
            _sleep(attempt + 3 if slow_down else attempt)
    # No API key from a query in the message, and no value of a service key anywhere in it (a
    # server's answer may echo the token of its request: settings.redact through clean_error)
    raise RuntimeError(cache.clean_error(last_error))


class _Final(RuntimeError):
    """An answer _get does not ask again (its `final` statuses)."""


def _sleep(attempt: int):
    """Exponential backoff with jitter (swisstopo's fair use asks for it), 0.5-1.5 times 2^attempt s."""
    time.sleep(2 ** attempt * (0.5 + random.random()))


def _locks(cache_dir: str, kind: str) -> str:
    folder = os.path.join(cache_dir, cache.LOCKS, kind)
    os.makedirs(folder, exist_ok=True)
    return folder


class _Queue:
    """n places taken in the order asked (a ticket each): threading.Semaphore lets a thread that has just
    released take its place back before a waiter woken for it, so a waiter can lose for an hour.

    A waiter that leaves before its turn (its timeout, or any exception in the wait) gives its ticket up
    (abandoned): the tickets behind it are served as if it had never asked, never stuck behind it."""

    def __init__(self, n: int):
        self.free, self.next_ticket, self.serving = n, 0, 0
        self.abandoned: set = set()
        self.cond = threading.Condition()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """A place, waiting in turn; False after timeout seconds without one (None: no limit)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self.cond:
            ticket, self.next_ticket = self.next_ticket, self.next_ticket + 1
            try:
                while ticket != self.serving or not self.free:
                    left = None if deadline is None else deadline - time.monotonic()
                    if left is not None and left <= 0:
                        self._give_up(ticket)
                        return False
                    self.cond.wait(left)
            except BaseException:
                self._give_up(ticket)
                raise
            self.serving, self.free = self.serving + 1, self.free - 1
            self._skip()
            self.cond.notify_all()  # the next ticket may take a place still free
            return True

    def _give_up(self, ticket: int):
        """A ticket left unserved (under self.cond): skipped when its turn comes, or now when it is due."""
        self.abandoned.add(ticket)
        self._skip()
        self.cond.notify_all()

    def _skip(self):
        while self.serving in self.abandoned:
            self.abandoned.discard(self.serving)
            self.serving += 1

    def release(self):
        with self.cond:
            self.free += 1
            self.cond.notify_all()


_queues: Dict[Tuple[str, str, int], _Queue] = {}  # (lock folder, host, slots) -> its _Queue in this process
_queues_lock = threading.Lock()


@contextlib.contextmanager
def host_slot(cache_dir: str, url: Optional[str]):
    """One of the HOST_SLOTS (HOST_SLOTS_OF) download slots of the host of url, across the
    threads and processes of a data folder: lock files <host>.<n>.lock, each tried in turn,
    waiting while all are taken. A file lock of the OS: a killed process releases it, and the
    files are a fixed few per host. Nothing to wait for without a remote host (a local mirror).

    The threads of one process first queue for as many places as there are slots (_Queue: in the
    order they asked, waiting only for each other's downloads, so up to QUEUE_WAIT_S: a real hang,
    not a busy host), so the file locks are tried by at most that many of them and LOCK_WAIT_S is
    spent waiting for other processes only. Polled at random, the 8 download threads of Slovenia's
    pass for ARSO's 2 slots let a thread lose for an hour to its own siblings ("busy with the
    downloads of other searches", 2026-11-13)."""
    host = _host(url)
    if not host:
        yield
        return
    folder = _locks(cache_dir, "hosts")
    slots = list(range(HOST_SLOTS_OF.get(host, HOST_SLOTS)))
    key = (folder, host, len(slots))
    with _queues_lock:
        queue = _queues.setdefault(key, _Queue(len(slots)))
    if not queue.acquire(QUEUE_WAIT_S):
        raise RuntimeError(f"{host} is busy with this process's own downloads from it "
                           f"(waited {QUEUE_WAIT_S // 60} min); try again later")
    try:
        with _file_slot(folder, host, slots):
            yield
    finally:
        queue.release()


@contextlib.contextmanager
def _file_slot(folder: str, host: str, slots: List[int]):
    """A free lock file of the host's slots (host_slot), waiting up to LOCK_WAIT_S while other processes
    hold them all."""
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        random.shuffle(slots)  # waiters spread over the slots
        for n in slots:
            # A new instance per attempt: filelock's instances are per thread, and two of them
            # on one file exclude each other also within a process (Windows LockFileEx, flock)
            lock = FileLock(os.path.join(folder, f"{host}.{n}.lock"))
            try:
                lock.acquire(blocking=False)
            except Timeout:
                continue
            try:
                yield
            finally:
                lock.release()
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"{host} is busy with the downloads of other searches "
                               f"(waited {LOCK_WAIT_S // 60} min); try again later")
        time.sleep(0.1 + 0.2 * random.random())


@contextlib.contextmanager
def tile_lock(cache_dir: str, path: str):
    """The lock of a cached file, so two searches never download it at once (the second waits
    and then finds it cached). One of TILE_LOCKS lock files chosen by the path, so their number
    stays fixed (on Linux filelock leaves its files behind); two tiles sharing one only wait
    for each other."""
    digest = hashlib.sha256(cache.relative(cache_dir, path).encode()).digest()
    name = f"{int.from_bytes(digest[:4], 'big') % TILE_LOCKS:04d}.lock"
    lock = FileLock(os.path.join(_locks(cache_dir, "tiles"), name))
    try:
        lock.acquire(timeout=LOCK_WAIT_S)
    except Timeout:
        raise RuntimeError(f"{cache.relative(cache_dir, path)} is being downloaded by another search "
                           f"(waited {LOCK_WAIT_S // 60} min); try again later") from None
    try:
        yield
    finally:
        lock.release()


def _part(path: str) -> str:
    """A temporary name next to path, unique per process and thread (searches may run in parallel)."""
    return f"{path}.{os.getpid()}-{threading.get_ident()}.part"


def _remote(url: str) -> str:
    """What rasterio opens for a file of an index: /vsicurl/ (HTTP range requests) for a URL,
    a local path as it is (tests)."""
    return f"/vsicurl/{url}" if re.match(r"https?://", url) else url


# The HTTP statuses GDAL retries (GDAL_HTTP_RETRY_CODES, "Configuration options", "Networking
# options" of GDAL's documentation): its defaults (429, 500, 502-504) and 0, a request that got no
# answer at all (a connection aborted or reset, a timeout). A list replaces GDAL's default rules,
# which retry only some curl errors by their text ("Connection reset by peer", "Operation timed
# out"; not "Connection was aborted" of Windows). GDAL matches a status as a substring of the
# list, so no other status may be a part of it (0 is part of none of the others here).
GDAL_RETRY_CODES = "0,429,500,502,503,504"


def _gdal_http(serial: bool = False) -> rio.Env:
    """GDAL's settings for reading windows of remote files: our User-Agent, no directory
    listing, retries of failed requests (GDAL_RETRY_CODES), neighbouring blocks in one request
    (serial: the ranges of a window one after another, each through GDAL's cache of ranges,
    RANGE_CACHE_BYTES, so neighbouring blocks read in a row fetch a shared tile once).
    Blocks are read in the calling thread (GDAL_NUM_THREADS=1, whatever the environment says):
    with more, the GTiff driver fetches and decodes them in its own threads, whose errors go to
    GDAL's default handler (printed to stderr) instead of the caller's, so gdal_errors would not
    see a failed read there, which then comes back as zeros. Only files named .tif or .tiff
    (LINZ's sheets) are opened."""
    return rio.Env(GDAL_HTTP_USERAGENT=cache.http_headers()["User-Agent"],
                   GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
                   GDAL_HTTP_MAX_RETRY=str(RETRIES), GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_TIMEOUT="120",
                   GDAL_HTTP_RETRY_CODES=GDAL_RETRY_CODES, GDAL_NUM_THREADS="1",
                   GDAL_HTTP_MULTIRANGE="SERIAL" if serial else "YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


# GDAL's errors as rasterio logs them: an error (CE_Failure) that did not make the call fail is
# logged at INFO by the loggers of its error handlers (rasterio._err: log_error), never raised
_GDAL_LOGGERS = ("rasterio._env", "rasterio._err")
_GDAL_ERROR = "GDAL signalled an error"
_errors_of: Dict[int, list] = {}  # thread -> the GDAL errors logged in it while gdal_errors is open
_errors_lock = threading.Lock()


class _GdalErrors(logging.Filter):
    """Collects GDAL's errors for the threads in gdal_errors; passes a record on only as the
    loggers would have without it (INFO is enabled on them for this filter alone)."""

    def filter(self, record) -> bool:
        if record.levelno == logging.INFO and str(record.msg).startswith(_GDAL_ERROR):
            with _errors_lock:
                found = _errors_of.get(record.thread)
            if found is not None:
                found.append(str(record.args[-1]) if record.args else record.getMessage())
        return record.levelno >= logging.getLogger("rasterio").getEffectiveLevel()


def _install_filter():
    for name in _GDAL_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, _GdalErrors) for f in logger.filters):
            logger.addFilter(_GdalErrors())
        if logger.getEffectiveLevel() > logging.INFO:
            logger.setLevel(logging.INFO)


@contextlib.contextmanager
def gdal_errors():
    """The errors GDAL signalled in this thread inside the block, also those of calls that did
    not fail (a list, filled as they come). GDAL takes some failed reads for data: libtiff caches
    a strile offset it could not read as 0, and GDAL's GTiff driver then fills that block with
    nodata, or zeros without nodata ("Cannot read offset/size for strile", libtiff's
    tif_dirread.c, _TIFFFetchStrileValue); /vsicurl/ keeps a range answer cut short (a 206 with
    bytes missing, cpl_vsil_curl.cpp, DownloadRegion: only a debug message). Only such errors
    show it, and rasterio raises none of them for a read that returned."""
    _install_filter()
    found: list = []
    key = threading.get_ident()
    with _errors_lock:
        outer = _errors_of.get(key)
        _errors_of[key] = found
    try:
        yield found
    finally:
        with _errors_lock:
            if outer is None:
                _errors_of.pop(key, None)
            else:
                _errors_of[key] = outer
                outer.extend(found)
