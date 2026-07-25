# Plan 1 Task 5B2a-S — Generated storage-v1 shape codec

**Date:** 2026-07-25
**Status:** Frozen execution card; Task 5B2a-S is not yet implemented

## Authority and bounded outcome

This card is subordinate to the [Program execution index](../plans/2026-07-23-program-execution-index.md), the [Task 5 packet map](2026-07-24-plan1-task5-packet-map.md), and the [storage-v1 schema design](../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md). Those three documents remain the authority for program order, packet boundaries, and the storage-v1 schema decisions respectively.

This card freezes only packet Task 5B2a-S and does not reopen any accepted architecture decision. Owner decision: none. Task 5B2a-R is verified and unchanged; no Task 5B2a-R source, test, fixture, or acceptance evidence is in this packet's write set.

Task 5B2a-S accepts only `ValidatedRawJSON`; the raw JSON gate remains the sole syntactic and resource-safety entry boundary. The codec must not accept bytes, text, Foundation JSON objects, or an unvalidated `JSONValue` as an alternate input. S owns the exact persisted storage-v1 shape, exact path-scoped policies, generated Swift shape descriptors, and internal typed decode into the declared storage records.

The typed result is internal implementation surface, and this packet does not publish a supported decoder. Task 5B2b-T later owns the supported composed decoder combining the R gate, S shape codec, and later semantic stages in the authorized order. Task 5B2a-S excludes graph validation, ledger algorithms/state-transition logic, mutation/persistence writes, request construction/network behavior, and any public decoder or public convenience entry point.

Shape validation must not infer semantic relationships or event applicability, nor repair, default, coerce, or normalize an accepted value. Completion does not complete Task 5B, Task 5, or Plan 1; those scopes remain incomplete pending their separately frozen packets and evidence.

## File ownership, schema grammar, and generated group

### Exact write set

Create exactly these files:

- `contracts/storage-v1/domain_ledger_storage_shapes_v1.json`
- `tools/contracts/generate_storage_v1_shape.py`
- `mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift`
- `mobile/ios/AICaddieDomain/StorageV1ShapeCodec.swift`
- `tests/test_storage_v1_shape_codegen.py`
- `tests/test_storage_v1_shape_codec_assets.py`
- `mobile/ios/AICaddieDomainTests/StorageV1ShapeCodecTests.swift`

Modify exactly these existing authority and asset-test files:

- `contracts/canonical/authority.json`
- `tests/test_storage_v1_literal_schema_assets.py`

Because `contracts/canonical/authority.json` changes, run its canonical generator once and regenerate exactly these three existing outputs:

