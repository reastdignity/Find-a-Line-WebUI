"""The Netherlands: the European part on PDOK's AHN4 (terrain and surface models 0.5 m, WCS), and Caribbean
Netherlands (Saba, Sint Eustatius, Bonaire) on the AHN's whole-island 0.5 m files of 2023, read in blocks."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks
from ..layers.wcs import WcsTiles
from .luxembourg import CC0

# Amersfoort / RD New, the CRS of the AHN: an oblique stereographic projection with scale 0.9999079 at its centre
# (Amersfoort), so its scale error over the European Netherlands stays within -0.01 % and +0.016 %
RD_NEW = "EPSG:28992"

# PDOK's WCS 2.0.1 of the Actueel Hoogtebestand Nederland (Rijkswaterstaat): AHN4 (flown 2020-2022), coverages
# dtm_05m (the ground points gridded by squared IDW) and dsm_05m (every point but water), float32 0.5 m in RD New,
# NAP heights in millimetres, pixel edges on whole metres (the grid's origin 10 000 / 618 750), extent 10 000-280 000
# / 306 250-618 750, nodata 3.4e38 (water and, in the DTM, buildings: filled from europe). Its MapServer answers a
# deflated GeoTIFF and refuses more than 4000 px a side (MAXSIZE=4000, HTTP 400): tiles of 1 km (2000 px, about
# 8.7 MB and 3.5 s at the ENCI quarry; 2 km took 31 MB and 10 s), 64 MB of float32 a tile less than 2 km's.
# The address PDOK's pages give since its renaming (https://www.pdok.nl/ogc-webservices/-/article/
# actueel-hoogtebestand-nederland-ahn, read 2026-11-15); the older .../rws/ahn/wcs/v1_0 answers the same bits and
# advertises this one. CC0 (the WCS's AccessConstraints, "Fees NONE"). AHN4 is frozen: a static folder. AHN5
# (2023-2024, three quarters of the country) and AHN6 (from 2025) are files only (docs/roadmap.md, batch 5)
NL_WCS = "https://service.pdok.nl/rws/actueel-hoogtebestand-nederland/wcs/v1_0"
NL_CREDIT = Credit("AHN4 DTM / DSM 0.5 m (PDOK, the Netherlands)",
                   "Actueel Hoogtebestand Nederland (AHN4), PDOK, CC0", *CC0)
# The European Netherlands (the Wadden Islands to South Limburg); it reaches over Belgium's north and Germany's
# border strip, whose sources (north_rhine_westphalia, lower_saxony) come first in SOURCES
NL_BOX = (50.75, 53.56, 3.35, 7.23)


def _ahn4(coverage: str, description: str) -> WcsTiles:
    return WcsTiles(description, NL_WCS, coverage, RD_NEW, f"netherlands/ahn4-{coverage[:3]}", native_res=0.5,
                    fetch_res=0.5, tile_px=2000)


# Beeldmateriaal Nederland's newest aerial photo (8 cm, "Actueel_orthoHR") on PDOK's WMTS in the map's own tiling
# up to zoom 21 (Fees none, AccessConstraints none; CC BY 4.0 as Beeldmateriaal's open data). No limits published
NL_ORTHO = OrthoService("PDOK aerial photo (Beeldmateriaal Nederland)", None, "", "netherlands/ortho/live",
                        "Luchtfoto: Beeldmateriaal Nederland (PDOK), CC BY 4.0", attribution_url=CC_BY[1],
                        base_url="https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857"
                                 "/{z}/{x}/{y}.jpeg", base_max_zoom=21)

# Caribbean Netherlands: the AHN's survey of 2023-2024 (Het Waterschapshuis / Beeldmateriaal Nederland; Saba and
# Sint Eustatius flown at the turn of 2023-24, Bonaire's lidar then too), its dataroom
# (https://www.beeldmateriaal.nl/dataroom-caribisch-nederland, read 2026-11-15): "De data is beschikbaar onder de
# Creative Commons Naamsvermelding 4.0 licentie", no credit wording given. One terrain (02a_DTM_50cm, M_*) and
# one surface model (03a_DSM_50cm, R_*) per island: float32 0.5 m, tiled 256, DEFLATE, overviews, nodata 3.4e38
# (the sea), pixel edges on whole metres; the files name only a LOCAL_CS, their coordinates those of the island's
# own CRS (EPSG:10641 Saba DPnet, 10745 Sint Eustatius DPnet long, 10759 Bonaire DPnet, PROJ 9.8; checked at The
# Quill and Mount Scenery), so the layers force it (FileBlocks(force_crs=True)). The addresses (dated 2025-03-19)
# answer 307 to Hetzner's object storage. The DTM has pinholes under forest (at The Quill 43 % of 0.5 m pixels
# valid, 81 % at 1 m, 97 % at 2 m; Saba's summit 54 % at 1 m): the 2 m working grid averages them away, what
# stays is filled from europe.
BQ_FILES = "https://basisdata.nl/hwh-ortho/Caribisch_NL/LiDAR/caribisch"
BQ_DATAROOM = "https://www.beeldmateriaal.nl/dataroom-caribisch-nederland"
BQ_CREDIT = Credit("AHN Caribisch Nederland 2023-2024 DTM / DSM 0.5 m (Het Waterschapshuis / Beeldmateriaal)",
                   "AHN Caribisch Nederland 2023-2024 (Het Waterschapshuis / Beeldmateriaal Nederland), CC BY 4.0",
                   *CC_BY, notice=f"Source: {BQ_DATAROOM}")
BQ_ATTRIBUTION = "Luchtfoto: Beeldmateriaal Nederland, CC BY 4.0"


class Island:
    """An island of Caribbean Netherlands: its folder and file names, CRS, the files' extent (left, bottom, right,
    top in it), its box (south, north, west, east: choosing and offline) and its RGB orthophoto mosaic of 2024 on
    Ellipsis Drive's WMTS (the dataroom's links; a KVP GetTile in the map's own tiling, matrix set EPSG:3857, PNG,
    to zoom 22; the layer's identifier is that of its upload, 2025-05-27)."""

    def __init__(self, id_: str, key: str, folder: str, name: str, crs: str, extent, box, area: str, wmts: str,
                 layer: str):
        self.id, self.key, self.folder, self.name, self.crs, self.extent = id_, key, folder, name, crs, extent
        self.box, self.area = box, area
        self.ortho = OrthoService(
            f"Beeldmateriaal orthophoto 2024 ({name})", None, "", f"caribbean_nl/ortho/{key}-2024", BQ_ATTRIBUTION,
            attribution_url=CC_BY[1],
            base_url=f"https://api.ellipsis-drive.com/v3/ogc/wmts/{wmts}?service=WMTS&request=GetTile&version=1.0.0"
                     f"&layer={layer}&style=default&tilematrixset=EPSG:3857&tilematrix={{z}}&tilerow={{y}}"
                     f"&tilecol={{x}}&format=image/png", base_max_zoom=21)

    def layer(self, kind: str) -> FileBlocks:
        """Its DTM or DSM in blocks of 1 km (2000 x 2000 px) on the file's own pixels, its CRS forced."""
        prefix, part = ("M", "02a_DTM_50cm") if kind == "dtm" else ("R", "03a_DSM_50cm")
        what = "terrain" if kind == "dtm" else "trees, buildings"
        return FileBlocks(f"AHN {self.name} 2023 {kind.upper()} 0.5 m ({what})",
                          f"caribbean_nl/ahn-{kind}-2023/{self.key}", self.crs, 0.5, 1000,
                          f"{BQ_FILES}/{self.folder}/{part}/{prefix}_{self.key.upper()}2023.TIF", extent=self.extent,
                          year=2023, bytes_per_tile=6e6, force_crs=True)


