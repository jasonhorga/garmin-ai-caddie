import Foundation
import XCTest
@testable import AICaddieDomain

private struct NumberVector: Decodable {
    let bitPatternHex: String
    let expected: String
}

private struct EncodableDoublePayload: Encodable {
    let value: Double
}

private struct EncodableIntegerPayload: Encodable {
    let value: Int64
}

final class CanonicalJSONTests: XCTestCase {
    private func utf8String(_ data: Data) throws -> String {
        try XCTUnwrap(String(data: data, encoding: .utf8))
    }

    private func lowercaseHex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    private func numberVectorURL() throws -> URL {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: CanonicalJSONTests.self)
        #endif
        if let nested = bundle.url(
            forResource: "rfc8785_number_vectors",
            withExtension: "json",
            subdirectory: "Fixtures"
        ) {
            return nested
        }
        return try XCTUnwrap(
            bundle.url(
                forResource: "rfc8785_number_vectors",
                withExtension: "json"
            ),
            "missing copied fixture Fixtures/rfc8785_number_vectors.json"
        )
    }

    func testJSONValueCodableCoversEveryCaseAndKeepsIntegersDistinct() throws {
        let source = Data(
            #"{"integer":1,"number":1.25,"null":null,"bool":true,"string":"球场","array":[2,false],"object":{"nested":"value"}}"#.utf8
        )
        let expected: JSONValue = .object([
            "integer": .integer(1),
            "number": .number(1.25),
            "null": .null,
            "bool": .bool(true),
            "string": .string("球场"),
            "array": .array([.integer(2), .bool(false)]),
            "object": .object(["nested": .string("value")]),
        ])

        let decoded = try JSONDecoder().decode(JSONValue.self, from: source)
        XCTAssertEqual(decoded, expected)
        XCTAssertEqual(
            try JSONDecoder().decode(
                JSONValue.self,
                from: JSONEncoder().encode(decoded)
            ),
            expected
        )

        let fixedCases: [(JSONValue, String)] = [
            (.integer(7), "7"),
            (.number(1.25), "1.25"),
            (.null, "null"),
            (.bool(false), "false"),
            (.string("球场"), "\"球场\""),
            (.array([.integer(1), .null]), "[1,null]"),
            (.object(["z": .integer(1), "a": .bool(true)]), "{\"a\":true,\"z\":1}"),
        ]
        for (value, literal) in fixedCases {
            XCTAssertEqual(try utf8String(CanonicalJSON.data(value)), literal)
        }
    }

    func testCanonicalGoldenBytesMatchFixedUTF8Hex() throws {
        let value: JSONValue = .object([
            "z": .integer(1),
            "a": .string("球场"),
        ])

        XCTAssertEqual(
            lowercaseHex(try CanonicalJSON.data(value)),
            "7b2261223a22e79083e59cba222c227a223a317d"
        )
    }

    func testTypedIDsMatchBothFixedDomainLiterals() throws {
        let value: JSONValue = .object([
            "z": .integer(1),
            "a": .string("球场"),
        ])

        XCTAssertEqual(
            try TypedID.make(domain: "CanonicalFixtureAlpha/v1", value: value),
            "a2fcc54ce2819d6ae58a7f40ffc9d6837ca3104c222eb391c8e7c204282309b3"
        )
        XCTAssertEqual(
            try TypedID.make(domain: "CanonicalFixtureBeta/v1", value: value),
            "f65b7f4bfaf68ad4a2005ebfd6c4a163b351c39fc0c59efb8ec83aace6295b44"
        )
    }

    func testNFCKeysAndValuesAreRequiredForTypedAndGenericInputs() throws {
        XCTAssertEqual(
            try utf8String(
                CanonicalJSON.data(
                    JSONValue.object(["é": .string("café")])
                )
            ),
            #"{"é":"café"}"#
        )

        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.string("e\u{301}"))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(
                JSONValue.object(["e\u{301}": .string("value")])
            )
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(["value": "e\u{301}"])
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(["e\u{301}": "value"])
        )
    }

    func testTypedIDRequiresNonEmptyASCIIDomainWithoutEmbeddedNUL() throws {
        let value = JSONValue.object(["a": .integer(1)])

        XCTAssertThrowsError(try TypedID.make(domain: "", value: value))
        XCTAssertThrowsError(
            try TypedID.make(domain: "Café/v1", value: value)
        )
        XCTAssertThrowsError(
            try TypedID.make(domain: "Cafe\u{301}/v1", value: value)
        )
        XCTAssertThrowsError(
            try TypedID.make(domain: "A\u{0000}B/v1", value: value)
        )
    }

    func testNegativeZeroIsRejectedForTypedAndGenericEncodableInputs() throws {
        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.number(-0.0))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(EncodableDoublePayload(value: -0.0))
        )
        XCTAssertThrowsError(try CanonicalJSON.number(-0.0))
    }

    func testNaNAndBothInfinitiesAreRejectedOnEveryPublicPath() throws {
        for value in [Double.nan, Double.infinity, -Double.infinity] {
            XCTAssertThrowsError(
                try CanonicalJSON.data(JSONValue.number(value)),
                "typed input accepted \(value)"
            )
            XCTAssertThrowsError(
                try CanonicalJSON.data(EncodableDoublePayload(value: value)),
                "generic input accepted \(value)"
            )
            XCTAssertThrowsError(
                try CanonicalJSON.number(value),
                "number serializer accepted \(value)"
            )
        }
    }

    func testSafeIntegerBoundariesAreInclusiveAndOutsideValuesAreRejected() throws {
        let maximum: Int64 = 9_007_199_254_740_991
        let minimum: Int64 = -9_007_199_254_740_991

        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(JSONValue.integer(maximum))),
            "9007199254740991"
        )
        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(JSONValue.integer(minimum))),
            "-9007199254740991"
        )
        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(JSONValue.number(Double(maximum)))),
            "9007199254740991"
        )
        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(JSONValue.number(Double(minimum)))),
            "-9007199254740991"
        )
        XCTAssertEqual(
            try utf8String(
                CanonicalJSON.data(EncodableIntegerPayload(value: maximum))
            ),
            #"{"value":9007199254740991}"#
        )

        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.integer(maximum + 1))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.integer(minimum - 1))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.number(9_007_199_254_740_992.0))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.number(-9_007_199_254_740_992.0))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(
                EncodableIntegerPayload(value: maximum + 1)
            )
        )
    }

    func testNestedObjectsAreOrderedAndStringsUseExactEscapes() throws {
        let value: JSONValue = .object([
            "z": .array([
                .string("line\nquote\"slash\\tab\tcontrol\u{0001}"),
                .bool(false),
            ]),
            "a": .object([
                "y": .integer(2),
                "x": .null,
            ]),
        ])

        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(value)),
            #"{"a":{"x":null,"y":2},"z":["line\nquote\"slash\\tab\tcontrol\u0001",false]}"#
        )
    }

    func testRepeatedCanonicalizationIsByteForByteDeterministic() throws {
        let value: JSONValue = .object([
            "z": .array([.integer(3), .integer(2), .integer(1)]),
            "a": .object(["β": .string("球场"), "alpha": .bool(true)]),
        ])
        let expected = try CanonicalJSON.data(value)

        for _ in 0..<64 {
            XCTAssertEqual(try CanonicalJSON.data(value), expected)
        }
    }

    func testEveryCheckedInRFC8785NumberVectorMatchesExpectedLiteral() throws {
        let vectors = try JSONDecoder().decode(
            [NumberVector].self,
            from: Data(contentsOf: numberVectorURL())
        )
        XCTAssertEqual(vectors.count, 2_048)

        for vector in vectors {
            let bits = try XCTUnwrap(UInt64(vector.bitPatternHex, radix: 16))
            XCTAssertEqual(
                try CanonicalJSON.number(Double(bitPattern: bits)),
                vector.expected,
                vector.bitPatternHex
            )
        }
    }
}
