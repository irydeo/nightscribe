############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: TNS resolver and astrometry WCS merge
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json

import numpy as np
import pytest
import requests

from nightscribe.core import blink, fits_io, wcs as wcs_mod
from nightscribe.core.sources import astrometry, tns

FIXTURES = __import__("pathlib").Path(__file__).parents[1] / "fixtures"


def test_tns_short_name():
    assert tns.short_name("2026zji") == "2026zji"
    assert tns.short_name("SN2023ixf") == "2023ixf"
    assert tns.short_name("AT 2024abc ") == "2024abc"
    assert tns.short_name("") == ""


def test_tns_parse_object_page():
    html = (FIXTURES / "tns_2026zji.html").read_text(encoding="utf-8")
    info = tns.parse_object_page(html)
    assert info["ra"] == pytest.approx(301.14364375)
    assert info["dec"] == pytest.approx(62.64409)
    assert info["mag"] == pytest.approx(17.235)
    assert info["type"] is None          # "---" means unclassified AT
    assert info["disc_date"].startswith("2026-08-21")
    assert info["name"] == "AT2026zji"


def test_tns_parse_page_without_position():
    assert tns.parse_object_page("<html><body><h1 class='title'>x</h1>"
                                 "</body></html>") is None


def test_tns_resolve_cached(monkeypatch):
    html = (FIXTURES / "tns_2026zji.html").read_bytes()
    monkeypatch.setattr(tns.db, "http_get",
                        lambda key, source, fetch: (html, "text/html"))
    info = tns.resolve("SN2026zji")
    assert info and info["ra"] == pytest.approx(301.14364375)


def test_tns_resolve_offline_or_404(monkeypatch):
    def boom(key, source, fetch):
        raise requests.HTTPError("404")
    monkeypatch.setattr(tns.db, "http_get", boom)
    assert tns.resolve("2026zzzz") is None


# ---------------- resolver order (manual -> TNS -> SIMBAD -> Rochester) ----

def test_resolve_sn_tns_wins_over_simbad(monkeypatch):
    calls = []
    monkeypatch.setattr(blink.tns, "resolve", lambda name:
                        {"name": name, "ra": 301.14, "dec": 62.64,
                         "type": None, "mag": 17.2, "disc_date": None})
    monkeypatch.setattr(blink.simbad, "query_id",
                        lambda name: calls.append("simbad") or None)
    got = blink.resolve_sn("2026zji")
    assert got["ra"] == pytest.approx(301.14)
    assert calls == []  # SIMBAD never asked when TNS knows the object


def test_resolve_sn_falls_back_to_simbad(monkeypatch):
    monkeypatch.setattr(blink.tns, "resolve", lambda name: None)
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: {
        "name": "SN2023ixf", "otype": "SN", "ra": "14 03 38.56",
        "dec": "+54 18 42.1", "vmag": 11.0, "z": None})
    got = blink.resolve_sn("2023ixf")
    assert got["ra"] == pytest.approx(210.9107, abs=1e-3)


def test_resolve_sn_nowhere_raises(monkeypatch):
    monkeypatch.setattr(blink.tns, "resolve", lambda name: None)
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: None)
    monkeypatch.setattr(blink.rochester, "latest_sne",
                        lambda limit_mag=25.0: [])
    with pytest.raises(blink.BlinkError) as exc:
        blink.resolve_sn("2026zzzz")
    assert "TNS" in exc.value.messages["en"]


def test_resolve_sn_reports_progress(monkeypatch):
    monkeypatch.setattr(blink.tns, "resolve", lambda name: None)
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: {
        "name": "SN2023ixf", "otype": "SN", "ra": "14 03 38.56",
        "dec": "+54 18 42.1", "vmag": None, "z": None})
    stages = []
    blink.resolve_sn("2023ixf", progress=stages.append)
    assert stages and all("es" in s and "en" in s for s in stages)


# ---------------- astrometry.net WCS merge ----------------

