"""The global datasets: FABDEM and Copernicus DEM (europe), NASADEM, the water body mask."""

from typing import List, Optional

from ..credit import Credit
from ..layer import _hemi
from ..source import Listing, Source
from ..layers.degree import DegreeTiles, OpenTopographyTiles

# Checked 2026-10-27 (docs/roadmap.md, "Before going public")
COPERNICUS_NOTICE = ("produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and "
                     "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
                     "all rights reserved")
COPERNICUS_DISCLAIMER = ("The organisations in charge of the Copernicus programme by law or by delegation do "
                         "not incur any liability for any use of the Copernicus WorldDEM-30.")
COPERNICUS_LICENCE = ("Copernicus DEM licence", "https://docs.sentinel-hub.com/api/latest/static/files/data/dem/"
                                                "resources/license/License-COPDEM-30.pdf")
COPERNICUS_CREDIT = Credit("Copernicus DEM GLO-30", COPERNICUS_NOTICE[0].upper() + COPERNICUS_NOTICE[1:],
                           *COPERNICUS_LICENCE, notice=COPERNICUS_DISCLAIMER)
WATER_MASK_CREDIT = Credit("Copernicus DEM GLO-30 water body mask", COPERNICUS_CREDIT.attribution,
                           *COPERNICUS_LICENCE, notice=COPERNICUS_DISCLAIMER)
# The record at data.bris.ac.uk states CC BY-NC-SA 4.0 in its description and its
# license.txt (its licence field says "Non-Commercial Government Licence"; both are non-commercial)
FABDEM_CREDIT = Credit(
    "FABDEM V1-2", "FABDEM V1-2 © University of Bristol; FABDEM is " + COPERNICUS_NOTICE,
    "CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    notice="Neal, J., Hawker, L. (2023): FABDEM V1-2. https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn. "
           "Non-commercial use only; results computed from FABDEM are adapted material, shared under "
           "the same licence. " + COPERNICUS_DISCLAIMER)
NASADEM_CREDIT = Credit("NASADEM", "NASADEM: NASA JPL (2020), NASA LP DAAC, via OpenTopography",
                        "NASA open data (no restrictions)",
                        "https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
                        notice="Data accessed through OpenTopography (opentopography.org).")
FABDEM = "https://huggingface.co/buckets/links-ads/fabdem/resolve/tiles"
COPERNICUS = "https://copernicus-dem-30m.s3.amazonaws.com"


def _fabdem_url(lat: int, lon: int) -> str:
    g_lat, g_lon = lat // 10 * 10, lon // 10 * 10
    group = (f"{_hemi(g_lat, 'N', 'S', 2)}{_hemi(g_lon, 'E', 'W', 3)}-"
             f"{_hemi(g_lat + 10, 'N', 'S', 2)}{_hemi(g_lon + 10, 'E', 'W', 3)}")
    return f"{FABDEM}/{group}_FABDEM_V1-2/{_hemi(lat, 'N', 'S', 2)}{_hemi(lon, 'E', 'W', 3)}_FABDEM_V1-2.tif"


def _copernicus_url(lat: int, lon: int, aux: Optional[str] = None) -> str:
    """URL of a Copernicus DEM tile, or of one of its auxiliary files (e.g. aux="WBM")."""
    name = f"Copernicus_DSM_COG_10_{_hemi(lat, 'N', 'S', 2)}_00_{_hemi(lon, 'E', 'W', 3)}_00"
    if aux:
        return f"{COPERNICUS}/{name}_DEM/AUXFILES/{name}_{aux}.tif"
    return f"{COPERNICUS}/{name}_DEM/{name}_DEM.tif"


WATER_MASK = DegreeTiles("Copernicus water body mask", "copernicus30/2021/wbm",
                         lambda lat, lon: _copernicus_url(lat, lon, "WBM"), native_res=30,
                         bytes_per_tile=1e5, credit=WATER_MASK_CREDIT)


SOURCES: List[Source] = [
    Source(
        id="europe", name="FABDEM + Copernicus DEM",
        description="FABDEM V1-2 (terrain, trees and buildings removed) and Copernicus GLO-30 (surface), 30 m",
        nmt=DegreeTiles("FABDEM (terrain)", "fabdem/v1-2", _fabdem_url, native_res=30, bytes_per_tile=20e6,
                        credit=FABDEM_CREDIT),
        nmpt=DegreeTiles("Copernicus DEM GLO-30 (surface)", "copernicus30/2021/dem", _copernicus_url,
                         native_res=30, bytes_per_tile=20e6, credit=COPERNICUS_CREDIT),
        fallback=None, credits=(FABDEM_CREDIT, COPERNICUS_CREDIT),
        listing=Listing("anywhere", "[FABDEM](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn) V1-2, "
                                    "30 m (trees and buildings removed)",
                        "[Copernicus DEM GLO-30](https://registry.opendata.aws/copernicus-dem/), 30 m"),
        sample=(39.7217, 21.6306),
        note="FABDEM is licensed for non-commercial use only (CC BY-NC-SA 4.0): results made from it may "
             "be shared only under the same terms. At 30 m only long lines can be found reliably."),
    Source(
        id="nasadem", name="NASADEM (OpenTopography)",
        description="NASADEM 30 m (SRTM, includes some vegetation), from the OpenTopography API",
        nmt=OpenTopographyTiles("NASADEM", "nasadem/v1", "NASADEM"), credits=(NASADEM_CREDIT,),
        note="NASADEM is a radar surface model at 30 m: only long lines can be found reliably.",
        listing=Listing("anywhere",
                        "NASADEM 30 m via the [OpenTopography API](https://portal.opentopography.org/apidocs/)"),
        sample=(39.7217, 21.6306)),
]
