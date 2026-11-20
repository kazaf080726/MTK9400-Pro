# -*- coding: utf-8 -*-
"""启动自检：12 项（8 个内置资源 + 4 个运行环境检查）。"""
import os
import shutil

from . import config
from . import parts
from .utils import hsize, sha256_file

# 期望的内置资源（大小, SHA256, 是否关键）。测试会临时改这个列表，所以保持可变。
EXPECT = [
    ("loader", "下载代理 DA", config.LOADER,
     1373364, "86d986c67c8fcc7bc35322214913837053c405e17f3dd604c8b0e1c25858c522", True),
    ("auth", "认证文件 auth", config.AUTH,
     2272, "747b4da7888fe592d22f32d76236f349e5b6b2fa7b442a5653f60209903f0e3f", True),
    ("heapbait", "安全绕过载荷", config.HEAPBAIT,
     4088, "10a329123f0893ace0d343d813eb035f722fc816b06f2b1e4a56cfa5c205b4bb", True),
    ("libusb", "USB 驱动库", config.LIBUSB,
     166912, "6b24b0ee1a59cbae385dd15b06eddf2c72b2ff3a875ae279883a880136c59ec8", True),
    ("winfsp", "文件系统库", config.WINFSP,
     197920, "ea3cf26f4958e26126882ec7addd6f89c1430ba9371e3c5109240bee511d6f54", False),
    ("gpt", "分区表清单", config.GPT_FILE,
     1812, "929fbb71f39009a624da334de5be686282db94a8013576a21790d5501fdfe0fa", True),
    ("fastboot", "fastboot 工具", config.FB_EXE, 0, None, False),
    ("zadig", "驱动安装工具", config.ZADIG, 0, None, False),
]


def run_selfcheck():
    """返回 [(key, 标题, 状态, 说明, 是否关键)]，状态 ok / fail / warn。"""
    out = []
    for key, label, path, size, digest, critical in EXPECT:
        try:
            if not os.path.exists(path):
                out.append((key, label, "fail", "文件缺失", critical))
                continue
            real = os.path.getsize(path)
            if size <= 0:
                out.append((key, label, "ok", hsize(real), critical))
                continue
            if real != size:
                out.append((key, label, "fail", "大小不符 %d/%d" % (real, size), critical))
                continue
            if digest and sha256_file(path) != digest:
                out.append((key, label, "fail", "校验和不对（文件被改动）", critical))
                continue
            out.append((key, label, "ok", hsize(size), critical))
        except Exception as e:
            out.append((key, label, "fail", "读取失败 %s" % str(e)[:24], critical))

    # 运行环境
    try:
        testf = os.path.join(config.WORK, ".write_test")
        with open(testf, "w") as f:
            f.write("ok")
        os.remove(testf)
        out.append(("workdir", "数据目录可写", "ok", "正常", True))
    except Exception:
        out.append(("workdir", "数据目录可写", "fail", "无写权限", True))

    try:
        free = shutil.disk_usage(config.BASE).free
        if free < 2 * 1024 ** 3:
            out.append(("disk", "磁盘剩余空间", "warn", hsize(free), False))
        else:
            out.append(("disk", "磁盘剩余空间", "ok", hsize(free), False))
    except Exception:
        out.append(("disk", "磁盘剩余空间", "warn", "无法读取", False))

    if len(parts.GPT) >= 90:
        out.append(("gptload", "分区表已加载", "ok", "%d 个分区" % len(parts.GPT), True))
    else:
        out.append(("gptload", "分区表已加载", "fail", "只有 %d 个" % len(parts.GPT), True))

    mod_ok = False
    try:
        import importlib.util as _iu
        mod_ok = (_iu.find_spec("mtk") is not None) and (_iu.find_spec("mtkclient") is not None)
    except Exception:
        mod_ok = False
    if not mod_ok:
        mod_ok = (os.path.exists(config.find_res("mtk.py")) and
                  os.path.exists(config.find_res(os.path.join("mtkclient", "__init__.py"))))
    if mod_ok:
        out.append(("mtkmod", "mtkclient 程序", "ok", "已打包", True))
    else:
        out.append(("mtkmod", "mtkclient 程序", "fail", "缺少 mtk 模块", True))

    return out


def summarize(results):
    """给 --selftest 用的文本明细。"""
    lines = []
    for key, label, status, detail, _critical in results:
        lines.append("%-10s %-5s %s" % (key, status.upper(), detail))
    # 兼容旧的测试矩阵：明确给出分区数量和 loader 的字节数 + 哈希
    loader = config.LOADER
    try:
        size = os.path.getsize(loader)
        digest = sha256_file(loader)
    except Exception:
        size, digest = 0, "0" * 64
    lines.append("gpt parts : %d" % len(parts.GPT))
    lines.append("loader %d %s" % (size, digest))
    fails = sum(1 for r in results if r[2] == "fail")
    lines.append("RESULT : %s" % ("OK" if fails == 0 else "FAIL %d" % fails))
    return lines
