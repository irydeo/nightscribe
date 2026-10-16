############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Observatory console widget (ADR-081 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The observatory console (ADR-081 rev, 2026-10-16).

It is the Capture step's control surface, and it reads like a console: the
STATUS on top (who answers, the stop always at hand, the telemetry band),
the COMMANDS below, and the last frame in its own panel. It replaced a
code-built pile of four button rows whose state was four text pairs.

The split with the main window is deliberate: this widget owns the
STRUCTURE (the Designer file) and the MODES (what is on screen when the
observatory is off, idle, moving, capturing or following), and the main
window keeps the protocol and the workers, which are bound to its threads
and to one client at a time. That is why nothing here talks to a client:
the console is told what to show, never what to do.

Three verbs and two checkboxes: Point telescope (+ Astrometric goto), Send
plan, Start capture (+ Follow the object). The checkboxes are the SAME
intention with another method, never a second destination, and they are
remembered between sessions (a preference, not a nightly decision).
"""

import logging

from PySide6.QtWidgets import QWidget

from ..ui_loader import adopt_ui

logger = logging.getLogger("nightscribe.gui.observatory_console")

# The registry names the main window wires and the tests read. The console
# exposes each one as an attribute, so the wiring did not have to move when
# the panel became a .ui.
KEYS = (
    "ccd_connect", "ccd_disconnect", "ccd_status", "ccd_stop",
    "ccd_version", "ccd_temp", "ccd_tracking", "ccd_slew", "ccd_coords",
    "ccd_goto", "ccd_sync", "cmb_ccd_filter", "ccd_push", "ccd_staged",
    "ccd_start", "ccd_follow",
    "capture_preview", "capture_preview_img", "capture_caption",
    "capture_open", "follow_box", "follow_label", "follow_bar",
)

# The modes the console can be in. They are what changes what is on screen:
# a console that shows the same buttons greyed out is the pile we retired.
MODE_OFF = "off"
MODE_IDLE = "idle"
MODE_MOVING = "moving"
MODE_CAPTURING = "capturing"
MODE_FOLLOWING = "following"


class ObservatoryConsole(QWidget):
    # The console itself: structure + modes (module docstring).
    #
    # @args: parent - the widget that hosts it (the Capture page's card)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = adopt_ui(self, "observatory_panel")
        for name in KEYS:
            setattr(self, name, getattr(self._ui, name))
        self.set_mode(MODE_OFF)

    def widgets(self):
        # @return: {registry name: widget} for the main window's wiring. The
        #          same shape the code-built block registered, so every
        #          consumer keeps working unchanged.
        return {name: getattr(self, name) for name in KEYS}

    def set_mode(self, mode):
        # @args: mode - one of the MODE_* constants
        # @return: None. Shows the region each mode calls for: the way in when
        #          there is no connection, the console when there is, and the
        #          live controls of the run that is in flight (the rest is
        #          hidden, not greyed: a console shows what it can do NOW).
        on = mode != MODE_OFF
        self._ui.w_off.setVisible(not on)
        self._ui.w_on.setVisible(on)
        if not on:
            return
        moving = mode == MODE_MOVING
        busy = mode in (MODE_CAPTURING, MODE_FOLLOWING)
        following = mode == MODE_FOLLOWING
        # the pointing commands have nothing to say while the run owns the
        # mount, and the capture commands have nothing to say while it moves
        self._ui.cmd_point.setEnabled(not busy)
        self._ui.cmd_capture.setEnabled(not moving and not following)
        # the progress line belongs to the run in flight
        self._ui.follow_box.setVisible(following)

    def set_backend_hint(self, backend, host, port, configured):
        # @args: backend - the display name ("CCDciel", "NINA / PINS"),
        #        host/port - where the app will look, configured - whether
        #        Settings carries a backend at all
        # @return: None. The disconnected state says WHERE it will look, so
        #          the observer can tell "not configured" from "not running".
        if configured:
            where = f"{host}:{port}"
        else:
            where = self.tr("no backend configured yet")
        self._ui.lbl_where.setText(
            f"{where} · " + self.tr("set it up in Settings → Integrations"))
