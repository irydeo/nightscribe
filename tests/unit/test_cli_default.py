############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the CLI entry point's default subcommand
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Typing the program's name opens the program.

`nightscribe` with no subcommand used to answer with a usage error and no
hint that the desktop app lives behind `gui`. It now opens the GUI (the CLI
stays one word away), which is what a user who types the program's name
wants.
"""

import pytest


def _no_logging(monkeypatch):
    # main() sets up the rotating file log on the real data dir and marks the
    # root handlers, which would leak into test_logging (it then finds the
    # handlers already there and writes no file). Keep this test out of it.
    from nightscribe import __main__ as cli
    monkeypatch.setattr(cli, "_setup_logging", lambda verbose: None)


def test_no_subcommand_opens_the_desktop_app(monkeypatch):
    from nightscribe import __main__ as cli
    import nightscribe.gui.app as gui_app

    _no_logging(monkeypatch)
    seen = {}

    def _run():
        seen["gui"] = True
        return 0

    monkeypatch.setattr(gui_app, "run", _run)
    assert cli.main([]) == 0
    assert seen.get("gui")


def test_an_unknown_subcommand_is_still_an_error(monkeypatch):
    # The default must not swallow real parsing: a typo is reported, not
    # quietly turned into "open the GUI".
    from nightscribe import __main__ as cli
    _no_logging(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["not-a-command"])
