"""Share links get the 3D view and every line's profile (docs/3d-view-contract.md, "Share links (2026-11-26)"):
the pure parts in Node (viewer/src/sharelink.ts: a link page's token, the header of a computed request, the wait after
a 429; view3d/page.ts: the links of the 3D view and to it in link mode; view3d/reach.ts fetchReach with the header and
the wait) and the link's 3D page in Playwright's Edge (link mode by its address /s/<token>/view3d; every computed
request with X-Findaline-Share and no token in an /api address; Back to the link's map with the line; Copy link the
link's own address; no Save, no "Saved lines", no Report; dragging, "Only valid lines" and trees; the wait after a 429).
Run the browser tests from PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import clip_data  # noqa: E402,F401 (a run of the clip, computed once)
from test_viewer import VIEWER, run_ts  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

node = pytest.mark.skipif(not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
                          reason="needs Node and `npm install` in viewer/")

TOKEN = "AbCdEf0123456789-view3dlink_token-xyz_01"  # a share link's token (token_urlsafe's alphabet)


@node
def test_token_header_and_wait(tmp_path):
    """sharelink.ts: the token of a link's page only (/s/<token>/<page>, not /s/runs.js, the app or a run's map), the
    header added to a computed request's own only there; Retry-After read as whole seconds of at least 1, else 60; a
    429 starts a wait of its kind only, which gives its text until it ends; the 2D page's hash of a line."""
    found = run_ts(tmp_path, "sharelink", f"""
const T = {json.dumps(TOKEN)};
const paths = ["/s/" + T + "/map.html", "/s/" + T + "/view3d", "/s/" + T + "/", "/s/runs.js", "/s/_viewer/viewer.js",
               "/view3d", "/runs/x/map.html", "/", "/s/" + T + "/a/b", "/s/bad token/map.html", ""];
const out = {{tokens: paths.map((p) => m.shareToken(p)),
  headers: [m.computedHeaders({{"X-Findaline-Profile": "1"}}, "/s/" + T + "/view3d"), m.computedHeaders({{"X-Findaline-Patch": "1"}}, "/view3d")],
  noLocation: m.shareToken(), name: m.SHARE_HEADER,
  seconds: ["2", " 7 ", "0", "-3", "1.5", "Wed, 21 Oct 2026 07:28:00 GMT", "", null, undefined, "120"].map((v) => m.retrySeconds(v)),
  hash: [m.lineHash("50.1,19.7,50.2,19.8"), m.lineHash(null), m.lineHash("")]}};
let now = 1000;
const b = new m.Backoff(() => now);
m.noteRefusal("profile", 400, "5", "not a rate", b);   // only a 429 starts a wait
const before = b.blocked("profile");
m.noteRefusal("profile", 429, "2", "Too many profiles", b);
const during = [b.blocked("profile"), b.blocked("patch"), b.blocked("reach")];
let thrown = null;
try {{ m.checkBackoff("profile", b); }} catch (e) {{ thrown = e.message; }}
now += 1999;
const late = b.blocked("profile");
now += 1;
const after = [b.blocked("profile"), (() => {{ try {{ m.checkBackoff("profile", b); return "passed"; }} catch (e) {{ return e.message; }} }})()];
m.noteRefusal("reach", 429, null, "Too many reach", b);   // no Retry-After: 60 s
now += 59999;
const reachLate = b.blocked("reach");
now += 1;
out.wait = {{before, during, thrown, late, after, reachLate, reachAfter: b.blocked("reach")}};
console.log(JSON.stringify(out));""")
    assert found["tokens"] == [TOKEN, TOKEN, TOKEN, None, None, None, None, None, None, None, None]
    assert found["headers"] == [{"X-Findaline-Profile": "1", "X-Findaline-Share": TOKEN}, {"X-Findaline-Patch": "1"}]
    assert found["noLocation"] is None and found["name"] == "X-Findaline-Share"
    assert found["seconds"] == [2, 7, 60, 60, 60, 60, 60, 60, 60, 120]
    assert found["hash"] == ["#line=50.1%2C19.7%2C50.2%2C19.8", "", ""]
    wait = found["wait"]
    assert wait["before"] is None and wait["during"] == ["Too many profiles", None, None], wait
    assert wait["thrown"] == "Too many profiles" and wait["late"] == "Too many profiles", wait
    assert wait["after"] == [None, "passed"], wait
    assert wait["reachLate"] == "Too many reach" and wait["reachAfter"] is None, wait


