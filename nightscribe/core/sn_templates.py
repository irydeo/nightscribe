############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN light-curve templates (Track B, B4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Schematic normalised SN light-curve templates.

The follow-up curve overlays a faint dashed line of the typical shape for
the SN's type so the observer can tell at a glance "evoluciona normal" vs
"hay algo brusco" — the real keep/drop criterion (interview, block 2).

These are **schematic**, not for analysis: hand-crafted parametric shapes
normalised to peak (day 0 = 0 mag, delta_mag positive = fainter). The chart's
inverted Y axis means the template curves go *up* on screen as the SN fades,
matching the user's own points. Multi-band differences are small and
best-effort; the label says "esquemática".
"""

import math

# Each template is a list of (days_from_peak, delta_mag) sampled at ~3-5-day
# intervals, covering ~120 days (the typical follow-up window). delta_mag is
# *fainter than peak* (positive = the chart plots it higher with inverted Y).
# The peak (0, 0.0) is always the first entry; the ranges exclude 0 to avoid
# duplicating it.


def _ia():
    # Type Ia: fast rise (~1 mag in 18 d), exponential decline. Decline rate
    # ~0.06 mag/d in the first 15 d (B-band), slowing after.
    pts = [(0, 0.0)]
    for d in range(-20, 0, 3):
        dm = 3.5 * math.exp(d / 7.0)
        pts.append((d, round(dm, 3)))
    for d in range(3, 121, 3):
        dm = min(3.5, 1.5 + 0.04 * d + 0.0008 * d * d)
        pts.append((d, round(dm, 3)))
    pts.sort(key=lambda p: p[0])
    return pts


def _ii_p():
    # Type II-P: rise (~2 mag in 15 d), plateau (~100 d at ~1 mag below peak),
    # then linear decline (~0.01 mag/d).
    pts = [(0, 0.0)]
    for d in range(-18, 0, 3):
        dm = 2.0 * math.exp(d / 6.0)
        pts.append((d, round(dm, 3)))
    for d in range(3, 121, 3):
        dm = 1.0 if d < 100 else 1.0 + 0.01 * (d - 100)
        pts.append((d, round(dm, 3)))
    pts.sort(key=lambda p: p[0])
    return pts


def _ii_l():
    # Type II-L: rise, then linear decline (no plateau, ~0.015 mag/d).
    pts = [(0, 0.0)]
    for d in range(-15, 0, 3):
        dm = 2.0 * math.exp(d / 5.0)
        pts.append((d, round(dm, 3)))
    for d in range(3, 121, 3):
        dm = 0.015 * d
        pts.append((d, round(dm, 3)))
    pts.sort(key=lambda p: p[0])
    return pts


def _ib_c():
    # Type Ib/c: rise, moderate decline (~0.03 mag/d).
    pts = [(0, 0.0)]
    for d in range(-12, 0, 3):
        dm = 2.5 * math.exp(d / 4.0)
        pts.append((d, round(dm, 3)))
    for d in range(3, 121, 3):
        dm = 0.03 * d
        pts.append((d, round(dm, 3)))
    pts.sort(key=lambda p: p[0])
    return pts


def _generic():
    # Unclassified / unknown: a gentle rise and slow decline — just a
    # visual reference, no claim of a specific shape.
    pts = [(0, 0.0)]
    for d in range(-10, 0, 5):
        dm = 2.0 * math.exp(d / 4.0)
        pts.append((d, round(dm, 3)))
    for d in range(5, 121, 5):
        dm = 0.02 * d
        pts.append((d, round(dm, 3)))
    pts.sort(key=lambda p: p[0])
    return pts


_TPL = {
    "Ia": _ia(),
    "II": _ii_p(),
    "II-P": _ii_p(),
    "II-L": _ii_l(),
    "Ib": _ib_c(),
    "Ic": _ib_c(),
    "Ib/c": _ib_c(),
    "IIn": _generic(),      # IIn is complex; use a generic shape
    "Iax": _ia(),           # Iax is Ia-like
    "SLSN": _generic(),      # superluminous; very broad — generic
    "kilonova": _generic(),
    "": _generic(),          # unclassified → generic reference
}


def template(sn_type):
    # @args: sn_type - string from TNS/SIMBAD (e.g. "SN Ia", "SN II-P")
    # @return: list of (days_from_peak, delta_mag) or None if no match.
    #         Normalised to peak; delta_mag is fainter-than-peak (positive).
    if not sn_type:
        return _TPL[""]
    # normalise: "SN Ia" -> "Ia", "SN II-P" -> "II-P". Keep the subtype
    # case (Ia, II-P, Ib/c) as the dict keys use it.
    t = sn_type.strip()
    if t.upper().startswith("SN "):
        t = t[3:].strip()
    return _TPL.get(t) or _TPL[""]   # unknown type → generic reference
