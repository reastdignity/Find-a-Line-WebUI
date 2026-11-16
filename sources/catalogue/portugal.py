"""Portugal: Madeira island's 2 m terrain model (DROTe, Região Autónoma da Madeira) as our own 2 km tiles from the
project's data server or a local copy, and the 5 m terrain models of Porto Santo, the Desertas and the Selvagens
(the same owner) as our own 2 km tiles in the local mirror (tools/mirror_tiles.py). The rest of Portugal keeps
FABDEM / Copernicus (europe)."""

from typing import List

from ..credit import Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.gridtiles import GridTiles

# DROTe's MDT 2 m (Modelo Digital do Terreno, photogrammetry of UltraCam flights from 2018-10-03 to 2019-06-19,
# vegetation and buildings edited out, RMSEz 0.145 m) is published only as one ZIP of 460 MB holding one BigTIFF of
# 64 959 x 171 894 px (float32, DEFLATE with the horizontal predictor, one row per strip: nothing to read in parts),
# PTRA08 / UTM zone 28N (EPSG:5016), its pixel edges on odd metres (the corner 287 861, 3 666 229), no data -32768
# and -999, heights in metres with millimetre values (the sea at 0.2-0.3 m). Its valid pixels cover Madeira island
# only (742 km²); the 5 m ZIP of the same record holds a raster per island (below). tools/mirror_tiles.py cuts it into
# 2 km tiles on its own pixel grid (origin (1, 1)) into the mirror (madeira/dtm/2m: FINDALINE_MIRROR, or the data
# server); without either the source is unavailable and --source auto takes europe. A frozen survey: a versioned
# folder. The file
# server (irig-storage.madeira.gov.pt) publishes no request limits: the tool downloads the ZIP once
MADEIRA_RECORD = ("https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/"
                  "abba9a83-cb1c-4d2c-ad1d-ccb592247754")
# The SNIG record abba9a83 (read 2026-11-15): useLimitation "No conditions apply", "Acesso e uso sem condições",
# "Acesso público sem restrições"; no wording prescribed: the producer, the region and the survey's years named
MADEIRA_CREDIT = Credit("MDT 2 m (DROTe, Região Autónoma da Madeira)",
                        "DTM 2 m: Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da Madeira, "
                        "2018-2019", "No conditions apply", MADEIRA_RECORD)
MADEIRA_ORIGIN = (1.0, 1.0)  # the pixel edges on odd metres (tools/mirror_tiles.py DATASETS["madeira"])
# The tile's size measured over the mirror's tiles with data (tools/mirror_tiles.py cut, 2026-11-15)
MADEIRA_DTM = GridTiles("Madeira MDT 2 m (terrain)", [], "EPSG:5016", "portugal/madeira-dtm2m/2019/epsg5016-2m-2km",
                        2000, 2.0, 1.4e6, mirror="madeira/dtm/2m", origin=MADEIRA_ORIGIN,
                        tool="tools/mirror_tiles.py")
# The regional orthophoto of 2023 (SNIG record 08c3bd64-ccd2-4bde-a8b2-b915bff64dd9, "No conditions apply"): a QGIS
# server WMS whose layer Ortos is the mosaic of every island, asked in Web Mercator (it also serves EPSG:4326 and
# 5016); sharp, without a watermark, about 0.6 s a tile (checked 2026-11-15)
MADEIRA_ORTHO = OrthoService("Orthophoto 2023 (DROTe, Madeira)",
                             "https://irig-sig.madeira.gov.pt/ows/pg/qwc_config/DIR_orto_mosaico", "Ortos",
                             "portugal/madeira-ortho/2023", "Ortofotomapa 2023, DROTe, Região Autónoma da Madeira",
                             attribution_url=("https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/"
                                              "metadata/08c3bd64-ccd2-4bde-a8b2-b915bff64dd9"),
                             wms_crs="EPSG:3857")

# The 5 m ZIP of the same record (mdt_5m.zip, 114 126 877 B, members of 2026-05-18): a raster per island, each a
# dataset of our mirror of its own (tools/mirror_tiles.py DATASETS "porto-santo", "desertas", "selvagens"), 5 m with
# pixel edges at 2.5 m modulo 5 (origin (2.5, 2.5)). Porto Santo's is in Porto Santo 1995 / UTM zone 28N (EPSG:3061),
# the sea written as 0 (its nodata tag); GDAL (rasterio.warp.transform, the mosaic's) takes it to WGS 84 by "Porto
# Santo 1995 to WGS 84 (3)" over the data and the whole offline box, left unpinned (tests/test_madeira_aosta.py); its
# choice changes about 3 km east of the data, beyond that operation's area (-16.23 E): sea only. The Desertas' file is
# labelled EPSG:3061 but lies in PTRA08 (EPSG:5016: its coast against OSM's and the orthophoto's, 2026-11-15), the
# Selvagens' is in PTRA08; both hold -32768 outside, -999 at the coast and coast pixels averaged with -999 (below -1 m:
# no data, tools/mirror_tiles.py). Without their mirror folders --source auto takes Madeira's source there
# (unavailable too: then europe)
MADEIRA_5M_CREDIT = Credit("MDT 5 m (DROTe, Região Autónoma da Madeira)",
                           "DTM 5 m: Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da "
                           "Madeira, 2018-2019", "No conditions apply", MADEIRA_RECORD)
