"""Diary entry: read, write, scan folder."""
from __future__ import annotations

import re
import os
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

from . import frontmatter as fm


_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Entry:
    id: str                       # stable id, derived from path
    path: Path                    # file path
    date: date_cls                # the date this entry represents
    title: str                    # first heading or filename
    body: str                     # markdown body (after frontmatter stripped)
    frontmatter: fm.Frontmatter

    @property
    def preview(self) -> str:
        """First ~200 chars of the body, single-line."""
        text = self.body.strip().replace("\n", " ")
        if len(text) <= 200:
            return text
        return text[:200] + "…"


def parse_date_from_filename(path: Path) -> Optional[date_cls]:
    m = _DATE_RE.match(path.stem)
    if not m:
        return None
    try:
        return date_cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_date_from_frontmatter(fm_obj: fm.Frontmatter, fallback: date_cls) -> date_cls:
    """Use frontmatter `date:` if it parses, else fall back to filename."""
    if fm_obj.date:
        m = _DATE_RE.match(fm_obj.date)
        if m:
            try:
                return date_cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return fallback


def scan_folder(folder: Path) -> list[Entry]:
    """Read all .md files in `folder`, return as a list of Entries
    sorted newest-first."""
    if not folder.exists() or not folder.is_dir():
        return []
    entries: list[Entry] = []
    for path in sorted(folder.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        f, body = fm.parse(content)
        filename_date = parse_date_from_filename(path) or date_cls.today()
        entry_date = parse_date_from_frontmatter(f, filename_date)
        # Title: frontmatter `title:`, else first heading, else filename
        title = f.title
        if not title:
            for line in body.split("\n"):
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            if not title:
                title = path.stem
        entries.append(Entry(
            id=str(path.resolve()),
            path=path,
            date=entry_date,
            title=title,
            body=body,
            frontmatter=f,
        ))
    entries.sort(key=lambda e: (e.date, e.title), reverse=True)
    return entries


def serialize_entry(date: date_cls, title: str, body: str, f: fm.Frontmatter) -> str:
    """Build the file content: frontmatter + body."""
    if f.date is None:
        f.date = date.isoformat()
    if f.title is None and title:
        f.title = title
    return fm.serialize(f) + "\n" + body


def available_filename(date: date_cls, folder: Path) -> str:
    """Return a YYYY-MM-DD.md filename that doesn't yet exist in `folder`."""
    base = date.isoformat()
    candidate = folder / f"{base}.md"
    if not candidate.exists():
        return candidate.name
    # Append -2, -3, ... until we find a free name
    n = 2
    while True:
        candidate = folder / f"{base}-{n}.md"
        if not candidate.exists():
            return candidate.name
        n += 1


def write_entry(folder: Path, date: date_cls, title: str, body: str, f: fm.Frontmatter,
                existing_path: Optional[Path] = None) -> Path:
    """Write an entry to disk. If `existing_path` is set, overwrite
    that file. Otherwise create a new file in `folder` with a
    collision-free name. Returns the final path."""
    folder.mkdir(parents=True, exist_ok=True)
    if existing_path is not None:
        target = existing_path
    else:
        target = folder / available_filename(date, folder)
    content = serialize_entry(date, title, body, f)
    target.write_text(content, encoding="utf-8")
    return target


def today_entry(entries: list[Entry]) -> Optional[Entry]:
    today = date_cls.today()
    for e in entries:
        if e.date == today:
            return e
    return None
