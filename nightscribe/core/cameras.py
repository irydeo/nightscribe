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

"""Camera presets for the photometric profile (data only).

Each preset carries the *datasheet* facts of a sensor so the profile starts
somewhere sensible: pixel size, full well, read noise, dark current (with
the temperature it was quoted at) and the exposure range, plus an exposure
**regime** (``short`` for the extremely sensitive sCMOS that must group many
short frames, ``normal`` for the classic long-exposure cameras).

The **linearity limit** and the **working maximum exposure** are NOT
datasheet properties: they depend on the gain and the individual unit, so
the preset only offers a *suggested* linearity to be measured (``suggested``
flag), and the user overrides it. This mirrors the author's own lesson on
the QHY42Pro: never reuse another observer's gain/offset values.

Sources are the manufacturers' pages (QHYCCD, ZWO, Gpixel, ON Semi/Truesense)
and, for the GSENSE400, the Irydeo QHY42Pro article (lineality measured at
gain 6, offset 60).
"""

# regime: "short" -> few-second exposures, group to win (sCMOS);
#         "normal" -> long exposures are fine (IMX deep-well, classic CCD).

PRESETS = [
    {
        "key": "gsense400",
        "sensor": "Gpixel GSENSE400 (sCMOS)",
        "cameras": "QHY42Pro",
        "pixel_um": 11.0,
        "full_well_e": 53000.0,
        "read_noise_e": 1.7,
        "dark_current_e_s": 2.2,
        "dark_temp_c": -20.0,
        "exp_min_s": 20e-6, "exp_max_s": 300.0,
        "regime": "short",
        # measured on a real unit at gain 6 / offset 60 (Irydeo article)
        "linearity_adu": 53000.0,
        "linearity_note": "measured at gain 6, offset 60",
        "source": "Gpixel datasheet + irydeo.com QHY42Pro article",
    },
    {
        "key": "imx455",
        "sensor": "Sony IMX455 (BSI, 16-bit)",
        "cameras": "QHY600, ASI6200",
        "pixel_um": 3.76,
        "full_well_e": 51000.0,        # 80 ke- in extended full-well mode
        "read_noise_e": 1.1,           # high-gain mode
        "dark_current_e_s": 0.0022,
        "dark_temp_c": -20.0,
        "exp_min_s": 40e-6, "exp_max_s": 3600.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "QHYCCD / ZWO product pages",
    },
    {
        "key": "imx571",
        "sensor": "Sony IMX571 (BSI, 16-bit)",
        "cameras": "QHY268, ASI2600",
        "pixel_um": 3.76,
        "full_well_e": 51000.0,        # 73-80 ke- in extended full-well mode
        "read_noise_e": 1.0,
        "dark_current_e_s": 0.0005,
        "dark_temp_c": -20.0,
        "exp_min_s": 30e-6, "exp_max_s": 3600.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "QHYCCD / ZWO product pages",
    },
    {
        "key": "imx533",
        "sensor": "Sony IMX533 (BSI, 16-bit)",
        "cameras": "QHY533, ASI533",
        "pixel_um": 3.76,
        "full_well_e": 50000.0,
        "read_noise_e": 1.0,
        "dark_current_e_s": None,      # very low; measure if it matters
        "dark_temp_c": None,
        "exp_min_s": 32e-6, "exp_max_s": 2000.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "QHYCCD / ZWO product pages",
    },
    {
        "key": "imx294",
        "sensor": "Sony IMX294 (FSI, 14-bit)",
        "cameras": "QHY294, ASI294",
        "pixel_um": 4.63,
        "full_well_e": 66000.0,
        "read_noise_e": 1.2,
        "dark_current_e_s": None,      # FSI: higher, temperature sensitive
        "dark_temp_c": None,
        "exp_min_s": 32e-6, "exp_max_s": 2000.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "QHYCCD / ZWO product pages",
    },
    {
        "key": "imx183",
        "sensor": "Sony IMX183 (FSI, 12-bit)",
        "cameras": "QHY183, ASI183",
        "pixel_um": 2.4,
        "full_well_e": 15000.0,
        "read_noise_e": 1.6,
        "dark_current_e_s": None,
        "dark_temp_c": None,
        "exp_min_s": 32e-6, "exp_max_s": 2000.0,
        "regime": "normal",
        "linearity_adu": 50000.0,      # small full well: measure, likely lower
        "linearity_note": "small full well: the linear limit may be lower; "
                          "measure yours",
        "source": "QHYCCD / ZWO product pages",
    },
    {
        "key": "kaf8300",
        "sensor": "Kodak/Truesense KAF-8300 (CCD, 16-bit)",
        "cameras": "SBIG STF-8300, Atik 383L+",
        "pixel_um": 5.4,
        "full_well_e": 25500.0,
        "read_noise_e": 8.0,
        "dark_current_e_s": None,      # strongly temperature dependent
        "dark_temp_c": None,
        "exp_min_s": 1.0, "exp_max_s": 3600.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "ABG/NABG differ; measure yours",
        "source": "ON Semi / Truesense datasheet",
    },
    {
        "key": "kaf16803",
        "sensor": "Kodak/Truesense KAF-16803 (CCD, 16-bit)",
        "cameras": "SBIG STX-16803, FLI PL16803",
        "pixel_um": 9.0,
        "full_well_e": 100000.0,
        "read_noise_e": 9.0,
        "dark_current_e_s": None,
        "dark_temp_c": None,
        "exp_min_s": 1.0, "exp_max_s": 3600.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "ON Semi / Truesense datasheet",
    },
    {
        "key": "kaf09000",
        "sensor": "Kodak/Truesense KAF-09000 (CCD, 16-bit)",
        "cameras": "FLI PL09000",
        "pixel_um": 12.0,
        "full_well_e": 110000.0,
        "read_noise_e": 11.0,
        "dark_current_e_s": None,
        "dark_temp_c": None,
        "exp_min_s": 1.0, "exp_max_s": 3600.0,
        "regime": "normal",
        "linearity_adu": 50000.0,
        "linearity_note": "suggested starting point; measure yours",
        "source": "ON Semi / Truesense datasheet",
    },
]


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
    # @return: the combo label, e.g. "Sony IMX455 (BSI, 16-bit) - QHY600, ASI6200"
    return f"{p['sensor']} - {p['cameras']}"


def full_well_adu(p, gain_e_per_adu):
    # The full well expressed in ADU for a given system gain: the hard
    # ceiling a pixel can hold before the amplifier clips.
    # @args: p - preset, gain_e_per_adu - e-/ADU (None -> None)
    # @return: ADU (float) or None
    if not p or not gain_e_per_adu or gain_e_per_adu <= 0 \
            or p.get("full_well_e") is None:
        return None
    return float(p["full_well_e"]) / float(gain_e_per_adu)
