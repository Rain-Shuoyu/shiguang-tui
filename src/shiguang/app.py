"""Textual app — 拾光 / AfterGlow TUI.

Visual language:
  - 蜜橙 #E8A87C 主色（跟 macOS 版一致）
  - 暗色背景 $surface + 卡片 border 提示分区
  - 顶部 Header: 模式 + 路径 + 时间
  - 主区: 多个 "card" 容器垂直堆叠，card 间留 1 行空
  - 底部 Footer: 分组键提示

7 modes (number keys 1-7):
  1 写作  — entry list
  2 列表  — full list grouped by month
  3 日记  — TODAY view (default): today + 今日签 + 周年 + 急救
  4 镜像  — Mirror reflection
  5 周年  — Anniversary echo
  6 急救  — Rescue detection
  7 AI    — placeholder
"""
from __future__ import annotations

import random
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Static

from . import __version__
from .config import load_state, default_diary_folder, state_file
from .diary import scan_folder, Entry, today_entry
from .algorithms import (
    daily_practice as dp,
    anniversary as anniv,
    rescue as resc,
    mirror as mirr,
)


# ── 视觉常量 ──────────────────────────────────────────────

AMBER = "#E8A87C"           # 蜜橙 — 主色
AMBER_DEEP = "#C97B4F"      # 深蜜橙
AMBER_SOFT = "#F5C7A0"      # 浅蜜橙
INK = "#1A1A1A"             # 主文字
PAPER = "#F5F1EB"           # 浅文字
WARM_GRAY = "#8B8680"       # 灰色
COOL_BLUE = "#7B95A8"       # 冷蓝（急救专用）

# 边框字符（用 ASCII 安全字符，跨字体）
HL = "─"                    # 横线
VL = "│"                    # 竖线
TL = "┌"
TR = "┐"
BL = "└"
BR = "┘"
ARROW = "›"
DOT = "·"
STAR = "✦"


def hr(width: int, char: str = HL) -> str:
    return char * max(1, width)


# ── 主 App ──────────────────────────────────────────────

