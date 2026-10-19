# Card #440 — agenthub native mutant workflow (Swift mutants judged by real native tests)

agenthub dispatches one workflow run per mutant on CI. Each run tests the head under test, plus the
mutant patch, with the real native tests. It then uploads `result.json`. agenthub counts a mutant
as caught when a native test fails. The gate stays as strict as before:
- at least three distinct mutants, all caught;
- an apply or build failure is invalid;
- a red baseline judges nothing.

Touches: `.github/workflows/agenthub-native-mutant.yml`, `.github/scripts/agenthub_native_result.py`, `tests/test_agenthub_native_result.py`, `tests/acceptance/test_card_440_native_mutant_workflow.py`, `.agent/contracts/card-440.md`

Acceptance tests: `tests/acceptance/test_card_440_native_mutant_workflow.py` (10 tests). Codex
must not edit `tests/acceptance/`.

## Revision 7: what revision 6 still let through

The gate's adversarial check failed again, on head `f353a60` (revision 6). I still could not read
the gate report. Revision 6 published a list of changes it left uncaught, and an adversary can read
that list. Revision 7 makes most of those changes observable. It also closes other gaps I found by
reading `f353a60`'s workflow and writer against the tests again.

The goals, the interface and the result format are unchanged. The new pass conditions are marked
**(rev 7)** below. They state what the head already does, so **no implementation change is
expected**. If a new case fails on the head, check the case against this contract first. Fix the
workflow or the writer only where they break the contract. If the case itself is wrong, report it
on the card. Never edit the tests.

Now caught:
- **Cancellation ignored:** `always()` or `!failure()` instead of `!cancelled()` on a step after the
  tests. The replay can now cancel a run, either while the iOS scheme tests or right after the
  writer. After a cancellation, no further step runs and nothing is uploaded.
- **Writer from the branch tip:** checking the tools out with `ref: main`, `refs/heads/main` or
  `${{ github.ref }}`. In the replay, `main` now has a later commit whose writer only fails. The
  writer must come from the dispatched revision, `github.sha`.
- **`git apply --recount`:** a patch whose hunk counts are wrong must be `apply_failed`.
- **Lenient base64:** decoding without `validate=True`, or with `base64 --ignore-garbage`. Valid
  base64 with one stray `*` in it must be `apply_failed`.
- **Rewritten added lines:** `git apply --whitespace=error` (refuses the patch) or
  `--whitespace=fix` (strips the space). A mutant whose added line ends in a space must apply and be
  tested exactly as sent.
- **Work after an apply failure:** dropping the `if:` of the simulator, install or generate step.
  After an apply failure, no simulator is listed and nothing is installed, generated or built.
- **All simulators listed:** dropping `available` from `xcrun simctl list devices available -j`.
- **Extra xcodebuild arguments:** anything beyond `test`, `-project`, `-scheme`, `-destination`,
  `-resultBundlePath` and `-skip-testing:AICaddieWatchUITests`. That covers build settings (for
  example `OTHER_SWIFT_FLAGS=…`), `-parallel-testing-…`, `-test-timeouts-enabled`,
  `-maximum-test-execution-time-allowance`, `-quiet`, and also the retry and destination options
  that revision 6 listed one by one.
- **Short timeouts:** a job `timeout-minutes` below 60, or a `timeout-minutes` on any step.
- **Outermost bundle:** in the mutant tree, the Watch UI test bundle now sits inside the Watch unit
  test bundle. Its test must keep its own bundle.
- **Loose result matching:** `Mixed`, or `passed` in lower case, must fail closed. That rules out
  case folding, trimming and extra statuses.
- **Unidentifiable test dropped:** a failed Test Case with neither `nodeIdentifier` nor `name` must
  fail closed, not be skipped.

Some changes stay uncaught. Each one behaves the same in every run this contract defines, and on a
real runner:
- **Dropping `!cancelled() &&` from the write or the upload step.** The implicit `success()` that
  then applies also skips the step after a cancellation. On every path where the step would run, no
  earlier step has failed the job.
