############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the observing journal dialog (ADR-036, J2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

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


@pytest.fixture
def db(tmp_path):
    from nightscribe.core.db import Database
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def seeded(db):
    from nightscribe.core import followup, project
    p = project.create(db, "variable", "R CrB", {"mag": 6.0})
    followup.create_session(db, p["id"], notes="12×180s V")
    project.add_file(db, p["id"], "/tmp/post_es.md", "post")
    db.mark_observed("T CrB", "variable", "2026-09-15")
    return db


def _texts(dlg):
    return [dlg.lst.item(i).text() for i in range(dlg.lst.count())]


def test_groups_by_night_with_headers(qapp, seeded):
    from nightscribe.gui.journal_dialog import JournalDialog
    dlg = JournalDialog(seeded)
    texts = _texts(dlg)
    assert any(t.startswith("— 20") and t.endswith(" —") for t in texts)
    assert any("R CrB — " in t for t in texts)
    assert any("T CrB — " in t for t in texts)
    dlg.deleteLater()


def test_kind_filter_narrows(qapp, seeded):
    from PySide6.QtCore import Qt
    from nightscribe.core import journal
    from nightscribe.gui.journal_dialog import JournalDialog
    dlg = JournalDialog(seeded)
    idx = dlg.cmb_kind.findData(journal.K_SESSION)
    dlg.cmb_kind.setCurrentIndex(idx)
    texts = _texts(dlg)
    assert texts and all("Visita" in t or t.startswith("— ")
                         for t in texts)
    assert not any("post" in t.lower() for t in texts)
    # back to all
    dlg.cmb_kind.setCurrentIndex(dlg.cmb_kind.findData(None))
    assert any("post" in t.lower() for t in _texts(dlg))
    dlg.deleteLater()


def test_search_narrows(qapp, seeded):
    from nightscribe.gui.journal_dialog import JournalDialog
    dlg = JournalDialog(seeded)
    dlg.edt_search.setText("t crb")
    texts = _texts(dlg)
    assert texts and all("T CrB" in t or t.startswith("— ") for t in texts)
    assert not any("R CrB" in t for t in texts)
    dlg.deleteLater()


def test_empty_state(qapp, db):
    from nightscribe.gui.journal_dialog import JournalDialog
    dlg = JournalDialog(db)
    assert dlg.lst.count() == 1
    item = dlg.lst.item(0)
    assert not item.flags()          # not clickable
    dlg._entry_activated(item)       # must not raise
    dlg.deleteLater()


def test_activation_hands_over_name_and_project(qapp, seeded):
    from PySide6.QtCore import Qt
    from nightscribe.gui.journal_dialog import JournalDialog
    seen = []
    dlg = JournalDialog(seeded, on_open_object=lambda n, p:
                        seen.append((n, p)))
    item = next(dlg.lst.item(i) for i in range(dlg.lst.count())
                if (dlg.lst.item(i).data(Qt.UserRole + 1) or "")
                == "R CrB")
    dlg._entry_activated(item)
    assert seen and seen[0][0] == "R CrB" and seen[0][1] is not None
    dlg.deleteLater()


def test_cli_history_uses_the_journal(qapp, seeded, capsys,
                                      monkeypatch):
    from nightscribe import __main__ as cli
    monkeypatch.setattr(cli, "db", seeded)
    cli.cmd_history(args=None)
    out = capsys.readouterr().out
    assert "Noche / Night" in out and "R CrB" in out
