"""tools/wesm_summary.py on a small WESM fixture (no network)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import wesm_summary  # noqa: E402

COLUMNS = ("workunit,p_method,dem_gsd_meters,horiz_crs,vert_crs,onemeter_category,onemeter_reason,"
           "sourcedem_link")
ROWS = [
    # chosen: no 1 m DEM, lidar, OPR linked
    "OR_Coast_2016,linear-mode lidar,0.5,6339,5703,Does not meet,LPC does not meet,https://x/OPR/a",
    "IN_County_2011,linear-mode lidar,1.524,2965,6360,Does not meet,LPC does not meet,https://x/OPR/b",
    "Il_Rock_2009,linear-mode lidar,,3435,8228,Pending publication,Awaiting,https://x/OPR/c",
    "HI_Volcano_2019,Geiger-mode LIDAR,0.762001524003048,Custom,Unknown,Does not meet,LPC does not meet,https://x/d",
    "FL_Glades_2018,Topobathymetric LIDAR,3,6350,Ellipsoidal,Does not meet,LPC does not meet,https://x/e",
    "IL_Knox_2014,linear-mode lidar,2,4269,5703,Does not meet,LPC does not meet,https://x/f",
    # left out: a 1 m DEM, IfSAR, no OPR link
    "UT_Meets_2020,linear-mode lidar,1,6341,5703,Meets,Meets,https://x/g",
    "UT_Variance_2019,linear-mode lidar,1,6341,5703,Meets with variance,v,https://x/h",
    "AK_IFSAR_2010,Ifsar,5,3338,5703,Does not meet,LPC does not meet,https://x/i",
    "OR_NoLink_2012,linear-mode lidar,1,6339,5703,Does not meet,LPC does not meet,",
]


def _csv(tmp_path):
    path = tmp_path / "WESM.csv"
    path.write_text("﻿" + COLUMNS + "\n" + "\n".join(ROWS) + "\n", encoding="utf-8")
    return str(path)


def test_counts_of_the_chosen_surveys(tmp_path):
    result = wesm_summary.summary(wesm_summary.read_csv(_csv(tmp_path)))
    by = result["by"]
    assert result["surveys"] == 6
    assert by["status"] == {"Does not meet": 5, "Pending publication": 1}
    assert by["height_unit"] == {"metre": 2, "unknown": 2, "US survey foot": 1, "foot": 1}
    assert by["vertical"] == {"height": 4, "not a height": 2}
    assert by["crs_kind"] == {"UTM": 1, "State Plane": 2, "not EPSG": 1, "Albers": 1, "geographic": 1}
    assert by["pixel"] == {"to 0.76 m": 2, "coarser": 1, "to 2 m": 2, "not given": 1}
    assert by["state"] == {"OR": 1, "IN": 1, "IL": 2, "HI": 1, "FL": 1}
    rows = {r["workunit"]: r for r in result["rows"]}
    assert rows["IN_County_2011"]["horizontal_unit"] == "US survey foot"
    assert rows["Il_Rock_2009"]["state"] == "IL"


def test_all_takes_every_lidar_survey_with_an_opr_dem(tmp_path):
    result = wesm_summary.summary(wesm_summary.read_csv(_csv(tmp_path)), everything=True)
    assert result["surveys"] == 8
    assert result["by"]["status"]["Meets"] == 1 and result["by"]["status"]["Meets with variance"] == 1


def test_the_command_line_writes_the_json(tmp_path, capsys):
    out = tmp_path / "summary.json"
    assert wesm_summary.main(["--csv", _csv(tmp_path), "--json", str(out)]) == 0
    assert "Surveys: 6" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["surveys"] == 6
