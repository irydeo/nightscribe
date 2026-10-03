############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Tonight's brief for a site (shared night data)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""What the night looks like from a site, in numbers and in words.

The Welcome hero, the navigation sky bar and the resting panel of the
projects view all answer the same three questions: when does it get dark,
what is the Moon doing, and which planets are up at dusk. This module is
the single place where those three are computed AND worded, so the three
surfaces can never disagree about the Moon.

Everything here is local arithmetic on core/coords and core/ephem_minor:
no network, no cache. That is what lets it run on every keystroke of a
latitude without anyone noticing.

i18n: the strings below are translated as the "NSNight" context. lupdate
reads them from the QT_TRANSLATE_NOOP marks (the same pattern as
core/kinds.py), and tr() fills the {placeholders}. The Qt import is
guarded so the CLI can use this module with no Qt around.
"""

import datetime as _dt

from . import coords, ephem_minor

try:
    from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
except ImportError:                     # the CLI: no Qt, plain strings
    QCoreApplication = None

    def QT_TRANSLATE_NOOP(context, string):
        # @args: context - unused here; string - the source text
        # @return: the source text unchanged
        return string

_K = "NSNight"

S_NO_DARK = QT_TRANSLATE_NOOP("NSNight",
    "No astronomical night at this site tonight: the Sun never drops 18° "
    "below the horizon.")
S_WINDOW = QT_TRANSLATE_NOOP("NSNight",
    "Astronomical night {start} → {end} · {hours} h of darkness")
S_MOON_SET = QT_TRANSLATE_NOOP("NSNight",
    "Moon {pct}% {phase} · sets {time}")
S_MOON_UP = QT_TRANSLATE_NOOP("NSNight",
    "Moon {pct}% {phase} · up all night")
S_MOON_DOWN = QT_TRANSLATE_NOOP("NSNight",
    "Moon {pct}% {phase} · below the horizon all night")
S_MOON_SHORT = QT_TRANSLATE_NOOP("NSNight", "Moon {pct}% {phase}")
S_PLANETS_NONE = QT_TRANSLATE_NOOP("NSNight",
    "At dusk: no bright planet above the horizon.")
S_PLANETS = QT_TRANSLATE_NOOP("NSNight", "At dusk: {planets}")
S_NO_SITE = QT_TRANSLATE_NOOP("NSNight", "Set your observatory")

# The phases in words. Bands, not a formula: the eye reads "waning
# gibbous" long before it reads "illum 0.72".
S_PHASES = (
    QT_TRANSLATE_NOOP("NSNight", "new moon"),
    QT_TRANSLATE_NOOP("NSNight", "waxing crescent"),
    QT_TRANSLATE_NOOP("NSNight", "first quarter"),
    QT_TRANSLATE_NOOP("NSNight", "waxing gibbous"),
    QT_TRANSLATE_NOOP("NSNight", "full moon"),
    QT_TRANSLATE_NOOP("NSNight", "waning gibbous"),
    QT_TRANSLATE_NOOP("NSNight", "last quarter"),
    QT_TRANSLATE_NOOP("NSNight", "waning crescent"),
)

S_MERCURY = QT_TRANSLATE_NOOP("NSNight", "Mercury")
S_VENUS = QT_TRANSLATE_NOOP("NSNight", "Venus")
S_MARS = QT_TRANSLATE_NOOP("NSNight", "Mars")
S_JUPITER = QT_TRANSLATE_NOOP("NSNight", "Jupiter")
S_SATURN = QT_TRANSLATE_NOOP("NSNight", "Saturn")

# Compass letters, one by one on purpose: west is W in English and O in
# Spanish, and a wrong letter sends the telescope the wrong way.
S_COMPASS = tuple(QT_TRANSLATE_NOOP("NSNight", letter)
                  for letter in ("N", "NE", "E", "SE", "S", "SW", "W", "NW"))

# A planet below this is behind the trees and the haze: saying it anyway
# would be noise.
MIN_PLANET_ALT = 5.0

# The Moon is sampled every 20 minutes to find its set: the ephemeris is
# arcminute-accurate, so finer steps would buy nothing.
_MOON_STEP = _dt.timedelta(minutes=20)


def tr(text, **values):
    # Translates one of the S_* marks (context "NSNight") and fills its
    # {placeholders}.
    # @args: text - an S_* mark; values - the .format() arguments
    # @return: the translated, filled-in text
    out = (QCoreApplication.translate(_K, text) if QCoreApplication
           else text)
    return out.format(**values) if values else out


def brief(lat, lon, when=None):
    # The whole night in one dict. Callers read it; nobody recomputes it.
    # @args: lat, lon - the site in degrees; when - a datetime.date (UTC)
    # @return: {"window": (dusk, dawn) UTC or None,
    #           "moon": {"illum", "age", "waxing", "set_utc", "up_ever"}
    #                   or None,
    #           "planets": [{"key", "alt", "az", "mag"}, ...]}
    win = coords.tonight_window(lat, lon, date=when)
    out = {"window": win, "moon": None, "planets": []}
    if win is None:
        return out
    out["moon"] = _moon(lat, lon, win)
    out["planets"] = _planets(lat, lon, win[0])
    return out


def _moon(lat, lon, win):
    # @args: lat, lon - the site; win - (dusk, dawn) UTC
    # @return: the Moon's night, in numbers (see brief)
    t = win[0]
    prev = None
    set_at = None
    up_ever = False
    while t <= win[1]:
        jd = coords.jd_from_datetime(t)
        m = ephem_minor.moon(jd)
        alt, _az = coords.altaz(m["ra"], m["dec"], lat,
                                coords.lst_degrees(jd, lon))
        up_ever = up_ever or alt > 0.0
        if prev is not None and prev > 0.0 >= alt and set_at is None:
            set_at = t
        prev = alt
        t += _MOON_STEP
    jd = coords.jd_from_datetime(win[0])
    m = ephem_minor.moon(jd)
    elong = float(m["elong_deg"])
    return {"illum": float(m["illum"]),
            "age": float(m["phase_age_days"]),
            # elong > 0 means the Moon is east of the Sun: waxing, lit on
            # the right as seen from the northern hemisphere. The signed
            # angle travels with the brief so the sky bar can DRAW the same
            # Moon it describes (gui/moon_icon.moon_pixmap).
            "elong": elong,
            "waxing": elong > 0.0,
            "set_utc": set_at,
            "up_ever": up_ever}


def _planets(lat, lon, dusk):
    # @args: lat, lon - the site; dusk - the UTC datetime to look at
    # @return: the planets worth a glance at dusk, highest first
    jd = coords.jd_from_datetime(dusk)
    lst = coords.lst_degrees(jd, lon)
    found = []
    for key in ("venus", "jupiter", "mars", "saturn", "mercury"):
        try:
            p = ephem_minor.planet(key, jd)
        except Exception:               # a broken element set is not a crash
            continue
        alt, az = coords.altaz(p["ra"], p["dec"], lat, lst)
        if alt >= MIN_PLANET_ALT:
            found.append({"key": key, "alt": alt, "az": az,
                          "mag": p.get("mag")})
    found.sort(key=lambda item: -item["alt"])
    return found


# ------------------------------------------------------------- wording

def local_hhmm(dt):
    # @args: dt - a UTC datetime
    # @return: "HH:MM" in the observer's own clock. The window comes out of
    #          the ephemeris in UTC; showing UTC would make the line useless
    #          for planning dinner, let alone a session.
    return dt.astimezone().strftime("%H:%M")


def phase_name(age):
    # @args: age - the Moon's age in days (0 new, ~14.8 full)
    # @return: the phase in words
    if age < 1.0 or age > 28.5:
        return tr(S_PHASES[0])
    if age < 6.5:
        return tr(S_PHASES[1])
    if age < 8.0:
        return tr(S_PHASES[2])
    if age < 13.8:
        return tr(S_PHASES[3])
    if age < 15.8:
        return tr(S_PHASES[4])
    if age < 21.0:
        return tr(S_PHASES[5])
    if age < 22.5:
        return tr(S_PHASES[6])
    return tr(S_PHASES[7])


def compass(az):
    # @args: az - azimuth in degrees (0 = north, 90 = east)
    # @return: the 8-point compass name: an azimuth in degrees is not
    #          something anyone points a telescope with
    return tr(S_COMPASS[int((az % 360.0) / 45.0 + 0.5) % 8])


def planet_name(key):
    # @args: key - "venus", "jupiter", ...
    # @return: the planet's name in the UI language
    return {"mercury": tr(S_MERCURY), "venus": tr(S_VENUS),
            "mars": tr(S_MARS), "jupiter": tr(S_JUPITER),
            "saturn": tr(S_SATURN)}.get(key, key.title())


def window_line(b):
    # @args: b - a brief() dict
    # @return: one sentence about the darkness window
    win = b.get("window")
    if win is None:
        return tr(S_NO_DARK)
    hours = (win[1] - win[0]).total_seconds() / 3600.0
    return tr(S_WINDOW, start=local_hhmm(win[0]), end=local_hhmm(win[1]),
              hours=("%.1f" % hours).replace(".0", ""))


def moon_line(b):
    # @args: b - a brief() dict
    # @return: one sentence: phase, and what it does during the night
    moon = b.get("moon")
    if moon is None:
        return ""
    pct = int(round(moon["illum"] * 100.0))
    name = phase_name(moon["age"])
    if not moon["up_ever"]:
        return tr(S_MOON_DOWN, pct=pct, phase=name)
    if moon["set_utc"] is not None:
        return tr(S_MOON_SET, pct=pct, phase=name,
                  time=local_hhmm(moon["set_utc"]))
    return tr(S_MOON_UP, pct=pct, phase=name)


def moon_short(b):
    # @args: b - a brief() dict
    # @return: the Moon in four words, for the sky bar
    moon = b.get("moon")
    if moon is None:
        return ""
    return tr(S_MOON_SHORT, pct=int(round(moon["illum"] * 100.0)),
              phase=phase_name(moon["age"]))


def planets_line(b):
    # @args: b - a brief() dict
    # @return: the planets at dusk, with where and how high they are
    found = b.get("planets") or []
    if not found:
        return tr(S_PLANETS_NONE)
    parts = ["%s (%s, %d°)" % (planet_name(p["key"]), compass(p["az"]),
                               int(round(p["alt"]))) for p in found]
    return tr(S_PLANETS, planets=", ".join(parts))


def planets_short(b):
    # @args: b - a brief() dict
    # @return: just the names, for a bar that has no room for altitudes
    found = b.get("planets") or []
    if not found:
        return ""
    return ", ".join(planet_name(p["key"]) for p in found)
