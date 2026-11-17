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
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / f"expected.{fmt}"
    linestore.export(str(folder), fmt, str(out))
    return out.read_bytes()


def exports_of(data_dir) -> list:
    folder = os.path.join(str(data_dir), *jb.EXPORTS)
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


# --- The command line ---

def test_export_command(clip_store, tmp_path, monkeypatch, capsys):
    """`findaline.py export RUN --format csv|geojson [--out PATH]`: linestore.export's text of the run's store byte
    for byte (the run's own lines.csv / lines.geojson before store wave 4: test_linestore keeps that equality); RUN a
    run id of --data-dir or a run folder; by default <run id>.<format> in the
    current folder; nothing written into the run folder."""
    import findaline
    data, run_id, folder = copy_data(clip_store, tmp_path)
    expected = {fmt: exported(folder, fmt, tmp_path / "expected") for fmt in ("csv", "geojson")}
    before = sorted(os.listdir(folder))
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    assert findaline.export_main([run_id, "--format", "csv", "--data-dir", str(data)]) == 0
    assert (here / f"{run_id}.csv").read_bytes() == expected["csv"]
    assert findaline.export_main([str(folder), "--format", "geojson"]) == 0  # a run folder
    assert (here / f"{run_id}.geojson").read_bytes() == expected["geojson"]
    out = tmp_path / "elsewhere" / "mine.csv"
    out.parent.mkdir()
    assert findaline.export_main([run_id, "--format", "csv", "--out", str(out), "--data-dir", str(data)]) == 0
    assert out.read_bytes() == expected["csv"] and os.listdir(out.parent) == ["mine.csv"]
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


def test_export_command_refuses_its_output(clip_store, tmp_path, monkeypatch):
    """An --out that names a folder, a folder that does not exist, or a place in the run folder (also the default
    name when the current folder is the run folder) is refused with a message and exit status 1 before any work
    (linestore.export is never called), and nothing is written; an existing file is overwritten."""
    import findaline
    import linestore
    data, run_id, folder = copy_data(clip_store, tmp_path)
    expected = exported(folder, "csv", tmp_path / "expected")
    before = sorted(os.listdir(folder))
    calls = []
    real_export = linestore.export
    monkeypatch.setattr(linestore, "export", lambda *a: calls.append(a) or real_export(*a))
    args = lambda *extra: [run_id, "--format", "csv", "--data-dir", str(data), *extra]  # noqa: E731
    (tmp_path / "a-folder").mkdir()
    for extra, said in ((["--out", str(tmp_path / "a-folder")], "names a folder"),
                        (["--out", str(tmp_path / "missing" / "x.csv")], "No folder"),
                        (["--out", str(folder / "x.csv")], "is in the run folder"),
                        (["--out", str(folder / "sub" / "x.csv")], "No folder")):
        with pytest.raises(SystemExit) as stopped:
            findaline.export_main(args(*extra))
        assert said in str(stopped.value.code), (extra, stopped.value.code)
    monkeypatch.chdir(folder)
    with pytest.raises(SystemExit) as stopped:
        findaline.export_main(args())  # the default <run id>.csv in the current folder: the run folder
    assert "is in the run folder" in str(stopped.value.code)
    assert calls == [] and sorted(os.listdir(folder)) == before and os.listdir(tmp_path / "a-folder") == []
    old = tmp_path / "old.csv"
    old.write_text("old")
    assert findaline.export_main(args("--out", str(old))) == 0 and old.read_bytes() == expected
    help_text = subprocess.run([sys.executable, os.path.join(REPO, "findaline.py"), "export", "--help"],
                               capture_output=True, text=True, timeout=300).stdout
    assert "existing file is overwritten" in " ".join(help_text.split())


def test_regression_takes_the_export(clip_store, tmp_path):
    """tests/regression.py: check_export gives the CSV the export makes and no problem (since store wave 4 a run
    keeps no lines.csv to compare it with), nothing written into or beside the run folder; measure's checksum and
    counts are the export's; a run without a store is a problem and has no checksum."""
    import hashlib
    import regression
    data, run_id, folder = copy_data(clip_store, tmp_path)
    before = sorted(os.listdir(folder.parent))
    table, problems = regression.check_export(str(folder))
    assert table == exported(folder, "csv", tmp_path / "expected") and problems == []
    assert sorted(os.listdir(folder.parent)) == before
    found = regression.measure("", str(data / "runs"))
    assert found["csv_sha256"] == hashlib.sha256(table).hexdigest() and found["store_problems"] == []
    assert found["lines"] == json.loads((folder / "run.json").read_text("utf-8"))["summary"]["lines"]
    assert found.pop("table") == table
    os.remove(folder / "lines.arrow")
    assert regression.check_export(str(folder)) == (None, ["the run has no store (lines.arrow)"])
    found = regression.measure("", str(data / "runs"))
    assert "csv_sha256" not in found and found["store_problems"] == ["the run has no store (lines.arrow)"]


