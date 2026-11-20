# -*- coding: utf-8 -*-
"""V2 资源包/机型选择对话框。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
                               QFormLayout, QCheckBox, QRadioButton, QDialogButtonBox,
                               QMessageBox, QSplitter, QWidget)

from core import resourcepack
from . import theme


class PackDialog(QDialog):
    def __init__(self, pack_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择设备 / 资源 / 配置")
        self.resize(900, 620)
        self.pack = None
        self.model = None
        self.patch_da = True
        self.carbonara = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        top = QHBoxLayout()
        self.path = QLineEdit(pack_path or "")
        self.path.setReadOnly(True)
        b = QPushButton("选择资源包")
        b.clicked.connect(self.browse)
        top.addWidget(QLabel("资源包路径"))
        top.addWidget(self.path, 1)
        top.addWidget(b)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["机型", "说明"])
        self.tree.setColumnWidth(0, 220)
        self.tree.itemClicked.connect(self._clicked)
        split.addWidget(self.tree)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.info = QLabel("请选择资源包")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color:%s;" % theme.MUTED)
        rv.addWidget(self.info)
        form = QFormLayout()
        self.model_label = QLabel("—")
        self.model_label.setWordWrap(True)
        self.pre_label = QLabel("—")
        self.pre_label.setWordWrap(True)
        self.da_label = QLabel("—")
        self.da_label.setWordWrap(True)
        self.desc = QLabel("—")
        self.desc.setWordWrap(True)
        form.addRow("选择机型", self.model_label)
        form.addRow("Preloader", self.pre_label)
        form.addRow("DA", self.da_label)
        form.addRow("说明", self.desc)
        rv.addLayout(form)
        self.integrated = QRadioButton("使用整合 DA")
        self.integrated.setChecked(True)
        rv.addWidget(self.integrated)
        self.patch = QCheckBox("是否 Patch DA?")
        self.patch.setChecked(True)
        rv.addWidget(self.patch)
        self.carb = QCheckBox("是否使用 Carbonara?")
        self.carb.setChecked(True)
        rv.addWidget(self.carb)
        rv.addStretch(1)
        split.addWidget(right)
        split.setSizes([520, 340])
        lay.addWidget(split, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if pack_path:
            self.load(pack_path)

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择资源包", os.path.dirname(self.path.text() or "."),
                                           "资源包 (*.zip);;所有文件 (*)")
        if p:
            self.load(p)

    def load(self, path):
        try:
            self.pack = resourcepack.load(path)
        except Exception as e:
            QMessageBox.critical(self, "资源包读取失败", "%s\n\n%s" % (path, e))
            return
        self.path.setText(path)
        self.tree.clear()
        self.info.setText("发布者：%s    版本：%s\n%s" %
                          (self.pack.publisher, self.pack.version, self.pack.tip))
        for brand, series in self.pack.brands:
            bitem = QTreeWidgetItem([brand, ""])
            self.tree.addTopLevelItem(bitem)
            for sname, models in series:
                sitem = QTreeWidgetItem([sname, ""])
                bitem.addChild(sitem)
                for m in models:
                    mi = QTreeWidgetItem([m.name, m.description])
                    mi.setData(0, Qt.UserRole, m)
                    sitem.addChild(mi)
        self.tree.expandAll()

    def _clicked(self, item, _col):
        m = item.data(0, Qt.UserRole)
        if not m:
            return
        self.model = m
        self.model_label.setText("%s / %s / %s" % (m.brand, m.series, m.name))
        self.pre_label.setText(m.preloader or "可选（使用自动导出）")
        self.da_label.setText("%s\nDA1 地址 0x%x / DA2 地址 0x%x" %
                              (m.da1 or "工具内置", m.da1_addr, m.da2_addr))
        self.desc.setText(m.description or "—")

    def accept(self):
        if self.model is None:
            QMessageBox.information(self, "没有选择", "请先选择机型。")
            return
        self.patch_da = self.patch.isChecked()
        self.carbonara = self.carb.isChecked()
        super().accept()
