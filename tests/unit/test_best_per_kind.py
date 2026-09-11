############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - best_per_kind unit tests (WORKFLOWS 7quater K3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure tests for the K3 "best per kind" grid selection:

    best_per_kind(scored, n)

scored is a list of (target, score, parts, phrase) tuples already sorted
by global score.  The helper keeps at most the *n* best of each kind,
preserves the global-score order, and returns the set of the best id of
each kind (those are the ones that wear the metallic ring in the grid).
"""

from nightscribe.core import suggest


def _t(id_=None, kind=None, score=50.0, **attrs):
    d = {"id": id_, "kind": kind or "neo"}
    d.update(attrs)
    return (d, score, {}, {"es": "", "en": ""})


def test_cap_limits_each_kind_to_n():
    # 8 NEOs (descending score) + 1 SN.  With n=3 the grid has 4 rows, the
    # three best NEOs first and the SN (score 80) before the 3rd NEO.
    scored = [
        _t("n1", "neo", 90), _t("s1", "sn", 80), _t("n2", "neo", 70),
        _t("n3", "neo", 60), _t("n4", "neo", 50), _t("n5", "neo", 40),
        _t("n6", "neo", 30), _t("n7", "neo", 20), _t("n8", "neo", 10),
    ]
    grid, best = suggest.best_per_kind(scored, n=3)
    ids = [t[0]["id"] for t in grid]
    assert ids == ["n1", "s1", "n2", "n3"], ids
    assert best == {"n1", "s1"}


def test_best_id_is_the_highest_scoring_of_each_kind():
    scored = [
        _t("a", "neo", 80), _t("b", "neo", 70), _t("c", "comet", 60),
        _t("d", "comet", 50),
    ]
    grid, best = suggest.best_per_kind(scored, n=2)
    assert best == {"a", "c"}
    # capped: only the top-2 of each kind survive
    assert [t[0]["id"] for t in grid] == ["a", "b", "c", "d"]


def test_no_cap_returns_everything_and_all_kind_best():
    scored = [
        _t("a", "neo", 80), _t("b", "neo", 70),
        _t("c", "sn", 60), _t("d", "sn", 50),
    ]
    grid, best = suggest.best_per_kind(scored, n=0)
    assert [t[0]["id"] for t in grid] == ["a", "b", "c", "d"]
    assert best == {"a", "c"}


def test_grid_keeps_global_score_order():
    # 4 NEOs (80/70/60/50) + 2 SNs (90/40) with n=3 -> 6 rows in global
    # score order (the K3 "best per kind, but interleaved").
    scored = [
        _t("s1", "sn", 90), _t("n1", "neo", 80), _t("n2", "neo", 70),
        _t("n3", "neo", 60), _t("n4", "neo", 50), _t("s2", "sn", 40),
    ]
    grid, _ = suggest.best_per_kind(scored, n=3)
    assert [t[0]["id"] for t in grid] == ["s1", "n1", "n2", "n3", "s2"]


def test_missing_kind_is_treated_as_its_own_group():
    # Some dicts come in with .get("kind") missing; the code path should
    # not crash, and group them all under "" (empty kind).
    scored = [
        ({}, 80, {}, {"es": "", "en": ""}),
        ({}, 70, {}, {"es": "", "en": ""}),
    ]
    grid, best = suggest.best_per_kind(scored, n=1)
    assert len(grid) == 1
    assert best == {None}


def test_empty_scored_is_empty():
    grid, best = suggest.best_per_kind([], n=5)
    assert grid == []
    assert best == set()


def test_hads_is_its_own_group():
    # the seventh kind: a HADS target neither drowns nor is drowned by the
    # other six kinds in the per-kind cap
    scored = [
        _t("n1", "neo", 90), _t("h1", "hads", 85), _t("h2", "hads", 80),
        _t("t1", "transit", 70),
    ]
    grid, best = suggest.best_per_kind(scored, n=1)
    assert [t[0]["id"] for t in grid] == ["n1", "h1", "t1"]
    assert best == {"n1", "h1", "t1"}
