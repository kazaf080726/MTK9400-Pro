# -*- coding: utf-8 -*-
"""界面偏好：主题和动态效果。"""
import json
import os

from core import config

FILE = "uiprefs.json"
DEFAULT = {"theme": "light", "animations": True}


def load():
    data = dict(DEFAULT)
    try:
        with open(os.path.join(config.WORK, FILE), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("theme") in ("light", "dark"):
            data["theme"] = saved["theme"]
        data["animations"] = bool(saved.get("animations", True))
    except Exception:
        pass
    return data


def save(data):
    os.makedirs(config.WORK, exist_ok=True)
    out = {
        "theme": data.get("theme") if data.get("theme") in ("light", "dark") else "light",
        "animations": bool(data.get("animations", True)),
    }
    path = os.path.join(config.WORK, FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return out
