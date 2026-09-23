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


# Borrowed from test_projects_hub.py (UD.5): stand-in for the real
# ExploreWorker, so building a project page never spawns a QThread that
# touches the network. A worker still in flight at interpreter exit aborts
# the process locally and hung the Windows CI runner; deliver=False leaves
# the object card in its loading state, which these tests never inspect.
class FakeWorker:
    def __init__(self, payload, deliver=True):
        self.payload = payload
        self.deliver = deliver
        self._cbs = []

    class _finished:
        # just the connect / disconnect / emit surface the panel needs
        def __init__(self, w):
            self._w = w

        def connect(self, cb):
            self._w._cbs.append(cb)

        def disconnect(self, cb=None):
            if cb is None:
                self._w._cbs = []
            else:
                self._w._cbs = [c for c in self._w._cbs if c is not cb]

        def emit(self, p):
            for cb in list(self._w._cbs):
                cb(p)

    @property
    def finished(self):
        return self._finished(self)

    def start(self):
        if self.deliver:
            self._finished(self).emit(self.payload)


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
    # hermetic object card: the fake loader means no ExploreWorker QThread
    orig_loader = w._proj_panel_loader
    w._proj_panel_loader = (lambda name, fallback_target=None:
                            FakeWorker({}, deliver=False))
    yield w
    w._proj_panel_loader = orig_loader
    config.is_configured = orig_cfg
    w.close()


def test_campaigns_tab_exists(window):
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import TAB_CAMPAIGNS
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 3      # ADR-036 J0 + ADR-040: History and the
    # Sun & sky live in the Tools menu; ADR-043 removed the Observatory
    # tab (its controls moved into the Capture step of each project)
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
    assert any("1 projects" in t or "1 proyectos" in t for t in texts)


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
    text = window.projects.lbl_mast_camp.text()
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
    # ADR-041: the project hub is a lazy tab bar — "navigate to
    # Follow-up" builds the follow-up tab and activates it.
    assert "followup" in window._tab_pages, "the Follow-up tab was not built"
    assert not window._tab_pages["followup"].isHidden(), \
        "the Follow-up tab should be active"


# --- ADR-037 SC2: the signals console -------------------------------------


def _wipe_campaigns():
    # @return: nothing — the shared module DB accumulates campaigns across
    #          tests; the console reads the WHOLE database, so each test
    #          starts from a clean slate
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    for c in camp_mod.list_campaigns(mw.db):
        camp_mod.delete(mw.db, c["id"])


# ---------------- UX-PC (U5): war room -------------------------------

def test_campaign_actions_disabled_without_selection(window):
    # UX-PC (U5): with no campaign selected the header actions are
    # disabled (real enablement, no silent no-ops) and the detail teaches
    # the concept instead of showing a blank.
    _wipe_campaigns()
    window._refresh_campaigns_tab()
    window.campaigns.lst_campaigns.setCurrentRow(-1)
    window.campaigns.lst_campaigns.clearSelection()
    window._campaign_selected()
    w = window.campaigns
    for b in (w.btn_cedit, w.btn_cclose, w.btn_cmore):
        assert not b.isEnabled()
    assert "campaign" in w.lbl_cname.text().lower()
    assert len(w.lbl_cgoal.text()) > 40      # the guide text is there


def test_campaign_close_button_follows_state(window):
    # UX-PC (U5): one lifecycle button — "Close" when active, "Reopen"
    # when finished, enabled only with a selection.
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Estado U5")
    window._goto_campaigns(cid)
    btn = window.campaigns.btn_cclose
    assert btn.isEnabled()
    assert "Close" in btn.text() or "Cerrar" in btn.text()
    camp_mod.finish(mw.db, cid)
    window._refresh_campaigns_tab()
    assert "Reopen" in btn.text() or "Reabrir" in btn.text()
    window._camp_close_or_reopen()           # and it works
    assert camp_mod.get(mw.db, cid)["status"] == camp_mod.CAMPAIGN_ACTIVE


