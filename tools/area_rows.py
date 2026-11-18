"""
What the window of the area download shows and does (tools/area_download_tui.py), without the window: the areas of the
catalogue with their continents and sizes, the settings, where each area's tiles go, the links to a share, starting and
stopping a download. No textual here: only the window needs the group `tui`.

The rows are the areas of the coverage map (viewer/src/coverage/coverage.json), their continents and sizes from its
outlines (shapes.json; a region takes its country's continent unless `REGION_CONTINENTS` says where it lies: Guadeloupe
in North America), plus the settings' `extra`. A row's name is its name in the state folder, so a download started by
hand with that name is the same row. The window groups the rows by continent and country (`Row.country`, so a country
may be under two continents): a region and a territory of `PARENTS` (Åland, Puerto Rico, ...) sit under their country,
in the continent where they lie, each showing its own name (`Row.label`) in a country's group, a country-wide row
"Whole country · <source>" (a country of one row in a continent has no group: its row shows its title). An extra row's
country is its `"country"`, else its title's part before ": " when that names a country of `COUNTRIES`, else its title.

The parts of a country-wide source (`PARTS`, `parts()`: the states of the USA's `usa`, the provinces and territories of
Canada's `canada`) are rows too, though no areas of the map: one download of such a country lists and checks millions
of tiles before its first one, at every restart of a pass, a part only its own (Utah, when the rows were made: 15 min
on an empty cache, 73 min with 199 000 tiles cached; the check itself is about fifteen times shorter since, asked by
folder: docs/performance.md, "The check of cached tiles"); a part is also done, and usable, on its own. A part's tiles are the country-wide row's (one
source, one cache folder): a tile on a border is found cached by the second part. A settings' `extra` of a part's name
replaces it (Utah was an extra first, and keeps its name `utah`). The country-wide row of such a source stays, its
label marked "(slow)" (`SLOW`), and the window says why before it starts it (`slow_note`).

The rows of a source with parts download one at a time (`command_of`: `--queue <source>`, area_download.py's queue;
the states, the country-wide row and the territories of `usa` alike), so that starting fifty states is fifty
downloads in turn, in the rows' order (`start`: the ticket), not fifty at once on the eight connections of their
host. The rows of the other sources start at once, as before.

The settings, a JSON file outside the repository (it may name a contact and a share):

    {"state_dir": "<folder>", "contact": "<an e-mail address or an http(s) address>", "default_target": "cache",
     "targets": {"cache": {"data_dir": "<the app's data folder>"},
                 "NAS": {"data_dir": "<a local data folder>", "tiles": "<a share's cache folder>", "min_free_gb": 200,
                         "max_memory_gb": 12}},
     "rows": {"poland": {"target": "NAS", "host_slots": ["opendata.geoportal.gov.pl=2"], "max_memory_gb": 8}},
     "extra": [{"name": "utah", "title": "United States: Utah", "continent": "North America", "area": "osm:Utah",
                "source": "usa", "km2": 219900, "country": "United States"}]}   # "country" may be left out

`max_memory_gb` (a target's, a row's over it; area_download.py's `--max-memory-gb`, a quarter of the machine's memory
unless given, 0 no budget): a pass over it is started again. A target with `tiles` keeps its indexes in `data_dir` and
its tile folders on the share (the source's own, and its stand-in's where they are not on this disk already:
`links_of`): SQLite's WAL does not work over one. The tile folders are symbolic links, made when a
download starts: Windows lets only an administrator make them while Developer Mode is off, so there they take one UAC
window per start.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pyproj
from anyascii import anyascii
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import area_download as ad  # noqa: E402
import cache  # noqa: E402

COVERAGE = os.path.join(REPO, "viewer", "src", "coverage")
TARGETS_FILE = "tui-targets.json"   # in the state folder: the target chosen for each row
# First in the window, in this order (a continent without a row has no group); others follow by name
CONTINENTS = ("Europe", "North America", "Oceania", "South America", "Asia", "Africa")
ELEVATED_SECONDS = 600
ERROR_PRIVILEGE_NOT_HELD = 1314

# The English names of the countries, for the rows' titles; a region is "<country>: <its name of the coverage map>"
COUNTRIES = {
    "at": "Austria", "au": "Australia", "ax": "Åland", "ca": "Canada", "ch": "Switzerland", "cz": "Czechia",
    "de": "Germany", "dk": "Denmark", "es": "Spain", "fi": "Finland", "fr": "France", "gb": "United Kingdom",
    "gl": "Greenland", "is": "Iceland", "it": "Italy", "li": "Liechtenstein", "lu": "Luxembourg", "mt": "Malta",
    "no": "Norway", "nz": "New Zealand", "pl": "Poland", "pr": "Puerto Rico", "si": "Slovenia", "sk": "Slovakia",
    "us": "United States", "vi": "U.S. Virgin Islands",
    "bl": "Saint-Barthélemy", "mf": "Saint-Martin (France)", "pm": "Saint-Pierre and Miquelon", "uy": "Uruguay", "nl": "Netherlands", "fo": "Faroe Islands",
    "mx": "Mexico", "cy": "Cyprus", "ee": "Estonia", "pt": "Portugal", "br": "Brazil", "jp": "Japan",
    "hk": "Hong Kong"}
# A territory's row sits under its country in the window (its title and continent stay its own). Empty: every code is a
# country of its own.
PARENTS = {"bl": "fr", "mf": "fr", "pm": "fr", "pr": "us", "vi": "us", "ax": "fi"}
# Where a region lies when that is not its country's continent: its outline in shapes.json has none (a region's has
# none today; one that has wins). The Canary Islands, Madeira, Svalbard and Jan Mayen stay European by convention.
REGION_CONTINENTS = {"fr-gp": "North America", "fr-mq": "North America", "fr-gf": "South America",
                     "nl-bq1": "North America", "nl-bq2": "North America", "nl-bq3": "North America",
                     "fr-re": "Africa", "fr-yt": "Africa",
                     "jp-13": "Asia", "jp-22": "Asia"}
WHOLE = "Whole country"   # the label of a country-wide row: "Whole country · <source id>"


@dataclass(frozen=True)
class Parts:
    """The parts of a country-wide source that are rows of their own: (name, land km², Nominatim's name when it is
    not "<name>, <country>") each."""
    source: str
    country: str    # a code of COUNTRIES: the rows' country and continent
    dataset: str    # in the title, "<country>: <part> (<dataset>)", where the country's regions of the map have rows of
                    # their own sources under the part's name (Canada: British Columbia); "": "<country>: <part>"
    called: str     # what the parts are, in the note of the country-wide row: "states"
    parts: Tuple[Tuple, ...]


# The land km² are about, as the census offices' tables give them (the US Census Bureau's of 2010, Statistics
# Canada's; written from those figures, not fetched): what a row shows as its size, nothing is computed from them.
# Nominatim's names checked on 2026-11-18, each match's outline against these (a state's outline holds its
# waters: Michigan 1.7 times its land, Prince Edward Island 4.7, Nunavut 2.1): "New York, United States" is the
# city and "Washington, United States" the District of Columbia, hence "... State"; the District's is its city
US_STATES = (
    ("Alabama", 131171), ("Arizona", 294207), ("Arkansas", 134771), ("California", 403466), ("Colorado", 268431),
    ("Connecticut", 12542), ("Delaware", 5047), ("District of Columbia", 158), ("Florida", 138887),
    ("Georgia", 148959), ("Hawaii", 16635), ("Idaho", 214045), ("Illinois", 143793), ("Indiana", 92789),
    ("Iowa", 144669), ("Kansas", 211754), ("Kentucky", 102269), ("Louisiana", 111898), ("Maine", 79883),
    ("Maryland", 25142), ("Massachusetts", 20202), ("Michigan", 146435), ("Minnesota", 206232),
    ("Mississippi", 121531), ("Missouri", 178040), ("Montana", 376962), ("Nebraska", 198974), ("Nevada", 284332),
    ("New Hampshire", 23187), ("New Jersey", 19047), ("New Mexico", 314161),
    ("New York", 122057, "New York State, United States"), ("North Carolina", 125920), ("North Dakota", 178711),
    ("Ohio", 105829), ("Oklahoma", 177660), ("Oregon", 248608), ("Pennsylvania", 115883), ("Rhode Island", 2678),
    ("South Carolina", 77857), ("South Dakota", 196350), ("Tennessee", 106798), ("Texas", 676587), ("Utah", 212818),
    ("Vermont", 23871), ("Virginia", 102279), ("Washington", 172119, "Washington State, United States"),
    ("West Virginia", 62259), ("Wisconsin", 140268), ("Wyoming", 251470))
CA_PROVINCES = (
    ("Alberta", 642317), ("British Columbia", 925186), ("Manitoba", 553556), ("New Brunswick", 71450),
    ("Newfoundland and Labrador", 373872), ("Northwest Territories", 1183085), ("Nova Scotia", 53338),
    ("Nunavut", 1936113), ("Ontario", 917741), ("Prince Edward Island", 5660), ("Quebec", 1365128),
    ("Saskatchewan", 591670), ("Yukon", 474391))
# Alaska is no part of `usa` (its own source and area of the map, us-ak); Puerto Rico and the U.S. Virgin Islands
# are areas of the map already
PARTS = (Parts("usa", "us", "", "states", US_STATES),
         Parts("canada", "ca", "NRCan", "provinces and territories", CA_PROVINCES))
SLOW = "(slow)"   # after the label of the country-wide row of a source with parts: "Whole country · usa (slow)"
# A part whose download ran under another name before it was a row here: a row's name never changes
PART_NAMES = {"United States: Utah": "utah"}


class SettingsError(ValueError):
    """A settings file that cannot be used: its text is shown as it is."""


EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
URL = re.compile(r"^https?://\S+$")


def contact_ok(contact: str) -> bool:
    """A contact a provider can use: an e-mail address with a dotted domain, or an http(s) address."""
    return bool(EMAIL.match(contact) or URL.match(contact))


@dataclass(frozen=True)
class Row:
    """One line of the window."""
    name: str        # in the state folder: slug(title); neither changes, the state files and settings are keyed by it
    title: str
    continent: str
    country: str     # the group under the continent: COUNTRIES' name, after PARENTS
    label: str       # what the row shows under its country: the region's or territory's name, or WHOLE · source
    area: str       # osm:<name>, or a GeoJSON file
    source: str
    resolution: float
    surface: bool    # whether the source has a surface model
    km2: int         # about: from the coverage map's outlines
    host_slots: Tuple[str, ...] = ()
    max_memory_gb: Optional[float] = None   # the row's own budget of a pass; None: the target's, or the default


@dataclass(frozen=True)
class Target:
    """Where a download goes."""
    label: str
    data_dir: str
    tiles: Optional[str] = None   # a share: the tile folders live there, linked from the data folder's cache
    min_free_gb: float = ad.FREE_GB_MIN
    max_memory_gb: Optional[float] = None   # a pass's budget (area_download.py --max-memory-gb); None: its default

    @property
    def disk(self) -> str:
        return self.tiles or self.data_dir


@dataclass(frozen=True)
class Link:
    path: str     # the tile folder in the data folder's cache
    target: str   # ... and on the share
    cache: str    # that cache


@dataclass
class Settings:
    state_dir: str
    targets: Dict[str, Target]
    default_target: str
    rows: Dict[str, Dict] = field(default_factory=dict)
    extra: List[Dict] = field(default_factory=list)
    contact: str = ""


def slug(title: str) -> str:
    """A row's name in the state folder: "Germany: Bavaria" is germany-bavaria."""
    return re.sub(r"[^a-z0-9]+", "-", anyascii(title).lower()).strip("-")


