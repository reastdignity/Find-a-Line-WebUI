"""
30 m against 1 m at famous places, for the coverage map's animations (docs/coverage/contrast/).

At each place of PLACES a search of a circle of RADIUS with the preset "typical" (lines of 30-150 m, anchors
at most 10 m apart in height) runs twice on the same national data: at 1 m, and averaged to 30 m with the slope
threshold THRESHOLD (a 30 m pixel never gets as steep as a wall: the global model's threshold). Then:
- a hillshade of each grid (JPEG, SIZE px, a square of 2 x RADIUS around the centre) with the lines of up to
  MAX_SPOTS spots (their representatives) as segments in the square's 0..1 coordinates;
- the check "is 30 m enough?": a 1 m spot is found at 30 m when a 30 m line has both anchors within
  MATCH_RADIUS of its representative's (either way round), a 30 m spot is real when one of its lines has a
  1 m line so near.
contrast.json is `Contrast` of viewer/src/coverage/types.ts. Run by hand (it downloads the data of nine places
into the data folder, about 2 GB), one search after another:

    uv run tools/coverage_contrast.py search --data-dir <folder> [--work <folder>] [place ...]
    uv run tools/coverage_contrast.py write [--work <folder>]

`search` keeps each search's grid and lines in the work folder (default: <data folder>/work/coverage-contrast,
`write` takes the same `--data-dir` or `--work`); `write` makes the images and contrast.json from them.
"""

import argparse
import datetime
import io
import json
import os
import sys
import time
from typing import Dict, List, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "docs", "coverage", "contrast")
# (lat, lon) of the places in the order the animations show them
PLACES = {
    "zabi_kon": (50.1559508, 19.7562722),
    "matterhorn": (45.9800, 7.6620),
    "preikestolen": (58.98640, 6.19030),
    "bastei": (50.96190, 14.07310),
    "verdon": (43.7615, 6.3130),  # the Imbut
    "half_dome": (37.74600, -119.53300),
    "delicate_arch": (38.74360, -109.49930),
    "stawamus_chief": (49.68300, -123.14100),
    "aoraki": (-43.5950, 170.1418),
}
RADIUS = 400
LINES = {"min_length": 30, "max_length": 150, "max_anchor_diff_m": 10}  # the preset "typical"
SIDES = (("fine", 1.0), ("coarse", 30.0))
THRESHOLD = 40.5   # degrees: the slope threshold of the 30 m search
MATCH_RADIUS = 45  # metres
SIZE = 560         # px of an image
MARGIN = 1.05      # the image's half side in radii
MAX_SPOTS = 80     # spots drawn as segments
QUALITY = 78       # JPEG


