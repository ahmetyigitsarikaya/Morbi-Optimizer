import ctypes
import subprocess
import threading
import time
from collections import deque
import psutil

CREATE_NO_WINDOW = 0x08000000


class UNSIGNED_RATIO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("uiNumerator", ctypes.c_uint32), ("uiDenominator", ctypes.c_uint32)]


class DWM_TIMING_INFO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rateRefresh", UNSIGNED_RATIO),
        ("qpcRefreshPeriod", ctypes.c_uint64),
        ("rateCompose", UNSIGNED_RATIO),
        ("qpcVBlank", ctypes.c_uint64),
        ("cRefresh", ctypes.c_uint64),
        ("cDXRefresh", ctypes.c_uint32),
        ("qpcCompose", ctypes.c_uint64),
        ("cFrame", ctypes.c_uint64),
        ("cDXPresent", ctypes.c_uint32),
        ("cRefreshFrame", ctypes.c_uint64),
        ("cFrameSubmitted", ctypes.c_uint64),
        ("cDXPresentSubmitted", ctypes.c_uint32),
        ("cFrameConfirmed", ctypes.c_uint64),
        ("cDXPresentConfirmed", ctypes.c_uint32),
        ("cRefreshConfirmed", ctypes.c_uint64),
        ("cDXRefreshConfirmed", ctypes.c_uint32),
        ("cFramesLate", ctypes.c_uint64),
        ("cFramesOutstanding", ctypes.c_uint32),
        ("cFrameDisplayed", ctypes.c_uint64),
        ("qpcFrameDisplayed", ctypes.c_uint64),
        ("cRefreshFrameDisplayed", ctypes.c_uint64),
        ("cFrameComplete", ctypes.c_uint64),
        ("qpcFrameComplete", ctypes.c_uint64),
        ("cFramePending", ctypes.c_uint64),
        ("qpcFramePending", ctypes.c_uint64),
        ("cFramesDisplayed", ctypes.c_uint64),
        ("cFramesComplete", ctypes.c_uint64),
        ("cFramesPending", ctypes.c_uint64),
        ("cFramesAvailable", ctypes.c_uint64),
        ("cFramesDropped", ctypes.c_uint64),
        ("cFramesMissed", ctypes.c_uint64),
        ("cRefreshNextDisplayed", ctypes.c_uint64),
        ("cRefreshNextPresented", ctypes.c_uint64),
        ("cRefreshesDisplayed", ctypes.c_uint64),
        ("cRefreshesPresented", ctypes.c_uint64),
        ("cRefreshStarted", ctypes.c_uint64),
        ("cPixelsReceived", ctypes.c_uint64),
        ("cPixelsDrawn", ctypes.c_uint64),
        ("cBuffersEmpty", ctypes.c_uint64),
    ]


