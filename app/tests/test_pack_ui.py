# -*- coding: utf-8 -*-
"""生成救砖包 UI 流程：全量备份目录 + GPT raw → ZIP + sidecar。"""
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
    tmp = tempfile.mkdtemp(prefix="pack_ui_")
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
        src = os.path.join(tmp, "backup_full")
        os.makedirs(src)
        with open(os.path.join(src, "boot.bin"), "wb") as f:
            f.write(b"Z" * (2048 * 512))
        with open(os.path.join(src, "gpt_primary.raw"), "wb") as f:
            f.write(primary)
        with open(os.path.join(src, "gpt_backup.raw"), "wb") as f:
            f.write(backup)

        old["dir"] = g.config.DIR_FULL
        old["pkg"] = g.config.DIR_PACKAGES
        old["info"] = QMessageBox.information
        old["crit"] = QMessageBox.critical
        g.config.DIR_FULL = src
        g.config.DIR_PACKAGES = os.path.join(tmp, "packages")
        os.makedirs(g.config.DIR_PACKAGES)
        info = []
        crit = []
        QMessageBox.information = staticmethod(lambda *a, **k: info.append(a[1]))
        QMessageBox.critical = staticmethod(lambda *a, **k: crit.append(a[1] + "|" + a[2]))
        w = g.MainWindow()
        w.show()
        app.processEvents()
        w.btns["pack"].click()
        ok = spin(app, lambda: (not w._hashing) and any(
            f.endswith(".zip") for f in os.listdir(g.config.DIR_PACKAGES)))
        zips = [f for f in os.listdir(g.config.DIR_PACKAGES) if f.endswith(".zip")]
        check("01 生成 zip", ok and len(zips) == 1, str(zips))
        check("02 生成 sidecar", bool(zips) and os.path.isfile(
            os.path.join(g.config.DIR_PACKAGES, zips[0] + ".sha256")))
        pk = rescue.inspect_package(os.path.join(g.config.DIR_PACKAGES, zips[0]))
        check("03 包可校验", pk["manifest"]["package_type"] == "full" and
              pk["sidecar_ok"], str(pk.get("sidecar_ok")))
        check("04 包内 GPT 完整", len(pk["gpt"]["partitions"]) == 2)
        check("05 完成提示", "救砖包已生成" in info, str(info))
        check("06 无失败提示", not crit, str(crit))
    finally:
        try:
            if w is not None:
                w.close()
        except Exception:
            pass
        if "dir" in old:
            g.config.DIR_FULL = old["dir"]
            g.config.DIR_PACKAGES = old["pkg"]
            QMessageBox.information = old["info"]
            QMessageBox.critical = old["crit"]
        shutil.rmtree(tmp, ignore_errors=True)

    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
