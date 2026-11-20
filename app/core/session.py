# -*- coding: utf-8 -*-
"""mtkclient 日志解析器。

把原始输出流解析成：设备信息 + 步骤时间线 + 进度 + 分区列表。
纯逻辑，不依赖 Qt，方便单独测试。
"""
import re

RE_DEVICE = re.compile(r"Device detected")
RE_MODE = re.compile(r"Detected (\w+) mode")
RE_CPU = re.compile(r"CPU:\s+(.+?)\s*$")
RE_HWCODE = re.compile(r"HW code:\s+(0x[0-9A-Fa-f]+)")
RE_HWSUB = re.compile(r"HW subcode:\s+(0x[0-9A-Fa-f]+)")
RE_HWVER = re.compile(r"HW Ver:\s+(0x[0-9A-Fa-f]+)")
RE_SWVER = re.compile(r"SW Ver:\s+(0x[0-9A-Fa-f]+)")
RE_SBC = re.compile(r"SBC enabled:\s+(True|False)")
RE_DAA = re.compile(r"DAA enabled:\s+(True|False)")
RE_TARGETCFG = re.compile(r"Target config:\s+(0x[0-9A-Fa-f]+)")
RE_DA1 = re.compile(r"Uploading (?:xflash )?stage 1")
RE_DA1OK = re.compile(r"DA Stage 1 successfully loaded")
RE_JUMP = re.compile(r"Jumping to (0x[0-9A-Fa-f]+)")
RE_HEAP = re.compile(r"HeapBait")
RE_HEAPOK = re.compile(r"Successfully ran DA1 HeapBait")
RE_PATCH = re.compile(r"Patched (.+?)[\.\s]*$")
RE_DA2 = re.compile(r"Uploading stage 2")
RE_DA2OK = re.compile(r"Successfully booted to stage 2")
RE_SLA = re.compile(r"SLA (?:Signature|Key) was (?:not )?accepted")
RE_GPT = re.compile(r"GPT Table:")
RE_DISK = re.compile(r"Total disk size:\s*(0x[0-9A-Fa-f]+)")
RE_TOTAL = re.compile(r"Total disk size:\s*0x[0-9A-Fa-f]+,\s*sectors:\s*(0x[0-9A-Fa-f]+)")
RE_PART = re.compile(r"^(\S+):\s+Offset 0x([0-9A-Fa-f]+),\s+Length 0x([0-9A-Fa-f]+)"
                     r"(?:,\s+Flags 0x([0-9A-Fa-f]+))?"
                     r"(?:,\s+UUID ([0-9A-Fa-f-]+))?"
                     r"(?:,\s+Type (\S+))?")
RE_PCT = re.compile(r"(\d{1,3})\.\d\s*%")
RE_DUMP = re.compile(r"Dumped sector (\d+) with sector count (\d+) as (.+?)\.")
RE_HANDSHAKE_FAIL = re.compile(r"Handshake failed")
RE_DA_FAIL = re.compile(r"Failed to upload da|No valid da loader")
RE_RESET = re.compile(r"Reset command was sent")
RE_WAIT = re.compile(r"Waiting for PreLoader VCOM")
RE_POWEROFF = re.compile(r"Power off the phone")
RE_ERROR = re.compile(r"\[LIB\]: (.+)$")
RE_SAVED = re.compile(r"Successfully (?:saved|wrote)")
RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text):
    """去掉 ANSI 颜色码和控制字符。"""
    text = RE_ANSI.sub("", text)
    text = RE_CTRL.sub("", text)
    return text