class ShiGuangApp(App):

    SCREENS: dict = {}

    CSS = f"""
    Screen {{
        background: #14110F;
    }}

    #mode-indicator {{
        dock: top;
        height: 1;
        background: #1F1A16;
        color: {AMBER_SOFT};
        padding: 0 2;
    }}

    #main-area {{
        padding: 1 2;
    }}

    Card {{
        height: auto;
        margin: 0 0 1 0;
        padding: 1 2;
        border: round {AMBER};
    }}

    .card-title {{
        color: {AMBER};
        text-style: bold;
        height: 1;
    }}

    .card-subtitle {{
        color: {WARM_GRAY};
        height: 1;
    }}

    .card-body {{
        color: {PAPER};
        padding: 1 0 0 0;
    }}

    .muted {{
        color: {WARM_GRAY};
    }}

    .accent {{
        color: {AMBER};
    }}

    .cool {{
        color: {COOL_BLUE};
    }}

    .dim {{
        color: #4A4540;
    }}

    .quote {{
        color: {PAPER};
        padding: 0 0 0 2;
    }}

    .keyword {{
        color: {AMBER};
        text-style: bold;
    }}

    .streak {{
        color: {AMBER_DEEP};
        text-style: bold;
    }}

    .hot {{
        color: #FF6B6B;
        text-style: bold;
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", show=False),
        Binding("1", "mode('writing')", "1 写作"),
        Binding("2", "mode('list')", "2 列表"),
        Binding("3", "mode('diary')", "3 日记"),
        Binding("4", "mode('mirror')", "4 镜像"),
        Binding("5", "mode('anniversary')", "5 周年"),
        Binding("6", "mode('rescue')", "6 急救"),
        Binding("7", "mode('ai')", "7 AI"),
        Binding("q", "quit", "q 退出", show=False),
        Binding("?", "help", "? 帮助"),
    ]

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
    MODE_GLYPH = {
        "writing": "✎",
        "list": "☰",
        "diary": "✦",
        "mirror": "◐",
        "anniversary": "✧",
        "rescue": "❅",
        "ai": "◈",
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

    # ── Compose ──────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(id="mode-indicator")
        with VerticalScroll(id="main-area"):
            yield Static("加载中…", id="content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "拾光 · AfterGlow"
        self.sub_title = f"v{__version__}  ·  {self.folder}"
        self.render_mode()

    # ── Actions ──────────────────────────────────────

    def action_mode(self, mode: str) -> None:
        if mode not in self.MY_MODES:
            return
        self.current_mode = mode
        self.render_mode()

    def action_help(self) -> None:
        self.push_screen("help")

    # ── 顶部状态条 ──────────────────────────────────────

    def render_mode(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        m = self.current_mode
        label = self.MODE_LABELS[m]
        glyph = self.MODE_GLYPH[m]
        now = datetime.now().strftime("%H:%M")
        # 1-7 模式提示
        mode_pills = " ".join(
            f"[{i}] {self.MODE_LABELS[k]}" for i, k in enumerate(self.MY_MODES, 1)
        )
        active = f"[reverse] [black on {AMBER}] {glyph} {label} [/]"
        others = " ".join(
            f"[dim][[{i}] {self.MODE_LABELS[k]}][/]"
            for i, k in enumerate(self.MY_MODES, 1)
            if k != m
        )
        indicator.update(
            f" 拾光  {ARROW}  {active}  {others}    "
            f"[dim]{self.folder}  {ARROW}  {now}[/]"
        )

        content = self.query_one("#content", Static)
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

    # ── Card 辅助 ──────────────────────────────────────

    def _card(self, title: str, body: str, subtitle: str = "",
              title_color: str = AMBER) -> str:
        """Render a card with title + body. The card has rounded
        border (rendered by CSS), we just provide the content."""
        if subtitle:
            return (
                f"[{title_color}]{title}[/]  [dim]{subtitle}[/]\n"
                f"{body}"
            )
        return f"[{title_color}]{title}[/]\n{body}"

    # ── 1 写作 ──────────────────────────────────────

    def render_writing(self, target: Static) -> None:
        self.refresh_entries()
        lines = []
        lines.append(f"[{AMBER}]{STAR} 写作 · {len(self.entries)} 篇[/]")
        lines.append(f"[dim]{self.folder}[/]")
        lines.append("")

        if not self.entries:
            lines.append(f"[dim]还没有日记。先按 `n` 新建今天的。[/]")
        else:
            lines.append(f"[dim]最近 20 篇  ·  按 ↑↓ 选择 · Enter 打开 · n 新建 · dd 删除[/]")
            lines.append("")
            for e in self.entries[:20]:
                # 7 chars for date, then padded title
                date_str = e.date.strftime("%Y-%m-%d")
                weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][e.date.weekday()]
                title = e.title[:30]
                # meta line
                meta_parts = []
                if e.frontmatter.mood is not None:
                    meta_parts.append(f"mood {e.frontmatter.mood}")
                if e.frontmatter.weather:
                    meta_parts.append(e.frontmatter.weather)
                if e.frontmatter.tags:
                    meta_parts.append(" ".join(f"#{t}" for t in e.frontmatter.tags[:3]))
                mq = e.frontmatter.extra.get("mood_quick")
                if mq:
                    meta_parts.append(mq)
                meta = "  ".join(meta_parts)
                lines.append(
                    f"  [{AMBER}]{date_str}[/]  [{weekday}]  {title}"
                    + (f"   [dim]{meta}[/]" if meta else "")
                )
        target.update("\n".join(lines))

    # ── 2 列表 ──────────────────────────────────────

    def render_list(self, target: Static) -> None:
        self.refresh_entries()
        lines = [f"[{AMBER}]{STAR} 全部日记 · {len(self.entries)} 篇[/]", ""]
        if not self.entries:
            lines.append(f"[dim]还没有日记[/]")
            target.update("\n".join(lines))
            return

        from collections import defaultdict
        by_month: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries:
            by_month[e.date.strftime("%Y-%m")].append(e)

        for month in sorted(by_month.keys(), reverse=True):
            lines.append(f"  [{AMBER}]{month}[/]")
            for e in sorted(by_month[month], key=lambda x: x.date, reverse=True):
                title = e.title[:35]
                preview = e.preview[:60].replace("\n", " ")
                lines.append(f"    [dim]·[/]  {e.date.strftime('%m-%d')}  {title}  [dim]{preview}[/]")
            lines.append("")

        target.update("\n".join(lines))

    # ── 3 日记 (default) ──────────────────────────────────────

    def render_diary(self, target: Static) -> None:
        """Main 'today' view: today's diary + 今日签 + 周年 + 急救."""
        self.refresh_entries()
        today_e = today_entry(self.entries)
        prompt = dp.pick_for(date_cls.today())
        done_today = dp.is_done_today(self.state)
        streak = self.state.daily_practice_streak
        longest = self.state.daily_practice_longest
        anniv_matches = anniv.find(self.entries)
        signal = resc.detect(self.entries)

        lines: list[str] = []

        # ── Header
        today_str = date_cls.today().isoformat()
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date_cls.today().weekday()]
        lines.append(f"[{AMBER}]{STAR} 拾光 · {today_str} {weekday}[/]")
        lines.append("")

        # ── 今日日记 card
        if today_e:
            title = today_e.title or "无标题"
            meta = []
            if today_e.frontmatter.mood is not None:
                meta.append(f"mood [{AMBER}]{today_e.frontmatter.mood}[/]")
            if today_e.frontmatter.weather:
                meta.append(today_e.frontmatter.weather)
            if today_e.frontmatter.tags:
                meta.append(" ".join(f"[{AMBER}]#{t}[/]" for t in today_e.frontmatter.tags))
            mq = today_e.frontmatter.extra.get("mood_quick")
            if mq:
                meta.append(f"情绪 [{AMBER}]{mq}[/]")
            meta_str = "  ".join(meta)
            lines.append(f"  [dim]──────[/]  [{AMBER}]{ARROW} 今天的日记[/]")
            lines.append(f"  [{AMBER_SOFT}]{title}[/]")
            if meta_str:
                lines.append(f"  [dim]{meta_str}[/]")
            lines.append("")
            # body
            body = today_e.body.strip()
            for line in body.split("\n"):
                if line.startswith("# "):
                    continue
                if line.startswith("## "):
                    lines.append(f"  [{AMBER}]{line.lstrip('# ').strip()}[/]")
                elif line.startswith("> "):
                    lines.append(f"  [dim]{DOT}[/]  [italic]{line[2:]}[/]")
                elif line.strip():
                    lines.append(f"  {line}")
                else:
                    lines.append("")
            # trim to first 25 lines to keep today card compact
            if len(lines) > 40:
                lines = lines[:40] + [f"  [dim]… (更多按 1 切到写作 tab)[/]"]
        else:
            lines.append(f"  [dim]──────[/]  [{AMBER}]{ARROW} 今天的日记[/]")
            lines.append(f"  [dim]今天还没写。按 `n` 新建。[dim]")
        lines.append("")

        # ── 今日签 card
        lines.append(f"  [dim]──────[/]  [{AMBER}]{ARROW} 今日签[/]")
        lines.append(f"  [dim]{prompt.category}[/]")
        lines.append(f"  [{AMBER_SOFT}]{prompt.text}[/]")
        lines.append("")
        if done_today:
            lines.append(f"  [{AMBER}]{STAR} 今日已完成[/]  [dim]连续 {streak} 天 · 最长 {longest}[/]")
        else:
            streak_hint = ""
            if streak >= 3:
                streak_hint = f"  [dim]当前连续 {streak} 天  [streak]{STAR}[/] · [dim]最长 {longest} 天[/]"
            elif streak > 0:
                streak_hint = f"  [dim]当前 {streak} 天 · 最长 {longest} 天[/]"
            lines.append(f"  [dim]按 r 写回答 (1-2 句就够){streak_hint}[/]")
        lines.append("")

        # ── 周年回响
        if anniv_matches:
            years_label = "/".join(f"{m.yearsAgo}y" for m in anniv_matches)
            lines.append(f"  [dim]──────[/]  [{AMBER}]{ARROW} 周年回响[/]  [dim]{years_label}[/]")
            lines.append("")
            for m in anniv_matches[:3]:
                lines.append(f"  [{AMBER_SOFT}]{m.years_ago} 年前[/]  [dim]·[/]  {m.entry.title}")
                # 1-line preview
                preview = m.preview.split("\n")[0][:60]
                lines.append(f"  [dim]{preview}[/]")
                lines.append("")

        # ── 情绪急救
        if signal.level != "none":
            emoji = "❅" if signal.level == "intervene" else "☁"
            title = "你之前走过这段路" if signal.level == "intervene" else "你最近不太好"
            lines.append(f"  [dim]──────[/]  [{COOL_BLUE}]{ARROW} 情绪急救[/]  [dim]{signal.days_affected} 天[/]")
            lines.append(f"  [{COOL_BLUE}]{emoji} {title}[/]")
            lines.append("")
            rescued = resc.find_rescued_entries(self.entries)
            for e in rescued[:2]:
                lines.append(f"  [{COOL_BLUE}]{e.date.isoformat()}[/]  [dim]·[/]  {e.title[:30]}")
                preview = e.body.strip().split("\n")[0][:60]
                lines.append(f"  [dim]{preview}[/]")
                lines.append("")

        # ── Footer hint
        lines.append("")
        lines.append(f"  [dim]────────  1 写作 · 2 列表 · 4 镜像 · 5 周年 · 6 急救 · r 写回答 · ? 帮助[/]")

        target.update("\n".join(lines))

    # ── 4 镜像 ──────────────────────────────────────

    def render_mirror(self, target: Static) -> None:
        self.refresh_entries()
        if len(self.entries) < 5:
            target.update(
                f"[{AMBER}]{STAR} 镜像回放[/]\n\n"
                f"[dim]日记还不够多（至少 5 篇）。继续写。[/]"
            )
            return
        try:
            reflections = mirr.sample(self.entries, seed=random.randint(0, 99999))
        except Exception as e:
            target.update(f"[red]镜像采样失败: {e}[/]")
            return
        if not reflections:
            target.update(f"[{AMBER}]{STAR} 镜像回放[/]\n\n[dim]没有可采样的句子。[/]")
            return

        lines = [
            f"[{AMBER}]{STAR} 镜像回放[/]  [dim]从过去 180 天里挑了 {len(reflections)} 句[/]",
            f"[dim]按 r 重新采样 · 1-7 切换模式[/]",
            "",
        ]
        for i, r in enumerate(reflections, 1):
            lines.append(f"  [{AMBER}]{i:2d}[/]  [dim]{r.source_date.isoformat()}[/]  [dim]{ARROW}[/]  {r.source_title[:25]}")
            lines.append(f"      [{AMBER_SOFT}]\"{r.text}\"[/]")
            lines.append("")
        target.update("\n".join(lines))

    # ── 5 周年 ──────────────────────────────────────

    def render_anniversary(self, target: Static) -> None:
        self.refresh_entries()
        matches = anniv.find(self.entries)
        today_str = date_cls.today().isoformat()
        if not matches:
            target.update(
                f"[{AMBER}]{STAR} 周年回响 · {today_str}[/]\n\n"
                f"[dim]往年的今天还没有日记。[/]\n\n"
                f"[dim]继续写，未来某年的今天会再回来。[/]"
            )
            return
        lines = [f"[{AMBER}]{STAR} 周年回响 · {today_str}[/]  [dim]{len(matches)} 年[/]", ""]
        for m in matches:
            lines.append(f"  [dim]──────[/]  [{AMBER}]{m.years_ago} 年前[/]  [dim]·[/]  {m.entry.title}")
            lines.append(f"  [dim]{m.entry.date.isoformat()}[/]")
            lines.append("")
            for line in m.preview.split("\n"):
                if line.strip():
                    lines.append(f"  {line}")
            lines.append("")
        target.update("\n".join(lines))

    # ── 6 急救 ──────────────────────────────────────

    def render_rescue(self, target: Static) -> None:
        self.refresh_entries()
        signal = resc.detect(self.entries)

        if signal.level == "none":
            target.update(
                f"[{COOL_BLUE}]{STAR} 情绪急救[/]\n\n"
                f"[dim]过去 14 天没有检测到连续 3 天低分。[/]\n\n"
                f"[dim]急救功能只在你连续 3 天情绪低时浮现。[/]\n"
                f"[dim]当前最近：{signal.sample_text or '无'}[/]"
            )
            return

        rescued = resc.find_rescued_entries(self.entries)
        emoji = "❅" if signal.level == "intervene" else "☁"
        title = "你之前走过这段路" if signal.level == "intervene" else "你最近不太好"
        lines = [
            f"[{COOL_BLUE}]{STAR} 情绪急救[/]  [dim]{signal.days_affected} 天[/]",
            f"[{COOL_BLUE}]{emoji} {title}[/]",
            f"[dim]不需要做任何事。可以只是看一会儿。[/]",
            "",
        ]
        for e in rescued:
            lines.append(f"  [dim]──────[/]  [{COOL_BLUE}]{e.date.isoformat()}[/]  [dim]·[/]  {e.title}")
            lines.append("")
            # first 6 lines
            for line in e.body.strip().split("\n")[:6]:
                if line.strip():
                    lines.append(f"  {line}")
            if len(e.body.strip().split("\n")) > 6:
                lines.append(f"  [dim]…[/]")
            lines.append("")
        target.update("\n".join(lines))

    # ── 7 AI ──────────────────────────────────────

    def render_ai(self, target: Static) -> None:
        llm = self.state.llm
        api_state = "[{AMBER}]已设置[/]".format(AMBER=AMBER) if llm.api_key else f"[{WARM_GRAY}]未设置 — 用 shi config（v0.2）[/]"
        target.update(
            f"[{AMBER}]{STAR} AI 助手[/]  [dim]v0.1 暂未实现[/]\n\n"
            f"**当前 LLM 配置**:\n\n"
            f"  Provider  [{AMBER}]{llm.provider}[/]\n"
            f"  Base URL  [dim]{llm.base_url}[/]\n"
            f"  Model     [{AMBER}]{llm.model}[/]\n"
            f"  API key   {api_state}\n\n"
            f"[dim]v0.2 会加入 free-form 问答 + 流式输出。[/]"
        )


