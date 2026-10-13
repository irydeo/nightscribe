############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: static undefined-name guard
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A renamed symbol can leave a stale reference that only blows up on the path
nobody tests. That happened on 2026-10-13: the observatory worker was renamed
`CcdcielWorker` -> `ObservatoryWorker`, one call site kept the old name, and the
NameError only fired when the observer pressed **Connect** (no unit test did).
pyflakes finds undefined names statically; this guard runs it over the package
and fails on any. It skips when pyflakes is not installed, so it never breaks a
minimal environment.
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "nightscribe"


def test_no_undefined_names_in_the_package():
    pytest.importorskip("pyflakes")
    from pyflakes import api, messages

    offenders = []

    class _Reporter:
        def flake(self, msg):
            # only undefined names: unused imports and the like are noise here
            if isinstance(msg, messages.UndefinedName):
                offenders.append(f"{msg.filename}:{msg.lineno}: {msg.message}")

        def unexpectedError(self, filename, msg):
            offenders.append(f"{filename}: {msg}")

        def syntaxError(self, filename, msg, lineno, offset, text):
            offenders.append(f"{filename}:{lineno}: {msg}")

    reporter = _Reporter()
    for path in sorted(_ROOT.rglob("*.py")):
        api.checkPath(str(path), reporter)
    assert not offenders, "undefined names:\n" + "\n".join(offenders)
