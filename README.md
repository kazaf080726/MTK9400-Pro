# MTK9400 Pro

面向 MediaTek MT6991 / MT9400（OPPO / OnePlus 等机型）的 Windows 图形化维护工具。

本项目是社区维护版本，不是 OPPO、OnePlus、MediaTek 官方工具。

> 重要：刷机、写 GPT、写分区、擦除都有风险。请先备份 nvram / nvdata / persist / proinfo / seccfg / frp / misc。作者不对变砖、数据丢失、IMEI 或校准丢失负责。

---

## 下载

GitHub Release：

https://github.com/kazaf080726/MTK9400-Pro/releases/tag/v1.0.0

Release 只包含工具本体，不包含固件、资源包、救砖包或用户数据。

## 功能

- COM / WinUSB 两种连接模式
- Preloader / BROM / DA 连接
- 读取设备信息、GPT、分区表
- 分区读取 / 写入 / 擦除
- GPT 备份、校验、恢复
- 从完整 scatter 生成并写入 GPT
- 无 GPT 时的 raw 绝对地址写入
- 备份 manifest、SHA256、关键分区分组
- 深度刷机：scatter / ZIP / OFP / payload / super
- payload.bin 解包
- OFP 解密
- lpunpack / lpmake / simg2img
- Android sparse 展开
- 槽位 / vbmeta / ODM / Fastboot 辅助

## 不包含

本仓库**不包含**：

```text
官方固件
救砖包
super.img
pgpt.bin / sgpt.bin
nvram / nvdata / persist
IMEI / 校准数据
OPLUS 资源包
payload-dumper.exe / lpmake.exe 等第三方二进制
platform-tools
```

运行前需要自行准备：

- 与机型匹配的资源包（DA / Preloader / auth）
- `app/tools`：payload-dumper、lpunpack、lpmake、simg2img、lpdump
- `app/platform-tools`：adb、fastboot
- 目标机型的完整 scatter 或 GPT 备份

## 构建

见 [docs/BUILD.md](docs/BUILD.md)。

```powershell
cd app
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name MTK9400Pro --icon icon.ico `
  --paths .. --paths . `
  --add-data "..\mtkclient\Loader\OPLUS_DA_mt6991.bin;mtkclient\Loader" `
  --add-data "..\mtkclient\Loader\OPLUS_mt6991.auth;mtkclient\Loader" `
  --add-data "..\mtkclient\payloads;mtkclient\payloads" `
  --add-data "..\mtkclient\Windows;mtkclient\Windows" `
  --add-data "..\mtkclient\Library\Filesystem\bin;mtkclient\Library\Filesystem\bin" `
  --add-data "icon.ico;." `
  --add-data "platform-tools;platform-tools" `
  --add-data "tools;tools" `
  launcher_v2.py
```

## 测试

```powershell
cd app
python -m unittest discover -s tests -p "test_v2_*.py"
```

预期：

```text
27 tests OK
```

## 架构

见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

核心入口：

```text
app/launcher_v2.py
app/v2/main.py
app/v2/gpt.py
app/v2/backup.py
app/v2/firmware.py
app/v2/flash_page.py
```

## 安全边界

- 所有外部路径都经过 `app/v2/paths.py`
- ZIP 拒绝路径穿越和符号链接
- sparse / OFP 有 64 GB 上限
- GPT 写入先写备份、再写主表、再读回
- raw 模式必须备份或显式确认
- 不自动写 nvram / nvdata / persist

详见 [docs/SECURITY.md](docs/SECURITY.md)。

## 已知限制

- 仓库不含完整 GPT/scatter；GPT 丢失时不能只靠本仓库恢复
- GPT 重建使用 EFI Basic Data 和随机 GUID，不是原厂逐字节复制
- 没有真实手机写后回归
- 普通分区写入后没有逐分区读回
- 固件没有强制 SHA256

详见 [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)。

## 许可证

GNU General Public License v3.0。

本项目基于 [bkerler/mtkclient](https://github.com/bkerler/mtkclient) 和社区资料。

第三方组件：

- payload-dumper-go：GPLv3
- AOSP lp 工具：Apache / AOSP 许可
- Qt / PySide6：LGPLv3
- OPLUS DA/auth：来自设备资源包，仅用于设备维护

完整说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 免责声明

本工具仅用于**自己拥有或获授权的设备**的维护、备份和恢复。

不得用于绕过他人设备的安全机制、盗取数据或非法维修。

使用即表示你理解并承担全部风险。
