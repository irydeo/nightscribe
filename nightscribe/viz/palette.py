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
