############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Full target list smoke tests (UX v3 phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen smoke tests for the «Full target list» table (phase C).

Same spirit as test_tonight_rows.py: build a throwaway MainWindow without
the network worker, drive the table with fake targets and check the phase-C
contracts — row-level selection, podium tints on the top 3, bold name/score,
kind filter, and double-click → project.
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
      "window_end": "2026-08-25T04:10:00+02:00",
      "disc_date": "2026-08-14"}, 66.0,
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
    from nightscribe.gui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()


def _fill(window):
    # @args: window - MainWindow
    window._tonight_all = TARGETS
    window.tonight.cmb_filter.setCurrentIndex(0)  # "All"
    window.tonight.chk_show_observed.setChecked(True)
    window._fill_table()


def _names(window):
    # @return: the first-column text of every row, visual (top) order
    tbl = window.tonight.tbl_targets
    return [tbl.item(r, 0).text() for r in range(tbl.rowCount())]


def test_table_prepared_phase_c(window):
    # row selection, no row numbers, starts empty
    from PySide6.QtWidgets import QAbstractItemView
    tbl = window.tonight.tbl_targets
    assert tbl.selectionBehavior() == QAbstractItemView.SelectRows
    assert tbl.selectionMode() == QAbstractItemView.SingleSelection
    assert not tbl.verticalHeader().isVisible()


def test_fill_rows_and_score_order(window):
    _fill(window)
    tbl = window.tonight.tbl_targets
    assert tbl.rowCount() == len(TARGETS)
    # best first: the top row is the highest-scored target, whatever the
    # column sort order Qt settles on
    names = _names(window)
    assert names[0] == "SN 2026abc (NGC 1058)"
    assert "2026 QK (443089)" in names and "TRAPPIST-1 b" in names


def test_headers_translated(window):
    _fill(window)
    tbl = window.tonight.tbl_targets
    labels = [tbl.horizontalHeaderItem(c).text()
              for c in range(tbl.columnCount())]
    assert any("Object" in l or "Objeto" in l for l in labels)
    assert any("Score" in l for l in labels)


def test_top3_get_the_podium_tint(window):
    # the top 3 rows (score order) wear their kind color as background
    # tinge; the rest a near-invisible white tint
    _fill(window)
    tbl = window.tonight.tbl_targets
    from PySide6.QtGui import QColor
    names = _names(window)
    order = {"SN 2026abc (NGC 1058)": "#e5484d",
             "2026 QK (443089)": "#4484ef",
             "C/2024 A1 (ATLAS)": "#46a758"}
    top3_rows = [r for r in range(tbl.rowCount())
                 if _names_name(tbl, r) in order]
    assert len(top3_rows) == 3
    for r in range(tbl.rowCount()):
        color = tbl.item(r, 0).background().color()
        name = _names_name(tbl, r)
        if name in order:
            assert color.alpha() == 48, f"row {r} lost its podium tint"
            assert color.rgb() == QColor(order[name]).rgb()
        else:
            assert color.alpha() < 20, f"row {r} must keep a quiet tint"


def test_name_and_score_bold_others_plain(window):
    _fill(window)
    tbl = window.tonight.tbl_targets
    # Object is always column 0 (bold); Score sits wherever the column
    # config puts it — resolve it by header so new columns don't break it
    assert tbl.item(0, 0).font().bold()
    headers = [tbl.horizontalHeaderItem(c).text()
               for c in range(tbl.columnCount())]
    score = headers.index("Score")
    for c in range(1, score):
        assert not tbl.item(0, c).font().bold(), f"column {c} must stay plain"
    assert tbl.item(0, score).font().bold()


def test_name_foreground_is_the_kind_color(window):
    from PySide6.QtGui import QColor
    _fill(window)
    tbl = window.tonight.tbl_targets
    name_row = [r for r in range(tbl.rowCount())
                if tbl.item(r, 0).text() == "SN 2026abc (NGC 1058)"][0]
    fg = tbl.item(name_row, 0).foreground().color()
    assert fg.rgb() == QColor("#e5484d").rgb()
    # the why-tonight phrase lives in the row tooltip, as before
    assert "Descubierta" in tbl.item(name_row, 0).toolTip() or \
           "Discovered" in tbl.item(name_row, 0).toolTip()


