# 重构验收报告

日期：2026-11-09
工程：`D:\Users\Administrator\Desktop\mtkclient\app`

## 1. 重构前基线

| 套件 | 结果 |
|---|---|
| `test_gui3.py`（原始 31 项） | **31 / 31 PASS** |
| 原始输出 | `baseline_gui3.txt` |

## 2. 重构后回归

| 套件 | 结果 | 输出 |
|---|---|---|
| `tests/run_gui_tests.py`（新入口 `main.py`，31 项） | **31 / 31 PASS** | `tests/output_gui_new.txt` |
| `test_gui3.py`（旧入口 `launcher_gui3.py` 兼容层，31 项） | **31 / 31 PASS** | `tests/output_gui_legacy.txt` |
| `test_selfcheck.py`（自检单测 16 项） | **16 / 16 PASS** | `tests/output_selfcheck.txt` |
| `tests/test_core.py`（业务层 23 项） | **23 / 23 PASS** | `tests/output_core.txt` |
| `tests/test_safety.py`（安全路径 16 项） | **16 / 16 PASS** | 运行输出 |
| `tests/test_full_backup.py`（全量备份 12 项） | **12 / 12 PASS** | 运行输出 |
| `tests/test_ui_status.py`（状态区 7 项） | **7 / 7 PASS** | 运行输出 |
| `tests/test_chinese_paths.py`（中文路径 5 项） | **5 / 5 PASS** | 运行输出 |
| `tests/test_rescue.py`（救砖包核心 15 项） | **15 / 15 PASS** | 运行输出 |
| `tests/test_rescue_ui.py`（救砖流程 9 项） | **9 / 9 PASS** | 运行输出 |
| `tests/test_rescue_rebuild.py`（GPT 重建 8 项） | **8 / 8 PASS** | 运行输出 |
| `tests/test_pack_ui.py`（打包 UI 6 项） | **6 / 6 PASS** | 运行输出 |
| `tests/test_pack_legacy.py`（旧备份补 GPT 5 项） | **5 / 5 PASS** | 运行输出 |
| `main.py --selftest`（12 项资源自检） | **RESULT : OK** | `tests/output_selftest.txt` |
| 冻结版 exe `--selftest` | **exit 0 / RESULT : OK** | `tests/output_frozen_selftest.txt` |
| 实际备份 SHA256 校验 | **18/18、81/81、18/18 全部正确** | `AUDIT_REPORT.md` |
| `tests/smoke_runtime.py`（真实子进程） | **OK** | `tests/output_smoke.txt` |

## 3. 交付物

- 源代码：`app/main.py` + `app/core/` + `app/ui/` + `app/tests/`
- 兼容入口：`app/launcher_gui3.py`
- 单文件 exe：`app/gui3_dist/MTK9400GUI3.exe`（60.67 MB）
- 桌面部署：`D:\Users\Administrator\Desktop\Win版本MTK深刷(9400-9400+).exe`
- 回滚源码：`app/_legacy/launcher_gui3_monolith.py`
- 架构说明：`app/ARCHITECTURE.md`
- 基线说明：`app/tests/BASELINE.md`

## 4. 关键修复

源码模式运行时，旧代码把子进程拼成 `python.exe --mtk ...`，会触发
“unknown option” 并返回 2。`core/mtk.py` 现在区分：

```python
# 源码
[sys.executable, app/main.py, "--mtk", ...]
# 冻结
[sys.executable, "--mtk", ...]
```

`tests/smoke_runtime.py` 真实启动了一次 mtkclient 子进程并验证
`rc=0`、输出完整、`busy=False`。

## 5. 2026-11-09 03:04 备份未落盘事故

- 现象：日志里每个分区都出现
  `Writer thread exception: [Errno 2] No such file or directory: 'backup_critical\\xxx.bin'`；
  界面却显示完成。
- 原因：`core/config.py` 导入时 `os.chdir(BASE)`，把 `MtkWorker` 子进程的 cwd 从
  `MTK9400_Data` 改成 exe 目录；备份脚本使用相对路径，父目录不存在。
- 修复：移除 `os.chdir(BASE)`；`MtkWorker` 固定 `cwd=WORK`；备份完成后逐文件核对，
  缺失或写入线程报错时明确弹窗“备份不完整”。
- 数据：旧备份 `mtkclient\backup_critical`（18）、`backup_important`（81）、
  `rescue`（18）完整，已复制到 `Desktop\MTK9400_Data\` 下，尺寸全部匹配。
- 回归：`tests/test_core.py` 新增 21–23 三项路径测试。

## 6. 2026-11-09 安全整改

- 备份改为 `.new` 暂存 + 尺寸/SHA256 校验通过后才替换正式目录，旧备份保留 `.old`。
- 读取改为 `.part` 暂存 + 校验 + 原子改名，生成 `.bin.sha256`。
- 写入前校验设备 GPT、备份尺寸、备份清单哈希、镜像哈希；擦除两道确认；
  写入/擦除中止与关窗危险确认；单实例锁。
- “校验备份”改为后台线程逐文件 SHA256；首次无清单时生成清单并明确提示。
- 新增 `tests/test_safety.py` 16 项安全路径回归；`test_core.py` 扩到 23 项。
- 详见 `AUDIT_REPORT.md`、`SAFETY.md`。
