# Plan 1 Task 5B2a-R Raw JSON Gate Verification

Date: 2026-07-25 UTC

Verified production candidate:
`2a8beb162a0791c3442f9201033ac0716f349342`

Production candidate tree:
`5bf344f9b1a50058209857fd305a7a18d4537824`

Card baseline:
`4ed014121ea47bb72d54eff6bfac13030c50801d`

Card-baseline tree:
`110b70abb6fcffc104ec2fdca4c88ef92eae242c`

## Frozen authority and bounded outcome

The approved design is
`../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md`, SHA-256
`f31a090fe9c4dc37828f25ee3528afd067d7222128606514b2cfe74229dc2b05`.
The bounded implementation card is
`../task-cards/2026-07-25-plan1-task5b2a-r-raw-json-gate.md`, SHA-256
`5f186b08e10334b9f5f8771b6b73fa724b65bc7b375979c7dbb4eb531010c38b`.
Both authorities remained byte-stable throughout the candidate range.

5B2a-R provides only a non-public raw-`Data` gate. It accepts exactly one
RFC 8259 JSON value, with optional legal JSON whitespace, and enforces these
inclusive limits:

- at most 67,108,864 source-document bytes;
- recursive JSON depth at most 64;
- decoded object keys at most 128 Unicode scalars; and
- decoded string values at most 1,398,104 Unicode scalars.

The iterative scanner rejects duplicate decoded keys within each object,
including literal/escaped spellings of the same key. It validates UTF-8,
escapes and Unicode scalars; carries exact scalar-count and decoded-string
evidence; preserves exact raw token lexemes and source ranges; snapshots caller
bytes immutably after the byte gate; and exposes independent,
source-identity-bound replay cursors without retaining an AST or token array.

The exact card-to-candidate range creates only:

- `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift`;
- `mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift`; and
- `tests/test_storage_v1_raw_json_gate_assets.py`.

Their final SHA-256 values are:

| Path | SHA-256 |
|---|---|
| `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift` | `9d68bf3a4b8b5931ccf0e778d3f8ef321016c519f2d3653257eb8a34f6e1553a` |
| `mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift` | `4e7ffa1bca560b54519ccb25ef17be52448dc58a2510ebcb97eb3bd68e754846` |
| `tests/test_storage_v1_raw_json_gate_assets.py` | `936dc2117b25dd22bd31528297910de4a569d1ef099ae6ad8492b3398685a55e` |

5B2a-R deliberately excludes the 5B2a-S generated root shape, unknown-key,
field type/nullability, NFC, canonical-number, Base64, collection-count and
typed-decode rules. It also excludes all ledger/transport graph validation,
identity and hashing algorithms, persistence, mutation, lifecycle, migration
and network work. No supported/public storage-v1 decoder exists at this gate.

## Production and TDD history

The feature-branch candidate history is linear through the fixture-only
erratum:

| Stage | Commit | Tree | Parent | Purpose |
|---|---|---|---|---|
| CARD | `4ed014121ea47bb72d54eff6bfac13030c50801d` | `110b70abb6fcffc104ec2fdca4c88ef92eae242c` | `ad6ce690e6afb2865f8ab2ce867ed9d6bf3075de` | activate the bounded frozen 5B2a-R card |
| RED-1 | `c0fac8d06244eebb5f6c9f27959bba67a2f83f20` | `34e6c82c5f2e887a5b0ffd7fc52e1fb1b562da0c` | `4ed014121ea47bb72d54eff6bfac13030c50801d` | define the complete wished-for tests before the production type exists |
| RED-2 | `3dc3e123f161a8174fafcec431555e2bde4e6967` | `afd4c88e675f8a98f413188601921f3acf49f856` | `c0fac8d06244eebb5f6c9f27959bba67a2f83f20` | add a compile-safe seam whose scanner behavior remains intentionally absent |
| original GREEN | `ce009bf333aa0bbc0e06101fe6521f366c6a45c1` | `094b3076eba040311ca31f195a436c8e91266f72` | `3dc3e123f161a8174fafcec431555e2bde4e6967` | install the exact frozen production scanner and original frozen test block |
| final fixture erratum | `2a8beb162a0791c3442f9201033ac0716f349342` | `5bf344f9b1a50058209857fd305a7a18d4537824` | `ce009bf333aa0bbc0e06101fe6521f366c6a45c1` | replace only the invalid one-byte Foundation alias fixture oracle |

One additional commit-tree proves the corrected fixture against the RED-2
scanner seam:

