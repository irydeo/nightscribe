############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Configuration module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
import logging

from . import paths

logger = logging.getLogger(__name__)

# Defaults: no site pre-filled. A fresh install goes through the wizard
# (ADR-042), which asks for the observatory and offers an optional
# geolocation hint. Existing configs keep whatever they already saved.
DEFAULTS = {
    "mpc_code": "",           # MPC observatory code; optional, may stay empty
    "observatory_name": "",
    "lat": 0.0,               # geodetic degrees (the wizard fills them)
    "lon": 0.0,               # degrees east (the wizard fills them)
    "height": 0,              # meters (the wizard fills it, best effort)
    "aperture_inches": 10.0,
    # hard gate: drop Tonight transits whose ExoClock minimum aperture is
    # above ours (ADR-015 consequence, object-card plan subplan 6)
    "transit_scope_filter": True,
    "limit_mag": 20.0,
    "min_alt": 30.0,        # degrees above horizon
    "language": "system",   # system | es | en
    "app_version": "",      # last app version the update wizard ran for
    "neofixer_key": "",     # optional, for reporting observing status
    "tns_bot_name": "",     # optional, to show TNS discovery images
    "tns_bot_key": "",
    "astrometry_key": "",   # optional, blind-solving unsolved FITS (blink)
    "solver": "auto",       # auto | astap | astrometry (ADR-051)
    "astap_path": "",       # local ASTAP binary; empty = look on PATH
    # ADR-051 rev: a solved plate is saved solved (the WCS cards go into
    # the FITS header, atomically). On by default; off keeps it in memory.
    "solve_save": True,
    # EXOTIC orchestration (series plan option A): the external Python <=3.10
    # used to run EXOTIC and the venv it lives in. Empty = autodetect.
    "exotic_python_path": "",
    "exotic_install_dir": "",
    # Container root for the projects: empty -> platformdirs data dir's
    # projects/ folder (the legacy location, see ADR-032)
    "projects_root": "",
    # UX v3 observing constraints (ADR-020 / ADR-021)
    "horizon_file": "",         # TheSkyX-style az/alt file; empty -> flat min_alt
    "horizon_margin_deg": 0.0,  # safety margin added on top of the horizon
    "pixel_um": 3.76,           # camera pixel size in microns
    "focal_mm": 2000.0,         # telescope focal length in mm
    "overhead_s": 15.0,         # per-frame readout/slew overhead in seconds
    # CCDciel JSON-RPC (ADR-030). Manual connect by default: the observatory
    # software is a human decision, not an automatic one.
    "ccdciel_host": "127.0.0.1",
    "ccdciel_port": 3277,
    "ccdciel_auto_connect": False,
    "moon_limit_enabled": True,   # soft Moon constraint (warning + score penalty)
    "moon_max_illum": 0.5,        # above this, faint targets get penalized
    "moon_min_sep_deg": 45.0,     # below this separation, targets get penalized
    # Sky calendar (ADR-040): by default hide Galilean transits when Jupiter
    # is not up; this checkbox re-enables them (dimmed, for completeness)
    "show_sat_moons_unobserved": False,
    # Tonight filter (WORKFLOWS 7quater): the enabled object kinds are the
    # whitelist shown in the header combo and in Settings; missing means all.
    "enabled_kinds": ["neo", "sn", "comet", "pccp", "transit", "alert",
                      "hads", "variable"],
    "tonight_kind": "",           # last-used header filter; "" = "All"
    "best_per_kind_n": 5,         # per-kind cap for the Tonight grid
    # SN follow-up (Track B, B11): cadence threshold in days — the Tonight
    # chip and the follow-up tab remind when a visit is due
    "sn_cadence_days": 3,
    # Track V (ADR-035, V-h): brightness-jump threshold for the variable
    # event advisor (dip/outburst vs. the median of the previous points)
    "event_mag_threshold": 0.5,
    # ADR-037 (SC1): "extremum imminent" window for campaign signals (days)
    "campaign_extremum_days": 3,
    # ADR-037 (SC4a): the vigil watch list — None means the curated
    # defaults in core/vigils.py (T CrB rise, R CrB drop); the settings
    # editor stores a list of dicts here
    "vigil_list": None,
    # ADR-037 (SC4b): show the AAVSO editorial channel (forum alerts +
    # active observing campaigns) in Tonight
    "aavso_feed": True,
    # ADR-037 (SC4a rev.): the AAVSO API token — the bright-star vigils
    # read the community photometry, and that endpoint answers 401
    # without it (empty = bright vigils stay silent, by design)
    "aavso_api_token": "",
    # EXOTIC handoff (Track D, subplan 4): camera identity and observer code
    # for the inits.json; height above is reused as "Obs. Elevation (meters)"
    # UFE photometry (phase H, PRECISION.es H4/D2): camera constants used
    # when the FITS header does not carry them; None means "unknown" (the
    # header wins when present). JSON-settable; the settings UI may grow
    # fields for them later.
    "ccd_gain": None,           # e-/ADU
    "ccd_read_noise": None,     # e-
    "ccd_saturate": None,       # ADU ceiling
    "flat_resid_mag": 0.007,    # flat-field residual floor in the error
    # Image calibration (ADR-061): where the master frames live, how far
    # the sensor temperature may drift and still accept a dark (+/-3 C by
    # default), and whether the calibrated frames are written to disk (off
    # by default: the stacking consumes them in memory).
    "calib_root": "",           # empty -> the data dir's calib/ folder
    "calib_temp_tol_c": 3.0,
    "calib_export": False,
    # P5: build a flat from the frames themselves for the filters the master
    # library has no flat for. Off by default: a real flat always wins, and
    # a pseudo-flat needs the sequence to be dithered.
    "calib_pseudo_flat": False,
    # The photometry METHOD a new plate starts with: the matched filter
    # (weigh each pixel by the star's shape) or the plain aperture. It is a
    # measured decision, not a taste (1.6x the signal-to-noise and no
    # faint-star bias against a real catalogue), so it starts ON. This key is
    # only the STARTING point: the recipe saved with a plate always wins, and
    # the switch the observer touches lives in the Photometry tab, beside the
    # measurement, with the numbers and the risks in its tooltip.
    "phot_matched": True,
    # The astrometry's own switch for ADR-061: calibrate the frames as they
    # are read (dark/bias and flat) before stacking them. THREE-STATE on
    # purpose (ADR-061 rev): None means nobody has chosen yet, and then the
    # library decides (on when it has a dark or a flat that matches the
    # visit, off when it has none); 0 and 1 are the observer's own word and
    # are never overridden.
    "calib_astrometry": None,
    # Track & stack (ADR-062): the detection gate and the submission bar
    # are DIFFERENT thresholds on purpose. The MPC recommends SNR >= 20 to
    # submit and forbids marginal detections, but that is a recommendation:
    # the author's Tycho submissions of 2025 UR ran at ~16 and were
    # accepted, so the default is 10 (editable) and the interface says how
    # far each observation is from the bar. The sweep walks a 5x5 grid
    # around the theoretical velocity, and the cutout carries a margin
    # over the object's own trail.
    "astrometry_snr_sigma": 3.5,
    "astrometry_submit_snr": 10.0,
    "astrometry_sweep_pct": 5.0,
    "astrometry_sweep_steps": 25,
    "astrometry_method": "sigma",
    # The warp's interpolation order (2026-10-07): 1 is the bilinear and the
    # default, because it makes the stack visibly cleaner at NO cost in depth
    # (measured on 2025 FG18: orders 1 and 3 tie at magnitude 18.20 against
    # 18.21 by injection and recovery, while the pixel noise differs by 29 %).
    # It is a knob for the eye, not for the limit. 3 or 5 give a sharper point
    # spread and a grainier image.
    "astrometry_warp_order": 1,
    "astrometry_cutout_margin_px": 64,
    # Extra margin added to the cutout when the ephemeris had to be
    # propagated LOCALLY (Horizons down): two-body and a coarse Earth can
    # put a close NEO a couple of arcminutes off, and the cutout has to
    # still contain it. The reported position is unaffected.
    "astrometry_fallback_margin_px": 300,
    "astrometry_full_frame_final": True,
    # Worker threads for the CPU-bound stages (register, warp, combine): 0 is
    # AUTOMATIC, computed from the cores the process may use and capped by the
    # memory one task needs (core/parallel.py). A positive value caps it by
    # hand for a machine that is busy with something else.
    "astrometry_threads": 0,
    "astrometry_disagree_arcsec": 0.5,
    "astrometry_disagree_sigma": 3.0,
    "astrometry_astcat": "Gaia2",
    # The check against other observers (ADR-062): Find_Orb is an external
    # tool the user installs (never bundled); the residual is normalised by
    # our own rms and the robust scatter of the others inside a window.
    "findorb_path": "",
    "findorb_run": False,
    "astrometry_check_enabled": True,
    "astrometry_check_sigma": 3.0,
    "astrometry_check_floor_arcsec": 1.0,
    "astrometry_check_window_days": 30,
    "mpc_obs_ttl_h": 6,
    # Camera profile (core/cameras.py presets): the sensor template and the
    # photometric limits the preset fills (all editable; the linearity and
    # the working max exposure are per gain and must be measured/set by the
    # user). regime: "short" (sCMOS, group many short frames) | "normal".
    "cam_preset": "",
    "cam_full_well_e": None,    # e-
    "cam_linearity_adu": None,  # ADU where linearity is lost (per gain)
    "cam_dark_current_e_s": None,   # e-/pixel/s at cam_dark_temp_c
    "cam_dark_temp_c": None,
    "cam_max_exposure_s": None,     # working max exposure (per gain)
    "cam_regime": "normal",
    # UFE (ADR-044): the unified editor is the only door to the FITS work
    # (Blink, comparison chart, annotated FITS). The switch that chose
    # between it and the classic dialogs retired with them (2026-10-07);
    # the top bar's look is the only UFE preference left.
    "ufe_bar_icons": True,
    # UFE top bar (ADR-044 rev, 2026-09-24): compact icons in place of the
    # text labels by default; off restores the full labels (the tooltips
    # never change). Solving and the marker-move button keep their text.
    "ufe_bar_icons": True,
    # CCD | CMOS | DSLR. Two consumers: the EXOTIC inits.json handoff (its
    # guide has CMOS entered as "CCD" plus a note) and the MPC report, whose
    # ADES "mode" is CCD or CMO and whose 80-column column 15 is "C"/"B".
    "camera_type": "CCD",
    "pixel_binning": "1x1",
    "aavso_code": "",           # AAVSO observer code; blank when none
    # Chart annotations (ADR-046): the identity stamped in the corner
    # boxes of the exported charts, and the two independent style
    # switches (the object marker's shape and the boxes layer)
    "observer_name": "",
    "measurer_name": "",      # empty -> falls back to observer_name
    "telescope_desc": "",     # free text, e.g. "0.43-m f/4.9 reflector"
    "camera_model": "",
    "marker_style": "ring",   # ring | cross (the object marker)
    # The object's marks in the editor: the full-frame crosshair (the object
    # mark), the cross the run measured with and the circle with the name.
    # `annot_visible` is whether that circle shows when a plate opens (the
    # editor's "A" toggle, live); `marker_color` is the colour of all three:
    # "kind" = the object type's own colour (theme.KIND_COLORS), "common" =
    # one colour for every mark (theme.C_OBJECT_MARK). ONE resolver reads it
    # (theme.mark_color), so the three cannot disagree.
    "annot_visible": False,
    "marker_color": "kind",
    "chart_boxes": False,     # metadata corner boxes on the OTHER charts
                              # (the blink GIF/MP4 and the finder chart);
                              # the UFE's plate band is chart_data
    "chart_data": True,       # what the plate's band says (ADR-046 rev.)
}


