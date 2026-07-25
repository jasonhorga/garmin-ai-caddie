# Plan 1 Task 5B2a-S — Generated storage-v1 shape codec

**Date:** 2026-07-25
**Status:** Frozen execution card; Task 5B2a-S is not yet implemented

## Authority and bounded outcome

This card is subordinate to the [Program execution index](../plans/2026-07-23-program-execution-index.md), the [Task 5 packet map](2026-07-24-plan1-task5-packet-map.md), and the [storage-v1 schema design](../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md).

Those three documents remain the authority for program order, packet boundaries, and the storage-v1 schema decisions respectively.

This card freezes only packet Task 5B2a-S. It does not reopen any accepted architecture decision.
Owner decision: none.

Task 5B2a-R is verified and unchanged. No Task 5B2a-R source, test, fixture, or acceptance evidence is in this packet's write set.

Task 5B2a-S accepts only `ValidatedRawJSON`. The raw JSON gate therefore remains the sole syntactic and resource-safety entry boundary. The codec must not accept bytes, text, Foundation JSON objects, or an unvalidated `JSONValue` as an alternate input.

Task 5B2a-S owns the exact persisted storage-v1 shape, the exact path-scoped policies applied to that shape, the generated Swift shape descriptors, and the internal typed decode from `ValidatedRawJSON` into the declared storage records.

The typed result is internal implementation surface, and this packet does not publish a supported decoder.
Task 5B2b-T later owns the supported composed decoder that combines the R gate, the S shape codec, and the later semantic stages in the authorized order.

Task 5B2a-S excludes graph validation, ledger algorithms and state-transition logic, mutation and persistence writes, request construction and all network behavior, and any public decoder or public convenience entry point.

Shape validation must not infer semantic relationships between records or decide whether an event may be applied.
It must not repair, default, coerce, or normalize an accepted value.

Completion of this card does not complete Task 5B, Task 5, or Plan 1. Those enclosing scopes remain incomplete until their separately frozen packets and acceptance evidence are complete.

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

Add `GeneratedStorageV1Shape.swift` as the second surgical `serverSequence` exclusion, beside `LegacyV1Transport.swift`.
That exclusion covers a literal-only receipt diagnostic field; it does not authorize server-sequence ordering, comparison, or transport semantics in storage decoding.
The asset test mechanically proves that readable generated `serverSequence` occurs only as the `LegacyV1EventReceipt` diagnostic field.
The generator must emit that spelling directly and must never hide it with token splicing, escaped fragments, encoded text, or another obfuscation.

### Closed descriptor grammar

`domain_ledger_storage_shapes_v1.json` is the sole machine-readable descriptor graph for this packet. The graph is closed: every named reference resolves inside the declared type roster, every definition is reachable from a declared root, and no undeclared descriptor kind or member is accepted.

The grammar supports named record descriptors, an open-string descriptor, a closed-enum descriptor, and recursive `JSONValue`.
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

Every field declared by a record is required.
A missing field is a shape failure.
Every generated record is closed,
so an unknown field is also a shape failure.

Nullable is explicit-null semantics only.
A nullable field key must still be present,
and its value must be either JSON `null` or a value matching the wrapped descriptor.

`RoundEventKind` is an open string.
The codec preserves an unfamiliar string value rather than rejecting it as an unknown case.
`LegacyV1TerminalStatus` is a closed enum,
so a value outside its declared cases is rejected.

`JSONValue` is recursive and retains the existing JSON value model.
Receipt maps and payload maps are dynamic maps with arbitrary string keys and descriptor-constrained values.
Dynamic-map keys are data,
not undeclared record fields.

`CanonicalStringSet` is a typed collection.
Its values must already be sorted in canonical order and unique.
The sole final typed decode rejects an unsorted or duplicate representation;
it does not sort or deduplicate it.

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

Do not constrain `LegacyV1EventBatchBody.events`.
Do not globally constrain `JSONValue`.
A matching field name at any other path does not inherit one of these policies.

