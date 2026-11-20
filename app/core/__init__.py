# -*- coding: utf-8 -*-
"""core —— 与界面无关的业务层。

模块划分：
    config     运行环境、路径、数据目录、常量
    utils      纯工具函数（体积格式化、哈希）
    session    mtkclient 日志解析（设备信息 / 步骤 / 进度 / 分区）
    state      应用状态机（未连接 → 连接中 → 已连接 → 操作中）
    parts      分区词典、GPT 表、读写保护名单
    selfcheck  启动自检（12 项）
    mtk        mtkclient 子进程封装
    fastboot   fastboot 检测 / 重启
"""
