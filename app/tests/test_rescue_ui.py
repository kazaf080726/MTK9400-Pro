# -*- coding: utf-8 -*-
"""救砖 UI 流程回归：选包 → 校验 → 预检 GPT → 解压 → 全局刷写。"""
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

import main as g  # noqa: E402
from core import rescue  # noqa: E402
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


def spin(app, cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def main():
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp(prefix="rescue_ui_")
    w = None
    old = {}
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
        primary, backup, _ = rescue.build_raw_gpt(
            parts, "12345678-1234-1234-1234-1234567890ab", 100000)
        bdir = os.path.join(tmp, "backup")
        os.makedirs(bdir)
        for p in parts:
            if p["name"] == "userdata":
                continue
            with open(os.path.join(bdir, p["name"] + ".bin"), "wb") as f:
                f.write(b"X" * ((p["last_lba"] - p["first_lba"] + 1) * 512))
        pp = os.path.join(tmp, "p.bin")
        bp = os.path.join(tmp, "b.bin")
        with open(pp, "wb") as f:
            f.write(primary)
        with open(bp, "wb") as f:
            f.write(backup)
        zp = os.path.join(tmp, "rescue.zip")
        rescue.create_package(zp, bdir, pp, bp, package_type="full")

        old.update({
            "exec": g.ConfirmDialog.exec,
            "info": QMessageBox.information,
            "crit": QMessageBox.critical,
            "warn": QMessageBox.warning,
            "question": QMessageBox.question,
            "filedialog": g.QFileDialog.getOpenFileName,
            "run": g.MainWindow.run_mtk,
        })
        rec = {"info": [], "crit": []}
        g.ConfirmDialog.exec = lambda self: QDialog.Accepted
        QMessageBox.information = staticmethod(lambda *a, **k: rec["info"].append(a[1]))
        QMessageBox.critical = staticmethod(lambda *a, **k: rec["crit"].append(a[1] + "|" + a[2]))
        QMessageBox.warning = staticmethod(lambda *a, **k: None)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
        g.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (zp, ""))

        w = g.MainWindow()
        w.connected = True
        w._set_enabled(True)
        w.resize(1180, 780)
        w.show()
        app.processEvents()
        scripts = []

        def gpt_text(pkg):
            g = pkg["gpt"]
            lines = ["GPT Table:"]
            for p in g["partitions"]:
                lines.append("%s: Offset 0x%016x, Length 0x%016x"
                             % (p["name"], p["first_lba"] * g["sector_size"], p["size"]))
            lines.append("Total disk size:0x%x, sectors:0x%x"
                         % (g["total_size"], g["total_sectors"]))
            return "\n".join(lines) + "\n"

        def fake_run(args, kind, label, timeout, on_done):
            path = next((a for a in args if str(a).endswith(".txt")), "")
            scripts.append((label, path))
            w.session = logparse.Session(kind)
            text = ""
            if path.endswith("rescue_preflight.txt"):
                pre = os.path.join(g.config.DIR_RESCUE_RUN, "preflight")
                os.makedirs(pre, exist_ok=True)
                with open(os.path.join(pre, "primary.raw"), "wb") as f:
                    f.write(primary)
                with open(os.path.join(pre, "backup.raw"), "wb") as f:
                    f.write(backup)
            elif path.endswith("flash.txt"):
                pkg = w._package_info
                for e in pkg["entries"]:
                    if e["name"] not in {"seccfg", "otp", "flashinfo", "pgpt", "sgpt", "userdata"}:
                        text += "Wrote %s to sector 0.\n" % e["name"]
                text += gpt_text(pkg)
                for line in text.splitlines(True):
                    w.session.feed(line)
            w._done(0, text, False, on_done)

        w.run_mtk = fake_run
        w.btns["rescue"].click()
        ok = spin(app, lambda: (not w._hashing) and (not w.busy) and
                  any(x[0] == "全局恢复" for x in scripts), 30)
        check("01 救砖流程跑到全局恢复", ok, str(scripts))
        check("02 包校验通过", w._package_info is not None)
        check("03 GPT 匹配后未重建", getattr(w, "_rescue_rebuild", False) is False)
        check("04 预检脚本执行", any(p.endswith("rescue_preflight.txt") for _l, p in scripts))
        check("05 全局脚本执行", any(p.endswith("flash.txt") for _l, p in scripts))
        flash = next((p for _l, p in scripts if p.endswith("flash.txt")), "")
        if flash:
            with open(flash, encoding="ascii") as f:
                cmds = f.read()
        else:
            cmds = ""
        check("06 全局脚本含分区写入", "w boot rescue_run\\partitions/boot.bin" in cmds, cmds)
        check("07 全局脚本格式化 userdata", "e userdata" in cmds)
        check("08 完成后有提示", "全局恢复完成" in rec["info"], str(rec))
        check("09 全局恢复无错误", not rec["crit"], str(rec["crit"]))
    finally:
        try:
            if w is not None:
                w.close()
        except Exception:
            pass
        g.ConfirmDialog.exec = old.get("exec", g.ConfirmDialog.exec)
        QMessageBox.information = old.get("info", QMessageBox.information)
        QMessageBox.critical = old.get("crit", QMessageBox.critical)
        QMessageBox.warning = old.get("warn", QMessageBox.warning)
        QMessageBox.question = old.get("question", QMessageBox.question)
        g.QFileDialog.getOpenFileName = old.get("filedialog", g.QFileDialog.getOpenFileName)
        if old.get("run"):
            g.MainWindow.run_mtk = old["run"]
        shutil.rmtree(tmp, ignore_errors=True)

    for r in rows:
        print("%-4s %-36s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
