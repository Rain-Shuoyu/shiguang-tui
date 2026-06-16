"""`shi --sanity-check` — non-TUI smoke test.

v0.2: dropped the algorithm-heavy sanity check (mirror /
anniversary / rescue / daily_practice were removed). Now it
just verifies that the diary folder can be scanned + stats
can be computed.
"""
from __future__ import annotations

from pathlib import Path

from .config import default_diary_folder
from .diary import scan_folder
from . import stats as stats_mod


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

    report = stats_mod.compute(entries)
    print(f"  ✓ Stats: {report.total_words} words, "
          f"streak {report.current_streak_days}/{report.longest_streak_days}, "
          f"{len(report.mood_distribution)} mood buckets")
    if report.word_cloud:
        top3 = ", ".join(f"{w}({c})" for w, c in report.word_cloud[:3])
        print(f"  ✓ Word cloud top 3: {top3}")
    print()
    print("All checks passed.")
    return 0