# --- The worker's quick kind "export" ---

def test_quick_export_writes_once_and_cleans_up(clip_store, tmp_path, monkeypatch):
    """jobs.quick_export writes work/exports/<run id>-<token>.<extension> (the token of 16 random bytes,
    URL-safe) with the run's own text and answers its name; files and folders of that folder older than
    EXPORT_KEEP_SECONDS go at the worker's start and before each export, younger ones stay; below the
    server's free_disk_gb_min once the file is written (LANE_LIMITS, whatever the task's limits; the file's size
    estimated from the store's lines) it refuses with export_disk_full, for a run without a store with
    export_failed."""
    from jobs import QuotaExceeded
    from messages import UserError
    data, run_id, folder = copy_data(clip_store, tmp_path)
    monkeypatch.setattr(jb, "LANE_LIMITS", None)
    names = [jb.quick_export(str(data), {"run": run_id, "format": fmt}, None)["name"] for fmt in ("csv", "geojson")]
    assert all(web.EXPORT_NAME.fullmatch(name) for name in names) and names[0][:22] != names[1][:22]
    exports = os.path.join(str(data), *jb.EXPORTS)
    assert exports_of(data) == sorted(f"{run_id}-{name}" for name in names)
    with open(os.path.join(exports, f"{run_id}-{names[0]}"), "rb") as f:
        assert f.read() == exported(folder, "csv", tmp_path / "expected")
    with open(os.path.join(exports, f"{run_id}-{names[1]}"), "rb") as f:
        assert f.read() == exported(folder, "geojson", tmp_path / "expected")

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

    meta = json.loads((folder / "run.json").read_text("utf-8"))
    lines = meta["store"]["lines"]
    assert all(jb.export_bytes(str(folder), fmt) == lines * jb.EXPORT_LINE_BYTES[fmt] > 0 for fmt in ("csv", "geojson"))
    assert all(jb.EXPORT_LINE_BYTES[fmt] * lines >= len(exported(folder, fmt, tmp_path / "expected"))
               for fmt in ("csv", "geojson"))  # an upper bound here too
    free = 50e9  # the disk as the guard sees it
    monkeypatch.setattr(jb.shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100e9, 50e9, free))
    size = jb.export_bytes(str(folder), "geojson")
    monkeypatch.setattr(jb, "LANE_LIMITS", Limits(free_disk_gb_min=(free - size) / 1e9 + 1e-6))  # just over after
    with pytest.raises(QuotaExceeded) as refused:
        jb.quick_export(str(data), {"run": run_id, "format": "geojson"}, None)  # a user without limits: still
    assert refused.value.status == 503 and refused.value.code == "export_disk_full"
    monkeypatch.setattr(jb, "LANE_LIMITS", Limits(free_disk_gb_min=(free - size) / 1e9 - 1e-3))  # room for it
    fourth = jb.quick_export(str(data), {"run": run_id, "format": "geojson"}, None)["name"]
    os.remove(os.path.join(exports, f"{run_id}-{fourth}"))
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


def _old_and_young_exports(data_dir) -> str:
    """Three files in work/exports/: an export and a broken-off sending's leftover just past export_sweep_age(),
    and an export 30 s short of it, which stays; the young one's name."""
    exports = os.path.join(str(data_dir), *jb.EXPORTS)
    os.makedirs(exports, exist_ok=True)
    old, young = time.time() - jb.export_sweep_age() - 5, time.time() - jb.export_sweep_age() + 30
    for name, when in (("r-" + "A" * 22 + ".csv", old), ("r-" + "B" * 22 + ".csv.0a1b2c3d.sending", old),
                       ("r-" + "C" * 22 + ".geojson", young)):
        with open(os.path.join(exports, name), "w") as f:
            f.write("x")
        os.utime(os.path.join(exports, name), (when, when))
    return "r-" + "C" * 22 + ".geojson"


def test_housekeeping_sweeps_the_exports(tmp_path):
    """A housekeeping round of the worker (every HOUSEKEEPING s) deletes what work/exports/ holds since
    export_sweep_age(), a broken-off sending's leftover too, and keeps the younger files."""
    young = _old_and_young_exports(tmp_path)
    jb.Scheduler(jb.Jobs(str(tmp_path)), limits=Limits()).housekeeping()
    assert exports_of(tmp_path) == [young]


