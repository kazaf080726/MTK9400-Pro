# -*- coding: utf-8 -*-
"""V2 深度刷机页面：固件解析、预检、备份和按计划写入。"""
import os
import shlex
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
                               QCheckBox, QInputDialog, QApplication)

from core import config
from . import backup, firmware, lptools
from .workers import Worker


class DeepFlashPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pkg = None
        self.worker = None
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        title = QLabel("深度刷机 / 固件恢复")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        v.addWidget(title)
        tip = QLabel("支持 scatter 目录 / ZIP / OFP / OTA payload.bin；"
                     "默认不刷 preloader / nvram / nvdata / persist / seccfg。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6B7280;")
        v.addWidget(tip)
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText("选择包含 scatter.txt 的固件目录或 ZIP")
        b = QPushButton("浏览目录")
        b.clicked.connect(self.browse)
        f = QPushButton("选择文件")
        f.clicked.connect(self.browse_file)
        p = QPushButton("解析固件")
        p.clicked.connect(self.parse)
        self.btn_parse = p
        row.addWidget(self.path, 1)
        row.addWidget(b)
        row.addWidget(f)
        row.addWidget(p)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("刷机模式"))
        self.mode = QComboBox()
        self.mode.addItem("系统修复（不碰 preloader/NVRAM）", "repair")
        self.mode.addItem("全量固件（不含 preloader）", "full")
        self.mode.addItem("专家模式（含 preloader/关键分区）", "all")
        self.mode.currentIndexChanged.connect(self.mode_changed)
        row2.addWidget(self.mode)
        self.auto_backup = QCheckBox("刷前自动备份关键分区")
        self.auto_backup.setChecked(True)
        row2.addWidget(self.auto_backup)
        self.raw_mode = QCheckBox("无 GPT：按 scatter 原地址写入")
        self.raw_mode.setToolTip("需要先用“从 Scatter 重建 GPT”写入完整 GPT，或设备已有可用 GPT")
        row2.addWidget(self.raw_mode)
        row2.addStretch(1)
        v.addLayout(row2)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["写入", "分组", "分区", "镜像", "大小", "风险"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, w in ((0, QHeaderView.ResizeToContents), (1, QHeaderView.ResizeToContents),
                     (2, QHeaderView.Stretch), (3, QHeaderView.Stretch),
                     (4, QHeaderView.ResizeToContents), (5, QHeaderView.ResizeToContents)):
            self.table.horizontalHeader().setSectionResizeMode(i, w)
        v.addWidget(self.table, 1)
        bar = QHBoxLayout()
        for text, cb in (("安全全选", self.select_safe), ("全选", self.select_all),
                         ("开始刷机", self.start), ("解包 super", self.unpack_super),
                         ("sparse→raw", self.sparse_to_raw), ("lpmake", self.run_lpmake)):
            b = QPushButton(text)
            b.clicked.connect(cb)
            if text == "开始刷机":
                self.btn_start = b
            bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)
        self.status = QLabel("尚未解析固件")
        self.status.setStyleSheet("color:#6B7280;")
        v.addWidget(self.status)

    def browse(self):
        p = QFileDialog.getExistingDirectory(self, "选择固件目录", config.WORK)
        if p:
            self.path.setText(p)

    def browse_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择固件文件", config.WORK,
            "固件 (*.ofp *.zip *.bin);;所有文件 (*)")
        if p:
            self.path.setText(p)

    def parse(self):
        p = self.path.text().strip()
        if not p:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.main.progress_begin("解析固件")
        self.btn_parse.setEnabled(False)
        self.status.setText("正在后台解析固件…")
        self.worker = Worker(firmware.FirmwarePackage.load, p)
        self.worker.result.connect(self._parse_done)
        self.worker.failed.connect(self._parse_failed)
        self.worker.finished.connect(lambda: self.btn_parse.setEnabled(True))
        self.worker.start()

    def _parse_done(self, pkg):
        try:
            if self.pkg:
                self.pkg.cleanup()
            self.pkg = pkg
            self._fill()
            self.main.progress_end("固件解析完成")
            if self.pkg.errors:
                QMessageBox.warning(self, "固件问题", "\n".join(self.pkg.errors[:20]))
            self.status.setText("解析完成：%d 个镜像（%s）" %
                                (len(self.pkg.items), self.pkg.source_kind))
        except Exception as e:
            self._parse_failed(str(e))

    def _parse_failed(self, msg):
        self.main.progress_end("固件解析失败", failed=True)
        self.status.setText("固件解析失败")
        QMessageBox.critical(self, "固件解析失败", msg)

    def _fill(self):
        self.table.setRowCount(0)
        if not self.pkg:
            return
        for i, x in enumerate(self.pkg.items):
            self.table.insertRow(i)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            chk.setCheckState(Qt.Checked if x.selected else Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            self.table.setItem(i, 1, QTableWidgetItem(x.group))
            self.table.setItem(i, 2, QTableWidgetItem(x.name))
            self.table.setItem(i, 3, QTableWidgetItem(os.path.basename(x.image)))
            self.table.setItem(i, 4, QTableWidgetItem(_hsize(x.file_size)))
            self.table.setItem(i, 5, QTableWidgetItem(x.risk))

    def mode_changed(self):
        if self.pkg:
            self.pkg.select_mode(self.mode.currentData())
            self._fill()

    def _checks(self):
        for i, x in enumerate(self.pkg.items):
            x.selected = self.table.item(i, 0).checkState() == Qt.Checked

    def select_safe(self):
        if not self.pkg:
            return
        for i, x in enumerate(self.pkg.items):
            if x.group in ("boot", "system", "modem"):
                self.table.item(i, 0).setCheckState(Qt.Checked)
        self._checks()

    def select_all(self):
        if not self.pkg:
            return
        for i, _x in enumerate(self.pkg.items):
            self.table.item(i, 0).setCheckState(Qt.Checked)
        self._checks()

    def start(self):
        if not self.pkg:
            QMessageBox.information(self, "没有固件", "请先解析固件。")
            return
        self._checks()
        selected = [x for x in self.pkg.items if x.selected]
        if not selected:
            QMessageBox.information(self, "没有选择", "请选择要写入的分区。")
            return
        logical = [x.name for x in selected if x.logical]
        if logical:
            QMessageBox.critical(
                self, "逻辑分区不能直接写",
                "以下镜像是 super 内部逻辑分区，不是 GPT 物理分区：\n\n%s\n\n"
                "请先使用“解包 super / lpmake”生成 super.img，"
                "再刷写 super 分区。" % "、".join(logical[:20]))
            return
        if any(x.pending for x in selected):
            self._start_materialize(selected)
            return
        self._continue_start(selected)

    def _start_materialize(self, selected):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "正在解析", "后台解析还没有结束。")
            return
        self.main.progress_begin("解包 payload 选中分区")
        self.status.setText("正在后台解包选中的 payload 分区…")
        if hasattr(self, "btn_start"):
            self.btn_start.setEnabled(False)
        self.worker = Worker(self.pkg.materialize, selected)
        self.worker.result.connect(lambda _r: self._materialize_done(selected))
        self.worker.failed.connect(self._materialize_failed)
        self.worker.start()

    def _materialize_done(self, selected):
        self.main.progress_end("payload 解包完成")
        if hasattr(self, "btn_start"):
            self.btn_start.setEnabled(True)
        try:
            self._fill()
        except Exception:
            pass
        self._continue_start(selected)

    def _materialize_failed(self, msg):
        self.main.progress_end("payload 解包失败", failed=True)
        self.status.setText("payload 解包失败")
        if hasattr(self, "btn_start"):
            self.btn_start.setEnabled(True)
        QMessageBox.critical(self, "payload 解包失败", msg)

    def _continue_start(self, selected):
        errors, warnings = self.pkg.preflight()
        if errors:
            QMessageBox.critical(self, "预检失败", "\n".join(errors[:30]))
            return
        if warnings:
            self.main._log("[固件] " + "；".join(warnings[:10]))
        if any(x.group == "preloader" for x in selected) and self.mode.currentData() != "all":
            QMessageBox.critical(self, "拒绝", "当前模式不允许写 preloader。")
            return
        if any(x.group == "gpt" for x in selected) and self.mode.currentData() != "all":
            QMessageBox.critical(self, "拒绝", "GPT 镜像只能在专家模式写入。")
            return
        if any(x.group == "critical" for x in selected) and \
                QMessageBox.warning(self, "关键分区",
                                    "你选择了 nvram/nvdata/persist 等关键分区。\n"
                                    "写错会导致 IMEI/校准丢失。\n\n继续？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if self.raw_mode.isChecked():
            if self.auto_backup.isChecked():
                if not self.main.parser or not self.main.parser.partitions:
                    QMessageBox.critical(
                        self, "无法自动备份",
                        "raw 模式勾选了自动备份，但当前 GPT 不可读。\n"
                        "请先手动备份，或取消自动备份后确认风险。")
                    return
                self._auto_backup_then_flash(selected, raw=True)
            else:
                if QMessageBox.warning(
                        self, "没有自动备份",
                        "当前是 raw 模式，且未勾选自动备份关键分区。\n\n继续？",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                self._execute_raw(selected)
            return
        if self.auto_backup.isChecked():
            self._auto_backup_then_flash(selected)
        else:
            if QMessageBox.warning(self, "没有自动备份",
                                   "当前未勾选自动备份关键分区。\n\n继续刷机？",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self._execute(selected)

    def _auto_backup_then_flash(self, selected, raw=False):
        p = self.main.parser
        if not p or not p.partitions:
            QMessageBox.critical(self, "无法自动备份", "请先读信息 / 分区表。")
            return
        ss = int(p.sector_size or 0)
        meta = {"model": self.main.model.name if self.main.model else "",
                "platform": "MTK", "sector_size": ss,
                "total_sectors": int(p.total_sectors or 0),
                "disk_size": int(p.disk_size or 0), "disk_guid": ""}
        out = os.path.join(config.WORK, "auto_backup_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(out, exist_ok=True)
        names = []
        for n in p.partitions:
            if backup.group_of(n) in ("critical", "boot"):
                names.append(n)
        if not names:
            QMessageBox.critical(self, "无法自动备份", "当前分区表没有关键分区。")
            return
        steps = [["r", n, os.path.join(out, backup.safe_filename(n) + ".bin")] for n in names]
        self.status.setText("刷机前备份 %d 个关键分区…" % len(names))
        self.main.run_sequence(steps, "刷机前备份",
                               lambda results: self._after_backup(
                                   results, meta, out, names, selected, raw),
                               14400)

    def _after_backup(self, results, meta, out, names, selected, raw=False):
        if not results or any(r[0] != 0 for r in results):
            QMessageBox.critical(self, "备份失败", "刷机前备份失败，已中止。")
            return
        try:
            p = self.main.parser
            ss = int(meta.get("sector_size") or 0)
            parts = [{"name": n,
                      "start_lba": (int(p.partition_meta.get(n, {}).get("offset", 0) or 0) // ss
                                    if p and ss else 0),
                      "size_bytes": os.path.getsize(os.path.join(out, backup.safe_filename(n) + ".bin"))}
                     for n in names]
            m = backup.make_manifest(meta, parts, out, selected=names)
            backup.save_manifest(m, out)
            self.main._log("[深度刷机] 前置备份完成：%s" % out)
        except Exception as e:
            QMessageBox.critical(self, "备份清单失败", str(e))
            return
        if raw:
            self._execute_raw(selected)
        else:
            self._execute(selected)

    def _execute_raw(self, selected):
        missing = [x.name for x in selected if not x.start or x.start <= 0]
        if missing:
            QMessageBox.critical(self, "无法原地址写入",
                                 "以下分区没有 scatter 起始地址：\n" + "、".join(missing[:20]))
            return
        if QMessageBox.warning(
                self, "确认原地址写入",
                "将按 scatter 的 physical_start_addr 写入 %d 个镜像。\n\n"
                "这个模式不依赖 GPT 分区名解析，但不会自动创建 GPT。\n"
                "如果 GPT 已经损坏，请先执行“从 Scatter 重建 GPT”。\n\n确定继续？" % len(selected),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        steps = [["wo", hex(x.start), hex(x.file_size), x.image] for x in selected]
        labels = ["%s · %s" % (x.name, _hsize(x.file_size)) for x in selected]
        self.main.run_sequence(steps, "按原地址刷写", self._done, 14400,
                               labels=labels)

    def _execute(self, selected):
        if QMessageBox.warning(self, "确认刷机",
                               "将写入 %d 个分区。\n\n确定开始？" % len(selected),
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        steps = [["w", x.name, x.image] for x in selected]
        labels = ["%s · %s" % (x.name, _hsize(x.file_size)) for x in selected]
        if self.mode.currentData() in ("full", "all"):
            for n in ("userdata", "metadata", "cache"):
                steps.append(["e", n])
                labels.append(n + " · 擦除")
        self.status.setText("正在刷写 %d 个分区…" % len(selected))
        self.main.run_sequence(steps, "深度刷机", self._done, 14400, labels=labels)

    def unpack_super(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 super.img", config.WORK,
                                           "镜像 (*.img);;所有文件 (*)")
        if not p:
            return
        out = QFileDialog.getExistingDirectory(self, "选择解包目录", config.WORK)
        if not out:
            return
        try:
            self.main.progress_begin("解包 super")
            self.status.setText("正在解包 super…")
            QApplication.processEvents()
            lptools.lpunpack(p, out)
            self.main.progress_end("super 解包完成")
            self.status.setText("super 解包完成：%s" % out)
            self.main._log("[lpunpack] %s -> %s" % (p, out))
        except Exception as e:
            self.main.progress_end("super 解包失败", failed=True)
            self.status.setText("super 解包失败")
            QMessageBox.critical(self, "lpunpack 失败", str(e))

    def sparse_to_raw(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 sparse 镜像", config.WORK,
                                           "镜像 (*.img);;所有文件 (*)")
        if not p:
            return
        out, _ = QFileDialog.getSaveFileName(self, "保存 raw 镜像", p + ".raw")
        if not out:
            return
        try:
            self.main.progress_begin("展开 sparse")
            self.status.setText("正在展开 sparse…")
            QApplication.processEvents()
            lptools.simg2img(p, out)
            self.main.progress_end("sparse 展开完成")
            self.status.setText("sparse 展开完成：%s" % out)
            self.main._log("[simg2img] %s -> %s" % (p, out))
        except Exception as e:
            self.main.progress_end("sparse 展开失败", failed=True)
            self.status.setText("sparse 展开失败")
            QMessageBox.critical(self, "simg2img 失败", str(e))

    def run_lpmake(self):
        text, ok = QInputDialog.getText(
            self, "lpmake",
            "输入 lpmake 参数（输出路径写在参数里）：")
        if not ok or not text.strip():
            return
        try:
            self.main.progress_begin("lpmake")
            QApplication.processEvents()
            args = shlex.split(text)
            lptools.lpmake(args)
            self.main.progress_end("lpmake 完成")
            self.status.setText("lpmake 完成")
            self.main._log("[lpmake] " + text)
        except Exception as e:
            self.main.progress_end("lpmake 失败", failed=True)
            self.status.setText("lpmake 失败")
            QMessageBox.critical(self, "lpmake 失败", str(e))

    def _done(self, results):
        if results and all(r[0] == 0 and not r[2] for r in results):
            self.status.setText("刷机完成")
            self.main._log("[深度刷机] 完成")
        else:
            self.status.setText("刷机失败")
            self.main._log("[深度刷机] 失败")

    def closeEvent(self, e):
        try:
            if self.worker is not None and self.worker.isRunning():
                self.worker.wait(3000)
        except Exception:
            pass
        try:
            if self.pkg:
                self.pkg.cleanup()
        except Exception:
            pass
        super().closeEvent(e)


def _hsize(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u == "B" else "%.2f %s") % (n, u)
        n /= 1024
