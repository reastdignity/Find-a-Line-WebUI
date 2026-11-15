"""France (mainland and Corsica): IGN's LiDAR HD terrain and surface models (MNT / MNS, 0.5 m) by GetMaps of raw
heights from the Géoplateforme's WMS-R; IGN's RGE ALTI 1 m fills their gaps (no key). The overseas territories of
the Antilles, French Guiana and Saint-Pierre-et-Miquelon: RGE ALTI 1 m from the same WMS-R, one layer each. La
Réunion: its LiDAR HD MNT / MNS from the same WMS-R, the gaps from its RGE ALTI 1 m."""

from typing import List

from ..credit import YEAR, Credit
from ..source import Coverage, OrthoService, ReadmeRow, Source
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


def _lidar_hd(kind: str, description: str, projection: str = "LAMB93", crs: str = LAMBERT93, zone: str = "",
              origin=FR_ORIGIN) -> WmsrTiles:
    # Tiles of 1 km, IGN's own (tile (res, i, j) is LHD_FXX_<i>_<j + 1>): 1000 px at 1 m (about 2.8 MB
    # deflated), 2000 px at 0.5 m for a grid finer than 1 m. An overseas region's layers: the suffix of its
    # projection in the layer's name, its CRS, its folder's zone and its pixel edges
    return WmsrTiles(f"LiDAR HD {kind} {description}", FR_WMSR,
                     f"IGNF_LIDAR-HD_{kind}_ELEVATION.ELEVATIONGRIDCOVERAGE.{projection}", crs,
                     f"france/lidarhd-{kind.lower()}{'-' + zone if zone else ''}/live", native_res=0.5,
                     fetch_res=(0.5, 1.0), tile_m=1000, origin=origin, bytes_per_tile=2.8e6)


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


# RGE ALTI 1 m of the overseas territories: one WMS-R layer per territory in its own CRS, float32, centimetres in
# most places (French Guiana's values are not on centimetres), nodata -99999, every pixel -99999 at sea and outside
# the territory (Sint Maarten). As the service answered on 2026-11-15: the Antilles' and Saint-Pierre-et-Miquelon's
# pixel CENTRES lie on whole metres (edges on .5: a GetMap at 0.5 m repeats each value in 2 x 2 blocks starting on
# the half metres, 100 % at Soufrière, the Pitons du Carbet and Saint-Pierre), unlike the mainland's RGE ALTI and
# French Guiana's (edges on whole metres, blocks on the whole metres 100 % at the Mahury); a GetMap on the stored
# edges answers the stored pixels, one off them the nearest pixel (no interpolation). The layers name IGN's own CRS
# codes; asked by the equivalent EPSG code the answer is the same pixels (equal bytes of values at every point
# tried). Vertical datums (IGN's product records): Guadeloupe GUAD88 (La Désirade GUAD92LD, Marie-Galante GUAD88MG,
# Les Saintes GUAD88LS, Saint-Barthélemy GUAD88SB, Saint-Martin GUAD88SM), Martinique MART87, French Guiana NGG77
# (GUYA77), Saint-Pierre-et-Miquelon Danger 1950 (STPM50). Editions: Guadeloupe 2013-2014, Saint-Barthélemy and
# Saint-Martin 2019, Martinique 2015, French Guiana 2023, Saint-Pierre-et-Miquelon 2017, Mayotte 2015 (SHOM 1953).
# Réunion's (RGEALTI-MNT_PYR-ZIP_REU_RGR92UTM40S_WMS) fills the gaps of its LiDAR HD (france_reunion).
HALF_METRE = (0.5, 0.5)
# These layers hold the sea floor along their coasts (measured 2026-11-15 on 500 m to 2.4 km boxes: Guadeloupe at
# Deshaies down to -11 m, Martinique at Saint-Pierre -33 m, Réunion -16 m at Saint-Gilles, Mayotte -38 m; Mayotte's
# source mask codes those pixels 20 and 10): next to the sea's 0 m fill (where a layer has no data) it made walls of
# 20-30 m, and a search found false lines between them (all 9 445 lines of a 400 m search at Saint-Pierre, all 315
# on Mayotte's north-west shore). Heights below OVERSEAS_FLOOR are no data (the user's decision of 2026-11-15), so
# the sea fill puts 0 m there; the water at about 0 m and the land are kept. Applied where the tiles are read onto
# the grid (Layer.nodata_below), so the tiles cached before with the sea floor in them give what a fresh one gives
OVERSEAS_FLOOR = -1.0


