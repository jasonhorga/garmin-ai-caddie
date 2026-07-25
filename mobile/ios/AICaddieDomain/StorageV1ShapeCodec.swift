internal struct ValidatedStorageV1Shape {
    internal let state: DomainLedgerStateV1

    fileprivate init(state: DomainLedgerStateV1) {
        self.state = state
    }
}

internal enum StorageV1ShapeCodec {
    internal enum ValidationError: Swift.Error, Equatable {
        case notImplemented
    }

    internal static func decode(
        _ validatedRawJSON: StorageV1RawJSONGate.ValidatedRawJSON
    ) throws -> ValidatedStorageV1Shape {
        _ = validatedRawJSON
        throw ValidationError.notImplemented
    }
}
