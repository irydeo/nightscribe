############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the local document index (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/docs_index` — the offline index the assistant's "about the app"
scope reads. No network: the corpus is the repo's own docs. The point is
that a question finds the right chapter (and the right LANGUAGE), and that
a question about nothing finds nothing instead of a random chunk."""

from nightscribe.core import docs_index


def test_spanish_query_finds_the_spanish_guide():
    hits = docs_index.search("fotometría curva de luz", lang="es")
    assert hits
    assert any("photometry" in h["label"] for h in hits), hits[0]["label"]
    # Spanish reads the Spanish files
    assert all(h["label"].endswith(".es.md") or h["label"].startswith("adr/")
               for h in hits)


def test_english_query_finds_the_english_guide():
    hits = docs_index.search("light curve photometry", lang="en")
    assert hits
    assert any("photometry" in h["label"] for h in hits), hits[0]["label"]
    assert all(not h["label"].endswith(".es.md") for h in hits)


def test_a_title_hit_outranks_a_body_hit():
    # "calibration" is a chapter word; a chunk with it in the heading must
    # come before one that only mentions it in the body
    hits = docs_index.search("calibration", lang="en")
    assert hits
    assert "calibration" in hits[0]["heading"].lower()


def test_a_question_about_nothing_finds_nothing():
    assert docs_index.search("zzz qqq xyzzy", lang="en") == []
    assert docs_index.search("", lang="en") == []


def test_adrs_are_sliced_by_language():
    # the ADRs carry both languages in one file; a Spanish query must not
    # drag the English half in
    hits = docs_index.search("astrometría medida", lang="es")
    assert any(h["label"].startswith("adr/") for h in hits)
    for h in hits:
        if h["label"].startswith("adr/"):
            assert "## English" not in h["text"]


def test_clear_cache_forgets_it():
    assert docs_index.search("photometry", lang="en")
    docs_index.clear_cache()
    assert docs_index.search("photometry", lang="en")
