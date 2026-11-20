# -*- coding: utf-8 -*-
"""OPPO / OnePlus MTK .ofp 解密。

算法来源：bkerler/oppo_decrypt 的 ofp_mtk_decrypt.py，MIT License。
已改为库调用，文件名做安全处理，不覆盖目录外文件。
"""
import hashlib
import os
from binascii import hexlify, unhexlify
from struct import unpack

from Cryptodome.Cipher import AES


class OfpError(Exception):
    pass


MAX_OUTPUT = 64 * 1024 ** 3


def _swap(ch):
    return ((ch & 0xF) << 4) + ((ch & 0xF0) >> 4)


def _keyshuffle(key, hkey):
    for i in range(0, 0x10, 4):
        key[i] = _swap(hkey[i] ^ key[i])
        key[i + 1] = _swap(hkey[i + 1] ^ key[i + 1])
        key[i + 2] = _swap(hkey[i + 2] ^ key[i + 2])
        key[i + 3] = _swap(hkey[i + 3] ^ key[i + 3])
    return key


def _mtk_shuffle(key, keylength, data, length):
    for i in range(0, length):
        k = key[(i % keylength)]
        h = (((data[i]) & 0xF0) >> 4) | (16 * ((data[i]) & 0xF))
        data[i] = k ^ h
    return data


def _mtk_shuffle2(key, keylength, data, length):
    for i in range(0, length):
        tmp = key[i % keylength] ^ data[i]
        data[i] = ((tmp & 0xF0) >> 4) | (16 * (tmp & 0xF))
    return data


def _aes_cfb(key, iv, data):
    return AES.new(key, AES.MODE_CFB, IV=iv, segment_size=128).decrypt(data)


_KEYTABLES = [
    ["67657963787565E837D226B69A495D21", "F6C50203515A2CE7D8C3E1F938B7E94C", "42F2D5399137E2B2813CD8ECDF2F4D72"],
    ["9E4F32639D21357D37D226B69A495D21", "A3D8D358E42F5A9E931DD3917D9A3218", "386935399137416B67416BECF22F519A"],
    ["892D57E92A4D8A975E3C216B7C9DE189", "D26DF2D9913785B145D18C7219B89F26", "516989E4A1BFC78B365C6BC57D944391"],
    ["27827963787265EF89D126B69A495A21", "82C50203285A2CE7D8C3E198383CE94C", "422DD5399181E223813CD8ECDF2E4D72"],
    ["3C4A618D9BF2E4279DC758CD535147C3", "87B13D29709AC1BF2382276C4E8DF232", "59B7A8E967265E9BCABE2469FE4A915E"],
    ["1C3288822BF824259DC852C1733127D3", "E7918D22799181CF2312176C9E2DF298", "3247F889A7B6DECBCA3E28693E4AAAFE"],
    ["1E4F32239D65A57D37D2266D9A775D43", "A332D3C3E42F5A3E931DD991729A321D", "3F2A35399A373377674155ECF28FD19A"],
    ["122D57E92A518AFF5E3C786B7C34E189", "DD6DF2D9543785674522717219989FB0", "12698965A132C76136CC88C5DD94EE91"],
    ["ab3f76d7989207f2", "2bf515b3a9737835"],
]


def _getkey(index):
    kt = _KEYTABLES[index]
    if len(kt) == 3:
        obskey = bytearray(unhexlify(kt[0]))
        encaeskey = bytearray(unhexlify(kt[1]))
        encaesiv = bytearray(unhexlify(kt[2]))
        aeskey = hexlify(hashlib.md5(_mtk_shuffle2(obskey, 16, encaeskey, 16)).digest())[:16]
        aesiv = hexlify(hashlib.md5(_mtk_shuffle2(obskey, 16, encaesiv, 16)).digest())[:16]
    else:
        aeskey = bytes(kt[0], "utf-8")
        aesiv = bytes(kt[1], "utf-8")
    return aeskey, aesiv


def _brutekey(rf):
    rf.seek(0)
    enc = rf.read(16)
    for i in range(len(_KEYTABLES)):
        key, iv = _getkey(i)
        if _aes_cfb(key, iv, enc)[:3] == b"MMM":
            return key, iv
    raise OfpError("OFP 密钥不匹配")


def _clean(raw):
    return raw.replace(b"\x00", b"").decode("utf-8", "replace")


def decrypt(path, outdir, progress=None):
    if not os.path.isfile(path):
        raise OfpError("OFP 文件不存在")
    os.makedirs(outdir, exist_ok=True)
    hdrkey = bytearray(b"geyixue")
    filesize = os.path.getsize(path)
    hdrlength = 0x6C
    out_files = []
    with open(path, "rb") as rf:
        aeskey, aesiv = _brutekey(rf)
        rf.seek(filesize - hdrlength)
        hdr = _mtk_shuffle(hdrkey, len(hdrkey), bytearray(rf.read(hdrlength)), hdrlength)
        prjname, _unknown, _reserved, cpu, flashtype, entries, prjinfo, _crc = \
            unpack("46s Q 4s 7s 5s H 32s H", hdr)
        hdr2length = entries * 0x60
        meta = {"project": _clean(prjname), "cpu": _clean(cpu),
                "flash": _clean(flashtype), "info": _clean(prjinfo)}
        rf.seek(filesize - hdr2length - hdrlength)
        hdr2 = _mtk_shuffle(hdrkey, len(hdrkey), bytearray(rf.read(hdr2length)), hdr2length)
        total = max(1, len(hdr2) // 0x60)
        total_out = 0
        for idx in range(total):
            name, start, length, enclength, filename, _crc = unpack(
                "<32s Q Q Q 32s Q", hdr2[idx * 0x60:(idx + 1) * 0x60])
            if start < 0 or length < 0 or enclength < 0 or enclength > length:
                raise OfpError("OFP 文件表参数非法")
            if start > filesize or start + enclength > filesize:
                raise OfpError("OFP 文件偏移超出文件大小")
            total_out += length
            if total_out > MAX_OUTPUT:
                raise OfpError("OFP 解压超过 64 GB 限制")
            name = _clean(name)
            filename = os.path.basename(_clean(filename).replace("\\", "/"))
            if not filename or filename in (".", ".."):
                filename = "ofp_part_%03d.bin" % idx
            out = os.path.join(outdir, filename)
            rf.seek(start)
            with open(out, "wb") as wb:
                if enclength > 0:
                    encdata = rf.read(enclength)
                    if enclength % 16:
                        encdata += b"\x00" * (16 - (enclength % 16))
                    wb.write(_aes_cfb(aeskey, aesiv, encdata)[:enclength])
                    length -= enclength
                while length > 0:
                    size = min(0x200000, length)
                    wb.write(rf.read(size))
                    length -= size
            out_files.append(out)
            if progress:
                progress(idx + 1, total, name, out)
    return meta, out_files
