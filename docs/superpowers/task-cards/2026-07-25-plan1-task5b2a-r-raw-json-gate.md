# Plan 1 Task 5B2a-R Raw JSON Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this card. The sole
> implementation writer uses `superpowers:test-driven-development`; fresh
> read-only reviewers run SPEC before QUALITY. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Validate one raw UTF-8 JSON value into a non-public, non-forgeable,
replayable capability while enforcing only the storage-v1 raw byte, depth,
duplicate-key and Unicode-scalar bounds.

**Architecture:** After the byte gate, validation makes one owned immutable
`Data` snapshot. An iterative scanner owns a stack bounded to 64 containers
and a decoded-key `Set<Data>` per live object. A capability-created cursor
replays source-bound structural events, raw ranges, decoded key/value string
bytes and exact scalar counts; there is no AST, number conversion or
Foundation JSON parser.

**Tech Stack:** Swift 5.9, Foundation `Data`, XCTest, Python 3.12 mechanical
audits, GitHub Actions `macos-15`.

---

## Authority, baseline and exact boundary

- Scope/order authority:
  `../plans/2026-07-23-program-execution-index.md`.
- Approved design authority:
  `../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md`, frozen
  SHA-256
  `f31a090fe9c4dc37828f25ee3528afd067d7222128606514b2cfe74229dc2b05`.
- Packet router: `2026-07-24-plan1-task5-packet-map.md`.
- Verified dependency: 5B1 production candidate
  `486d2e354c43c1a4754b18c8dbdf76eeca7f4657`; verification audit head
  `ad6ce690e6afb2865f8ab2ce867ed9d6bf3075de`.
- Implementation baseline is the commit that first adds this card. Before RED,
  record it exactly:

  ```bash
  CARD_SHA=$(git log --diff-filter=A -1 --format=%H -- \
    docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-r-raw-json-gate.md)
  test -n "$CARD_SHA"
  test "$(git diff-tree --no-commit-id --name-only -r "$CARD_SHA")" = \
    docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-r-raw-json-gate.md
  ```

The implementation range creates exactly three files:

- `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift`
- `mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift`
- `tests/test_storage_v1_raw_json_gate_assets.py`

`Package.swift` and `mobile/ios/project.yml` already include the source and
test directories. No registry, schema, authority-manifest, generated output,
app/Watch callsite, fixture or workflow changes belong to 5B2a-R.

Execution is serial under one implementation writer and follows
`CARD -> RED-1 -> RED-2 -> GREEN -> REMOTE -> SPEC -> QUALITY -> VERIFIED`.

## Frozen behavior

The gate accepts raw `Data` only when it contains exactly one RFC 8259 JSON
value, optionally surrounded by the four JSON whitespace bytes. Top-level
objects, arrays and scalars are all legal at R. Every bound is inclusive:

| Raw property | Accepted bound |
|---|---:|
| source document bytes | `<= 67_108_864` |
| recursive JSON depth | `<= 64` |
| decoded object-key length | `<= 128` Unicode scalars |
| decoded length of any string value | `<= 1_398_104` Unicode scalars |

Depth is the approved recursive definition: a scalar is depth `0`; an empty
container is depth `1`; and a non-empty container is `1 + max(child depth)`.
An iterative stack therefore rejects the 65th simultaneously open container.

Strings are decoded only far enough to validate UTF-8/escapes, count Unicode
scalars and emit the current event's decoded UTF-8 bytes. A surrogate pair is
one scalar; unpaired surrogate escapes are rejected. Key bytes are additionally
used for duplicate comparison in the current object's `Set<Data>`:

- `"a"` and `"\u0061"` are duplicates;
- literal `"😀"` and `"\uD83D\uDE00"` are duplicates;
- `"é"` and `"e\u0301"` remain distinct because R does not normalize NFC;
- the same key in different objects is not a duplicate.

Numbers are checked only against JSON number grammar. They are never converted
to `Int64`, `Double`, `Decimal` or `NSNumber`; each replay event points to the
exact raw number lexeme in the retained `Data`. Each key/string replay event
carries its exact decoded Unicode-scalar count. Replaying does not materialize
or retain a token tree: each cursor deterministically revalidates the immutable
source and emits occurrence-ordered evidence bound to that token's source
range and container topology. The capability never stores an aggregate-only
maximum or a heap object per token.

`Cursor` is a capability-created reference type: copying a cursor reference
does not fork parser state while sharing object-key sets, and each
`makeCursor()` call creates a completely independent replay.

The byte limit is checked before allocation. Validation then copies the input
bytes once into owned storage so `Data(referencing: NSMutableData)`, mapped or
no-copy backing cannot mutate a successful capability afterward. Capability,
event and cursor construction remain internal/file-private and each event is
bound to one source identity; a range from one capability cannot be applied to
another. The same gate is reusable later for the already size-bounded decoded
`exactRequestBody` bytes.

The new file owns only the storage-document byte limit and the absolute string
cap. It aliases `RoundTransportLimits.maxRawJsonDepth` and
`RoundTransportLimits.maxJsonKeyCharacters`; it must not duplicate the existing
generated `64`/`128` authority or use the unrelated generated ordinary-string
limit of 4,096.

The 64 MiB contract bounds source bytes, not process RSS. Exact duplicate
detection for a very wide legal object necessarily retains its decoded keys;
R must not invent a member/token limit to reduce that cost. The implementation
therefore uses one reference-stable key set per live object, releases it on
object close, does not pre-reserve it from document size, and retains no token
array. A replay event may transiently own the decoded bytes of its one current
string; the capability does not retain those per-token buffers.

## Explicit deferrals and required acceptance cases

5B2a-R must accept these because their policies belong to 5B2a-S or later:

- valid non-NFC keys and values;
- an ordinary string of 4,097 scalars;
- syntactically valid integers/exponents far beyond native numeric ranges,
  including `-0` and `-0.0`;
- text that merely looks like invalid or non-canonical Base64;
- arrays/objects with more than 65,536 members when the raw byte/depth/key/
  string limits still pass; and
- any valid top-level JSON kind.

This packet explicitly excludes:

- root shape, key roster, field type/nullability and collection-count rules;
- the ordinary-string 4,096 policy, NFC and canonical-number policy;
- Base64 syntax/canonical padding/decoded-byte validation;
- event/envelope byte/depth bounds and prepared-slot bounds;
- typed `DomainLedgerStateV1` decode or a supported/public storage decoder;
- ledger/transport graph validation, hashes, identity and algorithms; and
- persistence, mutation, lifecycle, migration and network behavior.

5B2a-S must consume the decoded key/value bytes from this source-bound replay,
apply its NFC and exact-shape rules before invoking `JSONDecoder`, and never
let Swift canonical-equivalent `String`/dictionary behavior collapse R's
intentionally distinct `"é"` and `"e\u0301"` keys before rejection.

5B2b-T has the same predecode obligation for every decoded
`exactRequestBody`: it must consume R's decoded-key evidence and reject NFC or
consumer-equivalent key collisions before materializing a
`LegacyV1EventBatchBody`, `[JSONValue]` or any other Swift dictionary-backed
representation of that inner JSON.

## Final production contract

`StorageV1RawJSONGate.swift` must contain the following bounded scanner. The
RED-2 seam uses the same API, so GREEN changes behavior without changing the
test contract.

