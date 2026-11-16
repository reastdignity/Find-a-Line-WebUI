"""
Compares two folders of screenshots (tools/ui_shots.py's, before and after a change) picture by picture: for every
PNG name in either folder, whether it is only in one, whether the sizes differ, or the share of pixels whose largest
channel difference exceeds --threshold (of 255) and the largest difference. A table sorted by that share, then a line
of totals. It reports and does not judge: the exit code is 0 whatever differs (map tiles come live from the
internet, so two runs of the same code can differ on a map).

With --out, a difference picture for each file that differs (<name>.png there): the picture of the first folder
dimmed, the changed pixels in red.

    uv run tools/shots_diff.py <folder a> <folder b> [--out <folder>] [--threshold 8]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

THRESHOLD = 8  # a pixel differs when one of its channels differs by more than this (of 255)


def compare(a: str, b: str, threshold: int = THRESHOLD) -> dict:
    """Two pictures: {"share": the share of pixels that differ, "max": the largest channel difference,
    "mask": the differing pixels (bool, height × width)}, or {"size": (size a, size b)} when their sizes differ."""
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return {"size": (ia.size, ib.size)}
        pa = np.asarray(ia.convert("RGBA"), dtype=np.int16)
        pb = np.asarray(ib.convert("RGBA"), dtype=np.int16)
    diff = np.abs(pa - pb).max(axis=2)
    mask = diff > threshold
    return {"share": float(mask.mean()), "max": int(diff.max()), "mask": mask}


def difference_picture(a: str, mask: np.ndarray, path: str):
    """Picture `a` dimmed (a third of its brightness, on white), the pixels of `mask` in red."""
    with Image.open(a) as image:
        pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    dimmed = (255 - (255 - pixels) / 3).astype(np.uint8)
    dimmed[mask] = (230, 0, 0)
    Image.fromarray(dimmed).save(path)


def compare_folders(a: str, b: str, threshold: int = THRESHOLD, out: str | None = None) -> list:
    """Every PNG of either folder: (name, what: "only in a" | "only in b" | "sizes differ" | "same" | "differs",
    share, largest difference), sorted by share (largest first), the files of one folder only and of other sizes
    first. With `out`, a difference picture of each file that differs there."""
    names = sorted({n for folder in (a, b) for n in os.listdir(folder) if n.lower().endswith(".png")})
    rows = []
    for name in names:
        pa, pb = os.path.join(a, name), os.path.join(b, name)
        if not os.path.isfile(pb):
            rows.append((name, "only in a", None, None))
            continue
        if not os.path.isfile(pa):
            rows.append((name, "only in b", None, None))
            continue
        result = compare(pa, pb, threshold)
        if "size" in result:
            (wa, ha), (wb, hb) = result["size"]
            rows.append((name, f"sizes differ ({wa}x{ha}, {wb}x{hb})", None, None))
            continue
        rows.append((name, "differs" if result["share"] else "same", result["share"], result["max"]))
        if out and result["share"]:
            os.makedirs(out, exist_ok=True)
            difference_picture(pa, result["mask"], os.path.join(out, name))
    rows.sort(key=lambda r: (r[2] is not None, -(r[2] or 0), r[0]))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("a", help="the first folder of pictures (before)")
    parser.add_argument("b", help="the second folder of pictures (after)")
    parser.add_argument("--out", help="a folder for the difference pictures of the files that differ")
    parser.add_argument("--threshold", type=int, default=THRESHOLD,
                        help=f"a pixel differs when a channel differs by more than this (of 255; default {THRESHOLD})")
    args = parser.parse_args()
    rows = compare_folders(args.a, args.b, args.threshold, args.out)
    width = max([len(r[0]) for r in rows] + [4])
    print(f"{'file':<{width}}  {'pixels':>8}  {'max':>4}  result")
    for name, what, share, largest in rows:
        print(f"{name:<{width}}  " + (f"{100 * share:7.3f}%  {largest:4d}  " if share is not None else f"{'':8}  {'':4}  ")
              + what)
    count = {what: sum(1 for r in rows if r[1] == what) for what in ("same", "differs", "only in a", "only in b")}
    sizes = sum(1 for r in rows if r[1].startswith("sizes"))
    print(f"{len(rows)} files: {count['same']} the same, {count['differs']} differ, {sizes} of another size, "
          f"{count['only in a']} only in a, {count['only in b']} only in b")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    main()
