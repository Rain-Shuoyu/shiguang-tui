"""拾光 logo: ASCII rendering of the open-book + crescent moon
mark used by the macOS app.  Drawn in Textual rich markup so it
renders cleanly in the terminal.

Returns a string (multi-line) ready to drop into a Static.update().

Glow: we fake a "soft halo" by adding progressively dimmer
characters around the mark — using ░ ▒ ▓ (Unicode block elements)
which the terminal renders as filled rectangles. This gives a
"blurred edge" feel.
"""

from __future__ import annotations


# Centered art. Mark is 5 rows × 22 cols; pad with space to keep
# the "book + moon" form readable in a terminal.
#
#   Open book: two trapezoid pages + a spine
#   Moon:     crescent right of the book
#
# All glyphs are box-drawing + Unicode block elements so they
# render at consistent width in monospace fonts.

BOOK_W = 11
MOON_W = 7
PAD = 2
TOTAL_W = BOOK_W + PAD + MOON_W   # 20

# Centered rows
ROWS = [
    # row 0: tops of pages + moon
    "   ╭─────╮  ╭───╮  ",
    # row 1: page tops
    "   │░░░░░│  ╱   ╲  ",
    # row 2: page body
    "   │▒▒▒▒▒│  │ ◐ │ ",
    # row 3: spine + moon shadow
    "   ╰──┬──╯  │   │ ",
    # row 4: bottom of book
    "      │     ╰───╯ ",
]


def render_logo(amber: str = "#E8A87C", amber_soft: str = "#F5C7A0",
                amber_deep: str = "#C97B4F", dim: str = "#5A4F46") -> str:
    """Return the logo as rich markup. Colors simulate glow:
    bright center (amber) → soft edges (amber_soft) → halo (dim).
    """
    out: list[str] = []
    for r in ROWS:
        # First 11 cols: book (center brighter)
        book = r[:BOOK_W]
        # Pad + moon
        middle = r[BOOK_W:BOOK_W + PAD]
        moon = r[BOOK_W + PAD:]

        # Colorize the book — characters in the center column are brightest
        colored_book = ""
        # The book has 3 visible "columns" of characters at offset 3-7
        # (the page body area). We make those brighter.
        for i, ch in enumerate(book):
            if ch == " ":
                colored_book += ch
            elif 3 <= i <= 7:
                # center area — brightest
                colored_book += f"[bold {amber}]{ch}[/]"
            elif i in (1, 2, 8, 9):
                # page edge — softer
                colored_book += f"[{amber_soft}]{ch}[/]"
            else:
                # spine / corners
                colored_book += f"[{amber_deep}]{ch}[/]"

        # Colorize the moon — the curved part
        colored_moon = ""
        for i, ch in enumerate(moon):
            if ch == " ":
                colored_moon += ch
            elif ch in "◐":
                colored_moon += f"[bold {amber}]{ch}[/]"
            elif ch in "╱╲│─":
                colored_moon += f"[{amber_soft}]{ch}[/]"
            else:
                colored_moon += f"[{amber_deep}]{ch}[/]"

        out.append(f"      {colored_book}{middle}{colored_moon}")
    return "\n".join(out)


def render_glow_frame(width: int = 60, height: int = 24) -> str:
    """Render a soft glow border around the home page.

    Uses a layered box: outer dim → inner brighter → core brightest.
    No real "blur" in terminal, but the multi-layer tint creates a
    similar "halo" feel.
    """
    lines: list[str] = []
    amber = "#E8A87C"
    amber_soft = "#F5C7A0"
    amber_deep = "#C97B4F"
    dim = "#3A322C"
    very_dim = "#1F1A16"

    # Top edge
    lines.append(
        f"[{very_dim}]" + "▁" * 2 + f"[/]"
        + f"[{dim}]" + "▔" * (width - 4) + f"[/]"
        + f"[{very_dim}]" + "▁" * 2 + f"[/]"
    )
    for i in range(height - 2):
        left = f"[{dim}]▏[/]"
        right = f"[{dim}]▕[/]"
        body = " " * (width - 2)
        lines.append(f"{left}{body}{right}")
    # Bottom edge
    lines.append(
        f"[{very_dim}]" + "▔" * 2 + f"[/]"
        + f"[{dim}]" + "▁" * (width - 4) + f"[/]"
        + f"[{very_dim}]" + "▔" * 2 + f"[/]"
    )
    return "\n".join(lines)


def render_glow_rings(radius: int = 12) -> list[str]:
    """Generate concentric rings of increasingly-dim glow characters
    centered on (0, 0). Returns list of (row_offset, col_offset, char).
    """
    rings: list[tuple[int, int, str, str]] = []   # (dy, dx, char, color)
    for r in range(radius, 0, -1):
        if r >= 10:
            ch, color = "░", "#3A322C"
        elif r >= 7:
            ch, color = "▒", "#5A4F46"
        elif r >= 4:
            ch, color = "▓", "#8A6B4A"
        elif r >= 2:
            ch, color = "•", "#C97B4F"
        else:
            ch, color = "✦", "#E8A87C"
        # Top + bottom of ring
        for dx in range(-r, r + 1):
            rings.append((-r, dx, ch, color))
            rings.append((r, dx, ch, color))
        # Left + right of ring
        for dy in range(-r, r + 1):
            rings.append((dy, -r, ch, color))
            rings.append((dy, r, ch, color))
    return rings
