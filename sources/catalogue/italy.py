"""Italy: the Autonomous Province of Bolzano / South Tyrol (its DTM and DSM 2.5 m, WCS), the Autonomous Province
of Trento (its LiDAR 2014 DTM and DSM 0.5 m, ASCII grids of 500 m), Sardinia (its coastal lidar DTM and DSM 1 m of
2008, ZIPs of ASCII grids listed by a WFS of their footprints), Tuscany (Regione Toscana's and the Ministry of the
Environment's lidar sheets 1 m of 2004-2017, credited per owner) and INGV's TINITALY 1.1 (10 m, WCS) for the rest of
Italy, San Marino and the Vatican and for the gaps of the regional sources. Valle d'Aosta: the region's DTM 2005/2008
2 m as our own 2 km tiles in the local mirror (tools/mirror_tiles.py); its DSM follows by hand later."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.gridtiles import GridTiles
from ..layers.cartoteca import CartotecaTiles
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


# Valle d'Aosta's DTM 2005/2008 2 m (lidar 2005 and 2008, "quota ortometrica (geoidica)" through IGM's grids), whole
# region, is published as one ZIP per product: DTM0508_002_UNICO.zip (2 604 729 175 B) holds one ESRI ASCII grid of
# 9.85 GB packed with Deflate64 (ZIP method 9: Python's zipfile cannot, 7-Zip can), decimal commas, CRLF, 44 174 x
# 28 557 px, ED50 / UTM 32N (EPSG:23032), x edges on even and y edges on odd metres (xllcorner 329116,000024,
# yllcorner 5036774,999974), NODATA -9999, millimetre values. The host's firewall answers HTTP 500 to a Range
# starting beyond about 1e8 bytes and the per-section ZIPs need a token for their index, so tools/mirror_tiles.py
# downloads the whole ZIP once with one plain GET (the manual: the service is "non per download massivi"; this is
# the region's own bulk product, fetched once) and cuts it into 2 km tiles on its own pixel grid (origin (0, 1)) into
# the local mirror (FINDALINE_MIRROR/aosta/dtm/2m); without the mirror the source is unavailable and --source auto
# takes TINITALY. The DSM (DSM0508_002) follows by hand later (the user's decision of 2026-11-14): this source has no
# surface layer until then. No request limits published (istruzioni.pdf, CC_BY_DTM_v2.pdf, read 2026-11-15)
VDA_LICENCE = "https://metadati.partout.it/metadata_documents/CC_BY_DTM_v2.pdf"
# CC_BY_DTM_v2.pdf (DGR 1620/2016): "Deve riconoscere una menzione di paternità adeguata su tutti gli elaborati che
# utilizzeranno dati estratti dal Modello Digitale del Terreno (DTM), apponendo la seguente dicitura: Dati estratti
# dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta." and "Deve fornire un link alla licenza
# e indicare se sono state effettuate delle modifiche": the sentence verbatim, the licence's link, the change in the
# notice (PROCESSED_NOTE says the rest)
VDA_CREDIT = Credit("DTM 2005/2008 2 m (Regione Autonoma Valle d'Aosta)",
                    "Dati estratti dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta.",
                    "CC BY 4.0", VDA_LICENCE,
                    notice="Modifiche: il DTM è stato tagliato in tessere di 2 km e compresso con un errore massimo di "
                           "5 mm (changed: cut into 2 km tiles, stored within 5 mm).")
VDA_ORIGIN = (0.0, 1.0)  # x edges on even, y edges on odd metres (tools/mirror_tiles.py DATASETS["aosta"])
# The tile's size measured over the mirror's tiles with data (tools/mirror_tiles.py cut, 2026-11-15)
VDA_DTM = GridTiles("Valle d'Aosta DTM 2 m (terrain)", [], "EPSG:23032", "italy/aosta-dtm0508-2m/2008/epsg23032-2m-2km",
                    2000, 2.0, 1.6e6, mirror="aosta/dtm/2m", origin=VDA_ORIGIN,
                    tool="tools/mirror_tiles.py")
# The region's offline boxes: bands of its outline (Nominatim's relation 45155, 2026-11-15), each from the region's
# westernmost to its easternmost land in the band rounded outwards to 0.01 deg, 0.025 deg high along the southern edge
# so that the Canavese (Ivrea, Valchiusella) stays out and Pont-Saint-Martin in: 100 % of the region, 0.067 deg2 of
# its neighbours' land (France, Piedmont, Switzerland; Carema at the border is in). North of 45.8 N Switzerland's box
# comes first in SOURCES
VDA_BOXES = tuple(("it-23", box) for box in (
    (45.46, 45.475, 7.04, 7.23), (45.475, 45.50, 7.00, 7.27), (45.50, 45.525, 6.99, 7.40),
    (45.525, 45.55, 6.99, 7.44), (45.55, 45.575, 6.98, 7.79), (45.575, 45.60, 6.97, 7.91),
    (45.60, 45.625, 6.98, 7.91), (45.625, 45.65, 6.92, 7.94), (45.65, 45.70, 6.84, 7.93),
    (45.70, 45.75, 6.80, 7.94), (45.75, 45.80, 6.80, 7.90), (45.80, 45.85, 6.80, 7.88),
    (45.85, 45.90, 6.94, 7.88), (45.90, 45.95, 7.00, 7.87), (45.95, 45.99, 7.47, 7.71)))


# Tuscany: Regione Toscana's lidar DTM and DSM of its own surveys (2004-2017) and of the Ministry of the Environment's
# (MATTM: 2008, 2010, 2016), 1 m (some 2 m), one file per survey of a 1:2000 sheet (1600 x 1200 m in Monte Mario /
# Italy zone 1, EPSG:3003, and a 20 m buffer: two neighbours' buffers hold the same values, checked at Carrara), a
# Deflate ZIP of an ARC/INFO ASCII grid without a CRS (xllcenter <edge>.5: pixel edges on whole metres), nodata
# -9999, millimetre values, "quota geoidica" (orthometric), and the owner's licence (licenza_dati_Lidar.pdf).
# Listed by the cartoteca's WFS feature type rt_cartoteca.lidar2k, which its capabilities do not name but which
# answers GetFeature (11 281 entries on 2026-11-15: 9 889 with their sheet's box, 1 392 of the surveys of 2016 and
# 2017 with only their footprint); a survey covers its footprint only, often part of a sheet, so every survey adding
# data to the newer ones is read (sources/indexes/cartoteca.py). The files' URLs carry a 32-hex hash no index gives:
# one GetFeatureInfo per survey (sources/readers/cartoteca.py). A survey under a newer one with a changed wall
# (Carrara's quarries: up to 22 m between RT 2012 and MATTM 2010) is hidden by it. No request limits published (the
# WMS's and WFS's Fees and AccessConstraints none; the GetFeatureInfo's licence notes; read 2026-11-15). The
# image-correlation DSM of 2021 (another layer, EPSG:7791) and the 2019-2021 lidar of the noRT layer (for public
# bodies only) are not used
TOS_WMS = "https://www502.regione.toscana.it/wmsraster/com.rt.wms.RTmap/wms?map=wmscartoteca"
TOS_TYPE = "rt_cartoteca.lidar2k"
# The citations each owner's licence asks for, verbatim ("La pubblicazione del dataset o di sue elaborazioni implica la
# citazione della fonte con la seguente dicitura: ..." in licenza_dati_Lidar.pdf of every sheet's ZIP, read
# 2026-11-15): Regione Toscana's surveys under CC BY 4.0 (its Decreto Dirigenziale n. 663/2014), the Ministry's
# under CC BY-SA 3.0 IT ("Creative Commons Attribuzione Condividi allo stesso modo 3.0 Italia"), also the 351 MATTM
# sheets co-owned with the Pisan municipalities, which the GetFeatureInfo calls "RT". A run is credited by the owners
# of the sheets it used (the user's decision of 2026-11-15): with a MATTM sheet, its results are share-alike
TOS_RT_CREDIT = Credit("Rilievi LIDAR 1 m (Regione Toscana)", "Fonte dei dati: Regione Toscana – “Rilievi LIDAR”",
                       *CC_BY, notice="Terms: licenza_dati_Lidar.pdf in each sheet's ZIP (Regione Toscana, Decreto "
                                      "Dirigenziale n. 663/2014)")
TOS_MATTM_CREDIT = Credit(
    "Rilievi Lidar 1 m (Ministero dell’Ambiente, distributed by Regione Toscana)",
    "Fonte dei dati: Ministero dell’Ambiente e della tutela del Territorio e del Mare – “Rilievi Lidar”",
    "CC BY-SA 3.0 IT", "https://creativecommons.org/licenses/by-sa/3.0/it/",
    notice="Share-alike: what is made from these data (this run's lines, heights, profiles and maps) is shared under "
           "the same licence (CC BY-SA 3.0 IT or a later version of it)")
TOS_CREDITS = {"RT": TOS_RT_CREDIT, "MATTM": TOS_MATTM_CREDIT}
TOS_LABELS = {"RT": "Regione Toscana's surveys", "MATTM": "the Ministry of the Environment's surveys"}
# Tuscany's land in bands of 0.05° from Nominatim's outline of the Toscana (relation 41977, 2026-11-15; consecutive
# bands of one width merged): its islands (Gorgona, Capraia, Elba, Pianosa, Montecristo, Giglio, Giannutri) in
# boxes of their own, Corsica (east to 9.56 E) outside; the bands hold slivers of Liguria (about 140 km²),
# Emilia-Romagna (990), Umbria (280) and Lazio (190), where an offline guess gets Tuscany, no lidar, and TINITALY
TOS_BOXES = (("it-52", (42.20, 42.30, 11.09, 11.12)), ("it-52", (42.30, 42.35, 10.28, 10.34)),
             ("it-52", (42.30, 42.35, 10.88, 10.94)), ("it-52", (42.35, 42.40, 10.06, 10.07)),
             ("it-52", (42.35, 42.40, 10.29, 10.32)), ("it-52", (42.35, 42.40, 10.86, 10.94)),
             ("it-52", (42.35, 42.40, 11.09, 11.46)), ("it-52", (42.40, 42.45, 11.08, 11.62)),
             ("it-52", (42.45, 42.50, 11.17, 11.63)), ("it-52", (42.50, 42.55, 11.16, 11.59)),
             ("it-52", (42.55, 42.60, 10.04, 10.11)), ("it-52", (42.55, 42.60, 10.88, 10.91)),
             ("it-52", (42.55, 42.60, 11.10, 11.70)), ("it-52", (42.60, 42.65, 10.07, 10.09)),
             ("it-52", (42.60, 42.65, 11.03, 11.81)), ("it-52", (42.65, 42.70, 10.99, 11.81)),
             ("it-52", (42.70, 42.75, 10.11, 10.44)), ("it-52", (42.70, 42.75, 10.92, 11.83)),
             ("it-52", (42.75, 42.80, 10.10, 10.44)), ("it-52", (42.75, 42.80, 10.71, 11.82)),
             ("it-52", (42.80, 42.85, 10.12, 10.45)), ("it-52", (42.80, 42.85, 10.72, 11.92)),
             ("it-52", (42.85, 42.90, 10.39, 10.55)), ("it-52", (42.85, 42.90, 10.76, 11.96)),
             ("it-52", (42.90, 42.95, 10.49, 11.96)), ("it-52", (42.95, 43.00, 10.48, 11.97)),
             ("it-52", (43.00, 43.05, 9.79, 9.85)), ("it-52", (43.00, 43.05, 10.50, 11.99)),
             ("it-52", (43.05, 43.10, 9.80, 9.85)), ("it-52", (43.05, 43.10, 10.53, 11.99)),
             ("it-52", (43.10, 43.15, 10.53, 11.93)), ("it-52", (43.15, 43.20, 10.53, 12.03)),
             ("it-52", (43.20, 43.25, 10.52, 12.12)), ("it-52", (43.25, 43.30, 10.48, 12.23)),
             ("it-52", (43.30, 43.35, 10.45, 12.22)), ("it-52", (43.35, 43.40, 10.42, 12.14)),
             ("it-52", (43.40, 43.45, 9.88, 9.91)), ("it-52", (43.40, 43.45, 10.37, 12.11)),
             ("it-52", (43.45, 43.50, 10.31, 12.15)), ("it-52", (43.50, 43.55, 10.21, 12.17)),
             ("it-52", (43.55, 43.60, 10.28, 12.20)), ("it-52", (43.60, 43.65, 10.28, 12.22)),
             ("it-52", (43.65, 43.70, 10.26, 12.34)), ("it-52", (43.70, 43.75, 10.27, 12.38)),
             ("it-52", (43.75, 43.80, 10.26, 12.33)), ("it-52", (43.80, 43.85, 10.24, 11.92)),
             ("it-52", (43.80, 43.85, 12.16, 12.24)), ("it-52", (43.85, 43.90, 10.21, 11.78)),
             ("it-52", (43.90, 43.95, 10.17, 11.72)), ("it-52", (43.95, 44.00, 10.10, 11.70)),
             ("it-52", (44.00, 44.05, 10.01, 11.70)), ("it-52", (44.05, 44.10, 9.98, 11.75)),
             ("it-52", (44.10, 44.15, 9.97, 11.76)), ("it-52", (44.15, 44.20, 9.85, 10.77)),
             ("it-52", (44.15, 44.20, 11.19, 11.62)), ("it-52", (44.20, 44.25, 9.85, 10.50)),
             ("it-52", (44.20, 44.25, 11.33, 11.46)), ("it-52", (44.25, 44.30, 9.77, 10.41)),
             ("it-52", (44.30, 44.35, 9.71, 10.23)), ("it-52", (44.35, 44.40, 9.68, 10.15)),
             ("it-52", (44.40, 44.45, 9.75, 10.01)), ("it-52", (44.45, 44.50, 9.80, 9.98)))


def _tos_layer(kind: str, description: str) -> CartotecaTiles:
    """One model's sheets; the index answers (tos-lidar) and the resolved URLs (tos-urls) shared by both models."""
    return CartotecaTiles(f"{description} Tuscany", TOS_WMS, TOS_TYPE, kind, "tos-lidar", f"italy/tos-{kind}",
                          "italy/sheet-index/tos-urls", TOS_CREDITS, TOS_LABELS, bytes_per_tile=5e6)


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
        id="aosta_valley", name="Valle d'Aosta (DTM 2005/2008, 2 m)",
        description="Regione Autonoma Valle d'Aosta: DTM 2005/2008 2 m (lidar), ED50 / UTM 32N; our own tiles from "
                    "the local mirror (the DSM follows later)",
        nmt=VDA_DTM, countries=("it",), regions=("it-23",), crs="EPSG:23032", default_resolution=2.0,
        grid_origin=VDA_ORIGIN, credits=(VDA_CREDIT,),
        # Gaps and the land beyond the region from TINITALY, then FABDEM / Copernicus. No neighbours: France
        # declares six already (the country layer's cap); swisstopo declares five, and its one free slot is left
        # unused pending the user's decision
        fallback="tinitaly", more_fallbacks=("europe",),
        listing=ReadmeRow("Valle d'Aosta (IT)", "Regione Valle d'Aosta DTM 2005/2008, 2 m (lidar)",
                          "– (the DSM follows by hand later)", "– (no open orthophoto service)"),
        offline=VDA_BOXES, sample=(45.7370, 7.3200),
        note="Valle d'Aosta's terrain model (2 m, lidar 2005 and 2008) comes from the local mirror; its surface model "
             "follows later, so trees are not checked yet, and rockfall since 2008 is not in the data. Data: Regione "
             "Autonoma Valle d'Aosta, CC BY 4.0. No open orthophoto service: the map shows its own base layers.",
        coverage=Coverage(provider="Regione Valle d'Aosta", added="2026-11-15", survey="2005–2008",
                          notes=("old_survey",))),
    Source(
        id="tuscany", name="Tuscany (lidar 1 m, 2004-2017)",
        description="Regione Toscana: lidar DTM and DSM 1 m (some 2 m) of its own and the Ministry of the "
                    "Environment's surveys 2004-2017, sheets of 1:2000, Monte Mario / Italy zone 1; elsewhere "
                    "TINITALY 10 m",
        nmt=_tos_layer("dtm", "DTM 1 m (terrain)"), nmpt=_tos_layer("dsm", "DSM 1 m (trees, buildings)"),
        countries=("it",), regions=("it-52",), crs="EPSG:3003", credits=(TOS_RT_CREDIT, TOS_MATTM_CREDIT),
        # The lidar covers about two thirds of the region: the rest and its gaps from TINITALY, what that leaves
        # (the sea, beyond Italy) from Copernicus GLO-30, never FABDEM: the Ministry's sheets are CC BY-SA, FABDEM
        # CC BY-NC-SA (as Queensland's are kept apart from it)
        fallback="tinitaly", more_fallbacks=("copernicus",),
        listing=ReadmeRow("Tuscany (IT)", "Regione Toscana / MATTM lidar DTM 2004-2017, 1 m (some 2 m; the rest "
                                          "TINITALY 10 m)", "Regione Toscana / MATTM lidar DSM, 1 m",
                          "– (no open orthophoto service)"),
        offline=TOS_BOXES, sample=(44.0870, 10.1340),  # the Carrara marble basins
        note="Tuscany's lidar (Regione Toscana and the Ministry of the Environment, 2004-2017, 1 m, some sheets 2 m) "
             "covers about two thirds of the region: elsewhere the data are TINITALY's 10 m (lines shorter than "
             "about 60 m there are not reliable). Quarries and rockfall since the survey are not in the data. A run "
             "that used the Ministry's sheets is CC BY-SA 3.0 IT (share-alike); Regione Toscana's are CC BY 4.0. No "
             "open orthophoto service of Tuscany: the map shows its own base layers.",
        coverage=Coverage(provider="Regione Toscana", added="2026-11-15", partial=True, rest=(10.0,),
                          survey="2004–2017", notes=("old_survey",))),
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