# ── 帮助屏 ──────────────────────────────────────

class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape,?,q", "app.pop_screen", "返回", show=False),
    ]

    CSS = f"""
    HelpScreen {{
        background: #14110F;
        align: center middle;
    }}
    #help-container {{
        width: 70%;
        max-width: 80;
        height: auto;
        padding: 2 3;
        border: round {AMBER};
        background: #1F1A16;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Static(self._help_text(), id="help-content"),
            id="help-container",
        )

    def _help_text(self) -> str:
        return (
            f"[{AMBER}]{STAR} 拾光 · 帮助[/]\n\n"
            f"[{AMBER_SOFT}]7 个模式[/]  [dim](按数字键切换)[/]\n\n"
            f"  [bold]1[/] 写作   [dim]—[/]  列表 + 新建/删除\n"
            f"  [bold]2[/] 列表   [dim]—[/]  全部日记，按月分组\n"
            f"  [bold]3[/] 日记   [dim]—[/]  [reverse] [black on {AMBER}] 默认视图 [/]  今天 + 今日签 + 周年 + 急救\n"
            f"  [bold]4[/] 镜像   [dim]—[/]  5-7 句自己写过的话（多样性采样）\n"
            f"  [bold]5[/] 周年   [dim]—[/]  往年今天你写过什么\n"
            f"  [bold]6[/] 急救   [dim]—[/]  连续 3 天情绪低时浮现\n"
            f"  [bold]7[/] AI     [dim]—[/]  自由问答 [dim](v0.2 计划)[/]\n\n"
            f"[{AMBER_SOFT}]常用键[/]\n\n"
            f"  [bold]?[/]   本帮助\n"
            f"  [bold]q[/]   退出\n\n"
            f"[{AMBER_SOFT}]配置文件[/]\n\n"
            f"  [dim]{state_file()}[/]\n\n"
            f"[dim]按 Esc / ? / q 返回[/]"
        )


# ── 注册 + 入口 ──────────────────────────────────────

ShiGuangApp.SCREENS = {"help": HelpScreen}


def main() -> None:
    app = ShiGuangApp()
    app.run()
