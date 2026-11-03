"""tools/coverage_media.py: its options, names and ffmpeg commands, the check of what it wrote (a tiny MP4 and
GIF made by imageio-ffmpeg's binary from a few numpy frames), the poster's PDF, and one image and a second of a
story rendered end to end (skipped without Playwright and its Chromium, Node or viewer/node_modules: CI installs
no group `ui`)."""

import importlib.util
import io
import os
import re
import shutil
import struct
import sys
import wave
import zlib

import numpy as np
import pytest
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import coverage_media as cm  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(importlib.util.find_spec("imageio_ffmpeg") is None,
                                  reason="imageio-ffmpeg is in the group ui")


def _png(rgb: np.ndarray) -> bytes:
    out = io.BytesIO()
    Image.fromarray(rgb).save(out, "PNG")
    return out.getvalue()


def _frames(n, width=64, height=48):
    """n PNGs of a gradient with a moving bar (RGBA, as the canvas gives them)."""
    y, x = np.mgrid[0:height, 0:width]
    for i in range(n):
        rgba = np.zeros((height, width, 4), np.uint8)
        rgba[..., 0] = x * 255 // width
        rgba[..., 1] = y * 255 // height
        rgba[..., 2] = np.where(abs(x - 8 * i) < 4, 255, 40)
        rgba[..., 3] = 255
        yield _png(rgba)


def test_arguments():
    args = cm.parse_args(["video", "--story", "mix", "--length", "long", "--format", "9x16", "--theme", "dark",
                          "--lang", "pl", "--place", "matterhorn"])
    assert (args.story, args.length, args.format, args.theme, args.lang, args.place) == \
        ("mix", "long", "9x16", "dark", "pl", "matterhorn")
    assert args.music is None
    assert cm.parse_args(["--all", "--force"]).command == "all"
    assert cm.parse_args(["gif"]).lang == "en" and cm.parse_args(["gif"]).theme is None
    assert cm.parse_args(["images", "--group", "poster"]).group == "poster"
    for wrong in (["video", "--story", "mix"],                        # options missing
                  ["video", "--story", "x", "--length", "long", "--format", "4x5", "--theme", "dark", "--lang", "en"],
                  ["images", "--group", "flyer"],
                  ["all", "--music", os.path.join(REPO, "no-such-track.mp3")]):
        with pytest.raises(SystemExit):
            cm.parse_args(wrong)
    assert cm.out_folder(cm.parse_args(["readme"])) == os.path.join(REPO, "docs", "images")
    assert cm.out_folder(cm.parse_args(["gif", "--data-dir", "D"])) == os.path.join(os.path.abspath("D"), "work",
                                                                                    "coverage-media")


def test_the_96_videos_and_their_names():
    videos = cm.all_videos()
    assert len(videos) == 96
    names = {cm.video_name(**v) for v in videos}
    assert len(names) == 96
    assert "coverage-contrast-long-4x5-light-en.mp4" in names
    assert "coverage-timeline-short-9x16-dark-pl.mp4" in names
    assert cm.video_name("fill", "medium", "4x5", "dark", "en", place="aoraki") == \
        "coverage-fill-medium-4x5-dark-en-aoraki.mp4"
    assert cm.gif_name("dark", "en") == "coverage-dark-en.gif"
    assert cm.image_name("poster", "light", "pl", "pdf") == "poster-light-pl.pdf"
    assert cm.places()[0] == "zabi_kon" and len(cm.places()) == 9


def test_frame_times():
    times = cm.frame_times(26, 30)
    assert len(times) == 780 and times[0] == 0 and times[-1] == 779 / 30
    assert len(cm.frame_times(9, 15)) == 135


