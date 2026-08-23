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
