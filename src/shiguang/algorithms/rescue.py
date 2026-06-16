"""🌧 情绪急救 — detect 3+ consecutive low-mood days, surface past rescue entries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from typing import Optional

from ..diary import Entry


# Cultural-context distress keywords (Chinese). Conservative:
# only fire when the user has hinted at it themselves.
TRIGGER_KEYWORDS = [
    "撑不住", "撑不下去了", "想死", "想消失", "没意义",
    "崩溃", "扛不住", "受不了", "熬不下去",
    "没用", "没人在乎", "没人关心", "我好累", "好累啊",
    "什么都不想做", "放弃",
    "都是我不好", "我有问题", "我是不是",
]


@dataclass
class RescueSignal:
    level: str             # "none" | "watch" | "intervene"
    days_affected: int
    sample_text: str


def detect(entries: list[Entry], today: Optional[date_cls] = None) -> RescueSignal:
    """Inspect the past 14 days for a 3+ day low-mood streak.

    Walks back from today, day by day, stopping at the first
    missing day (the streak has to be contiguous). Then counts
    the trailing run of score ≤ 2.
    """
    today = today or date_cls.today()
    lookback_days = 14
    cutoff = today - timedelta(days=lookback_days)

    # Day → entry map for the past N days
    day_map: dict[date_cls, Entry] = {}
    for e in entries:
        if cutoff <= e.date <= today:
            day_map[e.date] = e

    # Build recent contiguous chain ending today
    chain: list[Entry] = []
    cursor = today
    for _ in range(lookback_days):
        if cursor in day_map:
            chain.append(day_map[cursor])
            cursor = cursor - timedelta(days=1)
        else:
            break

    # Score each day
    scores: list[tuple[date_cls, int, str]] = []
    for e in reversed(chain):    # chronological
        mq = _parse_mood_quick(e)
        if mq is not None:
            score = mq["score"]
            text = f"{mq['emoji']} {mq['text']}"
        elif e.frontmatter.mood is not None:
            score = e.frontmatter.mood
            text = f"mood={e.frontmatter.mood}"
        else:
            continue
        scores.append((e.date, score, text))

    # Longest trailing run of score <= 2
    run = 0
    for _, s, _ in scores:
        if s <= 2:
            run += 1
        else:
            break

    # Keyword hit in the last 7 days
    seven_day_cutoff = today - timedelta(days=7)
    keyword_hit: Optional[str] = None
    for d, _, text in scores:
        if d < seven_day_cutoff:
            continue
        for kw in TRIGGER_KEYWORDS:
            if kw in text:
                keyword_hit = kw
                break
        if keyword_hit:
            break

    if run >= 3:
        if keyword_hit:
            return RescueSignal(level="intervene", days_affected=run, sample_text=scores[-1][2] if scores else "")
        return RescueSignal(level="watch", days_affected=run, sample_text=scores[-1][2] if scores else "")
    return RescueSignal(level="none", days_affected=0, sample_text="")


def find_rescued_entries(entries: list[Entry], today: Optional[date_cls] = None,
                         max_entries: int = 2) -> list[Entry]:
    """Find past entries (6-12 months ago) with low mood, sorted
    chronologically. Returns up to `max_entries`."""
    today = today or date_cls.today()
    six_months_ago = today - timedelta(days=183)
    twelve_months_ago = today - timedelta(days=365)
    two_years_ago = today - timedelta(days=730)

    def is_low(e: Entry) -> bool:
        if e.frontmatter.mood is not None and e.frontmatter.mood <= 2:
            return True
        mq = _parse_mood_quick(e)
        if mq and mq["score"] <= 2:
            return True
        return False

    # Try 6-12 month window first
    candidates = [e for e in entries
                  if twelve_months_ago <= e.date <= six_months_ago and is_low(e)]
    candidates.sort(key=lambda e: e.date)
    if candidates:
        return candidates[:max_entries]

    # Fallback: 1-2 years back
    older = [e for e in entries
             if two_years_ago <= e.date < twelve_months_ago and is_low(e)]
    older.sort(key=lambda e: e.date)
    return older[:max_entries]


# ── mood_quick frontmatter helpers ──────────────────────────────

def _parse_mood_quick(e: Entry) -> Optional[dict]:
    """Parse `mood_quick: "😔 撑了一天"` from frontmatter.extra."""
    raw = e.frontmatter.extra.get("mood_quick")
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    emoji = trimmed[0]
    if emoji not in ["😔", "😐", "🙂", "😊"]:
        return None
    text = trimmed[1:].strip()
    score_map = {"😔": 1, "😐": 2, "🙂": 3, "😊": 4}
    return {"emoji": emoji, "text": text, "score": score_map[emoji]}


def make_mood_quick(emoji: str, text: str) -> str:
    """Serialize a mood_quick for frontmatter.extra."""
    if text:
        return f"{emoji} {text.strip()}"
    return emoji
