"""Renaming a run (docs/line-volume/spec-store.md section 5, step 2g; the public site only): the map page's template
in runs.py, where the web process may import it (runs.map_page, kept in mapping under its names), the name rule
(runs.run_name), runs.rename_run and the route POST /api/runs/<id>."""

import contextlib
import html
import json
import os
import shutil
import subprocess
import sys
import unicodedata

import pytest

import cache
import mapping
import runs as rn
from messages import UserError
from test_public import (DENIED, LINE, LOCAL, RUN_A, RUN_B, TOKEN, URL, account_settings, clip_run,  # noqa: F401
                         mark, providers, run_people, settings)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# mapping.MAP_HTML at b1434458 (before the template moved to runs.py): a search's map.html stays byte for byte this
FROZEN_MAP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Find-a-Line</title>
<link rel="stylesheet" href="../{viewer}/viewer.css">
</head><body><div id="map"></div>
<script src="../runs.js"></script>
<script src="../{viewer}/viewer.js"></script>
<main id="{notice_id}" class="ui fal-disk" data-run="{run}"><div class="fal-disk-box">
<h1 class="fal-disk-name">{title}</h1>
<p class="fal-disk-text">{notice}</p>
<pre class="fal-disk-command"><code>findaline.py view {run}</code></pre>
</div></main>
</body></html>
"""

# The modules the web process never imports (CLAUDE.md "Always"; the template's move keeps mapping out of it)
WORKERS_MODULES = ("mapping", "search", "numba", "linestore", "pyarrow", "linesearch")


def test_the_map_page_moved_unchanged():
    """runs.map_page writes what mapping.map_page wrote at b1434458 (the frozen template, the same escaping), and
    mapping keeps every moved name as the same object."""
    import messages
    for name in ("DISK_NOTICE", "MAP_HTML", "VIEWER_FOLDER", "map_page"):
        assert getattr(mapping, name) is getattr(rn, name), name
    assert (rn.VIEWER_FOLDER, rn.DISK_NOTICE) == ("_viewer", "disk-notice")
    for run in ({"id": "2026-11-23_100000_X_0123456789abcdef", "name": "Żabi Koń"},
                {"id": "r<1>", "name": 'A <b>&amp; "quoted" \'one\''}):
        expected = FROZEN_MAP_HTML.format(title=html.escape(run["name"]), viewer="_viewer", notice_id="disk-notice",
                                          run=html.escape(run["id"]),
                                          notice=html.escape(messages.text("ui.map.disk_notice")))
        assert rn.map_page(run) == expected == mapping.map_page(run)


def _modules_of_the_web_process(tmp_path, extra: str = "") -> list:
    """The modules of WORKERS_MODULES a fresh process holds after importing web, making the local app, listing the
    runs and running `extra` (code with `c`, the TestClient, and `rn`, runs)."""
    (tmp_path / "local").mkdir(exist_ok=True)
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            "import runs as rn\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(tmp_path / 'local')!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "assert c.get('/api/runs').status_code == 200\n"
            "rn.map_page({'id': 'r', 'name': 'n'})\n"
            f"{extra}\n"
            f"print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {WORKERS_MODULES!r})))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_web_process_writes_the_map_page_without_mapping(tmp_path):
    """The web process makes a run's map page (runs.map_page) and renames a run (runs.rename_run) without importing
    mapping, the search, numba or the store's modules."""
    runs_dir = tmp_path / "small" / "runs"
    (runs_dir / "r1").mkdir(parents=True)
    meta = {"id": "r1", "name": "Old", "created": "2026-11-23T10:00:00+00:00"}
    (runs_dir / "r1" / "run.json").write_text(json.dumps(meta), "utf-8")
    (runs_dir / "r1" / "map.html").write_text(rn.map_page(meta), "utf-8")
    assert _modules_of_the_web_process(tmp_path) == []
    renamed = _modules_of_the_web_process(tmp_path, f"rn.rename_run({str(runs_dir)!r}, 'r1', 'New')")
    assert renamed == [] and json.loads((runs_dir / "r1" / "run.json").read_text("utf-8"))["name"] == "New"


# --- The name rule (runs.run_name) ---