Contextual policies are embedded constrained nodes in the descriptor graph.
Runtime code contains no wildcard matcher and no path-string matcher.
The generator and its tests flatten the descriptor graph and assert equality with this exact policy roster before Swift emission.

### Exact limits

Each `rootCollection` has a maximum count of `65,536`.
`preparedSlots` has an inclusive count range of `1...64`.
An ordinary string has a maximum length of `4,096` Unicode scalars.
A Base64 text value has a maximum length of `1,398,104` Unicode scalars.
A decoded request body has a maximum size of `1,048,576` bytes.
An `eventOrEnvelope` canonical encoding has a maximum size of `65,536` bytes.
An `eventOrEnvelope` has a maximum relative depth of `16`.

Generated Swift must reference `RoundTransportLimits` symbolically for every matching transport limit.
Only the `65,536` root-collection count remains a storage-schema literal because no matching transport symbol owns it.
The descriptor and generated output must not create shadow constants for existing transport limits.

Counts are checked before per-element descent where the representation makes that possible.
Unicode string limits count scalars,
not UTF-8 bytes or UTF-16 code units.
Canonical byte and relative-depth checks apply only at the two `eventOrEnvelope` paths.

### Generator rejection contract

The generator rejects duplicate definitions.
It rejects unknown definitions,
unknown members,
unknown references,
unknown policies,
and unknown profiles.
It rejects malformed definitions,
references,
policies,
and profiles.

The generator rejects incompatible constraints on a single descriptor path.
It rejects policy paths that cannot be reached from the applicable declared root.
It rejects a policy application that resolves to the wrong descriptor shape.
It rejects unused or unreachable policy nodes.

Generation is deterministic.
Stable descriptor traversal and stable emitted ordering are mandatory,
and the generator rejects inputs whose representation would make output ordering nondeterministic.
The same accepted source bytes and generator version must produce byte-identical Swift output.

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

Hostile key and value text is checked for NFC before Swift `String` equality, dictionary insertion, or typed materialization. No hostile text may gain host-language normalization behavior before this check.

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

Every raw number lexeme is resource-guarded before numeric conversion. Canonical numeric bytes are obtained only through existing `CanonicalJSON` / SwiftJCS behavior; the codec contains no handwritten number formatter.

The canonical spelling is compared exactly with the accepted raw lexeme. Consequently `1` is accepted where its numeric shape is valid, while `1.0`, `1e0`, and `-0` are rejected as noncanonical spellings.

An integer field must first convert exactly to `Int64` and then exactly to platform `Int`.
Fractional, out-of-range, rounded, or saturated integer values are rejected.

Task 5B2a-S enforces only shape and the frozen contextual resource policies. It adds no graph, hash, identity, or domain-range semantics.

## TDD and mutation test matrix

### Stage A — CODEGEN-RED

The first implementation commit is tests only. It proves the generated file is absent and that repeated generation must be byte-identical.
The schema test asserts the exact top-key set rather than presence-only checks.

It asserts the two exact declared roots, the exact 17-type roster, every record field, every scalar/ref/array/dynamic-map/nullable/constrained wrapper, and every open/closed distinction.
It flattens embedded constrained nodes and compares the complete policy roster exactly.

The malformed-generator corpus covers duplicate, unknown, malformed, and dangling definitions, references, policies, and profiles.
It also covers incompatible constraints, unreachable policy nodes, wrong-shaped policy targets, and nondeterministic input structures.

Authority tests require a separate storage-v1 generated group outside `canonicalRoots`, and pin the one-time digest changes for all three canonical outputs caused by `authority.json`. A mutation of only a storage-v1 schema source must leave every public canonical digest stable.

The literal audit allows the second surgical `serverSequence` exception only in readable generated receipt-field context. It fails obfuscation, another generated occurrence, or a use outside the diagnostic field.

The focused CODEGEN-RED run must fail for the expected missing schema/generator/generated-asset behavior.

### Stage B — CODEGEN-GREEN

The same sole writer creates the storage schema, generator, generated Swift output, and manifest/asset-test changes frozen in the write set. The writer performs the one-time regeneration of the three canonical outputs.

