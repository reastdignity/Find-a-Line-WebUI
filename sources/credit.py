"""Who a dataset must be credited to (Credit) and the licences shared by several sources."""

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class Credit:
    """Who a dataset must be credited to and under which terms: recorded with every run
    that used it (run.json), shown in its map and written to its ATTRIBUTION.txt."""
    data: str         # the dataset
    attribution: str  # the notice to show with what is made from it (plain text)
    licence: str      # short name of the licence or terms of use
    url: str = ""     # where the licence or terms are stated
    notice: str = ""  # more the licence asks for in a notice (citation, disclaimer): ATTRIBUTION.txt only

    def as_dict(self) -> Dict:
        return asdict(self)


CC_BY = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")
OSM_CREDIT = Credit("OpenStreetMap", "© OpenStreetMap contributors", "ODbL 1.0",
                    "https://www.openstreetmap.org/copyright")
