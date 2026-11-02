"""France (mainland and Corsica): IGN's LiDAR HD terrain and surface models (MNT / MNS, 0.5 m) by GetMaps of raw
heights from the Géoplateforme's WMS-R; IGN's RGE ALTI 1 m fills their gaps (no key)."""

from typing import List

from ..credit import YEAR, Credit
from ..source import OrthoService, ReadmeRow, Source
from ..layers.wmsr import WmsrTiles

# The Géoplateforme's WMS-R (WMS 1.3.0, raw heights as float32 GeoTIFF; data.geopf.fr also serves the WMTS
# of the orthophoto). As the service answered on 2026-11-02: the LiDAR HD's MNT and MNS in EPSG:2154
# (Lambert-93, heights IGN69 on the mainland and IGN78 in Corsica, neither named in the answer), 0.5 m pixels
# with their edges on .25 / .75 (centres on whole and half metres), stored as true floats; the answer on those
# edges is the stored pixels exactly, and at 1 m on edges x .75 / y .25 the exact mean of the 2 x 2 pixels of
# 0.5 m; nodata -9999 (the sea, sites closed to the public (ZICAD), outside France, and the blocks not
# published yet: the coverage is not complete, the flat north has holes until IGN ends the programme), the
# server answers HTTP 200 with every pixel -9999 there. At most 5010 px a side; FORMAT_OPTIONS=
# compression:deflate gives a DEFLATE GeoTIFF of the same values (11 MB a km² at 0.5 m instead of 16).
# IGN publishes blocks and re-issues editions, so the folders are "live" (no index: the WFS of the tiles'
# editions is not asked).
FR_WMSR = "https://data.geopf.fr/wms-r/wms"
LAMBERT93 = "EPSG:2154"
FR_ORIGIN = (-0.25, 0.25)  # LiDAR HD's pixel edges: x on .75 (= -0.25 mod 1), y on .25
# The working grid's edges on those of the 1 m answers (and on the 0.5 m pixels)
FR_GRID_ORIGIN = (0.75, 0.25)

# Licence Ouverte / Open Licence 2.0 (Etalab), the licence of the LiDAR HD, RGE ALTI and BD ORTHO (their records
# on data.gouv.fr and the Géoplateforme's catalogue, 2026-10): "mentionner la paternité de l'« Information » :
# sa source (a minima le nom du « Concédant ») et la date de la dernière mise à jour de l'« Information »
# réutilisée". The date of the edition of each tile is not kept (the WFS is not asked), so the year of the run,
# when the data were taken from the service, stands for it (YEAR, as Lower Saxony's year of the download)
FR_LICENCE = ("Licence Ouverte 2.0", "https://www.etalab.gouv.fr/licence-ouverte-open-licence/")
FR_LIDAR_CREDIT = Credit(
    "LiDAR HD MNT / MNS (IGN, France)", f"IGN, LiDAR HD (MNT, MNS), Géoplateforme {YEAR}, Licence Ouverte 2.0",
    *FR_LICENCE,
    notice=f"Source: IGN (Institut national de l'information géographique et forestière), LiDAR HD digital terrain "
           f"and surface models, as served by the Géoplateforme (https://cartes.gouv.fr) in {YEAR}, Licence "
           "Ouverte / Open Licence 2.0 (Etalab).")
FR_RGEALTI_CREDIT = Credit(
    "RGE ALTI 1 m (IGN, France)", f"IGN, RGE ALTI 1 m, Géoplateforme {YEAR}, Licence Ouverte 2.0", *FR_LICENCE,
    notice=f"Source: IGN (Institut national de l'information géographique et forestière), RGE ALTI 1 m digital "
           f"terrain model, as served by the Géoplateforme (https://cartes.gouv.fr) in {YEAR}, Licence Ouverte / "
           "Open Licence 2.0 (Etalab).")


def _lidar_hd(kind: str, description: str) -> WmsrTiles:
    # Tiles of 1 km, IGN's own (tile (res, i, j) is LHD_FXX_<i>_<j + 1>): 1000 px at 1 m (about 2.8 MB
    # deflated), 2000 px at 0.5 m for a grid finer than 1 m
    return WmsrTiles(f"LiDAR HD {kind} {description}", FR_WMSR,
                     f"IGNF_LIDAR-HD_{kind}_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93", LAMBERT93,
                     f"france/lidarhd-{kind.lower()}/live", native_res=0.5, fetch_res=(0.5, 1.0), tile_m=1000,
                     origin=FR_ORIGIN, bytes_per_tile=2.8e6)


FR_MNT = _lidar_hd("MNT", "0.5 m (terrain)")
FR_MNS = _lidar_hd("MNS", "0.5 m (trees, buildings)")
# RGE ALTI 1 m: the national terrain model (LiDAR in the mountains, forests and along the coasts and rivers,
# elsewhere older correlation of aerial photographs, 2009-2021), its pixel edges on whole metres, centimetre
# values, nodata -99999; layer RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS (not ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES,
# a mosaic in WGS84 interpolated onto other pixels). It has no surface model. Never re-issued now: "live"
# all the same (IGN's pyramid may be rebuilt)
FR_RGEALTI = WmsrTiles("RGE ALTI 1 m (terrain)", FR_WMSR, "RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS", LAMBERT93,
                       "france/rgealti-1m/live", native_res=1.0, fetch_res=(1.0,), tile_m=1000, bytes_per_tile=2e6)