| Stage | Commit | Tree | Parent | Purpose |
|---|---|---|---|---|
| auxiliary corrected-fixture RED | `5f55a57a9e4b9176e309eda70664692b5d4d2038` | `af50765fefe2a84f5acf8ce21bdb27704c986981` | `3dc3e123f161a8174fafcec431555e2bde4e6967` | prove caller aliasing first, then observe missing snapshot/replay behavior |

The auxiliary commit is retained only on its dedicated evidence branch. It is
not part of the feature branch's linear history and must not be merged into the
candidate.

## RED evidence

### Test-only RED-1

At exact RED-1 `c0fac8d0`, the fresh homeserver run executed five mechanical
tests. One passed and four failed at the intended missing-production boundary.
The preserved log contains 65 lines and 8,687 bytes; SHA-256:
`9303324af55b8965156a3f2ae0049e3cf1d82843eb9bdb9fb32075dbb696000a`.

Native Mobile CI run
[`30168504789`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30168504789),
job `89705474915`, checked out the exact RED-1 SHA and failed only because the
production type was intentionally absent. Its 3,362-line, 747,137-byte log has
SHA-256
`d959ed324a3eb46699aabd99fac2fe3c8bd1c861f08429d40fadb1a10ee627d5`.

### Compile-safe behavioral RED-2

At exact RED-2 `3dc3e123`, the fresh homeserver run executed five top-level
tests: four passed, while the scanner test produced 14 intended behavioral
subtest failures with zero errors. The 148-line, 70,105-byte log SHA-256 is
`fb3e04abf5e54bb5ba4268e800e29b913513b419ebf4cc2a2314598b6e904419`.

Native Mobile CI run
[`30168661565`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30168661565),
job `89705874936`, compiled successfully and ran all 17 raw-gate tests. Five
passed and 12 failed with 67 intended assertions against the missing scanner
behavior; there was no compile failure. Its 5,069-line, 1,167,885-byte log
SHA-256 is
`a0c892b118c00aecf8102a027040a702df992760bc4257c3dbe08c21a6863ee8`.

## Original GREEN and fixture erratum

At original GREEN `ce009bf3`, the fresh homeserver run passed 112/112 tests.
The generator-clean, authority, exact-diff and final-clean checks also passed.
The 129-line, 20,539-byte log SHA-256 is
`bc6735bdf4317141c68aaefaa14fd37fdc7e556d36cf71d2c0c5a632e6029c2d`.

Native Mobile CI run
[`30169029157`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30169029157),
job `89706810717`, compiled the frozen candidate and failed only the original
one-byte Foundation alias assertion. The actual capability snapshot and replay
assertions passed. Its 4,946-line, 1,134,935-byte log SHA-256 is
`98ddf8c72b0e395a2a507567cb151c45138b7ce65f473f5acf275966301acf82`.

On macOS 15, Foundation stores `Data` payloads of 14 bytes or fewer inline.
The original one-byte `NSMutableData`/`Data(referencing:)` fixture therefore
copied into inline storage and could not prove that the caller and input
`Data` shared mutable backing. This was a fixture-oracle failure, not a
production scanner failure.

The authorized erratum replaces only that fixture with a caller-owned 64-byte
allocation wrapped by
`Data(bytesNoCopy:count:deallocator:)` with deallocator `.none`. The test first
proves that a direct pointer mutation appears in the caller's `Data`, then
proves that the validated capability retains its original snapshot and replays
the original bytes. The caller deallocates the pointer after both checks. An
independent Swift memory-safety audit reported Critical 0, Important 0, Minor
0. The 702-line production scanner remained byte-identical to the frozen GREEN
block, with SHA-256
`9d68bf3a4b8b5931ccf0e778d3f8ef321016c519f2d3653257eb8a34f6e1553a`.

### Auxiliary corrected-fixture RED

The corrected fixture was also applied to the RED-2 tree as auxiliary commit
`5f55a57a`. Its fresh homeserver run produced four top-level passes plus the 14
intended missing-scanner failures. The 148-line, 67,090-byte log SHA-256 is
`c502016349c58d1e2f2e6d956bac4dc2656175d36eb72d7d2a3cbf84162fdb23`.

Native Mobile CI run
[`30170560259`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30170560259),
job `89710852991`, artifact `8622833963`, checked out the exact auxiliary SHA.
The caller-alias assertion passed, after which capability snapshot and replay
failed as intended against the RED-2 seam. All 17 tests ran: five passed and 12
failed with 67 intended assertions. Compilation succeeded and the seam-behavior
failures remained controlled. The 5,061-line, 1,167,512-byte log SHA-256 is
`a683c2208774a9f8ddb85586c80a66128e59448c6529cc468c51a8d5c0da4f99`.

## Final homeserver GREEN and mechanical evidence

