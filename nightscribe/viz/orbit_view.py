############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Top-down orbit chart
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
import math

from ..core import coords, ephem_minor
from . import style

logger = logging.getLogger(__name__)

# Top-down (ecliptic, north up) chart: inner planets for scale, the object's
# orbit highlighted, its current position, and an Earth-Moon zoom inset when
# a close approach is given (see docs/VIZ).

_PLANET_COLORS = {"mercury": "#b5a58f", "venus": "#e8c07d", "earth": style.ACCENT2,
                  "mars": "#d1704f", "jupiter": "#c8a06e"}
_ORBIT_SPAN = {"mercury": 0.47, "venus": 0.73, "earth": 1.0, "mars": 1.67,
               "jupiter": 5.45}


def _orbit_xy(elements, n=360):
    # Samples a full orbit in heliocentric ecliptic coordinates.
    # @args: elements - dict with a, e, i, om, w; n - samples
    # @return: (xs, ys) lists in AU
    e = elements.get("e", 0)
    # open orbit (parabolic/hyperbolic): sample true anomaly directly
    if e >= 1.0:
        q = elements.get("q")
        if q is None or q <= 0:
            return [], []
        # avoid the asymptote where 1 + e*cos(nu) -> 0
        nu_max = min(150.0, math.degrees(math.acos(-1.0 / e)) - 5.0)
        xs, ys = [], []
        for k in range(n + 1):
            nu = -nu_max + 2 * nu_max * k / n
            try:
                x, y, z, _r = ephem_minor._open_orbit_ecliptic(
                    elements.get("om", 0.0), elements.get("i", 0.0),
                    elements.get("w", 0.0), q, e, nu)
                xs.append(x)
                ys.append(y)
            except (KeyError, ZeroDivisionError, ValueError):
                continue
        return xs, ys
    # bound orbit: sample via Kepler
    a = elements.get("a")
    if a is None:
        q = elements.get("q")
        if q is not None:
            a = q / (1.0 - e)
        else:
            return [], []
    xs, ys = [], []
    for k in range(n + 1):
        els = dict(elements)
        els["a"] = a
        els["ma"] = 360.0 * k / n
        try:
            x, y, z, _r = ephem_minor._elements_to_ecliptic(
                els.get("om", 0.0), els.get("i", 0.0), els.get("w", 0.0),
                a, els.get("e", 0.0), els["ma"])
            xs.append(x)
            ys.append(y)
        except (KeyError, ZeroDivisionError, ValueError):
            continue
    return xs, ys


