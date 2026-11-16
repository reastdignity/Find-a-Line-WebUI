"""tools/ui_shots.py: its data edits (the browser passes run by hand, .claude/rules/viewer.md "Verifying changes")."""

import hashlib
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import linestore  # noqa: E402
import ui_shots  # noqa: E402


def test_credits_go_into_data_js_and_the_store(tmp_path):
    """with_credits: a run's credits in its data.js, run.json and its store's head (the page reads the store when
    run.json lists it), run.json's block "store" matching the rewritten lines.arrow; the store's lines as before."""
    from test_linestore import _hard_lines, _profiles
    from test_viewer import _store_and_script, _store_head
    lines = _hard_lines(200, False, False, np.random.default_rng(1))
    lines.profiles = _profiles(200, np.random.default_rng(2))
    folder = tmp_path / "run"
    block = _store_and_script(folder, lines, _store_head(lines, False, False))
    (folder / "run.json").write_text(json.dumps({"id": "r", "store": block}), encoding="utf-8")
    before, _ = linestore.read(str(folder))

    ui_shots.with_credits(str(folder / "data.js"))
    data = json.loads((folder / "data.js").read_text(encoding="utf-8").partition(" = ")[2].rstrip().rstrip(";"))
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    after, head = linestore.read(str(folder))
    assert data["attribution"] and head["attribution"] == data["attribution"] == meta["attribution"]
    store = meta["store"]
    assert store["lines"] == 200 and store["format"] == linestore.FORMAT
    assert store["bytes"] == sum((folder / name).stat().st_size for name in linestore.FILES)
    assert store["sha256"] == hashlib.sha256((folder / linestore.LINES_FILE).read_bytes()).hexdigest()[:16]
    for name, values in before.columns.items():
        assert np.array_equal(values, after.columns[name], equal_nan=values.dtype.kind == "f"), name

    plain = tmp_path / "plain"  # a run without a store: data.js and run.json only
    plain.mkdir()
    (plain / "data.js").write_text((folder / "data.js").read_text(encoding="utf-8"), encoding="utf-8")
    (plain / "run.json").write_text(json.dumps({"id": "p"}), encoding="utf-8")
    ui_shots.with_credits(str(plain / "data.js"))
    assert "store" not in json.loads((plain / "run.json").read_text(encoding="utf-8"))
