############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the in-app documentation browser (ADR-070)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The offline manual opens on the user guide, in the app's own language,
with the two topic documents its "?" buttons need. Everything else (the
topic documents for enthusiasts, the design decisions) lives behind its own
collapsed "Advanced documentation" branch, and the work plans are not
listed at all: the browser is a manual, not a mirror of docs/. No network.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _fake_docs(tmp_path):
    # @return: a docs root with both languages, an ADR and a PLANS folder
    root = tmp_path / "docs"
    (root / "user").mkdir(parents=True)
    (root / "adr").mkdir()
    (root / "PLANS").mkdir()
    for name in ("README", "01-getting-started", "02-tonight"):
        (root / "user" / f"{name}.md").write_text(f"# {name} EN\n",
                                                  encoding="utf-8")
        (root / "user" / f"{name}.es.md").write_text(f"# {name} ES\n",
                                                     encoding="utf-8")
    for stem in ("UFE", "SEQUENCES", "PHOTOMETRY"):
        (root / f"{stem}.md").write_text(f"# {stem}\n", encoding="utf-8")
        (root / f"{stem}.es.md").write_text(f"# {stem} ES\n",
                                            encoding="utf-8")
    (root / "adr" / "ADR-001-pyside6.md").write_text("# ADR 1\n",
                                                     encoding="utf-8")
    (root / "adr" / "ADR-001-pyside6.es.md").write_text("# ADR 1 ES\n",
                                                        encoding="utf-8")
    (root / "PLANS" / "work.md").write_text("# plan\n", encoding="utf-8")
    return root


def _labels(view):
    # @return: {branch label: [file names under it]} for the whole tree
    out = {}
    for i in range(view._tree.topLevelItemCount()):
        item = view._tree.topLevelItem(i)
        data = item.data(0, Qt.UserRole)
        if data:                                   # a loose file
            out.setdefault("", []).append(os.path.basename(data))
            continue
        out[item.text(0)] = [os.path.basename(item.child(j).data(0, Qt.UserRole))
                             for j in range(item.childCount())]
    return out


def test_the_manual_comes_first_and_the_plans_are_not_listed(qapp, tmp_path):
    from nightscribe.gui.doc_viewer import DocViewer
    view = DocViewer(_fake_docs(tmp_path), lang="en")
    labels = _labels(view)
    assert "PLANS" not in str(labels)
    assert "work.md" not in str(labels)
    # the manual is its own branch and it is expanded; the advanced one is
    # collapsed (a manual that opens on a list of ADRs is not a manual)
    guide = view._tree.topLevelItem(0)
    assert guide.text(0) == "User guide" and guide.isExpanded()
    adv = [view._tree.topLevelItem(i) for i in
           range(view._tree.topLevelItemCount())
           if view._tree.topLevelItem(i).text(0) == "Advanced documentation"]
    assert adv and not adv[0].isExpanded()
    # the topic docs the "?" buttons open are part of the manual, loose at
    # the top level
    loose = labels.get("", [])
    assert "UFE.md" in loose and "SEQUENCES.md" in loose
    # the other topic docs and the ADRs live in the advanced branches
    assert "PHOTOMETRY.md" in labels["Advanced documentation"]
    assert "ADR-001-pyside6.md" in labels["Design decisions"]
    view.deleteLater()


def test_the_tree_follows_the_app_language(qapp, tmp_path):
    from nightscribe.gui.doc_viewer import DocViewer
    es = DocViewer(_fake_docs(tmp_path), lang="es")
    labels = _labels(es)
    assert labels["User guide"] == ["README.es.md", "01-getting-started.es.md",
                                    "02-tonight.es.md"]
    assert "UFE.es.md" in labels.get("", [])
    assert "ADR-001-pyside6.es.md" in labels["Design decisions"]
    assert es.default_file().name == "README.es.md"
    es.deleteLater()


def test_a_document_with_one_language_is_still_reachable(qapp, tmp_path):
    # a doc that exists only in English must not vanish from the Spanish
    # tree: showing the English text beats hiding the page
    from nightscribe.gui.doc_viewer import DocViewer
    root = _fake_docs(tmp_path)
    (root / "unified-fits-editor.md").write_text("# UFE notes\n",
                                                 encoding="utf-8")
    view = DocViewer(root, lang="es")
    assert "unified-fits-editor.md" in _labels(view)["Advanced documentation"]
    view.deleteLater()


def test_the_real_docs_tree_hides_the_plans(qapp):
    # against the repository's own docs/: the plans never show, and the
    # manual's index is the default page
    from nightscribe import paths
    from nightscribe.gui.doc_viewer import DocViewer
    root = paths.docs_dir()
    if not (root / "user").is_dir():
        pytest.skip("no docs tree in this checkout")
    view = DocViewer(root, lang="en")
    labels = _labels(view)
    assert "PLANS" not in labels
    assert view.default_file().name == "README.md"
    assert "01-getting-started.md" in labels["User guide"]
    view.deleteLater()
