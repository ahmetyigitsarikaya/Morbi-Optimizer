import ctypes
import datetime
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import psutil

from config import BACKGROUND_THROTTLE_TARGETS
from telemetry import TelemetryCollector

PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400
CREATE_NO_WINDOW = 0x08000000

HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE_PERF_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def format_game_title(exe_name: str) -> str:
    base = exe_name.lower().replace(".exe", "")
    mapping = {
        "league of legends": "League of Legends",
        "valorant-win64-shipping": "VALORANT",
        "cs2": "Counter-Strike 2",
        "csgo": "CS:GO",
        "javaw": "Minecraft (Java)",
        "minecraft.windows": "Minecraft Bedrock",
        "gta5": "Grand Theft Auto V",
        "rdr2": "Red Dead Redemption 2",
        "dota2": "Dota 2",
        "cities2": "Cities: Skylines II",
        "albion-online": "Albion Online",
        "fortniteclient-win64-shipping": "Fortnite",
        "fc25": "EA SPORTS FC 25",
        "fc24": "EA SPORTS FC 24",
        "efootball": "eFootball",
        "bannerlord": "Mount & Blade II: Bannerlord",
        "r5apex": "Apex Legends",
        "tslgame": "PUBG: Battlegrounds",
        "overwatch": "Overwatch 2",
        "rainbowsix": "Rainbow Six Siege",
        "rocketleague": "Rocket League",
        "rustclient": "Rust",
        "cyberpunk2077": "Cyberpunk 2077",
        "eldenring": "Elden Ring",
        "cod": "Call of Duty",
        "bf2042": "Battlefield 2042",
        "genshinimpact": "Genshin Impact",
        "witcher3": "The Witcher 3",
        "baldursgate3": "Baldur's Gate 3",
        "bg3": "Baldur's Gate 3",
        "helldivers2": "Helldivers 2",
        "palworld-win64-shipping": "Palworld",
        "robloxplayerbeta": "Roblox",
    }
    if base in mapping:
        return mapping[base]
    return base.replace("-", " ").replace("_", " ").title()


