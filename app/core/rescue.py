# -*- coding: utf-8 -*-
"""救砖包：GPT 原始扇区、分区镜像、清单与全局恢复计划。

包结构（ZIP_STORED，ZIP64）：
    manifest.json
    hashes.sha256.json
    gpt/primary.bin      主 GPT 原始扇区（保护 MBR + 头 + 分区数组）
    gpt/backup.bin       备份 GPT 原始扇区（分区数组 + 头）
    gpt/gpt.json         解析后的 GPT 信息
    partitions/<name>.bin
    README.txt

设计原则：
- 包是自包含的，恢复时不依赖内置 97 分区表；
- GPT 原始数据和解析结果都保存，恢复前做严格对比；
- 任何尺寸、SHA256、CRC、机型、磁盘大小不一致都拒绝；
- 全量包才允许全局恢复，部分包只能提示，不允许救砖。
"""
import datetime
import hashlib
import json
import os
import struct
import uuid
import zipfile


VERSION = 1
MANIFEST = "manifest.json"
HASHES = "hashes.sha256.json"
GPT_PRIMARY = "gpt/primary.bin"
GPT_BACKUP = "gpt/backup.bin"
GPT_JSON = "gpt/gpt.json"
PART_DIR = "partitions"
PRELOADER_DIR = "preloader"
PRELOADER_FILE = PRELOADER_DIR + "/preloader_raw.bin"
CHUNK = 4 * 1024 * 1024
GPT_ENTRY_COUNT = 128
GPT_ENTRY_SIZE = 128
GPT_PRIMARY_SECTORS = 34
GPT_BACKUP_SECTORS = 33

# 定制包：只允许官方白名单里的系统/引导/固件分区。
# 私人校准、IMEI、安全、日志、预留分区一律不进包。
PRIVATE_BLOCK = {
    "userdata", "nvram", "nvdata", "nvcfg", "persist", "protect1", "protect2",
    "sec1", "proinfo", "ocdt", "frp", "md_sec", "misc", "boot_para",
    "dram_para", "metadata", "expdb", "pstore", "mrdump", "hybridswap",
    "oplusreserve1", "oplusreserve2", "oplusreserve3", "oplusreserve4",
    "oplusreserve5", "oplusreserve6", "splash_odm", "seccfg", "otp",
    "flashinfo", "vb", "para", "preloader", "preloader_a", "preloader_b",
    "preloader_raw", "preloader_raw_a", "preloader_raw_b", "pgpt", "sgpt",
    "bootloader", "bootloader_a", "bootloader_b", "sda", "sdb", "sdc",
}

CURATED_REQUIRED = {
    "super", "boot_a", "boot_b", "vendor_boot_a", "vendor_boot_b",
    "init_boot_a", "init_boot_b", "vbmeta_a", "vbmeta_b",
    "vbmeta_system_a", "vbmeta_system_b",
    "vbmeta_vendor_a", "vbmeta_vendor_b",
    "modem_a", "modem_b",
}


class RescueError(Exception):
    pass


def _u32(data):
    return struct.unpack_from("<I", data, 0)[0]


def crc32(data):
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def _guid_str(raw):
    try:
        return str(uuid.UUID(bytes_le=raw))
    except Exception:
        return raw.hex()


def _guid_raw(text):
    return uuid.UUID(text).bytes_le


def _name(raw):
    try:
        return raw.decode("utf-16-le", "ignore").split("\x00", 1)[0]
    except Exception:
        return ""


