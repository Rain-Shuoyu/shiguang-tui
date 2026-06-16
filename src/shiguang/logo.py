"""The 'GLOW' wordmark for the TUI home screen.

Hand-drawn by the user. Clean, readable, no fonts needed.
Each row colored with a single amber accent.

The original drawing has varying row widths (28-30 cols) — L's
base extends to col 30. We preserve that asymmetry: the user's
art is the source of truth, not figlet smushing rules.
"""

from __future__ import annotations


# ── The 'GLOW' lines ────────────────────────────────────────
# Hand-drawn by the user. Verbatim from their message.

GLOW_LINES = [
    " ██████  ██      ██      ██  ",
    "██      ██      ██      ██  ",
    "██      ██      ██      ██  ",
    "██      ██      ██████  ██  ",
    " ██████  ████████  ██      ██ ",
    "          ██      ██      ██ ",
]
GLOW_WIDTH = 30


def render_glow_block() -> list[str]:
    """Render 'GLOW' as a list of rich-markup lines.

    Coloring strategy:
      - rows 0-2 (top of all caps): soft amber
      - row 3 (mid-section): bright amber
      - rows 4-5 (bottom): deep amber

    Each non-space char gets a rich-markup color tag. Spaces stay.
    """
    bright = "#E8A87C"
    soft = "#F5C7A0"
    deep = "#C97B4F"

    palette = [
        soft,     # row 0
        soft,     # row 1
        soft,     # row 2
        bright,   # row 3
        deep,     # row 4
        deep,     # row 5
    ]

    lines: list[str] = []
    for r, row in enumerate(GLOW_LINES):
        color = palette[r]
        rendered = ""
        for ch in row:
            if ch == " ":
                rendered += " "
            else:
                rendered += f"[bold {color}]{ch}[/]"
        lines.append(rendered)
    return lines


def render_home_header() -> str:
    """Return the home header: just the 'GLOW' wordmark."""
    return "\n".join(render_glow_block())
