# -*- coding: utf-8 -*-
"""GUI 回归：动态 GPT、全量/自定义备份、读取、写入、校验、救砖入口。"""
import os
import shutil
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from core import rescue  # noqa: E402

SAMPLE = (
    "Preloader - Status: Waiting for PreLoader VCOM\n"
    "Port - Device detected :)\n"
    "Preloader - Detected regular mode !\n"
    "Preloader - \tCPU:\t\t\tMT6991(Dimensity 9400 Ultra)\n"
    "Preloader - HW code:\t\t\t0x1357\n"
    "Preloader - HW Ver:\t\t\t0xca01\n"
    "Preloader - SBC enabled:\t\tTrue\n"
    "Uploading stage 1\n"
    "Jumping to 0x100000\n"
    "DA Stage 1 successfully loaded\n"
    "HeapBait - Successfully ran DA1 HeapBait\n"
    "XmlFlashExt - Patched CUSTOM command\n"
    "Uploading stage 2\n"
    "Progress: |████| 45.3% Upload: 0.4 MB/s\n"
    "Progress: |████| 99.0% Upload: 1.0 MB/s\n"
    "DAXML - Successfully booted to stage 2\n"
    "DAXML - SLA Signature was accepted.\n"
    "GPT Table:\n"
    "misc:     Offset 0x0000000000008000, Length 0x0000000000080000, Flags 0x0, "
    "UUID 11111111-1111-1111-1111-111111111111, Type EFI_BASIC_DATA\n"
    "boot_a:   Offset 0x0000000000488000, Length 0x0000000004000000, Flags 0x0, "
    "UUID 22222222-2222-2222-2222-222222222222, Type EFI_BASIC_DATA\n"
    "boot_b:   Offset 0x0000000004488000, Length 0x0000000004000000, Flags 0x0, "
    "UUID 33333333-3333-3333-3333-333333333333, Type EFI_BASIC_DATA\n"
    "userdata: Offset 0x0000000008488000, Length 0x0000000004000000, Flags 0x0, "
    "UUID 44444444-4444-4444-4444-444444444444, Type EFI_BASIC_DATA\n"
    "seccfg:   Offset 0x000000000c488000, Length 0x0000000000100000, Flags 0x0, "
    "UUID 55555555-5555-5555-5555-555555555555, Type EFI_BASIC_DATA\n"
    "Total disk size:0x0000000020000000, sectors:0x0000000000100000\n"
    "\x1b[31mError on sending reboot\x1b[0m\n"
)


class Recorder(object):
    def __init__(self):
        self.rows = []
        self.passed = 0
        self.failed = 0

    def check(self, name, cond, note=""):
        if cond:
            self.passed += 1
            self.rows.append(("PASS", name, ""))
        else:
            self.failed += 1
            self.rows.append(("FAIL", name, note))


def _raw_for(session):
    ps = []
    for n in session.partitions:
        meta = session.partition_meta.get(n, {})
        off = int(meta.get("offset", 0))
        size = int(meta.get("size", 0))
        ps.append({"name": n,
                   "type_guid": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                   "unique_guid": meta.get("uuid") or ("00000000-0000-0000-0000-%012d" % abs(hash(n))),
                   "first_lba": off // 512,
                   "last_lba": (off + size) // 512 - 1,
                   "flags": 0})
    return rescue.build_raw_gpt(ps, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                                int(session.total_sectors), 512)[:2]


