# -*- coding: utf-8 -*-
"""路径安全 / ZIP 路径穿越测试。"""
import os
import sys
import tempfile
import unittest
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from v2 import paths


class SecurityTest(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(paths.safe_name("..\\boot_a"), "boot_a")
        self.assertNotIn("/", paths.safe_name("../x"))
        self.assertNotIn("\\", paths.safe_name("..\\x"))

    def test_safe_join_blocks_escape(self):
        with tempfile.TemporaryDirectory() as d:
            p = paths.safe_join(d, "..\\escape", ".bin")
            self.assertTrue(os.path.abspath(p).startswith(os.path.abspath(d) + os.sep))

    def test_zip_slip_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            z = os.path.join(d, "evil.zip")
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("../../outside.txt", b"x")
            with self.assertRaises(paths.PathError):
                paths.safe_extract_zip(z, os.path.join(d, "out"))
            self.assertFalse(os.path.exists(os.path.join(d, "outside.txt")))

    def test_zip_normal(self):
        with tempfile.TemporaryDirectory() as d:
            z = os.path.join(d, "ok.zip")
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("scatter.txt", b"x")
                f.writestr("images/boot.img", b"boot")
            out = os.path.join(d, "out")
            paths.safe_extract_zip(z, out)
            self.assertEqual(open(os.path.join(out, "images", "boot.img"), "rb").read(), b"boot")


if __name__ == "__main__":
    unittest.main(verbosity=2)
