"""Malta's Planning Authority LiDAR of 2018 and 2012 (WCS of MSDI)."""

from typing import List

from ..credit import Credit
from ..source import Listing, OrthoService, Source
from ..layers.wcs import WcsTiles

MSDI = "https://msdi.data.gov.mt/geonetwork/"
MALTA_CREDITS = {
    2018: Credit("Malta LiDAR 2018 (Planning Authority, MSDI)", "Planning Authority Malta (MSDI), LiDAR 2018",
                 "no conditions on access and use (INSPIRE metadata)", MSDI),
    # The MSDI records were reported as CC BY-NC-ND 4.0, the INSPIRE ones as without conditions
    2012: Credit("Malta LiDAR 2012 (Planning Authority, MSDI)", "Planning Authority Malta (MSDI), LiDAR 2012",
                 "unresolved (CC BY-NC-ND 4.0 or no conditions)", MSDI),
}
MALTA = "https://malta.coverage.wetransform.eu"


# The 2012 Malta services are georeferenced about 56 m east and 196 m north of the
# true position: measured against Copernicus DEM and the 2018 survey at Dingli
# (-56, -196 m), Valletta (-50, -190) and Gozo (-60, -190).
MALTA_2012_SHIFT = (-56.0, -196.0)


MALTA_LISTINGS = {
    2018: Listing("Malta", "MSDI DTM 2018, LiDAR 1 m (heights in whole metres)", "MSDI DSM 2018, 1 m", "MSDI 2018"),
    2012: Listing("Malta", "MSDI DTM 2012, centimetre heights, gaps filled from 2018", "MSDI DSM 2012", "MSDI 2018"),
}


def _malta(year: int, note: str = "") -> Source:
    crs = "EPSG:25833" if year == 2012 else "EPSG:32633"
    layer = lambda kind, desc: WcsTiles(
        f"{desc} Malta {year}", f"{MALTA}/{kind}_1m_{year}/ows", f"{kind}_1m_{year}", crs,
        f"malta/{kind}/{year}", native_res=1.0 if year == 2012 else 0.15, fetch_res=1.0, axes=("E", "N"),
        shift=MALTA_2012_SHIFT if year == 2012 else (0.0, 0.0), bytes_per_px=0.8)  # measured: ~3 MB per tile
    return Source(
        id="malta" if year == 2018 else f"malta{year}", name=f"Malta {year} (MSDI)",
        description=f"Malta Planning Authority LiDAR {year}, DTM and DSM 1 m",
        nmt=layer("dtm", "DTM (terrain)"), nmpt=layer("dsm", "DSM (trees, buildings)"),
        countries=("mt",) if year == 2018 else (), crs=crs,
        fallback="malta" if year == 2012 else "europe", credits=(MALTA_CREDITS[year],),
        ortho=OrthoService("Orthophoto Malta 2018 (MSDI)", f"{MALTA}/wms/ortho_2018/ows",
                           "OI.OrthoimageCoverage", "malta/ortho/2018", "Planning Authority Malta"),
        listing=MALTA_LISTINGS[year], offline=(("mt", (35.78, 36.10, 14.15, 14.60)),) if year == 2018 else (),
        sample=(35.8565, 14.3830), note=note)


SOURCES: List[Source] = [
    _malta(2018, note="Malta 2018 heights are published in whole metres, which makes slopes and "
                      "clearances coarser; --source malta2012 has centimetre precision but gaps "
                      "along the coast (filled from 2018)."),
    _malta(2012),
]
