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

## Revision 7: the changes that still pass on `f353a60`

The owner's local replay on head `f353a60` found three adversarial mutants (01, 03 and 04) that
pass the revision-6 suite. **I could not see those mutants' patches.** The request gives only their
numbers, and the contract job runs offline. So I read `f353a60`'s workflow and writer against the
revision-6 tests again, change by change. These six wrong implementations still pass the
revision-6 tests, and revision 7 catches all of them:

1. **Lenient base64.** The apply step drops `validate=True` from `base64.b64decode`, or decodes
   with `base64 --decode --ignore-garbage`. A stray character outside the base64 alphabet is then
   silently dropped, and the patch applies. The revision-6 case `not base64!` still fails with
   lenient decoding, because after the garbage is dropped the length is wrong. Now caught: a valid
   mutant patch with one `*` in it must be `apply_failed`.
2. **Reduced context, `git apply -C1` / `-C2`.** The stale-context case had only one line of
   context on each side, so only `-C0` applied it. Now caught: a hunk with three lines of context
   on each side, as `git diff` writes it, whose outermost context lines are stale must be
   `apply_failed`. GNU `patch`'s default fuzz also applies that hunk.
3. **Runner steps after a failed apply.** The simulator step or the XcodeGen install step loses its
   `if: steps.apply.outcome == 'success'`. When the patch does not apply and the runner also has no
   simulator, or `brew` fails, the job turns red. Now caught: an apply failure is `apply_failed`
   with a green job, whatever the runner's state.
4. **Whitespace errors refused.** `git apply --whitespace=error` or `error-all` refuses a mutant
   whose added line ends in spaces. That makes a valid mutant invalid. Now caught: such a patch is
   applied as written, byte for byte, and the run is `tested`. The fake `xcodebuild` now records
   the marker file's raw text.
5. **Watch UI journeys skipped.** `-skip-testing:AICaddieWatchUITests` was allowed until revision 6.
   It leaves a Watch mutant that only a UI journey catches unjudged, and `native-mobile.yml` runs
   the whole `AICaddieWatch` scheme. **This changes the contract:** no `-skip-testing` at all.
6. **No job timeout.** If `timeout-minutes` is removed, a hung simulator can hold a macOS runner
   for GitHub's six-hour default. Now caught: the job sets `timeout-minutes` to a number from 30
   to 120.

**No implementation change is expected.** The head already does all six. The goals, the
interface and the result format stay as they were. New pass conditions are marked
**(rev 7)** below. If a new case fails, check it against this contract first. Fix the workflow or
the writer only if they break the contract. If the case itself is wrong (see "Gate notes"),
report it on the card. Never edit the tests.

I can't tell which of these are 01, 03 and 04. If one of the three changes a behaviour that is
not on this list, the replay should name that mutant's patch (or the line it changes). I will
then pin it.

These changes still pass, because they behave the same in every run this contract defines and on
every real runner:
- `always()` instead of `!cancelled()`, or dropping one of the write or upload step's redundant
  conditions. Whenever such a condition would matter, the job has already failed.
- `git apply --recount`. It differs only on a patch whose hunk counts are wrong, and agenthub's
  patches come from `git diff`.
- `git apply -C3`. It matches the default on `git diff`'s three lines of context.
- `git apply --3way`. It needs the stale preimage blobs. A one-commit head checkout lacks them,
  and the replay's patches carry no `index` line.
- Dropping the writer's removal of an old `result.json`. Every run starts on a fresh runner, and
  the unit test in `tests/test_agenthub_native_result.py` still covers it.
- Taking the outermost instead of the nearest test bundle. Bundles do not nest in xcresulttool's
  output, and the same unit test covers it.
- Dropping one of the two availability filters (`simctl list devices available` and
  `isAvailable`). Either one is enough.
- `ref: main` on the tools checkout. agenthub dispatches the workflow on `main`.

## History

Revision 6 (built on revision 5, for the same 0/3 report) caught:
- **Lenient apply:** `git apply --whitespace=fix`, `--ignore-whitespace` or
  `--ignore-space-change`. A patch whose context differs only by a trailing space is
  `apply_failed`.
- **xcresulttool exit code ignored:** the writer reads stdout after a non-zero exit. That is
  `build_failed`.
