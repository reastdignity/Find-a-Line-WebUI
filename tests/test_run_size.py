"""A run's size on Home's card (line volume's step 2d as the user reduced it, 2026-11-23: "Size on Home only", "Size
as stored"): /api/runs gives each run "bytes", run.json's store.bytes (lines.arrow and profiles.arrow as written), or
null for a run without a store block; on the public site and in the local app."""

import json
import os
import shutil

import linestore
from test_public import (LOCAL, RUN_A, RUN_B, RUN_OLD, TOKEN, account_settings, clip_run, providers,  # noqa: F401
                         run_people, settings)


def _on_disk(folder) -> int:
    """The store's two files' sizes on disk."""
    return sum(os.path.getsize(os.path.join(folder, name)) for name in linestore.FILES)


def _bytes_of(client) -> dict:
    """{run id: "bytes"} of /api/runs."""
    answer = client.get("/api/runs")
    assert answer.status_code == 200
    return {r["id"]: r["bytes"] for r in answer.json()["runs"]}


def test_runs_carry_their_size_as_stored(run_people, tmp_path):
    """Each listed run has "bytes": its store's two files as written (= their sizes on disk), an integer; a run whose
    run.json has no store block gives null; another user's runs are still not listed; nothing else of the store
    block is sent; the admin's list (its "bytes": the runs row's folder size for the quota) and runs.js are as
    before."""
    a, b, admin = run_people["a"], run_people["b"], run_people["admin"]
    runs_dir = tmp_path / "runs"
    expected = _on_disk(runs_dir / RUN_A)
    assert set(linestore.FILES) == {"lines.arrow", "profiles.arrow"} and expected > 0
    sizes = _bytes_of(a)
    assert sizes == {RUN_A: expected} and type(sizes[RUN_A]) is int
    assert _bytes_of(b) == {RUN_B: _on_disk(runs_dir / RUN_B)}
    assert _bytes_of(admin) == {RUN_OLD: _on_disk(runs_dir / RUN_OLD)}
    listed = a.get("/api/runs").json()["runs"][0]
    assert "store" not in listed and "sha256" not in json.dumps(listed)
    admin_rows = {r["run_id"]: r for r in admin.get("/api/admin/runs").json()["runs"]}
    assert admin_rows[RUN_A]["bytes"] == 100 == run_people["jobs"].run(RUN_A)["bytes"]  # the runs row's, as before
    runs_js = json.loads(a.get("/runs/runs.js").text.split("window.FINDALINE_RUNS = ")[1].split(";\n")[0])
    assert "bytes" not in runs_js[0] and runs_js[0]["store"]["bytes"] == expected  # its store block as before
    meta = json.loads((runs_dir / RUN_A / "run.json").read_text("utf-8"))
    del meta["store"]
    (runs_dir / RUN_A / "run.json").write_text(json.dumps(meta), "utf-8")
    assert _bytes_of(a) == {RUN_A: None}


def test_the_local_app_gives_the_size_too(tmp_path, clip_run):
    """The local app lists every run with "bytes" as the public site does."""
    import web
    from fastapi.testclient import TestClient
    local = tmp_path / "local"
    shutil.copytree(clip_run, local / "runs" / clip_run.name)
    meta = json.loads((clip_run / "run.json").read_text("utf-8"))
    assert meta["store"]["bytes"] == _on_disk(clip_run)  # as the search wrote it
    with TestClient(web.create_app(str(local), token=TOKEN, start_scheduler=False), base_url=LOCAL) as client:
        assert _bytes_of(client) == {clip_run.name: _on_disk(clip_run)}
