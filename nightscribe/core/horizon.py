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

import datetime
import logging
import re

logger = logging.getLogger(__name__)

# Local horizon (ADR-020), the safety reference for the whole app.
#
# Two reference formats:
#   1. TheSkyX limits export (.hrz): one header line, one cardinality line
#      (number of per-azimuth limits; 360 for a 1-deg file) and then one
#      altitude per line, the azimuth being the line index (0..359).
#      Canonical sample: docs/limits-sample.hrz.
#   2. Plain text pairs "az alt" per line ('#' comments) — the simpler
#      format kept for tests and hand-made files.
#
# Precedence (the safety rule): when a horizon file is configured and
# usable it is THE reference — min_alt plays no role. The flat min_alt
# plane is only the fallback when no file is configured (or broken).
# horizon_margin_deg is added on top of whichever reference is in use.

# a safe span breaks when two consecutive safe samples are more than
# one sampling step apart
_SPAN_GAP = datetime.timedelta(minutes=20)

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _floats_in(line):
    # @return: list of float numbers found in a text line
    return [float(x) for x in _NUM_RE.findall(line)]


class _Base:
    # Common API for both horizon kinds: alt_at, is_flat, stats, safe spans.

    def alt_at(self, az_deg):
        # @args: az_deg - azimuth in degrees (any sign/wrap)
        # @return: horizon altitude in degrees at that azimuth
        raise NotImplementedError

    def peak(self):
        # @return: (azimuth, altitude) of the highest point of the horizon
        az, alt = max(self.points, key=lambda p: p[1])
        return az, alt

    def stats(self):
        # @return: dict with min/max altitude and peak azimuth; the GUI uses
        #          it to summarise the file next to the browse button
        pts = self.points
        lo = min(p[1] for p in pts)
        hi = max(p[1] for p in pts)
        return {"min_alt": lo, "max_alt": hi, "peak_az": self.peak()[0]}

    def safe_spans(self, samples, margin=0.0, duration_s=None):
        # Contiguous runs of safe samples over an already-computed sample
        # list (time order preserved from coords.samples_tonight).
        # @args: samples - list of (time, alt, az),
        #        margin - extra safety degrees on top of the horizon,
        #        duration_s - optional minimum span length in seconds
        # @return: list of (start_time, end_time) contiguous safe spans
        spans = []
        cur = []
        prev = None
        for t, alt, az in samples:
            if alt >= self.alt_at(az) + margin:
                if prev is not None and (t - prev) > _SPAN_GAP:
                    if cur:
                        spans.append(cur)
                        cur = []
                cur.append(t)
                prev = t
            elif cur:
                spans.append(cur)
                cur = []
                prev = None
        if cur:
            spans.append(cur)
        if duration_s:
            min_dt = datetime.timedelta(seconds=float(duration_s))
            spans = [s for s in spans if (s[-1] - s[0]) >= min_dt]
        return [(s[0], s[-1]) for s in spans]

    def best_span(self, samples, margin=0.0, duration_s=None):
        # The best safe span for a session of the given duration: the
        # longest contiguous run that still contains the duration. If
        # several spans are equal in length the earliest one wins (it is
        # the one the observer can start earliest).
        # @return: (start, end, recommended_start) UTC datetimes, or None
        #          when no span fits; recommended_start is the latest safe
        #          begin for a session (end - duration) when duration is
        #          given, else the span start
        spans = self.safe_spans(samples, margin, duration_s)
        if not spans:
            return None
        best = max(spans, key=lambda s: (s[1] - s[0]))
        rec = best[1] - datetime.timedelta(seconds=float(duration_s)) \
            if duration_s else best[0]
        return best[0], best[1], rec


class Horizon(_Base):
    # Local horizon as a list of (az, alt) points, linearly interpolated
    # per azimuth and wrapped across 0/360.

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


