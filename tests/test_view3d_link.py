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
from test_viewer import VIEWER, run_ts  # noqa: E402

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
