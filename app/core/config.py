# -*- coding: utf-8 -*-
"""运行环境：路径解析、数据目录、进程常量。

打包（PyInstaller onefile）与源码运行的目录规则：
    BASE  可执行文件所在目录（源码运行时为 app/）
    MEI   打包解压目录（源码运行时等于 BASE）
    WORK  数据目录（永远在 exe / app 旁边，不往桌面散落）
"""
import datetime
import os
import subprocess
import sys

APP = "Win版本MTK深刷(9400-9400+)"
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 主题重启会从 ASCII 临时路径启动副本；数据目录仍指向原 exe 所在目录。
BASE = os.environ.get("MTK9400_BASE") or BASE
MEI = getattr(sys, "_MEIPASS", BASE)

# 注意：这里绝对不能 os.chdir(BASE)。
# MtkWorker 启动子进程时会把 cwd 设为 WORK，备份脚本里的
# backup_critical\xxx.bin 是相对路径；一旦 chdir 到 BASE，
# 子进程就会在 exe 目录下找 backup_critical，结果每个文件都写不进去。


def find_res(rel):
    """优先用打包内资源；源码运行时回退到仓库根目录。"""
    for root in (MEI, BASE, os.path.dirname(BASE)):
        path = os.path.join(root, rel)
        if os.path.exists(path):
            return path
    return os.path.join(MEI, rel)


LOADER = find_res(os.path.join("mtkclient", "Loader", "OPLUS_DA_mt6991.bin"))
AUTH = find_res(os.path.join("mtkclient", "Loader", "OPLUS_mt6991.auth"))
HEAPBAIT = find_res(os.path.join("mtkclient", "payloads", "heapbait_sram.bin"))
LIBUSB = find_res(os.path.join("mtkclient", "Windows", "libusb-1.0.dll"))
WINFSP = find_res(os.path.join("mtkclient", "Library", "Filesystem", "bin", "winfsp-x64.dll"))
GPT_FILE = find_res("gpt_partitions.txt")

FB_DIR = os.path.join(MEI, "platform-tools")
FB_EXE = os.path.join(FB_DIR, "fastboot.exe")
ZADIG = os.path.join(MEI, "tools", "zadig.exe")

WORK = os.path.join(BASE, "MTK9400_Data")
DIR_LOG = os.path.join(WORK, "logs")
DIR_BACKUP = os.path.join(WORK, "backup")
DIR_RESCUE = os.path.join(WORK, "rescue")
DIR_CRIT = os.path.join(WORK, "backup_critical")
DIR_IMP = os.path.join(WORK, "backup_important")
DIR_FULL = os.path.join(WORK, "backup_full")
DIR_CUSTOM = os.path.join(WORK, "backup_custom")
DIR_PACKAGES = os.path.join(WORK, "rescue_packages")
DIR_RESCUE_RUN = os.path.join(WORK, "rescue_run")
DIR_READ = os.path.join(WORK, "read")
DIR_WRITE = os.path.join(WORK, "write")
for _d in (WORK, DIR_LOG, DIR_BACKUP, DIR_RESCUE, DIR_CRIT, DIR_IMP, DIR_FULL,
           DIR_CUSTOM, DIR_PACKAGES, DIR_RESCUE_RUN, DIR_READ, DIR_WRITE):
    os.makedirs(_d, exist_ok=True)

LOG_PATH = os.path.join(DIR_LOG, "gui_%s.log" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
STARTUPINFO = subprocess.STARTUPINFO() if os.name == "nt" else None
if STARTUPINFO is not None:
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE

# 进程卡片的默认标题
WINDOW_TITLE = APP
