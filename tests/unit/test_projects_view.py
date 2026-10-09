############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the projects view (Interfaz 1.6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The merged projects view: list and project in one page, the splitter
that decides how wide the list is, the sky bar in the navigation row and
the night panel that fills the pane when nothing is selected.

Offscreen, no network: the projects are seeded straight into a temporary
database.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.core import db as coredb
    from nightscribe.core import project
    from nightscribe.gui import theme
    from nightscribe.gui import main_window as mwmod
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    tmp = tempfile.mkdtemp()
    # main_window imports the shared `db` singleton by name: redirect BOTH
    # references (the same trick test_projects_hub.py uses)
    throwaway = coredb.Database(str(Path(tmp) / "t.db"))
    monkeypatch.setattr(coredb, "db", throwaway)
    monkeypatch.setattr(mwmod, "db", throwaway)
    config.is_configured = lambda: True
    config.set("app_version", "9.9.9")
    config.set("lat", 40.41678)
    config.set("lon", -3.70379)
    # the splitter's width is remembered in the settings: a test must not
    # leave its own value behind in the user's config
    had_width = config.get("projects_list_width")
    for kind, name, ctx in (("sn", "2026abc", {"mag": 15.2, "sn_type": "Ia",
                                               "host": "NGC 4414"}),
                            ("neo", "2026 QR1", {"mag": 17.8,
                                                 "rate_arcsec_min": 12.4}),
                            ("hads", "XX Cyg", {"period_d": 0.1348,
                                                "amplitude": 0.83})):
        project.create(coredb.db, kind, name, ctx)
    w = MainWindow(snapshot=None)
    w._now_timer.stop()
    w.resize(1360, 900)
    w.show()
    for _ in range(4):
        app.processEvents()
    yield w
    if getattr(w, "_split_save", None) is not None:
        w._split_save.stop()
    if had_width is None:
        config.set("projects_list_width", None)
    else:
        config.set("projects_list_width", had_width)
    w.close()


def _rows(window):
    from nightscribe.gui.widgets.project_row import ProjectRow
    return window.projects.lst_projects.findChildren(ProjectRow)


def test_list_and_project_share_one_page(window):
    # The whole point: opening a project does not take the list away.
    from nightscribe.core import db as coredb
    from nightscribe.core import project
    from nightscribe.gui.main_window import VIEW_DETAIL
    p = project.list_projects(coredb.db)[0]
    window.navigate(VIEW_DETAIL, pid=p["id"])
    assert not window.projects.lst_projects.isHidden()
    assert not window.projects.page_detail.isHidden()
    assert window.projects.stack_detail.currentWidget() is \
        window.projects.page_detail


def test_the_visit_window_steps_aside_for_the_workbench(window):
    # Interfaz 1.6 fix: the workbench is a PAGE of the main window now, but
    # the visit window is a non-modal dialog WITH a parent, so the window
    # manager keeps it above. Opening a plate from a visit put the editor
    # behind the visit window; the visit steps aside and comes back.
    from nightscribe.core import db as coredb
    from nightscribe.core import project
    from nightscribe.gui.main_window import VIEW_DETAIL, VIEW_UFE
    p = project.list_projects(coredb.db)[0]
    # the visits panel is built with the Analysis tab (ADR-045)
    window.navigate(VIEW_DETAIL, pid=p["id"], tab="analysis")
    panel = window._project_widgets.get("visits_panel")
    assert panel is not None
    panel.btn_new.click()                  # creates the visit and opens it
    win = panel._win
    assert win is not None and not win.isHidden()
    window.navigate(VIEW_UFE)
    assert win.isHidden()             # out of the editor's way
    window.navigate(VIEW_DETAIL, pid=p["id"])
    assert not win.isHidden()                 # and back, same visit
    assert panel._win is win


def test_entering_the_workbench_without_a_visit_is_harmless(window):
    from nightscribe.gui.main_window import VIEW_UFE
    window.navigate(VIEW_UFE)
    assert window._visit_win_hidden is None
    window._ufe_leave()                    # idempotent, must not raise


