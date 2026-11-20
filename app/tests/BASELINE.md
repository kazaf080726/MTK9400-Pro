# 基线记录

## 重构前（原始单文件 launcher_gui3.py）

命令：

```powershell
cd D:\Users\Administrator\Desktop\mtkclient\app
$env:QT_QPA_PLATFORM = "offscreen"
D:\Users\Administrator\Desktop\mtkclient\python.exe test_gui3.py
```

结果（原始输出见 `app/baseline_gui3.txt`）：

```
TOTAL 31  PASS=31  FAIL=0
```

## 重构后

同一套 31 项检查迁移到 `tests/gui_suite.py`，分别对两个入口各跑一遍：

```powershell
# 新入口 app/main.py
python tests/run_gui_tests.py
# 旧入口 app/launcher_gui3.py（兼容层）
python test_gui3.py
```

两次结果都必须是：

```
TOTAL 31  PASS=31  FAIL=0
```

另外：

```powershell
python test_selfcheck.py     # 16 项自检单测
python tests/test_safety.py  # 16 项安全路径回归
python tests/test_full_backup.py  # 12 项动态全量备份回归
python tests/test_ui_status.py  # 7 项状态区回归
python tests/test_rescue.py  # 15 项救砖包回归
python tests/test_rescue_ui.py  # 9 项全局恢复 UI 回归
python tests/test_rescue_rebuild.py  # 8 项 GPT 重建回归
python tests/test_pack_ui.py  # 6 项打包 UI 回归
python tests/test_pack_legacy.py  # 5 项旧备份补 GPT 回归
python tests/test_chinese_paths.py  # 5 项中文路径回归
python tests/test_core.py    # 23 项业务层单测
python main.py --selftest    # 12 项资源自检
```

## 31 项覆盖范围

| # | 检查 |
|---|---|
| 01–02 | 按钮尺寸 / 不重叠 |
| 03–07 | 连接、按钮状态、设备信息 |
| 08–08d | 读分区表、解锁、忙碌态、页面切换 |
| 09–10 | 关键 / 重要备份脚本 |
| 11–16 | 读、写、禁写、无备份拒绝、擦除、禁擦除 |
| 17–18d | 重启、断开、按钮恢复、页面回主页 |
| 19–20 | 校验 / 环境检查不调用 mtk |
| 21 | 六步全部 ok |
| 22–25 | 日志无 ANSI / 无替换符 / 中文正常 |
| 26–27 | 中止按钮 |
| 28 | 未连接拦截 |
