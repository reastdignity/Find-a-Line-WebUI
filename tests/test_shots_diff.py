"""tools/shots_diff.py: two folders of pictures compared file by file."""

import os
import subprocess
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import shots_diff  # noqa: E402


def _png(path, pixels):
    Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(path)


def test_folders_compared(tmp_path):
    """Only in one folder, sizes that differ, the share of pixels beyond the threshold and the largest difference
    (a change at the threshold is no difference), sorted by share; a difference picture of each file that differs;
    exit code 0 with differences."""
    a, b, out = tmp_path / "a", tmp_path / "b", tmp_path / "out"
    a.mkdir()
    b.mkdir()
    base = np.full((10, 20, 3), 200)
    _png(a / "same.png", base)
    _png(b / "same.png", base)
    _png(a / "edge.png", base)
    _png(b / "edge.png", base + 8)  # at the threshold: the same
    changed = base.copy()
    changed[:5, :4] = 0  # 20 of 200 pixels
    _png(a / "some.png", base)
    _png(b / "some.png", changed)
    more = base.copy()
    more[:, :10, 1] = 150  # half, one channel by 50
    _png(a / "half.png", base)
    _png(b / "half.png", more)
    _png(a / "gone.png", base)
    _png(b / "new.png", base)
    _png(a / "size.png", base)
    _png(b / "size.png", np.full((12, 20, 3), 200))
    (a / "notes.txt").write_text("not a picture")

    rows = shots_diff.compare_folders(str(a), str(b), out=str(out))
    by = {name: (what, share, largest) for name, what, share, largest in rows}
    assert set(by) == {"same.png", "edge.png", "some.png", "half.png", "gone.png", "new.png", "size.png"}
    assert by["gone.png"][0] == "only in a" and by["new.png"][0] == "only in b"
    assert by["size.png"][0] == "sizes differ (20x10, 20x12)"
    assert by["same.png"] == ("same", 0.0, 0) and by["edge.png"] == ("same", 0.0, 8)
    assert by["some.png"] == ("differs", 0.1, 200) and by["half.png"] == ("differs", 0.5, 50)
    assert [r[0] for r in rows][3:] == ["half.png", "some.png", "edge.png", "same.png"]
    assert sorted(os.listdir(out)) == ["half.png", "some.png"]
    marked = np.asarray(Image.open(out / "some.png"))
    assert tuple(marked[0, 0]) == (230, 0, 0) and tuple(marked[9, 19]) != (230, 0, 0)

    result = subprocess.run([sys.executable, os.path.join(REPO, "tools", "shots_diff.py"), str(a), str(b),
                             "--threshold", "60"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "7 files: 3 the same, 1 differ, 1 of another size, 1 only in a, 1 only in b" in result.stdout
