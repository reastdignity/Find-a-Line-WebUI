"""The site on a phone's home screen ("Add to home screen", line volume round 7's extra B8; the user's answers to the
mock-up's points 18 to 23, 2026-11-24): every page's head names the manifest, the iPhone's icon and the page's
ground (runs.HOME_SCREEN_HEAD); the manifest (viewer/build.mjs: "Find-a-Line", standalone, from "/", the
light ground of viewer/src/ui/tokens.css) and the icons (tools/home_screen_icons.py: the logo's mark on white) are
served to anyone under the pages' own Content-Security-Policy; Chromium finds the page installable on both phones of
the tests. What only a real phone shows (the name under the icon, the status bar, signing in inside the installed
app) is the user's check on the iPhone.
"""

import json
import os
import re
import shutil
import socket
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import home_screen_icons as icons  # noqa: E402
import runs as rn  # noqa: E402
import web  # noqa: E402
from test_public import (LOCAL, TOKEN, account_settings, providers, public, session_of,  # noqa: E402,F401
                         settings)

TOKENS = os.path.join(REPO, "viewer", "src", "ui", "tokens.css")
DIST_MANIFEST = os.path.join(web.APP_DIST, "manifest.webmanifest")
TEMPLATES = ("APP_HTML", "COVERAGE_HTML", "VIEW3D_HTML", "SIGNIN_HTML", "PAGE_HTML")  # web.py's five heads
# The lines as the user's answers give them (points 18 to 23): the manifest, the iPhone's icon, the page's ground
HEAD = ('<link rel="manifest" href="/app/manifest.webmanifest">\n'
        '<link rel="apple-touch-icon" href="/app/apple-touch-icon.png">\n'
        '<meta name="theme-color" content="#f2f5f5" media="(prefers-color-scheme: light)">\n'
        '<meta name="theme-color" content="#121a1b" media="(prefers-color-scheme: dark)">')
ICON_FILES = {"icon-192.png": 192, "icon-512.png": 512, "icon-maskable-512.png": 512, "apple-touch-icon.png": 180}
SHARE = "home-screen-share-" + "x" * 30
RUN = "2026-11-24_100000_Home_0123456789abcdef"
WHITE = (255, 255, 255)


def _tokens() -> tuple:
    """(the light theme's tokens, each dark block's tokens) of tokens.css."""
    with open(TOKENS, encoding="utf-8") as f:
        text = f.read()
    dark = [dict(re.findall(r"(--[\w-]+):\s*([^;]+?)\s*;", block))
            for block in re.findall(r'\.ui(?::not\(\[data-theme="light"\]\)|\[data-theme="dark"\]) \{(.*?)\}', text,
                                    re.S)]
    return icons.light_tokens(text), dark


def _manifest_expected() -> dict:
    ground = _tokens()[0]["--bg"]
    return {"name": "Find-a-Line", "short_name": "Find-a-Line", "start_url": "/", "display": "standalone",
            "background_color": ground, "theme_color": ground,
            "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                      {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
                       "purpose": "maskable"}]}


def _head(page: str) -> str:
    return page.split("<head>", 1)[1].split("</head>", 1)[0]


def test_every_head_names_the_manifest_the_icon_and_the_ground():
    """The five heads of web.py and the map page's template carry the same lines once, inside the head; the ground's
    two colours are tokens.css's --bg (light, and each of its dark blocks); no page asks to be drawn under a
    see-through status bar (no viewport-fit=cover, no black-translucent): the bar stays a strip of its own."""
    light, dark = _tokens()
    assert (rn.GROUND_LIGHT, rn.GROUND_DARK) == (light["--bg"], dark[0]["--bg"])
    assert len(dark) == 2 and dark[0]["--bg"] == dark[1]["--bg"]
    assert rn.HOME_SCREEN_HEAD == HEAD
    for name, template in [(name, getattr(web, name)) for name in TEMPLATES] + [("MAP_HTML", rn.MAP_HTML)]:
        assert template.count(HEAD) == 1 and HEAD in _head(template), name
        assert "viewport-fit" not in template and "apple-mobile-web-app" not in template, name
    page = rn.map_page({"id": RUN, "name": "A run"})
    assert HEAD in _head(page) and page.count("theme-color") == 2


