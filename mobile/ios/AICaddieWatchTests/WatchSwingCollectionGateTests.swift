import XCTest
@testable import AICaddieWatch

/// B7 capability and battery gate (IMPLEMENTATION_PLAN B7 "能力 / 电量门槛").
final class WatchSwingCollectionGateTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 1_790_000_000)
    private let capable = WatchSwingCapability(sensorsSupported: true, motionPermissionDenied: false, workoutFailed: false)

    /// One reading a minute for `minutes`, draining `perHour` (fraction per hour) from `start`.
    private func readings(from start: Double = 0.9, perHour: Double, minutes: Int, charging: Bool = false,
                          offsetMinutes: Int = 0) -> [WatchBatterySample] {
        (0...minutes).map { minute in
            WatchBatterySample(
                at: t0.addingTimeInterval(Double(offsetMinutes + minute) * 60),
                level: start - perHour * Double(minute) / 60,
                charging: charging
            )
        }
    }

    private func reportStore() -> WatchRoundBatteryReportStore {
        WatchRoundBatteryReportStore(fileURL: FileManager.default.temporaryDirectory
            .appendingPathComponent("battery-\(UUID().uuidString).json"))
    }

    func testDrainIsMeasuredOnlyOverEnoughUnchargedTime() throws {
        XCTAssertNil(WatchBatteryBudget.drainPerHour(readings(perHour: 0.12, minutes: 10)), "too short to judge")
        let drain = try XCTUnwrap(WatchBatteryBudget.drainPerHour(readings(perHour: 0.12, minutes: 40)))
        XCTAssertEqual(drain, 0.12, accuracy: 0.001)
        let charging = readings(perHour: -0.3, minutes: 30, charging: true)
            + readings(start: 0.9, perHour: 0.12, minutes: 30, offsetMinutes: 31)
        XCTAssertEqual(try XCTUnwrap(WatchBatteryBudget.drainPerHour(charging)), 0.12, accuracy: 0.001,
                       "charging time never counts")
    }

    func testCollectionStopsForTheRoundOnceItsDrainExceedsTheBaselineByFivePercentAnHour() {
        var gate = WatchSwingCollectionGate(roundId: "r1", startedAt: t0, baselinePerHour: 0.10)
        XCTAssertTrue(gate.allowsCollection(preference: true, capability: capable))
        // 14 %/h is within 10 % + 5 %.
        readings(perHour: 0.14, minutes: 30).forEach { gate.record($0) }
        XCTAssertTrue(gate.allowsCollection(preference: true, capability: capable))
        // Then it drains at 25 %/h: over budget, and off for the rest of the round.
        readings(start: 0.83, perHour: 0.25, minutes: 60, offsetMinutes: 31).forEach { gate.record($0) }
        XCTAssertFalse(gate.allowsCollection(preference: true, capability: capable))
        XCTAssertEqual(gate.latchedBlocker, .batteryOverBudget)
        XCTAssertFalse(gate.allowsCollection(preference: true, capability: capable), "latched")
        let report = gate.report(endedAt: t0.addingTimeInterval(5400))
        XCTAssertTrue(report.collecting)
        XCTAssertEqual(report.disabledReason, .batteryOverBudget)
    }

    func testWithoutABaselineCollectionStaysOffAndThatRoundBecomesTheBaseline() throws {
        let store = reportStore()
        XCTAssertNil(store.baselinePerHour())
        var first = WatchSwingCollectionGate(roundId: "r1", startedAt: t0, baselinePerHour: store.baselinePerHour())
        XCTAssertFalse(first.allowsCollection(preference: true, capability: capable))
        XCTAssertEqual(first.latchedBlocker, .noBatteryBaseline)
        readings(perHour: 0.11, minutes: 90).forEach { first.record($0) }
        store.append(first.report(endedAt: t0.addingTimeInterval(5400)))

        let baseline = try XCTUnwrap(store.baselinePerHour(), "a round that did not collect measures the baseline")
        XCTAssertEqual(baseline, 0.11, accuracy: 0.001)
        var second = WatchSwingCollectionGate(roundId: "r2", startedAt: t0, baselinePerHour: baseline)
        XCTAssertTrue(second.allowsCollection(preference: true, capability: capable))
        readings(perHour: 0.30, minutes: 60).forEach { second.record($0) }
        _ = second.allowsCollection(preference: true, capability: capable)
        store.append(second.report(endedAt: t0.addingTimeInterval(3600)))
        XCTAssertEqual(try XCTUnwrap(store.baselinePerHour()), 0.11, accuracy: 0.001,
                       "a collecting round never moves the baseline")
    }

    func testCapabilityFailuresTurnCollectionOffForTheRound() {
        let cases: [(WatchSwingCapability, WatchSwingGateBlocker)] = [
            (.init(sensorsSupported: false, motionPermissionDenied: false, workoutFailed: false), .unsupportedDevice),
            (.init(sensorsSupported: true, motionPermissionDenied: true, workoutFailed: false), .motionPermissionDenied),
            (.init(sensorsSupported: true, motionPermissionDenied: false, workoutFailed: true), .workoutSessionFailed),
        ]
        for (capability, blocker) in cases {
            var gate = WatchSwingCollectionGate(roundId: "r1", startedAt: t0, baselinePerHour: 0.1)
            XCTAssertFalse(gate.allowsCollection(preference: true, capability: capability))
            XCTAssertEqual(gate.latchedBlocker, blocker)
            XCTAssertFalse(gate.allowsCollection(preference: true, capability: capable), "\(blocker) holds for the round")
        }
        XCTAssertFalse(WatchSwingCollectionGate(roundId: "r1", startedAt: t0, baselinePerHour: 0.1)
            .allowsCollectionWithoutPreference(capability: capable))
    }

    func testTheProviderStateMapsWithoutFlappingWhileTheSessionStarts() {
        for state in [WatchAutoShotRuntimeState.off, .requestingAuthorization, .starting, .active] {
            XCTAssertFalse(WatchSwingCapability(provider: state, sensorsSupported: true, motionPermissionDenied: false).workoutFailed,
                           "\(state) is not a failure")
        }
        XCTAssertTrue(WatchSwingCapability(provider: .failed, sensorsSupported: true, motionPermissionDenied: false).workoutFailed)
        XCTAssertFalse(WatchSwingCapability(provider: .unsupported, sensorsSupported: true, motionPermissionDenied: false).sensorsSupported)
    }

    func testTheSettingsStatusExplainsTheGate() {
        XCTAssertEqual(WatchSwingCollectionStatus.text(preference: true, roundActive: true, blocker: .noBatteryBaseline),
                       "先打一场不采集的球，测出耗电基准")
        XCTAssertEqual(WatchSwingCollectionStatus.text(preference: true, roundActive: true, blocker: nil), "采集中")
        XCTAssertEqual(WatchSwingCollectionStatus.text(preference: true, roundActive: false, blocker: nil), "下一场开始后采集")
        XCTAssertTrue(WatchSwingCollectionStatus.text(preference: false, roundActive: true, blocker: nil).hasPrefix("关闭"))
    }
}

private extension WatchSwingCollectionGate {
    func allowsCollectionWithoutPreference(capability: WatchSwingCapability) -> Bool {
        var copy = self
        return copy.allowsCollection(preference: false, capability: capability)
    }
}
