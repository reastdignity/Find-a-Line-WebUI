"""`findaline.py view [RUN]` (docs/line-volume/spec-store.md 1.2, store wave 4): it opens a run in the local app,
the one on the port when that app holds the run, else an app it starts as `findaline.py web` does; an app on the
port that does not hold the run ends it with a message (never a second app). Tested on ports of their own with a
stub for the browser: never port 8765, never the user's browser."""

import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

import psutil
import pytest
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import clip_runs  # noqa: E402
import findaline  # noqa: E402
import old_runs  # noqa: E402
import web  # noqa: E402
from test_web import _playwright, _server  # noqa: E402

DEADLINE = 120  # s: the started app answering (an event awaited, never a fixed pause)


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """(data folder, run id) of a copy of the clip's run."""
    folder = clip_runs.view_clip(tmp_path_factory, "view-command")
    return folder.parent.parent, folder.name


@pytest.fixture(scope="module")
def app(clip):
    """The app over the clip's data folder on a port of its own (a server in a thread); yields its port."""
    with _server(clip[0]) as port:
        yield port


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _browser(monkeypatch) -> list:
    """webbrowser.open stubbed: the addresses it was asked to open."""
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *args, **kwargs: opened.append(url) or True)
    return opened


def _no_start(monkeypatch):
    def start(*args, **kwargs):
        raise AssertionError("view started an app")
    monkeypatch.setattr(web, "main", start)


def test_view_uses_the_app_that_holds_the_run(clip, app, monkeypatch, capsys):
    """The app on the port serves this run: the browser opens /#run=<id> there and nothing is started."""
    data, run_id = clip
    opened = _browser(monkeypatch)
    _no_start(monkeypatch)
    assert findaline.view_main([run_id, "--port", str(app), "--data-dir", str(data)]) == 0
    url = f"http://127.0.0.1:{app}/#run={urllib.parse.quote(run_id)}"
    assert opened == [url] and url in capsys.readouterr().out
    # a run folder for RUN, and no RUN at all (the newest run of the data folder): the same run
    assert findaline.view_main([str(data / "runs" / run_id), "--port", str(app)]) == 0
    assert findaline.view_main(["--port", str(app), "--data-dir", str(data)]) == 0
    assert opened == [url] * 3
    assert findaline.view_main([run_id, "--port", str(app), "--data-dir", str(data), "--no-browser"]) == 0
    assert opened == [url] * 3


def test_view_never_starts_a_second_app(clip, app, tmp_path, monkeypatch):
    """The app on the port answers but holds another data folder: view ends with the message, opens nothing, starts
    nothing; a run that is not there ends with its own message."""
    data, run_id = clip
    other = tmp_path / "other"
    (other / "runs").mkdir(parents=True)
    old_runs.copy_run(data / "runs" / run_id, other / "runs", "2026-11-17_120000_other_0123456789abcdef")
    opened = _browser(monkeypatch)
    _no_start(monkeypatch)
    with pytest.raises(SystemExit) as stop:
        findaline.view_main(["2026-11-17_120000_other_0123456789abcdef", "--port", str(app), "--data-dir", str(other)])
    assert str(stop.value) == (f"Port {app} answers, but not with this run: another Find-a-Line (another data folder) "
                               f"or another program. Stop it, or use --port.")
    with pytest.raises(SystemExit) as stop:
        findaline.view_main(["no-such-run", "--port", str(app), "--data-dir", str(data)])
    assert str(stop.value).startswith("No run no-such-run: give a run folder or the id of a run in ")
    outside = tmp_path / "loose"
    shutil.copytree(data / "runs" / run_id, outside)
    with pytest.raises(SystemExit) as stop:
        findaline.view_main([str(outside), "--port", str(app)])
    assert "is not in one" in str(stop.value)
    assert opened == []


def test_view_starts_the_app_when_none_answers(clip, monkeypatch):
    """Nothing on the port: view runs the app as findaline.py web does, on that port and data folder, with the
    browser sent to the run's result."""
    data, run_id = clip
    started = []
    monkeypatch.setattr(web, "main", lambda argv, open_path="/": started.append((argv, open_path)) or 0)
    port = _free_port()
    assert findaline.view_main([run_id, "--port", str(port), "--data-dir", str(data)]) == 0
    assert findaline.view_main([run_id, "--port", str(port), "--data-dir", str(data), "--no-browser"]) == 0
    path = f"/#run={urllib.parse.quote(run_id)}"
    assert started == [(["--port", str(port), "--data-dir", str(data)], path),
                       (["--port", str(port), "--data-dir", str(data), "--no-browser"], path)]


def test_view_runs_the_app(clip):
    """The real start: `findaline.py view <id> --no-browser` on a free port keeps the app running, which serves the
    run, and prints the run's address; stopped with its process tree."""
    data, run_id = clip
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "findaline.py", "view", run_id, "--port", str(port), "--data-dir", str(data), "--no-browser"],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(text) for text in process.stdout], daemon=True).start()
    session = requests.Session()
    session.trust_env = False
    try:
        line = lines.get(timeout=DEADLINE)  # the app's first line, once it is about to serve
        assert line.strip() == (f"Find-a-Line is running at http://127.0.0.1:{port}/#run={urllib.parse.quote(run_id)} "
                                f"(close this window or press Ctrl+C to stop it)"), line
        deadline = time.monotonic() + DEADLINE
        while True:
            try:
                answer = session.get(f"http://127.0.0.1:{port}/runs/{run_id}/run.json", timeout=5)
                break
            except requests.ConnectionError:
                assert time.monotonic() < deadline, "the app did not answer"
                time.sleep(0.2)
        assert answer.status_code == 200 and answer.json()["id"] == run_id
    finally:
        children = psutil.Process(process.pid).children(recursive=True)
        for p in [psutil.Process(process.pid), *children]:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        process.wait(30)
        process.stdout.close()
    assert not psutil.wait_procs(children, timeout=30)[1]  # none left alive


@pytest.mark.skipif(not _playwright(), reason="needs playwright (uv sync --group ui)")
def test_a_run_without_map_html_opens_in_the_app(clip, app, tmp_path):
    """Store U10 / Q2: a run saved with --no-html has no map.html, and the app's result route reads its store: the
    run opens there as one with a map (its count of spots shown), so view prints its line for every run."""
    from playwright.sync_api import sync_playwright
    data, run_id = clip
    bare = "2026-11-17_120001_bare_0123456789abcdef"
    old_runs.copy_run(data / "runs" / run_id, data / "runs", bare)
    (data / "runs" / bare / "map.html").unlink()
    import runs as rn
    rn.write_index(str(data / "runs"))
    counts = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for name in (run_id, bare):
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{app}/#run={urllib.parse.quote(name)}")
                page.wait_for_function("() => /\\d+ spots?/.test(document.querySelector('.r-summary-count')?.textContent"
                                       " || '')", timeout=60000)
                counts[name] = page.inner_text(".r-summary-count")
                page.close()
        finally:
            browser.close()
    assert counts[bare] == counts[run_id], counts
