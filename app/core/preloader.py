# -*- coding: utf-8 -*-
"""Preloader 导出与目录批量刷入的纯逻辑。"""
import os

PRELOADER_NAMES = ("preloader", "preloader_a", "preloader_b")


def find_preloader(partition_sizes):
    names = [n for n in PRELOADER_NAMES if n in (partition_sizes or {})]
    return names[0] if names else ""


def export_plan(partition_sizes, out_dir):
    name = find_preloader(partition_sizes)
    if not name:
        return None, "现场 GPT 里没有 preloader 分区"
    size = int((partition_sizes or {}).get(name, 0) or 0)
    if size <= 0:
        return None, "preloader 分区大小无效"
    path = os.path.join(out_dir, "preloader_raw.bin")
    return {"name": name, "size": size, "file": path,
            "args": ["r", name, path]}, ""


def batch_plan(images, live_sizes, blocked=None, only_existing=True):
    """images: {partition: path}; 返回可写入项和错误。"""
    blocked = set(blocked or ())
    live_sizes = live_sizes or {}
    plans = []
    errors = []
    for name, path in sorted((images or {}).items()):
        if only_existing and name not in live_sizes:
            errors.append("现场 GPT 没有分区：%s" % name)
            continue
        if name in blocked:
            errors.append("安全规则禁止写入：%s" % name)
            continue
        if not path or not os.path.isfile(path):
            errors.append("文件不存在：%s" % (path or name))
            continue
        size = os.path.getsize(path)
        expected = int(live_sizes.get(name, 0) or 0)
        if size <= 0:
            errors.append("空文件：%s" % path)
            continue
        if expected and size > expected:
            errors.append("%s 镜像 %s 大于分区 %s" % (name, size, expected))
            continue
        plans.append({"name": name, "file": path, "size": size, "expected": expected})
    return plans, errors


def script_lines(plans):
    return ["w %s %s" % (p["name"], p["file"]) for p in plans]
