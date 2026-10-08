############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: comparison chart in the Follow-up tab
# (ADR-042, phase 3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the follow-up entry to the photometric sequence
(ADR-042):

  * the Follow-up tab of a photometric project shows the primary
    «Comparison chart…» button and the plain-language status line.

The chart itself, its worker and its picker live in the unified editor
since 2026-10-07 (ADR-044 rev.): the routing to the editor is covered in
test_ufe_integration.py, next to the rest of the UFE integration.

No network anywhere.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # the shared db singleton goes to a throwaway file (test_projects_hub
    # pattern), so project CRUD never touches the real database
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("seqdb") / "t.db")
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
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


VAR_CTX = {"ra_deg": 291.366, "dec_deg": 42.784, "mag": 13.5}


def _variable_project():
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    return project.create(dbmod.db, "variable", "V0001 Cyg",
                          dict(VAR_CTX))


def _open_followup(window, p):
    # Selects the project and opens its Follow-up tab (no list signals, no
    # object-panel worker: the page build only needs _current_project).
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("analysis")


def test_followup_shows_the_primary_button(window):
    p = _variable_project()
    _open_followup(window, p)
    from PySide6.QtWidgets import QPushButton
    buttons = window._tab_pages["analysis"].findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    assert any("Comparison chart" in b for b in labels)
    # the status line starts empty, in plain words
    lbl = window._project_widgets.get("fu_sequence")
    assert lbl is not None
    assert "No comparison sequence yet" in lbl.text()