def test_heads_as_served(public, tmp_path):
    """Every page as the two servers send it holds the lines: the app, the coverage map and the 3D view locally;
    the sign-in, privacy, about and coverage pages to a visitor of the public site."""
    (tmp_path / "local").mkdir()
    with TestClient(web.create_app(str(tmp_path / "local"), token=TOKEN, start_scheduler=False),
                    base_url=LOCAL) as local:
        for path in ("/", "/coverage", "/view3d"):
            answer = local.get(path)
            assert answer.status_code == 200 and HEAD in _head(answer.text), path
    for path in ("/", "/privacy", "/about", "/coverage"):
        answer = public.get(path)
        assert answer.status_code == 200 and HEAD in _head(answer.text), path


def test_manifest_as_built():
    """viewer/build.mjs writes the manifest (its one colour the light ground, read from tokens.css) and copies the
    four icons into dist as they are (viewer/dist is compared with a fresh build: test_viewer.py). No orientation:
    the installed app turns sideways as a browser tab does (the user's "Drop the lock" of 2026-11-26)."""
    with open(DIST_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    assert "orientation" not in manifest
    assert manifest == _manifest_expected()
    for name in ICON_FILES:
        with open(os.path.join(web.APP_DIST, name), "rb") as a, open(os.path.join(icons.FOLDER, name), "rb") as b:
            assert a.read() == b.read(), name


def _served(client):
    """The manifest and the icons as `client` gets them: each 200 with its type, the pages' security headers, no
    cookie set; the icons PNG of their sizes."""
    import io
    answer = client.get("/app/manifest.webmanifest")
    assert answer.status_code == 200 and answer.headers["content-type"] == "application/manifest+json"
    assert answer.json() == _manifest_expected()
    for name, size in ICON_FILES.items():
        icon = client.get(f"/app/{name}")
        assert icon.status_code == 200 and icon.headers["content-type"] == "image/png", name
        assert Image.open(io.BytesIO(icon.content)).size == (size, size), name
        for response in (answer, icon):
            assert response.headers["content-security-policy"] == web.SECURITY_HEADERS["Content-Security-Policy"]
            assert "set-cookie" not in response.headers


def test_manifest_and_icons_to_anyone(public, tmp_path):
    """A visitor of the public site (no session) and the local app get the manifest and the icons from /app/
    (APP_DIST, already open to anyone: no new route); the CSP covers the manifest by its default-src 'self'
    (no manifest-src of its own) and loosens nothing."""
    _served(public)
    (tmp_path / "local").mkdir()
    with TestClient(web.create_app(str(tmp_path / "local"), token=TOKEN, start_scheduler=False),
                    base_url=LOCAL) as local:
        _served(local)
    csp = web.SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'self';" in csp and "manifest-src" not in csp
    assert web.CSP_DIRECTIVES == {
        "default-src": ("'self'",), "script-src": ("'self'",), "style-src": ("'self'",),
        "img-src": ("'self'", "data:", "https:"), "connect-src": ("'self'",), "base-uri": ("'none'",),
        "form-action": ("'self'",), "frame-ancestors": ("'none'",)}
    assert "/app" in web.PUBLIC_ROUTES


def test_icons_are_the_marks_drawing():
    """The four files: PNG of their size without transparency (an iPhone draws it black), on white to the edges,
    the mark in the light theme's ink and magenta (tokens.css through ui.css); "any" icons within the mark's square
    of SHARE, the maskable one's drawing inside the middle 80 % every mask keeps."""
    light = icons.light_tokens(open(TOKENS, encoding="utf-8").read())
    colours = {tuple(int(light[t][i:i + 2], 16) for i in (1, 3, 5)) for t in ("--ink", "--clear")}
    for name, size in ICON_FILES.items():
        picture = Image.open(os.path.join(icons.FOLDER, name))
        assert picture.format == "PNG" and picture.mode == "RGB" and picture.size == (size, size), name
        assert icons.ICONS[name][0] == size
        pixels = picture.load()
        for x, y in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
            assert pixels[x, y] == WHITE, name
        found = {colour for _, colour in picture.getcolors(size * size)}
        assert colours <= found, name
        drawn = [(x, y) for y in range(size) for x in range(size) if pixels[x, y] != WHITE]
        if name == "icon-maskable-512.png":
            far = max(((x + 0.5 - size / 2) ** 2 + (y + 0.5 - size / 2) ** 2) ** 0.5 for x, y in drawn)
            assert far <= icons.SAFE_RADIUS * size, (name, far)
        else:
            edge = (1 - icons.SHARE) / 2 * size
            assert min(min(x, y) for x, y in drawn) >= int(edge) and max(max(x, y) for x, y in drawn) < size - int(edge)


# Playwright's words when the browser it launches is not installed (`playwright install chromium` not run, as on CI:
# "Executable doesn't exist at <path>")
NOT_INSTALLED = "executable doesn't exist"


def _launched(start):
    """`start()` (a browser or a context launched): skipped only where Playwright's browser is not installed; any
    other failure to start fails the test."""
    try:
        return start()
    except Exception as e:
        if NOT_INSTALLED in str(e).lower():
            pytest.skip(f"Playwright's browser is not installed: {str(e).splitlines()[0]}")
        raise


def _chromium(p):
    return _launched(lambda: p.chromium.launch())


def _phone(p, profile, folder, phone: str):
    """A context of Playwright's full Chromium (channel "chromium": the default headless shell answers no
    installability error even for a page without a manifest) with its own profile (an off-the-record context answers
    "in-incognito"), as the phone `phone` of Playwright's device profiles."""
    options = {k: v for k, v in p.devices[phone].items() if k != "default_browser_type"}
    return _launched(lambda: p.chromium.launch_persistent_context(str(folder / profile), channel="chromium",
                                                                  **options))


def test_icons_match_a_fresh_drawing():
    """The committed files are the mark's drawing of today (mark.svg, ui.css, tokens.css): drawn again, no pixel
    differs by more than a shade of anti-aliasing (another Chromium may smooth an edge otherwise)."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _chromium(p).close()
    drawn = icons.draw()
    for name, size in ICON_FILES.items():
        kept = Image.open(os.path.join(icons.FOLDER, name)).convert("RGB")
        fresh = drawn[name]
        assert fresh.size == kept.size == (size, size), name
        a, b = kept.load(), fresh.load()
        apart = [max(abs(u - v) for u, v in zip(a[x, y], b[x, y])) for y in range(size) for x in range(size)]
        assert sum(d > 48 for d in apart) <= size * size // 1000, (name, sum(d > 48 for d in apart))
        assert sum(apart) / len(apart) < 0.5, (name, sum(apart) / len(apart))


@pytest.fixture
def servers(tmp_path, account_settings):
    """The local app and the public site on real servers (uvicorn in threads), each with a run's map.html (the
    public site's behind a share link): {"local": address, "public": address}."""
    import uvicorn

    import accounts as ac
    from jobs import Jobs
    from settings import PublicSettings

    found, threads = {}, []
    for kind in ("local", "public"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        data = tmp_path / kind
        folder = data / "runs" / RUN
        folder.mkdir(parents=True)
        (folder / "map.html").write_text(rn.map_page({"id": RUN, "name": "A run"}), "utf-8")  # no run.json: unlisted
        if kind == "local":
            shutil.copytree(web.APP_DIST, data / "runs" / rn.VIEWER_FOLDER)  # mapping.install_viewer's copy
            # the control's page: a map without the lines (the local runs folder is served as it is)
            (folder / "plain.html").write_text(rn.map_page({"id": RUN, "name": "A run"}).replace(HEAD + "\n", ""),
                                               "utf-8")
            app = web.create_app(str(data), token=TOKEN, port=port, start_scheduler=False)
            site = f"http://127.0.0.1:{port}"
        else:
            site = f"http://localhost:{port}"
            user_id, _, _ = session_of(data, account_settings, "a")
            jobs = Jobs(str(data))
            jobs.add_run(RUN, user_id, 1)
            jobs.set_share(RUN, ac.digest(SHARE))
            app = web.create_app(str(data), public=PublicSettings(public_url=site, trusted_proxy="127.0.0.1",
                                                                  contact="admin@example.org"),
                                 accounts=account_settings)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        threads.append((server, thread))
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        found[kind] = site
    try:
        yield found
    finally:
        for server, thread in threads:
            server.should_exit = True
        for server, thread in threads:
            thread.join(10)


# Every CSP violation of the page (the manifest is fetched by the browser for the page: a block shows here)
VIOLATIONS = ("window.__violations = [];"
              "document.addEventListener('securitypolicyviolation',"
              " (e) => window.__violations.push(e.violatedDirective + ' ' + e.blockedURI));")
PHONES = ("Pixel 7", "iPhone 13")  # tools/ui_shots.py's two phones, both in Chromium here (the DevTools protocol)


def _installable(context, url: str) -> dict:
    """What Chromium says of the page at `url`: its manifest (address, errors, text), the installability errors,
    the page's CSP violations and errors, and the iPhone's icons its head names (their addresses as resolved)."""
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_load_state("load")
    cdp = context.new_cdp_session(page)
    manifest = cdp.send("Page.getAppManifest")
    installability = cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
    cdp.detach()
    page.evaluate("new Promise((done) => requestAnimationFrame(() => setTimeout(done)))")  # queued events fired
    found = {"manifest": manifest, "installability": installability,
             "violations": page.evaluate("window.__violations"), "errors": errors,
             "touch": page.eval_on_selector_all('link[rel="apple-touch-icon"]', "links => links.map((l) => l.href)")}
    page.close()
    return found


def _icons(context, manifest: dict, touch: list) -> dict:
    """The manifest's icons (their addresses resolved against the manifest's) and the iPhone's as the browser gets
    them: {address: (status, media type, size in px)}."""
    import io
    from urllib.parse import urljoin
    got = {}
    for address in [urljoin(manifest["url"], icon["src"]) for icon in json.loads(manifest["data"])["icons"]] + touch:
        answer = context.request.get(address)
        got[address] = (answer.status, answer.headers.get("content-type"),
                        Image.open(io.BytesIO(answer.body())).size if answer.ok else None)
    return got


def test_installable_in_chromium(servers, tmp_path, monkeypatch):
    """On both phones of the tests every page names the manifest, which Chromium reads without an error or a
    warning and finds installable (an icon of at least 144 px fetched, standalone, a start in scope), fetched with no
    CSP violation; every icon the manifest and the head name answers 200 with a PNG of its size, as the browser asks
    for it: the local app, its coverage map, 3D view and a run's map.html; the public site's sign-in, privacy, about
    and coverage pages and a share link's map.html, all without a session. The controls, on each phone: a page
    without the lines is not installable ("no-manifest"); a CSP that refuses the manifest is a violation and makes
    the page not installable."""
    pytest.importorskip("playwright")
    from urllib.parse import urljoin

    from playwright.sync_api import sync_playwright
    pages = {"local": ("/", "/coverage", "/view3d", f"/runs/{RUN}/map.html"),
             "public": ("/", "/privacy", "/about", "/coverage", f"/s/{SHARE}/map.html")}
    with sync_playwright() as p:
        for phone in PHONES:
            context = _phone(p, "profile-" + phone.split()[0], tmp_path, phone)
            try:
                context.add_init_script(VIOLATIONS)
                for kind, paths in pages.items():
                    for path in paths:
                        url = servers[kind] + path
                        found = _installable(context, url)
                        manifest = found["manifest"]
                        assert manifest["url"] == servers[kind] + "/app/manifest.webmanifest", (phone, url)
                        assert manifest["errors"] == [] and json.loads(manifest["data"]) == _manifest_expected(), \
                            (phone, url, manifest["errors"])
                        assert found["installability"] == [], (phone, url, found["installability"])
                        assert found["violations"] == [] and found["errors"] == [], (phone, url, found)
                        expected = {urljoin(manifest["url"], icon["src"]):
                                    (200, "image/png", tuple(int(v) for v in icon["sizes"].split("x")))
                                    for icon in _manifest_expected()["icons"]}
                        expected[servers[kind] + "/app/apple-touch-icon.png"] = (200, "image/png", (180, 180))
                        assert _icons(context, manifest, found["touch"]) == expected, (phone, url)
                plain = _installable(context, servers["local"] + f"/runs/{RUN}/plain.html")
                assert [e["errorId"] for e in plain["installability"]] == ["no-manifest"], (phone, plain)
                with monkeypatch.context() as patched:
                    patched.setitem(web.SECURITY_HEADERS, "Content-Security-Policy",
                                    web.SECURITY_HEADERS["Content-Security-Policy"] + "; manifest-src 'none'")
                    refused = _installable(context, servers["local"] + "/coverage")
                assert any(v.startswith("manifest-src") for v in refused["violations"]), (phone, refused)
                assert "manifest-parsing-or-network-error" in [e["errorId"] for e in refused["installability"]], \
                    (phone, refused)
            finally:
                context.close()


def test_map_page_from_disk(tmp_path):
    """A map.html opened from disk (file://): its links name /app/ of a server, which a file has not. The page
    loads as before (the disk notice shown, no page error) and asks for nothing of /app/; only a request for the
    manifest (here the DevTools protocol's; a browser's own install check does not run on a file) tries
    file:///<drive>/app/manifest.webmanifest, which Chromium refuses to a file's page (origin null): no manifest."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    folder = tmp_path / "runs" / RUN
    folder.mkdir(parents=True)
    shutil.copytree(web.APP_DIST, tmp_path / "runs" / rn.VIEWER_FOLDER)
    page_path = folder / "map.html"
    page_path.write_text(rn.map_page({"id": RUN, "name": "A run"}), "utf-8")
    with sync_playwright() as p:
        browser = _chromium(p)
        try:
            context = browser.new_context(**{k: v for k, v in p.devices["Pixel 7"].items()
                                             if k != "default_browser_type"})
            page = context.new_page()
            errors, asked = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: asked.append(request.url))
            page.goto(page_path.as_uri())
            page.wait_for_selector(f"#{rn.DISK_NOTICE}", state="visible")
            page.evaluate("new Promise((done) => requestAnimationFrame(() => setTimeout(done)))")
            loaded = list(asked)
            links = page.eval_on_selector_all('link[rel="manifest"], link[rel="apple-touch-icon"]',
                                              "links => links.map((l) => l.href)")
            cdp = context.new_cdp_session(page)
            manifest = cdp.send("Page.getAppManifest")
            cdp.detach()
            page.evaluate("new Promise((done) => requestAnimationFrame(() => setTimeout(done)))")
            context.close()
        finally:
            browser.close()
    assert errors == []
    assert len(links) == 2 and all(link.startswith("file:///") for link in links), links
    assert [link.rsplit("/app/", 1)[1] for link in links] == ["manifest.webmanifest", "apple-touch-icon.png"], links
    assert not any("/app/" in url for url in loaded), loaded
    assert [url for url in asked if "/app/" in url] == links[:1], asked  # only the manifest, once asked for
    assert not manifest.get("data") and not manifest.get("url"), manifest
