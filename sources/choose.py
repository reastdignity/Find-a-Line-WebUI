"""Which source a search uses (--source auto: the country of the centre)."""

import os
from typing import Optional, Tuple

import rasterio as rio
import requests

import osm

from .source import MIN_RESOLUTION, Source
from .layers.files import FileLayer
from .readers.tilebases import mirror_url
from .catalogue import SOURCES

# Rough boxes used when the country cannot be looked up (offline): the sources' own
# (Source.offline), in the order of SOURCES; the first box holding a point wins. A box of a
# region (gb-wls) gives its country here and the region to region_codes
OFFLINE_BOXES = [box for source in SOURCES.values() for box in source.offline]
# The zoom of Nominatim's reverse lookup whose answer names the regions of a point: 8 (county)
# gives ISO3166-2-lvl4 (GB-WLS, DE-NI) and, where there is one, lvl6 (IT-BZ: its lvl4 is IT-32),
# also in mountains, forests and on a coast; 5 (state) gives lvl4 only (tried 2026-11-01:
# tests/data/recorded/nominatim/)
REGION_ZOOM = 8


def _country_of(code: str) -> str:
    """The country of an offline box's code: gb of gb-wls."""
    return code.split("-")[0]


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
            return _country_of(code)
    return None


def region_codes(lat: float, lon: float, cache_dir: str, country: str) -> Tuple[str, ...]:
    """ISO 3166-2 codes (lower case) of the regions of a country holding a point (OpenStreetMap:
    every level Nominatim names, gb-wls; it-32 and it-bz), or a rough guess when offline: the
    first region box of the country holding it; () if none. Asked only where a source has regions."""
    try:
        address = osm.reverse(lat, lon, cache_dir, zoom=REGION_ZOOM).get("address", {})
        codes = tuple(value.lower() for key, value in sorted(address.items())
                      if key.startswith("ISO3166-2-lvl") and isinstance(value, str)
                      and value.lower().startswith(country + "-"))
        if codes:
            return codes
    except (requests.RequestException, ValueError):  # also a user's quota (jobs.QuotaExceeded)
        pass
    for code, (s, n, w, e) in OFFLINE_BOXES:
        if code != _country_of(code) and _country_of(code) == country and s <= lat <= n and w <= lon <= e:
            return (code,)
    return ()


def choose_source(name: str, lat: float, lon: float, cache_dir: str, elevation_file: Optional[str] = None,
                  surface_file: Optional[str] = None, reach: bool = False) -> Tuple[Source, str]:
    """The source to use and why. reach: also ask whether the servers of a source answer now
    (source_unreachable: the project's data server), a request; only the first planning of a search, an
    estimate (and a country run's main process, itself) do: docs/mirror-hosting/spec.md C.3. A source that does
    not answer is then unavailable: auto takes the next source of the place, a named one is an error."""
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
    mirror_url()  # FINDALINE_MIRROR_URL neither an address nor off: refused at every search's start (ValueError)
    if name != "auto":
        why = _cannot_use(SOURCES[name], reach)
        if why:
            raise ValueError(why)
        return SOURCES[name], f"--source {name}"
    code = country_code(lat, lon, cache_dir)
    found = [s for s in SOURCES.values() if code and code in s.countries and s.covers(lat, lon)]
    # A second lookup only for a country with regional sources: nothing changes for the others
    regions = region_codes(lat, lon, cache_dir, code) if any(s.regions for s in found) else ()
    # A region's source wins over its country's (sorted is stable: otherwise the order of SOURCES)
    found = sorted((s for s in found if not s.regions or set(s.regions) & set(regions)), key=lambda s: not s.regions)
    if found:
        source = found[0]
        where = next((r for r in regions if r in source.regions), code).upper()
        why = _cannot_use(source, reach)
        if why:  # e.g. our own Slovak tiles without a copy set up: the next source of the place (Valle d'Aosta's
            # without its mirror: TINITALY, the country's), else europe
            after = next((s for s in found[1:] if not _cannot_use(s, reach)), SOURCES["europe"])
            return after, f"the centre is in {where}, but {why}"
        if source.instead_without_data and source.nmt.has_data_near(lat, lon, cache_dir) is False:
            return (SOURCES[source.instead_without_data],
                    f"the centre is in {where}, but {source.id} has no terrain data near it")
        return source, f"the centre is in {where}"
    return SOURCES["europe"], f"no national source for {code.upper() if code else 'this place'}"


def source_unavailable(source: Source) -> Optional[str]:
    """Why a source cannot be used here, or None."""
    for layer in (source.nmt, source.nmpt):
        why = layer.unavailable() if layer else None
        if why:
            return why
    return None


def source_unreachable(source: Source) -> Optional[str]:
    """Why the servers of a source do not answer now (its layers' reach: the project's data server's start
    check), or None. A request: asked only where a caller passes reach=True (choose_source) and by a country
    run's main process and the probe."""
    for layer in (source.nmt, source.nmpt):
        why = layer.reach() if layer else None
        if why:
            return why
    return None


def _cannot_use(source: Source, reach: bool) -> Optional[str]:
    """source_unavailable, then with reach source_unreachable."""
    return source_unavailable(source) or (source_unreachable(source) if reach else None)
