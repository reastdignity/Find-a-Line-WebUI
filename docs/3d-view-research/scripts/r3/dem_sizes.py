"""Bytes of a 1.5 km x 1.5 km DEM patch at 1 m in the encodings a 3D view could fetch.

Reads cached GeoTIFFs of the data folder (read-only), mosaics the patch around a point, writes the
encodings into an output folder and prints their sizes. Usage:
    python -I dem_sizes.py <folder of GeoTIFFs> <x> <y> <out dir> [size_m]
(x, y in the CRS of the files). Our own data: no untrusted input.
"""
import glob
import gzip
import io
import os
import sys
import zlib

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds
from PIL import Image

folder, x, y, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
size = float(sys.argv[5]) if len(sys.argv) > 5 else 1500.0
res = float(sys.argv[6]) if len(sys.argv) > 6 else None
crs = sys.argv[7] if len(sys.argv) > 7 else "EPSG:2180"
os.makedirs(out, exist_ok=True)
half = size / 2
box = (x - half, y - half, x + half, y + half)
files = []
for f in glob.glob(os.path.join(folder, "**", "*.tif"), recursive=True):
    with rasterio.open(f) as d:
        b = d.bounds
        if b.left < box[2] and b.right > box[0] and b.bottom < box[3] and b.top > box[1]:
            files.append(f)
print(f"{len(files)} files overlap the box {box}")
arr, transform = merge(files, bounds=box, res=res, nodata=np.nan, dtype="float32")
z = arr[0]
print(f"patch {z.shape[1]} x {z.shape[0]} px, res {transform.a} m, nan {np.isnan(z).mean():.4f}, "
      f"min {np.nanmin(z):.2f} max {np.nanmax(z):.2f} m")
z = np.where(np.isnan(z), np.nanmin(z), z).astype("float32")
np.save(os.path.join(out, "patch.npy"), z)
n = z.size


def report(name, data: bytes):
    gz = gzip.compress(data, compresslevel=5)
    print(f"{name:42s} {len(data) / 1e6:7.2f} MB  gzip-5 {len(gz) / 1e6:6.2f} MB  ({len(gz) * 8 / n:.2f} bit/px)")


report("raw float32", z.tobytes())
lo = float(np.floor(z.min()))
cm = np.round((z - lo) * 100).astype("<u2")
report(f"uint16 cm above {lo:.0f} m", cm.tobytes())
dm = np.round((z - lo) * 10).astype("<u2")
report("uint16 dm", dm.tobytes())
# Byte planes split (high bytes, then low bytes) compress better with deflate
report("uint16 cm, byte planes", (cm >> 8).astype("u1").tobytes() + (cm & 255).astype("u1").tobytes())
# Horizontal delta of the cm values (a PNG/TIFF predictor) before deflate
delta = np.diff(cm.astype("int32"), axis=1, prepend=0).astype("<i2")
report("int16 cm, horizontal delta", delta.tobytes())
delta_dm = np.diff(dm.astype("int32"), axis=1, prepend=0).astype("<i2")
report("int16 dm, horizontal delta", delta_dm.tobytes())
print(f"share of values on whole cm: {np.mean(np.abs(z * 100 - np.round(z * 100)) < 1e-3):.3f}")


def png(name, rgb):
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    with open(os.path.join(out, "".join(c if c.isalnum() else "_" for c in name) + ".png"), "wb") as f:
        f.write(data)
    print(f"{name + ' PNG':42s} {len(data) / 1e6:7.2f} MB  ({len(data) * 8 / n:.2f} bit/px)")


v = np.round((z + 10000) * 10).astype("u4")  # Mapbox terrain-RGB: 0.1 m steps
png("terrain-RGB (0.1 m)", np.dstack([(v >> 16) & 255, (v >> 8) & 255, v & 255]).astype("u1"))
t = z + 32768.0  # Terrarium: R*256 + G + B/256 - 32768 (1/256 m steps)
r = np.floor(t / 256)
g = np.floor(t - r * 256)
b = np.clip(np.round((t - r * 256 - g) * 256), 0, 255)
png("terrarium (1/256 m)", np.dstack([r, g, b]).astype("u1"))
t = np.round(z * 10) / 10 + 32768.0  # Terrarium rounded to 0.1 m: fewer distinct low bytes
r = np.floor(t / 256)
g = np.floor(t - r * 256)
b = np.clip(np.round((t - r * 256 - g) * 256), 0, 255)
png("terrarium rounded to 0.1 m", np.dstack([r, g, b]).astype("u1"))

profile = dict(driver="GTiff", width=z.shape[1], height=z.shape[0], count=1, dtype="float32",
               crs=crs, transform=transform, tiled=True, blockxsize=256, blockysize=256)
variants = [("deflate pred3 float32", dict(compress="deflate", predictor=3, zlevel=6)),
            ("zstd pred3 float32", dict(compress="zstd", predictor=3)),
            ("LERC 1 cm", dict(compress="lerc", max_z_error=0.01)),
            ("LERC 5 cm", dict(compress="lerc", max_z_error=0.05)),
            ("LERC 10 cm", dict(compress="lerc", max_z_error=0.10)),
            ("LERC_DEFLATE 1 cm", dict(compress="lerc_deflate", max_z_error=0.01)),
            ("LERC_ZSTD 1 cm", dict(compress="lerc_zstd", max_z_error=0.01)),
            ("LERC_ZSTD 10 cm", dict(compress="lerc_zstd", max_z_error=0.10))]
for name, opts in variants:
    path = os.path.join(out, name.replace(" ", "_") + ".tif")
    try:
        with rasterio.open(path, "w", **profile, **opts) as d:
            d.write(z, 1)
        print(f"{'GeoTIFF ' + name:42s} {os.path.getsize(path) / 1e6:7.2f} MB  "
              f"({os.path.getsize(path) * 8 / n:.2f} bit/px)")
    except Exception as e:  # a GDAL build without LERC
        print(f"{'GeoTIFF ' + name:42s} failed: {e}")
