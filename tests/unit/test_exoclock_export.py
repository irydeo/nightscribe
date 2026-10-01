############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: ExoClock export (series plan, phase 8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-8 acceptance: the HOPS three-column data file and ExoClock_info,
with the exposure-start convention (D15/D19) and the blocking rule for a
missing EXPTIME. No network."""

import math
from pathlib import Path

import pytest

from nightscribe.core import exoclock_export as ex
from nightscribe.core import variables


def _points():
    return [
        {"mjd": 58107.065, "mag": 12.500, "err": 0.010, "exptime": 60.0,
         "filter": "V", "flags": []},
        {"mjd": 58107.075, "mag": 12.520, "err": 0.012, "exptime": 60.0,
         "filter": "V", "flags": []},
        {"mjd": 58107.085, "mag": 12.510, "err": 0.011, "exptime": 60.0,
         "filter": "V", "flags": ["cloud"]},
    ]


def test_data_columns_and_rows():
    rows, warnings, _mode = ex.build_data(_points())
    assert warnings == []
    assert len(rows) == 3
    text = ex.format_data(rows)
    lines = text.strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        assert len(line.split()) == 3


def test_start_is_the_exposure_start():
    # D15: the exported instant is the START = mid - EXPTIME/2.
    pts = _points()
    rows, _w, _m = ex.build_data(pts)
    expected = (pts[0]["mjd"] - 30.0 / 86400.0) + variables.MJD0
    assert rows[0][0] == pytest.approx(expected, abs=1e-9)


def test_grouping_uses_the_total_integration():
    # D19: with grouping the start is the group mean minus the total
    # integration over two; the point's exptime carries that total.
    pts = [{"mjd": 58107.065, "mag": 12.5, "err": 0.01, "exptime": 300.0,
            "flags": []}]
    rows, _w, _m = ex.build_data(pts)
    expected = (58107.065 - 150.0 / 86400.0) + variables.MJD0
    assert rows[0][0] == pytest.approx(expected, abs=1e-9)


def test_missing_exptime_cannot_be_exported():
    pts = _points()
    pts[1]["exptime"] = None
    rows, warnings, _mode = ex.build_data(pts)
    assert len(rows) == 2                      # the point is refused
    assert any("EXPTIME" in w for w in warnings)


def test_flux_is_normalised_and_dips():
    pts = _points()
    pts[1]["mag"] = 12.6                      # a deeper point
    rows, _w, _m = ex.build_data(pts)
    fluxes = [r[1] for r in rows]
    # the baseline is ~1 and the deeper point is fainter (flux < 1)
    assert fluxes[1] < fluxes[0]
    assert fluxes[0] == pytest.approx(1.0, abs=0.05)


def test_reference_is_the_mean_oot_flux():
    # Review #24: a series with a known OOT level and a 1 % dip; with
    # more in-transit than OOT points the median of magnitudes would sit
    # INSIDE the dip and bias the baseline. The mean OOT flux does not.
    t0 = 58107.100
    dur_d = 2.0 / 24.0
    pts = []
    # 4 OOT points at 12.500, 6 in-transit points at 12.511 (1 % dip)
    for i in range(4):
        pts.append({"mjd": t0 - 0.08 - i * 0.01, "mag": 12.500,
                    "err": 0.01, "exptime": 60.0, "flags": []})
    for i in range(6):
        pts.append({"mjd": t0 - 0.03 + i * 0.012, "mag": 12.500
                    - 2.5 * math.log10(0.99), "err": 0.01,
                    "exptime": 60.0, "flags": []})
    rows, _w, mode = ex.build_data(pts, t0_mjd=t0, duration_d=dur_d)
    assert mode == "oot"
    oot_flux = [r[1] for r in rows[:4]]
    dip_flux = [r[1] for r in rows[4:]]
    for f in oot_flux:
        assert f == pytest.approx(1.0, abs=1e-9)
    for f in dip_flux:
        assert f == pytest.approx(0.99, abs=1e-3)
    # without the window the reference is the whole-series mean flux,
    # said out loud (never the median of mags)
    rows2, _w2, mode2 = ex.build_data(pts)
    assert mode2 == "series"
    mean_flux = (4 * 1.0 + 6 * 0.99) / 10.0
    assert rows2[0][1] == pytest.approx(1.0 / mean_flux, rel=1e-3)


def test_comments_say_where_the_baseline_hangs(tmp_path):
    data = tmp_path / "WASP-52b.txt"
    _d, ipath = ex.write_submission(_points(), data, "WASP-52 b", "V",
                                    60.0, "Transit covered well.")
    assert "reference flux: mean of the whole series" \
        in ipath.read_text()


def test_info_file_fields(tmp_path):
    data = tmp_path / "HATP-32b.txt"
    dpath, ipath = ex.write_submission(_points(), data, "HAT-P-32 b", "V",
                                       60.0, "Transit covered well.")
    assert dpath.exists() and ipath.exists()
    assert ipath.name == "ExoClock_info.txt"      # the name ExoClock reads
    assert ipath.parent == dpath.parent           # next to the data file
    info = ipath.read_text()
    assert "Planet: HAT-P-32 b" in info
    assert "Time format: JD_UTC" in info
    assert "Time stamp: Exposure start" in info
    assert "Flux format: Flux" in info
    assert "Filter: V" in info
    assert "Exposure time: 60.0" in info
    assert "Comments: Transit covered well." in info
    assert len(dpath.read_text().strip().splitlines()) == 3


def test_comments_must_be_non_empty_by_contract():
    # the checklist/UI always prefills the honest self-assessment; an
    # empty string is still written (the field is never dropped)
    info = ex.build_info("HAT-P-32 b", "V", 60.0, "")
    assert "Comments:" in info


def test_checklist_levels():
    pts = _points()
    rep = ex.checklist(pts)
    assert rep["level"] in ("ok", "warn")
    # no magnitudes at all is a blocker
    none = [dict(p, mag=None) for p in pts]
    assert ex.checklist(none)["level"] == "red"
    # a flagged point warns
    rep2 = ex.checklist(pts)
    assert any("marca" in m["es"] or "flag" in m["en"]
               for m in rep2["messages"])
