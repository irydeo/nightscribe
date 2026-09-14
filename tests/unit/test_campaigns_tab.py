############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: campaigns tab (UX, UA.2)
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
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------- harness ----------------

@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a throw
    # away file so the campaigns tab never touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("campdb") / "t.db")
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
    # keep the tests hermetic: no auto-compute network worker on startup
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


def test_campaigns_tab_exists(window):
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import TAB_CAMPAIGNS
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 5
    assert tabs.widget(TAB_CAMPAIGNS) is window.campaigns


def test_campaign_list_shows_health(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB", group_name="obsSN")
    proj_mod.create(mw.db, "variable", "T CrB",
                    {"ra_deg": 239.9, "dec_deg": 25.9}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert any("Campaña T CrB" in t and "obsSN" in t for t in texts)
    assert any("1 target" in t or "1 objetivo" in t for t in texts)


def test_finished_campaign_is_dimmed(window):
    from PySide6.QtCore import Qt
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Vieja")
    camp_mod.finish(mw.db, cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == cid)
    assert "finished" in item.text() or "finalizada" in item.text()


def test_campaign_detail_shows_protocol_and_members(window):
    from PySide6.QtCore import Qt
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(
        mw.db, "Campaña WeSb 1", group_name="obsSN",
        goal="Catch the fade",
        protocol={"cadence_nights": 1, "filters": ["B", "V"],
                  "comp_stars": ["000-BB0-123"], "notes": "HJD report"},
        report_url="https://example.org/report")
    proj_mod.create(mw.db, "variable", "WeSb 1",
                    {"ra_deg": 15.2, "dec_deg": 55.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == cid:
            lst.setCurrentRow(i)
    w = window.campaigns
    assert w.lbl_cname.text() == "Campaña WeSb 1"
    assert "obsSN" in w.lbl_cmeta.text()
    assert "Catch the fade" in w.lbl_cgoal.text()
    assert "B, V" in w.lbl_protocol.text()
    assert "000-BB0-123" in w.lbl_protocol.text()
    assert "https://example.org/report" in w.lbl_urls.text()
    tbl = w.tbl_members
    assert tbl.rowCount() == 1
    assert tbl.item(0, 0).text() == "WeSb 1"
    assert "never" in tbl.item(0, 3).text() or \
        "visitar" in tbl.item(0, 3).text()


def test_empty_campaign_detail_is_clean(window):
    # clearSelection() alone does not reset currentItem() in QListWidget;
    # setCurrentRow(-1) is the Qt-idiomatic "no current selection".
    window.campaigns.lst_campaigns.setCurrentRow(-1)
    window.campaigns.lst_campaigns.clearSelection()
    window._campaign_selected()
    assert window.campaigns.tbl_members.rowCount() == 0
    assert window.campaigns.lbl_cname.text() != ""


def test_member_double_click_jumps_to_project(window):
    from PySide6.QtCore import Qt
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.main_window import TAB_PROJECTS
    cid = camp_mod.create(mw.db, "Campaña salto")
    p = proj_mod.create(mw.db, "variable", "R CrB",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == cid:
            lst.setCurrentRow(i)
    window._campaign_member_opened(0, 0)
    from PySide6.QtWidgets import QTabWidget
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.currentIndex() == TAB_PROJECTS
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]


def test_goto_campaigns_selects_the_campaign(window):
    from PySide6.QtCore import Qt
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.main_window import TAB_CAMPAIGNS
    cid = camp_mod.create(mw.db, "Campaña destino")
    window._goto_campaigns(cid)
    from PySide6.QtWidgets import QTabWidget
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.currentIndex() == TAB_CAMPAIGNS
    cur = window.campaigns.lst_campaigns.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == cid


def test_camp_detach_member_unlinks(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña quita")
    p = proj_mod.create(mw.db, "variable", "SS Cyg",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._goto_campaigns(cid)
    window._camp_detach_member(p["id"])
    assert proj_mod.get(mw.db, p["id"])["campaign_id"] is None


# --- UX-a UA.5: the tab's equivalents of the old manager tests -----------


def test_tab_lists_active_and_finished(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    camp_mod.create(mw.db, "Activa UA.5")
    cid = camp_mod.create(mw.db, "Vieja UA.5")
    camp_mod.finish(mw.db, cid)
    window._refresh_campaigns_tab()
    texts = [window.campaigns.lst_campaigns.item(i).text()
             for i in range(window.campaigns.lst_campaigns.count())]
    assert any(t.startswith("Activa UA.5") for t in texts)
    assert any("Vieja UA.5" in t and ("finalizada" in t or "finished" in t)
               for t in texts)


def test_tab_finish_and_reopen(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "FinRe UA.5")
    window._goto_campaigns(cid)
    window._camp_finish()
    assert camp_mod.get(mw.db, cid)["status"] == camp_mod.CAMPAIGN_FINISHED
    window._camp_reopen()
    assert camp_mod.get(mw.db, cid)["status"] == camp_mod.CAMPAIGN_ACTIVE


def test_tab_delete_keeps_projects(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    cid = camp_mod.create(mw.db, "Campaña X UA.5")
    proj_mod.create(mw.db, "variable", "T CrB UA.5",
                    {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._goto_campaigns(cid)
    window._camp_delete()
    assert camp_mod.get(mw.db, cid) is None
    p = proj_mod.list_projects(mw.db, campaign_id=None)
    assert any(pr["object_name"] == "T CrB UA.5" for pr in p)


def test_attach_without_candidates_informs(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    seen = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.setdefault("told", True))
    # The shared module DB still holds unlinked active projects from the
    # earlier tests (e.g. the detached member above); a non-empty candidate
    # list would open a real QInputDialog modal and block the run.
    from nightscribe.core import project as proj_mod
    for p in proj_mod.list_projects(mw.db, status="active"):
        if p.get("campaign_id") is None:
            proj_mod.delete(mw.db, p["id"])
    cid = camp_mod.create(mw.db, "Campaña sola UA.5")
    window._goto_campaigns(cid)
    window._camp_attach()
    assert seen.get("told")


def test_header_badge_is_a_link(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña enlace")
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._render_project_header(proj_mod.get(mw.db, p["id"]))
    text = window.projects.lbl_header.text()
    assert f"campaign://{cid}" in text and "Campaña enlace" in text


def test_cadence_chip_navigates_to_followup(window):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099zz", {"mag": 15.0})
    fu.create_session(mw.db, p["id"])
    # age the session beyond the cadence threshold
    old = 1_700_000_000
    mw.db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
                  (old, p["id"]))
    mw.db.commit()
    window._show_cadence_hints()
    chips = window.tonight.findChildren(QLabel, "ns_cadence_chip")
    assert chips, "no cadence chip was created"
    window._goto_project_followup(p["id"])
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]
    assert window.projects.tabs_steps.currentIndex() == 4
