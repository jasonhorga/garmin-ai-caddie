# Plan 1 Task 3 Registry and Codegen Verification

Date: 2026-07-23 UTC
Candidate production HEAD: `b6b818a8008ce2014c2d0fd8b3f1f745df2317c6`

## Bounded requirement and exclusions

Task 3 establishes the registry and generated-declaration framework shared by
Python, Swift, and TypeScript. It must provide:

- a duplicate-key-safe, schema-checked event-kind registry whose production
  `kinds` table remains empty until the task that owns round-event schemas;
- the frozen reason-code set and all fourteen round transport limits;
- fail-closed registry validation for envelope shape, raw names, duplicate
  values, Swift identifier/reserved-word collisions, submission classes, and
  exact transport-limit keys;
- transport-limit values that are non-Boolean integers in the inclusive range
  `1...9_007_199_254_740_991`, so every emitted value is exact in Python,
  Swift `Int`, and JavaScript `Number`;
- deterministic, sorted declarations and submission-class maps in all three
  languages, including the omitted-rule default `ordinary_event` and all four
  submission classes;
- checked-in outputs tied to every canonical JSON source and the generator by
  one length-prefixed SHA-256 source digest.

This task does not define `round_event_v2`, populate production event kinds,
implement mobile event durability, define reducers, or establish any product
scoring behavior. Those remain owned by later Plan 1 tasks. Future fields in an
event rule remain allowed so this framework does not pre-empt the later schema
owner.

## Production evidence

The dedicated Task 3 implementation and remediation commits are:

- `cfac7cfa59b1f56b3a41c2c5857572d507a06211` — initial normative registries,
  shared generated tables, Swift/TypeScript smoke coverage, and three-language
  source digest;
- `7a6fa22f669380f68e15fbec5377a047ed60b876` — fail-closed registry schemas,
  duplicate/name/collision checks, deterministic generation, explicit UTF-8
  writes, and owner-gate integration;
- `b6b818a8008ce2014c2d0fd8b3f1f745df2317c6` — JavaScript-safe transport-limit
  bounds plus exact all-key, four-class, three-language, and repeated-output
  regression evidence.

The final remediation commit has sole parent
`7387ca6c734aaf378ecb0c08f77aa35c5dce5d15` and changes exactly:

- `tools/contracts/generate_contracts.py`;
- `tests/test_contract_codegen.py`;
- `ai_caddie/contracts/generated.py`;
- `mobile/ios/AICaddieDomain/GeneratedContracts.swift`;
- `web_v2/src/contracts/generated.ts`.

At the candidate HEAD:

- every canonical registry is loaded with duplicate-key rejection;
- the registry envelope, schema tags, names, submission classes, exact limit
  keys, and cross-language numeric domain are validated before any emitter
  receives them;
- event kinds are sorted once and drive the Python tuple/map, Swift members and
  map, and TypeScript array/map;
- a deliberately out-of-order temporary registry exercises all four
  submission classes and the omitted default without modifying the empty
  production registry;
- a complete second generation is byte-compared with the first;
- all three checked-in outputs carry
  `d15178ffb567437d32e3c2b7acf361eaf846672efb9d6814a3ac9587eee08eb1`.

## RED and mutation evidence

The main-thread natural RED used the unmodified production generator at parent
`7387ca6` and overlaid only the final test file in this homeserver scratch:

`/home/jason/codex-runs/garmin-ai-caddie-plan1-task3-mainred-7387ca6-20260723-a1`

The focused command was:

```text
python3 -m unittest \
  tests.test_contract_codegen.ContractCodegenTests.test_rejects_above_max_safe_integer_for_every_transport_limit \
  -v
```

All fourteen named limit-key subtests failed because the parent generator did
not raise `ValueError`; the run ended with `FAILED (failures=14)` and exit 1.
The same test is green at the candidate HEAD.

The implementation pass also recorded controlled test-sensitivity mutations,
each restored before commit:

- disabling event-kind sorting broke the exact declaration test;
- changing the omitted submission-class default broke the Python projection;
- corrupting Swift lower-camel members/submission mapping broke the exact Swift
  declaration;
- reversing TypeScript kinds and emptying its map broke the exact TypeScript
  declaration.

Exact maximum acceptance, and Boolean, float, zero, and negative rejection,
are exercised for every one of the fourteen keys rather than one representative
key.

## Independent reviews

- Final specification-compliance review at `b6b818a`: `SPEC PASS`; zero
  findings.
- Final code-quality review at `b6b818a`: `QUALITY PASS`; zero Critical,
  Important, or Minor findings.

The specification review independently checked sole-parent history, five-file
scope, all fourteen bounds, the four-class fixture, exact three-language
projections, empty production kinds, and recomputed the shared digest. The
quality review rechecked fail-closed validation, ordering, all-key boundaries,
test sensitivity, and future drift risk.

## Homeserver verification

Independent main-thread verification used this fresh, clean, exact clone:

`/home/jason/codex-runs/garmin-ai-caddie-plan1-task3-mainverify-b6b818a-20260723-a1`

It was cloned from the complete-history bundle:

`/home/jason/codex-runs/garmin-ai-caddie-plan1-task3-final-b6b818a-v4TsQY.bundle`

The bundle SHA-256 is
`80e09187df9bc099d44f64149e14a15846de8c977698109571a6750c875202c5`.
`git bundle verify` reported a complete history and the sole branch ref at the
candidate SHA. The clone resolved to:

```text
HEAD   = b6b818a8008ce2014c2d0fd8b3f1f745df2317c6
HEAD^  = 7387ca6c734aaf378ecb0c08f77aa35c5dce5d15
branch = feature/execute-all-frozen-plans
Python = 3.12.3
Node   = v24.14.1
npm    = 11.14.1
```

