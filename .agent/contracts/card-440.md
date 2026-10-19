# Card #440 — agenthub native mutant workflow (Swift mutants judged by real native tests)

agenthub dispatches one workflow run per mutant on CI. Each run tests the head under test, plus the
mutant patch, with the real native tests. It then uploads `result.json`. agenthub counts a mutant
as caught when a native test fails. The gate stays as strict as before:
- at least three distinct mutants, all caught;
- an apply or build failure is invalid;
- a red baseline judges nothing.

Touches: `.github/workflows/agenthub-native-mutant.yml`, `.github/scripts/agenthub_native_result.py`, `tests/test_agenthub_native_result.py`, `tests/acceptance/test_card_440_native_mutant_workflow.py`, `.agent/contracts/card-440.md`

Acceptance tests: `tests/acceptance/test_card_440_native_mutant_workflow.py` (9 tests). Codex
must not edit `tests/acceptance/`.

## Revision 5: more wrong implementations caught

The gate's adversarial check failed on head `6942203`, which holds the revision-4 tests and the
implementation from `b7f0936`. I could not read the gate report. I read the head against the tests
again and listed the wrong implementations that would still pass; revision 5 catches them. The
goals, the interface and the result format are unchanged. The new pass conditions (marked
**(rev 5)** below) state what the head already does, so **no implementation change is expected**.
If a new case fails, fix the workflow or the writer, not the tests.

Now caught:
- **Writer stops early:** it stops at the first scheme without a usable result, so it never reads
  an unknown result in the other scheme. That must still fail closed.
- **Failed test hides a build failure:** a failed test in one scheme is reported as `tested` when
  the other scheme left no result. That is `build_failed`.
- **Duplicates merged:** duplicate ids are merged when their statuses agree, or are checked only
  across the schemes. The same id passed in both schemes, or listed twice in one tree, fails closed.
- **Writer exits 0:** it exits 0 without writing `result.json` on a result it cannot judge. The
  writer's step must fail.
- **Fixed depth:** the writer reads Test Cases only at a fixed depth. One iOS case now sits in a
  nested suite, as Swift Testing reports it.
- **Prefix name match:** simulator names are matched by prefix or substring. `iPhone 16 Plus` and
  `Series 10 (42mm)` now sit in the expected devices' runtimes, so every tie-break picks a wrong
  device.
- **Narrowed run:** an extra destination field (`OS=latest`), or a scheme narrowed with `-testPlan`
  or a test configuration.
- **Tests after a failed generate:** `xcodebuild test` runs after `xcodegen generate` failed.
- **No XcodeGen install:** the step that installs XcodeGen is left out. The fake `xcodegen` is now
  missing until `brew install xcodegen` runs, as on the runner image.
- **Writer from the head:** the workflow uses the head's writer when the head has one. A mutant
  patch now adds a writer that only fails.

Some changes stay uncaught because they behave the same in every run this contract defines. For
example, `always()` instead of `!cancelled()`, or dropping one of the write step's redundant
conditions. If the gate reports such a survivor, it should name it. I will then either pin the
behaviour it changes or record it as equivalent here.

History:
- Revision 4 renamed the helper `test_runs()` to `scheme_runs()`, because the gate counted it as a
  test. It also added the simulator-order, generate, install, duplicate, stale-context and static
  cases.
- Revision 3 replaced `subTest` with `_case`.
- Revision 2 made this contract the authoritative interface (next section).

## About the agenthub template (revision 2)

The card asks for agenthub's `templates/native-mutant/` at 3b89733, copied and adapted. **Neither
the contract job nor the implementation session can read it.** agenthub is a separate repository,
and both run offline. I cannot provide the template's files, and I won't recreate them from memory
as if they were authoritative.

So that implementation can go ahead without guessing, this contract is now **the authoritative
interface for this repository.** It does not just reflect the template. In particular:
- **Artifact name:** `agenthub-native-result`, fixed by this contract. `result.json` sits at the
  root of that artifact. The tests check this.
- **`result.json` format:** the keys, status words and test id format under "`result.json`"
  below. These come from this contract, not from the template.
- **Writer:** written for this contract, not copied. Card step 1 says "copy … unchanged"; that
  cannot be done here. In the PR body, say that the writer and workflow follow
  `.agent/contracts/card-440.md` because the template was not available.

Compatibility with agenthub's reader is checked outside this repository, by the console's
post-merge dispatches (see "Not covered"). If agenthub's reader expects another artifact name, other
keys or other status words, the console reports the difference and a follow-up card aligns the
workflow, the writer and these tests. Nothing is judged by this workflow until that check passes.