ISLAND_ORIGIN = (2.5, 2.5)
# Each tile's size measured over Porto Santo's mirror tiles with data (28, 2026-11-15)
ISLAND_TILE_BYTES = 0.09e6


def _madeira_island(sid: str, name: str, crs: str, folder: str, area: str, box, sample, note: str,
                    where: str) -> Source:
    """One island group of the 5 m ZIP as a source: our own tiles, chosen in Madeira's region by its box."""
    epsg = crs.split(":")[1]
    layer = GridTiles(f"{name} MDT 5 m (terrain)", [], crs, f"portugal/{folder}-dtm5m/2019/epsg{epsg}-5m-2km", 2000,
                      5.0, ISLAND_TILE_BYTES, mirror=f"{folder}/dtm/5m", origin=ISLAND_ORIGIN,
                      tool="tools/mirror_tiles.py")
    return Source(
        id=sid, name=f"DROTe {name} (MDT 5 m)",
        description=f"DROTe (Regiao Autonoma da Madeira): terrain model 5 m of {where} (photogrammetry 2018-2019); "
                    "our own tiles from the local mirror",
        nmt=layer, countries=("pt",), regions=("pt-30",), crs=crs, default_resolution=5.0, grid_origin=ISLAND_ORIGIN,
        ortho=MADEIRA_ORTHO, credits=(MADEIRA_5M_CREDIT,), fallback="europe", bbox=box,
        listing=ReadmeRow(f"{name} (PT)", "DROTe MDT 5 m, photogrammetry 2018–2019", "–", "DROTe orthophoto 2023"),
        offline=(("pt-30", box),), sample=sample,
        note=f"{note} Its tiles come from the local mirror (tools/mirror_tiles.py); no surface model, so trees are "
             "not checked.",
        coverage=Coverage(provider="DROTe", added="2026-11-15", areas=(area,), survey="2018–2019"))


SOURCES: List[Source] = [
    # Before Madeira's: a region's sources are taken in the order of SOURCES where their boxes hold the centre
    _madeira_island("porto_santo", "Porto Santo", "EPSG:3061", "porto-santo", "pt-30-ps",
                    (32.98, 33.14, -16.43, -16.26), (33.0750, -16.3400),
                    "Porto Santo's terrain model (DROTe, 5 m, photogrammetry 2018-2019).",
                    "Porto Santo, Porto Santo 1995 / UTM 28N"),
    _madeira_island("desertas", "Desertas", "EPSG:5016", "desertas", "pt-30-de", (32.39, 32.61, -16.57, -16.45),
                    (32.5180, -16.5000), "The Desertas' terrain model (DROTe, 5 m, photogrammetry 2018-2019).",
                    "the Desertas, PTRA08 / UTM 28N"),
    _madeira_island("selvagens", "Selvagens", "EPSG:5016", "selvagens", "pt-30-se", (30.02, 30.17, -16.07, -15.84),
                    (30.1420, -15.8690), "The Selvagens' terrain model (DROTe, 5 m, photogrammetry 2018-2019).",
                    "the Selvagens, PTRA08 / UTM 28N"),
    Source(
        id="madeira", name="DROTe Madeira (MDT 2 m)",
        description="DROTe (Regiao Autonoma da Madeira): terrain model 2 m of Madeira island (photogrammetry "
                    "2018-2019), PTRA08 / UTM 28N; our own tiles from the project's data server or a local copy",
        nmt=MADEIRA_DTM, countries=("pt",), regions=("pt-30",), crs="EPSG:5016", default_resolution=2.0,
        grid_origin=MADEIRA_ORIGIN, ortho=MADEIRA_ORTHO, credits=(MADEIRA_CREDIT,),
        # the sea, and the other islands while their mirror folders are missing, from FABDEM / Copernicus
        fallback="europe",
        listing=ReadmeRow("Madeira (PT)", "DROTe MDT 2 m, photogrammetry 2018–2019 (Madeira island)", "–",
                          "DROTe orthophoto 2023"),
        # Madeira island only (the other islands have their own boxes); before Spain in FAMILIES: Spain's offline
        # box (27-43.9 N, 18.6 W-4.4 E) holds Portugal and Madeira too
        offline=(("pt-30", (32.6, 32.9, -17.35, -16.6)),), sample=(32.8630, -17.1941),
        note="Madeira's terrain model (DROTe, 2 m, photogrammetry 2018-2019) covers Madeira island only; no surface "
             "model, so trees are not checked. Its tiles come from the project's data server or a local copy "
             "(tools/mirror_tiles.py).",
        coverage=Coverage(provider="DROTe", added="2026-11-15", survey="2018–2019")),
]
