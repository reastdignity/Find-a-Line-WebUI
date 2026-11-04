"""
The 3D view of a line on a real phone (docs/3d-view-contract.md, "Wave 4", V4b): the answers of /api/patch
and /api/profile of a few lines recorded from the local app, served again over HTTPS on the LAN with the 3D
page as the app gives it, and the data one open of each line takes. Run by hand:

    python tools/device_page.py record --data-dir <folder> [--run ID ...] [--lines 3] [--spacing 50]
    python tools/device_page.py serve --data-dir <folder> [--port 8443] [--host 0.0.0.0]
    python tools/device_page.py measure --data-dir <folder> [--samples 20]

`record` takes the runs of the data folder (or those named), the first `--lines` lines of each run's data.js
whose middles lie at least `--spacing` metres apart (0: simply the first rows), and asks the local app,
in-process with its worker (as tests/test_patch.py does), for their /api/patch at steps 1 and 2 and their
/api/profile; the answers, with their status, Content-Type and Cache-Control, go to <folder>/device/
(index.json and one file per answer). Missing elevation tiles around a line are downloaded then, as the app
would.

`serve` answers GET only, without accounts, with nothing else of the app: the 3D page exactly as
web.VIEW3D_HTML builds it locally (findaline-3d-ring "off"; the meta of ESRI_API_KEY when that is set, never
written to a file) with the app's headers (web.SECURITY_HEADERS, the 3D page's Content-Security-Policy and
Permissions-Policy (the motion sensors allowed: web.PAGE_PERMISSIONS), Cache-Control no-store), /app/view3d.js, /app/view3d.css and /app/favicon.svg from viewer/dist, the recorded
answers by run, line and step (anything not recorded: 404), the orthophoto tiles of /cache/ read-only from
the data folder (as the app's /cache/ route), and an index page of the recorded lines at "/" (no script, the
app's CSP). Its certificate is self-signed, made at each start for localhost and the PC's LAN IPv4 addresses
(kept in a temporary folder while it runs).

`measure` gives the data of one open of each recorded line at both levels (full: step 1; phone: step 2): the
patch's answer, the profile's, and the imagery of the default kind (the run's orthophoto; none without one,
Shaded and Edges load no tiles): the tiles that viewer/src/view3d/tiles.ts plans for the patch's chunks,
computed by the page's own modules (decode.ts, terrain.ts, tiles.ts bundled by viewer/node_modules' esbuild
and run in Node: `npm ci` in viewer once). A tile our cache holds is measured from its file; a tile the page
asks a service for is estimated from a sample of the service's tiles (at most --samples GETs per host, with
the app's User-Agent and the host's rate turns, sources.net.rate_turn). A WMS over base tiles, drawn as
orthophoto.tile_content composes our cache (tiles.ts Composed), is estimated from a sample of its JPEGs, each
classified by orthophoto._white_blocks: every tile takes the JPEGs' mean, the share found all white the base's
mean too, the share partly white the base's and the transparent PNG's (sampled from those samples' own base
tiles and PNGs, the three together at most --samples GETs per host). Esri's tiles are counted, never
fetched. A chunk is counted when it holds data (terrain.ts chunkTile), so a chunk whose data makes no whole
triangle would be counted too (rare at the patch's edge).

The checklist for an iPhone (iOS 18), printed at the start of `serve`:
CHECKLIST_TEXT
"""

import argparse
import ipaddress
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

DEVICE = "device"          # the folder of the recordings in the data folder
INDEX = "index.json"
LOCAL = "http://127.0.0.1:8765"
STEPS = (1, 2)
LEVELS = {"full": 1, "phone": 2}  # the page's level and the patch's step it asks for (page.ts patchUrl)
KEPT_HEADERS = ("content-type", "cache-control")  # of the recorded answers, served again

