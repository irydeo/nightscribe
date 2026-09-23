############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: photometry export (Track V, VD.4/VD.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import followup, photometry_export
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _pid_with_points(db):
    from nightscribe.core import project
    p = project.create(db, "variable", "WeSb 1",
                       {"ra_deg": 15.2254, "dec_deg": 55.0667})
    for i, m in enumerate((15.10, 15.12, 15.09)):
        followup.add_point(db, p["id"], 59650.94800 + i, "V", m, err=0.02)
    followup.add_point(db, p["id"], 59660.0, "V", 15.2, source="quicklook")
    return p["id"]


def test_collect_points_excludes_quicklook_by_default(db):
    pid = _pid_with_points(db)
    assert len(photometry_export.collect_points(db, pid)) == 3
    assert len(photometry_export.collect_points(db, pid,
                                                include_quicklook=True)) == 4


def test_collect_points_includes_measure_by_default(db):
    # ADR-044: a point saved from the editor's measure tab is the
    # observer's own calibrated data and belongs in the campaign report;
    # only "quicklook" stays out by default (it is indicative).
    pid = _pid_with_points(db)
    followup.add_point(db, pid, 59665.5, "V", 15.3, source="measure")
    pts = photometry_export.collect_points(db, pid)
    assert len(pts) == 4
    assert any(pt["source"] == "measure" for pt in pts)
    assert all(pt["source"] != "quicklook" for pt in pts)


def test_csv_columns_and_hjd(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.csv"
    photometry_export.export_csv(pts, out, "WeSb 1", ra_deg=15.2254,
                                 dec_deg=55.0667, observer="ZABC",
                                 comp_stars=["C1", "C2"])
    lines = out.read_text().splitlines()
    assert lines[0] == "# name: WeSb 1"
    assert lines[2] == "name,hjd,mag,err,filter,comp_stars,observer,notes"
    row = lines[3].split(",")
    assert row[0] == "WeSb 1"
    # frozen reference: MJD 59650.94800 -> JD 2459651.448 -> HJD corr known
    # within 30 s of +250.09 s at JD 2459653.448 (same geometry, 2 d apart)
    hjd = float(row[1])
    corr_s = (hjd - (59650.94800 + 2400000.5)) * 86400
    assert corr_s == pytest.approx(250.09, abs=30.0)
    assert row[2] == "15.100" and row[3] == "0.020" and row[4] == "V"
    assert row[5] == "C1+C2" and row[6] == "ZABC"


def test_csv_without_coordinates_leaves_hjd_empty(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.csv"
    photometry_export.export_csv(pts, out, "WeSb 1")
    row = out.read_text().splitlines()[3].split(",")
    assert row[1] == ""


def test_eff_header_and_rows(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(pts, out, "WeSb 1", ra_deg=15.2254,
                                 dec_deg=55.0667, obscode="ZABC")
    lines = out.read_text().splitlines()
    assert lines[:6] == ["#TYPE=EXTENDED", "#OBSCODE=ZABC",
                         "#SOFTWARE=NightScribe", "#DELIM=,", "#DATE=HJD",
                         "#OBSTYPE=CCD"]
    assert lines[6] == photometry_export.EFF_FIELDS
    row = lines[7].split(",")
    assert row[0] == "WESB 1"                    # upper-cased
    assert row[2] == "15.100" and row[3] == "0.020" and row[4] == "V"
    assert row[5] == "NA" and row[6] == "STD"
    assert len(row) == 15
    assert len(lines) == 10                       # 7 header + 3 rows


def test_eff_skips_points_without_hjd(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(pts, out, "WeSb 1")   # no coords
    assert len(out.read_text().splitlines()) == 7      # header only


def test_export_report_dispatch(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    o1 = photometry_export.export_report(pts, tmp_path / "a.csv", fmt="csv",
                                         name="WeSb 1")
    o2 = photometry_export.export_report(pts, tmp_path / "a.txt", fmt="eff",
                                         name="WeSb 1", obscode="ZABC")
    assert o1.exists() and o2.exists()


def test_eff_fills_comp_and_check_from_the_sequence(db, tmp_path):
    # ADR-042: a saved sequence lands in CNAME/CMAG/KNAME/KMAG
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(
        pts, out, "WeSb 1", ra_deg=15.2254, dec_deg=55.0667,
        obscode="ZABC", comp={"name": "Comp1", "mag": 12.34},
        check={"name": "Check", "mag": 11.98})
    row = out.read_text().splitlines()[7].split(",")
    assert row[7] == "Comp1" and row[8] == "12.340"
    assert row[9] == "Check" and row[10] == "11.980"


def test_eff_without_sequence_keeps_na(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(pts, out, "WeSb 1", ra_deg=15.2254,
                                 dec_deg=55.0667)
    row = out.read_text().splitlines()[7].split(",")
    assert row[7:11] == ["na", "na", "na", "na"]
    # a comp without magnitude writes "na" in the mag cell, never "None"
    photometry_export.export_eff(
        pts, out, "WeSb 1", ra_deg=15.2254, dec_deg=55.0667,
        comp={"name": "Comp1", "mag": None})
    row = out.read_text().splitlines()[7].split(",")
    assert row[7] == "Comp1" and row[8] == "na"