The tests only check what the card and this contract ask for. The following stay free:
- the writer's command line (the tests run whatever the workflow runs);
- how the head and the writer are checked out;
- the step layout.

## Interface

### Workflow `.github/workflows/agenthub-native-mutant.yml`

- `on:` has only `workflow_dispatch`, with exactly three `string` inputs:
  - `request_id` (required);
  - the head SHA (required): one input whose name contains `sha`. `head_sha` is recommended;
  - the mutant patch as base64: one input whose name contains `patch`. `patch_b64` is
    recommended. It is empty for a baseline run, so it is **not required** (`required` absent or
    `false`).
- `run-name: agenthub-native ${{ inputs.request_id }}`, exactly.
- `permissions: contents: read` at the top level. If a job sets `permissions`, it is the same
  mapping.
- One job:
  - `runs-on` is the same value as the `native-mobile` job in `native-mobile.yml` (`macos-15`);
  - no job-level `if:` or `continue-on-error`.
- No `concurrency` at the workflow or job level. agenthub dispatches one run per mutant; a shared
  concurrency group cancels pending runs.
- No `secrets.` anywhere, and no `AICaddieUITests` anywhere in the file.
- Every `run:` is bash and contains no `${{ … }}`. Inputs and step outcomes reach the shell
  through `env:`, which also prevents script injection.
- The head under test is checked out with `actions/checkout` and
  `ref: ${{ inputs.<sha input> }}`.
- Every `actions/checkout` step sets `persist-credentials: false`. The patch is untrusted code that
  runs on the runner.
- **The writer comes from the workflow's own revision, not from the head under test.**
  - #434's head was branched before this card, so it has no `agenthub_native_result.py`, and a
    mutant patch must not be able to change the writer. A head (or patch) that brings its own
    writer does not change which writer runs **(rev 5)**.
  - One way to do this: check out the dispatched revision (`actions/checkout` without `ref`) into
    a separate `path:`, and check out the head into another one.
  - `actions/checkout` replaces whatever its `path` held. Do not check the head out over a
    directory that holds the tools.
- Order of the steps:
  1. **Apply.** Decode the patch (`base64 --decode` or python3) and `git apply` it at the root of
     the head checkout. An empty patch is a baseline: there is nothing to apply, and the step
     succeeds. A patch that does not decode, is not a patch, or does not apply cleanly is an
     apply failure. "Cleanly" means `git apply`'s default: every context line must match, so no
     fuzz and no reduced context (`git apply -C…`, `patch`). The step's outcome must carry the
     failure (`continue-on-error: true` on this step is the expected way). When the apply fails,
     no `xcodebuild test` runs.
  2. **Simulators by UDID.** Pick the simulators from
     `xcrun simctl list devices available -j`:
     - the `iPhone 16` on the newest iOS runtime that has one available;
     - the `Apple Watch Series 10 (46mm)` on the newest watchOS runtime that has one available.

     "Newest" compares the runtime's `(major, minor)` numerically: `watchOS-11-10` is newer than
     `watchOS-11-5`. Device names match exactly, not by prefix or substring: `iPhone 16 Plus` is
     not `iPhone 16` **(rev 5)**. The order of runtimes and devices in the listing means nothing.
     Parse the JSON with python3; the acceptance environment does not guarantee `jq`. If either
     device is missing, the step fails. That is a runner failure (see "Outcomes").
  3. **Generate.** Install XcodeGen with `brew install xcodegen`, as `native-mobile.yml` does: the
     runner image does not ship it **(rev 5)**. If the install fails, that is a runner failure.
     Then run `xcodegen generate --spec mobile/ios/project.yml --project-root .`, exactly these
     arguments, at the root of the head checkout, after the patch is applied. If `xcodegen
     generate` fails (the patched spec does not generate), that is a build failure of the mutant:
     the job stays green, no `xcodebuild test` runs **(rev 5)**, and `result.json` says
     `build_failed`.
  4. **Test.** One `xcodebuild test` per scheme, at the root of the head checkout:
     - with `-project mobile/ios/AICaddieNative.xcodeproj`;
     - with `-scheme AICaddie` and
       `-destination "platform=iOS Simulator,id=<iOS UDID>"`;
     - with `-scheme AICaddieWatch` and
       `-destination "platform=watchOS Simulator,id=<Watch UDID>"`;
     - each destination has exactly these two fields: no `name=`, no `OS=` **(rev 5)**;
     - each with its own new `-resultBundlePath` (two different paths);
     - with the scheme's whole test action: no `-only-testing`, `-only-test-configuration`,
       `-skip-test-configuration` or `-testPlan` **(rev 5)**.

     Only `-skip-testing:AICaddieWatchUITests` may be skipped. The Watch scheme's UI journeys run
     against fixture screens without a backend, so keeping them is allowed. The `AICaddieUITests`
     scheme or target never runs. A test failure (exit 65) keeps the job green
     (`continue-on-error: true` on the test steps), and the Watch scheme still runs after an iOS
     failure. Use `xcodebuild test`, not `build-for-testing` / `test-without-building`.
  5. **Write.** `python3 <tools checkout>/.github/scripts/agenthub_native_result.py …` writes
     `result.json`. It runs after an apply, generate, build or test failure. It does not run, or
     at least uploads nothing, after a runner failure.
  6. **Upload.** Exactly one `actions/upload-artifact` step, with:
     - `name: agenthub-native-result`, as a literal (no expression);
     - one `path`: the `result.json` file itself, or a directory with `result.json` directly in
       it, so that `result.json` is at the artifact's root.

     No other step uploads an artifact.

