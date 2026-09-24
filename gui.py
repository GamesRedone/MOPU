import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import github_client as gc
import local_client as lc
import diffs_generator as dg
from orchestrator import run_analysis, write_output, predict_output_files, paths_overlap
from diagnostic_log import DiagnosticLog
from assets_util import resource_path
from font_loader import load_bundled_font, FONT_FAMILY
from widgets import RoundedButton, RoundedDropdown

GAMES_REDONE_URL = "https://www.gamesredone.com/"
DISCORD_URL = "https://discord.com/invite/WejTdPFBbk"
DOCUMENTATION_URL = "https://www.gamesredone.com/mopu/"
EULA_URL = "https://www.gamesredone.com/mopu-eula/"
THIRDPARTY_URL = "https://www.gamesredone.com/mopu-thirdparty/"
# Anchor guessed from the heading text ("Dos & Don'ts") using WordPress's usual
# slugify rules (lowercase, spaces to hyphens, punctuation dropped) -- the section
# doesn't exist on the page yet, so double check this matches the real anchor once
# it's added and adjust here if WordPress generated something different.
DOS_DONTS_URL = "https://www.gamesredone.com/mopu/#dos-donts"

REPO_URL_RE = re.compile(r"^(https?://)?(www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
SEMVER_RE = re.compile(r"^[vV]?\d+\.\d+\.\d+$")


def _drive_root():
    """Root of the main drive, for defaulting folder-browse dialogs there instead of
    wherever the OS last remembered -- "C:\\" on Windows, "/" elsewhere."""
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"

# Colors sampled from the Games Redone logo (sky-blue background, dark slate controller)
COLOR_BG = "#eaf6fd"
COLOR_ACCENT = "#2f8fd1"
COLOR_ACCENT_DARK = "#1f6fa8"
COLOR_TEXT = "#3c3d40"
COLOR_TROUGH = "#c8e6f7"


class ZissUpdaterApp(tk.Tk):
    PLACEHOLDER = "---"  # sentinel value for not-yet-selected dropdowns
    VERSION = "1.0.2"
    NORMAL_GEOMETRY = "720x760"  # fixed size for every step except Review

    def __init__(self):
        super().__init__()

        load_bundled_font(resource_path("assets/fonts/EBGaramond-VariableFont_wght.ttf"))
        self._font = FONT_FAMILY

        self.title(f"MOPU v{self.VERSION}")
        self._center_on_screen(*(int(n) for n in self.NORMAL_GEOMETRY.split("x")))
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        try:
            self.iconbitmap(resource_path("assets/mopu.ico"))
        except Exception:
            pass

        self._style = ttk.Style(self)
        try:
            self._style.theme_use("clam")
        except Exception:
            pass
        self._style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=(self._font, 11))
        self._style.configure("TFrame", background=COLOR_BG)
        self._style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=(self._font, 11))
        self._style.configure("TButton", background=COLOR_ACCENT, foreground="white",
                               padding=6, font=(self._font, 11))
        self._style.map("TButton", background=[("active", COLOR_ACCENT_DARK)])
        self._style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_TEXT,
                               font=(self._font, 11))
        self._style.map("TCheckbutton", focuscolor=[("", COLOR_BG)],
                         background=[("active", COLOR_BG)])
        self._style.configure("TCombobox", fieldbackground="white", font=(self._font, 11))
        self._style.configure("TEntry", font=(self._font, 11))
        self._style.configure("Horizontal.TProgressbar", troughcolor=COLOR_TROUGH,
                               background=COLOR_ACCENT, bordercolor=COLOR_BG,
                               lightcolor=COLOR_ACCENT, darkcolor=COLOR_ACCENT)
        self._style.configure("TSeparator", background=COLOR_ACCENT)

        self.workdir = tempfile.mkdtemp(prefix="mopu_")
        # One DiagnosticLog per app launch -- covers Fetch Repo through Finalize, so a
        # user hitting an error at any stage still has the earlier steps recorded when
        # they attach it for support, not just whatever step happened to fail. The
        # filename is stamped once here (at launch), not regenerated on every write,
        # so every write during this run still lands in the same file -- but a
        # different launch (a retry after closing and reopening MOPU) never silently
        # overwrites the previous run's log the way a fixed filename would.
        self._diag = DiagnosticLog()
        self._diag_log_filename = f"mopu-error-log-{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        self.repo_data = None
        self.analysis_result = None
        self.custom_profile_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.profile_var = tk.StringVar()
        self.current_version_var = tk.StringVar()
        self.target_version_var = tk.StringVar()
        self.repo_url_var = tk.StringVar(value="")

        self._logo_img = None  # keep a reference so PhotoImage isn't garbage-collected
        # Pattern background disabled for now -- back to a plain solid color. Left the
        # loading code in place (just not called) in case it's wanted again later.
        self._bg_img = None

        self.auto_update_rows = []
        self._preview_popup = None
        self._preview_text_widget = None
        self._preview_icon_img = None
        self._upload_icon_img = None
        self.show_plugins_var = tk.BooleanVar(value=False)  # plugins hidden from the
        # log by default -- shared by the Log preview popup and the Done page, so
        # toggling it in either place is consistent everywhere the log is shown.
        self._done_text_widget = None
        self._help_icon_img = None
        self._modlist_path_help_icon_img = None
        self._folder_structure_popup = None
        self._diffs_gen_icon_img = None
        self._diffs_gen_popup = None

        self._build_step1()

    # ---------------------------------------------------------------- shared chrome
    def _content_frame(self, stretch=False):
        """Every step's content goes in a centered column. `stretch=True` (Review,
        the only resizable step) also lets that column grow to fill the window
        horizontally and vertically as it's resized/maximized, instead of staying a
        fixed size with blank space padded around it -- used so the Auto Updates
        table actually gets bigger on a bigger window rather than just floating in
        more empty space."""
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        if self._bg_img is not None:
            bg_label = tk.Label(outer, image=self._bg_img, borderwidth=0)
            bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            bg_label.lower()
        content = ttk.Frame(outer)
        if stretch:
            content.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        else:
            content.pack(expand=True, pady=(20, 0))
        return outer, content

    def _footer(self, outer):
        footer = ttk.Frame(outer)
        footer.pack(side="bottom", pady=(12, 14))

        site = ttk.Label(footer, text="www.GamesRedone.com", foreground=COLOR_ACCENT_DARK,
                          cursor="hand2", font=(self._font, 15, "underline"))
        site.pack()
        site.bind("<Button-1>", lambda e: webbrowser.open(GAMES_REDONE_URL))

        legal_row = ttk.Frame(footer)
        legal_row.pack(pady=(4, 0))
        ttk.Label(legal_row, text="Copyright \u00a9 2026 Games Redone. All rights reserved. | ",
                  foreground=COLOR_TEXT, font=(self._font, 9)).pack(side="left")
        thirdparty_link = ttk.Label(legal_row, text="Third-Party Licenses", foreground=COLOR_ACCENT_DARK,
                                     cursor="hand2", font=(self._font, 9))
        thirdparty_link.pack(side="left")
        thirdparty_link.bind("<Button-1>", lambda e: webbrowser.open(THIRDPARTY_URL))
        ttk.Label(legal_row, text=" | ", foreground=COLOR_TEXT, font=(self._font, 9)).pack(side="left")
        eula_link = ttk.Label(legal_row, text="EULA", foreground=COLOR_ACCENT_DARK,
                               cursor="hand2", font=(self._font, 9))
        eula_link.pack(side="left")
        eula_link.bind("<Button-1>", lambda e: webbrowser.open(EULA_URL))

        doc_link = ttk.Label(footer, text="Documentation", foreground=COLOR_ACCENT_DARK,
                              cursor="hand2", font=(self._font, 10))
        doc_link.pack(pady=(4, 0))
        doc_link.bind("<Button-1>", lambda e: webbrowser.open(DOCUMENTATION_URL))

        discord = ttk.Label(footer, text="Join us on Discord!", foreground=COLOR_ACCENT_DARK,
                             cursor="hand2", font=(self._font, 10))
        discord.pack(pady=(4, 0))
        discord.bind("<Button-1>", lambda e: webbrowser.open(DISCORD_URL))

    def _centered_label(self, parent, text, **kwargs):
        kwargs.setdefault("justify", "center")
        kwargs.setdefault("wraplength", 620)
        font = kwargs.pop("font", None)
        if font is None:
            font = (self._font, 11)
        else:
            font = (self._font,) + tuple(font[1:])
        lbl = ttk.Label(parent, text=text, font=font, **kwargs)
        lbl.pack(anchor="center")
        return lbl

    def _copyable_label(self, parent, text, font=None, foreground=None, padding=None):
        """A centered, read-only text field the user can select and copy (Ctrl+C) --
        used for 'e.g. ...' example text. Looks like a plain label (no visible border)."""
        if font is None:
            font = (self._font, 11)
        else:
            font = (self._font,) + tuple(font[1:])
        fg = foreground or COLOR_TEXT
        top = padding[1] if padding and len(padding) > 1 else 0
        bottom = padding[3] if padding and len(padding) > 3 else 0

        wrapper = ttk.Frame(parent)
        wrapper.pack(anchor="center", pady=(top, bottom))

        e = tk.Entry(wrapper, font=font, fg=fg, bg=COLOR_BG, readonlybackground=COLOR_BG,
                     disabledforeground=fg, relief="flat", bd=0, highlightthickness=0,
                     justify="center", width=len(text) + 2)
        e.insert(0, text)
        e.config(state="readonly")
        e.pack()
        return e

    # ---------------------------------------------------------------- Step 1
    def _build_step1(self):
        self._set_resizable(False)
        self._clear()
        outer, content = self._content_frame()

        # Small icon button in the top-right corner, opens the "Prepare Your Files
        # For Upload to GitHub" helper modal -- positioned independently of the
        # centered column.
        upload_btn = self._icon_button(outer, "_upload_icon_img", "upload-cloud-blue.png",
                                        self._open_folder_structure_modal)
        if upload_btn:
            upload_btn.place(relx=1.0, x=-16, y=14, anchor="ne")

        # Sits immediately left of the upload icon, opens the "Update your diffs.md
        # file(s)" helper modal -- regenerates every profile's changelog straight
        # from a repo's own version history, rather than requiring one to be
        # hand-written.
        diffs_gen_btn = self._icon_button(outer, "_diffs_gen_icon_img", "refresh-loop-blue.png",
                                           self._open_diffs_generator_modal)
        if diffs_gen_btn:
            diffs_gen_btn.place(relx=1.0, x=-52, y=14, anchor="ne")

        # Games Redone logo -- shown only on this step, above the title
        try:
            logo_path = resource_path("assets/mopu_logo_shadow.png")
            self._logo_img = tk.PhotoImage(file=logo_path)
            ttk.Label(content, image=self._logo_img).pack(pady=(0, 6))
        except Exception:
            pass

        self._centered_label(content, "MOPU", font=("", 36, "bold"))

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=(12, 16))

        self._centered_label(content, "Link to GitHub Repository",
                              font=("", 13, "bold"))
        self._copyable_label(content, "(e.g.) github.com/GamesRedone/ZISS",
                              padding=(0, 4, 0, 8))
        entry = ttk.Entry(content, textvariable=self.repo_url_var, width=60, justify="left")
        entry.pack(pady=(4, 16))

        self.step1_status = ttk.Label(content, text="", foreground=COLOR_TEXT, justify="center")
        self.step1_status.pack(pady=(0, 2))

        self.step1_progress = ttk.Progressbar(content, mode="determinate", length=400,
                                               style="Horizontal.TProgressbar")
        # not packed until fetch starts

        RoundedButton(content, "Fetch Repo", command=self._fetch_repo,
                      width=170, height=42).pack(pady=(2, 8))

        self._footer(outer)

    def _fetch_repo(self):
        url = self.repo_url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a GitHub repo URL first.")
            return
        if not REPO_URL_RE.match(url):
            messagebox.showwarning(
                "Invalid URL",
                "Please enter a GitHub repository URL in this format:\n"
                "github.com/GamesRedone/ZISS",
            )
            return

        self.step1_progress.pack(pady=(0, 10))
        self.step1_progress["value"] = 0
        self.step1_status.config(text="Starting...")
        self.update_idletasks()

        def progress(frac, msg):
            self.after(0, lambda: self._update_progress(self.step1_progress, self.step1_status, frac, msg))

        self._diag.info(f"Fetch Repo started -- URL: {url}")

        def work():
            try:
                data = gc.fetch_repo_data(url, self.workdir, progress)
                profiles = gc.list_profiles(data)
                if not profiles:
                    raise gc.RepoError("No profile subfolders found inside LoadOrder.")
                self.repo_data = data
                self._diag.info(f"Fetch Repo succeeded -- profile(s) found: {', '.join(profiles)}")
                self.after(0, lambda: self._build_step2(profiles))
            except Exception as e:
                self._diag.error(f"Fetch Repo failed: {e}\n{traceback.format_exc()}")
                self.after(0, lambda: self._error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, bar, status_label, frac, msg):
        bar["value"] = max(0, min(100, frac * 100))
        status_label.config(text=msg)

    def _error(self, msg):
        for widget_name, action in (
            ("step1_status", lambda w: w.config(text="")),
            ("step1_progress", lambda w: w.pack_forget()),
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    if widget.winfo_exists():
                        action(widget)
                except tk.TclError:
                    pass
        messagebox.showerror("Error", msg)

    # ---------------------------------------------------------------- Step 2
    def _build_step2(self, profiles):
        self._set_resizable(False)
        self._clear()
        outer, content = self._content_frame()

        self._centered_label(content, "What MO2 profile did you build your Profile from?",
                              font=("", 13, "bold"))

        self._centered_label(content, "Select from one of the official MO2 profiles for your modlist.",
                              padding=(0, 8, 0, 6))
        self.profile_var.set(self.PLACEHOLDER)
        profile_dd = RoundedDropdown(content, values=profiles, textvariable=self.profile_var,
                                      width=220, height=36, command=self._on_profile_selected)
        profile_dd.pack()

        self.version_frame = ttk.Frame(content)
        self.version_frame.pack(pady=(14, 0))

        self.version_match_label = ttk.Label(
            content, text="Current version and target version can't be the same.",
            foreground="#b3401f", font=(self._font, 9))
        # not packed until needed

        nav = ttk.Frame(content)
        nav.pack(pady=20)
        self.step2_nav_frame = nav
        RoundedButton(nav, "Back", command=self._build_step1, kind="secondary",
                      width=90, height=32).pack(side="left")
        self.step2_next_btn = RoundedButton(nav, "Next", command=self._build_step3,
                                             width=110, height=42, state="disabled")
        self.step2_next_btn.pack(side="left", padx=6)

        self._footer(outer)

        if len(profiles) == 1:
            self.profile_var.set(profiles[0])
            self._on_profile_selected()

    def _on_profile_selected(self, *_):
        for w in self.version_frame.winfo_children():
            w.destroy()

        from version_utils import sort_versions
        versions = sort_versions(gc.list_versions(self.repo_data, self.profile_var.get()))

        self.current_version_var.set(self.PLACEHOLDER)
        self.target_version_var.set(self.PLACEHOLDER)

        ttk.Label(self.version_frame, text="Modlist Version of your profile:").grid(
            row=0, column=0, sticky="e", pady=4, padx=4)
        cur_dd = RoundedDropdown(self.version_frame, values=versions, textvariable=self.current_version_var,
                                  width=140, height=34, command=self._check_step2_ready)
        cur_dd.grid(row=0, column=1, pady=4, padx=4)

        ttk.Label(self.version_frame, text="Version to update to:").grid(
            row=1, column=0, sticky="e", pady=4, padx=4)
        tgt_dd = RoundedDropdown(self.version_frame, values=versions, textvariable=self.target_version_var,
                                  width=140, height=34, command=self._check_step2_ready)
        tgt_dd.grid(row=1, column=1, pady=4, padx=4)

        self._check_step2_ready()

    def _check_step2_ready(self, *_):
        profile_ok = self.profile_var.get() not in ("", self.PLACEHOLDER)
        cur = self.current_version_var.get()
        tgt = self.target_version_var.get()
        versions_ok = cur not in ("", self.PLACEHOLDER) and tgt not in ("", self.PLACEHOLDER)
        same_version = versions_ok and cur == tgt

        if same_version:
            self.version_match_label.pack(before=self.step2_nav_frame, pady=(8, 0))
        else:
            self.version_match_label.pack_forget()

        ready = profile_ok and versions_ok and not same_version
        self.step2_next_btn.set_state("normal" if ready else "disabled")

    # ---------------------------------------------------------------- Step 3
    def _confirm_overwrite(self, output_dir, on_continue, expected_files=None):
        """If the files this operation is actually about to write already exist in
        output_dir, ask before proceeding -- calls on_continue() either immediately
        (nothing would actually be overwritten) or after the user picks "Continue" in
        the confirmation dialog. Does nothing if "Cancel" is picked.

        `expected_files` is the set/list of paths (relative to output_dir) this
        specific run will write -- only those are checked against what's already on
        disk, so a file already sitting in the output folder that this run has
        nothing to do with never triggers a false warning. Pass None only when the
        whole folder is always replaced wholesale regardless of what's being written
        (the one case where "anything already there" is an accurate answer)."""
        existing = []
        if output_dir and os.path.isdir(output_dir):
            if expected_files is not None:
                wanted = {os.path.normpath(p).lower() for p in expected_files}
                for dirpath, _dirnames, filenames in os.walk(output_dir):
                    for fn in filenames:
                        rel = os.path.normpath(os.path.relpath(os.path.join(dirpath, fn), output_dir))
                        if rel.lower() in wanted:
                            existing.append(rel)
            else:
                for _dirpath, _dirnames, filenames in os.walk(output_dir):
                    existing.extend(filenames)
        if not existing:
            on_continue()
            return

        existing.sort(key=str.lower)
        preview = existing[:14]
        more = len(existing) - len(preview)
        list_text = "\n".join(preview) + (f"\n...and {more} more" if more else "")

        popup_w = 620
        win = self._make_centered_popup("Files Will Be Overwritten", popup_w, 240, grab=True)

        ttk.Label(win, text=(f"The output folder already contains {len(existing)} "
                              f"file(s) that will be overwritten:"),
                  justify="center", anchor="center", wraplength=popup_w - 60, background=COLOR_BG,
                  foreground=COLOR_TEXT, font=(self._font, 11)).pack(padx=30, pady=(26, 6), fill="x")

        ttk.Label(win, text=output_dir, justify="center", anchor="center", background=COLOR_BG,
                  foreground=COLOR_TEXT, font=(self._font, 9, "italic")
                  ).pack(padx=30, pady=(0, 14), fill="x")

        # justify="center" here only aligns wrapped lines relative to each other --
        # ttk.Label's own default anchor is "w" (left), so without an explicit
        # anchor="center" the whole block still hugs the left edge once fill="x"
        # stretches it to the popup's width.
        ttk.Label(win, text=list_text, justify="left", anchor="center", background=COLOR_BG,
                  foreground=COLOR_TEXT, font=(self._font, 10)).pack(padx=30, pady=(0, 14), fill="x")

        def do_continue():
            win.destroy()
            on_continue()

        nav = ttk.Frame(win)
        nav.pack(pady=(0, 22))
        RoundedButton(nav, "Cancel", command=win.destroy, kind="secondary",
                      width=100, height=36).pack(side="left", padx=6)
        RoundedButton(nav, "Continue", command=do_continue,
                      width=100, height=36).pack(side="left", padx=6)

        self._autosize_popup(win, popup_w)

    def _confirm_new_folder(self, path, on_continue):
        """If `path` doesn't exist yet, ask before creating it -- catches a typo'd
        or otherwise-unintended folder name before MOPU silently creates a brand new
        folder on disk with no feedback at all. Calls on_continue() immediately if
        the folder is already there."""
        if os.path.isdir(path):
            on_continue()
            return

        popup_w = 560
        win = self._make_centered_popup("Folder Doesn't Exist Yet", popup_w, 220, grab=True)

        ttk.Label(win, text="This folder doesn't exist yet:", justify="center", anchor="center",
                  background=COLOR_BG, foreground=COLOR_TEXT, font=(self._font, 11)
                  ).pack(padx=30, pady=(26, 6), fill="x")

        ttk.Label(win, text=path, justify="center", anchor="center", background=COLOR_BG,
                  foreground=COLOR_TEXT, font=(self._font, 9, "italic")
                  ).pack(padx=30, pady=(0, 6), fill="x")

        ttk.Label(win, text="MOPU will create it if you continue.", justify="center",
                  anchor="center", background=COLOR_BG, foreground=COLOR_TEXT,
                  font=(self._font, 11)).pack(padx=30, pady=(0, 14), fill="x")

        def do_continue():
            win.destroy()
            on_continue()

        nav = ttk.Frame(win)
        nav.pack(pady=(0, 22))
        RoundedButton(nav, "Cancel", command=win.destroy, kind="secondary",
                      width=100, height=36).pack(side="left", padx=6)
        RoundedButton(nav, "Continue", command=do_continue,
                      width=100, height=36).pack(side="left", padx=6)

        self._autosize_popup(win, popup_w)

    def _show_error_popup(self, title, message, width=640):
        """Larger, custom-styled error dialog used in place of tkinter's built-in
        messagebox wherever the text includes a file path -- the built-in messagebox
        is sized by the OS and wraps a long path mid-string at a fixed, often too
        narrow width. `message` may contain "\\n\\n"-separated paragraphs. A path has
        no spaces in it, so Tk's word-wrapping (which only breaks at whitespace)
        never splits one mid-string even when it shares a line with ordinary prose --
        the whole path just moves down as one unbroken unit if it doesn't fit."""
        paragraphs = message.split("\n\n")
        win = self._make_centered_popup(title, width, 200, grab=True)

        ttk.Label(win, text=title, font=(self._font, 16, "bold"), background=COLOR_BG,
                  foreground="#b3401f", justify="center", anchor="center", wraplength=width - 60
                  ).pack(padx=30, pady=(26, 12), fill="x")

        for p in paragraphs:
            ttk.Label(win, text=p, background=COLOR_BG, foreground=COLOR_TEXT,
                      font=(self._font, 11), justify="center", anchor="center",
                      wraplength=width - 60).pack(padx=30, pady=(0, 14), fill="x")

        RoundedButton(win, "OK", command=win.destroy, width=100, height=36).pack(pady=(6, 22))
        self._autosize_popup(win, width)
        return win

    def _build_step3(self):
        self._set_resizable(False)
        self._clear()
        outer, content = self._content_frame()

        self._centered_label(content, "Your MO2 Profile Folder", font=("", 26, "bold"))
        self._copyable_label(content, "(e.g.) D:\\ZISS\\profiles\\My Custom MO2 Profile",
                              padding=(0, 4, 0, 8))
        row = ttk.Frame(content)
        row.pack()
        ttk.Entry(row, textvariable=self.custom_profile_dir, width=48, justify="left"
                  ).pack(side="left", ipady=6)
        RoundedButton(row, "Browse...", command=self._browse_custom_dir,
                      width=100, height=28, font=(self._font, 10, "bold")).pack(side="left", padx=(0, 0))

        self._centered_label(content, "Output Folder for the Updated Profile",
                              font=("", 26, "bold"), padding=(0, 22, 0, 8))
        row2 = ttk.Frame(content)
        row2.pack()
        ttk.Entry(row2, textvariable=self.output_dir, width=48, justify="left").pack(side="left", ipady=6)
        RoundedButton(row2, "Browse...", command=self._browse_output_dir,
                      width=100, height=28, font=(self._font, 10, "bold")).pack(side="left", padx=(0, 0))

        self.step3_status = ttk.Label(content, text="", foreground=COLOR_TEXT, justify="center")
        self.step3_status.pack(pady=(16, 4))

        self.step3_progress = ttk.Progressbar(content, mode="determinate", length=400,
                                               style="Horizontal.TProgressbar")
        # packed on demand

        nav = ttk.Frame(content)
        nav.pack(pady=16)
        RoundedButton(nav, "Back", command=self._build_step2_reentry, kind="secondary",
                      width=90, height=32).pack(side="left")
        RoundedButton(nav, "Analyze My Profile", command=self._run_analysis,
                      width=190, height=42).pack(side="left", padx=6)

        self._footer(outer)

    def _build_step2_reentry(self):
        self._build_step2(gc.list_profiles(self.repo_data))

    def _browse_custom_dir(self):
        d = filedialog.askdirectory(title="Select your MO2 Profile folder", initialdir=_drive_root())
        if d:
            self.custom_profile_dir.set(d)

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Select the output folder", initialdir=_drive_root())
        if d:
            self.output_dir.set(d)

    def _validate_output_folder(self, path):
        """None if `path` looks like a genuine folder location on this computer, or
        an error message otherwise. Catches the case of someone typing or pasting
        something that isn't a real path into an Output Folder box -- a GitHub URL,
        for instance -- which os.makedirs() would otherwise happily accept, silently
        creating a nonsense folder relative to wherever MOPU happens to be running
        from instead of anywhere the person actually meant. Doesn't require the
        folder to already exist -- it'll be created -- only that it's a genuine
        absolute filesystem path."""
        if not os.path.isabs(path):
            return (
                f"This doesn't look like a real folder on your computer: {path}\n\n"
                "Please use Browse to pick an output folder."
            )
        if os.path.isfile(path):
            return f"This is a file, not a folder: {path}\n\nPlease choose a folder instead."
        return None

    def _run_analysis(self):
        if not self.custom_profile_dir.get() or not self.output_dir.get():
            messagebox.showwarning("Missing info",
                                    "Please select both a profile folder and an output folder.")
            return

        err = self._validate_output_folder(self.output_dir.get())
        if err:
            self._show_error_popup("Invalid Output Folder", err)
            return

        profile_dir = self.custom_profile_dir.get()

        if paths_overlap(self.output_dir.get(), profile_dir):
            self._show_error_popup(
                "Invalid Output Folder",
                f"This can't be the same as, or contain, your Custom Profile "
                f"folder:\n{self.output_dir.get()}\n\n"
                f"Please choose an output folder outside of\n{profile_dir}.",
            )
            return

        missing = [fn for fn in ("modlist.txt", "plugins.txt")
                   if not os.path.isfile(os.path.join(profile_dir, fn))]
        if missing:
            self._show_error_popup(
                "Invalid Profile Folder",
                f"This doesn't look like a valid MO2 profile folder -- it's missing "
                f"{' and '.join(missing)}: {profile_dir}",
            )
            return

        expected_files = predict_output_files(profile_dir)

        def proceed():
            self._confirm_overwrite(self.output_dir.get(), self._run_analysis_confirmed,
                                     expected_files=expected_files)

        self._confirm_new_folder(self.output_dir.get(), proceed)

    def _run_analysis_confirmed(self):
        cur, tgt = self.current_version_var.get(), self.target_version_var.get()
        self.step3_progress.pack(pady=(0, 10))
        self.step3_progress["value"] = 0
        self.step3_status.config(text=f"Analyzing changes from {cur} and {tgt}")
        self.update_idletasks()

        def progress(frac, msg):
            self.after(0, lambda: self._update_progress(self.step3_progress, self.step3_status, frac, msg))

        def work():
            try:
                result = run_analysis(
                    self.repo_data,
                    self.profile_var.get(),
                    cur,
                    tgt,
                    self.custom_profile_dir.get(),
                    progress,
                    diag=self._diag,
                )
                self.analysis_result = result
                self._write_diagnostic_log()
                self.after(0, self._build_step4_review)
            except Exception as e:
                traceback.print_exc()
                self._diag.error(f"Analyze failed: {e}\n{traceback.format_exc()}")
                self._write_diagnostic_log()
                self.after(0, lambda: self._error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _write_diagnostic_log(self):
        """Best-effort -- writing the troubleshooting log must never itself crash the
        app, even if the output folder isn't ready yet or isn't writable. Called after
        both Analyze and Finalize (success or failure) so it's on disk as early as
        possible and never missing just because a later step is what failed.

        Written into a "MOPU" subfolder of the output folder (e.g.
        <ModlistName>\\profiles\\<Profile Name>\\MOPU\\), the same place "Save Log"
        already defaults to on the Done screen -- keeps it out of the actual MO2
        profile folder contents (modlist.txt, plugins.txt, saves\\, etc.) instead of
        mixed in among them. The filename carries the date/time this run started
        (set once, in __init__) so re-running MOPU later never overwrites an earlier
        run's log -- each run gets its own file to attach for support."""
        try:
            out_dir = self.output_dir.get()
            if not out_dir:
                return
            mopu_dir = os.path.join(out_dir, "MOPU")
            os.makedirs(mopu_dir, exist_ok=True)
            path = os.path.join(mopu_dir, self._diag_log_filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._diag.render())
        except Exception:
            pass

    # ---------------------------------------------------------------- Step 4: Review
    def _build_step4_review(self):
        self._set_resizable(True)
        self._close_log_preview()
        self._clear()
        outer, content = self._content_frame(stretch=True)

        log = self.analysis_result.log

        review_row = ttk.Frame(content)
        review_row.pack()
        ttk.Label(review_row, text="Review", font=(self._font, 26, "bold")).pack(side="left")
        icon_btn = self._icon_button(review_row, "_preview_icon_img", "file-text-blue.png",
                                      self._open_log_preview)
        if icon_btn:
            icon_btn.pack(side="left", padx=(10, 0))

        summary = (f"Added: {len(log.added)}   Removed: {len(log.removed)}   "
                   f"Enabled: {len(log.enabled)}   Disabled: {len(log.disabled)}   "
                   f"Renamed: {len(log.renamed)}   Repositioned: {len(log.repositioned)}   "
                   f"Your Mods: {len(log.your_mods)}")
        self._centered_label(content, summary, padding=(0, 10, 0, 12))

        has_any_rows = bool(log.auto_updates)

        if not has_any_rows:
            self._centered_label(content, "No Changes to Review", foreground="#2a2")
        else:
            canvas_frame = ttk.Frame(content)
            canvas_frame.pack(fill="both", expand=True, pady=(10, 0))
            canvas = tk.Canvas(canvas_frame, borderwidth=0, highlightthickness=0,
                               bg=COLOR_BG, width=700, height=300)
            scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

            # Force geometry to settle now so the canvas has its real, final width
            # available immediately -- waiting on a <Configure> event for the initial
            # placement is unreliable (it can fire with a stale/placeholder width
            # before the window's layout has actually settled), which previously left
            # wide content (like this table) hugging the left edge instead of centered.
            canvas.update_idletasks()
            initial_cw = canvas.winfo_width() or 680

            scroll_frame = ttk.Frame(canvas)
            window_id = canvas.create_window((initial_cw // 2, 0), window=scroll_frame, anchor="n")

            def on_scroll_configure(_e=None):
                canvas.configure(scrollregion=canvas.bbox("all"))
            scroll_frame.bind("<Configure>", on_scroll_configure)

            def on_canvas_configure(event):
                if event.width > 1:
                    canvas.coords(window_id, event.width // 2, 0)
                    # Also stretch the inner frame itself to the canvas's current width
                    # (not just re-center it) -- otherwise resizing/maximizing the
                    # window just pads more blank space around a same-size table
                    # instead of actually making the table bigger.
                    canvas.itemconfig(window_id, width=event.width)
            canvas.bind("<Configure>", on_canvas_configure)

            self.auto_update_rows = []

            header_row = ttk.Frame(scroll_frame)
            header_row.pack(anchor="center", pady=(6, 8))
            ttk.Label(header_row, text="Auto Updates", font=(self._font, 13, "bold")).pack(side="left")
            help_btn = self._icon_button(header_row, "_help_icon_img", "help-circle-blue.png",
                                          self._open_auto_updates_help)
            if help_btn:
                help_btn.pack(side="left", padx=(6, 0))

            table = ttk.Frame(scroll_frame)
            table.pack(fill="x", padx=20)

            def grid_cell(parent, text, bold=False, bg=COLOR_BG, fg=COLOR_TEXT, anchor="center"):
                return tk.Label(parent, text=text, font=(self._font, 9, "bold" if bold else "normal"),
                                 relief="solid", borderwidth=1, bg=bg, fg=fg, padx=6, pady=4,
                                 anchor=anchor)

            def grid_checkbox_cell(parent, variable, command):
                cell_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg=COLOR_BG)
                cb = ttk.Checkbutton(cell_frame, variable=variable, command=command, takefocus=False)
                cb.pack(padx=6, pady=4)
                return cell_frame

            headers = ["Mod/Plugin Name", "Current State", "New State", "Apply Change", "Keep As Is"]
            # column 0 (the +/- symbol column) has no header cell -- left blank, no border,
            # so the grid's top-left corner is empty rather than an empty bordered box
            tk.Frame(table, bg=COLOR_BG).grid(row=0, column=0, sticky="nsew")
            for col, text in enumerate(headers, start=1):
                header_anchor = "w" if col == 1 else "center"
                grid_cell(table, text, bold=True, anchor=header_anchor).grid(row=0, column=col, sticky="nsew")

            # Only the Mod/Plugin Name column absorbs extra width as the window grows --
            # the state/checkbox columns stay a fixed, comfortable size either way.
            table.grid_columnconfigure(1, weight=1)

            # sorted so disabled-bound entries (new_state False) come first
            sorted_updates = sorted(log.auto_updates, key=lambda a: a.new_state)

            for i, a in enumerate(sorted_updates, start=1):
                symbol = "+" if a.new_state else "-"
                cell_bg = "#2a2" if a.new_state else "#c0392b"
                grid_cell(table, symbol, bold=True, bg=cell_bg, fg="white"
                          ).grid(row=i, column=0, sticky="nsew")

                tag = "PLUGIN" if a.file == "plugins.txt" else "MOD"
                name_text = f"[ {tag} ] {a.name}"
                grid_cell(table, name_text, anchor="w").grid(row=i, column=1, sticky="nsew")
                grid_cell(table, "enabled" if a.old_state else "disabled"
                          ).grid(row=i, column=2, sticky="nsew")
                grid_cell(table, "enabled" if a.new_state else "disabled"
                          ).grid(row=i, column=3, sticky="nsew")

                var = tk.StringVar(value="apply_new_default")
                apply_var = tk.BooleanVar(value=True)
                keep_var = tk.BooleanVar(value=False)

                def on_apply_toggle(av=apply_var, kv=keep_var, v=var):
                    if av.get():
                        kv.set(False)
                        v.set("apply_new_default")
                    else:
                        av.set(True)
                    self._refresh_log_preview_if_open()

                def on_keep_toggle(av=apply_var, kv=keep_var, v=var):
                    if kv.get():
                        av.set(False)
                        v.set("keep_as_is")
                    else:
                        kv.set(True)
                    self._refresh_log_preview_if_open()

                grid_checkbox_cell(table, apply_var, on_apply_toggle).grid(row=i, column=4, sticky="nsew")
                grid_checkbox_cell(table, keep_var, on_keep_toggle).grid(row=i, column=5, sticky="nsew")

                self.auto_update_rows.append((a, var))

        nav = ttk.Frame(content)
        nav.pack(pady=(16, 4))
        RoundedButton(nav, "Back", command=self._build_step3, kind="secondary",
                      width=90, height=32).pack(side="left")
        RoundedButton(nav, "Confirm Profile Update", command=self._finalize,
                      width=230, height=42).pack(side="left", padx=6)

        dos_donts_link = ttk.Label(content, text="Dos & Don'ts", foreground=COLOR_ACCENT_DARK,
                                    cursor="hand2", font=(self._font, 15, "bold", "underline"))
        dos_donts_link.pack(pady=(20, 12))
        dos_donts_link.bind("<Button-1>", lambda e: webbrowser.open(DOS_DONTS_URL))

        self._footer(outer)

    def _open_auto_updates_help(self):
        win = self._make_centered_popup("What is this?", 480, 420)

        ttk.Label(win, text="Auto Updates", font=(self._font, 14, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(padx=20, pady=(20, 8))

        text_widget = tk.Text(win, wrap="word", width=52, height=17, bg=COLOR_BG, fg=COLOR_TEXT,
                               font=(self._font, 11), relief="flat", bd=0, highlightthickness=0)
        text_widget.tag_configure("italic", font=(self._font, 11, "italic"))
        text_widget.tag_configure("bold", font=(self._font, 11, "bold"))
        text_widget.tag_configure("center", justify="center")

        text_widget.insert("end", "If a modlist author disables/enables a mod in an update...\n\n")
        text_widget.insert("end", "...and you still have it in the original state...", "italic")
        text_widget.insert("end", "\n\n")
        text_widget.insert("end", "...the mod will be marked to be Automatically Updated.\n\n")
        text_widget.insert("end", "Most of the time you want this change.", "bold")
        text_widget.insert("end", "\n\n")
        text_widget.insert("end",
            "Although, you may want to check here to see if any mods were disabled "
            "that are required by mods ")
        text_widget.insert("end", "YOU", "italic")
        text_widget.insert("end",
            " added.\n\n"
            "Select the option \"Keep As Is\" to reject the Auto Update.")

        text_widget.tag_add("center", "1.0", "end")
        text_widget.config(state="disabled")
        text_widget.pack(padx=20, pady=(0, 20))

    # ---------------------------------------------------------------- Prepare Your Files For Upload to GitHub
    def _open_folder_structure_modal(self):
        if self._folder_structure_popup is not None and self._folder_structure_popup.winfo_exists():
            self._folder_structure_popup.lift()
            return

        win = self._make_centered_popup("Prepare Your Files For Upload to GitHub", 560, 640)

        modlist_path_var = tk.StringVar()
        modlist_name_var = tk.StringVar()
        modlist_version_var = tk.StringVar()

        ttk.Label(win, text="Package Your Current Load Order", font=(self._font, 20, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT, justify="center", wraplength=500
                  ).pack(pady=(20, 8))

        ttk.Label(win,
                  text=("MOPU will take a snapshot of your Load Order across all "
                        "of your profiles.\n"
                        "All of the modlist.txt and plugins.txt files within "
                        "your Profiles folder will be copied."),
                  font=(self._font, 9), background=COLOR_BG, foreground=COLOR_TEXT,
                  justify="center", wraplength=460).pack(pady=(0, 14))

        path_label_row = ttk.Frame(win)
        path_label_row.pack()
        ttk.Label(path_label_row, text="File Path of Modlist", font=(self._font, 12, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(side="left")
        path_help_btn = self._icon_button(path_label_row, "_modlist_path_help_icon_img",
                                           "help-circle-blue.png", self._open_modlist_path_help)
        if path_help_btn:
            path_help_btn.pack(side="left", padx=(6, 0))

        row = ttk.Frame(win)
        row.pack(pady=(6, 0))
        ttk.Entry(row, textvariable=modlist_path_var, width=38, justify="left").pack(side="left", ipady=5)

        def browse_modlist():
            d = filedialog.askdirectory(title="Select the modlist folder", initialdir=_drive_root())
            if d:
                modlist_path_var.set(d)

        RoundedButton(row, "Browse...", command=browse_modlist, width=90, height=32,
                      font=(self._font, 10, "bold")).pack(side="left", padx=(6, 0))

        ttk.Label(win, text="Modlist Name", font=(self._font, 12, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(pady=(20, 0))
        ttk.Label(win, text="Used to name the output folder", font=(self._font, 9, "italic"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(pady=(0, 6))
        ttk.Entry(win, textvariable=modlist_name_var, width=42, justify="left").pack(ipady=5)

        ttk.Label(win, text="Modlist Version", font=(self._font, 12, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(pady=(16, 4))

        version_hint_row = ttk.Frame(win)
        version_hint_row.pack()
        ttk.Label(version_hint_row, text="Use ", font=(self._font, 9),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(side="left")
        semver_link = ttk.Label(version_hint_row, text="Semantic Versioning", font=(self._font, 9),
                                 background=COLOR_BG, foreground=COLOR_ACCENT_DARK, cursor="hand2")
        semver_link.pack(side="left")
        semver_link.bind("<Button-1>", lambda e: webbrowser.open("https://semver.org/"))
        ttk.Label(version_hint_row, text=" (e.g. v1.0.0)", font=(self._font, 9, "italic"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(side="left")

        ttk.Entry(win, textvariable=modlist_version_var, width=42, justify="left").pack(pady=(4, 0), ipady=5)

        status_label = ttk.Label(win, text="", background=COLOR_BG, foreground=COLOR_TEXT,
                                  justify="center", wraplength=500)
        status_label.pack(pady=(16, 6))

        def do_generate(modlist_path, modlist_name, modlist_version):
            try:
                mo2_updater_dir, profiles = lc.create_github_folder_structure(
                    modlist_path, modlist_name, modlist_version)
                _, output_folder = lc.output_folder_for(modlist_path, modlist_name)
            except Exception as e:
                self._show_error_popup("Error", str(e))
                return

            try:
                if sys.platform == "win32":
                    os.startfile(mo2_updater_dir)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", mo2_updater_dir])
                else:
                    subprocess.Popen(["xdg-open", mo2_updater_dir])
            except Exception:
                pass

            self._build_generate_files_done_page(win, modlist_name, profiles, output_folder)

        def on_create():
            modlist_path = modlist_path_var.get().strip()
            modlist_name = modlist_name_var.get().strip()
            modlist_version = modlist_version_var.get().strip()
            if not modlist_path:
                messagebox.showwarning("Missing path", "Please enter the file path of the modlist first.")
                return
            if not modlist_name:
                messagebox.showwarning("Missing name", "Please enter the modlist name first.")
                return
            if not modlist_version:
                messagebox.showwarning("Missing version", "Please enter the modlist version first.")
                return
            if not SEMVER_RE.match(modlist_version):
                messagebox.showwarning(
                    "Invalid Version",
                    "Please enter the modlist version using Semantic Versioning",
                )
                return

            try:
                existing = lc.existing_output_files(modlist_path, modlist_name)
            except Exception as e:
                self._show_error_popup("Error", str(e))
                return

            if existing:
                _, output_folder = lc.output_folder_for(modlist_path, modlist_name)
                self._confirm_overwrite(output_folder,
                                         lambda: do_generate(modlist_path, modlist_name, modlist_version))
            else:
                do_generate(modlist_path, modlist_name, modlist_version)

        RoundedButton(win, "Generate Files", command=on_create,
                      width=260, height=40).pack(pady=(6, 10))

        self._folder_structure_popup = win

    def _build_generate_files_done_page(self, win, modlist_name, profiles, output_folder):
        """Replaces the "Prepare Your Files" modal's contents with a Done-style
        confirmation page, in the same modal window -- no Save Log / Start Over,
        since those belong to the main profile-update flow, not this one."""
        for w in win.winfo_children():
            w.destroy()

        ttk.Label(win, text="Done!", font=(self._font, 26, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(pady=(30, 10))

        ttk.Label(win, text=f"Prepared {len(profiles)} Profile(s) for {modlist_name}",
                  font=(self._font, 12, "bold"), background=COLOR_BG, foreground=COLOR_TEXT,
                  justify="center", wraplength=500).pack(pady=(0, 10))

        profile_list = "\n".join(profiles)
        ttk.Label(win, text=profile_list, font=(self._font, 11), background=COLOR_BG,
                  foreground=COLOR_TEXT, justify="center").pack(pady=(0, 18))

        ttk.Label(win, text="You can find your output here:", font=(self._font, 10, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack()
        ttk.Label(win, text=output_folder, font=(self._font, 10), background=COLOR_BG,
                  foreground=COLOR_TEXT, justify="center", wraplength=500).pack()

    def _open_modlist_path_help(self):
        win = self._make_centered_popup("Where is your modlist installed?", 500, 280)

        ttk.Label(win, text="File Path of Modlist", font=(self._font, 14, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(padx=20, pady=(20, 12))

        ttk.Label(win, text="Regular / Global Instance", font=(self._font, 10, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack()
        ttk.Label(win, text="(e.g. C:\\Users\\<YourUsername>\\AppData\\Local\\ModOrganizer\\"
                             "<InstanceName>\\profiles).",
                  font=(self._font, 9, "italic"), background=COLOR_BG, foreground=COLOR_TEXT,
                  justify="center", wraplength=440).pack(pady=(0, 12))

        ttk.Label(win, text="Portable Instance", font=(self._font, 10, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack()
        ttk.Label(win, text="(e.g. C:\\ZISS\\ or C:\\Modlist\\ZISS\\)",
                  font=(self._font, 9, "italic"), background=COLOR_BG, foreground=COLOR_TEXT
                  ).pack()

    # ---------------------------------------------------------------- Update your diffs.md file(s)
    def _open_diffs_generator_modal(self):
        if self._diffs_gen_popup is not None and self._diffs_gen_popup.winfo_exists():
            self._diffs_gen_popup.lift()
            return

        win = self._make_centered_popup("Sync your diffs.md file(s)", 560, 560)

        # Everything lives in this inner frame, packed with expand=True and no side/
        # fill, so pack's default centering places the whole block in the middle of
        # the popup both vertically and horizontally, instead of stacked at the top
        # with empty space left below it.
        body = ttk.Frame(win)
        body.pack(expand=True)

        diffs_repo_url_var = tk.StringVar()
        diffs_output_dir_var = tk.StringVar()

        ttk.Label(body, text="Sync Your Changelog", font=(self._font, 20, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT, justify="center", wraplength=500
                  ).pack(pady=(0, 8))

        ttk.Label(body,
                  text=("This will generate updated versions your Diffs Changelog(s), "
                        "reflecting all changes across every uploaded modlist.txt and "
                        "plugins.txt file."),
                  font=(self._font, 11), background=COLOR_BG, foreground=COLOR_TEXT,
                  justify="center", wraplength=480).pack(padx=20, pady=(0, 18))

        self._centered_label(body, "Link to GitHub Repository", font=("", 13, "bold"),
                              wraplength=480)
        self._copyable_label(body, "(e.g.) github.com/GamesRedone/ZISS", padding=(0, 4, 0, 8))
        ttk.Entry(body, textvariable=diffs_repo_url_var, width=48, justify="left"
                  ).pack(pady=(4, 16), ipady=4)

        self._centered_label(body, "Output Folder for the Updated Changelogs", font=("", 13, "bold"),
                              padding=(0, 0, 0, 8), wraplength=480)
        out_row = ttk.Frame(body)
        out_row.pack()
        ttk.Entry(out_row, textvariable=diffs_output_dir_var, width=38, justify="left"
                  ).pack(side="left", ipady=5)

        def browse_output():
            d = filedialog.askdirectory(title="Select the output folder", initialdir=_drive_root())
            if d:
                diffs_output_dir_var.set(d)

        RoundedButton(out_row, "Browse...", command=browse_output, width=90, height=32,
                      font=(self._font, 10, "bold")).pack(side="left", padx=(6, 0))

        status_label = ttk.Label(body, text="", background=COLOR_BG, foreground=COLOR_TEXT,
                                  justify="center", wraplength=500)
        status_label.pack(pady=(16, 2))

        progress = ttk.Progressbar(body, mode="determinate", length=400,
                                    style="Horizontal.TProgressbar")
        # not packed until generation starts

        def progress_cb(frac, msg):
            self.after(0, lambda: self._update_progress(progress, status_label, frac, msg))

        def do_generate(repo_data, repo_url, output_dir):
            """Actually writes the changelogs -- repo_data has already been fetched
            (by fetch_then_confirm below), so this never re-hits the network."""
            def work():
                try:
                    title = gc.repo_name_from_url(repo_url) or "Modlist"
                    results = dg.generate_all_diffs(repo_data, title, output_dir,
                                                     progress_cb, diag=self._diag)
                    if not results:
                        raise gc.RepoError(
                            "No profile in this repo has at least two versions to diff.")
                    self._diag.info(f"Sync Diffs succeeded -- {len(results)} changelog(s) written")

                    try:
                        if sys.platform == "win32":
                            os.startfile(output_dir)
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", output_dir])
                        else:
                            subprocess.Popen(["xdg-open", output_dir])
                    except Exception:
                        pass

                    self.after(0, lambda: self._build_diffs_generator_done_page(win, results, output_dir))
                except Exception as e:
                    self._diag.error(f"Sync Diffs failed: {e}\n{traceback.format_exc()}")
                    self.after(0, lambda: status_label.config(text=f"Error: {e}"))
                    self.after(0, lambda: progress.pack_forget())

            threading.Thread(target=work, daemon=True).start()

        def fetch_then_confirm(repo_url, output_dir):
            """Fetches the repo first so the exact set of diffs-<profile>.md files
            this run will write is known up front -- only THOSE are checked against
            what already exists in output_dir, instead of assuming every existing
            "diffs-*.md" file in the folder is about to be replaced."""
            try:
                repo_data = gc.fetch_repo_data(repo_url, self.workdir, progress_cb)
                targets = [p for p, versions in repo_data.profiles.items() if len(versions) >= 2]
                if not targets:
                    raise gc.RepoError("No profile in this repo has at least two versions to diff.")
                expected_files = [f"diffs-{p.lower()}.md" for p in targets]

                def proceed():
                    progress["value"] = 0
                    self._confirm_overwrite(
                        output_dir,
                        lambda: do_generate(repo_data, repo_url, output_dir),
                        expected_files=expected_files,
                    )
                self.after(0, proceed)
            except Exception as e:
                self._diag.error(f"Sync Diffs failed: {e}\n{traceback.format_exc()}")
                self.after(0, lambda: status_label.config(text=f"Error: {e}"))
                self.after(0, lambda: progress.pack_forget())

        def on_generate():
            repo_url = diffs_repo_url_var.get().strip()
            output_dir = diffs_output_dir_var.get().strip()
            if not repo_url:
                messagebox.showwarning("Missing URL", "Please enter a GitHub repo URL first.")
                return
            if not REPO_URL_RE.match(repo_url):
                messagebox.showwarning(
                    "Invalid URL",
                    "Please enter a GitHub repository URL in this format:\n"
                    "github.com/GamesRedone/ZISS",
                )
                return
            if not output_dir:
                messagebox.showwarning("Missing folder", "Please choose an output folder first.")
                return
            err = self._validate_output_folder(output_dir)
            if err:
                self._show_error_popup("Invalid Output Folder", err)
                return

            def start_fetch():
                progress.pack(pady=(0, 10))
                progress["value"] = 0
                status_label.config(text="Fetching repository...")
                win.update_idletasks()
                self._diag.info(f"Sync Diffs started -- URL: {repo_url}")

                threading.Thread(target=fetch_then_confirm, args=(repo_url, output_dir),
                                  daemon=True).start()

            self._confirm_new_folder(output_dir, start_fetch)

        RoundedButton(body, "Generate Changelogs", command=on_generate,
                      width=260, height=40).pack(pady=(6, 10))

        self._diffs_gen_popup = win

    def _build_diffs_generator_done_page(self, win, results, output_dir):
        """Replaces the "Update your diffs.md file(s)" modal's contents with a
        Done-style confirmation page, in the same modal window -- mirrors
        _build_generate_files_done_page, just talking about changelogs instead of
        profiles."""
        for w in win.winfo_children():
            w.destroy()

        ttk.Label(win, text="Done!", font=(self._font, 26, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(pady=(30, 10))

        ttk.Label(win, text=f"Prepared {len(results)} Changelog(s)",
                  font=(self._font, 12, "bold"), background=COLOR_BG, foreground=COLOR_TEXT,
                  justify="center", wraplength=500).pack(pady=(0, 10))

        changelog_list = "\n".join(r.profile for r in results)
        ttk.Label(win, text=changelog_list, font=(self._font, 11), background=COLOR_BG,
                  foreground=COLOR_TEXT, justify="center").pack(pady=(0, 18))

        ttk.Label(win, text="You can find your output here:", font=(self._font, 10, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack()
        ttk.Label(win, text=output_dir, font=(self._font, 10), background=COLOR_BG,
                  foreground=COLOR_TEXT, justify="center", wraplength=500).pack()

    # ---------------------------------------------------------------- Log preview popup
    def _icon_button(self, parent, img_attr, icon_filename, command):
        """Creates a clickable icon Label (used for the upload-cloud button and the
        several "?" help icons). Loads the icon into self.<img_attr> so the
        PhotoImage isn't garbage-collected, and binds the click handler. Returns the
        Label unpositioned -- callers place/pack it themselves since that varies
        (top-right corner via place(), inline via pack(), etc) -- or returns None if
        the icon file can't be loaded, so callers should guard with `if btn:`."""
        try:
            img = tk.PhotoImage(file=resource_path(f"assets/icons/{icon_filename}"))
        except Exception:
            return None
        setattr(self, img_attr, img)
        btn = tk.Label(parent, image=img, bg=COLOR_BG, cursor="hand2")
        btn.bind("<Button-1>", lambda e: command())
        return btn

    def _center_on_screen(self, w, h):
        """Positions the main window in the center of the screen -- called once, at
        launch, before anything is drawn. Every later geometry change in this app
        (_set_resizable, below) sets only a WxH size with no +X+Y position, which
        Tk interprets as "keep the window wherever it currently is" -- so centering
        it this one time at startup is what keeps it centered for the rest of the
        app's life instead of wherever the OS would have defaulted to placing it."""
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _set_resizable(self, resizable):
        """Every step is a fixed 720x760 except Review (Step 4), which is the only
        one that benefits from more room -- the Auto Updates table can be long.
        Always resets geometry back to the normal fixed size first, so leaving
        Review at some larger size the user dragged it to (or actually maximized,
        via the OS title bar's maximize button/double-click, not just a drag-resize)
        never carries over and makes a later fixed-size step look inconsistent.

        A window the user maximized natively is in Tk's "zoomed" state, and
        `geometry()` alone has no visible effect on a zoomed window on Windows --
        it has to be dropped back to "normal" state first, or Done would still show
        full-screen even though this correctly reset the target geometry underneath
        it."""
        try:
            if self.state() == "zoomed":
                self.state("normal")
        except tk.TclError:
            pass  # "zoomed" isn't a recognized state on every platform -- harmless
        if resizable:
            self.geometry(self.NORMAL_GEOMETRY)
            self.resizable(True, True)
        else:
            self.resizable(False, False)
            self.geometry(self.NORMAL_GEOMETRY)

    def _centered_popup_position(self, popup_w, popup_h):
        """Same positioning the Log modal uses: horizontally centered over the main
        window, and pushed as high as possible so it sits above the window's
        vertical center (clamped so it never goes off the top of the window)."""
        self.update_idletasks()
        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        main_w = self.winfo_width()
        main_h = self.winfo_height()

        pos_x = main_x + (main_w - popup_w) // 2
        pos_y = main_y + (main_h // 2) - popup_h
        pos_y = max(pos_y, main_y + 10)
        return pos_x, pos_y

    def _make_centered_popup(self, title, popup_w, popup_h, grab=False):
        """Every modal in this app (Log, Auto Updates help, the folder-structure
        modal, its own instance-path help, and the overwrite-confirmation dialog)
        wants the exact same setup: a Toplevel, centered over the main window per
        _centered_popup_position, with the app icon and a title. This is that setup,
        shared instead of repeated five times."""
        pos_x, pos_y = self._centered_popup_position(popup_w, popup_h)

        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=COLOR_BG)
        win.geometry(f"{popup_w}x{popup_h}+{pos_x}+{pos_y}")
        win.transient(self)
        if grab:
            win.grab_set()
        try:
            win.iconbitmap(resource_path("assets/mopu.ico"))
        except Exception:
            pass
        return win

    def _autosize_popup(self, win, popup_w, min_h=160):
        """Call once, after every widget inside `win` has been packed, to resize the
        popup to the height its content actually needs (re-centering it in place) --
        replaces hand-guessed height math, which reliably either wastes blank space
        or clips content (including, once, the OK button) whenever the real
        rendered text takes more or less room than the guess assumed."""
        win.update_idletasks()
        popup_h = max(min_h, win.winfo_reqheight())
        pos_x, pos_y = self._centered_popup_position(popup_w, popup_h)
        win.geometry(f"{popup_w}x{popup_h}+{pos_x}+{pos_y}")

    def _open_log_preview(self):
        if self._preview_popup is not None and self._preview_popup.winfo_exists():
            self._preview_popup.lift()
            return

        win = self._make_centered_popup("Log", 480, 460)

        ttk.Label(win, text="Preview of the Changes to Your Profile",
                  font=(self._font, 11, "bold"), background=COLOR_BG,
                  foreground=COLOR_TEXT).pack(pady=(14, 4))

        ttk.Checkbutton(win, text="Show Plugins", variable=self.show_plugins_var,
                        command=self._refresh_log_preview_if_open,
                        takefocus=False).pack(pady=(0, 6))

        text_frame = ttk.Frame(win)
        text_frame.pack(padx=14, pady=(0, 14), fill="both", expand=True)

        text_widget = tk.Text(text_frame, font=(self._font, 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text_widget.pack(side="left", fill="both", expand=True)

        text_widget.insert("1.0", self._build_log_text(live=True))
        text_widget.config(state="disabled")

        self._preview_popup = win
        self._preview_text_widget = text_widget
        win.protocol("WM_DELETE_WINDOW", self._close_log_preview)

    def _refresh_log_preview_if_open(self):
        if self._preview_popup is None or self._preview_text_widget is None:
            return
        try:
            self._preview_text_widget.config(state="normal")
            self._preview_text_widget.delete("1.0", "end")
            self._preview_text_widget.insert("1.0", self._build_log_text(live=True))
            self._preview_text_widget.config(state="disabled")
        except tk.TclError:
            self._preview_popup = None
            self._preview_text_widget = None

    def _close_log_preview(self):
        if self._preview_popup is not None:
            try:
                self._preview_popup.destroy()
            except Exception:
                pass
        self._preview_popup = None
        self._preview_text_widget = None

    def _refresh_done_log(self):
        if self._done_text_widget is None:
            return
        try:
            self._done_text_widget.config(state="normal")
            self._done_text_widget.delete("1.0", "end")
            self._done_text_widget.insert("1.0", self._build_log_text())
            self._done_text_widget.config(state="disabled")
        except tk.TclError:
            self._done_text_widget = None

    # ---------------------------------------------------------------- Finalize
    def _finalize(self):
        self._close_log_preview()
        for a, var in getattr(self, "auto_update_rows", []):
            a.resolution = var.get()

        from merge_engine import apply_auto_update_resolutions
        apply_auto_update_resolutions(self.analysis_result.modlist_entries,
                                       self.analysis_result.log.auto_updates)
        apply_auto_update_resolutions(self.analysis_result.plugins_entries,
                                       self.analysis_result.log.auto_updates)

        try:
            write_output(self.custom_profile_dir.get(), self.output_dir.get(), self.analysis_result,
                         diag=self._diag)
        except Exception as e:
            self._diag.error(f"Finalize (write output) failed: {e}\n{traceback.format_exc()}")
            self._write_diagnostic_log()
            messagebox.showerror("Error writing output", str(e))
            return

        self._write_diagnostic_log()
        self._open_folder(self.output_dir.get())
        self._build_step5_done()

    def _open_folder(self, path):
        """Best-effort -- open the given folder in the OS file browser (Explorer/
        Finder/whatever the Linux desktop's default is). Never lets a failure here
        (e.g. an unusual desktop environment with no xdg-open) interrupt the rest of
        the finalize flow -- the Done screen still shows the path either way."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _build_log_text(self, live=False):
        log = self.analysis_result.log

        if live and getattr(self, "auto_update_rows", None):
            auto_resolution_by_id = {id(a): var.get() for a, var in self.auto_update_rows}
        else:
            auto_resolution_by_id = {}

        show_plugins = self.show_plugins_var.get()

        def tag_line(name, file_label):
            tag = "PLUGIN" if file_label == "plugins.txt" else "MOD"
            return f"[ {tag} ] {name}"

        def visible(file_label):
            return show_plugins or file_label != "plugins.txt"

        added_lines = [tag_line(name, fl) for name, fl in log.added if visible(fl)]
        removed_lines = [tag_line(name, fl) for name, fl in log.removed if visible(fl)]

        resolution_label = {
            "apply_new_default": "Change Applied",
            "keep_as_is": "Change Rejected",
        }

        # disabled-bound entries (new_state False) first, matching the Review table's order
        visible_updates = [a for a in log.auto_updates if visible(a.file)]
        sorted_updates = sorted(visible_updates, key=lambda a: a.new_state)

        auto_update_lines = []
        for a in sorted_updates:
            resolution = auto_resolution_by_id.get(id(a), a.resolution)
            symbol = "+" if a.new_state else "-"
            tag = "PLUGIN" if a.file == "plugins.txt" else "MOD"
            label = resolution_label.get(resolution, resolution)
            auto_update_lines.append(f"{symbol} [ {tag} ] [ {label} ] {a.name}")

        renamed_items = []
        if log.rename_warning:
            warning_lines = log.rename_warning.split("\n")
            renamed_items.append(f"[!] {warning_lines[0]}")
            renamed_items.extend(warning_lines[1:])
            if log.renamed:
                renamed_items.append("")
        renamed_items.extend(
            f"[ {'PLUGIN' if fl == 'plugins.txt' else 'MOD'} ] {old_name} -> {new_name}"
            for old_name, new_name, fl in log.renamed
            if visible(fl)
        )

        repositioned_lines = [tag_line(name, fl) for name, fl in log.repositioned if visible(fl)]
        your_mods_lines = [tag_line(name, fl) for name, fl in log.your_mods if visible(fl)]

        sections = [
            ("=== Added ===", added_lines),
            ("=== Removed ===", removed_lines),
            ("=== Renamed ===", renamed_items),
            ("=== Repositioned ===", repositioned_lines),
            ("=== Auto Updates ===", auto_update_lines),
            ("=== Your Mods (Back these up!) ===", your_mods_lines),
        ]
        blocks = []
        for header, items in sections:
            blocks.append("\n".join([header, *items]))
        return "\n\n".join(blocks) + "\n"

    def _build_step5_done(self):
        self._set_resizable(False)
        self._clear()
        outer, content = self._content_frame()

        self._centered_label(content, "DONE!", font=("", 30, "bold"))
        self._centered_label(content, f"Updated profile written to:\n{self.output_dir.get()}",
                              padding=(0, 8, 0, 14))

        cur, tgt = self.current_version_var.get(), self.target_version_var.get()
        modlist_name = gc.repo_name_from_url(self.repo_url_var.get())
        summary_line = f"Your MO2 profile has been updated from {modlist_name} {cur} to {tgt}".strip()
        self._centered_label(content, summary_line, padding=(0, 0, 0, 4))

        ttk.Checkbutton(content, text="Show Plugins", variable=self.show_plugins_var,
                        command=self._refresh_done_log,
                        takefocus=False).pack(pady=(0, 6))

        text_frame = ttk.Frame(content)
        text_frame.pack(fill="both", expand=True)

        text_box = tk.Text(text_frame, height=14, font=(self._font, 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_box.yview)
        text_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text_box.pack(side="left", fill="both", expand=True)

        text_box.insert("1.0", self._build_log_text())
        text_box.config(state="disabled")
        self._done_text_widget = text_box

        nav = ttk.Frame(content)
        nav.pack(pady=16)
        RoundedButton(nav, "Save Log (.md)", command=lambda: self._save_log("md"),
                      width=160, height=40).pack(side="left")
        RoundedButton(nav, "Save Log (.txt)", command=lambda: self._save_log("txt"),
                      width=160, height=40).pack(side="left", padx=6)

        nav2 = ttk.Frame(content)
        nav2.pack(pady=(0, 8))
        RoundedButton(nav2, "Start Over", command=self._restart, kind="secondary",
                      width=130, height=32).pack()

        self._footer(outer)

    def _save_log(self, fmt):
        ext = ".md" if fmt == "md" else ".txt"
        initial_dir = None
        if self.output_dir.get():
            initial_dir = os.path.join(self.output_dir.get(), "MOPU")
            try:
                os.makedirs(initial_dir, exist_ok=True)
            except Exception:
                initial_dir = self.output_dir.get()
        path = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=ext,
            filetypes=[("Markdown" if fmt == "md" else "Text file", f"*{ext}")],
            initialdir=initial_dir,
        )
        if not path:
            return
        content = self._build_log_text()
        if fmt == "md":
            md_lines = []
            for line in content.split("\n"):
                if line.startswith("===") and line.endswith("==="):
                    md_lines.append("## " + line.strip("= ").strip())
                else:
                    md_lines.append(line)
            content = "\n".join(md_lines)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Error saving log", str(e))

    def _restart(self):
        self.repo_data = None
        self.analysis_result = None
        self.auto_update_rows = []
        self._close_log_preview()
        self._done_text_widget = None
        self.show_plugins_var.set(False)
        self.custom_profile_dir.set("")
        self.output_dir.set("")
        self.profile_var.set("")
        self.current_version_var.set("")
        self.target_version_var.set("")
        self.repo_url_var.set("")
        self._build_step1()

    # ---------------------------------------------------------------- utils
    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def destroy(self):
        shutil.rmtree(self.workdir, ignore_errors=True)
        super().destroy()


if __name__ == "__main__":
    app = ZissUpdaterApp()
    app.mainloop()
