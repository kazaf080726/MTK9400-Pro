# -*- coding: utf-8 -*-
"""Android OTA payload.bin 解包，使用内置 payload-dumper.exe。"""
import os
import re
import subprocess

from core import config


class PayloadError(Exception):
    pass


def _parse_list(text):
    names = []
    sizes = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("total"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)\s+\(([\d.]+)\s*(B|KB|MB|GB)\)", line)
        if m:
            name = m.group(1)
            names.append(name)
            mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2,
                    "GB": 1024 ** 3}[m.group(3)]
            sizes[name] = int(float(m.group(2)) * mult)
    return names, sizes


def list_entries(payload, timeout=120):
    text = list_parts(payload, timeout=timeout)
    return _parse_list(text)


def tool_path():
    for root in (os.path.join(config.MEI, "tools"), os.path.join(config.BASE, "tools")):
        p = os.path.join(root, "payload-dumper.exe")
        if os.path.isfile(p):
            return p
    raise PayloadError("缺少 tools/payload-dumper.exe")


def dump(payload, outdir, partitions=None, timeout=3600):
    exe = tool_path()
    os.makedirs(outdir, exist_ok=True)
    if not partitions:
        partitions = _parse_list(list_parts(payload))[0]
        if not partitions:
            raise PayloadError("payload 里没有识别到分区")
    args = [exe, "extract", payload, "-o", outdir,
            "-p", ",".join(partitions)]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, creationflags=config.CREATE_NO_WINDOW,
                           startupinfo=config.STARTUPINFO)
    except subprocess.TimeoutExpired:
        raise PayloadError("payload 解包超时")
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        raise PayloadError("payload 解包失败：\n" + out[-3000:])
    return out


def list_parts(payload, timeout=120):
    exe = tool_path()
    p = subprocess.run([exe, "list", payload], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout,
                       creationflags=config.CREATE_NO_WINDOW,
                       startupinfo=config.STARTUPINFO)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        raise PayloadError("payload 列表失败：\n" + out[-3000:])
    return out
