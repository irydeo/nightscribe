############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - chart palette module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Single source of truth for the *chart* colours (the dark space theme with the
# orange accent the object wears and the muted hues for grids and labels).
#
# Kept free of any matplotlib import on purpose: `gui/widgets/*` reads these
# the same constants from `viz.palette` without pulling the backend along
# (ADR-029 — the GUI chart layer is PySide6-only, the matplotlib engine stays
# reserved for the social-media PNG exports, ADR-010).

BG     = "#0b0d17"   # chart surface (windows themselves use a slightly
                    # warmer C_BG from gui/theme — the two layers stay
                    # distinct on purpose)
FG     = "#e8eaf2"   # main text, tick labels, foreground lines
ACCENT = "#ffb347"   # warm orange — the object, the orbit, the target curve
ACCENT2 = "#6ec1ff"  # cool blue — Earth, dark-spawn tints
MUTED  = "#8a90a6"   # planet rings, the 1 AU ruler, grids, watermarks
SUN    = "#ffd76e"   # the Sun marker
DANGER = "#ff6b6b"   # safety warnings (does-not-fit, moon interference)
GOOD   = "#46a758"   # a measurement you can trust (the plate's band)
FAIR = "#ff9e4d"     # usable but not clean: the band's orange (see GOOD)
CATALOG = "#ffffff"  # a value that is NOT a measurement of this plate

# Per-planet marker rings (kept distinct from the theme above so a chart
# can tell Earth / Mercury / Venus / Mars apart at a glance).
PLANET_COLORS = {
    "mercury": "#b5a58f",
    "venus":   "#e8c07d",
    "earth":   ACCENT2,
    "mars":    "#d1704f",
    "jupiter": "#c8a06e",
    "saturn":  "#d8c9a3",
    "uranus":  "#8fc7c9",
    "neptune": "#5f7fcf",
}


def planet_color(name):
    # @args: name - one of the "mercury"|"venus"|"earth"|"mars"|"jupiter"
    # @return: a PySide6 QColor for that planet (falls back to Earth).
    from PySide6.QtGui import QColor
    return QColor(PLANET_COLORS.get(name.lower(), PLANET_COLORS["earth"]))


def color(name):
    # @args: name - one of the constant names on this module
    # @return: a PySide6 QColor from the hex string. Raises when the name
    #          is not a chart colour (typo or a colour that was later
    #          removed), so a wrong reference cannot silently produce
    #          a black/transparent chart.
    from PySide6.QtGui import QColor
    keys = (BG, FG, ACCENT, ACCENT2, MUTED, SUN, DANGER)
    if name not in keys:
        raise KeyError(f"unknown chart colour: {name!r}")
    return QColor(name)


# Which colour each ROLE of a measurement wears. The roles are decided in
# core/chart_annotate (pure, testable: see magnitude_role) and the colour is
# here, so the plate's band, the measurement's panel and the curve's points
# cannot disagree about what "green" means.
MEASURE_COLOURS = {
    "name": FG,           # the object: whose plate this is
    "pos": FG,            # placed by this plate's own solution
    "pos-cat": MUTED,     # the catalogue's position, not this plate's
    "mag": GOOD,          # a clean measurement
    "mag-fair": FAIR,     # usable, but not clean
    "mag-doubt": DANGER,  # not worth reporting without looking
    "mag-cat": CATALOG,   # a catalogue value: not a measurement
    "mag-eph": MUTED,     # the ephemeris' prediction, not measured here
    "motion": FG,         # the object's motion, measured on this plate
    "motion-eph": MUTED,  # only the ephemeris' prediction, not measured
    "context": MUTED,     # date, exposure, filter, kit, Stn, PSc, FOV
}
