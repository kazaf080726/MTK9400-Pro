# -*- coding: utf-8 -*-
"""37 项 GUI 回归（命令行运行器）。

用法（在 app/ 目录）：
    python tests/run_gui_tests.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as g  # noqa: E402
from tests.gui_suite import run_suite  # noqa: E402


def main():
    passed, failed, rows = run_suite(g)
    for result, name, note in rows:
        print("%-4s %-34s %s" % (result, name, note))
    print("")
    print("TOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
