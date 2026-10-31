"""Fixtures shared by the test modules."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http_server import HttpServer  # noqa: E402


@pytest.fixture
def http_server(monkeypatch):
    """A local HTTP server (tests/http_server.py); requests to it never go through a proxy
    (some tests set HTTP_PROXY to a dead one to keep the code offline)."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = HttpServer()
    yield server
    server.close()
