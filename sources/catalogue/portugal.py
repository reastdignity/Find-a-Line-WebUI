"""Portugal: Madeira island's 2 m terrain model (DROTe, Região Autónoma da Madeira) as our own 2 km tiles in the
local mirror (tools/mirror_tiles.py). The rest of Portugal, Porto Santo, the Desertas and the Selvagens keep
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
# only (742 km²); the 5 m ZIP of the same record covers every island (not used). tools/mirror_tiles.py cuts it into
# 2 km tiles on its own pixel grid (origin (1, 1)) into the local mirror (FINDALINE_MIRROR/madeira/dtm/2m); without
# the mirror the source is unavailable and --source auto takes europe. A frozen survey: a versioned folder. The file
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

SOURCES: List[Source] = [
    Source(
        id="madeira", name="DROTe Madeira (MDT 2 m)",
        description="DROTe (Regiao Autonoma da Madeira): terrain model 2 m of Madeira island (photogrammetry "
                    "2018-2019), PTRA08 / UTM 28N; our own tiles from the local mirror",
        nmt=MADEIRA_DTM, countries=("pt",), regions=("pt-30",), crs="EPSG:5016", default_resolution=2.0,
        grid_origin=MADEIRA_ORIGIN, ortho=MADEIRA_ORTHO, credits=(MADEIRA_CREDIT,),
        # Porto Santo, the Desertas and the Selvagens (no 2 m data) and the sea from FABDEM / Copernicus
        fallback="europe",
        listing=ReadmeRow("Madeira (PT)", "DROTe MDT 2 m, photogrammetry 2018–2019 (Madeira island; the other "
                                          "islands FABDEM)", "–", "DROTe orthophoto 2023"),
        # Before Spain in FAMILIES: Spain's offline box (27-43.9 N, 18.6 W-4.4 E) holds Portugal and Madeira too
        offline=(("pt-30", (32.35, 33.15, -17.35, -16.25)),), sample=(32.8630, -17.1941),
        note="Madeira's terrain model (DROTe, 2 m, photogrammetry 2018-2019) covers Madeira island only; no surface "
             "model, so trees are not checked. Its tiles come from the local mirror (tools/mirror_tiles.py).",
        coverage=Coverage(provider="DROTe", added="2026-11-15", partial=True, rest=(30.0,), survey="2018–2019")),
]
