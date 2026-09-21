############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: comparison stars module (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from pathlib import Path

import pytest

from nightscribe.core import compstars
from nightscribe.core.sources import vizier

FIX = Path(__file__).resolve().parent.parent / "fixtures"
CENTER = (291.366, 42.784)      # 19h25m27.9s +42d47m03s
FIELD_DEG = 18.0 / 60.0         # 18' square


def _rows(name, catalog):
    spec = vizier.CATALOGS[catalog]
    text = (FIX / name).read_bytes().decode("utf-8")
    return vizier.parse_tsv(text, spec["required"], spec["ra"],
                            spec["dec"])[1]


def _star(ra, dec, mag, bv=None, vsx=None, bands=None):
    return {"id": f"J{ra:.4f}{dec:+.4f}", "name": None, "ra": ra,
            "dec": dec, "mag": mag, "band": "G", "catalog": "Gaia EDR3",
            "bands": bands or [{"label": "G", "value": mag, "err": 0.003,
                                "derived": False}],
            "bv": bv, "color_origin": "estimated" if bv is not None else None,
            "vsx": vsx}


# --------------------------- geometry ---------------------------

def test_separation_arcsec():
    a = {"ra": 10.0, "dec": 20.0}
    b = {"ra": 10.0, "dec": 20.0 + 1.0 / 3600.0}
    assert compstars.separation_arcsec(a, b) == pytest.approx(1.0, abs=1e-3)
    # RA wrap at 0h/24h must not explode
    c = {"ra": 359.9999, "dec": 0.0}
    d = {"ra": 0.0001, "dec": 0.0}
    assert compstars.separation_arcsec(c, d) < 1.0


def test_inside_field():
    assert compstars.inside_field(291.366, 42.784, CENTER, FIELD_DEG)
    assert compstars.inside_field(291.500, 42.900, CENTER, FIELD_DEG)
    # 0.334 deg of RA at dec 42.8 is ~14.7' across: outside a 9' half-side
    assert not compstars.inside_field(291.700, 42.784, CENTER, FIELD_DEG)


# --------------------------- field building ---------------------------

def test_build_stars_gaia():
    rows = _rows("vizier_gaia.tsv", "gaia")
    stars = compstars.build_stars(rows, CENTER, FIELD_DEG, "gaia")
    # 9 rows: star 7 is outside the field, star 9 has no Gmag
    assert len(stars) == 7
    # sorted by G magnitude, brightest first
    assert [s["mag"] for s in stars] == sorted(s["mag"] for s in stars)
    first = stars[0]
    assert first["id"] == "2100000000000004"
    assert first["mag"] == pytest.approx(11.05)
    # B-V estimated from BP-RP (0.55 for star 4: BP 11.30 - RP 10.75;
    # hand-computed through the Riello 2021 polynomials)
    assert first["bv"] == pytest.approx(0.0867, abs=1e-3)
    assert first["color_origin"] == "estimated"
    labels = [b["label"] for b in first["bands"]]
    assert labels[:4] == ["G", "BP", "RP", "BP-RP"]
    assert {"B", "V", "Rc", "Ic", "B-V"} <= set(labels)
    assert all(b["derived"] for b in first["bands"] if b["label"] == "B-V")


def test_build_stars_apass_direct_bv():
    rows = _rows("vizier_apass.tsv", "apass")
    stars = compstars.build_stars(rows, CENTER, FIELD_DEG, "apass")
    # star 100006 sits outside the field
    assert len(stars) == 5
    first = stars[0]
    assert first["id"] == "100004"
    assert first["bv"] == pytest.approx(11.400 - 10.900, abs=1e-3)
    assert first["color_origin"] == "direct"
    # star 100005 has no Bmag: no B-V, no colour origin
    s5 = next(s for s in stars if s["id"] == "100005")
    assert s5["bv"] is None and s5["color_origin"] is None


