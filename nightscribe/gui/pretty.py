############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - pretty proper nouns and short dates for the GUI
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Hand-picked proper nouns and short dates for the GUI.

The engines hand over lowercase keys ("ganymede", "perseids") and raw
datetimes; turning them into display text is done by hand here, because
lupdate cannot see strings built from variables — a "Ganímedes" spelled
as "ganymede".capitalize() would come out wrong in *both* languages.

These are the same tables the Sky calendar dialog shows; keeping them in
one place means the tonight chips and the calendar never disagree.
"""

# (es, en) pairs, keyed by the engine's lowercase names
PLANET_NAMES = {
    "mercury": ("Mercurio", "Mercury"), "venus": ("Venus", "Venus"),
    "mars": ("Marte", "Mars"), "jupiter": ("Júpiter", "Jupiter"),
    "saturn": ("Saturno", "Saturn"), "uranus": ("Urano", "Uranus"),
    "neptune": ("Neptuno", "Neptune"),
    # Earth is our reference planet (the 1 AU ring on the orbit charts)
    "earth": ("la Tierra", "the Earth")}
MOON_NAMES = {
    "io": ("Io", "Io"), "europa": ("Europa", "Europa"),
    "ganymede": ("Ganímedes", "Ganymede"), "callisto": ("Calisto", "Callisto"),
    "moon": ("la Luna", "the Moon")}
SOLAR_NAMES = {"sun": ("el Sol", "the Sun")}
SHOWER_NAMES = {
    "quadrantids": ("Cuadrántidas", "Quadrantids"),
    "lyrids": ("Líridas", "Lyrids"),
    "eta_aquariids": ("Eta Acuáridas", "Eta Aquariids"),
    "perseids": ("Perseidas", "Perseids"),
    "orionids": ("Oriónidas", "Orionids"),
    "leonids": ("Leónidas", "Leonids"),
    "geminids": ("Gemínidas", "Geminids"),
    "ursids": ("Úrsidas", "Ursids")}
# Short month names, because strftime("%d %b") is always English
_MONTH_ABBR = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun",
           "jul", "ago", "sep", "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")}


def name(lang, key):
    # The proper noun for an engine key, in the UI's language.
    # @args: lang - "es"|"en"; key - the engine's lowercase name
    # @return: the proper noun, or the capitalised key when unknown
    pair = (PLANET_NAMES.get(key) or MOON_NAMES.get(key)
            or SHOWER_NAMES.get(key) or SOLAR_NAMES.get(key))
    if pair is None:
        return str(key).capitalize()
    return pair[0] if lang == "es" else pair[1]


def day(lang, dt, year=False):
    # The short local-form date, "18 sep" / "18 Sep" (or + year).
    # @args: lang - "es"|"en"; dt - a datetime; year - append the year
    # @return: the localized short date string
    abbr = _MONTH_ABBR.get(lang, _MONTH_ABBR["en"])
    base = f"{dt.day} {abbr[dt.month - 1]}"
    return f"{base} {dt.year}" if year else base


def ui_lang():
    # The active UI language, resolving the "system" fallback the same way
    # everywhere (main window, dialogs, chart widgets).
    # @return: "es" or "en", never anything else
    from PySide6.QtCore import QLocale
    from ..config import config
    lang = config.get("language", "system")
    if lang == "system":
        lang = str(QLocale.system().name()[:2])
    return lang if lang in ("es", "en") else "en"
