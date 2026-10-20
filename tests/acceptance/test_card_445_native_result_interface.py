"""Card #445: the native mutant workflow follows agenthub's result interface.

agenthub's reader (`agenthub/native.py`) takes exactly one artifact named `agenthub-native-<request_id>`
holding only `result.json`, an object with exactly the keys `request_id`, `head`, `patch_sha256`,
`stage` and `tests`. #440's workflow uploaded `agenthub-native-result` with other keys, so the first
real gate run on #434 ended as `artifact missing or invalid`.

These tests replay the workflow offline with card #440's harness (`_Replay`, fake Xcode tools, a
throwaway origin), so the real result writer runs from the workflow's own step. The contract is
`.agent/contracts/card-445.md`; the updated #440 tests share the stricter `_result` checks.
"""

from __future__ import annotations

import base64
import hashlib
import uuid

import yaml

from .test_card_440_native_mutant_workflow import (
    ARTIFACT,
    BASELINE_STATUSES,
    BROKEN_SPEC_PATCH,
    HEAD_MARKER,
    IOS_CASES,
    IOS_FAILED_ONCE,
    MUTANT_MARKER,
    MUTANT_PATCH,
    PASSING_IOS,
    PASSING_WATCH,
    RESULT_KEYS,
    STALE_CONTEXT_PATCH,
    STALE_PATCH,
    TRAILING_SPACE_MARKER,
    TRAILING_SPACE_PATCH,
    WATCH_CASES,
    WATCH_DEVICE,
    WORKFLOW,
    NativeMutantReplayCase,
    _b64,
    _case,
    _option,
    _patch,
    _scheme,
    _tree,
)


# sha256 of no bytes: a baseline sends an empty patch.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
NOT_A_PATCH = "this is not a unified diff\n"


