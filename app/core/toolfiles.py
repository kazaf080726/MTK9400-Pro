# -*- coding: utf-8 -*-
"""DA / Preloader / auth 工具文件管理。

刷机匣等工具通常单独提供 DA 和 Preloader。这里只保存路径和参数，
不把外部文件复制进数据目录，避免意外改动别人的固件。
"""
import json
import os

from core import config

SETTINGS_NAME = "toolfiles.json"


def defaults():
    return {
        "da": config.LOADER,
        "preloader": "",
        "auth": config.AUTH,
        "use_auth": True,
        "serialport": "",
    }


def _clean(path):
    return os.path.abspath(os.path.expanduser(path.strip())) if path and str(path).strip() else ""


def load(work_dir):
    data = defaults()
    path = os.path.join(work_dir, SETTINGS_NAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for key in ("da", "preloader", "auth"):
                if saved.get(key):
                    data[key] = _clean(saved[key])
            data["serialport"] = str(saved.get("serialport") or "").strip()
            data["use_auth"] = bool(saved.get("use_auth", True))
    except Exception:
        pass
    # 文件被移动/删除时退回内置 DA，避免启动后所有操作都失败。
    if not os.path.isfile(data["da"]):
        data["da"] = config.LOADER
    if data["preloader"] and not os.path.isfile(data["preloader"]):
        data["preloader"] = ""
    if data["auth"] and not os.path.isfile(data["auth"]):
        data["auth"] = config.AUTH
    return data


def validate(data):
    da = _clean(data.get("da", ""))
    pre = _clean(data.get("preloader", ""))
    auth = _clean(data.get("auth", ""))
    if not da:
        raise ValueError("没有选择 DA 文件")
    if not os.path.isfile(da):
        raise ValueError("DA 文件不存在：%s" % da)
    if os.path.getsize(da) < 1024:
        raise ValueError("DA 文件太小，可能不是有效 DA")
    if pre:
        if not os.path.isfile(pre):
            raise ValueError("Preloader 文件不存在：%s" % pre)
        if os.path.getsize(pre) < 1024:
            raise ValueError("Preloader 文件太小，可能不是有效 Preloader")
    if data.get("use_auth", True) and auth:
        if not os.path.isfile(auth):
            raise ValueError("auth 文件不存在：%s" % auth)
        if os.path.getsize(auth) == 0:
            raise ValueError("auth 文件为空")
    return {"da": da, "preloader": pre, "auth": auth,
            "use_auth": bool(data.get("use_auth", True)),
            "serialport": str(data.get("serialport") or "").strip()}


def save(work_dir, data):
    clean = validate(data)
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, SETTINGS_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return clean


def command_args(data):
    """生成 mtkclient 公共参数。Preloader 可选，auth 可选。"""
    clean = validate(data)
    args = ["--skipmeid"]
    if clean["serialport"]:
        args += ["--serialport", clean["serialport"]]
    args += ["--loader", clean["da"]]
    if clean["preloader"]:
        args += ["--preloader", clean["preloader"]]
    if clean["use_auth"] and clean["auth"]:
        args += ["--auth", clean["auth"]]
    return args


def describe(path):
    if not path:
        return "未选择"
    if not os.path.isfile(path):
        return "缺失"
    return "%s · %s" % (os.path.basename(path), _hsize(os.path.getsize(path)))


def _hsize(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.1f %s" % (n, unit)) if unit != "B" else ("%d B" % n)
        n /= 1024.0
    return "%d B" % n
