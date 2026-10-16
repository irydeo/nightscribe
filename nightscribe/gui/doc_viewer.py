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
from .ui_loader import adopt_ui

# The docs live at the repo root (source) or bundled (PyInstaller); the
# browser renders the selected .md in a QTextBrowser, so the reader never
# leaves the application (ADR-013: documentation belongs to the project,
# this is its GUI door).
#
# WHAT THE TREE SHOWS (ADR-070 rev, 2026-10-16). The manual opens on the
# user guide: that is what the observer came for. Under it, the two topic
# documents the app's own "?" buttons open are part of the manual too.
# Everything else (the topic documents for enthusiasts and the design
# decisions) lives behind its own COLLAPSED "Advanced documentation"
# branch: reachable, but never in the way of a first read. The work plans
# (docs/PLANS) are not listed at all: they are the project's own notebooks.

# Topic docs the app opens from a "?" button, so they belong to the manual.
_REFERENCED = ("UFE", "SEQUENCES")

# The advanced guide's topic documents, in reading order. Their titles come
# from each file's own H1, so a renamed document cannot drift from the list.
_ADVANCED = ("ARCHITECTURE", "DESIGN", "WORKFLOWS", "DEVELOPING",
             "DATA_SOURCES", "SCORING", "ORBITS", "CAMPAIGNS", "HADS",
             "PHOTOMETRY", "SEQUENCES", "ASTROMETRY", "PRECISION", "SNR",
             "UFE", "UI_EXPORTS", "VIZ", "MPC_SUBMISSION",
             "unified-fits-editor")


def _lang_of(path):
    # @args: path - a doc file name or a path
    # @return: "es" when it is the Spanish twin, "en" otherwise
    return "es" if str(path).endswith(".es.md") else "en"


def _pick(folder, stem, lang):
    # @args: folder - where the doc lives, stem - its name without ".md",
    #        lang - "en" | "es"
    # @return: the file to read: this language's twin, or the other one when
    #          the document has only one language (better than hiding it)
    order = ((f"{stem}.es.md", f"{stem}.md") if lang == "es"
             else (f"{stem}.md", f"{stem}.es.md"))
    for name in order:
        cand = folder / name
        if cand.is_file():
            return cand
    return None

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

    def __init__(self, docs_root, parent=None, lang=None):
        super().__init__(parent)
        self._root = Path(docs_root)
        self._current = None
        # the language of the tree: the app's own when the caller says so,
        # else read from the file it was asked to open (the "?" doors know
        # which twin they want)
        self._lang = lang or "en"
        self._default = None
        self.setWindowTitle(self.tr("Documentation"))
        self.resize(1100, 760)
        self.setStyleSheet(_TREE_STYLE)

        # the structure is the Designer file's (ADR-005); the tree's
        # content and the page styles are data, applied here
        self._ui = adopt_ui(self, "doc_viewer")
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
        # The manual first (expanded), then the advanced guide (collapsed).
        # Only ONE language is listed: the reader asked for their own.
        user = self._root / "user"
        if user.is_dir():
            branch = self._branch(self.tr("User guide"), expanded=True)
            for path in self._language_files(user):
                self._add_item(branch, path)
            self._default = _pick(user, "README", self._lang)
        # the topic docs the app's own "?" buttons open: manual material
        for stem in _REFERENCED:
            path = _pick(self._root, stem, self._lang)
            if path:
                self._add_item(self._tree.invisibleRootItem(), path)
        # the advanced guide: the topic documents and the design decisions
        advanced = self._branch(self.tr("Advanced documentation"))
        for stem in _ADVANCED:
            path = _pick(self._root, stem, self._lang)
            if path:
                self._add_item(advanced, path)
        adr = self._root / "adr"
        if adr.is_dir():
            adr_branch = self._branch(self.tr("Design decisions (ADR)"),
                                      expanded=False)
            for path in self._language_files(adr):
                self._add_item(adr_branch, path)

    def _branch(self, name, expanded=False):
        # @args: name - the branch label, expanded - open it right away
        # @return: the new top-level branch item (no file behind it)
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.UserRole, None)
        self._tree.addTopLevelItem(item)
        item.setExpanded(expanded)
        return item

    def _language_files(self, folder):
        # @args: folder - a docs folder
        # @return: one file per document, this language's twin when it
        #          exists, README first and the numbered chapters in order
        stems = []
        for f in sorted(folder.glob("*.md")):
            stem = f.name[:-len(".md")]
            if stem.endswith(".es"):
                stem = stem[:-len(".es")]
            if stem not in stems:
                stems.append(stem)
        stems.sort(key=lambda s: (s != "README", s))
        out = []
        for stem in stems:
            path = _pick(folder, stem, self._lang)
            if path:
                out.append(path)
        return out

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
        # @return: the manual's own index (README) when it is there, else the
        #          first file the tree offers
        if self._default is not None and self._default.is_file():
            return self._default
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data:
                return Path(data)
            if item.childCount():
                child = item.child(0)
                return Path(child.data(0, Qt.UserRole))
        return None

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


def open_browser(docs_root, parent, start=None, lang=None):
    # Shows the documentation browser (modal).
    # @args: docs_root - docs folder, parent - main window,
    #        start - initial .md file or None,
    #        lang - "en" | "es" for the tree; when omitted it is read from
    #        the file being opened (the "?" doors pass the twin they want)
    if lang is None and start is not None:
        lang = _lang_of(start)
    dialog = DocViewer(docs_root, parent, lang=lang)
    if not (start and dialog.show_file(start)):
        first = dialog.default_file()
        if first:
            dialog.show_file(first)
    dialog.exec()
