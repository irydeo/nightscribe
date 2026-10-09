############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Camera presets (photometric camera profiles)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Camera presets for the photometric profile.

The DATA lives in a TOML file, not in this module, so a camera can be added,
fixed or removed by editing a text file. Two files are merged at load:

* the bundled catalogue, ``nightscribe/assets/cameras.toml`` (the source of
  truth, shipped with the app);
* an optional user file, ``<config>/cameras.toml`` (see ``paths.config_dir``),
  which can ADD a camera (a new ``key``), CORRECT a bundled one (same ``key``:
  the fields written there replace the bundled ones) or HIDE one (the
  top-level ``hide = ["key", ...]``).

This module keeps the LOGIC: how a preset is looked up, labelled, grouped,
turned into config keys and how the suggested linearity is derived from the
real ceilings. ``reload()`` re-reads both files and refreshes the catalogue,
so editing the user file takes effect without restarting the app; a broken
user file is reported in ``USER_ERROR`` and the last good catalogue is kept.

Each preset carries the *datasheet* facts of a sensor so the profile starts
somewhere sensible: pixel size, sensor size and resolution, ADC bit depth,
full well, read noise (with the gain mode it belongs to), dark current (with
the temperature it was quoted at) and the exposure range, plus an exposure
**regime** (``short`` for the extremely sensitive sCMOS that must group many
short frames, ``normal`` for the classic long-exposure cameras).

The **linearity limit** and the **working maximum exposure** are NOT
datasheet properties: they depend on the gain and the individual unit, so the
preset carries only a *linearity fraction* (the fraction of the lesser of the
full well and the ADC ceiling where the sensor is still linear) and the user
overrides the number. This mirrors the author's own lesson on the QHY42Pro:
never reuse another observer's gain/offset values.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Bundled catalogue, next to the other assets (the PyInstaller spec bundles
# nightscribe/assets/* whole, so this file travels with the app).
_BUNDLED = Path(__file__).resolve().parent.parent / "assets" / "cameras.toml"


def _user_path():
    # @return: the optional user catalogue (adds/corrects/hides cameras),
    #          in the app's config folder next to nightscribe.json
    from .. import paths
    return paths.config_dir() / "cameras.toml"


def _read(path):
    # @args: path - a .toml file
    # @return: the parsed dict (tomllib is stdlib; binary mode is required)
    import tomllib
    with open(path, "rb") as fh:
        return tomllib.load(fh)


# The fields every preset must carry, by kind. Anything the datasheet does
# not publish (a dark current, a note) is simply omitted and read as None.
_STR_FIELDS = ("key", "family", "sensor", "cameras", "regime")
_NUM_FIELDS = ("pixel_um", "sensor_w_mm", "sensor_h_mm", "full_well_e",
               "read_noise_e", "exp_min_s", "exp_max_s")
_INT_FIELDS = ("resolution_w", "resolution_h", "bit_depth")


def _validate(presets, families):
    # Fail fast and by name: a typo in the file must not surface as a KeyError
    # in the middle of a dialog. Checks the shape, the uniqueness of keys and
    # aliases, the declared family, the linearity rule and the dark current's
    # temperature.
    # @args: presets - list of dicts; families - the allowed family order
    # @return: None (raises ValueError on the first problem)
    fam_set = set(families)
    keys = set()
    aliases = {}
    for p in presets:
        where = p.get("key") or "<camera without key>"
        for k in _STR_FIELDS:
            if not isinstance(p.get(k), str) or not p.get(k):
                raise ValueError(f"{where}: missing or bad {k}")
        for k in _NUM_FIELDS:
            v = p.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or v <= 0:
                raise ValueError(f"{where}: missing or bad {k}")
        for k in _INT_FIELDS:
            v = p.get(k)
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                raise ValueError(f"{where}: missing or bad {k}")
        if p["bit_depth"] not in (12, 14, 16):
            raise ValueError(f"{where}: bit_depth must be 12, 14 or 16")
        if p["regime"] not in ("short", "normal"):
            raise ValueError(f"{where}: regime must be short or normal")
        if p["family"] not in fam_set:
            raise ValueError(
                f"{where}: family {p['family']!r} is not in family_order")
        if p.get("linearity_adu") is None \
                and p.get("linearity_frac") is None:
            raise ValueError(f"{where}: needs linearity_adu or linearity_frac")
        if p.get("dark_current_e_s") is not None \
                and p.get("dark_temp_c") is None:
            raise ValueError(
                f"{where}: dark current without the temperature it was "
                f"quoted at")
        if p["key"] in keys:
            raise ValueError(f"duplicate camera key {p['key']!r}")
        keys.add(p["key"])
        for alias in (a.strip().lower() for a in p["cameras"].split(",")):
            if not alias:
                raise ValueError(f"{where}: an empty camera alias")
            if alias in aliases:
                raise ValueError(
                    f"alias {alias!r} is in {where} and in {aliases[alias]}")
            aliases[alias] = p["key"]


