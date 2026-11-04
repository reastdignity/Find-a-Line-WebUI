"""Fixtures shared by the test modules."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The app's modules for the fixtures below, also when only a module that imports none of them runs
# (the CI's monitoring job: tests/test_monitoring.py alone)
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from http_server import HttpServer  # noqa: E402

# The processes the tests start write their output as they would for a user: in the code page when it is
# redirected, until the entry point sets UTF-8 itself (progress.utf8_output; tests/test_entry_points.py).
# A PYTHONIOENCODING of the calling shell hid the quick lane's "km²" from the tests (4901833)
for _name in ("PYTHONIOENCODING", "PYTHONUTF8"):
    os.environ.pop(_name, None)


@pytest.fixture
def http_server(monkeypatch):
    """A local HTTP server (tests/http_server.py); requests to it never go through a proxy
    (some tests set HTTP_PROXY to a dead one to keep the code offline)."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = HttpServer()
    yield server
    server.close()


@pytest.fixture(autouse=True)
def no_host_rates(request, monkeypatch):
    """No waiting for the turns of sources.net.rate_turn (HOST_RATES_OF emptied), so a test that
    names a real host with a rate (the probe's swisstopo addresses) neither waits nor writes to the
    machine's shared bucket; tests/test_rates.py keeps the rates and moves the bucket into tmp_path."""
    if request.module.__name__.endswith("test_rates"):
        yield
        return
    from sources import net
    monkeypatch.setattr(net, "HOST_RATES_OF", {})
    yield


@pytest.fixture(autouse=True)
def no_service_counts():
    """A test that calls a phase of the worker in the test's process (jobs.run_phase) turns the
    counting of servicecounts on: it is off again after every test, so no later test counts into
    a data folder that is gone."""
    yield
    module = sys.modules.get("servicecounts")
    if module is not None:
        module.disable()
