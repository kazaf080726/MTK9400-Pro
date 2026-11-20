# -*- coding: utf-8 -*-
"""pytest 入口：37 项 GUI 回归打包成一个测试用例。

没有 pytest 时也可以直接：
    python tests/test_gui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as g  # noqa: E402
from tests.gui_suite import run_suite  # noqa: E402


def test_gui_37_items():
    passed, failed, rows = run_suite(g)
    if failed:
        print("\n".join("%-4s %-34s %s" % r for r in rows if r[0] == "FAIL"))
    assert (passed, failed) == (37, 0), "37 项回归未全过：PASS=%d FAIL=%d" % (passed, failed)


if __name__ == "__main__":
    passed, failed, rows = run_suite(g)
    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    sys.exit(0 if failed == 0 else 1)
