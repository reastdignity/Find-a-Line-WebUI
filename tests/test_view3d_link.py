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
// a shorter 429 after a longer one (a user's quick_waiting after the hour's rate) keeps the later deadline
m.noteRefusal("patch", 429, "3600", "the hour", b);
m.noteRefusal("patch", 429, "5", "five seconds", b);
now += 6000;
const longKept = b.blocked("patch");
m.noteRefusal("patch", 429, "7200", "two hours", b);   // a later deadline takes over, with its text
now += 3600000;
out.later = [longKept, b.blocked("patch")];
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
    assert found["later"] == ["the hour", "two hours"], found["later"]


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


# The server's words of a link's 429 per kind of request (contract.md); the canopy is a patch
REFUSALS = {"reach": ("rate_link_reach", REACH_TEXT),
            "profile": ("rate_link_profile", "Too many profiles on this link in a short time. Try again later."),
            "patch": ("rate_link_patch", "Too many 3D views on this link in a short time. Try again later."),
            "canopy": ("rate_link_patch", "Too many 3D views on this link in a short time. Try again later.")}


def _kind(url: str) -> str:
    """The kind of an /api request: reach, canopy, patch or profile."""
    return "canopy" if "part=canopy" in url else url.split("/api/")[1].split("?")[0]


def _link_context(browser, port: int, asked: list, refuse: dict | None = None, refused: dict | None = None):
    """A context without cookies in which /s/<TOKEN>/view3d is the link's 3D page and everything else the local app's
    (its /api answers the clip's run; the local app answers a request with X-Findaline-Share 404, so the header is
    taken off on the way: the link's server side is test_public's and test_share_link_end_to_end's); `asked` gets
    every /api request as the page sent it, [path and query, its X-Findaline-Share or None, the time]; while
    `refuse[kind]` (REFUSALS' kinds) holds a count, such a request is answered 429 with Retry-After: 2 and the server's
    words, and `refused[kind]` gets the time the browser had each such answer (its response event: the page's wait
    counts from the answer)."""
    import time
    from test_web import CSP_STUB
    page_html, csp = _link_page()
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    ctx.add_init_script(CSP_STUB + CLIPBOARD)
    ctx.route(f"http://127.0.0.1:{port}/s/{TOKEN}/view3d*", lambda route: route.fulfill(
        status=200, body=page_html, headers={"content-type": "text/html; charset=utf-8", "content-security-policy": csp,
                                             "cache-control": "no-store"}))

    def api(route):
        kind = _kind(route.request.url)
        if refuse and refuse.get(kind, 0) > 0:
            refuse[kind] -= 1
            code, text = REFUSALS[kind]
            route.fulfill(status=429, headers={"content-type": "application/json", "retry-after": "2"},
                          body=json.dumps({"detail": {"code": code, "params": {}, "message": text}}))
        else:
            route.continue_(headers={k: v for k, v in route.request.headers.items() if k.lower() != "x-findaline-share"})
    ctx.route(f"http://127.0.0.1:{port}/api/**", api)

    def seen(request):
        from urllib.parse import urlsplit
        parts = urlsplit(request.url)
        if parts.path.startswith("/api/"):
            asked.append([parts.path + "?" + parts.query, request.headers.get("x-findaline-share"), time.monotonic()])
    ctx.on("request", seen)
    if refused is not None:
        ctx.on("response", lambda r: refused.setdefault(_kind(r.url), []).append(time.monotonic())
               if r.status == 429 and "/api/" in r.url else None)
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


def _waited(refused_at: float, page):
    """Until the server's Retry-After (2 s) has passed since the browser had the 429 (the time is the subject)."""
    import time
    while time.monotonic() - refused_at < 2.3:
        page.evaluate(FRAMES)


