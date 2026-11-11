"""Contract fixtures are valid and every native copy matches its source (test-plan 6.2).

The phone, the Watch and the server test against one fixture set. A fixture that
drifts from its schema, or a bundled Swift copy that drifts from its contract
source, would let the two ends pass against different data.
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.support.hermetic import SmallTestCase

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FIXTURE_DIR = ROOT / "mobile" / "contracts" / "fixtures"
NATIVE_DIR = ROOT / "mobile" / "ios"
SHARED_VECTOR_DIR = ROOT / "contracts" / "fixtures" / "shared"

PACKAGE_SCHEMA = "mobile/contracts/live_round_package.schema.json"
IDENTITY_CASES = "mobile/contracts/fixtures/round_identity_cases.json"
# Whole contract documents and the schema each one is an instance of.
FIXTURE_SCHEMAS = {
    "mobile/contracts/fixtures/live_round_package.fixture.json": PACKAGE_SCHEMA,
    "mobile/contracts/fixtures/live_round_event.fixture.json": "mobile/contracts/live_round_event.schema.json",
    "mobile/contracts/fixtures/watch/round_state.fixture.json": "mobile/contracts/watch_round_state.schema.json",
    "mobile/contracts/fixtures/watch/input_score.fixture.json": "mobile/contracts/watch_input_event.schema.json",
    "mobile/contracts/fixtures/watch/input_location.fixture.json": "mobile/contracts/watch_input_event.schema.json",
}
# Native bundle resource copy -> the contract file it was copied from.
NATIVE_COPIES = {
    "mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json":
        "mobile/contracts/fixtures/live_round_package.fixture.json",
    "mobile/ios/AICaddie/Fixtures/live_round_event.fixture.json":
        "mobile/contracts/fixtures/live_round_event.fixture.json",
    "mobile/ios/AICaddieTests/Fixtures/round_identity_cases.json": IDENTITY_CASES,
    "mobile/ios/AICaddieWatchTests/round_identity_cases.json": IDENTITY_CASES,
    "mobile/ios/AICaddieTests/Fixtures/mobile_event_sanitizer_golden.json":
        "contracts/canonical/fixtures/mobile_event_sanitizer_golden.json",
}
# Cross-language product vectors read by Python tests and bundled into the Swift tests.
SHARED_VECTORS = (
    "contracts/fixtures/shared/c120_avoid_zones.json",
    "contracts/fixtures/shared/caddie_golden.json",
    "contracts/fixtures/shared/loop_map.json",
    "contracts/fixtures/shared/tee_result.json",
)


def _json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _errors(schema, document):
    return [f"{'/'.join(map(str, error.absolute_path))}: {error.message}"
            for error in Draft202012Validator(schema).iter_errors(document)]


def _listed(directory, pattern="*"):
    return {path.relative_to(ROOT).as_posix() for path in directory.rglob(pattern) if path.is_file()}


class ContractFixtureSchemaTests(SmallTestCase):
    """S-06 S-11: the package and event fixtures both ends test against are valid contract documents."""

    def test_every_contract_fixture_is_checked(self):
        """S-06 S-11: a new contract fixture cannot be added without a schema to check it against."""
        self.assertEqual(_listed(CONTRACT_FIXTURE_DIR), set(FIXTURE_SCHEMAS) | {IDENTITY_CASES})

    def test_fixtures_pass_their_schema(self):
        """S-06 S-11: each package and event fixture is accepted by its contract schema."""
        for fixture, schema in FIXTURE_SCHEMAS.items():
            with self.subTest(fixture=fixture):
                self.assertEqual([], _errors(_json(schema), _json(fixture)))

    def test_valid_identity_cases_fit_the_package_schema(self):
        """S-06: every valid round-identity case uses package fields exactly as the package schema defines them.

        A case carries only the identity slice of a package, so only the fields it
        has are required; their shapes and values must still be schema-valid.
        """
        package_schema = _json(PACKAGE_SCHEMA)
        cases = _json(IDENTITY_CASES)
        self.assertEqual(cases["schema"], "ai-caddie-round-identity-cases-v1")
        self.assertTrue(cases["valid"])
        for name, package in cases["valid"].items():
            with self.subTest(case=name):
                slice_schema = {**package_schema,
                                "required": [key for key in package_schema["required"] if key in package]}
                self.assertEqual([], _errors(slice_schema, package))


class NativeFixtureCopyTests(SmallTestCase):
    """S-06 S-11: the fixtures bundled into the iPhone and Watch tests are the contract files themselves."""

    def test_native_copies_are_byte_identical(self):
        """S-06 S-11: every Swift resource copy has exactly the bytes of its contract source."""
        for copy, source in NATIVE_COPIES.items():
            with self.subTest(copy=copy):
                self.assertEqual((ROOT / copy).read_bytes(), (ROOT / source).read_bytes())

    def test_every_native_copy_is_registered(self):
        """S-06 S-11: a bundled copy of a contract fixture cannot escape the byte comparison."""
        source_names = {Path(source).name for source in NATIVE_COPIES.values()}
        bundled = {path for path in _listed(NATIVE_DIR, "*.json")
                   if path.endswith(".fixture.json") or Path(path).name in source_names}
        self.assertEqual(bundled, set(NATIVE_COPIES))


class SharedVectorLocationTests(SmallTestCase):
    """META: cross-language product vectors live with the contracts, not under one side's tests."""

    def test_shared_vectors_live_with_contracts(self):
        """META: the shared vector set is complete under contracts/fixtures/shared and each file has cases."""
        self.assertEqual(_listed(SHARED_VECTOR_DIR, "*.json"), set(SHARED_VECTORS))
        for vector in SHARED_VECTORS:
            with self.subTest(vector=vector):
                ids = [case["id"] for case in _json(vector)["cases"]]
                self.assertTrue(ids)
                self.assertEqual(len(ids), len(set(ids)))