def test_the_worker_loop_sweeps_the_exports(tmp_path, monkeypatch):
    """Between housekeeping rounds the worker's loop (Scheduler._loop) sweeps work/exports/ every EXPORT_SWEEP
    seconds, so no file is kept longer than the privacy page's hour: export_sweep_age() + EXPORT_SWEEP + TICK <
    EXPORT_KEEP_SECONDS. Here housekeeping does nothing and the loop's sweep comes after 0.2 s."""
    assert jb.EXPORT_KEEP_SECONDS == 3600 and jb.export_sweep_age() + jb.EXPORT_SWEEP + jb.TICK < 3600
    monkeypatch.setattr(jb, "EXPORT_SWEEP", 0.2)
    young = _old_and_young_exports(tmp_path)
    scheduler = jb.Scheduler(jb.Jobs(str(tmp_path)), worker_id="w-loop", limits=Limits())
    for name in ("housekeeping", "_heartbeat", "_check_quick", "_check"):  # nothing else: no processes, no rounds
        monkeypatch.setattr(scheduler, name, lambda: None)
    loop = threading.Thread(target=scheduler._loop, daemon=True)
    loop.start()
    try:
        deadline = time.monotonic() + 30
        while len(exports_of(tmp_path)) > 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert exports_of(tmp_path) == [young]
    finally:
        scheduler.stopped.set()
        loop.join(10)
    assert not loop.is_alive()


def test_a_listing_error_never_stops_the_sweep(tmp_path, monkeypatch):
    """jobs._remove_old: a folder whose listing raises (a network drive's hiccup) removes nothing and raises
    nothing, so the worker's loop, which sweeps the exports every EXPORT_SWEEP seconds, goes on."""
    _old_and_young_exports(tmp_path)
    exports = os.path.join(str(tmp_path), *jb.EXPORTS)
    real = os.scandir

    def failing(folder="."):
        if os.path.abspath(str(folder)) == os.path.abspath(exports):
            raise OSError(5, "Input/output error", str(folder))
        return real(folder)
    monkeypatch.setattr(jb.os, "scandir", failing)
    assert jb.remove_old_exports(str(tmp_path)) == 0 and len(exports_of(tmp_path)) == 3


