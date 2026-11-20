# -*- coding: utf-8 -*-
"""重启当前程序以应用主题。"""
import os
import shutil
import subprocess
import sys
import tempfile

from core import config


def _ascii_dir():
    d = os.path.join(tempfile.gettempdir(), "mtk9400_restart")
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup(d):
    """清掉上一次重启留下的副本/批处理；正在运行的副本删不掉就跳过。"""
    try:
        for name in os.listdir(d):
            if name.startswith(("app_", "restart_")):
                try:
                    os.remove(os.path.join(d, name))
                except Exception:
                    pass
    except Exception:
        pass


def _command():
    if getattr(sys, "frozen", False):
        # onefile 直接由中文名 exe 重启时，PyInstaller 在本机偶发
        # "Failed to load Python DLL"；复制到一个纯 ASCII 临时路径再启动，
        # 并通过 MTK9400_BASE 把数据目录指回原位置。
        d = _ascii_dir()
        _cleanup(d)
        src = os.path.abspath(sys.executable)
        dst = os.path.join(d, "app_%d.exe" % os.getpid())
        try:
            shutil.copy2(src, dst)
            return [dst]
        except Exception:
            return [src]
    entry = os.path.join(config.BASE, "main.py")
    return [sys.executable, entry]


def restart(delay=5):
    """延迟启动新进程，让旧进程先释放单实例锁和串口。"""
    cmd = _command()
    bat = os.path.join(_ascii_dir(), "restart_%d.cmd" % os.getpid())
    lines = ["@echo off",
             "ping -n %d 127.0.0.1 >nul" % (int(delay) + 1),
             " ".join('"%s"' % c for c in cmd)]
    with open(bat, "w", encoding="ascii", errors="replace", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    env = os.environ.copy()
    env["MTK9400_BASE"] = config.BASE
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen(["cmd.exe", "/c", bat], cwd=config.BASE, env=env,
                     creationflags=flags, close_fds=True)
    return bat
