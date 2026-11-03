"""Italy: the Autonomous Province of Bolzano / South Tyrol (its DTM and DSM 2.5 m, WCS) and the Autonomous Province
of Trento (its LiDAR 2014 DTM and DSM 0.5 m, ASCII grids of 500 m)."""

from typing import List

from ..credit import CC_BY, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
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


SOURCES: List[Source] = [
    Source(
        id="south_tyrol", name="South Tyrol (DTM / DSM 2.5 m)",
        description="Autonomous Province of Bolzano - South Tyrol: terrain and surface models 2.5 m "
                    "(LiDAR 2004-2006 in the mountains), ETRS89 / UTM 32N",
        nmt=_bz_layer("DigitalTerrainModel", "DTM 2.5 m (terrain)"),
        nmpt=_bz_layer("DigitalElevationModel", "DSM 2.5 m (trees, buildings)"),
        countries=("it",), regions=("it-bz",), crs="EPSG:25832", grid_origin=BZ_ORIGIN,
        ortho=BZ_ORTHO, credits=(BZ_CREDIT,),
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
        neighbours=("south_tyrol",),
        listing=ReadmeRow("Trento (IT)", "Province of Trento LiDAR 2014 DTM, 0.5 m", "Province of Trento DSM, 0.5 m",
                          "– (no open orthophoto service)"),
        offline=(("it-tn", (45.67, 46.54, 10.45, 11.97)),), sample=(45.9245, 10.8855),
        note="Trento's models come from the LiDAR of 2014 (with flights of 2018): rockfall and buildings since "
             "then are not in the data. Data: Provincia autonoma di Trento, CC BY 4.0. No open orthophoto "
             "service of Trento: the map shows its own base layers.",
        coverage=Coverage(provider="Provincia di Trento", added="2026-11-02", survey="2014")),
]
