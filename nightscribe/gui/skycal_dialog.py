############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Sky calendar dialog module (Track SC2-SC1, ADR-040)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The «Sky calendar» dialog (menu Tools): the solar system as a stream of
events. The old «Sun & sky» tab content lives here intact (the Sun now,
the impact line, the almanac, the outreach buttons), enriched with the
locally-computed calendar: next 60 days of events, the Moon calendar,
the planets, and the week's Galilean moon transits.

All the event maths is local (`core/skyevents` + `core/satellites`); the
dialog only puts words to it (plain language rule, ADR-038). The engine
hands over plain dicts; this module formats them with tr().
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QListWidgetItem,
                               QVBoxLayout)

from . import theme

# Moon names and planet names are proper nouns: translated by hand here
# (the engine hands over lowercase keys, never display text).
_MOON_NAMES = {"io": ("Io", "Io"), "europa": ("Europa", "Europa"),
               "ganymede": ("Ganímedes", "Ganymede"),
               "callisto": ("Calisto", "Callisto")}
_PLANET_NAMES = {
    "mercury": ("Mercurio", "Mercury"), "venus": ("Venus", "Venus"),
    "mars": ("Marte", "Mars"), "jupiter": ("Júpiter", "Jupiter"),
    "saturn": ("Saturno", "Saturn"), "uranus": ("Urano", "Uranus"),
    "neptune": ("Neptuno", "Neptune"), "moon": ("la Luna", "the Moon"),
    "sun": ("el Sol", "the Sun")}
_SHOWER_NAMES = {
    "quadrantids": ("Cuadrántidas", "Quadrantids"),
    "lyrids": ("Líridas", "Lyrids"),
    "eta_aquariids": ("Eta Acuáridas", "Eta Aquariids"),
    "perseids": ("Perseidas", "Perseids"),
    "orionids": ("Oriónidas", "Orionids"),
    "leonids": ("Leónidas", "Leonids"),
    "geminids": ("Gemínidas", "Geminids"),
    "ursids": ("Úrsidas", "Ursids")}


