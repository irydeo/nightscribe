############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the planet table and sky-calendar strings
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import xml.etree.ElementTree as ET
from pathlib import Path
import datetime

from nightscribe.gui import pretty

I18N = Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n"

# context -> the source strings that must exist, translated, in the .ts.
# The HADS night-frequencies ("med", "high", ...) are runtime words, so
# lupdate cannot see them: this test pins them down and re-adding them
# after a lupdate run is part of the job if it ever fails.
EXPECTED = {
    "MainWindow": (
        "none", "minimal", "very low", "low", "med-low", "med", "medium",
        "med-high", "high", "very high", "critical",
        "Planet", "Mag", "Rise (UTC)", "Max (alt · UTC)", "Set (UTC)",
        "{t} UTC  ·  {l} local",
        "Best {alt}° tonight — below 15°, needs optics or a better season",
        "Never above the horizon within two days of tonight",
        "Up already two days ago — it never sets from your site",
        "Still up two days from now — it never sets from your site",
    ),
    "SkyCalendarContent": (
        "Moon", "Planets", "Sun",
        "Planets tonight",
        "Rise, set and best moment for each planet tonight "
        "(UTC times; your local time in the tooltip)",
    ),
    "SkyCalendarDialog": (
        "No transits are visible from your site this week — "
        "Jupiter is below the horizon at all of them",
        "Below — Jupiter is not up at these times",
    ),
}


def test_planet_and_sky_cal_strings_translated():
    # every string the planet table and the three sky-calendar tabs show
    # must be present and finished in both .ts files
    for lang in ("es", "en"):
        tree = ET.parse(I18N / f"nightscribe_{lang}.ts")
        missing = []
        for ctx in tree.getroot().findall("context"):
            name = ctx.find("name").text
            if name not in EXPECTED:
                continue
            have = set()
            for msg in ctx.findall("message"):
                tr = msg.find("translation")
                if tr is None or tr.get("type") in ("unfinished", "obsolete"):
                    continue
                if tr.text is None or tr.text.strip() == "":
                    continue
                have.add(msg.find("source").text)
            for src in EXPECTED[name]:
                if src not in have:
                    missing.append(f"{name} :: {src}")
        assert not missing, f"{lang} missing translations: {missing}"


def test_pretty_tables_es_en():
    # pretty is now the single source of truth for proper nouns and
    # month names (planet table, sky chips, calendar, chart dates).
    day = datetime.datetime(2026, 9, 3, 12, 0)

    # proper nouns: ES and EN differ where they must, agree where
    # they should (Venus, Neptune-ish names stay proper)
    assert pretty.name("es", "mars") == "Marte"
    assert pretty.name("en", "mars") == "Mars"
    assert pretty.name("es", "ganymede") == "Ganímedes"
    assert pretty.name("en", "ganymede") == "Ganymede"
    assert pretty.name("es", "sun") == "el Sol"
    assert pretty.name("en", "sun") == "the Sun"
    assert pretty.name("es", "moon") == "la Luna"
    assert pretty.name("en", "moon") == "the Moon"
    assert pretty.name("es", "earth") == "la Tierra"
    assert pretty.name("en", "earth") == "the Earth"
    assert pretty.name("es", "perseids") == "Perseidas"
    assert pretty.name("en", "perseids") == "Perseids"

    # unknown key: fall back to a capitalised key, never crash
    assert pretty.name("es", "weird") == "Weird"
    assert pretty.name("en", "weird") == "Weird"

    # dates: month name localised, day without zero padding, year last
    assert pretty.day("es", day) == "3 sep"
    assert pretty.day("en", day) == "3 Sep"
    assert pretty.day("es", day, year=True) == "3 sep 2026"
    assert pretty.day("en", day, year=True) == "3 Sep 2026"
