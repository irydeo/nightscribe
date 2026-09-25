############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - In-app documentation browser
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QTreeWidgetItem

from . import markdown
from .ui_loader import load_ui

# The docs live at the repo root (source) or bundled (PyInstaller); the
# browser lists every .md file and renders the selected one in a
# QTextBrowser, so the reader never leaves the application (ADR-013:
# documentation belongs to the project, this is its GUI door).

_TREE_STYLE = (
    "QDialog { background: #171a26; }"
    "QTreeWidget { background: #12141f; color: #dfe4f0;"
    " border: none; font-size: 12px; }"
    "QTreeWidget::item { padding: 4px 0; }"
    "QTreeWidget::item:selected { background: #2a3350; color: #ffffff; }"
    "QSplitter::handle { background: #232736; width: 3px; }"
    "QTextBrowser { background: #ffffff; color: #1b1f2a;"
    " padding: 14px 22px; }"
    "QTextBrowser a { color: #0a58ca; }"
    "QTextBrowser table { border: 1px solid #9aa4bd; border-collapse: collapse; }"
    "QTextBrowser th, QTextBrowser td { border: 1px solid #9aa4bd;"
    " padding: 3px 8px; }"
    "QTextBrowser th { background: #e8ecf5; }")

_DOC_STYLE = ("QTextBrowser { background-color: #ffffff; color: #1b1f2a; }"
              "a { color: #0a58ca; }"
              "table { border: 1px solid #9aa4bd; border-collapse: collapse; }"
              "th, td { border: 1px solid #9aa4bd; padding: 3px 8px; }"
              "th { background: #e8ecf5; }")


class DocViewer(QDialog):
    # Documentation browser: markdown file tree on the left, rendered
    # document on the right (light page). Local .md links navigate
    # inside the browser, http(s) links go to the OS browser.
    # @args: docs_root - folder that contains the docs, parent - window

    def __init__(self, docs_root, parent=None):
        super().__init__(parent)
        self._root = Path(docs_root)
        self._current = None
        self.setWindowTitle(self.tr("Technical Documentation"))
        self.resize(1100, 760)
        self.setStyleSheet(_TREE_STYLE)

        # the structure is the Designer file's (ADR-005); the tree's
        # content and the page styles are data, applied here
        self._ui = load_ui("doc_viewer", self)
        self.setLayout(self._ui.layout())   # no wrapper, no extra margins
        self._split = self._ui.split
        self._tree = self._ui.tree
        self._fill_tree()
        self._tree.itemClicked.connect(self._on_item)

        self._view = self._ui.view
        self._view.setStyleSheet(_DOC_STYLE)
        self._view.anchorClicked.connect(self._on_link)

        self._split.setStretchFactor(0, 0)
        self._split.setStretchFactor(1, 1)
        self._split.setSizes([240, 860])

    # ---- tree -------------------------------------------------------------

    def _fill_tree(self):
        # Groups the files: top-level docs first, then subfolders (adr/).
        files = sorted(f for f in self._root.iterdir()
                       if f.is_file() and f.suffix == ".md")
        dirs = sorted(d for d in self._root.iterdir() if d.is_dir())
        for f in files:
            self._add_item(self._tree.invisibleRootItem(), f)
        for d in dirs:
            if not any(p.is_file() and p.suffix == ".md"
                       for p in d.rglob("*")):
                continue
            dir_item = QTreeWidgetItem([d.name])
            dir_item.setData(0, Qt.UserRole, None)
            self._tree.addTopLevelItem(dir_item)
            for f in sorted(d.rglob("*.md")):
                self._add_item(dir_item, f)
        self._tree.expandAll()

    def _add_item(self, parent, path):
        # @args: parent - target tree branch, path - the .md file
        # @return: the new tree item (path stored in Qt.UserRole)
        item = QTreeWidgetItem([path.name])
        item.setData(0, Qt.UserRole, str(path))
        if parent is self._tree.invisibleRootItem():
            self._tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    # ---- rendering --------------------------------------------------------

    def _render(self, path):
        # Loads and shows one markdown file, highlighting it in the tree.
        # @args: path - .md file
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return False
        self._current = Path(path)
        self._view.setHtml(markdown.to_html(text))
        self._select_in_tree(self._current)
        return True

    def _select_in_tree(self, path):
        # Highlights and scrolls the tree to the matching item.
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            found = self._find_child(item, str(path))
            if found:
                self._tree.setCurrentItem(found)
                self._tree.scrollToItem(found)
                break

    def _find_child(self, item, want):
        data = item.data(0, Qt.UserRole)
        if data == want:
            return item
        for j in range(item.childCount()):
            found = self._find_child(item.child(j), want)
            if found:
                return found
        return None

    # ---- navigation -------------------------------------------------------

    def show_file(self, path):
        # Public entry: render a file and keep this dialog reusable.
        # @return: True if the file was rendered.
        return self._render(path)

    def default_file(self):
        # First top-level markdown file in the tree (WORKFLOWS in practice).
        item = self._tree.topLevelItem(0)
        data = item.data(0, Qt.UserRole)
        return Path(data) if data else None

    def _on_item(self, item, _col):
        path = item.data(0, Qt.UserRole)
        if path:
            self._render(Path(path))

    def _on_link(self, url):
        # .md links stay inside the browser (resolved against the current
        # file), http(s) and friends go to the OS browser.
        target = url.toString()
        if target.endswith(".md"):
            cand = Path(target)
            if not cand.is_absolute() and self._current:
                cand = (self._current.parent / target).resolve()
            if cand.is_file():
                self._render(cand)
                return
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(url)


def open_browser(docs_root, parent, start=None):
    # Shows the documentation browser (modal).
    # @args: docs_root - docs folder, parent - main window,
    #        start - initial .md file or None
    dialog = DocViewer(docs_root, parent)
    if not (start and dialog.show_file(start)):
        first = dialog.default_file()
        if first:
            dialog.show_file(first)
    dialog.exec()
