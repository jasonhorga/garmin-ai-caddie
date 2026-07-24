from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import rfc8785
import yaml


ROOT = Path(__file__).resolve().parents[1]

PINNED_FILES = {
    "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/JSONCanonicalization.swift": (
        "22a38cf5cda61062cf3a61688474e4dba796a8eea1bfb2ca8c977587deddbc9c"
    ),
    "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/NumberSerializer.swift": (
        "acdedc57a40e8ceb66ff640a82d84b7e340617670aff955b4679df43b3816502"
    ),
    "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/StringSerializer.swift": (
        "cbb40f06dbb35c43ca9db9e0637cb6baaaf82844d673476363c548556ec91464"
    ),
    "mobile/ios/ThirdPartyLicenses/swift-jcs-UNLICENSE": (
        "b5065838cbac452dfc855ba6e6e031481ad2c68406f70d21ead9321374653e6c"
    ),
}

EXPECTED_PROVENANCE = {
    "repository": "https://github.com/minacle/swift-jcs",
    "commit": "1e69befe76f5445696e821811402c586dd2186d8",
    "license": "Unlicense",
    "files": {
        "JSONCanonicalization.swift": (
            "22a38cf5cda61062cf3a61688474e4dba796a8eea1bfb2ca8c977587deddbc9c"
        ),
        "NumberSerializer.swift": (
            "acdedc57a40e8ceb66ff640a82d84b7e340617670aff955b4679df43b3816502"
        ),
        "StringSerializer.swift": (
            "cbb40f06dbb35c43ca9db9e0637cb6baaaf82844d673476363c548556ec91464"
        ),
        "UNLICENSE": (
            "b5065838cbac452dfc855ba6e6e031481ad2c68406f70d21ead9321374653e6c"
        ),
    },
}

OFFICIAL_BIT_PATTERNS = (
    0x0000000000000000,
    0x0000000000000001,
    0x8000000000000001,
    0x7FEFFFFFFFFFFFFF,
    0xFFEFFFFFFFFFFFFF,
    0x4340000000000000,
    0xC340000000000000,
    0x4430000000000000,
    0x44B52D02C7E14AF5,
    0x44B52D02C7E14AF6,
    0x44B52D02C7E14AF7,
    0x444B1AE4D6E2EF4E,
    0x444B1AE4D6E2EF4F,
    0x444B1AE4D6E2EF50,
    0x3EB0C6F7A0B5ED8C,
    0x3EB0C6F7A0B5ED8D,
    0x41B3DE4355555553,
    0x41B3DE4355555554,
    0x41B3DE4355555555,
    0x41B3DE4355555556,
    0x41B3DE4355555557,
    0xBECBF647612F3696,
    0x43143FF3C1CB0959,
)

VECTOR_FIXTURE = Path(
    "mobile/ios/AICaddieDomainTests/Fixtures/rfc8785_number_vectors.json"
)
VECTOR_GENERATOR = Path("tools/contracts/generate_rfc8785_vectors.py")
PROVENANCE = Path("mobile/ios/ThirdPartyLicenses/swift-jcs-provenance.json")


def _as_double(bits: int) -> float:
    return struct.unpack(">d", bits.to_bytes(8, "big"))[0]


def _expected_bit_pattern_roster() -> list[str]:
    bits = list(OFFICIAL_BIT_PATTERNS)
    state = 0xA1CADD1E5EED1234
    while len(bits) < 2_048:
        state = (
            state * 6364136223846793005 + 1442695040888963407
        ) & ((1 << 64) - 1)
        value = _as_double(state)
        if math.isfinite(value) and not (
            value == 0.0 and math.copysign(1.0, value) < 0
        ):
            bits.append(state)
    return [f"{item:016x}" for item in bits]


