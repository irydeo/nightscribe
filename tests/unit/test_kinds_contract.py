############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the target-kind contract
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Adding a target kind must not leave a hole.

kinds.KINDS is the canonical list, but the id is written by hand in ~35 files
(DEV-04), so a new kind is a hunt. This is the cheap half of the contract: the
maps that MUST cover every kind (the colour, the chip label, the analysis, the
context fields, the hashtags) fail the day a kind is added without them. The
if-chains in planner/suggest/overview/narrative are not a map and are not
checked here; this holds the ones that are, which is what would have caught a
kind added with no colour.
"""

from nightscribe.core import kinds, narrative
from nightscribe.gui import theme


def test_every_kind_has_a_colour_and_a_chip():
    ids = set(kinds.ids())
    assert set(theme.KIND_COLORS) == ids
    assert set(theme.KIND_LABELS) == ids


def test_every_kind_has_an_analysis_and_context_fields():
    ids = set(kinds.ids())
    assert set(kinds.ANALYSIS) == ids
    assert set(kinds._CONTEXT_FIELDS) == ids
    for k in ids:
        assert kinds.analysis_of(k) in ("astrometry", "photometry")


def test_every_kind_has_hashtags():
    base = narrative.hashtags("__not_a_kind__")
    for k in kinds.ids():
        assert narrative.hashtags(k) != base, k


def test_the_enriched_types_map_to_known_kinds():
    assert set(kinds._ENRICHED_KIND.values()) <= set(kinds.ids())
