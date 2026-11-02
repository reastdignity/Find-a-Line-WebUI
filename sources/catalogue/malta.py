"""Malta's Planning Authority LiDAR of 2018 and 2012 (WCS of MSDI)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.wcs import WcsTiles

# The Planning Authority's datasets on the national open data portal (checked 2026-11-01: license_id
# CC-BY-4.0, organisation Planning Authority, for the DTM and DSM of 2018 and 2012 and the orthoimagery
# of 2018); the MSDI geonetwork named before answers 403
MT_PORTAL = "https://portal.data.gov.mt/dataset/"
MALTA_CREDITS = {
    2018: Credit("Malta LiDAR 2018 (Planning Authority, MSDI)",
                 "Planning Authority, Malta: Digital Terrain / Surface Model 2018, CC BY 4.0", CC_BY[0],
                 f"{MT_PORTAL}digital-terrain-model-2018",
                 notice=f"Surface model: {MT_PORTAL}digital-surface-model-2018. Licence: {CC_BY[1]}"),
    2012: Credit("Malta LiDAR 2012 (Planning Authority, MSDI)",
                 "Planning Authority, Malta: Digital Terrain / Surface Model 2012, CC BY 4.0", CC_BY[0],
                 f"{MT_PORTAL}digital-terrain-model-2012",
                 notice=f"Surface model: {MT_PORTAL}digital-surface-model-2012. Licence: {CC_BY[1]}; "
                        "changed: moved 56 m west and 196 m south to its true position (the services' "
                        "georeferencing is off by that much)."),
}
MALTA = "https://malta.coverage.wetransform.eu"


# The 2012 Malta services are georeferenced about 56 m east and 196 m north of the
# true position: measured against Copernicus DEM and the 2018 survey at Dingli
# (-56, -196 m), Valletta (-50, -190) and Gozo (-60, -190).
MALTA_2012_SHIFT = (-56.0, -196.0)


MALTA_LISTINGS = {
    2018: ReadmeRow("Malta", "MSDI DTM 2018, LiDAR 1 m (heights in whole metres)", "MSDI DSM 2018, 1 m", "MSDI 2018"),
    2012: ReadmeRow("Malta", "MSDI DTM 2012, centimetre heights", "MSDI DSM 2012", "MSDI 2018"),
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
                           "OI.OrthoimageCoverage", "malta/ortho/2018",
                           "Orthoimagery 2018: Planning Authority, Malta, CC BY 4.0",
                           attribution_url=CC_BY[1]),  # dataset: MT_PORTAL orthoimagery-2018
        listing=MALTA_LISTINGS[year], offline=(("mt", (35.78, 36.10, 14.15, 14.60)),) if year == 2018 else (),
        sample=(35.8565, 14.3830), note=note,
        coverage=Coverage(provider="MSDI", added="2026-10-23", survey="2018", notes=("whole_m",))
        if year == 2018 else None)


SOURCES: List[Source] = [
    _malta(2018, note="Malta 2018 heights are published in whole metres, which makes slopes and "
                      "clearances coarser; --source malta2012 has centimetre precision but gaps "
                      "along the coast (filled from 2018)."),
    _malta(2012),
]
