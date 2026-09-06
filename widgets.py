"""
Custom-drawn rounded button and dropdown widgets. Plain ttk widgets can't render true
rounded corners, so these are built on tk.Canvas instead -- no extra runtime dependency
(no Pillow needed), so nothing extra to bundle for the .exe.
"""

import time
import tkinter as tk

# After a dropdown popup closes (a selection made, or dismissed by clicking away), button
# clicks are briefly ignored. Without this, selecting a dropdown option can register as a
# click on whatever button happens to be under the cursor immediately afterward, since the
# popup closing changes what's actually under the mouse mid-click.
_CLICK_SUPPRESS_SECONDS = 0.35
_click_suppressed_until = 0.0


def _suppress_clicks(duration=_CLICK_SUPPRESS_SECONDS):
    global _click_suppressed_until
    _click_suppressed_until = time.monotonic() + duration


def _clicks_suppressed():
    return time.monotonic() < _click_suppressed_until


def _round_rect_points(x1, y1, x2, y2, r):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _safe_bg(parent, fallback="#eaf6fd"):
    try:
        return parent.cget("background")
    except Exception:
        try:
            return parent.cget("bg")
        except Exception:
            return fallback


class RoundedButton(tk.Canvas):
    """A pill-shaped button. kind='primary' is the big accent-colored button with a soft
    drop shadow; kind='secondary' is a smaller, flat grey button with no shadow/glow
    (used for Back / Start Over)."""

    def __init__(self, parent, text, command=None, kind="primary", width=190, height=42,
                 font=None, bg=None, state="normal"):
        self.kind = kind
        self.margin = 5 if kind == "primary" else 0
        self.w, self.h = width, height
        total_w = width + self.margin * 2
        total_h = height + self.margin * 2
        bg = bg or _safe_bg(parent)
        super().__init__(parent, width=total_w, height=total_h, bg=bg,
                          highlightthickness=0, bd=0)

        self.command = command
        self.text = text
        self.font = font or ("EB Garamond", 12, "bold")
        self.radius = height // 2
        self._state = state

        if kind == "primary":
            self.c_normal, self.c_hover, self.c_active, self.c_disabled = (
                "#2f8fd1", "#3fa1e8", "#1c6ba3", "#a9c6db")
            self.shadow_color = "#bcd8ec"
        else:
            self.c_normal, self.c_hover, self.c_active, self.c_disabled = (
                "#9099a1", "#a3abb2", "#767d84", "#c6cbcf")
            self.shadow_color = None

        self._render(self._current_color())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._apply_cursor()

    def _current_color(self):
        return self.c_normal if self._state == "normal" else self.c_disabled

    def _apply_cursor(self):
        try:
            self.configure(cursor="hand2" if self._state == "normal" else "arrow")
        except Exception:
            pass

    def _render(self, color):
        self.delete("all")
        x1, y1 = self.margin, self.margin
        x2, y2 = self.margin + self.w, self.margin + self.h
        if self.kind == "primary":
            pts = _round_rect_points(x1 + 2, y1 + 3, x2 + 2, y2 + 3, self.radius)
            self.create_polygon(pts, smooth=True, fill=self.shadow_color, outline="")
        pts = _round_rect_points(x1, y1, x2, y2, self.radius)
        self.create_polygon(pts, smooth=True, fill=color, outline="")
        self.create_text((x1 + x2) // 2, (y1 + y2) // 2, text=self.text,
                          fill="white", font=self.font)

    def _on_enter(self, _e):
        if self._state == "normal":
            self._render(self.c_hover)

    def _on_leave(self, _e):
        if self._state == "normal":
            self._render(self.c_normal)

    def _on_press(self, _e):
        if self._state == "normal":
            self._render(self.c_active)

    def _on_release(self, event):
        if self._state != "normal":
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._render(self.c_hover if inside else self.c_normal)
        if inside and self.command and not _clicks_suppressed():
            self.command()

    def set_state(self, state):
        """state: 'normal' or 'disabled'."""
        self._state = state
        self._apply_cursor()
        self._render(self._current_color())


# ---------------------------------------------------------------------- Dropdown

_open_dropdown = None
_global_bound_roots = set()


