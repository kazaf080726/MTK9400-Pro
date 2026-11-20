# -*- coding: utf-8 -*-
"""OFP 解密器电脑端合成测试。"""
import os
import struct
import sys
import tempfile
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

from Cryptodome.Cipher import AES
from v2 import ofp, firmware


def shuffle(data, key=b"geyixue"):
    # 与 ofp._mtk_shuffle 的逆过程：pad = key ^ plain，cipher = swap(pad)
    out = bytearray(data)
    for i in range(len(out)):
        out[i] = ((key[i % len(key)] ^ out[i]) & 0xF0) >> 4 | (16 * ((key[i % len(key)] ^ out[i]) & 0xF))
    return bytes(out)


def make_ofp(path, payload):
    aeskey = b"ab3f76d7989207f2"
    aesiv = b"2bf515b3a9737835"
    first = AES.new(aeskey, AES.MODE_CFB, IV=aesiv, segment_size=128).encrypt(b"MMM" + b"\x00" * 13)
    body = first + payload
    entry = struct.pack("<32s Q Q Q 32s Q", b"boot", 16, len(payload), 0,
                        b"boot.img", 0)
    hdr2 = shuffle(entry)
    hdr = struct.pack("46s Q 4s 7s 5s H 32s H", b"TEST", 0, b"\x00" * 4,
                      b"MT6991", b"UFS", 1, b"info", 0)
    hdr = hdr.ljust(0x6C, b"\x00")
    with open(path, "wb") as f:
        f.write(body)
        f.write(hdr2)
        f.write(shuffle(hdr))


class OfpTest(unittest.TestCase):
    def test_decrypt(self):
        payload = b"BOOTIMAGE" * 128
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "test.ofp")
            make_ofp(p, payload)
            meta, files = ofp.decrypt(p, os.path.join(d, "out"))
            self.assertEqual(meta["cpu"], "MT6991")
            self.assertTrue(files)
            self.assertEqual(open(files[0], "rb").read(), payload)

    def test_ofp_enters_firmware_package(self):
        payload = b"BOOTIMAGE" * 64
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "test.ofp")
            make_ofp(p, payload)
            pkg = firmware.FirmwarePackage.load(p)
            self.assertEqual(pkg.source_kind, "ofp+images")
            self.assertTrue(any(x.name == "boot" for x in pkg.items))
            errors, _ = pkg.preflight()
            self.assertFalse(any("缺少" in e for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
