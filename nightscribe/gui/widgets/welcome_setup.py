############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Welcome view: first-run / update setup (ADR-053, 1.4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Welcome view (Interfaz 1.4): the old modal QWizard lives here as an
inline stepper (Observatory -> Targets -> Data) wrapped in a painted night
sky.

Two things make this screen worth looking at:

   * the hero is a real sky. gui/widgets/welcome_sky.py paints our vector
     sky and the Moon AT TONIGHT'S PHASE, so the first frame says "this
     app looks at your sky", not "fill this form";
   * the "your night, now" strip answers back. It is computed here, 100%
     offline (core/coords + core/ephem_minor): darkness window, Moon set
     and the planets up at dusk. Type a latitude and the sky answers in
     the same breath; that is the whole hook.

The heavy lifting is still the SAME code as the wizard: the helpers in
gui/wizard.py (_detect, _resolve_site, _setup_kinds, _setup_data,
_apply_site, _apply_kinds, _mark_done) are reused against the loaded
widget, so the two never drift. _setup_kinds runs in card mode here.

The host (MainWindow) decides when Welcome is shown (first run, a pending
update, or no projects) and gates navigation on the Data step while an
update is unacknowledged.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import theme
from ..ui_loader import drop_in, load_ui


class WelcomeSetup(QWidget):
    # create_project: the CTA asks the host to open the new-project view.
    # finished: the Data step was acknowledged (the host seals app_version).
    # skip: "explore first" asks the host to go straight to the projects.
    # open_guide/open_skycal: the onboarding cards ask the host for the
    # documentation / the Sky calendar dialog.
    create_project = Signal()
    finished = Signal()
    skip = Signal()
    open_guide = Signal()
    open_skycal = Signal()

    # @args: snapshot - the pre-migration backup dict (core/backup.backup)
    #        or None when there is no database yet; parent - the host
    def __init__(self, snapshot=None, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        # the .ui is loaded as a child and its named widgets are reached
        # through self.ui (ADR-005); the wizard helpers take the husk
        self.ui = load_ui("welcome_tab", self)
        # The page has a natural height of roughly 800 px (the compact
        # layout above). On a short screen it must SCROLL, never squeeze:
        # the old build let the vertical layout compress the observatory
        # form until its rows overlapped, which is how a form becomes
        # unreadable instead of merely off-screen.
        from PySide6.QtWidgets import QFrame, QScrollArea
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.ui)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        self._boxes = {}
        self._step_text = {}
        self._map = None
        self._faded = False
        self._fade_anim = None
        # Interfaz 1.5: the host tells us WHO is looking at this screen.
        # has_projects flips the call to action; update_version turns the
        # whole page into the post-update notice (see set_context).
        self._has_projects = False
        self._update_version = None
        self._step_key = "obs"
        self._done_before = ()
        from ...config import config
        # Motion is a preference, not a default we impose: Settings >
        # Interface turns it off and nothing here moves.
        self._animations = bool(config.get("ui_animations", True))
        self._brand()
        self._wire()
        self._fill_from_config()
        self._fill_night()
        self._fill_doors()
        self.show_step("obs")

    # ------------------------------------------------------------ building

    def _brand(self):
        # The logo + the wordmark ("SCRIBE" in the accent), the only bits
        # of the hero that are not plain text (Interfaz 1.2).
        u = self.ui
        logo = theme.app_logo(64)
        if not logo.isNull():
            u.lbl_logo.setPixmap(logo)
        u.welcomeWordmark.setText(
            'NIGHT<span style="color:%s">SCRIBE</span>' % theme.C_ACCENT)

    def _wire(self):
        from .. import wizard as wz
        u = self.ui
        # the painted sky takes the placeholder's slot (ADR-005): the .ui
        # never carries a custom widget
        from .welcome_sky import WelcomeSky
        self._sky = WelcomeSky()
        self._sky.set_animations(self._animations)
        drop_in(u.skyHero.parentWidget().layout(), u.skyHero, self._sky)

        # The site picker map (Interfaz 1.5). It is the way IN for anyone
        # who knows where they live but not their latitude, and the way to
        # SEE the point once it is set.
        from .site_map import SiteMap
        self._map = SiteMap()
        self._map.picked.connect(self._map_picked)
        drop_in(u.mapHost.parentWidget().layout(), u.mapHost, self._map)
        u.obsColumns.setStretch(0, 1)
        # drop_in's replaceWidget puts the new widget LAST in the parent's
        # child list, which paints it OVER the overlay: the hero would come
        # up as a beautiful sky with no words on it. Raise the text back.
        u.heroOverlay.raise_()
        # the strip's text takes the slack so its button stays pinned right
        u.nightStripLayout.setStretch(1, 1)
        # and the setup panel, not the onboarding cards, is what grows when
        # the window has room: the doors keep their natural height instead
        # of stretching into three tall empty boxes
        u.welcomeLayout.setStretch(2, 1)

        # the rail buttons keep their .ui text; we re-read it so the "done"
        # tick can be added and removed without losing the translation
        self._step_text = {btn.objectName(): btn.text() for btn in
                           (u.btn_step_obs, u.btn_step_kinds, u.btn_step_data)}

        u.btn_card2_guide.clicked.connect(self.open_guide.emit)
        u.btn_card3_skycal.clicked.connect(self.open_skycal.emit)
        u.btn_detect.clicked.connect(lambda: wz._detect(u))
        u.btn_resolve.clicked.connect(lambda: wz._resolve_site(u))
        u.btn_step_obs.clicked.connect(lambda: self.show_step("obs"))
        u.btn_step_kinds.clicked.connect(lambda: self.show_step("kinds"))
        u.btn_step_data.clicked.connect(lambda: self.show_step("data"))
        u.btn_obs_next.clicked.connect(self._obs_next)
        u.btn_kinds_next.clicked.connect(self._kinds_next)
        u.btn_data_ack.clicked.connect(self.finished.emit)
        # The two buttons are roles, not meanings: _primary/_secondary
        # decide what each one does once we know whether the observer
        # already has projects (Interfaz 1.5).
        u.btn_create.clicked.connect(self._primary)
        u.btn_skip.clicked.connect(self._secondary)
        u.btn_night_set.clicked.connect(self._night_set)
        u.btn_kinds_all.clicked.connect(lambda: self._set_all(True))
        u.btn_kinds_none.clicked.connect(lambda: self._set_all(False))
        # the kinds grid (cards) and the migration report are data (ADR-005)
        self._boxes = wz._setup_kinds(u, card=True)
        wz._setup_data(u, self._snapshot)
        for box in self._boxes.values():
            box.toggled.connect(lambda _on: self._update_kinds_count())
        self._update_kinds_count()

        # Every path that moves the site also moves the sky: the strip is
        # the reward for typing, so it must answer on the spot (and it is
        # all local maths, no network behind this signal).
        for w in (u.spn_site_lat, u.spn_site_lon):
            w.valueChanged.connect(lambda _v: self._site_changed())
        u.edt_site_name.textChanged.connect(lambda _t: self._site_changed())
        u.edt_site_mpc.textChanged.connect(lambda _t: self._site_changed())

    def _fill_from_config(self):
        # Seeds the form from the current settings so a re-visit shows what
        # is already saved (a first run shows zeros / empty).
        from ...config import config
        u = self.ui
        u.spn_site_lat.setValue(float(config.get("lat") or 0.0))
        u.spn_site_lon.setValue(float(config.get("lon") or 0.0))
        u.spn_site_height.setValue(int(config.get("height") or 0))
        u.edt_site_name.setText(config.get("observatory_name") or "")
        u.edt_site_mpc.setText(config.get("mpc_code") or "")
        self._refresh_create()

    def _fill_doors(self):
        # The first door lists what you can observe as coloured chips: the
        # hues are the app's own per-kind colours, so the Welcome screen and
        # the Tonight rows already speak the same language on day one.
        from ...core import kinds as core_kinds
        grid = self.ui.card1ChipsGrid
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        # four across: eight kinds in two short rows keeps the door the same
        # height as its two neighbours instead of a tall column of chips
        cols = 4
        for i, kind in enumerate(core_kinds.KINDS):
            chip = theme.KIND_LABELS.get(kind["id"], kind["id"].upper())
            lbl = self._chip(chip, theme.KIND_COLORS.get(kind["id"]))
            grid.addWidget(lbl, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)

    def _chip(self, text, color):
        # @args: text - the short chip label; color - its KIND_COLORS hue
        # @return: a QLabel wearing the shared pill style
        from PySide6.QtWidgets import QLabel
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        if color:
            lbl.setStyleSheet(theme.chip_style(color, font_size=10))
        return lbl

    # ------------------------------------------------------- your night, now

    def _site_ok(self):
        # @return: True when the form has a usable site (coords or MPC code)
        u = self.ui
        return (u.spn_site_lat.value() != 0.0
                or u.spn_site_lon.value() != 0.0
                or bool(u.edt_site_mpc.text().strip()))

    def _site_changed(self):
        # One place for "the site moved": the CTA wakes up, the sky strip
        # recomputes and the map marker follows. Kept together so a new
        # field cannot update one and forget the others.
        self._refresh_create()
        self._fill_night()
        self._site_to_map()

    def _site_to_map(self):
        # Spin boxes -> map. A zero pair is "not set", so the marker goes
        # away instead of sitting in the Gulf of Guinea.
        if self._map is None:
            return
        u = self.ui
        lat, lon = u.spn_site_lat.value(), u.spn_site_lon.value()
        if lat == 0.0 and lon == 0.0:
            self._map.set_site(None, None)
            return
        self._map.set_site(lat, lon, u.edt_site_name.text().strip())

    def _map_picked(self, lat, lon):
        # Map -> spin boxes and name. The signals are blocked so this does
        # not come straight back as a "the site moved" and recentre the view
        # the observer just clicked on; _site_changed is called once, by
        # hand, at the end.
        # @args: lat, lon - the clicked point, in degrees
        u = self.ui
        fields = (u.spn_site_lat, u.spn_site_lon, u.edt_site_name)
        for w in fields:
            w.blockSignals(True)
        u.spn_site_lat.setValue(lat)
        u.spn_site_lon.setValue(lon)
        # A clicked point has no name, so we borrow the nearest city's, or
        # write the coordinates out when there is none within reach. It is
        # written every time, like the MPC resolve: picking a point is an
        # explicit statement of where the site is.
        from ...core import places
        u.edt_site_name.setText(places.label(lat, lon, self.tr))
        for w in fields:
            w.blockSignals(False)
        self._site_changed()

    def _fill_night(self):
        # Fills the hero strip. Everything here is local arithmetic on the
        # numbers already on screen (no network, no cache): that is why it
        # can afford to run on every keystroke of the latitude.
        u = self.ui
        # Coordinates, not just "a site": an MPC code that has not been
        # resolved yet leaves lat/lon at zero, and 0/0 is the Gulf of
        # Guinea. Showing a night for a spot in the Atlantic because a code
        # was typed would be worse than showing nothing.
        has_coords = (u.spn_site_lat.value() != 0.0
                      or u.spn_site_lon.value() != 0.0)
        if not has_coords:
            if u.edt_site_mpc.text().strip():
                u.lbl_night_window.setText(self.tr(
                    "Press Resolve and this becomes your sky."))
            else:
                u.lbl_night_window.setText(self.tr(
                    "Astronomical night: set your observatory and this "
                    "becomes your sky."))
            u.lbl_night_moon.setText(self.tr(
                "Moon and planets for your exact site."))
            u.lbl_night_planets.setText("")
            u.btn_night_set.setVisible(True)
            return
        u.btn_night_set.setVisible(False)
        lat, lon = u.spn_site_lat.value(), u.spn_site_lon.value()
        # The numbers AND the words come from core/night_brief: the sky bar
        # and the resting panel of the projects view read the same source,
        # so the three can never disagree about the Moon.
        from ...core import night_brief as nb
        try:
            b = nb.brief(lat, lon)
        except Exception:                      # a broken site is not a crash
            b = {"window": None, "moon": None, "planets": []}
        u.lbl_night_window.setText(nb.window_line(b))
        u.lbl_night_moon.setText(nb.moon_line(b))
        u.lbl_night_planets.setText(nb.planets_line(b))

    def _night_set(self):
        # The strip's own call to action when there is no site yet.
        self.show_step("obs")
        self.ui.spn_site_lat.setFocus()

    # -------------------------------------------------------------- actions

    # ------------------------------------------------- who is looking at this

    def set_context(self, has_projects=False, update_version=None):
        # The host says who is looking at this screen (Interfaz 1.5):
        # @args: has_projects - True when the observer already has projects,
        #          which swaps the call to action around;
        #        update_version - the version string when this screen is the
        #          post-update notice (an update is a gate: its report must
        #          be read once), or None on a first run / a manual visit.
        self._has_projects = bool(has_projects)
        self._update_version = (update_version or "").strip() or None
        self._apply_context()
        self._refresh_create()

    def _apply_context(self):
        # Everything that changes between the three ways this page is seen:
        # a first run, the post-update notice, and a manual visit.
        u = self.ui
        update = self._update_version is not None
        # The badge sits next to the report's title, not in the hero: up
        # there it fought the wordmark for attention, and the fact it
        # announces belongs to the panel that asks for the click.
        u.lbl_data_badge.setVisible(update)
        if update:
            u.lbl_data_badge.setText(
                self.tr("UPDATED TO {version}").format(
                    version=self._update_version))
        # The hero must not tell someone who has been using the app for
        # months to "set up your observatory in three steps": on an update
        # it explains WHY the app stopped here.
        u.welcomeLead.setText(
            self.tr("NightScribe has been updated to {version}. Your "
                    "database was copied and verified before anything else, "
                    "and below is what changed.").format(
                        version=self._update_version) if update else
            self.tr("Three steps, then the app walks you through every "
                    "project: record, capture, analysis and publishing."))
        # The report's own note: on an update it says what happens after,
        # because the gate blocks navigation until it is read.
        u.lbl_data_rule.setText(
            self.tr("Shown once per version; after this the app opens "
                    "straight on your projects.") if update else
            self.tr("Required once per version."))
        # One action, and on an update it lives with the report it closes:
        # two buttons doing the same thing read as a mistake.
        u.btn_data_ack.setText(
            self.tr("Got it, go to my projects") if update else
            self.tr("Got it, continue"))
        self._mark_primary(u.btn_data_ack, update)
        for w in (u.btn_create, u.lbl_cta_sub, u.btn_skip):
            w.setVisible(not update)
        # The rail tells the truth about an update: steps 1 and 2 were
        # configured long ago, so they read as done from the first frame.
        self._done_before = (0, 1) if update else ()
        self.show_step(self._step_key)

    def _mark_primary(self, button, on):
        # @args: button - the widget; on - True paints it as THE action
        # @return: None. A dynamic property plus a repolish: the QSS cannot
        #          know which button is primary today.
        button.setProperty("primary", bool(on))
        button.style().unpolish(button)
        button.style().polish(button)

    def _refresh_create(self):
        # The CTA says what it does for THIS observer, and when it cannot be
        # used it says why: a dead button with no explanation is the fastest
        # way to lose a first-time user.
        u = self.ui
        if self._has_projects:
            # There is a workflow to go back to, so the way out is back to
            # it and starting another project is the quiet alternative.
            u.btn_create.setText(self.tr("My projects →"))
            u.btn_create.setToolTip(self.tr("Back to your project list"))
            u.btn_create.setEnabled(True)
            u.btn_skip.setText(self.tr("New project →"))
            u.lbl_cta_sub.setText(self.tr(
                "Back to your projects, or start a new one from tonight's "
                "targets."))
            return
        ok = self._site_ok()
        u.btn_create.setText(self.tr("Create my first project"))
        u.btn_create.setToolTip(self.tr("Pick among tonight's best objects"))
        u.btn_create.setEnabled(ok)
        u.btn_skip.setText(self.tr("Explore first →"))
        u.lbl_cta_sub.setText(
            self.tr("Tonight's best objects, with the app walking you "
                    "through.") if ok else
            self.tr("Set your observatory in step 1 and this button wakes "
                    "up."))

    def _primary(self):
        # The big button: create a project, or go back to the ones you have.
        if self._has_projects:
            self.skip.emit()
            return
        self._create()

    def _secondary(self):
        # The quiet link, the mirror image of _primary.
        if self._has_projects:
            self._create()
            return
        self.skip.emit()

    def _update_kinds_count(self):
        n = sum(1 for b in self._boxes.values() if b.isChecked())
        self.ui.lbl_kinds_count.setText(
            self.tr("{n} of {total} followed").format(
                n=n, total=len(self._boxes)))

    def _set_all(self, on):
        # @args: on - True checks every kind, False clears them all. The
        #        "keep one" rule still holds: Continue refuses an empty set.
        for box in self._boxes.values():
            box.setChecked(on)

    def show_step(self, key, done_before=None):
        # @args: key - "obs" | "kinds" | "data"; done_before - steps that
        #        were already completed BEFORE this visit (an update marks
        #        the observatory and the targets as configured), or None to
        #        keep whatever was set
        if done_before is not None:
            self._done_before = tuple(done_before)
        self._step_key = key
        idx = {"obs": 0, "kinds": 1, "data": 2}.get(key, 0)
        u = self.ui
        u.setup_stack.setCurrentIndex(idx)
        # A step is "done" when it is behind us or when it was already
        # configured; the step we are LOOKING at is never done, whatever
        # else is true (you are working on it right now).
        done = {i for i in range(3)
                if (i < idx or i in self._done_before) and i != idx}
        steps = ((u.btn_step_obs, 0), (u.btn_step_kinds, 1),
                 (u.btn_step_data, 2))
        for btn, i in steps:
            base = self._step_text.get(btn.objectName(), btn.text())
            btn.setChecked(i == idx)
            # done steps read green in the QSS and carry a tick; the .ui's
            # own text stays translated underneath
            btn.setProperty("state", "done" if i in done else "")
            btn.setText(("✓ " + base) if i in done else base)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        # the rail fills up to the last done step: each connector belongs to
        # the step on its left
        for sep, reached in ((u.rail_sep1, 0 in done),
                             (u.rail_sep2, 1 in done)):
            sep.setProperty("state", "done" if reached else "")
            sep.style().unpolish(sep)
            sep.style().polish(sep)

    def _obs_next(self):
        from .. import wizard as wz
        if not self._site_ok():
            self.ui.lbl_site_status.setText(
                self.tr("Type the coordinates, use the MPC code or detect "
                        "your location."))
            return
        wz._apply_site(self.ui)
        self._refresh_create()
        self._fill_night()
        self.show_step("kinds")

    def _kinds_next(self):
        from .. import wizard as wz
        if not any(b.isChecked() for b in self._boxes.values()):
            self.ui.lbl_kinds_rule.setText(
                self.tr("Keep at least one kind checked."))
            self.ui.lbl_kinds_rule.setStyleSheet(
                "color: %s;" % theme.C_WARN)
            return
        self.ui.lbl_kinds_rule.setStyleSheet(
            "color: %s;" % theme.C_TEXT_DIM)
        wz._apply_kinds(self._boxes)
        self.show_step("data")

    def _create(self):
        # The CTA: persist whatever is set and ask the host to open the
        # new-project view.
        from .. import wizard as wz
        if self._site_ok():
            wz._apply_site(self.ui)
        wz._apply_kinds(self._boxes)
        self.create_project.emit()

    def ack_data(self):
        # The host calls this when the Data step is the acknowledged gate.
        from .. import wizard as wz
        wz._mark_done()

    # -------------------------------------------------------------- motion

    def refresh_animations(self):
        # Re-reads the preference (Settings > Interface) without a restart:
        # the hero stops breathing the moment the box is cleared.
        from ...config import config
        self._animations = bool(config.get("ui_animations", True))
        self._sky.set_animations(self._animations)

    def showEvent(self, event):
        super().showEvent(event)
        # A single fade on the first reveal. Not a slideshow: the app is a
        # tool, and a tool that takes a second to show itself is a tool in
        # the way.
        if self._faded or not self._animations:
            return
        self._faded = True
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(420)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # The effect is dropped when it ends: a live QGraphicsOpacityEffect
        # forces every repaint through an offscreen buffer, and the hero
        # repaints its glints several times a second.
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        self._fade_anim = anim
        anim.start(QPropertyAnimation.DeleteWhenStopped)
