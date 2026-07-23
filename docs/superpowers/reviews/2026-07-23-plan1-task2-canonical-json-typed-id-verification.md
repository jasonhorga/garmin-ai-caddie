# Plan 1 Task 2 CanonicalJSON and Typed ID Verification

Date: 2026-07-23 UTC
Verified production HEAD: `09770d7ee103440a81104e59820ae480a18cb4dd`

## Bounded requirement and exclusions

Task 2 establishes the shared canonical identity foundation. It must provide:

- RFC 8785 canonical bytes with the AI Caddie v1 restrictions for JavaScript
  safe integers, finite numbers, negative zero, NFC strings, Unicode scalar
  values, JSON types, and exact UTF-8;
- a duplicate-key-safe transport parser that normalizes malformed syntax and
  invalid UTF-8 without prematurely applying canonical semantic validation;
- registry-driven schema validation and top-level projection before hashing;
- domain-separated typed IDs over the projected canonical bytes;
- exact golden bytes and typed IDs plus deterministic Python, Swift, and
  TypeScript canonical descriptor declarations tied to one source digest.

This task does not register round-event kinds, define reason/transport tables,
implement event durability, or establish round/product behavior. Those remain
owned by later Plan 1 tasks. In particular, this verification does not infer
that Task 3 is complete merely because its later shared generator code is
present at the verified HEAD.

## Production evidence

The dedicated implementation and remediation history is:

- `07bcb61` — initial CanonicalJSON runtime, object registry/schema/goldens,
  generated descriptors, typed IDs, dependencies, and tests;
- `c00ebef` — strict UTF-8 and Unicode handling, canonical error normalization,
  descriptor/runtime hardening, and deployment/CI dependency coverage;
- `16044d4` — requirement-level canonical matrix, projection-order,
  stateful-snapshot, pre-hash, and cross-language descriptor evidence;
- `f308056` — malformed syntax, non-finite constants, transport-versus-semantic
  parser boundaries, and unsafe integral-float evidence;
- `09770d7` — finite-checking JSON float parser and signed exponent-overflow
  regression coverage.

At the verified production HEAD:

- `canonical_json.py` validates the complete supported value tree before RFC
  8785 encoding, maps library failures to `CanonicalJSONError`, preserves an
  integer `-0` sentinel for deferred semantic validation, rejects duplicate
  keys, rejects non-standard constants, and rejects finite-syntax exponent
  overflow that Python would otherwise decode as infinity;
- `parse_unique_json` remains a transport parser: it accepts syntactically
  valid unsafe integers, finite unsafe integral floats, integer negative zero,
  and non-NFC strings for later per-event semantic rejection;
- `canonical_objects.py` snapshots a caller mapping once, validates the whole
  snapshot against Draft 2020-12 before wildcard or explicit projection, and
  rejects unclassified fields;
- `typed_ids.py` resolves a registered domain and validates/projects before it
  can call the domain-separated SHA-256 digest;
- the checked-in schema and fixtures freeze exact UTF-8 bytes, domain
  separation, excluded transport-field behavior, and a deliberately
  duplicate-key raw fixture;
- Python, Swift, and TypeScript declarations carry the same canonical source
  digest and exact two-domain descriptor table.

## RED and mutation evidence

The remediation sequence retained behavior-specific failing evidence rather
than relying only on final green tests:

- the `16044d4` evidence matrix observed mutations produce three failures plus
  two errors for the canonical value matrix, two errors for integral-float
  endpoints, two failures when projection preceded validation, two failures
  when hashing occurred prematurely, and one failure when the Swift Beta
  descriptor was removed;
- the `f308056` parser mutations produced three failures when non-finite
  constant rejection was bypassed, four failures when `JSONDecodeError`
  normalization was removed, and two failures when the integral-float safe
  bound was bypassed;
- before `09770d7`, the focused signed exponent-overflow test ran once against
  unmodified parent `f308056` and produced two failures because
  `parse_unique_json` accepted both `1e400` and `-1e400`;
- after the finite-checking `parse_float` hook, the same signed cases pass for
  both transport parsers while the finite unsafe-integral deferral cases remain
  green.

## Independent reviews

- Final specification-compliance re-review at `09770d7`: `SPEC PASS`; no
  Critical, Important, or Minor finding.
- Final code-quality re-review at `09770d7`: `QUALITY PASS`; no Critical,
  Important, or Minor finding.

The final reviews specifically rechecked signed exponent overflow, finite float
semantics, transport-only deferral, exception normalization, test sensitivity,
and the two-file scope of the last production fix.

