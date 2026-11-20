# -*- coding: utf-8 -*-
"""生成重构后 UI 的预览图（真实 Windows 平台，不使用 offscreen）。"""
import os
import sys
import time

os.environ.pop("QT_QPA_PLATFORM", None)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as g  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from ui import theme  # noqa: E402

SAMPLE = (
    "Preloader - Status: Waiting for PreLoader VCOM\n"
    "Port - Device detected :)\n"
    "Preloader - Detected regular mode !\n"
    "Preloader - \tCPU:\t\t\tMT6991(Dimensity 9400 Ultra)\n"
    "Preloader - HW code:\t\t\t0x1357\n"
    "Preloader - SBC enabled:\t\tTrue\n"
    "Uploading stage 1\n"
    "Jumping to 0x100000\n"
    "DA Stage 1 successfully loaded\n"
    "HeapBait - Successfully ran DA1 HeapBait\n"
    "XmlFlashExt - Patched CUSTOM command\n"
    "Uploading stage 2\n"
    "Progress: |████| 99.0% Upload: 1.0 MB/s\n"
    "DAXML - Successfully booted to stage 2\n"
    "DAXML - SLA Signature was accepted.\n"
    "GPT Table:\n"
    "misc:     Offset 0x0000000000008000, Length 0x0000000000080000\n"
    "boot_a:   Offset 0x0000000000488000, Length 0x0000000004000000\n"
    "Total disk size:0x000000772c019000\n"
)


def pump(app, n=12):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.04)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.app_qss())
    w = g.MainWindow()
    w.resize(1180, 780)
    w.show()
    pump(app)

    w.new_session("connect")
    for i in range(0, len(SAMPLE), 120):
        w.on_stream(SAMPLE[i:i + 120])
    w.session.finish(0)
    w._update_steps()
    w.connected = True
    w.set_pill("已连接 MT6991", theme.GREEN)
    w._set_enabled(True)
    w.btns["connect"].setEnabled(False)
    w._sync_state()
    w.ring.set_indeterminate(False, theme.GREEN)
    w.ring.set_value_anim(100, theme.GREEN)
    w.ring.set_text("完成", "")
    w.ring_cap.setText("已读取 97 个分区")
    w.boot_hint.setVisible(False)
    w._set_warn("")
    w.status.setText("连接成功 · 已读取分区表")
    w.status.setStyleSheet("color:%s;font-size:10px;" % theme.GREEN)
    w.badge.setText("自检通过")
    w.badge.setStyleSheet("color:%s;font-size:10px;" % theme.GREEN)
    pump(app)
    out = os.path.join(APP_DIR, "gui3_preview.png")
    w.grab().save(out)

    w.show_page(1)
    w.part_page.fill(list(g.GPT.keys()), g.GPT)
    w.part_page.set_summary("共 97 个分区，已全部翻译")
    pump(app)
    w.grab().save(os.path.join(APP_DIR, "parts_preview.png"))

    w.show_page(2)
    names = g.parts.important_names()[:12]
    w.backup_page.reset(names, sum(g.parts.GPT.get(n, 0) for n in names))
    for i, n in enumerate(names):
        w.backup_page.mark(n, "ok" if i < 5 else ("running" if i == 5 else "等待"))
    pump(app)
    w.grab().save(os.path.join(APP_DIR, "backup_preview.png"))

    w.show_page(4)
    for i in range(30):
        w.append_log("Preloader - line %02d  ·  DA stage 2  ·  partition boot_a 0x%08x" % (i, i * 4096))
    pump(app)
    w.grab().save(os.path.join(APP_DIR, "log_preview.png"))

    w.show_page(3)
    pump(app)
    w.grab().save(os.path.join(APP_DIR, "write_preview.png"))

    print("saved previews")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
