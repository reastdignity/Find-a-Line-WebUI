"""
What the window of the area download shows and does (tools/area_download_tui.py), without the window: the areas of the
catalogue with their continents and sizes, the settings, where each area's tiles go, the links to a share, starting and
stopping a download. No textual here: only the window needs the group `tui`.

The rows are the areas of the coverage map (viewer/src/coverage/coverage.json), their continents and sizes from its
outlines (shapes.json; a region takes its country's continent), plus the settings' `extra`. A row's name is its name in
the state folder, so a download started by hand with that name is the same row.

The settings, a JSON file outside the repository (it may name a contact and a share):

    {"state_dir": "<folder>", "contact": "<address>", "default_target": "cache",
     "targets": {"cache": {"data_dir": "<the app's data folder>"},
                 "NAS": {"data_dir": "<a local data folder>", "tiles": "<a share's cache folder>", "min_free_gb": 200}},
     "rows": {"poland": {"target": "NAS", "host_slots": ["opendata.geoportal.gov.pl=2"]}},
     "extra": [{"name": "utah", "title": "United States: Utah", "continent": "North America", "area": "osm:Utah",
                "source": "usa", "km2": 219900}]}

A target with `tiles` keeps its indexes in `data_dir` and its tile folders on the share: SQLite's WAL does not work over
one. The tile folders are symbolic links, made when a download starts: Windows lets only an administrator make them
while Developer Mode is off, so there they take one UAC window per start.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
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
CONTINENTS = ("Europe", "North America", "Oceania")   # first in the window; others follow by name
ELEVATED_SECONDS = 600
ERROR_PRIVILEGE_NOT_HELD = 1314

# The English names of the countries, for the rows' titles; a region is "<country>: <its name of the coverage map>"
COUNTRIES = {
    "at": "Austria", "au": "Australia", "ax": "Åland", "ca": "Canada", "ch": "Switzerland", "cz": "Czechia",
    "de": "Germany", "dk": "Denmark", "es": "Spain", "fi": "Finland", "fr": "France", "gb": "United Kingdom",
    "gl": "Greenland", "is": "Iceland", "it": "Italy", "li": "Liechtenstein", "lu": "Luxembourg", "mt": "Malta",
    "no": "Norway", "nz": "New Zealand", "pl": "Poland", "pr": "Puerto Rico", "si": "Slovenia", "sk": "Slovakia",
    "us": "United States", "vi": "U.S. Virgin Islands"}

# Each area's name for Nominatim (`osm:<name>`), checked against the coverage map's outlines
OSM_NAMES = {
    "at": "Österreich", "au-qld": "Queensland", "au-tas": "Tasmania", "ax": "Åland", "ca": "Canada",
    "ca-bc": "British Columbia", "ca-nu": "Nunavut", "ch": "Schweiz", "cz": "Česko",
    "de-bb": "Brandenburg, Deutschland", "de-be": "Berlin", "de-bw": "Baden-Württemberg", "de-by": "Bayern",
    "de-he": "Hessen", "de-mv": "Mecklenburg-Vorpommern", "de-ni": "Niedersachsen", "de-nw": "Nordrhein-Westfalen",
    "de-rp": "Rheinland-Pfalz", "de-sh": "Schleswig-Holstein", "de-sl": "Saarland", "de-sn": "Sachsen",
    "de-st": "Sachsen-Anhalt", "dk": "Danmark", "es": "España", "es-cn": "Canarias", "fi": "Suomi", "fr": "France",
    "gb-eng": "England", "gb-sct": "Scotland", "gb-wls": "Wales", "gl": "Kalaallit Nunaat", "is": "Ísland",
    "it-bz": "Provincia autonoma di Bolzano", "it-tn": "Provincia autonoma di Trento", "li": "Liechtenstein",
    "lu": "Luxembourg", "mt": "Malta", "no": "Norge", "no-21": "Svalbard", "no-22": "Jan Mayen", "nz": "New Zealand",
    "pl": "Polska", "pr": "Puerto Rico", "si": "Slovenija", "sk": "Slovensko", "us": "United States",
    "us-ak": "Alaska", "vi": "United States Virgin Islands"}


class SettingsError(ValueError):
    """A settings file that cannot be used: its text is shown as it is."""


@dataclass(frozen=True)
class Row:
    """One line of the window."""
    name: str        # in the state folder
    title: str
    continent: str
    area: str        # osm:<name>, or a GeoJSON file
    source: str
    resolution: float
    surface: bool    # whether the source has a surface model
    km2: int         # about: from the coverage map's outlines
    host_slots: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Target:
    """Where a download goes."""
    label: str
    data_dir: str
    tiles: Optional[str] = None   # a share: the tile folders live there, linked from the data folder's cache
    min_free_gb: float = ad.FREE_GB_MIN

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
    """A row for every area of the coverage map, each with its source's default resolution."""
    import sources as src
    areas = _read_json(os.path.join(COVERAGE, "coverage.json"))["areas"]
    regions = _read_json(os.path.join(REPO, "locales", "coverage", "en.json"))
    continents, sizes = _shapes()
    rows = []
    for area, facts in areas.items():
        country = area.split("-")[0]
        title = COUNTRIES[country] if area == country else f"{COUNTRIES[country]}: {regions[f'region.{area}']}"
        source = src.SOURCES[facts["source"]]
        rows.append(Row(slug(title), title, continents[country], f"osm:{OSM_NAMES[area]}", source.id,
                        source.default_resolution, source.nmpt is not None, round(sizes[area])))
    return rows


