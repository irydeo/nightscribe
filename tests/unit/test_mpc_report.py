############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC report validator (ADR-022)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import mpc_report


# A valid MPC 80-column observation line for Z41 (exactly 80 chars)
# cols 1-5: packed desig, 6-12: spaces, 13: note, 14-15: note2,
# 16-32: date, 33-44: RA, 45-45: Dec, 57-65: spaces, 66-70: mag,
# 71-72: band, 73-77: spaces, 78-80: station
_MPC80_GOOD = (
    "J01EQ"        # 1-5   (5)
    "       "      # 6-12  (7)
    " "             # 13    (1)
    "  "            # 14-15 (2)
    "2021 03 15.123456"  # 16-32 (17)
    "21 30 45.678"  # 33-44 (12)
    "+12 34 56.78"  # 45-56 (12)
    "         "     # 57-65 (9)
    "18.0 "          # 66-70 (5)
    "V "             # 71-72 (2)
    "     "          # 73-77 (5)
    "Z41"            # 78-80 (3)
)
# same but with wrong station code
_MPC80_BAD_STATION = _MPC80_GOOD[:77] + "500"
# too short
_MPC80_SHORT = "J01EQ3  too short"


def _mpc80_block(*lines):
    return "\n".join(lines)


def test_detect_mpc80():
    fmt = mpc_report.detect_format(_MPC80_GOOD)
    assert fmt == "mpc80"


def test_detect_ades():
    ades = ("objid|provID|mode|stn|obsTime|ra|dec\n"
            "J01EQ3|2021EQ3|CCD|Z41|2021-03-15T12:00:00|323.23|+12.58")
    assert mpc_report.detect_format(ades) == "ades"


def test_detect_unknown():
    assert mpc_report.detect_format("# only comments\n\n") is None


def test_validate_mpc80_good():
    text = _mpc80_block(_MPC80_GOOD, _MPC80_GOOD)
    r = mpc_report.validate(text, obs_code="Z41")
    assert r["format"] == "mpc80"
    assert r["valid"] is True
    assert r["n_lines"] == 2
    assert len(r["errors"]) == 0


def test_validate_mpc80_bad_station():
    r = mpc_report.validate(_mpc80_block(_MPC80_BAD_STATION), obs_code="Z41")
    assert r["valid"] is False
    assert any("Z41" in e for e in r["errors"])


def test_validate_mpc80_short():
    r = mpc_report.validate(_mpc80_block(_MPC80_SHORT))
    assert r["valid"] is False
    assert any("too short" in e for e in r["errors"])


def test_validate_ades_good():
    text = ("objid|provID|mode|stn|obsTime|ra|dec\n"
            "J01EQ3|2021EQ3|CCD|Z41|2021-03-15T12:00:00|323.23|+12.58\n"
            "J01EQ3|2021EQ3|CCD|Z41|2021-03-15T12:01:00|323.24|+12.59")
    r = mpc_report.validate(text, obs_code="Z41")
    assert r["format"] == "ades"
    assert r["valid"] is True
    assert r["n_lines"] == 2


def test_validate_ades_missing_field():
    text = ("objid|mode|stn|obsTime|ra|dec\n"
            "J01EQ3|CCD|Z41|2021-03-15T12:00:00|323.23|+12.58")
    r = mpc_report.validate(text, obs_code="Z41")
    # no provID column — but objid is present, so it's OK
    assert r["valid"] is True


def test_package_writes_file(tmp_path):
    text = _mpc80_block(_MPC80_GOOD)
    out = tmp_path / "report.txt"
    path, result = mpc_report.package(text, out, obs_code="Z41")
    assert path is not None
    assert result["valid"] is True
    content = open(path, encoding="ascii", errors="replace").read()
    assert "J01EQ" in content
    assert "Z41" in content


def test_package_rejects_invalid(tmp_path):
    text = _mpc80_block(_MPC80_SHORT)
    out = tmp_path / "bad.txt"
    path, result = mpc_report.package(text, out, obs_code="Z41")
    assert path is None
    assert result["valid"] is False


def test_designations_collected():
    text = _mpc80_block(_MPC80_GOOD, _MPC80_GOOD)
    r = mpc_report.validate(text, obs_code="Z41")
    assert "J01EQ" in r["designations"]


def test_first_obs_date_mpc80():
    assert mpc_report.first_obs_date(_MPC80_GOOD) == "2021-03-15"


def test_first_obs_date_ades():
    ades = ("objid|provID|mode|stn|obsTime|ra|dec\n"
            "J01EQ3|2021EQ3|CCD|Z41|2021-03-15T12:00:00|323.23|+12.58")
    assert mpc_report.first_obs_date(ades) == "2021-03-15"


def test_first_obs_date_none_on_garbage():
    assert mpc_report.first_obs_date("# nothing\n") is None
    assert mpc_report.first_obs_date("not a report line") is None
