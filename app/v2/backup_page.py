# -*- coding: utf-8 -*-
"""V2 深度备份 / 恢复页面。"""
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QFileDialog, QMessageBox, QInputDialog, QProgressBar)

from core import config
from . import backup, gpt


class BackupPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.items = []
        self._starts = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        title = QLabel("深度备份 / 恢复")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        v.addWidget(title)
        tip = QLabel("关键分区：nvram / nvdata / persist / proinfo / seccfg / frp / misc。"
                     "恢复前会校验 manifest、SHA256、扇区、容量和磁盘 GUID。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6B7280;")
        v.addWidget(tip)
        bar = QHBoxLayout()
        for text, cb in (("刷新分区", self.refresh), ("选择关键分区", self.select_critical),
                         ("全选", self.select_all), ("开始备份", self.do_backup),
                         ("恢复备份", self.do_restore)):
            b = QPushButton(text)
            b.clicked.connect(cb)
            bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["备份", "分组", "分区", "大小", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        v.addWidget(self.table, 1)
        self.status = QLabel("先完成“读信息 / 读分区表”")
        self.status.setStyleSheet("color:#6B7280;")
        v.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setFormat("备份 %p%")
        v.addWidget(self.progress)

    def _meta(self, required=True):
        p = self.main.parser
        if not p or not p.partitions:
            if required:
                QMessageBox.information(self, "没有分区表", "请先在 MTK 页面读信息 / 分区表。")
            return None
        ss = int(p.sector_size or 0)
        total = int(p.total_sectors or 0)
        return {"model": self.main.model.name if self.main.model else "",
                "platform": "MTK", "sector_size": ss, "total_sectors": total,
                "disk_size": int(p.disk_size or ss * total), "disk_guid": ""}

    def refresh(self):
        p = self.main.parser
        if not p:
            self.status.setText("没有分区表")
            return
        ss = int(p.sector_size or 512)
        self.items = []
        self._starts = {}
        for n in p.partitions:
            m = p.partition_meta.get(n, {})
            size = int(p.partition_sizes.get(n, 0) or 0)
            start_lba = int(m.get("offset", 0) or 0) // ss
            self._starts[n] = start_lba
            self.items.append({"name": n, "start_lba": start_lba,
                               "size_bytes": size})
        self.table.setRowCount(len(self.items))
        for i, r in enumerate(self.items):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            chk.setCheckState(Qt.Checked if backup.default_selected(r["name"]) else Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            self.table.setItem(i, 1, QTableWidgetItem(backup.group_of(r["name"])))
            self.table.setItem(i, 2, QTableWidgetItem(r["name"]))
            self.table.setItem(i, 3, QTableWidgetItem(_hsize(r["size_bytes"])))
            self.table.setItem(i, 4, QTableWidgetItem(""))
        self.status.setText("共 %d 个分区" % len(self.items))

    def _set_checks(self, pred):
        for i, r in enumerate(self.items):
            self.table.item(i, 0).setCheckState(Qt.Checked if pred(r) else Qt.Unchecked)

    def select_critical(self):
        self._set_checks(lambda r: backup.group_of(r["name"]) in ("critical", "boot"))

    def select_all(self):
        self._set_checks(lambda r: True)

    def _selected(self):
        out = []
        for i, r in enumerate(self.items):
            it = self.table.item(i, 0)
            if it and it.checkState() == Qt.Checked:
                out.append(r)
        return out

    def do_backup(self):
        meta = self._meta()
        if not meta:
            return
        selected = self._selected()
        if not selected:
            QMessageBox.information(self, "没有选择", "请选择要备份的分区。")
            return
        base = QFileDialog.getExistingDirectory(self, "选择备份保存目录", config.WORK)
        if not base:
            return
        out = os.path.join(base, "Backup_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(out, exist_ok=True)
        if self.main.parser and self.main.parser.disk_size:
            def after_gpt(results, m2, pp, bp):
                if results and results[-1][0] == 0:
                    try:
                        img = self.main._gpt_parse_current(m2, pp, bp)
                        img.save(os.path.join(out, "gpt"))
                        meta["disk_guid"] = img.disk_guid
                        meta["gpt"] = {"dir": "gpt", "disk_guid": img.disk_guid}
                    except Exception as e:
                        self.main._log("[备份] GPT 备份失败：" + str(e))
                self._start_partition_backup(meta, selected, out)
            self.main._gpt_read_current("备份 GPT", after_gpt, "v2_backup_gpt")
        else:
            self._start_partition_backup(meta, selected, out)

    def _start_partition_backup(self, meta, selected, out):
        paths = {}
        steps = []
        labels = []
        for r in selected:
            p = os.path.join(out, backup.safe_filename(r["name"]) + ".bin")
            paths[r["name"]] = p
            steps.append(["r", r["name"], p])
            labels.append("%s · %s" % (r["name"], _hsize(r["size_bytes"])))
        self.status.setText("正在备份 %d 个分区…" % len(selected))
        self.progress.setVisible(True)
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress.setFormat("备份 0/%d" % len(selected))
        self.main.run_sequence(
            steps, "备份分区",
            lambda results: self._backup_done(results, meta, out, paths),
            14400, on_step=self._backup_step, labels=labels)

    def _backup_step(self, index, total, args):
        name = args[1] if len(args) > 1 else ""
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.progress.setFormat("备份 %d/%d · %s" % (index + 1, total, name))
        self.status.setText("正在备份 %d/%d：%s" % (index + 1, total, name))
        for i, r in enumerate(self.items):
            if r["name"] == name and self.table.item(i, 0).checkState() == Qt.Checked:
                self.table.item(i, 4).setText("备份中")
                break

    def _backup_done(self, results, meta, out, paths):
        self.progress.setVisible(False)
        if not results or any(r[0] != 0 for r in results):
            self.status.setText("备份失败")
            QMessageBox.critical(self, "备份失败", "至少一个分区读取失败。")
            return
        parts = [{"name": n, "start_lba": self._starts.get(n, 0),
                  "size_bytes": os.path.getsize(p)}
                 for n, p in paths.items()]
        try:
            m = backup.make_manifest(meta, parts, out, selected=paths,
                                     gpt=meta.get("gpt"))
            backup.save_manifest(m, out)
            self.status.setText("备份完成：%s" % out)
            self.main._log("[备份] 完成 %d 个分区：%s" % (len(parts), out))
            QMessageBox.information(self, "备份完成",
                                    "目录：\n%s\n\n分区：%d" % (out, len(parts)))
        except Exception as e:
            self.status.setText("manifest 生成失败")
            QMessageBox.critical(self, "备份清单失败", str(e))

    def do_restore(self):
        d = QFileDialog.getExistingDirectory(self, "选择备份目录", config.WORK)
        if not d:
            return
        try:
            m = backup.load_manifest(d)
            errs = backup.verify_backup(m, d)
            if errs:
                raise backup.BackupError("；".join(errs))
        except Exception as e:
            QMessageBox.critical(self, "备份无效", str(e))
            return
        meta = self._meta(required=False)
        raw_restore = meta is None
        if raw_restore:
            meta = {"model": m.model, "platform": m.platform,
                    "sector_size": m.sector_size, "total_sectors": m.total_sectors,
                    "disk_size": m.disk_size, "disk_guid": m.disk_guid}
            if QMessageBox.warning(
                    self, "无法读取当前 GPT",
                    "当前设备 GPT 不可读，将按备份 manifest 恢复：\n\n"
                    "容量：%d 字节\n扇区：%d\n磁盘 GUID：%s\n\n"
                    "恢复时将使用 manifest 的绝对 LBA 写入，不依赖 GPT。\n"
                    "确定继续？" % (m.disk_size, m.sector_size, m.disk_guid),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        groups = [g for g in ("critical", "boot", "system", "modem", "userdata", "other")
                  if any(i.group == g for i in m.items)]
        if not groups:
            return
        choice, ok = QInputDialog.getItem(self, "恢复范围", "选择恢复分组",
                                          ["全部"] + groups, 0, False)
        if not ok:
            return
        try:
            if choice == "全部":
                plan = backup.restore_plan(m, d, target=meta)
            else:
                plan = backup.restore_plan(m, d, groups=[choice], target=meta)
        except Exception as e:
            QMessageBox.critical(self, "拒绝恢复", str(e))
            return
        if QMessageBox.warning(self, "确认恢复",
                               "将写入 %d 个分区到当前设备。\n\n确定继续？" % len(plan),
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        steps = []
        for x in plan:
            if raw_restore:
                if not x.get("start_lba"):
                    QMessageBox.critical(self, "无法恢复", "备份缺少起始 LBA：" + x["name"])
                    return
                steps.append(["wo", hex(int(x["start_lba"]) * int(meta["sector_size"])),
                              hex(int(x["size"])), x["file"]])
            else:
                steps.append(["w", x["name"], x["file"]])
        self.status.setText("正在恢复 %d 个分区…" % len(plan))
        self.progress.setVisible(True)
        self.progress.setRange(0, len(plan))
        self.progress.setValue(0)
        self.progress.setFormat("恢复 0/%d" % len(plan))
        self.main.run_sequence(steps, "恢复分区", self._restore_done, 14400,
                               on_step=self._restore_step)

    def _restore_step(self, index, total, args):
        name = args[1] if len(args) > 1 else ""
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.progress.setFormat("恢复 %d/%d · %s" % (index + 1, total, name))
        self.status.setText("正在恢复 %d/%d：%s" % (index + 1, total, name))

    def _restore_done(self, results):
        self.progress.setVisible(False)
        if results and all(r[0] == 0 and not r[2] for r in results):
            self.status.setText("恢复完成")
            self.main._log("[恢复] 分区写入完成")
        else:
            self.status.setText("恢复失败")
            self.main._log("[恢复] 至少一个分区写入失败")


def _hsize(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u == "B" else "%.2f %s") % (n, u)
        n /= 1024
