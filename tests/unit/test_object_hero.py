############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the object card's dossier pieces (ADR-057)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the ADR-057 dossier pieces: the ObjectHero
(identity + score ring), the KPI tiles and the section cards. The panel
integration lives in test_overview_panel.py; here the widgets themselves
are pinned down.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    existing = QApplication.instance()
    if existing is not None:
        return existing
    app = QApplication([])
    theme.apply_theme(app)
    return app


# ---------------- ScoreRing ----------------

def test_score_ring_clamps_and_reports(qapp):
    from nightscribe.gui.widgets.score_ring import ScoreRing
    ring = ScoreRing(64)
    assert ring.score() is None
    ring.set_score(82.4)
    assert ring.score() == 82.4
    ring.set_score(140)            # over 100 clamps, never overflows the arc
    assert ring.score() == 100.0
    ring.set_score(-5)
    assert ring.score() == 0.0
    ring.set_score(None)           # and None paints the bare track
    assert ring.score() is None
    ring.deleteLater()


def test_score_ring_paints(qapp):
    # paintEvent must not raise, with and without a score (offscreen, the
    # paint runs on grab())
    from nightscribe.gui.widgets.score_ring import ScoreRing
    ring = ScoreRing(64)
    ring.show()
    assert not ring.grab().isNull()
    ring.set_score(55)
    assert not ring.grab().isNull()
    ring.deleteLater()


# ---------------- KpiTile ----------------

def test_kpi_tile_texts_and_tooltip(qapp):
    from nightscribe.gui.widgets.kpi_tile import KpiTile
    tile = KpiTile("19.5", "Mag", "#4484ef", "the long explanation")
    assert tile.texts() == ("19.5", "Mag")
    # the tooltip fires on the labels too: they cover the tile's surface
    assert tile.lbl_value.toolTip() == "the long explanation"
    assert tile.lbl_caption.toolTip() == "the long explanation"
    tile.deleteLater()


def test_kpi_tile_neutral_without_accent(qapp):
    from nightscribe.gui.widgets.kpi_tile import KpiTile
    from nightscribe.gui import theme
    tile = KpiTile("45°", "Moon")
    assert theme.C_TEXT in tile.lbl_value.styleSheet()
    tile.deleteLater()


# ---------------- SectionCard ----------------

def test_section_card_rows(qapp):
    from nightscribe.gui.widgets.section_card import SectionCard
    card = SectionCard("Orbit", "#4484ef")
    card.add_row("Family", "Apollo", "It crosses Earth's orbit from "
                 "the outside, which is why we can meet it.")
    card.add_row("MOID", "0.028 AU", "")     # no explanation, no wrap row
    assert card.row_count() == 2
    assert card.rows_text[0][0] == "Family"
    assert card.rows_text[1][2] == ""
    card.deleteLater()


# ---------------- ObjectHero ----------------

def test_hero_identity_and_score(qapp):
    from nightscribe.gui.widgets.object_hero import ObjectHero
    hero = ObjectHero()
    hero.set_object("2026 QK", "neo", subtitle="2026 QK (443089)",
                    pha=True)
    hero.set_hook("An Apollo asteroid")
    hero.set_score(82.0, "Moving at 12 arcsec per minute.")
    assert hero.lbl_name.text() == "2026 QK"
    assert hero.lbl_kind.text() == "NEO"
    assert not hero.lbl_pha.isHidden()
    assert hero.lbl_subtitle.text() == "2026 QK (443089)"
    assert hero.lbl_hook.text() == "An Apollo asteroid"
    assert hero.ring.score() == 82.0
    assert not hero.ring.isHidden()
    assert not hero.lbl_why.isHidden()
    hero.deleteLater()


def test_hero_hides_score_without_one(qapp):
    # no score (a bare Explore object): the ring AND the why line hide;
    # absent, not zero
    from nightscribe.gui.widgets.object_hero import ObjectHero
    hero = ObjectHero()
    hero.set_object("SN 2026ziz", "sn")
    hero.set_score(None, "")
    assert hero.ring.isHidden()
    assert hero.lbl_score_cap.isHidden()
    assert hero.lbl_why.isHidden()
    # and the optional chips stay out of the way
    assert hero.lbl_pha.isHidden()
    assert hero.lbl_subtitle.isHidden()
    hero.deleteLater()


def test_hero_glyph_is_painted(qapp):
    from nightscribe.gui.widgets.object_hero import ObjectHero
    hero = ObjectHero()
    hero.set_object("CY Aqr", "hads")
    pix = hero.lbl_glyph.pixmap()
    assert pix is not None and not pix.isNull()
    hero.deleteLater()


# ---------------- kind glyph ----------------

def test_kind_glyph_every_kind(qapp):
    # every catalogued kind paints a non-empty glyph at both sizes
    from nightscribe.gui.widgets.kind_glyph import kind_glyph_pixmap
    for kind in ("neo", "sn", "comet", "pccp", "transit", "alert",
                 "hads", "variable"):
        for size in (28, 44):
            pix = kind_glyph_pixmap(kind, size)
            assert not pix.isNull(), f"{kind}@{size}"
            assert pix.width() == size
    # an unknown kind paints empty, never raises
    assert kind_glyph_pixmap("mystery", 28).width() == 28