def _read_json(path: str) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _shapes() -> Tuple[Dict[str, str], Dict[str, float]]:
    """The continents of the countries and the km² of the areas, from the coverage map's outlines. A country split at
    its source's box has its `rest` left out, as the map draws that at 30 m."""
    continents, sizes = {}, {}
    geod = pyproj.Geod(ellps="WGS84")
    for feature in _read_json(os.path.join(COVERAGE, "shapes.json"))["features"]:
        properties = feature["properties"]
        area = properties["id"]
        if properties.get("continent"):
            continents[area] = properties["continent"]
        if properties.get("kind") != "rest":
            sizes[area] = sizes.get(area, 0.0) + abs(geod.geometry_area_perimeter(shape(feature["geometry"]))[0]) / 1e6
    return continents, sizes


def catalogue() -> List[Row]:
    """A row for every area of the coverage map, each with its source's default resolution and its name for
    Nominatim (sources.AREA_NAMES, which the country layer reads too)."""
    import sources as src
    areas = _read_json(os.path.join(COVERAGE, "coverage.json"))["areas"]
    regions = _read_json(os.path.join(REPO, "locales", "coverage", "en.json"))
    continents, sizes = _shapes()
    rows = []
    for area, facts in areas.items():
        code = area.split("-")[0]
        parent = PARENTS.get(code, code)
        region = None if area == code else regions[f"region.{area}"]
        title = COUNTRIES[code] if region is None else f"{COUNTRIES[code]}: {region}"   # the row's name: never changes
        source = src.SOURCES[facts["source"]]
        if region is not None:
            label = region
        elif code != parent:
            label = COUNTRIES[code]          # a territory: its own name
        else:
            label = f"{WHOLE} · {source.id}"
            if any(group.source == source.id for group in PARTS):
                label += f" {SLOW}"          # the user, 2026-11-18: the parts are the way; slow_note says why
        continent = continents.get(area) or REGION_CONTINENTS.get(area) or continents[code]
        rows.append(Row(slug(title), title, continent, COUNTRIES[parent], label,
                        f"osm:{src.AREA_NAMES[area]}", source.id, source.default_resolution, source.nmpt is not None,
                        round(sizes[area])))
    return rows