class SwiftCanonicalRuntimeAssetTests(unittest.TestCase):
    def test_pinned_swift_jcs_files_have_exact_paths_and_sha256(self) -> None:
        for relative, expected_sha256 in PINNED_FILES.items():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(
                    path.is_file(),
                    f"missing pinned SwiftJCS runtime asset: {relative}",
                )
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected_sha256,
                    f"pinned SwiftJCS SHA-256 drift: {relative}",
                )

    def test_swift_jcs_provenance_is_exact(self) -> None:
        path = ROOT / PROVENANCE
        self.assertTrue(
            path.is_file(),
            f"missing pinned SwiftJCS provenance: {PROVENANCE}",
        )
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")),
            EXPECTED_PROVENANCE,
        )

    def test_vector_generator_contains_frozen_lcg_contract(self) -> None:
        path = ROOT / VECTOR_GENERATOR
        self.assertTrue(
            path.is_file(),
            f"missing deterministic RFC 8785 vector generator: {VECTOR_GENERATOR}",
        )
        source = path.read_text(encoding="utf-8")
        for literal in (
            "state = 0xA1CADD1E5EED1234",
            "state * 6364136223846793005 + 1442695040888963407",
            "while len(bits) < 2_048:",
        ):
            with self.subTest(literal=literal):
                self.assertIn(literal, source)

    def test_checked_in_vector_fixture_has_exact_2048_entry_roster(self) -> None:
        path = ROOT / VECTOR_FIXTURE
        self.assertTrue(
            path.is_file(),
            f"missing checked-in RFC 8785 number fixture: {VECTOR_FIXTURE}",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 2_048)

        for index, row in enumerate(payload):
            with self.subTest(index=index):
                self.assertIsInstance(row, dict)
                self.assertEqual(set(row), {"bitPatternHex", "expected"})
                self.assertIsInstance(row["bitPatternHex"], str)
                self.assertIsInstance(row["expected"], str)
                self.assertTrue(row["expected"])

        actual_bits = [row["bitPatternHex"] for row in payload]
        official_bits = [f"{item:016x}" for item in OFFICIAL_BIT_PATTERNS]
        self.assertEqual(actual_bits[: len(official_bits)], official_bits)
        self.assertEqual(actual_bits, _expected_bit_pattern_roster())

    def test_vector_generator_reproduces_checked_in_bytes(self) -> None:
        generator = ROOT / VECTOR_GENERATOR
        fixture = ROOT / VECTOR_FIXTURE
        self.assertTrue(
            generator.is_file(),
            f"missing deterministic RFC 8785 vector generator: {VECTOR_GENERATOR}",
        )
        self.assertTrue(
            fixture.is_file(),
            f"missing checked-in RFC 8785 number fixture: {VECTOR_FIXTURE}",
        )

        with tempfile.TemporaryDirectory(prefix="swift-canonical-vectors-") as tmp:
            result = subprocess.run(
                [sys.executable, str(generator)],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"vector generator failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            regenerated = Path(tmp) / VECTOR_FIXTURE
            self.assertTrue(
                regenerated.is_file(),
                f"vector generator did not create {VECTOR_FIXTURE}",
            )
            self.assertEqual(regenerated.read_bytes(), fixture.read_bytes())

    def test_every_vector_expected_matches_locked_python_rfc8785(self) -> None:
        path = ROOT / VECTOR_FIXTURE
        self.assertTrue(
            path.is_file(),
            f"missing checked-in RFC 8785 number fixture: {VECTOR_FIXTURE}",
        )
        self.assertEqual(importlib.metadata.version("rfc8785"), "0.1.4")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 2_048)

        for row in payload:
            bits = int(row["bitPatternHex"], 16)
            self.assertEqual(
                row["expected"],
                rfc8785.dumps(_as_double(bits)).decode("ascii"),
                row["bitPatternHex"],
            )

    def test_swift_package_copies_domain_fixtures_byte_for_byte(self) -> None:
        package = (ROOT / "Package.swift").read_text(encoding="utf-8")
        match = re.search(
            r'\.testTarget\(\s*name: "AICaddieDomainTests",(?P<body>.*?)\n\s*\),',
            package,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "missing AICaddieDomainTests Swift package target")
        assert match is not None
        target = match.group("body")
        self.assertIn('resources: [.copy("Fixtures")]', target)
        self.assertNotIn('.process("Fixtures")', target)

    def test_xcode_scheme_runs_domain_tests_in_normal_ios_job(self) -> None:
        project = yaml.safe_load(
            (ROOT / "mobile/ios/project.yml").read_text(encoding="utf-8")
        )
        self.assertIn("schemes", project)
        self.assertIn("AICaddie", project["schemes"])
        scheme = project["schemes"]["AICaddie"]
        self.assertIn("AICaddieDomainTests", scheme["build"]["targets"])
        self.assertEqual(
            scheme["build"]["targets"]["AICaddieDomainTests"],
            ["test"],
        )
        self.assertIn("AICaddieDomainTests", scheme["test"]["targets"])


if __name__ == "__main__":
    unittest.main()