def run_suite(g):
    app = QApplication.instance() or QApplication([])
    rec = Recorder()
    records = {"critical": [], "warning": [], "information": []}
    orig = (QMessageBox.critical, QMessageBox.warning, QMessageBox.information,
            QMessageBox.question, g.ConfirmDialog.exec, g.QDialog.exec,
            g.PartitionSelectDialog)
    QMessageBox.critical = staticmethod(lambda *a, **k: records["critical"].append(a[1] + "|" + a[2]))
    QMessageBox.warning = staticmethod(lambda *a, **k: records["warning"].append(a[1] + "|" + a[2]))
    QMessageBox.information = staticmethod(lambda *a, **k: records["information"].append(a[1] + "|" + a[2]))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    g.ConfirmDialog.exec = lambda self: QDialog.Accepted
    g.QDialog.exec = lambda self: QDialog.Accepted

    class FakeSelect:
        def __init__(self, sizes, parent=None):
            self.sizes = sizes

        def exec(self):
            return QDialog.Accepted

        def selected_names(self):
            return ["boot_a", "misc"]

    g.PartitionSelectDialog = FakeSelect
    try:
        import main as _main_mod
        _main_orig_select = _main_mod.PartitionSelectDialog
        _main_mod.PartitionSelectDialog = FakeSelect
    except Exception:
        _main_mod = None
        _main_orig_select = None

    # 测试目录必须是干净状态，避免上一次运行的 backup_custom 干扰“只备份勾选分区”。
    for _d in (g.config.DIR_FULL, g.config.DIR_CUSTOM):
        shutil.rmtree(_d, ignore_errors=True)
        shutil.rmtree(_d + ".new", ignore_errors=True)
        shutil.rmtree(_d + ".old", ignore_errors=True)

    w = g.MainWindow()
    w.resize(1180, 780)
    w.show()
    app.processEvents()
    calls = []
    w.connected = True
    w.busy = False
    w._set_enabled(True)

    def fake_run(args, kind, label, timeout, on_done):
        calls.append({"args": list(args), "kind": kind, "label": label, "timeout": timeout})
        # 模拟 mtkclient 输出，让 session 拿到现场 GPT
        w.session = g.logparse.Session(kind)
        for ch in [SAMPLE[i:i + 160] for i in range(0, len(SAMPLE), 160)]:
            w.on_stream(ch)
        ctx = w._backup_ctx
        if ctx:
            for n in ctx["names"]:
                with open(os.path.join(ctx["stage"], n + ".bin"), "wb") as f:
                    f.truncate(int(ctx["expected"].get(n, 0)))
            primary, backup = _raw_for(w.session)
            with open(os.path.join(ctx["stage"], "gpt_primary.raw"), "wb") as f:
                f.write(primary)
            with open(os.path.join(ctx["stage"], "gpt_backup.raw"), "wb") as f:
                f.write(backup)
        if on_done:
            w._done(0, SAMPLE, False, on_done)
        else:
            w._done(0, SAMPLE, False, None)

    w.run_mtk = fake_run

    def click(key, wait=False):
        calls.clear()
        for k in records:
            records[k].clear()
        w.btns[key].click()
        app.processEvents()
        if wait:
            end = time.time() + 20
            while time.time() < end and (w.busy or w._hashing):
                app.processEvents()
                time.sleep(0.02)
            app.processEvents()

    try:
        # UI
        rec.check("01 新按钮存在", all(k in w.btns for k in ("full", "custom", "pack", "rescue")))
        rec.check("02 旧按钮已删除", not any(k in w.btns for k in ("crit", "imp")))
        geo = [(k, b.width(), b.height(), b.geometry().top()) for k, b in w.btns.items()]
        rec.check("03 按钮尺寸正常", all(sz[1] >= 100 and sz[2] >= 30 for sz in geo))
        ys = sorted(b.geometry().top() for b in w.btns.values())
        rec.check("04 按钮不重叠", all(ys[i + 1] - ys[i] >= 36 for i in range(len(ys) - 1)))

        # 动态 GPT
        click("connect", wait=True)
        rec.check("05 连接 -> printgpt", calls and calls[0]["args"][0] == "printgpt")
        rec.check("06 现场分区数", w.info_labels["parts"].text() == "5", w.info_labels["parts"].text())
        rec.check("07 总扇区已解析", w.session.total_sectors == 0x100000,
                  str(w.session.total_sectors))
        rec.check("08 GPT 结构有效", w._gpt_ok is True)
        rec.check("09 分区中文/未知可显示",
                  w.part_page is not None and w.session.partition_sizes.get("misc") == 0x80000)

        # 全量备份：脚本含 GPT 原始扇区，排除 userdata
        click("full", wait=True)
        rec.check("10 全量 -> backup_full 脚本",
                  calls and any(str(a).endswith("backup_full.txt") for a in calls[0]["args"]),
                  str(calls[:1]))
        script = os.path.join(g.config.WORK, "backup_full.txt")
        with open(script, encoding="ascii") as f:
            content = f.read()
        rec.check("11 全量脚本含 GPT 主扇区分块",
                  "ro 0x0 0x4000 backup_full.new\\gpt_primary.raw.part0" in content and
                  "gpt_backup.raw.part" not in content)
        rec.check("12 全量脚本排除 userdata", " userdata " not in content)
        rec.check("13 全量备份完成", os.path.isfile(os.path.join(g.config.DIR_FULL, "misc.bin")) and
                  os.path.isfile(os.path.join(g.config.DIR_FULL, "manifest.sha256.json")))
        rec.check("14 全量备份含 GPT raw",
                  os.path.isfile(os.path.join(g.config.DIR_FULL, "gpt_primary.raw")))

        # 自定义多选
        click("custom", wait=True)
        rec.check("15 自定义 -> backup_custom 脚本",
                  calls and any(str(a).endswith("backup_custom.txt") for a in calls[0]["args"]),
                  str(calls[:1]))
        check_custom = os.path.isfile(os.path.join(g.config.DIR_CUSTOM, "boot_a.bin")) and \
            not os.path.isfile(os.path.join(g.config.DIR_CUSTOM, "boot_b.bin"))
        rec.check("16 自定义只备份勾选分区", check_custom)

        # 读取
        w._ask_text = lambda *a, **k: "boot_a"
        click("read", wait=True)
        rec.check("17 读取 -> r boot_a", calls and calls[0]["args"][0] == "r" and
                  calls[0]["args"][1] == "boot_a")

        # 写入：准备同尺寸备份
        bak = os.path.join(g.DIR_RESCUE, "boot_b.bin")
        with open(bak, "wb") as f:
            f.truncate(w.session.partition_sizes["boot_b"])
        img = os.path.join(g.DIR_WRITE, "_t.bin")
        with open(img, "wb") as f:
            f.write(b"\0" * w.session.partition_sizes["boot_b"])
        w._pick_file = lambda files: "_t.bin"
        w._ask_text = lambda *a, **k: "boot_b"
        click("write", wait=True)
        rec.check("18 写入动态分区 -> w boot_b", calls and calls[0]["args"][0] == "w" and
                  calls[0]["args"][1] == "boot_b")

        # 擦除
        w._ask_text = lambda *a, **k: "userdata"
        click("erase", wait=True)
        rec.check("19 擦除 -> e userdata", calls and calls[0]["args"][0] == "e" and
                  calls[0]["args"][1] == "userdata")
        w._ask_text = lambda *a, **k: "boot_a"
        click("erase", wait=True)
        rec.check("20 禁止擦除 boot_a", any("禁止擦除" in x for x in records["critical"]))
        w._ask_text = lambda *a, **k: "seccfg"
        click("write", wait=True)
        rec.check("21 禁止写 seccfg", any("禁止写入名单" in x for x in records["critical"]))

        # 重置
        click("reset", wait=True)
        rec.check("22 重启 -> reset", calls and calls[0]["args"][0] == "reset")
        rec.check("23 重启后断开/回主页", w.connected is False and w.step_area.isVisible())

        # 校验/环境检查不调 mtk
        w.connected = True
        w._set_enabled(True)
        click("verify", wait=True)
        rec.check("24 校验不调 mtk", len(calls) == 0)
        click("env", wait=True)
        rec.check("25 环境检查不调 mtk", len(calls) == 0)

        # 状态解析与日志
        w.session = g.logparse.Session("connect")
        for ch in [SAMPLE[i:i + 120] for i in range(0, len(SAMPLE), 120)]:
            w.on_stream(ch)
        w.session.finish(0)
        w._update_steps()
        raw = w.raw.toPlainText()
        rec.check("26 六步全部 ok", all(
            {r["key"]: r["status"] for r in w.session.step_rows()}.get(k) == "ok"
            for k in ("handshake", "target", "da1", "bypass", "da2", "sla")))
        rec.check("27 原始日志无 ESC", "\x1b" not in raw)
        rec.check("28 中文正常", "连接" in raw or "CPU" in raw)

        # 中止
        class FakeWorker:
            def __init__(self):
                self.stopped = False
                self.running = True

            def isRunning(self):
                return self.running

            def stop(self):
                self.stopped = True

        fw = FakeWorker()
        w.worker = fw
        w.busy = True
        w.btn_stop.setEnabled(True)
        w.do_stop()
        rec.check("29 中止调用 stop", fw.stopped is True and w.stop_requested is True)
        w.busy = False

        # 未连接时点“读取分区表”应自动发起连接
        w.connected = False
        w._set_enabled(True)
        for k in records:
            records[k].clear()
        click("gpt", wait=True)
        rec.check("30 未连接自动连接",
                  bool(calls) and calls[0]["args"][0] == "printgpt")

        # 救砖入口存在、包格式/核心由 test_rescue 覆盖
        rec.check("31 救砖打包/恢复按钮存在",
                  w.btns["pack"].isEnabled() and "rescue" in w.btns)
    finally:
        try:
            w.close()
        except Exception:
            pass
        (QMessageBox.critical, QMessageBox.warning, QMessageBox.information,
         QMessageBox.question, g.ConfirmDialog.exec, g.QDialog.exec,
         g.PartitionSelectDialog) = orig
        if _main_mod is not None:
            _main_mod.PartitionSelectDialog = _main_orig_select
        app.processEvents()

    return rec.passed, rec.failed, rec.rows