def draw_orbit(elements, jd=None, obj_name="", approach=None, out=None,
                fmt="instagram", watermark="NightScribe", size=None, lang="es"):
    # Renders the object's orbit among the inner planets.
    # @args: elements - SBDB elements dict, jd - Julian date (today),
    #        obj_name - label, approach - dict from cad.next_approach,
    #        out - output PNG path (returns figure if None),
    #        fmt - size preset, watermark - footer text,
    #        size - (w, h) px override (panel re-render mode),
    #        lang - string language ("es"|"en"); charts follow the UI language
    # @return: matplotlib figure (and writes PNG if out is given)
    import matplotlib.pyplot as plt

    jd = jd or coords.jd_from_datetime(
        datetime.datetime.now(datetime.timezone.utc))
    fig, ax = style.new_fig(fmt, size=size)
    ax.set_aspect("equal")

    # ensure a is available (compute from q when SBDB omits it for high-e)
    e = elements.get("e", 0)
    a = elements.get("a")
    if (a is None or a <= 0) and e < 1.0:
        q = elements.get("q")
        if q is not None:
            a = q / (1.0 - e)
            elements = dict(elements, a=a)

    # frame: the smallest square that contains the object's orbit AND the Sun,
    # centred on that union (not the orbit alone — the Sun sits at a focus, so
    # an eccentric orbit's centre is offset and framing it alone left a big
    # empty side). The 1 AU ring is the chart's ruler ("1 AU = Earth–Sun") and
    # always stays in frame; the larger Mars/Jupiter references are drawn only
    # when they already fit inside that square, so small/inner targets keep a
    # tight crop instead of being padded out to Mars (ADR-010, 2026-09-02).
    xs0, ys0 = _orbit_xy(elements)
    ox = list(xs0) + [0.0]
    oy = list(ys0) + [0.0]
    cx = (min(ox) + max(ox)) / 2.0
    cy = (min(oy) + max(oy)) / 2.0
    span = max((max(ox) - min(ox)) / 2.0,
               (max(oy) - min(oy)) / 2.0,
               1.0 + abs(cx), 1.0 + abs(cy)) * 1.06
    planets = ["mercury", "venus", "earth"]
    for r, pname in ((_ORBIT_SPAN["mars"], "mars"),
                     (_ORBIT_SPAN["jupiter"], "jupiter")):
        if span >= r + max(abs(cx), abs(cy)):
            planets.append(pname)
    for pname in planets:
        pos = ephem_minor.planet(pname, jd) if pname != "earth" else None
        r = _ORBIT_SPAN[pname]
        circle = plt.Circle((0, 0), r, fill=False, color=style.MUTED,
                            alpha=0.35, lw=0.8)
        ax.add_patch(circle)
        # planet current position (heliocentric)
        if pname == "earth":
            xe, ye, _ = ephem_minor.earth_ecliptic_xyz(jd)
        else:
            # heliocentric from the planet() geocentric: recompute directly
            p = ephem_minor._PLANETS[pname]
            d = jd - 2451543.5
            els = {"om": (p[0] + p[1] * d) % 360, "i": p[2] + p[3] * d,
                   "w": (p[4] + p[5] * d) % 360, "a": p[6] + p[7] * d,
                   "e": p[8] + p[9] * d}
            x, y, z, _r = ephem_minor._elements_to_ecliptic(
                els["om"], els["i"], els["w"], els["a"], els["e"],
                (p[10] + p[11] * d) % 360)
            xe, ye = x, y
        ax.plot(xe, ye, "o", color=_PLANET_COLORS[pname], ms=7,
                zorder=5)
        ax.annotate(pname.capitalize(), (xe, ye), textcoords="offset points",
                    xytext=(6, 6), color=style.MUTED, fontsize=8)

    # the Sun at the origin
    ax.plot(0, 0, "o", color=style.SUN, ms=12, zorder=6)
    ax.annotate(style.pick(lang, "Sol", "Sun"), (0, 0),
                textcoords="offset points",
                xytext=(8, -12), color=style.SUN, fontsize=8)

    # the object's orbit and current position
    xs, ys = _orbit_xy(elements)
    ax.plot(xs, ys, color=style.ACCENT, lw=1.6, zorder=4)
    # current heliocentric position for the marker
    if e >= 1.0:
        # open orbit: use Barker's equation to get true anomaly, then position
        q = elements.get("q")
        tp = elements.get("tp")
        if q and tp:
            nu = ephem_minor._barker_true_anomaly(q, jd - tp)
            x, y, z, _r = ephem_minor._open_orbit_ecliptic(
                elements.get("om", 0.0), elements.get("i", 0.0),
                elements.get("w", 0.0), q, e, nu)
            ax.plot(x, y, "o", color=style.ACCENT, ms=10, zorder=7)
            ax.annotate(obj_name or "?", (x, y), textcoords="offset points",
                        xytext=(8, 8), color=style.ACCENT, fontsize=10,
                        fontweight="bold")
    else:
        pos = ephem_minor.kepler_ra_dec(elements, jd)
        if pos:
            a_el = elements.get("a")
            if a_el and a_el > 0 and elements.get("ma") is not None:
                n_day = 0.9856076686 / (a_el ** 1.5)
                m_now = (elements["ma"] + n_day * (jd - elements.get("epoch", jd))) % 360
            elif a_el and a_el > 0 and elements.get("tp") is not None:
                n_day = 0.9856076686 / (a_el ** 1.5)
                m_now = (n_day * (jd - elements["tp"])) % 360
            else:
                m_now = None
            if m_now is not None:
                x, y, z, _r = ephem_minor._elements_to_ecliptic(
                    elements.get("om", 0.0), elements.get("i", 0.0),
                    elements.get("w", 0.0), a_el, elements.get("e", 0.0), m_now)
                ax.plot(x, y, "o", color=style.ACCENT, ms=10, zorder=7)
                ax.annotate(obj_name or "?", (x, y), textcoords="offset points",
                            xytext=(8, 8), color=style.ACCENT, fontsize=10,
                            fontweight="bold")

    ax.set_xlim(cx - span, cx + span)
    ax.set_ylim(cy - span, cy + span)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        style.pick(lang,
                   f"{obj_name} — órbita" if obj_name else "Órbita",
                   f"{obj_name} — orbit" if obj_name else "Orbit"),
        loc="left")
    ax.text(0.02, 0.98,
            style.pick(
                lang,
                f"1 AU = Tierra–Sol  ·  vista {span * 2:.0f} AU",
                f"1 AU = Earth–Sun  ·  {span * 2:.0f} AU across"),
            transform=ax.transAxes, va="top", color=style.MUTED, fontsize=8)

    # close-approach inset: Earth-Moon system
    if approach and approach.get("dist_ld"):
        _draw_approach_inset(fig, ax, approach, lang=lang)

    style.watermark(fig, watermark)
    if out:
        style.save(fig, out)
        logger.info("orbit chart written to %s", out)
    return fig