```swift
import Foundation

enum StorageV1RawJSONGate {
    static let maximumDocumentBytes = 67_108_864
    static let maximumDepth = RoundTransportLimits.maxRawJsonDepth
    static let maximumKeyScalars = RoundTransportLimits.maxJsonKeyCharacters
    static let maximumStringScalars = 1_398_104

    fileprivate final class SourceIdentity {
        fileprivate init() {}
    }

    enum ValidationError: Error, Equatable {
        case documentTooLarge(actual: Int, maximum: Int)
        case malformedJSON(byteOffset: Int)
        case invalidUTF8(byteOffset: Int)
        case nestingTooDeep(byteOffset: Int, maximum: Int)
        case keyTooLong(byteOffset: Int, maximumScalars: Int)
        case stringTooLong(byteOffset: Int, maximumScalars: Int)
        case duplicateObjectKey(byteOffset: Int)
    }

    struct Event: Equatable {
        enum Kind: Equatable {
            case objectStart
            case objectEnd
            case arrayStart
            case arrayEnd
            case objectKey
            case string
            case number
            case trueLiteral
            case falseLiteral
            case nullLiteral
        }

        let kind: Kind
        fileprivate let byteRange: Range<Data.Index>
        let stringScalarCount: Int?
        let decodedStringUTF8: Data?
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            kind: Kind,
            byteRange: Range<Data.Index>,
            stringScalarCount: Int?,
            decodedStringUTF8: Data?,
            sourceIdentity: SourceIdentity
        ) {
            self.kind = kind
            self.byteRange = byteRange
            self.stringScalarCount = stringScalarCount
            self.decodedStringUTF8 = decodedStringUTF8
            self.sourceIdentity = sourceIdentity
        }

        static func == (lhs: Event, rhs: Event) -> Bool {
            lhs.sourceIdentity === rhs.sourceIdentity
                && lhs.kind == rhs.kind
                && lhs.byteRange == rhs.byteRange
                && lhs.stringScalarCount == rhs.stringScalarCount
                && lhs.decodedStringUTF8 == rhs.decodedStringUTF8
        }
    }

    struct ValidatedRawJSON {
        private let data: Data
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
        }

        func makeCursor() -> Cursor {
            Cursor(data: data, sourceIdentity: sourceIdentity)
        }

        func exactBytes() -> Data {
            data
        }

        func rawBytes(for event: Event) -> Data.SubSequence? {
            guard event.sourceIdentity === sourceIdentity,
                  event.byteRange.lowerBound >= data.startIndex,
                  event.byteRange.upperBound <= data.endIndex else {
                return nil
            }
            return data[event.byteRange]
        }
    }

    final class Cursor {
        private static let trueBytes: [UInt8] = [
            0x74, 0x72, 0x75, 0x65,
        ]
        private static let falseBytes: [UInt8] = [
            0x66, 0x61, 0x6C, 0x73, 0x65,
        ]
        private static let nullBytes: [UInt8] = [
            0x6E, 0x75, 0x6C, 0x6C,
        ]

        private enum DocumentState {
            case expectingRoot
            case afterRoot
        }

        private enum FrameState {
            case arrayFirstValueOrEnd
            case arrayValueAfterComma
            case arrayCommaOrEnd
            case objectFirstKeyOrEnd
            case objectKeyAfterComma
            case objectColon
            case objectValue
            case objectCommaOrEnd
        }

        private final class ObjectKeySet {
            var values: Set<Data> = []
        }

        private struct Frame {
            var state: FrameState
            let objectKeys: ObjectKeySet?
        }

        private struct ParsedString {
            let byteRange: Range<Data.Index>
            let scalarCount: Int
            let decodedUTF8: Data
        }

        private let data: Data
        private let sourceIdentity: SourceIdentity
        private var index: Data.Index
        private var documentState: DocumentState = .expectingRoot
        private var frames: [Frame] = []

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
            self.index = data.startIndex
            self.frames.reserveCapacity(
                StorageV1RawJSONGate.maximumDepth
            )
        }

        func next() throws -> Event? {
            while true {
                consumeWhitespace()

                if index == data.endIndex {
                    if frames.isEmpty, documentState == .afterRoot {
                        return nil
                    }
                    throw malformed(at: index)
                }

                guard !frames.isEmpty else {
                    guard documentState == .expectingRoot else {
                        throw malformed(at: index)
                    }
                    return try consumeValue()
                }

                let frameIndex = frames.count - 1
                switch frames[frameIndex].state {
                case .arrayFirstValueOrEnd:
                    if data[index] == 0x5D {
                        return try closeContainer(kind: .arrayEnd)
                    }
                    return try consumeValue()

                case .arrayValueAfterComma:
                    return try consumeValue()

                case .arrayCommaOrEnd:
                    switch data[index] {
                    case 0x2C:
                        index += 1
                        frames[frameIndex].state = .arrayValueAfterComma
                    case 0x5D:
                        return try closeContainer(kind: .arrayEnd)
                    default:
                        throw malformed(at: index)
                    }

                case .objectFirstKeyOrEnd:
                    if data[index] == 0x7D {
                        return try closeContainer(kind: .objectEnd)
                    }
                    return try consumeObjectKey(at: frameIndex)

                case .objectKeyAfterComma:
                    return try consumeObjectKey(at: frameIndex)

                case .objectColon:
                    guard data[index] == 0x3A else {
                        throw malformed(at: index)
                    }
                    index += 1
                    frames[frameIndex].state = .objectValue

                case .objectValue:
                    return try consumeValue()

                case .objectCommaOrEnd:
                    switch data[index] {
                    case 0x2C:
                        index += 1
                        frames[frameIndex].state = .objectKeyAfterComma
                    case 0x7D:
                        return try closeContainer(kind: .objectEnd)
                    default:
                        throw malformed(at: index)
                    }
                }
            }
        }

        private func consumeValue() throws -> Event {
            let start = index
            switch data[index] {
            case 0x7B:
                return try openContainer(
                    kind: .objectStart,
                    initialState: .objectFirstKeyOrEnd,
                    tracksObjectKeys: true
                )
            case 0x5B:
                return try openContainer(
                    kind: .arrayStart,
                    initialState: .arrayFirstValueOrEnd,
                    tracksObjectKeys: false
                )
            case 0x22:
                let parsed = try consumeString(isObjectKey: false)
                try finishValue()
                return Event(
                    kind: .string,
                    byteRange: parsed.byteRange,
                    stringScalarCount: parsed.scalarCount,
                    decodedStringUTF8: parsed.decodedUTF8,
                    sourceIdentity: sourceIdentity
                )
            case 0x74:
                let range = try consumeLiteral(Self.trueBytes)
                try finishValue()
                return scalarEvent(kind: .trueLiteral, range: range)
            case 0x66:
                let range = try consumeLiteral(Self.falseBytes)
                try finishValue()
                return scalarEvent(kind: .falseLiteral, range: range)
            case 0x6E:
                let range = try consumeLiteral(Self.nullBytes)
                try finishValue()
                return scalarEvent(kind: .nullLiteral, range: range)
            case 0x2D, 0x30...0x39:
                let range = try consumeNumber()
                try finishValue()
                return scalarEvent(kind: .number, range: range)
            default:
                if data[index] >= 0x80 {
                    _ = try consumeUnescapedScalar()
                    index = start
                }
                throw malformed(at: start)
            }
        }

        private func openContainer(
            kind: Event.Kind,
            initialState: FrameState,
            tracksObjectKeys: Bool
        ) throws -> Event {
            let start = index
            let nextDepth = frames.count + 1
            guard nextDepth <= StorageV1RawJSONGate.maximumDepth else {
                throw ValidationError.nestingTooDeep(
                    byteOffset: offset(of: start),
                    maximum: StorageV1RawJSONGate.maximumDepth
                )
            }
            index += 1
            frames.append(Frame(
                state: initialState,
                objectKeys: tracksObjectKeys ? ObjectKeySet() : nil
            ))
            return Event(
                kind: kind,
                byteRange: start..<index,
                stringScalarCount: nil,
                decodedStringUTF8: nil,
                sourceIdentity: sourceIdentity
            )
        }

        private func closeContainer(
            kind: Event.Kind
        ) throws -> Event {
            let start = index
            index += 1
            frames.removeLast()
            try finishValue()
            return Event(
                kind: kind,
                byteRange: start..<index,
                stringScalarCount: nil,
                decodedStringUTF8: nil,
                sourceIdentity: sourceIdentity
            )
        }

        private func consumeObjectKey(
            at frameIndex: Int
        ) throws -> Event {
            guard data[index] == 0x22 else {
                throw malformed(at: index)
            }
            let parsed = try consumeString(isObjectKey: true)
            let decodedKey = parsed.decodedUTF8
            guard let objectKeys = frames[frameIndex].objectKeys,
                  objectKeys.values.insert(decodedKey).inserted else {
                throw ValidationError.duplicateObjectKey(
                    byteOffset: offset(of: parsed.byteRange.lowerBound)
                )
            }
            frames[frameIndex].state = .objectColon
            return Event(
                kind: .objectKey,
                byteRange: parsed.byteRange,
                stringScalarCount: parsed.scalarCount,
                decodedStringUTF8: decodedKey,
                sourceIdentity: sourceIdentity
            )
        }

        private func finishValue() throws {
            guard !frames.isEmpty else {
                guard documentState == .expectingRoot else {
                    throw malformed(at: index)
                }
                documentState = .afterRoot
                return
            }

            let frameIndex = frames.count - 1
            switch frames[frameIndex].state {
            case .arrayFirstValueOrEnd, .arrayValueAfterComma:
                frames[frameIndex].state = .arrayCommaOrEnd
            case .objectValue:
                frames[frameIndex].state = .objectCommaOrEnd
            default:
                throw malformed(at: index)
            }
        }

        private func consumeString(
            isObjectKey: Bool
        ) throws -> ParsedString {
            let start = index
            index += 1
            var scalarCount = 0
            var decodedString = Data()
            var unescapedRunStart = index

            while index < data.endIndex {
                if data[index] == 0x22 {
                    if unescapedRunStart < index {
                        decodedString.append(
                            contentsOf: data[unescapedRunStart..<index]
                        )
                    }
                    index += 1
                    return ParsedString(
                        byteRange: start..<index,
                        scalarCount: scalarCount,
                        decodedUTF8: decodedString
                    )
                }

                if data[index] == 0x5C {
                    if unescapedRunStart < index {
                        decodedString.append(
                            contentsOf: data[unescapedRunStart..<index]
                        )
                    }
                    let scalar = try consumeEscapedScalar()
                    appendUTF8(scalar, to: &decodedString)
                    unescapedRunStart = index
                } else {
                    guard data[index] >= 0x20 else {
                        throw malformed(at: index)
                    }
                    _ = try consumeUnescapedScalar()
                }

                scalarCount += 1
                if isObjectKey,
                   scalarCount > StorageV1RawJSONGate.maximumKeyScalars {
                    throw ValidationError.keyTooLong(
                        byteOffset: offset(of: start),
                        maximumScalars:
                            StorageV1RawJSONGate.maximumKeyScalars
                    )
                }
                if !isObjectKey,
                   scalarCount > StorageV1RawJSONGate.maximumStringScalars {
                    throw ValidationError.stringTooLong(
                        byteOffset: offset(of: start),
                        maximumScalars:
                            StorageV1RawJSONGate.maximumStringScalars
                    )
                }
            }

            throw malformed(at: index)
        }

        private func consumeEscapedScalar() throws -> UInt32 {
            let escapeStart = index
            index += 1
            guard index < data.endIndex else {
                throw malformed(at: escapeStart)
            }
            let escape = data[index]
            index += 1
            switch escape {
            case 0x22: return 0x22
            case 0x5C: return 0x5C
            case 0x2F: return 0x2F
            case 0x62: return 0x08
            case 0x66: return 0x0C
            case 0x6E: return 0x0A
            case 0x72: return 0x0D
            case 0x74: return 0x09
            case 0x75:
                let first = try consumeHexQuad()
                if (0xD800...0xDBFF).contains(first) {
                    guard index < data.endIndex,
                          data[index] == 0x5C else {
                        throw malformed(at: index)
                    }
                    index += 1
                    guard index < data.endIndex,
                          data[index] == 0x75 else {
                        throw malformed(at: index)
                    }
                    index += 1
                    let second = try consumeHexQuad()
                    guard (0xDC00...0xDFFF).contains(second) else {
                        throw malformed(at: index)
                    }
                    return 0x10000
                        + ((first - 0xD800) << 10)
                        + (second - 0xDC00)
                }
                guard !(0xDC00...0xDFFF).contains(first) else {
                    throw malformed(at: index)
                }
                return first
            default:
                throw malformed(at: data.index(before: index))
            }
        }

        private func consumeHexQuad() throws -> UInt32 {
            var value: UInt32 = 0
            for _ in 0..<4 {
                guard index < data.endIndex,
                      let digit = hexValue(data[index]) else {
                    throw malformed(at: index)
                }
                value = (value << 4) | digit
                index += 1
            }
            return value
        }

        private func consumeUnescapedScalar() throws -> UInt32 {
            let start = index
            let first = data[index]
            if first < 0x80 {
                index += 1
                return UInt32(first)
            }

            let length: Int
            let minimum: UInt32
            var scalar: UInt32
            switch first {
            case 0xC2...0xDF:
                length = 2
                minimum = 0x80
                scalar = UInt32(first & 0x1F)
            case 0xE0...0xEF:
                length = 3
                minimum = 0x800
                scalar = UInt32(first & 0x0F)
            case 0xF0...0xF4:
                length = 4
                minimum = 0x10000
                scalar = UInt32(first & 0x07)
            default:
                throw ValidationError.invalidUTF8(
                    byteOffset: offset(of: start)
                )
            }

            index += 1
            for _ in 1..<length {
                guard index < data.endIndex else {
                    throw ValidationError.invalidUTF8(
                        byteOffset: offset(of: start)
                    )
                }
                let continuation = data[index]
                guard continuation >= 0x80, continuation <= 0xBF else {
                    throw ValidationError.invalidUTF8(
                        byteOffset: offset(of: start)
                    )
                }
                scalar = (scalar << 6) | UInt32(continuation & 0x3F)
                index += 1
            }

            guard scalar >= minimum,
                  scalar <= 0x10FFFF,
                  !(0xD800...0xDFFF).contains(scalar) else {
                throw ValidationError.invalidUTF8(
                    byteOffset: offset(of: start)
                )
            }
            return scalar
        }

        private func consumeNumber() throws -> Range<Data.Index> {
            let start = index
            if data[index] == 0x2D {
                index += 1
                guard index < data.endIndex else {
                    throw malformed(at: index)
                }
            }

            if data[index] == 0x30 {
                index += 1
            } else {
                guard data[index] >= 0x31, data[index] <= 0x39 else {
                    throw malformed(at: index)
                }
                consumeDigits()
            }

            if index < data.endIndex, data[index] == 0x2E {
                index += 1
                guard index < data.endIndex, isDigit(data[index]) else {
                    throw malformed(at: index)
                }
                consumeDigits()
            }

            if index < data.endIndex,
               data[index] == 0x65 || data[index] == 0x45 {
                index += 1
                if index < data.endIndex,
                   data[index] == 0x2B || data[index] == 0x2D {
                    index += 1
                }
                guard index < data.endIndex, isDigit(data[index]) else {
                    throw malformed(at: index)
                }
                consumeDigits()
            }

            return start..<index
        }

        private func consumeDigits() {
            while index < data.endIndex, isDigit(data[index]) {
                index += 1
            }
        }

        private func consumeLiteral(
            _ literal: [UInt8]
        ) throws -> Range<Data.Index> {
            let start = index
            for expected in literal {
                guard index < data.endIndex,
                      data[index] == expected else {
                    throw malformed(at: index)
                }
                index += 1
            }
            return start..<index
        }

        private func consumeWhitespace() {
            while index < data.endIndex {
                switch data[index] {
                case 0x09, 0x0A, 0x0D, 0x20:
                    index += 1
                default:
                    return
                }
            }
        }

        private func scalarEvent(
            kind: Event.Kind,
            range: Range<Data.Index>
        ) -> Event {
            Event(
                kind: kind,
                byteRange: range,
                stringScalarCount: nil,
                decodedStringUTF8: nil,
                sourceIdentity: sourceIdentity
            )
        }

        private func malformed(
            at index: Data.Index
        ) -> ValidationError {
            .malformedJSON(byteOffset: offset(of: index))
        }

        private func offset(of index: Data.Index) -> Int {
            data.distance(from: data.startIndex, to: index)
        }

        private func isDigit(_ byte: UInt8) -> Bool {
            byte >= 0x30 && byte <= 0x39
        }

        private func hexValue(_ byte: UInt8) -> UInt32? {
            switch byte {
            case 0x30...0x39: return UInt32(byte - 0x30)
            case 0x41...0x46: return UInt32(byte - 0x41 + 10)
            case 0x61...0x66: return UInt32(byte - 0x61 + 10)
            default: return nil
            }
        }

        private func appendUTF8(_ scalar: UInt32, to data: inout Data) {
            switch scalar {
            case 0...0x7F:
                data.append(UInt8(scalar))
            case 0x80...0x7FF:
                data.append(UInt8(0xC0 | (scalar >> 6)))
                data.append(UInt8(0x80 | (scalar & 0x3F)))
            case 0x800...0xFFFF:
                data.append(UInt8(0xE0 | (scalar >> 12)))
                data.append(UInt8(0x80 | ((scalar >> 6) & 0x3F)))
                data.append(UInt8(0x80 | (scalar & 0x3F)))
            default:
                data.append(UInt8(0xF0 | (scalar >> 18)))
                data.append(UInt8(0x80 | ((scalar >> 12) & 0x3F)))
                data.append(UInt8(0x80 | ((scalar >> 6) & 0x3F)))
                data.append(UInt8(0x80 | (scalar & 0x3F)))
            }
        }
    }

    static func validate(_ data: Data) throws -> ValidatedRawJSON {
        guard data.count <= maximumDocumentBytes else {
            throw ValidationError.documentTooLarge(
                actual: data.count,
                maximum: maximumDocumentBytes
            )
        }
        let snapshot = immutableSnapshot(of: data)
        let sourceIdentity = SourceIdentity()
        let cursor = Cursor(
            data: snapshot,
            sourceIdentity: sourceIdentity
        )
        while try cursor.next() != nil {}
        return ValidatedRawJSON(
            data: snapshot,
            sourceIdentity: sourceIdentity
        )
    }

    private static func immutableSnapshot(of data: Data) -> Data {
        data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) in
            guard let baseAddress = bytes.baseAddress else {
                return Data()
            }
            return Data(bytes: baseAddress, count: bytes.count)
        }
    }
}
```

