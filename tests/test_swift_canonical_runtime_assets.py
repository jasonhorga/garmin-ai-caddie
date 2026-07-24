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
VENDOR_ROOT = Path("mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS")
EXPECTED_VENDOR_FILES = {
    Path(relative)
    for relative in PINNED_FILES
    if relative.startswith(f"{VENDOR_ROOT.as_posix()}/")
}


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_unique_json(path: Path) -> object:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )


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
    def test_vendor_source_roster_is_exact(self) -> None:
        root = ROOT / VENDOR_ROOT
        self.assertTrue(
            root.is_dir(),
            f"missing pinned SwiftJCS source directory: {VENDOR_ROOT}",
        )
        actual = {
            path.relative_to(ROOT)
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_VENDOR_FILES)
        self.assertTrue(all(path.suffix == ".swift" for path in actual))

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
            _load_unique_json(path),
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
        payload = _load_unique_json(path)
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
        payload = _load_unique_json(path)
        self.assertEqual(len(payload), 2_048)

        for row in payload:
            bits = int(row["bitPatternHex"], 16)
            self.assertEqual(
                row["expected"],
                rfc8785.dumps(_as_double(bits)).decode("ascii"),
                row["bitPatternHex"],
            )

    def test_vendor_serializer_has_no_production_bypass_calls(self) -> None:
        domain_root = ROOT / "mobile/ios/AICaddieDomain"
        bypasses: list[str] = []
        for path in domain_root.rglob("*.swift"):
            if path.is_relative_to(ROOT / VENDOR_ROOT):
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if "_serializeNumber(" not in line:
                    continue
                if re.search(r"\bfunc\s+_serializeNumber\s*\(", line):
                    continue
                bypasses.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual(bypasses, [])

        vendor_api_calls: list[str] = []
        for path in domain_root.rglob("*.swift"):
            if path.is_relative_to(ROOT / VENDOR_ROOT):
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if "JSONCanonicalization." in line:
                    vendor_api_calls.append(
                        f"{path.relative_to(ROOT)}:{line_number}"
                    )
        self.assertEqual(
            [entry.rsplit(":", 1)[0] for entry in vendor_api_calls],
            ["mobile/ios/AICaddieDomain/CanonicalJSON.swift"],
        )

    def test_swift_package_isolates_swift_jcs_as_non_product_target(self) -> None:
        package = (ROOT / "Package.swift").read_text(encoding="utf-8")
        products = package.split("products: [", 1)[1].split("],\n    targets:", 1)[0]
        self.assertNotIn('name: "SwiftJCS"', products)
        self.assertRegex(
            package,
            r'\.target\(\s*name: "SwiftJCS",\s*'
            r'path: "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS"\s*\)',
        )

        domain = re.search(
            r'\.target\(\s*name: "AICaddieDomain",(?P<body>.*?)\n\s*\),',
            package,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(domain, "missing AICaddieDomain Swift package target")
        assert domain is not None
        self.assertIn('dependencies: ["SwiftJCS"]', domain["body"])
        self.assertIn('exclude: ["ThirdParty/SwiftJCS"]', domain["body"])

        domain_tests = re.search(
            r'\.testTarget\(\s*name: "AICaddieDomainTests",'
            r'(?P<body>.*?)\n\s*\),',
            package,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            domain_tests,
            "missing AICaddieDomainTests Swift package target",
        )
        assert domain_tests is not None
        self.assertIn(
            'dependencies: ["AICaddieDomain", "SwiftJCS"]',
            domain_tests["body"],
        )

    def test_xcodegen_isolates_swift_jcs_as_implementation_target(self) -> None:
        project = yaml.safe_load(
            (ROOT / "mobile/ios/project.yml").read_text(encoding="utf-8")
        )
        targets = project["targets"]
        swift_jcs = targets["SwiftJCS"]
        self.assertEqual(swift_jcs["type"], "library.static")
        self.assertEqual(swift_jcs["platform"], "auto")
        self.assertEqual(set(swift_jcs["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertEqual(
            swift_jcs["sources"],
            [{"path": VENDOR_ROOT.as_posix()}],
        )

        domain = targets["AICaddieDomain"]
        self.assertEqual(
            domain["sources"],
            [
                {
                    "path": "mobile/ios/AICaddieDomain",
                    "excludes": ["ThirdParty/SwiftJCS"],
                }
            ],
        )
        self.assertIn(
            {"target": "SwiftJCS", "link": True},
            domain["dependencies"],
        )
        self.assertIn(
            {"target": "SwiftJCS", "link": True},
            targets["AICaddieDomainTests"]["dependencies"],
        )

        for scheme in project["schemes"].values():
            self.assertNotIn("SwiftJCS", scheme.get("build", {}).get("targets", {}))

        wrapper = (
            ROOT / "mobile/ios/AICaddieDomain/CanonicalJSON.swift"
        ).read_text(encoding="utf-8")
        domain_tests = (
            ROOT / "mobile/ios/AICaddieDomainTests/CanonicalJSONTests.swift"
        ).read_text(encoding="utf-8")
        self.assertIn("import SwiftJCS", wrapper.splitlines())
        self.assertNotIn("@_exported import SwiftJCS", wrapper)
        self.assertIn("@testable import SwiftJCS", domain_tests.splitlines())

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

    def test_native_workflow_runs_generated_aicaddie_scheme(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/native-mobile.yml").read_text(
                encoding="utf-8"
            )
        )
        steps = {
            step["name"]: step
            for step in workflow["jobs"]["native-mobile"]["steps"]
            if "name" in step
        }
        self.assertEqual(
            steps["Generate native project"]["run"],
            "xcodegen generate --spec mobile/ios/project.yml --project-root .",
        )
        ios_test = steps["Test iOS app target"]["run"]
        self.assertIn("-project mobile/ios/AICaddieNative.xcodeproj", ios_test)
        self.assertIn("-scheme AICaddie", ios_test)

        visibility_step = steps["Verify SwiftJCS consumer boundaries"]
        self.assertEqual(visibility_step["if"], "always()")
        visibility_gate = visibility_step["run"]
        self.assertIn('name: "ExternalAICaddieConsumer"', visibility_gate)
        self.assertIn("platforms: [.iOS(.v17)]", visibility_gate)
        self.assertIn(
            '.package(name: "AICaddieSource", path: "$GITHUB_WORKSPACE")',
            visibility_gate,
        )
        self.assertEqual(visibility_gate.count(".product("), 2)
        self.assertEqual(visibility_gate.count('name: "AICaddieDomain"'), 2)
        self.assertIn("--target PositiveConsumer", visibility_gate)
        self.assertIn("--target ExplicitSwiftJCSConsumer", visibility_gate)
        self.assertEqual(
            visibility_gate.count('--triple "$ARCH-apple-ios17.0-simulator"'),
            2,
        )
        self.assertEqual(visibility_gate.count('--sdk "$SDK"'), 2)
        self.assertIn("import AICaddieDomain", visibility_gate)
        self.assertIn("JSONValue.null", visibility_gate)
        self.assertIn("CanonicalJSON.data", visibility_gate)
        self.assertIn("TypedID.make", visibility_gate)
        self.assertEqual(visibility_gate.count("import SwiftJCS"), 2)
        self.assertEqual(
            visibility_gate.count("JSONCanonicalization.data"),
            2,
        )
        self.assertIn("ditto", visibility_gate)
        self.assertIn('"$DOMAIN_FRAMEWORK"', visibility_gate)
        self.assertIn(
            '"$FRAMEWORK_ARTIFACT/AICaddieDomain.framework"',
            visibility_gate,
        )
        self.assertNotIn('-I "$(dirname "$DOMAIN_FRAMEWORK")"', visibility_gate)
        self.assertIn("xcrun swiftc -typecheck", visibility_gate)
        self.assertLess(
            visibility_gate.index("CanonicalJSON.data"),
            visibility_gate.index("JSONCanonicalization"),
        )
        self.assertEqual(
            visibility_gate.count("no such module 'SwiftJCS'"),
            2,
        )


if __name__ == "__main__":
    unittest.main()
