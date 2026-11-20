# -*- coding: utf-8 -*-
"""应用状态机。

一张状态表决定“哪些按钮该亮 / 该灭”，避免散落在每个动作里手写 setEnabled。
界面层只负责把按钮注册进来，然后调用 apply()。
"""
from enum import Enum


class AppState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WORKING = "working"

    @property
    def label(self):
        return {
            AppState.DISCONNECTED: "未连接",
            AppState.CONNECTING: "连接中",
            AppState.CONNECTED: "已连接",
            AppState.WORKING: "操作中",
        }[self]


# 每个状态下允许点击的按钮 key。None 表示“全部允许”。
STATE_RULES = {
    AppState.DISCONNECTED: {"connect", "zadig", "env", "verify"},
    AppState.CONNECTING: {"zadig"},
    AppState.CONNECTED: {"zadig", "gpt", "crit", "imp", "read", "write",
                         "erase", "reset", "verify", "env"},
    AppState.WORKING: set(),
}


def allowed(state, keys):
    rule = STATE_RULES.get(state)
    if rule is None:
        rule = set(keys)
    return {k for k in keys if k in rule}


def derive(connected, busy):
    if busy:
        return AppState.WORKING
    return AppState.CONNECTED if connected else AppState.DISCONNECTED


class StateMachine(object):
    """极简观察者：状态变化时通知界面刷新。"""

    def __init__(self):
        self._state = AppState.DISCONNECTED
        self._listeners = []

    @property
    def state(self):
        return self._state

    def subscribe(self, fn):
        self._listeners.append(fn)

    def set(self, state):
        if state is self._state:
            return
        old, self._state = self._state, state
        for fn in list(self._listeners):
            fn(old, state)

    def sync(self, connected, busy):
        self.set(derive(connected, busy))
        return self._state
