"""Textual app — 拾光 / AfterGlow TUI.

Layout (one screen, mode-aware):
  ┌─ Header (current mode + folder) ──────────────────────────┐
  │  Mode: 日记     Folder: ~/Documents/Journal   14:23:01    │
  ├───────────────────────────────────────────────────────────┤
  │                                                            │
  │  Main content (mode-specific)                              │
  │                                                            │
  ├───────────────────────────────────────────────────────────┤
  │  Footer (key hints)                                        │
  │  1写作 2列表 3日记 4镜像 5周年 6急救 7AI r回答 n新建 ?帮助 │
  └────────────────────────────────────────────────────────────┘

7 modes (number keys):
  1 写作  — entry list + create/delete
  2 列表  — full list with filter
  3 日记  — TODAY view: today's diary + 今日签 + 周年 + 急救
  4 镜像  — Mirror reflection
  5 周年  — Anniversary echo (manual)
  6 急救  — Rescue detection + history
  7 AI    — free-form LLM chat
"""
from __future__ import annotations

import asyncio
import random
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Static

from . import __version__
from .config import load_state, save_state, default_diary_folder, state_file, config_dir
from .diary import scan_folder, write_entry, today_entry, Entry
from .frontmatter import Frontmatter
from . import llm
from .algorithms import (
    daily_practice as dp,
    anniversary as anniv,
    rescue as resc,
    mirror as mirr,
)


# ── Main App ────────────────────────────────────────────────────