def test_a_visit_closed_while_hidden_is_not_resurrected(window):
    from nightscribe.core import db as coredb
    from nightscribe.core import project
    from nightscribe.gui.main_window import VIEW_DETAIL, VIEW_UFE
    p = project.list_projects(coredb.db)[0]
    window.navigate(VIEW_DETAIL, pid=p["id"], tab="analysis")
    panel = window._project_widgets["visits_panel"]
    panel.btn_new.click()
    win = panel._win
    window.navigate(VIEW_UFE)
    assert win.isHidden()
    # a project switch closes the panel's window while it is hidden
    panel.close_visit_window()
    window.navigate(VIEW_DETAIL, pid=p["id"])
    assert panel._win is None              # nothing came back


def test_the_night_panel_fills_the_empty_pane(window):
    assert window.projects.stack_detail.currentWidget() is \
        window.projects.page_night
    panel = window._night_panel
    assert panel.ui.lbl_night_when.text()
    assert panel.ui.lbl_night_moon.text()
    assert panel.ui.lbl_night_planets.text()
    # and it is the SAME brief the sky bar shows
    from nightscribe.core import night_brief as nb
    b = nb.brief(40.41678, -3.70379)
    assert panel.ui.lbl_night_moon.text() == nb.moon_line(b)


def test_the_invitation_is_painted_on_the_resting_sky(window):
    # ADR-055: the resting pane says what to do ON the drawing, not only
    # under it. The overlay sits on the LEFT half (the SVG darkens it for
    # text) and must not eat the clicks meant for what is under it.
    from PySide6.QtCore import Qt
    panel = window._night_panel
    u = panel.ui
    assert u.lbl_resting_head.text()
    assert u.lbl_resting_hint.text()
    assert u.lbl_resting_head.objectName() == "restingHead"
    assert u.lbl_resting_hint.objectName() == "restingHint"
    assert u.nightOverlay.testAttribute(Qt.WA_TransparentForMouseEvents)
    # it is ON the sky, and it stays on the left
    sky = panel._sky
    assert sky.geometry().intersects(u.nightOverlay.geometry())
    assert u.lbl_resting_head.x() + u.lbl_resting_head.width() \
        <= sky.width() * 0.7
    # the way in to a new project is still the button below
    assert u.btn_night_new.text()


def test_the_list_width_is_the_observers_and_is_remembered(window):
    from nightscribe.config import config
    from nightscribe.gui.main_window import _LIST_W_DEFAULT, _LIST_W_MAX
    window._apply_list_width()
    assert window._projects_split.sizes()[0] == _LIST_W_DEFAULT
    # dragging the handle: the width is kept and written to the settings
    window._apply_list_width(500)
    window._on_splitter_moved(500, 1)
    assert window._list_width == 500
    window._split_save.stop()
    window._split_save.timeout.emit()
    assert int(config.get("projects_list_width")) == 500
    # and a width beyond the range is clamped when it comes back
    config.set("projects_list_width", 9000)
    window._restore_list_width()
    assert window._list_width == _LIST_W_MAX


def test_the_fold_button_collapses_and_restores_the_list(window):
    window._apply_list_width(420)
    window._toggle_list(False)
    assert window._projects_split.sizes()[0] == 0
    window._toggle_list(True)
    assert window._projects_split.sizes()[0] == 420


def test_the_sky_bar_is_in_the_navigation_row(window):
    bar = window._sky_bar
    assert bar.lbl_when.text()                  # the darkness window
    assert "→" in bar.lbl_when.text()
    assert "%" in bar.lbl_moon_txt.text()       # the Moon
    assert not bar.lbl_moon.pixmap().isNull()   # drawn at tonight's phase
    # visible from every view, not only from Projects
    from nightscribe.gui.main_window import VIEW_TONIGHT
    window._goto_tab(VIEW_TONIGHT)
    assert not bar.isHidden()


def test_the_sky_bar_waits_for_a_site(window):
    from nightscribe.config import config
    config.set("lat", 0.0)
    config.set("lon", 0.0)
    window.refresh_sky_bar()
    assert window._sky_bar.lbl_moon.isHidden()
    assert window._sky_bar.lbl_when.text()      # "Set your observatory"


def test_a_project_row_carries_its_kind_colour(window):
    from nightscribe.gui import theme
    row = _rows(window)[0]
    assert row.lbl_detail.text()                # the one-glance numbers
    assert "·" in row.lbl_detail.text()
    kind_color = row._kind_color
    row.set_selected(True)
    sheet = row.styleSheet()
    # the selection is tinted with the row's OWN kind hue, not the global
    # blue: six projects on screen, and the hue says which one
    assert kind_color in sheet
    assert theme.C_SEL not in sheet
    row.set_selected(False)
    # unselected, the hue stays as a dimmed spine: the list reads as a
    # colour map even before you click anything
    assert "border-left: 3px solid" in row.styleSheet()
    assert theme.composite(kind_color, "80", over=theme.C_BASE) \
        in row.styleSheet()


