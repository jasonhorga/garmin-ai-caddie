from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from ai_caddie.contracts.canonical_json import (
    CanonicalJSONError,
    canonical_json_bytes,
    parse_canonical_json,
)
from ai_caddie.contracts.canonical_objects import CanonicalObjectError
from ai_caddie.contracts.typed_ids import typed_id


class CanonicalContractIdTests(unittest.TestCase):
    def test_orders_keys_and_preserves_exact_utf8(self) -> None:
        self.assertEqual(
            canonical_json_bytes({"z": 1, "a": "球场"}),
            b'{"a":"\xe7\x90\x83\xe5\x9c\xba","z":1}',
        )

    def test_rejects_negative_zero_and_non_nfc(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json_bytes({"value": -0.0})
        with self.assertRaises(CanonicalJSONError):
            canonical_json_bytes({"name": "e\u0301"})

    def test_rejects_integral_float_outside_javascript_safe_integer(self) -> None:
        with self.assertRaisesRegex(CanonicalJSONError, "safe integer"):
            canonical_json_bytes({"value": 9_007_199_254_740_992.0})

    def test_strict_parser_rejects_duplicate_object_keys(self) -> None:
        raw = Path("contracts/canonical/fixtures/canonical_json_duplicate_key.json").read_bytes()
        with self.assertRaisesRegex(CanonicalJSONError, "duplicate object key: eventId"):
            parse_canonical_json(raw)

    def test_domain_tags_prevent_cross_type_collision(self) -> None:
        payload = {"a": "same", "z": 1}
        self.assertNotEqual(
            typed_id("CanonicalFixtureAlpha/v1", payload),
            typed_id("CanonicalFixtureBeta/v1", payload),
        )

    def test_unknown_domain_fails_before_hashing(self) -> None:
        with self.assertRaisesRegex(CanonicalObjectError, "unregistered canonical domain"):
            typed_id("NotRegistered/v1", {"a": "same", "z": 1})

    def test_schema_invalid_payload_fails_before_hashing(self) -> None:
        with self.assertRaisesRegex(CanonicalObjectError, "schema validation failed"):
            typed_id("CanonicalFixtureAlpha/v1", {"a": "same", "z": "one"})

    def test_excluded_transport_field_does_not_change_semantic_id(self) -> None:
        first = {"a": "same", "z": 1, "transportNote": "first delivery"}
        retry = {"a": "same", "z": 1, "transportNote": "retry delivery"}
        self.assertEqual(
            typed_id("CanonicalFixtureAlpha/v1", first),
            typed_id("CanonicalFixtureAlpha/v1", retry),
        )

    def test_checked_in_golden_bytes_and_ids_are_exact(self) -> None:
        fixture = json.loads(Path("contracts/canonical/fixtures/canonical_json_v1.json").read_text())
        canonical = canonical_json_bytes(fixture["canonicalValue"])
        self.assertEqual(canonical.hex(), fixture["canonicalUtf8Hex"])
        for domain, expected in fixture["typedIds"].items():
            self.assertEqual(typed_id(domain, fixture["value"]), expected)
