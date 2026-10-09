############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the setup helpers (wizard.py)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The helpers the wizard and the Welcome view share.

They are exercised against a stub husk carrying only the widgets the helper
touches, so no window, no network and no database are involved.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


class _Husk:
    """Only the widgets _detect / _resolve_site / _apply_site reach for."""

    def __init__(self):
        from PySide6.QtWidgets import (QDoubleSpinBox, QLabel, QLineEdit,
                                       QSpinBox)
        self.spn_site_lat = QDoubleSpinBox()
        self.spn_site_lat.setRange(-90.0, 90.0)
        self.spn_site_lat.setDecimals(5)
        self.spn_site_lon = QDoubleSpinBox()
        self.spn_site_lon.setRange(-180.0, 180.0)
        self.spn_site_lon.setDecimals(5)
        self.spn_site_height = QSpinBox()
        self.spn_site_height.setRange(0, 9000)
        self.edt_site_name = QLineEdit()
        self.edt_site_mpc = QLineEdit()
        self.lbl_site_status = QLabel()


def test_detect_fills_the_site(qapp, monkeypatch):
    from nightscribe.gui import wizard
    from nightscribe.core.sources import geo
    monkeypatch.setattr(geo, "ip_location",
                        lambda force=False: {"lat": 40.41678, "lon": -3.70379,
                                             "name": "Madrid, Spain"})
    monkeypatch.setattr(geo, "elevation", lambda lat, lon, force=False: 650)
    h = _Husk()
    wizard._detect(h)
    assert h.spn_site_lat.value() == 40.41678
    assert h.spn_site_lon.value() == -3.70379
    assert h.spn_site_height.value() == 650
    assert h.edt_site_name.text() == "Madrid, Spain"
    assert "Madrid" in h.lbl_site_status.text()


def test_detect_overwrites_the_name(qapp, monkeypatch):
    # Like the MPC resolve: pressing the button is an explicit statement of
    # where the site is, so the detected city replaces what was typed.
    from nightscribe.gui import wizard
    from nightscribe.core.sources import geo
    monkeypatch.setattr(geo, "ip_location",
                        lambda force=False: {"lat": 40.4, "lon": -3.7,
                                             "name": "Madrid, Spain"})
    monkeypatch.setattr(geo, "elevation", lambda lat, lon, force=False: None)
    h = _Husk()
    h.edt_site_name.setText("mi casita")
    wizard._detect(h)
    assert h.edt_site_name.text() == "Madrid, Spain"


def test_detect_survives_a_broken_elevation(qapp, monkeypatch):
    # The real failure of 2026-10-02: open-meteo's list payload raised a
    # TypeError inside the elevation call, it escaped the button's slot and
    # the status line stayed on "Finding your observatory..." forever, with
    # the coordinates already on screen. The height is a finishing touch:
    # losing it must never cost the detection.
    from nightscribe.gui import wizard
    from nightscribe.core.sources import geo
    monkeypatch.setattr(geo, "ip_location",
                        lambda force=False: {"lat": 1.5, "lon": 2.5,
                                             "name": "Somewhere"})
    monkeypatch.setattr(geo, "elevation",
                        lambda lat, lon, force=False: (_ for _ in ()).throw(
                            TypeError("float() argument must be a real number")))
    h = _Husk()
    wizard._detect(h)
    assert h.spn_site_lat.value() == 1.5
    assert h.spn_site_lon.value() == 2.5
    assert h.spn_site_height.value() == 0
    assert "Somewhere" in h.lbl_site_status.text()


def test_detect_reports_an_offline_service(qapp, monkeypatch):
    from nightscribe.gui import wizard
    from nightscribe.core.sources import geo
    monkeypatch.setattr(geo, "ip_location", lambda force=False: None)
    h = _Husk()
    wizard._detect(h)
    # the message now points at the three real ways out, the map included
    assert "map" in h.lbl_site_status.text().lower()


def test_resolve_site_overwrites_the_name(qapp, monkeypatch):
    # Resolving an MPC code is an explicit action and the code IS the site's
    # identity, so the official name replaces a name typed earlier.
    from nightscribe.gui import wizard
    from nightscribe.core.sources import obscodes
    monkeypatch.setattr(obscodes, "lookup",
                        lambda code: {"lat": 40.55, "lon": -3.37,
                                      "name": "Irydeo Observatory"})
    h = _Husk()
    h.edt_site_name.setText("mi casita")
    h.edt_site_mpc.setText("z41")
    wizard._resolve_site(h)
    assert h.edt_site_name.text() == "Irydeo Observatory"
    assert h.spn_site_lat.value() == 40.55
    assert "Irydeo Observatory" in h.lbl_site_status.text()


