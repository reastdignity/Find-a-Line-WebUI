"""Uruguay: IDE Uruguay's national terrain model of 2.5 m (photogrammetric, flown 2017-2018) as whole sheet files,
and the IDE's national orthophoto (WMTS)."""

from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from ..credit import Credit
from ..source import Coverage, OrthoService, ReadmeRow, Source
from ..layers.geosheets import GeoSheetTiles

# IDE Uruguay's (Infraestructura de Datos Espaciales) national DTM of 2.5 m from the photogrammetric flight of
# 2017-2018 ("Modelo Digital del Terreno", files of 2018-09-22): 6 597 sheets of 0.06 x 0.045 degrees in 12
# deliveries ("remesas"), each a GeoTIFF at <UY_DATA>/CN_Remesa_<nn>/01_MDT/02_MDT_GeoTIFF_Resolucion_250cm/
# <sheet>_MDT_Remesa_<nn>.tif (an Apache server). A file is float32, uncompressed, one row per strip with its
# directory at the end (so never read in windows: downloaded whole, about 20 MB), in SIRGAS-ROU98 / UTM 21S
# (EPSG:5382; some eastern sheets in 22S, EPSG:5383), nodata -32767, AREA_OR_POINT=Point, cut to its sheet's
# box with its origin off whole metres (G26A6 at 654460.0374 / 6209564.7505): Download keeps each file's own
# pixels and the mosaic resamples them onto the working grid. Heights above EGM2008 (the survey's metadata).
# The national flight is frozen (the Minas flight of 2025 covers one town): a versioned folder. No request
# limits published (net.HOST_SLOTS_OF: two at once).
UY_DATA = "https://visualizador.ide.uy/descargas/datos"
# The sheets' grid: cell (i, j) of 0.06 x 0.045 degrees from 58.68 W / 35.10 S, j northwards. A sheet's name is
# its place in the 1:50 000 grid of sheets of 0.36 x 0.18 degrees: a letter for the column (westwards from
# 53.28-52.92 W: A B C D E F G H J K L M N O P R, no I and no Q), two digits for the row (southwards, 03 at
# 30.06-30.24 S), then the quarter (A north-west, B north-east, C south-west, D south-east, 0.18 x 0.09 degrees)
# and its sixth (1-3 the northern row west to east, 4-6 the southern). Checked against every sheet of the IDE's
# index Grillas/Nacional/Articulacion_Ortoimagenes_Nacional.shp (2026-11-15: all 6 597 names equal)
UY_CELL = (0.06, 0.045)
UY_ORIGIN = (-58.68, -35.10)
UY_LETTERS = "ABCDEFGHJKLMNOPR"


def uy_sheet(i: int, j: int) -> Optional[str]:
    """The name of the sheet of cell (i, j) (G26A6), None outside the national grid's letters and rows."""
    k, r = len(UY_LETTERS) - 1 - i // 6, 30 - j // 4
    if not (i >= 0 and j >= 0 and 0 <= k < len(UY_LETTERS) and r >= 0):
        return None
    cx, cy = i % 6, 3 - j % 4  # the sixth's column (west to east) and row (north to south) in the sheet
    return f"{UY_LETTERS[k]}{r:02d}{'ABCD'[(cy >= 2) * 2 + (cx >= 3)]}{cx % 3 + 1 + 3 * (cy % 2)}"


