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

from nightscribe.core import exotic

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
            "st_metfe": -0.12, "st_logg": 4.31, "sy_dist": 289.5,
            "sy_pmra": -9.8, "sy_pmdec": 3.5}


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
    # plate solve on, AAVSO comp-star fetch on (first-timer friendly)
    assert ui["Plate Solution? (y/n)"] == "y"
    assert ui["Add Comparison Stars from AAVSO? (y/n)"] == "y"


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
