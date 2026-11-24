import time
import tkinter as tk
import customtkinter as ctk
from config import THEME
from widgets import PillBadge, _hex_blend


class GameNotificationToast(ctk.CTkToplevel):
    """
    Modern dark-glass floating toast notification that appears when a game starts
    (or Turbo Boost runs), displays live system telemetry & optimization badges,
    and automatically fades out after 10-15 seconds.
    """

    def __init__(self, master, payload: dict, duration_sec: int = 12, position: str = "Sağ Üst", on_close=None):
        super().__init__(master)
        self.duration_sec = max(5, min(25, int(duration_sec)))
        self.on_close = on_close
        self._start_time = time.perf_counter()
        self._closed = False
        self._alpha = 0.0

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(fg_color=THEME["bg_root"])

        width = 390
        height = 228
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        margin_x, margin_y = 22, 48

        if position == "Sağ Alt":
            x = sw - width - margin_x
            y = sh - height - margin_y - 24
        elif position == "Sol Üst":
            x = margin_x
            y = margin_y
        elif position == "Sol Alt":
            x = margin_x
            y = sh - height - margin_y - 24
        else:  # Sağ Üst
            x = sw - width - margin_x
            y = margin_y

        self.geometry(f"{width}x{height}+{x}+{y}")

        # Outer glowing border container
        outer = ctk.CTkFrame(
            self,
            fg_color="#0E131F",
            border_color=THEME["accent_indigo"],
            border_width=1.5,
            corner_radius=16,
        )
        outer.pack(fill="both", expand=True)

        # Header row
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))

        icon_box = ctk.CTkFrame(
            header, width=34, height=34, corner_radius=10, fg_color="#1D2144", border_width=1, border_color="#3D458A"
        )
        icon_box.pack(side="left", padx=(0, 10))
        icon_box.pack_propagate(False)
        ctk.CTkLabel(
            icon_box,
            text="🎮",
            font=ctk.CTkFont(size=16),
            text_color=THEME["text_primary"],
        ).place(relx=0.5, rely=0.5, anchor="center")

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)

        title_text = payload.get("title", "Oyun Yakalandı — Optimize Ediliyor")
        ctk.CTkLabel(
            title_col,
            text=title_text,
            text_color=THEME["accent_emerald"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        game_name = payload.get("game_name", "Oyun")
        pid = payload.get("pid", "-")
        ctk.CTkLabel(
            title_col,
            text=f"{game_name}  •  PID {pid}",
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        right_ctrl = ctk.CTkFrame(header, fg_color="transparent")
        right_ctrl.pack(side="right", anchor="n")

        self.countdown_lbl = ctk.CTkLabel(
            right_ctrl,
            text=f"{self.duration_sec}s",
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        )
        self.countdown_lbl.pack(side="left", padx=(0, 6))

        close_btn = ctk.CTkButton(
            right_ctrl,
            text="✕",
            width=24,
            height=24,
            corner_radius=8,
            fg_color="#1A2033",
            hover_color="#2A3350",
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.close_toast,
        )
        close_btn.pack(side="left")

        # Applied optimizations pill row
        pills_frame = ctk.CTkFrame(outer, fg_color="transparent")
        pills_frame.pack(fill="x", padx=14, pady=(2, 8))

        freed_mb = payload.get("freed_mb", 0.0)
        PillBadge(pills_frame, f"⚡ +{freed_mb:.0f} MB RAM", "emerald").pack(side="left", padx=(0, 6))
        PillBadge(pills_frame, "🚀 Yüksek Öncelik", "indigo").pack(side="left", padx=(0, 6))
        PillBadge(pills_frame, "⏱ 1ms Timer", "cyan").pack(side="left")

        # Live telemetry 4-column mini grid
        grid = ctk.CTkFrame(outer, fg_color="#131929", corner_radius=12, border_width=1, border_color="#202840")
        grid.pack(fill="x", padx=14, pady=(0, 10))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        self._metric_vals = {}
        specs = [
            ("fps", "FPS", THEME["accent_emerald"]),
            ("cpu", "CPU", THEME["accent_indigo"]),
            ("ram", "RAM", THEME["accent_cyan"]),
            ("gpu", "GPU", THEME["accent_amber"]),
        ]
        for idx, (key, label, color) in enumerate(specs):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=0, column=idx, sticky="nsew", padx=4, pady=8)
            ctk.CTkLabel(
                cell,
                text=label,
                text_color=THEME["text_muted"],
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            ).pack()
            val_lbl = ctk.CTkLabel(
                cell,
                text="--",
                text_color=color,
                font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            )
            val_lbl.pack()
            sub_lbl = ctk.CTkLabel(
                cell,
                text="",
                text_color=THEME["text_secondary"],
                font=ctk.CTkFont(family="Consolas", size=9),
            )
            sub_lbl.pack()
            self._metric_vals[key] = (val_lbl, sub_lbl)

        # Footer info
        power_plan = payload.get("power_plan", "Yüksek Performans")
        ctk.CTkLabel(
            outer,
            text=f"Güç Planı: {power_plan[:34]}  •  Sürekli Optimizasyon Aktif",
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=10),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        # Smooth countdown progress bar
        self.progress = ctk.CTkProgressBar(
            outer,
            height=4,
            corner_radius=2,
            fg_color="#1B2235",
            progress_color=THEME["accent_indigo"],
        )
        self.progress.pack(fill="x", padx=14, pady=(0, 10))
        self.progress.set(1.0)

        # Seed initial telemetry if available
        if payload.get("telemetry"):
            self.update_live_metrics(payload["telemetry"])

        self._animate_fade_in()
        self._tick_countdown()

    def update_live_metrics(self, data: dict):
        if self._closed:
            return
        try:
            fps_d = data.get("fps", {})
            gpu_d = data.get("gpu", {})

            fps_val = fps_d.get("fps", 0.0)
            ft = fps_d.get("frametime_ms", 0.0)
            self._metric_vals["fps"][0].configure(text=f"{fps_val:.0f}")
            self._metric_vals["fps"][1].configure(text=f"{ft:.1f}ms")

            cpu_val = data.get("cpu_percent", 0.0)
            self._metric_vals["cpu"][0].configure(text=f"%{cpu_val:.0f}")
            self._metric_vals["cpu"][1].configure(text=f"{data.get('cpu_mhz', 0):.0f}MHz")

            ram_val = data.get("ram_percent", 0.0)
            self._metric_vals["ram"][0].configure(text=f"%{ram_val:.0f}")
            self._metric_vals["ram"][1].configure(text=f"{data.get('ram_used_gb', 0):.1f}GB")

            if gpu_d.get("available"):
                self._metric_vals["gpu"][0].configure(text=f"%{gpu_d.get('usage', 0):.0f}")
                self._metric_vals["gpu"][1].configure(text=f"{gpu_d.get('temp', 0):.0f}°C")
            else:
                self._metric_vals["gpu"][0].configure(text="—")
                self._metric_vals["gpu"][1].configure(text="N/A")
        except Exception:
            pass

    def _animate_fade_in(self):
        if self._closed:
            return
        self._alpha = min(0.95, self._alpha + 0.12)
        try:
            self.attributes("-alpha", self._alpha)
        except Exception:
            return
        if self._alpha < 0.95:
            self.after(20, self._animate_fade_in)

    def _tick_countdown(self):
        if self._closed:
            return
        elapsed = time.perf_counter() - self._start_time
        remaining = max(0.0, self.duration_sec - elapsed)
        frac = remaining / self.duration_sec
        try:
            self.progress.set(frac)
            self.countdown_lbl.configure(text=f"{int(remaining + 0.9)}s")
        except Exception:
            return

        if remaining <= 0.0:
            self._animate_fade_out()
        else:
            self.after(100, self._tick_countdown)

    def _animate_fade_out(self):
        if self._closed:
            return
        self._alpha = max(0.0, self._alpha - 0.12)
        try:
            self.attributes("-alpha", self._alpha)
        except Exception:
            self.close_toast()
            return
        if self._alpha <= 0.02:
            self.close_toast()
        else:
            self.after(25, self._animate_fade_out)

    def close_toast(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass


class FPSOverlayHUD(ctk.CTkToplevel):
    """
    Custom draggable, always-on-top floating FPS & Performance HUD widget.
    Supports 'Detaylı', 'Kompakt', and 'Minimal' layouts.
    """

    def __init__(self, master, config: dict):
        super().__init__(master)
        self.config_data = config
        self._drag_x = 0
        self._drag_y = 0
        self._fps_hist = [0.0] * 36

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=THEME["bg_root"])

        self.container = ctk.CTkFrame(
            self,
            fg_color="#0B0F19",
            border_color="#2A3452",
            border_width=1,
            corner_radius=12,
        )
        self.container.pack(fill="both", expand=True)

        self.labels = {}
        self.graph_canvas = None

        self.rebuild()
        self.apply_position()
        self.apply_opacity()

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        if self.config_data.get("hud_locked", False):
            return
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        if self.config_data.get("hud_locked", False):
            return
        x = self.winfo_x() + (event.x - self._drag_x)
        y = self.winfo_y() + (event.y - self._drag_y)
        self.geometry(f"+{x}+{y}")

    def apply_opacity(self):
        alpha = float(self.config_data.get("hud_opacity", 0.88))
        alpha = max(0.45, min(0.98, alpha))
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass

    def apply_position(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        pos = self.config_data.get("hud_position", "Sol Üst")
        m = 18
        if pos == "Sağ Üst":
            x, y = sw - w - m, m
        elif pos == "Sol Alt":
            x, y = m, sh - h - 64
        elif pos == "Sağ Alt":
            x, y = sw - w - m, sh - h - 64
        else:
            x, y = m, m
        self.geometry(f"+{x}+{y}")

    def rebuild(self):
        for w in self.container.winfo_children():
            w.destroy()
        self.labels.clear()
        self.graph_canvas = None

        style = self.config_data.get("hud_style", "Detaylı")
        self._bind_drag(self.container)

        if style == "Minimal":
            row = ctk.CTkFrame(self.container, fg_color="transparent")
            row.pack(padx=12, pady=7)
            self._bind_drag(row)
            lbl_fps = ctk.CTkLabel(
                row,
                text="0 FPS",
                text_color=THEME["accent_emerald"],
                font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            )
            lbl_fps.pack(side="left")
            self._bind_drag(lbl_fps)
            self.labels["fps_big"] = lbl_fps

            if self.config_data.get("hud_show_frametime", True):
                lbl_ft = ctk.CTkLabel(
                    row,
                    text="  0.0ms",
                    text_color=THEME["text_muted"],
                    font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                )
                lbl_ft.pack(side="left", pady=(4, 0))
                self._bind_drag(lbl_ft)
                self.labels["ft"] = lbl_ft

        elif style == "Kompakt":
            row = ctk.CTkFrame(self.container, fg_color="transparent")
            row.pack(padx=12, pady=7)
            self._bind_drag(row)

            dot = ctk.CTkFrame(row, width=7, height=7, corner_radius=4, fg_color=THEME["accent_indigo"])
            dot.pack(side="left", padx=(0, 8))
            dot.pack_propagate(False)

            items = []
            if self.config_data.get("hud_show_fps", True):
                items.append(("fps_compact", "FPS --", THEME["accent_emerald"]))
            if self.config_data.get("hud_show_frametime", True):
                items.append(("ft", "--ms", THEME["text_secondary"]))
            if self.config_data.get("hud_show_cpu", True):
                items.append(("cpu", "CPU --%", THEME["accent_indigo"]))
            if self.config_data.get("hud_show_ram", True):
                items.append(("ram", "RAM --%", THEME["accent_cyan"]))
            if self.config_data.get("hud_show_gpu", True):
                items.append(("gpu", "GPU --%", THEME["accent_amber"]))
            if self.config_data.get("hud_show_ping", True):
                items.append(("ping", "--ms", THEME["accent_violet"]))

            for idx, (key, txt, color) in enumerate(items):
                if idx > 0:
                    sep = ctk.CTkLabel(row, text="|", text_color="#28324B", font=ctk.CTkFont(size=11))
                    sep.pack(side="left", padx=6)
                lbl = ctk.CTkLabel(
                    row,
                    text=txt,
                    text_color=color,
                    font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                )
                lbl.pack(side="left")
                self._bind_drag(lbl)
                self.labels[key] = lbl

        else:  # Detaylı
            top = ctk.CTkFrame(self.container, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(9, 4))
            self._bind_drag(top)

            brand = ctk.CTkLabel(
                top,
                text="● MORBI HUD",
                text_color=THEME["accent_indigo"],
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            )
            brand.pack(side="left")
            self._bind_drag(brand)

            hz_lbl = ctk.CTkLabel(
                top,
                text="180Hz",
                text_color=THEME["text_muted"],
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            )
            hz_lbl.pack(side="right")
            self._bind_drag(hz_lbl)
            self.labels["hz"] = hz_lbl

            if self.config_data.get("hud_show_fps", True):
                fps_row = ctk.CTkFrame(self.container, fg_color="transparent")
                fps_row.pack(fill="x", padx=12, pady=(0, 4))
                self._bind_drag(fps_row)

                lbl_fps = ctk.CTkLabel(
                    fps_row,
                    text="0",
                    text_color=THEME["accent_emerald"],
                    font=ctk.CTkFont(family="Consolas", size=26, weight="bold"),
                )
                lbl_fps.pack(side="left")
                self._bind_drag(lbl_fps)
                self.labels["fps_num"] = lbl_fps

                meta_col = ctk.CTkFrame(fps_row, fg_color="transparent")
                meta_col.pack(side="left", padx=(8, 0))
                self._bind_drag(meta_col)

                lbl_fps_tag = ctk.CTkLabel(
                    meta_col,
                    text="FPS",
                    text_color=THEME["text_secondary"],
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    anchor="w",
                )
                lbl_fps_tag.pack(anchor="w")

                lbl_sub = ctk.CTkLabel(
                    meta_col,
                    text="0.0ms  •  1% Low: 0",
                    text_color=THEME["text_muted"],
                    font=ctk.CTkFont(family="Consolas", size=10),
                    anchor="w",
                )
                lbl_sub.pack(anchor="w")
                self._bind_drag(lbl_sub)
                self.labels["fps_sub"] = lbl_sub

            if self.config_data.get("hud_show_graph", True):
                self.graph_canvas = tk.Canvas(
                    self.container,
                    width=210,
                    height=38,
                    bg="#0F1524",
                    highlightthickness=1,
                    highlightbackground="#1E263D",
                )
                self.graph_canvas.pack(fill="x", padx=12, pady=(2, 6))
                self._bind_drag(self.graph_canvas)

            # Metrics grid
            grid = ctk.CTkFrame(self.container, fg_color="#111726", corner_radius=8)
            grid.pack(fill="x", padx=10, pady=(0, 10))
            self._bind_drag(grid)

            metrics = []
            if self.config_data.get("hud_show_cpu", True):
                metrics.append(("cpu", "CPU", THEME["accent_indigo"]))
            if self.config_data.get("hud_show_ram", True):
                metrics.append(("ram", "RAM", THEME["accent_cyan"]))
            if self.config_data.get("hud_show_gpu", True):
                metrics.append(("gpu", "GPU", THEME["accent_amber"]))
            if self.config_data.get("hud_show_ping", True):
                metrics.append(("ping", "PING", THEME["accent_violet"]))

            for idx, (key, title, color) in enumerate(metrics):
                r, c_idx = divmod(idx, 2)
                grid.grid_columnconfigure(c_idx, weight=1)
                cell = ctk.CTkFrame(grid, fg_color="transparent")
                cell.grid(row=r, column=c_idx, sticky="ew", padx=8, pady=4)
                self._bind_drag(cell)
                ctk.CTkLabel(
                    cell,
                    text=title,
                    text_color=THEME["text_muted"],
                    font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                ).pack(side="left")
                v = ctk.CTkLabel(
                    cell,
                    text="--",
                    text_color=color,
                    font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                )
                v.pack(side="right")
                self._bind_drag(v)
                self.labels[key] = v

        self.apply_position()

    def _fps_color(self, fps: float) -> str:
        if fps >= 60:
            return THEME["accent_emerald"]
        if fps >= 30:
            return THEME["accent_amber"]
        return THEME["accent_rose"]

    def update_telemetry(self, data: dict):
        try:
            fps_d = data.get("fps", {})
            gpu_d = data.get("gpu", {})
            fps = fps_d.get("fps", 0.0)
            ft = fps_d.get("frametime_ms", 0.0)
            low1 = fps_d.get("low_1pct", 0.0)
            hz = fps_d.get("refresh_hz", 60)
            col = self._fps_color(fps)

            self._fps_hist.append(fps)
            if len(self._fps_hist) > 36:
                self._fps_hist = self._fps_hist[-36:]

            if "fps_big" in self.labels:
                self.labels["fps_big"].configure(text=f"{fps:.0f} FPS", text_color=col)
            if "fps_compact" in self.labels:
                self.labels["fps_compact"].configure(text=f"FPS {fps:.0f}", text_color=col)
            if "fps_num" in self.labels:
                self.labels["fps_num"].configure(text=f"{fps:.0f}", text_color=col)
            if "fps_sub" in self.labels:
                self.labels["fps_sub"].configure(text=f"{ft:.1f}ms  •  1% Low: {low1:.0f}")
            if "ft" in self.labels:
                self.labels["ft"].configure(text=f"{ft:.1f}ms")
            if "hz" in self.labels:
                self.labels["hz"].configure(text=f"{hz:.0f}Hz")
            if "cpu" in self.labels:
                self.labels["cpu"].configure(text=f"%{data.get('cpu_percent', 0):.0f}")
            if "ram" in self.labels:
                self.labels["ram"].configure(text=f"%{data.get('ram_percent', 0):.0f}")
            if "gpu" in self.labels:
                if gpu_d.get("available"):
                    self.labels["gpu"].configure(text=f"%{gpu_d.get('usage', 0):.0f} {gpu_d.get('temp', 0):.0f}°")
                else:
                    self.labels["gpu"].configure(text="N/A")
            if "ping" in self.labels:
                p = data.get("ping_ms", 0)
                self.labels["ping"].configure(text=f"{p:.0f}ms" if p > 0 else "—")

            if self.graph_canvas is not None:
                self._draw_mini_graph(col, max(60.0, hz))
        except Exception:
            pass

    def _draw_mini_graph(self, color: str, y_max: float):
        c = self.graph_canvas
        c.delete("all")
        w = c.winfo_width() or 210
        h = c.winfo_height() or 38
        n = len(self._fps_hist)
        if n < 2:
            return
        pts = []
        for i, val in enumerate(self._fps_hist):
            x = 2 + (i / (n - 1)) * (w - 4)
            y = (h - 4) - (min(val, y_max) / max(1.0, y_max)) * (h - 8)
            pts.extend([x, y])
        fill_c = _hex_blend(color, "#0F1524", 0.22)
        poly = [2, h - 2] + pts + [w - 2, h - 2]
        c.create_polygon(poly, fill=fill_c, outline="")
        c.create_line(pts, fill=color, width=1.8, smooth=True)