- **Not a tree, read as empty:** JSON without `testNodes` is `build_failed`, not zero tests.
- **Wrong fallback suite:** the fallback id uses the outermost suite or the whole suite path.
- **Duplicates skipped on a build failure:** the duplicate check runs only when the run is
  `tested`.
- **Retried or repeated tests:** `-retry-tests-on-failure`, `-test-iterations` or
  `-run-tests-until-failure`.
- **A second destination:** an extra `-destination` next to the UDID one.

Revision 5 (adversarial 0/3 on `6942203`) caught:
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
  - `timeout-minutes` is a number from 30 to 120 (a literal, not an expression) **(rev 7)**. A
    hung simulator must not hold a macOS runner for GitHub's six-hour default, and a normal
    build-and-test run needs more than a few minutes;
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
     succeeds.
     - **Apply failures.** A patch that does not decode, is not a patch, or does not apply
       cleanly is an apply failure.
     - **Strict decoding.** Decoding is strict: a character outside the standard base64 alphabet
       makes the input not decode, even when the rest is a valid patch. No `validate=False` and
       no `--ignore-garbage` **(rev 7)**. Whether line breaks are accepted is up to the
       implementation (see "Not covered").
     - **What "cleanly" means.** It means `git apply`'s default: every context line must match.
       So no fuzz and no reduced context: no `git apply -C…` and no `patch`. This holds on
       `git diff`'s three lines of context too: a hunk whose outermost context lines are stale
       does not apply **(rev 7)**.
     - **Whitespace.** A context line that differs only in whitespace does not match: no
       `--whitespace=fix`, `--ignore-whitespace` or `--ignore-space-change` **(rev 6)**.
       Whitespace errors in the added lines (trailing spaces, for example) neither block nor
       change the patch. It is applied as written, byte for byte: no `--whitespace=error`,
       `error-all` or `fix` **(rev 7)**.
     - **Carrying the failure.** The step's outcome must carry the failure.
       `continue-on-error: true` on this step is the expected way.
     - **After an apply failure.** The job goes straight to the writer: no simulator lookup, no
       XcodeGen install, no generate and no `xcodebuild test`. The verdict is `apply_failed` with
       a green job, even when the runner has no simulator or `brew` would fail **(rev 7)**.
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
     - exactly one `-destination` per scheme **(rev 6)**;
     - each with its own new `-resultBundlePath` (two different paths);
     - with the scheme's whole test action: no `-only-testing`, `-only-test-configuration`,
       `-skip-test-configuration` or `-testPlan` **(rev 5)**;
     - each test runs once: no `-retry-tests-on-failure`, `-test-iterations` or
       `-run-tests-until-failure`. A retry would let a mutant's intermittent failure pass
       **(rev 6)**.

     No `-skip-testing` at all **(rev 7; until revision 6, skipping `AICaddieWatchUITests` was
     allowed)**. The `AICaddieWatch` scheme's whole test action runs, `AICaddieWatchUITests`
     included, as in `native-mobile.yml`. Its UI journeys run against fixture screens without a
     backend, so the card's reason for leaving out `AICaddieUITests` does not apply to them. A
     Watch mutant that only a UI journey catches must not go unjudged. The `AICaddieUITests`
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
  `xcrun xcresulttool get test-results tests --path <bundle>` (Xcode 16; not `--legacy`). When
  xcresulttool exits non-zero, the scheme has no usable result, even if it printed a tree
  **(rev 6)**.
- **Tests.** Every node with `nodeType == "Test Case"` in `testNodes`, at any depth, is one test.
  A Test Case can sit in a suite nested in another suite **(rev 5)**.
  - its `id` is `<bundle>/<nodeIdentifier>`, e.g.
    `AICaddieTests/StartRoundDiscoveryTests/testOpeningPageIsCourseUnlessACourseIsPassed()`;
  - `<bundle>` is the name of the nearest `Unit test bundle` / `UI test bundle` ancestor;
  - when `nodeIdentifier` is missing, the id falls back to `<bundle>/<suite>/<name>`, with the
    nearest suite. In a nested suite that is the inner suite alone, e.g.
    `AICaddieTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()` **(rev 6)**;
  - nodes below a Test Case (`Device`, `Test Case Run`, `Failure Message`, …) are not tests.
