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

from nightscribe.core.sources import (esa_neo, pccp, rochester, sbdb)


def test_parse_sbdb_apophis(sbdb_apophis):
    body = sbdb.parse_sbdb(sbdb_apophis)
    assert body["fullname"] == "99942 Apophis (2004 MN4)"
    assert body["neo"] is True
    assert body["pha"] is True
    assert body["orbit_class"] == "Aten"
    assert abs(body["phys"]["diameter"] - 0.34) < 0.01
    assert abs(body["phys"]["H"] - 19.09) < 0.01
    assert body["elements"]["a"] > 0


def test_parse_sbdb_unknown():
    assert sbdb.parse_sbdb({}) is None


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


def test_exoclock_planets_parse(exoclock_sample):
    # the sample bypasses the network by testing the field mapping directly
    from nightscribe.core import coords
    for key, p in exoclock_sample.items():
        ra = coords.ra_hms_to_deg(p["ra_j2000"])
        dec = coords.dec_dms_to_deg(p["dec_j2000"])
        assert 0 <= ra < 360
        assert -90 <= dec <= 90
        assert float(p["ephem_period"]) > 0
