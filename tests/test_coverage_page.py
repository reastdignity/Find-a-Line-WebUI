"""The coverage map's page (/coverage, web.COVERAGE_HTML; the page itself is viewer/src/coverage/page): open
to everyone in both modes, a shell of its bundle with the site's security headers, linked from the sign-in
and about pages; its texts in both languages of locales/coverage; the app links to it."""
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import web  # noqa: E402

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402
from test_public import (LOCAL, SETTINGS, TOKEN, URL, _public_app, account_settings, providers,  # noqa: E402,F401
                         public, settings)


def _shell_checks(answer):
    assert answer.status_code == 200, answer.text
    page = answer.text
    assert '<div id="coverage"' in page
    assert '<script src="/app/coverage.js"></script>' in page and 'href="/app/coverage.css"' in page
    assert "style=" not in page and "<style" not in page  # the CSP: style-src 'self'
    assert len(re.findall(r"<script", page)) == 1  # no inline script
    for name, value in web.SECURITY_HEADERS.items():
        assert answer.headers[name] == value, name
    assert answer.headers["cache-control"] == "no-cache"
    assert "set-cookie" not in answer.headers  # no cookie: nothing is stored about a visitor


def test_coverage_page_public(public):
    """A visitor (no session) gets the page, with the public site's links; its bundle and outlines are
    there too (/app is public)."""
    answer = public.get("/coverage")
    _shell_checks(answer)
    assert 'data-site="public"' in answer.text
    assert "/coverage" in web.PUBLIC_ROUTES
    for path in ("/app/coverage.js", "/app/coverage.css", "/app/coverage-shapes.json"):
        assert public.get(path).status_code == 200, path
    fonts = [name for name in os.listdir(web.APP_DIST) if name.endswith(".woff2")]
    assert len(fonts) == 6  # Barlow Condensed 500, 600, 700, latin and latin-ext (ui/fonts.css)
    assert public.get(f"/app/{fonts[0]}").headers["content-type"] == "font/woff2"


def test_coverage_page_local(tmp_path):
    """The local app serves it too (no sign-in there), without the public site's links."""
    with TestClient(web.create_app(str(tmp_path), token=TOKEN, start_scheduler=False), base_url=LOCAL) as client:
        answer = client.get("/coverage")
        _shell_checks(answer)
        assert 'data-site="local"' in answer.text


def test_links_to_the_coverage_page(public):
    """The sign-in page and the about page link to it (the about page's footer and its text)."""
    signin = public.get("/").text
    about = public.get("/about").text
    assert 'href="/coverage"' in signin
    assert "href='/coverage'" in about and 'href="/coverage"' in about  # the text and the footer


def test_coverage_texts_and_app_links():
    """Both languages have the same page.* keys; the app's search intro and source field link to /coverage
    with texts of the app's catalogue; the page asks for its texts through ct, never t."""
    with open(os.path.join(REPO, "locales", "coverage", "en.json"), encoding="utf-8") as f:
        en = json.load(f)
    with open(os.path.join(REPO, "locales", "coverage", "pl.json"), encoding="utf-8") as f:
        pl = json.load(f)
    page_en = {k for k in en if k.startswith("page.")}
    assert page_en and page_en == {k for k in pl if k.startswith("page.")}
    src = os.path.join(REPO, "viewer", "src")
    used = set()
    for folder, _, files in os.walk(os.path.join(src, "coverage", "page")):
        for name in files:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                text = f.read()
            assert not re.search(r"\bt\(", text), name
            used |= set(re.findall(r"""(?:ct\(lang, |word\()["'](page\.[^"'`]+)["']""", text))
    assert used and used <= page_en, used - page_en
    for name in ("SearchIntro.tsx", "SearchPanel.tsx"):
        with open(os.path.join(src, "search", name), encoding="utf-8") as f:
            assert 'href="/coverage"' in f.read(), name


# In headless Edge: the flat view, a card, the globe, the Leaflet view, the stars, Polish; then the result
COVERAGE_SCRIPT = """
(function () {
  const out = document.createElement("pre");
  out.id = "result";
  document.body.appendChild(out);
  const seen = {};
  const wait = (ok, then, tries = 150) => ok() ? then() : tries ? setTimeout(() => wait(ok, then, tries - 1), 100)
                                                    : (seen.timeout = true, done());
  const done = () => { out.textContent = JSON.stringify(seen); };
  const radio = (box, n) => document.querySelectorAll(box + " button")[n].click();
  wait(() => document.querySelector(".cov-shape[data-key='pl']"), () => {
    seen.shapes = document.querySelectorAll(".cov-svg .cov-shape").length;
    document.querySelector(".cov-shape[data-key='pl']").dispatchEvent(new MouseEvent("click", {bubbles: true}));
    wait(() => document.querySelector(".cov-card"), () => {
      seen.card = document.querySelector(".cov-card").textContent;
      seen.rows = document.querySelectorAll(".cov-table tbody tr").length;
      radio(".cov-bar .u-seg", 2);
      wait(() => document.querySelector(".cov-canvas"), () => {
        seen.globe = true;
        radio(".cov-bar .u-seg", 1);
        wait(() => document.querySelector(".cov-leaflet .leaflet-interactive"), () => {
          seen.leaflet = document.querySelectorAll(".cov-leaflet path.leaflet-interactive").length;
          radio(".cov-scale", 2);
          radio(".cov-top .u-seg", 1);
          setTimeout(() => {
            seen.title = document.querySelector(".cov-h1").textContent;
            seen.lang = document.documentElement.lang;
            seen.stars = !!document.querySelector(".cov-card .cov-stars");
            done();
          }, 500);
        });
      });
    });
  });
})();
"""
STORAGE_CLEARED = """
try { for (const key of ["view", "scale", "lang"]) localStorage.removeItem("findaline.coverage." + key); } catch (e) {}
"""


def test_coverage_page_in_edge(tmp_path):
    """The page in headless Edge: the outlines load from next to the bundle, a click opens an area's
    card, the globe and the Leaflet view draw, the stars and Polish switch; no CSP violation."""
    import html
    import importlib
    test_web = importlib.import_module("test_web")
    if not os.path.exists(test_web.EDGE):
        pytest.skip("needs Microsoft Edge")
    folder = tmp_path / "runs" / "covtest"
    folder.mkdir(parents=True)
    (folder / "stubs.js").write_text(test_web.CSP_STUB + STORAGE_CLEARED, encoding="utf-8")
    (folder / "test.js").write_text(COVERAGE_SCRIPT, encoding="utf-8")
    (folder / "index.html").write_text(web.COVERAGE_HTML.format(site="local").replace(
        '<script src="/app/coverage.js"></script>',
        '<script src="stubs.js"></script><script src="/app/coverage.js"></script><script src="test.js"></script>'),
        encoding="utf-8")
    dom = test_web._edge_page(tmp_path, "runs/covtest/index.html?lang=en")  # not the browser's language
    assert test_web._violations(dom) == []
    seen = json.loads(html.unescape(re.search(r'<pre id="result">(.*?)</pre>', dom, re.S).group(1)))
    assert "timeout" not in seen, seen
    assert seen["shapes"] > 200 and seen["leaflet"] > 200 and seen["globe"], seen
    assert "Poland" in seen["card"] and "GUGiK" in seen["card"], seen
    assert seen["rows"] == len(json.load(open(os.path.join(REPO, "viewer", "src", "coverage", "coverage.json"),
                                              encoding="utf-8"))["areas"]) + 1  # and the rest of the world
    assert seen["lang"] == "pl" and seen["title"] == "Gdzie Find-a-Line widzi dokładnie" and seen["stars"], seen