- **Status mapping:** `Passed` and `Expected Failure` map to `passed`, `Failed` to `failed`, and
  `Skipped` to `skipped`.
- **Fail closed.** The writer exits non-zero, writes no `result.json`, and so nothing is uploaded
  or judged, when:
  - any Test Case has another or missing `result`, in either scheme. This holds even when the
    other scheme left no usable result: the writer still reads both schemes **(rev 5)**;
  - two Test Cases get the same id, in one tree or across the two schemes, whatever their statuses
    **(rev 5)**, and also when the other scheme left no usable result **(rev 6)**. Merging them
    could hide a failure behind a pass.

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
  may be missing, xcresulttool may have failed (a non-zero exit, even with a tree on stdout,
  **rev 6**), the output may not be JSON, the JSON may have no `testNodes` **(rev 6)**, or there may
  be no Test Case at all. This holds even when the other scheme has a failed test **(rev 5)**.
  `tests` is unchecked.
- `tested`: otherwise. `tests` lists every Test Case of both schemes. A mutant is caught when one
  of them is `failed`.

### Outcomes

| Run | Job | result.json |
|---|---|---|
| baseline, all tests pass | green | `tested`, all `passed` |
| a native test fails (exit 65) | green | `tested`, that test `failed` |
| patch does not apply / decode (also context off by whitespace only, rev 6; outer lines of three-line context stale, or one stray non-base64 character, rev 7) | green | `apply_failed`, no xcodebuild test |
| patch does not apply, and the runner has no simulator or `brew` fails (rev 7) | green | `apply_failed`, no xcodebuild test |
| an added line has a whitespace error (rev 7) | green | applied as written; judged like any other run |
| patched spec does not generate | green | `build_failed`, no xcodebuild test (rev 5) |
| a scheme leaves no usable result (also next to a failed test, rev 5) | green | `build_failed` |
| simulator missing (runner failure) | red | not uploaded |
| `brew install xcodegen` fails (runner failure) | red | not uploaded |
| unrecognised test result (also next to a scheme without a result, rev 5), or a duplicate test id (also next to a scheme without a result, rev 6) | red | not uploaded |

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
    It holds a one-line marker file, a three-line context file, a seven-line context file
    **(rev 7)** and a one-line `mobile/ios/project.yml`;
  - `ref`: a SHA, a branch, or `refs/heads/…`; by default `github.sha`, the `main` commit;
  - `path` is supported; the target's contents are replaced.
- `actions/upload-artifact` records `name` and `path`; other actions are no-ops.
- `xcrun` (`simctl`, `xcresulttool get test-results tests`), `xcodebuild`, `xcodegen`, `brew`,
  `xcode-select` and `sudo` are fakes:
  - `xcodegen` exits 127 until `brew install xcodegen` has run **(rev 5)**;
  - `xcodegen generate` creates the project directory next to the spec, unless the spec carries
    the test's broken-spec marker; then it exits 1;
  - `xcodebuild test` needs that project, and creates the result bundle. Every `xcodebuild` call
    records the marker file, both stripped and as raw text **(rev 7)**;
  - `xcresulttool` serves the case's tree, raw text or error; a case can make it print a tree and
    still exit 1 **(rev 6)**;
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

1. `test_workflow_is_dispatch_only_read_only_and_named_by_request_id` checks:
   - the trigger, the inputs (the patch input not required), permissions and run-name;
   - a single job on native-mobile's runner, with `timeout-minutes` from 30 to 120
     **(rev 7)** and no `concurrency`;
   - no secrets, no `${{ }}` in `run:`, and bash only;
   - the writer is run, and the head is checked out by its input;
   - every checkout sets `persist-credentials: false`;
   - exactly one upload step, named `agenthub-native-result`.
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
   - with exactly one `-destination` **(rev 6)**;
   - with no `-only-testing`, no `-skip-testing` **(rev 7)**, no test configuration and no
     `-testPlan`;
   - with no retry or iteration option **(rev 6)**;
   - with no argument naming `AICaddieUITests`.

   Every replay that runs the schemes checks all of this.