def sha256_file(path, progress=None, stop=None):
    h = hashlib.sha256()
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            if stop is not None and stop():
                return None
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(done, total)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _parse_header(header):
    if len(header) < 92:
        raise RescueError("GPT 头长度不足")
    (sig, rev, hsize, hcrc, _res, cur, backup, first, last,
     disk_guid, entry_lba, n_entries, e_size, ecrc) = struct.unpack_from(
        "<8sIIIIQQQQ16sQIII", header, 0)
    if sig != b"EFI PART":
        raise RescueError("GPT 签名不正确")
    if hsize < 92 or hsize > len(header):
        raise RescueError("GPT 头大小异常")
    zeroed = bytearray(header[:hsize])
    zeroed[16:20] = b"\x00\x00\x00\x00"
    if crc32(bytes(zeroed)) != hcrc:
        raise RescueError("GPT 头 CRC 校验失败")
    if n_entries <= 0 or n_entries > 4096:
        raise RescueError("GPT 分区项数量异常")
    if e_size < 128 or e_size > 512:
        raise RescueError("GPT 分区项大小异常")
    return {
        "revision": rev, "header_size": hsize, "header_crc32": hcrc,
        "current_lba": cur, "backup_lba": backup, "first_usable": first,
        "last_usable": last, "disk_guid": _guid_str(disk_guid),
        "entry_lba": entry_lba, "num_entries": n_entries,
        "entry_size": e_size, "entries_crc32": ecrc,
    }


def _parse_entries(entries, hdr):
    n, esz = hdr["num_entries"], hdr["entry_size"]
    need = n * esz
    if len(entries) < need:
        raise RescueError("GPT 分区数组不完整")
    entries = entries[:need]
    if crc32(entries) != hdr["entries_crc32"]:
        raise RescueError("GPT 分区数组 CRC 校验失败")
    out = []
    for i in range(n):
        raw = entries[i * esz:(i + 1) * esz]
        if len(raw) < 128:
            break
        type_raw, unique_raw, first, last, flags, name_raw = struct.unpack_from(
            "<16s16sQQQ72s", raw, 0)
        if type_raw == b"\x00" * 16:
            continue
        if last < first:
            raise RescueError("GPT 分区 %d 的 LBA 范围异常" % i)
        out.append({
            "index": i,
            "name": _name(name_raw),
            "type_guid": _guid_str(type_raw),
            "unique_guid": _guid_str(unique_raw),
            "first_lba": int(first),
            "last_lba": int(last),
            "sectors": int(last - first + 1),
            "size": int((last - first + 1) * hdr.get("sector_size", 0)),
            "flags": int(flags),
        })
    if not out:
        raise RescueError("GPT 没有任何有效分区")
    return out


def parse_gpt_raw(primary, backup=None):
    """解析主 GPT 原始数据，返回严格校验后的结构。

    primary 从 LBA0 开始，至少覆盖 34 个扇区。
    backup 从备份分区数组开始，覆盖 33 个扇区。
    """
    if len(primary) < 1024:
        raise RescueError("主 GPT 原始数据太短")
    sector_size = None
    header_off = None
    for ss in (512, 4096):
        if len(primary) >= ss * 2 and primary[ss:ss + 8] == b"EFI PART":
            sector_size, header_off = ss, ss
            break
    if sector_size is None:
        raise RescueError("找不到 GPT 头（512/4096 扇区均失败）")
    if len(primary) < GPT_PRIMARY_SECTORS * sector_size:
        raise RescueError("主 GPT 原始数据不足 34 个扇区")
    hdr = _parse_header(primary[header_off:header_off + 512])
    hdr["sector_size"] = sector_size
    if hdr["current_lba"] != 1:
        raise RescueError("GPT 头当前 LBA 异常")
    ent_off = hdr["entry_lba"] * sector_size
    entries = primary[ent_off:ent_off + hdr["num_entries"] * hdr["entry_size"]]
    parts = _parse_entries(entries, hdr)
    total_sectors = int(hdr["last_usable"]) + 34
    hdr["total_sectors"] = total_sectors
    hdr["total_size"] = total_sectors * sector_size
    hdr["partitions"] = parts

    if backup is not None:
        if len(backup) < GPT_BACKUP_SECTORS * sector_size:
            raise RescueError("备份 GPT 原始数据不足 33 个扇区")
        bh_off = len(backup) - sector_size
        bh = _parse_header(backup[bh_off:bh_off + 512])
        bh["sector_size"] = sector_size
        if bh["current_lba"] != total_sectors - 1:
            raise RescueError("备份 GPT 头 LBA 与主 GPT 不一致")
        if bh["disk_guid"] != hdr["disk_guid"]:
            raise RescueError("主/备份 GPT 磁盘 GUID 不一致")
        if bh["num_entries"] != hdr["num_entries"] or bh["entry_size"] != hdr["entry_size"]:
            raise RescueError("主/备份 GPT 分区数组参数不一致")
        b_entries = backup[:bh["num_entries"] * bh["entry_size"]]
        b_parts = _parse_entries(b_entries, bh)
        a_sig = [(p["name"], p["first_lba"], p["last_lba"], p["unique_guid"]) for p in parts]
        b_sig = [(p["name"], p["first_lba"], p["last_lba"], p["unique_guid"]) for p in b_parts]
        if a_sig != b_sig:
            raise RescueError("主/备份 GPT 分区内容不一致")
        hdr["backup_header_crc32"] = bh["header_crc32"]
    return hdr