## Homeserver verification

Independent verification and the main-thread rerun both used the fresh, clean,
exact homeserver clone:

`/home/jason/codex-runs/garmin-ai-caddie-plan1-task2-final-verify-09770d7-20260723-codexfresh-v2`

The clone resolved to:

```text
HEAD  = 09770d7ee103440a81104e59820ae480a18cb4dd
HEAD^ = f30805666f4ff0bf1969c46ca07007325ec337b2
branch = feature/execute-all-frozen-plans
Python = 3.12.3
```

Its complete-history transfer bundle matched local and remote SHA-256
`ad1ee07948b8cbb421e52e0228ae0164e23ca4cd1313665f3c92f3fbd0867415`.

Fresh main-thread commands and results were:

```text
python -m py_compile \
  ai_caddie/contracts/canonical_json.py \
  tests/test_canonical_contract_ids.py \
  tests/test_contract_codegen.py
  -> exit 0

python -m unittest \
  tests.test_canonical_contract_ids tests.test_contract_codegen -q
  -> Ran 40 tests in 0.252s; OK

python -m unittest \
  tests.test_contract_authority tests.test_contract_codegen -q
  -> Ran 85 tests in 1.494s; OK

git diff --no-renames --name-only -z b60b555..09770d7 |
  python tools/contracts/check_authority.py
  -> exit 0

git diff --no-renames --name-only -z 09770d7^..09770d7 |
  python tools/contracts/check_authority.py
  -> exit 0

git diff --check
git diff --check b60b555..09770d7
git diff --check 09770d7^..09770d7
  -> all exit 0

git status --porcelain
  -> empty
```

An independent digest calculation over the nine canonical JSON/generator
inputs produced
`f49c911225cac30cfdddfe5c485d217c6c199a432831f66855a509a96d6aec5c`.
All three checked-in generated declarations carry that exact pin.

## Verified file digests

| Artifact | SHA-256 |
|---|---|
| `ai_caddie/contracts/canonical_json.py` | `81524648ecce2e2a024eee7778878a98bbccd7d21d33af65497499e9f5d6ead9` |
| `ai_caddie/contracts/canonical_objects.py` | `18f9354e156262aa2cf9565e39922be4b32e677f1bfed72b09208067ae787773` |
| `ai_caddie/contracts/typed_ids.py` | `d372b6e380c2a1bb0b9c51cc8111f2fd630773f13b1e6977e9abe33ee27ae71e` |
| `contracts/canonical/canonical_object_registry.json` | `9d4cbbdeec91909e6e0b3b9203eb0c7d9cedec06d382d1cf654bd09400b4cc3a` |
| `contracts/canonical/canonical_fixture_v1.schema.json` | `a8929cbdbc7fa84666f7f66800033000ffa11323911d45b734e7497d5605b4e2` |
| `contracts/canonical/fixtures/canonical_json_v1.json` | `80a5fe4b3231a48e33a1299549afa09b5fde61ad607497aac4f3f0688382e24f` |
| `contracts/canonical/fixtures/canonical_json_duplicate_key.json` | `838ea2ad137143cc2679cf6a072d45a00ce085fd898ada161d4672b789982b14` |
| `tests/test_canonical_contract_ids.py` | `e8b1c098b845ec5e3ace5876e22bf42b6ee57398ec3aeb929b31f1d74bd209e4` |
| `tests/test_contract_codegen.py` | `79611aa538dfd65b576fadfaf8d9e749a9b267e140e75cf3192f3c3a232db712` |
| `tools/contracts/generate_contracts.py` | `83a4e132603cccf0ff68be83c1e93163f2f5f8d4885fa225ee2fe8910d2e5f90` |
| `ai_caddie/contracts/generated.py` | `e826474e0daf776f63c0f6e47f56f03a4bd0859e30826db57721816b0dc78b15` |
| `mobile/ios/AICaddieDomain/GeneratedContracts.swift` | `fa848e6348fc6a33b45ac75cbc5ae635e72e591ba1dc9fc30634fd4c95af801b` |
| `web_v2/src/contracts/generated.ts` | `29d001b530520ab6a1363dbffe4b0ec136ca74e6c45583826073110f1a9e2ee0` |

## Gate result

Plan 1 Task 2 satisfies the Execution Index definition of `VERIFIED` at
production HEAD `09770d7`. POP returns to the canonical reliability foundation
and selects Plan 1 Task 3; this result does not pre-approve Task 3's candidate
implementation.
