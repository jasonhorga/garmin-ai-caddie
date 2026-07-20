from __future__ import annotations

import ast
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
                self.assertEqual(Path(relative).read_bytes(), generated.encode("utf-8"), relative)
                self.assertIn("CanonicalFixtureAlpha/v1", generated)
                self.assertIn("CanonicalFixtureBeta/v1", generated)

    def test_main_writes_generated_outputs_as_explicit_utf8_bytes(self) -> None:
        source = Path("tools/contracts/generate_contracts.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_bytes"
        ]
        self.assertEqual(len(calls), 1)
        encoded = calls[0].args[0]
        self.assertIsInstance(encoded, ast.Call)
        assert isinstance(encoded, ast.Call)
        self.assertIsInstance(encoded.func, ast.Attribute)
        assert isinstance(encoded.func, ast.Attribute)
        self.assertEqual(encoded.func.attr, "encode")
        self.assertEqual([ast.literal_eval(arg) for arg in encoded.args], ["utf-8"])
