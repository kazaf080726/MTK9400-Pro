import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from core import rescue  # noqa: E402

TOTAL = 0x10000
REQUIRED = [
    "super", "boot_a", "boot_b", "vendor_boot_a", "vendor_boot_b",
    "init_boot_a", "init_boot_b", "vbmeta_a", "vbmeta_b",
    "vbmeta_system_a", "vbmeta_system_b", "vbmeta_vendor_a", "vbmeta_vendor_b",
    "modem_a", "modem_b",
]
EXTRA = ["spmfw_a", "spmfw_b", "logo_a", "logo_b"]
PRIVATE = ["nvdata", "persist", "seccfg", "otp", "flashinfo"]

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("  " + str(detail))


def make_gpt(tmp):
    parts = []
    lba = 100
    for i, name in enumerate(REQUIRED + EXTRA + PRIVATE + ["userdata"]):
        size = 0x2000 if name == "super" else 0x1000
        n = max(1, size // 512)
        parts.append({
            "name": name,
            "type_guid": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
            "unique_guid": "11111111-2222-3333-4444-%012d" % i,
            "first_lba": lba,
            "last_lba": lba + n - 1,
            "flags": 0,
        })
        lba += n + 8
    primary, backup, _ = rescue.build_raw_gpt(
        parts, "12345678-1234-1234-1234-1234567890ab", TOTAL, 512)
    pp = os.path.join(tmp, "primary.raw")
    bp = os.path.join(tmp, "backup.raw")
    with open(pp, "wb") as f:
        f.write(primary)
    with open(bp, "wb") as f:
        f.write(backup)
    return parts, pp, bp


def main():
    tmp = tempfile.mkdtemp(prefix="curated_")
    try:
        parts, pp, bp = make_gpt(tmp)
        bdir = os.path.join(tmp, "backup")
        os.makedirs(bdir)
        for p in parts:
            size = (p["last_lba"] - p["first_lba"] + 1) * 512
            with open(os.path.join(bdir, p["name"] + ".bin"), "wb") as f:
                f.write(b"\0" * size)
        include = REQUIRED + EXTRA
        z = os.path.join(tmp, "定制救砖包.zip")
        r = rescue.create_package(
            z, bdir, pp, bp, package_type="curated", include_names=include)
        check("01 定制包创建", os.path.isfile(z), r)
        check("02 定制包类型", r["manifest"]["package_type"] == "curated")
        check("03 定制包分区数", len(r["manifest"]["partitions"]) == len(include))
        info = rescue.inspect_package(z)
        names = [e["name"] for e in info["entries"]]
        check("04 复查通过", info["manifest"]["package_type"] == "curated")
        check("05 不含私人分区", not (set(names) & set(PRIVATE)), names)
        check("06 不含 userdata", "userdata" not in names)
        cmds = rescue.plan_restore(info, prefix="")
        check("07 只写白名单", all(any(c.startswith("w %s " % n) for c in cmds) for n in include))
        check("08 不写私人分区",
              not any(any(c.startswith("w %s " % n) for c in cmds) for n in PRIVATE))
        check("09 userdata 单独格式化", "e userdata" in cmds and "printgpt" in cmds)

        try:
            rescue.create_package(
                os.path.join(tmp, "bad_private.zip"), bdir, pp, bp,
                package_type="curated", include_names=include + ["nvdata"])
            ok = False
        except Exception:
            ok = True
        check("10 拒绝私人分区入包", ok)

        try:
            rescue.create_package(
                os.path.join(tmp, "bad_missing.zip"), bdir, pp, bp,
                package_type="curated", include_names=[n for n in include if n != "modem_b"])
            ok = False
        except Exception:
            ok = True
        check("11 拒绝缺少必需分区", ok)

        try:
            rescue.create_package(
                os.path.join(tmp, "bad_super.zip"), bdir, pp, bp,
                package_type="curated",
                include_names=[n for n in include if n != "super"])
            ok = False
        except Exception:
            ok = True
        check("12 拒绝缺少 super", ok)

        check("13 清单可读", rescue.load_manifest_from_zip(
            __import__("zipfile").ZipFile(z))["package_type"] == "curated")

        pre = os.path.join(tmp, "preloader_raw.bin")
        with open(pre, "wb") as f:
            f.write(b"P" * 0x1000)
        zp = os.path.join(tmp, "定制救砖包_带preloader.zip")
        rp = rescue.create_package(
            zp, bdir, pp, bp, package_type="curated", include_names=include,
            preloader_raw={"path": pre, "parttype": "lu0", "offset": 0})
        check("14 preloader_raw 入包",
              rp["manifest"].get("preloader_raw", {}).get("size") == 0x1000)
        ip = rescue.inspect_package(zp)
        check("15 preloader_raw 校验通过", ip.get("preloader") is not None)
        check("16 preloader_raw 可选写入",
              any("--parttype lu0" in c for c in rescue.plan_restore(
                  ip, prefix="", flash_preloader=True)))
        check("17 preloader_raw 默认不写",
              not any("preloader_raw" in c for c in rescue.plan_restore(
                  ip, prefix="", flash_preloader=False)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nTOTAL 17  PASS=%d  FAIL=%d" % (17 - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