def _cards_text(cards):
    lines = []
    for k, v in cards.items():
        if isinstance(v, str):
            lines.append(f"{k:<8}= '{v}'")
        elif isinstance(v, bool):
            lines.append(f"{k:<8}= {'T' if v else 'F':>20}")
        else:
            lines.append(f"{k:<8}= {v:>20}")
    return lines


def _fits_blob(cards, payload=b""):
    raw = [line.encode("ascii").ljust(80)[:80] for line in cards]
    raw.append(b"END".ljust(80))
    header = b"".join(raw)
    header += b" " * ((-len(header)) % 2880)
    payload += b"\0" * ((-len(payload)) % 2880)
    return header + payload


def test_read_header_only_file(tmp_path):
    # an astrometry.net wcs.fits has NAXIS=0 and only WCS cards
    cards = _cards_text({"SIMPLE": True, "BITPIX": 8, "NAXIS": 0,
                         "CTYPE1": "RA---TAN-SIP", "CTYPE2": "DEC--TAN-SIP",
                         "CRVAL1": 187.705, "CRVAL2": 12.391,
                         "CRPIX1": 60.0, "CRPIX2": 45.0,
                         "CD1_1": -0.0005, "CD1_2": 0.0,
                         "CD2_1": 0.0, "CD2_2": 0.0005,
                         "IMAGEW": 120, "IMAGEH": 90})
    path = tmp_path / "wcs.fits"
    path.write_bytes(_fits_blob(cards))
    header = fits_io.read_header(path)
    assert header["CRVAL1"] == pytest.approx(187.705)
    assert header["IMAGEW"] == 120
    # fits_io.read_fits must refuse it politely (no image HDU)
    with pytest.raises(fits_io.FitsError):
        fits_io.read_fits(path)


def test_merge_solved_wcs_replaces_stale_cards():
    header = {"SIMPLE": True, "BITPIX": 16, "NAXIS": 2, "NAXIS1": 120,
              "NAXIS2": 90, "CDELT1": 1.0, "CDELT2": 1.0,  # bogus partial WCS
              "CROTA2": 0.0, "OBJECT": "SN field"}
    cards = {"CTYPE1": "RA---TAN-SIP", "CTYPE2": "DEC--TAN-SIP",
             "CRVAL1": 187.705, "CRVAL2": 12.391, "CRPIX1": 60.0,
             "CRPIX2": 45.0, "CD1_1": -0.0005, "CD1_2": 0.0,
             "CD2_1": 0.0, "CD2_2": 0.0005}
    merged = blink.merge_solved_wcs(header, cards)
    assert "CDELT1" not in merged and "CROTA2" not in merged
    assert merged["OBJECT"] == "SN field" and merged["NAXIS1"] == 120
    w = wcs_mod.Wcs.from_header(merged)
    assert w is not None  # SIP suffix tolerated with a warning
    assert w.pixel_scale() == pytest.approx(1.8)
    # centre sits half a pixel off CRVAL (CRPIX=60,45 vs geometrical 59.5,44.5)
    ra, dec = w.center()
    assert ra == pytest.approx(187.705, abs=1e-3)
    assert dec == pytest.approx(12.391, abs=1e-3)


def test_load_user_image_blind_solve(monkeypatch, tmp_path):
    # unsolved user FITS + fake astrometry solution -> usable pair geometry
    data = np.zeros((90, 120), dtype=">f4")
    path = tmp_path / "raw.fits"
    path.write_bytes(_fits_blob(_cards_text(
        {"SIMPLE": True, "BITPIX": -32, "NAXIS": 2, "NAXIS1": 120,
         "NAXIS2": 90, "OBJECT": "SN field"}), data.tobytes()))
    cards = {"CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
             "CRVAL1": 187.705, "CRVAL2": 12.391, "CRPIX1": 60.0,
             "CRPIX2": 45.0, "CD1_1": -0.0005, "CD1_2": 0.0,
             "CD2_1": 0.0, "CD2_2": 0.0005}
    monkeypatch.setattr(blink.astrometry, "solve", lambda p, progress=None:
                        cards)
    from nightscribe.config import config
    monkeypatch.setattr(config, "get",
                        lambda k, d=None: "fake-key"
                        if k == "astrometry_key" else d)
    stages = []
    got = blink.load_user_image(path, progress=stages.append)
    assert got["wcs"].pixel_scale() == pytest.approx(1.8)
    assert any("Astrometry" in s["en"] for s in stages)


