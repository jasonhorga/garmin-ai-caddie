# Plan 1 Task 5B1 Storage-v1 Literals Verification

Date: 2026-07-25 UTC

Verified production candidate: `486d2e354c43c1a4754b18c8dbdf76eeca7f4657`

Production candidate tree: `64688a7234ef8a4584c81242d89537519e3338e7`

Card baseline: `083f850c553d43c95a0a751254de49c623df812e`

Card-baseline tree: `904c0576158378774a872302c434454299adcc41`

## Frozen authority and bounded outcome

The approved design is
`../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md`, SHA-256
`f31a090fe9c4dc37828f25ee3528afd067d7222128606514b2cfe74229dc2b05`.
The bounded implementation card is
`../task-cards/2026-07-25-plan1-task5b1-storage-v1-literals.md`, SHA-256
`87a2f22ede270b6639711c239fdd871775424e8b6b05476a825bad52fbe33c71`.
Both hashes were independently recomputed at the card baseline and production
candidate.

5B1 provides only the internal, immutable storage-v1 literal/value language:

- the historical `StoredEventV1` row;
- `OriginSequenceState`, the deterministic `CanonicalStringSet`, and the exact
  12-key `DomainLedgerStateV1` root with literal version `1`;
- the legacy-v1 binding, prepared-batch, receipt, outbox, anomaly, Watch relay,
  and exact two-key backend body values;
- required fields and required-nullable outbox fields;
- source-order preservation for every order-bearing array; and
- a surgical authority exception for the diagnostic legacy
  `serverSequence` field in `LegacyV1Transport.swift` only.

The exact card range changes ten paths: three production Swift files, two
XCTest files, one Python mechanical test, `authority.json`, and the three
generated contract outputs. The production files and both XCTest files plus
the Python test byte-match the card's frozen source blocks. The generated files
change only their common source digest:
`df9d1b3810eca3a1bf0523bc0fbc5ad5ae65a5023c85010f014e9f64c74d97c3`.

5B1 deliberately does not provide raw hostile-JSON parsing, generated recursive
shape authority, graph validation, a supported storage decoder, identity/hash
or request algorithms, ownership, persistence, mutation, lifecycle, network,
response application, or the final rich fixture. Those remain assigned to
5B2a-R, 5B2a-S, 5B2b-L, 5B2b-T, and later Task 5 packets.

## Production and TDD history

The exact card-to-candidate history is linear:

| Stage | Commit | Tree | Purpose |
|---|---|---|---|
| CARD | `083f850c553d43c95a0a751254de49c623df812e` | `904c0576158378774a872302c434454299adcc41` | activate the bounded 5B1 card |
| test-only RED | `a7810317f8f8f5554a042863e729a21811f4f72b` | `82492cebc5ff61157a6773f3609bf49d9de73b2d` | define the complete wished-for tests before production types exist |
| behavioral RED | `3eeca293a47484ac350474baa0845eba74f7f1f0` | `285d605a6644c869c6e7c01da06b4d226c151bf7` | compile-safe declarations expose value-behavior and authority failures |
| GREEN input | `bdb7d8a94773fcf79e65843b856291a61ad1581a` | `7f7b6557514201f0d80dba0637a45101f95e7e08` | implement the minimal values and authority input |
| generated candidate | `486d2e354c43c1a4754b18c8dbdf76eeca7f4657` | `64688a7234ef8a4584c81242d89537519e3338e7` | regenerate all three derived outputs |

The final generator commit was created in the original fresh homeserver
generator clone from exact input `bdb7d8a9`, pushed to the unique generated
evidence ref, and integrated into the control branch by a recorded fast-forward.
The homeserver's stale HTTPS credential store caused an initial authentication
failure before any remote write. Recovery used a control credential only through
an ephemeral stdin-fed helper, with no printed token, persistence, or Git config
change. The failed/preflight/cancelled probe refs remain absent; the valid
generated and GREEN refs resolve to the exact candidate.

## RED evidence

### Test-only RED

At `a7810317`, the fresh homeserver mechanical suite ran 93 tests and produced
exactly six controlled failures with zero errors because the three production
files and authority exception did not exist. The preserved log is:

`/home/jason/codex-runs/task5b1-red-tests-a7810317f8f8f5554a042863e729a21811f4f72b-JAOYPd/mechanical-red.log`

It contains 152 lines and 21,594 bytes; SHA-256:
`6af065fe195fd3a3e05ddee72ee401ad42147b9eca63a4f0137567925f42bf01`.

Native run
[`30160187606`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30160187606),
job `89684151147`, checked out the same exact RED SHA and failed at the intended
missing literal symbols. Its 3,321-line, 740,453-byte preserved log has SHA-256
`6925b2aba73e08decd19c9799eb52bdd05ccdd610e8587c4c003798de2076c03`.

### Compile-safe behavioral RED

At `3eeca293`, the fresh homeserver suite again ran 93 tests and produced
exactly two controlled authority failures with zero errors. The 127-line,
18,741-byte log is:

`/home/jason/codex-runs/task5b1-red-behavior-3eeca293a47484ac350474baa0845eba74f7f1f0-NNQLsb/mechanical-red.log`

