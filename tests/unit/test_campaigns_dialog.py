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


# ---------------- VC.5: create / edit form ----------------


def test_new_campaign_via_form(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    dlg = CampaignEditDialog(db_obj=db)
    dlg.edt_name.setText("Campaña T CrB")
    dlg.edt_group.setText("obsSN")
    dlg.edt_filters.setText("B, V")
    dlg.edt_comps.setText("000-BB0-123, 000-BB0-124")
    assert dlg.spn_cadence.value() == 1          # V-l default
    dlg._save()
    c = campaign.list_campaigns(db)[0]
    assert c["name"] == "Campaña T CrB"
    assert c["protocol"]["filters"] == ["B", "V"]
    assert c["protocol"]["comp_stars"] == ["000-BB0-123", "000-BB0-124"]


def test_edit_campaign_via_form(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    cid = campaign.create(db, "A", protocol={"cadence_nights": 5})
    dlg = CampaignEditDialog(camp=campaign.get(db, cid), db_obj=db)
    assert dlg.spn_cadence.value() == 5
    dlg.edt_name.setText("A2")
    dlg._save()
    assert campaign.get(db, cid)["name"] == "A2"


def test_save_without_name_is_refused(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    dlg = CampaignEditDialog(db_obj=db)
    dlg._save()
    assert campaign.list_campaigns(db) == []
