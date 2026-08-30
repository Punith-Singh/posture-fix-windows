"""
Dashboard — Full GUI for PostureFix Windows.

Features:
- Header with status indicator dot and camera connection info
- Live pitch, deviation, and progress bar to threshold
- 60-second live deviation chart with threshold line
- Session stats: good %, slouch count, session duration
- 7-day history stacked bar chart
- Full settings panel (sensitivity, hold, cooldown, alerts, camera)
- System tray integration
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import winsound

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import pystray
from PIL import Image, ImageDraw

from .app_state import AppState
from .posture_analyzer import PostureState
from .alert_manager import AlertManager

# Theme management
from .theme import apply_theme, DARK_THEME, LIGHT_THEME

# Chart interactivity
import mplcursors


# ── Colors ────────────────────────────────────────────────────
COLOR_BG = "#1e1e2e"
COLOR_SURFACE = "#2a2a3d"
COLOR_CARD = "#313148"
COLOR_TEXT = "#e0e0e8"
COLOR_TEXT_DIM = "#8888a0"
COLOR_GREEN = "#2ecc71"
COLOR_RED = "#e74c3c"
COLOR_AMBER = "#f39c12"
COLOR_BLUE = "#3498db"
COLOR_ACCENT = "#0078D7"
COLOR_CHART_BG = "#252538"


class PostureFixDashboard:
    def __init__(self, app_state: AppState):
        self.state = app_state
        self.state.on_state_change = self._schedule_ui_update
        self._icon = None
        self._update_pending = False

        # ── Build Root Window ──
        self.root = tk.Tk()
        self.root.title("PostureFix")
        self.root.geometry("400x800")
        self.root.minsize(380, 700)
        self.root.configure(bg=COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        # Apply initial theme
        self.current_theme = DARK_THEME
        apply_theme(self.root, self.current_theme)

        # Apply dark theme
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, fieldbackground=COLOR_SURFACE)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("TButton", background=COLOR_ACCENT, foreground="white", padding=6)
        style.map("TButton", background=[("active", "#005a9e")])
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
        style.configure("green.Horizontal.TProgressbar", troughcolor=COLOR_BG, background=COLOR_GREEN)
        style.configure("red.Horizontal.TProgressbar", troughcolor=COLOR_BG, background=COLOR_RED)

        # ── Scrollable Container ──
        self._canvas_widget = tk.Canvas(self.root, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self._canvas_widget.yview)
        self._scroll_frame = ttk.Frame(self._canvas_widget)

        self._scroll_frame.bind("<Configure>", lambda e: self._canvas_widget.configure(scrollregion=self._canvas_widget.bbox("all")))
        self._canvas_widget.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        self._canvas_widget.configure(yscrollcommand=scrollbar.set)
        self._canvas_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._canvas_widget.bind_all("<MouseWheel>", lambda e: self._canvas_widget.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._build_ui(self._scroll_frame)

        # Start periodic UI refresh
        self.root.after(200, self._ui_tick)

    # ══════════════════════════════════════════════════════════
    # ██  BUILD UI
    # ══════════════════════════════════════════════════════════
    def _build_ui(self, parent):
        # ── Header ──
        header = tk.Frame(parent, bg=COLOR_ACCENT, pady=12)
        header.pack(fill="x", padx=0, pady=(0, 8))

        header_inner = tk.Frame(header, bg=COLOR_ACCENT)
        header_inner.pack(padx=16, fill="x")

        # Status dot
        self._status_dot = tk.Canvas(header_inner, width=14, height=14, bg=COLOR_ACCENT, highlightthickness=0)
        self._dot_id = self._status_dot.create_oval(2, 2, 12, 12, fill="gray", outline="")
        self._status_dot.pack(side="left", padx=(0, 8))
        
        # Theme toggle button
        self._theme_btn = tk.Button(header_inner, text="Light", font=("Segoe UI", 9), bg=COLOR_ACCENT, fg="white", relief="flat", command=self._toggle_theme, cursor="hand2")
        self._theme_btn.pack(side="right", padx=(0, 8))

        tk.Label(header_inner, text="PostureFix", font=("Segoe UI", 14, "bold"), bg=COLOR_ACCENT, fg="white").pack(side="left")

        self._lbl_connection = tk.Label(header_inner, text="Camera Off", font=("Segoe UI", 9), bg=COLOR_ACCENT, fg="#cce0ff")
        self._lbl_connection.pack(side="right")

        # ── Status Section ──
        status_card = tk.Frame(parent, bg=COLOR_CARD, padx=16, pady=12)
        status_card.pack(fill="x", padx=12, pady=4)

        self._lbl_headline = tk.Label(status_card, text="Click Start to begin", font=("Segoe UI", 13, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT)
        self._lbl_headline.pack(anchor="w")

        # Progress bar (slouch fraction)
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress = ttk.Progressbar(status_card, variable=self._progress_var, maximum=1.0, length=300, style="green.Horizontal.TProgressbar")
        self._progress.pack(fill="x", pady=(8, 4))

        info_row = tk.Frame(status_card, bg=COLOR_CARD)
        info_row.pack(fill="x")
        self._lbl_drop = tk.Label(info_row, text="Head drop: 0.0°", font=("Segoe UI", 10), bg=COLOR_CARD, fg=COLOR_TEXT_DIM)
        self._lbl_drop.pack(side="left")
        self._lbl_pitch = tk.Label(info_row, text="Pitch: 0.0°", font=("Segoe UI", 10), bg=COLOR_CARD, fg=COLOR_TEXT_DIM)
        self._lbl_pitch.pack(side="right")

        # ── Face Detection Indicator ──
        self._lbl_face = tk.Label(parent, text="", font=("Segoe UI", 9), bg=COLOR_BG, fg=COLOR_TEXT_DIM)
        self._lbl_face.pack(anchor="w", padx=16, pady=(4, 0))

        # ── Session Stats ──
        self._stats_frame = tk.Frame(parent, bg=COLOR_BG)
        self._stats_frame.pack(fill="x", padx=12, pady=4)

        self._stat_good = self._make_stat_tile(self._stats_frame, "Good Posture", "—", 0)
        self._stat_slouch = self._make_stat_tile(self._stats_frame, "Slouches", "—", 1)
        self._stat_time = self._make_stat_tile(self._stats_frame, "Session", "—", 2)

        self._stats_frame.columnconfigure(0, weight=1)
        self._stats_frame.columnconfigure(1, weight=1)
        self._stats_frame.columnconfigure(2, weight=1)

        # ── Live Chart ──
        chart_label = tk.Label(parent, text="Head Drop (last 60s)", font=("Segoe UI", 9, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DIM)
        chart_label.pack(anchor="w", padx=16, pady=(8, 2))

        self._fig_live = Figure(figsize=(3.6, 1.6), dpi=100, facecolor=COLOR_CHART_BG)
        self._ax_live = self._fig_live.add_subplot(111)
        self._ax_live.set_facecolor(COLOR_CHART_BG)
        self._fig_live.subplots_adjust(left=0.12, right=0.96, top=0.92, bottom=0.18)

        self._canvas_live = FigureCanvasTkAgg(self._fig_live, master=parent)
        self._canvas_live.get_tk_widget().pack(fill="x", padx=12, pady=2)

        # ── Control Buttons ──
        btn_frame = tk.Frame(parent, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=12, pady=8)

        self._btn_start = tk.Button(btn_frame, text="▶  Start Monitoring", font=("Segoe UI", 10, "bold"),
                                     bg=COLOR_GREEN, fg="white", relief="flat", padx=12, pady=8,
                                     command=self._toggle_monitoring, cursor="hand2")
        self._btn_start.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._btn_calibrate = tk.Button(btn_frame, text="◎  Calibrate", font=("Segoe UI", 10, "bold"),
                                         bg=COLOR_BLUE, fg="white", relief="flat", padx=12, pady=8,
                                         command=self._calibrate, cursor="hand2")
        self._btn_calibrate.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # ── 7-Day History Section ──
        hist_header = tk.Frame(parent, bg=COLOR_BG)
        hist_header.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(hist_header, text="7-Day History", font=("Segoe UI", 10, "bold"), bg=COLOR_BG, fg=COLOR_TEXT).pack(side="left")

        self._fig_hist = Figure(figsize=(3.6, 1.4), dpi=100, facecolor=COLOR_CHART_BG)
        self._ax_hist = self._fig_hist.add_subplot(111)
        self._ax_hist.set_facecolor(COLOR_CHART_BG)
        self._fig_hist.subplots_adjust(left=0.12, right=0.96, top=0.88, bottom=0.22)

        self._canvas_hist = FigureCanvasTkAgg(self._fig_hist, master=parent)
        self._canvas_hist.get_tk_widget().pack(fill="x", padx=12, pady=2)

        self._lbl_week_summary = tk.Label(parent, text="", font=("Segoe UI", 9), bg=COLOR_BG, fg=COLOR_TEXT_DIM)
        self._lbl_week_summary.pack(anchor="w", padx=16, pady=(0, 4))

        # ── Settings Section (collapsible) ──
        settings_header = tk.Frame(parent, bg=COLOR_BG, cursor="hand2")
        settings_header.pack(fill="x", padx=16, pady=(8, 2))
        self._settings_toggle_text = tk.StringVar(value="▸ Settings")
        tk.Label(settings_header, textvariable=self._settings_toggle_text, font=("Segoe UI", 10, "bold"),
                 bg=COLOR_BG, fg=COLOR_TEXT, cursor="hand2").pack(side="left")
        settings_header.bind("<Button-1>", self._toggle_settings)
        for child in settings_header.winfo_children():
            child.bind("<Button-1>", self._toggle_settings)

        self._settings_frame = tk.Frame(parent, bg=COLOR_SURFACE, padx=12, pady=10)
        self._settings_visible = False

        self._build_settings_panel(self._settings_frame)

        # ── Footer ──
        footer = tk.Frame(parent, bg=COLOR_BG)
        footer.pack(fill="x", padx=16, pady=(12, 8))
        tk.Button(footer, text="Quit PostureFix", font=("Segoe UI", 9), bg=COLOR_RED, fg="white",
                  relief="flat", padx=8, pady=4, command=self._quit_app, cursor="hand2").pack(side="right")

        # Initial chart render
        self._update_history_chart()

    def _make_stat_tile(self, parent, label: str, value: str, col: int):
        frame = tk.Frame(parent, bg=COLOR_CARD, padx=8, pady=8)
        frame.grid(row=0, column=col, padx=3, sticky="nsew")
        val_lbl = tk.Label(frame, text=value, font=("Segoe UI", 16, "bold"), bg=COLOR_CARD, fg=COLOR_TEXT)
        val_lbl.pack()
        tk.Label(frame, text=label, font=("Segoe UI", 8), bg=COLOR_CARD, fg=COLOR_TEXT_DIM).pack()
        return val_lbl

    # ── Settings Panel ──
    def _build_settings_panel(self, parent):
        s = self.state

        # Sensitivity
        tk.Label(parent, text="Sensitivity (degrees drop to count as slouch)", font=("Segoe UI", 9), bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(4, 0))
        self._scale_sens = tk.Scale(parent, from_=5, to=30, orient="horizontal", resolution=1,
                                     bg=COLOR_SURFACE, fg=COLOR_TEXT, highlightthickness=0, troughcolor=COLOR_BG)
        self._scale_sens.set(s.get_setting("threshold"))
        self._scale_sens.pack(fill="x")

        # Hold time
        tk.Label(parent, text="Hold before alert (seconds of slouching)", font=("Segoe UI", 9), bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(4, 0))
        self._scale_hold = tk.Scale(parent, from_=1, to=10, orient="horizontal", resolution=0.5,
                                     bg=COLOR_SURFACE, fg=COLOR_TEXT, highlightthickness=0, troughcolor=COLOR_BG)
        self._scale_hold.set(s.get_setting("hold_seconds"))
        self._scale_hold.pack(fill="x")

        # Cooldown
        tk.Label(parent, text="Alert cooldown (minimum gap between nudges)", font=("Segoe UI", 9), bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(4, 0))
        self._scale_cool = tk.Scale(parent, from_=5, to=120, orient="horizontal", resolution=5,
                                     bg=COLOR_SURFACE, fg=COLOR_TEXT, highlightthickness=0, troughcolor=COLOR_BG)
        self._scale_cool.set(s.get_setting("cooldown"))
        self._scale_cool.pack(fill="x")

        # Alert sound picker
        tk.Label(parent, text="Alert Sound", font=("Segoe UI", 9), bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(8, 0))
        sound_row = tk.Frame(parent, bg=COLOR_SURFACE)
        sound_row.pack(fill="x")
        self._sound_var = tk.StringVar(value=s.get_setting("sound_name"))
        sound_menu = ttk.Combobox(sound_row, textvariable=self._sound_var, values=AlertManager.AVAILABLE_SOUNDS,
                                   state="readonly", width=20)
        sound_menu.pack(side="left", padx=(0, 8))
        tk.Button(sound_row, text="▶ Preview", font=("Segoe UI", 8), bg=COLOR_ACCENT, fg="white",
                  relief="flat", padx=4, command=self._preview_sound, cursor="hand2").pack(side="left")

        # Toggles
        self._var_sound = tk.BooleanVar(value=s.get_setting("sound_enabled"))
        self._var_voice = tk.BooleanVar(value=s.get_setting("voice_enabled"))
        self._var_notif = tk.BooleanVar(value=s.get_setting("notification_enabled"))
        self._var_invert = tk.BooleanVar(value=s.get_setting("invert"))

        toggle_frame = tk.Frame(parent, bg=COLOR_SURFACE)
        toggle_frame.pack(fill="x", pady=(8, 0))
        for text, var in [("Sound cue", self._var_sound), ("Spoken cue (\"Sit up straight\")", self._var_voice),
                          ("Windows notifications", self._var_notif), ("Reverse detection", self._var_invert)]:
            tk.Checkbutton(toggle_frame, text=text, variable=var, bg=COLOR_SURFACE, fg=COLOR_TEXT,
                           selectcolor=COLOR_BG, activebackground=COLOR_SURFACE, activeforeground=COLOR_TEXT,
                           font=("Segoe UI", 9)).pack(anchor="w")

        # Camera index
        tk.Label(parent, text="Camera Index (0 = default webcam)", font=("Segoe UI", 9), bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(8, 0))
        self._scale_cam = tk.Scale(parent, from_=0, to=4, orient="horizontal", resolution=1,
                                    bg=COLOR_SURFACE, fg=COLOR_TEXT, highlightthickness=0, troughcolor=COLOR_BG)
        self._scale_cam.set(s.get_setting("camera_index"))
        self._scale_cam.pack(fill="x")

        # Save button
        tk.Button(parent, text="Save Settings", font=("Segoe UI", 9, "bold"), bg=COLOR_GREEN, fg="white",
                  relief="flat", padx=10, pady=6, command=self._save_settings, cursor="hand2").pack(pady=(10, 4))

    def _toggle_settings(self, event=None):
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_toggle_text.set("▸ Settings")
        else:
            self._settings_frame.pack(fill="x", padx=12, pady=2)
            self._settings_toggle_text.set("▾ Settings")
        self._settings_visible = not self._settings_visible

    def _preview_sound(self):
        self.state.alerts.sound_name = self._sound_var.get()
        self.state.alerts.preview_sound()

    def _save_settings(self):
        self.state.update_settings({
            "threshold": self._scale_sens.get(),
            "hold_seconds": self._scale_hold.get(),
            "cooldown": self._scale_cool.get(),
            "sound_name": self._sound_var.get(),
            "sound_enabled": self._var_sound.get(),
            "voice_enabled": self._var_voice.get(),
            "notification_enabled": self._var_notif.get(),
            "invert": self._var_invert.get(),
            "camera_index": int(self._scale_cam.get()),
        })
        messagebox.showinfo("PostureFix", "Settings saved! Restart monitoring to apply camera changes.")

    # ══════════════════════════════════════════════════════════
    # ██  UI UPDATE
    # ══════════════════════════════════════════════════════════
    def _schedule_ui_update(self):
        self._update_pending = True

    def _ui_tick(self):
        if self._update_pending or self.state.is_monitoring:
            self._update_pending = False
            self._refresh_ui()
        self.root.after(200, self._ui_tick)

    def _refresh_ui(self):
        s = self.state

        # ── Status dot color ──
        if not s.is_monitoring:
            dot_color = "gray"
        elif not s.webcam.face_detected:
            dot_color = COLOR_AMBER
        elif not s.is_calibrated:
            dot_color = COLOR_AMBER
        elif s.posture_state == PostureState.GOOD:
            dot_color = COLOR_GREEN
        else:
            dot_color = COLOR_RED
        self._status_dot.itemconfig(self._dot_id, fill=dot_color)

        # ── Connection label ──
        self._lbl_connection.config(text=s.webcam.status_text)

        # ── Face detection indicator ──
        if s.is_monitoring:
            if s.webcam.face_detected:
                self._lbl_face.config(text="👤 Face detected", fg=COLOR_GREEN)
            elif s.webcam.is_connected:
                self._lbl_face.config(text="⚠ No face — please look at the camera", fg=COLOR_AMBER)
            else:
                self._lbl_face.config(text="📷 Opening camera...", fg=COLOR_TEXT_DIM)
        else:
            self._lbl_face.config(text="")

        # ── Headline ──
        if not s.is_monitoring:
            self._lbl_headline.config(text="Paused", fg=COLOR_TEXT_DIM)
        elif not s.webcam.face_detected:
            self._lbl_headline.config(text="Look at the camera", fg=COLOR_AMBER)
        elif not s.is_calibrated:
            self._lbl_headline.config(text="Sit upright, then click Calibrate", fg=COLOR_AMBER)
        elif s.posture_state == PostureState.GOOD:
            self._lbl_headline.config(text="Good posture ✓", fg=COLOR_GREEN)
        elif s.posture_state == PostureState.BAD:
            self._lbl_headline.config(text="Slouching — straighten up!", fg=COLOR_RED)
        else:
            self._lbl_headline.config(text="Analyzing...", fg=COLOR_TEXT_DIM)

        # ── Progress bar ──
        self._progress_var.set(s.slouch_fraction)
        if s.posture_state == PostureState.BAD:
            self._progress.configure(style="red.Horizontal.TProgressbar")
        else:
            self._progress.configure(style="green.Horizontal.TProgressbar")

        # ── Drop & Pitch ──
        self._lbl_drop.config(text=f"Head drop: {s.deviation:.1f}°")
        self._lbl_pitch.config(text=f"Pitch: {s.live_pitch:.1f}°")

        # ── Session stats ──
        if s.is_calibrated and s.is_monitoring:
            self._stat_good.config(text=f"{s.good_percent:.0f}%")
            self._stat_slouch.config(text=str(s.slouch_events))
            elapsed = int(s.session_elapsed)
            mins, secs = divmod(elapsed, 60)
            self._stat_time.config(text=f"{mins:02d}:{secs:02d}")
        elif not s.is_monitoring:
            self._stat_good.config(text="—")
            self._stat_slouch.config(text="—")
            self._stat_time.config(text="—")

        # ── Buttons ──
        if s.is_monitoring:
            self._btn_start.config(text="⏹  Stop Monitoring", bg=COLOR_RED)
        else:
            self._btn_start.config(text="▶  Start Monitoring", bg=COLOR_GREEN)

        if s.is_calibrated:
            self._btn_calibrate.config(text="◎  Recalibrate")
        else:
            self._btn_calibrate.config(text="◎  Calibrate (sit upright)")

        # ── Live chart ──
        self._update_live_chart()

    def _update_live_chart(self):
        ax = self._ax_live
        ax.clear()

        samples = self.state.recent_samples
        threshold = self.state.get_setting("threshold")

        if samples:
            times = [s.t for s in samples]
            drops = [s.drop for s in samples]
            t_min, t_max = times[0], times[-1]

            line_color = COLOR_RED if self.state.posture_state == PostureState.BAD else COLOR_GREEN
            ax.fill_between(times, drops, alpha=0.15, color=line_color)
            ax.plot(times, drops, color=line_color, linewidth=1.5)
            mplcursors.cursor(ax, hover=True).connect("add", lambda sel: sel.annotation.set_text(f"{sel.target[1]:.1f}°"))
            ax.axhline(y=threshold, color=COLOR_RED, linestyle="--", linewidth=1, alpha=0.6)
            ax.set_xlim(t_min, max(t_max, t_min + 10))
            ax.set_ylim(0, max(max(drops) * 1.2, threshold * 1.5, 5))
        else:
            ax.axhline(y=threshold, color=COLOR_RED, linestyle="--", linewidth=1, alpha=0.6)
            ax.set_ylim(0, threshold * 1.5)

        ax.tick_params(colors=COLOR_TEXT_DIM, labelsize=7)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color(COLOR_TEXT_DIM)
        ax.spines['left'].set_color(COLOR_TEXT_DIM)
        ax.set_ylabel("Drop°", fontsize=7, color=COLOR_TEXT_DIM)

        try:
            self._canvas_live.draw_idle()
        except Exception:
            pass

    def _update_history_chart(self):
        ax = self._ax_hist
        ax.clear()

        days = self.state.history.last_days(7)
        labels = [d.short_weekday for d in days]
        good_mins = [d.good_minutes for d in days]
        bad_mins = [d.bad_minutes for d in days]
        x = range(len(days))

        ax.bar(x, good_mins, color=COLOR_GREEN, alpha=0.8, label="Good", width=0.5)
        ax.bar(x, bad_mins, bottom=good_mins, color=COLOR_RED, alpha=0.8, label="Slouch", width=0.5)

        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.tick_params(colors=COLOR_TEXT_DIM, labelsize=7)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color(COLOR_TEXT_DIM)
        ax.spines['left'].set_color(COLOR_TEXT_DIM)
        ax.set_ylabel("Min", fontsize=7, color=COLOR_TEXT_DIM)

        total_good = sum(good_mins)
        total_all = total_good + sum(bad_mins)
        if total_all > 0:
            pct = (total_good / total_all) * 100
            self._lbl_week_summary.config(text=f"This week: {pct:.0f}% good · {total_all:.0f} min tracked")
        else:
            self._lbl_week_summary.config(text="No history yet this week")

        try:
            self._canvas_hist.draw_idle()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # ██  ACTIONS
    # ══════════════════════════════════════════════════════════
    def _toggle_monitoring(self):
        if self.state.is_monitoring:
            self.state.stop_monitoring()
            self._update_history_chart()
        else:
            self.state.start_monitoring()

    def _calibrate(self):
        if not self.state.webcam.is_connected:
            messagebox.showwarning("PostureFix", "Camera not active.\nClick 'Start Monitoring' first.")
            return
        if not self.state.webcam.face_detected:
            messagebox.showwarning("PostureFix", "No face detected.\nPlease look at the camera and try again.")
            return
        ok = self.state.calibrate()
        if ok:
            winsound.MessageBeep(winsound.MB_OK)

    def _quit_app(self):
        self.state.stop_monitoring()
        if self._icon:
            self._icon.stop()
        self.root.destroy()
        os._exit(0)

    def _hide_to_tray(self):
        self.root.withdraw()

    def _show_from_tray(self):
        self.root.deiconify()

    def _toggle_theme(self):
        """Toggle between dark and light themes and update UI elements."""
        if self.current_theme == DARK_THEME:
            self.current_theme = LIGHT_THEME
            self._theme_btn.config(text="Dark")
        else:
            self.current_theme = DARK_THEME
            self._theme_btn.config(text="Light")
        apply_theme(self.root, self.current_theme)
        # Force redraw of charts to apply new background colors
        self._update_live_chart()
        self._update_history_chart()


    # ══════════════════════════════════════════════════════════
    # ██  SYSTEM TRAY
    # ══════════════════════════════════════════════════════════
    def setup_tray(self):
        image = self._create_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Open PostureFix", self._show_from_tray, default=True),
            pystray.MenuItem(
                lambda text: "Stop Monitoring" if self.state.is_monitoring else "Start Monitoring",
                lambda: self.root.after(0, self._toggle_monitoring)
            ),
            pystray.MenuItem("Quit", lambda: self.root.after(0, self._quit_app)),
        )
        self._icon = pystray.Icon("PostureFix", image, "PostureFix", menu)
        self._icon.run()

    def _create_tray_icon(self) -> Image.Image:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, size - 4, size - 4], fill=(0, 120, 215, 255))
        cx, cy = size // 2, size // 2
        draw.ellipse([cx - 6, cy - 18, cx + 6, cy - 6], fill=(255, 255, 255, 255))
        draw.line([(cx, cy - 6), (cx, cy + 10)], fill=(255, 255, 255, 255), width=3)
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill=(255, 255, 255, 255), width=2)
        draw.line([(cx, cy + 10), (cx - 8, cy + 22)], fill=(255, 255, 255, 255), width=2)
        draw.line([(cx, cy + 10), (cx + 8, cy + 22)], fill=(255, 255, 255, 255), width=2)
        return img

    # ══════════════════════════════════════════════════════════
    # ██  RUN
    # ══════════════════════════════════════════════════════════
    def run(self):
        threading.Thread(target=self.setup_tray, daemon=True).start()
        self.root.mainloop()
