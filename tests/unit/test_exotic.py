############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: EXOTIC inits.json handoff (Track D, subplan 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The EXOTIC handoff file is fixed against the real inits.json sample of
the rzellem/EXOTIC repo (re-verified 2026-09-10): exact key spelling, null
conventions, Rp/Rs and a/Rs conversions from the TAP fields, and the
EXOTIC file-name convention. No network anywhere.
"""

import datetime
import json
from pathlib import Path

import pytest

from nightscribe.core import exotic

_FIXTURES = Path(__file__).parents[1] / "fixtures"
_HATP32 = _FIXTURES / "hatp32_sample.fits"    # MicroObservatory crop

_MID = datetime.datetime(2026, 8, 22, 0, 20, tzinfo=datetime.timezone.utc)


class _Cfg:
    # config-like stub with the observatory + camera profile
    _v = {"lat": 40.55, "lon": -3.37, "height": 631, "aavso_code": "FJCF",
          "camera_type": "CCD", "pixel_binning": "1x1",
          "pixel_um": 3.76, "focal_mm": 2000.0}

    def __init__(self, **over):
        self._v = {**_Cfg._v, **over}

    def get(self, k, d=None):
        return self._v.get(k, d)


def _ctx():
    return {"ra_deg": 330.123, "dec_deg": 40.456,
            "transit": {"star": "WASP-999", "mid": _MID.isoformat(),
                        "t0": 2459000.5}}


def _d():
    # an Exoplanet Archive row (pscomppars) with the Track-D fields
    return {"pl_name": "WASP-999 b", "hostname": "WASP-999",
            "ra": 330.123, "dec": 40.456,
            "pl_orbper": 3.2745, "pl_radj": 1.5, "st_rad": 1.2,
            "pl_orbsmax": 0.05, "pl_orbincl": 87.5, "pl_orbeccen": None,
            "pl_tranmid": 2459123.456789, "st_teff": 6100.0,
            "st_met": -0.12, "st_metratio": "[Fe/H]", "st_logg": 4.31,
            "sy_dist": 289.5, "sy_pmra": -9.8, "sy_pmdec": 3.5}


# ---------------- structure ----------------

def test_structure_matches_exotic_schema():
    inits = exotic.make_inits(_ctx(), _d(), _Cfg(), plan={"filter": "R",
                                                          "exp_s": 60.0},
                              out_dir="/tmp/x")
    assert set(inits) == {"inits_guide", "user_info", "planetary_parameters",
                          "optional_info"}
    ui = inits["user_info"]
    # exact EXOTIC key spelling (a typo here silently breaks the handoff)
    for key in ("Directory with FITS files", "Directory to Save Plots",
                "Directory of Flats", "Directory of Darks",
                "Directory of Biases",
                "AAVSO Observer Code (blank if none)",
                "Secondary Observer Codes (blank if none)",
                "Observation date", "Obs. Latitude", "Obs. Longitude",
                "Obs. Elevation (meters)", "Camera Type (CCD or DSLR)",
                "Pixel Binning", "Filter Name (aavso.org/filters)",
                "Observing Notes", "Plate Solution? (y/n)",
                "Add Comparison Stars from AAVSO? (y/n)",
                "Target Star X & Y Pixel",
                "Comparison Star(s) X & Y Pixel"):
        assert key in ui, key
    pp = inits["planetary_parameters"]
    for key in ("Target Star RA", "Target Star Dec", "Planet Name",
                "Host Star Name", "Orbital Period (days)",
                "Published Mid-Transit Time (BJD-UTC)",
                "Ratio of Planet to Stellar Radius (Rp/Rs)",
                "Ratio of Distance to Stellar Radius (a/Rs)",
                "Orbital Inclination (deg)",
                "Orbital Eccentricity (0 if null)",
                "Star Effective Temperature (K)",
                "Star Metallicity ([FE/H])",
                "Star Surface Gravity (log(g))", "Star Distance (pc)"):
        assert key in pp, key
    # the wizard fields stay null (the user marks stars in EXOTIC)
    assert ui["Target Star X & Y Pixel"] is None
    assert ui["Comparison Star(s) X & Y Pixel"] is None
    # plate solve off (astrometry.net is never asked: it cost minutes and
    # failed; EXOTIC uses the frame's own WCS or astroalign), AAVSO comp-star
    # fetch on (first-timer friendly)
    assert ui["Plate Solution? (y/n)"] == "n"
    assert ui["Add Comparison Stars from AAVSO? (y/n)"] == "y"


def test_plate_solution_can_still_be_asked_for():
    # the escape hatch: a caller may still want astrometry.net's solution
    ui = exotic.make_inits(_ctx(), _d(), _Cfg(),
                           plate_solution=True)["user_info"]
    assert ui["Plate Solution? (y/n)"] == "y"


def test_user_info_values():
    ui = exotic.make_inits(_ctx(), _d(), _Cfg(), out_dir="/tmp/x",
                           plan={"filter": "R"})["user_info"]
    assert ui["AAVSO Observer Code (blank if none)"] == "FJCF"
    assert ui["Observation date"] == "22-August-2026"   # English, always
    assert ui["Obs. Latitude"] == "+40.550000"
    assert ui["Obs. Longitude"] == "-3.370000"
    assert ui["Obs. Elevation (meters)"] == 631
    assert ui["Camera Type (CCD or DSLR)"] == "CCD"
    assert ui["Pixel Binning"] == "1x1"
    assert ui["Filter Name (aavso.org/filters)"] == "R"


# ---------------- conversions ----------------

def test_planetary_parameter_conversions():
    pp = exotic.make_inits(_ctx(), _d(), _Cfg())["planetary_parameters"]
    # Rp/Rs = pl_radj * 0.10045 / st_rad
    assert abs(pp["Ratio of Planet to Stellar Radius (Rp/Rs)"]
               - 1.5 * 0.10045 / 1.2) < 1e-9
    # a/Rs = pl_orbsmax / (st_rad * 0.00465047)
    assert abs(pp["Ratio of Distance to Stellar Radius (a/Rs)"]
               - 0.05 / (1.2 * 0.00465047)) < 1e-9
    assert pp["Orbital Period (days)"] == 3.2745
    assert pp["Orbital Inclination (deg)"] == 87.5
    # eccentricity: EXOTIC wants 0 when null
    assert pp["Orbital Eccentricity (0 if null)"] == 0
    assert pp["Star Effective Temperature (K)"] == 6100.0
    assert pp["Star Metallicity ([FE/H])"] == -0.12
    # the legacy st_metfe key is honoured as a fallback (pscomppars uses
    # st_met — verified 2026-09-10)
    d2 = _d()
    d2["st_metfe"] = d2.pop("st_met")
    pp2 = exotic.make_inits(_ctx(), d2, _Cfg())["planetary_parameters"]
    assert pp2["Star Metallicity ([FE/H])"] == -0.12
    assert pp["Star Surface Gravity (log(g))"] == 4.31
    assert pp["Star Distance (pc)"] == 289.5
    # the published mid-transit comes from pl_tranmid (not the fallback)
    assert pp["Published Mid-Transit Time (BJD-UTC)"] == 2459123.456789


def test_nulls_when_data_missing():
    pp = exotic.make_inits({"transit": {}}, {}, _Cfg())[
        "planetary_parameters"]
    assert pp["Ratio of Planet to Stellar Radius (Rp/Rs)"] is None
    assert pp["Ratio of Distance to Stellar Radius (a/Rs)"] is None
    assert pp["Orbital Inclination (deg)"] is None
    assert pp["Published Mid-Transit Time (BJD-UTC)"] is None
    # ...but the eccentricity is 0 by EXOTIC's own convention
    assert pp["Orbital Eccentricity (0 if null)"] == 0


def test_mid_transit_fallbacks():
    # no pl_tranmid -> the catalogue t0 of the event snapshot
    d = _d()
    del d["pl_tranmid"]
    pp = exotic.make_inits(_ctx(), d, _Cfg())["planetary_parameters"]
    assert pp["Published Mid-Transit Time (BJD-UTC)"] == 2459000.5
    # no t0 either -> tonight's mid-transit (planner-computed JD)
    ctx = _ctx()
    del ctx["transit"]["t0"]
    pp = exotic.make_inits(ctx, d, _Cfg())["planetary_parameters"]
    from nightscribe.core import coords
    assert abs(pp["Published Mid-Transit Time (BJD-UTC)"]
               - coords.jd_from_datetime(_MID)) < 1e-4


# ---------------- filters / camera / scale ----------------

def test_filter_mapping_and_wavelengths():
    # L -> CV (no clean wavelength); R -> Cousins R with nm bounds;
    # unknown -> "O" (other)
    oi = exotic.make_inits(_ctx(), _d(), _Cfg(), plan={"filter": "L"})
    assert oi["user_info"]["Filter Name (aavso.org/filters)"] == "CV"
    assert oi["optional_info"]["Filter Minimum Wavelength (nm)"] is None
    oi = exotic.make_inits(_ctx(), _d(), _Cfg(), plan={"filter": "R"})
    assert oi["user_info"]["Filter Name (aavso.org/filters)"] == "R"
    assert oi["optional_info"]["Filter Minimum Wavelength (nm)"] == 561.7
    assert oi["optional_info"]["Filter Maximum Wavelength (nm)"] == 719.7
    oi = exotic.make_inits(_ctx(), _d(), _Cfg(), plan={"filter": "OIII"})
    assert oi["user_info"]["Filter Name (aavso.org/filters)"] == "O"


def test_cmos_camera_follows_exotic_guide():
    # CMOS cameras enter "CCD" and the real type goes to the notes
    ui = exotic.make_inits(_ctx(), _d(), _Cfg(camera_type="CMOS"))[
        "user_info"]
    assert ui["Camera Type (CCD or DSLR)"] == "CCD"
    assert "CMOS" in ui["Observing Notes"]


def test_plate_scale_and_exposure_in_optional_info():
    oi = exotic.make_inits(_ctx(), _d(), _Cfg(),
                           plan={"filter": "R", "exp_s": 75.0})
    # 206.265 * 3.76 / 2000 = 0.3878 arcsec/px
    assert abs(oi["optional_info"]["Image Scale (Ex: 5.21 arcsecs/pixel)"]
               - 0.388) < 1e-3
    assert oi["optional_info"]["Exposure Time (s)"] == 75.0


def test_sexagesimal_coordinates():
    pp = exotic.make_inits(_ctx(), _d(), _Cfg())["planetary_parameters"]
    hms = pp["Target Star RA"]
    dms = pp["Target Star Dec"]
    assert hms.count(":") == 2 and dms.count(":") == 2
    assert dms.startswith("+")
    assert pp["Planet Name"] == "WASP-999 b"
    assert pp["Host Star Name"] == "WASP-999"


# ---------------- observation date (2026-09-30) ----------------

def test_frame_jd_reads_the_observation_date():
    # MJD-OBS first: the MicroObservatory crop carries 58107.065
    assert exotic.frame_jd(_HATP32) == pytest.approx(2458107.565)
    # an unreadable frame is not fatal: the caller falls back to its own date
    assert exotic.frame_jd(_HATP32.parent / "nope.fits") is None


def test_visit_inits_dates_the_handoff_from_the_frames():
    # Regression (2026-09-30): a December 2017 visit was handed over dated
    # "today" (30-September-2026) and EXOTIC named every output, figure and
    # AAVSO report that way. The frames know the night.
    inits = exotic.make_inits_for_visit(
        _ctx(), _d(), _Cfg(), [_HATP32], target_xy=(424, 286), comps_xy=[])
    assert inits["user_info"]["Observation date"] == "20-December-2017"


def test_make_inits_takes_an_explicit_observation_date():
    inits = exotic.make_inits(_ctx(), _d(), _Cfg(), obs_jd=2458107.565)
    assert inits["user_info"]["Observation date"] == "20-December-2017"


def test_make_inits_without_a_date_keeps_the_transit_snapshot():
    # no frames and no obs_jd: the project's transit snapshot still rules
    inits = exotic.make_inits(_ctx(), _d(), _Cfg())
    assert inits["user_info"]["Observation date"] == "22-August-2026"


# ---------------- uncertainties (2026-09-30) ----------------

def _d_hatp32():
    # the real pscomppars row of the reference transit run (HAT-P-32 b)
    return {"pl_name": "HAT-P-32 b", "hostname": "HAT-P-32",
            "ra": 31.0427614, "dec": 46.6878512,
            "pl_orbper": 2.1500082, "pl_orbpererr1": 1.3e-07,
            "pl_radj": 1.98, "pl_radjerr1": 0.045,
            "st_rad": 1.367, "st_raderr1": 0.031,
            "pl_orbsmax": 0.03397, "pl_orbsmaxerr1": 0.00051,
            "pl_orbincl": 88.98, "pl_orbinclerr1": 0.68,
            "pl_orbeccen": 0.159, "pl_orblper": 50.0,
            "pl_tranmid": 2455867.402743, "pl_tranmiderr1": 4.9e-05,
            "st_teff": 6001.0, "st_tefferr1": 88.0, "st_tefferr2": -88.0,
            "st_met": -0.16, "st_meterr1": 0.08, "st_meterr2": -0.08,
            "st_logg": 4.22, "st_loggerr1": 0.04, "st_loggerr2": -0.04,
            "sy_dist": 289.205, "sy_pmra": -9.82484, "sy_pmdec": 3.47654}


def test_uncertainties_travel_with_the_planet():
    # Without them EXOTIC replaces each one with 1 (exotic.py:1996-2002), and
    # its transit-time window is then so wide that the aperture/comparison
    # search cannot fit the time at all
    pp = exotic.make_inits(_ctx(), _d_hatp32(), _Cfg())["planetary_parameters"]
    assert pp["Mid-Transit Time Uncertainty"] == pytest.approx(4.9e-05)
    assert pp["Orbital Period Uncertainty"] == pytest.approx(1.3e-07)
    assert pp["Orbital Inclination (deg) Uncertainty"] == pytest.approx(0.68)
    assert pp["Star Effective Temperature (+) Uncertainty"] == 88.0
    # the "(+)/(-)" pair is a pair of magnitudes: the archive's -88 becomes 88
    assert pp["Star Effective Temperature (-) Uncertainty"] == 88.0
    assert pp["Star Metallicity (-) Uncertainty"] == pytest.approx(0.08)
    assert pp["Star Surface Gravity (-) Uncertainty"] == pytest.approx(0.04)
    # the periastron, which EXOTIC otherwise models as omega = 0
    assert pp["Argument of Periastron (deg)"] == 50.0


def test_the_ratio_uncertainties_are_propagated():
    # Rp/Rs = 1.98*0.10045/1.367 and a/Rs = 0.03397/(1.367*0.00465047):
    # their relative uncertainty is the quadrature sum of the two relative
    # ones, which is the only honest way to get it from the archive
    pp = exotic.make_inits(_ctx(), _d_hatp32(), _Cfg())["planetary_parameters"]
    assert pp["Ratio of Planet to Stellar Radius (Rp/Rs)"] == \
        pytest.approx(0.14549, abs=1e-4)
    assert pp["Ratio of Planet to Stellar Radius (Rp/Rs) Uncertainty"] == \
        pytest.approx(0.00467, abs=1e-4)
    assert pp["Ratio of Distance to Stellar Radius (a/Rs)"] == \
        pytest.approx(5.3436, abs=1e-3)
    assert pp["Ratio of Distance to Stellar Radius (a/Rs) Uncertainty"] == \
        pytest.approx(0.1454, abs=1e-3)


def test_a_missing_uncertainty_stays_null():
    # a row cached before the v3 fields (or an incomplete one) carries no
    # uncertainties: the inits must not invent a number
    pp = exotic.make_inits(_ctx(), _d(), _Cfg())["planetary_parameters"]
    assert pp["Mid-Transit Time Uncertainty"] is None
    assert pp["Ratio of Planet to Stellar Radius (Rp/Rs) Uncertainty"] is None


# ---------------- output file ----------------

def test_suggested_name_convention():
    now = datetime.datetime(2026, 9, 10, 21, 30, 5)
    assert exotic.suggested_name(now) == "inits_09_10_2026__21_30_05.json"


def test_export_inits_writes_parseable_json(tmp_path):
    inits = exotic.make_inits(_ctx(), _d(), _Cfg(), out_dir=str(tmp_path))
    out = exotic.export_inits(inits, tmp_path / exotic.suggested_name())
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["planetary_parameters"]["Planet Name"] == "WASP-999 b"
    assert data["user_info"]["Directory to Save Plots"] == str(tmp_path)


# ---------------- visit inits (orchestration phase B) ----------------

def test_make_inits_for_visit_points_at_the_frames(tmp_path):
    frames = [tmp_path / "a.fits", tmp_path / "b.fits"]
    inits = exotic.make_inits_for_visit(
        _ctx(), _d(), _Cfg(), frames, target_xy=(424, 286),
        comps_xy=[(465, 183), (512, 263)], plan={"filter": "R"})
    ui = inits["user_info"]
    assert ui["Directory with FITS files"] == str(tmp_path)
    assert ui["Directory to Save Plots"] == str(tmp_path)
    # EXOTIC's sample writes these as strings
    assert ui["Target Star X & Y Pixel"] == "[424, 286]"
    assert ui["Comparison Star(s) X & Y Pixel"].startswith(
        "[[465, 183], [512, 263]")
    # padded to EXOTIC's ten slots
    assert ui["Comparison Star(s) X & Y Pixel"].count("[]") == 8
    # headless: comps in pixels, no AAVSO fetch, no astrometry.net round trip
    assert ui["Add Comparison Stars from AAVSO? (y/n)"] == "n"
    assert ui["Plate Solution? (y/n)"] == "n"
    # the manual note ("set the FITS folder yourself") is wrong here
    assert "Directory with FITS files' to your reduced" not in \
        ui["Observing Notes"]
    assert "set by NightScribe" in ui["Observing Notes"]


def test_make_inits_for_visit_out_dir_and_prereduced(tmp_path):
    frames = [tmp_path / "a.fits"]
    plots = tmp_path / "plots"
    inits = exotic.make_inits_for_visit(
        _ctx(), _d(), _Cfg(), frames, target_xy=(1, 2), comps_xy=[],
        out_dir=str(plots), pre_reduced="/data/curve.txt")
    ui = inits["user_info"]
    assert ui["Directory to Save Plots"] == str(plots)
    assert inits["optional_info"]["Pre-reduced File:"] == "/data/curve.txt"


def test_export_inits_creates_its_folder(tmp_path):
    # regression: the visit handoff writes into a fresh <project>/exotic
    # folder that does not exist yet; the write used to raise
    # FileNotFoundError (the reduce dialog flashed and nothing happened)
    out = tmp_path / "project" / "exotic" / "inits.json"
    exotic.export_inits({"user_info": {}}, out)
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))["user_info"] == {}
