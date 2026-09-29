############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Scientific axis ticks module (quality plan, phase A1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Where the numbers on a chart's axes come from.

A light curve is read with the eye, so the axis has to do half the work:
the ticks must land on values a human reads without arithmetic (12.50,
12.52, 12.54, not 12.4973, 12.5127...), they must carry exactly the
number of decimals the step needs, and when the data sits far from zero
(a Julian Date, a pixel position) the chart must factor out that offset
and say so, the way matplotlib writes "+6.0297e4" in the corner.

Nothing here knows about Qt, matplotlib or light curves: it is the small
piece of arithmetic that every chart in the application shares, so the
dark panel, the dark PNG and the white scientific figure can never
disagree about what 12.5 looks like.

The recipe comes from the Photometrica tool of our group (its
`niceTicks`, `tickLabel` and `axisOffset`), rewritten here with the same
behaviour so both tools draw the same figure.
"""

import logging
import math

logger = logging.getLogger(__name__)

# The "nice" steps a human reads without thinking, relative to the power
# of ten of the raw step. Anything else (0.7, 1.3, 3.3) makes the reader
# do arithmetic, which is exactly what an axis must never ask for.
_NICE_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)

# Below this many ticks the axis looks empty; above it, the labels start
# to collide. One is a preference, the caller may pass its own.
TARGET_TICKS = 7

# When the values sit this many steps away from zero, the offset is worth
# factoring out (below it, the labels are simply long, which is fine).
_OFFSET_RATIO = 1.0e4

# Decimal places are clamped here: a chart never needs more than six, and
# a rounding artefact never asks for fewer than none.
_MAX_DECIMALS = 6


def _step_for(span, target):
    # The nice step that splits `span` into about `target` intervals.
    #
    # We first take the raw step (span / target), then look at its mantissa
    # to snap it to the nearest nice value: 0.7 becomes 1.0 (times the
    # power of ten), 1.4 becomes 2.0, 2.2 becomes 2.5, 4.0 becomes 5.0.
    # The result is always a round number in the units the reader sees.
    # @args: span - hi - lo (positive), target - desired number of intervals
    # @return: the step (float)
    raw = span / max(2.0, float(target))
    power = math.pow(10.0, math.floor(math.log10(raw)))
    mantissa = raw / power
    for nice in _NICE_STEPS:
        if mantissa <= nice:
            return nice * power
    return 10.0 * power


def nice_ticks(lo, hi, target=TARGET_TICKS):
    # The tick values between lo and hi, on round numbers.
    # @args: lo - lower end of the axis, hi - upper end (hi > lo),
    #        target - desired number of intervals (7 reads well)
    # @return: a list of tick values (empty when the range is degenerate)
    if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
        return []
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return []
    step = _step_for(hi - lo, target)
    # start on the first multiple of the step at or above lo: 12.50 rather
    # than 12.4973
    first = math.ceil(lo / step) * step
    out = []
    value = first
    # the tolerance keeps 0.30000000000000004 from adding one tick too many
    while value <= hi + step * 1e-6:
        out.append(0.0 if abs(value) < step * 1e-9 else value)
        value += step
        if len(out) > 200:            # a pathological range, never a hang
            break
    return out


def step_of(ticks):
    # The spacing between two ticks of a list, for the label's decimals.
    # @args: ticks - a nice_ticks() result
    # @return: the step, or 0.0 when there is no pair to measure
    if len(ticks) < 2:
        return 0.0
    return abs(ticks[1] - ticks[0])


def frac_digits(step, cap=_MAX_DECIMALS):
    # How many decimals a step needs to be written down exactly.
    #
    # The obvious answer (ceil(-log10(step))) is wrong for the 2.5 family,
    # which appears often: a step of 0.025 written with two decimals gives
    # "0.02, 0.05, 0.07, 0.10", a sequence that lies about its own
    # spacing. The step is a mantissa (1, 2, 2.5, 5, 10) times a power of
    # ten, so the decimals are the power's plus one when the mantissa is
    # not a whole number.
    # @args: step - the tick spacing, cap - never more than this
    # @return: the number of decimals (int)
    if not step or step <= 0.0 or not math.isfinite(step):
        return 2
    power = math.floor(math.log10(step))
    mantissa = step / math.pow(10.0, power)
    extra = 0 if abs(mantissa - round(mantissa)) < 1e-9 else 1
    return max(0, min(int(cap), int(-power) + extra))


def tick_label(value, step):
    # The label of one tick, with exactly the decimals its step needs.
    #
    # This is the small detail that makes a curve readable: on a night
    # that varies 0.10 mag the step is 0.02, so the label is "12.52"; on a
    # year-long curve the step is 10 mag and "12" is the whole story.
    # Printing a fixed number of decimals is how a chart ends up with
    # "12.5" five times in a row, which tells the reader nothing.
    # @args: value - the tick value, step - the spacing between ticks
    # @return: the label (str)
    if not math.isfinite(value):
        return ""
    decimals = frac_digits(step)
    text = "{0:.{1}f}".format(value, decimals)
    return "0" if text.lstrip("-").strip("0.") == "" and text.startswith("-") \
        else text


def axis_offset(ticks):
    # The constant worth taking out of the labels, or 0 when none is.
    #
    # A Julian Date axis covering ten minutes spans 0.007 d while its
    # values are around 60297.8: printing those labels in full wastes half
    # the margin and hides which tick moved. The fix is the one matplotlib
    # uses: subtract the offset and write it once, at the top of the axis
    # ("+6.0297e4"). The same applies to pixel positions drifting around
    # 800 px by a couple of pixels.
    # @args: ticks - a nice_ticks() result
    # @return: the offset to subtract from every label (0.0 when not worth it)
    if len(ticks) < 2:
        return 0.0
    step = step_of(ticks)
    if step <= 0.0:
        return 0.0
    magnitude = max(abs(t) for t in ticks)
    if magnitude / step <= _OFFSET_RATIO:
        return 0.0
    power = math.pow(10.0, math.floor(math.log10(step)))
    return round(ticks[0] / power) * power


def offset_label(offset):
    # The text that says which offset was taken out ("+6.0297e4").
    # @args: offset - the axis_offset() result
    # @return: the label (str), empty when there is no offset
    if not offset:
        return ""
    sign = "+" if offset > 0 else "\u2212"       # a real minus sign
    text = "{0:.12g}".format(abs(offset))
    return sign + text


def axis_plan(lo, hi, target=TARGET_TICKS):
    # Everything a chart needs to label one axis, in one call: the ticks,
    # their labels, the offset taken out and the step used.
    #
    # Callers that only want to draw (the Qt widget) and callers that want
    # to render a PNG (matplotlib) both go through here, which is why the
    # two can never drift apart.
    # @args: lo - lower end of the axis, hi - upper end, target - ticks
    # @return: {"ticks", "labels", "offset", "offset_label", "step"}
    ticks = nice_ticks(lo, hi, target)
    step = step_of(ticks)
    offset = axis_offset(ticks)
    return {"ticks": ticks,
            "labels": [tick_label(t - offset, step) for t in ticks],
            "offset": offset,
            "offset_label": offset_label(offset),
            "step": step}