## Final XCTest contract

`StorageV1RawJSONGateTests.swift` is the full behavioral contract. Tests may
materialize event arrays for assertions; production code may not.

```swift
import Foundation
import XCTest
@testable import AICaddieDomain

final class StorageV1RawJSONGateTests: XCTestCase {
    private typealias Gate = StorageV1RawJSONGate
    private typealias Event = StorageV1RawJSONGate.Event

    private func validated(_ source: String) throws -> Gate.ValidatedRawJSON {
        try Gate.validate(Data(source.utf8))
    }

    private func replay(
        _ value: Gate.ValidatedRawJSON
    ) throws -> [Event] {
        let cursor = value.makeCursor()
        var result: [Event] = []
        while let event = try cursor.next() {
            result.append(event)
        }
        return result
    }

    private func rawLexeme(
        _ event: Event,
        in value: Gate.ValidatedRawJSON
    ) throws -> String {
        let bytes = try XCTUnwrap(value.rawBytes(for: event))
        return String(decoding: bytes, as: UTF8.self)
    }

    private func assertRejected(
        _ source: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try Gate.validate(Data(source.utf8)),
            source.debugDescription,
            file: file,
            line: line
        )
    }

    func testExactlyOneValueReplaysEveryTokenKindAndExactLexemes() throws {
        let source =
            #" {"k":["x",-123456789012345678901234567890e+999,true,false,null,{}]} "#
        let value = try validated(source)
        let first = try replay(value)
        let second = try replay(value)

        XCTAssertEqual(first, second)
        XCTAssertEqual(first.map(\.kind), [
            .objectStart, .objectKey, .arrayStart, .string, .number,
            .trueLiteral, .falseLiteral, .nullLiteral, .objectStart,
            .objectEnd, .arrayEnd, .objectEnd,
        ])

        let key = try XCTUnwrap(first.first { $0.kind == .objectKey })
        XCTAssertEqual(key.stringScalarCount, 1)
        XCTAssertEqual(key.decodedStringUTF8, Data("k".utf8))
        XCTAssertEqual(try rawLexeme(key, in: value), #""k""#)

        let number = try XCTUnwrap(first.first { $0.kind == .number })
        XCTAssertEqual(
            try rawLexeme(number, in: value),
            "-123456789012345678901234567890e+999"
        )
        XCTAssertEqual(value.exactBytes(), Data(source.utf8))

        let copiedCapability = value
        XCTAssertNotNil(copiedCapability.rawBytes(for: number))
        let otherSource = try validated(source)
        XCTAssertNil(otherSource.rawBytes(for: number))
    }

    func testAllTopLevelJSONKindsAreAccepted() throws {
        for source in [
            "null", "true", "false", #""text""#, "0", "-0", "-0.0",
            "1E+00", "1e999999", "[]", "{}", " \t\r\n0 \t\r\n",
        ] {
            XCTAssertNoThrow(try validated(source), source)
        }
    }

    func testSourceRangesRemainBoundToExactDataSlice() throws {
        let backing = Data("xx-0.0yy".utf8)
        let start = backing.index(backing.startIndex, offsetBy: 2)
        let end = backing.index(start, offsetBy: 4)
        let slice = backing[start..<end]
        let value = try Gate.validate(slice)
        let number = try XCTUnwrap(
            try replay(value).first { $0.kind == .number }
        )
        XCTAssertEqual(try rawLexeme(number, in: value), "-0.0")
        XCTAssertEqual(value.exactBytes(), slice)
    }

    func testValidatedCapabilityOwnsImmutableDataSnapshot() throws {
        let mutable = NSMutableData(data: Data("0".utf8))
        let aliased = Data(referencing: mutable)
        let value = try Gate.validate(aliased)

        mutable.mutableBytes.storeBytes(of: UInt8(0x78), as: UInt8.self)

        XCTAssertEqual(aliased, Data("x".utf8))
        XCTAssertEqual(value.exactBytes(), Data("0".utf8))
        let number = try XCTUnwrap(
            try replay(value).first { $0.kind == .number }
        )
        XCTAssertEqual(try rawLexeme(number, in: value), "0")
    }

    func testCursorReferenceProgressionAndFreshReplayAreUnambiguous() throws {
        let value = try validated(#"{"a":1}"#)
        let cursor = value.makeCursor()
        let alias = cursor
        XCTAssertTrue(cursor === alias)
        XCTAssertEqual(try cursor.next()?.kind, .objectStart)
        XCTAssertEqual(try alias.next()?.kind, .objectKey)

        let fresh = value.makeCursor()
        XCTAssertFalse(fresh === cursor)
        XCTAssertEqual(try fresh.next()?.kind, .objectStart)
    }

    func testEmptyMultipleTrailingAndMalformedDocumentsAreRejected() {
        for source in [
            "", " \n\t", "0 1", "true false", "0x", "+1", "01", "-",
            "1.", "1e", "1e+", "NaN", "Infinity", "[1,]", "[1 2]",
            #"{"a":1,}"#, #"{a:1}"#, #"{"a" 1}"#, "[}",
            #""unterminated"#, #""\q""#, #""\U0000""#,
            #""\u12G4""#, #""\u123""#, #""\u{1F600}""#,
            "\"raw\ncontrol\"", "\u{FEFF}0", "\u{000B}0", "\u{00A0}0",
            "// comment\n0", "/* comment */0", "0/* comment */",
        ] {
            assertRejected(source)
        }
    }

    func testInvalidUTF8AndInvalidSurrogateFormsAreRejected() {
        let invalidUTF8: [Data] = [
            Data([0x22, 0xC3, 0x28, 0x22]),
            Data([0x22, 0xC0, 0xAF, 0x22]),
            Data([0x22, 0xE0, 0x80, 0x80, 0x22]),
            Data([0x22, 0xF0, 0x80, 0x80, 0x80, 0x22]),
            Data([0x22, 0xE2, 0x82]),
            Data([0x22, 0xED, 0xA0, 0x80, 0x22]),
            Data([0x22, 0xF4, 0x90, 0x80, 0x80, 0x22]),
            Data([0xFF]),
        ]
        for data in invalidUTF8 {
            XCTAssertThrowsError(try Gate.validate(data))
        }

        for source in [
            #""\uD800""#, #""\uDC00""#, #""\uD800x""#,
            #""\uD800\u0041""#,
        ] {
            assertRejected(source)
        }
    }

    func testDecodedScalarDuplicateKeysAreRejectedPerObject() throws {
        for source in [
            #"{"a":1,"\u0061":2}"#,
            #"{"é":1,"\u00E9":2}"#,
            #"{"😀":1,"\uD83D\uDE00":2}"#,
            #"{"/":1,"\/":2}"#,
            #"{"\\":1,"\u005C":2}"#,
            #"{"":1,"":2}"#,
        ] {
            XCTAssertThrowsError(try Gate.validate(Data(source.utf8))) { error in
                guard let gateError = error as? Gate.ValidationError,
                      case .duplicateObjectKey = gateError else {
                    return XCTFail("unexpected error: \(error)")
                }
            }
        }

        XCTAssertNoThrow(try validated(#"{"a":1,"nested":{"a":2}}"#))
    }

    func testNonNFCKeysRemainDistinctAndScalarEvidenceIsExact() throws {
        let distinct = try validated(#"{"é":1,"e\u0301":2}"#)
        let keys = try replay(distinct).filter { $0.kind == .objectKey }
        let keyCounts = try keys.map {
            try XCTUnwrap($0.stringScalarCount)
        }
        XCTAssertEqual(keyCounts, [1, 2])
        let decodedKeys = try keys.map {
            try XCTUnwrap($0.decodedStringUTF8)
        }
        XCTAssertEqual(decodedKeys, [
            Data("é".utf8), Data("e\u{301}".utf8),
        ])

        let value = try validated(
            #"["","\u0000","\uD800\uDC00","\uDBFF\uDFFF","👨‍👩‍👧‍👦","a\n\u0062😀\uD83D\uDE00e\u0301"]"#
        )
        let stringEvents = try replay(value)
            .filter { $0.kind == .string }
        let counts = try stringEvents
            .map { try XCTUnwrap($0.stringScalarCount) }
        XCTAssertEqual(counts, [0, 1, 1, 1, 7, 7])
        let decodedStrings = try stringEvents.map {
            try XCTUnwrap($0.decodedStringUTF8)
        }
        XCTAssertEqual(decodedStrings, [
            Data(),
            Data([0x00]),
            Data(String(UnicodeScalar(0x10000)!).utf8),
            Data(String(UnicodeScalar(0x10FFFF)!).utf8),
            Data("👨‍👩‍👧‍👦".utf8),
            Data("a\nb😀😀e\u{301}".utf8),
        ])
    }

    func testEverySimpleEscapeDecodesToExactBytes() throws {
        let value = try validated(#""\"\\\/\b\f\n\r\t""#)
        let event = try XCTUnwrap(
            try replay(value).first { $0.kind == .string }
        )
        XCTAssertEqual(event.stringScalarCount, 8)
        XCTAssertEqual(event.decodedStringUTF8, Data([
            0x22, 0x5C, 0x2F, 0x08, 0x0C, 0x0A, 0x0D, 0x09,
        ]))
    }

    func testDocumentByteLimitIsInclusiveAndOversizeFailsBeforeParsing() throws {
        XCTAssertEqual(Gate.maximumDocumentBytes, 67_108_864)

        var exact = Data(
            repeating: 0x20,
            count: Gate.maximumDocumentBytes - 1
        )
        exact.append(0x30)
        XCTAssertNoThrow(try Gate.validate(exact))

        let oversized = Data(
            repeating: 0x20,
            count: Gate.maximumDocumentBytes + 1
        )
        XCTAssertThrowsError(try Gate.validate(oversized)) { error in
            XCTAssertEqual(
                error as? Gate.ValidationError,
                .documentTooLarge(
                    actual: Gate.maximumDocumentBytes + 1,
                    maximum: Gate.maximumDocumentBytes
                )
            )
        }
    }

    func testRecursiveDepthLimitIsInclusive() throws {
        XCTAssertEqual(Gate.maximumDepth, 64)
        let accepted = String(repeating: "[", count: 64)
            + "0"
            + String(repeating: "]", count: 64)
        XCTAssertNoThrow(try validated(accepted))

        let rejected = String(repeating: "[", count: 65)
            + "0"
            + String(repeating: "]", count: 65)
        XCTAssertThrowsError(try validated(rejected)) { error in
            guard let gateError = error as? Gate.ValidationError,
                  case .nestingTooDeep = gateError else {
                return XCTFail("unexpected error: \(error)")
            }
        }
    }

    func testKeyScalarLimitCountsDecodedScalarsAndIsInclusive() throws {
        XCTAssertEqual(Gate.maximumKeyScalars, 128)
        let acceptedKey = String(repeating: "😀", count: 128)
        XCTAssertNoThrow(try validated("{\"\(acceptedKey)\":0}"))

        let escapedPairKey = String(
            repeating: "\\uD83D\\uDE00",
            count: 128
        )
        XCTAssertNoThrow(try validated("{\"\(escapedPairKey)\":0}"))
        XCTAssertThrowsError(
            try validated("{\"\(escapedPairKey)\\u0061\":0}")
        ) { error in
            guard let gateError = error as? Gate.ValidationError,
                  case .keyTooLong = gateError else {
                return XCTFail("unexpected error: \(error)")
            }
        }

        let rejectedKey = String(repeating: "😀", count: 127)
            + "e\u{301}"
        XCTAssertThrowsError(
            try validated("{\"\(rejectedKey)\":0}")
        ) { error in
            guard let gateError = error as? Gate.ValidationError,
                  case .keyTooLong = gateError else {
                return XCTFail("unexpected error: \(error)")
            }
        }
    }

    func testAbsoluteStringScalarLimitIsInclusive() throws {
        XCTAssertEqual(Gate.maximumStringScalars, 1_398_104)
        let accepted = "\""
            + String(repeating: "a", count: Gate.maximumStringScalars)
            + "\""
        let value = try validated(accepted)
        let stringEvent = try XCTUnwrap(
            try replay(value).first { $0.kind == .string }
        )
        XCTAssertEqual(
            stringEvent.stringScalarCount,
            Gate.maximumStringScalars
        )

        let rejected = "\""
            + String(repeating: "a", count: Gate.maximumStringScalars + 1)
            + "\""
        XCTAssertThrowsError(try validated(rejected)) { error in
            guard let gateError = error as? Gate.ValidationError,
                  case .stringTooLong = gateError else {
                return XCTFail("unexpected error: \(error)")
            }
        }
    }

    func testLaterShapeCanonicalAndBase64PoliciesRemainDeferred() throws {
        let ordinary4097 = String(repeating: "x", count: 4_097)
        let nonNFC = "e\u{301}"
        let invalidBase64Looking = "%%%not canonical base64===\n"
        let source = "[\"\(ordinary4097)\",\"\(nonNFC)\","
            + "\"\(invalidBase64Looking.replacingOccurrences(of: "\n", with: "\\n"))\","
            + "1234567890123456789012345678901234567890e-999999]"
        XCTAssertNoThrow(try validated(source))

        var largeCollection = Data([0x5B])
        for item in 0...65_536 {
            if item != 0 {
                largeCollection.append(0x2C)
            }
            largeCollection.append(0x30)
        }
        largeCollection.append(0x5D)
        XCTAssertNoThrow(try Gate.validate(largeCollection))

        var largeObject = Data([0x7B])
        for item in 0...65_536 {
            if item != 0 {
                largeObject.append(0x2C)
            }
            largeObject.append(contentsOf: Data("\"k\(item)\":0".utf8))
        }
        largeObject.append(0x7D)
        XCTAssertNoThrow(try Gate.validate(largeObject))
    }

    func testInnerRequestBodyIsAcceptedWithoutStorageRootAuthority() throws {
        XCTAssertNoThrow(try validated(
            #"{"roundId":"round-1","events":[{"unknown":true}]}"#
        ))
        XCTAssertNoThrow(try validated(
            #"{"exactRequestBody":"%%%not-base64%%%=="}"#
        ))
    }

    func testValidUTF8BoundaryScalarsAreAccepted() throws {
        let valid: [Data] = [
            Data([0x22, 0xC2, 0x80, 0x22]),
            Data([0x22, 0xE0, 0xA0, 0x80, 0x22]),
            Data([0x22, 0xED, 0x9F, 0xBF, 0x22]),
            Data([0x22, 0xEE, 0x80, 0x80, 0x22]),
            Data([0x22, 0xF0, 0x90, 0x80, 0x80, 0x22]),
            Data([0x22, 0xF4, 0x8F, 0xBF, 0xBF, 0x22]),
            Data([0x22, 0xEF, 0xBB, 0xBF, 0x22]),
        ]
        for data in valid {
            XCTAssertNoThrow(try Gate.validate(data))
        }
    }
}
```

