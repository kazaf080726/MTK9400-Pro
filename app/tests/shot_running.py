import os
import sys
import time

os.environ.pop("QT_QPA_PLATFORM", None)
APP = r"D:\Users\Administrator\Desktop\mtkclient\app"
sys.path.insert(0, APP)

import main as g  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SAMPLE = (
    "Preloader - Status: Waiting for PreLoader VCOM\n"
    "Port - Device detected :)\n"
    "Preloader - Detected regular mode !\n"
    "Preloader - \tCPU:\t\t\tMT6991(Dimensity 9400 Ultra)\n"
    "Preloader - HW code:\t\t\t0x1357\n"
    "Uploading stage 1\n"
    "Jumping to 0x100000\n"
    "DA Stage 1 successfully loaded\n"
    "HeapBait - Successfully ran DA1 HeapBait\n"
    "XmlFlashExt - Patched CUSTOM command\n"
    "Uploading stage 2\n"
    "Progress: |████| 62.0% Upload: 0.8 MB/s\n"
)

app = QApplication([])
app.setStyle("Fusion")
w = g.MainWindow()
w.resize(1180, 780)
w.show()
for _ in range(8):
    app.processEvents()
    time.sleep(0.04)
w.new_session("connect")
for i in range(0, len(SAMPLE), 80):
    w.on_stream(SAMPLE[i:i + 80])
w._update_steps()
w.connected = True
w.set_pill("连接中…", "#35d0e0", True)
w.ring.set_indeterminate(True, "#35d0e0")
w.ring.set_text("上传 DA2", "62%")
w.ring_cap.setText("正在上传第二阶段引导")
w.status.setText("连接并读取分区表 · 进行中")
w.status.setStyleSheet("color:#35d0e0;font-size:10px;")
for _ in range(12):
    app.processEvents()
    time.sleep(0.04)
out = os.path.join(APP, "home_running_preview.png")
w.grab().save(out)
print("saved", out)
sys.stdout.flush()
os._exit(0)
