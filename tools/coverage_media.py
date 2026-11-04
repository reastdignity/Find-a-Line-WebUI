"""
The coverage map's animations and images: the videos for Instagram and Facebook (MP4, 4:5 and 9:16), the
README's GIFs and maps, the carousel, the Stories and the A3 poster.

Every picture is drawn by the media page (viewer/src/coverage/media/main.ts, built by
`node build.mjs --media` into a temporary folder) in headless Chromium: `window.FAL_MEDIA.setup(...)` picks a
story or an image, `frame(t)` draws the frame at t seconds without a clock, so the same command gives the same
frames. The page is served from 127.0.0.1 with the app's Content-Security-Policy (web.SECURITY_HEADERS), next to
the contrast of docs/coverage/contrast/ as `contrast/`; an error in its console stops the tool. The frames go
as PNGs straight into ffmpeg (imageio-ffmpeg's binary), never to files: H.264, yuv420p (BT.709, limited range),
30 fps, CRF 18, `+faststart`; `--music` adds the track cut to the video's length with a fade-out in its last
second (AAC), without it there is no audio stream. Every file is checked after writing (codec, pixel format,
frame rate, size, number of frames, audio), a failure is an error.

    uv sync --group ui
    uv run playwright install chromium
    cd viewer; npm ci
    uv run tools/coverage_media.py video --story contrast|fill|timeline|mix --length short|medium|long
        --format 4x5|9x16 --theme light|dark --lang en|pl [--place <id>] [--music <file>] [--out <folder>]
    uv run tools/coverage_media.py gif [--theme light|dark] [--lang en|pl] [--out <folder>]
    uv run tools/coverage_media.py images [--group readme|carousel|stories|poster] [--theme ...] [--lang ...]
    uv run tools/coverage_media.py all [--music <file>] [--force] [--out <folder>]
    uv run tools/coverage_media.py readme

`--out` defaults to <data folder>/work/coverage-media/ (`--data-dir`, FINDALINE_DATA, else the repository).
`all` writes the 96 videos (4 stories x 3 lengths x 2 formats x 2 themes x 2 languages), the GIFs and every
image, skipping the files that exist unless `--force`. `readme` writes the README's English GIFs and maps into
docs/images/. The poster is a PNG of 300 dpi and a PDF of one A3 page made by img2pdf, which holds the PNG's
compressed data as they are, so nothing is lost.
"""

import argparse
import base64
import functools
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Dict, List, Optional, Sequence

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

VIEWER = os.path.join(REPO, "viewer")
CONTRAST = os.path.join(REPO, "docs", "coverage", "contrast")
README_DIR = os.path.join(REPO, "docs", "images")

# What the media page offers (FAL_MEDIA: checked against it when it has loaded)
STORIES = ("contrast", "fill", "timeline", "mix")
LENGTHS = {"short": 10, "medium": 18, "long": 26}
FORMATS = {"4x5": (1080, 1350), "9x16": (1080, 1920)}
THEMES = ("light", "dark")
LANGS = ("en", "pl")
GROUPS = ("readme", "carousel", "stories", "poster")

FPS = 30
CRF = 18                 # x264's quality: thin text and the hatching survive Instagram's re-encoding
GIF_FPS = 15             # the README's GIF: 15 frames a second, scaled to GIF_WIDTH (each under about 3 MB)
GIF_WIDTH = 900
POSTER_DPI = 300         # the A3 poster: 3508 x 4961 px are 297 x 420 mm
# README's assets: the GIF of each theme and the static maps of these views (FAL_MEDIA's `gh-<view>`)
README_VIEWS = ("world", "europe", "na", "oceania")
LOAD_SECONDS = 60


class Failure(Exception):
    """A missing tool, a page error or an output that fails its check: the tool stops with its text."""


# --- names ---------------------------------------------------------------------------------------------------

def video_name(story: str, length: str, format: str, theme: str, lang: str, place: Optional[str] = None) -> str:
    return f"coverage-{story}-{length}-{format}-{theme}-{lang}{'-' + place if place else ''}.mp4"


