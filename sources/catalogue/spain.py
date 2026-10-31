"""IGN Spain: MDT05 and MDS05 (WCS), the peninsula and the Canary Islands."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Listing, OrthoService, Source
from ..layers.wcs import WcsTiles

# IGN's form of a credit for a derived work (Orden FOM/2807/2015): "Obra derivada de <product> CC-BY 4.0 ign.es"
IGN_CREDIT = Credit("MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)", "Obra derivada de MDT05 / MDS05 CC-BY 4.0 ign.es",
                    CC_BY[0], "https://www.ign.es/web/en/politica-datos")
SPAIN_MDT = "https://servicios.idee.es/wcs-inspire/mdt"
SPAIN_MDS = "https://wcs-mds.idee.es/mds"
SPAIN_ORTHO = OrthoService("Orthophoto PNOA (IGN Spain)", "https://www.ign.es/wms-inspire/pnoa-ma",
                           "OI.OrthoimageCoverage", "spain/ortho/live", "PNOA © IGN")


def _spain(canary: bool) -> Source:
    """IGN Spain: MDT05 (terrain) and MDS05 (surface), 5 m from PNOA-LiDAR, via WCS.

    The peninsula and the Balearic Islands are in ETRS89 / UTM 30N (extended zone),
    the Canary Islands in REGCAN95 / UTM 28N; MDS05 covers both in UTM 30N. The ASCII
    grid format keeps centimetres (the GeoTIFF output is rounded to whole metres).
    """
    crs, coverage = ("EPSG:4083", "Elevacion4083_5") if canary else ("EPSG:25830", "Elevacion25830_5")
    where = "Canary Islands" if canary else "Spain"
    return Source(
        id="spain_canarias" if canary else "spain", name=f"IGN {where} (MDT05/MDS05)",
        description=f"IGN Spain PNOA-LiDAR, MDT05 terrain and MDS05 surface, 5 m ({where})",
        nmt=WcsTiles(f"MDT05 (terrain) {where}", SPAIN_MDT, coverage, crs,
                     "spain/mdt05/live", native_res=5.0, fetch_res=5.0,
                     fmt="application/asc", bytes_per_px=8),
        # MDS05's grid is 5.0045 m; tiles are resampled to 5 m on download
        nmpt=WcsTiles(f"MDS05 (trees, buildings) {where}", SPAIN_MDS, "mds05", "EPSG:25830",
                      "spain/mds05/live", native_res=5.0, fetch_res=5.0, fmt="application/asc", bytes_per_px=8),
        countries=("es",), crs=crs, ortho=SPAIN_ORTHO, credits=(IGN_CREDIT,),
        bbox=(27.0, 29.6, -18.6, -13.0) if canary else None,
        listing=Listing("Canary Islands", "IGN MDT05 (REGCAN95 / UTM 28N), 5 m", "IGN MDS05, 5 m", "PNOA (IGN)")
        if canary else Listing("Spain (peninsula, Balearic Islands)", "IGN MDT05, PNOA-LiDAR 5 m", "IGN MDS05, 5 m",
                               "PNOA (IGN)"),
        # The box of Spain holds the Canary Islands too
        offline=() if canary else (("es", (27.0, 43.9, -18.6, 4.4)),),
        sample=(28.2640, -16.8460) if canary else (41.5930, 1.8100),
        note="IGN Spain data is available at 5 m: lines shorter than about 30 m are not reliable.")


SOURCES: List[Source] = [
    _spain(canary=True),
    _spain(canary=False),
]
