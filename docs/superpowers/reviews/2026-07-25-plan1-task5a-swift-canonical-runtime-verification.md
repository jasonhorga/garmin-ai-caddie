# Plan 1 Task 5A Swift Canonical Runtime Verification

Date: 2026-07-25 UTC

Verified production candidate: `343e9a227494889956d3135ba9f93382fc4a58c4`

Production candidate tree: `aa106873c7d1366393a382154ec8a3dcf3d1d4d1`

Reviewed audit head: `f14fb9fce9c98e57f21ae127c19ba3fe432f6338`

Audit-head tree: `5621ad07d93e4c967b832f493245897570ce7e8a`

## Bounded outcome and exclusions

The bounded card is
`../task-cards/2026-07-24-plan1-task5a-swift-canonical-runtime.md`.
Against baseline `f39a025266010c762328d71fb6d28811b9d29649`, Task 5A
provides the shared Swift `JSONValue`, RFC 8785 plus AI-Caddie-v1
`CanonicalJSON`, and `TypedID` runtime. It also pins the vendored SwiftJCS
source/license/provenance, the deterministic 2,048-number fixture, the normal
iOS Domain-test route, and the supported artifact boundary.

The supported distribution boundary is the repository's iOS/watchOS apps and
the isolated `AICaddieDomain.framework`. `Package.swift` remains an
in-repository source-build/audit harness rather than a supported third-party
SDK. Its observable transitive SwiftJCS module is diagnostic. The isolated
framework must load the public canonical wrapper without exposing a separately
importable SwiftJCS module.

5A does not define `DomainRoundEvent`, storage-v1 records or decoding, ledger
ownership, origin/sequence reservation, legacy wire identities, prepared
batches, receipts, app lifecycle, or Watch synchronization behavior. No
canonical registry or generated declaration changed in this packet.

## Production and remediation history

The exact range contains one bounded implementation history:

- `ae8116d` records the Task 5 packet map and 5A card;
- `eeb5d14` through `eae44e0` establish compile-safe behavioral REDs for the
  public API, typed IDs, recursive validation, generic Encodable paths, and raw
  SwiftJCS number behavior;
- `74a8de8` and `a3418a1` add the pinned runtime and deterministic vectors;
- `93d6f88` through `bb82186` make raw SwiftJCS access auditable and link the
  private static implementation into the Domain framework;
- `609cb66` through `fe7d506` reproduce the independent review findings and
  preserve raw top-level and nested negative-zero signs for public rejection;
- `1fa1160` defines the supported artifact-boundary RED; and
- `343e9a2` supplies the final production/workflow implementation used by
  Native and homeserver GREEN evidence.

Independent SPEC clarification then found that the card's owned-file ledger
omitted `.github/workflows/native-mobile.yml` and under-described the existing
Package/XcodeGen target changes. Commit `f14fb9f` changes only that task card
(12 additions, 3 deletions), closes that documentation boundary, and leaves
all production, test, generator, and workflow bytes identical to `343e9a2`.

## RED evidence

Native Mobile CI preserved several exact-SHA RED checkpoints rather than
inferring TDD from the final tests:

- run [`30064482119`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30064482119)
  at `eeb5d14` failed because `JSONValue`, `CanonicalJSON`, and `TypedID` did
  not exist;
- run [`30065207093`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30065207093)
  at `eb5e438` compiled the seam and then failed exact canonical bytes, safe
  integer boundaries, domain validation, and typed-ID expectations;
- run [`30065919797`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30065919797)
  at `eae44e0` failed the intended representative canonical and validation
  assertions while exercising the raw vendor audit seam;
- run [`30070438433`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30070438433)
  at `a1ebfc4` exposed the missing static SwiftJCS link with an undefined
  `JSONCanonicalization.data` symbol; and
- run [`30076942034`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30076942034)
  at `609cb66` showed raw `-0`/`-0.0` decoding to integer zero and therefore
  bypassing `CanonicalJSON`/`TypedID` rejection.

The final artifact-boundary Python RED used a fresh homeserver clone at
`1fa116001ef60621cb555dc8220831872d13650f`. It ran 14 focused tests, failed 8
intended workflow/card assertions, exited 1, remained clean, and was wrapped by
an outer assertion that required the failure. The corresponding exact
`343e9a2` focused run passed 14/14.

An earlier attempt to clone a review checkpoint over SSH failed before test
discovery with GitHub public-key exit 128. The immediate HTTPS clone retry
passed. It is an environment-only attempt, not counted as RED or hidden as
test evidence.

## Homeserver GREEN and mechanical evidence

The production candidate `343e9a2` first passed 103/103 tests in an ephemeral,
clean homeserver clone:

```text
/home/jason/.local/bin/uv run python -m unittest \
  tests.test_swift_canonical_runtime_assets \
  tests.test_contract_codegen \
  tests.test_contract_authority -v
  -> 103 tests; OK; exit 0

git diff --no-renames --name-only -z f39a025..HEAD |
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py
git diff --check f39a025..HEAD
git status --porcelain=v1
  -> all exit 0; status empty
```

After the docs-only audit remediation, the main session independently cloned
the public repository at exact `f14fb9f` into:

`/home/jason/codex-runs/garmin-ai-caddie-task5a-doc-f14fb9f-20260725-root-a1`

It reran the same 103-test suite plus authority, diff-check, and clean-state
gates. All exited 0; the suite reported `Ran 103 tests in 2.699s` and `OK`.
The preserved log is:

`/home/jason/codex-runs/garmin-ai-caddie-task5a-doc-f14fb9f-20260725-root-a1.log`

Its SHA-256 is
`6861065eaf0e563d38caaae1b17d39fe9cd8ec62307899e59f1ad6a1697f5d54`.

The independently checked pinned asset hashes are:

| Asset | SHA-256 |
|---|---|
| `JSONCanonicalization.swift` | `22a38cf5cda61062cf3a61688474e4dba796a8eea1bfb2ca8c977587deddbc9c` |
| `NumberSerializer.swift` | `acdedc57a40e8ceb66ff640a82d84b7e340617670aff955b4679df43b3816502` |
| `StringSerializer.swift` | `cbb40f06dbb35c43ca9db9e0637cb6baaaf82844d673476363c548556ec91464` |
| `swift-jcs-UNLICENSE` | `b5065838cbac452dfc855ba6e6e031481ad2c68406f70d21ead9321374653e6c` |
| `rfc8785_number_vectors.json` | `e39332b29fbda04ff1aed0c1f7d0bed4f1f221d798b4204bc95553e891d42b79` |

## Native exact-SHA evidence

Native Mobile CI run
[`30089246951`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30089246951),
job `89468547687`, checked out exact production candidate `343e9a2` on
`macos-15` and completed successfully:

- `CanonicalJSONTests`: 18 tests, 0 failures;
- complete `AICaddieDomainTests`: 19 tests, 0 failures;
- iOS app tests: 108 tests, 0 failures;
- real iOS UI tests: 3 tests, 0 failures; and
- Watch tests: 66 tests, 0 failures.

The log shows the iOS and Watch `AICaddieDomain.framework` binaries linked with
the private static `SwiftJCS` target. The SwiftPM source consumer could import
the transitive module, which is the expected diagnostic result for the audit
harness. The staged isolated framework loaded the public wrapper, contained no
separate SwiftJCS module/library artifact, and its explicit `import SwiftJCS`
consumer failed with the required `no such module 'SwiftJCS'` diagnostic.

The downloaded job log SHA-256 is
`6d3fe744d0e43a006dbd90b889de4d9251ef002615e7b9673c6af7f2ddd31549`.
The `native-build-evidence` payload names exact commit `343e9a2`, both schemes,
both simulator destinations, and `passed`; its SHA-256 is
`c1a58c650bbeec431b4a62fe7612b26e0595b69fa730b9d94935ceed3c3a9e80`.

## Independent reviews

The final specification re-review covered exact range `f39a025..f14fb9f` and
reported `SPEC PASS`, Critical 0 and Important 0. It explicitly confirmed that
the card now owns the Native workflow and accurately describes the Package and
XcodeGen target/link/source-isolation changes.

The fresh quality review initially encountered a platform-wide 503/429 before
producing a verdict. The automatic retry reviewed the same exact range and
reported `QUALITY PASS`, Critical 0, Important 0, and Minor 0. It inspected all
18 paths, production references, generator/provenance, target configuration,
tests, and Native gates. It found no supported-artifact gap: the framework
itself is linked with SwiftJCS, Domain tests execute the public wrapper, the
isolated module loads, and the negative consumer requires the exact missing
module diagnostic.

## Gate result and POP

Plan 1 Task 5A satisfies the Execution Index definition of `VERIFIED` for
production candidate `343e9a2`, with the complete reviewed audit boundary at
`f14fb9f`: approved requirements and exclusions, observed behavioral REDs,
production implementation, homeserver GREEN/mechanical evidence, exact-SHA
Native evidence, clean SPEC, clean QUALITY, and dedicated commits all exist.

POP returns to the S70 Unified Golf Program Execution Index. The next work is
to activate only the first bounded 5B literal-schema packet; this verification
does not approve a monolithic 5B implementation or any 5C+ mutation,
ownership, network, or lifecycle behavior.
