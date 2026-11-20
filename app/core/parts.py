# -*- coding: utf-8 -*-
"""分区词典、GPT 表和读写保护名单。"""
import os
import shutil

from . import config

# 名称: (中文名, 一句话说明, 分类)
DESC = {
    "misc": ("启动标志", "记录进恢复模式、进 fastboot 等状态，刷机工具常用", "系统"),
    "vb": ("启动状态", "记录上次启动是否正常、有没有被篡改", "系统"),
    "para": ("启动参数", "保存上一次启动的参数和日志", "系统"),
    "oplusreserve1": ("厂商预留 1", "OPPO/一加预留，系统更新与恢复使用", "预留"),
    "oplusreserve2": ("厂商预留 2", "同上，容量较大（256MB）", "预留"),
    "oplusreserve3": ("厂商预留 3", "同上", "预留"),
    "oplus_custom": ("厂商定制", "机型定制数据，不同机型内容不同", "预留"),
    "expdb": ("异常日志", "系统崩溃时记录的调试信息", "日志"),
    "frp": ("恢复出厂保护", "防止恢复出厂后被账号锁住", "安全"),
    "nvcfg": ("基带配置", "信号相关的配置文件，丢了可能没信号", "基带"),
    "nvdata": ("基带数据", "IMEI 等关键数据，丢了没信号", "基带"),
    "md_sec": ("基带安全", "基带加密与安全数据", "基带"),
    "persist": ("传感器校准", "指纹、传感器、屏幕校准数据，丢了指纹会坏", "校准"),
    "vbmeta_a": ("启动校验 A", "校验 boot 等分区有没有被改过", "校验"),
    "vbmeta_system_a": ("系统校验 A", "校验 system 分区", "校验"),
    "vbmeta_vendor_a": ("厂商校验 A", "校验 vendor 分区", "校验"),
    "vbmeta_b": ("启动校验 B", "B 槽位的启动校验", "校验"),
    "vbmeta_system_b": ("系统校验 B", "B 槽位的系统校验", "校验"),
    "vbmeta_vendor_b": ("厂商校验 B", "B 槽位的厂商校验", "校验"),
    "metadata": ("系统元数据", "加密、系统更新状态等元数据", "系统"),
    "protect1": ("保护分区 1", "校验与备份数据", "安全"),
    "protect2": ("保护分区 2", "校验与备份数据", "安全"),
    "seccfg": ("安全配置", "记录 BL 是否解锁、锁状态。写错会变砖", "安全"),
    "otp": ("一次性密钥", "出厂写入、不可更改的密钥，禁止写入", "安全"),
    "pstore": ("崩溃日志", "内核崩溃时的持久化日志", "日志"),
    "modem_a": ("基带固件 A", "负责通话、移动数据网络", "基带"),
    "spmfw_a": ("电源管理 A", "电源管理固件", "固件"),
    "mcf_ota_a": ("OTA 固件 A", "厂商 OTA 升级相关", "固件"),
    "audio_dsp_a": ("音频固件 A", "音频处理芯片的固件", "固件"),
    "pi_img_a": ("厂商镜像 A", "厂商内部镜像", "固件"),
    "dpm_a": ("数据保护 A", "数据保护管理固件", "固件"),
    "scp_a": ("传感器协处理 A", "传感器协处理器固件", "固件"),
    "ccu_a": ("摄像头控制 A", "摄像头控制单元固件", "固件"),
    "vcp_a": ("视频协处理 A", "视频编解码协处理器固件", "固件"),
    "sspm_a": ("安全电源管理 A", "安全系统的电源管理固件", "固件"),
    "mcupm_a": ("MCU 电源管理 A", "微控制器电源管理固件", "固件"),
    "gpueb_a": ("GPU 能效 A", "GPU 能效控制固件", "固件"),
    "apusys_a": ("AI 加速 A", "APU 人工智能加速固件", "固件"),
    "mvpu_algo_a": ("AI 视觉算法 A", "AI 视觉算法固件", "固件"),
    "gz_a": ("安全执行环境 A", "TEE 安全环境的一部分", "安全"),
    "lk_a": ("引导加载器 A", "开机第二阶段的小内核", "引导"),
    "boot_a": ("内核 A", "系统内核和 ramdisk，刷机常改这个", "引导"),
    "vendor_boot_a": ("厂商内核 A", "厂商内核模块和 ramdisk", "引导"),
    "init_boot_a": ("初始化镜像 A", "安卓 13 以后放初始化 ramdisk，root 常改这个", "引导"),
    "dtbo_a": ("设备树 A", "描述硬件配置，刷错可能不开机", "引导"),
    "tee_a": ("可信执行环境 A", "指纹、支付等安全功能依赖它", "安全"),
    "cdt_engineering_a": ("工程校准 A", "工厂校准数据", "校准"),
    "connsys_bt_a": ("蓝牙固件 A", "蓝牙芯片固件", "无线"),
    "connsys_wifi_a": ("WiFi 固件 A", "WiFi 芯片固件", "无线"),
    "connsys_gnss_a": ("GPS 固件 A", "定位芯片固件", "无线"),
    "pvmfw_a": ("虚拟机固件 A", "受保护虚拟机的固件", "固件"),
    "ise_a": ("图像安全引擎 A", "图像安全处理固件", "固件"),
    "rotfw_a": ("信任根固件 A", "安全启动的信任根", "安全"),
    "logo_a": ("开机 logo A", "开机第一屏显示的图片", "显示"),
    "sec1": ("安全分区", "密钥与证书", "安全"),
    "proinfo": ("产品信息", "机型、销售地区等出厂信息", "系统"),
    "nvram": ("无线校准", "WiFi/蓝牙的 MAC 和射频参数，丢了 WiFi 打不开", "校准"),
    "ocdt": ("出厂校准", "屏幕、触控等出厂校准数据", "校准"),
    "boot_para": ("启动参数备份", "启动参数的备份副本", "系统"),
    "dram_para": ("内存参数", "内存时序参数，刷错直接不开机", "系统"),
    "modem_b": ("基带固件 B", "B 槽位的基带固件", "基带"),
    "spmfw_b": ("电源管理 B", "B 槽位电源管理固件", "固件"),
    "mcf_ota_b": ("OTA 固件 B", "B 槽位 OTA 固件", "固件"),
    "audio_dsp_b": ("音频固件 B", "B 槽位音频固件", "固件"),
    "pi_img_b": ("厂商镜像 B", "B 槽位厂商镜像", "固件"),
    "dpm_b": ("数据保护 B", "B 槽位数据保护固件", "固件"),
    "scp_b": ("传感器协处理 B", "B 槽位传感器固件", "固件"),
    "ccu_b": ("摄像头控制 B", "B 槽位摄像头固件", "固件"),
    "vcp_b": ("视频协处理 B", "B 槽位视频固件", "固件"),
    "sspm_b": ("安全电源管理 B", "B 槽位安全电源固件", "固件"),
    "mcupm_b": ("MCU 电源管理 B", "B 槽位 MCU 电源固件", "固件"),
    "gpueb_b": ("GPU 能效 B", "B 槽位 GPU 能效固件", "固件"),
    "apusys_b": ("AI 加速 B", "B 槽位 AI 加速固件", "固件"),
    "mvpu_algo_b": ("AI 视觉算法 B", "B 槽位 AI 视觉固件", "固件"),
    "gz_b": ("安全执行环境 B", "B 槽位安全环境", "安全"),
    "lk_b": ("引导加载器 B", "B 槽位引导器", "引导"),
    "boot_b": ("内核 B", "B 槽位内核", "引导"),
    "vendor_boot_b": ("厂商内核 B", "B 槽位厂商内核", "引导"),
    "init_boot_b": ("初始化镜像 B", "B 槽位初始化镜像", "引导"),
    "connsys_bt_b": ("蓝牙固件 B", "B 槽位蓝牙固件", "无线"),
    "connsys_wifi_b": ("WiFi 固件 B", "B 槽位 WiFi 固件", "无线"),
    "connsys_gnss_b": ("GPS 固件 B", "B 槽位定位固件", "无线"),
    "dtbo_b": ("设备树 B", "B 槽位设备树", "引导"),
    "pvmfw_b": ("虚拟机固件 B", "B 槽位虚拟机固件", "固件"),
    "ise_b": ("图像安全引擎 B", "B 槽位图像安全固件", "固件"),
    "rotfw_b": ("信任根固件 B", "B 槽位信任根", "安全"),
    "logo_b": ("开机 logo B", "B 槽位开机图片", "显示"),
    "tee_b": ("可信执行环境 B", "B 槽位安全环境", "安全"),
    "cdt_engineering_b": ("工程校准 B", "B 槽位工厂校准", "校准"),
    "splash_odm": ("开机动画", "厂商定制的开机动画", "显示"),
    "oplusreserve5": ("厂商预留 5", "OPPO/一加预留空间", "预留"),
    "oplusreserve6": ("厂商预留 6", "OPPO/一加预留空间", "预留"),
    "hybridswap": ("内存扩展", "混合交换分区，用来扩展运行内存", "系统"),
    "super": ("动态分区容器", "system、vendor、product 都装在里面（约 13.7GB）", "系统"),
    "userdata": ("用户数据", "照片、应用、设置都在这里（约 459GB），刷机常清", "数据"),
    "mrdump": ("崩溃转储", "系统崩溃时的内存转储", "日志"),
    "flashinfo": ("闪存信息", "闪存芯片参数，禁止写入", "系统"),
}

