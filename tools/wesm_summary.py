"""
A summary of USGS's WESM table (the Work Unit Extent Spatial Metadata: one row per 3DEP survey, "work unit",
https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.csv, rewritten daily): which lidar surveys
have an OPR DEM ("source DEM", a `sourcedem_link`) and in what form, for the plan "OPR DEMs for the USA"
(local notes of 2026-11-22).

By default it counts the lidar surveys (`p_method` names lidar: IfSAR left out) with a `sourcedem_link` whose
`onemeter_category` is neither "Meets" nor "Meets with variance", the surveys whose OPR DEM may be the only lidar
terrain of their place (357 on 2026-11-22); `--all` counts every lidar survey with a `sourcedem_link` (2207 then).
The counts are by:

- the 1 m DEM's status (`onemeter_category`) and its reason (`onemeter_reason`);
- the height unit: the unit of `vert_crs` as an EPSG vertical CRS (pyproj: EPSG:5703 metres, 6360 US survey feet,
  8228 international feet), "unknown" when `vert_crs` is no EPSG vertical CRS ("Unknown", "Ellipsoidal", a text);
- the kind of vertical CRS: "height" (an EPSG vertical CRS, a height above a geoid or a local datum) or "not a
  height" (anything else: such a survey's heights cannot be scaled to metres from WESM alone);
- the kind of horizontal CRS from `horiz_crs` as an EPSG code: "UTM", "State Plane" (an SPCS conversion), "Albers",
  "other projected", "geographic", or "not EPSG" (no code pyproj knows: "Custom"); and its unit;
- the pixel class of `dem_gsd_meters`: to 0.7621 m (2.5 ft), to 1 m, to 2 m, coarser, not given;
- the state: the two letters before the first "_" of `workunit`, upper case (other names count as "other").

Read-only; the network only when --csv is an http(s) address (one GET with the app's User-Agent).

    python tools/wesm_summary.py [--csv FILE_OR_URL] [--all] [--json FILE]

--csv defaults to WESM's address. The output is one table per count; --json writes the counts and the rows' classes.
"""

import argparse
import collections
import csv
import io
import json
import os
import re
import sys
from typing import Dict, Iterable, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WESM_URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.csv"
MEETS = ("Meets", "Meets with variance")
# The bounds of the pixel classes in metres (2.5 ft, also in US survey feet: 0.762002; 1 m; 2 m), each class up
# to and with its bound
PIXEL_CLASSES = ((0.7621, "to 0.76 m"), (1.0, "to 1 m"), (2.0, "to 2 m"))


def _crs(code: str):
    """The pyproj CRS of an EPSG code given as text, None when it is no code pyproj knows."""
    from pyproj import CRS
    from pyproj.exceptions import CRSError
    code = (code or "").strip().strip('"')
    if not code.isdigit():
        return None
    try:
        return CRS.from_epsg(int(code))
    except CRSError:
        return None


_horizontal_cache: Dict[str, Dict[str, str]] = {}
_vertical_cache: Dict[str, Dict[str, str]] = {}


def horizontal(code: str) -> Dict[str, str]:
    """{kind, unit, name} of a `horiz_crs` value."""
    if code not in _horizontal_cache:
        crs = _crs(code)
        if crs is None:
            info = {"kind": "not EPSG", "unit": "unknown", "name": (code or "").strip()}
        elif crs.is_geographic:
            info = {"kind": "geographic", "unit": "degree", "name": crs.name}
        else:
            conversion = crs.coordinate_operation.name if crs.coordinate_operation else ""
            method = crs.coordinate_operation.method_name if crs.coordinate_operation else ""
            if conversion.startswith("UTM zone"):
                kind = "UTM"
            elif conversion.startswith("SPCS"):
                kind = "State Plane"
            elif "Albers" in method:
                kind = "Albers"
            else:
                kind = "other projected"
            info = {"kind": kind, "unit": crs.axis_info[0].unit_name if crs.axis_info else "unknown", "name": crs.name}
        _horizontal_cache[code] = info
    return _horizontal_cache[code]


