# -*- coding: utf-8 -*-
"""真机只读验证脚本（不写手机）。

用法：
    python tests/real_readonly.py

前提：手机进入 Preloader，COM 口没有被其它工具占用。
脚本只执行 printgpt 和读取 preloader，不发送 w/e/wo。
"""
import os
import re
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtCore import QCoreApplication  # noqa: E402
from core import config, mtk, toolfiles  # noqa: E402
from core import session as logparse  # noqa: E402


def _base(tf):
    args = ["--skipmeid"]
    if tf.get("serialport"):
        args += ["--serialport", tf["serialport"]]
    if tf.get("da"):
        args += ["--loader", tf["da"]]
    if tf.get("preloader"):
        args += ["--preloader", tf["preloader"]]
    if tf.get("use_auth") and tf.get("auth"):
        args += ["--auth", tf["auth"]]
    return args


def main():
    tf = toolfiles.load(config.WORK)
    if not tf.get("serialport"):
        print("SKIP: 没有配置串口（请在 GUI 里设置 COM 口）")
        return 0
    app = QCoreApplication([])
    sess = mtk.MtkSession(_base(tf))
    lines = []
    done = []
    sess.line.connect(lambda s: lines.append(s))
    sess.done.connect(lambda rc, text, to: done.append((rc, text, to)))
    sess.start()
    try:
        sess.submit(["printgpt"], 90)
        end = time.time() + 95
        while time.time() < end and not done:
            app.processEvents()
            time.sleep(0.02)
        text = "".join(lines)
        if not done or done[-1][0] != 0 or "GPT Table" not in text:
            print("FAIL: 未能读取 GPT")
            print(text[-1500:])
            return 2
        print("PASS: GPT 读取成功")
        names = set(re.findall(r"^(\S+):\s+Offset 0x", text, re.M))
        target = "preloader" if "preloader" in names else (
            "misc" if "misc" in names else (sorted(names)[0] if names else "preloader"))
        print("INFO: 只读目标分区 %s，进程 PID %s" %
              (target, getattr(sess.proc, "pid", "?")))

        done.clear()
        lines.clear()
        out = os.path.join(tempfile.gettempdir(), "real_%s_readonly.bin" % target)
        sess.submit(["r", target, out], 90)
        end = time.time() + 95
        while time.time() < end and not done:
            app.processEvents()
            time.sleep(0.02)
        size = os.path.getsize(out) if os.path.exists(out) else -1
        if not done or done[-1][0] != 0 or size <= 0:
            print("FAIL: %s 只读失败" % target)
            print("".join(lines)[-1500:])
            return 3
        print("PASS: %s 只读成功，%d 字节，%s" % (target, size, out))
        return 0
    finally:
        sess.stop()
        sess.wait(3000)


if __name__ == "__main__":
    sys.exit(main())
