"""HomeView — the centered home screen (v0.2 default mode).

Layout, top to bottom:
  - The GLOW wordmark (figlet banner3, 7 rows × 42 cols)
  - 拾  光 title
  - AfterGlow · v{__version__} subtitle
  - 3 menu lines, with ▸ cursor on the selected one
  - Folder path dim line (the only footer; no key hints — the
    global Footer widget already shows `? q` and the top status
    bar already shows the folder + clock)

Keyboard-only navigation (no mouse, no clickable buttons):
  - `1` / `2` / `3` for direct menu selection
  - `↑` / `↓` (or `j` / `k`) to move the cursor between items
  - `Enter` / `→` / `l` to enter the highlighted item
  - `?` for help, `q` to quit

MENU_ITEMS is the single source of truth for the 3 modes
displayed on the home screen. Adding a 4th mode here is the only
change needed (plus a corresponding BINDINGS key in app.py).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from . import __version__
from .logo import render_home_header
from .theme import AMBER, AMBER_SOFT


class HomeView(Vertical):
    """The centered home screen: GLOW wordmark + 3 menu lines."""

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
        content-align: center middle;
        width: 100%;
        height: 9;
    }}
    #title {{
        align: center middle;
        content-align: center middle;
        width: 100%;
        height: 1;
        margin-top: 1;
    }}
    #subtitle {{
        align: center middle;
        content-align: center middle;
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }}
    #menu {{
        align: center middle;
        content-align: center middle;
        width: 100%;
        height: auto;
    }}
    #footer-hint {{
        align: center middle;
        content-align: center middle;
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

    def __init__(self, app) -> None:
        super().__init__(id="home-screen")
        self._app_ref = app

    def compose(self) -> ComposeResult:
        with Vertical(id="home-stack"):
            # Giant GLOW wordmark
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
            # Footer path (only the diary folder, no key hint —
            # keep the home screen clean; the top bar already
            # shows the folder and the Footer widget lists ? q).
            yield Static(
                f"[dim]  {self._app_ref.folder}[/]",
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
