"""Textual app — 拾光 / AfterGlow TUI (v0.2).

4 modes:
  0 首页   (default) — welcome + 3-item menu (stats/edit/browse)
  1 编辑   — list + editor (TextArea) for writing entries
  2 记录   — read-only browser, list + markdown preview
  3 报表   — stats: counts, mood distribution, monthly trend,
              tag frequency, word cloud, streaks
  ? 帮助   — key reference

This module is the app shell: the App class, top-level bindings,
the mode dispatch (render_mode), and the stats renderer. The
individual mode widgets live in their own modules:
  - home_view.py  → HomeView
  - edit_view.py  → EditView
  - browse_view.py → BrowseView
  - modals.py     → HelpScreen, ChangeFolderScreen
  - format.py     → visual_width, bar, strip_markup
  - theme.py      → AMBER palette + glyphs
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Static

from . import __version__, stats as stats_mod
from .browse_view import BrowseView
from .config import default_diary_folder, load_state
from .diary import Entry, scan_folder
from .edit_view import EditView
from .format import bar, visual_width
from .home_view import HomeView
from .modals import ChangeFolderScreen, HelpScreen
from .theme import AMBER, AMBER_DEEP, AMBER_SOFT, ARROW, DOT, STAR


class ShiGuangApp(App):

    SCREENS = {"help": HelpScreen}

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
        # Mode-switch and command keys. NONE are priority=True. The
        # rationale: in the editor (TextArea focused), TextArea's
        # check_consume_key returns True for these characters, so
        # Textual's binding chain filter strips them from the App's
        # binding map. The TextArea handles them as text input. In
        # other modes (home, browse, stats) and in list focus
        # (EditView focused), the App's binding fires and the
        # corresponding action runs.
        Binding("0", "go_home_or_back", "0 首页", show=False),
        Binding("1", "menu_pick(0)", "1 数据面板", show=False),
        Binding("2", "menu_pick(1)", "2 创作笔记", show=False),
        Binding("3", "menu_pick(2)", "3 洞察笔记", show=False),
        # Arrow / vim keys: ↑ / ↓ / ← / → are non-priority, so they
        # get filtered by TextArea when the editor is focused (caret
        # moves). In list focus (EditView focused, doesn't consume
        # keys), the App's binding fires and moves the list cursor.
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
        Binding("ctrl+s", "save", show=False),
        Binding("n", "new_entry", show=False),
        Binding("d", "delete_entry", show=False),
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

    def _find_edit_view(self) -> Optional["EditView"]:
        try:
            return self.query_one(EditView)
        except Exception:
            return None

    def _find_browse_view(self) -> Optional["BrowseView"]:
        try:
            return self.query_one(BrowseView)
        except Exception:
            return None

    def action_save(self) -> None:
        """Ctrl+S — save the current entry (only in edit mode)."""
        if self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_save()

    def action_new_entry(self) -> None:
        """`n` — create today's entry (only in edit mode, list focus)."""
        if self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_new_entry()

    def action_delete_entry(self) -> None:
        """`d` — start the two-step delete (only in edit mode, list focus)."""
        if self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_delete_entry()

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

    def action_arrow_up(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_up()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_cursor_up()
        elif self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_cursor_up()
        elif self.current_mode == "stats":
            self._scroll_stats("up")

    def action_arrow_down(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_down()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_cursor_down()
        elif self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_cursor_down()
        elif self.current_mode == "stats":
            self._scroll_stats("down")

    def _scroll_stats(self, direction: str) -> None:
        """Scroll the stats VerticalScroll widget in 'up' / 'down' direction.

        Stats mode wraps the report in a VerticalScroll (see render_mode),
        but no widget in the stats view is focusable by default. So the
        App's arrow bindings must scroll the scroll container directly,
        not rely on focused-widget routing.
        """
        try:
            vs = self.query_one("#main-area VerticalScroll")
        except Exception:
            return
        if direction == "up":
            vs.scroll_up()
        else:
            vs.scroll_down()

    def action_arrow_left(self) -> None:
        if self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_focus_list()
        elif self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_cursor_left()

    def action_arrow_right(self) -> None:
        # In browse, → no longer focuses the preview (use Enter instead).
        if self.current_mode == "browse":
            return
        elif self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_focus_editor()

    def action_arrow_enter(self) -> None:
        if self.current_mode == "home":
            self.action_home_menu_enter()
        elif self.current_mode == "browse":
            bv = self._find_browse_view()
            if bv:
                bv.action_focus_preview()
        elif self.current_mode == "edit":
            ev = self._find_edit_view()
            if ev:
                ev.action_focus_editor()

    def action_arrow_pageup(self) -> None:
        # In stats mode, page through the report.
        if self.current_mode == "stats":
            try:
                self.query_one("#main-area VerticalScroll").scroll_page_up()
            except Exception:
                pass
            return
        # In other modes TextArea/browse own the key — no-op.

    def action_arrow_pagedown(self) -> None:
        if self.current_mode == "stats":
            try:
                self.query_one("#main-area VerticalScroll").scroll_page_down()
            except Exception:
                pass
            return

    def action_arrow_home(self) -> None:
        if self.current_mode == "stats":
            try:
                self.query_one("#main-area VerticalScroll").scroll_home()
            except Exception:
                pass
            return

    def action_arrow_end(self) -> None:
        if self.current_mode == "stats":
            try:
                self.query_one("#main-area VerticalScroll").scroll_end()
            except Exception:
                pass
            return

    # ── 顶部 status bar ──────────────────────────────────────

    def render_mode(self) -> None:
        indicator = self.query_one("#mode-indicator", Static)
        m = self.current_mode
        label = self.MODE_LABELS[m]
        glyph = self.MODE_GLYPH[m]
        now = datetime.now().strftime("%H:%M")
        # Minimal top line: just the current mode + folder + time.
        # (No more mode pills — user requested they be removed.)
        indicator.update(
            f"  [bold {AMBER}]{glyph} {label}[/]   "
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
        elif self.current_mode == "edit":
            # Edit mode: list + TextArea, keyboard-native.
            self.refresh_entries()
            main.mount(EditView(self))
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

    # ── 3 报表 (stats renderer) ──────────────────────────

    def render_stats(self, target: Static) -> None:
        self.refresh_entries()
        report = stats_mod.compute(self.entries)
        lines: list[str] = []

        # ── Title block
        # Big amber title, then a one-line subtitle with the headline metrics,
        # then the folder path. Visual hierarchy: title > subtitle > path.
        lines.append(f"  [bold {AMBER}]{STAR}  数据报表[/]")
        subtitle_bits = [
            f"[{AMBER}]{report.total_entries} 篇[/]",
            f"[{AMBER}]{report.total_words:,} 字[/]",
        ]
        if report.date_range:
            days = (report.date_range[1] - report.date_range[0]).days + 1
            subtitle_bits.append(f"[{AMBER}]{days} 天[/]")
        lines.append("     " + " [dim]·[/] ".join(subtitle_bits))
        lines.append(f"     [dim]{self.folder}[/]")
        lines.append("")

        if not report.total_entries:
            lines.append("  [dim]还没有日记，没有数据可统计。[/]")
            target.update("\n".join(lines))
            return

        # ── 概览
        lines.append(self._section_header("概览"))
        lines.append("")
        if report.date_range:
            lines.append("     " + self._stat_row(
                "日期范围", f"{report.date_range[0]} → {report.date_range[1]}"))
        lines.append("     " + self._stat_row("总字数", f"{report.total_words:,}"))
        lines.append("     " + self._stat_row("总字符", f"{report.total_characters:,}"))
        lines.append("     " + self._stat_row("平均字数", f"{report.average_words_per_entry:.0f} 字/篇"))
        lines.append("     " + self._stat_row(
            "Streak", f"{report.current_streak_days} 天  (最长 {report.longest_streak_days} 天)"))
        lines.append("")

        # ── 心情分布
        if report.mood_distribution:
            lines.append(self._section_header("心情分布", sub="(1=最差, 5=最好)"))
            lines.append("")
            lines.append(self._bar_chart_mood(report.mood_distribution))
            lines.append("")

        # ── 月度字数
        if report.monthly_trend:
            lines.append(self._section_header("月度字数", sub="(最近 6 个月)"))
            lines.append("")
            lines.append(self._bar_chart_monthly(report.monthly_trend))
            lines.append("")

        # ── Tag 频率 Top 10
        if report.top_tags:
            lines.append(self._section_header("Tag 频率 Top 10"))
            lines.append("")
            for tc in report.top_tags[:10]:
                tag_bar = bar(tc.count, report.top_tags[0].count, width=20)
                lines.append(
                    f"     [{AMBER}]#{tc.tag:<8}[/]  "
                    f"[{AMBER_SOFT}]{tag_bar}[/]  "
                    f"[dim]{tc.count}[/]"
                )
            lines.append("")

        # ── 词云
        if report.word_cloud:
            lines.append(self._section_header("词云", sub="(Top 30 · CJK + Latin)"))
            lines.append("")
            lines.append(self._word_cloud_render(report.word_cloud))

        target.update("\n".join(lines))

    @staticmethod
    def _section_header(title: str, sub: str = "") -> str:
        """Render a section heading: '▎ Title' + '─────' rule on the next line.

        Returns the single string to append (caller adds its own blank line
        below for breathing room).
        """
        if sub:
            return f"  [bold {AMBER}]▎ {title}[/]  [dim]{sub}[/]\n  [dim]─────[/]"
        return f"  [bold {AMBER}]▎ {title}[/]\n  [dim]─────[/]"

    @staticmethod
    def _stat_row(label: str, value: str) -> str:
        """Format a single overview row: label left-padded to 8 visual cells,
        then 2-cell gap, then value.

        Handles CJK labels (each CJK char = 2 visual cells).
        """
        lw = visual_width(label)
        pad = max(2, 8 - lw)  # 2..8 cells of padding
        return f"{label}{' ' * pad}  {value}"

    # ── Bar chart helpers ──────────────────────────────────────

    def _bar_chart_mood(self, buckets) -> str:
        """Render a horizontal bar chart for mood distribution.

        5 fixed rows (1..5). 8-step unicode bars over a 20-cell track.
        """
        max_count = max(b.count for b in buckets) if buckets else 1
        by_score = {b.score: b.count for b in buckets}
        lines: list[str] = []
        for score in range(1, 6):
            count = by_score.get(score, 0)
            b = bar(count, max_count, width=20)
            label = ["很差", "差", "一般", "好", "很好"][score - 1]
            lines.append(
                f"     [{AMBER}]{score} {label:<4}[/]  "
                f"[{AMBER_SOFT}]{b}[/]  [dim]{count}[/]"
            )
        return "\n".join(lines)

    def _bar_chart_monthly(self, points) -> str:
        """Render monthly word-count trend.

        Bar width 20 (8-step precision). The right-side stat column is
        right-padded to a stable width so the numbers line up.
        """
        max_words = max(p.word_count for p in points) if points else 1
        lines: list[str] = []
        for p in points:
            b = bar(p.word_count, max_words, width=20)
            lines.append(
                f"     [{AMBER}]{p.label:<6}[/]  "
                f"[{AMBER_SOFT}]{b}[/]  "
                f"[dim]{p.word_count:>5,} 字  {DOT}  {p.entry_count} 篇[/]"
            )
        return "\n".join(lines)

    def _word_cloud_render(self, words: list[tuple[str, int]]) -> str:
        """Render the word cloud as a wrapped horizontal flow.

        Words are styled by frequency (4 bands: bold amber / amber /
        amber-soft / dim) and laid out as a single flow separated by
        double spaces, wrapped to ~110 visual cells per line.
        """
        if not words:
            return ""
        max_count = words[0][1]
        styled: list[str] = []
        for word, count in words:
            if count >= max_count * 0.5:
                style = f"[bold {AMBER}]"
            elif count >= max_count * 0.25:
                style = f"[{AMBER}]"
            elif count >= max_count * 0.1:
                style = f"[{AMBER_SOFT}]"
            else:
                style = f"[dim]"
            styled.append(f"{style}{word}[/]")

        # Wrap the flow to ~110 visual cells per line. We measure
        # rendered (tag-stripped) width; tags themselves are zero-width.
        sep = "  "
        out: list[str] = []
        cur = ""
        for piece in styled:
            candidate = (cur + sep + piece) if cur else piece
            if visual_width(candidate) > 110 and cur:
                out.append("     " + cur)
                cur = piece
            else:
                cur = candidate
        if cur:
            out.append("     " + cur)
        return "\n".join(out)


# ── Entry point ───────────────────────────────────────────────

def main() -> None:
    app = ShiGuangApp()
    app.run()