def vertical(code: str) -> Dict[str, str]:
    """{kind, unit, name} of a `vert_crs` value: "height" with the unit of an EPSG vertical CRS, else
    "not a height" with the unit "unknown"."""
    if code not in _vertical_cache:
        crs = _crs(code)
        if crs is None or not crs.is_vertical:
            info = {"kind": "not a height", "unit": "unknown", "name": (code or "").strip()}
        else:
            unit = crs.axis_info[0].unit_name if crs.axis_info else "unknown"
            info = {"kind": "height", "unit": unit, "name": crs.name}
        _vertical_cache[code] = info
    return _vertical_cache[code]


def pixel_class(gsd: str) -> str:
    try:
        value = float(gsd)
    except (TypeError, ValueError):
        return "not given"
    for bound, name in PIXEL_CLASSES:
        if value <= bound + 1e-9:
            return name
    return "coarser"


def state(workunit: str) -> str:
    match = re.match(r"([A-Za-z]{2})_", workunit or "")
    return match.group(1).upper() if match else "other"


def is_lidar(row: Dict[str, str]) -> bool:
    return "lidar" in (row.get("p_method") or "").lower()


def selected(rows: Iterable[Dict[str, str]], everything: bool = False) -> List[Dict[str, str]]:
    """The lidar surveys with an OPR DEM; without everything only those whose 1 m DEM status is not a "Meets"."""
    return [r for r in rows if is_lidar(r) and (r.get("sourcedem_link") or "").strip()
            and (everything or (r.get("onemeter_category") or "") not in MEETS)]


def classes(row: Dict[str, str]) -> Dict[str, str]:
    """The classes a survey is counted by."""
    h, v = horizontal(row.get("horiz_crs", "")), vertical(row.get("vert_crs", ""))
    return {"workunit": row.get("workunit", ""), "status": row.get("onemeter_category", ""),
            "reason": (row.get("onemeter_reason") or "").strip(), "height_unit": v["unit"], "vertical": v["kind"],
            "vertical_name": v["name"], "crs_kind": h["kind"], "horizontal_unit": h["unit"],
            "horizontal_name": h["name"], "pixel": pixel_class(row.get("dem_gsd_meters", "")),
            "state": state(row.get("workunit", ""))}


COUNTS = ("status", "reason", "height_unit", "vertical", "crs_kind", "horizontal_unit", "pixel", "state")


def summary(rows: Iterable[Dict[str, str]], everything: bool = False) -> Dict:
    """{"surveys": n, "by": {count: {value: n}}, "rows": [classes]} of the selected surveys."""
    chosen = [classes(r) for r in selected(rows, everything)]
    by = {name: dict(collections.Counter(c[name] for c in chosen).most_common()) for name in COUNTS}
    by["crs_count"] = len({c["horizontal_name"] for c in chosen})
    return {"surveys": len(chosen), "by": by, "rows": chosen}


def read_csv(source: str) -> List[Dict[str, str]]:
    """WESM's rows from a file or an http(s) address."""
    if source.startswith(("http://", "https://")):
        import requests

        import cache
        response = requests.get(source, headers=cache.http_headers(), timeout=300)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig")
    else:
        with open(source, encoding="utf-8-sig", newline="") as f:
            text = f.read()
    return list(csv.DictReader(io.StringIO(text)))


def report(result: Dict) -> str:
    lines = [f"Surveys: {result['surveys']}  (horizontal CRSs: {result['by']['crs_count']})"]
    for name in COUNTS:
        lines.append(f"\nBy {name}:")
        for value, n in result["by"][name].items():
            lines.append(f"  {n:5d}  {value or '(empty)'}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=WESM_URL, help="WESM.csv: a file or an http(s) address (default: USGS's)")
    parser.add_argument("--all", action="store_true", help="every lidar survey with an OPR DEM, any 1 m status")
    parser.add_argument("--json", help="write the counts and the rows' classes here")
    args = parser.parse_args(argv)
    result = summary(read_csv(args.csv), args.all)
    print(report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    return 0


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
