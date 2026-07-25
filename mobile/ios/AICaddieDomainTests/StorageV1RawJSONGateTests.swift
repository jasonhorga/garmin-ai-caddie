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
        let byteCount = 64
        var original = Data(repeating: 0x20, count: byteCount)
        original[original.startIndex] = 0x30

        let pointer = UnsafeMutableRawPointer.allocate(
            byteCount: byteCount,
            alignment: MemoryLayout<UInt8>.alignment
        )
        defer { pointer.deallocate() }
        _ = pointer.initializeMemory(
            as: UInt8.self,
            repeating: 0x20,
            count: byteCount
        )
        pointer.storeBytes(of: UInt8(0x30), as: UInt8.self)

        let aliased = Data(
            bytesNoCopy: pointer,
            count: byteCount,
            deallocator: .none
        )
        XCTAssertEqual(aliased, original)
        let value = try Gate.validate(aliased)

        pointer.storeBytes(of: UInt8(0x78), as: UInt8.self)

        XCTAssertEqual(aliased.first, UInt8(0x78))
        XCTAssertEqual(value.exactBytes(), original)
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