@node
def test_links_of_the_link_mode(tmp_path):
    """page.ts: Back of a link's 3D view goes to the link's map.html with the 2D page's #line= (relative), the app's
    to /#run=…&line=… as before; Copy link takes the page's path (the link's own /s/<token>/view3d); view3dLink gives
    the 2D result's button its base and the hash with the spot's other lines, as ResultPage's view3dOf did."""
    found = run_ts(tmp_path, "view3d/page", f"""
const T = {json.dumps(TOKEN)};
const hash = "#run=" + encodeURIComponent("run 1") + "&line=1.5,2.5,3.5,4.5&also=" + encodeURIComponent("5,6,7,8");
const p = m.parsePage("", hash, false), moved = "50,19.5,50.0002,19.5001";
const lines = {{a: {{k: "1.5,2.5,3.5,4.5"}}, b: {{k: "5,6,7,8"}}, c: {{k: "9,10,11,12"}}}};
const model = (also) => ({{runOf: () => "run 1", lineLink: (l) => l.k, alsoOf: (l, max) => also.slice(0, max)}});
const many = Array.from({{length: 25}}, (_, i) => ({{k: i + ",0,0,0"}}));
console.log(JSON.stringify({{
  back: [m.backUrl(p, p.line, true), m.backUrl(p, moved, true), m.backUrl(p, null, true), m.backUrl(p), m.backUrl(p, moved, false)],
  view: [m.viewUrl(p, moved, "?level=phone", p.also, "/s/" + T + "/view3d"), m.viewUrl(p, moved, "", p.also)],
  button: [m.view3dLink("view3d")(model([]), lines.a), m.view3dLink("/view3d")(model([lines.b, lines.c]), lines.a),
           m.view3dLink("view3d")(model(many), lines.a).split("&also=")[1]],
}}));""")
    assert found["back"] == ["map.html#line=1.5%2C2.5%2C3.5%2C4.5", "map.html#line=50%2C19.5%2C50.0002%2C19.5001", "map.html",
                             "/#run=run%201&line=1.5%2C2.5%2C3.5%2C4.5", "/#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001"]
    assert found["view"] == [f"/s/{TOKEN}/view3d?level=phone#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001&also=5%2C6%2C7%2C8",
                             "/view3d#run=run%201&line=50%2C19.5%2C50.0002%2C19.5001&also=5%2C6%2C7%2C8"]
    assert found["button"][0] == "view3d#run=run%201&line=1.5%2C2.5%2C3.5%2C4.5"
    assert found["button"][1] == "/view3d#run=run%201&line=1.5%2C2.5%2C3.5%2C4.5&also=5%2C6%2C7%2C8%3B9%2C10%2C11%2C12"
    assert len(found["button"][2].split("%3B")) == 20  # OTHERS_MAX