UNKNOWN = ("未知分区", "不在已知清单里，建议不要动它", "未知")
CATEGORY_ORDER = ["引导", "系统", "安全", "基带", "固件", "无线", "校准", "数据", "显示", "校验", "日志", "预留", "未知"]

# 关键分区：必须优先备份
CRITICAL = ["nvram", "nvdata", "nvcfg", "persist", "sec1", "proinfo", "protect1", "protect2",
            "seccfg", "ocdt", "md_sec", "otp", "frp", "misc", "boot_para", "dram_para",
            "cdt_engineering_a", "cdt_engineering_b"]

# 备份“重要分区”时排除的数据 / 日志 / 超大分区
EXCLUDE = {"userdata", "metadata", "expdb", "pstore", "mrdump", "hybridswap",
           "oplusreserve1", "oplusreserve2", "oplusreserve3", "oplusreserve5", "oplusreserve6",
           "flashinfo", "logo_a", "logo_b", "splash_odm", "super"}

BLOCK_WRITE = {
    "seccfg", "otp", "flashinfo",
    "preloader", "preloader_a", "preloader_b",
    "preloader_raw", "preloader_raw_a", "preloader_raw_b",
    "pgpt", "sgpt", "bootloader", "bootloader_a", "bootloader_b",
    "sda", "sdb", "sdc",
}
BLOCK_ERASE = {
    "seccfg", "otp", "flashinfo",
    "preloader", "preloader_a", "preloader_b",
    "preloader_raw", "preloader_raw_a", "preloader_raw_b",
    "pgpt", "sgpt", "bootloader", "bootloader_a", "bootloader_b",
    "boot_a", "boot_b", "init_boot_a", "init_boot_b", "vendor_boot_a", "vendor_boot_b",
    "dtbo_a", "dtbo_b", "lk_a", "lk_b", "tee_a", "tee_b", "gz_a", "gz_b",
    "modem_a", "modem_b", "nvram", "nvdata", "nvcfg", "persist", "sec1", "proinfo",
    "protect1", "protect2", "misc", "boot_para", "dram_para", "sda", "sdb", "sdc",
    "super",
    "vbmeta_a", "vbmeta_b", "vbmeta_system_a", "vbmeta_system_b",
    "vbmeta_vendor_a", "vbmeta_vendor_b",
}

