"""Single-letter logo with glow halo.

The TUI home screen shows a giant "A" (for AfterGlow) centered
on the screen, with a faked glow effect via concentric rings
of Unicode block characters (░ ▒ ▓) in progressively-dimmer
amber shades.

We use Textual's rich markup so the result renders cleanly in
the terminal. The glow is purely a visual effect — no real
blur — but the multi-layer tint creates a "halo" feel.
"""

from __future__ import annotations


def render_letter(letter: str = "A", size: int = 1) -> str:
    """Render the letter as a single character with a chosen size.

    size=1: single character
    size=2: vertical repeat of 2 lines (looks taller in terminal)
    size=3: vertical repeat of 3 lines

    The repeat is just the same character on multiple lines so
    that the terminal can render it as a "tall" letter.
    """
    amber = "#E8A87C"
    amber_soft = "#F5C7A0"
    pad = " " * size
    if size == 1:
        return f"[bold {amber}]{letter}[/]"
    # Multi-line tall rendering
    lines = []
    for _ in range(size):
        lines.append(f"[bold {amber}]{letter}[/]")
    return "\n".join(lines)


def render_glow_rings(width: int = 22) -> list[str]:
    """Generate 9 rows of concentric glow rings.

    Row layout (centered on a 22-col field):
      - 4 rows above the letter (denser as we approach center)
      - 1 row in the middle (empty — the letter paints there)
      - 4 rows below the letter

    The blocks get brighter (more saturated amber) as we approach
    the center, faking a soft halo.
    """
    out: list[str] = []
    center_x = width // 2

    # (distance, color, char_distance_pattern)
    # distance=0 means "right next to the letter"
    rows = [
        # (d, color) — char only at exact distance from center
        (4, "#3A322C"),   # very far, dim
        (3, "#5A4F46"),   # far
        (2, "#8A6B4A"),   # mid
        (1, "#C97B4F"),   # close
        (0, "CENTER"),    # the letter itself
        (1, "#C97B4F"),
        (2, "#8A6B4A"),
        (3, "#5A4F46"),
        (4, "#3A322C"),
    ]
    for d, color in rows:
        if color == "CENTER":
            out.append(" " * width)
            continue
        row = list(" " * width)
        for x in range(width):
            if abs(x - center_x) == d:
                row[x] = "▓"
            elif abs(x - center_x) == d + 1:
                row[x] = "▒"
            elif abs(x - center_x) == d + 2 and d == 4:
                row[x] = "░"
        out.append(f"[{color}]{''.join(row)}[/]")
    return out


def render_home_header(letter: str = "A") -> str:
    """Return the full home header: glow rings + giant letter.

    Lines: 4 glow rows above, then the letter (centered with
    surrounding glow), then 4 glow rows below. The whole thing
    is rich markup ready for Static.update().
    """
    glow_rows = render_glow_rings(width=22)
    # Build the assembly. The glow at distance 0 (the center line)
    # is replaced by the giant letter + 1 ring of ▓ on each side.
    center = 4  # index of the center row
    amber = "#E8A87C"

    # Replace the center line with a hand-crafted row that has the
    # letter in the middle, a bright ring of ▓ on each side, and
    # outer rings fading out.
    def line_at_distance(d: int) -> str:
        if d == 0:
            # Letter surrounded by 2 ring layers of ▓ on each side
            # (no glow chars touch the letter — they start 1 col away)
            return (
                f"  [{amber}]▓▓▓[/]  "
                f"[bold {amber}]{letter}[/]"
                f"  [{amber}]▓▓▓[/]  "
            )
        elif d == 1:
            return (
                f" [{amber}]▓▓[/]            [{amber}]▓▓[/] "
            )
        elif d == 2:
            return (
                f"[#8A6B4A]▓▓[/]              [#8A6B4A]▓▓[/]"
            )
        elif d == 3:
            return (
                f" [#5A4F46]▒▒[/]              [#5A4F46]▒▒[/] "
            )
        else:   # d == 4
            return (
                f"  [#3A322C]░░[/]              [#3A322C]░░[/]  "
            )

    lines = [line_at_distance(d) for d in range(9)]
    return "\n".join(lines)
