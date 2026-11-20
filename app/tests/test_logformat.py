# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import logformat


def test_levels():
    assert logformat.record("ERROR: failed to read")["level"] == "ERROR"
    assert logformat.record("Waiting for PreLoader VCOM")["level"] == "WARN"
    assert logformat.record("GPT Table:")["module"] == "GPT"
    assert logformat.record("backup completed")["level"] == "INFO"


def test_records_ansi():
    r = logformat.records("\x1b[31mERROR\x1b[0m failed\n\n")
    assert len(r) == 1 and r[0]["level"] == "ERROR"


if __name__ == "__main__":
    test_levels()
    test_records_ansi()
    print("PASS logformat")