def _drag(page, k: int = 1, dx: float = 25, dy: float = 10) -> str:
    """Anchor k's handle dragged by (dx, dy) after the page settled; the edit's state once the profile answered."""
    from test_web import WAIT
    page.evaluate(FRAMES)
    box = page.evaluate("(k) => { const r = document.querySelectorAll('.v3-handle')[k].getBoundingClientRect();"
                        " return [r.left + r.width / 2, r.top + r.height / 2]; }", k)
    page.evaluate("() => { document.getElementById('view3d').dataset.edit = ''; }")
    page.mouse.move(box[0], box[1])
    page.mouse.down()
    page.mouse.move(box[0] + dx, box[1] + dy, steps=6)
    page.mouse.up()
    page.wait_for_function("() => ['checked', 'error'].includes(document.getElementById('view3d').dataset.edit)",
                           timeout=WAIT * 2)
    return page.evaluate("() => document.getElementById('view3d').dataset.edit")


# The readout's failure (line.ts: the profile's own, not saving's)
READ_FAILED = "() => document.querySelector('.v3-readout .v3-failed:not(.v3-save-failed):not(.v3-hidden)')?.textContent ?? null"


@pytest.fixture
def link_page(clip_data, monkeypatch):
    """A factory of the link's 3D page over the local app (as test_link_view3d_page, the run with its surface model:
    the trees' tool): page(refuse, level, ready) -> (page, asked, refused); the server, the browser and run.json's
    text end with the test."""
    from contextlib import ExitStack
    from urllib.parse import quote
    from playwright.sync_api import sync_playwright
    from test_patch import _offline_env
    from test_view3d_others import _key_of
    from test_web import WAIT, _lines_of, _server
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    run_json, saved = _clip_with_surface(data, meta)
    with ExitStack() as stack:
        stack.callback(run_json.write_text, saved, encoding="utf-8")
        port = stack.enter_context(_server(data, start_scheduler=True))
        p = stack.enter_context(sync_playwright())
        browser = p.chromium.launch(channel="msedge", headless=True)
        stack.callback(browser.close)

        def open_page(refuse: dict, level: str = "full", ready: bool = True):
            asked, refused = [], {}
            page = _link_context(browser, port, asked, refuse, refused)
            page.goto(f"http://127.0.0.1:{port}/s/{TOKEN}/view3d?level={level}#run={quote(meta['id'], safe='')}"
                      f"&line={quote(keys[0], safe='')}")
            if ready:
                page.wait_for_function(READY, timeout=WAIT * 4)
            return page, asked, refused
        yield open_page


@edge
def test_link_view3d_waits_after_a_429(link_page):
    """A reach answered 429 with Retry-After: 2 (a link's rate): the server's text in the tool's note, no reach asked
    for 2 s from the answer however often the tool is switched (the other anchor's ask included), then asked again
    and shown."""
    import time
    from test_web import WAIT
    page, asked, refused = link_page({"reach": 1})
    reaches = lambda: [a for a in asked if a[0].startswith("/api/reach")]  # noqa: E731
    failed = "() => document.querySelector('.v3-reach-failed:not(.v3-hidden)')?.textContent ?? null"
    page.click('.v3-tool[data-tool="valid"]')
    page.wait_for_function(f"() => ({failed})() !== null", timeout=WAIT * 4)
    assert REACH_TEXT in page.evaluate(failed) and len(reaches()) == 1, (page.evaluate(failed), reaches())
    answered = refused["reach"][0]
    page.click('.v3-tool[data-tool="valid"]')  # off
    page.click('.v3-tool[data-tool="valid"]')  # on: both anchors wanted, none asked
    page.wait_for_function(f"() => ({failed})() !== null", timeout=WAIT)
    assert REACH_TEXT in page.evaluate(failed) and len(reaches()) == 1 and time.monotonic() - answered < 2, reaches()
    _waited(answered, page)
    page.click('.v3-tool[data-tool="valid"]')
    page.click('.v3-tool[data-tool="valid"]')
    page.wait_for_function("() => document.getElementById('view3d').dataset.reach === '1'", timeout=WAIT * 4)
    assert len(reaches()) >= 2 and all(a[1] == TOKEN for a in asked), asked
    assert page.evaluate(failed) is None and page.errors == []


