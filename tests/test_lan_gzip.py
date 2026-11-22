"""tools/lan_app.py sends a run's store gzipped (gate 2's item 5: the phones over a slow link downloaded Gozo's 97 MB
as they are, the public site's nginx gzips them to 32 MB): lines.arrow and profiles.arrow with Content-Encoding gzip
when the browser accepts it, their bytes the file's, and web.SIZE_HEADER the file's size before compression (the page's
progress bar: viewer/src/download.ts bodySize); as they are without Accept-Encoding and for a Range; everything else
as the local app sends it."""

import gzip
import os
import sys

from fastapi.testclient import TestClient

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lan_app  # noqa: E402
import web  # noqa: E402

LAN = "https://192.0.2.5:8443"
RUN = "2026-11-22_100000_Store_0000000000000001"


def test_the_store_gzipped_with_its_size(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "app.js").write_text("window.LAN_BUILD = 'app';", encoding="utf-8")
    data = tmp_path / "data"
    run = data / "runs" / RUN
    run.mkdir(parents=True)
    # bytes that compress (as a store's columns do), and a text file of the run that the middleware leaves alone
    stores = {"lines.arrow": bytes(range(256)) * 4000, "profiles.arrow": b"profile " * 50000}
    for name, body in stores.items():
        (run / name).write_bytes(body)
    (run / "ATTRIBUTION.txt").write_text("credits " * 400, encoding="utf-8")
    app, _ = lan_app.make_app(str(data), 8443, ["192.0.2.5"], str(build), start_scheduler=False)
    with TestClient(app, base_url=LAN) as client:
        for name, body in stores.items():
            path = f"/runs/{RUN}/{name}"
            zipped = client.get(path, headers={"accept-encoding": "gzip"})
            assert zipped.status_code == 200 and zipped.headers["content-encoding"] == "gzip", (name, zipped.headers)
            assert zipped.content == body  # httpx undoes the gzip
            assert zipped.headers[web.SIZE_HEADER] == str(len(body))
            plain = client.get(path, headers={"accept-encoding": "identity"})
            assert plain.status_code == 200 and "content-encoding" not in plain.headers and plain.content == body
            assert plain.headers[web.SIZE_HEADER] == str(len(body)) and plain.headers["content-length"] == str(len(body))
            part = client.get(path, headers={"accept-encoding": "gzip", "range": "bytes=0-99"})
            assert part.status_code == 206 and part.content == body[:100] and "content-encoding" not in part.headers
        # the raw bytes on the wire are gzip's (read without httpx's decoding)
        with client.stream("GET", f"/runs/{RUN}/lines.arrow", headers={"accept-encoding": "gzip"}) as answer:
            raw = b"".join(answer.iter_raw())
        assert gzip.decompress(raw) == stores["lines.arrow"] and len(raw) < len(stores["lines.arrow"]) / 4
        other = client.get(f"/runs/{RUN}/ATTRIBUTION.txt", headers={"accept-encoding": "gzip"})
        assert other.status_code == 200 and "content-encoding" not in other.headers and web.SIZE_HEADER not in other.headers
        missing = client.get("/runs/no-such-run/lines.arrow", headers={"accept-encoding": "gzip"})
        assert missing.status_code == 404 and web.SIZE_HEADER not in missing.headers