def test_positional_name_when_no_id():
    rows = _rows("vizier_gaia.tsv", "gaia")
    for row in rows:
        row["Source"] = ""
    stars = compstars.build_stars(rows, CENTER, FIELD_DEG, "gaia")
    assert all(s["id"].startswith("J") for s in stars)


def test_vsx_crossmatch_disqualifies_variables():
    stars = compstars.build_stars(_rows("vizier_gaia.tsv", "gaia"),
                                  CENTER, FIELD_DEG, "gaia")
    variables = compstars.build_variables(_rows("vizier_vsx.tsv", "vsx"),
                                          CENTER, FIELD_DEG)
    assert len(variables) == 2
    compstars.match_vsx(stars, variables)
    matched = next(v for v in variables if v["name"] == "V0001 Cyg")
    unmatched = next(v for v in variables if v["name"] == "V0002 Cyg")
    assert matched["star"] is not None
    assert matched["star"]["id"] == "2100000000000008"
    assert matched["star"]["vsx"] is matched
    assert unmatched["star"] is None
    assert unmatched["distance_arcsec"] > compstars.VSX_MATCH_ARCSEC


def test_load_field_orchestrates_both_queries(monkeypatch):
    bodies = {
        "gaia": (FIX / "vizier_gaia.tsv").read_bytes(),
        "vsx": (FIX / "vizier_vsx.tsv").read_bytes(),
    }

    def fake_http_get(key, source, fetch, force=False):
        catalog = "vsx" if "B/vsx" in key else "gaia"
        return bodies[catalog], "text/tab-separated-values"

    monkeypatch.setattr(vizier.db, "http_get", fake_http_get)
    field = compstars.load_field("gaia", CENTER[0], CENTER[1], 18.0)
    assert field is not None
    assert len(field["stars"]) == 7
    assert len(field["variables"]) == 2
    assert field["vsx_warning"] is False
    # the matched star carries its VSX tag
    s8 = next(s for s in field["stars"] if s["id"] == "2100000000000008")
    assert s8["vsx"]["name"] == "V0001 Cyg"


def test_load_field_catalog_failure_is_none(monkeypatch):
    def failing(key, source, fetch, force=False):
        import requests
        raise requests.RequestException("down")

    monkeypatch.setattr(vizier.db, "http_get", failing)
    assert compstars.load_field("gaia", CENTER[0], CENTER[1], 18.0) is None


def test_load_field_vsx_failure_only_warns(monkeypatch):
    def fake_http_get(key, source, fetch, force=False):
        if "B/vsx" in key:
            import requests
            raise requests.RequestException("down")
        return (FIX / "vizier_gaia.tsv").read_bytes(), "text/tab-separated-values"

    monkeypatch.setattr(vizier.db, "http_get", fake_http_get)
    field = compstars.load_field("gaia", CENTER[0], CENTER[1], 18.0)
    assert field is not None
    assert field["variables"] == []
    assert field["vsx_warning"] is True


# --------------------------- proposal ---------------------------

def _proposal_field():
    # Ring of stars around CENTER: bright/faint, blue/red, one variable,
    # one with a close neighbour. 0.001 deg ~ 3.6" in dec, ~2.6" in RA
    # at this declination.
    stars = [
        _star(291.300, 42.780, 12.0, bv=0.60),                    # good
        _star(291.310, 42.750, 12.5, bv=0.62),                    # good
        _star(291.320, 42.810, 13.0, bv=0.58),                    # good
        _star(291.340, 42.750, 13.5, bv=1.80),                    # red
        _star(291.350, 42.820, 14.0, bv=0.65),                    # faint-ish
        _star(291.360, 42.740, 12.2, bv=0.61, vsx={"name": "V1"}),  # var
        _star(291.370, 42.820, 12.8, bv=0.59),                    # good
        _star(291.371, 42.820, 14.9, bv=0.60),  # 2.6" from previous
        _star(291.390, 42.760, 15.5, bv=0.60),                    # faint
        _star(291.410, 42.800, 13.1, bv=None),                    # no colour
        _star(291.420, 42.770, 12.6, bv=0.64),                    # good
        _star(291.430, 42.810, 14.4, bv=0.90),                    # faint+red
    ]
    return stars