class ShiGuangApp(App):
    """Main Textual app."""

    # Textual expects SCREENS to be a dict {name: ScreenType}
    # for its auto-collection logic. We don't have named screens,
    # so we provide an empty dict.
    SCREENS: dict = {}

    CSS = """
    Screen { background: $surface; }

    #mode-indicator {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    #main-area {
        padding: 1 2;
    }

    .card {
        border: round $primary;
        padding: 1;
        margin: 1 0;
    }

    .prompt-card {
        background: $boost;
        border: round $warning;
        padding: 1;
        margin: 1 0;
    }

    .cool-card {
        background: $boost;
        border: round $secondary;
        padding: 1;
        margin: 1 0;
    }

    .muted { color: $text-muted; }

    .answer-line { color: $success; }

    .key-hint { color: $accent; text-style: bold; }

    .entry-list-row {
        height: 3;
    }

    .empty {
        text-align: center;
        color: $text-muted;
        padding: 4;
    }

    TextArea {
        height: 1fr;
        border: round $primary;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", show=True),
        Binding("1", "mode('writing')", "写作", show=True),
        Binding("2", "mode('list')", "列表", show=True),
        Binding("3", "mode('diary')", "日记", show=True),
        Binding("4", "mode('mirror')", "镜像", show=True),
        Binding("5", "mode('anniversary')", "周年", show=True),
        Binding("6", "mode('rescue')", "急救", show=True),
        Binding("7", "mode('ai')", "AI", show=True),
        Binding("q", "action_quit", "退出", show=False),
        Binding("?", "help", "帮助", show=True),
    ]

    SCREENS: dict = {}

    MY_MODES = ["writing", "list", "diary", "mirror", "anniversary", "rescue", "ai"]
    MODE_LABELS = {
        "writing": "写作",
        "list": "列表",
        "diary": "日记",
        "mirror": "镜像",
        "anniversary": "周年",
        "rescue": "急救",
        "ai": "AI",
    }

    current_mode: reactive[str] = reactive("diary")

    def __init__(self, folder: Optional[str] = None) -> None:
        super().__init__()
        self.state = load_state()
        if folder:
            self.state.diary_folder = folder
        elif not self.state.diary_folder:
            self.state.diary_folder = str(default_diary_folder())
        self.folder = Path(self.state.diary_folder)
        self.entries: list[Entry] = []
        self.refresh_entries()

    # ── Compose ──────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(id="mode-indicator")
        with Container(id="main-area"):
            yield Static("加载中…", id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "拾光 · AfterGlow"
        self.sub_title = f"v{__version__}  ·  {self.folder}"
        self.render_mode()

    # ── Public actions ──────────────────────────────────────

    def action_mode(self, mode: str) -> None:
        if mode not in self.MY_MODES:
            return
        self.current_mode = mode
        self.render_mode()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ── Mode rendering ──────────────────────────────────────

    def render_mode(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        indicator.update(
            f" [bold]{self.MODE_LABELS[self.current_mode]}[/] · "
            f"📁 {self.folder} · "
            f"{datetime.now().strftime('%H:%M:%S')}  "
        )
        content = self.query_one("#content", Static)
        # Dispatch to mode renderer
        renderer = getattr(self, f"render_{self.current_mode}", None)
        if renderer is None:
            content.update(f"模式 {self.current_mode} 暂未实现")
            return
        try:
            renderer(content)
        except Exception as e:
            content.update(f"[red]渲染出错: {e}[/]")

    def refresh_entries(self) -> None:
        self.entries = scan_folder(self.folder)

    # ── Mode renderers ──────────────────────────────────────

    def render_diary(self, target: Static) -> None:
        """Main 'today' view: today's diary + 今日签 + 周年 + 急救."""
        self.refresh_entries()
        today_e = today_entry(self.entries)
        prompt = dp.pick_for(date_cls.today())
        done_today = dp.is_done_today(self.state)
        anniv_matches = anniv.find(self.entries)
        signal = resc.detect(self.entries)

        lines: list[str] = []
        lines.append(f"# 拾光 · {date_cls.today().isoformat()}")
        lines.append("")

        # Today's diary
        if today_e:
            lines.append(f"## 📔 今天的日记 · {today_e.title}")
            lines.append("")
            preview = today_e.body.strip()
            if len(preview) > 600:
                preview = preview[:600] + "…"
            lines.append(preview)
            lines.append("")
            meta = []
            if today_e.frontmatter.mood is not None:
                meta.append(f"mood={today_e.frontmatter.mood}")
            if today_e.frontmatter.weather:
                meta.append(f"天气={today_e.frontmatter.weather}")
            if today_e.frontmatter.tags:
                meta.append("tags=" + ", ".join(today_e.frontmatter.tags))
            mq = today_e.frontmatter.extra.get("mood_quick")
            if mq:
                meta.append(f"情绪={mq}")
            if meta:
                lines.append(f"[dim]{'  ·  '.join(meta)}[/]")
            lines.append("")
        else:
            lines.append("## 📔 今天还没有日记")
            lines.append("")
            lines.append("[dim]按 `n` 新建今天的日记[/]")
            lines.append("")

        # 今日签
        lines.append("---")
        lines.append("")
        lines.append(f"## 🌙 今日签 · {prompt.category}")
        lines.append("")
        if done_today:
            lines.append(f"[green]✓ 已完成 · 连续 {self.state.daily_practice_streak} 天[/]")
            lines.append("")
            lines.append(f"> {prompt.text}")
        else:
            lines.append(f"**{prompt.text}**")
            lines.append("")
            streak_line = ""
            if self.state.daily_practice_streak > 0:
                streak_line = f" · 当前连续 {self.state.daily_practice_streak} 天"
            lines.append(f"[dim]按 `r` 写回答 (1-2 句就够){streak_line}[/]")
        lines.append("")

        # Anniversary
        if anniv_matches:
            lines.append("---")
            lines.append("")
            lines.append(f"## 🕯 周年回响 ({len(anniv_matches)} 年)")
            lines.append("")
            for m in anniv_matches[:3]:
                lines.append(f"### {m.years_ago} 年前 · {m.entry.title}")
                lines.append("")
                lines.append(m.preview)
                lines.append("")

        # Rescue
        if signal.level != "none":
            lines.append("---")
            lines.append("")
            if signal.level == "intervene":
                lines.append("## 🌧 你之前走过这段路")
            else:
                lines.append("## ☁️ 你最近不太好")
            lines.append("")
            lines.append(f"过去 {signal.days_affected} 天你都不太好。下面这些是之前类似的时刻：")
            lines.append("")
            rescued = resc.find_rescued_entries(self.entries)
            for e in rescued[:2]:
                lines.append(f"### {e.date.isoformat()} · {e.title}")
                preview = e.body.strip()
                if len(preview) > 250:
                    preview = preview[:250] + "…"
                lines.append(preview)
                lines.append("")
            lines.append("[dim]按 `6` 进入急救 tab 重看 · 按 `i` 永久关闭急救 banner[/]")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("[dim]按 `1-7` 切换模式 · `?` 帮助 · `q` 退出[/]")

        target.update("\n".join(lines))

    def render_writing(self, target: Static) -> None:
        """Entry list + create / delete."""
        self.refresh_entries()
        lines = [
            f"# 写作 · {len(self.entries)} 篇",
            "",
            f"📁 {self.folder}",
            "",
            "**快捷键**",
            "",
            "- `n` 新建今天的日记",
            "- `↑↓` 选择 · `Enter` 打开",
            "- `dd` 删除选中",
            "- `m` 镜像回放",
            "- `r` 写今日签回答",
            "",
            "---",
            "",
        ]
        # Last 20 entries
        for e in self.entries[:20]:
            mood_str = f" · mood {e.frontmatter.mood}" if e.frontmatter.mood else ""
            lines.append(f"**{e.date.isoformat()}** · {e.title}{mood_str}")
        if not self.entries:
            lines.append("[dim]还没有日记。按 `n` 新建。[/]")
        target.update("\n".join(lines))

    def render_list(self, target: Static) -> None:
        self.refresh_entries()
        lines = [
            f"# 全部日记 · {len(self.entries)} 篇",
            "",
        ]
        # Group by year-month
        from collections import defaultdict
        by_month: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries:
            key = e.date.strftime("%Y-%m")
            by_month[key].append(e)
        for month in sorted(by_month.keys(), reverse=True):
            lines.append(f"## {month}")
            lines.append("")
            for e in sorted(by_month[month], key=lambda x: x.date, reverse=True):
                preview = e.preview[:80]
                lines.append(f"- **{e.date.isoformat()}** · {e.title}  [dim]{preview}[/]")
            lines.append("")
        target.update("\n".join(lines))

    def render_mirror(self, target: Static) -> None:
        self.refresh_entries()
        if len(self.entries) < 5:
            target.update("[dim]日记还不够多（至少 5 篇）。继续写。[/]")
            return
        try:
            reflections = mirr.sample(self.entries, seed=random.randint(0, 99999))
        except Exception as e:
            target.update(f"[red]镜像采样失败: {e}[/]")
            return
        lines = ["# 🪞 镜像回放", "", "从你过去的日记里挑了 5-7 句。", ""]
        for r in reflections:
            lines.append(f"> {r.text}")
            lines.append(f"> [dim]— {r.source_date.isoformat()} · {r.source_title}[/]")
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("[dim]按 `r` 重新采样一组 · `3` 回到日记 tab · `?` 帮助[/]")
        target.update("\n".join(lines))

    def render_anniversary(self, target: Static) -> None:
        self.refresh_entries()
        matches = anniv.find(self.entries)
        if not matches:
            target.update(f"[dim]今天 {date_cls.today().isoformat()} 在过去的日记里没有匹配。[/]")
            return
        lines = [f"# 🕯 周年回响 · {date_cls.today().isoformat()}", ""]
        for m in matches:
            lines.append(f"## {m.years_ago} 年前 · {m.entry.title}")
            lines.append("")
            lines.append(f"[dim]{m.entry.date.isoformat()}[/]")
            lines.append("")
            lines.append(m.preview)
            lines.append("")
        target.update("\n".join(lines))

    def render_rescue(self, target: Static) -> None:
        self.refresh_entries()
        signal = resc.detect(self.entries)
        if signal.level == "none":
            target.update(
                "# 🌧 情绪急救\n\n"
                f"过去 14 天没有检测到连续 3 天低分。\n"
                f"最近一次是 `{signal.sample_text or '无'}`。\n\n"
                "[dim]急救功能只在你连续 3 天情绪低时浮现。[/]"
            )
            return
        rescued = resc.find_rescued_entries(self.entries)
        lines = []
        if signal.level == "intervene":
            lines.append("# 🌧 你之前走过这段路")
        else:
            lines.append("# ☁️ 你最近不太好")
        lines.append("")
        lines.append(f"过去 {signal.days_affected} 天你都不太好。下面这些是之前类似的时刻：")
        lines.append("")
        for e in rescued:
            lines.append(f"## {e.date.isoformat()} · {e.title}")
            preview = e.body.strip()
            if len(preview) > 400:
                preview = preview[:400] + "…"
            lines.append(preview)
            lines.append("")
        lines.append("[dim]按 `i` 永久关闭急救 banner · `1-7` 切换模式[/]")
        target.update("\n".join(lines))

    def render_ai(self, target: Static) -> None:
        target.update(
            "# 💬 AI 助手\n\n"
            "AI tab 暂未在 v0.1 实现。\n\n"
            "**当前 LLM 配置**：\n\n"
            f"- Provider: `{self.state.llm.provider}`\n"
            f"- Base URL: `{self.state.llm.base_url}`\n"
            f"- Model: `{self.state.llm.model}`\n"
            f"- API key: `{'已设置' if self.state.llm.api_key else '[未设置 — 用 shi config]'}`\n\n"
            "v0.2 会加入 free-form 问答和流式输出。\n"
        )


