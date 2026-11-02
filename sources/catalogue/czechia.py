"""Czechia: ČÚZK's digital terrain model DMR 5G and surface model DMP 1G (2 m) from its ArcGIS ImageServers, in
S-JTSK / Krovak East North (no key)."""

from typing import List

from ..credit import YEAR, Credit
from ..source import OrthoService, ReadmeRow, Source
from ..layers.imageserver import ImageServerTiles

# ČÚZK's terms of its spatial data ("Podmínky poskytování prostorových dat ČÚZK", read 2026-11-02; Czech): the
# open data (DMR 5G, DMP 1G and the orthophoto among them) under CC BY 4.0; "tiskové výstupy z těchto dat a
# prohlížecí služby nad těmito daty musí obsahovat uvedení zdroje ve formátu: „ČÚZK, [rok]“, kde časové údaje
# jsou vztaženy k aktuálnosti použitého datového souboru", with a link to the terms, and a description of the
# changes of a changed work (credit.PROCESSED_NOTE). The services name no edition date, so the year is the
# run's (sources.YEAR), as for Lower Saxony. The terms of its network services ("Podmínky poskytování síťových
# služeb ČÚZK", version 1.0 of 4.3.2016) ask for "ČÚZK – on-line" where a viewing service is used in the user's
# own product (the orthophoto tiles) and a link to them; they allow commercial and non-commercial use "pokud
# rozsah užití není na újmu poskytovatele", and ČÚZK may stop a user who overloads its infrastructure. No
# request limit in numbers: net.HOST_SLOTS_OF caps the host as a courtesy.
CZ_DATA_TERMS = ("https://cuzk.gov.cz/Predpisy/Podminky-poskytovani-prostor-dat-a-sitovych-sluzeb/"
                 "Podminky-poskytovani-prostorovych-dat-CUZK.aspx")
CZ_SERVICE_TERMS = ("https://cuzk.gov.cz/Predpisy/Podminky-poskytovani-prostor-dat-a-sitovych-sluzeb/"
                    "Podminky-poskytovani-sitovych-sluzeb-CUZK.aspx")
CZ_CREDIT = Credit("DMR 5G / DMP 1G (ČÚZK, Czechia)", f"ČÚZK, {YEAR}", "CC BY 4.0", CZ_DATA_TERMS,
                   notice=f"Digitální model reliéfu České republiky 5. generace (DMR 5G) and digitální model povrchu "
                          f"1. generace (DMP 1G): ČÚZK, {YEAR}, CC BY 4.0, read from ČÚZK's network services "
                          f"(terms: {CZ_SERVICE_TERMS}).")

# The ImageServers of the two models, as they answered on 2026-11-02 (ArcGIS Server 12; tests/test_imageserver.py
# on recorded answers): one mosaic raster each of 2 m pixels, float32, Baltic heights (Bpv, vcsWkid 8357), WKID
# 102067 = EPSG:5514, at most 15000 x 4100 px a request. Each on a grid of its own (found from the extents and by
# sampling at 0.1 m): DMR 5G's pixel edges at x 0.4, y 1.88 modulo 2 m, DMP 1G's at 1.69, 1.98. exportImage on
# that grid with nearest neighbour gives the stored values exactly (a box equals its halves and a one-pixel
# shift); outside the country it answers 0 without a nodata tag unless noData is given (-9999, as asked). Tiles of
# 1000 px (2 km, about 3 MB with LZ77, under a second each). The models are updated from new surveys (a national
# laser scanning from 2026 on): the folders are "live".
CZ_SERVICES = "https://ags.cuzk.gov.cz/arcgis2/rest/services"
CZ_CRS = "EPSG:5514"
CZ_DMR_ORIGIN = (0.4, 1.88)
CZ_DMP_ORIGIN = (1.69, 1.98)
CZ_DMR = ImageServerTiles("ČÚZK DMR 5G 2 m (terrain)", f"{CZ_SERVICES}/dmr5g/ImageServer", CZ_CRS,
                          "czechia/dmr5g/live", 2.0, tile_px=1000, origin=CZ_DMR_ORIGIN)
