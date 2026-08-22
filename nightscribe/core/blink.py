############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Supernova blink orchestrator module (ADR-018)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re
from pathlib import Path

import numpy as np
from PIL import Image

from . import coords, fits_io, wcs as wcs_mod
from .sources import astrometry, cutouts, rochester, simbad, tns

logger = logging.getLogger(__name__)

# Working size cap for blinking: bigger frames are downscaled (and the survey
# cutout is requested in the downscaled geometry, so alignment still holds)
WORK_MAX = 2048

# WCS-ish cards we strip from a header before merging a solved solution
_STALE_WCS = ("CRVAL", "CRPIX", "CTYPE", "CUNIT", "CD", "PC", "CDELT",
              "CROTA", "PV", "A_", "B_", "AP_", "BP_")


class BlinkError(Exception):
    # User-facing failure of the blink pipeline, with a bilingual message.
    def __init__(self, msg_es, msg_en):
        super().__init__(msg_en)
        self.messages = {"es": msg_es, "en": msg_en}


def _stage(progress, es, en):
    # Reports a pipeline stage to the caller (GUI status bar / CLI).
    if progress:
        progress({"es": es, "en": en})


def normalize_sn_name(name):
    # Normalizes a supernova designation: "2026ziz" -> "SN2026ziz",
    # "sn 2023ixf" -> "SN2023ixf", "AT2024abc" -> "AT2024abc".
    # @args: name - raw user input
    # @return: normalized name (or the stripped input if it does not parse)
    m = re.match(r"^\s*(?:(SN|AT)\s*)?(\d{4}[a-zA-Z]{1,4})\s*$",
                 name or "", re.I)
    if not m:
        return (name or "").strip()
    return (m.group(1) or "SN").upper() + m.group(2).lower()


def resolve_sn(name=None, ra=None, dec=None, progress=None):
    # Resolves the supernova position. Order (ADR-018): manual RA/Dec, then
    # TNS (freshest transients, public object page), SIMBAD, and finally the
    # Rochester recent-SN list.
    # @args: name - e.g. "2026ziz", ra, dec - optional manual degrees,
    #        progress - optional stage callback
    # @return: dict {"name", "ra", "dec"} (degrees); raises BlinkError
    if ra is not None and dec is not None:
        return {"name": normalize_sn_name(name) if name else "SN",
                "ra": float(ra), "dec": float(dec)}
    full = normalize_sn_name(name)
    if not full:
        raise BlinkError(
            "Indica el nombre de la supernova o sus coordenadas.",
            "Enter the supernova name or its coordinates.")
    _stage(progress, f"Resolviendo {full} en TNS…", f"Resolving {full} "
           "on TNS…")
    info = tns.resolve(full)
    if info:
        logger.info("%s resolved via TNS: %.6f %+.6f", full,
                    info["ra"], info["dec"])
        return {"name": full, "ra": info["ra"], "dec": info["dec"]}
    _stage(progress, f"TNS no conoce {full}; probando SIMBAD…",
           f"TNS does not know {full}; trying SIMBAD…")
    info = simbad.query_id(full)
    if info and info.get("ra") and info.get("dec"):
        return {"name": full,
                "ra": coords.ra_hms_to_deg(info["ra"]),
                "dec": coords.dec_dms_to_deg(info["dec"])}
    # very fresh SNe may only be on the Rochester list so far
    short = re.sub(r"^(SN|AT)", "", full).lower()
    for sn in rochester.latest_sne(limit_mag=25.0):
        if sn["name"].lower() == short:
            return {"name": full,
                    "ra": coords.ra_hms_to_deg(sn["ra"]),
                    "dec": coords.dec_dms_to_deg(sn["dec"])}
    raise BlinkError(
        f"No se encontraron coordenadas para «{name}» (TNS, SIMBAD ni "
        "Rochester). Introdúcelas a mano (RA/Dec en grados).",
        f"No coordinates found for '{name}' (TNS, SIMBAD or Rochester). "
        "Please enter them manually (RA/Dec in degrees).")


def merge_solved_wcs(header, cards):
    # Merges an astrometry.net solution into the user's header: stale WCS
    # cards are dropped first so flavours never mix (CD vs CDELT+PC...).
    # NAXIS stays from the user image (the wcs.fits carries NAXIS=0).
    # @args: header - original header dict, cards - solved WCS cards
    # @return: new header dict with the solved WCS in place
    out = {k: v for k, v in header.items()
           if not any(k.startswith(p) for p in _STALE_WCS)}
    out.update(cards)
    return out


