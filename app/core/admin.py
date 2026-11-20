# -*- coding: utf-8 -*-
"""Windows 管理员权限检测与重新提权。

只负责真实检测和启动一个新的管理员进程，不尝试绕过 UAC。
"""
import ctypes
import os
import subprocess
import sys


def is_admin():
    """当前进程是否已经拥有管理员令牌。非 Windows 环境返回 False。"""
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevation_args():
    """返回 (可执行文件, 命令行参数, 工作目录)。"""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = list(sys.argv[1:])
    else:
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        args = [script] + list(sys.argv[1:])
    params = subprocess.list2cmdline(args)
    return exe, params, os.getcwd()


def elevate():
    """通过 ShellExecuteW 的 runas 动词触发 UAC，重新启动自身。

    返回 True 表示新进程已启动；False 表示用户取消或启动失败。
    UAC 必须在系统弹窗里由用户同意，工具不能静默提权。
    """
    if os.name != "nt":
        return False
    if is_admin():
        return True
    exe, params, cwd = elevation_args()
    try:
        # SW_SHOWNORMAL = 1，返回值大于 32 表示成功。
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, cwd, 1)
        return int(rc) > 32
    except Exception:
        return False
