"""Horizontal and vertical shift between the national frames of our sources and ITRF2020 (≈ WGS 84
(G2296)) at sample points, epoch 2026.8, with pyproj's own Helmert parameters (no grids, network off)."""
import math

from pyproj import Transformer, network

network.set_network_enabled(False)
EPOCH = 2026.8
CASES = [
    ("ETRF2000 (ETRS89 realisation of PL)", "EPSG:7931", (50.1559508, 19.7562722, 400.0)),
    ("ETRF2000 at Lauterbrunnen", "EPSG:7931", (46.59, 7.91, 1500.0)),
    ("ETRF2000 at the Tatras (SK)", "EPSG:7931", (49.18, 20.10, 1500.0)),
    ("NAD83(2011) at Yosemite", "EPSG:6319", (37.75, -119.55, 1500.0)),
    ("NAD83(2011) at Indian Creek UT", "EPSG:6319", (38.03, -109.55, 1500.0)),
]
for label, src, (lat, lon, h) in CASES:
    t = Transformer.from_crs(src, "EPSG:9989", always_xy=True)  # ITRF2020 geographic 3D
    x, y, z, _ = t.transform(lon, lat, h, EPOCH)
    dn = (y - lat) * 111320.0
    de = (x - lon) * 111320.0 * math.cos(math.radians(lat))
    print(f"{label}: dE {de:+.3f} m dN {dn:+.3f} m (horizontal {math.hypot(de, dn):.3f} m), dh {z - h:+.3f} m"
          f"  via: {t.description}")
