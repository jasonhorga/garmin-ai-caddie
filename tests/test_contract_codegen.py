from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from tools.contracts import generate_contracts as contract_codegen


GENERATED_OUTPUTS = {
    "ai_caddie/contracts/generated.py",
    "mobile/ios/AICaddieDomain/GeneratedContracts.swift",
    "web_v2/src/contracts/generated.ts",
}
CANONICAL_OBJECT_DESCRIPTORS = {
    "CanonicalFixtureAlpha": {
        "domainTag": "CanonicalFixtureAlpha/v1",
        "schemaRef": "contracts/canonical/canonical_fixture_v1.schema.json",
        "includedFields": ["*"],
        "excludedFields": ["transportNote"],
    },
    "CanonicalFixtureBeta": {
        "domainTag": "CanonicalFixtureBeta/v1",
        "schemaRef": "contracts/canonical/canonical_fixture_v1.schema.json",
        "includedFields": ["*"],
        "excludedFields": ["transportNote"],
    },
}
SHARED_RESOURCE_OUTPUTS = {
    "mobile/ios/AICaddieTests/Fixtures/mobile_event_sanitizer_golden.json",
}
MOBILE_EVENT_SANITIZER_SHA256 = (
    "123cba00d8ead0ab2388f508bc9119eba4ba888755b087924839f57947e8aa37"
)

EVENT_KIND_REGISTRY = {
    "schema": "ai-caddie-event-kind-registry-v1",
    "kinds": {},
}

REASON_CODES = (
    "actor_not_authorized",
    "account_principal_conflict",
    "binding_not_established",
    "bootstrap_required",
    "consumer_ack_ahead_of_stream",
    "invalid_device_proof",
    "entity_base_revision_conflict",
    "event_batch_too_large",
    "event_envelope_limit_exceeded",
    "dead_letter_quota_exceeded",
    "flag_position_not_player_set",
    "identity_envelope_mismatch",
    "idempotency_key_body_mismatch",
    "merge_semantic_binding_mismatch",
    "merge_control_not_ready",
    "missing_event_receipt",
    "payload_schema_invalid",
    "peer_ledger_bundle_invalid",
    "player_cancelled_target",
    "projection_dependency_cycle",
    "request_body_too_large",
    "replay_gap_detected",
    "illegal_lifecycle_transition",
    "green_surface_quarantined",
    "legacy_migration_invalid_payload",
    "legacy_migration_malformed",
    "legacy_migration_unmappable",
    "resolution_episode_conflict",
    "resolution_commit_conflict",
    "resolution_commit_invalid_bundle",
    "resolution_commit_required",
    "resolution_episode_terminal",
    "resolution_required_cause_missing",
    "round_binding_mismatch",
    "round_start_authority_unavailable",
    "round_start_binding_rejected",
    "round_start_intent_conflict",
    "shot_identity_conflict",
    "shot_location_unavailable",
    "shot_target_not_player_confirmed",
    "shot_target_orphaned",
    "transport_receipt_hash_mismatch",
    "unknown_event_kind",
    "unsupported_client_version",
)

ROUND_TRANSPORT_LIMITS = {
    "maxHttpBodyBytes": 1048576,
    "maxEventsPerBatch": 64,
    "maxEventCanonicalBytes": 65536,
    "maxEventJsonDepth": 16,
    "maxRawJsonDepth": 64,
    "maxJsonKeyCharacters": 128,
    "maxJsonStringCharacters": 4096,
    "maxDeadLetterRetainedBytes": 16384,
    "maxDeadLettersPerRound": 2048,
    "maxDeadLetterPageSize": 100,
    "maxConsumerEpochCharacters": 128,
    "maxMergeSourceIncarnations": 8,
    "maxSyncPathIdCharacters": 128,
    "maxReplayPageSize": 500,
}
JAVASCRIPT_MAX_SAFE_INTEGER = 9_007_199_254_740_991

REASON_CODE_REGISTRY = {
    "schema": "ai-caddie-reason-code-registry-v1",
    "codes": list(REASON_CODES),
    "roundTransportLimits": ROUND_TRANSPORT_LIMITS,
}

