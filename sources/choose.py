"""Which source a search uses (--source auto: the country of the centre)."""

import os
from typing import Optional, Tuple

import rasterio as rio
import requests

import osm

from .source import MIN_RESOLUTION, Source
from .layers.files import FileLayer
from .catalogue.usa import ALASKA_BOX
from .catalogue import SOURCES

# Rough boxes used when the country cannot be looked up (offline)
OFFLINE_BOXES = [("mt", (35.78, 36.10, 14.15, 14.60)), ("pl", (49.0, 54.9, 14.1, 24.2)),
                 ("es", (27.0, 43.9, -18.6, 4.4)), ("sk", (47.7, 49.65, 16.8, 22.6)),
                 ("ch", (45.8, 47.85, 5.9, 10.5)), ("us", (24.4, 49.4, -125.0, -66.9)), ("us", ALASKA_BOX),
                 ("pr", (17.8, 18.6, -67.4, -65.2))]


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
            return code
    return None


def choose_source(name: str, lat: float, lon: float, cache_dir: str, elevation_file: Optional[str] = None,
                  surface_file: Optional[str] = None) -> Tuple[Source, str]:
    """The source to use and why."""
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
    if name != "auto":
        why = source_unavailable(SOURCES[name])
        if why:
            raise ValueError(why)
        return SOURCES[name], f"--source {name}"
    code = country_code(lat, lon, cache_dir)
    for source in SOURCES.values():
        if code and code in source.countries and source.covers(lat, lon):
            why = source_unavailable(source)
            if why:  # e.g. our own Slovak tiles without a copy set up
                return SOURCES["europe"], f"the centre is in {code.upper()}, but {why}"
            if source.instead_without_data and source.nmt.has_data_near(lat, lon, cache_dir) is False:
                return (SOURCES[source.instead_without_data],
                        f"the centre is in {code.upper()}, but {source.id} has no terrain data near it")
            return source, f"the centre is in {code.upper()}"
    return SOURCES["europe"], f"no national source for {code.upper() if code else 'this place'}"


def source_unavailable(source: Source) -> Optional[str]:
    """Why a source cannot be used here, or None."""
    for layer in (source.nmt, source.nmpt):
        why = layer.unavailable() if layer else None
        if why:
            return why
    return None
