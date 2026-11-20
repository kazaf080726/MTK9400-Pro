# -*- coding: utf-8 -*-
"""模拟 V2 的 ro/wo 绝对偏移流程，不连接手机。"""
import os
import sys
import tempfile
import unittest
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from v2 import gpt


class DiskIO:
    def __init__(self, disk: bytearray):
        self.disk = disk
        self.reads = []
        self.writes = []

    def read(self, offset, length, path):
        self.reads.append((offset, length))
        with open(path, "wb") as f:
            f.write(self.disk[offset:offset + length])

    def write(self, offset, length, path):
        self.writes.append((offset, length))
        data = open(path, "rb").read()
        if len(data) != length:
            raise AssertionError("写入长度不一致")
        self.disk[offset:offset + length] = data


def make_disk(ss=512):
    total = 8192 if ss == 512 else 2048
    entries = [
        gpt.GptEntry(b"\x01" + b"\x00" * 15, uuid.uuid4().bytes, 100, 199, 0,
                     gpt._name_to_raw("boot_a")),
        gpt.GptEntry(b"\x02" + b"\x00" * 15, uuid.uuid4().bytes, 200, 249, 0,
                     gpt._name_to_raw("init_boot_a")),
        gpt.GptEntry(b"\x03" + b"\x00" * 15, uuid.uuid4().bytes, 300, 799, 0,
                     gpt._name_to_raw("userdata")),
    ]
    img = gpt.build_image(entries, total, ss)
    return img, total, bytearray(gpt.disk_bytes(img))


class GptDeviceFlowTest(unittest.TestCase):
    def run_case(self, ss):
        img, total, disk = make_disk(ss)
        io = DiskIO(disk)
        with tempfile.TemporaryDirectory() as d:
            pp = os.path.join(d, "primary.bin")
            bp = os.path.join(d, "backup.bin")
            read_len = min(len(disk), 0x10000)
            read_len = (read_len // ss) * ss
            backup_off = len(disk) - read_len
            io.read(0, read_len, pp)
            io.read(backup_off, read_len, bp)
            parsed = gpt.GptImage.from_blocks(
                open(pp, "rb").read(), open(bp, "rb").read(),
                total, ss, backup_base_lba=backup_off // ss)
            self.assertFalse(parsed.validate(strict_mbr=True))
            self.assertEqual(parsed.disk_guid, img.disk_guid)

            backup_dir = os.path.join(d, "backup")
            parsed.save(backup_dir)
            loaded = gpt.GptImage.load(backup_dir)
            plan = loaded.restore_plan(total, ss, loaded.disk_guid)

            # 模拟 GPT 损坏：抹掉主头、备份头和分区表项
            for off in (ss, 2 * ss, backup_off, backup_off + ss):
                disk[off:off + ss] = b"\x00" * ss

            # 按 V2 的顺序：备份 GPT 先写，主 GPT 后写
            p1 = os.path.join(d, "pgpt.restore")
            p2 = os.path.join(d, "sgpt.restore")
            open(p1, "wb").write(plan["primary_data"])
            open(p2, "wb").write(plan["backup_data"])
            io.write(plan["backup_offset"], plan["backup_length"], p2)
            io.write(plan["primary_offset"], plan["primary_length"], p1)

            # 读回校验
            io.read(0, read_len, pp)
            io.read(backup_off, read_len, bp)
            restored = gpt.GptImage.from_blocks(
                open(pp, "rb").read(), open(bp, "rb").read(),
                total, ss, backup_base_lba=backup_off // ss)
            self.assertEqual(restored.disk_guid, img.disk_guid)
            self.assertFalse(restored.validate(strict_mbr=True))
            self.assertEqual([e.name for e in restored.entries],
                             ["boot_a", "init_boot_a", "userdata"])
            self.assertEqual(io.writes[0][0], plan["backup_offset"])
            self.assertEqual(io.writes[1][0], 0)

    def test_512(self):
        self.run_case(512)

    def test_4096(self):
        self.run_case(4096)


if __name__ == "__main__":
    unittest.main(verbosity=2)
