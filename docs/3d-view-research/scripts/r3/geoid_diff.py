"""How far EGM2008 (and EGM96) are from the national geoid models of PROJ-data, at the nodes of each
national grid: the error of using the global model for an orthometric/normal height of a source.
Reads downloaded GeoTIFF grids as data only. Usage: python -I geoid_diff.py <grid dir> <files.geojson>"""
import hashlib
import json
import os
import sys

import numpy as np
import rasterio

folder, index = sys.argv[1], sys.argv[2]
with open(index, encoding="utf-8") as f:
    sums = {feat["properties"]["name"]: feat["properties"].get("sha256sum")
            for feat in json.load(f)["features"]}
for name in sorted(os.listdir(folder)):
    if name.endswith(".tif"):
        with open(os.path.join(folder, name), "rb") as f:
            ok = hashlib.sha256(f.read()).hexdigest() == sums.get(name)
        print(f"sha256 {'ok' if ok else 'MISMATCH'}: {name}")


def load(name):
    with rasterio.open(os.path.join(folder, name)) as d:
        a = d.read(1).astype("float64")
        nodata = d.nodata
        tags = {k: v for k, v in d.tags().items() if k in ("TYPE", "AREA_OR_POINT", "positive_value")}
        btags = d.tags(1)
        desc = d.descriptions
        t = d.transform
        crs = d.crs
    if nodata is not None:
        a[a == nodata] = np.nan
    a[np.abs(a) > 1000] = np.nan
    return a, t, tags, btags, desc, crs


def bilinear(a, t, lon, lat):
    col = (lon - t.c) / t.a - 0.5
    row = (lat - t.f) / t.e - 0.5
    c0 = np.floor(col).astype(int)
    r0 = np.floor(row).astype(int)
    fc, fr = col - c0, row - r0
    c0 %= a.shape[1]
    c1 = (c0 + 1) % a.shape[1]
    r1 = np.clip(r0 + 1, 0, a.shape[0] - 1)
    r0 = np.clip(r0, 0, a.shape[0] - 1)
    return (a[r0, c0] * (1 - fc) * (1 - fr) + a[r0, c1] * fc * (1 - fr)
            + a[r1, c0] * (1 - fc) * fr + a[r1, c1] * fc * fr)


egm08, t08, tags08, b08, d08, _ = load("us_nga_egm08_25.tif")
egm96, t96, tags96, b96, d96, _ = load("us_nga_egm96_15.tif")
print("EGM2008 tags", tags08, b08, d08, "EGM96 tags", tags96)
for name, label in (("pl_gugik_geoid2021-PL-EVRF2007-NH.tif", "PL-geoid2021 (PL-EVRF2007-NH)"),
                    ("ch_swisstopo_chgeo2004_ETRS89_LN02.tif", "CHGeo2004 (LN02)"),
                    ("sk_gku_Slovakia_ETRS89h_to_Baltic1957.tif", "Slovakia (Bpv, Baltic 1957)"),
                    ("es_ign_egm08-rednap.tif", "EGM08-REDNAP (Alicante)"),
                    ("us_noaa_g2018u0.tif", "GEOID18 CONUS (NAVD88, on NAD83(2011))")):
    a, t, tags, btags, desc, crs = load(name)
    rows, cols = np.nonzero(np.isfinite(a))
    lon = t.c + (cols + 0.5) * t.a
    lat = t.f + (rows + 0.5) * t.e
    nat = a[rows, cols]
    print(f"\n{label}: {name}  crs={crs}  tags={tags} band={btags} desc={desc}")
    print(f"  {len(nat)} nodes, spacing {abs(t.a) * 60:.2f}' x {abs(t.e) * 60:.2f}', national N {nat.min():.2f}..{nat.max():.2f} m")
    for gname, g, tg in (("EGM2008", egm08, t08), ("EGM96", egm96, t96)):
        d = bilinear(g, tg, lon, lat) - nat
        d = d[np.isfinite(d)]
        p = np.percentile(d, [1, 5, 50, 95, 99])
        print(f"  {gname} - national: mean {d.mean():+.3f} m, std {d.std():.3f} m, min {d.min():+.3f}, max {d.max():+.3f}, "
              f"p1/p5/p50/p95/p99 {' / '.join(f'{x:+.2f}' for x in p)}; spread after removing the mean "
              f"p99-p1 {p[4] - p[0]:.2f} m")
