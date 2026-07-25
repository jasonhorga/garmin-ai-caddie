from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift"
AUTHORITY = ROOT / "contracts/canonical/authority.json"
STORAGE_SOURCES = [
    "contracts/storage-v1/**/*.json",
    "tools/contracts/generate_storage_v1_shape.py",
]
GENERATED_OUTPUT = "mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift"
TYPE_ROSTER = {
    "StoredEventV1",
    "OriginSequenceState",
    "CanonicalStringSet",
    "DomainLedgerStateV1",
    "LegacyDomainAlias",
    "LegacyWireBinding",
    "PreparedLegacyV1Slot",
    "PreparedLegacyV1Batch",
    "LegacyV1TerminalStatus",
    "LegacyV1EventReceipt",
    "LegacyV1OutboxRecord",
    "LegacyV1TransportAnomaly",
    "WatchTerminalReceiptRelayObligation",
    "WatchTerminalReceiptRelayConfirmation",
    "LegacyV1EventBatchBody",
    "RoundEventKind",
    "JSONValue",
}
HANDWRITTEN = {
    "codec": ROOT / "mobile/ios/AICaddieDomain/StorageV1ShapeCodec.swift",
    "streaming": (
        ROOT
        / "mobile/ios/AICaddieDomain/StorageV1StreamingShapeValidator.swift"
    ),
    "scalars": (
        ROOT / "mobile/ios/AICaddieDomain/StorageV1ShapeScalarValidation.swift"
    ),
    "metrics": ROOT / "mobile/ios/AICaddieDomain/StorageV1CanonicalMetrics.swift",
}


