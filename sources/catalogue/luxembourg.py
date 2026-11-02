"""Luxembourg: ACT's BD-L-Lidar2024, terrain and surface models 0.5 m, one national COG each."""

from typing import List

from ..credit import Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks

CC0 = ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
# LUREF / Luxembourg TM, the CRS of the files: scale factor 1 on 6°10' E, so its scale error over the
# country (5.73-6.53° E) stays below 0.002 %
LUREF = "EPSG:2169"

# BD-L-Lidar2024 of the Administration du cadastre et de la topographie (data.public.lu, dataset
# "Lidar 2024 - Relevé 3D du territoire luxembourgeois", flown in the winter of 2024): one
# cloud-optimized GeoTIFF per model for the whole country (float64, LZW, 128 px tiles, nodata -9999,
# centimetre heights, NG95 (NGL); 114 617 x 163 687 px of 0.5 m, 40 GB (MNT) and 43 GB (MNS)), its
# pixel edges on the 0.5 m lattice (the file starts at 48 880.5 m E, 138 809 m N). data.public.lu puts
# each upload into a folder named by its time, so a republished file has a new address: the dataset's
# resources keep their ids (MNT 507842e4-0272-48ab-84b4-33f06ccfe2ea, MNS
# 9c70f408-aae4-45d6-b70b-a75ac6e074a3), and https://data.public.lu/api/1/datasets/
# lidar-2024-releve-3d-du-territoire-luxembourgeois/ (or https://data.public.lu/fr/datasets/r/<id>,
# a redirect) gives their current address. A new upload is a new folder here and in the cache.
LU_RELEASE = "20241223-093912"
LU_FILES = ("https://download.data.public.lu/resources/bd-l-lidar2024-releve-3d-du-territoire-luxembourgeois/"
            f"{LU_RELEASE}")
LU_EXTENT = (48880.5, 56965.5, 106189.0, 138809.0)  # the files' bounds: blocks outside make no request
# CC0 asks for nothing; ACT is credited all the same
LU_CREDIT = Credit("BD-L-Lidar2024 MNT / MNS 0.5 m (ACT, Luxembourg)",
                   "Administration du cadastre et de la topographie (ACT), Luxembourg: Lidar 2024, CC0", *CC0)


def _lidar(kind: str, description: str) -> FileBlocks:
    # Blocks of 1 km (2000 x 2000 px, about 17 x 17 of the file's 128 px tiles): about 4.5 s and
    # 11 MB of float64 read per block, 6-7 MB cached as float32 (blocks of 500 m: 2.5 s and 3.3 MB
    # each, so twice the time per km²). The 1 m working grid averages 2 x 2 pixels.
    return FileBlocks(description, f"luxembourg/lidar2024-{kind.lower()}/{LU_RELEASE[:8]}", LUREF, 0.5, 1000,
                      f"{LU_FILES}/{kind}_Lidar2024.tif", extent=LU_EXTENT, year=2024, bytes_per_tile=6.5e6)


# geoportail.lu's newest orthophoto (open data, CC0) in the map's own tiling, up to zoom 21; above it the
# service answers HTTP 400. No request limits published.
GEOPORTAIL_ORTHO = OrthoService("geoportail.lu orthophoto (ACT)", None, "", "luxembourg/ortho/live",
                                "Orthophoto: ACT Luxembourg (geoportail.lu), CC0",
                                base_url="https://wmts1.geoportail.lu/opendata/wmts/ortho_latest"
                                         "/GLOBAL_WEBMERCATOR_4_V3/{z}/{x}/{y}.jpeg", base_max_zoom=21)


SOURCES: List[Source] = [
    Source(
        id="luxembourg", name="ACT Luxembourg (Lidar 2024 MNT / MNS)",
        description="ACT Luxembourg: BD-L-Lidar2024 terrain and surface models 0.5 m (winter 2024), "
                    "LUREF / Luxembourg TM, NG95 heights",
        # The national COGs read in blocks on their own pixels, so the working grid is LUREF too; its
        # 1 m pixels (edges on whole metres) are the average of 2 x 2 of the data's
        nmt=_lidar("MNT", "Lidar 2024 MNT 0.5 m (terrain)"),
        nmpt=_lidar("MNS", "Lidar 2024 MNS 0.5 m (trees, buildings)"),
        countries=("lu",), crs=LUREF, ortho=GEOPORTAIL_ORTHO, credits=(LU_CREDIT,),
        listing=ReadmeRow("Luxembourg", "ACT BD-L-Lidar2024 MNT, 0.5 m", "ACT BD-L-Lidar2024 MNS, 0.5 m",
                          "geoportail.lu orthophoto"),
        offline=(("lu", (49.44, 50.19, 5.73, 6.54)),), sample=(49.8205, 6.3460),
        neighbours=("france", "rhineland_palatinate"),
        # Flown with the leaves off, but the surface model (the highest return per pixel, over 30 points
        # per m²) still holds the crowns: around Berdorf a median of 24 m above the ground
        note="Data: ACT Luxembourg, CC0. Surveyed in the winter of 2024.",
        coverage=Coverage(provider="ACT", added="2026-11-01", survey="2024")),
]
