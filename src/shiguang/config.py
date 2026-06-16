"""Configuration: paths, LLM settings, persistent state.

State lives in:
  - macOS:   ~/Library/Application Support/ShiGuang/
  - Linux:   $XDG_CONFIG_HOME/shiguang/  (default ~/.config/shiguang/)
  - Windows: %APPDATA%/ShiGuang/

This is a "lite" version of the macOS app's persistence. We
only carry the keys we actually use in the TUI.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ── Paths ────────────────────────────────────────────────────────────

def _config_dir() -> Path:
    """Return the per-user config/state directory."""
    if sys := os.environ.get("SHIGUANG_CONFIG_DIR"):
        return Path(sys).expanduser()
    # XDG-style for Linux, AppSupport-style for macOS
    if os.name == "posix" and os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ShiGuang"
    if os.name == "posix":
        xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
        return Path(xdg).expanduser() / "shiguang"
    # Windows
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "ShiGuang"
    return Path.home() / ".shiguang"


def config_dir() -> Path:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file() -> Path:
    return config_dir() / "state.json"


def default_diary_folder() -> Path:
    """Default diary folder: ~/Documents/Journal, overridable via env."""
    env = os.environ.get("SHIGUANG_FOLDER")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Documents" / "Journal"


# ── Settings (LLM) ─────────────────────────────────────────────────

class LLMSettings(BaseModel):
    """LLM provider config. Same shape as the macOS app so the
    same API key works for both."""
    provider: str = "minimax"            # "minimax" | "openai" | "anthropic"
    base_url: str = "https://api.minimax.chat"
    api_key: str = ""
    model: str = "MiniMax-M2.7"

    # Retrieval knobs (when relevant)
    temperature: float = 0.7
    max_tokens: int = 2048


# ── Persistent state ───────────────────────────────────────────────

class PersistentState(BaseModel):
    """UserDefaults-equivalent state we want to persist across runs."""
    diary_folder: Optional[str] = None
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Daily practice
    daily_practice_streak: int = 0
    daily_practice_longest: int = 0
    daily_practice_last_done_date: Optional[str] = None  # ISO date
    daily_practice_last_done_prompt_id: Optional[int] = None

    # Anniversary
    anniversary_last_shown_date: Optional[str] = None
    anniversary_user_disabled: bool = False
    anniversary_dismissed_dates: list[str] = Field(default_factory=list)

    # Rescue
    rescue_last_shown_date: Optional[str] = None
    rescue_user_disabled: bool = False
    rescue_dismissed_dates: list[str] = Field(default_factory=list)
    rescue_permanent_dismiss_count: int = 0


def load_state() -> PersistentState:
    path = state_file()
    if not path.exists():
        return PersistentState()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return PersistentState(**data)
    except Exception:
        # Corrupt state — start fresh, don't crash.
        return PersistentState()


def save_state(state: PersistentState) -> None:
    path = state_file()
    path.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
