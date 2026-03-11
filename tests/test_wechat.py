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

    def test_split_message_keeps_symbol_block_integrity(self) -> None:
        text = (
            "🔴 **A**: **1** | 创[y1]高位\n"
            "> 历史分位: 21d(90%) | 63d(91%) | 1y(95%) | 3y(88%)\n\n"
            "🟢 **B**: **2** | 创[y1]低位\n"
            "> 历史分位: 21d(20%) | 63d(25%) | 1y(10%) | 3y(40%)"
        )
        chunks = split_message(text, max_chars=90)
        self.assertEqual(len(chunks), 2)
        self.assertIn("🔴 **A**", chunks[0])
        self.assertIn("> 历史分位", chunks[0])
        self.assertIn("🟢 **B**", chunks[1])
        self.assertIn("> 历史分位", chunks[1])

    def test_split_message_respects_utf8_byte_limit(self) -> None:
        block = (
            "🔴 **测试品种**: **12345** | 创[y1]高位\n"
            "> 历史分位: 21d(88%) | 63d(92%) | 1y(96%) | 3y(99%)"
        )
        text = "\n\n".join([block] * 8)
        chunks = split_message(text, max_chars=2000, max_bytes=220)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.encode("utf-8")) <= 220 for c in chunks))


if __name__ == "__main__":
    unittest.main()
