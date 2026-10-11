############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The assistant window (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The non-modal assistant window (ADR-075).

One conversation, a scope selector on top, and the ground behind each
scope supplied by the host: the object's brief, the app's documents, or the
editor's state. The window itself decides nothing: it sends the question
with the ground through `AssistantWorker` and paints the answer and the
sources the assistant injected.

It is non-modal and remembers nothing: the history lives in this window
while it is open, and closing it forgets the conversation. No bubbles, no
automatic questions: the observer asks.
"""

import html as _html
import logging

from PySide6.QtWidgets import QDialog

from ..config import config
from ..core import assistant
from ..core.sources import llm
from .ui_loader import adopt_ui

logger = logging.getLogger(__name__)


class AssistantWindow(QDialog):
    # @args: object_name - the current project's name (enables the object
    #          scope) or None,
    #        brief_provider - callable() -> brief dict, built in the WORKER
    #          (it may enrich over the network),
    #        editor_state_provider - callable() -> state dict, read on the
    #          GUI thread (it reads widgets); None hides the editor scope,
    #        start_scope - which scope to open on,
    #        parent - parent widget

    def __init__(self, object_name=None, brief_provider=None,
                 editor_state_provider=None, start_scope=assistant.SCOPE_APP,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Assistant (experimental)"))
        self._ui = adopt_ui(self, "assistant_window")
        self._object_name = (object_name or "").strip()
        self._brief_provider = brief_provider
        self._editor_provider = editor_state_provider
        self._history = []
        self._worker = None

        # the scopes this window can offer, in a stable order
        scopes = []
        if self._object_name:
            scopes.append((assistant.SCOPE_OBJECT,
                           self.tr("This object: %1").replace(
                               "%1", self._object_name)))
        scopes.append((assistant.SCOPE_APP,
                       self.tr("The app (guide and ADRs)")))
        if editor_state_provider is not None:
            scopes.append((assistant.SCOPE_EDITOR, self.tr("The editor")))
        for key, label in scopes:
            self._ui.cmb_scope.addItem(label, key)
        idx = self._ui.cmb_scope.findData(start_scope)
        self._ui.cmb_scope.setCurrentIndex(idx if idx >= 0 else 0)

        self._ui.btn_send.clicked.connect(self._send)
        self._ui.edt_question.returnPressed.connect(self._send)
        self._ui.btn_clear.clicked.connect(self._clear)
        self._ui.cmb_scope.currentIndexChanged.connect(
            lambda _i: self._update_context_label())
        self._ui.buttonBox.rejected.connect(self.close)

        if not llm.is_enabled(config):
            self._ui.btn_send.setEnabled(False)
            self._ui.edt_question.setEnabled(False)
            if not config.get("ai_enabled"):
                self._ui.lbl_hint.setText(self.tr(
                    "The AI is off: turn it on in Settings → Integrations."))
            else:
                self._ui.lbl_hint.setText(self.tr(
                    "Configure a language model in Settings → Integrations "
                    "to use the assistant."))
        self._update_context_label()
        self.resize(620, 520)

    def _current_scope(self):
        # @return: the scope key of the combo
        return self._ui.cmb_scope.currentData()

    def _update_context_label(self):
        # Says, in one line, what the next answer will be grounded on.
        scope = self._current_scope()
        if scope == assistant.SCOPE_OBJECT:
            txt = self.tr("Your own data for %1").replace(
                "%1", self._object_name)
        elif scope == assistant.SCOPE_EDITOR:
            txt = self.tr("The editor's state and the guide")
        else:
            txt = self.tr("The user guide and the ADRs")
        self._ui.lbl_context.setText(txt)

    def _append(self, role, text):
        # @args: role - "user"|"assistant"|"error", text - the message
        who = {"user": self.tr("You"), "assistant": self.tr("Assistant"),
               "error": self.tr("Error")}.get(role, role)
        safe = _html.escape(text or "").replace("\n", "<br>")
        self._ui.txt_log.append(f"<p><b>{who}:</b> {safe}</p>")

    def _send(self):
        if self._worker is not None and self._worker.isRunning():
            return
        question = self._ui.edt_question.text().strip()
        if not question:
            return
        scope = self._current_scope()
        # the editor's state is read HERE (it touches widgets); the brief is
        # built in the worker (it may enrich over the network)
        state = None
        if scope == assistant.SCOPE_EDITOR and self._editor_provider:
            state = self._editor_provider()
        self._append("user", question)
        past = list(self._history)
        self._history.append({"role": "user", "content": question})
        self._ui.edt_question.clear()
        self._ui.btn_send.setEnabled(False)
        self._ui.lbl_sources.setText("")
        self._ui.progress.setVisible(True)
        self._ui.lbl_hint.setText(self.tr("Thinking…"))
        from .workers import AssistantWorker, hold
        self._worker = hold(AssistantWorker(
            config, scope, question, past,
            brief_provider=(self._brief_provider
                            if scope == assistant.SCOPE_OBJECT else None),
            editor_state=state))
        self._worker.done.connect(self._done)
        self._worker.start()

    def _done(self, answer, sources, err):
        self._ui.progress.setVisible(False)
        if llm.is_enabled(config):
            self._ui.btn_send.setEnabled(True)
        self._ui.lbl_hint.setText("")
        if err:
            self._append("error", self.tr("The assistant failed: ") + err)
            return
        self._append("assistant", answer)
        self._history.append({"role": "assistant", "content": answer})
        if sources:
            self._ui.lbl_sources.setText(
                self.tr("Sources: ") + " · ".join(sources))
        else:
            self._ui.lbl_sources.setText(self.tr(
                "No sources: there was nothing to ground the answer on."))

    def _clear(self):
        self._ui.txt_log.clear()
        self._ui.lbl_sources.setText("")
        self._history = []

    def closeEvent(self, event):
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(2000)
        super().closeEvent(event)