def parts() -> List[Row]:
    """A row for every part of PARTS, under its country in the country's continent: "United States: Texas"
    (united-states-texas) showing "Texas", "Canada: Alberta (NRCan)" (canada-alberta-nrcan) showing
    "Alberta · canada" beside the regions of the map."""
    import sources as src
    continents, _ = _shapes()
    rows = []
    for group in PARTS:
        source = src.SOURCES[group.source]
        country = COUNTRIES[group.country]
        for name, km2, *query in group.parts:
            title = f"{country}: {name} ({group.dataset})" if group.dataset else f"{country}: {name}"
            label = f"{name} · {source.id}" if group.dataset else name
            rows.append(Row(PART_NAMES.get(title, slug(title)), title, continents[group.country], country, label,
                            f"osm:{query[0] if query else f'{name}, {country}'}", source.id,
                            source.default_resolution, source.nmpt is not None, km2))
    return rows


def slow_note(row: Row) -> Optional[str]:
    """What the window says before it starts the country-wide row of a source with parts (its label ends with
    SLOW), None for any other row: the row is kept, the parts are the better way."""
    group = next((g for g in PARTS if g.source == row.source), None)
    if group is None or not (row.label.startswith(WHOLE) and row.label.endswith(SLOW)):
        return None
    return (f"{row.title}: one download of the whole country lists and checks all its tiles at every restart, and "
            f"nothing of it is done before all of it. Its {group.called} are rows of their own.")


