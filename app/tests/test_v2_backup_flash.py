# -*- coding: utf-8 -*-
"""备份清单 / 固件计划电脑端测试。"""
import os
import sys
import tempfile
import unittest
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from core import scatter
from v2 import backup, firmware


class BackupTest(unittest.TestCase):
    def test_manifest_roundtrip_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            files = {"nvram": b"N" * 4096, "boot_a": b"B" * 8192, "super": b"S" * 4096}
            for n, data in files.items():
                open(os.path.join(d, n + ".bin"), "wb").write(data)
            parts = [{"name": n, "start_lba": i * 10, "size_bytes": len(data)}
                     for i, (n, data) in enumerate(files.items())]
            meta = {"model": "MT6991", "platform": "MT6991", "sector_size": 512,
                    "total_sectors": 1000, "disk_size": 512000, "disk_guid": "ABC"}
            m = backup.make_manifest(meta, parts, d, selected=files)
            backup.save_manifest(m, d)
            loaded = backup.load_manifest(d)
            self.assertEqual(len(loaded.items), 3)
            self.assertFalse(backup.verify_backup(loaded, d))
            plan = backup.restore_plan(loaded, d, groups=["critical", "boot"],
                                       target=meta)
            self.assertEqual(len(plan), 2)
            self.assertEqual(plan[0]["name"], "nvram")

    def test_tamper_detected(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "nvram.bin"), "wb").write(b"abc")
            m = backup.make_manifest(
                {"model": "X", "sector_size": 512, "total_sectors": 10,
                 "disk_size": 5120, "disk_guid": "G"},
                [{"name": "nvram", "start_lba": 1, "size_bytes": 3}], d, selected=["nvram"])
            backup.save_manifest(m, d)
            open(os.path.join(d, "nvram.bin"), "wb").write(b"abd")
            self.assertTrue(backup.verify_backup(m, d))

    def test_target_reject(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "boot_a.bin"), "wb").write(b"x")
            m = backup.make_manifest(
                {"model": "X", "sector_size": 512, "total_sectors": 10,
                 "disk_size": 5120, "disk_guid": "G"},
                [{"name": "boot_a", "start_lba": 1, "size_bytes": 1}], d, selected=["boot_a"])
            with self.assertRaises(backup.BackupError):
                backup.restore_plan(m, d, groups=["boot"],
                                    target={"sector_size": 4096, "total_sectors": 10,
                                            "disk_guid": "G", "model": "X"})


class FirmwareTest(unittest.TestCase):
    def make_pkg(self, d):
        entries = [
            {"name": "boot_a", "file_name": "boot_a.img", "size": 8192, "start": 0x1000, "download": True},
            {"name": "super", "file_name": "super.img", "size": 65536, "start": 0x2000, "download": True},
            {"name": "nvram", "file_name": "nvram.bin", "size": 4096, "start": 0x3000, "download": True},
        ]
        scatter.write(os.path.join(d, "scatter.txt"), entries)
        for n in ("boot_a.img", "super.img", "nvram.bin"):
            open(os.path.join(d, n), "wb").write(b"x" * (8192 if "boot" in n else 4096))
        return firmware.FirmwarePackage.load(d)

    def test_parse_and_plan(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = self.make_pkg(d)
            self.assertEqual(len(pkg.items), 3)
            pkg.select_mode("repair")
            names = [x.name for x in pkg.selected_items()]
            self.assertIn("boot_a", names)
            self.assertIn("super", names)
            self.assertNotIn("nvram", names)
            cmds = pkg.plan("repair")
            self.assertTrue(any(c["action"] == "write" for c in cmds))

    def test_preflight_missing_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            entries = [{"name": "boot_a", "file_name": "boot_a.img", "size": 10, "start": 0, "download": True}]
            scatter.write(os.path.join(d, "scatter.txt"), entries)
            pkg = firmware.FirmwarePackage.load(d)
            self.assertTrue(any("缺少镜像" in e for e in pkg.errors))

    def test_sparse_converted(self):
        import struct
        with tempfile.TemporaryDirectory() as d:
            entries = [{"name": "super", "file_name": "super.img", "size": 4096, "start": 0, "download": True}]
            scatter.write(os.path.join(d, "scatter.txt"), entries)
            hdr = struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, 512, 1, 1, 0)
            chunk = struct.pack("<HHII", 0xCAC1, 0, 1, 524) + b"x" * 512
            open(os.path.join(d, "super.img"), "wb").write(hdr + chunk)
            pkg = firmware.FirmwarePackage.load(d)
            self.assertTrue(pkg.items)
            self.assertTrue(pkg.items[0].converted)
            errors, _ = pkg.preflight()
            self.assertFalse(any("sparse" in e for e in errors))

if __name__ == "__main__":
    unittest.main(verbosity=2)
