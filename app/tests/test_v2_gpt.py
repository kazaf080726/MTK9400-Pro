# -*- coding: utf-8 -*-
"""GPT 备份 / 校验 / 恢复的电脑端模拟测试。"""
import os
import shutil
import sys
import tempfile
import unittest
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from v2 import gpt


def entry(name, first, last, index=0):
    # 类型 GUID 任意非零；唯一 GUID 必须唯一
    return gpt.GptEntry(
        bytes([index + 1]) + b"\x00" * 15,
        uuid.uuid4().bytes,
        first, last, 0,
        gpt._name_to_raw(name),
    )


class GptTest(unittest.TestCase):
    def make_image(self, sector_size=512):
        total = 8192 if sector_size == 512 else 2048
        es = [entry("boot_a", 100, 199, 0),
              entry("init_boot_a", 200, 249, 1),
              entry("userdata", 300, 799, 2)]
        return gpt.build_image(es, total, sector_size), total

    def test_build_from_layout(self):
        layout = [
            {"name": "boot_a", "start": 1024 * 512, "size": 512 * 512},
            {"name": "vendor_boot_a", "start": 2048 * 512, "size": 1024 * 512},
            {"name": "super", "start": 4096 * 512, "size": 2048 * 512},
        ]
        img = gpt.build_from_layout(layout, 8192, 512)
        self.assertEqual(len(img.entries), 3)
        self.assertEqual([e.name for e in img.entries], ["boot_a", "vendor_boot_a", "super"])
        self.assertFalse(img.validate(strict_mbr=True))
        self.assertEqual(img.entries[0].first_lba, 1024)

    def test_build_from_layout_rejects_overlap(self):
        layout = [
            {"name": "a", "start": 1024 * 512, "size": 1024 * 512},
            {"name": "b", "start": 1536 * 512, "size": 1024 * 512},
        ]
        with self.assertRaises(gpt.GptError):
            gpt.build_from_layout(layout, 8192, 512)

    def test_build_parse_512(self):
        img, total = self.make_image(512)
        self.assertEqual(img.sector_size, 512)
        self.assertEqual(img.total_sectors, total)
        self.assertEqual(len(img.entries), 3)
        self.assertFalse(img.validate(strict_mbr=True))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "disk.img")
            open(p, "wb").write(gpt.disk_bytes(img))
            img2 = gpt.parse_disk_file(p)
            self.assertEqual(img2.disk_guid, img.disk_guid)
            self.assertEqual(len(img2.entries), 3)
            self.assertFalse(img2.validate(strict_mbr=True))

    def test_build_parse_4096(self):
        img, total = self.make_image(4096)
        self.assertEqual(img.sector_size, 4096)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "disk.img")
            open(p, "wb").write(gpt.disk_bytes(img))
            img2 = gpt.parse_disk_file(p)
            self.assertEqual(img2.sector_size, 4096)
            self.assertEqual(len(img2.entries), 3)

    def test_crc_detection(self):
        img, _ = self.make_image(512)
        raw = bytearray(gpt.disk_bytes(img))
        raw[512 + 16] ^= 0x01  # header crc field
        with self.assertRaises(gpt.GptError):
            gpt.GptImage.from_blocks(bytes(raw[:0x10000]), bytes(raw[-0x10000:]),
                                     img.total_sectors, 512)
        raw = bytearray(gpt.disk_bytes(img))
        raw[1024] ^= 0x01  # first entry byte
        with self.assertRaises(gpt.GptError):
            gpt.GptImage.from_blocks(bytes(raw[:0x10000]), bytes(raw[-0x10000:]),
                                     img.total_sectors, 512)

    def test_backup_load_and_restore_plan(self):
        img, total = self.make_image(512)
        with tempfile.TemporaryDirectory() as d:
            img.save(d)
            loaded = gpt.GptImage.load(d)
            self.assertEqual(loaded.disk_guid, img.disk_guid)
            plan = loaded.restore_plan(total, 512, loaded.disk_guid)
            self.assertEqual(plan["order"], ["backup", "primary"])
            self.assertEqual(plan["primary_offset"], 0)
            self.assertEqual(plan["backup_offset"], img.backup_start_lba * 512)
            disk = bytearray(gpt.disk_bytes(img))
            # 模拟按计划写入：备份先写，主 GPT 后写
            disk[plan["backup_offset"]:plan["backup_offset"] + plan["backup_length"]] = plan["backup_data"]
            disk[plan["primary_offset"]:plan["primary_offset"] + plan["primary_length"]] = plan["primary_data"]
            restored = gpt.GptImage.from_blocks(
                bytes(disk[:0x10000]), bytes(disk[-0x10000:]),
                total, 512, backup_base_lba=(len(disk) - 0x10000) // 512)
            self.assertEqual(restored.disk_guid, img.disk_guid)
            self.assertFalse(restored.validate(strict_mbr=True))

    def test_tampered_backup_rejected(self):
        img, _ = self.make_image(512)
        with tempfile.TemporaryDirectory() as d:
            img.save(d)
            p = os.path.join(d, "pgpt.bin")
            data = bytearray(open(p, "rb").read())
            data[0x30] ^= 0x01
            open(p, "wb").write(data)
            with self.assertRaises(gpt.GptError):
                gpt.GptImage.load(d)

    def test_partition_overlap_rejected(self):
        es = [entry("a", 100, 300, 0), entry("b", 200, 400, 1)]
        with self.assertRaises(gpt.GptError):
            gpt.build_image(es, 8192, 512)

    def test_capacity_mismatch_rejected(self):
        img, total = self.make_image(512)
        with self.assertRaises(gpt.GptError):
            img.restore_plan(total + 1, 512, img.disk_guid)
        with self.assertRaises(gpt.GptError):
            img.restore_plan(total, 4096, img.disk_guid)

    def test_disk_guid_mismatch_rejected(self):
        img, total = self.make_image(512)
        with self.assertRaises(gpt.GptError):
            img.restore_plan(total, 512, "00000000-0000-0000-0000-000000000000")

    def test_mbr_required_on_restore(self):
        img, total = self.make_image(512)
        broken = bytearray(img.primary_raw)
        broken[0x1FE:0x200] = b"\x00\x00"
        img.primary_raw = bytes(broken)
        with self.assertRaises(gpt.GptError):
            img.restore_plan(total, 512, img.disk_guid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
