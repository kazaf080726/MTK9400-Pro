# -*- coding: utf-8 -*-
"""全量/自定义备份的动态 GPT 回归。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core import parts  # noqa: E402
from core import session as logparse  # noqa: E402

passed = failed = 0
rows = []


def check(name, cond, note=""):
    global passed, failed
    if cond:
        passed += 1
        rows.append(("PASS", name, ""))
    else:
        failed += 1
        rows.append(("FAIL", name, note))


def main():
    samples = ["misc", "boot_a", "boot_b", "super", "userdata"]
    s = logparse.Session("connect")
    text = "GPT Table:\n"
    for i, n in enumerate(samples):
        text += "%s: Offset 0x%016x, Length 0x%016x\n" % (n, (2048 + i * 4096) * 512, 2048 * 512)
    text += "Total disk size:0x%x, sectors:0x%x\n" % (100000 * 512, 100000)
    for ch in [text[i:i + 100] for i in range(0, len(text), 100)]:
        s.feed(ch)
    live = dict(s.partition_sizes)
    names = parts.full_names(live)
    check("01 全量等于现场 GPT 减 userdata", set(names) == set(live) - {"userdata"}, str(names))
    check("02 全量不含 userdata", "userdata" not in names)
    check("03 全量包含 super", "super" in names)
    check("04 分区数动态", len(names) == 4, str(len(names)))
    check("05 现场总扇区", s.total_sectors == 100000, str(s.total_sectors))
    check("06 现场尺寸", live.get("misc") == 2048 * 512, str(live.get("misc")))

    tmp = tempfile.mkdtemp(prefix="mtk_dyn_")
    try:
        script = os.path.join(tmp, "full.txt")
        parts.write_script(script, names, "backup_full.new", s.total_sectors)
        with open(script, encoding="ascii") as f:
            lines = f.read().splitlines()
        check("07 脚本先 printgpt", lines and lines[0] == "printgpt")
        check("08 脚本抓取 GPT 主扇区", "ro 0x0 0x4000 backup_full.new\\gpt_primary.raw.part0" in lines)
        check("09 备份 GPT 由主 GPT 重建",
              not any("gpt_backup.raw.part" in x for x in lines))
        check("10 脚本不读 userdata", not any(" userdata " in x for x in lines))
        check("11 脚本读取 super", any(x.startswith("r super ") for x in lines))
        check("12 脚本路径相对 staging", all("backup_full.new\\" in x for x in lines[3:]))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    for r in rows:
        print("%-4s %-36s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