5. `test_failing_native_test_is_reported_and_the_job_stays_green`,
   `test_watch_only_failure_is_reported` and the writer-origin test: the patch is applied before
   generate and test (the marker file reads `"mutant"`), and both schemes still run after a
   failure.
   - **(rev 7)** `test_patch_with_a_whitespace_error_is_applied_as_written`: the mutant line ends
     in two spaces. Both schemes test the marker file with exactly that line, spaces included.
     The job is green, and `result.json` is `tested` with every test `passed`.
6. `test_runner_failure_is_red_and_uploads_no_result`: no test runs on a device other than the
   expected UDID.
7. `test_build_failure_is_reported_as_build_failed`: a patched spec that does not generate gives
   `build_failed` with a green job and no `xcodebuild test` **(rev 5)**. In every other case of
   that test, both schemes run.

### G3 — `result.json` is the verdict: green on test failures, apply/build failures recorded, nothing uploaded on a runner failure

8. Failing iOS test, or failing Watch test: the job is green and `status` is `tested`.
9. Each of these is green, with no `xcodebuild test`, `apply_failed` and `tests: []`:
   - a stale changed line;
   - stale surrounding context;
   - **(rev 6)** surrounding context that differs only by a trailing space;
   - **(rev 7)** a hunk with three lines of context on each side whose outermost line on each
     side is stale;
   - input that is not base64;
   - **(rev 7)** a valid mutant patch with one `*` inserted into its base64;
   - input that is not a patch;
   - **(rev 7)** a stale patch, when no iPhone 16 is available;
   - **(rev 7)** a stale patch, when `brew` fails.
10. These runs are green with `build_failed`:
    - a spec that does not generate;
    - the Watch scheme ran no test;
    - the Watch or the iOS scheme left no bundle;
    - an unreadable bundle;
    - a tree that is not JSON;
    - **(rev 6)** xcresulttool printed a whole passing Watch tree but exited 1;
    - **(rev 6)** the Watch output is JSON without `testNodes`;
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
    - **(rev 5)** one test id appears twice in the iOS tree;
    - **(rev 6)** one test id appears twice in the iOS tree, and the Watch scheme left no bundle.
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
    - **(rev 6)** The nested iOS case has no `nodeIdentifier` either. It is listed under the
      nearest suite, `AICaddieTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()`, as
      `skipped`.
16. Cases 10 and 12 cover `build_failed`, failing closed and duplicate ids.

## Not covered by these tests

- Compatibility with agenthub's reader (artifact name, `result.json` schema), and the real
  xcresulttool output on the runner. After the merge, the console dispatches a baseline run (empty
  patch) on #434's head. It checks that agenthub reads the uploaded `agenthub-native-result`
  artifact and that its `result.json` lists the native tests, all `passed`. Only then is
  `[adversarial.native]` turned on for this project. If the reader rejects the format, that is a
  follow-up card, not a reason to relax the gate.
- The patch encoding agenthub actually sends. A baseline sends an empty patch, so it never decodes
  one. This contract fixes the input as strict standard base64 (rev 7). Whether the apply step
  accepts line breaks in it is up to the implementation; `f353a60`'s `validate=True` refuses them. I recommend that the console also dispatches one known
  mutant before turning `[adversarial.native]` on, and checks that it comes back `tested` with a
  `failed` test, not `apply_failed`.
- Behaviour on cancellation or on reaching the timeout. The replay never cancels a run; only the
  `timeout-minutes` value is checked, statically (rev 7).
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
  - **Strict decoding.** The apply step calls `base64.b64decode(…, validate=True)`, which raises on
    the `*`. The step fails, and the writer reports `apply_failed`.
  - **Stale outer context.** `git apply` keeps every context line by default (no `-C`), so the
    outer-stale three-line-context hunk does not apply. With `-C1` or `-C2`, git trims one line
    from each end and applies it at line 2.
  - **Whitespace errors.** `--whitespace=nowarn` applies the trailing-space line as written.
  - **Order after a failed apply.** The simulator, install and generate steps run only
    `if: steps.apply.outcome == 'success'`, so a failed apply never reaches `simctl` or `brew`.
    The write step still runs on `steps.apply.outcome == 'failure'`.
  - **Scheme flags.** The test steps pass no `-skip-testing`.
  - **Timeout.** The job sets `timeout-minutes: 60`.

  The gate's own run is the authority. If a revision-7 case fails on that head, the case is
  probably wrong, not the implementation. Report it on the card and I will fix the test.