## Final mechanical contract

`test_storage_v1_raw_json_gate_assets.py` prevents an attractive but invalid
implementation based on Foundation decoding, input-array copies, an AST or a
forgeable/public token.

```python
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift")
SWIFT_TEST = Path(
    "mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift"
)


class StorageV1RawJSONGateAssetTests(unittest.TestCase):
    def source(self) -> str:
        path = ROOT / SOURCE
        self.assertTrue(path.is_file(), f"missing raw JSON gate: {SOURCE}")
        return path.read_text(encoding="utf-8")

    def test_exact_limits_and_single_gate_roster(self) -> None:
        source = self.source()
        for literal in (
            "maximumDocumentBytes = 67_108_864",
            "maximumDepth = RoundTransportLimits.maxRawJsonDepth",
            "maximumKeyScalars = RoundTransportLimits.maxJsonKeyCharacters",
            "maximumStringScalars = 1_398_104",
        ):
            with self.subTest(literal=literal):
                self.assertEqual(source.count(literal), 1)
        self.assertEqual(
            re.findall(
                r"^(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                source,
                flags=re.MULTILINE,
            ),
            ["StorageV1RawJSONGate"],
        )

    def test_capability_is_internal_nonforgeable_and_replayable(self) -> None:
        source = self.source()
        self.assertNotRegex(source, r"\bpublic\b")
        self.assertIn("struct ValidatedRawJSON", source)
        self.assertNotRegex(source, r"struct ValidatedRawJSON\s*:")
        capability = source.split("struct ValidatedRawJSON {", 1)[1].split(
            "\n    final class Cursor", 1
        )[0]
        self.assertEqual(capability.count("init("), 1)
        self.assertIn("fileprivate init(", capability)
        self.assertIn("private let data: Data", capability)
        self.assertIn("sourceIdentity: SourceIdentity", capability)
        self.assertIn("func exactBytes() -> Data", capability)
        self.assertEqual(source.count("ValidatedRawJSON("), 1)
        self.assertNotIn("init(data: Data)", source)
        self.assertNotIn("init(_ data: Data)", source)
        self.assertIn("func makeCursor() -> Cursor", source)
        self.assertIn("func rawBytes(for event: Event)", source)
        self.assertIn("final class Cursor", source)
        self.assertIn("func next() throws -> Event?", source)
        self.assertIn("fileprivate let byteRange: Range<Data.Index>", source)
        self.assertIn("let stringScalarCount: Int?", source)
        self.assertIn("let decodedStringUTF8: Data?", source)
        self.assertIn("fileprivate let sourceIdentity: SourceIdentity", source)

    def test_scanner_is_iterative_and_does_not_materialize_json(self) -> None:
        source = self.source()
        required = (
            "private var frames: [Frame] = []",
            "private final class ObjectKeySet",
            "var values: Set<Data> = []",
            "objectKeys.values.insert(decodedKey)",
            "self.frames.reserveCapacity(",
            "consumeUnescapedScalar",
            "consumeEscapedScalar",
            "consumeNumber",
            "var unescapedRunStart = index",
            "data[unescapedRunStart..<index]",
            "while try cursor.next() != nil {}",
            "immutableSnapshot(of: data)",
            "withUnsafeBytes",
            "Data(bytes: baseAddress, count: bytes.count)",
        )
        for literal in required:
            with self.subTest(literal=literal):
                self.assertIn(literal, source)

        forbidden = (
            "JSONSerialization", "JSONDecoder", "JSONEncoder",
            "JSONObjectWithData", "Array(data)", "Array(data[",
            "String(data:", "String(decoding:", "NSJSON", "NSNumber",
            "Decimal", "Base64", "base64", "precomposedString",
            "CanonicalJSON", "DomainLedgerStateV1", "JSONValue",
            "Set<String>", "Codable", "Decodable", "URLSession",
            "FileManager", "maxJsonStringCharacters", "maxEventsPerBatch",
            "maxHttpBodyBytes", "reserveCapacity(128)",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_xctest_source_pins_adversarial_and_deferred_vectors(self) -> None:
        path = ROOT / SWIFT_TEST
        self.assertTrue(path.is_file(), f"missing raw-gate tests: {SWIFT_TEST}")
        source = path.read_text(encoding="utf-8")
        for literal in (
            r'"a":1,"\u0061":2',
            r'"😀":1,"\uD83D\uDE00":2',
            r'"é":1,"e\u0301":2',
            "maximumDocumentBytes - 1",
            "String(repeating: \"[\", count: 64)",
            "String(repeating: \"[\", count: 65)",
            "String(repeating: \"😀\", count: 128)",
            "maximumStringScalars + 1",
            "String(repeating: \"x\", count: 4_097)",
            "for item in 0...65_536",
            "var largeObject = Data([0x7B])",
            "%%%not canonical base64",
            r'"exactRequestBody":"%%%not-base64%%%=="',
            "1234567890123456789012345678901234567890e-999999",
            r'"roundId":"round-1","events"',
            "0xF4, 0x8F, 0xBF, 0xBF",
            "1E+00",
            "// comment\\n0",
            "testEverySimpleEscapeDecodesToExactBytes",
            "repeating: \"\\\\uD83D\\\\uDE00\"",
            "0x22, 0xE2, 0x82",
            "Data(referencing: mutable)",
            "XCTAssertEqual(aliased, Data(\"x\".utf8))",
            "otherSource.rawBytes(for: number)",
            "decodedStringUTF8",
            "cursor === alias",
            r'#""\q""#',
        ):
            with self.subTest(literal=literal):
                self.assertIn(literal, source)

    def test_new_source_passes_repository_authority_gate(self) -> None:
        self.source()
        try:
            violations = check_authority(
                ROOT,
                changed_paths=[SOURCE.as_posix()],
            )
        except AuthorityViolation as exc:
            self.fail(f"authority gate rejected raw JSON gate: {exc}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
```