# IGN's orthophoto (BD ORTHO, 20 cm and finer) from the Géoplateforme's WMTS in Web Mercator, zoom 0-19 (20
# answers 404); the WMTS has no usage limit (CGU, annex 3, art. 3.2); Licence Ouverte 2.0
FR_ORTHO = OrthoService(
    "BD ORTHO (IGN)", None, "", "france/ortho/live", "IGN, BD ORTHO, Licence Ouverte 2.0",
    attribution_url=FR_LICENCE[1],
    base_url="https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS"
             "&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
    base_max_zoom=19)

# Metropolitan France and Corsica (the data's extent; the overseas departments are not in these layers):
# --source auto takes the source only here
FR_BOX = (41.3, 51.15, -5.2, 9.6)
FR_NOTE = ("Data: IGN, Licence Ouverte 2.0 (processed: mosaicked onto the working grid). IGN is still publishing "
           "LiDAR HD (holes in the flat north until it ends): where it has no data yet, and on sites closed to the "
           "public, gaps are filled from RGE ALTI 1 m, older in many places. The working grid is Lambert-93 (EPSG:2154): "
           "lengths are up to 0.1 % too short in the middle of France and up to 0.3 % too long at its northern "
           "and southern ends (Corsica).")


SOURCES: List[Source] = [
    Source(
        id="france", name="IGN (LiDAR HD MNT / MNS)",
        description="IGN (France, mainland and Corsica): LiDAR HD terrain and surface models 0.5 m from the "
                    "Géoplateforme's WMS-R, fetched at 1 m (the exact mean of 2 x 2 pixels), Lambert-93, IGN69 "
                    "heights (IGN78 in Corsica); gaps from RGE ALTI 1 m",
        # The tiles on their own pixels, so the working grid is Lambert-93 too; at 1 m on the 1 m answers' edges
        nmt=FR_MNT, nmpt=FR_MNS, countries=("fr",), bbox=FR_BOX, crs=LAMBERT93, default_resolution=1.0,
        grid_origin=FR_GRID_ORIGIN, ortho=FR_ORTHO, credits=(FR_LIDAR_CREDIT,),
        # RGE ALTI first; what it leaves (closed sites may be empty in it too) from FABDEM / Copernicus
        fallback="france_rgealti", more_fallbacks=("europe",),
        neighbours=("swisstopo", "luxembourg", "spain", "baden_wurttemberg"),
        listing=ReadmeRow("France (mainland, Corsica)", "IGN LiDAR HD MNT, 0.5 m (WMS-R, fetched at 1 m)",
                          "IGN LiDAR HD MNS, 0.5 m (WMS-R, fetched at 1 m)", "IGN BD ORTHO"),
        # Boxes inside France that keep clear of its neighbours' land (the first box holding a point wins, and
        # France comes before Switzerland, Spain, England, Hesse and Luxembourg in SOURCES): what lies near a
        # border outside them falls to the neighbour's box (the Jura and Haute-Savoie to Switzerland's) or to
        # none. The first box touches Spain's, Switzerland's and Luxembourg's (tests/test_neighbours.py)
        offline=(("fr", (43.40, 49.45, -1.80, 5.90)), ("fr", (47.20, 48.90, -4.80, -1.80)),
                 ("fr", (48.90, 49.75, -1.90, -1.20)), ("fr", (49.40, 50.20, 0.00, 4.10)),
                 ("fr", (50.20, 51.08, 1.45, 2.50)), ("fr", (50.20, 50.68, 2.50, 3.20)),
                 ("fr", (47.85, 49.00, 5.90, 7.50)), ("fr", (49.00, 49.40, 5.90, 6.50)),
                 ("fr", (43.00, 45.80, 5.90, 6.60)), ("fr", (43.00, 44.10, 6.60, 7.40)),
                 ("fr", (42.50, 43.40, 2.00, 5.90)), ("fr", (43.05, 43.40, -1.00, 2.00)),
                 ("fr", (42.80, 43.05, 1.00, 2.00)), ("fr", (41.30, 43.05, 8.50, 9.60))),
        sample=(43.7655, 6.3580),  # the Verdon, Escalès (R43)
        note=FR_NOTE),
    Source(
        id="france_rgealti", name="IGN (RGE ALTI 1 m)",
        description="IGN (France, mainland and Corsica): RGE ALTI 1 m terrain model from the Géoplateforme's "
                    "WMS-R, Lambert-93, IGN69 heights (IGN78 in Corsica)",
        nmt=FR_RGEALTI, countries=("fr",), bbox=FR_BOX, crs=LAMBERT93, ortho=FR_ORTHO,
        credits=(FR_RGEALTI_CREDIT,),
        listing=ReadmeRow("France (mainland, Corsica)", "IGN RGE ALTI, 1 m (WMS-R)", ortho="IGN BD ORTHO"),
        sample=(43.7655, 6.3580),
        note="Data: IGN, Licence Ouverte 2.0 (processed). RGE ALTI 1 m is LiDAR in the mountains, forests and along "
             "coasts and rivers, elsewhere older and smoother (aerial photographs): LiDAR HD (the source france) is "
             "better wherever it has data."),
]
