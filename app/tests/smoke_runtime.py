# -*- coding: utf-8 -*-
"""运行时冒烟：真实启动一次 mtkclient 子进程，验证线程 / 信号 / 收尾。"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as g  # noqa: E402


def main():
    app = QApplication.instance() or QApplication([])
    w = g.MainWindow()
    w.show()
    app.processEvents()

    seen = {"done": None}
    marks = []

    def cb(rc, text, timed_out):
        seen["done"] = (rc, len(text), timed_out)
        marks.append("done")

    w.run_mtk(["-h"], "connect", "help", 20, cb)
    deadline = time.time() + 30
    while time.time() < deadline and seen["done"] is None:
        app.processEvents()
        time.sleep(0.03)
    app.processEvents()

    ok = True
    if seen["done"] is None:
        print("FAIL 子进程没有在 30s 内结束")
        ok = False
    else:
        rc, n, timed_out = seen["done"]
        print("done rc=%s bytes=%s timeout=%s" % (rc, n, timed_out))
        ok = ok and rc == 0 and n > 100 and not timed_out
    ok = ok and w.busy is False
    ok = ok and "usage:" in w.raw.toPlainText()
    print("busy=%s raw=%d" % (w.busy, len(w.raw.toPlainText())))
    print("RESULT:", "OK" if ok else "FAIL")
    w.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
