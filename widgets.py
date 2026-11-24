import tkinter as tk
import customtkinter as ctk
from config import THEME


def _hex_blend(hex1: str, hex2: str, alpha: float) -> str:
    """Blends hex1 over hex2 with alpha (0..1) to simulate translucent fills on tk.Canvas."""
    h1 = hex1.lstrip("#")
    h2 = hex2.lstrip("#")
    r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
    r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
    r = int(r1 * alpha + r2 * (1 - alpha))
    g = int(g1 * alpha + g2 * (1 - alpha))
    b = int(b1 * alpha + b2 * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


class PillBadge(ctk.CTkFrame):
    """React/Tailwind-style rounded status pill badge."""

    VARIANTS = {
        "indigo": ("#1E1F3B", "#818CF8", "#312E81"),
        "emerald": ("#0D2922", "#34D399", "#065F46"),
        "cyan": ("#0B2732", "#22D3EE", "#155E75"),
        "amber": ("#2C210D", "#FBBF24", "#78350F"),
        "rose": ("#2E121D", "#FB7185", "#881337"),
        "slate": ("#171D2B", "#94A3B8", "#273147"),
    }

    def __init__(self, master, text: str, variant: str = "slate", **kwargs):
        bg, fg, border = self.VARIANTS.get(variant, self.VARIANTS["slate"])
        super().__init__(
            master,
            fg_color=bg,
            border_color=border,
            border_width=1,
            corner_radius=999,
            **kwargs,
        )
        self.label = ctk.CTkLabel(
            self,
            text=text,
            text_color=fg,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            padx=10,
            pady=2,
        )
        self.label.pack()

    def set_state(self, text: str, variant: str = None):
        self.label.configure(text=text)
        if variant and variant in self.VARIANTS:
            bg, fg, border = self.VARIANTS[variant]
            self.configure(fg_color=bg, border_color=border)
            self.label.configure(text_color=fg)


class GlassCard(ctk.CTkFrame):
    """Shadcn/Vercel-inspired dark card container with crisp 1px border."""

    def __init__(self, master, title: str = None, subtitle: str = None, badge: tuple = None, **kwargs):
        fg_color = kwargs.pop("fg_color", THEME["bg_card"])
        border_color = kwargs.pop("border_color", THEME["border"])
        corner_radius = kwargs.pop("corner_radius", 14)
        super().__init__(
            master,
            fg_color=fg_color,
            border_color=border_color,
            border_width=1,
            corner_radius=corner_radius,
            **kwargs,
        )
        self.header_frame = None
        self.badge_widget = None
        if title:
            self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.header_frame.pack(fill="x", padx=16, pady=(14, 8))

            left = ctk.CTkFrame(self.header_frame, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)

            self.title_label = ctk.CTkLabel(
                left,
                text=title,
                text_color=THEME["text_primary"],
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                anchor="w",
            )
            self.title_label.pack(anchor="w")

            if subtitle:
                self.subtitle_label = ctk.CTkLabel(
                    left,
                    text=subtitle,
                    text_color=THEME["text_muted"],
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    anchor="w",
                )
                self.subtitle_label.pack(anchor="w")

            if badge:
                self.badge_widget = PillBadge(self.header_frame, text=badge[0], variant=badge[1])
                self.badge_widget.pack(side="right", anchor="n")


class RadialGauge(ctk.CTkFrame):
    """Custom circular ring gauge widget with tabular center readout."""

    def __init__(
        self,
        master,
        title: str,
        accent: str = THEME["accent_indigo"],
        size: int = 112,
        unit: str = "%",
        max_val: float = 100.0,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=THEME["bg_card"],
            border_color=THEME["border"],
            border_width=1,
            corner_radius=14,
            **kwargs,
        )
        self.accent = accent
        self.size = size
        self.unit = unit
        self.max_val = max_val
        self.value = 0.0

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))

        dot = ctk.CTkFrame(top, width=8, height=8, corner_radius=4, fg_color=accent)
        dot.pack(side="left", padx=(0, 7))
        dot.pack_propagate(False)

        self.title_lbl = ctk.CTkLabel(
            top,
            text=title,
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.title_lbl.pack(side="left")

        self.canvas = tk.Canvas(
            self,
            width=size,
            height=size,
            bg=THEME["bg_card"],
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(pady=(2, 2))

        self.sub_lbl = ctk.CTkLabel(
            self,
            text="—",
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        self.sub_lbl.pack(pady=(0, 10))

        self._draw_gauge(0.0)

    def _draw_gauge(self, val: float):
        self.canvas.delete("all")
        s = self.size
        pad = 12
        bbox = (pad, pad, s - pad, s - pad)

        # Background ring
        self.canvas.create_oval(bbox, outline="#1D2436", width=9)

        # Soft outer glow ring
        pct = max(0.0, min(1.0, val / max(1.0, self.max_val)))
        extent = -360.0 * pct

        if pct > 0.005:
            glow_color = _hex_blend(self.accent, THEME["bg_card"], 0.25)
            self.canvas.create_arc(
                (pad - 2, pad - 2, s - pad + 2, s - pad + 2),
                start=90,
                extent=extent,
                style=tk.ARC,
                outline=glow_color,
                width=13,
            )
            self.canvas.create_arc(
                bbox,
                start=90,
                extent=extent,
                style=tk.ARC,
                outline=self.accent,
                width=9,
            )

        # Center value
        val_txt = f"{val:.0f}{self.unit}" if self.unit == "%" else f"{val:.0f}"
        self.canvas.create_text(
            s / 2,
            s / 2 - (4 if self.unit != "%" else 0),
            text=val_txt,
            fill=THEME["text_primary"],
            font=("Consolas", 18, "bold"),
        )
        if self.unit != "%":
            self.canvas.create_text(
                s / 2,
                s / 2 + 16,
                text=self.unit,
                fill=THEME["text_muted"],
                font=("Segoe UI", 9, "bold"),
            )

    def update_value(self, value: float, subtext: str = "", accent: str = None, max_val: float = None):
        self.value = value
        if accent:
            self.accent = accent
        if max_val:
            self.max_val = max_val
        self._draw_gauge(value)
        if subtext:
            self.sub_lbl.configure(text=subtext)


class SparklineChart(ctk.CTkFrame):
    """React Recharts-style real-time multi-series area/line chart."""

    def __init__(
        self,
        master,
        series_config: list,
        height: int = 175,
        y_max: float = 100.0,
        bg_color: str = THEME["bg_card"],
        show_legend: bool = True,
        **kwargs,
    ):
        super().__init__(master, fg_color=bg_color, corner_radius=10, **kwargs)
        self.series_config = series_config  # list of {"key": str, "label": str, "color": str}
        self.y_max = y_max
        self.bg_color = bg_color
        self.last_data = {}

        if show_legend:
            self.legend_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.legend_frame.pack(fill="x", padx=6, pady=(2, 6))
            self.legend_labels = {}
            for s in series_config:
                item = ctk.CTkFrame(self.legend_frame, fg_color="transparent")
                item.pack(side="left", padx=(0, 14))
                dot = ctk.CTkFrame(item, width=9, height=9, corner_radius=5, fg_color=s["color"])
                dot.pack(side="left", padx=(0, 5))
                dot.pack_propagate(False)
                lbl = ctk.CTkLabel(
                    item,
                    text=f"{s['label']}: --",
                    text_color=THEME["text_secondary"],
                    font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                )
                lbl.pack(side="left")
                self.legend_labels[s["key"]] = lbl
        else:
            self.legend_labels = {}

        self.canvas = tk.Canvas(
            self,
            height=height,
            bg=bg_color,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

    def update_data(self, data_map: dict, y_max: float = None):
        self.last_data = data_map
        if y_max is not None:
            self.y_max = max(10.0, y_max)
        for s in self.series_config:
            k = s["key"]
            vals = data_map.get(k, [])
            if k in self.legend_labels and vals:
                unit = s.get("unit", "%")
                self.legend_labels[k].configure(text=f"{s['label']}: {vals[-1]:.0f}{unit}")
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 40 or h < 30:
            return

        pad_l, pad_r, pad_t, pad_b = 34, 10, 10, 14
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        # Horizontal gridlines (0, 25, 50, 75, 100% of y_max)
        for i in range(5):
            frac = i / 4.0
            y = pad_t + plot_h * (1.0 - frac)
            c.create_line(pad_l, y, w - pad_r, y, fill="#1B2234", dash=(2, 4))
            val = self.y_max * frac
            c.create_text(
                pad_l - 6,
                y,
                text=f"{val:.0f}",
                fill=THEME["text_muted"],
                font=("Consolas", 8),
                anchor="e",
            )

        # Draw each series (area + smooth line)
        for idx, s in enumerate(self.series_config):
            vals = self.last_data.get(s["key"], [])
            if len(vals) < 2:
                continue
            n = len(vals)
            pts = []
            for i, v in enumerate(vals):
                x = pad_l + (i / (n - 1)) * plot_w
                clamped = max(0.0, min(self.y_max, v))
                y = pad_t + plot_h * (1.0 - clamped / self.y_max)
                pts.extend([x, y])

            # Soft area fill for the primary series
            if idx == 0:
                fill_color = _hex_blend(s["color"], self.bg_color, 0.14)
                poly = [pad_l, pad_t + plot_h] + pts + [pad_l + plot_w, pad_t + plot_h]
                c.create_polygon(poly, fill=fill_color, outline="")

            c.create_line(pts, fill=s["color"], width=2.2, smooth=True)

            # Live end dot
            lx, ly = pts[-2], pts[-1]
            c.create_oval(lx - 3.5, ly - 3.5, lx + 3.5, ly + 3.5, fill=s["color"], outline=self.bg_color, width=1.5)


class NavButton(ctk.CTkButton):
    """Sidebar navigation button with React active-pill styling."""

    def __init__(self, master, text: str, command, **kwargs):
        super().__init__(
            master,
            text=f"  {text}",
            command=command,
            anchor="w",
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="transparent",
            hover_color="#151A27",
            text_color=THEME["text_secondary"],
            **kwargs,
        )

    def set_active(self, active: bool):
        if active:
            self.configure(
                fg_color="#1A2035",
                hover_color="#1E2540",
                text_color=THEME["text_primary"],
                border_width=1,
                border_color="#343F68",
            )
        else:
            self.configure(
                fg_color="transparent",
                hover_color="#151A27",
                text_color=THEME["text_secondary"],
                border_width=0,
            )


class ToggleRow(ctk.CTkFrame):
    """Clean settings toggle row with title, description, and switch."""

    def __init__(self, master, title: str, subtitle: str, initial: bool, command=None, **kwargs):
        super().__init__(
            master,
            fg_color=THEME["bg_elevated"],
            border_color=THEME["border"],
            border_width=1,
            corner_radius=10,
            **kwargs,
        )
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=14, pady=10)

        ctk.CTkLabel(
            left,
            text=title,
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            left,
            text=subtitle,
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
        ).pack(anchor="w")

        self.var = ctk.BooleanVar(value=initial)
        self.switch = ctk.CTkSwitch(
            self,
            text="",
            variable=self.var,
            command=self._on_toggle,
            width=46,
            progress_color=THEME["accent_indigo"],
            button_color="#F8FAFC",
            button_hover_color="#E2E8F0",
            fg_color="#2A3248",
        )
        self.switch.pack(side="right", padx=14)
        self._cb = command

    def _on_toggle(self):
        if self._cb:
            self._cb(self.var.get())

    def set(self, val: bool):
        self.var.set(val)
