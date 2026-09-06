############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Settings dialog tabs smoke tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Settings dialog layout smoke tests (offscreen, ADR-028).

The dialog is now a QTabWidget with three tabs (Site & equipment /
Observing / Integrations) instead of eight stacked boxes.
What these tests lock in:

* the tab order and the widgets that live on each tab;
* the language selector on the first tab (system/es/en round-trip);
* the optional TNS bot fields on Integrations;
* the horizon chunk still keeps its ADR-020 behaviour (same objects —
  test_settings_horizon.py drives the real preview; this file only
  checks the layout it lives on).

No network, no full MainWindow: the tests load the exact .ui the
settings flow loads (settings_dialog.ui) and read the tree.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _tab_names(dlg):
    # @args: dlg - loaded settings dialog
    # @return: list of visible tab titles in order
    return [dlg.tabWidget.tabText(i) for i in range(dlg.tabWidget.count())]


def _tab_widgets(dlg, index):
    # @args: dlg - loaded settings dialog, index - tab index
    # @return: objectName of every widget on that page, recursively
    from PySide6.QtWidgets import QWidget
    page = dlg.tabWidget.widget(index)
    return [w.objectName() for w in page.findChildren(QWidget) if w.objectName()]


def test_three_tabs_in_order(qapp):
    dlg = _dlg()
    tabs = _tab_names(dlg)
    assert len(tabs) == 4
    # the last tab is the CCDciel JSON-RPC page (ADR-030), named identically
    # in every locale on purpose
    assert tabs[-1] == "CCDciel"
    # the first tab is the site page (language-aware)
    assert tabs[0] in ("Site & equipment", "Sitio y equipo")
    dlg.deleteLater()


def test_site_tab_widgets(qapp):
    dlg = _dlg()
    names = set(_tab_widgets(dlg, 0))
    for w in [" edt_mpc_code", "btn_resolve", "edt_obs_name",
              "spn_lat", "spn_lon", "spn_height", "spn_aperture",
              "spn_limit_mag", "spn_pixel_um", "spn_focal_mm",
              "cmb_language"]:
        assert w.strip() in names, f"{w} expected on the Site & equipment tab"
    dlg.deleteLater()


def test_language_combo_populated_by_on_open_settings(qapp):
    dlg = _dlg()
    assert dlg.cmb_language is not None
    # the combo is the selector; the fixed 3-slot order
    # (system=0, es=1, en=2) is asserted against main_window.py below
    import inspect
    import re
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert re.search(r"\(\s*\"system\"\s*,\s*\"es\"\s*,\s*\"en\"\s*\)", src), \
        "on_open_settings must map the combo order to system/es/en"
    dlg.deleteLater()


def test_observating_tab_widgets(qapp):
    dlg = _dlg()
    names = set(_tab_widgets(dlg, 1))
    for w in ["edt_horizon_file", "btn_horizon_browse",
              "spn_horizon_margin", "spn_min_alt", "lbl_horizon_stats",
              "chk_moon_enabled", "spn_moon_sep", "spn_moon_illum",
              "spn_overhead"]:
        assert w in names, f"{w} expected on the Observing tab"
    dlg.deleteLater()


def test_integrations_tab_widgets(qapp):
    dlg = _dlg()
    names = set(_tab_widgets(dlg, 2))
    for w in ["edt_neofixer_key", "edt_astrometry_key",
              "edt_tns_bot", "edt_tns_bot_key"]:
        assert w in names, f"{w} expected on the Integrations tab"
    dlg.deleteLater()


def test_ccdciel_tab_widgets(qapp):
    dlg = _dlg()
    names = set(_tab_widgets(dlg, 3))
    for w in ["edt_ccdciel_host", "spn_ccdciel_port", "chk_ccdciel_auto"]:
        assert w in names, f"{w} expected on the CCDciel tab"
    dlg.deleteLater()


def _dlg():
    # @args: none; reuses the module-scoped qapp of the sibling test
    # @return: a loaded settings dialog (caller deletes it)
    from nightscribe.gui.main_window import _load_ui
    return _load_ui("settings_dialog")