class StorageV1ShapeCodecAssetTests(unittest.TestCase):
    def _generated_source_or_none(self) -> str | None:
        if not GENERATED.is_file():
            return None
        return GENERATED.read_text(encoding="utf-8")

    def _handwritten_sources_or_none(self) -> dict[str, str] | None:
        if any(not path.is_file() for path in HANDWRITTEN.values()):
            return None
        return {
            name: path.read_text(encoding="utf-8")
            for name, path in HANDWRITTEN.items()
        }

    def test_000_generated_swift_asset_exists(self) -> None:
        self.assertTrue(
            GENERATED.is_file(),
            "missing generated storage-v1 shape asset: GeneratedStorageV1Shape.swift",
        )

    def test_storage_codegen_group_is_separate_and_has_exact_inputs_and_output(self) -> None:
        source = self._generated_source_or_none()
        if source is None:
            return
        manifest = json.loads(AUTHORITY.read_text(encoding="utf-8"))
        owners = [
            group
            for group in manifest["generatedGroups"]
            if GENERATED_OUTPUT in group["outputs"]
        ]
        self.assertEqual(len(owners), 1)
        storage_group = owners[0]
        self.assertEqual(set(storage_group), {"name", "sources", "outputs"})
        self.assertEqual(storage_group["sources"], STORAGE_SOURCES)
        self.assertEqual(storage_group["outputs"], [GENERATED_OUTPUT])
        self.assertEqual(manifest["canonicalRoots"], ["contracts/canonical"])
        self.assertNotIn("contracts/storage-v1", manifest["canonicalRoots"])
        canonical_owners = [
            group
            for group in manifest["generatedGroups"]
            if "ai_caddie/contracts/generated.py" in group["outputs"]
        ]
        self.assertEqual(len(canonical_owners), 1)
        self.assertIsNot(canonical_owners[0], storage_group)
        self.assertNotEqual(canonical_owners[0]["name"], storage_group["name"])

    def test_generated_descriptor_surface_is_internal_only(self) -> None:
        source = self._generated_source_or_none()
        if source is None:
            return
        for forbidden in ("public ", "package ", "@_spi", "@usableFromInline"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        declarations = re.findall(
            r"^(\S[^\n]*\b(?:enum|struct|protocol|typealias|let|var)\b[^\n]*)$",
            source,
            flags=re.MULTILINE,
        )
        self.assertTrue(declarations, "generated Swift has no declarations")
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                self.assertTrue(
                    declaration.startswith("internal "),
                    f"generated declaration is not explicitly internal: {declaration}",
                )

    def test_generated_output_references_but_never_redeclares_domain_types(self) -> None:
        source = self._generated_source_or_none()
        if source is None:
            return
        for name in TYPE_ROSTER:
            with self.subTest(type=name):
                self.assertIn(name, source)
                self.assertIsNone(
                    re.search(
                        rf"^(?:internal\s+)?(?:struct|enum|typealias)\s+{re.escape(name)}\b",
                        source,
                        flags=re.MULTILINE,
                    ),
                    f"generated storage descriptor redeclares {name}",
                )

    def test_generated_output_contains_only_descriptor_authority(self) -> None:
        source = self._generated_source_or_none()
        if source is None:
            return
        for required in (
            "storageDocument",
            "legacyV1EventBatchBody",
            "rootCollection",
            "preparedSlots",
            "requestBody",
            "eventOrEnvelope",
            "ordinaryString",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        for forbidden in (
            "JSONDecoder",
            "JSONSerialization",
            "URLSession",
            "FileManager",
            "decodeStorageV1",
            "preparedLegacyV1Batches[*]",
            "events[*]",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_generated_limits_reference_existing_authorities_without_shadows(self) -> None:
        source = self._generated_source_or_none()
        if source is None:
            return
        for symbol in (
            "StorageV1RawJSONGate.maximumStringScalars",
            "RoundTransportLimits.maxHttpBodyBytes",
            "RoundTransportLimits.maxEventsPerBatch",
            "RoundTransportLimits.maxEventCanonicalBytes",
            "RoundTransportLimits.maxEventJsonDepth",
            "RoundTransportLimits.maxJsonStringCharacters",
        ):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, source)
        for forbidden_literal in (
            r"\b1_?398_?104\b",
            r"\b1_?048_?576\b",
            r"\b4_?096\b",
            r"\b64\b",
            r"\b16\b",
        ):
            with self.subTest(literal=forbidden_literal):
                self.assertIsNone(re.search(forbidden_literal, source))
        self.assertEqual(len(re.findall(r"\b65_?536\b", source)), 1)

    def test_100_exact_handwritten_runtime_sources_exist(self) -> None:
        missing = [
            path.relative_to(ROOT).as_posix()
            for path in HANDWRITTEN.values()
            if not path.is_file()
        ]
        self.assertEqual(
            missing,
            [],
            "missing handwritten storage-v1 shape source(s): "
            + ", ".join(missing),
        )

    def test_handwritten_surface_is_internal_and_has_one_capability_entry(self) -> None:
        sources = self._handwritten_sources_or_none()
        if sources is None:
            return
        combined = "\n".join(sources.values())
        for forbidden in (
            "public ",
            "package ",
            "@_spi",
            "@usableFromInline",
            "open ",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

        codec = sources["codec"]
        self.assertRegex(
            codec,
            r"(?s)internal\s+struct\s+ValidatedStorageV1Shape\s*\{"
            r".*?internal\s+let\s+state\s*:\s*DomainLedgerStateV1\b"
            r".*?fileprivate\s+init\s*\(\s*state\s*:\s*"
            r"DomainLedgerStateV1\s*\)",
        )
        self.assertNotRegex(
            codec,
            r"\b(?:var|private\s+let|fileprivate\s+let|public\s+let|"
            r"package\s+let)\s+state\b",
        )
        entries = re.findall(r"\bfunc\s+decode\s*\(", combined)
        self.assertEqual(entries, ["func decode("], "codec must have one decode entry")
        self.assertRegex(
            codec,
            r"(?s)internal\s+static\s+func\s+decode\s*\(\s*"
            r"_\s+validatedRawJSON\s*:\s*"
            r"StorageV1RawJSONGate\.ValidatedRawJSON\s*\)\s*throws\s*"
            r"->\s*ValidatedStorageV1Shape\b",
        )
        self.assertNotRegex(
            codec,
            r"\bfunc\s+decode\s*\([^)]*\b(?:Data|String|JSONValue|"
            r"JSONDecoder)\b",
        )

    def test_handwritten_responsibilities_have_no_bypass_or_fake_runtime(self) -> None:
        sources = self._handwritten_sources_or_none()
        if sources is None:
            return
        combined = "\n".join(sources.values())
        for forbidden in (
            "JSONSerialization",
            "fatalError(",
            "preconditionFailure(",
            "[*]",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)
        self.assertIsNone(
            re.search(
                r"\b(?:tokens|events)\s*:\s*\[\s*"
                r"(?:StorageV1RawJSONGate\.)?Event\s*\]",
                combined,
            ),
            "streaming validation must not retain a token/event array",
        )

        seam_owners = [
            name for name, source in sources.items() if "notImplemented" in source
        ]
        cursor_owners = [
            name for name, source in sources.items() if ".makeCursor(" in source
        ]
        decoder_pattern = re.compile(
            r"JSONDecoder\s*\(\s*\)\s*\.decode\s*\(\s*"
            r"DomainLedgerStateV1\.self\s*,"
        )
        decoder_owners = [
            name for name, source in sources.items() if decoder_pattern.search(source)
        ]
        all_decoder_mentions = sum(
            source.count("JSONDecoder") for source in sources.values()
        )

        if seam_owners:
            self.assertEqual(seam_owners, ["codec"])
            self.assertEqual(cursor_owners, [])
            self.assertEqual(decoder_owners, [])
            self.assertEqual(all_decoder_mentions, 0)
        else:
            self.assertEqual(cursor_owners, ["codec"])
            self.assertEqual(sources["codec"].count(".makeCursor("), 1)
            self.assertEqual(decoder_owners, ["codec"])
            self.assertEqual(len(decoder_pattern.findall(sources["codec"])), 1)
            self.assertEqual(all_decoder_mentions, 1)


if __name__ == "__main__":
    unittest.main()
