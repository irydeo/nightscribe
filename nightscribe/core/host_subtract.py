############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Host-galaxy subtraction module (ADR-018, H2b)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Host-galaxy subtraction for supernovae on galactic cores (H2b).

The blink asks CDS hips2fits for the survey cutout at the frame's own
centre, scale and rotation (ADR-018), so the two images SHOULD land on top
of each other "by construction". They do not, quite: the frame's WCS is
only as good as its solution (the blink ignores the SIP distortion terms),
hips2fits rounds the field, and the survey is a stack of another epoch. The
dominant term is a pixel-SCALE mismatch of a fraction of a percent between
the WCS scale the cutout was requested at and the frame's real scale: the
stars pair but land further and further off with distance from the centre
(measured on a real frame: 0.15 %, about 1.5 px at the edge). A rigid
(translation + rotation) fit cannot remove that, and it is left as a
bright/dark DIPOLE at every star: the black dots the observer sees, and a
bias in the measurement when a neighbour's dark lobe falls in the target's
sky.

So the reference is not trusted to the WCS: it is REGISTERED to the frame
on the stars the two images share as a SIMILARITY (scale + rotation +
translation, core/register), then scaled by the comparison stars (their
flux ratio absorbs the filter difference between the survey's g and the
observer's band) and subtracted.

The survey also carries MASKED pixels (PanSTARRS saturations, bleed
columns) that arrive as NaN. Subtracted as-is they paint solid black holes
(any display maps NaN to zero) and can poison an aperture. Here they are
filled only so the resampling can cross them, and then excluded again: a
measurement never reads a pixel the survey never had.
"""

import logging

import numpy as np

from . import difference, photometry, register

logger = logging.getLogger(__name__)

# Fewer comparison stars than this and the flux ratio cannot be trusted:
# the caller reports "no usable comparison star" (the same floor the tab
# used before this module existed).
MIN_COMPS = 2


def _fill_invalid(ref):
    # The reference without NaN, and the mask of what was filled.
    #
    # The survey's masked pixels are filled with the sky's own median: the
    # exact value does not matter, because every filled pixel is excluded
    # from the difference again below. The point is only that a bilinear
    # resampling crossing a NaN would spread it over its whole 2x2
    # neighbourhood, so the fill keeps the warp finite and the mask (warped
    # separately) puts the holes back where they belong.
    # @args: ref - the survey reference (2D float array)
    # @return: (filled, valid): the reference with no NaN and the boolean
    #          mask that is True where the survey had real data
    valid = np.isfinite(ref)
    if valid.all():
        return ref, valid
    filled = np.array(ref, dtype=np.float64, copy=True)
    sky = float(np.median(ref[valid])) if valid.any() else 0.0
    filled[~valid] = sky
    return filled, valid


def align_reference(obs, ref, allow_rotation=True):
    # Registers the survey reference onto the observation's pixel grid.
    #
    # The transform is estimated from the stars the two share
    # (core/register): a translation first, a rotation only when it really
    # removes residual. The reference is then resampled (the observer's own
    # pixels are never touched, ADR-018) and its validity mask is carried
    # across so the difference can put the survey's holes back.
    # @args: obs, ref - the observed frame and the survey cutout (same
    #        shape), allow_rotation - let the fit rotate, not only shift
    # @return: (warped, valid, transform): the aligned reference, the
    #          boolean mask of pixels that carry real survey data, and the
    #          register.estimate_transform report
    filled, survey_ok = _fill_invalid(ref)
    # allow_scale: the survey cutout is asked for at the frame WCS's pixel
    # scale, and that scale is off by a fraction of a percent, so a rigid
    # (translation + rotation) fit leaves the stars misaligned further and
    # further from the centre. The similarity absorbs it (see
    # register._fit_similarity).
    tr = register.estimate_transform(obs, filled, allow_rotation=allow_rotation,
                                     allow_scale=True)
    scale = float(tr.get("scale") or 1.0)
    warped = register.apply_transform(filled, tr["angle"], tr["dx"], tr["dy"],
                                      scale=scale)
    valid = register.warp_mask(ref.shape, tr["angle"], tr["dx"], tr["dy"],
                               scale=scale)
    # the survey's own holes, warped with the same transform: an output
    # pixel whose bilinear read touched a masked source pixel is invalid
    mask = register.apply_transform(survey_ok.astype(np.float64),
                                    tr["angle"], tr["dx"], tr["dy"],
                                    scale=scale)
    valid &= mask > 0.0
    return warped, valid, tr


def _psf_stars(obs, comp_xy, max_n=80):
    # The stars the PSF match is fitted to: bright but unsaturated, spread
    # over the frame (the comparison stars are added in, since the caller
    # already trusts them).
    #
    # Saturated stars are excluded on purpose: their cores are a flat
    # plateau, which carries no point-spread information and would drag the
    # fit toward a broad, wrong kernel.
    # @args: obs - the observed frame, comp_xy - the comps to keep, max_n -
    #        cap on the number of stars
    # @return: a list of (x, y) positions
    stars = [(float(x), float(y)) for x, y in comp_xy]
    finite = obs[np.isfinite(obs)]
    ceil = 0.9 * float(np.max(finite)) if finite.size else None
    stars.extend(difference.find_stars(obs, max_n=max_n, ceil=ceil))
    return stars[:max_n]


def subtract(obs, ref, comp_xy, fwhm_px=None, allow_rotation=True):
    # The whole H2b step: align the reference, match its point spread to the
    # frame's, scale it by the comparison stars so they vanish, and subtract.
    # @args: obs - the observed work frame, ref - the survey cutout (same
    #        shape), comp_xy - the comparison stars' pixel positions in the
    #        observation, fwhm_px - the frame's seeing (the registration
    #        quality gate follows it), allow_rotation - see align_reference
    # @return: dict {"diff" (or None), "gain", "used", "transform",
    #          "trusted", "n_stars", "rms_px", "masked", "psf"}
    warped, valid, tr = align_reference(obs, ref, allow_rotation=allow_rotation)
    # PSF matching (ADR-073): the survey's stars are sharper than the
    # frame's, so the reference is broadened to match before it is
    # subtracted. Without this every star keeps a dark core and a bright
    # ring, which is what contaminates the sky around a faint target.
    psf = difference.match(obs, warped, _psf_stars(obs, comp_xy))
    warped = psf["ref"]
    logger.info("host subtraction: angle=%.4f dx=%.2f dy=%.2f scale=%.5f "
                "rms_px=%s n=%d source=%s | psf=%s sigma=%.2f "
                "residual=%s",
                tr.get("angle", 0.0), tr.get("dx", 0.0), tr.get("dy", 0.0),
                tr.get("scale") or 1.0, tr.get("rms_px"), tr.get("n") or 0,
                tr.get("source"), psf["kind"], psf["sigma"],
                (round(psf["residual"], 3)
                 if psf.get("residual") is not None else None))
    num = den = 0.0
    used = 0
    for x, y in comp_xy:
        ro = photometry.measure_point(obs, x, y)
        rr = photometry.measure_point(warped, x, y)
        if not ro["ok"] or not rr["ok"] or rr["flux"] <= 0.0:
            continue
        num += ro["flux"] * rr["flux"]
        den += rr["flux"] ** 2
        used += 1
    report = {"diff": None, "gain": None, "used": used, "transform": tr,
              "trusted": bool(register.trusted(tr, fwhm_px=fwhm_px)),
              "n_stars": int(tr.get("n") or 0),
              "rms_px": tr.get("rms_px"),
              "masked": int((~valid).sum()), "psf": psf}
    star_gain = (num / den) if (used >= MIN_COMPS and den > 0.0) else None
    # the scale that cancels the HOST is fitted on the galaxy's own bright
    # pixels: its colour differs from the stars' (ADR-073), and the star
    # scale leaves the bulge uncancelled over the target. The star gain is
    # the fallback when there is no extended host to fit.
    h_gain = difference.host_gain(obs, warped, _psf_stars(obs, comp_xy))
    report["star_gain"] = float(star_gain) if star_gain is not None else None
    report["host_gain"] = float(h_gain) if h_gain is not None else None
    gain = h_gain if h_gain is not None else star_gain
    if gain is None:
        return report
    diff = obs.astype(np.float64) - gain * warped
    # the extended host: a galaxy's bulge is smooth and has another colour
    # than the stars, so the star-based scale leaves a broad pedestal over
    # the core (ADR-073). A low-order polynomial takes it away without
    # touching the target.
    bg = difference.background(diff)
    if bg is not None:
        diff = diff - bg
    # the survey's holes are holes in the difference too: NaN is what the
    # photometry already knows to skip, and the display paints it as sky
    diff = np.where(valid, diff, np.nan)
    logger.info("host subtraction: gain=%.4f used=%d obs_med=%.0f "
                "diff_med=%.0f", gain, used, float(np.median(obs)),
                float(np.nanmedian(diff)))
    report["diff"] = diff
    report["gain"] = float(gain)
    return report
