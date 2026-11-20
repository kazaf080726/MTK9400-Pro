# -*- coding: utf-8 -*-
"""纯工具函数，不依赖 Qt。"""
import hashlib


def hsize(n):
    """把字节数格式化成人类可读的大小（与旧版输出保持一致）。"""
    n = float(n)
    if n >= 1024 ** 3:
        return "%.2f GB" % (n / 1024 ** 3)
    if n >= 1024 ** 2:
        return "%.1f MB" % (n / 1024 ** 2)
    return "%.0f KB" % (n / 1024)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
