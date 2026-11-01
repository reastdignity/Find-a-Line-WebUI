"""Source: the layers of a data source, its working CRS, orthophoto, credits and fallbacks."""

from dataclasses import dataclass
from typing import Callable, List, NamedTuple, Optional, Tuple

import cache
from grid import utm_crs

from .credit import Credit
from .layer import Layer

# Finest working resolution: finer grids bring nothing for highlines (clearances are
# metres; 0.5 m LiDAR grids are partly interpolated) and cost 4x per halving
MIN_RESOLUTION = 1.0


@dataclass
class OrthoService:
    """A WMS with orthophotos, requested in WGS84, and/or tiles in Web Mercator (see orthophoto.py)."""
    name: str
    url: Optional[str]  # the WMS; None: the base tiles only
    layer: str
    folder: str      # in the cache; tiles go to <folder>/wm256/{z}/{x}/{y}.jpg
    attribution: str
    # Tiles ({z}/{x}/{y} in Web Mercator, up to base_max_zoom, enlarged above it) with full
    # coverage under this service, where it has no imagery and answers with white
    # (geoportal's HighResolution covers only sheets of 10 cm or finer)
    base_url: Optional[str] = None
    base_max_zoom: int = 19
    # Fair use: detailed tiles (zoom 17 and more) for at most this many groups, circles too
    # (--ortho-detail overrides it)
    detail: Optional[int] = None

    @property
    def ttl_days(self) -> Optional[int]:
        """Days between update checks; None for a dated orthophoto that never changes."""
        return cache.TTL_DAYS["live"] if "/live" in self.folder else None


class ReadmeRow(NamedTuple):
    """The cells of a source's row in README's "Data sources" table (Markdown; tools/source_docs.py)."""
    where: str
    terrain: str
    surface: str = "–"
    ortho: str = "–"


@dataclass
class Source:
    id: str
    name: str
    description: str
    nmt: Layer
    nmpt: Optional[Layer] = None
    countries: Tuple[str, ...] = ()
    # ISO 3166-2 codes in lower case (gb-wls, it-bz): --source auto takes the source only where the
    # centre lies in one of them (and its country is one of countries), before the sources of its
    # country without regions, whatever the order of SOURCES (choose.choose_source); () = the countries
    regions: Tuple[str, ...] = ()
    crs: Optional[str] = None       # working CRS; None = UTM zone of the search centre
    default_resolution: Optional[float] = None  # None: the terrain data's own, at least MIN_RESOLUTION
    ortho: Optional[OrthoService] = None
    note: str = ""                  # licence or quality note printed at the start
    fallback: Optional[str] = "europe"  # source that fills gaps in the data on land
    # Sources that fill, in turn, what the fallback left (Alaska: its IfSAR, then 1/3″)
    more_fallbacks: Tuple[str, ...] = ()
    # Sources of the neighbouring countries or regions that fill, in turn, the gaps on land at the
    # border before the fallback (filling.fill_from_neighbours: only where their offline boxes or
    # bbox reach such a gap, and only when available)
    neighbours: Tuple[str, ...] = ()
    bbox: Optional[Tuple[float, float, float, float]] = None  # (south, north, west, east) for --source auto
    grid_origin: Tuple[float, float] = (0.0, 0.0)  # pixel edges of the data in the working CRS (grid.make_grid)
    # Licences and notices of the data; a source with one credit gives it to its layers,
    # one with more sets each layer's own (europe: FABDEM and Copernicus)
    credits: Tuple[Credit, ...] = ()
    # The working CRS of a centre when crs is None (the USA: NAD83 / UTM, the CRS of the 1 m tiles)
    local_crs: Callable[[float, float], str] = utm_crs
    # The source --source auto takes instead when the terrain layer has no data near the
    # centre (Alaska: its IfSAR where there is no 1 m lidar)
    instead_without_data: Optional[str] = None
    # Its row in README's "Data sources" table (tools/source_docs.py)
    listing: Optional[ReadmeRow] = None
    # Rough boxes (country code, (south, north, west, east)) for the country of a point when it
    # cannot be looked up (offline): choose.OFFLINE_BOXES, in the order of SOURCES. A region's
    # code (gb-wls) gives its country and that region; a source with regions has region boxes only
    offline: Tuple[Tuple[str, Tuple[float, float, float, float]], ...] = ()
    # (lat, lon) of a point with data in every layer, for the source probe (sources/probe.py) and
    # tools/check_source.py; None: no such point (Alaska's 1 m DEM has no data yet)
    sample: Optional[Tuple[float, float]] = None

    def __post_init__(self):
        if self.default_resolution is None:
            self.default_resolution = max(float(self.nmt.native_res), MIN_RESOLUTION)
        for layer in (self.nmt, self.nmpt):
            if layer is not None and layer.credit is None and len(self.credits) == 1:
                layer.credit = self.credits[0]

    @property
    def licence(self) -> str:
        """The licences of the source's data ("" for local files)."""
        return "; ".join(dict.fromkeys(f"{c.data}: {c.licence}" if len(self.credits) > 1 else c.licence
                                       for c in self.credits))

    @property
    def attribution(self) -> str:
        """The notice its data must be shown with ("" for local files)."""
        return "; ".join(dict.fromkeys(c.attribution for c in self.credits))

    def covers(self, lat: float, lon: float) -> bool:
        if self.bbox is None:
            return True
        south, north, west, east = self.bbox
        return south <= lat <= north and west <= lon <= east

    def working_crs(self, lat: float, lon: float) -> str:
        return self.crs or self.local_crs(lat, lon)

    @property
    def fallbacks(self) -> List[str]:
        """The sources that fill gaps on land, in turn."""
        return [self.fallback, *self.more_fallbacks] if self.fallback else []
