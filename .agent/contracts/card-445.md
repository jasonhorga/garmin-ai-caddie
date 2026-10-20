# Card #445 — the native mutant workflow follows agenthub's result interface

The first real native gate run on #434 ended as `artifact missing or invalid`. That run was five
dispatches, all green on CI. The #440 workflow uploads `agenthub-native-result` with the keys
`request_id`, `head_sha`, `status` and `tests`, but agenthub's reader takes something else. This card
changes the artifact and `result.json` to what the reader accepts. The #440 workflow's behaviour stays
the same: apply, generate, test, the verdict rules, failing closed, and cancellation.

Touches: `.github/workflows/agenthub-native-mutant.yml`, `.github/scripts/agenthub_native_result.py`, `tests/test_agenthub_native_result.py`, `tests/acceptance/test_card_440_native_mutant_workflow.py`, `tests/acceptance/test_card_445_native_result_interface.py`, `.agent/contracts/card-440.md`, `.agent/contracts/card-445.md`

Acceptance tests (Claude-owned; Codex must not edit `tests/acceptance/`):
- `tests/acceptance/test_card_445_native_result_interface.py` (6 tests);
- `tests/acceptance/test_card_440_native_mutant_workflow.py` (10 tests). These are updated to this
  interface and share the stricter `_result` check. Their G tags now name this card's goals, which
  keep #440's numbering.

## About agenthub's reference files

The card asks for agenthub's `templates/native-mutant/agenthub_native_result.py` and
`agenthub-native-mutant.yml` at e86a6d3, copied unchanged. As with #440, neither this contract job nor
the offline implementation session can read the agenthub repository. If your session can read those
files, use them as the starting point. Either way, **these tests and this contract decide**:
- **The output format below is agenthub's.** It is quoted from the card, which takes it from
  agenthub's `docs/fixes/B27-NATIVE-MUTANTS.md` G4. Do not change it.