STEP_TEMPLATES = {
    "connect": [
        ("handshake", "建立握手", "正在和 preloader 通信。失败通常是没进 preloader 模式，或端口被别的软件占用"),
        ("target", "读取芯片信息", "识别 CPU 型号、硬件代码，确认是 MT6991"),
        ("da1", "上传 DA1", "把第一段下载代理送进芯片内存"),
        ("bypass", "安全绕过", "利用 DA1 漏洞绕开 SBC / SLA 校验，这是 9400 深刷的核心"),
        ("da2", "上传 DA2", "加载打过补丁的 DA2，之后就能自由读写分区"),
        ("sla", "SLA 校验", "验证补丁是否生效，正常会显示 accepted"),
        ("gpt", "读取分区表", "拿到整机 97 个分区的布局"),
    ],
    "read": [
        ("handshake", "建立握手", "正在和 preloader 通信"),
        ("target", "读取芯片信息", "识别 CPU 型号"),
        ("da1", "上传 DA1", "加载第一段下载代理"),
        ("bypass", "安全绕过", "绕开校验"),
        ("da2", "上传 DA2", "加载补丁版 DA2"),
        ("sla", "SLA 校验", "验证补丁"),
        ("read", "读取分区", "把分区内容读出来并写入文件"),
    ],
    "write": [
        ("handshake", "建立握手", "正在和 preloader 通信"),
        ("target", "读取芯片信息", "识别 CPU 型号"),
        ("da1", "上传 DA1", "加载第一段下载代理"),
        ("bypass", "安全绕过", "绕开校验"),
        ("da2", "上传 DA2", "加载补丁版 DA2"),
        ("sla", "SLA 校验", "验证补丁"),
        ("write", "写入分区", "把镜像写进手机。这一步千万不能断电"),
    ],
    "erase": [
        ("handshake", "建立握手", "正在和 preloader 通信"),
        ("target", "读取芯片信息", "识别 CPU 型号"),
        ("da1", "上传 DA1", "加载第一段下载代理"),
        ("bypass", "安全绕过", "绕开校验"),
        ("da2", "上传 DA2", "加载补丁版 DA2"),
        ("sla", "SLA 校验", "验证补丁"),
        ("erase", "擦除分区", "清除指定分区内容"),
    ],
    "reset": [
        ("handshake", "建立握手", "正在和 preloader 通信"),
        ("target", "读取芯片信息", "识别 CPU 型号"),
        ("da1", "上传 DA1", "加载第一段下载代理"),
        ("bypass", "安全绕过", "绕开校验"),
        ("da2", "上传 DA2", "加载补丁版 DA2"),
        ("sla", "SLA 校验", "验证补丁"),
        ("reset", "重启设备", "让手机重新启动"),
    ],
}


class Step(object):
    __slots__ = ("key", "title", "hint", "status", "detail")

    def __init__(self, key, title, hint):
        self.key = key
        self.title = title
        self.hint = hint
        self.status = "pending"   # pending / running / ok / fail / warn
        self.detail = ""

    def __repr__(self):
        return "<%s %s>" % (self.key, self.status)