# 风险较高、但仍允许在“有正确备份 + 两道确认”下写入的分区，界面额外提示。
WARN_WRITE = {
    "misc", "boot_para", "dram_para", "nvram", "nvdata", "nvcfg",
    "persist", "sec1", "proinfo", "protect1", "protect2", "frp",
    "md_sec", "cdt_engineering_a", "cdt_engineering_b",
    "vbmeta_a", "vbmeta_b", "vbmeta_system_a", "vbmeta_system_b",
    "vbmeta_vendor_a", "vbmeta_vendor_b", "super", "userdata", "metadata",
}


def describe(name):
    """返回 (中文名, 说明, 分类)。"""
    if name in DESC:
        return DESC[name]
    for suf in ("_a", "_b"):
        if name.endswith(suf) and name[:-2] in DESC:
            cn, d, cat = DESC[name[:-2]]
            slot = "A" if suf == "_a" else "B"
            return (cn + " " + slot, d + "（%s 槽位）" % slot, cat)
    return UNKNOWN


def friendly(name):
    cn, _d, _cat = describe(name)
    if cn == UNKNOWN[0]:
        return "未知"
    return cn


def full_label(name):
    cn, d, _cat = describe(name)
    if cn == UNKNOWN[0]:
        return "未知"
    return "%s（%s）" % (cn, d)