- **The xcresulttool rules stay #440's.** These are the test ids, the status mapping, failing closed,
  and `build_failed` for a scheme without a usable result. They are what this runner's output needs,
  and the card allows this change ("If this runner's xcresulttool output needs a change, keep the
  output format above exactly and say why in the PR"). Say so in the PR body.
- **Writer CLI (recommended, not tested).** Use the reference's command line, `--request-id --head
  --patch --stage [--tests-json ...] --out`. The tests run whatever the workflow runs, so the CLI,
  the step layout, and the split of work between the workflow and the writer are all free. For
  example, the workflow may call xcresulttool and pass its output with `--tests-json`.

## Interface

### Dispatch inputs (unchanged)

The inputs are exactly `request_id` (required), `head_sha` (required) and `patch_b64` (not required;
empty for a baseline), all `string`. agenthub's #434 dispatches were accepted with these names, and
GitHub refuses a dispatch with unknown inputs. Do not rename them. `run-name` stays
`agenthub-native ${{ inputs.request_id }}`.

### Input validation (new)

The job fails before anything is generated or tested, and uploads no artifact, when:
- `request_id` is empty, or holds whitespace, or holds a character an artifact name cannot carry
  (`" : < > | * ? \ /`, CR, LF);
- `head_sha` is not exactly 40 lower-case hex characters.

The workflow must accept every request id made of ASCII letters, digits, `.`, `_` and `-`, up to
100 characters. The tests use `card440-<hex>` and `card445_base.<hex>`. Other characters are up to
the implementation.

`patch_b64` input that is not strict standard base64 has two allowed outcomes:
- validation refuses it (red job, no artifact);
- the apply step reports it as `apply_failed`, as in #440.

Either way it is never tested. Validation runs in a `run:` step, with the inputs passed through
`env:`, as for every step (#440's rules).

### Artifact (new)

- There is exactly one `actions/upload-artifact` step:
  - `name: agenthub-native-${{ inputs.request_id }}`, exactly this text;
  - `if-no-files-found: error`;
  - one `path`.
- The artifact holds only `result.json`, at its root. Upload the file itself, or a directory that
  holds nothing else. Never upload xcresulttool dumps, patches or logs.
- No artifact at all is uploaded on any of these:
  - a runner failure (no simulator, `brew install xcodegen` fails);
  - an unjudgeable result (#440's fail-closed cases);
  - invalid input;
  - a cancelled run.
- The string `agenthub-native-result` no longer appears in the workflow.

### `result.json` (new)

```json
{
  "request_id": "<request_id input>",
  "head": "<head_sha input>",
  "patch_sha256": "<sha256 hex of the decoded patch bytes>",
  "stage": "tested | apply_failed | build_failed",
  "tests": [{"id": "<bundle>/<nodeIdentifier>", "status": "passed | failed | error | skipped"}]
}
```

- **Keys:** exactly these five. No extra keys, and no `head_sha` or `status`.
- **Test entries:** each one has exactly `id` and `status`.
- **`patch_sha256`:** the lower-case sha256 hex digest of the base64-decoded patch bytes, exactly as
  sent, with trailing whitespace and the final newline kept. A baseline (empty input) gives
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. It is never the digest of
  the base64 text, of a re-encoded or stripped patch, or of `git diff` output. When the input is not
  strict base64 and is reported as `apply_failed`, it is any 64-character lower-case hex string.
- **`stage`:** uses #440's rules, renamed from `status`:
  - `apply_failed`: the patch did not decode or apply;
  - `build_failed`: generate failed, or some scheme left no usable result;
  - `tested`: otherwise.
- **`tests`:** empty unless `stage` is `tested`. A `build_failed` run lists no tests, not even the
  other scheme's. Under `tested`, every Test Case of both schemes appears, with #440's ids (unique,
  non-empty) and #440's status mapping:
  - `Passed` and `Expected Failure` become `passed`;
  - `Failed` becomes `failed`;
  - `Skipped` becomes `skipped`.

  `error` is valid in the format, but #440's writer never needs it. Any other xcresult result still
  fails closed. Do not map it to `error`: that would turn an unknown result into a judged one.
- **Writer source:** the writer still comes from the dispatched revision (`github.sha`), never from
  the head under test or a later `main`. This is the card's "writer taken from the dispatched
  branch".

### Kept from #440

Everything else in `.agent/contracts/card-440.md` is unchanged:
- the trigger, permissions, the single job and its runner;
- checkouts with `persist-credentials: false`;
- strict base64 decoding and a strict `git apply`;
- simulators picked by UDID from `simctl list devices available -j`;
- `brew install xcodegen` and `xcodegen generate` with exactly #440's arguments;
- exactly #440's `xcodebuild test` arguments for `AICaddie` and `AICaddieWatch`, and never
  `AICaddieUITests`;
- no timeouts below 60 minutes, and no step timeouts;
- `!cancelled()` conditions;
- failing closed on unknown results, unusable ids and duplicate ids.

### Unit tests

Update `tests/test_agenthub_native_result.py` to the new writer, keeping its intent:
- duplicate ids fail closed;
- a scheme without a result gives `build_failed`, and its tests are empty;
- an unknown status is not masked;
- a failed writer leaves no stale `result.json`.

## Goals and pass conditions

### G1 — Dispatch and artifact follow agenthub's interface

1. `test_dispatch_inputs_and_upload_step_follow_agenthubs_interface` (static) checks:
   - the inputs are exactly `request_id`, `head_sha` and `patch_b64`, and the patch input is
     optional;
   - there is one upload step, named `agenthub-native-${{ inputs.request_id }}` exactly, with
     `if-no-files-found: error` and one path;
   - `agenthub-native-result` is gone.
2. `test_baseline_result_json_has_exactly_agenthubs_keys`: a request id with `_` and `.` uploads
   exactly one artifact, `agenthub-native-<request_id>`, which holds only `result.json`.
3. `test_invalid_dispatch_inputs_fail_without_an_artifact`: the job is red, no artifact is uploaded,
   and nothing is generated or tested for each of these inputs:
   - an empty request id;
   - a request id containing `/`, a space, `"` or `:`;
   - a head of `main`;
   - an empty head.
4. Every #440 replay that expects a result checks the same artifact rules through the shared
   `_result`.

### G2 — The head plus patch is still built and tested like native-mobile

5. The baseline test of this card, and #440's tests through `_check_scheme_runs`, check:
   - both schemes run on the newest iPhone 16 and Series 10 (46mm) by UDID;
   - they run on `mobile/ios/AICaddieNative.xcodeproj` after `xcodegen`, with exactly #440's
     arguments;
   - `AICaddieUITests` is never run.
6. #440's tests check the rest unchanged:
   - the patch is applied before generate;
   - the writer comes from `github.sha`;
   - the simulator selection and the runner failures.

### G3 — `stage` is the verdict; a run that judges nothing uploads nothing

7. `test_mutant_digest_is_the_sha256_of_the_decoded_patch_bytes`: an iOS failure, or a Watch failure
   with a trailing-space added line, gives a green job, `stage: tested`, and the failed test as
   `failed`.
8. `test_unappliable_patch_is_apply_failed_with_a_green_job`: a stale changed line, stale context, or
   decoded text that is not a diff gives:
   - a green job;
   - `stage: apply_failed` and `tests: []`;
   - no `xcodegen` and no `xcodebuild test`.
9. `test_build_failure_is_build_failed_with_empty_tests`: a spec that does not generate, or an iOS
   failure next to a Watch scheme without a bundle, gives a green job, `stage: build_failed` and
   `tests: []`.
10. #440's apply, build, runner-failure, fail-closed and cancellation tests check:
    - every apply and build case;
    - for undecodable input, either `apply_failed` or a red job with no artifact;
    - **no artifact at all** (`uploads == []`) on runner failures, unjudgeable results and
      cancellation. Those three tests are `# pinned:`: #440 already uploads nothing there.

### G4 — `result.json` holds exactly agenthub's keys and values

11. `_result` (used by every replay that expects a result) checks:
    - the exact key set;
    - `request_id`, and `head` equal to the inputs;
    - `patch_sha256` is the sha256 of the strictly decoded patch bytes;
    - `stage` is one of the three values;
    - each test entry is exactly `{id, status}`, with a non-empty unique id and a status from the
      four;
    - `tests` is empty unless `stage` is `tested`.
12. The baseline gives `patch_sha256` equal to the empty-input digest, and `head` equal to the
    40-hex head SHA.
13. The mutant test computes the digest of the patch text itself, and checks it against the base64
    text's digest. The trailing-space case catches a digest taken from stripped text.
14. The apply-failed and build-failed tests check the digest of the decoded bytes.

## Not covered by these tests

- **agenthub's own reader.** After the merge, the console dispatches one baseline run and validates
  the artifact with `agenthub/native.py`. It then turns the native gate back on for this project. If
  the reader still rejects the artifact, that is a follow-up card. Do not relax these tests for it.
- **The real xcresulttool output and the real `upload-artifact` name rules on the runner.** The
  replay models them.
- **The native acceptance gate.** This PR changes no path under `native-mobile.yml`'s
  `pull_request.paths`, so that gate does not apply. `.github/**` is protected, so the full gate
  does.

## Gate notes

- On `main` today, every test in the card-445 file fails:
  - the static test, on the upload name;
  - the replays, on the artifact name or the keys;
  - the validation test, because a run with an empty request id is green and uploads.
- In the #440 file, seven tests fail on `main` through `_result` or the static name check. The other
  three keep existing behaviour and carry `# pinned:`.
- I could not run the tests in this sandbox, because Python runs are refused. I checked them by
  reading them against `main`'s workflow and writer. The gate's run is the authority. If a case
  looks wrong against this contract, report it on the card. Never edit the tests.