def _merge(bundled, bundled_families, user):
    # @args: bundled - the shipped presets; bundled_families - their order;
    #        user - the parsed user file (may be empty)
    # @return: (presets, families) with the user file applied: a new key is
    #          appended, an existing one is corrected field by field (only
    #          the fields written there change), `hide` drops keys, and any
    #          family the user brings is added to the order so a camera with
    #          its own family still shows.
    presets = [dict(p) for p in bundled]
    by_key = {p["key"]: p for p in presets}
    for u in user.get("camera", []) or []:
        key = u.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("a [[camera]] in the user file has no key")
        if key in by_key:
            by_key[key].update(u)
        else:
            presets.append(dict(u))
            by_key[key] = presets[-1]
    hidden = set(user.get("hide", []) or [])
    if hidden:
        presets = [p for p in presets if p.get("key") not in hidden]
    order = list(bundled_families)
    for fam in (user.get("family_order", []) or []):
        if fam not in order:
            order.append(fam)
    for p in presets:
        fam = p.get("family")
        if isinstance(fam, str) and fam not in order:
            order.append(fam)
    return presets, order


def reload():
    # Re-reads the bundled catalogue and the user file and refreshes PRESETS,
    # FAMILY_ORDER and USER_ERROR. Called at import and again when Settings or
    # the Welcome equipment step opens, so editing the user file takes effect
    # without restarting. A broken user file does NOT crash the app: the last
    # good catalogue stays and USER_ERROR says what happened (Settings shows
    # it), because a camera that silently does not appear is worse than an
    # error message.
    # @return: None
    global PRESETS, FAMILY_ORDER, USER_ERROR
    raw = _read(_BUNDLED)
    bundled = raw.get("camera", [])
    bundled_families = list(raw.get("family_order", []))
    _validate(bundled, bundled_families)
    presets, families = bundled, bundled_families
    USER_ERROR = None
    upath = _user_path()
    if upath.exists():
        try:
            user = _read(upath)
            merged, merged_families = _merge(bundled, bundled_families, user)
            _validate(merged, merged_families)
            presets, families = merged, merged_families
        except (OSError, ValueError) as err:
            # ValueError covers tomllib.TOMLDecodeError (it subclasses it)
            USER_ERROR = f"{upath.name}: {err}"
            logger.error("user camera catalogue ignored (%s)", err)
    PRESETS = presets
    FAMILY_ORDER = tuple(families)


def preset(key):
    # @args: key - a preset key (e.g. "imx455") or a camera alias
    # @return: the preset dict, or None
    if not key:
        return None
    want = str(key).strip().lower()
    for p in PRESETS:
        if p["key"] == want:
            return p
    for p in PRESETS:
        aliases = [a.strip().lower() for a in p["cameras"].split(",")]
        if want in aliases:
            return p
    return None


def label(p):
    # @return: the combo label, e.g.
    #          "Sony IMX455 (BSI, 16-bit) - QHY600, ASI6200, ..."
    return f"{p['sensor']} - {p['cameras']}"


def combo_entries():
    # @return: the preset combo's rows in FAMILY_ORDER, each one
    #          (text, key, is_header): a header names a sensor family and
    #          carries no key (the UI disables it so it cannot be picked);
    #          the rest are the presets themselves. A shared list so the
    #          Settings dialog and the Welcome step group the combo the
    #          same way.
    rows = []
    for family in FAMILY_ORDER:
        items = [p for p in PRESETS if p.get("family") == family]
        if not items:
            continue
        rows.append((family, None, True))
        for p in items:
            rows.append((label(p), p["key"], False))
    return rows


