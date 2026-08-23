from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


class AuthorityFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "repo"
        self.outside = base / "outside"
        (self.root / "contracts/canonical").mkdir(parents=True)
        self.pinned_path = "docs/spec.md"

    def close(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, value: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def write_bytes(self, relative: str, value: bytes) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def write_manifest(self, **changes: object) -> None:
        payload: dict[str, object] = {
            "schema": "ai-caddie-contract-authority-v1",
            "authoritativeInputs": [],
            "evidenceInputs": [],
            "canonicalRoots": ["contracts/canonical"],
            "legacyAdapters": [],
            "forbiddenSymbols": [],
            "generatedGroups": [],
        }
        payload.update(changes)
        self.write("contracts/canonical/authority.json", json.dumps(payload))

    @classmethod
    def with_forbidden_pattern(cls, pattern: str) -> "AuthorityFixture":
        fixture = cls()
        fixture.write_manifest(
            forbiddenSymbols=[{"paths": [pattern], "values": ["weatherSnapshot"]}]
        )
        return fixture

    @classmethod
    def with_pinned_input(cls) -> "AuthorityFixture":
        fixture = cls()
        subprocess.run(["git", "init", "-q"], cwd=fixture.root, check=True)
        fixture.write(fixture.pinned_path, "pinned authority\n")
        subprocess.run(["git", "add", fixture.pinned_path], cwd=fixture.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Contract Test", "-c",
                "user.email=contracts@example.invalid", "commit", "-qm", "pin input",
            ],
            cwd=fixture.root,
            check=True,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=fixture.root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        blob = subprocess.run(
            ["git", "rev-parse", f"HEAD:{fixture.pinned_path}"], cwd=fixture.root,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        sha256 = hashlib.sha256((fixture.root / fixture.pinned_path).read_bytes()).hexdigest()
        fixture.write_manifest(
            authoritativeInputs=[{
                "path": fixture.pinned_path,
                "sourceCommit": commit,
                "gitBlobOid": blob,
                "sha256": sha256,
            }]
        )
        return fixture

    @staticmethod
    def _registry_payload() -> dict[str, object]:
        return {
            "schema": "ai-caddie-canonical-object-registry-v1",
            "canonicalization": "RFC8785+AI-Caddie-v1",
            "typedIdAlgorithm": (
                "lowercaseHex(SHA-256(ASCII(domainTag+'\\u0000')||canonicalBytes))"
            ),
            "objects": {
                "First": {
                    "domainTag": "First/v1",
                    "schemaRef": "contracts/canonical/test.schema.json#/$defs/value",
                    "includedFields": ["id"],
                    "excludedFields": [],
                }
            },
        }

    @classmethod
    def with_registry(cls) -> "AuthorityFixture":
        fixture = cls()
        fixture.write_manifest()
        fixture.write(
            "contracts/canonical/test.schema.json",
            json.dumps({"$defs": {"value": {"type": "object"}}}),
        )
        fixture.write(
            "contracts/canonical/canonical_object_registry.json",
            json.dumps(cls._registry_payload()),
        )
        return fixture

    def check(self, changed_paths: list[str]) -> None:
        check_authority(self.root, changed_paths=changed_paths)

    def verify(self) -> None:
        self.check([])

    def verify_registry(self, mutation: str) -> None:
        payload = self._registry_payload()
        objects = payload["objects"]
        assert isinstance(objects, dict)
        if mutation == "missing_file":
            objects["First"]["schemaRef"] = "contracts/canonical/missing.schema.json"
        elif mutation == "missing_fragment":
            objects["First"]["schemaRef"] = (
                "contracts/canonical/test.schema.json#/$defs/missing"
            )
        elif mutation == "path_escape":
            self.write("outside.schema.json", '{"type":"object"}')
            objects["First"]["schemaRef"] = "outside.schema.json"
        elif mutation == "duplicate_domain":
            objects["Second"] = {
                "domainTag": "First/v1",
                "schemaRef": "contracts/canonical/test.schema.json#/$defs/value",
                "includedFields": ["id"],
                "excludedFields": [],
            }
        elif mutation == "duplicate_json_key":
            descriptor = json.dumps(objects["First"])
            self.write(
                "contracts/canonical/canonical_object_registry.json",
                '{"schema":"ai-caddie-canonical-object-registry-v1",'
                '"canonicalization":"RFC8785+AI-Caddie-v1",'
                '"typedIdAlgorithm":"lowercaseHex(SHA-256(ASCII(domainTag+'
                "'\\\\u0000')||canonicalBytes))\",\"objects\":{\"First\":" + descriptor
                + ',"First":' + descriptor + '}}',
            )
            self.verify()
            return
        else:
            raise AssertionError(mutation)
        self.write(
            "contracts/canonical/canonical_object_registry.json", json.dumps(payload)
        )
        self.verify()


class ContractAuthorityTests(unittest.TestCase):
    def test_authoritative_and_evidence_inputs_exist(self) -> None:
        manifest = json.loads(Path("contracts/canonical/authority.json").read_text())
        for item in manifest["authoritativeInputs"] + manifest["evidenceInputs"]:
            self.assertTrue(Path(item["path"]).is_file(), item["path"])

    def test_valid_repository_has_no_authority_violations(self) -> None:
        self.assertEqual(check_authority(Path.cwd(), changed_paths=[]), [])

    def test_root_and_nested_paths_both_match_gitwildmatch_rules(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("contracts/canonical/**/*.json")
        self.addCleanup(fixture.close)
        for relative in (
            "contracts/canonical/round_event_v2.schema.json",
            "contracts/canonical/nested/round_event_v2.schema.json",
        ):
            with self.subTest(relative=relative):
                fixture.write(relative, '{"weatherSnapshot":true}')
                with self.assertRaisesRegex(AuthorityViolation, "weatherSnapshot"):
                    fixture.check([relative])

    def test_manifest_may_declare_forbidden_symbols_without_self_violation(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("contracts/canonical/**/*.json")
        self.addCleanup(fixture.close)

        fixture.check(["contracts/canonical/authority.json"])

    def test_cli_preserves_nul_delimited_git_paths(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("**")
        self.addCleanup(fixture.close)
        relative = " leading\tname\n.py "
        fixture.write(relative, "weatherSnapshot = {}\n")
        checker = Path(__file__).resolve().parents[1] / "tools/contracts/check_authority.py"

        result = subprocess.run(
            [sys.executable, str(checker)],
            cwd=fixture.root,
            input=relative.encode() + b"\0",
            capture_output=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(b"forbidden symbol weatherSnapshot", result.stderr)

    def test_cli_rejects_non_nul_input_and_escaped_changed_paths(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        checker = Path(__file__).resolve().parents[1] / "tools/contracts/check_authority.py"

        for raw, message in (
            (b"changed.py\n", b"changed path input is not NUL-terminated"),
            (b"../escape.py\0", b"invalid changed path"),
        ):
            with self.subTest(raw=raw):
                result = subprocess.run(
                    [sys.executable, str(checker)], cwd=fixture.root,
                    input=raw, capture_output=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(message, result.stderr)

    def test_cli_reports_policy_violations_without_a_traceback(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        checker = Path(__file__).resolve().parents[1] / "tools/contracts/check_authority.py"

        result = subprocess.run(
            [sys.executable, str(checker)],
            cwd=fixture.root,
            input=b"../escape.py\0",
            capture_output=True,
        )

        self.assertEqual(1, result.returncode)
        self.assertEqual(
            b"authority violation: invalid changed path: '../escape.py'\n",
            result.stderr,
        )
        self.assertNotIn(b"Traceback", result.stderr)

    def test_manifest_sha256_drift_fails(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["authoritativeInputs"][0]["sha256"] = "0" * 64
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "pinned input sha256"):
            fixture.verify()

    def test_current_pinned_bytes_must_match_source_commit_blob(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        fixture.write(fixture.pinned_path, "current bytes drifted\n")
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["authoritativeInputs"][0]["sha256"] = hashlib.sha256(
            (fixture.root / fixture.pinned_path).read_bytes()
        ).hexdigest()
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "current-vs-commit content mismatch"):
            fixture.verify()

    def test_source_commit_content_drift_is_distinct_from_current_content_drift(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        original = fixture.read(fixture.pinned_path)
        fixture.write(fixture.pinned_path, "different historical bytes\n")
        subprocess.run(["git", "add", fixture.pinned_path], cwd=fixture.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Contract Test", "-c",
                "user.email=contracts@example.invalid", "commit", "-qm", "alternate pin",
            ],
            cwd=fixture.root,
            check=True,
        )
        alternate_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=fixture.root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        fixture.write(fixture.pinned_path, original)
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["authoritativeInputs"][0]["sourceCommit"] = alternate_commit
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "sourceCommit content mismatch"):
            fixture.verify()

    def test_git_blob_oid_drift_is_reported_distinctly(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["authoritativeInputs"][0]["gitBlobOid"] = "0" * 40
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "gitBlobOid mismatch"):
            fixture.verify()

    def test_missing_source_commit_ref_fails_closed(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["authoritativeInputs"][0]["sourceCommit"] = "0" * 40
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "git pin lookup failed"):
            fixture.verify()

    def test_working_tree_evidence_blob_pin_is_verified(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        relative = "docs/evidence.md"
        fixture.write(relative, "evidence\n")
        blob = subprocess.run(
            ["git", "hash-object", "--", relative], cwd=fixture.root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        fixture.write_manifest(evidenceInputs=[{
            "path": relative,
            "gitBlobOid": blob,
            "sha256": hashlib.sha256((fixture.root / relative).read_bytes()).hexdigest(),
        }])
        fixture.verify()
        fixture.write(relative, "drifted evidence\n")
        manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
        manifest["evidenceInputs"][0]["sha256"] = hashlib.sha256(
            (fixture.root / relative).read_bytes()
        ).hexdigest()
        fixture.write("contracts/canonical/authority.json", json.dumps(manifest))

        with self.assertRaisesRegex(AuthorityViolation, "working blob mismatch"):
            fixture.verify()

    def test_unreadable_pinned_input_is_an_authority_violation(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        pinned = fixture.root / fixture.pinned_path
        pinned.chmod(0)

        with self.assertRaisesRegex(AuthorityViolation, "cannot read authoritative input"):
            fixture.verify()

    def test_registry_ref_must_resolve_inside_canonical_roots(self) -> None:
        fixture = AuthorityFixture.with_registry()
        self.addCleanup(fixture.close)
        fixture.verify()
        for mutation in (
            "missing_file", "missing_fragment", "path_escape", "duplicate_domain",
            "duplicate_json_key",
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(AuthorityViolation):
                    fixture.verify_registry(mutation)

    def test_registry_fragment_must_be_a_valid_json_pointer(self) -> None:
        cases = (
            ("/items/-1", {"items": [{"type": "object"}]}),
            ("/~2", {"~2": {"type": "object"}}),
        )
        for fragment, schema in cases:
            with self.subTest(fragment=fragment):
                fixture = AuthorityFixture.with_registry()
                try:
                    payload = fixture._registry_payload()
                    payload["objects"]["First"]["schemaRef"] = (
                        f"contracts/canonical/test.schema.json#{fragment}"
                    )
                    fixture.write(
                        "contracts/canonical/test.schema.json", json.dumps(schema)
                    )
                    fixture.write(
                        "contracts/canonical/canonical_object_registry.json",
                        json.dumps(payload),
                    )

                    with self.assertRaisesRegex(
                        AuthorityViolation, "unresolved canonical schemaRef"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_registry_fragment_percent_decodes_before_json_pointer_resolution(self) -> None:
        fixture = AuthorityFixture.with_registry()
        self.addCleanup(fixture.close)
        payload = fixture._registry_payload()
        payload["objects"]["First"]["schemaRef"] = (
            "contracts/canonical/test.schema.json#/space%20key"
        )
        fixture.write(
            "contracts/canonical/test.schema.json",
            json.dumps({"space key": {"type": "object"}}),
        )
        fixture.write(
            "contracts/canonical/canonical_object_registry.json", json.dumps(payload)
        )

        fixture.verify()

    def test_registry_fragment_rejects_invalid_percent_encoding(self) -> None:
        cases = (
            ("/bad%ZZ", "bad%ZZ"),
            ("/%FF", "%FF"),
        )
        for fragment, raw_key in cases:
            with self.subTest(fragment=fragment):
                fixture = AuthorityFixture.with_registry()
                try:
                    payload = fixture._registry_payload()
                    payload["objects"]["First"]["schemaRef"] = (
                        f"contracts/canonical/test.schema.json#{fragment}"
                    )
                    fixture.write(
                        "contracts/canonical/test.schema.json",
                        json.dumps({raw_key: {"type": "object"}}),
                    )
                    fixture.write(
                        "contracts/canonical/canonical_object_registry.json",
                        json.dumps(payload),
                    )

                    with self.assertRaisesRegex(
                        AuthorityViolation, "unresolved canonical schemaRef"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_registry_projection_fields_must_be_non_empty_and_unique(self) -> None:
        cases = (
            ("includedFields", ["id", "id"]),
            ("excludedFields", ["transport", "transport"]),
            ("includedFields", [""]),
            ("excludedFields", [""]),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                fixture = AuthorityFixture.with_registry()
                try:
                    payload = fixture._registry_payload()
                    payload["objects"]["First"][field] = value
                    fixture.write(
                        "contracts/canonical/canonical_object_registry.json",
                        json.dumps(payload),
                    )

                    with self.assertRaisesRegex(
                        AuthorityViolation, "invalid canonical field projection"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_authority_manifest_requires_supported_schema_and_exact_top_level_structure(self) -> None:
        for mutation in ("unknown_schema", "missing_key", "extra_key", "not_object"):
            with self.subTest(mutation=mutation):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest()
                    payload = json.loads(fixture.read("contracts/canonical/authority.json"))
                    if mutation == "unknown_schema":
                        payload["schema"] = "ai-caddie-contract-authority-v2"
                    elif mutation == "missing_key":
                        payload.pop("generatedGroups")
                    elif mutation == "extra_key":
                        payload["unexpected"] = []
                    elif mutation == "not_object":
                        payload = []
                    fixture.write("contracts/canonical/authority.json", json.dumps(payload))

                    with self.assertRaisesRegex(AuthorityViolation, "authority manifest"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_manifest_rejects_duplicate_keys_malformed_json_and_invalid_utf8(self) -> None:
        cases = (
            (
                b'{"schema":"unsupported","schema":"ai-caddie-contract-authority-v1",'
                b'"authoritativeInputs":[],"evidenceInputs":[],'
                b'"canonicalRoots":["contracts/canonical"],"legacyAdapters":[],'
                b'"forbiddenSymbols":[],"generatedGroups":[]}'
            ),
            b'{"schema":',
            b"\xff\xfe",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                fixture = AuthorityFixture()
                try:
                    fixture.write_bytes("contracts/canonical/authority.json", raw)
                    with self.assertRaises(AuthorityViolation):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_authority_manifest_requires_at_least_one_canonical_root(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(canonicalRoots=[])

        with self.assertRaisesRegex(AuthorityViolation, "canonicalRoots"):
            fixture.verify()

    def test_forbidden_symbol_rule_requires_at_least_one_path_pattern(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(forbiddenSymbols=[{"paths": [], "values": ["weatherSnapshot"]}])

        with self.assertRaisesRegex(AuthorityViolation, "forbidden symbol paths"):
            fixture.verify()

    def test_gitwildmatch_declarations_cannot_be_comment_only(self) -> None:
        cases = (
            {
                "forbiddenSymbols": [
                    {"paths": ["# ignored"], "values": ["weatherSnapshot"]}
                ]
            },
            {
                "generatedGroups": [{
                    "name": "generated",
                    "sources": ["# ignored"],
                    "outputs": ["generated.py"],
                }]
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(**changes)
                    with self.assertRaisesRegex(AuthorityViolation, "pattern"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_malformed_gitwildmatch_patterns_are_authority_violations(self) -> None:
        for pattern in ("   ", "[z-a]"):
            with self.subTest(pattern=pattern):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(forbiddenSymbols=[{
                        "paths": [pattern],
                        "values": ["weatherSnapshot"],
                    }])
                    with self.assertRaisesRegex(
                        AuthorityViolation, "invalid forbidden symbol pattern"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_gitwildmatch_declarations_require_a_positive_include_pattern(self) -> None:
        cases = (
            {
                "forbiddenSymbols": [{
                    "paths": ["!protected.py"],
                    "values": ["weatherSnapshot"],
                }]
            },
            {
                "generatedGroups": [{
                    "name": "generated",
                    "sources": ["!source.json"],
                    "outputs": ["generated.py"],
                }]
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(**changes)
                    with self.assertRaisesRegex(AuthorityViolation, "positive.*pattern"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_generated_group_requires_non_empty_sources_and_outputs(self) -> None:
        for missing in ("sources", "outputs"):
            with self.subTest(missing=missing):
                fixture = AuthorityFixture()
                try:
                    group = {
                        "name": "canonical-contracts",
                        "sources": ["contracts/canonical/source.json"],
                        "outputs": ["generated.py"],
                    }
                    group[missing] = []
                    fixture.write_manifest(generatedGroups=[group])

                    with self.assertRaisesRegex(
                        AuthorityViolation, f"generated group {missing}"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_generated_group_names_are_unique(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[
            {"name": "generated", "sources": ["a.json"], "outputs": ["a.py"]},
            {"name": "generated", "sources": ["b.json"], "outputs": ["b.py"]},
        ])

        with self.assertRaisesRegex(AuthorityViolation, "duplicate generated group name"):
            fixture.verify()

    def test_authority_manifest_nested_declarations_require_exact_key_sets(self) -> None:
        pin = {
            "path": "missing.md",
            "gitBlobOid": "0" * 40,
            "sha256": "0" * 64,
        }
        cases = (
            (
                "authoritative_missing_source_commit",
                {"authoritativeInputs": [pin]},
                "invalid authoritativeInputs declaration",
            ),
            (
                "authoritative_extra_key",
                {"authoritativeInputs": [{**pin, "sourceCommit": "0" * 40, "extra": True}]},
                "invalid authoritativeInputs declaration",
            ),
            (
                "evidence_extra_key",
                {"evidenceInputs": [{**pin, "extra": True}]},
                "invalid evidenceInputs declaration",
            ),
            (
                "legacy_adapter_extra_key",
                {"legacyAdapters": [{
                    "path": "mobile/contracts/watch_input_event.schema.json",
                    "mode": "adapter_only",
                    "allowedProperties": [],
                    "forbiddenEnumValues": [],
                    "extra": True,
                }]},
                "invalid legacy adapter declaration",
            ),
            (
                "forbidden_symbol_extra_key",
                {"forbiddenSymbols": [{"paths": ["**"], "values": [], "extra": True}]},
                "invalid forbidden symbol declaration",
            ),
            (
                "generated_group_extra_key",
                {"generatedGroups": [{
                    "name": "generated",
                    "sources": ["source.json"],
                    "outputs": ["generated.py"],
                    "extra": True,
                }]},
                "invalid generated group declaration",
            ),
        )
        for name, changes, message in cases:
            with self.subTest(name=name):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(**changes)
                    with self.assertRaisesRegex(AuthorityViolation, message):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_rejects_unknown_legacy_adapter_mode(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(legacyAdapters=[{
            "path": "mobile/contracts/watch_input_event.schema.json",
            "mode": "future_mode",
            "allowedProperties": [],
            "forbiddenEnumValues": [],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "invalid legacy adapter mode"):
            fixture.verify()

    def test_legacy_adapter_mode_must_match_its_frozen_declaration(self) -> None:
        for path, mode in (
            ("mobile/contracts/watch_input_event.schema.json", "v1_compatibility_only"),
            ("mobile/contracts/live_round_event.schema.json", "adapter_only"),
        ):
            with self.subTest(path=path, mode=mode):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(legacyAdapters=[{
                        "path": path,
                        "mode": mode,
                        "allowedProperties": [],
                        "forbiddenEnumValues": [],
                    }])
                    with self.assertRaisesRegex(AuthorityViolation, "legacy adapter mode mismatch"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_malformed_legacy_adapter_declaration_fails_closed(self) -> None:
        for adapter in (
            {
                "path": "mobile/contracts/watch_input_event.schema.json",
                "allowedProperties": [],
                "forbiddenEnumValues": [],
            },
            {
                "path": "mobile/contracts/watch_input_event.schema.json",
                "mode": [],
                "allowedProperties": [],
                "forbiddenEnumValues": [],
            },
        ):
            with self.subTest(adapter=adapter):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest(legacyAdapters=[adapter])
                    with self.assertRaisesRegex(AuthorityViolation, "invalid legacy adapter"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_changed_legacy_adapter_requires_object_schema_and_properties(self) -> None:
        for payload in ([], {"properties": []}, {"properties": None}):
            with self.subTest(payload=payload):
                fixture = AuthorityFixture()
                try:
                    relative = "mobile/contracts/watch_input_event.schema.json"
                    fixture.write_manifest(legacyAdapters=[{
                        "path": relative,
                        "mode": "adapter_only",
                        "allowedProperties": [],
                        "forbiddenEnumValues": ["sync_marker"],
                    }])
                    fixture.write(relative, json.dumps(payload))

                    with self.assertRaisesRegex(
                        AuthorityViolation, "malformed legacy contract"
                    ):
                        fixture.check([relative])
                finally:
                    fixture.close()

    def test_canonical_registry_requires_supported_schema_and_object_shape(self) -> None:
        for mutation in (
            "unknown_schema", "not_object", "missing_objects", "extra_key",
            "malformed_descriptor",
        ):
            with self.subTest(mutation=mutation):
                fixture = AuthorityFixture.with_registry()
                try:
                    payload = fixture._registry_payload()
                    if mutation == "unknown_schema":
                        payload["schema"] = "ai-caddie-canonical-object-registry-v2"
                    elif mutation == "not_object":
                        payload = []
                    elif mutation == "missing_objects":
                        payload.pop("objects")
                    elif mutation == "extra_key":
                        payload["unexpected"] = True
                    elif mutation == "malformed_descriptor":
                        payload["objects"]["First"]["domainTag"] = []
                    fixture.write(
                        "contracts/canonical/canonical_object_registry.json",
                        json.dumps(payload),
                    )

                    with self.assertRaisesRegex(AuthorityViolation, "canonical object registry"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_registry_enforces_canonicalization_algorithm_domain_and_projection(self) -> None:
        mutations = (
            ("canonicalization", "other"),
            ("typedIdAlgorithm", "other"),
            ("domainTag", "球场/v1"),
            ("overlap", None),
        )
        for mutation, value in mutations:
            with self.subTest(mutation=mutation):
                fixture = AuthorityFixture.with_registry()
                try:
                    payload = fixture._registry_payload()
                    if mutation in {"canonicalization", "typedIdAlgorithm"}:
                        payload[mutation] = value
                    elif mutation == "domainTag":
                        payload["objects"]["First"]["domainTag"] = value
                    else:
                        payload["objects"]["First"]["excludedFields"] = ["id"]
                    fixture.write(
                        "contracts/canonical/canonical_object_registry.json",
                        json.dumps(payload),
                    )

                    with self.assertRaises(AuthorityViolation):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_registry_and_referenced_schema_reject_malformed_json_and_utf8(self) -> None:
        for target, raw in (
            ("contracts/canonical/canonical_object_registry.json", b"{malformed"),
            ("contracts/canonical/canonical_object_registry.json", b"\xff"),
            (
                "contracts/canonical/test.schema.json",
                b'{"$defs":{"value":{"title":"first","title":"second"}}}',
            ),
            ("contracts/canonical/test.schema.json", b"\xff"),
        ):
            with self.subTest(target=target, raw=raw):
                fixture = AuthorityFixture.with_registry()
                try:
                    fixture.write_bytes(target, raw)
                    with self.assertRaises(AuthorityViolation):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_referenced_schema_rejects_non_finite_json_constants(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                fixture = AuthorityFixture.with_registry()
                try:
                    fixture.write_bytes(
                        "contracts/canonical/test.schema.json",
                        (
                            '{"$defs":{"value":{"const":'
                            + constant
                            + "}}}"
                        ).encode("ascii"),
                    )

                    with self.assertRaisesRegex(
                        AuthorityViolation, "non-finite JSON constant"
                    ):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_rejects_noncanonical_canonical_roots(self) -> None:
        for value in (
            "/contracts/canonical",
            "contracts//canonical",
            "contracts/./canonical",
            "contracts/../canonical",
            "contracts\\canonical",
        ):
            with self.subTest(value=value):
                fixture = AuthorityFixture.with_registry()
                try:
                    manifest = json.loads(fixture.read("contracts/canonical/authority.json"))
                    manifest["canonicalRoots"] = [value]
                    fixture.write("contracts/canonical/authority.json", json.dumps(manifest))
                    with self.assertRaisesRegex(AuthorityViolation, "invalid canonical root path"):
                        fixture.verify()
                finally:
                    fixture.close()

    def test_canonical_root_must_be_a_real_directory(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write("contracts/not-a-directory", "not a directory\n")
        fixture.write_manifest(canonicalRoots=["contracts/not-a-directory"])

        with self.assertRaisesRegex(AuthorityViolation, "canonical root.*directory"):
            fixture.verify()

    def test_existing_changed_path_must_be_a_regular_file(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        (fixture.root / "changed-directory").mkdir()

        with self.assertRaisesRegex(AuthorityViolation, "changed path.*regular file"):
            fixture.check(["changed-directory"])

    def test_existing_changed_file_must_be_readable_without_matching_a_rule(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        relative = "unmatched.bin"
        fixture.write_bytes(relative, b"content")
        (fixture.root / relative).chmod(0)

        with self.assertRaisesRegex(AuthorityViolation, "cannot read changed path"):
            fixture.check([relative])

    def test_changed_path_below_a_file_is_treated_as_deleted(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        fixture.write("parent", "replacement file\n")

        self.assertIsNone(fixture.check(["parent/deleted.py"]))

    def test_changed_paths_must_be_normalized_repository_relative_values(self) -> None:
        for relative in ("/absolute.py", "../escape.py", "dir/../escape.py", "dir//file.py"):
            with self.subTest(relative=relative):
                fixture = AuthorityFixture()
                try:
                    fixture.write_manifest()
                    with self.assertRaisesRegex(AuthorityViolation, "invalid changed path"):
                        fixture.check([relative])
                finally:
                    fixture.close()

    def test_changed_symlink_is_not_treated_as_a_regular_file(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        fixture.write("target.py", "ordinary = True\n")
        (fixture.root / "alias.py").symlink_to("target.py")

        with self.assertRaisesRegex(AuthorityViolation, "changed path.*regular file"):
            fixture.check(["alias.py"])

    def test_changed_symlink_loop_is_an_authority_violation(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        (fixture.root / "first").symlink_to("second")
        (fixture.root / "second").symlink_to("first")

        with self.assertRaisesRegex(AuthorityViolation, "invalid changed path"):
            fixture.check(["first"])

    def test_pinned_input_must_not_be_a_symlink(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        original = fixture.read(fixture.pinned_path)
        fixture.write("docs/other.md", original)
        pinned = fixture.root / fixture.pinned_path
        pinned.unlink()
        pinned.symlink_to("other.md")

        with self.assertRaisesRegex(AuthorityViolation, "authoritative input.*regular file"):
            fixture.verify()

    def test_existing_registry_path_must_be_a_regular_file(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest()
        (fixture.root / "contracts/canonical/canonical_object_registry.json").mkdir()

        with self.assertRaisesRegex(AuthorityViolation, "canonical object registry.*regular file"):
            fixture.verify()

    def test_registry_schema_ref_must_not_be_a_symlink(self) -> None:
        fixture = AuthorityFixture.with_registry()
        self.addCleanup(fixture.close)
        schema = fixture.root / "contracts/canonical/test.schema.json"
        schema.rename(schema.with_name("actual.schema.json"))
        schema.symlink_to("actual.schema.json")

        with self.assertRaisesRegex(AuthorityViolation, "canonical schemaRef.*regular file"):
            fixture.verify()

    def test_rejects_pinned_input_path_that_resolves_outside_repository(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.outside.mkdir()
        (fixture.outside / "pin.md").write_text("outside pin\n", encoding="utf-8")
        (fixture.root / "escape").symlink_to(fixture.outside, target_is_directory=True)
        relative = "escape/pin.md"
        blob = subprocess.run(
            ["git", "hash-object", "--", relative], cwd=fixture.root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        fixture.write_manifest(authoritativeInputs=[{
            "path": relative,
            "sourceCommit": "0" * 40,
            "gitBlobOid": blob,
            "sha256": hashlib.sha256((fixture.root / relative).read_bytes()).hexdigest(),
        }])

        with self.assertRaisesRegex(AuthorityViolation, "invalid authoritative input path"):
            fixture.verify()

    def test_rejects_legacy_adapter_path_that_resolves_outside_repository(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.outside.mkdir()
        (fixture.outside / "adapter.json").write_text("{}", encoding="utf-8")
        (fixture.root / "escape").symlink_to(fixture.outside, target_is_directory=True)
        relative = "escape/adapter.json"
        fixture.write_manifest(legacyAdapters=[{
            "path": relative,
            "mode": "adapter_only",
            "allowedProperties": [],
            "forbiddenEnumValues": [],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "invalid legacy adapter path"):
            fixture.check([relative])

    def test_rejects_escaped_generated_output_path(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "escaped-output",
            "sources": ["input.json"],
            "outputs": ["../generated.py"],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "invalid generated output path"):
            fixture.verify()

    def test_rejects_noncanonical_generated_source_pattern_segments(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "escaped-source",
            "sources": ["sources/../*.json"],
            "outputs": ["generated.py"],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "invalid generated source pattern"):
            fixture.verify()

    def test_allows_generated_source_gitwildmatch_negation(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "future-round-contracts",
            "sources": [
                "contracts/canonical/**/*.json",
                "!contracts/canonical/round_event_v2.schema.json",
            ],
            "outputs": ["generated.py"],
        }])

        fixture.verify()

    def test_rejects_generated_output_alias_before_owner_comparison(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[
            {"name": "canonical", "sources": ["a.json"], "outputs": ["generated.py"]},
            {"name": "alias", "sources": ["b.json"], "outputs": ["dir/../generated.py"]},
        ])

        with self.assertRaisesRegex(AuthorityViolation, "invalid generated output path"):
            fixture.verify()

    def test_rejects_new_business_fields_in_legacy_watch_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "mobile/contracts").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-contract-authority-v1",
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "canonicalRoots": ["contracts/canonical"],
                        "legacyAdapters": [
                            {
                                "path": "mobile/contracts/watch_input_event.schema.json",
                                "mode": "adapter_only",
                                "allowedProperties": ["schema", "eventId"],
                                "forbiddenEnumValues": ["sync_marker"],
                            }
                        ],
                        "forbiddenSymbols": [],
                        "generatedGroups": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "mobile/contracts/watch_input_event.schema.json").write_text(
                json.dumps({"properties": {"newBusinessFact": {"type": "string"}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuthorityViolation, "legacy contract expanded"):
                check_authority(root, changed_paths=["mobile/contracts/watch_input_event.schema.json"])

    def test_rejects_forbidden_string_in_changed_legacy_adapter(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        relative = "mobile/contracts/watch_input_event.schema.json"
        fixture.write_manifest(legacyAdapters=[{
            "path": relative,
            "mode": "adapter_only",
            "allowedProperties": ["kind"],
            "forbiddenEnumValues": ["sync_marker"],
        }])
        fixture.write(relative, json.dumps({
            "properties": {"kind": {"type": "string", "enum": ["sync_marker"]}}
        }))

        with self.assertRaisesRegex(AuthorityViolation, "legacy forbidden enum value"):
            fixture.check([relative])

    def test_allows_adapter_only_change_when_canonical_registry_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "mobile/contracts").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-contract-authority-v1",
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "canonicalRoots": ["contracts/canonical"],
                        "legacyAdapters": [
                            {
                                "path": "mobile/contracts/watch_input_event.schema.json",
                                "mode": "adapter_only",
                                "allowedProperties": [],
                                "forbiddenEnumValues": ["sync_marker"],
                            }
                        ],
                        "forbiddenSymbols": [],
                        "generatedGroups": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "mobile/contracts/watch_input_event.schema.json").write_text(
                json.dumps({"description": "legacy transport adapter"}), encoding="utf-8"
            )
            self.assertEqual(
                check_authority(root, changed_paths=["mobile/contracts/watch_input_event.schema.json"]),
                [],
            )

    def test_rejects_manifest_forbidden_symbol_in_changed_v2_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "ai_caddie/rounds").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-contract-authority-v1",
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "canonicalRoots": ["contracts/canonical"],
                        "legacyAdapters": [],
                        "forbiddenSymbols": [
                            {"paths": ["ai_caddie/rounds/*.py"], "values": ["weatherSnapshot"]}
                        ],
                        "generatedGroups": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "ai_caddie/rounds/models.py").write_text(
                "weatherSnapshot = {}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(AuthorityViolation, "forbidden symbol weatherSnapshot"):
                check_authority(root, changed_paths=["ai_caddie/rounds/models.py"])

    def test_changed_protected_text_must_be_valid_utf8(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("**/*.py")
        self.addCleanup(fixture.close)
        fixture.write_bytes("protected.py", b"\xff\xfe")

        with self.assertRaisesRegex(AuthorityViolation, "cannot read protected path"):
            fixture.check(["protected.py"])

    def test_forbidden_symbols_use_token_boundaries_and_changed_path_scope(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("**/*.py")
        self.addCleanup(fixture.close)
        fixture.write("suffix.py", "weatherSnapshotSuffix = True\n")
        fixture.write("unchanged.py", "weatherSnapshot = {}\n")

        fixture.check(["suffix.py"])

    def test_deleted_protected_path_is_a_valid_changed_path(self) -> None:
        fixture = AuthorityFixture.with_forbidden_pattern("**/*.py")
        self.addCleanup(fixture.close)

        self.assertEqual(fixture.check(["deleted.py"]), None)

    def test_generated_group_requires_a_source_and_owned_output_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-contract-authority-v1",
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "canonicalRoots": ["contracts/canonical"],
                        "legacyAdapters": [],
                        "forbiddenSymbols": [],
                        "generatedGroups": [
                            {
                                "name": "round-contracts",
                                "sources": ["contracts/canonical/events.json", "tools/generate.py"],
                                "outputs": ["python/generated.py", "swift/Generated.swift"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuthorityViolation, "generated group round-contracts"):
                check_authority(root, changed_paths=["python/generated.py"])
            with self.assertRaisesRegex(AuthorityViolation, "generated group round-contracts"):
                check_authority(root, changed_paths=["contracts/canonical/events.json"])
            self.assertEqual(
                check_authority(
                    root,
                    changed_paths=[
                        "contracts/canonical/events.json",
                        "python/generated.py",
                    ],
                ),
                [],
            )

    def test_authority_manifest_change_is_metadata_not_a_generated_source(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "canonical-contracts",
            "sources": ["contracts/canonical/**/*.json", "tools/generate.py"],
            "outputs": ["python/generated.py"],
        }])

        self.assertEqual(
            fixture.check(["contracts/canonical/authority.json"]),
            None,
        )

    def test_generated_output_has_exactly_one_group_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps({
                    "schema": "ai-caddie-contract-authority-v1",
                    "authoritativeInputs": [], "evidenceInputs": [],
                    "canonicalRoots": ["contracts/canonical"],
                    "legacyAdapters": [], "forbiddenSymbols": [],
                    "generatedGroups": [
                        {"name": "a", "sources": ["a.json"], "outputs": ["generated.py"]},
                        {"name": "b", "sources": ["b.json"], "outputs": ["generated.py"]},
                    ],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuthorityViolation, "multiple generated owners"):
                check_authority(root, changed_paths=[])

    def test_generated_group_rejects_duplicate_output_within_one_owner(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "canonical",
            "sources": ["source.json"],
            "outputs": ["generated.py", "generated.py"],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "duplicate generated output"):
            fixture.verify()

    def test_generated_group_rejects_duplicate_source_patterns(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[{
            "name": "canonical",
            "sources": ["source.json", "source.json"],
            "outputs": ["generated.py"],
        }])

        with self.assertRaisesRegex(AuthorityViolation, "duplicate generated source"):
            fixture.verify()

    def test_generated_output_cannot_also_match_its_source_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps({
                    "schema": "ai-caddie-contract-authority-v1",
                    "authoritativeInputs": [], "evidenceInputs": [],
                    "canonicalRoots": ["contracts/canonical"],
                    "legacyAdapters": [], "forbiddenSymbols": [],
                    "generatedGroups": [{
                        "name": "canonical-contracts",
                        "sources": ["contracts/canonical/**/*.json"],
                        "outputs": ["contracts/canonical/generated.schema.json"],
                    }],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AuthorityViolation, "also matches a source"):
                check_authority(root, changed_paths=[])

    def test_generated_output_cannot_match_another_groups_source_pattern(self) -> None:
        fixture = AuthorityFixture()
        self.addCleanup(fixture.close)
        fixture.write_manifest(generatedGroups=[
            {
                "name": "source-owner",
                "sources": ["shared/**/*.json"],
                "outputs": ["generated/source_owner.py"],
            },
            {
                "name": "output-owner",
                "sources": ["other/source.json"],
                "outputs": ["shared/generated.json"],
            },
        ])

        with self.assertRaisesRegex(
            AuthorityViolation, "source-owner.*shared/generated.json"
        ):
            fixture.verify()
