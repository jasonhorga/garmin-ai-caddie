# Card #440 — agenthub native mutant workflow (Swift mutants judged by real native tests)

agenthub dispatches one workflow run per mutant on CI. Each run tests the head under test, plus the
mutant patch, with the real native tests. It then uploads `result.json`. agenthub counts a mutant
as caught when a native test fails. The gate stays as strict as before:
- at least three distinct mutants, all caught;
- an apply or build failure is invalid;
- a red baseline judges nothing.

Touches: `.github/workflows/agenthub-native-mutant.yml`, `.github/scripts/agenthub_native_result.py`, `tests/acceptance/test_card_440_native_mutant_workflow.py`, `.agent/contracts/card-440.md`

Acceptance tests: `tests/acceptance/test_card_440_native_mutant_workflow.py` (8 tests). Codex
must not edit `tests/acceptance/`.

## About the agenthub template

The card asks for the agenthub template (`templates/native-mutant/` at 3b89733), copied and adapted.
I could not read that template from this checkout, so this contract defines:
- the interface the acceptance tests check;
- the `result.json` format.

If the template differs from this contract, do not reshape the template to match it. Examples: other
input names than the tolerated ones below, other `result.json` keys or status words, a different
test id format. Report the differences on the card before you implement. I will then revise the
contract and the tests to follow the template, because agenthub's reader is the authority on the
format.

The tests only check what the card asks for. The following stay free:
- the writer's command line (the tests run whatever the workflow runs);
- how the head and the writer are checked out;
- the artifact name;
- the step layout.

## Interface

### Workflow `.github/workflows/agenthub-native-mutant.yml`

- `on:` has only `workflow_dispatch`, with exactly three `string` inputs:
  - `request_id` (required);
  - the head SHA (required): one input whose name contains `sha`, e.g. `head_sha`;
  - the mutant patch as base64: one input whose name contains `patch`, e.g. `patch_b64`. It is
    empty for a baseline run.
- `run-name: agenthub-native ${{ inputs.request_id }}`, exactly.
- `permissions: contents: read` at the top level. If a job sets `permissions`, it is the same
  mapping.
- One job:
  - `runs-on` is the same value as the `native-mobile` job in `native-mobile.yml` (`macos-15`);
  - no job-level `if:` or `continue-on-error`.
- No `secrets.` anywhere, and no `AICaddieUITests` anywhere in the file.
- Every `run:` is bash and contains no `${{ … }}`. Inputs and step outcomes reach the shell
  through `env:`, which also prevents script injection.
- The head under test is checked out with `actions/checkout` and
  `ref: ${{ inputs.<sha input> }}`.
- **The writer comes from the workflow's own revision, not from the head under test.**
  - #434's head was branched before this card, so it has no `agenthub_native_result.py`, and a
    mutant patch must not be able to change the writer.
  - One way to do this: check out the dispatched revision (`actions/checkout` without `ref`) into
    a separate `path:`, and check out the head into another one.
  - `actions/checkout` replaces whatever its `path` held. Do not check the head out over a
    directory that holds the tools.
- Order of the steps:
  1. **Apply.** Decode the patch (`base64 --decode` or python3) and `git apply` it at the root of
     the head checkout. An empty patch is a baseline: there is nothing to apply, and the step
     succeeds. A patch that does not decode, is not a patch, or does not apply cleanly is an
     apply failure. The step's outcome must carry that (`continue-on-error: true` on this step is
     the expected way). When the apply fails, no `xcodebuild test` runs.
  2. **Simulators by UDID.** Pick the simulators from
     `xcrun simctl list devices available -j`:
     - the `iPhone 16` on the newest iOS runtime that has one available;
     - the `Apple Watch Series 10 (46mm)` on the newest watchOS runtime that has one available.

     "Newest" compares the runtime's `(major, minor)` numerically: `watchOS-11-10` is newer than
     `watchOS-11-5`. Device names match exactly (`iPhone 16 Plus` is not `iPhone 16`). Parse the
     JSON with python3; the acceptance environment does not guarantee `jq`. If either device is
     missing, the step fails. That is a runner failure (see "Outcomes").
  3. **Generate.** `xcodegen generate --spec mobile/ios/project.yml --project-root .`, exactly
     these arguments, at the root of the head checkout, after the patch is applied. Installing
     XcodeGen with `brew install xcodegen` is fine.
  4. **Test.** One `xcodebuild test` per scheme, at the root of the head checkout:
     - with `-project mobile/ios/AICaddieNative.xcodeproj`;
     - with `-scheme AICaddie` and
       `-destination "platform=iOS Simulator,id=<iOS UDID>"`;
     - with `-scheme AICaddieWatch` and
       `-destination "platform=watchOS Simulator,id=<Watch UDID>"`;
     - each with its own new `-resultBundlePath`;
     - with no `name=` in the destination and no `-only-testing`.

     Only `-skip-testing:AICaddieWatchUITests` may be skipped. The Watch scheme's UI journeys run
     against fixture screens without a backend, so keeping them is allowed. The `AICaddieUITests`
     scheme or target never runs. A test failure (exit 65) keeps the job green
     (`continue-on-error: true` on the test steps), and the Watch scheme still runs after an iOS
     failure. Use `xcodebuild test`, not `build-for-testing` / `test-without-building`.
  5. **Write.** `python3 <tools checkout>/.github/scripts/agenthub_native_result.py …` writes
     `result.json`. It runs after an apply, build or test failure. It does not run, or at least
     uploads nothing, after a runner failure.
  6. **Upload.** `actions/upload-artifact` uploads one path: `result.json`, or a directory that
     contains it. Use the template's artifact name.

