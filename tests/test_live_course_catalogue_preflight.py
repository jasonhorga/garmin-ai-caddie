from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(".github/scripts/preflight_live_course_catalogue.py")
SPEC = importlib.util.spec_from_file_location("preflight_live_course_catalogue", SCRIPT)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class LiveCourseCataloguePreflightTests(unittest.TestCase):
    def test_accepts_sorted_nearby_contract(self) -> None:
        rows = preflight.validate_matches(
            {
                "schema": "ai-caddie-course-nearby-v1",
                "matches": [
                    {"globalId": 31793, "distanceKm": 0.2},
                    {"globalId": 31794, "distanceKm": 4.1},
                ],
            },
            schema="ai-caddie-course-nearby-v1",
            expected_global_id=31793,
            require_distance_order=True,
        )
        self.assertEqual(len(rows), 2)

    def test_rejects_mock_like_or_unsorted_nearby_contract(self) -> None:
        invalid_payloads = [
            {"schema": "wrong", "matches": []},
            {"schema": "ai-caddie-course-nearby-v1", "matches": "not-an-array"},
            {
                "schema": "ai-caddie-course-nearby-v1",
                "matches": [
                    {"globalId": 31794, "distanceKm": 4.1},
                    {"globalId": 31793, "distanceKm": 0.2},
                ],
            },
            {
                "schema": "ai-caddie-course-nearby-v1",
                "matches": [{"globalId": 31794, "distanceKm": None}],
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                preflight.validate_matches(
                    payload,
                    schema="ai-caddie-course-nearby-v1",
                    expected_global_id=31793,
                    require_distance_order=True,
                )

    def test_localized_name_gate_requires_native_cjk_name_for_expected_rows(self) -> None:
        payload = {
            "schema": "ai-caddie-course-nearby-v1",
            "matches": [
                {"globalId": 32842, "name": "北京黄港国际高尔夫俱乐部"},
                {"globalId": 31783, "name": "天安假日高尔夫俱乐部 ~ A"},
            ],
        }
        preflight.validate_localized_names(
            payload,
            schema="ai-caddie-course-nearby-v1",
            expected_names={32842: "北京黄港", 31783: "天安假日"},
        )
        for bad_name in (
            "Beijing Huanggang International Golf Club",
            "",
            "北京另一座球场",
        ):
            invalid = {**payload, "matches": [{"globalId": 32842, "name": bad_name}]}
            with self.subTest(bad_name=bad_name), self.assertRaises(ValueError):
                preflight.validate_localized_names(
                    invalid,
                    schema="ai-caddie-course-nearby-v1",
                    expected_names={32842: "北京黄港"},
                )

        with self.assertRaises(ValueError):
            preflight.validate_localized_names(
                payload,
                schema="ai-caddie-course-search-v1",
                expected_names={32842: "北京黄港"},
            )

    def test_localized_name_expectation_parser_rejects_ambiguous_input(self) -> None:
        self.assertEqual(
            preflight._parse_expected_names("32842=北京黄港;31783=天安假日"),
            {32842: "北京黄港", 31783: "天安假日"},
        )
        for raw in ("32842", "0=坏", "32842=甲;32842=乙", "bad=名称"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                preflight._parse_expected_names(raw)

    def test_empty_nearby_requires_a_real_zero_result_contract(self) -> None:
        preflight.validate_empty_nearby(
            {
                "schema": "ai-caddie-course-nearby-v1",
                "radiusKm": 50,
                "matches": [],
            }
        )
        invalid_payloads = [
            {"schema": "ai-caddie-course-nearby-v1", "radiusKm": 50, "matches": [{}]},
            {"schema": "wrong", "radiusKm": 50, "matches": []},
            {"schema": "ai-caddie-course-nearby-v1", "radiusKm": 200, "matches": []},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                preflight.validate_empty_nearby(payload)

    def test_health_requires_the_production_schema(self) -> None:
        preflight.validate_health({"schema": "ai-caddie-health-v2", "revision": "abc123"})
        with self.assertRaises(ValueError):
            preflight.validate_health({"status": "ok", "revision": "abc123"})
        with self.assertRaisesRegex(ValueError, "health revision is missing"):
            preflight.validate_health({"schema": "ai-caddie-health-v2"})

    def test_health_requires_the_expected_backend_revision(self) -> None:
        preflight.validate_health(
            {"schema": "ai-caddie-health-v2", "revision": "abc123"},
            expected_revision="abc123",
        )
        with self.assertRaisesRegex(ValueError, "backend revision mismatch"):
            preflight.validate_health(
                {"schema": "ai-caddie-health-v2", "revision": "old456"},
                expected_revision="abc123",
            )

    def test_revisions_are_explicit_independent_40_character_git_ids(self) -> None:
        app = "a" * 40
        backend = "b" * 40
        self.assertEqual(preflight.validate_revision(app, label="app revision"), app)
        self.assertEqual(preflight.validate_revision(backend, label="backend revision"), backend)
        self.assertNotEqual(app, backend)
        for value in (None, "", "github.sha", "0" * 39, "g" * 40):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preflight.validate_revision(value, label="backend revision")

    def test_main_fails_closed_when_revision_inputs_are_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_CADDIE_PREFLIGHT_BASE_URL": "https://example.invalid",
                "AI_CADDIE_PREFLIGHT_TOKEN": "redacted-test-token",
            },
            clear=False,
        ):
            os.environ.pop("AI_CADDIE_PREFLIGHT_APP_REVISION", None)
            os.environ.pop("AI_CADDIE_PREFLIGHT_EXPECTED_REVISION", None)
            with self.assertRaisesRegex(ValueError, "app revision"):
                preflight.main()


if __name__ == "__main__":
    unittest.main()
