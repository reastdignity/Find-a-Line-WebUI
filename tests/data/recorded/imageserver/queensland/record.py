"""Record small real answers of Queensland's DEM time series ImageServer (exportImage) for
tests/data/recorded/imageserver/queensland/ (run once, by hand, from the repository: `uv run python
tests/data/recorded/imageserver/queensland/record.py tests/data/recorded/imageserver/queensland`). Writes
exports.json (the cassette format of tests/http_server.py) and the bodies; the requests are those the layers of
sources/catalogue/australia.py make (their readers' export_params)."""

import json
import os
import sys
from urllib.parse import urlencode

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 5)))
from sources.catalogue.australia import QLD_DEMH, QLD_LIDAR  # noqa: E402

OUT = sys.argv[1]
HEADERS = {"User-Agent": "Find-a-Line (test recording)"}
# 16 x 16 px boxes (left, bottom) on whole metres: Mt Tibrogargan's east face (MGA 56), Mount Isa (MGA 54, the
# town's lidar of 2012), the sea east of Moreton Island (MGA 56); DEM-H at 30 m at Tibrogargan
TIBROGARGAN = (494770, 7021640)
ISA = (343040, 7707480)
SEA = (562000, 7002000)


def export(layer, crs, left, bottom, w, h, res, **change):
    reader = layer.readers[crs]
    params = reader.export_params(left, bottom, left + w * res, bottom + h * res, res)
    params = [(k, change.get(k, v)) for k, v in params]
    return f"{reader.export_url}?" + urlencode(params)


x, y = TIBROGARGAN
CASES = [
    ("full", export(QLD_LIDAR, "EPSG:28356", x, y, 16, 16, 1.0)),
    ("left", export(QLD_LIDAR, "EPSG:28356", x, y, 8, 16, 1.0)),
    ("right", export(QLD_LIDAR, "EPSG:28356", x + 8, y, 8, 16, 1.0)),
    ("isa", export(QLD_LIDAR, "EPSG:28354", *ISA, 16, 16, 1.0)),
    ("sea", export(QLD_LIDAR, "EPSG:28356", *SEA, 16, 16, 1.0)),
    ("demh", export(QLD_DEMH, "EPSG:28356", 494400, 7021400, 16, 16, 30.0)),
    ("bad-where", export(QLD_LIDAR, "EPSG:28356", x, y, 16, 16, 1.0,
                         mosaicRule='{"mosaicMethod":"esriMosaicAttribute","sortField":"ZOrder","where":"no_field = 1"}')),
]

os.makedirs(OUT, exist_ok=True)
answers = []
for n, (name, url) in enumerate(CASES, 1):
    r = requests.get(url, headers=HEADERS, timeout=120)
    kind = r.headers.get("content-type", "")
    ext = "json" if r.content[:1] == b"{" else ("tif" if r.content[:2] in (b"II", b"MM") else "bin")
    body = f"{n:03d}-{name}.{ext}"
    with open(os.path.join(OUT, body), "wb") as f:
        f.write(r.content)
    answers.append({"method": "GET", "url": url, "status": r.status_code, "content_type": kind, "body": body,
                    "case": name})
    print(name, r.status_code, kind, len(r.content), r.content[:200] if ext != "tif" else "")
with open(os.path.join(OUT, "exports.json"), "w", encoding="utf-8") as f:
    json.dump({"recipe": "imageserver-queensland", "recorded": "2026-11-02",
               "hosts": ["https://spatial-img.information.qld.gov.au"], "answers": answers}, f, indent=1,
              ensure_ascii=False)
    f.write("\n")