### Result writer `.github/scripts/agenthub_native_result.py`

- Python 3 standard library only. It reads each scheme's bundle with
  `xcrun xcresulttool get test-results tests --path <bundle>` (Xcode 16; not `--legacy`).
- **Tests.** Every node with `nodeType == "Test Case"` in `testNodes`, at any depth, is one test.
  A Test Case can sit in a suite nested in another suite **(rev 5)**.
  - its `id` is `<bundle>/<nodeIdentifier>`, e.g.
    `AICaddieTests/StartRoundDiscoveryTests/testOpeningPageIsCourseUnlessACourseIsPassed()`;
  - `<bundle>` is the name of the nearest `Unit test bundle` / `UI test bundle` ancestor;
  - when `nodeIdentifier` is missing, the id falls back to `<bundle>/<suite>/<name>`, with the
    nearest suite;
  - nodes below a Test Case (`Device`, `Test Case Run`, `Failure Message`, …) are not tests.
- **Status mapping:** `Passed` and `Expected Failure` map to `passed`, `Failed` to `failed`, and
  `Skipped` to `skipped`.
- **Fail closed.** The writer exits non-zero, writes no `result.json`, and so nothing is uploaded
  or judged, when:
  - any Test Case has another or missing `result`, in either scheme. This holds even when the
    other scheme left no usable result: the writer still reads both schemes **(rev 5)**;
  - two Test Cases get the same id, in one tree or across the two schemes, whatever their statuses
    **(rev 5)**. Merging them could hide a failure behind a pass.

  The step that runs the writer must therefore end in `failure` **(rev 5)**.

### `result.json` (artifact `agenthub-native-result`, at its root)

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
- `build_failed`: the project did not generate, or some scheme has no usable result. The bundle
  may be missing, xcresulttool may have failed, the output may not be JSON, or there may be no Test
  Case at all. This holds even when the other scheme has a failed test **(rev 5)**. `tests` is
  unchecked.
- `tested`: otherwise. `tests` lists every Test Case of both schemes. A mutant is caught when one
  of them is `failed`.

### Outcomes

| Run | Job | result.json |
|---|---|---|
| baseline, all tests pass | green | `tested`, all `passed` |
| a native test fails (exit 65) | green | `tested`, that test `failed` |
| patch does not apply / decode | green | `apply_failed`, no xcodebuild test |
| patched spec does not generate | green | `build_failed`, no xcodebuild test (rev 5) |
| a scheme leaves no usable result (also next to a failed test, rev 5) | green | `build_failed` |
| simulator missing (runner failure) | red | not uploaded |
| `brew install xcodegen` fails (runner failure) | red | not uploaded |
| unrecognised test result (also next to a scheme without a result, rev 5), or a duplicate test id | red | not uploaded |

## Replay rules (how the acceptance tests run the workflow)

Linux CI has no Xcode, so the tests replay the single job offline:
- Steps run in order under GitHub's rules: a default `if: success()`, status functions,
  `continue-on-error`, `steps.<id>.outcome` / `conclusion` / `outputs`, `$GITHUB_ENV`,
  `$GITHUB_OUTPUT`.
- `run:` steps run in real bash (`bash -e`, or `bash --noprofile --norc -eo pipefail` for
  `shell: bash`), with real git, base64 and python3. `working-directory` is supported.
