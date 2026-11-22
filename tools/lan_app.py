"""
The local app on the local network, for a phone's test of the result view (gate 2 of the view: the user's iPhone
opens the app's Home, a run's page `/?ui=c#run=`, as the default will open it). Run by hand:

    python tools/lan_app.py prepare --from <data folder> --data-dir <scratch folder> [--run ID ...] [--no-clip]
                                    [--coast]
    python tools/lan_app.py serve --data-dir <scratch folder> [--port 8443]

`prepare` fills a scratch data folder (neither the folder copied from nor a folder inside it): **copies** of the runs
named by `--run` of `--from`'s runs folder (of each only web.RUN_FILES and its run.json), the clip's run (the Żabi Koń
clip, made by tools/ui_shots.py's offline search once, its two terrain files copied beside it so the run does not
lean on a checkout), with `--coast` the Gozo coast's run (COAST: a public place's request, no user's data;
make_coast: a search of minutes, offline on the copy), the list of runs (runs.write_index), a copy of the cache's
files those runs read again for Measure and computed profiles (CACHE_PARTS and the files each run's run.json names),
and the folder's mark, MARKER, which `serve` requires (so it is never pointed at a real data folder). Nothing is ever
written into `--from`: the cache is copied, never linked (a read through a link would write its index.sqlite and
locks). A tile the copy lacks is downloaded into the scratch copy when Measure needs it, as the app does (no offline
mode).

`serve` starts the local app (web.create_app with its worker in its own processes, as `findaline.py web` does) on
every address of the PC (0.0.0.0) at `--port` (default 8443; never the app's own port, web.PORT 8765), over HTTPS
with tools/device_page.py's self-signed certificate (localhost, 127.0.0.1 and the PC's LAN addresses; kept in
`<data>/lan-cert` while it runs and removed at its stop, Ctrl+C or Ctrl+Break), and prints the addresses to open on
the phone. **No token and no sign-in**: anyone on the network reaches the app while it runs.
So it refuses what would start work on this PC (REFUSED: a search, "Edit & run again", an OSM download: 403 with a
plain reason); Measure, computed profiles, Download's export and favourites stay, and so does the rest of the local
app: an estimate and a place's lookup (work of the quick lane, Nominatim), deleting a search or a run (of the scratch
data folder only), the saved rigs. The page is a scratch build of the
viewer with VIEW_DEFAULT true (build_viewer: viewer/build.mjs into `<data>/lan-build`, then app.js and viewer.js
again with the one line set, as tests/test_view_default.py builds them), served as the app's /app/ and as the runs'
_viewer/ (copied into `<data>/runs/_viewer`); the repository's viewer/dist is never written. `?view=today` still
opens today's page. ESRI_API_KEY is left out of the app (no satellite map; the key would go to every phone on the
network) unless `--esri`. Ctrl+C (or Ctrl+Break) stops the server and its worker.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

PORT = 8443  # the port the user knows from tools/device_page.py
# The Gozo coast: a coastal search of a public place (the coast within 100 m of OSM's Gozo), today's defaults
COAST = ("--area", "coast", "--buffer", "100", "--within", "osm:Gozo")
MARKER = "lan-app.json"  # in the data folder: made by prepare (serve requires it); the clip's and the coast's run ids
CLIP_DIR = "clip"  # in the data folder: the clip's terrain files, which its run.json names
BUILD_DIR = "lan-build"  # in the data folder: the scratch viewer build served
CERT_DIR = "lan-cert"  # in the data folder: the certificate and its key while serve runs
# The cache's files of the sources the test's places read again for Measure and profiles (besides the files each
# run.json names), relative to a cache folder; sources and cells only, no run: the layout; geoportal.gov.pl's index,
# sheet index and orthophoto; the whole of Malta's source (COAST); Copernicus' water mask; the gap fillers' (Copernicus
# DEM, FABDEM) 1-degree cells of the Tatras (N49E020) and of Gozo (N36E014); the geoid; OSM's answers (Nominatim's
# names, the themes, the water polygons)
CACHE_PARTS = ("LAYOUT", "poland/index.sqlite", "poland/sheet-index", "poland/ortho", "malta",
               "copernicus30/index.sqlite", "copernicus30/2021/wbm", "copernicus30/2021/dem/N36E014.tif",
               "copernicus30/2021/dem/N49E020.tif", "fabdem/index.sqlite", "fabdem/v1-2/N36E014.tif",
               "fabdem/v1-2/N49E020.tif", "geoid", "osm")
REFUSED = (("POST", re.compile(r"/api/jobs")), ("POST", re.compile(r"/api/jobs/[^/]+/again")),
           ("POST", re.compile(r"/api/osm")))
REFUSED_TEXT = "This test server starts no searches on this PC (tools/lan_app.py): open a saved run instead."
# The scratch build's app.js and viewer.js: viewer/build.mjs's options, the constant's one line set by a plugin (the
# count of the files it changed is printed; a source without the line exactly once fails the build)
BUILD = r"""
const esbuild = require("esbuild"), fs = require("fs");
const [out, value] = JSON.parse(process.argv[1]);
const notice = "/*! Licences of the bundled libraries: THIRD-PARTY-LICENSES.txt */";
let hits = 0;
const flip = {name: "view-default", setup(build) {
  build.onLoad({filter: /[\\/]SpotColumns\.tsx$/}, (args) => {
    const text = fs.readFileSync(args.path, "utf8"), line = /export const VIEW_DEFAULT: boolean = (true|false);/g;
    const found = text.match(line) || [];
    if (found.length !== 1) throw new Error(found.length + " lines of VIEW_DEFAULT in " + args.path);
    hits++;
    return {contents: text.replace(line, "export const VIEW_DEFAULT: boolean = " + value + ";"), loader: "tsx"};
  });
}};
esbuild.build({entryPoints: {app: "src/app/app.tsx", viewer: "src/map/main.tsx"}, bundle: true, minify: true,
               legalComments: "none", banner: {js: notice, css: notice}, format: "iife", target: "es2020",
               outdir: out, assetNames: "[name]-[hash]", loader: {".png": "dataurl", ".svg": "text", ".woff2": "file"},
               logLevel: "warning", plugins: [flip]})
  .then(() => console.log(JSON.stringify({hits})), (e) => { console.error(String(e)); process.exit(1); });
