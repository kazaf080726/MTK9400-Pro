# MTK9400 Pro 完整使用说明

版本：v1.0.0
适用：MediaTek MT6991 / MT9400，Windows 10/11 x64
项目：https://github.com/kazaf080726/MTK9400-Pro

---

## 0. 先看这几条

1. 这是社区工具，不是 OPPO / 一加 / MediaTek 官方工具。
2. 只用于自己拥有或获授权的设备。
3. 刷机、写 GPT、擦除都可能变砖或丢数据。
4. 刷前必须备份 nvram / nvdata / persist / proinfo / seccfg / frp / misc。
5. GPT 重建和 raw 刷写是最后手段，能不用就不用。
6. 没有真实手机写后回归测试，第一次操作请先只读。

---

## 1. 准备

### 1.1 电脑

```text
Windows 10/11 x64
管理员权限
USB 2.0/3.0 数据线
剩余空间：至少 20 GB
关闭杀毒软件的实时拦截（如果误报）
```

不要用只有充电功能的线，不要用劣质 HUB。

### 1.2 工具

Release 下载：

```text
https://github.com/kazaf080726/MTK9400-Pro/releases/tag/v1.0.0
```

文件：

```text
MTK9400Pro.exe
```

校验：

```text
SHA256 20073DE4080052BD10997648C5A11CDDBF026E84D99714C2155E1F2BA6103340
```

### 1.3 资源包

资源包需要包含与机型匹配的：

```text
Config.xml
DA/...
PreLoader/...
```

在工具顶部：

```text
选择设备 / 资源 / 配置
```

选中资源包，再选择品牌 / 系列 / 机型。

资源包不匹配会导致：

- DA 握手失败
- 写错 preloader
- 设备无法启动

### 1.4 驱动

优先使用 COM：

```text
MediaTek USB Port / Preloader COM
```

如果只能用 WinUSB：

- 用 Zadig 把 Preloader 的 CDC 数据接口绑定到 WinUSB
- 绑定后不要同时再让 COM 驱动占用同一个接口

COM 能用就优先 COM，WinUSB 在部分机器上仍会出现 Pipe error。

---

## 2. 进入 Preloader / BROM

不同机型按键不同，常见方式：

```text
关机
按住音量键/电源键组合
插 USB
工具检测到新 COM 或 MTK 设备
```

也可以在工具里点“读信息 / 读分区表”，然后按提示让手机进入 Preloader。

如果设备完全无反应：

- 尝试 BROM 模式
- 尝试短接测试点
- 检查数据线和驱动

不要在没有确认模式的情况下反复插拔几十次。

---

## 3. 连接模式

工具顶部：

```text
自动（优先 COM）
仅 WinUSB
仅 COM
```

建议：

```text
日常：自动（优先 COM）
COM 不稳定：仅 COM
WinUSB 已正确绑定：仅 WinUSB
```

端口栏：

```text
WinUSB（不使用 COM）
COMx ...
```

如果看不到端口：

1. 点“刷新”
2. 重新插拔
3. 检查设备管理器
4. 检查驱动是否被系统占用

---

## 4. 第一次连接：只读检查

打开工具后，先做只读操作。

### 4.1 读信息 / 分区表

点：

```text
读信息 / 读分区表
```

成功后应看到：

- 机型/平台
- 磁盘容量
- 扇区大小
- 分区表
- 每个分区的起始地址、大小、文件名

如果失败：

```text
没有拿到有效分区表
```

先排查：

- 资源包
- 连接模式
- 驱动
- Preloader/DA
- GPT 是否已损坏

### 4.2 确认分区表

重点确认：

```text
super
boot_a / boot_b
init_boot_a / init_boot_b
vendor_boot_a / vendor_boot_b
dtbo_a / dtbo_b
vbmeta_a / vbmeta_b
lk_a / lk_b
modem_a / modem_b
nvram
nvdata
persist
```

不同机型分区名可能略有差异。

---

## 5. MTK 页面基本操作

### 5.1 读取分区

1. 选中分区
2. 点“回读（已选）”
3. 选择保存目录
4. 等待完成

保存的是 raw 分区镜像，不是文件系统压缩包。

### 5.2 写入分区

前提：已经有正确镜像，且分区表可读。

1. 选中目标分区
2. 点“刷入（已选）”
3. 选择镜像
4. 确认大小不超过分区
5. 开始

不要写：

```text
preloader
nvram
nvdata
persist
proinfo
seccfg
frp
misc
```

除非你非常清楚后果。

### 5.3 擦除

```text
快速擦除 / 安全擦除
```

一般只擦：

```text
userdata
metadata
cache
```

不要擦 GPT、preloader、nvram、persist。

### 5.4 自定义地址

高级功能：

```text
读自定义地址
写自定义地址
```

格式：

```text
偏移（字节或 0x）
长度
文件
```

写错偏移会直接破坏分区表或其他数据。只读调试时使用。

### 5.5 其他

```text
导出 Preloader
读取 RPMB
槽位查看 / 设为 A / 设为 B
vbmeta 修补
ODM 解锁
恢复出厂设置
重启 / 关机 / Fastboot
```