- `actions/checkout` clones a throwaway origin:
  - `main` holds this workflow, the writer and `.github/scripts`;
  - the head under test is an older commit without the workflow and the writer, like #434's head.
    It holds a one-line marker file, a three-line context file and a one-line
    `mobile/ios/project.yml`;
  - `ref`: a SHA, a branch, or `refs/heads/…`; by default `github.sha`, the `main` commit;
  - `path` is supported; the target's contents are replaced.
- `actions/upload-artifact` records `name` and `path`; other actions are no-ops.
- `xcrun` (`simctl`, `xcresulttool get test-results tests`), `xcodebuild`, `xcodegen`, `brew`,
  `xcode-select` and `sudo` are fakes:
  - `xcodegen` exits 127 until `brew install xcodegen` has run **(rev 5)**;
  - `xcodegen generate` creates the project directory next to the spec, unless the spec carries
    the test's broken-spec marker; then it exits 1;
  - `xcodebuild test` needs that project, and creates the result bundle;
  - `simctl list` prints runtimes in the same unordered order as its JSON;
  - a case can make `brew` (or `xcode-select`) exit 1.
- Supported `${{ }}` (in `env:`, `with:`, `if:`, `continue-on-error`):
  - contexts: `inputs.*`, `github.event.inputs.*`, `github.{sha,ref,ref_name,repository,
    repository_owner,workspace,run_id,run_number,run_attempt,event_name,actor,server_url}`,
    `runner.{temp,os,arch}`, `env.*`, `steps.*`, `job.status`;
  - literals: strings, numbers, `true`, `false`, `null`;
  - operators: `== != && || !` and parentheses;
  - functions: `success() failure() always() cancelled()`.

  Anything else fails the test with a message naming the expression.

### G1 — The workflow is dispatch-only and read-only, named `agenthub-native <request_id>`, with three inputs

1. `test_workflow_is_dispatch_only_read_only_and_named_by_request_id`: the trigger, the inputs
   (the patch input not required), permissions, run-name, a single job on native-mobile's runner
   with no `concurrency`, no secrets, no `${{ }}` in `run:`, bash only, the writer is run, the head
   is checked out by its input, every checkout sets `persist-credentials: false`, and exactly one
   upload step, named `agenthub-native-result`.
2. `test_baseline_run_tests_the_head_with_both_schemes_on_udid_simulators` (replay, also G2–G4) and
   `test_patch_that_does_not_apply_is_reported_as_apply_failed` (also G3) feed the three inputs
   and check that `request_id` and the head SHA come back in `result.json`.
3. `test_the_writer_comes_from_the_workflow_revision_not_the_head` **(rev 5)**: the mutant patch
   adds a writer to the head under test that only fails. The job stays green, and `result.json`
   is `tested` with every test, written by the workflow's own writer.

### G2 — It builds and tests the head plus patch like native-mobile: xcodegen, both schemes, simulators by UDID, never AICaddieUITests

4. Baseline replay: `xcodegen` runs once with exactly `XCODEGEN_ARGS` in the head checkout, after
   `brew install xcodegen`. `xcodebuild test` runs once per scheme (`AICaddie`, `AICaddieWatch`):
   - on `mobile/ios/AICaddieNative.xcodeproj`;
   - with two different `-resultBundlePath`s;
   - with `-destination` exactly `platform=iOS Simulator,id=<newest iPhone 16>` and
     `platform=watchOS Simulator,id=<newest Series 10 (46mm)>`. In the sample list, each of these
     picks another device: the first match, the last match, text order, major-only order, UDID
     order, or a prefix name match with any tie-break **(rev 5)**;
   - with no `-only-testing`, test configuration or `-testPlan`, and no argument naming
     `AICaddieUITests`.
5. `test_failing_native_test_is_reported_and_the_job_stays_green`,
   `test_watch_only_failure_is_reported` and the writer-origin test: the patch is applied before
   generate and test (the marker file reads `"mutant"`), and both schemes still run after a
   failure.
6. `test_runner_failure_is_red_and_uploads_no_result`: no test runs on a device other than the
   expected UDID.
7. `test_build_failure_is_reported_as_build_failed`: a patched spec that does not generate gives
   `build_failed` with a green job and no `xcodebuild test` **(rev 5)**. In every other case of
   that test, both schemes run.

### G3 — `result.json` is the verdict: green on test failures, apply/build failures recorded, nothing uploaded on a runner failure