def test_ffmpeg_commands():
    cmd = cm.video_command("ffmpeg", "out.mp4", 26)
    text = " ".join(cmd)
    for part in ("-f image2pipe -framerate 30 -c:v png -i -", "-c:v libx264", "-crf 18", "-pix_fmt yuv420p",
                 "-movflags +faststart", "-t 26", "-an", "out_color_matrix=bt709"):
        assert part in text
    assert cmd[-1] == "out.mp4" and "aac" not in text
    music = " ".join(cm.video_command("ffmpeg", "out.mp4", 18, "track.mp3"))
    for part in ("-i track.mp3", "-map 1:a:0", "afade=t=out:st=17:d=1", "-c:a aac", "-t 18"):
        assert part in music
    assert "-an" not in music.split()
    gif = " ".join(cm.gif_command("ffmpeg", "out.gif", 15, 900))
    for part in ("-framerate 15", "scale=900:-2", "palettegen", "paletteuse", "-loop 0"):
        assert part in gif


PROBE = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.mp4':
  Duration: 00:00:26.00, start: 0.000000, bitrate: 1441 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 1080x1920, 1291 kb/s, 30 fps, 30 tbr, 15360 tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 139 kb/s (default)
frame=  400 fps=0.0 q=-1.0 size=N/A time=00:00:13.30\rframe=  780 fps=0.0 q=-1.0 Lsize=N/A time=00:00:25.97
"""


def test_parse_probe():
    info = cm.parse_probe(PROBE)
    assert info == {"audio": ["aac"], "codec": "h264", "pix_fmt": "yuv420p", "width": 1080, "height": 1920,
                    "fps": 30.0, "duration": 26.0, "frames": 780}
    assert cm.parse_probe("garbage") == {"audio": [], "fps": None, "duration": None, "frames": None}


def _encode(cmd, frames):
    encoder = cm.Encoder(cmd)
    for png in frames:
        encoder.write(png)
    encoder.close()


@needs_ffmpeg
def test_encoded_video_is_checked(tmp_path):
    ffmpeg = cm.ffmpeg_exe()
    path = str(tmp_path / "v.mp4")
    _encode(cm.video_command(ffmpeg, path, 12 / 30), _frames(12))
    info = cm.check_media(ffmpeg, path, codec="h264", width=64, height=48, frames=12, fps=30, pix_fmt="yuv420p")
    assert info["frames"] == 12 and info["audio"] == [] and info["bytes"] > 0
    for wrong in ({"frames": 20}, {"width": 32}, {"audio": True}, {"codec": "hevc"}):
        with pytest.raises(cm.Failure):
            cm.check_media(ffmpeg, path, **{"codec": "h264", "width": 64, "height": 48, "frames": 12, "fps": 30,
                                            "pix_fmt": "yuv420p", **wrong})
    with pytest.raises(cm.Failure):
        cm.check_media(ffmpeg, str(tmp_path / "missing.mp4"), codec="h264", width=64, height=48, frames=12)

    # with music: a 3 s tone cut to the video's 0.4 s, AAC
    track = str(tmp_path / "tone.wav")
    with wave.open(track, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(44100)
        w.writeframes((np.sin(np.arange(3 * 44100) * 0.06) * 8000).astype("<i2").tobytes())
    music = str(tmp_path / "m.mp4")
    _encode(cm.video_command(ffmpeg, music, 12 / 30, track), _frames(12))
    info = cm.check_media(ffmpeg, music, codec="h264", width=64, height=48, frames=12, fps=30, pix_fmt="yuv420p",
                          audio=True)
    assert info["audio"] == ["aac"]


@needs_ffmpeg
def test_encoded_gif_and_a_failing_ffmpeg(tmp_path):
    ffmpeg = cm.ffmpeg_exe()
    path = str(tmp_path / "g.gif")
    _encode(cm.gif_command(ffmpeg, path, 15, 32), _frames(6))
    assert cm.check_media(ffmpeg, path, codec="gif", width=32, height=24, frames=6)["frames"] == 6
    with pytest.raises(cm.Failure, match="ffmpeg ended"):
        _encode(cm.video_command(ffmpeg, str(tmp_path / "x.mp4"), 1), [b"not a png" * 1000])


def test_png_and_poster_pdf():
    rgba = np.zeros((40, 30, 4), np.uint8)
    rgba[..., 0], rgba[..., 3] = np.arange(30, dtype=np.uint8) * 8, 255
    png = cm.png_file(_png(rgba), 300)
    with Image.open(io.BytesIO(png)) as im:
        assert im.mode == "RGB" and im.size == (30, 40)
        assert tuple(round(d) for d in im.info["dpi"]) == (300, 300)
        assert np.array_equal(np.asarray(im), rgba[..., :3])
    rgba[0, 0, 3] = 0
    with pytest.raises(cm.Failure, match="transparent"):
        cm.png_file(_png(rgba))

    pdf = cm.pdf_of_png(png, 300)
    assert pdf.startswith(b"%PDF-1.4") and pdf.endswith(b"%%EOF\n")
    assert b"/MediaBox [0 0 7.2000 9.6000]" in pdf      # 30 x 40 px at 300 dpi in points
    # the xref's offsets point at their objects, startxref at the xref
    xref = int(re.search(rb"startxref\n(\d+)", pdf)[1])
    assert pdf[xref:xref + 4] == b"xref"
    for number, offset in enumerate(re.findall(rb"(\d{10}) 00000 n", pdf), 1):
        assert pdf[int(offset):].startswith(b"%d 0 obj" % number)
    # the image's data are the PNG's, which inflate to its filtered rows
    idat = b"".join(body for kind, body in cm.png_chunks(png) if kind == b"IDAT")
    assert idat in pdf and len(zlib.decompress(idat)) == 40 * (1 + 30 * 3)
    # A3 at 300 dpi
    width, height = 3508 * 72 / 300, 4961 * 72 / 300
    assert (round(width / 72 * 25.4), round(height / 72 * 25.4)) == (297, 420)
    with pytest.raises(cm.Failure):
        cm.pdf_of_png(_png(np.zeros((4, 4, 4), np.uint8)), 300)    # RGBA


def _browser_ready() -> bool:
    if importlib.util.find_spec("playwright") is None or importlib.util.find_spec("imageio_ffmpeg") is None:
        return False
    if not shutil.which("node") or not os.path.isdir(os.path.join(REPO, "viewer", "node_modules", "esbuild")):
        return False
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return os.path.exists(p.chromium.executable_path)


@pytest.mark.skipif(not _browser_ready(), reason="needs the group ui, Playwright's Chromium and viewer/node_modules")
def test_render_end_to_end(tmp_path):
    ffmpeg = cm.ffmpeg_exe()
    with cm.MediaPage() as page:
        assert page.info["places"] == cm.places()
        info = cm.write_image(page, str(tmp_path / "gh-oceania.png"), "gh-oceania", "dark", "pl")
        assert info["bytes"] > 10_000
        with Image.open(tmp_path / "gh-oceania.png") as im:
            assert im.size == (1600, 800) and len(im.getcolors(1 << 20) or range(1000)) > 50
        path = str(tmp_path / "s.mp4")
        video = cm.write_video(page, ffmpeg, path, {"story": "contrast", "length": "short", "format": "4x5",
                                                    "theme": "light", "lang": "en"}, seconds=1)
        assert video["frames"] == 30 and (video["width"], video["height"]) == (1080, 1350)
        # the same frame twice: the drawing has no clock
        page.setup({"kind": "story", "story": "contrast", "length": "short", "format": "4x5", "theme": "light",
                    "lang": "en"})
        assert page.frame(0.5) == page.frame(0.5)
    assert sorted(os.listdir(tmp_path)) == ["gh-oceania.png", "s.mp4"]


def test_pdf_header_struct():
    """png_chunks reads the IHDR the PDF needs."""
    png = cm.png_file(_png(np.full((3, 5, 4), 255, np.uint8)))
    kind, body = next(cm.png_chunks(png))
    assert kind == b"IHDR" and struct.unpack(">II", body[:8]) == (5, 3)
