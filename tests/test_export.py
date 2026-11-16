"""Exports made for each download, none kept (docs/line-volume/spec-store.md 1.2 and 1.4, store wave 3):
`findaline.py export`, the worker's quick kind `export` (jobs.quick_export into work/exports/, the clean-up of
that folder), the routes POST /api/runs/<run>/export and GET /api/runs/<run>/export/<name> of the local app (the
public site's access rules: tests/test_public.py), and a web process that never imports the store's code."""

import contextlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import jobs as jb  # noqa: E402
import web  # noqa: E402
from settings import Limits  # noqa: E402

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402

DATA = os.path.join(REPO, "tests", "data")
TOKEN = "test-token"
LOCAL = "http://127.0.0.1:8765"  # the local app's own host
HEADERS = {"x-findaline-token": TOKEN}
# The clip's search as tests/test_public.py's clip_run makes it (clip_runs: one search for both modules)
CLIP_ARGS = ["--elevation-file", os.path.join(DATA, "zabi_kon_nmt.tif"), "--northing", "254608", "--easting", "553966",
             "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
             "--nmpt", "off"]


@pytest.fixture(scope="module")
def clip_store(tmp_path_factory):
    """A data folder holding a run of the Żabi Koń clip with its store (computed once, offline): (data folder,
    run id). Tests take copies (copy_data)."""
    import clip_runs
    data = clip_runs.data_copy(tmp_path_factory, "export", CLIP_ARGS)
    run_id = next(d for d in os.listdir(data / "runs") if (data / "runs" / d / "run.json").is_file())
    assert (data / "runs" / run_id / "lines.arrow").is_file()
    return data, run_id


def copy_data(clip_store, tmp_path):
    """The clip's data folder copied into tmp_path/data (its runs only): (data folder, run id, run folder)."""
    data, run_id = clip_store
    target = tmp_path / "data"
    shutil.copytree(data / "runs" / run_id, target / "runs" / run_id)
    return target, run_id, target / "runs" / run_id


@contextlib.contextmanager
def quick_lane(data_dir, monkeypatch, public: bool = False, limits=None, worker: str = "lane-worker"):
    """The worker's quick lane (jobs.run_quick) in a thread of this process, with a lease (Jobs.register),
    until the block ends (its "worker" process is killed: the lane ends at its next look). The lane's globals
    are restored afterwards."""
    for name in ("SLOT_MEMORY", "PUBLIC_TEXTS", "LANE_LIMITS"):
        monkeypatch.setattr(jb, name, getattr(jb, name))
    jobs = jb.Jobs(str(data_dir), public)
    jobs.register(worker)
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    lane = threading.Thread(target=jb.run_quick, args=(str(data_dir), worker, parent.pid, limits, public),
                            name="lane", daemon=True)
    lane.start()
    try:
        yield jobs
    finally:
        parent.kill()
        parent.wait()
        lane.join(20)
        jobs.unregister(worker)


def exported(folder, fmt: str, tmp_path) -> bytes:
    """What linestore.export makes of a run folder now (its run.json as it is)."""
    import linestore
    out = tmp_path / f"expected.{fmt}"
    linestore.export(str(folder), fmt, str(out))
    return out.read_bytes()


def exports_of(data_dir) -> list:
    folder = os.path.join(str(data_dir), *jb.EXPORTS)
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


# --- The command line ---

def test_export_command(clip_store, tmp_path, monkeypatch, capsys):
    """`findaline.py export RUN --format csv|geojson [--out PATH]`: the run's own lines.csv / lines.geojson byte
    for byte, from the store; RUN a run id of --data-dir or a run folder; by default <run id>.<format> in the
    current folder; nothing written into the run folder."""
    import findaline
    data, run_id, folder = copy_data(clip_store, tmp_path)
    before = sorted(os.listdir(folder))
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    assert findaline.export_main([run_id, "--format", "csv", "--data-dir", str(data)]) == 0
    assert (here / f"{run_id}.csv").read_bytes() == (folder / "lines.csv").read_bytes()
    assert findaline.export_main([str(folder), "--format", "geojson"]) == 0  # a run folder
    assert (here / f"{run_id}.geojson").read_bytes() == (folder / "lines.geojson").read_bytes()
    out = tmp_path / "elsewhere" / "mine.csv"
    out.parent.mkdir()
    assert findaline.export_main([run_id, "--format", "csv", "--out", str(out), "--data-dir", str(data)]) == 0
    assert out.read_bytes() == (folder / "lines.csv").read_bytes() and os.listdir(out.parent) == ["mine.csv"]
    assert sorted(os.listdir(folder)) == before  # nothing in the run folder
    assert sorted(os.listdir(here)) == [f"{run_id}.csv", f"{run_id}.geojson"]  # no temporary folder left
    assert str(out) in capsys.readouterr().out


