############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Settings: the declarative field table (ADR-071)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The one table that says which Settings widget carries which config key.

The dialog used to load and save its fields in two long hand-written lists
that lived side by side in `on_open_settings`, one per direction. Two lists
of the same thing drift: a field added to the load and forgotten in the save
looks right until the app restarts, and nothing tests it. Here there is ONE
list, `FIELDS`, and both directions are generated from it; the round-trip
test then holds every entry.

What is NOT here, on purpose: the combos whose items are filled at runtime
(the camera preset, the solver, the object marker, the language), the kinds
grid, the master table and the vigils list. Those carry a mapping of their
own (index or data), so they stay hand-wired in `on_open_settings` where the
mapping is visible.
"""

from collections import namedtuple

from PySide6.QtCore import QT_TRANSLATE_NOOP

# (widget objectName, config key, kind, flags)
# kind: str | text | int | float | bool | combo | combo_text
# flags: zero_none (0 means "unknown" -> None on save), upper (save uppercased)
Field = namedtuple("Field", "widget key kind zero_none upper")
Field.__new__.__defaults__ = (False, False)

# The rail, in the order of the QStackedWidget pages. Each entry is
# (page objectName, label, SVG stem): the rail is icon-only (ADR-071) and
# the label survives as the tooltip. The label is marked for translation
# with the MainWindow context (the class that calls tr() on it).
CATEGORIES = [
    ("page_observatory",
     QT_TRANSLATE_NOOP("MainWindow", "Observatory"), "settings_observatory"),
    ("page_equipment",
     QT_TRANSLATE_NOOP("MainWindow", "Equipment"), "settings_equipment"),
    ("page_observing",
     QT_TRANSLATE_NOOP("MainWindow", "Observing"), "settings_observing"),
    ("page_measurement",
     QT_TRANSLATE_NOOP("MainWindow", "Measurement"), "settings_measurement"),
    ("page_integrations",
     QT_TRANSLATE_NOOP("MainWindow", "Integrations"),
     "settings_integrations"),
    ("page_interface",
     QT_TRANSLATE_NOOP("MainWindow", "Interface"), "settings_interface"),
]

# Groups that are advanced: they carry a disclosure and open collapsed, so
# the common path is short and the rare knob is one click away.
ADVANCED_GROUPS = ("grp_phot_adv", "grp_astro_adv", "grp_astro_work")

FIELDS = [
    # --- Observatory ---------------------------------------------------
    Field("edt_mpc_code", "mpc_code", "str", upper=True),
    Field("edt_obs_name", "observatory_name", "str"),
    Field("spn_lat", "lat", "float"),
    Field("spn_lon", "lon", "float"),
    Field("spn_height", "height", "int"),
    Field("edt_aavso_code", "aavso_code", "str", upper=True),
    # --- Equipment -----------------------------------------------------
    Field("spn_aperture", "aperture_inches", "float"),
    Field("spn_limit_mag", "limit_mag", "float"),
    Field("spn_pixel_um", "pixel_um", "float"),
    Field("spn_focal_mm", "focal_mm", "float"),
    Field("spn_cam_full_well", "cam_full_well_e", "float", zero_none=True),
    Field("spn_cam_linearity", "cam_linearity_adu", "float", zero_none=True),
    Field("spn_cam_gain", "ccd_gain", "float", zero_none=True),
    Field("spn_cam_ron", "ccd_read_noise", "float", zero_none=True),
    Field("spn_cam_dark", "cam_dark_current_e_s", "float", zero_none=True),
    Field("spn_cam_max_exp", "cam_max_exposure_s", "float", zero_none=True),
    # --- Observing -----------------------------------------------------
    Field("edt_horizon_file", "horizon_file", "str"),
    Field("spn_horizon_margin", "horizon_margin_deg", "float"),
    Field("spn_min_alt", "min_alt", "float"),
    Field("chk_moon_enabled", "moon_limit_enabled", "bool"),
    Field("spn_moon_sep", "moon_min_sep_deg", "float"),
    Field("spn_moon_illum", "moon_max_illum", "float"),
    Field("chk_moons_all", "show_sat_moons_unobserved", "bool"),
    Field("spn_overhead", "overhead_s", "float"),
    Field("spn_sn_cadence", "sn_cadence_days", "int"),
    Field("spn_event_mag", "event_mag_threshold", "float"),
    Field("spn_extremum_days", "campaign_extremum_days", "int"),
    Field("chk_aavso", "aavso_feed", "bool"),
    Field("chk_transit_scope_filter", "transit_scope_filter", "bool"),
    Field("spn_best_pk", "best_per_kind_n", "int"),
    Field("edt_projects_root", "projects_root", "str"),
    # --- Measurement ---------------------------------------------------
    Field("chk_phot_matched", "phot_matched", "bool"),
    Field("spn_ccd_saturate", "ccd_saturate", "float", zero_none=True),
    Field("spn_flat_resid_mag", "flat_resid_mag", "float"),
    Field("spn_astro_gate", "astrometry_snr_sigma", "float"),
    Field("spn_astro_floor", "astrometry_submit_snr", "float"),
    Field("spn_astro_sweep_pct", "astrometry_sweep_pct", "float"),
    Field("spn_astro_steps", "astrometry_sweep_steps", "int"),
    Field("spn_astro_margin", "astrometry_cutout_margin_px", "int"),
    Field("chk_astro_check", "astrometry_check_enabled", "bool"),
    Field("spn_astro_check_sigma", "astrometry_check_sigma", "float"),
    Field("spn_astro_check_floor", "astrometry_check_floor_arcsec", "float"),
    Field("spn_astro_check_window", "astrometry_check_window_days", "int"),
    Field("spn_astro_threads", "astrometry_threads", "int"),
    Field("spn_astro_fallback_margin", "astrometry_fallback_margin_px",
          "int"),
    Field("spn_astro_disagree_arcsec", "astrometry_disagree_arcsec", "float"),
    Field("spn_astro_disagree_sigma", "astrometry_disagree_sigma", "float"),
    Field("edt_astap_path", "astap_path", "str"),
    Field("chk_solve_save", "solve_save", "bool"),
    Field("edt_findorb_path", "findorb_path", "str"),
    Field("edt_exotic_python", "exotic_python_path", "str"),
    Field("edt_exotic_install", "exotic_install_dir", "str"),
    # --- Integrations --------------------------------------------------
    Field("edt_ccdciel_host", "ccdciel_host", "str"),
    Field("spn_ccdciel_port", "ccdciel_port", "int"),
    Field("chk_ccdciel_auto", "ccdciel_auto_connect", "bool"),
    Field("edt_neofixer_key", "neofixer_key", "str"),
    Field("edt_astrometry_key", "astrometry_key", "str"),
    Field("edt_tns_bot", "tns_bot_name", "str"),
    Field("edt_tns_bot_key", "tns_bot_key", "str"),
    Field("edt_aavso_token", "aavso_api_token", "str"),
    # --- Interface -----------------------------------------------------
    Field("chk_animations", "ui_animations", "bool"),
    Field("chk_ufe_bar_icons", "ufe_bar_icons", "bool"),
    Field("edt_observer", "observer_name", "str"),
    Field("edt_measurer", "measurer_name", "str"),
    Field("edt_telescope", "telescope_desc", "str"),
    Field("edt_camera_model", "camera_model", "str"),
    Field("chk_annot_visible", "annot_visible", "bool"),
    Field("chk_chart_data", "chart_data", "bool"),
    Field("chk_chart_boxes", "chart_boxes", "bool"),
]


def load(dlg, cfg):
    # Fills every simple field from the config, one entry at a time.
    # @args: dlg - the loaded settings dialog, cfg - the config
    # @return: None
    for f in FIELDS:
        w = getattr(dlg, f.widget, None)
        if w is None:
            continue
        value = cfg.get(f.key)
        if f.kind in ("str", "text"):
            text = "" if value is None else str(value)
            if f.kind == "str":
                w.setText(text)
            else:
                w.setPlainText(text)
        elif f.kind == "int":
            w.setValue(int(value or 0))
        elif f.kind == "float":
            w.setValue(float(value or 0.0))
        elif f.kind == "bool":
            w.setChecked(bool(value))
        elif f.kind == "combo":
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
        elif f.kind == "combo_text":
            w.setCurrentText("" if value is None else str(value))


def save(dlg, cfg):
    # Writes every simple field back to the config, one entry at a time.
    # @args: dlg - the settings dialog, cfg - the config
    # @return: None
    for f in FIELDS:
        w = getattr(dlg, f.widget, None)
        if w is None:
            continue
        if f.kind == "str":
            value = w.text().strip()
            if f.upper:
                value = value.upper()
            cfg.set(f.key, value)
        elif f.kind == "text":
            cfg.set(f.key, w.toPlainText())
        elif f.kind == "int":
            cfg.set(f.key, w.value())
        elif f.kind == "float":
            value = w.value()
            cfg.set(f.key, None if (f.zero_none and not value) else value)
        elif f.kind == "bool":
            cfg.set(f.key, w.isChecked())
        elif f.kind == "combo":
            cfg.set(f.key, w.currentData())
        elif f.kind == "combo_text":
            cfg.set(f.key, w.currentText().strip())