def test_resolve_site_refuses_a_short_code(qapp, monkeypatch):
    from nightscribe.gui import wizard
    h = _Husk()
    h.edt_site_mpc.setText("Z4")
    wizard._resolve_site(h)
    assert "three characters" in h.lbl_site_status.text().lower()


class _EquipHusk:
    """Only the widgets _setup_equipment / _apply_equipment reach for."""

    def __init__(self):
        from PySide6.QtWidgets import QComboBox, QDoubleSpinBox
        self.spn_aperture = QDoubleSpinBox()
        self.spn_aperture.setRange(0.0, 100.0)
        self.spn_limit_mag = QDoubleSpinBox()
        self.spn_limit_mag.setRange(5.0, 25.0)
        self.spn_limit_mag.setDecimals(1)
        self.spn_pixel_um = QDoubleSpinBox()
        self.spn_pixel_um.setRange(1.0, 30.0)
        self.spn_pixel_um.setDecimals(2)
        self.spn_focal_mm = QDoubleSpinBox()
        self.spn_focal_mm.setRange(50.0, 20000.0)
        self.cmb_camera_type = QComboBox()
        self.cmb_camera_type.addItems(["CCD", "CMOS", "DSLR"])
        self.cmb_cam_preset = QComboBox()


def test_setup_equipment_lists_the_presets(qapp, monkeypatch):
    # The combo carries "None" first and one entry per preset, and choosing
    # one writes its datasheet pixel size on the spot (the scale hook reads
    # that spin, so the step answers in the same breath).
    from nightscribe.config import config
    from nightscribe.gui import wizard
    from nightscribe.core import cameras
    monkeypatch.setitem(config._data, "cam_preset", "")
    monkeypatch.setitem(config._data, "pixel_um", 3.76)
    h = _EquipHusk()
    wizard._setup_equipment(h)
    # "None" + one row per preset + one header per family
    assert h.cmb_cam_preset.count() == \
        1 + len(cameras.PRESETS) + len(cameras.FAMILY_ORDER)
    assert h.cmb_cam_preset.itemData(0) == ""
    h.cmb_cam_preset.setCurrentIndex(h.cmb_cam_preset.findData("kaf8300"))
    assert h.spn_pixel_um.value() == 5.4


def test_apply_equipment_writes_and_fills_a_new_preset(qapp, monkeypatch):
    # A preset chosen in the visit brings its datasheet profile; one restored
    # unchanged leaves the profile alone, because the observer may have
    # measured and tuned it in Settings.
    from nightscribe.config import config
    from nightscribe.gui import wizard
    for key in ("aperture_inches", "limit_mag", "pixel_um", "focal_mm",
                "camera_type", "cam_preset", "cam_full_well_e",
                "ccd_read_noise"):
        monkeypatch.setitem(config._data, key, config.get(key))
    monkeypatch.setitem(config._data, "cam_preset", "")
    monkeypatch.setitem(config._data, "ccd_read_noise", None)
    monkeypatch.setitem(config._data, "cam_full_well_e", None)
    h = _EquipHusk()
    wizard._setup_equipment(h)
    h.spn_aperture.setValue(9.0)
    h.spn_limit_mag.setValue(19.6)
    h.cmb_camera_type.setCurrentText("CMOS")
    h.cmb_cam_preset.setCurrentIndex(h.cmb_cam_preset.findData("kaf8300"))
    wizard._apply_equipment(h)
    assert config.get("aperture_inches") == 9.0
    assert config.get("limit_mag") == 19.6
    assert config.get("camera_type") == "CMOS"
    assert config.get("cam_preset") == "kaf8300"
    assert config.get("ccd_read_noise") == 9.0        # the preset's datasheet
    assert config.get("cam_full_well_e") == 25500.0
    # a second visit with the SAME preset leaves the tuned profile alone
    config.set("ccd_read_noise", 7.5)                 # measured by the observer
    wizard._apply_equipment(h)
    assert config.get("ccd_read_noise") == 7.5
