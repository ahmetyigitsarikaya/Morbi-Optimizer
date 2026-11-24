import json
import os
import sys

APP_NAME = "Morbi Optimizer"
APP_VERSION = "2.5 Pro"


def _resolve_config_path() -> str:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.dirname(sys.executable)
        cfg_dir = os.path.join(appdata, "MorbiOptimizer")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "morbi_config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "morbi_config.json")


CONFIG_FILE = _resolve_config_path()

# React / Shadcn / Tailwind inspired dark obsidian theme palette
THEME = {
    "bg_root": "#090B10",
    "bg_sidebar": "#0D1017",
    "bg_header": "#0D1017",
    "bg_card": "#121620",
    "bg_card_hover": "#161B28",
    "bg_elevated": "#181E2C",
    "bg_input": "#0E121B",
    "border": "#1E2538",
    "border_strong": "#2B3550",
    "text_primary": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    "accent_indigo": "#6366F1",
    "accent_indigo_hover": "#4F46E5",
    "accent_cyan": "#06B6D4",
    "accent_emerald": "#10B981",
    "accent_amber": "#F59E0B",
    "accent_rose": "#F43F5E",
    "accent_violet": "#8B5CF6",
}

DEFAULT_KNOWN_GAMES = [
    "league of legends.exe",
    "valorant-win64-shipping.exe",
    "cs2.exe",
    "csgo.exe",
    "javaw.exe",
    "minecraft.windows.exe",
    "gta5.exe",
    "rdr2.exe",
    "dota2.exe",
    "cities2.exe",
    "albion-online.exe",
    "fortniteclient-win64-shipping.exe",
    "fc25.exe",
    "fc24.exe",
    "efootball.exe",
    "bannerlord.exe",
    "r5apex.exe",
    "tslgame.exe",
    "overwatch.exe",
    "rainbowsix.exe",
    "rocketleague.exe",
    "rustclient.exe",
    "cyberpunk2077.exe",
    "eldenring.exe",
    "cod.exe",
    "modernwarfare.exe",
    "bf2042.exe",
    "destiny2.exe",
    "warframe.x64.exe",
    "genshinimpact.exe",
    "pubg.exe",
    "deadbydaylight-win64-shipping.exe",
    "escapefromtarkov.exe",
    "pathofexile_x64.exe",
    "worldofwarcraft.exe",
    "wow.exe",
    "witcher3.exe",
    "hogwartslegacy.exe",
    "baldursgate3.exe",
    "bg3.exe",
    "helldivers2.exe",
    "palworld-win64-shipping.exe",
    "among us.exe",
    "terraria.exe",
    "stardew valley.exe",
    "robloxplayerbeta.exe",
]

# Non-essential background apps that can be gently throttled during Game Mode
BACKGROUND_THROTTLE_TARGETS = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "brave.exe",
    "onedrive.exe",
    "spotify.exe",
    "teams.exe",
    "ms-teams.exe",
    "slack.exe",
    "epicwebhelper.exe",
    "steamwebhelper.exe",
    "dropbox.exe",
    "adobeipcbroker.exe",
    "ccxprocess.exe",
}

DEFAULT_CONFIG = {
    "continuous_optimization": True,
    "auto_ram_clean": True,
    "ram_threshold_percent": 75.0,
    "auto_clean_interval_sec": 180,
    "auto_game_mode": True,
    "game_high_priority": True,
    "game_high_perf_power": True,
    "game_timer_resolution": True,
    "game_throttle_background": True,
    "game_toast_enabled": True,
    "toast_duration_sec": 12,
    "toast_position": "Sağ Üst",
    "hud_enabled": False,
    "hud_style": "Detaylı",
    "hud_opacity": 0.88,
    "hud_position": "Sol Üst",
    "hud_show_fps": True,
    "hud_show_frametime": True,
    "hud_show_cpu": True,
    "hud_show_ram": True,
    "hud_show_gpu": True,
    "hud_show_ping": True,
    "hud_show_graph": True,
    "hud_locked": False,
    "start_with_windows": False,
    "start_minimized": True,
    "custom_games": [],
    "known_games": DEFAULT_KNOWN_GAMES,
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    # Ensure known_games always contains defaults merged with any saved entries
    merged = list(dict.fromkeys([g.lower() for g in DEFAULT_KNOWN_GAMES] + [g.lower() for g in cfg.get("known_games", [])]))
    cfg["known_games"] = merged
    cfg["custom_games"] = list(dict.fromkeys([g.lower() for g in cfg.get("custom_games", [])]))
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
