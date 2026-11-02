"""New Zealand's sources: the Topo50 sheet names of their blocks and the files they are read from."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from sources.catalogue import new_zealand as nz  # noqa: E402

# Sheets of the nz-elevation bucket with the lower-left corners of their files (2026-11-02): the 1 m DEM's
# northernmost (AS21), southernmost (CJ10), westernmost (CD06) and easternmost (BD46) sheets, Wellington,
# Castle Hill, and the 8 m DEM's southernmost (CK08) and westernmost (CD04) sheets (all 449 names of the
# 8 m DEM and the 424 of the 1 m DEM matched when the rule was written)
SHEETS = [("AS21", 1492000, 6198000), ("CJ10", 1228000, 4758000), ("CD06", 1132000, 4938000),
          ("BD46", 2092000, 5802000), ("BQ31", 1732000, 5406000), ("BW21", 1492000, 5190000),
          ("CK08", 1180000, 4722000), ("CD04", 1084000, 4938000), ("BF45", 2068000, 5730000)]


@pytest.mark.parametrize("name, e, n", SHEETS)
def test_sheet_names(name, e, n):
    # Every point of the sheet has its name (its west and south edges too), none outside
    for de, dn in ((0, 0), (23999, 0), (0, 35999), (23999, 35999), (12000, 18000)):
        assert nz.topo50_sheet(e + de, n + dn) == name
    for de, dn in ((-1, 0), (0, -1), (24000, 0), (0, 36000)):
        assert nz.topo50_sheet(e + de, n + dn) != name


def test_outside_the_division():
    assert nz.topo50_sheet(987999, 6000000) == ""
    assert nz.topo50_sheet(1500000, 6810000) == ""
    assert nz.topo50_sheet(988000 + 100 * 24000, 6000000) == ""
    assert nz.topo50_sheet(988000, 6810000 - 24 * 24 * 36000 - 1) == ""


def test_block_files():
    """A block of 1 km (8 m DEM: 4 km from (0, 2000)) reads the sheet holding it: the bucket's URL; its
    corners lie in that sheet."""
    i, j = 1505, 5203  # Castle Hill
    (name, url, year), = nz.NZ_DEM.index.files(i, j)
    assert name == "BW21" and year == 0
    assert url == "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/new-zealand/new-zealand/dem_1m/2193/BW21.tiff"
    assert nz.topo50_sheet((i + 1) * nz.NZ_BLOCK_M - 1, (j + 1) * nz.NZ_BLOCK_M - 1) == name
    (name, url, _), = nz.NZ_DSM.index.files(i, j)
    assert url.endswith("/new-zealand/new-zealand/dsm_1m/2193/BW21.tiff")
    (name, url, _), = nz.NZ_DEM_8M.index.files(376, 1300)
    assert name == "BW21"
    assert url.endswith("/new-zealand/new-zealand-contour/dem_8m/2193/BW21.tiff")
    assert nz.NZ_DEM.index.files(-100, 5203) == []


@pytest.mark.parametrize("block_m, origin", [(nz.NZ_BLOCK_M, (0, 0)), (nz.CONTOUR_BLOCK_M, nz.CONTOUR_ORIGIN)])
def test_blocks_inside_one_sheet(block_m, origin):
    """The blocks' edges lie on the sheets' edges: each block's four corners are in one sheet."""
    for e in range(988000, 988000 + 48 * 24000, 4000):
        for n in range(4700000, 6234000, 6000):
            i, j = (e - origin[0]) // block_m, (n - origin[1]) // block_m
            left, bottom = i * block_m + origin[0], j * block_m + origin[1]
            names = {nz.topo50_sheet(x, y) for x in (left, left + block_m - 1) for y in (bottom, bottom + block_m - 1)}
            assert len(names) == 1, (e, n)
