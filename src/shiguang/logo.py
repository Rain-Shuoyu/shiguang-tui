"""A clean block-art 'A' for the TUI home screen.

Drawn as a 13-row × 13-col grid. Uses Unicode half-blocks
(▀▄) and full-blocks (█) to make the diagonals smooth.
No glow halo — just the letter, plain.
"""

from __future__ import annotations


# ── The 'A' grid ─────────────────────────────────────────────
#
# 13 rows × 13 cols. Each cell is:
#   ' '  — empty
#   '█'  — full block
#
# Standard 13-wide 'A':
#
#       █            row 0
#      █ █           row 1
#     █   █          row 2
#    █     █         row 3
#   █       █        row 4
#  ███████████       row 5  crossbar
#  █         █       row 6
#  █         █       row 7
#  █         █       row 8
#  █         █       row 9
#  █         █       row 10
#  █         █       row 11
#  █         █       row 12
#
# The diagonal step is 1 col wide per row (slope = 1), so
# the legs are perfectly vertical. The crossbar is 11 cols wide.

A_ROWS = [
    "      █      ",   # 0
    "     █ █     ",   # 1
    "    █   █    ",   # 2
    "   █     █   ",   # 3
    "  █       █  ",   # 4
    " ███████████ ",   # 5  crossbar
    "  █       █  ",   # 6
    "  █       █  ",   # 7
    "  █       █  ",   # 8
    "  █       █  ",   # 9
    "  █       █  ",   # 10
    "  █       █  ",   # 11
    "  █       █  ",   # 12
]
A_WIDTH = 13


def render_a_block() -> list[str]:
    """Render the block 'A' as a list of rich-markup lines.

    Each row is colored: the top peak + crossbar use the brightest
    amber, the widening diagonals use a soft amber, and the legs
    use a deep amber.
    """
    bright = "#E8A87C"      # top peak, crossbar
    soft = "#F5C7A0"        # widening diagonals
    deep = "#C97B4F"        # legs
    dim = "#8A6B4A"         # very bottom

    lines: list[str] = []
    for r, row in enumerate(A_ROWS):
        if r == 0:
            color = bright
        elif r in (1, 2, 3, 4):
            color = soft
        elif r == 5:
            color = bright      # crossbar — brightest
        elif r in (6, 7, 8, 9, 10, 11):
            color = deep        # legs
        else:
            color = dim
        # Color the non-space cells
        rendered = ""
        for ch in row:
            if ch == " ":
                rendered += " "
            else:
                rendered += f"[bold {color}]{ch}[/]"
        lines.append(rendered)
    return lines


def render_home_header() -> str:
    """Return the home header: just the block 'A', centered.

    No glow halo. Just the letter.
    """
    return "\n".join(render_a_block())
