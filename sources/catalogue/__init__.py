"""The sources, one module per family (a country, or the global datasets), and SOURCES in the order --source auto
tries them.

To add a source: a module of its family here (its services, credits and a list SOURCES of
its Source objects) and the module in FAMILIES, before the sources it should win over."""

from typing import Dict

from ..source import Source
from . import austria, canada, czechia, denmark, finland, france, germany, italy, luxembourg, malta, new_zealand, norway, poland, slovakia, spain, switzerland, uk, usa, world
from . import australia
from . import slovenia
from . import arctic
from . import iceland

# Spain's Canary Islands before the rest of Spain, Alaska before the rest of the USA, the global ones last;
# Czechia first: its offline boxes lie inside Poland's and Slovakia's; France before Switzerland, Spain, England,
# Hesse and Luxembourg: their offline boxes reach into France, its own keep clear of their land (the first box
# holding a point wins); Australia (Tasmania and Queensland, each its own region) anywhere before the global
# ones; Slovenia before Austria: Austria's offline box reaches over Triglav; the Arctic (Greenland, Svalbard, Nunavut)
# before Canada: Canada's offline box holds north-western Greenland, and Nunavut's boxes lie inside it; Iceland
# anywhere before the global ones
FAMILIES = (czechia, poland, france, switzerland, slovakia, malta, spain, usa, arctic, canada, slovenia, austria, uk, germany, italy, luxembourg, denmark, finland, norway, new_zealand, australia, iceland, world)
SOURCES: Dict[str, Source] = {s.id: s for family in FAMILIES for s in family.SOURCES}

# Each area of the coverage map (Source.map_areas: ISO 3166-1 alpha-2 or 3166-2, lower case) by its name for
# Nominatim (`osm:<name>`), checked against the coverage map's outlines: an area download's outline
# (tools/area_rows.py) and the territory of a neighbour's layer (country.territory_specs: the outline its cube is
# cut by, which names the partner of a line across a border). An administrative boundary of the area, larger on a
# coast by the territorial waters (tests/test_area_rows.py::test_every_area_of_the_map_is_a_row)
AREA_NAMES: Dict[str, str] = {
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
