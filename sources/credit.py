"""Who a dataset must be credited to (Credit) and the licences shared by several sources."""

from dataclasses import asdict, dataclass
from typing import Dict, Union

# A placeholder in a credit's attribution or notice (and an orthophoto's attribution or a source's
# note): the year of the run, for terms that ask for the year of the download (LGLN's "© GeoBasis-DE/LGLN
# <year>"); where no run exists (the about page) it reads as YEAR_TEXT
YEAR = "{year}"
YEAR_TEXT = "<year of the run>"


def dated(text: str, year: Union[int, str]) -> str:
    """text with YEAR replaced by year; a text without it stays as it is."""
    return text.replace(YEAR, str(year))


@dataclass(frozen=True)
class Credit:
    """Who a dataset must be credited to and under which terms: recorded with every run
    that used it (run.json), shown in its map and written to its ATTRIBUTION.txt."""
    data: str         # the dataset
    attribution: str  # the notice to show with what is made from it (plain text; YEAR: the run's year)
    licence: str      # short name of the licence or terms of use
    url: str = ""     # where the licence or terms are stated
    notice: str = ""  # more the licence asks for in a notice (citation, disclaimer): ATTRIBUTION.txt only (YEAR too)

    def as_dict(self) -> Dict:
        return asdict(self)


def dated_credit(credit: Dict, year: Union[int, str]) -> Dict:
    """A credit as recorded with a run (Credit.as_dict()) with YEAR in its attribution and notice filled."""
    return {k: dated(v, year) if k in ("attribution", "notice") and isinstance(v, str) else v
            for k, v in credit.items()}


CC_BY = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")
DL_DE_BY = ("dl-de/by-2.0", "https://www.govdata.de/dl-de/by-2-0")
# FOSSGIS's terms of the Overpass API ask for a link to the page where errors in the data are reported
OSM_FIXTHEMAP = "https://www.openstreetmap.org/fixthemap"
OSM_CREDIT = Credit("OpenStreetMap", "© OpenStreetMap contributors", "ODbL 1.0",
                    "https://www.openstreetmap.org/copyright",
                    notice=f"Report errors in the map data: {OSM_FIXTHEMAP}")
# Written with every run's credits (ATTRIBUTION.txt) and on the about page: what is made from the data
# is a changed work (CC BY's "indicate if changes were made", dl-de/by-2.0 §3, OGL, Defra's Fair Use Policy §7)
PROCESSED_NOTE = ("Find-a-Line's lines, heights, profiles and maps are computed from these data, which were "
                  "resampled and combined onto a working grid (changed).")