def _draw_approach_inset(fig, ax, approach, lang="es"):
    # Small inset showing the flyby distance against the Moon's orbit.
    # @args: fig - figure, ax - main axes, approach - dict from cad,
    #        lang - string language ("es"|"en")
    import matplotlib.pyplot as plt
    inset = fig.add_axes([0.66, 0.63, 0.27, 0.27])
    inset.set_facecolor(style.BG)
    ld = approach["dist_ld"]
    span = max(1.6, ld * 1.9)
    moon_orbit = plt.Circle((0, 0), 1.0, fill=False, color=style.MUTED, lw=1.0)
    inset.add_patch(moon_orbit)
    inset.plot(0, 0, "o", color=style.ACCENT2, ms=8)
    inset.annotate(style.pick(lang, "Tierra", "Earth"), (0, 0),
                   textcoords="offset points",
                   xytext=(8, -12), color=style.ACCENT2, fontsize=7)
    inset.plot(1, 0, "o", color="#c9c9c9", ms=5)
    inset.annotate(style.pick(lang, "Luna", "Moon"), (1, 0),
                   textcoords="offset points",
                   xytext=(6, 5), color=style.MUTED, fontsize=7)
    # the flyby, stylised as a straight pass at the given distance
    inset.plot([-span, span], [ld, ld], color=style.ACCENT, lw=1.5, ls="--")
    inset.plot(0, ld, "o", color=style.ACCENT, ms=6)
    inset.annotate(f"{ld:.2f} LD", (0, ld), textcoords="offset points",
                   xytext=(-span * 30, 6), color=style.ACCENT, fontsize=7,
                   fontweight="bold")
    if ld < 0.5:
        inset.text(0.5, 0.02,
                   style.pick(lang, "¡Más cerca que la Luna!",
                              "Closer than the Moon!"),
                   transform=inset.transAxes, ha="center", va="bottom",
                   color=style.ACCENT, fontsize=7, fontweight="bold")
    inset.set_xlim(-span, span)
    inset.set_ylim(-span, span)
    inset.set_aspect("equal")
    inset.set_xticks([])
    inset.set_yticks([])
    date = (approach.get("date") or "")[:11]
    inset.set_title(
        style.pick(lang, f"Aproximación\n{date}", f"Close approach\n{date}"),
        fontsize=8, color=style.FG)
    for spine in inset.spines.values():
        spine.set_color(style.MUTED)
