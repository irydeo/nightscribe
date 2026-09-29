############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Single-document dialog (Guide, What's new, sources)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog

from . import markdown
from .doc_viewer import _DOC_STYLE
from .ui_loader import adopt_ui


class DocDialog(QDialog):
    # One curated markdown page, no tree (ADR-053): the friendly door
    # for Guide, What's new and Data sources. Local .md links in the
    # document cross into the full docs browser (that one has the tree);
    # anything else goes to the OS browser.
    # @args: parent - owning window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = None
        self.setWindowTitle(self.tr("Document"))
        self.resize(900, 640)
        self.setStyleSheet(_DOC_STYLE)

        # the structure is the Designer file's (ADR-005); the page style
        # is the doc browser's shared constant, applied here
        self._ui = adopt_ui(self, "doc_dialog")
        self._view = self._ui.view
        self._view.anchorClicked.connect(self._on_link)

    # ---- content ----------------------------------------------------------

    def show_file(self, path):
        # Loads and renders the markdown file.
        # @args: path - the markdown file to render
        # @return: True when the file was read and shown

        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return False
        self._current = Path(path)
        self._view.setHtml(markdown.to_html(text))
        return True

    # ---- links ------------------------------------------------------------

    def _on_link(self, url):
        # .md links stay in the app and open in the full docs browser;
        # the rest goes to the OS browser (same rule as the doc viewer).
        # @args: url - the clicked QUrl

        target = url.toString()
        if target.endswith(".md"):
            cand = Path(target)
            if not cand.is_absolute() and self._current is not None:
                cand = (self._current.parent / target).resolve()
            if cand.is_file():
                from .doc_viewer import open_browser
                open_browser(cand.parent, self, start=cand)
                return
        QDesktopServices.openUrl(url)


def open_doc(docs_root, base, title, locale, parent):
    # Shows a curated one-pager, modal (ADR-053): the language twin of
    # the doc (X.es.md preferred for "es" when it exists, else X.md).
    # @args: docs_root - the docs folder, base - the doc name without
    #        the extension (e.g. "GUIDE"), title - the window title,
    #        locale - "es" or "en", parent - owning window
    # @return: True when a file was shown, False when the doc is missing

    root = Path(docs_root)
    order = (root / f"{base}.es.md", root / f"{base}.md") \
        if locale == "es" else (root / f"{base}.md", root / f"{base}.es.md")
    file = next((cand for cand in order if cand.is_file()), None)
    if file is None:
        return False
    dlg = DocDialog(parent)
    dlg.setWindowTitle(title)
    if not dlg.show_file(file):
        return False
    dlg.exec()
    return True
