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

"""Offscreen smoke tests for the campaign sub-dialogs (UX-a, supersedes
ADR-035 V-j): the create/edit form and the new-project resolution chain.
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


def test_new_project_resolves_vsx_and_creates_project(qapp, db):
    # U0.5: resolution runs in a ResolveWorker; tests feed the payload
    # straight into _resolve_done
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import NewProjectDialog
    cid = campaign.create(db, "Campaña T CrB")
    dlg = NewProjectDialog(campaign_id=cid, db_obj=db)
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


def test_new_project_manual_when_nothing_knows_it(qapp, db):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import NewProjectDialog
    cid = campaign.create(db, "Campaña WeSb 1")
    dlg = NewProjectDialog(campaign_id=cid, db_obj=db)
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


def test_new_project_without_coordinates_warns(qapp, db, monkeypatch):
    # UX-e: replaces test_add_target_without_coordinates_is_refused
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import NewProjectDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.setdefault("warned", True))
    cid = campaign.create(db, "C")
    dlg = NewProjectDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("X")
    dlg._save()
    assert seen.get("warned")
    assert proj_mod.list_projects(db) == []