- **Dropping one of the write step's conditions on `simulators`, `install` or `generate`.** Those
  three steps share one `if:`, so each condition implies the others.
- **Dropping the upload's `steps.write_result.outcome == 'success'`, its
  `if-no-files-found: error`, or both.** Without a result file, `upload-artifact@v4` creates no
  artifact.
- **Dropping the writer's removal of an old `result.json`.** Every run starts on a fresh runner,
  and the upload runs only after the writer succeeded. The unit test in
  `tests/test_agenthub_native_result.py` covers it.
- **Dropping the `isAvailable` check.** `simctl list devices available`, now required, lists
  available devices only.
- **`git apply --3way` or `--index`.** agenthub's patches are made on the head under test. In a
  depth-1 checkout, a 3-way merge applies exactly when a direct apply does. `--index` applies the
  same on a clean checkout.
- **Adding `-skip-testing:AICaddieWatchUITests` on the Watch scheme.** The contract allows it.
- **Removing the job's `timeout-minutes`.** GitHub's default is 360 minutes.
- **Swapping the two bundles passed to the writer.** The order of `tests` is not part of the
  format.
- **The writer recursing below a Test Case.** Nodes below a Test Case are never Test Cases.

If the gate reports a survivor that is not on this list, it should name it. I will then either pin
the behaviour it changes or record it here as equivalent.

## History