@pytest.mark.parametrize("value", [None, 5, ["a"], {"name": "a"}, b"bytes", "", " ", " \t ", "　",
                                   "x" * 101, " " + "y" * 101 + " ", "a\x00b", "a\nb", "a\tb", "a\x7fb", "a\x85b",
                                   "a‮b", "‭ab", "a​b", "a‍b", "a﻿b", "a b", "a b",
                                   "ab", "a\ud800b", "a͸b", "a\U000e0001b"],
                         ids=repr)
def test_names_refused(value):
    """Not a string, empty after trimming, longer than params.MAX_NAME, or holding a character of a category "C*"
    (control, format: bidi and zero-width marks, surrogate, private use, unassigned) or "Zl"/"Zp": a coded error
    "run_name" with the limit, whose web text comes from the catalogue and never holds the name."""
    import messages
    with pytest.raises(UserError) as refused:
        rn.run_name(value)
    assert refused.value.code == "run_name" and refused.value.detail() == {
        "message": "Give the run a name of 1 to 100 characters.", "code": "run_name", "params": {"max": 100}}
    assert messages.text("error.run_name", max=100) == "Give the run a name of 1 to 100 characters."
    if isinstance(value, str) and value.strip():
        assert value.strip() not in str(refused.value)


@pytest.mark.parametrize("value, stored", [
    ("Żabi Koń", "Żabi Koń"), ("  New   name  ", "New name"), ("étude", "étude"),
    ("a  b", "a b"), ("x" * 100, "x" * 100), ("  " + "z" * 100 + "  ", "z" * 100),
    ('<b>A & "q"</b>', '<b>A & "q"</b>'), ("1", "1")], ids=repr)
def test_names_as_stored(value, stored):
    """NFC, the runs of (Unicode) whitespace one space, trimmed, 1 to 100 characters after that."""
    assert rn.run_name(value) == stored
    assert unicodedata.is_normalized("NFC", rn.run_name(value))


# --- runs.rename_run on a run a search saved ---

def _files(folder) -> dict:
    """Every file of a run folder (relative path with /) and its bytes."""
    found = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            found[os.path.relpath(path, folder).replace(os.sep, "/")] = open(path, "rb").read()
    return found


@pytest.fixture
def saved(tmp_path, clip_run):
    """A data folder's runs folder with the clip's run as the search saved it (its own id and name), plus a tiled
    search's work state (progress.json, tiles/) and a runs.js; (runs folder, run id, the run's files before)."""
    runs_dir = tmp_path / "data" / "runs"
    runs_dir.mkdir(parents=True)
    folder = runs_dir / clip_run.name
    shutil.copytree(clip_run, folder)
    (folder / "progress.json").write_text('{"status": "done"}', "utf-8")
    (folder / "tiles").mkdir()
    (folder / "tiles" / "0.pkl.gz").write_bytes(b"tile")
    (runs_dir / "runs.js").write_text("window.FINDALINE_RUNS = [];\n", "utf-8")
    return runs_dir, clip_run.name, _files(folder)


def _attribution_head(meta) -> bytes:
    return f"Find-a-Line run \"{meta['name']}\" ({meta['created']})".encode("utf-8")


