"""Italy: the Autonomous Province of Bolzano / South Tyrol (its DTM and DSM 2.5 m, WCS)."""

from typing import List

from ..credit import Credit
from ..source import ReadmeRow, OrthoService, Source
from ..layers.wcs import WcsTiles

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


# The province's orthophoto of 2023 (20 cm, CC BY 4.0) from its MapProxy WMTS in Web Mercator
# (zoom 0-24 offered: the imagery's own detail ends at about 19); no request limits published
BZ_ORTHO = OrthoService(
    "Orthophoto 2023 (Autonomous Province of Bolzano)", None, "", "italy/bz-ortho/2023",
    "Orthofoto 2023: Autonome Provinz Bozen - Südtirol (CC BY 4.0)",
    base_url="https://geoservices.buergernetz.bz.it/mapproxy/ows?service=WMTS&version=1.0.0&request=GetTile"
             "&layer=p_bz-Orthoimagery:Aerial-2023-RGB&style=default&tilematrixset=EPSG_3857"
             "&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/png", base_max_zoom=19)


SOURCES: List[Source] = [
    Source(
        id="south_tyrol", name="South Tyrol (DTM / DSM 2.5 m)",
        description="Autonomous Province of Bolzano - South Tyrol: terrain and surface models 2.5 m "
                    "(LiDAR 2004-2006 in the mountains), ETRS89 / UTM 32N",
        nmt=_bz_layer("DigitalTerrainModel", "DTM 2.5 m (terrain)"),
        nmpt=_bz_layer("DigitalElevationModel", "DSM 2.5 m (trees, buildings)"),
        countries=("it",), regions=("it-bz",), crs="EPSG:25832", grid_origin=BZ_ORIGIN,
        ortho=BZ_ORTHO, credits=(BZ_CREDIT,),
        neighbours=("austria", "swisstopo"),
        listing=ReadmeRow("South Tyrol (IT)", "Province of Bolzano DTM, 2.5 m (LiDAR 2004-2006)",
                          "Province of Bolzano DSM, 2.5 m", "Province of Bolzano 2023"),
        offline=(("it-bz", (46.21, 47.10, 10.38, 12.48)),), sample=(46.5208, 11.7325),
        note="South Tyrol's models are 2.5 m from the LiDAR of 2004-2006 in the mountains: lines shorter "
             "than about 15 m are not reliable, and rockfall since then is not in the data."),
]