SUBMISSION_CLASSES = (
    ("ordinaryEvent", "ordinary_event"),
    ("resolutionPrerequisite", "resolution_prerequisite"),
    ("ordinaryOrResolutionCommit", "ordinary_or_resolution_commit"),
    ("resolutionCommitOnly", "resolution_commit_only"),
)


class ContractCodegenTests(unittest.TestCase):
    @staticmethod
    def _copy_contract_repo(tmp: str) -> tuple[Path, Path, Path]:
        repo_root = Path(tmp)
        registry_root = repo_root / "contracts/canonical"
        shutil.copytree(Path("contracts/canonical"), registry_root)
        generator_copy = repo_root / "tools/contracts/generate_contracts.py"
        generator_copy.parent.mkdir(parents=True)
        shutil.copy2(Path("tools/contracts/generate_contracts.py"), generator_copy)
        return repo_root, registry_root, generator_copy

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def _source_shas(self, outputs: dict[str, str]) -> dict[str, str]:
        patterns = {
            "ai_caddie/contracts/generated.py": (
                r"^CANONICAL_CONTRACT_SOURCE_SHA256 = '([0-9a-f]{64})'$"
            ),
            "mobile/ios/AICaddieDomain/GeneratedContracts.swift": (
                r'^public let canonicalContractSourceSHA256 = "([0-9a-f]{64})"$'
            ),
            "web_v2/src/contracts/generated.ts": (
                r'^export const canonicalContractSourceSHA256 = "([0-9a-f]{64})" as const$'
            ),
        }
        values: dict[str, str] = {}
        for relative, pattern in patterns.items():
            match = re.search(pattern, outputs[relative], re.MULTILINE)
            self.assertIsNotNone(match, relative)
            assert match is not None
            values[relative] = match.group(1)
        return values

    def _typescript_const(self, source: str, name: str) -> Any:
        match = re.search(
            rf"^export const {re.escape(name)} = (.+) as const$",
            source,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, name)
        assert match is not None
        return json.loads(match.group(1))

    def _swift_canonical_descriptors(self, source: str) -> dict[str, dict[str, Any]]:
        section = source.split("public enum GeneratedCanonicalObjects", 1)[1].split(
            "public enum RoundEventSubmissionClass", 1
        )[0]
        quoted = r'("(?:\\.|[^"\\])*")'
        rows = re.findall(
            rf"^\s+{quoted}: CanonicalObjectDescriptor\("
            rf"objectName: {quoted}, domainTag: {quoted}, schemaRef: {quoted}, "
            rf"includedFields: (\[[^\n]*\]), excludedFields: (\[[^\n]*\])\),$",
            section,
            re.MULTILINE,
        )
        descriptors: dict[str, dict[str, Any]] = {}
        for domain_key, object_name, domain_tag, schema_ref, included, excluded in rows:
            normalized_domain_key = json.loads(domain_key)
            normalized_name = json.loads(object_name)
            normalized_domain_tag = json.loads(domain_tag)
            self.assertEqual(normalized_domain_key, normalized_domain_tag)
            self.assertNotIn(normalized_name, descriptors)
            descriptors[normalized_name] = {
                "domainTag": normalized_domain_tag,
                "schemaRef": json.loads(schema_ref),
                "includedFields": json.loads(included),
                "excludedFields": json.loads(excluded),
            }
        return descriptors

    def test_checked_in_outputs_match_all_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path(tmp))
            self.assertEqual(set(outputs), GENERATED_OUTPUTS)
            for relative, generated in outputs.items():
                self.assertEqual(Path(relative).read_bytes(), generated.encode("utf-8"), relative)

    def test_checked_in_mobile_event_sanitizer_resource_is_exact_byte_copy(self) -> None:
        canonical_path = Path(
            "contracts/canonical/fixtures/mobile_event_sanitizer_golden.json"
        )
        self.assertTrue(canonical_path.exists())
        canonical = canonical_path.read_bytes()
        outputs = contract_codegen.generate_shared_resource_outputs(
            Path("contracts/canonical")
        )

        self.assertEqual(set(outputs), SHARED_RESOURCE_OUTPUTS)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), MOBILE_EVENT_SANITIZER_SHA256)
        for relative, generated in outputs.items():
            self.assertEqual(generated, canonical, relative)
            self.assertEqual(Path(relative).read_bytes(), canonical, relative)

    def test_checked_in_registries_match_all_frozen_normative_values(self) -> None:
        events = contract_codegen._load(Path("contracts/canonical/event_kind_registry.json"))
        reasons = contract_codegen._load(Path("contracts/canonical/reason_codes.json"))
        self.assertEqual(events, EVENT_KIND_REGISTRY)
        self.assertEqual(reasons, REASON_CODE_REGISTRY)
        self.assertEqual(tuple(reasons["codes"]), REASON_CODES)
        self.assertEqual(len(reasons["codes"]), 44)
        self.assertEqual(len(set(reasons["codes"])), 44)
        self.assertEqual(reasons["roundTransportLimits"], ROUND_TRANSPORT_LIMITS)

    def test_generated_declarations_are_complete_and_share_one_source_sha(self) -> None:
        outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path("."))
        for relative, generated in outputs.items():
            with self.subTest(relative=relative):
                self.assertIn("CanonicalFixtureAlpha/v1", generated)
                self.assertIn("round_binding_mismatch", generated)
                self.assertIn("maxEventsPerBatch", generated)

        source_shas = self._source_shas(outputs)
        self.assertEqual(len(set(source_shas.values())), 1)

        python_namespace: dict[str, object] = {}
        exec(outputs["ai_caddie/contracts/generated.py"], python_namespace)
        self.assertEqual(python_namespace["EVENT_KINDS"], ())
        self.assertEqual(python_namespace["EVENT_SUBMISSION_CLASSES"], {})
        self.assertEqual(python_namespace["REASON_CODES"], tuple(sorted(REASON_CODES)))
        self.assertEqual(python_namespace["ROUND_TRANSPORT_LIMITS"], ROUND_TRANSPORT_LIMITS)

        swift = outputs["mobile/ios/AICaddieDomain/GeneratedContracts.swift"]
        submission_section = swift.split("public enum RoundEventSubmissionClass", 1)[1].split(
            "public struct RoundEventKind", 1
        )[0]
        self.assertEqual(
            re.findall(r'^\s+case (\w+) = "([a-z_]+)"$', submission_section, re.MULTILINE),
            list(SUBMISSION_CLASSES),
        )
        kind_section = swift.split("public struct RoundEventKind", 1)[1].split(
            "public struct ReasonCode", 1
        )[0]
        self.assertIn("public static let knownValues: Set<String> = []", kind_section)
        self.assertIn(
            "public static let submissionClasses: [String: RoundEventSubmissionClass] = [:]",
            kind_section,
        )
        self.assertNotIn("RoundEventKind(rawValue:", kind_section)
        swift_reasons = re.findall(
            r'^\s+public static let ([A-Za-z_][A-Za-z0-9_]*) = '
            r'ReasonCode\(rawValue: "([a-z0-9_]+)"\)$',
            swift,
            re.MULTILINE,
        )
        self.assertEqual(
            swift_reasons,
            [(contract_codegen._swift_name(value), value) for value in sorted(REASON_CODES)],
        )
        swift_limits = {
            name: int(value)
            for name, value in re.findall(
                r"^\s+public static let (max[A-Za-z0-9]+) = ([0-9]+)$",
                swift,
                re.MULTILINE,
            )
        }
        self.assertEqual(swift_limits, ROUND_TRANSPORT_LIMITS)

        typescript = outputs["web_v2/src/contracts/generated.ts"]
        self.assertEqual(self._typescript_const(typescript, "roundEventKinds"), [])
        self.assertEqual(self._typescript_const(typescript, "roundEventSubmissionClasses"), {})
        self.assertEqual(
            self._typescript_const(typescript, "reasonCodes"),
            sorted(REASON_CODES),
        )
        self.assertEqual(
            self._typescript_const(typescript, "roundTransportLimits"),
            ROUND_TRANSPORT_LIMITS,
        )
        self.assertIn(
            "export type RoundEventKind = typeof roundEventKinds[number] | (string & {})",
            typescript,
        )

    def test_generated_canonical_descriptors_are_exact_and_identical_in_all_languages(self) -> None:
        outputs = contract_codegen.generate_all(Path("contracts/canonical"), Path("."))

        python_namespace: dict[str, object] = {}
        exec(outputs["ai_caddie/contracts/generated.py"], python_namespace)
        python_descriptors = python_namespace["CANONICAL_OBJECT_DESCRIPTORS"]
        swift_descriptors = self._swift_canonical_descriptors(
            outputs["mobile/ios/AICaddieDomain/GeneratedContracts.swift"]
        )
        typescript_descriptors = self._typescript_const(
            outputs["web_v2/src/contracts/generated.ts"],
            "canonicalObjectDescriptors",
        )

        for language, descriptors in (
            ("Python", python_descriptors),
            ("Swift", swift_descriptors),
            ("TypeScript", typescript_descriptors),
        ):
            with self.subTest(language=language):
                self.assertEqual(descriptors, CANONICAL_OBJECT_DESCRIPTORS)

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
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                (registry_root / filename).write_bytes(contents)
                with self.assertRaisesRegex(ValueError, f"duplicate JSON key: {duplicate_key}"):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_duplicate_key_fixture_is_raw_digest_input_but_is_never_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, registry_root, _ = self._copy_contract_repo(tmp)
            before = self._source_shas(contract_codegen.generate_all(registry_root, repo_root))
            fixture = registry_root / "fixtures/canonical_json_duplicate_key.json"
            fixture.write_bytes(fixture.read_bytes() + b" ")
            after = self._source_shas(contract_codegen.generate_all(registry_root, repo_root))
            self.assertEqual(len(set(before.values())), 1)
            self.assertEqual(len(set(after.values())), 1)
            self.assertNotEqual(next(iter(before.values())), next(iter(after.values())))

    def test_generator_raw_bytes_are_source_digest_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, registry_root, generator_copy = self._copy_contract_repo(tmp)
            before = self._source_shas(contract_codegen.generate_all(registry_root, repo_root))
            generator_copy.write_bytes(generator_copy.read_bytes() + b"\n# digest mutation\n")
            after = self._source_shas(contract_codegen.generate_all(registry_root, repo_root))
            self.assertEqual(len(set(before.values())), 1)
            self.assertEqual(len(set(after.values())), 1)
            self.assertNotEqual(next(iter(before.values())), next(iter(after.values())))

    def test_rejects_invalid_registry_envelopes(self) -> None:
        invalid_cases: list[tuple[str, str, Any, str]] = [
            (
                "event top-level shape",
                "event_kind_registry.json",
                [],
                "event kind registry must be an object",
            ),
            (
                "event schema",
                "event_kind_registry.json",
                {"schema": "wrong", "kinds": {}},
                "event kind registry schema",
            ),
            (
                "event keys",
                "event_kind_registry.json",
                {**EVENT_KIND_REGISTRY, "extra": True},
                "event kind registry keys",
            ),
            (
                "event kinds shape",
                "event_kind_registry.json",
                {"schema": EVENT_KIND_REGISTRY["schema"], "kinds": []},
                "event kind registry kinds",
            ),
            (
                "reason top-level shape",
                "reason_codes.json",
                [],
                "reason code registry must be an object",
            ),
            (
                "reason schema",
                "reason_codes.json",
                {**REASON_CODE_REGISTRY, "schema": "wrong"},
                "reason code registry schema",
            ),
            (
                "reason keys",
                "reason_codes.json",
                {**REASON_CODE_REGISTRY, "extra": True},
                "reason code registry keys",
            ),
            (
                "reason codes shape",
                "reason_codes.json",
                {**REASON_CODE_REGISTRY, "codes": {}},
                "reason code registry codes",
            ),
            (
                "reason limits shape",
                "reason_codes.json",
                {**REASON_CODE_REGISTRY, "roundTransportLimits": []},
                "roundTransportLimits",
            ),
        ]
        for label, filename, value, message in invalid_cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                self._write_json(registry_root / filename, value)
                with self.assertRaisesRegex(ValueError, message):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_rejects_duplicate_reason_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, registry_root, _ = self._copy_contract_repo(tmp)
            reasons = copy.deepcopy(REASON_CODE_REGISTRY)
            reasons["codes"] = [REASON_CODES[0], REASON_CODES[0]]
            self._write_json(registry_root / "reason_codes.json", reasons)
            with self.assertRaisesRegex(ValueError, "reason codes must be unique"):
                contract_codegen.generate_all(registry_root, repo_root)

    def test_rejects_invalid_event_rules_and_submission_classes(self) -> None:
        invalid_kinds = (
            ("rule shape", {"future_event": []}, "event rule for future_event"),
            (
                "submission class",
                {"future_event": {"submissionClass": "not_a_real_class"}},
                "submissionClass for future_event",
            ),
        )
        for label, kinds, message in invalid_kinds:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                self._write_json(
                    registry_root / "event_kind_registry.json",
                    {"schema": EVENT_KIND_REGISTRY["schema"], "kinds": kinds},
                )
                with self.assertRaisesRegex(ValueError, message):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_submission_class_defaults_without_restricting_future_rule_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, registry_root, _ = self._copy_contract_repo(tmp)
            kinds = {
                "future_event": {
                    "payloadRef": "contracts/canonical/future.schema.json",
                    "futureNormativeField": {"preserved": True},
                },
                "resolution_opened": {
                    "submissionClass": "resolution_prerequisite",
                    "anotherFutureField": ["preserved"],
                },
            }
            self._write_json(
                registry_root / "event_kind_registry.json",
                {"schema": EVENT_KIND_REGISTRY["schema"], "kinds": kinds},
            )
            outputs = contract_codegen.generate_all(registry_root, repo_root)
            python_namespace: dict[str, object] = {}
            exec(outputs["ai_caddie/contracts/generated.py"], python_namespace)
            self.assertEqual(
                python_namespace["EVENT_SUBMISSION_CLASSES"],
                {
                    "future_event": "ordinary_event",
                    "resolution_opened": "resolution_prerequisite",
                },
            )

    def test_event_kind_declarations_are_exact_sorted_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, registry_root, _ = self._copy_contract_repo(tmp)
            out_of_order_kinds = {
                "zeta_defaulted_event": {
                    "payloadRef": "contracts/canonical/future.schema.json",
                    "futureNormativeField": {"preserved": True},
                },
                "gamma_commit_eligible": {
                    "submissionClass": "ordinary_or_resolution_commit",
                },
                "beta_commit_only": {
                    "submissionClass": "resolution_commit_only",
                },
                "alpha_resolution_opened": {
                    "submissionClass": "resolution_prerequisite",
                    "anotherFutureField": ["preserved"],
                },
            }
            self._write_json(
                registry_root / "event_kind_registry.json",
                {"schema": EVENT_KIND_REGISTRY["schema"], "kinds": out_of_order_kinds},
            )

            outputs = contract_codegen.generate_all(registry_root, repo_root)
            repeated_outputs = contract_codegen.generate_all(registry_root, repo_root)
            self.assertEqual(set(outputs), GENERATED_OUTPUTS)
            self.assertEqual(
                {relative: content.encode("utf-8") for relative, content in outputs.items()},
                {
                    relative: content.encode("utf-8")
                    for relative, content in repeated_outputs.items()
                },
            )

            python_declarations = [
                line
                for line in outputs["ai_caddie/contracts/generated.py"].splitlines()
                if line.startswith(("EVENT_KINDS = ", "EVENT_SUBMISSION_CLASSES = "))
            ]
            self.assertEqual(
                python_declarations,
                [
                    "EVENT_KINDS = ('alpha_resolution_opened', 'beta_commit_only', "
                    "'gamma_commit_eligible', 'zeta_defaulted_event')",
                    "EVENT_SUBMISSION_CLASSES = {'alpha_resolution_opened': "
                    "'resolution_prerequisite', 'beta_commit_only': "
                    "'resolution_commit_only', 'gamma_commit_eligible': "
                    "'ordinary_or_resolution_commit', 'zeta_defaulted_event': "
                    "'ordinary_event'}",
                ],
            )

            swift = outputs["mobile/ios/AICaddieDomain/GeneratedContracts.swift"]
            swift_kind_section = swift[
                swift.index("public struct RoundEventKind") : swift.index(
                    "\n\npublic struct ReasonCode"
                )
            ]
            self.assertEqual(
                swift_kind_section,
                """public struct RoundEventKind: RawRepresentable, Codable, Hashable, Sendable {
    public let rawValue: String
    public init(rawValue: String) { self.rawValue = rawValue }
    public init(from decoder: Decoder) throws {
        self.rawValue = try decoder.singleValueContainer().decode(String.self)
    }
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
    public static let knownValues: Set<String> = ["alpha_resolution_opened", "beta_commit_only", "gamma_commit_eligible", "zeta_defaulted_event"]
    public static let submissionClasses: [String: RoundEventSubmissionClass] = [
        "alpha_resolution_opened": .resolutionPrerequisite,
        "beta_commit_only": .resolutionCommitOnly,
        "gamma_commit_eligible": .ordinaryOrResolutionCommit,
        "zeta_defaulted_event": .ordinaryEvent,
    ]
    public static let alphaResolutionOpened = RoundEventKind(rawValue: "alpha_resolution_opened")
    public static let betaCommitOnly = RoundEventKind(rawValue: "beta_commit_only")
    public static let gammaCommitEligible = RoundEventKind(rawValue: "gamma_commit_eligible")
    public static let zetaDefaultedEvent = RoundEventKind(rawValue: "zeta_defaulted_event")
}""",
            )

            typescript_declarations = [
                line
                for line in outputs["web_v2/src/contracts/generated.ts"].splitlines()
                if line.startswith(
                    ("export const roundEventKinds = ", "export const roundEventSubmissionClasses = ")
                )
            ]
            self.assertEqual(
                typescript_declarations,
                [
                    'export const roundEventKinds = ["alpha_resolution_opened", '
                    '"beta_commit_only", "gamma_commit_eligible", '
                    '"zeta_defaulted_event"] as const',
                    'export const roundEventSubmissionClasses = {"alpha_resolution_opened": '
                    '"resolution_prerequisite", "beta_commit_only": '
                    '"resolution_commit_only", "gamma_commit_eligible": '
                    '"ordinary_or_resolution_commit", "zeta_defaulted_event": '
                    '"ordinary_event"} as const',
                ],
            )

    def test_rejects_invalid_names_and_swift_identifier_collisions(self) -> None:
        invalid_cases: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []

        events = copy.deepcopy(EVENT_KIND_REGISTRY)
        events["kinds"] = {"Bad-Name": {}}
        invalid_cases.append(("event raw name", events, REASON_CODE_REGISTRY, "event kind name"))

        reasons = copy.deepcopy(REASON_CODE_REGISTRY)
        reasons["codes"] = ["bad-name"]
        invalid_cases.append(("reason raw name", EVENT_KIND_REGISTRY, reasons, "reason code name"))

        events = copy.deepcopy(EVENT_KIND_REGISTRY)
        events["kinds"] = {"foo1bar": {}, "foo_1bar": {}}
        invalid_cases.append(
            ("event Swift collision", events, REASON_CODE_REGISTRY, "RoundEventKind.*foo1bar")
        )

        reasons = copy.deepcopy(REASON_CODE_REGISTRY)
        reasons["codes"] = ["foo1bar", "foo_1bar"]
        invalid_cases.append(
            ("reason Swift collision", EVENT_KIND_REGISTRY, reasons, "ReasonCode.*foo1bar")
        )

        events = copy.deepcopy(EVENT_KIND_REGISTRY)
        events["kinds"] = {"known_values": {}}
        invalid_cases.append(
            ("event member collision", events, REASON_CODE_REGISTRY, "RoundEventKind.*knownValues")
        )

        reasons = copy.deepcopy(REASON_CODE_REGISTRY)
        reasons["codes"] = ["raw_value"]
        invalid_cases.append(
            ("reason member collision", EVENT_KIND_REGISTRY, reasons, "ReasonCode.*rawValue")
        )

        reasons = copy.deepcopy(REASON_CODE_REGISTRY)
        reasons["codes"] = ["class"]
        invalid_cases.append(
            ("Swift reserved word", EVENT_KIND_REGISTRY, reasons, "Swift reserved word.*class")
        )

        for label, event_value, reason_value, message in invalid_cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                self._write_json(registry_root / "event_kind_registry.json", event_value)
                self._write_json(registry_root / "reason_codes.json", reason_value)
                with self.assertRaisesRegex(ValueError, message):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_rejects_invalid_transport_limits(self) -> None:
        invalid_limits: list[tuple[str, dict[str, Any], str]] = []

        missing = copy.deepcopy(ROUND_TRANSPORT_LIMITS)
        missing.pop("maxReplayPageSize")
        invalid_limits.append(("missing key", missing, "roundTransportLimits keys"))

        extra = copy.deepcopy(ROUND_TRANSPORT_LIMITS)
        extra["maxUnexpectedLimit"] = 1
        invalid_limits.append(("extra key", extra, "roundTransportLimits keys"))

        boolean = copy.deepcopy(ROUND_TRANSPORT_LIMITS)
        boolean["maxEventsPerBatch"] = True
        invalid_limits.append(
            ("bool", boolean, "roundTransportLimits.maxEventsPerBatch.*positive integer")
        )

        zero = copy.deepcopy(ROUND_TRANSPORT_LIMITS)
        zero["maxEventsPerBatch"] = 0
        invalid_limits.append(
            ("zero", zero, "roundTransportLimits.maxEventsPerBatch.*positive integer")
        )

        for label, limits, message in invalid_limits:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                reasons = copy.deepcopy(REASON_CODE_REGISTRY)
                reasons["roundTransportLimits"] = limits
                self._write_json(registry_root / "reason_codes.json", reasons)
                with self.assertRaisesRegex(ValueError, message):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_accepts_max_safe_integer_for_every_transport_limit(self) -> None:
        for key in ROUND_TRANSPORT_LIMITS:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                reasons = copy.deepcopy(REASON_CODE_REGISTRY)
                reasons["roundTransportLimits"][key] = JAVASCRIPT_MAX_SAFE_INTEGER
                self._write_json(registry_root / "reason_codes.json", reasons)

                outputs = contract_codegen.generate_all(registry_root, repo_root)
                python_namespace: dict[str, object] = {}
                exec(outputs["ai_caddie/contracts/generated.py"], python_namespace)
                self.assertEqual(
                    python_namespace["ROUND_TRANSPORT_LIMITS"][key],
                    JAVASCRIPT_MAX_SAFE_INTEGER,
                )
                swift_match = re.search(
                    rf"^\s+public static let {re.escape(key)} = ([0-9]+)$",
                    outputs["mobile/ios/AICaddieDomain/GeneratedContracts.swift"],
                    re.MULTILINE,
                )
                self.assertIsNotNone(swift_match, key)
                assert swift_match is not None
                self.assertEqual(int(swift_match.group(1)), JAVASCRIPT_MAX_SAFE_INTEGER)
                self.assertEqual(
                    self._typescript_const(
                        outputs["web_v2/src/contracts/generated.ts"],
                        "roundTransportLimits",
                    )[key],
                    JAVASCRIPT_MAX_SAFE_INTEGER,
                )

    def test_rejects_above_max_safe_integer_for_every_transport_limit(self) -> None:
        invalid_value = JAVASCRIPT_MAX_SAFE_INTEGER + 1
        for key in ROUND_TRANSPORT_LIMITS:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                reasons = copy.deepcopy(REASON_CODE_REGISTRY)
                reasons["roundTransportLimits"][key] = invalid_value
                self._write_json(registry_root / "reason_codes.json", reasons)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"^roundTransportLimits\.{re.escape(key)} must be a positive integer "
                    rf"no greater than {JAVASCRIPT_MAX_SAFE_INTEGER}; got {invalid_value}$",
                ):
                    contract_codegen.generate_all(registry_root, repo_root)

    def test_rejects_invalid_scalar_for_every_transport_limit(self) -> None:
        invalid_values = (
            ("bool", True),
            ("float", 1.5),
            ("zero", 0),
            ("negative", -1),
        )
        for key in ROUND_TRANSPORT_LIMITS:
            for label, invalid_value in invalid_values:
                with (
                    self.subTest(key=key, invalid=label),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    repo_root, registry_root, _ = self._copy_contract_repo(tmp)
                    reasons = copy.deepcopy(REASON_CODE_REGISTRY)
                    reasons["roundTransportLimits"][key] = invalid_value
                    self._write_json(registry_root / "reason_codes.json", reasons)
                    with self.assertRaisesRegex(
                        ValueError,
                        rf"roundTransportLimits\.{re.escape(key)}.*positive integer",
                    ):
                        contract_codegen.generate_all(registry_root, repo_root)

    def test_swift_package_declares_shared_domain_targets_and_resources(self) -> None:
        package = Path("Package.swift").read_text(encoding="utf-8")
        self.assertIn('.library(name: "AICaddieDomain", targets: ["AICaddieDomain"])', package)
        self.assertIn(
            'name: "SwiftJCS",\n'
            '            path: "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS"',
            package,
        )
        self.assertIn(
            'name: "AICaddieDomain",\n'
            '            dependencies: ["SwiftJCS"],\n'
            '            path: "mobile/ios/AICaddieDomain",\n'
            '            exclude: ["ThirdParty/SwiftJCS"]',
            package,
        )
        self.assertIn(
            'name: "AICaddieDomainTests",\n'
            '            dependencies: ["AICaddieDomain", "SwiftJCS"],\n'
            '            path: "mobile/ios/AICaddieDomainTests",\n'
            '            resources: [.copy("Fixtures")]',
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
        self.assertIn(
            'name: "AICaddieTests",\n'
            '            dependencies: ["AICaddie"],\n'
            '            path: "mobile/ios/AICaddieTests",\n'
            '            resources: [.copy("Fixtures")]',
            package,
        )

    def test_xcodegen_declares_multidestination_domain_targets_and_dependencies(self) -> None:
        project = yaml.safe_load(Path("mobile/ios/project.yml").read_text(encoding="utf-8"))
        targets = project["targets"]

        swift_jcs = targets["SwiftJCS"]
        self.assertEqual(swift_jcs["type"], "library.static")
        self.assertEqual(swift_jcs["platform"], "auto")
        self.assertEqual(set(swift_jcs["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertEqual(
            swift_jcs["sources"],
            [{"path": "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS"}],
        )

        domain = targets["AICaddieDomain"]
        self.assertEqual(domain["type"], "framework")
        self.assertEqual(domain["platform"], "auto")
        self.assertEqual(set(domain["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertIn(
            {
                "path": "mobile/ios/AICaddieDomain",
                "excludes": ["ThirdParty/SwiftJCS"],
            },
            domain["sources"],
        )
        self.assertIn(
            {"target": "SwiftJCS", "link": True},
            domain["dependencies"],
        )

        domain_tests = targets["AICaddieDomainTests"]
        self.assertEqual(domain_tests["type"], "bundle.unit-test")
        self.assertEqual(domain_tests["platform"], "auto")
        self.assertEqual(set(domain_tests["supportedDestinations"]), {"iOS", "watchOS"})
        self.assertIn({"target": "AICaddieDomain"}, domain_tests["dependencies"])
        self.assertIn(
            {"target": "SwiftJCS", "link": True},
            domain_tests["dependencies"],
        )
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

        ios_tests = targets["AICaddieTests"]
        self.assertIn(
            {"path": "mobile/ios/AICaddieTests", "excludes": ["Fixtures"]},
            ios_tests["sources"],
        )
        self.assertIn(
            {
                "path": "mobile/ios/AICaddieTests/Fixtures",
                "buildPhase": "resources",
            },
            ios_tests["sources"],
        )

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
        written = calls[0].args[0]
        self.assertIsInstance(written, ast.Name)
        assert isinstance(written, ast.Name)
        self.assertEqual(written.id, "content")
        encode_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "encode"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "content"
            and [ast.literal_eval(arg) for arg in node.args] == ["utf-8"]
        ]
        self.assertEqual(len(encode_calls), 1)
        self.assertIn("generate_shared_resource_outputs(registry_root)", source)
