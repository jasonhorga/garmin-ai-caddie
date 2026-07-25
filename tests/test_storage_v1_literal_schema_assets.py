from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


ROOT = Path(__file__).resolve().parents[1]
EVENT = Path("mobile/ios/AICaddieDomain/DomainRoundEvent.swift")
LEDGER = Path("mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift")
TRANSPORT = Path("mobile/ios/AICaddieDomain/LegacyV1Transport.swift")
GENERATED_SHAPE = Path(
    "mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift"
)
SHAPE_GENERATOR = Path("tools/contracts/generate_storage_v1_shape.py")
PROTECTED_PATHS = [
    "contracts/canonical/**/*.json",
    "ai_caddie/rounds/**/*.py",
    "server_v2/round_ledger_api.py",
    "mobile/ios/AICaddieDomain/**/*.swift",
    "web_v2/src/contracts/**/*.ts",
]
CANONICAL_OUTPUT_SHA256 = {
    "ai_caddie/contracts/generated.py": (
        "c728b49004f7650b223572b165d8efa65e2fc74faccead991c07569bbb047021"
    ),
    "mobile/ios/AICaddieDomain/GeneratedContracts.swift": (
        "795dd5c75925d5c998be1ca75b5e7c8b4c381261ff3dde473e772cc24c334deb"
    ),
    "web_v2/src/contracts/generated.ts": (
        "d021a6a675f9336dafebb099d62aab10d5e2d6f28ff753043b0c6a88dd2aeb53"
    ),
}


class StorageV1LiteralSchemaAssetTests(unittest.TestCase):
    def test_authority_regeneration_canonical_output_sha256_values_are_exact(self) -> None:
        for relative, expected in CANONICAL_OUTPUT_SHA256.items():
            with self.subTest(path=relative):
                actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_top_level_type_roster_is_exact(self) -> None:
        expected = {
            EVENT: {"StoredEventV1"},
            LEDGER: {
                "OriginSequenceState", "CanonicalStringSet",
                "DomainLedgerStateV1",
            },
            TRANSPORT: {
                "LegacyDomainAlias", "LegacyWireBinding",
                "PreparedLegacyV1Slot", "PreparedLegacyV1Batch",
                "LegacyV1TerminalStatus", "LegacyV1EventReceipt",
                "LegacyV1OutboxRecord", "LegacyV1TransportAnomaly",
                "WatchTerminalReceiptRelayObligation",
                "WatchTerminalReceiptRelayConfirmation",
                "LegacyV1EventBatchBody",
            },
        }
        for relative, names in expected.items():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(
                    path.is_file(),
                    f"missing literal source: {relative.as_posix()}",
                )
                source = path.read_text(encoding="utf-8")
                actual = set(
                    re.findall(
                        r"^(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                        source,
                        flags=re.MULTILINE,
                    )
                )
                self.assertEqual(actual, names)

    def test_literal_sources_are_internal_and_algorithm_free(self) -> None:
        forbidden = (
            "public", "Identifiable", "Hashable", "Sendable", "@unchecked",
            "CryptoKit", "SHA256", "CanonicalJSON", "TypedID",
            "URLSession", "FileManager", "binding.v1", "event.v1",
            "decodeStorageV1", "reserveClientSequence", "appendEvent",
            "prepareLegacyV1Batch", "applyLegacyV1BatchResponse",
        )
        for relative in (EVENT, LEDGER, TRANSPORT):
            path = ROOT / relative
            self.assertTrue(
                path.is_file(),
                f"missing literal source: {relative.as_posix()}",
            )
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=relative, token=token):
                    self.assertNotIn(token, source)

    def test_server_sequence_exception_is_the_exact_surgical_file_roster(self) -> None:
        transport_path = ROOT / TRANSPORT
        self.assertTrue(
            transport_path.is_file(),
            f"missing literal source: {TRANSPORT.as_posix()}",
        )
        transport_source = transport_path.read_text(encoding="utf-8")
        self.assertEqual(transport_source.count("serverSequence"), 1)
        self.assertIn("let serverSequence: Int", transport_source)
        generated_path = ROOT / GENERATED_SHAPE
        generated_exists = generated_path.is_file()
        manifest = json.loads(
            (ROOT / "contracts/canonical/authority.json").read_text(
                encoding="utf-8"
            )
        )
        rules = manifest["forbiddenSymbols"]
        server_rules = [rule for rule in rules if rule["values"] == ["serverSequence"]]
        self.assertEqual(len(server_rules), 1)
        expected_exclusions = [f"!{TRANSPORT.as_posix()}"]
        if generated_exists:
            expected_exclusions.append(f"!{GENERATED_SHAPE.as_posix()}")
        self.assertEqual(
            server_rules[0]["paths"],
            [*PROTECTED_PATHS, *expected_exclusions],
        )
        common = [
            rule for rule in rules
            if set(rule["values"]) == {
                "weatherSnapshot", "weatherByHole", "WatchInputEvent",
                "autoshot_candidate",
            }
        ]
        self.assertEqual(len(common), 1)
        self.assertEqual(common[0]["paths"], PROTECTED_PATHS)

        # Stage A deliberately owns the sole generated-asset missing assertion
        # in test_storage_v1_shape_codec_assets.  Once that asset exists, this
        # same test tightens the authority exception and generated field audit.
        if not generated_exists:
            return
        generated_source = generated_path.read_text(encoding="utf-8")
        self.assertEqual(generated_source.count("serverSequence"), 1)
        occurrence = generated_source.index("serverSequence")
        receipt = generated_source.rfind("LegacyV1EventReceipt", 0, occurrence)
        self.assertGreaterEqual(
            receipt,
            0,
            "generated serverSequence is not in LegacyV1EventReceipt context",
        )
        self.assertLess(
            occurrence - receipt,
            1_500,
            "generated serverSequence is not a readable receipt field",
        )
        field_context = generated_source[
            max(receipt, occurrence - 180): occurrence + 180
        ]
        self.assertRegex(
            field_context,
            r"(?s)(?:\b(?:Int|int)\b.{0,120}serverSequence|"
            r"serverSequence.{0,120}\b(?:Int|int)\b)",
        )

        generator_path = ROOT / SHAPE_GENERATOR
        if not generator_path.is_file():
            return
        generator_source = generator_path.read_text(encoding="utf-8")
        known_obscuring_constructs = (
            r"server\s*['\"]\s*\+\s*['\"]Sequence",
            r"server\\u0053equence",
            r"server\\x53equence",
            r"base64\.(?:b64decode|decodebytes)",
            r"bytes\.fromhex\(",
            r"codecs\.decode\(",
        )
        for pattern in known_obscuring_constructs:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, generator_source))

    def test_new_sources_pass_the_repository_authority_gate(self) -> None:
        for relative in (EVENT, LEDGER, TRANSPORT):
            path = ROOT / relative
            self.assertTrue(
                path.is_file(),
                f"missing literal source: {relative.as_posix()}",
            )
        try:
            violations = check_authority(
                ROOT,
                changed_paths=[
                    EVENT.as_posix(), LEDGER.as_posix(),
                    TRANSPORT.as_posix(),
                ],
            )
        except AuthorityViolation as exc:
            self.fail(f"authority gate rejected storage sources: {exc}")
        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