def all_videos() -> List[Dict[str, str]]:
    """The options of every video of `all`: 4 stories x 3 lengths x 2 formats x 2 themes x 2 languages."""
    return [{"story": s, "length": n, "format": f, "theme": t, "lang": g}
            for s in STORIES for n in LENGTHS for f in FORMATS for t in THEMES for g in LANGS]


def gif_name(theme: str, lang: str) -> str:
    return f"coverage-{theme}-{lang}.gif"


def image_name(name: str, theme: str, lang: str, ext: str = "png") -> str:
    return f"{name}-{theme}-{lang}.{ext}"


def frame_times(duration: float, fps: float) -> List[float]:
    """The times of the frames of a story: n = duration x fps frames, the first at 0."""
    return [i / fps for i in range(round(duration * fps))]


# --- ffmpeg --------------------------------------------------------------------------------------------------

def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError:
        raise Failure("imageio-ffmpeg is missing: uv sync --group ui")
    return imageio_ffmpeg.get_ffmpeg_exe()


def video_command(ffmpeg: str, out: str, duration: float, music: Optional[str] = None) -> List[str]:
    """ffmpeg reading PNG frames from its input and writing an MP4 for social media (with `music`, an AAC track
    cut to `duration` and faded out over the last second)."""
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-"]
    if music:
        cmd += ["-i", music]
    cmd += ["-map", "0:v:0",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
                   "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv",
            "-c:v", "libx264", "-preset", "slow", "-crf", str(CRF), "-profile:v", "high",
            "-x264-params", "aq-mode=3",      # no banding in the hillshades' smooth shades
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-r", str(FPS)]
    if music:
        fade = max(duration - 1, 0)
        cmd += ["-map", "1:a:0", "-af", f"apad,afade=t=out:st={fade:g}:d=1", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    return cmd + ["-t", f"{duration:g}", "-movflags", "+faststart", "-f", "mp4", out]


def gif_command(ffmpeg: str, out: str, fps: float = GIF_FPS, width: int = GIF_WIDTH) -> List[str]:
    """ffmpeg reading PNG frames and writing a looping GIF with one palette made for the whole of it."""
    graph = (f"scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];"
             f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
    return [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "image2pipe", "-framerate", f"{fps:g}", "-c:v", "png", "-i", "-",
            "-filter_complex", graph, "-loop", "0", "-f", "gif", out]


def probe_command(ffmpeg: str, path: str) -> List[str]:
    """ffmpeg describing a file and counting its video frames (a stream copy, no decoding)."""
    return [ffmpeg, "-hide_banner", "-nostdin", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"]


def parse_probe(text: str) -> Dict:
    """What the output of probe_command tells: the first video stream's codec, pixel format, size and frame
    rate, the audio codecs, the duration and the number of frames copied."""
    info: Dict = {"audio": re.findall(r"Stream #\S+.*?: Audio: (\w+)", text)}
    video = re.search(r"Stream #\S+.*?: Video: (\w+).*?, (\w+)(?:\([^)]*\))?, (\d+)x(\d+)", text)
    if video:
        info.update(codec=video[1], pix_fmt=video[2], width=int(video[3]), height=int(video[4]))
    fps = re.search(r"Video: .*?, ([\d.]+) fps", text)
    info["fps"] = float(fps[1]) if fps else None
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    info["duration"] = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]) if duration else None
    frames = re.findall(r"frame=\s*(\d+)", text)
    info["frames"] = int(frames[-1]) if frames else None
    return info


def check_media(ffmpeg: str, path: str, *, codec: str, width: int, height: int, frames: int,
                fps: Optional[float] = None, pix_fmt: Optional[str] = None, audio: bool = False) -> Dict:
    """Read the written file back and compare it with what was meant; a difference is a Failure."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise Failure(f"{path}: not written")
    run = subprocess.run(probe_command(ffmpeg, path), capture_output=True, text=True, errors="replace")
    info = parse_probe(run.stderr)
    wrong = []
    for key, want in (("codec", codec), ("width", width), ("height", height), ("pix_fmt", pix_fmt), ("fps", fps)):
        if want is not None and info.get(key) != want:
            wrong.append(f"{key} {info.get(key)} instead of {want}")
    if info["frames"] is None or abs(info["frames"] - frames) > 1:
        wrong.append(f"{info['frames']} frames instead of {frames}")
    if fps and (info["duration"] is None or abs(info["duration"] - frames / fps) > 1 / fps + 1e-6):
        wrong.append(f"lasts {info['duration']} s instead of {frames / fps:g} s")
    if audio and info["audio"] != ["aac"] or not audio and info["audio"]:
        wrong.append(f"audio streams {info['audio']}" + (" instead of one AAC" if audio else ", none expected"))
    if wrong:
        raise Failure(f"{path}: " + "; ".join(wrong))
    info["bytes"] = os.path.getsize(path)
    return info


class Encoder:
    """An ffmpeg process taking PNG frames on its input; `close` waits for it and fails on its errors."""

    def __init__(self, cmd: List[str]):
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)

    def write(self, png: bytes):
        try:
            self.proc.stdin.write(png)
        except (BrokenPipeError, OSError):
            self.close()  # raises with ffmpeg's message
            raise

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        code = self.proc.wait()
        self.log.seek(0)
        message = self.log.read().decode("utf-8", "replace").strip()
        self.log.close()
        if code:
            raise Failure(f"ffmpeg ended with {code}: {message[-2000:]}")

    def kill(self):
        try:
            self.proc.kill()
        except OSError:
            pass
        self.proc.wait()
        self.log.close()


# --- PNG and PDF ---------------------------------------------------------------------------------------------

def png_file(png: bytes, dpi: Optional[int] = None) -> bytes:
    """The canvas's PNG (RGBA) as an optimised RGB PNG, with its resolution (pHYs) when `dpi` is given."""
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        if im.mode == "RGBA" and im.getchannel("A").getextrema() != (255, 255):
            raise Failure("the canvas has transparent pixels")
        out = io.BytesIO()
        im.convert("RGB").save(out, "PNG", optimize=True, **({"dpi": (dpi, dpi)} if dpi else {}))
    return out.getvalue()


def pdf_of_png(png: bytes, dpi: int) -> bytes:
    """A PDF of one page the size of the image at `dpi`, the image its whole content (img2pdf takes the IDAT data
    of a PNG without interlacing as they are: FlateDecode with PNG's predictors, nothing compressed again)."""
    try:
        import img2pdf
    except ImportError:
        raise Failure("img2pdf is missing: uv sync --group ui")
    return img2pdf.convert(png, layout_fun=img2pdf.get_fixed_dpi_layout_fun((dpi, dpi)), nodate=True)


# --- the media page ------------------------------------------------------------------------------------------

PAGE = ('<!doctype html><html><head><meta charset="utf-8"><title>Find-a-Line media</title>'
        '<link rel="stylesheet" href="coverage-media.css"></head>'
        '<body><canvas id="media"></canvas><script src="coverage-media.js"></script></body></html>')

FRAME_JS = "t => { window.FAL_MEDIA.frame(t); return document.getElementById('media').toDataURL('image/png'); }"


def _security_headers() -> Dict[str, str]:
    import web
    return dict(web.SECURITY_HEADERS)


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".woff2": "font/woff2", ".js": "text/javascript", ".json": "application/json"}
    headers_to_send: Dict[str, str] = {}

    def end_headers(self):
        for name, value in self.headers_to_send.items():
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, *args):
        pass


