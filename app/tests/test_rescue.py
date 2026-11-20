# -*- coding: utf-8 -*-
"""救砖包 / GPT 原始数据 / 全局恢复计划 回归。"""
import os
import shutil
import sys
import tempfile
import zipfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core import rescue  # noqa: E402

passed = failed = 0
rows = []
TYPE = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"


def check(name, cond, note=""):
    global passed, failed
    if cond:
        passed += 1
        rows.append(("PASS", name, ""))
    else:
        failed += 1
        rows.append(("FAIL", name, note))


def main():
    tmp = tempfile.mkdtemp(prefix="rescue_")
    try:
        parts = [
            {"name": "boot", "type_guid": TYPE,
             "unique_guid": "11111111-2222-3333-4444-555555555555",
             "first_lba": 2048, "last_lba": 4095},
            {"name": "super", "type_guid": TYPE,
             "unique_guid": "11111111-2222-3333-4444-777777777777",
             "first_lba": 4096, "last_lba": 8191},
            {"name": "userdata", "type_guid": TYPE,
             "unique_guid": "11111111-2222-3333-4444-666666666666",
             "first_lba": 8192, "last_lba": 16383},
        ]
        primary, backup, info = rescue.build_raw_gpt(parts, "12345678-1234-1234-1234-1234567890ab", 100000)
        pp = os.path.join(tmp, "primary.bin")
        bp = os.path.join(tmp, "backup.bin")
        with open(pp, "wb") as f:
            f.write(primary)
        with open(bp, "wb") as f:
            f.write(backup)
        g = rescue.parse_gpt_raw(primary, backup)
        check("01 GPT 原始解析", len(g["partitions"]) == 3 and g["total_sectors"] == 100000,
              str(g["partitions"]))
        check("02 GPT 主备一致", rescue.compare_gpt(g, g) == [])

        d = os.path.join(tmp, "backup_full")
        os.makedirs(d)
        for p in parts:
            if p["name"] == "userdata":
                continue
            size = (p["last_lba"] - p["first_lba"] + 1) * 512
            with open(os.path.join(d, p["name"] + ".bin"), "wb") as f:
                f.write(b"X" * size)
        zp = os.path.join(tmp, "rescue.zip")
        created = rescue.create_package(zp, d, pp, bp, package_type="full")
        check("03 生成全量救砖包", os.path.isfile(zp) and created["sha256"],
              str(os.path.getsize(zp)))
        with zipfile.ZipFile(zp) as zf:
            check("04 ZIP 仅存储", all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist()))
        pkg = rescue.inspect_package(zp)
        check("05 包校验通过", pkg["manifest"]["package_type"] == "full" and
              len(pkg["entries"]) == 2, str(len(pkg["entries"])))
        check("06 包内无 userdata", all(e["name"] != "userdata" for e in pkg["entries"]))
        cmds = rescue.plan_restore(pkg, prefix="rescue_run", rebuild=True, wipe_userdata=True)
        check("07 恢复计划含 GPT 重建", any(c.startswith("wo 0 ") for c in cmds), str(cmds[:3]))
        check("08 恢复计划含分区写入", any(c.startswith("w boot ") for c in cmds))
        check("09 恢复计划含 userdata 格式化", "e userdata" in cmds)
        check("10 恢复计划不写 userdata 镜像", all("partitions/userdata" not in c for c in cmds))

        ex = os.path.join(tmp, "extract")
        rescue.extract_package(zp, ex)
        check("11 解压并复核", os.path.isfile(os.path.join(ex, "partitions", "boot.bin")) and
              os.path.isfile(os.path.join(ex, "gpt", "primary.bin")))

        # GPT 损坏 / 不匹配
        badp = bytearray(primary)
        badp[512 + 16] ^= 0xFF
        st, _g, _err = rescue.current_gpt_status(bytes(badp), backup)
        check("12 GPT CRC 损坏可识别", st == "damaged")

        other = [dict(p) for p in parts]
        other[0]["unique_guid"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        p2, b2, _ = rescue.build_raw_gpt(other, "12345678-1234-1234-1234-1234567890ab", 100000)
        g2 = rescue.parse_gpt_raw(p2, b2)
        check("13 GPT 不匹配可识别", rescue.compare_gpt(g, g2) != [])

        # 部分包：只含 boot，不能当全量包
        d2 = os.path.join(tmp, "part")
        os.makedirs(d2)
        shutil.copyfile(os.path.join(d, "boot.bin"), os.path.join(d2, "boot.bin"))
        zp2 = os.path.join(tmp, "part.zip")
        rescue.create_package(zp2, d2, pp, bp, package_type="partial")
        pkg2 = rescue.inspect_package(zp2)
        check("14 部分包类型", pkg2["manifest"]["package_type"] == "partial")

        # 篡改 zip 中一个分区文件
        bad_zip = os.path.join(tmp, "bad.zip")
        with zipfile.ZipFile(zp) as src, zipfile.ZipFile(bad_zip, "w",
                                                         compression=zipfile.ZIP_STORED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith("boot.bin"):
                    data = bytearray(data)
                    data[0] ^= 0xFF
                    data = bytes(data)
                dst.writestr(info, data)
        try:
            rescue.inspect_package(bad_zip)
            ok = False
        except Exception:
            ok = True
        check("15 篡改包被拒绝", ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for r in rows:
        print("%-4s %-36s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
