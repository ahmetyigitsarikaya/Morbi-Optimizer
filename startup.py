import os
import subprocess
import sys
import winreg

TASK_NAME = "MorbiOptimizerStartup"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "MorbiOptimizer"
CREATE_NO_WINDOW = 0x08000000


def get_app_executable() -> tuple:
    """Returns (exe_path, extra_args) for either frozen .exe or script mode."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "optimiser.py"))
    return sys.executable, f'"{script_path}"'


def build_startup_command(minimized: bool = True) -> str:
    exe_path, extra = get_app_executable()
    parts = [f'"{exe_path}"']
    if extra:
        parts.append(extra)
    if minimized:
        parts.append("--minimized")
    return " ".join(parts)


def _has_scheduled_task() -> bool:
    try:
        res = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        return res.returncode == 0
    except Exception:
        return False


def _has_registry_entry() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REG_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def is_startup_enabled() -> bool:
    return _has_scheduled_task() or _has_registry_entry()


def _remove_registry_entry():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_NAME)
    except Exception:
        pass


def _remove_scheduled_task():
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
    except Exception:
        pass


def set_startup_enabled(enable: bool, minimized: bool = True) -> tuple:
    """
    Enables or disables automatic Windows startup.
    Uses Task Scheduler (/RL HIGHEST) for UAC-elevated auto-start, with Registry Run fallback.
    Returns (success: bool, message: str).
    """
    if not enable:
        _remove_scheduled_task()
        _remove_registry_entry()
        return True, "Windows başlangıcından kaldırıldı."

    cmd = build_startup_command(minimized=minimized)

    # First try Task Scheduler with highest privileges (required for UAC admin .exe)
    try:
        res = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/F",
                "/TN",
                TASK_NAME,
                "/TR",
                cmd,
                "/SC",
                "ONLOGON",
                "/RL",
                "HIGHEST",
            ],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
            timeout=6,
        )
        if res.returncode == 0:
            _remove_registry_entry()
            return True, "Windows başlangıcına eklendi (Görev Zamanlayıcı — Yönetici)."
    except Exception:
        pass

    # Fallback to HKCU Run registry key
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, cmd)
        return True, "Windows başlangıcına eklendi (Kayıt Defteri)."
    except Exception as e:
        return False, f"Başlangıca eklenemedi: {e}"