Its SHA-256 is
`4fecc517a5fe724a80e57d855e4f44f5d07eccb4352f9ddbec72db1d56c812d1`.

Native run
[`30160359179`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30160359179),
job `89684576512`, compiled the seam and ran 30 Domain tests with nine intended
behavior failures: storage version, deterministic set, explicit-null/missing
nullable keys, and exact value shapes. The pre-existing iOS suite remained
108/108 green. The 4,909-line, 1,130,643-byte log SHA-256 is
`f3e719f977260e3f2a3e2ee3e5c6200188bc63cdb7045b04d3396b9c277c81e6`.

## Homeserver GREEN and mechanical evidence

The production candidate was fetched into the fresh exact-SHA clone:

`/home/jason/codex-runs/task5b1-remote-486d2e354c43c1a4754b18c8dbdf76eeca7f4657-97LiPk`

Inside that clone, `CARD_SHA` was recomputed from Git history rather than
inherited from the control shell. The focused literal-schema, Swift canonical
runtime, code-generation, and authority suites passed 107/107. Regeneration
produced zero diff; the exact changed-path authority check and `git diff
--check` exited zero; final status remained empty.

The preserved 124-line, 19,584-byte log is:

`/home/jason/codex-runs/task5b1-remote-486d2e354c43c1a4754b18c8dbdf76eeca7f4657-97LiPk.log`

Its SHA-256 is
`9267acc4f753a28599728a3908d5cf7299ee1d1efe2f294c67d11de2884c1d46`.

Independent source auditing confirmed that `serverSequence` occurs once in
production, at `LegacyV1Transport.swift`, and remains forbidden everywhere
else. The three generated outputs contain the same independently recomputed
digest and no other generated difference.

## Native exact-SHA GREEN evidence

Native Mobile CI run
[`30161049015`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30161049015),
job `89686311088`, completed successfully at exact candidate
`486d2e354c43c1a4754b18c8dbdf76eeca7f4657` on `macos-15`, with no failed
step:

- `DomainLedgerStateV1Tests`: 5/5;
- `LegacyV1TransportTests`: 6/6;
- complete `AICaddieDomainTests`: 30/30;
- complete iOS `AICaddieTests`: 108/108;
- complete `AICaddieWatchTests`: 66/66; and
- live iOS UI tests: 3/3.

All counts have zero failures. The SwiftJCS boundary step built the supported
Domain wrapper consumer, recorded the expected source-build audit behavior,
proved that the copied framework contains no separate SwiftJCS module/library,
and observed the required `no such module 'SwiftJCS'` diagnostic for a direct
artifact consumer.

The complete 9,172-line, 2,043,511-byte job log is preserved at:

`/home/jason/codex-runs/task5b1-native-486d2e354c43c1a4754b18c8dbdf76eeca7f4657-run-30161049015.log`

Its SHA-256 is
`d8bcf04aacebdb80bb7c8c0134bb0b62267b767c2498e0a56953d087bcd86b45`.

The run uploaded six artifacts. `native-build-evidence` artifact `8620469310`
pins the exact commit, run ID, both schemes and simulator destinations, and a
`passed` status for iOS and Watch. The downloaded ZIP SHA-256 is
`26ceecc04cafb922ebc9648f6348fd047ca2e809d02dcdc2fa1392ca7e8a0fe3`;
the extracted JSON SHA-256 is
`f856e39687dfe0cbb15b045bfd088e16122f45384ad04d8979c1d1aa736ae51f`.

## Independent reviews

The fresh read-only specification reviewer inspected the exact card range and
then re-confirmed its verdict after authenticating the terminal Native log and
artifacts: `SPEC PASS`, Critical 0, Important 0. It authenticated the frozen
hashes, base/head/trees, exact ten-path range, byte-matching declarations and
tests, narrow authority exception, generated digest, RED history, and complete
REMOTE evidence. It found no extra or missing 5B1 scope.

Only after SPEC passed, a different fresh read-only quality reviewer inspected
the same exact range and terminal evidence. It reported `QUALITY PASS`,
Critical 0, Important 0, Minor 0. It independently checked Codable symmetry,
required and required-nullable error paths, Unicode ordering, immutable/internal
API boundaries, manifest semantics, generated drift, test strength, TDD
history, and complete Native evidence. No correction or remediation commit was
required.

## Gate result and POP

Plan 1 Task 5B1 satisfies the Execution Index definition of `VERIFIED` at
production candidate `486d2e3`: frozen requirements and exclusions, observed
test-only and behavioral REDs, production values, fresh homeserver GREEN,
exact-SHA Native GREEN, clean SPEC and QUALITY reviews, and dedicated commits
all exist with no open Critical or Important issue.

POP returns to the S70 Unified Golf Program Execution Index. The next bounded
packet is 5B2a-R, the non-public raw JSON gate. This result does not verify the
generated V1 shape/codec, ledger or transport graph, any supported decoder, the
rest of Task 5B, Task 5, or Plan 1. In particular, it does not satisfy the
standing strict-Pydantic mechanical audit or authorize the declaration
`Plan 1 frozen`.
