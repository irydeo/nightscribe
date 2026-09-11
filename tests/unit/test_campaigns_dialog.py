############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: campaigns dialog (Track V, VC.4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen smoke tests for the campaign manager dialog (ADR-035, VC.4):
the list, and the finish / reopen buttons driving core/campaign.py.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import campaign            # noqa: E402
from nightscribe.core.db import Database         # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    # One QApplication for the whole module (copied from test_theme.py).
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_dialog_lists_active_and_finished(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    campaign.create(db, "Activa")
    cid = campaign.create(db, "Vieja")
    campaign.finish(db, cid)
    dlg = CampaignsDialog(db_obj=db)
    assert dlg.lst_active.count() == 1
    assert dlg.lst_finished.count() == 1
    assert dlg.lst_active.item(0).text().startswith("Activa")


def test_finish_and_reopen_from_the_buttons(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    campaign.create(db, "A")
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg.btn_finish.click()
    assert dlg.lst_active.count() == 0
    assert dlg.lst_finished.count() == 1
    dlg.lst_finished.setCurrentRow(0)
    dlg.btn_reopen.click()
    assert dlg.lst_active.count() == 1


def test_empty_dialog_buttons_disabled(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    dlg = CampaignsDialog(db_obj=db)
    assert not dlg.btn_finish.isEnabled()
    assert not dlg.btn_reopen.isEnabled()
