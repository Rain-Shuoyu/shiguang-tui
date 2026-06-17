"""Modal screens: HelpScreen and ChangeFolderScreen.

Both are small, single-purpose popups. HelpScreen is registered
as an app Screen (push via `app.push_screen("help")`); ChangeFolderScreen
is a ModalScreen pushed from any mode via `app.push_screen(ChangeFolderScreen(app))`.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Static

from .config import save_state, state_file
from .theme import AMBER, AMBER_DEEP, AMBER_SOFT, STAR

if TYPE_CHECKING:
    from .app import ShiGuangApp


# ── HelpScreen ─────────────────────────────────────────────────

class HelpScreen(Screen):
    """The '?' help overlay: shows the 4 modes + common keys."""

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
            f"  [bold]0[/] 首页   [dim]—[/]  [bold {AMBER}]默认视图[/]  概览 + 最近 5 篇 + 快捷操作\n"
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


# ── ChangeFolderScreen ─────────────────────────────────────────

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
