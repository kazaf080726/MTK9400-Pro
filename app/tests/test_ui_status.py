# -*- coding: utf-8 -*-
"""新版状态区回归：只显示当前步骤、自动切换、日志常驻。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as g  # noqa: E402

BEFORE = (
    "Preloader - Status: Waiting for PreLoader VCOM\n"
    "Port - Device detected :)\n"
    "Preloader - Detected regular mode !\n"
    "Preloader - \tCPU:\t\t\tMT6991(Dimensity 9400 Ultra)\n"
    "Preloader - HW code:\t\t\t0x1357\n"
    "Uploading stage 1\n"
    "Jumping to 0x100000\n"
    "DA Stage 1 successfully loaded\n"
    "HeapBait - Successfully ran DA1 HeapBait\n"
    "XmlFlashExt - Patched CUSTOM command\n"
    "Uploading stage 2\n"
    "Progress: |████| 62.0% Upload: 0.8 MB/s\n"
)
AFTER = (
    "DAXML - Successfully booted to stage 2\n"
    "DAXML - SLA Signature was accepted.\n"
    "GPT Table:\n"
    "misc:     Offset 0x0000000000008000, Length 0x0000000000080000\n"
)

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
    app = QApplication.instance() or QApplication([])
    w = g.MainWindow()
    w.resize(1180, 780)
    w.show()
    app.processEvents()
    try:
        w.new_session("connect")
        for line in BEFORE.splitlines(True):
            w.on_stream(line)
        w._update_steps()
        app.processEvents()
        check("01 当前步骤自动切换", w.home_page.current_title.text() == "上传 DA2",
              w.home_page.current_title.text())
        check("02 步骤计数正确", w.home_page.counter.text() == "5 / 7",
              w.home_page.counter.text())
        check("03 状态胶囊进行中", "进行中" in w.home_page.status_chip.text())

        for line in AFTER.splitlines(True):
            w.on_stream(line)
        w.session.finish(0)
        w._update_steps()
        app.processEvents()
        check("04 完成后显示全部完成", w.home_page.current_title.text() == "全部完成",
              w.home_page.current_title.text())
        check("05 不再展开全部步骤",
              not w.home_page.timeline.isVisible() and
              not any(r.isVisible() for r in w.home_page.timeline.rows.values()))
        check("06 日志常驻右下", w.log_card.isVisible() and w.raw.isVisible() and
              w.splitter.count() == 2)
        check("07 右上状态常驻", w.home_page.step_area.isVisible() and
              w.home_page.isVisible())
    finally:
        w.close()
    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
