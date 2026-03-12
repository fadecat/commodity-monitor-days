from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.config import SymbolConfig, load_config, load_symbols, with_extra_symbols


class TestConfig(unittest.TestCase):
    def test_load_core_config(self) -> None:
        cfg = load_config(ROOT / "config" / "monitor.toml")
        self.assertGreater(len(cfg.symbols), 0)
        self.assertIn("y5", cfg.windows)
        self.assertIn("y10", cfg.windows)

    def test_with_extra_symbols_dedup(self) -> None:
        cfg = load_config(ROOT / "config" / "monitor.toml")
        extra = [
            SymbolConfig(code=cfg.symbols[0].code, name="dup", market=cfg.symbols[0].market),
            SymbolConfig(code="ZZ0", name="ZZ0", market="domestic"),
        ]
        merged = with_extra_symbols(cfg, extra)
        self.assertEqual(len(merged.symbols), len(cfg.symbols) + 1)

    def test_load_extended_symbols(self) -> None:
        symbols = load_symbols(ROOT / "config" / "symbols_extended.toml")
        self.assertGreater(len(symbols), 10)


if __name__ == "__main__":
    unittest.main()