- `ai_caddie/contracts/generated.py`
- `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- `web_v2/src/contracts/generated.ts`

The regenerated files may contain only the deterministic consequences of the authority change; they are not an invitation to edit canonical contract content.

Do not modify any of the following:

- `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift`
- `mobile/ios/AICaddieDomain/CanonicalJSON.swift`
- `mobile/ios/AICaddieDomain/JSONValue.swift`
- any Task 5B1 literal source
- any SwiftJCS source
- `Package.swift`
- `project.yml`
- any workflow
- any fixture

Every other path is outside the packet write set.

### Separate generated group

Register a distinct storage-v1 generated group whose sources are exactly:

- `contracts/storage-v1/**/*.json`
- `tools/contracts/generate_storage_v1_shape.py`

Its sole output is:

- `mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift`

The storage-v1 group remains outside `canonicalRoots`; its schema is not a canonical wire-contract root, and its output must not be folded into any of the three canonical generated files.
Every descriptor declaration and constant in `GeneratedStorageV1Shape.swift` is `internal`, never `public`, `package`, or SPI; Task 5B2b-T may reuse it only inside the same module. This output only describes/references the existing 5B1 17-type roster and must not redeclare or shadow `DomainLedgerStateV1`, its records, `JSONValue`, `RoundEventKind`, or any other domain value type; asset audits prove both restrictions.
Like the canonical generator, the sole output embeds an internal source SHA-256 over stable length-prefixed relative paths plus exact bytes for every group schema JSON and `generate_storage_v1_shape.py`; without another provenance file, tests prove path/content sensitivity (including whitespace and generator changes), byte-identical repeated generation, legitimate deterministic sole-output drift, and no storage-only change to the three public canonical digests.

Add `GeneratedStorageV1Shape.swift` as the second surgical `serverSequence` exclusion, beside `LegacyV1Transport.swift`.
That exclusion covers a literal-only receipt diagnostic field; it does not authorize server-sequence ordering, comparison, or transport semantics in storage decoding.
The asset test mechanically proves that readable generated `serverSequence` occurs only as the `LegacyV1EventReceipt` diagnostic field.
The generator must emit that spelling directly and must never hide it with token splicing, escaped fragments, encoded text, or another obfuscation.

### Closed descriptor grammar

`domain_ledger_storage_shapes_v1.json` is the sole machine-readable descriptor graph for this packet. The graph is closed: every named reference resolves inside the declared type roster, every definition is reachable from a declared root, and no undeclared descriptor kind or member is accepted.

The grammar supports named record descriptors, a named collection descriptor for existing `CanonicalStringSet`, an open-string descriptor, a closed-enum descriptor, and recursive `JSONValue`; it adds no 18th alias/helper type.
It supports generic constrained wrappers for arrays, dynamic maps, nullable values, and values carrying a named path policy or limit profile.

Wrappers remain structural and composable; the generator must not encode one-off field-name branches where a generic wrapper expresses the same rule.
A reference wrapped as nullable remains the same referenced type with explicit-null permission; it does not become an optional field.

The descriptor declares exactly these roots:

- `storageDocument` -> `DomainLedgerStateV1` (`S` consumes this root)
- `legacyV1EventBatchBody` -> `LegacyV1EventBatchBody` (generated for `T`; `S` does not consume this root)

The closed roster contains exactly these 17 types:

1. `StoredEventV1`
2. `OriginSequenceState`
3. `CanonicalStringSet`
4. `DomainLedgerStateV1`
5. `LegacyDomainAlias`
6. `LegacyWireBinding`
7. `PreparedLegacyV1Slot`
8. `PreparedLegacyV1Batch`
9. `LegacyV1TerminalStatus`
10. `LegacyV1EventReceipt`
11. `LegacyV1OutboxRecord`
12. `LegacyV1TransportAnomaly`
13. `WatchTerminalReceiptRelayObligation`
14. `WatchTerminalReceiptRelayConfirmation`
15. `LegacyV1EventBatchBody`
16. `RoundEventKind`
17. `JSONValue`

No additional helper record, alias, enum, or root may be introduced into the descriptor graph.

The exact generated field/type roster is:

| Type | Exact representation |
|---|---|
| `StoredEventV1` | `eventId: String`; `originDeviceId: String`; `originEpoch: String`; `clientSequence: Int`; `roundId: String`; `kind: RoundEventKind`; `payload: dynamic map String -> JSONValue`; `occurredAt: String` |
| `OriginSequenceState` | `originDeviceId: String`; `originEpoch: String`; `lastReservedClientSequence: Int` |
| `CanonicalStringSet` | `[String]`, already sorted and unique |
| `DomainLedgerStateV1` | `storageVersion: literal Int = 1`; `origin: OriginSequenceState`; `events: [StoredEventV1]`; `outbox: [LegacyV1OutboxRecord]`; `deadLetters: [LegacyV1OutboxRecord]`; `receipts: dynamic map String -> LegacyV1EventReceipt`; `legacyWireBindings: [LegacyWireBinding]`; `preparedLegacyV1Batches: [PreparedLegacyV1Batch]`; `watchTerminalReceiptRelayObligations: [WatchTerminalReceiptRelayObligation]`; `watchTerminalReceiptRelayConfirmations: [WatchTerminalReceiptRelayConfirmation]`; `migrationMarkers: CanonicalStringSet`; `transportAnomalies: [LegacyV1TransportAnomaly]` |
| `LegacyDomainAlias` | `eventIdentity: String`; `eventHash: String` |
| `LegacyWireBinding` | `roundId: String`; `wireClientId: String`; `wireEventId: String`; `canonicalDomainIdentity: String`; `canonicalDomainEventHash: String`; `normalizedWireEnvelopeHash: String`; `legacyAliases: [LegacyDomainAlias]` |
| `PreparedLegacyV1Slot` | `bindingKey: String`; `exactNormalizedEnvelope: JSONValue`; `exactNormalizedEnvelopeHash: String` |
| `PreparedLegacyV1Batch` | `roundId: String`; `orderedSlots: [PreparedLegacyV1Slot]`; `exactRequestBody: Base64 text / typed Data`; `requestBodySha256: String`; `idempotencyKey: String` |
| `LegacyV1TerminalStatus` | closed enum: `accepted`, `duplicate_hash_match`, `rejected_permanent` |
| `LegacyV1EventReceipt` | `eventIdentity: String`; `eventHash: String`; `status: LegacyV1TerminalStatus`; `serverSequence: Int` |
| `LegacyV1OutboxRecord` | `eventIdentity: String`; `eventHash: String`; `receipt: required-nullable LegacyV1EventReceipt`; `deadLetterReason: required-nullable String` |
| `LegacyV1TransportAnomaly` | `roundId: String`; `code: String`; `evidence: String` |
| `WatchTerminalReceiptRelayObligation` | `obligationId: String`; `eventIdentity: String`; `eventHash: String`; `status: LegacyV1TerminalStatus` |
| `WatchTerminalReceiptRelayConfirmation` | `confirmationId: String`; `obligationId: String`; `eventIdentity: String`; `eventHash: String`; `status: LegacyV1TerminalStatus` |
| `LegacyV1EventBatchBody` | `roundId: String`; `events: [JSONValue]` |
| `RoundEventKind` | open string |
| `JSONValue` | recursive null / bool / integer / number / string / array / object |

### Shape semantics

Every record field is required, so a missing field is a shape failure. Every generated record is closed, so an unknown field is also a shape failure.

Nullable is explicit-null semantics only: the key remains required, and its value is either JSON `null` or matches the wrapped descriptor.

`RoundEventKind` is an open string that preserves unfamiliar values. `LegacyV1TerminalStatus` is a closed enum that rejects values outside its declared cases.

`JSONValue` is recursive and retains the existing model. Receipt and payload maps are dynamic maps with arbitrary data keys and descriptor-constrained values; their keys are not undeclared record fields.

`CanonicalStringSet` is typed and must already be canonically sorted and unique. The sole final typed decode rejects unsorted or duplicate representations without sorting or deduplicating them.

### Exact path-policy roster

The `rootCollection` policy applies to exactly these `DomainLedgerStateV1` paths:

- `events`
- `outbox`
- `deadLetters`
- `receipts`
- `legacyWireBindings`
- `preparedLegacyV1Batches`
- `watchTerminalReceiptRelayObligations`
- `watchTerminalReceiptRelayConfirmations`
- `migrationMarkers`
- `transportAnomalies`

The `preparedSlots` policy applies only to:

- `preparedLegacyV1Batches[*].orderedSlots`

The `requestBody` policy applies only to:

- `preparedLegacyV1Batches[*].exactRequestBody`

The `eventOrEnvelope` policy applies only to:

- `events[*]`
- `preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`

Do not constrain `LegacyV1EventBatchBody.events` or globally constrain `JSONValue`; a matching field name elsewhere inherits no policy. Contextual policies are embedded constrained nodes, with no runtime wildcard/path-string matcher. Generator tests flatten the graph and assert this exact roster before Swift emission.

### Exact limits

Each `rootCollection` has maximum count `65,536`; `preparedSlots` count is `1...64`; ordinary strings are at most `4,096` Unicode scalars; Base64 text is at most `1,398,104` Unicode scalars.
Decoded request bodies are at most `1,048,576` bytes; `eventOrEnvelope` canonical encodings are at most `65,536` bytes and relative depth is at most `16`.

Generated descriptor/runtime code references Task 5B2a-R's `StorageV1RawJSONGate.maximumStringScalars` for the `1,398,104` request-body Base64 text cap, and matching `RoundTransportLimits` symbols for decoded-body bytes, slots, event/envelope canonical bytes and depth, and ordinary strings. Only the `65,536` root-collection count is a new storage literal; neither `1,398,104` nor any existing transport limit may be copied into a shadow constant.

Counts are checked before per-element descent where possible. String limits count Unicode scalars, not UTF-8 bytes or UTF-16 code units. Canonical byte/depth checks apply only at the two `eventOrEnvelope` paths.

### Generator rejection contract

Descriptor-source parsing rejects every duplicate JSON object member/key at every level before exact top-key/grammar validation; ordinary last-wins loading is forbidden. The generator also rejects duplicate definitions; unknown definitions, members, references, policies, or profiles; and malformed definitions, references, policies, or profiles.

The generator rejects incompatible constraints, policy paths unreachable from the applicable root, wrong-shaped policy targets, and unused or unreachable policy nodes.

Generation uses stable traversal/emission, rejects nondeterministic input structures, and produces byte-identical Swift for the same accepted source bytes and generator version.

## Runtime invariants and capability API

### Internal capability surface

The only codec entry point is exactly:

```swift
internal static func decode(
    _ validatedRawJSON: StorageV1RawJSONGate.ValidatedRawJSON
) throws -> ValidatedStorageV1Shape
```

`ValidatedStorageV1Shape` is an internal capability with an internal read-only `state: DomainLedgerStateV1` property and a `fileprivate` initializer. Only the successful codec path can construct it.

There is no public overload and no `Data`, `String`, `JSONValue`, or `JSONDecoder` bypass overload. Task 5B2b-T remains the owner of the later supported composed decoder.

The codec consumes only the generated `storageDocument` root. The generated `legacyV1EventBatchBody` root is present for later composition but remains unused until Task 5B2b-T.

### One replay and streaming shape descent

The codec performs exactly one replay pass over the cursor capability supplied by Task 5B2a-R. Shape validation uses streaming event descent with at most one event of lookahead and does not construct a second syntax tree or retain a token array.

The implementation must not use `JSONSerialization` or build a dictionary from hostile object keys during streaming validation. Generated ASCII field keys are compared directly as UTF-8 bytes.

Hostile key and value text is checked for NFC before Swift `String` equality, dictionary-key insertion, storage as a key/value, domain materialization, or the final typed decode.
A short-lived Swift `String` may be constructed from Task 5B2a-R's already validated decoded UTF-8 solely to perform that NFC check. Its precomposed mapping is encoded as UTF-8 and compared byte-for-byte with the original decoded bytes; until equality succeeds, the transient value must not be retained, compared as text, or inserted into a dictionary.
This uses Foundation's existing normalization behavior rather than introducing another Unicode-normalization engine, and prevents canonically equivalent hostile keys from collapsing before rejection.

Bounded recursive streaming descent is permitted because Task 5B2a-R caps accepted raw JSON depth at `64`. Recursion may track the active shape and bounded metrics only; it must not accumulate an AST or unbounded path history.

### Canonical metrics and final typed decode

Canonical byte and relative-depth metrics are computed bottom-up at the constrained nodes.
Byte totals include escaped object keys, escaped strings, canonical number spellings, container delimiters, commas, and colons.

Object sorting is unnecessary for size because member order does not change the sum of those canonical components. All metric arithmetic uses checked or saturating addition and fails at the configured bound instead of overflowing. A shared metric corpus cross-checks the streaming totals against the existing `CanonicalJSON` implementation.

After every shape and contextual-policy check succeeds, the codec performs exactly one final root `JSONDecoder` decode into `DomainLedgerStateV1`.
That is the sole typed materialization and the sole point where `CanonicalStringSet` sorted/unique conformance is rejected; no intermediate typed decode is allowed.

### Base64 request-body validation

`exactRequestBody` Base64 is validated while its string token is visited. The validator accepts only the standard alphabet and standard padding, with no whitespace and no missing padding.

The text-length limit is checked before decoded-data preallocation, and the decoded-byte limit is checked before or during allocation.
Validation decodes the token, performs an exact standard Base64 re-encode comparison, and discards the temporary decoded `Data` immediately.

An empty Base64 string is valid in Task 5B2a-S; whether a request body is semantically allowed to be empty belongs outside this shape packet.

### Number and integer validation

Every number lexeme is raw-resource-guarded first. An `Int` descriptor requires an integer-shaped raw token parsed exactly to `Int64`, then platform `Int`, then `CanonicalJSON.data(JSONValue.integer(...))`, with canonical/raw bytes equal; integer fields never accept fractional or exponent spelling.
In recursive `JSONValue`, raw token `1` still takes that integer route. A number token that cannot parse as an exact raw `Int64` must convert exactly to a finite `Double`, pass `CanonicalJSON.data(JSONValue.number(...))`, and equal the raw bytes; no path uses an intermediate `JSONDecoder`, handwritten formatter, or shadow bound.
When platform-representable, inclusive integers `±9,007,199,254,740,991` pass; `±9,007,199,254,740,992` and `Int64.min/max` fail the existing unsafe-canonical-integer policy, while values outside `Int64` fail exact conversion. Canonical `1.5`, `1e-7`, `5e-324`, and existing RFC 8785 corpus representatives pass as recursive numbers; equal-value noncanonical `1.0`/`1e0`, negative zero, overflow/nonfinite conversion, and unsafe integral values fail.

Task 5B2a-S enforces only shape and the frozen contextual resource policies. It adds no graph, hash, identity, or domain-range semantics.

## TDD and mutation test matrix

### Stage A — CODEGEN-RED

The first implementation commit is tests only. It proves the generated file is absent and that repeated generation must be byte-identical.
The schema test asserts the exact top-key set rather than presence-only checks.

It asserts the two exact declared roots, the exact 17-type roster, every record field, every scalar/ref/array/dynamic-map/nullable/constrained wrapper, and every open/closed distinction.
It flattens embedded constrained nodes and compares the complete policy roster exactly.

The malformed-generator corpus covers duplicate JSON keys at the top level and inside type/member, policy, and profile objects, plus duplicate, unknown, malformed, and dangling definitions, references, policies, and profiles.
It also covers incompatible constraints, unreachable policy nodes, wrong-shaped policy targets, and nondeterministic input structures.

Authority tests require a separate storage-v1 generated group outside `canonicalRoots`, and pin the one-time digest changes for all three canonical outputs caused by `authority.json`. A mutation of only a storage-v1 schema source must leave every public canonical digest stable.

The literal audit allows the second surgical `serverSequence` exception only in readable generated receipt-field context. It fails obfuscation, another generated occurrence, or a use outside the diagnostic field.

The focused CODEGEN-RED run must fail for the expected missing schema/generator/generated-asset behavior.

### Stage B — CODEGEN-GREEN

The same sole writer creates the storage schema, generator, generated Swift output, and manifest/asset-test changes frozen in the write set. The writer performs the one-time regeneration of the three canonical outputs.

Generation twice must be byte-identical. All focused codegen and asset modules must become green before runtime test work starts. No runtime codec behavior is implemented in this stage.

### Stage C — RUNTIME-RED

Add the final asset assertions and XCTest API/behavior suite. Add only the compile-safe runtime seam required to discover those tests, with the codec throwing its internal `.notImplemented` error; that seam is permitted only at the exact RUNTIME-RED commit.

Dispatch Native at the exact RUNTIME-RED commit SHA through a unique evidence branch.
Native must compile and discover the suite, then fail for the expected codec behavioral assertion rather than compilation, linkage, workflow, or test-discovery failure.

### Stage D — RUNTIME-GREEN

Implement the production streaming validator and sole final typed decode. Stage D removes the `.notImplemented` throw seam and preferably its error case; final source/asset audits reject any production occurrence or reachable stub. Make focused Python and XCTest coverage green without weakening any RED assertion.

### Positive and negative vectors

The runtime matrix includes both a minimal root and a representative root containing every record family.
It accepts an unfamiliar `RoundEventKind` string and every closed terminal status value.

For every record family it isolates missing, extra, wrong-type, and forbidden-null mutations.
Required-nullable fields separately prove present-null success and missing-key failure.

Dynamic receipt and payload maps accept hostile data keys only after NFC validation. Key/value vectors cover the permitted short-lived validation `String`, exact precomposed-UTF-8 comparison, no pre-success retention/equality/dictionary insertion, NFC success, and non-NFC rejection without canonical-equivalent key collapse.

An ordinary string of `4,096` scalars passes and `4,097` fails. Each named root collection passes at `65,536` elements and fails at `65,537`. An unrelated nested array is not given the root-collection limit.

Prepared slots fail at `0`, pass at `1` and `64`, and fail at `65`.

Base64 vectors cover canonical text, noncanonical text, whitespace, missing padding, empty text, the text preallocation boundary, and the decoded-body byte boundary.

Number vectors distinguish integer-field, recursive-integer, and recursive-Double routes: they accept `1`, platform-representable `±9,007,199,254,740,991`, canonical `1.5`, `1e-7`, `5e-324`, and RFC 8785 representatives; they reject fractional/exponent integer fields, `1.0`, `1e0`, negative zero, `±9,007,199,254,740,992`, `Int64.min/max`, overflow/nonfinite conversion, and outside-`Int64` hostile lexemes, with narrower platform `Int` failing only after exact `Int64` parse.

Canonical event/envelope bytes pass at `65,536` and fail at `65,537`. Relative depth passes at `16` and fails at `17`. The same shapes prove those constraints apply only to `events[*]` and `preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`.

`LegacyV1EventBatchBody.events` and unrelated `JSONValue` nodes remain unconstrained by `eventOrEnvelope`. Sorted unique `CanonicalStringSet` values pass at the final typed decode; unsorted and duplicate values fail only there.

Source audits enforce one cursor replay, one final root decoder, no AST or retained token array, no `JSONSerialization`, no runtime wildcard/path matcher, no bypass overload, no hostile `String` retention/comparison before the exact NFC byte check, and internal-only generated descriptors with no public/package/SPI exposure.

Every negative vector changes exactly one relevant property and isolates one expected rejection reason.

## Serial evidence, remote commands, review, and freeze

All commands here are planned, not already run. The local machine is limited to Git, text inspection, and SSH transport; all tests, builds, generation, and dependency work run in a unique homeserver scratch or CI.
After complete logs/hashes are recorded, delete only this packet's exact `mktemp` result after asserting its `/home/jason/codex-runs/` prefix; a failed run may remain through diagnosis, but closeout inventories and removes every packet-created scratch and never cleans an unfamiliar directory, process, or ref.
Transient GitHub/SSH `429`, `503`, or cooldown responses receive timed exponential-backoff retries with the same SHA/ref/dispatch binding; safe audits may continue while waiting, but transient service state is neither RED, completion, nor a permanent blocker.

### 1. Freeze and review the card

Before sending an initial candidate or any same-writer correction to review, run this local text/Git block from the repository root to audit the one dirty card path and create its one-file commit. Reviewers receive committed bytes only.

```bash
CARD=docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-s-generated-shape-codec.md
LINES=$(wc -l < "$CARD")
test "$LINES" -ge 380
test "$LINES" -le 560
test "$(rg -c '^## ' "$CARD")" -eq 5
rg '^## ' "$CARD"
rg -n 'program-execution-index|task5-packet-map|task5b-storage-v1-schema-design' "$CARD"
test "$(git status --short | wc -l)" -eq 1
git status --short
git diff --check
printf '%s  %s\n' 'f31a090fe9c4dc37828f25ee3528afd067d7222128606514b2cfe74229dc2b05' 'docs/superpowers/specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md' | sha256sum --check --strict
git add -- "$CARD"
test "$(git diff --cached --name-only)" = "$CARD"
git diff --cached --check
git commit -m 'docs: freeze Plan 1 Task 5B2a-S card' -- "$CARD"
git show --stat --oneline HEAD
sha256sum "$CARD"
```

Each resulting committed SHA receives fresh SPEC review first and different fresh QUALITY review second. A finding returns to the same sole writer, who corrects the card, reruns the block to create a new committed SHA, and obtains both fresh reviews again.
After both reviewers accept the same exact committed bytes, do not rerun the dirty/commit block or alter the card. Confirm the worktree is clean, record that final card commit and SHA-256, and freeze it; the lexical audit rejects unfinished-marker vocabulary and obsolete uppercase packet spelling without weakening the required `.notImplemented` RED seam.

### 2. Prove CODEGEN-RED remotely

Commit only the Stage A tests, then push a unique evidence ref that contains the commit SHA. The homeserver must start from that GitHub ref in a fresh SHA-named scratch; no working-tree overlay is allowed.

```bash
set -euo pipefail
CARD=docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-s-generated-shape-codec.md
RED_SHA=$(git rev-parse HEAD)
CARD_COMMIT=$(git log -1 --format=%H -- "$CARD")
RED_REF="refs/heads/evidence/plan1-task5b2as-codegen-red-$RED_SHA"
git push origin "$RED_SHA:$RED_REF"
test "$(git ls-remote --heads origin "$RED_REF" | awk 'NR == 1 {print $1}')" = "$RED_SHA"
ssh homeserver 'free -h; df -h "$HOME"; uptime'
RED_LOG="/tmp/task5b2as-codegen-red-$RED_SHA.log"
set +e
ssh homeserver bash -s -- "$RED_SHA" "$RED_REF" "$CARD_COMMIT" 2>&1 <<'REMOTE' | tee "$RED_LOG"
set -euo pipefail
SHA=$1; REF=$2; CARD_COMMIT=$3
RUN_DIR=$(mktemp -d "/home/jason/codex-runs/task5b2as-codegen-red-${SHA}-XXXXXX")
printf 'RUN_DIR=%s\n' "$RUN_DIR"
git clone --quiet --no-checkout https://github.com/jasonhorga/garmin-ai-caddie.git "$RUN_DIR"
cd "$RUN_DIR"
git fetch --quiet origin "$REF"
git checkout --quiet --detach "$SHA"
test "$(git rev-parse HEAD)" = "$SHA"
git merge-base --is-ancestor "$CARD_COMMIT" HEAD
test -z "$(git status --porcelain=v1)"
set +e
/home/jason/.local/bin/uv run python -m unittest -v tests.test_storage_v1_shape_codegen tests.test_storage_v1_shape_codec_assets tests.test_storage_v1_literal_schema_assets tests.test_contract_authority tests.test_contract_codegen
TEST_STATUS=$?
set -e
printf 'TEST_EXIT=%s\n' "$TEST_STATUS"
exit "$TEST_STATUS"
REMOTE
RED_STATUS=${PIPESTATUS[0]}
set -e
printf 'SSH_EXIT=%s\n' "$RED_STATUS" | tee -a "$RED_LOG"
test "$RED_STATUS" -ne 0
for EXPECTED in domain_ledger_storage_shapes_v1.json generate_storage_v1_shape.py GeneratedStorageV1Shape.swift; do rg -F "$EXPECTED" "$RED_LOG"; done
if rg -n 'ModuleNotFoundError|ImportError|No module named|command not found|FAILED \(errors=' "$RED_LOG"; then exit 1; fi
wc -l -c "$RED_LOG"
sha256sum "$RED_LOG"
```

The nonzero status is valid RED only when controlled assertions name the intentionally absent schema, generator, and generated asset; both existing manifest/codegen gates must pass, and their regression or any import, checkout, command, or infrastructure failure invalidates RED. Preserve the full log, status, assertion text, test/failure/error counts, scratch path, and log SHA-256.

### 3. Prove CODEGEN-GREEN remotely

Commit Stage B, push its own immutable SHA-bearing ref, run the homeserver pressure check, and use another fresh GitHub clone under `/home/jason/codex-runs`. The clone must prove exact HEAD, card ancestry, and initial cleanliness before generation.

```bash
set -euo pipefail
GREEN_SHA=$(git rev-parse HEAD)
CARD_COMMIT=$(git log -1 --format=%H -- docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-s-generated-shape-codec.md)
GREEN_REF="refs/heads/evidence/plan1-task5b2as-codegen-green-$GREEN_SHA"
git push origin "$GREEN_SHA:$GREEN_REF"
test "$(git ls-remote --heads origin "$GREEN_REF" | awk 'NR == 1 {print $1}')" = "$GREEN_SHA"
ssh homeserver 'free -h; df -h "$HOME"; uptime'
GREEN_LOG="/tmp/task5b2as-codegen-green-$GREEN_SHA.log"
set +e
ssh homeserver bash -s -- "$GREEN_SHA" "$GREEN_REF" "$CARD_COMMIT" 2>&1 <<'REMOTE' | tee "$GREEN_LOG"
set -euo pipefail
SHA=$1; REF=$2; CARD_COMMIT=$3
RUN_DIR=$(mktemp -d "/home/jason/codex-runs/task5b2as-codegen-green-${SHA}-XXXXXX")
printf 'RUN_DIR=%s\n' "$RUN_DIR"
git clone --quiet --no-checkout https://github.com/jasonhorga/garmin-ai-caddie.git "$RUN_DIR"
cd "$RUN_DIR"
git fetch --quiet origin "$REF"
git checkout --quiet --detach "$SHA"
test "$(git rev-parse HEAD)" = "$SHA"
git merge-base --is-ancestor "$CARD_COMMIT" HEAD
test -z "$(git status --porcelain=v1)"
for PASS in 1 2; do
  python3 tools/contracts/generate_contracts.py
  python3 tools/contracts/generate_storage_v1_shape.py
  git diff --exit-code -- ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift
  test -z "$(git status --porcelain=v1)"
