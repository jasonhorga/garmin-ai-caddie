from __future__ import annotations

import ast
import json
import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path
from unittest.mock import patch

import rfc8785

from ai_caddie.contracts.canonical_json import (
    CanonicalJSONError,
    canonical_json_bytes,
    parse_canonical_json,
    parse_unique_json,
)
from ai_caddie.contracts.canonical_objects import CanonicalObjectError
from ai_caddie.contracts.typed_ids import typed_id


class _StatefulCanonicalPayload(Mapping[str, object]):
    def __init__(self) -> None:
        self.reads: dict[str, int] = {}

    def __getitem__(self, key: str) -> object:
        self.reads[key] = self.reads.get(key, 0) + 1
        if key == "a":
            return "same"
        if key == "z":
            return 1 if self.reads[key] == 1 else -1
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(("a", "z"))

    def __len__(self) -> int:
        return 2


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

    def test_parser_requires_strict_utf8_bytes(self) -> None:
        with self.assertRaisesRegex(CanonicalJSONError, "UTF-8"):
            parse_canonical_json('"not utf8 transport"'.encode("utf-16"))

    def test_parser_rejects_integer_negative_zero_token(self) -> None:
        with self.assertRaisesRegex(CanonicalJSONError, "negative zero"):
            parse_canonical_json(b"-0")

    def test_unique_parser_preserves_integer_negative_zero_for_event_validation(self) -> None:
        try:
            parsed = parse_unique_json(b'{"value":-0}')
        except CanonicalJSONError as exc:
            self.fail(f"transport parser rejected syntactically valid JSON: {exc}")
        marker = parsed["value"]
        self.assertIsInstance(marker, int)
        self.assertIsNot(type(marker), int)
        with self.assertRaisesRegex(CanonicalJSONError, "negative zero"):
            canonical_json_bytes(marker)

    def test_rejects_lone_surrogates_in_values_and_keys(self) -> None:
        for value in ("\ud800", {"\udfff": "value"}):
            with self.subTest(value=ascii(value)):
                try:
                    canonical_json_bytes(value)
                except Exception as exc:
                    self.assertIsInstance(exc, CanonicalJSONError)
                    self.assertRegex(str(exc), "surrogate")
                else:
                    self.fail("lone surrogate was accepted")
        for raw in (b'"\\ud800"', b'{"\\udfff":"value"}'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(CanonicalJSONError, "surrogate"):
                    parse_canonical_json(raw)

    def test_wraps_rfc8785_canonicalization_failures(self) -> None:
        failure = rfc8785.CanonicalizationError("forced canonicalization failure")
        with patch("ai_caddie.contracts.canonical_json.rfc8785.dumps", side_effect=failure):
            try:
                canonical_json_bytes({"a": "valid", "z": 1})
            except Exception as exc:
                self.assertIsInstance(exc, CanonicalJSONError)
                self.assertRegex(str(exc), "forced canonicalization failure")
            else:
                self.fail("RFC8785 canonicalization failure was not raised")

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

    def test_stateful_mapping_is_snapshotted_once_for_validation_projection_and_hashing(self) -> None:
        payload = _StatefulCanonicalPayload()
        expected = typed_id("CanonicalFixtureAlpha/v1", {"a": "same", "z": 1})

        self.assertEqual(typed_id("CanonicalFixtureAlpha/v1", payload), expected)
        self.assertEqual(payload.reads, {"a": 1, "z": 1})

    def test_checked_in_golden_bytes_and_ids_are_exact(self) -> None:
        fixture = json.loads(Path("contracts/canonical/fixtures/canonical_json_v1.json").read_text())
        canonical = canonical_json_bytes(fixture["canonicalValue"])
        self.assertEqual(canonical.hex(), fixture["canonicalUtf8Hex"])
        for domain, expected in fixture["typedIds"].items():
            self.assertEqual(typed_id(domain, fixture["value"]), expected)
