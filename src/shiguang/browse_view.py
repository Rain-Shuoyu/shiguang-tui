"""BrowseView — the '洞察 / 记录' (browse) mode.

Two-pane layout:
  ┌─ list ────────┬─ preview ──────────────────┐
  │  2026-06      │ 2026-06-16                 │
  │ ▸ 06-16 ...   │ 今天的天气真好             │
  │   06-06 ...   │                            │
  │  2026-05      │                            │
  │   ...         │                            │
  └───────────────┴────────────────────────────┘

Pure keyboard, vim-style. No mouse / Tab / click.

Two focus regions, switched with Enter / Esc:
  - "list"   (default on mount) — ↑/↓ or k/j move the cursor.
              Enter focuses the preview pane.
  - "preview" — ↑/↓/←/→ (or k/j/h/l) move the caret in the
                read-only TextArea; the pane scrolls automatically
                to keep the caret visible. Esc returns focus to
                the list (handled by `_BrowsePreviewTextArea`'s
                custom _on_key, which calls the BrowseView's
                action_focus_list — TextArea's built-in Esc uses
                focus_next which doesn't reliably land on the
                parent Container).

Global keys (always available in browse mode):
  - 0: back to home
  - c: change diary folder
  - ? / q: help / quit
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Static, TextArea

from .diary import Entry
from .format import strip_markup
from .markup import md_to_markup
from .theme import AMBER, AMBER_DEEP, AMBER_SOFT, STAR


class _BrowsePreviewTextArea(TextArea):
    """A read-only TextArea whose Esc key returns focus to the
    parent BrowseView (instead of calling screen.focus_next, which
    doesn't reliably land on the grandparent Container in this layout).
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.read_only = True

    async def _on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            # Walk up to find the BrowseView and call its action.
            node = self.parent
            while node is not None and not isinstance(node, BrowseView):
                node = node.parent
            if node is not None:
                node.action_focus_list()
            return
        # Defer to the standard TextArea handler for everything else.
        await super()._on_key(event)


class BrowseView(Container):
    """The '洞察 / 记录' (browse) mode widget."""

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
    #preview-textarea {{
        width: 1fr;
        height: 1fr;
        border: round {AMBER_DEEP};
        background: #14110F;
    }}
    #preview-textarea:focus {{
        border: round {AMBER};
    }}
    """

    # Focusable so the Container itself can take focus in list mode.
    can_focus = True

    # All command keys live on the App; BrowseView has none.
    BINDINGS = []

    # Two focus regions. Reactive so we can watch changes and re-style
    # the borders.
    focus_region: reactive[str] = reactive("list")
    # Cursor index into self._flat (skipping month-header rows).
    cursor: reactive[int] = reactive(0)

    def __init__(self, app) -> None:
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
            yield _BrowsePreviewTextArea(
                "",
                id="preview-textarea",
                soft_wrap=True,
            )

    def on_mount(self) -> None:
        self._populate_list()
        # Style initial focus
        self._apply_focus_style()
        # Make sure the list is the initially focused region
        self.focus()

    # ── Focus routing — mirrors EditView's pattern ──────────────

    def _focus_preview(self) -> None:
        """Move focus into the read-only preview TextArea."""
        try:
            ta = self.query_one("#preview-textarea", TextArea)
            ta.focus()
        except Exception:
            pass

    def watch_focus_region(self, _old, _new) -> None:
        """React to focus_region changes by re-styling borders and
        actually moving the focus."""
        self._apply_focus_style()
        if _new == "preview":
            self._focus_preview()
        else:
            # When switching back to list, focus self (the Container)
            # — but only if we're not already in the middle of a
            # focus change driven by Textual's own focus machinery.
            if self.app.focused is not self:
                self.focus()

    def on_focus(self) -> None:
        """When BrowseView itself gains focus (e.g. user pressed Esc
        in the preview, which moves focus via screen.focus_next()),
        switch to list focus."""
        if self.focus_region == "preview":
            self.focus_region = "list"

    def on_descendant_focus(self, descendant) -> None:
        """When the TextArea descendant gains focus, switch to
        preview focus."""
        if isinstance(descendant, _BrowsePreviewTextArea):
            if self.focus_region != "preview":
                self.focus_region = "preview"

    # ── Header / hint line ──────────────────────────────────────

    def _render_header(self) -> str:
        n = len(self._app_ref.entries)
        focus_label = "列表" if self.focus_region == "list" else "预览"
        if self.focus_region == "list":
            hint = (
                "↑/↓ j/k 选 · Enter 进入预览 · "
                "0 返首页 · c 改目录 · ? 帮助"
            )
        else:
            hint = (
                "↑/↓/←/→ h/j/k/l 移动光标 (自动滚动) · "
                "Esc 回列表 · 0 返首页"
            )
        return (
            f"[bold {AMBER}]{STAR} 洞察 · {n} 篇[/]   "
            f"[dim]焦点: [{AMBER}]{focus_label}[/][/]\n"
            f"[dim]{hint}[/]"
        )

    # ── List population ──────────────────────────────────────

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
            list_widget.update("[dim]还没有日记。按 2 进入创作 tab 新建。[/]")
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
                is_loaded = (self.focus_region == "preview" and flat_idx == self.cursor)
                if is_selected:
                    # Bright amber text + ▸ cursor (no reverse block).
                    out.append(f"  [bold {AMBER}]▸  {e.date.strftime('%m-%d')}  {e.title or '无标题'}[/]")
                elif is_loaded:
                    out.append(f"  [dim]▸  {e.date.strftime('%m-%d')}  {e.title or '无标题'}[/]")
                else:
                    out.append(f"    {self._entry_label(e)}")
                flat_idx += 1
        list_widget.update("\n".join(out))

    # ── Preview pane ──────────────────────────────────────

    def _refresh_preview(self) -> None:
        if not self._flat:
            self._set_preview_text("[dim]    选择左侧任一日记条目,这里会显示内容预览。[/]")
            return
        if self.cursor < 0 or self.cursor >= len(self._flat):
            return
        entry = self._flat[self.cursor]
        self._render_preview(entry)
        # Move caret to top of preview when selection changes
        try:
            ta = self.query_one("#preview-textarea", _BrowsePreviewTextArea)
            ta.cursor_location = (0, 0)
        except Exception:
            pass

    def _set_preview_text(self, text: str) -> None:
        try:
            ta = self.query_one("#preview-textarea", _BrowsePreviewTextArea)
            ta.text = text
        except Exception:
            pass

    def _render_preview(self, entry: Entry) -> None:
        # TextArea's `text` is a plain str, but it does support
        # lightweight Rich markup via `text_markup` for syntax-highlight
        # styled lines. For the preview we keep it readable plain
        # text — the cursor needs line/column addressing, which works
        # only on plain text.
        lines: list[str] = []
        lines.append(f"{entry.date.isoformat()}")
        if entry.title:
            lines.append(f"{entry.title}")
            lines.append("─" * max(8, len(entry.title) * 2))
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
            lines.append("  ·  ".join(meta_bits))
        lines.append("")
        try:
            # Strip rich markup from rendered body for plain-text
            # display inside the TextArea.
            rendered_body = md_to_markup(entry.body or "")
            rendered_body = strip_markup(rendered_body)
        except Exception as e:
            rendered_body = f"渲染失败: {e}"
        lines.append(rendered_body)
        self._set_preview_text("\n".join(lines))

    # ── Focus / key handling ──────────────────────────────────────

    def _apply_focus_style(self) -> None:
        """Re-style list / preview borders to indicate which is focused."""
        try:
            list_widget = self.query_one("#browse-list", Static)
            # The preview "pane" is now the TextArea itself. We don't
            # toggle classes on it (TextArea has its own focused style
            # via Textual's default), we just toggle the list class.
        except Exception:
            return
        if self.focus_region == "list":
            list_widget.set_class(True, "focused")
        else:
            list_widget.set_class(False, "focused")
        # Refresh the header label and list selection indicator
        try:
            self.query_one("#browse-header", Static).update(self._render_header())
        except Exception:
            pass
        self._render_list()

    def watch_cursor(self, _old, _new) -> None:
        # Re-render list (cursor moved) and preview
        self._render_list()
        self._refresh_preview()

    # ── Action handlers (called from App-level BINDINGS) ────────
    # In list focus, the Container is focused → App BINDINGS (↑/↓/Enter)
    # fire here. In preview focus, the TextArea is focused → App
    # BINDINGS are filtered out of Textual's binding chain, and the
    # TextArea handles arrows as caret movement natively.

    def action_cursor_up(self) -> None:
        # Only called in list focus (preview is handled by TextArea).
        if self.focus_region == "list" and self._flat:
            self.cursor = (self.cursor - 1) % len(self._flat)

    def action_cursor_down(self) -> None:
        if self.focus_region == "list" and self._flat:
            self.cursor = (self.cursor + 1) % len(self._flat)

    def action_focus_preview(self) -> None:
        """Enter in list focus → move focus to the preview TextArea."""
        if self.focus_region == "list" and self._flat:
            self.focus_region = "preview"

    def action_focus_list(self) -> None:
        """Esc / ← in preview focus → move focus back to the list.
        In practice, Esc is handled by TextArea itself (calls
        screen.focus_next) and our on_focus picks up the change.
        This method exists so an explicit call (e.g. ← in preview
        if we ever want it) can also drive the switch.
        """
        if self.focus_region == "preview":
            self.focus_region = "list"
