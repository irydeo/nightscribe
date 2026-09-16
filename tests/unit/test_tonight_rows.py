############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Tonight rows smoke tests (UX v3 phase B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen smoke tests for the «Tonight» wide-row list (phase B).

Builds a throwaway MainWindow without the network worker and drives the
row construction with fake targets, so it runs headless in CI.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TARGETS = [
    ({"id": "sn1", "kind": "sn", "name": "SN 2026abc (NGC 1058)", "mag": 13.2,
      "max_alt": 70, "window_start": "2026-08-25T21:00:00+02:00",
      "window_end": "2026-08-25T23:30:00+02:00"}, 78.0,
     {"scientific": 22.0, "observability": 24.0, "urgency": 16.0, "hook": 16.0},
     {"es": "Descubierta hace 3 días.", "en": "Discovered 3 days ago."}),
    ({"id": "neo1", "kind": "neo", "name": "2026 QK (443089)", "mag": 21.5,
      "max_alt": 55, "window_start": "2026-08-25T00:30:00+02:00",
      "window_end": "2026-08-25T04:10:00+02:00"}, 66.0,
     {"scientific": 30.0, "observability": 18.0, "urgency": 10.0, "hook": 8.0},
     {"es": "En la página de confirmación del MPC.",
      "en": "On the MPC confirmation page."}),
    ({"id": "com1", "kind": "comet", "name": "C/2024 A1 (ATLAS)", "mag": 11.0,
      "max_alt": 40, "window_start": "2026-08-25T23:00:00+02:00",
      "window_end": "2026-08-26T03:00:00+02:00"}, 54.0,
     {"scientific": 18.0, "observability": 20.0, "urgency": 8.0, "hook": 8.0},
     {"es": "Cometa activo.", "en": "Active comet."}),
    ({"id": "tr1", "kind": "transit", "name": "TRAPPIST-1 b", "mag": 18.8,
      "max_alt": 25, "transit": {"star": "TRAPPIST-1 b", "depth_mmag": 40},
      "window_start": "2026-08-25T22:15:00+02:00",
      "window_end": "2026-08-25T23:45:00+02:00"}, 41.0,
     {"scientific": 18.0, "observability": 12.0, "urgency": 6.0, "hook": 5.0},
     {"es": "Un planeta eclipsa a su estrella.",
      "en": "A planet eclipses its star."}),
]


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui import theme
    theme.apply_theme(app)
    from nightscribe import config as cfgmod
    from nightscribe.gui.main_window import MainWindow
    # With a real (configured) config, __init__ schedules
    # QTimer.singleShot(on_compute_tonight) — a network worker that would
    # wipe the rows mid-test. Keep the suite headless by hiding the flag
    # while the window is built.
    real = cfgmod.config.is_configured
    cfgmod.config.is_configured = lambda: False
    w = MainWindow()
    cfgmod.config.is_configured = real
    yield w
    w.close()


def _rebuild(window):
    # Rebuild the list and let pending deleteLater() calls apply, so the
    # assertions see only the live widgets.
    window._tonight_all = TARGETS
    window._build_suggestion_grid()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


def test_rows_are_a_vertical_list(window):
    # Build the list with a small fake result set (no worker involved).
    _rebuild(window)
    rows = _all_rows(window)
    assert len(rows) == len(TARGETS), (
        f"expected {len(TARGETS)} rows, got {len(rows)}")
    # rows are the only direct widgets of the container layout (no grid)
    container = window.tonight.scroll_suggestions.findChild(
        _QWidget(), "suggestions_container")
    widgets = [w for w in _layout_widgets(container)]
    assert all(x.objectName() == "tonightrow" for x in widgets)


