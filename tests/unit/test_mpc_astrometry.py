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
    # JD 2459289.0 is 2021-03-15 12:00 UTC. 5 decimals of a day is the MPC's
    # normal precision (0.001 s would fill the field and eat the separator).
    assert mpc.format_time_mpc80(2459289.0) == "2021 03 15.50000"


def test_format_ra_mpc80():
    assert mpc.format_ra_mpc80(_RA_DEG) == "21 30 45.68"


def test_format_dec_mpc80_negative():
    assert mpc.format_dec_mpc80(_DEC_DEG) == "-12 34 56.8"


def test_format_dec_mpc80_positive_sign():
    assert mpc.format_dec_mpc80(12.582439).startswith("+")


def test_format_sexagesimal_never_overflows():
    # A value a hair below the next second must round cleanly, not to 60.
    ra = (1 * 3600 + 59 * 60 + 59.9996) / 240.0
    assert mpc.format_ra_mpc80(ra).endswith("00.00")
    dec = (10 + 59 / 60.0 + 59.9996 / 3600.0)
    assert mpc.format_dec_mpc80(dec).endswith("00.0")


# --- bands ----------------------------------------------------------------

def test_band_code_known_filters():
    assert mpc.band_code("V") == "V"
    assert mpc.band_code("Rc") == "R"
    assert mpc.band_code("Clear") == "C"
    assert mpc.band_code("r'") == "r"
    assert mpc.band_code("g") == "g"
    # the MPC lists both G (Gaia) and g (SDSS): the app's "G" is the Gaia
    # band its comparisons come from, so it stays uppercase (2026-10-11)
    assert mpc.band_code("G") == "G"
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
        "2021 03 15.50000"
    assert line[mpc_report._RA[0]:mpc_report._RA[1]].strip() == "21 30 45.68"
    assert line[mpc_report._DEC[0]:mpc_report._DEC[1]].strip() == \
        "-12 34 56.8"
    assert line[mpc_report._MAG[0]:mpc_report._MAG[1]].strip() == "18.4"
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


def test_the_instrument_mode_follows_the_camera_setting():
    # The report used to declare CCD whatever the observer's camera was
    # (reported 2026-10-07: "pone CCD y usamos CMOS"). The MPC's own value
    # lists decide the names: the ADES "mode" is CCD or CMO (the code is
    # CMO, not "CMOS") and the MPC 1992 column 15 is "C" for CCD and "B"
    # for CMOS.
    rows = mpc.to_ades_psv([_point()], "Z41", "2021 EQ3",
                           {"camera_type": "CMOS"}).splitlines()
    row = dict(zip(rows[0].split("|"), rows[1].split("|")))
    assert row["mode"] == "CMO"
    line = mpc.to_mpc80([_point()], "Z41", "2021 EQ3",
                        {"camera_type": "CMOS"}).splitlines()[0]
    assert len(line) == 80
    assert line[14] == "B"
    # a CCD says so in both formats
    rows = mpc.to_ades_psv([_point()], "Z41", "2021 EQ3",
                           {"camera_type": "CCD"}).splitlines()
    row = dict(zip(rows[0].split("|"), rows[1].split("|")))
    assert row["mode"] == "CCD"
    line = mpc.to_mpc80([_point()], "Z41", "2021 EQ3",
                        {"camera_type": "CCD"}).splitlines()[0]
    assert line[14] == "C"
    # A DSLR carries a CMOS sensor; an unknown type never invents a value
    # (the old CCD is the honest floor)
    assert mpc.instrument_mode({"camera_type": "DSLR"}) == ("CMO", "B")
    assert mpc.instrument_mode(None) == ("CCD", "C")
    assert mpc.instrument_mode({"camera_type": "nope"}) == ("CCD", "C")


def test_the_instrument_mode_still_validates():
    # The type lands inside the 80-column line and in the ADES row: the
    # round trip through the validator (the same judge a pasted report
    # passes) must stay green with either camera.
    for cfg in ({"camera_type": "CMOS"}, {"camera_type": "CCD"}):
        text = mpc.to_mpc80([_point()], "Z41", "2021 EQ3", cfg)
        assert len(text.splitlines()[0]) == 80
        assert mpc_report.validate(text, "Z41", "2021 EQ3")["valid"] is True
        ades = mpc.to_ades_psv([_point()], "Z41", "2021 EQ3", cfg)
        assert mpc_report.validate(ades, "Z41", "2021 EQ3")["valid"] is True


