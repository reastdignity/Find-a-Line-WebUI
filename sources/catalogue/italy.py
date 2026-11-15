"""Italy: the Autonomous Province of Bolzano / South Tyrol (its DTM and DSM 2.5 m, WCS), the Autonomous Province
of Trento (its LiDAR 2014 DTM and DSM 0.5 m, ASCII grids of 500 m), Sardinia (its coastal lidar DTM and DSM 1 m of
2008, ZIPs of ASCII grids listed by a WFS of their footprints) and INGV's TINITALY 1.1 (10 m, WCS) for the rest of
Italy, San Marino and the Vatican and for the gaps of the regional sources."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.sheets import WfsFeatureTiles
from ..layers.wcs import WcsTiles
from ..layers.zipped import ZippedTiles

# The province's GeoServer (WCS 2.0.1, axes E/N, no SCALESIZE): float32 GeoTIFFs in ETRS89 /
# UTM 32N, nodata -9999, heights orthometric (the province's own geoid). The 2.5 m models cover
# the whole province (the mountains from the LiDAR of 2004-2006); the 0.5 m ones only the
# settlements, newer ones parts (Etsch/Adige 0.2 m 2024, glaciers 0.5 m 2023): not used yet.
BZ_WCS = "https://geoservices9.civis.bz.it/geoserver/ows"
BZ_PROVINCE = "Autonome Provinz Bozen - Südtirol / Provincia autonoma di Bolzano - Alto Adige"
# CC0 1.0: no attribution required; the province is credited all the same
BZ_CREDIT = Credit("DTM / DSM 2.5 m (Autonomous Province of Bolzano - South Tyrol)", BZ_PROVINCE,
                   "CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
# The pixel centres of the 2.5 m grid are on multiples of 2.5 m (the coverage's edges at
# 604998.75 / 5119998.75): tiles and the working grid have their edges 1.25 m from them
BZ_ORIGIN = (1.25, 1.25)
# At the province's border (Sassolungo, Sella) pixels up to 3 from no data are blended with zero
# (1972.8 = 0.9 x 2192, or 229.7: false steps of up to 1270 m; 5% of the pixels 1-3 from the edge
# with steps over 50 m, none 4 or more from it): they are dropped and filled from the fallback
BZ_EDGE_PX = 3


def _bz_layer(kind: str, description: str) -> WcsTiles:
    # Tiles of 5 km on the coverage's own pixels, DEFLATE-compressed by the server: 9.6-11.3 MB
    # a tile full of data (16.8 MB uncompressed); a request reaching beyond the coverage gets the
    # part inside (404 only for one wholly outside it)
    return WcsTiles(f"{description} South Tyrol", BZ_WCS, f"p_bz-Elevation__{kind}-2.5m", "EPSG:25832",
                    f"italy/bz-{'dtm' if kind == 'DigitalTerrainModel' else 'dsm'}/2.5m", native_res=2.5,
                    fetch_res=2.5, axes=("E", "N"), origin=BZ_ORIGIN, bytes_per_px=2.5, edge_px=BZ_EDGE_PX,
                    params=(("GEOTIFF:COMPRESSION", "DEFLATE"),))


# The province's orthophoto of 2023 (20 cm) from its MapProxy WMTS in Web Mercator (zoom 0-24 offered: the
# imagery's own detail ends at about 19); no request limits published. Its record on data.civis.bz.it
# (ortofoto-2023, checked 2026-11-01) says "L'utilizzo dei dati è vincolato dal rispetto delle condizioni di cui
# al modello di licenza Creative Commons BY 4.0", its access constraints the CC BY 4.0 deed (its licence field
# says CC0: the stricter CC BY is followed)
BZ_ORTHO = OrthoService(
    "Orthophoto 2023 (Autonomous Province of Bolzano)", None, "", "italy/bz-ortho/2023",
    "Orthofoto 2023: Autonome Provinz Bozen - Südtirol (CC BY 4.0)", attribution_url=CC_BY[1],
    base_url="https://geoservices.buergernetz.bz.it/mapproxy/ows?service=WMTS&version=1.0.0&request=GetTile"
             "&layer=p_bz-Orthoimagery:Aerial-2023-RGB&style=default&tilematrixset=EPSG_3857"
             "&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/png", base_max_zoom=19)


# Trento: the province's LiDAR of 2014 (with flights of 2018 integrated), DTM and DSM of first returns at 0.5 m
# (Servizio Geologico), plain ESRI ASCII grids of 500 m tiles on its download server (nginx, static files about
# 13 MB/s; a directory listing of 3 MB takes 30 s): <folder>/5h<E / 100 m, 4 digits><N / 100 m, 5 digits>_<kind>.asc
# with E, N the tile's south-west corner in ETRS89 / UTM 32N (checked against all 25 201 listed names, E
# 612000-728500, N 5059500-5157000). 1000 x 1000 px, xllcenter <corner>.25 (pixel edges on whole metres),
# nodata -9999, no CRS in the files (EPSG:25832 imposed), centimetre heights, orthometric (90-97 m at Arco, the lake
# at 65 m); header case and padding vary. About 7 MB a tile, 28 MB a km² and model. A tile without data answers
# 404. No newer survey (the province's LiDAR page, updated 2025-06-10), files dated 2015-2020: the folder carries
# the survey's year. The province's GeoServer publishes no WCS coverage; no request limits published.
TN_DATA = "https://siatservices.provincia.tn.it/stemdata"
# CC BY 4.0 (the CSW record of the province's index, p_TN:9f2cc32d-...), no wording prescribed: the province and
# its service named, with the survey
TN_CREDIT = Credit("LiDAR PAT 2014 DTM / DSM 0.5 m (Autonomous Province of Trento)",
                   "Provincia autonoma di Trento - Servizio Geologico, LiDAR PAT 2014", *CC_BY)


def _tn_layer(folder: str, suffix: str, kind: str, description: str) -> ZippedTiles:
    """500 m tiles of the DTM or the DSM, each one plain ASCII grid (read by SheetFile without members)."""
    def url(left: float, bottom: float) -> str:
        return f"{TN_DATA}/{folder}/5h{round(left) // 100:04d}{round(bottom) // 100:05d}_{suffix}.asc"
    return ZippedTiles(f"{description} Trento", f"italy/tn-{kind}/2014", "EPSG:25832", 500, 0.5, url, None,
                       bytes_per_tile=7e6)


# Sardinia: the region's coastal lidar of 2008 (the "fascia costiera", a strip of about 1-3 km along most of the
# coast), DTM and DSM 1 m, one ZIP (Deflate) per tile of a 1:10 000 section's 25 (about 1.4 x 1.1 km), named
# <section>_<01-25> (some <section>a..._nn), of one ASCII grid <name>_WGS.ASC: WGS 84 / UTM 32N without a CRS in the
# file (EPSG:32632 imposed), cell 1 m, XLLCENTER / YLLCENTER on whole metres (pixel edges on .5: grid_origin
# 0.5), nodata -9999, millimetre values, orthometric heights (the sea at -0.3..0 m); about 3-4.4 MB a tile; a tile
# missing on the server answers 404. Listed by the region's GeoServer as the WFS feature type
# dbu:QU2k_fasciacostiera2008_DTM_DSM1m (2963 features: nomemappa and the ZIPs' URLs dtm, dsm, dsm_buildi,
# dsm_vegeta; footprints stored in EPSG:3003, given in EPSG:32632 on request, where they are the files' own
# rectangles on .5 m, checked 2026-11-15 at Cala Gonone against tile 500120_03's header). The DSM used is `dsm`
# (the whole surface: buildings and vegetation). A frozen survey: versioned folders. No request limits published
# (the WFS's Fees and AccessConstraints none; the geoportal's legal notes, read 2026-11-15)
SAR_WFS = "https://webgis.regione.sardegna.it/geoserver/ows"
SAR_TYPE = "dbu:QU2k_fasciacostiera2008_DTM_DSM1m"
# CC BY 4.0: the record R_SARDEG:BFPNM (otherConstraints https://creativecommons.org/licenses/by/4.0, "no
# limitations to public access", fees "Gratuito"; read 2026-11-15) and the geoportal's legal notes ("I dati di
# proprietà della Regione Autonoma della Sardegna sono pubblicati con licenza Creative Commons CC BY 4.0"; their
# sentence "solo per uso personale e non commerciale" is of the site's own texts and images); no wording prescribed:
# the region and the dataset named, the record's licence link kept
SAR_CREDIT = Credit("DTM / DSM 1 m fascia costiera 2008 (Regione Autonoma della Sardegna)",
                    "Regione Autonoma della Sardegna, DTM e DSM passo 1 m fascia costiera 2008, CC BY 4.0", *CC_BY)
SAR_ORIGIN = (0.5, 0.5)


def _sar_layer(link: str, kind: str, description: str) -> WfsFeatureTiles:
    """The tiles of one model (its URL the feature's attribute link), the index asked per model."""
    return WfsFeatureTiles(f"{description} Sardinia", SAR_WFS, SAR_TYPE, link, "nomemappa", f"sar-{kind}",
                           f"italy/sar-{kind}/2008", "EPSG:32632", 1.0, 2008, bytes_per_tile=4e6)


# TINITALY 1.1 (INGV, 2023): a 10 m terrain model of all of Italy (with San Marino and the Vatican) made from a TIN of
# contour lines, spot heights, GPS and other surveys, served by INGV's GeoServer as WCS 2.0.1, coverage
# TINItaly_1_1__tinitaly_dem: float32 in WGS 84 / UTM 32N (axes E, N; extent 312 500-1 320 000 E, 3 930 000-5 222 500
# N), pixel edges on whole 10 m, nodata -9999 over the sea and outside Italy where a granule lies, and all 0 without
# a nodata tag where none lies (the open sea: zero_is_nodata; no land pixel of the tiles read was exactly 0, the
# shore's lowest 0.016 m), heights in metres (vertical datum not stated: orthometric, see tools/check_source.py's
# comparison with Copernicus); `GEOTIFF:COMPRESSION=DEFLATE` honoured (float32 without a predictor: about 3.4 bytes
# a pixel), 2000 px a side answered, a request beyond the extent clipped, one wholly outside it 404. Checked
# 2026-11-15. No request limits published (the WCS's Fees and AccessConstraints NONE; tinitaly.pi.ingv.it and its
# Download_Area1_1.html, read 2026-11-15)
TINITALY_WCS = "https://tinitaly.pi.ingv.it/TINItaly_1_1/wcs"
# The citation INGV asks for (Download_Area1_1.html: "TINITALY is published with a CC BY 4.0 license and can be used
# freely, even partly, but it must be cited as follows"), verbatim
TINITALY_CITATION = ("Tarquini S., I. Isola, M. Favalli, A. Battistini, G. Dotta (2023). TINITALY, a digital "
                     "elevation model of Italy with a 10 meters cell size (Version 1.1). Istituto Nazionale di "
                     "Geofisica e Vulcanologia (INGV). https://doi.org/10.13127/tinitaly/1.1")
TINITALY_CREDIT = Credit("TINITALY 1.1 10 m (INGV)", TINITALY_CITATION, *CC_BY,
                         notice="Terms: https://tinitaly.pi.ingv.it/Download_Area1_1.html")
# Tiles of 10 km (1000 px at 10 m, about 3.4 MB deflated): the server answers 2000 px, but a search of a few km
# would fetch up to four tiles of 14 MB
TINITALY_DEM = WcsTiles("TINITALY 1.1 10 m (terrain)", TINITALY_WCS, "TINItaly_1_1__tinitaly_dem", "EPSG:32632",
                        "italy/tinitaly/1.1", native_res=10.0, tile_px=1000, fetch_res=10.0, axes=("E", "N"),
                        zero_is_nodata=True, bytes_per_px=3.4, params=(("GEOTIFF:COMPRESSION", "DEFLATE"),))
# Rough boxes of Italy (the first box holding a point wins, and Italy comes after France, Switzerland, Austria,
# Slovenia and Malta in SOURCES, Sardinia, South Tyrol and Trento before TINITALY): steps along the French border
# that keep off Savoie, the Hautes-Alpes, the Alpes-Maritimes and Menton (east of 6.6 E France's own boxes stop at
# 44.1 N and 7.4 E), the Adriatic off Istria and Dalmatia, Sicily east of Tunisia's Cap Bon (11.04 E), Sardinia,
# the Gargano and the Tremiti islands, Lampedusa and Linosa
IT_BOXES = (("it", (45.45, 46.40, 7.06, 13.37)), ("it", (45.20, 45.45, 7.20, 13.37)),
            ("it", (45.00, 45.20, 7.10, 13.37)), ("it", (44.70, 45.00, 7.05, 13.37)),
            ("it", (44.30, 44.70, 7.10, 13.37)), ("it", (44.15, 44.30, 7.30, 13.37)),
            ("it", (43.95, 44.15, 7.75, 13.37)), ("it", (43.60, 43.95, 7.56, 15.00)),
            ("it", (41.90, 43.60, 8.00, 15.40)), ("it", (41.90, 42.25, 15.40, 16.25)),
            ("it", (39.70, 41.90, 8.00, 18.60)), ("it", (36.60, 39.70, 11.90, 17.30)),
            ("it", (38.85, 41.32, 8.10, 9.85)), ("it", (35.45, 35.90, 12.30, 12.90)),
            # Italy's land beyond the boxes above, which only TINITALY's coverage needs (coverage_boxes: an area
            # download of Italy): north of 46.37 N and east of 13.37 E Switzerland's, Austria's and Slovenia's
            # boxes come first and keep their land offline
            ("it", (46.37, 47.10, 8.30, 13.712)), ("it", (45.45, 46.40, 13.37, 13.95)),
            # Along the French border, bands of 0.05 deg from Italy's westernmost land in each (Nominatim's
            # outlines of Italia and France, 2026-11-15; consecutive bands of one edge merged; east of the Roya
            # valley and at Ventimiglia apart): France has no box there, so they hold about 800 km2 of its
            # border strip too (offline only: an offline guess of Italy there gets TINITALY, no data, filled from
            # europe, as before)
            ("it", (44.15, 44.20, 7.17, 7.80)), ("it", (44.20, 44.25, 6.99, 7.80)), ("it", (44.25, 44.30, 6.95, 7.80)),
            ("it", (44.30, 44.35, 6.92, 7.80)), ("it", (44.35, 44.40, 6.88, 7.80)), ("it", (44.40, 44.45, 6.89, 7.80)),
            ("it", (44.45, 44.50, 6.86, 7.80)), ("it", (44.50, 44.55, 6.85, 7.80)), ("it", (44.55, 44.60, 6.87, 7.80)),
            ("it", (44.60, 44.65, 6.93, 7.80)), ("it", (44.65, 44.70, 6.94, 7.80)), ("it", (44.70, 44.75, 7.02, 7.80)),
            ("it", (44.75, 44.80, 6.99, 7.80)), ("it", (44.80, 44.85, 6.86, 7.80)), ("it", (44.85, 44.90, 6.77, 7.80)),
            ("it", (44.90, 44.95, 6.74, 7.80)), ("it", (44.95, 45.00, 6.73, 7.80)), ("it", (45.00, 45.05, 6.66, 7.80)),
            ("it", (45.05, 45.10, 6.63, 7.80)), ("it", (45.10, 45.15, 6.62, 7.80)), ("it", (45.15, 45.20, 6.75, 7.80)),
            ("it", (45.20, 45.25, 6.96, 7.80)), ("it", (45.25, 45.30, 7.12, 7.80)), ("it", (45.30, 45.35, 7.10, 7.80)),
            ("it", (45.35, 45.40, 7.13, 7.80)), ("it", (45.40, 45.45, 7.10, 7.80)), ("it", (45.45, 45.50, 7.00, 7.80)),
            ("it", (45.50, 45.55, 6.99, 7.80)), ("it", (45.55, 45.60, 6.97, 7.80)), ("it", (45.60, 45.65, 6.92, 7.80)),
            ("it", (45.65, 45.70, 6.84, 7.80)), ("it", (45.70, 45.85, 6.80, 7.80)), ("it", (45.85, 45.90, 6.94, 7.80)),
            ("it", (45.90, 45.95, 7.00, 7.80)), ("it", (44.10, 44.15, 7.26, 7.45)), ("it", (43.85, 44.00, 7.59, 7.80)),
            ("it", (44.00, 44.05, 7.66, 7.80)), ("it", (44.05, 44.10, 7.69, 7.80)), ("it", (43.75, 43.80, 7.52, 7.60)),
            ("it", (43.80, 43.85, 7.51, 7.60)), ("it", (43.85, 43.92, 7.51, 7.60)), ("it", (43.72, 43.75, 7.53, 7.60)),
            ("it", (44.10, 44.15, 7.66, 7.80)), ("it", (44.135, 44.15, 7.45, 7.66)))

SOURCES: List[Source] = [
    Source(
        id="south_tyrol", name="South Tyrol (DTM / DSM 2.5 m)",
        description="Autonomous Province of Bolzano - South Tyrol: terrain and surface models 2.5 m "
                    "(LiDAR 2004-2006 in the mountains), ETRS89 / UTM 32N",
        nmt=_bz_layer("DigitalTerrainModel", "DTM 2.5 m (terrain)"),
        nmpt=_bz_layer("DigitalElevationModel", "DSM 2.5 m (trees, buildings)"),
        countries=("it",), regions=("it-bz",), crs="EPSG:25832", grid_origin=BZ_ORIGIN,
        ortho=BZ_ORTHO, credits=(BZ_CREDIT,),
        # Its neighbours first at its borders; the rest of Italy from TINITALY, what that leaves (beyond Italy,
        # the sea) from FABDEM / Copernicus
        fallback="tinitaly", more_fallbacks=("europe",),
        neighbours=("austria", "swisstopo", "trento"),
        listing=ReadmeRow("South Tyrol (IT)", "Province of Bolzano DTM, 2.5 m (LiDAR 2004-2006)",
                          "Province of Bolzano DSM, 2.5 m", "Province of Bolzano 2023"),
        offline=(("it-bz", (46.21, 47.10, 10.38, 12.48)),), sample=(46.5208, 11.7325),
        note="South Tyrol's models are 2.5 m from the LiDAR of 2004-2006 in the mountains: lines shorter "
             "than about 15 m are not reliable, and rockfall since then is not in the data.",
        coverage=Coverage(provider="Provincia di Bolzano", added="2026-11-01", survey="2004–2006",
                          min_length=15, notes=("old_survey",))),
    Source(
        id="trento", name="Trento (LiDAR 2014, 0.5 m)",
        description="Autonomous Province of Trento: LiDAR 2014 terrain and surface (first returns) models 0.5 m, "
                    "ETRS89 / UTM 32N",
        nmt=_tn_layer("2014_lidar_dtm_asc", "DTM", "dtm", "DTM 0.5 m (terrain)"),
        nmpt=_tn_layer("2014_lidar_dsmfirst_asc", "DSMFirst", "dsm", "DSM 0.5 m (trees, buildings)"),
        countries=("it",), regions=("it-tn",), crs="EPSG:25832", credits=(TN_CREDIT,),
        fallback="tinitaly", more_fallbacks=("europe",),
        neighbours=("south_tyrol",),
        listing=ReadmeRow("Trento (IT)", "Province of Trento LiDAR 2014 DTM, 0.5 m", "Province of Trento DSM, 0.5 m",
                          "– (no open orthophoto service)"),
        offline=(("it-tn", (45.67, 46.54, 10.45, 11.97)),), sample=(45.9245, 10.8855),
        note="Trento's models come from the LiDAR of 2014 (with flights of 2018): rockfall and buildings since "
             "then are not in the data. Data: Provincia autonoma di Trento, CC BY 4.0. No open orthophoto "
             "service of Trento: the map shows its own base layers.",
        coverage=Coverage(provider="Provincia di Trento", added="2026-11-02", survey="2014")),
    Source(
        id="sardinia", name="Sardinia (coastal lidar 2008, 1 m)",
        description="Regione Autonoma della Sardegna: lidar DTM and DSM 1 m of the coastal strip (2008), WGS 84 / "
                    "UTM 32N; inland and gaps from TINITALY 10 m",
        nmt=_sar_layer("dtm", "dtm", "DTM 1 m (terrain)"), nmpt=_sar_layer("dsm", "dsm", "DSM 1 m (trees, buildings)"),
        countries=("it",), regions=("it-88",), crs="EPSG:32632", grid_origin=SAR_ORIGIN, credits=(SAR_CREDIT,),
        # The lidar covers the coast only: inland and its gaps from TINITALY, what that leaves (the sea, beyond
        # Italy) from FABDEM / Copernicus
        fallback="tinitaly", more_fallbacks=("europe",),
        listing=ReadmeRow("Sardinia (IT)", "Regione Sardegna lidar DTM 2008, 1 m (the coastal strip; inland "
                                           "TINITALY 10 m)", "Regione Sardegna lidar DSM 2008, 1 m",
                          "– (no open orthophoto service)"),
        # The box stops at 41.32 N, where France's Corsica box starts: La Maddalena's islands (Razzoli up to
        # 41.313 N) are Sardinia's, Lavezzi (from 41.327 N) Corsica's
        offline=(("it-88", (38.85, 41.32, 8.10, 9.85)),), sample=(40.8843, 8.2237),
        note="Sardinia's lidar (2008, 1 m) covers a strip of about 1-3 km along most of the coast only: inland and "
             "in its gaps the data are TINITALY's 10 m (lines shorter than about 60 m there are not reliable). "
             "Rockfall since 2008 is not in the data. Data: Regione Autonoma della Sardegna, CC BY 4.0. No open "
             "orthophoto service of Sardinia: the map shows its own base layers.",
        coverage=Coverage(provider="Regione Sardegna", added="2026-11-15", partial=True, rest=(10.0,),
                          survey="2008", notes=("old_survey",))),
    Source(
        id="tinitaly", name="TINITALY 1.1 (INGV, 10 m)",
        description="INGV's TINITALY 1.1: a terrain model 10 m of Italy, San Marino and the Vatican (a TIN of contour "
                    "lines, spot heights and other surveys), WGS 84 / UTM 32N",
        # On the WCS's own pixels (edges on whole 10 m), so the working grid is UTM 32N everywhere. No surface
        # model, as the other national 10 m terrain models (islandsdem10, nz8m, usgs10m): Copernicus GLO-30 against
        # a 10 m terrain would stand above every wall's smoothed foot; a regional source's surface gaps it fills
        # take its terrain (as RGE ALTI's for France's LiDAR HD)
        nmt=TINITALY_DEM, countries=("it", "sm", "va"), crs="EPSG:32632", credits=(TINITALY_CREDIT,),
        # After the regional sources' own neighbours (South Tyrol's before it at Switzerland's grids). Not Austria
        # nor France: each has six neighbours, the most the country layer's partner index holds (1-6); their
        # borders with Italy keep FABDEM / Copernicus for the other side's gaps
        neighbours=("swisstopo", "slovenia"),
        listing=ReadmeRow("Italy, San Marino, Vatican City (and the gaps of the Italian regional sources)",
                          "INGV TINITALY 1.1, 10 m (WCS)"),
        offline=IT_BOXES, sample=(42.4700, 13.5600),  # Corno Piccolo, Gran Sasso
        note="Data: INGV, TINITALY 1.1, CC BY 4.0. TINITALY is a terrain model at 10 m interpolated from contour "
             "lines, spot heights and other surveys: walls come out less steep than they are, lines shorter than "
             "about 60 m are not reliable, and a line over a forest looks clear. The working grid is WGS 84 / UTM "
             "32N: lengths east of 12 E are up to 0.4 % too long (0.8 % at Otranto).",
        coverage=Coverage(provider="INGV", added="2026-11-15", areas=("it",), survey="mosaic", min_length=60,
                          notes=("smoothed",))),
]