class SkyCalendarDialog(QDialog):
    # The dialog shell: holds the loaded sky_calendar.ui content, a Close
    # button, and the formatters that turn engine events into plain words.

    def __init__(self, content, lang="es", parent=None):
        # @args: content - the loaded sky_calendar.ui widget (its widgets
        #         are re-owned by the MainWindow's solar handlers),
        #        lang - "es"|"en" for the proper-noun tables
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sky calendar"))
        self._lang = lang
        self.content = content    # the loaded sky_calendar.ui widget
        lay = QVBoxLayout(self)
        lay.addWidget(content)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.resize(1080, 760)

    # ---------------- formatting (engine dicts -> plain words) ----------

    def _name(self, key):
        # @args: key - lowercase object key from the engine
        # @return: the proper noun in the dialog's language
        pair = _MOON_NAMES.get(key) or _PLANET_NAMES.get(key) \
            or _SHOWER_NAMES.get(key)
        if pair is None:
            return key
        return pair[0] if self._lang == "es" else pair[1]

    def event_row(self, ev):
        # One event of the 60-day list, in plain words.
        # @args: ev - a skyevents event dict
        # @return: (icon, text) — the row's pieces
        kind = ev["kind"]
        objs = ev["objects"]
        if kind in ("new_moon", "first_quarter", "full_moon",
                    "last_quarter"):
            words = {"new_moon": self.tr("New moon"),
                     "first_quarter": self.tr("First quarter"),
                     "full_moon": self.tr("Full moon"),
                     "last_quarter": self.tr("Last quarter")}
            return ev["icon"], words[kind]
        if kind in ("perigee", "apogee"):
            label = self.tr("Moon at perigee") if kind == "perigee" \
                else self.tr("Moon at apogee")
            return ev["icon"], self.tr("%1 (%2 km)").replace(
                "%1", label).replace("%2", f"{ev.get('dist_km', 0):,}")
        if kind == "moon_conjunction":
            name = self._name(objs[1])
            text = self.tr("The Moon %1° from %2").replace(
                "%1", str(ev.get("sep_deg"))).replace("%2", name)
            if ev.get("mag") is not None:
                text += self.tr(" (mag %1)").replace(
                    "%1", str(ev.get("mag")))
            return ev["icon"], text
        if kind == "planet_conjunction":
            text = self.tr("%1 and %2 only %3° apart") \
                .replace("%1", self._name(objs[0])) \
                .replace("%2", self._name(objs[1])) \
                .replace("%3", str(ev.get("sep_deg")))
            return ev["icon"], text
        if kind == "opposition":
            return ev["icon"], self.tr(
                "%1 at opposition — mag %2, up all night") \
                .replace("%1", self._name(objs[0])) \
                .replace("%2", str(ev.get("mag")))
        if kind == "max_elongation":
            side = self.tr("east — evening sky") \
                if ev.get("side") == "east" \
                else self.tr("west — morning sky")
            return ev["icon"], self.tr(
                "%1 at greatest elongation (%2°), %3") \
                .replace("%1", self._name(objs[0])) \
                .replace("%2", str(ev.get("elong_deg"))) \
                .replace("%3", side)
        if kind == "sun_conjunction":
            detail = self.tr("inferior") if ev.get("detail") == "inferior" \
                else self.tr("superior")
            return ev["icon"], self.tr(
                "%1 at %2 conjunction with the Sun") \
                .replace("%1", self._name(objs[0])) \
                .replace("%2", detail)
        if kind == "lunar_eclipse":
            detail = self.tr("total") if ev.get("detail") == "total" \
                else self.tr("partial")
            return ev["icon"], self.tr(
                "Likely %1 lunar eclipse (approximate — no contact times)") \
                .replace("%1", detail)
        if kind == "solar_eclipse":
            word = {"total": self.tr("total"),
                    "annular": self.tr("annular"),
                    "partial": self.tr("partial")}.get(
                        ev.get("detail"), self.tr("partial"))
            return ev["icon"], self.tr(
                "Likely %1 solar eclipse (approximate — check visibility)") \
                .replace("%1", word)
        if kind == "meteor_shower":
            return ev["icon"], self.tr(
                "%1 meteor shower peaks (ZHR ~%2, radiant %3)") \
                .replace("%1", self._name(objs[0])) \
                .replace("%2", str(ev.get("zhr"))) \
                .replace("%3", ev.get("radiant") or "")
        return ev["icon"], kind     # satellite kinds live in their own box

    def moon_row(self, ev):
        # One Galilean window, in plain words, with the honesty label.
        # @args: ev - a skyevents event of kind sat_transit/shadow_transit
        # @return: (icon, text)
        who = self._name(ev["objects"][0])
        span = "%s–%s UT" % (ev["t0"].strftime("%H:%M"),
                             ev["t1"].strftime("%H:%M"))
        if ev["kind"] == "shadow_transit":
            text = self.tr("%1's shadow crosses Jupiter %2") \
                .replace("%1", who).replace("%2", span)
        else:
            text = self.tr("%1 transits Jupiter %2") \
                .replace("%1", who).replace("%2", span)
        text += "  " + self.tr("(±%1 min)").replace(
            "%1", str(ev.get("uncertainty_min", 10)))
        return ev["icon"], text

    # ---------------- population ----------------

    def fill_events(self, events, content):
        # Fills the 60-day list (satellite windows excluded — they live
        # in the Jupiter box) and the Moon calendar line.
        # @args: events - skyevents.events() output, content - the loaded
        #         ui widget (lst_events, lbl_moon_cal)
        # @return: None
        lst = content.lst_events
        lst.clear()
        today = None
        for ev in events:
            if ev["kind"] in ("sat_transit", "shadow_transit"):
                continue
            icon, text = self.event_row(ev)
            day = ev["date"].strftime("%d %b")
            item = QListWidgetItem(f"{icon}  {day} — {text}")
            if ev.get("tonight"):
                today = today or day
                item.setForeground(Qt.GlobalColor.white)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            lst.addItem(item)
        # the Moon calendar: the next phases + apsides, compact
        ph = [e for e in events if e["kind"] in
              ("new_moon", "first_quarter", "full_moon", "last_quarter",
               "perigee", "apogee")][:6]
        bits = []
        for ev in ph:
            icon, text = self.event_row(ev)
            bits.append(f"{icon} {text}: "
                        + ev["date"].strftime("%d %b"))
        content.lbl_moon_cal.setText("   ·   ".join(bits))

    def fill_jupiter_moons(self, events, content):
        # The week's Galilean windows from the site: observable first,
        # then the rest dimmed. @return: None
        sats = [e for e in events
                if e["kind"] in ("sat_transit", "shadow_transit")]
        lst = content.lst_jupmoons
        lst.clear()
        obs = [e for e in sats if e.get("observable")]
        rest = [e for e in sats if not e.get("observable")]
        for ev in obs:
            icon, text = self.moon_row(ev)
            day = ev["t0"].strftime("%d %b")
            item = QListWidgetItem(f"{icon}  {day} — {text}")
            lst.addItem(item)
        for ev in rest:
            icon, text = self.moon_row(ev)
            day = ev["t0"].strftime("%d %b")
            item = QListWidgetItem(f"{icon}  {day} — {text}")
            item.setForeground(QColor(theme.C_TEXT_DIM))
            lst.addItem(item)