def load_user_image(path, work=WORK_MAX, progress=None):
    # Reads the user's FITS and its WCS, downscaling to the working size.
    # No WCS? Blind-solve with Astrometry.net when an API key is configured
    # (the user is told either way — ADR-018).
    # @args: path - FITS file, work - maximum dimension in pixels,
    #        progress - optional stage callback
    # @return: dict {"data", "wcs", "shape", "factor"}; raises BlinkError
    try:
        header, data = fits_io.read_fits(path)
    except fits_io.FitsError as err:
        raise BlinkError(
            f"No se pudo leer el FITS: {err}",
            f"Could not read the FITS file: {err}") from err
    wcs = wcs_mod.Wcs.from_header(header)
    if wcs is None:
        from ..config import config
        if not (config.get("astrometry_key") or "").strip():
            raise BlinkError(
                "La imagen no tiene astrometría (WCS). Configura tu clave de "
                "API de Astrometry.net en Ajustes para resolverla "
                "automáticamente, o resuélvela con ASTAP, NINA, Ekos o "
                "PixInsight y guárdala de nuevo.",
                "The image has no astrometry (WCS). Set your Astrometry.net "
                "API key in Settings to solve it automatically, or solve it "
                "with ASTAP, NINA, Ekos or PixInsight and save it again.")
        _stage(progress, "Sin WCS: subiendo a Astrometry.net para resolver "
               "la astrometría (puede tardar unos minutos)…",
               "No WCS: uploading to Astrometry.net for blind solving "
               "(this may take a few minutes)…")
        cards = astrometry.solve(
            Path(path),
            progress=lambda s: _stage(progress, f"Astrometry.net: {s}",
                                      f"Astrometry.net: {s}"))
        if not cards:
            raise BlinkError(
                "Astrometry.net no pudo resolver la imagen (o está sin "
                "conexión). Revisa la clave en Ajustes o resuélvela con "
                "ASTAP/NINA/Ekos/PixInsight.",
                "Astrometry.net could not solve the image (or is offline). "
                "Check the key in Settings or solve it with "
                "ASTAP/NINA/Ekos/PixInsight.")
        _stage(progress, "Astrometría resuelta por Astrometry.net ✔",
               "Astrometry solved by Astrometry.net ✔")
        wcs = wcs_mod.Wcs.from_header(merge_solved_wcs(header, cards))
        if wcs is None:
            raise BlinkError(
                "La solución de Astrometry.net no es usable (WCS no TAN).",
                "The Astrometry.net solution is not usable (non-TAN WCS).")
    flipped = False
    if wcs.is_mirrored():
        # mirrored solve (det > 0): no rotation matches it to a survey —
        # flip horizontally so the pair aligns (ADR-018)
        data = np.ascontiguousarray(data[:, ::-1])
        wcs = wcs.flipped_x()
        flipped = True
        logger.info("user image WCS is mirrored; flipped horizontally")
    factor = 1.0
    if max(data.shape) > work:
        factor = max(data.shape) / work
        new_w = max(1, round(data.shape[1] / factor))
        new_h = max(1, round(data.shape[0] / factor))
        # NaNs are rare in camera data; zero them so PIL can resample
        img = Image.fromarray(np.nan_to_num(data, nan=0.0), mode="F")
        img = img.resize((new_w, new_h), Image.LANCZOS)
        data = np.asarray(img, dtype=np.float32)
        wcs = wcs.scaled(factor)
        logger.info("downscaled user image x%.2f -> %dx%d", factor,
                    new_w, new_h)
    return {"data": data, "wcs": wcs, "shape": data.shape, "factor": factor,
            "flipped": flipped}


def prepare_pair(image_path, sn_name=None, ra=None, dec=None, work=WORK_MAX,
                 progress=None):
    # Full blink pipeline: resolve the SN, read (and if needed solve) the
    # user's FITS, and fetch a PanSTARRS DR1 g cutout with the same
    # centre/scale/rotation (ADR-018).
    # @args: image_path - user FITS, sn_name - e.g. "2026ziz",
    #        ra, dec - optional manual position (degrees), work - size cap,
    #        progress - optional stage callback
    # @return: dict {"ref", "obs", "sn_xy", "name", "ra", "dec",
    #                "ref_label", "wcs", "image_path"}; raises BlinkError
    user = load_user_image(image_path, work, progress)
    target = resolve_sn(sn_name, ra, dec, progress)
    wcs = user["wcs"]
    cra, cdec = wcs.center()
    scale = wcs.pixel_scale()
    rotation = wcs.rotation()
    logger.info("user image: centre %.5f %+.5f, %.3f\"/px, rotation %.1f deg",
                cra, cdec, scale, rotation)
    _stage(progress, "Descargando la referencia del survey (PanSTARRS DR1 g)…",
           "Downloading the survey reference (PanSTARRS DR1 g)…")
    ref_path, ref_label = cutouts.ps1g_matched(cra, cdec, wcs.naxis1,
                                               wcs.naxis2, scale, rotation)
    if ref_path is None:
        raise BlinkError(
            "No se pudo obtener la imagen de referencia (PanSTARRS/DSS).",
            "Could not fetch the reference image (PanSTARRS/DSS).")
    _, ref = fits_io.read_fits(ref_path)
    if abs(ref.shape[1] - wcs.naxis1) > 2 or abs(ref.shape[0] - wcs.naxis2) > 2:
        logger.warning("survey cutout shape %s differs from user %s",
                       ref.shape, user["shape"])
    sx, sy = wcs.sky_to_pixel(target["ra"], target["dec"])
    if not (0 <= sx < wcs.naxis1 and 0 <= sy < wcs.naxis2):
        logger.info("SN position (%.1f, %.1f) falls outside the frame", sx, sy)
    return {"ref": ref, "obs": user["data"], "sn_xy": (sx, sy),
            "name": target["name"], "ra": target["ra"], "dec": target["dec"],
            "ref_label": ref_label, "wcs": wcs, "image_path": str(image_path),
            "flipped": user["flipped"]}
