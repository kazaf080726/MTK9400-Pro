# -*- coding: utf-8 -*-
"""管理员启动门槛测试：非管理员不得进入主界面/自检。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main as g  # noqa: E402

passed = 0
failed = 0


def check(name, ok, note=""):
    global passed, failed
    if ok:
        passed += 1
        print("PASS " + name)
    else:
        failed += 1
        print("FAIL " + name + ("  " + str(note) if note else ""))


class FakeBox:
    Warning = 1
    AcceptRole = 2
    RejectRole = 3

    def __init__(self, *a, **k):
        self._clicked = None

    def setIcon(self, *a):
        pass

    def setWindowTitle(self, *a):
        pass

    def setText(self, *a):
        pass

    def setInformativeText(self, *a):
        pass

    def addButton(self, text, role):
        if role == self.AcceptRole:
            self._clicked = text
        return text

    def setDefaultButton(self, *a):
        pass

    def exec(self):
        pass

    def clickedButton(self):
        return self._clicked

    @staticmethod
    def critical(*a, **k):
        pass


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    old_admin = g.admin.is_admin
    old_elevate = g.admin.elevate
    old_box = g.QMessageBox
    try:
        g.admin.is_admin = lambda: True
        check("01 管理员允许进入", g.ensure_admin_gui(app) is True)

        g.admin.is_admin = lambda: False
        g.admin.elevate = lambda: False
        g.QMessageBox = FakeBox
        check("02 非管理员拒绝进入", g.ensure_admin_gui(app) is False)
        check("03 非管理员不会启动自检", g.admin.is_admin() is False)

        g.admin.elevate = lambda: True
        check("04 提权启动后旧进程退出", g.ensure_admin_gui(app) is False)
    finally:
        g.admin.is_admin = old_admin
        g.admin.elevate = old_elevate
        g.QMessageBox = old_box

    print("\nTOTAL 4  PASS=%d  FAIL=%d" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