## Task 1: Establish test-only RED-1

**Files:**

- Create: `mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift`
- Create: `tests/test_storage_v1_raw_json_gate_assets.py`

- [ ] **Step 1: Add the complete wished-for tests**

Copy the two final test contracts above exactly. Do not create a production
gate or compile seam in this commit. Confirm the changed-path roster contains
only these two test files, then commit:

```bash
git add \
  mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift \
  tests/test_storage_v1_raw_json_gate_assets.py
git diff --cached --check
git commit -m "test: define storage v1 raw JSON gate"
RED1_SHA=$(git rev-parse HEAD)
test "$(git diff-tree --no-commit-id --name-only -r "$RED1_SHA" | wc -l)" -eq 2
```

- [ ] **Step 2: Observe the missing-production RED only on remote workers**

Push an immutable evidence ref, create a unique fresh homeserver clone, and run
the mechanical test there. First check shared pressure as required by
`~/HOMESERVER.md`; never fall back to the control machine.

```bash
RED1_REF="refs/heads/evidence/plan1-task5b2ar-red1-$RED1_SHA"
git push origin "$RED1_SHA:$RED1_REF"
ssh homeserver 'free -h; df -h "$HOME"; uptime'
RED1_REMOTE=$(ssh homeserver "mktemp -d \
  /home/jason/codex-runs/task5b2ar-red1-$RED1_SHA-XXXXXX")
ssh homeserver "git clone --filter=blob:none \
  https://github.com/jasonhorga/garmin-ai-caddie.git '$RED1_REMOTE' && \
  git -C '$RED1_REMOTE' checkout --detach '$RED1_SHA'"
ssh homeserver "cd '$RED1_REMOTE' && \
  /home/jason/.local/bin/uv run python -m unittest -v \
  tests.test_storage_v1_raw_json_gate_assets"
```

