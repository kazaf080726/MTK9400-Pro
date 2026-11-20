# -*- coding: utf-8 -*-
"""中文/空格路径回归：备份脚本、哈希清单、读取/写入参数。"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import main as g  # noqa: E402
from core import manifest, parts  # noqa: E402
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
    QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp(prefix="MTK 中文 路径 ")
    w = None
    try:
        size = parts.GPT["misc"]
        # 1) 哈希清单
        d = os.path.join(tmp, "备份 目录")
        os.makedirs(d)
        with open(os.path.join(d, "misc.bin"), "wb") as f:
            f.truncate(size)
        r = manifest.scan_dir(d, ["misc"], {"misc": size}, "test")
        check("01 中文目录清单", r["complete"] and r["manifest_written"])
        check("02 中文目录清单可读", os.path.isfile(manifest.manifest_path(d)))

        # 2) 备份脚本
        script = os.path.join(tmp, "脚本 文件.txt")
        parts.write_script(script, ["misc"], "backup_full.new")
        with open(script, encoding="ascii") as f:
            text = f.read()
        check("03 中文目录写脚本", "r misc backup_full.new\\misc.bin" in text, text)

        # 3) 写入：中文镜像名 + 中文路径
        wdir = os.path.join(tmp, "写入 目录")
        rdir = os.path.join(tmp, "备份 目录")
        os.makedirs(wdir, exist_ok=True)
        img_name = "中文 镜像.img"
        img = os.path.join(wdir, img_name)
        with open(img, "wb") as f:
            f.truncate(size)
        bak = os.path.join(rdir, "misc.bin")
        manifest.write_manifest(rdir, "rescue",
                                [{"partition": "misc", "file": "misc.bin",
                                  "size": size, "sha256": manifest.file_digest(bak)}])

        w = g.MainWindow()
        w.connected = True
        w.session = logparse.Session("connect")
        for line in ("GPT Table:\n",
                     "misc: Offset 0x0000000000000800, Length 0x%x\n" % size,
                     "Total disk size:0x%x, sectors:0x%x\n" % (100000 * 512, 100000)):
            for i in range(0, len(line), 80):
                w.session.feed(line[i:i + 80])
        w._gpt_ok = True
        old_dirs = (g.config.DIR_WRITE, g.config.DIR_RESCUE, g.config.DIR_CRIT,
                    g.config.DIR_IMP, g.config.DIR_FULL, g.config.DIR_BACKUP,
                    g.config.DIR_READ)
        g.config.DIR_WRITE, g.config.DIR_RESCUE = wdir, rdir
        g.config.DIR_CRIT = os.path.join(tmp, "空1")
        g.config.DIR_IMP = os.path.join(tmp, "空2")
        g.config.DIR_FULL = os.path.join(tmp, "空3")
        g.config.DIR_BACKUP = os.path.join(tmp, "空4")
        read_dir = os.path.join(tmp, "读取 目录")
        os.makedirs(read_dir, exist_ok=True)
        g.config.DIR_READ = read_dir
        old_exec = g.ConfirmDialog.exec
        g.ConfirmDialog.exec = lambda self: QDialog.Accepted
        calls = []
        try:
            w._pick_file = lambda files: img_name
            w._ask_text = lambda *a, **k: "misc"
            w.run_mtk = lambda *a, **k: calls.append(a)
            w.do_write()
        finally:
            g.ConfirmDialog.exec = old_exec
        check("04 中文镜像可写入", calls and calls[0][0][2] == img and os.path.exists(calls[0][0][2]),
              str(calls[:1]))

        # 4) 读取：中文输出路径
        rcalls = []
        w.run_mtk = lambda *a, **k: rcalls.append(a)
        w._ask_text = lambda *a, **k: "misc"
        w.do_read()
        target = rcalls[0][0][2] if rcalls else ""
        check("05 中文读取路径", target.startswith(read_dir) and target.endswith(".part"),
              target)
        (g.config.DIR_WRITE, g.config.DIR_RESCUE, g.config.DIR_CRIT,
         g.config.DIR_IMP, g.config.DIR_FULL, g.config.DIR_BACKUP,
         g.config.DIR_READ) = old_dirs
    finally:
        if w is not None:
            try:
                w.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    for r in rows:
        print("%-4s %-38s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