槽位切换会写 misc，操作前确认当前槽位。

---

## 6. 备份 / 恢复

打开：

```text
备份 / 恢复
```

### 6.1 选择关键分区

点：

```text
选择关键分区
```

会选中：

```text
nvram
nvdata
persist
proinfo
seccfg
frp
misc
boot
```

建议全选关键组。

### 6.2 开始备份

1. 选保存目录
2. 点“开始备份”
3. 等待每个分区完成

输出目录：

```text
Backup_YYYYMMDD_HHMMSS/
  manifest.json
  boot_a.bin
  nvram.bin
  ...
  gpt/
    pgpt.bin
    sgpt.bin
    gpt.json
```

manifest 记录：

```text
机型
平台
扇区大小
总扇区
磁盘大小
磁盘 GUID
每个分区的 SHA256
起始 LBA
```

如果当前 GPT 可读，工具会尽量附带 GPT。

### 6.3 恢复备份

1. 点“恢复备份”
2. 选择 Backup 目录
3. 选择分组
4. 确认

GPT 可读时：

```text
w 分区名 文件
```

GPT 不可读时：

```text
wo 起始LBA * 扇区大小 长度 文件
```

第二种不依赖分区名，但要求 manifest 里的 LBA 正确。

### 6.4 恢复前检查

恢复前会校验：

- manifest
- 文件 SHA256
- 扇区大小
- 容量
- 磁盘 GUID（如果有）

不一致会拒绝。

---

## 7. GPT 分区表

GPT 是最高风险区域。

### 7.1 备份 GPT

```text
GPT 分区表 → 备份 GPT
```

生成：

```text
GPT_YYYYMMDD_HHMMSS/
  pgpt.bin
  sgpt.bin
  gpt.json
```

### 7.2 校验 GPT

```text
校验 GPT
```

检查：

- 保护 MBR
- 主/备 GPT 头
- CRC
- 分区表
- 分区重叠
- 容量/扇区

### 7.3 恢复 GPT

```text
恢复 GPT / 刷写分区表
```

流程：

```text
选择备份目录
→ 校验备份
→ 读当前 GPT（可选）
→ 对比容量/扇区/GUID
→ 写备份 GPT
→ 写主 GPT
→ 读回校验
```

如果当前 GPT 已经读不到：

- 工具会让你手动输入磁盘总字节数
- 选择 512 或 4096 扇区
- 跳过当前 GUID 对比
- 仍然做写后读回校验

### 7.4 从 Scatter 重建 GPT

```text
从 Scatter 重建 GPT
```

要求：

```text
完整 scatter
必须包含 pgpt / sgpt
```

不能使用只包含“有镜像分区”的简化 scatter。

流程：

```text
选择完整 scatter
→ 输入磁盘容量
→ 选择扇区
→ 生成 PGPT/SGPT
→ 保存当前 GPT 为 pre_rebuild_*
→ 写备份 GPT
→ 写主 GPT
→ 读回校验
```

注意：

- 生成的分区类型是 EFI Basic Data
- 唯一 GUID 是随机生成
- 不保留原厂属性
- 不是原厂 GPT 逐字节复制
- 能恢复原厂备份就不要用重建

### 7.5 GPT 丢失后的正确顺序

```text
1. 先恢复/重建 GPT
2. 确认 printgpt 能读
3. 再刷 super 和物理分区
```

只刷 super，不恢复 GPT，设备仍然不能启动。

---

## 8. 深度刷机

打开：

```text
深度刷机
```

支持：

```text
scatter 目录
ZIP（scatter 或 payload.bin）
OFP
payload.bin
包含 super 的目录
```

### 8.1 选择固件

- 目录：选择包含 scatter.txt 的目录
- ZIP/OFP：选择文件
- 解析固件

解析在后台线程执行，不会卡住主界面。

### 8.2 刷机模式

```text
系统修复（不碰 preloader/NVRAM）
全量固件（不含 preloader）
专家模式（含 preloader/关键分区）
```

推荐：

```text
系统修复
```

不要随便用专家模式。

### 8.3 自动备份

默认勾选：

```text
刷前自动备份关键分区
```

会备份：

```text
critical + boot
```

如果 GPT 不可读，普通模式会拒绝，raw 模式也不会偷偷跳过。

### 8.4 选择分区

默认会选：

```text
boot
super
system 相关物理分区
modem
```

确认：

- 不要选逻辑分区
- 不要选 preloader
- 不要选 nvram/nvdata/persist
- 不要选 misc

### 8.5 逻辑分区

payload/OFP/super 里的：

```text
system
vendor
product
odm
system_ext
system_dlkm
vendor_dlkm
odm_dlkm
my_*
```

是 super 内部逻辑分区，不能直接 `w`。

必须先做：

```text
lpmake 生成 super.img
```

再刷 `super` 物理分区。

### 8.6 无 GPT 原地址刷写

勾选：

```text
无 GPT：按 scatter 原地址写入
```

写入方式：

```text
wo scatter偏移 长度 文件
```

不会创建 GPT。

正确顺序：

```text
先重建 GPT
→ 再 raw 刷写
```

