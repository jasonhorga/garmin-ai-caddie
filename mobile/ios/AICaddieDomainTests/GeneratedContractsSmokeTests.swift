import XCTest
@testable import AICaddieDomain

final class GeneratedContractsSmokeTests: XCTestCase {
    func testGeneratedRegistriesExposeOpenStringsAndTransportLimits() {
        XCTAssertTrue(RoundEventKind.knownValues.isEmpty)
        XCTAssertEqual(ReasonCode.roundBindingMismatch.rawValue, "round_binding_mismatch")
        XCTAssertEqual(RoundTransportLimits.maxEventsPerBatch, 64)
    }
}
