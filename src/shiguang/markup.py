"""Convert a small subset of markdown to rich markup strings.

Just enough to render diaries cleanly in the TUI. Not a full
markdown implementation — we don't need to handle tables,
footnotes, code fences with language hints, etc.

Supported:
  - `# heading`     → [bold amber]heading[/]
  - `## heading`    → [bold amber-soft]heading[/]
  - `### heading`   → [bold dim]heading[/]
  - `**bold**`      → [bold]bold[/]
  - `*italic*`      → [italic]italic[/]
  - `> quote`       → │ quote
  - `- item`        → • item
  - `1. item`       → 1. item
  - `` `code` ``    → [reverse]code[/]
  - `[text](url)`   → [blue underline]text[/]

Anything else is preserved as-is. Brackets `[` in user content
will be left alone — Rich only treats them as markup if they
match a known style name.
"""
from __future__ import annotations

import re


# Compile patterns once.
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_ITALIC = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_RE_CODE = re.compile(r"`([^`]+?)`")
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")


def md_to_markup(md: str) -> str:
    """Render markdown to rich markup suitable for Static.update()."""
    out_lines: list[str] = []
    for line in md.split("\n"):
        stripped = line.lstrip()
        if not stripped:
            out_lines.append("")
            continue
        # Headers
        if stripped.startswith("### "):
            content = stripped[4:].strip()
            out_lines.append(f"  [bold dim]{_inline(content)}[/]")
            continue
        if stripped.startswith("## "):
            content = stripped[3:].strip()
            out_lines.append(f"  [bold amber-soft]{_inline(content)}[/]")
            continue
        if stripped.startswith("# "):
            content = stripped[2:].strip()
            out_lines.append(f"  [bold amber]{_inline(content)}[/]")
            continue
        # Blockquote
        if stripped.startswith("> "):
            content = stripped[2:].strip()
            out_lines.append(f"  [dim]│[/]  [italic]{_inline(content)}[/]")
            continue
        if stripped.startswith(">"):
            content = stripped[1:].strip()
            out_lines.append(f"  [dim]│[/]  [italic]{_inline(content)}[/]")
            continue
        # Unordered list
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            out_lines.append(f"  [amber]•[/]  {_inline(m.group(1))}")
            continue
        # Ordered list
        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            out_lines.append(f"  [amber dim]{m.group(1)}.[/]  {_inline(m.group(2))}")
            continue
        # Plain paragraph line
        out_lines.append(f"  {_inline(stripped)}")
    return "\n".join(out_lines)


def _inline(text: str) -> str:
    """Apply inline styles: bold, italic, code, links.

    Order matters: bold before italic, code before link (links
    in code shouldn't match the link pattern).
    """
    # Bold first (it has unique ** markers)
    text = _RE_BOLD.sub(r"[bold]\1[/]", text)
    # Italic
    text = _RE_ITALIC.sub(r"[italic]\1[/]", text)
    # Inline code — render with reverse so it stands out
    text = _RE_CODE.sub(r"[reverse]\1[/]", text)
    # Links — render text only with underline
    text = _RE_LINK.sub(r"[underline]\1[/]", text)
    return text
