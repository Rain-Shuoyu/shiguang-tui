"""Visual theme: colors and glyphs shared across the app.

Single source of truth for the warm-amber palette and the small
set of unicode glyphs the UI uses as decoration (mode indicators,
list cursors, separators). All views import from here so changing
a color or glyph is a one-line edit.
"""
from __future__ import annotations


# ── Colors (hex) ───────────────────────────────────────────────
# The whole UI is a single accent (amber) on a warm dark canvas.
# Three amber tints for hierarchy, plus two neutrals and two
# paper/ink swatches for the few places that need a different tone.

AMBER = "#E8A87C"          # primary accent (bright)
AMBER_DEEP = "#C97B4F"     # darker amber, used for unfocused borders
AMBER_SOFT = "#F5C7A0"     # lighter amber, used for secondary text

WARM_GRAY = "#8B8680"      # mid-gray for de-emphasized text
PAPER = "#F5F1EB"          # off-white, for occasional inverted backgrounds
INK = "#1A1A1A"            # near-black, for amber-on-light contrast


# ── Glyphs ────────────────────────────────────────────────────
# Keep these short — they're sprinkled through the UI as accents
# (a star here, an arrow there). Don't grow this list without need.

STAR = "✦"                 # section/title marker (used in headers and mode pills)
ARROW = "›"                # narrow arrow, used in the top status bar (folder › time)
DOT = "·"                  # mid-dot, used as separator in stats subtitle (N 篇 · N 字)
