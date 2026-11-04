"""
The coverage map's data, generated from the catalogue (sources/catalogue/, `Source.coverage`).

Writes viewer/src/coverage/coverage.json (its schema: `Coverage` of viewer/src/coverage/types.ts): an area per
country or region of a source on the map, its level, resolutions, trees, survey, provider and notes, and the
date it went live (the timeline). tests/test_coverage.py fails while the file is out of date.

    uv run tools/coverage_data.py           # rewrite coverage.json
    uv run tools/coverage_data.py --check   # exit 1 if coverage.json is out of date

Then rebuild viewer/dist (the bundles that import it hold the file).
"""

import argparse
import json
import os
import sys
from typing import Dict, List

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import sources as src  # noqa: E402

OUT = os.path.join(HERE, "viewer", "src", "coverage", "coverage.json")
# The first version of Find-a-Line, the whole world at 30 m: the timeline's start
START = "2025-11-05"
# The rest of the world: the global sources (europe: FABDEM and Copernicus DEM)
WORLD = {"level": 3, "res": [30], "trees": "rough", "provider": "FABDEM / Copernicus DEM"}
# Fallbacks that fill gaps at 30 m: the world's level, no note of their own
GLOBAL = ("europe", "nasadem")
# Territories counted with their state
TERRITORIES = {"pr": "us", "vi": "us", "ax": "fi"}


def _number(value: float):
    """Metres as JSON writes them best: 1 rather than 1.0."""
    return int(value) if float(value).is_integer() else float(value)


def level_of(res: float) -> int:
    """The colour of a resolution: 1 (1 m or finer), 2 (up to 5 m), 3 (coarser)."""
    return 1 if res <= 1 else 2 if res <= 5 else 3


def areas_of(source) -> List[str]:
    """The areas of a source on the map: its coverage's, else its regions, else its countries."""
    return list(source.coverage.areas or source.regions or source.countries)


def country_of(area: str) -> str:
    """The country an area counts for: a region's, a territory's state."""
    code = area.split("-", 1)[0]
    return TERRITORIES.get(code, code)


def notes_of(source, res: List[float], trees: str) -> List[dict]:
    """The notes of a source's areas in the order they are shown."""
    cov = source.coverage
    notes = []
    if cov.rest:
        notes.append({"code": "mixed"})
    if trees == "no":
        notes.append({"code": "no_trees"})
    fallback = source.fallbacks[0] if source.fallbacks else None
    if fallback and fallback not in GLOBAL:
        fill = src.SOURCES[fallback].default_resolution
        if fill not in cov.rest:
            notes.append({"code": "gaps", "params": {"res": _number(fill)}})
    for code in cov.notes:
        notes.append({"code": code, "params": {"years": cov.survey}} if code == "old_survey" else {"code": code})
    if cov.min_length:
        notes.append({"code": "short", "params": {"m": _number(cov.min_length)}})
    return notes


def area_of(source) -> dict:
    """The entry of each area of a source."""
    cov = source.coverage
    res = [_number(source.default_resolution), *map(_number, cov.rest)]
    trees = cov.trees or ("yes" if source.nmpt is not None else "no")
    return {"source": source.id, "level": cov.level or level_of(res[0]), "partial": cov.partial, "res": res,
            "trees": trees, "survey": cov.survey, "provider": cov.provider,
            "notes": notes_of(source, res, trees), "added": cov.added}


def coverage() -> dict:
    """The content of coverage.json."""
    areas: Dict[str, dict] = {}
    for source in src.SOURCES.values():
        if source.coverage is None:
            continue
        for area in areas_of(source):
            if area in areas:
                raise SystemExit(f"area {area}: sources {areas[area]['source']} and {source.id}")
            areas[area] = area_of(source)
    partly: Dict[str, List[str]] = {}
    for area in areas:
        country = area.split("-", 1)[0]
        if "-" in area and country not in areas:
            partly.setdefault(country, []).append(area)
    return {"areas": areas, "partly": {k: sorted(v) for k, v in partly.items()},
            "countries": len({country_of(a) for a in areas}), "start": START, "world": WORLD}


def render() -> str:
    return json.dumps(coverage(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="only check; exit 1 if coverage.json is out of date")
    args = parser.parse_args(argv)
    new = render()
    try:
        with open(OUT, encoding="utf-8") as f:  # a Windows checkout has CRLF
            old = f.read()
    except FileNotFoundError:
        old = None
    if args.check:
        if new != old:
            print("viewer/src/coverage/coverage.json is out of date: run `uv run tools/coverage_data.py`")
            return 1
        return 0
    if new != old:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        print("viewer/src/coverage/coverage.json rewritten")
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