CHECKLIST = """\
 1. Phone and PC on the same Wi-Fi. Open one of the URLs above in Safari.
 2. The certificate warning ("This Connection Is Not Private"): Show Details, then "visit this website",
    and confirm. (Made anew at each start: accept it again after a restart of this server.)
 3. On the PC: allow Windows' firewall prompt for Python on PRIVATE networks (if no prompt came and the
    phone cannot connect, the Wi-Fi may be a "public" network in Windows' settings).
 4. Per line of the index, open it with "phone" (the phone's own level) and later "full":
    a. the terrain appears, the line is coloured once the profile is in;
    b. orbit (one finger), zoom (pinch), pan (two fingers): smooth, nothing jumps or disappears;
    c. every imagery kind of the control: the orthophoto, Esri (only with ESRI_API_KEY set at the
       server's start), Shaded, Edges: each draws, the credits change with it;
    d. the walker: drag its slider end to end, then Walk (smooth? the speed control; Stop);
    e. the walker's views, Walker's eyes and Behind the walker (the switch's eye and figure): one finger
       looks around (never upside down); the slider and Walk carry the camera along the line, the sag
       moving it as walking would; Orbit gives back the camera as it was;
    f. the zoom in both walker's views: a pinch and the - / + beside the switch; the indicator shows the
       eyes' factor (x1 is 60 degrees wide) and the distance behind the walker in metres; the slider stays
       wide enough to drag; each view keeps its zoom;
    g. Phone motion (in a walker's view): iOS asks for the motion's permission inside the button's tap;
       allowed, turning the phone turns the gaze, upright and in landscape, a finger's drag adds to it;
       denied, the note "No phone motion: drag to look around." shows. With this server's self-signed
       certificate iOS may refuse the sensors (no question, or the note): write it down, it is not a
       failure of the page;
    h. rotate the phone to landscape and back: the scene and the bar fit again;
    i. leave it open five minutes without a reload (screen on), then orbit again: still drawn, no
       "context lost";
    j. Back to the map: it goes to "/", which this server answers only with this index (no app here).
 5. `?level=full` on the phone too: heavier (full patch, finer textures); does it load and stay smooth?
 6. Dragging an anchor asks /api/profile for a line that was not recorded: an error there is expected.
    The data credits' notices link (ATTRIBUTION.txt) answers 404 here.
 7. Note per line and level: load time, smoothness, anything drawn wrong (a screenshot helps)."""

__doc__ = __doc__.replace("CHECKLIST_TEXT", CHECKLIST)


def say_now(*args):
    """print, flushed (the server's start is read through pipes too)."""
    print(*args, flush=True)


# --- Recording ---------------------------------------------------------------------------------------------

def device_dir(data: str) -> str:
    return os.path.join(data, DEVICE)


def run_ids(data: str) -> List[str]:
    """The runs of a data folder (those with a run.json), sorted."""
    runs = os.path.join(data, "runs")
    if not os.path.isdir(runs):
        return []
    return sorted(d for d in os.listdir(runs) if os.path.isfile(os.path.join(runs, d, "run.json")))


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The distance of two points (an equirectangular approximation: enough for spacing and labels)."""
    k = math.pi / 180 * 6371000
    return math.hypot((lat2 - lat1) * k, (lon2 - lon1) * k * math.cos((lat1 + lat2) / 2 * math.pi / 180))


def run_lines(data: str, run: str, count: int, spacing: float) -> List[Dict]:
    """The first `count` lines of a run's data.js (their anchors as its links name them: keys.lineCoords)
    whose middles lie at least `spacing` metres from the lines taken before."""
    with open(os.path.join(data, "runs", run, "data.js"), encoding="utf-8") as f:
        rows = json.loads(f.read().partition(" = ")[2].rstrip().rstrip(";"))["lines"]
    taken: List[Dict] = []
    for row in rows:
        lat1, lon1, lat2, lon2 = (float(v) for v in row[:4])
        middle = ((lat1 + lat2) / 2, (lon1 + lon2) / 2)
        if any(_metres(*middle, *t["middle"]) < spacing for t in taken):
            continue
        taken.append({"line": ",".join(str(v) for v in row[:4]), "middle": middle,
                      "length_m": round(_metres(lat1, lon1, lat2, lon2), 1)})
        if len(taken) >= count:
            break
    return taken


def line_key(line: str) -> Optional[Tuple[float, ...]]:
    """A line's four numbers rounded to 7 decimals (the page sends them as it got them), None when not four."""
    try:
        numbers = tuple(round(float(v), 7) for v in line.split(","))
    except ValueError:
        return None
    return numbers if len(numbers) == 4 and all(math.isfinite(v) for v in numbers) else None


