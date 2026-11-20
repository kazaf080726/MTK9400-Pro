# -*- coding: utf-8 -*-
"""路径安全和 ZIP 安全解压。"""
import os
import re
import shutil
import zipfile

MAX_ZIP_FILES = 20000
MAX_ZIP_BYTES = 64 * 1024 ** 3


class PathError(Exception):
    pass


def safe_name(name, fallback="item"):
    name = os.path.basename(str(name or "").replace("\\", "/"))
    name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff ]+", "_", name).strip(" .")
    if not name or name in (".", ".."):
        name = fallback
    return name


def safe_join(root, name, suffix=""):
    root = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root, safe_name(name) + suffix))
    if os.path.commonpath([root, target]) != root:
        raise PathError("路径越界：" + name)
    return target


def safe_extract_zip(zip_path, dest):
    os.makedirs(dest, exist_ok=True)
    root = os.path.abspath(dest)
    total = 0
    count = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            count += 1
            if count > MAX_ZIP_FILES:
                raise PathError("ZIP 文件数量过多")
            total += max(0, info.file_size)
            if total > MAX_ZIP_BYTES:
                raise PathError("ZIP 解压后超过大小限制")
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            target = os.path.abspath(os.path.join(root, name))
            if os.path.commonpath([root, target]) != root:
                raise PathError("ZIP 包含路径穿越：" + name)
            # 拒绝符号链接
            mode = (info.external_attr >> 16) & 0xF000
            if mode == 0xA000:
                raise PathError("ZIP 包含符号链接：" + name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
    return dest
