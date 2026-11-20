# -*- coding: utf-8 -*-
"""恢复出厂设置的安全计划。"""
import os

FACTORY_NAMES = ("userdata", "metadata", "cache", "misc")
NEVER = ("persist", "nvdata", "nvcfg", "nvram", "seccfg", "otp", "proinfo",
         "modem_a", "modem_b", "md_sec", "frp", "boot_a", "boot_b", "lk_a", "lk_b")


def plan(live_names):
    live = set(live_names or ())
    targets = [n for n in FACTORY_NAMES if n in live]
    bad = [n for n in targets if n in NEVER]
    if bad:
        return [], ["安全规则拒绝擦除：%s" % "、".join(bad)]
    if not targets:
        return [], ["现场 GPT 里没有 userdata / metadata / cache / misc"]
    return targets, []


def script_lines(targets):
    return ["e %s" % n for n in targets]
