############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Settings dialog information architecture (ADR-071)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Settings dialog layout smoke tests (offscreen, ADR-071).

The dialog is a rail of six categories (Observatory / Equipment /
Observing / Measurement / Integrations / Interface) over a stack of
scrollable pages, with a search box and collapsible advanced groups. What
these tests lock in:

* the page order and the widgets that live on each page;
* the field table (`settings_spec.FIELDS`) covering every simple field and
  mapping to a real config key (the round-trip, one table both ways);
* the search filtering a row by its label or its help;
* the advanced groups opening collapsed;
* the help-below-field rule (ADR-028) on the reorganized pages.

No network, no full MainWindow: the tests load the exact .ui the settings
flow loads and read the tree.
"""

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


def _dlg():
    from nightscribe.gui.main_window import _load_ui
    return _load_ui("settings_dialog")


def _pages(dlg):
    # @return: the six page widgets, in rail order
    return [dlg.stk_pages.widget(i).widget()
            for i in range(dlg.stk_pages.count())]


def _page_names(dlg):
    return [p.objectName() for p in _pages(dlg)]


def _page_widgets(dlg, index):
    # @return: objectName of every widget on that page, recursively
    from PySide6.QtWidgets import QWidget
    page = _pages(dlg)[index]
    return {w.objectName() for w in page.findChildren(QWidget)
            if w.objectName()}


def _page_of_group(dlg, group_name):
    # @return: the page index that holds a group, or -1
    for i in range(dlg.stk_pages.count()):
        if group_name in _page_widgets(dlg, i):
            return i
    return -1


def test_pages_in_order(qapp):
    from nightscribe.gui import settings_spec, settings_view
    dlg = _dlg()
    assert _page_names(dlg) == [
        "page_observatory", "page_equipment", "page_observing",
        "page_measurement", "page_integrations", "page_interface"]
    # the rail mirrors the pages, one label each, and follows the stack
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    assert dlg.lst_categories.count() == 6
    assert dlg.stk_pages.count() == 6
    dlg.lst_categories.setCurrentRow(3)
    qapp.processEvents()
    assert dlg.stk_pages.currentIndex() == 3
    dlg.deleteLater()


def test_the_rail_is_icon_only_with_a_tooltip(qapp):
    # ADR-071: the rail carries an ICON per category instead of the text;
    # the name lives in the tooltip (and the accessible name), and every
    # icon has its dim/active pair on disk.
    from nightscribe.gui import settings_spec, settings_view, theme
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    rail = dlg.lst_categories
    assert rail.count() == len(settings_spec.CATEGORIES)
    for i, (_page, label, stem) in enumerate(settings_spec.CATEGORIES):
        item = rail.item(i)
        assert item.text() == "", "the rail must be icon-only"
        assert not item.icon().isNull(), f"{stem}: icon is missing"
        assert item.toolTip() == label, f"{stem}: the tooltip is the name"
        assert theme.asset(stem + ".svg").exists(), f"{stem}.svg missing"
        assert theme.asset(stem + "_on.svg").exists(), f"{stem}_on.svg missing"
    dlg.deleteLater()


def test_observatory_page(qapp):
    dlg = _dlg()
    names = _page_widgets(dlg, 0)
    for w in ("grp_site", "edt_mpc_code", "btn_resolve", "btn_map_pick",
              "edt_obs_name", "spn_lat", "spn_lon", "spn_height",
              "edt_aavso_code"):
        assert w in names, f"{w} expected on the Observatory page"
    dlg.deleteLater()


def test_equipment_page_holds_the_unified_camera(qapp):
    # The camera options used to live in three places (a plate-scale group,
    # a photometric-profile group and the aperture in Equipment). They are
    # one group now, led by the preset (ADR-071).
    dlg = _dlg()
    names = _page_widgets(dlg, 1)
    for w in ("grp_equip", "grp_camera", "cmb_cam_preset", "spn_pixel_um",
              "spn_focal_mm", "cmb_camera_type", "cmb_binning",
              "spn_cam_full_well", "spn_cam_linearity", "spn_cam_gain",
              "spn_cam_ron", "spn_cam_dark", "spn_cam_max_exp",
              "lbl_cam_ref", "spn_aperture", "spn_limit_mag"):
        assert w in names, f"{w} expected on the Equipment page"
    dlg.deleteLater()


def test_observing_page(qapp):
    dlg = _dlg()
    names = _page_widgets(dlg, 2)
    for w in ("grp_horizon", "edt_horizon_file", "btn_horizon_browse",
              "spn_horizon_margin", "spn_min_alt", "lbl_horizon_stats",
              "grp_kinds", "grp_transits", "chk_transit_scope_filter",
              "grp_moon", "chk_moon_enabled", "spn_moon_sep",
              "spn_moon_illum", "grp_session", "spn_overhead",
              "spn_sn_cadence", "spn_event_mag", "spn_extremum_days",
              "chk_aavso", "edt_vigils", "grp_storage", "edt_projects_root",
              "btn_projects_browse", "btn_projects_reset"):
        assert w in names, f"{w} expected on the Observing page"
    dlg.deleteLater()


def test_kinds_grid_includes_hads(qapp):
    # the enabled-kinds whitelist checkboxes follow the chk_kind_<kind>
    # naming convention; HADS is the seventh (ADR-034)
    dlg = _dlg()
    names = _page_widgets(dlg, 2)
    for k in ("neo", "sn", "comet", "pccp", "transit", "alert", "hads"):
        assert f"chk_kind_{k}" in names, f"chk_kind_{k} missing"
    assert dlg.chk_kind_hads.text() == "HADS variable stars"
    dlg.deleteLater()


def test_measurement_page(qapp):
    # photometry + calibration + astrometry + solver + Find_Orb + EXOTIC,
    # together: whoever measures should not jump three tabs (ADR-071)
    dlg = _dlg()
    names = _page_widgets(dlg, 3)
    for w in ("grp_photmethod", "chk_phot_matched", "grp_phot_adv",
              "grp_calibration", "cmb_master_kind", "btn_master_add",
              "tbl_masters", "btn_master_remove", "grp_astro_gate",
              "grp_astro_sweep", "grp_astro_check", "grp_findorb",
              "grp_solver", "cmb_solver", "edt_astap_path",
              "chk_solve_save", "grp_exotic", "edt_exotic_python",
              "grp_astro_adv", "grp_astro_work"):
        assert w in names, f"{w} expected on the Measurement page"
    dlg.deleteLater()


def test_integrations_page(qapp):
    dlg = _dlg()
    names = _page_widgets(dlg, 4)
    for w in ("grp_ccdciel", "edt_ccdciel_host", "spn_ccdciel_port",
              "chk_ccdciel_auto", "grp_apikeys", "edt_neofixer_key",
              "edt_astrometry_key", "edt_tns_bot", "edt_tns_bot_key",
              "edt_aavso_token", "grp_ai", "chk_ai_enabled",
              "cmb_ai_preset", "edt_ai_base_url", "edt_ai_api_key",
              "cmb_ai_model", "btn_ai_models", "spn_ai_temp", "btn_ai_test",
              "lbl_ai_status"):
        assert w in names, f"{w} expected on the Integrations page"
    dlg.deleteLater()


def test_interface_page_absorbs_development(qapp):
    # the Development tab is gone: its only switch (the UFE top bar) lives
    # with the Interface preferences now, as the guide already said
    dlg = _dlg()
    names = _page_widgets(dlg, 5)
    for w in ("grp_language", "cmb_language", "grp_motion", "chk_animations",
              "grp_ufe", "chk_ufe_bar_icons", "grp_chartann",
              "edt_observer", "edt_measurer", "edt_telescope",
              "edt_camera_model", "cmb_marker_style", "cmb_mark_color",
              "chk_annot_visible", "chk_chart_data", "chk_chart_boxes"):
        assert w in names, f"{w} expected on the Interface page"
    dlg.deleteLater()


def test_language_combo_populated_by_on_open_settings(qapp):
    dlg = _dlg()
    assert dlg.cmb_language is not None
    # the fixed 3-slot order (system=0, es=1, en=2) is asserted against
    # main_window.py below
    import inspect
    import re
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert re.search(r"\(\s*\"system\"\s*,\s*\"es\"\s*,\s*\"en\"\s*\)", src), \
        "on_open_settings must map the combo order to system/es/en"
    dlg.deleteLater()


def test_every_simple_field_maps_to_a_real_key(qapp):
    # The whole point of ADR-071: ONE table fills and saves. Every entry
    # must name a widget that exists and a key the config knows, or the
    # table is lying about something.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui import settings_spec
    from nightscribe.config import DEFAULTS
    dlg = _dlg()
    names = {w.objectName() for w in dlg.findChildren(QWidget)
             if w.objectName()}
    for f in settings_spec.FIELDS:
        assert f.widget in names, f"{f.widget} is not in the dialog"
        assert f.key in DEFAULTS, f"{f.key} has no default in config"
    dlg.deleteLater()


def test_the_field_table_round_trips(qapp):
    # set a value, save it through the table, load it back: a field that
    # is loaded but not saved (or the other way) would fail here
    from nightscribe.gui import settings_spec
    dlg = _dlg()

    class _Cfg:
        def __init__(self):
            self.d = {}

        def get(self, key, default=None):
            return self.d.get(key, default)

        def set(self, key, value):
            self.d[key] = value

    cfg = _Cfg()
    dlg.spn_limit_mag.setValue(17.5)
    dlg.chk_chart_data.setChecked(False)
    dlg.spn_cam_gain.setValue(0.0)          # 0 = unknown -> None
    dlg.edt_mpc_code.setText("z41")
    dlg.chk_ai_long_report.setChecked(True)  # the long report (ADR-075)
    settings_spec.save(dlg, cfg)
    assert cfg.d["limit_mag"] == 17.5
    assert cfg.d["chart_data"] is False
    assert cfg.d["ccd_gain"] is None
    assert cfg.d["mpc_code"] == "Z41"       # uppercased on save
    assert cfg.d["ai_long_report"] is True

    dlg2 = _dlg()
    settings_spec.load(dlg2, cfg)
    assert dlg2.spn_limit_mag.value() == 17.5
    assert dlg2.chk_chart_data.isChecked() is False
    assert dlg2.edt_mpc_code.text() == "Z41"
    assert dlg2.chk_ai_long_report.isChecked() is True
    dlg.deleteLater()
    dlg2.deleteLater()


def test_the_search_filters_by_label_and_help(qapp):
    from nightscribe.gui import settings_spec, settings_view
    from PySide6.QtWidgets import QLabel
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    for name in settings_spec.ADVANCED_GROUPS:
        settings_view.make_collapsible(getattr(dlg, name))
    settings_view.wire_search(dlg, "none")
    note = dlg.findChild(QLabel, "lbl_no_results")
    # a hit: the row stays and the quiet note is away
    dlg.edt_search.setText("limiting magnitude")
    qapp.processEvents()
    assert note.isHidden()
    assert dlg.spn_limit_mag.isVisibleTo(dlg)
    # a miss: the quiet note appears
    dlg.edt_search.setText("zzzznotfound")
    qapp.processEvents()
    assert not note.isHidden()
    # cleared: everything back
    dlg.edt_search.setText("")
    qapp.processEvents()
    assert note.isHidden()
    assert dlg.spn_limit_mag.isVisibleTo(dlg)
    dlg.deleteLater()


def test_advanced_groups_open_collapsed(qapp):
    from PySide6.QtWidgets import QToolButton
    from nightscribe.gui import settings_spec, settings_view
    dlg = _dlg()
    for name in settings_spec.ADVANCED_GROUPS:
        group = getattr(dlg, name)
        settings_view.make_collapsible(group, collapsed=True)
        header = group.findChild(QToolButton, name + "_header")
        assert header is not None and not header.isChecked(), \
            f"{name} should start collapsed"
    dlg.deleteLater()


def _is_descendant(widget, ancestor):
    node = widget
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent()
    return False


def test_help_labels_sit_below_their_field(qapp):
    # ADR-028 kept: every lblH_* lives in the SAME group as its field and
    # vertically AFTER it. Checked on the first page (visible geometry).
    from PySide6.QtWidgets import QWidget
    dlg = _dlg()
    dlg.resize(900, dlg.sizeHint().height())
    qapp.processEvents()
    pairs = [
        ("grp_site", "spn_lat", "lblH_lat"),
        ("grp_site", "spn_lon", "lblH_lon"),
        ("grp_site", "spn_height", "lblH_height"),
    ]
    widgets = {w.objectName(): w for w in dlg.findChildren(QWidget)
               if w.objectName()}
    for grp_name, field_name, help_name in pairs:
        grp = widgets.get(grp_name)
        field = widgets.get(field_name)
        help_lbl = widgets.get(help_name)
        assert _is_descendant(field, grp), f"{field_name} not inside {grp_name}"
        assert _is_descendant(help_lbl, grp), f"{help_name} not inside {grp_name}"
        fy = field.mapTo(dlg, field.pos()).y()
        hy = help_lbl.mapTo(dlg, help_lbl.pos()).y()
        assert hy >= fy, f"help {help_name} must sit below {field_name}"
    dlg.deleteLater()


def test_on_open_settings_runs_both_paths(qapp, monkeypatch):
    # the whole flow, on a stub host: the load path and the save path, so a
    # widget named in on_open_settings but missing from the .ui fails here
    from PySide6.QtWidgets import QComboBox, QDialog
    from nightscribe.gui import main_window as mw

    class _Cfg:
        def __init__(self):
            self.d = {"ui_animations": True}

        def get(self, key, default=None):
            return self.d.get(key, default)

        def set(self, key, value):
            self.d[key] = value

    def _win():
        win = mw.MainWindow.__new__(mw.MainWindow)
        win.tr = lambda s: s
        win._enabled_kinds = lambda: ["neo"]
        win._tonight_all = False
        win._welcome = None
        win.statusBar = lambda: type(
            "S", (), {"showMessage": lambda *a, **k: None})()
        win._settings_masters_init = lambda dlg: None
        win.tonight = type("T", (), {"cmb_filter": QComboBox()})()
        win._apply_kind_filter = lambda: None
        win._build_suggestion_grid = lambda: None
        return win

    for accepted in (False, True):
        dlg = _dlg()
        monkeypatch.setattr(
            dlg, "exec",
            (lambda: QDialog.Accepted) if accepted
            else (lambda: QDialog.Rejected))
        monkeypatch.setattr(mw, "_load_ui", lambda name, parent=None: dlg)
        cfg = _Cfg()
        monkeypatch.setattr(mw, "config", cfg)
        mw.MainWindow.on_open_settings(_win())
        if accepted:
            assert "limit_mag" in cfg.d
            assert "astrometry_snr_sigma" in cfg.d


def test_the_astrometry_settings_are_editable_at_last(qapp):
    # asked for 2026-10-06: "¿dónde puedo ajustar la SNR para el MPC?".
    # The fields live on the Measurement page now and the table maps each
    # one to its key (the dialog is modal, so the table is the proof).
    from nightscribe.gui import settings_spec
    dlg = _dlg()
    names = _page_widgets(dlg, 3)
    fields = {
        "spn_astro_gate": "astrometry_snr_sigma",
        "spn_astro_floor": "astrometry_submit_snr",
        "spn_astro_sweep_pct": "astrometry_sweep_pct",
        "spn_astro_steps": "astrometry_sweep_steps",
        "spn_astro_margin": "astrometry_cutout_margin_px",
        "chk_astro_check": "astrometry_check_enabled",
        "spn_astro_check_sigma": "astrometry_check_sigma",
        "spn_astro_check_floor": "astrometry_check_floor_arcsec",
        "spn_astro_check_window": "astrometry_check_window_days",
        "spn_astro_threads": "astrometry_threads",
    }
    table = {f.widget: f.key for f in settings_spec.FIELDS}
    for widget, key in fields.items():
        assert widget in names, widget
        assert hasattr(dlg, widget), widget
        assert table.get(widget) == key, f"{widget} must map to {key}"
    # the help of the floor says what the MPC recommends and what the app
    # ships: it is the whole reason the page exists
    help_text = dlg.lblH_astro_floor.text()
    assert "recommends 20" in help_text and "ships 10" in help_text
    dlg.deleteLater()


def test_the_ai_group_is_marked_experimental(qapp):
    # ADR-075: the language-model controls are presented as experimental
    dlg = _dlg()
    assert "experimental" in dlg.grp_ai.title().lower()
    assert "experimental" in dlg.lblH_ai_enabled.text().lower()
    dlg.deleteLater()


def test_ai_endpoint_preset_fills_the_address(qapp, monkeypatch):
    # ADR-075: choosing a known endpoint fills the base URL; the field table
    # maps the AI fields to their config keys. The endpoint is
    # OpenAI-compatible, so the local servers are just another entry.
    from PySide6.QtWidgets import QComboBox, QDialog
    from nightscribe.gui import main_window as mw, settings_spec

    class _Cfg:
        def __init__(self):
            self.d = {"ui_animations": True}

        def get(self, key, default=None):
            return self.d.get(key, default)

        def set(self, key, value):
            self.d[key] = value

    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s
    win._enabled_kinds = lambda: ["neo"]
    win._tonight_all = False
    win._welcome = None
    win.statusBar = lambda: type(
        "S", (), {"showMessage": lambda *a, **k: None})()
    win._settings_masters_init = lambda dlg: None
    win.tonight = type("T", (), {"cmb_filter": QComboBox()})()
    win._apply_kind_filter = lambda: None
    win._build_suggestion_grid = lambda: None

    dlg = _dlg()
    monkeypatch.setattr(dlg, "exec", lambda: QDialog.Rejected)
    monkeypatch.setattr(mw, "_load_ui", lambda name, parent=None: dlg)
    monkeypatch.setattr(mw, "config", _Cfg())
    mw.MainWindow.on_open_settings(win)

    table = {f.widget: f.key for f in settings_spec.FIELDS}
    assert table["chk_ai_enabled"] == "ai_enabled"
    assert table["edt_ai_base_url"] == "ai_base_url"
    assert table["cmb_ai_model"] == "ai_model"
    assert table["spn_ai_temp"] == "ai_temperature"

    # a known endpoint fills the address; "Custom…" (index 0) writes nothing
    idx = dlg.cmb_ai_preset.findData("http://localhost:11434/v1")
    assert idx > 0
    dlg.cmb_ai_preset.setCurrentIndex(idx)
    assert dlg.edt_ai_base_url.text() == "http://localhost:11434/v1"
    dlg.cmb_ai_preset.setCurrentIndex(0)
    assert dlg.edt_ai_base_url.text() == "http://localhost:11434/v1"
    dlg.deleteLater()


def test_ai_test_runs_off_the_gui_thread(qapp, monkeypatch):
    # the Test button must not call the endpoint on the GUI thread (ADR-075)
    from nightscribe.gui import main_window as mw, workers
    dlg = _dlg()
    dlg.edt_ai_base_url.setText("http://x/v1")
    dlg.cmb_ai_model.setCurrentText("m")
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg):
            seen["cfg"] = cfg

        done = type("D", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(workers, "LlmTestWorker", _FakeWorker)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s
    win._keep = lambda w: seen.__setitem__("kept", w)
    mw.MainWindow._ai_test(win, dlg)
    assert seen["started"] and seen["kept"]
    assert seen["cfg"].get("ai_base_url") == "http://x/v1"
    assert not dlg.btn_ai_test.isEnabled()      # disabled while testing
    dlg.deleteLater()


def test_ai_list_models_fills_the_combo(qapp, monkeypatch):
    # ADR-075: a local server answers with its exact model names, so nobody
    # types "qwen2.5:7b" from memory
    from nightscribe.gui import main_window as mw, workers
    dlg = _dlg()
    dlg.edt_ai_base_url.setText("http://localhost:11434/v1")
    dlg.cmb_ai_model.setCurrentText("kept-model")
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg):
            seen["cfg"] = cfg

        done = type("D", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            seen["started"] = True

    monkeypatch.setattr(workers, "LlmModelsWorker", _FakeWorker)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s
    win._keep = lambda w: None
    mw.MainWindow._ai_list_models(win, dlg)
    assert seen["started"]
    seen["fn"](["qwen2.5:7b", "llama3.2:latest"], "")
    items = [dlg.cmb_ai_model.itemText(i)
             for i in range(dlg.cmb_ai_model.count())]
    assert "qwen2.5:7b" in items
    assert dlg.cmb_ai_model.currentText() == "kept-model"   # typed name kept
    dlg.deleteLater()


def test_llm_models_worker_emits_on_success(qapp, monkeypatch):
    # the bug of 2026-10-09: the worker emitted only on ERROR, so a working
    # endpoint (a local Ollama) left the button at "Asking the endpoint…"
    # forever. This runs the REAL run() (no fake worker) with the source
    # monkeypatched, so the success emit is actually exercised.
    from nightscribe.gui import workers
    from nightscribe.core.sources import llm
    monkeypatch.setattr(llm, "list_models", lambda cfg: ["qwen3.6:latest"])
    w = workers.LlmModelsWorker(object())
    got = {}
    w.done.connect(lambda m, e: got.update(m=m, e=e))
    w.start()
    w.wait(3000)
    qapp.processEvents()
    assert got.get("m") == ["qwen3.6:latest"]
    assert got.get("e") == ""


def test_selecting_a_preset_loads_its_template(qapp, monkeypatch):
    # reported confusion (2026-10-09): picking another camera left the old
    # camera's full well / read noise / dark on screen. Choosing a camera now
    # loads its datasheet template over whatever was there.
    from PySide6.QtWidgets import QComboBox, QDialog
    from nightscribe.gui import main_window as mw

    class _Cfg:
        def __init__(self):
            self.d = {"ui_animations": True}

        def get(self, key, default=None):
            return self.d.get(key, default)

        def set(self, key, value):
            self.d[key] = value

    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s
    win._enabled_kinds = lambda: ["neo"]
    win._tonight_all = False
    win._welcome = None
    win.statusBar = lambda: type(
        "S", (), {"showMessage": lambda *a, **k: None})()
    win._settings_masters_init = lambda dlg: None
    win.tonight = type("T", (), {"cmb_filter": QComboBox()})()
    win._apply_kind_filter = lambda: None
    win._build_suggestion_grid = lambda: None

    dlg = _dlg()
    monkeypatch.setattr(dlg, "exec", lambda: QDialog.Rejected)
    monkeypatch.setattr(mw, "_load_ui", lambda name, parent=None: dlg)
    monkeypatch.setattr(mw, "config", _Cfg())
    mw.MainWindow.on_open_settings(win)

    def pick(key):
        dlg.cmb_cam_preset.setCurrentIndex(dlg.cmb_cam_preset.findData(key))

    pick("imx571")
    assert dlg.spn_pixel_um.value() == 3.76
    assert dlg.spn_cam_full_well.value() == 50000.0
    assert dlg.spn_cam_ron.value() == 1.0
    pick("imx294")
    # the WHOLE template moves, not only the pixel size
    assert dlg.spn_pixel_um.value() == 4.63
    assert dlg.spn_cam_full_well.value() == 63700.0
    assert dlg.spn_cam_ron.value() == 1.2
    # a family header reads as a header (bold, uppercased), not as a camera
    c = dlg.cmb_cam_preset
    hidx = next(i for i in range(c.count())
                if not c.model().item(i).isEnabled())
    assert c.model().item(hidx).font().bold()
    assert c.itemText(hidx).isupper()
    dlg.deleteLater()
