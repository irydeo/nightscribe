############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Campaign pass dialog module (E5c)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The campaign pass, as the observer sees it (E5c).

Several projects of one campaign may look at the same field, and then the
comparison stars are the same for all of them: measuring them one by one
would measure the SAME stars once per project. This dialog prepares ONE
pass: which visit holds the shared frames, which sequence is compared
against, and which sibling objects travel in it.

It decides no science: the grouping by field, the sequence precedence and
the "no usable pointing" refusal come from core.campaign and from the
reference frame's own WCS, and this dialog shows them plainly, including
WHO IS LEFT OUT and why. A project that vanished from a pass in silence
would be exactly the kind of loss this app refuses.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                               QListWidgetItem)

from ..core import (campaign, fits_io, followup, project,
                    wcs as wcs_mod)
from ..core.db import db
from .ui_loader import adopt_ui

logger = logging.getLogger(__name__)

# Bands a pass can be measured in when the campaign says nothing. They are
# the Johnson-Cousins set the rest of the app uses, plus Clear.
_COMMON_BANDS = ("V", "B", "Rc", "Ic", "Clear")


class PassDialog(QDialog):
    # Chooses the source visit, the shared sequence and the objects of a
    # pass, and refuses to promise what it cannot deliver: without a
    # pointing for the reference frame there is no way to know where an
    # object falls on the pixels, and the dialog says so instead of
    # measuring somewhere arbitrary.
    #
    # @args: db_obj - the Database, camp - the campaign dict,
    #        lang - the observer's language ("es"|"en"), parent - the
    #        owning window
    # @return: after exec(), source()/targets()/sequence()/band() answer

    def __init__(self, parent=None, db_obj=None, camp=None, lang="es"):
        super().__init__(parent)
        self._db = db_obj or db
        self._camp = camp or {}
        self._lang = lang
        self._projects = campaign.projects_of(self._db, self._camp.get("id"),
                                              status="active")
        self._visits = self._source_visits()
        self._wcs = None
        self._group = {"targets": [], "left_out": []}
        self._ui = adopt_ui(self, "pass_dialog")
        self.setWindowTitle(self.tr("Measure the campaign pass"))
        self.cmb_visit = self._ui.cmb_visit
        self.cmb_sequence = self._ui.cmb_sequence
        self.cmb_band = self._ui.cmb_band
        self.lst_targets = self._ui.lst_targets
        self.lbl_wcs = self._ui.lbl_wcs
        self.lbl_left = self._ui.lbl_left
        self._ui.buttonBox.accepted.connect(self.accept)
        self._ui.buttonBox.rejected.connect(self.reject)
        self._fill_visits()
        self._fill_bands()
        self.cmb_visit.currentIndexChanged.connect(self._reload)
        self.cmb_sequence.currentIndexChanged.connect(self._reload)
        self._reload()

    # ---------------- what the pass can be built from ----------------

    def _source_visits(self):
        # Every visit of every project of the campaign that holds FITS
        # frames is a candidate source: a pass measures what was already
        # filed, so the frames come from a visit and never from a folder.
        # @return: [{"pid", "object_name", "session_id", "obs_date",
        #            "paths"}]
        out = []
        for p in self._projects:
            for s in followup.list_sessions(self._db, p["id"]):
                files = project.files_for_session(self._db, s["id"])
                paths = sorted(f["path"] for f in files
                               if f.get("kind") == "fits" and f.get("path"))
                if not paths:
                    continue
                out.append({"pid": p["id"],
                            "object_name": p["object_name"],
                            "session_id": s["id"],
                            "obs_date": s.get("obs_date"),
                            "paths": paths})
        return out

    def _sequence_choices(self):
        # The sequences a pass can measure with: the campaign's shared one
        # and each project's own. The precedence (the project's wins) is
        # core.campaign's; here they are only OFFERED, with their origin
        # spelled out.
        # @return: [(label, sequence, source, project_id)]
        out = []
        shared = campaign.sequence_of(self._camp)
        if shared:
            out.append((self.tr("Campaign's shared sequence ({0} stars)"
                                ).format(len(shared.get("entries") or [])),
                        shared, "campaign", None))
        for p in self._projects:
            own = (p.get("context") or {}).get("sequence")
            if isinstance(own, dict) and own.get("entries"):
                out.append((self.tr("{0}'s own sequence ({1} stars)").format(
                    p["object_name"], len(own["entries"])),
                    own, "project", p["id"]))
        return out

    def _fill_visits(self):
        self.cmb_visit.clear()
        for v in self._visits:
            self.cmb_visit.addItem(
                "{} · {} ({})".format(v["object_name"], v["obs_date"] or "",
                                      len(v["paths"])),
                v)
        if not self._visits:
            self.cmb_visit.addItem(self.tr("(no visit has FITS frames)"),
                                   None)

    def _fill_bands(self):
        # The campaign's own filters first (that is the protocol), then the
        # common set, without repeating anything.
        self.cmb_band.clear()
        seen = []
        for b in (self._camp.get("protocol") or {}).get("filters") or []:
            if b and b not in seen:
                seen.append(b)
        for b in _COMMON_BANDS:
            if b not in seen:
                seen.append(b)
        for b in seen:
            self.cmb_band.addItem(b, b)

    # ---------------- the preview, recomputed on every change --------

    def _reload(self):
        # Rebuilds the whole preview from the current choices: the
        # reference frame's pointing, the sequence, and who travels.
        visit = self.cmb_visit.currentData()
        self._fill_sequences(visit)
        self._wcs = self._reference_wcs(visit)
        self._show_pointing(visit)
        self._build_targets(visit)
        ok = self._ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(bool(self._wcs) and bool(visit)
                      and bool(self._checked_targets()))

    def _fill_sequences(self, visit):
        # Keeps the chosen sequence when it is still available (the user
        # picked it on purpose); otherwise pre-selects the campaign's, or
        # the source project's own.
        keep = self.cmb_sequence.currentData()
        self.cmb_sequence.blockSignals(True)
        self.cmb_sequence.clear()
        for label, seq, source, pid in self._sequence_choices():
            self.cmb_sequence.addItem(label, {"sequence": seq,
                                              "source": source,
                                              "project_id": pid})
        if not self.cmb_sequence.count():
            self.cmb_sequence.addItem(
                self.tr("(the campaign has no sequence yet)"), None)
        want = None
        if keep:
            for i in range(self.cmb_sequence.count()):
                data = self.cmb_sequence.itemData(i)
                if data and data.get("source") == keep.get("source") \
                        and data.get("project_id") == keep.get("project_id"):
                    want = i
        if want is None and visit is not None:
            for i in range(self.cmb_sequence.count()):
                data = self.cmb_sequence.itemData(i)
                if data and data.get("project_id") == visit["pid"]:
                    want = i
        if want is None:
            want = 0
        self.cmb_sequence.setCurrentIndex(want)
        self.cmb_sequence.blockSignals(False)

    def _reference_wcs(self, visit):
        # The pointing of the reference frame, from its own header. This
        # is the precondition of a pass and the reason it is stated out
        # loud: an object's place on the pixels can only be known if the
        # frame knows where it was looking (ADR-051 writes the solved WCS
        # back into the header, which is what makes solving it worthwhile).
        # @return: a Wcs, or None
        if not visit:
            return None
        try:
            header = fits_io.read_header(visit["paths"][0])
        except Exception as err:
            logger.warning("could not read the reference header: %s", err)
            return None
        return wcs_mod.Wcs.from_header(header)

    def _show_pointing(self, visit):
        if not visit:
            self.lbl_wcs.setText(self.tr(
                "This campaign has no visit with frames yet: capture a "
                "night first."))
            return
        if self._wcs is None:
            self.lbl_wcs.setText(self.tr(
                "⚠ The reference frame has no usable pointing (no WCS in "
                "its header). Without it there is no way to know where "
                "each object falls on the pixels: resolve one frame of "
                "this visit (Tools → FITS editor → Solve) and try again."))
            return
        self.lbl_wcs.setText(self.tr(
            "Reference frame: {0} — pointing from its own header. Each "
            "object's place on the pixels comes from it."
        ).format(visit["paths"][0].rsplit("/", 1)[-1]))

    def _build_targets(self, visit):
        # Who travels in the pass: the campaign's projects of the same
        # field (core.campaign decides, this only shows it), minus those
        # that do not even fall inside the reference frame's pixels.
        seq_data = self.cmb_sequence.currentData() or {}
        seq = seq_data.get("sequence") or {}
        self._group = campaign.group_by_field(
            self._projects, fov_arcmin=seq.get("fov_arcmin"))
        self.lst_targets.clear()
        reference = self._group.get("reference")
        left = list(self._group.get("left_out") or [])
        for p in self._group.get("targets") or []:
            ctx = p.get("context") or {}
            xy, why = self._pixel_of(ctx, visit)
            if xy is None:
                # inside the FIELD of the campaign but outside the FRAME:
                # a good sibling that simply cannot be measured on this
                # shot, and it is reported rather than assumed
                left.append({"project": p, "reason": why})
            item = QListWidgetItem(
                "{} · {}".format(p["object_name"], why)
                if why else p["object_name"])
            item.setData(Qt.UserRole, {"pid": p["id"],
                                       "label": p["object_name"],
                                       "xy": xy, "why": why})
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if xy is None:
                # inside the field but outside the frame: it cannot be
                # measured, and it is said rather than assumed
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
            self.lst_targets.addItem(item)
        self._left = left
        self.lbl_left.setText(self._left_text(left))
        txt = self.tr("Objects measured in this pass:")
        if reference is not None:
            txt = self.tr("Objects measured in this pass (centre: {0}):"
                          ).format(reference["object_name"])
        self._ui.lbl_targets.setText(txt)

    def _pixel_of(self, ctx, visit):
        # Where this project's object falls on the reference frame.
        # @return: ((x, y), None) or (None, bilingual reason dict)
        if not self._wcs or not visit:
            return None, {"es": "sin punto de referencia",
                          "en": "no pointing"}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            return None, {"es": "sin posición guardada",
                          "en": "no saved position"}
        try:
            x, y = self._wcs.sky_to_pixel(float(ra), float(dec))
        except Exception:
            return None, {"es": "fuera de la proyección",
                          "en": "outside the projection"}
        h = self._wcs.naxis2 if getattr(self._wcs, "naxis2", None) else None
        w = self._wcs.naxis1 if getattr(self._wcs, "naxis1", None) else None
        if w and h and not (0 <= x < w and 0 <= y < h):
            return None, {"es": "fuera del encuadre de la toma de referencia",
                          "en": "outside the reference frame"}
        return (float(x), float(y)), None

    def _left_text(self, left):
        # The excluded projects, each with its reason: the panel must be
        # able to answer "why is my project not in this pass?".
        if not left:
            return ""
        lines = [self.tr("Left out of this pass:")]
        for entry in left:
            name = (entry.get("project") or {}).get("object_name") or "?"
            reason = entry.get("reason") or {}
            lines.append("• {} — {}".format(name, self._say(reason)))
        return "\n".join(lines)

    def _say(self, reason):
        # @args: reason - {"es", "en"} or None
        # @return: the reason in the observer's language, never empty when
        #          a reason exists
        if not reason:
            return ""
        return (reason.get(self._lang) or reason.get("en")
                or reason.get("es") or "")

    # ---------------- what the caller runs ----------------

    def source(self):
        # @return: the chosen visit dict or None
        return self.cmb_visit.currentData()

    def wcs(self):
        # The reference frame's pointing, resolved from its own header.
        # @return: a Wcs or None (the dialog refuses to accept without one)
        return self._wcs

    def sequence(self):
        # @return: (sequence or None, source)
        data = self.cmb_sequence.currentData() or {}
        return data.get("sequence"), data.get("source")

    def band(self):
        # @return: the chosen band
        return self.cmb_band.currentData() or "V"

    def _checked_targets(self):
        out = []
        for i in range(self.lst_targets.count()):
            item = self.lst_targets.item(i)
            data = item.data(Qt.UserRole) or {}
            if data.get("xy") is not None \
                    and item.checkState() == Qt.Checked:
                out.append(data)
        return out

    def targets(self):
        # @return: [{"pid", "label", "xy", "why"}] in the reference frame's
        #          pixels, exactly what the engine is handed
        return self._checked_targets()

    def left_out(self):
        # @return: [{"project", "reason"}] every project the dialog told
        #          the observer it was leaving out, whether it fell outside
        #          the campaign's field or outside the reference frame
        return list(getattr(self, "_left", None) or [])
