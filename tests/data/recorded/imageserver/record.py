"""Record small real answers of ČÚZK's ImageServer exportImage for tests/data/recorded/imageserver/ (run once,
by hand). Writes answers.json in the cassette format of tests/http_server.py (add_cassette) and the bodies."""

import json
import os
import sys
from urllib.parse import urlencode

import requests

OUT = sys.argv[1]
BASE = "https://ags.cuzk.gov.cz/arcgis2/rest/services"
HEADERS = {"User-Agent": "Find-a-Line (test recording)"}


def export(service, box, w, h, **extra):
    params = {"bbox": ",".join(box), "bboxSR": "5514", "imageSR": "5514", "size": f"{w},{h}", "format": "tiff",
              "pixelType": "F32", "noData": "-9999", "interpolation": "RSP_NearestNeighbor",
              "compression": "LZ77", "f": "image", **extra}
    return f"{BASE}/{service}/ImageServer/exportImage?" + urlencode(params)


CASES = [
    ("dmr5g-json", f"{BASE}/dmr5g/ImageServer?f=json"),
    ("full", export("dmr5g", ("-615777.6", "-1000282.12", "-615745.6", "-1000250.12"), 16, 16)),
    ("left", export("dmr5g", ("-615777.6", "-1000282.12", "-615761.6", "-1000250.12"), 8, 16)),
    ("right", export("dmr5g", ("-615761.6", "-1000282.12", "-615745.6", "-1000250.12"), 8, 16)),
    ("shift", export("dmr5g", ("-615775.6", "-1000282.12", "-615743.6", "-1000250.12"), 16, 16)),
    ("dmp", export("dmp1g", ("-615776.31", "-1000282.02", "-615744.31", "-1000250.02"), 16, 16)),
    ("poland", export("dmr5g", ("-559081.6", "-990980.12", "-559049.6", "-990948.12"), 16, 16)),
    ("beyond", export("dmr5g", ("-915689.6", "-1026214.12", "-915657.6", "-1026182.12"), 16, 16)),
    ("too-high", export("dmr5g", ("-615777.6", "-1000282.12", "-615745.6", "-992080.12"), 16, 4101)),
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
    print(name, r.status_code, kind, len(r.content), r.content[:120] if ext != "tif" else "")
with open(os.path.join(OUT, "answers.json"), "w", encoding="utf-8") as f:
    json.dump({"recipe": "imageserver-cuzk", "recorded": "2026-11-02", "hosts": ["https://ags.cuzk.gov.cz"],
               "answers": answers}, f, indent=1, ensure_ascii=False)
    f.write("\n")
