"""Print 'name<TAB>url' lines for the CORS probe: one small tile per service near its source's sample point."""
import math
import sys

for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
    stream.reconfigure(encoding="utf-8", errors="replace")


def tile(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    r = math.radians(lat)
    y = int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)
    return x, y


def tile_bounds(z, x, y):
    n = 2 ** z
    west = x / n * 360 - 180
    east = (x + 1) / n * 360 - 180
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return south, west, north, east


def wms(base, layer, lat, lon, z=16, fmt="image/jpeg"):
    x, y = tile(lat, lon, z)
    s, w, n, e = tile_bounds(z, x, y)
    return (f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES=&CRS=EPSG:4326"
            f"&BBOX={s:.7f},{w:.7f},{n:.7f},{e:.7f}&WIDTH=256&HEIGHT=256&FORMAT={fmt}")


def xyz(template, lat, lon, z):
    x, y = tile(lat, lon, z)
    return template.format(z=z, x=x, y=y)


PL = (50.1559508, 19.7562722)
CH = (46.5960, 7.9070)
US = (38.5610, -109.5680)
ES = (41.5930, 1.8100)
SK = (49.1700, 18.5750)
MT = (35.8565, 14.3830)
AT = (47.2740, 11.3120)
HE = (51.1830, 9.0500)
MV = (54.5735, 13.6640)
ST = (51.7340, 11.0200)
NI = (51.8770, 10.4460)
BZ = (46.5208, 11.7325)
LU = (49.8205, 6.3460)
GP = "https://mapy.geoportal.gov.pl/wss/service/PZGIK"

rows = [
    ("geoportal WMS HighResolution", wms(f"{GP}/ORTO/WMS/HighResolution", "Raster", *PL)),
    ("geoportal WMTS StandardResolution", xyz(
        f"{GP}/ORTO/WMTS/StandardResolution?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTOFOTOMAPA"
        "&STYLE=default&FORMAT=image/jpeg&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}",
        *PL, 16)),
    ("swisstopo WMTS SWISSIMAGE", xyz(
        "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg", *CH, 16)),
    ("USGS ImageryOnly tiles", xyz(
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}", *US, 15)),
    ("IGN Spain WMS pnoa-ma", wms("https://www.ign.es/wms-inspire/pnoa-ma", "OI.OrthoimageCoverage", *ES)),
    ("ZBGIS WMS orthophoto", wms("https://zbgisws.skgeodesy.sk/zbgis_ortofoto_wms/service.svc/get", "1", *SK)),
    ("Malta WMS ortho_2018", wms("https://malta.coverage.wetransform.eu/wms/ortho_2018/ows", "OI.OrthoimageCoverage",
                                 *MT)),
    ("Esri World Imagery (server.arcgisonline.com, keyless)", xyz(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", *PL, 16)),
    ("Esri World Imagery (ibasemaps-api, no token)", xyz(
        "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", *PL, 16)),
    # orthophotos of the sources added on new-sources (now in main)
    ("basemap.at Orthofoto", xyz(
        "https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg", *AT, 16)),
    ("LVermGeo DOP20 WMS (Saxony-Anhalt)", wms(
        "https://www.geodatenportal.sachsen-anhalt.de/wss/service/ST_LVermGeo_DOP_WMS_OpenData/guest",
        "lsa_lvermgeo_dop20_2", *ST)),
    ("LGLN DOP20 WMS (Lower Saxony)", wms("https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
                                         "ni_dop20", *NI)),
    ("HVBG DOP WMS (Hesse)", wms("https://www.gds-srv.hessen.de/cgi-bin/lika-services/ogc-free-images.ows",
                                "he_dop_rgb", *HE)),
    ("LAiV DOP WMS (Mecklenburg-Vorpommern)", wms("https://www.geodaten-mv.de/dienste/adv_dop", "mv_dop", *MV)),
    ("South Tyrol orthophoto 2023 WMTS", xyz(
        "https://geoservices.buergernetz.bz.it/mapproxy/ows?service=WMTS&version=1.0.0&request=GetTile"
        "&layer=p_bz-Orthoimagery:Aerial-2023-RGB&style=default&tilematrixset=EPSG_3857"
        "&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/png", *BZ, 16)),
    ("geoportail.lu orthophoto WMTS", xyz(
        "https://wmts1.geoportail.lu/opendata/wmts/ortho_latest/GLOBAL_WEBMERCATOR_4_V3/{z}/{x}/{y}.jpeg", *LU, 16)),
    # terrain services a 3D view could use
    ("Esri Terrain3D LERC tile (elevation3d)", xyz(
        "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer/tile/{z}/{y}/{x}",
        *PL, 14)),
    ("AWS Terrain Tiles terrarium", xyz("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                                        *PL, 14)),
    ("Mapterhorn terrarium webp", xyz("https://tiles.mapterhorn.com/{z}/{x}/{y}.webp", *PL, 14)),
    ("swisstopo terrain quantized mesh (doc example)",
     "https://3d.geo.admin.ch/ch.swisstopo.terrain.3d/v1/20250101/11/2130/1550.terrain"),
]

for name, url in rows:
    print(f"{name}\t{url}")
