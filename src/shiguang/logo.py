"""Block-art 'A' logo for the TUI home screen.

The letter is built from a 9x9 grid of cells, each cell being
either empty (space) or filled with a block character. The
resulting letter looks like a real blocky 'A':

  ▟███▙
  █▄▄▄█
  █▀▀▀█
  █   █
  █   █

We use full-block Unicode characters (█) plus box-drawing
characters (─│┌┐└┘) for the legs and crossbar.

Color gradients simulate glow:
  bright amber (#E8A87C) at the center,
  amber_soft (#F5C7A0) on the next layer,
  amber_deep (#C97B4F) at the outer halo,
  dim (#5A4F46) at the very edges.

The mark is wrapped in concentric glow rings (▓▒░) that fade
from the center outward, faking a soft halo.
"""

from __future__ import annotations


# ── The "A" pixel map ──────────────────────────────────────
#
# 9 rows × 9 cols. Each cell is one of:
#   " "  — empty
#   "X"  — solid block (█)
#   "-"  — horizontal stroke (─)
#   "|"  — vertical stroke (│)
#
# The 'A' is drawn as a triangle on top + crossbar + two legs:
#
#       X           row 0
#      X X          row 1
#     X   X         row 2
#    X     X        row 3
#   XXXXXXXXX      row 4  crossbar
#   |       |       row 5  legs (use box-drawing)
#   |       |       row 6
#   |       |       row 7
#   |       |       row 8

A_ROWS = [
    "    X    ",
    "   X X   ",
    "  X   X  ",
    " X     X ",
    "XXXXXXXXX",
    " |     | ",
    " |     | ",
    " |     | ",
    " |     | ",
]
A_WIDTH = 9


def render_a_block(size: int = 1) -> list[str]:
    """Render the block 'A' at the given size.

    size=1: 9 rows × 9 cols
    size=2: 18 rows × 18 cols (each cell becomes 2x2)
    """
    lines: list[str] = []
    for r, row in enumerate(A_ROWS):
        cells: list[str] = []
        for ch in row:
            if ch == " ":
                cells.append(" " * size)
            elif ch == "X":
                cells.append("█" * size)
            elif ch == "-":
                cells.append("─" * size)
            elif ch == "|":
                cells.append("│" * size)
            else:
                cells.append(ch * size)
        # Color per row
        if r == 0:
            color = "#E8A87C"   # bright top peak
        elif r == 1:
            color = "#E8A87C"
        elif r == 2:
            color = "#F5C7A0"   # widening
        elif r == 3:
            color = "#F5C7A0"
        elif r == 4:
            color = "#E8A87C"   # crossbar — bright
        elif r in (5, 6):
            color = "#C97B4F"   # legs — deep amber
        else:
            color = "#8A6B4A"   # very bottom — fading
        # Render: each cell is colored if non-empty
        rendered = ""
        for cell in cells:
            if cell.strip():
                rendered += f"[bold {color}]{cell}[/]"
            else:
                rendered += cell
        for _ in range(size):
            lines.append(rendered)
    return lines


def render_glow_halo(height: int = 9) -> tuple[list[str], list[str]]:
    """Render glow as TWO half-strips: left half + right half.

    Each half is 3 visible cols wide. The letter (9 cols) sits
    in the middle, with the two halves flanking it on each side.

    Returns (left_lines, right_lines) — both are height-long
    lists of rich-markup strings.
    """
    left_lines: list[str] = []
    right_lines: list[str] = []
    center_y = height // 2
    # Each half: 3 visible cols. We pre-compute the (dx, dist) for
    # each position relative to the letter's left/right edge.
    for y in range(height):
        dist = abs(y - center_y)
        if dist == 0:
            # Center row — letter row, leave halos empty
            left_lines.append("    ")   # 3 visible cols of space, padded
            right_lines.append("    ")
            continue
        # Color + char per distance
        if dist == 4:
            color, ch = "#3A322C", "░"
        elif dist == 3:
            color, ch = "#5A4F46", "▒"
        elif dist == 2:
            color, ch = "#8A6B4A", "▓"
        elif dist == 1:
            color, ch = "#C97B4F", "▓"
        else:
            color, ch = "#1F1A16", " "
        # Left half: 3 cols, distance from letter's left edge
        # dist=4: 1 col with ░ at edge
        # dist=3: 2 cols with ▒ at edge
        # dist=2: 3 cols with ▓ at edge
        # dist=1: 1 col with ▓ tight
        left = ""
        if dist == 4:
            left = f"  {ch}"
        elif dist == 3:
            left = f" {ch} "
        elif dist == 2:
            left = f"{ch}  "
        elif dist == 1:
            left = f"{ch}  "
        # Right half: mirror of left
        right = ""
        if dist == 4:
            right = f"{ch}  "
        elif dist == 3:
            right = f" {ch} "
        elif dist == 2:
            right = f"  {ch}"
        elif dist == 1:
            right = f"  {ch}"
        # Apply color to the non-space chars
        def colorize(s: str) -> str:
            out = ""
            for c in s:
                if c.isspace():
                    out += c
                else:
                    out += f"[{color}]{c}[/]"
            return out
        left_lines.append(colorize(left))
        right_lines.append(colorize(right))
    return left_lines, right_lines


def render_home_header(size: int = 1) -> str:
    """Compose: left glow + giant block 'A' + right glow.

    Layout: 3-col glow on each side, 9-col letter in the middle.
    Total visible width: 15 cols.
    """
    left_glow, right_glow = render_glow_halo(height=9)
    letter = render_a_block(size=size)
    out: list[str] = []
    for lg, lline, rg in zip(left_glow, letter, right_glow):
        out.append(f"{lg}{lline}{rg}")
    return "\n".join(out)
