// generated; do not edit
public let canonicalContractSourceSHA256 = "b2acae87f2672c2d7baf6004b803a2669d8908be89c27d4b9bf83df71d645d35"

public struct CanonicalObjectDescriptor: Sendable, Equatable {
    public let objectName: String
    public let domainTag: String
    public let schemaRef: String
    public let includedFields: [String]
    public let excludedFields: [String]
}

public enum GeneratedCanonicalObjects {
    public static let byDomain: [String: CanonicalObjectDescriptor] = [
        "CanonicalFixtureAlpha/v1": CanonicalObjectDescriptor(objectName: "CanonicalFixtureAlpha", domainTag: "CanonicalFixtureAlpha/v1", schemaRef: "contracts/canonical/canonical_fixture_v1.schema.json", includedFields: ["*"], excludedFields: ["transportNote"]),
        "CanonicalFixtureBeta/v1": CanonicalObjectDescriptor(objectName: "CanonicalFixtureBeta", domainTag: "CanonicalFixtureBeta/v1", schemaRef: "contracts/canonical/canonical_fixture_v1.schema.json", includedFields: ["*"], excludedFields: ["transportNote"]),
    ]
}