def test_a_narrow_row_drops_the_least_important_bits(window):
    row = _rows(window)[0]
    row.resize(320, 54)
    assert row.lbl_detail.isHidden()       # too narrow for the numbers
    assert row.lbl_camp.isHidden()
    # The numbers come back as soon as they REALLY fit, and "really" is
    # measured with the running font: a fixed 500 is a Linux number and this
    # assertion failed on the Windows runner, where the same text is wider.
    fits = next(w for w in range(320, 1200, 10) if row._detail_fits(w))
    row.resize(fits, 54)
    assert not row.lbl_detail.isHidden()


def test_the_curve_wins_the_room_at_the_default_width(window):
    # Measured: the thumbnail and the object's numbers do not fit together
    # in the default list. The curve wins (the name cannot tell you what it
    # says) and the numbers move to the tooltip, so nothing is lost.
    from nightscribe.core import db as coredb
    from nightscribe.core import followup, project
    p = project.list_projects(coredb.db)[0]
    for i in range(6):
        followup.add_point(coredb.db, p["id"], 61000.0 + i, "V",
                           15.0 + 0.1 * i)
    window.on_refresh_projects()
    # a refresh rebuilds the rows and deleteLater() has not run yet, so the
    # list still holds the corpses: process events and take the LAST match
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    row = [r for r in _rows(window) if r.lbl_name.text()
           == p["object_name"]][-1]
    row.resize(392, 54)                     # the default list width
    assert not row.lbl_spark.isHidden()        # the curve is there
    assert row.lbl_detail.isHidden()   # ... and the numbers gave way
    assert row.toolTip()                    # but they are one hover away
    assert row.lbl_detail.text() in row.toolTip()
    # widening the list brings both back; the width is measured, not
    # guessed (the numbers' threshold depends on the running font)
    fits = next(w for w in range(392, 1400, 10) if row._detail_fits(w))
    row.resize(fits, 54)
    assert not row.lbl_spark.isHidden()
    assert not row.lbl_detail.isHidden()
    assert not row.toolTip()


def _paints_glyph(widget):
    # @args: widget - a shown button
    # @return: True when it paints at least one clearly bright pixel (its
    #          glyph). A small fixed-width QPushButton with the global
    #          6px/16px padding has no content rect left and draws an EMPTY
    #          box (the brightest pixel is its own border, ~70-115): that is
    #          the reported bug this guards.
    img = widget.grab().toImage()
    return any(img.pixelColor(x, y).lightness() > 130
               for y in range(img.height()) for x in range(img.width()))


def test_the_small_glyph_buttons_paint_their_glyph(window):
    # Reported: the drawer's ✕ (close the project list) and the masthead's
    # ☆ (favorite) drew as empty boxes. Both are small fixed-width
    # QPushButtons, and the global padding clips the glyph unless they carry
    # compact="true" (the same fix the row × and the step ✕ already had).
    from PySide6.QtWidgets import QApplication, QPushButton
    from nightscribe.core import db as coredb
    from nightscribe.core import project
    from nightscribe.gui.main_window import VIEW_DETAIL, VIEW_TONIGHT
    p = project.list_projects(coredb.db)[0]
    window.navigate(VIEW_DETAIL, pid=p["id"])
    for _ in range(4):
        QApplication.processEvents()
    assert _paints_glyph(window.projects.btn_favorite), \
        "the favorite ☆ is clipped to an empty box"
    # The drawer is the project list overlay; it opens from a view OTHER
    # than Projects (VIEW_HOME is Projects here), so switch to Tonight first.
    window.navigate(VIEW_TONIGHT)
    for _ in range(4):
        QApplication.processEvents()
    window._drawer_open(True)
    for _ in range(4):
        QApplication.processEvents()
    assert window._drawer.isVisible(), "the drawer did not open"
    close = next(b for b in window._drawer.findChildren(QPushButton)
                 if b.text() == "✕")
    assert _paints_glyph(close), "the drawer close ✕ is clipped to an empty box"
    window._drawer_open(False)
