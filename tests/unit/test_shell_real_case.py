############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Shell regression tests: the real (configured) case
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The bugs the first Interfaz 1.0 pass shipped were only visible in the
REAL case: a configured observatory, a current version and at least one
project, so Welcome is never built and the stack keeps its four main pages.
The other tests forced `is_configured=False`, which built Welcome at index
4 and made the appended indices line up by accident, hiding both the UFE
index bug and the hidden dashboard/detail pages.

These tests pin the real case: Home on start (no Welcome), the fixed view
indices, and the reparented pages actually VISIBLE. No network: no project
is selected (the detail visibility is checked through the view switch)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    from nightscribe.config import config
    from nightscribe.core import project as proj_mod
    from nightscribe.core.db import db
    from nightscribe.version import base_version
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    # a configured site and the CURRENT version: Welcome is not due
    config.set("lat", 40.0)
    config.set("lon", -3.0)
    config.set("app_version", base_version())
    if not proj_mod.list_projects(db):
        proj_mod.create(db, "sn", "SN shell", {"ra_deg": 10.0, "dec_deg": 20.0})
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    for _ in range(6):
        app.processEvents()
    yield w
    w.close()


def test_opens_on_projects_without_welcome(window):
    from nightscribe.gui.main_window import VIEW_HOME
    # Interfaz 1.6: the projects view holds the list AND the project, so
    # the shell has 3 main pages + welcome + ufe
    assert window._shell_stack().count() == 5
    assert window._shell_stack().currentIndex() == VIEW_HOME
    assert window._welcome is None                 # nothing to set up


def test_the_resting_pane_is_the_night(window):
    # Interfaz 1.6: with no project selected the right pane shows the night
    # (the retired "needs your attention" dashboard is gone).
    assert window.projects.stack_detail.currentWidget() is \
        window.projects.page_night
    assert window._night_panel is not None
    assert not hasattr(window, "_cadence_band")


def test_opening_a_project_shows_it_beside_the_list(window):
    # The whole point of the merge: the project comes up WITHOUT the list
    # going away, in the same shell page.
    from nightscribe.core import db as _db
    from nightscribe.core import project as _project
    from nightscribe.gui.main_window import VIEW_DETAIL
    p = _project.create(_db.db, "sn", "2026test",
                        {"ra_deg": 10.0, "dec_deg": 20.0, "mag": 15.0})
    window.on_refresh_projects()
    window.navigate(VIEW_DETAIL, pid=p["id"])
    assert window._shell_stack().currentIndex() == VIEW_DETAIL
    assert window.projects.page_detail.isVisible()
    assert window.projects.lst_projects.isVisible()


def test_home_matches_the_mock(window):
    # Interfaz 1.2: header with the new-project tile and the sky band with
    # its calendar link.
    from PySide6.QtWidgets import QPushButton
    tiles = [b for b in window.findChildren(QPushButton)
             if b.objectName() == "newTile"]
    assert tiles and tiles[0].isEnabled()
    # Interfaz 1.6: the sky moved to the navigation row
    assert window._sky_bar is not None
    assert any("calendar" in b.text().lower()
               for b in window._sky_bar.findChildren(QPushButton))
    # the app logo sits in the navigation bar
    assert not window._menus.lbl_nav_logo.pixmap().isNull()


def test_home_hides_the_drawer_and_its_tab(window):
    # Interfaz 1.3: on Home the list IS the screen, so the vertical tab is
    # hidden and the drawer does not open; both come back elsewhere.
    # Campaigns (not Tonight) so the test never triggers the network.
    from nightscribe.gui.main_window import VIEW_CAMPAIGNS
    assert not window._menus.btn_vtab.isVisible()
    window._drawer_open(True)
    assert not window._drawer.isVisible()
    window.navigate(VIEW_CAMPAIGNS)
    assert window._menus.btn_vtab.isVisible()
    window._drawer_open(True)
    assert window._drawer.isVisible()
    window._drawer_open(False)


def test_drawer_shows_the_same_rich_rows_as_home(window):
    # Interfaz 1.1: the overlay drawer reuses ProjectRow, the SAME rich
    # rows as the hub list (not the plain "[SN] name" text it used to).
    # Interfaz 1.3: it opens from a view other than Home.
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from nightscribe.gui.main_window import VIEW_CAMPAIGNS
    from nightscribe.gui.widgets.project_row import ProjectRow
    window.navigate(VIEW_CAMPAIGNS)
    window._drawer_open(True)
    for _ in range(3):
        QApplication.processEvents()
    dl = window._drawer_list
    assert dl.count() >= 1
    rows = [dl.itemWidget(dl.item(i)) for i in range(dl.count())]
    assert all(isinstance(r, ProjectRow) for r in rows)
    home_ids = {window.projects.lst_projects.item(i).data(Qt.UserRole)
                for i in range(window.projects.lst_projects.count())
                if window.projects.lst_projects.item(i).data(
                    Qt.UserRole) is not None}
    drawer_ids = {dl.item(i).data(Qt.UserRole) for i in range(dl.count())}
    assert drawer_ids == home_ids
    assert "SN shell" in {r.lbl_name.text() for r in rows}


def test_workbench_has_a_fixed_index_and_shows(window):
    # the bug: with no Welcome the UFE was appended at index 4 while
    # VIEW_UFE was 5, so it never showed.
    from nightscribe.gui.main_window import VIEW_UFE
    window._ufe_page()
    window._goto_tab(VIEW_UFE)
    assert window._shell_stack().currentIndex() == VIEW_UFE
    assert window._ufe.isVisible()
    # and leaving the view keeps it alive (its state survives, ADR-047)
    from nightscribe.gui.main_window import VIEW_HOME
    window._goto_tab(VIEW_HOME)
    assert window._ufe is not None