done
sha256sum ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift
/home/jason/.local/bin/uv run python -m unittest -v tests.test_storage_v1_shape_codegen tests.test_storage_v1_shape_codec_assets tests.test_storage_v1_literal_schema_assets tests.test_contract_authority tests.test_contract_codegen
sha256sum ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift
test -z "$(git status --porcelain=v1)"
REMOTE
GREEN_STATUS=${PIPESTATUS[0]}
set -e
printf 'SSH_EXIT=%s\n' "$GREEN_STATUS" | tee -a "$GREEN_LOG"
test "$GREEN_STATUS" -eq 0
rg -n '^Ran [0-9]+ tests|^OK$' "$GREEN_LOG"
wc -l -c "$GREEN_LOG"
sha256sum "$GREEN_LOG"
```

The complete pressure-check-through-log-hash block above is the normative reusable `CODEGEN_GREEN_EXACT_SHA` protocol. Two generator passes must leave the exact tree clean; preserve SHA/ref, printed scratch, full log/status, actual focused counts, and the four before/after output hashes.

### 4. Prove RUNTIME-RED in Native

Commit Stage C and push its exact SHA to a unique evidence ref. Record dispatch time, then select only a new `workflow_dispatch` run matching branch, `headSha`, and `createdAt`.

```bash
set -euo pipefail
RED_SHA=$(git rev-parse HEAD)
RED_REF="refs/heads/evidence/plan1-task5b2as-runtime-red-$RED_SHA"
git push origin "$RED_SHA:$RED_REF"
test "$(git ls-remote --heads origin "$RED_REF" | awk 'NR == 1 {print $1}')" = "$RED_SHA"
RED_REF_NAME=${RED_REF#refs/heads/}
DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run native-mobile.yml --ref "$RED_REF_NAME"
RUN_ID=
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list --workflow native-mobile.yml --branch "$RED_REF_NAME" --event workflow_dispatch --limit 100 --json databaseId,headSha,createdAt --jq "map(select(.headSha == \"$RED_SHA\" and .createdAt >= \"$DISPATCHED_AT\")) | sort_by(.createdAt) | .[-1].databaseId // empty")
  test -n "$RUN_ID" && break
  sleep 2
