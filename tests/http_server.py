"""A local HTTP server for the tests of the download code: static answers, recorded answers
(cassettes of tools/record_answers.py) and handlers, with HTTP range requests as GDAL's
/vsicurl/ sends them (one range, several in one request, beyond the end), and a log of
every request (its User-Agent, the requests nothing answered).

Standard library only (http.server in a thread on a free port), so requests, GDAL and
pyogrio read the same answers offline. The fixture `http_server` is in conftest.py.
"""

import gzip
import json
import mimetypes
import os
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

Key = Tuple[str, str, Tuple[Tuple[str, str], ...]]  # method, path, sorted query


@dataclass
class Answer:
    status: int = 200
    body: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Request:
    method: str
    path: str
    query: Tuple[Tuple[str, str], ...]
    headers: Dict[str, str]
    answered: bool = True

    @property
    def user_agent(self) -> Optional[str]:
        return self.headers.get("user-agent")


def key_of(method: str, url: str) -> Key:
    """What a request is matched by: its method (HEAD as GET), path and query, sorted."""
    parts = urlsplit(url)
    method = "GET" if method == "HEAD" else method
    return method, parts.path or "/", tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))


def _ranges(header: str, size: int) -> Optional[List[Tuple[int, int]]]:
    """The ranges of a Range header as (first, last) bytes; [] if none can be served; None if
    the header is not one of bytes."""
    match = re.fullmatch(r"\s*bytes=(.+)", header)
    if not match:
        return None
    found = []
    for part in match.group(1).split(","):
        first, _, last = part.strip().partition("-")
        if first == "":  # the last n bytes
            n = int(last)
            if n > 0:
                found.append((max(size - n, 0), size - 1))
            continue
        first = int(first)
        last = min(int(last), size - 1) if last else size - 1
        if first < size and first <= last:
            found.append((first, last))
    return found


class HttpServer:
    """The server: `base` is its address; answers are added by `add`, `add_folder`,
    `add_cassette` and `route`; `log` holds every request, `stray()` those nothing answered."""

    BOUNDARY = "findaline-test-boundary"

    def __init__(self):
        self.answers: Dict[Key, Answer] = {}
        self.routes: List[Tuple[str, Callable[[Request], Optional[Answer]]]] = []
        self.log: List[Request] = []
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                server._handle(self, head=False)

            def do_HEAD(self):
                server._handle(self, head=True)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path: str) -> str:
        return self.base + path

    # Answers

    def add(self, path: str, body: bytes, content_type: str = "application/octet-stream", status: int = 200,
            method: str = "GET", headers: Optional[Dict[str, str]] = None):
        """A fixed answer to path (with its query, if any: matched sorted)."""
        self.answers[key_of(method, path)] = Answer(status, body, {"Content-Type": content_type, **(headers or {})})

    def add_folder(self, prefix: str, folder: str, content_type: Optional[str] = None):
        """Every file under folder at prefix/<its relative path> (the type by its extension
        unless given)."""
        for root, _, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    rel = os.path.relpath(path, folder).replace(os.sep, "/")
                    kind = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
                    self.add(f"{prefix.rstrip('/')}/{rel}", f.read(), kind)

    def add_cassette(self, folder: str):
        """The answers recorded by tools/record_answers.py in folder (answers.json and the bodies),
        the recorded hosts (`hosts`) in their bodies and headers replaced by this server's base."""
        with open(os.path.join(folder, "answers.json"), encoding="utf-8") as f:
            cassette = json.load(f)
        for entry in cassette["answers"]:
            with open(os.path.join(folder, entry["body"]), "rb") as f:
                body = f.read()
            if entry["body"].endswith(".gz"):
                body = gzip.decompress(body)
            for host in cassette.get("hosts", []):
                body = body.replace(host.encode(), self.base.encode())
            self.answers[key_of(entry.get("method", "GET"), entry["url"])] = Answer(
                entry["status"], body, {"Content-Type": entry["content_type"]})

    def route(self, prefix: str, handler: Callable[[Request], Optional[Answer]]):
        """A handler of the paths starting with prefix (None from it: not found)."""
        self.routes.append((prefix, handler))

    # The log

    def requests(self, path_prefix: str = "") -> List[Request]:
        with self._lock:
            return [r for r in self.log if r.path.startswith(path_prefix)]

    def stray(self) -> List[Request]:
        """Requests that nothing answered (a 404 of the server itself)."""
        with self._lock:
            return [r for r in self.log if not r.answered]

    # Serving

    def _find(self, request: Request) -> Optional[Answer]:
        answer = self.answers.get((("GET" if request.method == "HEAD" else request.method), request.path,
                                   tuple(sorted(request.query))))
        if answer is not None:
            return answer
        for prefix, handler in self.routes:
            if request.path.startswith(prefix):
                answer = handler(request)
                if answer is not None:
                    return answer
        return None

    def _handle(self, handler: BaseHTTPRequestHandler, head: bool):
        parts = urlsplit(handler.path)
        request = Request(handler.command, parts.path, tuple(parse_qsl(parts.query, keep_blank_values=True)),
                          {k.lower(): v for k, v in handler.headers.items()})
        answer = self._find(request)
        request.answered = answer is not None
        with self._lock:
            self.log.append(request)
        if answer is None:
            answer = Answer(404, b"not found", {"Content-Type": "text/plain"})
        status, body, headers = answer.status, answer.body, dict(answer.headers)
        headers.setdefault("Content-Type", "application/octet-stream")
        if status == 200:
            headers["Accept-Ranges"] = "bytes"
            ranges = _ranges(request.headers["range"], len(body)) if "range" in request.headers else None
            if ranges == []:
                status, headers, body = 416, {"Content-Range": f"bytes */{len(body)}",
                                              "Content-Type": "text/plain"}, b""
            elif ranges and len(ranges) == 1:
                (first, last), = ranges
                headers["Content-Range"] = f"bytes {first}-{last}/{len(body)}"
                status, body = 206, body[first:last + 1]
            elif ranges:
                content_type = headers["Content-Type"]
                parts = []
                for first, last in ranges:
                    parts.append(f"--{self.BOUNDARY}\r\nContent-Type: {content_type}\r\n"
                                 f"Content-Range: bytes {first}-{last}/{len(body)}\r\n\r\n".encode()
                                 + body[first:last + 1] + b"\r\n")
                status, body = 206, b"".join(parts) + f"--{self.BOUNDARY}--\r\n".encode()
                headers["Content-Type"] = f"multipart/byteranges; boundary={self.BOUNDARY}"
        handler.send_response(status)
        for name, value in headers.items():
            handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        if not head:
            handler.wfile.write(body)