class MediaPage:
    """The media page built into a temporary folder, served on 127.0.0.1 and opened in headless Chromium."""

    def __enter__(self):
        node = shutil.which("node")
        if not node:
            raise Failure("Node.js is missing (https://nodejs.org), it builds the media page")
        if not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")):
            raise Failure("viewer/node_modules is missing: cd viewer; npm ci")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Failure("Playwright is missing: uv sync --group ui; uv run playwright install chromium")
        self.folder = tempfile.mkdtemp(prefix="findaline-media-")
        try:
            build = subprocess.run([node, "build.mjs", "--media", "--out", self.folder], cwd=VIEWER,
                                   capture_output=True, text=True, errors="replace")
            if build.returncode:
                raise Failure(f"building the media page failed: {build.stderr.strip()[-2000:]}")
            shutil.copytree(CONTRAST, os.path.join(self.folder, "contrast"))
            with open(os.path.join(self.folder, "index.html"), "w", encoding="utf-8") as f:
                f.write(PAGE)
            handler = type("Handler", (_Handler,), {"headers_to_send": _security_headers()})
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                          functools.partial(handler, directory=self.folder))
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            self.playwright = sync_playwright().start()
            try:
                self.browser = self.playwright.chromium.launch()
            except Exception as e:
                raise Failure(f"Chromium does not start ({str(e).splitlines()[0]}): uv run playwright install chromium")
            self.page = self.browser.new_page()
            self.errors: List[str] = []
            self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
            self.page.on("pageerror", lambda e: self.errors.append(str(e)))
            self.page.goto(f"http://127.0.0.1:{self.server.server_address[1]}/index.html")
            started = time.monotonic()
            # polled: wait_for_function evaluates a string, which the CSP refuses
            while not self.page.evaluate("() => !!(window.FAL_MEDIA || window.FAL_MEDIA_ERROR)"):
                if self.errors or time.monotonic() - started > LOAD_SECONDS:
                    raise Failure(f"the media page did not load: {self.errors or 'timeout'}")
                self.page.wait_for_timeout(100)
            error = self.page.evaluate("() => window.FAL_MEDIA_ERROR")
            if error:
                raise Failure(f"the media page did not load: {error}")
            self.info = self.page.evaluate("() => ({stories: FAL_MEDIA.stories, lengths: FAL_MEDIA.lengths, "
                                           "formats: FAL_MEDIA.formats, gif: FAL_MEDIA.gif, "
                                           "places: FAL_MEDIA.places, statics: FAL_MEDIA.statics})")
            self._compare()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _compare(self):
        """The tool's lists of stories, lengths and formats must be the page's."""
        info = self.info
        if (tuple(info["stories"]) != STORIES or info["lengths"] != LENGTHS
                or {k: tuple(v) for k, v in info["formats"].items()} != FORMATS
                or {s["group"] for s in info["statics"]} != set(GROUPS)):
            raise Failure(f"the media page offers other stories, lengths, formats or groups: {info}")

    def __exit__(self, *exc):
        for name, close in (("browser", "close"), ("playwright", "stop"), ("server", "shutdown")):
            if hasattr(self, name):
                try:
                    getattr(getattr(self, name), close)()
                except Exception:
                    pass
        shutil.rmtree(self.folder, ignore_errors=True)

    def setup(self, options: Dict) -> Dict:
        return self.page.evaluate("o => window.FAL_MEDIA.setup(o)", options)

    def frame(self, t: float) -> bytes:
        """The PNG of the frame at t seconds."""
        url = self.page.evaluate(FRAME_JS, t)
        if self.errors:
            raise Failure(f"the media page: {self.errors}")
        return base64.b64decode(url.split(",", 1)[1])

    def static(self, name: str) -> Dict:
        found = [s for s in self.info["statics"] if s["name"] == name]
        if not found:
            raise Failure(f"no image {name} on the media page")
        return found[0]