"""


def say_now(*args):
    """print, flushed (the start is read through pipes too)."""
    print(*args, flush=True)


# --- The data folder ---------------------------------------------------------------------------------------

def _copy(source: str, target: str):
    """A file or a folder copied (a file already there with the same size and time is kept); only reads `source`."""
    if os.path.isdir(source):
        for root, _, names in os.walk(source):
            for name in names:
                path = os.path.join(root, name)
                _copy(path, os.path.join(target, os.path.relpath(path, source)))
        return
    if os.path.isfile(target):
        a, b = os.stat(source), os.stat(target)
        if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
            return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)


def copy_run(source_runs: str, data: str, run: str):
    """A run's web.RUN_FILES and run.json copied into the data folder's runs/ (nothing else of its folder)."""
    import web
    folder = os.path.join(source_runs, run)
    if not os.path.isfile(os.path.join(folder, "run.json")):
        raise SystemExit(f"no run {run} in {source_runs}")
    target = os.path.join(data, "runs", run)
    os.makedirs(target, exist_ok=True)
    for name in (*web.RUN_FILES, "run.json"):
        if os.path.isfile(os.path.join(folder, name)):
            _copy(os.path.join(folder, name), os.path.join(target, name))


def run_cache_paths(run_folder: str) -> List[str]:
    """The cache files a run's run.json names (its data's `paths`, relative to a cache folder)."""
    with open(os.path.join(run_folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return [p for d in meta.get("data") or [] for p in d.get("paths") or []]


def copy_cache(source_cache: str, data: str, parts: Iterable[str]) -> Tuple[int, int]:
    """The parts (files or folders, relative) copied from a cache folder into the data folder's cache/ (those the
    source lacks are skipped); (files, bytes) of the copy."""
    target = os.path.join(data, "cache")
    for part in dict.fromkeys(parts):
        source = os.path.join(source_cache, *part.split("/"))
        if os.path.exists(source):
            _copy(source, os.path.join(target, *part.split("/")))
    files = size = 0
    for root, _, names in os.walk(target):
        for name in names:
            files += 1
            size += os.path.getsize(os.path.join(root, name))
    return files, size


def read_marker(data: str) -> Dict:
    try:
        with open(os.path.join(data, MARKER), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_marker(data: str, **values):
    """The data folder's mark with `values` added (read whole before the file is opened for writing: that empties it)."""
    marker = {**read_marker(data), **values}
    with open(os.path.join(data, MARKER), "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=1)


def make_clip(data: str, say=say_now) -> str:
    """The clip's run in the data folder (tools/ui_shots.py's offline search of tests/data, once: the marker keeps its
    id), with its two terrain files copied into <data>/clip and its run.json naming those copies."""
    import ui_shots
    marker = read_marker(data)
    clip = marker.get("clip")
    if clip and os.path.isfile(os.path.join(data, "runs", clip, "run.json")):
        return clip
    say("The clip's run: an offline search of tests/data ...")
    clip = ui_shots.clip_run(data)
    folder = os.path.join(data, CLIP_DIR)
    os.makedirs(folder, exist_ok=True)
    meta_path = os.path.join(data, "runs", clip, "run.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    for entry in meta.get("data") or []:
        if entry.get("file"):
            copy = os.path.join(folder, os.path.basename(entry["file"]))
            shutil.copy2(entry["file"], copy)
            entry["file"] = copy
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    write_marker(data, clip=clip)
    return clip


def make_coast(data: str, say=say_now) -> str:
    """The Gozo coast's run in the data folder (COAST, today's defaults), once: the marker keeps its id. A search of
    minutes on the data folder's cache (prepare copies Malta's), offline: what the copy lacks fails the search instead
    of being downloaded."""
    marker = read_marker(data)
    coast = marker.get("coast")
    if coast and os.path.isfile(os.path.join(data, "runs", coast, "run.json")):
        return coast
    say("The Gozo coast's run: a search of minutes ...")
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
           "PYTHONIOENCODING": "utf-8"}
    env = {k: v for k, v in env.items() if k.upper() != "ESRI_API_KEY"}
    runs = os.path.join(data, "runs")
    before = set(os.listdir(runs))
    done = subprocess.run([sys.executable, os.path.join(REPO, "findaline.py"), *COAST, "--no-plot", "--yes",
                           "--data-dir", data], cwd=REPO, env=env)
    if done.returncode:
        raise SystemExit(f"the Gozo coast's search failed (exit {done.returncode})")
    made = [d for d in os.listdir(runs) if d not in before and os.path.isfile(os.path.join(runs, d, "run.json"))]
    if len(made) != 1:
        raise SystemExit(f"the Gozo coast's search made {len(made)} runs in {runs}, not one")
    write_marker(data, coast=made[0])
    return made[0]


def served_runs(data: str) -> List[Dict]:
    """The runs the app lists (runs.list_runs of the data folder): id and name, newest first."""
    import runs as rn
    return [{"id": r["id"], "name": r.get("name", r["id"])} for r in rn.list_runs(os.path.join(data, "runs"))]


def prepare(data: str, source: str, runs: Sequence[str] = (), clip: bool = True, coast: bool = False,
            parts: Sequence[str] = CACHE_PARTS, say=say_now) -> List[str]:
    """The data folder made ready (docs above); the ids of its runs. `source`: the data folder copied from (its runs/
    and cache/ are only read)."""
    import runs as rn
    data, source = os.path.realpath(data), os.path.realpath(source)
    inside = os.path.normcase(data) == os.path.normcase(source) or os.path.normcase(data).startswith(
        os.path.normcase(source).rstrip(os.sep) + os.sep)
    if inside:
        raise SystemExit("the data folder must be a scratch folder, neither the one copied from nor inside it")
    os.makedirs(os.path.join(data, "runs"), exist_ok=True)
    write_marker(data, prepared=True)  # the mark serve requires
    for run in runs:
        copy_run(os.path.join(source, "runs"), data, run)
        say(f"Copied the run {run}")
    wanted = list(parts) + [p for run in runs for p in run_cache_paths(os.path.join(data, "runs", run))]
    files, size = copy_cache(os.path.join(source, "cache"), data, wanted)
    say(f"The cache's copy: {files} files, {size / 1e9:.2f} GB in {os.path.join(data, 'cache')}")
    if clip:
        make_clip(data, say)
    if coast:
        make_coast(data, say)
    rn.write_index(os.path.join(data, "runs"))
    return [r["id"] for r in served_runs(data)]


# --- The page served ---------------------------------------------------------------------------------------

def build_viewer(out: str, say=say_now) -> str:
    """The scratch build: viewer/build.mjs into `out`, then app.js and viewer.js (with their CSS) again with
    VIEW_DEFAULT true (BUILD); `out`. SystemExit when Node or esbuild is missing or the build fails."""
    viewer = os.path.join(REPO, "viewer")
    if not os.path.isdir(os.path.join(viewer, "node_modules", "esbuild")):
        raise SystemExit("esbuild missing: run `npm ci` in viewer/ once")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    say("Building the viewer with VIEW_DEFAULT true ...")
    done = subprocess.run(["node", "build.mjs", "--out", out], cwd=viewer, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)
    if done.returncode:
        raise SystemExit("viewer/build.mjs failed: " + done.stderr)
    done = subprocess.run(["node", "-e", BUILD, json.dumps([out, "true"])], cwd=viewer, capture_output=True,
                          text=True, encoding="utf-8", timeout=600)
    if done.returncode:
        raise SystemExit("the build with VIEW_DEFAULT true failed: " + done.stderr)
    hits = json.loads(done.stdout.strip().splitlines()[-1])["hits"]
    if hits != 1:
        raise SystemExit(f"the build set VIEW_DEFAULT in {hits} files, not one")
    return out


def install_build(build: str, data: str):
    """The scratch build as the runs' _viewer/ of the data folder (its old files removed first)."""
    import mapping
    target = os.path.join(data, "runs", mapping.VIEWER_FOLDER)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(build, target)


def origin(host: str, port: int) -> str:
    """The https origin of a host and port as a browser writes it (no port when it is https' own, 443)."""
    return f"https://{host}" if port == 443 else f"https://{host}:{port}"


def origins(port: int, addresses: Sequence[str]) -> Tuple[str, ...]:
    """The origins the phone and the PC reach the app by: https on localhost, 127.0.0.1 and the LAN addresses."""
    return tuple(origin(host, port) for host in dict.fromkeys(["localhost", "127.0.0.1", *addresses]))


def refusing(app):
    """The ASGI app that answers REFUSED's requests itself (403, REFUSED_TEXT), the rest by `app`."""
    from starlette.responses import JSONResponse

    import web

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and any(scope["method"] == method and pattern.fullmatch(scope["path"])
                                           for method, pattern in REFUSED):
            answer = JSONResponse({"detail": REFUSED_TEXT}, status_code=403,
                                  headers={**web.SECURITY_HEADERS, "Cache-Control": "no-store"})
            return await answer(scope, receive, send)
        return await app(scope, receive, send)
    return guarded


def make_app(data: str, port: int, addresses: Sequence[str], build: str, start_scheduler: bool = True,
             esri: bool = False):
    """The local app over the data folder for the LAN (docs above): (the ASGI app, the FastAPI app inside)."""
    import web
    from jobs import warm_up_wanted
    if port == web.PORT:
        raise SystemExit(f"port {web.PORT} is the app's own: take another (default {PORT})")
    install_build(build, data)
    read_key = web.web_key
    # the satellite map's key stays off the network's phones (create_app reads it once, here); the app's /app/ from
    # the scratch build
    keys = mock.patch.object(web, "web_key", lambda name, *a, **k: None if name == "esri_api_key" and not esri
                             else read_key(name, *a, **k))
    with keys, mock.patch.object(web, "APP_DIST", build):
        app = web.create_app(data, port=port, start_scheduler=start_scheduler, warm_up=warm_up_wanted(),
                             lan_origins=origins(port, addresses))
    return refusing(app), app


def _break_as_interrupt(*_):
    """Ctrl+Break as Ctrl+C: uvicorn stops on it and then raises it again with the handler it found, this one, so the
    stop unwinds (the certificate's folder removed) instead of ending the process at once."""
    raise KeyboardInterrupt


def serve(data: str, port: int = PORT, host: str = "0.0.0.0", esri: bool = False, say=say_now):
    """Serve the app over HTTPS until Ctrl+C or Ctrl+Break."""
    import uvicorn

    import cache
    import device_page
    import web
    data = os.path.abspath(data)
    if port == web.PORT:
        raise SystemExit(f"port {web.PORT} is the app's own: take another (default {PORT})")
    if not os.path.isfile(os.path.join(data, MARKER)):
        raise SystemExit(f"{data} is no data folder made by `tools/lan_app.py prepare` (no {MARKER}): "
                         "serve shows only such a scratch folder")
    listed = served_runs(data)
    if not listed:
        raise SystemExit(f"no runs in {os.path.join(data, 'runs')}: run `tools/lan_app.py prepare` first")
    cache.check_layout(os.path.join(data, "cache"))
    build = build_viewer(os.path.join(data, BUILD_DIR), say)
    addresses = device_page.lan_addresses()
    folder = os.path.join(data, CERT_DIR)
    shutil.rmtree(folder, ignore_errors=True)  # a stop that could not remove it (the process killed)
    os.makedirs(folder)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _break_as_interrupt)
    try:
        cert_file, key_file = device_page.certificate(folder, addresses)
        app, _ = make_app(data, port, addresses, build, esri=esri)
        say(f"\nFind-a-Line on the local network, over HTTPS, from {data}: OPEN TO ANYONE ON THIS NETWORK while it "
            f"runs (no sign-in). Searches are refused; the result view is the default (?view=today: today's page).")
        say("Runs: " + "; ".join(r["name"] for r in listed))
        first = device_page.default_address()
        for address in (["localhost"] if host in ("127.0.0.1", "localhost") else addresses + ["localhost"]):
            say(f"  {origin(address, port)}/" + ("   <- the default route: most likely the phone's Wi-Fi"
                                                 if address == first else ""))
        say("The certificate is self-signed and made anew at each start: accept it on the phone again after a "
            "restart.\nCtrl+C stops the server.")
        server = uvicorn.Server(uvicorn.Config(
            app, host=host, port=port, log_level="warning", server_header=False, proxy_headers=False,
            timeout_graceful_shutdown=web.GRACEFUL_SECONDS, timeout_keep_alive=web.KEEP_ALIVE_SECONDS,
            ssl_certfile=cert_file, ssl_keyfile=key_file))
        server.run()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main(argv: Optional[Sequence[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("prepare", help="copy the runs and the cache's files they need, make the clip")
    pre.add_argument("--from", dest="source", required=True, help="the data folder copied from (only read)")
    pre.add_argument("--data-dir", required=True, help="the scratch data folder")
    pre.add_argument("--run", action="append", default=[], help="a run's id in --from's runs folder (repeatable)")
    pre.add_argument("--no-clip", action="store_true", help="without the clip's run")
    pre.add_argument("--coast", action="store_true",
                     help="also the Gozo coast's run: the request of a public place (COAST), a search of minutes")
    srv = commands.add_parser("serve", help="serve the app over HTTPS on the local network")
    srv.add_argument("--data-dir", required=True, help="the data folder made by prepare")
    srv.add_argument("--port", type=int, default=PORT, help=f"the port (default {PORT}; never 8765)")
    srv.add_argument("--host", default="0.0.0.0", help="the address listened on (default: all of the PC's)")
    srv.add_argument("--esri", action="store_true", help="give the page ESRI_API_KEY (the satellite map)")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        ids = prepare(args.data_dir, args.source, args.run, clip=not args.no_clip, coast=args.coast)
        say_now("Runs in the data folder: " + ", ".join(ids))
    else:
        serve(args.data_dir, args.port, args.host, args.esri)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    try:
        main()
    except KeyboardInterrupt:  # Ctrl+C: uvicorn has stopped the app and its worker, then raised it again
        say_now("Stopped.")
