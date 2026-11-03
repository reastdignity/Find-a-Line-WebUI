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
    # A link for the attribution (a licence page, or the provider's site where its terms ask for a
    # link: basemap.at); the about page and the map show the attribution as a link to it
    attribution_url: Optional[str] = None

    @property
    def ttl_days(self) -> Optional[int]:
        """Days between update checks; None for a dated orthophoto that never changes."""
        return cache.TTL_DAYS["live"] if "/live" in self.folder else None


@dataclass(frozen=True)
class Coverage:
    """How the coverage map shows a source (tools/coverage_data.py writes viewer/src/coverage/coverage.json
    from it, tools/coverage_shapes.py the outlines). Sources only used to fill gaps have none.

    The resolution comes from the source (`default_resolution`, then `rest`), whether trees are known from
    its surface layer, the note on gaps from its first fallback."""
    provider: str           # the provider's short name ("GUGiK", "swisstopo")
    added: str              # ISO date the source reached main (the timeline; CI clones are shallow, so not from git)
    # Its areas on the map (ISO 3166-1 alpha-2 or ISO 3166-2, lower case); () = the source's regions, else
    # its countries. One source per area
    areas: Tuple[str, ...] = ()
    partial: bool = False   # its level is reached in parts of its areas only (drawn hatched)
    rest: Tuple[float, ...] = ()  # the coarser resolutions (metres) of the rest of its areas: a mix
    level: Optional[int] = None   # 1 (≤ 1 m), 2 (2-5 m); None: from the default resolution
    survey: str = ""        # years ("2018", "2017–2023" with an en dash), a code of "survey.<code>", "" unknown
    trees: Optional[str] = None   # "yes", "no", "part"; None: "yes" with a surface layer, else "no"
    min_length: Optional[float] = None  # metres: shorter lines are not reliable (note "short")
    # Codes of further notes (locales/coverage "note.<code>"): "smoothed", "whole_m", "old_survey" (its
    # years: `survey`)
    notes: Tuple[str, ...] = ()
    # (south, north, west, east): the part of a country the source covers, its rest drawn at 30 m; None:
    # the source's bbox (France's overseas regions, the Chatham Islands)
    box: Optional[Tuple[float, float, float, float]] = None


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
    # How the coverage map shows it; None: not on the map (a source only used to fill gaps)
    coverage: Optional[Coverage] = None
    # The surface model's obstacles are told from the terrain's own rock (obstacles.py): every
    # surface model of a survey's points; not FABDEM + Copernicus, whose difference is by
    # construction the trees and buildings FABDEM removed (on the same pixels)
    obstacles: bool = True

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