@edge
def test_link_view3d_profile_waits_after_a_429(link_page):
    """The found line's profile answered 429: its reason over the readout (main.ts passes the text to edit.found, as a
    moved line's failure shows), the page ready; a drag within 2 s of the answer asks nothing and shows the text; after
    them a drag asks and is checked; a 429 during a drag shows the text and the next drag in the wait asks nothing."""
    import time
    page, asked, refused = link_page({"profile": 1})
    text = REFUSALS["profile"][1]
    profiles = lambda: [a for a in asked if a[0].startswith("/api/profile")]  # noqa: E731
    assert text in (page.evaluate(READ_FAILED) or ""), page.evaluate(READ_FAILED)
    assert page.evaluate("() => document.getElementById('view3d').dataset.profileError") == text
    answered = refused["profile"][0]
    assert _drag(page) == "error" and len(profiles()) == 1 and time.monotonic() - answered < 2, profiles()
    assert text in page.evaluate(READ_FAILED)
    _waited(answered, page)
    assert _drag(page, dx=-20) == "checked" and len(profiles()) == 2, profiles()
    assert page.evaluate(READ_FAILED) is None
    # a 429 during a drag
    refuse_again = {"profile": 1}
    page.context.unroute("**/api/**")
    page.context.route("**/api/**", lambda route: (
        route.fulfill(status=429, headers={"content-type": "application/json", "retry-after": "2"},
                      body=json.dumps({"detail": {"code": "rate_link_profile", "params": {}, "message": text}}))
        if _kind(route.request.url) == "profile" and refuse_again.pop("profile", 0)
        else route.continue_(headers={k: v for k, v in route.request.headers.items() if k.lower() != "x-findaline-share"})))
    assert _drag(page, dx=15) == "error" and len(profiles()) == 3 and text in page.evaluate(READ_FAILED), profiles()
    answered = refused["profile"][1]
    assert _drag(page, dx=-15) == "error" and len(profiles()) == 3 and time.monotonic() - answered < 2, profiles()
    assert all(a[1] == TOKEN for a in asked) and page.errors == []


@edge
def test_link_view3d_patch_and_canopy_wait_after_a_429(link_page):
    """The patch answered 429: the server's text in the page's status. The canopy (a patch's kind) answered 429: the
    text in the trees' note; the tool switched on again within 2 s of the answer asks nothing and shows it again; after
    them it asks and draws the trees."""
    import time
    from test_web import WAIT
    page, asked, refused = link_page({"patch": 1}, ready=False)
    page.wait_for_function("() => !!document.querySelector('.v3-status.v3-error')", timeout=WAIT * 2)
    assert REFUSALS["patch"][1] in page.evaluate("() => document.querySelector('.v3-status').textContent")
    assert [a[1] for a in asked] == [TOKEN] and page.errors == []
    page.context.close()
    page, asked, refused = link_page({"canopy": 1})
    note = "() => { const n = [...document.querySelectorAll('.v3-note.v3-alert')].find((e) => !e.classList.contains('v3-hidden') && /3D views/.test(e.textContent)); return n ? n.textContent : null; }"
    canopies = lambda: [a for a in asked if "part=canopy" in a[0]]  # noqa: E731
    page.click('.v3-tool[data-tool="trees"]')
    page.wait_for_function("() => document.getElementById('view3d').dataset.trees === 'failed'", timeout=WAIT * 2)
    assert REFUSALS["canopy"][1] in page.evaluate(note) and len(canopies()) == 1
    answered = refused["canopy"][0]
    page.evaluate("() => { document.getElementById('view3d').dataset.trees = ''; }")
    page.click('.v3-tool[data-tool="trees"]')
    page.wait_for_function("() => document.getElementById('view3d').dataset.trees === 'failed'", timeout=WAIT * 2)
    assert len(canopies()) == 1 and time.monotonic() - answered < 2 and REFUSALS["canopy"][1] in page.evaluate(note)
    _waited(answered, page)
    page.click('.v3-tool[data-tool="trees"]')
    page.wait_for_function("() => ['on', 'failed'].includes(document.getElementById('view3d').dataset.trees)",
                           timeout=WAIT * 4)
    assert page.evaluate("() => document.getElementById('view3d').dataset.trees") == "on" and len(canopies()) == 2
    assert all(a[1] == TOKEN for a in asked) and page.errors == []


