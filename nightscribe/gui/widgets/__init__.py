############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - GUI chart widgets package (ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The interactive, vector chart layer of the GUI.
#
# Two rules keep this package clean (see ADR-029, and docs/PLANS/qt-chart-
# widgets.md §"Reglas del paquete gui/widgets"):
#
#   1. It may only import `core/*` (pure math) and `PySide6`. It must never
#      import `matplotlib` — the chart engine stays reserved for the social-
#      media PNG exports (ADR-010).
#   2. Colours come from `viz.palette` (a matplotlib-free module), not from
#      `viz.style` (which does import matplotlib, so pulling it in here would
#      violate rule 1).