# On its own grid, 0.71 and 0.1 m from the terrain model's: mosaic.prepare_layer interpolates it bilinearly onto
# the working grid (the terrain model's), as any layer on other pixels; the cache keeps its stored values
CZ_DMP = ImageServerTiles("ČÚZK DMP 1G 2 m (trees, buildings)", f"{CZ_SERVICES}/dmp1g/ImageServer", CZ_CRS,
                          "czechia/dmp1g/live", 2.0, tile_px=1000, origin=CZ_DMP_ORIGIN)

# The orthophoto's tiles in Web Mercator (the same host; levels to 23, maxScale 564 is zoom 20)
CZ_ORTHO = OrthoService("ČÚZK Ortofoto", None, "", "czechia/ortho/live", "ČÚZK – on-line",
                        base_url="https://ags.cuzk.gov.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}",
                        base_max_zoom=20, attribution_url=CZ_SERVICE_TERMS)

# Czechia comes first in FAMILIES (the first box holding a point wins): Poland's box holds most of Bohemia and
# Moravia, Slovakia's the east of Moravia. So these boxes keep inside the country as far as boxes allow, off
# Polish, Slovak, Austrian and German land; the first touches Poland's, Slovakia's and Austria's boxes
# (tests/test_neighbours.py). Offline, the salients of Šluknov, Frýdlant and Javorník, Broumov's east and the
# north of Jeseník fall to Poland's box, the south below about 48.95 N (Znojmo, Mikulov, Břeclav) to Austria's
# or Slovakia's, the rest of the border strips to no box
CZ_OFFLINE = (("cz", (48.95, 49.95, 15.5, 17.2)),  # Vysočina and the middle of Moravia
              ("cz", (49.25, 50.25, 12.95, 15.5)),  # the middle of Bohemia
              ("cz", (48.6, 49.25, 13.85, 14.95)),  # South Bohemia
              ("cz", (49.0, 49.25, 14.95, 15.5)),
              ("cz", (49.45, 50.3, 12.5, 12.95)),   # the west (Tachov, Karlovy Vary)
              ("cz", (50.0, 50.3, 12.25, 12.5)),    # Cheb
              ("cz", (50.25, 50.55, 12.95, 14.1)),  # under the Ore Mountains
              ("cz", (50.25, 50.8, 14.1, 15.3)),    # Děčín, Liberec
              ("cz", (50.25, 50.64, 15.3, 16.2)),   # the Giant Mountains, Adršpach
              ("cz", (49.95, 50.1, 15.5, 17.7)),    # East Bohemia
              ("cz", (50.1, 50.25, 15.5, 16.45)),   # the Eagle Mountains
              ("cz", (50.1, 50.25, 16.8, 17.6)),    # Jeseník
              ("cz", (49.45, 49.95, 17.2, 18.6)),   # Ostrava
              ("cz", (49.0, 49.45, 17.2, 18.1)))    # Zlín

SOURCES: List[Source] = [
    Source(
        id="czechia", name="ČÚZK (DMR 5G / DMP 1G)",
        description="ČÚZK (Czechia): digital terrain model DMR 5G and surface model DMP 1G, 2 m from its "
                    "ImageServers, S-JTSK / Krovak East North, Bpv heights",
        # The working grid on the terrain model's pixels, in its CRS: Krovak's scale error stays within about
        # -0.01 % and +0.014 % over the country
        nmt=CZ_DMR, nmpt=CZ_DMP, countries=("cz",), crs=CZ_CRS, grid_origin=CZ_DMR_ORIGIN, ortho=CZ_ORTHO,
        credits=(CZ_CREDIT,), neighbours=("geoportal", "slovakia", "austria"),
        listing=ReadmeRow("Czechia", "ČÚZK DMR 5G, 2 m (ImageServer)", "ČÚZK DMP 1G, 2 m (ImageServer)",
                          "ČÚZK Ortofoto"),
        offline=CZ_OFFLINE, sample=(50.6115, 16.1170),  # Adršpach (R44)
        note=f"Data: ČÚZK, {YEAR}, CC BY 4.0 (processed: mosaicked onto the working grid). DMR 5G comes mostly from "
             "the airborne laser scanning of 2009-2013, thinned: narrow rock towers may be smoothed. The surface "
             "model DMP 1G lies on other pixels and is interpolated onto the terrain model's."),
]