def test_rename_a_saved_run(saved):
    """ATTRIBUTION.txt's first line, map.html (map_page with the new name, written as save_map writes it) and
    run.json's name (every other key, value and the order kept) change; nothing else of the folder, runs.js neither;
    the lock taken once; a rename back to the old name gives every file's bytes of before."""
    runs_dir, run_id, before = saved
    folder = runs_dir / run_id
    meta = json.loads(before["run.json"])
    assert before["ATTRIBUTION.txt"].splitlines()[0] == _attribution_head(meta)  # the line the search wrote
    assert "map.html" in before and {"lines.arrow", "profiles.arrow"} <= before.keys()
    runs_js = (runs_dir / "runs.js").read_bytes()
    taken = []
    real_lock = cache.runs_lock

    def counted_lock(path):
        taken.append(path)
        return real_lock(path)
    name = 'Nowa <b>& "linia"</b> Żabi'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cache, "runs_lock", counted_lock)
        answer = rn.rename_run(str(runs_dir), run_id, name)
    assert taken == [str(runs_dir)] and answer["name"] == name
    after = _files(folder)
    assert after.keys() == before.keys()
    changed = {path for path in after if after[path] != before[path]}
    assert changed == {"ATTRIBUTION.txt", "run.json", "map.html"}
    old_first, _, rest = before["ATTRIBUTION.txt"].partition(b"\n")
    new_first, _, new_rest = after["ATTRIBUTION.txt"].partition(b"\n")
    assert new_rest == rest and new_first.rstrip(b"\r") == _attribution_head({**meta, "name": name})
    assert new_first.endswith(b"\r") == old_first.endswith(b"\r")
    stored = json.loads(after["run.json"])
    assert list(stored) == list(meta) and stored == {**meta, "name": name}
    reference = folder.parent / "reference.html"
    with open(reference, "w", encoding="utf-8") as f:  # as mapping.save_map writes it
        f.write(mapping.map_page({**meta, "name": name}))
    assert after["map.html"] == reference.read_bytes()
    page = after["map.html"].decode("utf-8")
    assert f"<title>{html.escape(name)} - Find-a-Line</title>" in page and "<b>" not in page
    assert f'<h1 class="fal-disk-name">{html.escape(name)}</h1>' in page
    assert (runs_dir / "runs.js").read_bytes() == runs_js
    assert [r["name"] for r in rn.list_runs(str(runs_dir))] == [name]
    with cache.runs_lock(str(runs_dir)).acquire(timeout=0):  # released
        pass
    rn.rename_run(str(runs_dir), run_id, meta["name"])
    assert _files(folder) == before


def test_rename_leaves_what_it_does_not_know(saved):
    """An ATTRIBUTION.txt whose first line is not the line of the old name stays as it is; a run without map.html
    gets none; a run without a readable run.json is a KeyError and nothing changes."""
    runs_dir, run_id, before = saved
    folder = runs_dir / run_id
    (folder / "ATTRIBUTION.txt").write_bytes(b"Edited by hand\nsecond line\n")
    (folder / "map.html").unlink()
    rn.rename_run(str(runs_dir), run_id, "Other")
    assert (folder / "ATTRIBUTION.txt").read_bytes() == b"Edited by hand\nsecond line\n"
    assert not (folder / "map.html").exists()
    assert json.loads((folder / "run.json").read_text("utf-8"))["name"] == "Other"
    for broken in (None, b"{not json", b"[1, 2]", b'{"id": "x"}'):
        if broken is None:
            (folder / "run.json").unlink()
        else:
            (folder / "run.json").write_bytes(broken)
        files = _files(folder)
        with pytest.raises(KeyError):
            rn.rename_run(str(runs_dir), run_id, "Third")
        assert _files(folder) == files
    with pytest.raises(KeyError):
        rn.rename_run(str(runs_dir), "no-such-run", "Third")


@pytest.mark.parametrize("failing", ["ATTRIBUTION.txt", "map.html", "run.json"])
def test_a_failed_rename_keeps_the_old_name(saved, failing):
    """A file that cannot be replaced (OSError: on Windows one held open) stops the rename: run.json keeps the old
    name, so every list shows it; a second rename to the same name repairs the files written before the failure.
    No temporary file is left."""
    runs_dir, run_id, before = saved
    folder = runs_dir / run_id
    old = json.loads(before["run.json"])["name"]
    real = cache.replacing

    @contextlib.contextmanager
    def refusing(path, *args, **kwargs):
        if os.path.basename(path) == failing:
            raise PermissionError(13, "held by another process", path)
        with real(path, *args, **kwargs) as f:
            yield f
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cache, "replacing", refusing)
        with pytest.raises(OSError):
            rn.rename_run(str(runs_dir), run_id, "New")
    after = _files(folder)
    assert after["run.json"] == before["run.json"] and [r["name"] for r in rn.list_runs(str(runs_dir))] == [old]
    written = ["ATTRIBUTION.txt", "map.html", "run.json"]
    for path in written[written.index(failing):]:
        assert after[path] == before[path], path
    assert after.keys() == before.keys()  # no .part left
    rn.rename_run(str(runs_dir), run_id, "New")
    assert json.loads((folder / "run.json").read_text("utf-8"))["name"] == "New"
    assert (folder / "ATTRIBUTION.txt").read_bytes().splitlines()[0] == _attribution_head(
        {**json.loads(before["run.json"]), "name": "New"})
    assert "<title>New - Find-a-Line</title>" in (folder / "map.html").read_text("utf-8")


