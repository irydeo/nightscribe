############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Object hero widget module (object card, ADR-057)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The object card's identity block (ADR-057): glyph, name, kind chip, the
# narrative hook and the "why tonight" phrase, with the 0-100 score ring
# on the right. Before the dossier redesign the card opened with a bare
# 15 px hook line; the hero is what makes the card read as the object's
# page and not as a form.

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame

from .. import theme
from ..ui_loader import adopt_ui, drop_in
from .kind_glyph import kind_glyph_pixmap
from .score_ring import ScoreRing

# The hero glyph is the 28 px row glyph scaled up (kind_glyph.py paints
# on a 28 px canvas and scales); 44 px is big enough to anchor the block
# without shouting over the name.
_GLYPH_PX = 44


class ObjectHero(QFrame):
    # The card's hero. All texts are data (set_object / set_hook /
    # set_score); the skin is applied in code because the kind hue is
    # data, not chrome (theme.py's rule: chrome in QSS, content inline).

    def __init__(self, parent=None):
        # @args: parent - parent widget
        super().__init__(parent)
        self.setObjectName("objectHero")
        self._ui = adopt_ui(self, "object_hero")
        self._accent = theme.C_ACCENT

        self.lbl_glyph = self._ui.lbl_glyph
        self.lbl_name = self._ui.lbl_name
        name_font = QFont(self.font())
        name_font.setPixelSize(17)
        name_font.setBold(True)
        self.lbl_name.setFont(name_font)

        self.lbl_kind = self._ui.lbl_kind
        self.lbl_pha = self._ui.lbl_pha
        self.lbl_pha.setStyleSheet(theme.chip_style(theme.C_WARN))

        self.lbl_subtitle = self._ui.lbl_subtitle
        self.lbl_subtitle.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.lbl_hook = self._ui.lbl_hook
        self.lbl_hook.setStyleSheet("font-size: 13px;")
        self.lbl_why = self._ui.lbl_why
        self.lbl_why.setStyleSheet(f"color: {theme.C_TEXT_DIM};")

        self.lbl_score_cap = self._ui.lbl_score_cap
        self.lbl_score_cap.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 10px;")

        # the score ring is a custom widget: the .ui carries only its slot
        self.ring = ScoreRing(64)
        self.ring.setToolTip(self.tr(
            "Tonight's score (0-100): scientific priority, observability, "
            "urgency and outreach hook for YOUR site, from core/suggest.py"))
        drop_in(self._ui.hero_score_col, self._ui.heroRingHost, self.ring)
        self.ring.hide()
        self._refresh_skin()

    def _refresh_skin(self):
        # Paints the hero's skin: a quiet gradient out of the kind hue over
        # the panel colour, with the 3 px spine carrying the hue (the same
        # grammar as the list rows). Solid composites, never alpha: over
        # the dark window an alpha wash reads muddy (theme.chip_style's
        # lesson).
        a = self._accent
        self.setStyleSheet(
            f"QFrame#objectHero {{ background: qlineargradient(x1:0, y1:0,"
            f" x2:1, y2:0, stop:0 {theme.composite(a, '24', over=theme.C_PANEL)},"
            f" stop:1 {theme.C_PANEL});"
            f" border: 1px solid {theme.C_LINE};"
            f" border-left: 3px solid {a}; border-radius: 12px; }}")

    def set_object(self, name, kind, subtitle="", pha=False):
        # @args: name - the object's display name, kind - its kind id
        #        (drives glyph, chip and hue), subtitle - a secondary
        #        designation (SBDB fullname, AUID...), pha - True shows
        #        the PHA flag chip
        # @return: None
        self._accent = theme.KIND_COLORS.get(kind, theme.C_ACCENT)
        self._refresh_skin()
        pix = kind_glyph_pixmap(kind, _GLYPH_PX)
        self.lbl_glyph.setPixmap(pix)
        self.lbl_glyph.setVisible(not pix.isNull()
                                  and pix.width() > 0)
        self.lbl_name.setText(name or "")
        label = theme.KIND_LABELS.get(kind, "")
        self.lbl_kind.setText(label)
        self.lbl_kind.setStyleSheet(theme.chip_style(self._accent))
        self.lbl_kind.setVisible(bool(label))
        self.lbl_pha.setVisible(bool(pha))
        self.lbl_subtitle.setText(subtitle or "")
        self.lbl_subtitle.setVisible(bool(subtitle))

    def set_hook(self, text):
        # @args: text - the narrative hook phrase (already translated)
        self.lbl_hook.setText(text or "")
        self.lbl_hook.setVisible(bool(text))

    def set_score(self, score, why_text=""):
        # @args: score - 0..100 or None (the ring and caption hide without
        #        one), why_text - the "why tonight" phrase
        # @return: None
        if score is None:
            self.ring.hide()
            self.lbl_score_cap.hide()
        else:
            self.ring.set_score(score)
            self.ring.show()
            self.lbl_score_cap.show()
        self.lbl_why.setText(why_text or "")
        self.lbl_why.setVisible(bool(why_text))