def _rgealti_overseas(zone: str, where: str, layer: str, crs: str, origin=(0.0, 0.0)) -> WmsrTiles:
    return WmsrTiles(f"RGE ALTI 1 m (terrain) {where}", FR_WMSR, layer, crs, f"france/rgealti-1m-{zone}/live",
                     native_res=1.0, fetch_res=(1.0,), tile_m=1000, origin=origin, bytes_per_tile=2e6,
                     nodata_below=OVERSEAS_FLOOR)


# La Réunion: LiDAR HD MNT and MNS in RGR92 / UTM 40S (EPSG:2975; the answers name EPSG:32740, forced to the
# reader's CRS), 0.5 m true floats, nodata -9999 (the open sea). Along the coast the sea has heights (the water at
# about 0 to -2 m: water inside the sea zone, their heights kept), and where the data end offshore their edge holds
# wrong values (Cap Méchant, 2026-11-15, about 1 km out: -40 to 975 m at 0.5 m, -235 to 644 m in the 1 m answers,
# 353 pixels above 100 m in one 1 km tile), not taken out. As the service answered on 2026-11-15: unlike the
# mainland's, the pixel EDGES lie on multiples of 0.5 m (a GetMap at 0.25 m repeats each value in 2 x 2 blocks
# starting on the whole and half metres), and the 1 m answer on whole metres is the mean of the 2 x 2 pixels of
# 0.5 m (within 1e-4 m: tests/test_france_overseas.py). Gaps from the island's RGE ALTI 1 m (vertical datum IGN 1989,
# IGN's record; centres on whole metres like the Antilles'), then FABDEM / Copernicus
REU_CRS = "EPSG:2975"
REU_MNT = _lidar_hd("MNT", "0.5 m (terrain) La Réunion", "RGR92UTM40S", REU_CRS, "reu", (0.0, 0.0))
REU_MNS = _lidar_hd("MNS", "0.5 m (trees, buildings) La Réunion", "RGR92UTM40S", REU_CRS, "reu", (0.0, 0.0))
REU_RGEALTI = _rgealti_overseas("reu", "La Réunion", "RGEALTI-MNT_PYR-ZIP_REU_RGR92UTM40S_WMS", REU_CRS, HALF_METRE)
REU_BOX = (-21.42, -20.84, 55.20, 55.86)

OVERSEAS_NOTE = ("Data: IGN, Licence Ouverte 2.0 (processed: heights below -1 m, the sea floor along the coasts, taken "
                 "as no data, so the sea is filled at 0 m). RGE ALTI 1 m has no surface model: trees and buildings "
                 "are not in the data, check the photo.")


def _overseas(id_: str, name: str, where: str, layer: WmsrTiles, crs: str, grid_origin, bbox, offline,
              sample, areas, listing: str) -> Source:
    return Source(
        id=id_, name=f"IGN (RGE ALTI 1 m, {name})",
        description=f"IGN ({where}): RGE ALTI 1 m terrain model from the Géoplateforme's WMS-R, {crs}",
        nmt=layer, countries=("fr",), bbox=bbox, crs=crs, grid_origin=grid_origin, ortho=FR_ORTHO,
        credits=(FR_RGEALTI_CREDIT,), fallback="europe", offline=tuple(("fr", box) for box in offline),
        listing=ReadmeRow(listing, "IGN RGE ALTI, 1 m (WMS-R)", ortho="IGN BD ORTHO"), sample=sample,
        note=OVERSEAS_NOTE, coverage=Coverage(provider="IGN", added="2026-11-15", areas=areas))