# --- end to end: a real share link on the public app with its worker ----------------------------------------------

@pytest.fixture
def link_site(clip_data, tmp_path, monkeypatch):
    """The public app (uvicorn in a thread) with a worker of its quick lane over a copy of the clip's data folder, the
    clip's run owned by user "a"; yields (site, run id, the owner's headers for the API, the Jobs)."""
    import shutil
    import socket
    import threading
    import time

    import uvicorn

    import accounts as ac
    import web
    from jobs import Jobs, Scheduler
    from settings import AccountSettings, PublicSettings
    from test_patch import _offline_env
    from test_public import ACCOUNTS, session_of
    for key, value in {**_offline_env(), **ACCOUNTS}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ESRI_API_KEY", raising=False)
    account_settings = AccountSettings.load()
    source, meta = clip_data
    data = tmp_path / "data"
    shutil.copytree(source, data)
    from test_reach import with_surface  # the run with the clip's surface model: the trees' tool
    (data / "runs" / meta["id"] / "run.json").write_text(json.dumps(with_surface(meta, "mark")), encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"http://localhost:{port}"
    jobs = Jobs(str(data))
    user_id, cookie, csrf = session_of(data, account_settings, "a")
    jobs.add_run(meta["id"], user_id, 1)
    scheduler = Scheduler(jobs, public=True)
    scheduler.start()
    app = web.create_app(str(data), public=PublicSettings(public_url=site, trusted_proxy="127.0.0.1",
                                                          contact="admin@example.org"), accounts=account_settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        owner = {"cookie": f"{ac.SESSION_COOKIE}={cookie}", "x-findaline-token": csrf, "origin": site}
        yield site, meta["id"], owner, jobs
    finally:
        server.should_exit = True
        scheduler.stop()
        thread.join(10)


@edge
def test_share_link_end_to_end(link_site):
    """A link made by its owner (POST /api/runs/<run>/share) opened in a context without cookies: a line outside the
    run (no saved profile) is measured by the server with the link's header; the selected line's "3D view" opens
    /s/<token>/view3d, which draws the patch and the profile, takes a drag of an anchor, shows "Only valid lines" (the
    reach) and the trees (the canopy) from the server, and goes Back to the link's map with the moved line; every /api
    request carries the token in X-Findaline-Share only. Revoked by the owner: the
    map and the 3D page answer 404."""
    import urllib.request
    from urllib.parse import quote, urlsplit
    from playwright.sync_api import sync_playwright
    from test_shell_c_view_map import FLAG
    from test_web import WAIT
    site, run, owner, jobs = link_site
    def owners(method: str) -> dict:  # the owner's request of the run's share link (Share's), its JSON answer
        request = urllib.request.Request(f"{site}/api/runs/{quote(run, safe='')}/share", method=method, headers=owner)
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the offline env's dead proxy left out
        with direct.open(request, timeout=30) as answer:
            return json.loads(answer.read())
    url = owners("POST")["url"]
    token = urlsplit(url).path.split("/")[2]
    asked: list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 820})
            ctx.add_init_script(FLAG)
            ctx.on("request", lambda r: asked.append([urlsplit(r.url).path + "?" + urlsplit(r.url).query,
                                                      r.headers.get("x-findaline-share")])
                   if urlsplit(r.url).path.startswith("/api/") else None)
            page = ctx.new_page()
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
            page.goto(url)
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT * 2)
            assert page.evaluate("() => window.FINDALINE_APP") == {"profiles": True, "favourites": False}
            # a line beside the run's first (its second anchor moved by about 5 m): measured by the server
            first = page.evaluate("() => { const m = window.FINDALINE_VIEW.view.model; return m.lineLink(m.lineAt(0)); }")
            lat1, lon1, lat2, lon2 = (float(v) for v in first.split(","))
            outside = f"{lat1},{lon1},{lat2 + 0.00004},{lon2}"
            page.evaluate("(hash) => { location.hash = hash; }", "#line=" + quote(outside, safe=""))
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured || !!window.FINDALINE_VIEW.view.model.note",
                                   timeout=WAIT * 4)
            assert page.evaluate("() => window.FINDALINE_VIEW.view.model.measuredLink") == outside, \
                page.evaluate("() => window.FINDALINE_VIEW.view.model.note && window.FINDALINE_VIEW.view.model.note.text")
            assert any(a[0].startswith("/api/profile") for a in asked), asked
            # the first line's 3D view, by its button
            page.evaluate("() => { const v = window.FINDALINE_VIEW.view; v.select(v.spotOf(0), 0); }")
            page.wait_for_selector(".r-view3d", timeout=WAIT)
            href = page.evaluate("() => document.querySelector('.r-view3d').href")
            assert urlsplit(href).path == f"/s/{token}/view3d", href
            page.goto(href)
            page.wait_for_function("() => document.getElementById('view3d')?.dataset.ready === '1'", timeout=WAIT * 6)
            assert page.evaluate("() => document.getElementById('view3d').dataset.profileError ?? null") is None
            tools = page.evaluate("() => [...document.querySelectorAll('.v3-tool')].map((b) => b.dataset.tool)")
            assert "save" not in tools and "others" not in tools, tools
            page.evaluate(FRAMES)
            box = page.evaluate("() => { const r = document.querySelectorAll('.v3-handle')[1].getBoundingClientRect();"
                                " return [r.left + r.width / 2, r.top + r.height / 2]; }")
            page.mouse.move(box[0], box[1])
            page.mouse.down()
            page.mouse.move(box[0] + 25, box[1] + 10, steps=6)
            page.mouse.up()
            page.wait_for_function("() => ['checked', 'error'].includes(document.getElementById('view3d').dataset.edit)",
                                   timeout=WAIT * 4)
            assert page.evaluate("() => document.getElementById('view3d').dataset.edit") == "checked"
            # "Only valid lines" and trees through the real link's header
            page.click('.v3-tool[data-tool="valid"]')
            page.wait_for_function("() => document.getElementById('view3d').dataset.reach === '1' || "
                                   "!!document.querySelector('.v3-reach-failed:not(.v3-hidden)')", timeout=WAIT * 6)
            assert page.evaluate("() => document.getElementById('view3d').dataset.reach") == "1"
            page.click('.v3-tool[data-tool="trees"]')
            page.wait_for_function("() => ['on', 'failed'].includes(document.getElementById('view3d').dataset.trees)",
                                   timeout=WAIT * 6)
            assert page.evaluate("() => document.getElementById('view3d').dataset.trees") == "on"
            back = page.evaluate("() => document.querySelector('.v3-back').href")
            assert urlsplit(back).path == f"/s/{token}/map.html" and urlsplit(back).fragment.startswith("line="), back
            page.click(".v3-back")
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT * 2)
            kinds = {a[0].split("?")[0] + ("&part=canopy" if "part=canopy" in a[0] else "") for a in asked}
            assert {"/api/profile", "/api/patch", "/api/patch&part=canopy", "/api/reach"} <= kinds, kinds
            assert all(a[1] == token and token not in a[0] for a in asked), asked
            assert page.errors == []
            # revoked: the map and the 3D page are gone
            assert owners("DELETE") == {"ok": True}
            assert page.goto(url).status == 404
            assert page.goto(href).status == 404
        finally:
            browser.close()