Expected: nonzero with controlled assertions that
`StorageV1RawJSONGate.swift` is absent. Preserve the full command, exit status,
test/failure/error counts and log SHA-256.

Dispatch Native Mobile CI against the evidence branch name and authenticate
that its `headSha` is exact `RED1_SHA`. Expected: nonzero because the wished-for
XCTest symbols do not exist. A typo, project-generation failure, unrelated
regression or moving-head run is not an observed RED.

## Task 2: Establish compile-safe behavioral RED-2

**Files:**

- Create: `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift`

- [ ] **Step 1: Add only the compile seam**

Add this entire seam. It deliberately performs only the constant-time byte
limit check and emits no events; do not borrow any final scanner body while
observing RED-2.

```swift
import Foundation

enum StorageV1RawJSONGate {
    static let maximumDocumentBytes = 67_108_864
    static let maximumDepth = RoundTransportLimits.maxRawJsonDepth
    static let maximumKeyScalars = RoundTransportLimits.maxJsonKeyCharacters
    static let maximumStringScalars = 1_398_104

    fileprivate final class SourceIdentity {
        fileprivate init() {}
    }

    enum ValidationError: Error, Equatable {
        case documentTooLarge(actual: Int, maximum: Int)
        case malformedJSON(byteOffset: Int)
        case invalidUTF8(byteOffset: Int)
        case nestingTooDeep(byteOffset: Int, maximum: Int)
        case keyTooLong(byteOffset: Int, maximumScalars: Int)
        case stringTooLong(byteOffset: Int, maximumScalars: Int)
        case duplicateObjectKey(byteOffset: Int)
    }

    struct Event: Equatable {
        enum Kind: Equatable {
            case objectStart, objectEnd, arrayStart, arrayEnd, objectKey
            case string, number, trueLiteral, falseLiteral, nullLiteral
        }

        let kind: Kind
        fileprivate let byteRange: Range<Data.Index>
        let stringScalarCount: Int?
        let decodedStringUTF8: Data?
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            kind: Kind,
            byteRange: Range<Data.Index>,
            stringScalarCount: Int?,
            decodedStringUTF8: Data?,
            sourceIdentity: SourceIdentity
        ) {
            self.kind = kind
            self.byteRange = byteRange
            self.stringScalarCount = stringScalarCount
            self.decodedStringUTF8 = decodedStringUTF8
            self.sourceIdentity = sourceIdentity
        }

        static func == (lhs: Event, rhs: Event) -> Bool {
            lhs.sourceIdentity === rhs.sourceIdentity
                && lhs.kind == rhs.kind
                && lhs.byteRange == rhs.byteRange
                && lhs.stringScalarCount == rhs.stringScalarCount
                && lhs.decodedStringUTF8 == rhs.decodedStringUTF8
        }
    }

    struct ValidatedRawJSON {
        private let data: Data
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
        }

        func makeCursor() -> Cursor {
            Cursor(data: data, sourceIdentity: sourceIdentity)
        }

        func exactBytes() -> Data {
            data
        }

        func rawBytes(for event: Event) -> Data.SubSequence? {
            guard event.sourceIdentity === sourceIdentity else {
                return nil
            }
            return data[event.byteRange]
        }
    }

    final class Cursor {
        private let data: Data
        private let sourceIdentity: SourceIdentity

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
        }

        func next() throws -> Event? {
            _ = data
            _ = sourceIdentity
            return nil
        }
    }

    static func validate(_ data: Data) throws -> ValidatedRawJSON {
        guard data.count <= maximumDocumentBytes else {
            throw ValidationError.documentTooLarge(
                actual: data.count,
                maximum: maximumDocumentBytes
            )
        }
        return ValidatedRawJSON(
            data: data,
            sourceIdentity: SourceIdentity()
        )
    }
}
```

