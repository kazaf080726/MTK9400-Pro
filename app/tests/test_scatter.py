# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import scatter

SAMPLE = """#
- general: MTK_PLATFORM_CFG
  info:
    - config_version: V1.1.2
      platform: MT6991
      project: test
      storage: UFS
      block_size: 0x20000
- partition_index: SYS0
  partition_name: preloader
  file_name: preloader.bin
  is_download: true
  type: SV5_BL_BIN
  physical_start_addr: 0x0
  partition_size: 0x200000
  region: UFS_LU2
- partition_index: SYS1
  partition_name: boot_a
  file_name: boot_a.bin
  is_download: true
  type: EXT4
  physical_start_addr: 0x200000
  partition_size: 0x4000000
  region: UFS_LU2
"""


def test_parse_generate():
    sc = scatter.parse(SAMPLE)
    assert sc.platform == "MT6991"
    assert len(sc.entries) == 2
    assert sc.by_name()["boot_a"].size == 0x4000000
    text = scatter.generate(sc.entries, project="x")
    sc2 = scatter.parse(text)
    assert sc2.platform == "MT6991"
    assert len(sc2.entries) == 2
    assert sc2.by_name()["boot_a"].start == 0x200000


def test_plan_directory():
    sc = scatter.parse(SAMPLE)
    d = tempfile.mkdtemp()
    open(os.path.join(d, "boot_a.bin"), "wb").write(b"x" * 10)
    open(os.path.join(d, "unknown.bin"), "wb").write(b"x")
    plans, errors = scatter.plan_directory(sc, d, {"boot_a": 0x4000000})
    assert len(plans) == 1
    assert plans[0]["name"] == "boot_a"
    assert any("unknown" in e for e in errors)


if __name__ == "__main__":
    test_parse_generate()
    test_plan_directory()
    print("PASS scatter")
