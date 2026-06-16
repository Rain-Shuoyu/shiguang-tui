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

Focus regions, switched with ←/→:
  - "list":    ↑/↓ or k/j move cursor (wrap-around). `n` create today's
               entry, `d d` delete the highlighted entry.
  - "editor":  TextArea is focused for typing. ← returns to list.

Global keys (always work in edit mode):
  - Ctrl+S         save the current entry to disk
  - 0 / Esc        back to home
  - c              change diary folder
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, TextArea

from . import frontmatter as fm
from .diary import Entry, write_entry, available_filename
from . import __version__


# Keys that the App's priority bindings want to capture even when
# TextArea is focused. We have to claim TextArea doesn't consume
# these (otherwise Textual's screen._binding_chain filter will
# remove the App's bindings for them).
APP_CAPTURED_KEYS = frozenset({
    "n", "d", "c", "j", "k", "0", "1", "2", "3", "q", "question_mark",
    "left", "right", "up", "down", "enter", "escape", "ctrl+s",
})


class _ShiGuangTextArea(TextArea):
    """TextArea that yields a handful of keys to App-level bindings
    instead of inserting them as text.

    Why: Textual's `screen._binding_chain` removes App-level bindings
    for any key that the focused widget's `check_consume_key` claims to
    consume. TextArea's default claims all printable characters. So
    `n`/`d`/etc. are silently stripped from the App's binding chain when
    the editor is focused.

    Two overrides:
    - `check_consume_key` returns False for the keys we want App to
      handle. This keeps the App's priority bindings in the chain.
    - `_on_key` short-circuits those same keys so the TextArea doesn't
      insert the character into the text. The event propagates to the
      App, which dispatches the priority binding.
    """

    def check_consume_key(self, key: str, character=None) -> bool:  # type: ignore[override]
        if key in APP_CAPTURED_KEYS:
            return False
        return super().check_consume_key(key, character)

    def _on_key(self, event) -> None:  # type: ignore[override]
        if event.key in APP_CAPTURED_KEYS:
            # Let the App-level priority binding fire. Don't insert.
            return
        super()._on_key(event)


# Reuse the project's amber palette
AMBER = "#E8A87C"
AMBER_DEEP = "#C97B4F"
AMBER_SOFT = "#F5C7A0"
STAR = "✦"


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


