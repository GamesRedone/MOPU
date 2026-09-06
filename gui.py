import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import github_client as gc
import local_client as lc
from orchestrator import run_analysis, write_output
from assets_util import resource_path
from font_loader import load_bundled_font, FONT_FAMILY
from widgets import RoundedButton, RoundedDropdown

GAMES_REDONE_URL = "https://www.gamesredone.com/"
DISCORD_URL = "https://discord.com/invite/WejTdPFBbk"
DOCUMENTATION_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/190574"

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
    VERSION = "1.0.0"

    def __init__(self):
        super().__init__()

        load_bundled_font(resource_path("assets/fonts/EBGaramond-VariableFont_wght.ttf"))
        self._font = FONT_FAMILY

        self.title(f"MO2 Profile Updater v{self.VERSION}")
        self.geometry("720x760")
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
        self._style.configure("TCombobox", fieldbackground="white", font=(self._font, 11))
        self._style.configure("TEntry", font=(self._font, 11))
        self._style.configure("Horizontal.TProgressbar", troughcolor=COLOR_TROUGH,
                               background=COLOR_ACCENT, bordercolor=COLOR_BG,
                               lightcolor=COLOR_ACCENT, darkcolor=COLOR_ACCENT)
        self._style.configure("TSeparator", background=COLOR_ACCENT)

        self.workdir = tempfile.mkdtemp(prefix="mo2_profile_updater_")
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
        self._help_icon_img = None
        self._modlist_path_help_icon_img = None
        self._folder_structure_popup = None

        self._build_step1()

    # ---------------------------------------------------------------- shared chrome
    def _content_frame(self):
        """Every step's content goes in a centered column."""
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        if self._bg_img is not None:
            bg_label = tk.Label(outer, image=self._bg_img, borderwidth=0)
            bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            bg_label.lower()
        content = ttk.Frame(outer)
        content.pack(expand=True, pady=(20, 0))
        return outer, content

    def _footer(self, outer):
        sep = ttk.Separator(outer, orient="horizontal")
        sep.pack(side="bottom", fill="x", padx=20)

        footer = ttk.Frame(outer)
        footer.pack(side="bottom", pady=(12, 14))

        site = ttk.Label(footer, text="www.GamesRedone.com", foreground=COLOR_ACCENT_DARK,
                          cursor="hand2", font=(self._font, 15, "underline"))
        site.pack()
        site.bind("<Button-1>", lambda e: webbrowser.open(GAMES_REDONE_URL))

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
        self._clear()
        outer, content = self._content_frame()

        # Small icon button in the top-right corner, opens the "Prepare Your Files
        # For Upload to GitHub" helper modal -- positioned independently of the
        # centered column.
        upload_btn = self._icon_button(outer, "_upload_icon_img", "upload-cloud-blue.png",
                                        self._open_folder_structure_modal)
        if upload_btn:
            upload_btn.place(relx=1.0, x=-16, y=14, anchor="ne")

        # Games Redone logo -- shown only on this step, above the title
        try:
            logo_path = resource_path("assets/mopu_logo_shadow.png")
            self._logo_img = tk.PhotoImage(file=logo_path)
            ttk.Label(content, image=self._logo_img).pack(pady=(0, 6))
        except Exception:
            pass

        self._centered_label(content, "MO2 Profile Updater", font=("", 36, "bold"))

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

        def work():
            try:
                data = gc.fetch_repo_data(url, self.workdir, progress)
                profiles = gc.list_profiles(data)
                if not profiles:
                    raise gc.RepoError("No profile subfolders found inside LoadOrder.")
                self.repo_data = data
                self.after(0, lambda: self._build_step2(profiles))
            except Exception as e:
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
    def _confirm_overwrite(self, output_dir, on_continue):
        """If output_dir already has files in it, ask before proceeding -- calls
        on_continue() either immediately (nothing would be overwritten) or after the
        user picks "Continue" in the confirmation dialog. Does nothing if "Cancel"
        is picked."""
        existing = []
        if output_dir and os.path.isdir(output_dir):
            for _dirpath, _dirnames, filenames in os.walk(output_dir):
                existing.extend(filenames)
        if not existing:
            on_continue()
            return

        win = self._make_centered_popup("Files Will Be Overwritten", 460, 240, grab=True)

        msg = (f"The output folder already contains {len(existing)} file(s) that "
               f"will be overwritten:\n\n{output_dir}")
        ttk.Label(win, text=msg, justify="center", wraplength=400, background=COLOR_BG,
                  foreground=COLOR_TEXT, font=(self._font, 11)).pack(padx=20, pady=(24, 16))

        def do_continue():
            win.destroy()
            on_continue()

        nav = ttk.Frame(win)
        nav.pack(pady=(0, 16))
        RoundedButton(nav, "Cancel", command=win.destroy, kind="secondary",
                      width=100, height=36).pack(side="left", padx=6)
        RoundedButton(nav, "Continue", command=do_continue,
                      width=100, height=36).pack(side="left", padx=6)

    def _build_step3(self):
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
                              font=("", 26, "bold"), padding=(0, 22, 0, 4))
        self._centered_label(content,
                              "Warning: Any files currently in the output folder will be overwritten.",
                              foreground="#b3401f", padding=(0, 0, 0, 8))
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

    def _run_analysis(self):
        if not self.custom_profile_dir.get() or not self.output_dir.get():
            messagebox.showwarning("Missing info",
                                    "Please select both a profile folder and an output folder.")
            return

        profile_dir = self.custom_profile_dir.get()
        missing = [fn for fn in ("modlist.txt", "plugins.txt")
                   if not os.path.isfile(os.path.join(profile_dir, fn))]
        if missing:
            messagebox.showerror(
                "Invalid Profile Folder",
                f"This doesn't look like a valid MO2 profile folder -- it's missing "
                f"{' and '.join(missing)}.\n\n{profile_dir}",
            )
            return

        self._confirm_overwrite(self.output_dir.get(), self._run_analysis_confirmed)

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
                )
                self.analysis_result = result
                self.after(0, self._build_step4_review)
            except Exception as e:
                traceback.print_exc()
                self.after(0, lambda: self._error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- Step 4: Review
    def _build_step4_review(self):
        self._close_log_preview()
        self._clear()
        outer, content = self._content_frame()

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
                   f"Renamed: {len(log.renamed)}")
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
            table.pack(anchor="center")

            def grid_cell(parent, text, bold=False, bg=COLOR_BG, fg=COLOR_TEXT):
                return tk.Label(parent, text=text, font=(self._font, 9, "bold" if bold else "normal"),
                                 relief="solid", borderwidth=1, bg=bg, fg=fg, padx=6, pady=4)

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
                grid_cell(table, text, bold=True).grid(row=0, column=col, sticky="nsew")

            # sorted so disabled-bound entries (new_state False) come first
            sorted_updates = sorted(log.auto_updates, key=lambda a: a.new_state)

            file_tag = {"modlist.txt": "ML", "plugins.txt": "PL"}

            for i, a in enumerate(sorted_updates, start=1):
                symbol = "+" if a.new_state else "-"
                cell_bg = "#2a2" if a.new_state else "#c0392b"
                grid_cell(table, symbol, bold=True, bg=cell_bg, fg="white"
                          ).grid(row=i, column=0, sticky="nsew")

                name_text = f"{a.name} ({file_tag.get(a.file, a.file)})"
                grid_cell(table, name_text).grid(row=i, column=1, sticky="nsew")
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
        nav.pack(pady=16)
        RoundedButton(nav, "Back", command=self._build_step3, kind="secondary",
                      width=90, height=32).pack(side="left")
        RoundedButton(nav, "Confirm Profile Update", command=self._finalize,
                      width=230, height=42).pack(side="left", padx=6)

        self._footer(outer)

    def _open_auto_updates_help(self):
        win = self._make_centered_popup("What is this?", 480, 360)

        ttk.Label(win, text="Auto Updates", font=(self._font, 14, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(padx=20, pady=(20, 8))

        text_widget = tk.Text(win, wrap="word", width=52, height=13, bg=COLOR_BG, fg=COLOR_TEXT,
                               font=(self._font, 11), relief="flat", bd=0, highlightthickness=0)
        text_widget.tag_configure("italic", font=(self._font, 11, "italic"))
        text_widget.tag_configure("bold", font=(self._font, 11, "bold"))
        text_widget.tag_configure("center", justify="center")

        text_widget.insert("end", "If a mod author disables/enables a mod in an update...\n\n")
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
                messagebox.showerror("Error", str(e))
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
                messagebox.showerror("Error", str(e))
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

    def _open_log_preview(self):
        if self._preview_popup is not None and self._preview_popup.winfo_exists():
            self._preview_popup.lift()
            return

        win = self._make_centered_popup("Log", 480, 420)

        ttk.Label(win, text="Preview of the Changes to Your Profile",
                  font=(self._font, 11, "bold"), background=COLOR_BG,
                  foreground=COLOR_TEXT).pack(pady=(14, 8))

        text_widget = tk.Text(win, height=18, width=56, font=(self._font, 10))
        text_widget.pack(padx=14, pady=(0, 14), fill="both", expand=True)
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
            write_output(self.custom_profile_dir.get(), self.output_dir.get(), self.analysis_result)
        except Exception as e:
            messagebox.showerror("Error writing output", str(e))
            return

        self._build_step5_done()

    def _build_log_text(self, live=False):
        log = self.analysis_result.log

        if live and getattr(self, "auto_update_rows", None):
            auto_resolution_by_id = {id(a): var.get() for a, var in self.auto_update_rows}
        else:
            auto_resolution_by_id = {}
        auto_update_lines = []
        for a in log.auto_updates:
            resolution = auto_resolution_by_id.get(id(a), a.resolution)
            symbol = "+" if a.new_state else "-"
            auto_update_lines.append(f"{symbol} {a.name} [{a.file}]: {resolution}")

        renamed_items = []
        if log.rename_warning:
            warning_lines = log.rename_warning.split("\n")
            renamed_items.append(f"[!] {warning_lines[0]}")
            renamed_items.extend(warning_lines[1:])
            if log.renamed:
                renamed_items.append("")
        renamed_items.extend(log.renamed)

        sections = [
            ("=== Added ===", log.added),
            ("=== Removed ===", log.removed),
            ("=== Renamed ===", renamed_items),
            ("=== Auto Updates ===", auto_update_lines),
        ]
        blocks = []
        for header, items in sections:
            blocks.append("\n".join([header, *items]))
        return "\n\n".join(blocks) + "\n"

    def _build_step5_done(self):
        self._clear()
        outer, content = self._content_frame()

        self._centered_label(content, "DONE!", font=("", 30, "bold"))
        self._centered_label(content, f"Updated profile written to:\n{self.output_dir.get()}",
                              padding=(0, 8, 0, 14))

        cur, tgt = self.current_version_var.get(), self.target_version_var.get()
        modlist_name = gc.repo_name_from_url(self.repo_url_var.get())
        summary_line = f"Your MO2 profile has been updated from {modlist_name} {cur} to {tgt}".strip()
        self._centered_label(content, summary_line, padding=(0, 0, 0, 8))

        text_box = tk.Text(content, height=14, width=80, font=(self._font, 10))
        text_box.pack(fill="both", expand=True)
        text_box.insert("1.0", self._build_log_text())
        text_box.config(state="disabled")

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
            initial_dir = os.path.join(self.output_dir.get(), "MO2 Profile Updater")
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