def gpt_summary(gpt):
    return {
        "sector_size": gpt["sector_size"],
        "total_sectors": gpt["total_sectors"],
        "total_size": gpt["total_size"],
        "disk_guid": gpt["disk_guid"],
        "header_crc32": gpt["header_crc32"],
        "entries_crc32": gpt["entries_crc32"],
        "backup_header_crc32": gpt.get("backup_header_crc32"),
        "partitions": [
            {k: p[k] for k in ("name", "type_guid", "unique_guid", "first_lba",
                               "last_lba", "sectors", "size", "flags")}
            for p in gpt["partitions"]
        ],
    }


def compare_gpt(a, b):
    """严格比较两份解析后的 GPT，返回差异列表。"""
    diffs = []
    for k in ("sector_size", "total_sectors", "disk_guid", "header_crc32",
              "entries_crc32", "backup_header_crc32"):
        if a.get(k) != b.get(k):
            diffs.append(k)
    pa = {p["name"]: p for p in a.get("partitions", [])}
    pb = {p["name"]: p for p in b.get("partitions", [])}
    if set(pa) != set(pb):
        diffs.append("partition_set")
    for n in sorted(set(pa) & set(pb)):
        for k in ("type_guid", "unique_guid", "first_lba", "last_lba", "flags"):
            if pa[n].get(k) != pb[n].get(k):
                diffs.append("%s.%s" % (n, k))
    return diffs


def partition_names(gpt):
    return [p["name"] for p in gpt["partitions"]]


def user_partitions(gpt):
    return [p for p in gpt["partitions"] if p["name"] == "userdata"]


def build_raw_gpt(partitions, disk_guid, total_sectors, sector_size=512):
    """由分区列表生成主/备份 GPT 原始数据（用于测试和应急重建）。

    partitions: [{name,type_guid,unique_guid,first_lba,last_lba,flags}]
    """
    if total_sectors < 100 or total_sectors > 0xFFFFFFFFFFFF:
        raise RescueError("总扇区数异常")
    if disk_guid is None:
        disk_guid = str(uuid.uuid4())
    dguid = _guid_raw(disk_guid) if isinstance(disk_guid, str) else disk_guid
    entries = bytearray(GPT_ENTRY_COUNT * GPT_ENTRY_SIZE)
    for i, p in enumerate(partitions[:GPT_ENTRY_COUNT]):
        type_raw = _guid_raw(p["type_guid"]) if isinstance(p["type_guid"], str) else p["type_guid"]
        uniq_raw = _guid_raw(p["unique_guid"]) if isinstance(p["unique_guid"], str) else p["unique_guid"]
        name = p.get("name", "")[:36]
        name_raw = name.encode("utf-16-le")[:72].ljust(72, b"\x00")
        struct.pack_into("<16s16sQQQ72s", entries, i * GPT_ENTRY_SIZE,
                         type_raw, uniq_raw, int(p["first_lba"]), int(p["last_lba"]),
                         int(p.get("flags", 0)), name_raw)
    ecrc = crc32(bytes(entries))
    first_usable = 34
    last_usable = total_sectors - 34

    def make_header(cur, backup_lba, entry_lba):
        h = struct.pack("<8sIIIIQQQQ16sQIII", b"EFI PART", 0x10000, 92, 0, 0,
                        cur, backup_lba, first_usable, last_usable,
                        dguid, entry_lba, GPT_ENTRY_COUNT, GPT_ENTRY_SIZE, ecrc)
        h = bytearray(h)
        h[16:20] = struct.pack("<I", crc32(bytes(h)))
        return bytes(h)

    h1 = make_header(1, total_sectors - 1, 2)
    primary = bytearray(GPT_PRIMARY_SECTORS * sector_size)
    primary[0x1FE:0x200] = b"\x55\xAA"
    primary[0x1BE:0x1CE] = struct.pack("<B3sB3sII", 0, b"\x00\x02\x00", 0xEE,
                                       b"\xff\xff\xff", 1, min(total_sectors - 1, 0xFFFFFFFF))
    primary[sector_size:sector_size + 92] = h1
    primary[2 * sector_size:2 * sector_size + len(entries)] = entries
    backup = bytearray(GPT_BACKUP_SECTORS * sector_size)
    backup[0:len(entries)] = entries
    bh = make_header(total_sectors - 1, 1, total_sectors - GPT_BACKUP_SECTORS)
    backup[-sector_size:-sector_size + 92] = bh
    return bytes(primary), bytes(backup), gpt_summary(parse_gpt_raw(bytes(primary), bytes(backup)))