class TelemetryCollector:
    """Collects live CPU, RAM, GPU, FPS (DWM), Disk, Network and Ping telemetry."""

    def __init__(self, history_len: int = 60):
        self.history_len = history_len
        self.lock = threading.Lock()

        # Rolling history
        self.cpu_history = deque([0.0] * history_len, maxlen=history_len)
        self.ram_history = deque([0.0] * history_len, maxlen=history_len)
        self.gpu_history = deque([0.0] * history_len, maxlen=history_len)
        self.fps_history = deque([0.0] * history_len, maxlen=history_len)

        # DWM FPS state
        self._dwmapi = getattr(ctypes.windll, "dwmapi", None)
        self._last_dwm_time = None
        self._last_dwm_frames = None
        self._last_dwm_dropped = 0
        self._fps_samples = deque(maxlen=60)

        # Net & Disk I/O state
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._last_io_time = time.perf_counter()

        # Async GPU & Ping cache (updated in background threads to never stall UI/engine)
        self._gpu_info = {
            "available": False,
            "name": "GPU Algılanıyor...",
            "usage": 0.0,
            "temp": 0.0,
            "vram_used": 0.0,
            "vram_total": 0.0,
        }
        self._ping_ms = 0.0
        self._running = True

        # Prime psutil cpu_percent
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

        threading.Thread(target=self._gpu_loop, daemon=True).start()
        threading.Thread(target=self._ping_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _gpu_loop(self):
        while self._running:
            try:
                out = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    creationflags=CREATE_NO_WINDOW,
                    timeout=3,
                    text=True,
                ).strip()
                if out:
                    line = out.splitlines()[0]
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 5:
                        with self.lock:
                            self._gpu_info = {
                                "available": True,
                                "name": parts[0],
                                "usage": float(parts[1]),
                                "temp": float(parts[2]),
                                "vram_used": float(parts[3]),
                                "vram_total": float(parts[4]),
                            }
            except Exception:
                with self.lock:
                    if not self._gpu_info["available"]:
                        self._gpu_info["name"] = "Entegre / Algılanamadı"
                time.sleep(6)
                continue
            time.sleep(1.5)

    def _ping_loop(self):
        while self._running:
            try:
                out = subprocess.check_output(
                    ["ping", "-n", "1", "-w", "1000", "1.1.1.1"],
                    creationflags=CREATE_NO_WINDOW,
                    timeout=2.5,
                    text=True,
                    errors="ignore",
                )
                ms = None
                for token in out.split():
                    low = token.lower()
                    if ("time=" in low or "süre=" in low or "time<" in low or "süre<" in low) and "ms" in low:
                        val = low.split("=")[-1].split("<")[-1].replace("ms", "").strip()
                        try:
                            ms = float(val)
                            break
                        except ValueError:
                            pass
                if ms is not None:
                    with self.lock:
                        self._ping_ms = ms
            except Exception:
                pass
            time.sleep(4.0)

    def _sample_fps(self) -> dict:
        fps = 0.0
        refresh_hz = 60.0
        dropped = 0
        if self._dwmapi is not None:
            try:
                info = DWM_TIMING_INFO()
                info.cbSize = ctypes.sizeof(DWM_TIMING_INFO)
                rc = self._dwmapi.DwmGetCompositionTimingInfo(None, ctypes.byref(info))
                if rc == 0:
                    now = time.perf_counter()
                    if info.rateRefresh.uiDenominator > 0:
                        refresh_hz = info.rateRefresh.uiNumerator / info.rateRefresh.uiDenominator
                    frames = max(info.cFrame, info.cRefresh)
                    if self._last_dwm_time is not None and self._last_dwm_frames is not None:
                        dt = now - self._last_dwm_time
                        if dt > 0.05:
                            df = frames - self._last_dwm_frames
                            if df >= 0:
                                fps = df / dt
                                # Cap extreme spikes from DWM counter resets
                                fps = min(fps, max(refresh_hz * 2.0, 500.0))
                            dropped = max(0, int(info.cFramesDropped - self._last_dwm_dropped))
                    self._last_dwm_time = now
                    self._last_dwm_frames = frames
                    self._last_dwm_dropped = info.cFramesDropped
            except Exception:
                pass

        if fps > 0:
            self._fps_samples.append(fps)

        if self._fps_samples:
            sorted_fps = sorted(self._fps_samples)
            avg_fps = sum(sorted_fps) / len(sorted_fps)
            low_idx = max(0, int(len(sorted_fps) * 0.05) - 1)
            low_1pct = sorted_fps[low_idx]
        else:
            avg_fps = 0.0
            low_1pct = 0.0

        frametime_ms = (1000.0 / fps) if fps >= 1.0 else 0.0
        return {
            "fps": round(fps, 1),
            "avg_fps": round(avg_fps, 1),
            "low_1pct": round(low_1pct, 1),
            "frametime_ms": round(frametime_ms, 2),
            "refresh_hz": round(refresh_hz, 0),
            "dropped": dropped,
        }

    def sample(self) -> dict:
        now = time.perf_counter()
        dt = max(0.1, now - self._last_io_time)
        self._last_io_time = now

        cpu_percent = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        cpu_freq = psutil.cpu_freq()
        cpu_mhz = cpu_freq.current if cpu_freq else 0.0

        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)
        ram_avail_gb = ram.available / (1024 ** 3)

        # Disk & Net throughput
        net = psutil.net_io_counters()
        net_down_mbps = max(0.0, ((net.bytes_recv - self._last_net.bytes_recv) * 8) / (dt * 1_000_000))
        net_up_mbps = max(0.0, ((net.bytes_sent - self._last_net.bytes_sent) * 8) / (dt * 1_000_000))
        self._last_net = net

        disk = psutil.disk_io_counters()
        if disk and self._last_disk:
            disk_read_mbs = max(0.0, (disk.read_bytes - self._last_disk.read_bytes) / (dt * 1024 * 1024))
            disk_write_mbs = max(0.0, (disk.write_bytes - self._last_disk.write_bytes) / (dt * 1024 * 1024))
        else:
            disk_read_mbs = 0.0
            disk_write_mbs = 0.0
        self._last_disk = disk

        fps_data = self._sample_fps()

        with self.lock:
            gpu = dict(self._gpu_info)
            ping_ms = self._ping_ms
            self.cpu_history.append(cpu_percent)
            self.ram_history.append(ram_percent)
            self.gpu_history.append(gpu["usage"])
            self.fps_history.append(fps_data["fps"])
            hist = {
                "cpu": list(self.cpu_history),
                "ram": list(self.ram_history),
                "gpu": list(self.gpu_history),
                "fps": list(self.fps_history),
            }

        return {
            "cpu_percent": round(cpu_percent, 1),
            "cpu_per_core": [round(c, 1) for c in per_core],
            "cpu_cores": len(per_core),
            "cpu_mhz": round(cpu_mhz, 0),
            "ram_percent": round(ram_percent, 1),
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "ram_avail_gb": round(ram_avail_gb, 2),
            "gpu": gpu,
            "fps": fps_data,
            "net_down_mbps": round(net_down_mbps, 2),
            "net_up_mbps": round(net_up_mbps, 2),
            "disk_read_mbs": round(disk_read_mbs, 2),
            "disk_write_mbs": round(disk_write_mbs, 2),
            "ping_ms": round(ping_ms, 1),
            "history": hist,
            "proc_count": len(psutil.pids()),
        }

    def get_top_processes(self, limit: int = 12) -> list:
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                info = p.info
                mem_mb = (info["memory_info"].rss / (1024 * 1024)) if info["memory_info"] else 0.0
                if mem_mb < 15.0:
                    continue
                procs.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"] or "Bilinmeyen",
                        "ram_mb": round(mem_mb, 1),
                        "cpu": round(info["cpu_percent"] or 0.0, 1),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        procs.sort(key=lambda x: x["ram_mb"], reverse=True)
        return procs[:limit]