# --- outputs -------------------------------------------------------------------------------------------------

def _temporary(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return f"{stem}.part{ext}"


def write_video(page: MediaPage, ffmpeg: str, path: str, options: Dict, music: Optional[str] = None,
                seconds: Optional[float] = None) -> Dict:
    """One story as an MP4 (written next to `path`, checked, then moved there); `seconds`: only its start."""
    size = page.setup({"kind": "story", **options})
    times = frame_times(min(size["duration"], seconds or size["duration"]), FPS)
    part = _temporary(path)
    started = time.monotonic()
    encoder = Encoder(video_command(ffmpeg, part, len(times) / FPS, music))
    try:
        for t in times:
            encoder.write(page.frame(t))
    except BaseException:
        encoder.kill()
        _remove(part)
        raise
    encoder.close()
    try:
        info = check_media(ffmpeg, part, codec="h264", width=size["width"], height=size["height"],
                           frames=len(times), fps=FPS, pix_fmt="yuv420p", audio=bool(music))
    except Failure:
        _remove(part)
        raise
    os.replace(part, path)
    info["seconds"] = time.monotonic() - started
    return info


def write_gif(page: MediaPage, ffmpeg: str, path: str, theme: str, lang: str,
              fps: float = GIF_FPS, width: int = GIF_WIDTH) -> Dict:
    size = page.setup({"kind": "gif", "theme": theme, "lang": lang})
    times = frame_times(size["duration"], fps)
    part = _temporary(path)
    started = time.monotonic()
    encoder = Encoder(gif_command(ffmpeg, part, fps, width))
    try:
        for t in times:
            encoder.write(page.frame(t))
    except BaseException:
        encoder.kill()
        _remove(part)
        raise
    encoder.close()
    height = round(size["height"] * width / size["width"] / 2) * 2
    try:
        info = check_media(ffmpeg, part, codec="gif", width=width, height=height, frames=len(times))
    except Failure:
        _remove(part)
        raise
    os.replace(part, path)
    info["seconds"] = time.monotonic() - started
    return info


def write_image(page: MediaPage, path: str, name: str, theme: str, lang: str) -> Dict:
    """A still image as an optimised PNG; the poster also as a PDF of A3 (`path` with .pdf)."""
    from PIL import Image
    image = page.static(name)
    page.setup({"kind": "static", "name": name, "theme": theme, "lang": lang})
    poster = image["group"] == "poster"
    png = png_file(page.frame(0), POSTER_DPI if poster else None)
    with Image.open(io.BytesIO(png)) as im:
        if im.size != (image["width"], image["height"]):
            raise Failure(f"{path}: {im.size} instead of {image['width']} x {image['height']}")
    _write(path, png)
    info = {"bytes": len(png)}
    if poster:
        pdf = os.path.splitext(path)[0] + ".pdf"
        _write(pdf, pdf_of_png(png, POSTER_DPI))
        info["pdf_bytes"] = os.path.getsize(pdf)
    return info


def _write(path: str, data: bytes):
    part = _temporary(path)
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, path)