class Config:
    # Tiny persistent configuration on top of a JSON file in the user
    # config dir. Values are strings/numbers/bools, and lists of strings
    # (enabled_kinds).

    def __init__(self):
        self._file = paths.config_dir() / "nightscribe.json"
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        # Reads the config file if it exists, keeping defaults for missing keys
        try:
            with open(self._file, encoding="utf-8") as f:
                self._data.update(json.load(f))
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError) as err:
            logger.warning("Could not read config %s: %s", self._file, err)
        # HADS/Track V rollout: a stored whitelist equal to any previous
        # default gets the new kind(s) for free; a customised list is
        # never touched
        if self._data.get("enabled_kinds") in (
                ["neo", "sn", "comet", "pccp", "transit", "alert"],
                ["neo", "sn", "comet", "pccp", "transit", "alert",
                 "hads"]):
            self._data["enabled_kinds"] = list(DEFAULTS["enabled_kinds"])

    def save(self):
        # Writes the current configuration to disk
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as err:
            logger.error("Could not save config %s: %s", self._file, err)

    def get(self, key, default=None):
        # @args: key - setting name, default - value if missing
        # @return: the setting value
        return self._data.get(key, default)

    def ui_language(self):
        # Effective UI/content language: the setting, or the OS locale when
        # set to "system" (used for exported captions, single-language).
        # @return: "es" | "en"
        lang = self._data.get("language", "system")
        if lang == "system":
            import locale
            loc = (locale.getlocale()[0] or "en")[:2]
            lang = loc if loc in ("es", "en") else "en"
        return lang

    def set(self, key, value):
        # @args: key - setting name, value - new value (persisted)
        self._data[key] = value
        self.save()

    def is_configured(self):
        # "Configured" means: we know where the user looks at the sky.
        # Coordinates are the real requirement; an MPC code alone counts
        # too (e.g. a hand-edited config: ephemeris just falls back to the
        # geocenter, which is honest and valid).
        # @return: True if lat + lon are usable, or an MPC code is present
        try:
            has_coords = (float(self._data.get("lat")) != 0.0
                          and float(self._data.get("lon")) != 0.0)
        except (TypeError, ValueError):
            has_coords = False
        if has_coords:
            return True
        return bool((self._data.get("mpc_code") or "").strip())

    def resolve_from_mpc_code(self, code):
        # Fills lat/lon/height (height stays as-is; MPC gives lon + parallax
        # constants) and the observatory name from the MPC observatory list.
        # @args: code - MPC observatory code, e.g. "Z41"
        # @return: True if the code was found
        from .core.sources import obscodes

        info = obscodes.lookup(code)
        if not info:
            return False
        self._data["mpc_code"] = code.strip().upper()
        self._data["lat"] = info["lat"]
        self._data["lon"] = info["lon"]
        self._data["observatory_name"] = info["name"]
        self.save()
        return True


# Shared instance used across the app
config = Config()
