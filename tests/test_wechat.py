from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.wechat import split_message


class TestWechat(unittest.TestCase):
    def test_split_message_keeps_length_limit(self) -> None:
        text = "line1\n" + ("x" * 30) + "\nline3\n"
        chunks = split_message(text, max_chars=21)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 21 for chunk in chunks))

    def test_split_message_single_chunk(self) -> None:
        text = "short text"
        chunks = split_message(text, max_chars=100)
        self.assertEqual(chunks, [text])


if __name__ == "__main__":
    unittest.main()