def test_a7_dataclass_with_ra_dec_alias():
    # The app's AstrometryPoint names the fields ra/dec; the module accepts
    # both so no caller has to rename anything.
    text = mpc.to_mpc80([_PointDataclass(ra=_RA_DEG, dec=_DEC_DEG)], "Z41",
                        "00433")
    assert len(text.splitlines()[0]) == 80
    assert mpc_report.validate(text, "Z41", "00433")["valid"] is True


# --- A15: the recommended floor (advises, never drops) --------------------

def test_a15_low_snr_is_kept_with_a_warning():
    # 2026-10-10: the floor RECOMMENDS. A low-SNR observation stays in the
    # report and the app says it does not recommend sending it; the decision
    # is the observer's.
    good = _point(group=0, snr=30.0)
    weak = _point(group=1, snr=8.0)
    kept, excluded, warnings = mpc.submittable([good, weak])
    assert kept == [good, weak]
    assert excluded == []
    assert len(warnings) == 1
    assert "SNR 8.0" in warnings[0]
    assert "20" in warnings[0]


def test_a15_threshold_is_configurable():
    weak = _point(snr=8.0)
    kept, excluded, warnings = mpc.submittable(
        [weak], cfg={"astrometry_submit_snr": 5.0})
    assert kept == [weak]
    assert excluded == []
    assert warnings == []


def test_a15_missing_snr_is_kept_with_a_warning():
    point = _point(snr=None)
    kept, excluded, warnings = mpc.submittable([point])
    assert kept == [point]
    assert excluded == []
    assert warnings


def test_a15_user_excluded_is_the_only_thing_dropped():
    # The observer's own exclusion is the one decision that takes a point out
    # of the report: the flag is set from the Astrometry tab and is reversible.
    keep = _point(group=0, snr=30.0)
    drop = _point(group=1, snr=30.0)
    drop["flags"] = ["user_excluded"]
    kept, excluded, warnings = mpc.submittable([keep, drop])
    assert kept == [keep]
    assert excluded == [drop]
    assert warnings == []


def test_generate_keeps_everything_and_warns():
    points = [_point(group=0, snr=30.0), _point(group=1, snr=5.0)]
    out = mpc.generate(points, "ades", "Z41", "2021 EQ3")
    assert out["format"] == "ades"
    # both go in: the low-SNR one is kept and warned about, not dropped
    assert len(out["kept"]) == 2
    assert out["excluded"] == []
    assert out["warnings"]
    assert out["validation"]["valid"] is True
    assert out["validation"]["n_lines"] == 2


def test_generate_unknown_format_raises():
    with pytest.raises(ValueError):
        mpc.generate([_point()], "garbage", "Z41", "2021 EQ3")


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


# --- the full submission header (2026-10-11) ------------------------------

def _ctx(**over):
    base = dict(obs_code="Z41", observer="F. Calvo", measurer="F. Calvo",
                email="obs@example.org", aperture_m=0.43, focal_ratio=4.9,
                telescope_type="reflector", detector="CMO", astcat="Gaia3E")
    base.update(over)
    return mpc.ReportContext(**base)


def test_the_mpc80_report_carries_the_full_header():
    # The report the MPC reads is header + data + end marker: without the
    # header the batch is IGNORED (ObsDetails.html), which is what the report
    # was missing.
    text = mpc.to_mpc80([_point()], "Z41", "2021 EQ3", context=_ctx(),
                        submission={"ack": "batch 1", "obj_type": "NEOCP"})
    lines = text.splitlines()
    head = lines[:lines.index("----- end -----")]
    assert head[0] == "COD Z41"
    assert "CON F. Calvo" in head
    assert "CON [obs@example.org]" in head
    assert "OBS F. Calvo" in head
    assert "MEA F. Calvo" in head
    assert "TEL 0.43-m f/4.9 reflector + CMO" in head
    assert "NET Gaia EDR 3" in head
    assert "AC2 obs@example.org" in head
    assert "NUM 1" in head
    # the target keyword rides the ACK line (the MPC reads it there)
    assert any(l.startswith("ACK ") and "NEOCP" in l for l in head)
    assert text.rstrip().endswith("----- end -----")
    # the round trip still accepts our own header
    result = mpc_report.validate(text, "Z41", "2021 EQ3")
    assert result["valid"] is True, result["errors"]
    assert result["n_lines"] == 1


