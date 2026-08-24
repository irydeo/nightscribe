############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: local horizon (ADR-020)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import horizon


def test_parse_sample_fixture(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    assert h is not None
    pts = h.points
    assert len(pts) == 36
    # sorted by azimuth
    assert pts[0][0] == 0.0 and pts[-1][0] == 350.0


def test_wall_and_gap_interpolation(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    # NE wall: az 60 -> 60 deg
    assert abs(h.alt_at(60.0) - 60.0) < 1e-6
    # uniform floor: az 120 -> 30 deg
    assert abs(h.alt_at(120.0) - 30.0) < 1e-6
    # southern gap: az 180 -> 20 deg
    assert abs(h.alt_at(180.0) - 20.0) < 1e-6
    # interpolation between 30 (az 30) and 60 (az 40): az 35 -> 45 deg
    assert abs(h.alt_at(35.0) - 45.0) < 1e-6


def test_wrap_across_seam(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    # across the 0/360 seam: between az 350 (30) and az 0 (30) -> 30
    assert abs(h.alt_at(355.0) - 30.0) < 1e-6
    assert abs(h.alt_at(5.0) - 30.0) < 1e-6
    # az slightly negative wraps to ~360
    assert abs(h.alt_at(-5.0) - 30.0) < 1e-6


def test_flat_horizon_constant():
    f = horizon.FlatHorizon(30.0)
    assert f.is_flat
    assert f.alt_at(0.0) == 30.0
    assert f.alt_at(123.4) == 30.0


def test_from_config_falls_back_to_flat(fake_cfg):
    # fake_cfg has no horizon_file -> flat min_alt (30)
    h = horizon.from_config(fake_cfg)
    assert h.is_flat
    assert h.alt_at(0.0) == 30.0


def test_from_config_uses_file(fake_cfg, fixture_path):
    fake_cfg._v["horizon_file"] = str(fixture_path / "horizon_sample.txt")
    h = horizon.from_config(fake_cfg)
    assert not h.is_flat
    assert abs(h.alt_at(60.0) - 60.0) < 1e-6


def test_from_config_missing_file_falls_back(fake_cfg, tmp_path):
    fake_cfg._v["horizon_file"] = str(tmp_path / "does_not_exist.txt")
    h = horizon.from_config(fake_cfg)
    assert h.is_flat
    assert h.alt_at(0.0) == 30.0


def test_load_rejects_garbage(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("# only comments\n\n", encoding="utf-8")
    assert horizon.load(p) is None