Generation twice must be byte-identical. All focused codegen and asset modules must become green before runtime test work starts. No runtime codec behavior is implemented in this stage.

### Stage C — RUNTIME-RED

Add the final asset assertions and XCTest API/behavior suite. Add only the compile-safe runtime seam required to discover those tests, with the codec throwing its internal `.notImplemented` error.

Dispatch Native at the exact RUNTIME-RED commit SHA through a unique evidence branch.
Native must compile and discover the suite, then fail for the expected codec behavioral assertion rather than compilation, linkage, workflow, or test-discovery failure.

### Stage D — RUNTIME-GREEN

Implement the production streaming validator and sole final typed decode. Make focused Python and XCTest coverage green without weakening any RED assertion. Refactor only while all focused checks remain green.

### Positive and negative vectors

The runtime matrix includes both a minimal root and a representative root containing every record family.
It accepts an unfamiliar `RoundEventKind` string and every closed terminal status value.

For every record family it isolates missing, extra, wrong-type, and forbidden-null mutations.
Required-nullable fields separately prove present-null success and missing-key failure.

Dynamic receipt and payload maps accept hostile data keys after NFC validation. Key and value vectors prove NFC success and non-NFC rejection before equality or materialization.

An ordinary string of `4,096` scalars passes and `4,097` fails. Each named root collection passes at `65,536` elements and fails at `65,537`. An unrelated nested array is not given the root-collection limit.

Prepared slots fail at `0`, pass at `1` and `64`, and fail at `65`.

Base64 vectors cover canonical text, noncanonical text, whitespace, missing padding, empty text, the text preallocation boundary, and the decoded-body byte boundary.

Number vectors cover `1`, `1.0`, `1e0`, `-0`, a hostile huge lexeme, both `Int64` bounds, and values just outside both bounds.
Platform-`Int` conversion receives its own exact-range assertion where it is narrower.

Canonical event/envelope bytes pass at `65,536` and fail at `65,537`. Relative depth passes at `16` and fails at `17`. The same shapes prove those constraints apply only to `events[*]` and `preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`.

`LegacyV1EventBatchBody.events` and unrelated `JSONValue` nodes remain unconstrained by `eventOrEnvelope`. Sorted unique `CanonicalStringSet` values pass at the final typed decode; unsorted and duplicate values fail only there.

Source audits enforce one cursor replay, one final root decoder, no AST or retained token array, no `JSONSerialization`, no runtime wildcard/path matcher, and no bypass overload.

Every negative vector changes exactly one relevant property and isolates one expected rejection reason.

## Serial evidence, remote commands, review, and freeze

All commands in this section are planned execution commands, not claims that they have already run.
The local machine is limited to Git,
text inspection,
and SSH transport.
All tests,
builds,
generation,
and dependency work run in a unique homeserver scratch or CI.

### 1. Freeze and review the card

Create a one-file card-candidate commit.
A fresh reviewer performs card SPEC review,
then a different fresh reviewer performs card QUALITY review.
The same sole writer applies corrections and sends each changed candidate back through the applicable fresh review.

After both reviews accept,
capture the final card SHA-256 and commit SHA.
No later stage may change a byte of this card.

Run these local text/Git checks from the repository root:

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

The lexical audit also rejects unfinished-marker vocabulary and the obsolete uppercase packet spelling without weakening the required `.notImplemented` RED seam.

### 2. Prove CODEGEN-RED remotely

Commit only the Stage A test changes.
Sync that exact tree to a unique homeserver scratch without environment files,
secret material,
or `--delete`.

```bash
SHA=$(git rev-parse HEAD)
SCRATCH="garmin-ai-caddie-5b2as-codegen-red-${SHA}"
ssh "$HOMESERVER" "git clone --no-hardlinks '$HOMESERVER_REPO' '/tmp/$SCRATCH'"
rsync -a -e ssh --exclude='.git/' --exclude='.env' --exclude='.env.*' --exclude='*secret*' ./ "$HOMESERVER:/tmp/$SCRATCH/"
ssh "$HOMESERVER" "cd '/tmp/$SCRATCH' && python3 -m unittest -v tests.test_storage_v1_shape_codegen tests.test_storage_v1_shape_codec_assets tests.test_storage_v1_literal_schema_assets"
```