class OptimizerEngine(threading.Thread):
    """Continuous system optimizer, game booster, power plan & timer resolution manager."""

    def __init__(self, config: dict, on_telemetry, on_game_detected=None, on_log=None):
        super().__init__(daemon=True)
        self.config = config
        self.on_telemetry = on_telemetry
        self.on_game_detected = on_game_detected
        self.on_log = on_log

        self.telemetry = TelemetryCollector(history_len=60)
        self.running = True
        self.lock = threading.Lock()

        # Runtime state
        self.game_mode_active = False
        self.active_game_pid = None
        self.active_game_exe = None
        self.active_game_name = None
        self.turbo_mode_active = False
        self.timer_boost_active = False

        # Power plan tracking
        self._previous_power_guid = None
        self.active_power_plan_name = "Bilinmiyor"
        self.active_power_plan_guid = None
        self._power_plans = []

        # Throttled background PIDs (so we can restore them when game exits)
        self._throttled_pids = {}

        # Cumulative optimization stats
        self.total_ram_freed_mb = 0.0
        self.total_optimizations = 0
        self.last_clean_time = time.time()
        self.last_clean_freed_mb = 0.0
        self.last_status_msg = "Sürekli Optimizasyon Aktif"
        self.logs = []

        self._refresh_power_plans()

    def log(self, category: str, message: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"time": ts, "category": category, "message": message}
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 250:
                self.logs = self.logs[-250:]
        if self.on_log:
            try:
                self.on_log(entry)
            except Exception:
                pass

    # --- Windows Low-Level Optimizations ---

    def set_timer_resolution(self, enable: bool):
        """Enables or disables 1ms high-resolution Windows timer for lower input lag."""
        try:
            winmm = ctypes.windll.winmm
            if enable and not self.timer_boost_active:
                winmm.timeBeginPeriod(1)
                self.timer_boost_active = True
                self.log("OPT", "Yüksek hassasiyetli sistem zamanlayıcısı (1ms) aktif edildi.")
            elif not enable and self.timer_boost_active:
                winmm.timeEndPeriod(1)
                self.timer_boost_active = False
                self.log("SYS", "Sistem zamanlayıcısı varsayılana döndürüldü.")
        except Exception:
            pass

    def _refresh_power_plans(self):
        plans = []
        active_guid = None
        active_name = "Dengeli"
        try:
            out = subprocess.check_output(
                ["powercfg", "/list"],
                creationflags=CREATE_NO_WINDOW,
                timeout=3,
                text=True,
                errors="ignore",
            )
            for line in out.splitlines():
                m = re.search(r"([0-9a-fA-F-]{36})\s+\((.+?)\)\s*(\*?)", line)
                if m:
                    guid, name, star = m.group(1).lower(), m.group(2).strip(), m.group(3)
                    plans.append({"guid": guid, "name": name, "active": bool(star)})
                    if star:
                        active_guid = guid
                        active_name = name
        except Exception:
            pass
        self._power_plans = plans
        if active_guid:
            self.active_power_plan_guid = active_guid
            self.active_power_plan_name = active_name

    def get_power_plans(self) -> list:
        self._refresh_power_plans()
        return list(self._power_plans)

    def set_power_plan(self, guid: str, silent: bool = False) -> bool:
        try:
            subprocess.check_call(
                ["powercfg", "/setactive", guid],
                creationflags=CREATE_NO_WINDOW,
                timeout=3,
            )
            self._refresh_power_plans()
            if not silent:
                self.log("OPT", f"Güç planı değiştirildi: {self.active_power_plan_name}")
            return True
        except Exception:
            return False

    def activate_best_performance_power_plan(self) -> bool:
        self._refresh_power_plans()
        if self._previous_power_guid is None and self.active_power_plan_guid:
            self._previous_power_guid = self.active_power_plan_guid

        # Check if already on an Ultra / High / Ultimate performance plan
        cur_low = self.active_power_plan_name.lower()
        if any(k in cur_low for k in ("ultra", "ultimate", "yüksek", "high", "bitsum", "revision")):
            return True

        # Try Ultimate Performance or High Performance from installed schemes
        preferred = None
        for p in self._power_plans:
            n = p["name"].lower()
            if p["guid"] == ULTIMATE_PERF_GUID or "ultimate" in n or "ultra" in n:
                preferred = p["guid"]
                break
        if not preferred:
            for p in self._power_plans:
                n = p["name"].lower()
                if p["guid"] == HIGH_PERF_GUID or "high" in n or "yüksek" in n:
                    preferred = p["guid"]
                    break
        if not preferred:
            preferred = HIGH_PERF_GUID

        return self.set_power_plan(preferred)

    def restore_power_plan(self):
        if self._previous_power_guid and self._previous_power_guid != self.active_power_plan_guid:
            self.set_power_plan(self._previous_power_guid)
        self._previous_power_guid = None

    def empty_working_set(self, pid: int) -> bool:
        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid
            )
            if handle:
                res = ctypes.windll.psapi.EmptyWorkingSet(handle)
                ctypes.windll.kernel32.CloseHandle(handle)
                return bool(res)
        except Exception:
            pass
        return False

    def trim_process_ram(self, pid: int) -> float:
        try:
            p = psutil.Process(pid)
            before = p.memory_info().rss
            if self.empty_working_set(pid):
                after = p.memory_info().rss
                freed_mb = max(0.0, (before - after) / (1024 * 1024))
                if freed_mb > 0.5:
                    self.total_ram_freed_mb += freed_mb
                self.log("OPT", f"{p.name()} (PID {pid}) RAM optimize edildi: {freed_mb:.1f} MB boşaltıldı.")
                return freed_mb
        except Exception:
            pass
        return 0.0

    def set_process_priority(self, pid: int, level: str) -> bool:
        mapping = {
            "Yüksek": psutil.HIGH_PRIORITY_CLASS,
            "Normalin Üstü": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            "Normal": psutil.NORMAL_PRIORITY_CLASS,
            "Düşük": psutil.BELOW_NORMAL_PRIORITY_CLASS,
        }
        cls = mapping.get(level)
        if cls is None:
            return False
        try:
            p = psutil.Process(pid)
            p.nice(cls)
            self.log("OPT", f"{p.name()} (PID {pid}) CPU önceliği '{level}' yapıldı.")
            return True
        except Exception:
            return False

    def optimize_ram(self, reason: str = "Otomatik RAM Optimizasyonu") -> tuple:
        """Trims working sets of background processes while protecting the active game."""
        mem_before = psutil.virtual_memory().used
        freed_count = 0
        own_pid = os.getpid()

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid = proc.info["pid"]
                if pid in (0, 4, own_pid):
                    continue
                if self.active_game_pid and pid == self.active_game_pid:
                    continue
                if self.empty_working_set(pid):
                    freed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        mem_after = psutil.virtual_memory().used
        freed_mb = max(0.0, (mem_before - mem_after) / (1024 * 1024))
        self.total_ram_freed_mb += freed_mb
        self.last_clean_freed_mb = freed_mb
        self.last_clean_time = time.time()
        self.total_optimizations += 1
        self.log("OPT", f"{reason}: {freed_mb:.1f} MB RAM boşaltıldı ({freed_count} işlem).")
        return round(freed_mb, 1), freed_count

    def _throttle_background_apps(self):
        if not self.config.get("game_throttle_background", True):
            return 0
        count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                pid = proc.info["pid"]
                if name in BACKGROUND_THROTTLE_TARGETS and pid != self.active_game_pid:
                    p = psutil.Process(pid)
                    if pid not in self._throttled_pids:
                        self._throttled_pids[pid] = p.nice()
                    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    self.empty_working_set(pid)
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if count:
            self.log("OPT", f"Oyun Modu: {count} arka plan uygulaması düşük önceliğe alındı.")
        return count

    def _restore_throttled_apps(self):
        if not self._throttled_pids:
            return
        restored = 0
        for pid, orig_nice in list(self._throttled_pids.items()):
            try:
                p = psutil.Process(pid)
                p.nice(orig_nice)
                restored += 1
            except Exception:
                pass
        self._throttled_pids.clear()
        if restored:
            self.log("SYS", f"{restored} arka plan uygulamasının önceliği normale döndürüldü.")

    # --- One-Click System Utilities ---

    def turbo_boost(self) -> dict:
        """Executes a full performance sweep on demand."""
        self.turbo_mode_active = True
        freed_mb, proc_count = self.optimize_ram("Turbo Boost RAM Temizliği")
        self.activate_best_performance_power_plan()
        self.set_timer_resolution(True)
        throttled = self._throttle_background_apps()
        self.last_status_msg = f"Turbo Boost Uygulandı ({freed_mb:.0f} MB boşaltıldı)"
        return {
            "freed_mb": freed_mb,
            "proc_count": proc_count,
            "throttled": throttled,
            "power_plan": self.active_power_plan_name,
            "timer_1ms": self.timer_boost_active,
        }

    def clean_temp_files(self) -> tuple:
        """Safely cleans temporary files from %TEMP%."""
        temp_dir = tempfile.gettempdir()
        freed_bytes = 0
        deleted_files = 0
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    os.remove(fp)
                    freed_bytes += sz
                    deleted_files += 1
                except Exception:
                    pass
            for d in dirs:
                dp = os.path.join(root, d)
                try:
                    shutil.rmtree(dp, ignore_errors=True)
                except Exception:
                    pass
            break  # top-level sweep for speed & safety
        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        self.log("OPT", f"Geçici dosyalar temizlendi: {deleted_files} dosya ({freed_mb:.2f} MB).")
        return freed_mb, deleted_files

    def flush_dns(self) -> bool:
        try:
            subprocess.check_call(
                ["ipconfig", "/flushdns"],
                creationflags=CREATE_NO_WINDOW,
                timeout=4,
            )
            self.log("OPT", "DNS önbelleği başarıyla temizlendi (daha kararlı ağ).")
            return True
        except Exception:
            self.log("WARN", "DNS önbelleği temizlenemedi.")
            return False

    # --- Game Detection ---

    def _get_target_games(self) -> set:
        known = self.config.get("known_games", [])
        custom = self.config.get("custom_games", [])
        return {g.lower().strip() for g in (known + custom) if g.strip()}

    def scan_for_games(self, current_telemetry: dict):
        if not self.config.get("auto_game_mode", True):
            if self.game_mode_active:
                self._exit_game_mode()
            return

        targets = self._get_target_games()
        found_pid = None
        found_exe = None

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in targets:
                    found_pid = proc.info["pid"]
                    found_exe = name
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if found_pid is not None:
            if self.active_game_pid != found_pid:
                self._enter_game_mode(found_pid, found_exe, current_telemetry)
        elif self.game_mode_active:
            self._exit_game_mode()

    def _enter_game_mode(self, pid: int, exe_name: str, current_telemetry: dict):
        self.active_game_pid = pid
        self.active_game_exe = exe_name
        self.active_game_name = format_game_title(exe_name)
        self.game_mode_active = True

        applied = []

        # 1. Boost CPU & I/O Priority
        if self.config.get("game_high_priority", True):
            try:
                p = psutil.Process(pid)
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                if hasattr(p, "ionice") and hasattr(psutil, "IOPRIO_HIGH"):
                    p.ionice(psutil.IOPRIO_HIGH)
                applied.append("CPU & I/O Önceliği: Yüksek")
            except Exception:
                pass

        # 2. Switch to High/Ultimate Performance Power Plan
        if self.config.get("game_high_perf_power", True):
            if self.activate_best_performance_power_plan():
                applied.append(f"Güç Planı: {self.active_power_plan_name}")

        # 3. 1ms Timer Resolution
        if self.config.get("game_timer_resolution", True):
            self.set_timer_resolution(True)
            applied.append("Zamanlayıcı: 1ms Düşük Gecikme")

        # 4. RAM Cleanup & Background Throttling
        freed_mb, _ = self.optimize_ram(f"Oyun Başlangıcı ({self.active_game_name})")
        throttled = self._throttle_background_apps()
        if throttled:
            applied.append(f"{throttled} Arka Plan Kısıtlandı")

        self.last_status_msg = f"Oyun Modu Aktif: {self.active_game_name} (PID: {pid})"
        self.log(
            "GAME",
            f"Oyun yakalandı: {self.active_game_name} (PID {pid}) — Optimize ediliyor ({freed_mb:.1f} MB RAM boşaltıldı).",
        )

        # 5. Trigger Floating Notification Banner
        if self.config.get("game_toast_enabled", True) and self.on_game_detected:
            payload = {
                "title": "Oyun Yakalandı — Optimize Ediliyor",
                "game_name": self.active_game_name,
                "exe_name": exe_name,
                "pid": pid,
                "freed_mb": freed_mb,
                "applied": applied,
                "power_plan": self.active_power_plan_name,
                "telemetry": current_telemetry,
            }
            try:
                self.on_game_detected(payload)
            except Exception:
                pass

    def _exit_game_mode(self):
        prev_name = self.active_game_name or "Oyun"
        self.game_mode_active = False
        self.active_game_pid = None
        self.active_game_exe = None
        self.active_game_name = None

        self._restore_throttled_apps()
        if not self.turbo_mode_active:
            self.set_timer_resolution(False)
            self.restore_power_plan()

        self.last_status_msg = "Sürekli Optimizasyon Aktif"
        self.log("GAME", f"{prev_name} kapatıldı. Sistem normal optimizasyon moduna döndü.")

    # --- Main Continuous Optimization Loop ---

    def run(self):
        self.log("SYS", "Morbi Optimizer Pro motoru başlatıldı. Sürekli optimizasyon aktif.")
        scan_tick = 0

        while self.running:
            loop_start = time.perf_counter()

            # 1. Sample real-time telemetry (1Hz)
            data = self.telemetry.sample()

            # 2. Scan for games every 2 seconds
            scan_tick += 1
            if scan_tick % 2 == 0:
                self.scan_for_games(data)

            # 3. Continuous Performance Optimization
            if self.config.get("continuous_optimization", True):
                ram_thresh = float(self.config.get("ram_threshold_percent", 75.0))
                interval = int(self.config.get("auto_clean_interval_sec", 180))
                now = time.time()

                if self.config.get("auto_ram_clean", True):
                    if data["ram_percent"] >= ram_thresh and (now - self.last_clean_time) >= 30:
                        freed_mb, _ = self.optimize_ram(f"Kritik RAM (%{data['ram_percent']:.0f})")
                        self.last_status_msg = f"Otomatik Temizlik: {freed_mb:.0f} MB RAM Boşaltıldı"
                    elif (now - self.last_clean_time) >= interval:
                        freed_mb, _ = self.optimize_ram("Sürekli Periyodik Optimizasyon")
                        if not self.game_mode_active:
                            self.last_status_msg = f"Sürekli Optimizasyon (+{freed_mb:.0f} MB)"

            # Enrich telemetry snapshot with engine status
            data["engine"] = {
                "game_mode": self.game_mode_active,
                "game_name": self.active_game_name,
                "game_exe": self.active_game_exe,
                "game_pid": self.active_game_pid,
                "turbo_mode": self.turbo_mode_active,
                "timer_1ms": self.timer_boost_active,
                "power_plan": self.active_power_plan_name,
                "total_ram_freed_mb": round(self.total_ram_freed_mb, 1),
                "total_optimizations": self.total_optimizations,
                "last_clean_freed_mb": round(self.last_clean_freed_mb, 1),
                "status_msg": self.last_status_msg,
                "continuous_on": self.config.get("continuous_optimization", True),
            }

            if self.on_telemetry:
                try:
                    self.on_telemetry(data)
                except Exception:
                    pass

            # Keep steady ~1.0s cadence
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0.2, 1.0 - elapsed)
            time.sleep(sleep_time)

    def stop(self):
        self.running = False
        self.telemetry.stop()
        self._restore_throttled_apps()
        self.set_timer_resolution(False)
        self.restore_power_plan()
