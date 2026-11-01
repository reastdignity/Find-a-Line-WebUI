"""Record small real answers of the index services once, for the offline tests of the indexes
(tests/test_parts.py, served by tests/http_server.py).

    uv run tools/record_answers.py                    # every recipe
    uv run tools/record_answers.py stac-swisstopo     # one
    uv run tools/record_answers.py wfs-geoportal --lat 49.0 --lon 22.75

A recipe asks a layer of the catalogue for the index of one 0.25° tile, as `cache update`
does (`update_index_tile` on an empty cache: the index is asked, nothing is downloaded),
and saves every answer of the service in tests/data/recorded/<interface>/<case>/:
answers.json (the requests in order: method, URL, status, type, body file), the bodies
(gzipped above 64 kB) and expected.json, the index answer the code wrote for them. The
tests serve the answers again and the code must write expected.json byte for byte.
An error recipe asks a layer that does not exist (YEARS) and records the service's error
answer instead: no expected.json, the exception raised in answers.json ("raises").
Chosen tiles lie at the edge of the data, so the answers stay small. Requests go one at
a time with the app's User-Agent (cache.http_headers()). The licences of the answers are
in tests/data/recorded/README.md.
"""

import argparse
import datetime
import gzip
import json
import mimetypes
import os
import shutil
import sys
import tempfile
from urllib.parse import urlsplit

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import sources as src  # noqa: E402

OUT = os.path.join(ROOT, "tests", "data", "recorded")
GZIP_ABOVE = 64_000

# recipe: (interface, case, source, layer, lat, lon of the 0.25° tile's south-west corner)
RECIPES = {
    "wfs-geoportal": ("wfs", "geoportal-nmt", "geoportal", "nmt", 54.75, 18.5),
    "stac-swisstopo": ("stac", "swisstopo-swissalti3d", "swisstopo", "nmt", 47.75, 8.5),
    "tnm-1m": ("tnm", "dem1m", "usa", "nmt", 48.75, -95.25),
    "tnm-ifsar": ("tnm", "ifsar5m", "alaska_ifsar", "nmt", 59.75, -141.0),
    "wfs-geoportal-error": ("wfs", "geoportal-error", "geoportal", "nmt", 54.75, 18.5),
}
# The year layers a WFS recipe asks instead of those of the capabilities (none: GetFeature only)
YEARS = {"wfs-geoportal-error": ["gugik:SkorowidzNMT1900"]}


def _extension(content_type: str) -> str:
    kind = content_type.split(";")[0].strip()
    if "json" in kind:
        return ".json"
    if "xml" in kind or "gml" in kind:
        return ".xml"
    return mimetypes.guess_extension(kind) or ".bin"


def record(recipe: str, lat: float, lon: float, out: str = OUT) -> str:
    interface, case, sid, kind, _, _ = RECIPES[recipe]
    layer = getattr(src.SOURCES[sid], kind)
    folder = os.path.join(out, interface, case)
    answers = []
    original = requests.Session.send  # every request of requests and pystac-client passes it

    def recording(session, prepared, **kwargs):
        response = original(session, prepared, **kwargs)
        n = len(answers) + 1
        content_type = response.headers.get("content-type", "")
        body, name = response.content, f"{n:03d}{_extension(content_type)}"
        if len(body) > GZIP_ABOVE:
            body, name = gzip.compress(body, mtime=0), name + ".gz"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(body)
        answers.append({"method": prepared.method, "url": prepared.url, "status": response.status_code,
                        "content_type": content_type, "body": name})
        return response

    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    cache_dir = tempfile.mkdtemp(prefix="record-")
    case = {"source": sid, "layer": kind, "lat": lat, "lon": lon}
    years, raises = YEARS.get(recipe), None
    if years:
        case["years"] = years
        layer = with_years(layer, years)
    requests.Session.send = recording
    try:
        layer.update_index_tile(cache_dir, lat, lon)
    except requests.RequestException as e:
        if not years:
            raise
        raises = type(e).__name__
    finally:
        requests.Session.send = original
    if raises is None:
        with open(layer.index_path(cache_dir, lat, lon), "rb") as f:
            expected = f.read()
        with open(os.path.join(folder, "expected.json"), "wb") as f:
            f.write(expected)
    shutil.rmtree(cache_dir, ignore_errors=True)
    hosts = sorted({"{0.scheme}://{0.netloc}".format(urlsplit(a["url"])) for a in answers})
    with open(os.path.join(folder, "answers.json"), "w", encoding="utf-8") as f:
        json.dump({"recipe": recipe, "recorded": datetime.date.today().isoformat(),
                   "case": case, **({"raises": raises} if raises else {}),
                   "hosts": hosts, "answers": answers}, f, indent=1)
        f.write("\n")
    size = sum(os.path.getsize(os.path.join(folder, n)) for n in os.listdir(folder))
    result = f"raised {raises}" if raises else f"{len(json.loads(expected)['sheets'])} listed"
    return f"{recipe}: {len(answers)} answers, {result}, {size / 1e3:.0f} kB"


def with_years(layer, years):
    """A copy of a WFS sheet layer that asks these year layers and not the capabilities."""
    copy = src.SheetTiles(layer.description, layer.index_url, layer.prefix, layer.folder, layer.native_res,
                          layer.min_res)
    copy.index.listing._years = list(years)
    return copy


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recipes", nargs="*", help=f"of {', '.join(RECIPES)} (default: all)")
    parser.add_argument("--lat", type=float, help="the tile's south-west corner instead of the recipe's")
    parser.add_argument("--lon", type=float)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()
    unknown = set(args.recipes) - set(RECIPES)
    if unknown:
        parser.error(f"no recipe {', '.join(sorted(unknown))}")
    for recipe in args.recipes or list(RECIPES):
        lat = args.lat if args.lat is not None else RECIPES[recipe][4]
        lon = args.lon if args.lon is not None else RECIPES[recipe][5]
        print(record(recipe, lat, lon, args.out))


if __name__ == "__main__":
    main()
