from __future__ import annotations

import ast
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.contracts import generate_contracts as contract_codegen


GENERATED_OUTPUTS = {
    "ai_caddie/contracts/generated.py",
    "mobile/ios/AICaddieDomain/GeneratedContracts.swift",
    "web_v2/src/contracts/generated.ts",
}

ROUND_TRANSPORT_LIMITS = {
    "maxConsumerEpochCharacters": 128,
    "maxDeadLetterPageSize": 100,
    "maxDeadLetterRetainedBytes": 16384,
    "maxDeadLettersPerRound": 2048,
    "maxEventCanonicalBytes": 65536,
    "maxEventJsonDepth": 16,
    "maxEventsPerBatch": 64,
    "maxHttpBodyBytes": 1048576,
    "maxJsonKeyCharacters": 128,
    "maxJsonStringCharacters": 4096,
    "maxMergeSourceIncarnations": 8,
    "maxRawJsonDepth": 64,
    "maxReplayPageSize": 500,
    "maxSyncPathIdCharacters": 128,
}


class ContractCodegenTests(unittest.TestCase):
    def test_checked_in_outputs_match_all_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path(tmp))
            self.assertEqual(set(outputs), GENERATED_OUTPUTS)
            for relative, generated in outputs.items():
                self.assertEqual(Path(relative).read_bytes(), generated.encode("utf-8"), relative)

    def test_all_outputs_contain_descriptor_reason_and_limit_tables(self) -> None:
        outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path("."))
        for relative, generated in outputs.items():
            with self.subTest(relative=relative):
                self.assertIn("CanonicalFixtureAlpha/v1", generated)
                self.assertIn("round_binding_mismatch", generated)
                self.assertIn("maxEventsPerBatch", generated)

    def test_generated_declarations_are_schema_owner_gated(self) -> None:
        outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path("."))

        python_namespace: dict[str, object] = {}
        exec(outputs["ai_caddie/contracts/generated.py"], python_namespace)
        self.assertEqual(python_namespace["EVENT_KINDS"], ())
        self.assertEqual(python_namespace["EVENT_SUBMISSION_CLASSES"], {})
        self.assertIn("round_binding_mismatch", python_namespace["REASON_CODES"])
        self.assertEqual(python_namespace["ROUND_TRANSPORT_LIMITS"], ROUND_TRANSPORT_LIMITS)

        swift = outputs["mobile/ios/AICaddieDomain/GeneratedContracts.swift"]
        self.assertIn("public enum RoundEventSubmissionClass: String, Codable, Sendable", swift)
        self.assertIn("public static let knownValues: Set<String> = []", swift)
        self.assertIn(
            "public static let submissionClasses: [String: RoundEventSubmissionClass] = [:]",
            swift,
        )
        self.assertIn(
            'public static let roundBindingMismatch = ReasonCode(rawValue: "round_binding_mismatch")',
            swift,
        )
        kind_declarations = swift.split("public struct RoundEventKind", 1)[1].split(
            "public struct ReasonCode", 1
        )[0]
        self.assertNotIn("RoundEventKind(rawValue:", kind_declarations)

        typescript = outputs["web_v2/src/contracts/generated.ts"]
        self.assertIn("export const roundEventKinds = [] as const", typescript)
        self.assertIn("export const roundEventSubmissionClasses = {} as const", typescript)
        self.assertIn(
            "export type RoundEventKind = typeof roundEventKinds[number] | (string & {})",
            typescript,
        )

    def test_swift_name_is_deterministic_lower_camel_case(self) -> None:
        self.assertEqual(
            contract_codegen._swift_name("round_binding_mismatch"),
            "roundBindingMismatch",
        )
        self.assertEqual(
            contract_codegen._swift_name("ordinary_or_resolution_commit"),
            "ordinaryOrResolutionCommit",
        )

    def test_event_and_reason_registries_reject_duplicate_keys(self) -> None:
        duplicate_registries = {
            "event_kind_registry.json": (
                b'{"schema":"ai-caddie-event-kind-registry-v1","kinds":{},"kinds":{}}\n',
                "kinds",
            ),
            "reason_codes.json": (
                b'{"schema":"ai-caddie-reason-code-registry-v1","codes":[],"codes":[],'
                b'"roundTransportLimits":{}}\n',
                "codes",
            ),
        }
        for filename, (contents, duplicate_key) in duplicate_registries.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                registry_root = repo_root / "contracts/canonical"
                shutil.copytree(Path("contracts/canonical"), registry_root)
                generator_copy = repo_root / "tools/contracts/generate_contracts.py"
                generator_copy.parent.mkdir(parents=True)
                shutil.copy2(Path("tools/contracts/generate_contracts.py"), generator_copy)
                (registry_root / "event_kind_registry.json").write_bytes(
                    b'{"schema":"ai-caddie-event-kind-registry-v1","kinds":{}}\n'
                )
                (registry_root / "reason_codes.json").write_bytes(
                    b'{"schema":"ai-caddie-reason-code-registry-v1","codes":[],'
                    b'"roundTransportLimits":{}}\n'
                )
                (registry_root / filename).write_bytes(contents)

                with self.assertRaisesRegex(ValueError, f"duplicate JSON key: {duplicate_key}"):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_swift_package_declares_shared_domain_targets_and_resources(self) -> None:
        package = Path("Package.swift").read_text(encoding="utf-8")
        self.assertIn('.library(name: "AICaddieDomain", targets: ["AICaddieDomain"])', package)
        self.assertIn(
            'name: "AICaddieDomain",\n            path: "mobile/ios/AICaddieDomain"',
            package,
        )
        self.assertIn(
            'name: "AICaddieDomainTests",\n'
            '            dependencies: ["AICaddieDomain"],\n'
            '            path: "mobile/ios/AICaddieDomainTests",\n'
            '            resources: [.process("Fixtures")]',
            package,
        )
        self.assertIn(
            'name: "AICaddie",\n            dependencies: ["AICaddieDomain"],',
            package,
        )
        self.assertIn(
            'name: "AICaddieWatch",\n            dependencies: ["AICaddieDomain"],',
            package,
        )

    def test_xcodegen_declares_multidestination_domain_targets_and_dependencies(self) -> None:
        project = yaml.safe_load(Path("mobile/ios/project.yml").read_text(encoding="utf-8"))
        targets = project["targets"]

        domain = targets["AICaddieDomain"]
        self.assertEqual(domain["type"], "framework")
        self.assertEqual(domain["platform"], "auto")
        self.assertEqual(set(domain["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertIn({"path": "mobile/ios/AICaddieDomain"}, domain["sources"])

        domain_tests = targets["AICaddieDomainTests"]
        self.assertEqual(domain_tests["type"], "bundle.unit-test")
        self.assertEqual(domain_tests["platform"], "auto")
        self.assertEqual(set(domain_tests["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertIn({"target": "AICaddieDomain"}, domain_tests["dependencies"])
        self.assertIn(
            {"path": "mobile/ios/AICaddieDomainTests", "excludes": ["Fixtures"]},
            domain_tests["sources"],
        )
        self.assertIn(
            {
                "path": "mobile/ios/AICaddieDomainTests/Fixtures",
                "buildPhase": "resources",
            },
            domain_tests["sources"],
        )

        ios_dependencies = {entry["target"] for entry in targets["AICaddie"]["dependencies"]}
        self.assertEqual(ios_dependencies, {"AICaddieDomain", "AICaddieWatch"})
        watch_dependencies = {
            entry["target"] for entry in targets["AICaddieWatch"]["dependencies"]
        }
        self.assertEqual(watch_dependencies, {"AICaddieDomain"})

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