# Nominatim names every one of them "fr" (zoom 3, 2026-11-15: its ISO 3166-2 codes are fr-971, fr-972, fr-gf /
# fr-973, fr-pm, fr-bl, fr-mf), so each is chosen by its bbox, outside the mainland's FR_BOX; Sint Maarten is "nl".
# Their boxes hold no other source's (Canada's offline box holds Saint-Pierre-et-Miquelon: France comes first in
# FAMILIES, and its box stops west of Newfoundland's Green Island)
OVERSEAS: List[Source] = [
    _overseas("france_guadeloupe", "Guadeloupe", "Guadeloupe, Saint-Barthélemy, Saint-Martin",
              _rgealti_overseas("glp", "Guadeloupe", "RGEALTI-MNT_PYR-ZIP_GLP_WGS84UTM20_WMS", "EPSG:32620",
                                HALF_METRE), "EPSG:32620", HALF_METRE, (15.80, 18.13, -63.16, -60.95),
              ((15.80, 16.55, -61.85, -60.95), (17.85, 17.98, -62.95, -62.77), (18.04, 18.13, -63.16, -62.95)),
              (16.0868, -61.6592),  # the gorge above the Grand Saut d'Eau (R66)
              ("fr-gp", "bl", "mf"), "Guadeloupe, Saint-Barthélemy, Saint-Martin (France)"),
    _overseas("france_martinique", "Martinique", "Martinique",
              _rgealti_overseas("mtq", "Martinique", "RGEALTI-MNT_PYR-ZIP_MTQ_WGS84UTM20_WMS", "EPSG:32620",
                                HALF_METRE), "EPSG:32620", HALF_METRE, (14.38, 14.89, -61.24, -60.80),
              ((14.38, 14.89, -61.24, -60.80),), (14.7050, -61.1000),  # the Pitons du Carbet
              ("fr-mq",), "Martinique (France)"),
    _overseas("france_guiana", "French Guiana", "French Guiana",
              _rgealti_overseas("guf", "French Guiana", "RGEALTI-MNT_PYR-ZIP_GUF_UTM22RGFG95_WMS", "EPSG:2972"),
              "EPSG:2972", (0.0, 0.0), (2.10, 5.80, -54.60, -51.60), ((2.10, 5.80, -54.60, -51.60),),
              (4.8800, -52.2700),  # the Montagne du Mahury
              ("fr-gf",), "French Guiana (France)"),
    _overseas("france_spm", "Saint-Pierre-et-Miquelon", "Saint-Pierre-et-Miquelon",
              _rgealti_overseas("spm", "Saint-Pierre-et-Miquelon", "RGEALTI-MNT_PYR-ZIP_SPM_RGSPM06U21_WMS",
                                "EPSG:4467", HALF_METRE), "EPSG:4467", HALF_METRE, (46.74, 47.15, -56.53, -56.11),
              ((46.74, 47.15, -56.53, -56.11),), (46.7800, -56.1800),  # Saint-Pierre
              ("pm",), "Saint-Pierre-et-Miquelon (France)"),
    # Mayotte (Nominatim's zoom 3: "fr"): RGE ALTI 1 m in RGM04 / UTM 38S (EPSG:4471; the answers name EPSG:5629,
    # "Moznet / UTM 38S", a wrong tag: forced), centimetres, the lagoon -99999; heights SHOM 1953, layer of 2015
    _overseas("france_mayotte", "Mayotte", "Mayotte",
              _rgealti_overseas("myt", "Mayotte", "RGEALTI-MNT_PYR-ZIP_MYT_RGM04UTM38S_WMS", "EPSG:4471",
                                HALF_METRE), "EPSG:4471", HALF_METRE, (-13.02, -12.62, 44.96, 45.32),
              ((-13.02, -12.62, 44.96, 45.32),), (-12.7000, 45.1000),
              ("fr-yt",), "Mayotte (France)"),
]


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
        neighbours=("swisstopo", "luxembourg", "spain", "baden_wurttemberg", "rhineland_palatinate", "saarland"),
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
                 ("fr", (42.80, 43.05, 1.00, 2.00)), ("fr", (41.32, 43.05, 8.50, 9.60))),
        sample=(43.7655, 6.3580),  # the Verdon, Escalès (R43)
        note=FR_NOTE,
        coverage=Coverage(provider="IGN", added="2026-11-02", survey="lidar_hd")),
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
    # The overseas territories after the mainland: no box of theirs touches its boxes
    *OVERSEAS,
    # La Réunion (Nominatim's zoom 3 names it "fr", 2026-11-15: chosen by its bbox, which holds no other source's
    # box): the LiDAR HD, its gaps from the island's RGE ALTI (the source after it, which its box takes only when
    # asked for by name), then FABDEM / Copernicus
    Source(
        id="france_reunion", name="IGN (LiDAR HD MNT / MNS, La Réunion)",
        description="IGN (La Réunion): LiDAR HD terrain and surface models 0.5 m from the Géoplateforme's WMS-R, "
                    "fetched at 1 m (the mean of 2 x 2 pixels), RGR92 / UTM 40S (EPSG:2975); gaps from RGE ALTI 1 m",
        # The working grid's edges on whole metres: those of the 1 m answers and of the 0.5 m pixels
        nmt=REU_MNT, nmpt=REU_MNS, countries=("fr",), bbox=REU_BOX, crs=REU_CRS, default_resolution=1.0,
        grid_origin=(0.0, 0.0), ortho=FR_ORTHO, credits=(FR_LIDAR_CREDIT,),
        fallback="france_reunion_rgealti", more_fallbacks=("europe",),
        offline=(("fr", REU_BOX),),
        listing=ReadmeRow("La Réunion (France)", "IGN LiDAR HD MNT, 0.5 m (WMS-R, fetched at 1 m)",
                          "IGN LiDAR HD MNS, 0.5 m (WMS-R, fetched at 1 m)", "IGN BD ORTHO"),
        sample=(-21.1300, 55.4550),  # the Cilaos rampart
        note="Data: IGN, Licence Ouverte 2.0 (processed: mosaicked onto the working grid). Where LiDAR HD has no "
             "data, gaps are filled from RGE ALTI 1 m. Along the coast LiDAR HD gives the sea heights of about 0 to "
             "-2 m; where its data end offshore, their edge can hold wrong heights (hundreds of metres); beyond, the "
             "sea is filled as water.",
        coverage=Coverage(provider="IGN", added="2026-11-15", areas=("fr-re",))),
    Source(
        id="france_reunion_rgealti", name="IGN (RGE ALTI 1 m, La Réunion)",
        description="IGN (La Réunion): RGE ALTI 1 m terrain model from the Géoplateforme's WMS-R, RGR92 / UTM 40S "
                    "(EPSG:2975), IGN 1989 heights",
        nmt=REU_RGEALTI, countries=("fr",), bbox=REU_BOX, crs=REU_CRS, grid_origin=HALF_METRE, ortho=FR_ORTHO,
        credits=(FR_RGEALTI_CREDIT,),
        listing=ReadmeRow("La Réunion (France)", "IGN RGE ALTI, 1 m (WMS-R)", ortho="IGN BD ORTHO"),
        sample=(-21.1300, 55.4550),
        note="Data: IGN, Licence Ouverte 2.0 (processed). RGE ALTI 1 m has no surface model: LiDAR HD (the source "
             "france_reunion) is better wherever it has data."),
]