def test_row_shows_why_phrase_and_action(window):
    from PySide6.QtWidgets import QLabel, QPushButton
    _rebuild(window)
    rows = _all_rows(window)
    # the why-tonight phrase must be VISIBLE (not only in a tooltip now):
    # it is a label inside each live row
    def texts_of(row):
        return "\n".join(l.text() for l in row.findChildren(QLabel))
    all_texts = "\n".join(texts_of(r) for r in rows)
    assert ("Descubierta hace 3 días" in all_texts
            or "Discovered 3 days ago" in all_texts), \
        "why-tonight phrase not visible"
    # the kind chip and the name are visible in the best row
    assert "SN" in texts_of(rows[0])
    assert "SN 2026abc" in texts_of(rows[0])
    # every live row carries the Start/Continue action button
    for i, row in enumerate(rows):
        btns = row.findChildren(QPushButton)
        assert len(btns) == 1, f"row {i}: expected 1 button, got {len(btns)}"


def test_best_per_kind_rows_get_the_metallic_ring(window):
    # K3: the ring now lands on the best-of-each-VISIBLE-KIND, not on the
    # first three rows.  The fixture has one target per kind, so every row
    # wears the ring — and if two rows shared a kind, only the higher one
    # would keep it.
    _rebuild(window)
    rows = _all_rows(window)
    ring = "border: 1px solid #5a6478;"
    kinds = [t[0]["kind"] for t in TARGETS]
    assert len(set(kinds)) == len(kinds), "fixture must have one target per kind"
    for i, row in enumerate(rows):
        assert ring in row.styleSheet(), \
            f"row {i} (kind {kinds[i]}) lost its best-of-kind ring"


def test_loading_state_and_empty_state(window):
    from PySide6.QtWidgets import QLabel
    window._show_loading_state()
    container = window.tonight.scroll_suggestions.findChild(
        _QWidget(), "suggestions_container")
    assert container.layout() is not None
    skel = [w for w in _layout_widgets(container)
            if w.objectName() == "skelrow"]
    assert len(skel) == 6, "loading state should show 6 skeleton rows"
    window._show_empty_state("network")
    texts = "\n".join(l.text() for l in container.findChildren(QLabel))
    assert "No targets found" in texts
    # back to a normal list afterwards
    _rebuild(window)
    assert len(_all_rows(window)) == len(TARGETS)


def test_score_meter_is_present(window):
    from PySide6.QtWidgets import QLabel
    from nightscribe.gui.main_window import _ScoreBar
    _rebuild(window)
    rows = _all_rows(window)
    # each live row owns exactly one 4-segment score meter
    for i, row in enumerate(rows):
        bars = row.findChildren(_ScoreBar)
        assert len(bars) == 1, f"row {i}: expected 1 meter, got {len(bars)}"
    # the total 0-100 number is visible next to the meter
    texts = "\n".join(l.text() for r in rows for l in r.findChildren(QLabel))
    assert "78" in texts, "score total must be visible"
    assert "/100" in texts


def _all_rows(window):
    # @return: the row frames in visual (best-first) order
    container = window.tonight.scroll_suggestions.findChild(
        _QWidget(), "suggestions_container")
    return [w for w in _layout_widgets(container)
            if w.objectName() == "tonightrow"]


def _layout_widgets(container):
    # @return: the direct child widgets of the container layout
    layout = container.layout()
    out = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None:
            out.append(w)
    return out


def _QWidget():
    # Indirection so the module imports cleanly without PySide6 at parse time.
    from PySide6.QtWidgets import QWidget
    return QWidget


# ---------------- phase E: the smart card button ----------------

def test_card_button_explore_when_no_project(window, monkeypatch):
    # No active project for this object -> "Explore" button, wired to
    # _open_explore_dialog with the target's name.
    import nightscribe.gui.main_window as mw
    monkeypatch.setattr(mw.project, "list_projects",
                        lambda db, status=None: [])
    t = {"id": "snX", "name": "SN 2026abc", "kind": "sn"}
    btn = window._card_button(t)
    assert "Explore" in btn.text() or "Explorar" in btn.text(), \
        f"expected Explore label, got {btn.text()!r}"
    called = {}
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: called.update(n=name))
    btn.clicked.emit()
    assert called.get("n") == "SN 2026abc", called


