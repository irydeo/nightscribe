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


def test_save_without_name_warns(qapp, db, monkeypatch):
    # UX-e: the silent refusal becomes a warning (replaces
    # test_save_without_name_is_refused)
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.setdefault("warned", True))
    dlg = CampaignEditDialog(db_obj=db)
    dlg._save()
    assert seen.get("warned")
    assert campaign.list_campaigns(db) == []


def test_add_target_resolves_vsx_and_creates_project(qapp, db):
    # U0.5: resolution runs in a ResolveWorker; tests feed the payload
    # straight into _resolve_done
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    cid = campaign.create(db, "Campaña T CrB")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("T CrB")
    dlg._resolve_done({"vsx": {
        "name": "T CrB", "auid": "000-BBW-825", "ra_deg": 239.87567,
        "dec_deg": 25.92017, "var_type": "NR+ELL", "period_d": 227.5528,
        "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8, "max_band": "V",
        "min_band": "V", "spectral": "M3III+WD", "constellation": "CrB"},
        "simbad": None})
    assert dlg.edt_ra.text().startswith("239.875")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["kind"] == "variable" and p["object_name"] == "T CrB"
    assert p["context"]["variable"]["period_d"] == 227.5528


def test_add_target_manual_when_nothing_knows_it(qapp, db):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    cid = campaign.create(db, "Campaña WeSb 1")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("WeSb 1")
    dlg._resolve_done({"vsx": None, "simbad": None})
    assert "Not found" in dlg.lbl_resolved.text()
    dlg.edt_ra.setText("15.2254")
    dlg.edt_dec.setText("55.0667")
    dlg.edt_mag.setText("15.0")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["context"]["ra_deg"] == 15.2254
    assert p["context"]["mag"] == 15.0


def test_add_target_without_coordinates_warns(qapp, db, monkeypatch):
    # UX-e: replaces test_add_target_without_coordinates_is_refused
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.setdefault("warned", True))
    cid = campaign.create(db, "C")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("X")
    dlg._save()
    assert seen.get("warned")
    assert proj_mod.list_projects(db) == []


def test_detach_with_no_members_informs(qapp, db, monkeypatch):
    # UX-e: replaces test_detach_with_no_members_is_a_noop
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.setdefault("told", True))
    campaign.create(db, "C")
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg._detach_project()
    assert seen.get("told")


def test_delete_campaign_keeps_projects(qapp, db, monkeypatch):
    # U0.4: deleting a campaign removes only the link, projects survive.
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    cid = campaign.create(db, "Campaña X")
    proj_mod.create(db, "variable", "T CrB", {"ra_deg": 1.0, "dec_deg": 2.0},
                    campaign_id=cid)
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg.btn_delete.click()
    assert campaign.list_campaigns(db) == []
    p = proj_mod.list_projects(db)[0]
    assert p["campaign_id"] is None            # ON DELETE SET NULL


def test_finished_campaign_is_editable(qapp, db):
    # U0.4: Edit works on a finished campaign (no Reopen→Edit needed).
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    cid = campaign.create(db, "Vieja")
    campaign.finish(db, cid)
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_finished.setCurrentRow(0)
    assert dlg.btn_edit.isEnabled()