def backup_from_primary(primary):
    """由主 GPT 原始数据重建备份 GPT 原始数据。

    不能重新生成 128 项/34 起始的“标准 GPT”：这台机器的真实 GPT
    可能是 97 项、first_usable=8、disk_guid 全零。备份头必须原样保留
    主头的 num_entries、entry_size、first/last usable、disk GUID 和
    分区数组，只改变 current/backup/entry_lba。
    """
    gpt = parse_gpt_raw(primary)
    sec = gpt["sector_size"]
    header_size = gpt["header_size"]
    h = bytearray(primary[sec:sec + header_size])
    if len(h) < header_size:
        raise RescueError("主 GPT 头不完整")
    entries = primary[gpt["entry_lba"] * sec:
                      gpt["entry_lba"] * sec + gpt["num_entries"] * gpt["entry_size"]]
    if len(entries) != gpt["num_entries"] * gpt["entry_size"]:
        raise RescueError("主 GPT 分区数组不完整")
    total = gpt["total_sectors"]
    struct.pack_into("<Q", h, 24, total - 1)       # current_lba
    struct.pack_into("<Q", h, 32, 1)               # backup_lba
    struct.pack_into("<Q", h, 72, total - 33)      # entry_lba
    h[16:20] = b"\x00" * 4
    struct.pack_into("<I", h, 16, crc32(bytes(h)))
    backup_len = 33 * sec
    backup = bytearray(backup_len)
    backup[:len(entries)] = entries
    backup[-sec:-sec + header_size] = h
    out = bytes(backup)
    parse_gpt_raw(primary, out)
    return out


def _safe_name(name):
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise RescueError("非法分区名：%r" % name)
    return name


def _zip_names(zf):
    names = set()
    for info in zf.infolist():
        n = info.filename.replace("\\", "/")
        if n.startswith("/") or ".." in n.split("/"):
            raise RescueError("压缩包内路径非法：%s" % n)
        if n in names:
            raise RescueError("压缩包内文件重复：%s" % n)
        names.add(n)
    return names


def _file_entry(name, path):
    st = os.path.getsize(path)
    digest = sha256_file(path)
    return {"name": name, "file": name + ".bin", "size": st, "sha256": digest}


