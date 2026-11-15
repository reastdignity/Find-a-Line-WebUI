"""Mexico: INEGI's high-resolution lidar elevation models of 5 m (terrain and surface), one ZIP per 1:10 000
sheet."""

import os
from typing import List

from ..credit import Credit
from ..source import Coverage, ReadmeRow, Source
from ..layers.inegi import InegiSheets

# INEGI's "Modelos Digitales de Elevación de Alta Resolución LiDAR" of 5 m (terrain "T" and surface "S", lidar of
# 2006-2012 interpolated through a TIN, editions 2011-2012): 26 334 terrain and 26 333 surface sheets of 1:10 000
# (3'20" x 3'45", sources.layers.inegi), about half of Mexico. The download viewer (elevacionesmex) asks
# getF10KDescarga.do?res=5&mod=<T|S>&cve=<sheet> for a sheet's products (a JSON list of about 1 kB: edition, datum
# ITRF92, url_descarga and archivo per product, GRID and ASCII; an empty list where there is none); the GRID
# product is a ZIP of about 4 MB (Terreno_GRID/<upc>_gr.zip) holding an ArcInfo GRID: float32, whole centimetres,
# nodata -FLT_MAX, 5 m pixels with their edges on whole 5 m of the sheet's UTM zone, no CRS (INEGI's metadata:
# ITRF92 epoch 1988.0, heights "NAVD88"). Each file reaches 100-400 m beyond its sheet (InegiGrid cuts it to the
# sheet). The viewer's RegistroDescarga.do (its log of downloads) is never asked. Neither endpoint is documented;
# GET works (wave 0, 2026-11-15). Limits: none published (the site's terms ask for "buen uso del sitio ... y a no
# causar daños en el mismo", https://www.inegi.org.mx/inegi/terminos.html, read 2026-11-15): two at once
# (net.HOST_SLOTS_OF)
MX_VIEWER = "https://www.inegi.org.mx/app/geo2/elevacionesmex"
MX_FILES = "https://www.inegi.org.mx/contenidos/productos/"  # the only place a sheet's JSON may send a download
# The cells of INEGI's lattice that hold a sheet of each model (tools/mx_sheets.py from the viewer's lists of
# getFormato10k.do, 2026-11-15): no JSON is asked for a cell without one, and --source auto takes europe where no
# sheet lies within 2 km of the centre (instead_without_data)
MX_SHEETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mexico_sheets.npz")
MX_TOP = "mexico/mde-lidar5m"
MX_DTM = InegiSheets("INEGI MDE LiDAR 5 m (terrain)", f"{MX_TOP}/t", "T", f"{MX_VIEWER}/getF10KDescarga.do",
                     MX_FILES, MX_SHEETS, MX_TOP)
MX_DSM = InegiSheets("INEGI MDE LiDAR 5 m (surface)", f"{MX_TOP}/s", "S", f"{MX_VIEWER}/getF10KDescarga.do",
                     MX_FILES, MX_SHEETS, MX_TOP)

# The "Términos de Libre Uso de la Información del INEGI" (https://www.inegi.org.mx/inegi/terminos.html, read
# 2026-11-15): credit INEGI as the author "de la siguiente manera: "Fuente: INEGI, nombre del producto de donde se
# extrae la información" y en su caso fecha de actualización", and tell users of any transformation without
# suggesting that INEGI made it (credit.PROCESSED_NOTE, and the notice); no endorsement
MX_TERMS = ("Términos de Libre Uso de la Información del INEGI", "https://www.inegi.org.mx/inegi/terminos.html")
MX_CREDIT = Credit("Modelos Digitales de Elevación de Alta Resolución LiDAR, 5 m (INEGI)",
                   "Fuente: INEGI, Modelos Digitales de Elevación de Alta Resolución LiDAR, 5 m (Terreno / "
                   "Superficie), ediciones 2011-2012",
                   *MX_TERMS,
                   notice="The models were cut to their sheets, resampled and combined by Find-a-Line, and the "
                          "lines computed from them; these transformations are not INEGI's, and INEGI does not "
                          "endorse Find-a-Line. Data: " + MX_VIEWER + "/ (5 m, Terreno and Superficie, GRID).")


