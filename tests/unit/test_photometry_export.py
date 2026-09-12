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
