# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import rawaddr, preloader, factory


def test_rawaddr():
    p = rawaddr.prepare("USER", "0x1000", "0x100", os.path.join(tempfile.gettempdir(), "a.bin"))
    assert p["args"][:2] == ["ro", "0x1000"]
    p = rawaddr.prepare("BOOT_1", "0", "0x10", os.path.join(tempfile.gettempdir(), "a.bin"))
    assert p["args"][-2:] == ["--parttype", "boot1"]
    try:
        rawaddr.prepare("USER", "0", "zzz", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("bad size accepted")


def test_preloader():
    p, err = preloader.export_plan({"preloader": 0x1000}, tempfile.gettempdir())
    assert not err and p["name"] == "preloader"
    assert p["args"][:2] == ["r", "preloader"]
    assert preloader.find_preloader({"preloader_b": 1}) == "preloader_b"


def test_factory():
    targets, err = factory.plan(["userdata", "metadata", "persist"])
    assert not err and "userdata" in targets and "persist" not in targets
    assert factory.script_lines(targets) == ["e userdata", "e metadata"]


if __name__ == "__main__":
    test_rawaddr()
    test_preloader()
    test_factory()
    print("PASS ops")
