"""The sources, one module per family (a country, or the global datasets), and SOURCES in the order --source auto
tries them.

To add a source: a module of its family here (its services, credits and a list SOURCES of
its Source objects) and the module in FAMILIES, before the sources it should win over."""

from typing import Dict

from ..source import Source
from . import austria, canada, denmark, finland, germany, italy, luxembourg, malta, poland, slovakia, spain, switzerland, uk, usa, world

# Spain's Canary Islands before the rest of Spain, Alaska before the rest of the USA, the global ones last
FAMILIES = (poland, switzerland, slovakia, malta, spain, usa, canada, austria, uk, germany, italy, luxembourg, denmark, finland, world)
SOURCES: Dict[str, Source] = {s.id: s for family in FAMILIES for s in family.SOURCES}
