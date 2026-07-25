from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/storage-v1/domain_ledger_storage_shapes_v1.json"
GENERATOR = ROOT / "tools/contracts/generate_storage_v1_shape.py"
GENERATED_RELATIVE = "mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift"
GENERATED = ROOT / GENERATED_RELATIVE
PUBLIC_CANONICAL_OUTPUTS = {
    "ai_caddie/contracts/generated.py",
    "mobile/ios/AICaddieDomain/GeneratedContracts.swift",
    "web_v2/src/contracts/generated.ts",
}

TYPE_ROSTER = (
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
)


def _scalar(name: str, *, profile: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "scalar", "name": name}
    if profile is not None:
        result["profile"] = profile
    return result


def _ref(name: str) -> dict[str, str]:
    return {"kind": "ref", "name": name}


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "array", "items": items}


def _dynamic_map(values: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "dynamicMap", "values": values}


def _nullable(value: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "nullable", "value": value}


def _constrained(policy: str, value: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "constrained", "policy": policy, "value": value}


STRING = _scalar("string", profile="ordinaryString")
INTEGER = _scalar("int")
BASE64_DATA = _scalar("base64Data")


def _record(*members: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "record",
        "members": [
            {"name": name, "shape": shape}
            for name, shape in members
        ],
    }


EXPECTED_TYPES: dict[str, dict[str, Any]] = {
    "StoredEventV1": _record(
        ("eventId", STRING),
        ("originDeviceId", STRING),
        ("originEpoch", STRING),
        ("clientSequence", INTEGER),
        ("roundId", STRING),
        ("kind", _ref("RoundEventKind")),
        ("payload", _dynamic_map(_ref("JSONValue"))),
        ("occurredAt", STRING),
    ),
    "OriginSequenceState": _record(
        ("originDeviceId", STRING),
        ("originEpoch", STRING),
        ("lastReservedClientSequence", INTEGER),
    ),
    "CanonicalStringSet": {
        "kind": "collection",
        "representation": "sortedUniqueArray",
        "items": STRING,
    },
    "DomainLedgerStateV1": _record(
        ("storageVersion", {"kind": "literal", "scalar": "int", "value": 1}),
        ("origin", _ref("OriginSequenceState")),
        (
            "events",
            _constrained(
                "rootCollection",
                _array(_constrained("eventOrEnvelope", _ref("StoredEventV1"))),
            ),
        ),
        ("outbox", _constrained("rootCollection", _array(_ref("LegacyV1OutboxRecord")))),
        (
            "deadLetters",
            _constrained("rootCollection", _array(_ref("LegacyV1OutboxRecord"))),
        ),
        (
            "receipts",
            _constrained(
                "rootCollection",
                _dynamic_map(_ref("LegacyV1EventReceipt")),
            ),
        ),
        (
            "legacyWireBindings",
            _constrained("rootCollection", _array(_ref("LegacyWireBinding"))),
        ),
        (
            "preparedLegacyV1Batches",
            _constrained("rootCollection", _array(_ref("PreparedLegacyV1Batch"))),
        ),
        (
            "watchTerminalReceiptRelayObligations",
            _constrained(
                "rootCollection",
                _array(_ref("WatchTerminalReceiptRelayObligation")),
            ),
        ),
        (
            "watchTerminalReceiptRelayConfirmations",
            _constrained(
                "rootCollection",
                _array(_ref("WatchTerminalReceiptRelayConfirmation")),
            ),
        ),
        (
            "migrationMarkers",
            _constrained("rootCollection", _ref("CanonicalStringSet")),
        ),
        (
            "transportAnomalies",
            _constrained("rootCollection", _array(_ref("LegacyV1TransportAnomaly"))),
        ),
    ),
    "LegacyDomainAlias": _record(
        ("eventIdentity", STRING),
        ("eventHash", STRING),
    ),
    "LegacyWireBinding": _record(
        ("roundId", STRING),
        ("wireClientId", STRING),
        ("wireEventId", STRING),
        ("canonicalDomainIdentity", STRING),
        ("canonicalDomainEventHash", STRING),
        ("normalizedWireEnvelopeHash", STRING),
        ("legacyAliases", _array(_ref("LegacyDomainAlias"))),
    ),
    "PreparedLegacyV1Slot": _record(
        ("bindingKey", STRING),
        (
            "exactNormalizedEnvelope",
            _constrained("eventOrEnvelope", _ref("JSONValue")),
        ),
        ("exactNormalizedEnvelopeHash", STRING),
    ),
    "PreparedLegacyV1Batch": _record(
        ("roundId", STRING),
        (
            "orderedSlots",
            _constrained("preparedSlots", _array(_ref("PreparedLegacyV1Slot"))),
        ),
        ("exactRequestBody", _constrained("requestBody", BASE64_DATA)),
        ("requestBodySha256", STRING),
        ("idempotencyKey", STRING),
    ),
    "LegacyV1TerminalStatus": {
        "kind": "closedEnum",
        "values": [
            "accepted",
            "duplicate_hash_match",
            "rejected_permanent",
        ],
    },
    "LegacyV1EventReceipt": _record(
        ("eventIdentity", STRING),
        ("eventHash", STRING),
        ("status", _ref("LegacyV1TerminalStatus")),
        ("serverSequence", INTEGER),
    ),
    "LegacyV1OutboxRecord": _record(
        ("eventIdentity", STRING),
        ("eventHash", STRING),
        ("receipt", _nullable(_ref("LegacyV1EventReceipt"))),
        ("deadLetterReason", _nullable(STRING)),
    ),
    "LegacyV1TransportAnomaly": _record(
        ("roundId", STRING),
        ("code", STRING),
        ("evidence", STRING),
    ),
    "WatchTerminalReceiptRelayObligation": _record(
        ("obligationId", STRING),
        ("eventIdentity", STRING),
        ("eventHash", STRING),
        ("status", _ref("LegacyV1TerminalStatus")),
    ),
    "WatchTerminalReceiptRelayConfirmation": _record(
        ("confirmationId", STRING),
        ("obligationId", STRING),
        ("eventIdentity", STRING),
        ("eventHash", STRING),
        ("status", _ref("LegacyV1TerminalStatus")),
    ),
    "LegacyV1EventBatchBody": _record(
        ("roundId", STRING),
        ("events", _array(_ref("JSONValue"))),
    ),
    "RoundEventKind": {
        "kind": "openString",
        "profile": "ordinaryString",
    },
    "JSONValue": {
        "kind": "recursiveJSONValue",
        "stringProfile": "ordinaryString",
    },
}

