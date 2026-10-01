# -*- coding: utf-8 -*-
"""
WiFi Doctor - Build script for standalone single executable.
Uses PyInstaller with UAC admin elevation manifest and UTF-8 encoding.
"""

import os
import sys
import subprocess

def build():
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(cur_dir)

    print("Building WiFiDoctor.exe with PyInstaller...")
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--clean",
        "--distpath", os.path.join(cur_dir, "dist"),
        "--workpath", os.path.join(cur_dir, "build"),
        os.path.join(cur_dir, "WiFiDoctor.spec")
    ]
    print("Executing command:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode == 0:
        exe_path = os.path.join(cur_dir, "dist", "WiFiDoctor.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"Build succeeded! Output: {exe_path} ({size_mb:.2f} MB)")
            return True
    print("Build failed!")
    return False

if __name__ == "__main__":
    build()
