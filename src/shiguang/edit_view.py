"""EditView — the '创作笔记' (edit) mode.

Two-pane layout, vim-style keyboard navigation, no click / no Tab:

  ┌─ list ─────────┬─ editor ────────────────┐
  │  2026-06       │ 2026-06-16.md  (saved)  │
  │ ▸ 06-16 ...    │ ── frontmatter ──       │
  │   06-06 ...    │ title: ...              │
  │  2026-05       │ mood: 4                 │
  │   ...          │ ── body ──              │
  │                │ <TextArea with full MD> │
  └────────────────┴─────────────────────────┘

Focus model — TWO independent focusable widgets, switched by blur/focus:

  list focus    EditView itself is focused. EditView's BINDINGS handle
                command keys: n/d/c/0/?/q/Enter/Ctrl+S. TextArea is
                blurred, so user can navigate the list with ↑/↓/j/k.
                → Enter / double-tap → / double-tap ← ... etc.

  editor focus  TextArea is focused. TextArea handles all keys as
                normal text input. EditView's BINDINGS are inactive
                because EditView is not the focused widget. User can
                type any character including c, d, n, 0-3, q, ?.

Focus switch rules:
  list → editor:  single →, Enter
  editor → list:  double-tap ←, double-tap →, 0/Esc, c (change folder)
                  (these keys only fire in list focus, but 0/Esc
                  also fire from the App level on Esc)

Inside editor (TextArea focused), ↑/↓/←/→ are normal caret movement.

Inside list (EditView focused), ↑/↓/j/k move the list cursor. The
EditView's BINDINGS only fire when EditView is the focused widget.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.reactive import reactive
from textual.widgets import Static, TextArea

from . import frontmatter as fm
from .diary import Entry, write_entry, available_filename
from . import __version__
from .theme import AMBER, AMBER_DEEP, AMBER_SOFT, STAR


# Template for a brand-new entry. The user edits this in the TextArea.
NEW_ENTRY_TEMPLATE = """---
title: ""
date: {date}
mood:
weather: ""
tags: []
---

# {date}

