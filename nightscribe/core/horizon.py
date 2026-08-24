############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Local horizon module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re

logger = logging.getLogger(__name__)

# Azimuth-dependent horizon (ADR-020). The real TheSkyX export format is
# validated against the user's file in phase 2; until then we parse any
# text file with one "az alt" pair per line (whitespace or comma separated,
# '#' comments). A flat min_alt fallback covers the no-file case.

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _floats_in(line):
    # @return: list of float numbers found in a text line
    return [float(x) for x in _NUM_RE.findall(line)]


class Horizon:
    # Local horizon as a sorted list of (az, alt) points, interpolated per
    # azimuth and wrapped across 0/360.

    def __init__(self, points):
        # @args: points - list of (az_deg, alt_deg)
        pts = {}
        for az, alt in points:
            pts[az % 360.0] = float(alt)
        self._azs = sorted(pts.keys())
        self._alts = [pts[a] for a in self._azs]

    def alt_at(self, az_deg):
        # @args: az_deg - azimuth in degrees (any sign/wrap)
        # @return: horizon altitude in degrees at that azimuth
        az = az_deg % 360.0
        azs, alts = self._azs, self._alts
        if len(azs) == 1:
            return alts[0]
        # extend across the 0/360 seam so interpolation wraps cleanly
        ext_a = [azs[-1] - 360.0] + azs + [azs[0] + 360.0]
        ext_b = [alts[-1]] + alts + [alts[0]]
        for i in range(len(ext_a) - 1):
            if ext_a[i] <= az <= ext_a[i + 1]:
                a0, a1 = ext_a[i], ext_a[i + 1]
                b0, b1 = ext_b[i], ext_b[i + 1]
                if a1 == a0:
                    return b0
                t = (az - a0) / (a1 - a0)
                return b0 + t * (b1 - b0)
        return alts[0]

    @property
    def points(self):
        # @return: list of (az, alt) tuples
        return list(zip(self._azs, self._alts))

    @property
    def is_flat(self):
        # @return: True if the horizon is a single uniform altitude
        return len(set(round(b, 3) for b in self._alts)) == 1


class FlatHorizon:
    # Fallback horizon: a uniform altitude floor (the legacy min_alt).

    def __init__(self, min_alt):
        # @args: min_alt - altitude floor in degrees
        self._min = float(min_alt)

    def alt_at(self, az_deg):
        # @return: the configured flat altitude, regardless of azimuth
        return self._min

    @property
    def is_flat(self):
        return True


def load(path):
    # Parse a text horizon file (az alt per line, comments with '#').
    # @args: path - file path or pathlib.Path
    # @return: Horizon or None when the file cannot be read/parsed
    pts = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                nums = _floats_in(line)
                if len(nums) >= 2:
                    az, alt = nums[0], nums[1]
                    if 0.0 <= az <= 360.0 and -90.0 <= alt <= 90.0:
                        pts.append((az, alt))
    except OSError as err:
        logger.warning("could not read horizon file %s: %s", path, err)
        return None
    if len(pts) < 2:
        return None
    return Horizon(pts)


def from_config(cfg):
    # Build the horizon in use from configuration: the configured file when
    # present, otherwise a flat min_alt fallback.
    # @args: cfg - Config (or config-like) instance
    # @return: Horizon or FlatHorizon
    path = cfg.get("horizon_file") if cfg else None
    if path:
        h = load(path)
        if h is not None:
            return h
        logger.warning("horizon file %s unusable; falling back to flat min_alt",
                       path)
    min_alt = float(cfg.get("min_alt", 30.0)) if cfg else 30.0
    return FlatHorizon(min_alt)
