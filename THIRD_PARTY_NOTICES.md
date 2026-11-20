# Third-party notices

本工具包含以下第三方组件或与之交互：

- `mtkclient` / `mtk.py`
  - 低位 MTK BROM / Preloader / DA 通信
  - 遵循其原始许可证

- `payload-dumper.exe`
  - 来自 payload-dumper-go
  - GPLv3
  - 用于 OTA `payload.bin` 列表和解包

- `lpunpack.exe` / `lpmake.exe` / `simg2img.exe` / `lpdump.exe`
  - 来自 AOSP / Android 工具链
  - 遵循其原始许可证

- OFP 解密实现
  - 参考 MIT 许可的 OPPO OFP 解密实现

- OPLUS DA / auth / preloader
  - 来自设备资源包
  - 仅用于设备维护

分发本工具时请保留以上说明，并遵守各组件许可证。

`payload-dumper.exe` 为 GPLv3。若将本工具作为闭源商业软件分发，请先确认 GPL 合规方案。
