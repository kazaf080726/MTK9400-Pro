# -*- coding: utf-8 -*-
"""DA / Preloader 工具文件参数测试。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from core import toolfiles  # noqa: E402

passed = failed = 0


def check(name, ok, note=""):
    global passed, failed
    if ok:
        passed += 1
        print("PASS " + name)
    else:
        failed += 1
        print("FAIL " + name + ("  " + str(note) if note else ""))


def touch(path, size=8192):
    with open(path, "wb") as f:
        f.write(b"D" * size)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="toolfiles_")
    try:
        da = touch(os.path.join(tmp, "da.bin"))
        pre = touch(os.path.join(tmp, "preloader.bin"), 4096)
        auth = touch(os.path.join(tmp, "auth.bin"), 2048)
        data = {"da": da, "preloader": pre, "auth": auth, "use_auth": False,
                "serialport": "COM13"}
        args = toolfiles.command_args(data)
        check("01 DA 参数存在", "--loader" in args and da in args)
        check("02 Preloader 参数存在", "--preloader" in args and pre in args)
        check("03 关闭 auth 不传 --auth", "--auth" not in args)
        check("04 串口参数存在", "--serialport" in args and "COM13" in args)

        toolfiles.save(tmp, data)
        loaded = toolfiles.load(tmp)
        check("05 保存读取", loaded["da"] == da and loaded["preloader"] == pre)
        check("06 auth 开关保存", loaded["use_auth"] is False)
        check("07 串口保存", loaded["serialport"] == "COM13")

        data2 = dict(data)
        data2["use_auth"] = True
        args2 = toolfiles.command_args(data2)
        check("08 开启 auth 传 --auth", "--auth" in args2 and auth in args2)

        bad = dict(data)
        bad["da"] = os.path.join(tmp, "missing.bin")
        try:
            toolfiles.validate(bad)
            ok = False
        except Exception:
            ok = True
        check("09 拒绝不存在的 DA", ok)

        bad2 = dict(data)
        bad2["preloader"] = os.path.join(tmp, "missing_pre.bin")
        try:
            toolfiles.validate(bad2)
            ok = False
        except Exception:
            ok = True
        check("10 拒绝不存在的 Preloader", ok)

        small = touch(os.path.join(tmp, "small_da.bin"), 10)
        bad3 = dict(data)
        bad3["da"] = small
        try:
            toolfiles.validate(bad3)
            ok = False
        except Exception:
            ok = True
        check("11 拒绝过小 DA", ok)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nTOTAL 11  PASS=%d  FAIL=%d" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
