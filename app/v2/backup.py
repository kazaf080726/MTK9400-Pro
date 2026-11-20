# -*- coding: utf-8 -*-
"""深度备份 / 还原：清单、关键分区、校验和恢复计划。

纯逻辑模块，不直接访问设备。设备读写由 UI 层通过 r/w 命令执行。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Iterable

FORMAT = "MTK9400_DEEP_BACKUP"
VERSION = 1

CRITICAL = (
    "nvram", "nvdata", "persist", "proinfo", "seccfg", "frp", "misc",
    "protect1", "protect2",
)
BOOT = (
    "boot", "init_boot", "vendor_boot", "dtbo", "vbmeta",
    "vbmeta_system", "vbmeta_vendor", "lk", "bootloader",
)
SYSTEM = ("super", "system", "vendor", "product", "odm", "system_ext", "vendor_dlkm")
USER = ("userdata", "metadata", "cache")

GROUP_ORDER = ("gpt", "critical", "boot", "system", "modem", "userdata", "other")


class BackupError(Exception):
    pass


def _slot_base(name: str) -> str:
    return re.sub(r"_[ab]$", "", name or "", flags=re.I)


def group_of(name: str) -> str:
    base = _slot_base(name).lower()
    if base in CRITICAL:
        return "critical"
    if base in BOOT:
        return "boot"
    if base in SYSTEM:
        return "system"
    if base in ("modem", "md1img", "md1dsp", "dsp", "spmfw", "scp", "sspm", "mcupm"):
        return "modem"
    if base in USER:
        return "userdata"
    return "other"


def is_critical(name: str) -> bool:
    return group_of(name) == "critical"


def default_selected(name: str) -> bool:
    return group_of(name) in ("critical", "boot")


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "partition")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class BackupItem:
    name: str
    file: str
    size: int = 0
    sha256: str = ""
    start_lba: int = 0
    size_bytes: int = 0
    group: str = "other"

    def as_dict(self):
        return {"name": self.name, "file": self.file, "size": self.size,
                "sha256": self.sha256, "start_lba": self.start_lba,
                "size_bytes": self.size_bytes, "group": self.group}


@dataclass
class Manifest:
    created: str
    model: str
    platform: str
    sector_size: int
    total_sectors: int
    disk_size: int
    disk_guid: str
    items: list[BackupItem] = field(default_factory=list)
    gpt: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "format": FORMAT, "version": VERSION, "created": self.created,
            "model": self.model, "platform": self.platform,
            "sector_size": self.sector_size, "total_sectors": self.total_sectors,
            "disk_size": self.disk_size, "disk_guid": self.disk_guid,
            "gpt": self.gpt, "notes": self.notes,
            "items": [i.as_dict() for i in self.items],
        }


def make_manifest(meta: dict, partitions: Iterable[dict], directory: str,
                  selected: Iterable[str] = None, gpt: dict = None,
                  notes: list[str] = None) -> Manifest:
    """partitions 每项至少 name/start/size；生成备份清单并校验文件。"""
    wanted = set(selected) if selected is not None else None
    items = []
    for p in partitions:
        name = str(p.get("name") or "")
        if not name:
            continue
        if wanted is not None and name not in wanted:
            continue
        fname = safe_filename(name) + ".bin"
        path = os.path.join(directory, fname)
        if not os.path.isfile(path):
            raise BackupError("缺少备份文件：" + path)
        size = os.path.getsize(path)
        items.append(BackupItem(
            name=name, file=fname, size=size, sha256=sha256_file(path),
            start_lba=int(p.get("start_lba") or 0),
            size_bytes=int(p.get("size_bytes") or size),
            group=group_of(name),
        ))
    if not items:
        raise BackupError("没有可备份的分区")
    return Manifest(
        created=time.strftime("%Y-%m-%d %H:%M:%S"),
        model=str(meta.get("model") or ""),
        platform=str(meta.get("platform") or ""),
        sector_size=int(meta.get("sector_size") or 0),
        total_sectors=int(meta.get("total_sectors") or 0),
        disk_size=int(meta.get("disk_size") or 0),
        disk_guid=str(meta.get("disk_guid") or ""),
        items=items, gpt=dict(gpt or {}), notes=list(notes or []),
    )


def save_manifest(manifest: Manifest, directory: str) -> str:
    path = os.path.join(directory, "manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest.as_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def load_manifest(directory: str) -> Manifest:
    path = os.path.join(directory, "manifest.json")
    if not os.path.isfile(path):
        raise BackupError("备份目录缺少 manifest.json")
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if d.get("format") != FORMAT or int(d.get("version") or 0) != VERSION:
        raise BackupError("不支持的备份格式")
    items = []
    for x in d.get("items") or []:
        name = str(x.get("name") or "")
        fname = str(x.get("file") or "")
        if not name or not fname or os.path.basename(fname) != fname:
            raise BackupError("备份清单包含非法文件名")
        items.append(BackupItem(name=name, file=fname, size=int(x.get("size") or 0),
                                sha256=str(x.get("sha256") or ""),
                                start_lba=int(x.get("start_lba") or 0),
                                size_bytes=int(x.get("size_bytes") or 0),
                                group=str(x.get("group") or group_of(name))))
    return Manifest(created=str(d.get("created") or ""),
                    model=str(d.get("model") or ""),
                    platform=str(d.get("platform") or ""),
                    sector_size=int(d.get("sector_size") or 0),
                    total_sectors=int(d.get("total_sectors") or 0),
                    disk_size=int(d.get("disk_size") or 0),
                    disk_guid=str(d.get("disk_guid") or ""),
                    items=items, gpt=dict(d.get("gpt") or {}),
                    notes=list(d.get("notes") or []))


def verify_backup(manifest: Manifest, directory: str) -> list[str]:
    errors = []
    for item in manifest.items:
        path = os.path.join(directory, item.file)
        if not os.path.isfile(path):
            errors.append("缺少文件：" + item.name)
            continue
        if item.size and os.path.getsize(path) != item.size:
            errors.append("大小不一致：" + item.name)
        if item.sha256 and sha256_file(path) != item.sha256:
            errors.append("SHA256 不一致：" + item.name)
    return errors


def match_target(manifest: Manifest, target: dict, allow_guid_mismatch=False,
                 allow_size_mismatch=False) -> list[str]:
    errors = []
    if manifest.sector_size and target.get("sector_size") and \
            manifest.sector_size != int(target["sector_size"]):
        errors.append("扇区大小不一致")
    if not allow_size_mismatch and manifest.total_sectors and target.get("total_sectors") and \
            manifest.total_sectors != int(target["total_sectors"]):
        errors.append("磁盘容量不一致")
    if not allow_guid_mismatch and manifest.disk_guid and target.get("disk_guid") and \
            manifest.disk_guid.upper() != str(target["disk_guid"]).upper():
        errors.append("磁盘 GUID 不一致")
    if manifest.model and target.get("model") and \
            manifest.model.upper() != str(target["model"]).upper():
        errors.append("机型不一致")
    return errors


def select_items(manifest: Manifest, groups: Iterable[str] = None,
                 names: Iterable[str] = None) -> list[BackupItem]:
    if names is not None:
        wanted = set(names)
        return [i for i in manifest.items if i.name in wanted]
    gs = set(groups or ())
    return [i for i in manifest.items if i.group in gs]


def restore_plan(manifest: Manifest, directory: str, groups: Iterable[str] = None,
                 names: Iterable[str] = None, target: dict = None) -> list[dict]:
    errors = verify_backup(manifest, directory)
    if errors:
        raise BackupError("；".join(errors))
    if target:
        errs = match_target(manifest, target)
        if errs:
            raise BackupError("；".join(errs))
    items = select_items(manifest, groups, names)
    if not items:
        raise BackupError("没有选择任何备份项")
    return [{"name": i.name, "file": os.path.join(directory, i.file),
             "size": i.size, "group": i.group,
             "start_lba": i.start_lba, "size_bytes": i.size_bytes}
            for i in items]