### Result writer `.github/scripts/agenthub_native_result.py`

- Python 3 standard library only. It reads each scheme's bundle with
  `xcrun xcresulttool get test-results tests --path <bundle>` (Xcode 16; not `--legacy`).
- **Tests.** Every node with `nodeType == "Test Case"` in `testNodes` is one test:
  - its `id` is `<bundle>/<nodeIdentifier>`, e.g.
    `AICaddieTests/StartRoundDiscoveryTests/testOpeningPageIsCourseUnlessACourseIsPassed()`;
  - `<bundle>` is the name of the nearest `Unit test bundle` / `UI test bundle` ancestor;
  - when `nodeIdentifier` is missing, the id falls back to `<bundle>/<suite>/<name>`;
  - nodes below a Test Case (`Device`, `Test Case Run`, `Failure Message`, …) are not tests.
- **Status mapping:** `Passed` and `Expected Failure` map to `passed`, `Failed` to `failed`, and
  `Skipped` to `skipped`. Any other or missing `result` fails closed: the writer exits non-zero and
  writes no `result.json`, so nothing is uploaded and nothing is judged.

### `result.json`

```json
{
  "request_id": "<request_id input>",
  "head_sha": "<head SHA input>",
  "status": "tested | apply_failed | build_failed",
  "tests": [{"id": "<bundle>/<nodeIdentifier>", "status": "passed | failed | skipped"}]
}
```

Extra keys are allowed. Test ids are unique.
- `apply_failed`: the patch did not apply. `tests` is `[]`.
- `build_failed`: some scheme has no usable result. The bundle may be missing, xcresulttool may
  have failed, the output may not be JSON, or there may be no Test Case at all. `tests` is
  unchecked.
- `tested`: otherwise. `tests` lists every Test Case of both schemes. A mutant is caught when one
  of them is `failed`.

### Outcomes

| Run | Job | result.json |
|---|---|---|
| baseline, all tests pass | green | `tested`, all `passed` |
| a native test fails (exit 65) | green | `tested`, that test `failed` |
| patch does not apply / decode | green | `apply_failed`, no xcodebuild test |
| a scheme leaves no usable result | green | `build_failed` |
| simulator missing (runner failure) | red | not uploaded |
| unrecognised test result | red | not uploaded |

## Replay rules (how the acceptance tests run the workflow)

Linux CI has no Xcode, so the tests replay the single job offline:
- Steps run in order under GitHub's rules: a default `if: success()`, status functions,
  `continue-on-error`, `steps.<id>.outcome` / `conclusion` / `outputs`, `$GITHUB_ENV`,
  `$GITHUB_OUTPUT`.
- `run:` steps run in real bash (`bash -e`, or `bash --noprofile --norc -eo pipefail` for
  `shell: bash`), with real git, base64 and python3. `working-directory` is supported.
- `actions/checkout` clones a throwaway origin:
  - `main` holds this workflow, the writer and `.github/scripts`;
  - the head under test is an older commit without the workflow and the writer, like #434's head;
  - `ref`: a SHA, a branch, or `refs/heads/…`; by default `github.sha`, the `main` commit;
  - `path` is supported; the target's contents are replaced.
- `actions/upload-artifact` records `path`; other actions are no-ops.
- `xcrun` (`simctl`, `xcresulttool get test-results tests`), `xcodebuild`, `xcodegen`, `brew`,
  `xcode-select` and `sudo` are fakes. `xcodegen generate` creates the project directory next to
  the spec. `xcodebuild test` needs that project, and creates the result bundle.