def test_load_user_image_no_wcs_no_key(tmp_path, monkeypatch):
    # no WCS and no key -> the error must point to Settings / external solvers
    data = np.zeros((10, 10), dtype=">f4")
    path = tmp_path / "nowcs.fits"
    path.write_bytes(_fits_blob(_cards_text(
        {"SIMPLE": True, "BITPIX": -32, "NAXIS": 2, "NAXIS1": 10,
         "NAXIS2": 10}), data.tobytes()))
    from nightscribe.config import config
    monkeypatch.setattr(config, "get", lambda k, d=None: d)
    with pytest.raises(blink.BlinkError) as exc:
        blink.load_user_image(path)
    assert "Astrometry.net" in exc.value.messages["en"]
    assert "Ajustes" in exc.value.messages["es"]


def test_astrometry_solve_without_key(monkeypatch):
    from nightscribe.config import config
    monkeypatch.setattr(config, "get", lambda k, d=None: d)
    assert astrometry.solve(__import__("pathlib").Path("whatever.fits")) is None


def test_load_user_image_flips_mirrored_wcs(tmp_path):
    # a mirrored solve (det CD > 0, like the real CDK17 2026zji frame) must
    # be flipped horizontally so it can align with the survey (ADR-018)
    data = np.zeros((90, 120), dtype=">f4")
    data[10, 20] = 1000.0      # marker pixel: row 10, col 20
    cards = _cards_text({"SIMPLE": True, "BITPIX": -32, "NAXIS": 2,
                         "NAXIS1": 120, "NAXIS2": 90, "CTYPE1": "RA---TAN",
                         "CTYPE2": "DEC--TAN", "CRVAL1": 187.705,
                         "CRVAL2": 12.391, "CRPIX1": 60.0, "CRPIX2": 45.0,
                         "CD1_1": 0.0005, "CD1_2": 0.0,   # det > 0: mirrored
                         "CD2_1": 0.0, "CD2_2": 0.0005})
    path = tmp_path / "mirrored.fits"
    path.write_bytes(_fits_blob(cards, data.tobytes()))
    got = blink.load_user_image(path)
    assert got["flipped"] is True
    assert not got["wcs"].is_mirrored()
    # the marker pixel moved to the mirrored column: 120-1-20 = 99
    assert got["data"][10, 99] == pytest.approx(1000.0)
    # and the sky position attached to it is unchanged
    w0 = wcs_mod.Wcs.from_header({"NAXIS1": 120, "NAXIS2": 90,
                                  "CRVAL1": 187.705, "CRVAL2": 12.391,
                                  "CRPIX1": 60.0, "CRPIX2": 45.0,
                                  "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
                                  "CD1_1": 0.0005, "CD1_2": 0.0,
                                  "CD2_1": 0.0, "CD2_2": 0.0005})
    ra0, dec0 = w0.pixel_to_sky(20, 10)
    x1, y1 = got["wcs"].sky_to_pixel(ra0, dec0)
    assert x1 == pytest.approx(99.0, abs=1e-6)
    assert y1 == pytest.approx(10.0, abs=1e-6)


def test_astrometry_cache_hit(monkeypatch, tmp_path):
    cards = {"CRVAL1": 1.0, "CRVAL2": 2.0}
    f = tmp_path / "x.fits"
    f.write_bytes(b"fake bytes")
    monkeypatch.setattr(astrometry.db, "cache_get",
                        lambda key: (json.dumps(cards).encode(), "application/json"))
    from nightscribe.config import config
    monkeypatch.setattr(config, "get",
                        lambda k, d=None: "key" if k == "astrometry_key" else d)
    assert astrometry.solve(f) == cards
