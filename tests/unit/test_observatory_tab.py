############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: observatory tab (UX, UD.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Observatory tab owns the CCDciel connection and the mount:

  * it is the 6th tab of the main window
  * its connect/status/goto widgets are window-owned (never orphaned by
    a project rebuild, the old per-project Plan block mistake)
  * the disconnected state disables capture + slew, keeps connect alive
  * the target combo lists the active projects

Offscreen harness, same pattern as test_campaigns_tab.py.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------- harness ----------------

@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a throw
    # away file so the tab never touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("obsdb") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    from nightscribe.gui.main_window import MainWindow
    # keep the tests hermetic: no auto-compute network worker on startup
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


# ---------------- tabs & ownership ----------------

def test_observatory_tab_exists(window):
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import TAB_OBSERVATORY
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 5      # ADR-036 J0: History left for the menu
    assert tabs.widget(TAB_OBSERVATORY) is window.observatory


def test_ccd_widgets_are_window_owned(window):
    # UX-j: the CCDciel controls live in the Observatory tab, outside any
    # project rebuild path (the old per-project Plan block orphaned them)
    w = window._obs_widgets["ccd_connect"]
    parent = w.parentWidget()
    while parent is not None:
        assert parent is not window.projects
        parent = parent.parentWidget()


# ---------------- state & target list ----------------

def test_disconnected_state_disables_capture(window):
    window._ccd_connected = False
    window._ccd_apply_state()
    assert not window.observatory.btn_obs_disconnect.isEnabled()
    assert not window.observatory.btn_obs_goto.isEnabled()
    assert window.observatory.btn_obs_connect.isEnabled()


def test_target_combo_lists_active_projects(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.create(mw.db, "sn", "SN 2099obs", {"mag": 15.0})
    window._refresh_obs_targets()
    texts = [window.observatory.cmb_obs_target.itemText(i)
             for i in range(window.observatory.cmb_obs_target.count())]
    assert any("SN 2099obs" in t for t in texts)
