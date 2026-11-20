# -*- coding: utf-8 -*-
"""V2 专业工具主题：纯背景明/暗，紧凑控件，无装饰卡片。"""
import os

MODE = "light"
_P = {
    "light": dict(BG="#f2f4f7", PANEL="#ffffff", ALT="#f8fafc", LINE="#d5dbe3",
                  LINE2="#c3ccd8", TEXT="#17202b", TEXT2="#3f4c5c", MUTED="#6b7787",
                  FAINT="#96a1af", ACCENT="#1f5fbf", ACCENT2="#174a96",
                  GREEN="#197a43", RED="#c02626", YELLOW="#a55b00"),
    "dark": dict(BG="#111316", PANEL="#191c20", ALT="#1e2228", LINE="#30363e",
                 LINE2="#3d4651", TEXT="#e6e9ee", TEXT2="#bdc6d2", MUTED="#8b97a6",
                 FAINT="#5d6876", ACCENT="#4f9cf0", ACCENT2="#3c7dcc",
                 GREEN="#4dbb7c", RED="#f06a6a", YELLOW="#d7a84b"),
}
try:
    from core import uiprefs
    _prefs = uiprefs.load()
    MODE = _prefs.get("theme", "light")
except Exception:
    _prefs = {"theme": "light", "animations": True}
if MODE not in _P:
    MODE = "light"
globals().update(_P[MODE])
ANIMATIONS = bool(_prefs.get("animations", True))


def set_mode(mode):
    global MODE
    if mode not in _P:
        mode = "light"
    MODE = mode
    globals().update(_P[mode])


def qss():
    return """
QWidget { color:%(TEXT)s; background:%(BG)s; font-family:"Microsoft YaHei UI"; font-size:12px; }
QMainWindow, QDialog { background:%(BG)s; }
QFrame#Panel { background:%(PANEL)s; border:1px solid %(LINE)s; }
QLabel { background:transparent; }
QPushButton {
    background:%(PANEL)s; border:1px solid %(LINE2)s; color:%(TEXT)s;
    padding:5px 10px; min-height:20px;
}
QPushButton:hover { border-color:%(ACCENT)s; color:%(ACCENT)s; }
QPushButton:pressed { background:%(ALT)s; }
QPushButton:disabled { color:%(FAINT)s; border-color:%(LINE)s; }
QPushButton#primary { background:%(ACCENT)s; border-color:%(ACCENT)s; color:#ffffff; }
QPushButton#primary:hover { background:%(ACCENT2)s; }
QPushButton#danger { color:%(RED)s; }
QPushButton#danger:hover { border-color:%(RED)s; }
QLineEdit, QComboBox {
    background:%(PANEL)s; border:1px solid %(LINE2)s; padding:4px 6px; min-height:20px;
    selection-background-color:%(ACCENT)s;
}
QComboBox::drop-down { border:none; width:18px; }
QComboBox QAbstractItemView { background:%(PANEL)s; border:1px solid %(LINE2)s;
    selection-background-color:%(ACCENT)s; selection-color:#fff; }
QCheckBox, QRadioButton { spacing:6px; background:transparent; }
QTableWidget {
    background:%(PANEL)s; alternate-background-color:%(ALT)s; border:1px solid %(LINE)s;
    gridline-color:%(LINE)s; selection-background-color:%(ACCENT)s; selection-color:#fff;
}
QHeaderView::section { background:%(ALT)s; color:%(MUTED)s; border:none;
    border-right:1px solid %(LINE)s; border-bottom:1px solid %(LINE)s; padding:5px 6px; }
QTableWidget::item { padding:3px 6px; }
QPlainTextEdit, QTextEdit { background:%(PANEL)s; border:1px solid %(LINE)s;
    color:%(TEXT2)s; font-family:Consolas; font-size:11px; }
QProgressBar { background:%(ALT)s; border:1px solid %(LINE)s; min-height:16px; max-height:16px;
    text-align:center; color:%(TEXT2)s; }
QProgressBar::chunk { background:%(ACCENT)s; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:%(BG)s; width:10px; }
QScrollBar::handle:vertical { background:%(LINE2)s; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QSplitter::handle { background:%(LINE)s; }
QListWidget, QTreeWidget { background:%(PANEL)s; border:1px solid %(LINE)s; }
QTreeWidget::item:selected, QListWidget::item:selected { background:%(ACCENT)s; color:#fff; }
QToolTip { background:%(PANEL)s; color:%(TEXT)s; border:1px solid %(ACCENT)s; padding:4px; }
""" % globals()
