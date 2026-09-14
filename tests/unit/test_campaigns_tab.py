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
