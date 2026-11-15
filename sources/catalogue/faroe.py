"""The Faroe Islands: Umhvørvisstovan's DSM 2015 2 m (a surface model from ArcticDEM's satellite stereo), one
national GeoTIFF read in blocks."""

from typing import List

from ..credit import YEAR, Credit
from ..source import Coverage, ReadmeRow, OrthoService, Source
from ..layers.fileblocks import FileBlocks

# ETRS89 / Faroe TM, the CRS of the files: a transverse Mercator on 7° W with scale factor 0.999997, so its scale
# error over the islands (6.2-7.7° W) stays below +0.002 %
FO_TM = "EPSG:5316"

# Umhvørvisstovan's (the Faroese Environment Agency's) DSM 2015, 2 m, from its file server (the files "updated
# 2024-11-12", frequency "rarely"): 39 233 x 57 644 px float32, LZW, 128 px tiles, no overviews (1.39 GB, read in
# windows only), nodata 3.4e38 (the sea), heights above the sea in sub-centimetres; its pixel edges lie off whole
# metres (the file starts at 161 177.791 m E, 923 243.743 m N), so the blocks and the working grid start there.
# It is ArcticDEM's 2015 surface upsampled (a grid pattern in hillshades, artefacts): snow, the few trees and the
# buildings are in it, there is no terrain model without them but a 10 m DTM of 2009 (FO_DTM_2009_10m.tif:
# compared at Enniberg, docs/roadmap.md batch 5), so the DSM is the terrain here as ArcticDEM is in the Arctic.
# A new upload is a new folder (the Last-Modified date) here and in the cache
FO_RELEASE = "20241112"
FO_DSM_URL = "https://cdn.foroyakort.fo/geodata/raster/DSM/2015/FO_DSM_2015_FOTM_2M.tif"
FO_LEFT, FO_TOP = 161177.7909712732, 923243.7428457682
FO_ORIGIN = (FO_LEFT % 2.0, FO_TOP % 2.0)  # the files' pixel edges modulo 2 m
FO_EXTENT = (FO_LEFT, FO_TOP - 57644 * 2.0, FO_LEFT + 39233 * 2.0, FO_TOP)
# Umhvørvisstovan's terms (https://www.foroyakort.fo/um-foeroyakort/terms-and-conditions-in-english, June 2019,
# read 2026-11-15): "a worldwide right to use the data ... copying, distributing and publishing; modifying and
# combining with other data; commercial and non-commercial use", credited "Data from the Faroese Environment Agency,
# Umhvørvisstovan:" with the datasets' names and the download date (their example: "Bygningar, June 2019"), with a
# copy of or a link to the terms. The month a run's blocks were downloaded is not kept, so the year of the run
# stands for it (as LGLN's credit, the user's decision of 2026-11-01)
FO_TERMS = "https://www.foroyakort.fo/um-foeroyakort/terms-and-conditions-in-english"
FO_CREDIT = Credit("DSM 2015 2 m (Umhvørvisstovan, the Faroe Islands)",
                   f"Data from the Faroese Environment Agency, Umhvørvisstovan: DSM 2015 (2 m), {YEAR}",
                   "Umhvørvisstovan's terms and conditions", FO_TERMS)

# Blocks of 2 km (1000 x 1000 px, about 64 of the file's 128 px tiles, 2-3 MB cached), from the file's own corner
FO_DSM = FileBlocks("Faroe DSM 2015 2 m (surface)", f"faroe/dsm-2015-2m/{FO_RELEASE}", FO_TM, 2.0, 2000, FO_DSM_URL,
                    origin=FO_ORIGIN, extent=FO_EXTENT, year=2015, bytes_per_tile=2.5e6, credit=FO_CREDIT)

# Umhvørvisstovan's orthophoto WMS (ArcGIS, layer 1 "Image"; EPSG:4326 in WMS 1.3.0; AccessConstraints
# "©Umhvørvisstovan"; about 0.6 s for 512 px; white where it has no imagery). Its terms as the DSM's
FO_ORTHO = OrthoService("Faroe orthophoto (Umhvorvisstovan)",
                        "https://gis.us.fo/arcgis/services/myndakort/myndakort_fotm/MapServer/WMSServer", "1",
                        "faroe/ortho/live", "©Umhvørvisstovan", attribution_url=FO_TERMS)

FO_BOX = (61.38, 62.42, -7.72, -6.22)

SOURCES: List[Source] = [
    Source(
        id="faroe_islands", name="Umhvorvisstovan DSM 2015 2 m (Faroe Islands)",
        description="Umhvorvisstovan (the Faroese Environment Agency): DSM 2015 2 m, a surface model from "
                    "ArcticDEM's satellite stereo, ETRS89 / Faroe TM; gaps from Copernicus GLO-30",
        nmt=FO_DSM, countries=("fo",), crs=FO_TM, grid_origin=FO_ORIGIN, ortho=FO_ORTHO, credits=(FO_CREDIT,),
        fallback="copernicus",
        listing=ReadmeRow("Faroe Islands", "Umhvorvisstovan DSM 2015, 2 m (a surface model)", "–",
                          "Umhvorvisstovan orthophoto"),
        offline=(("fo", FO_BOX),), sample=(62.385, -6.560),  # Enniberg (R71)
        note="Data from the Faroese Environment Agency, Umhvorvisstovan. Its DSM 2015 is a surface model from "
             "satellite stereo (ArcticDEM): the few trees and the buildings are part of it (there is no terrain "
             "model of that detail, so the check of trees is off); gaps are filled from 30 m data.",
        coverage=Coverage(provider="Umhvørvisstovan", added="2026-11-15", survey="2015", trees="surface")),
]