def test_campaign_cards_show_health(window):
    # UX-PC (U5): each campaign row is a health card — dots, coverage and
    # the next action in words — with the plain text kept on the item.
    from PySide6.QtCore import Qt
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    _wipe_campaigns()
    cid = camp_mod.create(mw.db, "Salud U5", group_name="obsSN")
    proj_mod.create(mw.db, "variable", "V U5",
                    {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == cid)
    row = lst.itemWidget(item)
    assert row is not None
    assert "Salud U5" in row.lbl_name.text()
    assert "obsSN" in row.lbl_group.text()
    assert "○" in row.lbl_dots.text()        # the member is due (never)
    assert "V U5" in row.lbl_next.text()     # the next action names it
    assert "Salud U5" in item.text()         # plain-text fallback intact


def test_cmore_menu_carries_the_secondary_actions(window):
    # UX-PC (U5): the ⋯ menu of the detail header holds the project-link
    # actions + delete.
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Menú U5")
    window._goto_campaigns(cid)
    window._rebuild_cmore_menu()
    texts = [a.text() for a in window.campaigns.btn_cmore.menu().actions()
             if a.text()]
    assert any("project" in t.lower() and "campaign" in t.lower()
               for t in texts)                      # New project in this…
    assert any("Attach" in t or "Vincular" in t for t in texts)
    assert any("Detach" in t or "Desvincular" in t for t in texts)
    assert any("Delete" in t or "Borrar" in t for t in texts)


def test_campaign_help_pops_with_plain_words(window, monkeypatch):
    # UX-PC (U5): the ⓘ help explains the concept with an example.
    from PySide6.QtWidgets import QMessageBox
    seen = {}
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: seen.update(args=a)))
    window.campaigns.btn_help.click()
    assert seen, "the ⓘ help did not open"
    text = str(seen["args"][-1])
    assert "T CrB" in text and "campaign" in text.lower()


def test_signals_console_empty_box(window):
    # U7: with no campaigns the coverage line is a GUIDE (it says what to
    # do, where), and the empty list is a calm STATE, not a dead one
    _wipe_campaigns()
    window._refresh_campaigns_tab()
    w = window.campaigns
    cov = w.lbl_cov.text()
    assert ("You follow no campaigns yet" in cov
            or "Aún no sigues ninguna campaña" in cov)
    assert w.lbl_cov.toolTip() == ""   # no numbers → nothing to explain
    assert w.lst_signals.count() == 1
    item = w.lst_signals.item(0)
    assert not item.flags()
    text = item.text()
    assert ("All calm" in text or "Todo en calma" in text)
    # empty-state rows carry no data: opening them is a no-op
    window._camp_signal_opened(item)


