############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Welcome view tests (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Welcome view replaces the modal first-run/update wizard: it hosts
the three setup steps inline and gates navigation on the update's Data
step. These tests pin the decision (when Welcome is shown), the gate and
the CTA's site requirement, plus the Interfaz 1.4 additions: the painted
hero, the live "your night, now" strip (pure local ephemeris) and the kind
cards. No network: the detect/resolve buttons are not exercised here (they
are the wizard's own, tested by hand)."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def make_window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    # a first run with no site: Welcome is due
    monkeypatch.setattr(config, "is_configured", lambda: False)
    # an "old" version forces the update path too
    config.set("app_version", "")
    windows = []

    def _make(snapshot=None):
        w = MainWindow(snapshot=snapshot)
        w._now_timer.stop()
        w._blink_timer.stop()
        w._blink_render_timer.stop()
        windows.append(w)
        return w

    yield _make
    for w in windows:
        w.close()


def test_welcome_is_branded_and_has_the_onboarding_cards(make_window):
    # Interfaz 1.2: the app logo, the accented wordmark and the three
    # onboarding cards of the mock.
    w = make_window(snapshot=None)
    u = w._welcome.ui
    assert not u.lbl_logo.pixmap().isNull()
    assert "SCRIBE" in u.welcomeWordmark.text()
    for name in ("wcard1", "wcard2", "wcard3",
                 "btn_card2_guide", "btn_card3_skycal"):
        assert hasattr(u, name)


def test_first_run_shows_welcome(make_window):
    from nightscribe.gui.main_window import VIEW_WELCOME
    w = make_window(snapshot=None)
    assert w._welcome is not None
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    # no database to report on: no gate
    assert w._welcome_gate is False


def test_first_run_stays_on_welcome_after_the_startup_refresh(make_window):
    # Regression: the deferred on_refresh_projects() found no selection and
    # _clear_project_detail -> _show_dashboard used to switch to Home,
    # yanking the observer out of Welcome on the very first frame.
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui.main_window import VIEW_WELCOME
    w = make_window(snapshot=None)
    for _ in range(6):
        QApplication.processEvents()
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    assert w._welcome is not None


def test_update_is_a_gate_until_acknowledged(make_window):
    from nightscribe.gui.main_window import VIEW_WELCOME, VIEW_HOME
    snap = {"integrity": "ok", "file": Path("nightscribe-before.db"),
            "size": 1024, "schema_version": 0}
    w = make_window(snapshot=snap)
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    assert w._welcome_gate is True
    # every other view is blocked while the report is unacknowledged
    w._goto_tab(VIEW_HOME)
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    # acknowledging unlocks and lands on Home
    w._welcome_finished()
    assert w._welcome_gate is False
    assert w._shell_stack().currentIndex() == VIEW_HOME


def test_cta_needs_a_site(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    u.spn_site_lat.setValue(0.0)
    u.spn_site_lon.setValue(0.0)
    u.edt_site_mpc.setText("")
    ws._refresh_create()
    assert not u.btn_create.isEnabled()
    u.spn_site_lat.setValue(40.41678)
    u.spn_site_lon.setValue(-3.70379)
    ws._refresh_create()
    assert u.btn_create.isEnabled()


def test_stepper_switches_panels(make_window):
    w = make_window(snapshot=None)
    u = w._welcome.ui
    w._welcome.show_step("kinds")
    assert u.setup_stack.currentIndex() == 1
    w._welcome.show_step("data")
    assert u.setup_stack.currentIndex() == 2
    assert u.btn_step_data.isChecked()


def test_stepper_marks_the_steps_behind_us(make_window):
    # Interfaz 1.4: the rail fills and the steps behind us carry a tick.
    # The tick is added to the .ui's own (translated) text, never replacing
    # it, so the label stays translatable.
    w = make_window(snapshot=None)
    u = w._welcome.ui
    base = u.btn_step_obs.text()
    assert not base.startswith("✓")
    w._welcome.show_step("data")
    assert u.btn_step_obs.text().startswith("✓")
    assert base in u.btn_step_obs.text()
    assert u.btn_step_obs.property("state") == "done"
    assert u.rail_sep1.property("state") == "done"
    assert u.rail_sep2.property("state") == "done"
    w._welcome.show_step("obs")
    assert u.btn_step_obs.text() == base
    assert u.rail_sep1.property("state") == ""


def test_hero_paints_tonight_moon(make_window):
    # The sky is ours (a painted widget), not a static image: it reads the
    # real phase from the same ephemeris the rest of the app uses.
    w = make_window(snapshot=None)
    info = w._welcome._sky.moon_info()
    assert info is not None
    assert 0.0 <= info["illum"] <= 1.0
    assert isinstance(info["waxing"], bool)


def test_night_strip_answers_with_a_site(make_window):
    # The hook of the redesign: typing a site makes the strip answer, and
    # it is pure local maths (no network, no cache).
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    u.spn_site_lat.setValue(40.41678)
    u.spn_site_lon.setValue(-3.70379)
    ws._fill_night()
    window = u.lbl_night_window.text()
    assert "→" in window and "h" in window
    assert "%" in u.lbl_night_moon.text()
    assert u.lbl_night_planets.text()
    assert u.btn_night_set.isHidden()


def test_night_strip_invites_you_when_there_is_no_site(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    u.spn_site_lat.setValue(0.0)
    u.spn_site_lon.setValue(0.0)
    u.edt_site_mpc.setText("")
    ws._fill_night()
    assert u.lbl_night_window.text()
    assert not u.btn_night_set.isHidden()


def test_kind_cards_and_count(make_window):
    from PySide6.QtWidgets import QFrame
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    cards = [c for c in u.kinds_container.findChildren(QFrame)
             if c.objectName() == "kindCard"]
    assert len(cards) == len(ws._boxes) == 8
    total = len(ws._boxes)
    ws._set_all(False)
    assert u.lbl_kinds_count.text().startswith("0 ")
    ws._set_all(True)
    assert u.lbl_kinds_count.text().startswith(f"{total} ")


def test_kinds_continue_refuses_an_empty_set(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    ws.show_step("kinds")
    ws._set_all(False)
    ws._kinds_next()
    assert ws.ui.setup_stack.currentIndex() == 1      # still on targets
    ws._set_all(True)
    ws._kinds_next()
    assert ws.ui.setup_stack.currentIndex() == 2


def test_animations_follow_the_preference(make_window, monkeypatch):
    from nightscribe.config import config
    w = make_window(snapshot=None)
    ws = w._welcome
    real_get = config.get
    monkeypatch.setattr(
        config, "get",
        lambda k, d=None: False if k == "ui_animations" else real_get(k, d))
    ws.refresh_animations()
    assert ws._animations is False
    assert not ws._sky._timer.isActive()
    assert ws._sky._animations is False


def test_skip_goes_home(make_window):
    from nightscribe.gui.main_window import VIEW_HOME, VIEW_WELCOME
    w = make_window(snapshot=None)
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    w._welcome.skip.emit()
    assert w._shell_stack().currentIndex() == VIEW_HOME


def test_cta_swaps_when_there_are_projects(make_window):
    # Interfaz 1.5: with projects already created, "Create my FIRST project"
    # is a lie. The big button becomes the way back to them and starting
    # another one drops to the quiet link.
    from nightscribe.gui.main_window import VIEW_HOME
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    ws.set_context(has_projects=False)
    assert "first" in u.btn_create.text()
    assert u.btn_create.isEnabled() == ws._site_ok()
    ws.set_context(has_projects=True)
    assert "first" not in u.btn_create.text()
    assert u.btn_create.isEnabled()          # going back needs no site
    assert "My projects" in u.btn_create.text()
    assert "New project" in u.btn_skip.text()
    # and the big button really goes Home
    u.btn_create.click()
    assert w._shell_stack().currentIndex() == VIEW_HOME


def test_quiet_link_creates_a_project_when_there_are_projects(make_window):
    from nightscribe.gui.main_window import VIEW_TONIGHT
    w = make_window(snapshot=None)
    ws = w._welcome
    ws.set_context(has_projects=True)
    seen = []
    ws.create_project.connect(lambda: seen.append(1))
    ws.ui.btn_skip.click()
    assert seen


def test_update_mode_explains_itself(make_window):
    # An update must not tell someone who has been using the app for months
    # to "set up your observatory in three steps": it says why the app
    # stopped here, marks what was already configured as done and leaves ONE
    # action, next to the report it closes.
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    ws.set_context(has_projects=True, update_version="9.9.9")
    ws.show_step("data")
    assert "9.9.9" in u.welcomeLead.text()
    assert "9.9.9" in u.lbl_data_badge.text()
    # isHidden(), not isVisible(): the fixture builds the window without
    # showing it, and isVisible() would be False for every widget
    assert not u.lbl_data_badge.isHidden()
    # the rail tells the truth: 1 and 2 were configured long ago
    assert u.btn_step_obs.text().startswith("✓")
    assert u.btn_step_kinds.text().startswith("✓")
    assert u.btn_step_obs.property("state") == "done"
    assert not u.btn_step_data.text().startswith("✓")
    # the report carries the only action, painted as the primary one
    assert u.btn_data_ack.property("primary") is True
    assert "projects" in u.btn_data_ack.text().lower()
    assert u.btn_create.isHidden() and u.btn_skip.isHidden()


def test_first_run_is_not_an_update(make_window):
    w = make_window(snapshot=None)
    u = w._welcome.ui
    w._welcome.set_context(has_projects=False, update_version=None)
    assert not u.lbl_data_badge.isVisible()
    assert u.btn_data_ack.property("primary") is False
    assert not u.btn_create.isHidden()
    assert not u.btn_step_obs.text().startswith("✓")


def test_the_data_report_rows_are_not_stretched(make_window):
    # The report used to spread the panel's spare height across its rows: a
    # one-line sentence ended up in a 72 px box and the whole page looked
    # broken. The rows keep their natural height and the slack goes below.
    from PySide6.QtWidgets import QApplication
    w = make_window(snapshot=None)
    ws = w._welcome
    ws.show_step("data")
    u = ws.ui
    ws.resize(1200, 800)
    QApplication.processEvents()
    u.dataBoxLayout.activate()
    lay = u.dataBoxLayout
    assert lay.count() > 1
    assert lay.stretch(lay.count() - 1) == 1        # the stretch is last
    rows = 0
    for i in range(lay.count() - 1):
        item = lay.itemAt(i)
        assert item.widget() is not None
        rows += item.widget().height()
    # the rows keep their natural height and the slack sits BELOW them
    # instead of being spread across the paragraph
    assert rows < u.data_container.height() - 20


def test_the_map_and_the_fields_are_wired_both_ways(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    # fields -> map
    u.spn_site_lat.setValue(12.5)
    u.spn_site_lon.setValue(-40.25)
    assert ws._map.site() == (12.5, -40.25)
    # map -> fields
    ws._map.picked.emit(-8.75, 20.5)
    ws._map_picked(-8.75, 20.5)
    assert u.spn_site_lat.value() == -8.75
    assert u.spn_site_lon.value() == 20.5


def test_the_map_names_the_point_it_was_given(make_window):
    # A clicked point has no name, so the map borrows the nearest city's;
    # it is written every time, like the MPC resolve.
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    u.edt_site_name.setText("mi casita")
    ws._map_picked(40.41678, -3.70379)          # Madrid
    assert u.edt_site_name.text() == "Madrid, Spain"
    assert u.spn_site_lat.value() == 40.41678
    # mid ocean: no city within reach, so the coordinates are written out
    ws._map_picked(0.0, -30.0)
    assert "N" in u.edt_site_name.text()
    assert "W" in u.edt_site_name.text()


def test_detect_button_spans_the_form_column(make_window):
    # It is a direct child of the column, so it stretches to the column's
    # full width instead of sitting at its natural ~150 px. The fields are
    # narrower than that (their labels take the left part of each row), so
    # the button is the widest control in the column, not a copy of one.
    from PySide6.QtWidgets import QApplication
    w = make_window(snapshot=None)
    u = w._welcome.ui
    w.show()
    QApplication.processEvents()
    assert abs(u.btn_detect.width() - u.obsFormHost.width()) <= 2
    assert u.btn_detect.width() > u.spn_site_lat.width()
    w.close()


def test_settings_map_button_copies_the_point(make_window, monkeypatch):
    # Settings opens the map as a dialog and copies the chosen point into
    # its own latitude/longitude fields.
    from PySide6.QtWidgets import QDialog
    from nightscribe.gui import site_map_dialog as smd
    from nightscribe.gui.ui_loader import load_ui
    monkeypatch.setattr(smd.SiteMapDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(smd.SiteMapDialog, "chosen",
                        lambda self: (12.5, -40.25))
    w = make_window(snapshot=None)
    dlg = load_ui("settings_dialog")
    w._map_pick_into(dlg)
    assert dlg.spn_lat.value() == 12.5
    assert dlg.spn_lon.value() == -40.25
    dlg.deleteLater()


def test_the_map_shows_no_marker_without_a_site(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    ws.ui.spn_site_lat.setValue(0.0)
    ws.ui.spn_site_lon.setValue(0.0)
    ws._site_to_map()
    assert not ws._map.has_site()


def test_skip_is_blocked_while_an_update_gates(make_window):
    # The Data report is read once per version: "explore first" cannot walk
    # around the gate.
    from nightscribe.gui.main_window import VIEW_WELCOME
    snap = {"integrity": "ok", "file": Path("nightscribe-before.db"),
            "size": 1024, "schema_version": 0}
    w = make_window(snapshot=snap)
    assert w._welcome_gate is True
    w._welcome.skip.emit()
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
