# -*- coding: utf-8 -*-
"""fastboot 检测与重启。"""
import os
import subprocess

from PySide6.QtCore import QThread, Signal

from . import config


def fastboot_run(args, timeout=10):
    """调用内置 fastboot，返回 (rc, 文本)。"""
    if not os.path.exists(config.FB_EXE):
        return 127, "缺少 fastboot.exe"
    try:
        p = subprocess.run(
            [config.FB_EXE] + list(args), cwd=config.FB_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
            creationflags=config.CREATE_NO_WINDOW, startupinfo=config.STARTUPINFO,
        )
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "fastboot 超时"
    except Exception as e:
        return 1, str(e)


def fastboot_devices():
    _rc, out = fastboot_run(["devices"], timeout=8)
    devs = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("<") or line.startswith("("):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower() == "fastboot":
            devs.append(parts[0])
        elif "fastboot" in line.lower():
            devs.append(line)
    return devs


def reboot(timeout=20):
    return fastboot_run(["reboot"], timeout=timeout)


class FbScanner(QThread):
    """后台扫描 fastboot 设备，避免阻塞 UI。"""
    found = Signal(list)

    def run(self):
        try:
            devs = fastboot_devices()
        except Exception:
            devs = []
        self.found.emit(devs)