def search(place: str, side: str, data_dir: str, work: str) -> None:
    """One search: its grid's heights, its lines' anchors and spots and what it used, into the work folder."""
    import search as sr
    import sources as src
    from params import SearchParams
    lat, lon = PLACES[place]
    res = dict(SIDES)[side]
    extra = {"slope_threshold": THRESHOLD} if side == "coarse" else {}
    params = SearchParams(lat=lat, lon=lon, radius=RADIUS, resolution=res, **LINES, **extra)
    folder = os.path.join(work, "search", f"{place}-{side}")
    os.makedirs(folder, exist_ok=True)
    plan = sr.plan_search(params, sr.Paths(data=data_dir, work=folder))
    data = sr.prepare_data(plan)
    try:
        lines = sr.find_lines(plan, data)
        c, groups = lines.results.columns, lines.spot_groups
        a1, a2, over = c["a1_xy"], c["a2_xy"], c["over_obstacles"]
        rep, members, start = groups.rep, groups.members, groups.start
    except sr.SearchError:  # not enough steep terrain: no lines
        a1 = a2 = np.empty((0, 2))
        over = np.empty(0, bool)
        rep = members = np.empty(0, np.int64)
        start = np.zeros(1, np.int64)
    np.savez_compressed(os.path.join(work, f"{place}-{side}.npz"),
                        elevation=np.asarray(data.elevation, dtype=np.float32), a1=a1, a2=a2, over=over,
                        rep=rep, members=members, start=start)
    grid = plan.grid
    info = {"lat": lat, "lon": lon, "radius": RADIUS, "res": res, "source": plan.source.id,
            "source_name": plan.source.name, "center_xy": [float(v) for v in plan.center_xy],
            "grid": {"left": grid.left, "top": grid.top, "res": grid.res},
            "credits": credits(src.used_data), "year": datetime.date.today().year}
    with open(os.path.join(work, f"{place}-{side}.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(f"== {place} {res:g} m: {plan.source.id}, {len(a1)} lines, {len(rep)} spots", flush=True)


def credits(used: Sequence[dict]) -> List[dict]:
    """The credits of the data a search used, each once, in their order."""
    out = []
    for entry in used:
        credit = entry.get("credit")
        if credit and credit not in out:
            out.append(credit)
    return out


# The pure parts (tests/test_coverage.py)

def matched(a1: np.ndarray, a2: np.ndarray, b1: np.ndarray, b2: np.ndarray, radius: float) -> np.ndarray:
    """For each line (a1[k], a2[k]): has a line of (b1, b2) both anchors within radius of its anchors,
    either way round."""
    from scipy.spatial import cKDTree
    out = np.zeros(len(a1), dtype=bool)
    if not len(a1) or not len(b1):
        return out
    t1, t2 = cKDTree(b1), cKDTree(b2)
    for k in range(len(a1)):
        for p, q in ((a1[k], a2[k]), (a2[k], a1[k])):
            if set(t1.query_ball_point(p, radius)) & set(t2.query_ball_point(q, radius)):
                out[k] = True
                break
    return out


def verify(fine: dict, coarse: dict, radius: float = MATCH_RADIUS) -> Dict[str, int]:
    """The check of one place from the lines of both searches (a1, a2, rep, members, start)."""
    reps = fine["rep"]
    found = matched(fine["a1"][reps], fine["a2"][reps], coarse["a1"], coarse["a2"], radius)
    real = matched(coarse["a1"], coarse["a2"], fine["a1"], fine["a2"], radius)
    start, members = coarse["start"], coarse["members"]
    spots_real = sum(bool(real[members[start[g]:start[g + 1]]].any()) for g in range(len(coarse["rep"])))
    return {"fine_spots": int(len(reps)), "fine_found": int(found.sum()),
            "coarse_spots": int(len(coarse["rep"])), "coarse_real": int(spots_real)}


def segments(a1: np.ndarray, a2: np.ndarray, reps: np.ndarray, over: np.ndarray,
             square: Tuple[float, float, float], limit: int = MAX_SPOTS) -> List[list]:
    """The first `limit` spots' representatives as [x1, y1, x2, y2, over obstacles] in the square (left, top,
    side) from 0 (left, top) to 1, rounded to 4 decimals; lines reaching beyond 5 % outside left out."""
    left, top, side = square
    out = []
    for k in reps[:limit]:
        x1, x2 = ((a[k][0] - left) / side for a in (a1, a2))
        y1, y2 = ((top - a[k][1]) / side for a in (a1, a2))
        if all(-0.05 <= v <= 1.05 for v in (x1, x2, y1, y2)):
            out.append([round(float(x1), 4), round(float(y1), 4), round(float(x2), 4), round(float(y2), 4),
                        int(bool(over[k]))])
    return out


def crop(info: dict, values: np.ndarray, half: float) -> Tuple[np.ndarray, Tuple[float, float, float]]:
    """The square of 2 x half metres around the centre (NaN outside the grid), and its (left, top, side)."""
    g = info["grid"]
    cx, cy = info["center_xy"]
    c0 = int(round((cx - half - g["left"]) / g["res"]))
    r0 = int(round((g["top"] - (cy + half)) / g["res"]))
    n = int(round(2 * half / g["res"]))
    out = np.full((n, n), np.nan)
    rs, cs = max(r0, 0), max(c0, 0)
    re, ce = min(r0 + n, values.shape[0]), min(c0 + n, values.shape[1])
    out[rs - r0:re - r0, cs - c0:ce - c0] = values[rs:re, cs:ce]
    return out, (cx - half, cy + half, 2 * half)


def shade(elevation: np.ndarray, res: float) -> np.ndarray:
    """A hillshade from the north-west, 0..1 (gaps at the mean height)."""
    from matplotlib.colors import LightSource
    z = np.array(elevation, dtype=np.float64)
    gaps = ~np.isfinite(z)
    if gaps.any():
        z[gaps] = np.nanmean(z)
    return np.clip(LightSource(azdeg=315, altdeg=40).hillshade(z, vert_exag=1.0, dx=res, dy=res), 0, 1)


def jpeg(hillshade: np.ndarray, smooth: bool) -> bytes:
    """The image: a 30 m grid enlarged smoothly (bicubic), a 1 m one reduced sharply (Lanczos)."""
    from PIL import Image
    img = Image.fromarray((np.nan_to_num(hillshade, nan=0.5) * 255).astype(np.uint8), "L")
    img = img.resize((SIZE, SIZE), Image.Resampling.BICUBIC if smooth else Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=QUALITY, optimize=True)
    return buf.getvalue()


def searched_in(info: dict, path: str) -> int:
    """The year of a search (its credits' "{year}", as a run's: the data as served then); a search of before
    the field by its file's time."""
    return info.get("year") or time.gmtime(os.path.getmtime(path + ".json")).tm_year


def write(work: str, out: str = OUT) -> dict:
    """contrast.json and the images from the searches in the work folder."""
    from sources import dated_credit
    os.makedirs(out, exist_ok=True)
    places = {}
    for place in PLACES:
        entry, found = {}, {}
        for side, res in SIDES:
            path = os.path.join(work, f"{place}-{side}")
            with open(path + ".json", encoding="utf-8") as f:
                info = json.load(f)
            lines = dict(np.load(path + ".npz"))
            found[side] = lines
            half = info["radius"] * MARGIN
            cut, square = crop(info, shade(lines["elevation"], info["grid"]["res"]), half)
            heights, _ = crop(info, lines["elevation"], half)
            image = f"{place}-{side}.jpg"
            with open(os.path.join(out, image), "wb") as f:
                f.write(jpeg(cut, smooth=side == "coarse"))
            entry.update(lat=info["lat"], lon=info["lon"], radius=info["radius"])
            entry[side] = {"image": image, "res": int(res), "lines": int(len(lines["a1"])),
                           "spots": int(len(lines["rep"])),
                           "segments": segments(lines["a1"], lines["a2"], lines["rep"], lines["over"], square),
                           "relief": [round(float(np.nanmin(heights)), 1), round(float(np.nanmax(heights)), 1)],
                           "source": info["source"], "source_name": info["source_name"],
                           "credits": [dated_credit(c, searched_in(info, path)) for c in info["credits"]]}
        entry["verify"] = verify(found["fine"], found["coarse"])
        places[place] = entry
        print(place, {side: (entry[side]["lines"], entry[side]["spots"]) for side, _ in SIDES}, entry["verify"])
    keys = ("fine_spots", "fine_found", "coarse_spots", "coarse_real")
    total = {k: sum(p["verify"][k] for p in places.values()) for k in keys}
    data = {"threshold": THRESHOLD, "match_radius": MATCH_RADIUS, "places": places,
            "verify": {"places": len(places), **total}}
    with open(os.path.join(out, "contrast.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("total", data["verify"])
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("step", choices=("search", "write"))
    parser.add_argument("places", nargs="*", metavar="place", help=f"search: these places only ({', '.join(PLACES)}; "
                                                                   "default all)")
    parser.add_argument("--data-dir", help="the data folder of the searches (search; default the repository)")
    parser.add_argument("--work", help="the searches' results (default <data folder>/work/coverage-contrast)")
    args = parser.parse_args(argv)
    unknown = set(args.places) - set(PLACES)
    if unknown:
        parser.error(f"unknown places: {', '.join(sorted(unknown))}")
    import cache
    data_dir = cache.data_dir(args.data_dir)
    work = os.path.abspath(args.work or os.path.join(data_dir, "work", "coverage-contrast"))
    if args.step == "search":
        for place in args.places or PLACES:
            for side, _ in SIDES:
                search(place, side, data_dir, work)
    else:
        write(work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
