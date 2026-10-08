############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Finding the editor host from a feature tab
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Where the feature tabs find the hooks their host set.

The tabs (Blink, Annotate, Compare, Measure, Calibration, Track & Stack)
ask the widget around them for the callables the host armed: the visit
context, the file registry, the export folder, the MPC sender. They used
to do it with `self.window()`, which works when the host IS a window (the
unit tests, which build a parentless host; the classic dialogs).

Since ADR-053 the editor is a plain QWidget embedded in the main window's
shell, so `self.window()` from a tab returns the MAIN WINDOW, which has
none of those methods: the lookups silently failed. The visible symptom
was the Calibration and Track & Stack buttons staying disabled even when
the editor had been opened from a visit (the visit reached the hook, the
tab never found it); the same trap disabled the series context and the
file registration on save.

`host_of` keeps the old behaviour when it already works (a host that is a
window) and otherwise walks up the parent chain to the widget that really
exposes the hooks. The unit tests missed this because they mounted the
host parentless, which is exactly what production does NOT do; the tests
now mount it embedded too.
"""

# Any of these marks the widget as the editor host (they live only on
# UfeDialog). Checking several keeps the helper from depending on one.
HOST_METHODS = ("open_plate", "series_context", "astrometry_context",
                "photometry_recipe", "notify_saved", "export_folder",
                "reset_state_local", "notify_point", "notify_points")


def _looks_like_host(widget):
    # @args: widget - a QWidget or None
    # @return: True when it exposes the host's hooks
    if widget is None:
        return False
    return any(callable(getattr(widget, name, None)) for name in HOST_METHODS)


def host_of(widget):
    # @args: widget - the tab asking
    # @return: the editor host (the UfeDialog), or widget.window() when no
    #          ancestor looks like one (so a plain host still answers)
    # First the cheap path (a host that IS a window, the tests and the
    # classic dialogs), then the parent chain (the embedded editor).
    top = widget.window()
    if _looks_like_host(top):
        return top
    parent = widget.parentWidget()
    while parent is not None:
        if _looks_like_host(parent):
            return parent
        parent = parent.parentWidget()
    return top