Revision 6 (the gate's adversarial check failed on `f353a60`) caught:
- lenient apply (`--whitespace=fix`, `--ignore-whitespace`, `--ignore-space-change`);
- an xcresulttool exit code that is ignored;
- JSON without `testNodes`;
- the wrong fallback suite;
- duplicates skipped on a build failure;
- retried or repeated tests;
- a second destination.

Revision 5 (adversarial 0/3 on `6942203`) caught:
- the writer stopping at the first scheme without a result;
- a failed test hiding a build failure;
- merged duplicates;
- a writer that exits 0 without a result;
- Test Cases read at a fixed depth;
- prefix name matches for simulators;
- a narrowed run;
- tests after a failed generate;
- a missing XcodeGen install;
- the writer from the head.

Earlier revisions:
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
  - no job-level `if:` or `continue-on-error`;
  - **(rev 7)** if the job sets `timeout-minutes`, it is a literal integer of at least 60. No step
    sets `timeout-minutes`: a test step cut short leaves a partial result bundle, which can read as
    a pass.
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
    writer does not change which writer runs.
  - **(rev 7)** The workflow's own revision is the dispatched commit, `github.sha`, not the tip of
    `main`. `main` may have moved on since the dispatch. Use `actions/checkout` without `ref`, or
    with `ref: ${{ github.sha }}`; not `ref: main` or `${{ github.ref }}`.
  - One way to do this: check out the dispatched revision into a separate `path:`, and check out
    the head into another one.
  - `actions/checkout` replaces whatever its `path` held. Do not check the head out over a
    directory that holds the tools.
- Order of the steps:
  1. **Apply.** Decode the patch (`base64 --decode` or python3) and `git apply` it at the root of
     the head checkout. An empty patch is a baseline: there is nothing to apply, and the step
     succeeds. A patch that does not decode, is not a patch, or does not apply cleanly is an
     apply failure.
     - **Decode.** The input is strict standard base64: a character outside the base64 alphabet
       fails the decode, even if the rest is valid **(rev 7)**. Whether line breaks are accepted
       is up to the implementation.
     - **Apply cleanly.** This means `git apply`'s default behaviour:
       - every context line must match: no fuzz and no reduced context (`git apply -C…`, `patch`);
       - a context line that differs only in whitespace does not match either: no
         `--whitespace=fix`, `--ignore-whitespace` or `--ignore-space-change`;
       - the hunk counts must be right: no `--recount` **(rev 7)**;
       - added lines are applied exactly as sent, trailing whitespace included: no
         `--whitespace=error`, `error-all` or `fix` **(rev 7)**.
     - **On failure.** The step's outcome must carry the failure (`continue-on-error: true` on
       this step is the expected way). When the apply fails, nothing else runs before the writer:
       no simulator listing, no `brew`, no `xcodegen`, no `xcodebuild` **(rev 7)**.
  2. **Simulators by UDID.** Pick the simulators from
     `xcrun simctl list devices available -j`. The JSON listing includes `available` **(rev 7)**.
     - the `iPhone 16` on the newest iOS runtime that has one available;
     - the `Apple Watch Series 10 (46mm)` on the newest watchOS runtime that has one available.

     "Newest" compares the runtime's `(major, minor)` numerically: `watchOS-11-10` is newer than
     `watchOS-11-5`. Device names match exactly, not by prefix or substring: `iPhone 16 Plus` is
     not `iPhone 16`. The order of runtimes and devices in the listing means nothing. Parse the JSON
     with python3; the acceptance environment does not guarantee `jq`. If either device is missing,
     the step fails. That is a runner failure (see "Outcomes").
  3. **Generate.** Install XcodeGen with `brew install xcodegen`, as `native-mobile.yml` does: the
     runner image does not ship it. If the install fails, that is a runner failure. Then run
     `xcodegen generate --spec mobile/ios/project.yml --project-root .`, exactly these arguments,
     at the root of the head checkout, after the patch is applied. If `xcodegen generate` fails
     (the patched spec does not generate), that is a build failure of the mutant: the job stays
     green, no `xcodebuild test` runs, and `result.json` says `build_failed`.
  4. **Test.** One `xcodebuild test` per scheme, at the root of the head checkout:
     - `-project mobile/ios/AICaddieNative.xcodeproj`;
     - `-scheme AICaddie` with `-destination "platform=iOS Simulator,id=<iOS UDID>"`;
     - `-scheme AICaddieWatch` with `-destination "platform=watchOS Simulator,id=<Watch UDID>"`;
     - each destination has exactly these two fields: no `name=`, no `OS=`;
     - each scheme with its own new `-resultBundlePath` (two different paths);
     - **(rev 7)** nothing else. Each command line holds exactly `test`, `-project`, `-scheme`,
       `-destination` and `-resultBundlePath`, once each, in any order. On the Watch scheme only,
       it may add `-skip-testing:AICaddieWatchUITests`. No build settings, `-only-testing`, test
       plans or configurations, retries, iterations, parallel-testing or timeout options, `-quiet`,
       `-derivedDataPath`, or any other option.

     The Watch scheme's UI journeys run against fixture screens without a backend, so keeping them
     is allowed. The `AICaddieUITests` scheme or target never runs. A test failure (exit 65) keeps
     the job green (`continue-on-error: true` on the test steps), and the Watch scheme still runs
     after an iOS failure. Use `xcodebuild test`, not `build-for-testing` / `test-without-building`.
  5. **Write.** `python3 <tools checkout>/.github/scripts/agenthub_native_result.py …` writes
     `result.json`. It runs after an apply, generate, build or test failure. It does not run, or
     at least uploads nothing, after a runner failure.
  6. **Upload.** Exactly one `actions/upload-artifact` step, with:
     - `name: agenthub-native-result`, as a literal (no expression);
     - one `path`: the `result.json` file itself, or a directory with `result.json` directly in
       it, so that `result.json` is at the artifact's root.

     No other step uploads an artifact.
- **Cancellation (rev 7).** Once the run is cancelled (agenthub cancels it, or the job times out),
  no further step runs: not the other scheme, not the writer, not the upload. Write the conditions
  of the steps after the tests with `!cancelled()`, not `always()`. A cancelled run uploads no
  `result.json`.

### Result writer `.github/scripts/agenthub_native_result.py`

- Python 3 standard library only. It reads each scheme's bundle with
  `xcrun xcresulttool get test-results tests --path <bundle>` (Xcode 16; not `--legacy`). When
  xcresulttool exits non-zero, the scheme has no usable result, even if it printed a tree.
