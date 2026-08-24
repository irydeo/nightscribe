############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: ephemeris exporters (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import csv

from nightscribe.core import ephemeris


def _mock_rows():
    # Simulated Horizons ephemeris rows (as generate() returns them after
    # enriching with alt/az; alt/az computed for a Madrid-like site)
    return [
        {"time": "2026-Aug-24 22:00", "ra": "12 00 00.0",
         "dec": "+40 00 00", "ra_deg": 180.0, "dec_deg": 40.0,
         "r": 1.5, "delta": 0.8, "alt": 45.2, "az": 180.0},
        {"time": "2026-Aug-24 23:00", "ra": "12 00 05.0",
         "dec": "+40 00 02", "ra_deg": 180.021, "dec_deg": 40.001,
         "r": 1.5, "delta": 0.8, "alt": 52.1, "az": 195.0},
        {"time": "2026-Aug-25 00:00", "ra": "12 00 10.0",
         "dec": "+40 00 04", "ra_deg": 180.042, "dec_deg": 40.002,
         "r": 1.5, "delta": 0.8, "alt": 55.0, "az": 210.0},
    ]


def test_export_csv(tmp_path):
    rows = _mock_rows()
    out = ephemeris.export_csv(rows, tmp_path / "eph.csv", "2021EQ3")
    with open(out, encoding="utf-8") as f:
        lines = f.readlines()
    assert "time" in lines[0]  # CSV header
    data = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(data) == 3
    assert data[0]["ra_deg"] == "180.0"
    assert data[0]["alt"] == "45.2"


def test_export_skyx(tmp_path):
    rows = _mock_rows()
    out = ephemeris.export_skyx(rows, tmp_path / "eph.txt", "2021EQ3")
    text = open(out, encoding="utf-8").read()
    assert "2021EQ3" in text
    assert "180.000000" in text
    assert "45.2" in text
    assert "RA(deg)" in text


def test_export_cdc(tmp_path):
    rows = _mock_rows()
    out = ephemeris.export_cdc(rows, tmp_path / "eph.txt", "2021EQ3")
    text = open(out, encoding="utf-8").read()
    assert "2021EQ3" in text
    assert "12 00 00.0" in text
    assert "Cartes du Ciel" in text


def test_export_dispatcher(tmp_path):
    rows = _mock_rows()
    out = ephemeris.export(rows, tmp_path / "eph", fmt="csv", obj_name="X")
    assert out.endswith(".csv")
    out = ephemeris.export(rows, tmp_path / "eph", fmt="skyx", obj_name="X")
    assert out.endswith(".txt")
    out = ephemeris.export(rows, tmp_path / "eph", fmt="cdc", obj_name="X")
    assert out.endswith(".txt")
