############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the post panel in the Publish page (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The post panel now lives in the Publish step (ADR-045 redesign), built in
code inside the same cards as Capture. What must hold: it waits for a button
(it never generates on its own), it shows a busy bar while a worker runs, and
a failure is said in plain words without emptying the boxes."""

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


def _build(monkeypatch, configured=True, folder=None, long=False):
    # @return: (fake MainWindow, the built post panel)
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from nightscribe.gui import main_window as mw
    from nightscribe.core.sources import llm
    from nightscribe.config import config
    monkeypatch.setattr(llm, "is_configured", lambda cfg: configured)
    monkeypatch.setattr(llm, "is_enabled", lambda cfg: configured)
    monkeypatch.setitem(config._data, "ai_long_report", long)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s
    win._project_widgets = {}
    win._current_project = {"id": 1, "object_name": "SN 2026abc",
                            "kind": "sn", "context": {}, "root_dir": ""}
    win._tonight_all = []
    win._keep = lambda w: None
    win.statusBar = lambda: type(
        "S", (), {"showMessage": lambda *a, **k: None})()
    # the page layout must hang from a live widget, or Qt deletes the cards
    host = QWidget()
    win._host = host
    lay = QVBoxLayout(host)
    win._step_section = lambda key: lay
    p = win._current_project
    mw.MainWindow._build_publish_tab(win, p, "sn", {})
    post_w = win._project_widgets["post_panel"]
    if folder is not None:
        post_w.edt_folder.setText(str(folder))
    return win, post_w


def test_panel_has_the_post_controls(qapp, monkeypatch):
    _win, post_w = _build(monkeypatch)
    for name in ("btn_generate", "btn_ai_generate", "btn_ai_brief",
                 "txt_es", "txt_en", "txt_tweet", "btn_copy_es",
                 "btn_copy_en", "btn_copy_tweet", "edt_folder",
                 "btn_folder_browse", "lbl_ai_note", "lbl_files", "progress"):
        assert hasattr(post_w, name), f"{name} missing from the panel"
    # the page starts empty: no draft has been built yet
    assert post_w.txt_es.toPlainText() == ""
    assert post_w.progress.isHidden()


def test_no_ai_controls_without_an_endpoint(qapp, monkeypatch):
    _win, post_w = _build(monkeypatch, configured=False)
    assert not post_w.btn_ai_generate.isEnabled()
    assert not post_w.btn_ai_brief.isEnabled()
    assert "template" in post_w.lbl_ai_note.text().lower()


def test_generate_sets_busy_and_starts_the_worker(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch)
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg, name, fallback_target=None):
            seen["name"] = name

        finished = type("F", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(mw, "PostWorker", _FakeWorker)
    mw.MainWindow._post_generate(win, post_w, "SN 2026abc")
    assert seen["started"]
    assert not post_w.progress.isHidden()               # the busy bar is on
    assert not post_w.btn_generate.isEnabled()
    post_w.progress.setVisible(False)


def test_ai_done_fills_the_boxes_and_clears_busy(qapp, monkeypatch, tmp_path):
    from nightscribe.gui import main_window as mw
    from nightscribe.core import post as post_mod
    monkeypatch.setattr(post_mod, "save_outputs", lambda *a, **k: {})
    win, post_w = _build(monkeypatch, folder=tmp_path)
    win._current_project = None          # no project: nothing to register
    post_w.progress.setVisible(True)
    mw.MainWindow._post_ai_done(
        win, post_w, "SN 2026abc", {"object": {}},
        {"es": "hola", "en": "hi", "tweet": "yo"}, {}, {}, "")
    assert post_w.txt_es.toPlainText() == "hola"
    assert post_w.txt_en.toPlainText() == "hi"
    assert post_w.txt_tweet.toPlainText() == "yo"
    assert post_w.progress.isHidden()
    assert "review" in post_w.lbl_ai_note.text().lower()


def test_ai_failure_is_said_and_keeps_the_text(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch)
    post_w.txt_es.setPlainText("my own draft")
    mw.MainWindow._post_ai_done(win, post_w, "SN 2026abc", {}, {}, {}, {},
                                "the model did not return a usable JSON post")
    assert "usable JSON" in post_w.lbl_ai_note.text()
    assert post_w.txt_es.toPlainText() == "my own draft"
    assert post_w.progress.isHidden()


def test_generate_ai_starts_a_worker_with_the_project(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch)
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg, project, db, enriched=None,
                     fallback_target=None, **kwargs):
            seen["project"] = project
            seen["long"] = kwargs.get("long")

        done = type("D", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(mw, "AiPostWorker", _FakeWorker)
    mw.MainWindow._post_generate_ai(win, post_w, "SN 2026abc")
    assert seen["started"] and seen["project"]["id"] == 1
    assert seen["long"] is False               # the setting is off by default
    assert not post_w.progress.isHidden()
    assert not post_w.btn_ai_generate.isEnabled()
    post_w.progress.setVisible(False)


def test_generate_ai_passes_the_long_setting(qapp, monkeypatch, tmp_path):
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch, long=True, folder=tmp_path)
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg, project, db, enriched=None,
                     fallback_target=None, **kwargs):
            seen["long"] = kwargs.get("long")
            seen["outdir"] = kwargs.get("outdir")
            seen["safe"] = kwargs.get("safe")

        done = type("D", (), {
            "connect": staticmethod(lambda fn: None)})

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(mw, "AiPostWorker", _FakeWorker)
    mw.MainWindow._post_generate_ai(win, post_w, "SN 2026abc")
    assert seen["started"] and seen["long"] is True
    assert seen["outdir"] and seen["safe"] == "SN_2026abc"
    post_w.progress.setVisible(False)


def test_generate_ai_does_nothing_when_the_ai_is_off(qapp, monkeypatch):
    # ADR-075: with the master switch off, the AI button must not reach the
    # worker even if it were somehow triggered
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch, configured=False)
    started = {"n": 0}

    class _FakeWorker:
        def __init__(self, *a, **k):
            started["n"] += 1

        done = type("D", (), {"connect": staticmethod(lambda fn: None)})

        def start(self):
            started["n"] += 1

    monkeypatch.setattr(mw, "AiPostWorker", _FakeWorker)
    mw.MainWindow._post_generate_ai(win, post_w, "SN 2026abc")
    assert started["n"] == 0


def test_post_done_hides_the_busy_bar(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    win, post_w = _build(monkeypatch)
    post_w.progress.setVisible(True)
    mw.MainWindow._post_done(win, post_w, "SN 2026abc", {}, None)
    assert post_w.progress.isHidden()
    assert "Not found" in post_w.lbl_files.text()


def test_the_ai_half_is_marked_experimental(qapp, monkeypatch):
    # ADR-075: the AI is opt-in and presented as experimental, so nobody
    # takes a model's draft for the app's own word
    _win, post_w = _build(monkeypatch)
    assert "experimental" in post_w.btn_ai_generate.text().lower()
    assert "experimental" in post_w.btn_ai_generate.toolTip().lower()
    assert "experimental" in post_w.btn_ai_brief.toolTip().lower()
    assert "experimental" in post_w.lbl_ai_note.text().lower()


def test_the_drafting_line_does_not_linger(qapp, monkeypatch, tmp_path):
    # The "drafting" line is written into lbl_files while the worker runs;
    # when the answer arrives it must go, or the page looks stuck forever
    from nightscribe.gui import main_window as mw
    from nightscribe.core import post as post_mod
    monkeypatch.setattr(post_mod, "save_outputs", lambda *a, **k: {})
    win, post_w = _build(monkeypatch, folder=tmp_path)
    win._current_project = None          # no project: nothing to register
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg, project, db, enriched=None,
                     fallback_target=None, **kwargs):
            pass

        done = type("D", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            pass

    monkeypatch.setattr(mw, "AiPostWorker", _FakeWorker)
    mw.MainWindow._post_generate_ai(win, post_w, "SN 2026abc")
    assert "drafting" in post_w.lbl_files.text().lower()
    mw.MainWindow._post_ai_done(win, post_w, "SN 2026abc", {"object": {}},
                                {"es": "a", "en": "b", "tweet": "c"}, {}, {}, "")
    # "Saved to: …" replaced the drafting line (it must not linger)
    assert "drafting" not in post_w.lbl_files.text().lower()


# ---------------- the long report (2026-10-09) ----------------

def test_the_long_report_card_follows_the_setting(qapp, monkeypatch):
    _win, post_w = _build(monkeypatch, long=False)
    assert post_w.report_card.isHidden()
    _win2, post_w2 = _build(monkeypatch, long=True)
    assert not post_w2.report_card.isHidden()


def test_ai_done_shows_and_saves_the_long_report(qapp, monkeypatch, tmp_path):
    from nightscribe.gui import main_window as mw
    from nightscribe.core import post as post_mod
    seen = {}

    def fake_save(post, outdir, base, **k):
        seen["post"] = post
        return {"es": tmp_path / "ES.md",
                "report_es": tmp_path / "rES.md"}

    monkeypatch.setattr(post_mod, "save_outputs", fake_save)
    win, post_w = _build(monkeypatch, long=True, folder=tmp_path)
    win._current_project = None          # no project: nothing to register
    rendered = {"report_es": "Informe largo", "report_en": "Long report",
                "es": "post", "en": "post", "tweet": "t"}
    mw.MainWindow._post_ai_done(win, post_w, "SN 2026abc", {"object": {}},
                                rendered, {}, {}, "")
    assert post_w.txt_report_es.toPlainText() == "Informe largo"
    assert post_w.txt_report_en.toPlainText() == "Long report"
    assert not post_w.report_card.isHidden()
    # the same text the observer sees is what gets written
    assert seen["post"]["report_es"] == "Informe largo"


def test_ai_done_registers_the_report_and_the_images(qapp, monkeypatch,
                                                     tmp_path):
    from nightscribe.gui import main_window as mw
    from nightscribe.core import post as post_mod
    from nightscribe.core import project as proj_mod
    import nightscribe.core.db as dbmod
    monkeypatch.setattr(post_mod, "save_outputs",
                        lambda post, outdir, base, **k: {
                            "es": tmp_path / "ES.md",
                            "report_es": tmp_path / "rES.md",
                            "chart_orbit": tmp_path / "orbit.png"})
    p = proj_mod.create(dbmod.db, "sn", "SN 2026abc", {"kind": "sn"})
    win, post_w = _build(monkeypatch, long=True, folder=tmp_path)
    win._current_project = proj_mod.get(dbmod.db, p["id"])
    win._populate_project_files = lambda pid: None
    rendered = {"report_es": "R", "report_en": "R", "es": "a", "en": "b",
                "tweet": "t"}
    charts = {"orbit": tmp_path / "orbit.png"}
    mw.MainWindow._post_ai_done(win, post_w, "SN 2026abc", {"object": {}},
                                rendered, charts, {}, "")
    kinds = [f["kind"] for f in proj_mod.list_files(dbmod.db, p["id"])]
    assert "post" in kinds and "chart" in kinds


def test_ai_done_keeps_the_short_post_when_the_report_failed(
        qapp, monkeypatch, tmp_path):
    # the long report failed but the short post came back: keep it and say
    # what failed, never a silent downgrade and never an empty panel
    from nightscribe.gui import main_window as mw
    from nightscribe.core import post as post_mod
    monkeypatch.setattr(post_mod, "save_outputs", lambda *a, **k: {})
    win, post_w = _build(monkeypatch, folder=tmp_path)
    win._current_project = None
    mw.MainWindow._post_ai_done(
        win, post_w, "SN 2026abc", {"object": {}},
        {"es": "post", "en": "post", "tweet": "t"}, {}, {},
        "the model did not return a usable JSON report")
    assert post_w.txt_es.toPlainText() == "post"
    assert "report failed" in post_w.lbl_ai_note.text().lower()
