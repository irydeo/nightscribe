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
