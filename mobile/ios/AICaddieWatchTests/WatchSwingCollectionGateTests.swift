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
            + readings(from: 0.9, perHour: 0.12, minutes: 30, offsetMinutes: 31)
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
        readings(from: 0.83, perHour: 0.25, minutes: 60, offsetMinutes: 31).forEach { gate.record($0) }
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

    private func lifecycle(_ dir: URL) -> WatchSwingGateLifecycle {
        WatchSwingGateLifecycle(
            gates: WatchSwingGateStore(fileURL: dir.appendingPathComponent("active-gate.json")),
            reports: WatchRoundBatteryReportStore(fileURL: dir.appendingPathComponent("battery-reports.json"))
        )
    }

    private func tempDir() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("gate-\(UUID().uuidString)", isDirectory: true)
    }

    /// Codex review on #370: the latch and the battery window survive a Watch app relaunch.
    func testAnOverBudgetLatchSurvivesARelaunchWithItsBatteryWindow() throws {
        let dir = tempDir()
        // A baseline round first.
        let before = lifecycle(dir)
        var baselineRound = try XCTUnwrap(before.open(roundId: "r0", at: t0))
        readings(perHour: 0.10, minutes: 60).forEach { baselineRound.record($0) }
        before.close(roundId: "r0", gate: baselineRound, at: t0.addingTimeInterval(3600))

        var gate = try XCTUnwrap(before.open(roundId: "r1", at: t0))
        XCTAssertTrue(gate.allowsCollection(preference: true, capability: capable))
        readings(perHour: 0.30, minutes: 40).forEach { gate.record($0) }
        XCTAssertFalse(gate.allowsCollection(preference: true, capability: capable))
        XCTAssertEqual(gate.latchedBlocker, .batteryOverBudget)
        before.save(gate)

        // The app is terminated and relaunched mid-round: a fresh lifecycle on the same files.
        let after = lifecycle(dir)
        var restored = try XCTUnwrap(after.open(roundId: "r1", at: t0.addingTimeInterval(2500)))
        XCTAssertEqual(restored.latchedBlocker, .batteryOverBudget)
        XCTAssertFalse(restored.allowsCollection(preference: true, capability: capable), "still off after relaunch")
        XCTAssertEqual(restored.startedAt, t0)
        XCTAssertEqual(try XCTUnwrap(restored.report(endedAt: t0.addingTimeInterval(2500)).drainPerHour), 0.30,
                       accuracy: 0.001, "the spent battery window is kept")
    }

    func testACapabilityFailureSurvivesARelaunch() throws {
        let dir = tempDir()
        let before = lifecycle(dir)
        var gate = try XCTUnwrap(before.open(roundId: "r1", at: t0))
        let failed = WatchSwingCapability(sensorsSupported: true, motionPermissionDenied: false, workoutFailed: true)
        XCTAssertFalse(gate.allowsCollection(preference: true, capability: failed))
        before.save(gate)

        var restored = try XCTUnwrap(lifecycle(dir).open(roundId: "r1", at: t0.addingTimeInterval(60)))
        XCTAssertEqual(restored.latchedBlocker, .workoutSessionFailed)
        XCTAssertFalse(restored.allowsCollection(preference: true, capability: capable), "a healthy relaunch does not re-enable it")
    }

    /// A phone Finish keeps the round visible for a deferred upload: the gate still closes, once, and
    /// the next round gets the resulting baseline.
    func testALogicalClosureWritesTheReportOnceAndFeedsTheNextBaseline() throws {
        let dir = tempDir()
        let life = lifecycle(dir)
        var gate = try XCTUnwrap(life.open(roundId: "r1", at: t0))
        readings(perHour: 0.11, minutes: 90).forEach { gate.record($0) }
        life.save(gate)

        XCTAssertTrue(life.close(roundId: "r1", gate: gate, at: t0.addingTimeInterval(5400)))
        XCTAssertFalse(life.close(roundId: "r1", gate: gate, at: t0.addingTimeInterval(5500)), "the deferred-finish completion")
        XCTAssertNil(life.open(roundId: "r1", at: t0.addingTimeInterval(5600)), "the still-visible round gets no new gate")
        XCTAssertEqual(life.reports.load().filter { $0.roundId == "r1" }.count, 1, "written exactly once")

        let next = try XCTUnwrap(life.open(roundId: "r2", at: t0.addingTimeInterval(7200)))
        XCTAssertEqual(try XCTUnwrap(next.baselinePerHour), 0.11, accuracy: 0.001)
    }

    func testAnUnclosedGateOfAnotherRoundIsClosedWhenTheNextRoundOpens() throws {
        let dir = tempDir()
        let life = lifecycle(dir)
        var gate = try XCTUnwrap(life.open(roundId: "r1", at: t0))
        readings(perHour: 0.12, minutes: 30).forEach { gate.record($0) }
        life.save(gate)
        // The app died before r1 closed; the next launch starts r2.
        _ = try XCTUnwrap(lifecycle(dir).open(roundId: "r2", at: t0.addingTimeInterval(9000)))
        XCTAssertEqual(life.reports.load().map(\.roundId), ["r1"])
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
