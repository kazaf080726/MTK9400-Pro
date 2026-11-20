# -*- coding: utf-8 -*-
"""MTK scatter 解析、生成和刷写计划。

只做纯逻辑，不访问设备。GUI 负责把现场 GPT 的 offset/size 传进来，
执行层仍然走 mtkclient 的 script/w 命令。
"""
import os
import re
import shlex

HEX = re.compile(r"^0x[0-9a-fA-F]+$")


def _int(v, default=0):
    if v is None:
        return default
    v = str(v).strip()
    if not v:
        return default
    try:
        return int(v, 16) if v.lower().startswith("0x") else int(v, 10)
    except Exception:
        return default


def _bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _kv(line):
    if ":" not in line:
        return None, None
    k, v = line.split(":", 1)
    return k.strip().lstrip("-").strip(), v.strip()


class Entry(object):
    __slots__ = ("name", "file_name", "size", "start", "region", "download", "type",
                 "index", "raw")

    def __init__(self, name="", file_name="", size=0, start=0, region="UFS_LU2",
                 download=True, type_="", index=0):
        self.name = name
        self.file_name = file_name
        self.size = int(size or 0)
        self.start = int(start or 0)
        self.region = region or "UFS_LU2"
        self.download = bool(download)
        self.type = type_ or ""
        self.index = int(index or 0)
        self.raw = {}

    def as_dict(self):
        return {"name": self.name, "file_name": self.file_name, "size": self.size,
                "start": self.start, "region": self.region,
                "download": self.download, "type": self.type, "index": self.index}

    def __repr__(self):
        return "<Entry %s 0x%x 0x%x %s>" % (self.name, self.start, self.size, self.region)


class Scatter(object):
    def __init__(self, platform="MT6991", storage="UFS", block_size=0x20000,
                 project="", entries=None):
        self.platform = platform or "MT6991"
        self.storage = storage or "UFS"
        self.block_size = int(block_size or 0x20000)
        self.project = project or ""
        self.entries = list(entries or [])

    def by_name(self):
        return {e.name: e for e in self.entries}

    def download_entries(self):
        return [e for e in self.entries if e.download and e.name and not e.file_name.startswith("NONE")]

    def __repr__(self):
        return "<Scatter %s %s %d>" % (self.platform, self.storage, len(self.entries))


def parse(text):
    sc = Scatter()
    cur = None
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- general:"):
            cur = "general"
            continue
        if line.startswith("- partition_index:"):
            if cur is not None and cur != "general":
                sc.entries.append(cur)
            cur = Entry()
            continue
        k, v = _kv(line)
        if not k:
            continue
        if cur == "general" or cur is None:
            if k == "platform":
                sc.platform = v
            elif k == "storage":
                sc.storage = v
            elif k == "block_size":
                sc.block_size = _int(v, 0x20000)
            elif k == "project":
                sc.project = v
            continue
        if not isinstance(cur, Entry):
            continue
        if k == "partition_name":
            cur.name = v
        elif k == "file_name":
            cur.file_name = v
        elif k == "partition_size":
            cur.size = _int(v)
        elif k in ("physical_start_addr", "linear_start_addr"):
            cur.start = _int(v, cur.start)
        elif k == "region":
            cur.region = v
        elif k == "is_download":
            cur.download = _bool(v, True)
        elif k == "type":
            cur.type = v
        elif k == "partition_index":
            cur.index = _int(v)
        cur.raw[k] = v
    if isinstance(cur, Entry):
        sc.entries.append(cur)
    return sc


