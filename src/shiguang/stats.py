"""Statistics: counts, mood distribution, monthly trend, tag frequency,
writing streak, word cloud candidates.

A pure functional module — given a list of Entry, return a
StatsReport with everything the report tab needs.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date as date_cls, timedelta
from typing import Optional

from .diary import Entry


@dataclass
class MoodBucket:
    score: int       # 1..5
    count: int


@dataclass
class MonthPoint:
    year_month: str  # "2026-04"
    label: str       # "4月"
    entry_count: int
    word_count: int


@dataclass
class TagCount:
    tag: str
    count: int


@dataclass
class StatsReport:
    total_entries: int = 0
    total_words: int = 0
    total_characters: int = 0
    date_range: tuple[date_cls, date_cls] | None = None
    average_words_per_entry: float = 0.0
    current_streak_days: int = 0
    longest_streak_days: int = 0
    mood_distribution: list[MoodBucket] = field(default_factory=list)
    monthly_trend: list[MonthPoint] = field(default_factory=list)
    top_tags: list[TagCount] = field(default_factory=list)
    word_cloud: list[tuple[str, int]] = field(default_factory=list)


# ── Public API ──────────────────────────────────────────

def compute(entries: list[Entry], today: Optional[date_cls] = None) -> StatsReport:
    today = today or date_cls.today()
    r = StatsReport()
    if not entries:
        return r

    r.total_entries = len(entries)
    word_counts = [_word_count(e.body) for e in entries]
    char_counts = [_char_count(e.body) for e in entries]
    r.total_words = sum(word_counts)
    r.total_characters = sum(char_counts)
    r.average_words_per_entry = r.total_words / r.total_entries if r.total_entries else 0

    dates = sorted(e.date for e in entries)
    r.date_range = (dates[0], dates[-1])
    r.current_streak_days, r.longest_streak_days = _streaks(dates, today)

    # Mood distribution
    mood_counts: Counter = Counter()
    for e in entries:
        if e.frontmatter.mood is not None:
            mood_counts[e.frontmatter.mood] += 1
    r.mood_distribution = [
        MoodBucket(score=k, count=v) for k, v in sorted(mood_counts.items())
    ]

    # Monthly trend (last 6 months, including the current one)
    r.monthly_trend = _monthly_trend(entries, today, months=6)

    # Top tags
    tag_counts: Counter = Counter()
    for e in entries:
        for t in e.frontmatter.tags:
            tag_counts[t] += 1
    r.top_tags = [TagCount(tag=t, count=c) for t, c in tag_counts.most_common(10)]

    # Word cloud (Chinese-friendly: split on CJK + Latin words)
    r.word_cloud = _word_cloud(entries, top_n=30)

    return r


# ── Helpers ──────────────────────────────────────────────

def _word_count(text: str) -> int:
    """Approximate word count: CJK chars count as 1 each; Latin
    words split on whitespace + punctuation."""
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    latin_words = len(_LATIN_WORD_RE.findall(text))
    return cjk + latin_words


def _char_count(text: str) -> int:
    """Total characters excluding whitespace."""
    return sum(1 for c in text if not c.isspace())


_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _streaks(sorted_dates: list[date_cls], today: date_cls) -> tuple[int, int]:
    """Current streak (consecutive days ending today) and longest."""
    if not sorted_dates:
        return 0, 0
    # Dedupe
    unique = sorted(set(sorted_dates))
    # Longest
    longest = 1
    cur = 1
    for i in range(1, len(unique)):
        if (unique[i] - unique[i - 1]).days == 1:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 1
    # Current: streak ending today (or yesterday — allow 1-day grace
    # so the streak doesn't break before the user has written today)
    today_streak = 0
    last = unique[-1]
    if last == today or last == today - timedelta(days=1):
        today_streak = 1
        for i in range(len(unique) - 2, -1, -1):
            if (unique[i + 1] - unique[i]).days == 1:
                today_streak += 1
            else:
                break
    return today_streak, longest


def _monthly_trend(entries: list[Entry], today: date_cls, months: int) -> list[MonthPoint]:
    """Return the last `months` months including the current one,
    ordered chronologically (oldest first)."""
    points: list[MonthPoint] = []
    # Compute start of the first month in the window
    first_month = today.month - (months - 1)
    first_year = today.year
    while first_month <= 0:
        first_month += 12
        first_year -= 1

    # Bucket entries by YYYY-MM
    by_month: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        key = f"{e.date.year:04d}-{e.date.month:02d}"
        by_month[key].append(e)

    year, month = first_year, first_month
    for _ in range(months):
        key = f"{year:04d}-{month:02d}"
        bucket = by_month.get(key, [])
        words = sum(_word_count(e.body) for e in bucket)
        points.append(MonthPoint(
            year_month=key,
            label=f"{month}月",
            entry_count=len(bucket),
            word_count=words,
        ))
        month += 1
        if month > 12:
            month = 1
            year += 1

    return points


# CJK Unified Ideographs + Latin word boundary
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff]+"      # CJK Unified Ideographs (basic)
    r"|[\u3400-\u4dbf]+"      # CJK Extension A
    r"|[A-Za-z0-9]+"           # Latin words
)
_STOPWORDS = {
    # Chinese stopwords (very short list — we keep the rest)
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "我们",
    "你们", "他们", "这个", "那个", "什么", "怎么", "为什么", "没有",
    "有", "和", "也", "都", "就", "不", "要", "会", "可以", "但是",
    # English stopwords
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "this", "that", "what",
    "how", "why", "have", "has", "had", "do", "does", "did", "and", "or",
    "but", "if", "then", "so", "of", "in", "on", "at", "to", "for",
}


def _word_cloud(entries: list[Entry], top_n: int) -> list[tuple[str, int]]:
    """Extract candidate words and rank by frequency.

    Approach:
      - Concatenate all entry bodies
      - Extract CJK runs (1+ chars) and Latin words
      - Drop CJK runs of length 1 that are stopwords
      - Drop pure single-char Latin words
      - Keep runs of length 2-4 for CJK (idiom-like)
      - Keep runs of length >= 3 for Latin
      - Rank by frequency
    """
    counter: Counter = Counter()
    for e in entries:
        for m in _CJK_RE.finditer(e.body):
            token = m.group(0)
            if not token:
                continue
            # CJK or CJK-extension
            if any('\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf' for c in token):
                if len(token) == 1 and token in _STOPWORDS:
                    continue
                if len(token) > 4:
                    continue
            else:
                # Latin
                if len(token) < 3:
                    continue
                if token.lower() in _STOPWORDS:
                    continue
            counter[token] += 1

    return counter.most_common(top_n)