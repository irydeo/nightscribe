############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometric transformations module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Photometric transformations and colour classification (pure math).

Gaia -> Johnson-Cousins uses the polynomials of the Gaia DR3 documentation
(section 5.5.1, Riello et al. 2021), valid for BP-RP in [-0.5, 4.0] and
normal colours only; derived values are always flagged as estimates by the
callers. Ported from SecFot (González Farfán & González Carballo 2026).
"""

import math

# Colour-class boundaries for B-V, shared by every catalog path
_BV_CLASSES = (
    (-0.10, {"es": "Azulada", "en": "Bluish"}),
    (0.30, {"es": "Blanco-azulada", "en": "Blue-white"}),
    (0.58, {"es": "Blanquecina", "en": "Whitish"}),
    (0.81, {"es": "Amarillenta", "en": "Yellowish"}),
    (1.40, {"es": "Anaranjada", "en": "Orange"}),
)
_BV_RED = {"es": "Rojiza", "en": "Reddish"}
_BV_NONE = {"es": "Sin dato", "en": "No data"}


def poly(coefficients, x):
    # Horner evaluation: coefficients[0] multiplies the highest degree.
    # @args: coefficients - highest-degree first, x - the variable
    # @return: the polynomial value
    acc = 0.0
    for k in coefficients:
        acc = acc * x + k
    return acc


def gaia_to_johnson(g, bp_rp):
    # Gaia DR3 -> Johnson-Cousins (Riello et al. 2021; Gaia DR3 doc 5.5.1).
    # @args: g - G magnitude, bp_rp - BP-RP colour
    # @return: {"B", "V", "R", "I"} magnitudes (R/I only when BP-RP <= 2.75,
    #          per the documented validity range), or None when the colour
    #          falls outside [-0.5, 4.0]
    if not (-0.5 <= bp_rp <= 4.0):
        return None
    out = {
        "B": g - poly((0.01448, -0.6874, -0.3604, 0.06718, -0.006061),
                      bp_rp),
        "V": g - poly((-0.02704, 0.01424, -0.2156, 0.01426), bp_rp),
    }
    if bp_rp <= 2.75:
        out["R"] = g - poly((-0.02275, 0.3961, -0.1243, -0.01396,
                             0.003775), bp_rp)
        out["I"] = g - poly((0.01753, 0.76, -0.0991), bp_rp)
    return out


def combine_err(err1, err2):
    # Colour/index uncertainty: both terms in quadrature.
    # @return: hypot(err1, err2), or None when either term is missing
    if err1 is None or err2 is None:
        return None
    return math.hypot(err1, err2)


def classify_bv(bv, lang="es"):
    # @args: bv - B-V colour index (None allowed), lang - "es"|"en"
    # @return: the colour class as a short word in the requested language
    if bv is None or not math.isfinite(bv):
        return _BV_NONE.get(lang, _BV_NONE["es"])
    for limit, label in _BV_CLASSES:
        if bv < limit:
            return label.get(lang, label["es"])
    return _BV_RED.get(lang, _BV_RED["es"])
