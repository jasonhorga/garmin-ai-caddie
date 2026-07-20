from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


class AuthorityFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "contracts/canonical").mkdir(parents=True)
        self.pinned_path = "docs/spec.md"

    def close(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, value: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def write_manifest(self, **changes: object) -> None:
        payload: dict[str, object] = {
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

    def test_pinned_authority_byte_or_commit_drift_fails(self) -> None:
        fixture = AuthorityFixture.with_pinned_input()
        self.addCleanup(fixture.close)
        fixture.verify()
        fixture.write(fixture.pinned_path, fixture.read(fixture.pinned_path) + "\n")
        with self.assertRaisesRegex(AuthorityViolation, "pinned input sha256"):
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

    def test_rejects_new_business_fields_in_legacy_watch_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "mobile/contracts").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "legacyAdapters": [
                            {
                                "path": "mobile/contracts/watch_input_event.schema.json",
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

    def test_allows_adapter_only_change_when_canonical_registry_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "mobile/contracts").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "legacyAdapters": [
                            {
                                "path": "mobile/contracts/watch_input_event.schema.json",
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
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
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

    def test_generated_group_requires_a_source_and_owned_output_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
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

    def test_generated_output_has_exactly_one_group_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps({
                    "authoritativeInputs": [], "evidenceInputs": [],
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

    def test_generated_output_cannot_also_match_its_source_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps({
                    "authoritativeInputs": [], "evidenceInputs": [],
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