class Session(object):
    """一次操作的解析状态。"""

    def __init__(self, kind="connect"):
        self.kind = kind
        self.device = {"chip": "", "hwcode": "", "mode": "", "hwver": "", "swver": "",
                       "sbc": "", "daa": "", "disk": "", "target": ""}
        self.steps = [Step(k, t, h) for k, t, h in STEP_TEMPLATES.get(kind, STEP_TEMPLATES["connect"])]
        self.step_map = {s.key: s for s in self.steps}
        self.progress = 0
        self.percent = 0
        self.partitions = []
        self.partition_sizes = {}
        self.partition_meta = {}
        self.total_sectors = 0
        self.disk_size = 0
        self.sector_size = 0
        self._part_seen = set()
        self.partition_count = 0
        self.errors = []
        self.warnings = []
        self.raw_lines = []
        self.current_step = None
        self.finished_ok = False
        self.failed = False
        self._buf = ""
        self._cur = 0
        for s in self.steps:
            s.status = "pending"
        if self.steps:
            self.steps[0].status = "running"
            self.current_step = self.steps[0].key

    # ---------- 内部
    def _step(self, key):
        return self.step_map.get(key)

    def _set(self, key, status, detail=None):
        s = self._step(key)
        if not s:
            return
        s.status = status
        if detail is not None:
            s.detail = detail
        if status == "running":
            self.current_step = key

    def _advance_to(self, key):
        """把 key 之前仍是 running/pending 的步骤标 ok（顺序推进）。"""
        hit = False
        for s in self.steps:
            if s.key == key:
                hit = True
                break
            if s.status in ("running", "pending"):
                s.status = "ok"
        if hit:
            self._set(key, "running")

    # ---------- 主入口
    def feed(self, chunk):
        """喂入一段原始文本（可能被截断），返回本次解析出的事件列表。"""
        events = []
        text = self._buf + clean(chunk).replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        self._buf = lines.pop() if lines else ""
        for line in lines:
            ev = self._line(line)
            if ev:
                events.append(ev)
        return events

    def _line(self, line):
        raw = line.rstrip()
        if not raw.strip():
            return None
        self.raw_lines.append(raw)
        s = raw.strip()

        # 进度百分比
        mp = RE_PCT.search(s)
        if mp:
            try:
                pct = int(mp.group(1))
                if "Upload" in s or "stage 2" in s.lower():
                    self.progress = max(self.progress, pct)
                    self.percent = self.progress
                    return {"type": "progress", "value": pct}
            except Exception:
                pass

        if RE_WAIT.search(s) or RE_POWEROFF.search(s):
            self._advance_to("handshake")
            self._set("handshake", "running", "等待手机进入 preloader…")
            if "手机还没进入 preloader" not in self.warnings:
                self.warnings.append("手机还没进入 preloader：请拔线、关机、再插上")
            return {"type": "waiting"}

        if RE_DEVICE.search(s):
            self._advance_to("handshake")
            self._set("handshake", "ok", "设备已响应")
            return {"type": "step", "key": "handshake", "status": "ok"}

        if RE_HANDSHAKE_FAIL.search(s):
            self._set("handshake", "warn", "握手重试中")
            if "握手失败" not in self.warnings:
                self.warnings.append("握手失败：请确认手机已关机并插好线，端口只存在 7~10 秒")
            return {"type": "warn", "text": "握手重试中"}

        m = RE_MODE.search(s)
        if m:
            self.device["mode"] = m.group(1)
            return {"type": "device", "field": "mode", "value": m.group(1)}

        m = RE_CPU.search(s)
        if m:
            self.device["chip"] = m.group(1).strip()
            self._advance_to("target")
            self._set("target", "ok", self.device["chip"])
            return {"type": "device", "field": "chip", "value": self.device["chip"]}

        m = RE_HWCODE.search(s)
        if m:
            self.device["hwcode"] = m.group(1)
            return {"type": "device", "field": "hwcode", "value": m.group(1)}

        m = RE_HWSUB.search(s)
        if m:
            self.device["hwsub"] = m.group(1)
            return {"type": "device", "field": "hwsub", "value": m.group(1)}

        m = RE_HWVER.search(s)
        if m:
            self.device["hwver"] = m.group(1)
            return {"type": "device", "field": "hwver", "value": m.group(1)}

        m = RE_SWVER.search(s)
        if m:
            self.device["swver"] = m.group(1)
            return {"type": "device", "field": "swver", "value": m.group(1)}

        m = RE_SBC.search(s)
        if m:
            self.device["sbc"] = m.group(1)
            return {"type": "device", "field": "sbc", "value": m.group(1)}

        m = RE_DAA.search(s)
        if m:
            self.device["daa"] = m.group(1)
            return {"type": "device", "field": "daa", "value": m.group(1)}

        m = RE_TARGETCFG.search(s)
        if m:
            self.device["target"] = m.group(1)
            return {"type": "device", "field": "target", "value": m.group(1)}

        if RE_DA1.search(s):
            self._advance_to("da1")
            self._set("da1", "running", "上传中…")
            return {"type": "step", "key": "da1", "status": "running"}

        m = RE_JUMP.search(s)
        if m:
            self._set("da1", "ok", "跳转 %s 成功" % m.group(1))
            return {"type": "step", "key": "da1", "status": "ok"}

        if RE_DA1OK.search(s):
            self._set("da1", "ok", "DA1 已运行")
            return {"type": "step", "key": "da1", "status": "ok"}

        if RE_HEAPOK.search(s):
            self._advance_to("bypass")
            self._set("bypass", "ok", "HeapBait 成功")
            return {"type": "step", "key": "bypass", "status": "ok"}

        if RE_HEAP.search(s):
            self._advance_to("bypass")
            self._set("bypass", "running", "尝试利用 DA1 漏洞…")
            return {"type": "step", "key": "bypass", "status": "running"}

        m = RE_PATCH.search(s)
        if m:
            self._set("bypass", "running", "已打补丁：%s" % m.group(1)[:40])
            return {"type": "patch", "text": m.group(1)[:48]}

        if RE_DA2.search(s):
            self._advance_to("da2")
            self._set("da2", "running", "上传中…")
            self.progress = 0
            return {"type": "step", "key": "da2", "status": "running"}

        if RE_DA2OK.search(s):
            self._set("da2", "ok", "DA2 已加载")
            self.progress = 100
            return {"type": "step", "key": "da2", "status": "ok"}

        if RE_SLA.search(s):
            self._set("sla", "ok", "校验通过")
            return {"type": "step", "key": "sla", "status": "ok"}

        if RE_GPT.search(s):
            self._advance_to("gpt")
            self._set("gpt", "running", "解析中…")
            return {"type": "step", "key": "gpt", "status": "running"}

        m = RE_DISK.search(s)
        if m:
            self.device["disk"] = m.group(1)
            try:
                self.disk_size = int(m.group(1), 16)
            except Exception:
                pass
            mt = RE_TOTAL.search(s)
            if mt:
                try:
                    self.total_sectors = int(mt.group(1), 16)
                    if self.total_sectors:
                        self.sector_size = self.disk_size // self.total_sectors
                except Exception:
                    pass
            return {"type": "device", "field": "disk", "value": m.group(1)}

        m = RE_PART.match(s)
        if m:
            name = m.group(1)
            if name in self._part_seen:
                return None
            self._part_seen.add(name)
            self.partition_count += 1
            try:
                size = int(m.group(3), 16)
            except Exception:
                size = 0
            self.partition_sizes[name] = size
            self.partition_meta[name] = {
                "name": name,
                "offset": int(m.group(2), 16),
                "size": size,
                "flags": int(m.group(4), 16) if m.group(4) else 0,
                "uuid": m.group(5) or "",
                "type": m.group(6) or "",
            }
            if len(self.partitions) < 256:
                self.partitions.append(name)
            self._set("gpt", "running", "已解析 %d 个分区" % self.partition_count)
            return {"type": "partition", "name": name, "count": self.partition_count}

        m = RE_DUMP.search(s)
        if m:
            self._advance_to("read")
            self._set("read", "running", "已写出 %s" % m.group(3)[-40:])
            return {"type": "read", "file": m.group(3)}

        if RE_RESET.search(s):
            self._advance_to("reset")
            self._set("reset", "ok", "已发送重启命令")
            return {"type": "step", "key": "reset", "status": "ok"}

        if RE_DA_FAIL.search(s):
            self.failed = True
            self._set("da1", "fail", "DA 加载失败")
            self.errors.append("DA 加载失败：可能是 DA 文件不匹配或端口已断开")
            return {"type": "error", "text": "DA 加载失败"}

        m = RE_ERROR.search(s)
        if m:
            msg = m.group(1).strip()
            if msg and "Timed out" not in msg:
                self.warnings.append(msg)
            return {"type": "warn", "text": msg}

        return None

    # ---------- 收尾
    def finish(self, rc, timed_out=False):
        """根据退出码整理步骤状态。"""
        if timed_out:
            if self.current_step:
                self._set(self.current_step, "fail", "超时被终止")
            self.failed = True
            return
        if rc != 0:
            if self.current_step:
                self._set(self.current_step, "fail", "异常退出 (exit %s)" % rc)
            self.failed = True
            return
        for s in self.steps:
            if s.status in ("running", "pending"):
                s.status = "ok"
        self.finished_ok = True

    # ---------- 展示用
    def step_rows(self):
        return [{"key": s.key, "title": s.title, "hint": s.hint,
                 "status": s.status, "detail": s.detail} for s in self.steps]

    def summary(self):
        d = self.device
        bits = []
        if d.get("chip"):
            bits.append(d["chip"])
        if d.get("hwcode"):
            bits.append("HW " + d["hwcode"])
        if d.get("mode"):
            bits.append(d["mode"] + " 模式")
        return " · ".join(bits)


# 兼容上次目录结构里“session.py 管连接状态”的约定；
# 状态机实现单独放在 core/state.py，便于无 Qt 单测。
from .state import AppState, StateMachine  # noqa: E402,F401

__all__ = ["Step", "Session", "STEP_TEMPLATES", "clean", "AppState", "StateMachine"]