- **Tests.** Every node with `nodeType == "Test Case"` in `testNodes`, at any depth, is one test.
  A Test Case can sit in a suite nested in another suite.
  - its `id` is `<bundle>/<nodeIdentifier>`, e.g.
    `AICaddieTests/StartRoundDiscoveryTests/testOpeningPageIsCourseUnlessACourseIsPassed()`;
  - `<bundle>` is the name of the nearest `Unit test bundle` / `UI test bundle` ancestor. Real
    output does not nest bundles, but if one bundle sits in another, the inner one counts
    **(rev 7)**;
  - when `nodeIdentifier` is missing, the id falls back to `<bundle>/<suite>/<name>`, with the
    nearest suite. In a nested suite that is the inner suite alone, e.g.
    `AICaddieTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()`;
  - nodes below a Test Case (`Device`, `Test Case Run`, `Failure Message`, …) are not tests.
- **Status mapping:** `Passed` and `Expected Failure` map to `passed`, `Failed` to `failed`, and
  `Skipped` to `skipped`. The `result` must be exactly one of these four strings: no case folding,
  no trimming **(rev 7)**.
- **Fail closed.** The writer exits non-zero, writes no `result.json`, and so nothing is uploaded
  or judged, when:
  - any Test Case has another or missing `result`, in either scheme. This holds even when the
    other scheme left no usable result: the writer still reads both schemes;
  - a Test Case has no usable id: no `nodeIdentifier` and no `name`, or no suite or bundle to
    build the fallback from **(rev 7)**. Dropping it could hide a failure;
  - two Test Cases get the same id, in one tree or across the two schemes, whatever their statuses,
    and also when the other scheme left no usable result. Merging them could hide a failure behind
    a pass.

  The step that runs the writer must therefore end in `failure`.

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
  may be missing, xcresulttool may have failed (a non-zero exit, even with a tree on stdout), the
  output may not be JSON, the JSON may have no `testNodes`, or there may be no Test Case at all.
  This holds even when the other scheme has a failed test. `tests` is unchecked.
- `tested`: otherwise. `tests` lists every Test Case of both schemes. A mutant is caught when one
  of them is `failed`.

### Outcomes

| Run | Job | result.json |
|---|---|---|
| baseline, all tests pass | green | `tested`, all `passed` |
| a native test fails (exit 65) | green | `tested`, that test `failed` |
| patch does not apply or decode (also: whitespace-only context, wrong hunk counts, a stray character in the base64) | green | `apply_failed`, nothing selected, installed, generated or built (rev 7) |
| patched spec does not generate | green | `build_failed`, no xcodebuild test |
| a scheme leaves no usable result (also next to a failed test) | green | `build_failed` |
| simulator missing (runner failure) | red | not uploaded |
| `brew install xcodegen` fails (runner failure) | red | not uploaded |
| unrecognised test result, a test without a usable id (rev 7), or a duplicate test id; also next to a scheme without a result | red | not uploaded |
| the run is cancelled, during the tests or after the writer (rev 7) | cancelled | not uploaded; no later step runs |

## Replay rules (how the acceptance tests run the workflow)

Linux CI has no Xcode, so the tests replay the single job offline:
- Steps run in order under GitHub's rules: a default `if: success()`, status functions,
  `continue-on-error`, `steps.<id>.outcome` / `conclusion` / `outputs`, `$GITHUB_ENV`,
  `$GITHUB_OUTPUT`.
- `run:` steps run in real bash (`bash -e`, or `bash --noprofile --norc -eo pipefail` for
  `shell: bash`), with real git, base64 and python3. `working-directory` is supported.
- `actions/checkout` clones a throwaway origin:
  - the head under test is an older commit without the workflow and the writer, like #434's head.
    It holds a one-line marker file, a three-line context file and a one-line
    `mobile/ios/project.yml`;
  - the dispatched `main` commit (`github.sha`) holds this workflow, the writer and
    `.github/scripts`;
  - **(rev 7)** a later `main` commit, the tip of the branch, replaces the writer with one that
    only fails;
  - `ref`: a SHA, a branch, or `refs/heads/…`; by default `github.sha`, the dispatched commit;
  - `path` is supported; the target's contents are replaced.