The final candidate `2a8beb16` was fetched by exact SHA into a fresh homeserver
clone. The focused raw-gate, Swift canonical runtime, code-generation and
authority suites passed 112/112 with zero failures or errors. Regeneration
produced no diff; authority and exact changed-path checks passed; `git diff
--check` passed; and final status remained empty.

The preserved log contains 129 lines and 20,559 bytes; SHA-256:
`702426cddcc5c37a2e1dc4804736635bd733d078ad89e677e45a5d76de6f5cc2`.

## Final Native exact-SHA GREEN evidence

Native Mobile CI run
[`30169682011`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30169682011),
job `89708601698`, completed successfully at exact candidate
`2a8beb162a0791c3442f9201033ac0716f349342` on `macos-15`:

- raw-gate tests: 17/17;
- complete `AICaddieDomainTests`: 47/47;
- complete iOS `AICaddieTests`: 108/108;
- live iOS UI tests: 3/3;
- complete `AICaddieWatchTests`: 66/66; and
- SwiftJCS boundary: PASS.

All counts have zero failures. The complete 9,238-line, 2,055,502-byte job log
SHA-256 is
`5165501418efa17dfed2098ee930af5d387879e9a7813471177afdf7d64c1c95`.

The run uploaded `native-build-evidence` artifact `8622757982`. The downloaded
ZIP SHA-256 is
`0f7507b916e073843453b86a0677b75e3cceaa9e3fe08838b75a89959c7efc3b`;
the extracted JSON SHA-256 is
`ec71aee4a8b6125c42c17e94dbd49d0743cf585759440ab2bb7260a4089800bd`.
That JSON binds the exact commit and run to passed iOS and Watch schemes and
destinations.

## Immutable evidence refs

The following origin refs resolve to the listed exact commits:

| Origin ref | Target |
|---|---|
| `refs/heads/evidence/plan1-task5b2ar-red1-c0fac8d06244eebb5f6c9f27959bba67a2f83f20` | `c0fac8d06244eebb5f6c9f27959bba67a2f83f20` |
| `refs/heads/evidence/plan1-task5b2ar-red2-3dc3e123f161a8174fafcec431555e2bde4e6967` | `3dc3e123f161a8174fafcec431555e2bde4e6967` |
| `refs/heads/evidence/plan1-task5b2ar-green-ce009bf333aa0bbc0e06101fe6521f366c6a45c1` | `ce009bf333aa0bbc0e06101fe6521f366c6a45c1` |
| `refs/heads/evidence/plan1-task5b2ar-erratum-green-2a8beb162a0791c3442f9201033ac0716f349342` | `2a8beb162a0791c3442f9201033ac0716f349342` |
| `refs/heads/evidence/plan1-task5b2ar-fixture-red-5f55a57a9e4b9176e309eda70664692b5d4d2038` | `5f55a57a9e4b9176e309eda70664692b5d4d2038` |

## Independent reviews

The fresh read-only specification reviewer inspected the exact three-path
candidate range, both RED stages, the fixture erratum and the terminal remote
evidence. It reported `SPEC PASS`, Critical 0, Important 0, Minor 0, explicitly
accepting the fixture-only correction. It found no extra or missing 5B2a-R
scope.

Only after SPEC passed, a different fresh read-only quality reviewer inspected
the same exact candidate and evidence. It reported `QUALITY PASS`, Critical 0,
Important 0, Minor 0. The separate Swift fixture memory-safety audit also
reported Critical 0, Important 0, Minor 0. No remediation commit was required.

## Gate result, retained gates and POP

Plan 1 Task 5B2a-R satisfies the Execution Index definition of `VERIFIED` at
candidate `2a8beb1`: frozen requirements and exclusions, observed test-only and
behavioral REDs, a separately observed corrected-fixture RED, fresh homeserver
GREEN, exact-SHA Native GREEN, clean SPEC and QUALITY reviews, and dedicated
commits all exist with no open finding.

This result verifies only 5B2a-R. Task 5B, Task 5 and Plan 1 remain incomplete
and unfrozen. The following later gates remain open:

- the strict-Pydantic compatibility/serializer audit;
- the shared iOS-valid/double-profile fixture gate;
- real LRP asset/static-authority byte and hash binding, with no zero-hash
  placeholder;
- all remaining mechanical checks; and
- the final gate: after all Plan 1 mechanical checks, output the final SHA-256
  and exact literal `Plan 1 frozen`, then make no further byte changes.

POP returns to the S70 Unified Golf Program Execution Index. The next bounded
packet is 5B2a-S, which owns generated V1 shape/codec authority. It must be
activated alone and receive its own bounded card before TDD. This verification
does not authorize graph, algorithm, supported-decoder, persistence, mutation,
lifecycle, migration or network work.
