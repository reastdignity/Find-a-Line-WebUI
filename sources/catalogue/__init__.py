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