- `actions/upload-artifact` records `name` and the files under `path`. **(rev 7)** A path without
  files creates no artifact, as `upload-artifact@v4` does, and fails the step with
  `if-no-files-found: error`. Other actions are no-ops.
- `xcrun` (`simctl`, `xcresulttool get test-results tests`), `xcodebuild`, `xcodegen`, `brew`,
  `xcode-select` and `sudo` are fakes:
  - `xcodegen` exits 127 until `brew install xcodegen` has run;
  - `xcodegen generate` creates the project directory next to the spec, unless the spec carries
    the test's broken-spec marker; then it exits 1;
  - `xcodebuild test` needs that project, and creates the result bundle. It records the marker
    file's text with its trailing spaces **(rev 7)**;
  - `xcresulttool` serves the case's tree, raw text or error; a case can make it print a tree and
    still exit 1;
  - `simctl list` prints runtimes in the same unordered order as its JSON;
  - a case can make `brew` (or `xcode-select`) exit 1.
- **(rev 7) Cancellation.** A case can cancel the run while a scheme tests (the fake `xcodebuild`
  reports it, and that step ends `cancelled`) or right after the last step whose `run:` names the
  writer. From then on, `cancelled()` is true, `success()` false, and a condition without a status
  function is false.
- Supported `${{ }}` (in `env:`, `with:`, `if:`, `continue-on-error`):
  - contexts: `inputs.*`, `github.event.inputs.*`, `github.{sha,ref,ref_name,repository,
    repository_owner,workspace,run_id,run_number,run_attempt,event_name,actor,server_url}`,
    `runner.{temp,os,arch}`, `env.*`, `steps.*`, `job.status`;
  - literals: strings, numbers, `true`, `false`, `null`;
  - operators: `== != && || !` and parentheses;
  - functions: `success() failure() always() cancelled()`.

  Anything else fails the test with a message naming the expression.

### G1 — The workflow is dispatch-only and read-only, named `agenthub-native <request_id>`, with three inputs

1. `test_workflow_is_dispatch_only_read_only_and_named_by_request_id` checks:
   - the trigger and the inputs (the patch input not required);
   - permissions and run-name;
   - a single job on native-mobile's runner, with no `concurrency`;
   - **(rev 7)** a job `timeout-minutes`, if set, of at least 60, and none on a step;
   - no secrets, no `${{ }}` in `run:`, bash only;
   - the writer is run, and the head is checked out by its input;
   - every checkout sets `persist-credentials: false`;
   - exactly one upload step, named `agenthub-native-result`.
2. `test_baseline_run_tests_the_head_with_both_schemes_on_udid_simulators` (replay, also G2–G4) and
   `test_patch_that_does_not_apply_is_reported_as_apply_failed` (also G3) feed the three inputs
   and check that `request_id` and the head SHA come back in `result.json`.
3. `test_the_writer_comes_from_the_workflow_revision_not_the_head`: the mutant patch adds a writer
   that only fails to the head under test. The job stays green, and `result.json` is `tested` with
   every test, written by the workflow's own writer.
4. **(rev 7)** In every replay, the tip of `main` carries a writer that only fails. The baseline and
   every other replay that expects a `result.json` therefore check that the writer comes from
   `github.sha`.

### G2 — It builds and tests the head plus patch like native-mobile: xcodegen, both schemes, simulators by UDID, never AICaddieUITests

