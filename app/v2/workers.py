# -*- coding: utf-8 -*-
"""后台工作线程：把阻塞解析/解包移出 UI 线程。"""
from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:
            import traceback
            self.failed.emit(str(e) + "\n" + traceback.format_exc(limit=4))
