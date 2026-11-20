# -*- coding: utf-8 -*-
"""分区文件的哈希清单：备份/读取完成后生成，校验时逐文件比对。

清单格式（UTF-8 JSON）：
{
  "version": 1,
  "kind": "backup_critical",
  "created": "2026-11-09T03:40:00",
  "files": [
    {"partition": "nvram", "file": "nvram.bin", "size": 67108864, "sha256": "..."}
  ]
}
"""
import datetime
import hashlib
import json
import os

MANIFEST_NAME = "manifest.sha256.json"
CHUNK = 4 * 1024 * 1024


def file_digest(path, progress=None, stop=None):
    """流式 SHA256；progress(done_bytes, total_bytes)，stop() 为真时中止。"""
    h = hashlib.sha256()
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            if stop is not None and stop():
                return None
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
            done += len(block)
            if progress is not None:
                progress(done, total)
    return h.hexdigest()


def manifest_path(dir_path):
    return os.path.join(dir_path, MANIFEST_NAME)


def load_manifest(dir_path):
    p = manifest_path(dir_path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            return data
    except Exception:
        pass
    return None


def write_manifest(dir_path, kind, entries, extra=None):
    """原子写入清单：先写 .tmp，再 replace。"""
    payload = {
        "version": 1,
        "kind": kind,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": sorted(entries, key=lambda e: e["file"]),
    }
    if extra:
        payload.update(extra)
    os.makedirs(dir_path, exist_ok=True)
    target = manifest_path(dir_path)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, target)
    return payload


def scan_dir(dir_path, names, expected_sizes=None, kind="", write_missing=True,
             include_existing=False, stop=None, progress=None):
    """扫描一个目录，计算哈希并与已有清单比对。

    返回：
        {
          "dir", "kind", "complete", "stopped",
          "missing": [partition...], "bad_size": [(p, real, expected)...],
          "hash_mismatch": [partition...], "errors": [(p, str)...],
          "entries": [...], "manifest_written": bool,
        }
    """
    names = list(names or [])
    existing_manifest = load_manifest(dir_path)
    old_files = {}
    if existing_manifest:
        for e in existing_manifest.get("files", []):
            if isinstance(e, dict) and e.get("file"):
                old_files[e["file"]] = e
    if include_existing:
        try:
            for f in os.listdir(dir_path):
                if f.lower().endswith(".bin"):
                    names.append(f[:-4])
        except Exception:
            pass
    names = sorted(set(names))

    expected = dict(expected_sizes or {})
    if existing_manifest:
        # 已有清单里的尺寸是这台设备备份时的真实尺寸，优先于静态 GPT。
        for e in existing_manifest.get("files", []):
            if isinstance(e, dict) and e.get("partition") and e.get("size"):
                expected[e["partition"]] = int(e["size"])

    missing, bad_size, hash_mismatch, errors, entries = [], [], [], [], []
    total = len(names)
    for i, name in enumerate(names, 1):
        if stop is not None and stop():
            return _result(dir_path, kind, False, True, missing, bad_size,
                           hash_mismatch, errors, entries, False)
        path = os.path.join(dir_path, name + ".bin")
        if not os.path.isfile(path):
            missing.append(name)
            if progress:
                progress(i, total, name)
            continue
        try:
            size = os.path.getsize(path)
            exp = expected.get(name)
            if exp is not None and size != int(exp):
                bad_size.append((name, size, int(exp)))
            last_pct = [-1]

            def chunk_progress(done, total_bytes, _name=name, _i=i,
                               _last=last_pct, _total_files=total):
                pct = int(done * 100 / max(1, total_bytes))
                if pct != _last[0] and progress is not None:
                    _last[0] = pct
                    progress(_i - 1, _total_files, "%s %d%%" % (_name, pct))

            digest = file_digest(path, progress=chunk_progress, stop=stop)
            if digest is None:
                return _result(dir_path, kind, False, True, missing, bad_size,
                               hash_mismatch, errors, entries, False)
            old = old_files.get(name + ".bin")
            if old and old.get("sha256") and old["sha256"] != digest:
                hash_mismatch.append(name)
            entries.append({"partition": name, "file": name + ".bin",
                            "size": size, "sha256": digest})
        except Exception as e:
            errors.append((name, str(e)))
        if progress:
            progress(i, total, name)

    complete = not (missing or bad_size or hash_mismatch or errors)
    wrote = False
    # 首次扫描（没有清单）且完整时生成清单；已有清单但校验失败时不覆盖。
    if write_missing and complete and existing_manifest is None:
        try:
            write_manifest(dir_path, kind, entries)
            wrote = True
        except Exception as e:
            errors.append((MANIFEST_NAME, str(e)))
            complete = False
    return _result(dir_path, kind, complete, False, missing, bad_size,
                   hash_mismatch, errors, entries, wrote)


def _result(dir_path, kind, complete, stopped, missing, bad_size, hash_mismatch,
            errors, entries, wrote):
    return {
        "dir": dir_path,
        "kind": kind,
        "complete": complete,
        "stopped": stopped,
        "missing": missing,
        "bad_size": bad_size,
        "hash_mismatch": hash_mismatch,
        "errors": errors,
        "entries": entries,
        "manifest_written": wrote,
    }


def result_line(result):
    """一行人类可读摘要。"""
    d = os.path.basename(result.get("dir", ""))
    if result.get("stopped"):
        return "%s：已中止" % d
    if result.get("complete"):
        n = len(result.get("entries", []))
        extra = "，已生成哈希清单" if result.get("manifest_written") else ""
        return "%s：%d 个文件，尺寸/哈希全部正确%s" % (d, n, extra)
    bits = []
    if result.get("missing"):
        bits.append("缺失 %d" % len(result["missing"]))
    if result.get("bad_size"):
        bits.append("尺寸不符 %d" % len(result["bad_size"]))
    if result.get("hash_mismatch"):
        bits.append("哈希不符 %d" % len(result["hash_mismatch"]))
    if result.get("errors"):
        bits.append("读取错误 %d" % len(result["errors"]))
    return "%s：%s" % (d, "，".join(bits) or "不完整")


def sidecar_path(bin_path):
    return bin_path + ".sha256"


def write_sidecar(bin_path, size, digest):
    with open(sidecar_path(bin_path), "w", encoding="ascii") as f:
        f.write("%s  %s  %d\n" % (digest, os.path.basename(bin_path), size))
