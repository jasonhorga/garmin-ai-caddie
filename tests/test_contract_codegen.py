from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.contracts.generate_contracts import generate_all


class ContractCodegenTests(unittest.TestCase):
    def test_checked_in_outputs_match_all_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = generate_all(Path("contracts/canonical"), Path(tmp))
            self.assertEqual(
                set(outputs),
                {
                    "ai_caddie/contracts/generated.py",
                    "mobile/ios/AICaddieDomain/GeneratedContracts.swift",
                    "web_v2/src/contracts/generated.ts",
                },
            )
            for relative, generated in outputs.items():
                self.assertEqual(Path(relative).read_text(encoding="utf-8"), generated, relative)
                self.assertIn("CanonicalFixtureAlpha/v1", generated)
                self.assertIn("CanonicalFixtureBeta/v1", generated)