@node
def test_reach_carries_the_token_and_waits(tmp_path):
    """reach.ts fetchReach on a link's page: the token in the header (never in the address it is given); a 429 with
    Retry-After: 2 makes the next asks reject with the server's text without a request until 2 s passed; the app's page
    sends no token."""
    found = run_ts(tmp_path, "view3d/reach", f"""
(async () => {{
  const T = {json.dumps(TOKEN)}, seen = [];
  const answer = (status, detail, retry) => (url, headers) => {{ seen.push([url, headers]);
    return Promise.resolve({{status, body: new TextEncoder().encode(JSON.stringify({{detail}})).buffer,
                            header: (n) => n === "Retry-After" ? retry : null}}); }};
  globalThis.location = {{pathname: "/s/" + T + "/view3d"}};
  let now = 0;
  const {{Backoff}} = require({json.dumps(str(tmp_path / "sharelink.cjs"))});
  const b = new Backoff(() => now), out = {{}};
  const tooMany = {{code: "rate_link_reach", message: "Too many reach calculations on this link in a short time. Try again later."}};
  const ask = async (get) => {{ try {{ await m.fetchReach("/api/reach?run=r", get, b); return "fetched"; }} catch (e) {{ return e.message; }} }};
  out.first = await ask(answer(429, tooMany, "2"));
  out.blocked = await ask(answer(400, "x", null));
  now = 1999;
  out.late = await ask(answer(400, "x", null));
  out.sentDuring = seen.length;
  now = 2000;
  out.again = await ask(answer(400, {{message: "The anchor is outside the patch.", code: "nope", params: {{}}}}, null));
  globalThis.location = {{pathname: "/view3d"}};
  out.app = await ask(answer(400, "y", null));
  out.seen = seen;
  console.log(JSON.stringify(out));
}})();""", bundles={"sharelink": "sharelink"})
    text = "Too many reach calculations on this link in a short time. Try again later."
    assert found["first"] == found["blocked"] == found["late"] == text and found["sentDuring"] == 1, found
    assert found["again"] == "The anchor is outside the patch." and found["app"] == "y", found
    assert [url for url, _ in found["seen"]] == ["/api/reach?run=r"] * 3 and all(TOKEN not in url for url, _ in found["seen"])
    assert [h for _, h in found["seen"]] == [{"X-Findaline-Reach": "1", "X-Findaline-Share": TOKEN}] * 2 + [{"X-Findaline-Reach": "1"}]


# --- the link's 3D page in Playwright's Edge ---------------------------------------------------------------------

READY = "() => document.getElementById('view3d')?.dataset.ready === '1'"
FRAMES = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"
REACH_TEXT = "Too many reach calculations on this link in a short time. Try again later."
# The clipboard's writes, kept (Copy link)
CLIPBOARD = """window.COPIED = [];
Object.defineProperty(navigator, "clipboard", {configurable: true, value: {writeText: (s) => { COPIED.push(s); return Promise.resolve(); }}});
"""


def _link_page() -> tuple:
    """The 3D page as the server gives a link's (/s/<token>/view3d: the user meta {"link": true}, no token, no CSRF;
    the ring off) and the 3D page's Content-Security-Policy."""
    import html

    import web
    from settings import ViewSettings
    page = web.VIEW3D_HTML.format(user=html.escape(json.dumps({"link": True})), keys=web.key_meta(None), ring="off")
    return page, web.page_csp(ViewSettings(ring=False))["/view3d"]


def _link_context(browser, port: int, asked: list, refuse_reach: list | None = None):
    """A context without cookies in which /s/<TOKEN>/view3d is the link's 3D page and everything else the local app's
    (its /api answers the clip's run: the link's server side is the server worker's); `asked` gets every /api request
    as [path and query, its X-Findaline-Share or None, the time]; while `refuse_reach` holds a count, a reach is
    answered 429 with Retry-After: 2 and the server's words."""
    import time
    from test_web import CSP_STUB
    page_html, csp = _link_page()
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    ctx.add_init_script(CSP_STUB + CLIPBOARD)
    ctx.route(f"http://127.0.0.1:{port}/s/{TOKEN}/view3d*", lambda route: route.fulfill(
        status=200, body=page_html, headers={"content-type": "text/html; charset=utf-8", "content-security-policy": csp,
                                             "cache-control": "no-store"}))

    def reach(route):
        if refuse_reach and refuse_reach[0] > 0:
            refuse_reach[0] -= 1
            route.fulfill(status=429, headers={"content-type": "application/json", "retry-after": "2"},
                          body=json.dumps({"detail": {"code": "rate_link_reach", "params": {}, "message": REACH_TEXT}}))
        else:
            route.continue_()
    ctx.route(f"http://127.0.0.1:{port}/api/reach*", reach)

    def seen(request):
        from urllib.parse import urlsplit
        parts = urlsplit(request.url)
        if parts.path.startswith("/api/"):
            asked.append([parts.path + "?" + parts.query, request.headers.get("x-findaline-share"), time.monotonic()])
    ctx.on("request", seen)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    return page


