import Foundation

internal enum StorageV1StreamingShapeValidator {
    private indirect enum Shape {
        case string(maximumScalars: Int)
        case int
        case base64(maximumTextScalars: Int, maximumDecodedBytes: Int)
        case array(item: Shape, minimumCount: Int?, maximumCount: Int?)
        case dynamicMap(value: Shape, minimumCount: Int?, maximumCount: Int?)
        case nullable(Shape)
        case literalInt(Int)
        case record([Member])
        case openString(maximumScalars: Int)
        case closedEnum([Data])
        case recursiveJSON(maximumStringScalars: Int)
        case canonicalJSON(value: Shape, maximumBytes: Int, maximumDepth: Int)
    }

    private struct Member {
        let keyUTF8: Data
        let shape: Shape
        let seenBit: UInt64
    }

    private final class EventStream {
        private let cursor: StorageV1RawJSONGate.Cursor
        private var buffered: StorageV1RawJSONGate.Event?
        private var reachedEnd = false

        init(cursor: StorageV1RawJSONGate.Cursor) {
            self.cursor = cursor
        }

        func peek() throws -> StorageV1RawJSONGate.Event? {
            if buffered == nil, !reachedEnd {
                buffered = try cursor.next()
                reachedEnd = buffered == nil
            }
            return buffered
        }

        func take() throws -> StorageV1RawJSONGate.Event {
            guard let event = try peek() else {
                throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
            }
            buffered = nil
            return event
        }
    }