5. Baseline replay:
   - `xcodegen` runs once with exactly `XCODEGEN_ARGS` in the head checkout, after
     `brew install xcodegen`;
   - **(rev 7)** there is a JSON device listing (`simctl list devices … -j`), and every such
     listing includes `available`;
   - `xcodebuild test` runs once per scheme (`AICaddie`, `AICaddieWatch`), on
     `mobile/ios/AICaddieNative.xcodeproj`, with two different `-resultBundlePath`s;
   - `-destination` is exactly `platform=iOS Simulator,id=<newest iPhone 16>` and
     `platform=watchOS Simulator,id=<newest Series 10 (46mm)>`. In the sample list, each of these
     picks another device: the first match, the last match, text order, major-only order, UDID
     order, or a prefix name match with any tie-break;
   - **(rev 7)** each command line holds only `test`, `-project`, `-scheme`, `-destination` and
     `-resultBundlePath`, once each, plus `-skip-testing:AICaddieWatchUITests` on the Watch scheme
     at most. No argument names `AICaddieUITests`.
6. `test_failing_native_test_is_reported_and_the_job_stays_green`,
   `test_watch_only_failure_is_reported` and the writer-origin test check that the patch is applied
   before generate and test (the marker file reads `"mutant"`), and that both schemes still run
   after a failure. **(rev 7)** In the Watch-only test, the mutant's added line ends in a space,
   and the tested marker keeps it.
7. `test_runner_failure_is_red_and_uploads_no_result`: no test runs on a device other than the
   expected UDID.
8. `test_build_failure_is_reported_as_build_failed`: a patched spec that does not generate gives
   `build_failed` with a green job and no `xcodebuild test`. In every other case of that test, both
   schemes run.
9. **(rev 7)** `test_patch_that_does_not_apply_is_reported_as_apply_failed`: after an apply failure
   there is no `simctl` call, `brew`, `xcodegen` or `xcodebuild`.

### G3 — `result.json` is the verdict: green on test failures, apply/build failures recorded, nothing uploaded on a runner failure

10. Failing iOS test, or failing Watch test: the job is green and `status` is `tested`.
11. Each of these runs is green, runs no `xcodebuild test`, and gives `apply_failed` with
    `tests: []`:
    - a stale changed line;
    - stale surrounding context;
    - surrounding context that differs only by a trailing space;
    - **(rev 7)** hunk counts that do not match the hunk;
    - input that is not base64;
    - **(rev 7)** valid base64 with one stray `*`;
    - input that is not a patch.
12. These runs are green with `build_failed`:
    - a spec that does not generate;
    - the Watch scheme ran no test;
    - the Watch or the iOS scheme left no bundle;
    - an unreadable bundle;
    - a tree that is not JSON;
    - xcresulttool printed a whole passing Watch tree but exited 1;
    - the Watch output is JSON without `testNodes`;
    - an iOS failed test next to a Watch scheme that left no bundle.
13. The job is red and no `result.json` is uploaded in any artifact when:
    - no iPhone 16 is available;
    - no Series 10 (46mm) is available (unavailable ones and similar names stay in the list);
    - `brew` fails.
14. `test_result_that_cannot_be_judged_uploads_no_result`: the job is red, no `result.json` is
    uploaded in any artifact, and the writer's step ends in `failure`, when:
    - a Test Case `result` in the iOS tree is `unknown` or missing;
    - **(rev 7)** a Test Case `result` in the iOS tree is `Mixed`, or `passed` in lower case;
    - **(rev 7)** a failed iOS Test Case has neither `nodeIdentifier` nor `name`;
    - a Test Case `result` in the Watch tree is `unknown`, also when the iOS scheme left no bundle;
    - one test id appears in both schemes, failed in one and passed in the other;
    - one test id appears in both schemes, passed in both;
    - one test id appears twice in the iOS tree, also when the Watch scheme left no bundle.
15. **(rev 7)** `test_cancelled_run_uploads_no_result` covers a run cancelled while the iOS scheme
    tests, and a run cancelled right after the writer has succeeded. In both:
    - the run ends cancelled;
    - no step after the cancellation runs (not the Watch scheme, the writer or the upload);
    - no `result.json` is uploaded.
16. Whenever a `result.json` is expected, it is uploaded exactly once, at the root of the artifact
    `agenthub-native-result` (checked in every replay that reads `result.json`).

### G4 — The writer turns the xcresulttool tree into the result format