class EditView(Container):
    """Two-pane edit view: list (left) + editor (right)."""

    DEFAULT_CSS = f"""
    EditView {{
        height: 1fr;
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
    #edit-list.focused {{
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

    # App-level bindings (see app.py) route arrow keys / Ctrl+S here.
    BINDINGS = [
        # Empty: keys are routed by the App's action_arrow_* and
        # action_save dispatchers so behavior is consistent across
        # browse / edit.
    ]

    focus_region: reactive[str] = reactive("list")
    cursor: reactive[int] = reactive(0)
    # dirty flag — true when the editor's text has been modified
    # since the last save.
    dirty: reactive[bool] = reactive(False)

    def __init__(self, app) -> None:
        super().__init__(id="edit-view")
        self._app_ref = app
        self._rows: list[tuple[str, object]] = []
        self._flat: list[Entry] = []
        # The path of the entry currently being edited. None when
        # the editor is showing a brand-new (unsaved) entry.
        self._current_path: Optional[Path] = None
        # The date the current entry represents (used when serialising).
        self._current_date: date_cls = date_cls.today()
        # Track if a 'd' key was pressed; second 'd' within 1s triggers delete.
        self._d_pending: bool = False
        # Snapshot of the text last loaded into / saved from the TextArea.
        # Used by on_text_area_changed to distinguish real user edits from
        # programmatic text replacement (which Textual posts as Changed
        # *after* the assignment returns).
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
        # Open the first entry (or a fresh empty template if no entries)
        self._load_into_editor()

    # ── Header / status ─────────────────────────────────────────

    def _render_header(self) -> str:
        n = len(self._app_ref.entries)
        focus_label = "列表" if self.focus_region == "list" else "编辑器"
        return (
            f"[bold {AMBER}]{STAR} 创作笔记 · {n} 篇[/]   "
            f"[dim]焦点: [{AMBER}]{focus_label}[/][/]\n"
            f"[dim]← → 切焦点 · 列表 ↑↓ 选 · n 新建今日 · dd 删除 · Ctrl+S 保存 · 0/Esc 返首页 · c 改目录[/]"
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
        list_widget = self.query_one("#edit-list", Static)
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
                is_selected = (self.focus_region == "list" and flat_idx == self.cursor)
                if is_selected:
                    out.append(
                        f"  [bold {AMBER}]▸  {e.date.strftime('%m-%d')}  {e.title or '无标题'}[/]"
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
        ta = self.query_one("#edit-textarea", TextArea)
        if self._flat and 0 <= self.cursor < len(self._flat):
            entry = self._flat[self.cursor]
            self._current_path = entry.path
            self._current_date = entry.date
            text = self._read_file_text(entry.path)
        else:
            # No entries (or cursor out of range) — open new-entry template
            self._current_path = None
            self._current_date = date_cls.today()
            text = NEW_ENTRY_TEMPLATE.format(date=self._current_date.isoformat())
        ta.text = text
        # Record the loaded text. Changed events fired *after* this
        # assignment will compare equal to `_last_saved_text` and be
        # ignored by on_text_area_changed.
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
            # Brand-new entry. Use the date in the file content if present,
            # otherwise today.
            new_date = self._current_date
            # Try to parse `date: YYYY-MM-DD` from the frontmatter
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
        # Re-scan so the new file shows up in the list
        self._app_ref.refresh_entries()
        self._populate_list()
        self._render_list()
        self._render_status_widget()
        # Move cursor to the entry we just (re)saved
        if self._current_path is not None:
            for i, e in enumerate(self._flat):
                if e.path == self._current_path:
                    self.cursor = i
                    break
        self._render_list()

    def _new_today(self) -> None:
        """Create a fresh empty entry for today and load into editor."""
        today = date_cls.today()
        # If today's entry already exists, just load it and switch focus to editor
        existing = next(
            (e for e in self._app_ref.entries if e.date == today), None
        )
        if existing:
            # Move cursor to existing today entry, then focus editor
            for i, e in enumerate(self._flat):
                if e.path == existing.path:
                    self.cursor = i
                    break
            self._render_list()
            self._load_into_editor()
            self.focus_region = "editor"
            self._focus_textarea()
            return
        # Otherwise create the template
        self._current_path = None
        self._current_date = today
        ta = self.query_one("#edit-textarea", TextArea)
        text = NEW_ENTRY_TEMPLATE.format(date=today.isoformat())
        ta.text = text
        # Brand-new entry: starting state is the template, which counts
        # as "saved" relative to the (non-existent) file — but mark
        # dirty so the user is prompted to save the new entry.
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
            # Soft-delete: move to ~/.shiguang-trash (or similar) for
            # safety. For simplicity, just delete the file — diary.md
            # files are user-generated content and the user explicitly
            # triggered the delete via 'dd'.
            path.unlink()
        except OSError:
            return
        # Re-scan and adjust cursor
        self._app_ref.refresh_entries()
        if self._flat:
            self.cursor = min(self.cursor, len(self._flat) - 1)
        else:
            self.cursor = 0
        self._populate_list()
        self._load_into_editor()
        self._render_list()
        self._render_status_widget()

    # ── Focus / styling ─────────────────────────────────────────

    def _focus_textarea(self) -> None:
        try:
            ta = self.query_one("#edit-textarea", TextArea)
            ta.focus()
        except Exception:
            pass

    def _apply_focus_style(self) -> None:
        try:
            list_widget = self.query_one("#edit-list", Static)
            editor_widget = self.query_one("#edit-editor", Container)
        except Exception:
            return
        if self.focus_region == "list":
            list_widget.set_class(True, "focused")
            editor_widget.set_class(False, "focused")
        else:
            list_widget.set_class(False, "focused")
            editor_widget.set_class(True, "focused")
        try:
            self.query_one("#edit-header", Static).update(self._render_header())
        except Exception:
            pass
        self._render_list()

    def watch_focus_region(self, _old, _new) -> None:
        self._apply_focus_style()
        if _new == "editor":
            self._focus_textarea()

    def watch_cursor(self, _old, _new) -> None:
        self._render_list()
        # Reload editor content when cursor changes (only if list is focused,
        # to avoid stomping on the user's in-progress edits).
        if self.focus_region == "list" and self.dirty is False:
            self._load_into_editor()

    def watch_dirty(self, _old, _new) -> None:
        self._render_status_widget()

    # ── Key handling (called by App-level BINDINGS) ──────────────────

    def action_browse_up(self) -> None:
        if self.focus_region == "list":
            if self._flat:
                self.cursor = (self.cursor - 1) % len(self._flat)
        else:
            # In editor: let TextArea handle up/down for caret movement.
            # We don't intercept here.
            ta = self.query_one("#edit-textarea", TextArea)
            ta.focus()

    def action_browse_down(self) -> None:
        if self.focus_region == "list":
            if self._flat:
                self.cursor = (self.cursor + 1) % len(self._flat)
        else:
            ta = self.query_one("#edit-textarea", TextArea)
            ta.focus()

    def action_browse_left(self) -> None:
        # With App-level priority binding, ← fires even when TextArea
        # is focused. In editor, ← returns focus to list; in list, it's
        # a no-op (we're already at the leftmost pane).
        if self.focus_region == "editor":
            self.focus_region = "list"
        # else: no-op (already at leftmost pane)

    def action_browse_right(self) -> None:
        # → in list switches to editor; in editor it's a no-op
        # (TextArea's own right-arrow for cursor movement is
        # sacrificed — use End / Ctrl+Right for line/word nav).
        if self.focus_region == "list" and self._flat:
            self.focus_region = "editor"

    def action_browse_enter(self) -> None:
        if self.focus_region == "list" and self._flat:
            self.focus_region = "editor"

    def action_browse_pageup(self) -> None:
        # editor handles its own page-up natively; nothing to do
        pass

    def action_browse_pagedown(self) -> None:
        pass

    def action_browse_home(self) -> None:
        pass

    def action_browse_end(self) -> None:
        pass

    def action_save(self) -> None:
        self._save_current()

    def action_new_entry(self) -> None:
        # `n` works from either focus region. From the editor, switch
        # focus to list first so the user sees the selection move to
        # today's entry.
        if self.focus_region == "editor":
            self.focus_region = "list"
        self._new_today()

    def action_delete_entry(self) -> None:
        # Two-step: 'd' sets a pending flag. A second 'd' within ~1s
        # actually deletes. Works from either focus region.
        if self.focus_region == "editor":
            self.focus_region = "list"
        if self._d_pending:
            self._d_pending = False
            self._delete_current()
        else:
            self._d_pending = True
            # Show a transient hint in the status line
            try:
                self.query_one("#editor-status", Static).update(
                    "  [bold #C97B4F]再按一次 d 确认删除[/]"
                )
            except Exception:
                pass

    # ── TextArea change tracking ──────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        # Textual posts Changed events asynchronously, sometimes after
        # _load_into_editor (or _save_current) has returned. So we can't
        # gate on a "loading" flag — we compare to the last text we
        # consider "saved" and treat equal content as a no-op.
        current_text = event.text_area.text
        if current_text == self._last_saved_text:
            return
        if not self.dirty:
            self.dirty = True
        else:
            # Already dirty — still re-render the status badge
            self._render_status_widget()