def _country_of(title: str) -> Tuple[str, str]:
    """An extra row's country and label from its title: "United States: Utah" is in the United States as Utah, a
    known country's (or territory's) title the whole country (or the territory), any other title its own country."""
    codes = {name: code for code, name in COUNTRIES.items()}
    head, sep, rest = title.partition(": ")
    if sep and head in codes:
        country = COUNTRIES[PARENTS.get(codes[head], codes[head])]
        return country, rest if head == country else title
    if title in codes:
        country = COUNTRIES[PARENTS.get(codes[title], codes[title])]
        return country, WHOLE if title == country else title
    return title, title


def _extra_row(entry: Dict) -> Row:
    """A row of the settings' `extra`, with its source's resolution and surface model unless it says. Its country is
    its `country`, else what its title says (_country_of)."""
    import sources as src
    try:
        source = src.SOURCES[entry["source"]]
        title = entry.get("title", entry["name"])
        country, label = _country_of(title)
        if entry.get("country"):
            given = entry["country"]
            head, sep, rest = title.partition(": ")
            label = rest if sep and slug(head) == slug(given) else WHOLE if slug(title) == slug(given) else title
            codes = {slug(name): code for code, name in COUNTRIES.items()}
            code = codes.get(slug(given))
            country = given if code is None else COUNTRIES[PARENTS.get(code, code)]   # a territory: its country's
            if label == WHOLE and code is not None and code in PARENTS:
                label = title                                                         # ... as the title's would
        if label == WHOLE:
            label = f"{WHOLE} · {source.id}"
        return Row(entry["name"], title, entry.get("continent", "Other"), country, label, entry["area"],
                   source.id, float(entry.get("resolution", source.default_resolution)), source.nmpt is not None,
                   int(entry.get("km2", 0)))
    except KeyError as e:
        raise SettingsError(f"extra area {entry.get('name', entry)}: {e} is missing or not a source") from e