def test_the_mpc80_designation_lands_in_the_right_columns():
    # Temporary (NEOCP): columns 6-12, the number field blank. Before this the
    # app wrote 5 chars of the tag in the NUMBER field (2026-10-11).
    line = mpc.to_mpc80([_point()], "Z41", "A11HPKO").splitlines()[0]
    assert line[0:5] == "     "
    assert line[5:12] == "A11HPKO"
    # Provisional: the full packed form in 6-12, never truncated.
    line = mpc.to_mpc80([_point()], "Z41", "2021 EQ3").splitlines()[0]
    assert line[0:5] == "     "
    assert line[5:12] == "K21E03Q"
    # Numbered: the packed number in 1-5, the provisional field blank.
    line = mpc.to_mpc80([_point()], "Z41", "433").splitlines()[0]
    assert line[0:5] == "00433"
    assert line[5:12] == "       "


def test_the_ades_psv_report_carries_the_obs_context():
    text = mpc.to_ades_psv([_point()], "Z41", "2021 EQ3", context=_ctx())
    lines = text.splitlines()
    assert lines[0] == "# version=2017"
    assert "# observatory" in lines and "! mpcCode Z41" in lines
    assert "# submitter" in lines and "! name F. Calvo" in lines
    assert "! aperture 0.43" in lines and "! fRatio 4.9" in lines
    assert "! design reflector" in lines and "! detector CMO" in lines
    # ADES keeps PII out of the document: no email anywhere
    assert "obs@example.org" not in text
    # the object goes in provID (ADES), not the legacy objid
    assert any(l.startswith("provID|mode|stn|") for l in lines)
    result = mpc_report.validate(text, "Z41", "2021 EQ3")
    assert result["valid"] is True, result["errors"]
    assert result["n_lines"] == 1


def test_the_ades_psv_uses_trksub_for_a_temporary_designation():
    text = mpc.to_ades_psv([_point()], "Z41", "A11HPKO", kind="neocp")
    assert text.splitlines()[0].startswith("trkSub|")
    assert text.splitlines()[1].startswith("A11HPKO|")


def test_is_temporary_designation_recognises_neocp_tags():
    # ADR-077 rev: the rename notice fires for these names even without the
    # planner's `neocp` flag, so a project created by hand is covered.
    for name in ("A11HPKO", "P11ABCD", "P10x99x", "P21vXYZ"):
        assert mpc.is_temporary_designation(name) is True, name
    # a confirmed designation (provisional, numbered, comet) is NOT a tag:
    # there is nothing to announce about it
    for name in ("2026 TQ8", "2021 EQ3", "433", "C/2023 A3", "", None,
                 "A11HPK", "AA11HPKO",
                 "K21E03Q"):        # packed provisional shares the shape
        assert mpc.is_temporary_designation(name) is False, name


def test_the_ades_xml_report_is_well_formed():
    import xml.etree.ElementTree as ET
    text = mpc.to_ades_xml([_point()], "Z41", "2021 EQ3", context=_ctx())
    root = ET.fromstring(text)
    assert root.tag == "ades" and root.get("version") == "2017"
    prov = root.find(".//obsBlock/obsData/optical/provID")
    assert prov is not None and prov.text == "2021 EQ3"
    assert root.find(
        ".//obsBlock/obsContext/observatory/mpcCode").text == "Z41"
    assert root.find(
        ".//obsBlock/obsContext/telescope/design").text == "reflector"
    # the generated XML goes through generate() too
    out = mpc.generate([_point()], "xml", "Z41", "2021 EQ3", context=_ctx())
    assert out["format"] == "xml"
    assert out["validation"]["valid"] is True


def test_report_context_is_built_from_the_settings():
    ctx = mpc.report_context({
        "mpc_code": "z41", "observer_name": "F. Calvo",
        "aperture_inches": 16.9, "focal_mm": 2000.0,
        "telescope_type": "reflector", "camera_type": "CMOS",
        "observer_email": "obs@example.org", "astrometry_astcat": "Gaia3E"})
    assert ctx.obs_code == "Z41"
    assert ctx.measurer == "F. Calvo"          # falls back to the observer
    assert ctx.detector == "CMO"
    assert ctx.aperture_m == 0.429
    assert ctx.focal_ratio == 4.7              # derived: 2000mm / 0.429m
    assert ctx.tel_mpc80() == "0.43-m f/4.7 reflector + CMO"
    assert ctx.missing() == []


def test_report_context_says_what_is_missing():
    ctx = mpc.report_context({"mpc_code": "Z41"})
    missing = ctx.missing()
    assert "the contact email" in missing
    assert "the observer's name" in missing
    assert "the telescope" in missing