"""


class _ShiGuangTextArea(TextArea):
    """Plain TextArea. No key overrides — all keys are processed as text
    when this widget is focused. Caret movement (↑/↓/←/→) works natively.
    """

    # No check_consume_key override. No _on_key override. Just TextArea.
    pass


class EditView(Container):
    """Two-pane edit view: list (left) + editor (right).

    Focusable: when this Container is the focused widget, the BINDINGS
    below fire. When the TextArea inside is focused, the BINDINGS are
    inactive and TextArea handles all key events as text input.
    """

    DEFAULT_CSS = f"""
    EditView {{
        height: 1fr;
    }}
    EditView:focus {{
        # leave default — no visual change for list focus
    }}
    #edit-header {{
        height: 3;
        padding: 0 1;
    }}
    #edit-body {{
        height: 1fr;
    }}
    #edit-list {{
        width: 40%;
        min-width: 24;
        height: 1fr;
        padding: 0 1;
        border: round {AMBER_DEEP};
        background: #14110F;
    }}
    EditView:focus #edit-list {{
        border: round {AMBER};
    }}
    #edit-editor {{
        width: 1fr;
        height: 1fr;
        border: round {AMBER_DEEP};
        background: #14110F;
    }}
    #edit-editor.focused {{
        border: round {AMBER};
    }}
    #editor-status {{
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: #1F1A16;
        color: {AMBER_SOFT};
    }}
    TextArea {{
        height: 1fr;
    }}
    """

    # No EditView BINDINGS. All command keys are at the App level
    # (see app.py BINDINGS). They are non-priority, so they get
    # filtered by TextArea's check_consume_key when the editor is
    # focused (TextArea handles them as text input). In list focus
    # (EditView focused, default check_consume_key returns False),
    # the App's binding fires and the action handler routes to
    # EditView's action_* methods.
    BINDINGS = []

    can_focus = True

    focus_region: reactive[str] = reactive("list")
    cursor: reactive[int] = reactive(0)
    dirty: reactive[bool] = reactive(False)

    def __init__(self, app) -> None:
        super().__init__(id="edit-view")
        self._app_ref = app
        self._rows: list[tuple[str, object]] = []
        self._flat: list[Entry] = []
        self._current_path: Optional[Path] = None
        self._current_date: date_cls = date_cls.today()
        self._d_pending: bool = False
        self._d_pending_ts: float = 0.0
        self._n_pending: bool = False
        self._n_pending_ts: float = 0.0
        self._N_PENDING_MS = 1500
        self._DOUBLE_TAP_MS = 350
        self._last_left_ts: float = 0.0
        self._last_right_ts: float = 0.0
        self._last_saved_text: str = ""

    # ── Compose ─────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._render_header(), id="edit-header")
        with Horizontal(id="edit-body"):
            yield Static("", id="edit-list")
            with Container(id="edit-editor"):
                yield _ShiGuangTextArea.code_editor(
                    "",
                    language=None,
                    id="edit-textarea",
                )
                yield Static(self._render_status(), id="editor-status")

    def on_mount(self) -> None:
        self._populate_list()
        self._apply_focus_style()
        # Load first entry into editor but DON'T focus the textarea —
        # start in list focus so user can navigate the list immediately.
        self._load_into_editor()
        # Default focus is the EditView itself (list focus)
        self.focus()

    def on_descendant_focus(self, descendant) -> None:
        """When focus moves to a descendant (e.g. the TextArea), update
        our focus_region accordingly. Triggered by:
        - User pressing → or Enter in list focus (we focus the TextArea).
        - User clicking on the TextArea.
        """
        if isinstance(descendant, _ShiGuangTextArea):
            if self.focus_region != "editor":
                self.focus_region = "editor"

    def on_focus(self) -> None:
        """When EditView itself gains focus (e.g. user pressed Esc
        in editor, which moves focus to the next focusable widget),
        switch to list focus.
        """
        if self.focus_region == "editor":
            self.focus_region = "list"

    def on_blur(self) -> None:
        """When EditView itself loses focus (e.g. user navigates away
        via Tab, opens a modal, etc.), don't change focus_region —
        let the modal/state handle it. The actual focus change is
        driven by descendant_focus events or explicit user action.
        """
        pass

    # ── Focus / styling ─────────────────────────────────────────

    def _apply_focus_style(self) -> None:
        try:
            editor_widget = self.query_one("#edit-editor", Container)
        except Exception:
            return
        if self.focus_region == "list":
            editor_widget.set_class(False, "focused")
        else:
            editor_widget.set_class(True, "focused")
        try:
            self.query_one("#edit-header", Static).update(self._render_header())
        except Exception:
            pass
        self._render_list()

    def _focus_textarea(self) -> None:
        try:
            ta = self.query_one("#edit-textarea", TextArea)
            ta.focus()
        except Exception:
            pass

    def _focus_self(self) -> None:
        # EditView is a Container; setting focus on it makes its
        # BINDINGS active and keys stop reaching the TextArea.
        self.focus()

    def watch_focus_region(self, _old, _new) -> None:
        self._apply_focus_style()
        if _new == "editor":
            self._focus_textarea()
        else:
            self._focus_self()

    def watch_cursor(self, _old, _new) -> None:
        # Cursor moved to a different entry — clear any pending
        # n/d confirmation (they were for the previous entry).
        if _old != _new:
            self._n_pending = False
            self._n_pending_ts = 0.0
            self._d_pending = False
            self._d_pending_ts = 0.0
        self._render_list()
        if self.focus_region == "list" and self.dirty is False:
            self._load_into_editor()

    def watch_dirty(self, _old, _new) -> None:
        self._render_status_widget()

    # ── Header / status ─────────────────────────────────────────

    def _render_header(self) -> str:
        n = len(self._app_ref.entries)
        focus_label = "列表" if self.focus_region == "list" else "编辑器"
        if self.focus_region == "list":
            hint = (
                "↑/↓ j/k 选 · → Enter 进入编辑器 · "
                "n 新建 · dd 删除 · Ctrl+S 保存 · c 改目录 · "
                "? 帮助 · q 退出 · 0 返首页"
            )
        else:
            # In editor focus, only Esc can exit (returns to list);
            # from there press 0 to go home. Letter/digit keys
            # must be free for typing.
            hint = (
                "编辑器内自由输入 · "
                "Esc 回列表 · c 改目录 · "
                "保存请先回列表再 Ctrl+S"
            )
        return (
            f"[bold {AMBER}]{STAR} 创作笔记 · {n} 篇[/]   "
            f"[dim]焦点: [{AMBER}]{focus_label}[/][/]\n"
            f"[dim]{hint}[/]"
        )

    def _render_status(self) -> str:
        if self._current_path is None:
            target_name = f"{self._current_date.isoformat()}.md"
            mode = "[bold #C97B4F]新文件(未保存)[/]"
        else:
            target_name = self._current_path.name
            mode = "[dim]已保存[/]" if not self.dirty else "[bold #C97B4F]● 未保存[/]"
        return f"  {mode}  [dim]·[/]  {target_name}"

    # ── List population ─────────────────────────────────────────

    def _populate_list(self) -> None:
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
        if self._flat:
            self.cursor = max(0, min(self.cursor, len(self._flat) - 1))
        else:
            self.cursor = 0
        self._render_list()

    def _entry_label(self, e: Entry) -> str:
        title = e.title or "无标题"
        mood_badge = ""
        if e.frontmatter.mood is not None:
            mood_badge = f" [dim]m{e.frontmatter.mood}[/]"
        return f"  [bold {AMBER_SOFT}]{e.date.strftime('%m-%d')}[/]  {title[:28]}{mood_badge}"

    def _render_list(self) -> str:
        try:
            list_widget = self.query_one("#edit-list", Static)
        except Exception:
            return ""
        if not self._flat:
            list_widget.update(
                "[dim]还没有日记。按 n 新建今天的。[/]"
            )
            return
        flat_idx = 0
        out: list[str] = []
        for kind, payload in self._rows:
            if kind == "header":
                out.append(f"  [bold {AMBER_SOFT}]{payload}[/]")
            else:
                e = payload  # type: ignore[assignment]
                is_focus_cursor = (self.focus_region == "list" and flat_idx == self.cursor)
                is_loaded = (self.focus_region == "editor" and flat_idx == self.cursor)
                if is_focus_cursor:
                    out.append(
                        f"  [bold {AMBER}]▸  {e.date.strftime('%m-%d')}  {e.title or '无标题'}[/]"
                    )
                elif is_loaded:
                    out.append(
                        f"  [dim]▸  {e.date.strftime('%m-%d')}  {e.title or '无标题'}[/]"
                    )
                else:
                    out.append(f"    {self._entry_label(e)}")
                flat_idx += 1
        return list_widget.update("\n".join(out))

    # ── Editor loading ─────────────────────────────────────────

    def _read_file_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _load_into_editor(self) -> None:
        """Load the file for `self.cursor` into the TextArea.

        Note: this does NOT clear `_n_pending` — the new-entry flow
        may need `_load_into_editor` to show today's existing content
        while the second-n confirm is still pending. Callers that
        genuinely switch to a different entry should clear
        `_n_pending` themselves (e.g. `watch_cursor` does this).
        """
        ta = self.query_one("#edit-textarea", TextArea)
        if self._flat and 0 <= self.cursor < len(self._flat):
            entry = self._flat[self.cursor]
            self._current_path = entry.path
            self._current_date = entry.date
            text = self._read_file_text(entry.path)
        else:
            self._current_path = None
            self._current_date = date_cls.today()
            text = NEW_ENTRY_TEMPLATE.format(date=self._current_date.isoformat())
        ta.text = text
        self._last_saved_text = text
        self.dirty = False
        self._render_status_widget()

    def _render_status_widget(self) -> None:
        try:
            self.query_one("#editor-status", Static).update(self._render_status())
        except Exception:
            pass

    # ── Save / new / delete ─────────────────────────────────────────

    def _save_current(self) -> None:
        ta = self.query_one("#edit-textarea", TextArea)
        text = ta.text
        if self._current_path is None:
            new_date = self._current_date
            parsed_fm, body = fm.parse(text)
            if parsed_fm.date:
                try:
                    new_date = date_cls.fromisoformat(parsed_fm.date)
                except ValueError:
                    pass
            self._current_date = new_date
            target = self._app_ref.folder / available_filename(new_date, self._app_ref.folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            self._current_path = target
        else:
            self._current_path.write_text(text, encoding="utf-8")
        self._last_saved_text = text
        self.dirty = False
        self._app_ref.refresh_entries()
        self._populate_list()
        self._render_list()
        self._render_status_widget()
        if self._current_path is not None:
            for i, e in enumerate(self._flat):
                if e.path == self._current_path:
                    self.cursor = i
                    break
        self._render_list()

    def _new_today(self) -> None:
        today = date_cls.today()
        existing = next(
            (e for e in self._app_ref.entries if e.date == today), None
        )
        if existing:
            for i, e in enumerate(self._flat):
                if e.path == existing.path:
                    self.cursor = i
                    break
            self._render_list()
            self._load_into_editor()
            self.focus_region = "editor"
            self._focus_textarea()
            return
        self._current_path = None
        self._current_date = today
        ta = self.query_one("#edit-textarea", TextArea)
        text = NEW_ENTRY_TEMPLATE.format(date=today.isoformat())
        ta.text = text
        self._last_saved_text = text
        self.dirty = True
        self._render_status_widget()
        self._render_list()
        self.focus_region = "editor"
        self._focus_textarea()

    def _delete_current(self) -> None:
        if not self._flat:
            return
        if self.cursor < 0 or self.cursor >= len(self._flat):
            return
        entry = self._flat[self.cursor]
        path = entry.path
        try:
            path.unlink()
        except OSError:
            return
        self._app_ref.refresh_entries()
        if self._flat:
            self.cursor = min(self.cursor, len(self._flat) - 1)
        else:
            self.cursor = 0
        self._populate_list()
        self._load_into_editor()
        self._render_list()
        self._render_status_widget()

    # ── Actions invoked by EditView BINDINGS (list focus only) ─────────

    def action_new_entry(self) -> None:
        """`n` — create / jump to today's entry.

        Called from EditView BINDINGS, so EditView must be focused
        (i.e. list focus). Today's entry handling:
        - Doesn't exist → create template, jump to editor.
        - Exists, first n → move cursor to today, show choice hint,
          stay in list focus.
        - Exists, second n within 1.5s → wipe to template, jump to
          editor.
        """
        now = time.monotonic()
        if self._n_pending and (now - self._n_pending_ts) * 1000 > self._N_PENDING_MS:
            self._n_pending = False
        today = date_cls.today()
        existing = next(
            (e for e in self._app_ref.entries if e.date == today), None
        )
        if existing is None:
            self._n_pending = False
            self._n_pending_ts = 0.0
            self._new_today()
            return
        # Today's entry exists — move cursor to it.
        for i, e in enumerate(self._flat):
            if e.path == existing.path:
                self.cursor = i
                break
        self._render_list()
        if not self._n_pending:
            self._n_pending = True
            self._n_pending_ts = now
            self._load_into_editor()
            try:
                self.query_one("#editor-status", Static).update(
                    "  [bold #C97B4F]今日已有 · "
                    "[N 再按一次] 覆盖  [→] 进入编辑  [0] 取消[/]"
                )
            except Exception:
                pass
            return
        # Second press within window: overwrite.
        self._n_pending = False
        self._n_pending_ts = 0.0
        self._current_path = None
        self._current_date = today
        ta = self.query_one("#edit-textarea", TextArea)
        text = NEW_ENTRY_TEMPLATE.format(date=today.isoformat())
        ta.text = text
        self._last_saved_text = text
        self.dirty = True
        self._render_status_widget()
        self._render_list()
        self.focus_region = "editor"
        self._focus_textarea()

    def action_delete_entry(self) -> None:
        """`d` — two-step delete (works in list focus)."""
        now = time.monotonic()
        if self._d_pending and (now - self._d_pending_ts) * 1000 > 1000:
            self._d_pending = False
        if self._d_pending:
            self._d_pending = False
            self._delete_current()
        else:
            self._d_pending = True
            self._d_pending_ts = now
            try:
                self.query_one("#editor-status", Static).update(
                    "  [bold #C97B4F]再按一次 d 确认删除[/]"
                )
            except Exception:
                pass

    def action_change_folder(self) -> None:
        """`c` — open change-folder modal. List focus only."""
        # Push the screen on the App, not on EditView.
        self._app_ref.action_change_folder()

    def action_go_home(self) -> None:
        """`0` — return to home. List focus only.

        Also the user can press Esc from the App level; both routes
        land on action_go_home_or_back which goes home if no modal
        is on top.
        """
        # Clear pending-N/D state to avoid stale confirmations later.
        self._n_pending = False
        self._n_pending_ts = 0.0
        self._d_pending = False
        self._d_pending_ts = 0.0
        if self._app_ref.current_mode != "home":
            self._app_ref.current_mode = "home"
            self._app_ref.render_mode()

    def action_help(self) -> None:
        self._app_ref.action_help()

    def action_quit(self) -> None:
        self._app_ref.exit()

    def action_save(self) -> None:
        """Ctrl+S — save current entry. List focus only."""
        self._save_current()

    def action_focus_editor(self) -> None:
        """→ or Enter — switch to editor focus.

        In list focus, single → or Enter should switch to editor.
        Note: there's no double-tap detection here — single press is
        the explicit gesture. (Double-tap detection was for ←/→ in
        editor focus, which we no longer need because ↑/↓/←/→
        are always passed through to the focused widget.)
        """
        if self.focus_region == "list" and self._flat:
            self.focus_region = "editor"

    # ── List navigation (works in list focus only) ─────────

    def action_cursor_up(self) -> None:
        if self._flat:
            self.cursor = (self.cursor - 1) % len(self._flat)

    def action_cursor_down(self) -> None:
        if self._flat:
            self.cursor = (self.cursor + 1) % len(self._flat)

    def action_cursor_left(self) -> None:
        # No-op in list focus
        pass

    def action_cursor_right(self) -> None:
        # No-op; use action_focus_editor
        pass

    # ── TextArea change tracking ──────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        current_text = event.text_area.text
        if current_text == self._last_saved_text:
            return
        if not self.dirty:
            self.dirty = True
        else:
            self._render_status_widget()