def _remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


def _mb(n: int) -> str:
    return f"{n / 1e6:.2f} MB"


# --- commands ------------------------------------------------------------------------------------------------

def places() -> List[str]:
    """The places of the contrast (its first is a story's default)."""
    with open(os.path.join(CONTRAST, "contrast.json"), encoding="utf-8") as f:
        return list(json.load(f)["places"])


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="coverage_media.py", description=__doc__.split("\n\n")[0].strip(),
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def common(q, out=True):
        if out:
            q.add_argument("--out", help="output folder (default: <data folder>/work/coverage-media)")
        q.add_argument("--data-dir", help="the data folder of the default --out")

    v = sub.add_parser("video", help="one story as an MP4")
    v.add_argument("--story", required=True, choices=STORIES)
    v.add_argument("--length", required=True, choices=list(LENGTHS))
    v.add_argument("--format", required=True, choices=list(FORMATS))
    v.add_argument("--theme", required=True, choices=THEMES)
    v.add_argument("--lang", required=True, choices=LANGS)
    v.add_argument("--place", choices=places(), help="the contrast's place (default: the first)")
    v.add_argument("--music", help="an audio file: cut to the video's length, faded out, AAC")
    common(v)
    g = sub.add_parser("gif", help="the README's looping GIF")
    g.add_argument("--theme", choices=THEMES, help="default: both")
    g.add_argument("--lang", choices=LANGS, default="en")
    common(g)
    i = sub.add_parser("images", help="the still images (PNG; the poster also as a PDF)")
    i.add_argument("--group", choices=GROUPS, help="default: every group")
    i.add_argument("--theme", choices=THEMES, help="default: both")
    i.add_argument("--lang", choices=LANGS, help="default: both")
    common(i)
    a = sub.add_parser("all", help="every video, GIF and image")
    a.add_argument("--music", help="an audio file for every video")
    a.add_argument("--force", action="store_true", help="write the files that exist again")
    common(a)
    sub.add_parser("readme", help="the README's GIFs and maps into docs/images/ (English)")
    return p


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    # `--all` as a synonym of the command `all`
    argv = ["all" if a == "--all" else a for a in (sys.argv[1:] if argv is None else argv)]
    args = parser().parse_args(argv)
    if getattr(args, "music", None) and not os.path.isfile(args.music):
        parser().error(f"--music: no file {args.music}")
    return args