def create_package(zip_path, backup_dir, gpt_primary_path, gpt_backup_path,
                   device=None, package_type="full", progress=None, stop=None,
                   include_names=None, required_names=None, extra=None,
                   preloader_raw=None):
    """从备份目录 + 原始 GPT 文件生成救砖包。

    package_type=full 时要求备份目录包含 GPT 的全部非 userdata 分区。
    package_type=curated 时只打包 include_names，并拒绝私人/校准/安全分区。
    """
    with open(gpt_primary_path, "rb") as f:
        primary = f.read()
    if not os.path.isfile(gpt_backup_path) or os.path.getsize(gpt_backup_path) == 0:
        backup = backup_from_primary(primary)
        with open(gpt_backup_path, "wb") as f:
            f.write(backup)
    with open(gpt_backup_path, "rb") as f:
        backup = f.read()
    try:
        parse_gpt_raw(primary, backup)
    except Exception:
        backup = backup_from_primary(primary)
        with open(gpt_backup_path, "wb") as f:
            f.write(backup)
    gpt = parse_gpt_raw(primary, backup)
    all_names = partition_names(gpt)
    gpt_sizes = {x["name"]: x["size"] for x in gpt["partitions"]}
    curated_info = None
    if package_type == "curated":
        if not include_names:
            raise RescueError("定制包没有 include_names")
        wanted = []
        seen = set()
        for n in include_names:
            n = str(n)
            if n in seen:
                continue
            seen.add(n)
            if n in PRIVATE_BLOCK:
                raise RescueError("定制包禁止包含私人/安全分区：%s" % n)
            if n not in gpt_sizes:
                raise RescueError("GPT 中没有分区：%s" % n)
            wanted.append(n)
        required = set(required_names or CURATED_REQUIRED)
        missing_required = required - seen
        if missing_required:
            raise RescueError("定制包缺少必需分区：%s" % ", ".join(sorted(missing_required)))
        if "super" not in seen:
            raise RescueError("定制包必须包含 super")
        existing = []
        for n in wanted:
            p = os.path.join(backup_dir, n + ".bin")
            if not os.path.isfile(p):
                raise RescueError("备份缺少分区：%s" % n)
            if os.path.getsize(p) != gpt_sizes[n]:
                raise RescueError("分区尺寸与 GPT 不一致：%s" % n)
            existing.append(n)
        curated_info = {
            "include": existing,
            "required": sorted(required),
            "exclude": sorted(PRIVATE_BLOCK),
            "rule": "official_ota_whitelist_no_private",
        }
    else:
        exclude = {"userdata"}
        wanted = [n for n in all_names if n not in exclude]
        existing = []
        if package_type == "full":
            for n in wanted:
                p = os.path.join(backup_dir, n + ".bin")
                if not os.path.isfile(p):
                    raise RescueError("备份缺少分区：%s" % n)
                if os.path.getsize(p) != gpt_sizes[n]:
                    raise RescueError("分区尺寸与 GPT 不一致：%s" % n)
                existing.append(n)
            if set(existing) != set(wanted):
                raise RescueError("全量包分区不完整")
        else:
            for n in wanted:
                p = os.path.join(backup_dir, n + ".bin")
                if not os.path.isfile(p):
                    continue
                if os.path.getsize(p) != gpt_sizes[n]:
                    raise RescueError("分区尺寸与 GPT 不一致：%s" % n)
                existing.append(n)
    if not existing:
        raise RescueError("没有可打包的分区")

    entries = []
    old_manifest = {}
    try:
        old_path = os.path.join(backup_dir, "manifest.sha256.json")
        if os.path.isfile(old_path):
            with open(old_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for e in old_data.get("files", []):
                if e.get("partition"):
                    old_manifest[e["partition"]] = e
    except Exception:
        old_manifest = {}
    for i, n in enumerate(existing, 1):
        if stop is not None and stop():
            raise RescueError("已取消")
        if progress:
            progress(i, len(existing), n)
        ent = _file_entry(n, os.path.join(backup_dir, n + ".bin"))
        old = old_manifest.get(n)
        if old and old.get("sha256"):
            if int(old.get("size", -1)) != int(ent["size"]) or old["sha256"] != ent["sha256"]:
                raise RescueError("源备份文件与旧清单不一致：%s" % n)
        entries.append(ent)
    gpt_info = gpt_summary(gpt)
    preloader_meta = None
    if preloader_raw:
        if isinstance(preloader_raw, dict):
            pre_src = preloader_raw.get("path")
            pre_parttype = str(preloader_raw.get("parttype") or "lu0")
            pre_offset = int(preloader_raw.get("offset") or 0)
            pre_source = str(preloader_raw.get("source") or "official_ota")
        else:
            pre_src = preloader_raw
            pre_parttype = "lu0"
            pre_offset = 0
            pre_source = "official_ota"
        if not pre_src or not os.path.isfile(pre_src):
            raise RescueError("preloader_raw 文件不存在")
        pre_size = os.path.getsize(pre_src)
        preloader_meta = {
            "file": PRELOADER_FILE,
            "size": pre_size,
            "sha256": sha256_file(pre_src),
            "parttype": pre_parttype,
            "offset": pre_offset,
            "write_mode": "manual_confirmed",
            "source": pre_source,
        }
    manifest = {
        "version": VERSION,
        "package_type": package_type,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": "MTK9400GUI",
        "device": dict(device or {}),
        "gpt": {
            "primary": GPT_PRIMARY,
            "backup": GPT_BACKUP,
            "primary_size": len(primary),
            "backup_size": len(backup),
            "primary_sha256": sha256_bytes(primary),
            "backup_sha256": sha256_bytes(backup),
            "info": gpt_info,
        },
        "partitions": entries,
        "userdata_included": False,
    }
    if curated_info is not None:
        manifest["curated"] = curated_info
    if extra:
        manifest["source"] = dict(extra)
    if preloader_meta is not None:
        manifest["preloader_raw"] = preloader_meta
    hashes = {
        "version": VERSION,
        "algorithm": "sha256",
        "files": [
            {"file": GPT_PRIMARY, "size": len(primary), "sha256": manifest["gpt"]["primary_sha256"]},
            {"file": GPT_BACKUP, "size": len(backup), "sha256": manifest["gpt"]["backup_sha256"]},
        ] + [{"file": PART_DIR + "/" + e["file"], "size": e["size"], "sha256": e["sha256"]}
             for e in entries] + (
            [{"file": PRELOADER_FILE, "size": preloader_meta["size"],
              "sha256": preloader_meta["sha256"]}] if preloader_meta else []),
    }
    readme = (
        "MTK9400 救砖包\n"
        "类型：%s\n"
        "分区数：%d\n"
        "用途：全局恢复 / GPT 重建（仅限同机型同 GPT）\n"
        "警告：非本机备份包禁止刷入。\n" % (package_type, len(entries))
    )
    if curated_info is not None:
        readme += "定制规则：仅官方白名单，排除私人/校准/安全分区。\n"
    if preloader_meta is not None:
        readme += (
            "包含 preloader_raw：%s\n"
            "preloader_raw 不按 GPT 分区名写入，默认不自动刷写。\n"
            "只有确认目标 parttype=%s、offset=0x%x 后才允许手动写入。\n"
            % (preloader_meta["file"], preloader_meta["parttype"], preloader_meta["offset"])
        )
    tmp = zip_path + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED,
                             allowZip64=True) as zf:
            def add(name, data):
                if stop is not None and stop():
                    raise RescueError("已取消")
                zf.writestr(name, data)
            add(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
            add(HASHES, json.dumps(hashes, ensure_ascii=False, indent=1).encode("utf-8"))
            add(GPT_JSON, json.dumps(gpt_info, ensure_ascii=False, indent=1).encode("utf-8"))
            add(GPT_PRIMARY, primary)
            add(GPT_BACKUP, backup)
            add("README.txt", readme.encode("utf-8"))
            for e in entries:
                path = os.path.join(backup_dir, e["file"])
                if stop is not None and stop():
                    raise RescueError("已取消")
                zf.write(path, PART_DIR + "/" + e["file"])
            if preloader_meta is not None:
                zf.write(pre_src, PRELOADER_FILE)
        os.replace(tmp, zip_path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise
    digest = sha256_file(zip_path)
    with open(zip_path + ".sha256", "w", encoding="utf-8") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(zip_path)))
    # 写完立即重新打开校验，防止 ZIP 写入过程中损坏。
    inspect_package(zip_path, verify_hashes=True)
    return {"zip": zip_path, "sha256": digest, "manifest": manifest, "verified": True}