def test_signals_console_lists_event_with_coverage(window):
    import re
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtCore import Qt
    _wipe_campaigns()
    cid = camp_mod.create(mw.db, "Campaña señales")
    p = proj_mod.create(mw.db, "variable", "R Crl",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    fu.create_session(mw.db, p["id"])            # today: up to date
    for i, mag in enumerate((11.0, 11.0, 11.0, 11.0, 11.9)):
        fu.add_point(mw.db, p["id"], 61500.0 + i, "V", mag,
                     source="manual")
    window._refresh_campaigns_tab()
    w = window.campaigns
    assert w.lst_signals.count() == 1
    text = w.lst_signals.item(0).text()
    assert "0.9" in text and "V" in text
    # U7: the coverage line names WHAT it counts (numbers still N, M order)
    cov = w.lbl_cov.text()
    assert ("Up to date: " in cov or "Al día: " in cov)
    assert re.findall(r"\d+", cov) == ["1", "1"]
    tip = w.lbl_cov.toolTip()
    assert ("Measured within their campaign's cadence" in tip
            or "cadencia" in tip)
    # and the row points at the project, so a double-click can open it
    assert w.lst_signals.item(0).data(Qt.UserRole) == p["id"]


def test_signal_double_click_opens_project(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.main_window import TAB_PROJECTS
    _wipe_campaigns()
    cid = camp_mod.create(mw.db, "Campaña doble clic")
    p = proj_mod.create(mw.db, "variable", "R Crl",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    fu.create_session(mw.db, p["id"])
    for i, mag in enumerate((11.0, 11.0, 11.0, 11.0, 11.9)):
        fu.add_point(mw.db, p["id"], 61600.0 + i, "V", mag,
                     source="manual")
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_signals
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    window._camp_signal_opened(item)
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.currentIndex() == TAB_PROJECTS
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]


def test_signals_console_calm_with_campaigns(window):
    # U7: members exist but nothing is firing — the list says "calm"
    # (not "no signals"), and the coverage line explains what it counts
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    _wipe_campaigns()
    cid = camp_mod.create(mw.db, "Campaña calma")
    proj_mod.create(mw.db, "variable", "U Geminorum",
                    {"ra_deg": 84.0, "dec_deg": 15.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    w = window.campaigns
    cov = w.lbl_cov.text()
    assert ("Up to date: 0 of 1 campaign projects" in cov
            or "Al día: 0 de 1 proyectos de campaña" in cov)
    tip = w.lbl_cov.toolTip()
    assert ("Measured within their campaign's cadence" in tip
            or "cadencia" in tip)
    assert w.lst_signals.count() == 1
    item = w.lst_signals.item(0)
    assert not item.flags()
    text = item.text()
    assert ("All calm" in text or "Todo en calma" in text)


def test_signals_scope_line_and_help(window):
    # U7: the strip says its own scope in the .ui, and the ⓘ opens the
    # icon legend (⚡ ⏳ 👁) — the plain-language rule, self-explanatory
    from PySide6.QtWidgets import QMessageBox
    w = window.campaigns
    scope = w.lbl_signals_scope.text()
    assert ("Outbursts, brightness drops and predicted extrema" in scope
            or "Erupciones, caídas de brillo y máximos previstos" in scope)
    captured = {}
    orig = QMessageBox.information
    def spy(*args, **kw):
        captured["args"] = args
    QMessageBox.information = staticmethod(spy)
    try:
        w.btn_signals_help.click()
    finally:
        QMessageBox.information = orig
    title, body = captured["args"][1], captured["args"][2]
    assert ("What do the icons mean?" in title
            or "¿Qué significan los iconos?" in title)
    for icon in ("⚡", "⏳", "👁"):
        assert icon in body


def _seed_vigil_cache(db, mag=9.0):
    # Writes the short-TTL AAVSO community-photometry cache entry that the
    # bright vigil (T CrB, baseline 10.2 < BRIGHT_LIMIT) re-reads — the
    # console never touches the network (ADR-037 SC4a rev.)
    import json
    payload = {"count": 1, "results": [
        {"jd_dbl": 2461050.5, "magnitude": mag, "band": "V"}]}
    db.cache_put("aavso:phot:T CrB:30", "aavso",
                 json.dumps(payload).encode(), "application/json")


def _wipe_vigil_cache(db):
    db.execute("DELETE FROM http_cache WHERE key LIKE 'aavso:phot:%'", ())
    db.commit()


def test_signals_console_lists_cached_vigil(window):
    # ADR-037 SC4a: the console shows the vigil alerts the last Tonight
    # run left in the cache, after the campaign signals
    from PySide6.QtCore import Qt
    from nightscribe.gui import main_window as mw
    _wipe_campaigns()
    _seed_vigil_cache(mw.db)
    try:
        window._refresh_campaigns_tab()
        lst = window.campaigns.lst_signals
        texts = [lst.item(i).text() for i in range(lst.count())]
        assert any("👁 T CrB" in t for t in texts), texts
        row = next(lst.item(i) for i in range(lst.count())
                   if "👁 T CrB" in lst.item(i).text())
        assert row.data(Qt.UserRole) == "vigil"
        assert row.data(Qt.UserRole + 1) == "T CrB"
    finally:
        _wipe_vigil_cache(mw.db)


def test_vigil_signal_double_click_explores_without_project(window):
    # SC-g: no project for the star -> the vigil row opens Explore (the
    # module DB is shared and projects are never wiped, so the routing
    # methods are patched to keep the test order-independent)
    from nightscribe.gui import main_window as mw
    _wipe_campaigns()
    _seed_vigil_cache(mw.db)
    seen = []
    orig_exp, orig_goto = window._open_explore_dialog, \
        window._goto_active_project
    window._goto_active_project = lambda name, *a, **k: False
    window._open_explore_dialog = lambda name, *a, **k: seen.append(name)
    try:
        window._refresh_campaigns_tab()
        lst = window.campaigns.lst_signals
        row = next(lst.item(i) for i in range(lst.count())
                   if "👁 T CrB" in lst.item(i).text())
        window._camp_signal_opened(row)
        assert seen == ["T CrB"]
    finally:
        window._open_explore_dialog = orig_exp
        window._goto_active_project = orig_goto
        _wipe_vigil_cache(mw.db)


def test_vigil_signal_double_click_jumps_to_existing_project(window):
    # SC-g fusion: the vigil row of a star that IS a project jumps to it
    # and never falls through to Explore
    from nightscribe.gui import main_window as mw
    _wipe_campaigns()
    _seed_vigil_cache(mw.db)
    seen, explored = [], []
    orig_goto, orig_exp = window._goto_active_project, \
        window._open_explore_dialog
    window._goto_active_project = lambda name, *a, **k: seen.append(name) \
        or True
    window._open_explore_dialog = lambda name, *a, **k: \
        explored.append(name)
    try:
        window._refresh_campaigns_tab()
        lst = window.campaigns.lst_signals
        row = next(lst.item(i) for i in range(lst.count())
                   if "👁 T CrB" in lst.item(i).text())
        window._camp_signal_opened(row)
        assert seen == ["T CrB"] and explored == []
    finally:
        window._goto_active_project = orig_goto
        window._open_explore_dialog = orig_exp
        _wipe_vigil_cache(mw.db)
