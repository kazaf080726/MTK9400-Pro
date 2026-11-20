# -*- coding: utf-8 -*-
"""内置 Android logical partition 工具：lpunpack / lpmake / simg2img。"""
import os
import subprocess

from core import config


class LpError(Exception):
    pass


def _tool(name):
    for root in (os.path.join(config.MEI, "tools"), os.path.join(config.BASE, "tools")):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            return p
    raise LpError("缺少 tools/" + name)


def _run(args, timeout=3600):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, creationflags=config.CREATE_NO_WINDOW,
                           startupinfo=config.STARTUPINFO)
    except subprocess.TimeoutExpired:
        raise LpError("命令超时")
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        raise LpError(out[-4000:] or ("返回码 %d" % p.returncode))
    return out


def lpunpack(super_img, outdir, timeout=3600):
    os.makedirs(outdir, exist_ok=True)
    return _run([_tool("lpunpack.exe"), super_img, outdir], timeout)


def simg2img(sparse_img, raw_img, timeout=3600):
    return _run([_tool("simg2img.exe"), sparse_img, raw_img], timeout)


def lpmake(args, timeout=3600):
    """args: 传给 lpmake 的参数列表，例如 --device-size=..."""
    return _run([_tool("lpmake.exe")] + list(args), timeout)
