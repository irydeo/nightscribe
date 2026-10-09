############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: camera presets (photometric profile)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import cameras


def test_preset_by_key_and_alias():
    assert cameras.preset("imx455")["sensor"].startswith("Sony IMX455")
    # by a camera alias
    assert cameras.preset("ASI2600")["key"] == "imx571"
    assert cameras.preset("QHY600")["key"] == "imx455"
    assert cameras.preset("qhy42pro")["key"] == "gsense400"
    assert cameras.preset("nope") is None
    assert cameras.preset(None) is None


def test_presets_have_the_expected_shape():
    for p in cameras.PRESETS:
        assert p["key"] and p["sensor"] and p["cameras"] and p["source"]
        assert p["family"] in cameras.FAMILY_ORDER
        assert p["pixel_um"] > 0
        assert p["regime"] in ("short", "normal")
        # the new sensor facts the profile reads
        assert p["bit_depth"] in (12, 14, 16)
        assert p["sensor_w_mm"] > 0 and p["sensor_h_mm"] > 0
        assert p["resolution_w"] > 0 and p["resolution_h"] > 0
        assert p["full_well_e"] > 0
        # every preset offers a linearity suggestion: an absolute measured
        # one (GSENSE400) or the fraction the code turns into ADU
        assert (p.get("linearity_adu") is not None
                or p.get("linearity_frac") is not None)
        # a dark current never travels without the temperature it was
        # quoted at (or it would mean nothing)
        if p.get("dark_current_e_s") is not None:
            assert p.get("dark_temp_c") is not None, p["key"]


def test_keys_and_aliases_are_unique():
    keys = [p["key"] for p in cameras.PRESETS]
    assert len(keys) == len(set(keys)), "two presets share a key"
    seen = {}
    for p in cameras.PRESETS:
        for alias in (a.strip().lower() for a in p["cameras"].split(",")):
            assert alias, p["key"]
            assert alias not in seen, (
                f"alias {alias!r} in {p['key']} also in {seen[alias]}")
            seen[alias] = p["key"]


def test_the_catalogue_covers_the_expected_families():
    families = {p["family"] for p in cameras.PRESETS}
    assert families == set(cameras.FAMILY_ORDER)
    # the ~20 sensors the core catalogue promises
    assert len(cameras.PRESETS) >= 20


def test_short_regime_only_for_the_scmos():
    assert cameras.preset("gsense400")["regime"] == "short"
    assert cameras.preset("imx455")["regime"] == "normal"
    assert cameras.preset("kaf16803")["regime"] == "normal"
    # and only GSENSE400 needs the grouping, not every Gpixel part
    shorts = [p["key"] for p in cameras.PRESETS if p["regime"] == "short"]
    assert shorts == ["gsense400"]


def test_full_well_in_adu():
    p = cameras.preset("imx571")     # 50000 e-
    assert cameras.full_well_adu(p, 2.0) == 25000.0
    assert cameras.full_well_adu(p, 0) is None
    assert cameras.full_well_adu(None, 2.0) is None


def test_suggested_linearity_uses_the_real_ceilings():
    # Without a gain the ceiling is the ADC: a 16-bit part suggests ~0.9 of
    # 65535, a 14-bit one ~0.9 of 16383 (never the old flat 50000).
    p16 = cameras.preset("imx571")
    assert cameras.suggested_linearity_adu(p16) == round(65535 * 0.9)
    p14 = cameras.preset("imx294")
    assert cameras.suggested_linearity_adu(p14) == round(16383 * 0.9)
    # With a gain the full well can be the LOWER ceiling: at 1 e-/ADU the
    # imx571's 50000 e- is below the ADC, so that is what is used.
    assert cameras.suggested_linearity_adu(p16, 1.0) == round(50000 * 0.9)
    # At high gain the full well climbs above the ADC and the ADC rules.
    assert cameras.suggested_linearity_adu(p16, 0.25) == round(65535 * 0.9)
    # GSENSE400 keeps its measured absolute
    assert cameras.suggested_linearity_adu(
        cameras.preset("gsense400"), 1.0) == 53000.0


def test_profile_from_preset_fills_the_dark_temperature():
    p = cameras.preset("imx571")
    out = cameras.profile_from_preset(p)
    assert out["pixel_um"] == 3.76
    assert out["cam_full_well_e"] == 50000.0
    assert out["ccd_read_noise"] == 1.0
    assert out["cam_dark_current_e_s"] == 0.00012
    # the temperature travels WITH the dark current, or the number is mute
    assert out["cam_dark_temp_c"] == -20.0
    assert out["cam_linearity_adu"] == round(65535 * 0.9)
    # a classic camera suggests no working max exposure (no cap)
    assert out["cam_max_exposure_s"] is None


