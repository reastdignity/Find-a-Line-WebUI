"""IGN Spain: MDT05 and MDS05 (WCS), the peninsula and the Canary Islands."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.wcs import WcsTiles

# IGN's form of a credit for a derived work (Orden FOM/2807/2015): "Obra derivada de <product> CC-BY 4.0 <producer>",
# with the product identifiers and producers of the SCNE's table (https://www.scne.es/tablaProductos.php, 2026-11-01:
# "MDT05-cob1 2008-2015" and "MDS05 2008-2015", both "CC-BY 4.0 scne.es"; the services' AccessConstraints
# "CC BY 4.0 scne.es")
IGN_CREDIT = Credit("MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)",
                    "Obra derivada de MDT05-cob1 2008-2015 y MDS05 2008-2015 CC-BY 4.0 scne.es",
                    CC_BY[0], "https://www.ign.es/web/en/politica-datos")
SPAIN_MDT = "https://servicios.idee.es/wcs-inspire/mdt"
SPAIN_MDS = "https://wcs-mds.idee.es/mds"
# PNOA máxima actualidad: the newest of the yearly PNOA orthophotos in each place, product "PNOA" of the SCNE's
# table (one row per year, "PNOA <year> CC-BY 4.0 scne.es"; the year differs from place to place, so none is named)
SPAIN_ORTHO = OrthoService("Orthophoto PNOA (IGN Spain)", "https://www.ign.es/wms-inspire/pnoa-ma",
                           "OI.OrthoimageCoverage", "spain/ortho/live", "PNOA CC-BY 4.0 scne.es",
                           attribution_url=CC_BY[1])
# `spain`'s heights of exactly 0 m are no data (zero_is_nodata, on the provider's own values before the cache's LERC
# encoding; the user's decision of 2026-11-26). Both models answer 0.000 without a nodata value where they hold
# nothing: the sea, and the land beyond their data, in rectangular blocks around Ceuta (the block ends north of
# Fnideq) and Melilla, and at the borders (Portugal at Elvas, France at Banyuls: measured 2026-11-26). As heights they
# made false walls of up to 322 m at the blocks' edges and the four best spots of a 5 km search at Ceuta false; as no
# data the sea is filled as sea from the coastline and the land from France's data or the fallback. Where MDS05 holds
# only zeros over land MDT05 covers (Ceuta, Melilla) the surface stays empty (fallback_surface_with_terrain: the
# fallback fills the surface only on the terrain's gaps, the user's decision of 2026-11-27): a line wholly over it is
# "not measured" and the run warns; one that also crosses sea the terrain model has no data for is measured on those
# sea pixels only (fill_water gives a surface to the water it fills; sea MDT05 covers keeps none). Land at exactly
# 0.000 m becomes a gap too (38 pixels in Melilla). `spain_canarias` keeps its zeros (its sea is 0 m in the data; R10
# rests on it).
# Both layers' tiles have folders of their own, so a cached tile means one thing: its terrain tiles cached before (zeros
# as heights; LERC keeps a zero only within 5 mm, so they cannot be told from the land's millimetres) stay in
# spain/mdt05/live, unread by `spain`, and a checkout of before keeps reading its own there (one folder with another
# processing made each fetch the other's tiles again: cache._state); `spain_canarias`'s MDS05 is the same coverage on
# the same tiling (EPSG:25830) with its zeros kept, and a shared folder would hold tiles whose content depends on which
# source fetched them (a named --source, or `cache update`, which takes the first layer knowing a path). The
# peninsula's surface tiles cached before stay in spain/mds05/live, unread by `spain`
SPAIN_MDT_FOLDER = "spain/mdt05-zeros-nodata/live"
SPAIN_MDS_FOLDER = "spain/mds05-zeros-nodata/live"


def _spain(canary: bool) -> Source:
    """IGN Spain: MDT05 (terrain) and MDS05 (surface), 5 m from PNOA-LiDAR, via WCS.

    The peninsula and the Balearic Islands are in ETRS89 / UTM 30N (extended zone),
    the Canary Islands in REGCAN95 / UTM 28N; MDS05 covers both in UTM 30N. The ASCII
    grid format keeps centimetres (the GeoTIFF output is rounded to whole metres).
    `spain`'s heights of exactly 0 m are no data (in folders of their own: SPAIN_MDT_FOLDER,
    SPAIN_MDS_FOLDER), the Canaries' are kept.
    """
    crs, coverage = ("EPSG:4083", "Elevacion4083_5") if canary else ("EPSG:25830", "Elevacion25830_5")
    where = "Canary Islands" if canary else "Spain"
    zeros = "" if canary else "; heights of exactly 0 m are no data"
    nmt = WcsTiles(f"MDT05 (terrain) {where}", SPAIN_MDT, coverage, crs,
                   "spain/mdt05/live" if canary else SPAIN_MDT_FOLDER, native_res=5.0,
                   fetch_res=5.0, fmt="application/asc", bytes_per_px=8, zero_is_nodata=not canary)
    return Source(
        id="spain_canarias" if canary else "spain", name=f"IGN {where} (MDT05/MDS05)",
        description=f"IGN Spain PNOA-LiDAR, MDT05 terrain and MDS05 surface, 5 m ({where}){zeros}",
        nmt=nmt,
        # MDS05's grid is 5.0045 m; tiles are resampled to 5 m on download
        nmpt=WcsTiles(f"MDS05 (trees, buildings) {where}", SPAIN_MDS, "mds05", "EPSG:25830",
                      "spain/mds05/live" if canary else SPAIN_MDS_FOLDER, native_res=5.0, fetch_res=5.0,
                      fmt="application/asc", bytes_per_px=8, zero_is_nodata=not canary),
        countries=("es",), crs=crs, ortho=SPAIN_ORTHO, credits=(IGN_CREDIT,),
        bbox=(27.0, 29.6, -18.6, -13.0) if canary else None,
        neighbours=() if canary else ("france",),
        listing=ReadmeRow("Canary Islands", "IGN MDT05 (REGCAN95 / UTM 28N), 5 m", "IGN MDS05, 5 m", "PNOA (IGN)")
        if canary else ReadmeRow("Spain (peninsula, Balearic Islands)",
                                 "IGN MDT05, PNOA-LiDAR 5 m (exactly 0 m: no data)",
                                 "IGN MDS05, 5 m (exactly 0 m: no data)", "PNOA (IGN)"),
        # The box of Spain holds the Canary Islands too
        offline=() if canary else (("es", (27.0, 43.9, -18.6, 4.4)),),
        sample=(28.2640, -16.8460) if canary else (41.5930, 1.8100),
        note="IGN Spain data is available at 5 m: lines shorter than about 30 m are not reliable." + ("" if canary else
             " Heights of exactly 0 m are taken as no data: the sea (filled as sea from the coastline) and the land "
             "beyond the data's edge around Ceuta and Melilla and along the borders (filled from France's data or "
             "the 30 m models). Around Ceuta and Melilla the surface model holds no data: trees and buildings on land "
             "there are not checked."),
        coverage=Coverage(provider="IGN España", added="2026-10-23", areas=("es-cn",) if canary else (),
                          survey="pnoa", min_length=30),
        fallback_surface_with_terrain=not canary)


SOURCES: List[Source] = [
    _spain(canary=True),
    _spain(canary=False),
]
