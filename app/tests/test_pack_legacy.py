# -*- coding: utf-8 -*-
"""旧全量备份补抓 GPT 原始扇区并打包。"""
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import main as g  # noqa: E402
from core import manifest, rescue  # noqa: E402
from core import session as logparse  # noqa: E402

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


def spin(app, cond, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def main():
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp(prefix="pack_legacy_")
    w = None
    old = {}
    try:
        ps = [
            {"name": "boot", "type_guid": TYPE,
             "unique_guid": "11111111-2222-3333-4444-555555555555",
             "first_lba": 2048, "last_lba": 4095},
            {"name": "userdata", "type_guid": TYPE,
             "unique_guid": "11111111-2222-3333-4444-666666666666",
             "first_lba": 4096, "last_lba": 8191},
        ]
        primary, backup, _ = rescue.build_raw_gpt(
            ps, "12345678-1234-1234-1234-1234567890ab", 100000)
        full = os.path.join(g.config.WORK, "backup_full_legacy")
        shutil.rmtree(full, ignore_errors=True)
        os.makedirs(full)
        size = 2048 * 512
        with open(os.path.join(full, "boot.bin"), "wb") as f:
            f.write(b"L" * size)
        manifest.write_manifest(full, "backup_full",
                                [{"partition": "boot", "file": "boot.bin",
                                  "size": size, "sha256": manifest.file_digest(os.path.join(full, "boot.bin"))}])

        old["full"] = g.config.DIR_FULL
        old["pkg"] = g.config.DIR_PACKAGES
        old["info"] = QMessageBox.information
        old["crit"] = QMessageBox.critical
        g.config.DIR_FULL = full
        g.config.DIR_PACKAGES = os.path.join(tmp, "packages")
        os.makedirs(g.config.DIR_PACKAGES)
        info = []
        crit = []
        QMessageBox.information = staticmethod(lambda *a, **k: info.append(a[1]))
        QMessageBox.critical = staticmethod(lambda *a, **k: crit.append(a[1] + "|" + a[2]))

        w = g.MainWindow()
        w.connected = True
        w.session = logparse.Session("connect")
        w.session.feed("GPT Table:\n")
        w.session.feed("boot: Offset 0x%016x, Length 0x%016x\n" % (2048 * 512, size))
        w.session.feed("userdata: Offset 0x%016x, Length 0x%016x\n" % (4096 * 512, size))
        w.session.feed("Total disk size:0x%x, sectors:0x%x\n" % (100000 * 512, 100000))
        w._gpt_ok = True
        w.show()
        app.processEvents()

        def fake_run(args, kind, label, timeout, on_done):
            path = next((a for a in args if str(a).endswith(".txt")), "")
            if path.endswith("capture_gpt.txt"):
                open(os.path.join(full, "gpt_primary.raw"), "wb").write(primary)
                open(os.path.join(full, "gpt_backup.raw"), "wb").write(backup)
            w._done(0, "", False, on_done)

        w.run_mtk = fake_run
        w.btns["pack"].click()
        ok = spin(app, lambda: (not w._hashing) and any(
            f.endswith(".zip") for f in os.listdir(g.config.DIR_PACKAGES)))
        zips = [f for f in os.listdir(g.config.DIR_PACKAGES) if f.endswith(".zip")]
        check("01 旧备份自动补 GPT raw", ok and os.path.isfile(
            os.path.join(full, "gpt_primary.raw")))
        check("02 生成救砖包", bool(zips), str(zips))
        check("03 包校验通过", bool(zips) and rescue.inspect_package(
            os.path.join(g.config.DIR_PACKAGES, zips[0]))["manifest"]["package_type"] == "full")
        check("04 完成提示", "救砖包已生成" in info, str(info))
        check("05 无失败提示", not crit, str(crit))
    finally:
        try:
            if w is not None:
                w.close()
        except Exception:
            pass
        if "full" in old:
            g.config.DIR_FULL = old["full"]
            g.config.DIR_PACKAGES = old["pkg"]
            QMessageBox.information = old["info"]
            QMessageBox.critical = old["crit"]
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(full, ignore_errors=True)

    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
