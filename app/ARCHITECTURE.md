# 重构后的目录结构

```
app/
├─ main.py                  入口 + 主窗口 + 动作编排 + 页面状态机
├─ launcher_gui3.py         兼容入口（旧测试 / 旧 spec / 旧命令仍可用）
├─ core/                    业务层（不依赖界面）
│  ├─ config.py             路径、资源定位、数据目录、进程常量
│  ├─ utils.py              hsize / sha256
│  ├─ session.py            mtkclient 日志解析（设备 / 步骤 / 进度 / 分区）
│  ├─ state.py              状态机：未连接 → 连接中 → 已连接 → 操作中
│  ├─ parts.py              97 个分区词典、GPT、读写保护名单
│  ├─ selfcheck.py          12 项启动自检
│  ├─ rescue.py           GPT 原始数据 / 救砖包 / 全局恢复计划
│  ├─ rescue_workers.py   打包 / 校验 / 解压线程
│  ├─ manifest.py           备份/读取的 SHA256 清单
│  ├─ verify.py             后台哈希校验线程
│  ├─ mtk.py                mtkclient 子进程封装（QThread）
│  └─ fastboot.py           fastboot 检测 / 重启
├─ ui/                      视图层
│  ├─ theme.py              设计令牌 + 全局 QSS
│  ├─ dialogs.py            二次确认、文本输入、镜像选择、自检对话框
│  ├─ widgets/
│  │  ├─ card.py            Card / Divider
│  │  ├─ buttons.py         NeonButton / NavButton / IconButton
│  │  ├─ ring.py            ProgressRing
│  │  ├─ steps.py           StepRow / StepTimeline
│  │  ├─ spinner.py         Spinner / PulseDot
│  │  ├─ titlebar.py        TitleBar / Shell
│  │  ├─ toast.py           Toast
│  │  └─ common.py          Metric / Caption / PageHeader
│  └─ pages/
│     ├─ home.py            进度环 + 步骤时间线
│     ├─ partitions.py      分区表（搜索 / 分类过滤）
│     ├─ backup.py          备份进度（表格 + 总进度）
│     ├─ write.py           镜像清单 + 安全规则
│     └─ log.py             原始日志 / 复制 / 打开目录
├─ tests/
│  ├─ gui_suite.py          31 项 GUI 回归（可复用套件）
│  ├─ run_gui_tests.py      命令行跑 31 项
│  ├─ test_gui.py           pytest 入口（也是 31 项）
│  ├─ test_core.py          业务层 23 项单元测试
│  ├─ test_safety.py        16 项安全路径回归
│  ├─ test_full_backup.py   12 项动态全量备份回归
│  ├─ test_rescue.py        15 项救砖包/GPT 回归
│  ├─ test_rescue_ui.py     9 项全局恢复 UI 回归
│  ├─ test_rescue_rebuild.py 8 项 GPT 重建回归
│  ├─ test_pack_ui.py       6 项打包 UI 回归
│  ├─ test_ui_status.py     7 项状态区回归
│  ├─ test_chinese_paths.py  5 项中文路径回归
│  ├─ smoke_runtime.py      真实子进程冒烟测试
│  ├─ shot_ui.py            生成预览图
│  └─ BASELINE.md           重构前后基线记录
├─ _legacy/                 重构前单文件版本（回滚用，不参与打包）
└─ ARCHITECTURE.md
```

## 关键改动

1. **状态机统一**
   `core/state.py` 用一张 `STATE_RULES` 表决定按钮可用性；`MainWindow._apply_state()`
   是唯一入口，不再在每个动作里散落 `setEnabled`。

2. **页面真正拆开**
   主内容改成 `QStackedWidget`：主页 / 分区表 / 备份 / 写入 / 日志。
   旧属性 `step_area`、`part_page`、`backup_page`、`raw` 全部保留为别名，
   所以 31 项回归不需要改断言。

3. **UI 重做**
   炭黑 + 石墨卡片 + 单一青色强调；8px 栅格；标题栏扫光、进度环动画、
   步骤逐条淡入、按钮 hover 辉光、Toast、页面切换。
   2026-11-09 布局调整：右侧上下拆分 —— 上方“当前状态”只显示当前步骤，
   自动跟随解析切换；下方常驻运行日志，左侧操作栏保持不变。

4. **子进程修复**
   源码运行时 `sys.executable` 是 python.exe，旧代码拼成 `python --mtk ...`
   会直接报 “unknown option”。`core/mtk.py` 现在在源码模式显式拼
   `python app/main.py --mtk ...`，冻结模式仍是 `exe --mtk ...`。

5. **兼容层**
   `launcher_gui3.py` 只做 re-export，旧的 `test_gui3.py`、`test_selfcheck.py`、
   `MTK9400GUI3.spec` 都不需要改。

6. **安全加固（2026-11-09）**
   - 备份先写 `.new`，尺寸+SHA256 全过才替换正式目录；旧备份保留 `.old`。
   - 读取先写 `.part`，校验通过才原子改名，并生成 `.sha256`。
   - 写入前校验 GPT 一致性、备份尺寸、备份清单哈希、镜像哈希；
     擦除两道确认；写入/擦除中止和关窗都有危险确认。
   - 校验备份在后台线程算哈希，窗口不卡。
   - 新增“全量备份”：除 userdata 外 96 个分区，约 17.51GB，走同一套 staging/哈希流程。
   详见 `SAFETY.md`。