def mx_crs(lat: float, lon: float) -> str:
    """Mexico ITRF92 / UTM of a point (zones 11-16, EPSG:4484-4489; a point outside takes the nearest): the CRS of
    INEGI's sheets of that zone, so they are placed on the working grid without resampling. PROJ takes Mexico
    ITRF92, Mexico ITRF2008 and WGS 84 as one (null transformations of 1-2 m accuracy), so the other data of a
    search (FABDEM, a neighbour's) land where they would on WGS 84 / UTM."""
    zone = min(16, max(11, int((lon + 180) // 6) + 1))
    return f"EPSG:{4484 + zone - 11}"


# Rough boxes of Mexico, kept off the United States' land (mexico comes before usa, whose box holds Monterrey):
# north of 25.8° N a staircase along the border in bands of longitude, each box's top below the southernmost US
# land of its band (Natural Earth's 1:50m outlines of the coverage map), so El Paso, Laredo, Eagle Pass, Del Rio,
# McAllen, Brownsville, Yuma, Nogales (Arizona) and San Diego stay with the usa while Ciudad Juárez, Nuevo Laredo,
# Piedras Negras, Reynosa, Matamoros, Nogales (Sonora), Mexicali and Tijuana are Mexico's; south of it the country
# without most of Guatemala and Belize
MX_BOXES = tuple(("mx", b) for b in (
    (28.0, 32.52, -117.3, -117.0), (28.0, 32.53, -117.0, -116.5), (28.0, 32.57, -116.5, -116.0),
    (28.0, 32.61, -116.0, -115.5), (28.0, 32.65, -115.5, -115.0), (22.8, 32.39, -115.0, -114.5),
    (22.8, 32.24, -114.5, -114.0), (22.8, 32.08, -114.0, -113.5), (22.8, 31.92, -113.5, -113.0),
    (22.8, 31.77, -113.0, -112.5), (22.8, 31.61, -112.5, -112.0), (22.8, 31.45, -112.0, -111.5),
    (22.8, 31.31, -111.5, -108.2), (22.8, 31.76, -108.2, -106.48), (22.8, 31.73, -106.48, -106.42),
    (22.8, 31.66, -106.42, -106.36), (22.8, 31.6, -106.36, -106.3), (22.8, 31.33, -106.3, -106.0),
    (25.8, 30.98, -106.0, -105.5), (25.8, 30.63, -105.5, -105.0), (25.8, 29.69, -105.0, -104.5),
    (25.8, 29.32, -104.5, -104.0), (25.8, 29.1, -104.0, -103.5), (25.8, 28.99, -103.5, -103.0),
    (25.8, 29.11, -103.0, -102.5), (25.8, 29.76, -102.5, -102.0), (25.8, 29.78, -102.0, -101.5),
    (25.8, 29.39, -101.5, -101.0), (25.8, 28.77, -101.0, -100.5), (25.8, 28.03, -100.5, -100.0),
    (25.8, 27.61, -100.0, -99.6), (25.8, 27.54, -99.6, -99.51), (25.8, 27.04, -99.51, -99.45),
    (25.8, 26.39, -99.45, -99.0), (25.8, 26.19, -99.0, -98.5), (25.8, 26.06, -98.5, -98.0),
    (25.8, 25.91, -98.0, -97.5), (25.8, 25.86, -97.5, -97.0),
    (18.5, 25.8, -106.0, -86.7), (17.82, 18.5, -106.0, -89.15), (14.5, 17.82, -106.0, -91.0)))
# Mexico's land along the US border that the staircase leaves to the usa's box, for the neighbour fill only (they
# hold US land too, where the static mask lists no sheet: no request is made there)
MX_BORDER_BOXES = ((31.2, 32.75, -117.3, -111.0), (31.2, 31.85, -111.0, -106.0), (28.9, 31.4, -106.0, -102.5),
                   (27.4, 29.9, -102.5, -99.4), (25.8, 27.6, -99.6, -97.0))

MX_NOTE = ("Fuente: INEGI, Modelos Digitales de Elevación de Alta Resolución LiDAR, 5 m. The 5 m models come from "
           "sparse lidar (2006-2012) interpolated through a triangle mesh: walls are smoothed and short ones may be "
           "missed. About half of Mexico has no sheet: there the gaps come from FABDEM 30 m. The surface model "
           "holds some spikes and pits of tens of metres.")


SOURCES: List[Source] = [
    Source(
        id="mexico", name="INEGI MDE LiDAR 5 m",
        description="INEGI: high-resolution lidar elevation models of 5 m (terrain and surface, 2006-2012), "
                    "1:10 000 sheets cut to their cells, Mexico ITRF92 / UTM of the place, NAVD88 heights",
        nmt=MX_DTM, nmpt=MX_DSM, countries=("mx",), local_crs=mx_crs, default_resolution=5.0,
        credits=(MX_CREDIT,),
        listing=ReadmeRow("Mexico, where it has lidar", "INEGI MDE LiDAR 5 m, terrain (2006-2012)",
                          "INEGI MDE LiDAR 5 m, surface"),
        offline=MX_BOXES, border_boxes=MX_BORDER_BOXES, sample=(25.9500, -100.4730),
        # The usa's 1 m DEM fills the US side of a border grid, as for Canada (not usgs10m: it has no boxes)
        neighbours=("usa",),
        # Where no sheet lies near the centre, --source auto takes europe instead
        instead_without_data="europe",
        note=MX_NOTE,
        # Partial: lidar sheets over about half of the country, FABDEM 30 m elsewhere
        coverage=Coverage(provider="INEGI", added="2026-11-15", partial=True, rest=(30.0,), survey="2006–2012",
                          notes=("smoothed",))),
]