    private struct DescriptorCompiler {
        mutating func root(named rootName: String) throws -> Shape {
            guard let root = storageV1Roots.first(where: {
                $0.name == rootName
            }) else {
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
            var activeReferences = Set<String>()
            return try compile(
                root.shape,
                activeReferences: &activeReferences
            )
        }

        private mutating func compile(
            _ descriptor: StorageV1ShapeDescriptor,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            switch descriptor {
            case .scalar(let scalar):
                return try compile(
                    scalar,
                    activeReferences: &activeReferences
                )

            case .reference(let name):
                return try compileReference(
                    named: name,
                    activeReferences: &activeReferences
                )

            case .array(let item):
                return .array(
                    item: try compile(
                        item,
                        activeReferences: &activeReferences
                    ),
                    minimumCount: nil,
                    maximumCount: nil
                )

            case .dynamicMap(let value):
                return .dynamicMap(
                    value: try compile(
                        value,
                        activeReferences: &activeReferences
                    ),
                    minimumCount: nil,
                    maximumCount: nil
                )

            case .nullable(let value):
                return .nullable(
                    try compile(
                        value,
                        activeReferences: &activeReferences
                    )
                )

            case .constrained(let policy, let value):
                let limit = try limitDescriptor(for: policy)
                return try compile(
                    value,
                    constrainedBy: limit,
                    activeReferences: &activeReferences
                )

            case .literalInt(let value):
                return .literalInt(value)

            case .record(let members):
                guard members.count < UInt64.bitWidth else {
                    throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
                }
                var compiledMembers: [Member] = []
                compiledMembers.reserveCapacity(members.count)
                for (index, member) in members.enumerated() {
                    let keyUTF8 = Data(member.name.utf8)
                    guard !compiledMembers.contains(where: {
                        $0.keyUTF8 == keyUTF8
                    }) else {
                        throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
                    }
                    compiledMembers.append(Member(
                        keyUTF8: keyUTF8,
                        shape: try compile(
                            member.shape,
                            activeReferences: &activeReferences
                        ),
                        seenBit: UInt64(1) << UInt64(index)
                    ))
                }
                return .record(compiledMembers)

            case .collection(_, let items):
                return .array(
                    item: try compile(
                        items,
                        activeReferences: &activeReferences
                    ),
                    minimumCount: nil,
                    maximumCount: nil
                )

            case .openString(let profile):
                return .openString(
                    maximumScalars: try stringMaximum(for: profile)
                )

            case .closedEnum(let values):
                return .closedEnum(values.map { Data($0.utf8) })

            case .recursiveJSONValue(let stringProfile):
                return .recursiveJSON(
                    maximumStringScalars: try stringMaximum(
                        for: stringProfile
                    )
                )
            }
        }

        private mutating func compile(
            _ scalar: StorageV1ScalarDescriptor,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            _ = activeReferences
            switch scalar {
            case .string(let profile):
                return .string(
                    maximumScalars: try stringMaximum(for: profile)
                )
            case .int:
                return .int
            case .base64Data:
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
        }

        private mutating func compile(
            _ descriptor: StorageV1ShapeDescriptor,
            constrainedBy limit: StorageV1LimitProfileDescriptor,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            switch limit {
            case .count(let minimum, let maximum):
                return try compileCounted(
                    descriptor,
                    minimum: minimum.map(limitValue),
                    maximum: limitValue(maximum),
                    activeReferences: &activeReferences
                )

            case .base64(
                _, _, let maximumTextScalars, let maximumDecodedBytes
            ):
                return try compileBase64(
                    descriptor,
                    maximumTextScalars: limitValue(maximumTextScalars),
                    maximumDecodedBytes: limitValue(maximumDecodedBytes),
                    activeReferences: &activeReferences
                )

            case .canonicalJSON(let maximumBytes, let maximumDepth):
                return .canonicalJSON(
                    value: try compile(
                        descriptor,
                        activeReferences: &activeReferences
                    ),
                    maximumBytes: limitValue(maximumBytes),
                    maximumDepth: limitValue(maximumDepth)
                )

            case .stringScalars:
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
        }

        private mutating func compileCounted(
            _ descriptor: StorageV1ShapeDescriptor,
            minimum: Int?,
            maximum: Int,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            switch descriptor {
            case .reference(let name):
                guard activeReferences.insert(name).inserted,
                      let referenced = storageV1Types.first(where: {
                          $0.name == name
                      }) else {
                    throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
                }
                defer { activeReferences.remove(name) }
                return try compileCounted(
                    referenced.shape,
                    minimum: minimum,
                    maximum: maximum,
                    activeReferences: &activeReferences
                )

            case .array(let item), .collection(_, let item):
                return .array(
                    item: try compile(
                        item,
                        activeReferences: &activeReferences
                    ),
                    minimumCount: minimum,
                    maximumCount: maximum
                )

            case .dynamicMap(let value):
                return .dynamicMap(
                    value: try compile(
                        value,
                        activeReferences: &activeReferences
                    ),
                    minimumCount: minimum,
                    maximumCount: maximum
                )

            default:
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
        }

        private mutating func compileBase64(
            _ descriptor: StorageV1ShapeDescriptor,
            maximumTextScalars: Int,
            maximumDecodedBytes: Int,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            switch descriptor {
            case .reference(let name):
                guard activeReferences.insert(name).inserted,
                      let referenced = storageV1Types.first(where: {
                          $0.name == name
                      }) else {
                    throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
                }
                defer { activeReferences.remove(name) }
                return try compileBase64(
                    referenced.shape,
                    maximumTextScalars: maximumTextScalars,
                    maximumDecodedBytes: maximumDecodedBytes,
                    activeReferences: &activeReferences
                )

            case .scalar(.base64Data):
                return .base64(
                    maximumTextScalars: maximumTextScalars,
                    maximumDecodedBytes: maximumDecodedBytes
                )

            default:
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
        }

        private mutating func compileReference(
            named name: String,
            activeReferences: inout Set<String>
        ) throws -> Shape {
            guard activeReferences.insert(name).inserted,
                  let referenced = storageV1Types.first(where: {
                      $0.name == name
                  }) else {
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
            defer { activeReferences.remove(name) }
            return try compile(
                referenced.shape,
                activeReferences: &activeReferences
            )
        }

        private func stringMaximum(
            for profile: StorageV1ProfileName
        ) throws -> Int {
            guard case .stringScalars(let maximum) = try limitDescriptor(
                for: profile
            ) else {
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
            return limitValue(maximum)
        }

        private func limitDescriptor(
            for policy: StorageV1PolicyName
        ) throws -> StorageV1LimitProfileDescriptor {
            guard let policyDescriptor = storageV1Policies.first(where: {
                policyMatches($0.name, policy)
            }) else {
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
            return try limitDescriptor(for: policyDescriptor.profile)
        }

        private func limitDescriptor(
            for profile: StorageV1ProfileName
        ) throws -> StorageV1LimitProfileDescriptor {
            guard let profileDescriptor = storageV1LimitProfiles.first(where: {
                profileMatches($0.name, profile)
            }) else {
                throw StorageV1ShapeCodec.ValidationError.invalidDescriptor
            }
            return profileDescriptor.descriptor
        }

        private func limitValue(_ reference: StorageV1LimitReference) -> Int {
            switch reference {
            case .literal(let value), .authority(_, let value):
                return value
            }
        }

        private func policyMatches(
            _ lhs: StorageV1PolicyName,
            _ rhs: StorageV1PolicyName
        ) -> Bool {
            switch (lhs, rhs) {
            case (.rootCollection, .rootCollection),
                 (.preparedSlots, .preparedSlots),
                 (.requestBody, .requestBody),
                 (.eventOrEnvelope, .eventOrEnvelope):
                return true
            default:
                return false
            }
        }

        private func profileMatches(
            _ lhs: StorageV1ProfileName,
            _ rhs: StorageV1ProfileName
        ) -> Bool {
            switch (lhs, rhs) {
            case (.ordinaryString, .ordinaryString),
                 (.rootCollection, .rootCollection),
                 (.preparedSlots, .preparedSlots),
                 (.requestBody, .requestBody),
                 (.eventOrEnvelope, .eventOrEnvelope):
                return true
            default:
                return false
            }
        }
    }

    internal static func validate(
        cursor: StorageV1RawJSONGate.Cursor,
        source: StorageV1RawJSONGate.ValidatedRawJSON,
        rootName: String
    ) throws {
        var compiler = DescriptorCompiler()
        let root = try compiler.root(named: rootName)
        let stream = EventStream(cursor: cursor)
        _ = try validateValue(root, stream: stream, source: source)
        guard try stream.peek() == nil else {
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
    }

    private static func validateValue(
        _ shape: Shape,
        stream: EventStream,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> StorageV1CanonicalMetrics.Value {
        switch shape {
        case .string(let maximumScalars),
             .openString(let maximumScalars):
            let event = try take(.string, from: stream)
            let text = try stringComponents(event)
            return try StorageV1ShapeScalarValidation.validateString(
                decodedUTF8: text.utf8,
                scalarCount: text.scalarCount,
                maximumScalars: maximumScalars
            )

        case .int:
            let event = try take(.number, from: stream)
            return try StorageV1ShapeScalarValidation.validateInteger(
                rawBytes: try rawBytes(for: event, source: source)
            ).metrics

        case .base64(let maximumTextScalars, let maximumDecodedBytes):
            let event = try take(.string, from: stream)
            let text = try stringComponents(event)
            return try StorageV1ShapeScalarValidation.validateBase64(
                decodedUTF8: text.utf8,
                scalarCount: text.scalarCount,
                maximumTextScalars: maximumTextScalars,
                maximumDecodedBytes: maximumDecodedBytes
            )

        case .array(let item, let minimumCount, let maximumCount):
            return try validateArray(
                item: item,
                minimumCount: minimumCount,
                maximumCount: maximumCount,
                stream: stream,
                source: source
            )

        case .dynamicMap(let value, let minimumCount, let maximumCount):
            return try validateDynamicMap(
                value: value,
                minimumCount: minimumCount,
                maximumCount: maximumCount,
                stream: stream,
                source: source
            )

        case .nullable(let value):
            if try stream.peek()?.kind == .nullLiteral {
                _ = try stream.take()
                return StorageV1CanonicalMetrics.scalar(canonicalBytes: 4)
            }
            return try validateValue(value, stream: stream, source: source)

        case .literalInt(let expected):
            let event = try take(.number, from: stream)
            let result = try StorageV1ShapeScalarValidation.validateInteger(
                rawBytes: try rawBytes(for: event, source: source)
            )
            guard result.value == expected else {
                throw StorageV1ShapeCodec.ValidationError.invalidLiteral
            }
            return result.metrics

        case .record(let members):
            return try validateRecord(
                members: members,
                stream: stream,
                source: source
            )

        case .closedEnum(let values):
            let event = try take(.string, from: stream)
            let text = try stringComponents(event)
            try StorageV1ShapeScalarValidation.validateNFC(text.utf8)
            guard values.contains(text.utf8) else {
                throw StorageV1ShapeCodec.ValidationError.invalidLiteral
            }
            return StorageV1CanonicalMetrics.quotedString(
                decodedUTF8: text.utf8
            )

        case .recursiveJSON(let maximumStringScalars):
            return try validateRecursiveJSON(
                maximumStringScalars: maximumStringScalars,
                stream: stream,
                source: source
            )

        case .canonicalJSON(
            let value, let maximumBytes, let maximumDepth
        ):
            let metrics = try validateValue(
                value,
                stream: stream,
                source: source
            )
            guard StorageV1CanonicalMetrics.isWithin(
                metrics,
                maximumBytes: maximumBytes,
                maximumDepth: maximumDepth
            ) else {
                throw StorageV1ShapeCodec.ValidationError.canonicalLimitExceeded
            }
            return metrics
        }
    }

    private static func validateArray(
        item: Shape,
        minimumCount: Int?,
        maximumCount: Int?,
        stream: EventStream,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> StorageV1CanonicalMetrics.Value {
        _ = try take(.arrayStart, from: stream)
        var count = 0
        var metrics = StorageV1CanonicalMetrics.Container()
        while try stream.peek()?.kind != .arrayEnd {
            count = try nextCount(count, maximum: maximumCount)
            let child = try validateValue(item, stream: stream, source: source)
            metrics.appendArrayValue(child)
        }
        _ = try take(.arrayEnd, from: stream)
        try validateMinimum(count, minimum: minimumCount)
        return metrics.value
    }

    private static func validateDynamicMap(
        value: Shape,
        minimumCount: Int?,
        maximumCount: Int?,
        stream: EventStream,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> StorageV1CanonicalMetrics.Value {
        _ = try take(.objectStart, from: stream)
        var count = 0
        var metrics = StorageV1CanonicalMetrics.Container()
        while try stream.peek()?.kind != .objectEnd {
            let keyEvent = try take(.objectKey, from: stream)
            let key = try stringComponents(keyEvent)
            try StorageV1ShapeScalarValidation.validateNFC(key.utf8)
            count = try nextCount(count, maximum: maximumCount)
            let child = try validateValue(value, stream: stream, source: source)
            metrics.appendObjectMember(
                key: StorageV1CanonicalMetrics.quotedString(
                    decodedUTF8: key.utf8
                ),
                value: child
            )
        }
        _ = try take(.objectEnd, from: stream)
        try validateMinimum(count, minimum: minimumCount)
        return metrics.value
    }

    private static func validateRecord(
        members: [Member],
        stream: EventStream,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> StorageV1CanonicalMetrics.Value {
        _ = try take(.objectStart, from: stream)
        var seen: UInt64 = 0
        var metrics = StorageV1CanonicalMetrics.Container()
        while try stream.peek()?.kind != .objectEnd {
            let keyEvent = try take(.objectKey, from: stream)
            let key = try stringComponents(keyEvent)
            try StorageV1ShapeScalarValidation.validateNFC(key.utf8)
            guard let member = members.first(where: {
                $0.keyUTF8 == key.utf8
            }), seen & member.seenBit == 0 else {
                throw StorageV1ShapeCodec.ValidationError.unknownRecordMember
            }
            seen |= member.seenBit
            let child = try validateValue(
                member.shape,
                stream: stream,
                source: source
            )
            metrics.appendObjectMember(
                key: StorageV1CanonicalMetrics.quotedString(
                    decodedUTF8: key.utf8
                ),
                value: child
            )
        }
        _ = try take(.objectEnd, from: stream)
        let expected = members.reduce(UInt64(0)) { $0 | $1.seenBit }
        guard seen == expected else {
            throw StorageV1ShapeCodec.ValidationError.missingRecordMember
        }
        return metrics.value
    }

    private static func validateRecursiveJSON(
        maximumStringScalars: Int,
        stream: EventStream,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> StorageV1CanonicalMetrics.Value {
        guard let kind = try stream.peek()?.kind else {
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
        switch kind {
        case .objectStart:
            return try validateDynamicMap(
                value: .recursiveJSON(
                    maximumStringScalars: maximumStringScalars
                ),
                minimumCount: nil,
                maximumCount: nil,
                stream: stream,
                source: source
            )
        case .arrayStart:
            return try validateArray(
                item: .recursiveJSON(
                    maximumStringScalars: maximumStringScalars
                ),
                minimumCount: nil,
                maximumCount: nil,
                stream: stream,
                source: source
            )
        case .string:
            let event = try stream.take()
            let text = try stringComponents(event)
            return try StorageV1ShapeScalarValidation.validateString(
                decodedUTF8: text.utf8,
                scalarCount: text.scalarCount,
                maximumScalars: maximumStringScalars
            )
        case .number:
            let event = try stream.take()
            return try StorageV1ShapeScalarValidation.validateRecursiveNumber(
                rawBytes: try rawBytes(for: event, source: source)
            )
        case .trueLiteral:
            _ = try stream.take()
            return StorageV1CanonicalMetrics.scalar(canonicalBytes: 4)
        case .falseLiteral:
            _ = try stream.take()
            return StorageV1CanonicalMetrics.scalar(canonicalBytes: 5)
        case .nullLiteral:
            _ = try stream.take()
            return StorageV1CanonicalMetrics.scalar(canonicalBytes: 4)
        default:
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
    }

    private static func take(
        _ kind: StorageV1RawJSONGate.Event.Kind,
        from stream: EventStream
    ) throws -> StorageV1RawJSONGate.Event {
        let event = try stream.take()
        guard event.kind == kind else {
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
        return event
    }

    private static func stringComponents(
        _ event: StorageV1RawJSONGate.Event
    ) throws -> (utf8: Data, scalarCount: Int) {
        guard let utf8 = event.decodedStringUTF8,
              let scalarCount = event.stringScalarCount else {
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
        return (utf8, scalarCount)
    }

    private static func rawBytes(
        for event: StorageV1RawJSONGate.Event,
        source: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> Data {
        guard let bytes = source.rawBytes(for: event) else {
            throw StorageV1ShapeCodec.ValidationError.unexpectedEvent
        }
        return Data(bytes)
    }

    private static func nextCount(
        _ current: Int,
        maximum: Int?
    ) throws -> Int {
        let (next, overflow) = current.addingReportingOverflow(1)
        guard !overflow, maximum.map({ next <= $0 }) ?? true else {
            throw StorageV1ShapeCodec.ValidationError.collectionLimitExceeded
        }
        return next
    }

    private static func validateMinimum(
        _ count: Int,
        minimum: Int?
    ) throws {
        guard minimum.map({ count >= $0 }) ?? true else {
            throw StorageV1ShapeCodec.ValidationError.collectionLimitExceeded
        }
    }
}
