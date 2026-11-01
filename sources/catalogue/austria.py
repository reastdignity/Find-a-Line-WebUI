"""BEV (Austria): the ALS DTM and DSM, 1 m, read in blocks from the 50 km COGs of a yearly edition."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks

# The national edition read (its "Stichtag": the date of the data set, not of the surveys). BEV
# publishes one a year (15.09.2019, 2021-2025 on 2026-11-01) at a fixed address with the date in the
# path, listed by its ATOM service feed (BEV_ATOM); each edition has a cache folder of its own and
# never changes. A new edition is a new date here (and the regression entry written again).
BEV_EDITION = "20250915"
BEV_ATOM = "https://data.bev.gv.at/geonetwork/srv/atom/describe/service?uuid=208cff7a-c8aa-42fe-bf4f-2b8156e37528"
BEV_DOWNLOAD = "https://data.bev.gv.at/download/ALS"
BEV_CREDIT = Credit("ALS DTM / DSM Höhenraster 1 m (BEV, Austria)",
                    "Datenquelle: BEV - Bundesamt für Eich- und Vermessungswesen, CC BY 4.0", *CC_BY)
BEV_FILE_M = 50000  # the files' grid: 50 001 x 50 001 px each, named by the lower-left pixel centre
# The 55 files of an edition, (north, east) in km of EPSG:3035 (the same for DTM and DSM, 2019-2025)
BEV_FILES = frozenset((n, e) for n, row in (
    (2550, (4650,)),
    (2600, (4300, 4350, 4400, 4450, 4500, 4550, 4600, 4650, 4700, 4750)),
    (2650, (4250, 4300, 4350, 4400, 4450, 4500, 4550, 4600, 4650, 4700, 4750, 4800)),
    (2700, (4250, 4300, 4350, 4400, 4450, 4500, 4550, 4600, 4650, 4700, 4750, 4800)),
    (2750, (4500, 4550, 4600, 4650, 4700, 4750, 4800, 4850)),
    (2800, (4500, 4550, 4600, 4650, 4700, 4750, 4800)),
    (2850, (4600, 4650, 4700, 4750, 4800))) for e in row)


def bev_files(kind: str, block_m: float = 1000):
    """The file of a block of block_m (a divisor of 50 km) of the DTM or DSM: the 50 km tile
    whose lower-left pixel centre is at or below and left of the block's lower-left corner
    (blocks have their edges on x.5, so each lies inside one tile; the tiles overlap by one
    pixel); none outside the 55 tiles."""
    def files(i: int, j: int):
        e, n = int(i * block_m) // BEV_FILE_M * BEV_FILE_M, int(j * block_m) // BEV_FILE_M * BEV_FILE_M
        if (n // 1000, e // 1000) not in BEV_FILES:
            return []
        name = f"ALS_{kind}_CRS3035RES50000mN{n}E{e}.tif"
        return [(name, f"{BEV_DOWNLOAD}/{kind}/{BEV_EDITION}/{name}", int(BEV_EDITION[:4]))]
    return files


# Blocks of 1 km read from the 7-12 GB COGs (LZW, 512 px tiles): about 2-2.5 MB each
BEV_DTM = FileBlocks("ALS DTM 1 m (terrain)", f"austria/als-dtm/{BEV_EDITION}", "EPSG:3035", 1.0, 1000,
                     bev_files("DTM"), origin=(0.5, 0.5), bytes_per_tile=2.5e6)
BEV_DSM = FileBlocks("ALS DSM 1 m (trees, buildings)", f"austria/als-dsm/{BEV_EDITION}", "EPSG:3035", 1.0, 1000,
                     bev_files("DSM"), origin=(0.5, 0.5), bytes_per_tile=2.5e6)
# basemap.at's orthophoto (Länder flights of different years) in the map's own tiling, up to zoom 19;
# CC BY 4.0, credited "Datenquelle: basemap.at", where its terms ask for "basemap.at" as a link to
# https://basemap.at (attribution_url); no request limits published
BASEMAP_ORTHO = OrthoService("basemap.at Orthofoto", None, "", "austria/ortho/live", "Datenquelle: basemap.at",
                             base_url="https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857"
                                      "/{z}/{y}/{x}.jpeg", base_max_zoom=19, attribution_url="https://basemap.at")


SOURCES: List[Source] = [
    Source(
        id="austria", name="BEV (ALS DTM / DSM)",
        description=f"BEV (Austria): ALS terrain and surface models 1 m, national edition of "
                    f"{BEV_EDITION[6:]}.{BEV_EDITION[4:6]}.{BEV_EDITION[:4]}, ETRS89 / LAEA, EVRF2000 heights",
        # The 50 km COGs read in blocks on their own pixels (centres on whole metres), so the working
        # grid is EPSG:3035 too: its scale error over Austria stays below 0.1 % (UTM 32/33: up to 0.4 %)
        nmt=BEV_DTM, nmpt=BEV_DSM, countries=("at",), crs="EPSG:3035", grid_origin=(0.5, 0.5),
        ortho=BASEMAP_ORTHO, credits=(BEV_CREDIT,),
        neighbours=("swisstopo", "south_tyrol", "slovakia"),
        listing=ReadmeRow("Austria", f"BEV ALS DTM, 1 m (edition {BEV_EDITION[:4]})",
                          f"BEV ALS DSM, 1 m (edition {BEV_EDITION[:4]})", "basemap.at Orthofoto"),
        offline=(("at", (46.37, 49.02, 9.53, 17.17)),), sample=(47.2740, 11.3120),
        note="Data: BEV, CC BY 4.0. The national model is a mosaic of the Länder's surveys of different "
             "years; the edition's date is not the survey date."),
]
