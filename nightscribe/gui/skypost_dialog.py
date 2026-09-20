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
core/narrative.sky_draft into two copyable boxes. Code-built like the
other small dialogs — no Designer file.
"""

from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)


class SkyPostDialog(QDialog):
    # @args: draft - {"es": str, "en": str} from narrative.sky_draft,
    #        parent - parent widget

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sky post draft"))
        lay = QVBoxLayout(self)
        self.edits = {}
        for lang, title in (("es", self.tr("Spanish draft")),
                            ("en", self.tr("English draft"))):
            lay.addWidget(QLabel(title))
            edt = QPlainTextEdit(draft.get(lang, ""))
            edt.setReadOnly(True)
            lay.addWidget(edt)
            btn = QPushButton(self.tr("Copy %1").replace(
                "%1", lang.upper()))
            btn.clicked.connect(lambda _c=False, e=edt:
                                QApplication.clipboard().setText(
                                    e.toPlainText()))
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(btn)
            lay.addLayout(row)
            self.edits[lang] = edt
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.resize(640, 520)
