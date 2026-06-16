"""Textual app — 拾光 / AfterGlow TUI (v0.2).

4 modes:
  0 首页   (default) — welcome + recent entries + quick actions
  1 编辑   — list + editor (TextArea)
  2 记录   — read-only browser, search
  3 报表   — stats: counts, mood distribution, monthly trend,
              tag frequency, word cloud, streaks
  ? 帮助   — key reference
"""
from __future__ import annotations

from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.widgets import Footer, Static, TextArea, Input, ListView, ListItem, Label, Button

from . import __version__
from .config import load_state, default_diary_folder, state_file, save_state
from .diary import scan_folder, Entry, write_entry, today_entry, parse_date_from_filename
from .frontmatter import Frontmatter
from .markup import md_to_markup
from . import stats as stats_mod
from .logo import render_home_header


# ── 视觉常量 ──────────────────────────────────────────────

AMBER = "#E8A87C"
AMBER_DEEP = "#C97B4F"
AMBER_SOFT = "#F5C7A0"
WARM_GRAY = "#8B8680"
PAPER = "#F5F1EB"
INK = "#1A1A1A"
STAR = "✦"
ARROW = "›"
DOT = "·"


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

    /* Home screen — centered, no scroll */
    #home-screen {{
        align: center middle;
        height: 1fr;
    }}
    #home-content {{
        width: 60;
        height: auto;
        padding: 2 4;
        align: center middle;
    }}
    .menu-item {{
        height: 3;
        width: 36;
        content-align: center middle;
        margin: 1 0;
        background: #1F1A16;
        border: round {AMBER_DEEP};
    }}
    .menu-item:hover {{
        background: #2A201A;
        border: round {AMBER};
    }}
    .menu-item:focus {{
        background: #2A201A;
        border: round {AMBER};
    }}

    /* Other modes — scrollable */
    #content {{
        padding: 1 2;
    }}

    Input {{
        background: #1F1A16;
        border: round {AMBER};
    }}

    TextArea {{
        background: #1F1A16;
        border: round {AMBER};
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", show=False),
        Binding("0", "mode('home')", "0 首页", show=False),
        # Number keys map directly to menu items in HomeView,
        # NOT to mode names. The mapping is:
        #   1 = stats (1st menu item)    2 = edit (2nd)    3 = browse (3rd)
        # When NOT in home, these route to the same-numbered mode
        # (1=edit, 2=browse, 3=stats) — same as before.
        Binding("1", "menu_pick(0)", "1 数据面板", show=False),
        Binding("2", "menu_pick(1)", "2 创作笔记", show=False),
        Binding("3", "menu_pick(2)", "3 洞察笔记", show=False),
        # Arrow / vim keys: routed by current mode (home menu or
        # browse navigation). Action handlers check the mode.
        Binding("up",   "arrow_up",   show=False),
        Binding("down", "arrow_down", show=False),
        Binding("left",  "arrow_left",  show=False),
        Binding("right", "arrow_right", show=False),
        Binding("j", "arrow_down", show=False),
        Binding("k", "arrow_up",   show=False),
        Binding("enter", "arrow_enter", show=False),
        Binding("pageup",   "arrow_pageup",   show=False),
        Binding("pagedown", "arrow_pagedown", show=False),
        Binding("home", "arrow_home", show=False),
        Binding("end",  "arrow_end",  show=False),
        Binding("escape", "go_home_or_back", show=False),
        Binding("c", "change_folder", show=False),
        Binding("?", "help", "? 帮助"),
        Binding("q", "quit", "q 退出", show=False),
    ]

    def action_help(self) -> None:
        self.push_screen("help")

    def action_go_home_or_back(self) -> None:
        """ESC: if a modal screen is on top, close it; otherwise
        return to home mode.
        """
        # If a non-base screen is active, pop it (modal/overlay dismissal)
        if len(self.screen_stack) > 1:
            self.pop_screen()
            return
        # Otherwise go home (no-op if already home)
        if self.current_mode != "home":
            self.current_mode = "home"
            self.render_mode()

    def action_change_folder(self) -> None:
        """`c` — open the folder-change modal from any mode."""
        self.push_screen(ChangeFolderScreen(self))

    MY_MODES = ["home", "edit", "browse", "stats"]
    MODE_LABELS = {
        "home": "首页",
        "edit": "编辑",
        "browse": "记录",
        "stats": "报表",
    }
    MODE_GLYPH = {
        "home": "⌂",
        "edit": "✎",
        "browse": "☰",
        "stats": "▦",
    }

    current_mode: reactive[str] = reactive("home")

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
        # The home screen and other modes use different layouts;
        # we mount/unmount them dynamically in render_mode().
        yield Container(id="main-area")
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

    def action_menu_pick(self, idx: int) -> None:
        """Press `1`/`2`/`3` — picks the idx-th menu item.

        - In home mode: activates the menu item (stats/edit/browse
          in display order).
        - In other modes: shortcuts to the corresponding mode by
          number. Same numbers as the menu (1=stats, 2=edit, 3=browse)
          — but in non-home modes the numbers are still shown in the
          status bar pills, so this is intuitive.
        """
        menu_modes = ["stats", "edit", "browse"]
        if not (0 <= idx < len(menu_modes)):
            return
        target_mode = menu_modes[idx]
        if self.current_mode == "home":
            try:
                home = self.query_one(HomeView)
                home.action_menu_activate(idx)
                return
            except Exception:
                pass
        # Not in home — direct mode switch
        self.current_mode = target_mode
        self.render_mode()

    def action_home_menu_up(self) -> None:
        if self.current_mode == "home":
            try:
                self.query_one(HomeView).action_menu_up()
            except Exception:
                pass

    def action_home_menu_down(self) -> None:
        if self.current_mode == "home":
            try:
                self.query_one(HomeView).action_menu_down()
            except Exception:
                pass

    def action_home_menu_enter(self) -> None:
        if self.current_mode == "home":
            try:
                self.query_one(HomeView).action_menu_enter()
            except Exception:
                pass

    # ── Arrow-key router — dispatches by current mode ────────────

    def _find_browse_view(self) -> Optional["BrowseView"]:
        try:
            return self.query_one(BrowseView)
        except Exception:
            return None

    def action_arrow_up(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_up()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_up()

    def action_arrow_down(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_down()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_down()

    def action_arrow_left(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_left()

    def action_arrow_right(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_right()

    def action_arrow_enter(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_enter()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_enter()

    def action_arrow_pageup(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_pageup()

    def action_arrow_pagedown(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_pagedown()

    def action_arrow_home(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_home()

    def action_arrow_end(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_browse_end()

    # ── 顶部 status bar ──────────────────────────────────────

    def render_mode(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        m = self.current_mode
        label = self.MODE_LABELS[m]
        glyph = self.MODE_GLYPH[m]
        now = datetime.now().strftime("%H:%M")
        # pills: 0 首页 · 1 编辑 · 2 记录 · 3 报表 · ? 帮助
        pills = []
        for k in self.MY_MODES:
            i = self.MY_MODES.index(k)
            if k == m:
                # Active mode: bright amber text only — no reverse / block
                pill = f"[bold {AMBER}]{glyph} {self.MODE_LABELS[k]}[/]"
            else:
                # Inactive: soft amber, dim
                pill = f"[{AMBER_SOFT}][[{i}] {self.MODE_LABELS[k]}][/]"
            pills.append(pill)
        active = next(p for p in pills if f"bold {AMBER}" in p)
        others = " ".join(p for p in pills if f"bold {AMBER}" not in p)
        indicator.update(
            f" 拾光  {ARROW}  {active}  {others}    "
            f"[dim]{self.folder.name}{ARROW} {now}[/]"
        )

        # Clear and re-render the main area
        main = self.query_one("#main-area")
        main.remove_children()
        if self.current_mode == "home":
            main.mount(HomeView(self))
        elif self.current_mode == "browse":
            # Browse mode uses an interactive ListView + preview pane,
            # not the generic Static-content pipeline.
            self.refresh_entries()
            main.mount(BrowseView(self))
        else:
            scroll = VerticalScroll()
            main.mount(scroll)
            scroll.mount(Static("加载中…", id="content"))
            # Now run the renderer
            try:
                content = self.query_one("#content", Static)
                renderer = getattr(self, f"render_{self.current_mode}", None)
                if renderer is None:
                    content.update(f"模式 {self.current_mode} 暂未实现")
                    return
                renderer(content)
            except Exception as e:
                content.update(f"[red]渲染出错: {e}[/]")

    def refresh_entries(self) -> None:
        self.entries = scan_folder(self.folder)

    # ── 0 首页 (rendered by HomeView widget) ──────────────────────

    def render_home(self, target: Static) -> None:
        # Unused — HomeView handles the home screen.
        pass

    # ── 1 编辑 ──────────────────────────────────────

    def render_edit(self, target: Static) -> None:
        self.refresh_entries()
        target.update(self._edit_list_view())

    def _edit_list_view(self) -> str:
        """Render the edit-mode list."""
        lines: list[str] = []
        lines.append(f"[bold {AMBER}]{STAR} 编辑 · {len(self.entries)} 篇[/]")
        lines.append(f"[dim]{self.folder}[/]")
        lines.append("")
        lines.append(f"  [dim]快捷键: n 新建今日 · Enter 打开编辑 · dd 删除[/]")
        lines.append("")

        if not self.entries:
            lines.append(f"  [dim]还没有日记。按 n 新建今天的。[/]")
            return "\n".join(lines)

        # Group by year-month
        from collections import defaultdict
        by_month: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries:
            by_month[e.date.strftime("%Y-%m")].append(e)

        i = 1
        for month in sorted(by_month.keys(), reverse=True):
            lines.append(f"  [{AMBER}]{month}[/]")
            for e in sorted(by_month[month], key=lambda x: x.date, reverse=True):
                title = e.title[:35] if e.title else "无标题"
                meta_parts = []
                if e.frontmatter.mood is not None:
                    meta_parts.append(f"m{e.frontmatter.mood}")
                if e.frontmatter.tags:
                    meta_parts.append(" ".join(f"#{t}" for t in e.frontmatter.tags[:2]))
                mq = e.frontmatter.extra.get("mood_quick")
                if mq:
                    meta_parts.append(mq)
                meta = f" [dim]{'·'.join(meta_parts)}[/]" if meta_parts else ""
                # Cursor row marker (we don't track cursor position in render,
                # but render with [1] [2] prefix for visual selection index)
                lines.append(f"    [{AMBER} dim]\\[{i:>2}][/]  {e.date.strftime('%m-%d')}  [bold]{title}[/]{meta}")
                i += 1
            lines.append("")
        return "\n".join(lines)

    # ── 2 记录 ──────────────────────────────────────

    def render_browse(self, target: Static) -> None:
        # Browse mode is rendered by BrowseView widget (mounted
        # directly in render_mode). This method is left here as a
        # no-op fallback in case the generic pipeline is hit.
        target.update(
            f"[bold {AMBER}]{STAR} 记录[/]\n\n"
            f"[dim]请按 2 切到记录 tab。[/]"
        )

    # ── 3 报表 ──────────────────────────────────────

    def render_stats(self, target: Static) -> None:
        self.refresh_entries()
        report = stats_mod.compute(self.entries)
        lines: list[str] = []

        lines.append(f"[bold {AMBER}]{STAR} 数据报表 · {report.total_entries} 篇[/]")
        lines.append(f"[dim]{self.folder}[/]")
        lines.append("")

        if not report.total_entries:
            lines.append(f"  [dim]还没有日记，没有数据可统计。[/]")
            target.update("\n".join(lines))
            return

        # ── 概览
        lines.append(f"  [dim]──────[/]  [dim]概览[/]")
        lines.append("")
        if report.date_range:
            lines.append(f"    日期范围   [{AMBER}]{report.date_range[0]}[/] → [{AMBER}]{report.date_range[1]}[/]")
        lines.append(f"    总字数     [{AMBER}]{report.total_words:,}[/]")
        lines.append(f"    总字符     [{AMBER}]{report.total_characters:,}[/]")
        lines.append(f"    平均字数   [{AMBER}]{report.average_words_per_entry:.0f}[/] 字/篇")
        lines.append(f"    写作 streak  [bold {AMBER}]{report.current_streak_days}[/] 天 (最长 {report.longest_streak_days} 天)")
        lines.append("")

        # ── 心情分布
        if report.mood_distribution:
            lines.append(f"  [dim]──────[/]  [dim]心情分布 (1=最差, 5=最好)[/]")
            lines.append("")
            lines.append(self._bar_chart_mood(report.mood_distribution))
            lines.append("")

        # ── 月度字数趋势
        if report.monthly_trend:
            lines.append(f"  [dim]──────[/]  [dim]月度字数 (最近 6 个月)[/]")
            lines.append("")
            lines.append(self._bar_chart_monthly(report.monthly_trend))
            lines.append("")

        # ── Tag 频率 Top 10
        if report.top_tags:
            lines.append(f"  [dim]──────[/]  [dim]Tag 频率 Top 10[/]")
            lines.append("")
            max_count = report.top_tags[0].count
            for tc in report.top_tags[:10]:
                bar_width = (tc.count * 16) // max(max_count, 1) if max_count else 0
                bar = "█" * bar_width
                lines.append(f"    [{AMBER}]#{tc.tag:<10}[/]  [{AMBER_SOFT}]{bar}[/]  [dim]{tc.count}[/]")
            lines.append("")

        # ── Word cloud
        if report.word_cloud:
            lines.append(f"  [dim]──────[/]  [dim]词云 (Top 30 · CJK + Latin)[/]")
            lines.append("")
            lines.append(self._word_cloud_render(report.word_cloud))
            lines.append("")

        lines.append(f"  [dim]────────  0 首页 · 1 编辑 · 2 记录 · 3 报表 · ? 帮助[/]")
        target.update("\n".join(lines))

    # ── Bar chart helpers ──────────────────────────────────────

    def _bar_chart_mood(self, buckets) -> str:
        """Render a horizontal bar chart for mood distribution."""
        max_count = max(b.count for b in buckets) if buckets else 1
        lines: list[str] = []
        # Ensure all 1..5 are represented
        by_score = {b.score: b.count for b in buckets}
        for score in range(1, 6):
            count = by_score.get(score, 0)
            bar_width = (count * 20) // max(max_count, 1) if max_count else 0
            bar = "█" * bar_width
            label = ["很差", "差", "一般", "好", "很好"][score - 1]
            lines.append(f"    [{AMBER}]{score} {label:<4}[/]  [{AMBER_SOFT}]{bar:<20}[/]  [dim]{count}[/]")
        return "\n".join(lines)

    def _bar_chart_monthly(self, points) -> str:
        """Render monthly word-count trend."""
        max_words = max(p.word_count for p in points) if points else 1
        lines: list[str] = []
        for p in points:
            bar_width = (p.word_count * 24) // max(max_words, 1) if max_words else 0
            bar = "█" * bar_width
            # show count
            lines.append(f"    [{AMBER}]{p.label:<6}[/]  [{AMBER_SOFT}]{bar:<24}[/]  [dim]{p.word_count:>5,} 字 · {p.entry_count} 篇[/]")
        return "\n".join(lines)

    def _word_cloud_render(self, words: list[tuple[str, int]]) -> str:
        """Render a small word cloud as colored text with varying sizes."""
        if not words:
            return ""
        # Simple two-band sizing: top 10 are "big" (bold amber), rest "small" (dim)
        out: list[str] = []
        # Render in 3 columns × ~10 rows for a compact grid
        # Group by max count to size them
        max_count = words[0][1]
        # Build 3-column grid
        col_size = (len(words) + 2) // 3
        cols = [words[i:i + col_size] for i in range(0, len(words), col_size)]
        rows = max(len(c) for c in cols)
        for row in range(rows):
            row_pieces = []
            for c in cols:
                if row < len(c):
                    word, count = c[row]
                    # Size: bigger words (count > max/3) get amber bold
                    if count >= max_count * 0.5:
                        style = f"[bold {AMBER}]"
                    elif count >= max_count * 0.25:
                        style = f"[{AMBER}]"
                    else:
                        style = f"[{AMBER_SOFT}]"
                    row_pieces.append(f"{style}{word}[/]")
                else:
                    row_pieces.append("     ")
            out.append("    " + "  ".join(f"{p:<14}" for p in row_pieces))
        return "\n".join(out)


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
            f"[bold {AMBER}]{STAR} 拾光 · 帮助[/]\n\n"
            f"[bold {AMBER_SOFT}]4 个模式[/]  [dim](按数字键切换)[/]\n\n"
            f"  [bold]0[/] 首页   [dim]—[/]  [reverse] [black on {AMBER}] 默认视图 [/]  概览 + 最近 5 篇 + 快捷操作\n"
            f"  [bold]1[/] 编辑   [dim]—[/]  列表 + 新建 + 编辑（TextArea 编辑器）\n"
            f"  [bold]2[/] 记录   [dim]—[/]  全部日记浏览 + 搜索\n"
            f"  [bold]3[/] 报表   [dim]—[/]  数据统计 + 趋势 + Tag 频率 + 词云\n\n"
            f"[bold {AMBER_SOFT}]常用键[/]\n\n"
            f"  [bold]?[/]   本帮助\n"
            f"  [bold]q[/]   退出\n\n"
            f"[bold {AMBER_SOFT}]配置文件[/]\n\n"
            f"  [dim]{state_file()}[/]\n\n"
            f"[dim]按 Esc / ? / q 返回[/]"
        )


# ── 注册 + 入口 ──────────────────────────────────────

ShiGuangApp.SCREENS = {"help": HelpScreen}


# ── 改目录 Modal ──────────────────────────────────────

class ChangeFolderScreen(ModalScreen):
    """Modal: prompt user to type a folder path. On submit,
    update app state and refresh."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "取消", show=False),
    ]

    CSS = f"""
    ChangeFolderScreen {{
        background: #14110F;
        align: center middle;
    }}
    #cf-container {{
        width: 70%;
        max-width: 80;
        height: auto;
        padding: 2 3;
        border: round {AMBER};
        background: #1F1A16;
    }}
    #cf-title {{
        margin-bottom: 1;
    }}
    #cf-current {{
        margin-bottom: 1;
    }}
    #cf-input {{
        margin-bottom: 1;
    }}
    #cf-hint {{
        margin-top: 1;
    }}
    """

    def __init__(self, app: "ShiGuangApp") -> None:
        super().__init__()
        self._app_ref = app

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                f"[bold {AMBER}]{STAR} 修改日记目录[/]",
                id="cf-title",
            ),
            Static(
                f"[dim]当前: {self._app_ref.folder}[/]",
                id="cf-current",
            ),
            Input(
                value=str(self._app_ref.folder),
                placeholder="新目录的绝对路径(留空取消)",
                id="cf-input",
            ),
            Static(
                f"[dim]回车确认 · Esc 取消 · 路径不存在将自动创建[/]",
                id="cf-hint",
            ),
            id="cf-container",
        )

    def on_mount(self) -> None:
        # Focus the input on mount
        self.query_one("#cf-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            self.app.pop_screen()
            return
        new_path = Path(raw).expanduser().resolve()
        try:
            new_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Show error inline; do not close.
            self.query_one("#cf-hint", Static).update(
                f"[red]创建目录失败: {e}[/]"
            )
            return
        # Update app state
        self._app_ref.state.diary_folder = str(new_path)
        save_state(self._app_ref.state)
        self._app_ref.folder = new_path
        self._app_ref.refresh_entries()
        self._app_ref.render_mode()
        self.app.pop_screen()


# ── 记录 (Browse) 视图 — ListView + Markdown 预览 ──────────────────────

class BrowseView(Container):
    """The '记录' (browse) mode: a left-side list of entries grouped by
    month, and a right-side preview pane showing the selected entry's
    rendered markdown.

    Pure keyboard, vim-style. No mouse / Tab / click.

    Two focus regions, switched with ←/→:
      - "list"   (default on mount) — ↑/↓ or k/j move the cursor, Enter
                  re-renders the preview for the highlighted row.
      - "preview" — ↑/↓ or k/j scroll the preview pane; ← returns to
                    the list.

    Global keys (always available in browse mode):
      - 0 / Esc: back to home
      - c:       change diary folder
    """

    DEFAULT_CSS = f"""
    BrowseView {{
        height: 1fr;
    }}
    #browse-header {{
        height: 3;
        padding: 0 1;
    }}
    #browse-body {{
        height: 1fr;
    }}
    #browse-list {{
        width: 40%;
        min-width: 24;
        height: 1fr;
        padding: 0 1;
        border: round {AMBER_DEEP};
        background: #14110F;
    }}
    #browse-list.focused {{
        border: round {AMBER};
    }}
    #browse-preview {{
        width: 1fr;
        height: 1fr;
        border: round {AMBER_DEEP};
        background: #14110F;
    }}
    #browse-preview.focused {{
        border: round {AMBER};
    }}
    #preview-scroll {{
        height: 1fr;
    }}
    """

    BINDINGS = [
        # BrowseView keys are routed via the App-level BINDINGS
        # (action_arrow_*), because Container is not focusable by
        # default. Keeping this empty prevents stale duplicates.
    ]

    # Two focus regions. Reactive so we can watch changes and re-style
    # the borders.
    focus_region: reactive[str] = reactive("list")
    # Cursor index into self._flat (skipping month-header rows).
    cursor: reactive[int] = reactive(0)

    def __init__(self, app: "ShiGuangApp") -> None:
        super().__init__(id="browse-view")
        self._app_ref = app
        # Two parallel arrays describing the rendered list:
        #   _rows        : list of (kind, payload) where kind in {"header","entry"}
        #   _flat        : list of Entry, indexed the same way as kind=="entry" rows
        self._rows: list[tuple[str, object]] = []
        self._flat: list[Entry] = []

    def compose(self) -> ComposeResult:
        yield Static(self._render_header(), id="browse-header")
        with Horizontal(id="browse-body"):
            yield Static("", id="browse-list")
            with VerticalScroll(id="preview-scroll"):
                yield Static(self._render_empty_preview(), id="browse-preview")

    def on_mount(self) -> None:
        self._populate_list()
        # Style initial focus
        self._apply_focus_style()

    # ── Header / hint line ──────────────────────────────────────

    def _render_header(self) -> str:
        n = len(self._app_ref.entries)
        focus_label = "列表" if self.focus_region == "list" else "预览"
        return (
            f"[bold {AMBER}]{STAR} 记录 · {n} 篇[/]   "
            f"[dim]焦点: [{AMBER}]{focus_label}[/][/]\n"
            f"[dim]← → 切焦点 · 在「列表」用 ↑↓ 选条目 · 在「预览」用 ↑↓ 滚动 · 0 / Esc 返首页 · c 改目录[/]"
        )

    def _render_empty_preview(self) -> str:
        return (
            f"\n[dim]    选择左侧任一日记条目,这里会显示内容预览。[/]\n"
        )

    # ── List population ──────────────────────────────────────

    def _populate_list(self) -> None:
        from collections import defaultdict
        self._rows = []
        self._flat = []
        by_month: dict[str, list[Entry]] = defaultdict(list)
        for e in self._app_ref.entries:
            by_month[e.date.strftime("%Y-%m")].append(e)

        for month in sorted(by_month.keys(), reverse=True):
            self._rows.append(("header", month))
            for e in sorted(by_month[month], key=lambda x: x.date, reverse=True):
                self._rows.append(("entry", e))
                self._flat.append(e)

        # Clamp cursor
        if self._flat:
            self.cursor = max(0, min(self.cursor, len(self._flat) - 1))
        else:
            self.cursor = 0

        self._render_list()
        self._refresh_preview()

    def _entry_label(self, e: Entry) -> str:
        title = e.title or "无标题"
        mood_badge = ""
        if e.frontmatter.mood is not None:
            mood_badge = f" [dim]m{e.frontmatter.mood}[/]"
        tag_badge = ""
        if e.frontmatter.tags:
            tag_badge = f" [dim]#{e.frontmatter.tags[0]}[/]"
        return (
            f"  [bold {AMBER_SOFT}]{e.date.strftime('%m-%d')}[/]  "
            f"{title[:24]}{mood_badge}{tag_badge}"
        )

    def _render_list(self) -> None:
        list_widget = self.query_one("#browse-list", Static)
        if not self._flat:
            list_widget.update("[dim]还没有日记。按 1 进入编辑 tab 新建。[/]")
            return

        # Find the flat-index cursor position in the rows list. Each
        # "entry" row corresponds to one flat entry; "header" rows do
        # not consume a flat index.
        flat_idx = 0
        out: list[str] = []
        for kind, payload in self._rows:
            if kind == "header":
                out.append(f"  [bold {AMBER_SOFT}]{payload}[/]")
            else:
                e = payload  # type: ignore[assignment]
                is_selected = (self.focus_region == "list" and flat_idx == self.cursor)
                if is_selected:
                    out.append(f"  [reverse] [bold {AMBER}]▸ {self._entry_label(e).strip()}[/]")
                else:
                    out.append(f"  {self._entry_label(e)}")
                flat_idx += 1
        list_widget.update("\n".join(out))

    # ── Preview pane ──────────────────────────────────────

    def _refresh_preview(self) -> None:
        if not self._flat:
            return
        if self.cursor < 0 or self.cursor >= len(self._flat):
            return
        entry = self._flat[self.cursor]
        self._render_preview(entry)
        # Reset scroll position to top whenever selection changes
        try:
            scroll = self.query_one("#preview-scroll", VerticalScroll)
            scroll.scroll_home(animate=False)
        except Exception:
            pass

    def _render_preview(self, entry: Entry) -> None:
        preview_widget = self.query_one("#browse-preview", Static)
        lines: list[str] = []
        lines.append(f"[bold {AMBER}]{entry.date.isoformat()}[/]")
        if entry.title:
            lines.append(f"[bold {AMBER_SOFT}]{entry.title}[/]")
        meta_bits: list[str] = []
        if entry.frontmatter.mood is not None:
            meta_bits.append(f"心情 m{entry.frontmatter.mood}")
        if entry.frontmatter.mood_label:
            meta_bits.append(entry.frontmatter.mood_label)
        if entry.frontmatter.weather:
            meta_bits.append(f"天气 {entry.frontmatter.weather}")
        if entry.frontmatter.tags:
            meta_bits.append(" ".join(f"#{t}" for t in entry.frontmatter.tags))
        if meta_bits:
            lines.append(f"[dim]{'  ·  '.join(meta_bits)}[/]")
        lines.append("")
        try:
            rendered_body = md_to_markup(entry.body or "")
        except Exception as e:
            rendered_body = f"[red]渲染失败: {e}[/]"
        lines.append(rendered_body)
        preview_widget.update("\n".join(lines))

    # ── Focus / key handling ──────────────────────────────────────

    def _apply_focus_style(self) -> None:
        """Re-style list / preview borders to indicate which is focused."""
        try:
            list_widget = self.query_one("#browse-list", Static)
            preview_widget = self.query_one("#browse-preview", Static)
        except Exception:
            return
        if self.focus_region == "list":
            list_widget.set_class(True, "focused")
            preview_widget.set_class(False, "focused")
        else:
            list_widget.set_class(False, "focused")
            preview_widget.set_class(True, "focused")
        # Refresh the header label and list selection indicator
        try:
            self.query_one("#browse-header", Static).update(self._render_header())
        except Exception:
            pass
        self._render_list()

    def watch_focus_region(self, _old, _new) -> None:
        self._apply_focus_style()

    def watch_cursor(self, _old, _new) -> None:
        # Re-render list (cursor moved) and preview
        self._render_list()
        self._refresh_preview()

    # ── Action handlers (called from App-level BINDINGS) ────────

    def _scroll_widget(self) -> VerticalScroll:
        return self.query_one("#preview-scroll", VerticalScroll)

    def action_browse_up(self) -> None:
        if self.focus_region == "list":
            if self._flat:
                self.cursor = (self.cursor - 1) % len(self._flat)
        else:
            self._scroll_widget().scroll_up(animate=False)

    def action_browse_down(self) -> None:
        if self.focus_region == "list":
            if self._flat:
                self.cursor = (self.cursor + 1) % len(self._flat)
        else:
            self._scroll_widget().scroll_down(animate=False)

    def action_browse_left(self) -> None:
        # In list: no-op (you're already at the leftmost pane).
        # In preview: move focus back to list.
        if self.focus_region == "preview":
            self.focus_region = "list"

    def action_browse_right(self) -> None:
        # In list: move focus to preview (if there are entries).
        # In preview: no-op (already at the rightmost pane).
        if self.focus_region == "list" and self._flat:
            self.focus_region = "preview"

    def action_browse_enter(self) -> None:
        # Re-render preview explicitly (also fires automatically on
        # cursor change, but Enter is the explicit "view this entry"
        # affordance in the home view too).
        if self.focus_region == "list" and self._flat:
            self._refresh_preview()

    def action_browse_pageup(self) -> None:
        if self.focus_region == "preview":
            self._scroll_widget().scroll_page_up(animate=False)

    def action_browse_pagedown(self) -> None:
        if self.focus_region == "preview":
            self._scroll_widget().scroll_page_down(animate=False)

    def action_browse_home(self) -> None:
        if self.focus_region == "preview":
            self._scroll_widget().scroll_home(animate=False)
        elif self._flat:
            self.cursor = 0

    def action_browse_end(self) -> None:
        if self.focus_region == "preview":
            self._scroll_widget().scroll_end(animate=False)
        elif self._flat:
            self.cursor = len(self._flat) - 1


# ── 首页 Widget ──────────────────────────────────────

class HomeView(Container):
    """The centered home screen: giant 'A' logo + glow halo + 3
    menu lines.

    Keyboard-only navigation (no mouse, no clickable buttons):
      - `1` / `2` / `3` for direct menu selection
      - `↑` / `↓` (or `j` / `k`) to move the cursor between menu items
      - `Enter` / `→` / `l` to enter the highlighted item
      - `?` for help, `q` to quit
    """

    DEFAULT_CSS = f"""
    HomeView {{
        align: center middle;
        height: 1fr;
    }}
    #home-stack {{
        width: 70;
        height: auto;
        align: center middle;
    }}
    #logo-block {{
        align: center middle;
        width: 100%;
        height: 9;
    }}
    #title {{
        align: center middle;
        width: 100%;
        height: 1;
        margin-top: 1;
    }}
    #subtitle {{
        align: center middle;
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }}
    #menu {{
        align: center middle;
        width: 40;
        height: auto;
    }}
    #footer-hint {{
        align: center middle;
        width: 100%;
        height: 1;
        margin-top: 2;
    }}
    """

    # 3 menu items, in display order. The first one is the
    # initial cursor position.
    MENU_ITEMS = [
        ("stats",  "1", "数据面板"),
        ("edit",   "2", "创作笔记"),
        ("browse", "3", "洞察笔记"),
    ]

    BINDINGS = [
        Binding("1", "menu_activate(0)", show=False),
        Binding("2", "menu_activate(1)", show=False),
        Binding("3", "menu_activate(2)", show=False),
        Binding("up,j", "menu_up", show=False),
        Binding("down,k", "menu_down", show=False),
        Binding("enter,right,l", "menu_enter", show=False),
    ]

    selected: reactive[int] = reactive(0)

    def __init__(self, app: "ShiGuangApp") -> None:
        super().__init__(id="home-screen")
        self._app_ref = app

    def compose(self) -> ComposeResult:
        with Vertical(id="home-stack"):
            # Giant 'A' + glow halo
            yield Static(render_home_header(), id="logo-block")
            # Title + subtitle
            yield Static(
                f"[bold {AMBER}]拾  光[/]",
                id="title"
            )
            yield Static(
                f"[{AMBER_SOFT}]AfterGlow · v{__version__}[/]",
                id="subtitle"
            )
            # 3 menu lines, with cursor (▸) on the selected one
            yield Static(self._render_menu(), id="menu")
            # Footer hint
            yield Static(
                f"[dim]  {self._app_ref.folder}  ·  1-3 直接选 · ↑↓ 移动 · Enter 进入 · ? 帮助 · q 退出[/]",
                id="footer-hint"
            )

    def _render_menu(self) -> str:
        lines = []
        for i, (mode, key, label) in enumerate(self.MENU_ITEMS):
            if i == self.selected:
                # Selected: bright amber + cursor
                lines.append(
                    f"  [bold {AMBER}]▸  {key}  {label}[/]"
                )
            else:
                # Not selected: soft amber (one shade dimmer, but still
                # in the same family — no contrast-block artifact).
                lines.append(
                    f"     [bold {AMBER_SOFT}]   {key}  {label}[/]"
                )
        return "\n".join(lines)

    def on_mount(self) -> None:
        # Re-render the menu whenever the selection changes.
        self.watch(self, "selected", self._on_selection_change)

    def _on_selection_change(self, _old, _new) -> None:
        try:
            menu_widget = self.query_one("#menu", Static)
            menu_widget.update(self._render_menu())
        except Exception:
            pass

    # ── Actions ──────────────────────────────────────

    def action_menu_activate(self, idx: int) -> None:
        """`1` / `2` / `3` direct activation."""
        if 0 <= idx < len(self.MENU_ITEMS):
            self.selected = idx
            self._enter_selected()

    def action_menu_up(self) -> None:
        self.selected = (self.selected - 1) % len(self.MENU_ITEMS)

    def action_menu_down(self) -> None:
        self.selected = (self.selected + 1) % len(self.MENU_ITEMS)

    def action_menu_enter(self) -> None:
        self._enter_selected()

    def _enter_selected(self) -> None:
        mode, _, _ = self.MENU_ITEMS[self.selected]
        self._app_ref.action_mode(mode)


def main() -> None:
    app = ShiGuangApp()
    app.run()


# ── helpers ──────────────────────────────────────────────

def _word_count(text: str) -> int:
    """Same logic as stats._word_count; inlined here to avoid import
    cycle on first build."""
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    import re as _re
    latin_words = len(_re.findall(r"[A-Za-z0-9]+", text))
    return cjk + latin_words