17. Baseline: all 8 sample tests (`AICaddieDomainTests`, `AICaddieTests`, `AICaddieWatchTests`,
    `AICaddieWatchUITests`) are listed as `passed`, with ids `<bundle>/<nodeIdentifier>`.
    - The `Device` / `Test Case Run` nodes under a case are not counted.
    - One case sits in a nested suite, with the id
      `AICaddieTests/StartRoundDiscoveryTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()`.
18. Mutant: each test gets its status. `Failed` maps to `failed`, `Skipped` to `skipped`, and
    `Expected Failure` to `passed`.
    - A Test Case without `nodeIdentifier`
      (`WatchDesignSnapshotTests/testTappingATeeStartsTheRoundWithThatTee()`) is listed under the
      fallback id
      `AICaddieWatchTests/WatchDesignSnapshotTests/testTappingATeeStartsTheRoundWithThatTee()`.
    - The nested iOS case has no `nodeIdentifier` either. It is listed under the nearest suite,
      `AICaddieTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()`, as `skipped`.
    - **(rev 7)** The `AICaddieWatchUITests` bundle sits inside the `AICaddieWatchTests` bundle.
      Its test is still listed as
      `AICaddieWatchUITests/WatchHolePagesUITests/testVerticalSwipesWalkTheThreeHolePagesAndBack()`.
19. Cases 12 and 14 cover `build_failed`, failing closed, unusable ids and duplicate ids.

## Not covered by these tests

- Compatibility with agenthub's reader (artifact name, `result.json` schema), and the real
  xcresulttool output on the runner. After the merge, the console dispatches a baseline run (empty
  patch) on #434's head. It checks that agenthub reads the uploaded `agenthub-native-result`
  artifact and that its `result.json` lists the native tests, all `passed`. Only then is
  `[adversarial.native]` turned on for this project. If the reader rejects the format, that is a
  follow-up card, not a reason to relax the gate.
- The patch encoding agenthub actually sends. A baseline sends an empty patch, so it never decodes
  one. This contract fixes the input as strict standard base64; whether the apply step accepts line
  breaks in it is up to the implementation. I recommend that the console also dispatches one known
  mutant before turning `[adversarial.native]` on, and checks that it comes back `tested` with a
  `failed` test, not `apply_failed`.
- How the real runner reports a cancellation or a job timeout. The replay models GitHub's
  documented status functions only.
- `native-mobile.yml` and app code stay untouched (card step 3). The reviewer checks this in the
  diff; a hash pin would break later cards.
- This PR changes no path under `native-mobile.yml`'s `pull_request.paths`, so the native
  acceptance gate does not apply. `.github/**` is protected, so the full gate does. CI must be
  green.

## Gate notes

- On `main`, every test fails at its first check, in the test function itself, because the
  workflow and the writer do not exist. No test is pinned, no test uses `subTest`, and no helper's
  name starts with `test`.
- The revision-6 tests passed on head `f353a60` in CI's `backend` job.
- I could not run the revision-7 tests in the contract sandbox: Python runs were refused again.
  I checked every new case by reading it against `f353a60`'s workflow and writer:
  - the tools checkout has no `ref`, so it gets `github.sha`, not the later `main` commit;
  - every step after the tests has `!cancelled()` or an implicit `success()`;
  - the apply step's `b64decode(…, validate=True)` and plain `git apply --whitespace=nowarn`:
    a stray `*` fails the decode, wrong hunk counts are a corrupt patch, and a trailing space on an
    added line is kept;
  - the simulator, install and generate steps are guarded by `steps.apply.outcome == 'success'`;
  - the simulator listing is `xcrun simctl list devices available -j`;
  - the test steps pass only `test`, `-project`, `-scheme`, `-destination` and
    `-resultBundlePath`;
  - the job's `timeout-minutes: 60`, and no step timeout;
  - `test_cases` keeps the nearest bundle, maps `result` by exact match, and raises on a Test Case
    without `nodeIdentifier` or `name`.

  The gate's own run is the authority. If a revision-7 case fails on that head, the case is
  probably wrong, not the implementation. Report it on the card and I will fix the test.
