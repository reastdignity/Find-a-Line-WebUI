"""List the PROJ-data grids of interest from cdn.proj.org's files.geojson (a downloaded JSON file,
read as data only). Usage: python -I proj_grids.py <files.geojson>"""
import json
import sys

PREFIXES = ("us_nga_egm", "pl_gugik", "ch_swisstopo", "sk_gku", "us_noaa_g2018", "us_noaa_g2012b",
            "us_noaa_geoid", "es_ign", "mt_", "eur_", "us_noaa_xgeoid", "us_noaa_g2012bu0")
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
for feat in data["features"]:
    p = feat["properties"]
    name = p.get("name", "")
    if name.startswith(PREFIXES) and not name.endswith(".txt"):
        print(f"{name:55s} {p.get('file_size', 0) / 1e6:8.2f} MB  type={p.get('type', '')!s:32s} "
              f"area={p.get('area_of_use', '')!s:40.40s} added={p.get('version_added', '')} "
              f"src={p.get('source_id', '')}")
