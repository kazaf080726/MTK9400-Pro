# -*- coding: utf-8 -*-
"""GPT / PGPT / SGPT 解析、校验、备份和恢复。

只处理 GPT 结构本身，不依赖 mtkclient 的 DA 实现。
设备读写在 UI 层通过 ro / wo 绝对偏移完成。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
import zlib
from dataclasses import dataclass, field
from struct import pack, unpack_from
from typing import Iterable

SECTOR_SIZES = (512, 4096)
GPT_SIGNATURE = b"EFI PART"
DEFAULT_ENTRY_COUNT = 128
DEFAULT_ENTRY_SIZE = 128
EFI_BASIC_DATA_GUID = bytes.fromhex("A2A0D0EBE5B9443387C068B6B72699C7")


class GptError(Exception):
    pass


def _u32(data, offset):
    return unpack_from("<I", data, offset)[0]


def _u64(data, offset):
    return unpack_from("<Q", data, offset)[0]


def _guid_str(raw: bytes) -> str:
    if len(raw) != 16:
        return ""
    d1, d2, d3 = unpack_from("<IHH", raw, 0)
    return "%08X-%04X-%04X-%s-%s" % (
        d1, d2, d3, raw[8:10].hex().upper(), raw[10:16].hex().upper())


def _guid_bytes(text: str) -> bytes:
    text = text.strip().replace("{", "").replace("}", "")
    u = uuid.UUID(text)
    return (u.fields[0].to_bytes(4, "little") +
            u.fields[1].to_bytes(2, "little") +
            u.fields[2].to_bytes(2, "little") +
            u.fields[3].to_bytes(2, "big") +
            u.fields[4].to_bytes(6, "big"))


def _name_from_raw(raw: bytes) -> str:
    try:
        return raw.decode("utf-16le", "replace").split("\x00", 1)[0]
    except Exception:
        return ""


def _name_to_raw(name: str) -> bytes:
    b = name.encode("utf-16le")
    return b[:72].ljust(72, b"\x00")


@dataclass
class GptHeader:
    signature: bytes
    revision: int
    header_size: int
    crc32: int
    reserved: int
    current_lba: int
    backup_lba: int
    first_usable_lba: int
    last_usable_lba: int
    disk_guid: bytes
    entries_lba: int
    entry_count: int
    entry_size: int
    entries_crc32: int
    raw: bytes = field(default=b"", repr=False)

    @classmethod
    def parse(cls, block: bytes, sector_size: int, at: int = 0) -> "GptHeader":
        if len(block) < at + 92:
            raise GptError("GPT 头长度不足")
        if block[at:at + 8] != GPT_SIGNATURE:
            raise GptError("GPT 签名不是 EFI PART")
        (sig, rev, hsize, crc, reserved, current, backup, first_usable,
         last_usable, disk_guid, entries_lba, count, esize, ecrc) = unpack_from(
            "<8sIIIIQQQQ16sQIII", block, at)
        if hsize < 92 or hsize > sector_size:
            raise GptError("GPT 头大小异常：%d" % hsize)
        if at + hsize > len(block):
            raise GptError("GPT 头被截断")
        hdr = bytearray(block[at:at + hsize])
        hdr[16:20] = b"\x00\x00\x00\x00"
        calc = zlib.crc32(hdr) & 0xFFFFFFFF
        if calc != crc:
            raise GptError("GPT 头 CRC32 错误：0x%08X != 0x%08X" % (calc, crc))
        if count <= 0 or count > 4096:
            raise GptError("GPT 分区表项数量异常：%d" % count)
        if esize < 128 or esize > 4096 or esize % 8:
            raise GptError("GPT 分区表项大小异常：%d" % esize)
        return cls(sig, rev, hsize, crc, reserved, current, backup,
                   first_usable, last_usable, disk_guid, entries_lba,
                   count, esize, ecrc, bytes(block[at:at + hsize]))

    def to_bytes(self, sector_size: int) -> bytes:
        hsize = max(92, self.header_size)
        buf = bytearray(sector_size)
        pack_into = pack
        buf[0:8] = GPT_SIGNATURE
        buf[8:12] = pack_into("<I", self.revision)
        buf[12:16] = pack_into("<I", hsize)
        buf[16:20] = b"\x00\x00\x00\x00"
        buf[20:24] = pack_into("<I", self.reserved)
        buf[24:32] = pack_into("<Q", self.current_lba)
        buf[32:40] = pack_into("<Q", self.backup_lba)
        buf[40:48] = pack_into("<Q", self.first_usable_lba)
        buf[48:56] = pack_into("<Q", self.last_usable_lba)
        buf[56:72] = self.disk_guid
        buf[72:80] = pack_into("<Q", self.entries_lba)
        buf[80:84] = pack_into("<I", self.entry_count)
        buf[84:88] = pack_into("<I", self.entry_size)
        buf[88:92] = pack_into("<I", self.entries_crc32)
        crc = zlib.crc32(bytes(buf[:hsize])) & 0xFFFFFFFF
        buf[16:20] = pack_into("<I", crc)
        return bytes(buf)


@dataclass
class GptEntry:
    type_guid: bytes
    unique_guid: bytes
    first_lba: int
    last_lba: int
    attrs: int
    name_raw: bytes
    index: int = 0

    @property
    def used(self) -> bool:
        return any(self.type_guid)

    @property
    def name(self) -> str:
        return _name_from_raw(self.name_raw)

    @property
    def type_text(self) -> str:
        return _guid_str(self.type_guid)

    @property
    def unique_text(self) -> str:
        return _guid_str(self.unique_guid)

    def to_bytes(self) -> bytes:
        return (self.type_guid.ljust(16, b"\x00")[:16] +
                self.unique_guid.ljust(16, b"\x00")[:16] +
                pack("<QQQ", self.first_lba, self.last_lba, self.attrs) +
                self.name_raw.ljust(72, b"\x00")[:72])


def parse_entries(raw: bytes, count: int, entry_size: int) -> list[GptEntry]:
    need = count * entry_size
    if len(raw) < need:
        raise GptError("GPT 分区表项数据不足：%d < %d" % (len(raw), need))
    ecrc = zlib.crc32(raw[:need]) & 0xFFFFFFFF
    out = []
    for i in range(count):
        off = i * entry_size
        chunk = raw[off:off + entry_size]
        if len(chunk) < 128:
            raise GptError("分区表项 #%d 长度不足" % i)
        tguid = chunk[0:16]
        uguid = chunk[16:32]
        first, last, attrs = unpack_from("<QQQ", chunk, 32)
        name = chunk[56:128]
        e = GptEntry(tguid, uguid, first, last, attrs, name, i)
        if e.used:
            out.append(e)
    return out


def build_entries_raw(entries: Iterable[GptEntry], count: int, entry_size: int) -> bytes:
    buf = bytearray(count * entry_size)
    for i, e in enumerate(entries):
        if i >= count:
            break
        data = e.to_bytes()
        buf[i * entry_size:i * entry_size + len(data)] = data
    return bytes(buf)


def _protective_mbr(total_sectors: int) -> bytes:
    mbr = bytearray(512)
    # Partition entry 0: type EE, start LBA 1, size min(total-1, 0xFFFFFFFF)
    mbr[0x1BE + 4] = 0xEE
    mbr[0x1BE + 5:0x1BE + 8] = b"\x00\x00\x00"
    mbr[0x1BE + 8:0x1BE + 12] = pack("<I", 1)
    mbr[0x1BE + 12:0x1BE + 16] = pack("<I", min(max(0, total_sectors - 1), 0xFFFFFFFF))
    mbr[0x1FE:0x200] = b"\x55\xAA"
    return bytes(mbr)


def _mbr_ok(data: bytes) -> tuple[bool, str]:
    if len(data) < 512:
        return False, "保护 MBR 长度不足"
    if data[0x1FE:0x200] != b"\x55\xAA":
        return False, "保护 MBR 缺少 55AA"
    if data[0x1BE + 4] != 0xEE:
        return False, "保护 MBR 分区类型不是 0xEE"
    return True, ""


@dataclass
class GptImage:
    sector_size: int
    total_sectors: int
    primary: GptHeader
    backup: GptHeader
    entries: list[GptEntry]
    primary_raw: bytes
    backup_raw: bytes
    primary_start_lba: int = 0
    backup_start_lba: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def disk_guid(self) -> str:
        return _guid_str(self.primary.disk_guid)

    @property
    def disk_size(self) -> int:
        return self.total_sectors * self.sector_size

    def primary_length(self) -> int:
        need = self.primary.entries_lba * self.sector_size + self.primary.entry_count * self.primary.entry_size
        return (need + self.sector_size - 1) // self.sector_size * self.sector_size

    def backup_length(self) -> int:
        if self.backup_start_lba <= 0:
            return len(self.backup_raw)
        return (self.total_sectors - self.backup_start_lba) * self.sector_size

    @classmethod
    def from_blocks(cls, primary_block: bytes, backup_block: bytes,
                    total_sectors: int, sector_size: int,
                    primary_start: int = 0, backup_base_lba: int = 0):
        if sector_size not in SECTOR_SIZES:
            raise GptError("不支持的扇区大小：%d" % sector_size)
        if total_sectors <= 0:
            raise GptError("磁盘总扇区数无效")
        if len(primary_block) < sector_size * 2:
            raise GptError("主 GPT 数据不足")
        ph = GptHeader.parse(primary_block, sector_size, sector_size)
        if ph.current_lba != 1:
            raise GptError("主 GPT current_lba 不是 1")
        if ph.backup_lba != total_sectors - 1:
            raise GptError("主 GPT backup_lba 与磁盘容量不匹配")
        primary_need = ph.entries_lba * sector_size + ph.entry_count * ph.entry_size
        if len(primary_block) < primary_need:
            raise GptError("主 GPT 分区表被截断")
        p_entries_raw = primary_block[ph.entries_lba * sector_size:primary_need]
        if zlib.crc32(p_entries_raw) & 0xFFFFFFFF != ph.entries_crc32:
            raise GptError("主 GPT 分区表项 CRC32 错误")
        entries = parse_entries(p_entries_raw, ph.entry_count, ph.entry_size)

        if len(backup_block) < sector_size * 2:
            raise GptError("备份 GPT 数据不足")
        # backup block 可能只是磁盘尾部一段；base 表示它从哪个 LBA 开始
        bh = GptHeader.parse(backup_block, sector_size, len(backup_block) - sector_size)
        if bh.current_lba != total_sectors - 1:
            raise GptError("备份 GPT current_lba 与磁盘容量不匹配")
        if bh.backup_lba != 1:
            raise GptError("备份 GPT backup_lba 不是 1")
        b_start = (bh.entries_lba - backup_base_lba) * sector_size
        if b_start < 0 or b_start + bh.entry_count * bh.entry_size > len(backup_block):
            raise GptError("备份 GPT 分区表被截断")
        b_entries_raw = backup_block[b_start:b_start + bh.entry_count * bh.entry_size]
        if zlib.crc32(b_entries_raw) & 0xFFFFFFFF != bh.entries_crc32:
            raise GptError("备份 GPT 分区表项 CRC32 错误")
        if p_entries_raw != b_entries_raw:
            raise GptError("主 GPT 和备份 GPT 分区表不一致")
        if ph.disk_guid != bh.disk_guid:
            raise GptError("主 GPT 和备份 GPT 磁盘 GUID 不一致")
        primary_raw = primary_block[:cls._primary_len(ph, sector_size)]
        backup_raw = backup_block[b_start:]
        img = cls(sector_size, total_sectors, ph, bh, entries, primary_raw, backup_raw,
                  primary_start_lba=0, backup_start_lba=bh.entries_lba)
        img._validate_basic()
        return img

    @staticmethod
    def _primary_len(h: GptHeader, sector_size: int) -> int:
        need = h.entries_lba * sector_size + h.entry_count * h.entry_size
        return (need + sector_size - 1) // sector_size * sector_size

    def _validate_basic(self):
        if self.primary.disk_guid != self.backup.disk_guid:
            raise GptError("磁盘 GUID 不一致")
        if self.primary.current_lba != 1:
            raise GptError("主 GPT current_lba 错误")
        if self.backup.current_lba != self.total_sectors - 1:
            raise GptError("备份 GPT current_lba 错误")
        if self.primary.backup_lba != self.total_sectors - 1:
            raise GptError("主 GPT backup_lba 错误")
        if self.backup.backup_lba != 1:
            raise GptError("备份 GPT backup_lba 错误")
        if self.primary.first_usable_lba > self.primary.last_usable_lba:
            raise GptError("可用 LBA 范围错误")
        if self.primary.first_usable_lba < self.primary.entries_lba + (
                self.primary.entry_count * self.primary.entry_size + self.sector_size - 1) // self.sector_size:
            raise GptError("First Usable LBA 与主分区表重叠")
        if self.backup_start_lba <= self.primary.last_usable_lba:
            raise GptError("备份分区表与可用区重叠")
        used = [e for e in self.entries if e.used]
        ranges = []
        uuids = set()
        for e in used:
            if e.first_lba > e.last_lba:
                raise GptError("分区 %s 的 LBA 范围无效" % e.name)
            if e.first_lba < self.primary.first_usable_lba or e.last_lba > self.primary.last_usable_lba:
                raise GptError("分区 %s 超出可用范围" % e.name)
            if e.unique_guid in uuids:
                raise GptError("分区唯一 GUID 重复")
            uuids.add(e.unique_guid)
            ranges.append((e.first_lba, e.last_lba, e.name))
        ranges.sort()
        for a, b in zip(ranges, ranges[1:]):
            if b[0] <= a[1]:
                raise GptError("分区重叠：%s 与 %s" % (a[2], b[2]))
        mbr_ok, mbr_msg = _mbr_ok(self.primary_raw[:512])
        if not mbr_ok:
            self.warnings.append(mbr_msg)

    def validate(self, strict_mbr=False) -> list[str]:
        errors = []
        if strict_mbr:
            ok, msg = _mbr_ok(self.primary_raw[:512])
            if not ok:
                errors.append(msg)
        if self.primary.entry_count != self.backup.entry_count:
            errors.append("主/备 entry_count 不一致")
        if self.primary.entry_size != self.backup.entry_size:
            errors.append("主/备 entry_size 不一致")
        if self.primary.first_usable_lba != self.backup.first_usable_lba:
            errors.append("主/备 first_usable_lba 不一致")
        if self.primary.last_usable_lba != self.backup.last_usable_lba:
            errors.append("主/备 last_usable_lba 不一致")
        if self.primary.entries_crc32 != self.backup.entries_crc32:
            errors.append("主/备分区表项 CRC 不一致")
        if len(self.primary_raw) < self.primary_length():
            errors.append("主 GPT 原始数据长度不足")
        if len(self.backup_raw) != self.backup_length():
            errors.append("备份 GPT 原始数据长度不足")
        return errors

    def summary(self) -> dict:
        return {
            "sector_size": self.sector_size,
            "total_sectors": self.total_sectors,
            "disk_size": self.disk_size,
            "disk_guid": self.disk_guid,
            "primary_lba": self.primary.current_lba,
            "backup_lba": self.backup.current_lba,
            "first_usable_lba": self.primary.first_usable_lba,
            "last_usable_lba": self.primary.last_usable_lba,
            "entry_count": self.primary.entry_count,
            "entry_size": self.primary.entry_size,
            "partitions": len([e for e in self.entries if e.used]),
            "warnings": list(self.warnings),
        }

    def meta(self) -> dict:
        return {
            "format": "MTK9400_GPT_BACKUP",
            "version": 1,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sector_size": self.sector_size,
            "total_sectors": self.total_sectors,
            "disk_size": self.disk_size,
            "disk_guid": self.disk_guid,
            "primary_sha256": hashlib.sha256(self.primary_raw).hexdigest(),
            "backup_sha256": hashlib.sha256(self.backup_raw).hexdigest(),
            "primary_length": len(self.primary_raw),
            "backup_length": len(self.backup_raw),
            "summary": self.summary(),
        }

    def save(self, directory: str) -> dict:
        os.makedirs(directory, exist_ok=True)
        p = os.path.join(directory, "pgpt.bin")
        b = os.path.join(directory, "sgpt.bin")
        m = os.path.join(directory, "gpt.json")
        with open(p, "wb") as f:
            f.write(self.primary_raw)
        with open(b, "wb") as f:
            f.write(self.backup_raw)
        meta = self.meta()
        with open(m, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"dir": directory, "pgpt": p, "sgpt": b, "meta": m, "data": meta}

    @classmethod
    def load(cls, directory: str) -> "GptImage":
        meta_path = os.path.join(directory, "gpt.json")
        p = os.path.join(directory, "pgpt.bin")
        b = os.path.join(directory, "sgpt.bin")
        if not all(os.path.isfile(x) for x in (meta_path, p, b)):
            raise GptError("备份目录缺少 gpt.json / pgpt.bin / sgpt.bin")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("format") != "MTK9400_GPT_BACKUP" or meta.get("version") != 1:
            raise GptError("不是受支持的 GPT 备份格式")
        with open(p, "rb") as f:
            pdata = f.read()
        with open(b, "rb") as f:
            bdata = f.read()
        if hashlib.sha256(pdata).hexdigest() != meta.get("primary_sha256"):
            raise GptError("pgpt.bin SHA256 校验失败")
        if hashlib.sha256(bdata).hexdigest() != meta.get("backup_sha256"):
            raise GptError("sgpt.bin SHA256 校验失败")
        if len(pdata) != meta.get("primary_length") or len(bdata) != meta.get("backup_length"):
            raise GptError("GPT 备份长度与元数据不一致")
        ss = int(meta["sector_size"])
        bh = GptHeader.parse(bdata, ss, len(bdata) - ss)
        return cls.from_blocks(pdata, bdata, int(meta["total_sectors"]), ss,
                               backup_base_lba=bh.entries_lba)

    def restore_plan(self, target_total_sectors: int, target_sector_size: int,
                     target_disk_guid: str = None, allow_other_disk: bool = False):
        errors = self.validate(strict_mbr=True)
        if errors:
            raise GptError("备份校验失败：" + "；".join(errors))
        if target_sector_size != self.sector_size:
            raise GptError("目标扇区大小 %d 与备份 %d 不一致" %
                           (target_sector_size, self.sector_size))
        if target_total_sectors != self.total_sectors:
            raise GptError("目标磁盘容量 %d 扇区与备份 %d 不一致" %
                           (target_total_sectors, self.total_sectors))
        if target_disk_guid and target_disk_guid.upper() != self.disk_guid.upper() and not allow_other_disk:
            raise GptError("目标磁盘 GUID 与备份不一致")
        backup_offset = self.backup_start_lba * self.sector_size
        return {
            "primary_offset": 0,
            "primary_length": len(self.primary_raw),
            "primary_data": self.primary_raw,
            "backup_offset": backup_offset,
            "backup_length": len(self.backup_raw),
            "backup_data": self.backup_raw,
            "order": ["backup", "primary"],
            "sector_size": self.sector_size,
            "total_sectors": self.total_sectors,
        }


def build_image(entries: Iterable[GptEntry], total_sectors: int, sector_size: int = 512,
                disk_guid: bytes = None, entry_count: int = DEFAULT_ENTRY_COUNT,
                entry_size: int = DEFAULT_ENTRY_SIZE,
                first_usable: int = None, last_usable: int = None) -> GptImage:
    if sector_size not in SECTOR_SIZES:
        raise GptError("扇区大小必须是 512 或 4096")
    if total_sectors < 64:
        raise GptError("磁盘太小")
    if disk_guid is None:
        disk_guid = uuid.uuid4().bytes
    entries = [GptEntry(e.type_guid, e.unique_guid, e.first_lba, e.last_lba,
                        e.attrs, e.name_raw) for e in entries]
    array_bytes = entry_count * entry_size
    array_sectors = (array_bytes + sector_size - 1) // sector_size
    default_first = 2 + array_sectors
    backup_entries_lba = total_sectors - 1 - array_sectors
    default_last = backup_entries_lba - 1
    first_usable = default_first if first_usable is None else int(first_usable)
    last_usable = default_last if last_usable is None else int(last_usable)
    if first_usable < default_first or first_usable > last_usable:
        raise GptError("First Usable LBA 与主 GPT 冲突")
    if last_usable > default_last:
        raise GptError("Last Usable LBA 与备份 GPT 冲突")
    for e in entries:
        if e.used and (e.first_lba < first_usable or e.last_lba > last_usable):
            raise GptError("分区 %s 超出 GPT 可用范围" % _name_from_raw(e.name_raw))
    entries_raw = build_entries_raw(entries, entry_count, entry_size)
    ecrc = zlib.crc32(entries_raw) & 0xFFFFFFFF

    ph = GptHeader(GPT_SIGNATURE, 0x00010000, 92, 0, 0, 1,
                   total_sectors - 1, first_usable, last_usable, disk_guid,
                   2, entry_count, entry_size, ecrc)
    bh = GptHeader(GPT_SIGNATURE, 0x00010000, 92, 0, 0,
                   total_sectors - 1, 1, first_usable, last_usable, disk_guid,
                   backup_entries_lba, entry_count, entry_size, ecrc)
    primary = bytearray(2 * sector_size + array_bytes)
    primary[0:512] = _protective_mbr(total_sectors)
    primary[sector_size:sector_size + sector_size] = ph.to_bytes(sector_size)
    primary[2 * sector_size:2 * sector_size + array_bytes] = entries_raw
    # primary length must be sector-aligned
    plen = (2 * sector_size + array_bytes + sector_size - 1) // sector_size * sector_size
    primary = primary[:plen]
    backup = bytearray((total_sectors - backup_entries_lba) * sector_size)
    backup[0:array_bytes] = entries_raw
    hoff = (total_sectors - 1 - backup_entries_lba) * sector_size
    backup[hoff:hoff + sector_size] = bh.to_bytes(sector_size)
    img = GptImage(sector_size, total_sectors, ph, bh,
                   [e for e in entries if e.used], bytes(primary), bytes(backup),
                   backup_start_lba=backup_entries_lba)
    # recompute header objects from actual bytes so CRC fields are valid
    img.primary = GptHeader.parse(img.primary_raw, sector_size, sector_size)
    img.backup = GptHeader.parse(img.backup_raw, sector_size, len(img.backup_raw) - sector_size)
    img._validate_basic()
    return img


def build_from_layout(partitions, total_sectors: int, sector_size: int = 512,
                      disk_guid: bytes = None,
                      entry_count: int = DEFAULT_ENTRY_COUNT,
                      entry_size: int = DEFAULT_ENTRY_SIZE) -> GptImage:
    """从 scatter 的 start/size（字节）生成 GPT。

    partitions 每项至少 name/start/size。地址按 physical_start_addr 处理。
    """
    if sector_size not in SECTOR_SIZES:
        raise GptError("扇区大小必须是 512 或 4096")
    entries = []
    seen = set()
    array_sectors = (entry_count * entry_size + sector_size - 1) // sector_size
    first_usable = 2 + array_sectors
    for p in partitions:
        name = str(p.get("name") or "").strip()
        start = int(p.get("start") or p.get("physical_start_addr") or 0)
        size = int(p.get("size") or p.get("partition_size") or 0)
        if not name or start <= 0 or size <= 0:
            continue
        if name in seen:
            raise GptError("scatter 分区重复：" + name)
        seen.add(name)
        if start % sector_size or size % sector_size:
            raise GptError("分区 %s 的地址或大小未按扇区对齐" % name)
        first_lba = start // sector_size
        last_lba = first_lba + size // sector_size - 1
        if first_lba < first_usable:
            raise GptError("分区 %s 与 GPT 区重叠" % name)
        if last_lba >= total_sectors:
            raise GptError("分区 %s 超出磁盘容量" % name)
        entries.append(GptEntry(EFI_BASIC_DATA_GUID, uuid.uuid4().bytes,
                                first_lba, last_lba, 0, _name_to_raw(name)))
    if not entries:
        raise GptError("scatter 没有可生成 GPT 的分区")
    entries.sort(key=lambda e: e.first_lba)
    return build_image(entries, total_sectors, sector_size, disk_guid,
                       entry_count, entry_size)


def disk_bytes(image: GptImage) -> bytes:
    disk = bytearray(image.total_sectors * image.sector_size)
    disk[:len(image.primary_raw)] = image.primary_raw
    off = image.backup_start_lba * image.sector_size
    disk[off:off + len(image.backup_raw)] = image.backup_raw
    return bytes(disk)


def parse_disk_file(path: str) -> GptImage:
    size = os.path.getsize(path)
    for ss in SECTOR_SIZES:
        if size % ss:
            continue
        total = size // ss
        with open(path, "rb") as f:
            first = f.read(min(size, 0x10000))
            if len(first) < ss * 2:
                continue
            try:
                ph = GptHeader.parse(first, ss, ss)
            except GptError:
                continue
            lastlen = min(size, max(0x10000, (ph.entry_count * ph.entry_size) + 3 * ss))
            lastlen = (lastlen + ss - 1) // ss * ss
            f.seek(max(0, size - lastlen))
            last = f.read(lastlen)
        base_lba = max(0, (size - lastlen) // ss)
        try:
            return GptImage.from_blocks(first, last, total, ss,
                                        backup_base_lba=base_lba)
        except GptError:
            continue
    raise GptError("无法从磁盘镜像解析 GPT")