8. Failing iOS test, or failing Watch test: the job is green and `status` is `tested`.
9. Stale changed line, stale surrounding context, input that is not base64, input that is not a
   patch: green, no `xcodebuild test`, `apply_failed`, `tests: []`.
10. These runs are green with `build_failed`:
    - a spec that does not generate;
    - the Watch scheme ran no test;
    - the Watch or the iOS scheme left no bundle;
    - an unreadable bundle;
    - a tree that is not JSON;
    - **(rev 5)** an iOS failed test next to a Watch scheme that left no bundle.
11. The job is red and no `result.json` is uploaded in any artifact when:
    - no iPhone 16 is available;
    - no Series 10 (46mm) is available (unavailable ones and similar names stay in the list);
    - `brew` fails.
12. `test_result_that_cannot_be_judged_uploads_no_result`: the job is red, no `result.json` is
    uploaded in any artifact, and the writer's step ends in `failure` **(rev 5)**, when:
    - a Test Case `result` in the iOS tree is `unknown` or missing;
    - a Test Case `result` in the Watch tree is `unknown`, also when the iOS scheme left no bundle
      **(rev 5)**;
    - one test id appears in both schemes, failed in one and passed in the other;
    - **(rev 5)** one test id appears in both schemes, passed in both;
    - **(rev 5)** one test id appears twice in the iOS tree.
13. Whenever a `result.json` is expected, it is uploaded exactly once, at the root of the artifact
    `agenthub-native-result` (checked in every replay that reads `result.json`).

### G4 — The writer turns the xcresulttool tree into the result format

14. Baseline: all 8 sample tests (`AICaddieDomainTests`, `AICaddieTests`, `AICaddieWatchTests`,
    `AICaddieWatchUITests`) are listed as `passed`, with ids `<bundle>/<nodeIdentifier>`.
    - The `Device` / `Test Case Run` nodes under a case are not counted.
    - **(rev 5)** One case sits in a nested suite, with the id
      `AICaddieTests/StartRoundDiscoveryTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()`.
15. Mutant: each test gets its status. `Failed` maps to `failed`, `Skipped` to `skipped`, and
    `Expected Failure` to `passed`.
    - A Test Case without `nodeIdentifier`
      (`WatchDesignSnapshotTests/testTappingATeeStartsTheRoundWithThatTee()`) is listed under the
      fallback id
      `AICaddieWatchTests/WatchDesignSnapshotTests/testTappingATeeStartsTheRoundWithThatTee()`.
16. Cases 10 and 12 cover `build_failed`, failing closed and duplicate ids.

## Not covered by these tests

- Compatibility with agenthub's reader (artifact name, `result.json` schema), and the real
  xcresulttool output on the runner. After the merge, the console dispatches a baseline run (empty
  patch) on #434's head. It checks that agenthub reads the uploaded `agenthub-native-result`
  artifact and that its `result.json` lists the native tests, all `passed`. Only then is
  `[adversarial.native]` turned on for this project. If the reader rejects the format, that is a
  follow-up card, not a reason to relax the gate.
- The patch encoding agenthub actually sends. A baseline sends an empty patch, so it never decodes
  one. This contract fixes the input as standard base64; whether the apply step accepts line
  breaks in it is up to the implementation. I recommend that the console also dispatches one known
  mutant before turning `[adversarial.native]` on, and checks that it comes back `tested` with a
  `failed` test, not `apply_failed`.
- Behaviour on cancellation, and `timeout-minutes`. The replay never cancels a run.
- `native-mobile.yml` and app code stay untouched (card step 3). The reviewer checks this in the
  diff; a hash pin would break later cards.
- This PR changes no path under `native-mobile.yml`'s `pull_request.paths`, so the native
  acceptance gate does not apply. `.github/**` is protected, so the full gate does. CI must be
  green.

## Gate notes

- On `main`, every test fails at its first check, in the test function itself, because the
  workflow and the writer do not exist. No test is pinned, no test uses `subTest`, and no helper's
  name starts with `test`.
- I could not run the revision-5 tests in the contract sandbox: Python test runs were refused.
  I checked every new case by reading it against `b7f0936`'s workflow and writer:
  - the writer's loop over both schemes, its duplicate check and its exit code;
  - the `brew install xcodegen` step before generate;
  - the test steps' `if: steps.generate.outcome == 'success'`;
  - the exact destinations;
  - the exact-name simulator choice;
  - the tools checkout in `native-tools`.

  The revision-4 tests passed on that head in CI's `backend` job. The gate's own run is the
  authority.
