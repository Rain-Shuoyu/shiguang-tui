"""🪞 镜像回放 — diversity-driven sampling of past sentences.

A faithful Python port of the macOS app's MirrorSampler.
Since we can't use Apple's NLEmbedding on non-macOS, we use
a *very* simple fallback: bag-of-character-trigrams + cosine
similarity. It won't be as good as the macOS version, but it's
good enough to produce diverse selections.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from ..diary import Entry


@dataclass
class Reflection:
    text: str
    source_date: date_cls
    source_title: str
    source_id: str


@dataclass
class _Config:
    entry_window_days: int = 180
    min_entries: int = 5
    max_entries: int = 12
    output_count: int = 6
    max_chars_per_sentence: int = 80
    min_chars_per_sentence: int = 12
    mmr_lambda: float = 0.0  # 0 = pure diversity


# ── Public ──────────────────────────────────────────────────────

def sample(entries: list[Entry], topic: Optional[str] = None,
           seed: Optional[int] = None,
           config: Optional[_Config] = None) -> list[Reflection]:
    """Sample `output_count` reflections from `entries`.

    `topic=None` → random mode (centroid anchor).
    `topic=str` → themed mode (topical anchor).
    """
    if seed is not None:
        random.seed(seed)
    cfg = config or _Config()

    # 1. Filter to time window
    if not entries:
        return []
    latest = max(e.date for e in entries)
    from datetime import timedelta
    cutoff = latest - timedelta(days=cfg.entry_window_days)
    candidates = [e for e in entries if e.date >= cutoff]
    if len(candidates) < cfg.min_entries:
        return []

    # 2. Pool
    if len(candidates) <= cfg.max_entries:
        pool = list(candidates)
    else:
        pool = random.sample(candidates, cfg.max_entries)

    # 3. Compute vectors (char-trigram bag-of-words, L2-normalised)
    pool_vecs = [(e, _trigram_vector(_e_text(e))) for e in pool]
    pool_vecs = [(e, v) for e, v in pool_vecs if v is not None]
    if len(pool_vecs) < cfg.min_entries:
        return []

    # 4. Query vector
    if topic:
        query_vec = _trigram_vector(topic)
        if not query_vec:
            return []
    else:
        query_vec = _centroid([v for _, v in pool_vecs])

    # 5. Anchor (closest to query)
    ranked = sorted(pool_vecs, key=lambda ev: -_cosine(query_vec, ev[1]))
    picked: list[tuple[Entry, list[float]]] = [ranked[0]]
    picked_vecs: list[list[float]] = [ranked[0][1]]

    # 6. Greedy MMR
    while len(picked) < cfg.output_count:
        best: Optional[tuple[Entry, list[float]]] = None
        best_score = float("-inf")
        for entry, vec in pool_vecs:
            if any(p[0].id == entry.id for p in picked):
                continue
            relevance = _cosine(query_vec, vec)
            max_sim = max((_cosine(vec, pv) for pv in picked_vecs), default=0.0)
            diversity = 1.0 - max_sim
            score = cfg.mmr_lambda * relevance + (1.0 - cfg.mmr_lambda) * diversity
            if score > best_score:
                best_score = score
                best = (entry, vec)
        if best is None:
            break
        picked.append(best)
        picked_vecs.append(best[1])

    # 7. Pick a sentence from each picked entry
    result: list[Reflection] = []
    for entry, _ in picked:
        sentence = _pick_sentence(entry.body, cfg)
        if sentence:
            result.append(Reflection(
                text=sentence,
                source_date=entry.date,
                source_title=entry.title,
                source_id=entry.id,
            ))

    return sorted(result, key=lambda r: r.source_date)


# ── Internals ────────────────────────────────────────────────────

def _e_text(e: Entry) -> str:
    """Combine body + first few frontmatter fields for embedding."""
    parts = [e.body or ""]
    if e.frontmatter.title:
        parts.insert(0, e.frontmatter.title)
    if e.frontmatter.tags:
        parts.append(" ".join(e.frontmatter.tags))
    return "\n".join(parts)


_TRIGRAM_RE = re.compile(r"(?<=.).(?=.)")  # any 3-char window


def _trigram_vector(text: str) -> list[float]:
    """Build a sparse-ish trigram vector.

    Real-valued (not sparse) because the dict is small. We
    enumerate all 3-character windows in `text`, count, then
    L2-normalise. Returns an empty list for very short texts.
    """
    if len(text) < 3:
        return []
    grams: dict[str, int] = {}
    for i in range(len(text) - 2):
        g = text[i:i+3]
        grams[g] = grams.get(g, 0) + 1
    # Convert to a sorted list of (gram, count) for determinism
    items = sorted(grams.items())
    # Vector as a list — but to keep size manageable we hash the
    # grams into a fixed-size bucket space. Simple approach:
    # bucket = hash(g) % 1024.
    vec = [0.0] * 1024
    for g, c in items:
        vec[hash(g) % 1024] += c
    return _l2_normalise(vec)


def _l2_normalise(v: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in v))
    if mag == 0:
        return v
    return [x / mag for x in v]


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    n = len(vectors[0])
    out = [0.0] * n
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    inv = 1.0 / len(vectors)
    return _l2_normalise([x * inv for x in out])


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


_PUNCT = re.compile(r"[。！？\n]")


def _pick_sentence(body: str, cfg: _Config) -> Optional[str]:
    parts = _PUNCT.split(body)
    candidates = [p.strip() for p in parts
                 if cfg.min_chars_per_sentence <= len(p.strip()) <= cfg.max_chars_per_sentence]
    if not candidates:
        return None
    return _strip_markdown(random.choice(candidates))


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
