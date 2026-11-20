# -*- coding: utf-8 -*-
"""MTK 固件解析与深度刷机计划。

支持：
- scatter.txt + 镜像目录
- ZIP 中的 scatter + 镜像
- 无 scatter 时的镜像扫描（仅预览，不自动写 GPT）
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field

from core import scatter as mtk_scatter
from . import backup, sparse, ofp, payload, paths
from .ofp import OfpError
from .payload import PayloadError

SPARSE_MAGIC = b"\x3a\xff\x26\xed"


class FirmwareError(Exception):
    pass


@dataclass
class FirmwareItem:
    name: str
    image: str
    file_size: int
    partition_size: int = 0
    start: int = 0
    region: str = ""
    group: str = "other"
    risk: str = "low"
    selected: bool = False
    is_download: bool = True
    sparse: bool = False
    converted: bool = False
    logical: bool = False
    pending: bool = False
    error: str = ""

    @property
    def display(self):
        return os.path.basename(self.image) if self.image else ""


def _group(name):
    if (name or "").lower() in ("pgpt", "sgpt", "gpt"):
        return "gpt"
    g = backup.group_of(name)
    if name.lower() in ("preloader", "preloader_a", "preloader_b"):
        return "preloader"
    if name.lower() in ("lk", "bootloader", "bootloader_a", "bootloader_b"):
        return "bootloader"
    if g in ("critical", "boot", "system", "modem", "userdata"):
        return g
    return "other"


def _is_logical(name):
    n = (name or "").lower()
    return (n in ("system", "system_ext", "vendor", "product", "odm",
                  "system_dlkm", "vendor_dlkm", "odm_dlkm")
            or n.startswith("my_"))


def _risk(name, group):
    n = name.lower()
    if group in ("preloader", "bootloader", "gpt") or n in backup.CRITICAL:
        return "high"
    if group in ("boot", "system", "modem"):
        return "medium"
    return "low"


def _sparse(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == SPARSE_MAGIC
    except Exception:
        return False


def _find_scatter(directory):
    p = _find_scatter_optional(directory)
    if not p:
        raise FirmwareError("固件目录没有找到 scatter.txt")
    return p


def _find_scatter_optional(directory):
    cands = []
    for root, _dirs, files in os.walk(directory):
        for n in files:
            low = n.lower()
            if low.endswith(".txt") and "scatter" in low:
                cands.append(os.path.join(root, n))
        if len(cands) > 20:
            break
    if not cands:
        return ""
    cands.sort(key=lambda p: (0 if os.path.basename(p).lower() == "scatter.txt" else 1,
                              len(p)))
    return cands[0]


def _find_payload(directory):
    for root, _dirs, files in os.walk(directory):
        for n in files:
            if n.lower() == "payload.bin":
                return os.path.join(root, n)
    return ""


def _find_image(directory, file_name, name, files):
    names = []
    if file_name:
        names.append(file_name)
    names += [name + ".img", name + ".bin", file_name + ".img" if file_name else ""]
    for want in names:
        if not want:
            continue
        want = os.path.basename(want.replace("\\", "/"))
        p = os.path.join(directory, want)
        if os.path.isfile(p):
            return p
        for f in files:
            if f.lower() == want.lower():
                return os.path.join(directory, f)
    return ""


def _make_item(directory, e, temp_dir):
    img = _find_image(directory, e.file_name, e.name, os.listdir(directory))
    if not img:
        return None, "缺少镜像：%s（%s）" % (e.name, e.file_name or e.name)
    size = os.path.getsize(img)
    group = _group(e.name)
    is_sparse = _sparse(img)
    converted = False
    if is_sparse:
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
        raw = os.path.join(temp_dir, os.path.basename(img) + ".raw")
        try:
            sparse.expand(img, raw)
            img = raw
            size = os.path.getsize(raw)
            converted = True
        except Exception as ex:
            return None, "%s sparse 展开失败：%s" % (e.name, ex)
    item = FirmwareItem(e.name, img, size, e.size, e.start, e.region,
                        group, _risk(e.name, group), bool(e.download), e.download,
                        is_sparse, converted)
    if e.size and size > e.size:
        item.error = "镜像大于分区"
    return item, ""


def _items_from_scatter(directory, sc, files, temp_dir):
    items, errors, warnings = [], [], []
    for e in sc.entries:
        if not e.name:
            continue
        img = _find_image(directory, e.file_name, e.name, files)
        if not img:
            if e.download:
                errors.append("缺少镜像：%s（%s）" % (e.name, e.file_name or e.name))
            continue
        size = os.path.getsize(img)
        group = _group(e.name)
        is_sparse = _sparse(img)
        converted = False
        if is_sparse:
            if temp_dir is None:
                temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
            raw = os.path.join(temp_dir, os.path.basename(img) + ".raw")
            try:
                sparse.expand(img, raw)
                img = raw
                size = os.path.getsize(raw)
                converted = True
            except Exception as ex:
                errors.append("%s sparse 展开失败：%s" % (e.name, ex))
                continue
        item = FirmwareItem(e.name, img, size, e.size, e.start, e.region,
                            group, _risk(e.name, group), bool(e.download), e.download,
                            is_sparse, converted)
        if e.size and size > e.size:
            item.error = "镜像大于分区"
        items.append(item)
    if not items:
        errors.append("固件没有可识别的分区镜像")
    return items, errors, warnings


def _scan_images(directory, temp_dir):
    items, errors = [], []
    skip = {"payload.bin", "payload_properties.txt", "care_map.pb", "metadata",
            "payload_metadata.bin", "scatter.txt"}
    for n in sorted(os.listdir(directory)):
        if not n.lower().endswith((".img", ".bin")):
            continue
        if n.lower() in skip:
            continue
        p = os.path.join(directory, n)
        if not os.path.isfile(p):
            continue
        name = os.path.splitext(n)[0]
        group = _group(name)
        size = os.path.getsize(p)
        is_sparse = _sparse(p)
        converted = False
        if is_sparse:
            if temp_dir is None:
                temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
            raw = os.path.join(temp_dir, n + ".raw")
            try:
                sparse.expand(p, raw)
                p = raw
                size = os.path.getsize(raw)
                converted = True
            except Exception as ex:
                errors.append("%s sparse 展开失败：%s" % (name, ex))
                continue
        item = FirmwareItem(name, p, size, 0, 0, "", group,
                            _risk(name, group), False, True, is_sparse, converted)
        items.append(item)
    if not items:
        errors.append("没有识别到 img/bin 镜像，也没有 scatter.txt")
    return items, errors, []


def _payload_items(names, sizes):
    items = []
    for name in names:
        group = _group(name)
        item = FirmwareItem(name, "", int(sizes.get(name, 0)), 0, 0, "", group,
                            _risk(name, group), False, True, False, False)
        item.pending = True
        items.append(item)
    return items


class FirmwarePackage:
    def __init__(self, directory, scatter, items, errors, warnings, temp_dir=None,
                 source_kind="scatter", payload_source=""):
        self.directory = directory
        self.scatter = scatter
        self.items = items
        self.errors = errors
        self.warnings = warnings
        self.temp_dir = temp_dir
        self.source_kind = source_kind
        self.payload_source = payload_source

    @classmethod
    def load(cls, path):
        temp_dir = None
        directory = path
        source_kind = "scatter"
        payload_source = ""
        lazy_items = None
        low = path.lower()
        try:
            if low.endswith(".ofp") and os.path.isfile(path):
                temp_dir = tempfile.mkdtemp(prefix="mtk9400_ofp_")
                ofp.decrypt(path, temp_dir)
                directory = temp_dir
                source_kind = "ofp"
            elif os.path.isfile(path) and low.endswith(".zip"):
                temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
                    has_payload = any(n.lower().split("/")[-1] == "payload.bin"
                                      for n in names)
                    if not has_payload:
                        paths.safe_extract_zip(path, temp_dir)
                if has_payload:
                    names, sizes = payload.list_entries(path)
                    if not names:
                        raise PayloadError("payload 里没有识别到分区")
                    lazy_items = _payload_items(names, sizes)
                    directory = temp_dir
                    payload_source = path
                    source_kind = "payload-lazy"
                else:
                    directory = temp_dir
                    source_kind = "zip"
            elif os.path.isfile(path) and low.endswith(".bin"):
                with open(path, "rb") as f:
                    magic = f.read(4)
                if magic == b"CrAU":
                    names, sizes = payload.list_entries(path)
                    if not names:
                        raise PayloadError("payload 里没有识别到分区")
                    temp_dir = tempfile.mkdtemp(prefix="mtk9400_payload_")
                    lazy_items = _payload_items(names, sizes)
                    directory = temp_dir
                    payload_source = path
                    source_kind = "payload-lazy"
                else:
                    raise FirmwareError("不支持的固件文件")
            elif not os.path.isdir(path):
                raise FirmwareError("固件路径不存在")
            else:
                pl = _find_payload(directory)
                if pl:
                    names, sizes = payload.list_entries(pl)
                    if not names:
                        raise PayloadError("payload 里没有识别到分区")
                    lazy_items = _payload_items(names, sizes)
                    payload_source = pl
                    source_kind = "payload-lazy"
            if temp_dir is None:
                temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
            if lazy_items is not None:
                sc = None
                items, errors, warnings = lazy_items, [], []
            else:
                scatter_path = _find_scatter_optional(directory)
                if scatter_path:
                    sc = mtk_scatter.load(scatter_path)
                    directory = os.path.dirname(scatter_path)
                    files = os.listdir(directory)
                    items, errors, warnings = _items_from_scatter(directory, sc, files, temp_dir)
                else:
                    sc = None
                    items, errors, warnings = _scan_images(directory, temp_dir)
                    source_kind += "+images"
        except (FirmwareError, OfpError, PayloadError, OSError):
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="mtk9400_fw_")
        pkg = cls(directory, sc, items, errors, warnings, temp_dir, source_kind,
                  payload_source)
        pkg._defaults()
        if source_kind.startswith(("payload", "ofp")):
            for x in pkg.items:
                x.logical = _is_logical(x.name)
                if x.logical:
                    x.selected = False
        return pkg

    def materialize(self, items):
        pending = [x for x in items if x.pending]
        if not pending:
            return
        if not self.payload_source:
            raise FirmwareError("固件没有 payload 来源，无法解包")
        out = os.path.join(self.temp_dir, "_payload_selected")
        os.makedirs(out, exist_ok=True)
        payload.dump(self.payload_source, out, [x.name for x in pending])
        for x in pending:
            safe = paths.safe_name(x.name)
            p = os.path.join(out, safe + ".img")
            if not os.path.isfile(p):
                p = os.path.join(out, safe)
            if not os.path.isfile(p):
                raise FirmwareError("payload 没有解出：" + x.name)
            x.image = p
            x.file_size = os.path.getsize(p)
            x.pending = False

    def _defaults(self):
        for x in self.items:
            if x.group in ("boot", "system", "modem"):
                x.selected = True
            elif x.group == "bootloader":
                x.selected = False
            elif x.group == "preloader":
                x.selected = False
            elif x.group == "critical":
                x.selected = False
            elif x.group == "other":
                x.selected = False

    def preflight(self, target=None):
        errors = []
        warnings = []
        seen = set()
        for x in self.items:
            if x.name in seen:
                errors.append("重复分区：" + x.name)
            seen.add(x.name)
            if x.pending:
                if x.selected:
                    errors.append("%s 尚未从 payload 解包" % x.name)
                continue
            if not os.path.isfile(x.image):
                errors.append("镜像不存在：" + x.image)
            if x.sparse and not x.converted:
                errors.append("%s 是 sparse 镜像，且未成功展开" % x.name)
            if x.partition_size and x.file_size > x.partition_size:
                errors.append("%s 镜像大于分区" % x.name)
            if x.logical:
                warnings.append("%s 是 super 逻辑分区，不能直接 w 到 GPT 分区" % x.name)
            if x.error and x.error not in errors:
                warnings.append("%s：%s" % (x.name, x.error))
        if target:
            if target.get("sector_size") not in (512, 4096):
                errors.append("目标扇区大小未知")
            if not target.get("total_sectors"):
                errors.append("目标容量未知")
        return errors, warnings

    def select_mode(self, mode):
        for x in self.items:
            x.selected = False
        if mode == "repair":
            allow = ("boot", "system", "modem")
        elif mode == "full":
            allow = ("boot", "system", "modem", "bootloader")
        else:
            allow = ("boot", "system", "modem", "bootloader", "preloader",
                     "critical", "other", "gpt")
        for x in self.items:
            if x.group in allow:
                x.selected = True
        return self

    def selected_items(self):
        return [x for x in self.items if x.selected]

    def plan(self, mode="repair", erase_userdata=True):
        self.select_mode(mode)
        order = {"gpt": 0, "preloader": 1, "bootloader": 2, "boot": 3,
                 "system": 4, "modem": 5, "critical": 6, "userdata": 7, "other": 8}
        items = sorted([x for x in self.items if x.selected and not x.logical],
                       key=lambda x: (order.get(x.group, 9), x.name))
        commands = []
        for x in items:
            commands.append({"action": "write", "name": x.name, "file": x.image,
                             "size": x.file_size, "group": x.group, "risk": x.risk})
        if erase_userdata and mode in ("full", "all"):
            for n in ("userdata", "metadata", "cache"):
                commands.append({"action": "erase", "name": n})
        return commands

    def cleanup(self):
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
