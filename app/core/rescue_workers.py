# -*- coding: utf-8 -*-
"""救砖包的后台任务：打包、校验、解压。"""
import shutil

from PySide6.QtCore import QThread, Signal

from . import rescue


class PackageBuildWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, zip_path, backup_dir, gpt_primary, gpt_backup,
                 device=None, package_type="full", parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self.backup_dir = backup_dir
        self.gpt_primary = gpt_primary
        self.gpt_backup = gpt_backup
        self.device = device or {}
        self.package_type = package_type
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            result = rescue.create_package(
                self.zip_path, self.backup_dir, self.gpt_primary, self.gpt_backup,
                device=self.device, package_type=self.package_type,
                progress=lambda a, b, c: self.progress.emit(a, b, c),
                stop=lambda: self._stop)
            self.done.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class PackageCheckWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, zip_path, parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            result = rescue.inspect_package(
                self.zip_path, verify_hashes=True,
                progress=lambda a, b, c: self.progress.emit(a, b, c),
                stop=lambda: self._stop)
            self.done.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class PackageExtractWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, zip_path, dest, parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self.dest = dest
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            shutil.rmtree(self.dest, ignore_errors=True)
            result = rescue.extract_package(
                self.zip_path, self.dest,
                progress=lambda a, b, c: self.progress.emit(a, b, c),
                stop=lambda: self._stop)
            self.done.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