def is_unknown(name):
    return describe(name)[0] == UNKNOWN[0]


def count_unknown(names):
    return sum(1 for n in names if is_unknown(n))


def load_gpt(path=None):
    """读取 gpt_partitions.txt（名称<TAB>字节数）。"""
    table = {}
    path = path or config.GPT_FILE
    try:
        with open(path, "r", encoding="ascii", errors="ignore") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2 and parts[1].isdigit():
                    table[parts[0]] = int(parts[1])
    except Exception:
        pass
    return table


GPT = load_gpt()


def important_names(table=None):
    table = GPT if table is None else table
    return sorted([k for k in table if k not in EXCLUDE])


# 全量备份：除 userdata（用户数据）外，所有分区都备份。
FULL_EXCLUDE = {"userdata"}


def full_names(table=None):
    table = GPT if table is None else table
    return sorted([k for k in table if k not in FULL_EXCLUDE])


def full_size(table=None):
    table = GPT if table is None else table
    return sum(table.get(n, 0) for n in full_names(table))


GPT_RAW_CHUNK = 0x4000


def write_gpt_commands(f, primary_path, backup_path, total_sectors, sector_size):
    """写主 GPT 的分块只读抓取命令。

    备份 GPT 在部分 UFS 上落在 LUA2 可寻址范围之外，DA 会报
    “base address is larger than partition max size”，因此只读主 GPT；
    备份 GPT 由主 GPT 的同一份分区数组在本地重建。
    """
    total = int(total_sectors or 0)
    sec = int(sector_size or 0)
    if total <= 100 or sec not in (512, 4096):
        return
    total_len = 34 * sec
    n = (total_len + GPT_RAW_CHUNK - 1) // GPT_RAW_CHUNK
    for i in range(n):
        length = min(GPT_RAW_CHUNK, total_len - i * GPT_RAW_CHUNK)
        f.write("ro 0x%x 0x%x %s.part%d\n"
                % (i * GPT_RAW_CHUNK, length, primary_path, i))


def join_gpt_file(base_path):
    """把 gpt_*.raw.partN 按顺序合并为完整 raw。"""
    parts = []
    i = 0
    while True:
        p = base_path + ".part%d" % i
        if not os.path.isfile(p):
            break
        parts.append(p)
        i += 1
    if not parts:
        return os.path.isfile(base_path)
    try:
        with open(base_path, "wb") as out:
            for p in parts:
                with open(p, "rb") as src:
                    shutil.copyfileobj(src, out)
        for p in parts:
            try:
                os.remove(p)
            except Exception:
                pass
        return True
    except Exception:
        return False


def join_gpt_backup(base_path):
    return join_gpt_file(base_path)


def write_script(path, names, subdir, total_sectors=None, sector_size=512):
    """生成 mtkclient 的 script 文件（printgpt + GPT 原始扇区 + 逐分区 r）。

    GPT 备份扇区在磁盘末尾，按 0x8000 分块抓取，避免 DA 单次读取上限。
    """
    with open(path, "w", encoding="ascii") as f:
        f.write("printgpt\n")
        write_gpt_commands(f, "%s\\gpt_primary.raw" % subdir,
                           "%s\\gpt_backup.raw" % subdir,
                           total_sectors, sector_size)
        for n in names:
            f.write("r %s %s\\%s.bin\n" % (n, subdir, n))
