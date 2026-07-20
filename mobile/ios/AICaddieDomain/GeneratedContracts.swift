// generated; do not edit
public let canonicalContractSourceSHA256 = "5a9de6f1c17bd1338b7a0b25d0c935611b38c09627423f7baad12909f594a71a"

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