done
test -n "$RUN_ID"
test "$(gh run view "$RUN_ID" --json headSha --jq .headSha)" = "$RED_SHA"
set +e
gh run watch "$RUN_ID" --exit-status
WATCH_STATUS=$?
set -e
test "$WATCH_STATUS" -ne 0
test "$(gh run view "$RUN_ID" --json conclusion --jq .conclusion)" = failure
RED_RUN_LOG="/tmp/task5b2as-runtime-red-$RED_SHA-run-$RUN_ID.log"
gh run view "$RUN_ID" --log > "$RED_RUN_LOG"
gh run view "$RUN_ID" --json databaseId,headSha,jobs,status,conclusion,url --jq '{databaseId,headSha,status,conclusion,url,jobs:[.jobs[]|{databaseId,name,conclusion}]}'
rg -F 'testMinimalStorageDocumentDecodes' "$RED_RUN_LOG"
rg -F 'notImplemented' "$RED_RUN_LOG"
if rg -n 'compil(e|ation) error|linker command failed|No tests found|workflow (invalid|failure)|infrastructure failure' "$RED_RUN_LOG"; then exit 1; fi
wc -l -c "$RED_RUN_LOG"
sha256sum "$RED_RUN_LOG"
```

The expected failure is the frozen `testMinimalStorageDocumentDecodes` behavioral assertion reaching `.notImplemented`. Record run/job IDs and exact head SHA; compilation, linking, discovery, workflow, or infrastructure failure is not RUNTIME-RED.

### 5. Prove RUNTIME-GREEN remotely and in Native

Commit Stage D and run `CODEGEN_GREEN_EXACT_SHA` before Native with exact substitutions `GREEN_SHA=<runtime-green HEAD>`, `GREEN_REF=refs/heads/evidence/plan1-task5b2as-runtime-green-$GREEN_SHA`, `GREEN_LOG=/tmp/task5b2as-runtime-green-$GREEN_SHA.log`, and scratch prefix `/home/jason/codex-runs/task5b2as-runtime-green-${GREEN_SHA}-XXXXXX`.
That same runtime ref must be pushed/verified, pressure-checked, freshly cloned/detached, card-ancestor and initially-clean checked, generator-drifted twice, four-output-hashed before/after the five focused modules, finally clean, and logged/hashed with zero status and actual counts. Only that success permits the exact same ref/SHA to continue below to time-bound Native dispatch.

```bash
set -euo pipefail
GREEN_SHA=$(git rev-parse HEAD)
GREEN_REF="refs/heads/evidence/plan1-task5b2as-runtime-green-$GREEN_SHA"
git push origin "$GREEN_SHA:$GREEN_REF"
test "$(git ls-remote --heads origin "$GREEN_REF" | awk 'NR == 1 {print $1}')" = "$GREEN_SHA"
# `CODEGEN_GREEN_EXACT_SHA` with the substitutions above has completed successfully here.
GREEN_REF_NAME=${GREEN_REF#refs/heads/}
DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run native-mobile.yml --ref "$GREEN_REF_NAME"
RUN_ID=
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list --workflow native-mobile.yml --branch "$GREEN_REF_NAME" --event workflow_dispatch --limit 100 --json databaseId,headSha,createdAt --jq "map(select(.headSha == \"$GREEN_SHA\" and .createdAt >= \"$DISPATCHED_AT\")) | sort_by(.createdAt) | .[-1].databaseId // empty")
  test -n "$RUN_ID" && break
  sleep 2