Commit only the compile seam:

```bash
git add mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift
git diff --cached --check
git commit -m "test: expose storage raw JSON behavioral seam"
RED2_SHA=$(git rev-parse HEAD)
test "$(git rev-parse "$RED2_SHA^")" = "$RED1_SHA"
```

- [ ] **Step 2: Observe behavioral failures at exact RED-2 SHA**

Push a new immutable evidence ref. In a new unique homeserver clone, rerun the
mechanical suite. Expected: the API/limit/access tests pass and the iterative
scanner assertions fail because no scanner exists.

Dispatch Native Mobile CI at exact `RED2_SHA`. Expected: the test target now
compiles, while malformed/duplicate/depth/string/event assertions fail for the
intended accept-all/no-events seam. Record exact run/job IDs, failing test
names and log SHA-256. Do not treat compilation errors as behavioral RED-2.

## Task 3: Implement minimal GREEN

**Files:**

- Modify: `mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift`

- [ ] **Step 1: Replace the seam with the frozen iterative scanner**

Replace the RED-2 file with the complete production contract above. Do not
change either test to accommodate the implementation. Do not reuse
`OfflineStore.JSONPrefixScanner`: it is an app-private prefix classifier with
different limits and no duplicate/scalar evidence.

- [ ] **Step 2: Self-review the scanner invariants before committing**

Check, from source rather than inference:

- every successful scalar or completed container calls `finishValue()` once;
- a container calls it only when closing, never when opening;
- a trailing comma reaches an expecting-value/key state and is rejected;
- direct UTF-8 rejects overlong forms, surrogate code points and values above
  `U+10FFFF`;
- escaped high surrogates require exactly one escaped low surrogate;
- key identity stores decoded UTF-8 and scopes the set to one live object;
- string counts increment once per decoded scalar, including a surrogate pair;
- the byte limit precedes one forced owned snapshot, and later validation and
  every replay read only that snapshot rather than caller-controlled backing;
- each event carries the capability's source identity and a checked raw range,
  so another capability cannot resolve or reuse it;
- object-key and value-string events both expose decoded UTF-8 plus their exact
  scalar count, preserving the predecode evidence required by S and T;
- `Cursor` is a reference type, aliases advance one parser state, and separate
  `makeCursor()` calls start independent deterministic replays;
- consecutive unescaped string bytes are appended as runs rather than through
  one `Data` slice/append operation per scalar;
- number parsing performs no numeric conversion and ranges cover exact bytes;
- no recursion, AST, `Array(data)`, Foundation JSON parser or public API exists.

Commit the one production file:

```bash
git add mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift
git diff --cached --check
git commit -m "feat: validate storage v1 raw JSON"
GREEN_SHA=$(git rev-parse HEAD)
test "$(git rev-parse "$GREEN_SHA^")" = "$RED2_SHA"
```

## Task 4: Prove GREEN remotely

- [ ] **Step 1: Run focused and regression mechanical suites on homeserver**

Push an immutable GREEN evidence ref and use a fresh exact-SHA clone. Before
running, inspect homeserver pressure; do not reuse or overwrite the RED clones.

```bash
set -euo pipefail
GREEN_SHA=$(git rev-parse HEAD)
GREEN_REF="refs/heads/evidence/plan1-task5b2ar-green-$GREEN_SHA"
git push origin "$GREEN_SHA:$GREEN_REF"
ssh homeserver 'free -h; df -h "$HOME"; uptime'
GREEN_REMOTE_LOG="/tmp/task5b2ar-green-$GREEN_SHA-homeserver.log"
ssh homeserver bash -s -- "$GREEN_SHA" "$GREEN_REF" 2>&1 <<'REMOTE' | \
  tee "$GREEN_REMOTE_LOG"
set -euo pipefail
GREEN_SHA=$1
GREEN_REF=$2
RUN_DIR=$(mktemp -d \
  "/home/jason/codex-runs/task5b2ar-green-${GREEN_SHA}-XXXXXX")
CARD_PATH="docs/superpowers/task-cards/2026-07-25-plan1-task5b2a-r-raw-json-gate.md"
printf 'RUN_DIR=%s\n' "$RUN_DIR"
git clone --quiet --no-checkout \
  https://github.com/jasonhorga/garmin-ai-caddie.git "$RUN_DIR"
cd "$RUN_DIR"
git fetch --quiet origin "$GREEN_REF"
git checkout --quiet --detach "$GREEN_SHA"
test "$(git rev-parse HEAD)" = "$GREEN_SHA"
CARD_SHA=$(git log --diff-filter=A -1 --format=%H -- "$CARD_PATH")
test -n "$CARD_SHA"
test "$(git cat-file -t "$CARD_SHA")" = commit
git cat-file -e "$CARD_SHA:$CARD_PATH"
git merge-base --is-ancestor "$CARD_SHA" HEAD

/home/jason/.local/bin/uv run python -m unittest -v \
  tests.test_storage_v1_raw_json_gate_assets \
  tests.test_storage_v1_literal_schema_assets \
  tests.test_swift_canonical_runtime_assets \
  tests.test_contract_authority \
  tests.test_contract_codegen

/home/jason/.local/bin/uv run python tools/contracts/generate_contracts.py
test -z "$(git status --porcelain=v1)"

git diff --no-renames --name-only -z "$CARD_SHA"..HEAD | \
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py

git diff --check "$CARD_SHA"..HEAD
test -z "$(git status --porcelain=v1)"
REMOTE
test "${PIPESTATUS[0]}" -eq 0
wc -l -c "$GREEN_REMOTE_LOG"
sha256sum "$GREEN_REMOTE_LOG"
```

