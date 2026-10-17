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

"""Settings dialog layout smoke tests (offscreen, ADR-071 and ADR-092).

The dialog is a rail of six named categories (Observatory / Equipment /
Observing / Measurement / Integrations / Interface) over a stack of
scrollable pages, with a search box and ONE "Advanced" door per page
behind which the expert groups live (ADR-092). What these tests lock in:

* the page order and the widgets that live on each page;
* the field table (`settings_spec.FIELDS`) covering every simple field and
  mapping to a real config key (the round-trip, one table both ways);
* the search filtering a row by its label or its help, and opening the
  door when the match lives behind it;
* the doors starting closed and handing themselves back to the observer
  when the search box is cleared;
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


def test_no_page_needs_more_width_than_the_dialog_has(qapp):
    # Measured 2026-10-17: the Measurement page's minimum was 767 px against
    # the 712 px viewport of the default 900 px dialog, so the page scrolled
    # sideways and the right-hand buttons of its rows (Find_Orb's Test and
    # Install…) sat off screen until the observer widened the window. The
    # expert groups COUNT: they hold the widest rows and they are folded away
    # by default, which is why the dialog's own sizeHint did not see them.
    from nightscribe.gui import settings_spec, settings_view
    from PySide6.QtWidgets import QScrollArea, QWidget
    dlg = _dlg()
    settings_view.make_advanced_doors(dlg, settings_spec.ADVANCED_GROUPS,
                                      lambda s: s)
    dlg.resize(max(900, dlg.sizeHint().width()),
               max(640, dlg.sizeHint().height()))
    dlg.show()
    qapp.processEvents()
    bad = []
    for i, page in enumerate(_pages(dlg)):
        door = page.findChild(QWidget, f"door_{page.objectName()}")
        if door is not None:
            door.set_open(True)
        dlg.stk_pages.setCurrentIndex(i)
        dlg.grab()                     # forces the layout of this page
        area = page.parent()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parent()
        room = area.viewport().width() if area is not None else 0
        need = page.minimumSizeHint().width()
        if need > room:
            bad.append(f"{page.objectName()}: needs {need} px, has {room}")
    dlg.deleteLater()
    assert not bad, ("una página de Ajustes pide más ancho del que tiene, así "
                     "que su contenido se corta por la derecha y los botones "
                     "de las filas quedan fuera de la ventana:\n  "
                     + "\n  ".join(bad))


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


def test_the_rail_shows_icon_and_name(qapp):
    # ADR-092: the rail carries the icon AND the name of each category
    # (ADR-071's icon-only rail had to be hovered to be learned). The name
    # is also the tooltip and the accessible name, and every icon keeps its
    # dim/active pair on disk.
    from nightscribe.gui import settings_spec, settings_view, theme
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    rail = dlg.lst_categories
    assert rail.count() == len(settings_spec.CATEGORIES)
    for i, (_page, label, stem) in enumerate(settings_spec.CATEGORIES):
        item = rail.item(i)
        assert item.text() == label, "the rail names every category"
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
              "edt_aavso_code",
              # ADR-083: the site's sky brightness and its two helpers
              "spn_sky_brightness", "btn_sky_lookup", "btn_sky_map",
              # the observer's own details are NOT visual: they build the
              # MPC report's header and the band, so they live here
              # (2026-10-11); ADR-092 gives them their own group, so the
              # page is two short boxes instead of one 18-row wall
              "grp_reports",
              "edt_observer", "edt_measurer", "edt_observer_email",
              "edt_telescope", "cmb_telescope_type", "spn_telescope_fratio",
              "edt_camera_model", "edt_mpc_comment"):
        assert w in names, f"{w} expected on the Observatory page"
    dlg.deleteLater()


def test_equipment_page_holds_the_unified_camera(qapp):
    # The camera options used to live in three places (a plate-scale group,
    # a photometric-profile group and the aperture in Equipment). ADR-071
    # unified them under the preset; ADR-092 splits the MEASURED profile
    # (the sensor physics the preset fills) into its own group, which lives
    # behind the page's Advanced door.
    dlg = _dlg()
    names = _page_widgets(dlg, 1)
    for w in ("grp_equip", "grp_camera", "cmb_cam_preset", "spn_pixel_um",
              "spn_focal_mm", "cmb_camera_type", "cmb_binning",
              "grp_camera_profile",
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
              "spn_moon_illum", "grp_session",
              "spn_sn_cadence", "spn_event_mag", "spn_extremum_days",
              "chk_aavso", "edt_vigils", "grp_storage", "edt_projects_root",
              "btn_projects_browse", "btn_projects_reset",
              # ADR-092: the follow run's guider handling is session
              # behaviour (the Capture step reads it), not a site fact
              "chk_follow_guide", "chk_follow_calibrate"):
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
              "grp_calibration", "btn_master_add", "btn_master_add_dir",
              "tbl_masters", "btn_master_remove", "chk_calib_vignette_model",
              "spn_calib_temp_tol", "grp_astro_gate",
              "grp_astro_sweep", "grp_astro_check", "grp_findorb",
              "grp_solver", "cmb_solver", "edt_astap_path",
              "chk_solve_save", "grp_exotic", "edt_exotic_python",
              "grp_astro_adv", "grp_astro_work"):
        assert w in names, f"{w} expected on the Measurement page"
    dlg.deleteLater()


def test_integrations_page(qapp):
    dlg = _dlg()
    names = _page_widgets(dlg, 4)
    for w in ("grp_obs_backend", "cmb_obs_backend",
              "grp_ccdciel", "edt_ccdciel_host", "spn_ccdciel_port",
              "chk_ccdciel_auto",
              "grp_nina", "edt_nina_host", "spn_nina_port", "chk_nina_auto",
              "grp_apikeys", "edt_neofixer_key",
              "edt_astrometry_key", "edt_lightpollution_key",
              "edt_tns_bot", "edt_tns_bot_key",
              "edt_aavso_token", "grp_ai", "chk_ai_enabled",
              "cmb_ai_preset", "edt_ai_base_url", "edt_ai_api_key",
              "cmb_ai_model", "btn_ai_models", "spn_ai_temp", "btn_ai_test",
              "lbl_ai_status"):
        assert w in names, f"{w} expected on the Integrations page"
    dlg.deleteLater()


def test_interface_page_absorbs_development(qapp):
    # the Development tab is gone: its only switch (the UFE top bar) lives
    # with the Interface preferences now, as the guide already said. Only the
    # VISUAL switches are here: the observer's own details moved to the
    # Observatory page (2026-10-11).
    dlg = _dlg()
    names = _page_widgets(dlg, 5)
    for w in ("grp_language", "cmb_language", "grp_motion", "chk_animations",
              "grp_ufe", "chk_ufe_bar_icons", "grp_chartann",
              "cmb_marker_style", "cmb_mark_color",
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


def test_integrations_show_only_the_selected_backend(qapp):
    # ADR-081: the Integrations page shows only the fields of the program
    # picked in the combo, and the search cannot bring the other one back.
    from nightscribe.gui import settings_spec, settings_view
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    # the combo carries the id as data and is filled in code (QUiLoader does
    # not read userData from a .ui)
    dlg.cmb_obs_backend.addItem("CCDciel", "ccdciel")
    dlg.cmb_obs_backend.addItem("NINA / PINS", "nina")
    apply_search = settings_view.wire_search(
        dlg, "none",
        eligible=settings_view.backend_gate(dlg, settings_spec.BACKEND_GROUPS))
    dlg.cmb_obs_backend.setCurrentIndex(
        dlg.cmb_obs_backend.findData("ccdciel"))
    apply_search()
    assert not dlg.grp_ccdciel.isHidden()
    assert dlg.grp_nina.isHidden()
    dlg.cmb_obs_backend.setCurrentIndex(dlg.cmb_obs_backend.findData("nina"))
    apply_search()
    assert not dlg.grp_nina.isHidden()
    assert dlg.grp_ccdciel.isHidden()
    # a query that matches the hidden backend does not reveal it
    dlg.edt_search.setText("host")
    qapp.processEvents()
    assert dlg.grp_ccdciel.isHidden()
    assert not dlg.grp_nina.isHidden()
    # clearing the box leaves the picked backend visible
    dlg.edt_search.setText("")
    qapp.processEvents()
    assert not dlg.grp_nina.isHidden()
    dlg.deleteLater()


def test_the_search_filters_by_label_and_help(qapp):
    from nightscribe.gui import settings_spec, settings_view
    from PySide6.QtWidgets import QLabel
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    settings_view.title_groups(dlg)
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


def test_every_group_wears_a_title_and_nothing_folds(qapp):
    # ADR-071 rev: a group shows its title in a bar and its content is ALWAYS
    # visible; there is no disclosure control.
    from PySide6.QtWidgets import QGroupBox, QLabel, QToolButton, QWidget
    from nightscribe.gui import settings_view
    dlg = _dlg()
    settings_view.title_groups(dlg)
    groups = [g for g in dlg.findChildren(QGroupBox)
              if g.layout() is not None and g.layout().count()]
    assert groups, "the dialog has groups"
    for group in groups:
        title = group.findChild(QLabel, group.objectName() + "_title")
        assert title is not None and title.text(), group.objectName()
        # nothing folds: no disclosure button and the content is shown
        assert group.findChild(QToolButton,
                               group.objectName() + "_header") is None
        content = group.findChild(QWidget, group.objectName() + "_content")
        assert content is not None and not content.isHidden(), \
            group.objectName()
    dlg.deleteLater()


def _is_descendant(widget, ancestor):
    node = widget
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent()
    return False


def _dlg_with_doors():
    # @return: (dlg, doors) with the full view treatment applied, the same
    #          order on_open_settings uses
    from nightscribe.gui import settings_spec, settings_view
    dlg = _dlg()
    settings_view.build_rail(dlg, settings_spec.CATEGORIES, lambda s: s)
    settings_view.title_groups(dlg)
    doors = settings_view.make_advanced_doors(
        dlg, settings_spec.ADVANCED_GROUPS, lambda s: s)
    return dlg, doors


def test_every_advanced_group_lives_behind_a_door(qapp):
    # ADR-092: nothing is removed; the expert groups sit behind the ONE
    # door of their page, closed by default. The declaration is walked
    # both ways: every named group exists and is behind a door, and no
    # door opens on its own.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui import settings_spec
    dlg, doors = _dlg_with_doors()
    assert set(doors) == settings_spec.ADVANCED_GROUPS
    widgets = {w.objectName(): w for w in dlg.findChildren(QWidget)
               if w.objectName()}
    for name in settings_spec.ADVANCED_GROUPS:
        group = widgets.get(name)
        assert group is not None, f"{name} is declared advanced but missing"
        door = doors[name]
        assert _is_descendant(group, door.content), \
            f"{name} is not inside its door"
        assert door.content.isHidden(), f"{name}'s door must start closed"
        assert door.bar.text().startswith("▸"), "a closed door points right"
    # the three pages that have a door, and only those
    pages = {door.parentWidget().objectName() for door in doors.values()}
    assert pages == {"page_equipment", "page_measurement",
                     "page_integrations"}
    dlg.deleteLater()


def test_the_search_opens_the_door_of_a_hit(qapp):
    # ADR-092: a match behind a door opens it (a search hit must be
    # visible, not folded away); clearing the box closes it again, because
    # the observer never asked for it.
    from nightscribe.gui import settings_spec, settings_view
    dlg, doors = _dlg_with_doors()
    settings_view.wire_search(dlg, "none", doors=doors)
    cam_door = doors["grp_camera_profile"]
    assert cam_door.content.isHidden()
    dlg.edt_search.setText("full well")
    qapp.processEvents()
    assert not cam_door.content.isHidden(), "a hit behind the door opens it"
    assert cam_door.bar.text().startswith("▾")
    # the rail jumps to the page that holds the hit
    assert dlg.stk_pages.currentIndex() == 1
    dlg.edt_search.setText("")
    qapp.processEvents()
    assert cam_door.content.isHidden(), "clearing hands the door back"
    dlg.deleteLater()


def test_the_door_keeps_the_observers_choice_over_a_search(qapp):
    # the search borrows the door; it never steals it: a door the observer
    # opened stays open after the box is cleared
    from nightscribe.gui import settings_view
    dlg, doors = _dlg_with_doors()
    settings_view.wire_search(dlg, "none", doors=doors)
    door = doors["grp_ai"]
    door.bar.click()                       # the observer opens it
    assert door.user_open and not door.content.isHidden()
    dlg.edt_search.setText("moon")
    qapp.processEvents()
    dlg.edt_search.setText("")
    qapp.processEvents()
    assert not door.content.isHidden(), "a user-opened door stays open"
    dlg.deleteLater()


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
    assert dlg.spn_cam_readout.value() == 1.5
    pick("imx294")
    # the WHOLE template moves, not only the pixel size
    assert dlg.spn_pixel_um.value() == 4.63
    assert dlg.spn_cam_full_well.value() == 63700.0
    assert dlg.spn_cam_ron.value() == 1.2
    # the readout+download (the ONE per-frame overhead) moves too
    assert dlg.spn_cam_readout.value() == 1.5
    pick("kaf16803")
    assert dlg.spn_cam_readout.value() == 8.0
    # a family header reads as a header (bold, uppercased), not as a camera
    c = dlg.cmb_cam_preset
    hidx = next(i for i in range(c.count())
                if not c.model().item(i).isEnabled())
    assert c.model().item(hidx).font().bold()
    assert c.itemText(hidx).isupper()
    dlg.deleteLater()


def test_the_gpu_status_names_the_card_the_backend_sees(qapp, monkeypatch):
    # The switch comes ON by default (ADR-089 rev), so "does my card work?"
    # is the first question an observer asks. The row answers it for the
    # SELECTED backend, and the answer follows the combo; a machine with no
    # card is not an error, it says the processor will do the work.
    from PySide6.QtWidgets import QComboBox, QDialog
    from nightscribe.core import gpu
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

    asked = []
    name = {"v": "Fake Card"}
    monkeypatch.setattr(
        gpu, "probe", lambda backend: asked.append(backend) or name["v"])
    dlg = _dlg()
    monkeypatch.setattr(dlg, "exec", lambda: QDialog.Rejected)
    monkeypatch.setattr(mw, "_load_ui", lambda name, parent=None: dlg)
    monkeypatch.setattr(mw, "config", _Cfg())
    mw.MainWindow.on_open_settings(win)

    # OpenCL is the default backend, and it is the one probed first
    assert dlg.cmb_astro_gpu_backend.currentData() == "opencl"
    assert asked and asked[-1] == "opencl"
    assert "Fake Card" in dlg.lbl_astro_gpu_status.text()
    # a machine with no card is not an error: the label says who does the work
    name["v"] = ""
    dlg.cmb_astro_gpu_backend.setCurrentIndex(
        dlg.cmb_astro_gpu_backend.findData("cuda"))
    qapp.processEvents()
    assert asked[-1] == "cuda"
    assert "processor" in dlg.lbl_astro_gpu_status.text().lower()
    dlg.deleteLater()