def _extra_row(entry: Dict) -> Row:
    """A row of the settings' `extra`, with its source's resolution and surface model unless it says."""
    import sources as src
    try:
        source = src.SOURCES[entry["source"]]
        return Row(entry["name"], entry.get("title", entry["name"]), entry.get("continent", "Other"), entry["area"],
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
                                 float(entry.get("min_free_gb", ad.FREE_GB_MIN)))
                   for label, entry in raw["targets"].items()}
        settings = Settings(os.path.abspath(raw["state_dir"]), targets, raw.get("default_target", next(iter(targets))),
                            raw.get("rows", {}), raw.get("extra", []), raw.get("contact", ""))
    except (KeyError, StopIteration) as e:
        raise SettingsError(f"{path}: needs state_dir and targets, each target with data_dir ({e})") from e
    named = [settings.default_target, *(row.get("target") for row in settings.rows.values() if row.get("target"))]
    unknown = sorted({label for label in named if label not in targets})
    if unknown:
        raise SettingsError(f"{path}: no target named {', '.join(unknown)}")
    return settings


def rows_of(settings: Settings) -> List[Row]:
    """The window's rows, by continent and title: the catalogue's and the settings' `extra`, each row's settings on it."""
    rows = [*catalogue(), *(_extra_row(entry) for entry in settings.extra)]
    known = {row.name for row in rows}
    unknown = sorted(set(settings.rows) - known)
    if unknown:
        raise SettingsError(f"rows of the settings not in the list: {', '.join(unknown)}")
    rows = [_with_settings(row, settings.rows.get(row.name, {})) for row in rows]
    order = {continent: k for k, continent in enumerate(CONTINENTS)}
    return sorted(rows, key=lambda row: (order.get(row.continent, len(order)), row.continent, row.title))


def _with_settings(row: Row, entry: Dict) -> Row:
    return Row(row.name, row.title, row.continent, row.area, row.source, float(entry.get("resolution", row.resolution)),
               row.surface, row.km2, tuple(entry.get("host_slots", ())))


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


def links_of(row: Row, target: Target) -> Tuple[List[Link], Optional[str]]:
    """The links a download to this target still needs, and why it cannot start, if so."""
    if target.tiles is None:
        return [], None
    needed = []
    for folder in layer_folders(row.source):
        parts = folder.split("/")
        cache_dir = os.path.join(target.data_dir, "cache")
        link = Link(os.path.join(cache_dir, *parts), os.path.join(target.tiles, *parts), cache_dir)
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
    """`area_download.py run` of a row, as by hand."""
    command = [sys.executable, os.path.join(HERE, "area_download.py"), "run", row.name, "--area", row.area,
               "--source", row.source, "--resolution", f"{row.resolution:g}", "--data-dir", target.data_dir,
               "--state-dir", settings.state_dir, "--min-free-gb", f"{target.min_free_gb:g}"]
    for slots in row.host_slots:
        command += ["--host-slots", slots]
    return command


def _detached() -> Dict:
    """Popen's arguments for a process that outlives this window: a hidden console of its own on Windows (a process
    without any would open a window for each pass), a session of its own on Linux (the terminal's end kills the rest)."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start(row: Row, target: Target, settings: Settings) -> int:
    """The supervisor of a row, detached; its pid. A row running already says so in its log, `run` itself refuses."""
    os.makedirs(settings.state_dir, exist_ok=True)
    env = dict(os.environ)
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