done
test -n "$RUN_ID"
test "$(gh run view "$RUN_ID" --json headSha --jq .headSha)" = "$GREEN_SHA"
gh run watch "$RUN_ID" --exit-status
test "$(gh run view "$RUN_ID" --json conclusion --jq .conclusion)" = success
GREEN_RUN_LOG="/tmp/task5b2as-runtime-green-$GREEN_SHA-run-$RUN_ID.log"
gh run view "$RUN_ID" --log > "$GREEN_RUN_LOG"
gh run view "$RUN_ID" --json databaseId,headSha,jobs,status,conclusion,url --jq '{databaseId,headSha,status,conclusion,url,jobs:[.jobs[]|{databaseId,name,conclusion}]}'
REPOSITORY=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
ARTIFACT_ID=$(gh api "repos/$REPOSITORY/actions/runs/$RUN_ID/artifacts" --jq '.artifacts[] | select(.name == "native-build-evidence" and .expired == false) | .id' | tail -n 1)
test -n "$ARTIFACT_ID"; printf 'ARTIFACT_ID=%s\n' "$ARTIFACT_ID"
ARTIFACT_ZIP="/tmp/task5b2as-runtime-green-$GREEN_SHA-native-build-evidence-$ARTIFACT_ID.zip"
gh api -H 'Accept: application/vnd.github+json' "repos/$REPOSITORY/actions/artifacts/$ARTIFACT_ID/zip" > "$ARTIFACT_ZIP"
test -s "$ARTIFACT_ZIP"
wc -c "$ARTIFACT_ZIP"; sha256sum "$ARTIFACT_ZIP"
ARTIFACT_DIR=$(mktemp -d "/tmp/task5b2as-runtime-green-$GREEN_SHA-artifacts-XXXXXX")
bsdtar -xf "$ARTIFACT_ZIP" -C "$ARTIFACT_DIR"
find "$ARTIFACT_DIR" -type f -print | sort
test -n "$(find "$ARTIFACT_DIR" -type f -print -quit)"
mapfile -d '' EVIDENCE_JSONS < <(find "$ARTIFACT_DIR" -type f -name native_build_evidence.json -print0)
test "${#EVIDENCE_JSONS[@]}" -eq 1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert d["schema"] == "ai-caddie-native-build-evidence-v1"; assert d["commit"] == sys.argv[2]; assert str(d["workflowRunId"]) == sys.argv[3]; assert d["artifactName"] == "native-build-evidence"; assert d["ios"]["scheme"] == "AICaddie" and d["ios"]["status"] == "passed"; assert d["watch"]["scheme"] == "AICaddieWatch" and d["watch"]["status"] == "passed"' "${EVIDENCE_JSONS[0]}" "$GREEN_SHA" "$RUN_ID"
find "$ARTIFACT_DIR" -type f -print0 | sort -z | xargs -0 -r sha256sum
wc -l -c "$GREEN_RUN_LOG"; sha256sum "$GREEN_RUN_LOG"
case "$ARTIFACT_DIR" in "/tmp/task5b2as-runtime-green-$GREEN_SHA-artifacts-"*) ;; *) exit 1 ;; esac
rm -f -- "$ARTIFACT_ZIP"
rm -rf -- "$ARTIFACT_DIR"
```

Capture run/job/artifact IDs, exact head SHA, full logs/hashes, validated evidence JSON, recursive regular-file hashes, counts, and green conclusion. Download no design/real-device/Watch screenshot or video artifact; retain `GREEN_RUN_LOG` through verification-record ingestion, and at closeout delete only exact packet-created `/tmp` logs after their hashes are recorded.

### 6. Review the implementation

After all exact-SHA checks are green, a fresh implementation reviewer performs SPEC review and a different fresh reviewer performs QUALITY review.

Every Critical or Important finding returns to the same writer for the smallest correction, affected focused homeserver checks, full exact-SHA Native workflow, and fresh review of the new SHA; the loop ends only with none unresolved.

### 7. Record verification and close only this packet

Write the verification record from captured evidence, then update the program index and packet map in their authorized closeout packet. Closeout marks only Task 5B2a-S `VERIFIED`.

Task 5B, Task 5, and Plan 1 remain incomplete.
The handoff returns Overall POP to the next frozen packet without implying broader completion.