# ── Help screen ────────────────────────────────────────────────

class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape,?,q", "app.pop_screen", "返回", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                "# 拾光 · 帮助\n\n"
                "**7 个模式** (按数字键切换):\n\n"
                "  `1` 写作  — entry 列表 + 新建/删除\n"
                "  `2` 列表  — 全部日记，按月分组\n"
                "  `3` 日记  — **默认视图**：今天的日记 + 今日签 + 周年 + 急救\n"
                "  `4` 镜像  — 5-7 句自己写过的话（多样性采样）\n"
                "  `5` 周年  — 往年今天你写过什么\n"
                "  `6` 急救  — 连续 3 天情绪低时浮现\n"
                "  `7` AI    — 自由问答（v0.2 计划）\n\n"
                "**常用键**：\n\n"
                "  `n`   新建今天的日记\n"
                "  `r`   写今日签回答\n"
                "  `m`   镜像回放（重新采样）\n"
                "  `?`   本帮助\n"
                "  `q`   退出\n\n"
                "**配置文件位置**：\n\n"
                f"  {state_file()}\n\n"
                "按 `Esc` / `?` 返回。",
                id="help-content",
            ),
            id="help-container",
        )

    def on_mount(self) -> None:
        self.query_one("#help-content", Static).styles.padding = (2, 4)


# ── CLI entry ─────────────────────────────────────────────────

# Register the help screen with the main app.
ShiGuangApp.SCREENS = {"help": HelpScreen}


def main() -> None:
    app = ShiGuangApp()
    app.run()
