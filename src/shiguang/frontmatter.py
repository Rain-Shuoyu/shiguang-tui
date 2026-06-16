"""Minimal YAML frontmatter parser/serializer.

Why minimal? The macOS app uses a similarly minimal parser that
only reads the keys we care about (mood, mood_label, weather,
tags, title, date) and preserves unknown keys verbatim. We
mirror that here so the two apps can read each other's files.

This is NOT a full YAML implementation. It handles:
  - Top-level `key: value` lines (string, int, list, bool)
  - Quoted strings (single or double)
  - Inline lists: `tags: [a, b, c]`
  - Block lists: `tags:\n  - a\n  - b`

Anything more exotic falls back to "store as `extra`" — same as
the macOS app.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Frontmatter:
    mood: int | None = None
    mood_label: str | None = None
    weather: str | None = None
    tags: list[str] = field(default_factory=list)
    title: str | None = None
    date: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        """Get an arbitrary key, including extras like 'mood_quick'."""
        return self.extra.get(key)


_FENCE_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse(content: str) -> tuple[Frontmatter, str]:
    """Parse a markdown file's content into (frontmatter, body).

    If no frontmatter is present, returns (empty Frontmatter, content).
    """
    m = _FENCE_RE.match(content)
    if not m:
        return Frontmatter(), content
    raw_fm = m.group(1)
    body = content[m.end():]
    return _parse_dict(raw_fm), body


def _parse_dict(raw: str) -> Frontmatter:
    lines = raw.split("\n")
    fm = Frontmatter()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == "" or rest == "|" or rest == ">":
            # Block scalar / list — peek next non-empty line
            block_lines: list[str] = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith("  ") or lines[j].startswith("\t") or lines[j].strip() == ""):
                if lines[j].strip():
                    block_lines.append(lines[j].strip().lstrip("- "))
                j += 1
            value = "\n".join(block_lines) if block_lines else ""
            _set_key(fm, key, value)
            i = j
            continue
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            value = [s.strip().strip('"\'') for s in inner.split(",") if s.strip()]
            _set_key(fm, key, value)
        else:
            # Strip surrounding quotes
            value = rest.strip('"\'')
            _set_key(fm, key, value)
        i += 1
    return fm


def _set_key(fm: Frontmatter, key: str, value: Any) -> None:
    """Set a known key, or fall back to extra for unknown keys."""
    if key == "mood":
        try:
            fm.mood = int(value)
        except (TypeError, ValueError):
            pass
    elif key == "mood_label":
        fm.mood_label = str(value)
    elif key == "weather":
        fm.weather = str(value)
    elif key == "tags":
        if isinstance(value, list):
            fm.tags = [str(v) for v in value]
        elif isinstance(value, str):
            fm.tags = [t.strip() for t in value.split(",") if t.strip()]
    elif key == "title":
        fm.title = str(value)
    elif key == "date":
        fm.date = str(value)
    else:
        # Round-trip: keep as string in extra
        if isinstance(value, list):
            fm.extra[key] = ", ".join(str(v) for v in value)
        else:
            fm.extra[key] = str(value)


def serialize(fm: Frontmatter) -> str:
    """Render frontmatter as a YAML block. Empty fm → empty string."""
    lines = ["---"]
    if fm.title is not None:
        lines.append(f"title: \"{_escape(fm.title)}\"")
    if fm.date is not None:
        lines.append(f"date: {fm.date}")
    if fm.mood is not None:
        lines.append(f"mood: {fm.mood}")
    if fm.mood_label is not None:
        lines.append(f"mood_label: \"{_escape(fm.mood_label)}\"")
    if fm.weather is not None:
        lines.append(f"weather: \"{_escape(fm.weather)}\"")
    if fm.tags:
        lines.append("tags: [" + ", ".join(_escape(t) for t in fm.tags) + "]")
    for k, v in fm.extra.items():
        lines.append(f"{k}: \"{_escape(v)}\"")
    lines.append("---")
    lines.append("")  # trailing newline before body
    return "\n".join(lines)


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
