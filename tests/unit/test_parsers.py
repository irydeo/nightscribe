############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: source parsers (offline fixtures)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core.sources import (esa_neo, neofixer, pccp, rochester,
                                      sbdb)


def test_parse_sbdb_apophis(sbdb_apophis):
    body = sbdb.parse_sbdb(sbdb_apophis)
    assert body["fullname"] == "99942 Apophis (2004 MN4)"
    assert body["neo"] is True
    assert body["pha"] is True
    assert body["orbit_class"] == "Aten"
    assert abs(body["phys"]["diameter"] - 0.34) < 0.01
    assert abs(body["phys"]["H"] - 19.09) < 0.01
    assert body["elements"]["a"] > 0
    # object-card plan 5a: discovery date — the fixture has no discovery
    # record, so the orbit's first_obs ("2004-03-15") fills in
    assert body["disc_date"] == "2004-03-15"


def test_parse_sbdb_unknown():
    assert sbdb.parse_sbdb({}) is None


def test_parse_sbdb_discovery_record_wins():
    # when SBDB does send the discovery block (get() asks discovery=1),
    # its "YYYY-Mmm-DD" date is normalised and preferred over first_obs
    raw = {"object": {"des": "99942", "fullname": "99942 Apophis"},
           "discovery": {"date": "2004-Jun-19", "who": "R. Tucker"},
           "orbit": {"first_obs": "2004-03-15", "elements": []}}
    body = sbdb.parse_sbdb(raw)
    assert body["disc_date"] == "2004-06-19"


def test_parse_sbdb_without_any_date():
    # no discovery block and no first_obs: the key exists as None
    raw = {"object": {"des": "X", "fullname": "X"}, "orbit": {}}
    body = sbdb.parse_sbdb(raw)
    assert body["disc_date"] is None


def test_parse_neofixer_orbit(fixture_path):
    import json
    data = json.loads((fixture_path / "neofixer_orbit_sample.json")
                      .read_text(encoding="utf-8"))
    body = neofixer.parse_neofixer_orbit(data, "ST26H88")
    assert body is not None
    els = body["elements"]
    # SBDB-shaped element keys must be present and sane
    assert els["a"] > 0 and 0 < els["e"] < 1.0
    assert 0 <= els["i"] < 180
    assert els["q"] == pytest.approx(els["a"] * (1 - els["e"]), rel=1e-3)
    assert els["om"] == pytest.approx(328.4813855513224)
    assert els["w"] == pytest.approx(341.631989634389)
    assert els["ma"] == pytest.approx(5.9850698674126)
    assert els["tp"] == pytest.approx(2461259.60434909)
    assert els["epoch"] == pytest.approx(2461277.5)
    # sigmas kept under their own dict, keyed by element name
    assert body["sigmas"]["e"] == pytest.approx(0.00308)
    assert body["sigmas"]["a"] == pytest.approx(0.0131)
    # MOID Earth drives pha; H feeds size estimates; arc from observations
    assert body["moid"] == pytest.approx(0.002316)
    assert body["pha"] is True and body["neo"] is True
    assert body["phys"]["H"] == pytest.approx(26.74)
    assert body["arc_days"] == pytest.approx(0.47, abs=0.01)
    assert body["preliminary"] is True
    # object-card plan 5b: first observation = the discovery night
    # (NEOfixer's "earliest iso" is 2026-08-24T07:55:33Z)
    assert body["disc_date"] == "2026-08-24"
    # the parsed elements must propagate with our Kepler solver
    from nightscribe.core import ephem_minor
    out = ephem_minor.kepler_ra_dec(els, els["epoch"])
    assert out is not None and out[2] > 0


def test_parse_neofixer_orbit_missing(fixture_path):
    import json
    data = json.loads((fixture_path / "neofixer_orbit_none.json")
                      .read_text(encoding="utf-8"))
    assert neofixer.parse_neofixer_orbit(data, "XXXXXX") is None
    assert neofixer.parse_neofixer_orbit({}, "XXXXXX") is None


def test_parse_rochester(fixture_path):
    html = (fixture_path / "rochester_sample.html").read_text(encoding="utf-8")
    sne = rochester.parse_sn_list(html)
    assert len(sne) >= 2
    for s in sne:
        assert s["name"]
        assert ":" in s["ra"]
        assert isinstance(s["mag"], float)


def test_parse_pccp(fixture_path):
    html = (fixture_path / "pccp_sample.html").read_text(encoding="utf-8")
    cands = pccp.parse_pccp(html)
    assert len(cands) >= 1
    c = cands[0]
    assert c["desig"]
    assert c["score"] is None or 0 <= c["score"] <= 100
    # coordinates must parse to degrees in range
    assert c["ra_deg"] is None or 0 <= c["ra_deg"] < 360
    assert c["dec_deg"] is None or -90 <= c["dec_deg"] <= 90


def test_parse_esa_close(fixture_path):
    text = (fixture_path / "esa_close_app.txt").read_text(encoding="utf-8")
    rows = esa_neo.parse_close_approaches(text)
    assert len(rows) >= 1
    r = rows[0]
    assert r["name"]
    assert r["dist_ld"] > 0
    assert r["dist_au"] > 0
    assert r["vel_kms"] > 0


def test_horizons_parser(fixture_path):
    import json
    from nightscribe.core.sources import horizons
    data = json.loads((fixture_path / "horizons_apophis.json")
                      .read_text(encoding="utf-8"))
    rows = horizons.parse_ephemeris(data.get("result", ""))
    assert len(rows) == 2
    assert rows[0]["delta"] > 0
    assert rows[0]["r"] > 0
    assert rows[0]["time"].startswith("2026-Aug-21")


def test_horizons_parser_with_markers():
    # Horizons inserts solar/lunar presence markers ("*", "m", "C/N/A")
    # between the time and the RA — captured live from the API 2026-08-24.
    # The parser must skip them instead of shifting every column.
    from nightscribe.core.sources import horizons
    text = (
        "$$SOE\n"
        " 2026-Aug-24 00:00  m  11 59 55.22 +00 14 00.2   "
        "0.983762760826  -5.2106786  1.73047558770703  -4.5644460\n"
        " 2026-Aug-25 00:00     12 03 19.81 -00 06 07.1   "
        "0.980738618798  -5.2613019  1.72769565812394  -4.6944216\n"
        " 2026-Aug-26 00:00*m   12 06 44.96 -00 26 17.6   "
        "0.977685578196  -5.3107397  1.72484117431761  -4.8239993\n"
        "$$EOE\n")
    rows = horizons.parse_ephemeris(text)
    assert len(rows) == 3
    assert rows[0]["ra"] == "11 59 55.22"
    assert rows[0]["dec"] == "+00 14 00.2"
    assert rows[0]["r"] == pytest.approx(0.983762760826)
    assert rows[0]["delta"] == pytest.approx(1.73047558770703)
    assert rows[1]["dec"].startswith("-00 06")       # no marker column
    assert rows[2]["time"] == "2026-Aug-26 00:00"    # glued "*m" markers
    assert rows[2]["ra"] == "12 06 44.96"


def test_exoclock_planets_parse(exoclock_sample):
    # the sample bypasses the network by testing the field mapping directly
    from nightscribe.core import coords
    for key, p in exoclock_sample.items():
        ra = coords.ra_hms_to_deg(p["ra_j2000"])
        dec = coords.dec_dms_to_deg(p["dec_j2000"])
        assert 0 <= ra < 360
        assert -90 <= dec <= 90
        assert float(p["ephem_period"]) > 0
