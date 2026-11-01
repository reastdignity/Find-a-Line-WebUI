"""Read a copy of proj.db: for each vertical CRS code given, the grid transformations whose target (or source)
is that vertical CRS, with their grid file names in PROJ-data (grid_alternatives) and accuracy."""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
codes = sys.argv[2:]
for code in codes:
    row = db.execute("SELECT name, datum_auth_name, datum_code FROM vertical_crs WHERE auth_name='EPSG' AND code=?",
                     (code,)).fetchone()
    print(f"== EPSG:{code} {row[0] if row else '(not a vertical CRS in proj.db)'}")
    rows = db.execute(
        "SELECT g.auth_name, g.code, g.name, g.source_crs_code, g.target_crs_code, g.grid_name, g.accuracy, "
        "g.deprecated FROM grid_transformation g WHERE (g.target_crs_auth_name='EPSG' AND g.target_crs_code=?) "
        "OR (g.source_crs_auth_name='EPSG' AND g.source_crs_code=?)", (code, code)).fetchall()
    for auth, tcode, name, src, tgt, grid, acc, dep in rows:
        alt = db.execute("SELECT proj_grid_name, open_license FROM grid_alternatives "
                         "WHERE original_grid_name=?", (grid,)).fetchone()
        print(f"   {auth}:{tcode} {name} | src {src} -> tgt {tgt} | grid {grid} -> {alt[0] if alt else '(no PROJ-data grid)'}"
              f" | acc {acc} | deprecated {dep}")