def _clip_with_surface(data, meta):
    """The run with the clip's surface model (the trees' tool) and data credits (the notices' link); run.json's text
    before, to put back."""
    from test_reach import with_surface
    run_json = data / "runs" / meta["id"] / "run.json"
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**with_surface(meta, "mark"), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    return run_json, saved


edge = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright")


@edge
def test_link_view3d_page(clip_data, monkeypatch):
    """The link's 3D page (/s/<token>/view3d, link mode by its address): the patch, the profile, a drag's profile, the
    reach and the canopy all carry X-Findaline-Share: <token>, none has the token in its address; no Save, no "Saved
    lines" (two lines of the address still drawn), no Report; Back is the link's map.html with the line (and the moved
    line after a drag); Copy link the link's own 3D address; the notices are the link's ATTRIBUTION.txt; dragging,
    "Only valid lines" and trees work against the app's routes; no CSP violation."""
    from urllib.parse import quote, unquote, urljoin
    from playwright.sync_api import sync_playwright
    from test_patch import _offline_env
    from test_view3d_others import _key_of
    from test_web import WAIT, _lines_of, _server
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    run_json, saved = _clip_with_surface(data, meta)
    asked: list = []
    try:
        with _server(data, start_scheduler=True) as port, sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            try:
                page = _link_context(browser, port, asked)
                origin = f"http://127.0.0.1:{port}"
                address = (f"{origin}/s/{TOKEN}/view3d?level=full#run={quote(meta['id'], safe='')}&line={quote(keys[0], safe='')}"
                           f"&also={quote(';'.join(keys[1:3]), safe='')}")
                page.goto(address)
                page.wait_for_function(READY, timeout=WAIT * 4)
                page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
                tools = page.evaluate("() => [...document.querySelectorAll('.v3-tool')].map((b) => b.dataset.tool)")
                assert "save" not in tools and "others" not in tools and {"valid", "trees", "profile"} <= set(tools), tools
                assert not page.evaluate("() => [...document.querySelectorAll('button, a')].some((b) => /report/i.test(b.textContent))")
                back = page.evaluate("() => document.querySelector('.v3-back').getAttribute('href')")
                assert back == "map.html#line=" + quote(keys[0], safe="-_.!~*'()"), back
                assert urljoin(page.url, back).split("#")[0] == f"{origin}/s/{TOKEN}/map.html"
                notices = page.evaluate("() => [...document.querySelectorAll('.v3-credits a')].map((a) => a.href)")
                assert f"{origin}/s/{TOKEN}/ATTRIBUTION.txt" in notices and not any("/runs/" in n for n in notices), notices
                page.click(".v3-copy")
                page.wait_for_function("() => window.COPIED.length === 1", timeout=WAIT)
                copied = page.evaluate("() => window.COPIED[0]")
                assert copied.startswith(f"{origin}/s/{TOKEN}/view3d?level=full#run=") and "&also=" in copied, copied
                assert unquote(copied.split("&line=")[1].split("&")[0]) == keys[0], copied
                # a drag of anchor 2: the moved line's profile asked (with the header), Back follows it
                page.evaluate(FRAMES)
                box = page.evaluate("() => { const r = document.querySelectorAll('.v3-handle')[1].getBoundingClientRect();"
                                    " return [r.left + r.width / 2, r.top + r.height / 2]; }")
                profiles = sum(1 for a in asked if a[0].startswith("/api/profile"))
                page.mouse.move(box[0], box[1])
                page.mouse.down()
                page.mouse.move(box[0] + 25, box[1] + 10, steps=6)
                page.mouse.up()
                page.wait_for_function("() => ['checked', 'error'].includes(document.getElementById('view3d').dataset.edit)",
                                       timeout=WAIT * 2)
                assert page.evaluate("() => document.getElementById('view3d').dataset.edit") == "checked"
                assert sum(1 for a in asked if a[0].startswith("/api/profile")) == profiles + 1, asked
                moved = page.evaluate("() => document.querySelector('.v3-back').getAttribute('href')")
                assert moved.startswith("map.html#line=") and moved != back, moved
                # "Only valid lines": the reaches of both anchors from the app's route
                page.click('.v3-tool[data-tool="valid"]')
                page.wait_for_function("() => document.getElementById('view3d').dataset.reach === '1' || "
                                       "!!document.querySelector('.v3-reach-failed:not(.v3-hidden)')", timeout=WAIT * 4)
                assert page.evaluate("() => document.getElementById('view3d').dataset.reach") == "1"
                # trees: the canopy part of the patch
                page.click('.v3-tool[data-tool="trees"]')
                page.wait_for_function("() => ['on', 'failed'].includes(document.getElementById('view3d').dataset.trees)",
                                       timeout=WAIT * 4)
                assert page.evaluate("() => document.getElementById('view3d').dataset.trees") == "on"
                kinds = {a[0].split("?")[0] + ("&part=canopy" if "part=canopy" in a[0] else "") for a in asked}
                assert {"/api/patch", "/api/patch&part=canopy", "/api/profile", "/api/reach"} <= kinds, kinds
                assert all(a[1] == TOKEN and TOKEN not in a[0] for a in asked), asked
                assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
            finally:
                browser.close()
    finally:
        run_json.write_text(saved, encoding="utf-8")


