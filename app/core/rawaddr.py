# -*- coding: utf-8 -*-
"""MTK 原始地址读写计划。

不直接访问设备，只生成 mtkclient 的 ro / wo 命令，并对地址和大小做校验。
"""
import os
import re

UNITS = {
    "USER": None,
    "BOOT_1": "boot1",
    "BOOT_2": "boot2",
}
MAX_CHUNK = 0x1000000  # 单次 16MB，避免单条命令过大


def _hex(v, name):
    if isinstance(v, int):
        return v
    s = str(v or "").strip()
    if not s:
        raise ValueError("%s 不能为空" % name)
    if s.lower().startswith("0x"):
        s = s[2:]
    if not re.fullmatch(r"[0-9a-fA-F]+", s):
        raise ValueError("%s 不是十六进制数" % name)
    return int(s, 16)


def prepare(unit, start, size, filename, write=False):
    unit = str(unit or "USER").upper()
    if unit not in UNITS:
        raise ValueError("未知单元：%s" % unit)
    start_i = _hex(start, "起始地址")
    size_i = _hex(size, "大小")
    if size_i <= 0:
        raise ValueError("大小必须大于 0")
    if size_i > MAX_CHUNK:
        raise ValueError("单次最大 16MB，请分块")
    if not filename:
        raise ValueError("文件名不能为空")
    filename = os.path.abspath(filename)
    if write and not os.path.isfile(filename):
        raise ValueError("写入源文件不存在")
    if write and os.path.getsize(filename) > size_i:
        raise ValueError("源文件大于指定大小")
    args = ["wo" if write else "ro", "0x%x" % start_i, "0x%x" % size_i, filename]
    parttype = UNITS[unit]
    if parttype:
        args += ["--parttype", parttype]
    return {"unit": unit, "parttype": parttype, "start": start_i, "size": size_i,
            "file": filename, "args": args}


def chunks(unit, start, total, out_base, write=False, chunk=MAX_CHUNK):
    """把大范围拆成多条命令。"""
    start_i = _hex(start, "起始地址")
    total_i = _hex(total, "总大小")
    if total_i <= 0:
        raise ValueError("总大小必须大于 0")
    out = []
    done = 0
    i = 0
    while done < total_i:
        n = min(chunk, total_i - done)
        if write:
            # 调用方必须自己准备 partN 文件；这里只做计划。
            fn = "%s.part%d" % (out_base, i)
        else:
            fn = "%s.part%d" % (out_base, i)
        out.append(prepare(unit, start_i + done, n, fn, write=write))
        done += n
        i += 1
    return out


def describe(unit, start, size):
    return "%s 起始 0x%x，大小 0x%x" % (str(unit).upper(), int(start), int(size))
