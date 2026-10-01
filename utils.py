# -*- coding: utf-8 -*-
"""
WiFi Doctor - Utilities module
Encoding-safe process runner, admin check, logger, backup manager, and clean environment manager.
"""

import os
import sys
import json
import ctypes
import datetime
import subprocess
import threading
from typing import Tuple, Dict, Any, Optional

# Ensure standard output doesn't crash on Windows with UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(os.path.abspath(sys.executable))
else:
    _base_dir = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(_base_dir, "wifi_doctor.log")

# Store backup in ProgramData (protected by Windows ACLs against non-admin tampering)
_prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
SECURE_DATA_DIR = os.path.join(_prog_data, "WiFiDoctor")
try:
    os.makedirs(SECURE_DATA_DIR, exist_ok=True)
    BACKUP_FILE = os.path.join(SECURE_DATA_DIR, "wifi_doctor_backup.json")
except Exception:
    BACKUP_FILE = os.path.join(_base_dir, "wifi_doctor_backup.json")


def get_clean_env() -> Dict[str, str]:
    """
    Get a clean environment for child processes.
    Prevents PyInstaller _MEIPASS DLL injection that causes 0xc0000142 STATUS_DLL_INIT_FAILED.
    """
    env = os.environ.copy()
    system_root = env.get('SystemRoot', r'C:\Windows')
    system32 = os.path.join(system_root, 'System32')
    wbem = os.path.join(system32, 'wbem')
    powershell_dir = os.path.join(system32, 'WindowsPowerShell', 'v1.0')

    # Filter out PyInstaller temporary paths from PATH
    meipass = getattr(sys, '_MEIPASS', None)
    current_paths = env.get('PATH', '').split(os.pathsep)
    cleaned_paths = []
    for p in current_paths:
        if meipass and p.startswith(meipass):
            continue
        cleaned_paths.append(p)

    # Ensure System32, wbem, and powershell are at the front of PATH
    env['PATH'] = os.pathsep.join([system32, wbem, powershell_dir] + cleaned_paths)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    return env


class Logger:
    """Thread-safe and encoding-safe logger that outputs to file and UI."""
    _listeners = []
    _lock = threading.Lock()

    @classmethod
    def register_listener(cls, callback):
        if callback not in cls._listeners:
            cls._listeners.append(callback)

    @classmethod
    def log(cls, level: str, message: str):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{now_str}] [{level.upper():5s}] {message}"
        
        # Write to log file in UTF-8
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

        # Notify UI callbacks
        for listener in cls._listeners:
            try:
                listener(level.upper(), entry)
            except Exception:
                pass

        # Print to console if available
        try:
            print(entry)
        except Exception:
            pass

    @classmethod
    def info(cls, msg: str):
        cls.log("INFO", msg)

    @classmethod
    def success(cls, msg: str):
        cls.log("SUCCESS", msg)

    @classmethod
    def warning(cls, msg: str):
        cls.log("WARN", msg)

    @classmethod
    def warn(cls, msg: str):
        """Compatibility alias for callers using the shorter name."""
        cls.warning(msg)

    @classmethod
    def error(cls, msg: str):
        cls.log("ERROR", msg)


def is_admin() -> bool:
    """Check if current process has Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin():
    """Relaunch the current script or executable as Administrator via UAC."""
    try:
        if getattr(sys, 'frozen', False):
            executable = sys.executable
            args = ""
        else:
            executable = sys.executable
            args = f'"{os.path.abspath(sys.argv[0])}"'
            
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            args,
            None,
            1  # SW_SHOWNORMAL
        )
        return ret > 32
    except Exception as e:
        Logger.error(f"无法请求管理员权限: {e}")
        return False


def run_cmd(command: str, timeout: int = 15) -> Tuple[int, str, str]:
    """
    Run a cmd command using clean environment and UTF-8 / GB18030 decoding.
    """
    full_cmd = f'chcp 65001 >nul & {command}'
    try:
        p = subprocess.run(
            ['cmd.exe', '/c', full_cmd],
            capture_output=True,
            timeout=timeout,
            env=get_clean_env()
        )
        out = _decode_safely(p.stdout)
        err = _decode_safely(p.stderr)
        return p.returncode, out.strip(), err.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"命令执行超时 ({timeout}秒)"
    except Exception as e:
        return -1, "", str(e)


def run_native(executable: str, args: list, timeout: int = 15) -> Tuple[int, str, str]:
    """
    Directly execute a Windows native executable (e.g. netsh, wevtutil, wmic) without cmd wrapper.
    Ultra-fast and zero subprocess overhead.
    """
    try:
        p = subprocess.run(
            [executable] + args,
            capture_output=True,
            timeout=timeout,
            env=get_clean_env()
        )
        out = _decode_safely(p.stdout)
        err = _decode_safely(p.stderr)
        return p.returncode, out.strip(), err.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"执行超时 ({timeout}秒)"
    except Exception as e:
        return -1, "", str(e)


def _decode_safely(raw_bytes: bytes) -> str:
    """Decode raw subprocess output trying UTF-8 first, then GB18030/CP936."""
    if not raw_bytes:
        return ""
    try:
        decoded = raw_bytes.decode('utf-8')
        if '\ufffd' not in decoded:
            return decoded
    except Exception:
        pass

    try:
        return raw_bytes.decode('gb18030')
    except Exception:
        pass

    try:
        return raw_bytes.decode('cp936')
    except Exception:
        pass

    return raw_bytes.decode('utf-8', errors='replace')


class BackupManager:
    """Manages snapshots of system configurations for rollback/undo functionality."""
    _lock = threading.Lock()

    @staticmethod
    def load_backup() -> Dict[str, Any]:
        if not os.path.exists(BACKUP_FILE):
            return {"created_at": None, "items": {}}
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            Logger.error(f"读取备份记录失败: {e}")
            return {"created_at": None, "items": {}}

    @staticmethod
    def save_item_snapshot(item_id: str, title: str, original_val: Any, target_val: Any, restore_info: Dict[str, Any]):
        with BackupManager._lock:
            data = BackupManager.load_backup()
            if not data.get("created_at"):
                data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if item_id not in data["items"]:
                data["items"][item_id] = {
                    "title": title,
                    "original_val": original_val,
                    "target_val": target_val,
                    "restore_info": restore_info,
                    "backed_up_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                try:
                    temp_file = BACKUP_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(temp_file, BACKUP_FILE)
                    Logger.info(f"已创建状态快照 [{title}]: 原值={original_val}")
                except Exception as e:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except Exception:
                        pass
                    Logger.error(f"保存快照失败: {e}")

    @staticmethod
    def remove_item_snapshot(item_id: str):
        with BackupManager._lock:
            data = BackupManager.load_backup()
            if item_id in data.get("items", {}):
                del data["items"][item_id]
                try:
                    temp_file = BACKUP_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(temp_file, BACKUP_FILE)
                except Exception:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except Exception:
                        pass

    @staticmethod
    def clear_all():
        if os.path.exists(BACKUP_FILE):
            try:
                os.remove(BACKUP_FILE)
            except Exception:
                pass
