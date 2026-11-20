# -*- coding: utf-8 -*-
"""mtkclient 子进程封装。

界面只和 MtkWorker 打交道：
    line      原始输出流（含 ANSI，界面层负责清洗显示）
    progress  解析出的百分比
    done      (returncode, 完整输出, 是否超时)
"""
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QThread, Signal

from . import config


def build_command(args):
    """源码运行时必须显式带上 main.py；冻结后 exe 自己就是入口。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mtk"] + list(args)
    entry = os.path.join(config.BASE, "main.py")
    return [sys.executable, entry, "--mtk"] + list(args)


_GLOBAL_FLAGS = {"--skipmeid"}
_GLOBAL_VALUED = {"--serialport", "--loader", "--preloader", "--auth", "--ptype"}


def command_only(args):
    """去掉常驻 server 已经持有的全局参数，只留下命令本身。"""
    out = []
    i = 0
    args = list(args)
    while i < len(args):
        a = str(args[i])
        if a in _GLOBAL_FLAGS:
            i += 1
            continue
        if a in _GLOBAL_VALUED:
            i += 2
            continue
        out.append(a)
        i += 1
    return out


class MtkWorker(QThread):
    line = Signal(str)
    progress = Signal(int)
    done = Signal(int, str, bool)

    def __init__(self, args, timeout, parent=None):
        super().__init__(parent)
        self.args = list(args)
        self.timeout = timeout
        self._stop = False
        self.proc = None

    def stop(self):
        self._stop = True

    def _kill_tree(self):
        proc = self.proc
        if proc is None:
            return
        try:
            if os.name == "nt":
                subprocess.call(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=config.CREATE_NO_WINDOW,
                                startupinfo=config.STARTUPINFO)
            else:
                proc.kill()
        except Exception:
            pass

    def run(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            os.makedirs(config.WORK, exist_ok=True)
            self.proc = subprocess.Popen(
                build_command(self.args),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                cwd=config.WORK, env=env,
                creationflags=config.CREATE_NO_WINDOW, startupinfo=config.STARTUPINFO,
            )
        except Exception as e:
            self.done.emit(-1, "启动失败: %s" % e, False)
            return

        q = queue.Queue()

        def reader():
            try:
                while True:
                    b = self.proc.stdout.read(4096)
                    if not b:
                        break
                    q.put(b)
            except Exception:
                pass
            q.put(None)

        threading.Thread(target=reader, daemon=True).start()
        chunks = []
        deadline = time.time() + self.timeout
        timed_out = False
        while True:
            try:
                b = q.get(timeout=0.15)
            except queue.Empty:
                b = b""
            if b is None:
                break
            if b:
                s = b.decode("utf-8", "replace")
                chunks.append(s)
                self.line.emit(s)
                mm = re.findall(r"(\d{1,3})\.\d\s*%", s)
                if mm:
                    try:
                        self.progress.emit(int(mm[-1]))
                    except Exception:
                        pass
            if self._stop:
                break
            if time.time() > deadline:
                timed_out = True
                break
        if timed_out or self._stop:
            self._kill_tree()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass
        rc = self.proc.returncode if self.proc.returncode is not None else -1
        if timed_out:
            rc = -1
        self.done.emit(rc, "".join(chunks), timed_out)


class MtkSession(QThread):
    """常驻 mtkclient server。

    首次提交命令时启动一个 `mtk.py ... server` 子进程，server 只做一次
    connect + configure_da，之后所有 printgpt/r/w/e/script 都复用同一个 DA。
    """

    line = Signal(str)
    progress = Signal(int)
    done = Signal(int, str, bool)

    def __init__(self, base_args, parent=None):
        super().__init__(parent)
        self.base_args = list(base_args)
        self.proc = None
        self._stop = False
        self._cmdq = queue.Queue()
        self._cid = 0
        self._buffer = ""
        self._ready = False
        self._current = None
        self._start_deadline = None

    def submit(self, args, timeout):
        self._cid += 1
        if not self._ready and self._start_deadline is None:
            self._start_deadline = time.time() + max(10, timeout)
        self._cmdq.put((self._cid, list(args), timeout))
        return self._cid

    def stop(self):
        self._stop = True
        self._kill_tree()

    def _kill_tree(self):
        proc = self.proc
        if proc is None:
            return
        try:
            if os.name == "nt":
                subprocess.call(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=config.CREATE_NO_WINDOW,
                                startupinfo=config.STARTUPINFO)
            else:
                proc.kill()
        except Exception:
            pass

    def _emit_text(self, text):
        if not text:
            return
        if self._current is not None:
            self._current["text"].append(text)
        self.line.emit(text)
        mm = re.findall(r"(\d{1,3})\.\d\s*%", text)
        if mm:
            try:
                self.progress.emit(int(mm[-1]))
            except Exception:
                pass

    def _consume(self, chunk):
        self._buffer += chunk
        # 保留可能是半个 marker 的尾部，避免破坏 @@DSH_...@@。
        while True:
            m = re.search(r"@@DSH_(READY|FATAL|BEGIN|END)([^@]*)@@", self._buffer)
            if not m:
                cut = self._buffer.rfind("@@DSH_")
                if cut >= 0:
                    # 可能是被拆开的 marker，先输出前面，后面继续等。
                    self._emit_text(self._buffer[:cut])
                    self._buffer = self._buffer[cut:]
                else:
                    self._emit_text(self._buffer)
                    self._buffer = ""
                    break
                break
            self._emit_text(self._buffer[:m.start()])
            kind = m.group(1)
            payload = m.group(2).strip()
            self._buffer = self._buffer[m.end():]
            if kind == "READY":
                self._ready = True
                continue
            if kind == "FATAL":
                self._emit_text("\n[SERVER] " + payload + "\n")
                if self._current is not None:
                    self._flush_current(-1, False)
                else:
                    self.done.emit(-1, payload, False)
                continue
            if kind == "BEGIN":
                deadline = self._current.get("deadline") if self._current else None
                self._current = {"id": payload, "text": [], "deadline": deadline}
                continue
            if kind == "END":
                parts = payload.split()
                cid = parts[0] if parts else ""
                rc = int(parts[1]) if len(parts) > 1 else -1
                if self._current and str(self._current["id"]) == str(cid):
                    text = "".join(self._current["text"])
                    self._current = None
                    self.done.emit(rc, text, False)

    def _flush_current(self, rc, timed_out):
        cur = self._current
        if cur is None:
            return
        self._current = None
        self.done.emit(rc, "".join(cur["text"]), timed_out)

    def run(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            os.makedirs(config.WORK, exist_ok=True)
            self.proc = subprocess.Popen(
                build_command(self.base_args + ["server"]),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, cwd=config.WORK, env=env,
                creationflags=config.CREATE_NO_WINDOW, startupinfo=config.STARTUPINFO,
            )
        except Exception as e:
            self.done.emit(-1, "启动常驻会话失败: %s" % e, False)
            return

        q = queue.Queue()

        def reader():
            try:
                while True:
                    b = self.proc.stdout.read(4096)
                    if not b:
                        break
                    q.put(b)
            except Exception:
                pass
            q.put(None)

        threading.Thread(target=reader, daemon=True).start()

        while not self._stop:
            try:
                b = q.get(timeout=0.05)
            except queue.Empty:
                b = b""
            if b is None:
                self._flush_current(-1, False)
                break
            if b:
                self._consume(b.decode("utf-8", "replace"))

            if not self._ready and self._start_deadline is not None:
                if time.time() > self._start_deadline:
                    self._kill_tree()
                    self.done.emit(-1, "常驻会话连接/DA 初始化超时", True)
                    break

            if self._ready and self._current is None and not self._cmdq.empty():
                cid, args, timeout = self._cmdq.get()
                line = "%s\t%s\n" % (cid, shlex.join(args))
                try:
                    self.proc.stdin.write(line.encode("utf-8"))
                    self.proc.stdin.flush()
                    self._current = {"id": str(cid), "text": [], "deadline": time.time() + timeout}
                except Exception as e:
                    self.done.emit(-1, "常驻会话写入失败: %s" % e, False)
                    break

            if self._current is not None:
                deadline = self._current.get("deadline")
                if deadline is not None and time.time() > deadline:
                    self._kill_tree()
                    self._flush_current(-1, True)
                    break

        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except Exception:
            pass