@edge
def test_link_view3d_waits_after_a_429(clip_data, monkeypatch):
    """A reach answered 429 with Retry-After: 2 (a link's rate): the server's text in the tool's note, no reach asked
    for 2 s however often the tool is switched (the other anchor's ask included), then asked again and shown."""
    import time
    from urllib.parse import quote
    from playwright.sync_api import sync_playwright
    from test_patch import _offline_env
    from test_view3d_others import _key_of
    from test_web import WAIT, _lines_of, _server
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    asked: list = []
    refuse = [1]
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _link_context(browser, port, asked, refuse)
            page.goto(f"http://127.0.0.1:{port}/s/{TOKEN}/view3d?level=full#run={quote(meta['id'], safe='')}"
                      f"&line={quote(keys[0], safe='')}")
            page.wait_for_function(READY, timeout=WAIT * 4)
            reaches = lambda: [a for a in asked if a[0].startswith("/api/reach")]  # noqa: E731
            failed = "() => document.querySelector('.v3-reach-failed:not(.v3-hidden)')?.textContent ?? null"
            page.click('.v3-tool[data-tool="valid"]')
            page.wait_for_function(f"() => ({failed})() !== null", timeout=WAIT * 4)
            assert REACH_TEXT in page.evaluate(failed) and len(reaches()) == 1, (page.evaluate(failed), reaches())
            refused = reaches()[0][2]
            page.click('.v3-tool[data-tool="valid"]')  # off
            page.click('.v3-tool[data-tool="valid"]')  # on: both anchors wanted, none asked
            page.wait_for_function(f"() => ({failed})() !== null", timeout=WAIT)
            assert REACH_TEXT in page.evaluate(failed) and len(reaches()) == 1 and time.monotonic() - refused < 2, reaches()
            while time.monotonic() - refused < 2.1:  # the server's Retry-After passing: the time is the test's subject
                page.evaluate(FRAMES)
            page.click('.v3-tool[data-tool="valid"]')
            page.click('.v3-tool[data-tool="valid"]')
            page.wait_for_function("() => document.getElementById('view3d').dataset.reach === '1'", timeout=WAIT * 4)
            assert len(reaches()) >= 2 and all(a[1] == TOKEN for a in asked), asked
            assert page.evaluate(failed) is None and page.errors == []
        finally:
            browser.close()