def load_settings(path: str) -> Settings:
    try:
        raw = _read_json(path)
    except OSError as e:
        raise SettingsError(f"{path}: {e.strerror}") from e
    except ValueError as e:
        raise SettingsError(f"{path}: not JSON: {e}") from e
    try:
        targets = {label: Target(label, os.path.abspath(entry["data_dir"]), entry.get("tiles"),
                                 float(entry.get("min_free_gb", ad.FREE_GB_MIN)), _budget(entry))
                   for label, entry in raw["targets"].items()}
        settings = Settings(os.path.abspath(raw["state_dir"]), targets, raw.get("default_target", next(iter(targets))),
                            raw.get("rows", {}), raw.get("extra", []), raw.get("contact", ""))
    except (KeyError, StopIteration) as e:
        raise SettingsError(f"{path}: needs state_dir and targets, each target with data_dir ({e})") from e
    named = [settings.default_target, *(row.get("target") for row in settings.rows.values() if row.get("target"))]
    unknown = sorted({label for label in named if label not in targets})
    if unknown:
        raise SettingsError(f"{path}: no target named {', '.join(unknown)}")
    if settings.contact and not contact_ok(settings.contact):
        raise SettingsError(f"{path}: the contact must be an e-mail address (name@domain.tld) or an http(s) address, "
                            f"not {settings.contact!r}: it goes into the User-Agent of every request")
    return settings


def _budget(entry: Dict) -> Optional[float]:
    value = entry.get("max_memory_gb")
    return None if value is None else float(value)


def rows_of(settings: Settings) -> List[Row]:
    """The window's rows, by continent, country and label: the catalogue's, the parts of the country-wide sources
    and the settings' `extra`, each row's settings on it. An extra of a part's name replaces the part (the settings
    that named Utah before it was one go on as they were); an extra never replaces an area of the map."""
    extra = [_extra_row(entry) for entry in settings.extra]
    named = {row.name for row in extra}
    rows = [*catalogue(), *(row for row in parts() if row.name not in named), *extra]
    known = {row.name for row in rows}
    unknown = sorted(set(settings.rows) - known)
    if unknown:
        raise SettingsError(f"rows of the settings not in the list: {', '.join(unknown)}")
    rows = [_with_settings(row, settings.rows.get(row.name, {})) for row in rows]
    return sorted(_one_spelling(rows), key=order_of)


def _one_spelling(rows: List[Row]) -> List[Row]:
    """Continents, and countries within a continent, whose names slug alike are one (the window's group ids are their
    slugs): "europe" is Europe, "france" or "FRANCE" beside the catalogue's France is France, "Aland" Åland. The
    spelling of CONTINENTS or of the catalogue wins (its rows come first), else the first seen."""
    continents = {slug(name): name for name in CONTINENTS}
    countries: Dict[Tuple[str, str], str] = {}
    spelled = []
    for row in rows:
        continent = continents.setdefault(slug(row.continent), row.continent)
        country = countries.setdefault((slug(continent), slug(row.country)), row.country)
        spelled.append(replace(row, continent=continent, country=country))
    return spelled


def _plain_name(text: str) -> str:
    return anyascii(text).lower()


def order_of(row: Row) -> Tuple:
    """Continents in CONTINENTS' order (others after them, by name), countries by name, in a country the country-wide
    row first, then by label."""
    rank = CONTINENTS.index(row.continent) if row.continent in CONTINENTS else len(CONTINENTS)
    return (rank, row.continent, _plain_name(row.country), row.country, not row.label.startswith(WHOLE),
            _plain_name(row.label), row.title)


