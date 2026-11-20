# -*- coding: utf-8 -*-
"""内置 payload / lpunpack / simg2img 工具可用性测试。"""
import os
import struct
import sys
import tempfile
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from v2 import lptools, payload


class ToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            if not os.path.isfile(payload.tool_path()):
                raise unittest.SkipTest("third-party tools not bundled")
            for name in ("lpunpack.exe", "lpmake.exe", "simg2img.exe"):
                if not lptools._tool(name):
                    raise unittest.SkipTest("third-party tools not bundled")
        except Exception:
            raise unittest.SkipTest("third-party tools not bundled")

    def test_tools_exist(self):
        self.assertTrue(os.path.isfile(payload.tool_path()))
        self.assertTrue(lptools._tool("lpunpack.exe"))
        self.assertTrue(lptools._tool("lpmake.exe"))
        self.assertTrue(lptools._tool("simg2img.exe"))

    def test_simg2img(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "sparse.img")
            dst = os.path.join(d, "raw.img")
            hdr = struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, 512, 1, 1, 0)
            chunk = struct.pack("<HHII", 0xCAC1, 0, 1, 524) + b"x" * 512
            open(src, "wb").write(hdr + chunk)
            lptools.simg2img(src, dst)
            self.assertEqual(open(dst, "rb").read(), b"x" * 512)


if __name__ == "__main__":
    unittest.main(verbosity=2)
