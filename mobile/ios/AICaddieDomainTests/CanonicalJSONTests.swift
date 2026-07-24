import Foundation
import XCTest
@testable import AICaddieDomain
@testable import SwiftJCS

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

private struct EncodableCanonicalFixture: Encodable {
    let z: Int64
    let a: String
}

private struct EncodableOracleNested: Encodable {
    let escaped: String
}

private struct EncodableCanonicalOracle: Encodable {
    let exponent: Double
    let subnormal: Double
    let maximumSafeInteger: Double
    let minimumSafeInteger: Double
    let nested: EncodableOracleNested
}

private struct RecursiveGenericNode<Value: Encodable>: Encodable {
    let inner: Value
}

private struct RecursiveGenericPayload<Value: Encodable>: Encodable {
    let outer: [RecursiveGenericNode<Value>]

    init(_ value: Value) {
        outer = [RecursiveGenericNode(inner: value)]
    }
}

final class CanonicalJSONTests: XCTestCase {
    private func utf8String(_ data: Data) throws -> String {
        try XCTUnwrap(String(data: data, encoding: .utf8))
    }

    private func lowercaseHex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    private func assertTypedInputIsRejected(
        _ value: JSONValue,
        _ label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try CanonicalJSON.data(value),
            "data accepted nested \(label)",
            file: file,
            line: line
        )
        XCTAssertThrowsError(
            try TypedID.make(domain: "RecursiveValidation/v1", value: value),
            "TypedID accepted nested \(label)",
            file: file,
            line: line
        )
    }

    private func assertGenericInputIsRejected<Value: Encodable>(
        _ value: Value,
        _ label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try CanonicalJSON.data(value),
            "generic data accepted nested \(label)",
            file: file,
            line: line
        )
        XCTAssertThrowsError(
            try TypedID.make(domain: "RecursiveValidation/v1", value: value),
            "generic TypedID accepted nested \(label)",
            file: file,
            line: line
        )
    }

    private func assertCanonicalPathsRejectNegativeZero(
        _ value: JSONValue,
        _ label: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try CanonicalJSON.data(value),
            "CanonicalJSON accepted \(label)",
            file: file,
            line: line
        ) { error in
            XCTAssertEqual(
                error as? CanonicalJSONError,
                .negativeZero,
                file: file,
                line: line
            )
        }
        XCTAssertThrowsError(
            try TypedID.make(domain: "RawNegativeZero/v1", value: value),
            "TypedID accepted \(label)",
            file: file,
            line: line
        ) { error in
            XCTAssertEqual(
                error as? CanonicalJSONError,
                .negativeZero,
                file: file,
                line: line
            )
        }
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
        XCTAssertNotEqual(JSONValue.integer(1), JSONValue.number(1.0))

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
        let generic = EncodableCanonicalFixture(z: 1, a: "球场")

        XCTAssertEqual(
            lowercaseHex(try CanonicalJSON.data(value)),
            "7b2261223a22e79083e59cba222c227a223a317d"
        )
        XCTAssertEqual(
            lowercaseHex(try CanonicalJSON.data(generic)),
            "7b2261223a22e79083e59cba222c227a223a317d"
        )
    }

    func testTypedIDsMatchBothFixedDomainLiterals() throws {
        let value: JSONValue = .object([
            "z": .integer(1),
            "a": .string("球场"),
        ])
        let generic = EncodableCanonicalFixture(z: 1, a: "球场")

        XCTAssertEqual(
            try TypedID.make(domain: "CanonicalFixtureAlpha/v1", value: value),
            "a2fcc54ce2819d6ae58a7f40ffc9d6837ca3104c222eb391c8e7c204282309b3"
        )
        XCTAssertEqual(
            try TypedID.make(domain: "CanonicalFixtureBeta/v1", value: value),
            "f65b7f4bfaf68ad4a2005ebfd6c4a163b351c39fc0c59efb8ec83aace6295b44"
        )
        XCTAssertEqual(
            try TypedID.make(
                domain: "CanonicalFixtureAlpha/v1",
                value: generic
            ),
            "a2fcc54ce2819d6ae58a7f40ffc9d6837ca3104c222eb391c8e7c204282309b3"
        )
        XCTAssertEqual(
            try TypedID.make(
                domain: "CanonicalFixtureBeta/v1",
                value: generic
            ),
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
        let generic = EncodableCanonicalFixture(z: 1, a: "球场")

        for domain in ["", "Café/v1", "Cafe\u{301}/v1", "A\u{0000}B/v1"] {
            XCTAssertThrowsError(
                try TypedID.make(domain: domain, value: value),
                "JSONValue overload accepted domain \(domain.debugDescription)"
            )
            XCTAssertThrowsError(
                try TypedID.make(domain: domain, value: generic),
                "generic overload accepted domain \(domain.debugDescription)"
            )
        }
    }

    func testNegativeZeroIsRejectedForTypedAndGenericEncodableInputs() throws {
        XCTAssertThrowsError(
            try CanonicalJSON.data(JSONValue.number(-0.0))
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(EncodableDoublePayload(value: -0.0))
        )
    }

    func testRawTopLevelNegativeZeroPreservesSignForPublicRejection() throws {
        for literal in ["-0", "-0.0"] {
            let decoded = try JSONDecoder().decode(
                JSONValue.self,
                from: Data(literal.utf8)
            )
            if case .number(let number) = decoded {
                XCTAssertTrue(number.isZero, literal)
                XCTAssertEqual(number.sign, .minus, literal)
            } else {
                XCTFail("\(literal) decoded without its negative-zero sign: \(decoded)")
            }
            assertCanonicalPathsRejectNegativeZero(
                decoded,
                "top-level raw \(literal)"
            )
        }
    }

    func testRawNestedNegativeZeroPreservesSignForPublicRejection() throws {
        for literal in ["-0", "-0.0"] {
            let source = Data(
                #"{"outer":[{"inner":\#(literal)}]}"#.utf8
            )
            let decoded = try JSONDecoder().decode(JSONValue.self, from: source)

            if case .object(let root) = decoded,
               case .array(let outer)? = root["outer"],
               case .object(let nested)? = outer.first,
               case .number(let number)? = nested["inner"] {
                XCTAssertTrue(number.isZero, literal)
                XCTAssertEqual(number.sign, .minus, literal)
            } else {
                XCTFail("nested \(literal) decoded without its negative-zero sign: \(decoded)")
            }
            assertCanonicalPathsRejectNegativeZero(
                decoded,
                "recursively nested raw \(literal)"
            )
        }
    }

    func testRawPositiveZeroControlsRemainAcceptedAndKeepNumberCasesDistinct() throws {
        let integerZero = try JSONDecoder().decode(
            JSONValue.self,
            from: Data("0".utf8)
        )
        let decimalZero = try JSONDecoder().decode(
            JSONValue.self,
            from: Data("0.0".utf8)
        )
        let fractionalNumber = try JSONDecoder().decode(
            JSONValue.self,
            from: Data("0.5".utf8)
        )

        XCTAssertEqual(integerZero, .integer(0))
        XCTAssertEqual(fractionalNumber, .number(0.5))
        XCTAssertNotEqual(JSONValue.integer(0), JSONValue.number(0.0))
        XCTAssertEqual(try utf8String(CanonicalJSON.data(integerZero)), "0")
        XCTAssertEqual(try utf8String(CanonicalJSON.data(decimalZero)), "0")
        XCTAssertNoThrow(
            try TypedID.make(domain: "RawPositiveZero/v1", value: integerZero)
        )
        XCTAssertNoThrow(
            try TypedID.make(domain: "RawPositiveZero/v1", value: decimalZero)
        )
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
        }
    }

    func testTypedAndGenericPathsMatchExactRepresentativeOracle() throws {
        let escaped = "line\nquote\"slash\\control\u{0001}"
        let typed: JSONValue = .object([
            "exponent": .number(1e-7),
            "subnormal": .number(Double(bitPattern: 1)),
            "maximumSafeInteger": .number(9_007_199_254_740_991.0),
            "minimumSafeInteger": .number(-9_007_199_254_740_991.0),
            "nested": .object(["escaped": .string(escaped)]),
        ])
        let generic = EncodableCanonicalOracle(
            exponent: 1e-7,
            subnormal: Double(bitPattern: 1),
            maximumSafeInteger: 9_007_199_254_740_991.0,
            minimumSafeInteger: -9_007_199_254_740_991.0,
            nested: EncodableOracleNested(escaped: escaped)
        )
        let expected = #"{"exponent":1e-7,"maximumSafeInteger":9007199254740991,"minimumSafeInteger":-9007199254740991,"nested":{"escaped":"line\nquote\"slash\\control\u0001"},"subnormal":5e-324}"#

        XCTAssertEqual(try utf8String(CanonicalJSON.data(typed)), expected)
        XCTAssertEqual(try utf8String(CanonicalJSON.data(generic)), expected)
    }

    func testRecursiveValidationPropagatesThroughDataAndTypedIDOverloads() {
        let typedInvalidValues: [(String, JSONValue)] = [
            ("non-NFC string", .string("e\u{301}")),
            ("non-NFC key", .object(["e\u{301}": .null])),
            ("negative zero", .number(-0.0)),
            ("non-finite number", .number(.infinity)),
            ("unsafe integer", .integer(9_007_199_254_740_992)),
            ("unsafe integral number", .number(9_007_199_254_740_992.0)),
        ]
        for (label, invalid) in typedInvalidValues {
            assertTypedInputIsRejected(
                .object([
                    "outer": .array([
                        .object(["inner": invalid]),
                    ]),
                ]),
                label
            )
        }

        assertGenericInputIsRejected(
            RecursiveGenericPayload("e\u{301}"),
            "non-NFC string"
        )
        assertGenericInputIsRejected(
            RecursiveGenericPayload(["e\u{301}": "value"]),
            "non-NFC key"
        )
        assertGenericInputIsRejected(
            RecursiveGenericPayload(-0.0),
            "negative zero"
        )
        assertGenericInputIsRejected(
            RecursiveGenericPayload(Double.nan),
            "non-finite number"
        )
        assertGenericInputIsRejected(
            RecursiveGenericPayload(Int64(9_007_199_254_740_992)),
            "unsafe integer"
        )
        assertGenericInputIsRejected(
            RecursiveGenericPayload(9_007_199_254_740_992.0),
            "unsafe integral number"
        )
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
        XCTAssertEqual(
            try utf8String(
                CanonicalJSON.data(EncodableIntegerPayload(value: minimum))
            ),
            #"{"value":-9007199254740991}"#
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
        XCTAssertThrowsError(
            try CanonicalJSON.data(
                EncodableIntegerPayload(value: minimum - 1)
            )
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(
                EncodableDoublePayload(value: 9_007_199_254_740_992.0)
            )
        )
        XCTAssertThrowsError(
            try CanonicalJSON.data(
                EncodableDoublePayload(value: -9_007_199_254_740_992.0)
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

    func testObjectPropertiesUseUTF16CodeUnitOrdering() throws {
        let value: JSONValue = .object([
            "\u{E000}": .integer(2),
            "\u{1F600}": .integer(1),
        ])
        let generic: [String: Int64] = [
            "\u{E000}": 2,
            "\u{1F600}": 1,
        ]

        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(value)),
            "{\"\u{1F600}\":1,\"\u{E000}\":2}"
        )
        XCTAssertEqual(
            try utf8String(CanonicalJSON.data(generic)),
            "{\"\u{1F600}\":1,\"\u{E000}\":2}"
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

    func testPinnedVendorRawNumberSmokeOracle() throws {
        let cases: [(UInt64, String)] = [
            (0x0000000000000001, "5e-324"),
            (0x4340000000000000, "9007199254740992"),
        ]

        for (bits, expected) in cases {
            XCTAssertEqual(
                try _serializeNumber(Double(bitPattern: bits)),
                expected,
                String(format: "%016llx", bits)
            )
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
                try _serializeNumber(Double(bitPattern: bits)),
                vector.expected,
                vector.bitPatternHex
            )
        }
    }
}
