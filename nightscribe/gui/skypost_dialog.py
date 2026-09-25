############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - "Sky post" draft dialog (ADR-036, S3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The bilingual "sky today" draft dialog (ADR-036, S3): renders
core/narrative.sky_draft into two copyable boxes. The structure is
ui/skypost_dialog.ui (ADR-005, restored 2026-09-25).
"""

from PySide6.QtWidgets import QApplication, QDialog

from .ui_loader import adopt_ui


class SkyPostDialog(QDialog):
    # @args: draft - {"es": str, "en": str} from narrative.sky_draft,
    #        parent - parent widget

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sky post draft"))
        self._ui = adopt_ui(self, "skypost_dialog")
        # the drafts' contents and the copy labels are data (the label
        # carries the language tag), filled here
        self.edits = {}
        for lang in ("es", "en"):
            edt = getattr(self._ui, f"txt_{lang}")
            edt.setPlainText(draft.get(lang, ""))
            btn = getattr(self._ui, f"btn_copy_{lang}")
            btn.setText(self.tr("Copy %1").replace("%1", lang.upper()))
            btn.clicked.connect(lambda _c=False, e=edt:
                                QApplication.clipboard().setText(
                                    e.toPlainText()))
            self.edits[lang] = edt
        self._ui.buttonBox.rejected.connect(self.reject)
        self.resize(640, 520)
