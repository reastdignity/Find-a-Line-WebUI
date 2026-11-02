"""Finland: the National Land Survey's elevation model 2 m, read in blocks from its 6 km map sheets on CSC's Paituli
mirror (no key)."""

from typing import List

from ..credit import CC_BY, YEAR, Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.fileblocks import FileBlocks

# ETRS-TM35FIN, the CRS of the files: one transverse Mercator for the whole country (27° E, scale 0.9996), so its
# scale error stays within -0.04 % (27° E) and about +0.1 % (Åland, 19.5° E; the far north-west, 20.5° E)
TM35FIN = "EPSG:3067"

# Korkeusmalli 2 m (NLS, from the laser scanning of 2008-; parts updated where the terrain changed) as CSC's
# Paituli service mirrors it on Funet: one GeoTIFF per 6 x 6 km sheet of the TM35 map sheet division
# (2008_latest/K2/K24/K2444F.tif: float32, LZW, 256 px tiles, 3000 x 3000 px, nodata -9999, millimetre heights,
# N2000), its pixel edges on whole metres; 10-30 MB each, read in windows by HTTP range requests (Accept-Ranges).
# 10 408 sheets (the mirror's dem2m_direct.vrt, 2026-11-01); a sheet without a file (open sea, beyond the eastern
# border) answers 404 and its blocks are missing. The files are replaced in place one by one as NLS updates them
# (Last-Modified of 2020-2026 side by side), so the cache folder is "live": cache update reads its blocks again
# after cache.TTL_DAYS["live"]. NLS's own services (WCS, OGC API Processes) need an api-key. www.nic.funet.fi is
# the base Paituli documents (mirrors.nic.funet.fi serves the same files; until 2026-11-01 it was read): the
# same paths, so the cache folder stays.
PAITULI = "https://www.nic.funet.fi/index/geodata/mml/dem2m/2008_latest"
FI_EXTENT = (62000.0, 6624000.0, 734000.0, 7782000.0)  # the mirror's VRT: blocks outside make no request
# NLS asks for the licensor, the dataset and the time ("contains data from the National Land Survey of Finland
# Topographic Database 06/2014"); the date of the files read is not kept, so the year of the run stands for it.
# CC BY asks to say that the data were changed: "processed" (resampled onto the working grid)
NLS_CREDIT = Credit("Elevation model 2 m (National Land Survey of Finland)",
                    f"Contains data from the National Land Survey of Finland Elevation model 2 m {YEAR}, CC BY 4.0, "
                    "processed", *CC_BY)

# The TM35 sheet division: 1:200 000 sheets of 192 x 96 km from (-76 000, 6 570 000), rows K L M N P Q R S T U V W X
# from the south, columns 2-6 from the west (K4); each split into quarters three times (1 SW, 2 NW, 3 SE, 4 NE:
# K44, K444, K4444 of 24 x 12 km), then into eight sheets of 6 km, A-H by columns from the south-west (A B, C D,
# E F, G H). It names every sheet of the mirror's VRT (tests/test_catalogue.py).
SHEET_ORIGIN = (-76000, 6570000)
SHEET_ROWS = "KLMNPQRSTUVWX"
SHEET_M = 6000


def tm35_sheet(e: int, n: int) -> str:
    """The name of the 6 km TM35 sheet holding the point (e, n) of EPSG:3067 in whole metres; "" outside the
    division."""
    x, y = e - SHEET_ORIGIN[0], n - SHEET_ORIGIN[1]
    row, column = y // 96000, x // 192000
    if not (0 <= row < len(SHEET_ROWS) and 0 <= column <= 4):
        return ""
    name = f"{SHEET_ROWS[row]}{column + 2}"
    x, y, w, h = x % 192000, y % 96000, 192000, 96000
    for _ in range(3):
        w, h = w // 2, h // 2
        i, j = x // w, y // h
        name += str(1 + 2 * i + j)
        x, y = x - i * w, y - j * h
    return name + "ABCDEFGH"[2 * (x // SHEET_M) + y // SHEET_M]


BLOCK_M = 2000  # divides the sheets (their edges on multiples of 2 km), so a block lies inside one sheet


def paituli_files(i: int, j: int):
    """The sheet file of block (i, j) of BLOCK_M: the sheet holding its lower-left corner. The survey years are
    not in the files (0)."""
    name = tm35_sheet(i * BLOCK_M, j * BLOCK_M)
    return [(name, f"{PAITULI}/{name[:2]}/{name[:3]}/{name}.tif", 0)] if name else []


# Blocks of 2 km (1000 x 1000 px, 16-25 of the files' 256 px tiles): about 2 MB each, about 0.5 s
FI_DEM = FileBlocks("NLS elevation model 2 m (terrain)", "finland/dem2m/live", TM35FIN, 2.0, BLOCK_M,
                    paituli_files, extent=FI_EXTENT, bytes_per_tile=2e6)


SOURCES: List[Source] = [
    Source(
        id="finland", name="NLS Finland (elevation model 2 m)",
        description="National Land Survey of Finland: elevation model 2 m from laser scanning (2008-, updated), "
                    "ETRS-TM35FIN, N2000 heights",
        # The sheets read in blocks on their own pixels, so the working grid is ETRS-TM35FIN too. The model
        # covers Åland (ISO "ax"; Nominatim names it "fi": a centre at Mariehamn is "in FI")
        nmt=FI_DEM, countries=("fi", "ax"), crs=TM35FIN, credits=(NLS_CREDIT,),
        listing=ReadmeRow("Finland (with Åland)", "NLS elevation model 2 m", "–",
                          "– (NLS's orthophoto needs an API key)"),
        offline=(("fi", (59.7, 70.1, 19.3, 31.6)),), sample=(66.1695, 27.4881),
        neighbours=("norway",),
        note="Data: National Land Survey of Finland, CC BY 4.0 (through CSC's Paituli mirror). There is no open "
             "surface model (trees, buildings) for Finland: lines over trees or buildings are not recognised. "
             "The terrain model has pixels of 2 m.",
        coverage=Coverage(provider="NLS", added="2026-11-01")),
]