def test_the_lane_sets_its_safeguards(clip_store, tmp_path, monkeypatch):
    """run_quick hands its worker's Limits to the lane (LANE_LIMITS): a task of the lane is refused below
    free_disk_gb_min (503 export_disk_full) though the task itself carries no limits."""
    data, run_id, _ = copy_data(clip_store, tmp_path)
    monkeypatch.setattr(jb, "LANE_LIMITS", None)
    with quick_lane(data, monkeypatch, limits=Limits(free_disk_gb_min=1e9)) as jobs:
        task = jobs.quick_add("export", {"run": run_id, "format": "csv"}, None, True)  # unlimited: no task limits
        deadline = time.monotonic() + 120
        while (answer := jobs.quick_take(task)) is None:
            assert time.monotonic() < deadline, "the lane did not answer"
            time.sleep(0.05)
    assert answer["code"] == 503 and answer["body"]["code"] == "export_disk_full", answer
    assert exports_of(data) == []


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
            for fmt, media in (("csv", "text/csv; charset=utf-8"), ("geojson", "application/geo+json")):
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
        # another token, whatever the random one (another letter, not only another case: Windows' file names)
        changed = ('y' if name[0].lower() == 'x' else 'x') + name[1:]
        for path in (f"/api/runs/{run_id}/export/{name}", f"/api/runs/other-run/export/{changed}",
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
    # NFKD makes fullwidth forms plain: refused after it too (the code review's names)
    for name, plain in (("a\uff02b\uff3cc.csv", "a_b_c.csv"), ("d\uff0fe\uff1af.csv", "d_e_f.csv"),
                        ("x\uff02; filename\uff1devil.exe; a\uff1d\uff02.csv", "x__ filename_evil.exe_ a__.csv")):
        header = web.content_disposition(name, "r.csv")
        assert header.startswith(f"attachment; filename=\"{plain}\"; filename*=UTF-8''"), header
        assert header.split("; filename*=")[0].count("=") == 1, header  # one parameter only
        assert header.count('"') == 2 and "\\" not in header and "/" not in header and ":" not in header, header


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


def test_sent_once_deletes_when_the_sending_fails(tmp_path):
    """SentOnce deletes its file also when the sending raises (a server whose `send` fails once the client is
    gone; uvicorn's own path returns normally and is the test above): the error goes on, the file is gone. A
    Range header is ignored: the whole file is sent."""
    import asyncio
    path = tmp_path / "x.csv"
    path.write_bytes(b"a" * 300_000)
    scope = {"type": "http", "method": "GET", "headers": [(b"range", b"bytes=0-9")], "asgi": {"spec_version": "2.4"}}
    sent = []

    async def broken(message):
        sent.append(message)
        if message["type"] == "http.response.body":
            raise OSError("the client went away")

    async def receive():
        return {"type": "http.disconnect"}
    with pytest.raises(OSError, match="went away"):
        asyncio.run(web.SentOnce(str(path))(scope, receive, broken))
    assert not path.exists() and sent[0]["status"] == 200
    path.write_bytes(b"b" * 10)
    whole = []

    async def keep(message):
        whole.append(message)
    asyncio.run(web.SentOnce(str(path))(scope, receive, keep))
    assert not path.exists() and whole[0]["status"] == 200
    assert b"".join(m.get("body", b"") for m in whole[1:]) == b"b" * 10


def test_two_requests_for_one_export(clip_store, tmp_path):
    """Two downloads of one export at once: the first takes it and sends it whole, the second answers 404 while
    the first still sends (take_export's rename), and the file is gone after the first."""
    data, run_id, _ = copy_data(clip_store, tmp_path)
    exports = os.path.join(str(data), *jb.EXPORTS)
    os.makedirs(exports)
    name = "D" * 22 + ".csv"
    content = os.urandom(32 << 20)
    with open(os.path.join(exports, f"{run_id}-{name}"), "wb") as f:
        f.write(content)
    with _server(data) as port:
        first = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        first.request("GET", f"/api/runs/{run_id}/export/{name}", headers={"Host": f"127.0.0.1:{port}"})
        response = first.getresponse()
        assert response.status == 200
        head = response.read(1 << 16)  # the first is sending: most of the file is still on its way
        second = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        second.request("GET", f"/api/runs/{run_id}/export/{name}", headers={"Host": f"127.0.0.1:{port}"})
        assert second.getresponse().status == 404
        second.close()
        assert head + response.read() == content
        first.close()
        deadline = time.monotonic() + 30
        while exports_of(data) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert exports_of(data) == []


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
            "print(json.dumps([a.status_code, b.status_code, b.text, sorted(m for m in sys.modules "
            "if m.split('.')[0] in ('numba', 'linesearch', 'search', 'linestore', 'pyarrow'))]))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [503, 200, "{}", []]


def test_taking_an_export_never_fails_with_500(clip_store, tmp_path, monkeypatch):
    """take_export: a rename refused (Windows: a scanner holds the file) answers 404 and leaves the export for a
    later request; a file gone between its rename and its opening answers 404 and leaves nothing behind; a
    refused mtime after the rename still sends the file; a file older than EXPORT_KEEP_SECONDS is never sent
    and is deleted (the privacy page's hour, also while no worker sweeps); a run.json that cannot be read names
    the download by the run id."""
    data, run_id, folder = copy_data(clip_store, tmp_path)
    exports = os.path.join(str(data), *jb.EXPORTS)
    os.makedirs(exports)
    name = "E" * 22 + ".csv"
    url = f"/api/runs/{run_id}/export/{name}"
    path = os.path.join(exports, f"{run_id}-{name}")

    def put():
        with open(path, "w") as f:
            f.write("x")
    put()
    app = web.create_app(str(data), token=TOKEN, start_scheduler=False)
    with TestClient(app, base_url=LOCAL, raise_server_exceptions=False) as client:
        real_replace, real_utime = os.replace, os.utime

        def held(src, dst):
            raise PermissionError(13, "The process cannot access the file", src)
        monkeypatch.setattr(web.os, "replace", held)
        assert client.get(url).status_code == 404 and exports_of(data) == [f"{run_id}-{name}"]
        monkeypatch.setattr(web.os, "replace", real_replace)

        def gone(target, *args, **kwargs):
            os.remove(target)
            raise FileNotFoundError(2, "No such file", target)
        monkeypatch.setattr(web.os, "utime", gone)
        assert client.get(url).status_code == 404 and exports_of(data) == []
        monkeypatch.setattr(web.os, "utime", real_utime)

        put()

        def refused(target, *args, **kwargs):
            raise PermissionError(13, "Access is denied", target)
        monkeypatch.setattr(web.os, "utime", refused)  # the rename went through, the mtime not: sent all the same
        sent = client.get(url)
        assert sent.status_code == 200 and sent.content == b"x" and exports_of(data) == []
        monkeypatch.setattr(web.os, "utime", real_utime)

        put()
        old = time.time() - jb.EXPORT_KEEP_SECONDS - 1
        os.utime(path, (old, old))  # past the hour (no worker swept it): never sent, deleted
        assert client.get(url).status_code == 404 and exports_of(data) == []

        put()
        (folder / "run.json").write_text("{not json", "utf-8")
        sent = client.get(url)
        assert sent.status_code == 200 and sent.content == b"x" and exports_of(data) == []
        assert f'filename="{run_id}.csv"' in sent.headers["content-disposition"]