Expected: exit zero, zero failures/errors, exact checked-out SHA, clean status
and `git diff --check` zero. Preserve the complete log and SHA-256. Report the
actual test count; do not predict it in advance.

- [ ] **Step 2: Run Native Mobile CI at exact GREEN SHA**

Convert `GREEN_REF` to its branch name, dispatch `.github/workflows/native-mobile.yml`,
and locate only the newly created `workflow_dispatch` run whose `headSha`
equals `GREEN_SHA`. Use this exact evidence binding:

```bash
set -euo pipefail
command -v gh sha256sum bsdtar >/dev/null
GREEN_SHA=$(git rev-parse HEAD)
GREEN_REF="refs/heads/evidence/plan1-task5b2ar-green-$GREEN_SHA"
REMOTE_GREEN_SHA=$(git ls-remote --heads origin "$GREEN_REF" |
  awk 'NR == 1 {print $1}')
test "$REMOTE_GREEN_SHA" = "$GREEN_SHA"
GREEN_REF_NAME=${GREEN_REF#refs/heads/}
test "$GREEN_REF_NAME" != "$GREEN_REF"

DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run native-mobile.yml --ref "$GREEN_REF_NAME"
RUN_ID=
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list \
    --workflow native-mobile.yml \
    --branch "$GREEN_REF_NAME" \
    --event workflow_dispatch \
    --limit 100 \
    --json databaseId,headSha,createdAt \
    --jq "map(select(.headSha == \"$GREEN_SHA\" and .createdAt >= \"$DISPATCHED_AT\")) | sort_by(.createdAt) | .[-1].databaseId // empty")
  if test -n "$RUN_ID"; then
    break
  fi
  sleep 2
done
test -n "$RUN_ID"
RUN_HEAD_SHA=$(gh run view "$RUN_ID" --json headSha --jq .headSha)
test "$RUN_HEAD_SHA" = "$GREEN_SHA"
gh run watch "$RUN_ID" --exit-status
test "$(gh run view "$RUN_ID" --json headSha --jq .headSha)" = "$GREEN_SHA"
test "$(gh run view "$RUN_ID" --json conclusion --jq .conclusion)" = success

JOB_IDS=$(gh run view "$RUN_ID" --json jobs \
  --jq '.jobs[] | [.databaseId, .name, .conclusion] | @tsv')
test -n "$JOB_IDS"
printf '%s\n' "$JOB_IDS"
RUN_LOG="/tmp/task5b2ar-green-$GREEN_SHA-native-run-$RUN_ID.log"
gh run view "$RUN_ID" --log > "$RUN_LOG"
wc -l -c "$RUN_LOG"
sha256sum "$RUN_LOG"

REPOSITORY=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
ARTIFACT_ID=$(gh api \
  "repos/$REPOSITORY/actions/runs/$RUN_ID/artifacts" \
  --jq '.artifacts[] | select(.name == "native-build-evidence" and .expired == false) | .id' |
  tail -n 1)
test -n "$ARTIFACT_ID"
ARTIFACT_ZIP="/tmp/task5b2ar-green-$GREEN_SHA-native-build-evidence-$ARTIFACT_ID.zip"
gh api -H 'Accept: application/vnd.github+json' \
  "repos/$REPOSITORY/actions/artifacts/$ARTIFACT_ID/zip" > "$ARTIFACT_ZIP"
test -s "$ARTIFACT_ZIP"
wc -c "$ARTIFACT_ZIP"
sha256sum "$ARTIFACT_ZIP"
ARTIFACT_DIR=$(mktemp -d \
  "/tmp/task5b2ar-green-$GREEN_SHA-native-build-evidence-XXXXXX")
bsdtar -xf "$ARTIFACT_ZIP" -C "$ARTIFACT_DIR"
find "$ARTIFACT_DIR" -type f -print0 | sort -z | xargs -0 sha256sum
```

Retry transient `429`/`503` responses with bounded exponential backoff, but do
not change `GREEN_REF`, `GREEN_SHA` or `DISPATCHED_AT` for the authenticated
dispatch attempt. After recovery, continue locating only the exact-SHA run.
The completed run must show:

- `StorageV1RawJSONGateTests` executed with zero failures;
- the complete Domain suite green;
- complete iOS, Watch and live UI suites green; and
- the SwiftJCS source/artifact boundary still green.

Download the complete job log and native-build-evidence artifact. Record exact
run/job/artifact IDs, suite counts, byte counts and SHA-256 values. A canceled,
partial or wrong-SHA run is not evidence. A transient 429/503 is retried with
bounded exponential backoff while other safe audit work continues.

- [ ] **Step 3: Authenticate the exact implementation boundary**

At the candidate SHA, require:

```bash
test "$(git diff --name-only "$CARD_SHA..$GREEN_SHA" | wc -l)" -eq 3
test -z "$(git diff --name-only "$CARD_SHA..$GREEN_SHA" | \
  rg -v '^(mobile/ios/AICaddieDomain/StorageV1RawJSONGate.swift|mobile/ios/AICaddieDomainTests/StorageV1RawJSONGateTests.swift|tests/test_storage_v1_raw_json_gate_assets.py)$' || true)"
git diff --check "$CARD_SHA..$GREEN_SHA"
```

Independently search the production range for public APIs, Foundation JSON
parsers, number conversions, recursion, typed decode, Base64/NFC/shape/graph,
persistence, mutation, lifecycle and network leakage.

## Task 5: SPEC, QUALITY and verification record

- [ ] **Step 1: Run independent SPEC review**

Give a fresh read-only reviewer the frozen card hash, design hash, exact
`CARD_SHA..GREEN_SHA` diff, RED-1/RED-2/GREEN evidence and Native artifacts.
The reviewer checks every frozen acceptance/rejection and every deferral.
Critical or Important findings return to the same implementation writer, who
adds a failing regression test before any correction, repeats GREEN/REMOTE,
and sends the new exact candidate back to SPEC.

- [ ] **Step 2: Run independent QUALITY review only after SPEC PASS**

Give a different fresh read-only reviewer the same authenticated range plus
the SPEC verdict. Review scanner state transitions, UTF-8/escape correctness,
offset safety, access control, streaming memory behavior, test strength and
repository fit. Fix and re-review every Critical or Important finding; Minor
findings are either fixed safely through TDD or explicitly recorded.

- [ ] **Step 3: Record evidence and POP**

Create
`docs/superpowers/reviews/2026-07-25-plan1-task5b2a-r-raw-json-gate-verification.md`
with exact commits/trees, frozen hashes, commands, run/job/artifact IDs,
logs/hashes, test counts, review verdicts and exclusions. Update the Execution
Index and packet map to mark only 5B2a-R `VERIFIED`; next POP is 5B2a-S.

Do not mark Task 5B, Task 5 or Plan 1 complete/frozen. The standing strict
Pydantic compatibility-serializer audit, cross-plan iOS fixture/real-asset
authority gate, all remaining mechanical checks and final Plan 1 SHA-256 stay
open until their named later gates. Once Plan 1 is finally declared frozen and
hashed, no later edit to it is permitted.

## Card freeze checklist

Before committing this card:

- recompute the approved design SHA-256;
- verify every relative link resolves;
- scan for unfinished markers, vague future-work prose and inconsistent API
  names;
- compare every requirement and deferral against the approved design;
- confirm the worktree diff is this card only and `git diff --check` passes;
- obtain read-only specification and Swift/Unicode preflight verdicts; and
- commit/push this card alone, then record its exact commit as `CARD_SHA`.

There is no open Owner decision in 5B2a-R.
