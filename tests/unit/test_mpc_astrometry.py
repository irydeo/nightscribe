############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC astrometry report generators (ADR-062)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A7 / A15: the generators and the validator must agree (offline).

The key test is the round trip: what core.mpc_astrometry emits has to pass
core.mpc_report.validate, the same judge the user's pasted measurements pass.
If the generator and the validator disagree, the bug is ours, not the user's.
"""

from dataclasses import dataclass

import pytest

from nightscribe.core import mpc_astrometry as mpc
from nightscribe.core import mpc_report


# MJD 59288.5 = JD 2459289.0 = 2021-03-15 12:00:00 UTC, a clean T_mid.
_MJD = 59288.5
# RA 21h30m45.678s and Dec -12d34m56.78s, written so the sexagesimal
# expectation is exact and the negative sign is exercised.
_RA_DEG = (21 * 3600 + 30 * 60 + 45.678) / 240.0
_DEC_DEG = -(12 + 34 / 60.0 + 56.78 / 3600.0)


def _point(group=0, mjd=_MJD, mag=18.4, band="V", snr=35.0, dec=_DEC_DEG):
    # @args: overrides for the fields a test cares about
    # @return: a measured point, the shape the generators document
    return {
        "mjd": mjd,
        "ra_deg": _RA_DEG,
        "dec_deg": dec,
        "rms_ra": 0.25,
        "rms_dec": 0.20,
        "mag": mag,
        "band": band,
        "snr": snr,
        "n_frames": 5,
        "group_index": group,
    }


@dataclass
class _PointDataclass:
    # A light dataclass using the app's own field names (ra/dec), to prove
    # both spellings are accepted.
    ra: float
    dec: float
    mjd: float = _MJD
    rms_ra: float = 0.3
    rms_dec: float = 0.3
    mag: float | None = 17.5
    band: str | None = "R"
    snr: float = 30.0
    n_frames: int = 3
    group_index: int = 0


# --- formatting -----------------------------------------------------------

def test_format_time_mpc80_t_mid():
    # JD 2459289.0 is 2021-03-15 12:00 UTC.
    assert mpc.format_time_mpc80(2459289.0) == "2021 03 15.500000"


def test_format_ra_mpc80():
    assert mpc.format_ra_mpc80(_RA_DEG) == "21 30 45.678"


def test_format_dec_mpc80_negative():
    assert mpc.format_dec_mpc80(_DEC_DEG) == "-12 34 56.78"


def test_format_dec_mpc80_positive_sign():
    assert mpc.format_dec_mpc80(12.582439).startswith("+")


def test_format_sexagesimal_never_overflows():
    # A value a hair below the next second must round cleanly, not to 60.
    ra = (1 * 3600 + 59 * 60 + 59.9996) / 240.0
    assert mpc.format_ra_mpc80(ra).endswith("00.000")
    dec = (10 + 59 / 60.0 + 59.9996 / 3600.0)
    assert mpc.format_dec_mpc80(dec).endswith("00.00")


# --- bands ----------------------------------------------------------------

def test_band_code_known_filters():
    assert mpc.band_code("V") == "V"
    assert mpc.band_code("Rc") == "R"
    assert mpc.band_code("Clear") == "C"
    assert mpc.band_code("r'") == "r"
    assert mpc.band_code("g") == "g"
    assert mpc.band_code(None) == "C"


def test_band_code_unknown_falls_to_c_with_warning(caplog):
    with caplog.at_level("WARNING"):
        assert mpc.band_code("NIR") == "C"
    assert any("NIR" in r.message for r in caplog.records)


# --- designations ---------------------------------------------------------

def test_pack_numbered():
    assert mpc.pack_designation("433")[0] == "00433"
    assert mpc.pack_designation("100000")[0] == "A0000"


def test_pack_provisional():
    packed, note = mpc.pack_designation("2021 EQ3", "provisional")
    assert packed  # the app's 5-char field keeps the head of "K21E03Q"
    assert note  # the full form is longer, so the user is told to confirm


def test_pack_comet_numbered():
    assert mpc.pack_designation("1P", "comet")[0] == "0001P"


def test_pack_comet_provisional_does_not_break():
    packed, note = mpc.pack_designation("C/2023 A3", "comet")
    assert packed
    assert note


def test_pack_pccp_returns_note():
    packed, note = mpc.pack_designation("P21vXYZ", "pccp")
    assert packed
    assert "PCCP" in note
    # The validator must still recognize it (D15: no invented packing).
    text = mpc.to_mpc80([_point()], "Z41", "P21vXYZ")
    result = mpc_report.validate(text, "Z41", "P21vXYZ")
    assert result["valid"] is True


# --- A7: round trip -------------------------------------------------------

def test_a7_mpc80_round_trip():
    text = mpc.to_mpc80([_point()], "Z41", "2021 EQ3")
    lines = text.splitlines()
    assert len(lines) == 1
    assert len(lines[0]) == 80
    result = mpc_report.validate(text, obs_code="Z41", expected_obj="2021 EQ3")
    assert result["format"] == "mpc80"
    assert result["valid"] is True, result["errors"]
    assert result["n_lines"] == 1


def test_a7_ades_round_trip():
    text = mpc.to_ades_psv([_point()], "Z41", "2021 EQ3")
    lines = text.splitlines()
    assert len(lines) == 2                    # header + one row
    result = mpc_report.validate(text, obs_code="Z41", expected_obj="2021 EQ3")
    assert result["format"] == "ades"
    assert result["valid"] is True, result["errors"]
    assert result["n_lines"] == 1


def test_a7_fields_land_where_mpc_report_expects():
    line = mpc.to_mpc80([_point()], "Z41", "2021 EQ3").splitlines()[0]
    assert line[mpc_report._DATE[0]:mpc_report._DATE[1]].strip() == \
        "2021 03 15.500000"
    assert line[mpc_report._RA[0]:mpc_report._RA[1]].strip() == "21 30 45.678"
    assert line[mpc_report._DEC[0]:mpc_report._DEC[1]].strip() == \
        "-12 34 56.78"
    assert line[mpc_report._MAG[0]:mpc_report._MAG[1]].strip() == "18.40"
    assert line[mpc_report._BAND[0]:mpc_report._BAND[1]].strip() == "V"
    assert line[mpc_report._STATION[0]:mpc_report._STATION[1]].strip() == "Z41"


def test_a7_three_groups_three_lines():
    points = [_point(group=i, mjd=_MJD + i * 0.01) for i in range(3)]
    text = mpc.to_mpc80(points, "Z41", "2021 EQ3")
    assert len(text.splitlines()) == 3
    result = mpc_report.validate(text, "Z41", "2021 EQ3")
    assert result["valid"] is True
    assert result["n_lines"] == 3
    # Each line carries its own time.
    dates = {ln[15:32] for ln in text.splitlines()}
    assert len(dates) == 3


def test_a7_three_groups_three_ades_rows():
    points = [_point(group=i, mjd=_MJD + i * 0.01) for i in range(3)]
    text = mpc.to_ades_psv(points, "Z41", "2021 EQ3")
    assert len(text.splitlines()) == 4        # header + three rows
    result = mpc_report.validate(text, "Z41", "2021 EQ3")
    assert result["valid"] is True
    assert result["n_lines"] == 3


def test_a7_no_magnitude_leaves_field_blank():
    point = _point(mag=None, band=None)
    line = mpc.to_mpc80([point], "Z41", "2021 EQ3").splitlines()[0]
    assert line[mpc_report._MAG[0]:mpc_report._MAG[1]].strip() == ""
    assert line[mpc_report._BAND[0]:mpc_report._BAND[1]].strip() == ""
    assert mpc_report.validate(
        mpc.to_mpc80([point], "Z41", "2021 EQ3"), "Z41")["valid"] is True

    rows = mpc.to_ades_psv([point], "Z41", "2021 EQ3").splitlines()
    header = rows[0].split("|")
    row = dict(zip(header, rows[1].split("|")))
    assert row["mag"] == ""
    assert row["band"] == ""
    assert mpc_report.validate(
        "\n".join(rows), "Z41")["valid"] is True


def test_a7_dataclass_with_ra_dec_alias():
    # The app's AstrometryPoint names the fields ra/dec; the module accepts
    # both so no caller has to rename anything.
    text = mpc.to_mpc80([_PointDataclass(ra=_RA_DEG, dec=_DEC_DEG)], "Z41",
                        "00433")
    assert len(text.splitlines()[0]) == 80
    assert mpc_report.validate(text, "Z41", "00433")["valid"] is True


# --- A15: submission floor ------------------------------------------------

def test_a15_low_snr_dropped_and_explained():
    good = _point(group=0, snr=30.0)
    weak = _point(group=1, snr=8.0)
    kept, dropped, notes = mpc.submittable([good, weak])
    assert kept == [good]
    assert dropped == [weak]
    assert len(notes) == 1
    assert "SNR 8.0" in notes[0]
    assert "20" in notes[0]


def test_a15_threshold_is_configurable():
    weak = _point(snr=8.0)
    kept, dropped, notes = mpc.submittable(
        [weak], cfg={"astrometry_submit_snr": 5.0})
    assert kept == [weak]
    assert dropped == []
    assert notes == []


def test_a15_missing_snr_is_not_silently_submitted():
    kept, dropped, notes = mpc.submittable([_point(snr=None)])
    assert kept == []
    assert len(dropped) == 1
    assert notes


def test_generate_applies_floor_and_validates():
    points = [_point(group=0, snr=30.0), _point(group=1, snr=5.0)]
    out = mpc.generate(points, "ades", "Z41", "2021 EQ3")
    assert out["format"] == "ades"
    assert len(out["kept"]) == 1
    assert len(out["dropped"]) == 1
    assert out["notes"]
    assert out["validation"]["valid"] is True
    # The low-SNR group left no row behind.
    assert out["validation"]["n_lines"] == 1


def test_generate_unknown_format_raises():
    with pytest.raises(ValueError):
        mpc.generate([_point()], "xml", "Z41", "2021 EQ3")


def test_generate_stack_and_frames_differ():
    stack = mpc.generate([_point(mjd=_MJD)], "mpc80", "Z41", "2021 EQ3")
    frames = mpc.generate([_point(mjd=_MJD + 0.02)], "mpc80", "Z41",
                          "2021 EQ3")
    assert stack["text"] != frames["text"]
    assert stack["validation"]["valid"] is True
    assert frames["validation"]["valid"] is True


def test_validate_generated_is_the_same_judge():
    text = mpc.to_mpc80([_point()], "Z41", "2021 EQ3")
    assert mpc.validate_generated(text, "Z41", "2021 EQ3") == \
        mpc_report.validate(text, "Z41", "2021 EQ3")