EXPECTED_POLICIES = [
    {"name": "rootCollection", "profile": "rootCollection"},
    {"name": "preparedSlots", "profile": "preparedSlots"},
    {"name": "requestBody", "profile": "requestBody"},
    {"name": "eventOrEnvelope", "profile": "eventOrEnvelope"},
]

EXPECTED_PROFILES = [
    {
        "name": "ordinaryString",
        "kind": "stringScalars",
        "maximum": {"swift": "RoundTransportLimits.maxJsonStringCharacters"},
    },
    {
        "name": "rootCollection",
        "kind": "count",
        "maximum": {"literal": 65_536},
    },
    {
        "name": "preparedSlots",
        "kind": "count",
        "minimum": {"literal": 1},
        "maximum": {"swift": "RoundTransportLimits.maxEventsPerBatch"},
    },
    {
        "name": "requestBody",
        "kind": "base64",
        "alphabet": "standard",
        "padding": "required",
        "maximumTextScalars": {
            "swift": "StorageV1RawJSONGate.maximumStringScalars",
        },
        "maximumDecodedBytes": {
            "swift": "RoundTransportLimits.maxHttpBodyBytes",
        },
    },
    {
        "name": "eventOrEnvelope",
        "kind": "canonicalJSON",
        "maximumBytes": {"swift": "RoundTransportLimits.maxEventCanonicalBytes"},
        "maximumDepth": {"swift": "RoundTransportLimits.maxEventJsonDepth"},
    },
]