# --- The route POST /api/runs/<id> on the public site ---

def _as_saved(folder):
    """ATTRIBUTION.txt and map.html of a run folder as the search writes them for its run.json (test_public's
    copy_run changes only run.json's name)."""
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    with open(folder / "ATTRIBUTION.txt", "w", encoding="utf-8") as f:
        f.write(rn.attribution_text(meta))
    with open(folder / "map.html", "w", encoding="utf-8") as f:
        f.write(rn.map_page(meta))


def _listed_names(client) -> dict:
    """{run id: name} of /runs/runs.js."""
    text = client.get("/runs/runs.js").text
    return {r["id"]: r["name"] for r in json.loads(text.split("window.FINDALINE_RUNS = ")[1].split(";\n")[0])}


def test_rename_through_the_site(run_people, tmp_path):
    """The owner renames a run: the answer gives the name as stored; run.json, ATTRIBUTION.txt's first line and
    map.html follow; /api/runs, runs.js, favourites, the admin's list, the demo cards of the sign-in page and an
    export's download name give the new name with no code of their own; the run's id, its map's address, its share
    link and its favourites still open it; the audit log records run_rename without the name."""
    import audit
    import jobs as jb
    a, admin, anonymous = run_people["a"], run_people["admin"], run_people["anonymous"]
    folder = tmp_path / "runs" / RUN_A
    _as_saved(folder)
    store = {n: (folder / n).read_bytes() for n in ("lines.arrow", "profiles.arrow")}
    token = a.post(f"/api/runs/{RUN_A}/share").json()["url"].split("/s/")[1].split("/")[0]
    assert mark(a, RUN_A, LINE).status_code == 200
    row = run_people["jobs"].run(RUN_A)

    answer = a.post(f"/api/runs/{RUN_A}", json={"name": "  Sunny   édge <b>&\"q\"  "})
    name = "Sunny édge <b>&\"q\""
    assert answer.status_code == 200 and answer.json() == {"ok": True, "name": name}
    meta = json.loads((folder / "run.json").read_text("utf-8"))
    assert meta["name"] == name and meta["id"] == RUN_A
    assert (folder / "ATTRIBUTION.txt").read_text("utf-8").splitlines()[0] == f"Find-a-Line run \"{name}\" " \
        f"({meta['created']})"
    page = a.get(f"/runs/{RUN_A}/map.html")
    assert page.status_code == 200 and f"<title>{html.escape(name)} - Find-a-Line</title>" in page.text
    assert "<b>" not in page.text
    assert {n: (folder / n).read_bytes() for n in store} == store
    assert run_people["jobs"].run(RUN_A) == row  # the runs row (owner, share hash, visibility) as it was

    assert {r["id"]: r["name"] for r in a.get("/api/runs").json()["runs"]} == {RUN_A: name}
    assert _listed_names(a) == {RUN_A: name}
    assert [f["run_name"] for f in a.get("/api/favourites").json()["favourites"]] == [name]
    assert {r["run_id"]: r["name"] for r in admin.get("/api/admin/runs").json()["runs"]}[RUN_A] == name
    shared = anonymous.get(f"/s/{token}/map.html")
    assert shared.status_code == 200 and f"<title>{html.escape(name)} - Find-a-Line</title>" in shared.text
    assert admin.post(f"/api/runs/{RUN_A}/demo", json={"demo": True}).status_code == 200
    assert f"<b>{html.escape(name)}</b>" in anonymous.get("/").text  # the sign-in page's demo card

    # an export's download (its file put where the worker's quick lane puts it: the lane itself is test_public's)
    exports = tmp_path / os.path.join(*jb.EXPORTS)
    exports.mkdir(parents=True, exist_ok=True)
    export_name = "A" * 22 + ".csv"
    (exports / f"{RUN_A}-{export_name}").write_bytes(b"a,b\r\n")
    assert a.post(f"/api/runs/{RUN_A}", json={"name": "Plain name"}).json()["name"] == "Plain name"
    sent = a.get(f"/api/runs/{RUN_A}/export/{export_name}")
    assert sent.status_code == 200 and sent.headers["content-disposition"].startswith(
        'attachment; filename="Plain name.csv"')

    entries = [e for e in audit.Audit(str(tmp_path)).entries() if e["action"] == "run_rename"]
    assert [(e["user_id"], e["target"], e["detail"]) for e in entries] == [(run_people["ids"]["a"], RUN_A, None)] * 2
    assert "Sunny" not in json.dumps(audit.Audit(str(tmp_path)).entries()) and "Plain" not in json.dumps(entries)