def load_manifest_from_zip(zf):
    try:
        raw = zf.read(MANIFEST)
    except KeyError:
        raise RescueError("缺少 manifest.json")
    try:
        m = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RescueError("manifest.json 解析失败：%s" % e)
    if m.get("version") != VERSION:
        raise RescueError("救砖包版本不支持")
    if m.get("package_type") not in ("full", "partial", "curated"):
        raise RescueError("救砖包类型异常")
    return m


def inspect_package(zip_path, verify_hashes=True, progress=None, stop=None):
    """打开并校验救砖包，返回 {manifest, gpt, entries, zip_sha256}。"""
    if not os.path.isfile(zip_path):
        raise RescueError("文件不存在：%s" % zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = _zip_names(zf)
        if MANIFEST not in names:
            raise RescueError("不是救砖包：缺少 manifest.json")
        m = load_manifest_from_zip(zf)
        g = m.get("gpt") or {}
        for key in ("primary", "backup"):
            if g.get(key) not in names:
                raise RescueError("救砖包缺少 GPT 原始数据：%s" % key)
        primary = zf.read(g["primary"])
        backup = zf.read(g["backup"])
        if sha256_bytes(primary) != g.get("primary_sha256"):
            raise RescueError("GPT 主数据 SHA256 不符")
        if sha256_bytes(backup) != g.get("backup_sha256"):
            raise RescueError("GPT 备份数据 SHA256 不符")
        gpt = parse_gpt_raw(primary, backup)
        if gpt_summary(gpt) != g.get("info"):
            raise RescueError("GPT 解析信息与清单不一致")
        entries = m.get("partitions") or []
        part_names = [e.get("name") for e in entries]
        if len(part_names) != len(set(part_names)):
            raise RescueError("分区文件重复")
        all_names = set(partition_names(gpt))
        if not set(part_names) <= all_names:
            raise RescueError("清单包含 GPT 中不存在的分区")
        if "userdata" in part_names:
            raise RescueError("救砖包不能包含 userdata")
        if m.get("package_type") == "full":
            wanted = all_names - {"userdata"}
            if set(part_names) != wanted:
                raise RescueError("全量包分区不完整")
        elif m.get("package_type") == "curated":
            info = m.get("curated")
            if not isinstance(info, dict) or not info.get("include"):
                raise RescueError("定制包缺少 curated.include")
            include = {str(x) for x in info.get("include")}
            if set(part_names) != include:
                raise RescueError("定制包分区清单与 curated.include 不一致")
            required = {str(x) for x in (info.get("required") or CURATED_REQUIRED)}
            if not required <= include:
                raise RescueError("定制包缺少必需分区：%s" % ", ".join(sorted(required - include)))
            bad = include & PRIVATE_BLOCK
            if bad:
                raise RescueError("定制包包含私人/安全分区：%s" % ", ".join(sorted(bad)))
            if "super" not in include:
                raise RescueError("定制包必须包含 super")
        for i, e in enumerate(entries, 1):
            if stop is not None and stop():
                raise RescueError("已取消")
            arc = PART_DIR + "/" + str(e.get("file") or "")
            if arc not in names:
                raise RescueError("缺少分区文件：%s" % arc)
            info = zf.getinfo(arc)
            if info.file_size != int(e.get("size", -1)):
                raise RescueError("分区文件尺寸不符：%s" % e.get("name"))
            if verify_hashes:
                h = hashlib.sha256()
                with zf.open(arc, "r") as f:
                    while True:
                        if stop is not None and stop():
                            raise RescueError("已取消")
                        b = f.read(CHUNK)
                        if not b:
                            break
                        h.update(b)
                if h.hexdigest() != e.get("sha256"):
                    raise RescueError("分区文件 SHA256 不符：%s" % e.get("name"))
            if progress:
                progress(i, len(entries), e.get("name"))
        preloader = None
        pre = m.get("preloader_raw")
        if pre:
            if pre.get("file") != PRELOADER_FILE:
                raise RescueError("preloader_raw 文件路径异常")
            if pre.get("size") is None or pre.get("sha256") is None:
                raise RescueError("preloader_raw 元数据不完整")
            if PRELOADER_FILE not in names:
                raise RescueError("缺少 preloader_raw 文件")
            info = zf.getinfo(PRELOADER_FILE)
            if info.file_size != int(pre["size"]):
                raise RescueError("preloader_raw 尺寸不符")
            if verify_hashes:
                h = hashlib.sha256()
                with zf.open(PRELOADER_FILE, "r") as f:
                    while True:
                        if stop is not None and stop():
                            raise RescueError("已取消")
                        b = f.read(CHUNK)
                        if not b:
                            break
                        h.update(b)
                if h.hexdigest() != pre["sha256"]:
                    raise RescueError("preloader_raw SHA256 不符")
            preloader = pre
        else:
            preloader = None
    digest = sha256_file(zip_path)
    sidecar = zip_path + ".sha256"
    sidecar_ok = False
    if os.path.isfile(sidecar):
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                want = f.read().split()[0].strip().lower()
            if want != digest:
                raise RescueError("zip 的 SHA256 与 .sha256 文件不一致")
            sidecar_ok = True
        except RescueError:
            raise
        except Exception as e:
            raise RescueError("读取 zip 的 SHA256 失败：%s" % e)
    return {"manifest": m, "gpt": gpt, "entries": entries,
            "preloader": preloader,
            "zip_sha256": digest, "sidecar_ok": sidecar_ok}


def current_gpt_status(primary, backup):
    try:
        gpt = parse_gpt_raw(primary, backup)
        return "ok", gpt, []
    except Exception as e:
        return "damaged", None, [str(e)]


def plan_restore(package, prefix="", rebuild=False, wipe_userdata=True,
                 flash_preloader=False):
    """生成相对 WORK 的 mtkclient 脚本命令。

    救砖模式允许 GPT、preloader、bootloader 等底层分区；
    seccfg、otp、flashinfo、pgpt、sgpt 永远不按分区名写。
    """
    m = package["manifest"]
    g = m["gpt"]
    gpt = package["gpt"]
    sec = gpt["sector_size"]
    total = gpt["total_sectors"]
    backup_len = g["backup_size"]
    backup_off = (total - int(backup_len / sec)) * sec
    pre = (prefix.rstrip("\\/") + "\\") if prefix else ""
    skip = {"userdata", "seccfg", "otp", "flashinfo", "pgpt", "sgpt"}
    cmds = []
    if rebuild:
        cmds.append("wo 0 0x%x %s%s" % (g["primary_size"], pre, g["primary"]))
        cmds.append("wo 0x%x 0x%x %s%s" % (backup_off, backup_len, pre, g["backup"]))
        cmds.append("printgpt")
    for e in m["partitions"]:
        if e["name"] in skip:
            continue
        cmds.append("w %s %s%s/%s" % (e["name"], pre, PART_DIR, e["file"]))
    cmds.append("printgpt")
    if wipe_userdata and "userdata" in partition_names(gpt):
        cmds.append("e userdata")
    if flash_preloader and package.get("preloader"):
        pl = package["preloader"]
        cmds.append("wo 0x%x 0x%x %s%s --parttype %s"
                    % (int(pl.get("offset") or 0), int(pl["size"]),
                       pre, pl["file"], pl.get("parttype") or "lu0"))
    cmds.append("reset")
    # 路径都是 WORK 下的相对路径；子进程 cwd 固定为 WORK。
    return cmds


def write_rescue_script(path, commands):
    with open(path, "w", encoding="ascii") as f:
        for c in commands:
            f.write(c + "\n")


def extract_package(zip_path, dest, progress=None, stop=None):
    """解压并逐个校验；只允许包内已知文件。"""
    os.makedirs(dest, exist_ok=True)
    res = inspect_package(zip_path, verify_hashes=True, progress=progress, stop=stop)
    manifest = res["manifest"]
    expected = {
        GPT_PRIMARY: (manifest["gpt"]["primary_size"], manifest["gpt"]["primary_sha256"]),
        GPT_BACKUP: (manifest["gpt"]["backup_size"], manifest["gpt"]["backup_sha256"]),
    }
    for e in res["entries"]:
        expected[PART_DIR + "/" + e["file"]] = (int(e["size"]), e["sha256"])
    if res.get("preloader"):
        expected[PRELOADER_FILE] = (int(res["preloader"]["size"]), res["preloader"]["sha256"])
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            target = os.path.join(dest, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            h = hashlib.sha256()
            size = 0
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                while True:
                    if stop is not None and stop():
                        raise RescueError("已取消")
                    b = src.read(CHUNK)
                    if not b:
                        break
                    h.update(b)
                    size += len(b)
                    dst.write(b)
            if name in expected:
                want_size, want_hash = expected[name]
                if size != int(want_size) or h.hexdigest() != want_hash:
                    raise RescueError("解压后校验失败：%s" % name)
    return res


def package_full_size(package):
    n = sum(int(e["size"]) for e in package["entries"])
    return n
