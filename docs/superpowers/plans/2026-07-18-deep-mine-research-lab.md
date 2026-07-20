# Deep Mine Research Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a replayable Deep Mine Research Lab that proves byte closure for a frozen authorized corpus, preserves every unknown occurrence, inventories protobuf/JSON/archive/Draco/texture/DSKIMG without silent loss, and emits evidence-bound promotion candidates without directly publishing product snapshots.

**Architecture:** Plan 1 supplies `canonical_json_bytes()` and `typed_id()`; Plan 2 supplies the only Raw CAS and acquisition receipt boundary through `CASRef`, `EncryptedCAS`, `SourceManifest`, and `ProviderResponse`. Track C adds research-only ByteDomains, Node Ledger, Lossless IR, Unknown Registry, format inventories, fingerprints, diffs, coverage, capture requests, and promotion candidates under `ai_caddie/research/deep_mine`; it may write derived CAS objects with explicit parent/transform records, but it must never import `snapshot_builder`, advance a release channel, or publish a `CourseSnapshot`.

**Tech Stack:** Python 3.12, standard-library `dataclasses`/`enum`/`hashlib`/`json`/`sqlite3`/`struct`/`zipfile`/`subprocess`, Pillow, Node.js 24, `draco3d`, Plan 1 canonical contracts, Plan 2 AES-GCM `EncryptedCAS`, `unittest`, Node's built-in `node:test`.

---

## Scope and dependency lock

This plan is Plan 3 of the course-data program and must be executed after these shared foundations exist:

- Plan 1: `ai_caddie/contracts/canonical_json.py::canonical_json_bytes` and `ai_caddie/contracts/typed_ids.py::typed_id`.
- Plan 2 Task B3: `ai_caddie/course_data/providers/base.py::ProviderResponse` and the shared occurrence-preserving `ai_caddie/course_data/providers/protobuf_wire.py`.
- Plan 2 Task B4: `ai_caddie/course_data/cas.py::CASRef`, `StaticDomainKeyProvider`, `EncryptedCAS`, plus `ai_caddie/course_data/source_manifest.py::SourceManifest`.

Normative interleave: Plan 2 B1–B7a (including the first and only complete `0008` checkpoint) → this plan C1–C16 → Plan 2 B8–B17. C15 **does not depend on B8 implementation**: it emits an evidence-bound research candidate whose exact `targetGate` is `plan-2-capability-quality-gate`. Plan 2 B8 later consumes/adjudicates that candidate under its product quality policy. C15 must not import or predict B8 policy classes/schema, and B8 must not be started merely to unblock C15. This removes the Plan 1 table's former apparent C15↔B8 cycle without moving product admission authority into Research Lab.

The shared Raw CAS boundary is normative:

```text
CASRef(storage_domain_id: str, byte_domain: str, sha256: str, size: int)
EncryptedCAS.put_bytes(storage_domain_id: str, byte_domain: str, data: bytes) -> CASRef
EncryptedCAS.read_bytes(storage_domain_id: str, ref: CASRef) -> bytes
```

Track C must not create `RawArtifact`, `RawStore`, a second CAS root, or a second SourceManifest. Archive members, decrypted plaintext, decoded image pixels, Lossless IR, fingerprints, coverage reports, and promotion candidates use new `byte_domain` values in the same `EncryptedCAS` and record `parent_refs + transform_name + transform_version + build_hash` in research provenance.

Legacy boundaries are also normative:

- `tools/courseview/fetch_courseview.py`, `tools/courseview/parse_courseview.py`, `tools/java/DumpMkgmapCourseView.java`, and `tools/java/DumpCourseView.java` remain fixture/oracle tools only.
- `ai_caddie/geometry/inspect_courseview_release.py`, `ai_caddie/courses/course_search.py::parse_course_search`, `ai_caddie/geometry/decode_courseview_geometry.js`, and `parse_date_layout()` remain migration/regression oracles; production research parsing moves to the shared wire walker and new Deep Mine parsers.
- `ai_caddie/geometry/fetch_courseview_geometry_key.js` may continue supplying authorized key/decrypt transport primitives, but its archive listing/extraction functions are not inventory authority.
- `ai_caddie/geometry/geometry_evidence.py`, `measure_prodgeometry_distances.py`, `course_prep.py`, `elevation.py`, and `topo_render.py` contain possible semantic/math candidates, not automatically promoted facts.
- No file in `ai_caddie/research/deep_mine` may import `ai_caddie.course_data.snapshot_builder`, `ai_caddie.course_data.channels`, or a client/server product DTO.
- Every evidence report named by a promotion candidate is a retrievable structured `CASRef`, scoped to one owner account and one Build/Storage Security Domain, and is included as an exact derived-object `parent_ref`; a bare 64-hex evidence hash is never sufficient admission evidence.
- A runtime hazard row's `evidenceRefs` value is a registry-backed `DeepMineHazardEvidenceMember/v1` member identity, not a standalone report hash: admission recomputes it from the row and requires that exact row inside the subject-bound, retrievable `hazardGuidanceSet` CAS parent whose hash is atomically bound by the coverage report.
- A hole promotion subject is revision-scoped and global-hole-scoped: `hole:<layoutRevisionId>:<holeGlobalId>`. Display `holeNumber` remains an asserted attribute and must never be used as the subject identity across revisions.
- Promotion binding arrays that model sets are duplicate-rejecting and canonically sorted before `candidateId` is computed. Occurrence streams, `LosslessIR.atoms`, archive central/local record order, DSKIMG block chains, and other fields with order semantics remain in observed order.

## File Structure

### Shared files extended by Track C

- Modify: `contracts/canonical/canonical_object_registry.json` — register `DeepMineCorpusArtifact/v1`, `DeepMineCorpus/v1`, `DeepMineByteDomain/v1`, `DeepMineNode/v1`, `DeepMineClosureProof/v1`, `DeepMineLosslessIR/v1`, `DeepMineDerivedArtifact/v1`, `DeepMineUnknown/v1`, `DeepMineFingerprint/v1`, `DeepMineCoverageReport/v1`, `DeepMineCaptureRequest/v1`, `DeepMineGmpVariantDescriptor/v1`, `DeepMineGmpDescriptorRegistry/v1`, `DeepMineAuthorizedImgMatrixRow/v1`, `DeepMineGreenOrientationTransform/v1`, `DeepMineHazardEvidenceMember/v1`, `DeepMinePromotionCandidate/v1`, `DeepMineDecoderBundle/v1`, and `DeepMineReplayReport/v1`.
- Create: `contracts/canonical/deep_mine_v1.schema.json` — shared schema anchors for every Track C canonical payload registered above.
- Modify: `ai_caddie/course_data/providers/protobuf_wire.py` — extend Plan 2's shared walker to wire types 0–5, groups, offsets, occurrence indexes, packed candidates, and bounded errors while retaining its existing fields.
- Modify: `package.json` — add the hermetic Node Draco test script.
- Modify: `.github/workflows/ci.yml` — install root Node dependencies before backend Deep Mine tests and run the Node inventory suite.

### Research package

- Create: `ai_caddie/research/__init__.py` — research namespace only.
- Create: `ai_caddie/research/deep_mine/__init__.py` — stable public research exports.
- Create: `ai_caddie/research/deep_mine/corpus.py` — frozen corpus manifest, Merkle root, strata, and CAS verification.
- Create: `ai_caddie/research/deep_mine/models.py` — ByteDomain, NodeRecord, NodeStatus, and closure-proof value types.
- Create: `ai_caddie/research/deep_mine/ledger.py` — same-domain accounting ledger and closure verifier.
- Create: `ai_caddie/research/deep_mine/ir.py` — lossless byte-slice IR and exact reassembly.
- Create: `ai_caddie/research/deep_mine/provenance.py` — derived CAS object plus parent/transform/build-hash DAG metadata.
- Create: `ai_caddie/research/deep_mine/budget.py` — deterministic byte/node/depth/output budgets.
- Create: `ai_caddie/research/deep_mine/parser_registry.py` — unique decoder selection and decoder-set fingerprint.
- Create: `ai_caddie/research/deep_mine/unknowns.py` — stable Unknown Registry and evidence lifecycle.
- Create: `ai_caddie/research/deep_mine/fingerprint.py` — content/structural/distribution fingerprints.
- Create: `ai_caddie/research/deep_mine/diff.py` — structural/cardinality/value-distribution diffs that register unknowns.
- Create: `ai_caddie/research/deep_mine/coverage.py` — multi-axis coverage and finite-corpus stop rule.
- Create: `ai_caddie/research/deep_mine/capture_requests.py` — engineering evidence-task generator.
- Create: `ai_caddie/research/deep_mine/playable_regions.py` — source-decoder composition root that freezes and trust-records the independent source roster before invoking the runtime projector.
- Create: `ai_caddie/research/deep_mine/promotion.py` — research-only promotion candidates with revision/global-hole subjects and owner/security-scoped evidence CAS parents for Plan 2 quality gates.
- Create: `ai_caddie/research/deep_mine/runner.py` — deterministic frozen-corpus replay.
- Create: `ai_caddie/research/deep_mine/cli.py` — offline lab CLI; no product route.
- Create: `ai_caddie/research/deep_mine/parsers/__init__.py`.
- Create: `ai_caddie/research/deep_mine/parsers/protobuf.py`.
- Create: `ai_caddie/research/deep_mine/parsers/json_occurrence.py`.
- Create: `ai_caddie/research/deep_mine/parsers/archive.py`.
- Create: `ai_caddie/research/deep_mine/parsers/texture.py`.
- Create: `ai_caddie/research/deep_mine/parsers/draco.py`.
- Create: `ai_caddie/research/deep_mine/parsers/dskimg.py`.
- Create: `ai_caddie/research/deep_mine/parsers/dskimg_header_facts.py` — strict evidence-backed raw IMG header signature registry; derives variants before GMP descriptor matching.
- Create: `ai_caddie/research/deep_mine/parsers/gmp.py` — descriptor-driven, section-local TRE/RGN/LBL/DEM/NET/NOD object inventory and byte-exact re-encoding.
- Create: `ai_caddie/research/deep_mine/parsers/gmp_descriptors.py` — strict evidence-backed GMP variant descriptor registry and unique matcher.
- Create: `ai_caddie/research/deep_mine/verify_img_matrix.py` — authorized real-corpus DSKIMG/GMP variant-matrix gate.
- Create: `ai_caddie/research/deep_mine/node/draco_inventory.js`.

### Research contracts and authorized corpus descriptors

- Create: `contracts/research/gmp_variant_descriptor_v1.schema.json` — strict schema for evidence-backed GMP header/section grammars.
- Create: `contracts/research/dskimg_header_facts_v1.schema.json` — strict schema for variant facts derived only from verified raw DSKIMG headers.
- Create: `contracts/research/authorized_garmin_img_matrix_v1.schema.json` — strict schema for non-secret authorized IMG matrix rows.
- Create: `research/corpus/gmp_variant_descriptors.json` — canonical descriptor bundle; production rows require multi-sample evidence.
- Create: `research/corpus/dskimg_header_facts.json` — canonical authorized header-fact bundle; no guessed classic/NT default.
- Create: `research/corpus/authorized_garmin_img_matrix.json` — canonical, body-free matrix of authorized CAS/source identities and required strata.

### Tests and generated fixtures

- Create: `tests/test_deep_mine_corpus.py`.
- Create: `tests/test_deep_mine_node_ledger.py`.
- Create: `tests/test_deep_mine_lossless_ir.py`.
- Create: `tests/test_deep_mine_parser_registry.py`.
- Create: `tests/test_deep_mine_unknown_registry.py`.
- Create: `tests/test_deep_mine_protobuf_inventory.py`.
- Create: `tests/test_deep_mine_json_inventory.py`.
- Create: `tests/test_deep_mine_archive_inventory.py`.
- Create: `tests/test_deep_mine_texture_inventory.py`.
- Create: `tests/test_deep_mine_draco_bridge.py`.
- Create: `tests/test_deep_mine_dskimg_inventory.py`.
- Create: `tests/test_deep_mine_gmp_objects.py`.
- Create: `tests/test_deep_mine_fingerprint_diff.py`.
- Create: `tests/test_deep_mine_coverage.py`.
- Create: `tests/test_deep_mine_capture_requests.py`.
- Create: `tests/test_deep_mine_promotion.py`.
- Create: `tests/test_deep_mine_replay.py`.
- Create: `tests/deep_mine_fixture_builders.py` — deterministic synthetic ZIP, image, protobuf, and DSKIMG byte builders; contains no provider secret or private bytes.
- Create: `tests/fixtures/research/synthetic_gmp_variant_descriptor.json` — test-only descriptor bound to the synthetic GMP bytes.
- Create: `tests/fixtures/research/synthetic_dskimg_header_facts.json` — test-only exact signatures for the synthetic DSKIMG builder.
- Create: `tests/fixtures/research/synthetic_gmp_golden.json` — exact section objects, cross-section edges, offsets, closure state, and re-encoded hashes.
- Create: `tests/fixtures/deep_mine_replay_v1.sha256` — checked-in deterministic full-corpus replay golden.
- Create: `tests/node/deep_mine_draco_inventory.test.js`.

## Dependency order

```text
C1 frozen corpus on shared CAS
  -> C2 ByteDomain / Node Ledger
      -> C3 Lossless IR / derived provenance
          -> C4 parser registry / budgets
              -> C5 Unknown Registry
                  -> C6 protobuf ─┐
                  -> C7 JSON     ├─ parallel inventories
                  -> C8 archive  ┤
                  -> C9 texture  ┤
                  -> C10 Draco   ┤
                  -> C11 DSKIMG ─┘
                       -> C12 fingerprint / diff
                           -> C13 coverage / stop rule
                               -> C14 capture requests
                               -> C15 promotion candidates
                                   -> C16 deterministic replay / CI
```

### Task 1: C1 — Freeze an authorized corpus on the shared Raw CAS

**Files:**
- Create: `ai_caddie/research/__init__.py`
- Create: `ai_caddie/research/deep_mine/__init__.py`
- Create: `ai_caddie/research/deep_mine/corpus.py`
- Create: `contracts/canonical/deep_mine_v1.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tools/contracts/generate_contracts.py` — consume the new canonical source through the sole generator/authority lane.
- Modify: `ai_caddie/contracts/generated.py`
- Modify: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Modify: `web_v2/src/contracts/generated.ts`
- Modify: `tests/test_contract_codegen.py`
- Create: `tests/test_deep_mine_corpus.py`

- [ ] **Step 1: Write the failing corpus identity and cross-domain tests**

```python
# tests/test_deep_mine_corpus.py
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.corpus import CorpusArtifact, FrozenCorpusManifest


class DeepMineCorpusTests(unittest.TestCase):
    def test_every_track_c_domain_tag_resolves_to_the_shared_schema(self) -> None:
        registry = json.loads(Path("contracts/canonical/canonical_object_registry.json").read_text())
        expected = {
            "DeepMineCorpusArtifact": "DeepMineCorpusArtifact/v1",
            "DeepMineCorpus": "DeepMineCorpus/v1",
            "DeepMineByteDomain": "DeepMineByteDomain/v1",
            "DeepMineNode": "DeepMineNode/v1",
            "DeepMineClosureProof": "DeepMineClosureProof/v1",
            "DeepMineLosslessIR": "DeepMineLosslessIR/v1",
            "DeepMineDerivedArtifact": "DeepMineDerivedArtifact/v1",
            "DeepMineUnknown": "DeepMineUnknown/v1",
            "DeepMineFingerprint": "DeepMineFingerprint/v1",
            "DeepMineCoverageReport": "DeepMineCoverageReport/v1",
            "DeepMineCaptureRequest": "DeepMineCaptureRequest/v1",
            "DeepMineGmpVariantDescriptor": "DeepMineGmpVariantDescriptor/v1",
            "DeepMineGmpDescriptorRegistry": "DeepMineGmpDescriptorRegistry/v1",
            "DeepMineAuthorizedImgMatrixRow": "DeepMineAuthorizedImgMatrixRow/v1",
            "DeepMineGreenOrientationTransform": "DeepMineGreenOrientationTransform/v1",
            "DeepMineHazardEvidenceMember": "DeepMineHazardEvidenceMember/v1",
            "DeepMinePromotionCandidate": "DeepMinePromotionCandidate/v1",
            "DeepMineDecoderBundle": "DeepMineDecoderBundle/v1",
            "DeepMineReplayReport": "DeepMineReplayReport/v1",
        }
        for name, domain_tag in expected.items():
            entry = registry["objects"][name]
            self.assertEqual(entry["domainTag"], domain_tag)
            self.assertTrue(entry["schemaRef"].startswith("contracts/canonical/deep_mine_v1.schema.json#/$defs/"))
            self.assertNotIn("*", entry["includedFields"])
        self.assertEqual(registry["objects"]["DeepMineUnknown"]["includedFields"], ["namespace", "locator"])
        self.assertEqual(
            registry["objects"]["DeepMineGmpVariantDescriptor"]["includedFields"],
            ["schema", "evidenceKind", "sourceRevisionIds", "evidenceRefs", "match", "sections"],
        )
        self.assertEqual(
            registry["objects"]["DeepMineGmpDescriptorRegistry"]["includedFields"],
            ["descriptorIds"],
        )
        self.assertEqual(
            registry["objects"]["DeepMineDecoderBundle"]["includedFields"],
            ["parserRegistryId", "gmpDescriptorRegistryId", "dskImgHeaderFactsRegistryId", "buildHash"],
        )
        self.assertIn("reportHash", registry["objects"]["DeepMineReplayReport"]["excludedFields"])
        schema = json.loads(Path("contracts/canonical/deep_mine_v1.schema.json").read_text())
        self.assertEqual(
            registry["objects"]["DeepMineAuthorizedImgMatrixRow"]["includedFields"],
            schema["$defs"]["authorizedImgMatrixRowIdentity"]["required"],
        )
        promotion = schema["$defs"]["promotionCandidate"]
        self.assertFalse(promotion["additionalProperties"])
        self.assertEqual(len(promotion["properties"]["capabilityEvidence"]["oneOf"]), 3)
        self.assertEqual(promotion["properties"]["subjectRef"]["pattern"], "^hole:[^:]+:[^:]+$")
        binding = schema["$defs"]["promotionBinding"]
        self.assertIn("evidenceCasRefs", binding["required"])
        self.assertIn("ownerAccountId", binding["required"])
        self.assertIn("securityDomainId", binding["required"])
        self.assertEqual(binding["properties"]["rawRefs"]["items"]["$ref"], "#/$defs/casRef")
        self.assertEqual(binding["properties"]["derivedRefs"]["items"]["$ref"], "#/$defs/casRef")
        self.assertEqual(binding["properties"]["assetRefs"]["items"]["$ref"], "#/$defs/casRef")
        self.assertNotIn("qualityReportHash", binding["properties"])
        evidence_ref = schema["$defs"]["evidenceCasRef"]
        self.assertFalse(evidence_ref["additionalProperties"])
        self.assertEqual(evidence_ref["properties"]["casRef"]["$ref"], "#/$defs/casRef")
        self.assertEqual(
            evidence_ref["properties"]["sourceInventoryTrust"]["$ref"],
            "#/$defs/sourceInventoryTrust",
        )
        self.assertFalse(schema["$defs"]["sourceInventoryTrust"]["additionalProperties"])
        for identity_def in (
            "gmpVariantDescriptorIdentity",
            "gmpDescriptorRegistryIdentity",
            "authorizedImgMatrixRowIdentity",
            "decoderBundleIdentity",
        ):
            self.assertFalse(schema["$defs"][identity_def]["additionalProperties"])

    def test_late_track_c_typed_id_golden_values_are_frozen(self) -> None:
        cas_ref = {
            "storageDomainId": "domain", "byteDomain": "raw-entity",
            "sha256": "0" * 64, "size": 1,
        }
        fixtures = {
            "DeepMineGmpVariantDescriptor/v1": ({
                "schema": "ai-caddie-gmp-variant-descriptor-v1",
                "evidenceKind": "synthetic",
                "sourceRevisionIds": ["source-revision-1"],
                "evidenceRefs": [cas_ref],
                "match": {},
                "sections": {},
            }, "236f5e3f8bf639da8cb0cb01cef86a323d1a1330d7ef6ef62fcd6888ea28c3d2"),
            "DeepMineGmpDescriptorRegistry/v1": ({
                "descriptorIds": ["1" * 64],
            }, "d933410a3756253c5c2f9be3d81ff6d9b90bff2ef21f7160f88f19e0a6338e30"),
            "DeepMineAuthorizedImgMatrixRow/v1": ({
                "ownerAccountId": "owner",
                "securityDomainId": "domain",
                "artifactRef": cas_ref,
                "artifactId": "2" * 64,
                "sourceManifestId": "3" * 64,
                "sourceRevisionId": "4" * 64,
                "providerConfigurationId": "provider-v1",
                "deviceFamily": "device",
                "softwareVersion": "1",
                "wrapperKind": "raw-img",
                "imgHeaderVariant": "classic",
                "gmpHeaderLength": 49,
                "descriptorId": "5" * 64,
                "presentSections": ["LBL", "RGN", "TRE"],
                "labelCodepage": 65001,
                "demPresent": False,
                "expectedSectionSha256": {
                    "LBL": "6" * 64, "RGN": "7" * 64, "TRE": "8" * 64,
                },
                "expectedClosure": True,
            }, "d5735857699a1273a450c9c507a1e4f133cb8522559b8c93618442224aaaf49a"),
            "DeepMineDecoderBundle/v1": ({
                "parserRegistryId": "9" * 64,
                "gmpDescriptorRegistryId": "a" * 64,
                "dskImgHeaderFactsRegistryId": "b" * 64,
                "buildHash": "build-v1",
            }, "2abaa4817f07244d2c20eb607dd5c301fd6fb19c2a07fdd6b8aa82477cd43a18"),
        }
        for domain_tag, (payload, expected_id) in fixtures.items():
            self.assertEqual(typed_id(domain_tag, payload), expected_id)

    def test_merkle_root_is_order_independent_and_reads_through_shared_cas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            release_ref = cas.put_bytes("account-a", "raw-entity", b"release-pb")
            archive_ref = cas.put_bytes("account-a", "raw-entity", b"geometry-zip")
            release = CorpusArtifact(
                source_manifest_id="manifest-release",
                cas_ref=release_ref,
                media_type="application/x-protobuf",
                source_type="course-layout-release",
                format_family="protobuf-wire",
                magic_prefix_hex="",
                schema_family="garmin-course-layout",
                schema_version="1",
                strata=("region:cn", "holes:9"),
            )
            archive = CorpusArtifact(
                source_manifest_id="manifest-archive",
                cas_ref=archive_ref,
                media_type="application/zip",
                source_type="prodgeometry-archive",
                format_family="zip",
                magic_prefix_hex="504b0304",
                schema_family="garmin-prodgeometry",
                schema_version="280630",
                strata=("region:cn", "terrain:mountain"),
            )
            first = FrozenCorpusManifest.create("decoder-set-1", [release, archive])
            second = FrozenCorpusManifest.create("decoder-set-1", [archive, release])
            self.assertEqual(first.corpus_id, second.corpus_id)
            self.assertEqual(first.merkle_root, second.merkle_root)
            self.assertEqual(first.read_artifact(cas, "account-a", release), b"release-pb")
            with self.assertRaisesRegex(PermissionError, "storage domain mismatch"):
                first.read_artifact(cas, "account-b", release)

    def test_same_raw_hash_in_different_byte_domains_is_not_the_same_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            raw_ref = cas.put_bytes("account-a", "raw-entity", b"same")
            member_ref = cas.put_bytes("account-a", "archive-member", b"same")
            raw = CorpusArtifact("m1", raw_ref, "application/octet-stream", "raw", "opaque", "", "bytes", "1", ())
            member = CorpusArtifact("m1", member_ref, "application/octet-stream", "member", "opaque", "", "bytes", "1", ())
            self.assertNotEqual(raw.artifact_id, member.artifact_id)
```

- [ ] **Step 2: Run the tests and verify the shared dependency fails first**

Run: `uv run python -m unittest tests.test_deep_mine_corpus -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.corpus`; if Plan 2 Task B4 has not run, it fails earlier importing `ai_caddie.course_data.cas`, which is a hard execution-order failure rather than permission to create another CAS.

- [ ] **Step 3: Implement the frozen corpus manifest**

```python
# ai_caddie/research/deep_mine/corpus.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS


def _ref_payload(ref: CASRef) -> dict[str, object]:
    return {
        "storageDomainId": ref.storage_domain_id,
        "byteDomain": ref.byte_domain,
        "sha256": ref.sha256,
        "size": ref.size,
    }


@dataclass(frozen=True)
class CorpusArtifact:
    source_manifest_id: str
    cas_ref: CASRef
    media_type: str
    source_type: str
    format_family: str
    magic_prefix_hex: str
    schema_family: str
    schema_version: str
    strata: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.format_family:
            raise ValueError("format family is required")
        if not re.fullmatch(r"(?:[0-9a-f]{2}){0,32}", self.magic_prefix_hex):
            raise ValueError("magicPrefixHex must contain at most 32 exact bytes")

    @property
    def artifact_id(self) -> str:
        return typed_id("DeepMineCorpusArtifact/v1", self.canonical())

    def canonical(self) -> dict[str, object]:
        return {
            "sourceManifestId": self.source_manifest_id,
            "casRef": _ref_payload(self.cas_ref),
            "mediaType": self.media_type,
            "sourceType": self.source_type,
            "formatFamily": self.format_family,
            "magicPrefixHex": self.magic_prefix_hex,
            "schemaFamily": self.schema_family,
            "schemaVersion": self.schema_version,
            "strata": sorted(set(self.strata)),
        }


@dataclass(frozen=True)
class FrozenCorpusManifest:
    corpus_id: str
    merkle_root: str
    decoder_set_id: str
    artifacts: tuple[CorpusArtifact, ...]

    @classmethod
    def create(cls, decoder_set_id: str, artifacts: Iterable[CorpusArtifact]) -> "FrozenCorpusManifest":
        ordered = tuple(sorted(artifacts, key=lambda item: item.artifact_id))
        leaves = [bytes.fromhex(item.artifact_id) for item in ordered]
        if not leaves:
            merkle_root = hashlib.sha256(b"").hexdigest()
        else:
            level = leaves
            while len(level) > 1:
                if len(level) % 2:
                    level = [*level, level[-1]]
                level = [hashlib.sha256(level[index] + level[index + 1]).digest() for index in range(0, len(level), 2)]
            merkle_root = level[0].hex()
        payload = {
            "decoderSetId": decoder_set_id,
            "merkleRoot": merkle_root,
            "artifacts": [item.canonical() for item in ordered],
        }
        return cls(typed_id("DeepMineCorpus/v1", payload), merkle_root, decoder_set_id, ordered)

    def canonical(self) -> dict[str, object]:
        return {
            "corpusId": self.corpus_id,
            "merkleRoot": self.merkle_root,
            "decoderSetId": self.decoder_set_id,
            "artifacts": [item.canonical() for item in self.artifacts],
        }

    def read_artifact(self, cas: EncryptedCAS, storage_domain_id: str, artifact: CorpusArtifact) -> bytes:
        return cas.read_bytes(storage_domain_id, artifact.cas_ref)
```

Create empty namespace files:

```python
# ai_caddie/research/__init__.py
"""Offline and server-side research packages; never imported by device clients."""
```

```python
# ai_caddie/research/deep_mine/__init__.py
from .corpus import CorpusArtifact, FrozenCorpusManifest

__all__ = ["CorpusArtifact", "FrozenCorpusManifest"]
```

- [ ] **Step 4: Register typed objects and run the focused tests**

Create the shared schema anchor file exactly as follows. Required field names match the canonical methods in this plan; the promotion candidate/binding/capability-evidence union is strict enough for Plan 2 admission validation, while other research payloads retain dataclass/test-owned nested validation and the registry freezes identity inclusion/exclusion.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-caddie.local/contracts/canonical/deep_mine_v1.schema.json",
  "title": "Deep Mine canonical payloads v1",
  "$defs": {
    "casRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["storageDomainId", "byteDomain", "sha256", "size"],
      "properties": {
        "storageDomainId": {"type": "string", "minLength": 1},
        "byteDomain": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "size": {"type": "integer", "minimum": 1, "maximum": 9007199254740991}
      }
    },
    "sourceInventoryTrust": {
      "type": "object",
      "additionalProperties": false,
      "required": ["artifactId", "recordSha256", "provenanceHash", "provenanceRef"],
      "properties": {
        "artifactId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "recordSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "provenanceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "provenanceRef": {"$ref": "#/$defs/casRef"}
      }
    },
    "evidenceCasRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["evidenceKind", "ownerAccountId", "securityDomainId", "sourceRevisionIds", "casRef"],
      "properties": {
        "evidenceKind": {"enum": ["researchEvidenceReport", "playsLikeCalibration", "hazardGuidanceSet", "hazardCoverage", "playableRegionsSourceInventory", "playableRegionsTopology", "playableRegionsCoverage", "greenRegistration", "greenCrossSource"]},
        "ownerAccountId": {"type": "string", "minLength": 1},
        "securityDomainId": {"type": "string", "minLength": 1},
        "sourceRevisionIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "casRef": {"$ref": "#/$defs/casRef"},
        "sourceInventoryTrust": {"$ref": "#/$defs/sourceInventoryTrust"}
      },
      "allOf": [{
        "if": {"properties": {"evidenceKind": {"const": "playableRegionsSourceInventory"}}, "required": ["evidenceKind"]},
        "then": {"required": ["sourceInventoryTrust"]},
        "else": {"not": {"required": ["sourceInventoryTrust"]}}
      }]
    },
    "promotionProductRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["role", "mediaType", "schemaId", "artifactId", "byteDomainId", "casRef"],
      "properties": {
        "role": {"enum": ["playsLike.model", "playsLike.elevation", "hazardGuidanceBody", "greenSurfaceGeometry", "guidance.playable-regions"]},
        "mediaType": {"type": "string", "minLength": 1},
        "schemaId": {"type": "string", "minLength": 1},
        "artifactId": {"type": "string", "minLength": 1},
        "byteDomainId": {"type": "string", "minLength": 1},
        "casRef": {"$ref": "#/$defs/casRef"}
      }
    },
    "corpusArtifact": {"type": "object", "required": ["sourceManifestId", "casRef", "mediaType", "sourceType", "formatFamily", "magicPrefixHex", "schemaFamily", "schemaVersion", "strata"], "additionalProperties": false},
    "corpus": {"type": "object", "required": ["corpusId", "merkleRoot", "decoderSetId", "artifacts"], "additionalProperties": true},
    "byteDomain": {"type": "object", "required": ["domainId", "casRef", "parentDomainId", "transformId"], "additionalProperties": true},
    "node": {"type": "object", "required": ["nodeId", "byteDomainId", "parentNodeId", "offset", "length", "status", "nodeKind", "decoderId", "decoderVersion", "occurrenceIndex", "accounting", "semanticHypothesis", "confidence", "consumedBy"], "additionalProperties": true},
    "closureProof": {"type": "object", "required": ["proofId", "byteDomainId", "rootNodeId", "domainSize", "classifiedBytes", "statusBytes", "complete"], "additionalProperties": true},
    "losslessIr": {"type": "object", "required": ["atoms"], "additionalProperties": false, "properties": {"atoms": {"type": "array"}}},
    "derivedArtifact": {"type": "object", "required": ["artifactId", "ref", "parentRefs", "transformName", "transformVersion", "parameters", "buildHash"], "additionalProperties": true},
    "unknown": {"type": "object", "required": ["unknownId", "namespace", "locator", "firstObservedAt", "lastObservedAt", "evidence", "status", "priority", "hypothesis", "counterevidence", "nextMinimumEvidence", "captureRequired"], "additionalProperties": true},
    "fingerprint": {"type": "object", "required": ["fingerprintId", "artifactId", "schemaFamily", "byteDomainId", "byteLength", "contentFingerprint", "structuralFingerprint", "distributionFingerprint", "structuralTokens", "structuralCounts", "distributionSummaries"], "additionalProperties": true},
    "coverageReport": {"type": "object", "required": ["reportId", "corpusId", "acquisition", "byteAccounting", "syntactic", "semantic", "strata", "fingerprints", "golden", "consumer", "errors"], "additionalProperties": true},
    "captureRequest": {"type": "object", "required": ["requestId", "unknownId", "gapKind", "uniqueQuestion", "positiveControl", "negativeControl", "context", "bodyRequirement", "hashAlgorithm", "redactionRules", "automaticValidator", "authorizedAccessRule", "destinationQueue", "optionalPager", "prohibitedProductSurfaces"], "additionalProperties": true},
    "gmpVariantDescriptorIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema", "evidenceKind", "sourceRevisionIds", "evidenceRefs", "match", "sections"],
      "properties": {
        "schema": {"const": "ai-caddie-gmp-variant-descriptor-v1"},
        "evidenceKind": {"enum": ["production_multi_sample", "research_only_single_sample", "synthetic"]},
        "sourceRevisionIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "evidenceRefs": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"$ref": "#/$defs/casRef"}},
        "match": {"type": "object"},
        "sections": {"type": "object"}
      }
    },
    "gmpDescriptorRegistryIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["descriptorIds"],
      "properties": {
        "descriptorIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}
      }
    },
    "authorizedImgMatrixRowIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["ownerAccountId", "securityDomainId", "artifactRef", "artifactId", "sourceManifestId", "sourceRevisionId", "providerConfigurationId", "deviceFamily", "softwareVersion", "wrapperKind", "imgHeaderVariant", "gmpHeaderLength", "descriptorId", "presentSections", "labelCodepage", "demPresent", "expectedSectionSha256", "expectedClosure"],
      "properties": {
        "ownerAccountId": {"type": "string", "minLength": 1},
        "securityDomainId": {"type": "string", "minLength": 1},
        "artifactRef": {"$ref": "#/$defs/casRef"},
        "artifactId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "sourceManifestId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "sourceRevisionId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "providerConfigurationId": {"type": "string", "minLength": 1},
        "deviceFamily": {"type": "string", "minLength": 1},
        "softwareVersion": {"type": "string", "minLength": 1},
        "wrapperKind": {"type": "string", "minLength": 1},
        "imgHeaderVariant": {"type": "string", "minLength": 1},
        "gmpHeaderLength": {"type": "integer", "minimum": 1},
        "descriptorId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "presentSections": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "labelCodepage": {"type": "integer", "minimum": 1},
        "demPresent": {"type": "boolean"},
        "expectedSectionSha256": {"type": "object"},
        "expectedClosure": {"const": true}
      }
    },
    "decoderBundleIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["parserRegistryId", "gmpDescriptorRegistryId", "dskImgHeaderFactsRegistryId", "buildHash"],
      "properties": {
        "parserRegistryId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "gmpDescriptorRegistryId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "dskImgHeaderFactsRegistryId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "buildHash": {"type": "string", "minLength": 1}
      }
    },
    "promotionBinding": {
      "type": "object",
      "additionalProperties": false,
      "required": ["ownerAccountId", "securityDomainId", "courseLayoutIdentity", "layoutRevisionId", "sourceRevisionIds", "sourceRosterHash", "holeGlobalId", "holeNumber", "rawRefs", "derivedRefs", "assetRefs", "closureProofIds", "fingerprintIds", "fingerprintedArtifactIds", "unknownIds", "consumedNodeIds", "evidenceRefs", "evidenceCasRefs", "researchEvidenceReportHash"],
      "properties": {
        "ownerAccountId": {"type": "string", "minLength": 1},
        "securityDomainId": {"type": "string", "minLength": 1},
        "courseLayoutIdentity": {"type": "string", "minLength": 1},
        "layoutRevisionId": {"type": "string", "minLength": 1},
        "sourceRevisionIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "sourceRosterHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "holeGlobalId": {"type": "string", "minLength": 1},
        "holeNumber": {"type": "integer", "minimum": 1, "maximum": 18},
        "rawRefs": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"$ref": "#/$defs/casRef"}},
        "derivedRefs": {"type": "array", "uniqueItems": true, "items": {"$ref": "#/$defs/casRef"}},
        "assetRefs": {"type": "array", "uniqueItems": true, "items": {"$ref": "#/$defs/casRef"}},
        "closureProofIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "fingerprintIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "fingerprintedArtifactIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "unknownIds": {"type": "array", "uniqueItems": true, "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"}},
        "consumedNodeIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "evidenceRefs": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "evidenceCasRefs": {"type": "array", "minItems": 2, "uniqueItems": true, "items": {"$ref": "#/$defs/evidenceCasRef"}},
        "researchEvidenceReportHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      }
    },
    "playsLikeEvidence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["evidenceKind", "sourceRevisionId", "axisAttestationId", "horizontalAxis", "verticalAxis", "horizontalUnit", "verticalUnit", "modelVersion", "adjustmentPerVerticalMeter", "calibrationAnchorIds", "maxAnchorDistanceM", "residualRmseM", "maxAbsResidualM", "outlierThresholdM", "outlierCount", "sampleCount", "sampleCourseCount", "sampleRegionCount", "calibrationEvidenceHash", "consumerId"],
      "properties": {
        "evidenceKind": {"const": "playsLike"},
        "sourceRevisionId": {"type": "string", "minLength": 1},
        "axisAttestationId": {"type": "string", "minLength": 1},
        "horizontalAxis": {"type": "string", "minLength": 1},
        "verticalAxis": {"type": "string", "minLength": 1},
        "horizontalUnit": {"const": "meter"},
        "verticalUnit": {"const": "meter"},
        "modelVersion": {"type": "string", "minLength": 1},
        "adjustmentPerVerticalMeter": {"type": "number", "minimum": -5, "maximum": 5},
        "calibrationAnchorIds": {"type": "array", "minItems": 3, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "maxAnchorDistanceM": {"type": "number", "minimum": 0},
        "residualRmseM": {"type": "number", "minimum": 0},
        "maxAbsResidualM": {"type": "number", "minimum": 0},
        "outlierThresholdM": {"type": "number", "minimum": 0},
        "outlierCount": {"type": "integer", "minimum": 0},
        "sampleCount": {"type": "integer", "minimum": 1},
        "sampleCourseCount": {"type": "integer", "minimum": 1},
        "sampleRegionCount": {"type": "integer", "minimum": 1},
        "calibrationEvidenceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "consumerId": {"type": "string", "minLength": 1}
      }
    },
    "hazardEvidenceMemberIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["hazardRef", "sourceRevisionId", "hazardSemanticKind", "routeGeometryHash", "stationingBasis", "landingWindowHash", "baseGeometryHash", "enterDistanceM", "clearDistanceM"],
      "properties": {
        "hazardRef": {"type": "string", "minLength": 1},
        "sourceRevisionId": {"type": "string", "minLength": 1},
        "hazardSemanticKind": {"enum": ["bunker", "water", "penalty_area", "vegetation", "out_of_bounds", "forced_carry", "layup"]},
        "routeGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "stationingBasis": {"const": "tee-origin-route-station-v1"},
        "landingWindowHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "baseGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "enterDistanceM": {"type": "number", "minimum": 0},
        "clearDistanceM": {"type": ["number", "null"], "minimum": 0}
      }
    },
    "hazardEvidenceRow": {
      "type": "object",
      "additionalProperties": false,
      "required": ["hazardRef", "sourceRevisionId", "hazardSemanticKind", "routeGeometryHash", "stationingBasis", "landingWindowHash", "baseGeometryHash", "enterDistanceM", "clearDistanceM", "evidenceHash"],
      "properties": {
        "hazardRef": {"type": "string", "minLength": 1},
        "sourceRevisionId": {"type": "string", "minLength": 1},
        "hazardSemanticKind": {"enum": ["bunker", "water", "penalty_area", "vegetation", "out_of_bounds", "forced_carry", "layup"]},
        "routeGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "stationingBasis": {"const": "tee-origin-route-station-v1"},
        "landingWindowHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "baseGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "enterDistanceM": {"type": "number", "minimum": 0},
        "clearDistanceM": {"type": ["number", "null"], "minimum": 0},
        "evidenceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      }
    },
    "hazardGuidanceEvidence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["evidenceKind", "sourceRevisionIds", "routeGeometryHash", "stationingBasis", "hazardSetEvidenceHash", "coverageEvidenceHash", "playableRegionsMapGeometryHash", "playableRegionsRegistrationResidualM", "playableRegionsTopologyEvidenceHash", "playableRegionsCoverageEvidenceHash", "hazards", "consumerId"],
      "properties": {
        "evidenceKind": {"const": "hazardGuidance"},
        "sourceRevisionIds": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1}},
        "routeGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "stationingBasis": {"const": "tee-origin-route-station-v1"},
        "hazardSetEvidenceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "coverageEvidenceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "playableRegionsMapGeometryHash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
        "playableRegionsRegistrationResidualM": {"type": ["number", "null"], "minimum": 0},
        "playableRegionsTopologyEvidenceHash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
        "playableRegionsCoverageEvidenceHash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
        "hazards": {"type": "array", "uniqueItems": true, "items": {"$ref": "#/$defs/hazardEvidenceRow"}},
        "consumerId": {"type": "string", "minLength": 1}
      }
    },
    "greenOrientationTransformIdentity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["matrix"],
      "properties": {
        "matrix": {"type": "array", "minItems": 6, "maxItems": 6, "items": {"type": "number"}}
      }
    },
    "greenSurfaceEvidence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["evidenceKind", "greenSourceRevisionId", "baseSourceRevisionId", "greenSourceSha256", "selectedComponentId", "decoderId", "decoderVersion", "calibrationId", "orientationTransformId", "baseGeometryHash", "slopeMagnitudePct", "downhillDirectionDeg", "registrationResidualM", "crossSourceResidualM", "registrationSampleCount", "registrationReportHash", "crossSourceEvidenceHash", "consumerId"],
      "properties": {
        "evidenceKind": {"const": "greenSurface"},
        "greenSourceRevisionId": {"type": "string", "minLength": 1},
        "baseSourceRevisionId": {"type": "string", "minLength": 1},
        "greenSourceSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "selectedComponentId": {"type": "string", "minLength": 1},
        "decoderId": {"type": "string", "minLength": 1},
        "decoderVersion": {"type": "string", "minLength": 1},
        "calibrationId": {"type": "string", "minLength": 1},
        "orientationTransformId": {"type": "string", "minLength": 1},
        "baseGeometryHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "slopeMagnitudePct": {"type": "number", "minimum": 0, "maximum": 100},
        "downhillDirectionDeg": {"type": "number", "minimum": 0, "exclusiveMaximum": 360},
        "registrationResidualM": {"type": "number", "minimum": 0},
        "crossSourceResidualM": {"type": "number", "minimum": 0},
        "registrationSampleCount": {"type": "integer", "minimum": 3, "maximum": 9007199254740991},
        "registrationReportHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "crossSourceEvidenceHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "consumerId": {"type": "string", "minLength": 1}
      }
    },
    "promotionCandidate": {
      "type": "object",
      "additionalProperties": false,
      "required": ["candidateId", "candidateState", "targetGate", "capability", "subjectRef", "projectorId", "qualityPolicyVersion", "binding", "productRefs", "capabilityEvidence"],
      "properties": {
        "candidateId": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "candidateState": {"const": "research_only_candidate"},
        "targetGate": {"const": "plan-2-capability-quality-gate"},
        "capability": {"enum": ["playsLike", "hazardGuidance", "greenSurface"]},
        "subjectRef": {"type": "string", "pattern": "^hole:[^:]+:[^:]+$"},
        "projectorId": {"type": "string", "minLength": 1},
        "qualityPolicyVersion": {"type": "string", "minLength": 1},
        "binding": {"$ref": "#/$defs/promotionBinding"},
        "productRefs": {"type": "array", "minItems": 1, "maxItems": 1, "uniqueItems": true, "items": {"$ref": "#/$defs/promotionProductRef"}},
        "capabilityEvidence": {"oneOf": [{"$ref": "#/$defs/playsLikeEvidence"}, {"$ref": "#/$defs/hazardGuidanceEvidence"}, {"$ref": "#/$defs/greenSurfaceEvidence"}]}
      },
      "allOf": [
        {"if": {"properties": {"capability": {"const": "playsLike"}}}, "then": {"properties": {"capabilityEvidence": {"$ref": "#/$defs/playsLikeEvidence"}}}},
        {"if": {"properties": {"capability": {"const": "hazardGuidance"}}}, "then": {"properties": {"capabilityEvidence": {"$ref": "#/$defs/hazardGuidanceEvidence"}}}},
        {"if": {"properties": {"capability": {"const": "greenSurface"}}}, "then": {"properties": {"capabilityEvidence": {"$ref": "#/$defs/greenSurfaceEvidence"}}}}
      ]
    },
    "replayReport": {"type": "object", "required": ["reportHash", "corpusId", "corpusMerkleRoot", "decoderSetId", "parserRegistryId", "gmpDescriptorRegistryId", "buildHash", "artifacts", "closureProofs", "fingerprints", "unknownRecords", "coverage"], "additionalProperties": true}
  }
}
```

Insert these exact members into the existing registry's `objects` map; keep every Plan 1/Plan 2 entry unchanged.

```json
{
"DeepMineCorpusArtifact": {"domainTag": "DeepMineCorpusArtifact/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/corpusArtifact", "includedFields": ["sourceManifestId", "casRef", "mediaType", "sourceType", "formatFamily", "magicPrefixHex", "schemaFamily", "schemaVersion", "strata"], "excludedFields": []},
"DeepMineCorpus": {"domainTag": "DeepMineCorpus/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/corpus", "includedFields": ["decoderSetId", "merkleRoot", "artifacts"], "excludedFields": ["corpusId"]},
"DeepMineByteDomain": {"domainTag": "DeepMineByteDomain/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/byteDomain", "includedFields": ["casRef", "parentDomainId", "transformId"], "excludedFields": ["domainId"]},
"DeepMineNode": {"domainTag": "DeepMineNode/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/node", "includedFields": ["byteDomainId", "parentNodeId", "offset", "length", "status", "nodeKind", "decoderId", "decoderVersion", "occurrenceIndex", "accounting", "semanticHypothesis", "confidence", "consumedBy"], "excludedFields": ["nodeId"]},
"DeepMineClosureProof": {"domainTag": "DeepMineClosureProof/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/closureProof", "includedFields": ["byteDomainId", "rootNodeId", "domainSize", "classifiedBytes", "statusBytes", "complete"], "excludedFields": ["proofId"]},
"DeepMineLosslessIR": {"domainTag": "DeepMineLosslessIR/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/losslessIr", "includedFields": ["atoms"], "excludedFields": []},
"DeepMineDerivedArtifact": {"domainTag": "DeepMineDerivedArtifact/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/derivedArtifact", "includedFields": ["ref", "parentRefs", "transformName", "transformVersion", "parameters", "buildHash"], "excludedFields": ["artifactId"]},
"DeepMineUnknown": {"domainTag": "DeepMineUnknown/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/unknown", "includedFields": ["namespace", "locator"], "excludedFields": ["unknownId", "firstObservedAt", "lastObservedAt", "evidence", "status", "priority", "hypothesis", "counterevidence", "nextMinimumEvidence", "captureRequired"]},
"DeepMineFingerprint": {"domainTag": "DeepMineFingerprint/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/fingerprint", "includedFields": ["artifactId", "schemaFamily", "byteDomainId", "byteLength", "contentFingerprint", "structuralFingerprint", "distributionFingerprint"], "excludedFields": ["fingerprintId", "structuralTokens", "structuralCounts", "distributionSummaries"]},
"DeepMineCoverageReport": {"domainTag": "DeepMineCoverageReport/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/coverageReport", "includedFields": ["corpusId", "acquisition", "byteAccounting", "syntactic", "semantic", "strata", "fingerprints", "golden", "consumer", "errors"], "excludedFields": ["reportId"]},
"DeepMineCaptureRequest": {"domainTag": "DeepMineCaptureRequest/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/captureRequest", "includedFields": ["unknownId", "gapKind", "uniqueQuestion", "positiveControl", "negativeControl", "context", "bodyRequirement", "hashAlgorithm", "redactionRules", "automaticValidator", "authorizedAccessRule", "destinationQueue", "optionalPager", "prohibitedProductSurfaces"], "excludedFields": ["requestId"]},
"DeepMineGmpVariantDescriptor": {"domainTag": "DeepMineGmpVariantDescriptor/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/gmpVariantDescriptorIdentity", "includedFields": ["schema", "evidenceKind", "sourceRevisionIds", "evidenceRefs", "match", "sections"], "excludedFields": ["descriptorId"]},
"DeepMineGmpDescriptorRegistry": {"domainTag": "DeepMineGmpDescriptorRegistry/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/gmpDescriptorRegistryIdentity", "includedFields": ["descriptorIds"], "excludedFields": ["registryId"]},
"DeepMineAuthorizedImgMatrixRow": {"domainTag": "DeepMineAuthorizedImgMatrixRow/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/authorizedImgMatrixRowIdentity", "includedFields": ["ownerAccountId", "securityDomainId", "artifactRef", "artifactId", "sourceManifestId", "sourceRevisionId", "providerConfigurationId", "deviceFamily", "softwareVersion", "wrapperKind", "imgHeaderVariant", "gmpHeaderLength", "descriptorId", "presentSections", "labelCodepage", "demPresent", "expectedSectionSha256", "expectedClosure"], "excludedFields": ["rowId"]},
"DeepMineGreenOrientationTransform": {"domainTag": "DeepMineGreenOrientationTransform/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/greenOrientationTransformIdentity", "includedFields": ["matrix"], "excludedFields": []},
"DeepMineHazardEvidenceMember": {"domainTag": "DeepMineHazardEvidenceMember/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/hazardEvidenceMemberIdentity", "includedFields": ["hazardRef", "sourceRevisionId", "hazardSemanticKind", "routeGeometryHash", "stationingBasis", "landingWindowHash", "baseGeometryHash", "enterDistanceM", "clearDistanceM"], "excludedFields": []},
"DeepMinePromotionCandidate": {"domainTag": "DeepMinePromotionCandidate/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/promotionCandidate", "includedFields": ["candidateState", "targetGate", "capability", "subjectRef", "projectorId", "qualityPolicyVersion", "binding", "productRefs", "capabilityEvidence"], "excludedFields": ["candidateId"]},
"DeepMineDecoderBundle": {"domainTag": "DeepMineDecoderBundle/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/decoderBundleIdentity", "includedFields": ["parserRegistryId", "gmpDescriptorRegistryId", "dskImgHeaderFactsRegistryId", "buildHash"], "excludedFields": ["decoderBundleId"]},
"DeepMineReplayReport": {"domainTag": "DeepMineReplayReport/v1", "schemaRef": "contracts/canonical/deep_mine_v1.schema.json#/$defs/replayReport", "includedFields": ["corpusId", "corpusMerkleRoot", "decoderSetId", "parserRegistryId", "gmpDescriptorRegistryId", "buildHash", "artifacts", "closureProofs", "fingerprints", "unknownRecords", "coverage"], "excludedFields": ["reportHash"]}
}
```

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python tools/contracts/generate_contracts.py --check
uv run python -m unittest tests.test_deep_mine_corpus tests.test_course_raw_cas tests.test_canonical_contract_ids tests.test_contract_codegen -v
```

Expected: all tests PASS; every Track C domain tag resolves to the checked-in schema anchor; the same bytes in `raw-entity` and `archive-member` have different artifact identities; cross-domain reads fail；the sole `canonical-contracts` authority accepts the new source and all Python/Swift/TypeScript generated outputs are current in this same C1 checkpoint.

- [ ] **Step 5: Commit C1**

```bash
git add ai_caddie/research/__init__.py ai_caddie/research/deep_mine/__init__.py ai_caddie/research/deep_mine/corpus.py contracts/canonical/deep_mine_v1.schema.json contracts/canonical/canonical_object_registry.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts tests/test_contract_codegen.py tests/test_deep_mine_corpus.py
git commit -m "feat(research): freeze deep mine corpus on shared cas"
```

### Task 2: C2 — Add ByteDomain, Node Ledger, and exact closure proofs

**Files:**
- Create: `ai_caddie/research/deep_mine/models.py`
- Create: `ai_caddie/research/deep_mine/ledger.py`
- Create: `tests/test_deep_mine_node_ledger.py`

- [ ] **Step 1: Write failing partition, overlap, gap, and cross-domain tests**

```python
# tests/test_deep_mine_node_ledger.py
from __future__ import annotations

import unittest

from ai_caddie.course_data.cas import CASRef
from ai_caddie.research.deep_mine.ledger import ClosureError, NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord, NodeStatus


def domain(domain_id: str, size: int = 8) -> ByteDomain:
    return ByteDomain(domain_id, CASRef("account-a", "raw-entity", "a" * 64, size), None, None)


class NodeLedgerTests(unittest.TestCase):
    def test_direct_accounting_children_prove_exact_partition(self) -> None:
        ledger = NodeLedger()
        ledger.add_domain(domain("raw-domain"))
        root = NodeRecord.root("raw-domain", 8, "raw")
        ledger.add_node(root)
        ledger.add_node(NodeRecord.accounting(root, 0, 3, NodeStatus.DECODED, "header", "bytes", "1", 0))
        ledger.add_node(NodeRecord.accounting(root, 3, 2, NodeStatus.PADDING, "padding", "bytes", "1", 0))
        ledger.add_node(NodeRecord.accounting(root, 5, 3, NodeStatus.OPAQUE_PRESERVED, "tail", "bytes", "1", 0))
        proof = ledger.prove_closure("raw-domain", root.node_id)
        self.assertEqual(proof.classified_bytes, 8)
        self.assertEqual(proof.status_bytes["opaque_preserved"], 3)
        self.assertTrue(proof.complete)

    def test_overlap_and_gap_fail_closed(self) -> None:
        ledger = NodeLedger()
        ledger.add_domain(domain("bad-domain"))
        root = NodeRecord.root("bad-domain", 8, "raw")
        ledger.add_node(root)
        ledger.add_node(NodeRecord.accounting(root, 0, 5, NodeStatus.DECODED, "left", "bytes", "1", 0))
        ledger.add_node(NodeRecord.accounting(root, 4, 2, NodeStatus.MALFORMED, "overlap", "bytes", "1", 0))
        with self.assertRaisesRegex(ClosureError, "overlap"):
            ledger.prove_closure("bad-domain", root.node_id)

    def test_parent_must_be_in_the_same_byte_domain(self) -> None:
        ledger = NodeLedger()
        ledger.add_domain(domain("a"))
        ledger.add_domain(domain("b"))
        root = NodeRecord.root("a", 8, "raw")
        ledger.add_node(root)
        foreign = NodeRecord(
            node_id="foreign",
            byte_domain_id="b",
            parent_node_id=root.node_id,
            offset=0,
            length=8,
            status=NodeStatus.DECODED,
            node_kind="illegal",
            decoder_id="bytes",
            decoder_version="1",
            occurrence_index=0,
            accounting=True,
            semantic_hypothesis=None,
            confidence=None,
            consumed_by=(),
        )
        with self.assertRaisesRegex(ValueError, "same ByteDomain"):
            ledger.add_node(foreign)
```

- [ ] **Step 2: Run the tests to verify the modules are absent**

Run: `uv run python -m unittest tests.test_deep_mine_node_ledger -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.ledger`.

- [ ] **Step 3: Implement immutable ByteDomain and NodeRecord values**

```python
# ai_caddie/research/deep_mine/models.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef


class NodeStatus(StrEnum):
    DECODED = "decoded"
    OPAQUE_PRESERVED = "opaque_preserved"
    PADDING = "padding"
    MALFORMED = "malformed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class ByteDomain:
    domain_id: str
    cas_ref: CASRef
    parent_domain_id: str | None
    transform_id: str | None

    @classmethod
    def create(
        cls,
        cas_ref: CASRef,
        *,
        parent_domain_id: str | None,
        transform_id: str | None,
    ) -> "ByteDomain":
        payload = {
            "casRef": {
                "storageDomainId": cas_ref.storage_domain_id,
                "byteDomain": cas_ref.byte_domain,
                "sha256": cas_ref.sha256,
                "size": cas_ref.size,
            },
            "parentDomainId": parent_domain_id,
            "transformId": transform_id,
        }
        return cls(
            typed_id("DeepMineByteDomain/v1", payload),
            cas_ref,
            parent_domain_id,
            transform_id,
        )

    @property
    def size(self) -> int:
        return self.cas_ref.size

    def canonical(self) -> dict[str, object]:
        return {
            "domainId": self.domain_id,
            "casRef": {
                "storageDomainId": self.cas_ref.storage_domain_id,
                "byteDomain": self.cas_ref.byte_domain,
                "sha256": self.cas_ref.sha256,
                "size": self.cas_ref.size,
            },
            "parentDomainId": self.parent_domain_id,
            "transformId": self.transform_id,
        }


@dataclass(frozen=True)
class NodeRecord:
    node_id: str
    byte_domain_id: str
    parent_node_id: str | None
    offset: int
    length: int
    status: NodeStatus
    node_kind: str
    decoder_id: str
    decoder_version: str
    occurrence_index: int
    accounting: bool
    semantic_hypothesis: str | None
    confidence: str | None
    consumed_by: tuple[str, ...]

    @staticmethod
    def identity_payload(
        *,
        byte_domain_id: str,
        parent_node_id: str | None,
        offset: int,
        length: int,
        status: NodeStatus,
        node_kind: str,
        decoder_id: str,
        decoder_version: str,
        occurrence_index: int,
        accounting: bool,
        semantic_hypothesis: str | None,
        confidence: str | None,
        consumed_by: tuple[str, ...],
    ) -> dict[str, object]:
        if len(set(consumed_by)) != len(consumed_by):
            raise ValueError("consumedBy contains duplicate set-like values")
        return {
            "byteDomainId": byte_domain_id,
            "parentNodeId": parent_node_id,
            "offset": str(offset),
            "length": str(length),
            "status": status.value,
            "nodeKind": node_kind,
            "decoderId": decoder_id,
            "decoderVersion": decoder_version,
            "occurrenceIndex": occurrence_index,
            "accounting": accounting,
            "semanticHypothesis": semantic_hypothesis,
            "confidence": confidence,
            "consumedBy": sorted(consumed_by),
        }

    @classmethod
    def create(
        cls,
        *,
        byte_domain_id: str,
        parent_node_id: str | None,
        offset: int,
        length: int,
        status: NodeStatus,
        node_kind: str,
        decoder_id: str,
        decoder_version: str,
        occurrence_index: int,
        accounting: bool,
        semantic_hypothesis: str | None,
        confidence: str | None,
        consumed_by: tuple[str, ...],
    ) -> "NodeRecord":
        payload = cls.identity_payload(
            byte_domain_id=byte_domain_id,
            parent_node_id=parent_node_id,
            offset=offset,
            length=length,
            status=status,
            node_kind=node_kind,
            decoder_id=decoder_id,
            decoder_version=decoder_version,
            occurrence_index=occurrence_index,
            accounting=accounting,
            semantic_hypothesis=semantic_hypothesis,
            confidence=confidence,
            consumed_by=consumed_by,
        )
        return cls(
            typed_id("DeepMineNode/v1", payload), byte_domain_id, parent_node_id,
            offset, length, status, node_kind, decoder_id, decoder_version,
            occurrence_index, accounting, semantic_hypothesis, confidence,
            tuple(sorted(consumed_by)),
        )

    @classmethod
    def root(cls, byte_domain_id: str, size: int, node_kind: str) -> "NodeRecord":
        return cls.create(
            byte_domain_id=byte_domain_id, parent_node_id=None, offset=0, length=size,
            status=NodeStatus.DECODED, node_kind=node_kind, decoder_id="root",
            decoder_version="1", occurrence_index=0, accounting=False,
            semantic_hypothesis=None, confidence=None, consumed_by=(),
        )

    @classmethod
    def accounting(
        cls,
        parent: "NodeRecord",
        offset: int,
        length: int,
        status: NodeStatus,
        node_kind: str,
        decoder_id: str,
        decoder_version: str,
        occurrence_index: int,
    ) -> "NodeRecord":
        return cls.create(
            byte_domain_id=parent.byte_domain_id, parent_node_id=parent.node_id,
            offset=offset, length=length, status=status, node_kind=node_kind,
            decoder_id=decoder_id, decoder_version=decoder_version,
            occurrence_index=occurrence_index, accounting=True,
            semantic_hypothesis=None, confidence=None, consumed_by=(),
        )

    def canonical(self) -> dict[str, object]:
        return {
            "nodeId": self.node_id,
            "byteDomainId": self.byte_domain_id,
            "parentNodeId": self.parent_node_id,
            "offset": str(self.offset),
            "length": str(self.length),
            "status": self.status.value,
            "nodeKind": self.node_kind,
            "decoderId": self.decoder_id,
            "decoderVersion": self.decoder_version,
            "occurrenceIndex": self.occurrence_index,
            "accounting": self.accounting,
            "semanticHypothesis": self.semantic_hypothesis,
            "confidence": self.confidence,
            "consumedBy": sorted(self.consumed_by),
        }
```

- [ ] **Step 4: Implement the ledger and closure verifier**

```python
# ai_caddie/research/deep_mine/ledger.py
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from ai_caddie.contracts.typed_ids import typed_id

from .models import ByteDomain, NodeRecord


class ClosureError(ValueError):
    pass


@dataclass(frozen=True)
class ClosureProof:
    proof_id: str
    byte_domain_id: str
    root_node_id: str
    domain_size: int
    classified_bytes: int
    status_bytes: dict[str, int]
    complete: bool

    def canonical(self) -> dict[str, object]:
        return {
            "proofId": self.proof_id,
            "byteDomainId": self.byte_domain_id,
            "rootNodeId": self.root_node_id,
            "domainSize": str(self.domain_size),
            "classifiedBytes": str(self.classified_bytes),
            "statusBytes": dict(sorted(self.status_bytes.items())),
            "complete": self.complete,
        }


class NodeLedger:
    def __init__(self) -> None:
        self.domains: dict[str, ByteDomain] = {}
        self.nodes: dict[str, NodeRecord] = {}

    def add_domain(self, domain: ByteDomain) -> None:
        existing = self.domains.get(domain.domain_id)
        if existing is not None and existing != domain:
            raise ValueError("ByteDomain identity collision")
        self.domains[domain.domain_id] = domain

    def add_node(self, node: NodeRecord) -> None:
        domain = self.domains.get(node.byte_domain_id)
        if domain is None:
            raise ValueError("unknown ByteDomain")
        if node.offset < 0 or node.length < 0 or node.offset + node.length > domain.size:
            raise ValueError("node range leaves ByteDomain")
        if node.parent_node_id is not None:
            parent = self.nodes.get(node.parent_node_id)
            if parent is None:
                raise ValueError("unknown parent node")
            if parent.byte_domain_id != node.byte_domain_id:
                raise ValueError("parent and child must use the same ByteDomain")
            if node.offset < parent.offset or node.offset + node.length > parent.offset + parent.length:
                raise ValueError("child range leaves parent node")
        existing = self.nodes.get(node.node_id)
        if existing is not None and existing != node:
            raise ValueError("node identity collision")
        self.nodes[node.node_id] = node

    def direct_accounting_children(self, root_node_id: str) -> list[NodeRecord]:
        return sorted(
            (node for node in self.nodes.values() if node.parent_node_id == root_node_id and node.accounting),
            key=lambda node: (node.offset, node.length, node.node_id),
        )

    def prove_closure(self, byte_domain_id: str, root_node_id: str) -> ClosureProof:
        domain = self.domains[byte_domain_id]
        root = self.nodes[root_node_id]
        if root.byte_domain_id != byte_domain_id or root.offset != 0 or root.length != domain.size:
            raise ClosureError("root node does not cover ByteDomain")
        cursor = 0
        status_bytes: dict[str, int] = defaultdict(int)
        for child in self.direct_accounting_children(root_node_id):
            if child.offset < cursor:
                raise ClosureError(f"overlap at offset {child.offset}")
            if child.offset > cursor:
                raise ClosureError(f"gap [{cursor}, {child.offset})")
            cursor = child.offset + child.length
            status_bytes[child.status.value] += child.length
        if cursor != domain.size:
            raise ClosureError(f"gap [{cursor}, {domain.size})")
        complete = cursor == domain.size
        payload = {
            "byteDomainId": byte_domain_id,
            "rootNodeId": root_node_id,
            "domainSize": str(domain.size),
            "classifiedBytes": str(cursor),
            "statusBytes": dict(sorted(status_bytes.items())),
            "complete": complete,
        }
        return ClosureProof(
            typed_id("DeepMineClosureProof/v1", payload), byte_domain_id, root_node_id,
            domain.size, cursor, dict(sorted(status_bytes.items())), complete,
        )
```

- [ ] **Step 5: Register types and run tests**

Verify the exact C1 registry entries for `DeepMineByteDomain/v1`, `DeepMineNode/v1`, and `DeepMineClosureProof/v1`; offsets and lengths are unsigned decimal strings in canonical persisted records even though Python uses integers internally.

Run: `uv run python -m unittest tests.test_deep_mine_node_ledger tests.test_canonical_contract_ids -v`

Expected: all tests PASS; overlap, gap, out-of-range, and cross-domain parenting fail closed.

- [ ] **Step 6: Commit C2**

```bash
git add ai_caddie/research/deep_mine/models.py ai_caddie/research/deep_mine/ledger.py tests/test_deep_mine_node_ledger.py
git commit -m "feat(research): prove byte-domain closure"
```

### Task 3: C3 — Add Lossless IR and derived transform provenance

**Files:**
- Create: `ai_caddie/research/deep_mine/ir.py`
- Create: `ai_caddie/research/deep_mine/provenance.py`
- Create: `tests/test_deep_mine_lossless_ir.py`

- [ ] **Step 1: Write failing exact-reassembly and transform-DAG tests**

```python
# tests/test_deep_mine_lossless_ir.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.ir import IRAtom, LosslessIR
from ai_caddie.research.deep_mine.provenance import persist_lossless_ir, put_derived


class LosslessIRTests(unittest.TestCase):
    def test_accounting_atoms_reassemble_exact_source_bytes(self) -> None:
        source = b'{"a":1,"a":2}'
        ir = LosslessIR((
            IRAtom("json-token", "json-domain", 0, 6, 0, True, "node-1"),
            IRAtom("json-token", "json-domain", 6, len(source) - 6, 1, True, "node-2"),
        ))
        self.assertEqual(ir.reassemble("json-domain", lambda _: source), source)

    def test_cross_domain_atoms_cannot_be_reassembled_together(self) -> None:
        ir = LosslessIR((
            IRAtom("raw", "raw-domain", 0, 2, 0, True, "n1"),
            IRAtom("member", "member-domain", 2, 2, 0, True, "n2"),
        ))
        with self.assertRaisesRegex(ValueError, "one ByteDomain"):
            ir.reassemble("raw-domain", lambda _: b"abcd")

    def test_derived_artifact_records_parent_refs_and_transform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            parent = cas.put_bytes("account-a", "raw-entity", b"compressed")
            derived = put_derived(
                cas=cas,
                storage_domain_id="account-a",
                byte_domain="archive-member",
                data=b"plain",
                parent_refs=(parent,),
                transform_name="zip-deflate",
                transform_version="stdlib-3.12",
                parameters={"memberOccurrence": 0},
                build_hash="decoder-build-1",
            )
            self.assertEqual(derived.ref.byte_domain, "archive-member")
            self.assertEqual(derived.parent_refs, (parent,))
            self.assertEqual(cas.read_bytes("account-a", derived.ref), b"plain")

    def test_lossless_ir_is_persisted_as_a_parent_bound_derived_cas_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            parent = cas.put_bytes("account-a", "raw-entity", b"abc")
            ir = LosslessIR((IRAtom("raw", "raw-domain", 0, 3, 0, True, "node-1"),))
            artifact = persist_lossless_ir(
                ir, cas=cas, storage_domain_id="account-a", parent_refs=(parent,),
                decoder_version="lossless-ir-v1", build_hash="ir-build-1",
            )
            self.assertEqual(artifact.ref.byte_domain, "deep-mine-lossless-ir")
            self.assertEqual(artifact.parent_refs, (parent,))
            self.assertIn(b'"nodeId":"node-1"', cas.read_bytes("account-a", artifact.ref))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_lossless_ir -v`

Expected: FAIL importing `IRAtom` and `put_derived`.

- [ ] **Step 3: Implement slice-only Lossless IR**

```python
# ai_caddie/research/deep_mine/ir.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class IRAtom:
    kind: str
    byte_domain_id: str
    offset: int
    length: int
    occurrence_index: int
    accounting: bool
    node_id: str

    def canonical(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "byteDomainId": self.byte_domain_id,
            "offset": str(self.offset),
            "length": str(self.length),
            "occurrenceIndex": self.occurrence_index,
            "accounting": self.accounting,
            "nodeId": self.node_id,
        }


@dataclass(frozen=True)
class LosslessIR:
    atoms: tuple[IRAtom, ...]

    def canonical(self) -> dict[str, object]:
        return {"atoms": [atom.canonical() for atom in self.atoms]}

    def reassemble(self, byte_domain_id: str, read_domain: Callable[[str], bytes]) -> bytes:
        accounting = sorted((atom for atom in self.atoms if atom.accounting), key=lambda atom: atom.offset)
        if any(atom.byte_domain_id != byte_domain_id for atom in accounting):
            raise ValueError("Lossless IR reassembly uses one ByteDomain")
        source = read_domain(byte_domain_id)
        cursor = 0
        chunks: list[bytes] = []
        for atom in accounting:
            if atom.offset != cursor:
                raise ValueError(f"Lossless IR gap or overlap at {cursor}")
            end = atom.offset + atom.length
            if end > len(source):
                raise ValueError("Lossless IR atom leaves ByteDomain")
            chunks.append(source[atom.offset:end])
            cursor = end
        if cursor != len(source):
            raise ValueError(f"Lossless IR does not cover trailing range [{cursor}, {len(source)})")
        return b"".join(chunks)
```

- [ ] **Step 4: Implement derived CAS provenance**

```python
# ai_caddie/research/deep_mine/provenance.py
from __future__ import annotations

from dataclasses import dataclass

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS


def _ref(ref: CASRef) -> dict[str, object]:
    return {
        "storageDomainId": ref.storage_domain_id,
        "byteDomain": ref.byte_domain,
        "sha256": ref.sha256,
        "size": ref.size,
    }


@dataclass(frozen=True)
class DerivedArtifact:
    artifact_id: str
    ref: CASRef
    parent_refs: tuple[CASRef, ...]
    transform_name: str
    transform_version: str
    parameters: dict[str, object]
    build_hash: str

    def canonical(self) -> dict[str, object]:
        return {
            "artifactId": self.artifact_id,
            "ref": _ref(self.ref),
            "parentRefs": [_ref(ref) for ref in self.parent_refs],
            "transformName": self.transform_name,
            "transformVersion": self.transform_version,
            "parameters": self.parameters,
            "buildHash": self.build_hash,
        }


def put_derived(
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    byte_domain: str,
    data: bytes,
    parent_refs: tuple[CASRef, ...],
    transform_name: str,
    transform_version: str,
    parameters: dict[str, object],
    build_hash: str,
) -> DerivedArtifact:
    if not parent_refs:
        raise ValueError("derived artifact requires at least one parent")
    ref = cas.put_bytes(storage_domain_id, byte_domain, data)
    payload = {
        "ref": _ref(ref),
        "parentRefs": [_ref(item) for item in parent_refs],
        "transformName": transform_name,
        "transformVersion": transform_version,
        "parameters": parameters,
        "buildHash": build_hash,
    }
    return DerivedArtifact(
        typed_id("DeepMineDerivedArtifact/v1", payload), ref, parent_refs,
        transform_name, transform_version, dict(parameters), build_hash,
    )


def persist_lossless_ir(
    ir: "LosslessIR",
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    parent_refs: tuple[CASRef, ...],
    decoder_version: str,
    build_hash: str,
) -> DerivedArtifact:
    from .ir import LosslessIR

    if not isinstance(ir, LosslessIR):
        raise TypeError("persist_lossless_ir requires LosslessIR")
    return put_derived(
        cas=cas,
        storage_domain_id=storage_domain_id,
        byte_domain="deep-mine-lossless-ir",
        data=canonical_json_bytes(ir.canonical()),
        parent_refs=parent_refs,
        transform_name="lossless-ir",
        transform_version=decoder_version,
        parameters={"atomCount": len(ir.atoms)},
        build_hash=build_hash,
    )
```

- [ ] **Step 5: Register derived/IR objects and run tests**

Verify the exact C1 registry entries for `DeepMineDerivedArtifact/v1` and `DeepMineLosslessIR/v1`; their schema refs must resolve to `deep_mine_v1.schema.json`.

Run: `uv run python -m unittest tests.test_deep_mine_lossless_ir tests.test_deep_mine_node_ledger -v`

Expected: all tests PASS; reassembly is byte-exact; cross-domain offsets fail; Lossless IR bytes use the shared CAS with explicit parents; every derived artifact has at least one parent.

- [ ] **Step 6: Commit C3**

```bash
git add ai_caddie/research/deep_mine/ir.py ai_caddie/research/deep_mine/provenance.py tests/test_deep_mine_lossless_ir.py
git commit -m "feat(research): preserve lossless ir with transform provenance"
```

### Task 4: C4 — Add parser registry, decoder-set identity, and hard budgets

**Files:**
- Create: `ai_caddie/research/deep_mine/budget.py`
- Create: `ai_caddie/research/deep_mine/parser_registry.py`
- Create: `tests/test_deep_mine_parser_registry.py`

- [ ] **Step 1: Write failing unique-selection and budget tests**

```python
# tests/test_deep_mine_parser_registry.py
from __future__ import annotations

import unittest

from ai_caddie.research.deep_mine.budget import BudgetExceeded, BudgetMeter, ParserBudget
from ai_caddie.research.deep_mine.parser_registry import ParserDescriptor, ParserRegistry, ParserSelectionKey


def decoder(_: object) -> object:
    return {"decoded": True}


class ParserRegistryTests(unittest.TestCase):
    def test_selects_exactly_one_compatible_decoder(self) -> None:
        registry = ParserRegistry()
        registry.register(ParserDescriptor(
            decoder_id="garmin-release-wire",
            decoder_version="1.0.0",
            build_hash="build-a",
            provider="garmin",
            source_type="course-layout-release",
            format_families=("protobuf-wire",),
            magic_prefix=b"",
            media_types=("application/x-protobuf",),
            schema_family="garmin-course-layout",
            min_version=1,
            max_version=2,
            ir_schema="protobuf-occurrence/v1",
        ), decoder)
        selected = registry.select(ParserSelectionKey(
            "garmin", "course-layout-release", "protobuf-wire", b"\x08\x01", "application/x-protobuf",
            "garmin-course-layout", 1,
        ))
        self.assertEqual(selected.descriptor.decoder_id, "garmin-release-wire")
        self.assertEqual(len(registry.decoder_set_id), 64)

    def test_ambiguous_and_unknown_versions_fail_closed(self) -> None:
        descriptor = ParserDescriptor("d", "1", "hash", "garmin", "asset", ("opaque",), b"", ("application/octet-stream",), "x", 1, 1, "ir/v1")
        registry = ParserRegistry()
        registry.register(descriptor, decoder)
        registry.register(ParserDescriptor("d2", "1", "hash2", "garmin", "asset", ("opaque",), b"", ("application/octet-stream",), "x", 1, 1, "ir/v1"), decoder)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            registry.select(ParserSelectionKey("garmin", "asset", "opaque", b"body", "application/octet-stream", "x", 1))
        with self.assertRaisesRegex(LookupError, "no authoritative decoder"):
            ParserRegistry().select(ParserSelectionKey("garmin", "asset", "opaque", b"body", "application/octet-stream", "x", 9))

    def test_budget_meter_stops_bytes_nodes_depth_and_output(self) -> None:
        meter = BudgetMeter(ParserBudget(max_input_bytes=4, max_nodes=2, max_depth=1, max_output_bytes=3))
        meter.consume_input(4)
        meter.add_node(); meter.add_node()
        meter.enter_depth(); meter.leave_depth()
        meter.add_output(3)
        with self.assertRaises(BudgetExceeded):
            meter.add_node()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_parser_registry -v`

Expected: FAIL importing `ParserRegistry` and `BudgetMeter`.

- [ ] **Step 3: Implement deterministic budgets**

```python
# ai_caddie/research/deep_mine/budget.py
from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ParserBudget:
    max_input_bytes: int
    max_nodes: int
    max_depth: int
    max_output_bytes: int


class BudgetMeter:
    def __init__(self, budget: ParserBudget) -> None:
        self.budget = budget
        self.input_bytes = 0
        self.nodes = 0
        self.depth = 0
        self.output_bytes = 0

    def consume_input(self, count: int) -> None:
        self.input_bytes += count
        if self.input_bytes > self.budget.max_input_bytes:
            raise BudgetExceeded("input byte budget exhausted")

    def add_node(self, count: int = 1) -> None:
        self.nodes += count
        if self.nodes > self.budget.max_nodes:
            raise BudgetExceeded("node budget exhausted")

    def enter_depth(self) -> None:
        self.depth += 1
        if self.depth > self.budget.max_depth:
            raise BudgetExceeded("depth budget exhausted")

    def leave_depth(self) -> None:
        if self.depth <= 0:
            raise ValueError("depth meter underflow")
        self.depth -= 1

    def add_output(self, count: int) -> None:
        self.output_bytes += count
        if self.output_bytes > self.budget.max_output_bytes:
            raise BudgetExceeded("output byte budget exhausted")
```

- [ ] **Step 4: Implement the registry and decoder-set hash**

```python
# ai_caddie/research/deep_mine/parser_registry.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

from ai_caddie.contracts.canonical_json import canonical_json_bytes


Decoder = Callable[[object], object]


@dataclass(frozen=True)
class ParserSelectionKey:
    provider: str
    source_type: str
    format_family: str
    prefix: bytes
    media_type: str
    schema_family: str
    version: int


@dataclass(frozen=True)
class ParserDescriptor:
    decoder_id: str
    decoder_version: str
    build_hash: str
    provider: str
    source_type: str
    format_families: tuple[str, ...]
    magic_prefix: bytes
    media_types: tuple[str, ...]
    schema_family: str
    min_version: int
    max_version: int
    ir_schema: str

    def matches(self, key: ParserSelectionKey) -> bool:
        return (
            self.provider == key.provider
            and self.source_type == key.source_type
            and key.format_family in self.format_families
            and key.prefix.startswith(self.magic_prefix)
            and key.media_type in self.media_types
            and self.schema_family == key.schema_family
            and self.min_version <= key.version <= self.max_version
        )

    def canonical(self) -> dict[str, object]:
        return {
            "decoderId": self.decoder_id,
            "decoderVersion": self.decoder_version,
            "buildHash": self.build_hash,
            "provider": self.provider,
            "sourceType": self.source_type,
            "formatFamilies": list(self.format_families),
            "magicPrefixHex": self.magic_prefix.hex(),
            "mediaTypes": list(self.media_types),
            "schemaFamily": self.schema_family,
            "minVersion": self.min_version,
            "maxVersion": self.max_version,
            "irSchema": self.ir_schema,
        }


@dataclass(frozen=True)
class RegisteredParser:
    descriptor: ParserDescriptor
    decoder: Decoder


class ParserRegistry:
    def __init__(self) -> None:
        self._registered: list[RegisteredParser] = []

    def register(self, descriptor: ParserDescriptor, decoder: Decoder) -> None:
        self._registered.append(RegisteredParser(descriptor, decoder))

    def select(self, key: ParserSelectionKey) -> RegisteredParser:
        matches = [item for item in self._registered if item.descriptor.matches(key)]
        if not matches:
            raise LookupError("no authoritative decoder")
        if len(matches) != 1:
            raise ValueError("ambiguous authoritative decoder")
        return matches[0]

    @property
    def decoder_set_id(self) -> str:
        payload = [item.descriptor.canonical() for item in sorted(self._registered, key=lambda item: item.descriptor.decoder_id)]
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
```

- [ ] **Step 5: Run tests**

Run: `uv run python -m unittest tests.test_deep_mine_parser_registry tests.test_deep_mine_corpus -v`

Expected: all tests PASS; unknown versions and ambiguous matches fail closed; decoder-set identity changes when any decoder build hash changes.

- [ ] **Step 6: Commit C4**

```bash
git add ai_caddie/research/deep_mine/budget.py ai_caddie/research/deep_mine/parser_registry.py tests/test_deep_mine_parser_registry.py
git commit -m "feat(research): register bounded authoritative decoders"
```

### Task 5: C5 — Persist every unknown in a stable Unknown Registry

**Files:**
- Create: `ai_caddie/research/deep_mine/unknowns.py`
- Create: `tests/test_deep_mine_unknown_registry.py`

- [ ] **Step 1: Write failing stable-ID and evidence-lifecycle tests**

```python
# tests/test_deep_mine_unknown_registry.py
from __future__ import annotations

import unittest

from ai_caddie.research.deep_mine.unknowns import (
    UnknownEvidence,
    UnknownRegistry,
    UnknownStatus,
)


class UnknownRegistryTests(unittest.TestCase):
    def test_unknown_id_is_stable_across_samples_and_ranges_are_preserved(self) -> None:
        registry = UnknownRegistry()
        first = registry.observe(
            namespace="protobuf",
            locator="date_layout/f12/wire2",
            observed_at="2026-07-18T10:00:00.000Z",
            evidence=UnknownEvidence("raw-a", "domain-a", 10, 4, "length=4", ("f7",)),
            priority="high",
        )
        second = registry.observe(
            namespace="protobuf",
            locator="date_layout/f12/wire2",
            observed_at="2026-07-18T11:00:00.000Z",
            evidence=UnknownEvidence("raw-b", "domain-b", 20, 7, "length=7", ("f7", "f9")),
            priority="high",
        )
        self.assertEqual(first.unknown_id, second.unknown_id)
        self.assertEqual(second.first_observed_at, "2026-07-18T10:00:00.000Z")
        self.assertEqual(second.last_observed_at, "2026-07-18T11:00:00.000Z")
        self.assertEqual(len(second.evidence), 2)

    def test_hypothesis_and_counterevidence_do_not_delete_the_unknown(self) -> None:
        registry = UnknownRegistry()
        record = registry.observe(
            namespace="draco",
            locator="CliffUV2/attr_uid_3",
            observed_at="2026-07-18T10:00:00.000Z",
            evidence=UnknownEvidence("raw-a", "domain-a", 0, 99, "color3", ()),
            priority="medium",
        )
        hypothesized = registry.update_status(
            record.unknown_id,
            UnknownStatus.HYPOTHESIS,
            hypothesis="secondary UV mask",
            counterevidence="semantic is COLOR rather than TEX_COORD",
            next_minimum_evidence="render positive and negative UV controls",
            capture_required=False,
        )
        self.assertEqual(hypothesized.status, UnknownStatus.HYPOTHESIS)
        self.assertIn("COLOR", hypothesized.counterevidence)
        self.assertEqual(len(registry.records()), 1)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_unknown_registry -v`

Expected: FAIL importing `UnknownRegistry`.

- [ ] **Step 3: Implement stable records and append-only evidence updates**

```python
# ai_caddie/research/deep_mine/unknowns.py
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from ai_caddie.contracts.typed_ids import typed_id


class UnknownStatus(StrEnum):
    OBSERVED = "observed"
    HYPOTHESIS = "hypothesis"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass(frozen=True, order=True)
class UnknownEvidence:
    raw_sha256: str
    byte_domain_id: str
    offset: int
    length: int
    morphology: str
    cooccurs_with: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "rawSha256": self.raw_sha256,
            "byteDomainId": self.byte_domain_id,
            "offset": str(self.offset),
            "length": str(self.length),
            "morphology": self.morphology,
            "cooccursWith": list(self.cooccurs_with),
        }


@dataclass(frozen=True)
class UnknownRecord:
    unknown_id: str
    namespace: str
    locator: str
    first_observed_at: str
    last_observed_at: str
    evidence: tuple[UnknownEvidence, ...]
    status: UnknownStatus
    priority: str
    hypothesis: str | None
    counterevidence: str | None
    next_minimum_evidence: str | None
    capture_required: bool

    def canonical(self) -> dict[str, object]:
        return {
            "unknownId": self.unknown_id,
            "namespace": self.namespace,
            "locator": self.locator,
            "firstObservedAt": self.first_observed_at,
            "lastObservedAt": self.last_observed_at,
            "evidence": [item.canonical() for item in self.evidence],
            "status": self.status.value,
            "priority": self.priority,
            "hypothesis": self.hypothesis,
            "counterevidence": self.counterevidence,
            "nextMinimumEvidence": self.next_minimum_evidence,
            "captureRequired": self.capture_required,
        }


class UnknownRegistry:
    def __init__(self) -> None:
        self._records: dict[str, UnknownRecord] = {}

    @staticmethod
    def stable_id(namespace: str, locator: str) -> str:
        return typed_id("DeepMineUnknown/v1", {"namespace": namespace, "locator": locator})

    def observe(
        self,
        *,
        namespace: str,
        locator: str,
        observed_at: str,
        evidence: UnknownEvidence,
        priority: str,
    ) -> UnknownRecord:
        unknown_id = self.stable_id(namespace, locator)
        current = self._records.get(unknown_id)
        if current is None:
            record = UnknownRecord(
                unknown_id, namespace, locator, observed_at, observed_at, (evidence,),
                UnknownStatus.OBSERVED, priority, None, None, None, False,
            )
        else:
            evidence_rows = tuple(sorted(set((*current.evidence, evidence))))
            record = replace(
                current,
                first_observed_at=min(current.first_observed_at, observed_at),
                last_observed_at=max(current.last_observed_at, observed_at),
                evidence=evidence_rows,
                priority=priority if priority == "high" else current.priority,
            )
        self._records[unknown_id] = record
        return record

    def update_status(
        self,
        unknown_id: str,
        status: UnknownStatus,
        *,
        hypothesis: str | None,
        counterevidence: str | None,
        next_minimum_evidence: str | None,
        capture_required: bool,
    ) -> UnknownRecord:
        current = self._records[unknown_id]
        record = replace(
            current,
            status=status,
            hypothesis=hypothesis,
            counterevidence=counterevidence,
            next_minimum_evidence=next_minimum_evidence,
            capture_required=capture_required,
        )
        self._records[unknown_id] = record
        return record

    def get(self, unknown_id: str) -> UnknownRecord:
        return self._records[unknown_id]

    def records(self) -> tuple[UnknownRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.unknown_id))
```

- [ ] **Step 4: Register the canonical object and run tests**

Verify C1's exact `DeepMineUnknown/v1` registry entry. Stable identity includes only `namespace + locator`; observation time, sample hash, hypothesis, and mutable research status are explicitly excluded registry state and must not change the ID.

Run: `uv run python -m unittest tests.test_deep_mine_unknown_registry tests.test_deep_mine_node_ledger -v`

Expected: all tests PASS; multiple samples merge under one stable ID and no update removes prior range evidence.

- [ ] **Step 5: Commit C5**

```bash
git add ai_caddie/research/deep_mine/unknowns.py tests/test_deep_mine_unknown_registry.py
git commit -m "feat(research): persist stable unknown evidence"
```

### Task 6: C6 — Upgrade the shared protobuf walker and emit lossless protobuf inventory

**Files:**
- Modify: `ai_caddie/course_data/providers/protobuf_wire.py`
- Create: `ai_caddie/research/deep_mine/parsers/__init__.py`
- Create: `ai_caddie/research/deep_mine/parsers/protobuf.py`
- Create: `tests/test_deep_mine_protobuf_inventory.py`

- [ ] **Step 1: Write failing wire 0–5, group, packed-candidate, and malformed-range tests**

```python
# tests/test_deep_mine_protobuf_inventory.py
from __future__ import annotations

import unittest

from ai_caddie.course_data.cas import CASRef
from ai_caddie.course_data.providers.protobuf_wire import WireDecodeError, walk_occurrences
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.protobuf import inventory_protobuf
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry


class ProtobufInventoryTests(unittest.TestCase):
    def test_walks_all_wire_types_groups_and_duplicate_occurrences(self) -> None:
        payload = (
            b"\x08\x96\x01"                      # f1 wire0 = 150
            b"\x11abcdefgh"                       # f2 wire1
            b"\x1a\x03\x01\x02\x03"             # f3 wire2, packed varint candidate
            b"\x23\x28\x07\x24"                 # f4 start-group, f5=7, f4 end-group
            b"\x35WXYZ"                           # f6 wire5
            b"\x08\x01"                          # second f1 occurrence
        )
        rows = walk_occurrences(payload)
        self.assertEqual([row.wire_type for row in rows], [0, 1, 2, 3, 5, 0])
        self.assertEqual(rows[0].occurrence_index, 0)
        self.assertEqual(rows[-1].occurrence_index, 1)
        self.assertEqual(rows[2].packed_varints, (1, 2, 3))
        self.assertEqual(rows[3].group_children[0].field_number, 5)
        self.assertEqual(b"".join(row.raw_field for row in rows), payload)

    def test_truncated_varint_reports_exact_offset(self) -> None:
        with self.assertRaises(WireDecodeError) as caught:
            walk_occurrences(b"\x08\x80")
        self.assertEqual(caught.exception.offset, 1)

    def test_inventory_accounts_all_bytes_and_registers_unknown_occurrences(self) -> None:
        payload = b"\x08\x01\x12\x03abc\x08\x02"
        ref = CASRef("account-a", "raw-entity", "b" * 64, len(payload))
        domain = ByteDomain("pb-domain", ref, None, None)
        ledger = NodeLedger(); ledger.add_domain(domain)
        root = NodeRecord.root(domain.domain_id, domain.size, "protobuf")
        ledger.add_node(root)
        unknowns = UnknownRegistry()
        result = inventory_protobuf(
            data=payload,
            domain=domain,
            root=root,
            ledger=ledger,
            unknowns=unknowns,
            observed_at="2026-07-18T10:00:00.000Z",
            schema_name="release",
            known_fields={1},
            decoder_id="protobuf-wire",
            decoder_version="1",
        )
        self.assertEqual(result.ir.reassemble("pb-domain", lambda _: payload), payload)
        self.assertTrue(ledger.prove_closure("pb-domain", root.node_id).complete)
        self.assertEqual(len(unknowns.records()), 1)
        self.assertIn("release/f2/wire2/occ0", unknowns.records()[0].locator)
```

- [ ] **Step 2: Run the tests and verify Plan 2's walker is insufficient**

Run: `uv run python -m unittest tests.test_deep_mine_protobuf_inventory -v`

Expected: FAIL because Plan 2's `WireOccurrence` lacks offsets/groups/packed candidates and rejects wire types 3/4.

- [ ] **Step 3: Replace the shared walker with a backward-compatible bounded implementation**

```python
# ai_caddie/course_data/providers/protobuf_wire.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


class WireDecodeError(ValueError):
    def __init__(self, message: str, offset: int) -> None:
        super().__init__(f"{message} at offset {offset}")
        self.offset = offset


@dataclass(frozen=True)
class WireOccurrence:
    field_number: int
    wire_type: int
    raw_field: bytes
    value_bytes: bytes | None
    int_value: int | None
    start: int
    end: int
    occurrence_index: int
    packed_varints: tuple[int, ...] | None
    group_children: tuple["WireOccurrence", ...]


def _varint(data: bytes, offset: int, end: int) -> tuple[int, int]:
    value = 0
    position = offset
    for shift in range(0, 70, 7):
        if position >= end:
            raise WireDecodeError("truncated protobuf varint", position)
        byte = data[position]
        position += 1
        if shift == 63 and byte > 1:
            raise WireDecodeError("protobuf varint exceeds uint64", position - 1)
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, position
    raise WireDecodeError("protobuf varint exceeds ten bytes", position)


def _packed_candidate(data: bytes) -> tuple[int, ...] | None:
    if not data:
        return ()
    values: list[int] = []
    position = 0
    try:
        while position < len(data):
            value, position = _varint(data, position, len(data))
            values.append(value)
    except WireDecodeError:
        return None
    return tuple(values)


def _walk(
    data: bytes,
    position: int,
    end: int,
    *,
    stop_group: int | None,
) -> tuple[list[WireOccurrence], int]:
    rows: list[WireOccurrence] = []
    counts: dict[int, int] = defaultdict(int)
    while position < end:
        start = position
        key, position = _varint(data, position, end)
        field_number, wire_type = key >> 3, key & 7
        if field_number <= 0:
            raise WireDecodeError("protobuf field number must be positive", start)
        if wire_type == 4:
            if stop_group != field_number:
                raise WireDecodeError("unexpected protobuf end-group", start)
            return rows, position
        occurrence_index = counts[field_number]
        counts[field_number] += 1
        value_bytes: bytes | None = None
        int_value: int | None = None
        packed_varints: tuple[int, ...] | None = None
        children: tuple[WireOccurrence, ...] = ()
        if wire_type == 0:
            int_value, position = _varint(data, position, end)
        elif wire_type == 1:
            fixed_end = position + 8
            if fixed_end > end:
                raise WireDecodeError("truncated fixed64", position)
            value_bytes = data[position:fixed_end]
            position = fixed_end
        elif wire_type == 2:
            length, position = _varint(data, position, end)
            value_end = position + length
            if value_end > end:
                raise WireDecodeError("truncated length-delimited field", position)
            value_bytes = data[position:value_end]
            packed_varints = _packed_candidate(value_bytes)
            position = value_end
        elif wire_type == 3:
            nested, position = _walk(data, position, end, stop_group=field_number)
            children = tuple(nested)
        elif wire_type == 5:
            fixed_end = position + 4
            if fixed_end > end:
                raise WireDecodeError("truncated fixed32", position)
            value_bytes = data[position:fixed_end]
            position = fixed_end
        else:
            raise WireDecodeError(f"unsupported protobuf wire type {wire_type}", start)
        rows.append(WireOccurrence(
            field_number, wire_type, data[start:position], value_bytes, int_value,
            start, position, occurrence_index, packed_varints, children,
        ))
    if stop_group is not None:
        raise WireDecodeError("unterminated protobuf group", position)
    return rows, position


def walk_occurrences(data: bytes) -> tuple[WireOccurrence, ...]:
    rows, position = _walk(data, 0, len(data), stop_group=None)
    if position != len(data):
        raise WireDecodeError("protobuf walker stopped early", position)
    return tuple(rows)
```

This retains Plan 2's existing `field_number`, `wire_type`, `raw_field`, `value_bytes`, and `int_value` attributes, so `GarminCourseAdapter` remains source-compatible.

- [ ] **Step 4: Implement Node Ledger and Unknown Registry projection**

```python
# ai_caddie/research/deep_mine/parsers/__init__.py
"""Occurrence-preserving research parsers; no product projection belongs here."""
```

```python
# ai_caddie/research/deep_mine/parsers/protobuf.py
from __future__ import annotations

from dataclasses import dataclass

from ai_caddie.course_data.providers.protobuf_wire import WireDecodeError, walk_occurrences

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..unknowns import UnknownEvidence, UnknownRegistry


@dataclass(frozen=True)
class ProtobufInventory:
    ir: LosslessIR
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def inventory_protobuf(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    observed_at: str,
    schema_name: str,
    known_fields: set[int],
    decoder_id: str,
    decoder_version: str,
) -> ProtobufInventory:
    atoms: list[IRAtom] = []
    structural: list[str] = []
    numeric: list[float] = []
    try:
        rows = walk_occurrences(data)
        for row in rows:
            node = NodeRecord.accounting(
                root, row.start, row.end - row.start, NodeStatus.DECODED,
                f"protobuf-field:{row.field_number}:wire{row.wire_type}",
                decoder_id, decoder_version, row.occurrence_index,
            )
            ledger.add_node(node)
            atoms.append(IRAtom("protobuf-field", domain.domain_id, row.start, row.end - row.start, row.occurrence_index, True, node.node_id))
            structural.append(f"f{row.field_number}/wire{row.wire_type}/occ{row.occurrence_index}")
            if row.int_value is not None:
                numeric.append(float(row.int_value))
            if row.field_number not in known_fields:
                unknowns.observe(
                    namespace="protobuf",
                    locator=f"{schema_name}/f{row.field_number}/wire{row.wire_type}/occ{row.occurrence_index}",
                    observed_at=observed_at,
                    evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, row.start, row.end - row.start, f"wire={row.wire_type}", ()),
                    priority="medium",
                )
        return ProtobufInventory(LosslessIR(tuple(atoms)), tuple(structural), tuple(numeric), None)
    except WireDecodeError as exc:
        offset = min(exc.offset, len(data))
        if offset:
            prefix = NodeRecord.accounting(root, 0, offset, NodeStatus.DECODED, "protobuf-prefix", decoder_id, decoder_version, 0)
            ledger.add_node(prefix)
            atoms.append(IRAtom("protobuf-prefix", domain.domain_id, 0, offset, 0, True, prefix.node_id))
        if offset < len(data):
            remainder = NodeRecord.accounting(root, offset, len(data) - offset, NodeStatus.MALFORMED, "protobuf-remainder", decoder_id, decoder_version, 0)
            ledger.add_node(remainder)
            atoms.append(IRAtom("protobuf-remainder", domain.domain_id, offset, len(data) - offset, 0, True, remainder.node_id))
            unknowns.observe(
                namespace="protobuf",
                locator=f"{schema_name}/malformed@{offset}",
                observed_at=observed_at,
                evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, offset, len(data) - offset, str(exc), ()),
                priority="high",
            )
        return ProtobufInventory(LosslessIR(tuple(atoms)), tuple(structural), tuple(numeric), str(exc))
```

- [ ] **Step 5: Run new and legacy protobuf tests**

Run:

```bash
uv run python -m unittest \
  tests.test_deep_mine_protobuf_inventory \
  tests.test_garmin_course_adapter \
  tests.test_course_search \
  tests.test_courseview_par \
  tests.test_geometry_date_fallback -v
```

Expected: all tests PASS; legacy projectors still read the shared fields; every top-level occurrence preserves its exact raw range; malformed remainder is registered rather than dropped.

- [ ] **Step 6: Commit C6**

```bash
git add ai_caddie/course_data/providers/protobuf_wire.py ai_caddie/research/deep_mine/parsers/__init__.py ai_caddie/research/deep_mine/parsers/protobuf.py tests/test_deep_mine_protobuf_inventory.py
git commit -m "feat(research): inventory every protobuf occurrence"
```

### Task 7: C7 — Add duplicate-key-aware lossless JSON inventory

**Files:**
- Create: `ai_caddie/research/deep_mine/parsers/json_occurrence.py`
- Create: `tests/test_deep_mine_json_inventory.py`

- [ ] **Step 1: Write failing duplicate-key, number-lexeme, null, order, and malformed tests**

```python
# tests/test_deep_mine_json_inventory.py
from __future__ import annotations

import unittest

from ai_caddie.course_data.cas import CASRef
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.json_occurrence import inventory_json, tokenize_json
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry


class JSONInventoryTests(unittest.TestCase):
    def test_preserves_duplicate_keys_order_raw_numbers_null_and_whitespace(self) -> None:
        payload = b'{ "a":1.2300, "a":null, "nested":{"b":-2e3}, "huge":1e400, "negativeZero":-0 }\n'
        tokens = tokenize_json(payload)
        self.assertIn(b"1.2300", [token.raw for token in tokens])
        self.assertIn(b"null", [token.raw for token in tokens])
        ref = CASRef("account-a", "archive-member", "c" * 64, len(payload))
        domain = ByteDomain("json-domain", ref, "zip-domain", "unzip-transform")
        ledger = NodeLedger(); ledger.add_domain(domain)
        root = NodeRecord.root(domain.domain_id, domain.size, "json")
        ledger.add_node(root)
        unknowns = UnknownRegistry()
        result = inventory_json(
            data=payload,
            domain=domain,
            root=root,
            ledger=ledger,
            unknowns=unknowns,
            observed_at="2026-07-18T10:00:00.000Z",
            schema_name="hole-json",
            known_paths={"$", "$.a", "$.nested", "$.nested.b", "$.huge", "$.negativeZero"},
            decoder_id="json-occurrence",
            decoder_version="1",
        )
        self.assertEqual([row.key for row in result.keys if row.path == "$.a"], ["a", "a"])
        self.assertEqual([row.occurrence_index for row in result.keys if row.path == "$.a"], [0, 1])
        self.assertIn("1e400", result.numeric_values)
        self.assertIn("-0", result.numeric_values)
        self.assertEqual(result.ir.reassemble(domain.domain_id, lambda _: payload), payload)
        self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)

    def test_invalid_json_accounts_the_unparsed_remainder_as_malformed(self) -> None:
        payload = b'{"a":1 trailing'
        ref = CASRef("account-a", "archive-member", "d" * 64, len(payload))
        domain = ByteDomain("bad-json", ref, None, None)
        ledger = NodeLedger(); ledger.add_domain(domain)
        root = NodeRecord.root(domain.domain_id, domain.size, "json")
        ledger.add_node(root)
        result = inventory_json(
            data=payload, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
            observed_at="2026-07-18T10:00:00.000Z", schema_name="bad",
            known_paths=set(), decoder_id="json-occurrence", decoder_version="1",
        )
        self.assertIsNotNone(result.error)
        self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_json_inventory -v`

Expected: FAIL importing `tokenize_json`.

- [ ] **Step 3: Implement an exact byte tokenizer and recursive key occurrence parser**

```python
# ai_caddie/research/deep_mine/parsers/json_occurrence.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..unknowns import UnknownEvidence, UnknownRegistry


TOKEN_RE = re.compile(
    rb'(?:[ \t\r\n]+|"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\[\],:])'
)


@dataclass(frozen=True)
class JsonToken:
    kind: str
    raw: bytes
    start: int
    end: int
    occurrence_index: int


@dataclass(frozen=True)
class JsonKeyOccurrence:
    path: str
    key: str
    occurrence_index: int
    start: int
    end: int


@dataclass(frozen=True)
class JsonInventory:
    ir: LosslessIR
    keys: tuple[JsonKeyOccurrence, ...]
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def _kind(raw: bytes) -> str:
    if raw[:1] in b" \t\r\n": return "whitespace"
    if raw[:1] == b'"': return "string"
    if raw in {b"true", b"false", b"null"}: return "literal"
    if raw in b"{}[],:": return "punctuation"
    return "number"


def tokenize_json(data: bytes) -> tuple[JsonToken, ...]:
    tokens: list[JsonToken] = []
    position = 0
    counts: dict[str, int] = {}
    while position < len(data):
        match = TOKEN_RE.match(data, position)
        if match is None:
            raise ValueError(f"invalid JSON byte at offset {position}")
        raw = match.group(0)
        kind = _kind(raw)
        occurrence = counts.get(kind, 0); counts[kind] = occurrence + 1
        tokens.append(JsonToken(kind, raw, position, match.end(), occurrence))
        position = match.end()
    return tuple(tokens)


class _KeyParser:
    def __init__(self, tokens: tuple[JsonToken, ...]) -> None:
        self.tokens = tuple(token for token in tokens if token.kind != "whitespace")
        self.keys: list[JsonKeyOccurrence] = []
        self.structural: list[str] = []
        self.numeric: list[float | str] = []

    def parse(self) -> None:
        end = self._value(0, "$")
        if end != len(self.tokens):
            raise ValueError(f"trailing JSON token at offset {self.tokens[end].start}")

    def _value(self, index: int, path: str) -> int:
        if index >= len(self.tokens):
            raise ValueError("truncated JSON value")
        token = self.tokens[index]
        if token.raw == b"{": return self._object(index, path)
        if token.raw == b"[": return self._array(index, path)
        if token.kind == "number":
            self.numeric.append(token.raw.decode("ascii"))
        if token.kind in {"string", "number", "literal"}:
            self.structural.append(f"{path}:{token.kind}")
            return index + 1
        raise ValueError(f"expected JSON value at offset {token.start}")

    def _object(self, index: int, path: str) -> int:
        self.structural.append(f"{path}:object")
        index += 1
        counts: dict[str, int] = {}
        if index < len(self.tokens) and self.tokens[index].raw == b"}": return index + 1
        while True:
            if index >= len(self.tokens) or self.tokens[index].kind != "string":
                raise ValueError("expected JSON object key")
            key_token = self.tokens[index]
            key = json.loads(key_token.raw.decode("utf-8"))
            occurrence = counts.get(key, 0); counts[key] = occurrence + 1
            key_path = f"{path}.{key}"
            self.keys.append(JsonKeyOccurrence(key_path, key, occurrence, key_token.start, key_token.end))
            self.structural.append(f"{key_path}:key#{occurrence}")
            index += 1
            if index >= len(self.tokens) or self.tokens[index].raw != b":": raise ValueError("expected ':' after JSON key")
            index = self._value(index + 1, key_path)
            if index >= len(self.tokens): raise ValueError("unterminated JSON object")
            if self.tokens[index].raw == b"}": return index + 1
            if self.tokens[index].raw != b",": raise ValueError("expected ',' in JSON object")
            index += 1

    def _array(self, index: int, path: str) -> int:
        self.structural.append(f"{path}:array")
        index += 1; item_index = 0
        if index < len(self.tokens) and self.tokens[index].raw == b"]": return index + 1
        while True:
            index = self._value(index, f"{path}[{item_index}]")
            item_index += 1
            if index >= len(self.tokens): raise ValueError("unterminated JSON array")
            if self.tokens[index].raw == b"]": return index + 1
            if self.tokens[index].raw != b",": raise ValueError("expected ',' in JSON array")
            index += 1
```

- [ ] **Step 4: Implement ledger projection and malformed-tail preservation**

Append to the same file:

```python
def inventory_json(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    observed_at: str,
    schema_name: str,
    known_paths: set[str],
    decoder_id: str,
    decoder_version: str,
) -> JsonInventory:
    atoms: list[IRAtom] = []
    try:
        tokens = tokenize_json(data)
        parser = _KeyParser(tokens); parser.parse()
        for token in tokens:
            status = NodeStatus.PADDING if token.kind == "whitespace" else NodeStatus.DECODED
            node = NodeRecord.accounting(
                root, token.start, token.end - token.start, status,
                f"json-{token.kind}", decoder_id, decoder_version, token.occurrence_index,
            )
            ledger.add_node(node)
            atoms.append(IRAtom(f"json-{token.kind}", domain.domain_id, token.start, token.end - token.start, token.occurrence_index, True, node.node_id))
        for key in parser.keys:
            if key.path not in known_paths:
                unknowns.observe(
                    namespace="json",
                    locator=f"{schema_name}/{key.path}/occ{key.occurrence_index}",
                    observed_at=observed_at,
                    evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, key.start, key.end - key.start, "object-key", ()),
                    priority="medium",
                )
        return JsonInventory(LosslessIR(tuple(atoms)), tuple(parser.keys), tuple(parser.structural), tuple(parser.numeric), None)
    except (UnicodeDecodeError, ValueError) as exc:
        message = str(exc)
        match = re.search(r"offset (\d+)", message)
        offset = int(match.group(1)) if match else 0
        offset = max(0, min(offset, len(data)))
        if offset:
            prefix = NodeRecord.accounting(root, 0, offset, NodeStatus.DECODED, "json-prefix", decoder_id, decoder_version, 0)
            ledger.add_node(prefix)
            atoms.append(IRAtom("json-prefix", domain.domain_id, 0, offset, 0, True, prefix.node_id))
        remainder = NodeRecord.accounting(root, offset, len(data) - offset, NodeStatus.MALFORMED, "json-remainder", decoder_id, decoder_version, 0)
        ledger.add_node(remainder)
        atoms.append(IRAtom("json-remainder", domain.domain_id, offset, len(data) - offset, 0, True, remainder.node_id))
        unknowns.observe(
            namespace="json",
            locator=f"{schema_name}/malformed@{offset}",
            observed_at=observed_at,
            evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, offset, len(data) - offset, message, ()),
            priority="high",
        )
        return JsonInventory(LosslessIR(tuple(atoms)), (), (), (), message)
```

- [ ] **Step 5: Run tests**

Run: `uv run python -m unittest tests.test_deep_mine_json_inventory -v`

Expected: all tests PASS; duplicate `a` keys remain two occurrences; `1.2300` and whitespace remain exact slices; malformed bytes are classified.

- [ ] **Step 6: Commit C7**

```bash
git add ai_caddie/research/deep_mine/parsers/json_occurrence.py tests/test_deep_mine_json_inventory.py
git commit -m "feat(research): preserve duplicate json occurrences"
```

### Task 8: C8 — Inventory ZIP central/local records, duplicates, gaps, and member ByteDomains

**Files:**
- Create: `tests/deep_mine_fixture_builders.py`
- Create: `ai_caddie/research/deep_mine/parsers/archive.py`
- Create: `tests/test_deep_mine_archive_inventory.py`

- [ ] **Step 1: Add a deterministic synthetic ZIP builder and failing tests**

```python
# tests/deep_mine_fixture_builders.py
from __future__ import annotations

from io import BytesIO
import warnings
from zipfile import ZIP_DEFLATED, ZipFile


def build_zip(entries: list[tuple[str, bytes]], *, prefix: bytes = b"") -> bytes:
    stream = BytesIO()
    stream.write(prefix)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(stream, "a", compression=ZIP_DEFLATED) as archive:
            for name, body in entries:
                archive.writestr(name, body)
    return stream.getvalue()
```

```python
# tests/test_deep_mine_archive_inventory.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.archive import inventory_zip
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry
from tests.deep_mine_fixture_builders import build_zip


class ArchiveInventoryTests(unittest.TestCase):
    def test_duplicate_paths_are_distinct_occurrences_and_prefix_is_preserved(self) -> None:
        payload = build_zip([("hole/a.txt", b"A"), ("hole/a.txt", b"B")], prefix=b"UNREFERENCED")
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            raw_ref = cas.put_bytes("account-a", "raw-entity", payload)
            domain = ByteDomain("zip-domain", raw_ref, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "zip")
            ledger.add_node(root)
            unknowns = UnknownRegistry()
            result = inventory_zip(
                data=payload, domain=domain, root=root, ledger=ledger, unknowns=unknowns,
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="zip-inventory", decoder_version="1", build_hash="zip-build-1",
                max_member_bytes=1024, max_total_uncompressed=2048,
            )
            self.assertEqual([(entry.name, entry.occurrence_index) for entry in result.entries], [("hole/a.txt", 0), ("hole/a.txt", 1)])
            self.assertEqual([cas.read_bytes("account-a", item.ref) for item in result.members], [b"A", b"B"])
            self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
            self.assertGreater(ledger.prove_closure(domain.domain_id, root.node_id).status_bytes["opaque_preserved"], 0)
            member_domains = sorted(
                (item for item in ledger.domains.values() if item.parent_domain_id == domain.domain_id),
                key=lambda item: item.domain_id,
            )
            self.assertEqual(len(member_domains), 2)
            for member_domain in member_domains:
                member_root = next(
                    node for node in ledger.nodes.values()
                    if node.byte_domain_id == member_domain.domain_id and node.parent_node_id is None
                )
                proof = ledger.prove_closure(member_domain.domain_id, member_root.node_id)
                self.assertEqual(proof.status_bytes, {"opaque_preserved": member_domain.size})
            duplicate = next(record for record in unknowns.records() if record.locator.endswith("duplicate-path"))
            self.assertEqual(len(duplicate.evidence), 2)

    def test_unsafe_path_is_inventoried_but_never_materialized(self) -> None:
        payload = build_zip([("../escape.txt", b"secret")])
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            raw_ref = cas.put_bytes("account-a", "raw-entity", payload)
            domain = ByteDomain("unsafe-zip", raw_ref, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "zip"); ledger.add_node(root)
            result = inventory_zip(
                data=payload, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="zip-inventory", decoder_version="1", build_hash="zip-build-1",
                max_member_bytes=1024, max_total_uncompressed=2048,
            )
            self.assertFalse(result.entries[0].safe_path)
            self.assertEqual(result.members, ())

    def test_member_budget_exhaustion_is_explicit(self) -> None:
        payload = build_zip([("large.bin", b"x" * 100)])
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            ref = cas.put_bytes("account-a", "raw-entity", payload)
            domain = ByteDomain("budget-zip", ref, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "zip"); ledger.add_node(root)
            unknowns = UnknownRegistry()
            result = inventory_zip(
                data=payload, domain=domain, root=root, ledger=ledger, unknowns=unknowns,
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="zip-inventory", decoder_version="1", build_hash="zip-build-1",
                max_member_bytes=10, max_total_uncompressed=10,
            )
            self.assertEqual(result.entries[0].member_status, "budget_exhausted")
            self.assertEqual(result.members, ())
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_archive_inventory -v`

Expected: FAIL importing `inventory_zip`.

- [ ] **Step 3: Implement central/local header parsing and range partitioning**

```python
# ai_caddie/research/deep_mine/parsers/archive.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import PurePosixPath
import struct
from zipfile import BadZipFile, ZipFile

from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..provenance import DerivedArtifact, put_derived
from ..unknowns import UnknownEvidence, UnknownRegistry


CENTRAL_SIGNATURE = b"PK\x01\x02"
LOCAL_SIGNATURE = b"PK\x03\x04"
EOCD_SIGNATURE = b"PK\x05\x06"


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    occurrence_index: int
    flags: int
    compression_method: int
    crc32: int
    compressed_size: int
    uncompressed_size: int
    central_start: int
    central_end: int
    local_start: int
    local_data_start: int
    local_data_end: int
    central_extra_hex: str
    local_extra_hex: str
    safe_path: bool
    member_status: str


@dataclass(frozen=True)
class ArchiveInventory:
    ir: LosslessIR
    entries: tuple[ArchiveEntry, ...]
    members: tuple[DerivedArtifact, ...]
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def _u16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data): raise ValueError(f"truncated uint16 at {offset}")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data): raise ValueError(f"truncated uint32 at {offset}")
    return struct.unpack_from("<I", data, offset)[0]


def _decode_name(raw: bytes, flags: int) -> str:
    return raw.decode("utf-8" if flags & 0x800 else "cp437")


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and bool(path.parts)


def _central_entries(data: bytes) -> tuple[list[ArchiveEntry], int, int]:
    eocd = data.rfind(EOCD_SIGNATURE)
    if eocd < 0 or eocd + 22 > len(data): raise ValueError("ZIP EOCD not found")
    total_entries = _u16(data, eocd + 10)
    central_size = _u32(data, eocd + 12)
    central_offset = _u32(data, eocd + 16)
    comment_length = _u16(data, eocd + 20)
    eocd_end = eocd + 22 + comment_length
    if central_offset + central_size != eocd or eocd_end > len(data): raise ValueError("ZIP central directory range mismatch")
    rows: list[ArchiveEntry] = []
    counts: dict[str, int] = defaultdict(int)
    position = central_offset
    while position < eocd:
        if data[position:position + 4] != CENTRAL_SIGNATURE or position + 46 > eocd:
            raise ValueError(f"invalid central record at {position}")
        fields = struct.unpack_from("<4s6H3I5H2I", data, position)
        flags, method, crc32 = fields[3], fields[4], fields[7]
        compressed_size, uncompressed_size = fields[8], fields[9]
        name_length, extra_length, comment_length = fields[10], fields[11], fields[12]
        local_start = fields[16]
        central_end = position + 46 + name_length + extra_length + comment_length
        if central_end > eocd: raise ValueError("truncated central record")
        name_raw = data[position + 46:position + 46 + name_length]
        central_extra = data[position + 46 + name_length:position + 46 + name_length + extra_length]
        name = _decode_name(name_raw, flags)
        occurrence = counts[name]; counts[name] += 1
        if data[local_start:local_start + 4] != LOCAL_SIGNATURE or local_start + 30 > len(data):
            raise ValueError(f"missing local header for {name}")
        local = struct.unpack_from("<4s5H3I2H", data, local_start)
        local_flags, local_method = local[2], local[3]
        local_name_length, local_extra_length = local[9], local[10]
        local_name = data[local_start + 30:local_start + 30 + local_name_length]
        local_extra_start = local_start + 30 + local_name_length
        local_extra = data[local_extra_start:local_extra_start + local_extra_length]
        local_data_start = local_extra_start + local_extra_length
        local_data_end = local_data_start + compressed_size
        if local_data_end > central_offset: raise ValueError(f"compressed data leaves local section for {name}")
        if local_flags != flags or local_method != method or _decode_name(local_name, flags) != name:
            raise ValueError(f"local/central metadata mismatch for {name}")
        rows.append(ArchiveEntry(
            name, occurrence, flags, method, crc32, compressed_size, uncompressed_size,
            position, central_end, local_start, local_data_start, local_data_end,
            central_extra.hex(), local_extra.hex(), _safe_member(name), "pending",
        ))
        position = central_end
    if len(rows) != total_entries: raise ValueError("ZIP entry count mismatch")
    return rows, eocd, eocd_end


def _partition(size: int, claims: list[tuple[int, int, str, NodeStatus]]) -> list[tuple[int, int, str, NodeStatus]]:
    ordered = sorted(claims)
    result: list[tuple[int, int, str, NodeStatus]] = []
    cursor = 0
    for start, end, kind, status in ordered:
        if start < cursor: raise ValueError(f"ZIP range overlap at {start}")
        if start > cursor: result.append((cursor, start, "archive-unreferenced", NodeStatus.OPAQUE_PRESERVED))
        result.append((start, end, kind, status)); cursor = end
    if cursor < size: result.append((cursor, size, "archive-unreferenced", NodeStatus.OPAQUE_PRESERVED))
    return result
```

- [ ] **Step 4: Implement member extraction, budgets, derived domains, and unknown registration**

Append to the same file:

```python
def inventory_zip(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    cas: EncryptedCAS,
    storage_domain_id: str,
    observed_at: str,
    decoder_id: str,
    decoder_version: str,
    build_hash: str,
    max_member_bytes: int,
    max_total_uncompressed: int,
) -> ArchiveInventory:
    rows, eocd, eocd_end = _central_entries(data)
    claims: list[tuple[int, int, str, NodeStatus]] = []
    for row in rows:
        claims.append((row.local_start, row.local_data_end, f"zip-local:{row.name}#{row.occurrence_index}", NodeStatus.DECODED))
        claims.append((row.central_start, row.central_end, f"zip-central:{row.name}#{row.occurrence_index}", NodeStatus.DECODED))
    claims.append((eocd, eocd_end, "zip-eocd", NodeStatus.DECODED))
    atoms: list[IRAtom] = []
    for occurrence, (start, end, kind, status) in enumerate(_partition(len(data), claims)):
        node = NodeRecord.accounting(root, start, end - start, status, kind, decoder_id, decoder_version, occurrence)
        ledger.add_node(node)
        atoms.append(IRAtom(kind, domain.domain_id, start, end - start, occurrence, True, node.node_id))

    members: list[DerivedArtifact] = []
    updated: list[ArchiveEntry] = []
    total_uncompressed = 0
    duplicate_counts = Counter(row.name for row in rows)
    for row in rows:
        if duplicate_counts[row.name] > 1:
            unknowns.observe(
                namespace="archive",
                locator=f"{row.name}/duplicate-path",
                observed_at=observed_at,
                evidence=UnknownEvidence(
                    domain.cas_ref.sha256,
                    domain.domain_id,
                    row.local_start,
                    row.local_data_end - row.local_start,
                    f"duplicate-occurrence-{row.occurrence_index}",
                    (),
                ),
                priority="high",
            )
    with ZipFile(BytesIO(data), "r") as archive:
        infos = archive.infolist()
        for row, info in zip(rows, infos, strict=True):
            status = "decoded"
            if not row.safe_path:
                status = "unsafe_path"
            elif row.uncompressed_size > max_member_bytes or total_uncompressed + row.uncompressed_size > max_total_uncompressed:
                status = "budget_exhausted"
            else:
                try:
                    body = archive.read(info)
                except (BadZipFile, RuntimeError) as exc:
                    status = "malformed"
                    unknowns.observe(
                        namespace="archive",
                        locator=f"{row.name}#occ{row.occurrence_index}/decode-error",
                        observed_at=observed_at,
                        evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, row.local_start, row.local_data_end - row.local_start, str(exc), ()),
                        priority="high",
                    )
                else:
                    total_uncompressed += len(body)
                    artifact = put_derived(
                        cas=cas, storage_domain_id=storage_domain_id, byte_domain="archive-member", data=body,
                        parent_refs=(domain.cas_ref,), transform_name=f"zip-method-{row.compression_method}",
                        transform_version=decoder_version,
                        parameters={"path": row.name, "occurrenceIndex": row.occurrence_index, "crc32": row.crc32},
                        build_hash=build_hash,
                    )
                    member_domain = ByteDomain.create(
                        artifact.ref,
                        parent_domain_id=domain.domain_id,
                        transform_id=artifact.artifact_id,
                    )
                    ledger.add_domain(member_domain)
                    member_root = NodeRecord.root(
                        member_domain.domain_id,
                        member_domain.size,
                        f"archive-member:{row.name}#{row.occurrence_index}",
                    )
                    ledger.add_node(member_root)
                    member_node = NodeRecord.accounting(
                        member_root,
                        0,
                        member_domain.size,
                        NodeStatus.OPAQUE_PRESERVED,
                        "archive-member-body",
                        decoder_id,
                        decoder_version,
                        row.occurrence_index,
                    )
                    ledger.add_node(member_node)
                    unknowns.observe(
                        namespace="archive",
                        locator=f"{row.name}#occ{row.occurrence_index}/member-content",
                        observed_at=observed_at,
                        evidence=UnknownEvidence(
                            artifact.ref.sha256,
                            member_domain.domain_id,
                            0,
                            member_domain.size,
                            "opaque-member-awaiting-format-router",
                            (),
                        ),
                        priority="medium",
                    )
                    members.append(artifact)
            if status != "decoded":
                unknowns.observe(
                    namespace="archive",
                    locator=f"{row.name}#occ{row.occurrence_index}/{status}",
                    observed_at=observed_at,
                    evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, row.local_start, row.local_data_end - row.local_start, status, ()),
                    priority="high" if status in {"unsafe_path", "malformed"} else "medium",
                )
            updated.append(replace(row, member_status=status))
    structural = tuple(
        f"{row.name}#occ{row.occurrence_index}/method{row.compression_method}/flags{row.flags}/extra{len(bytes.fromhex(row.central_extra_hex))}"
        for row in updated
    )
    numeric = tuple(float(row.uncompressed_size) for row in updated)
    return ArchiveInventory(LosslessIR(tuple(atoms)), tuple(updated), tuple(members), structural, numeric, None)
```

- [ ] **Step 5: Run tests**

Run: `uv run python -m unittest tests.test_deep_mine_archive_inventory -v`

Expected: all tests PASS; duplicate member occurrences remain distinct and enter the Unknown Registry; unreferenced prefix bytes are opaque-preserved; every extracted member has its own opaque-preserved ByteDomain closure; unsafe and over-budget members never materialize outside CAS.

- [ ] **Step 6: Commit C8**

```bash
git add tests/deep_mine_fixture_builders.py ai_caddie/research/deep_mine/parsers/archive.py tests/test_deep_mine_archive_inventory.py
git commit -m "feat(research): inventory archives without silent gaps"
```

### Task 9: C9 — Inventory texture/image metadata and decoded pixel ByteDomains

**Files:**
- Create: `ai_caddie/research/deep_mine/parsers/texture.py`
- Modify: `tests/deep_mine_fixture_builders.py` — add deterministic KTX1/KTX2 header/index/level builders.
- Create: `tests/test_deep_mine_texture_inventory.py`

- [ ] **Step 1: Write failing frame, alpha, metadata, pixel-domain, and stats tests**

```python
# tests/test_deep_mine_texture_inventory.py
from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.texture import inventory_texture
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry


def animated_gif() -> bytes:
    first = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    second = Image.new("RGBA", (2, 2), (0, 255, 0, 255))
    stream = BytesIO()
    first.save(stream, format="GIF", save_all=True, append_images=[second], duration=20, loop=0)
    return stream.getvalue()


def sixteen_bit_png() -> bytes:
    image = Image.new("I;16", (1, 1), 4095)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class TextureInventoryTests(unittest.TestCase):
    def test_records_frames_alpha_bit_depth_stats_and_pixel_domains(self) -> None:
        payload = animated_gif()
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            ref = cas.put_bytes("account-a", "archive-member", payload)
            domain = ByteDomain("image-domain", ref, "zip-domain", "member-transform")
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "image"); ledger.add_node(root)
            result = inventory_texture(
                data=payload, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="pillow-image", decoder_version="12.2.0", build_hash="pillow-build",
            )
            self.assertEqual(result.format, "GIF")
            self.assertEqual(len(result.frames), 2)
            self.assertTrue(result.frames[0].has_alpha)
            self.assertEqual(result.frames[0].width, 2)
            self.assertEqual(result.frames[0].height, 2)
            self.assertEqual(result.frames[0].bit_depth_per_channel, 8)
            self.assertEqual(result.frames[0].decoded_bit_depth_per_channel, 8)
            self.assertEqual(len(result.pixel_artifacts), 2)
            self.assertEqual(result.pixel_artifacts[0].ref.byte_domain, "image-pixels")
            self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
            pixel_domains = sorted(
                (item for item in ledger.domains.values() if item.parent_domain_id == domain.domain_id),
                key=lambda item: item.domain_id,
            )
            self.assertEqual(len(pixel_domains), 2)
            for pixel_domain in pixel_domains:
                pixel_root = next(
                    node for node in ledger.nodes.values()
                    if node.byte_domain_id == pixel_domain.domain_id and node.parent_node_id is None
                )
                self.assertEqual(
                    ledger.prove_closure(pixel_domain.domain_id, pixel_root.node_id).status_bytes,
                    {"decoded": pixel_domain.size},
                )

    def test_preserves_source_bit_depth_before_rgba8_pixel_derivation(self) -> None:
        payload = sixteen_bit_png()
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            ref = cas.put_bytes("account-a", "archive-member", payload)
            domain = ByteDomain("png16-domain", ref, "zip-domain", "member-transform")
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "image"); ledger.add_node(root)
            result = inventory_texture(
                data=payload, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="pillow-image", decoder_version="12.2.0", build_hash="pillow-build",
            )
            self.assertEqual(result.frames[0].bit_depth_per_channel, 16)
            self.assertEqual(result.frames[0].decoded_bit_depth_per_channel, 8)
```

Extend the same test file imports with `build_ktx1/build_ktx2` and `inventory_ktx`, then add:

```python
    def test_ktx1_levels_have_exact_size_padding_and_independent_encoded_domains(self) -> None:
        payload = build_ktx1((b"abc", b"12345"), gl_internal_format=0x83F1)
        result, ledger = self.inventory_ktx_fixture(payload, "ktx1")
        self.assertEqual(result.container, "ktx1")
        self.assertEqual([(row.byte_length, row.padding_length) for row in result.levels], [(3, 1), (5, 3)])
        self.assertEqual(len(result.encoded_level_artifacts), 2)
        self.assertEqual(result.pixel_artifacts, ())
        self.assertTrue(ledger.prove_closure(result.root_domain_id, result.root_node_id).complete)
        self.assertTrue(all(row.byte_domain == "ktx-encoded-level" for row in (item.ref for item in result.encoded_level_artifacts)))

    def test_ktx2_level_index_uses_u64_bounds_and_preserves_unsupported_levels(self) -> None:
        payload = build_ktx2((b"level-zero", b"L1"), vk_format=147, supercompression_scheme=2)
        result, ledger = self.inventory_ktx_fixture(payload, "ktx2")
        self.assertEqual(result.container, "ktx2")
        self.assertEqual([row.uncompressed_length for row in result.levels], [10, 2])
        self.assertEqual(result.pixel_artifacts, ())
        self.assertEqual(len(result.encoded_level_artifacts), 2)
        self.assertTrue(any(item.priority == "high" and "unsupported-transcode" in item.locator for item in result.unknown_records))
        self.assertTrue(ledger.prove_closure(result.root_domain_id, result.root_node_id).complete)

    def test_ktx_bad_offset_fails_closed_with_complete_root_accounting(self) -> None:
        payload = bytearray(build_ktx2((b"level",), vk_format=37, supercompression_scheme=0))
        payload[80:88] = (2**63).to_bytes(8, "little")
        result, ledger = self.inventory_ktx_fixture(bytes(payload), "ktx2-bad")
        self.assertIsNotNone(result.error)
        proof = ledger.prove_closure(result.root_domain_id, result.root_node_id)
        self.assertTrue(proof.complete)
        self.assertEqual(proof.status_bytes, {"malformed": len(payload)})
```

`inventory_ktx_fixture` is a complete test helper in the same class: it creates a `test-fixture` CAS/domain/root/UnknownRegistry, invokes `inventory_ktx`, and returns the result/ledger. It never injects a claimed container kind; the parser derives KTX1/KTX2 from the exact 12-byte identifier.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_texture_inventory -v`

Expected: FAIL importing `inventory_texture`.

- [ ] **Step 3: Implement metadata hashing, frame stats, and pixel transforms**

```python
# ai_caddie/research/deep_mine/parsers/texture.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO

from PIL import Image, ImageSequence, ImageStat, UnidentifiedImageError

from ai_caddie.course_data.cas import EncryptedCAS

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..provenance import DerivedArtifact, put_derived
from ..unknowns import UnknownEvidence, UnknownRegistry


@dataclass(frozen=True)
class TextureFrame:
    index: int
    width: int
    height: int
    mode: str
    channels: tuple[str, ...]
    has_alpha: bool
    bit_depth_per_channel: int
    decoded_bit_depth_per_channel: int
    channel_min: tuple[float, ...]
    channel_max: tuple[float, ...]
    channel_mean: tuple[float, ...]


@dataclass(frozen=True)
class TextureInventory:
    ir: LosslessIR
    format: str
    frames: tuple[TextureFrame, ...]
    metadata_hashes: dict[str, str]
    pixel_artifacts: tuple[DerivedArtifact, ...]
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def _metadata_hashes(image: Image.Image) -> dict[str, str]:
    rows: dict[str, str] = {}
    values = {
        "icc": image.info.get("icc_profile"),
        "exif": image.info.get("exif"),
        "xmp": image.info.get("xmp"),
    }
    for name, value in values.items():
        if value:
            body = value if isinstance(value, bytes) else str(value).encode("utf-8")
            rows[name] = hashlib.sha256(body).hexdigest()
    return rows


def _source_bit_depth(mode: str) -> int:
    if mode == "1": return 1
    if mode.startswith("I;16"): return 16
    if mode in {"I", "F"}: return 32
    if mode in {"L", "LA", "P", "PA", "RGB", "RGBA", "RGBX", "RGBa", "CMYK", "YCbCr", "HSV", "LAB"}: return 8
    return 0


def inventory_texture(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    cas: EncryptedCAS,
    storage_domain_id: str,
    observed_at: str,
    decoder_id: str,
    decoder_version: str,
    build_hash: str,
) -> TextureInventory:
    try:
        image = Image.open(BytesIO(data))
    except (UnidentifiedImageError, OSError) as exc:
        node = NodeRecord.accounting(root, 0, len(data), NodeStatus.MALFORMED, "image-malformed", decoder_id, decoder_version, 0)
        ledger.add_node(node)
        unknowns.observe(
            namespace="texture", locator="image/decode-error", observed_at=observed_at,
            evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, 0, len(data), str(exc), ()), priority="high",
        )
        return TextureInventory(LosslessIR((IRAtom("image-malformed", domain.domain_id, 0, len(data), 0, True, node.node_id),)), "unknown", (), {}, (), (), (), str(exc))

    raw_node = NodeRecord.accounting(root, 0, len(data), NodeStatus.DECODED, "image-container", decoder_id, decoder_version, 0)
    ledger.add_node(raw_node)
    frames: list[TextureFrame] = []
    artifacts: list[DerivedArtifact] = []
    numeric: list[float] = []
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        rgba = frame.convert("RGBA")
        source_has_alpha = (
            "A" in frame.getbands()
            or "transparency" in frame.info
            or "transparency" in image.info
        )
        source_bit_depth = _source_bit_depth(frame.mode)
        if source_bit_depth == 0:
            unknowns.observe(
                namespace="texture",
                locator=f"frame{index}/source-mode/{frame.mode}",
                observed_at=observed_at,
                evidence=UnknownEvidence(
                    domain.cas_ref.sha256, domain.domain_id, 0, len(data),
                    "unknown-source-bit-depth", (),
                ),
                priority="medium",
            )
        stats = ImageStat.Stat(rgba)
        extrema = rgba.getextrema()
        frame_row = TextureFrame(
            index=index, width=rgba.width, height=rgba.height, mode=frame.mode,
            channels=tuple(rgba.getbands()), has_alpha=source_has_alpha,
            bit_depth_per_channel=source_bit_depth, decoded_bit_depth_per_channel=8,
            channel_min=tuple(float(pair[0]) for pair in extrema),
            channel_max=tuple(float(pair[1]) for pair in extrema),
            channel_mean=tuple(float(value) for value in stats.mean),
        )
        frames.append(frame_row)
        numeric.extend((*frame_row.channel_min, *frame_row.channel_max, *frame_row.channel_mean))
        artifact = put_derived(
            cas=cas, storage_domain_id=storage_domain_id, byte_domain="image-pixels", data=rgba.tobytes(),
            parent_refs=(domain.cas_ref,), transform_name="decode-rgba8", transform_version=decoder_version,
            parameters={
                "frameIndex": index,
                "width": rgba.width,
                "height": rgba.height,
                "sourceMode": frame.mode,
                "sourceBitDepth": frame_row.bit_depth_per_channel,
                "decodedMode": "RGBA",
                "decodedBitDepth": frame_row.decoded_bit_depth_per_channel,
            },
            build_hash=build_hash,
        )
        pixel_domain = ByteDomain.create(
            artifact.ref,
            parent_domain_id=domain.domain_id,
            transform_id=artifact.artifact_id,
        )
        ledger.add_domain(pixel_domain)
        pixel_root = NodeRecord.root(pixel_domain.domain_id, pixel_domain.size, f"image-pixels:frame{index}")
        ledger.add_node(pixel_root)
        ledger.add_node(NodeRecord.accounting(
            pixel_root, 0, pixel_domain.size, NodeStatus.DECODED,
            "rgba8-pixel-plane", decoder_id, decoder_version, index,
        ))
        artifacts.append(artifact)
    structural = tuple(
        f"frame{row.index}/{row.width}x{row.height}/{row.mode}/sourceBits{row.bit_depth_per_channel}/decodedBits{row.decoded_bit_depth_per_channel}/alpha{row.has_alpha}"
        for row in frames
    )
    return TextureInventory(
        LosslessIR((IRAtom("image-container", domain.domain_id, 0, len(data), 0, True, raw_node.node_id),)),
        image.format or "unknown", tuple(frames), _metadata_hashes(image), tuple(artifacts), structural, tuple(numeric), None,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m unittest tests.test_deep_mine_texture_inventory -v`

Expected: all tests PASS; raw container and each decoded pixel plane use separate closed ByteDomains; 16-bit source depth remains distinct from the RGBA8 derived plane; reports contain only metadata hashes, not embedded ICC/EXIF/XMP bytes.

- [ ] **Step 5: Commit C9**

```bash
git add tests/deep_mine_fixture_builders.py ai_caddie/research/deep_mine/parsers/texture.py tests/test_deep_mine_texture_inventory.py
git commit -m "feat(research): inventory image metadata and pixels"
```

### Task 10: C10 — Enumerate every Draco attribute without research-layer rounding

**Files:**
- Create: `ai_caddie/research/deep_mine/node/draco_inventory.js`
- Create: `ai_caddie/research/deep_mine/parsers/draco.py`
- Create: `tests/node/deep_mine_draco_inventory.test.js`
- Create: `tests/test_deep_mine_draco_bridge.py`
- Modify: `package.json`

- [ ] **Step 1: Write failing Node metadata/no-rounding and real decoder smoke tests**

```javascript
// tests/node/deep_mine_draco_inventory.test.js
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  inventoryBuffer,
  summarizeValues,
} = require("../../ai_caddie/research/deep_mine/node/draco_inventory.js");

test("summarizeValues keeps decoded precision and per-component ranges", () => {
  const summary = summarizeValues([1.23456789, -2.5, 9.125, 4.75], 2);
  assert.deepEqual(summary.values, [[1.23456789, -2.5], [9.125, 4.75]]);
  assert.deepEqual(summary.min, [1.23456789, -2.5]);
  assert.deepEqual(summary.max, [9.125, 4.75]);
});

test("bunny fixture emits every declared attribute", async () => {
  const modulePath = require.resolve("draco3d");
  const bunny = fs.readFileSync(path.join(path.dirname(modulePath), "bunny.drc"));
  const inventory = await inventoryBuffer(bunny);
  assert.equal(inventory.status, "decoded");
  assert.equal(inventory.attributes.length, inventory.attributeCount);
  assert.ok(inventory.attributes.length >= 1);
  for (const attribute of inventory.attributes) {
    assert.equal(attribute.values.length, inventory.pointCount);
    assert.equal(attribute.min.length, attribute.componentCount);
    assert.equal(attribute.max.length, attribute.componentCount);
    assert.equal(typeof attribute.uniqueId, "number");
  }
});
```

- [ ] **Step 2: Run the Node test and verify the helper is absent**

Run: `npm ci --omit=dev && node --test tests/node/deep_mine_draco_inventory.test.js`

Expected: FAIL requiring `ai_caddie/research/deep_mine/node/draco_inventory.js`.

- [ ] **Step 3: Implement the Node decoder with all attributes and transform metadata**

```javascript
#!/usr/bin/env node
// ai_caddie/research/deep_mine/node/draco_inventory.js
"use strict";

const fs = require("node:fs");
const draco3d = require("draco3d");

function semanticName(module, value) {
  const rows = new Map([
    [module.POSITION, "POSITION"],
    [module.NORMAL, "NORMAL"],
    [module.COLOR, "COLOR"],
    [module.TEX_COORD, "TEX_COORD"],
    [module.GENERIC, "GENERIC"],
  ]);
  return rows.get(value) || `UNKNOWN_${value}`;
}

function summarizeValues(flatValues, componentCount) {
  const values = [];
  const min = Array(componentCount).fill(Infinity);
  const max = Array(componentCount).fill(-Infinity);
  for (let offset = 0; offset < flatValues.length; offset += componentCount) {
    const row = [];
    for (let component = 0; component < componentCount; component += 1) {
      const value = flatValues[offset + component];
      row.push(value);
      if (value < min[component]) min[component] = value;
      if (value > max[component]) max[component] = value;
    }
    values.push(row);
  }
  return { values, min, max };
}

function quantizationMetadata(module, attribute) {
  const quantization = new module.AttributeQuantizationTransform();
  const octahedron = new module.AttributeOctahedronTransform();
  try {
    if (quantization.InitFromAttribute(attribute)) {
      return {
        kind: "quantization",
        bits: quantization.quantization_bits(),
        range: quantization.range(),
        min: Array.from({ length: attribute.num_components() }, (_, index) => quantization.min_value(index)),
      };
    }
    if (octahedron.InitFromAttribute(attribute)) {
      return { kind: "octahedron", bits: octahedron.quantization_bits() };
    }
    return null;
  } finally {
    module.destroy(quantization);
    module.destroy(octahedron);
  }
}

async function inventoryBuffer(input) {
  const module = await draco3d.createDecoderModule({});
  const decoder = new module.Decoder();
  const buffer = new module.DecoderBuffer();
  buffer.Init(new Int8Array(input), input.length);
  for (const semantic of [module.POSITION, module.NORMAL, module.COLOR, module.TEX_COORD, module.GENERIC]) {
    decoder.SkipAttributeTransform(semantic);
  }
  let geometry = null;
  try {
    const geometryType = decoder.GetEncodedGeometryType(buffer);
    let status;
    let geometryKind;
    if (geometryType === module.TRIANGULAR_MESH) {
      geometry = new module.Mesh();
      status = decoder.DecodeBufferToMesh(buffer, geometry);
      geometryKind = "triangular_mesh";
    } else if (geometryType === module.POINT_CLOUD) {
      geometry = new module.PointCloud();
      status = decoder.DecodeBufferToPointCloud(buffer, geometry);
      geometryKind = "point_cloud";
    } else {
      return { status: "malformed", error: `unsupported geometry type ${geometryType}` };
    }
    if (!status.ok()) {
      return { status: "malformed", error: status.error_msg() };
    }
    const attributes = [];
    for (let index = 0; index < geometry.num_attributes(); index += 1) {
      const attribute = decoder.GetAttribute(geometry, index);
      const array = new module.DracoFloat32Array();
      try {
        if (!decoder.GetAttributeFloatForAllPoints(geometry, attribute, array)) {
          throw new Error(`failed reading attribute ${index}`);
        }
        const flat = Array.from({ length: array.size() }, (_, valueIndex) => array.GetValue(valueIndex));
        const summarized = summarizeValues(flat, attribute.num_components());
        attributes.push({
          index,
          semanticCode: attribute.attribute_type(),
          semantic: semanticName(module, attribute.attribute_type()),
          uniqueId: attribute.unique_id(),
          componentCount: attribute.num_components(),
          dataType: attribute.data_type(),
          normalized: attribute.normalized(),
          byteStride: attribute.byte_stride(),
          byteOffset: attribute.byte_offset(),
          transform: quantizationMetadata(module, attribute),
          values: summarized.values,
          min: summarized.min,
          max: summarized.max,
        });
      } finally {
        module.destroy(array);
      }
    }
    const faces = [];
    if (geometryKind === "triangular_mesh") {
      const face = new module.DracoInt32Array();
      try {
        for (let index = 0; index < geometry.num_faces(); index += 1) {
          decoder.GetFaceFromMesh(geometry, index, face);
          faces.push([face.GetValue(0), face.GetValue(1), face.GetValue(2)]);
        }
      } finally {
        module.destroy(face);
      }
    }
    return {
      status: "decoded",
      geometryKind,
      pointCount: geometry.num_points(),
      faceCount: geometryKind === "triangular_mesh" ? geometry.num_faces() : 0,
      attributeCount: geometry.num_attributes(),
      attributes,
      faces,
    };
  } catch (error) {
    return { status: "malformed", error: error.message || String(error) };
  } finally {
    if (geometry) module.destroy(geometry);
    module.destroy(buffer);
    module.destroy(decoder);
  }
}

async function main() {
  const input = fs.readFileSync(0);
  const result = await inventoryBuffer(input);
  process.stdout.write(`${JSON.stringify(result)}\n`);
  if (result.status !== "decoded") process.exitCode = 2;
}

module.exports = { inventoryBuffer, summarizeValues };

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.message || error}\n`);
    process.exit(2);
  });
}
```

- [ ] **Step 4: Write the failing Python bridge test**

```python
# tests/test_deep_mine_draco_bridge.py
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.draco import inventory_draco
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry


class DracoBridgeTests(unittest.TestCase):
    def test_all_attributes_are_stored_as_derived_values_without_rounding(self) -> None:
        decoded = {
            "status": "decoded", "geometryKind": "triangular_mesh", "pointCount": 1,
            "faceCount": 0, "attributeCount": 2, "faces": [],
            "attributes": [
                {"index": 0, "semanticCode": 0, "semantic": "POSITION", "uniqueId": 0,
                 "componentCount": 3, "dataType": 9, "normalized": False,
                 "byteStride": 12, "byteOffset": 0, "transform": {"kind": "quantization", "bits": 14},
                 "values": [[1.23456789, 2.0, 3.0]], "min": [1.23456789, 2.0, 3.0], "max": [1.23456789, 2.0, 3.0]},
                {"index": 1, "semanticCode": 3, "semantic": "TEX_COORD", "uniqueId": 7,
                 "componentCount": 2, "dataType": 9, "normalized": False,
                 "byteStride": 8, "byteOffset": 0, "transform": None,
                 "values": [[0.25, 0.75]], "min": [0.25, 0.75], "max": [0.25, 0.75]},
            ],
        }
        completed = subprocess.CompletedProcess(["node"], 0, json.dumps(decoded).encode(), b"")
        with tempfile.TemporaryDirectory() as tmp, patch("subprocess.run", return_value=completed):
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            ref = cas.put_bytes("account-a", "archive-member", b"drc")
            domain = ByteDomain("drc-domain", ref, "zip-domain", "member-transform")
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "draco"); ledger.add_node(root)
            result = inventory_draco(
                data=b"drc", domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="account-a", observed_at="2026-07-18T10:00:00.000Z",
                decoder_version="draco3d-1.5.7", build_hash="draco-build",
            )
            self.assertEqual(len(result.attributes), 2)
            position_bytes = cas.read_bytes("account-a", result.attributes[0].values_artifact.ref)
            self.assertIn(b"1.23456789", position_bytes)
            self.assertEqual(result.attributes[1].unique_id, 7)
            self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
            value_domains = sorted(
                (item for item in ledger.domains.values() if item.parent_domain_id == domain.domain_id),
                key=lambda item: item.domain_id,
            )
            self.assertEqual(
                {item.domain_id for item in value_domains},
                {attribute.byte_domain_id for attribute in result.attributes},
            )
            for value_domain in value_domains:
                value_root = next(
                    node for node in ledger.nodes.values()
                    if node.byte_domain_id == value_domain.domain_id and node.parent_node_id is None
                )
                self.assertEqual(
                    ledger.prove_closure(value_domain.domain_id, value_root.node_id).status_bytes,
                    {"decoded": value_domain.size},
                )
```

- [ ] **Step 5: Implement the Python bridge and derived attribute artifacts**

```python
# ai_caddie/research/deep_mine/parsers/draco.py
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.course_data.cas import EncryptedCAS

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..provenance import DerivedArtifact, put_derived
from ..unknowns import UnknownEvidence, UnknownRegistry


@dataclass(frozen=True)
class DracoAttribute:
    index: int
    semantic: str
    semantic_code: int
    unique_id: int
    component_count: int
    data_type: int
    normalized: bool
    transform: dict[str, object] | None
    minimum: tuple[float, ...]
    maximum: tuple[float, ...]
    values_artifact: DerivedArtifact
    byte_domain_id: str


@dataclass(frozen=True)
class DracoInventory:
    ir: LosslessIR
    geometry_kind: str
    point_count: int
    face_count: int
    attributes: tuple[DracoAttribute, ...]
    faces_artifact: DerivedArtifact | None
    faces_byte_domain_id: str | None
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def inventory_draco(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    cas: EncryptedCAS,
    storage_domain_id: str,
    observed_at: str,
    decoder_version: str,
    build_hash: str,
) -> DracoInventory:
    script = Path(__file__).resolve().parents[1] / "node" / "draco_inventory.js"
    completed = subprocess.run(
        ["node", str(script)], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120,
    )
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        payload = {"status": "malformed", "error": f"invalid node output: {exc}"}
    if completed.returncode != 0 or payload.get("status") != "decoded":
        error = str(payload.get("error") or completed.stderr.decode("utf-8", "replace")[:500])
        node = NodeRecord.accounting(root, 0, len(data), NodeStatus.MALFORMED, "draco-malformed", "draco3d", decoder_version, 0)
        ledger.add_node(node)
        unknowns.observe(
            namespace="draco", locator="decode-error", observed_at=observed_at,
            evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, 0, len(data), error, ()), priority="high",
        )
        return DracoInventory(
            LosslessIR((IRAtom("draco-malformed", domain.domain_id, 0, len(data), 0, True, node.node_id),)),
            "unknown", 0, 0, (), None, None, (), (), error,
        )

    raw_node = NodeRecord.accounting(root, 0, len(data), NodeStatus.DECODED, "draco-container", "draco3d", decoder_version, 0)
    ledger.add_node(raw_node)
    attributes: list[DracoAttribute] = []
    structural: list[str] = []
    numeric: list[float] = []
    for row in payload["attributes"]:
        values = row["values"]
        artifact = put_derived(
            cas=cas, storage_domain_id=storage_domain_id, byte_domain="draco-attribute-values",
            data=canonical_json_bytes(values), parent_refs=(domain.cas_ref,),
            transform_name="draco-decode-attribute", transform_version=decoder_version,
            parameters={"attributeIndex": row["index"], "uniqueId": row["uniqueId"], "semantic": row["semantic"]},
            build_hash=build_hash,
        )
        value_domain = ByteDomain.create(
            artifact.ref,
            parent_domain_id=domain.domain_id,
            transform_id=artifact.artifact_id,
        )
        ledger.add_domain(value_domain)
        value_root = NodeRecord.root(
            value_domain.domain_id,
            value_domain.size,
            f"draco-attribute-values:{row['index']}",
        )
        ledger.add_node(value_root)
        ledger.add_node(NodeRecord.accounting(
            value_root, 0, value_domain.size, NodeStatus.DECODED,
            "draco-decoded-values", "draco3d", decoder_version, int(row["index"]),
        ))
        minimum = tuple(float(value) for value in row["min"])
        maximum = tuple(float(value) for value in row["max"])
        numeric.extend((*minimum, *maximum))
        attribute = DracoAttribute(
            int(row["index"]), str(row["semantic"]), int(row["semanticCode"]), int(row["uniqueId"]),
            int(row["componentCount"]), int(row["dataType"]), bool(row["normalized"]),
            row.get("transform"), minimum, maximum, artifact, value_domain.domain_id,
        )
        attributes.append(attribute)
        structural.append(
            f"attr{attribute.index}/{attribute.semantic}/uid{attribute.unique_id}/components{attribute.component_count}/type{attribute.data_type}/normalized{attribute.normalized}"
        )
    faces_artifact = None
    faces_byte_domain_id = None
    if payload.get("faces"):
        faces_artifact = put_derived(
            cas=cas, storage_domain_id=storage_domain_id, byte_domain="draco-faces",
            data=canonical_json_bytes(payload["faces"]), parent_refs=(domain.cas_ref,),
            transform_name="draco-decode-faces", transform_version=decoder_version,
            parameters={"faceCount": payload["faceCount"]}, build_hash=build_hash,
        )
        faces_domain = ByteDomain.create(
            faces_artifact.ref,
            parent_domain_id=domain.domain_id,
            transform_id=faces_artifact.artifact_id,
        )
        ledger.add_domain(faces_domain)
        faces_root = NodeRecord.root(faces_domain.domain_id, faces_domain.size, "draco-faces")
        ledger.add_node(faces_root)
        ledger.add_node(NodeRecord.accounting(
            faces_root, 0, faces_domain.size, NodeStatus.DECODED,
            "draco-decoded-faces", "draco3d", decoder_version, 0,
        ))
        faces_byte_domain_id = faces_domain.domain_id
    if len(attributes) != int(payload["attributeCount"]):
        raise ValueError("Draco decoder omitted an attribute")
    return DracoInventory(
        LosslessIR((IRAtom("draco-container", domain.domain_id, 0, len(data), 0, True, raw_node.node_id),)),
        str(payload["geometryKind"]), int(payload["pointCount"]), int(payload["faceCount"]),
        tuple(attributes), faces_artifact, faces_byte_domain_id, tuple(structural), tuple(numeric), None,
    )
```

- [ ] **Step 6: Add the package script and run both suites**

Modify the root `package.json` scripts object to contain:

```json
{
  "decode:geometry": "node ai_caddie/geometry/decode_courseview_geometry.js",
  "fetch:geometry-key": "node ai_caddie/geometry/fetch_courseview_geometry_key.js",
  "test:deep-mine:draco": "node --test tests/node/deep_mine_draco_inventory.test.js"
}
```

Run:

```bash
npm ci --omit=dev
npm run test:deep-mine:draco
uv run python -m unittest tests.test_deep_mine_draco_bridge -v
```

Expected: Node tests PASS against the packaged bunny; Python bridge tests PASS; every decoded attribute/faces buffer has its own closed ByteDomain; no `round()`, `toFixed()`, or precision option exists in the research decoder.

- [ ] **Step 7: Commit C10**

```bash
git add package.json ai_caddie/research/deep_mine/node/draco_inventory.js ai_caddie/research/deep_mine/parsers/draco.py tests/node/deep_mine_draco_inventory.test.js tests/test_deep_mine_draco_bridge.py
git commit -m "feat(research): inventory every draco attribute"
```

### Task 11: C11 — Recursively inventory DSKIMG/GMP sections and decode TRE/RGN/LBL/DEM objects

**Files:**
- Modify: `contracts/canonical/deep_mine_v1.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tests/deep_mine_fixture_builders.py`
- Create: `ai_caddie/research/deep_mine/parsers/dskimg.py`
- Create: `ai_caddie/research/deep_mine/parsers/dskimg_header_facts.py`
- Create: `ai_caddie/research/deep_mine/parsers/gmp.py`
- Create: `ai_caddie/research/deep_mine/parsers/gmp_descriptors.py`
- Create: `ai_caddie/research/deep_mine/verify_img_matrix.py`
- Create: `contracts/research/gmp_variant_descriptor_v1.schema.json`
- Create: `contracts/research/dskimg_header_facts_v1.schema.json`
- Create: `contracts/research/authorized_garmin_img_matrix_v1.schema.json`
- Create: `research/corpus/gmp_variant_descriptors.json`
- Create: `research/corpus/dskimg_header_facts.json`
- Create: `research/corpus/authorized_garmin_img_matrix.json`
- Create: `tests/fixtures/research/synthetic_gmp_variant_descriptor.json`
- Create: `tests/fixtures/research/synthetic_dskimg_header_facts.json`
- Create: `tests/fixtures/research/synthetic_gmp_golden.json`
- Create: `tests/test_deep_mine_dskimg_inventory.py`
- Create: `tests/test_deep_mine_gmp_objects.py`

- [ ] **Step 1: Add a complete synthetic DSKIMG/coursedata builder**

Append to `tests/deep_mine_fixture_builders.py`:

```python
import struct


def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _synthetic_tre() -> bytes:
    header = struct.pack("<4sHBBH6x", b"TRE\0", 16, 1, 1, 1)
    level = struct.pack("<BBHI", 0, 24, 0, 1)
    subdivision = struct.pack("<IiiiiII", 1, 0, 0, 1_000, 1_000, 16, len(_synthetic_rgn()) - 16)
    return header + level + subdivision


def _rgn_record(kind: int, label_offset: int, origin: tuple[int, int], deltas: tuple[tuple[int, int], ...], *, closed: bool = False) -> bytes:
    flags = 1 if closed else 0
    length = 22 + 4 * len(deltas)
    return struct.pack(
        "<HBBHIIii", length, kind, flags, len(deltas), 1, label_offset,
        origin[0], origin[1],
    ) + b"".join(struct.pack("<hh", east, north) for east, north in deltas)


def _synthetic_rgn() -> bytes:
    records = (
        _rgn_record(1, 0, (100, 100), ((0, 0),)),
        _rgn_record(2, 0, (100, 100), ((0, 0), (200, 100))),
        _rgn_record(3, 8, (400, 400), ((0, 0), (100, 0), (100, 100), (0, 100), (0, 0)), closed=True),
    )
    body = b"".join(records)
    return struct.pack("<4sHHII", b"RGN\0", 16, len(records), 16, len(body)) + body


def _synthetic_lbl() -> bytes:
    strings = b"fairway\0bunker\0"
    return struct.pack("<4sHHII", b"LBL\0", 16, 65_001, 16, len(strings)) + strings


def _synthetic_dem() -> bytes:
    samples = struct.pack("<hhhh", 100, 101, 102, 103)
    descriptor = struct.pack(
        "<BBHiiHHiiI", 12, 16, 4, 0, 0, 2, 2, 1_000, 100, 48,
    )
    return struct.pack("<4sHHIII", b"DEM\0", 20, 1, 1, 20, len(samples)) + descriptor + samples


def build_synthetic_dskimg(*, invalid_block: bool = False) -> tuple[bytes, bytes]:
    block_size = 512
    image = bytearray(block_size * 12)
    image[0x10:0x16] = b"DSKIMG"
    image[0x61] = 9
    image[0x62] = 0

    gmp = bytearray(block_size * 2)
    struct.pack_into("<H", gmp, 0, 0x31)
    gmp[2:12] = b"GARMIN GMP"
    struct.pack_into("<I", gmp, 0x19, 0x100)
    struct.pack_into("<I", gmp, 0x1D, 0x180)
    struct.pack_into("<I", gmp, 0x21, 0x200)
    struct.pack_into("<I", gmp, 0x2D, 0x280)
    sections = {
        0x100: _synthetic_tre(),
        0x180: _synthetic_rgn(),
        0x200: _synthetic_lbl(),
        0x280: _synthetic_dem(),
    }
    for offset, section in sections.items():
        gmp[offset:offset + len(section)] = section

    fat = 0x1200
    image[fat] = 1
    image[fat + 1:fat + 9] = b"COURSE  "
    image[fat + 9:fat + 12] = b"GMP"
    struct.pack_into("<I", image, fat + 12, len(gmp))
    struct.pack_into("<H", image, fat + 0x20, 99 if invalid_block else 10)
    struct.pack_into("<H", image, fat + 0x22, 11)
    struct.pack_into("<H", image, fat + 0x24, 0xFFFF)
    image[10 * block_size:12 * block_size] = gmp

    raw = bytes(image)
    wrapper = b"\x08\x01" + b"\x1a" + encode_varint(len(raw)) + raw
    return raw, wrapper
```

- [ ] **Step 2: Write failing block-size, FAT, section, wrapper, and abort tests**

```python
# tests/test_deep_mine_dskimg_inventory.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord
from ai_caddie.research.deep_mine.parsers.dskimg import inventory_dskimg, unwrap_coursedata
from ai_caddie.research.deep_mine.parsers.dskimg_header_facts import DskImgHeaderFactsRegistry
from ai_caddie.research.deep_mine.parsers.gmp_descriptors import GmpVariantDescriptorRegistry
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry
from tests.deep_mine_fixture_builders import build_synthetic_dskimg


class DskImgInventoryTests(unittest.TestCase):
    def descriptors(self) -> GmpVariantDescriptorRegistry:
        return GmpVariantDescriptorRegistry.from_path(
            Path("tests/fixtures/research/synthetic_gmp_variant_descriptor.json")
        )

    def header_facts(self) -> DskImgHeaderFactsRegistry:
        return DskImgHeaderFactsRegistry.from_path(
            Path("tests/fixtures/research/synthetic_dskimg_header_facts.json")
        )

    def test_enumerates_block_size_fat_chain_subfile_and_all_gmp_sections(self) -> None:
        raw, _wrapper = build_synthetic_dskimg()
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"test-fixture": b"a" * 32}))
            ref = cas.put_bytes("test-fixture", "raw-entity", raw)
            domain = ByteDomain("img-domain", ref, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "dskimg"); ledger.add_node(root)
            result = inventory_dskimg(
                data=raw, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="test-fixture", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="dskimg-inventory", decoder_version="1", build_hash="dskimg-build",
                descriptors=self.descriptors(), header_facts=self.header_facts(),
            )
            self.assertEqual(result.block_size, 512)
            self.assertEqual(result.img_header_variant, "synthetic-classic")
            self.assertEqual(result.subfiles[0].name, "COURSE.GMP")
            self.assertEqual(result.subfiles[0].blocks, (10, 11))
            self.assertEqual(result.subfiles[0].gmp_header_length, 0x31)
            self.assertEqual([section.name for section in result.subfiles[0].sections], ["HEADER", "TRE", "RGN", "LBL", "DEM"])
            self.assertEqual(len(result.subfiles[0].section_domain_ids), 4)
            for section_domain_id in result.subfiles[0].section_domain_ids:
                section_root = next(
                    node for node in ledger.nodes.values()
                    if node.byte_domain_id == section_domain_id
                    and node.parent_node_id is None
                )
                self.assertTrue(
                    ledger.prove_closure(section_domain_id, section_root.node_id).complete
                )
            self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
            gmp_domain = ledger.domains[result.subfiles[0].byte_domain_id]
            gmp_root = next(node for node in ledger.nodes.values() if node.byte_domain_id == gmp_domain.domain_id and node.parent_node_id is None)
            self.assertTrue(ledger.prove_closure(gmp_domain.domain_id, gmp_root.node_id).complete)

    def test_outer_protobuf_field_three_becomes_a_new_dskimg_byte_domain(self) -> None:
        raw, wrapper = build_synthetic_dskimg()
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"test-fixture": b"a" * 32}))
            wrapper_ref = cas.put_bytes("test-fixture", "raw-entity", wrapper)
            derived = unwrap_coursedata(
                wrapper, cas=cas, storage_domain_id="test-fixture", parent_ref=wrapper_ref,
                decoder_version="protobuf-wire-1", build_hash="wire-build",
            )
            self.assertEqual(derived.ref.byte_domain, "dskimg-image")
            self.assertEqual(cas.read_bytes("test-fixture", derived.ref), raw)

    def test_invalid_block_pointer_accounts_the_remaining_bytes_as_malformed(self) -> None:
        raw, _wrapper = build_synthetic_dskimg(invalid_block=True)
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"test-fixture": b"a" * 32}))
            ref = cas.put_bytes("test-fixture", "raw-entity", raw)
            domain = ByteDomain("bad-img", ref, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "dskimg"); ledger.add_node(root)
            result = inventory_dskimg(
                data=raw, domain=domain, root=root, ledger=ledger, unknowns=UnknownRegistry(),
                cas=cas, storage_domain_id="test-fixture", observed_at="2026-07-18T10:00:00.000Z",
                decoder_id="dskimg-inventory", decoder_version="1", build_hash="dskimg-build",
                descriptors=self.descriptors(), header_facts=self.header_facts(),
            )
            self.assertIsNotNone(result.error)
            self.assertTrue(ledger.prove_closure(domain.domain_id, root.node_id).complete)
```

- [ ] **Step 3: Run tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_dskimg_inventory -v`

Expected: FAIL importing `inventory_dskimg`.

- [ ] **Step 4: Implement header/FAT/block-chain parsing and coursedata unwrap**

```python
# ai_caddie/research/deep_mine/parsers/dskimg.py
from __future__ import annotations

from dataclasses import dataclass
import struct

from ai_caddie.course_data.cas import CASRef, EncryptedCAS
from ai_caddie.course_data.providers.protobuf_wire import walk_occurrences

from ..ir import IRAtom, LosslessIR
from ..ledger import NodeLedger
from ..models import ByteDomain, NodeRecord, NodeStatus
from ..provenance import DerivedArtifact, put_derived
from ..unknowns import UnknownEvidence, UnknownRegistry
from .dskimg_header_facts import DskImgHeaderFactsRegistry
from .gmp import inventory_gmp
from .gmp_descriptors import GmpVariantDescriptorRegistry


class DskImgError(ValueError):
    def __init__(self, message: str, offset: int) -> None:
        super().__init__(f"{message} at offset {offset}")
        self.offset = offset


@dataclass(frozen=True)
class DskSection:
    name: str
    offset: int
    length: int
    status: str


@dataclass(frozen=True)
class DskSubfile:
    name: str
    size: int
    blocks: tuple[int, ...]
    artifact: DerivedArtifact
    byte_domain_id: str
    sections: tuple[DskSection, ...]
    section_domain_ids: tuple[str, ...]
    gmp_header_length: int | None
    gmp_descriptor_id: str | None


@dataclass(frozen=True)
class DskImgInventory:
    ir: LosslessIR
    block_size: int
    img_header_variant: str
    header_fact_hash: str
    subfiles: tuple[DskSubfile, ...]
    structural_tokens: tuple[str, ...]
    numeric_values: tuple[float | str, ...]
    error: str | None


def _u16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data): raise DskImgError("truncated uint16", offset)
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data): raise DskImgError("truncated uint32", offset)
    return struct.unpack_from("<I", data, offset)[0]


def _block_size(data: bytes) -> int:
    if len(data) < 0x63 or data[0x10:0x16] != b"DSKIMG": raise DskImgError("missing DSKIMG magic", 0x10)
    exponent = data[0x61] + data[0x62]
    if exponent < 9 or exponent > 20: raise DskImgError("invalid block-size exponent", 0x61)
    return 1 << exponent


@dataclass(frozen=True)
class _FatEntry:
    name: str
    size: int
    blocks: tuple[int, ...]
    record_offset: int


def _fat_entries(data: bytes, block_size: int) -> list[_FatEntry]:
    rows: list[_FatEntry] = []
    for offset in range(0x1000, len(data), 0x200):
        if data[offset] != 1:
            continue
        name = data[offset + 1:offset + 9].decode("ascii", "strict").rstrip()
        extension = data[offset + 9:offset + 12].decode("ascii", "strict").rstrip()
        size = _u32(data, offset + 12)
        blocks: list[int] = []
        for pointer_offset in range(offset + 0x20, min(offset + 0x200, len(data)), 2):
            pointer = _u16(data, pointer_offset)
            if pointer == 0xFFFF or (pointer == 0 and blocks): break
            if pointer * block_size >= len(data): raise DskImgError("FAT block pointer leaves image", pointer_offset)
            blocks.append(pointer)
        if not blocks and size: raise DskImgError("non-empty FAT entry has no blocks", offset)
        if len(blocks) * block_size < size: raise DskImgError("FAT block chain is shorter than subfile", offset)
        rows.append(_FatEntry(f"{name}.{extension}" if extension else name, size, tuple(blocks), offset))
    if not rows: raise DskImgError("no DSKIMG FAT entries", 0x1000)
    used = [block for row in rows for block in row.blocks]
    if len(used) != len(set(used)): raise DskImgError("FAT block reused by multiple entries", 0x1000)
    return rows


def _extract(data: bytes, block_size: int, entry: _FatEntry) -> bytes:
    return b"".join(data[block * block_size:(block + 1) * block_size] for block in entry.blocks)[:entry.size]


def unwrap_coursedata(
    data: bytes,
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    parent_ref: CASRef,
    decoder_version: str,
    build_hash: str,
) -> DerivedArtifact:
    fields = [row for row in walk_occurrences(data) if row.field_number == 3 and row.wire_type == 2]
    if len(fields) != 1 or fields[0].value_bytes is None: raise ValueError("coursedata requires exactly one field-3 DSKIMG")
    return put_derived(
        cas=cas, storage_domain_id=storage_domain_id, byte_domain="dskimg-image", data=fields[0].value_bytes,
        parent_refs=(parent_ref,), transform_name="protobuf-field-3", transform_version=decoder_version,
        parameters={"fieldNumber": 3, "occurrenceIndex": fields[0].occurrence_index}, build_hash=build_hash,
    )
```

- [ ] **Step 5: Implement raw-image and per-subfile closure maps**

Append to the same file:

```python
def _gmp_sections(body: bytes) -> list[DskSection]:
    if body[2:12] != b"GARMIN GMP": return [DskSection("OPAQUE", 0, len(body), NodeStatus.OPAQUE_PRESERVED.value)]
    header_length = _u16(body, 0)
    if header_length < 0x31 or header_length > len(body):
        raise DskImgError("unsupported/truncated GMP header length", 0)
    offsets = {
        name: _u32(body, offset)
        for name, offset in (
            ("TRE", 0x19), ("RGN", 0x1D), ("LBL", 0x21),
            ("NET", 0x25), ("NOD", 0x29), ("DEM", 0x2D),
        )
        if offset + 4 <= header_length and _u32(body, offset) != 0
    }
    if not {"TRE", "RGN", "LBL"}.issubset(offsets):
        raise DskImgError("GMP lacks mandatory TRE/RGN/LBL sections", 0x19)
    if any(offset < header_length or offset >= len(body) for offset in offsets.values()): raise DskImgError("GMP section offset leaves subfile", 0x19)
    ordered = sorted((offset, name) for name, offset in offsets.items())
    if len({offset for offset, _name in ordered}) != len(ordered): raise DskImgError("duplicate GMP section offsets", 0x19)
    rows = [DskSection("HEADER", 0, ordered[0][0], NodeStatus.DECODED.value)]
    for index, (offset, name) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else len(body)
        rows.append(DskSection(name, offset, end - offset, NodeStatus.DECODED.value))
    return rows


def _raw_claims(data: bytes, block_size: int, entries: list[_FatEntry]) -> list[tuple[int, int, str, NodeStatus]]:
    first_data = min(block for entry in entries for block in entry.blocks) * block_size
    claims: list[tuple[int, int, str, NodeStatus]] = [
        (0, min(0x1000, len(data)), "dskimg-header", NodeStatus.DECODED),
        (0x1000, first_data, "dskimg-fat", NodeStatus.DECODED),
    ]
    for entry in entries:
        remaining = entry.size
        for index, block in enumerate(entry.blocks):
            start = block * block_size
            decoded = min(block_size, remaining)
            if decoded:
                claims.append((start, start + decoded, f"dskimg-block:{entry.name}#{index}", NodeStatus.DECODED))
            if decoded < block_size:
                claims.append((start + decoded, start + block_size, f"dskimg-block-padding:{entry.name}#{index}", NodeStatus.PADDING))
            remaining -= decoded
    return claims


def _partition(size: int, claims: list[tuple[int, int, str, NodeStatus]]) -> list[tuple[int, int, str, NodeStatus]]:
    rows: list[tuple[int, int, str, NodeStatus]] = []
    cursor = 0
    for start, end, kind, status in sorted(claims):
        if start < cursor: raise DskImgError("DSKIMG accounting overlap", start)
        if start > cursor: rows.append((cursor, start, "dskimg-unreferenced", NodeStatus.OPAQUE_PRESERVED))
        rows.append((start, end, kind, status)); cursor = end
    if cursor < size: rows.append((cursor, size, "dskimg-unreferenced", NodeStatus.OPAQUE_PRESERVED))
    return rows


def inventory_dskimg(
    *,
    data: bytes,
    domain: ByteDomain,
    root: NodeRecord,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    cas: EncryptedCAS,
    storage_domain_id: str,
    observed_at: str,
    decoder_id: str,
    decoder_version: str,
    build_hash: str,
    descriptors: GmpVariantDescriptorRegistry,
    header_facts: DskImgHeaderFactsRegistry,
) -> DskImgInventory:
    atoms: list[IRAtom] = []
    try:
        header_fact = header_facts.match(data=data, storage_domain_id=storage_domain_id)
        block_size = _block_size(data)
        fat_entries = _fat_entries(data, block_size)
        subfiles: list[DskSubfile] = []
        for entry in fat_entries:
            body = _extract(data, block_size, entry)
            artifact = put_derived(
                cas=cas, storage_domain_id=storage_domain_id, byte_domain="dskimg-subfile", data=body,
                parent_refs=(domain.cas_ref,), transform_name="dskimg-block-chain", transform_version=decoder_version,
                parameters={"name": entry.name, "blocks": list(entry.blocks), "size": entry.size}, build_hash=build_hash,
            )
            child_domain = ByteDomain.create(
                artifact.ref,
                parent_domain_id=domain.domain_id,
                transform_id=artifact.artifact_id,
            )
            ledger.add_domain(child_domain)
            child_root = NodeRecord.root(child_domain.domain_id, child_domain.size, f"dskimg-subfile:{entry.name}")
            ledger.add_node(child_root)
            sections = _gmp_sections(body) if entry.name.endswith(".GMP") else [DskSection("OPAQUE", 0, len(body), NodeStatus.OPAQUE_PRESERVED.value)]
            for index, section in enumerate(sections):
                status = NodeStatus(section.status)
                node = NodeRecord.accounting(child_root, section.offset, section.length, status, f"dskimg-section:{section.name}", decoder_id, decoder_version, index)
                ledger.add_node(node)
                if status == NodeStatus.OPAQUE_PRESERVED:
                    unknowns.observe(
                        namespace="dskimg", locator=f"{entry.name}/{section.name}", observed_at=observed_at,
                        evidence=UnknownEvidence(artifact.ref.sha256, child_domain.domain_id, section.offset, section.length, "opaque-section", ()), priority="medium",
                    )
            section_domain_ids: tuple[str, ...] = ()
            gmp_header_length: int | None = None
            gmp_descriptor_id: str | None = None
            if entry.name.endswith(".GMP"):
                gmp_header_length = _u16(body, 0)
                gmp_inventory = inventory_gmp(
                    body=body,
                    sections=sections,
                    img_header_variant=header_fact.variant,
                    gmp_header_length=gmp_header_length,
                    parent_domain=child_domain,
                    parent_ref=artifact.ref,
                    ledger=ledger,
                    unknowns=unknowns,
                    cas=cas,
                    storage_domain_id=storage_domain_id,
                    observed_at=observed_at,
                    decoder_version=decoder_version,
                    build_hash=build_hash,
                    descriptors=descriptors,
                )
                section_domain_ids = tuple(
                    row.byte_domain_id for row in gmp_inventory.sections
                )
                gmp_descriptor_id = gmp_inventory.descriptor_id
            subfiles.append(DskSubfile(
                entry.name, entry.size, entry.blocks, artifact,
                child_domain.domain_id, tuple(sections), section_domain_ids,
                gmp_header_length, gmp_descriptor_id,
            ))
        for index, (start, end, kind, status) in enumerate(_partition(len(data), _raw_claims(data, block_size, fat_entries))):
            node = NodeRecord.accounting(root, start, end - start, status, kind, decoder_id, decoder_version, index)
            ledger.add_node(node)
            atoms.append(IRAtom(kind, domain.domain_id, start, end - start, index, True, node.node_id))
        structural = tuple(
            f"{row.name}/blocks{len(row.blocks)}/sections:{','.join(section.name for section in row.sections)}"
            for row in subfiles
        )
        numeric = tuple(float(row.size) for row in subfiles)
        return DskImgInventory(
            LosslessIR(tuple(atoms)), block_size, header_fact.variant,
            header_fact.fact_hash, tuple(subfiles), structural, numeric, None,
        )
    except (DskImgError, UnicodeDecodeError) as exc:
        offset = exc.offset if isinstance(exc, DskImgError) else 0
        offset = max(0, min(offset, len(data)))
        if offset:
            prefix = NodeRecord.accounting(root, 0, offset, NodeStatus.DECODED, "dskimg-prefix", decoder_id, decoder_version, 0)
            ledger.add_node(prefix); atoms.append(IRAtom("dskimg-prefix", domain.domain_id, 0, offset, 0, True, prefix.node_id))
        remainder = NodeRecord.accounting(root, offset, len(data) - offset, NodeStatus.MALFORMED, "dskimg-remainder", decoder_id, decoder_version, 0)
        ledger.add_node(remainder); atoms.append(IRAtom("dskimg-remainder", domain.domain_id, offset, len(data) - offset, 0, True, remainder.node_id))
        unknowns.observe(
            namespace="dskimg", locator=f"parse-abort@{offset}", observed_at=observed_at,
            evidence=UnknownEvidence(domain.cas_ref.sha256, domain.domain_id, offset, len(data) - offset, str(exc), ()), priority="high",
        )
        return DskImgInventory(LosslessIR(tuple(atoms)), 0, "unmatched", "", (), (), (), str(exc))
```

- [ ] **Step 6: Add section ByteDomains, object tables, cross-section references, and variant tests**

`dskimg.py` must never mark an entire recognized TRE/RGN/LBL/DEM section `OPAQUE_PRESERVED`. Each non-empty section is copied byte-for-byte into its own child CAS/`ByteDomain`; its root is partitioned into header, table/directory records, object records, padding, and narrowly scoped unknown records. Unknown opcodes or unsupported header variants remain lossless `UnknownRegistry` entries at their exact offsets, but do not abort sibling sections or the whole image. Zero optional GMP offsets are valid (`DEM/NET/NOD` may be absent); only TRE/RGN/LBL are mandatory for the classic route. GMP header length/version selects the offset layout. A section parser may stop only at its own malformed span, and every section-domain closure proof must still be complete.

Create `ai_caddie/research/deep_mine/parsers/gmp.py` with this public contract:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from ..budget import BudgetMeter, ParserBudget
from ..ledger import NodeLedger
from ..models import ByteDomain
from ..unknowns import UnknownRegistry
from .gmp_descriptors import GmpVariantDescriptorRegistry


@dataclass(frozen=True)
class GmpObject:
    section: str
    object_kind: str
    object_index: int
    offset: int
    length: int
    attributes: Mapping[str, int | float | str | tuple[int, ...]]
    cross_refs: tuple[str, ...]


@dataclass(frozen=True)
class GmpSectionInventory:
    name: str
    artifact_ref: CASRef
    byte_domain_id: str
    header_length: int
    header_variant: str
    descriptor_id: str
    objects: tuple[GmpObject, ...]
    unknown_ids: tuple[str, ...]


@dataclass(frozen=True)
class GmpInventory:
    descriptor_id: str
    sections: tuple[GmpSectionInventory, ...]
    cross_section_edges: tuple[tuple[str, str, str], ...]


def inventory_gmp(
    *,
    body: bytes,
    sections: Sequence[object],
    img_header_variant: str,
    gmp_header_length: int,
    parent_domain: ByteDomain,
    parent_ref: CASRef,
    ledger: NodeLedger,
    unknowns: UnknownRegistry,
    cas: EncryptedCAS,
    storage_domain_id: str,
    observed_at: str,
    decoder_version: str,
    build_hash: str,
    descriptors: GmpVariantDescriptorRegistry,
    budget: ParserBudget = ParserBudget(
        max_input_bytes=64 * 1024 * 1024,
        max_nodes=2_000_000,
        max_depth=8,
        max_output_bytes=128 * 1024 * 1024,
    ),
) -> GmpInventory:
    """Losslessly parse each recognized GMP section into its own child domain."""
```

`inventory_dskimg(...)` receives the same immutable `GmpVariantDescriptorRegistry` from the composition root and passes it to `inventory_gmp`; tests pass the checked-in synthetic registry explicitly. Production has no permissive default registry. A section without an exact descriptor match is fully preserved as a section-local high-priority Unknown and blocks the C11 matrix gate; it is never decoded by guessing.

The private parser family is exact and bounded:

```python
_SECTION_PARSERS = {
    "TRE": _parse_tre,  # header/version, map levels, subdivisions, RGN spans
    "RGN": _parse_rgn,  # point/polyline/polygon records by subdivision
    "LBL": _parse_lbl,  # codepage, label offsets, raw+decoded label text
    "DEM": _parse_dem,  # zoom levels, tile descriptors, quantization, samples
    "NET": _parse_net,  # header/table inventory; unsupported records stay narrow unknowns
    "NOD": _parse_nod,
}
```

Do not encode folklore offsets in Python. `contracts/research/gmp_variant_descriptor_v1.schema.json` is a strict, duplicate-key-rejecting schema for an evidence-bound record grammar. Its exact top-level keys are `schema/descriptorId/evidenceKind/sourceRevisionIds/evidenceRefs/match/sections`. `evidenceKind` is exactly `production_multi_sample | research_only_single_sample | synthetic`. `match` has `imgHeaderVariants/gmpHeaderLengths/sectionSignatures`; a section signature is an exact `{offset,hex}` byte match. Every `production_multi_sample` descriptor in `research/corpus/gmp_variant_descriptors.json` carries at least two distinct authorized `SourceRevision` IDs and at least two retrievable encrypted-CAS evidence refs. A currently single-capture stratum is `research_only_single_sample` and cannot pass C11. `synthetic` is legal only in the checked-in test fixture and never in the production descriptor bundle.

The section grammar is deliberately small and reviewable:

- scalar encodings are exactly `u8/u16le/u24le/u32le/i16le/i24le/i32le`;
- a scalar field is `{name,base,offset,encoding}` where `base` is `section` or `record`;
- a fixed table is `{kind,offsetField,countField,recordLength,fields}`;
- a length-prefixed stream is `{kind,offsetField,endField,lengthOffset,lengthEncoding,kindOffset,kindMap,fields,repeat}`;
- `repeat` is either absent or `{countField,itemEncoding,itemWidth}` and preserves the raw ordered values;
- a string pool is `{offsetField,lengthField,codepageField,terminatorHex}` and always retains raw bytes plus proved decode status;
- a DEM sample plane is `{directory,originEastField,originNorthField,widthField,heightField,spacingField,scaleField,sampleOffsetField,sampleEncoding}`.

`tests/fixtures/research/synthetic_gmp_variant_descriptor.json` binds the exact bytes emitted in Step 1. Its TRE grammar reads the 16-byte header, one `<BBHI>` level record and one `<IiiiiII>` subdivision record. Its RGN grammar reads the 16-byte header and the length-prefixed `<HBBHIIii>` records followed by signed `<hh>` deltas; kind map is `1=point,2=polyline,3=polygon`, and flag bit zero means explicitly closed. Its LBL grammar reads `<4sHHII>` and a NUL-terminated UTF-8 pool. Its DEM grammar reads `<4sHHIII>`, one `<BBHiiHHiiI>` tile descriptor, and exact signed 16-bit quantized samples. `tests/fixtures/research/synthetic_gmp_golden.json` contains the exact expected object attributes, cross-reference edges, record offsets/lengths, closure status, and per-section re-encoded SHA-256 values. This synthetic descriptor is accepted only when `storage_domain_id == "test-fixture"`; production rejects descriptor IDs whose evidence kind is `synthetic`.

Create `gmp_descriptors.py` with these exact public operations:

```python
@dataclass(frozen=True)
class GmpVariantDescriptor:
    descriptor_id: str
    evidence_kind: str
    source_revision_ids: tuple[str, ...]
    evidence_refs: tuple[CASRef, ...]
    match: Mapping[str, object]
    sections: Mapping[str, Mapping[str, object]]

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema": "ai-caddie-gmp-variant-descriptor-v1",
            "evidenceKind": self.evidence_kind,
            "sourceRevisionIds": list(self.source_revision_ids),
            "evidenceRefs": [{
                "storageDomainId": ref.storage_domain_id,
                "byteDomain": ref.byte_domain,
                "sha256": ref.sha256,
                "size": ref.size,
            } for ref in self.evidence_refs],
            "match": self.match,
            "sections": self.sections,
        }


class GmpVariantDescriptorRegistry:
    @property
    def registry_id(self) -> str:
        return typed_id("DeepMineGmpDescriptorRegistry/v1", {
            "descriptorIds": [row.descriptor_id for row in self._descriptors],
        })

    @classmethod
    def from_path(cls, path: Path) -> "GmpVariantDescriptorRegistry":
        raw = path.read_bytes()
        value = strict_json_loads(raw)
        validate_json_schema(value, Path("contracts/research/gmp_variant_descriptor_v1.schema.json"))
        descriptors = tuple(_decode_descriptor(row) for row in value["descriptors"])
        return cls(descriptors)

    def match(
        self,
        *,
        storage_domain_id: str,
        img_header_variant: str,
        gmp_header_length: int,
        section_bytes: Mapping[str, bytes],
    ) -> GmpVariantDescriptor:
        matches = tuple(row for row in self._descriptors if _matches(row, img_header_variant, gmp_header_length, section_bytes))
        if len(matches) != 1:
            raise DescriptorMatchError(f"expected one GMP descriptor, found {len(matches)}")
        selected = matches[0]
        if storage_domain_id == "test-fixture":
            if selected.evidence_kind != "synthetic":
                raise DescriptorMatchError("test-fixture domain requires a synthetic descriptor")
        elif selected.evidence_kind == "synthetic":
            raise DescriptorMatchError("synthetic descriptor is forbidden outside test-fixture")
        return selected
```

The constructor sorts descriptors by `descriptor_id`, rejects duplicate IDs, and verifies the stored order is canonical. `registry_id` therefore commits to the exact descriptor bundle, not only its filename.

`_decode_descriptor` rejects noncanonical descriptor/source/evidence ordering, recomputes `descriptorId` as `DeepMineGmpVariantDescriptor/v1` over exactly `schema/evidenceKind/sourceRevisionIds/evidenceRefs/match/sections`, rejects duplicate field/table names and overlapping fixed fields, and validates every referenced offset/count/end field exists with an integer encoding. It enforces the evidence-count/domain policy before a descriptor enters the registry. `_matches` performs every configured signature check with bounds checks. A zero-match or multiple-match result is not guessed through.

The evidence boundary is executable, not a comment:

```python
_DESCRIPTOR_KEYS = {
    "schema", "descriptorId", "evidenceKind", "sourceRevisionIds",
    "evidenceRefs", "match", "sections",
}
_EVIDENCE_KINDS = {
    "production_multi_sample", "research_only_single_sample", "synthetic",
}


def _decode_descriptor(value: Mapping[str, object]) -> GmpVariantDescriptor:
    if set(value) != _DESCRIPTOR_KEYS:
        raise DescriptorValidationError("GMP descriptor top-level keys are not exact")
    if value["schema"] != "ai-caddie-gmp-variant-descriptor-v1":
        raise DescriptorValidationError("GMP descriptor schema mismatch")
    evidence_kind = require_string(value["evidenceKind"])
    if evidence_kind not in _EVIDENCE_KINDS:
        raise DescriptorValidationError("unknown GMP descriptor evidenceKind")
    source_ids = canonical_unique_strings(value["sourceRevisionIds"])
    refs = canonical_unique_cas_refs(value["evidenceRefs"])
    if evidence_kind == "production_multi_sample" and (len(source_ids) < 2 or len(refs) < 2):
        raise DescriptorValidationError("production descriptor requires multiple samples")
    if evidence_kind == "research_only_single_sample" and len(source_ids) != 1:
        raise DescriptorValidationError("single-sample descriptor requires exactly one source revision")
    if evidence_kind == "synthetic":
        if any(ref.storage_domain_id != "test-fixture" for ref in refs):
            raise DescriptorValidationError("synthetic descriptor evidence must use test-fixture")
    elif any(ref.storage_domain_id == "test-fixture" for ref in refs):
        raise DescriptorValidationError("production evidence cannot use test-fixture")
    match = decode_match(value["match"])
    sections = decode_section_grammars(value["sections"])
    provisional = GmpVariantDescriptor(
        descriptor_id="", evidence_kind=evidence_kind,
        source_revision_ids=source_ids, evidence_refs=refs,
        match=match, sections=sections,
    )
    expected = typed_id("DeepMineGmpVariantDescriptor/v1", provisional.identity_payload())
    if value["descriptorId"] != expected:
        raise DescriptorValidationError("GMP descriptorId mismatch")
    return GmpVariantDescriptor(
        descriptor_id=expected, evidence_kind=evidence_kind,
        source_revision_ids=source_ids, evidence_refs=refs,
        match=match, sections=sections,
    )
```

`require_string`、`canonical_unique_strings`、`canonical_unique_cas_refs`、`decode_match` and `decode_section_grammars` are defined in this file as strict decoders: they reject Booleans-as-integers、duplicates、noncanonical ordering、unknown keys、unsafe integers、overlapping fields/tables and a reference to any scalar name that is not defined in the same section grammar. Mutation tests remove/change `evidenceKind`, downgrade a production descriptor to one sample, swap evidence order, use `synthetic + account-a`, use `production_multi_sample + test-fixture`, change one match byte and reuse the old descriptor ID; every mutation fails before inventory.

Implement the parser mechanics, not only the names:

1. `inventory_gmp` first copies every non-empty section to CAS byte domain `gmp-section-<lower-name>`, creates its child `ByteDomain`, and gives it an independent budget meter. It selects exactly one descriptor from the original GMP header and all present section signatures.
2. `_read_scalar` bounds-checks and returns both numeric value and raw slice. `_parse_fixed_table` proves `offset + count * recordLength <= section.size`; `_parse_length_stream` requires each record length to cover its declared fixed fields and to advance the cursor; `_parse_repeat` proves `count * itemWidth` is inside the record. Every consumed range becomes a `NodeRecord`; gaps become `PADDING` only when all-zero or descriptor-declared padding, otherwise a narrow `OPAQUE_PRESERVED` Unknown.
3. `_parse_tre` creates stable `tre-level:<index>` and `tre-subdivision:<id>` refs, validates unique subdivision IDs and non-overlapping RGN spans, and retains west/south/east/north integers without coordinate conversion.
4. `_parse_rgn` preserves record header, origin, ordered signed delta stream, accumulated integer points, label offset, subdivision ref, raw flags, closure, signed doubled area, and winding. It does not close, reverse, simplify, or round geometry.
5. `_parse_lbl` records the exact codepage declaration and raw string slices. Only a descriptor-declared codepage may decode; undecodable bytes remain raw and create a high-priority Unknown rather than replacement characters.
6. `_parse_dem` records zoom/tile descriptor integers and every quantized sample. Physical elevation is represented as the exact rational pair `(quantized * scaleNumerator, scaleDenominator)` plus datum evidence; no float is stored in research IR.
7. `_parse_net` and `_parse_nod` run their descriptor tables when present. If a recognized descriptor has no grammar for one of these optional sections, only that section is an exact high-priority Unknown; TRE/RGN/LBL/DEM results remain available but the real-matrix row cannot pass.
8. `_resolve_cross_refs` runs after all section parsers: RGN→TRE subdivision, RGN/NET→LBL offset, DEM→TRE coverage. Missing, duplicate, wrong-section, or out-of-range targets create high-priority Unknowns and make the row non-promotable.
9. `_reencode_section` concatenates every decoded node's original raw slice plus preserved padding/unknown slices in offset order and requires byte-for-byte equality and matching SHA-256. This is asserted for every recognized section, not only the parent GMP.

Split the real-corpus matrix into schema and instance. `contracts/research/authorized_garmin_img_matrix_v1.schema.json` is the schema; `research/corpus/authorized_garmin_img_matrix.json` is a non-secret instance that contains no Garmin body bytes. Each row has exact keys:

```json
{
  "rowId": "DeepMineAuthorizedImgMatrixRow/v1 typed ID",
  "ownerAccountId": "owner account",
  "securityDomainId": "encrypted CAS security domain",
  "artifactRef": {"storageDomainId": "domain", "byteDomain": "raw-entity", "sha256": "64 lowercase hex", "size": 1},
  "artifactId": "DeepMineCorpusArtifact/v1 typed ID",
  "sourceManifestId": "SourceManifest/v1 typed ID",
  "sourceRevisionId": "SourceRevision/v1 typed ID",
  "providerConfigurationId": "versioned provider configuration",
  "deviceFamily": "observed family",
  "softwareVersion": "observed version",
  "wrapperKind": "raw-img",
  "imgHeaderVariant": "classic",
  "gmpHeaderLength": 49,
  "descriptorId": "DeepMineGmpVariantDescriptor/v1 typed ID",
  "presentSections": ["TRE", "RGN", "LBL"],
  "labelCodepage": 65001,
  "demPresent": false,
  "expectedSectionSha256": {"TRE": "64 lowercase hex", "RGN": "64 lowercase hex", "LBL": "64 lowercase hex"},
  "expectedClosure": true
}
```

The generator computes `rowId = typed_id("DeepMineAuthorizedImgMatrixRow/v1", identity)` where `identity` contains exactly the 18 explicit registry fields in the order shown above and never contains `rowId`. The descriptor loader computes `descriptorId` from exactly `schema/evidenceKind/sourceRevisionIds/evidenceRefs/match/sections`; the descriptor registry identity contains only canonical `descriptorIds`. Tests compare these payload key sets with C1's explicit registry entries before checking the golden IDs. The C1 golden for the synthetic descriptor is `236f5e3f8bf639da8cb0cb01cef86a323d1a1330d7ef6ef62fcd6888ea28c3d2`; the former ID without `evidenceKind` is rejected as stale.

The instance generator reads C1's authorized `CorpusArtifact` records, joins the exact `SourceManifest` and current `SourceRevision`, and writes canonical rows sorted by `rowId`; it cannot accept free-form `artifactId/sourceManifestId` strings. At replay, `artifactRef.storageDomainId` must equal the row security domain, all CAS identity fields and size are checked before read, and `sourceRevisionId` must resolve back to the exact manifest and provider configuration revision. The required acceptance matrix contains at least: classic GMP with DEM, classic GMP without DEM, NT/header-length variant, two label codepages, both raw IMG and coursedata wrapper, and at least two distinct course packages. Missing strata keep C11 and the Plan 3 exit gate incomplete.

`tests/test_deep_mine_gmp_objects.py` must contain concrete assertions for all of the following (use the Step 1 builder and the checked-in golden JSON; do not use empty test bodies):

- all present sections have distinct child domains and complete closure proofs;
- TRE level/subdivision values equal the golden values and its RGN span covers exactly the three fixture records;
- RGN emits one point, one polyline, one closed polygon, resolves both LBL offsets, preserves every delta, and re-encodes to the golden section hashes;
- an unproved LBL codepage yields raw bytes plus a high-priority Unknown and no decoded text;
- DEM yields the exact four quantized samples `(100,101,102,103)`, descriptor geometry, rational scale, and golden hash;
- a generated no-DEM variant and a generated alternate-header variant still parse mandatory siblings;
- a mutated label offset produces `dangling_cross_section_ref` and makes the row non-promotable;
- a section-local budget fault preserves that section's unconsumed remainder and leaves every section closure complete;
- schema and instance parse separately, every real row resolves EncryptedCAS + SourceManifest + SourceRevision, all required strata are covered, and every present section matches its recorded SHA-256.

- [ ] **Step 7: Run tests and the legacy oracle import guard**

Run:

```bash
uv run python -m unittest tests.test_deep_mine_dskimg_inventory -v
uv run python -m unittest tests.test_deep_mine_gmp_objects -v
uv run python -m unittest tests.test_deep_mine_corpus -v
uv run python -m ai_caddie.research.deep_mine.verify_img_matrix --matrix research/corpus/authorized_garmin_img_matrix.json --descriptors research/corpus/gmp_variant_descriptors.json
uv run python - <<'PY'
from pathlib import Path
text = Path('ai_caddie/research/deep_mine/parsers/dskimg.py').read_text()
for forbidden in ('tools.courseview.parse_courseview', 'DumpMkgmapCourseView', 'DumpCourseView'):
    assert forbidden not in text, forbidden
print('legacy-oracle-import-guard: PASS')
PY
```

Expected: all three unit suites PASS, including the explicit `DeepMineGmpVariantDescriptor/v1`, `DeepMineGmpDescriptorRegistry/v1`, and `DeepMineAuthorizedImgMatrixRow/v1` registry/schema identities; `verify-img-matrix` prints `rows>=6 strata=complete section_roundtrip=complete`, and the guard prints `legacy-oracle-import-guard: PASS`; malformed block chains retain a complete root-domain closure proof; every present GMP section has a child-domain closure proof and object-level inventory; optional-section/header variants do not abort the package. If authorized CAS credentials or any required stratum are absent, the command exits nonzero with `deep_mine_incomplete`; this is a failed gate, never a skipped test.

- [ ] **Step 8: Commit C11**

```bash
git add tests/deep_mine_fixture_builders.py ai_caddie/research/deep_mine/parsers/dskimg.py ai_caddie/research/deep_mine/parsers/dskimg_header_facts.py ai_caddie/research/deep_mine/parsers/gmp.py ai_caddie/research/deep_mine/parsers/gmp_descriptors.py ai_caddie/research/deep_mine/verify_img_matrix.py contracts/canonical/deep_mine_v1.schema.json contracts/canonical/canonical_object_registry.json contracts/research/gmp_variant_descriptor_v1.schema.json contracts/research/dskimg_header_facts_v1.schema.json contracts/research/authorized_garmin_img_matrix_v1.schema.json research/corpus/gmp_variant_descriptors.json research/corpus/dskimg_header_facts.json research/corpus/authorized_garmin_img_matrix.json tests/fixtures/research/synthetic_gmp_variant_descriptor.json tests/fixtures/research/synthetic_dskimg_header_facts.json tests/fixtures/research/synthetic_gmp_golden.json tests/test_deep_mine_dskimg_inventory.py tests/test_deep_mine_gmp_objects.py
git commit -m "feat(research): recursively inventory garmin img objects"
```

### Task 12: C12 — Fingerprint content, structure, and distributions and auto-register diffs

**Files:**
- Create: `ai_caddie/research/deep_mine/fingerprint.py`
- Create: `ai_caddie/research/deep_mine/diff.py`
- Create: `tests/test_deep_mine_fingerprint_diff.py`

- [ ] **Step 1: Write failing fingerprint, persistence, and automatic-diff tests**

```python
# tests/test_deep_mine_fingerprint_diff.py
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from ai_caddie.course_data.cas import CASRef, EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.diff import diff_fingerprints, register_first_seen_fingerprint
from ai_caddie.research.deep_mine.fingerprint import build_fingerprint, persist_fingerprint
from ai_caddie.research.deep_mine.models import ByteDomain
from ai_caddie.research.deep_mine.unknowns import UnknownRegistry


def make_domain(name: str, data: bytes) -> ByteDomain:
    return ByteDomain(
        name,
        CASRef("account-a", "raw-entity", hashlib.sha256(data).hexdigest(), len(data)),
        None,
        None,
    )


class FingerprintDiffTests(unittest.TestCase):
    def test_content_structure_and_distribution_have_separate_stable_hashes(self) -> None:
        data = b"artifact-v1"
        first = build_fingerprint(
            artifact_id="artifact-1",
            schema_family="fixture-schema",
            domain=make_domain("domain-1", data),
            data=data,
            structural_tokens=("field/a/occ0", "field/a/occ1", "field/b/occ0"),
            numeric_series={"field/a": (1.0, 2.0, 3.0), "json-exact": ("-0", "1e400")},
        )
        second = build_fingerprint(
            artifact_id="artifact-1",
            schema_family="fixture-schema",
            domain=make_domain("domain-1", data),
            data=data,
            structural_tokens=("field/a/occ0", "field/a/occ1", "field/b/occ0"),
            numeric_series={"field/a": (1.0, 2.0, 3.0), "json-exact": ("-0", "1e400")},
        )
        self.assertEqual(first, second)
        self.assertEqual(first.content_fingerprint, hashlib.sha256(data).hexdigest())
        self.assertEqual(dict(first.structural_counts), {"field/a/occ*": 2, "field/b/occ*": 1})
        summaries = {summary.series: summary for summary in first.distribution_summaries}
        self.assertEqual(summaries["field/a"].count, 3)
        self.assertEqual(summaries["json-exact"].count, 2)
        unknowns = UnknownRegistry()
        unknown_id = register_first_seen_fingerprint(
            first,
            evidence_domain=make_domain("domain-1", data),
            unknowns=unknowns,
            observed_at="2026-07-18T10:00:00.000Z",
        )
        self.assertEqual(unknowns.get(unknown_id).locator, f"fixture-schema/structural-fingerprint/{first.structural_fingerprint}")

    def test_added_removed_cardinality_distribution_and_new_structure_register_unknowns(self) -> None:
        before_data = b"before"
        after_data = b"after!"
        before = build_fingerprint(
            artifact_id="artifact-before",
            schema_family="fixture-schema",
            domain=make_domain("before-domain", before_data),
            data=before_data,
            structural_tokens=("field/a/occ0", "field/a/occ1", "field/removed/occ0"),
            numeric_series={"field/a": (1.0, 2.0)},
        )
        after_domain = make_domain("after-domain", after_data)
        after = build_fingerprint(
            artifact_id="artifact-after",
            schema_family="fixture-schema",
            domain=after_domain,
            data=after_data,
            structural_tokens=("field/a/occ0", "field/added/occ0"),
            numeric_series={"field/a": (10.0, 20.0)},
        )
        unknowns = UnknownRegistry()
        result = diff_fingerprints(
            before,
            after,
            evidence_domain=after_domain,
            unknowns=unknowns,
            observed_at="2026-07-18T10:00:00.000Z",
        )
        self.assertEqual(
            {change.kind for change in result.changes},
            {"structural_fingerprint", "added", "removed", "cardinality", "distribution"},
        )
        self.assertEqual(set(result.unknown_ids), {record.unknown_id for record in unknowns.records()})
        self.assertTrue(any("structural-fingerprint" in record.locator for record in unknowns.records()))

    def test_fingerprint_bytes_use_shared_cas_and_parent_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            raw = b"raw"
            ref = cas.put_bytes("account-a", "raw-entity", raw)
            domain = ByteDomain("domain-1", ref, None, None)
            record = build_fingerprint(
                artifact_id="artifact-1",
                schema_family="fixture-schema",
                domain=domain,
                data=raw,
                structural_tokens=("raw",),
                numeric_series={},
            )
            artifact = persist_fingerprint(
                record,
                cas=cas,
                storage_domain_id="account-a",
                parent_ref=ref,
                decoder_version="fingerprint-1",
                build_hash="fingerprint-build-1",
            )
            self.assertEqual(artifact.ref.byte_domain, "deep-mine-fingerprint")
            self.assertEqual(artifact.parent_refs, (ref,))
            self.assertIn(record.fingerprint_id.encode(), cas.read_bytes("account-a", artifact.ref))
```

- [ ] **Step 2: Run the tests and verify the modules are absent**

Run: `uv run python -m unittest tests.test_deep_mine_fingerprint_diff -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.fingerprint`.

- [ ] **Step 3: Implement deterministic content, structural, and distribution fingerprints**

```python
# ai_caddie/research/deep_mine/fingerprint.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import math
import re
from typing import Iterable, Mapping

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from .models import ByteDomain
from .provenance import DerivedArtifact, put_derived


_JSON_KEY_OCCURRENCE = re.compile(r"(:key)#\d+")


def _structural_key(token: str) -> str:
    normalized = re.sub(r"/occ\d+", "/occ*", token)
    normalized = re.sub(r"#occ\d+", "#occ*", normalized)
    return _JSON_KEY_OCCURRENCE.sub(r"\1#*", normalized)


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _scalar(value: float | str) -> tuple[Decimal, str]:
    if isinstance(value, str):
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"invalid exact numeric lexeme: {value}") from exc
        if not number.is_finite():
            raise ValueError("numeric lexeme must be finite")
        return number, f"decimal:{value}"
    number = float(value)
    if not math.isfinite(number) or (number == 0.0 and math.copysign(1.0, number) < 0):
        raise ValueError("binary numeric values must be finite and cannot be negative zero")
    return Decimal.from_float(number), f"binary64:{number.hex()}"


@dataclass(frozen=True)
class DistributionSummary:
    series: str
    count: int
    minimum_encoded: str | None
    maximum_encoded: str | None
    median_encoded: str | None
    p95_encoded: str | None
    values_sha256: str

    def canonical(self) -> dict[str, object]:
        return {
            "series": self.series,
            "count": self.count,
            "minimumEncoded": self.minimum_encoded,
            "maximumEncoded": self.maximum_encoded,
            "medianEncoded": self.median_encoded,
            "p95Encoded": self.p95_encoded,
            "valuesSha256": self.values_sha256,
        }


def _summarize(series: str, values: Iterable[float | str]) -> DistributionSummary:
    ordered_pairs = sorted((_scalar(value) for value in values), key=lambda item: (item[0], item[1]))
    ordered = [encoded for _number, encoded in ordered_pairs]
    if not ordered:
        return DistributionSummary(series, 0, None, None, None, None, _digest([]))
    median_index = (len(ordered) - 1) // 2
    p95_index = ((len(ordered) - 1) * 95) // 100
    return DistributionSummary(
        series,
        len(ordered),
        ordered[0],
        ordered[-1],
        ordered[median_index],
        ordered[p95_index],
        _digest(ordered),
    )


@dataclass(frozen=True)
class ArtifactFingerprint:
    fingerprint_id: str
    artifact_id: str
    schema_family: str
    byte_domain_id: str
    byte_length: int
    content_fingerprint: str
    structural_fingerprint: str
    distribution_fingerprint: str
    structural_tokens: tuple[str, ...]
    structural_counts: tuple[tuple[str, int], ...]
    distribution_summaries: tuple[DistributionSummary, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "fingerprintId": self.fingerprint_id,
            "artifactId": self.artifact_id,
            "schemaFamily": self.schema_family,
            "byteDomainId": self.byte_domain_id,
            "byteLength": str(self.byte_length),
            "contentFingerprint": self.content_fingerprint,
            "structuralFingerprint": self.structural_fingerprint,
            "distributionFingerprint": self.distribution_fingerprint,
            "structuralTokens": list(self.structural_tokens),
            "structuralCounts": [{"token": token, "count": count} for token, count in self.structural_counts],
            "distributionSummaries": [summary.canonical() for summary in self.distribution_summaries],
        }


def build_fingerprint(
    *,
    artifact_id: str,
    schema_family: str,
    domain: ByteDomain,
    data: bytes,
    structural_tokens: Iterable[str],
    numeric_series: Mapping[str, Iterable[float | str]],
) -> ArtifactFingerprint:
    content = hashlib.sha256(data).hexdigest()
    if content != domain.cas_ref.sha256 or len(data) != domain.size:
        raise ValueError("fingerprint input does not match ByteDomain CASRef")
    normalized = tuple(_structural_key(token) for token in structural_tokens)
    counts = tuple(sorted(Counter(normalized).items()))
    summaries = tuple(_summarize(name, numeric_series[name]) for name in sorted(numeric_series))
    structural = _digest({
        "orderedTokens": list(normalized),
        "counts": [{"token": token, "count": count} for token, count in counts],
    })
    distribution = _digest([summary.canonical() for summary in summaries])
    identity = {
        "artifactId": artifact_id,
        "schemaFamily": schema_family,
        "byteDomainId": domain.domain_id,
        "byteLength": str(len(data)),
        "contentFingerprint": content,
        "structuralFingerprint": structural,
        "distributionFingerprint": distribution,
    }
    return ArtifactFingerprint(
        typed_id("DeepMineFingerprint/v1", identity),
        artifact_id,
        schema_family,
        domain.domain_id,
        len(data),
        content,
        structural,
        distribution,
        normalized,
        counts,
        summaries,
    )
```

- [ ] **Step 4: Persist canonical fingerprint bytes through the shared CAS**

Append to `ai_caddie/research/deep_mine/fingerprint.py`:

```python
def persist_fingerprint(
    record: ArtifactFingerprint,
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    parent_ref: CASRef,
    decoder_version: str,
    build_hash: str,
) -> DerivedArtifact:
    return put_derived(
        cas=cas,
        storage_domain_id=storage_domain_id,
        byte_domain="deep-mine-fingerprint",
        data=canonical_json_bytes(record.canonical()),
        parent_refs=(parent_ref,),
        transform_name="deep-mine-fingerprint",
        transform_version=decoder_version,
        parameters={"fingerprintId": record.fingerprint_id, "schemaFamily": record.schema_family},
        build_hash=build_hash,
    )
```

- [ ] **Step 5: Implement diffs that register every structural and distribution change**

```python
# ai_caddie/research/deep_mine/diff.py
from __future__ import annotations

from dataclasses import dataclass

from .fingerprint import ArtifactFingerprint, DistributionSummary
from .models import ByteDomain
from .unknowns import UnknownEvidence, UnknownRegistry


@dataclass(frozen=True)
class FingerprintChange:
    kind: str
    locator: str
    before: str | None
    after: str | None
    unknown_id: str

    def canonical(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "locator": self.locator,
            "before": self.before,
            "after": self.after,
            "unknownId": self.unknown_id,
        }


@dataclass(frozen=True)
class FingerprintDiff:
    before_fingerprint_id: str
    after_fingerprint_id: str
    changes: tuple[FingerprintChange, ...]
    unknown_ids: tuple[str, ...]


def _summary_map(record: ArtifactFingerprint) -> dict[str, DistributionSummary]:
    return {summary.series: summary for summary in record.distribution_summaries}


def register_first_seen_fingerprint(
    fingerprint: ArtifactFingerprint,
    *,
    evidence_domain: ByteDomain,
    unknowns: UnknownRegistry,
    observed_at: str,
) -> str:
    if fingerprint.byte_domain_id != evidence_domain.domain_id:
        raise ValueError("structural fingerprint evidence must use its own ByteDomain")
    record = unknowns.observe(
        namespace="fingerprint",
        locator=f"{fingerprint.schema_family}/structural-fingerprint/{fingerprint.structural_fingerprint}",
        observed_at=observed_at,
        evidence=UnknownEvidence(
            evidence_domain.cas_ref.sha256,
            evidence_domain.domain_id,
            0,
            evidence_domain.size,
            "first-seen-structural-fingerprint",
            (fingerprint.fingerprint_id,),
        ),
        priority="medium",
    )
    return record.unknown_id


def diff_fingerprints(
    before: ArtifactFingerprint,
    after: ArtifactFingerprint,
    *,
    evidence_domain: ByteDomain,
    unknowns: UnknownRegistry,
    observed_at: str,
) -> FingerprintDiff:
    if before.schema_family != after.schema_family:
        raise ValueError("cannot diff fingerprints from different schema families")
    if after.byte_domain_id != evidence_domain.domain_id:
        raise ValueError("diff evidence must use the after ByteDomain")
    changes: list[FingerprintChange] = []

    def register(kind: str, locator: str, old: str | None, new: str | None, priority: str) -> None:
        record = unknowns.observe(
            namespace="fingerprint",
            locator=f"{after.schema_family}/{locator}",
            observed_at=observed_at,
            evidence=UnknownEvidence(
                evidence_domain.cas_ref.sha256,
                evidence_domain.domain_id,
                0,
                evidence_domain.size,
                f"{kind}:{old or '<absent>'}->{new or '<absent>'}",
                (before.fingerprint_id, after.fingerprint_id),
            ),
            priority=priority,
        )
        changes.append(FingerprintChange(kind, locator, old, new, record.unknown_id))

    if before.structural_fingerprint != after.structural_fingerprint:
        register(
            "structural_fingerprint",
            f"structural-fingerprint/{after.structural_fingerprint}",
            before.structural_fingerprint,
            after.structural_fingerprint,
            "medium",
        )

    before_counts = dict(before.structural_counts)
    after_counts = dict(after.structural_counts)
    for token in sorted(before_counts.keys() | after_counts.keys()):
        old = before_counts.get(token, 0)
        new = after_counts.get(token, 0)
        if old == 0:
            register("added", f"structure/{token}", None, str(new), "medium")
        elif new == 0:
            register("removed", f"structure/{token}", str(old), None, "high")
        elif old != new:
            register("cardinality", f"structure/{token}", str(old), str(new), "high")

    before_series = _summary_map(before)
    after_series = _summary_map(after)
    for name in sorted(before_series.keys() | after_series.keys()):
        old = before_series.get(name)
        new = after_series.get(name)
        old_hash = old.values_sha256 if old else None
        new_hash = new.values_sha256 if new else None
        if old_hash != new_hash:
            register("distribution", f"distribution/{name}", old_hash, new_hash, "medium")

    ordered = tuple(sorted(changes, key=lambda item: (item.kind, item.locator)))
    return FingerprintDiff(
        before.fingerprint_id,
        after.fingerprint_id,
        ordered,
        tuple(sorted({change.unknown_id for change in ordered})),
    )
```

- [ ] **Step 6: Register the canonical object and run focused regression tests**

Verify C1's exact `DeepMineFingerprint/v1` entry. Identity fields are the artifact/schema/domain identities plus the three hashes; normalized tokens, cardinalities, and distribution summaries remain persisted audit data excluded from the ID.

Run:

```bash
uv run python -m unittest \
  tests.test_deep_mine_fingerprint_diff \
  tests.test_deep_mine_unknown_registry \
  tests.test_deep_mine_protobuf_inventory \
  tests.test_deep_mine_json_inventory \
  tests.test_deep_mine_archive_inventory \
  tests.test_deep_mine_texture_inventory \
  tests.test_deep_mine_draco_bridge \
  tests.test_deep_mine_dskimg_inventory \
  tests.test_deep_mine_gmp_objects -v
```

Expected: all tests PASS; a new structural fingerprint and every added, removed, cardinality, or distribution change create stable Unknown Registry records with whole-artifact hash/range evidence.

- [ ] **Step 7: Commit C12**

```bash
git add ai_caddie/research/deep_mine/fingerprint.py ai_caddie/research/deep_mine/diff.py tests/test_deep_mine_fingerprint_diff.py
git commit -m "feat(research): fingerprint and diff every inventory"
```

### Task 13: C13 — Report multi-axis coverage and enforce the finite-corpus stop rule

**Files:**
- Create: `ai_caddie/research/deep_mine/coverage.py`
- Create: `tests/test_deep_mine_coverage.py`

- [ ] **Step 1: Write failing multi-axis, opaque-separation, persistence, and stop-rule tests**

```python
# tests/test_deep_mine_coverage.py
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from ai_caddie.course_data.cas import CASRef, EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.corpus import CorpusArtifact, FrozenCorpusManifest
from ai_caddie.research.deep_mine.coverage import (
    ExplorationBatch,
    build_coverage,
    can_stop_exploration,
    persist_coverage,
)
from ai_caddie.research.deep_mine.fingerprint import build_fingerprint
from ai_caddie.research.deep_mine.ledger import NodeLedger
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord, NodeStatus
from ai_caddie.research.deep_mine.unknowns import UnknownEvidence, UnknownRegistry, UnknownStatus


def ref(body: bytes, byte_domain: str = "raw-entity") -> CASRef:
    return CASRef("account-a", byte_domain, hashlib.sha256(body).hexdigest(), len(body))


class CoverageTests(unittest.TestCase):
    def test_reports_all_axes_and_never_counts_opaque_as_semantic_understanding(self) -> None:
        first_body = b"abcdefghij"
        second_body = b"12345"
        first_artifact = CorpusArtifact(
            "manifest-1", ref(first_body), "application/octet-stream", "fixture-a", "opaque", "", "schema-a", "1",
            ("region:cn", "holes:9", "terrain:mountain"),
        )
        second_artifact = CorpusArtifact(
            "manifest-2", ref(second_body), "application/octet-stream", "fixture-b", "opaque", "", "schema-b", "1",
            ("region:us", "holes:18", "coast:inland"),
        )
        corpus = FrozenCorpusManifest.create("decoder-set-1", (first_artifact, second_artifact))
        ledger = NodeLedger()
        first_domain = ByteDomain("domain-1", first_artifact.cas_ref, None, None)
        second_domain = ByteDomain("domain-2", second_artifact.cas_ref, None, None)
        ledger.add_domain(first_domain); ledger.add_domain(second_domain)
        first_root = NodeRecord.root(first_domain.domain_id, first_domain.size, "first"); ledger.add_node(first_root)
        second_root = NodeRecord.root(second_domain.domain_id, second_domain.size, "second"); ledger.add_node(second_root)
        ledger.add_node(NodeRecord.accounting(first_root, 0, 4, NodeStatus.DECODED, "known", "fixture", "1", 0))
        ledger.add_node(NodeRecord.accounting(first_root, 4, 6, NodeStatus.OPAQUE_PRESERVED, "opaque", "fixture", "1", 0))
        ledger.add_node(NodeRecord.accounting(second_root, 0, 5, NodeStatus.MALFORMED, "broken", "fixture", "1", 0))
        semantic = NodeRecord(
            "semantic-node", first_domain.domain_id, first_root.node_id, 0, 4, NodeStatus.DECODED,
            "semantic-par", "projector", "1", 0, False, "par=4", "confirmed", ("scorecard-projector",),
        )
        hypothesis = NodeRecord(
            "hypothesis-node", first_domain.domain_id, first_root.node_id, 4, 2, NodeStatus.OPAQUE_PRESERVED,
            "semantic-mask", "projector", "1", 0, False, "normal-map", "0.40", (),
        )
        ledger.add_node(semantic); ledger.add_node(hypothesis)
        unknowns = UnknownRegistry()
        unknowns.observe(
            namespace="fixture", locator="opaque", observed_at="2026-07-18T10:00:00.000Z",
            evidence=UnknownEvidence(first_artifact.cas_ref.sha256, first_domain.domain_id, 4, 6, "opaque", ()),
            priority="medium",
        )
        fingerprints = (
            build_fingerprint(
                artifact_id=first_artifact.artifact_id, schema_family="schema-a", domain=first_domain,
                data=first_body, structural_tokens=("known", "opaque"), numeric_series={},
            ),
            build_fingerprint(
                artifact_id=second_artifact.artifact_id, schema_family="schema-b", domain=second_domain,
                data=second_body, structural_tokens=("broken",), numeric_series={},
            ),
        )
        report = build_coverage(
            corpus=corpus,
            acquired_artifact_ids={first_artifact.artifact_id},
            ledger=ledger,
            root_node_ids={first_domain.domain_id: first_root.node_id, second_domain.domain_id: second_root.node_id},
            unknowns=unknowns,
            fingerprints=fingerprints,
            golden_results={"synthetic": True, "malformed": False},
        )
        self.assertEqual(report.acquisition.expected_artifacts, 2)
        self.assertEqual(report.acquisition.acquired_artifacts, 1)
        self.assertEqual(report.byte_accounting.classified_bytes, 15)
        self.assertEqual(report.syntactic.status_bytes["opaque_preserved"], 6)
        self.assertEqual(report.semantic.confirmed_nodes, 1)
        self.assertEqual(report.semantic.hypothesis_nodes, 1)
        self.assertEqual(report.semantic.opaque_preserved_bytes_excluded, 6)
        self.assertEqual(report.consumer.consumed_nodes, 1)
        self.assertGreater(report.consumer.unconsumed_nodes, 0)
        self.assertEqual(report.errors.malformed_nodes, 1)
        self.assertEqual(report.golden.failed, ("malformed",))
        self.assertNotIn("percentage", str(report.canonical()).lower())

    def test_stop_requires_last_three_batches_of_at_least_25_and_disposed_high_unknowns(self) -> None:
        unknowns = UnknownRegistry()
        record = unknowns.observe(
            namespace="fixture", locator="high", observed_at="2026-07-18T10:00:00.000Z",
            evidence=UnknownEvidence("a" * 64, "domain-1", 0, 1, "new-field", ()), priority="high",
        )
        strata = (
            "region:cn", "version:1", "holes:18", "terrain:flat",
            "coast:inland", "drc-layer:rare", "dskimg-cluster:synthetic-a",
        )
        def clean(name: str, count: int = 25, new: tuple[str, ...] = (), include_high: bool = True) -> ExplorationBatch:
            course_ids = tuple(f"{name}-course-{index}" for index in range(count))
            discoveries = tuple((course_ids[0], fingerprint_id) for fingerprint_id in new) if course_ids else ()
            return ExplorationBatch(
                name, "corpus-1", course_ids, strata, discoveries,
                (record.unknown_id,) if include_high else (),
            )
        def stop(*batches: ExplorationBatch):
            authorized = {course_id for batch in batches for course_id in batch.course_ids}
            return can_stop_exploration(
                batches, unknowns, corpus_id="corpus-1", authorized_course_ids=authorized,
            )
        self.assertFalse(stop(clean("b1"), clean("b2"), clean("b3")).can_stop)
        unknowns.update_status(
            record.unknown_id, UnknownStatus.OBSERVED, hypothesis=None, counterevidence=None,
            next_minimum_evidence="capture normal UI transition", capture_required=True,
        )
        self.assertFalse(stop(
            clean("omitted-1", include_high=False),
            clean("omitted-2", include_high=False),
            clean("omitted-3", include_high=False),
        ).can_stop)
        membership_batches = (clean("membership-1"), clean("membership-2"), clean("membership-3"))
        authorized = {course_id for batch in membership_batches for course_id in batch.course_ids}
        authorized.remove(membership_batches[-1].course_ids[-1])
        self.assertFalse(can_stop_exploration(
            membership_batches, unknowns, corpus_id="corpus-1", authorized_course_ids=authorized,
        ).can_stop)
        self.assertFalse(stop(clean("b1", 24), clean("b2"), clean("b3")).can_stop)
        self.assertFalse(stop(clean("b1"), clean("b2", new=("fp-new",)), clean("b3"), clean("b4")).can_stop)
        decision = stop(clean("b1"), clean("b2", new=("fp-new",)), clean("b3"), clean("b4"), clean("b5"))
        self.assertTrue(decision.can_stop)
        self.assertEqual(decision.qualifying_batch_ids, ("b3", "b4", "b5"))
        self.assertEqual(decision.scope, "finite-frozen-corpus-only")

    def test_coverage_report_is_a_parent_bound_derived_cas_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"account-a": b"a" * 32}))
            parent = cas.put_bytes("account-a", "raw-entity", b"raw")
            artifact = CorpusArtifact("manifest", parent, "application/octet-stream", "fixture", "opaque", "", "fixture", "1", ())
            corpus = FrozenCorpusManifest.create("decoder-set", (artifact,))
            domain = ByteDomain("domain", parent, None, None)
            ledger = NodeLedger(); ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, "raw"); ledger.add_node(root)
            ledger.add_node(NodeRecord.accounting(root, 0, domain.size, NodeStatus.DECODED, "raw", "fixture", "1", 0))
            report = build_coverage(
                corpus=corpus, acquired_artifact_ids={artifact.artifact_id}, ledger=ledger,
                root_node_ids={domain.domain_id: root.node_id}, unknowns=UnknownRegistry(), fingerprints=(), golden_results={},
            )
            stored = persist_coverage(
                report, cas=cas, storage_domain_id="account-a", parent_refs=(parent,),
                decoder_version="coverage-1", build_hash="coverage-build-1",
            )
            self.assertEqual(stored.ref.byte_domain, "deep-mine-coverage")
            self.assertIn(report.report_id.encode(), cas.read_bytes("account-a", stored.ref))
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_coverage -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.coverage`.

- [ ] **Step 3: Implement explicit acquisition, byte, syntax, semantic, strata, fingerprint, golden, consumer, and error axes**

```python
# ai_caddie/research/deep_mine/coverage.py
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from .corpus import FrozenCorpusManifest
from .fingerprint import ArtifactFingerprint
from .ledger import ClosureError, NodeLedger
from .models import NodeStatus
from .provenance import DerivedArtifact, put_derived
from .unknowns import UnknownRegistry, UnknownStatus


@dataclass(frozen=True)
class AcquisitionAxis:
    expected_artifacts: int
    acquired_artifacts: int
    missing_artifact_ids: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "expectedArtifacts": self.expected_artifacts,
            "acquiredArtifacts": self.acquired_artifacts,
            "missingArtifactIds": list(self.missing_artifact_ids),
        }


@dataclass(frozen=True)
class ByteAccountingAxis:
    domain_count: int
    closed_domains: tuple[str, ...]
    open_domains: tuple[str, ...]
    total_bytes: int
    classified_bytes: int

    def canonical(self) -> dict[str, object]:
        return {
            "domainCount": self.domain_count,
            "closedDomains": list(self.closed_domains),
            "openDomains": list(self.open_domains),
            "totalBytes": str(self.total_bytes),
            "classifiedBytes": str(self.classified_bytes),
        }


@dataclass(frozen=True)
class SyntacticAxis:
    status_bytes: dict[str, int]

    def canonical(self) -> dict[str, object]:
        return {"statusBytes": {key: str(value) for key, value in sorted(self.status_bytes.items())}}


@dataclass(frozen=True)
class SemanticAxis:
    confirmed_nodes: int
    hypothesis_nodes: int
    unknown_records: int
    opaque_preserved_bytes_excluded: int

    def canonical(self) -> dict[str, object]:
        return {
            "confirmedNodes": self.confirmed_nodes,
            "hypothesisNodes": self.hypothesis_nodes,
            "unknownRecords": self.unknown_records,
            "opaquePreservedBytesExcluded": str(self.opaque_preserved_bytes_excluded),
        }


@dataclass(frozen=True)
class StrataAxis:
    artifact_counts: dict[str, int]

    def canonical(self) -> dict[str, object]:
        return {"artifactCounts": dict(sorted(self.artifact_counts.items()))}


@dataclass(frozen=True)
class FingerprintAxis:
    fingerprinted_artifacts: int
    unique_content: int
    unique_structural: int
    unique_distribution: int

    def canonical(self) -> dict[str, object]:
        return {
            "fingerprintedArtifacts": self.fingerprinted_artifacts,
            "uniqueContent": self.unique_content,
            "uniqueStructural": self.unique_structural,
            "uniqueDistribution": self.unique_distribution,
        }


@dataclass(frozen=True)
class GoldenAxis:
    passed: tuple[str, ...]
    failed: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {"passed": list(self.passed), "failed": list(self.failed)}


@dataclass(frozen=True)
class ConsumerAxis:
    consumed_nodes: int
    unconsumed_nodes: int
    consumer_ids: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "consumedNodes": self.consumed_nodes,
            "unconsumedNodes": self.unconsumed_nodes,
            "consumerIds": list(self.consumer_ids),
        }


@dataclass(frozen=True)
class ErrorAxis:
    malformed_nodes: int
    budget_exhausted_nodes: int

    def canonical(self) -> dict[str, object]:
        return {"malformedNodes": self.malformed_nodes, "budgetExhaustedNodes": self.budget_exhausted_nodes}


@dataclass(frozen=True)
class CoverageReport:
    report_id: str
    corpus_id: str
    acquisition: AcquisitionAxis
    byte_accounting: ByteAccountingAxis
    syntactic: SyntacticAxis
    semantic: SemanticAxis
    strata: StrataAxis
    fingerprints: FingerprintAxis
    golden: GoldenAxis
    consumer: ConsumerAxis
    errors: ErrorAxis

    def payload(self) -> dict[str, object]:
        return {
            "corpusId": self.corpus_id,
            "acquisition": self.acquisition.canonical(),
            "byteAccounting": self.byte_accounting.canonical(),
            "syntactic": self.syntactic.canonical(),
            "semantic": self.semantic.canonical(),
            "strata": self.strata.canonical(),
            "fingerprints": self.fingerprints.canonical(),
            "golden": self.golden.canonical(),
            "consumer": self.consumer.canonical(),
            "errors": self.errors.canonical(),
        }

    def canonical(self) -> dict[str, object]:
        return {"reportId": self.report_id, **self.payload()}
```

- [ ] **Step 4: Build reports without hiding gaps behind a single percentage**

Append to `ai_caddie/research/deep_mine/coverage.py`:

```python
def build_coverage(
    *,
    corpus: FrozenCorpusManifest,
    acquired_artifact_ids: set[str],
    ledger: NodeLedger,
    root_node_ids: Mapping[str, str],
    unknowns: UnknownRegistry,
    fingerprints: Iterable[ArtifactFingerprint],
    golden_results: Mapping[str, bool],
) -> CoverageReport:
    artifact_ids = {artifact.artifact_id for artifact in corpus.artifacts}
    unexpected = acquired_artifact_ids - artifact_ids
    if unexpected:
        raise ValueError(f"acquisition set contains artifacts outside corpus: {sorted(unexpected)}")
    missing = tuple(sorted(artifact_ids - acquired_artifact_ids))

    status_bytes: dict[str, int] = defaultdict(int)
    closed: list[str] = []
    open_domains: list[str] = []
    classified = 0
    for domain_id, domain in sorted(ledger.domains.items()):
        root_id = root_node_ids.get(domain_id)
        if root_id is None:
            open_domains.append(domain_id)
            continue
        children = ledger.direct_accounting_children(root_id)
        for child in children:
            status_bytes[child.status.value] += child.length
            classified += child.length
        try:
            ledger.prove_closure(domain_id, root_id)
        except (ClosureError, KeyError, ValueError):
            open_domains.append(domain_id)
        else:
            closed.append(domain_id)

    non_root_nodes = [node for node in ledger.nodes.values() if node.parent_node_id is not None]
    confirmed = sum(node.semantic_hypothesis is not None and node.confidence == "confirmed" for node in non_root_nodes)
    hypotheses = sum(node.semantic_hypothesis is not None and node.confidence != "confirmed" for node in non_root_nodes)
    consumed = [node for node in non_root_nodes if node.consumed_by]
    consumer_ids = tuple(sorted({consumer for node in consumed for consumer in node.consumed_by}))
    strata = Counter(stratum for artifact in corpus.artifacts for stratum in set(artifact.strata))
    fingerprint_rows = tuple(fingerprints)
    passed = tuple(sorted(name for name, ok in golden_results.items() if ok))
    failed = tuple(sorted(name for name, ok in golden_results.items() if not ok))

    acquisition = AcquisitionAxis(len(artifact_ids), len(acquired_artifact_ids), missing)
    byte_accounting = ByteAccountingAxis(
        len(ledger.domains), tuple(closed), tuple(open_domains),
        sum(domain.size for domain in ledger.domains.values()), classified,
    )
    syntactic = SyntacticAxis(dict(sorted(status_bytes.items())))
    semantic = SemanticAxis(
        confirmed,
        hypotheses,
        len(unknowns.records()),
        status_bytes.get(NodeStatus.OPAQUE_PRESERVED.value, 0),
    )
    strata_axis = StrataAxis(dict(strata))
    fingerprint_axis = FingerprintAxis(
        len(fingerprint_rows),
        len({row.content_fingerprint for row in fingerprint_rows}),
        len({row.structural_fingerprint for row in fingerprint_rows}),
        len({row.distribution_fingerprint for row in fingerprint_rows}),
    )
    golden = GoldenAxis(passed, failed)
    consumer = ConsumerAxis(len(consumed), len(non_root_nodes) - len(consumed), consumer_ids)
    errors = ErrorAxis(
        sum(node.status == NodeStatus.MALFORMED for node in non_root_nodes),
        sum(node.status == NodeStatus.BUDGET_EXHAUSTED for node in non_root_nodes),
    )
    provisional = CoverageReport(
        "", corpus.corpus_id, acquisition, byte_accounting, syntactic, semantic,
        strata_axis, fingerprint_axis, golden, consumer, errors,
    )
    return CoverageReport(
        typed_id("DeepMineCoverageReport/v1", provisional.payload()),
        corpus.corpus_id,
        acquisition,
        byte_accounting,
        syntactic,
        semantic,
        strata_axis,
        fingerprint_axis,
        golden,
        consumer,
        errors,
    )


def persist_coverage(
    report: CoverageReport,
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    parent_refs: tuple[CASRef, ...],
    decoder_version: str,
    build_hash: str,
) -> DerivedArtifact:
    return put_derived(
        cas=cas,
        storage_domain_id=storage_domain_id,
        byte_domain="deep-mine-coverage",
        data=canonical_json_bytes(report.canonical()),
        parent_refs=parent_refs,
        transform_name="deep-mine-coverage",
        transform_version=decoder_version,
        parameters={"reportId": report.report_id, "corpusId": report.corpus_id},
        build_hash=build_hash,
    )
```

- [ ] **Step 5: Implement the three-consecutive-batch finite-corpus stop decision**

Append to the same file:

```python
@dataclass(frozen=True)
class ExplorationBatch:
    batch_id: str
    corpus_id: str
    course_ids: tuple[str, ...]
    strata: tuple[str, ...]
    new_structural_fingerprints: tuple[tuple[str, str], ...]
    high_priority_unknown_ids: tuple[str, ...]

    @property
    def course_count(self) -> int:
        return len(self.course_ids)


@dataclass(frozen=True)
class StopDecision:
    can_stop: bool
    qualifying_batch_ids: tuple[str, ...]
    reason: str
    scope: str = "finite-frozen-corpus-only"


def _high_unknown_disposed(unknown_id: str, unknowns: UnknownRegistry) -> bool:
    try:
        record = unknowns.get(unknown_id)
    except KeyError:
        return False
    return (
        record.status == UnknownStatus.CONFIRMED
        or record.status == UnknownStatus.DEFERRED
        or record.capture_required
    )


REQUIRED_EXPLORATION_STRATA = (
    "region:", "version:", "holes:", "terrain:", "coast:", "drc-layer:", "dskimg-cluster:",
)


def can_stop_exploration(
    batches: Iterable[ExplorationBatch],
    unknowns: UnknownRegistry,
    *,
    corpus_id: str,
    authorized_course_ids: set[str],
) -> StopDecision:
    ordered = tuple(batches)
    if len({batch.batch_id for batch in ordered}) != len(ordered):
        return StopDecision(False, (), "batch IDs must be unique")
    high_priority_ids = {
        record.unknown_id for record in unknowns.records() if record.priority == "high"
    }
    undisposed = sorted(
        unknown_id for unknown_id in high_priority_ids
        if not _high_unknown_disposed(unknown_id, unknowns)
    )
    if undisposed:
        return StopDecision(
            False,
            (),
            f"high-priority unknowns remain unresolved: {undisposed}",
        )
    qualifying: list[str] = []
    seen_courses: set[str] = set()
    trailing_strata: set[str] = set()
    for batch in reversed(ordered):
        batch_courses = set(batch.course_ids)
        discovery_courses = {course_id for course_id, _fingerprint_id in batch.new_structural_fingerprints}
        qualifies = (
            batch.corpus_id == corpus_id
            and batch.course_count >= 25
            and len(batch_courses) == batch.course_count
            and batch_courses.issubset(authorized_course_ids)
            and not (batch_courses & seen_courses)
            and discovery_courses.issubset(batch_courses)
            and not batch.new_structural_fingerprints
            and set(batch.high_priority_unknown_ids).issuperset(high_priority_ids)
            and all(_high_unknown_disposed(unknown_id, unknowns) for unknown_id in batch.high_priority_unknown_ids)
        )
        if not qualifies:
            break
        seen_courses.update(batch_courses)
        trailing_strata.update(batch.strata)
        qualifying.append(batch.batch_id)
        if len(qualifying) == 3:
            if not all(any(stratum.startswith(prefix) for stratum in trailing_strata) for prefix in REQUIRED_EXPLORATION_STRATA):
                return StopDecision(False, tuple(reversed(qualifying)), "three batches do not cover every required exploration stratum")
            ids = tuple(reversed(qualifying))
            return StopDecision(
                True,
                ids,
                "last three batches each contain at least 25 courses, add no structural fingerprint, and dispose every high-priority unknown",
            )
    return StopDecision(
        False,
        tuple(reversed(qualifying)),
        "need three qualifying consecutive trailing batches; this rule never claims coverage beyond the frozen corpus",
    )
```

- [ ] **Step 6: Register coverage reports and run focused tests**

Verify C1's exact `DeepMineCoverageReport/v1` entry. Its schema anchor exposes all nine axes as siblings and defines no `coveragePercent`, `semanticPercent`, or aggregate success score.

Run:

```bash
uv run python -m unittest \
  tests.test_deep_mine_coverage \
  tests.test_deep_mine_node_ledger \
  tests.test_deep_mine_unknown_registry \
  tests.test_deep_mine_fingerprint_diff -v
```

Expected: all tests PASS; opaque bytes are classified under syntax/byte accounting but excluded from confirmed semantics; only three trailing batches of at least 25 courses with no new structural fingerprints and disposed high-priority unknowns permit the finite-corpus stop decision.

- [ ] **Step 7: Commit C13**

```bash
git add ai_caddie/research/deep_mine/coverage.py tests/test_deep_mine_coverage.py
git commit -m "feat(research): report multi-axis deep mine coverage"
```

### Task 14: C14 — Generate Owner capture requests only for four evidence gaps

**Files:**
- Create: `ai_caddie/research/deep_mine/capture_requests.py`
- Create: `tests/test_deep_mine_capture_requests.py`

- [ ] **Step 1: Write failing allowlist, existing-raw rejection, metadata, redaction, and validator tests**

```python
# tests/test_deep_mine_capture_requests.py
from __future__ import annotations

import hashlib
import unittest

from ai_caddie.research.deep_mine.capture_requests import (
    CaptureContext,
    CaptureGap,
    CaptureGapKind,
    CaptureSubmission,
    generate_capture_request,
    validate_submission,
)
from ai_caddie.research.deep_mine.unknowns import UnknownEvidence, UnknownRegistry


def registry_with_unknown() -> tuple[UnknownRegistry, str]:
    registry = UnknownRegistry()
    record = registry.observe(
        namespace="behavior",
        locator="AdjGreen",
        observed_at="2026-07-18T10:00:00.000Z",
        evidence=UnknownEvidence("a" * 64, "domain-1", 0, 1, "ui-only", ()),
        priority="high",
    )
    return registry, record.unknown_id


def context() -> CaptureContext:
    return CaptureContext(
        device_model="Garmin Approach S70 47mm",
        app_version="20.10",
        locale="en-US",
        gid="31936",
        hole=7,
        window_start="2026-07-18T10:00:00.000Z",
        window_end="2026-07-18T10:05:00.000Z",
    )


class CaptureRequestTests(unittest.TestCase):
    def test_only_four_evidence_gap_kinds_exist(self) -> None:
        self.assertEqual(
            {item.value for item in CaptureGapKind},
            {"raw_body_missing", "ui_network_timing", "missing_region_history_experiment", "runtime_generated"},
        )

    def test_existing_raw_parser_filter_or_semantic_work_never_becomes_owner_capture(self) -> None:
        registry, unknown_id = registry_with_unknown()
        gap = CaptureGap(
            unknown_id,
            CaptureGapKind.RAW_BODY_MISSING,
            "Which response contains AdjGreen?",
            "Open hole 7 and enter Green View.",
            "Open hole 7 and remain on Hole View.",
        )
        for engineering_gap in ("parser_gap", "branch_filtered", "semantic_ambiguity"):
            with self.subTest(engineering_gap=engineering_gap), self.assertRaisesRegex(ValueError, "engineering task"):
                generate_capture_request(
                    gap, context=context(), unknowns=registry,
                    existing_raw_for_unknown=True, engineering_gap=engineering_gap,
                )

    def test_request_binds_full_unknown_controls_context_hash_redaction_and_automatic_validator(self) -> None:
        registry, unknown_id = registry_with_unknown()
        request = generate_capture_request(
            CaptureGap(
                unknown_id,
                CaptureGapKind.UI_NETWORK_TIMING,
                "Which request begins within the Green View transition window?",
                "Enter Green View on hole 7.",
                "Stay on Hole View on hole 7 for the same duration.",
            ),
            context=context(),
            unknowns=registry,
            existing_raw_for_unknown=True,
            engineering_gap=None,
        )
        self.assertEqual(request.unknown_id, unknown_id)
        self.assertEqual(len(request.unknown_id), 64)
        self.assertEqual(request.body_requirement, "complete-untruncated-entity-body")
        self.assertEqual(request.hash_algorithm, "sha256")
        self.assertIn("cookie", request.redaction_rules)
        self.assertEqual(request.destination_queue, "engineering-evidence")
        self.assertEqual(request.optional_pager, "telegram-decision-pager")
        self.assertEqual(request.prohibited_product_surfaces, ("web-inbox", "ios-inbox", "watch-inbox"))
        self.assertTrue(registry.get(unknown_id).capture_required)

        body = b"captured-body"
        valid = CaptureSubmission(
            request_id=request.request_id,
            unknown_id=request.unknown_id,
            body=body,
            body_sha256=hashlib.sha256(body).hexdigest(),
            truncated=False,
            captured_at="2026-07-18T10:02:00.000Z",
            device_model=request.context.device_model,
            app_version=request.context.app_version,
            locale=request.context.locale,
            gid=request.context.gid,
            hole=request.context.hole,
            positive_control_body=b"positive-control-body",
            positive_control_sha256=hashlib.sha256(b"positive-control-body").hexdigest(),
            negative_control_body=b"negative-control-body",
            negative_control_sha256=hashlib.sha256(b"negative-control-body").hexdigest(),
            redacted_fields=request.redaction_rules,
            retained_metadata={"content-type": "application/octet-stream", "request-path": "/normal/user/flow"},
        )
        self.assertTrue(validate_submission(request, valid).valid)
        invalid = CaptureSubmission(
            **{**valid.__dict__, "body_sha256": "0" * 64, "truncated": True},
        )
        result = validate_submission(request, invalid)
        self.assertFalse(result.valid)
        self.assertIn("body is truncated", result.errors)
        self.assertIn("body sha256 mismatch", result.errors)
        reused = CaptureSubmission(**{**valid.__dict__, "request_id": "0" * 64})
        self.assertIn(
            "submission request/Unknown ID binding mismatch",
            validate_submission(request, reused).errors,
        )
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_capture_requests -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.capture_requests`.

- [ ] **Step 3: Implement the four-kind evidence model and fail-closed generator**

```python
# ai_caddie/research/deep_mine/capture_requests.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import re
from urllib.parse import parse_qsl, urlsplit

from ai_caddie.contracts.typed_ids import typed_id

from .unknowns import UnknownRegistry


class CaptureGapKind(StrEnum):
    RAW_BODY_MISSING = "raw_body_missing"
    UI_NETWORK_TIMING = "ui_network_timing"
    MISSING_REGION_HISTORY_EXPERIMENT = "missing_region_history_experiment"
    RUNTIME_GENERATED = "runtime_generated"


REQUIRED_REDACTIONS = (
    "authorization",
    "cookie",
    "csrf",
    "oauth-token",
    "set-cookie",
    "signed-query",
    "zip-key",
)
RFC3339_MILLIS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


@dataclass(frozen=True)
class CaptureContext:
    device_model: str
    app_version: str
    locale: str
    gid: str
    hole: int
    window_start: str
    window_end: str

    def canonical(self) -> dict[str, object]:
        return {
            "deviceModel": self.device_model,
            "appVersion": self.app_version,
            "locale": self.locale,
            "gid": self.gid,
            "hole": self.hole,
            "windowStart": self.window_start,
            "windowEnd": self.window_end,
        }


@dataclass(frozen=True)
class CaptureGap:
    unknown_id: str
    kind: CaptureGapKind
    unique_question: str
    positive_control: str
    negative_control: str


@dataclass(frozen=True)
class CaptureRequest:
    request_id: str
    unknown_id: str
    gap_kind: CaptureGapKind
    unique_question: str
    positive_control: str
    negative_control: str
    context: CaptureContext
    body_requirement: str
    hash_algorithm: str
    redaction_rules: tuple[str, ...]
    automatic_validator: str
    authorized_access_rule: str
    destination_queue: str
    optional_pager: str
    prohibited_product_surfaces: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            "unknownId": self.unknown_id,
            "gapKind": self.gap_kind.value,
            "uniqueQuestion": self.unique_question,
            "positiveControl": self.positive_control,
            "negativeControl": self.negative_control,
            "context": self.context.canonical(),
            "bodyRequirement": self.body_requirement,
            "hashAlgorithm": self.hash_algorithm,
            "redactionRules": list(self.redaction_rules),
            "automaticValidator": self.automatic_validator,
            "authorizedAccessRule": self.authorized_access_rule,
            "destinationQueue": self.destination_queue,
            "optionalPager": self.optional_pager,
            "prohibitedProductSurfaces": list(self.prohibited_product_surfaces),
        }

    def canonical(self) -> dict[str, object]:
        return {"requestId": self.request_id, **self.payload()}


def _validate_context(context: CaptureContext) -> None:
    if not all((context.device_model, context.app_version, context.locale, context.gid)):
        raise ValueError("capture context requires device, version, locale, and gid")
    if context.hole < 1 or context.hole > 18:
        raise ValueError("capture hole must be in 1..18")
    if not RFC3339_MILLIS.fullmatch(context.window_start) or not RFC3339_MILLIS.fullmatch(context.window_end):
        raise ValueError("capture time window must use UTC RFC3339 milliseconds")
    if context.window_start >= context.window_end:
        raise ValueError("capture time window must be increasing RFC3339 values")


def generate_capture_request(
    gap: CaptureGap,
    *,
    context: CaptureContext,
    unknowns: UnknownRegistry,
    existing_raw_for_unknown: bool,
    engineering_gap: str | None,
) -> CaptureRequest:
    record = unknowns.get(gap.unknown_id)
    if record.unknown_id != gap.unknown_id or len(gap.unknown_id) != 64:
        raise ValueError("capture request requires the complete Unknown ID")
    if engineering_gap is not None:
        raise ValueError("existing raw parsing/filtering/semantic work is an engineering task, not an Owner capture")
    if existing_raw_for_unknown and gap.kind != CaptureGapKind.UI_NETWORK_TIMING:
        raise ValueError("existing raw is an engineering task unless UI/network timing correlation is the missing evidence")
    if gap.kind == CaptureGapKind.RAW_BODY_MISSING and existing_raw_for_unknown:
        raise ValueError("raw_body_missing conflicts with existing raw")
    if not gap.unique_question or not gap.positive_control or not gap.negative_control:
        raise ValueError("capture request requires one question and positive/negative controls")
    if gap.positive_control == gap.negative_control:
        raise ValueError("positive and negative controls must differ")
    _validate_context(context)
    provisional = CaptureRequest(
        "",
        gap.unknown_id,
        gap.kind,
        gap.unique_question,
        gap.positive_control,
        gap.negative_control,
        context,
        "complete-untruncated-entity-body",
        "sha256",
        REQUIRED_REDACTIONS,
        "validate_submission/v1",
        "normal-user-authorized-access-only; no authorization bypass",
        "engineering-evidence",
        "telegram-decision-pager",
        ("web-inbox", "ios-inbox", "watch-inbox"),
    )
    request_id = typed_id("DeepMineCaptureRequest/v1", provisional.payload())
    request = CaptureRequest(
        request_id,
        provisional.unknown_id,
        provisional.gap_kind,
        provisional.unique_question,
        provisional.positive_control,
        provisional.negative_control,
        provisional.context,
        provisional.body_requirement,
        provisional.hash_algorithm,
        provisional.redaction_rules,
        provisional.automatic_validator,
        provisional.authorized_access_rule,
        provisional.destination_queue,
        provisional.optional_pager,
        provisional.prohibited_product_surfaces,
    )
    unknowns.update_status(
        record.unknown_id,
        record.status,
        hypothesis=record.hypothesis,
        counterevidence=record.counterevidence,
        next_minimum_evidence=gap.unique_question,
        capture_required=True,
    )
    return request
```

- [ ] **Step 4: Implement the deterministic submission validator**

Append to `ai_caddie/research/deep_mine/capture_requests.py`:

```python
@dataclass(frozen=True)
class CaptureSubmission:
    request_id: str
    unknown_id: str
    body: bytes
    body_sha256: str
    truncated: bool
    captured_at: str
    device_model: str
    app_version: str
    locale: str
    gid: str
    hole: int
    positive_control_body: bytes
    positive_control_sha256: str
    negative_control_body: bytes
    negative_control_sha256: str
    redacted_fields: tuple[str, ...]
    retained_metadata: dict[str, str]


@dataclass(frozen=True)
class CaptureValidation:
    valid: bool
    errors: tuple[str, ...]


def validate_submission(request: CaptureRequest, submission: CaptureSubmission) -> CaptureValidation:
    errors: list[str] = []
    if submission.request_id != request.request_id or submission.unknown_id != request.unknown_id:
        errors.append("submission request/Unknown ID binding mismatch")
    if submission.truncated:
        errors.append("body is truncated")
    if not submission.body:
        errors.append("body is empty")
    if hashlib.sha256(submission.body).hexdigest() != submission.body_sha256:
        errors.append("body sha256 mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", submission.body_sha256):
        errors.append("body sha256 is not lowercase hex")
    expected_context = (
        request.context.device_model,
        request.context.app_version,
        request.context.locale,
        request.context.gid,
        request.context.hole,
    )
    actual_context = (
        submission.device_model,
        submission.app_version,
        submission.locale,
        submission.gid,
        submission.hole,
    )
    if actual_context != expected_context:
        errors.append("device/version/locale/gid/hole context mismatch")
    if not (request.context.window_start <= submission.captured_at <= request.context.window_end):
        errors.append("capture timestamp leaves requested window")
    if not RFC3339_MILLIS.fullmatch(submission.captured_at):
        errors.append("capture timestamp is not UTC RFC3339 milliseconds")
    for label, body, claimed_hash in (
        ("positive", submission.positive_control_body, submission.positive_control_sha256),
        ("negative", submission.negative_control_body, submission.negative_control_sha256),
    ):
        if not body:
            errors.append(f"{label} control body is empty")
        if not re.fullmatch(r"[0-9a-f]{64}", claimed_hash):
            errors.append(f"{label} control hash must be lowercase sha256")
        elif hashlib.sha256(body).hexdigest() != claimed_hash:
            errors.append(f"{label} control sha256 mismatch")
    if submission.positive_control_body == submission.negative_control_body:
        errors.append("positive and negative control bodies must differ")
    if not set(request.redaction_rules).issubset(set(submission.redacted_fields)):
        errors.append("required secret redactions are incomplete")
    forbidden = set(request.redaction_rules)
    retained_keys = {key.lower() for key in submission.retained_metadata}
    if forbidden & retained_keys:
        errors.append("retained metadata contains a forbidden secret field")
    for key, value in submission.retained_metadata.items():
        if "url" in key.lower() or "path" in key.lower():
            query_names = {name.lower() for name, _value in parse_qsl(urlsplit(value).query, keep_blank_values=True)}
            if query_names & forbidden:
                errors.append("retained URL contains a forbidden secret query")
                break
    return CaptureValidation(not errors, tuple(errors))
```

- [ ] **Step 5: Register requests and run focused tests**

Verify C1's exact `DeepMineCaptureRequest/v1` entry. Its identity contains the complete Unknown ID, unique question, controls, device/version/locale/gid/hole/time window, body/hash rules, redaction list, validator, authorization rule, and engineering-only routing.

Run:

```bash
uv run python -m unittest \
  tests.test_deep_mine_capture_requests \
  tests.test_deep_mine_unknown_registry \
  tests.test_deep_mine_coverage -v
```

Expected: all tests PASS; only the four evidence-gap enum values can create requests; parser gaps, filtered branches, and semantic ambiguity with available raw remain engineering work; valid requests carry a complete automatic acceptance contract and never target a product Inbox.

- [ ] **Step 6: Commit C14**

```bash
git add ai_caddie/research/deep_mine/capture_requests.py tests/test_deep_mine_capture_requests.py
git commit -m "feat(research): generate evidence-bound capture requests"
```

### Task 15: C15 — Emit research-only, evidence-bound promotion candidates

**Files:**
- Create: `ai_caddie/research/deep_mine/playable_regions.py`
- Create: `ai_caddie/research/deep_mine/promotion.py`
- Create: `tests/test_deep_mine_promotion.py`

- [ ] **Step 1: Write failing evidence-CAS, revision/global-hole, canonical-set, strict-union, and import-boundary tests**

```python
# tests/test_deep_mine_promotion.py
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from itertools import permutations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.fingerprint import build_fingerprint
from ai_caddie.research.deep_mine.ledger import ClosureProof
from ai_caddie.research.deep_mine.models import ByteDomain, NodeRecord, NodeStatus
from ai_caddie.research.deep_mine.playable_regions import (
    DecodedPlayableRegion,
    DecodedPlayableRegionSource,
    ProjectedPlayableRegionSet,
    project_playable_regions_from_decoded_source,
)
from ai_caddie.research.deep_mine.promotion import (
    _GeometryBudget,
    _MAX_ABS_LOCAL_COORDINATE_M,
    _MAX_GEOMETRY_PAIR_CHECKS,
    _MAX_PLAYABLE_POINTS,
    _MAX_PLAYABLE_POINTS_PER_RING,
    _MAX_PLAYABLE_REGIONS,
    _MAX_PLAYABLE_REGIONS_BODY_BYTES,
    _MAX_PLAYABLE_RINGS,
    _classify_validated_playable_region_point,
    _finite_geometry_number,
    _require_playable_body_budget,
    _require_playable_region_count,
    _require_point_in_envelope,
    _validated_map_geometry_envelope,
    EvidenceCASRef,
    GreenSurfaceEvidence,
    HazardEvidenceRow,
    HazardGuidanceEvidence,
    PlaysLikeEvidence,
    PromotionBinding,
    PromotionCandidate,
    PromotionProductRef,
    SourceInventoryTrust,
    SourceRegionInventoryRow,
    TrustedPromotionCandidateStore,
    build_promotion_candidate,
    classify_playable_region_point,
    freeze_playable_regions_source_inventory,
    persist_promotion_candidate,
    validate_candidate_schema,
    validate_promotion_product_bytes,
    validate_untrusted_promotion_candidate,
)
from ai_caddie.research.deep_mine.unknowns import UnknownEvidence, UnknownRegistry, UnknownStatus


OWNER_ACCOUNT_ID = "account-a"
SECURITY_DOMAIN_ID = "domain-a"
BASE_GEOMETRY_HASH = hashlib.sha256(b"base-geometry").hexdigest()
FORCED_CARRY_ROW_PAYLOAD = {
    "hazardRef": "hazard:forced-carry-7",
    "sourceRevisionId": "source-revision-base",
    "hazardSemanticKind": "forced_carry",
    "routeGeometryHash": BASE_GEOMETRY_HASH,
    "stationingBasis": "tee-origin-route-station-v1",
    "landingWindowHash": BASE_GEOMETRY_HASH,
    "baseGeometryHash": BASE_GEOMETRY_HASH,
    "enterDistanceM": 132.0,
    "clearDistanceM": 150.5,
}
FORCED_CARRY_ROW_EVIDENCE_HASH = typed_id(
    "DeepMineHazardEvidenceMember/v1", FORCED_CARRY_ROW_PAYLOAD,
)
HAZARD_SET_BODY = canonical_json_bytes({
    "schema": "ai-caddie-hazard-set-evidence-v1",
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "routeGeometryHash": BASE_GEOMETRY_HASH,
    "stationingBasis": "tee-origin-route-station-v1",
    "hazards": [{
        "hazardRef": "hazard:forced-carry-7",
        "sourceRevisionId": "source-revision-base",
        "hazardSemanticKind": "forced_carry",
        "routeGeometryHash": BASE_GEOMETRY_HASH,
        "stationingBasis": "tee-origin-route-station-v1",
        "landingWindowHash": BASE_GEOMETRY_HASH,
        "baseGeometryHash": BASE_GEOMETRY_HASH,
        "enterDistanceM": 132.0,
        "clearDistanceM": 150.5,
        "evidenceHash": FORCED_CARRY_ROW_EVIDENCE_HASH,
    }],
})
HAZARD_COVERAGE_BODY = canonical_json_bytes({
    "schema": "ai-caddie-hazard-coverage-evidence-v1",
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "routeGeometryHash": BASE_GEOMETRY_HASH,
    "stationingBasis": "tee-origin-route-station-v1",
    "hazardSetEvidenceHash": hashlib.sha256(HAZARD_SET_BODY).hexdigest(),
    "complete": True,
})
PLAYABLE_REGIONS_REGISTRATION_RESIDUAL_M = 1.2
PLAYABLE_REGIONS_MAXIMUM_REGISTRATION_RESIDUAL_M = 3.0
PLAYABLE_MAP_GEOMETRY_ENVELOPE = {
    "minEastM": -50.0,
    "minNorthM": -50.0,
    "maxEastM": 500.0,
    "maxNorthM": 200.0,
}
PLAYABLE_REGIONS = [
    {
        "regionRef": "region:bunker-1", "lieKind": "bunker",
        "rings": [{
            "ringRef": "ring:bunker-1:outer", "ringRole": "outer",
            "points": [
                {"eastM": 400.0, "northM": 100.0},
                {"eastM": 440.0, "northM": 100.0},
                {"eastM": 440.0, "northM": 130.0},
                {"eastM": 400.0, "northM": 130.0},
                {"eastM": 400.0, "northM": 100.0},
            ],
        }],
        "evidenceRefs": [],
    },
    {
        "regionRef": "region:fairway-1", "lieKind": "fairway",
        "rings": [{
            "ringRef": "ring:fairway-1:outer", "ringRole": "outer",
            "points": [
                {"eastM": 0.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 0.0},
            ],
        }],
        "evidenceRefs": [],
    },
]
PLAYABLE_REGIONS_HASH = hashlib.sha256(
    canonical_json_bytes([
        {
            "regionRef": region["regionRef"],
            "lieKind": region["lieKind"],
            "rings": region["rings"],
        }
        for region in PLAYABLE_REGIONS
    ]),
).hexdigest()
PLAYABLE_SOURCE_REF = CASRef(
    SECURITY_DOMAIN_ID,
    "derived-base-geometry",
    BASE_GEOMETRY_HASH,
    len(b"base-geometry"),
)
PLAYABLE_SOURCE_DOMAIN = ByteDomain.create(
    PLAYABLE_SOURCE_REF, parent_domain_id=None, transform_id=None,
)
PLAYABLE_SOURCE_ROOT = NodeRecord.root(
    PLAYABLE_SOURCE_DOMAIN.domain_id,
    PLAYABLE_SOURCE_DOMAIN.size,
    "source-region-root",
)
PLAYABLE_SOURCE_NODES = (
    NodeRecord.create(
        byte_domain_id=PLAYABLE_SOURCE_DOMAIN.domain_id,
        parent_node_id=PLAYABLE_SOURCE_ROOT.node_id,
        offset=0,
        length=6,
        status=NodeStatus.DECODED,
        node_kind="source-region-object",
        decoder_id="gmp-rgn-source-regions",
        decoder_version="1",
        occurrence_index=0,
        accounting=False,
        semantic_hypothesis="bunker source region",
        confidence="confirmed",
        consumed_by=("playable-source-inventory",),
    ),
    NodeRecord.create(
        byte_domain_id=PLAYABLE_SOURCE_DOMAIN.domain_id,
        parent_node_id=PLAYABLE_SOURCE_ROOT.node_id,
        offset=6,
        length=7,
        status=NodeStatus.DECODED,
        node_kind="source-region-object",
        decoder_id="gmp-rgn-source-regions",
        decoder_version="1",
        occurrence_index=1,
        accounting=False,
        semantic_hypothesis="fairway source region",
        confidence="confirmed",
        consumed_by=("playable-source-inventory",),
    ),
)
PLAYABLE_SOURCE_PROOF_PAYLOAD = {
    "byteDomainId": PLAYABLE_SOURCE_DOMAIN.domain_id,
    "rootNodeId": PLAYABLE_SOURCE_ROOT.node_id,
    "domainSize": str(PLAYABLE_SOURCE_DOMAIN.size),
    "classifiedBytes": str(PLAYABLE_SOURCE_DOMAIN.size),
    "statusBytes": {"decoded": PLAYABLE_SOURCE_DOMAIN.size},
    "complete": True,
}
PLAYABLE_SOURCE_PROOF = ClosureProof(
    typed_id("DeepMineClosureProof/v1", PLAYABLE_SOURCE_PROOF_PAYLOAD),
    PLAYABLE_SOURCE_DOMAIN.domain_id,
    PLAYABLE_SOURCE_ROOT.node_id,
    PLAYABLE_SOURCE_DOMAIN.size,
    PLAYABLE_SOURCE_DOMAIN.size,
    {"decoded": PLAYABLE_SOURCE_DOMAIN.size},
    True,
)
PLAYABLE_SOURCE_FINGERPRINT = build_fingerprint(
    artifact_id="artifact-source-base-geometry",
    schema_family="gmp-rgn-source-regions",
    domain=PLAYABLE_SOURCE_DOMAIN,
    data=b"base-geometry",
    structural_tokens=("rgn", "source-regions"),
    numeric_series={"regionCount": (2.0,)},
)
PLAYABLE_SOURCE_REGIONS = [
    {
        "regionRef": "region:bunker-1",
        "sourceRevisionId": "source-revision-base",
        "sourceObjectRef": "rgn-object:31936-7:bunker-1",
        "sourceNodeIds": [PLAYABLE_SOURCE_NODES[0].node_id],
        "closureProofIds": [PLAYABLE_SOURCE_PROOF.proof_id],
        "fingerprintIds": [PLAYABLE_SOURCE_FINGERPRINT.fingerprint_id],
        "evidenceIds": ["field-check-1"],
    },
    {
        "regionRef": "region:fairway-1",
        "sourceRevisionId": "source-revision-base",
        "sourceObjectRef": "rgn-object:31936-7:fairway-1",
        "sourceNodeIds": [PLAYABLE_SOURCE_NODES[1].node_id],
        "closureProofIds": [PLAYABLE_SOURCE_PROOF.proof_id],
        "fingerprintIds": [PLAYABLE_SOURCE_FINGERPRINT.fingerprint_id],
        "evidenceIds": ["field-check-1"],
    },
]
PLAYABLE_SOURCE_REGION_INVENTORY_HASH = hashlib.sha256(
    canonical_json_bytes(PLAYABLE_SOURCE_REGIONS),
).hexdigest()
PLAYABLE_REGIONS_SOURCE_INVENTORY_BODY = canonical_json_bytes({
    "schema": "ai-caddie-playable-regions-source-inventory-v1",
    "inventoryBuildStage": "source_decode_before_product_projection",
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "mapGeometryHash": BASE_GEOMETRY_HASH,
    "mapGeometryEnvelope": PLAYABLE_MAP_GEOMETRY_ENVELOPE,
    "sourceRegionInventoryHash": PLAYABLE_SOURCE_REGION_INVENTORY_HASH,
    "sourceRegions": PLAYABLE_SOURCE_REGIONS,
    "complete": True,
})
PLAYABLE_REGIONS_SOURCE_INVENTORY_EVIDENCE_HASH = hashlib.sha256(
    PLAYABLE_REGIONS_SOURCE_INVENTORY_BODY,
).hexdigest()
PLAYABLE_SOURCE_ARTIFACT_REF = CASRef(
    SECURITY_DOMAIN_ID,
    "deep-mine-playable-regions-source-inventory-evidence",
    PLAYABLE_REGIONS_SOURCE_INVENTORY_EVIDENCE_HASH,
    len(PLAYABLE_REGIONS_SOURCE_INVENTORY_BODY),
)
PLAYABLE_SOURCE_PARENT_REF = {
    "storageDomainId": PLAYABLE_SOURCE_REF.storage_domain_id,
    "byteDomain": PLAYABLE_SOURCE_REF.byte_domain,
    "sha256": PLAYABLE_SOURCE_REF.sha256,
    "size": PLAYABLE_SOURCE_REF.size,
}
PLAYABLE_SOURCE_ARTIFACT_REF_PAYLOAD = {
    "storageDomainId": PLAYABLE_SOURCE_ARTIFACT_REF.storage_domain_id,
    "byteDomain": PLAYABLE_SOURCE_ARTIFACT_REF.byte_domain,
    "sha256": PLAYABLE_SOURCE_ARTIFACT_REF.sha256,
    "size": PLAYABLE_SOURCE_ARTIFACT_REF.size,
}
PLAYABLE_SOURCE_ARTIFACT_IDENTITY = {
    "ref": PLAYABLE_SOURCE_ARTIFACT_REF_PAYLOAD,
    "parentRefs": [PLAYABLE_SOURCE_PARENT_REF],
    "transformName": "freeze-playable-regions-source-inventory",
    "transformVersion": "1",
    "parameters": {
        "ownerAccountId": OWNER_ACCOUNT_ID,
        "sourceRegionInventoryHash": PLAYABLE_SOURCE_REGION_INVENTORY_HASH,
        "decoderVersion": "source-inventory-1",
    },
    "buildHash": "source-inventory-build-1",
}
PLAYABLE_SOURCE_ARTIFACT = {
    "artifactId": typed_id(
        "DeepMineDerivedArtifact/v1", PLAYABLE_SOURCE_ARTIFACT_IDENTITY,
    ),
    **PLAYABLE_SOURCE_ARTIFACT_IDENTITY,
}
PLAYABLE_SOURCE_PROVENANCE_BODY = canonical_json_bytes({
    "schema": "ai-caddie-trusted-playable-source-inventory-provenance-v1",
    "ownerAccountId": OWNER_ACCOUNT_ID,
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "authorizedEvidenceIds": ["field-check-1"],
    "sourceRegionInventoryHash": PLAYABLE_SOURCE_REGION_INVENTORY_HASH,
    "sourceRegions": PLAYABLE_SOURCE_REGIONS,
    "sourceDomains": [PLAYABLE_SOURCE_DOMAIN.canonical()],
    "sourceNodes": [
        row.canonical() for row in sorted(
            PLAYABLE_SOURCE_NODES, key=lambda row: row.node_id,
        )
    ],
    "closureProofs": [PLAYABLE_SOURCE_PROOF.canonical()],
    "fingerprints": [PLAYABLE_SOURCE_FINGERPRINT.canonical()],
    "artifact": PLAYABLE_SOURCE_ARTIFACT,
})
PLAYABLE_SOURCE_PROVENANCE_REF = CASRef(
    SECURITY_DOMAIN_ID,
    "deep-mine-playable-regions-source-inventory-provenance",
    hashlib.sha256(PLAYABLE_SOURCE_PROVENANCE_BODY).hexdigest(),
    len(PLAYABLE_SOURCE_PROVENANCE_BODY),
)
PLAYABLE_SOURCE_PROVENANCE_REF_PAYLOAD = {
    "storageDomainId": PLAYABLE_SOURCE_PROVENANCE_REF.storage_domain_id,
    "byteDomain": PLAYABLE_SOURCE_PROVENANCE_REF.byte_domain,
    "sha256": PLAYABLE_SOURCE_PROVENANCE_REF.sha256,
    "size": PLAYABLE_SOURCE_PROVENANCE_REF.size,
}
PLAYABLE_SOURCE_TRUST_RECORD_PAYLOAD = {
    "inventorySha256": PLAYABLE_SOURCE_ARTIFACT_REF.sha256,
    "provenanceHash": PLAYABLE_SOURCE_PROVENANCE_REF.sha256,
    "provenanceRef": PLAYABLE_SOURCE_PROVENANCE_REF_PAYLOAD,
    "artifact": PLAYABLE_SOURCE_ARTIFACT,
}
PLAYABLE_SOURCE_TRUST = SourceInventoryTrust(
    artifact_id=PLAYABLE_SOURCE_ARTIFACT["artifactId"],
    record_sha256=hashlib.sha256(
        canonical_json_bytes(PLAYABLE_SOURCE_TRUST_RECORD_PAYLOAD),
    ).hexdigest(),
    provenance_hash=PLAYABLE_SOURCE_PROVENANCE_REF.sha256,
    provenance_ref=PLAYABLE_SOURCE_PROVENANCE_REF,
)
PLAYABLE_REGIONS_TOPOLOGY_BODY = canonical_json_bytes({
    "schema": "ai-caddie-playable-regions-topology-evidence-v1",
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "mapGeometryHash": BASE_GEOMETRY_HASH,
    "mapGeometryEnvelope": PLAYABLE_MAP_GEOMETRY_ENVELOPE,
    "horizontalCrs": "local-enu-wgs84-v1",
    "horizontalUnit": "meter",
    "registrationResidualM": PLAYABLE_REGIONS_REGISTRATION_RESIDUAL_M,
    "sourceInventoryEvidenceHash": PLAYABLE_REGIONS_SOURCE_INVENTORY_EVIDENCE_HASH,
    "sourceRegionInventoryHash": PLAYABLE_SOURCE_REGION_INVENTORY_HASH,
    "regionsHash": PLAYABLE_REGIONS_HASH,
    "regionRefs": ["region:bunker-1", "region:fairway-1"],
    "closed": True,
    "oriented": True,
    "selfIntersectionFree": True,
    "interiorNonOverlapping": True,
    "boundaryContactPolicy": "allow_cross_region_touch_and_shared_edge",
})
PLAYABLE_REGIONS_COVERAGE_BODY = canonical_json_bytes({
    "schema": "ai-caddie-playable-regions-coverage-evidence-v1",
    "courseLayoutIdentity": "layout-identity-1",
    "layoutRevisionId": "layout-revision-1",
    "holeGlobalId": "31936-7",
    "sourceRevisionIds": ["source-revision-base"],
    "mapGeometryHash": BASE_GEOMETRY_HASH,
    "mapGeometryEnvelope": PLAYABLE_MAP_GEOMETRY_ENVELOPE,
    "sourceInventoryEvidenceHash": PLAYABLE_REGIONS_SOURCE_INVENTORY_EVIDENCE_HASH,
    "sourceRegionInventoryHash": PLAYABLE_SOURCE_REGION_INVENTORY_HASH,
    "topologyEvidenceHash": hashlib.sha256(PLAYABLE_REGIONS_TOPOLOGY_BODY).hexdigest(),
    "regionsHash": PLAYABLE_REGIONS_HASH,
    "expectedRegionRefs": [row["regionRef"] for row in PLAYABLE_SOURCE_REGIONS],
    "observedRegionRefs": ["region:bunker-1", "region:fairway-1"],
    "complete": True,
})
GREEN_ORIENTATION_TRANSFORM = [1.0, 0.0, 0.0, 1.0, 4.0, -3.0]
GREEN_ORIENTATION_TRANSFORM_ID = typed_id(
    "DeepMineGreenOrientationTransform/v1",
    {"matrix": GREEN_ORIENTATION_TRANSFORM},
)
GREEN_REGISTRATION_RESIDUAL_M = 1.5
GREEN_CROSS_SOURCE_RESIDUAL_M = 2.0
GREEN_REGISTRATION_SAMPLE_COUNT = 24


def green_evidence_body(schema: str) -> bytes:
    return canonical_json_bytes({
        "schema": schema,
        "courseLayoutIdentity": "layout-identity-1",
        "layoutRevisionId": "layout-revision-1",
        "holeGlobalId": "31936-7",
        "greenSourceRevisionId": "source-revision-green",
        "baseSourceRevisionId": "source-revision-base",
        "greenSourceSha256": hashlib.sha256(b"green-source").hexdigest(),
        "selectedComponentId": "draco-component-4",
        "decoderId": "draco-green",
        "decoderVersion": "1.5.7+green-1",
        "calibrationId": "green-calibration-2026-07",
        "orientationTransformId": GREEN_ORIENTATION_TRANSFORM_ID,
        "orientationTransform": GREEN_ORIENTATION_TRANSFORM,
        "baseGeometryHash": BASE_GEOMETRY_HASH,
        "registrationResidualM": GREEN_REGISTRATION_RESIDUAL_M,
        "crossSourceResidualM": GREEN_CROSS_SOURCE_RESIDUAL_M,
        "registrationSampleCount": GREEN_REGISTRATION_SAMPLE_COUNT,
        "accepted": True,
    })


EVIDENCE_BODIES = {
    "researchEvidenceReport": (
        "deep-mine-research-evidence-report",
        canonical_json_bytes({
            "schema": "ai-caddie-research-evidence-report-v1",
            "layoutRevisionId": "layout-revision-1",
            "sourceRevisionIds": ["source-revision-base", "source-revision-green"],
            "complete": True,
        }),
    ),
    "playsLikeCalibration": (
        "deep-mine-calibration-evidence",
        canonical_json_bytes({
            "schema": "ai-caddie-plays-like-calibration-evidence-v1",
            "sourceRevisionId": "source-revision-green",
            "modelVersion": "playslike-elevation-v1",
            "accepted": True,
        }),
    ),
    "hazardGuidanceSet": ("deep-mine-hazard-set-evidence", HAZARD_SET_BODY),
    "hazardCoverage": ("deep-mine-hazard-coverage-evidence", HAZARD_COVERAGE_BODY),
    "playableRegionsSourceInventory": (
        "deep-mine-playable-regions-source-inventory-evidence",
        PLAYABLE_REGIONS_SOURCE_INVENTORY_BODY,
    ),
    "playableRegionsTopology": (
        "deep-mine-playable-regions-topology-evidence", PLAYABLE_REGIONS_TOPOLOGY_BODY,
    ),
    "playableRegionsCoverage": (
        "deep-mine-playable-regions-coverage-evidence", PLAYABLE_REGIONS_COVERAGE_BODY,
    ),
    "greenRegistration": (
        "deep-mine-registration-report",
        green_evidence_body("ai-caddie-green-registration-report-v1"),
    ),
    "greenCrossSource": (
        "deep-mine-cross-source-evidence",
        green_evidence_body("ai-caddie-green-cross-source-evidence-v1"),
    ),
}
EVIDENCE_SOURCES = {
    "researchEvidenceReport": ("source-revision-green", "source-revision-base"),
    "playsLikeCalibration": ("source-revision-green",),
    "hazardGuidanceSet": ("source-revision-base",),
    "hazardCoverage": ("source-revision-base",),
    "playableRegionsSourceInventory": ("source-revision-base",),
    "playableRegionsTopology": ("source-revision-base",),
    "playableRegionsCoverage": ("source-revision-base",),
    "greenRegistration": ("source-revision-green", "source-revision-base"),
    "greenCrossSource": ("source-revision-green", "source-revision-base"),
}
def capability_evidence_kinds(
    capability: str,
    product_role: str,
) -> tuple[str, ...]:
    if capability == "playsLike":
        return ("researchEvidenceReport", "playsLikeCalibration")
    if capability == "hazardGuidance":
        base = ("researchEvidenceReport", "hazardGuidanceSet", "hazardCoverage")
        return (
            *base, "playableRegionsSourceInventory",
            "playableRegionsTopology", "playableRegionsCoverage",
        ) if product_role == "guidance.playable-regions" else base
    if capability == "greenSurface":
        return ("researchEvidenceReport", "greenRegistration", "greenCrossSource")
    raise ValueError(capability)


def evidence_hash(kind: str) -> str:
    return hashlib.sha256(EVIDENCE_BODIES[kind][1]).hexdigest()


def evidence_cas_ref(kind: str) -> EvidenceCASRef:
    byte_domain, body = EVIDENCE_BODIES[kind]
    return EvidenceCASRef(
        evidence_kind=kind,
        owner_account_id=OWNER_ACCOUNT_ID,
        security_domain_id=SECURITY_DOMAIN_ID,
        source_revision_ids=EVIDENCE_SOURCES[kind],
        cas_ref=CASRef(SECURITY_DOMAIN_ID, byte_domain, hashlib.sha256(body).hexdigest(), len(body)),
        source_inventory_trust=(
            PLAYABLE_SOURCE_TRUST
            if kind == "playableRegionsSourceInventory" else None
        ),
    )


def green_orientation_transform_id() -> str:
    return GREEN_ORIENTATION_TRANSFORM_ID


def product_body_for(
    capability: str,
    *,
    source_hash: str,
    base_geometry_hash: str,
    product_role: str,
) -> bytes:
    allowed_roles = {
        "playsLike": {"playsLike.model", "playsLike.elevation"},
        "hazardGuidance": {"hazardGuidanceBody", "guidance.playable-regions"},
        "greenSurface": {"greenSurfaceGeometry"},
    }
    if product_role not in allowed_roles.get(capability, set()):
        raise ValueError("fixture capability/product_role pair is unsupported")
    values: dict[str, dict[str, object]] = {
        "playsLike": {
            "schema": "ai-caddie-playsLike-body-v1",
            "modelVersion": "playslike-elevation-v1",
            "adjustmentPerVerticalMeter": 1.0,
            "modelEvidenceRefs": [evidence_hash("playsLikeCalibration")],
        },
        "hazardGuidance": {
            "schema": "ai-caddie-hazardGuidance-body-v1",
            "routeGeometryHash": base_geometry_hash,
            "stationingBasis": "tee-origin-route-station-v1",
            "hazards": [{
                "hazardRef": "hazard:forced-carry-7", "kind": "forced_carry",
                "enterDistanceM": 132.0, "clearDistanceM": 150.5,
                "evidenceRefs": [FORCED_CARRY_ROW_EVIDENCE_HASH],
            }],
        },
        "greenSurface": {
            "schema": "ai-caddie-greenSurface-body-v1",
            "sourceHash": source_hash,
            "componentId": "draco-component-4",
            "decoderVersion": "1.5.7+green-1",
            "calibrationVersion": "green-calibration-2026-07",
            "orientationTransformId": green_orientation_transform_id(),
            "orientationTransform": GREEN_ORIENTATION_TRANSFORM,
            "baseGeometryHash": base_geometry_hash,
            "slopeMagnitudePct": 2.4,
            "downhillDirectionDeg": 215.0,
            "registrationResidualM": GREEN_REGISTRATION_RESIDUAL_M,
            "crossSourceResidualM": GREEN_CROSS_SOURCE_RESIDUAL_M,
            "registrationSampleCount": GREEN_REGISTRATION_SAMPLE_COUNT,
            "evidenceRefs": sorted([
                evidence_hash("greenRegistration"),
                evidence_hash("greenCrossSource"),
            ]),
        },
    }
    if capability == "playsLike" and product_role == "playsLike.elevation":
        return canonical_json_bytes({
            "schema": "ai-caddie-playsLike-elevation-v1",
            "layoutRevisionId": "layout-revision-1",
            "holeGlobalId": "31936-7",
            "subjectRef": "hole:layout-revision-1:31936-7",
            "mapGeometryHash": base_geometry_hash,
            "horizontalCrs": "local-enu-wgs84-v1",
            "verticalDatumId": "source-local-orthometric-v1",
            "horizontalUnit": "meter",
            "verticalUnit": "meter",
            "origin": {
                "latitudeDeg": 22.001,
                "longitudeDeg": 113.001,
                "elevationM": 0.0,
            },
            "maximumAnchorDistanceM": 12.0,
            "maximumInterpolationResidualM": 1.9,
            "samples": [
                {"sampleRef": "anchor-fairway", "eastM": 100.0, "northM": 20.0, "elevationM": 8.0, "anchorDistanceM": 6.0, "anchorResidualM": 0.8},
                {"sampleRef": "anchor-green", "eastM": 210.0, "northM": 5.0, "elevationM": 13.0, "anchorDistanceM": 9.0, "anchorResidualM": 1.2},
                {"sampleRef": "anchor-tee", "eastM": 0.0, "northM": 0.0, "elevationM": 2.0, "anchorDistanceM": 4.0, "anchorResidualM": 0.5},
            ],
            "triangles": [{
                "triangleRef": "triangle-001",
                "sampleRefs": ["anchor-fairway", "anchor-green", "anchor-tee"],
            }],
            "evidenceRefs": [evidence_hash("playsLikeCalibration")],
        })
    if capability == "hazardGuidance" and product_role == "guidance.playable-regions":
        topology_hash = evidence_hash("playableRegionsTopology")
        return canonical_json_bytes({
            "schema": "ai-caddie-playable-regions-v1",
            "layoutRevisionId": "layout-revision-1",
            "holeGlobalId": "31936-7",
            "subjectRef": "hole:layout-revision-1:31936-7",
            "mapGeometryHash": base_geometry_hash,
            "mapGeometryEnvelope": PLAYABLE_MAP_GEOMETRY_ENVELOPE,
            "horizontalCrs": "local-enu-wgs84-v1",
            "horizontalUnit": "meter",
            "registrationResidualM": PLAYABLE_REGIONS_REGISTRATION_RESIDUAL_M,
            "maximumRegistrationResidualM": PLAYABLE_REGIONS_MAXIMUM_REGISTRATION_RESIDUAL_M,
            "sourceInventoryEvidenceHash": evidence_hash(
                "playableRegionsSourceInventory"
            ),
            "topologyEvidenceHash": topology_hash,
            "coverageEvidenceHash": evidence_hash("playableRegionsCoverage"),
            "regions": [
                {**region, "evidenceRefs": [topology_hash]}
                for region in PLAYABLE_REGIONS
            ],
            "evidenceRefs": sorted([
                evidence_hash("playableRegionsSourceInventory"),
                topology_hash,
                evidence_hash("playableRegionsCoverage"),
            ]),
        })
    return canonical_json_bytes(values[capability])


def product_refs_for(binding: PromotionBinding, capability: str) -> tuple[PromotionProductRef, ...]:
    values = {
        ("playsLike", "plays-like-model"): ("playsLike.model", "application/vnd.ai-caddie.plays-like+json", "ai-caddie-playsLike-body-v1"),
        ("playsLike", "plays-like-elevation"): ("playsLike.elevation", "application/vnd.ai-caddie.plays-like-elevation+json", "ai-caddie-playsLike-elevation-v1"),
        ("hazardGuidance", "hazard-guidance-body"): ("hazardGuidanceBody", "application/vnd.ai-caddie.hazard-guidance+json", "ai-caddie-hazardGuidance-body-v1"),
        ("hazardGuidance", "playable-regions"): ("guidance.playable-regions", "application/vnd.ai-caddie.playable-regions+json", "ai-caddie-playable-regions-v1"),
        ("greenSurface", "green-surface-geometry"): ("greenSurfaceGeometry", "application/vnd.ai-caddie.green-surface+json", "ai-caddie-greenSurface-body-v1"),
    }
    role, media_type, schema_id = values[(capability, binding.asset_refs[0].byte_domain)]
    domain = ByteDomain.create(
        binding.asset_refs[0], parent_domain_id=None, transform_id=None,
    )
    return (PromotionProductRef(
        role, media_type, schema_id,
        binding.fingerprinted_artifact_ids[0], domain.domain_id,
        binding.asset_refs[0],
    ),)


def evidence_fixture(
    *, capability: str, product_role: str,
    unresolved: bool = False, complete: bool = True,
):
    raw_body = b"green-source"
    raw_hash = hashlib.sha256(raw_body).hexdigest()
    ref = CASRef(SECURITY_DOMAIN_ID, "raw-entity", raw_hash, len(raw_body))
    base_geometry_body = b"base-geometry"
    base_geometry_ref = CASRef(
        SECURITY_DOMAIN_ID, "derived-base-geometry",
        hashlib.sha256(base_geometry_body).hexdigest(), len(base_geometry_body),
    )
    asset_byte_domain = {
        "playsLike": (
            "plays-like-elevation"
            if product_role == "playsLike.elevation" else "plays-like-model"
        ),
        "hazardGuidance": (
            "playable-regions"
            if product_role == "guidance.playable-regions" else "hazard-guidance-body"
        ),
        "greenSurface": "green-surface-geometry",
    }[capability]
    asset_body = product_body_for(
        capability, source_hash=raw_hash, base_geometry_hash=base_geometry_ref.sha256,
        product_role=product_role,
    )
    asset_ref = CASRef(
        SECURITY_DOMAIN_ID, asset_byte_domain,
        hashlib.sha256(asset_body).hexdigest(), len(asset_body),
    )
    domain = ByteDomain.create(asset_ref, parent_domain_id=None, transform_id=None)
    root = NodeRecord.root(domain.domain_id, len(asset_body), "runtime-product-root")
    node = NodeRecord.create(
        byte_domain_id=domain.domain_id,
        parent_node_id=root.node_id,
        offset=0,
        length=len(asset_body),
        status=NodeStatus.DECODED,
        node_kind="runtime-product",
        decoder_id="green-projector",
        decoder_version="1",
        occurrence_index=0,
        accounting=True,
        semantic_hypothesis=(
            f"registered {capability} product"
            if not unresolved else f"possible {capability} product"
        ),
        confidence="confirmed" if not unresolved else "0.60",
        consumed_by=("green-projector",),
    )
    proof_payload = {
        "byteDomainId": domain.domain_id,
        "rootNodeId": root.node_id,
        "domainSize": str(len(asset_body)),
        "classifiedBytes": str(len(asset_body)),
        "statusBytes": {"decoded": len(asset_body)},
        "complete": complete,
    }
    proof = ClosureProof(
        typed_id("DeepMineClosureProof/v1", proof_payload),
        domain.domain_id, root.node_id, len(asset_body), len(asset_body),
        {"decoded": len(asset_body)}, complete,
    )
    fingerprint = build_fingerprint(
        artifact_id=f"artifact-{capability}-product", schema_family=f"{capability}-schema",
        domain=domain, data=asset_body,
        structural_tokens=("schema", "runtime-product"),
        numeric_series={"byteLength": (float(len(asset_body)),)},
    )
    unknowns = UnknownRegistry()
    record = unknowns.observe(
        namespace=capability, locator="runtime-product", observed_at="2026-07-18T10:00:00.000Z",
        evidence=UnknownEvidence(
            asset_ref.sha256, domain.domain_id, 0, len(asset_body), "runtime-product", (),
        ), priority="high",
    )
    if not unresolved:
        unknowns.update_status(
            record.unknown_id, UnknownStatus.CONFIRMED,
            hypothesis=f"{capability} runtime product decoded",
            counterevidence="alternate schema/byte-domain candidates rejected",
            next_minimum_evidence=None, capture_required=False,
        )
    binding = PromotionBinding(
        owner_account_id=OWNER_ACCOUNT_ID,
        security_domain_id=SECURITY_DOMAIN_ID,
        course_layout_identity="layout-identity-1",
        layout_revision_id="layout-revision-1",
        source_revision_ids=("source-revision-green", "source-revision-base"),
        source_roster_hash="d" * 64,
        hole_global_id="31936-7",
        hole_number=7,
        raw_refs=(ref,),
        derived_refs=(base_geometry_ref,),
        asset_refs=(asset_ref,),
        closure_proof_ids=(proof.proof_id,),
        fingerprint_ids=(fingerprint.fingerprint_id,),
        fingerprinted_artifact_ids=(fingerprint.artifact_id,),
        unknown_ids=(record.unknown_id,),
        consumed_node_ids=(node.node_id,),
        evidence_refs=("overlay-evidence-1", "field-check-1"),
        evidence_cas_refs=tuple(
            evidence_cas_ref(kind)
            for kind in capability_evidence_kinds(capability, product_role)
        ),
        research_evidence_report_hash=evidence_hash("researchEvidenceReport"),
    )
    green = GreenSurfaceEvidence(
        green_source_revision_id="source-revision-green",
        base_source_revision_id="source-revision-base",
        green_source_sha256=raw_hash,
        selected_component_id="draco-component-4",
        decoder_id="draco-green",
        decoder_version="1.5.7+green-1",
        calibration_id="green-calibration-2026-07",
        orientation_transform_id=green_orientation_transform_id(),
        base_geometry_hash=base_geometry_ref.sha256,
        slope_magnitude_pct=2.4,
        downhill_direction_deg=215.0,
        registration_residual_m=GREEN_REGISTRATION_RESIDUAL_M,
        cross_source_residual_m=GREEN_CROSS_SOURCE_RESIDUAL_M,
        registration_sample_count=GREEN_REGISTRATION_SAMPLE_COUNT,
        registration_report_hash=evidence_hash("greenRegistration"),
        cross_source_evidence_hash=evidence_hash("greenCrossSource"),
        consumer_id="green-projector",
    )
    capability_evidence: PlaysLikeEvidence | HazardGuidanceEvidence | GreenSurfaceEvidence
    if capability == "playsLike":
        capability_evidence = plays_like_evidence()
    elif capability == "hazardGuidance":
        capability_evidence = hazard_evidence(binding, product_role=product_role)
    else:
        capability_evidence = green
    return ref, proof, fingerprint, unknowns, node, binding, capability_evidence


def put_fixture_parents(
    cas: EncryptedCAS,
    binding: PromotionBinding,
    capability: str,
    *,
    product_role: str,
    trusted_candidate_store: TrustedPromotionCandidateStore | None = None,
) -> tuple[CASRef, ...]:
    if product_refs_for(binding, capability)[0].role != product_role:
        raise AssertionError("fixture product role differs from bound runtime asset")
    parents = [
        cas.put_bytes(SECURITY_DOMAIN_ID, "raw-entity", b"green-source"),
        cas.put_bytes(SECURITY_DOMAIN_ID, "derived-base-geometry", b"base-geometry"),
    ]
    trusted_source_provenance_ref: CASRef | None = None
    if product_role == "guidance.playable-regions":
        if trusted_candidate_store is None:
            raise AssertionError("playable fixture requires the trusted freeze store")
        rows = tuple(SourceRegionInventoryRow(
            region_ref=row["regionRef"],
            source_revision_id=row["sourceRevisionId"],
            source_object_ref=row["sourceObjectRef"],
            source_node_ids=tuple(row["sourceNodeIds"]),
            closure_proof_ids=tuple(row["closureProofIds"]),
            fingerprint_ids=tuple(row["fingerprintIds"]),
            evidence_ids=tuple(row["evidenceIds"]),
        ) for row in PLAYABLE_SOURCE_REGIONS)
        frozen = freeze_playable_regions_source_inventory(
            cas=cas,
            trusted_candidate_store=trusted_candidate_store,
            storage_domain_id=SECURITY_DOMAIN_ID,
            owner_account_id=OWNER_ACCOUNT_ID,
            course_layout_identity=binding.course_layout_identity,
            layout_revision_id=binding.layout_revision_id,
            hole_global_id=binding.hole_global_id,
            source_revision_ids=("source-revision-base",),
            map_geometry_hash=binding.derived_refs[0].sha256,
            map_geometry_envelope=PLAYABLE_MAP_GEOMETRY_ENVELOPE,
            rows=rows,
            source_domains={PLAYABLE_SOURCE_DOMAIN.domain_id: PLAYABLE_SOURCE_DOMAIN},
            source_nodes={row.node_id: row for row in PLAYABLE_SOURCE_NODES},
            closure_proofs={PLAYABLE_SOURCE_PROOF.proof_id: PLAYABLE_SOURCE_PROOF},
            fingerprints={
                PLAYABLE_SOURCE_FINGERPRINT.fingerprint_id:
                PLAYABLE_SOURCE_FINGERPRINT,
            },
            authorized_evidence_ids=frozenset({"field-check-1"}),
            parent_refs=(PLAYABLE_SOURCE_REF,),
            decoder_version="source-inventory-1",
            build_hash="source-inventory-build-1",
        )
        source_evidence_ref = next(
            row.cas_ref for row in binding.evidence_cas_refs
            if row.evidence_kind == "playableRegionsSourceInventory"
        )
        if frozen.artifact.ref != source_evidence_ref:
            raise AssertionError("freeze output differs from bound source inventory")
        source_trust = next(
            row.source_inventory_trust for row in binding.evidence_cas_refs
            if row.evidence_kind == "playableRegionsSourceInventory"
        )
        if frozen.source_inventory_trust != source_trust:
            raise AssertionError("freeze trust record differs from candidate binding")
        trusted_source_provenance_ref = frozen.provenance_ref
    parents.append(cas.put_bytes(
        SECURITY_DOMAIN_ID,
        binding.asset_refs[0].byte_domain,
        product_body_for(
            capability,
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role=product_role,
        ),
    ))
    for evidence_ref in binding.evidence_cas_refs:
        byte_domain, body = EVIDENCE_BODIES[evidence_ref.evidence_kind]
        parents.append(cas.put_bytes(SECURITY_DOMAIN_ID, byte_domain, body))
    if trusted_source_provenance_ref is not None:
        parents.append(trusted_source_provenance_ref)
    expected = {
        *(ref for ref in binding.raw_refs),
        *(ref for ref in binding.derived_refs),
        *(ref for ref in binding.asset_refs),
        *(row.cas_ref for row in binding.evidence_cas_refs),
    }
    if trusted_source_provenance_ref is not None:
        expected.add(trusted_source_provenance_ref)
    if set(parents) != expected:
        raise AssertionError("fixture CAS parents do not match promotion binding")
    return tuple(parents)


def empty_hazard_fixture():
    raw_body = b"green-source"
    raw_ref = CASRef(
        SECURITY_DOMAIN_ID, "raw-entity", hashlib.sha256(raw_body).hexdigest(), len(raw_body),
    )
    base_body = b"base-geometry"
    base_ref = CASRef(
        SECURITY_DOMAIN_ID, "derived-base-geometry",
        hashlib.sha256(base_body).hexdigest(), len(base_body),
    )
    source_ids = ("source-revision-base",)
    set_body = canonical_json_bytes({
        "schema": "ai-caddie-hazard-set-evidence-v1",
        "courseLayoutIdentity": "layout-identity-1",
        "layoutRevisionId": "layout-revision-1",
        "holeGlobalId": "31936-7",
        "sourceRevisionIds": list(source_ids),
        "routeGeometryHash": base_ref.sha256,
        "stationingBasis": "tee-origin-route-station-v1",
        "hazards": [],
    })
    set_hash = hashlib.sha256(set_body).hexdigest()
    coverage_body = canonical_json_bytes({
        "schema": "ai-caddie-hazard-coverage-evidence-v1",
        "courseLayoutIdentity": "layout-identity-1",
        "layoutRevisionId": "layout-revision-1",
        "holeGlobalId": "31936-7",
        "sourceRevisionIds": list(source_ids),
        "routeGeometryHash": base_ref.sha256,
        "stationingBasis": "tee-origin-route-station-v1",
        "hazardSetEvidenceHash": set_hash,
        "complete": True,
    })
    product_body = canonical_json_bytes({
        "schema": "ai-caddie-hazardGuidance-body-v1",
        "routeGeometryHash": base_ref.sha256,
        "stationingBasis": "tee-origin-route-station-v1",
        "hazards": [],
    })
    asset_ref = CASRef(
        SECURITY_DOMAIN_ID, "hazard-guidance-body",
        hashlib.sha256(product_body).hexdigest(), len(product_body),
    )
    domain = ByteDomain.create(asset_ref, parent_domain_id=None, transform_id=None)
    root = NodeRecord.root(domain.domain_id, domain.size, "runtime-product-root")
    node = NodeRecord.create(
        byte_domain_id=domain.domain_id, parent_node_id=root.node_id,
        offset=0, length=domain.size, status=NodeStatus.DECODED,
        node_kind="runtime-product", decoder_id="green-projector", decoder_version="1",
        occurrence_index=0, accounting=True,
        semantic_hypothesis="verified exhaustive empty hazard product",
        confidence="confirmed", consumed_by=("green-projector",),
    )
    proof_payload = {
        "byteDomainId": domain.domain_id,
        "rootNodeId": root.node_id,
        "domainSize": str(domain.size),
        "classifiedBytes": str(domain.size),
        "statusBytes": {"decoded": domain.size},
        "complete": True,
    }
    proof = ClosureProof(
        typed_id("DeepMineClosureProof/v1", proof_payload), domain.domain_id,
        root.node_id, domain.size, domain.size, {"decoded": domain.size}, True,
    )
    fingerprint = build_fingerprint(
        artifact_id="artifact-hazard-empty-product", schema_family="hazardGuidance-schema",
        domain=domain, data=product_body, structural_tokens=("schema", "hazards", "empty"),
        numeric_series={"hazardCount": (0.0,)},
    )
    unknowns = UnknownRegistry()
    unknown = unknowns.observe(
        namespace="hazardGuidance", locator="runtime-product-empty",
        observed_at="2026-07-18T10:00:00.000Z",
        evidence=UnknownEvidence(
            asset_ref.sha256, domain.domain_id, 0, domain.size, "runtime-product-empty", (),
        ),
        priority="high",
    )
    unknowns.update_status(
        unknown.unknown_id, UnknownStatus.CONFIRMED,
        hypothesis="exhaustive hazard coverage proves an empty set",
        counterevidence="nonempty candidate and stale coverage pairings rejected",
        next_minimum_evidence=None, capture_required=False,
    )
    evidence = HazardGuidanceEvidence(
        source_revision_ids=source_ids,
        route_geometry_hash=base_ref.sha256,
        stationing_basis="tee-origin-route-station-v1",
        hazard_set_evidence_hash=set_hash,
        coverage_evidence_hash=hashlib.sha256(coverage_body).hexdigest(),
        playable_regions_map_geometry_hash=None,
        playable_regions_registration_residual_m=None,
        playable_regions_topology_evidence_hash=None,
        playable_regions_coverage_evidence_hash=None,
        hazards=(), consumer_id="green-projector",
    )
    binding = PromotionBinding(
        owner_account_id=OWNER_ACCOUNT_ID, security_domain_id=SECURITY_DOMAIN_ID,
        course_layout_identity="layout-identity-1", layout_revision_id="layout-revision-1",
        source_revision_ids=("source-revision-green", "source-revision-base"),
        source_roster_hash="d" * 64, hole_global_id="31936-7", hole_number=7,
        raw_refs=(raw_ref,), derived_refs=(base_ref,), asset_refs=(asset_ref,),
        closure_proof_ids=(proof.proof_id,), fingerprint_ids=(fingerprint.fingerprint_id,),
        fingerprinted_artifact_ids=(fingerprint.artifact_id,),
        unknown_ids=(unknown.unknown_id,), consumed_node_ids=(node.node_id,),
        evidence_refs=("hazard-empty-field-check",),
        evidence_cas_refs=(
            evidence_cas_ref("researchEvidenceReport"),
            EvidenceCASRef(
                "hazardGuidanceSet", OWNER_ACCOUNT_ID, SECURITY_DOMAIN_ID, source_ids,
                CASRef(SECURITY_DOMAIN_ID, "deep-mine-hazard-set-evidence", set_hash, len(set_body)),
            ),
            EvidenceCASRef(
                "hazardCoverage", OWNER_ACCOUNT_ID, SECURITY_DOMAIN_ID, source_ids,
                CASRef(
                    SECURITY_DOMAIN_ID, "deep-mine-hazard-coverage-evidence",
                    evidence.coverage_evidence_hash, len(coverage_body),
                ),
            ),
        ),
        research_evidence_report_hash=evidence_hash("researchEvidenceReport"),
    )
    bodies = {
        "raw-entity": raw_body,
        "derived-base-geometry": base_body,
        "hazard-guidance-body": product_body,
        "deep-mine-research-evidence-report": EVIDENCE_BODIES["researchEvidenceReport"][1],
        "deep-mine-hazard-set-evidence": set_body,
        "deep-mine-hazard-coverage-evidence": coverage_body,
    }
    return proof, fingerprint, unknowns, node, binding, evidence, bodies


def plays_like_evidence() -> PlaysLikeEvidence:
    return PlaysLikeEvidence(
        source_revision_id="source-revision-green",
        axis_attestation_id="axis-attestation-enu-up",
        horizontal_axis="local-east-north",
        vertical_axis="up-positive",
        horizontal_unit="meter",
        vertical_unit="meter",
        model_version="playslike-elevation-v1",
        adjustment_per_vertical_meter=1.0,
        calibration_anchor_ids=("tee-anchor", "fairway-anchor", "green-anchor"),
        max_anchor_distance_m=12.0,
        residual_rmse_m=0.8,
        max_abs_residual_m=1.9,
        outlier_threshold_m=3.0,
        outlier_count=1,
        sample_count=40,
        sample_course_count=5,
        sample_region_count=2,
        calibration_evidence_hash=evidence_hash("playsLikeCalibration"),
        consumer_id="green-projector",
    )


def hazard_evidence(
    binding: PromotionBinding,
    *,
    product_role: str,
) -> HazardGuidanceEvidence:
    has_playable_regions = product_role == "guidance.playable-regions"
    return HazardGuidanceEvidence(
        source_revision_ids=("source-revision-base",),
        route_geometry_hash=binding.derived_refs[0].sha256,
        stationing_basis="tee-origin-route-station-v1",
        hazard_set_evidence_hash=evidence_hash("hazardGuidanceSet"),
        coverage_evidence_hash=evidence_hash("hazardCoverage"),
        playable_regions_map_geometry_hash=(
            binding.derived_refs[0].sha256 if has_playable_regions else None
        ),
        playable_regions_registration_residual_m=(
            PLAYABLE_REGIONS_REGISTRATION_RESIDUAL_M if has_playable_regions else None
        ),
        playable_regions_topology_evidence_hash=(
            evidence_hash("playableRegionsTopology") if has_playable_regions else None
        ),
        playable_regions_coverage_evidence_hash=(
            evidence_hash("playableRegionsCoverage") if has_playable_regions else None
        ),
        hazards=(HazardEvidenceRow(
            hazard_ref="hazard:forced-carry-7",
            source_revision_id="source-revision-base",
            hazard_semantic_kind="forced_carry",
            route_geometry_hash=binding.derived_refs[0].sha256,
            landing_window_hash=binding.derived_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            stationing_basis="tee-origin-route-station-v1",
            enter_distance_m=132.0,
            clear_distance_m=150.5,
            evidence_hash=FORCED_CARRY_ROW_EVIDENCE_HASH,
        ),),
        consumer_id="green-projector",
    )


class PromotionTests(unittest.TestCase):
    def test_all_capability_evidence_variants_are_strict_and_plan2_schema_valid(self) -> None:
        for capability, product_role in (
            ("playsLike", "playsLike.model"),
            ("hazardGuidance", "hazardGuidanceBody"),
            ("greenSurface", "greenSurfaceGeometry"),
        ):
            with self.subTest(capability=capability, product_role=product_role):
                _ref, proof, fingerprint, unknowns, node, capability_binding, evidence = evidence_fixture(
                    capability=capability,
                    product_role=product_role,
                )
                candidate = build_promotion_candidate(
                    capability=capability,
                    product_role=product_role,
                    subject_ref="hole:layout-revision-1:31936-7",
                    projector_id="green-projector",
                    quality_policy_version=f"{capability}-quality-v1",
                    binding=capability_binding,
                    closure_proofs=(proof,),
                    fingerprints=(fingerprint,),
                    unknowns=unknowns,
                    nodes={node.node_id: node},
                    capability_evidence=evidence,
                )
                validate_candidate_schema(candidate)
                payload = candidate.canonical()
                self.assertEqual(payload["capabilityEvidence"]["evidenceKind"], capability)
                self.assertIn("researchEvidenceReportHash", payload["binding"])
                self.assertTrue(payload["binding"]["evidenceCasRefs"])
                self.assertEqual(len(payload["productRefs"]), 1)
                self.assertEqual(
                    payload["productRefs"][0]["casRef"],
                    payload["binding"]["assetRefs"][0],
                )
                self.assertNotIn("qualityReportHash", payload["binding"])

    def test_hazard_product_roles_require_exact_playable_evidence_shape(self) -> None:
        (
            _ref, proof, fingerprint, unknowns,
            node, binding, hazard_evidence_value,
        ) = evidence_fixture(
            capability="hazardGuidance",
            product_role="hazardGuidanceBody",
        )
        with self.assertRaisesRegex(ValueError, "requested product_role does not match"):
            build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=hazard_evidence_value,
            )
        with self.assertRaisesRegex(ValueError, "must not carry playable-regions evidence"):
            build_promotion_candidate(
                capability="hazardGuidance",
                product_role="hazardGuidanceBody",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=replace(
                    hazard_evidence_value,
                    playable_regions_map_geometry_hash=(
                        hazard_evidence_value.route_geometry_hash
                    ),
                ),
            )

        (
            _ref, proof, fingerprint, unknowns,
            node, binding, playable_evidence,
        ) = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        with self.assertRaisesRegex(ValueError, "playable-regions evidence is incomplete"):
            build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=replace(
                    playable_evidence,
                    playable_regions_coverage_evidence_hash=None,
                ),
            )

    def test_plays_like_elevation_product_is_queryable_and_geometry_bound(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
            capability="playsLike", product_role="playsLike.elevation",
        )
        product = product_refs_for(binding, "playsLike")[0]
        self.assertEqual(product.role, "playsLike.elevation")
        body = product_body_for(
            "playsLike",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="playsLike.elevation",
        )
        payload = validate_promotion_product_bytes(product, body, evidence)
        self.assertEqual(payload["mapGeometryHash"], binding.derived_refs[0].sha256)
        self.assertEqual(
            [row["sampleRef"] for row in payload["samples"]],
            sorted(row["sampleRef"] for row in payload["samples"]),
        )
        self.assertEqual(payload["horizontalCrs"], "local-enu-wgs84-v1")

        tampered = json.loads(body)
        tampered["samples"][2]["eastM"] = tampered["samples"][0]["eastM"]
        tampered["samples"][2]["northM"] = tampered["samples"][0]["northM"]
        with self.assertRaisesRegex(ValueError, "degenerate"):
            validate_promotion_product_bytes(
                product, canonical_json_bytes(tampered), evidence,
            )

        candidate = build_promotion_candidate(
            capability="playsLike",
            product_role="playsLike.elevation",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector",
            quality_policy_version="playsLike-quality-v1",
            binding=binding,
            closure_proofs=(proof,),
            fingerprints=(fingerprint,),
            unknowns=unknowns,
            nodes={node.node_id: node},
            capability_evidence=evidence,
        )
        self.assertEqual(candidate.product_refs[0].role, "playsLike.elevation")

    def test_playable_source_inventory_freezes_trusted_provenance_before_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            cas = EncryptedCAS(
                root_path / "cas",
                StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
            )
            trusted_store = TrustedPromotionCandidateStore.open(
                root_path / "trusted", SECURITY_DOMAIN_ID,
            )
            self.addCleanup(trusted_store.close)
            source_ref = cas.put_bytes(
                SECURITY_DOMAIN_ID, "derived-base-geometry", b"base-geometry",
            )
            source_domain = ByteDomain.create(
                source_ref, parent_domain_id=None, transform_id=None,
            )
            source_root = NodeRecord.root(
                source_domain.domain_id, source_domain.size, "source-region-root",
            )
            source_node = NodeRecord.create(
                byte_domain_id=source_domain.domain_id,
                parent_node_id=source_root.node_id,
                offset=0,
                length=source_domain.size,
                status=NodeStatus.DECODED,
                node_kind="source-region-object",
                decoder_id="gmp-rgn-source-regions",
                decoder_version="1",
                occurrence_index=0,
                accounting=True,
                semantic_hypothesis="source region roster",
                confidence="confirmed",
                consumed_by=("playable-source-inventory",),
            )
            proof_payload = {
                "byteDomainId": source_domain.domain_id,
                "rootNodeId": source_root.node_id,
                "domainSize": str(source_domain.size),
                "classifiedBytes": str(source_domain.size),
                "statusBytes": {"decoded": source_domain.size},
                "complete": True,
            }
            proof = ClosureProof(
                typed_id("DeepMineClosureProof/v1", proof_payload),
                source_domain.domain_id,
                source_root.node_id,
                source_domain.size,
                source_domain.size,
                {"decoded": source_domain.size},
                True,
            )
            fingerprint = build_fingerprint(
                artifact_id="artifact-source-base-geometry",
                schema_family="gmp-rgn-source-regions",
                domain=source_domain,
                data=b"base-geometry",
                structural_tokens=("rgn", "source-region"),
                numeric_series={"regionCount": (1.0,)},
            )
            row = SourceRegionInventoryRow(
                region_ref="region:fairway-1",
                source_revision_id="source-revision-base",
                source_object_ref="rgn-object:31936-7:fairway-1",
                source_node_ids=(source_node.node_id,),
                closure_proof_ids=(proof.proof_id,),
                fingerprint_ids=(fingerprint.fingerprint_id,),
                evidence_ids=("field-check-1",),
            )
            handle = freeze_playable_regions_source_inventory(
                cas=cas,
                trusted_candidate_store=trusted_store,
                storage_domain_id=SECURITY_DOMAIN_ID,
                owner_account_id=OWNER_ACCOUNT_ID,
                course_layout_identity="layout-identity-1",
                layout_revision_id="layout-revision-1",
                hole_global_id="31936-7",
                source_revision_ids=("source-revision-base",),
                map_geometry_hash=source_ref.sha256,
                map_geometry_envelope=PLAYABLE_MAP_GEOMETRY_ENVELOPE,
                rows=(row,),
                source_domains={source_domain.domain_id: source_domain},
                source_nodes={source_node.node_id: source_node},
                closure_proofs={proof.proof_id: proof},
                fingerprints={fingerprint.fingerprint_id: fingerprint},
                authorized_evidence_ids=frozenset({"field-check-1"}),
                parent_refs=(source_ref,),
                decoder_version="source-inventory-1",
                build_hash="source-inventory-build-1",
            )
            body = json.loads(
                cas.read_bytes(SECURITY_DOMAIN_ID, handle.artifact.ref)
            )
            self.assertEqual(
                body["inventoryBuildStage"],
                "source_decode_before_product_projection",
            )
            self.assertEqual(body["sourceRegions"][0]["sourceNodeIds"], [source_node.node_id])
            trusted_record = trusted_store.get_source_inventory_by_ref(
                handle.artifact.ref,
            )
            self.assertEqual(trusted_record.record_sha256, handle.trusted_record_sha256)
            self.assertEqual(trusted_record.artifact, handle.artifact)
            trusted_provenance = json.loads(
                cas.read_bytes(SECURITY_DOMAIN_ID, handle.provenance_ref)
            )
            self.assertEqual(trusted_provenance["artifact"], handle.artifact.canonical())
            self.assertEqual(
                trusted_provenance["sourceRegions"], body["sourceRegions"],
            )
            inverse_object_order = (
                replace(
                    row,
                    region_ref="region:a",
                    source_object_ref="rgn-object:z",
                ),
                replace(
                    row,
                    region_ref="region:b",
                    source_object_ref="rgn-object:a",
                ),
            )
            inverse_handle = freeze_playable_regions_source_inventory(
                cas=cas,
                trusted_candidate_store=trusted_store,
                storage_domain_id=SECURITY_DOMAIN_ID,
                owner_account_id=OWNER_ACCOUNT_ID,
                course_layout_identity="layout-identity-1",
                layout_revision_id="layout-revision-1",
                hole_global_id="31936-7",
                source_revision_ids=("source-revision-base",),
                map_geometry_hash=source_ref.sha256,
                map_geometry_envelope=PLAYABLE_MAP_GEOMETRY_ENVELOPE,
                rows=inverse_object_order,
                source_domains={source_domain.domain_id: source_domain},
                source_nodes={source_node.node_id: source_node},
                closure_proofs={proof.proof_id: proof},
                fingerprints={fingerprint.fingerprint_id: fingerprint},
                authorized_evidence_ids=frozenset({"field-check-1"}),
                parent_refs=(source_ref,),
                decoder_version="source-inventory-1",
                build_hash="source-inventory-build-1",
            )
            self.assertEqual(
                [
                    source["sourceObjectRef"]
                    for source in json.loads(
                        cas.read_bytes(
                            SECURITY_DOMAIN_ID, inverse_handle.artifact.ref,
                        )
                    )["sourceRegions"]
                ],
                ["rgn-object:z", "rgn-object:a"],
            )
            with self.assertRaisesRegex(ValueError, "unknown node/proof/fingerprint"):
                freeze_playable_regions_source_inventory(
                    cas=cas,
                    trusted_candidate_store=trusted_store,
                    storage_domain_id=SECURITY_DOMAIN_ID,
                    owner_account_id=OWNER_ACCOUNT_ID,
                    course_layout_identity="layout-identity-1",
                    layout_revision_id="layout-revision-1",
                    hole_global_id="31936-7",
                    source_revision_ids=("source-revision-base",),
                    map_geometry_hash=source_ref.sha256,
                    map_geometry_envelope=PLAYABLE_MAP_GEOMETRY_ENVELOPE,
                    rows=(replace(row, source_node_ids=("0" * 64,)),),
                    source_domains={source_domain.domain_id: source_domain},
                    source_nodes={source_node.node_id: source_node},
                    closure_proofs={proof.proof_id: proof},
                    fingerprints={fingerprint.fingerprint_id: fingerprint},
                    authorized_evidence_ids=frozenset({"field-check-1"}),
                    parent_refs=(source_ref,),
                    decoder_version="source-inventory-1",
                    build_hash="source-inventory-build-1",
                )

    def test_hand_written_source_inventory_bytes_have_no_admission_authority(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        candidate = build_promotion_candidate(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector",
            quality_policy_version="hazardGuidance-quality-v1",
            binding=binding,
            closure_proofs=(proof,),
            fingerprints=(fingerprint,),
            unknowns=unknowns,
            nodes={node.node_id: node},
            capability_evidence=evidence,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cas = EncryptedCAS(
                root / "cas",
                StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
            )
            store = TrustedPromotionCandidateStore.open(
                root / "trusted", SECURITY_DOMAIN_ID,
            )
            self.addCleanup(store.close)
            forged_ref = cas.put_bytes(
                SECURITY_DOMAIN_ID,
                "deep-mine-playable-regions-source-inventory-evidence",
                PLAYABLE_REGIONS_SOURCE_INVENTORY_BODY,
            )
            parents = (
                cas.put_bytes(SECURITY_DOMAIN_ID, "raw-entity", b"green-source"),
                cas.put_bytes(
                    SECURITY_DOMAIN_ID, "derived-base-geometry", b"base-geometry",
                ),
                cas.put_bytes(
                    SECURITY_DOMAIN_ID,
                    binding.asset_refs[0].byte_domain,
                    product_body_for(
                        "hazardGuidance",
                        source_hash=binding.raw_refs[0].sha256,
                        base_geometry_hash=binding.derived_refs[0].sha256,
                        product_role="guidance.playable-regions",
                    ),
                ),
                *(
                    forged_ref
                    if row.evidence_kind == "playableRegionsSourceInventory"
                    else cas.put_bytes(
                        SECURITY_DOMAIN_ID,
                        EVIDENCE_BODIES[row.evidence_kind][0],
                        EVIDENCE_BODIES[row.evidence_kind][1],
                    )
                    for row in binding.evidence_cas_refs
                ),
            )
            with self.assertRaisesRegex(ValueError, "trusted freeze store"):
                persist_promotion_candidate(
                    candidate,
                    cas=cas,
                    trusted_candidate_store=store,
                    closure_proofs=(proof,),
                    fingerprints=(fingerprint,),
                    unknowns=unknowns,
                    nodes={node.node_id: node},
                    owner_account_id=OWNER_ACCOUNT_ID,
                    storage_domain_id=SECURITY_DOMAIN_ID,
                    parent_refs=parents,
                    decoder_version="promotion-1",
                    build_hash="promotion-build-1",
                )

    def test_playable_regions_product_is_geometry_bound_and_readmits_end_to_end(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        body = product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        )
        payload = validate_promotion_product_bytes(product, body, evidence)
        self.assertEqual(product.role, "guidance.playable-regions")
        self.assertEqual(
            payload["maximumRegistrationResidualM"],
            PLAYABLE_REGIONS_MAXIMUM_REGISTRATION_RESIDUAL_M,
        )
        self.assertEqual(
            [row["regionRef"] for row in payload["regions"]],
            sorted(row["regionRef"] for row in payload["regions"]),
        )
        candidate = build_promotion_candidate(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector",
            quality_policy_version="hazardGuidance-quality-v1",
            binding=binding,
            closure_proofs=(proof,),
            fingerprints=(fingerprint,),
            unknowns=unknowns,
            nodes={node.node_id: node},
            capability_evidence=evidence,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cas = EncryptedCAS(
                root / "cas",
                StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
            )
            store = TrustedPromotionCandidateStore.open(root / "trusted", SECURITY_DOMAIN_ID)
            self.addCleanup(store.close)
            parents = put_fixture_parents(
                cas, binding, "hazardGuidance",
                product_role="guidance.playable-regions",
                trusted_candidate_store=store,
            )
            source_inventory_ref = next(
                row.cas_ref for row in binding.evidence_cas_refs
                if row.evidence_kind == "playableRegionsSourceInventory"
            )
            self.assertIn(
                store.get_source_inventory_by_ref(
                    source_inventory_ref,
                ).provenance_ref,
                parents,
            )
            bound_trust = next(
                row.source_inventory_trust for row in binding.evidence_cas_refs
                if row.evidence_kind == "playableRegionsSourceInventory"
            )
            self.assertEqual(bound_trust, PLAYABLE_SOURCE_TRUST)
            artifact = persist_promotion_candidate(
                candidate,
                cas=cas,
                trusted_candidate_store=store,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID,
                parent_refs=parents,
                decoder_version="promotion-1",
                build_hash="promotion-build-1",
            )
            validated = validate_untrusted_promotion_candidate(
                canonical_json_bytes(candidate.canonical()),
                cas=cas,
                trusted_candidate_store=store,
                storage_domain_id=SECURITY_DOMAIN_ID,
                parent_refs=tuple(reversed(parents)),
                expected_owner_account_id=OWNER_ACCOUNT_ID,
                expected_course_layout_identity=binding.course_layout_identity,
                expected_layout_revision_id=binding.layout_revision_id,
                expected_hole_global_id=binding.hole_global_id,
                expected_source_revision_ids=binding.source_revision_ids,
                expected_source_roster_hash=binding.source_roster_hash,
            )
            self.assertEqual(
                validated.candidate.product_refs[0].role,
                "guidance.playable-regions",
            )
            self.assertEqual(validated.trusted_record.artifact, artifact)

    def test_tampered_trusted_source_inventory_sql_row_fails_closed(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, _evidence = (
            evidence_fixture(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cas = EncryptedCAS(
                root / "cas",
                StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
            )
            store = TrustedPromotionCandidateStore.open(
                root / "trusted", SECURITY_DOMAIN_ID,
            )
            self.addCleanup(store.close)
            put_fixture_parents(
                cas,
                binding,
                "hazardGuidance",
                product_role="guidance.playable-regions",
                trusted_candidate_store=store,
            )
            inventory_ref = next(
                row.cas_ref for row in binding.evidence_cas_refs
                if row.evidence_kind == "playableRegionsSourceInventory"
            )
            stored = store.connection.execute(
                """
                SELECT artifact_id, record_json
                FROM trusted_playable_source_inventories
                WHERE storage_domain_id = ? AND inventory_sha256 = ?
                """,
                (SECURITY_DOMAIN_ID, inventory_ref.sha256),
            ).fetchone()
            store.connection.execute(
                """
                UPDATE trusted_playable_source_inventories
                SET record_json = ?
                WHERE storage_domain_id = ? AND artifact_id = ?
                """,
                (bytes(stored[1]) + b"\n", SECURITY_DOMAIN_ID, stored[0]),
            )
            with self.assertRaisesRegex(ValueError, "SQL row hash mismatch"):
                store.get_source_inventory_by_ref(inventory_ref)

    def test_cross_region_shared_boundary_is_valid_but_runtime_boundary_is_unavailable(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        payload = json.loads(product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        ))
        payload["regions"][0]["rings"][0]["points"] = [
            {"eastM": 100.0, "northM": 80.0},
            {"eastM": 140.0, "northM": 80.0},
            {"eastM": 140.0, "northM": 100.0},
            {"eastM": 100.0, "northM": 100.0},
            {"eastM": 100.0, "northM": 80.0},
        ]
        body = canonical_json_bytes(payload)
        validated = validate_promotion_product_bytes(
            replace(product, cas_ref=replace(
                product.cas_ref,
                sha256=hashlib.sha256(body).hexdigest(),
                size=len(body),
            )),
            body,
            evidence,
        )
        self.assertEqual(
            classify_playable_region_point(
                validated["regions"], east_m=120.0, north_m=80.0,
                topology_evidence_hash=validated["topologyEvidenceHash"],
                map_geometry_envelope=validated["mapGeometryEnvelope"],
            ),
            None,
        )
        self.assertEqual(
            classify_playable_region_point(
                validated["regions"], east_m=120.0, north_m=90.0,
                topology_evidence_hash=validated["topologyEvidenceHash"],
                map_geometry_envelope=validated["mapGeometryEnvelope"],
            ),
            "region:bunker-1",
        )
        self.assertEqual(
            classify_playable_region_point(
                validated["regions"], east_m=120.0, north_m=70.0,
                topology_evidence_hash=validated["topologyEvidenceHash"],
                map_geometry_envelope=validated["mapGeometryEnvelope"],
            ),
            "region:fairway-1",
        )

    def test_cross_region_proper_crossing_and_interior_overlap_are_rejected(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        original = json.loads(product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        ))
        for points, message in (
            ([
                {"eastM": 100.0, "northM": 60.0},
                {"eastM": 140.0, "northM": 60.0},
                {"eastM": 140.0, "northM": 100.0},
                {"eastM": 100.0, "northM": 100.0},
                {"eastM": 100.0, "northM": 60.0},
            ], "proper crossing"),
            ([
                {"eastM": 10.0, "northM": 10.0},
                {"eastM": 20.0, "northM": 10.0},
                {"eastM": 20.0, "northM": 20.0},
                {"eastM": 10.0, "northM": 20.0},
                {"eastM": 10.0, "northM": 10.0},
            ], "interiors overlap"),
            ([
                {"eastM": 0.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 0.0},
            ], "interiors overlap"),
            ([
                {"eastM": 0.0, "northM": 0.0},
                {"eastM": 175.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 0.0},
                {"eastM": 350.0, "northM": 80.0},
                {"eastM": 175.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 80.0},
                {"eastM": 0.0, "northM": 0.0},
            ], "interiors overlap"),
        ):
            payload = json.loads(canonical_json_bytes(original))
            payload["regions"][0]["rings"][0]["points"] = points
            body = canonical_json_bytes(payload)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                validate_promotion_product_bytes(
                    replace(product, cas_ref=replace(
                        product.cas_ref,
                        sha256=hashlib.sha256(body).hexdigest(),
                        size=len(body),
                    )),
                    body,
                    evidence,
                )

    def test_point_contact_hole_outer_outside_and_multi_match_are_unavailable(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        point_contact = json.loads(product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        ))
        point_contact["regions"][0]["rings"][0]["points"] = [
            {"eastM": 350.0, "northM": 80.0},
            {"eastM": 370.0, "northM": 80.0},
            {"eastM": 370.0, "northM": 100.0},
            {"eastM": 350.0, "northM": 100.0},
            {"eastM": 350.0, "northM": 80.0},
        ]
        point_contact_body = canonical_json_bytes(point_contact)
        point_contact_payload = validate_promotion_product_bytes(
            replace(product, cas_ref=replace(
                product.cas_ref,
                sha256=hashlib.sha256(point_contact_body).hexdigest(),
                size=len(point_contact_body),
            )),
            point_contact_body,
            evidence,
        )
        for east_m, north_m in ((350.0, 80.0), (500.0, 150.0)):
            with self.subTest(point=(east_m, north_m)):
                self.assertIsNone(classify_playable_region_point(
                    point_contact_payload["regions"],
                    east_m=east_m,
                    north_m=north_m,
                    topology_evidence_hash=point_contact_payload["topologyEvidenceHash"],
                    map_geometry_envelope=point_contact_payload["mapGeometryEnvelope"],
                ))

        with_hole = json.loads(canonical_json_bytes(point_contact))
        with_hole["regions"][1]["rings"].append({
            "ringRef": "ring:fairway-1:hole-1",
            "ringRole": "hole",
            "points": [
                {"eastM": 100.0, "northM": 20.0},
                {"eastM": 100.0, "northM": 30.0},
                {"eastM": 120.0, "northM": 30.0},
                {"eastM": 120.0, "northM": 20.0},
                {"eastM": 100.0, "northM": 20.0},
            ],
        })
        with_hole_body = canonical_json_bytes(with_hole)
        hole_payload = validate_promotion_product_bytes(
            replace(product, cas_ref=replace(
                product.cas_ref,
                sha256=hashlib.sha256(with_hole_body).hexdigest(),
                size=len(with_hole_body),
            )),
            with_hole_body,
            evidence,
        )
        for east_m, north_m in ((0.0, 40.0), (110.0, 20.0), (110.0, 25.0)):
            with self.subTest(point=(east_m, north_m)):
                self.assertIsNone(classify_playable_region_point(
                    hole_payload["regions"],
                    east_m=east_m,
                    north_m=north_m,
                    topology_evidence_hash=hole_payload["topologyEvidenceHash"],
                    map_geometry_envelope=hole_payload["mapGeometryEnvelope"],
                ))

        square = (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)),)
        overlapping_validated_geometry = (
            ("region:a", square, (), square),
            ("region:b", square, (), square),
        )
        self.assertIsNone(_classify_validated_playable_region_point(
            overlapping_validated_geometry,
            (5.0, 5.0),
        ))

    def test_v1_playable_resource_limits_are_exact_and_version_frozen(self) -> None:
        self.assertEqual(
            (
                _MAX_PLAYABLE_REGIONS_BODY_BYTES,
                _MAX_PLAYABLE_REGIONS,
                _MAX_PLAYABLE_RINGS,
                _MAX_PLAYABLE_POINTS,
                _MAX_PLAYABLE_POINTS_PER_RING,
                _MAX_GEOMETRY_PAIR_CHECKS,
                _MAX_ABS_LOCAL_COORDINATE_M,
            ),
            (2_000_000, 256, 512, 4_096, 512, 4_000_000, 100_000.0),
        )
        _require_playable_body_budget(b"x" * 2_000_000)
        with self.assertRaisesRegex(ValueError, "body byte budget"):
            _require_playable_body_budget(b"x" * 2_000_001)
        self.assertEqual(len(_require_playable_region_count([None] * 256)), 256)
        with self.assertRaisesRegex(ValueError, "region budget"):
            _require_playable_region_count([None] * 257)

        rings = _GeometryBudget(rings=511)
        rings.add_ring(1)
        self.assertEqual(rings.rings, 512)
        with self.assertRaisesRegex(ValueError, "ring budget"):
            rings.add_ring(1)
        points = _GeometryBudget(points=4_095)
        points.add_ring(1)
        self.assertEqual(points.points, 4_096)
        with self.assertRaisesRegex(ValueError, "point budget"):
            points.add_ring(1)
        per_ring = _GeometryBudget()
        per_ring.add_ring(512)
        with self.assertRaisesRegex(ValueError, "ring point budget"):
            _GeometryBudget().add_ring(513)
        comparisons = _GeometryBudget(pair_checks=3_999_999)
        comparisons.add_pair_check()
        self.assertEqual(comparisons.pair_checks, 4_000_000)
        with self.assertRaisesRegex(ValueError, "O.n.2.*budget"):
            comparisons.add_pair_check()

        self.assertEqual(_finite_geometry_number(100_000, "coordinate"), 100_000.0)
        self.assertEqual(_finite_geometry_number(-100_000, "coordinate"), -100_000.0)
        for value in (100_000.1, -100_000.1, 1e308):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "absolute local-coordinate envelope",
            ):
                _finite_geometry_number(value, "coordinate")
        envelope = _validated_map_geometry_envelope({
            "minEastM": -100_000.0,
            "minNorthM": -100_000.0,
            "maxEastM": 100_000.0,
            "maxNorthM": 100_000.0,
        })
        _require_point_in_envelope((100_000.0, -100_000.0), envelope, "point")
        with self.assertRaisesRegex(ValueError, "bound mapGeometryEnvelope"):
            _require_point_in_envelope((100_000.1, 0.0), envelope, "point")
        for invalid in (
            {"minEastM": 1.0, "minNorthM": 0.0, "maxEastM": 1.0, "maxNorthM": 2.0},
            {"minEastM": 2.0, "minNorthM": 0.0, "maxEastM": 1.0, "maxNorthM": 2.0},
        ):
            with self.subTest(envelope=invalid), self.assertRaisesRegex(
                ValueError, "positive finite area",
            ):
                _validated_map_geometry_envelope(invalid)

    def test_playable_geometry_envelope_numeric_and_complexity_budgets_fail_closed(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        original = json.loads(product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        ))
        for coordinate, message in (
            (1e308, "absolute local-coordinate envelope"),
            (-1e308, "absolute local-coordinate envelope"),
            (501.0, "bound mapGeometryEnvelope"),
        ):
            payload = json.loads(canonical_json_bytes(original))
            payload["regions"][0]["rings"][0]["points"][1]["eastM"] = coordinate
            body = canonical_json_bytes(payload)
            with self.subTest(coordinate=coordinate), self.assertRaisesRegex(ValueError, message):
                validate_promotion_product_bytes(
                    replace(product, cas_ref=replace(
                        product.cas_ref,
                        sha256=hashlib.sha256(body).hexdigest(), size=len(body),
                    )), body, evidence,
                )

        original_body = canonical_json_bytes(original)
        for constant, limit, message in (
            ("_MAX_PLAYABLE_REGIONS", 1, "region budget"),
            ("_MAX_PLAYABLE_RINGS", 1, "ring budget"),
            ("_MAX_PLAYABLE_POINTS", 5, "point budget"),
        ):
            with self.subTest(constant=constant), patch(
                f"ai_caddie.research.deep_mine.promotion.{constant}", limit,
            ), self.assertRaisesRegex(ValueError, message):
                validate_promotion_product_bytes(
                    replace(product, cas_ref=replace(
                        product.cas_ref,
                        sha256=hashlib.sha256(original_body).hexdigest(),
                        size=len(original_body),
                    )),
                    original_body,
                    evidence,
                )

        over_points = json.loads(canonical_json_bytes(original))
        over_points["regions"][0]["rings"][0]["points"] = [
            {"eastM": 1.0, "northM": 1.0}
        ] * 513
        over_points_body = canonical_json_bytes(over_points)
        with self.assertRaisesRegex(ValueError, "ring point budget"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(over_points_body).hexdigest(),
                    size=len(over_points_body),
                )),
                over_points_body,
                evidence,
            )

        oversized = b" " * 2_000_001
        with self.assertRaisesRegex(ValueError, "body byte budget"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(oversized).hexdigest(), size=len(oversized),
                )),
                oversized,
                evidence,
            )

        with patch(
            "ai_caddie.research.deep_mine.promotion._MAX_GEOMETRY_PAIR_CHECKS", 1,
        ), self.assertRaisesRegex(ValueError, "O.n.2.*budget"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(original_body).hexdigest(),
                    size=len(original_body),
                )),
                original_body,
                evidence,
            )

    def test_playable_regions_rejects_missing_fields_bad_topology_and_bad_evidence(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="guidance.playable-regions",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        body = product_body_for(
            "hazardGuidance",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="guidance.playable-regions",
        )

        missing = json.loads(body)
        del missing["maximumRegistrationResidualM"]
        missing_body = canonical_json_bytes(missing)
        with self.assertRaisesRegex(ValueError, "fields do not match schema"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(missing_body).hexdigest(),
                    size=len(missing_body),
                )),
                missing_body,
                evidence,
            )

        excessive_residual = json.loads(body)
        excessive_residual["registrationResidualM"] = (
            PLAYABLE_REGIONS_MAXIMUM_REGISTRATION_RESIDUAL_M + 0.1
        )
        excessive_residual_body = canonical_json_bytes(excessive_residual)
        with self.assertRaisesRegex(ValueError, "header is invalid"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(excessive_residual_body).hexdigest(),
                    size=len(excessive_residual_body),
                )),
                excessive_residual_body,
                evidence,
            )

        invalid_envelope = json.loads(body)
        invalid_envelope["mapGeometryEnvelope"]["minEastM"] = 600.0
        invalid_envelope_body = canonical_json_bytes(invalid_envelope)
        with self.assertRaisesRegex(ValueError, "positive finite area"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(invalid_envelope_body).hexdigest(),
                    size=len(invalid_envelope_body),
                )),
                invalid_envelope_body,
                evidence,
            )

        clockwise = json.loads(body)
        points = clockwise["regions"][1]["rings"][0]["points"]
        clockwise["regions"][1]["rings"][0]["points"] = list(reversed(points))
        clockwise_body = canonical_json_bytes(clockwise)
        with self.assertRaisesRegex(ValueError, "counter-clockwise"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(clockwise_body).hexdigest(),
                    size=len(clockwise_body),
                )),
                clockwise_body,
                evidence,
            )

        bad_hole_orientation = json.loads(body)
        bad_hole_orientation["regions"][1]["rings"].append({
            "ringRef": "ring:fairway-1:hole-1",
            "ringRole": "hole",
            "points": [
                {"eastM": 100.0, "northM": 20.0},
                {"eastM": 120.0, "northM": 20.0},
                {"eastM": 120.0, "northM": 30.0},
                {"eastM": 100.0, "northM": 30.0},
                {"eastM": 100.0, "northM": 20.0},
            ],
        })
        bad_hole_orientation_body = canonical_json_bytes(bad_hole_orientation)
        with self.assertRaisesRegex(ValueError, "hole rings must be clockwise"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(bad_hole_orientation_body).hexdigest(),
                    size=len(bad_hole_orientation_body),
                )),
                bad_hole_orientation_body,
                evidence,
            )

        outside_hole = json.loads(body)
        outside_hole["regions"][1]["rings"].append({
            "ringRef": "ring:fairway-1:hole-1",
            "ringRole": "hole",
            "points": [
                {"eastM": 400.0, "northM": 20.0},
                {"eastM": 400.0, "northM": 30.0},
                {"eastM": 420.0, "northM": 30.0},
                {"eastM": 420.0, "northM": 20.0},
                {"eastM": 400.0, "northM": 20.0},
            ],
        })
        outside_hole_body = canonical_json_bytes(outside_hole)
        with self.assertRaisesRegex(ValueError, "strictly inside exactly one outer ring"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(outside_hole_body).hexdigest(),
                    size=len(outside_hole_body),
                )),
                outside_hole_body,
                evidence,
            )

        overlapping = json.loads(body)
        overlapping["regions"][0]["rings"][0]["points"] = [
            {"eastM": 10.0, "northM": 10.0},
            {"eastM": 20.0, "northM": 10.0},
            {"eastM": 20.0, "northM": 20.0},
            {"eastM": 10.0, "northM": 20.0},
            {"eastM": 10.0, "northM": 10.0},
        ]
        overlapping_body = canonical_json_bytes(overlapping)
        with self.assertRaisesRegex(ValueError, "region interiors overlap"):
            validate_promotion_product_bytes(
                replace(product, cas_ref=replace(
                    product.cas_ref,
                    sha256=hashlib.sha256(overlapping_body).hexdigest(),
                    size=len(overlapping_body),
                )),
                overlapping_body,
                evidence,
            )

        topology_ref = next(
            row for row in binding.evidence_cas_refs
            if row.evidence_kind == "playableRegionsTopology"
        )
        wrong_topology_ref = replace(
            topology_ref,
            cas_ref=replace(topology_ref.cas_ref, sha256="0" * 64),
        )
        wrong_binding = replace(
            binding,
            evidence_cas_refs=tuple(
                wrong_topology_ref if row == topology_ref else row
                for row in binding.evidence_cas_refs
            ),
        )
        with self.assertRaisesRegex(ValueError, "CAS sha256 does not bind"):
            build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=wrong_binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=evidence,
            )

        topology_domain, topology_body = EVIDENCE_BODIES["playableRegionsTopology"]
        malformed_topology = json.loads(topology_body)
        malformed_topology["selfIntersectionFree"] = False
        with patch.dict(EVIDENCE_BODIES, {
            "playableRegionsTopology": (
                topology_domain,
                canonical_json_bytes(malformed_topology),
            ),
        }):
            (
                _bad_ref, bad_proof, bad_fingerprint, bad_unknowns,
                bad_node, bad_binding, bad_evidence,
            ) = evidence_fixture(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
            )
            bad_candidate = build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=bad_binding,
                closure_proofs=(bad_proof,),
                fingerprints=(bad_fingerprint,),
                unknowns=bad_unknowns,
                nodes={bad_node.node_id: bad_node},
                capability_evidence=bad_evidence,
            )
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cas = EncryptedCAS(
                    root / "cas",
                    StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
                )
                store = TrustedPromotionCandidateStore.open(
                    root / "trusted", SECURITY_DOMAIN_ID,
                )
                self.addCleanup(store.close)
                parents = put_fixture_parents(
                    cas, bad_binding, "hazardGuidance",
                    product_role="guidance.playable-regions",
                    trusted_candidate_store=store,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "playableRegionsTopology evidence body does not exactly bind",
                ):
                    persist_promotion_candidate(
                        bad_candidate,
                        cas=cas,
                        trusted_candidate_store=store,
                        closure_proofs=(bad_proof,),
                        fingerprints=(bad_fingerprint,),
                        unknowns=bad_unknowns,
                        nodes={bad_node.node_id: bad_node},
                        owner_account_id=OWNER_ACCOUNT_ID,
                        storage_domain_id=SECURITY_DOMAIN_ID,
                        parent_refs=parents,
                        decoder_version="promotion-1",
                        build_hash="promotion-build-1",
                    )

    def test_playable_regions_coverage_cas_body_must_exactly_bind_product(self) -> None:
        coverage_domain, coverage_body = EVIDENCE_BODIES["playableRegionsCoverage"]
        malformed_coverage = json.loads(coverage_body)
        malformed_coverage["complete"] = False
        with patch.dict(EVIDENCE_BODIES, {
            "playableRegionsCoverage": (
                coverage_domain,
                canonical_json_bytes(malformed_coverage),
            ),
        }):
            (
                _ref, proof, fingerprint, unknowns,
                node, binding, evidence,
            ) = evidence_fixture(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
            )
            candidate = build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=evidence,
            )
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cas = EncryptedCAS(
                    root / "cas",
                    StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
                )
                store = TrustedPromotionCandidateStore.open(
                    root / "trusted", SECURITY_DOMAIN_ID,
                )
                self.addCleanup(store.close)
                parents = put_fixture_parents(
                    cas, binding, "hazardGuidance",
                    product_role="guidance.playable-regions",
                    trusted_candidate_store=store,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "playableRegionsCoverage evidence body does not exactly bind",
                ):
                    persist_promotion_candidate(
                        candidate,
                        cas=cas,
                        trusted_candidate_store=store,
                        closure_proofs=(proof,),
                        fingerprints=(fingerprint,),
                        unknowns=unknowns,
                        nodes={node.node_id: node},
                        owner_account_id=OWNER_ACCOUNT_ID,
                        storage_domain_id=SECURITY_DOMAIN_ID,
                        parent_refs=parents,
                        decoder_version="promotion-1",
                        build_hash="promotion-build-1",
                    )

    def test_product_and_projection_evidence_cannot_synchronously_delete_source_region(self) -> None:
        reduced_regions = [PLAYABLE_REGIONS[1]]
        reduced_regions_hash = hashlib.sha256(canonical_json_bytes([{
            "regionRef": region["regionRef"],
            "lieKind": region["lieKind"],
            "rings": region["rings"],
        } for region in reduced_regions])).hexdigest()
        topology_domain, topology_body = EVIDENCE_BODIES["playableRegionsTopology"]
        reduced_topology = json.loads(topology_body)
        reduced_topology["regionsHash"] = reduced_regions_hash
        reduced_topology["regionRefs"] = ["region:fairway-1"]
        reduced_topology_body = canonical_json_bytes(reduced_topology)
        coverage_domain, coverage_body = EVIDENCE_BODIES["playableRegionsCoverage"]
        reduced_coverage = json.loads(coverage_body)
        reduced_coverage["topologyEvidenceHash"] = hashlib.sha256(
            reduced_topology_body,
        ).hexdigest()
        reduced_coverage["regionsHash"] = reduced_regions_hash
        # The independent frozen source inventory remains authoritative and complete.
        reduced_coverage["expectedRegionRefs"] = [
            "region:bunker-1", "region:fairway-1",
        ]
        reduced_coverage["observedRegionRefs"] = ["region:fairway-1"]
        reduced_coverage_body = canonical_json_bytes(reduced_coverage)

        with patch(__name__ + ".PLAYABLE_REGIONS", reduced_regions), patch.dict(
            EVIDENCE_BODIES,
            {
                "playableRegionsTopology": (topology_domain, reduced_topology_body),
                "playableRegionsCoverage": (coverage_domain, reduced_coverage_body),
            },
        ):
            _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
            )
            candidate = build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=evidence,
            )
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cas = EncryptedCAS(
                    root / "cas",
                    StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
                )
                store = TrustedPromotionCandidateStore.open(
                    root / "trusted", SECURITY_DOMAIN_ID,
                )
                self.addCleanup(store.close)
                parents = put_fixture_parents(
                    cas, binding, "hazardGuidance",
                    product_role="guidance.playable-regions",
                    trusted_candidate_store=store,
                )
                with self.assertRaisesRegex(ValueError, "completeness mismatch"):
                    persist_promotion_candidate(
                        candidate,
                        cas=cas,
                        trusted_candidate_store=store,
                        closure_proofs=(proof,),
                        fingerprints=(fingerprint,),
                        unknowns=unknowns,
                        nodes={node.node_id: node},
                        owner_account_id=OWNER_ACCOUNT_ID,
                        storage_domain_id=SECURITY_DOMAIN_ID,
                        parent_refs=parents,
                        decoder_version="promotion-1",
                        build_hash="promotion-build-1",
                    )

    def test_product_cannot_add_region_absent_from_frozen_source_inventory(self) -> None:
        extra_region = {
            "regionRef": "region:rough-1",
            "lieKind": "rough",
            "rings": [{
                "ringRef": "ring:rough-1:outer",
                "ringRole": "outer",
                "points": [
                    {"eastM": 360.0, "northM": 0.0},
                    {"eastM": 390.0, "northM": 0.0},
                    {"eastM": 390.0, "northM": 20.0},
                    {"eastM": 360.0, "northM": 20.0},
                    {"eastM": 360.0, "northM": 0.0},
                ],
            }],
            "evidenceRefs": [],
        }
        expanded_regions = [*PLAYABLE_REGIONS, extra_region]
        expanded_hash = hashlib.sha256(canonical_json_bytes([{
            "regionRef": region["regionRef"],
            "lieKind": region["lieKind"],
            "rings": region["rings"],
        } for region in expanded_regions])).hexdigest()
        topology_domain, topology_body = EVIDENCE_BODIES["playableRegionsTopology"]
        expanded_topology = json.loads(topology_body)
        expanded_topology["regionsHash"] = expanded_hash
        expanded_topology["regionRefs"] = [
            "region:bunker-1", "region:fairway-1", "region:rough-1",
        ]
        expanded_topology_body = canonical_json_bytes(expanded_topology)
        coverage_domain, coverage_body = EVIDENCE_BODIES["playableRegionsCoverage"]
        expanded_coverage = json.loads(coverage_body)
        expanded_coverage["topologyEvidenceHash"] = hashlib.sha256(
            expanded_topology_body,
        ).hexdigest()
        expanded_coverage["regionsHash"] = expanded_hash
        expanded_coverage["expectedRegionRefs"] = [
            "region:bunker-1", "region:fairway-1",
        ]
        expanded_coverage["observedRegionRefs"] = [
            "region:bunker-1", "region:fairway-1", "region:rough-1",
        ]
        expanded_coverage_body = canonical_json_bytes(expanded_coverage)

        with patch(__name__ + ".PLAYABLE_REGIONS", expanded_regions), patch.dict(
            EVIDENCE_BODIES,
            {
                "playableRegionsTopology": (
                    topology_domain, expanded_topology_body,
                ),
                "playableRegionsCoverage": (
                    coverage_domain, expanded_coverage_body,
                ),
            },
        ):
            _ref, proof, fingerprint, unknowns, node, binding, evidence = evidence_fixture(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
            )
            candidate = build_promotion_candidate(
                capability="hazardGuidance",
                product_role="guidance.playable-regions",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector",
                quality_policy_version="hazardGuidance-quality-v1",
                binding=binding,
                closure_proofs=(proof,),
                fingerprints=(fingerprint,),
                unknowns=unknowns,
                nodes={node.node_id: node},
                capability_evidence=evidence,
            )
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cas = EncryptedCAS(
                    root / "cas",
                    StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
                )
                store = TrustedPromotionCandidateStore.open(
                    root / "trusted", SECURITY_DOMAIN_ID,
                )
                self.addCleanup(store.close)
                parents = put_fixture_parents(
                    cas, binding, "hazardGuidance",
                    product_role="guidance.playable-regions",
                    trusted_candidate_store=store,
                )
                with self.assertRaisesRegex(ValueError, "completeness mismatch"):
                    persist_promotion_candidate(
                        candidate,
                        cas=cas,
                        trusted_candidate_store=store,
                        closure_proofs=(proof,),
                        fingerprints=(fingerprint,),
                        unknowns=unknowns,
                        nodes={node.node_id: node},
                        owner_account_id=OWNER_ACCOUNT_ID,
                        storage_domain_id=SECURITY_DOMAIN_ID,
                        parent_refs=parents,
                        decoder_version="promotion-1",
                        build_hash="promotion-build-1",
                    )

    def test_hazard_runtime_product_supports_multi_row_and_verified_empty_sets(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, evidence = evidence_fixture(
            capability="hazardGuidance",
            product_role="hazardGuidanceBody",
        )
        product = product_refs_for(binding, "hazardGuidance")[0]
        empty_evidence = replace(evidence, hazards=())
        empty_body = canonical_json_bytes({
            "schema": product.schema_id,
            "routeGeometryHash": empty_evidence.route_geometry_hash,
            "stationingBasis": empty_evidence.stationing_basis,
            "hazards": [],
        })
        validate_promotion_product_bytes(
            replace(product, cas_ref=replace(
                product.cas_ref,
                sha256=hashlib.sha256(empty_body).hexdigest(),
                size=len(empty_body),
            )),
            empty_body,
            empty_evidence,
        )

        second_payload = {
            "hazardRef": "hazard:water-8",
            "sourceRevisionId": evidence.hazards[0].source_revision_id,
            "hazardSemanticKind": "water",
            "routeGeometryHash": evidence.hazards[0].route_geometry_hash,
            "landingWindowHash": evidence.hazards[0].landing_window_hash,
            "baseGeometryHash": evidence.hazards[0].base_geometry_hash,
            "stationingBasis": "tee-origin-route-station-v1",
            "enterDistanceM": 164.0,
            "clearDistanceM": 179.0,
        }
        second = replace(
            evidence.hazards[0],
            hazard_ref=second_payload["hazardRef"],
            hazard_semantic_kind=second_payload["hazardSemanticKind"],
            stationing_basis=second_payload["stationingBasis"],
            enter_distance_m=second_payload["enterDistanceM"],
            clear_distance_m=second_payload["clearDistanceM"],
            evidence_hash=typed_id("DeepMineHazardEvidenceMember/v1", second_payload),
        )
        multi_evidence = replace(evidence, hazards=tuple(sorted(
            (*evidence.hazards, second), key=lambda row: row.hazard_ref,
        )))
        rows = [{
            "hazardRef": row.hazard_ref,
            "kind": row.hazard_semantic_kind,
            "enterDistanceM": row.enter_distance_m,
            "clearDistanceM": row.clear_distance_m,
            "evidenceRefs": [row.evidence_hash],
        } for row in multi_evidence.hazards]
        multi_body = canonical_json_bytes({
            "schema": product.schema_id,
            "routeGeometryHash": multi_evidence.route_geometry_hash,
            "stationingBasis": multi_evidence.stationing_basis,
            "hazards": rows,
        })
        validate_promotion_product_bytes(
            replace(product, cas_ref=replace(
                product.cas_ref,
                sha256=hashlib.sha256(multi_body).hexdigest(),
                size=len(multi_body),
            )),
            multi_body,
            multi_evidence,
        )
        with self.assertRaisesRegex(ValueError, "canonical by hazardRef"):
            validate_promotion_product_bytes(product, canonical_json_bytes({
                "schema": product.schema_id,
                "routeGeometryHash": multi_evidence.route_geometry_hash,
                "stationingBasis": multi_evidence.stationing_basis,
                "hazards": list(reversed(rows)),
            }), multi_evidence)

    def test_verified_empty_hazard_candidate_persists_and_readmits_end_to_end(self) -> None:
        proof, fingerprint, unknowns, node, binding, evidence, bodies = empty_hazard_fixture()
        with self.assertRaisesRegex(ValueError, "set/coverage evidence hash is not exact"):
            build_promotion_candidate(
                capability="hazardGuidance", product_role="hazardGuidanceBody",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="hazard-quality-v1",
                binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node},
                capability_evidence=replace(
                    evidence, coverage_evidence_hash=evidence_hash("hazardCoverage"),
                ),
            )
        candidate = build_promotion_candidate(
            capability="hazardGuidance", product_role="hazardGuidanceBody",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector", quality_policy_version="hazard-quality-v1",
            binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
            unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=evidence,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cas = EncryptedCAS(root / "cas", StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}))
            store = TrustedPromotionCandidateStore.open(root / "trusted", SECURITY_DOMAIN_ID)
            parents = tuple(
                cas.put_bytes(SECURITY_DOMAIN_ID, ref.byte_domain, bodies[ref.byte_domain])
                for ref in (
                    *binding.raw_refs, *binding.derived_refs, *binding.asset_refs,
                    *(row.cas_ref for row in binding.evidence_cas_refs),
                )
            )
            artifact = persist_promotion_candidate(
                candidate, cas=cas, trusted_candidate_store=store,
                closure_proofs=(proof,), fingerprints=(fingerprint,), unknowns=unknowns,
                nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=parents,
                decoder_version="promotion-1", build_hash="promotion-build-1",
            )
            validated = validate_untrusted_promotion_candidate(
                canonical_json_bytes(candidate.canonical()),
                cas=cas, trusted_candidate_store=store,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=tuple(reversed(parents)),
                expected_owner_account_id=OWNER_ACCOUNT_ID,
                expected_course_layout_identity=binding.course_layout_identity,
                expected_layout_revision_id=binding.layout_revision_id,
                expected_hole_global_id=binding.hole_global_id,
                expected_source_revision_ids=binding.source_revision_ids,
                expected_source_roster_hash=binding.source_roster_hash,
            )
            self.assertEqual(validated.candidate.capability_evidence.hazards, ())
            product = json.loads(cas.read_bytes(SECURITY_DOMAIN_ID, binding.asset_refs[0]))
            self.assertEqual(product["hazards"], [])
            self.assertEqual(validated.trusted_record.artifact, artifact)
            store.close()

    def test_runtime_product_bytes_are_strict_and_exactly_evidence_bound(self) -> None:
        _ref, _proof, _fingerprint, _unknowns, _node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        product = product_refs_for(binding, "greenSurface")[0]
        body = product_body_for(
            "greenSurface",
            source_hash=binding.raw_refs[0].sha256,
            base_geometry_hash=binding.derived_refs[0].sha256,
            product_role="greenSurfaceGeometry",
        )
        validate_promotion_product_bytes(product, body, green)
        mutated = json.loads(body)
        mutated["slopeMagnitudePct"] = 8.0
        with self.assertRaisesRegex(ValueError, "does not match capability evidence"):
            validate_promotion_product_bytes(product, canonical_json_bytes(mutated), green)
        mutated = json.loads(body)
        mutated["orientationTransform"][4] = 99.0
        with self.assertRaisesRegex(ValueError, "does not match capability evidence"):
            validate_promotion_product_bytes(product, canonical_json_bytes(mutated), green)
        for field, bad_value in (
            ("registrationResidualM", 99.0),
            ("crossSourceResidualM", 99.0),
            ("registrationSampleCount", 2),
        ):
            mutated = json.loads(body)
            mutated[field] = bad_value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_promotion_product_bytes(
                    product, canonical_json_bytes(mutated), green,
                )
        with self.assertRaisesRegex(ValueError, "duplicate runtime product key"):
            validate_promotion_product_bytes(
                product, b'{"schema":"x","schema":"y"}', green,
            )
        with self.assertRaisesRegex(ValueError, "not canonical JSON"):
            validate_promotion_product_bytes(product, body + b"\n", green)

    def test_green_registration_and_cross_source_cas_bodies_are_strictly_bound(self) -> None:
        for evidence_kind, mutate in (
            ("greenRegistration", lambda row: row.update({"accepted": False})),
            ("greenCrossSource", lambda row: row.update({"registrationSampleCount": 2})),
        ):
            with self.subTest(evidence_kind=evidence_kind):
                byte_domain, valid_body = EVIDENCE_BODIES[evidence_kind]
                tampered = json.loads(valid_body)
                mutate(tampered)
                tampered_body = canonical_json_bytes(tampered)
                with patch.dict(
                    EVIDENCE_BODIES,
                    {evidence_kind: (byte_domain, tampered_body)},
                ):
                    _ref, proof, fingerprint, unknowns, node, binding, green = (
                        evidence_fixture(
                            capability="greenSurface",
                            product_role="greenSurfaceGeometry",
                        )
                    )
                    candidate = build_promotion_candidate(
                        capability="greenSurface",
                        product_role="greenSurfaceGeometry",
                        subject_ref="hole:layout-revision-1:31936-7",
                        projector_id="green-projector",
                        quality_policy_version="greenSurface-quality-v1",
                        binding=binding,
                        closure_proofs=(proof,),
                        fingerprints=(fingerprint,),
                        unknowns=unknowns,
                        nodes={node.node_id: node},
                        capability_evidence=green,
                    )
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        cas = EncryptedCAS(
                            root / "cas",
                            StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
                        )
                        store = TrustedPromotionCandidateStore.open(
                            root / "trusted", SECURITY_DOMAIN_ID,
                        )
                        self.addCleanup(store.close)
                        parents = put_fixture_parents(
                            cas, binding, "greenSurface",
                            product_role="greenSurfaceGeometry",
                        )
                        with self.assertRaisesRegex(
                            ValueError,
                            f"{evidence_kind} evidence body does not exactly bind",
                        ):
                            persist_promotion_candidate(
                                candidate,
                                cas=cas,
                                trusted_candidate_store=store,
                                closure_proofs=(proof,),
                                fingerprints=(fingerprint,),
                                unknowns=unknowns,
                                nodes={node.node_id: node},
                                owner_account_id=OWNER_ACCOUNT_ID,
                                storage_domain_id=SECURITY_DOMAIN_ID,
                                parent_refs=parents,
                                decoder_version="promotion-1",
                                build_hash="promotion-build-1",
                            )

    def test_invalid_capability_specific_evidence_and_unknown_schema_fields_fail_closed(self) -> None:
        plays_fixture = evidence_fixture(
            capability="playsLike", product_role="playsLike.model",
        )
        hazard_fixture = evidence_fixture(
            capability="hazardGuidance", product_role="hazardGuidanceBody",
        )
        green_fixture = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        bad_plays = PlaysLikeEvidence(**{**plays_fixture[-1].__dict__, "vertical_unit": "foot"})
        valid_hazard = hazard_fixture[-1]
        bad_hazard = replace(
            valid_hazard,
            hazards=(replace(valid_hazard.hazards[0], hazard_semantic_kind="guess"),),
        )
        reversed_hazard = replace(
            valid_hazard,
            hazards=(replace(
                valid_hazard.hazards[0], enter_distance_m=151.0, clear_distance_m=138.0,
            ),),
        )
        for capability, product_role, fixture, evidence, message in (
            ("playsLike", "playsLike.model", plays_fixture, bad_plays, "canonical units"),
            (
                "hazardGuidance", "hazardGuidanceBody", hazard_fixture,
                bad_hazard, "semantic kind",
            ),
            (
                "hazardGuidance", "hazardGuidanceBody", hazard_fixture,
                reversed_hazard, "clear station precedes enter",
            ),
            (
                "playsLike", "playsLike.model", plays_fixture,
                green_fixture[-1], "does not match capability",
            ),
        ):
            _ref, proof, fingerprint, unknowns, node, capability_binding, _valid = fixture
            with self.subTest(capability=capability, message=message), self.assertRaisesRegex(ValueError, message):
                build_promotion_candidate(
                    capability=capability, product_role=product_role,
                    subject_ref="hole:layout-revision-1:31936-7",
                    projector_id="green-projector", quality_policy_version="quality-v1",
                    binding=capability_binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                    unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=evidence,
                )
        _ref, proof, fingerprint, unknowns, node, binding, green = green_fixture
        candidate = build_promotion_candidate(
            capability="greenSurface", product_role="greenSurfaceGeometry",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector", quality_policy_version="green-quality-v1",
            binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
            unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
        )
        payload = candidate.canonical()
        payload["binding"]["qualityReportHash"] = "9" * 64
        with self.assertRaises(ValidationError):
            validate_candidate_schema(payload)
        payload = candidate.canonical()
        payload["capabilityEvidence"]["unexpected"] = True
        with self.assertRaises(ValidationError):
            validate_candidate_schema(payload)

    def test_green_surface_candidate_requires_complete_bound_evidence_and_stays_research_only(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        candidate = build_promotion_candidate(
            capability="greenSurface",
            product_role="greenSurfaceGeometry",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector",
            quality_policy_version="green-quality-v1",
            binding=binding,
            closure_proofs=(proof,),
            fingerprints=(fingerprint,),
            unknowns=unknowns,
            nodes={node.node_id: node},
            capability_evidence=green,
        )
        self.assertEqual(candidate.candidate_state, "research_only_candidate")
        self.assertEqual(candidate.target_gate, "plan-2-capability-quality-gate")
        self.assertEqual(candidate.binding.unknown_ids, tuple(record.unknown_id for record in unknowns.records()))

    def test_unresolved_unknown_hypothesis_or_incomplete_closure_fails_closed(self) -> None:
        for unresolved, complete, message in (
            (True, True, "unresolved unknown"),
            (False, False, "incomplete closure"),
        ):
            with self.subTest(unresolved=unresolved, complete=complete):
                _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
                    capability="greenSurface", product_role="greenSurfaceGeometry",
                    unresolved=unresolved, complete=complete,
                )
                with self.assertRaisesRegex(ValueError, message):
                    build_promotion_candidate(
                        capability="greenSurface", product_role="greenSurfaceGeometry",
                        subject_ref="hole:layout-revision-1:31936-7",
                        projector_id="green-projector", quality_policy_version="green-quality-v1",
                        binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                        unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
                    )

    def test_forged_closure_fingerprint_and_node_ids_fail_recomputation(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        forged_proof = replace(proof, proof_id="forged-proof")
        with self.assertRaisesRegex(ValueError, "invalid proof identity"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=replace(binding, closure_proof_ids=(forged_proof.proof_id,)),
                closure_proofs=(forged_proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
            )
        forged_fingerprint = replace(fingerprint, fingerprint_id="forged-fingerprint")
        with self.assertRaisesRegex(ValueError, "invalid fingerprint identity"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=replace(binding, fingerprint_ids=(forged_fingerprint.fingerprint_id,)),
                closure_proofs=(proof,), fingerprints=(forged_fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
            )
        forged_node = replace(node, node_id="forged-node")
        with self.assertRaisesRegex(ValueError, "invalid identity"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=replace(binding, consumed_node_ids=(forged_node.node_id,)),
                closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={forged_node.node_id: forged_node},
                capability_evidence=green,
            )

    def test_missing_consumer_or_green_specific_evidence_fails_closed(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        unconsumed = NodeRecord.create(
            byte_domain_id=node.byte_domain_id, parent_node_id=node.parent_node_id,
            offset=node.offset, length=node.length, status=node.status,
            node_kind=node.node_kind, decoder_id=node.decoder_id,
            decoder_version=node.decoder_version, occurrence_index=node.occurrence_index,
            accounting=node.accounting, semantic_hypothesis=node.semantic_hypothesis,
            confidence=node.confidence, consumed_by=(),
        )
        with self.assertRaisesRegex(ValueError, "consumer binding"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=replace(binding, consumed_node_ids=(unconsumed.node_id,)),
                closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={unconsumed.node_id: unconsumed}, capability_evidence=green,
            )
        with self.assertRaisesRegex(ValueError, "capability-specific evidence"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=None,
            )

    def test_fingerprint_domain_and_cross_revision_same_hole_number_subject_fail_closed(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        foreign_fingerprint = fingerprint.__class__(
            **{**fingerprint.__dict__, "byte_domain_id": "unproved-domain"},
        )
        with self.assertRaisesRegex(ValueError, "fingerprint domain"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=binding, closure_proofs=(proof,), fingerprints=(foreign_fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
            )
        same_bytes_wrong_domain = replace(
            binding,
            asset_refs=(replace(binding.asset_refs[0], byte_domain="archive-member"),),
        )
        with self.assertRaisesRegex(ValueError, "green-surface-geometry runtime product"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=same_bytes_wrong_domain, closure_proofs=(proof,),
                fingerprints=(fingerprint,), unknowns=unknowns,
                nodes={node.node_id: node}, capability_evidence=green,
            )
        next_revision = replace(binding, layout_revision_id="layout-revision-2")
        with self.assertRaisesRegex(ValueError, "promotion subject"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=next_revision, closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
            )

    def test_green_and_base_require_distinct_bound_source_revisions(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        same_revision = replace(green, base_source_revision_id=green.green_source_revision_id)
        with self.assertRaisesRegex(ValueError, "independent source revisions"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=same_revision,
            )

    def test_evidence_cas_refs_validate_owner_security_domain_byte_domain_size_and_hash_binding(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        research = next(row for row in binding.evidence_cas_refs if row.evidence_kind == "researchEvidenceReport")
        mutations = (
            (replace(research, owner_account_id="account-b"), "owner account"),
            (replace(research, security_domain_id="domain-b"), "security domain"),
            (replace(research, cas_ref=replace(research.cas_ref, storage_domain_id="domain-b")), "storage/security domain"),
            (replace(research, cas_ref=replace(research.cas_ref, byte_domain="deep-mine-wrong-evidence")), "byte domain"),
            (replace(research, cas_ref=replace(research.cas_ref, size=0)), "positive size"),
            (replace(research, cas_ref=replace(research.cas_ref, sha256="0" * 64)), "does not bind"),
        )
        for bad_ref, message in mutations:
            refs = tuple(bad_ref if row.evidence_kind == bad_ref.evidence_kind else row for row in binding.evidence_cas_refs)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                build_promotion_candidate(
                    capability="greenSurface", product_role="greenSurfaceGeometry",
                    subject_ref="hole:layout-revision-1:31936-7",
                    projector_id="green-projector", quality_policy_version="green-quality-v1",
                    binding=replace(binding, evidence_cas_refs=refs),
                    closure_proofs=(proof,), fingerprints=(fingerprint,), unknowns=unknowns,
                    nodes={node.node_id: node}, capability_evidence=green,
                )

    def test_set_like_permutations_have_one_candidate_id_and_duplicates_fail_closed(self) -> None:
        _ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )

        def candidate_id(candidate_binding: PromotionBinding, evidence=green, capability: str = "greenSurface") -> str:
            provisional = PromotionCandidate(
                "", "research_only_candidate", "plan-2-capability-quality-gate", capability,
                "hole:layout-revision-1:31936-7", "green-projector", "quality-v1",
                candidate_binding, product_refs_for(candidate_binding, capability), evidence,
            )
            return typed_id("DeepMinePromotionCandidate/v1", provisional.payload())

        set_fields = {
            "source_revision_ids": binding.source_revision_ids,
            "raw_refs": (
                binding.raw_refs[0],
                CASRef(SECURITY_DOMAIN_ID, "raw-entity-alt", "a" * 64, 1),
            ),
            "derived_refs": (
                binding.derived_refs[0],
                CASRef(SECURITY_DOMAIN_ID, "derived-alt", "b" * 64, 1),
            ),
            "asset_refs": (
                binding.asset_refs[0],
                CASRef(SECURITY_DOMAIN_ID, "asset-alt", "c" * 64, 1),
            ),
            "closure_proof_ids": (binding.closure_proof_ids[0], "closure-2"),
            "fingerprint_ids": (binding.fingerprint_ids[0], "fingerprint-2"),
            "fingerprinted_artifact_ids": (binding.fingerprinted_artifact_ids[0], "artifact-2"),
            "unknown_ids": (binding.unknown_ids[0], "d" * 64),
            "consumed_node_ids": (binding.consumed_node_ids[0], "consumer-node-2"),
            "evidence_refs": binding.evidence_refs,
            "evidence_cas_refs": binding.evidence_cas_refs,
        }
        for field_name, values in set_fields.items():
            ids = {candidate_id(replace(binding, **{field_name: order})) for order in permutations(values)}
            self.assertEqual(ids, {candidate_id(replace(binding, **{field_name: values}))}, field_name)

        research_ref = next(
            row for row in binding.evidence_cas_refs if row.evidence_kind == "researchEvidenceReport"
        )
        nested_source_ids = set()
        for order in permutations(research_ref.source_revision_ids):
            reordered_ref = replace(research_ref, source_revision_ids=order)
            reordered_refs = tuple(
                reordered_ref if row.evidence_kind == reordered_ref.evidence_kind else row
                for row in binding.evidence_cas_refs
            )
            nested_source_ids.add(candidate_id(replace(binding, evidence_cas_refs=reordered_refs)))
        self.assertEqual(len(nested_source_ids), 1)

        (
            _plays_ref, plays_proof, plays_fingerprint, plays_unknowns,
            plays_node, plays_binding, plays_evidence,
        ) = evidence_fixture(
            capability="playsLike", product_role="playsLike.model",
        )
        anchor_ids = {
            candidate_id(plays_binding, replace(plays_evidence, calibration_anchor_ids=order), "playsLike")
            for order in permutations(plays_evidence.calibration_anchor_ids)
        }
        self.assertEqual(len(anchor_ids), 1)

        for field_name in set_fields:
            first = getattr(binding, field_name)[0]
            duplicate_binding = replace(binding, **{field_name: (first, first)})
            with self.subTest(field_name=field_name), self.assertRaisesRegex(ValueError, "duplicate"):
                build_promotion_candidate(
                    capability="greenSurface", product_role="greenSurfaceGeometry",
                    subject_ref="hole:layout-revision-1:31936-7",
                    projector_id="green-projector", quality_policy_version="green-quality-v1",
                    binding=duplicate_binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
                    unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
                )
        duplicate_anchors = replace(
            plays_evidence, calibration_anchor_ids=("tee-anchor", "tee-anchor", "green-anchor"),
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_promotion_candidate(
                capability="playsLike", product_role="playsLike.model",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="plays-quality-v1",
                binding=plays_binding, closure_proofs=(plays_proof,), fingerprints=(plays_fingerprint,),
                unknowns=plays_unknowns, nodes={plays_node.node_id: plays_node},
                capability_evidence=duplicate_anchors,
            )
        duplicate_sources = replace(
            research_ref,
            source_revision_ids=(research_ref.source_revision_ids[0], research_ref.source_revision_ids[0]),
        )
        duplicate_refs = tuple(
            duplicate_sources if row.evidence_kind == duplicate_sources.evidence_kind else row
            for row in binding.evidence_cas_refs
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_promotion_candidate(
                capability="greenSurface", product_role="greenSurfaceGeometry",
                subject_ref="hole:layout-revision-1:31936-7",
                projector_id="green-projector", quality_policy_version="green-quality-v1",
                binding=replace(binding, evidence_cas_refs=duplicate_refs),
                closure_proofs=(proof,), fingerprints=(fingerprint,), unknowns=unknowns,
                nodes={node.node_id: node}, capability_evidence=green,
            )

    def test_candidate_persists_in_shared_cas_and_module_has_no_publish_surface(self) -> None:
        parent_ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        candidate = build_promotion_candidate(
            capability="greenSurface", product_role="greenSurfaceGeometry",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector", quality_policy_version="green-quality-v1",
            binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
            unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
        )
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}))
            store = TrustedPromotionCandidateStore.open(Path(tmp) / "trusted", SECURITY_DOMAIN_ID)
            all_parents = put_fixture_parents(
                cas, binding, "greenSurface",
                product_role="greenSurfaceGeometry",
            )
            artifact = persist_promotion_candidate(
                candidate, cas=cas, trusted_candidate_store=store,
                closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=all_parents,
                decoder_version="promotion-1", build_hash="promotion-build-1",
            )
            self.assertEqual(artifact.ref.byte_domain, "deep-mine-promotion-candidate")
            self.assertIn(candidate.candidate_id.encode(), cas.read_bytes(SECURITY_DOMAIN_ID, artifact.ref))
            reordered = persist_promotion_candidate(
                candidate, cas=cas, trusted_candidate_store=store,
                closure_proofs=(proof,), fingerprints=(fingerprint,),
                unknowns=unknowns, nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=tuple(reversed(all_parents)),
                decoder_version="promotion-1", build_hash="promotion-build-1",
            )
            self.assertEqual(artifact.artifact_id, reordered.artifact_id)
            with self.assertRaisesRegex(ValueError, "exactly equal"):
                persist_promotion_candidate(
                    candidate, cas=cas, trusted_candidate_store=store,
                    closure_proofs=(proof,), fingerprints=(fingerprint,),
                    unknowns=unknowns, nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                    storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=all_parents[:-1],
                    decoder_version="promotion-1", build_hash="promotion-build-1",
                )
            with self.assertRaisesRegex(ValueError, "owner account"):
                persist_promotion_candidate(
                    candidate, cas=cas, trusted_candidate_store=store,
                    closure_proofs=(proof,), fingerprints=(fingerprint,),
                    unknowns=unknowns, nodes={node.node_id: node}, owner_account_id="account-b",
                    storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=all_parents,
                    decoder_version="promotion-1", build_hash="promotion-build-1",
                )
            store.close()
            reopened = TrustedPromotionCandidateStore.open(
                Path(tmp) / "trusted", SECURITY_DOMAIN_ID,
            )
            restarted = validate_untrusted_promotion_candidate(
                candidate.canonical(), cas=cas, trusted_candidate_store=reopened,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=all_parents,
                expected_owner_account_id=OWNER_ACCOUNT_ID,
                expected_course_layout_identity=binding.course_layout_identity,
                expected_layout_revision_id=binding.layout_revision_id,
                expected_hole_global_id=binding.hole_global_id,
                expected_source_revision_ids=binding.source_revision_ids,
                expected_source_roster_hash=binding.source_roster_hash,
            )
            self.assertEqual(restarted.trusted_record.artifact.artifact_id, artifact.artifact_id)
            reopened.close()
        root = Path("ai_caddie/research/deep_mine")
        for path in root.rglob("*.py"):
            source = path.read_text()
            for forbidden in (
                "ai_caddie.course_data.snapshot_builder",
                "ai_caddie.course_data.channels",
                "CourseReleaseChannel",
                "qualityReportHash",
                "def publish(",
                "publish_snapshot(",
                "publish_channel(",
                "advance_channel(",
            ):
                self.assertNotIn(forbidden, source, f"{path}: {forbidden}")

    def test_public_untrusted_admission_decodes_and_checks_exact_cas_context(self) -> None:
        parent_ref, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        candidate = build_promotion_candidate(
            capability="greenSurface", product_role="greenSurfaceGeometry",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector", quality_policy_version="green-quality-v1",
            binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
            unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
        )
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}))
            store = TrustedPromotionCandidateStore.open(Path(tmp) / "trusted", SECURITY_DOMAIN_ID)
            parents = put_fixture_parents(
                cas, binding, "greenSurface",
                product_role="greenSurfaceGeometry",
            )
            persist_promotion_candidate(
                candidate, cas=cas, trusted_candidate_store=store,
                closure_proofs=(proof,), fingerprints=(fingerprint,), unknowns=unknowns,
                nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=parents,
                decoder_version="promotion-1", build_hash="promotion-build-1",
            )
            admission = {
                "trusted_candidate_store": store,
                "storage_domain_id": SECURITY_DOMAIN_ID,
                "expected_owner_account_id": OWNER_ACCOUNT_ID,
                "expected_course_layout_identity": "layout-identity-1",
                "expected_layout_revision_id": "layout-revision-1",
                "expected_hole_global_id": "31936-7",
                "expected_source_revision_ids": binding.source_revision_ids,
                "expected_source_roster_hash": binding.source_roster_hash,
            }
            empty_store = TrustedPromotionCandidateStore.open(
                Path(tmp) / "empty-trusted", SECURITY_DOMAIN_ID,
            )
            with self.assertRaisesRegex(ValueError, "not in trusted Track C store"):
                validate_untrusted_promotion_candidate(
                    candidate.canonical(), cas=cas, parent_refs=parents,
                    **{**admission, "trusted_candidate_store": empty_store},
                )
            empty_store.close()
            validated = validate_untrusted_promotion_candidate(
                canonical_json_bytes(candidate.canonical()),
                cas=cas, parent_refs=tuple(reversed(parents)), **admission,
            )
            self.assertEqual(validated.candidate, candidate)
            self.assertEqual(
                validated.ordered_parent_refs,
                tuple(sorted(parents, key=lambda ref: (
                    ref.storage_domain_id, ref.byte_domain, ref.sha256, ref.size,
                ))),
            )

            same_bytes_other_domain = cas.put_bytes(
                SECURITY_DOMAIN_ID, "raw-alias", b"green-source",
            )
            wrong_parents = tuple(
                same_bytes_other_domain if ref == parent_ref else ref for ref in parents
            )
            with self.assertRaisesRegex(ValueError, "exactly equal"):
                validate_untrusted_promotion_candidate(
                    candidate.canonical(), cas=cas, parent_refs=wrong_parents, **admission,
                )

            noncanonical = candidate.canonical()
            noncanonical["binding"]["sourceRevisionIds"] = list(reversed(
                noncanonical["binding"]["sourceRevisionIds"],
            ))
            with self.assertRaisesRegex(ValueError, "canonical set order"):
                validate_untrusted_promotion_candidate(
                    noncanonical, cas=cas, parent_refs=parents, **admission,
                )

            with self.assertRaisesRegex(ValueError, "duplicate promotion key"):
                validate_untrusted_promotion_candidate(
                    b'{"candidateId":"' + candidate.candidate_id.encode() + b'","candidateId":"' + candidate.candidate_id.encode() + b'"}',
                    cas=cas, parent_refs=parents, **admission,
                )

            wrong_consumer = candidate.canonical()
            wrong_consumer["capabilityEvidence"]["consumerId"] = "other-projector"
            wrong_consumer["candidateId"] = typed_id(
                "DeepMinePromotionCandidate/v1",
                {key: value for key, value in wrong_consumer.items() if key != "candidateId"},
            )
            with self.assertRaisesRegex(ValueError, "consumer does not match projector"):
                validate_untrusted_promotion_candidate(
                    wrong_consumer, cas=cas, parent_refs=parents, **admission,
                )
            with self.assertRaisesRegex(ValueError, "source revision set is stale"):
                validate_untrusted_promotion_candidate(
                    candidate.canonical(), cas=cas, parent_refs=parents,
                    **{**admission, "expected_source_revision_ids": ("new-head",)},
                )
            with self.assertRaisesRegex(ValueError, "source roster hash is stale"):
                validate_untrusted_promotion_candidate(
                    candidate.canonical(), cas=cas, parent_refs=parents,
                    **{**admission, "expected_source_roster_hash": "e" * 64},
                )
            store.close()

    def test_trusted_record_rejects_provenance_domain_substitution_and_forged_rows(self) -> None:
        _parent, proof, fingerprint, unknowns, node, binding, green = evidence_fixture(
            capability="greenSurface", product_role="greenSurfaceGeometry",
        )
        candidate = build_promotion_candidate(
            capability="greenSurface", product_role="greenSurfaceGeometry",
            subject_ref="hole:layout-revision-1:31936-7",
            projector_id="green-projector", quality_policy_version="green-quality-v1",
            binding=binding, closure_proofs=(proof,), fingerprints=(fingerprint,),
            unknowns=unknowns, nodes={node.node_id: node}, capability_evidence=green,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cas = EncryptedCAS(root / "cas", StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}))
            store = TrustedPromotionCandidateStore.open(root / "trusted", SECURITY_DOMAIN_ID)
            parents = put_fixture_parents(
                cas, binding, "greenSurface",
                product_role="greenSurfaceGeometry",
            )
            persist_promotion_candidate(
                candidate, cas=cas, trusted_candidate_store=store,
                closure_proofs=(proof,), fingerprints=(fingerprint,), unknowns=unknowns,
                nodes={node.node_id: node}, owner_account_id=OWNER_ACCOUNT_ID,
                storage_domain_id=SECURITY_DOMAIN_ID, parent_refs=parents,
                decoder_version="promotion-1", build_hash="promotion-build-1",
            )
            record = store.get(candidate.candidate_id)
            original_row = record.canonical()
            provenance_bytes = cas.read_bytes(SECURITY_DOMAIN_ID, record.provenance_ref)
            admission = {
                "cas": cas,
                "trusted_candidate_store": store,
                "storage_domain_id": SECURITY_DOMAIN_ID,
                "parent_refs": parents,
                "expected_owner_account_id": OWNER_ACCOUNT_ID,
                "expected_course_layout_identity": binding.course_layout_identity,
                "expected_layout_revision_id": binding.layout_revision_id,
                "expected_hole_global_id": binding.hole_global_id,
                "expected_source_revision_ids": binding.source_revision_ids,
                "expected_source_roster_hash": binding.source_roster_hash,
            }

            def replace_sql_record(row: dict[str, object]) -> None:
                payload = {key: value for key, value in row.items() if key != "recordSha256"}
                row["recordSha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
                record_bytes = canonical_json_bytes(row)
                store.connection.execute(
                    """
                    UPDATE trusted_promotion_candidates
                    SET record_json = ?, record_sha256 = ?
                    WHERE storage_domain_id = ? AND candidate_id = ?
                    """,
                    (
                        record_bytes, hashlib.sha256(record_bytes).hexdigest(),
                        SECURITY_DOMAIN_ID, candidate.candidate_id,
                    ),
                )

            alias_ref = cas.put_bytes(
                SECURITY_DOMAIN_ID, "archive-member", provenance_bytes,
            )
            alias_row = json.loads(canonical_json_bytes(original_row))
            alias_row["provenanceRef"] = {
                "storageDomainId": alias_ref.storage_domain_id,
                "byteDomain": alias_ref.byte_domain,
                "sha256": alias_ref.sha256,
                "size": alias_ref.size,
            }
            replace_sql_record(alias_row)
            with self.assertRaisesRegex(ValueError, "artifact binding is invalid"):
                validate_untrusted_promotion_candidate(candidate.canonical(), **admission)

            forged = json.loads(provenance_bytes)
            forged["closureProofs"][0]["complete"] = False
            forged_bytes = canonical_json_bytes(forged)
            forged_ref = cas.put_bytes(
                SECURITY_DOMAIN_ID, "deep-mine-promotion-provenance", forged_bytes,
            )
            forged_row = json.loads(canonical_json_bytes(original_row))
            forged_row["provenanceHash"] = forged_ref.sha256
            forged_row["provenanceRef"] = {
                "storageDomainId": forged_ref.storage_domain_id,
                "byteDomain": forged_ref.byte_domain,
                "sha256": forged_ref.sha256,
                "size": forged_ref.size,
            }
            replace_sql_record(forged_row)
            with self.assertRaisesRegex(ValueError, "invalid proof identity"):
                validate_untrusted_promotion_candidate(candidate.canonical(), **admission)
            store.close()
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run python -m unittest tests.test_deep_mine_promotion -v`

Expected: FAIL importing `ai_caddie.research.deep_mine.promotion`.

- [ ] **Step 3: Implement immutable binding and strict capability-evidence union values**

```python
# ai_caddie/research/deep_mine/promotion.py
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Mapping, TypeAlias

from jsonschema import Draft202012Validator

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from .fingerprint import ArtifactFingerprint, DistributionSummary
from .ledger import ClosureProof
from .models import ByteDomain, NodeRecord, NodeStatus
from .provenance import DerivedArtifact, put_derived
from .unknowns import (
    UnknownEvidence, UnknownRecord, UnknownRegistry, UnknownStatus,
)


_EVIDENCE_BYTE_DOMAINS = {
    "researchEvidenceReport": "deep-mine-research-evidence-report",
    "playsLikeCalibration": "deep-mine-calibration-evidence",
    "hazardGuidanceSet": "deep-mine-hazard-set-evidence",
    "hazardCoverage": "deep-mine-hazard-coverage-evidence",
    "playableRegionsSourceInventory": (
        "deep-mine-playable-regions-source-inventory-evidence"
    ),
    "playableRegionsTopology": "deep-mine-playable-regions-topology-evidence",
    "playableRegionsCoverage": "deep-mine-playable-regions-coverage-evidence",
    "greenRegistration": "deep-mine-registration-report",
    "greenCrossSource": "deep-mine-cross-source-evidence",
}


def _ref_payload(ref: CASRef) -> dict[str, object]:
    return {
        "storageDomainId": ref.storage_domain_id,
        "byteDomain": ref.byte_domain,
        "sha256": ref.sha256,
        "size": ref.size,
    }


def _ref_identity(ref: CASRef) -> tuple[str, str, str, int]:
    return (ref.storage_domain_id, ref.byte_domain, ref.sha256, ref.size)


def _canonical_string_set(values: tuple[str, ...], label: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicate set-like values")
    return sorted(values)


def _canonical_cas_ref_set(values: tuple[CASRef, ...], label: str) -> list[dict[str, object]]:
    identities = [_ref_identity(value) for value in values]
    if len(set(identities)) != len(identities):
        raise ValueError(f"{label} contains duplicate set-like CAS refs")
    return [_ref_payload(value) for value in sorted(values, key=_ref_identity)]


@dataclass(frozen=True)
class SourceInventoryTrust:
    artifact_id: str
    record_sha256: str
    provenance_hash: str
    provenance_ref: CASRef

    def canonical(self) -> dict[str, object]:
        return {
            "artifactId": self.artifact_id,
            "recordSha256": self.record_sha256,
            "provenanceHash": self.provenance_hash,
            "provenanceRef": _ref_payload(self.provenance_ref),
        }


@dataclass(frozen=True)
class EvidenceCASRef:
    evidence_kind: str
    owner_account_id: str
    security_domain_id: str
    source_revision_ids: tuple[str, ...]
    cas_ref: CASRef
    source_inventory_trust: SourceInventoryTrust | None = None

    def canonical(self) -> dict[str, object]:
        payload = {
            "evidenceKind": self.evidence_kind,
            "ownerAccountId": self.owner_account_id,
            "securityDomainId": self.security_domain_id,
            "sourceRevisionIds": _canonical_string_set(
                self.source_revision_ids, "evidence sourceRevisionIds",
            ),
            "casRef": _ref_payload(self.cas_ref),
        }
        if self.source_inventory_trust is not None:
            payload["sourceInventoryTrust"] = self.source_inventory_trust.canonical()
        return payload


def _canonical_evidence_ref_set(values: tuple[EvidenceCASRef, ...]) -> list[dict[str, object]]:
    payloads = [value.canonical() for value in values]
    rows = [(canonical_json_bytes(payload), payload) for payload in payloads]
    if len({key for key, _payload in rows}) != len(rows):
        raise ValueError("evidenceCasRefs contains duplicate set-like values")
    return [payload for _key, payload in sorted(rows, key=lambda row: row[0])]


@dataclass(frozen=True)
class PromotionBinding:
    owner_account_id: str
    security_domain_id: str
    course_layout_identity: str
    layout_revision_id: str
    source_revision_ids: tuple[str, ...]
    source_roster_hash: str
    hole_global_id: str
    hole_number: int
    raw_refs: tuple[CASRef, ...]
    derived_refs: tuple[CASRef, ...]
    asset_refs: tuple[CASRef, ...]
    closure_proof_ids: tuple[str, ...]
    fingerprint_ids: tuple[str, ...]
    fingerprinted_artifact_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]
    consumed_node_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    evidence_cas_refs: tuple[EvidenceCASRef, ...]
    research_evidence_report_hash: str

    def canonical(self) -> dict[str, object]:
        return {
            "ownerAccountId": self.owner_account_id,
            "securityDomainId": self.security_domain_id,
            "courseLayoutIdentity": self.course_layout_identity,
            "layoutRevisionId": self.layout_revision_id,
            "sourceRevisionIds": _canonical_string_set(self.source_revision_ids, "sourceRevisionIds"),
            "sourceRosterHash": self.source_roster_hash,
            "holeGlobalId": self.hole_global_id,
            "holeNumber": self.hole_number,
            "rawRefs": _canonical_cas_ref_set(self.raw_refs, "rawRefs"),
            "derivedRefs": _canonical_cas_ref_set(self.derived_refs, "derivedRefs"),
            "assetRefs": _canonical_cas_ref_set(self.asset_refs, "assetRefs"),
            "closureProofIds": _canonical_string_set(self.closure_proof_ids, "closureProofIds"),
            "fingerprintIds": _canonical_string_set(self.fingerprint_ids, "fingerprintIds"),
            "fingerprintedArtifactIds": _canonical_string_set(
                self.fingerprinted_artifact_ids, "fingerprintedArtifactIds",
            ),
            "unknownIds": _canonical_string_set(self.unknown_ids, "unknownIds"),
            "consumedNodeIds": _canonical_string_set(self.consumed_node_ids, "consumedNodeIds"),
            "evidenceRefs": _canonical_string_set(self.evidence_refs, "evidenceRefs"),
            "evidenceCasRefs": _canonical_evidence_ref_set(self.evidence_cas_refs),
            "researchEvidenceReportHash": self.research_evidence_report_hash,
        }


@dataclass(frozen=True)
class PlaysLikeEvidence:
    source_revision_id: str
    axis_attestation_id: str
    horizontal_axis: str
    vertical_axis: str
    horizontal_unit: str
    vertical_unit: str
    model_version: str
    adjustment_per_vertical_meter: float
    calibration_anchor_ids: tuple[str, ...]
    max_anchor_distance_m: float
    residual_rmse_m: float
    max_abs_residual_m: float
    outlier_threshold_m: float
    outlier_count: int
    sample_count: int
    sample_course_count: int
    sample_region_count: int
    calibration_evidence_hash: str
    consumer_id: str

    def canonical(self) -> dict[str, object]:
        return {
            "evidenceKind": "playsLike",
            "sourceRevisionId": self.source_revision_id,
            "axisAttestationId": self.axis_attestation_id,
            "horizontalAxis": self.horizontal_axis,
            "verticalAxis": self.vertical_axis,
            "horizontalUnit": self.horizontal_unit,
            "verticalUnit": self.vertical_unit,
            "modelVersion": self.model_version,
            "adjustmentPerVerticalMeter": self.adjustment_per_vertical_meter,
            "calibrationAnchorIds": _canonical_string_set(
                self.calibration_anchor_ids, "calibrationAnchorIds",
            ),
            "maxAnchorDistanceM": self.max_anchor_distance_m,
            "residualRmseM": self.residual_rmse_m,
            "maxAbsResidualM": self.max_abs_residual_m,
            "outlierThresholdM": self.outlier_threshold_m,
            "outlierCount": self.outlier_count,
            "sampleCount": self.sample_count,
            "sampleCourseCount": self.sample_course_count,
            "sampleRegionCount": self.sample_region_count,
            "calibrationEvidenceHash": self.calibration_evidence_hash,
            "consumerId": self.consumer_id,
        }


@dataclass(frozen=True)
class HazardEvidenceRow:
    hazard_ref: str
    source_revision_id: str
    hazard_semantic_kind: str
    route_geometry_hash: str
    stationing_basis: str
    landing_window_hash: str
    base_geometry_hash: str
    enter_distance_m: float
    clear_distance_m: float | None
    evidence_hash: str

    def canonical(self) -> dict[str, object]:
        return {
            "hazardRef": self.hazard_ref,
            "sourceRevisionId": self.source_revision_id,
            "hazardSemanticKind": self.hazard_semantic_kind,
            "routeGeometryHash": self.route_geometry_hash,
            "stationingBasis": self.stationing_basis,
            "landingWindowHash": self.landing_window_hash,
            "baseGeometryHash": self.base_geometry_hash,
            "enterDistanceM": self.enter_distance_m,
            "clearDistanceM": self.clear_distance_m,
            "evidenceHash": self.evidence_hash,
        }


@dataclass(frozen=True)
class HazardGuidanceEvidence:
    source_revision_ids: tuple[str, ...]
    route_geometry_hash: str
    stationing_basis: str
    hazard_set_evidence_hash: str
    coverage_evidence_hash: str
    playable_regions_map_geometry_hash: str | None
    playable_regions_registration_residual_m: float | None
    playable_regions_topology_evidence_hash: str | None
    playable_regions_coverage_evidence_hash: str | None
    hazards: tuple[HazardEvidenceRow, ...]
    consumer_id: str

    def canonical(self) -> dict[str, object]:
        refs = [row.hazard_ref for row in self.hazards]
        if len(set(refs)) != len(refs):
            raise ValueError("hazards contains duplicate hazardRef values")
        return {
            "evidenceKind": "hazardGuidance",
            "sourceRevisionIds": _canonical_string_set(
                self.source_revision_ids, "hazard sourceRevisionIds",
            ),
            "routeGeometryHash": self.route_geometry_hash,
            "stationingBasis": self.stationing_basis,
            "hazardSetEvidenceHash": self.hazard_set_evidence_hash,
            "coverageEvidenceHash": self.coverage_evidence_hash,
            "playableRegionsMapGeometryHash": self.playable_regions_map_geometry_hash,
            "playableRegionsRegistrationResidualM": (
                self.playable_regions_registration_residual_m
            ),
            "playableRegionsTopologyEvidenceHash": (
                self.playable_regions_topology_evidence_hash
            ),
            "playableRegionsCoverageEvidenceHash": (
                self.playable_regions_coverage_evidence_hash
            ),
            "hazards": [
                row.canonical() for row in sorted(self.hazards, key=lambda row: row.hazard_ref)
            ],
            "consumerId": self.consumer_id,
        }


@dataclass(frozen=True)
class GreenSurfaceEvidence:
    green_source_revision_id: str
    base_source_revision_id: str
    green_source_sha256: str
    selected_component_id: str
    decoder_id: str
    decoder_version: str
    calibration_id: str
    orientation_transform_id: str
    base_geometry_hash: str
    slope_magnitude_pct: float
    downhill_direction_deg: float
    registration_residual_m: float
    cross_source_residual_m: float
    registration_sample_count: int
    registration_report_hash: str
    cross_source_evidence_hash: str
    consumer_id: str

    def canonical(self) -> dict[str, object]:
        return {
            "evidenceKind": "greenSurface",
            "greenSourceRevisionId": self.green_source_revision_id,
            "baseSourceRevisionId": self.base_source_revision_id,
            "greenSourceSha256": self.green_source_sha256,
            "selectedComponentId": self.selected_component_id,
            "decoderId": self.decoder_id,
            "decoderVersion": self.decoder_version,
            "calibrationId": self.calibration_id,
            "orientationTransformId": self.orientation_transform_id,
            "baseGeometryHash": self.base_geometry_hash,
            "slopeMagnitudePct": self.slope_magnitude_pct,
            "downhillDirectionDeg": self.downhill_direction_deg,
            "registrationResidualM": self.registration_residual_m,
            "crossSourceResidualM": self.cross_source_residual_m,
            "registrationSampleCount": self.registration_sample_count,
            "registrationReportHash": self.registration_report_hash,
            "crossSourceEvidenceHash": self.cross_source_evidence_hash,
            "consumerId": self.consumer_id,
        }


CapabilityEvidence: TypeAlias = PlaysLikeEvidence | HazardGuidanceEvidence | GreenSurfaceEvidence


_PRODUCT_CONTRACTS = {
    ("playsLike", "plays-like-model"): (
        "playsLike.model", "application/vnd.ai-caddie.plays-like+json",
        "ai-caddie-playsLike-body-v1", "plays-like-model",
    ),
    ("playsLike", "plays-like-elevation"): (
        "playsLike.elevation", "application/vnd.ai-caddie.plays-like-elevation+json",
        "ai-caddie-playsLike-elevation-v1", "plays-like-elevation",
    ),
    ("hazardGuidance", "hazard-guidance-body"): (
        "hazardGuidanceBody", "application/vnd.ai-caddie.hazard-guidance+json",
        "ai-caddie-hazardGuidance-body-v1", "hazard-guidance-body",
    ),
    ("hazardGuidance", "playable-regions"): (
        "guidance.playable-regions", "application/vnd.ai-caddie.playable-regions+json",
        "ai-caddie-playable-regions-v1", "playable-regions",
    ),
    ("greenSurface", "green-surface-geometry"): (
        "greenSurfaceGeometry", "application/vnd.ai-caddie.green-surface+json",
        "ai-caddie-greenSurface-body-v1", "green-surface-geometry",
    ),
}


@dataclass(frozen=True)
class PromotionProductRef:
    role: str
    media_type: str
    schema_id: str
    artifact_id: str
    byte_domain_id: str
    cas_ref: CASRef

    def canonical(self) -> dict[str, object]:
        return {
            "role": self.role,
            "mediaType": self.media_type,
            "schemaId": self.schema_id,
            "artifactId": self.artifact_id,
            "byteDomainId": self.byte_domain_id,
            "casRef": _ref_payload(self.cas_ref),
        }


def _product_refs_for(
    capability: str,
    product_role: str,
    binding: PromotionBinding,
    closure_proofs: Iterable[ClosureProof],
    fingerprints: Iterable[ArtifactFingerprint],
) -> tuple[PromotionProductRef, ...]:
    if len(binding.asset_refs) != 1:
        raise ValueError(
            f"{capability} requires exactly one runtime product asset per promotion candidate"
        )
    asset_ref = binding.asset_refs[0]
    try:
        role, media_type, schema_id, byte_domain = _PRODUCT_CONTRACTS[
            (capability, asset_ref.byte_domain)
        ]
    except KeyError as exc:
        raise ValueError(
            f"unsupported {capability} runtime product byte domain {asset_ref.byte_domain}"
        ) from exc
    if role != product_role:
        raise ValueError(
            "requested product_role does not match the bound runtime asset byte domain"
        )
    domain = ByteDomain.create(asset_ref, parent_domain_id=None, transform_id=None)
    proof_domains = {
        proof.byte_domain_id for proof in closure_proofs
        if proof.complete and proof.domain_size == asset_ref.size
    }
    matches = tuple(
        row for row in fingerprints
        if row.artifact_id in binding.fingerprinted_artifact_ids
        and row.fingerprint_id in binding.fingerprint_ids
        and row.content_fingerprint == asset_ref.sha256
        and row.byte_length == asset_ref.size
        and row.byte_domain_id == domain.domain_id
        and row.byte_domain_id in proof_domains
    )
    if len(matches) != 1:
        raise ValueError(f"{capability} runtime product requires one proved current fingerprint")
    product = matches[0]
    return (PromotionProductRef(
        role, media_type, schema_id, product.artifact_id,
        product.byte_domain_id, asset_ref,
    ),)


def _validate_product_refs(candidate: "PromotionCandidate") -> None:
    if len(candidate.product_refs) != 1:
        raise ValueError("promotion v1 requires exactly one logical-role runtime product per candidate")
    product = candidate.product_refs[0]
    try:
        role, media_type, schema_id, byte_domain = _PRODUCT_CONTRACTS[
            (candidate.capability, product.cas_ref.byte_domain)
        ]
    except KeyError as exc:
        raise ValueError("unsupported promotion product capability/byte-domain pair") from exc
    expected_domain = ByteDomain.create(
        product.cas_ref, parent_domain_id=None, transform_id=None,
    )
    if (
        product.role != role
        or product.media_type != media_type
        or product.schema_id != schema_id
        or product.cas_ref.byte_domain != byte_domain
        or product.cas_ref not in candidate.binding.asset_refs
        or not product.artifact_id
        or product.byte_domain_id != expected_domain.domain_id
    ):
        raise ValueError("promotion productRefs do not match capability runtime product contract")


_GEOMETRY_EPSILON = 1e-9
_MAX_PLAYABLE_REGIONS_BODY_BYTES = 2_000_000
_MAX_PLAYABLE_REGIONS = 256
_MAX_PLAYABLE_RINGS = 512
_MAX_PLAYABLE_POINTS = 4_096
_MAX_PLAYABLE_POINTS_PER_RING = 512
_MAX_GEOMETRY_PAIR_CHECKS = 4_000_000
_MAX_ABS_LOCAL_COORDINATE_M = 100_000.0


@dataclass
class _GeometryBudget:
    rings: int = 0
    points: int = 0
    pair_checks: int = 0

    def add_ring(self, point_count: int) -> None:
        if point_count > _MAX_PLAYABLE_POINTS_PER_RING:
            raise ValueError("playable ring point budget exceeded")
        self.rings += 1
        self.points += point_count
        if self.rings > _MAX_PLAYABLE_RINGS:
            raise ValueError("playable ring budget exceeded")
        if self.points > _MAX_PLAYABLE_POINTS:
            raise ValueError("playable point budget exceeded")

    def add_pair_check(self) -> None:
        self.pair_checks += 1
        if self.pair_checks > _MAX_GEOMETRY_PAIR_CHECKS:
            raise ValueError("playable O(n^2) geometry comparison budget exceeded")


def _require_playable_body_budget(data: bytes) -> None:
    if len(data) > _MAX_PLAYABLE_REGIONS_BODY_BYTES:
        raise ValueError("playable-regions body byte budget exceeded")


def _require_playable_region_count(raw: object) -> list[object]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("playable regions must be a nonempty canonical region set")
    if len(raw) > _MAX_PLAYABLE_REGIONS:
        raise ValueError("playable region budget exceeded")
    return raw


def _finite_result(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} overflowed or became non-finite")
    return value


def _finite_geometry_number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    if abs(number) > _MAX_ABS_LOCAL_COORDINATE_M:
        raise ValueError(f"{label} leaves the absolute local-coordinate envelope")
    return number


def _validated_map_geometry_envelope(
    raw: object,
) -> tuple[float, float, float, float]:
    if not isinstance(raw, dict) or set(raw) != {
        "minEastM", "minNorthM", "maxEastM", "maxNorthM",
    }:
        raise ValueError("mapGeometryEnvelope fields do not match schema")
    min_east = _finite_geometry_number(raw["minEastM"], "envelope minEastM")
    min_north = _finite_geometry_number(raw["minNorthM"], "envelope minNorthM")
    max_east = _finite_geometry_number(raw["maxEastM"], "envelope maxEastM")
    max_north = _finite_geometry_number(raw["maxNorthM"], "envelope maxNorthM")
    if min_east >= max_east or min_north >= max_north:
        raise ValueError("mapGeometryEnvelope must have positive finite area")
    return min_east, min_north, max_east, max_north


def _require_point_in_envelope(
    point: tuple[float, float],
    envelope: tuple[float, float, float, float],
    label: str,
) -> None:
    min_east, min_north, max_east, max_north = envelope
    if not (
        min_east <= point[0] <= max_east
        and min_north <= point[1] <= max_north
    ):
        raise ValueError(f"{label} leaves the bound mapGeometryEnvelope")


def _cross(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    ab_x = _finite_result(b[0] - a[0], "cross ab.x")
    ab_y = _finite_result(b[1] - a[1], "cross ab.y")
    ac_x = _finite_result(c[0] - a[0], "cross ac.x")
    ac_y = _finite_result(c[1] - a[1], "cross ac.y")
    left = _finite_result(ab_x * ac_y, "cross left product")
    right = _finite_result(ab_y * ac_x, "cross right product")
    return _finite_result(left - right, "cross result")


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    return (
        abs(_cross(start, end, point)) <= _GEOMETRY_EPSILON
        and min(start[0], end[0]) - _GEOMETRY_EPSILON
        <= point[0]
        <= max(start[0], end[0]) + _GEOMETRY_EPSILON
        and min(start[1], end[1]) - _GEOMETRY_EPSILON
        <= point[1]
        <= max(start[1], end[1]) + _GEOMETRY_EPSILON
    )


def _segment_relation(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> str:
    ab_c = _cross(a, b, c)
    ab_d = _cross(a, b, d)
    cd_a = _cross(c, d, a)
    cd_b = _cross(c, d, b)
    if (
        ((ab_c > _GEOMETRY_EPSILON and ab_d < -_GEOMETRY_EPSILON)
         or (ab_c < -_GEOMETRY_EPSILON and ab_d > _GEOMETRY_EPSILON))
        and ((cd_a > _GEOMETRY_EPSILON and cd_b < -_GEOMETRY_EPSILON)
             or (cd_a < -_GEOMETRY_EPSILON and cd_b > _GEOMETRY_EPSILON))
    ):
        return "proper_crossing"
    collinear = all(
        abs(value) <= _GEOMETRY_EPSILON
        for value in (ab_c, ab_d, cd_a, cd_b)
    )
    if collinear:
        axis = 0 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 1
        overlap_low = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        overlap_high = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        overlap = _finite_result(overlap_high - overlap_low, "collinear overlap")
        if overlap > _GEOMETRY_EPSILON:
            return "shared_boundary"
        if overlap >= -_GEOMETRY_EPSILON:
            return "boundary_touch"
        return "none"
    if (
        (abs(ab_c) <= _GEOMETRY_EPSILON and _point_on_segment(c, a, b))
        or (abs(ab_d) <= _GEOMETRY_EPSILON and _point_on_segment(d, a, b))
        or (abs(cd_a) <= _GEOMETRY_EPSILON and _point_on_segment(a, c, d))
        or (abs(cd_b) <= _GEOMETRY_EPSILON and _point_on_segment(b, c, d))
    ):
        return "boundary_touch"
    return "none"


def _shared_boundary_has_same_side_interior(
    left: tuple[tuple[float, float], tuple[float, float]],
    right: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    """All admitted rings orient region material to the left of each segment."""
    left_dx = _finite_result(left[1][0] - left[0][0], "shared edge left dx")
    left_dy = _finite_result(left[1][1] - left[0][1], "shared edge left dy")
    right_dx = _finite_result(right[1][0] - right[0][0], "shared edge right dx")
    right_dy = _finite_result(right[1][1] - right[0][1], "shared edge right dy")
    dot_x = _finite_result(left_dx * right_dx, "shared edge dot x")
    dot_y = _finite_result(left_dy * right_dy, "shared edge dot y")
    dot = _finite_result(dot_x + dot_y, "shared edge direction dot")
    if abs(dot) <= _GEOMETRY_EPSILON:
        raise ValueError("shared boundary contains a zero-length or unstable segment")
    return dot > 0.0


def _ring_segments(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    return tuple(zip(points[:-1], points[1:], strict=True))


def _signed_twice_area(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for start, end in _ring_segments(points):
        left = _finite_result(start[0] * end[1], "ring area left product")
        right = _finite_result(end[0] * start[1], "ring area right product")
        term = _finite_result(left - right, "ring area term")
        total = _finite_result(total + term, "ring area accumulator")
    return total


def _validated_ring_points(
    raw: object,
    label: str,
    *,
    envelope: tuple[float, float, float, float],
    budget: _GeometryBudget,
) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list) or len(raw) < 4:
        raise ValueError(f"{label} must contain at least three vertices plus closure")
    budget.add_ring(len(raw))
    points: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, dict) or set(point) != {"eastM", "northM"}:
            raise ValueError(f"{label} point fields do not match schema")
        point_value = (
            _finite_geometry_number(point["eastM"], f"{label} eastM"),
            _finite_geometry_number(point["northM"], f"{label} northM"),
        )
        _require_point_in_envelope(point_value, envelope, label)
        points.append(point_value)
    if points[0] != points[-1]:
        raise ValueError(f"{label} must be explicitly closed")
    vertices = points[:-1]
    if len(vertices) < 3 or len(set(vertices)) != len(vertices):
        raise ValueError(f"{label} must have unique non-closure vertices")
    if vertices[0] != min(vertices):
        raise ValueError(
            f"{label} points must start at the lexicographically minimum coordinate"
        )
    closed = tuple(points)
    if abs(_signed_twice_area(closed)) <= _GEOMETRY_EPSILON:
        raise ValueError(f"{label} is degenerate")
    segments = _ring_segments(closed)
    for left in range(len(segments)):
        for right in range(left + 1, len(segments)):
            if right == left + 1 or (left == 0 and right == len(segments) - 1):
                continue
            budget.add_pair_check()
            if _segment_relation(*segments[left], *segments[right]) != "none":
                raise ValueError(f"{label} is not simple")
    return closed


def _point_location_in_ring(
    point: tuple[float, float],
    ring: tuple[tuple[float, float], ...],
) -> int:
    for start, end in _ring_segments(ring):
        if _point_on_segment(point, start, end):
            return 0
    inside = False
    x, y = point
    for start, end in _ring_segments(ring):
        if (start[1] > y) != (end[1] > y):
            offset_y = _finite_result(y - start[1], "point-in-ring offset y")
            segment_dx = _finite_result(
                end[0] - start[0], "point-in-ring segment dx",
            )
            segment_dy = _finite_result(
                end[1] - start[1], "point-in-ring segment dy",
            )
            numerator = _finite_result(
                offset_y * segment_dx, "point-in-ring numerator",
            )
            fraction = _finite_result(
                numerator / segment_dy, "point-in-ring fraction",
            )
            crossing_x = _finite_result(
                start[0] + fraction, "point-in-ring crossing",
            )
            if crossing_x > x:
                inside = not inside
    return 1 if inside else -1


def _rings_overlap_or_touch(
    left: tuple[tuple[float, float], ...],
    right: tuple[tuple[float, float], ...],
    *,
    budget: _GeometryBudget,
) -> bool:
    for left_segment in _ring_segments(left):
        for right_segment in _ring_segments(right):
            budget.add_pair_check()
            if _segment_relation(*left_segment, *right_segment) != "none":
                return True
    return (
        _point_location_in_ring(left[0], right) == 1
        or _point_location_in_ring(right[0], left) == 1
    )


def _point_location_in_region(
    point: tuple[float, float],
    outers: tuple[tuple[tuple[float, float], ...], ...],
    holes: tuple[tuple[tuple[float, float], ...], ...],
) -> int:
    for ring in (*outers, *holes):
        if _point_location_in_ring(point, ring) == 0:
            return 0
    if not any(_point_location_in_ring(point, outer) == 1 for outer in outers):
        return -1
    if any(_point_location_in_ring(point, hole) == 1 for hole in holes):
        return -1
    return 1


def _validate_playable_regions(
    raw: object,
    *,
    topology_evidence_hash: str,
    map_geometry_envelope: object,
) -> tuple[
    list[str],
    tuple[tuple[
        str,
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
    ], ...],
]:
    raw = _require_playable_region_count(raw)
    envelope = _validated_map_geometry_envelope(map_geometry_envelope)
    budget = _GeometryBudget()
    region_refs: list[str] = []
    global_ring_refs: set[str] = set()
    geometries: list[tuple[
        str,
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
    ]] = []
    for region in raw:
        if not isinstance(region, dict) or set(region) != {
            "regionRef", "lieKind", "rings", "evidenceRefs",
        }:
            raise ValueError("playable region fields do not match schema")
        region_ref = region["regionRef"]
        if not isinstance(region_ref, str) or not region_ref:
            raise ValueError("playable regionRef is invalid")
        if region["lieKind"] not in {
            "fairway", "rough", "bunker", "green", "penalty_area", "out_of_bounds",
        }:
            raise ValueError("playable region lieKind is invalid")
        if region["evidenceRefs"] != [topology_evidence_hash]:
            raise ValueError("playable region evidenceRefs do not exactly bind topology")
        rings = region["rings"]
        if not isinstance(rings, list) or not rings:
            raise ValueError("playable region rings must be nonempty")
        ring_keys: list[tuple[int, str]] = []
        outers: list[tuple[tuple[float, float], ...]] = []
        holes: list[tuple[tuple[float, float], ...]] = []
        all_rings: list[tuple[tuple[float, float], ...]] = []
        for ring in rings:
            if not isinstance(ring, dict) or set(ring) != {
                "ringRef", "ringRole", "points",
            }:
                raise ValueError("playable region ring fields do not match schema")
            ring_ref = ring["ringRef"]
            role = ring["ringRole"]
            if (
                not isinstance(ring_ref, str) or not ring_ref
                or role not in {"outer", "hole"}
                or ring_ref in global_ring_refs
            ):
                raise ValueError("playable ring identity or role is invalid")
            global_ring_refs.add(ring_ref)
            points = _validated_ring_points(
                ring["points"], f"playable ring {ring_ref}",
                envelope=envelope, budget=budget,
            )
            area = _signed_twice_area(points)
            if role == "outer" and area <= _GEOMETRY_EPSILON:
                raise ValueError("playable outer rings must be counter-clockwise")
            if role == "hole" and area >= -_GEOMETRY_EPSILON:
                raise ValueError("playable hole rings must be clockwise")
            ring_keys.append((0 if role == "outer" else 1, ring_ref))
            (outers if role == "outer" else holes).append(points)
            all_rings.append(points)
        if ring_keys != sorted(set(ring_keys)):
            raise ValueError("playable rings are not canonical by role and ringRef")
        if not outers:
            raise ValueError("playable region requires at least one outer ring")
        for index, outer in enumerate(outers):
            if any(
                _rings_overlap_or_touch(outer, other, budget=budget)
                for other in outers[index + 1:]
            ):
                raise ValueError("playable outer rings overlap or touch")
        for index, hole in enumerate(holes):
            if any(
                _rings_overlap_or_touch(hole, other, budget=budget)
                for other in holes[index + 1:]
            ):
                raise ValueError("playable hole rings overlap or touch")
            for outer in outers:
                for hole_segment in _ring_segments(hole):
                    for outer_segment in _ring_segments(outer):
                        budget.add_pair_check()
                        if _segment_relation(*hole_segment, *outer_segment) != "none":
                            raise ValueError("playable hole touches or crosses an outer ring")
            containing_outers = sum(
                _point_location_in_ring(hole[0], outer) == 1 for outer in outers
            )
            if containing_outers != 1:
                raise ValueError("playable hole must be strictly inside exactly one outer ring")
        region_refs.append(region_ref)
        geometries.append((
            region_ref, tuple(outers), tuple(holes), tuple(all_rings),
        ))
    if region_refs != sorted(set(region_refs)):
        raise ValueError("playable regions are not canonical by regionRef")
    for left_index, (_left_ref, left_outers, left_holes, left_rings) in enumerate(
        geometries
    ):
        for _right_ref, right_outers, right_holes, right_rings in geometries[
            left_index + 1:
        ]:
            proper_crossing = False
            same_side_shared_boundary = False
            for left_ring in left_rings:
                for right_ring in right_rings:
                    for left_segment in _ring_segments(left_ring):
                        for right_segment in _ring_segments(right_ring):
                            budget.add_pair_check()
                            relation = _segment_relation(
                                *left_segment, *right_segment,
                            )
                            if relation == "proper_crossing":
                                proper_crossing = True
                            elif relation == "shared_boundary" and (
                                _shared_boundary_has_same_side_interior(
                                    left_segment, right_segment,
                                )
                            ):
                                same_side_shared_boundary = True
            left_inside_right = any(
                _point_location_in_region(point, right_outers, right_holes) == 1
                for outer in left_outers
                for point in outer[:-1]
            )
            right_inside_left = any(
                _point_location_in_region(point, left_outers, left_holes) == 1
                for outer in right_outers
                for point in outer[:-1]
            )
            if proper_crossing:
                raise ValueError("playable region boundaries have a proper crossing")
            if (
                same_side_shared_boundary
                or left_inside_right
                or right_inside_left
            ):
                raise ValueError("playable region interiors overlap")
    return region_refs, tuple(geometries)


def _classify_validated_playable_region_point(
    geometries: tuple[tuple[
        str,
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
        tuple[tuple[tuple[float, float], ...], ...],
    ], ...],
    point: tuple[float, float],
) -> str | None:
    """Defensive last step for already validated geometry; never breaks ties."""
    matches: list[str] = []
    for region_ref, outers, holes, _rings in geometries:
        location = _point_location_in_region(point, outers, holes)
        if location == 0:
            return None
        if location == 1:
            matches.append(region_ref)
    return matches[0] if len(matches) == 1 else None


def classify_playable_region_point(
    raw: object,
    *,
    east_m: object,
    north_m: object,
    topology_evidence_hash: str,
    map_geometry_envelope: object,
) -> str | None:
    """Return one strict interior match; invalid/boundary/multi-match is unavailable."""
    try:
        _refs, geometries = _validate_playable_regions(
            raw,
            topology_evidence_hash=topology_evidence_hash,
            map_geometry_envelope=map_geometry_envelope,
        )
        point = (
            _finite_geometry_number(east_m, "runtime eastM"),
            _finite_geometry_number(north_m, "runtime northM"),
        )
        _require_point_in_envelope(
            point,
            _validated_map_geometry_envelope(map_geometry_envelope),
            "runtime point",
        )
    except ValueError:
        return None
    return _classify_validated_playable_region_point(geometries, point)


def _playable_regions_hash(regions: object) -> str:
    if not isinstance(regions, list):
        raise ValueError("playable regions payload is invalid")
    stripped = [{
        "regionRef": region["regionRef"],
        "lieKind": region["lieKind"],
        "rings": region["rings"],
    } for region in regions]
    return hashlib.sha256(canonical_json_bytes(stripped)).hexdigest()


def validate_promotion_product_bytes(
    product: PromotionProductRef,
    data: bytes,
    capability_evidence: CapabilityEvidence,
) -> dict[str, object]:
    if product.role == "guidance.playable-regions":
        _require_playable_body_budget(data)

    def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f"duplicate runtime product key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite runtime product number: {value}")

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime product is not strict JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError("runtime product bytes are not canonical JSON")

    def exact(required: set[str]) -> None:
        if set(value) != required:
            raise ValueError("runtime product fields do not match schema")

    def strings(raw: object, label: str) -> list[str]:
        if (
            not isinstance(raw, list) or not raw
            or any(not isinstance(item, str) or not item for item in raw)
            or raw != sorted(set(raw))
        ):
            raise ValueError(f"{label} must be a canonical nonempty string set")
        return raw

    if product.role == "playsLike.model":
        exact({"schema", "modelVersion", "adjustmentPerVerticalMeter", "modelEvidenceRefs"})
        if (
            value["schema"] != product.schema_id
            or not isinstance(value["modelVersion"], str) or not value["modelVersion"]
            or not isinstance(value["adjustmentPerVerticalMeter"], (int, float))
            or isinstance(value["adjustmentPerVerticalMeter"], bool)
            or not math.isfinite(float(value["adjustmentPerVerticalMeter"]))
            or not -5.0 <= float(value["adjustmentPerVerticalMeter"]) <= 5.0
        ):
            raise ValueError("playsLike runtime product is invalid")
        strings(value["modelEvidenceRefs"], "modelEvidenceRefs")
        if not isinstance(capability_evidence, PlaysLikeEvidence) or (
            value["modelVersion"] != capability_evidence.model_version
            or float(value["adjustmentPerVerticalMeter"])
            != capability_evidence.adjustment_per_vertical_meter
            or value["modelEvidenceRefs"] != [capability_evidence.calibration_evidence_hash]
        ):
            raise ValueError("playsLike runtime product does not match capability evidence")
    elif product.role == "playsLike.elevation":
        exact({
            "schema", "layoutRevisionId", "holeGlobalId", "subjectRef",
            "mapGeometryHash", "horizontalCrs", "verticalDatumId",
            "horizontalUnit", "verticalUnit", "origin",
            "maximumAnchorDistanceM", "maximumInterpolationResidualM",
            "samples", "triangles", "evidenceRefs",
        })
        origin = value["origin"]
        samples = value["samples"]
        triangles = value["triangles"]
        if (
            value["schema"] != product.schema_id
            or value["horizontalCrs"] != "local-enu-wgs84-v1"
            or value["horizontalUnit"] != "meter"
            or value["verticalUnit"] != "meter"
            or not isinstance(value["verticalDatumId"], str)
            or not value["verticalDatumId"]
            or not isinstance(origin, dict)
            or set(origin) != {"latitudeDeg", "longitudeDeg", "elevationM"}
            or not isinstance(samples, list) or len(samples) < 3
            or not isinstance(triangles, list) or not triangles
            or not re.fullmatch(r"[0-9a-f]{64}", value["mapGeometryHash"])
        ):
            raise ValueError("playsLike elevation product header is invalid")
        for key, lower, upper in (
            ("latitudeDeg", -90.0, 90.0),
            ("longitudeDeg", -180.0, 180.0),
        ):
            number = origin[key]
            if (
                not isinstance(number, (int, float)) or isinstance(number, bool)
                or not math.isfinite(float(number)) or not lower <= float(number) <= upper
            ):
                raise ValueError("playsLike elevation origin is invalid")
        if (
            not isinstance(origin["elevationM"], (int, float))
            or isinstance(origin["elevationM"], bool)
            or not math.isfinite(float(origin["elevationM"]))
        ):
            raise ValueError("playsLike elevation origin is invalid")
        sample_refs: list[str] = []
        sample_points: dict[str, tuple[float, float]] = {}
        for sample in samples:
            if not isinstance(sample, dict) or set(sample) != {
                "sampleRef", "eastM", "northM", "elevationM",
                "anchorDistanceM", "anchorResidualM",
            }:
                raise ValueError("playsLike elevation sample is invalid")
            ref = sample["sampleRef"]
            numbers = tuple(sample[key] for key in (
                "eastM", "northM", "elevationM", "anchorDistanceM", "anchorResidualM",
            ))
            if (
                not isinstance(ref, str) or not ref
                or any(not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(float(item)) for item in numbers)
                or float(sample["anchorDistanceM"]) < 0.0
                or float(sample["anchorResidualM"]) < 0.0
            ):
                raise ValueError("playsLike elevation sample is invalid")
            sample_refs.append(ref)
            sample_points[ref] = (float(sample["eastM"]), float(sample["northM"]))
        if sample_refs != sorted(set(sample_refs)):
            raise ValueError("playsLike elevation samples are not canonical by sampleRef")
        triangle_refs: list[str] = []
        used_triangles: set[tuple[str, str, str]] = set()
        for triangle in triangles:
            if not isinstance(triangle, dict) or set(triangle) != {"triangleRef", "sampleRefs"}:
                raise ValueError("playsLike elevation triangle is invalid")
            triangle_ref = triangle["triangleRef"]
            refs = triangle["sampleRefs"]
            if (
                not isinstance(triangle_ref, str) or not triangle_ref
                or not isinstance(refs, list) or len(refs) != 3
                or refs != sorted(set(refs))
                or any(ref not in sample_points for ref in refs)
                or tuple(refs) in used_triangles
            ):
                raise ValueError("playsLike elevation triangle is invalid")
            a, b, c = (sample_points[ref] for ref in refs)
            twice_area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(twice_area) < 1e-9:
                raise ValueError("playsLike elevation triangle is degenerate")
            triangle_refs.append(triangle_ref)
            used_triangles.add(tuple(refs))
        if triangle_refs != sorted(set(triangle_refs)):
            raise ValueError("playsLike elevation triangles are not canonical by triangleRef")
        maximum_anchor_distance = value["maximumAnchorDistanceM"]
        maximum_residual = value["maximumInterpolationResidualM"]
        if (
            not isinstance(maximum_anchor_distance, (int, float))
            or isinstance(maximum_anchor_distance, bool)
            or not math.isfinite(float(maximum_anchor_distance))
            or float(maximum_anchor_distance) < 0.0
            or not isinstance(maximum_residual, (int, float))
            or isinstance(maximum_residual, bool)
            or not math.isfinite(float(maximum_residual))
            or float(maximum_residual) < 0.0
            or any(float(sample["anchorDistanceM"]) > float(maximum_anchor_distance) for sample in samples)
            or any(float(sample["anchorResidualM"]) > float(maximum_residual) for sample in samples)
        ):
            raise ValueError("playsLike elevation confidence envelope is invalid")
        strings(value["evidenceRefs"], "playsLike elevation evidenceRefs")
        if not isinstance(capability_evidence, PlaysLikeEvidence) or (
            float(maximum_anchor_distance) != capability_evidence.max_anchor_distance_m
            or float(maximum_residual) != capability_evidence.max_abs_residual_m
            or value["evidenceRefs"] != [capability_evidence.calibration_evidence_hash]
        ):
            raise ValueError("playsLike elevation product does not match capability evidence")
    elif product.role == "hazardGuidanceBody":
        exact({"schema", "routeGeometryHash", "stationingBasis", "hazards"})
        hazards = value["hazards"]
        if (
            value["schema"] != product.schema_id
            or not re.fullmatch(r"[0-9a-f]{64}", value["routeGeometryHash"])
            or value["stationingBasis"] != "tee-origin-route-station-v1"
            or not isinstance(hazards, list)
        ):
            raise ValueError("hazard runtime product is invalid")
        refs: list[str] = []
        for row in hazards:
            if not isinstance(row, dict) or set(row) != {
                "hazardRef", "kind", "enterDistanceM", "clearDistanceM", "evidenceRefs",
            }:
                raise ValueError("hazard runtime product row is invalid")
            if row["kind"] not in {
                "bunker", "water", "penalty_area", "vegetation",
                "out_of_bounds", "forced_carry", "layup",
            }:
                raise ValueError("hazard runtime product kind is invalid")
            enter = row["enterDistanceM"]
            clear = row["clearDistanceM"]
            if (
                not isinstance(row["hazardRef"], str) or not row["hazardRef"]
                or not isinstance(enter, (int, float)) or isinstance(enter, bool)
                or not math.isfinite(float(enter)) or float(enter) < 0
                or (clear is not None and (
                    not isinstance(clear, (int, float)) or isinstance(clear, bool)
                    or not math.isfinite(float(clear)) or float(clear) < float(enter)
                ))
            ):
                raise ValueError("hazard runtime product distance is invalid")
            strings(row["evidenceRefs"], "hazard evidenceRefs")
            refs.append(row["hazardRef"])
        if refs != sorted(set(refs)):
            raise ValueError("hazard rows must be unique and canonical by hazardRef")
        if not isinstance(capability_evidence, HazardGuidanceEvidence) or (
            value["routeGeometryHash"] != capability_evidence.route_geometry_hash
            or value["stationingBasis"] != capability_evidence.stationing_basis
        ):
            raise ValueError("hazard runtime product does not match capability evidence")
        expected = sorted(capability_evidence.hazards, key=lambda item: item.hazard_ref)
        if len(hazards) != len(expected):
            raise ValueError("hazard runtime product does not match capability evidence")
        for row, evidence in zip(hazards, expected, strict=True):
            if (
                row["hazardRef"] != evidence.hazard_ref
                or row["kind"] != evidence.hazard_semantic_kind
                or float(row["enterDistanceM"]) != evidence.enter_distance_m
                or row["clearDistanceM"] != evidence.clear_distance_m
                or row["evidenceRefs"] != [evidence.evidence_hash]
            ):
                raise ValueError("hazard runtime product does not match capability evidence")
    elif product.role == "guidance.playable-regions":
        exact({
            "schema", "layoutRevisionId", "holeGlobalId", "subjectRef",
            "mapGeometryHash", "mapGeometryEnvelope", "horizontalCrs", "horizontalUnit",
            "registrationResidualM", "maximumRegistrationResidualM",
            "sourceInventoryEvidenceHash", "topologyEvidenceHash",
            "coverageEvidenceHash", "regions", "evidenceRefs",
        })
        _validated_map_geometry_envelope(value["mapGeometryEnvelope"])
        registration_residual = _finite_geometry_number(
            value["registrationResidualM"], "playable registrationResidualM",
        )
        maximum_registration_residual = _finite_geometry_number(
            value["maximumRegistrationResidualM"],
            "playable maximumRegistrationResidualM",
        )
        if (
            value["schema"] != product.schema_id
            or not isinstance(value["layoutRevisionId"], str)
            or not value["layoutRevisionId"]
            or not isinstance(value["holeGlobalId"], str)
            or not value["holeGlobalId"]
            or value["subjectRef"]
            != f"hole:{value['layoutRevisionId']}:{value['holeGlobalId']}"
            or value["horizontalCrs"] != "local-enu-wgs84-v1"
            or value["horizontalUnit"] != "meter"
            or any(
                not isinstance(value[key], str)
                or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
                for key in (
                    "mapGeometryHash", "sourceInventoryEvidenceHash",
                    "topologyEvidenceHash", "coverageEvidenceHash",
                )
            )
            or registration_residual < 0.0
            or maximum_registration_residual < 0.0
            or registration_residual > maximum_registration_residual
        ):
            raise ValueError("playable-regions runtime product header is invalid")
        topology_hash = value["topologyEvidenceHash"]
        coverage_hash = value["coverageEvidenceHash"]
        source_inventory_hash = value["sourceInventoryEvidenceHash"]
        strings(value["evidenceRefs"], "playable-regions evidenceRefs")
        if value["evidenceRefs"] != sorted([
            source_inventory_hash, topology_hash, coverage_hash,
        ]):
            raise ValueError(
                "playable-regions evidenceRefs do not exactly bind source inventory, "
                "topology, and coverage"
            )
        _validate_playable_regions(
            value["regions"],
            topology_evidence_hash=topology_hash,
            map_geometry_envelope=value["mapGeometryEnvelope"],
        )
        if not isinstance(capability_evidence, HazardGuidanceEvidence) or any(
            field is None for field in (
                capability_evidence.playable_regions_map_geometry_hash,
                capability_evidence.playable_regions_registration_residual_m,
                capability_evidence.playable_regions_topology_evidence_hash,
                capability_evidence.playable_regions_coverage_evidence_hash,
            )
        ):
            raise ValueError(
                "playable-regions runtime product lacks typed capability evidence"
            )
        if (
            value["mapGeometryHash"]
            != capability_evidence.playable_regions_map_geometry_hash
            or registration_residual
            != capability_evidence.playable_regions_registration_residual_m
            or topology_hash
            != capability_evidence.playable_regions_topology_evidence_hash
            or coverage_hash
            != capability_evidence.playable_regions_coverage_evidence_hash
        ):
            raise ValueError(
                "playable-regions runtime product does not match capability evidence"
            )
    elif product.role == "greenSurfaceGeometry":
        exact({
            "schema", "sourceHash", "componentId", "decoderVersion", "calibrationVersion",
            "orientationTransformId", "orientationTransform", "baseGeometryHash", "slopeMagnitudePct",
            "downhillDirectionDeg", "registrationResidualM", "crossSourceResidualM",
            "registrationSampleCount", "evidenceRefs",
        })
        transform = value["orientationTransform"]
        slope = value["slopeMagnitudePct"]
        direction = value["downhillDirectionDeg"]
        registration_residual = value["registrationResidualM"]
        cross_source_residual = value["crossSourceResidualM"]
        sample_count = value["registrationSampleCount"]
        if (
            value["schema"] != product.schema_id
            or any(not isinstance(value[key], str) or not value[key] for key in (
                "componentId", "decoderVersion", "calibrationVersion", "orientationTransformId",
            ))
            or any(not re.fullmatch(r"[0-9a-f]{64}", value[key]) for key in (
                "sourceHash", "baseGeometryHash",
            ))
            or not isinstance(transform, list) or len(transform) != 6
            or any(not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(float(item)) for item in transform)
            or abs(float(transform[0]) * float(transform[3]) - float(transform[1]) * float(transform[2])) < 1e-12
            or not isinstance(slope, (int, float)) or isinstance(slope, bool)
            or not math.isfinite(float(slope)) or not 0.0 <= float(slope) <= 100.0
            or not isinstance(direction, (int, float)) or isinstance(direction, bool)
            or not math.isfinite(float(direction)) or not 0.0 <= float(direction) < 360.0
            or not isinstance(registration_residual, (int, float)) or isinstance(registration_residual, bool)
            or not math.isfinite(float(registration_residual)) or float(registration_residual) < 0.0
            or not isinstance(cross_source_residual, (int, float)) or isinstance(cross_source_residual, bool)
            or not math.isfinite(float(cross_source_residual)) or float(cross_source_residual) < 0.0
            or not isinstance(sample_count, int) or isinstance(sample_count, bool)
            or not 3 <= sample_count <= 9_007_199_254_740_991
        ):
            raise ValueError("greenSurface runtime product is invalid")
        expected_transform_id = typed_id(
            "DeepMineGreenOrientationTransform/v1",
            {"matrix": [float(item) for item in transform]},
        )
        strings(value["evidenceRefs"], "greenSurface evidenceRefs")
        if not isinstance(capability_evidence, GreenSurfaceEvidence) or (
            value["sourceHash"] != capability_evidence.green_source_sha256
            or value["componentId"] != capability_evidence.selected_component_id
            or value["decoderVersion"] != capability_evidence.decoder_version
            or value["calibrationVersion"] != capability_evidence.calibration_id
            or value["orientationTransformId"] != expected_transform_id
            or expected_transform_id != capability_evidence.orientation_transform_id
            or value["baseGeometryHash"] != capability_evidence.base_geometry_hash
            or float(value["slopeMagnitudePct"]) != capability_evidence.slope_magnitude_pct
            or float(value["downhillDirectionDeg"]) != capability_evidence.downhill_direction_deg
            or float(value["registrationResidualM"]) != capability_evidence.registration_residual_m
            or float(value["crossSourceResidualM"]) != capability_evidence.cross_source_residual_m
            or value["registrationSampleCount"] != capability_evidence.registration_sample_count
            or value["evidenceRefs"] != sorted([
                capability_evidence.registration_report_hash,
                capability_evidence.cross_source_evidence_hash,
            ])
        ):
            raise ValueError("greenSurface runtime product does not match capability evidence")
    else:
        raise ValueError("unsupported runtime product role")
    return value


@dataclass(frozen=True)
class PromotionCandidate:
    candidate_id: str
    candidate_state: str
    target_gate: str
    capability: str
    subject_ref: str
    projector_id: str
    quality_policy_version: str
    binding: PromotionBinding
    product_refs: tuple[PromotionProductRef, ...]
    capability_evidence: CapabilityEvidence

    def payload(self) -> dict[str, object]:
        return {
            "candidateState": self.candidate_state,
            "targetGate": self.target_gate,
            "capability": self.capability,
            "subjectRef": self.subject_ref,
            "projectorId": self.projector_id,
            "qualityPolicyVersion": self.quality_policy_version,
            "binding": self.binding.canonical(),
            "productRefs": [value.canonical() for value in self.product_refs],
            "capabilityEvidence": self.capability_evidence.canonical(),
        }

    def canonical(self) -> dict[str, object]:
        return {"candidateId": self.candidate_id, **self.payload()}


def validate_candidate_schema(candidate: PromotionCandidate | Mapping[str, object]) -> None:
    payload = candidate.canonical() if isinstance(candidate, PromotionCandidate) else dict(candidate)
    schema_path = Path(__file__).resolve().parents[3] / "contracts/canonical/deep_mine_v1.schema.json"
    schema = json.loads(schema_path.read_text())
    admission_schema = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/promotionCandidate",
        "$defs": schema["$defs"],
    }
    Draft202012Validator.check_schema(admission_schema)
    Draft202012Validator(admission_schema).validate(payload)


def _decode_cas_ref(value: Mapping[str, object]) -> CASRef:
    return CASRef(
        storage_domain_id=value["storageDomainId"],
        byte_domain=value["byteDomain"],
        sha256=value["sha256"],
        size=value["size"],
    )


def _decode_evidence_cas_ref(value: Mapping[str, object]) -> EvidenceCASRef:
    trust = value.get("sourceInventoryTrust")
    return EvidenceCASRef(
        evidence_kind=value["evidenceKind"],
        owner_account_id=value["ownerAccountId"],
        security_domain_id=value["securityDomainId"],
        source_revision_ids=tuple(value["sourceRevisionIds"]),
        cas_ref=_decode_cas_ref(value["casRef"]),
        source_inventory_trust=(
            SourceInventoryTrust(
                artifact_id=trust["artifactId"],
                record_sha256=trust["recordSha256"],
                provenance_hash=trust["provenanceHash"],
                provenance_ref=_decode_cas_ref(trust["provenanceRef"]),
            )
            if isinstance(trust, Mapping) else None
        ),
    )


def _decode_product_ref(value: Mapping[str, object]) -> PromotionProductRef:
    return PromotionProductRef(
        role=value["role"],
        media_type=value["mediaType"],
        schema_id=value["schemaId"],
        artifact_id=value["artifactId"],
        byte_domain_id=value["byteDomainId"],
        cas_ref=_decode_cas_ref(value["casRef"]),
    )


def _decode_binding(value: Mapping[str, object]) -> PromotionBinding:
    return PromotionBinding(
        owner_account_id=value["ownerAccountId"],
        security_domain_id=value["securityDomainId"],
        course_layout_identity=value["courseLayoutIdentity"],
        layout_revision_id=value["layoutRevisionId"],
        source_revision_ids=tuple(value["sourceRevisionIds"]),
        source_roster_hash=value["sourceRosterHash"],
        hole_global_id=value["holeGlobalId"],
        hole_number=value["holeNumber"],
        raw_refs=tuple(_decode_cas_ref(row) for row in value["rawRefs"]),
        derived_refs=tuple(_decode_cas_ref(row) for row in value["derivedRefs"]),
        asset_refs=tuple(_decode_cas_ref(row) for row in value["assetRefs"]),
        closure_proof_ids=tuple(value["closureProofIds"]),
        fingerprint_ids=tuple(value["fingerprintIds"]),
        fingerprinted_artifact_ids=tuple(value["fingerprintedArtifactIds"]),
        unknown_ids=tuple(value["unknownIds"]),
        consumed_node_ids=tuple(value["consumedNodeIds"]),
        evidence_refs=tuple(value["evidenceRefs"]),
        evidence_cas_refs=tuple(
            _decode_evidence_cas_ref(row) for row in value["evidenceCasRefs"]
        ),
        research_evidence_report_hash=value["researchEvidenceReportHash"],
    )


def _decode_capability_evidence(value: Mapping[str, object]) -> CapabilityEvidence:
    kind = value["evidenceKind"]
    if kind == "playsLike":
        return PlaysLikeEvidence(
            source_revision_id=value["sourceRevisionId"],
            axis_attestation_id=value["axisAttestationId"],
            horizontal_axis=value["horizontalAxis"],
            vertical_axis=value["verticalAxis"],
            horizontal_unit=value["horizontalUnit"],
            vertical_unit=value["verticalUnit"],
            model_version=value["modelVersion"],
            adjustment_per_vertical_meter=value["adjustmentPerVerticalMeter"],
            calibration_anchor_ids=tuple(value["calibrationAnchorIds"]),
            max_anchor_distance_m=value["maxAnchorDistanceM"],
            residual_rmse_m=value["residualRmseM"],
            max_abs_residual_m=value["maxAbsResidualM"],
            outlier_threshold_m=value["outlierThresholdM"],
            outlier_count=value["outlierCount"],
            sample_count=value["sampleCount"],
            sample_course_count=value["sampleCourseCount"],
            sample_region_count=value["sampleRegionCount"],
            calibration_evidence_hash=value["calibrationEvidenceHash"],
            consumer_id=value["consumerId"],
        )
    if kind == "hazardGuidance":
        return HazardGuidanceEvidence(
            source_revision_ids=tuple(value["sourceRevisionIds"]),
            route_geometry_hash=value["routeGeometryHash"],
            stationing_basis=value["stationingBasis"],
            hazard_set_evidence_hash=value["hazardSetEvidenceHash"],
            coverage_evidence_hash=value["coverageEvidenceHash"],
            playable_regions_map_geometry_hash=value["playableRegionsMapGeometryHash"],
            playable_regions_registration_residual_m=(
                value["playableRegionsRegistrationResidualM"]
            ),
            playable_regions_topology_evidence_hash=(
                value["playableRegionsTopologyEvidenceHash"]
            ),
            playable_regions_coverage_evidence_hash=(
                value["playableRegionsCoverageEvidenceHash"]
            ),
            hazards=tuple(HazardEvidenceRow(
                hazard_ref=row["hazardRef"],
                source_revision_id=row["sourceRevisionId"],
                hazard_semantic_kind=row["hazardSemanticKind"],
                route_geometry_hash=row["routeGeometryHash"],
                stationing_basis=row["stationingBasis"],
                landing_window_hash=row["landingWindowHash"],
                base_geometry_hash=row["baseGeometryHash"],
                enter_distance_m=row["enterDistanceM"],
                clear_distance_m=row["clearDistanceM"],
                evidence_hash=row["evidenceHash"],
            ) for row in value["hazards"]),
            consumer_id=value["consumerId"],
        )
    if kind == "greenSurface":
        return GreenSurfaceEvidence(
            green_source_revision_id=value["greenSourceRevisionId"],
            base_source_revision_id=value["baseSourceRevisionId"],
            green_source_sha256=value["greenSourceSha256"],
            selected_component_id=value["selectedComponentId"],
            decoder_id=value["decoderId"],
            decoder_version=value["decoderVersion"],
            calibration_id=value["calibrationId"],
            orientation_transform_id=value["orientationTransformId"],
            base_geometry_hash=value["baseGeometryHash"],
            slope_magnitude_pct=value["slopeMagnitudePct"],
            downhill_direction_deg=value["downhillDirectionDeg"],
            registration_residual_m=value["registrationResidualM"],
            cross_source_residual_m=value["crossSourceResidualM"],
            registration_sample_count=value["registrationSampleCount"],
            registration_report_hash=value["registrationReportHash"],
            cross_source_evidence_hash=value["crossSourceEvidenceHash"],
            consumer_id=value["consumerId"],
        )
    raise ValueError(f"unsupported capability evidence kind {kind}")


def _decode_candidate(value: Mapping[str, object]) -> PromotionCandidate:
    return PromotionCandidate(
        candidate_id=value["candidateId"],
        candidate_state=value["candidateState"],
        target_gate=value["targetGate"],
        capability=value["capability"],
        subject_ref=value["subjectRef"],
        projector_id=value["projectorId"],
        quality_policy_version=value["qualityPolicyVersion"],
        binding=_decode_binding(value["binding"]),
        product_refs=tuple(_decode_product_ref(row) for row in value["productRefs"]),
        capability_evidence=_decode_capability_evidence(value["capabilityEvidence"]),
    )


def _strict_untrusted_candidate(
    payload: bytes | str | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(payload, Mapping):
        value: object = dict(payload)
    else:
        raw_bytes = payload.encode() if isinstance(payload, str) else payload
        def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, child in rows:
                if key in result:
                    raise ValueError(f"duplicate promotion key: {key}")
                result[key] = child
            return result

        def reject_constant(value: str) -> object:
            raise ValueError(f"non-finite promotion number: {value}")

        value = json.loads(raw_bytes, object_pairs_hook=pairs, parse_constant=reject_constant)
        if canonical_json_bytes(value) != raw_bytes:
            raise ValueError("promotion candidate bytes are not canonical JSON")
    if not isinstance(value, dict):
        raise ValueError("promotion candidate must be an object")
    return value


@dataclass(frozen=True)
class ValidatedPromotionCandidate:
    candidate: PromotionCandidate
    ordered_parent_refs: tuple[CASRef, ...]
    trusted_record: "TrustedPromotionCandidateRecord"


@dataclass(frozen=True)
class TrustedPromotionCandidateRecord:
    record_sha256: str
    candidate_id: str
    candidate_sha256: str
    provenance_hash: str
    provenance_ref: CASRef
    artifact: DerivedArtifact

    def payload(self) -> dict[str, object]:
        return {
            "candidateId": self.candidate_id,
            "candidateSha256": self.candidate_sha256,
            "provenanceHash": self.provenance_hash,
            "provenanceRef": _ref_payload(self.provenance_ref),
            "artifact": self.artifact.canonical(),
        }

    def canonical(self) -> dict[str, object]:
        return {"recordSha256": self.record_sha256, **self.payload()}

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        candidate_sha256: str,
        provenance_ref: CASRef,
        artifact: DerivedArtifact,
    ) -> "TrustedPromotionCandidateRecord":
        provisional = cls(
            "", candidate_id, candidate_sha256, provenance_ref.sha256,
            provenance_ref, artifact,
        )
        digest = hashlib.sha256(canonical_json_bytes(provisional.payload())).hexdigest()
        return cls(
            digest, candidate_id, candidate_sha256, provenance_ref.sha256,
            provenance_ref, artifact,
        )


@dataclass(frozen=True)
class TrustedPlayableSourceInventoryRecord:
    record_sha256: str
    inventory_sha256: str
    provenance_hash: str
    provenance_ref: CASRef
    artifact: DerivedArtifact

    def payload(self) -> dict[str, object]:
        return {
            "inventorySha256": self.inventory_sha256,
            "provenanceHash": self.provenance_hash,
            "provenanceRef": _ref_payload(self.provenance_ref),
            "artifact": self.artifact.canonical(),
        }

    def canonical(self) -> dict[str, object]:
        return {"recordSha256": self.record_sha256, **self.payload()}

    @classmethod
    def create(
        cls,
        *,
        provenance_ref: CASRef,
        artifact: DerivedArtifact,
    ) -> "TrustedPlayableSourceInventoryRecord":
        provisional = cls(
            "", artifact.ref.sha256, provenance_ref.sha256,
            provenance_ref, artifact,
        )
        digest = hashlib.sha256(
            canonical_json_bytes(provisional.payload()),
        ).hexdigest()
        return cls(
            digest, artifact.ref.sha256, provenance_ref.sha256,
            provenance_ref, artifact,
        )


@dataclass(frozen=True)
class FrozenPlayableRegionInventoryHandle:
    artifact: DerivedArtifact
    source_inventory_trust: SourceInventoryTrust
    trusted_record_sha256: str
    provenance_ref: CASRef
    source_region_inventory_hash: str
    source_region_refs: tuple[str, ...]


_TRUSTED_STORE_WRITE_TOKEN = object()


class TrustedPromotionCandidateStore:
    def __init__(self, connection: sqlite3.Connection, storage_domain_id: str) -> None:
        self.connection = connection
        self.storage_domain_id = storage_domain_id

    @classmethod
    def open(cls, root: Path, storage_domain_id: str) -> "TrustedPromotionCandidateStore":
        if not storage_domain_id:
            raise ValueError("trusted promotion store requires storage domain")
        root.mkdir(parents=True, exist_ok=True)
        suffix = hashlib.sha256(storage_domain_id.encode()).hexdigest()
        connection = sqlite3.connect(
            root / f"trusted-promotion-{suffix}.sqlite3",
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS trusted_promotion_candidates (
                storage_domain_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                record_json BLOB NOT NULL,
                record_sha256 TEXT NOT NULL,
                PRIMARY KEY (storage_domain_id, candidate_id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS trusted_playable_source_inventories (
                storage_domain_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                inventory_sha256 TEXT NOT NULL,
                record_json BLOB NOT NULL,
                record_sha256 TEXT NOT NULL,
                PRIMARY KEY (storage_domain_id, artifact_id),
                UNIQUE (storage_domain_id, inventory_sha256)
            )
        """)
        return cls(connection, storage_domain_id)

    @staticmethod
    def _strict_object(data: bytes) -> dict[str, object]:
        def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in rows:
                if key in result:
                    raise ValueError(f"duplicate trusted promotion key: {key}")
                result[key] = value
            return result
        def reject_constant(value: str) -> object:
            raise ValueError(f"non-finite trusted promotion number: {value}")
        value = json.loads(
            data, object_pairs_hook=pairs, parse_constant=reject_constant,
        )
        if not isinstance(value, dict):
            raise ValueError("trusted promotion index must be an object")
        return value

    def get(self, candidate_id: str) -> TrustedPromotionCandidateRecord:
        stored = self.connection.execute(
            """
            SELECT record_json, record_sha256
            FROM trusted_promotion_candidates
            WHERE storage_domain_id = ? AND candidate_id = ?
            """,
            (self.storage_domain_id, candidate_id),
        ).fetchone()
        if stored is None:
            raise ValueError("candidate is not in trusted Track C store")
        record_bytes, stored_sha256 = bytes(stored[0]), stored[1]
        if hashlib.sha256(record_bytes).hexdigest() != stored_sha256:
            raise ValueError("trusted candidate SQL row hash mismatch")
        row = self._strict_object(record_bytes)
        if canonical_json_bytes(row) != record_bytes or set(row) != {
            "recordSha256", "candidateId", "candidateSha256", "provenanceHash",
            "provenanceRef", "artifact",
        }:
            raise ValueError("trusted candidate record shape/canonical form invalid")
        artifact = row["artifact"]
        if not isinstance(artifact, dict) or set(artifact) != {
            "artifactId", "ref", "parentRefs", "transformName",
            "transformVersion", "parameters", "buildHash",
        }:
            raise ValueError("trusted candidate artifact shape invalid")
        record = TrustedPromotionCandidateRecord(
            record_sha256=row["recordSha256"],
            candidate_id=row["candidateId"],
            candidate_sha256=row["candidateSha256"],
            provenance_hash=row["provenanceHash"],
            provenance_ref=_decode_cas_ref(row["provenanceRef"]),
            artifact=DerivedArtifact(
                artifact_id=artifact["artifactId"],
                ref=_decode_cas_ref(artifact["ref"]),
                parent_refs=tuple(_decode_cas_ref(ref) for ref in artifact["parentRefs"]),
                transform_name=artifact["transformName"],
                transform_version=artifact["transformVersion"],
                parameters=dict(artifact["parameters"]),
                build_hash=artifact["buildHash"],
            ),
        )
        if record.candidate_id != candidate_id:
            raise ValueError("trusted candidate index key/row mismatch")
        if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in (
            record.record_sha256, record.candidate_sha256, record.provenance_hash,
        )):
            raise ValueError("trusted candidate record hashes are invalid")
        if hashlib.sha256(canonical_json_bytes(record.payload())).hexdigest() != record.record_sha256:
            raise ValueError("trusted candidate record identity mismatch")
        if record.provenance_hash != record.provenance_ref.sha256:
            raise ValueError("trusted candidate provenance hash/ref mismatch")
        if any(
            ref.storage_domain_id != self.storage_domain_id
            for ref in (
                record.provenance_ref, record.artifact.ref, *record.artifact.parent_refs,
            )
        ):
            raise ValueError("trusted candidate record crosses storage domain")
        return record

    def _record_verified(
        self,
        record: TrustedPromotionCandidateRecord,
        *,
        token: object,
    ) -> None:
        if token is not _TRUSTED_STORE_WRITE_TOKEN:
            raise PermissionError("trusted candidate rows are builder-only")
        record_bytes = canonical_json_bytes(record.canonical())
        row_sha256 = hashlib.sha256(record_bytes).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                """
                SELECT record_json, record_sha256
                FROM trusted_promotion_candidates
                WHERE storage_domain_id = ? AND candidate_id = ?
                """,
                (self.storage_domain_id, record.candidate_id),
            ).fetchone()
            if existing is not None and (
                bytes(existing[0]) != record_bytes or existing[1] != row_sha256
            ):
                raise ValueError("trusted promotion candidate identity collision")
            self.connection.execute(
                """
                INSERT OR IGNORE INTO trusted_promotion_candidates (
                    storage_domain_id, candidate_id, record_json, record_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (self.storage_domain_id, record.candidate_id, record_bytes, row_sha256),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def get_source_inventory_by_ref(
        self,
        inventory_ref: CASRef,
    ) -> TrustedPlayableSourceInventoryRecord:
        stored = self.connection.execute(
            """
            SELECT record_json, record_sha256
            FROM trusted_playable_source_inventories
            WHERE storage_domain_id = ? AND inventory_sha256 = ?
            """,
            (self.storage_domain_id, inventory_ref.sha256),
        ).fetchone()
        if stored is None:
            raise ValueError(
                "playable source inventory is not in the trusted freeze store"
            )
        record_bytes, stored_sha256 = bytes(stored[0]), stored[1]
        if hashlib.sha256(record_bytes).hexdigest() != stored_sha256:
            raise ValueError("trusted source inventory SQL row hash mismatch")
        row = self._strict_object(record_bytes)
        if canonical_json_bytes(row) != record_bytes or set(row) != {
            "recordSha256", "inventorySha256", "provenanceHash",
            "provenanceRef", "artifact",
        }:
            raise ValueError("trusted source inventory record shape/canonical form invalid")
        artifact_row = row["artifact"]
        if not isinstance(artifact_row, dict) or set(artifact_row) != {
            "artifactId", "ref", "parentRefs", "transformName",
            "transformVersion", "parameters", "buildHash",
        }:
            raise ValueError("trusted source inventory artifact shape invalid")
        artifact = DerivedArtifact(
            artifact_id=artifact_row["artifactId"],
            ref=_decode_cas_ref(artifact_row["ref"]),
            parent_refs=tuple(
                _decode_cas_ref(ref) for ref in artifact_row["parentRefs"]
            ),
            transform_name=artifact_row["transformName"],
            transform_version=artifact_row["transformVersion"],
            parameters=dict(artifact_row["parameters"]),
            build_hash=artifact_row["buildHash"],
        )
        record = TrustedPlayableSourceInventoryRecord(
            record_sha256=row["recordSha256"],
            inventory_sha256=row["inventorySha256"],
            provenance_hash=row["provenanceHash"],
            provenance_ref=_decode_cas_ref(row["provenanceRef"]),
            artifact=artifact,
        )
        if (
            any(
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in (
                    record.record_sha256, record.inventory_sha256,
                    record.provenance_hash,
                )
            )
            or hashlib.sha256(canonical_json_bytes(record.payload())).hexdigest()
            != record.record_sha256
            or record.inventory_sha256 != inventory_ref.sha256
            or record.artifact.ref != inventory_ref
            or record.provenance_hash != record.provenance_ref.sha256
            or any(
                ref.storage_domain_id != self.storage_domain_id
                for ref in (
                    record.artifact.ref, record.provenance_ref,
                    *record.artifact.parent_refs,
                )
            )
        ):
            raise ValueError("trusted source inventory record binding is invalid")
        _validate_derived_artifact_identity(record.artifact)
        return record

    def _record_verified_source_inventory(
        self,
        record: TrustedPlayableSourceInventoryRecord,
        *,
        token: object,
    ) -> None:
        if token is not _TRUSTED_STORE_WRITE_TOKEN:
            raise PermissionError("trusted source inventory rows are builder-only")
        record_bytes = canonical_json_bytes(record.canonical())
        sql_row_sha256 = hashlib.sha256(record_bytes).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                """
                SELECT record_json, record_sha256
                FROM trusted_playable_source_inventories
                WHERE storage_domain_id = ? AND artifact_id = ?
                """,
                (self.storage_domain_id, record.artifact.artifact_id),
            ).fetchone()
            if existing is not None and (
                bytes(existing[0]) != record_bytes
                or existing[1] != sql_row_sha256
            ):
                raise ValueError("trusted source inventory identity collision")
            self.connection.execute(
                """
                INSERT OR IGNORE INTO trusted_playable_source_inventories (
                    storage_domain_id, artifact_id, inventory_sha256,
                    record_json, record_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.storage_domain_id, record.artifact.artifact_id,
                    record.inventory_sha256, record_bytes, sql_row_sha256,
                ),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.connection.close()
```

The sorting helpers above are deliberately limited to mathematical sets in promotion identity. Do not apply them to `LosslessIR.atoms`, protobuf/JSON occurrences, archive central/local records, DSKIMG block chains, transform steps, or an ordered layout hole roster; those sequences retain source/semantic order and their existing occurrence-index tests remain authoritative.

For `guidance.playable-regions`, the geometry order above is normative: regions sort uniquely by `regionRef`; rings sort uniquely by `(outer first, ringRef)`; and every explicitly closed ring is rotated so its first/last point is the lexicographically minimum `(eastM,northM)` vertex. Outer rings are counter-clockwise and hole rings are clockwise, so admitted region material is always on the left of an oriented boundary segment. Rings are simple/non-degenerate, holes are strictly contained by exactly one outer, and same-region components cannot overlap or touch. Across **different** regions, a point-only contact is legal; a collinear shared boundary is legal only when the two oriented segments put region interiors on opposite sides. A proper crossing, strict containment, or same-direction shared boundary proves interior overlap and fails admission. Therefore identical polygons and differently segmented coincident polygons fail, while point-touching regions and adjacent regions with an oppositely oriented common edge pass. Runtime point classification returns a region only for one strict interior match; a point on any outer/hole/shared/point-contact boundary, outside all regions, or in more than one interior is `unavailable`, never resolved by list order or epsilon nudging.

`regionsHash` is the SHA-256 of the canonical `regions` array after removing only each region's `evidenceRefs`; this avoids a topology/product hash cycle while still binding the exact region, lie, ring, and point geometry. Coverage does not derive both sides from that product array. Before projection, the source decoder freezes `playableRegionsSourceInventory` as its own derived CAS parent, with a canonical source-region roster plus the exact source node IDs, closure-proof IDs, fingerprint IDs, evidence IDs, source revisions, map-geometry hash, and map envelope. Its immutable body hash and roster hash flow into topology and coverage evidence; admission compares the product's observed `regionRef` set with this independent expected roster. Regenerating product/topology/coverage after deleting a known source region still fails unless the previously frozen source inventory also changes, which changes the parent/candidate identity and cannot readmit as the trusted candidate.

The `playableRegionsSourceInventory` `EvidenceCASRef` also carries the strict `sourceInventoryTrust` object `{artifactId, recordSha256, provenanceHash, provenanceRef}` returned by the freeze handle. Those four values are part of the promotion candidate identity. Admission requires them to equal the independently stored SQL authority row, requires the provenance CAS ref as an additional exact promotion parent, rereads both source-inventory and provenance CAS bytes, and recomputes the complete `DerivedArtifact`, parent-ref set, transform name/version, build hash, ByteDomain/node/closure/fingerprint identities, evidence authority, revisions, and source roster. A caller that writes byte-identical inventory JSON directly to CAS but never obtains the builder-only trusted record therefore has no admissible authority.

The resource envelope is also normative and version-frozen for v1: product/evidence body `<= 2,000,000` bytes, `<= 256` regions, `<= 512` rings, `<= 4,096` total stored points, `<= 512` stored points per ring, and `<= 4,000,000` explicit segment-pair checks. Local coordinates and map-envelope bounds must be finite and have absolute value `<= 100,000m`; every point must lie inside the source-inventory-bound `mapGeometryEnvelope`. Every subtraction, product, cross product, signed-area term/accumulator, collinear-overlap calculation, ray crossing, and shared-edge direction dot product is checked for finiteness. Values such as `1e308`, overflow/non-finite intermediates, invalid envelopes, out-of-envelope coordinates, and any byte/count/comparison budget exhaustion fail closed before promotion. These caps are required because the deliberately simple validator has worst-case quadratic intersection work; raising a cap requires a new quality-policy/version and complexity evidence, not a silent constant edit.

The source inventory is not a hand-authored JSON sidecar. Add this freeze operation to `promotion.py` and call it directly from the source decoder output **before** any runtime `regions` array exists:

```python
@dataclass(frozen=True)
class SourceRegionInventoryRow:
    region_ref: str
    source_revision_id: str
    source_object_ref: str
    source_node_ids: tuple[str, ...]
    closure_proof_ids: tuple[str, ...]
    fingerprint_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "regionRef": self.region_ref,
            "sourceRevisionId": self.source_revision_id,
            "sourceObjectRef": self.source_object_ref,
            "sourceNodeIds": list(self.source_node_ids),
            "closureProofIds": list(self.closure_proof_ids),
            "fingerprintIds": list(self.fingerprint_ids),
            "evidenceIds": list(self.evidence_ids),
        }


def freeze_playable_regions_source_inventory(
    *,
    cas: EncryptedCAS,
    trusted_candidate_store: TrustedPromotionCandidateStore,
    storage_domain_id: str,
    owner_account_id: str,
    course_layout_identity: str,
    layout_revision_id: str,
    hole_global_id: str,
    source_revision_ids: tuple[str, ...],
    map_geometry_hash: str,
    map_geometry_envelope: Mapping[str, object],
    rows: tuple[SourceRegionInventoryRow, ...],
    source_domains: Mapping[str, ByteDomain],
    source_nodes: Mapping[str, NodeRecord],
    closure_proofs: Mapping[str, ClosureProof],
    fingerprints: Mapping[str, ArtifactFingerprint],
    authorized_evidence_ids: frozenset[str],
    parent_refs: tuple[CASRef, ...],
    decoder_version: str,
    build_hash: str,
) -> FrozenPlayableRegionInventoryHandle:
    if trusted_candidate_store.storage_domain_id != storage_domain_id:
        raise ValueError("trusted source inventory store/storage domain mismatch")
    canonical_source_ids = _canonical_string_set(
        source_revision_ids, "source inventory sourceRevisionIds",
    )
    _require_hash(map_geometry_hash, "source inventory mapGeometryHash")
    envelope = _validated_map_geometry_envelope(map_geometry_envelope)
    if not owner_account_id or not course_layout_identity or not layout_revision_id:
        raise ValueError("source inventory owner/layout authority is incomplete")
    if not hole_global_id or not rows or len(rows) > _MAX_PLAYABLE_REGIONS:
        raise ValueError("source inventory hole/region roster is incomplete or over budget")
    region_refs = [row.region_ref for row in rows]
    source_object_refs = [row.source_object_ref for row in rows]
    if region_refs != sorted(set(region_refs)):
        raise ValueError("source inventory rows are not canonical by regionRef")
    if any(not value for value in source_object_refs) or (
        len(set(source_object_refs)) != len(source_object_refs)
    ):
        raise ValueError("source inventory sourceObjectRefs must be nonempty and unique")
    parent_identities = {_ref_identity(ref) for ref in parent_refs}
    if not parent_refs or any(
        _ref_identity(domain.cas_ref) not in parent_identities
        for domain in source_domains.values()
    ):
        raise ValueError("source inventory parents do not cover every source ByteDomain")

    for row in rows:
        if row.source_revision_id not in canonical_source_ids:
            raise ValueError("source inventory row leaves source revision authority")
        for label, values in (
            ("sourceNodeIds", row.source_node_ids),
            ("closureProofIds", row.closure_proof_ids),
            ("fingerprintIds", row.fingerprint_ids),
            ("evidenceIds", row.evidence_ids),
        ):
            if not values or tuple(sorted(set(values))) != values:
                raise ValueError(f"source inventory {label} is not a canonical nonempty set")
        if not set(row.evidence_ids).issubset(authorized_evidence_ids):
            raise ValueError("source inventory row cites unauthorized evidence")
        row_nodes = tuple(source_nodes.get(node_id) for node_id in row.source_node_ids)
        row_proofs = tuple(closure_proofs.get(proof_id) for proof_id in row.closure_proof_ids)
        row_fingerprints = tuple(
            fingerprints.get(fingerprint_id) for fingerprint_id in row.fingerprint_ids
        )
        if any(item is None for item in (*row_nodes, *row_proofs, *row_fingerprints)):
            raise ValueError("source inventory cites an unknown node/proof/fingerprint ID")
        proof_domains = {
            proof.byte_domain_id for proof in row_proofs
            if proof is not None and proof.complete
        }
        if len(proof_domains) != len(row_proofs):
            raise ValueError("source inventory closure proofs are incomplete or ambiguous")
        if any(
            node is None
            or node.byte_domain_id not in proof_domains
            or node.byte_domain_id not in source_domains
            or node.offset < 0
            or node.length <= 0
            or node.offset + node.length > source_domains[node.byte_domain_id].size
            for node in row_nodes
        ):
            raise ValueError("source inventory node leaves its proved source ByteDomain")
        if any(
            fingerprint is None
            or fingerprint.byte_domain_id not in proof_domains
            or fingerprint.byte_domain_id not in source_domains
            or fingerprint.content_fingerprint
            != source_domains[fingerprint.byte_domain_id].cas_ref.sha256
            for fingerprint in row_fingerprints
        ):
            raise ValueError("source inventory fingerprint leaves proved source bytes")

    source_regions = [row.canonical() for row in rows]
    source_region_inventory_hash = hashlib.sha256(
        canonical_json_bytes(source_regions),
    ).hexdigest()
    body = canonical_json_bytes({
        "schema": "ai-caddie-playable-regions-source-inventory-v1",
        "inventoryBuildStage": "source_decode_before_product_projection",
        "courseLayoutIdentity": course_layout_identity,
        "layoutRevisionId": layout_revision_id,
        "holeGlobalId": hole_global_id,
        "sourceRevisionIds": canonical_source_ids,
        "mapGeometryHash": map_geometry_hash,
        "mapGeometryEnvelope": {
            "minEastM": envelope[0], "minNorthM": envelope[1],
            "maxEastM": envelope[2], "maxNorthM": envelope[3],
        },
        "sourceRegionInventoryHash": source_region_inventory_hash,
        "sourceRegions": source_regions,
        "complete": True,
    })
    if len(body) > _MAX_PLAYABLE_REGIONS_BODY_BYTES:
        raise ValueError("source inventory body byte budget exceeded")
    artifact = put_derived(
        cas=cas,
        storage_domain_id=storage_domain_id,
        byte_domain="deep-mine-playable-regions-source-inventory-evidence",
        data=body,
        parent_refs=tuple(sorted(parent_refs, key=_ref_identity)),
        transform_name="freeze-playable-regions-source-inventory",
        transform_version="1",
        parameters={
            "ownerAccountId": owner_account_id,
            "sourceRegionInventoryHash": source_region_inventory_hash,
            "decoderVersion": decoder_version,
        },
        build_hash=build_hash,
    )
    provenance_bytes = canonical_json_bytes({
        "schema": "ai-caddie-trusted-playable-source-inventory-provenance-v1",
        "ownerAccountId": owner_account_id,
        "courseLayoutIdentity": course_layout_identity,
        "layoutRevisionId": layout_revision_id,
        "holeGlobalId": hole_global_id,
        "sourceRevisionIds": canonical_source_ids,
        "authorizedEvidenceIds": sorted(authorized_evidence_ids),
        "sourceRegionInventoryHash": source_region_inventory_hash,
        "sourceRegions": source_regions,
        "sourceDomains": [
            source_domains[key].canonical() for key in sorted(source_domains)
        ],
        "sourceNodes": [
            source_nodes[key].canonical() for key in sorted(source_nodes)
        ],
        "closureProofs": [
            closure_proofs[key].canonical() for key in sorted(closure_proofs)
        ],
        "fingerprints": [
            fingerprints[key].canonical() for key in sorted(fingerprints)
        ],
        "artifact": artifact.canonical(),
    })
    provenance_ref = cas.put_bytes(
        storage_domain_id,
        "deep-mine-playable-regions-source-inventory-provenance",
        provenance_bytes,
    )
    record = TrustedPlayableSourceInventoryRecord.create(
        provenance_ref=provenance_ref,
        artifact=artifact,
    )
    trusted_candidate_store._record_verified_source_inventory(
        record, token=_TRUSTED_STORE_WRITE_TOKEN,
    )
    return FrozenPlayableRegionInventoryHandle(
        artifact=artifact,
        source_inventory_trust=SourceInventoryTrust(
            artifact_id=artifact.artifact_id,
            record_sha256=record.record_sha256,
            provenance_hash=provenance_ref.sha256,
            provenance_ref=provenance_ref,
        ),
        trusted_record_sha256=record.record_sha256,
        provenance_ref=provenance_ref,
        source_region_inventory_hash=source_region_inventory_hash,
        source_region_refs=tuple(region_refs),
    )
```

The composition root records the returned `DerivedArtifact` in the research provenance DAG and passes only its exact CAS identity plus decoded expected roster to the projector. The projector has no API that accepts `product.regions` as source-inventory input. Promotion then binds that exact inventory CAS body as a mandatory evidence parent; the freeze operation is the only writer for its byte domain and has already resolved every named node/proof/fingerprint/evidence ID against trusted repositories. Replay verifies the `DerivedArtifact` DAG again, while untrusted admission verifies the immutable body hash, source roster, and all downstream topology/coverage links rather than treating regex-shaped IDs in a later product document as new authority.

Create the composition root as a separate module; this is the only production call path from decoded RGN objects into a playable-regions projector:

```python
# ai_caddie/research/deep_mine/playable_regions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from .fingerprint import ArtifactFingerprint
from .ledger import ClosureProof
from .models import ByteDomain, NodeRecord
from .promotion import (
    FrozenPlayableRegionInventoryHandle,
    SourceRegionInventoryRow,
    TrustedPromotionCandidateStore,
    freeze_playable_regions_source_inventory,
)


@dataclass(frozen=True)
class DecodedPlayableRegion:
    inventory_row: SourceRegionInventoryRow
    decoded_geometry: Mapping[str, object]


@dataclass(frozen=True)
class DecodedPlayableRegionSource:
    owner_account_id: str
    course_layout_identity: str
    layout_revision_id: str
    hole_global_id: str
    source_revision_ids: tuple[str, ...]
    map_geometry_hash: str
    map_geometry_envelope: Mapping[str, object]
    regions: tuple[DecodedPlayableRegion, ...]
    source_domains: Mapping[str, ByteDomain]
    source_nodes: Mapping[str, NodeRecord]
    closure_proofs: Mapping[str, ClosureProof]
    fingerprints: Mapping[str, ArtifactFingerprint]
    authorized_evidence_ids: frozenset[str]
    parent_refs: tuple[CASRef, ...]
    decoder_version: str
    build_hash: str


@dataclass(frozen=True)
class ProjectedPlayableRegionSet:
    product_body: bytes
    topology_evidence_body: bytes
    coverage_evidence_body: bytes


class PlayableRegionsProjector(Protocol):
    def project(
        self,
        *,
        frozen_inventory: FrozenPlayableRegionInventoryHandle,
        decoded_regions: tuple[DecodedPlayableRegion, ...],
    ) -> ProjectedPlayableRegionSet: ...


def project_playable_regions_from_decoded_source(
    source: DecodedPlayableRegionSource,
    *,
    cas: EncryptedCAS,
    trusted_candidate_store: TrustedPromotionCandidateStore,
    storage_domain_id: str,
    projector: PlayableRegionsProjector,
) -> tuple[FrozenPlayableRegionInventoryHandle, ProjectedPlayableRegionSet]:
    rows = tuple(region.inventory_row for region in source.regions)
    if [row.region_ref for row in rows] != sorted({row.region_ref for row in rows}):
        raise ValueError("decoded playable source is not canonical by regionRef")
    frozen_inventory = freeze_playable_regions_source_inventory(
        cas=cas,
        trusted_candidate_store=trusted_candidate_store,
        storage_domain_id=storage_domain_id,
        owner_account_id=source.owner_account_id,
        course_layout_identity=source.course_layout_identity,
        layout_revision_id=source.layout_revision_id,
        hole_global_id=source.hole_global_id,
        source_revision_ids=source.source_revision_ids,
        map_geometry_hash=source.map_geometry_hash,
        map_geometry_envelope=source.map_geometry_envelope,
        rows=rows,
        source_domains=source.source_domains,
        source_nodes=source.source_nodes,
        closure_proofs=source.closure_proofs,
        fingerprints=source.fingerprints,
        authorized_evidence_ids=source.authorized_evidence_ids,
        parent_refs=source.parent_refs,
        decoder_version=source.decoder_version,
        build_hash=source.build_hash,
    )
    projected = projector.project(
        frozen_inventory=frozen_inventory,
        decoded_regions=source.regions,
    )
    return frozen_inventory, projected
```

Add an event-order test with a recording projector. It must assert `freeze`/trusted-row visibility before `project`, and it must statically inspect the projector signature so neither `product`, `product_regions`, nor `expected_region_refs` can be supplied by a runtime product:

```python
def decoded_playable_source_fixture(
    cas: EncryptedCAS,
) -> tuple[DecodedPlayableRegionSource, tuple[str, ...]]:
    source_ref = cas.put_bytes(
        SECURITY_DOMAIN_ID, "derived-base-geometry", b"base-geometry",
    )
    domain = ByteDomain.create(
        source_ref, parent_domain_id=None, transform_id=None,
    )
    root = NodeRecord.root(domain.domain_id, domain.size, "source-region-root")
    node = NodeRecord.create(
        byte_domain_id=domain.domain_id,
        parent_node_id=root.node_id,
        offset=0,
        length=domain.size,
        status=NodeStatus.DECODED,
        node_kind="source-region-object",
        decoder_id="gmp-rgn-source-regions",
        decoder_version="1",
        occurrence_index=0,
        accounting=True,
        semantic_hypothesis="source region roster",
        confidence="confirmed",
        consumed_by=("playable-source-inventory",),
    )
    proof_payload = {
        "byteDomainId": domain.domain_id,
        "rootNodeId": root.node_id,
        "domainSize": str(domain.size),
        "classifiedBytes": str(domain.size),
        "statusBytes": {"decoded": domain.size},
        "complete": True,
    }
    proof = ClosureProof(
        typed_id("DeepMineClosureProof/v1", proof_payload),
        domain.domain_id,
        root.node_id,
        domain.size,
        domain.size,
        {"decoded": domain.size},
        True,
    )
    fingerprint = build_fingerprint(
        artifact_id="artifact-source-base-geometry",
        schema_family="gmp-rgn-source-regions",
        domain=domain,
        data=b"base-geometry",
        structural_tokens=("rgn", "source-region"),
        numeric_series={"regionCount": (1.0,)},
    )
    inventory_row = SourceRegionInventoryRow(
        region_ref="region:fairway-1",
        source_revision_id="source-revision-base",
        source_object_ref="rgn-object:31936-7:fairway-1",
        source_node_ids=(node.node_id,),
        closure_proof_ids=(proof.proof_id,),
        fingerprint_ids=(fingerprint.fingerprint_id,),
        evidence_ids=("field-check-1",),
    )
    source = DecodedPlayableRegionSource(
        owner_account_id=OWNER_ACCOUNT_ID,
        course_layout_identity="layout-identity-1",
        layout_revision_id="layout-revision-1",
        hole_global_id="31936-7",
        source_revision_ids=("source-revision-base",),
        map_geometry_hash=source_ref.sha256,
        map_geometry_envelope=PLAYABLE_MAP_GEOMETRY_ENVELOPE,
        regions=(DecodedPlayableRegion(
            inventory_row=inventory_row,
            decoded_geometry={"sourceObjectRef": inventory_row.source_object_ref},
        ),),
        source_domains={domain.domain_id: domain},
        source_nodes={node.node_id: node},
        closure_proofs={proof.proof_id: proof},
        fingerprints={fingerprint.fingerprint_id: fingerprint},
        authorized_evidence_ids=frozenset({"field-check-1"}),
        parent_refs=(source_ref,),
        decoder_version="source-inventory-1",
        build_hash="source-inventory-build-1",
    )
    return source, (inventory_row.region_ref,)


class DeepMinePromotionCompositionTests(unittest.TestCase):
    def test_composition_root_freezes_before_projector_and_has_no_product_roster_input(self) -> None:
        import inspect

        signature = inspect.signature(PlayableRegionsProjector.project)
        self.assertEqual(
            tuple(signature.parameters),
            ("self", "frozen_inventory", "decoded_regions"),
        )
        events: list[str] = []

        class RecordingProjector:
            def project(self, *, frozen_inventory, decoded_regions):
                self.assert_trusted(frozen_inventory)
                events.append("project")
                return ProjectedPlayableRegionSet(b"{}", b"{}", b"{}")

            def assert_trusted(self, frozen_inventory):
                record = store.get_source_inventory_by_ref(
                    frozen_inventory.artifact.ref,
                )
                self_test.assertEqual(
                    record.record_sha256,
                    frozen_inventory.trusted_record_sha256,
                )
                events.append("trusted-freeze-visible")

        with tempfile.TemporaryDirectory() as tmp:
            self_test = self
            root = Path(tmp)
            cas = EncryptedCAS(
                root / "cas",
                StaticDomainKeyProvider({SECURITY_DOMAIN_ID: b"a" * 32}),
            )
            store = TrustedPromotionCandidateStore.open(
                root / "trusted", SECURITY_DOMAIN_ID,
            )
            self.addCleanup(store.close)
            source, expected_handle = decoded_playable_source_fixture(cas)
            handle, _projected = project_playable_regions_from_decoded_source(
                source,
                cas=cas,
                trusted_candidate_store=store,
                storage_domain_id=SECURITY_DOMAIN_ID,
                projector=RecordingProjector(),
            )
            self.assertEqual(handle.source_region_refs, expected_handle)
            self.assertEqual(events, ["trusted-freeze-visible", "project"])
```

The test must not construct a runtime product body or expected roster before calling the composition root. C16's runner calls this composition root for every decoded playable source and passes the returned handle into promotion binding construction; it must not call a projector directly.

- [ ] **Step 4: Validate closure/fingerprint/unknown/consumer bindings and fail closed**

Append to `ai_caddie/research/deep_mine/promotion.py`:

```python
def _require_hash(value: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be lowercase sha256")


def _evidence_rows_by_kind(binding: PromotionBinding) -> dict[str, EvidenceCASRef]:
    rows: dict[str, EvidenceCASRef] = {}
    for row in binding.evidence_cas_refs:
        if row.evidence_kind in rows:
            raise ValueError(f"evidenceCasRefs contains duplicate evidence kind {row.evidence_kind}")
        try:
            expected_byte_domain = _EVIDENCE_BYTE_DOMAINS[row.evidence_kind]
        except KeyError as exc:
            raise ValueError(f"unsupported evidence kind {row.evidence_kind}") from exc
        if row.owner_account_id != binding.owner_account_id:
            raise ValueError(f"{row.evidence_kind} owner account does not match promotion binding")
        if row.security_domain_id != binding.security_domain_id:
            raise ValueError(f"{row.evidence_kind} security domain does not match promotion binding")
        if row.cas_ref.storage_domain_id != row.security_domain_id:
            raise ValueError(f"{row.evidence_kind} CAS storage/security domain mismatch")
        if row.cas_ref.byte_domain != expected_byte_domain:
            raise ValueError(f"{row.evidence_kind} CAS byte domain is invalid")
        if row.cas_ref.size <= 0:
            raise ValueError(f"{row.evidence_kind} CAS evidence requires positive size")
        _require_hash(row.cas_ref.sha256, f"{row.evidence_kind} CAS hash")
        if not row.source_revision_ids or not set(row.source_revision_ids).issubset(binding.source_revision_ids):
            raise ValueError(f"{row.evidence_kind} source revisions are outside promotion binding")
        trust = row.source_inventory_trust
        if row.evidence_kind == "playableRegionsSourceInventory":
            if trust is None:
                raise ValueError("playable source inventory trust binding is missing")
            for label, value in (
                ("artifactId", trust.artifact_id),
                ("recordSha256", trust.record_sha256),
                ("provenanceHash", trust.provenance_hash),
            ):
                _require_hash(value, f"playable source inventory {label}")
            if (
                trust.provenance_ref.storage_domain_id != row.security_domain_id
                or trust.provenance_ref.byte_domain
                != "deep-mine-playable-regions-source-inventory-provenance"
                or trust.provenance_ref.sha256 != trust.provenance_hash
                or trust.provenance_ref.size <= 0
            ):
                raise ValueError("playable source inventory provenance trust is invalid")
        elif trust is not None:
            raise ValueError(
                f"{row.evidence_kind} must not carry sourceInventoryTrust"
            )
        rows[row.evidence_kind] = row
    return rows


def _require_evidence_cas_refs(
    binding: PromotionBinding,
    expected: Mapping[str, tuple[str, tuple[str, ...]]],
) -> None:
    rows = _evidence_rows_by_kind(binding)
    if set(rows) != set(expected):
        raise ValueError(
            f"evidenceCasRefs kinds mismatch: expected {sorted(expected)}, got {sorted(rows)}"
        )
    for kind, (expected_hash, expected_source_revisions) in expected.items():
        row = rows[kind]
        if row.cas_ref.sha256 != expected_hash:
            raise ValueError(f"{kind} CAS sha256 does not bind the named evidence hash")
        if set(row.source_revision_ids) != set(expected_source_revisions):
            raise ValueError(f"{kind} source revision binding mismatch")


def _category_refs(binding: PromotionBinding) -> tuple[CASRef, ...]:
    return (*binding.raw_refs, *binding.derived_refs, *binding.asset_refs)


def _require_unique_bound_ref_for_hash(
    refs: tuple[CASRef, ...],
    sha256: str,
    label: str,
) -> CASRef:
    matches = tuple(ref for ref in refs if ref.sha256 == sha256)
    if len(matches) != 1:
        raise ValueError(f"{label} must resolve to exactly one bound CAS identity")
    return matches[0]


def _validate_binding_shape(binding: PromotionBinding) -> None:
    binding.canonical()  # rejects duplicates in every canonical set-like field before set comparisons
    required_strings = (
        binding.owner_account_id,
        binding.security_domain_id,
        binding.course_layout_identity,
        binding.layout_revision_id,
        binding.source_roster_hash,
        binding.hole_global_id,
        binding.research_evidence_report_hash,
    )
    if (
        not all(required_strings)
        or not binding.source_revision_ids
        or not binding.evidence_refs
        or not binding.evidence_cas_refs
    ):
        raise ValueError("promotion binding chain is incomplete")
    if binding.hole_number < 1 or binding.hole_number > 18:
        raise ValueError("promotion hole number must be in 1..18")
    if (
        not binding.raw_refs
        or not binding.closure_proof_ids
        or not binding.fingerprint_ids
        or not binding.fingerprinted_artifact_ids
        or not binding.consumed_node_ids
    ):
        raise ValueError("promotion binding lacks raw, closure, fingerprint, or consumer evidence")
    _require_hash(binding.source_roster_hash, "source roster hash")
    _require_hash(binding.research_evidence_report_hash, "research evidence report hash")
    category_refs = _category_refs(binding)
    category_identities = tuple(_ref_identity(ref) for ref in category_refs)
    if len(set(category_identities)) != len(category_identities):
        raise ValueError("raw/derived/asset categories contain duplicate CAS identities")
    for label, refs in (
        ("rawRefs", binding.raw_refs),
        ("derivedRefs", binding.derived_refs),
        ("assetRefs", binding.asset_refs),
    ):
        for ref in refs:
            if ref.storage_domain_id != binding.security_domain_id:
                raise ValueError(f"{label} crosses promotion security/storage domain")
            if not ref.byte_domain or ref.size <= 0:
                raise ValueError(f"{label} contains invalid byte domain or size")
            _require_hash(ref.sha256, f"{label} CAS hash")
    rows = _evidence_rows_by_kind(binding)
    all_role_identities = [
        *(_ref_identity(ref) for ref in category_refs),
        *(_ref_identity(row.cas_ref) for row in rows.values()),
        *(
            _ref_identity(row.source_inventory_trust.provenance_ref)
            for row in rows.values()
            if row.source_inventory_trust is not None
        ),
    ]
    if len(set(all_role_identities)) != len(all_role_identities):
        raise ValueError("promotion CAS identity is ambiguously assigned to multiple roles")
    research = rows.get("researchEvidenceReport")
    if research is None or research.cas_ref.sha256 != binding.research_evidence_report_hash:
        raise ValueError("researchEvidenceReport CAS sha256 does not bind the named evidence hash")
    if set(research.source_revision_ids) != set(binding.source_revision_ids):
        raise ValueError("researchEvidenceReport source revision binding mismatch")


def _require_nonnegative_number(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _validate_plays_like(
    evidence: PlaysLikeEvidence,
    binding: PromotionBinding,
    projector_id: str,
) -> None:
    if evidence.source_revision_id not in binding.source_revision_ids:
        raise ValueError("playsLike source revision is outside promotion binding")
    if not all((evidence.axis_attestation_id, evidence.horizontal_axis, evidence.vertical_axis)):
        raise ValueError("playsLike axis attestation is incomplete")
    if evidence.horizontal_unit != "meter" or evidence.vertical_unit != "meter":
        raise ValueError("playsLike canonical units must be meter")
    if (
        not evidence.model_version
        or not math.isfinite(evidence.adjustment_per_vertical_meter)
        or not -5.0 <= evidence.adjustment_per_vertical_meter <= 5.0
    ):
        raise ValueError("playsLike runtime model binding is invalid")
    _canonical_string_set(evidence.calibration_anchor_ids, "calibrationAnchorIds")
    if len(set(evidence.calibration_anchor_ids)) < 3:
        raise ValueError("playsLike requires at least three distinct calibration anchors")
    for label, value in (
        ("max anchor distance", evidence.max_anchor_distance_m),
        ("residual RMSE", evidence.residual_rmse_m),
        ("max absolute residual", evidence.max_abs_residual_m),
        ("outlier threshold", evidence.outlier_threshold_m),
    ):
        _require_nonnegative_number(value, label)
    if evidence.sample_count < 1 or evidence.sample_course_count < 1 or evidence.sample_region_count < 1:
        raise ValueError("playsLike sample coverage must include samples, courses, and regions")
    if evidence.outlier_count < 0 or evidence.outlier_count > evidence.sample_count:
        raise ValueError("playsLike outlier count leaves sample coverage")
    _require_hash(evidence.calibration_evidence_hash, "playsLike calibration evidence hash")
    _require_evidence_cas_refs(binding, {
        "researchEvidenceReport": (
            binding.research_evidence_report_hash, binding.source_revision_ids,
        ),
        "playsLikeCalibration": (
            evidence.calibration_evidence_hash, (evidence.source_revision_id,),
        ),
    })
    if evidence.consumer_id != projector_id:
        raise ValueError("playsLike consumer does not match projector")


def _validate_hazard(
    evidence: HazardGuidanceEvidence,
    binding: PromotionBinding,
    projector_id: str,
    product_role: str,
) -> None:
    source_revision_ids = _canonical_string_set(
        evidence.source_revision_ids, "hazard sourceRevisionIds",
    )
    if not set(source_revision_ids).issubset(binding.source_revision_ids):
        raise ValueError("hazardGuidance source revisions are outside promotion binding")
    _require_hash(evidence.hazard_set_evidence_hash, "hazard set evidence hash")
    _require_hash(evidence.coverage_evidence_hash, "hazard coverage evidence hash")
    _require_hash(evidence.route_geometry_hash, "hazard route geometry hash")
    if evidence.stationing_basis != "tee-origin-route-station-v1":
        raise ValueError("hazardGuidance stationing basis is not canonical")
    _require_unique_bound_ref_for_hash(
        binding.derived_refs, evidence.route_geometry_hash,
        "hazardGuidance routeGeometryHash",
    )
    allowed_kinds = {
        "bunker", "water", "penalty_area", "vegetation", "out_of_bounds", "forced_carry", "layup",
    }
    hazard_refs = [row.hazard_ref for row in evidence.hazards]
    if hazard_refs != sorted(set(hazard_refs)):
        raise ValueError("hazardGuidance hazards must be unique and canonical by hazardRef")
    expected_set_hash = hashlib.sha256(canonical_json_bytes({
        "schema": "ai-caddie-hazard-set-evidence-v1",
        "courseLayoutIdentity": binding.course_layout_identity,
        "layoutRevisionId": binding.layout_revision_id,
        "holeGlobalId": binding.hole_global_id,
        "sourceRevisionIds": source_revision_ids,
        "routeGeometryHash": evidence.route_geometry_hash,
        "stationingBasis": evidence.stationing_basis,
        "hazards": [row.canonical() for row in evidence.hazards],
    })).hexdigest()
    expected_coverage_hash = hashlib.sha256(canonical_json_bytes({
        "schema": "ai-caddie-hazard-coverage-evidence-v1",
        "courseLayoutIdentity": binding.course_layout_identity,
        "layoutRevisionId": binding.layout_revision_id,
        "holeGlobalId": binding.hole_global_id,
        "sourceRevisionIds": source_revision_ids,
        "routeGeometryHash": evidence.route_geometry_hash,
        "stationingBasis": evidence.stationing_basis,
        "hazardSetEvidenceHash": evidence.hazard_set_evidence_hash,
        "complete": True,
    })).hexdigest()
    if (
        evidence.hazard_set_evidence_hash != expected_set_hash
        or evidence.coverage_evidence_hash != expected_coverage_hash
    ):
        raise ValueError("hazardGuidance set/coverage evidence hash is not exact")
    row_source_ids: set[str] = set()
    for row in evidence.hazards:
        if not row.hazard_ref:
            raise ValueError("hazardGuidance hazardRef is required")
        if row.source_revision_id not in evidence.source_revision_ids:
            raise ValueError("hazardGuidance row source revision is outside evidence set")
        row_source_ids.add(row.source_revision_id)
        if row.hazard_semantic_kind not in allowed_kinds:
            raise ValueError("hazardGuidance semantic kind is not canonical")
        if (
            row.route_geometry_hash != evidence.route_geometry_hash
            or row.stationing_basis != evidence.stationing_basis
        ):
            raise ValueError("hazardGuidance row stationing does not match set authority")
        for label, value in (
            ("route geometry hash", row.route_geometry_hash),
            ("landing window hash", row.landing_window_hash),
            ("base geometry hash", row.base_geometry_hash),
            ("row evidence hash", row.evidence_hash),
        ):
            _require_hash(value, label)
        expected_member_id = typed_id("DeepMineHazardEvidenceMember/v1", {
            "hazardRef": row.hazard_ref,
            "sourceRevisionId": row.source_revision_id,
            "hazardSemanticKind": row.hazard_semantic_kind,
            "routeGeometryHash": row.route_geometry_hash,
            "landingWindowHash": row.landing_window_hash,
            "baseGeometryHash": row.base_geometry_hash,
            "stationingBasis": row.stationing_basis,
            "enterDistanceM": row.enter_distance_m,
            "clearDistanceM": row.clear_distance_m,
        })
        if row.evidence_hash != expected_member_id:
            raise ValueError("hazardGuidance row evidenceHash is not its set-member identity")
        for label, value in (
            ("routeGeometryHash", row.route_geometry_hash),
            ("landingWindowHash", row.landing_window_hash),
            ("baseGeometryHash", row.base_geometry_hash),
        ):
            _require_unique_bound_ref_for_hash(
                binding.derived_refs, value, f"hazardGuidance {label}",
            )
        _require_nonnegative_number(row.enter_distance_m, "hazardGuidance enter station")
        if row.clear_distance_m is not None:
            _require_nonnegative_number(row.clear_distance_m, "hazardGuidance clear distance")
            if row.clear_distance_m < row.enter_distance_m:
                raise ValueError("hazardGuidance clear station precedes enter station")
    if row_source_ids and row_source_ids != set(evidence.source_revision_ids):
        raise ValueError("hazardGuidance source revision set is not exact")
    expected_evidence = {
        "researchEvidenceReport": (
            binding.research_evidence_report_hash, binding.source_revision_ids,
        ),
        "hazardGuidanceSet": (
            evidence.hazard_set_evidence_hash, evidence.source_revision_ids,
        ),
        "hazardCoverage": (
            evidence.coverage_evidence_hash, evidence.source_revision_ids,
        ),
    }
    playable_values = (
        evidence.playable_regions_map_geometry_hash,
        evidence.playable_regions_registration_residual_m,
        evidence.playable_regions_topology_evidence_hash,
        evidence.playable_regions_coverage_evidence_hash,
    )
    if product_role == "hazardGuidanceBody":
        if any(value is not None for value in playable_values):
            raise ValueError(
                "hazardGuidanceBody must not carry playable-regions evidence"
            )
    elif product_role == "guidance.playable-regions":
        if any(value is None for value in playable_values):
            raise ValueError("playable-regions evidence is incomplete")
        _require_hash(
            evidence.playable_regions_map_geometry_hash,
            "playable-regions map geometry hash",
        )
        _require_hash(
            evidence.playable_regions_topology_evidence_hash,
            "playable-regions topology evidence hash",
        )
        _require_hash(
            evidence.playable_regions_coverage_evidence_hash,
            "playable-regions coverage evidence hash",
        )
        _require_nonnegative_number(
            evidence.playable_regions_registration_residual_m,
            "playable-regions registration residual",
        )
        if evidence.playable_regions_map_geometry_hash != evidence.route_geometry_hash:
            raise ValueError(
                "playable-regions map geometry differs from hazard route authority"
            )
        _require_unique_bound_ref_for_hash(
            binding.derived_refs,
            evidence.playable_regions_map_geometry_hash,
            "playable-regions mapGeometryHash",
        )
        source_inventory_row = _evidence_rows_by_kind(binding).get(
            "playableRegionsSourceInventory"
        )
        if source_inventory_row is None:
            raise ValueError("playable-regions source inventory evidence is missing")
        expected_evidence.update({
            "playableRegionsSourceInventory": (
                source_inventory_row.cas_ref.sha256,
                evidence.source_revision_ids,
            ),
            "playableRegionsTopology": (
                evidence.playable_regions_topology_evidence_hash,
                evidence.source_revision_ids,
            ),
            "playableRegionsCoverage": (
                evidence.playable_regions_coverage_evidence_hash,
                evidence.source_revision_ids,
            ),
        })
    else:
        raise ValueError("unsupported hazardGuidance product role")
    _require_evidence_cas_refs(binding, expected_evidence)
    if evidence.consumer_id != projector_id:
        raise ValueError("hazardGuidance consumer does not match projector")


def _validate_green(
    green: GreenSurfaceEvidence | None,
    binding: PromotionBinding,
    projector_id: str,
) -> None:
    if green is None:
        raise ValueError("greenSurface evidence is required")
    if not all((
        green.green_source_revision_id,
        green.base_source_revision_id,
        green.selected_component_id,
        green.decoder_id,
        green.decoder_version,
        green.calibration_id,
        green.orientation_transform_id,
        green.consumer_id,
    )):
        raise ValueError("greenSurface evidence is incomplete")
    for label, value in (
        ("green source hash", green.green_source_sha256),
        ("base geometry hash", green.base_geometry_hash),
        ("registration report hash", green.registration_report_hash),
        ("cross-source evidence hash", green.cross_source_evidence_hash),
    ):
        _require_hash(value, label)
    if (
        not math.isfinite(green.slope_magnitude_pct)
        or not 0.0 <= green.slope_magnitude_pct <= 100.0
        or not math.isfinite(green.downhill_direction_deg)
        or not 0.0 <= green.downhill_direction_deg < 360.0
        or not math.isfinite(green.registration_residual_m)
        or green.registration_residual_m < 0.0
        or not math.isfinite(green.cross_source_residual_m)
        or green.cross_source_residual_m < 0.0
        or not isinstance(green.registration_sample_count, int)
        or isinstance(green.registration_sample_count, bool)
        or not 3 <= green.registration_sample_count <= 9_007_199_254_740_991
    ):
        raise ValueError("greenSurface geometry/registration measurements are invalid")
    if green.green_source_sha256 == green.base_geometry_hash:
        raise ValueError("greenSurface requires independent green and base geometry sources")
    if green.green_source_revision_id == green.base_source_revision_id:
        raise ValueError("greenSurface requires independent source revisions for green and base")
    if not {
        green.green_source_revision_id, green.base_source_revision_id,
    }.issubset(binding.source_revision_ids):
        raise ValueError("greenSurface source revisions are outside promotion binding")
    _require_unique_bound_ref_for_hash(
        binding.raw_refs, green.green_source_sha256, "greenSurface greenSourceSha256",
    )
    _require_unique_bound_ref_for_hash(
        (*binding.derived_refs, *binding.asset_refs),
        green.base_geometry_hash,
        "greenSurface baseGeometryHash",
    )
    green_and_base_revisions = (
        green.green_source_revision_id, green.base_source_revision_id,
    )
    _require_evidence_cas_refs(binding, {
        "researchEvidenceReport": (
            binding.research_evidence_report_hash, binding.source_revision_ids,
        ),
        "greenRegistration": (
            green.registration_report_hash, green_and_base_revisions,
        ),
        "greenCrossSource": (
            green.cross_source_evidence_hash, green_and_base_revisions,
        ),
    })
    if green.consumer_id != projector_id:
        raise ValueError("greenSurface consumer does not match projector")


def _validate_capability_evidence(
    capability: str,
    evidence: CapabilityEvidence,
    binding: PromotionBinding,
    projector_id: str,
    product_role: str,
) -> None:
    if capability == "playsLike" and isinstance(evidence, PlaysLikeEvidence):
        _validate_plays_like(evidence, binding, projector_id)
    elif capability == "hazardGuidance" and isinstance(evidence, HazardGuidanceEvidence):
        _validate_hazard(evidence, binding, projector_id, product_role)
    elif capability == "greenSurface" and isinstance(evidence, GreenSurfaceEvidence):
        _validate_green(evidence, binding, projector_id)
    else:
        raise ValueError("capability-specific evidence does not match capability")


def _validate_research_provenance(
    *,
    binding: PromotionBinding,
    projector_id: str,
    product_refs: Iterable[PromotionProductRef],
    closure_proofs: Iterable[ClosureProof],
    fingerprints: Iterable[ArtifactFingerprint],
    unknowns: UnknownRegistry | Iterable[UnknownRecord],
    nodes: Mapping[str, NodeRecord],
) -> None:
    product_rows = tuple(product_refs)
    domains = {
        product.byte_domain_id: ByteDomain.create(
            product.cas_ref, parent_domain_id=None, transform_id=None,
        )
        for product in product_rows
    }
    if len(domains) != len(product_rows) or any(
        domain.domain_id != domain_id for domain_id, domain in domains.items()
    ):
        raise ValueError("runtime product ByteDomain identity mismatch")
    if any(
        _ref_identity(domain.cas_ref) != _ref_identity(product.cas_ref)
        for product in product_rows
        for domain in (domains[product.byte_domain_id],)
    ):
        raise ValueError("runtime product ByteDomain CAS identity mismatch")

    proof_rows = tuple(closure_proofs)
    if len({proof.proof_id for proof in proof_rows}) != len(proof_rows):
        raise ValueError("closure proofs contain duplicate set-like values")
    if {proof.proof_id for proof in proof_rows} != set(binding.closure_proof_ids):
        raise ValueError("closure binding mismatch")
    if {proof.byte_domain_id for proof in proof_rows} != set(domains):
        raise ValueError("closure domains do not exactly match runtime product domains")
    for proof in proof_rows:
        if (
            not proof.status_bytes
            or any(
                not isinstance(count, int) or isinstance(count, bool) or count <= 0
                for count in proof.status_bytes.values()
            )
            or any(status not in {value.value for value in NodeStatus} for status in proof.status_bytes)
        ):
            raise ValueError("closure statusBytes are invalid")
        classified = sum(proof.status_bytes.values())
        derived_complete = classified == proof.domain_size
        expected_proof_id = typed_id("DeepMineClosureProof/v1", {
            "byteDomainId": proof.byte_domain_id,
            "rootNodeId": proof.root_node_id,
            "domainSize": str(proof.domain_size),
            "classifiedBytes": str(proof.classified_bytes),
            "statusBytes": dict(sorted(proof.status_bytes.items())),
            "complete": proof.complete,
        })
        if proof.proof_id != expected_proof_id:
            raise ValueError("trusted closure repository returned invalid proof identity")
        domain = domains[proof.byte_domain_id]
        expected_root = NodeRecord.root(
            domain.domain_id, domain.size, "runtime-product-root",
        )
        if (
            proof.domain_size != domain.size
            or proof.root_node_id != expected_root.node_id
            or proof.classified_bytes != classified
            or proof.complete != derived_complete
            or not proof.complete
        ):
            raise ValueError("incomplete closure or inconsistent accounting blocks promotion")

    fingerprint_rows = tuple(fingerprints)
    if len({row.fingerprint_id for row in fingerprint_rows}) != len(fingerprint_rows):
        raise ValueError("fingerprints contain duplicate set-like values")
    if {row.fingerprint_id for row in fingerprint_rows} != set(binding.fingerprint_ids):
        raise ValueError("fingerprint binding mismatch")
    if {row.artifact_id for row in fingerprint_rows} != set(binding.fingerprinted_artifact_ids):
        raise ValueError("fingerprinted artifact binding mismatch")
    if not fingerprint_rows:
        raise ValueError("at least one current fingerprint is required")
    proof_domains = {proof.byte_domain_id for proof in proof_rows}
    if any(row.byte_domain_id not in proof_domains for row in fingerprint_rows):
        raise ValueError("fingerprint domain is outside closure proofs")
    for row in fingerprint_rows:
        if not row.artifact_id or not row.schema_family or row.byte_length <= 0:
            raise ValueError("trusted fingerprint row is incomplete")
        for label, value in (
            ("fingerprint content", row.content_fingerprint),
            ("fingerprint structural", row.structural_fingerprint),
            ("fingerprint distribution", row.distribution_fingerprint),
        ):
            _require_hash(value, label)
        expected_fingerprint_id = typed_id("DeepMineFingerprint/v1", {
            "artifactId": row.artifact_id,
            "schemaFamily": row.schema_family,
            "byteDomainId": row.byte_domain_id,
            "byteLength": str(row.byte_length),
            "contentFingerprint": row.content_fingerprint,
            "structuralFingerprint": row.structural_fingerprint,
            "distributionFingerprint": row.distribution_fingerprint,
        })
        if row.fingerprint_id != expected_fingerprint_id:
            raise ValueError("trusted fingerprint repository returned invalid fingerprint identity")
    bound_content_hashes = {ref.sha256 for ref in _category_refs(binding)}
    if any(row.content_fingerprint not in bound_content_hashes for row in fingerprint_rows):
        raise ValueError("fingerprint content is outside bound raw/derived/asset CAS refs")

    unknown_rows = unknowns.records() if isinstance(unknowns, UnknownRegistry) else tuple(unknowns)
    relevant_unknowns = tuple(
        record for record in unknown_rows
        if any(evidence.byte_domain_id in proof_domains for evidence in record.evidence)
    )
    if {record.unknown_id for record in relevant_unknowns} != set(binding.unknown_ids):
        raise ValueError("unknown binding mismatch")
    if any(
        record.unknown_id != UnknownRegistry.stable_id(record.namespace, record.locator)
        for record in relevant_unknowns
    ):
        raise ValueError("trusted unknown repository returned invalid stable identity")
    for record in relevant_unknowns:
        if not record.evidence:
            raise ValueError("trusted unknown row lacks evidence")
        for evidence in record.evidence:
            domain = domains.get(evidence.byte_domain_id)
            if (
                domain is None
                or evidence.raw_sha256 != domain.cas_ref.sha256
                or evidence.offset < 0
                or evidence.length <= 0
                or evidence.offset + evidence.length > domain.size
                or not evidence.morphology
                or len(set(evidence.cooccurs_with)) != len(evidence.cooccurs_with)
            ):
                raise ValueError("trusted unknown evidence is outside exact ByteDomain bytes")
    unresolved = [
        record.unknown_id for record in relevant_unknowns
        if record.status not in {UnknownStatus.CONFIRMED, UnknownStatus.REJECTED}
        or record.capture_required
    ]
    if unresolved:
        raise ValueError(f"unresolved unknown blocks promotion: {sorted(unresolved)}")

    if set(nodes) != set(binding.consumed_node_ids):
        raise ValueError("consumer node binding mismatch")
    for node_id in binding.consumed_node_ids:
        node = nodes[node_id]
        expected_node_id = typed_id(
            "DeepMineNode/v1",
            NodeRecord.identity_payload(
                byte_domain_id=node.byte_domain_id,
                parent_node_id=node.parent_node_id,
                offset=node.offset,
                length=node.length,
                status=node.status,
                node_kind=node.node_kind,
                decoder_id=node.decoder_id,
                decoder_version=node.decoder_version,
                occurrence_index=node.occurrence_index,
                accounting=node.accounting,
                semantic_hypothesis=node.semantic_hypothesis,
                confidence=node.confidence,
                consumed_by=node.consumed_by,
            ),
        )
        if node.node_id != node_id or node.node_id != expected_node_id:
            raise ValueError(f"trusted node repository returned invalid identity for {node_id}")
        domain = domains.get(node.byte_domain_id)
        if (
            domain is None
            or node.offset < 0
            or node.length <= 0
            or node.offset + node.length > domain.size
            or node.status.value != "decoded"
        ):
            raise ValueError(f"consumer node {node_id} is outside decoded proved domains")
        if projector_id not in node.consumed_by:
            raise ValueError(f"consumer binding missing for node {node_id}")
        if node.semantic_hypothesis is not None and node.confidence != "confirmed":
            raise ValueError(f"unresolved hypothesis blocks promotion at node {node_id}")
    for product in product_rows:
        matches = tuple(
            row for row in fingerprint_rows
            if row.artifact_id == product.artifact_id
            and row.byte_domain_id == product.byte_domain_id
            and row.content_fingerprint == product.cas_ref.sha256
            and row.byte_length == product.cas_ref.size
        )
        if len(matches) != 1:
            raise ValueError("runtime product lacks exact current fingerprint")
        product_proofs = tuple(
            proof for proof in proof_rows
            if proof.byte_domain_id == product.byte_domain_id
            and proof.complete
            and proof.classified_bytes == proof.domain_size == product.cas_ref.size
            and proof.status_bytes == {"decoded": product.cas_ref.size}
        )
        if len(product_proofs) != 1:
            raise ValueError("runtime product lacks exact complete closure proof")
        proof = product_proofs[0]
        product_nodes = tuple(
            node for node in nodes.values()
            if node.byte_domain_id == product.byte_domain_id
            and node.parent_node_id == proof.root_node_id
            and node.offset == 0
            and node.length == product.cas_ref.size
            and node.status.value == "decoded"
            and node.accounting
            and projector_id in node.consumed_by
        )
        if len(product_nodes) != 1:
            raise ValueError("runtime product lacks one full-range consumed projector root node")


def _provenance_snapshot_payload(
    *,
    candidate: PromotionCandidate,
    candidate_ref: CASRef,
    ordered_parent_refs: tuple[CASRef, ...],
    closure_proofs: Iterable[ClosureProof],
    fingerprints: Iterable[ArtifactFingerprint],
    unknowns: UnknownRegistry | Iterable[UnknownRecord],
    nodes: Mapping[str, NodeRecord],
) -> dict[str, object]:
    unknown_rows = unknowns.records() if isinstance(unknowns, UnknownRegistry) else tuple(unknowns)
    domains = tuple(sorted((
        ByteDomain.create(product.cas_ref, parent_domain_id=None, transform_id=None)
        for product in candidate.product_refs
    ), key=lambda row: row.domain_id))
    return {
        "schema": "ai-caddie-trusted-promotion-provenance-v1",
        "candidateId": candidate.candidate_id,
        "candidateRef": _ref_payload(candidate_ref),
        "candidateSha256": candidate_ref.sha256,
        "bindingHash": hashlib.sha256(
            canonical_json_bytes(candidate.binding.canonical()),
        ).hexdigest(),
        "orderedParentRefs": [_ref_payload(ref) for ref in ordered_parent_refs],
        "byteDomains": [row.canonical() for row in domains],
        "closureProofs": [
            row.canonical() for row in sorted(closure_proofs, key=lambda row: row.proof_id)
        ],
        "fingerprints": [
            row.canonical() for row in sorted(fingerprints, key=lambda row: row.fingerprint_id)
        ],
        "unknownRecords": [
            row.canonical() for row in sorted(unknown_rows, key=lambda row: row.unknown_id)
        ],
        "nodes": [
            nodes[node_id].canonical() for node_id in sorted(nodes)
        ],
    }


def _strict_canonical_object(data: bytes, label: str) -> dict[str, object]:
    def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f"duplicate {label} key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite {label} number: {value}")

    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError(f"{label} is not canonical JSON")
    return value


def _decimal_int(value: object, label: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError(f"{label} must be an unsigned canonical decimal string")
    return int(value)


def _decode_provenance_snapshot(
    data: bytes,
    *,
    candidate: PromotionCandidate,
    candidate_ref: CASRef,
    ordered_parent_refs: tuple[CASRef, ...],
) -> tuple[
    tuple[ClosureProof, ...],
    tuple[ArtifactFingerprint, ...],
    tuple[UnknownRecord, ...],
    dict[str, NodeRecord],
]:
    root = _strict_canonical_object(data, "trusted promotion provenance")
    if set(root) != {
        "schema", "candidateId", "candidateRef", "candidateSha256", "bindingHash",
        "orderedParentRefs", "byteDomains", "closureProofs", "fingerprints",
        "unknownRecords", "nodes",
    }:
        raise ValueError("trusted promotion provenance shape invalid")
    if root["schema"] != "ai-caddie-trusted-promotion-provenance-v1":
        raise ValueError("trusted promotion provenance schema invalid")
    if root["candidateId"] != candidate.candidate_id:
        raise ValueError("trusted promotion provenance candidateId mismatch")
    if _decode_cas_ref(root["candidateRef"]) != candidate_ref:
        raise ValueError("trusted promotion provenance candidate CAS mismatch")
    if root["candidateSha256"] != candidate_ref.sha256:
        raise ValueError("trusted promotion provenance candidate hash mismatch")
    expected_binding_hash = hashlib.sha256(
        canonical_json_bytes(candidate.binding.canonical()),
    ).hexdigest()
    if root["bindingHash"] != expected_binding_hash:
        raise ValueError("trusted promotion provenance binding hash mismatch")
    snapshot_parents = tuple(_decode_cas_ref(row) for row in root["orderedParentRefs"])
    if snapshot_parents != ordered_parent_refs:
        raise ValueError("trusted promotion provenance parent set/order mismatch")

    domain_rows: dict[str, ByteDomain] = {}
    for row in root["byteDomains"]:
        if not isinstance(row, dict) or set(row) != {
            "domainId", "casRef", "parentDomainId", "transformId",
        }:
            raise ValueError("trusted ByteDomain row shape invalid")
        domain = ByteDomain(
            row["domainId"], _decode_cas_ref(row["casRef"]),
            row["parentDomainId"], row["transformId"],
        )
        expected = ByteDomain.create(
            domain.cas_ref,
            parent_domain_id=domain.parent_domain_id,
            transform_id=domain.transform_id,
        )
        if domain != expected or domain.canonical() != row:
            raise ValueError("trusted ByteDomain identity invalid")
        if domain.domain_id in domain_rows:
            raise ValueError("trusted ByteDomain rows contain duplicate identity")
        domain_rows[domain.domain_id] = domain
    if list(domain_rows) != sorted(domain_rows):
        raise ValueError("trusted ByteDomain rows are not canonical by domainId")
    expected_domains = {
        product.byte_domain_id: product.cas_ref for product in candidate.product_refs
    }
    if set(domain_rows) != set(expected_domains) or any(
        domain_rows[domain_id].cas_ref != ref for domain_id, ref in expected_domains.items()
    ):
        raise ValueError("trusted ByteDomain rows do not exactly bind product CAS identities")

    proof_rows: list[ClosureProof] = []
    for row in root["closureProofs"]:
        if not isinstance(row, dict) or set(row) != {
            "proofId", "byteDomainId", "rootNodeId", "domainSize",
            "classifiedBytes", "statusBytes", "complete",
        } or not isinstance(row["statusBytes"], dict) or not isinstance(row["complete"], bool):
            raise ValueError("trusted closure proof shape invalid")
        proof = ClosureProof(
            row["proofId"], row["byteDomainId"], row["rootNodeId"],
            _decimal_int(row["domainSize"], "closure domainSize"),
            _decimal_int(row["classifiedBytes"], "closure classifiedBytes"),
            dict(row["statusBytes"]), row["complete"],
        )
        if proof.canonical() != row:
            raise ValueError("trusted closure proof canonical form invalid")
        proof_rows.append(proof)
    if [row.proof_id for row in proof_rows] != sorted({row.proof_id for row in proof_rows}):
        raise ValueError("trusted closure proofs are not a canonical unique set")

    fingerprint_rows: list[ArtifactFingerprint] = []
    for row in root["fingerprints"]:
        if not isinstance(row, dict) or set(row) != {
            "fingerprintId", "artifactId", "schemaFamily", "byteDomainId", "byteLength",
            "contentFingerprint", "structuralFingerprint", "distributionFingerprint",
            "structuralTokens", "structuralCounts", "distributionSummaries",
        }:
            raise ValueError("trusted fingerprint shape invalid")
        counts: list[tuple[str, int]] = []
        for item in row["structuralCounts"]:
            if not isinstance(item, dict) or set(item) != {"token", "count"}:
                raise ValueError("trusted fingerprint structural count invalid")
            counts.append((item["token"], item["count"]))
        summaries: list[DistributionSummary] = []
        for item in row["distributionSummaries"]:
            if not isinstance(item, dict) or set(item) != {
                "series", "count", "minimumEncoded", "maximumEncoded", "medianEncoded",
                "p95Encoded", "valuesSha256",
            }:
                raise ValueError("trusted fingerprint distribution summary invalid")
            summaries.append(DistributionSummary(
                item["series"], item["count"], item["minimumEncoded"],
                item["maximumEncoded"], item["medianEncoded"], item["p95Encoded"],
                item["valuesSha256"],
            ))
        fingerprint = ArtifactFingerprint(
            row["fingerprintId"], row["artifactId"], row["schemaFamily"],
            row["byteDomainId"], _decimal_int(row["byteLength"], "fingerprint byteLength"),
            row["contentFingerprint"], row["structuralFingerprint"],
            row["distributionFingerprint"], tuple(row["structuralTokens"]),
            tuple(counts), tuple(summaries),
        )
        if (
            fingerprint.canonical() != row
            or tuple(counts) != tuple(sorted(set(counts)))
            or len({token for token, _count in counts}) != len(counts)
            or [item.series for item in summaries]
            != sorted({item.series for item in summaries})
        ):
            raise ValueError("trusted fingerprint canonical form invalid")
        fingerprint_rows.append(fingerprint)
    if [row.fingerprint_id for row in fingerprint_rows] != sorted({
        row.fingerprint_id for row in fingerprint_rows
    }):
        raise ValueError("trusted fingerprints are not a canonical unique set")

    unknown_rows: list[UnknownRecord] = []
    for row in root["unknownRecords"]:
        if not isinstance(row, dict) or set(row) != {
            "unknownId", "namespace", "locator", "firstObservedAt", "lastObservedAt",
            "evidence", "status", "priority", "hypothesis", "counterevidence",
            "nextMinimumEvidence", "captureRequired",
        }:
            raise ValueError("trusted unknown row shape invalid")
        evidence_rows: list[UnknownEvidence] = []
        for item in row["evidence"]:
            if not isinstance(item, dict) or set(item) != {
                "rawSha256", "byteDomainId", "offset", "length", "morphology", "cooccursWith",
            }:
                raise ValueError("trusted unknown evidence shape invalid")
            evidence_rows.append(UnknownEvidence(
                item["rawSha256"], item["byteDomainId"],
                _decimal_int(item["offset"], "unknown offset"),
                _decimal_int(item["length"], "unknown length"),
                item["morphology"], tuple(item["cooccursWith"]),
            ))
        unknown = UnknownRecord(
            row["unknownId"], row["namespace"], row["locator"], row["firstObservedAt"],
            row["lastObservedAt"], tuple(evidence_rows), UnknownStatus(row["status"]),
            row["priority"], row["hypothesis"], row["counterevidence"],
            row["nextMinimumEvidence"], row["captureRequired"],
        )
        if (
            unknown.canonical() != row
            or tuple(evidence_rows) != tuple(sorted(set(evidence_rows)))
        ):
            raise ValueError("trusted unknown canonical form invalid")
        unknown_rows.append(unknown)
    if [row.unknown_id for row in unknown_rows] != sorted({row.unknown_id for row in unknown_rows}):
        raise ValueError("trusted unknowns are not a canonical unique set")

    node_rows: dict[str, NodeRecord] = {}
    for row in root["nodes"]:
        if not isinstance(row, dict) or set(row) != {
            "nodeId", "byteDomainId", "parentNodeId", "offset", "length", "status",
            "nodeKind", "decoderId", "decoderVersion", "occurrenceIndex", "accounting",
            "semanticHypothesis", "confidence", "consumedBy",
        }:
            raise ValueError("trusted node shape invalid")
        node = NodeRecord(
            row["nodeId"], row["byteDomainId"], row["parentNodeId"],
            _decimal_int(row["offset"], "node offset"),
            _decimal_int(row["length"], "node length"), NodeStatus(row["status"]),
            row["nodeKind"], row["decoderId"], row["decoderVersion"],
            row["occurrenceIndex"], row["accounting"], row["semanticHypothesis"],
            row["confidence"], tuple(row["consumedBy"]),
        )
        if node.canonical() != row or node.node_id in node_rows:
            raise ValueError("trusted node canonical form/identity set invalid")
        node_rows[node.node_id] = node
    if list(node_rows) != sorted(node_rows):
        raise ValueError("trusted nodes are not canonical by nodeId")
    return tuple(proof_rows), tuple(fingerprint_rows), tuple(unknown_rows), node_rows


def _validate_derived_artifact_identity(artifact: DerivedArtifact) -> None:
    payload = artifact.canonical()
    del payload["artifactId"]
    if artifact.artifact_id != typed_id("DeepMineDerivedArtifact/v1", payload):
        raise ValueError("trusted candidate DerivedArtifact identity invalid")


def _validate_trusted_playable_source_inventory_record(
    record: TrustedPlayableSourceInventoryRecord,
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    binding: PromotionBinding,
    inventory_ref: CASRef,
    inventory_raw: bytes,
    source_inventory: Mapping[str, object],
) -> None:
    artifact = record.artifact
    if (
        artifact.ref != inventory_ref
        or artifact.ref.byte_domain
        != "deep-mine-playable-regions-source-inventory-evidence"
        or artifact.transform_name != "freeze-playable-regions-source-inventory"
        or artifact.transform_version != "1"
        or not artifact.build_hash
        or set(artifact.parameters) != {
            "ownerAccountId", "sourceRegionInventoryHash", "decoderVersion",
        }
        or artifact.parameters["ownerAccountId"] != binding.owner_account_id
        or artifact.parameters["sourceRegionInventoryHash"]
        != source_inventory["sourceRegionInventoryHash"]
    ):
        raise ValueError("trusted source inventory DerivedArtifact binding is invalid")
    _validate_derived_artifact_identity(artifact)
    if (
        len(inventory_raw) != inventory_ref.size
        or hashlib.sha256(inventory_raw).hexdigest() != record.inventory_sha256
    ):
        raise ValueError("trusted source inventory CAS bytes do not match record")
    if (
        record.provenance_ref.byte_domain
        != "deep-mine-playable-regions-source-inventory-provenance"
    ):
        raise ValueError("trusted source inventory provenance domain is invalid")
    try:
        provenance_bytes = cas.read_bytes(storage_domain_id, record.provenance_ref)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise ValueError("trusted source inventory provenance is not retrievable") from exc
    if (
        len(provenance_bytes) != record.provenance_ref.size
        or hashlib.sha256(provenance_bytes).hexdigest() != record.provenance_hash
    ):
        raise ValueError("trusted source inventory provenance hash is invalid")
    root = _strict_canonical_object(
        provenance_bytes, "trusted playable source inventory provenance",
    )
    if set(root) != {
        "schema", "ownerAccountId", "courseLayoutIdentity", "layoutRevisionId",
        "holeGlobalId", "sourceRevisionIds", "authorizedEvidenceIds",
        "sourceRegionInventoryHash", "sourceRegions", "sourceDomains",
        "sourceNodes", "closureProofs", "fingerprints", "artifact",
    } or root["schema"] != (
        "ai-caddie-trusted-playable-source-inventory-provenance-v1"
    ):
        raise ValueError("trusted source inventory provenance shape is invalid")
    if (
        root["ownerAccountId"] != binding.owner_account_id
        or root["courseLayoutIdentity"] != binding.course_layout_identity
        or root["layoutRevisionId"] != binding.layout_revision_id
        or root["holeGlobalId"] != binding.hole_global_id
        or root["sourceRevisionIds"] != source_inventory["sourceRevisionIds"]
        or root["sourceRegionInventoryHash"]
        != source_inventory["sourceRegionInventoryHash"]
        or root["sourceRegions"] != source_inventory["sourceRegions"]
        or root["artifact"] != artifact.canonical()
    ):
        raise ValueError("trusted source inventory provenance subject/snapshot drift")

    domains: dict[str, ByteDomain] = {}
    for row in root["sourceDomains"]:
        domain = ByteDomain(
            row["domainId"], _decode_cas_ref(row["casRef"]),
            row["parentDomainId"], row["transformId"],
        )
        if (
            set(row) != {"domainId", "casRef", "parentDomainId", "transformId"}
            or domain != ByteDomain.create(
                domain.cas_ref,
                parent_domain_id=domain.parent_domain_id,
                transform_id=domain.transform_id,
            )
            or domain.canonical() != row
            or domain.domain_id in domains
            or _ref_identity(domain.cas_ref)
            not in {_ref_identity(ref) for ref in artifact.parent_refs}
        ):
            raise ValueError("trusted source inventory ByteDomain identity is invalid")
        domains[domain.domain_id] = domain
    if list(domains) != sorted(domains):
        raise ValueError("trusted source inventory domains are not canonical")

    proofs: dict[str, Mapping[str, object]] = {}
    for row in root["closureProofs"]:
        payload = {key: value for key, value in row.items() if key != "proofId"}
        if (
            set(row) != {
                "proofId", "byteDomainId", "rootNodeId", "domainSize",
                "classifiedBytes", "statusBytes", "complete",
            }
            or row["proofId"] != typed_id("DeepMineClosureProof/v1", payload)
            or row["byteDomainId"] not in domains
            or row["complete"] is not True
            or _decimal_int(row["domainSize"], "source closure domainSize")
            != domains[row["byteDomainId"]].size
            or _decimal_int(row["classifiedBytes"], "source closure classifiedBytes")
            != domains[row["byteDomainId"]].size
            or row["proofId"] in proofs
        ):
            raise ValueError("trusted source inventory closure proof is invalid")
        proofs[row["proofId"]] = row

    fingerprints: dict[str, Mapping[str, object]] = {}
    for row in root["fingerprints"]:
        identity = {
            key: row[key] for key in (
                "artifactId", "schemaFamily", "byteDomainId", "byteLength",
                "contentFingerprint", "structuralFingerprint",
                "distributionFingerprint",
            )
        }
        if (
            row["fingerprintId"] != typed_id("DeepMineFingerprint/v1", identity)
            or row["byteDomainId"] not in domains
            or row["contentFingerprint"]
            != domains[row["byteDomainId"]].cas_ref.sha256
            or row["fingerprintId"] in fingerprints
        ):
            raise ValueError("trusted source inventory fingerprint identity is invalid")
        fingerprints[row["fingerprintId"]] = row

    nodes: dict[str, Mapping[str, object]] = {}
    for row in root["sourceNodes"]:
        expected_node_id = typed_id(
            "DeepMineNode/v1",
            NodeRecord.identity_payload(
                byte_domain_id=row["byteDomainId"],
                parent_node_id=row["parentNodeId"],
                offset=_decimal_int(row["offset"], "source node offset"),
                length=_decimal_int(row["length"], "source node length"),
                status=NodeStatus(row["status"]),
                node_kind=row["nodeKind"],
                decoder_id=row["decoderId"],
                decoder_version=row["decoderVersion"],
                occurrence_index=row["occurrenceIndex"],
                accounting=row["accounting"],
                semantic_hypothesis=row["semanticHypothesis"],
                confidence=row["confidence"],
                consumed_by=tuple(row["consumedBy"]),
            ),
        )
        if (
            row["nodeId"] != expected_node_id
            or row["byteDomainId"] not in domains
            or row["nodeId"] in nodes
        ):
            raise ValueError("trusted source inventory node identity is invalid")
        nodes[row["nodeId"]] = row

    authorized_evidence_ids = root["authorizedEvidenceIds"]
    if authorized_evidence_ids != sorted(set(authorized_evidence_ids)):
        raise ValueError("trusted source inventory evidence authority is noncanonical")
    for source_region in root["sourceRegions"]:
        if (
            not set(source_region["sourceNodeIds"]).issubset(nodes)
            or not set(source_region["closureProofIds"]).issubset(proofs)
            or not set(source_region["fingerprintIds"]).issubset(fingerprints)
            or not set(source_region["evidenceIds"]).issubset(authorized_evidence_ids)
            or any(
                nodes[node_id]["byteDomainId"]
                not in {proofs[proof_id]["byteDomainId"] for proof_id in source_region["closureProofIds"]}
                for node_id in source_region["sourceNodeIds"]
            )
            or any(
                fingerprints[fingerprint_id]["byteDomainId"]
                not in {proofs[proof_id]["byteDomainId"] for proof_id in source_region["closureProofIds"]}
                for fingerprint_id in source_region["fingerprintIds"]
            )
        ):
            raise ValueError("trusted source inventory row leaves its frozen provenance")


def _validate_candidate_core(
    payload: bytes | str | Mapping[str, object],
    *,
    storage_domain_id: str,
    expected_owner_account_id: str,
    expected_course_layout_identity: str,
    expected_layout_revision_id: str,
    expected_hole_global_id: str,
    expected_source_revision_ids: tuple[str, ...],
    expected_source_roster_hash: str,
) -> PromotionCandidate:
    raw = _strict_untrusted_candidate(payload)
    validate_candidate_schema(raw)
    candidate = _decode_candidate(raw)
    if candidate.canonical() != raw:
        raise ValueError("promotion candidate is not in canonical set order/form")
    if candidate.candidate_id != typed_id(
        "DeepMinePromotionCandidate/v1", candidate.payload(),
    ):
        raise ValueError("promotion candidateId does not match canonical candidate payload")
    if candidate.candidate_state != "research_only_candidate" or candidate.target_gate != "plan-2-capability-quality-gate":
        raise ValueError("promotion candidate state/gate is not admissible")
    if not candidate.projector_id or not candidate.quality_policy_version:
        raise ValueError("promotion projector and quality policy are required")

    binding = candidate.binding
    _validate_binding_shape(binding)
    _validate_product_refs(candidate)
    _validate_capability_evidence(
        candidate.capability,
        candidate.capability_evidence,
        binding,
        candidate.projector_id,
        candidate.product_refs[0].role,
    )
    expected_subject = f"hole:{binding.layout_revision_id}:{binding.hole_global_id}"
    if candidate.subject_ref != expected_subject:
        raise ValueError("promotion subject does not match layout revision/global-hole binding")
    if binding.owner_account_id != expected_owner_account_id:
        raise ValueError("promotion owner account does not match admission context")
    if binding.security_domain_id != storage_domain_id:
        raise ValueError("promotion storage/security domain does not match admission context")
    if binding.course_layout_identity != expected_course_layout_identity:
        raise ValueError("promotion course layout identity does not match admission context")
    if binding.layout_revision_id != expected_layout_revision_id:
        raise ValueError("promotion layout revision does not match admission context")
    if binding.hole_global_id != expected_hole_global_id:
        raise ValueError("promotion global hole does not match admission context")
    expected_source_ids = _canonical_string_set(
        expected_source_revision_ids, "expected sourceRevisionIds",
    )
    if set(binding.source_revision_ids) != set(expected_source_ids):
        raise ValueError("promotion source revision set is stale or outside admission context")
    if binding.source_roster_hash != expected_source_roster_hash:
        raise ValueError("promotion source roster hash is stale or outside admission context")
    return candidate


def _validate_green_evidence_cas_bodies(
    candidate: PromotionCandidate,
    *,
    product_payload: Mapping[str, object],
    evidence_bodies: Mapping[str, bytes],
) -> None:
    evidence = candidate.capability_evidence
    if not isinstance(evidence, GreenSurfaceEvidence):
        raise ValueError("greenSurface candidate lacks typed green evidence")
    common = {
        "courseLayoutIdentity": candidate.binding.course_layout_identity,
        "layoutRevisionId": candidate.binding.layout_revision_id,
        "holeGlobalId": candidate.binding.hole_global_id,
        "greenSourceRevisionId": evidence.green_source_revision_id,
        "baseSourceRevisionId": evidence.base_source_revision_id,
        "greenSourceSha256": evidence.green_source_sha256,
        "selectedComponentId": evidence.selected_component_id,
        "decoderId": evidence.decoder_id,
        "decoderVersion": evidence.decoder_version,
        "calibrationId": evidence.calibration_id,
        "orientationTransformId": evidence.orientation_transform_id,
        "orientationTransform": product_payload["orientationTransform"],
        "baseGeometryHash": evidence.base_geometry_hash,
        "registrationResidualM": evidence.registration_residual_m,
        "crossSourceResidualM": evidence.cross_source_residual_m,
        "registrationSampleCount": evidence.registration_sample_count,
        "accepted": True,
    }
    for kind, schema in (
        ("greenRegistration", "ai-caddie-green-registration-report-v1"),
        ("greenCrossSource", "ai-caddie-green-cross-source-evidence-v1"),
    ):
        raw = evidence_bodies.get(kind)
        if raw is None:
            raise ValueError(f"{kind} evidence CAS body is missing")
        parsed = _strict_canonical_object(raw, kind)
        expected = {"schema": schema, **common}
        if parsed != expected:
            raise ValueError(
                f"{kind} evidence body does not exactly bind subject, revisions, "
                "transform, base geometry, and registration measurements"
            )


def _validate_playable_regions_evidence_cas_bodies(
    candidate: PromotionCandidate,
    *,
    product_payload: Mapping[str, object],
    evidence_bodies: Mapping[str, bytes],
) -> None:
    evidence = candidate.capability_evidence
    if not isinstance(evidence, HazardGuidanceEvidence):
        raise ValueError("playable-regions candidate lacks typed hazard guidance evidence")
    binding = candidate.binding
    if (
        product_payload["layoutRevisionId"] != binding.layout_revision_id
        or product_payload["holeGlobalId"] != binding.hole_global_id
        or product_payload["subjectRef"] != candidate.subject_ref
    ):
        raise ValueError("playable-regions product subject binding is not exact")
    _require_unique_bound_ref_for_hash(
        binding.derived_refs,
        product_payload["mapGeometryHash"],
        "playable-regions mapGeometryHash",
    )
    source_inventory_raw = evidence_bodies.get("playableRegionsSourceInventory")
    topology_raw = evidence_bodies.get("playableRegionsTopology")
    coverage_raw = evidence_bodies.get("playableRegionsCoverage")
    if source_inventory_raw is None:
        raise ValueError("playableRegionsSourceInventory evidence CAS body is missing")
    if topology_raw is None:
        raise ValueError("playableRegionsTopology evidence CAS body is missing")
    if coverage_raw is None:
        raise ValueError("playableRegionsCoverage evidence CAS body is missing")
    if any(
        len(raw) > _MAX_PLAYABLE_REGIONS_BODY_BYTES
        for raw in (source_inventory_raw, topology_raw, coverage_raw)
    ):
        raise ValueError("playable-regions evidence body byte budget exceeded")
    source_inventory = _strict_canonical_object(
        source_inventory_raw, "playableRegionsSourceInventory evidence body",
    )
    _strict_canonical_object(
        topology_raw, "playableRegionsTopology evidence body",
    )
    _strict_canonical_object(
        coverage_raw, "playableRegionsCoverage evidence body",
    )
    if set(source_inventory) != {
        "schema", "inventoryBuildStage", "courseLayoutIdentity",
        "layoutRevisionId", "holeGlobalId", "sourceRevisionIds",
        "mapGeometryHash", "mapGeometryEnvelope", "sourceRegionInventoryHash",
        "sourceRegions", "complete",
    }:
        raise ValueError("playable source inventory fields do not match schema")
    source_regions = source_inventory["sourceRegions"]
    if (
        not isinstance(source_regions, list)
        or not source_regions
        or len(source_regions) > _MAX_PLAYABLE_REGIONS
    ):
        raise ValueError("playable source inventory region budget is invalid")

    def canonical_ids(raw: object, label: str, *, hashes: bool) -> list[str]:
        if (
            not isinstance(raw, list) or not raw
            or any(not isinstance(item, str) or not item for item in raw)
            or raw != sorted(set(raw))
            or hashes and any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in raw)
        ):
            raise ValueError(f"{label} must be a canonical nonempty identity set")
        return raw

    expected_region_refs: list[str] = []
    source_object_refs: list[str] = []
    for source_region in source_regions:
        if not isinstance(source_region, dict) or set(source_region) != {
            "regionRef", "sourceRevisionId", "sourceObjectRef", "sourceNodeIds",
            "closureProofIds", "fingerprintIds", "evidenceIds",
        }:
            raise ValueError("playable source region fields do not match schema")
        if (
            not isinstance(source_region["regionRef"], str)
            or not source_region["regionRef"]
            or source_region["sourceRevisionId"] not in evidence.source_revision_ids
            or not isinstance(source_region["sourceObjectRef"], str)
            or not source_region["sourceObjectRef"]
        ):
            raise ValueError("playable source region identity is invalid")
        canonical_ids(source_region["sourceNodeIds"], "sourceNodeIds", hashes=True)
        canonical_ids(source_region["closureProofIds"], "closureProofIds", hashes=True)
        canonical_ids(source_region["fingerprintIds"], "fingerprintIds", hashes=True)
        evidence_ids = canonical_ids(
            source_region["evidenceIds"], "source evidenceIds", hashes=False,
        )
        if not set(evidence_ids).issubset(binding.evidence_refs):
            raise ValueError("playable source inventory evidence IDs leave binding")
        expected_region_refs.append(source_region["regionRef"])
        source_object_refs.append(source_region["sourceObjectRef"])
    if expected_region_refs != sorted(set(expected_region_refs)):
        raise ValueError("playable source inventory is not canonical by regionRef")
    if any(not value for value in source_object_refs) or (
        len(set(source_object_refs)) != len(source_object_refs)
    ):
        raise ValueError("playable source inventory has empty or duplicate source objects")

    source_inventory_hash = hashlib.sha256(
        canonical_json_bytes(source_regions),
    ).hexdigest()
    source_inventory_evidence_hash = hashlib.sha256(source_inventory_raw).hexdigest()
    source_revision_ids = sorted(evidence.source_revision_ids)
    expected_source_inventory_header = {
        "schema": "ai-caddie-playable-regions-source-inventory-v1",
        "inventoryBuildStage": "source_decode_before_product_projection",
        "courseLayoutIdentity": binding.course_layout_identity,
        "layoutRevisionId": binding.layout_revision_id,
        "holeGlobalId": binding.hole_global_id,
        "sourceRevisionIds": source_revision_ids,
        "mapGeometryHash": product_payload["mapGeometryHash"],
        "mapGeometryEnvelope": product_payload["mapGeometryEnvelope"],
        "sourceRegionInventoryHash": source_inventory_hash,
        "sourceRegions": source_regions,
        "complete": True,
    }
    if (
        source_inventory != expected_source_inventory_header
        or source_inventory_evidence_hash
        != product_payload["sourceInventoryEvidenceHash"]
    ):
        raise ValueError(
            "playableRegionsSourceInventory evidence body does not exactly bind "
            "the pre-projection source roster, source provenance IDs, map authority, "
            "subject, and revisions"
        )

    regions_hash = _playable_regions_hash(product_payload["regions"])
    observed_region_refs = [
        region["regionRef"] for region in product_payload["regions"]
    ]
    if expected_region_refs != observed_region_refs:
        raise ValueError(
            "playable-regions completeness mismatch: independent source inventory "
            "and observed product regionRefs must be exactly equal"
        )
    # `complete: true` below is derived only after this equality; it is never
    # accepted as self-authenticating completeness evidence.
    topology_hash = hashlib.sha256(topology_raw).hexdigest()
    coverage_hash = hashlib.sha256(coverage_raw).hexdigest()
    expected_topology = {
        "schema": "ai-caddie-playable-regions-topology-evidence-v1",
        "courseLayoutIdentity": binding.course_layout_identity,
        "layoutRevisionId": binding.layout_revision_id,
        "holeGlobalId": binding.hole_global_id,
        "sourceRevisionIds": source_revision_ids,
        "mapGeometryHash": product_payload["mapGeometryHash"],
        "mapGeometryEnvelope": product_payload["mapGeometryEnvelope"],
        "horizontalCrs": product_payload["horizontalCrs"],
        "horizontalUnit": product_payload["horizontalUnit"],
        "registrationResidualM": product_payload["registrationResidualM"],
        "sourceInventoryEvidenceHash": source_inventory_evidence_hash,
        "sourceRegionInventoryHash": source_inventory_hash,
        "regionsHash": regions_hash,
        "regionRefs": observed_region_refs,
        "closed": True,
        "oriented": True,
        "selfIntersectionFree": True,
        "interiorNonOverlapping": True,
        "boundaryContactPolicy": "allow_cross_region_touch_and_shared_edge",
    }
    if (
        topology_hash != product_payload["topologyEvidenceHash"]
        or topology_hash != evidence.playable_regions_topology_evidence_hash
        or topology_raw != canonical_json_bytes(expected_topology)
    ):
        raise ValueError(
            "playableRegionsTopology evidence body does not exactly bind "
            "product regions, subject, revisions, map authority, and topology"
        )
    expected_coverage = {
        "schema": "ai-caddie-playable-regions-coverage-evidence-v1",
        "courseLayoutIdentity": binding.course_layout_identity,
        "layoutRevisionId": binding.layout_revision_id,
        "holeGlobalId": binding.hole_global_id,
        "sourceRevisionIds": source_revision_ids,
        "mapGeometryHash": product_payload["mapGeometryHash"],
        "mapGeometryEnvelope": product_payload["mapGeometryEnvelope"],
        "sourceInventoryEvidenceHash": source_inventory_evidence_hash,
        "sourceRegionInventoryHash": source_inventory_hash,
        "topologyEvidenceHash": topology_hash,
        "regionsHash": regions_hash,
        "expectedRegionRefs": expected_region_refs,
        "observedRegionRefs": observed_region_refs,
        "complete": True,
    }
    if (
        coverage_hash != product_payload["coverageEvidenceHash"]
        or coverage_hash != evidence.playable_regions_coverage_evidence_hash
        or coverage_raw != canonical_json_bytes(expected_coverage)
    ):
        raise ValueError(
            "playableRegionsCoverage evidence body does not exactly bind "
            "the independent source inventory, observed product regions, topology, "
            "subject, revisions, and complete coverage"
        )


def _validate_parent_cas(
    candidate: PromotionCandidate,
    *,
    cas: EncryptedCAS,
    trusted_candidate_store: TrustedPromotionCandidateStore,
    storage_domain_id: str,
    parent_refs: tuple[CASRef, ...],
) -> tuple[CASRef, ...]:
    binding = candidate.binding

    parent_identities = tuple(_ref_identity(ref) for ref in parent_refs)
    if len(set(parent_identities)) != len(parent_identities):
        raise ValueError("promotion parent_refs contains duplicate set-like values")
    ordered_parent_refs = tuple(sorted(parent_refs, key=_ref_identity))
    expected_parent_identities = {
        *(_ref_identity(ref) for ref in _category_refs(binding)),
        *(_ref_identity(row.cas_ref) for row in binding.evidence_cas_refs),
    }
    trusted_source_record: TrustedPlayableSourceInventoryRecord | None = None
    if any(
        product.role == "guidance.playable-regions"
        for product in candidate.product_refs
    ):
        source_row = _evidence_rows_by_kind(binding).get(
            "playableRegionsSourceInventory",
        )
        if source_row is None:
            raise ValueError("playable source inventory evidence row is missing")
        trusted_source_record = trusted_candidate_store.get_source_inventory_by_ref(
            source_row.cas_ref,
        )
        source_trust = source_row.source_inventory_trust
        if source_trust is None or (
            source_trust.artifact_id
            != trusted_source_record.artifact.artifact_id
            or source_trust.record_sha256
            != trusted_source_record.record_sha256
            or source_trust.provenance_hash
            != trusted_source_record.provenance_hash
            or source_trust.provenance_ref
            != trusted_source_record.provenance_ref
        ):
            raise ValueError(
                "playable source inventory trust object does not match trusted freeze record"
            )
        expected_parent_identities.add(
            _ref_identity(trusted_source_record.provenance_ref),
        )
    if set(parent_identities) != expected_parent_identities:
        raise ValueError(
            "promotion parent_refs must exactly equal category/evidence CAS refs "
            "plus the trusted source-inventory provenance ref"
        )
    products_by_identity = {
        _ref_identity(product.cas_ref): product for product in candidate.product_refs
    }
    evidence_by_identity = {
        _ref_identity(row.cas_ref): row.evidence_kind
        for row in candidate.binding.evidence_cas_refs
    }
    validated_product_payloads: dict[str, dict[str, object]] = {}
    evidence_bodies: dict[str, bytes] = {}
    for ref in ordered_parent_refs:
        if ref.storage_domain_id != storage_domain_id:
            raise ValueError("promotion parent crosses storage/security domain")
        try:
            data = cas.read_bytes(storage_domain_id, ref)
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            raise ValueError(f"promotion parent is not retrievable: {_ref_identity(ref)}") from exc
        if len(data) != ref.size or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError(f"promotion parent bytes do not match CASRef: {_ref_identity(ref)}")
        if product := products_by_identity.get(_ref_identity(ref)):
            validated_product_payloads[product.role] = validate_promotion_product_bytes(
                product, data, candidate.capability_evidence,
            )
        evidence_kind = evidence_by_identity.get(_ref_identity(ref))
        if evidence_kind is not None:
            evidence_bodies[evidence_kind] = data
    playable_payload = validated_product_payloads.get("guidance.playable-regions")
    if playable_payload is not None:
        if trusted_source_record is None:
            raise ValueError("playable source inventory lacks a trusted freeze record")
        source_inventory_raw = evidence_bodies.get(
            "playableRegionsSourceInventory",
        )
        if source_inventory_raw is None:
            raise ValueError("playable source inventory body is missing")
        source_inventory = _strict_canonical_object(
            source_inventory_raw, "playableRegionsSourceInventory evidence body",
        )
        _validate_trusted_playable_source_inventory_record(
            trusted_source_record,
            cas=cas,
            storage_domain_id=storage_domain_id,
            binding=binding,
            inventory_ref=next(
                row.cas_ref for row in binding.evidence_cas_refs
                if row.evidence_kind == "playableRegionsSourceInventory"
            ),
            inventory_raw=source_inventory_raw,
            source_inventory=source_inventory,
        )
        _validate_playable_regions_evidence_cas_bodies(
            candidate,
            product_payload=playable_payload,
            evidence_bodies=evidence_bodies,
        )
    if candidate.capability == "greenSurface":
        product_payload = validated_product_payloads.get("greenSurfaceGeometry")
        if product_payload is None:
            raise ValueError("greenSurface runtime product was not validated")
        _validate_green_evidence_cas_bodies(
            candidate,
            product_payload=product_payload,
            evidence_bodies=evidence_bodies,
        )
    if elevation_payload := validated_product_payloads.get("playsLike.elevation"):
        if (
            elevation_payload["layoutRevisionId"] != binding.layout_revision_id
            or elevation_payload["holeGlobalId"] != binding.hole_global_id
            or elevation_payload["subjectRef"] != candidate.subject_ref
        ):
            raise ValueError("playsLike elevation product subject binding is not exact")
        _require_unique_bound_ref_for_hash(
            binding.derived_refs,
            elevation_payload["mapGeometryHash"],
            "playsLike elevation mapGeometryHash",
        )
    return ordered_parent_refs


def validate_untrusted_promotion_candidate(
    payload: bytes | str | Mapping[str, object],
    *,
    cas: EncryptedCAS,
    trusted_candidate_store: TrustedPromotionCandidateStore,
    storage_domain_id: str,
    parent_refs: tuple[CASRef, ...],
    expected_owner_account_id: str,
    expected_course_layout_identity: str,
    expected_layout_revision_id: str,
    expected_hole_global_id: str,
    expected_source_revision_ids: tuple[str, ...],
    expected_source_roster_hash: str,
) -> ValidatedPromotionCandidate:
    if trusted_candidate_store.storage_domain_id != storage_domain_id:
        raise ValueError("trusted candidate store/admission storage domain mismatch")
    candidate = _validate_candidate_core(
        payload,
        storage_domain_id=storage_domain_id,
        expected_owner_account_id=expected_owner_account_id,
        expected_course_layout_identity=expected_course_layout_identity,
        expected_layout_revision_id=expected_layout_revision_id,
        expected_hole_global_id=expected_hole_global_id,
        expected_source_revision_ids=expected_source_revision_ids,
        expected_source_roster_hash=expected_source_roster_hash,
    )
    ordered_parent_refs = _validate_parent_cas(
        candidate,
        cas=cas,
        trusted_candidate_store=trusted_candidate_store,
        storage_domain_id=storage_domain_id,
        parent_refs=parent_refs,
    )
    try:
        record = trusted_candidate_store.get(candidate.candidate_id)
    except (KeyError, TypeError, IndexError, sqlite3.DatabaseError) as exc:
        raise ValueError("trusted candidate index typed decode failed") from exc
    candidate_bytes = canonical_json_bytes(candidate.canonical())
    if (
        record.provenance_ref.byte_domain != "deep-mine-promotion-provenance"
        or record.candidate_sha256 != hashlib.sha256(candidate_bytes).hexdigest()
        or record.artifact.ref.sha256 != record.candidate_sha256
        or record.artifact.ref.size != len(candidate_bytes)
        or record.artifact.ref.byte_domain != "deep-mine-promotion-candidate"
        or record.artifact.parent_refs != ordered_parent_refs
        or record.artifact.transform_name != "deep-mine-promotion-candidate"
        or record.artifact.parameters != {
            "candidateId": candidate.candidate_id,
            "capability": candidate.capability,
            "targetGate": candidate.target_gate,
        }
        or not record.artifact.transform_version
        or not record.artifact.build_hash
    ):
        raise ValueError("trusted candidate artifact binding is invalid")
    _validate_derived_artifact_identity(record.artifact)
    try:
        stored_candidate = cas.read_bytes(storage_domain_id, record.artifact.ref)
        provenance_bytes = cas.read_bytes(storage_domain_id, record.provenance_ref)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise ValueError("trusted candidate or provenance CAS object is not retrievable") from exc
    if stored_candidate != candidate_bytes:
        raise ValueError("trusted candidate CAS bytes do not match admitted candidate")
    if (
        len(provenance_bytes) != record.provenance_ref.size
        or hashlib.sha256(provenance_bytes).hexdigest() != record.provenance_hash
    ):
        raise ValueError("trusted promotion provenance CAS bytes do not match record")
    try:
        proofs, fingerprints, unknowns, nodes = _decode_provenance_snapshot(
            provenance_bytes,
            candidate=candidate,
            candidate_ref=record.artifact.ref,
            ordered_parent_refs=ordered_parent_refs,
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("trusted promotion provenance typed decode failed") from exc
    _validate_research_provenance(
        binding=candidate.binding,
        projector_id=candidate.projector_id,
        product_refs=candidate.product_refs,
        closure_proofs=proofs,
        fingerprints=fingerprints,
        unknowns=unknowns,
        nodes=nodes,
    )
    return ValidatedPromotionCandidate(candidate, ordered_parent_refs, record)


def build_promotion_candidate(
    *,
    capability: str,
    product_role: str,
    subject_ref: str,
    projector_id: str,
    quality_policy_version: str,
    binding: PromotionBinding,
    closure_proofs: Iterable[ClosureProof],
    fingerprints: Iterable[ArtifactFingerprint],
    unknowns: UnknownRegistry,
    nodes: Mapping[str, NodeRecord],
    capability_evidence: CapabilityEvidence,
) -> PromotionCandidate:
    if not all((
        capability, product_role, subject_ref, projector_id, quality_policy_version,
    )):
        raise ValueError("promotion identity fields are required")
    _validate_binding_shape(binding)
    proof_rows = tuple(closure_proofs)
    fingerprint_rows = tuple(fingerprints)
    product_refs = _product_refs_for(
        capability,
        product_role,
        binding,
        proof_rows,
        fingerprint_rows,
    )
    _validate_research_provenance(
        binding=binding, projector_id=projector_id, product_refs=product_refs,
        closure_proofs=proof_rows, fingerprints=fingerprint_rows,
        unknowns=unknowns, nodes=nodes,
    )
    if subject_ref != f"hole:{binding.layout_revision_id}:{binding.hole_global_id}":
        raise ValueError("promotion subject does not match layout revision/global-hole binding")

    _validate_capability_evidence(
        capability,
        capability_evidence,
        binding,
        projector_id,
        product_refs[0].role,
    )

    provisional = PromotionCandidate(
        "",
        "research_only_candidate",
        "plan-2-capability-quality-gate",
        capability,
        subject_ref,
        projector_id,
        quality_policy_version,
        binding,
        product_refs,
        capability_evidence,
    )
    candidate = PromotionCandidate(
        typed_id("DeepMinePromotionCandidate/v1", provisional.payload()),
        provisional.candidate_state,
        provisional.target_gate,
        provisional.capability,
        provisional.subject_ref,
        provisional.projector_id,
        provisional.quality_policy_version,
        provisional.binding,
        provisional.product_refs,
        provisional.capability_evidence,
    )
    validate_candidate_schema(candidate)
    return candidate
```

- [ ] **Step 5: Persist candidates as research-derived objects without a publish API**

Append to the same file:

```python
def persist_promotion_candidate(
    candidate: PromotionCandidate,
    *,
    cas: EncryptedCAS,
    trusted_candidate_store: TrustedPromotionCandidateStore,
    closure_proofs: Iterable[ClosureProof],
    fingerprints: Iterable[ArtifactFingerprint],
    unknowns: UnknownRegistry,
    nodes: Mapping[str, NodeRecord],
    owner_account_id: str,
    storage_domain_id: str,
    parent_refs: tuple[CASRef, ...],
    decoder_version: str,
    build_hash: str,
) -> DerivedArtifact:
    if trusted_candidate_store.storage_domain_id != storage_domain_id:
        raise ValueError("trusted candidate store/persistence storage domain mismatch")
    checked = _validate_candidate_core(
        candidate.canonical(),
        storage_domain_id=storage_domain_id,
        expected_owner_account_id=owner_account_id,
        expected_course_layout_identity=candidate.binding.course_layout_identity,
        expected_layout_revision_id=candidate.binding.layout_revision_id,
        expected_hole_global_id=candidate.binding.hole_global_id,
        expected_source_revision_ids=candidate.binding.source_revision_ids,
        expected_source_roster_hash=candidate.binding.source_roster_hash,
    )
    proof_rows = tuple(closure_proofs)
    fingerprint_rows = tuple(fingerprints)
    _validate_research_provenance(
        binding=checked.binding,
        projector_id=checked.projector_id,
        product_refs=checked.product_refs,
        closure_proofs=proof_rows,
        fingerprints=fingerprint_rows,
        unknowns=unknowns,
        nodes=nodes,
    )
    ordered_parent_refs = _validate_parent_cas(
        checked,
        cas=cas,
        trusted_candidate_store=trusted_candidate_store,
        storage_domain_id=storage_domain_id,
        parent_refs=parent_refs,
    )
    candidate_bytes = canonical_json_bytes(checked.canonical())
    artifact = put_derived(
        cas=cas,
        storage_domain_id=storage_domain_id,
        byte_domain="deep-mine-promotion-candidate",
        data=candidate_bytes,
        parent_refs=ordered_parent_refs,
        transform_name="deep-mine-promotion-candidate",
        transform_version=decoder_version,
        parameters={
            "candidateId": candidate.candidate_id,
            "capability": candidate.capability,
            "targetGate": candidate.target_gate,
        },
        build_hash=build_hash,
    )
    provenance_bytes = canonical_json_bytes(_provenance_snapshot_payload(
        candidate=checked,
        candidate_ref=artifact.ref,
        ordered_parent_refs=ordered_parent_refs,
        closure_proofs=proof_rows,
        fingerprints=fingerprint_rows,
        unknowns=unknowns,
        nodes=nodes,
    ))
    provenance_ref = cas.put_bytes(
        storage_domain_id, "deep-mine-promotion-provenance", provenance_bytes,
    )
    record = TrustedPromotionCandidateRecord.create(
        candidate_id=checked.candidate_id,
        candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        provenance_ref=provenance_ref,
        artifact=artifact,
    )
    trusted_candidate_store._record_verified(
        record, token=_TRUSTED_STORE_WRITE_TOKEN,
    )
    validate_untrusted_promotion_candidate(
        candidate_bytes,
        cas=cas,
        trusted_candidate_store=trusted_candidate_store,
        storage_domain_id=storage_domain_id,
        parent_refs=ordered_parent_refs,
        expected_owner_account_id=owner_account_id,
        expected_course_layout_identity=checked.binding.course_layout_identity,
        expected_layout_revision_id=checked.binding.layout_revision_id,
        expected_hole_global_id=checked.binding.hole_global_id,
        expected_source_revision_ids=checked.binding.source_revision_ids,
        expected_source_roster_hash=checked.binding.source_roster_hash,
    )
    return artifact
```

The module ends here. It exports value objects, schema validation, the domain-scoped immutable `TrustedPromotionCandidateStore`, one builder-only persistence path, and the single public `validate_untrusted_promotion_candidate(...) -> ValidatedPromotionCandidate` admission boundary. Persistence writes canonical candidate bytes and a complete canonical provenance snapshot to separate CAS byte domains, then transactionally inserts an idempotent SQLite authority row; it never publishes a course capability. Plan 2 calls only the public validator inside its semantic-build transaction and must not copy private validation logic. The validator strict-decodes candidate/store/snapshot bytes, rejects duplicate or noncanonical sets, recomputes candidate/record/DerivedArtifact/ByteDomain/closure/fingerprint/node/unknown identities, verifies exact product bytes against capability evidence, checks owner/security-domain/layout/revision/global-hole plus the complete current SourceRevision set and `sourceRosterHash`, and requires `parent_refs` to equal the exact structured raw/derived/asset/evidence CAS tuple set plus the trusted source-inventory provenance ref for playable regions. Only then may Plan 2 apply its versioned quality policy and generate the canonical `QualityReport`/`qualityReportHash`. Track C binds `researchEvidenceReportHash` to its own retrievable evidence CAS parent but never includes the later `qualityReportHash`, so no candidate/report identity cycle can form.

- [ ] **Step 6: Register candidates and run evidence and boundary tests**

Verify C1's exact `DeepMinePromotionCandidate/v1` entry and strict `promotionCandidate` schema. The canonical object retains the full owner/security-domain/layout/revision/roster/global-hole binding, exact structured `rawRefs/derivedRefs/assetRefs`, closure/fingerprint/unknown/consumer/research evidence, and exactly one `playsLike`, set-valued `hazardGuidance`, or `greenSurface` evidence object; it cannot contain a Plan 2 `qualityReportHash`. The hazard set and exhaustive coverage CAS bodies bind the same layout revision, global hole, exact SourceRevision set, and set hash, so multi-hazard and verified-empty states cannot be replayed across holes or paired across runs. Playable-region promotion additionally requires a separately persisted pre-projection source inventory, its strict `sourceInventoryTrust` object, trusted provenance parent, node/closure/fingerprint/evidence IDs, roster hash, map envelope, topology evidence, and coverage evidence; expected refs come only from that frozen source inventory while observed refs come only from the runtime product, and `complete: true` is accepted only after the two lists are exactly equal. The green fixture binds distinct green/base SourceRevisions and evidence-bound slope/direction/orientation values; the same display hole number in another layout revision must fail the subject check.

Run:

```bash
uv run python -m unittest \
  tests.test_deep_mine_promotion \
  tests.test_deep_mine_node_ledger \
  tests.test_deep_mine_fingerprint_diff \
  tests.test_deep_mine_unknown_registry -v
uv run python - <<'PY'
from pathlib import Path
root = Path('ai_caddie/research/deep_mine')
for path in root.rglob('*.py'):
    text = path.read_text()
    for forbidden in (
        'ai_caddie.course_data.snapshot_builder',
        'ai_caddie.course_data.channels',
        'CourseReleaseChannel',
        'qualityReportHash',
        'def publish(',
        'publish_snapshot(',
        'publish_channel(',
        'advance_channel(',
    ):
        assert forbidden not in text, f'{path}: {forbidden}'
print('research-publish-boundary: PASS')
PY
```

Expected: all unit tests PASS and the guard prints `research-publish-boundary: PASS`; Plan 2's shared schema validator accepts each exact capability union and rejects extra/mismatched fields; candidate identity is invariant under every permutation of set-like binding arrays; multi-hazard and evidence-backed empty products validate. Adjacent cross-region shared edges pass while boundary runtime lookup returns unavailable; proper crossings, strict interior overlap, identical polygons, and same-side shared edges with different segmentation fail. Product/topology/coverage cannot synchronously delete a region retained by the independent source inventory. Oversized bodies, excessive regions/rings/points/comparisons, `1e308`, non-finite/overflow intermediates, invalid or unbound map envelopes, and out-of-envelope coordinates fail closed, as do duplicate/noncanonical product JSON, semantic body/evidence drift, same-bytes/different-domain substitution, forged closure/fingerprint/node IDs, missing/tampered trusted rows or provenance snapshots, stale source heads/roster, cross-revision display-hole aliasing, incomplete closure, unresolved unknowns/hypotheses, unconsumed product roots, and non-retrievable/wrong-domain evidence CAS refs.

- [ ] **Step 7: Commit C15**

```bash
git add ai_caddie/research/deep_mine/playable_regions.py ai_caddie/research/deep_mine/promotion.py tests/test_deep_mine_promotion.py
git commit -m "feat(research): emit evidence-bound promotion candidates"
```

### Task 16: C16 — Replay the frozen corpus deterministically and wire CLI plus CI

**Files:**
- Modify: `contracts/canonical/deep_mine_v1.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tests/deep_mine_fixture_builders.py`
- Create: `ai_caddie/research/deep_mine/runner.py`
- Create: `ai_caddie/research/deep_mine/cli.py`
- Create: `tests/test_deep_mine_replay.py`
- Create: `tests/fixtures/deep_mine_replay_v1.sha256`
- Modify: `package.json`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add a six-format synthetic frozen corpus and failing deterministic replay tests**

Append to `tests/deep_mine_fixture_builders.py`:

```python
from pathlib import Path

from PIL import Image

from ai_caddie.course_data.cas import EncryptedCAS
from ai_caddie.research.deep_mine.corpus import CorpusArtifact, FrozenCorpusManifest


def build_test_gif() -> bytes:
    first = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    second = Image.new("RGBA", (2, 2), (0, 255, 0, 255))
    stream = BytesIO()
    first.save(stream, format="GIF", save_all=True, append_images=[second], duration=20, loop=0)
    return stream.getvalue()


def build_full_format_corpus(
    *,
    cas: EncryptedCAS,
    storage_domain_id: str,
    decoder_set_id: str,
) -> FrozenCorpusManifest:
    dskimg, _wrapper = build_synthetic_dskimg()
    bodies = (
        (
            "protobuf", b"\x08\x01\x12\x03new", "application/x-protobuf",
            "course-layout-release", "synthetic-protobuf", ("region:cn", "holes:9", "version:1"),
        ),
        (
            "json", b'{"a":1.2300,"a":null}', "application/json",
            "hole-json", "synthetic-json", ("region:us", "holes:18", "terrain:flat"),
        ),
        (
            "archive", build_zip([("rare/layer.drc", b"one"), ("rare/layer.drc", b"two")], prefix=b"GAP"),
            "application/zip", "prodgeometry-archive", "synthetic-archive", ("coast:inland", "branch:rare-drc"),
        ),
        (
            "texture", build_test_gif(), "image/gif",
            "texture", "synthetic-texture", ("coast:coastal", "terrain:mountain"),
        ),
        (
            "draco", Path("node_modules/draco3d/bunny.drc").read_bytes(), "application/vnd.google.draco",
            "draco", "synthetic-draco", ("drc-layer:rare", "version:draco-1.5.7"),
        ),
        (
            "dskimg", dskimg, "application/x-garmin-dskimg",
            "dskimg", "synthetic-dskimg", ("dskimg-cluster:synthetic-a", "holes:18"),
        ),
    )
    artifacts: list[CorpusArtifact] = []

    def signature(name: str, body: bytes) -> tuple[str, str]:
        if name == "protobuf": return "protobuf-wire", ""
        if name == "json":
            first = body.lstrip()[:1]
            return ("json-object" if first == b"{" else "json-array", first.hex())
        if name == "archive": return "zip", ""
        if name == "texture": return "gif", body[:6].hex()
        if name == "draco": return "draco", body[:5].hex()
        if name == "dskimg": return "dskimg", body[:22].hex()
        raise ValueError(f"unclassified fixture format {name}")

    for name, body, media_type, source_type, schema_family, strata in bodies:
        ref = cas.put_bytes(storage_domain_id, "raw-entity", body)
        format_family, magic_prefix_hex = signature(name, body)
        artifacts.append(CorpusArtifact(
            source_manifest_id=f"synthetic-manifest-{name}",
            cas_ref=ref,
            media_type=media_type,
            source_type=source_type,
            format_family=format_family,
            magic_prefix_hex=magic_prefix_hex,
            schema_family=schema_family,
            schema_version="1",
            strata=strata,
        ))
    return FrozenCorpusManifest.create(decoder_set_id, artifacts)
```

```python
# tests/test_deep_mine_replay.py
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.course_data.cas import EncryptedCAS, StaticDomainKeyProvider
from ai_caddie.research.deep_mine.corpus import CorpusArtifact, FrozenCorpusManifest
from ai_caddie.research.deep_mine.parser_registry import ParserSelectionKey
from ai_caddie.research.deep_mine.cli import main as cli_main
from ai_caddie.research.deep_mine.parsers.gmp_descriptors import GmpVariantDescriptorRegistry
from ai_caddie.research.deep_mine.runner import DeepMineRunner, decoder_bundle_id, default_parser_registry, parser_registry_for_corpus
from tests.deep_mine_fixture_builders import build_full_format_corpus


GOLDEN = Path("tests/fixtures/deep_mine_replay_v1.sha256")
FIXED_TIME = "2026-07-18T10:00:00.000Z"
KEY = b"a" * 32


def run_fixture(root: Path):
    registry = default_parser_registry()
    gmp_descriptors = GmpVariantDescriptorRegistry.from_path(
        Path("tests/fixtures/research/synthetic_gmp_variant_descriptor.json")
    )
    build_hash = "synthetic-replay-build-v1"
    cas = EncryptedCAS(root, StaticDomainKeyProvider({"test-fixture": KEY}))
    corpus = build_full_format_corpus(
        cas=cas,
        storage_domain_id="test-fixture",
        decoder_set_id=decoder_bundle_id(registry, gmp_descriptors, build_hash),
    )
    runner = DeepMineRunner(
        cas=cas,
        storage_domain_id="test-fixture",
        registry=registry,
        observed_at=FIXED_TIME,
        build_hash=build_hash,
        gmp_descriptors=gmp_descriptors,
        golden_results={"checked-in-replay": True, "six-format-fixtures": True},
    )
    return runner.run(corpus), corpus


class DeepMineReplayTests(unittest.TestCase):
    def test_production_registry_uses_observed_format_family_and_magic_for_png_and_json_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cas = EncryptedCAS(Path(tmp), StaticDomainKeyProvider({"test-fixture": KEY}))
            output = BytesIO(); Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(output, format="PNG")
            png = output.getvalue(); array_json = b"[1,2,3]"
            artifacts = (
                CorpusArtifact("manifest-png", cas.put_bytes("test-fixture", "raw-entity", png), "image/png", "texture", "png", png[:8].hex(), "garmin-texture", "1", ("format:png",)),
                CorpusArtifact("manifest-json", cas.put_bytes("test-fixture", "raw-entity", array_json), "application/json", "hole-json", "json-array", "5b", "garmin-hole-json", "1", ("shape:array",)),
            )
            corpus = FrozenCorpusManifest.create("bundle-not-used-for-selection", artifacts)
            registry = parser_registry_for_corpus(corpus)
            png_selected = registry.select(ParserSelectionKey("garmin", "texture", "png", png[:32], "image/png", "garmin-texture", 1))
            json_selected = registry.select(ParserSelectionKey("garmin", "hole-json", "json-array", array_json, "application/json", "garmin-hole-json", 1))
            self.assertEqual(png_selected.descriptor.decoder_id, "pillow-image")
            self.assertEqual(png_selected.descriptor.magic_prefix, png[:8])
            self.assertEqual(json_selected.descriptor.decoder_id, "json-occurrence")

    def test_all_six_formats_close_register_unknowns_match_golden_and_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first, first_corpus = run_fixture(Path(first_tmp))
            second, second_corpus = run_fixture(Path(second_tmp))
        self.assertEqual(first_corpus.corpus_id, second_corpus.corpus_id)
        self.assertEqual(
            {row.source_type for row in first.report.artifacts},
            {"course-layout-release", "hole-json", "prodgeometry-archive", "texture", "draco", "dskimg"},
        )
        self.assertTrue(all(proof.complete for proof in first.closure_proofs))
        self.assertEqual(
            first.coverage.byte_accounting.classified_bytes,
            first.coverage.byte_accounting.total_bytes,
        )
        self.assertGreater(len(first.unknown_records), 0)
        self.assertGreater(len(first.fingerprints), len(first_corpus.artifacts))
        self.assertEqual(first.coverage.golden.passed, ("checked-in-replay", "six-format-fixtures"))
        self.assertEqual(first.report.report_hash, second.report.report_hash)
        self.assertEqual(
            tuple(record.canonical() for record in first.unknown_records),
            tuple(record.canonical() for record in second.unknown_records),
        )
        self.assertEqual(first.report.report_hash, GOLDEN.read_text().strip())

    def test_cli_replays_offline_from_corpus_json_and_verifies_the_golden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outcome, corpus = run_fixture(root / "cas")
            corpus_path = root / "corpus.json"
            report_path = root / "report.json"
            corpus_path.write_bytes(canonical_json_bytes(corpus.canonical()))
            code = cli_main(
                [
                    "--cas-root", str(root / "cas"),
                    "--storage-domain-id", "test-fixture",
                    "--corpus", str(corpus_path),
                    "--gmp-descriptors", "tests/fixtures/research/synthetic_gmp_variant_descriptor.json",
                    "--observed-at", FIXED_TIME,
                    "--build-hash", "synthetic-replay-build-v1",
                    "--golden", str(GOLDEN),
                    "--report", str(report_path),
                ],
                environ={"AI_CADDIE_DEEP_MINE_KEY_HEX": KEY.hex()},
            )
            self.assertEqual(code, 0)
            self.assertEqual(outcome.report.report_hash, GOLDEN.read_text().strip())
            report_bytes = report_path.read_bytes()
            self.assertIn(outcome.report.report_hash.encode(), report_bytes)
            self.assertNotIn(b'{"a":1.2300', report_bytes)
            self.assertNotIn(b"\x08\x01\x12\x03new", report_bytes)
            wrong_golden = root / "wrong.sha256"
            wrong_golden.write_text("0" * 64 + "\n")
            with self.assertRaisesRegex(ValueError, "replay golden mismatch"):
                cli_main(
                    [
                        "--cas-root", str(root / "cas"),
                        "--storage-domain-id", "test-fixture",
                        "--corpus", str(corpus_path),
                        "--gmp-descriptors", "tests/fixtures/research/synthetic_gmp_variant_descriptor.json",
                        "--observed-at", FIXED_TIME,
                        "--build-hash", "synthetic-replay-build-v1",
                        "--golden", str(wrong_golden),
                        "--report", str(root / "must-not-be-written.json"),
                    ],
                    environ={"AI_CADDIE_DEEP_MINE_KEY_HEX": KEY.hex()},
                )
            self.assertFalse((root / "must-not-be-written.json").exists())


def write_golden() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        outcome, _corpus = run_fixture(Path(tmp))
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(outcome.report.report_hash + "\n")
    print(f"deep-mine-golden:{outcome.report.report_hash}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-golden"]:
        write_golden()
    else:
        unittest.main()
```

- [ ] **Step 2: Install the hermetic Draco dependency and verify replay is absent**

Run:

```bash
npm ci --omit=dev
uv run python -m unittest tests.test_deep_mine_replay -v
```

Expected: FAIL importing `ai_caddie.research.deep_mine.runner`; the checked-in golden is created only after the replay implementation exists and its report is inspected.

- [ ] **Step 3: Implement the default six-format parser registry and decoder adapters**

```python
# ai_caddie/research/deep_mine/runner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.course_data.cas import CASRef, EncryptedCAS

from .corpus import CorpusArtifact, FrozenCorpusManifest
from .coverage import CoverageReport, build_coverage, persist_coverage
from .diff import register_first_seen_fingerprint
from .fingerprint import ArtifactFingerprint, build_fingerprint, persist_fingerprint
from .ledger import ClosureProof, NodeLedger
from .models import ByteDomain, NodeRecord
from .parser_registry import ParserDescriptor, ParserRegistry, ParserSelectionKey
from .parsers.archive import inventory_zip
from .parsers.draco import inventory_draco
from .parsers.dskimg import inventory_dskimg
from .parsers.gmp_descriptors import GmpVariantDescriptorRegistry
from .parsers.json_occurrence import inventory_json
from .parsers.protobuf import inventory_protobuf
from .parsers.texture import inventory_texture
from .playable_regions import (
    PlayableRegionsProjector,
    project_playable_regions_from_decoded_source,
)
from .promotion import TrustedPromotionCandidateStore
from .provenance import DerivedArtifact, persist_lossless_ir, put_derived
from .unknowns import UnknownRecord, UnknownRegistry


@dataclass(frozen=True)
class ReplayDecodeInput:
    artifact: CorpusArtifact
    data: bytes
    domain: ByteDomain
    root: NodeRecord
    ledger: NodeLedger
    unknowns: UnknownRegistry
    cas: EncryptedCAS
    storage_domain_id: str
    observed_at: str
    descriptor: ParserDescriptor
    gmp_descriptors: GmpVariantDescriptorRegistry


def decoder_bundle_id(
    registry: ParserRegistry,
    gmp_descriptors: GmpVariantDescriptorRegistry,
    build_hash: str,
) -> str:
    return typed_id("DeepMineDecoderBundle/v1", {
        "parserRegistryId": registry.decoder_set_id,
        "gmpDescriptorRegistryId": gmp_descriptors.registry_id,
        "buildHash": build_hash,
    })


def _protobuf(context: ReplayDecodeInput):
    return inventory_protobuf(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, observed_at=context.observed_at,
        schema_name=context.artifact.schema_family, known_fields={1},
        decoder_id=context.descriptor.decoder_id, decoder_version=context.descriptor.decoder_version,
    )


def _json(context: ReplayDecodeInput):
    return inventory_json(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, observed_at=context.observed_at,
        schema_name=context.artifact.schema_family, known_paths=set(),
        decoder_id=context.descriptor.decoder_id, decoder_version=context.descriptor.decoder_version,
    )


def _archive(context: ReplayDecodeInput):
    return inventory_zip(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, cas=context.cas, storage_domain_id=context.storage_domain_id,
        observed_at=context.observed_at, decoder_id=context.descriptor.decoder_id,
        decoder_version=context.descriptor.decoder_version, build_hash=context.descriptor.build_hash,
        max_member_bytes=64 * 1024 * 1024, max_total_uncompressed=256 * 1024 * 1024,
    )


def _texture(context: ReplayDecodeInput):
    return inventory_texture(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, cas=context.cas, storage_domain_id=context.storage_domain_id,
        observed_at=context.observed_at, decoder_id=context.descriptor.decoder_id,
        decoder_version=context.descriptor.decoder_version, build_hash=context.descriptor.build_hash,
    )


def _draco(context: ReplayDecodeInput):
    return inventory_draco(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, cas=context.cas, storage_domain_id=context.storage_domain_id,
        observed_at=context.observed_at, decoder_version=context.descriptor.decoder_version,
        build_hash=context.descriptor.build_hash,
    )


def _dskimg(context: ReplayDecodeInput):
    return inventory_dskimg(
        data=context.data, domain=context.domain, root=context.root, ledger=context.ledger,
        unknowns=context.unknowns, cas=context.cas, storage_domain_id=context.storage_domain_id,
        observed_at=context.observed_at, decoder_id=context.descriptor.decoder_id,
        decoder_version=context.descriptor.decoder_version, build_hash=context.descriptor.build_hash,
        descriptors=context.gmp_descriptors,
    )


def _descriptor(
    *,
    decoder_id: str,
    decoder_version: str,
    build_hash: str,
    source_type: str,
    format_family: str,
    magic_prefix: bytes,
    media_type: str,
    schema_family: str,
    schema_version: int = 1,
) -> ParserDescriptor:
    return ParserDescriptor(
        decoder_id, decoder_version, build_hash, "garmin", source_type, (format_family,), magic_prefix,
        (media_type,), schema_family, schema_version, schema_version, "DeepMineLosslessIR/v1",
    )


def default_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    rows: tuple[tuple[ParserDescriptor, Callable[[ReplayDecodeInput], object]], ...] = (
        (_descriptor(
            decoder_id="protobuf-inventory", decoder_version="wire-v1", build_hash="protobuf-wire-build-v1",
            source_type="course-layout-release", format_family="protobuf-wire", magic_prefix=b"", media_type="application/x-protobuf",
            schema_family="synthetic-protobuf",
        ), _protobuf),
        (_descriptor(
            decoder_id="json-occurrence", decoder_version="json-v1", build_hash="json-occurrence-build-v1",
            source_type="hole-json", format_family="json-object", magic_prefix=b"{", media_type="application/json",
            schema_family="synthetic-json",
        ), _json),
        (_descriptor(
            decoder_id="zip-inventory", decoder_version="zip-v1", build_hash="zip-inventory-build-v1",
            source_type="prodgeometry-archive", format_family="zip", magic_prefix=b"GAP", media_type="application/zip",
            schema_family="synthetic-archive",
        ), _archive),
        (_descriptor(
            decoder_id="pillow-image", decoder_version="pillow-12.2.0", build_hash="pillow-build-v1",
            source_type="texture", format_family="gif", magic_prefix=b"GIF89a", media_type="image/gif",
            schema_family="synthetic-texture",
        ), _texture),
        (_descriptor(
            decoder_id="draco3d", decoder_version="draco3d-1.5.7", build_hash="draco-build-v1",
            source_type="draco", format_family="draco", magic_prefix=b"DRACO", media_type="application/vnd.google.draco",
            schema_family="synthetic-draco",
        ), _draco),
        (_descriptor(
            decoder_id="dskimg-inventory", decoder_version="dskimg-v1", build_hash="dskimg-build-v1",
            source_type="dskimg", format_family="dskimg", magic_prefix=b"\x00" * 16 + b"DSKIMG", media_type="application/x-garmin-dskimg",
            schema_family="synthetic-dskimg",
        ), _dskimg),
    )
    for descriptor, decoder in rows:
        registry.register(descriptor, decoder)
    return registry
```

- [ ] **Step 4: Implement deterministic replay, all-domain closure, fingerprints, unknowns, coverage, and report persistence**

Append to `ai_caddie/research/deep_mine/runner.py`:

```python
@dataclass(frozen=True)
class ReplayArtifactResult:
    artifact_id: str
    source_manifest_id: str
    source_type: str
    byte_domain_id: str
    root_node_id: str
    decoder_id: str
    decoder_version: str
    lossless_ir_artifact_id: str
    fingerprint_id: str
    fingerprint_artifact_id: str
    error: str | None

    def canonical(self) -> dict[str, object]:
        return {
            "artifactId": self.artifact_id,
            "sourceManifestId": self.source_manifest_id,
            "sourceType": self.source_type,
            "byteDomainId": self.byte_domain_id,
            "rootNodeId": self.root_node_id,
            "decoderId": self.decoder_id,
            "decoderVersion": self.decoder_version,
            "losslessIrArtifactId": self.lossless_ir_artifact_id,
            "fingerprintId": self.fingerprint_id,
            "fingerprintArtifactId": self.fingerprint_artifact_id,
            "error": self.error,
        }


def _proof_payload(proof: ClosureProof) -> dict[str, object]:
    return {
        "proofId": proof.proof_id,
        "byteDomainId": proof.byte_domain_id,
        "rootNodeId": proof.root_node_id,
        "domainSize": str(proof.domain_size),
        "classifiedBytes": str(proof.classified_bytes),
        "statusBytes": {key: str(value) for key, value in sorted(proof.status_bytes.items())},
        "complete": proof.complete,
    }


@dataclass(frozen=True)
class ReplayReport:
    report_hash: str
    corpus_id: str
    corpus_merkle_root: str
    decoder_set_id: str
    parser_registry_id: str
    gmp_descriptor_registry_id: str
    build_hash: str
    artifacts: tuple[ReplayArtifactResult, ...]
    closure_proofs: tuple[ClosureProof, ...]
    fingerprints: tuple[ArtifactFingerprint, ...]
    unknown_records: tuple[UnknownRecord, ...]
    coverage: CoverageReport

    def payload(self) -> dict[str, object]:
        return {
            "corpusId": self.corpus_id,
            "corpusMerkleRoot": self.corpus_merkle_root,
            "decoderSetId": self.decoder_set_id,
            "parserRegistryId": self.parser_registry_id,
            "gmpDescriptorRegistryId": self.gmp_descriptor_registry_id,
            "buildHash": self.build_hash,
            "artifacts": [row.canonical() for row in self.artifacts],
            "closureProofs": [_proof_payload(proof) for proof in self.closure_proofs],
            "fingerprints": [row.canonical() for row in self.fingerprints],
            "unknownRecords": [row.canonical() for row in self.unknown_records],
            "coverage": self.coverage.canonical(),
        }

    def canonical(self) -> dict[str, object]:
        return {"reportHash": self.report_hash, **self.payload()}


@dataclass(frozen=True)
class ReplayOutcome:
    report: ReplayReport
    closure_proofs: tuple[ClosureProof, ...]
    fingerprints: tuple[ArtifactFingerprint, ...]
    unknown_records: tuple[UnknownRecord, ...]
    coverage: CoverageReport
    lossless_ir_artifacts: tuple[DerivedArtifact, ...]
    fingerprint_artifacts: tuple[DerivedArtifact, ...]
    coverage_artifact: DerivedArtifact
    report_artifact: DerivedArtifact


def _domain_for(artifact: CorpusArtifact) -> ByteDomain:
    return ByteDomain.create(artifact.cas_ref, parent_domain_id=None, transform_id=None)


def _derived_artifacts(inventory: object) -> tuple[DerivedArtifact, ...]:
    rows: list[DerivedArtifact] = []
    rows.extend(getattr(inventory, "members", ()))
    rows.extend(getattr(inventory, "pixel_artifacts", ()))
    rows.extend(attribute.values_artifact for attribute in getattr(inventory, "attributes", ()))
    faces = getattr(inventory, "faces_artifact", None)
    if faces is not None:
        rows.append(faces)
    rows.extend(subfile.artifact for subfile in getattr(inventory, "subfiles", ()))
    unique = {artifact.artifact_id: artifact for artifact in rows}
    return tuple(sorted(unique.values(), key=lambda artifact: artifact.artifact_id))


class DeepMineRunner:
    def __init__(
        self,
        *,
        cas: EncryptedCAS,
        storage_domain_id: str,
        registry: ParserRegistry,
        observed_at: str,
        build_hash: str,
        gmp_descriptors: GmpVariantDescriptorRegistry,
        trusted_candidate_store: TrustedPromotionCandidateStore | None = None,
        playable_regions_projector: PlayableRegionsProjector | None = None,
        golden_results: Mapping[str, bool] | None = None,
    ) -> None:
        self.cas = cas
        self.storage_domain_id = storage_domain_id
        self.registry = registry
        self.observed_at = observed_at
        self.build_hash = build_hash
        self.gmp_descriptors = gmp_descriptors
        self.trusted_candidate_store = trusted_candidate_store
        self.playable_regions_projector = playable_regions_projector
        self.golden_results = dict(golden_results or {})

    def run(self, corpus: FrozenCorpusManifest) -> ReplayOutcome:
        expected_bundle_id = decoder_bundle_id(
            self.registry, self.gmp_descriptors, self.build_hash,
        )
        if corpus.decoder_set_id != expected_bundle_id:
            raise ValueError("frozen corpus decoder bundle does not match parser, GMP descriptor, and build identities")
        ledger = NodeLedger()
        unknowns = UnknownRegistry()
        artifact_results: list[ReplayArtifactResult] = []
        lossless_ir_artifacts: list[DerivedArtifact] = []
        fingerprints: list[ArtifactFingerprint] = []
        fingerprint_artifacts: list[DerivedArtifact] = []
        source_inventory_artifacts: list[DerivedArtifact] = []
        source_inventory_provenance_refs: list[CASRef] = []
        acquired: set[str] = set()

        for artifact in corpus.artifacts:
            data = corpus.read_artifact(self.cas, self.storage_domain_id, artifact)
            acquired.add(artifact.artifact_id)
            domain = _domain_for(artifact)
            ledger.add_domain(domain)
            root = NodeRecord.root(domain.domain_id, domain.size, f"artifact:{artifact.source_type}")
            ledger.add_node(root)
            try:
                version = int(artifact.schema_version)
            except ValueError as exc:
                raise ValueError(f"schema version must be an integer for {artifact.artifact_id}") from exc
            selected = self.registry.select(ParserSelectionKey(
                "garmin",
                artifact.source_type,
                artifact.format_family,
                data[:32],
                artifact.media_type,
                artifact.schema_family,
                version,
            ))
            context = ReplayDecodeInput(
                artifact,
                data,
                domain,
                root,
                ledger,
                unknowns,
                self.cas,
                self.storage_domain_id,
                self.observed_at,
                selected.descriptor,
                self.gmp_descriptors,
            )
            inventory = selected.decoder(context)
            decoded_playable_source = getattr(
                inventory, "decoded_playable_region_source", None,
            )
            if decoded_playable_source is not None:
                if (
                    self.trusted_candidate_store is None
                    or self.playable_regions_projector is None
                ):
                    raise ValueError(
                        "decoded playable regions require the trusted freeze/project composition root"
                    )
                frozen_inventory, _projected = (
                    project_playable_regions_from_decoded_source(
                        decoded_playable_source,
                        cas=self.cas,
                        trusted_candidate_store=self.trusted_candidate_store,
                        storage_domain_id=self.storage_domain_id,
                        projector=self.playable_regions_projector,
                    )
                )
                source_inventory_artifacts.append(frozen_inventory.artifact)
                source_inventory_provenance_refs.append(
                    frozen_inventory.provenance_ref,
                )
            ir_artifact = persist_lossless_ir(
                getattr(inventory, "ir"),
                cas=self.cas,
                storage_domain_id=self.storage_domain_id,
                parent_refs=(artifact.cas_ref,),
                decoder_version=selected.descriptor.decoder_version,
                build_hash=self.build_hash,
            )
            lossless_ir_artifacts.append(ir_artifact)
            structural_tokens = tuple(getattr(inventory, "structural_tokens"))
            numeric_values = tuple(getattr(inventory, "numeric_values"))
            fingerprint = build_fingerprint(
                artifact_id=artifact.artifact_id,
                schema_family=artifact.schema_family,
                domain=domain,
                data=data,
                structural_tokens=structural_tokens,
                numeric_series={
                    f"{artifact.source_type}/numeric/{index}": (value,)
                    for index, value in enumerate(numeric_values)
                },
            )
            register_first_seen_fingerprint(
                fingerprint,
                evidence_domain=domain,
                unknowns=unknowns,
                observed_at=self.observed_at,
            )
            fingerprint_artifact = persist_fingerprint(
                fingerprint,
                cas=self.cas,
                storage_domain_id=self.storage_domain_id,
                parent_ref=artifact.cas_ref,
                decoder_version="fingerprint-v1",
                build_hash=self.build_hash,
            )
            fingerprints.append(fingerprint)
            fingerprint_artifacts.append(fingerprint_artifact)
            for derived in _derived_artifacts(inventory):
                matching_domains = [
                    item for item in ledger.domains.values() if item.transform_id == derived.artifact_id
                ]
                if len(matching_domains) != 1:
                    raise ValueError(
                        f"derived artifact {derived.artifact_id} requires exactly one ByteDomain"
                    )
                derived_domain = matching_domains[0]
                derived_data = self.cas.read_bytes(self.storage_domain_id, derived.ref)
                derived_roots = [
                    node for node in ledger.nodes.values()
                    if node.byte_domain_id == derived_domain.domain_id and node.parent_node_id is None
                ]
                if len(derived_roots) != 1:
                    raise ValueError(
                        f"derived ByteDomain {derived_domain.domain_id} requires exactly one root"
                    )
                derived_tokens = tuple(
                    f"{node.node_kind}/{node.status.value}"
                    for node in ledger.direct_accounting_children(derived_roots[0].node_id)
                )
                derived_fingerprint = build_fingerprint(
                    artifact_id=derived.artifact_id,
                    schema_family=f"{artifact.schema_family}/derived/{derived.ref.byte_domain}",
                    domain=derived_domain,
                    data=derived_data,
                    structural_tokens=derived_tokens,
                    numeric_series={},
                )
                register_first_seen_fingerprint(
                    derived_fingerprint,
                    evidence_domain=derived_domain,
                    unknowns=unknowns,
                    observed_at=self.observed_at,
                )
                derived_fingerprint_artifact = persist_fingerprint(
                    derived_fingerprint,
                    cas=self.cas,
                    storage_domain_id=self.storage_domain_id,
                    parent_ref=derived.ref,
                    decoder_version="fingerprint-v1",
                    build_hash=self.build_hash,
                )
                fingerprints.append(derived_fingerprint)
                fingerprint_artifacts.append(derived_fingerprint_artifact)
            artifact_results.append(ReplayArtifactResult(
                artifact.artifact_id,
                artifact.source_manifest_id,
                artifact.source_type,
                domain.domain_id,
                root.node_id,
                selected.descriptor.decoder_id,
                selected.descriptor.decoder_version,
                ir_artifact.artifact_id,
                fingerprint.fingerprint_id,
                fingerprint_artifact.artifact_id,
                getattr(inventory, "error"),
            ))

        root_node_ids: dict[str, str] = {}
        for domain_id in sorted(ledger.domains):
            roots = sorted(
                (node.node_id for node in ledger.nodes.values() if node.byte_domain_id == domain_id and node.parent_node_id is None),
            )
            if len(roots) != 1:
                raise ValueError(f"ByteDomain {domain_id} requires exactly one root node")
            root_node_ids[domain_id] = roots[0]
        closure_proofs = tuple(
            ledger.prove_closure(domain_id, root_node_ids[domain_id]) for domain_id in sorted(root_node_ids)
        )
        fingerprint_rows = tuple(sorted(fingerprints, key=lambda row: row.fingerprint_id))
        unknown_rows = unknowns.records()
        coverage = build_coverage(
            corpus=corpus,
            acquired_artifact_ids=acquired,
            ledger=ledger,
            root_node_ids=root_node_ids,
            unknowns=unknowns,
            fingerprints=fingerprint_rows,
            golden_results=self.golden_results,
        )
        parent_refs = tuple(artifact.cas_ref for artifact in corpus.artifacts)
        coverage_artifact = persist_coverage(
            coverage,
            cas=self.cas,
            storage_domain_id=self.storage_domain_id,
            parent_refs=parent_refs,
            decoder_version="coverage-v1",
            build_hash=self.build_hash,
        )
        provisional = ReplayReport(
            "",
            corpus.corpus_id,
            corpus.merkle_root,
            corpus.decoder_set_id,
            self.registry.decoder_set_id,
            self.gmp_descriptors.registry_id,
            self.build_hash,
            tuple(sorted(artifact_results, key=lambda row: row.artifact_id)),
            closure_proofs,
            fingerprint_rows,
            unknown_rows,
            coverage,
        )
        report_hash = typed_id("DeepMineReplayReport/v1", provisional.payload())
        report = ReplayReport(
            report_hash,
            provisional.corpus_id,
            provisional.corpus_merkle_root,
            provisional.decoder_set_id,
            provisional.parser_registry_id,
            provisional.gmp_descriptor_registry_id,
            provisional.build_hash,
            provisional.artifacts,
            provisional.closure_proofs,
            provisional.fingerprints,
            provisional.unknown_records,
            provisional.coverage,
        )
        report_parent_refs = (
            coverage_artifact.ref,
            *(artifact.ref for artifact in sorted(lossless_ir_artifacts, key=lambda item: item.artifact_id)),
            *(artifact.ref for artifact in sorted(fingerprint_artifacts, key=lambda item: item.artifact_id)),
            *(artifact.ref for artifact in sorted(source_inventory_artifacts, key=lambda item: item.artifact_id)),
            *sorted(source_inventory_provenance_refs, key=lambda ref: (
                ref.storage_domain_id, ref.byte_domain, ref.sha256, ref.size,
            )),
        )
        report_artifact = put_derived(
            cas=self.cas,
            storage_domain_id=self.storage_domain_id,
            byte_domain="deep-mine-replay-report",
            data=canonical_json_bytes(report.canonical()),
            parent_refs=report_parent_refs,
            transform_name="deep-mine-replay",
            transform_version="replay-v1",
            parameters={
                "reportHash": report.report_hash,
                "corpusId": corpus.corpus_id,
                "decoderSetId": corpus.decoder_set_id,
            },
            build_hash=self.build_hash,
        )
        return ReplayOutcome(
            report,
            closure_proofs,
            fingerprint_rows,
            unknown_rows,
            coverage,
            tuple(sorted(lossless_ir_artifacts, key=lambda artifact: artifact.artifact_id)),
            tuple(sorted(fingerprint_artifacts, key=lambda artifact: artifact.artifact_id)),
            coverage_artifact,
            report_artifact,
        )
```

The runner intentionally requires an exact decoder-set match and a caller-supplied timestamp. It does not read wall-clock time, network state, release channels, or product snapshot modules.

- [ ] **Step 5: Build an exact registry from a frozen manifest and add the offline CLI**

Append to `ai_caddie/research/deep_mine/runner.py`:

```python
_FORMAT_CONFIG: dict[tuple[str, str], tuple[str, str, str, Callable[[ReplayDecodeInput], object]]] = {
    ("course-layout-release", "protobuf-wire"): ("protobuf-inventory", "wire-v1", "protobuf-wire-build-v1", _protobuf),
    ("hole-json", "json-object"): ("json-occurrence", "json-v1", "json-occurrence-build-v1", _json),
    ("hole-json", "json-array"): ("json-occurrence", "json-v1", "json-occurrence-build-v1", _json),
    ("prodgeometry-archive", "zip"): ("zip-inventory", "zip-v1", "zip-inventory-build-v1", _archive),
    ("texture", "gif"): ("pillow-image", "pillow-12.2.0", "pillow-build-v1", _texture),
    ("texture", "png"): ("pillow-image", "pillow-12.2.0", "pillow-build-v1", _texture),
    ("texture", "jpeg"): ("pillow-image", "pillow-12.2.0", "pillow-build-v1", _texture),
    ("texture", "webp"): ("pillow-image", "pillow-12.2.0", "pillow-build-v1", _texture),
    ("texture", "dds"): ("pillow-image", "pillow-12.2.0", "pillow-build-v1", _texture),
    ("draco", "draco"): ("draco3d", "draco3d-1.5.7", "draco-build-v1", _draco),
    ("dskimg", "dskimg"): ("dskimg-inventory", "dskimg-v1", "dskimg-build-v1", _dskimg),
}


def parser_registry_for_corpus(corpus: FrozenCorpusManifest) -> ParserRegistry:
    registry = ParserRegistry()
    registered: set[tuple[str, str, str, str, str, int]] = set()
    for artifact in corpus.artifacts:
        try:
            decoder_id, decoder_version, build_hash, decoder = _FORMAT_CONFIG[
                (artifact.source_type, artifact.format_family)
            ]
        except KeyError as exc:
            raise LookupError(
                f"unsupported frozen-corpus format: {artifact.source_type}/{artifact.format_family}"
            ) from exc
        try:
            schema_version = int(artifact.schema_version)
        except ValueError as exc:
            raise ValueError(f"schema version must be an integer for {artifact.artifact_id}") from exc
        key = (
            artifact.source_type, artifact.format_family, artifact.magic_prefix_hex,
            artifact.media_type, artifact.schema_family, schema_version,
        )
        if key in registered:
            continue
        registered.add(key)
        registry.register(
            _descriptor(
                decoder_id=decoder_id,
                decoder_version=decoder_version,
                build_hash=build_hash,
                source_type=artifact.source_type,
                format_family=artifact.format_family,
                magic_prefix=bytes.fromhex(artifact.magic_prefix_hex),
                media_type=artifact.media_type,
                schema_family=artifact.schema_family,
                schema_version=schema_version,
            ),
            decoder,
        )
    return registry
```

`default_parser_registry()` is the checked-in six-format synthetic profile. `parser_registry_for_corpus()` creates the same exact descriptors for that fixture and exact schema-family/version descriptors for an authorized real manifest; replay still rejects the manifest if its frozen `decoderSetId` was produced by different decoder builds.

```python
# ai_caddie/research/deep_mine/cli.py
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Mapping, Sequence

from ai_caddie.contracts.canonical_json import canonical_json_bytes
from ai_caddie.course_data.cas import CASRef, EncryptedCAS, StaticDomainKeyProvider

from .corpus import CorpusArtifact, FrozenCorpusManifest
from .runner import DeepMineRunner, decoder_bundle_id, parser_registry_for_corpus


def load_corpus(path: Path) -> FrozenCorpusManifest:
    def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, child in rows:
            if key in value:
                raise ValueError(f"duplicate corpus JSON key: {key}")
            value[key] = child
        return value

    payload = json.loads(path.read_bytes(), object_pairs_hook=pairs)
    if not isinstance(payload, dict) or set(payload) != {
        "corpusId", "merkleRoot", "decoderSetId", "artifacts",
    }:
        raise ValueError("corpus JSON top-level shape is invalid")
    if not isinstance(payload["artifacts"], list) or not payload["artifacts"]:
        raise ValueError("corpus JSON requires a nonempty artifact array")
    artifacts: list[CorpusArtifact] = []
    for row in payload["artifacts"]:
        if not isinstance(row, dict) or set(row) != {
            "sourceManifestId", "casRef", "mediaType", "sourceType",
            "formatFamily", "magicPrefixHex", "schemaFamily", "schemaVersion", "strata",
        }:
            raise ValueError("corpus artifact shape is invalid")
        ref = row["casRef"]
        if not isinstance(ref, dict) or set(ref) != {
            "storageDomainId", "byteDomain", "sha256", "size",
        }:
            raise ValueError("corpus artifact CAS ref shape is invalid")
        if not isinstance(row["strata"], list) or row["strata"] != sorted(set(row["strata"])):
            raise ValueError("corpus artifact strata are not canonical")
        artifacts.append(CorpusArtifact(
            source_manifest_id=row["sourceManifestId"],
            cas_ref=CASRef(
                ref["storageDomainId"],
                ref["byteDomain"],
                ref["sha256"],
                int(ref["size"]),
            ),
            media_type=row["mediaType"],
            source_type=row["sourceType"],
            format_family=row["formatFamily"],
            magic_prefix_hex=row["magicPrefixHex"],
            schema_family=row["schemaFamily"],
            schema_version=row["schemaVersion"],
            strata=tuple(row["strata"]),
        ))
    corpus = FrozenCorpusManifest.create(payload["decoderSetId"], artifacts)
    if corpus.corpus_id != payload["corpusId"] or corpus.merkle_root != payload["merkleRoot"]:
        raise ValueError("corpus JSON identity or Merkle root mismatch")
    if canonical_json_bytes(payload) != path.read_bytes():
        raise ValueError("corpus JSON bytes are not canonical")
    return corpus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay an authorized frozen Deep Mine corpus offline")
    parser.add_argument("--cas-root", type=Path, required=True)
    parser.add_argument("--storage-domain-id", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--gmp-descriptors", type=Path, required=True)
    parser.add_argument("--observed-at", required=True, help="fixed RFC3339 timestamp; no wall-clock default")
    parser.add_argument("--build-hash", required=True)
    parser.add_argument("--golden", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env = dict(os.environ if environ is None else environ)
    key_hex = env.get("AI_CADDIE_DEEP_MINE_KEY_HEX", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", key_hex):
        raise ValueError("AI_CADDIE_DEEP_MINE_KEY_HEX must contain one 32-byte key")
    corpus = load_corpus(args.corpus)
    registry = parser_registry_for_corpus(corpus)
    gmp_descriptors = GmpVariantDescriptorRegistry.from_path(args.gmp_descriptors)
    if decoder_bundle_id(registry, gmp_descriptors, args.build_hash) != corpus.decoder_set_id:
        raise ValueError("corpus decoderSetId does not match parser/GMP/build bundle")
    cas = EncryptedCAS(
        args.cas_root,
        StaticDomainKeyProvider({args.storage_domain_id: bytes.fromhex(key_hex)}),
    )
    outcome = DeepMineRunner(
        cas=cas,
        storage_domain_id=args.storage_domain_id,
        registry=registry,
        observed_at=args.observed_at,
        build_hash=args.build_hash,
        gmp_descriptors=gmp_descriptors,
        golden_results={"checked-in-replay": args.golden is not None, "six-format-fixtures": True},
    ).run(corpus)
    if args.golden is not None:
        expected = args.golden.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("golden replay hash must be one lowercase sha256")
        if outcome.report.report_hash != expected:
            raise ValueError(
                f"replay golden mismatch: expected {expected}, got {outcome.report.report_hash}"
            )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(canonical_json_bytes(outcome.report.canonical()) + b"\n")
    print(f"deep-mine-report:{outcome.report.report_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Generate, inspect, freeze, and verify the replay golden**

Run:

```bash
uv run python tests/test_deep_mine_replay.py --write-golden
uv run python - <<'PY'
from pathlib import Path
import re
value = Path('tests/fixtures/deep_mine_replay_v1.sha256').read_text().strip()
assert re.fullmatch(r'[0-9a-f]{64}', value)
print(f'deep-mine-golden-shape: PASS ({value})')
PY
uv run python -m unittest tests.test_deep_mine_replay -v
```

Expected: the generator prints `deep-mine-golden:<64 lowercase hex characters>`, the shape guard prints `deep-mine-golden-shape: PASS (...)`, and both replay tests PASS. Review the generated report in the CLI test failure output or by invoking the CLI before accepting the fixture; the committed golden changes only when corpus bytes, decoder-set identity, closure, fingerprints, unknowns, or coverage intentionally change.

- [ ] **Step 7: Register replay reports and wire the root Node suite**

Verify C1's exact `DeepMineReplayReport/v1` entry. Its typed ID payload is exactly `ReplayReport.payload()`; `reportHash` is excluded from its own identity and added only to the persisted envelope.

Modify the root `package.json` scripts object to contain:

```json
{
  "decode:geometry": "node ai_caddie/geometry/decode_courseview_geometry.js",
  "fetch:geometry-key": "node ai_caddie/geometry/fetch_courseview_geometry_key.js",
  "test": "npm run test:deep-mine",
  "test:deep-mine": "node --test tests/node/deep_mine_draco_inventory.test.js",
  "test:deep-mine:draco": "node --test tests/node/deep_mine_draco_inventory.test.js"
}
```

Run:

```bash
npm ci --omit=dev
npm test
```

Expected: the root Node test command exits 0 and all Draco inventory tests PASS against the package-lock-pinned `draco3d` bunny fixture.

- [ ] **Step 8: Install root Node dependencies in backend CI before Python replay tests**

In `.github/workflows/ci.yml`, insert these backend steps immediately after `actions/checkout@v4` and before Python dependency installation:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: package-lock.json
      - name: Install root research decoder dependencies
        run: npm ci --omit=dev
      - name: Run Deep Mine Node inventory tests
        run: npm test
```

Keep the existing frontend job's `working-directory: web_v2` and its separate `web_v2/package-lock.json` cache unchanged.

Run a local equivalent:

```bash
npm ci --omit=dev
npm test
uv sync --frozen
uv run python -m unittest tests.test_deep_mine_replay tests.test_deep_mine_draco_bridge -v
```

Expected: root Node tests PASS, Python dependencies remain lockfile-clean, and both the real Node bridge and six-format deterministic replay tests PASS.

- [ ] **Step 9: Run the complete Track C and repository verification suite**

Run:

```bash
npm ci --omit=dev
npm test
uv run python -m unittest discover -s tests -v
uv run python -m ai_caddie.research.deep_mine.cli --help
uv run python - <<'PY'
from pathlib import Path
root = Path('ai_caddie/research/deep_mine')
for path in root.rglob('*'):
    if path.suffix not in {'.py', '.js'}:
        continue
    text = path.read_text()
    for forbidden in (
        'ai_caddie.course_data.snapshot_builder',
        'ai_caddie.course_data.channels',
        'tools.courseview.parse_courseview',
        'DumpMkgmapCourseView',
        'DumpCourseView',
        'CourseReleaseChannel',
        'qualityReportHash',
        'def publish(',
        'publish_snapshot(',
        'publish_channel(',
        'advance_channel(',
    ):
        assert forbidden not in text, f'{path}: {forbidden}'
print('deep-mine-boundaries: PASS')
PY
```

Expected: root Node tests PASS; the full Python suite PASSes; CLI help exits 0 without network access; the boundary guard prints `deep-mine-boundaries: PASS`; two fresh-CAS replays produce the checked-in golden hash, complete closure for every registered ByteDomain, identical Unknown Registry records, and identical multi-axis coverage.

- [ ] **Step 10: Commit C16**

```bash
git add tests/deep_mine_fixture_builders.py ai_caddie/research/deep_mine/runner.py ai_caddie/research/deep_mine/cli.py contracts/canonical/deep_mine_v1.schema.json contracts/canonical/canonical_object_registry.json tests/test_deep_mine_replay.py tests/fixtures/deep_mine_replay_v1.sha256 package.json .github/workflows/ci.yml
git commit -m "feat(research): replay frozen deep mine corpus deterministically"
```
