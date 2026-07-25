import Foundation

internal struct ValidatedStorageV1Shape {
    internal let state: DomainLedgerStateV1

    fileprivate init(state: DomainLedgerStateV1) {
        self.state = state
    }
}

internal enum StorageV1ShapeCodec {
    internal enum ValidationError: Swift.Error, Equatable {
        case invalidDescriptor
        case unexpectedEvent
        case missingRecordMember
        case unknownRecordMember
        case nonNFCString
        case stringLimitExceeded
        case collectionLimitExceeded
        case invalidBase64
        case invalidNumber
        case invalidLiteral
        case canonicalLimitExceeded
    }

    internal static func decode(
        _ validatedRawJSON: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> ValidatedStorageV1Shape {
        let cursor = validatedRawJSON.makeCursor()
        try StorageV1StreamingShapeValidator.validate(
            cursor: cursor,
            source: validatedRawJSON,
            rootName: "storageDocument"
        )
        let state = try JSONDecoder().decode(
            DomainLedgerStateV1.self,
            from: validatedRawJSON.exactBytes()
        )
        return ValidatedStorageV1Shape(state: state)
    }
}