- Supported `${{ }}` (in `env:`, `with:`, `if:`, `continue-on-error`):
  - contexts: `inputs.*`, `github.event.inputs.*`, `github.{sha,ref,ref_name,repository,
    repository_owner,workspace,run_id,run_number,run_attempt,event_name,actor,server_url}`,
    `runner.{temp,os,arch}`, `env.*`, `steps.*`, `job.status`;
  - literals: strings, numbers, `true`, `false`, `null`;
  - operators: `== != && || !` and parentheses;
  - functions: `success() failure() always() cancelled()`.

  Anything else fails the test with a message naming the expression.

### G1 — The workflow is dispatch-only and read-only, named `agenthub-native <request_id>`, with three inputs

1. `test_workflow_is_dispatch_only_read_only_and_named_by_request_id`: the trigger, inputs,
   permissions, run-name, single job on native-mobile's runner, no secrets, no `${{ }}` in `run:`,
   bash only, the writer is run, and the head is checked out by its input.
2. `test_baseline_run_tests_the_head_with_both_schemes_on_udid_simulators` (replay, also G2–G4) and
   `test_patch_that_does_not_apply_is_reported_as_apply_failed` (also G3) feed the three inputs
   and check that `request_id` and the head SHA come back in `result.json`.

### G2 — It builds and tests the head plus patch like native-mobile: xcodegen, both schemes, simulators by UDID, never AICaddieUITests

3. Baseline replay: `xcodegen` runs once with exactly `XCODEGEN_ARGS` in the head checkout.
   `xcodebuild test` runs once per scheme (`AICaddie`, `AICaddieWatch`):
   - on `mobile/ios/AICaddieNative.xcodeproj`;
   - with `-resultBundlePath`;
   - on `platform=iOS Simulator,id=<newest iPhone 16>` and
     `platform=watchOS Simulator,id=<newest Series 10 (46mm)>`;
   - with no `name=`, no `-only-testing`, and no argument naming `AICaddieUITests`.
4. `test_failing_native_test_is_reported_and_the_job_stays_green` and
   `test_watch_only_failure_is_reported`: the patch is applied before generate and test (the
   marker file reads `"mutant"`), and both schemes still run after a failure.
5. `test_missing_simulator_is_a_runner_failure_without_result`: no test runs on a device other
   than the expected UDID.

### G3 — `result.json` is the verdict: green on test failures, apply/build failures recorded, nothing uploaded on a runner failure

6. Failing iOS test, or failing Watch test: the job is green and `status` is `tested`.
7. Stale patch, input that is not base64, input that is not a patch: green, no `xcodebuild test`,
   `apply_failed`, `tests: []`.
8. Watch ran no test, Watch or iOS left no bundle, unreadable bundle, non-JSON tree: green,
   `build_failed`.
9. No available iPhone 16, or no available Series 10 (46mm): the job is red and no `result.json`
   is uploaded.
10. A Test Case `result` of `unknown`, or none at all: the job is red and no `result.json` is
    uploaded.

### G4 — The writer turns the xcresulttool tree into the result format

11. Baseline: all 8 sample tests (`AICaddieDomainTests`, `AICaddieTests`, `AICaddieWatchTests`,
    `AICaddieWatchUITests`) are listed as `passed`, with ids `<bundle>/<nodeIdentifier>`. The
    `Device` / `Test Case Run` nodes under a case are not counted.
12. Mutant: each test gets its status: `Failed` maps to `failed`, `Skipped` to `skipped`, and
    `Expected Failure` to `passed`.
13. Cases 8 and 10 cover `build_failed` and failing closed.

## Not covered by these tests

- Parity with the agenthub template, and the real xcresulttool output on the runner. After the
  merge, the console dispatches a baseline run (empty patch) on #434's head. It checks that the
  uploaded `result.json` lists the native tests, all `passed`. Only then is
  `[adversarial.native]` turned on for this project.
- `native-mobile.yml` and app code stay untouched (card step 3). The reviewer checks this in the
  diff; a hash pin would break later cards.
- This PR changes no path under `native-mobile.yml`'s `pull_request.paths`, so the native
  acceptance gate does not apply. `.github/**` is protected, so the full gate does. CI must be
  green.

## Not run

The contract sandbox did not allow running Python. The tests have not been executed here, either
on `main` or against a reference implementation.
- On `main` every test fails at the first check: the workflow and the writer do not exist.
- I checked the replay by reading it against a reference workflow and writer that follow this
  contract.