def _with_settings(row: Row, entry: Dict) -> Row:
    return replace(row, resolution=float(entry.get("resolution", row.resolution)),
                   host_slots=tuple(entry.get("host_slots", ())), max_memory_gb=_budget(entry))


def targets_chosen(settings: Settings) -> Dict[str, str]:
    """The target of each row changed in the window: the settings' default comes back when its target went away."""
    try:
        chosen = _read_json(os.path.join(settings.state_dir, TARGETS_FILE))
    except (OSError, ValueError):
        return {}
    return {name: label for name, label in chosen.items() if label in settings.targets}


def target_of(row: Row, settings: Settings, chosen: Dict[str, str]) -> str:
    return chosen.get(row.name) or settings.rows.get(row.name, {}).get("target") or settings.default_target


def save_target(name: str, label: str, settings: Settings):
    chosen = targets_chosen(settings)
    chosen[name] = label
    os.makedirs(settings.state_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=settings.state_dir, prefix=TARGETS_FILE)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(chosen, f, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(settings.state_dir, TARGETS_FILE))


def free_gb(path: str) -> Optional[float]:
    """What is free on a target's disk; None for a share that cannot be reached."""
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return None


def states(settings: Settings) -> Dict[str, Dict]:
    """The rows of `area_download.py status`, by name."""
    if not os.path.isdir(settings.state_dir):
        return {}
    return {row["name"]: row for row in ad.areas(settings.state_dir)}


# --- links to a share -------------------------------------------------------------------------------------------

def _plain(path: str) -> str:
    """A path to compare: os.readlink gives Windows' \\\\?\\ and \\\\?\\UNC\\ forms."""
    for prefix, instead in (("\\\\?\\UNC\\", "\\\\"), ("\\\\?\\", "")):
        if path.startswith(prefix):
            path = instead + path[len(prefix):]
    return os.path.normcase(os.path.normpath(path))


def layer_folders(source_id: str) -> List[str]:
    """The tile folders of a source's terrain and surface models, relative to a cache."""
    import sources as src
    source = src.SOURCES[source_id]
    return [layer.folder for layer in (source.nmt, source.nmpt) if layer is not None]


def stand_in_folders(source_id: str) -> List[str]:
    """The tile folders of the source's stand-in (Source.instead_without_data, which a download fetches too:
    area_download.plans_of), those that are not the source's own: `usa/3dep-13/live` for `usa`, `usa/ifsar-5m` for
    `alaska`; [] without a stand-in."""
    import sources as src
    stand_in = src.SOURCES[source_id].instead_without_data
    if not stand_in or stand_in == source_id:
        return []
    own = layer_folders(source_id)
    return [folder for folder in layer_folders(stand_in) if folder not in own]


def links_of(row: Row, target: Target) -> Tuple[List[Link], Optional[str]]:
    """The links a download to this target still needs, and why it cannot start, if so: the folders of the
    source's own layers, which must be on the share (one that holds tiles on this disk, or links elsewhere, stops
    the row), and those of its stand-in, linked when they can be: a stand-in's folder that is there already, with
    tiles on this disk or as a link of its own, stays as it is and stops nothing (a state's 10 m tiles went to the
    local disk until 2026-11-18, and a stand-in may be a world-wide model another download filled)."""
    if target.tiles is None:
        return [], None
    needed = []
    cache_dir = os.path.join(target.data_dir, "cache")

    def link_of(folder: str) -> Link:
        parts = folder.split("/")
        return Link(os.path.join(cache_dir, *parts), os.path.join(target.tiles, *parts), cache_dir)

    for folder in layer_folders(row.source):
        link = link_of(folder)
        if os.path.islink(link.path):
            if _plain(os.readlink(link.path)) != _plain(link.target):
                return [], f"{link.path} links to another folder"
        elif os.path.lexists(link.path):
            if os.listdir(link.path):
                return [], f"{link.path} holds tiles on this disk"
            os.rmdir(link.path)
            needed.append(link)
        else:
            needed.append(link)
    for folder in stand_in_folders(row.source):
        link = link_of(folder)
        if os.path.islink(link.path) or (os.path.lexists(link.path) and os.listdir(link.path)):
            continue
        if os.path.lexists(link.path):
            os.rmdir(link.path)
        needed.append(link)
    return needed, None


