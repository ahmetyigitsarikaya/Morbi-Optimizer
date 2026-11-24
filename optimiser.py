import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw
import pystray
import customtkinter as ctk

from config import APP_NAME, APP_VERSION, THEME, load_config, save_config
from engine import OptimizerEngine, is_admin
from overlays import FPSOverlayHUD, GameNotificationToast
from startup import is_startup_enabled, set_startup_enabled
from widgets import GlassCard, NavButton, PillBadge, RadialGauge, SparklineChart, ToggleRow


class MorbiOptimizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config_data = load_config()
        self.admin_mode = is_admin()
        self.latest_telemetry = {}
        self.active_toast = None
        self.fps_hud = None
        self.current_page = "dashboard"
        self.tray_icon = None
        self._tray_running = False

        # Window setup
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x740")
        self.minsize(980, 640)
        self.configure(fg_color=THEME["bg_root"])
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Build layout
        self._build_shell()
        self._build_pages()
        self.switch_page("dashboard")

        # Start Optimizer Engine
        self.engine = OptimizerEngine(
            config=self.config_data,
            on_telemetry=self._handle_telemetry_threadsafe,
            on_game_detected=self._handle_game_detected_threadsafe,
            on_log=self._handle_log_threadsafe,
        )
        self.engine.start()

        # Populate power plans & processes after engine initializes
        self.after(400, self._refresh_power_plans_ui)
        self.after(600, self._refresh_processes_ui)

        # Restore HUD if enabled in config
        if self.config_data.get("hud_enabled", False):
            self.after(300, lambda: self.toggle_fps_hud(True))

        # System tray
        self._setup_tray()

        # If launched with --minimized (e.g. from Windows startup), hide to tray
        if "--minimized" in sys.argv:
            self.after(250, self.hide_window)

    # =========================================================================
    # SHELL (Sidebar + Top Header + Content Container)
    # =========================================================================

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Left Sidebar ---
        self.sidebar = ctk.CTkFrame(
            self,
            width=226,
            corner_radius=0,
            fg_color=THEME["bg_sidebar"],
            border_color=THEME["border"],
            border_width=1,
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Brand Logo
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(18, 16))

        logo_box = ctk.CTkFrame(
            brand,
            width=36,
            height=36,
            corner_radius=10,
            fg_color=THEME["accent_indigo"],
        )
        logo_box.pack(side="left", padx=(0, 10))
        logo_box.pack_propagate(False)
        ctk.CTkLabel(
            logo_box,
            text="M",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        brand_txt = ctk.CTkFrame(brand, fg_color="transparent")
        brand_txt.pack(side="left")
        ctk.CTkLabel(
            brand_txt,
            text="MORBI",
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_txt,
            text=f"OPTIMIZER {APP_VERSION}",
            text_color=THEME["accent_indigo"],
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        # Divider
        ctk.CTkFrame(self.sidebar, height=1, fg_color=THEME["border"]).pack(fill="x", padx=14, pady=(0, 12))

        # Navigation items
        nav_items = [
            ("dashboard", "⚡  Genel Bakış"),
            ("gamemode", "🎮  Oyun Modu"),
            ("hud", "📊  FPS & HUD Widget"),
            ("optimizer", "🚀  Performans & Temizlik"),
            ("settings", "⚙  Ayarlar & Günlük"),
        ]
        self.nav_buttons = {}
        for key, label in nav_items:
            btn = NavButton(self.sidebar, text=label, command=lambda k=key: self.switch_page(k))
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        # Bottom live sidebar card
        bottom_card = ctk.CTkFrame(
            self.sidebar,
            fg_color=THEME["bg_card"],
            border_color=THEME["border"],
            border_width=1,
            corner_radius=12,
        )
        bottom_card.pack(side="bottom", fill="x", padx=12, pady=14)

        self.sb_status_badge = PillBadge(bottom_card, "● Sürekli Aktif", "emerald")
        self.sb_status_badge.pack(anchor="w", padx=12, pady=(10, 6))

        self.sb_freed_lbl = ctk.CTkLabel(
            bottom_card,
            text="Boşaltılan RAM: 0 MB",
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            anchor="w",
        )
        self.sb_freed_lbl.pack(fill="x", padx=12, pady=(0, 4))

        admin_txt = "🛡 Yönetici Yetkisi Aktif" if self.admin_mode else "⚠ Standart Kullanıcı Modu"
        admin_col = THEME["accent_emerald"] if self.admin_mode else THEME["accent_amber"]
        ctk.CTkLabel(
            bottom_card,
            text=admin_txt,
            text_color=admin_col,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 10))

        # --- Top Header Bar ---
        self.header = ctk.CTkFrame(
            self,
            height=60,
            corner_radius=0,
            fg_color=THEME["bg_header"],
            border_color=THEME["border"],
            border_width=1,
        )
        self.header.grid(row=0, column=1, sticky="ew")
        self.header.grid_propagate(False)

        title_wrap = ctk.CTkFrame(self.header, fg_color="transparent")
        title_wrap.pack(side="left", padx=20)

        self.page_title_lbl = ctk.CTkLabel(
            title_wrap,
            text="Genel Bakış",
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            anchor="w",
        )
        self.page_title_lbl.pack(anchor="w")

        self.page_sub_lbl = ctk.CTkLabel(
            title_wrap,
            text="Gerçek zamanlı sistem telemetrisi ve sürekli optimizasyon kontrolü",
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
        )
        self.page_sub_lbl.pack(anchor="w")

        header_actions = ctk.CTkFrame(self.header, fg_color="transparent")
        header_actions.pack(side="right", padx=16)

        self.header_mode_badge = PillBadge(header_actions, "● SİSTEM NORMAL", "slate")
        self.header_mode_badge.pack(side="left", padx=(0, 10))

        self.header_hud_btn = ctk.CTkButton(
            header_actions,
            text="📊 FPS HUD",
            width=100,
            height=34,
            corner_radius=9,
            fg_color=THEME["bg_elevated"],
            hover_color="#232B40",
            border_width=1,
            border_color=THEME["border_strong"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._toggle_hud_button,
        )
        self.header_hud_btn.pack(side="left", padx=(0, 8))

        self.header_turbo_btn = ctk.CTkButton(
            header_actions,
            text="⚡ Turbo Boost",
            width=124,
            height=34,
            corner_radius=9,
            fg_color=THEME["accent_indigo"],
            hover_color=THEME["accent_indigo_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._run_turbo_boost,
        )
        self.header_turbo_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            header_actions,
            text="Tepsiye Gizle",
            width=102,
            height=34,
            corner_radius=9,
            fg_color="transparent",
            hover_color="#1A2033",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.hide_window,
        ).pack(side="left")

        # --- Main Content Area ---
        self.content_area = ctk.CTkFrame(self, fg_color=THEME["bg_root"], corner_radius=0)
        self.content_area.grid(row=1, column=1, sticky="nsew")
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

    # =========================================================================
    # PAGES CONSTRUCTION
    # =========================================================================

    def _build_pages(self):
        self.pages = {}
        self.pages["dashboard"] = self._create_dashboard_page()
        self.pages["gamemode"] = self._create_gamemode_page()
        self.pages["hud"] = self._create_hud_page()
        self.pages["optimizer"] = self._create_optimizer_page()
        self.pages["settings"] = self._create_settings_page()

    def switch_page(self, key: str):
        self.current_page = key
        meta = {
            "dashboard": ("Genel Bakış", "Gerçek zamanlı sistem telemetrisi ve sürekli optimizasyon merkezi"),
            "gamemode": ("Oyun Modu & Bildirimler", "Otomatik oyun algılama, öncelik yükseltme ve canlı bildirim yönetimi"),
            "hud": ("FPS & Custom HUD Widget", "Oyun içi ekran üstü FPS, Frametime ve donanım widget ayarları"),
            "optimizer": ("Performans & Sistem Temizliği", "Sürekli RAM optimizasyonu, güç planları, süreç yönetimi ve temizlik"),
            "settings": ("Ayarlar & Optimizasyon Günlüğü", "Bildirim süreleri, otomasyon tercihleri ve canlı işlem kayıtları"),
        }
        title, sub = meta.get(key, ("Morbi Optimizer", ""))
        self.page_title_lbl.configure(text=title)
        self.page_sub_lbl.configure(text=sub)

        for k, btn in self.nav_buttons.items():
            btn.set_active(k == key)

        for k, frame in self.pages.items():
            if k == key:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

        if key == "optimizer":
            self._refresh_processes_ui()

    # -------------------------------------------------------------------------
    # PAGE 1: DASHBOARD
    # -------------------------------------------------------------------------

    def _create_dashboard_page(self):
        page = ctk.CTkScrollableFrame(self.content_area, fg_color=THEME["bg_root"])
        page.grid_columnconfigure(0, weight=1)

        # 1. Hero Status Banner
        hero = GlassCard(page, fg_color="#101524", border_color="#283254")
        hero.pack(fill="x", padx=18, pady=(16, 12))

        hero_inner = ctk.CTkFrame(hero, fg_color="transparent")
        hero_inner.pack(fill="x", padx=18, pady=14)

        left = ctk.CTkFrame(hero_inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        self.hero_status_lbl = ctk.CTkLabel(
            left,
            text="Sürekli Performans Motoru Aktif",
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            anchor="w",
        )
        self.hero_status_lbl.pack(anchor="w")

        self.hero_sub_lbl = ctk.CTkLabel(
            left,
            text="Arka plan RAM yönetimi, oyun algılama ve düşük gecikme motoru çalışıyor.",
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            anchor="w",
        )
        self.hero_sub_lbl.pack(anchor="w", pady=(2, 8))

        pills = ctk.CTkFrame(left, fg_color="transparent")
        pills.pack(anchor="w")
        self.pill_power = PillBadge(pills, "⚡ Güç Planı: Yükleniyor", "indigo")
        self.pill_power.pack(side="left", padx=(0, 8))
        self.pill_timer = PillBadge(pills, "⏱ Zamanlayıcı: Standart", "slate")
        self.pill_timer.pack(side="left", padx=(0, 8))
        self.pill_game = PillBadge(pills, "🎮 Oyun Bekleniyor", "slate")
        self.pill_game.pack(side="left")

        right_btns = ctk.CTkFrame(hero_inner, fg_color="transparent")
        right_btns.pack(side="right", padx=(12, 0))

        ctk.CTkButton(
            right_btns,
            text="⚡ Turbo Boost",
            width=136,
            height=38,
            corner_radius=10,
            fg_color=THEME["accent_indigo"],
            hover_color=THEME["accent_indigo_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._run_turbo_boost,
        ).pack(pady=(0, 6))

        ctk.CTkButton(
            right_btns,
            text="🧹 RAM Temizle",
            width=136,
            height=34,
            corner_radius=10,
            fg_color=THEME["bg_elevated"],
            hover_color="#232B42",
            border_width=1,
            border_color=THEME["border_strong"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._run_manual_ram_clean,
        ).pack()

        # 2. 4 Radial KPI Gauges Row
        gauges_row = ctk.CTkFrame(page, fg_color="transparent")
        gauges_row.pack(fill="x", padx=18, pady=(0, 12))
        for i in range(4):
            gauges_row.grid_columnconfigure(i, weight=1, uniform="kpi")

        self.gauge_cpu = RadialGauge(gauges_row, "İŞLEMCİ (CPU)", accent=THEME["accent_indigo"], unit="%")
        self.gauge_cpu.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.gauge_ram = RadialGauge(gauges_row, "BELLEK (RAM)", accent=THEME["accent_cyan"], unit="%")
        self.gauge_ram.grid(row=0, column=1, sticky="nsew", padx=4)

        self.gauge_gpu = RadialGauge(gauges_row, "EKRAN KARTI (GPU)", accent=THEME["accent_amber"], unit="%")
        self.gauge_gpu.grid(row=0, column=2, sticky="nsew", padx=4)

        self.gauge_fps = RadialGauge(gauges_row, "ANLIK FPS", accent=THEME["accent_emerald"], unit="FPS", max_val=180.0)
        self.gauge_fps.grid(row=0, column=3, sticky="nsew", padx=(8, 0))

        # 3. Charts & Live Stats Split Row
        mid_row = ctk.CTkFrame(page, fg_color="transparent")
        mid_row.pack(fill="x", padx=18, pady=(0, 12))
        mid_row.grid_columnconfigure(0, weight=3)
        mid_row.grid_columnconfigure(1, weight=2)

        # Left column: Live Telemetry Chart + FPS Chart
        left_col = ctk.CTkFrame(mid_row, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        chart_card = GlassCard(
            left_col,
            title="Canlı Sistem Telemetrisi",
            subtitle="Son 60 saniyelik CPU, RAM ve GPU kullanım grafiği",
            badge=("● 1Hz CANLI", "emerald"),
        )
        chart_card.pack(fill="x", pady=(0, 12))

        self.sys_chart = SparklineChart(
            chart_card,
            series_config=[
                {"key": "cpu", "label": "CPU", "color": THEME["accent_indigo"], "unit": "%"},
                {"key": "ram", "label": "RAM", "color": THEME["accent_cyan"], "unit": "%"},
                {"key": "gpu", "label": "GPU", "color": THEME["accent_amber"], "unit": "%"},
            ],
            height=155,
            y_max=100.0,
        )
        self.sys_chart.pack(fill="x", padx=12, pady=(0, 12))

        fps_chart_card = GlassCard(
            left_col,
            title="Canlı FPS & Kare Zamanı Grafiği",
            subtitle="Windows DWM gerçek zamanlı kare hızı takibi",
            badge=("180Hz", "cyan"),
        )
        fps_chart_card.pack(fill="x")
        self.fps_chart_card = fps_chart_card

        self.fps_chart = SparklineChart(
            fps_chart_card,
            series_config=[
                {"key": "fps", "label": "FPS", "color": THEME["accent_emerald"], "unit": ""},
            ],
            height=120,
            y_max=180.0,
        )
        self.fps_chart.pack(fill="x", padx=12, pady=(0, 12))

        # Right column: Live Details + Mini Activity Feed
        right_col = ctk.CTkFrame(mid_row, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew")

        details_card = GlassCard(right_col, title="Anlık Donanım & Ağ", subtitle="Canlı I/O ve gecikme verileri")
        details_card.pack(fill="x", pady=(0, 12))

        self.detail_rows = {}
        detail_specs = [
            ("gpu_name", "GPU Modeli"),
            ("vram", "VRAM Kullanımı"),
            ("net", "Ağ (İndirme / Yükleme)"),
            ("disk", "Disk (Okuma / Yazma)"),
            ("ping", "Ağ Gecikmesi (Ping)"),
            ("procs", "Aktif İşlem Sayısı"),
            ("freed", "Oturumda Boşaltılan RAM"),
        ]
        for key, label in detail_specs:
            r = ctk.CTkFrame(details_card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(
                r,
                text=label,
                text_color=THEME["text_muted"],
                font=ctk.CTkFont(family="Segoe UI", size=12),
            ).pack(side="left")
            val = ctk.CTkLabel(
                r,
                text="—",
                text_color=THEME["text_primary"],
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            )
            val.pack(side="right")
            self.detail_rows[key] = val
        ctk.CTkFrame(details_card, height=8, fg_color="transparent").pack()

        feed_card = GlassCard(right_col, title="Son Optimizasyonlar", subtitle="Otomatik motor günlüğü")
        feed_card.pack(fill="both", expand=True)

        self.dash_log_box = ctk.CTkTextbox(
            feed_card,
            height=145,
            fg_color="#0B0E16",
            border_color=THEME["border"],
            border_width=1,
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=10,
        )
        self.dash_log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.dash_log_box.configure(state="disabled")

        return page

    # -------------------------------------------------------------------------
    # PAGE 2: GAME MODE & NOTIFICATIONS
    # -------------------------------------------------------------------------

    def _create_gamemode_page(self):
        page = ctk.CTkScrollableFrame(self.content_area, fg_color=THEME["bg_root"])

        # Active game status card
        active_card = GlassCard(
            page,
            title="Oyun Algılama & Canlı Bildirim Merkezi",
            subtitle="Desteklenen bir oyun açıldığında otomatik optimize edilir ve ekrana 12 saniyelik canlı bildirim gönderilir",
            badge=("HAZIR", "indigo"),
        )
        active_card.pack(fill="x", padx=18, pady=(16, 12))
        self.gm_status_card = active_card

        body = ctk.CTkFrame(active_card, fg_color=THEME["bg_elevated"], corner_radius=12, border_width=1, border_color=THEME["border"])
        body.pack(fill="x", padx=16, pady=(4, 14))

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=14, pady=12)

        self.gm_active_title = ctk.CTkLabel(
            left,
            text="Şu anda aktif bir oyun algılanmadı",
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w",
        )
        self.gm_active_title.pack(anchor="w")

        self.gm_active_sub = ctk.CTkLabel(
            left,
            text="Oyun başladığında CPU önceliği, güç planı, 1ms zamanlayıcı ve RAM temizliği otomatik devreye girer.",
            text_color=THEME["text_muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
        )
        self.gm_active_sub.pack(anchor="w", pady=(2, 0))

        ctk.CTkButton(
            body,
            text="🔔 Oyun Bildirimini Test Et",
            width=185,
            height=36,
            corner_radius=10,
            fg_color=THEME["accent_indigo"],
            hover_color=THEME["accent_indigo_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._trigger_test_game_toast,
        ).pack(side="right", padx=14, pady=12)

        # Automation toggles
        toggles_card = GlassCard(page, title="Otomatik Oyun Optimizasyonları", subtitle="Oyun yakalandığında uygulanacak yüksek performans adımları")
        toggles_card.pack(fill="x", padx=18, pady=(0, 12))

        toggle_defs = [
            ("auto_game_mode", "Otomatik Oyun Modu", "Arka planda çalışan oyunları 2 saniyede bir otomatik algılar."),
            ("game_toast_enabled", "Oyun Yakalandı Bildirimi (10–15 sn)", "Oyun başladığında anlık CPU, RAM, GPU ve FPS değerleriyle şık bildirim gösterir."),
            ("game_high_priority", "Yüksek CPU & I/O Önceliği", "Oyun sürecini HIGH_PRIORITY_CLASS ve yüksek disk I/O önceliğine taşır."),
            ("game_high_perf_power", "Otomatik Yüksek Performans Güç Planı", "Oyun açıldığında güç planını Yüksek/Ultra Performansa geçirir, çıkışta geri yükler."),
            ("game_timer_resolution", "1ms Düşük Gecikme Zamanlayıcısı", "Windows sistem zamanlayıcısını 1ms hassasiyete alarak kare kararlılığını artırır."),
            ("game_throttle_background", "Arka Plan Uygulamalarını Kısıtla", "Oyun sırasında tarayıcı ve güncelleyicilerin önceliğini düşürüp RAM'ini boşaltır."),
        ]
        for cfg_key, t_title, t_sub in toggle_defs:
            row = ToggleRow(
                toggles_card,
                title=t_title,
                subtitle=t_sub,
                initial=bool(self.config_data.get(cfg_key, True)),
                command=lambda v, k=cfg_key: self._set_cfg(k, v),
            )
            row.pack(fill="x", padx=16, pady=4)
        ctk.CTkFrame(toggles_card, height=8, fg_color="transparent").pack()

        # Custom Game Library
        lib_card = GlassCard(
            page,
            title="Oyun Kütüphanesi",
            subtitle=f"{len(self.config_data.get('known_games', []))} yerleşik oyun destekleniyor — kendi oyunlarınızı (.exe) ekleyebilirsiniz",
        )
        lib_card.pack(fill="x", padx=18, pady=(0, 18))

        add_row = ctk.CTkFrame(lib_card, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(4, 10))

        self.custom_game_entry = ctk.CTkEntry(
            add_row,
            placeholder_text="Örn: oyunadi.exe",
            height=36,
            corner_radius=9,
            fg_color=THEME["bg_input"],
            border_color=THEME["border_strong"],
            text_color=THEME["text_primary"],
        )
        self.custom_game_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            add_row,
            text="📂 Gözat (.exe)",
            width=115,
            height=36,
            corner_radius=9,
            fg_color=THEME["bg_elevated"],
            hover_color="#232C44",
            border_width=1,
            border_color=THEME["border_strong"],
            command=self._browse_custom_game,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            add_row,
            text="+ Ekle",
            width=86,
            height=36,
            corner_radius=9,
            fg_color=THEME["accent_indigo"],
            hover_color=THEME["accent_indigo_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._add_custom_game,
        ).pack(side="left")

        self.custom_games_list_frame = ctk.CTkFrame(lib_card, fg_color="transparent")
        self.custom_games_list_frame.pack(fill="x", padx=16, pady=(0, 14))
        self._render_custom_games()

        return page

    # -------------------------------------------------------------------------
    # PAGE 3: FPS & HUD WIDGET
    # -------------------------------------------------------------------------

    def _create_hud_page(self):
        page = ctk.CTkScrollableFrame(self.content_area, fg_color=THEME["bg_root"])

        # Live FPS telemetry summary card
        fps_card = GlassCard(
            page,
            title="Canlı FPS & Kare Analizi",
            subtitle="Windows DWM gerçek zamanlı kare hızı, frametime ve ekran yenileme verileri",
            badge=("CANLI", "emerald"),
        )
        fps_card.pack(fill="x", padx=18, pady=(16, 12))

        grid = ctk.CTkFrame(fps_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(4, 14))
        for i in range(5):
            grid.grid_columnconfigure(i, weight=1, uniform="fpsstat")

        self.hud_page_stats = {}
        stat_defs = [
            ("fps", "ANLIK FPS", THEME["accent_emerald"]),
            ("avg", "ORTALAMA FPS", THEME["accent_cyan"]),
            ("low1", "1% LOW FPS", THEME["accent_amber"]),
            ("ft", "FRAMETIME", THEME["accent_indigo"]),
            ("hz", "EKRAN HIZI", THEME["text_primary"]),
        ]
        for idx, (k, lbl, col) in enumerate(stat_defs):
            box = ctk.CTkFrame(grid, fg_color=THEME["bg_elevated"], corner_radius=12, border_width=1, border_color=THEME["border"])
            box.grid(row=0, column=idx, sticky="nsew", padx=4)
            ctk.CTkLabel(box, text=lbl, text_color=THEME["text_muted"], font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(10, 2))
            v = ctk.CTkLabel(box, text="--", text_color=col, font=ctk.CTkFont(family="Consolas", size=20, weight="bold"))
            v.pack(pady=(0, 10))
            self.hud_page_stats[k] = v

        # HUD Controls
        ctrl_card = GlassCard(page, title="Ekran Üstü Custom FPS HUD Widget", subtitle="Oyun veya masaüstü üzerinde daima üstte duran sürüklenebilir performans widget'ı")
        ctrl_card.pack(fill="x", padx=18, pady=(0, 12))

        self.hud_master_toggle = ToggleRow(
            ctrl_card,
            title="FPS & Performans HUD Widget'ını Göster",
            subtitle="Ekranın köşesinde canlı FPS, CPU, RAM, GPU ve Ping değerlerini gösterir (fareyle sürüklenebilir).",
            initial=bool(self.config_data.get("hud_enabled", False)),
            command=self.toggle_fps_hud,
        )
        self.hud_master_toggle.pack(fill="x", padx=16, pady=(4, 10))

        # Style & Position row
        opt_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        opt_row.pack(fill="x", padx=16, pady=(0, 10))
        opt_row.grid_columnconfigure(0, weight=1)
        opt_row.grid_columnconfigure(1, weight=1)

        style_box = ctk.CTkFrame(opt_row, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        style_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(style_box, text="Widget Görünüm Stili", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(10, 6))
        self.hud_style_seg = ctk.CTkSegmentedButton(
            style_box,
            values=["Detaylı", "Kompakt", "Minimal"],
            selected_color=THEME["accent_indigo"],
            selected_hover_color=THEME["accent_indigo_hover"],
            unselected_color="#121622",
            command=self._on_hud_style_change,
        )
        self.hud_style_seg.set(self.config_data.get("hud_style", "Detaylı"))
        self.hud_style_seg.pack(fill="x", padx=14, pady=(0, 12))

        pos_box = ctk.CTkFrame(opt_row, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        pos_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(pos_box, text="Ekran Konumu", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(10, 6))
        self.hud_pos_seg = ctk.CTkSegmentedButton(
            pos_box,
            values=["Sol Üst", "Sağ Üst", "Sol Alt", "Sağ Alt"],
            selected_color=THEME["accent_indigo"],
            selected_hover_color=THEME["accent_indigo_hover"],
            unselected_color="#121622",
            command=self._on_hud_pos_change,
        )
        self.hud_pos_seg.set(self.config_data.get("hud_position", "Sol Üst"))
        self.hud_pos_seg.pack(fill="x", padx=14, pady=(0, 12))

        # Opacity slider
        op_box = ctk.CTkFrame(ctrl_card, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        op_box.pack(fill="x", padx=16, pady=(0, 10))
        op_top = ctk.CTkFrame(op_box, fg_color="transparent")
        op_top.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(op_top, text="Widget Saydamlığı (Opaklık)", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.hud_opacity_lbl = ctk.CTkLabel(
            op_top,
            text=f"%{int(self.config_data.get('hud_opacity', 0.88) * 100)}",
            text_color=THEME["accent_cyan"],
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.hud_opacity_lbl.pack(side="right")

        op_slider = ctk.CTkSlider(
            op_box,
            from_=0.45,
            to=0.98,
            number_of_steps=53,
            progress_color=THEME["accent_indigo"],
            button_color="#F8FAFC",
            command=self._on_hud_opacity_change,
        )
        op_slider.set(self.config_data.get("hud_opacity", 0.88))
        op_slider.pack(fill="x", padx=14, pady=(2, 12))

        ToggleRow(
            ctrl_card,
            title="Widget Konumunu Kilitle",
            subtitle="Aktifken HUD yanlışlıkla fare ile sürüklenmez.",
            initial=bool(self.config_data.get("hud_locked", False)),
            command=lambda v: self._set_cfg("hud_locked", v),
        ).pack(fill="x", padx=16, pady=(0, 14))

        # Metric Toggles
        metrics_card = GlassCard(page, title="HUD İçeriği (Gösterilecek Metrikler)", subtitle="Widget üzerinde hangi verilerin görüneceğini özelleştirin")
        metrics_card.pack(fill="x", padx=18, pady=(0, 18))

        metric_defs = [
            ("hud_show_fps", "FPS Sayacı", "Anlık kare hızını renk kodlu olarak gösterir."),
            ("hud_show_frametime", "Frametime (ms)", "Kare başına geçen milisaniye süresini gösterir."),
            ("hud_show_graph", "Canlı FPS Mini Grafiği", "Detaylı modda anlık FPS dalgalanma grafiğini çizer."),
            ("hud_show_cpu", "CPU Kullanımı", "Toplam işlemci kullanım yüzdesini gösterir."),
            ("hud_show_ram", "RAM Kullanımı", "Bellek doluluk yüzdesini gösterir."),
            ("hud_show_gpu", "GPU Kullanımı & Sıcaklık", "NVIDIA ekran kartı kullanım % ve °C sıcaklığını gösterir."),
            ("hud_show_ping", "Ağ Ping (ms)", "1.1.1.1 üzerinden canlı ağ gecikmesini gösterir."),
        ]
        for k, t, s in metric_defs:
            ToggleRow(
                metrics_card,
                title=t,
                subtitle=s,
                initial=bool(self.config_data.get(k, True)),
                command=lambda v, key=k: self._on_hud_metric_toggle(key, v),
            ).pack(fill="x", padx=16, pady=4)
        ctk.CTkFrame(metrics_card, height=8, fg_color="transparent").pack()

        return page

    # -------------------------------------------------------------------------
    # PAGE 4: PERFORMANCE & CLEANER
    # -------------------------------------------------------------------------

    def _create_optimizer_page(self):
        page = ctk.CTkScrollableFrame(self.content_area, fg_color=THEME["bg_root"])

        # 1. One-Click Boost Tools
        tools_card = GlassCard(page, title="Tek Tıkla Yüksek Performans Araçları", subtitle="Anında bellek, ağ, zamanlayıcı ve geçici dosya optimizasyonu")
        tools_card.pack(fill="x", padx=18, pady=(16, 12))

        t_grid = ctk.CTkFrame(tools_card, fg_color="transparent")
        t_grid.pack(fill="x", padx=16, pady=(4, 14))
        for i in range(4):
            t_grid.grid_columnconfigure(i, weight=1, uniform="tool")

        actions = [
            ("🧹 RAM Boşalt", "Arka plan belleğini temizler", THEME["accent_indigo"], self._run_manual_ram_clean),
            ("🗑 Temp Temizle", "%TEMP% gereksiz dosyaları siler", THEME["accent_cyan"], self._run_temp_clean),
            ("🌐 DNS Temizle", "Ağ önbelleğini sıfırlar", THEME["accent_emerald"], self._run_dns_flush),
            ("⏱ 1ms Timer", "Düşük gecikme modunu aç/kapa", THEME["accent_violet"], self._toggle_timer_manual),
        ]
        for idx, (title, desc, col, cmd) in enumerate(actions):
            box = ctk.CTkFrame(t_grid, fg_color=THEME["bg_elevated"], corner_radius=12, border_width=1, border_color=THEME["border"])
            box.grid(row=0, column=idx, sticky="nsew", padx=4)
            ctk.CTkLabel(box, text=title, text_color=THEME["text_primary"], font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(12, 2))
            ctk.CTkLabel(box, text=desc, text_color=THEME["text_muted"], font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(0, 10))
            ctk.CTkButton(
                box,
                text="Uygula",
                height=30,
                corner_radius=8,
                fg_color=col,
                hover_color=THEME["accent_indigo_hover"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=cmd,
            ).pack(fill="x", padx=12, pady=(0, 12))

        self.tool_feedback_lbl = ctk.CTkLabel(
            tools_card,
            text="",
            text_color=THEME["accent_emerald"],
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            anchor="w",
        )
        self.tool_feedback_lbl.pack(fill="x", padx=18, pady=(0, 8))

        # 2. Continuous Optimization Controls
        cont_card = GlassCard(page, title="Sürekli Performans Arttırma Ayarları", subtitle="Arka planda kesintisiz çalışan akıllı RAM ve sistem optimizasyonu")
        cont_card.pack(fill="x", padx=18, pady=(0, 12))

        ToggleRow(
            cont_card,
            title="Sürekli Optimizasyon Motoru",
            subtitle="Sistem kaynaklarını sürekli izler, gerektiğinde otomatik optimizasyon uygular.",
            initial=bool(self.config_data.get("continuous_optimization", True)),
            command=lambda v: self._set_cfg("continuous_optimization", v),
        ).pack(fill="x", padx=16, pady=4)

        ToggleRow(
            cont_card,
            title="Akıllı Otomatik RAM Temizliği",
            subtitle="RAM kullanımı eşiği geçtiğinde veya belirli aralıklarla kullanılmayan belleği boşaltır.",
            initial=bool(self.config_data.get("auto_ram_clean", True)),
            command=lambda v: self._set_cfg("auto_ram_clean", v),
        ).pack(fill="x", padx=16, pady=4)

        # RAM threshold slider
        sl_box = ctk.CTkFrame(cont_card, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        sl_box.pack(fill="x", padx=16, pady=(6, 10))
        sl_top = ctk.CTkFrame(sl_box, fg_color="transparent")
        sl_top.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(sl_top, text="Otomatik RAM Temizleme Eşiği", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.ram_thresh_lbl = ctk.CTkLabel(
            sl_top,
            text=f"%{int(self.config_data.get('ram_threshold_percent', 75))}",
            text_color=THEME["accent_cyan"],
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.ram_thresh_lbl.pack(side="right")

        ram_slider = ctk.CTkSlider(
            sl_box,
            from_=55,
            to=95,
            number_of_steps=40,
            progress_color=THEME["accent_cyan"],
            button_color="#F8FAFC",
            command=self._on_ram_thresh_change,
        )
        ram_slider.set(self.config_data.get("ram_threshold_percent", 75))
        ram_slider.pack(fill="x", padx=14, pady=(2, 12))

        # Periodic clean interval
        int_box = ctk.CTkFrame(cont_card, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        int_box.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(int_box, text="Periyodik Sürekli Temizlik Aralığı", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(10, 6))
        int_map = {60: "1 Dakika", 180: "3 Dakika", 300: "5 Dakika", 600: "10 Dakika"}
        cur_int = int_map.get(int(self.config_data.get("auto_clean_interval_sec", 180)), "3 Dakika")
        int_seg = ctk.CTkSegmentedButton(
            int_box,
            values=["1 Dakika", "3 Dakika", "5 Dakika", "10 Dakika"],
            selected_color=THEME["accent_indigo"],
            selected_hover_color=THEME["accent_indigo_hover"],
            unselected_color="#121622",
            command=self._on_clean_interval_change,
        )
        int_seg.set(cur_int)
        int_seg.pack(fill="x", padx=14, pady=(0, 12))

        # 3. Power Plans Card
        self.power_card = GlassCard(page, title="Windows Güç Planları", subtitle="Yüksek veya Ultra Performans modları arasında tek tıkla geçiş yapın")
        self.power_card.pack(fill="x", padx=18, pady=(0, 12))
        self.power_plans_container = ctk.CTkFrame(self.power_card, fg_color="transparent")
        self.power_plans_container.pack(fill="x", padx=16, pady=(0, 14))

        # 4. Top Processes Manager
        proc_card = GlassCard(page, title="En Çok RAM Kullanan Süreçler", subtitle="İstediğiniz uygulamanın belleğini anında boşaltın veya önceliğini düşürün")
        proc_card.pack(fill="x", padx=18, pady=(0, 18))

        p_top = ctk.CTkFrame(proc_card, fg_color="transparent")
        p_top.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(
            p_top,
            text="↻ Listeyi Yenile",
            width=120,
            height=30,
            corner_radius=8,
            fg_color=THEME["bg_elevated"],
            hover_color="#232B42",
            border_width=1,
            border_color=THEME["border_strong"],
            command=self._refresh_processes_ui,
        ).pack(side="right")

        self.proc_list_frame = ctk.CTkFrame(proc_card, fg_color="transparent")
        self.proc_list_frame.pack(fill="x", padx=16, pady=(0, 14))

        return page

    # -------------------------------------------------------------------------
    # PAGE 5: SETTINGS & LOGS
    # -------------------------------------------------------------------------

    def _create_settings_page(self):
        page = ctk.CTkScrollableFrame(self.content_area, fg_color=THEME["bg_root"])

        # Windows Startup Card
        startup_card = GlassCard(
            page,
            title="Windows Başlangıcı & Otomatik Yönetici",
            subtitle="Bilgisayar açıldığında Morbi Optimizer otomatik olarak yönetici yetkisiyle başlatılır",
            badge=("YÖNETİCİ" if self.admin_mode else "STANDART", "emerald" if self.admin_mode else "amber"),
        )
        startup_card.pack(fill="x", padx=18, pady=(16, 12))

        actual_startup = is_startup_enabled()
        self.config_data["start_with_windows"] = actual_startup

        self.startup_toggle = ToggleRow(
            startup_card,
            title="Windows ile Otomatik Başlat (Görev Zamanlayıcı)",
            subtitle="Oturum açıldığında UAC engeline takılmadan otomatik olarak yönetici yetkisiyle başlar.",
            initial=actual_startup,
            command=self._on_startup_toggle,
        )
        self.startup_toggle.pack(fill="x", padx=16, pady=4)

        self.startup_min_toggle = ToggleRow(
            startup_card,
            title="Başlangıçta Tepsiye Gizli Başlat (--minimized)",
            subtitle="Windows açıldığında pencere ekranda açılmaz, doğrudan sistem tepsisinde çalışır.",
            initial=bool(self.config_data.get("start_minimized", True)),
            command=self._on_startup_min_toggle,
        )
        self.startup_min_toggle.pack(fill="x", padx=16, pady=4)

        self.startup_feedback_lbl = ctk.CTkLabel(
            startup_card,
            text="✓ Başlangıçta otomatik başlatma aktif." if actual_startup else "○ Başlangıçta otomatik başlatma kapalı.",
            text_color=THEME["accent_emerald"] if actual_startup else THEME["text_muted"],
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            anchor="w",
        )
        self.startup_feedback_lbl.pack(fill="x", padx=18, pady=(4, 12))

        notif_card = GlassCard(page, title="Bildirim Ayarları", subtitle="Oyun yakalandığında gösterilen canlı bildirim penceresini özelleştirin")
        notif_card.pack(fill="x", padx=18, pady=(0, 12))

        dur_box = ctk.CTkFrame(notif_card, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        dur_box.pack(fill="x", padx=16, pady=(4, 10))
        d_top = ctk.CTkFrame(dur_box, fg_color="transparent")
        d_top.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(d_top, text="Bildirim Ekranda Kalma Süresi", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.toast_dur_lbl = ctk.CTkLabel(
            d_top,
            text=f"{int(self.config_data.get('toast_duration_sec', 12))} saniye",
            text_color=THEME["accent_emerald"],
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.toast_dur_lbl.pack(side="right")

        dur_slider = ctk.CTkSlider(
            dur_box,
            from_=5,
            to=20,
            number_of_steps=15,
            progress_color=THEME["accent_emerald"],
            button_color="#F8FAFC",
            command=self._on_toast_dur_change,
        )
        dur_slider.set(self.config_data.get("toast_duration_sec", 12))
        dur_slider.pack(fill="x", padx=14, pady=(2, 12))

        pos_row = ctk.CTkFrame(notif_card, fg_color=THEME["bg_elevated"], corner_radius=10, border_width=1, border_color=THEME["border"])
        pos_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(pos_row, text="Bildirim Konumu", text_color=THEME["text_primary"], font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(10, 6))
        pos_seg = ctk.CTkSegmentedButton(
            pos_row,
            values=["Sağ Üst", "Sağ Alt", "Sol Üst", "Sol Alt"],
            selected_color=THEME["accent_indigo"],
            selected_hover_color=THEME["accent_indigo_hover"],
            unselected_color="#121622",
            command=lambda v: self._set_cfg("toast_position", v),
        )
        pos_seg.set(self.config_data.get("toast_position", "Sağ Üst"))
        pos_seg.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkButton(
            notif_card,
            text="🔔 Örnek Oyun Bildirimi Göster",
            width=210,
            height=34,
            corner_radius=9,
            fg_color=THEME["accent_indigo"],
            hover_color=THEME["accent_indigo_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._trigger_test_game_toast,
        ).pack(anchor="w", padx=16, pady=(0, 14))

        # Full Logs Terminal
        log_card = GlassCard(page, title="Canlı Optimizasyon Günlüğü", subtitle="Motorun gerçekleştirdiği tüm performans ve oyun modu işlemleri")
        log_card.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.full_log_box = ctk.CTkTextbox(
            log_card,
            height=290,
            fg_color="#0A0D14",
            border_color=THEME["border"],
            border_width=1,
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=10,
        )
        self.full_log_box.pack(fill="both", expand=True, padx=16, pady=(4, 10))
        self.full_log_box.configure(state="disabled")

        ctk.CTkButton(
            log_card,
            text="Günlüğü Temizle",
            width=130,
            height=30,
            corner_radius=8,
            fg_color=THEME["bg_elevated"],
            hover_color="#232B42",
            command=self._clear_logs,
        ).pack(anchor="e", padx=16, pady=(0, 14))

        return page

    # =========================================================================
    # ENGINE CALLBACKS (THREAD-SAFE UI UPDATES)
    # =========================================================================

    def _handle_telemetry_threadsafe(self, data: dict):
        self.after(0, lambda d=data: self._update_ui_from_telemetry(d))

    def _handle_game_detected_threadsafe(self, payload: dict):
        self.after(0, lambda p=payload: self.show_game_toast(p))

    def _handle_log_threadsafe(self, entry: dict):
        self.after(0, lambda e=entry: self._append_log_entry(e))

    def _update_ui_from_telemetry(self, data: dict):
        self.latest_telemetry = data
        eng = data.get("engine", {})
        gpu = data.get("gpu", {})
        fps_d = data.get("fps", {})
        hist = data.get("history", {})

        # 1. Update Gauges
        cpu = data.get("cpu_percent", 0.0)
        cpu_col = THEME["accent_rose"] if cpu >= 85 else (THEME["accent_amber"] if cpu >= 65 else THEME["accent_indigo"])
        self.gauge_cpu.update_value(cpu, f"{data.get('cpu_mhz', 0):.0f} MHz • {data.get('cpu_cores', 0)} Çekirdek", accent=cpu_col)

        ram = data.get("ram_percent", 0.0)
        ram_col = THEME["accent_rose"] if ram >= 85 else (THEME["accent_amber"] if ram >= 70 else THEME["accent_cyan"])
        self.gauge_ram.update_value(ram, f"{data.get('ram_used_gb', 0):.1f} / {data.get('ram_total_gb', 0):.1f} GB", accent=ram_col)

        if gpu.get("available"):
            g_use = gpu.get("usage", 0.0)
            g_col = THEME["accent_rose"] if gpu.get("temp", 0) >= 82 else THEME["accent_amber"]
            self.gauge_gpu.update_value(g_use, f"{gpu.get('temp', 0):.0f}°C • {gpu.get('vram_used', 0):.0f} MiB", accent=g_col)
        else:
            self.gauge_gpu.update_value(0.0, "GPU Algılanamadı", accent=THEME["text_muted"])

        fps_val = fps_d.get("fps", 0.0)
        hz = max(60.0, fps_d.get("refresh_hz", 60.0))
        fps_col = THEME["accent_emerald"] if fps_val >= 60 else (THEME["accent_amber"] if fps_val >= 30 else THEME["accent_rose"])
        self.gauge_fps.update_value(fps_val, f"{fps_d.get('frametime_ms', 0):.1f}ms • {hz:.0f}Hz", accent=fps_col, max_val=hz)

        # 2. Update Charts
        if self.current_page == "dashboard":
            self.sys_chart.update_data(hist, y_max=100.0)
            self.fps_chart.update_data(hist, y_max=hz)
            if self.fps_chart_card.badge_widget:
                self.fps_chart_card.badge_widget.set_state(f"{hz:.0f}Hz • Ort {fps_d.get('avg_fps', 0):.0f}", "cyan")

        # 3. Update Detail Rows
        self.detail_rows["gpu_name"].configure(text=gpu.get("name", "—")[:26])
        if gpu.get("available"):
            self.detail_rows["vram"].configure(text=f"{gpu.get('vram_used', 0):.0f} / {gpu.get('vram_total', 0):.0f} MiB")
        else:
            self.detail_rows["vram"].configure(text="—")
        self.detail_rows["net"].configure(text=f"↓{data.get('net_down_mbps', 0):.1f} / ↑{data.get('net_up_mbps', 0):.1f} Mbps")
        self.detail_rows["disk"].configure(text=f"R:{data.get('disk_read_mbs', 0):.1f} / W:{data.get('disk_write_mbs', 0):.1f} MB/s")
        ping_v = data.get("ping_ms", 0.0)
        self.detail_rows["ping"].configure(text=f"{ping_v:.0f} ms" if ping_v > 0 else "—")
        self.detail_rows["procs"].configure(text=str(data.get("proc_count", 0)))
        freed_total = eng.get("total_ram_freed_mb", 0.0)
        self.detail_rows["freed"].configure(text=f"+{freed_total:.1f} MB")

        # 4. Sidebar & Header Status Pills
        self.sb_freed_lbl.configure(text=f"Boşaltılan RAM: +{freed_total:.0f} MB")
        if eng.get("continuous_on"):
            self.sb_status_badge.set_state("● Sürekli Aktif", "emerald")
        else:
            self.sb_status_badge.set_state("○ Duraklatıldı", "slate")

        self.pill_power.set_state(f"⚡ {eng.get('power_plan', 'Dengeli')[:24]}", "indigo")
        if eng.get("timer_1ms"):
            self.pill_timer.set_state("⏱ Zamanlayıcı: 1ms", "cyan")
        else:
            self.pill_timer.set_state("⏱ Zamanlayıcı: Standart", "slate")

        if eng.get("game_mode"):
            gname = eng.get("game_name", "Oyun")
            gpid = eng.get("game_pid", "-")
            self.header_mode_badge.set_state(f"🎮 {gname[:18]}", "emerald")
            self.pill_game.set_state(f"🎮 {gname} (PID {gpid})", "emerald")
            self.hero_status_lbl.configure(text=f"Oyun Modu Aktif — {gname} Optimize Ediliyor")
            self.gm_active_title.configure(text=f"🎮 {gname} çalışıyor (PID: {gpid})")
            self.gm_active_sub.configure(text="Yüksek CPU/I/O önceliği, 1ms zamanlayıcı ve arka plan koruması aktif.")
            if self.gm_status_card.badge_widget:
                self.gm_status_card.badge_widget.set_state("AKTİF", "emerald")
        else:
            if eng.get("turbo_mode"):
                self.header_mode_badge.set_state("⚡ TURBO AKTİF", "indigo")
            else:
                self.header_mode_badge.set_state("● SİSTEM OPTİMİZE", "cyan")
            self.pill_game.set_state("🎮 Oyun Bekleniyor", "slate")
            self.hero_status_lbl.configure(text=eng.get("status_msg", "Sürekli Performans Motoru Aktif"))
            self.gm_active_title.configure(text="Şu anda aktif bir oyun algılanmadı")
            self.gm_active_sub.configure(text="Oyun başladığında CPU önceliği, güç planı, 1ms zamanlayıcı ve RAM temizliği otomatik devreye girer.")
            if self.gm_status_card.badge_widget:
                self.gm_status_card.badge_widget.set_state("HAZIR", "indigo")

        # 5. HUD Page Live FPS Stats
        self.hud_page_stats["fps"].configure(text=f"{fps_val:.0f}")
        self.hud_page_stats["avg"].configure(text=f"{fps_d.get('avg_fps', 0):.0f}")
        self.hud_page_stats["low1"].configure(text=f"{fps_d.get('low_1pct', 0):.0f}")
        self.hud_page_stats["ft"].configure(text=f"{fps_d.get('frametime_ms', 0):.1f}ms")
        self.hud_page_stats["hz"].configure(text=f"{hz:.0f}Hz")

        # 6. Forward live telemetry to active Toast & FPS HUD Overlay
        if self.active_toast is not None:
            self.active_toast.update_live_metrics(data)
        if self.fps_hud is not None:
            self.fps_hud.update_telemetry(data)

    def _append_log_entry(self, entry: dict):
        line = f"[{entry['time']}] [{entry['category']}] {entry['message']}\n"
        for box in (self.dash_log_box, self.full_log_box):
            try:
                box.configure(state="normal")
                box.insert("end", line)
                box.see("end")
                box.configure(state="disabled")
            except Exception:
                pass

    def _clear_logs(self):
        for box in (self.dash_log_box, self.full_log_box):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.configure(state="disabled")

    # =========================================================================
    # TOAST NOTIFICATION & FPS HUD OVERLAY
    # =========================================================================

    def show_game_toast(self, payload: dict):
        if self.active_toast is not None:
            try:
                self.active_toast.close_toast()
            except Exception:
                pass
            self.active_toast = None

        dur = int(self.config_data.get("toast_duration_sec", 12))
        pos = self.config_data.get("toast_position", "Sağ Üst")
        self.active_toast = GameNotificationToast(
            self,
            payload=payload,
            duration_sec=dur,
            position=pos,
            on_close=self._on_toast_closed,
        )

    def _on_toast_closed(self):
        self.active_toast = None

    def _trigger_test_game_toast(self):
        payload = {
            "title": "Oyun Yakalandı — Optimize Ediliyor",
            "game_name": self.engine.active_game_name or "VALORANT (Test Bildirimi)",
            "pid": self.engine.active_game_pid or os.getpid(),
            "freed_mb": max(self.engine.last_clean_freed_mb, 184.0),
            "power_plan": self.engine.active_power_plan_name,
            "telemetry": self.latest_telemetry,
        }
        self.show_game_toast(payload)

    def _toggle_hud_button(self):
        new_state = self.fps_hud is None
        self.hud_master_toggle.set(new_state)
        self.toggle_fps_hud(new_state)

    def toggle_fps_hud(self, enable: bool):
        self._set_cfg("hud_enabled", enable)
        if enable:
            if self.fps_hud is None:
                self.fps_hud = FPSOverlayHUD(self, self.config_data)
                if self.latest_telemetry:
                    self.fps_hud.update_telemetry(self.latest_telemetry)
            self.header_hud_btn.configure(fg_color="#1A2644", border_color=THEME["accent_cyan"], text_color=THEME["accent_cyan"])
        else:
            if self.fps_hud is not None:
                try:
                    self.fps_hud.destroy()
                except Exception:
                    pass
                self.fps_hud = None
            self.header_hud_btn.configure(fg_color=THEME["bg_elevated"], border_color=THEME["border_strong"], text_color=THEME["text_primary"])

    def _on_hud_style_change(self, value: str):
        self._set_cfg("hud_style", value)
        if self.fps_hud is not None:
            self.fps_hud.rebuild()

    def _on_hud_pos_change(self, value: str):
        self._set_cfg("hud_position", value)
        if self.fps_hud is not None:
            self.fps_hud.apply_position()

    def _on_hud_opacity_change(self, value: float):
        val = round(float(value), 2)
        self.hud_opacity_lbl.configure(text=f"%{int(val * 100)}")
        self._set_cfg("hud_opacity", val)
        if self.fps_hud is not None:
            self.fps_hud.apply_opacity()

    def _on_hud_metric_toggle(self, key: str, value: bool):
        self._set_cfg(key, value)
        if self.fps_hud is not None:
            self.fps_hud.rebuild()

    # =========================================================================
    # ACTIONS & SETTINGS HANDLERS
    # =========================================================================

    def _set_cfg(self, key: str, value):
        self.config_data[key] = value
        save_config(self.config_data)

    def _on_ram_thresh_change(self, val: float):
        v = round(float(val), 0)
        self.ram_thresh_lbl.configure(text=f"%{int(v)}")
        self._set_cfg("ram_threshold_percent", v)

    def _on_clean_interval_change(self, label: str):
        rev = {"1 Dakika": 60, "3 Dakika": 180, "5 Dakika": 300, "10 Dakika": 600}
        self._set_cfg("auto_clean_interval_sec", rev.get(label, 180))

    def _on_toast_dur_change(self, val: float):
        v = int(round(val))
        self.toast_dur_lbl.configure(text=f"{v} saniye")
        self._set_cfg("toast_duration_sec", v)

    def _on_startup_toggle(self, enable: bool):
        minimized = bool(self.config_data.get("start_minimized", True))
        ok, msg = set_startup_enabled(enable, minimized=minimized)
        if ok:
            self._set_cfg("start_with_windows", enable)
            self.startup_feedback_lbl.configure(
                text=f"✓ {msg}",
                text_color=THEME["accent_emerald"] if enable else THEME["text_secondary"],
            )
            self.engine.log("SYS", msg)
        else:
            self.startup_toggle.set(not enable)
            self.startup_feedback_lbl.configure(text=f"⚠ {msg}", text_color=THEME["accent_rose"])
            self.engine.log("WARN", msg)

    def _on_startup_min_toggle(self, minimized: bool):
        self._set_cfg("start_minimized", minimized)
        if is_startup_enabled():
            ok, msg = set_startup_enabled(True, minimized=minimized)
            if ok:
                self.startup_feedback_lbl.configure(
                    text=f"✓ Başlangıç komutu güncellendi ({'Tepsiye gizli' if minimized else 'Normal pencere'}).",
                    text_color=THEME["accent_cyan"],
                )

    def _run_turbo_boost(self):
        def worker():
            res = self.engine.turbo_boost()
            self.after(0, lambda: self._on_turbo_done(res))

        threading.Thread(target=worker, daemon=True).start()

    def _on_turbo_done(self, res: dict):
        self.tool_feedback_lbl.configure(
            text=f"✓ Turbo Boost tamamlandı: +{res['freed_mb']:.1f} MB RAM boşaltıldı, 1ms Timer & Yüksek Performans aktif!"
        )
        self._refresh_power_plans_ui()
        if self.config_data.get("game_toast_enabled", True):
            self.show_game_toast(
                {
                    "title": "Turbo Boost — Sistem Optimize Edildi",
                    "game_name": "Yüksek Performans Modu",
                    "pid": f"{res['proc_count']} İşlem",
                    "freed_mb": res["freed_mb"],
                    "power_plan": res["power_plan"],
                    "telemetry": self.latest_telemetry,
                }
            )

    def _run_manual_ram_clean(self):
        def worker():
            freed_mb, cnt = self.engine.optimize_ram("Manuel RAM Temizliği")
            self.after(
                0,
                lambda: self.tool_feedback_lbl.configure(
                    text=f"✓ RAM temizlendi: +{freed_mb:.1f} MB bellek boşaltıldı ({cnt} işlem)."
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _run_temp_clean(self):
        def worker():
            freed_mb, files = self.engine.clean_temp_files()
            self.after(
                0,
                lambda: self.tool_feedback_lbl.configure(
                    text=f"✓ Geçici dosyalar temizlendi: {files} dosya silindi ({freed_mb:.2f} MB)."
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _run_dns_flush(self):
        def worker():
            ok = self.engine.flush_dns()
            msg = "✓ DNS önbelleği başarıyla temizlendi." if ok else "⚠ DNS temizlenemedi (Yönetici yetkisi gerekebilir)."
            self.after(0, lambda: self.tool_feedback_lbl.configure(text=msg))

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_timer_manual(self):
        new_state = not self.engine.timer_boost_active
        self.engine.set_timer_resolution(new_state)
        msg = "✓ 1ms yüksek hassasiyetli zamanlayıcı aktif edildi." if new_state else "✓ Sistem zamanlayıcısı normale döndürüldü."
        self.tool_feedback_lbl.configure(text=msg)

    # --- Custom Games ---

    def _browse_custom_game(self):
        fp = filedialog.askopenfilename(
            title="Oyun .exe Dosyası Seç",
            filetypes=[("Çalıştırılabilir Dosya", "*.exe")],
        )
        if fp:
            exe = os.path.basename(fp).lower()
            self.custom_game_entry.delete(0, "end")
            self.custom_game_entry.insert(0, exe)

    def _add_custom_game(self):
        exe = self.custom_game_entry.get().strip().lower()
        if not exe:
            return
        if not exe.endswith(".exe"):
            exe += ".exe"
        custom = self.config_data.get("custom_games", [])
        if exe not in custom:
            custom.append(exe)
            self._set_cfg("custom_games", custom)
            self.engine.log("SYS", f"Özel oyun eklendi: {exe}")
        self.custom_game_entry.delete(0, "end")
        self._render_custom_games()

    def _remove_custom_game(self, exe: str):
        custom = [g for g in self.config_data.get("custom_games", []) if g != exe]
        self._set_cfg("custom_games", custom)
        self._render_custom_games()

    def _render_custom_games(self):
        for w in self.custom_games_list_frame.winfo_children():
            w.destroy()
        custom = self.config_data.get("custom_games", [])
        if not custom:
            ctk.CTkLabel(
                self.custom_games_list_frame,
                text="Henüz özel oyun eklenmedi. Yukarıdan .exe adı yazarak ekleyebilirsiniz.",
                text_color=THEME["text_muted"],
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", pady=4)
            return

        for exe in custom:
            row = ctk.CTkFrame(
                self.custom_games_list_frame,
                fg_color=THEME["bg_elevated"],
                corner_radius=8,
                border_width=1,
                border_color=THEME["border"],
            )
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=f"🎮  {exe}",
                text_color=THEME["text_primary"],
                font=ctk.CTkFont(family="Consolas", size=12),
            ).pack(side="left", padx=12, pady=7)
            ctk.CTkButton(
                row,
                text="Kaldır",
                width=68,
                height=26,
                corner_radius=6,
                fg_color="#2B1420",
                hover_color="#45192E",
                text_color=THEME["accent_rose"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda e=exe: self._remove_custom_game(e),
            ).pack(side="right", padx=8, pady=5)

    # --- Power Plans & Processes UI ---

    def _refresh_power_plans_ui(self):
        for w in self.power_plans_container.winfo_children():
            w.destroy()
        plans = self.engine.get_power_plans()
        if not plans:
            ctk.CTkLabel(self.power_plans_container, text="Güç planları okunamadı.", text_color=THEME["text_muted"]).pack(anchor="w")
            return
        for p in plans:
            is_act = p["active"]
            row = ctk.CTkFrame(
                self.power_plans_container,
                fg_color="#161E34" if is_act else THEME["bg_elevated"],
                border_color=THEME["accent_indigo"] if is_act else THEME["border"],
                border_width=1,
                corner_radius=9,
            )
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=f"{'⚡ ' if is_act else '○ '}{p['name']}",
                text_color=THEME["text_primary"],
                font=ctk.CTkFont(size=12, weight="bold" if is_act else "normal"),
            ).pack(side="left", padx=12, pady=8)

            if is_act:
                PillBadge(row, "AKTİF", "emerald").pack(side="right", padx=10)
            else:
                ctk.CTkButton(
                    row,
                    text="Aktifleştir",
                    width=92,
                    height=26,
                    corner_radius=7,
                    fg_color=THEME["accent_indigo"],
                    hover_color=THEME["accent_indigo_hover"],
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda g=p["guid"]: self._select_power_plan(g),
                ).pack(side="right", padx=10, pady=6)

    def _select_power_plan(self, guid: str):
        self.engine.set_power_plan(guid)
        self._refresh_power_plans_ui()

    def _refresh_processes_ui(self):
        for w in self.proc_list_frame.winfo_children():
            w.destroy()

        procs = self.engine.telemetry.get_top_processes(limit=10)
        for p in procs:
            row = ctk.CTkFrame(
                self.proc_list_frame,
                fg_color=THEME["bg_elevated"],
                border_color=THEME["border"],
                border_width=1,
                corner_radius=8,
            )
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(
                row,
                text=f"{p['name'][:26]}",
                text_color=THEME["text_primary"],
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                width=210,
                anchor="w",
            ).pack(side="left", padx=(12, 6), pady=7)

            ctk.CTkLabel(
                row,
                text=f"PID {p['pid']}",
                text_color=THEME["text_muted"],
                font=ctk.CTkFont(family="Consolas", size=11),
                width=85,
                anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=f"{p['ram_mb']:.0f} MB",
                text_color=THEME["accent_cyan"],
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                width=85,
                anchor="e",
            ).pack(side="left", padx=(0, 12))

            ctk.CTkButton(
                row,
                text="Düşük Öncelik",
                width=96,
                height=26,
                corner_radius=7,
                fg_color="#1D2234",
                hover_color="#2A324D",
                text_color=THEME["text_secondary"],
                font=ctk.CTkFont(size=11),
                command=lambda pid=p["pid"]: self.engine.set_process_priority(pid, "Düşük"),
            ).pack(side="right", padx=(4, 10), pady=5)

            ctk.CTkButton(
                row,
                text="RAM Boşalt",
                width=88,
                height=26,
                corner_radius=7,
                fg_color=THEME["accent_indigo"],
                hover_color=THEME["accent_indigo_hover"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda pid=p["pid"]: self._trim_single_proc(pid),
            ).pack(side="right", padx=4, pady=5)

    def _trim_single_proc(self, pid: int):
        freed = self.engine.trim_process_ram(pid)
        self.tool_feedback_lbl.configure(text=f"✓ PID {pid} RAM optimize edildi (+{freed:.1f} MB).")
        self.after(300, self._refresh_processes_ui)

    # =========================================================================
    # SYSTEM TRAY & LIFECYCLE
    # =========================================================================

    def _create_tray_image(self):
        img = Image.new("RGBA", (64, 64), (9, 11, 16, 255))
        dc = ImageDraw.Draw(img)
        dc.rounded_rectangle([6, 6, 58, 58], radius=14, fill=(99, 102, 241, 255))
        dc.rectangle([18, 18, 26, 46], fill=(255, 255, 255, 255))
        dc.rectangle([38, 18, 46, 46], fill=(255, 255, 255, 255))
        dc.polygon([(26, 18), (32, 30), (38, 18), (38, 28), (32, 38), (26, 28)], fill=(255, 255, 255, 255))
        return img

    def _setup_tray(self):
        image = self._create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("Pencereyi Göster", self.show_window, default=True),
            pystray.MenuItem("⚡ Hızlı Turbo Boost", lambda _i, _m: self.after(0, self._run_turbo_boost)),
            pystray.MenuItem("📊 FPS HUD Aç / Kapa", lambda _i, _m: self.after(0, self._toggle_hud_button)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış", self.quit_app),
        )
        self.tray_icon = pystray.Icon("MorbiOptimizer", image, f"{APP_NAME} {APP_VERSION}", menu)

    def hide_window(self):
        self.withdraw()
        if not self._tray_running:
            self._tray_running = True
            threading.Thread(target=self._run_tray, daemon=True).start()

    def _run_tray(self):
        try:
            self.tray_icon.run()
        finally:
            self._tray_running = False

    def show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(50, self.lift)

    def quit_app(self, icon=None, item=None):
        save_config(self.config_data)
        if self.tray_icon and self._tray_running:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.fps_hud is not None:
            try:
                self.fps_hud.destroy()
            except Exception:
                pass
        if self.active_toast is not None:
            try:
                self.active_toast.close_toast()
            except Exception:
                pass
        self.engine.stop()
        self.after(0, self.destroy)


if __name__ == "__main__":
    if not is_admin():
        print("Bilgi: Yönetici olarak çalıştırmak tüm Windows optimizasyon yetkilerini aktif eder.")
    app = MorbiOptimizerApp()
    app.mainloop()