# Areas: ISO 3166-2:NL's special municipalities (NL-BQ1 Bonaire, NL-BQ2 Saba, NL-BQ3 Sint Eustatius), as Natural
# Earth's admin-1 codes them; Nominatim names them country "nl", their own codes (BQ-BO, BQ-SA, BQ-SE) only at zoom
# 10, so the sources are chosen by their boxes (Source.bbox, as Alaska), not by regions
SABA = Island("saba", "saba", "Saba", "Saba", "EPSG:10641", (2000.0, -1000.0, 8000.0, 4000.0),
              (17.60, 17.66, -63.27, -63.20), "nl-bq2", "37a9029d-7578-4471-826d-3b40d721b83b",
              "007963d5-7a71-4d40-b6ce-b4440306244f_786eb116-19ff-4406-bd3e-3d03bf8b89af")
STATIA = Island("sint_eustatius", "statia", "St_Eustatius", "Sint Eustatius", "EPSG:10745",
                (499000.0, 1930000.0, 506000.0, 1938000.0),
                (17.46, 17.53, -63.00, -62.93), "nl-bq3", "cc50d13b-33cf-4d6e-ab41-9e5fb4651478",
                "e4db515f-ac3e-4bee-aaae-bfa27f7d1dae_4d242928-ebbf-4ddd-9e65-77a4f1058aaf")
