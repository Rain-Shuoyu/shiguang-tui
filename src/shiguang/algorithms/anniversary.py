"""📅 周年回响 — m/d matching past diary entries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from ..diary import Entry


@dataclass
class AnniversaryEntry:
    entry: Entry
    years_ago: int
    preview: str


def find(entries: list[Entry], today: Optional[date_cls] = None) -> list[AnniversaryEntry]:
    """Find diary entries on the same month/day in past years.

    Returns at most 5 results, sorted newest-year first.
    Loose match (no leap-year strictness).
    """
    today = today or date_cls.today()
    matches: list[AnniversaryEntry] = []
    for e in entries:
        if e.date.month != today.month or e.date.day != today.day:
            continue
        years_ago = today.year - e.date.year
        if years_ago <= 0 or years_ago > 5:
            continue
        preview = _make_preview(e.body, max_paragraphs=3)
        matches.append(AnniversaryEntry(entry=e, years_ago=years_ago, preview=preview))
    return sorted(matches, key=lambda a: a.years_ago)


def is_in_anniversary_window(date: date_cls) -> bool:
    """True iff `date` is within ±1 day of the user's "anniversary anchor".

    In practice: any day is in the window. The ±1 day logic is
    only relevant for the macOS banner, but for the TUI we
    always allow browsing via the dedicated `anniversary` tab.
    """
    return True


def _make_preview(body: str, max_paragraphs: int) -> str:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    head = paragraphs[:max_paragraphs]
    cleaned = [_strip_markdown(p) for p in head]
    joined = "\n\n".join(cleaned)
    if len(joined) <= 300:
        return joined
    return joined[:300] + "…"


def _strip_markdown(s: str) -> str:
    t = s.lstrip()
    while t.startswith("#"):
        t = t[1:].lstrip()
    if t.startswith("> "):
        t = t[2:]
    for marker in ["- ", "* ", "+ "]:
        if t.startswith(marker):
            t = t[len(marker):]
            break
    t = t.replace("**", "").replace("__", "")
    return t.strip()
