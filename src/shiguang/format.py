"""Formatting helpers: visual width measurement and bar charts.

Two utilities shared by the stats view (and any future view that
needs CJK-aware text measurement or fractional-precision bars):

  visual_width(s)  — render cell width of a string, treating CJK
                     chars as 2 cells and stripping rich markup
                     first. Used to keep right-aligned label
                     gutters stable across mixed Chinese/English.

  bar(value, max, width=20)  — horizontal bar of `width` cells
                     with 1/8 precision using the 8-step unicode
                     block characters '▏▎▍▌▋▊▉█'. Empty bar is
                     spaces; full bar is full blocks; in-between
                     uses one fraction char for the last cell.

Also exposes the small private helpers (BAR_FRACTIONS, _TAG_RE,
_strip_markup) used by app.py's stats renderer.
"""
from __future__ import annotations

import re
import unicodedata


# 8-step unicode block characters for high-resolution bar charts.
# Index 0 = 1/8 cell, index 7 = full 8/8 cell.
BAR_FRACTIONS = "▏▎▍▌▋▊▉█"


# Rich markup tag pattern (e.g. "[bold #E8A87C]" or "[/]") — has no visual
# width but is interleaved with text. We strip it before measuring.
_TAG_RE = re.compile(r"\[/?[^\]]*\]")


def visual_width(s: str) -> int:
    """Visual cell width of a string, treating CJK chars as 2 cells.

    Strips rich markup tags first since they render to zero cells.
    """
    s = _TAG_RE.sub("", s)
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            w += 2
        else:
            w += 1
    return w


def bar(value: int, max_value: int, width: int = 20) -> str:
    """Render a horizontal bar of `width` cells with 1/8 precision.

    Returns `width` chars: a mix of full blocks, a single fraction
    block (▏▎▍▌▋▊▉█), and trailing spaces.
    """
    if max_value <= 0 or value <= 0:
        return " " * width
    total = round(value * width * 8 / max_value)
    total = max(0, min(total, width * 8))
    full = total // 8
    rem = total % 8
    if rem == 0:
        return "█" * full + " " * (width - full)
    return "█" * full + BAR_FRACTIONS[rem - 1] + " " * (width - full - 1)


def strip_markup(text: str) -> str:
    """Remove rich-style markup tags (e.g. [bold #E8A87C]foo[/]) from
    a string. Used to feed a TextArea with plain text. Keep newlines
    and indentation intact.
    """
    return _TAG_RE.sub("", text)