def test_export_command_refuses(clip_store, tmp_path, monkeypatch):
    """A run without a store ends with a plain message and exit status 1 (writing nothing), as does a run
    that is not there; `findaline.py export` reaches the command from the script's own entry."""
    import findaline
    data, run_id, folder = copy_data(clip_store, tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        findaline.export_main(["no-such-run", "--format", "csv", "--data-dir", str(data)])
    assert "No run no-such-run" in str(stopped.value.code)
    os.remove(folder / "lines.arrow")
    with pytest.raises(SystemExit) as stopped:
        findaline.export_main([run_id, "--format", "csv", "--data-dir", str(data)])
    assert "has no store" in str(stopped.value.code) and not (tmp_path / f"{run_id}.csv").exists()
    result = subprocess.run([sys.executable, os.path.join(REPO, "findaline.py"), "export", str(folder), "--format",
                             "geojson"], cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert result.returncode == 1 and "has no store" in result.stderr, result.stdout + result.stderr
    assert not (tmp_path / f"{run_id}.geojson").exists()


# --- The worker's quick kind "export" ---

def test_quick_export_writes_once_and_cleans_up(clip_store, tmp_path, monkeypatch):
    """jobs.quick_export writes work/exports/<run id>-<token>.<extension> (the token of 16 random bytes,
    URL-safe) with the run's own text and answers its name; files and folders of that folder older than
    EXPORT_KEEP_SECONDS go at the worker's start and before each export, younger ones stay; below the
    server's free_disk_gb_min (LANE_LIMITS, whatever the task's limits) and for a run without a store it
    refuses with the code export_failed."""
    from jobs import QuotaExceeded
    from messages import UserError
    data, run_id, folder = copy_data(clip_store, tmp_path)
    monkeypatch.setattr(jb, "LANE_LIMITS", None)
    names = [jb.quick_export(str(data), {"run": run_id, "format": fmt}, None)["name"] for fmt in ("csv", "geojson")]
    assert all(web.EXPORT_NAME.fullmatch(name) for name in names) and names[0][:22] != names[1][:22]
    exports = os.path.join(str(data), *jb.EXPORTS)
    assert exports_of(data) == sorted(f"{run_id}-{name}" for name in names)
    with open(os.path.join(exports, f"{run_id}-{names[0]}"), "rb") as f:
        assert f.read() == (folder / "lines.csv").read_bytes()
    with open(os.path.join(exports, f"{run_id}-{names[1]}"), "rb") as f:
        assert f.read() == (folder / "lines.geojson").read_bytes()

    old = time.time() - jb.EXPORT_KEEP_SECONDS - 60
    for name in ("stale.csv", "taken.sending"):
        with open(os.path.join(exports, name), "w") as f:
            f.write("x")
        os.utime(os.path.join(exports, name), (old, old))
    os.makedirs(os.path.join(exports, ".export-left"))
    os.utime(os.path.join(exports, ".export-left"), (old, old))
    third = jb.quick_export(str(data), {"run": run_id, "format": "csv"}, None)["name"]
    assert exports_of(data) == sorted(f"{run_id}-{name}" for name in names + [third])

    with open(os.path.join(exports, "stale.csv"), "w") as f:
        f.write("x")
    os.utime(os.path.join(exports, "stale.csv"), (old, old))
    scheduler = jb.Scheduler(jb.Jobs(str(data)), worker_id="w-start", limits=Limits())
    scheduler._begin()  # the worker's start
    scheduler.jobs.unregister("w-start")
    assert "stale.csv" not in exports_of(data) and len(exports_of(data)) == 3

    monkeypatch.setattr(jb, "LANE_LIMITS", Limits(free_disk_gb_min=1e9))
    with pytest.raises(QuotaExceeded) as refused:
        jb.quick_export(str(data), {"run": run_id, "format": "csv"}, None)  # a user without limits: still
    assert refused.value.status == 503 and refused.value.code == "export_failed"
    monkeypatch.setattr(jb, "LANE_LIMITS", None)
    os.remove(folder / "lines.arrow")
    with pytest.raises(UserError) as refused:
        jb.quick_export(str(data), {"run": run_id, "format": "csv"}, None)
    assert refused.value.code == "export_failed"
    with pytest.raises(ValueError):
        jb.quick_export(str(data), {"run": "../x", "format": "csv"}, None)
    with pytest.raises(ValueError):
        jb.quick_export(str(data), {"run": run_id, "format": "kml"}, None)
    assert len(exports_of(data)) == 3


# --- The routes of the local app ---

def test_export_routes_of_the_local_app(clip_store, tmp_path, monkeypatch):
    """POST /api/runs/<run>/export asks the quick lane and answers the download's address; GET sends the file
    as an attachment named after the run (its name, else its id), with its media type, once: the file is
    deleted and a second request answers 404; a Range request gets the whole file. 503 without a worker; the
    format checked; a run without a store refused (409 export_failed) before the lane is asked; other names
    and other runs' exports answer 404 and leave the file."""
    data, run_id, folder = copy_data(clip_store, tmp_path)
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    meta["name"] = 'Żabi "Koń"/1'
    (folder / "run.json").write_text(json.dumps(meta), "utf-8")
    shutil.copytree(folder, data / "runs" / "other-run")
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client:
        post = lambda run, body: client.post(f"/api/runs/{run}/export", json=body, headers=HEADERS)  # noqa: E731
        assert post(run_id, {"format": "csv"}).status_code == 503  # no worker
        assert post(run_id, {"format": "kml"}).status_code == 400 and post(run_id, {}).status_code == 400
        assert post("no-such-run", {"format": "csv"}).status_code == 404
        assert client.post(f"/api/runs/{run_id}/export", json={"format": "csv"}).status_code == 403  # no token
        with quick_lane(data, monkeypatch):
            for fmt, kept, media in (("csv", "lines.csv", "text/csv; charset=utf-8"),
                                     ("geojson", "lines.geojson", "application/geo+json")):
                if fmt == "csv":  # lines.geojson's "findaline" part names the run: here renamed (run.json)
                    assert exported(folder, fmt, tmp_path) == (folder / kept).read_bytes()
                answer = post(run_id, {"format": fmt})
                assert answer.status_code == 200, answer.text
                url = answer.json()["url"]
                assert url.startswith(f"/api/runs/{run_id}/export/") and url.endswith(f".{fmt}")
                name = url.rsplit("/", 1)[1]
                assert client.get(f"/api/runs/other-run/export/{name}").status_code == 404  # another run's
                assert client.head(url).status_code == 405 and exports_of(data) == [f"{run_id}-{name}"]
                sent = client.get(url, headers={"range": "bytes=0-9"})
                assert sent.status_code == 200 and sent.content == exported(folder, fmt, tmp_path)
                assert sent.headers["content-type"] == media
                assert sent.headers["content-disposition"] == (
                    f"attachment; filename=\"Zabi _Kon__1.{fmt}\"; filename*=UTF-8''"
                    f"%C5%BBabi%20_Ko%C5%84__1.{fmt}")
                assert exports_of(data) == [] and client.get(url).status_code == 404  # once
            os.remove(folder / "lines.arrow")
            meta.pop("store")
            (folder / "run.json").write_text(json.dumps(meta), "utf-8")
            refused = post(run_id, {"format": "csv"})
            assert refused.status_code == 409 and refused.json()["detail"]["code"] == "export_failed"
            other = post("other-run", {"format": "geojson"}).json()["url"]
        name = other.rsplit("/", 1)[1]
        for path in (f"/api/runs/{run_id}/export/{name}", f"/api/runs/other-run/export/x{name[1:]}",
                     f"/api/runs/other-run/export/{name[:-8]}.csv", "/api/runs/other-run/export/..%2Fjobs.sqlite",
                     f"/api/runs/other-run/export/{name}.sending"):
            assert client.get(path).status_code == 404, path
        assert exports_of(data) == [f"other-run-{name}"]
        nameless = json.loads((data / "runs" / "other-run" / "run.json").read_text("utf-8"))
        nameless.pop("name")
        (data / "runs" / "other-run" / "run.json").write_text(json.dumps(nameless), "utf-8")
        sent = client.get(other)
        assert sent.headers["content-disposition"] == (
            "attachment; filename=\"other-run.geojson\"; filename*=UTF-8''other-run.geojson")


def test_content_disposition_names():
    """The download's name: UTF-8 in filename*, an ASCII form in filename, never a character a file name or
    the quoted string cannot hold; the fallback when no name is left."""
    assert web.content_disposition("Dolina Kobylańska.csv", "r.csv") == (
        "attachment; filename=\"Dolina Kobylanska.csv\"; filename*=UTF-8''Dolina%20Kobyla%C5%84ska.csv")
    assert web.content_disposition("Łódź.csv", "r.csv") == (
        "attachment; filename=\"odz.csv\"; filename*=UTF-8''%C5%81%C3%B3d%C5%BA.csv")
    assert web.content_disposition("ŁŁ.csv", "r.csv").startswith("attachment; filename=\"r.csv\"; ")
    assert web.content_disposition('a\\b\r\n"c".geojson', "r.geojson") == (
        "attachment; filename=\"a_b___c_.geojson\"; filename*=UTF-8''a_b___c_.geojson")


def _server(data_dir):
    """The local app on a real server (uvicorn in a thread, behind its guard middleware); yields its port."""
    import socket

    import uvicorn

    @contextlib.contextmanager
    def serve():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        app = web.create_app(str(data_dir), token=TOKEN, port=port, start_scheduler=False)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 30
            while not server.started:
                assert time.monotonic() < deadline, "the server did not start"
                time.sleep(0.05)
            yield port
        finally:
            server.should_exit = True
            thread.join(10)
    return serve()


def test_export_deleted_when_the_client_breaks_off(clip_store, tmp_path):
    """A download the browser breaks off deletes the export as a whole one does (the sending is cancelled,
    the file closed and deleted): a later request answers 404 and the folder is empty."""
    data, run_id, _ = copy_data(clip_store, tmp_path)
    exports = os.path.join(str(data), *jb.EXPORTS)
    os.makedirs(exports)
    name = "A" * 22 + ".csv"
    with open(os.path.join(exports, f"{run_id}-{name}"), "wb") as f:
        f.write(os.urandom(64 << 20))  # far more than the sockets' buffers hold
    with _server(data) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        connection.request("GET", f"/api/runs/{run_id}/export/{name}", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        assert response.status == 200 and len(response.read(1 << 16)) == 1 << 16
        connection.sock.close()  # broken off after 64 KB
        connection.close()
        deadline = time.monotonic() + 30
        while exports_of(data) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert exports_of(data) == []
        again = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        again.request("GET", f"/api/runs/{run_id}/export/{name}", headers={"Host": f"127.0.0.1:{port}"})
        assert again.getresponse().status == 404
        again.close()


def test_export_never_counts_in_a_run_or_quota(clip_store, tmp_path, monkeypatch):
    """An export lies in work/exports/, not in the run folder: the runs row's bytes, the user's runs in
    Jobs.usage and the run folder's own files stay as they were while it waits and after it is sent."""
    data, run_id, folder = copy_data(clip_store, tmp_path)
    jobs = jb.Jobs(str(data))
    jobs.add_run(run_id, None, 12345)
    usage = jobs.usage(None, None)
    files = sorted(os.listdir(folder))
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL) as client, quick_lane(data, monkeypatch):
        url = client.post(f"/api/runs/{run_id}/export", json={"format": "geojson"}, headers=HEADERS).json()["url"]
        assert jobs.run(run_id)["bytes"] == 12345 and jobs.usage(None, None) == usage
        assert sorted(os.listdir(folder)) == files
        assert client.get(url).status_code == 200
    assert jobs.run(run_id)["bytes"] == 12345 and jobs.usage(None, None) == usage


def test_web_process_never_imports_the_store(clip_store, tmp_path):
    """Both export routes in a web process of its own (the local app, no worker: the POST answers 503, the
    GET sends an export the test put there) load neither linestore, pyarrow, search, linesearch nor numba."""
    data, run_id, _ = copy_data(clip_store, tmp_path)
    exports = os.path.join(str(data), *jb.EXPORTS)
    os.makedirs(exports)
    name = "B" * 22 + ".geojson"
    with open(os.path.join(exports, f"{run_id}-{name}"), "w") as f:
        f.write("{}")
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(data)!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            f"a = c.post('/api/runs/{run_id}/export', json={{'format': 'csv'}}, headers={{'x-findaline-token': 't'}})\n"
            f"b = c.get('/api/runs/{run_id}/export/{name}')\n"
            "print(json.dumps([a.status_code, b.status_code, b.text, sorted(m for m in sys.modules if m.split('.')[0] in "
            "('numba', 'linesearch', 'search', 'linestore', 'pyarrow'))]))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [503, 200, "{}", []]
