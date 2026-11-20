# -*- coding: utf-8 -*-
"""Android sparse image 展开。"""
import os
import struct

MAGIC = 0xED26FF3A
MAX_OUTPUT = 64 * 1024 ** 3
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


class SparseError(Exception):
    pass


def is_sparse(path):
    try:
        with open(path, "rb") as f:
            return struct.unpack("<I", f.read(4))[0] == MAGIC
    except Exception:
        return False


def expand(src, dst):
    with open(src, "rb") as f:
        magic, major, minor, fhsz, chsz, blk, total_blks, total_chunks, checksum = \
            struct.unpack("<IHHHHIIII", f.read(28))
        if magic != MAGIC:
            raise SparseError("不是 Android sparse 镜像")
        if blk <= 0 or blk > 16 * 1024 * 1024:
            raise SparseError("sparse block size 异常")
        written = 0
        with open(dst, "wb") as out:
            for _ in range(total_chunks):
                hdr = f.read(12)
                if len(hdr) != 12:
                    raise SparseError("sparse chunk 截断")
                ctype, _res, cblocks, total = struct.unpack("<HHII", hdr)
                if cblocks > MAX_OUTPUT // blk:
                    raise SparseError("sparse 单块过大")
                if written + cblocks * blk > MAX_OUTPUT:
                    raise SparseError("sparse 展开超过 64 GB 限制")
                data_len = max(0, int(total) - 12)
                data = f.read(data_len) if ctype != CHUNK_DONT_CARE else b""
                if ctype == CHUNK_RAW:
                    if len(data) != cblocks * blk:
                        raise SparseError("sparse RAW 长度异常")
                    out.write(data)
                elif ctype == CHUNK_FILL:
                    if len(data) < 4:
                        raise SparseError("sparse FILL 长度异常")
                    out.write(data[:4] * cblocks * (blk // 4))
                elif ctype == CHUNK_DONT_CARE:
                    out.write(b"\x00" * (cblocks * blk))
                elif ctype == CHUNK_CRC32:
                    pass
                else:
                    raise SparseError("未知 sparse chunk：0x%x" % ctype)
                written += cblocks * blk
        if total_blks and written != total_blks * blk:
            raise SparseError("sparse 总块数不一致")
    return dst