def uy_cell(name: str) -> Optional[Tuple[int, int]]:
    """The cell (i, j) of a sheet's name, None when it is not one."""
    if len(name) != 5 or name[0] not in UY_LETTERS or not name[1:3].isdigit() or name[3] not in "ABCD" \
            or name[4] not in "123456":
        return None
    k, r, q, d = UY_LETTERS.index(name[0]), int(name[1:3]), "ABCD".index(name[3]), int(name[4]) - 1
    cx, cy = (q % 2) * 3 + d % 3, (q // 2) * 2 + d // 3
    cell = (len(UY_LETTERS) - 1 - k) * 6 + cx, (30 - r) * 4 + 3 - cy
    return cell if uy_sheet(*cell) == name else None


@lru_cache(maxsize=None)
def _uy_remesas() -> Dict[Tuple[int, int], int]:
    cells = {}
    for remesa, text in UY_REMESAS.items():
        for row in text.split():
            j, runs = row.split(":")
            for run in runs.split(","):
                first, _, last = run.partition("-")
                for i in range(int(first), int(last or first) + 1):
                    cells[(i, int(j))] = remesa
    return cells


def uy_url(i: int, j: int) -> Optional[str]:
    """The file of the sheet of cell (i, j), None when the IDE has none (not in UY_REMESAS)."""
    remesa = _uy_remesas().get((i, j))
    if remesa is None:
        return None
    return (f"{UY_DATA}/CN_Remesa_{remesa:02d}/01_MDT/02_MDT_GeoTIFF_Resolucion_250cm/"
            f"{uy_sheet(i, j)}_MDT_Remesa_{remesa:02d}.tif")


# The cells of the grid: columns 0-95 (the 16 letters), rows 0-111 (rows 30 to 03); the table's cells are within
UY_MDT = GeoSheetTiles("IDE Uruguay MDT 2.5 m (terrain)", "uruguay/mdt250/2018", "EPSG:4326", UY_CELL, UY_ORIGIN,
                       2.5, uy_sheet, uy_cell, uy_url, within=(0, 0, 95, 111), bytes_per_tile=20e6)

# The Licencia de Datos Abiertos - Uruguay (version 0.1, read 2026-11-15) asks every use to name the provider,
# the licence and the dataset, and to mention changes in that note (credit.PROCESSED_NOTE)
UY_LICENCE_URL = f"{UY_DATA}/00_Licencia_de_datos_abiertos.pdf"
UY_CREDIT = Credit("Modelo Digital del Terreno nacional 2,5 m, vuelo 2017-2018 (IDEuy)",
                   "Infraestructura de Datos Espaciales de Uruguay (IDEuy): Modelo Digital del Terreno nacional "
                   "2,5 m (vuelo 2017-2018), Licencia de Datos Abiertos – Uruguay",
                   "Licencia de Datos Abiertos – Uruguay", UY_LICENCE_URL,
                   notice=f"Dataset: {UY_DATA}/ (CN_Remesa_01-12, 01_MDT, GeoTIFF 2.5 m), IDE Uruguay.")
# The IDE's national orthophoto (about 0.6 m at zoom 18; its zoom-19 tiles are enlargements) as GeoWebCache WMTS
# tiles in Web Mercator, keyless, under the same licence (2026-11-15)
UY_ORTHO = OrthoService(
    "Ortofoto nacional (IDE Uruguay)", None, "", "uruguay/ortho/live",
    "Ortofoto nacional, Infraestructura de Datos Espaciales de Uruguay (IDEuy), Licencia de Datos Abiertos – "
    "Uruguay", attribution_url=UY_LICENCE_URL,
    base_url="https://mapas.ide.uy/geoserver-raster/gwc/service/wmts/rest/ortofotos:ortofoto_nacional/raster/"
             "EPSG:3857/EPSG:3857:{z}/{y}/{x}?format=image/jpeg", base_max_zoom=18)


def uy_crs(lat: float, lon: float) -> str:
    """SIRGAS-ROU98 / UTM of a point: zone 21S (EPSG:5382, most files' own) west of 54 W, 22S (EPSG:5383) east."""
    return "EPSG:5382" if lon < -54.0 else "EPSG:5383"


SOURCES: List[Source] = [
    Source(
        id="uruguay", name="IDE Uruguay MDT 2.5 m",
        description="IDE Uruguay: national terrain model of 2.5 m from the photogrammetric flight of 2017-2018, "
                    "its sheets resampled onto SIRGAS-ROU98 / UTM of the place, EGM2008 heights",
        nmt=UY_MDT, countries=("uy",), local_crs=uy_crs, ortho=UY_ORTHO, credits=(UY_CREDIT,),
        listing=ReadmeRow("Uruguay", "IDE Uruguay MDT 2.5 m (photogrammetric, 2017-2018)", "–",
                          "IDE Uruguay ortofoto nacional"),
        # The sample on Arequita (R73): Quebrada de los Cuervos, the first choice, gives no line at 2.5 m
        offline=(("uy", (-35.05, -30.08, -58.45, -53.10)),), sample=(-34.2913, -55.2673),
        note="Data: Infraestructura de Datos Espaciales de Uruguay (IDEuy), Licencia de Datos Abiertos - Uruguay. "
             "The 2.5 m model is photogrammetric (2017-2018): vertical walls are smoothed and short ones may be "
             "missed. No surface model: trees and buildings are not in the data.",
        coverage=Coverage(provider="IDE Uruguay", added="2026-11-15", survey="2017–2018", notes=("smoothed",))),
]

# The sheets of each delivery (remesa) from the IDE's index (Nombre, Remesa: 6 597 sheets, equal to the listings
# of the 12 folders, 2026-11-15), as runs of cells "<j>:<i0>-<i1>,<i2> ..." per row j of the grid (UY_CELL from
# UY_ORIGIN). Recipe: read the index with pyogrio; cell (i, j) = (round((west + 58.68) / 0.06),
# round((south + 35.10) / 0.045)); check uy_sheet(i, j) == Nombre; group by Remesa and row. The flight is frozen,
# so the table is static; a cell outside it has no file
UY_REMESAS: Dict[int, str] = {
    1: (
        "3:39-41 4:38-41 5:37-41 6:37-41 7:33-41 8:32-43 9:32-43 10:32-43 11:32-43 12:31-44 13:31-45,56-59 "
        "14:31-50,55-59 15:31-51,55-59 16:31-59 17:30-59 18:30-59 19:29-59 20:28-59 21:27-59 22:27-59 23:26-58 "
        "24:26-58 25:26-56 26:27-56 27:27-55 28:27-34,39-50 29:27-34,39-49 30:28-32,40-47 31:29-30"
    ),
    2: (
        "26:25-26 27:25-26 28:25-26,35-38 29:25-26,35-38 30:25-27,33-39 31:25-28,31-41 32:25-41 33:25-41 34:25-41 "
        "35:25-41 36:25-41 37:25-41 38:25-41 39:25-41 40:28-41 41:28-41 42:28-41 43:28-41 44:28-39 45:28-39 "
        "46:28-39 47:28-39 48:28-39 49:28-39 50:28-39 51:28-39 52:28-39 53:28-39 54:28-39 55:28-39 56:28-39 "
        "57:28-39 58:28-39 59:28-39 60:28-39 61:28-39 62:28-39 63:28-39 64:28-39"
    ),
    3: (
        "8:30-31 9:29-31 10:28-31 11:27-31 12:26-30 13:12-16,18-19,25-30 14:12-30 15:12-30 16:11-30 17:11-29 "
        "18:9-29 19:9-28 20:6-27 21:7-26 22:6-26 23:6-25 24:4-25 25:4-25 26:4-24 27:4-24 28:4-24 29:4-24 30:4-24 "
        "31:4-24 32:4-24 33:4-24 34:4-24 35:4-24 36:4-24 37:4-24 38:4-24 39:4-24 40:5-22 41:5-22 42:5-22 43:5-22"
    ),
    4: (
        "40:23-27 41:23-27 42:23-27 43:23-27 44:5-27 45:8-27 46:8-27 47:9-27 48:9-27 49:9-27 50:9-27 51:9-27 "
        "52:8-27 53:8-27 54:8-27 55:8-27 56:8-27 57:8-27 58:8-27 59:8-27 60:8-27 61:8-27 62:9-27 63:9-27 64:8-27"
    ),
    5: (
        "25:57-59 26:57-59 27:56-59 28:51-59 29:50-59 30:48-59 31:42-59 32:42-59 33:42-59 34:42-59 35:42-59 "
        "36:42-59 37:42-59 38:42-59 39:42-59 40:42-59 41:42-59 42:42-59 43:42-59 44:40-59 45:40-59 46:40-59 "
        "47:40-59 48:40-59 49:40-59 50:40-59 51:40-59 52:40-59 53:40-59 54:40-59 55:40-59 56:40-59 57:40-59"
    ),
    6: (
        "1:62-63 2:61-63 3:42,45-46,56-57,60-64 4:42-46,56-66 5:42-46,55-68 6:42-69 7:42-71 8:44-73 9:44-76 "
        "10:44-76 11:44-76 12:45-76 13:46-55,60-76 14:51-54,60-76 15:52-54,60-76 16:60-76 17:60-76 18:60-76 "
        "19:60-76 20:60-76 21:60-76 22:60-76 23:59-76 24:59-76 25:60-76 26:60-76 27:60-76 28:60-76"
    ),
    7: (
        "29:60-76 30:60-76 31:60-76 32:60-76 33:60-76 34:60-76 35:60-76 36:60-76 37:60-76 38:60-76 39:60-76 "
        "40:60-76 41:60-76 42:60-76 43:60-76 44:60-76 45:60-77 46:60-77 47:60-77 48:60-77 49:60-77 50:60-77 "
        "51:60-77 52:60-77 53:60-77 54:60-77 55:60-77 56:60-77 57:60-77"
    ),
    8: (
        "58:40-77 59:40-77 60:40-77 61:40-77 62:40-77 63:40-77 64:40-77 65:38-77 66:38-77 67:38-77 68:38-77 "
        "69:38-77 70:38-77 71:38-77 72:38-75 73:38-74 74:38-73 75:38-72 76:38-71"
    ),
    9: (
        "11:77 12:77-78 13:77-79 14:77-81 15:77-82 16:77-82 17:77-82 18:77-82 19:77-83 20:77-84 21:77-85 22:77-85 "
        "23:77-86 24:77-86 25:77-86 26:77-86 27:77-87 28:77-88 29:77-88 30:77-88 31:77-87 32:77-85 33:77-85 "
        "34:77-85 35:77-85 36:77-84 37:77-84 38:77-85 39:77-85 40:77-85 41:77-84 42:77-84 43:77-84 44:77-85 "
        "45:78-85 46:78-86 47:78-88 48:78-89 49:78-89 50:78-89 51:78-89 52:78-91 53:78-91 54:78-91 55:78-90 "
        "56:78-88 57:78-87 58:78-86 59:78-84 60:78-84 61:78-84 62:78-83 63:78-83 64:78-83 65:78-82 66:78-82 "
        "67:78-82 68:78-80 69:78-80 70:78"
    ),
    10: (
        "65:8-37 66:8-37 67:8-37 68:8-37 69:8-37 70:8-37 71:8-37 72:8-37 73:10-37 74:10-37 75:10-37 76:11-37 "
        "77:11-37 78:11-37 79:10-37 80:10-37 81:10-37 82:11-37 83:11-37 84:11-37 85:12-37"
    ),
    11: (
        "77:38-70 78:38-70 79:38-69 80:38-69 81:38-67 82:38-63 83:38-62 84:38-61 85:38-58,60-61 86:37-57 87:37-56 "
        "88:37-56 89:37-55 90:37-55 91:37-54 92:37-46,49-53 93:37-45,50-52 94:37-44,50-52 95:37-44 96:37-44 "
        "97:37-42 98:37-42 99:37-41 100:37-40 101:37-40 102:37-39 103:37-38 104:37"
    ),
    12: (
        "86:12-36 87:12-36 88:12-36 89:13-36 90:13-36 91:13-36 92:13-36 93:14-36 94:14-36 95:14-36 96:14-36 "
        "97:14-36 98:14-36 99:13-36 100:13-36 101:13-36 102:13-36 103:14-36 104:15-36 105:16-36 106:17-35 "
        "107:17-34 108:17-18,25-34 109:17-18,25-33 110:25-31 111:26-31"
    ),
}
