# -*- coding: utf-8 -*-
"""把原始日志行解析成结构化记录。"""
import datetime
import re

RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
RE_TIME = re.compile(r"^\[?(\d{1,2}:\d{2}:\d{2})\]?\s*")
RE_LEVEL = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|TRACE)\b", re.I)

_LEVEL_WORDS = (
    ("ERROR", ("error", "failed", "failure", "exception", "traceback", "无法", "失败", "错误")),
    ("WARN", ("warn", "warning", "waiting", "not found", "missing", "超时", "警告", "未找到")),
    ("INFO", ("info", "success", "successfully", "done", "ok", "完成", "成功")),
)


def clean(text):
    return RE_ANSI.sub("", text)


def _level(line):
    m = RE_LEVEL.search(line)
    if m:
        lv = m.group(1).upper()
        return "WARN" if lv.startswith("WARN") else lv
    low = line.lower()
    for lv, words in _LEVEL_WORDS:
        if any(w in low for w in words):
            return lv
    return "INFO"


def _module(line):
    low = line.lower()
    if "gpt" in low or "partition" in low or "分区" in line:
        return "GPT"
    if "preloader" in low or "da1" in low or "da2" in low or "da stage" in low:
        return "DA"
    if "usb" in low or "vcom" in low or "serial" in low or "串口" in line:
        return "USB"
    if "backup" in low or "备份" in line:
        return "备份"
    if "write" in low or "写入" in line:
        return "写入"
    if "erase" in low or "擦除" in line:
        return "擦除"
    if "hash" in low or "sha" in low or "校验" in line:
        return "校验"
    if "rescue" in low or "救砖" in line:
        return "救砖"
    return "系统"


def record(line, now=None):
    line = clean(str(line)).strip()
    if not line:
        return None
    tm = RE_TIME.match(line)
    if tm:
        ts = tm.group(1)
    else:
        ts = (now or datetime.datetime.now()).strftime("%H:%M:%S")
    return {
        "time": ts,
        "level": _level(line),
        "module": _module(line),
        "text": line,
    }


def records(text, now=None):
    out = []
    for line in clean(text).splitlines():
        rec = record(line, now=now)
        if rec:
            out.append(rec)
    return out
