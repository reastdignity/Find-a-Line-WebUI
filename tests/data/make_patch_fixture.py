"""Make the recorded patch of the 3D view's tests from the Żabi Koń clip (docs/3d-view-contract.md, "Body").

Run from the repository root: python tests/data/make_patch_fixture.py. Writes patch_zabi_kon.bin (the
deflated heights, as /api/patch sends them after its meta) and patch_zabi_kon.json (their size, base and
checks): the clip's first 513 x 513 pixels, the last 16 x 16 of them set to no data. `encode` and `decode`
are the reference of the format: the server's encoder and the page's decoder must give the same values
(the sha256 of the decoded int16 values), not necessarily the same deflated bytes (zlib builds differ).
"""

import hashlib
import json
import os
import sys
import zlib

import numpy as np
import rasterio as rio

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE, HOLE = 513, 16
NO_DATA = -32768


def encode(heights: np.ndarray) -> tuple:
    """Heights in metres (NaN for no data), row-major from the top: the deflated body and base_dm (int)."""
    finite = np.isfinite(heights)
    base_dm = int(np.floor(np.min(heights[finite]) * 10)) if finite.any() else 0
    values = np.full(heights.shape, NO_DATA, dtype=np.int64)
    values[finite] = np.rint(heights[finite].astype(np.float64) * 10).astype(np.int64) - base_dm
    if finite.any() and values[finite].max() > 32767:
        raise ValueError("the relief of the patch exceeds 3276.7 m")
    values = values.astype(np.int16)
    deltas = values.copy()
    deltas[:, 1:] = values[:, 1:] - values[:, :-1]  # int16 arithmetic wraps, the decoder wraps back
    return zlib.compress(deltas.astype("<i2").tobytes(), 9), base_dm


def decode_values(body: bytes, width: int, height: int) -> np.ndarray:
    """The int16 values (decimetres above base_dm, NO_DATA for no data) of a body."""
    deltas = np.frombuffer(zlib.decompress(body), dtype="<i2").reshape(height, width).astype(np.int64)
    return ((np.cumsum(deltas, axis=1) + 32768) % 65536 - 32768).astype(np.int16)


def decode(body: bytes, width: int, height: int, base_dm: int) -> np.ndarray:
    """Heights in metres, NaN for no data."""
    values = decode_values(body, width, height)
    return np.where(values == NO_DATA, np.nan, (values.astype(np.float64) + base_dm) / 10)


def values_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.astype("<i2").tobytes()).hexdigest()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")
    with rio.open(os.path.join(HERE, "zabi_kon_nmt.tif")) as src:
        heights = src.read(1)[:SIZE, :SIZE].astype(np.float64)
    heights[-HOLE:, -HOLE:] = np.nan
    body, base_dm = encode(heights)
    values = decode_values(body, SIZE, SIZE)
    back = decode(body, SIZE, SIZE, base_dm)
    finite = np.isfinite(heights)
    assert np.array_equal(np.isnan(back), ~finite) and np.abs(back[finite] - heights[finite]).max() <= 0.05 + 1e-9
    samples = [[0, 0], [256, 256], [100, 400], [SIZE - 1, 0], [SIZE - 1, SIZE - 1]]
    meta = {"width": SIZE, "height": SIZE, "base_dm": base_dm, "no_data": NO_DATA,
            "values_sha256": values_sha256(values), "body_bytes": len(body),
            "samples": [[r, c, None if np.isnan(back[r, c]) else round(float(back[r, c]), 1)] for r, c in samples]}
    with open(os.path.join(HERE, "patch_zabi_kon.bin"), "wb") as f:
        f.write(body)
    with open(os.path.join(HERE, "patch_zabi_kon.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")
    print(f"patch_zabi_kon.bin: {len(body)} bytes, base {base_dm} dm, values {meta['values_sha256'][:12]}")