def _title(data: str, run: str) -> str:
    try:
        with open(os.path.join(data, "runs", run, "run.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return run
    return meta.get("title") or meta.get("name") or meta.get("place") or run


def load_index(data: str) -> Dict:
    try:
        with open(os.path.join(device_dir(data), INDEX), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"entries": []}


def record(data: str, runs: Optional[Sequence[str]] = None, lines: int = 3, spacing: float = 50,
           say=say_now) -> Dict:
    """Record the answers of the lines of `runs` (default: every run of the folder) from the local app with
    its worker (the 3D view's ring off); returns the index written to <data>/device/index.json."""
    from fastapi.testclient import TestClient

    import web
    from settings import ViewSettings

    runs = list(runs) if runs else run_ids(data)
    if not runs:
        raise SystemExit(f"no runs in {os.path.join(data, 'runs')}")
    folder = device_dir(data)
    os.makedirs(folder, exist_ok=True)
    index = load_index(data)
    index["entries"] = [e for e in index["entries"] if e["run"] not in runs]  # these runs again
    app = web.create_app(data, token="device-page-record", view=ViewSettings(ring=False))
    with TestClient(app, base_url=LOCAL) as client:
        for run in runs:
            os.makedirs(os.path.join(folder, run), exist_ok=True)
            for k, picked in enumerate(run_lines(data, run, lines, spacing)):
                line = picked["line"]
                entry = {"run": run, "title": _title(data, run), "line": line, "length_m": picked["length_m"],
                         "answers": {}}
                asks = [(f"patch-{step}", f"/api/patch?run={run}&line={line}&step={step}",
                         {"X-Findaline-Patch": "1"}, "bin") for step in STEPS]
                asks.append(("profile", f"/api/profile?run={run}&line={line}", {"X-Findaline-Profile": "1"}, "json"))
                for name, url, header, ext in asks:
                    started = time.monotonic()
                    answer = client.get(url, headers=header)
                    file = f"{run}/{k}-{name}.{ext}"
                    with open(os.path.join(folder, file), "wb") as f:
                        f.write(answer.content)
                    entry["answers"][name] = {
                        "file": file, "status": answer.status_code,
                        "headers": {h: answer.headers[h] for h in KEPT_HEADERS if h in answer.headers}}
                    say(f"{run} line {k} {name}: {answer.status_code}, {len(answer.content) / 1024:.0f} KB, "
                        f"{time.monotonic() - started:.1f} s")
                index["entries"].append(entry)
    with open(os.path.join(folder, INDEX), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return index


# --- Serving -----------------------------------------------------------------------------------------------

def default_address() -> Optional[str]:
    """The IPv4 address of the PC's default route (most likely its Wi-Fi or LAN), None without one."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # no packet is sent: only the route is chosen
            return sock.getsockname()[0]
    except OSError:
        return None


def lan_addresses() -> List[str]:
    """The PC's IPv4 addresses but loopback and link-local: its host name's, and the one of its default route
    (first; the others sorted, e.g. the virtual adapters of WSL or Hyper-V)."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    first = default_address()
    if first:
        found.add(first)
    keep = [a for a in found if not ipaddress.ip_address(a).is_loopback and not ipaddress.ip_address(a).is_link_local]
    return sorted(keep, key=lambda a: (a != first, ipaddress.ip_address(a)))


def certificate(folder: str, addresses: Sequence[str]) -> Tuple[str, str]:
    """A self-signed certificate of localhost, 127.0.0.1 and `addresses` (IP SANs), valid for a week:
    (certificate file, key file) in `folder`."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Find-a-Line device test")])
    now = datetime.now(timezone.utc)
    ips = list(dict.fromkeys(["127.0.0.1", *addresses]))
    sans = [x509.DNSName("localhost"), *(x509.IPAddress(ipaddress.ip_address(a)) for a in ips)]
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=7))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = os.path.join(folder, "device.pem"), os.path.join(folder, "device-key.pem")
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_file, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cert_file, key_file


def view3d_page(esri_key: Optional[str]) -> str:
    """The 3D page as the local app's /view3d gives it with the ring off."""
    import html

    import web
    return web.VIEW3D_HTML.format(user=html.escape(json.dumps({"local": True})), keys=web.key_meta(esri_key),
                                  ring="off")


def view3d_csp() -> str:
    import web
    from settings import ViewSettings
    return web.page_csp(ViewSettings(ring=False))["/view3d"]


def _link(entry: Dict, level: str) -> str:
    from urllib.parse import quote
    return f"/view3d?level={level}#run={quote(entry['run'], safe='')}&line={quote(entry['line'], safe='')}"


def index_page(index: Dict) -> str:
    """The recorded lines with their links for both levels (no script)."""
    import html
    rows = []
    for entry in index["entries"]:
        ok = all(a["status"] == 200 for a in entry["answers"].values())
        note = "" if ok else " (an answer was not 200: the page shows the error)"
        rows.append(f'<li><b>{html.escape(entry["title"])}</b> &middot; {entry["length_m"]:.0f} m{note}<br>'
                    f'<a href="{html.escape(_link(entry, "phone"))}">phone</a> &middot; '
                    f'<a href="{html.escape(_link(entry, "full"))}">full</a>'
                    f'<br><small>{html.escape(entry["run"])} &middot; {html.escape(entry["line"])}</small></li>')
    body = "\n".join(rows) or "<li>Nothing recorded: run <code>tools/device_page.py record</code> first.</li>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Find-a-Line device test</title>
<link rel="icon" href="/app/favicon.svg" type="image/svg+xml">
</head><body>
<h1>Find-a-Line 3D: device test</h1>
<p>The recorded lines (tools/device_page.py). "Back to the map" in the 3D view comes back here.</p>
<ul>
{body}
</ul>
</body></html>
"""


def make_app(data: str, esri_key: Optional[str] = None):
    """The device test server's Starlette app (GET only; docs above)."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from starlette.routing import Route

    import web

    folder = device_dir(data)
    index = load_index(data)
    answers: Dict[Tuple[str, Tuple[float, ...], str], Dict] = {}
    for entry in index["entries"]:
        key = line_key(entry["line"])
        for name, answer in entry["answers"].items():
            answers[(entry["run"], key, name)] = answer
    page, page_csp = view3d_page(esri_key), view3d_csp()
    cache_dir = os.path.normpath(os.path.join(data, "cache"))
    dist = web.APP_DIST

    def headers(csp: Optional[str] = None, cache: str = "no-cache", path: str = "") -> Dict[str, str]:
        found = dict(web.SECURITY_HEADERS)
        if csp:
            found["Content-Security-Policy"] = csp
        if path in web.PAGE_PERMISSIONS:  # the 3D page's: the phone's motion
            found["Permissions-Policy"] = web.PAGE_PERMISSIONS[path]
        found["Cache-Control"] = cache
        return found

    def not_found() -> Response:
        return JSONResponse({"detail": "Not Found"}, status_code=404, headers=headers(cache="no-store"))

    def home(request: Request):
        return HTMLResponse(index_page(index), headers=headers(cache="no-store"))

    def view3d(request: Request):
        return HTMLResponse(page, headers=headers(page_csp, "no-store", "/view3d"))

    def app_file(request: Request):
        return FileResponse(os.path.join(dist, request.path_params["name"]), headers=headers())

    def recorded(name: str, request: Request) -> Response:
        query = request.query_params
        answer = answers.get((query.get("run", ""), line_key(query.get("line", "")), name))
        if answer is None:
            return not_found()
        with open(os.path.join(folder, answer["file"]), "rb") as f:
            content = f.read()
        found = headers(cache="no-store")
        found.update({k.title(): v for k, v in answer["headers"].items()})
        return Response(content, status_code=answer["status"], headers=found)

    def patch(request: Request):
        step = request.query_params.get("step", "1")
        if not request.headers.get("x-findaline-patch") or step not in ("1", "2"):
            return not_found()
        return recorded(f"patch-{step}", request)

    def profile(request: Request):
        if not request.headers.get("x-findaline-profile"):
            return not_found()
        return recorded("profile", request)

    def tile(request: Request):
        path = request.path_params["path"]
        parts = path.split("/")
        full = os.path.normpath(os.path.join(cache_dir, *parts))
        if ("wm256" not in parts or not path.endswith(".jpg") or ".." in parts
                or not full.startswith(cache_dir + os.sep) or not os.path.isfile(full)):
            return not_found()
        return FileResponse(full, media_type="image/jpeg", headers=headers())

    routes = [Route("/", home, methods=["GET"]), Route("/index.html", home, methods=["GET"]),
              Route("/view3d", view3d, methods=["GET"]),
              Route("/app/{name:str}", app_file, methods=["GET"]),
              Route("/api/patch", patch, methods=["GET"]), Route("/api/profile", profile, methods=["GET"]),
              Route("/cache/{path:path}", tile, methods=["GET"])]
    app = Starlette(routes=routes)
    app_files = {"view3d.js", "view3d.css", "favicon.svg"}

    class Only:
        """GET (and HEAD) only; /app/ only the 3D page's files; the app's headers on every answer."""
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.inner(scope, receive, send)
            path = scope["path"]
            if path.startswith("/app/") and path[len("/app/"):] not in app_files:
                return await not_found()(scope, receive, send)
            if scope["method"] not in ("GET", "HEAD"):
                answer = JSONResponse({"detail": "Method Not Allowed"}, status_code=405,
                                      headers={**headers(cache="no-store"), "Allow": "GET"})
                return await answer(scope, receive, send)

            async def with_headers(message):
                if message["type"] == "http.response.start":
                    have = {k.lower() for k, _ in message["headers"]}
                    extra = [(k.lower().encode(), v.encode()) for k, v in headers(cache="no-store").items()
                             if k.lower().encode() not in have]
                    message = {**message, "headers": list(message["headers"]) + extra}
                await send(message)
            return await self.inner(scope, receive, with_headers)

    return Only(app)


def serve(data: str, port: int = 8443, host: str = "0.0.0.0", say=say_now):
    """Serve the recordings over HTTPS until stopped (Ctrl+C)."""
    import uvicorn

    from settings import web_key

    index = load_index(data)
    if not index["entries"]:
        say("Nothing recorded yet: run `tools/device_page.py record --data-dir ...` first.")
    esri_key = web_key("esri_api_key")
    addresses = lan_addresses()
    with tempfile.TemporaryDirectory(prefix="findaline-device-") as folder:
        cert_file, key_file = certificate(folder, addresses)
        app = make_app(data, esri_key)
        say(f"Serving {len(index['entries'])} recorded lines of {data} over HTTPS"
            f" (Esri imagery {'on: ESRI_API_KEY is set' if esri_key else 'off: ESRI_API_KEY not set'}):")
        first = default_address()
        for address in (["localhost"] if host in ("127.0.0.1", "localhost") else addresses + ["localhost"]):
            say(f"  https://{address}:{port}/" + ("   <- the default route: most likely the phone's Wi-Fi"
                                                   if address == first else ""))
        say("\nChecklist for the iPhone (iOS 18):\n" + CHECKLIST + "\n\nCtrl+C stops the server.")
        uvicorn.run(app, host=host, port=port, log_level="warning", ssl_certfile=cert_file, ssl_keyfile=key_file)


# --- Measuring ---------------------------------------------------------------------------------------------

# The page's modules, run in Node: per patch the tiles of the default imagery that tiles.ts plans
PLAN_TS = r"""
import { readFileSync } from "fs";
import { inflateSync } from "zlib";
import { CHUNK, decodeValues, splitAnswer, toHeights } from "./src/view3d/decode";
import { originOf } from "./src/view3d/geometry";
import { chunkCount, chunkTile, forcedSamples } from "./src/view3d/terrain";
import { corridorOf, dataBounds, orthoDraws, orthoOf, planTextures, tilesOf } from "./src/view3d/tiles";

const tasks = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = tasks.map((task) => {
  const bytes = readFileSync(task.file);
  const {meta, body} = splitAnswer(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  const values = decodeValues(new Uint8Array(inflateSync(body)), meta.width, meta.height);
  const patch = {meta, values, ...toHeights(values, meta.width, meta.height, meta.base_dm)};
  const origin = originOf(meta), {all, line} = forcedSamples(patch), [rows, cols] = chunkCount(patch);
  const chunks = [];
  for (let ci = 0; ci < rows; ci++) for (let cj = 0; cj < cols; cj++) {
    if (!chunkTile(patch, ci, cj, all, origin.h0)) continue;  // no data: no mesh, no texture
    const i0 = ci * CHUNK, j0 = cj * CHUNK;
    const bounds = {x0: meta.left + j0 * meta.res, x1: meta.left + (j0 + CHUNK + 1) * meta.res,
                    y0: meta.top - (i0 + CHUNK + 1) * meta.res, y1: meta.top - i0 * meta.res};  // scene.ts chunkOf
    const hasLine = line.some(([i, j]) => i >= i0 && i <= i0 + CHUNK && j >= j0 && j <= j0 + CHUNK);
    chunks.push({bounds, hasLine});
  }
  const plans = planTextures(meta.affine, chunks.map((c) => ({bounds: dataBounds(meta, c.bounds), hasLine: c.hasLine})),
                             task.level);
  // result/load.ts orthoForApp: the cache's path as the page resolves it from the run's map.html
  let ortho = orthoOf(meta.ortho);
  if (ortho && ortho.cache) {
    ortho = {...ortho, cache: new URL(ortho.cache, "https://device/runs/" + encodeURIComponent(task.run) + "/map.html").pathname};
  }
  const draws = [];
  let esri = 0;
  plans.forEach((p, k) => {
    if (!p) return;
    esri += tilesOf(p).length;
    if (ortho) draws.push(...orthoDraws(ortho, p, chunks[k].hasLine ? corridorOf(meta.affine, meta.anchors, p.z) : null)
                               .map((d) => ({z: p.z, x: d.x, y: d.y, cache: d.cache, layers: d.layers.map((l) => l.url),
                                             composed: d.composed ? {jpeg: d.composed.jpeg.url, base: d.composed.base.url,
                                                                     png: d.composed.png.url} : null})));
  });
  return {key: task.key, chunks: chunks.length, zooms: plans.map((p) => p ? p.z : null), ortho: !!ortho, esri, draws};
});
console.log(JSON.stringify(out));
"""


def imagery_plans(tasks: List[Dict], scratch: str) -> List[Dict]:
    """The imagery's tiles of each task ({key, file, level, run}) as the page plans them (PLAN_TS in Node)."""
    viewer = os.path.join(REPO, "viewer")
    if not os.path.isdir(os.path.join(viewer, "node_modules", "esbuild")):
        raise SystemExit("esbuild missing: run `npm ci` in viewer/ once")
    bundle, inputs = os.path.join(scratch, "plan.cjs"), os.path.join(scratch, "tasks.json")
    with open(inputs, "w", encoding="utf-8") as f:
        json.dump(tasks, f)
    build = ("require('esbuild').buildSync({stdin: {contents: " + json.dumps(PLAN_TS) + ", resolveDir: '.', "
             "loader: 'ts'}, bundle: true, format: 'cjs', platform: 'node', logLevel: 'error', outfile: "
             + json.dumps(bundle) + "})")
    subprocess.run(["node", "-e", build], cwd=viewer, check=True)
    result = subprocess.run(["node", bundle, inputs], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def _service(url: str) -> str:
    """A service of a tile URL: its host and its path without the tile's numbers (a host may serve several
    layers, a WMS's PNGs and a WMTS's JPEGs, of very different sizes)."""
    parts = urlsplit(url)
    path = "/".join(p for p in parts.path.split("/") if p and not p.split(".")[0].isdigit())
    return parts.netloc.lower() + "/" + path


def sample_hosts(urls: Sequence[str], per_host: int, say=say_now) -> Dict[str, Dict]:
    """GET up to `per_host` of the URLs of each host (spread over them and over its services, _service), with
    the app's User-Agent and the host's rate turns: {service: {"mean": bytes, "ok": n, "failed": n}}."""
    import requests

    import cache
    from sources import net
    by_service: Dict[str, List[str]] = {}
    for url in dict.fromkeys(urls):
        by_service.setdefault(_service(url), []).append(url)
    services_of: Dict[str, int] = {}
    for service in by_service:
        services_of[service.partition("/")[0]] = services_of.get(service.partition("/")[0], 0) + 1
    found = {}
    for service, listed in sorted(by_service.items()):
        share = max(1, per_host // services_of[service.partition("/")[0]])  # at most per_host GETs per host
        picked = [listed[round(i * (len(listed) - 1) / max(1, share - 1))] for i in range(min(share, len(listed)))]
        sizes, failed = [], 0
        for url in dict.fromkeys(picked):
            net.rate_turn(url)
            try:
                answer = requests.get(url, headers=cache.http_headers(), timeout=30)
                if answer.ok and answer.headers.get("content-type", "").startswith("image/"):
                    sizes.append(len(answer.content))
                else:
                    failed += 1
            except requests.RequestException:
                failed += 1
        found[service] = {"mean": sum(sizes) / len(sizes) if sizes else 0.0, "ok": len(sizes), "failed": failed}
        say(f"  sampled {service}: {len(sizes)} tiles, mean {found[service]['mean'] / 1024:.1f} KB, {failed} failed")
    return found


def _fetch(url: str) -> Optional[bytes]:
    """One tile with the app's User-Agent after the host's rate turn; None when it fails or is no image."""
    import requests

    import cache
    from sources import net
    net.rate_turn(url)
    try:
        answer = requests.get(url, headers=cache.http_headers(), timeout=30)
    except requests.RequestException:
        return None
    return answer.content if answer.ok and answer.headers.get("content-type", "").startswith("image/") else None


def sample_composed(composed: Sequence[Dict], per_host: int, say=say_now, fetch=_fetch) -> Dict[str, Dict]:
    """The tiles of a WMS over base tiles ({jpeg, base, png} URLs), by service of its JPEGs: about three quarters of
    `per_host` JPEGs spread over them, each classified by orthophoto._white_blocks, then the base tiles of the
    samples found white or partly white and the PNGs of those partly white, while the host's GETs last:
    {service: {"jpeg", "base", "png": mean bytes, "white", "partly": shares of the samples, "ok", "failed"}}."""
    import orthophoto
    by_service: Dict[str, List[Dict]] = {}
    for c in composed:
        by_service.setdefault(_service(c["jpeg"]), []).append(c)
    for service in by_service:  # one per tile
        by_service[service] = list({c["jpeg"]: c for c in by_service[service]}.values())
    used: Dict[str, int] = {}
    found = {}

    def get(url: str) -> Optional[bytes]:
        host = urlsplit(url).netloc.lower()
        if used.get(host, 0) >= per_host:
            return None
        used[host] = used.get(host, 0) + 1
        return fetch(url)

    for service, listed in sorted(by_service.items()):
        share = max(1, per_host * 3 // 4 // len(by_service))
        picked = [listed[round(i * (len(listed) - 1) / max(1, share - 1))] for i in range(min(share, len(listed)))]
        jpegs, kinds, failed = [], [], 0
        for c in {c["jpeg"]: c for c in picked}.values():
            content = get(c["jpeg"])
            if content is None:
                failed += 1
                continue
            jpegs.append(len(content))
            empty, partly = orthophoto._white_blocks(content)
            kinds.append((c, "white" if empty else "partly" if partly else "full"))
        bases, pngs = [], []
        for c, kind in kinds:
            if kind == "full":
                continue
            content = get(c["base"])
            if content is not None:
                bases.append(len(content))
            if kind == "partly" and (content := get(c["png"])) is not None:
                pngs.append(len(content))
        mean = lambda sizes: sum(sizes) / len(sizes) if sizes else 0.0  # noqa: E731
        n = max(1, len(kinds))
        found[service] = {"jpeg": mean(jpegs), "base": mean(bases), "png": mean(pngs), "ok": len(jpegs),
                          "failed": failed, "white": sum(k == "white" for _, k in kinds) / n,
                          "partly": sum(k == "partly" for _, k in kinds) / n}
        f = found[service]
        say(f"  sampled {service} (JPEG, composed): {len(jpegs)} tiles, mean {f['jpeg'] / 1024:.1f} KB, "
            f"{f['white']:.0%} white, {f['partly']:.0%} partly white (base {f['base'] / 1024:.1f} KB of {len(bases)}, "
            f"PNG {f['png'] / 1024:.1f} KB of {len(pngs)}), {failed} failed")
    return found


def composed_bytes(sample: Dict) -> float:
    """The expected bytes of one composed tile from its service's sample (sample_composed)."""
    return (sample["jpeg"] + (sample["white"] + sample["partly"]) * sample["base"]
            + sample["partly"] * sample["png"])


def measure(data: str, samples: int = 20, say=say_now) -> List[Dict]:
    """The data per open of each recorded line and level (docs above); prints the table, returns its rows."""
    folder = device_dir(data)
    index = load_index(data)
    tasks, sizes = [], {}
    for n, entry in enumerate(index["entries"]):
        answers = entry["answers"]
        for level, step in LEVELS.items():
            patch = answers.get(f"patch-{step}")
            if not patch or patch["status"] != 200:
                continue
            key = f"{n}-{level}"
            tasks.append({"key": key, "file": os.path.join(folder, patch["file"]), "level": level, "run": entry["run"]})
            profile = answers.get("profile")
            sizes[key] = (entry, level, os.path.getsize(os.path.join(folder, patch["file"])),
                          os.path.getsize(os.path.join(folder, profile["file"])) if profile else 0)
    if not tasks:
        raise SystemExit("nothing recorded: run `record` first")
    with tempfile.TemporaryDirectory(prefix="findaline-measure-") as scratch:
        plans = {p["key"]: p for p in imagery_plans(tasks, scratch)}

    def cached(url: Optional[str]) -> Optional[int]:
        if not url or not url.startswith("/cache/"):
            return None
        path = os.path.join(data, *url.strip("/").split("/"))
        return os.path.getsize(path) if os.path.isfile(path) else None

    # The service's requests of every tile our cache does not answer
    missed = [d for p in plans.values() for d in p["draws"] if cached(d["cache"]) is None]
    say(f"Sampling the services' tiles (at most {samples} per host):")
    composed = sample_composed([d["composed"] for d in missed if d.get("composed")], samples, say)
    hosts = sample_hosts([u for d in missed for u in d["layers"]], samples, say)
    rows = []
    for key, (entry, level, patch_bytes, profile_bytes) in sizes.items():
        plan = plans[key]
        tiles = cached_n = service_n = 0
        imagery = 0.0
        for d in plan["draws"]:
            tiles += 1
            size = cached(d["cache"])
            if size is not None:
                cached_n += 1
                imagery += size
            elif d.get("composed"):
                sample = composed.get(_service(d["composed"]["jpeg"]))
                service_n += 1  # its JPEG; the base and the PNG in their shares
                imagery += composed_bytes(sample) if sample else 0.0
            else:
                service_n += len(d["layers"])
                imagery += sum(hosts.get(_service(u), {"mean": 0.0})["mean"] for u in d["layers"])
        rows.append({"run": entry["run"], "title": entry["title"], "line": entry["line"], "length_m": entry["length_m"],
                     "level": level, "patch_kb": patch_bytes / 1024, "profile_kb": profile_bytes / 1024,
                     "tiles": tiles, "cached": cached_n, "service_requests": service_n, "imagery_kb": imagery / 1024,
                     "esri_tiles": plan["esri"], "zooms": plan["zooms"], "chunks": plan["chunks"],
                     "total_kb": (patch_bytes + profile_bytes + imagery) / 1024})
    head = (f"{'run':<34} {'line':>6} {'level':<5} {'patch KB':>9} {'profile KB':>10} {'tiles':>6} {'cached':>6} "
            f"{'imagery KB':>10} {'total KB':>9} {'Esri tiles':>10}  zooms")
    say("\n" + head + "\n" + "-" * len(head))
    for r in rows:
        zooms = ",".join("-" if z is None else str(z) for z in r["zooms"])
        say(f"{r['run'][:34]:<34} {r['length_m']:>5.0f}m {r['level']:<5} {r['patch_kb']:>9.0f} {r['profile_kb']:>10.1f} "
            f"{r['tiles']:>6} {r['cached']:>6} {r['imagery_kb']:>10.0f} {r['total_kb']:>9.0f} {r['esri_tiles']:>10}  {zooms}")
    say("\nimagery: the run's orthophoto (the default kind); a tile not cached is the mean of its service's sampled "
        "tiles (a WMS over base tiles: its JPEG, and the base and PNG in the shares of its samples found white and "
        "partly white). Esri tiles: the same plan's tiles, never fetched.")
    return rows


def main(argv: Optional[Sequence[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record", help="record the answers of a few lines of each run")
    rec.add_argument("--data-dir", required=True)
    rec.add_argument("--run", action="append", help="a run's id (repeatable; default: every run)")
    rec.add_argument("--lines", type=int, default=3, help="lines per run (default 3)")
    rec.add_argument("--spacing", type=float, default=50,
                     help="metres between the middles of the lines taken (default 50; 0: the first rows)")
    srv = commands.add_parser("serve", help="serve the recordings over HTTPS")
    srv.add_argument("--data-dir", required=True)
    srv.add_argument("--port", type=int, default=8443)
    srv.add_argument("--host", default="0.0.0.0")
    mes = commands.add_parser("measure", help="the data per open of each recorded line")
    mes.add_argument("--data-dir", required=True)
    mes.add_argument("--samples", type=int, default=20, help="service tiles fetched per host (default 20)")
    mes.add_argument("--json", help="also write the rows to this file")
    args = parser.parse_args(argv)
    data = os.path.abspath(args.data_dir)
    if args.command == "record":
        record(data, args.run, args.lines, args.spacing)
    elif args.command == "serve":
        serve(data, args.port, args.host)
    else:
        rows = measure(data, args.samples)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=1)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