def _global_click_handler(event):
    global _open_dropdown
    dd = _open_dropdown
    if dd is None:
        return
    widget = event.widget
    if widget is dd:
        return
    popup = dd.popup
    if popup is not None:
        top = widget
        while top is not None:
            if top == popup:
                return
            top = getattr(top, "master", None)
    dd._close_popup()


class RoundedDropdown(tk.Canvas):
    """A read-only, click-to-select dropdown styled as a white rounded box with a
    colored border, matching the reference look -- selected text left-aligned, a
    chevron on the right, and a rounded white popup list below on click."""

    def __init__(self, parent, values, textvariable, width=220, height=36, font=None,
                 command=None, border_color="#2f8fd1", text_color="#1f6fa8", bg=None):
        bg = bg or _safe_bg(parent)
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.values = list(values)
        self.var = textvariable
        self.width, self.height = width, height
        self.radius = 10
        self.font = font or ("EB Garamond", 11)
        self.command = command
        self.border_color = border_color
        self.text_color = text_color
        self.popup = None

        self._render()
        self.bind("<Button-1>", self._toggle_popup)
        self.configure(cursor="hand2")

        self._trace_id = self.var.trace_add("write", self._on_var_write)
        self.bind("<Destroy>", self._on_destroy)

        root = self.winfo_toplevel()
        if root not in _global_bound_roots:
            root.bind_all("<Button-1>", _global_click_handler, add="+")
            _global_bound_roots.add(root)

    def _on_var_write(self, *_args):
        try:
            self._render()
        except tk.TclError:
            pass

    def _on_destroy(self, _event=None):
        global _open_dropdown
        try:
            self.var.trace_remove("write", self._trace_id)
        except Exception:
            pass
        if _open_dropdown is self:
            _open_dropdown = None
        if self.popup is not None:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None

    def _render(self):
        self.delete("all")
        pts = _round_rect_points(1, 1, self.width - 1, self.height - 1, self.radius)
        self.create_polygon(pts, smooth=True, fill="white", outline=self.border_color, width=2)
        text = self.var.get() or ""
        self.create_text(14, self.height // 2, text=text, fill=self.text_color,
                          font=self.font, anchor="w")
        cx, cy = self.width - 20, self.height // 2
        self.create_line(cx - 5, cy - 3, cx, cy + 3, cx + 5, cy - 3,
                          fill=self.border_color, width=2, capstyle="round", joinstyle="round")

    def _toggle_popup(self, _event=None):
        if self.popup is not None:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        global _open_dropdown
        if not self.values:
            return
        _open_dropdown = self

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.height + 2
        row_h = 30
        pad = 5
        total_h = row_h * len(self.values) + pad * 2

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except Exception:
            pass
        self.popup = popup

        canvas = tk.Canvas(popup, width=self.width, height=total_h,
                            highlightthickness=0, bd=0, bg="white")
        canvas.pack()
        pts = _round_rect_points(1, 1, self.width - 1, total_h - 1, 10)
        canvas.create_polygon(pts, smooth=True, fill="white", outline="#c8d9e6", width=1)

        for i, val in enumerate(self.values):
            ry = pad + i * row_h
            row_rect = canvas.create_rectangle(2, ry, self.width - 2, ry + row_h,
                                                fill="white", outline="")
            row_text = canvas.create_text(14, ry + row_h // 2, text=val, anchor="w",
                                           fill="#3c3d40", font=self.font)

            def on_enter(_e, r=row_rect):
                canvas.itemconfig(r, fill="#eaf6fd")

            def on_leave(_e, r=row_rect):
                canvas.itemconfig(r, fill="white")

            def on_click(_e, v=val):
                self._select(v)

            for item in (row_rect, row_text):
                canvas.tag_bind(item, "<Enter>", on_enter)
                canvas.tag_bind(item, "<Leave>", on_leave)
                canvas.tag_bind(item, "<Button-1>", on_click)

        popup.geometry(f"{self.width}x{total_h}+{x}+{y}")

    def _select(self, value):
        self.var.set(value)
        self._close_popup()
        if self.command:
            self.command()

    def _close_popup(self):
        global _open_dropdown
        if _open_dropdown is self:
            _open_dropdown = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
            _suppress_clicks()