def test_card_button_continue_when_project_exists(window, monkeypatch):
    # An active project already exists for this object -> "Continue"
    # button, wired to _start_or_continue (which resumes the project).
    import nightscribe.gui.main_window as mw
    monkeypatch.setattr(
        mw.project, "list_projects",
        lambda db, status=None:
            [{"id": 1, "object_name": "SN 2026abc", "status": "active"}])
    t = {"id": "snX", "name": "SN 2026abc", "kind": "sn"}
    btn = window._card_button(t)
    assert "Continue" in btn.text() or "Continuar" in btn.text(), \
        f"expected Continue label, got {btn.text()!r}"
    called = {"t": None}
    monkeypatch.setattr(window, "_start_or_continue",
                        lambda t2: called.__setitem__("t", t2))
    btn.clicked.emit()
    assert called["t"] is t


def test_card_button_continue_falls_back_to_create(window, monkeypatch):
    # The card's Continue still creates a fresh project when _goto_active_
    # project misses (e.g. the lookup returned a project by name but the
    # hub's selection could not match).
    import nightscribe.gui.main_window as mw
    monkeypatch.setattr(
        mw.project, "list_projects",
        lambda db, status=None:
            [{"id": 1, "object_name": "2026 QK (443089)", "status": "active"}])
    t = {"id": "443089", "name": "2026 QK (443089)", "kind": "neo"}
    btn = window._card_button(t)
    assert "Continue" in btn.text() or "Continuar" in btn.text(), \
        f"expected Continue label, got {btn.text()!r}"
    # pretend the hub selection misses and _create_project fires instead
    monkeypatch.setattr(window, "_goto_active_project",
                        lambda name, fallback=None: False)
    called = {}
    monkeypatch.setattr(window, "_create_project",
                        lambda tt: called.update(t=tt) or {"id": 99})
    btn.clicked.emit()
    assert called.get("t") is t


def test_variable_extremum_chip_max(window):
    # ADR-037 SC3: variable rows get the predicted-extremum countdown chip
    t = dict(TARGETS[0][0])
    t.update({"id": "var1", "kind": "variable", "name": "V Cyg",
              "mag": 9.4, "max_alt": 80,
              "variable": {"period_d": 150.0, "amp": 1.5,
                           "next_extremum": {"kind": "max", "mjd": 61044.0,
                                              "days": 2.4}}})
    window._tonight_all = [(t, 80.0, TARGETS[0][2], TARGETS[0][3])]
    window._build_suggestion_grid()
    from PySide6.QtWidgets import QLabel, QApplication
    QApplication.processEvents()
    rows = _all_rows(window)
    labels = [w.text() for w in rows[0].findChildren(QLabel)]
    assert any(l in ("maximum in 2.4 d", "máximo en 2.4 d") for l in labels), \
        f"extremum chip not found: {labels!r}"


def test_variable_extremum_chip_min_kind(window):
    # Eclipsing: the VSX epoch marks the minimum, so the chip reads "minimum"
    t = dict(TARGETS[0][0])
    t.update({"id": "var2", "kind": "variable", "name": "β Lyg",
              "mag": 4.4, "max_alt": 60,
              "variable": {"period_d": 12.9,
                           "next_extremum": {"kind": "min", "mjd": 61046.3,
                                              "days": 4.7}}})
    window._tonight_all = [(t, 72.0, TARGETS[0][2], TARGETS[0][3])]
    window._build_suggestion_grid()
    from PySide6.QtWidgets import QLabel, QApplication
    QApplication.processEvents()
    rows = _all_rows(window)
    labels = [w.text() for w in rows[0].findChildren(QLabel)]
    assert any(l in ("minimum in 4.7 d", "mínimo en 4.7 d") for l in labels), \
        f"extremum chip not found: {labels!r}"