def load(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse(f.read())


def generate(entries, platform="MT6991", storage="UFS", project="",
             block_size=0x20000):
    """entries: 可迭代的 dict/Entry，需有 name/size/start。"""
    out = []
    out.append("#" * 100)
    out.append("#  General Setting")
    out.append("#" * 100)
    out.append("- general: MTK_PLATFORM_CFG")
    out.append("  info:")
    out.append("    - config_version: V1.1.2")
    out.append("      platform: %s" % (platform or "MT6991"))
    out.append("      project: %s" % (project or ""))
    out.append("      storage: %s" % (storage or "UFS"))
    out.append("      boot_channel: MSDC_0")
    out.append("      block_size: 0x%x" % int(block_size or 0x20000))
    norm = []
    for i, e in enumerate(entries):
        if isinstance(e, Entry):
            d = e.as_dict()
        else:
            d = dict(e)
        name = str(d.get("name") or d.get("partition_name") or "")
        if not name:
            continue
        norm.append((int(d.get("start") or d.get("offset") or 0), i, d, name))
    norm.sort(key=lambda x: (x[0], x[1]))
    for idx, (_start, _i, d, name) in enumerate(norm):
        size = int(d.get("size") or d.get("partition_size") or 0)
        start = int(d.get("start") or d.get("offset") or 0)
        region = d.get("region") or ("UFS_LU2" if (storage or "UFS").upper() == "UFS" else "EMMC_USER")
        download = bool(d.get("download", True))
        type_ = d.get("type") or ("SV5_BL_BIN" if name in ("preloader", "preloader_a", "preloader_b") else "EXT4")
        out.append("")
        out.append("- partition_index: SYS%d" % idx)
        out.append("  partition_name: %s" % name)
        out.append("  file_name: %s" % (d.get("file_name") or ("%s.bin" % name)))
        out.append("  is_download: %s" % ("true" if download else "false"))
        out.append("  type: %s" % type_)
        out.append("  linear_start_addr: 0x%x" % start)
        out.append("  physical_start_addr: 0x%x" % start)
        out.append("  partition_size: 0x%x" % size)
        out.append("  region: %s" % region)
        out.append("  storage: %s" % (storage or "UFS"))
        out.append("  boundary_check: true")
        out.append("  is_reserved: false")
        out.append("  operation_type: UPDATE")
        out.append("  reserve: 0x00")
    return "\n".join(out) + "\n"


def write(path, entries, **kw):
    text = generate(entries, **kw)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def normalize_name(name):
    return str(name or "").strip().replace("\\", "/").split("/")[-1]


def plan_directory(scatter, image_dir, live_sizes=None, blocked=None):
    """把目录里的镜像映射到 scatter 分区。

    返回 (plans, errors)。plans 每项:
      {"name","file","size","expected","start","region","action"}
    """
    blocked = set(blocked or ())
    live_sizes = live_sizes or {}
    errors = []
    plans = []
    by_file = {}
    for e in scatter.download_entries():
        fn = normalize_name(e.file_name)
        if fn and fn.upper() != "NONE":
            by_file[fn.lower()] = e
    try:
        names = sorted(os.listdir(image_dir))
    except Exception as exc:
        return [], ["无法读取镜像目录：%s" % exc]
    for fn in names:
        p = os.path.join(image_dir, fn)
        if not os.path.isfile(p):
            continue
        e = by_file.get(fn.lower())
        if e is None:
            stem = os.path.splitext(fn)[0]
            e = scatter.by_name().get(stem)
        if e is None:
            errors.append("找不到 scatter 分区：%s" % fn)
            continue
        if not e.download:
            errors.append("分区不允许下载：%s" % e.name)
            continue
        if e.name in blocked:
            errors.append("安全规则禁止写入：%s" % e.name)
            continue
        size = os.path.getsize(p)
        expected = int(live_sizes.get(e.name, e.size) or e.size)
        if expected and size > expected:
            errors.append("%s 镜像 %s 大于分区 %s" % (e.name, size, expected))
            continue
        if size == 0:
            errors.append("%s 镜像是空文件" % e.name)
            continue
        plans.append({"name": e.name, "file": p, "size": size,
                      "expected": expected, "start": e.start,
                      "region": e.region, "action": "write"})
    if not plans and not errors:
        errors.append("目录里没有可写入的镜像")
    return plans, errors


def script_lines(plans):
    """生成 mtkclient script 行：w 分区 路径。"""
    out = []
    for p in plans:
        out.append("w %s %s" % (p["name"], p["file"]))
    return out