The dependency-bearing Python commands used the existing isolated Python
3.12 environment at
`/home/jason/codex-runs/garmin-ai-caddie-plan1-task2-overflow-fix-b71c4e-20260723/.venv`;
it contains `rfc8785 0.1.4`, `jsonschema`, `PyYAML`, and `pathspec`. No global
package was installed. The TypeScript test reused the already-installed
`web_v2/node_modules` from the implementation verification clone through a
temporary symlink that was removed before the final clean-status check.

Fresh commands and results were:

```text
python3 -m py_compile \
  tools/contracts/generate_contracts.py \
  tests/test_contract_codegen.py \
  ai_caddie/contracts/generated.py
  -> exit 0

python3 -m unittest tests.test_contract_codegen -v
  -> Ran 22 tests in 0.796s; OK

<isolated-python> -m unittest \
  tests.test_canonical_contract_ids tests.test_contract_codegen -q
  -> Ran 44 tests in 0.857s; OK

<isolated-python> -m unittest \
  tests.test_contract_authority tests.test_contract_codegen -q
  -> Ran 89 tests in 2.419s; OK

web_v2/node_modules/.bin/vitest run src/contracts/generated.test.ts
  -> 1 file passed; 1 test passed

git diff --no-renames --name-only -z 7387ca6..b6b818a |
  <isolated-python> tools/contracts/check_authority.py
  -> exit 0

git diff --no-renames --name-only -z b6b818a^..b6b818a |
  <isolated-python> tools/contracts/check_authority.py
  -> exit 0

git diff --check
git diff --check 7387ca6..b6b818a
git diff --check b6b818a^..b6b818a
  -> all exit 0

git status --porcelain
  -> empty
```

An independent length-prefixed calculation over the nine canonical
JSON/generator inputs produced
`d15178ffb567437d32e3c2b7acf361eaf846672efb9d6814a3ac9587eee08eb1`.
All three checked-in declarations carry that exact pin.

## Native Swift evidence and unrelated failure attribution

Native Mobile CI run
[`30036446529`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30036446529)
checked out exact SHA `b6b818a` on `macos-15` with Xcode 16.4. Its first
attempt compiled `GeneratedContracts.swift` and linked `AICaddieDomain` for
both iOS and watchOS simulator targets. The later iOS runtime suite executed 95
tests and failed one pre-existing Task 4 test:

`OfflineStoreTests.testLaterMediaUploadSuccessKeepsResponseLostRetryBodyAndKeyExact`

The assertion compared two separately encoded 333-byte JSON bodies and found
different bytes. Neither that test nor its `OfflineStore`/`SyncClient` path is
changed by `7387ca6..b6b818a`. The failure is retained as a Task 4 input rather
than hidden or attributed to generated declarations.

The unchanged second attempt again compiled and linked the generated Domain
source for both simulator platforms, then executed 95 iOS tests and again
failed only the same 333-byte comparison. This rules out a transient runner or
service failure and gives Task 4 a stable native RED. It does not contradict
the successful Task 3 native compile evidence, but its root-cause attribution
must be retained in the Task 4 card rather than erased by another rerun.

An independent read-only trace confirmed that `removePendingMedia` changes
only the pending-media index and media files; both bodies are reconstructed
from the unchanged event log. The test uses two default `JSONEncoder` instances
over dictionary-backed payloads and therefore asserts an object-member order
that Foundation does not promise. Backend v1 idempotency hashes the parsed,
normalized event roster with sorted keys, so this raw-order difference is not
a current server idempotency mismatch. Task 4 owns effective-envelope
invariance and must repair this oracle plus add a real media-sync regression;
persisted exact raw-body retry is explicitly owned by Task 5.

The generated Xcode scheme does not include `AICaddieDomainTests`, so this
record does not claim that `GeneratedContractsSmokeTests` ran. Exact values,
ordering, maps, names, limits, and pins are proved by the three-language
generator tests above; the macOS evidence proves that the exact checked-in
Swift output compiles and links for both supported native platforms.

## Verified file digests

| Artifact | SHA-256 |
|---|---|
| `tools/contracts/generate_contracts.py` | `7f92fca504ce0aaf14efff9263c0ef1d61e6172b7b7a7c770f773dc35d94820f` |
| `tests/test_contract_codegen.py` | `1846df88811181c75f05caa92fad1976765ca5ccdd838cc3859f95930e941549` |
| `contracts/canonical/event_kind_registry.json` | `4860c3d700887e672a49544c458dc6c977686e2f67826a78105229a5e88e0834` |
| `contracts/canonical/reason_codes.json` | `3553274bb82938e41cf6bcf363d857c52c57e62a40fcb0a10c1cbc385058739e` |
| `ai_caddie/contracts/generated.py` | `e99b4b76c0945e24987c1f0f004e1f2704d308811797a36c7439e6c294a243f2` |
| `mobile/ios/AICaddieDomain/GeneratedContracts.swift` | `464c6e5521c2830d57dd8efa81585c9edf85d4578eff8f49201fe7f2439a35b4` |
| `web_v2/src/contracts/generated.ts` | `6db712a162f23eb15b1fb5fe156a251719099b61f5679dc5de257db86ae56e5c` |

## Gate result

Plan 1 Task 3 satisfies the Execution Index definition of `VERIFIED` at
production HEAD `b6b818a`. Its exact generated Swift output compiled and linked
for iOS and watchOS twice; the overall Native workflow is correctly recorded
as red because it exposed the separate Task 4 oracle above, not reported as a
green Task 3 job. POP returns to the canonical reliability foundation and
selects Plan 1 Task 4; this result does not pre-approve Task 4's candidate
implementation.