def test_kind_filter_keeps_only_that_kind(window):
    _fill(window)
    window.tonight.cmb_filter.setCurrentIndex(1)  # NEOs
    tbl = window.tonight.tbl_targets
    assert tbl.rowCount() == 1
    assert _names(window)[0] == "2026 QK (443089)"
    # back to every kind
    window.tonight.cmb_filter.setCurrentIndex(0)
    window._fill_table()
    assert window.tonight.tbl_targets.rowCount() == len(TARGETS)


def test_covered_hidden_when_unchecked(window, monkeypatch):
    # ADR-036 J3: the checkbox filters objects already "covered" (a
    # project closed or a post written); the activity query is patched so
    # the real database is never read by this smoke test
    from nightscribe.core import project
    monkeypatch.setattr(project, "activity_for",
                        lambda db, name: {
                            "has_project": name == "com1",
                            "active": False, "covered": name == "com1",
                            "posted": False, "last_ts": None})
    window._tonight_all = TARGETS
    window.tonight.cmb_filter.setCurrentIndex(0)
    window.tonight.chk_show_observed.setChecked(False)
    window._fill_table()
    assert "C/2024 A1 (ATLAS)" not in _names(window)
    # showing covered brings it back, with its ✔ mark
    window.tonight.chk_show_observed.setChecked(True)
    window._fill_table()
    tbl = window.tonight.tbl_targets
    row = _names(window).index("C/2024 A1 (ATLAS)")
    assert any(tbl.item(row, c) and tbl.item(row, c).text() == "✔"
               for c in range(tbl.columnCount()))


def test_double_click_opens_explore_from_any_column(window, monkeypatch):
    # Phase E (single entry point): the double-click on any column of the
    # full list opens the Explore dialog for that target — the same
    # gesture and the same destination as the row's click or the card's
    # "Explore" shortcut.
    captured = []
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: captured.append(name))
    tbl = window.tonight.tbl_targets
    _fill(window)
    name_row = [r for r in range(tbl.rowCount())
                if tbl.item(r, 0).text() == "2026 QK (443089)"][0]
    for col in range(tbl.columnCount()):
        captured.clear()
        tbl.cellDoubleClicked.emit(name_row, col)
        assert len(captured) == 1, f"column {col} did not open Explore"
        assert captured[0] == "2026 QK (443089)"


def test_neo_view_has_discovered_column(window):
    # object-card plan, subplan 5: NEOs get the Discovered column too,
    # filled with the ISO date the planner resolved (SBDB/NEOfixer)
    _fill(window)
    window.tonight.cmb_filter.setCurrentIndex(1)  # NEOs
    try:
        tbl = window.tonight.tbl_targets
        labels = [tbl.horizontalHeaderItem(c).text()
                  for c in range(tbl.columnCount())]
        disc_col = next((i for i, l in enumerate(labels)
                         if l in ("Discovered", "Descubierta")), None)
        assert disc_col is not None, \
            f"no Discovered column in the NEO view: {labels}"
        assert tbl.item(0, disc_col).text() == "2026-08-14"
    finally:
        window.tonight.cmb_filter.setCurrentIndex(0)
        window._fill_table()


def test_all_view_discovered_normalizes_formats(window):
    # the default view shows the same date whatever format the source
    # used (Rochester "2026/08/30", SBDB "2004-Mar-15", ISO…)
    _fill(window)
    tbl = window.tonight.tbl_targets
    labels = [tbl.horizontalHeaderItem(c).text()
              for c in range(tbl.columnCount())]
    disc_col = next(i for i, l in enumerate(labels)
                    if l in ("Discovered", "Descubierta"))
    neo_row = next(r for r in range(tbl.rowCount())
                   if tbl.item(r, 0).text() == "2026 QK (443089)")
    assert tbl.item(neo_row, disc_col).text() == "2026-08-14"


def _names_name(tbl, r):
    # @return: the Object text of one row
    return tbl.item(r, 0).text()