def test_profile_from_preset_is_a_full_template():
    # Choosing a camera loads its datasheet OVER whatever was there: the
    # earlier "only fill empty fields" rule left the old camera's numbers on
    # screen, which read as "the preset does nothing".
    p = cameras.preset("imx294")
    out = cameras.profile_from_preset(p)
    assert out["pixel_um"] == 4.63
    assert out["cam_full_well_e"] == 63700.0
    assert out["ccd_read_noise"] == 1.2
    assert out["cam_dark_current_e_s"] == 0.0022
    assert out["cam_dark_temp_c"] == -20.0
    # a camera that does NOT publish a dark current clears it (None), so the
    # previous camera's value does not linger
    out183 = cameras.profile_from_preset(cameras.preset("imx183"))
    assert out183["cam_dark_current_e_s"] is None
    assert out183["cam_dark_temp_c"] is None
    # the sCMOS suggests its few-second working cap
    out400 = cameras.profile_from_preset(cameras.preset("gsense400"))
    assert out400["cam_max_exposure_s"] == 300


def test_profile_from_preset_reads_the_gain_for_the_linearity():
    p = cameras.preset("imx571")
    out = cameras.profile_from_preset(p, 1.0)
    assert out["cam_linearity_adu"] == round(50000 * 0.9)


def test_combo_entries_group_by_family_with_headers():
    rows = cameras.combo_entries()
    headers = [r for r in rows if r[2]]
    assert [h[0] for h in headers] == list(cameras.FAMILY_ORDER)
    # a header carries no key; every preset key appears once
    assert all(key is None for _text, key, _is_h in headers)
    keys = [key for _text, key, is_h in rows if not is_h]
    assert keys == [p["key"] for p in cameras.PRESETS]


def test_label_names_the_cameras():
    lab = cameras.label(cameras.preset("imx455"))
    assert "IMX455" in lab and "QHY600" in lab and "ASI6200" in lab


# ------------------------------------------------ the catalogue is a file

def test_bundled_catalogue_lives_in_a_file():
    # the data left the code: a camera is added/fixed by editing the TOML
    assert cameras._BUNDLED.is_file()
    assert cameras._BUNDLED.name == "cameras.toml"
    assert cameras._BUNDLED.parent.name == "assets"


@pytest.fixture(autouse=True)
def _isolate_catalogue(tmp_path, monkeypatch):
    # every test here works on the BUNDLED catalogue alone, never on the
    # developer's own <config>/cameras.toml (which would make the counts and
    # the "only GSENSE400 is short" checks depend on their machine)
    monkeypatch.setattr(cameras, "_user_path",
                        lambda: tmp_path / "no-user-cameras.toml")
    cameras.reload()
    yield
    # back to bundled-only for whatever runs next (the patch is still active)
    monkeypatch.setattr(cameras, "_user_path",
                        lambda: tmp_path / "no-user-cameras.toml")
    cameras.reload()


def test_the_bundled_file_alone_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(cameras, "_user_path",
                        lambda: tmp_path / "does-not-exist.toml")
    cameras.reload()
    assert cameras.USER_ERROR is None
    assert len(cameras.PRESETS) >= 20


def test_a_user_file_adds_corrects_and_hides(tmp_path, monkeypatch):
    path = tmp_path / "cameras.toml"
    path.write_text(
        'hide = ["kaf09000"]\n'
        'family_order = ["My cameras"]\n'
        '\n'
        '[[camera]]\n'
        'key = "imx571"\n'
        'read_noise_e = 1.4\n'          # correct ONE field of a bundled camera
        '\n'
        '[[camera]]\n'
        'key = "mycam"\n'
        'family = "My cameras"\n'
        'sensor = "My sensor"\n'
        'cameras = "MyCam 1"\n'
        'pixel_um = 4.0\n'
        'resolution_w = 1000\n'
        'resolution_h = 1000\n'
        'sensor_w_mm = 4.0\n'
        'sensor_h_mm = 4.0\n'
        'bit_depth = 16\n'
        'full_well_e = 30000.0\n'
        'read_noise_e = 2.0\n'
        'exp_min_s = 1.0e-3\n'
        'exp_max_s = 1000.0\n'
        'regime = "normal"\n'
        'linearity_frac = 0.9\n',
        encoding="utf-8")
    monkeypatch.setattr(cameras, "_user_path", lambda: path)
    cameras.reload()
    assert cameras.USER_ERROR is None
    # corrected field by field: only read_noise changed, the rest survives
    assert cameras.preset("imx571")["read_noise_e"] == 1.4
    assert cameras.preset("imx571")["full_well_e"] == 50000.0
    # added, and its own family is shown (appended after the bundled ones)
    assert cameras.preset("mycam")["sensor"] == "My sensor"
    assert "My cameras" in cameras.FAMILY_ORDER
    # hidden
    assert cameras.preset("kaf09000") is None


def test_a_broken_user_file_is_reported_and_ignored(tmp_path, monkeypatch):
    path = tmp_path / "cameras.toml"
    path.write_text("this is not toml =", encoding="utf-8")
    monkeypatch.setattr(cameras, "_user_path", lambda: path)
    cameras.reload()
    assert cameras.USER_ERROR is not None
    # the bundled catalogue is intact
    assert len(cameras.PRESETS) >= 20
    assert cameras.preset("imx571") is not None


def test_a_user_camera_with_a_missing_field_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "cameras.toml"
    path.write_text('[[camera]]\nkey = "half"\nsensor = "Half"\n',
                    encoding="utf-8")
    monkeypatch.setattr(cameras, "_user_path", lambda: path)
    cameras.reload()
    assert cameras.USER_ERROR is not None and "half" in cameras.USER_ERROR
    assert cameras.preset("half") is None

