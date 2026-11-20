# -*- coding: utf-8 -*-
"""后台哈希校验线程：不阻塞 UI。"""
import os

from PySide6.QtCore import QThread, Signal

from . import manifest


class ManifestWorker(QThread):
    """扫描一个备份目录：算哈希、比对清单、必要时生成清单。"""

    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, dir_path, names, expected_sizes=None, kind="",
                 write_missing=True, include_existing=False, parent=None):
        super().__init__(parent)
        self.dir_path = dir_path
        self.names = list(names or [])
        self.expected_sizes = dict(expected_sizes or {})
        self.kind = kind
        self.write_missing = write_missing
        self.include_existing = include_existing
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            result = manifest.scan_dir(
                self.dir_path, self.names, self.expected_sizes, self.kind,
                write_missing=self.write_missing, include_existing=self.include_existing,
                stop=lambda: self._stop,
                progress=lambda d, t, n: self.progress.emit(d, t, n),
            )
        except Exception as e:
            result = {
                "dir": self.dir_path, "kind": self.kind, "complete": False,
                "stopped": self._stop, "missing": [], "bad_size": [],
                "hash_mismatch": [], "errors": [("manifest", str(e))],
                "entries": [], "manifest_written": False,
            }
        self.done.emit(result)


class MultiManifestWorker(QThread):
    """依次校验多个目录（备份页的“校验备份”）。"""

    progress = Signal(int, int, str)
    done = Signal(list)

    def __init__(self, tasks, parent=None):
        """tasks: [(dir_path, names, expected_sizes, kind), ...]"""
        super().__init__(parent)
        self.tasks = list(tasks)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        results = []
        total_files = 0
        for _d, names, _e, _k in self.tasks:
            total_files += len(names or [])
        done_files = 0
        for dir_path, names, expected, kind in self.tasks:
            if self._stop:
                break
            try:
                result = manifest.scan_dir(
                    dir_path, names, expected, kind, write_missing=True,
                    include_existing=True, stop=lambda: self._stop,
                    progress=lambda d, t, n: self.progress.emit(
                        done_files + d, max(1, total_files), "%s / %s" % (os.path.basename(dir_path), n)),
                )
            except Exception as e:
                result = {
                    "dir": dir_path, "kind": kind, "complete": False,
                    "stopped": False, "missing": [], "bad_size": [],
                    "hash_mismatch": [], "errors": [("manifest", str(e))],
                    "entries": [], "manifest_written": False,
                }
            done_files += len(names or [])
            results.append(result)
        self.done.emit(results)


class FileHashWorker(QThread):
    """给单个读取出来的文件算哈希（读取分区用）。"""

    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, path, expected_size=None, parent=None):
        super().__init__(parent)
        self.path = path
        self.expected_size = expected_size
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        result = {"path": self.path, "ok": False, "stopped": False,
                  "size": 0, "sha256": "", "error": ""}
        try:
            size = os.path.getsize(self.path)
            result["size"] = size
            if self.expected_size is not None and size != int(self.expected_size):
                result["error"] = "尺寸不符：%d / 应为 %d" % (size, int(self.expected_size))
                self.done.emit(result)
                return
            digest = manifest.file_digest(
                self.path,
                progress=lambda d, t: self.progress.emit(
                    int(d * 100 / max(1, t)), 100,
                    "%.1f%%" % (d * 100 / max(1, t))),
                stop=lambda: self._stop,
            )
            if digest is None:
                result["stopped"] = True
            else:
                result["sha256"] = digest
                result["ok"] = True
        except Exception as e:
            result["error"] = str(e)
        self.done.emit(result)
