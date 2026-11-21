"""tools/ui_coast_run.py: the coastal copy of the clip's run that ui_shots' coast states of the result view need (an
uncertain shore and coarser terrain over its lines, the view's columns kept); never a run that is not the clip's."""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_coast_run  # noqa: E402
import ui_shots  # noqa: E402


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    import clip_runs
    return clip_runs.view_clip(tmp_path_factory, "coast-run")


def test_the_copy_has_the_coast_and_the_view(clip, tmp_path):
    """The copy: its own id (run.json and the store's head), the shore's segments and the coarser terrain in both, the
    store's block matching the file, the features the coast states need; the clip's run itself unchanged."""
    import pyarrow as pa
    import linestore
    before = (clip / "run.json").read_bytes()
    dst = ui_coast_run.coast_copy(str(clip), str(tmp_path))
    assert os.path.basename(dst) == ui_coast_run.RUN and (clip / "run.json").read_bytes() == before
    assert ui_shots.run_features(dst) >= {"view", "shore"}
    meta = json.loads(open(os.path.join(dst, "run.json"), encoding="utf-8").read())
    assert meta["id"] == ui_coast_run.RUN and meta["name"] == ui_coast_run.NAME
    with pa.OSFile(os.path.join(dst, linestore.LINES_FILE), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    head = json.loads(table.schema.metadata[linestore.META_KEY])["head"]
    assert head["shore"] == meta["shore"] and head["terrain_sources"] == meta["terrain_sources"]
    assert clip.name not in json.dumps(head) and {s["kind"] for s in head["shore"]["segments"]} == {"surface", "sea"}
    assert head["terrain_sources"]["regions"] and table.num_rows == meta["store"]["lines"]
    import hashlib
    with open(os.path.join(dst, linestore.LINES_FILE), "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest()[:16] == meta["store"]["sha256"]
    # every coast state of the view stays in a ui_shots run of this copy
    assert not ui_shots.left_out_by_run(ui_shots.VIEW_STATES, ui_shots.run_features(dst))


def test_only_the_clip(tmp_path):
    """A run whose run.json names another elevation file is refused (a user's run is never copied)."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "run.json").write_text(json.dumps({"data": [{"layer": "Terrain file", "file": "C:/somewhere/else.tif"}]}),
                                    encoding="utf-8")
    with pytest.raises(ValueError, match="not a run of the clip"):
        ui_coast_run.coast_copy(str(other), str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()
