############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - System gain and read noise from the frames (quality
# plan, phase G)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The system gain, measured on the observer's own frames.

Every honest error bar starts here: the CCD equation needs the gain
(e-/ADU) and the read noise (e-), and without them the "error" of a
photometric point collapses into the scatter of the comparison stars,
which is a different and usually much bigger animal.

The recipe is the classic one and needs no flats, no special hardware and
no scipy: two frames of the SAME exposure, in ADU, give

    var(F1 - F2) = 2 * (level / g + ron^2 / g^2)

so a straight line fitted over the boxes of the frame pair yields both
the gain (the slope) and the read noise (the intercept). The sky itself
is the Poisson source, which is why an ordinary pair of frames is enough.

Two frames at ONE exposure give the gain well and the read noise only
badly (the level range across a frame is narrow); a second pair at a very
different level (a longer exposure, twilight against night) widens the
lever arm and pins the read noise too. The module does the same fit
either way and says which of the two numbers it trusts.

Pure numpy (ADR-004). The measured values are reported, never written
into the settings behind the observer's back.
"""

import logging
import math

import numpy as np

from . import outliers

logger = logging.getLogger(__name__)

# A gain outside this range is not a gain (a mis-typed value, a different
# unit, saturated boxes): the estimate is refused, not rounded.
GAIN_MIN = 0.05
GAIN_MAX = 30.0
RON_MIN = 0.3
RON_MAX = 50.0
# Boxes smaller than this cannot hold a clean sky patch.
BOX_MIN = 16
# A box whose sigma-clipped sky is below this (ADU) carries no usable
# photon statistics.
MIN_LEVEL_ADU = 100.0
# The clip around each box's median, in robust sigmas. Tight on purpose:
# a sky box is a sky box, and the wings of a bright thing that only one
# frame carries inflate the variance (and would bias the gain low).
_CLIP_SIGMA = 3.0
# At least this share of a box must survive the clip for the box to be a
# sky box (a star filling the box is not).
_MIN_KEEP = 0.95
# And no more than this share may have been rejected: a box that needed a
# lot of clipping is not clean sky either.
_MAX_REJECT = 0.02
# Below this relative spread of levels (p90 - p10 over the median) the
# intercept of the fit is meaningless: the gain is fitted through the
# origin and the read noise is left unknown.
_MIN_LEVEL_SPREAD = 0.15
# Exposures closer than this (relative) are the same exposure.
_SAME_EXPOSURE = 1e-3
# Two gains "agree" when neither is more than this factor times the other
# (used only to decide whether the header's claim and the measurement of
# the very frames are the same number, or the header is a placeholder).
_AGREE_FACTOR = 1.5


def _finite(data):
    # @return: the array as float64 without NaN/inf poisoning the stats
    arr = np.asarray(data, dtype=np.float64)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def frame_boxes(f1, f2, box=64, clip=_CLIP_SIGMA, min_keep=_MIN_KEEP,
                max_reject=_MAX_REJECT, level_min=MIN_LEVEL_ADU,
                level_max=None):
    # The (level, variance) points of one pair of frames at the same
    # exposure: for every box the robust sky level in ADU and the variance
    # of F1 - F2 inside it.
    #
    # The difference kills the structures (the field, the vignetting, a
    # hot column), and the robust clip kills the stars, so what is left in
    # a box is the photon noise of the sky plus the read noise.
    #
    # @args: f1, f2 - 2D arrays in ADU (same shape, same exposure),
    #        box - box side in pixels, clip - robust sigmas kept,
    #        min_keep - share of the box that must survive,
    #        level_min/level_max - the sky levels accepted (ADU)
    # @return: {"level": array, "var": array, "n_boxes": int,
    #          "n_kept": int, "shape": (h, w)}
    a = _finite(f1)
    b = _finite(f2)
    if a.shape != b.shape:
        raise ValueError("the two frames must have the same shape")
    h, w = a.shape
    box = int(max(BOX_MIN, box))
    diff = a - b
    levels, variances = [], []
    n_boxes = 0
    level_max = float(level_max) if level_max else None
    for y0 in range(0, h - box + 1, box):
        for x0 in range(0, w - box + 1, box):
            n_boxes += 1
            sub = diff[y0:y0 + box, x0:x0 + box]
            med = float(np.median(sub))
            mad = float(outliers.scaled_mad(sub, centre=med))
            if mad <= 0.0:
                continue
            keep = np.abs(sub - med) <= clip * mad
            rejected = 1.0 - float(keep.sum()) / float(sub.size)
            if float(keep.sum()) < min_keep * sub.size:
                continue
            if rejected > max_reject:
                continue
            level = float(np.mean((a[y0:y0 + box, x0:x0 + box][keep]
                                   + b[y0:y0 + box, x0:x0 + box][keep])
                                  / 2.0))
            if not math.isfinite(level) or level < level_min:
                continue
            if level_max is not None and level > level_max:
                continue
            var = float(np.var(sub[keep], ddof=1))
            if not math.isfinite(var) or var <= 0.0:
                continue
            levels.append(level)
            variances.append(var)
    return {"level": np.asarray(levels, dtype=np.float64),
            "var": np.asarray(variances, dtype=np.float64),
            "n_boxes": n_boxes, "n_kept": len(levels),
            "shape": (h, w)}


def fit_pair(points, intercept=True):
    # Fit var = a * level + b over the boxes of one or more pairs, by
    # least squares, and turn the line into gain and read noise:
    #
    #   var(F1 - F2) = 2 * level / g + 2 * ron^2 / g^2
    #   a = 2 / g          -> g = 2 / a
    #   b = 2 * ron^2 / g^2 -> ron = sqrt(2 b) / a
    #
    # With intercept=False the line goes through the origin (b = 0), which
    # is what a single narrow sky level can honestly support: the gain
    # comes out, the read noise does not.
    #
    # @args: points - [{"level", "var"}] concatenated boxes (fit_pair
    #        accepts a single frame_boxes dict too), intercept - also fit
    #        the constant term (the read noise)
    # @return: {"gain", "ron", "gain_err", "ron_err", "slope", "intercept",
    #          "n_points", "level_spread", "intercept_used", "notes"}
    notes = []
    if isinstance(points, dict):
        points = [points]
    pairs = [p for p in points if len(np.asarray(p.get("level", [])))]
    levels = np.concatenate([np.asarray(p["level"], dtype=np.float64)
                             for p in pairs]) if pairs else np.empty(0)
    variances = np.concatenate([np.asarray(p["var"], dtype=np.float64)
                                for p in pairs]) if pairs else np.empty(0)
    out = {"gain": None, "ron": None, "gain_err": None, "ron_err": None,
           "slope": None, "intercept": None, "n_points": int(levels.size),
           "n_boxes": int(sum(int(p.get("n_boxes") or 0) for p in points)),
           "n_kept": int(sum(int(p.get("n_kept") or 0) for p in points)),
           "level_spread": None, "intercept_used": False, "notes": notes}
    if levels.size < 8:
        notes.append({"es": "Muy pocas cajas de cielo limpias ({}): no se "
                            "puede medir la ganancia".format(int(levels.size)),
                      "en": "Too few clean sky boxes ({}): the gain cannot "
                            "be measured".format(int(levels.size))})
        return out
    med = float(np.median(levels))
    spread = ((float(np.percentile(levels, 90))
               - float(np.percentile(levels, 10))) / med) if med > 0 else 0.0
    out["level_spread"] = spread
    use_intercept = bool(intercept) and spread >= _MIN_LEVEL_SPREAD
    if intercept and not use_intercept:
        notes.append({
            "es": "El nivel de cielo apenas cambia dentro de las tomas "
                  "({:.0%}): se mide la ganancia sin término constante, "
                  "así que el ruido de lectura se queda desconocido. "
                  "Añade un par a otra exposición (o crepúsculo frente a "
                  "noche) para medirlo".format(spread),
            "en": "The sky level hardly changes across the frames ({:.0%}): "
                  "the gain is measured without a constant term, so the "
                  "read noise stays unknown. Add a pair at another exposure "
                  "(or twilight against night) to measure it".format(spread)})
    # weighted-free least squares (the boxes are all equally long)
    if use_intercept:
        design = np.column_stack([levels, np.ones_like(levels)])
    else:
        design = levels[:, None]
    coef, *_ = np.linalg.lstsq(design, variances, rcond=None)
    slope = float(coef[0])
    b = float(coef[1]) if use_intercept else 0.0
    out["slope"] = slope
    out["intercept"] = b if use_intercept else None
    out["intercept_used"] = use_intercept
    if not math.isfinite(slope) or slope <= 0.0:
        notes.append({"es": "El ajuste no da una pendiente física: revisa "
                            "que las dos tomas tengan la misma exposición",
                      "en": "The fit gives no physical slope: check that the "
                            "two frames really share an exposure"})
        return out
    gain = 2.0 / slope
    # the standard error of the slope, from the residuals of the fit
    resid = variances - design @ coef
    dof = max(1, levels.size - (2 if use_intercept else 1))
    s2 = float(np.sum(np.square(resid)) / dof)
    xtx = float(np.sum(np.square(levels - (float(np.mean(levels))
                                           if use_intercept else 0.0))))
    slope_err = math.sqrt(s2 / xtx) if xtx > 0 else 0.0
    out["gain"] = gain
    out["gain_err"] = abs(2.0 / slope ** 2) * slope_err if slope > 0 else None
    if gain < GAIN_MIN or gain > GAIN_MAX:
        notes.append({
            "es": "La ganancia medida ({:.3g} e-/ADU) se sale del rango "
                  "razonable: se descarta (¿tomas saturadas, un flat mal "
                  "aplicado, o dos exposiciones distintas?)".format(gain),
            "en": "The measured gain ({:.3g} e-/ADU) is out of the sensible "
                  "range: it is dropped (saturated frames, a bad flat, or "
                  "two different exposures?)".format(gain)})
        out["gain"] = None
        return out
    if use_intercept and b > 0.0:
        ron = math.sqrt(2.0 * b) / slope
        if RON_MIN <= ron <= RON_MAX:
            out["ron"] = ron
            out["ron_err"] = ron * (slope_err / slope) if slope else None
        else:
            notes.append({
                "es": "El término constante da un ruido de lectura de "
                      "{:.3g} e-, fuera de rango: no se usa".format(ron),
                "en": "The constant term gives a read noise of {:.3g} e-, "
                      "out of range: it is not used".format(ron)})
    elif use_intercept:
        notes.append({
            "es": "El término constante sale negativo (el nivel de cielo no "
                  "llega a separar el ruido de lectura): se queda "
                  "desconocido",
            "en": "The constant term comes out negative (the sky levels do "
                  "not separate the read noise): it stays unknown"})
    return out


def header_numbers(header):
    # The gain and the read noise written in a FITS header, under any of
    # the names cameras actually use. Thins to core/photometry.
    # @args: header - the header dict from core/fits_io (or None)
    # @return: {"gain", "ron"} with None for every absent or non-numeric key
    from . import photometry
    return photometry.header_instrument(header)


def same_exposure(header_a, header_b):
    # @args: header_a, header_b - two FITS headers
    # @return: True when both carry an exposure and they match
    ea = header_numbers(header_a)
    eb = header_numbers(header_b)
    return _exposures_match(ea, eb)


def _exposures_match(a, b):
    # @args: a, b - photometry.header_instrument dicts
    # @return: True when both exposures exist and agree
    ta, tb = a.get("exptime"), b.get("exptime")
    if not ta or not tb or ta <= 0 or tb <= 0:
        return False
    return abs(ta - tb) <= _SAME_EXPOSURE * max(ta, tb)


def estimate_from_frames(f1, f2, box=64, level_max=None):
    # The whole estimate from one pair of already-loaded frames, when
    # nothing better (the settings, the header) is known.
    # @args: f1, f2 - 2D ADU arrays at the same exposure, box - box side,
    #        level_max - ceiling of accepted sky levels (ADU)
    # @return: the fit_pair block, "source"="frames"
    out = fit_pair(frame_boxes(f1, f2, box=box, level_max=level_max))
    out["source"] = "frames"
    return out


def estimate_from_paths(paths, box=64, max_scan=8, level_max=None):
    # Find two frames that really share an exposure inside a series, read
    # them and measure. Only the headers of the first `max_scan` files are
    # touched until a pair shows up, then two frames are read once.
    # @args: paths - FITS paths in observation order, box - box side,
    #        max_scan - files to inspect for the pair, level_max - ceiling
    # @return: the fit_pair block (or None when no pair was found)
    from . import fits_io
    seen = []
    for path in list(paths)[:max(2, int(max_scan))]:
        try:
            header = fits_io.read_header(path)
        except fits_io.FitsError:
            continue
        seen.append((str(path), header))
        if len(seen) < 2:
            continue
        for i in range(len(seen) - 1):
            for j in range(i + 1, len(seen)):
                if not same_exposure(seen[i][1], seen[j][1]):
                    continue
                try:
                    _ha, a = fits_io.read_fits(seen[i][0])
                    _hb, b = fits_io.read_fits(seen[j][0])
                except fits_io.FitsError:
                    continue
                out = estimate_from_frames(a, b, box=box,
                                           level_max=level_max)
                out["pair"] = (seen[i][0], seen[j][0])
                return out
    return None


def gains_agree(a, b, factor=_AGREE_FACTOR):
    # @args: a, b - two gains in e-/ADU, factor - how far apart they may be
    # @return: True when neither is more than `factor` times the other
    # A measurement carries its own few-percent bias, so an exact match
    # would cry wolf; a placeholder that is off by a factor is caught.
    if a is None or b is None or a <= 0.0 or b <= 0.0:
        return False
    return max(a, b) / min(a, b) <= factor


def _disagreement_note(head_gain, est_gain):
    # @return: the bilingual note for a header that does not match the
    #          measurement of the very frames being measured
    return {
        "es": ("La cabecera del FITS dice una ganancia de {:.3g} e-/ADU y "
               "tus tomas dicen {:.3g} e-/ADU: uso la de tus tomas. La "
               "tarjeta suele ser el ajuste de la cámara o un valor de "
               "relleno, y con ella el error de la medida sale mal."
               ).format(float(head_gain), float(est_gain)),
        "en": ("The FITS header claims a gain of {:.3g} e-/ADU and your "
               "frames say {:.3g} e-/ADU: I use the one from your frames. "
               "The card is usually the camera setting or a placeholder, "
               "and with it the measurement's error comes out wrong."
               ).format(float(head_gain), float(est_gain))}


def resolve(settings_gain=None, settings_ron=None, header=None,
            points=None, estimate=None):
    # The priority chain of the working gain, resolved one number at a
    # time: what the observer set in Ajustes wins (it is a decision), then
    # WHAT THE FRAMES THEMSELVES SAY (a measurement of the data in hand),
    # and only then what the frame header carries.
    #
    # THE MEASUREMENT BEATS THE HEADER (revision, 2026-10-08). The header
    # used to win, on the reasoning that it is "a fact of the camera". It
    # is not: it can carry the camera's gain SETTING (a small integer, not
    # an e-/ADU figure) or a placeholder the capture software writes when
    # it does not really know. Measured on the author's own QHY42Pro
    # frames: GAIN = 5, EGAIN = 1.0, and the real conversion gain was
    # 0.11 e-/ADU. Trusting the card under-reported every error bar by a
    # factor of three, and the check star's semaphore (2.5 sigma) was
    # never told. When the header and the measurement disagree, the note
    # says so.
    #
    # When the gain comes from the frames, the read noise of the same fit
    # rides along with it. If none of the three exists the answer is
    # "there is no gain", and the caller says so instead of guessing.
    # @args: settings_gain/settings_ron - the Ajustes values (e-/ADU, e-),
    #        header - the header of the reference frame, points - boxes
    #        from frame_boxes (fitted here), estimate - an already computed
    #        gain block
    # @return: {"gain", "ron", "source", "gain_err", "ron_err", "notes"}
    out = {"gain": None, "ron": None, "source": None, "gain_err": None,
           "ron_err": None, "notes": []}
    if estimate is None and points is not None:
        estimate = fit_pair(points)
    est_gain = estimate.get("gain") if estimate else None
    head = header_numbers(header) if header is not None else {}
    if settings_gain is not None:
        out["gain"], out["source"] = float(settings_gain), "settings"
    elif est_gain is not None:
        out["gain"], out["source"] = float(est_gain), "frames"
        out["gain_err"] = estimate.get("gain_err")
        out["notes"] = list(estimate.get("notes") or [])
        if head.get("gain") is not None \
                and not gains_agree(float(head["gain"]), float(est_gain)):
            out["notes"].append(_disagreement_note(head["gain"], est_gain))
    elif head.get("gain") is not None:
        out["gain"], out["source"] = float(head["gain"]), "header"
    if settings_ron is not None:
        out["ron"] = float(settings_ron)
    elif out["source"] == "frames" and estimate.get("ron") is not None:
        out["ron"] = estimate.get("ron")
        out["ron_err"] = estimate.get("ron_err")
    elif head.get("ron") is not None:
        out["ron"] = float(head["ron"])
    return out


def source_label(source, lang="es"):
    # The origin of the gain in plain language, for the panel and the
    # run's audit trail.
    # @args: source - "settings" | "header" | "frames" | None, lang - ui
    # @return: the label
    es = {"settings": "de Ajustes", "header": "de la cabecera del FITS",
          "frames": "medida en tus propias tomas"}
    en = {"settings": "from settings", "header": "from the FITS header",
          "frames": "measured on your own frames"}
    table = es if (lang or "es") != "en" else en
    return table.get(source, "")


def summary(resolved, lang="es"):
    # The resolved gain as one plain sentence, or the warning that there
    # is none (which is the whole reason this module exists).
    # @args: resolved - the resolve() dict, lang - ui language
    # @return: {"es", "en"}
    gain = resolved.get("gain") if resolved else None
    if gain is None:
        return {"es": "Sin ganancia (ni en Ajustes ni en la cabecera, y no "
                      "se ha podido medir en las tomas): la barra de error "
                      "es la dispersión de las comparadas, no la ecuación "
                      "del CCD",
                "en": "No gain (not in settings, not in the header, and it "
                      "could not be measured on the frames): the error bar "
                      "is the scatter of the comparison stars, not the CCD "
                      "equation"}
    src = resolved.get("source")
    gtxt = "{:.3g}".format(gain)
    if resolved.get("gain_err"):
        gtxt += " ± {:.2g}".format(resolved["gain_err"])
    ron = resolved.get("ron")
    es = "Ganancia {} e-/ADU ({})".format(gtxt, source_label(src, "es"))
    en = "Gain {} e-/ADU ({})".format(gtxt, source_label(src, "en"))
    if ron is not None:
        rt = "{:.3g}".format(ron)
        if resolved.get("ron_err"):
            rt += " ± {:.2g}".format(resolved["ron_err"])
        es += ", ruido de lectura {} e-".format(rt)
        en += ", read noise {} e-".format(rt)
    return {"es": es, "en": en}
