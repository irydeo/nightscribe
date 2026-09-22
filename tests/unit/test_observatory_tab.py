############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the Capture step's CCDciel block (ADR-043)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Capture step owns the CCDciel connection and the mount (ADR-030,
ADR-043):

  * the main window is down to three tabs (the Observatory tab is gone)
  * the CCD block is built per project page inside the Capture step and
    registered in window._obs_widgets (reset when the page is torn down)
  * the disconnected state disables capture + slew, keeps connect alive
  * the block works on the CURRENT project (no target picker): with none
    open, the capture buttons stay disabled with a "open a project" tip

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
    # keep the tests hermetic: no auto-compute
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


# ---------------- helper ----------------

def _select_project(window, name="SN 2099obs"):
    # Create a project, select it in the hub and open the Capture step:
    # that is where the CCD block (window._obs_widgets) gets built.
    from PySide6.QtCore import Qt
    import nightscribe.core.db as dbmod
    from nightscribe.core import project as proj_mod
    p = proj_mod.create(dbmod.db, "sn", name, {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    window._project_selected()
    window._build_project_page(window._current_project)
    window._show_tab("plan")
    return p


# ---------------- tabs & ownership ----------------

def test_three_tabs_no_observatory(window):
    # ADR-043: the Observatory tab is gone; its control surface moved into
    # the Capture step of each project page.
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import (TAB_TONIGHT, TAB_PROJECTS,
                                             TAB_CAMPAIGNS)
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 3
    assert tabs.widget(TAB_TONIGHT) is window.tonight
    assert tabs.widget(TAB_PROJECTS) is window.projects
    assert tabs.widget(TAB_CAMPAIGNS) is window.campaigns
    titles = [tabs.tabText(i) for i in range(3)]
    assert not any("Observatory" in t for t in titles)


def test_ccd_block_lives_in_the_plan_page(window):
    # ADR-043: the whole control surface rebuilds with the project page and
    # every control is a child of the Capture step page; the slots find it
    # through window._obs_widgets.
    _select_project(window)
    page = window._tab_pages["plan"]
    for key in ("ccd_connect", "ccd_status", "cmb_ccd_filter"):
        w = window._obs_widgets[key]
        assert page.isAncestorOf(w), f"{key} should live in the plan page"


def test_ccd_registry_reset_on_page_teardown(window):
    # The block dies with the page: tearing the page down must not leave
    # slots pointing at dead widgets.
    _select_project(window, name="SN 2099rt")
    assert window._obs_widgets
    window._clear_project_page()
    assert window._obs_widgets == {}


# ---------------- state ----------------

def test_ccd_block_is_bound_to_the_current_project(window):
    # ADR-043: no target picker. Opening another project rebinds the block
    # to it automatically; there is no combo to drive.
    first = _select_project(window, name="SN 2099a")
    second = _select_project(window, name="SN 2099rt")
    # the selection re-reads the project from the db, so compare ids, not
    # dict identity: the block follows whichever project is current
    assert window._current_project["id"] == second["id"]
    assert second["id"] != first["id"]
    assert "obs_target" not in window._obs_widgets


def test_disconnected_state_disables_capture(window):
    _select_project(window)
    window._ccd_connected = False
    window._ccd_apply_state()
    assert not window._obs_widgets["ccd_disconnect"].isEnabled()
    assert not window._obs_widgets["ccd_goto"].isEnabled()
    assert window._obs_widgets["ccd_connect"].isEnabled()


