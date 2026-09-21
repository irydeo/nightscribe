############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Finder-field chart math module (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure math for the finder/comparison chart, shared by the matplotlib
export (viz/finder_view.py) and the interactive GUI widget (ADR-029, the
same rule core/orbit_math.py follows: one math, two renderers).

The synthetic canvas follows the screen convention (x right, y DOWN,
0..CANVAS units), native to SVG and QGraphicsView; the matplotlib renderer
flips y at draw time. The gnomonic (TAN) projection and its inverse, the
edge-tick placement and the nice-scale choice are ported from SecFot
(González Farfán & González Carballo 2026).
"""

import math

CANVAS = 1000.0   # synthetic canvas side, in canvas units

# [major step, minor step] in seconds of time (RA) or arcseconds (Dec);
# the picker keeps at most ~7 major divisions per edge
TICK_STEPS = ((1, 0.2), (2, 0.5), (5, 1), (10, 2), (15, 5), (30, 5),
              (60, 10), (120, 30), (300, 60), (600, 120), (900, 300),
              (1800, 300), (3600, 600))

_SCALE_OPTIONS = (0.25, 0.5, 1, 2, 5, 10, 15, 20)   # arcminutes


def project(ra, dec, center, field_rad, inverted=False):
    # Gnomonic (TAN) projection onto the synthetic canvas.
    # @args: ra, dec - degrees, center - (ra, dec) degrees, field_rad -
    #        field side in radians, inverted - rotate the view 180 deg
    #        (north down, east right)
    # @return: (x, y) canvas units, y DOWN (0 at the top), north-up and
    #          east-left when not inverted
    ra0 = math.radians(center[0])
    dec0 = math.radians(center[1])
    rar = math.radians(ra)
    decr = math.radians(dec)
    dra = rar - ra0
    if dra > math.pi:
        dra -= 2 * math.pi
    elif dra < -math.pi:
        dra += 2 * math.pi
    denominator = (math.sin(dec0) * math.sin(decr)
                   + math.cos(dec0) * math.cos(decr) * math.cos(dra))
    xi = math.cos(decr) * math.sin(dra) / denominator
    eta = ((math.cos(dec0) * math.sin(decr)
            - math.sin(dec0) * math.cos(decr) * math.cos(dra))
           / denominator)
    direction = 1.0 if inverted else -1.0
    half = CANVAS / 2.0
    return (half + direction * (xi / field_rad) * CANVAS,
            half + direction * (eta / field_rad) * CANVAS)


def screen_to_sky(x, y, center, field_rad, inverted=False):
    # Inverse of project(): canvas point -> sky.
    # @args: x, y - canvas units (y down)
    # @return: (ra, dec) degrees; RA stays continuous with respect to the
    #          center so edges never jump across 0h/24h
    direction = 1.0 if inverted else -1.0
    half = CANVAS / 2.0
    xi = direction * (x - half) / CANVAS * field_rad
    eta = direction * (y - half) / CANVAS * field_rad
    ra0 = math.radians(center[0])
    dec0 = math.radians(center[1])
    rho = math.hypot(xi, eta)
    if rho == 0.0:
        return center
    c = math.atan(rho)
    sin_c, cos_c = math.sin(c), math.cos(c)
    dec = math.asin(cos_c * math.sin(dec0)
                    + eta * sin_c * math.cos(dec0) / rho)
    ra = ra0 + math.atan2(xi * sin_c,
                          rho * math.cos(dec0) * cos_c
                          - eta * math.sin(dec0) * sin_c)
    ra_deg = math.degrees(ra)
    delta = ((ra_deg - center[0] + 540.0) % 360.0) - 180.0
    return center[0] + delta, math.degrees(dec)


def choose_step(span):
    # @args: span - edge span in seconds of time (RA) or arcseconds (Dec)
    # @return: (major, minor) step from TICK_STEPS
    for major, minor in TICK_STEPS:
        if span / major <= 7:
            return major, minor
    return TICK_STEPS[-1]


def edge_crossings(samples, major, minor):
    # Where a monotonic-ish quantity sampled along an edge crosses step
    # multiples: that is where the tick marks go.
    # @args: samples - list of (t, value) along the edge, major/minor -
    #        step sizes in the value's units
    # @return: list of {"t", "value", "major"} dicts, t in edge units
    divisions = max(1, round(major / minor))
    seen = set()
    ticks = []
    for k in range(len(samples) - 1):
        ta, va = samples[k]
        tb, vb = samples[k + 1]
        low, high = min(va, vb), max(va, vb)
        j = math.ceil(low / minor - 1e-9)
        while j * minor <= high + 1e-9:
            if j not in seen and va != vb:
                fraction = (j * minor - va) / (vb - va)
                if -1e-9 <= fraction <= 1 + 1e-9:
                    seen.add(j)
                    ticks.append({
                        "t": ta + fraction * (tb - ta),
                        "value": j * minor,
                        "major": (j % divisions) == 0,
                    })
            j += 1
    return ticks


def format_ra_tick(seconds, step):
    # @args: seconds - RA in seconds of time, step - major step size
    # @return: compact "19h", "19h25m" or "19h25m27s"
    s = (round(seconds) % 86400 + 86400) % 86400
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if step >= 3600:
        return f"{h}h"
    if step >= 60:
        return f"{h}h{m:02d}m"
    return f"{h}h{m:02d}m{sec:02d}s"


def format_dec_tick(arcsec, step):
    # @args: arcsec - Dec in arcseconds, step - major step size
    # @return: compact "+42°", "+42°47'" or "+42°47'03\""
    sign = "-" if arcsec < 0 else "+"
    a = round(abs(arcsec))
    d, rem = divmod(a, 3600)
    m, s = divmod(rem, 60)
    if step >= 3600:
        return f"{sign}{d}\u00b0"
    if step >= 60:
        return f"{sign}{d}\u00b0{m:02d}\u2032"
    return f"{sign}{d}\u00b0{m:02d}\u2032{s:02d}\u2033"


def label_layout(points, clear, cap):
    # The label collision rule (SecFot): the caller sorts by priority
    # (brightest first); a point keeps its label when no kept point sits
    # closer than `clear` (same units); at most `cap` labels survive.
    # @args: points - [(x, y, payload)...] in priority order, clear -
    #        minimum separation, cap - maximum labels
    # @return: list of kept payloads
    kept, occupied = [], []
    for x, y, payload in points:
        if any(math.hypot(ox - x, oy - y) < clear for ox, oy in occupied):
            continue
        occupied.append((x, y))
        kept.append(payload)
        if len(kept) >= cap:
            break
    return kept


def nice_scale(field_arcmin):
    # Round scale-bar length: the largest round option under ~29% of the
    # field (SecFot's rule).
    # @args: field_arcmin - field side in arcminutes
    # @return: scale length in arcminutes
    target = field_arcmin * 0.29
    pick = _SCALE_OPTIONS[0]
    for value in _SCALE_OPTIONS:
        if value <= target:
            pick = value
    return pick


def format_scale(value, lang="es"):
    # @args: value - scale length in arcminutes
    # @return: "30\""-style arcseconds or "5'"-style arcminutes
    if value < 1:
        return f"{round(value * 60)}\u2033"
    return f"{value:g}\u2032"