def full_well_adu(p, gain_e_per_adu):
    # The full well expressed in ADU for a given system gain: the hard
    # ceiling a pixel can hold before the amplifier clips.
    # @args: p - preset, gain_e_per_adu - e-/ADU (None -> None)
    # @return: ADU (float) or None
    if not p or not gain_e_per_adu or gain_e_per_adu <= 0 \
            or p.get("full_well_e") is None:
        return None
    return float(p["full_well_e"]) / float(gain_e_per_adu)


def suggested_linearity_adu(p, gain_e_per_adu=None):
    # The linearity ceiling the preset suggests, in ADU.
    #
    # Why not a flat number: linearity is where the sensor stops counting
    # photons faithfully, and that sits below the LESSER of its two ceilings,
    # the full well (at YOUR gain) and the ADC's range (2**bits - 1). A flat
    # 50000 ADU is wrong for a 12-bit sensor (its ADC tops out at 4095) and
    # for a high-gain 16-bit one (the full well, not the ADC, is the ceiling).
    # With a gain we can name the real ceiling; without one we fall back to
    # the ADC's, which is the best we can say.
    #
    # GSENSE400 is the exception: it carries an ABSOLUTE linearity_adu
    # measured on a real unit (the preset's note says so), so it is returned
    # as-is.
    # @args: p - preset; gain_e_per_adu - the system gain if known
    # @return: ADU (int) or None
    if not p:
        return None
    if p.get("linearity_adu") is not None:
        return float(p["linearity_adu"])
    frac = p.get("linearity_frac")
    if frac is None:
        return None
    bits = int(p.get("bit_depth") or 16)
    adc = float((1 << bits) - 1)
    ceiling = adc
    fw = full_well_adu(p, gain_e_per_adu) if gain_e_per_adu else None
    if fw:
        ceiling = min(fw, adc)
    return round(ceiling * float(frac))


def profile_from_preset(p, gain_e_per_adu=None):
    # The datasheet values a camera preset loads into the profile, in CONFIG
    # keys. Choosing a preset IS loading its template, so the datasheet fields
    # are written over whatever was there (the previous camera's numbers, or a
    # value typed by hand): the observer picks a camera to see THAT camera's
    # figures, and the earlier "only fill empty fields" rule left the screen
    # showing the old camera, which read as "the preset does nothing". A field
    # the datasheet does not publish is cleared (0 / None), so switching away
    # from a camera does not leave its values behind either.
    #
    # The SYSTEM GAIN is never filled: it is per unit and per gain setting, and
    # no datasheet can know it (the preset itself says so). It is only READ,
    # when given, so the suggested linearity comes from the real full well at
    # the observer's gain.
    #
    # It returns a dict instead of touching widgets so the Settings dialog and
    # the Welcome step share ONE rule (2026-10-07): two places filling the same
    # profile by hand is how they drift apart.
    # @args: p - a preset dict (None -> nothing); gain_e_per_adu - the system
    #        gain if known (for the linearity suggestion only)
    # @return: {config_key: value} to write
    if not p:
        return {}
    out = {"pixel_um": float(p["pixel_um"])}
    for key, field in (("cam_full_well_e", "full_well_e"),
                       ("ccd_read_noise", "read_noise_e")):
        if p.get(field) is not None:
            out[key] = float(p[field])
    # the dark current travels with the temperature it was quoted at, or the
    # number loses its meaning; a camera that does not publish one clears it
    out["cam_dark_current_e_s"] = (
        float(p["dark_current_e_s"])
        if p.get("dark_current_e_s") is not None else None)
    out["cam_dark_temp_c"] = (
        float(p["dark_temp_c"]) if p.get("dark_temp_c") is not None else None)
    lin = suggested_linearity_adu(p, gain_e_per_adu)
    if lin is not None:
        out["cam_linearity_adu"] = float(lin)
    # the working max exposure is a per-gain choice the preset only suggests
    # for the sCMOS that must group short frames; a classic camera means "no
    # cap" (None), so switching away from the sCMOS clears its few-second cap
    out["cam_max_exposure_s"] = (
        round(float(p["exp_max_s"]))
        if p.get("regime") == "short" and p.get("exp_max_s") else None)
    return out


# The catalogue, loaded once at import and refreshed by reload().
PRESETS = []
FAMILY_ORDER = ()
# The user file's problem, or None. Settings shows it: a camera that is there
# in the file and not in the list, in silence, is the worst outcome.
USER_ERROR = None
reload()
