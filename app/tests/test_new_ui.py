# -*- coding: utf-8 -*-
"""新增工具入口的电脑端回归（不接触真机）。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
import main as g  # noqa: E402
from core import scatter  # noqa: E402
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


class FakeSession:
    partitions = ["boot_a", "boot_b", "preloader", "userdata", "metadata", "misc"]
    partition_sizes = {"boot_a": 0x4000000, "boot_b": 0x4000000,
                       "preloader": 0x200000, "userdata": 0x100000,
                       "metadata": 0x100000, "misc": 0x80000}
    partition_meta = {
        "boot_a": {"offset": 0x100000, "size": 0x4000000, "type": "EXT4"},
        "boot_b": {"offset": 0x4100000, "size": 0x4000000, "type": "EXT4"},
        "preloader": {"offset": 0x0, "size": 0x200000, "type": "SV5_BL_BIN"},
        "userdata": {"offset": 0x8200000, "size": 0x100000, "type": "EXT4"},
        "metadata": {"offset": 0x8300000, "size": 0x100000, "type": "EXT4"},
        "misc": {"offset": 0x8400000, "size": 0x80000, "type": "EXT4"},
    }


class FakeConfirm:
    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.Accepted


class FakeRaw:
    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.Accepted

    def value(self):
        return {"unit": "USER", "start": "0x0", "size": "0x1000",
                "mode": "read", "file": os.path.join(tempfile.gettempdir(), "raw.bin")}


def main():
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp(prefix="mtk_newui_")
    w = None
    try:
        w = g.MainWindow()
        w.connected = True
        w.session = FakeSession()
        w._gpt_ok = True
        calls = []
        w.run_mtk = lambda args, kind, label, timeout, cb=None: calls.append(
            {"args": args, "kind": kind, "label": label})
        g.ConfirmDialog = FakeConfirm
        g.BatchConfirmDialog = FakeConfirm
        g.RawAddressDialog = FakeRaw
        g.QMessageBox.information = staticmethod(lambda *a, **k: None)
        g.QMessageBox.warning = staticmethod(lambda *a, **k: None)
        g.QMessageBox.critical = staticmethod(lambda *a, **k: None)

        # 生成 Scatter
        out = os.path.join(tmp, "scatter.txt")
        old_save = g.QFileDialog.getSaveFileName
        g.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
        w.do_scatter_gen()
        g.QFileDialog.getSaveFileName = old_save
        sc = scatter.load(out)
        check("01 生成 Scatter", len(sc.entries) == 6 and sc.platform == "MT6991")

        # 导出 Preloader
        calls.clear()
        w.do_export_preloader()
        check("02 导出 Preloader", calls and "r" in calls[0]["args"] and
              "preloader" in calls[0]["args"])

        # 自定义地址读取
        calls.clear()
        w.do_rawaddr()
        check("03 自定义地址读取", calls and "ro" in calls[0]["args"])

        # 目录批量刷入
        calls.clear()
        d = os.path.join(tmp, "images")
        os.makedirs(d)
        open(os.path.join(d, "boot_a.bin"), "wb").write(b"x" * 1024)
        open(os.path.join(d, "userdata.bin"), "wb").write(b"x" * 1024)
        old_dir = g.QFileDialog.getExistingDirectory
        g.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: d)
        w.scatter = None
        w.do_batch_flash()
        g.QFileDialog.getExistingDirectory = old_dir
        check("04 目录批量刷入", calls and "script" in calls[0]["args"])

        # 分区多选回读/擦除
        w.part_page.fill(w.session.partitions, w._gpt_view(),
                         getattr(w.session, "partition_meta", {}))
        w.part_page.table.selectRow(0)
        calls.clear()
        w.do_read_selected()
        check("05 回读选中分区", calls and "script" in calls[0]["args"])
        calls.clear()
        w.do_erase_selected()
        check("06 关键分区擦除被拒绝", not calls)
        w.part_page.table.selectRow(3)  # userdata
        calls.clear()
        w.do_erase_selected()
        check("07 普通分区擦除", calls and "script" in calls[0]["args"])

        # 刷入选定分区
        w.part_page.table.selectRow(0)  # boot_a
        d2 = os.path.join(tmp, "selected_images")
        os.makedirs(d2)
        open(os.path.join(d2, "boot_a.bin"), "wb").write(b"x" * 1024)
        old_dir2 = g.QFileDialog.getExistingDirectory
        g.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: d2)
        calls.clear()
        w.do_write_selected()
        g.QFileDialog.getExistingDirectory = old_dir2
        check("08 刷入选定分区", calls and "script" in calls[0]["args"])

        # 恢复出厂，persist 不能进脚本
        calls.clear()
        w.do_factory()
        body = ""
        if calls:
            script = calls[0]["args"][-1]
            if os.path.isfile(script):
                body = open(script, encoding="ascii").read()
        check("09 恢复出厂安全", "persist" not in body and "userdata" in body)

        # 结构化日志
        w.session = logparse.Session("connect")
        w.on_stream("GPT Table: \r\n")
        w.on_stream("ERROR: failed to read\r\n")
        check("10 结构化日志", len(w.log_page.records) >= 2 and
              any(r["level"] == "ERROR" for r in w.log_page.records))
    finally:
        if w is not None:
            w.close()
    for r in rows:
        print("%-4s %-30s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
