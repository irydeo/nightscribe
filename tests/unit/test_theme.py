############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - theme tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the global dark theme (ADR-026).

These tests build a throwaway QApplication on the offscreen platform, so
they run headless in CI and on a laptop alike. The shared fixture is local
to this file to avoid touching the app-global instance elsewhere.
"""

import os

import pytest


def _contrast(a, b):
    # WCAG contrast ratio (>=1) between two #rrggbb strings.
    from nightscribe.gui import theme
    la, lb = theme._lum(a), theme._lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture(scope="module")
def qapp():
    # One QApplication for the whole module — Qt allows exactly one per
    # process, so the scope must be module/session, not per-test.
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_kind_accent_colors_cover_all_kinds(qapp):
    from nightscribe.gui import theme
    expected = {"sn", "neo", "comet", "pccp", "transit", "alert"}
    assert expected == set(theme.KIND_COLORS), "KIND_COLORS lost a kind"
    assert expected == set(theme.KIND_LABELS), "KIND_LABELS lost a kind"
    for kind in expected:
        col = theme.KIND_COLORS[kind]
        assert col.startswith("#") and len(col) == 7, f"bad hex for {kind}"


def test_apply_theme_sets_dark_palette_and_fusion(qapp):
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QStyleFactory
    from nightscribe.gui import theme

    theme.apply_theme(qapp)

    # Fusion plugin is available (even if the proxy style loses its name).
    assert "Fusion" in QStyleFactory.keys(), "Fusion style plugin missing"

    pal = qapp.palette()
    window = pal.color(QPalette.Window)
    base = pal.color(QPalette.Base)
    text = pal.color(QPalette.WindowText)
    # Dark family: low luminance (< 60) for surfaces, bright for text.
    assert window.lightness() < 60, f"window too light: {window.name()}"
    assert base.lightness() < 60, f"base too light: {base.name()}"
    assert text.lightness() > 200, f"text too dark: {text.name()}"
    # Highlight is accent-tinted blue (not red, not grey).
    hl = pal.color(QPalette.Highlight)
    assert hl.blue() > hl.red(), f"highlight should be bluish: {hl.name()}"


def test_apply_theme_installs_stylesheet(qapp):
    from nightscribe.gui import theme

    theme.apply_theme(qapp)
    qss = qapp.styleSheet()
    assert "QToolTip" in qss, "global QSS should cover tooltips"
    assert "QHeaderView::section" in qss, "global QSS should style tables"
    assert "QTabBar::tab" in qss, "global QSS should style tabs"
    # And the stylesheet references the palette hex (sanity, no regressions)
    assert theme.C_BG in qss


def test_style_checkbox_indicator_is_visible_and_checked(qapp):
    # The Fusion frame was invisible on the dark palette (only size was set);
    # the indicator must draw an explicit edge and a checked accent + tick.
    from pathlib import Path
    from nightscribe.gui import theme

    theme.apply_theme(qapp)
    qss = qapp.styleSheet()
    assert "QCheckBox::indicator" in qss
    assert f"border: 1px solid {theme.C_EDGE}" in qss, \
        "indicator needs a visible outline (barely-there bug)"
    assert "::indicator:checked" in qss
    # The checked state must reference the bundled tick asset and it must exist.
    assert theme.CHECK_SVG in qss, "checked indicator should paint check.svg"
    assert Path(theme.CHECK_SVG).is_file(), "check.svg asset missing"
    # And the boundary must actually read against the input background.
    assert _contrast(theme.C_EDGE, theme.C_BASE) >= 1.5


def test_style_lists_read_as_containers(qapp):
    from nightscribe.gui import theme

    theme.apply_theme(qapp)
    qss = qapp.styleSheet()
    assert "QListView, QListWidget" in qss, "list views should be containers"
    assert f"border: 1px solid {theme.C_EDGE}" in qss, "lists need a visible edge"
    assert "::item:hover" in qss, "list items should highlight on hover"
    assert "::item:selected" in qss
    assert "QPlainTextEdit" in qss, "plain text edits should join the input chrome"


def test_apply_theme_is_idempotent(qapp):
    theme_a = __import__("nightscribe.gui.theme", fromlist=["theme"])
    qss_before = qapp.styleSheet()
    theme_a.apply_theme(qapp)
    assert qapp.styleSheet() == qss_before, "re-applying must not accumulate"