def _digest(text: str) -> str:
    # G4: the sha256 hex digest of a patch's bytes as agenthub sends them (UTF-8, before base64).
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class NativeResultInterfaceTests(NativeMutantReplayCase):
    def test_dispatch_inputs_and_upload_step_follow_agenthubs_interface(self) -> None:
        # G1: the inputs agenthub already dispatches with (#434's runs were accepted) stay exactly
        # request_id, head_sha and patch_b64; one upload step names the artifact
        # `agenthub-native-${{ inputs.request_id }}` exactly and fails when result.json is missing.
        workflow = self._workflow()
        triggers = workflow.get("on", workflow.get(True))
        self.assertIsInstance(triggers, dict)
        inputs = (triggers.get("workflow_dispatch") or {}).get("inputs") or {}
        self.assertEqual(sorted(inputs), ["head_sha", "patch_b64", "request_id"])
        self.assertIs(inputs["request_id"].get("required"), True)
        self.assertIs(inputs["head_sha"].get("required"), True)
        self.assertIs((inputs["patch_b64"] or {}).get("required", False), False)
        steps = next(iter((workflow.get("jobs") or {}).values())).get("steps") or []
        uploads = [step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
        self.assertEqual(len(uploads), 1, "exactly one upload step")
        with_ = uploads[0].get("with") or {}
        self.assertEqual(with_.get("name"), ARTIFACT)
        self.assertEqual(with_.get("if-no-files-found"), "error")
        self.assertEqual(len(str(with_.get("path", "")).strip().splitlines()), 1, "one upload path")
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("agenthub-native-result", text, "the old artifact name is gone")
        self.assertIsInstance(yaml.safe_load(text), dict)

    def test_baseline_result_json_has_exactly_agenthubs_keys(self) -> None:
        # G1 G2 G4: a baseline (empty patch) with a request id that uses `_` and `.` uploads exactly one
        # artifact `agenthub-native-<request_id>` holding only result.json, with exactly request_id,
        # head (the dispatched SHA), patch_sha256 (sha256 of no bytes), stage `tested` and every test as
        # {"id", "status"}; both schemes still run on the UDID simulators, from the head checkout.
        request_id = f"card445_base.{uuid.uuid4().hex[:8]}"
        run = self._replay(patch_b64="", request_id=request_id)

        self.assertFalse(run.job_failed, run.describe())
        self._check_scheme_runs(run, HEAD_MARKER)
        self.assertEqual([upload["name"] for upload in run.uploads], [f"agenthub-native-{request_id}"], run.describe())
        result = self._result(run)
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["request_id"], request_id)
        self.assertRegex(result["head"], r"\A[0-9a-f]{40}\Z")
        self.assertEqual(result["head"], run.head_sha)
        self.assertEqual(result["patch_sha256"], EMPTY_SHA256)
        self.assertEqual(result["stage"], "tested")
        self.assertEqual(self._statuses(result), BASELINE_STATUSES)

    def test_mutant_digest_is_the_sha256_of_the_decoded_patch_bytes(self) -> None:
        # G3 G4: for a mutant a native test catches, the job stays green, stage is `tested` with the
        # failed test, and patch_sha256 is the digest of the decoded patch bytes: not of the base64 text,
        # and with an added line's trailing space kept.
        watch_failing = _tree("AICaddieWatch", WATCH_CASES, ("Passed", "Failed", "Passed"), WATCH_DEVICE)
        cases = {
            "iOS test fails": (
                MUTANT_PATCH,
                _patch(HEAD_MARKER, MUTANT_MARKER),
                MUTANT_MARKER,
                _scheme(65, tree=IOS_FAILED_ONCE),
                PASSING_WATCH,
                f"{IOS_CASES[2][0]}/{IOS_CASES[2][1]}/{IOS_CASES[2][2]}",
            ),
            "Watch test fails, the added line ends in a space": (
                TRAILING_SPACE_PATCH,
                _patch(HEAD_MARKER, TRAILING_SPACE_MARKER),
                TRAILING_SPACE_MARKER,
                PASSING_IOS,
                _scheme(65, tree=watch_failing),
                f"{WATCH_CASES[1][0]}/{WATCH_CASES[1][1]}/{WATCH_CASES[1][2]}",
            ),
        }
        for name, (patch_b64, patch_text, marker, ios, watch, failed_id) in cases.items():
            with _case(name):
                run = self._replay(patch_b64=patch_b64, ios=ios, watch=watch)

                self.assertFalse(run.job_failed, run.describe())
                self._check_scheme_runs(run, marker)
                result = self._result(run)
                self.assertEqual(result["stage"], "tested")
                self.assertEqual(result["patch_sha256"], _digest(patch_text))
                self.assertNotEqual(result["patch_sha256"], _digest(patch_b64))
                expected = dict(BASELINE_STATUSES)
                expected[failed_id] = "failed"
                self.assertEqual(self._statuses(result), expected)

    def test_unappliable_patch_is_apply_failed_with_a_green_job(self) -> None:
        # G3 G4: a patch that decodes but does not apply (stale changed line, stale context, not a diff)
        # gives a green job and one artifact whose result.json has stage `apply_failed`, tests [] and the
        # digest of the decoded patch bytes; nothing is generated or tested.
        cases = {
            "stale changed line": STALE_PATCH,
            "stale surrounding context": STALE_CONTEXT_PATCH,
            "not a patch": _b64(NOT_A_PATCH),
        }
        for name, patch_b64 in cases.items():
            with _case(name):
                run = self._replay(patch_b64=patch_b64)

                self.assertFalse(run.job_failed, run.describe())
                self.assertEqual(run.scheme_runs(), [], run.describe())
                self.assertEqual(run.tool("xcodegen"), [], run.describe())
                result = self._result(run)
                self.assertEqual(result["stage"], "apply_failed")
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["patch_sha256"], hashlib.sha256(base64.b64decode(patch_b64)).hexdigest())

    def test_build_failure_is_build_failed_with_empty_tests(self) -> None:
        # G3 G4: a patched spec that does not generate, or a scheme that leaves no result next to a
        # failed test in the other one, gives a green job and stage `build_failed` with tests [] (never
        # the other scheme's tests) and the digest of the decoded patch.
        cases = {
            "the patched project spec does not generate": (BROKEN_SPEC_PATCH, PASSING_IOS, PASSING_WATCH),
            "iOS failed a test, Watch left no result bundle": (
                MUTANT_PATCH,
                _scheme(65, tree=IOS_FAILED_ONCE),
                _scheme(65, bundle=False),
            ),
        }
        for name, (patch_b64, ios, watch) in cases.items():
            with _case(name):
                run = self._replay(patch_b64=patch_b64, ios=ios, watch=watch)

                self.assertFalse(run.job_failed, run.describe())
                result = self._result(run)
                self.assertEqual(result["stage"], "build_failed")
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["patch_sha256"], hashlib.sha256(base64.b64decode(patch_b64)).hexdigest())

    def test_invalid_dispatch_inputs_fail_without_an_artifact(self) -> None:
        # G1 G3: input validation. A request id that is empty or holds whitespace or a character an
        # artifact name cannot carry, or a head that is not a full 40-character lower-case hex SHA, fails
        # the job before anything is generated or tested, and no artifact is uploaded.
        cases = {
            "empty request id": {"request_id": ""},
            "request id with a slash": {"request_id": "card445/evil"},
            "request id with a space": {"request_id": "card445 evil"},
            "request id with a quote": {"request_id": 'card445"evil'},
            "request id with a colon": {"request_id": "card445:evil"},
            "head is a branch name": {"head": "main"},
            "head is empty": {"head": ""},
        }
        for name, options in cases.items():
            with _case(name):
                run = self._replay(patch_b64="", **options)

                self.assertTrue(run.job_failed, f"invalid input must fail the job\n{run.describe()}")
                self.assertEqual(run.uploads, [], run.describe())
                self.assertEqual(run.scheme_runs(), [], run.describe())
                self.assertEqual(
                    [call for call in run.tool("xcodegen") if call["args"][:1] == ["generate"]], [], run.describe()
                )
                self.assertFalse(
                    [call for call in run.tool("xcodebuild") if _option(call["args"], "-scheme")], run.describe()
                )
