# -*- coding: utf-8 -*-
"""V2 自定义地址添加窗口。"""
import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QPushButton, QFileDialog, QDialogButtonBox,
                               QMessageBox)

from . import theme


class RawDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自定义地址")
        self.resize(500, 300)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("单元"))
        self.unit = QComboBox()
        self.unit.addItems(["USER", "BOOT_1", "BOOT_2"])
        row.addWidget(self.unit, 1)
        v.addLayout(row)
        for label, attr, default in (("起始地址", "start", "0x0"),
                                     ("大小", "size", "0x100000")):
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            e = QLineEdit(default)
            setattr(self, attr, e)
            r.addWidget(e, 1)
            v.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("文件"))
        self.file = QLineEdit()
        r.addWidget(self.file, 1)
        b = QPushButton("浏览")
        b.clicked.connect(self.browse)
        r.addWidget(b)
        v.addLayout(r)
        self.mode = QComboBox()
        self.mode.addItems(["读取到文件", "从文件写入"])
        v.addWidget(self.mode)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def browse(self):
        if self.mode.currentIndex() == 0:
            p, _ = QFileDialog.getSaveFileName(self, "保存文件")
        else:
            p, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if p:
            self.file.setText(p)

    def value(self):
        return {"unit": self.unit.currentText(), "start": self.start.text().strip(),
                "size": self.size.text().strip(), "write": self.mode.currentIndex() == 1,
                "file": self.file.text().strip()}