def test_propose_comps_criteria():
    stars = _proposal_field()
    out = compstars.propose_comps(stars, target_mag=14.0, target_bv=0.60,
                                  n=5)
    comps = out["comps"]
    assert len(comps) == 5
    assert [c["name"] for c in comps] == [f"Comp{i}" for i in range(1, 6)]
    ids = [c["star"]["id"] for c in comps]
    # the variable is never proposed
    assert not any(c["star"].get("vsx") for c in comps)
    # the crowded pair contributes at most one star
    crowded = [sid for sid in ids
               if sid.startswith("J291.370") or sid.startswith("J291.371")]
    assert len(crowded) <= 1
    # brighter, colour-matched stars win over the red/faint ones
    assert ids[0] == "J291.3000+42.7800"
    # every entry carries its bilingual reason
    assert "más brillante" in comps[0]["why"]["es"]
    assert "brighter than the target" in comps[0]["why"]["en"]
    assert "not a known variable" in comps[0]["why"]["en"]
    # a check star beyond the comps
    assert out["check"] is not None
    assert out["check"]["kind"] == "check"
    assert all(c["star"] is not out["check"]["star"] for c in comps)


def test_propose_comps_relaxes_when_strict_pool_is_short():
    stars = _proposal_field()
    # target brighter than almost everything: the margin cannot hold
    out = compstars.propose_comps(stars, target_mag=11.0, target_bv=0.60,
                                  n=3)
    assert len(out["comps"]) == 3
    assert "fainter than the target" in out["comps"][0]["why"]["en"]


def test_propose_comps_spread_keeps_one_per_region():
    stars = _proposal_field()
    out = compstars.propose_comps(stars, target_mag=16.0, target_bv=0.60,
                                  n=3, spread_arcmin=6.0)
    comps = [c["star"] for c in out["comps"]]
    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            assert compstars.separation_arcsec(a, b) >= 6.0 * 60.0 - 1e-6


def test_propose_comps_no_check_when_disabled():
    out = compstars.propose_comps(_proposal_field(), target_mag=14.0,
                                  n=2, check=False)
    assert out["check"] is None


# --------------------------- CSV export ---------------------------

def test_export_sequence_csv(tmp_path):
    stars = _proposal_field()
    out = compstars.propose_comps(stars, target_mag=14.0, target_bv=0.60,
                                  n=3)
    entries = out["comps"] + [out["check"]]
    path = compstars.export_sequence_csv(
        entries, tmp_path / "seq.csv", target_name="V0001 Cyg",
        catalog_label="Gaia EDR3")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# target: V0001 Cyg"
    header = lines[3].split(",")
    assert header[:4] == ["Name", "Type", "RA (h m s)", "Dec (d m s)"]
    assert "G" in header
    rows = [ln.split(",") for ln in lines[4:] if ln]
    assert len(rows) == 4
    assert rows[0][0] == "Comp1"
    assert rows[-1][1] == "Check"
    # RA in sexagesimal and degrees agree
    assert rows[0][2].startswith("19 ")
    assert float(rows[0][4]) == pytest.approx(291.3, abs=1e-3)


def test_export_sequence_csv_derived_columns(tmp_path):
    bands = [{"label": "G", "value": 12.34, "err": 0.003,
              "derived": False},
             {"label": "V", "value": 12.44, "err": None, "derived": True}]
    star = _star(291.366, 42.784, 12.34, bands=bands)
    entries = [{"name": "Comp1", "kind": "comp", "star": star}]
    path = compstars.export_sequence_csv(entries, tmp_path / "seq.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[3].split(",")
    assert "V (est.)" in header
    row = lines[4].split(",")
    assert row[header.index("G")] == "12.340"
    assert row[header.index("V (est.)")] == "12.44"