def _elevated(links: Sequence[Link], state_dir: str):
    """Windows without Developer Mode: the links by a script run as administrator, one UAC window."""
    def quoted(path: str) -> str:
        return "'" + path.replace("'", "''") + "'"
    script = os.path.join(state_dir, "links.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:  # Windows PowerShell 5.1 reads UTF-8 only with its BOM
        for link in links:
            f.write(f"cmd /c mklink /D {quoted(link.path)} {quoted(link.target)}\n")
    arguments = f"'-NoProfile','-ExecutionPolicy','Bypass','-File','\"{script}\"'"
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList {arguments}"],
                   check=False, timeout=ELEVATED_SECONDS, capture_output=True)


def make_links(links: Sequence[Link], state_dir: str, elevated: Callable = _elevated) -> List[Link]:
    """The links, each folder made on the share first; the links that could not be made are returned. A new cache is
    marked before anything lands in it: without its LAYOUT it would be refused as a cache of another layout."""
    for cache_dir in {link.cache for link in links}:
        try:
            cache.check_layout(cache_dir)
        except SystemExit as e:
            raise OSError(str(e)) from e
    waiting = []
    for link in links:
        os.makedirs(link.target, exist_ok=True)
        os.makedirs(os.path.dirname(link.path), exist_ok=True)
        try:
            os.symlink(link.target, link.path, target_is_directory=True)
        except OSError as e:
            if getattr(e, "winerror", None) != ERROR_PRIVILEGE_NOT_HELD:
                raise
            waiting.append(link)
    if waiting:
        os.makedirs(state_dir, exist_ok=True)
        elevated(waiting, state_dir)
    return [link for link in links if not os.path.islink(link.path)]


# --- starting and stopping --------------------------------------------------------------------------------------

def command_of(row: Row, target: Target, settings: Settings) -> List[str]:
    """`area_download.py run` of a row, as by hand. A row of a source with parts (PARTS: `usa`, `canada`) is in the
    queue of its source: the states, the country-wide row and the territories of that source download one after
    another, in the order they were started (they share a host's connections). The rows of every other source
    start at once, as they always did."""
    command = [sys.executable, os.path.join(HERE, "area_download.py"), "run", row.name, "--area", row.area,
               "--source", row.source, "--resolution", f"{row.resolution:g}", "--data-dir", target.data_dir,
               "--state-dir", settings.state_dir, "--min-free-gb", f"{target.min_free_gb:g}"]
    if row.source in {group.source for group in PARTS}:
        command += ["--queue", row.source]
    for slots in row.host_slots:
        command += ["--host-slots", slots]
    budget = target.max_memory_gb if row.max_memory_gb is None else row.max_memory_gb
    if budget is not None:
        command += ["--max-memory-gb", f"{budget:g}"]
    return command


def _detached() -> Dict:
    """Popen's arguments for a process that outlives this window: a hidden console of its own on Windows (a process
    without any would open a window for each pass), a session of its own on Linux (the terminal's end kills the rest)."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start(row: Row, target: Target, settings: Settings) -> int:
    """The supervisor of a row, detached; its pid. A row running already says so in its log, `run` itself refuses.
    The time of this call is the row's place in its queue (ad.QUEUE_TICKET): rows started in a loop download in
    that order, however their processes come up."""
    os.makedirs(settings.state_dir, exist_ok=True)
    env = dict(os.environ, **{ad.QUEUE_TICKET: repr(time.time())})
    if settings.contact:
        env["FINDALINE_CONTACT"] = settings.contact
    with open(ad.state_file(settings.state_dir, row.name, ".supervisor.out"), "w", encoding="utf-8") as out, \
            open(ad.state_file(settings.state_dir, row.name, ".supervisor.err"), "w", encoding="utf-8") as err:
        process = subprocess.Popen(command_of(row, target, settings), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   cwd=REPO, env=env, close_fds=True, **_detached())
    return process.pid


def stop(names: Sequence[str], settings: Settings):
    """The stop files `area_download.py stop` writes: each supervisor ends its pass within POLL_SECONDS."""
    for name in names:
        with open(ad.state_file(settings.state_dir, name, ".stop"), "w", encoding="utf-8"):
            pass