def test_rename_refused(run_people, tmp_path, monkeypatch):
    """Another user's run and an administrator who is not the owner: 404; no session, a pending or blocked user:
    the guard's answer; a refused name or a body without a string name: 400 with the coded error; a run without
    run.json: 404; a file held: 409; each changes nothing and records nothing."""
    import audit
    a = run_people["a"]
    folder = tmp_path / "runs" / RUN_A
    _as_saved(folder)
    before = _files(folder)
    assert run_people["b"].post(f"/api/runs/{RUN_A}", json={"name": "Mine"}).status_code == 404
    assert run_people["admin"].post(f"/api/runs/{RUN_A}", json={"name": "Mine"}).status_code == 404
    assert a.post(f"/api/runs/{RUN_B}", json={"name": "Mine"}).status_code == 404
    assert a.post("/api/runs/no-such-run", json={"name": "Mine"}).status_code == 404
    for who, code in DENIED.items():
        assert run_people[who].post(f"/api/runs/{RUN_A}", json={"name": "Mine"}).status_code == code, who
    assert a.post(f"/api/runs/{RUN_A}", json={"name": "Mine"}, headers={"origin": "https://evil.example"}) \
        .status_code == 403
    for body in ({"name": ""}, {"name": "   "}, {"name": "x" * 101}, {"name": "a\x01b"}, {"name": "a‮b"},
                 {"name": "a​b"}, {"name": 5}, {"name": None}, {}, {"title": "x"}):
        refused = a.post(f"/api/runs/{RUN_A}", json=body)
        assert refused.status_code == 400 and refused.json()["detail"] == {
            "message": "Give the run a name of 1 to 100 characters.", "code": "run_name", "params": {"max": 100}}, body
    assert a.post(f"/api/runs/{RUN_A}", json=["Mine"]).status_code == 422  # not an object: FastAPI's own answer
    real = cache.replacing

    @contextlib.contextmanager
    def held(path, *args, **kwargs):
        if os.path.basename(path) == "map.html":
            raise PermissionError(13, "held by another process", path)
        with real(path, *args, **kwargs) as f:
            yield f
    monkeypatch.setattr(cache, "replacing", held)
    in_use = a.post(f"/api/runs/{RUN_A}", json={"name": "Mine"})
    assert in_use.status_code == 409 and in_use.json()["detail"] == "the run is in use: try again in a moment"
    monkeypatch.setattr(cache, "replacing", real)
    after = _files(folder)
    assert after["run.json"] == before["run.json"] and after["map.html"] == before["map.html"]
    assert {r["name"] for r in a.get("/api/runs").json()["runs"]} == {"A's run"}
    (folder / "run.json").unlink()
    assert a.post(f"/api/runs/{RUN_A}", json={"name": "Mine"}).status_code == 404
    assert not [e for e in audit.Audit(str(tmp_path)).entries() if e["action"] == "run_rename"]


def test_no_rename_in_the_local_app(tmp_path, clip_run):
    """The local app has no rename (the runs folder is the user's own: findaline.py has no command either): 404 for
    a run that exists, its files unchanged."""
    import web
    from fastapi.testclient import TestClient
    local = tmp_path / "local"
    shutil.copytree(clip_run, local / "runs" / clip_run.name)
    before = _files(local / "runs" / clip_run.name)
    with TestClient(web.create_app(str(local), token=TOKEN, start_scheduler=False), base_url=LOCAL) as client:
        headers = {"x-findaline-token": TOKEN}
        assert client.get(f"/runs/{clip_run.name}/map.html").status_code == 200
        refused = client.post(f"/api/runs/{clip_run.name}", json={"name": "Mine"}, headers=headers)
        assert refused.status_code == 404 and refused.json()["detail"] == "runs are renamed on the public site"
    assert _files(local / "runs" / clip_run.name) == before
