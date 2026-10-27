############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The series' quality flags, in words
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The flags the series engine writes on a point, in the observer's language.

THE ENGINE NAMES THEM (core/series_measure.DATA_FLAGS and CAVEAT_FLAGS) AND
THIS IS THE ONLY PLACE THAT PUTS THEM IN WORDS, because two places show them:
the editor's list of frames, which marks each row with what the series said
about that frame, and the measurement panel, which says why a series came
out with nothing to draw. They have to read the same, or the same night gets
two different explanations.

Every flag comes with its WHY and not only its name: a mark nobody can
explain is a mark that gets ignored, and the observer who reported the empty
chart of 2026-10-20 had a list of 338 flagged frames in front of him and
nothing that told him what any of them meant.

The words are built with LITERAL translate() calls on purpose: lupdate only
extracts literals, and a table of pre-built strings would never reach the
catalogue (see CONTRIBUTING).
"""

from PySide6.QtCore import QCoreApplication

# The context lupdate files these under. It is not a widget: the panel and
# the list ask for the same words from here.
CONTEXT = "FlagWords"

_cache = None


def words():
    # @return: {flag: (short, why)} in the observer's language, cached.
    #
    # (short, why): the short form is what a row or a line can carry; the why
    # is for a tooltip or a second line, because a mark nobody can explain is
    # a mark that gets ignored.
    global _cache
    if _cache is None:
        t = lambda s: QCoreApplication.translate(CONTEXT, s)  # noqa: E731
        _cache = {
            "unusable": (
                t("unusable"),
                t("the plate's recipe refused the measurement")),
            "saturated": (
                t("saturated"),
                t("the star's core is clipped, so its flux is a floor and "
                  "not a value")),
            "nonlinear": (
                t("nonlinear"),
                t("the peak is above the camera profile's linearity limit: "
                  "the flux is no longer proportional")),
            "cosmic": (
                t("cosmic ray"),
                t("an isolated spike sits in the aperture")),
            "cloud": (
                t("cloud"),
                t("the frame is dimmer than its neighbours by more than the "
                  "night's scatter")),
            "seeing": (
                t("seeing"),
                t("the FWHM left the night's range: defocus, a trail or a "
                  "satellite through the core")),
            "align_failed": (
                t("not aligned"),
                t("the frame could not be registered on the reference "
                  "plate")),
            "align_edge": (
                t("edge"),
                t("the frame only overlaps the reference plate at its edge")),
            "guide_jump": (
                t("guiding"),
                t("the target moved off the position it had on the reference "
                  "plate")),
            "few_comps": (
                t("few comparisons"),
                t("the zero point rests on fewer comparisons than the recipe "
                  "asks for")),
            "no_zp": (
                t("no zero point"),
                t("no comparison star could hold a zero point, so this frame "
                  "has no magnitude")),
            "neighbour_zp": (
                t("neighbour zero point"),
                t("the zero point came from a neighbouring frame")),
        }
    return _cache


def short(flag):
    # @args: flag - an engine flag key
    # @return: its short name in the observer's language (the key itself
    #          when it is one nobody has named yet: better a raw key than a
    #          silent blank)
    return words().get(flag, (flag, ""))[0]


def why(flag):
    # @args: flag - an engine flag key
    # @return: what it means in the observer's language, or "" when unknown
    return words().get(flag, (flag, ""))[1]


def clear_cache():
    # @return: None. A new language means new words (the tests use it).
    global _cache
    _cache = None