def out_folder(args: argparse.Namespace) -> str:
    if args.command == "readme":
        return README_DIR
    if args.out:
        return os.path.abspath(args.out)
    import cache
    return os.path.join(cache.data_dir(args.data_dir), "work", "coverage-media")


def _video(page, ffmpeg, folder, options, music, label=""):
    path = os.path.join(folder, video_name(**options))
    info = write_video(page, ffmpeg, path, options, music)
    print(f"{label}{os.path.basename(path)}: {info['frames']} frames in {info['seconds']:.1f} s "
          f"({info['frames'] / info['seconds']:.1f} frames/s), {_mb(info['bytes'])}", flush=True)


def _gif(page, ffmpeg, path, theme, lang, label=""):
    info = write_gif(page, ffmpeg, path, theme, lang)
    print(f"{label}{os.path.basename(path)}: {info['frames']} frames in {info['seconds']:.1f} s, {_mb(info['bytes'])}",
          flush=True)


def _image(page, path, name, theme, lang, label=""):
    info = write_image(page, path, name, theme, lang)
    pdf = f", PDF {_mb(info['pdf_bytes'])}" if "pdf_bytes" in info else ""
    print(f"{label}{os.path.basename(path)}: {_mb(info['bytes'])}{pdf}", flush=True)


def run(args: argparse.Namespace):
    folder = out_folder(args)
    os.makedirs(folder, exist_ok=True)
    ffmpeg = ffmpeg_exe() if args.command in ("video", "gif", "all", "readme") else None
    themes = [args.theme] if getattr(args, "theme", None) else list(THEMES)
    with MediaPage() as page:
        if args.command == "video":
            options = {k: getattr(args, k) for k in ("story", "length", "format", "theme", "lang")}
            if args.place:
                options["place"] = args.place
            _video(page, ffmpeg, folder, options, args.music)
        elif args.command == "gif":
            for theme in themes:
                _gif(page, ffmpeg, os.path.join(folder, gif_name(theme, args.lang)), theme, args.lang)
        elif args.command == "images":
            langs = [args.lang] if args.lang else list(LANGS)
            for image in page.info["statics"]:
                if args.group in (None, image["group"]):
                    for theme in themes:
                        for lang in langs:
                            _image(page, os.path.join(folder, image_name(image["name"], theme, lang)),
                                   image["name"], theme, lang)
        elif args.command == "readme":
            for theme in THEMES:
                _gif(page, ffmpeg, os.path.join(folder, f"coverage-{theme}.gif"), theme, "en")
                for view in README_VIEWS:
                    _image(page, os.path.join(folder, f"coverage-{view}-{theme}.png"), f"gh-{view}", theme, "en")
        else:
            _all(page, ffmpeg, folder, args)
    print(f"written to {folder}")


def _all(page, ffmpeg, folder, args):
    jobs = [("video", options, video_name(**options)) for options in all_videos()]
    jobs += [("gif", (theme, lang), gif_name(theme, lang)) for theme in THEMES for lang in LANGS]
    jobs += [("image", (s["name"], theme, lang), image_name(s["name"], theme, lang))
             for s in page.info["statics"] for theme in THEMES for lang in LANGS]
    started = time.monotonic()
    for k, (kind, what, name) in enumerate(jobs, 1):
        path = os.path.join(folder, name)
        label = f"[{k}/{len(jobs)}, {(time.monotonic() - started) / 60:.0f} min] "
        if os.path.exists(path) and not args.force:
            print(f"{label}{name}: exists", flush=True)
        elif kind == "video":
            _video(page, ffmpeg, folder, what, args.music, label)
        elif kind == "gif":
            _gif(page, ffmpeg, path, *what, label=label)
        else:
            _image(page, path, *what, label=label)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except Failure as e:
        print(f"coverage_media.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
