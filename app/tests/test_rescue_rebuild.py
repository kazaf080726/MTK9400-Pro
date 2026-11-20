# -*- coding: utf-8 -*-
"""GPT 损坏 → 确认重建 → 回读校验 → 全局刷写。"""
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
    tmp = tempfile.mkdtemp(prefix="rescue_rebuild_")
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
        bdir = os.path.join(tmp, "b")
        os.makedirs(bdir)
        with open(os.path.join(bdir, "boot.bin"), "wb") as f:
            f.write(b"B" * (2048 * 512))
        pp = os.path.join(tmp, "p.bin")
        bp = os.path.join(tmp, "b.bin")
        with open(pp, "wb") as f:
            f.write(primary)
        with open(bp, "wb") as f:
            f.write(backup)
        zp = os.path.join(tmp, "r.zip")
        rescue.create_package(zp, bdir, pp, bp, package_type="full")

        bad = bytearray(primary)
        bad[512 + 16] ^= 0xFF
        old.update({"exec": g.ConfirmDialog.exec, "info": QMessageBox.information,
                    "crit": QMessageBox.critical, "warn": QMessageBox.warning,
                    "question": QMessageBox.question,
                    "fd": g.QFileDialog.getOpenFileName})
        info = []
        crit = []
        g.ConfirmDialog.exec = lambda self: QDialog.Accepted
        QMessageBox.information = staticmethod(lambda *a, **k: info.append(a[1]))
        QMessageBox.critical = staticmethod(lambda *a, **k: crit.append(a[1] + "|" + a[2]))
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
                open(os.path.join(pre, "primary.raw"), "wb").write(bytes(bad))
                open(os.path.join(pre, "backup.raw"), "wb").write(backup)
            elif path.endswith("rescue_rebuild.txt"):
                post = os.path.join(g.config.DIR_RESCUE_RUN, "post")
                os.makedirs(post, exist_ok=True)
                open(os.path.join(post, "primary.raw"), "wb").write(primary)
                open(os.path.join(post, "backup.raw"), "wb").write(backup)
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
        check("01 GPT 损坏触发重建分支", getattr(w, "_rescue_rebuild", False) is True)
        check("02 执行 GPT 重建脚本", any(p.endswith("rescue_rebuild.txt") for _l, p in scripts))
        check("03 重建后回读校验并继续刷写",
              any(p.endswith("flash.txt") for _l, p in scripts), str(scripts))
        check("04 流程完成", ok)
        check("05 无失败提示", not crit, str(crit))
        check("06 完成提示", "全局恢复完成" in info, str(info))
        rebuild = next((p for _l, p in scripts if p.endswith("rescue_rebuild.txt")), "")
        if rebuild:
            body = open(rebuild, encoding="ascii").read()
        else:
            body = ""
        check("07 重建脚本写主/备 GPT", body.count("wo ") >= 2, body)
        check("08 重建脚本回读主 GPT", "ro 0x0 0x4000" in body and
              "backup.raw.part" not in body, body)
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
        g.QFileDialog.getOpenFileName = old.get("fd", g.QFileDialog.getOpenFileName)
        shutil.rmtree(tmp, ignore_errors=True)

    for r in rows:
        print("%-4s %-36s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
