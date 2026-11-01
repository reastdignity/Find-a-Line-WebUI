"""Finland's source: the TM35 sheet names of its blocks and the files they are read from."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from sources.catalogue import finland  # noqa: E402

# Sheets of the Paituli mirror's dem2m_direct.vrt (2026-11-01) with their lower-left corners: the corners of
# the whole set, its westernmost and easternmost sheets and others spread over the country (all 10 408 of the
# VRT matched when the rule was written)
SHEETS = [("K3213H", 158000, 6624000), ("L2324H", 62000, 6708000), ("L4122E", 320000, 6702000),
          ("M3131G", 182000, 6762000), ("M5211B", 500000, 6816000), ("N3432D", 266000, 6924000),
          ("N5132G", 566000, 6870000), ("P3314B", 236000, 6972000), ("P5412E", 608000, 7014000),
          ("P6114F", 728000, 6972000), ("Q4121E", 320000, 7074000), ("Q5224H", 542000, 7140000),
          ("R5242H", 566000, 7236000), ("S5422D", 602000, 7332000), ("U4311A", 404000, 7434000),
          ("U5244F", 584000, 7524000), ("W4133A", 380000, 7626000), ("X5213F", 536000, 7776000),
          ("K2444F", 104000, 6660000), ("K2444H", 110000, 6660000), ("K2444E", 104000, 6654000),
          ("K2443B", 92000, 6648000)]


@pytest.mark.parametrize("name, e, n", SHEETS)
def test_sheet_names(name, e, n):
    # Every point of the sheet has its name, none outside
    for de, dn in ((0, 0), (5999, 0), (0, 5999), (5999, 5999), (3000, 3000)):
        assert finland.tm35_sheet(e + de, n + dn) == name
    for de, dn in ((-1, 0), (0, -1), (6000, 0), (0, 6000)):
        assert finland.tm35_sheet(e + de, n + dn) != name


def test_outside_the_division():
    assert finland.tm35_sheet(-76001, 6700000) == ""
    assert finland.tm35_sheet(200000, 6569999) == ""
    assert finland.tm35_sheet(200000, 6570000 + 13 * 96000) == ""
    assert finland.tm35_sheet(-76000 + 5 * 192000, 6700000) == ""


def test_block_files():
    """A block of 2 km reads the sheet holding it: the URL of the mirror's folders; its corners
    lie in that sheet."""
    i, j = 261, 3669  # 522-524 km E, 7338-7340 km N: Korouoma
    (name, url, year), = finland.paituli_files(i, j)
    assert name == "T5111G" and year == 0
    assert url == "https://mirrors.nic.funet.fi/index/geodata/mml/dem2m/2008_latest/T5/T51/T5111G.tif"
    m = finland.BLOCK_M
    assert finland.tm35_sheet((i + 1) * m - 1, (j + 1) * m - 1) == name
    assert finland.paituli_files(-100, 3669) == []
