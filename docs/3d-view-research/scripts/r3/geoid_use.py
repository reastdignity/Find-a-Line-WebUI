"""Can pyproj 3.8 with the network off convert a source's height to a WGS 84 ellipsoidal height with
one grid file placed in an extra data folder? Which operation does it choose, with and without the
national grid? Usage: python -I geoid_use.py <grid dir>"""
import sys

import pyproj
from pyproj import Transformer, network
from pyproj.transformer import TransformerGroup

network.set_network_enabled(False)
grid_dir = sys.argv[1]
# Żabi Koń, Lauterbrunnen, the Tatras, Yosemite as (source CRS of the line's heights, lon, lat, H)
POINTS = [("EPSG:4326+9651", 19.7562722, 50.1559508, 400.0, "Poland, PL-EVRF2007-NH (EPSG:9651)"),
          ("EPSG:4326+5728", 7.91, 46.59, 1500.0, "Switzerland, LN02 (EPSG:5728)"),
          ("EPSG:4326+8357", 20.10, 49.18, 1500.0, "Slovakia, Baltic 1957 / Bpv (EPSG:8357)"),
          ("EPSG:4326+5703", -119.55, 37.75, 1500.0, "USA, NAVD88 (EPSG:5703)"),
          ("EPSG:4326+3855", 19.7562722, 50.1559508, 400.0, "World, EGM2008 (EPSG:3855)")]


def run(label):
    print(f"--- {label}: data dirs {pyproj.datadir.get_data_dir()}")
    for src, lon, lat, H, name in POINTS:
        group = TransformerGroup(src, "EPSG:4979", always_xy=True)
        best = group.transformers[0] if group.transformers else None
        missing = [op.name for op in group.unavailable_operations][:2]
        if best is None:
            print(f"{name}: no available operation; unavailable: {missing}")
            continue
        x, y, h = best.transform(lon, lat, H)
        print(f"{name}: h = {h:.3f} m (N = {h - H:+.3f}), best available: {best.description[:150]!r} "
              f"accuracy {best.accuracy} m; best_available={group.best_available}; unavailable first: {missing}")


run("pyproj's data only (no grids)")
pyproj.datadir.append_data_dir(grid_dir)
run("with the grid folder appended")