如果 raw 模式勾选自动备份但 GPT 不可读，会直接拒绝。

### 8.7 开始刷机

点：

```text
开始刷机
```

进度显示：

```text
深度刷机 4/27 · super · 13.67 GB
```

完成后检查日志，不要立刻拔线。

### 8.8 刷完

如果需要清数据：

```text
userdata
metadata
cache
```

不要清：

```text
nvram
nvdata
persist
proinfo
seccfg
frp
misc
```

如果是 A/B 机型，且 super 只有 `_a`：

```text
槽位功能 → 设为 A
```

或 Fastboot：

```text
fastboot set_active a
```

然后重启。

第一次开机可能 5 到 15 分钟，不要反复断电。

---

## 9. super / lpmake

### 9.1 解包 super

```text
解包 super / lpmake
```

选择 super.img，输出逻辑分区镜像。

### 9.2 查看

```text
lpdump
```

确认：

- block size
- alignment
- metadata slots
- virtual A/B
- group
- 每个分区大小

### 9.3 打包

必须匹配目标：

```text
device-size
metadata-size
metadata-slots
block-size
alignment
virtual-ab
groups
```

参数不对，刷进去也可能不启动。

### 9.4 sparse

```text
sparse → raw
```

用于把 Android sparse 镜像展开成 raw。

---

## 10. OFP / payload

### 10.1 OFP

选择 `.ofp` 文件，工具会解密并提取镜像。

注意：

- 新机型可能换密钥
- 解包前确认磁盘空间
- 解出的逻辑分区不能直接写

### 10.2 payload.bin

选择 OTA ZIP 或 payload.bin。

工具会：

```text
列出分区
→ 选中后才解包
```

解包在后台线程执行。

---

## 11. 重启 / 断开

### 正常重启

```text
重启 → 重启设备
```

设备会立即断开 USB。

日志出现：

```text
Pipe error
xread: Wrong length
Error on sending reboot
```

不是失败，是设备先断开。看到：

```text
Reset command was sent
```

就说明命令已发出。

### 正常断开

刷写完成后：

1. 等待日志停止
2. 关闭工具
3. 拔线
4. 再开机

不要在写入过程中拔线。

---

## 12. 常见问题

### 12.1 看不到端口

- 换数据线
- 换 USB 口
- 重装 MTK 驱动
- 检查设备管理器
- 点“刷新”
- 确认手机在 Preloader/BROM

### 12.2 DA 握手失败

- 资源包不匹配
- auth 不匹配
- 端口被占用
- 杀毒软件拦截
- 换 COM 模式

### 12.3 WinUSB Pipe error

- 驱动绑定问题
- 同一个接口被 COM 占用
- 改用 COM
- 重新用 Zadig 绑定

### 12.4 读不到 GPT

- GPT 已损坏
- 先尝试 GPT 备份恢复
- 没有备份就找同机型完整 scatter
- 不要直接刷 super 就重启

### 12.5 分区表里没有某个分区

- 固件和机型不匹配
- scatter 不完整
- GPT 不完整

### 12.6 刷完不开机

检查：

```text
GPT 是否恢复
super 是否写入正确
槽位是否 A
userdata/metadata 是否要清
vbmeta 是否匹配
```

不要连续重刷十几次。

### 12.7 磁盘空间不足

payload/OFP/super 解包会占大量空间。

至少预留 20 GB。

### 12.8 工具被拦截

未签名 exe 可能被 SmartScreen/杀毒误报。

核对 SHA256，确认来源后再放行。

---

## 13. 安全清单

刷前：

```text
[ ] 电量 > 50%
[ ] 原装/可靠数据线
[ ] 资源包匹配
[ ] 已备份 nvram/nvdata/persist
[ ] 已备份 GPT
[ ] 已确认机型/容量/扇区
[ ] 已确认固件匹配
```

刷后：

```text
[ ] 日志无失败
[ ] GPT 可读
[ ] 关键分区存在
[ ] 槽位正确
[ ] 再重启
```

---

## 14. 不要做的事

```text
不要写错机型的 preloader
不要用简化 scatter 重建 GPT
不要在 GPT 不可读时直接刷 super 后重启
不要把逻辑分区当物理分区写
不要擦 nvram/nvdata/persist
不要在用别人机器的备份恢复自己的 IMEI/校准
不要在写入过程中拔线
```

---

## 15. 版本与链接

源码：

```text
https://github.com/kazaf080726/MTK9400-Pro
```

Release：

```text
https://github.com/kazaf080726/MTK9400-Pro/releases/tag/v1.0.0
```

exe SHA256：

```text
20073DE4080052BD10997648C5A11CDDBF026E84D99714C2155E1F2BA6103340
```

许可证：

```text
GPL-3.0
```

第三方：

```text
payload-dumper-go: GPLv3
AOSP lp tools: Apache/AOSP
Qt/PySide6: LGPLv3
```

---

## 16. 最后

这个工具的目标是“可控地维护自己的设备”，不是“一键救所有砖”。

遇到不确定的分区、容量、GUID、槽位，先停下来备份日志，不要凭感觉继续写。

设备有价，数据无价。
