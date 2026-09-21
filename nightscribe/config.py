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
    "camera_type": "CCD",       # CCD | CMOS | DSLR (CMOS -> "CCD" + note)
    "pixel_binning": "1x1",
    "aavso_code": "",           # AAVSO observer code; blank when none
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
