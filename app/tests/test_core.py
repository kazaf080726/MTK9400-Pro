# -*- coding: utf-8 -*-
"""业务层单元测试（不启动 Qt 窗口）。

运行：
    python tests/test_core.py
"""
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from core import config, parts, state  # noqa: E402
from core.session import Session, clean  # noqa: E402
from core.utils import hsize  # noqa: E402

SAMPLE = (
    "Port - Device detected :)\n"
    "Preloader - \tCPU:\t\t\tMT6991(Dimensity 9400 Ultra)\n"
    "Preloader - HW code:\t\t\t0x1357\n"
    "Uploading stage 1\n"
    "DA Stage 1 successfully loaded\n"
    "HeapBait - Successfully ran DA1 HeapBait\n"
    "Uploading stage 2\n"
    "DAXML - Successfully booted to stage 2\n"
    "DAXML - SLA Signature was accepted.\n"
    "GPT Table:\n"
    "boot_a:   Offset 0x0000000000488000, Length 0x0000000004000000\n"
)


def run():
    passed = failed = 0
    rows = []

    def check(name, cond, note=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            rows.append(("PASS", name, ""))
        else:
            failed += 1
            rows.append(("FAIL", name, note))

    check("01 ANSI 清洗", clean("\x1b[31mERR\x1b[0m") == "ERR")
    check("02 GPT 97 项", len(parts.GPT) == 97, str(len(parts.GPT)))
    check("03 中文说明", parts.describe("boot_a")[0] == "内核 A")
    check("04 未知分区兜底", parts.describe("no_such")[0] == "未知分区")
    check("05 备份脚本格式", parts.write_script.__name__ == "write_script")
    check("06 体积格式化", hsize(1024 ** 2) == "1.0 MB")

    s = Session("connect")
    for i in range(0, len(SAMPLE), 40):
        s.feed(SAMPLE[i:i + 40])
    s.finish(0)
    st = {x["key"]: x["status"] for x in s.step_rows()}
    check("07 设备芯片解析", "MT6991" in s.device["chip"], s.device["chip"])
    check("08 硬件码解析", s.device["hwcode"] == "0x1357", s.device["hwcode"])
    core_steps = ("handshake", "target", "da1", "bypass", "da2", "sla")
    check("09 六步完成", all(st[k] == "ok" for k in core_steps), str(st))
    check("10 分区解析", s.partition_count == 1, str(s.partition_count))
    check("11 无 ANSI 残留", all("\x1b" not in r["detail"] for r in s.step_rows()))

    sm = state.StateMachine()
    seen = []
    sm.subscribe(lambda old, new: seen.append(new))
    sm.sync(False, False)
    check("12 初始未连接", sm.state is state.AppState.DISCONNECTED)
    sm.sync(True, False)
    check("13 连接状态", sm.state is state.AppState.CONNECTED)
    sm.sync(True, True)
    check("14 操作中", sm.state is state.AppState.WORKING)
    sm.sync(False, False)
    check("15 状态通知", len(seen) >= 3, str(seen))
    check("16 连接态禁用 connect", "connect" not in
          state.allowed(state.AppState.CONNECTED, {"connect", "gpt"}))
    check("17 未连接只留连接类", state.allowed(
        state.AppState.DISCONNECTED, {"connect", "gpt", "zadig"}) == {"connect", "zadig"})
    check("18 分区尺寸解析", s.partition_sizes.get("boot_a") == 0x4000000,
          str(s.partition_sizes))
    check("19 preloader 禁止写入", "preloader" in parts.BLOCK_WRITE)
    check("20 preloader 禁止擦除", "preloader" in parts.BLOCK_ERASE)

    # 备份路径回归：曾经因为 config 里 os.chdir(BASE)，子进程 cwd 被改到 exe 目录，
    # 相对路径 backup_critical\xxx.bin 全部写失败。
    check("21 数据目录是绝对路径", os.path.isabs(config.WORK) and os.path.isdir(config.WORK))
    script = os.path.join(config.WORK, "_probe_backup.txt")
    parts.write_script(script, ["nvram"], "backup_critical")
    with open(script, encoding="ascii") as f:
        text = f.read()
    check("22 备份脚本使用相对目录", "r nvram backup_critical\\nvram.bin" in text, text)
    probe = os.path.join(config.DIR_CRIT, "_probe.bin")
    code = "open(r'backup_critical\\\\_probe.bin','wb').write(b'x')"
    child = subprocess.run([sys.executable, "-c", code], cwd=config.WORK,
                           capture_output=True, text=True)
    check("23 子进程 cwd 可写备份目录",
          child.returncode == 0 and os.path.isfile(probe) and os.path.getsize(probe) == 1,
          child.stderr)
    for path in (probe, script):
        try:
            os.remove(path)
        except OSError:
            pass

    for r in rows:
        print("%-4s %-34s %s" % r)
    print("\nTOTAL %d  PASS=%d  FAIL=%d" % (passed + failed, passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