BONAIRE = Island("bonaire", "bonaire", "Bonaire", "Bonaire", "EPSG:10759", (4000.0, 4000.0, 30000.0, 36000.0),
                 (11.97, 12.32, -68.43, -68.18), "nl-bq1", "07a0f368-478f-4377-a753-c66d7b0c3f6f",
                 "f462790a-88ab-404c-9e6c-83fca88ccfb3_e0ed4080-c898-43e0-965c-a4310de2da31")
# A working grid of 2 m: at 1 m the DTM's pinholes under forest (19 % of The Quill's pixels within 500 m, 46 % at
# Saba's summit) are filled from 30 m data and no anchor stands at a filled seam, so a search at The Quill found 20
# lines in 5 spots at 1 m and 299 lines at 2 m (3 % filled; 2026-11-15, radius 500 m, 20-150 m)
BQ_RESOLUTION = 2.0
BQ_NOTE = ("Data: AHN Caribisch Nederland 2023-2024 (Het Waterschapshuis / Beeldmateriaal Nederland), CC BY 4.0. "
           "Its terrain model has small holes under forest, averaged on the 2 m working grid; the rest is filled "
           "from 30 m data.")


def _island(island: Island, sample) -> Source:
    return Source(
        id=island.id,
        name=f"AHN Caribisch Nederland 2023 ({island.name})",
        description=f"AHN Caribisch Nederland ({island.name}): lidar terrain and surface models 0.5 m (2023-2024), "
                    f"{island.name} DPnet ({island.crs})",
        nmt=island.layer("dtm"), nmpt=island.layer("dsm"), countries=("nl",), bbox=island.box, crs=island.crs,
        default_resolution=BQ_RESOLUTION, ortho=island.ortho, credits=(BQ_CREDIT,),
        listing=ReadmeRow(f"{island.name} (Caribbean Netherlands)", "AHN Caribisch Nederland DTM, 0.5 m",
                          "AHN Caribisch Nederland DSM, 0.5 m", "Beeldmateriaal orthophoto 2024"),
        offline=(("nl", island.box),), sample=sample, note=BQ_NOTE,
        coverage=Coverage(provider="Het Waterschapshuis", added="2026-11-15", areas=(island.area,),
                          survey="2023–2024"))


SOURCES: List[Source] = [
    _island(SABA, (17.6350, -63.2370)),        # Mount Scenery
    _island(STATIA, (17.4783, -62.9600)),      # The Quill (R70)
    _island(BONAIRE, (12.2830, -68.3900)),     # Brandaris
    Source(
        id="netherlands", name="PDOK AHN4 (DTM / DSM 0.5 m)",
        description="PDOK's AHN4 (Rijkswaterstaat): lidar terrain and surface models 0.5 m (2020-2022) from its WCS, "
                    "Amersfoort / RD New, NAP heights",
        # Tiles of 0.5 m on the service's own pixels, averaged 2 x 2 on the 1 m working grid (as Luxembourg's)
        nmt=_ahn4("dtm_05m", "AHN4 DTM 0.5 m (terrain)"), nmpt=_ahn4("dsm_05m", "AHN4 DSM 0.5 m (trees, buildings)"),
        countries=("nl",), bbox=NL_BOX, crs=RD_NEW, ortho=NL_ORTHO, credits=(NL_CREDIT,),
        listing=ReadmeRow("Netherlands (European part)", "PDOK AHN4 DTM, 0.5 m (WCS)", "PDOK AHN4 DSM, 0.5 m (WCS)",
                          "PDOK aerial photo (Beeldmateriaal)"),
        offline=(("nl", NL_BOX),), sample=(50.8258, 5.6866),  # the ENCI quarry at Maastricht (R69)
        # North Rhine-Westphalia only: Lower Saxony declares six neighbours already, the most a country layer's
        # cube can name (countcube.PARTNERS); its border with the Netherlands is flat land (Groningen to Twente)
        neighbours=("north_rhine_westphalia",),
        note="Data: AHN4, PDOK, CC0. Surveyed 2020-2022. Water and the buildings removed from the terrain model are "
             "holes, filled from 30 m data.",
        coverage=Coverage(provider="PDOK", added="2026-11-15", survey="2020–2022")),
]
