# -*- coding: utf-8 -*-
"""安全路径回归：哈希清单、备份原子替换、读取临时文件、写入校验。

只使用临时目录和小文件，不接触真实手机。
"""
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog  # noqa: E402

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


def spin(app, cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def raw_gpt(names, total=100000, sector=512):
    ps = []
    for i, n in enumerate(names):
        first = 2048 + i * 4096
        last = first + 2047
        ps.append({"name": n, "type_guid": TYPE,
                   "unique_guid": "11111111-2222-3333-4444-%012d" % (i + 1),
                   "first_lba": first, "last_lba": last})
    return rescue.build_raw_gpt(ps, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", total, sector)[:2]


def sample_session(names, total=100000):
    s = logparse.Session("connect")
    lines = ["GPT Table:"]
    for i, n in enumerate(names):
        first = 2048 + i * 4096
        lines.append("%s: Offset 0x%016x, Length 0x%016x" % (n, first * 512, 2048 * 512))
    lines.append("Total disk size:0x%x, sectors:0x%x" % (total * 512, total))
    for line in lines:
        for ch in [line[i:i + 80] for i in range(0, len(line), 80)]:
            s.feed(ch + "\n")
    return s


def main():
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp(prefix="mtk_safety_")
    w = None
    old_dirs = {}
    try:
        size = 512 * 2048
        # 1) 哈希清单
        d1 = os.path.join(tmp, "m1")
        os.makedirs(d1)
        with open(os.path.join(d1, "misc.bin"), "wb") as f:
            f.truncate(size)
        r1 = manifest.scan_dir(d1, ["misc"], {"misc": size}, "test")
        check("01 清单生成", r1["complete"] and r1["manifest_written"])
        check("02 清单文件存在", os.path.isfile(manifest.manifest_path(d1)))
        r2 = manifest.scan_dir(d1, ["misc"], {"misc": size}, "test")
        check("03 二次校验通过", r2["complete"] and not r2["hash_mismatch"])
        with open(os.path.join(d1, "misc.bin"), "r+b") as f:
            f.write(b"X")
        r3 = manifest.scan_dir(d1, ["misc"], {"misc": size}, "test")
        check("04 篡改能被发现", not r3["complete"] and r3["hash_mismatch"])

        # 2) 备份原子替换（含 GPT 原始数据）
        old = os.path.join(tmp, "backup_full")
        stage = old + ".new"
        os.makedirs(old)
        with open(os.path.join(old, "old.txt"), "w") as f:
            f.write("old")
        os.makedirs(stage)
        with open(os.path.join(stage, "misc.bin"), "wb") as f:
            f.truncate(size)
        primary, backup = raw_gpt(["misc", "userdata"])
        with open(os.path.join(stage, "gpt_primary.raw"), "wb") as f:
            f.write(primary)
        with open(os.path.join(stage, "gpt_backup.raw"), "wb") as f:
            f.write(backup)
        w = g.MainWindow()
        w._backup_ctx = {"final": old, "stage": stage, "names": ["misc"],
                         "expected": {"misc": size}, "kind": "backup_full",
                         "total_sectors": 100000, "live_names": ["misc", "userdata"],
                         "package_type": "partial"}
        w._start_backup_verify(0, False)
        ok = spin(app, lambda: (not w._hashing) and
                  os.path.isfile(os.path.join(old, "misc.bin")))
        check("05 备份替换完成", ok)
        check("06 旧备份保留为 .old", os.path.isfile(os.path.join(old + ".old", "old.txt")))
        check("07 新备份有清单", os.path.isfile(manifest.manifest_path(old)))

        # 3) 读取临时文件 → 正式文件 + sidecar
        read_dir = os.path.join(tmp, "read")
        os.makedirs(read_dir)
        final = os.path.join(read_dir, "misc.bin")
        temp = final + ".part"
        with open(temp, "wb") as f:
            f.truncate(size)
        w._read_ctx = {"name": "misc", "final": final, "temp": temp, "expected": size}
        w._start_read_verify(0, False, "read")
        ok = spin(app, lambda: (not w._hashing) and os.path.isfile(final))
        check("08 读取文件转正", ok)
        check("09 读取 sidecar 存在", os.path.isfile(final + ".sha256"))

        # 4) 写入：截断备份必须被拒绝
        w.connected = True
        w.session = sample_session(["misc", "userdata"])
        wdir = os.path.join(tmp, "write")
        rdir = os.path.join(tmp, "rescue")
        os.makedirs(wdir)
        os.makedirs(rdir)
        with open(os.path.join(wdir, "img.bin"), "wb") as f:
            f.truncate(size)
        with open(os.path.join(rdir, "misc.bin"), "wb") as f:
            f.truncate(1024)
        old_write, old_rescue = g.config.DIR_WRITE, g.config.DIR_RESCUE
        g.config.DIR_WRITE, g.config.DIR_RESCUE = wdir, rdir
        rec = []
        old_crit = QMessageBox.critical
        QMessageBox.critical = staticmethod(lambda *a, **k: rec.append(a[2]))
        calls = []
        try:
            w._pick_file = lambda files: "img.bin"
            w._ask_text = lambda *a, **k: "misc"
            w.run_mtk = lambda *a, **k: calls.append(a)
            w.do_write()
        finally:
            QMessageBox.critical = old_crit
            g.config.DIR_WRITE, g.config.DIR_RESCUE = old_write, old_rescue
        check("10 截断备份拒绝写入", any("备份尺寸不对" in x for x in rec), str(rec))
        check("11 拒绝后不调用 mtk", len(calls) == 0)

        # 5) 动态自定义备份：临时目录 → 哈希 → 替换正式目录
        final_dir = os.path.join(g.config.WORK, "backup_custom_safety")
        stage_dir = final_dir + ".new"
        old_custom = g.config.DIR_CUSTOM
        old_exec = g.ConfirmDialog.exec
        old_q = QMessageBox.question
        try:
            g.config.DIR_CUSTOM = final_dir
            g.ConfirmDialog.exec = lambda self: QDialog.Accepted
            QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
            w.session = sample_session(["misc", "userdata"])

            def fake_backup(args, kind, label, timeout, on_done):
                ctx = w._backup_ctx
                if ctx:
                    with open(os.path.join(ctx["stage"], "misc.bin"), "wb") as f:
                        f.truncate(size)
                    primary, backup = raw_gpt(["misc", "userdata"])
                    with open(os.path.join(ctx["stage"], "gpt_primary.raw"), "wb") as f:
                        f.write(primary)
                    with open(os.path.join(ctx["stage"], "gpt_backup.raw"), "wb") as f:
                        f.write(backup)
                w._done(0, "", False, on_done)

            w.run_mtk = fake_backup
            w.connected = True
            w.do_backup("custom", ["misc"])
            ok = spin(app, lambda: (not w._hashing) and
                      os.path.isfile(os.path.join(final_dir, "misc.bin")))
            check("12 自定义备份流程", ok)
            check("13 自定义备份含清单",
                  os.path.isfile(manifest.manifest_path(final_dir)))
            script = os.path.join(g.config.WORK, "backup_custom.txt")
            with open(script, encoding="ascii") as f:
                content = f.read()
            check("14 自定义脚本写入 staging", "backup_custom_safety.new\\misc.bin" in content,
                  content)
        finally:
            g.config.DIR_CUSTOM = old_custom
            g.ConfirmDialog.exec = old_exec
            QMessageBox.question = old_q
            shutil.rmtree(final_dir, ignore_errors=True)
            shutil.rmtree(stage_dir, ignore_errors=True)
            shutil.rmtree(final_dir + ".old", ignore_errors=True)

        # 6) 正常写入：备份尺寸/哈希都对，才允许发出 w 命令
        good_write = os.path.join(tmp, "good_write")
        good_rescue = os.path.join(tmp, "good_rescue")
        os.makedirs(good_write)
        os.makedirs(good_rescue)
        with open(os.path.join(good_write, "misc.img"), "wb") as f:
            f.truncate(size)
        bpath = os.path.join(good_rescue, "misc.bin")
        with open(bpath, "wb") as f:
            f.truncate(size)
        manifest.write_manifest(good_rescue, "rescue",
                                [{"partition": "misc", "file": "misc.bin",
                                  "size": size, "sha256": manifest.file_digest(bpath)}])
        old_dirs = (g.config.DIR_WRITE, g.config.DIR_RESCUE, g.config.DIR_BACKUP,
                    g.config.DIR_READ)
        g.config.DIR_WRITE, g.config.DIR_RESCUE = good_write, good_rescue
        g.config.DIR_BACKUP = os.path.join(tmp, "none3")
        g.config.DIR_READ = os.path.join(tmp, "none4")
        old_exec2 = g.ConfirmDialog.exec
        g.ConfirmDialog.exec = lambda self: QDialog.Accepted
        calls2 = []
        try:
            w._pick_file = lambda files: "misc.img"
            w._ask_text = lambda *a, **k: "misc"
            w.run_mtk = lambda *a, **k: calls2.append(a)
            w.do_write()
        finally:
            g.ConfirmDialog.exec = old_exec2
            (g.config.DIR_WRITE, g.config.DIR_RESCUE, g.config.DIR_BACKUP,
             g.config.DIR_READ) = old_dirs
        check("15 正确备份允许写入", calls2 and calls2[0][0][0] == "w", str(calls2[:1]))
        check("16 写入前核对备份哈希",
              "[写入] 备份" in w.raw.toPlainText() and "哈希已核对" in w.raw.toPlainText())
    finally:
        if w is not None:
            try:
                w.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
