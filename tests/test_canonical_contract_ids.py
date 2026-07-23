from __future__ import annotations

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
from ai_caddie.contracts.canonical_objects import (
    GENERATED_CANONICAL_OBJECTS,
    CanonicalObjectDescriptor,
    CanonicalObjectError,
)
from ai_caddie.contracts.typed_ids import typed_id


JAVASCRIPT_MAX_SAFE_INTEGER = 9_007_199_254_740_991


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
    def test_accepts_all_json_value_types_nesting_and_safe_integer_boundaries(self) -> None:
        cases = (
            ("null", None, b"null"),
            ("true", True, b"true"),
            ("false", False, b"false"),
            ("zero", 0, b"0"),
            (
                "minimum safe integer",
                -JAVASCRIPT_MAX_SAFE_INTEGER,
                b"-9007199254740991",
            ),
            (
                "maximum safe integer",
                JAVASCRIPT_MAX_SAFE_INTEGER,
                b"9007199254740991",
            ),
            (
                "minimum safe integral float",
                float(-JAVASCRIPT_MAX_SAFE_INTEGER),
                b"-9007199254740991",
            ),
            (
                "maximum safe integral float",
                float(JAVASCRIPT_MAX_SAFE_INTEGER),
                b"9007199254740991",
            ),
            ("finite fraction", 1.5, b"1.5"),
            ("empty string", "", b'""'),
            ("NFC string", "\u00e9", b'"\xc3\xa9"'),
            ("empty array", [], b"[]"),
            ("empty object", {}, b"{}"),
            (
                "nested arrays and objects with NFC keys and values",
                {"z": [None, True, False, {"\u00e9": "\u00e9"}], "a": 0},
                b'{"a":0,"z":[null,true,false,{"\xc3\xa9":"\xc3\xa9"}]}',
            ),
        )

        for label, value, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(canonical_json_bytes(value), expected)

    def test_rejects_all_noncanonical_or_unsupported_python_values(self) -> None:
        cases = (
            (
                "positive unsafe integer",
                JAVASCRIPT_MAX_SAFE_INTEGER + 1,
                "safe range",
            ),
            (
                "negative unsafe integer",
                -JAVASCRIPT_MAX_SAFE_INTEGER - 1,
                "safe range",
            ),
            (
                "positive unsafe integral float",
                float(JAVASCRIPT_MAX_SAFE_INTEGER + 1),
                "safe integer",
            ),
            (
                "negative unsafe integral float",
                float(-JAVASCRIPT_MAX_SAFE_INTEGER - 1),
                "safe integer",
            ),
            ("NaN", float("nan"), "non-finite"),
            ("positive infinity", float("inf"), "non-finite"),
            ("negative infinity", float("-inf"), "non-finite"),
            ("negative zero", -0.0, "negative zero"),
            ("non-NFC value", "e\u0301", "NFC"),
            ("non-NFC key", {"e\u0301": "value"}, "NFC"),
            ("non-string key", {1: "value"}, "keys must be strings"),
            ("tuple", (), "unsupported canonical type: tuple"),
            ("set", set(), "unsupported canonical type: set"),
            ("bytes", b"value", "unsupported canonical type: bytes"),
        )

        for label, value, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(CanonicalJSONError, message):
                    canonical_json_bytes(value)

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

    def test_transport_parsers_reject_duplicate_object_keys(self) -> None:
        raw = Path("contracts/canonical/fixtures/canonical_json_duplicate_key.json").read_bytes()
        for parser in (parse_unique_json, parse_canonical_json):
            with self.subTest(parser=parser.__name__):
                with self.assertRaisesRegex(CanonicalJSONError, "duplicate object key: eventId"):
                    parser(raw)

    def test_transport_parsers_require_strict_utf8_bytes(self) -> None:
        raw = '"not utf8 transport"'.encode("utf-16")
        for parser in (parse_unique_json, parse_canonical_json):
            with self.subTest(parser=parser.__name__):
                with self.assertRaisesRegex(CanonicalJSONError, "UTF-8"):
                    parser(raw)

    def test_transport_parsers_normalize_malformed_json_syntax_errors(self) -> None:
        cases = (
            ("unclosed root array", b"[1,2"),
            ("missing nested object value", b'{"outer":{"value":}}'),
        )
        for label, raw in cases:
            for parser in (parse_unique_json, parse_canonical_json):
                with self.subTest(label=label, parser=parser.__name__):
                    try:
                        parser(raw)
                    except Exception as exc:
                        self.assertIsInstance(exc, CanonicalJSONError)
                    else:
                        self.fail("malformed JSON syntax was accepted")

    def test_transport_parsers_reject_non_finite_json_constants(self) -> None:
        for raw in (b"NaN", b"Infinity", b"-Infinity"):
            for parser in (parse_unique_json, parse_canonical_json):
                with self.subTest(raw=raw, parser=parser.__name__):
                    with self.assertRaisesRegex(CanonicalJSONError, "non-finite"):
                        parser(raw)

    def test_parser_rejects_integer_negative_zero_token(self) -> None:
        with self.assertRaisesRegex(CanonicalJSONError, "negative zero"):
            parse_canonical_json(b"-0")

    def test_unique_parser_defers_canonical_semantic_value_validation(self) -> None:
        cases = (
            ("integer negative zero", b'{"value":-0}', "negative zero"),
            (
                "unsafe integer",
                b'{"value":9007199254740992}',
                "safe range",
            ),
            (
                "unsafe integral float",
                b'{"value":9007199254740992.0}',
                "safe integer",
            ),
            ("non-NFC string", b'{"value":"e\\u0301"}', "NFC"),
        )

        for label, raw, message in cases:
            with self.subTest(label=label):
                try:
                    parsed = parse_unique_json(raw)
                except CanonicalJSONError as exc:
                    self.fail(f"transport parser rejected syntactically valid JSON: {exc}")
                for validator, value in (
                    (canonical_json_bytes, parsed),
                    (parse_canonical_json, raw),
                ):
                    with self.subTest(validator=validator.__name__):
                        with self.assertRaisesRegex(CanonicalJSONError, message):
                            validator(value)

        marker = parse_unique_json(b'{"value":-0}')["value"]
        self.assertIsInstance(marker, int)
        self.assertIsNot(type(marker), int)

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
        with patch("ai_caddie.contracts.typed_ids._typed_digest") as typed_digest:
            with self.assertRaisesRegex(CanonicalObjectError, "unregistered canonical domain"):
                typed_id("NotRegistered/v1", {"a": "same", "z": 1})
        typed_digest.assert_not_called()

    def test_schema_invalid_payload_fails_before_hashing(self) -> None:
        with patch("ai_caddie.contracts.typed_ids._typed_digest") as typed_digest:
            with self.assertRaisesRegex(CanonicalObjectError, "schema validation failed"):
                typed_id("CanonicalFixtureAlpha/v1", {"a": "same", "z": "one"})
        typed_digest.assert_not_called()

    def test_complete_schema_validation_precedes_wildcard_and_explicit_projection(self) -> None:
        descriptors = (
            (
                "wildcard",
                GENERATED_CANONICAL_OBJECTS.require_domain("CanonicalFixtureAlpha/v1"),
            ),
            (
                "explicit",
                CanonicalObjectDescriptor(
                    object_name="ExplicitCanonicalFixture",
                    domain_tag="ExplicitCanonicalFixture/v1",
                    schema_ref="contracts/canonical/canonical_fixture_v1.schema.json",
                    included_fields=("a", "z"),
                    excluded_fields=frozenset({"transportNote"}),
                ),
            ),
        )
        valid = {"a": "same", "z": 1, "transportNote": "delivery metadata"}
        invalid_excluded = {"a": "same", "z": 1, "transportNote": "x" * 129}

        for branch, descriptor in descriptors:
            with self.subTest(branch=branch, payload="valid excluded field"):
                self.assertEqual(
                    descriptor.validate_and_project(valid),
                    {"a": "same", "z": 1},
                )
            with self.subTest(branch=branch, payload="invalid excluded field"):
                with self.assertRaisesRegex(
                    CanonicalObjectError,
                    "schema validation failed.*transportNote",
                ):
                    descriptor.validate_and_project(invalid_excluded)

    def test_explicit_projection_rejects_schema_allowed_but_unclassified_fields(self) -> None:
        descriptor = CanonicalObjectDescriptor(
            object_name="ExplicitCanonicalFixture",
            domain_tag="ExplicitCanonicalFixture/v1",
            schema_ref="contracts/canonical/canonical_fixture_v1.schema.json",
            included_fields=("a", "z"),
            excluded_fields=frozenset(),
        )

        with self.assertRaisesRegex(
            CanonicalObjectError,
            "unclassified fields.*transportNote",
        ):
            descriptor.validate_and_project(
                {"a": "same", "z": 1, "transportNote": "schema allowed"}
            )

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
