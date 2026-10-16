############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC report controller module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The MPC report window and its flow, written once (ADR-080).

The two windows are dumb: `ufe_report_dialog.ui` shows the report and its
actions, `ufe_mpc_send_dialog.ui` asks for what a submission needs. WHO fills
the report and WHERE the observations come from is what changes: the editor's
Astrometry tab has the run on stage, and a visit has its own run. That "who"
lives here, so the two paths cannot drift apart: the same window is opened,
the same judge validates what goes in it, and the same worker sends it. Each
owner only supplies its data through the small hooks below.

The report text is still built by the owner: the generator needs the points,
the designation and the notes, and those belong to whoever measured them.
Everything downstream of the text (fill, state, copy, save, register, send)
is shared and lives here.
"""

from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QFileDialog

from ..config import config
from .mpc_send_dialog import MpcSendDialog
from .ufe_report_dialog import UfeReportDialog


class MpcReportController(QObject):
    """Owns the report window, the send window and the flow between them."""

    def __init__(self, parent, build, *, is_neocp=None, object_name=None,
                 save_dir=None, on_saved=None, on_report=None, say=None):
        # @args: parent - the owning widget (also the windows' parent),
        #        build - callable(fmt, submission, quiet) -> dict with "text"
        #        and "kept", or None when there is nothing to report yet,
        #        is_neocp - callable() -> True while the object is on the
        #        confirmation page (the send dialog's default target),
        #        object_name - callable() -> the object's name (the saved
        #        file's default name), save_dir - callable() -> the folder the
        #        save dialog opens on (None = the home folder), on_saved -
        #        callable(path, text) after a successful save (the owner
        #        registers the file where it belongs), on_report - callable()
        #        after a report is filled (the owner resyncs its buttons),
        #        say - callable(text) for the owner's status line
        # @return: None
        super().__init__(parent)
        self._build = build
        self._is_neocp = is_neocp or (lambda: False)
        self._object_name = object_name or (lambda: "")
        self._save_dir = save_dir
        self._on_saved = on_saved
        self._on_report = on_report
        self._say = say or (lambda _text: None)
        # the submission parameters the report's ACK line carries; the send
        # dialog refines them and the report is rebuilt with them
        self.submission = {"ack": "", "obj_type": ""}
        self._kept = 0
        self._dirty = False
        self._submit_worker = None
        self.dialog = UfeReportDialog(parent)
        self.send = MpcSendDialog(parent)
        self._wire()

    # ------------------------------------------------------------ wiring

    def _wire(self):
        # @return: None. The report is EDITABLE (the observer's ask,
        #          2026-10-14): a wrong designation or a line can be fixed
        #          before sending; Regenerate rebuilds it from the
        #          measurements and clears the edit. The format combo rebuilds
        #          it too, because the format is part of the text.
        self.dialog.cmb_format.currentIndexChanged.connect(
            lambda _i: self.regenerate(quiet=True))
        self.dialog.btn_regen.clicked.connect(
            lambda: self.regenerate(quiet=True))
        self.dialog.btn_copy.clicked.connect(self.copy)
        self.dialog.btn_save.clicked.connect(self.save)
        self.dialog.btn_send.clicked.connect(self.open_send)
        self.dialog.btn_close.clicked.connect(self.dialog.hide)
        self.dialog.txt_report.textChanged.connect(self._on_edited)
        self.send.btn_close.clicked.connect(self.send.hide)
        self.send.btn_send.clicked.connect(self.submit)
        # The intro quotes what is about to go out and follows the target and
        # the mode, so it never goes stale (the app talks first, ADR-038).
        self.send.cmb_target.currentIndexChanged.connect(
            lambda _i: self.refresh_intro())
        self.send.cmb_mode.currentIndexChanged.connect(
            lambda _i: self.refresh_intro())
        from ..core.sources import mpc_submit
        self.send.set_targets(mpc_submit.TARGETS)

    # ------------------------------------------------------------ state

    @property
    def fmt(self):
        # @return: the generator's key for the chosen format
        return self.dialog.cmb_format.currentData() or "ades"

    @property
    def text(self):
        # @return: the report as it reads in the box
        return self.dialog.txt_report.toPlainText()

    @property
    def kept(self):
        # @return: how many observations the report in the box carries
        return self._kept

    @property
    def edited(self):
        # @return: True when the observer changed the report text
        return self._dirty

    # ------------------------------------------------------------ the report

    def regenerate(self, quiet=False):
        # @args: quiet - True when the rebuild is not news (a reopen, or the
        #        format combo changed): the text is replaced, nothing is said
        # @return: True when a report landed in the box. An empty build (no
        #          measurements yet) leaves the box untouched.
        out = self._build(self.fmt, self.submission, quiet)
        if not out or not str(out.get("text") or "").strip():
            return False
        self.fill(out["text"], int(out.get("kept") or 0))
        return True

    def fill(self, text, kept):
        # @args: text - the generated report, kept - the observations it
        #        carries
        # @return: None. Putting the text in the box fires textChanged; the
        #          dirty flag is cleared AFTER it, because a freshly generated
        #          report is not an edit.
        self.dialog.txt_report.setPlainText(text)
        self._kept = int(kept or 0)
        self._dirty = False
        self.paint_state()
        # the intro describes the report that was just put in the box
        self.refresh_intro()
        if self._on_report is not None:
            self._on_report()

    def _on_edited(self):
        # @return: None. The observer touched the report: what is in the box
        #          is what gets sent, and the send dialog says so.
        if self.dialog.txt_report.toPlainText():
            self._dirty = True
        self.paint_state()

    def paint_state(self):
        # @return: None. Says, under the box, whether the report is the
        #          generated one or the observer's edited version.
        self.dialog.lbl_report_state.setText(self.tr(
            "Edited: this exact text will be sent (Regenerate to rebuild it "
            "from the measurements).") if self._dirty else "")

    def open_window(self):
        # @return: True when the window was shown. The report is rebuilt first,
        #          so the window never shows a stale one; with nothing to
        #          report it stays shut and the owner's build hook has said
        #          why (an empty window reads as broken).
        self.regenerate(quiet=True)
        if not self.text.strip():
            return False
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        return True

    def copy(self):
        # @return: None. The report as it reads, on the clipboard.
        text = self.text
        if not text.strip():
            return
        QApplication.clipboard().setText(text)
        self._say(self.tr("Report copied to the clipboard."))

    def save(self):
        # @return: None. Writes the report into a file the observer picks. The
        #          owner is told where it went, so it can register the file as
        #          its own resource (a visit's report hangs from the visit).
        text = self.text
        if not text.strip():
            return
        obj = self._object_name() or "report"
        suffix = {"mpc80": "obs80.txt", "ades": "ades.psv", "xml": "ades.xml"}
        name = f"{obj}_{suffix.get(self.fmt, 'report.txt')}"
        base = Path.home()
        if self._save_dir is not None:
            base = Path(self._save_dir() or base)
        default = str(base / name)
        out, _sel = QFileDialog.getSaveFileName(
            self.parent(), self.tr("Save MPC report"), default,
            self.tr("All files (*)"))
        if not out:
            return
        try:
            Path(out).write_text(text.rstrip() + "\n", encoding="utf-8")
        except OSError as err:
            self._say(self.tr("The report could not be written:") + f" {err}")
            return
        if self._on_saved is not None:
            self._on_saved(out, text)
        else:
            self._say(self.tr("Report saved:") + f" {out}")

    # ------------------------------------------------------------ sending

    def open_send(self):
        # @return: None. Sending is never silent (ADR-080): the dialog asks
        #          for the acknowledgement email, the target and the mode.
        if not self.text.strip():
            self._say(self.tr("There is no report to send."))
            return
        self.send.edt_ack_email.setText(
            self.send.edt_ack_email.text()
            or str(config.get("observer_email", "") or ""))
        # The target starts at the project's own kind, as the manual promises:
        # NEOCP for a project on the confirmation page, Unclassified otherwise.
        # The old guard also asked for an EMPTY combo, and set_targets had
        # already filled it, so the default never applied (measured
        # 2026-10-13: a NEOCP project opened on Unclassified). It is set on
        # every open, and the observer can still change it for this batch.
        default_target = "NEOCP" if self._is_neocp() else "Unclassified"
        idx = self.send.cmb_target.findData(default_target)
        if idx >= 0:
            self.send.cmb_target.setCurrentIndex(idx)
        # an edited report is sent as it reads, so the ACK/target fields do
        # not apply and the dialog says so (the observer's ask, 2026-10-14)
        self.send.set_edited(self._dirty)
        self.refresh_gate()
        self.refresh_intro()
        self.send.show()
        self.send.raise_()
        self.send.activateWindow()

    def refresh_intro(self):
        # @return: None. Says, above the log, what the batch carries: how many
        #          observations, the format, the target and the mode. Without
        #          it the window opened empty and looked broken; the target and
        #          the mode refresh it, so the line is never a stale claim
        #          about what is about to go out (the app talks first, ADR-038).
        kept = int(self._kept or 0)
        if not kept:
            self.send.lbl_intro.setText("")
            return
        self.send.lbl_intro.setText(self.tr(
            "Ready to send: %1 observation(s), format %2, target %3, "
            "mode %4. The MPC's own answer will appear below.").replace(
                "%1", str(kept)).replace(
                "%2", self.dialog.cmb_format.currentText()).replace(
                "%3", self.send.cmb_target.currentText()).replace(
                "%4", self.send.cmb_mode.currentText()))

    def refresh_gate(self):
        # @return: None. What the submission header still needs, said in the
        #          dialog, and the Send button blocked while anything is
        #          missing (ADR-080: the app never sends a half report).
        from ..core import mpc_astrometry
        ctx = mpc_astrometry.report_context(config)
        # the dialog's own field is the AC2 that will be sent, so it is the
        # one that decides: the config's email is only its prefill
        missing = [m for m in ctx.missing() if m != "the contact email"]
        email = self.send.edt_ack_email.text().strip()
        if not email:
            missing.append("the contact email")
        self.send.lbl_missing.setText(
            self.tr("Missing: %1. Set it in Settings → Observer, then send.")
            .replace("%1", ", ".join(missing)) if missing else "")
        self.send.btn_send.setEnabled(not missing)

    def submit(self):
        # @return: None. Builds the report with the chosen acknowledgement and
        #          target, then submits it off the GUI thread. The server's own
        #          answer lands in the dialog's log. When the observer EDITED
        #          the report, that text is sent verbatim and is NOT rebuilt
        #          (regenerating it would throw the edit away).
        from .workers import MpcSubmitWorker
        dlg = self.send
        email = dlg.edt_ack_email.text().strip()
        ack = dlg.edt_ack.text().strip()
        target = dlg.cmb_target.currentData() or ""
        test = bool(dlg.cmb_mode.currentData())
        self.submission = {"ack": ack, "obj_type": target}
        if self._dirty:
            dlg.log(self.tr("Sending your edited report as it reads."))
        else:
            # rebuild with the chosen ACK/target so the header carries them
            self.regenerate(quiet=True)
        text = self.text
        if not text.strip():
            dlg.log(self.tr("Nothing to send: the report is empty."))
            return
        mode = self.tr("Test") if test else self.tr("Normal")
        dlg.log(self.tr("Submitting (%1, %2)…").replace("%1", self.fmt)
                .replace("%2", mode))
        dlg.btn_send.setEnabled(False)
        self._submit_worker = MpcSubmitWorker(
            self.fmt, text, ack=ack, email=email, obj_type=target, test=test)
        self._submit_worker.finished.connect(self._on_submit_done)
        self._submit_worker.start()

    def _on_submit_done(self, out):
        # @args: out - mpc_submit.submit's dict
        # @return: None. The server's own words, and the button armed again.
        dlg = self.send
        self._submit_worker = None
        ok = bool(out.get("ok"))
        dlg.log((self.tr("The MPC accepted the batch:") if ok else
                 self.tr("The MPC did NOT accept the batch:")))
        dlg.log(str(out.get("text") or "").strip()[:2000])
        dlg.log(self.tr("URL: %1").replace("%1", str(out.get("url") or "")))
        if ok:
            self._say(self.tr("Report submitted to the MPC."))
        else:
            self._say(self.tr("The MPC did not accept the report: see the "
                              "send window."))
        self.refresh_gate()
