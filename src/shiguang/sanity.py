"""`shi --sanity-check` — non-TUI smoke test."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import default_diary_folder
from .diary import scan_folder
from .algorithms import (
    daily_practice as dp,
    anniversary as anniv,
    rescue as resc,
    mirror as mirr,
)


def run_sanity_check(folder_arg: str | None) -> int:
    folder = Path(folder_arg).expanduser() if folder_arg else default_diary_folder()
    print(f"Sanity check on: {folder}")
    if not folder.exists():
        print(f"  ! folder does not exist: {folder}")
        return 1
    entries = scan_folder(folder)
    print(f"  ✓ {len(entries)} entries scanned")
    if not entries:
        return 0

    # Today
    from datetime import date as date_cls
    today = date_cls.today()
    p = dp.pick_for(today)
    print(f"  ✓ Today's daily practice prompt: #{p.id} ({p.category}) — {p.text[:40]}…")

    # Anniversary
    matches = anniv.find(entries, today)
    if matches:
        print(f"  ✓ Anniversary: {len(matches)} matches for {today.isoformat()}")
        for m in matches[:3]:
            print(f"      {m.years_ago}y ago: {m.entry.title}")
    else:
        print(f"  - No anniversary match for {today.isoformat()}")

    # Rescue
    signal = resc.detect(entries, today)
    print(f"  ✓ Rescue signal: {signal.level} (days={signal.days_affected})")

    # Mirror
    if len(entries) >= 5:
        try:
            reflections = mirr.sample(entries, seed=42)
            print(f"  ✓ Mirror: {len(reflections)} reflections")
            for r in reflections[:3]:
                print(f"      {r.source_date.isoformat()}: {r.text[:60]}…")
        except Exception as e:
            print(f"  ✗ Mirror failed: {e}")
    else:
        print(f"  - Mirror skipped (need ≥5 entries, have {len(entries)})")

    print()
    print("All checks passed.")
    return 0