EXPECTED_POLICY_PATHS = {
    ("rootCollection", "events"),
    ("rootCollection", "outbox"),
    ("rootCollection", "deadLetters"),
    ("rootCollection", "receipts"),
    ("rootCollection", "legacyWireBindings"),
    ("rootCollection", "preparedLegacyV1Batches"),
    ("rootCollection", "watchTerminalReceiptRelayObligations"),
    ("rootCollection", "watchTerminalReceiptRelayConfirmations"),
    ("rootCollection", "migrationMarkers"),
    ("rootCollection", "transportAnomalies"),
    ("preparedSlots", "preparedLegacyV1Batches[*].orderedSlots"),
    ("requestBody", "preparedLegacyV1Batches[*].exactRequestBody"),
    ("eventOrEnvelope", "events[*]"),
    (
        "eventOrEnvelope",
        "preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope",
    ),
}


class StorageV1ShapeCodegenTests(unittest.TestCase):
    def _schema_or_none(self) -> dict[str, Any] | None:
        if not SCHEMA.is_file():
            return None
        return json.loads(SCHEMA.read_text(encoding="utf-8"))

    def _types(self, document: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            definition["name"]: definition["shape"]
            for definition in document["types"]
        }

    def _flatten_policy_paths(
        self,
        document: dict[str, Any],
    ) -> set[tuple[str, str]]:
        types = self._types(document)
        result: set[tuple[str, str]] = set()

        def child_path(path: str, component: str) -> str:
            return f"{path}.{component}" if path else component

        def visit(
            shape: dict[str, Any],
            path: str,
            resolving: frozenset[str],
        ) -> None:
            kind = shape["kind"]
            if kind == "constrained":
                result.add((shape["policy"], path))
                visit(shape["value"], path, resolving)
            elif kind == "record":
                for member in shape["members"]:
                    visit(
                        member["shape"],
                        child_path(path, member["name"]),
                        resolving,
                    )
            elif kind in {"array", "collection"}:
                visit(shape["items"], f"{path}[*]", resolving)
            elif kind == "dynamicMap":
                visit(shape["values"], f"{path}[*]", resolving)
            elif kind == "nullable":
                visit(shape["value"], path, resolving)
            elif kind == "ref":
                name = shape["name"]
                if name not in resolving:
                    visit(types[name], path, resolving | {name})

        for root in document["roots"]:
            visit(root["shape"], "", frozenset())
        return result

    def _generator_or_none(self) -> ModuleType | None:
        if not GENERATOR.is_file():
            return None
        module_name = "_storage_v1_shape_generator_under_test"
        loaded = sys.modules.get(module_name)
        if loaded is not None:
            return loaded
        spec = importlib.util.spec_from_file_location(module_name, GENERATOR)
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertIsNotNone(spec.loader)
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _generate(
        self,
        module: ModuleType,
        repo_root: Path,
    ) -> dict[str, str]:
        generate_all = getattr(module, "generate_all", None)
        self.assertTrue(
            callable(generate_all),
            "storage-v1 generator must expose generate_all(registry_root, output_root)",
        )
        assert callable(generate_all)
        outputs = generate_all(repo_root / "contracts/storage-v1", repo_root)
        self.assertIsInstance(outputs, dict)
        self.assertEqual(set(outputs), {GENERATED_RELATIVE})
        self.assertIsInstance(outputs[GENERATED_RELATIVE], str)
        return outputs

    def _copy_storage_codegen_repo(self, destination: Path) -> None:
        shutil.copytree(
            ROOT / "contracts/storage-v1",
            destination / "contracts/storage-v1",
        )
        generator = destination / "tools/contracts/generate_storage_v1_shape.py"
        generator.parent.mkdir(parents=True)
        shutil.copy2(GENERATOR, generator)

    def _write_document(self, repo_root: Path, document: Any) -> None:
        path = repo_root / SCHEMA.relative_to(ROOT)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _assert_invalid_document(
        self,
        module: ModuleType,
        document: Any,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._copy_storage_codegen_repo(repo_root)
            self._write_document(repo_root, document)
            with self.assertRaises(ValueError):
                self._generate(module, repo_root)

    def _assert_invalid_raw_descriptor(
        self,
        module: ModuleType,
        raw: str,
        duplicate_key: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._copy_storage_codegen_repo(repo_root)
            path = repo_root / SCHEMA.relative_to(ROOT)
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                rf"duplicate JSON key: {re.escape(duplicate_key)}",
            ):
                self._generate(module, repo_root)

    def _expected_source_sha(self, repo_root: Path) -> str:
        registry_root = repo_root / "contracts/storage-v1"
        paths = sorted(registry_root.rglob("*.json"))
        paths.append(repo_root / "tools/contracts/generate_storage_v1_shape.py")
        digest = hashlib.sha256()
        for path in paths:
            relative = path.relative_to(repo_root).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            raw = path.read_bytes()
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
        return digest.hexdigest()

    def _embedded_source_sha(self, generated: str) -> str:
        match = re.search(
            r'^internal let storageV1ShapeSourceSHA256 = "([0-9a-f]{64})"$',
            generated,
            re.MULTILINE,
        )
        self.assertIsNotNone(match)
        assert match is not None
        return match.group(1)

    def _definition(
        self,
        document: dict[str, Any],
        name: str,
    ) -> dict[str, Any]:
        return next(item for item in document["types"] if item["name"] == name)

    def _member(
        self,
        document: dict[str, Any],
        type_name: str,
        member_name: str,
    ) -> dict[str, Any]:
        definition = self._definition(document, type_name)
        return next(
            item
            for item in definition["shape"]["members"]
            if item["name"] == member_name
        )

    def test_000_schema_asset_exists(self) -> None:
        self.assertTrue(
            SCHEMA.is_file(),
            "missing storage-v1 shape schema: "
            "domain_ledger_storage_shapes_v1.json",
        )

    def test_001_generator_asset_exists(self) -> None:
        self.assertTrue(
            GENERATOR.is_file(),
            "missing storage-v1 shape generator: generate_storage_v1_shape.py",
        )

    def test_schema_has_exact_top_level_keys_and_marker(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        self.assertEqual(
            set(document),
            {"schema", "roots", "types", "policies", "profiles"},
        )
        self.assertEqual(document["schema"], "ai-caddie-storage-v1-shapes-v1")

    def test_schema_declares_only_the_two_frozen_roots(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        self.assertEqual(
            document["roots"],
            [
                {"name": "storageDocument", "shape": _ref("DomainLedgerStateV1")},
                {
                    "name": "legacyV1EventBatchBody",
                    "shape": _ref("LegacyV1EventBatchBody"),
                },
            ],
        )

    def test_schema_type_roster_and_every_shape_are_exact(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        self.assertEqual(
            tuple(definition["name"] for definition in document["types"]),
            TYPE_ROSTER,
        )
        self.assertEqual(self._types(document), EXPECTED_TYPES)

    def test_all_record_members_are_required_and_nullable_is_value_shape_only(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        definitions = self._types(document)
        for type_name, shape in definitions.items():
            if shape["kind"] != "record":
                continue
            for member in shape["members"]:
                with self.subTest(type=type_name, member=member.get("name")):
                    self.assertEqual(set(member), {"name", "shape"})
        outbox_members = {
            member["name"]: member["shape"]
            for member in definitions["LegacyV1OutboxRecord"]["members"]
        }
        self.assertEqual(
            outbox_members["receipt"],
            _nullable(_ref("LegacyV1EventReceipt")),
        )
        self.assertEqual(outbox_members["deadLetterReason"], _nullable(STRING))

    def test_open_closed_collection_and_recursive_distinctions_are_exact(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        definitions = self._types(document)
        self.assertEqual(
            definitions["RoundEventKind"],
            {"kind": "openString", "profile": "ordinaryString"},
        )
        self.assertEqual(
            definitions["LegacyV1TerminalStatus"],
            {
                "kind": "closedEnum",
                "values": [
                    "accepted",
                    "duplicate_hash_match",
                    "rejected_permanent",
                ],
            },
        )
        self.assertEqual(
            definitions["CanonicalStringSet"],
            {
                "kind": "collection",
                "representation": "sortedUniqueArray",
                "items": STRING,
            },
        )
        self.assertEqual(
            definitions["JSONValue"],
            {"kind": "recursiveJSONValue", "stringProfile": "ordinaryString"},
        )

    def test_policy_and_limit_profile_declarations_are_exact(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        self.assertEqual(document["policies"], EXPECTED_POLICIES)
        self.assertEqual(document["profiles"], EXPECTED_PROFILES)

    def test_embedded_contextual_policy_paths_are_exact(self) -> None:
        document = self._schema_or_none()
        if document is None:
            return
        self.assertEqual(self._flatten_policy_paths(document), EXPECTED_POLICY_PATHS)
        policy_paths = {path for _, path in EXPECTED_POLICY_PATHS}
        self.assertNotIn("legacyV1EventBatchBody.events[*]", policy_paths)
        self.assertFalse(any(path.startswith("payload") for path in policy_paths))

    def test_generator_checked_in_output_and_repeat_generation_are_byte_exact(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None or not GENERATED.is_file():
            return
        first = self._generate(module, ROOT)
        second = self._generate(module, ROOT)
        self.assertEqual(first, second)
        self.assertEqual(
            GENERATED.read_bytes(),
            first[GENERATED_RELATIVE].encode("utf-8"),
        )

    def test_embedded_source_sha_uses_length_prefixed_paths_and_exact_bytes(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return
        generated = self._generate(module, ROOT)[GENERATED_RELATIVE]
        self.assertEqual(
            self._embedded_source_sha(generated),
            self._expected_source_sha(ROOT),
        )

    def test_source_sha_and_output_are_sensitive_to_each_frozen_source_input(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return

        def generated_in(repo_root: Path) -> tuple[str, str]:
            source = self._generate(module, repo_root)[GENERATED_RELATIVE]
            return source, self._embedded_source_sha(source)

        with tempfile.TemporaryDirectory() as tmp:
            baseline_root = Path(tmp) / "baseline"
            self._copy_storage_codegen_repo(baseline_root)
            baseline_source, baseline_sha = generated_in(baseline_root)

            whitespace_root = Path(tmp) / "whitespace"
            self._copy_storage_codegen_repo(whitespace_root)
            whitespace_schema = whitespace_root / SCHEMA.relative_to(ROOT)
            whitespace_schema.write_bytes(whitespace_schema.read_bytes() + b"\n")
            whitespace_source, whitespace_sha = generated_in(whitespace_root)

            generator_root = Path(tmp) / "generator"
            self._copy_storage_codegen_repo(generator_root)
            generator_copy = (
                generator_root / "tools/contracts/generate_storage_v1_shape.py"
            )
            generator_copy.write_bytes(
                generator_copy.read_bytes() + b"\n# source digest mutation\n"
            )
            generator_source, generator_sha = generated_in(generator_root)

            path_root = Path(tmp) / "path"
            self._copy_storage_codegen_repo(path_root)
            original = path_root / SCHEMA.relative_to(ROOT)
            moved = original.parent / "nested" / original.name
            moved.parent.mkdir()
            original.rename(moved)
            path_source, path_sha = generated_in(path_root)

        for label, source, source_sha in (
            ("schema whitespace", whitespace_source, whitespace_sha),
            ("generator bytes", generator_source, generator_sha),
            ("schema path", path_source, path_sha),
        ):
            with self.subTest(mutation=label):
                self.assertNotEqual(source_sha, baseline_sha)
                self.assertNotEqual(source, baseline_source)

    def test_valid_schema_mutation_drifts_only_the_sole_storage_output(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._copy_storage_codegen_repo(repo_root)
            before = self._generate(module, repo_root)
            mutated = copy.deepcopy(document)
            terminal = self._definition(mutated, "LegacyV1TerminalStatus")
            terminal["shape"]["values"].append("future_terminal_status")
            self._write_document(repo_root, mutated)
            after = self._generate(module, repo_root)
        self.assertEqual(set(before), {GENERATED_RELATIVE})
        self.assertEqual(set(after), {GENERATED_RELATIVE})
        self.assertNotEqual(before[GENERATED_RELATIVE], after[GENERATED_RELATIVE])

    def test_storage_only_source_mutation_leaves_public_canonical_digests_stable(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return
        from tools.contracts import generate_contracts as canonical_codegen

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._copy_storage_codegen_repo(repo_root)
            shutil.copytree(
                ROOT / "contracts/canonical",
                repo_root / "contracts/canonical",
            )
            canonical_generator = repo_root / "tools/contracts/generate_contracts.py"
            shutil.copy2(ROOT / "tools/contracts/generate_contracts.py", canonical_generator)

            def canonical_digests() -> dict[str, str]:
                outputs = canonical_codegen.generate_all(
                    repo_root / "contracts/canonical",
                    repo_root,
                )
                self.assertEqual(set(outputs), PUBLIC_CANONICAL_OUTPUTS)
                return {
                    path: hashlib.sha256(content.encode("utf-8")).hexdigest()
                    for path, content in outputs.items()
                }

            before = canonical_digests()
            storage_schema = repo_root / SCHEMA.relative_to(ROOT)
            storage_schema.write_bytes(storage_schema.read_bytes() + b"\n")
            self.assertNotEqual(
                self._generate(module, repo_root)[GENERATED_RELATIVE],
                self._generate(module, ROOT)[GENERATED_RELATIVE],
            )
            after = canonical_digests()
        self.assertEqual(after, before)

    def test_generator_rejects_duplicate_json_keys_at_every_grammar_layer(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return
        compact = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        cases = {
            "top level": (
                compact.replace(
                    '{"schema":',
                    '{"schema":"duplicate","schema":',
                    1,
                ),
                "schema",
            ),
            "type definition": (
                compact.replace(
                    '{"name":"StoredEventV1","shape":',
                    '{"name":"StoredEventV1","name":"Duplicate","shape":',
                    1,
                ),
                "name",
            ),
            "record member": (
                compact.replace(
                    '{"name":"eventId","shape":',
                    '{"name":"eventId","name":"duplicate","shape":',
                    1,
                ),
                "name",
            ),
            "policy": (
                compact.replace(
                    '{"name":"rootCollection","profile":',
                    '{"name":"rootCollection","profile":"duplicate","profile":',
                    1,
                ),
                "profile",
            ),
            "profile": (
                compact.replace(
                    '{"name":"ordinaryString","kind":',
                    '{"name":"ordinaryString","kind":"duplicate","kind":',
                    1,
                ),
                "kind",
            ),
        }
        for label, (raw, duplicate_key) in cases.items():
            with self.subTest(layer=label):
                self.assertNotEqual(raw, compact)
                self._assert_invalid_raw_descriptor(module, raw, duplicate_key)

    def test_generator_rejects_closed_grammar_and_graph_mutations(self) -> None:
        module = self._generator_or_none()
        document = self._schema_or_none()
        if module is None or document is None:
            return

        cases: list[tuple[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["unknownTopLevel"] = True
        cases.append(("unknown top-level member", mutated))

        mutated = copy.deepcopy(document)
        mutated["roots"].append(copy.deepcopy(mutated["roots"][0]))
        cases.append(("duplicate root definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["roots"][0]["unknown"] = True
        cases.append(("unknown root member", mutated))

        mutated = copy.deepcopy(document)
        mutated["roots"][0] = {"name": "storageDocument"}
        cases.append(("malformed root definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["types"].append(copy.deepcopy(mutated["types"][0]))
        cases.append(("duplicate type definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["types"].append(
            {"name": "UnreachableHelper", "shape": _record(("value", STRING))}
        )
        cases.append(("unreachable type definition", mutated))

        mutated = copy.deepcopy(document)
        self._definition(mutated, "StoredEventV1")["unknown"] = True
        cases.append(("unknown type-definition member", mutated))

        mutated = copy.deepcopy(document)
        mutated["types"][0] = "not a definition"
        cases.append(("malformed type definition", mutated))

        mutated = copy.deepcopy(document)
        self._definition(mutated, "RoundEventKind")["shape"]["kind"] = "unknownKind"
        cases.append(("unknown descriptor kind", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "StoredEventV1", "kind")["shape"]["name"] = "MissingType"
        cases.append(("dangling named reference", mutated))

        mutated = copy.deepcopy(document)
        kind_ref = self._member(mutated, "StoredEventV1", "kind")["shape"]
        kind_ref["unknown"] = True
        cases.append(("unknown reference member", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "StoredEventV1", "kind")["shape"] = {"kind": "ref"}
        cases.append(("malformed reference", mutated))

        mutated = copy.deepcopy(document)
        stored_event = self._definition(mutated, "StoredEventV1")["shape"]
        stored_event["members"].append(copy.deepcopy(stored_event["members"][0]))
        cases.append(("duplicate record member", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "StoredEventV1", "eventId")["optional"] = True
        cases.append(("unknown record-member property", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "StoredEventV1", "eventId")["name"] = 7
        cases.append(("malformed record member", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "DomainLedgerStateV1", "events")["shape"][
            "policy"
        ] = "missingPolicy"
        cases.append(("unknown policy reference", mutated))

        mutated = copy.deepcopy(document)
        mutated["policies"].append(copy.deepcopy(mutated["policies"][0]))
        cases.append(("duplicate policy definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["policies"][0]["unknown"] = True
        cases.append(("unknown policy member", mutated))

        mutated = copy.deepcopy(document)
        mutated["policies"][0] = {"name": "rootCollection"}
        cases.append(("malformed policy definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["policies"][0]["profile"] = "missingProfile"
        cases.append(("dangling policy profile", mutated))

        mutated = copy.deepcopy(document)
        mutated["policies"].append(
            {"name": "unusedPolicy", "profile": "rootCollection"}
        )
        cases.append(("unused policy node", mutated))

        mutated = copy.deepcopy(document)
        mutated["profiles"].append(copy.deepcopy(mutated["profiles"][0]))
        cases.append(("duplicate profile definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["profiles"][0]["unknown"] = True
        cases.append(("unknown profile member", mutated))

        mutated = copy.deepcopy(document)
        mutated["profiles"][0] = {"name": "ordinaryString"}
        cases.append(("malformed profile definition", mutated))

        mutated = copy.deepcopy(document)
        mutated["profiles"][0]["kind"] = "unknownProfileKind"
        cases.append(("unknown profile kind", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "StoredEventV1", "eventId")["shape"][
            "profile"
        ] = "missingProfile"
        cases.append(("dangling scalar profile", mutated))

        mutated = copy.deepcopy(document)
        mutated["profiles"].append(
            {
                "name": "unusedProfile",
                "kind": "count",
                "maximum": {"literal": 1},
            }
        )
        cases.append(("unused profile node", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "PreparedLegacyV1Batch", "exactRequestBody")[
            "shape"
        ]["value"] = STRING
        cases.append(("request-body policy on incompatible string", mutated))

        mutated = copy.deepcopy(document)
        self._member(mutated, "PreparedLegacyV1Batch", "orderedSlots")["shape"][
            "value"
        ] = STRING
        cases.append(("prepared-slots policy on wrong-shaped target", mutated))

        mutated = copy.deepcopy(document)
        event_shape = self._member(mutated, "DomainLedgerStateV1", "events")[
            "shape"
        ]
        event_shape["value"] = INTEGER
        cases.append(("root-collection policy on scalar target", mutated))

        mutated = copy.deepcopy(document)
        envelope = self._member(
            mutated,
            "PreparedLegacyV1Slot",
            "exactNormalizedEnvelope",
        )["shape"]
        envelope["value"] = STRING
        cases.append(("event policy on wrong-shaped target", mutated))

        mutated = copy.deepcopy(document)
        batch_events = self._member(
            mutated,
            "LegacyV1EventBatchBody",
            "events",
        )["shape"]
        batch_events["items"] = _constrained(
            "eventOrEnvelope",
            _ref("JSONValue"),
        )
        cases.append(("event policy outside its applicable root path", mutated))

        mutated = copy.deepcopy(document)
        legacy_aliases = self._member(
            mutated,
            "LegacyWireBinding",
            "legacyAliases",
        )["shape"]
        self._member(
            mutated,
            "LegacyWireBinding",
            "legacyAliases",
        )["shape"] = _constrained("rootCollection", legacy_aliases)
        cases.append(("root policy on a reachable non-root collection", mutated))

        mutated = copy.deepcopy(document)
        mutated["types"] = {
            item["name"]: item["shape"]
            for item in mutated["types"]
        }
        cases.append(("nondeterministic mapping-shaped definitions", mutated))

        mutated = copy.deepcopy(document)
        maximum = mutated["profiles"][0]["maximum"]
        maximum["literal"] = 4_096
        cases.append(("incompatible literal and Swift limit references", mutated))

        for label, malformed in cases:
            with self.subTest(mutation=label):
                self._assert_invalid_document(module, malformed)


if __name__ == "__main__":
    unittest.main()