class FlatHorizon(_Base):
    # Fallback horizon: a uniform altitude floor (the legacy min_alt),
    # used only when no horizon file is configured or the file is broken.

    def __init__(self, min_alt):
        # @args: min_alt - altitude floor in degrees
        self._min = float(min_alt)

    def alt_at(self, az_deg):
        # @return: the configured flat altitude, regardless of azimuth
        return self._min

    @property
    def points(self):
        # one synthetic point per 15 deg; enough for peak()/stats()
        return [(float(i) * 15.0, self._min) for i in range(24)]

    @property
    def is_flat(self):
        return True


# ---------------- parsers ----------------

def _parse_pairs(lines):
    # Plain-text format: one "az alt" pair per non-comment line.
    # @return: list of (az, alt) or None when nothing usable is found
    pts = []
    for s in lines:
        if not s or s.startswith("#"):
            continue
        nums = _floats_in(s)
        if len(nums) >= 2:
            az, alt = nums[0], nums[1]
            if 0.0 <= az <= 360.0 and 0.0 <= alt <= 90.0:
                pts.append((az, alt))
    return pts or None


def _parse_thesky(lines):
    # TheSkyX limits export: header line, cardinality line, then one
    # altitude per line with azimuth = index (docs/limits-sample.hrz).
    # @return: list of (az, alt) or None when the structure does not fit
    content = [s for s in lines if s]
    if len(content) < 5:
        return None
    nums0 = _floats_in(content[0])
    nums1 = _floats_in(content[1])
    if not nums0 or len(nums1) != 1:
        return None
    n = int(nums1[0])
    if not (2 <= n <= 360):
        return None
    body = content[2:2 + n]
    if len(body) < n:
        return None
    # every body line must hold exactly one altitude in the 0..90 range
    alts = []
    for s in body:
        nums = _floats_in(s)
        if len(nums) != 1:
            return None
        v = nums[0]
        if not (0.0 <= v <= 90.0):
            return None
        alts.append(v)
    step = 360.0 / n
    return [(i * step, alts[i]) for i in range(n)]


def _looks_like_thesky(lines):
    # TheSkyX signature: a header holding numbers and a second line that is a
    # bare integer (the limit count). Used to decide which parser owns the
    # file — a file that claims to be TheSkyX must not silently degrade into
    # a 1-point horizon through the pairs fallback (that would read as
    # "no obstacle anywhere", a real safety hazard).
    # @return: True when the structure matches the TheSkyX header
    content = [s for s in lines if s]
    if len(content) < 2:
        return False
    nums2 = _floats_in(content[1])
    return bool(_floats_in(content[0])) and len(nums2) == 1 \
        and nums2[0].is_integer()


def load(path):
    # Parse a horizon file in either supported format.
    # @args: path - file path or pathlib.Path
    # @return: Horizon, or None when the file cannot be read or parsed
    #          (the caller falls back to the flat min_alt plane)
    try:
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
    except OSError as err:
        logger.warning("could not read horizon file %s: %s", path, err)
        return None
    if _looks_like_thesky(lines):
        # one owner, no silent fallback: a bad .hrz is rejected
        pts = _parse_thesky(lines)
        return Horizon(pts) if pts else None
    pts = _parse_pairs(lines)
    return Horizon(pts) if pts else None


def open_reference(cfg):
    # Build the reference horizon actually in use, per the precedence rule:
    # a configured horizon file wins over the flat min_alt plane.
    # @args: cfg - Config (or config-like) instance
    # @return: (Horizon|FlatHorizon, notes) where notes is a list of
    #          (level, message) pairs for the user (UI warnings/status)
    notes = []
    if not cfg:
        return FlatHorizon(30.0), notes
    path = cfg.get("horizon_file") or ""
    if path:
        try:
            h = load(path)
        except Exception as err:  # defensive: never hide a failure silently
            h = None
            notes.append(("error", str(err)))
        if h is None:
            notes.append(("warn",
                          "horizon file unusable (%s) — falling back to "
                          "the flat minimum altitude" % path))
            return FlatHorizon(float(cfg.get("min_alt", 30.0))), notes
        return h, notes
    return FlatHorizon(float(cfg.get("min_alt", 30.0))), notes


def from_config(cfg):
    # Convenience wrapper: just the horizon object (see open_reference).
    # @return: Horizon or FlatHorizon
    hor, _notes = open_reference(cfg)
    return hor
