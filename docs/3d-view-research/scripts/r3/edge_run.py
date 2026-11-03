"""Serve a folder on 127.0.0.1 with a given Content-Security-Policy (and the other headers of web.py's
SECURITY_HEADERS), open one page in headless Edge with --dump-dom and print the text of <pre id="out">.
Usage: python -I edge_run.py <site dir> <page> <csp or "none"> <profile dir> [extra Edge flags ...]"""
import functools
import html
import http.server
import re
import subprocess
import sys
import os
import threading

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
site, page, csp, profile = sys.argv[1:5]
flags = sys.argv[5:]
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
         ".json": "application/json", ".css": "text/css", ".html": "text/html; charset=utf-8",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
         ".glb": "model/gltf-binary", ".bin": "application/octet-stream", ".ktx2": "image/ktx2"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        m = re.search(r"\.[A-Za-z0-9]+$", str(path))
        return TYPES.get(m.group(0).lower(), "application/octet-stream") if m else "application/octet-stream"

    def end_headers(self):
        if csp != "none":
            self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        if os.environ.get("ACAO"):
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin" if os.environ.get("ACAO") else "same-origin")
        self.send_header("Referrer-Policy", "strict-origin")
        self.send_header("Cache-Control", os.environ.get("CACHE_CONTROL", "no-store"))
        super().end_headers()

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=site))
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
real = os.environ.get("EDGE_TIMEOUT_MS")
timing = [f"--timeout={real}"] if real else ["--virtual-time-budget=60000"]
try:
    out = subprocess.run([EDGE, "--headless", f"--user-data-dir={profile}", "--no-first-run",
                          "--window-size=1280,800", *flags, *timing, "--dump-dom",
                          f"http://127.0.0.1:{port}/{page}"],
                         capture_output=True, text=True, encoding="utf-8", timeout=240).stdout
finally:
    server.shutdown()
m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
print(html.unescape(m.group(1)) if m else "NO RESULT; DOM starts: " + out[:500])
