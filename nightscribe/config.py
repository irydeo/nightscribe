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

# Defaults: the author's own observatory, used as a working example.
DEFAULTS = {
    "mpc_code": "Z41",
    "observatory_name": "Irydeo Observatory",
    "lat": 40.55,           # geodetic degrees
    "lon": -3.37,           # degrees east
    "height": 631,          # meters
    "aperture_inches": 10.0,
    "limit_mag": 20.0,
    "min_alt": 30.0,        # degrees above horizon
    "language": "system",   # system | es | en
    "neofixer_key": "",     # optional, for reporting observing status
    "tns_bot_name": "",     # optional, to show TNS discovery images
    "tns_bot_key": "",
    "astrometry_key": "",   # optional, blind-solving unsolved FITS (blink)
}


class Config:
    # Tiny persistent configuration on top of a JSON file in the user
    # config dir. Values are always strings/numbers/bools.

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
        # @return: True once the first-run wizard has been completed
        return bool(self._data.get("mpc_code") and self._data.get("observatory_name"))

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
