"""tools/device_page.py (docs/3d-view-contract.md, "Wave 4", V4b): a line of the Żabi Koń clip recorded from the
local app with its worker, served again over HTTPS on 127.0.0.1 (offline: local files): the index, the 3D page as
the app gives it, a recorded patch byte for byte with the app's headers, 404 for what was not recorded, GET only;
the certificate's SANs."""

import ipaddress
import json
import os
import socket
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import device_page  # noqa: E402

TIF = os.path.join(REPO, "tests", "data", "zabi_kon_nmt.tif")
OFFLINE = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
           "PYTHONIOENCODING": "utf-8"}


@pytest.fixture(scope="module")
def clip_data(tmp_path_factory):
    """A data folder with a run of the clip (computed once, offline)."""
    import subprocess
    data = tmp_path_factory.mktemp("device")
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", TIF, "--northing", "254608", "--easting", "553966",
         "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
         "--nmpt", "off", "--model", "sag", "--data-dir", str(data)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env={**os.environ, **OFFLINE})
    assert result.returncode == 0, result.stdout + result.stderr
    return str(data)


def test_certificate_names_the_addresses(tmp_path):
    from cryptography import x509
    cert_file, key_file = device_page.certificate(str(tmp_path), ["192.168.1.23", "10.0.0.7"])
    with open(cert_file, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.DNSName) == ["localhost"]
    assert set(sans.get_values_for_type(x509.IPAddress)) == {
        ipaddress.ip_address(a) for a in ("127.0.0.1", "192.168.1.23", "10.0.0.7")}
    assert os.path.isfile(key_file)
    assert all(not ipaddress.ip_address(a).is_loopback for a in device_page.lan_addresses())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_record_and_serve(clip_data, tmp_path, monkeypatch):
    import requests
    import uvicorn
    from fastapi.testclient import TestClient

    import web
    from settings import ViewSettings
    for key, value in OFFLINE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ESRI_API_KEY", raising=False)
    monkeypatch.delenv("FINDALINE_3D_RING", raising=False)

    index = device_page.record(clip_data, lines=1, say=lambda *a: None)
    (entry,) = index["entries"]
    assert set(entry["answers"]) == {"patch-1", "patch-2", "profile"}
    assert all(a["status"] == 200 for a in entry["answers"].values())
    with open(os.path.join(clip_data, "device", "index.json"), encoding="utf-8") as f:
        assert json.load(f) == index
    run, line = entry["run"], entry["line"]

    # The app's own answers, for comparison
    app = web.create_app(clip_data, token="t", view=ViewSettings(ring=False))
    with TestClient(app, base_url=device_page.LOCAL) as client:
        app_page = client.get("/view3d")
        app_patch = client.get(f"/api/patch?run={run}&line={line}&step=2", headers={"X-Findaline-Patch": "1"})
        app_home = client.get("/")
    assert app_patch.status_code == 200

    cert_file, key_file = device_page.certificate(str(tmp_path), [])
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(device_page.make_app(clip_data), host="127.0.0.1", port=port,
                                           log_level="warning", ssl_certfile=cert_file, ssl_keyfile=key_file))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    site = f"https://127.0.0.1:{port}"
    session = requests.Session()
    session.verify = cert_file
    session.trust_env = False  # not through the test's dead proxy
    try:
        home = session.get(site + "/")
        assert home.status_code == 200 and "text/html" in home.headers["content-type"]
        assert home.headers["content-security-policy"] == app_home.headers["content-security-policy"]
        assert "<script" not in home.text and "level=phone" in home.text and "level=full" in home.text

        page = session.get(site + "/view3d?level=phone")
        assert page.status_code == 200 and page.text == app_page.text
        assert page.headers["content-security-policy"] == app_page.headers["content-security-policy"]
        assert page.headers["content-security-policy"] == web.page_csp(ViewSettings(ring=False))["/view3d"]
        assert page.headers["cache-control"] == "no-store"
        for name in ("view3d.js", "view3d.css", "favicon.svg"):
            assert session.get(f"{site}/app/{name}").status_code == 200
        assert session.get(site + "/app/app.js").status_code == 404  # nothing else of the app

        # The recorded patch, its line as the page sends it (encoded), equal to the app's answer
        from urllib.parse import quote
        url = f"{site}/api/patch?run={quote(run)}&line={quote(line, safe='')}&step=2"
        patch = session.get(url, headers={"X-Findaline-Patch": "1"})
        assert patch.status_code == 200 and patch.content == app_patch.content
        for header in ("content-type", "cache-control", *(h.lower() for h in web.SECURITY_HEADERS)):
            assert patch.headers[header] == app_patch.headers[header], header
        profile = session.get(f"{site}/api/profile?run={quote(run)}&line={quote(line, safe='')}",
                              headers={"X-Findaline-Profile": "1"})
        assert profile.status_code == 200 and profile.headers["content-type"] == "application/json"
        assert "d" in profile.json()

        # Not recorded: another line, another step, another run; GET only
        other = ",".join(str(float(v) + 0.001) for v in line.split(","))
        assert session.get(f"{site}/api/patch?run={run}&line={other}&step=2",
                           headers={"X-Findaline-Patch": "1"}).status_code == 404
        assert session.get(f"{site}/api/patch?run={run}&line={line}&step=3",
                           headers={"X-Findaline-Patch": "1"}).status_code == 404
        assert session.get(f"{site}/api/patch?run=other&line={line}&step=1",
                           headers={"X-Findaline-Patch": "1"}).status_code == 404
        assert session.get(f"{site}/api/estimate").status_code == 404
        assert session.get(f"{site}/runs/{run}/data.js").status_code == 404
        assert session.get(f"{site}/cache/../device/index.json").status_code == 404
        posted = session.post(url, headers={"X-Findaline-Patch": "1"})
        assert posted.status_code in (404, 405)
        assert posted.headers["x-content-type-options"] == "nosniff"
    finally:
        server.should_exit = True
