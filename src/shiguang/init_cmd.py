"""`shi --init` — set up the diary folder with a sample entry."""
from __future__ import annotations

import sys
from datetime import date as date_cls
from pathlib import Path

from .config import default_diary_folder, save_state, load_state
from .diary import write_entry, scan_folder
from .frontmatter import Frontmatter


SAMPLE_ENTRY = """\
---
date: {date}
title: "欢迎使用 拾光"
mood: 4
tags: [meta]
---

# 欢迎使用 拾光

这是你的第一篇日记。一切从这里开始。

## 拾光能做什么

- **写作** — 每天写下你的想法，自动存成 Markdown
- **记录** — 浏览所有日记，按月分组
- **报表** — 看数据：总字数、心情分布、月度趋势、Tag 频率、词云

按 `?` 看全部快捷键。 按 `q` 退出。
"""


def run_init(folder_arg: str | None) -> int:
    folder = Path(folder_arg).expanduser() if folder_arg else default_diary_folder()
    folder.mkdir(parents=True, exist_ok=True)

    # Sample entry
    sample_path = folder / f"{date_cls.today().isoformat()}.md"
    if not sample_path.exists():
        content = SAMPLE_ENTRY.format(date=date_cls.today().isoformat())
        sample_path.write_text(content, encoding="utf-8")
        print(f"✓ Created sample entry: {sample_path}")
    else:
        print(f"  Sample entry already exists: {sample_path}")

    # Persist the folder in state
    state = load_state()
    state.diary_folder = str(folder)
    save_state(state)
    print(f"✓ Diary folder set to: {folder}")
    print(f"✓ State saved to: ~/.config/shiguang/state.json")
    print()
    print("Run `shi` to launch the TUI.")
    return 0
