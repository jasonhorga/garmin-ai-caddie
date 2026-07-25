from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift")
SWIFT_TEST = Path(
    "mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift"
)


class StorageV1RawJSONGateAssetTests(unittest.TestCase):
    def source(self) -> str:
        path = ROOT / SOURCE
        self.assertTrue(path.is_file(), f"missing raw JSON gate: {SOURCE}")
        return path.read_text(encoding="utf-8")

    def test_exact_limits_and_single_gate_roster(self) -> None:
        source = self.source()
        for literal in (
            "maximumDocumentBytes = 67_108_864",
            "maximumDepth = RoundTransportLimits.maxRawJsonDepth",
            "maximumKeyScalars = RoundTransportLimits.maxJsonKeyCharacters",
            "maximumStringScalars = 1_398_104",
        ):
            with self.subTest(literal=literal):
                self.assertEqual(source.count(literal), 1)
        self.assertEqual(
            re.findall(
                r"^(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                source,
                flags=re.MULTILINE,
            ),
            ["StorageV1RawJSONGate"],
        )

    def test_capability_is_internal_nonforgeable_and_replayable(self) -> None:
        source = self.source()
        self.assertNotRegex(source, r"\bpublic\b")
        self.assertIn("struct ValidatedRawJSON", source)
        self.assertNotRegex(source, r"struct ValidatedRawJSON\s*:")
        capability = source.split("struct ValidatedRawJSON {", 1)[1].split(
            "\n    final class Cursor", 1
        )[0]
        self.assertEqual(capability.count("init("), 1)
        self.assertIn("fileprivate init(", capability)
        self.assertIn("private let data: Data", capability)
        self.assertIn("sourceIdentity: SourceIdentity", capability)
        self.assertIn("func exactBytes() -> Data", capability)
        self.assertEqual(source.count("ValidatedRawJSON("), 1)
        self.assertNotIn("init(data: Data)", source)
        self.assertNotIn("init(_ data: Data)", source)
        self.assertIn("func makeCursor() -> Cursor", source)
        self.assertIn("func rawBytes(for event: Event)", source)
        self.assertIn("final class Cursor", source)
        self.assertIn("func next() throws -> Event?", source)
        self.assertIn("fileprivate let byteRange: Range<Data.Index>", source)
        self.assertIn("let stringScalarCount: Int?", source)
        self.assertIn("let decodedStringUTF8: Data?", source)
        self.assertIn("fileprivate let sourceIdentity: SourceIdentity", source)

    def test_scanner_is_iterative_and_does_not_materialize_json(self) -> None:
        source = self.source()
        required = (
            "private var frames: [Frame] = []",
            "private final class ObjectKeySet",
            "var values: Set<Data> = []",
            "objectKeys.values.insert(decodedKey)",
            "self.frames.reserveCapacity(",
            "consumeUnescapedScalar",
            "consumeEscapedScalar",
            "consumeNumber",
            "var unescapedRunStart = index",
            "data[unescapedRunStart..<index]",
            "while try cursor.next() != nil {}",
            "immutableSnapshot(of: data)",
            "withUnsafeBytes",
            "Data(bytes: baseAddress, count: bytes.count)",
        )
        for literal in required:
            with self.subTest(literal=literal):
                self.assertIn(literal, source)

        forbidden = (
            "JSONSerialization", "JSONDecoder", "JSONEncoder",
            "JSONObjectWithData", "Array(data)", "Array(data[",
            "String(data:", "String(decoding:", "NSJSON", "NSNumber",
            "Decimal", "Base64", "base64", "precomposedString",
            "CanonicalJSON", "DomainLedgerStateV1", "JSONValue",
            "Set<String>", "Codable", "Decodable", "URLSession",
            "FileManager", "maxJsonStringCharacters", "maxEventsPerBatch",
            "maxHttpBodyBytes", "reserveCapacity(128)",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_xctest_source_pins_adversarial_and_deferred_vectors(self) -> None:
        path = ROOT / SWIFT_TEST
        self.assertTrue(path.is_file(), f"missing raw-gate tests: {SWIFT_TEST}")
        source = path.read_text(encoding="utf-8")
        for literal in (
            r'"a":1,"\u0061":2',
            r'"😀":1,"\uD83D\uDE00":2',
            r'"é":1,"e\u0301":2',
            "maximumDocumentBytes - 1",
            "String(repeating: \"[\", count: 64)",
            "String(repeating: \"[\", count: 65)",
            "String(repeating: \"😀\", count: 128)",
            "maximumStringScalars + 1",
            "String(repeating: \"x\", count: 4_097)",
            "for item in 0...65_536",
            "var largeObject = Data([0x7B])",
            "%%%not canonical base64",
            r'"exactRequestBody":"%%%not-base64%%%=="',
            "1234567890123456789012345678901234567890e-999999",
            r'"roundId":"round-1","events"',
            "0xF4, 0x8F, 0xBF, 0xBF",
            "1E+00",
            "// comment\\n0",
            "testEverySimpleEscapeDecodesToExactBytes",
            "repeating: \"\\\\uD83D\\\\uDE00\"",
            "0x22, 0xE2, 0x82",
            "Data(referencing: mutable)",
            "XCTAssertEqual(aliased, Data(\"x\".utf8))",
            "otherSource.rawBytes(for: number)",
            "decodedStringUTF8",
            "cursor === alias",
            r'#""\q""#',
        ):
            with self.subTest(literal=literal):
                self.assertIn(literal, source)

    def test_new_source_passes_repository_authority_gate(self) -> None:
        self.source()
        try:
            violations = check_authority(
                ROOT,
                changed_paths=[SOURCE.as_posix()],
            )
        except AuthorityViolation as exc:
            self.fail(f"authority gate rejected raw JSON gate: {exc}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