Record the nonzero exit,
the failing assertion,
and proof that the cause is the intentionally absent storage-v1 schema/generator/generated output.

### 3. Prove CODEGEN-GREEN remotely

Commit Stage B and sync a new unique scratch with the same exclusions and no deletion flag.
Run generation in this exact order,
then prove a second generation has no drift and run the focused modules:

```bash
python3 tools/contracts/generate_contracts.py
python3 tools/contracts/generate_storage_v1_shape.py
git diff --exit-code -- ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift
python3 tools/contracts/generate_storage_v1_shape.py
git diff --exit-code -- contracts/storage-v1 mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift
python3 -m unittest -v tests.test_storage_v1_shape_codegen tests.test_storage_v1_shape_codec_assets tests.test_storage_v1_literal_schema_assets
```

Capture the commit SHA,
scratch name,
command transcript,
focused test counts,
and output hashes.

### 4. Prove RUNTIME-RED in Native

Commit Stage C.
Create and push a unique evidence branch pointing at that exact SHA,
dispatch `native-mobile.yml` by branch,
and verify the run's `headSha` equals the intended commit.

```bash
SHA=$(git rev-parse HEAD)
BRANCH="evidence/5b2as-runtime-red-${SHA}"
git branch "$BRANCH" "$SHA"
git push origin "$BRANCH:$BRANCH"
gh workflow run native-mobile.yml --ref "$BRANCH"
gh run list --workflow native-mobile.yml --branch "$BRANCH" --json databaseId,headSha,status,conclusion,url
gh run view "$RUN_ID" --json databaseId,headSha,jobs,status,conclusion,url
gh run view "$RUN_ID" --log-failed
```

Record the run ID,
job ID,
head SHA,
and the expected behavioral assertion.
Reject evidence from the wrong SHA or from compile,
link,
discovery,
workflow,
or infrastructure failure.

### 5. Prove RUNTIME-GREEN remotely and in Native

Commit Stage D and create a new homeserver scratch.
Run the focused Python modules green there before CI dispatch.
Then create a new exact-SHA evidence branch and dispatch the full Native workflow.

```bash
python3 -m unittest -v tests.test_storage_v1_shape_codegen tests.test_storage_v1_shape_codec_assets tests.test_storage_v1_literal_schema_assets
SHA=$(git rev-parse HEAD)
BRANCH="evidence/5b2as-runtime-green-${SHA}"
git branch "$BRANCH" "$SHA"
git push origin "$BRANCH:$BRANCH"
gh workflow run native-mobile.yml --ref "$BRANCH"
gh run view "$RUN_ID" --json databaseId,headSha,jobs,status,conclusion,url
gh run watch "$RUN_ID" --exit-status
gh run view "$RUN_ID" --log
gh run download "$RUN_ID" --dir "/tmp/5b2as-native-$RUN_ID"
sha256sum /tmp/5b2as-native-$RUN_ID/*
```

Capture run,
job,
and artifact IDs;
head SHA;
logs;
artifact hashes;
suite and test counts;
and the green conclusion.

### 6. Review the implementation

After all exact-SHA checks are green,
a fresh implementation reviewer performs SPEC review.
A different fresh reviewer then performs QUALITY review.

Every Critical or Important finding returns to the same writer for the smallest bounded correction.
The writer reruns the affected focused homeserver checks and full exact-SHA Native workflow,
then obtains fresh review of the new SHA.
The loop ends only with no unresolved Critical or Important finding.

### 7. Record verification and close only this packet

Write the verification record from captured evidence,
then update the program index and packet map in their authorized closeout packet.
Closeout marks only Task 5B2a-S `VERIFIED`.

Task 5B,
Task 5,
and Plan 1 remain incomplete.
The handoff returns Overall POP to the next frozen packet without implying broader completion.
