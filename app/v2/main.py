# -*- coding: utf-8 -*-
"""MTK9400 V2：专业 MTK 深度刷机界面。

只保留连接底层（COM / WinUSB / Preloader / DA），业务操作按刷机匣
MTK 深度刷机流程重新实现。
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QFrame, QStackedWidget, QScrollArea,
    QCheckBox, QRadioButton, QFileDialog, QMessageBox, QDialog, QPlainTextEdit,
    QProgressBar, QDialogButtonBox, QListWidget, QListWidgetItem, QMenu, QSizeGrip,
    QInputDialog,
)

from core import config, toolfiles, session as logparse, resourcepack, scatter
from core import preloader, factory, rawaddr, parts
from core.mtk import MtkSession
from . import theme, gpt
from .packdialog import PackDialog
from .rawdialog import RawDialog
from .backup_page import BackupPage
from .flash_page import DeepFlashPage


def _hsize(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u == "B" else "%.2f %s") % (n, u)
        n /= 1024


ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _clean_log(s):
    return ANSI_RE.sub("", str(s or ""))


def _short(s, n=48):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1] + "…"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTK9400 专业深刷工具")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self.pack = None
        self.model = None
        self.scatter = None
        self.image_dir = ""
        self.session = None
        self.parser = None
        self.busy = False
        self._session_cb = None
        self._seq = None
        self._seq_index = 0
        self._seq_results = []
        self._seq_done = None
        self._seq_on_step = None
        self._seq_labels = None
        self._cur_text = []
        self.rows = []
        self.custom_rows = []
        self._view_rows = []
        self.port = ""
        self._build()
        self._load_ports()
        self.cmb_port.currentIndexChanged.connect(self._port_changed)
        self._load_state()
        self.port_timer = QTimer(self)
        self.port_timer.timeout.connect(self._auto_ports)
        self.port_timer.start(1000)
        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(200)
        self.watch_timer.timeout.connect(self._watch_tick)
        self._watch_deadline = 0
        self._watch_base = set()
        theme.set_mode(theme.MODE)

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左侧导航
        nav = QFrame()
        nav.setObjectName("Panel")
        nav.setFixedWidth(176)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(10, 12, 10, 10)
        nv.setSpacing(3)
        title = QLabel("MTK9400")
        title.setFont(QFont(theme.FONT_UI if hasattr(theme, "FONT_UI") else "Microsoft YaHei UI", 14, QFont.Bold))
        nv.addWidget(title)
        sub = QLabel("MTK 深度刷机")
        sub.setStyleSheet("color:%s;font-size:10px;" % theme.MUTED)
        nv.addWidget(sub)
        nv.addSpacing(10)
        self.nav_buttons = []
        for i, text in enumerate(("首页", "Fastboot", "QC / 高通", "MTK / 联发科",
                                  "深度刷机", "备份 / 恢复", "设置", "关于")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setStyleSheet("QPushButton{text-align:left;padding-left:12px;}"
                            "QPushButton:checked{background:%s;color:%s;border-left:3px solid %s;}"
                            % (theme.ALT, theme.ACCENT, theme.ACCENT))
            b.clicked.connect(lambda _=False, idx=i: self.show_page(idx))
            nv.addWidget(b)
            self.nav_buttons.append(b)
        nv.addStretch(1)
        ver = QLabel("v2.0 · MTK")
        ver.setStyleSheet("color:%s;font-size:10px;" % theme.FAINT)
        nv.addWidget(ver)
        outer.addWidget(nav)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.mtk_page = self._build_mtk()
        self.stack.addWidget(self.mtk_page)
        self.fb_page = self._build_fastboot()
        self.stack.addWidget(self.fb_page)
        p = QLabel("QC / 高通页面尚未接入")
        p.setAlignment(Qt.AlignCenter)
        p.setStyleSheet("color:%s;font-size:16px;" % theme.MUTED)
        self.stack.addWidget(p)
        self.settings_page = QWidget()
        self._build_settings(self.settings_page)
        self.stack.addWidget(self.settings_page)
        p = QLabel("MTK9400 专业深刷工具")
        p.setAlignment(Qt.AlignCenter)
        p.setStyleSheet("color:%s;font-size:16px;" % theme.MUTED)
        self.stack.addWidget(p)
        self.deep_page = DeepFlashPage(self)
        self.stack.addWidget(self.deep_page)
        self.backup_page = BackupPage(self)
        self.stack.addWidget(self.backup_page)
        self.show_page(3)

    def _build_mtk(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 8, 10, 6)
        lay.setSpacing(6)

        # 顶部资源/端口条
        bar = QFrame()
        bar.setObjectName("Panel")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 10, 6)
        bl.setSpacing(8)
        self.btn_pack = QPushButton("选择设备 / 资源 / 配置")
        self.btn_pack.clicked.connect(self.choose_pack)
        self.lbl_pack = QLabel("资源包未选择")
        self.lbl_pack.setStyleSheet("color:%s;" % theme.MUTED)
        self.lbl_model = QLabel("通用")
        self.lbl_model.setStyleSheet("font-weight:600;")
        bl.addWidget(self.btn_pack)
        bl.addWidget(self.lbl_pack)
        bl.addSpacing(10)
        bl.addWidget(QLabel("已选择:"))
        bl.addWidget(self.lbl_model)
        bl.addStretch(1)
        bl.addWidget(QLabel("连接:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("自动（优先 COM）", "auto")
        self.cmb_mode.addItem("仅 WinUSB", "usb")
        self.cmb_mode.addItem("仅 COM", "com")
        self.cmb_mode.setFixedWidth(110)
        self.cmb_mode.currentIndexChanged.connect(self._mode_changed)
        bl.addWidget(self.cmb_mode)
        bl.addWidget(QLabel("捕获端口:"))
        self.cmb_port = QComboBox()
        self.cmb_port.setMinimumWidth(150)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedWidth(48)
        self.btn_refresh.clicked.connect(self._load_ports)
        bl.addWidget(self.cmb_port)
        bl.addWidget(self.btn_refresh)
        lay.addWidget(bar)

        # 分区来源
        mode = QFrame()
        mode.setObjectName("Panel")
        ml = QHBoxLayout(mode)
        ml.setContentsMargins(10, 5, 10, 5)
        ml.setSpacing(6)
        self.rb_scatter = QRadioButton("使用 Scatter")
        self.rb_scatter.setChecked(True)
        self.btn_scatter = QPushButton("选择 Scatter")
        self.btn_scatter.clicked.connect(self.load_scatter)
        self.btn_imgdir = QPushButton("选择镜像目录")
        self.btn_imgdir.clicked.connect(self.choose_image_dir)
        self.rb_gpt = QRadioButton("使用设备分区表")
        self.btn_gpt = QPushButton("读取设备分区表")
        self.btn_gpt.clicked.connect(self.read_info)
        self.rb_custom = QRadioButton("使用自定义地址")
        self.btn_add_addr = QPushButton("添加")
        self.btn_del_addr = QPushButton("删除")
        self.btn_add_addr.clicked.connect(self.add_custom)
        self.btn_del_addr.clicked.connect(self.del_custom)
        for w in (self.rb_scatter, self.btn_scatter, self.btn_imgdir,
                  self.rb_gpt, self.btn_gpt, self.rb_custom,
                  self.btn_add_addr, self.btn_del_addr):
            ml.addWidget(w)
        ml.addStretch(1)
        lay.addWidget(mode)

        # 搜索/全选
        filt = QHBoxLayout()
        filt.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索分区名 / 标签 / 文件…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_rows)
        self.lbl_selected = QLabel("已选择: 0")
        self.lbl_selected.setStyleSheet("color:%s;" % theme.MUTED)
        self.chk_all = QCheckBox("全选")
        self.chk_all.stateChanged.connect(self._select_all)
        self.chk_user = QCheckBox("用户数据分区")
        self.chk_user.stateChanged.connect(self._filter_rows)
        filt.addWidget(QLabel("搜索:"))
        filt.addWidget(self.search, 1)
        filt.addWidget(self.lbl_selected)
        filt.addWidget(self.chk_all)
        filt.addWidget(self.chk_user)
        lay.addLayout(filt)

        # 主体：表 + 右侧
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["单元", "#", "标签", "起始", "大小", "文件"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        split.addWidget(self.table)

        self.right = QScrollArea()
        self.right.setWidgetResizable(True)
        self.right.setFrameShape(QFrame.NoFrame)
        right_host = QWidget()
        self.rv = QVBoxLayout(right_host)
        self.rv.setContentsMargins(8, 0, 0, 0)
        self.rv.setSpacing(5)
        self._build_basic(self.rv)
        self._build_more(self.rv)
        self._build_advanced(self.rv)
        self._build_gpt_section(self.rv)
        self.rv.addStretch(1)
        self.right.setWidget(right_host)
        self.right.setFixedWidth(320)
        split.addWidget(self.right)
        split.setSizes([1000, 286])
        lay.addWidget(split, 1)

        # 底部日志/进度
        bottom = QFrame()
        bottom.setObjectName("Panel")
        bl2 = QVBoxLayout(bottom)
        bl2.setContentsMargins(8, 5, 8, 5)
        bl2.setSpacing(4)
        logbar = QHBoxLayout()
        self.chk_log = QCheckBox("日志")
        self.chk_log.setChecked(True)
        self.chk_log.stateChanged.connect(self._toggle_log)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:%s;" % theme.MUTED)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_command)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(340)
        self.progress.setTextVisible(True)
        logbar.addWidget(self.chk_log)
        logbar.addWidget(self.status, 1)
        logbar.addWidget(self.btn_stop)
        logbar.addWidget(self.progress)
        bl2.addLayout(logbar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(8000)
        self.log.setFixedHeight(150)
        bl2.addWidget(self.log)
        lay.addWidget(bottom)
        return page

    def _section(self, parent, title):
        box = QFrame()
        box.setObjectName("Panel")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        h = QPushButton(title)
        h.setCheckable(True)
        h.setChecked(True)
        h.setStyleSheet("text-align:left; font-weight:600; border:none; background:transparent;")
        v.addWidget(h)
        body = QWidget()
        bv = QGridLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(4)
        v.addWidget(body)
        h.toggled.connect(body.setVisible)
        parent.addWidget(box)
        return bv

    def _btn(self, parent, text, cb, row, col=0, span=2, danger=False, primary=False):
        b = QPushButton(text)
        if danger:
            b.setObjectName("danger")
        if primary:
            b.setObjectName("primary")
        b.clicked.connect(cb)
        parent.addWidget(b, row, col, 1, span)
        return b

    def _build_basic(self, parent):
        g = self._section(parent, "基础操作")
        self._btn(g, "读信息 / 读分区表", self.read_info, 0, primary=True)
        self._btn(g, "刷入（已选）", self.write_selected, 1, danger=True)
        self._btn(g, "刷入指定目录全部文件", self.write_dir, 2, danger=True)
        self._btn(g, "回读（已选）", self.read_selected, 3)
        g.addWidget(self._check_row("导出 Preloader", "生成 Scatter"), 4, 0, 1, 2)
        row = QHBoxLayout()
        row.addWidget(QLabel("擦除"))
        self.cmb_erase = QComboBox()
        self.cmb_erase.addItems(["快速擦除", "完整擦除"])
        row.addWidget(self.cmb_erase, 1)
        b = QPushButton("执行")
        b.clicked.connect(self.erase_selected)
        row.addWidget(b)
        wrap = QWidget()
        wrap.setLayout(row)
        g.addWidget(wrap, 5, 0, 1, 2)
        self._btn(g, "恢复出厂设置", self.factory_reset, 6, danger=True)
        self._menu_button(g, "重启", [
            ("系统", lambda: self._reboot("reset")),
            ("Recovery", lambda: self._fastboot("reboot recovery", "重启到 Recovery")),
            ("Brom(Crash)", lambda: self._reboot("crash")),
            ("FastbootD-方案1", lambda: self._fastboot("reboot fastboot", "重启到 FastbootD")),
            ("FastbootD-方案2", lambda: self._fastboot("reboot fastboot", "重启到 FastbootD")),
        ], 7, 0)

    def _check_row(self, a, b):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        self.chk_pre = QCheckBox(a)
        self.chk_scatter = QCheckBox(b)
        h.addWidget(self.chk_pre)
        h.addWidget(self.chk_scatter)
        return w

    def _menu_button(self, parent, text, actions, row, col, danger=False):
        b = QPushButton(text)
        if danger:
            b.setObjectName("danger")
        menu = QMenu(b)
        for label, cb in actions:
            act = menu.addAction(label)
            act.triggered.connect(cb)
        b.setMenu(menu)
        parent.addWidget(b, row, col)
        return b

    def _build_more(self, parent):
        g = self._section(parent, "更多功能")
        self._menu_button(g, "BL 锁：解锁 / 上锁", [
            ("解锁", lambda: self._seccfg("unlock")),
            ("上锁", lambda: self._seccfg("lock")),
        ], 0, 0, danger=True)
        self._menu_button(g, "槽位功能：查看 / A / B", [
            ("查看当前槽位", self._slot_view),
            ("设为 A 槽位", lambda: self._slot_set("a")),
            ("设为 B 槽位", lambda: self._slot_set("b")),
        ], 0, 1)
        self._menu_button(g, "OEM 解锁开关", [
            ("打开", lambda: self._oem(True)),
            ("关闭", lambda: self._oem(False)),
        ], 1, 0)
        self._menu_button(g, "Vbmeta 修补", [
            ("Locked", lambda: self._vbmeta(0)),
            ("Disable Verity", lambda: self._vbmeta(1)),
            ("Disable Verification", lambda: self._vbmeta(2)),
            ("Disable Verity + Verification", lambda: self._vbmeta(3)),
        ], 1, 1)
        self._menu_button(g, "绕过授权 Bypass", [
            ("说明 / 自动 Bypass", self._bypass_info),
        ], 2, 0)
        b = QPushButton("移除谷歌锁")
        b.clicked.connect(self._erase_frp)
        b.setObjectName("danger")
        g.addWidget(b, 2, 1)

    def _build_advanced(self, parent):
        g = self._section(parent, "高级功能（不懂勿用）")
        self._menu_button(g, "Preloader 操作", [
            ("读取", lambda: self._preloader_op("r")),
            ("写入", lambda: self._preloader_op("w")),
            ("擦除", lambda: self._preloader_op("e")),
        ], 0, 0, danger=True)
        self._menu_button(g, "RPMB 操作", [
            ("读取", lambda: self._rpmb_op("r")),
            ("写入", lambda: self._rpmb_op("w")),
            ("擦除", lambda: self._rpmb_op("e")),
        ], 0, 1, danger=True)
        b = QPushButton("导出 Brom")
        b.clicked.connect(self._dump_brom)
        g.addWidget(b, 1, 0)
        b = QPushButton("生成密钥")
        b.clicked.connect(self._gen_keys)
        g.addWidget(b, 1, 1)

    def _build_fastboot(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 10, 12, 10)
        v.addWidget(QLabel("Fastboot 命令"))
        row = QHBoxLayout()
        self.fb_cmd = QLineEdit("devices")
        self.fb_cmd.setFont(QFont("Consolas", 10))
        b = QPushButton("执行")
        b.clicked.connect(self.fb_exec)
        row.addWidget(self.fb_cmd, 1)
        row.addWidget(b)
        v.addLayout(row)
        quick = QHBoxLayout()
        for text, cmd in (("设备列表", "devices"), ("重启", "reboot"),
                          ("重启到 Fastboot", "reboot fastboot")):
            q = QPushButton(text)
            q.clicked.connect(lambda _=False, c=cmd: self.fb_exec(c))
            quick.addWidget(q)
        quick.addStretch(1)
        v.addLayout(quick)
        self.fb_out = QPlainTextEdit()
        self.fb_out.setReadOnly(True)
        self.fb_out.setFont(QFont("Consolas", 10))
        v.addWidget(self.fb_out, 1)
        return page

    def fb_exec(self, command=None):
        from core.fastboot import fastboot_run
        cmd = command if command is not None else self.fb_cmd.text().strip()
        if not cmd:
            return
        self.progress_begin("Fastboot · " + cmd)
        try:
            rc, out = fastboot_run(cmd.split(), timeout=60)
            self.fb_out.appendPlainText("$ fastboot %s\n[rc=%s]\n%s" % (cmd, rc, out))
            self.progress_end("Fastboot 完成" if rc == 0 else "Fastboot 失败",
                              failed=rc != 0)
        except Exception as e:
            self.progress_end("Fastboot 失败", failed=True)
            self.fb_out.appendPlainText("$ fastboot %s\n%s" % (cmd, e))

    def _build_gpt_section(self, parent):
        g = self._section(parent, "GPT 分区表（高风险）")
        self._btn(g, "备份 GPT", self.gpt_backup, 0)
        self._btn(g, "校验 GPT", self.gpt_verify, 1)
        self._btn(g, "恢复 GPT / 刷写分区表", self.gpt_restore, 2, danger=True)
        self._btn(g, "从 Scatter 重建 GPT", self.gpt_rebuild, 3, danger=True)
        note = QLabel("只允许同容量、同扇区、同磁盘 GUID 的备份；写入顺序为备份 GPT → 主 GPT。")
        note.setWordWrap(True)
        note.setStyleSheet("color:%s;font-size:10px;" % theme.MUTED)
        g.addWidget(note, 4, 0, 1, 2)

    def _build_settings(self, page):
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 20)
        v.addWidget(QLabel("界面设置"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("浅色", "light")
        self.cmb_theme.addItem("深色", "dark")
        try:
            from core import uiprefs
            prefs = uiprefs.load()
            self.cmb_theme.setCurrentIndex(1 if prefs.get("theme") == "dark" else 0)
        except Exception:
            pass
        v.addWidget(self.cmb_theme)
        b = QPushButton("保存并重新打开")
        b.clicked.connect(self.save_theme)
        v.addWidget(b)
        v.addStretch(1)

    # ---------------------------------------------------------------- helpers
    def show_page(self, idx):
        # 0 首页和 3 MTK 共用同一个工作页；4 设置；5 关于。
        page = {0: 0, 1: 1, 2: 2, 3: 0, 4: 5, 5: 6, 6: 3, 7: 4}.get(idx, 0)
        self.stack.setCurrentIndex(page)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == idx)

    def _not_ready(self, name):
        QMessageBox.information(self, "暂未接入", "%s 需要底层命令接入后才能使用。\n当前版本先完成界面、资源包和基础分区操作。" % name)

    def _ports_now(self):
        out = []
        try:
            from serial.tools import list_ports
            for p in list_ports.comports():
                out.append((p.device, p.description or p.device))
        except Exception:
            pass
        return out

    def _auto_ports(self):
        """检查新端口；是否自动占用由连接模式决定。"""
        ports = self._ports_now()
        names = [d for d, _x in ports]
        if getattr(self, "_last_port_names", None) == names:
            return
        old = self.cmb_port.currentData() or ""
        self._last_port_names = names
        mode = self.cmb_mode.currentData() if hasattr(self, "cmb_mode") else "auto"
        if mode == "usb":
            self._fill_port_combo(ports, "")
            return
        if mode == "com" and not names:
            self._fill_port_combo([], "")
            return
        if names and (not old or old not in names):
            # 优先 MediaTek/PreLoader，其次任意一个新端口。
            pick = None
            for d, desc in ports:
                if "mediatek" in desc.lower() or "preloader" in desc.lower():
                    pick = d
                    break
            if pick is None:
                pick = names[0]
            old = pick
            self._log("[端口] 检测到新端口：%s" % pick)
        self._fill_port_combo(ports, old)

    def _mode_changed(self):
        if not hasattr(self, "cmb_mode") or not hasattr(self, "cmb_port"):
            return
        self._load_ports()

    def _fill_port_combo(self, ports, selected=""):
        self.cmb_port.blockSignals(True)
        self.cmb_port.clear()
        self.cmb_port.addItem("WinUSB（不使用 COM）", "")
        found = False
        for dev, desc in ports:
            self.cmb_port.addItem("%s  %s" % (dev, desc), dev)
            if selected and dev == selected:
                found = True
        if selected and not found:
            # 旧版逻辑：即使当前没枚举到，也允许用配置里的 COM 先启动
            # mtkclient，让它在 Preloader 出现后自己完成握手。
            self.cmb_port.addItem("%s（未检测到）" % selected, selected)
        if selected:
            for i in range(self.cmb_port.count()):
                if self.cmb_port.itemData(i) == selected:
                    self.cmb_port.setCurrentIndex(i)
                    break
        self.cmb_port.blockSignals(False)
        self._port_changed()

    def _load_ports(self):
        old = self.cmb_port.currentData() or ""
        ports = self._ports_now()
        names = [d for d, _x in ports]
        self._last_port_names = names
        if not hasattr(self, "cmb_mode") or self.cmb_mode.currentData() == "usb":
            self._fill_port_combo(ports, "")
            return
        if self.cmb_mode.currentData() == "com":
            if old not in names:
                old = ""
            self._fill_port_combo(ports, old)
            return
        if (not old or old not in names) and ports:
            old = names[0]
        self._fill_port_combo(ports, old)

    def _port_changed(self):
        self.port = self.cmb_port.currentData() or ""
        self.prefer_usb = not bool(self.port)

    def _load_state(self):
        p = os.path.join(config.WORK, "v2_state.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            pack_path = d.get("pack", "")
            model_name = d.get("model", "")
            mode = d.get("mode", "auto")
            if hasattr(self, "cmb_mode") and mode in ("auto", "usb", "com"):
                idx = self.cmb_mode.findData(mode)
                if idx >= 0:
                    self.cmb_mode.blockSignals(True)
                    self.cmb_mode.setCurrentIndex(idx)
                    self.cmb_mode.blockSignals(False)
            if pack_path and os.path.isfile(pack_path):
                self.pack = resourcepack.load(pack_path)
                for m in self.pack.models:
                    if m.name == model_name:
                        self.model = m
                        self.pack.extract(m)
                        self.lbl_pack.setText(os.path.basename(pack_path))
                        self.lbl_model.setText(m.name)
                        break
        except Exception:
            pass
        try:
            self._load_ports()
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(os.path.join(config.WORK, "v2_state.json"), "w", encoding="utf-8") as f:
                json.dump({"port": self.port,
                           "mode": self.cmb_mode.currentData() if hasattr(self, "cmb_mode") else "auto",
                           "model": self.model.name if self.model else "",
                           "pack": self.pack.path if self.pack else ""}, f, ensure_ascii=False)
        except Exception:
            pass

    def choose_pack(self):
        d = PackDialog(self.pack.path if self.pack else "", self)
        if d.exec() != QDialog.Accepted:
            return
        self.pack, self.model = d.pack, d.model
        try:
            self.pack.extract(self.model)
        except Exception as e:
            QMessageBox.critical(self, "资源包文件解压失败", str(e))
            return
        self.lbl_pack.setText(os.path.basename(self.pack.path))
        self.lbl_model.setText(self.model.name)
        self._log("[资源包] %s / %s / %s" % (self.model.brand, self.model.series, self.model.name))
        self._save_state()

    def load_scatter(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 Scatter", config.WORK,
                                           "Scatter (*.txt);;所有文件 (*)")
        if not p:
            return
        try:
            self.scatter = scatter.load(p)
        except Exception as e:
            QMessageBox.critical(self, "Scatter 读取失败", str(e))
            return
        self.scatter.path = p
        self.rb_scatter.setChecked(True)
        self._fill_scatter()
        self._log("[Scatter] %s，%d 个分区" % (p, len(self.scatter.entries)))

    def choose_image_dir(self):
        p = QFileDialog.getExistingDirectory(self, "选择镜像目录", config.WORK)
        if p:
            self.image_dir = p
            self._log("[镜像目录] %s" % p)
            if self.scatter:
                for r in self.rows:
                    for e in self.scatter.entries:
                        if e.name == r["name"]:
                            r["file"] = e.file_name
                            break
                self._render_rows()

    def _fill_scatter(self):
        self.rows = []
        if not self.scatter:
            return
        for i, e in enumerate(self.scatter.entries):
            self.rows.append({"unit": "USER", "idx": i, "name": e.name,
                              "start": e.start, "size": e.size, "file": e.file_name})
        self._render_rows()

    def _fill_gpt(self, parser):
        self.rows = []
        for i, n in enumerate(parser.partitions):
            m = parser.partition_meta.get(n, {})
            self.rows.append({"unit": "USER", "idx": i, "name": n,
                              "start": int(m.get("offset", 0) or 0),
                              "size": int(parser.partition_sizes.get(n, 0) or 0),
                              "file": ""})
        self._render_rows()

    def _render_rows(self):
        q = self.search.text().strip().lower()
        only_user = self.chk_user.isChecked()
        self.table.setRowCount(0)
        self._view_rows = []
        shown = 0
        for r in list(self.custom_rows) + list(self.rows):
            if only_user and r["name"] not in ("userdata",):
                continue
            if q and q not in ("%s %s %s" % (r["name"], r["file"], r["unit"])).lower():
                continue
            self._view_rows.append(r)
            self.table.insertRow(shown)
            vals = [r["unit"], str(r["idx"]), r["name"],
                    "0x%x" % r["start"] if r["start"] else "",
                    _hsize(r["size"]), r["file"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 2:
                    it.setFont(QFont("Consolas", 9))
                self.table.setItem(shown, c, it)
            shown += 1
        self._sel_changed()

    def add_custom(self):
        d = RawDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        v = d.value()
        try:
            start = int(v["start"], 16) if v["start"].lower().startswith("0x") else int(v["start"])
            size = int(v["size"], 16) if v["size"].lower().startswith("0x") else int(v["size"])
        except Exception:
            QMessageBox.critical(self, "参数错误", "起始地址和大小必须是十六进制数")
            return
        row = {"unit": v["unit"], "idx": len(self.custom_rows), "name": "RAW",
               "start": start, "size": size, "file": v["file"], "raw": True,
               "write": bool(v["write"])}
        self.custom_rows.append(row)
        self.rb_custom.setChecked(True)
        self._render_rows()

    def del_custom(self):
        selected = [r for r in self.selected_items() if r.get("raw")]
        if not selected:
            return
        self.custom_rows = [r for r in self.custom_rows if r not in selected]
        self._render_rows()

    def _filter_rows(self, *_):
        self._render_rows()

    def _select_all(self, *_):
        if self.chk_all.isChecked():
            self.table.selectAll()
        else:
            self.table.clearSelection()

    def _sel_changed(self):
        n = len(self.table.selectionModel().selectedRows()) if self.table.selectionModel() else 0
        self.lbl_selected.setText("已选择: %d" % n)
        self._update_counts()

    def _update_counts(self):
        pass

    def selected_items(self):
        sm = self.table.selectionModel()
        if sm is None:
            return []
        out = []
        for idx in sm.selectedRows():
            if 0 <= idx.row() < len(self._view_rows):
                out.append(self._view_rows[idx.row()])
        return out

    def selected_names(self):
        return [r["name"] for r in self.selected_items()]

    # ---------------------------------------------------------------- session
    def _da_path(self):
        # 资源包里的 MT6991_DA1.bin 与已验证可连接的 OPLUS_DA_mt6991.bin
        # 内容不同；刷机匣会在运行时 Patch DA，我们不能直接假设它可用。
        # 当前机型优先使用已经验证过的 DA；资源包仍用于 Preloader/机型信息。
        if os.path.isfile(config.LOADER):
            return config.LOADER
        if self.model and self.model.local.get("da1"):
            return self.model.local["da1"]
        tf = toolfiles.load(config.WORK)
        return tf.get("da") or config.LOADER

    def _pre_path(self):
        if self.model and self.model.local.get("preloader"):
            return self.model.local["preloader"]
        tf = toolfiles.load(config.WORK)
        return tf.get("preloader") or ""

    def base_args(self):
        args = ["--skipmeid"]
        if self.port:
            args += ["--serialport", self.port]
        args += ["--loader", self._da_path()]
        pre = self._pre_path()
        if pre:
            args += ["--preloader", pre]
        auth = config.AUTH
        try:
            tf = toolfiles.load(config.WORK)
            if tf.get("auth"):
                auth = tf["auth"]
        except Exception:
            pass
        if os.path.isfile(auth):
            args += ["--auth", auth]
        return args

    def _ensure_session(self):
        if self.session is not None and self.session.isRunning():
            return True
        self.session = MtkSession(self.base_args(), parent=self)
        self.session.line.connect(self._on_line)
        self.session.done.connect(self._on_done)
        self.session.start()
        return True

    def _on_line(self, text):
        text = _clean_log(text)
        label = getattr(self, "_current_label", "")
        if "重启" in label:
            if "xread: Wrong length" in text:
                text = "[重启] 设备已断开，读取结束（正常）\n"
            elif "Error on sending reboot" in text:
                text = "[重启] 复位命令已发出，USB 断开（正常）\n"
            elif "USBError(32, 'Pipe error')" in text:
                text = "[重启] USB 已断开（正常）\n"
        self._cur_text.append(text)
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
        stage = " ".join(str(text).strip().split())
        if stage:
            stage = stage[-120:]
            self.status.setText((getattr(self, "_progress_label", "") + " · " + stage)
                               if getattr(self, "_progress_label", "") else stage)
            if self.progress.isVisible() and self.progress.maximum() == 0:
                self.progress.setFormat(stage[:60])
        try:
            with open(os.path.join(config.WORK, "v2_session.log"), "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def progress_begin(self, label, total=0, value=0):
        self._progress_label = label
        self.progress.setVisible(True)
        if total and total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(value)
            self.progress.setFormat("%s %d/%d" % (label, value, total))
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat(label)
        self.status.setText(label)
        self.status.setStyleSheet("color:%s;" % theme.MUTED)
        self.btn_stop.setEnabled(bool(self.busy or self.watch_timer.isActive()))

    def progress_end(self, text="完成", failed=False):
        self._progress_label = ""
        if failed:
            self.progress.setFormat("失败")
            self.progress.setVisible(True)
            self.status.setStyleSheet("color:%s;" % theme.RED)
        else:
            if self.progress.maximum() > 0:
                self.progress.setValue(self.progress.maximum())
                self.progress.setFormat("完成")
            self.progress.setVisible(self.progress.maximum() > 0)
        self.status.setText(text)
        if failed:
            self.progress.setVisible(True)
        self.btn_stop.setEnabled(False)

    def _on_done(self, rc, text, timed_out):
        self.busy = False
        label = getattr(self, "_current_label", "")
        clean = _clean_log(text)
        reset_ok = ("Reset command was sent" in clean or
                    "Error on sending reboot" in clean or
                    "xread: Wrong length" in clean)
        if self._seq is None:
            if reset_ok and "重启" in label:
                self.progress_end("重启命令已发送（设备断开属正常）")
            elif rc != 0 or timed_out:
                self.progress_end("操作失败", failed=True)
            else:
                self.progress_end("完成")
        if hasattr(self, "btn_stop"):
            self.btn_stop.setEnabled(False)
        cb = self._session_cb
        self._session_cb = None
        if cb:
            cb(rc, text, timed_out)

    def stop_command(self):
        if self.watch_timer.isActive():
            self.watch_timer.stop()
            self.progress.setVisible(False)
            self.btn_stop.setEnabled(False)
            self.status.setText("已停止等待端口")
            self.status.setStyleSheet("color:%s;" % theme.RED)
            return
        if not self.busy:
            return
        self._log("[停止] 用户请求停止当前操作")
        try:
            if self.session:
                self.session.stop()
                self.session.wait(2500)
        except Exception:
            pass
        self.busy = False
        self._session_cb = None
        self._seq = None
        self._seq_done = None
        self._seq_on_step = None
        self._seq_labels = None
        self.progress.setVisible(False)
        self.btn_stop.setEnabled(False)
        self.status.setText("已停止")
        self.status.setStyleSheet("color:%s;" % theme.RED)

    def run_command(self, args, label, cb=None, timeout=3600, progress=None):
        if self.busy:
            QMessageBox.information(self, "正在执行", "当前操作还没有完成，请先点停止。")
            return
        self.busy = True
        self._session_cb = cb
        self._current_label = label
        self._cur_text.clear()
        if progress:
            index, total, seq_label = progress
            self.progress_begin(seq_label, total, index)
            self.progress.setFormat("%s %d/%d" % (label, index + 1, total))
            self.status.setText(label)
        else:
            self.progress_begin(label)
        self.btn_stop.setEnabled(True)
        self._ensure_session()
        self.session.submit(args, timeout)
        self._log("[操作] " + label)

    def run_sequence(self, steps, label, done, timeout=600, on_step=None, labels=None):
        """顺序执行多个 mtkclient 命令，每一步完成后再启动下一步。"""
        if self.busy:
            QMessageBox.information(self, "正在执行", "当前操作还没有完成，请先点停止。")
            return
        self._seq = list(steps)
        self._seq_index = 0
        self._seq_results = []
        self._seq_done = done
        self._seq_label = label
        self._seq_timeout = timeout
        self._seq_on_step = on_step
        self._seq_labels = list(labels) if labels else None
        self._run_seq_next()

    def _run_seq_next(self):
        if self._seq is None:
            return
        if self._seq_index >= len(self._seq):
            done = self._seq_done
            results = self._seq_results
            total = len(self._seq)
            self._seq = None
            self._seq_done = None
            self._seq_on_step = None
            self._seq_labels = None
            self.progress_end("完成（%d/%d）" % (total, total))
            if done:
                done(results)
            return
        args = self._seq[self._seq_index]
        step_label = ""
        if self._seq_labels and self._seq_index < len(self._seq_labels):
            step_label = " · " + str(self._seq_labels[self._seq_index])
        elif len(args) > 1:
            step_label = " · " + str(args[1])
        label = "%s %d/%d%s" % (self._seq_label, self._seq_index + 1,
                                len(self._seq), step_label)
        if self._seq_on_step:
            try:
                self._seq_on_step(self._seq_index, len(self._seq), args)
            except Exception:
                pass
        self.run_command(args, label, self._seq_step_done, self._seq_timeout,
                         progress=(self._seq_index, len(self._seq), self._seq_label))

    def _seq_step_done(self, rc, text, timed_out):
        if self._seq is None:
            return
        self._seq_results.append((rc, text, timed_out))
        if rc != 0 or timed_out:
            done = self._seq_done
            self._seq = None
            self._seq_done = None
            self._seq_on_step = None
            self._seq_labels = None
            self.status.setText("操作失败，已中止")
            self.status.setStyleSheet("color:%s;" % theme.RED)
            self.progress_end("操作失败", failed=True)
            if done:
                done(self._seq_results)
            return
        self._seq_index += 1
        self._run_seq_next()

    def _log(self, text):
        text = _clean_log(text)
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        try:
            with open(os.path.join(config.WORK, "v2_session.log"), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    # ---------------------------------------------------------------- actions
    def read_info(self):
        if self.busy:
            QMessageBox.information(self, "正在执行", "当前操作还没有完成，请先点停止。")
            return
        self._load_ports()
        ports = self._ports_now()
        names = [d for d, _x in ports]
        mode = self.cmb_mode.currentData() if hasattr(self, "cmb_mode") else "auto"
        if mode == "usb":
            self.port = ""
            self._log("[连接] 仅 WinUSB，不使用 COM")
            if any("mediatek" in (desc or "").lower() or "preloader" in (desc or "").lower()
                   for _d, desc in ports):
                QMessageBox.warning(
                    self, "WinUSB / VCOM",
                    "当前系统里存在 MediaTek VCOM/COM 设备。\n"
                    "如果该设备使用 usbser 驱动，WinUSB 无法同时占用同一接口。\n"
                    "要用 WinUSB，需要先用 Zadig 把 Preloader 接口替换为 WinUSB；"
                    "否则请选择“自动（优先 COM）”或“仅 COM”。")
            self._do_read_info()
            return
        cur = self.cmb_port.currentData() or ""
        if mode == "com":
            if not cur:
                QMessageBox.information(self, "没有 COM", "当前模式为仅 COM，但没有可用的 COM 端口。")
                return
            self._fill_port_combo(ports, cur)
            self._do_read_info()
            return
        if cur:
            self._fill_port_combo(ports, cur)
            self._do_read_info()
            return
        # 自动模式没有 COM：使用 WinUSB
        self.port = ""
        self._do_read_info()

    def _start_port_watch(self):
        self._watch_base = set(d for d, _x in self._ports_now())
        self._watch_deadline = time.time() + 30
        self._log("[端口] 等待手机进入 Preloader，检测到任何新 COM 会立即连接")
        self.status.setText("等待手机进入 Preloader · 检测新端口")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.btn_stop.setEnabled(True)
        self.watch_timer.start()

    def _watch_tick(self):
        if time.time() > self._watch_deadline:
            self.watch_timer.stop()
            self.progress.setVisible(False)
            self.btn_stop.setEnabled(False)
            self.status.setText("未检测到新 COM 端口")
            self.status.setStyleSheet("color:%s;" % theme.RED)
            self._log("[端口] 30 秒内没有新端口；请确认设备管理器出现 PreLoader")
            return
        ports = self._ports_now()
        new = [d for d, _x in ports if d not in self._watch_base]
        if not new:
            return
        pick = new[0]
        for d, desc in ports:
            if d in new and ("mediatek" in desc.lower() or "preloader" in desc.lower()):
                pick = d
                break
        self.watch_timer.stop()
        self.progress.setVisible(False)
        self._log("[端口] 发现新端口，立即连接：%s" % pick)
        self._fill_port_combo(ports, pick)
        self._do_read_info()

    def _do_read_info(self):
        self.parser = logparse.Session("connect")
        self._cur_text.clear()
        self.run_command(["printgpt"], "读取设备信息 / 分区表", self._after_read, 180)

    def _after_read(self, rc, text, to):
        try:
            for line in text.splitlines():
                self.parser.feed(line + "\n")
        except Exception:
            pass
        if rc != 0 or len(self.parser.partitions) < 1:
            self.status.setText("读取失败：没有拿到有效分区表")
            self.status.setStyleSheet("color:%s;" % theme.RED)
            self._log("[GPT] 失败：rc=%s，分区=%d" % (rc, len(self.parser.partitions)))
            self._log("[GPT] 原始输出尾部：" + (text[-500:] if text else "无"))
            self.progress.setVisible(False)
            return
        self._fill_gpt(self.parser)
        self.status.setText("读取完成：%d 个分区" % len(self.parser.partitions))
        self._log("[GPT] %d 个分区，磁盘 %s" %
                  (len(self.parser.partitions), _hsize(self.parser.disk_size)))
        self._save_state()
        self.progress.setVisible(False)
        if self.chk_pre.isChecked():
            self._export_pre()
        if self.chk_scatter.isChecked():
            self._gen_scatter()

    def _export_pre(self):
        names = dict(getattr(self.parser, "partition_sizes", {}))
        plan, err = preloader.export_plan(names, config.DIR_READ)
        if err:
            self._log("[Preloader] " + err)
            return
        self.run_command(["r", plan["name"], plan["file"]], "导出 Preloader", 600)

    def _gen_scatter(self):
        if not self.parser:
            return
        entries = []
        for n, m in self.parser.partition_meta.items():
            entries.append({"name": n, "offset": m.get("offset", 0), "size": m.get("size", 0),
                            "file_name": n + ".bin", "download": True})
        p = os.path.join(config.WORK, "generated_scatter.txt")
        scatter.write(p, entries)
        self._log("[Scatter] 已生成 " + p)

    def read_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.information(self, "没有选择", "请先在分区表中选择分区。")
            return
        raw = [r for r in items if r.get("raw")]
        if raw and len(raw) == len(items):
            out = QFileDialog.getExistingDirectory(self, "选择回读目录", config.DIR_READ)
            if not out:
                return
            steps = []
            for r in raw:
                path = r.get("file") or os.path.join(out, "raw_%x.bin" % r["start"])
                pt = {"BOOT_1": "boot1", "BOOT_2": "boot2"}.get(r["unit"], "")
                args = ["ro", hex(r["start"]), hex(r["size"]), path]
                if pt:
                    args += ["--parttype", pt]
                steps.append(args)
            self._run_steps(steps, "回读自定义地址", 14400)
            return
        names = [r["name"] for r in items if not r.get("raw")]
        out = QFileDialog.getExistingDirectory(self, "选择回读目录", config.DIR_READ)
        if not out:
            return
        steps = [["r", n, os.path.join(out, n + ".bin")] for n in names]
        self._run_steps(steps, "回读 %d 个分区" % len(names), 14400)

    def write_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.information(self, "没有选择", "请先在分区表中选择分区。")
            return
        raw = [r for r in items if r.get("raw")]
        if raw and len(raw) == len(items):
            steps = []
            for r in raw:
                if not r.get("file") or not os.path.isfile(r["file"]):
                    QMessageBox.critical(self, "缺少文件", "自定义地址没有写入文件。")
                    return
                args = ["wo", hex(r["start"]), hex(r["size"]), r["file"]]
                if r["unit"] in ("BOOT_1", "BOOT_2"):
                    args += ["--parttype", "boot1" if r["unit"] == "BOOT_1" else "boot2"]
                steps.append(args)
            if QMessageBox.question(self, "确认写自定义地址",
                                    "即将写入原始地址。\n\n确定继续？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self._run_steps(steps, "写自定义地址", 14400)
            return
        d = self.image_dir
        if not d or not os.path.isdir(d):
            d = QFileDialog.getExistingDirectory(self, "选择镜像目录（文件名=分区名.bin）", config.WORK)
        if not d:
            return
        self.image_dir = d
        plans, errors = [], []
        live = dict(getattr(self.parser, "partition_sizes", {})) if self.parser else {}
        for r in items:
            if r.get("raw"):
                continue
            n = r["name"]
            if n in parts.BLOCK_WRITE:
                errors.append("安全规则禁止写入：" + n)
                continue
            p = os.path.join(d, n + ".bin")
            if not os.path.isfile(p):
                errors.append("缺少 " + n + ".bin")
                continue
            size = os.path.getsize(p)
            if n in live and live[n] and size > live[n]:
                errors.append("%s 文件大于分区" % n)
                continue
            plans.append((n, p))
        if errors:
            QMessageBox.critical(self, "预检失败", "\n".join(errors))
            return
        if QMessageBox.question(self, "确认刷入",
                                "即将写入 %d 个分区。\n\n确定继续？" % len(plans),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._run_steps([["w", n, p] for n, p in plans], "刷入选定分区", 14400)

    def write_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择镜像目录", config.WORK)
        if not d:
            return
        live = dict(getattr(self.parser, "partition_sizes", {})) if self.parser else {}
        if self.scatter is not None:
            plans, errors = scatter.plan_directory(self.scatter, d, live,
                                                    blocked=parts.BLOCK_WRITE)
            if errors:
                QMessageBox.critical(self, "预检失败", "\n".join(errors[:30]))
                return
        else:
            images = {}
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    name = os.path.splitext(fn)[0]
                    if name in parts.BLOCK_WRITE:
                        continue
                    images[name] = p
            plans, errors = preloader.batch_plan(images, live, set(), only_existing=False)
            if errors:
                QMessageBox.critical(self, "预检失败", "\n".join(errors[:30]))
                return
        if not plans:
            QMessageBox.information(self, "没有镜像", "目录里没有可写入的镜像。")
            return
        if QMessageBox.question(self, "确认刷入目录",
                                "即将写入 %d 个镜像。\n\n确定继续？" % len(plans),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._run_steps([["w", p["name"], p["file"]] for p in plans],
                        "刷入目录全部文件", 14400)

    def erase_selected(self):
        names = self.selected_names()
        if not names:
            QMessageBox.information(self, "没有选择", "请先选择分区。")
            return
        blocked = sorted(set(names) & parts.BLOCK_ERASE)
        if blocked:
            QMessageBox.critical(self, "安全规则拒绝", "以下分区禁止擦除：\n" + "、".join(blocked))
            return
        mode = self.cmb_erase.currentText()
        if QMessageBox.question(self, "确认擦除",
                                "确定擦除：\n%s\n\n模式：%s" % ("、".join(names[:20]), mode),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        steps = []
        for n in names:
            if mode.startswith("快速"):
                # 快速擦除只清前面 0x1000 个扇区；完整擦除走 e 全分区。
                steps.append(["es", n, "0x1000"])
            else:
                steps.append(["e", n])
        self._run_steps(steps, "擦除分区", 14400)

    def factory_reset(self):
        live = [r["name"] for r in self.rows]
        targets, errors = factory.plan(live)
        if errors:
            QMessageBox.critical(self, "预检失败", "\n".join(errors))
            return
        if QMessageBox.question(self, "恢复出厂设置",
                                "将擦除：\n%s\n\n确定继续？" % "、".join(targets),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        steps = [["e", n] for n in targets]
        self._run_steps(steps, "恢复出厂设置", 14400)

    def _seccfg(self, flag):
        if QMessageBox.warning(self, "高风险操作",
                               "seccfg %s 会修改 BL 锁状态，可能影响开机。\n\n继续？" % flag,
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.run_command(["da", "seccfg", flag], "BL %s" % flag, 600)

    def _vbmeta(self, mode):
        self.run_command(["da", "vbmeta", str(mode)], "Vbmeta 修补 %d" % mode, 600)

    def _bypass_info(self):
        QMessageBox.information(self, "Bypass",
                                "连接阶段已经执行 DA1 安全绕过；\n"
                                "这里不重复写入手机，避免二次破坏。")

    def _preloader_op(self, op):
        part = "preloader"
        if self.parser:
            part = preloader.find_preloader(self.parser.partition_sizes) or "preloader"
        if op == "r":
            p, _ = QFileDialog.getSaveFileName(self, "保存 Preloader", os.path.join(config.DIR_READ, part + ".bin"))
            if not p:
                return
            self.run_command(["r", part, p], "读取 Preloader", 600)
        elif op == "w":
            p, _ = QFileDialog.getOpenFileName(self, "选择 Preloader")
            if not p:
                return
            if QMessageBox.warning(self, "写入 Preloader",
                                   "写错 Preloader 会导致无法开机。\n\n确定写入？",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.run_command(["w", part, p], "写入 Preloader", 900)
        else:
            if QMessageBox.warning(self, "擦除 Preloader",
                                   "擦除 Preloader 会导致无法开机。\n\n确定擦除？",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.run_command(["e", part], "擦除 Preloader", 600)

    def _rpmb_op(self, op):
        if op == "e":
            if QMessageBox.warning(self, "擦除 RPMB", "RPMB 擦除可能导致设备无法解密。\n\n继续？",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.run_command(["da", "rpmb", "e"], "擦除 RPMB", 900)
            return
        if op == "r":
            p, _ = QFileDialog.getSaveFileName(self, "保存 RPMB", os.path.join(config.DIR_READ, "rpmb.bin"))
            if p:
                self.run_command(["da", "rpmb", "r", p], "读取 RPMB", 900)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "选择 RPMB")
            if p:
                if QMessageBox.warning(self, "写入 RPMB", "RPMB 写入风险极高。\n\n继续？",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                self.run_command(["da", "rpmb", "w", p], "写入 RPMB", 900)

    def _dump_brom(self):
        self.run_command(["da", "dumpbrom"], "导出 Brom", 1200)

    def _gen_keys(self):
        if QMessageBox.warning(
                self, "生成密钥",
                "生成密钥会让 DA 连续执行 SSR / FDE / ROT / FW key 操作。\n"
                "部分 Preloader/DA 在最后一步会断开串口，报设备未发挥作用。\n\n"
                "失败后需要重新进入 Preloader。\n\n继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.run_command(["da", "generatekeys"], "生成密钥", 600)

    # ---------------------------------------------------------------- GPT
    def _gpt_meta(self):
        p = self.parser
        if not p or not p.disk_size or not p.sector_size:
            return None
        ss = int(p.sector_size)
        total = int(p.total_sectors or (p.disk_size // ss))
        if ss not in gpt.SECTOR_SIZES or total <= 0:
            return None
        disk_size = total * ss
        read_len = max(0x10000, 128 * 128 + 4 * ss)
        read_len = min(disk_size, read_len)
        read_len = (read_len // ss) * ss
        if read_len < ss * 2:
            read_len = disk_size
        return {"sector_size": ss, "total_sectors": total,
                "disk_size": disk_size, "read_len": read_len,
                "backup_offset": disk_size - read_len}

    def _ask_gpt_target(self, default_size, default_ss):
        text, ok = QInputDialog.getText(
            self, "GPT 目标参数",
            "当前无法从设备读取 GPT。\n\n"
            "请输入磁盘总字节数（必须与设备真实容量一致）：",
            text=str(int(default_size or 0)))
        if not ok or not text.strip():
            return None
        try:
            disk_size = int(text.strip(), 0)
        except Exception:
            QMessageBox.critical(self, "参数错误", "磁盘容量必须是整数")
            return None
        choices = ["4096", "512"]
        default_idx = 0 if int(default_ss or 0) == 4096 else 1
        choice, ok = QInputDialog.getItem(self, "GPT 扇区大小", "选择扇区大小",
                                          choices, default_idx, False)
        if not ok:
            return None
        ss = int(choice)
        if disk_size <= 0 or disk_size % ss:
            QMessageBox.critical(self, "参数错误", "磁盘容量必须能被扇区大小整除")
            return None
        total = disk_size // ss
        read_len = max(0x10000, 128 * 128 + 4 * ss)
        read_len = min(disk_size, read_len)
        read_len = (read_len // ss) * ss
        if read_len < ss * 2:
            read_len = disk_size
        return {"sector_size": ss, "total_sectors": total,
                "disk_size": disk_size, "read_len": read_len,
                "backup_offset": disk_size - read_len}

    def _gpt_temp(self, name):
        return os.path.join(config.WORK, name)

    def _gpt_read_current(self, label, cb, prefix="v2_gpt"):
        meta = self._gpt_meta()
        if not meta:
            return
        pp = self._gpt_temp(prefix + "_primary.bin")
        bp = self._gpt_temp(prefix + "_backup.bin")
        steps = [
            ["ro", "0x0", hex(meta["read_len"]), pp],
            ["ro", hex(meta["backup_offset"]), hex(meta["read_len"]), bp],
        ]
        self.run_sequence(steps, label,
                          lambda results: cb(results, meta, pp, bp), 600)

    def _gpt_parse_current(self, meta, pp, bp):
        with open(pp, "rb") as f:
            primary = f.read()
        with open(bp, "rb") as f:
            backup = f.read()
        base = meta["backup_offset"] // meta["sector_size"]
        return gpt.GptImage.from_blocks(primary, backup, meta["total_sectors"],
                                        meta["sector_size"], backup_base_lba=base)

    def gpt_verify(self):
        def done(results, meta, pp, bp):
            if not results or results[-1][0] != 0:
                self._log("[GPT] 读取失败")
                return
            try:
                img = self._gpt_parse_current(meta, pp, bp)
                errs = img.validate(strict_mbr=True)
                s = img.summary()
                self._log("[GPT] 校验：扇区=%d，总扇区=%d，分区=%d，磁盘 GUID=%s" %
                          (s["sector_size"], s["total_sectors"],
                           s["partitions"], s["disk_guid"]))
                for w in s.get("warnings", []):
                    self._log("[GPT] 警告：" + w)
                if errs:
                    for e in errs:
                        self._log("[GPT] 错误：" + e)
                    QMessageBox.critical(self, "GPT 校验失败", "\n".join(errs))
                else:
                    QMessageBox.information(self, "GPT 校验通过",
                                            "扇区大小：%d\n总扇区：%d\n分区：%d\n磁盘 GUID：%s" %
                                            (s["sector_size"], s["total_sectors"],
                                             s["partitions"], s["disk_guid"]))
            except Exception as e:
                self._log("[GPT] 校验失败：" + str(e))
                QMessageBox.critical(self, "GPT 校验失败", str(e))
        self._gpt_read_current("校验 GPT", done, "v2_verify")

    def gpt_backup(self):
        meta = self._gpt_meta()
        if not meta:
            return
        base = QFileDialog.getExistingDirectory(self, "选择 GPT 备份保存目录", config.WORK)
        if not base:
            return
        out = os.path.join(base, "GPT_" + time.strftime("%Y%m%d_%H%M%S"))

        def done(results, meta2, pp, bp):
            if not results or results[-1][0] != 0:
                self._log("[GPT] 备份读取失败")
                return
            try:
                img = self._gpt_parse_current(meta2, pp, bp)
                errs = img.validate(strict_mbr=True)
                if errs:
                    raise gpt.GptError("；".join(errs))
                saved = img.save(out)
                self._log("[GPT] 已备份：%s" % saved["dir"])
                QMessageBox.information(self, "GPT 备份完成",
                                        "目录：\n%s\n\n磁盘 GUID：%s\n分区：%d" %
                                        (saved["dir"], img.disk_guid,
                                         len([e for e in img.entries if e.used])))
            except Exception as e:
                self._log("[GPT] 备份失败：" + str(e))
                QMessageBox.critical(self, "GPT 备份失败", str(e))
        self._gpt_read_current("备份 GPT", done, "v2_backup")

    def gpt_rebuild(self):
        sp, _ = QFileDialog.getOpenFileName(self, "选择完整 Scatter", config.WORK,
                                            "Scatter (*.txt);;所有文件 (*)")
        if not sp:
            return
        try:
            sc = scatter.load(sp)
        except Exception as e:
            QMessageBox.critical(self, "Scatter 读取失败", str(e))
            return
        names = {e.name.lower() for e in sc.entries}
        if not ({"pgpt", "sgpt"} & names):
            QMessageBox.critical(
                self, "拒绝重建 GPT",
                "这个 scatter 没有 pgpt/sgpt 条目，无法确认它是完整分区表。\n\n"
                "用只包含有镜像分区的简化 scatter 重建 GPT 会漏掉其它分区，"
                "可能直接导致设备无法启动。\n\n"
                "请使用完整机型的 scatter，或先恢复同机型 GPT 备份。")
            return
        p = self.parser
        default_size = str(int(p.disk_size)) if p and p.disk_size else "14680064000"
        text, ok = QInputDialog.getText(self, "目标磁盘容量",
                                        "磁盘总字节数：\n\n"
                                        "必须与设备真实容量一致；可从 printgpt 的 Total disk size 获取。",
                                        text=default_size)
        if not ok or not text.strip():
            return
        try:
            disk_size = int(text.strip(), 0)
        except Exception:
            QMessageBox.critical(self, "参数错误", "磁盘容量必须是整数")
            return
        ss = int(p.sector_size) if p and p.sector_size else 0
        if ss not in (512, 4096):
            choice, ok = QInputDialog.getItem(self, "扇区大小", "选择扇区大小",
                                              ["512", "4096"], 0, False)
            if not ok:
                return
            ss = int(choice)
        if disk_size <= 0 or disk_size % ss:
            QMessageBox.critical(self, "参数错误", "磁盘容量必须能被扇区大小整除")
            return
        total = disk_size // ss
        parts = []
        skip = {"pgpt", "sgpt", "preloader", "preloader_backup", "boot1", "boot2"}
        for e in sc.entries:
            if e.name.lower() in skip:
                continue
            if e.name and e.start > 0 and e.size > 0:
                parts.append({"name": e.name, "start": e.start, "size": e.size})
        if not parts:
            QMessageBox.critical(self, "Scatter 为空", "没有可用分区")
            return
        try:
            img = gpt.build_from_layout(parts, total, ss)
        except Exception as e:
            QMessageBox.critical(self, "GPT 生成失败", str(e))
            return
        if QMessageBox.warning(
                self, "确认生成并写入 GPT",
                "将根据 Scatter 生成新的 GPT：\n\n"
                "分区数：%d\n磁盘容量：%d 字节\n扇区大小：%d\n\n"
                "Scatter 必须是完整分区表，不能只包含有镜像的分区。\n"
                "分区类型 GUID 将使用 EFI Basic Data，唯一 GUID 将随机生成。\n\n"
                "这会覆盖当前 GPT，确定继续？" %
                (len(parts), disk_size, ss),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        out = os.path.join(config.WORK, "gpt_rebuild")
        if os.path.isdir(out):
            shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out, exist_ok=True)
        try:
            img.save(out)
        except Exception as e:
            QMessageBox.critical(self, "GPT 保存失败", str(e))
            return
        plan = img.restore_plan(total, ss)
        pp = os.path.join(out, "pgpt.bin")
        bp = os.path.join(out, "sgpt.bin")
        read_len = min(disk_size, 0x10000)
        read_len = (read_len // ss) * ss
        backup_off = disk_size - read_len
        pre_p = os.path.join(out, "pre_rebuild_pgpt.bin")
        pre_b = os.path.join(out, "pre_rebuild_sgpt.bin")
        vp = os.path.join(out, "verify_pgpt.bin")
        vb = os.path.join(out, "verify_sgpt.bin")
        steps = [
            ["ro", "0x0", hex(read_len), pre_p],
            ["ro", hex(backup_off), hex(read_len), pre_b],
            ["wo", hex(plan["backup_offset"]), hex(plan["backup_length"]), bp],
            ["wo", "0x0", hex(plan["primary_length"]), pp],
            ["ro", "0x0", hex(read_len), vp],
            ["ro", hex(backup_off), hex(read_len), vb],
        ]

        def done(results):
            if results and all(r[0] == 0 and not r[2] for r in results):
                try:
                    with open(vp, "rb") as f:
                        vpdata = f.read()
                    with open(vb, "rb") as f:
                        vbdata = f.read()
                    check = gpt.GptImage.from_blocks(
                        vpdata, vbdata, total, ss,
                        backup_base_lba=backup_off // ss)
                    errs = check.validate(strict_mbr=True)
                    if errs:
                        raise gpt.GptError("；".join(errs))
                    self._log("[GPT] 重建完成，读回校验通过；原 GPT 已保存到 " + out)
                    self.status.setText("GPT 重建完成")
                except Exception as e:
                    self._log("[GPT] 重建后校验失败：" + str(e))
                    QMessageBox.critical(self, "GPT 写后校验失败",
                                         "GPT 已写入，但读回校验失败。\n"
                                         "不要重启，先检查 pre_rebuild_* 备份。\n\n" + str(e))
            else:
                self._log("[GPT] 重建写入失败")
        self.run_sequence(steps, "重建 GPT（含原表备份）", done, 1200)

    def gpt_restore(self):
        d = QFileDialog.getExistingDirectory(self, "选择 GPT 备份目录", config.WORK)
        if not d:
            return
        try:
            backup_img = gpt.GptImage.load(d)
            errs = backup_img.validate(strict_mbr=True)
            if errs:
                raise gpt.GptError("；".join(errs))
        except Exception as e:
            QMessageBox.critical(self, "GPT 备份无效", str(e))
            return
        meta = self._gpt_meta()
        if meta:
            self._gpt_read_current(
                "读取当前 GPT",
                lambda results, m, pp, bp: self._gpt_restore_after_read(
                    backup_img, m, pp, bp, results),
                "v2_current")
        else:
            meta = self._ask_gpt_target(backup_img.disk_size, backup_img.sector_size)
            if not meta:
                return
            if QMessageBox.warning(
                    self, "无法读取当前 GPT",
                    "当前设备 GPT 不可读，将按以下参数直接恢复：\n\n"
                    "容量：%d 字节\n扇区：%d\n备份磁盘 GUID：%s\n\n"
                    "确定继续？" % (meta["disk_size"], meta["sector_size"],
                                   backup_img.disk_guid),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self._gpt_restore_apply(backup_img, meta, None)

    def _gpt_restore_after_read(self, backup_img, meta, pp, bp, results):
        if not results or results[-1][0] != 0:
            self._log("[GPT] 读取当前 GPT 失败，改为按备份参数恢复")
            self._gpt_restore_apply(backup_img, meta, None)
            return
        current = None
        try:
            current = self._gpt_parse_current(meta, pp, bp)
        except Exception as e:
            self._log("[GPT] 当前 GPT 解析失败：" + str(e))
        self._gpt_restore_apply(backup_img, meta, current)

    def _gpt_restore_apply(self, backup_img, meta, current):
        if current is not None and backup_img.disk_guid != current.disk_guid:
            QMessageBox.critical(self, "拒绝恢复",
                                 "备份磁盘 GUID 与当前设备不一致：\n\n"
                                 "备份：%s\n当前：%s" %
                                 (backup_img.disk_guid, current.disk_guid))
            return
        if backup_img.sector_size != meta["sector_size"] or \
                backup_img.total_sectors != meta["total_sectors"]:
            QMessageBox.critical(self, "拒绝恢复", "备份的扇区大小或磁盘容量与当前设备不一致。")
            return
        try:
            plan = backup_img.restore_plan(meta["total_sectors"],
                                           meta["sector_size"],
                                           current.disk_guid if current else None)
        except Exception as e:
            QMessageBox.critical(self, "拒绝恢复", str(e))
            return
        if QMessageBox.warning(
                self, "确认刷写 GPT",
                "目标磁盘：\n容量 %d 扇区 / %d 字节\n扇区大小 %d\n"
                "磁盘 GUID：%s\n\n"
                "将先写备份 GPT，再写主 GPT，然后读回校验。\n"
                "写错分区表可能导致设备无法开机。\n\n确定继续？" %
                (meta["total_sectors"], meta["disk_size"],
                 meta["sector_size"], backup_img.disk_guid),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        ppg = self._gpt_temp("v2_restore_pgpt.bin")
        psg = self._gpt_temp("v2_restore_sgpt.bin")
        with open(ppg, "wb") as f:
            f.write(plan["primary_data"])
        with open(psg, "wb") as f:
            f.write(plan["backup_data"])
        vp = self._gpt_temp("v2_restore_verify_p.bin")
        vb = self._gpt_temp("v2_restore_verify_b.bin")
        steps = [
            ["wo", hex(plan["backup_offset"]), hex(plan["backup_length"]), psg],
            ["wo", "0x0", hex(plan["primary_length"]), ppg],
            ["ro", "0x0", hex(meta["read_len"]), vp],
            ["ro", hex(meta["backup_offset"]), hex(meta["read_len"]), vb],
        ]

        def restore_done(results2):
            if not results2 or results2[-1][0] != 0:
                self._log("[GPT] 刷写失败，请勿重启，保留当前备份")
                return
            try:
                with open(vp, "rb") as f:
                    vpdata = f.read()
                with open(vb, "rb") as f:
                    vbdata = f.read()
                img = gpt.GptImage.from_blocks(
                    vpdata, vbdata,
                    meta["total_sectors"], meta["sector_size"],
                    backup_base_lba=meta["backup_offset"] // meta["sector_size"])
                errs2 = img.validate(strict_mbr=True)
                if errs2:
                    raise gpt.GptError("；".join(errs2))
                self._log("[GPT] 刷写完成，读回校验通过：%d 个分区" %
                          len([e for e in img.entries if e.used]))
                self.status.setText("GPT 刷写完成")
            except Exception as e:
                self._log("[GPT] 写后校验失败：" + str(e))
                QMessageBox.critical(self, "GPT 写后校验失败",
                                     "分区表已经写入但读回校验失败。\n"
                                     "不要重启，先检查日志和备份。\n\n" + str(e))
        self.run_sequence(steps, "刷写 GPT", restore_done, 1200)

    def _slot_view(self):
        p = os.path.join(config.WORK, "v2_misc_slot.bin")
        self.run_command(["r", "misc", p], "读取当前槽位", 600,
                         lambda rc, text, to: self._slot_show(p, rc))

    def _slot_show(self, path, rc):
        try:
            data = open(path, "rb").read()
            if len(data) >= 0x802:
                slot = data[0x800:0x802].decode("utf-8", "replace").strip("\x00")
                self._log("[槽位] 当前槽位：%s" % (slot or "未设置"))
            else:
                self._log("[槽位] misc 数据长度不足")
        except Exception as e:
            self._log("[槽位] 读取失败：%s" % e)

    def _slot_set(self, slot):
        if QMessageBox.warning(self, "修改槽位",
                               "修改当前槽位可能影响系统启动。\n\n设为 %s？" % slot.upper(),
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        p = os.path.join(config.WORK, "v2_misc_slot.bin")
        self._slot_target = slot
        self.run_command(["r", "misc", p], "读取 misc", 600,
                         lambda rc, text, to: self._slot_write(p, rc))

    def _slot_write(self, path, rc):
        try:
            data = bytearray(open(path, "rb").read())
            if len(data) < 0x802:
                raise ValueError("misc 长度不足")
            data[0x800:0x802] = self._slot_target.encode("ascii")
            open(path, "wb").write(data)
            self.run_command(["w", "misc", path], "写入槽位", 600)
        except Exception as e:
            QMessageBox.critical(self, "槽位写入失败", str(e))

    def _erase_frp(self):
        if QMessageBox.warning(self, "移除谷歌锁",
                               "将擦除 frp 分区，可能解除恢复出厂保护。\n\n确定执行？",
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.run_command(["e", "frp"], "移除谷歌锁", 600)

    def _oem(self, enable):
        if QMessageBox.question(self, "OEM 解锁开关",
                                "将向 fastboot 发送 OEM %s 命令。\n\n继续？" %
                                ("解锁" if enable else "上锁"),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._fastboot("oem %s" % ("unlock" if enable else "lock"), "OEM %s" %
                       ("打开" if enable else "关闭"))

    def _fastboot(self, command, label):
        try:
            from core.fastboot import fastboot_run
            rc, out = fastboot_run(command.split(), timeout=30)
            self._log("[%s] rc=%s\n%s" % (label, rc, out))
            self.status.setText("%s：%s" % (label, "完成" if rc == 0 else "失败"))
        except Exception as e:
            self._log("[%s] 失败：%s" % (label, e))

    def _reboot(self, command):
        self.run_command([command], "重启设备", 180)

    def reboot(self):
        self.run_command(["reset"], "重启设备", 180)

    def _steps_done(self, label, results):
        ok = bool(results) and all(r[0] == 0 and not r[2] for r in results)
        if ok:
            self._log("[完成] %s（%d 步）" % (label, len(results)))
        else:
            self._log("[失败] %s" % label)

    def _run_steps(self, steps, label, timeout=14400):
        if not steps:
            return
        self.run_sequence(steps, label, lambda results: self._steps_done(label, results), timeout)

    def _confirm_run(self, script, label, kind):
        self.run_command(["script", script], label, 14400)

    def _toggle_log(self, *_):
        self.log.setVisible(self.chk_log.isChecked())

    def save_theme(self):
        mode = self.cmb_theme.currentData()
        try:
            from core import uiprefs
            uiprefs.save({"theme": mode, "animations": True})
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QMessageBox.information(self, "已保存", "关闭程序后重新打开，主题才会完整生效。")

    def closeEvent(self, e):
        if self.busy and QMessageBox.question(
                self, "操作进行中", "当前操作还没有结束，确定退出？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            e.ignore()
            return
        try:
            if getattr(self, "port_timer", None):
                self.port_timer.stop()
            if getattr(self, "watch_timer", None):
                self.watch_timer.stop()
            if getattr(self, "deep_page", None) and self.deep_page.pkg:
                self.deep_page.pkg.cleanup()
            if self.session:
                self.session.stop()
                self.session.wait(2000)
        except Exception:
            pass
        super().closeEvent(e)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.qss())
    w = MainWindow()
    if "--selftest" in sys.argv:
        print("V2 RESULT : OK")
        return 0
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
