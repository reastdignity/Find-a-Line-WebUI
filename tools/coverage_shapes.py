"""
The coverage map's outlines: countries and regions from Natural Earth (public domain), simplified.

Writes viewer/src/coverage/shapes.json, a GeoJSON FeatureCollection whose properties are `ShapeProperties` of
viewer/src/coverage/types.ts: every country of Natural Earth's admin-0 (1:50m), then the regions of the coverage
map's areas from its admin-1 (1:10m: ISO 3166-2 codes, the Canary Islands from both provinces, the nations of
Great Britain by `geonunit`, Jan Mayen, which admin-1 lacks, cut from Norway's outline: CUT). A country its source covers only in part (`Coverage.box`, else the source's
`bbox`: France without its overseas regions, Norway without Svalbard, New Zealand without the Chatham Islands)
is split: the covered part keeps the id, the rest is a feature of the same id with `rest: true`. Areas under
SMALL_KM2 are `small` (drawn as a dot too). tests/test_coverage.py checks that every area has a shape.

    uv run tools/coverage_shapes.py

The two ZIP files are downloaded once into the system's temporary folder, checked against their pinned sha256.
Then rebuild viewer/dist (`node build.mjs`: dist/coverage-shapes.json is a copy).
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile

import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import cache  # noqa: E402
import sources as src  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage_data  # noqa: E402

OUT = os.path.join(HERE, "viewer", "src", "coverage", "shapes.json")
# Natural Earth 5.1.1 (its VERSION.txt), checked 2026-11-02
NE = "https://naciscdn.org/naturalearth"
FILES = {
    "admin0": (f"{NE}/50m/cultural/ne_50m_admin_0_countries.zip",
               "5fed433373581fa648920435f937d95f2d3c0200e067409c6478dcdf1b853139"),
    "admin1": (f"{NE}/10m/cultural/ne_10m_admin_1_states_provinces.zip",
               "efc59726337323058f9446210adc96673179cd344e053666ee3d28cb58ba2b05"),
}
# Regions made of several admin-1 units (ISO 3166-2 codes); any other region is its own code
MERGED = {"es-cn": ("ES-GC", "ES-TF")}
# Regions without an admin-1 unit: their country's outline within a box (south, north, west, east)
CUT = {"no-22": ("no", (70.5, 71.5, -9.5, -7.5))}
# Regions of Great Britain: Natural Earth's admin-1 units of a nation (`geonunit`)
NATIONS = {"gb-eng": "England", "gb-wls": "Wales", "gb-sct": "Scotland", "gb-nir": "Northern Ireland"}
SMALL_KM2 = 10_000
PRECISION = 0.01            # degrees of the coordinates
# Degrees of the simplification: a region is drawn over its country, so finer, unless it is as large as one
# (Alaska, from the 1:10m admin-1)
TOLERANCE = {"country": 0.03, "region": 0.01}
LARGE_KM2 = 200_000
EQUAL_AREA = "EPSG:6933"    # for the areas in km²


def download(name: str) -> str:
    """The path of a Natural Earth file in the temporary folder, downloaded when missing or changed."""
    url, sha256 = FILES[name]
    folder = os.path.join(tempfile.gettempdir(), "findaline-natural-earth")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, url.rsplit("/", 1)[1])

    def digest(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    if os.path.exists(path) and digest(path) == sha256:
        return path
    print(f"downloading {url}")
    part = f"{path}.{os.getpid()}.part"
    with requests.get(url, headers=cache.http_headers(), stream=True, timeout=60) as answer:
        answer.raise_for_status()
        with open(part, "wb") as f:
            for block in answer.iter_content(1 << 20):
                f.write(block)
    if digest(part) != sha256:
        os.remove(part)
        raise SystemExit(f"{url}: not the pinned version (sha256 differs)")
    os.replace(part, path)
    return path


def simplified(geom, kind: str, area: float):
    """The outline as the map draws it: simplified, on a grid of PRECISION degrees, never empty."""
    import shapely
    valid = shapely.make_valid(geom)
    tolerance = TOLERANCE["country" if area > LARGE_KM2 else kind]
    out = shapely.set_precision(valid.simplify(tolerance, preserve_topology=True), PRECISION)
    if out.is_empty:  # a small island: less simplification
        out = shapely.set_precision(valid.simplify(PRECISION / 2), PRECISION)
    return out


def km2(geom) -> float:
    import geopandas as gpd
    return float(gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(EQUAL_AREA).area.iloc[0]) / 1e6


def feature(id_: str, kind: str, continent, geom, rest: bool = False) -> dict:
    from shapely.geometry import mapping
    area = km2(geom)
    props = {"id": id_, "kind": kind, "continent": continent, "small": area < SMALL_KM2}
    if rest:
        props["rest"] = True
    return {"type": "Feature", "properties": props, "geometry": mapping(simplified(geom, kind, area))}


def boxes() -> dict:
    """The part of each country area its source covers, as a shapely box: `Coverage.box`, else `bbox`."""
    from shapely.geometry import box
    out = {}
    for source in src.SOURCES.values():
        if source.coverage is None:
            continue
        clip = source.coverage.box or source.bbox
        for area in coverage_data.areas_of(source):
            if clip and "-" not in area:
                south, north, west, east = clip
                out[area] = box(west, south, east, north)
    return out


def regions():
    """The region areas of the catalogue."""
    return sorted({a for s in src.SOURCES.values() if s.coverage for a in coverage_data.areas_of(s) if "-" in a})


def shapes(admin0: str, admin1: str) -> dict:
    import geopandas as gpd
    import shapely
    countries = gpd.read_file(f"zip://{admin0}")
    units = gpd.read_file(f"zip://{admin1}", columns=["iso_3166_2", "geonunit", "adm0_a3"])
    # A country's id: ISO 3166-1 alpha-2, else Natural Earth's own code (Somaliland, Northern Cyprus); its
    # parts with the same code merged (Australia and its external territories)
    countries["id"] = [(a2 if a2 not in ("-99", None) else a3).lower()
                       for a2, a3 in zip(countries["ISO_A2_EH"], countries["ADM0_A3"])]
    clips = boxes()
    features = []
    for id_, rows in sorted(countries.groupby("id"), key=lambda item: item[0]):
        geom = shapely.union_all(list(rows.geometry))
        continent = max(zip(rows.geometry, rows["CONTINENT"]), key=lambda part: part[0].area)[1]  # the largest's
        if id_ in clips:
            covered, rest = geom.intersection(clips[id_]), geom.difference(clips[id_])
            features.append(feature(id_, "country", continent, covered))
            if not rest.is_empty:
                features.append(feature(id_, "country", continent, rest, rest=True))
        else:
            features.append(feature(id_, "country", continent, geom))
    for id_ in regions():
        if id_ in CUT:
            country, (south, north, west, east) = CUT[id_]
            geom = shapely.union_all(list(countries[countries["id"] == country].geometry)).intersection(
                shapely.box(west, south, east, north))
            if geom.is_empty:
                raise SystemExit(f"region {id_}: not in {country}'s outline")
            features.append(feature(id_, "region", None, geom))
            continue
        if id_ in NATIONS:
            rows = units[(units["adm0_a3"] == "GBR") & (units["geonunit"] == NATIONS[id_])]
        else:
            codes = MERGED.get(id_, (id_.upper(),))
            rows = units[units["iso_3166_2"].isin(codes)]
            if len(rows) != len(codes):
                raise SystemExit(f"region {id_}: {len(rows)} admin-1 units for {codes}")
        if rows.empty:
            raise SystemExit(f"region {id_}: not in Natural Earth's admin-1")
        features.append(feature(id_, "region", None, shapely.union_all(list(rows.geometry))))
    return {"type": "FeatureCollection", "features": features}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.parse_args(argv)
    data = shapes(download("admin0"), download("admin1"))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"{len(data['features'])} features, {os.path.getsize(OUT) / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
