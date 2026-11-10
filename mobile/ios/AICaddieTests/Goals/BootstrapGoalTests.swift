// size: medium
// goals: I-20
//
// I-20: a cold start brings the player straight back to the round they were playing (same hole,
// same scores), and data left behind by an older app version or a damaged file never crashes the
// launch; the app lands in a sane state without destroying recorded holes.

import Foundation
import XCTest
@testable import AICaddie

private let goalBootstrapRoundTimestamp = "2026-09-29T08:00:00Z"

private func goalScoreEvent(
    _ id: String,
    roundId: String,
    hole: Int,
    strokes: Int
) -> LiveRoundEvent {
    LiveRoundEvent(
        eventId: id,
        roundId: roundId,
        timestamp: goalBootstrapRoundTimestamp,
        hole: hole,
        kind: .score,
        payload: ["strokes": .number(Double(strokes))]
    )
}

/// One event line exactly as an older build wrote it: no `clientId`, no `startHole`.
private func goalLegacyEventLine(id: String, roundId: String, hole: Int, strokes: Int) -> String {
    #"{"schema":"ai-caddie-live-round-event-v1","eventId":"\#(id)","roundId":"\#(roundId)","timestamp":"2026-05-01T08:00:00Z","hole":\#(hole),"kind":"score","payload":{"strokes":\#(strokes)}}"#
}

@MainActor
final class BootstrapGoalTests: XCTestCase {
    private var temporaryDirectories: [URL] = []
    private var models: [LiveRoundAppModel] = []

    override func tearDown() async throws {
        for model in models {
            await model.stopRoundBackgroundWorkForTesting()
        }
        models.removeAll()
        for directory in temporaryDirectories {
            try? FileManager.default.removeItem(at: directory)
        }
        temporaryDirectories.removeAll()
        try await super.tearDown()
    }

    private func makeRoot() -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("bootstrap-goal-\(UUID().uuidString)", isDirectory: true)
        temporaryDirectories.append(directory)
        return directory
    }

    /// A cold start: a fresh OfflineStore over the same disk, a fresh app model, the launch-time
    /// session activation and then `bootstrap()`, as the app root does.
    private func coldStart(root: URL, playerId: String) async -> (LiveRoundAppModel, OfflineStore) {
        let store = OfflineStore(directoryURL: root)
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: nil,
            networkPathObserver: nil
        )
        models.append(model)
        model.activateSession(
            AppSession(token: "sess-\(playerId)", playerId: playerId, expiresAt: nil),
            migrateLegacyData: true
        )
        await model.bootstrap()
        return (model, store)
    }

    private func accountStore(root: URL, playerId: String) -> OfflineStore {
        let store = OfflineStore(directoryURL: root)
        store.bindAccount(playerId: playerId, migrateLegacyData: false)
        return store
    }

    // goals: I-20 [main]
    func testColdStartRestoresActiveRound() async throws {
        let root = makeRoot()
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        do {
            // Previous app process: two holes scored, putts on hole 2, the cursor moved on to hole 3.
            let previous = accountStore(root: root, playerId: "p_resume")
            try previous.saveRoundPackage(round)
            try previous.appendEvent(goalScoreEvent("resume-1", roundId: round.roundId, hole: 1, strokes: 4))
            try previous.appendEvent(goalScoreEvent("resume-2", roundId: round.roundId, hole: 2, strokes: 6))
            try previous.appendEvent(LiveRoundEvent(
                eventId: "resume-2-putts",
                roundId: round.roundId,
                timestamp: goalBootstrapRoundTimestamp,
                hole: 2,
                kind: .putt,
                payload: ["putts": .number(2)]
            ))
            try previous.saveActiveHole(roundId: round.roundId, hole: 3)
        }

        let (model, _) = await coldStart(root: root, playerId: "p_resume")

        XCTAssertFalse(model.isBootstrapping)
        let state = try XCTUnwrap(model.liveRoundState, "the in-progress round must be resumed")
        XCTAssertEqual(state.roundId, round.roundId)
        XCTAssertEqual(model.package?.roundId, round.roundId)
        // The player's own stored round is on screen, not a stand-in package with the same id.
        XCTAssertEqual(model.package?.dataMode, "local")
        XCTAssertEqual(model.package?.loopKey, round.loopKey)
        XCTAssertEqual(state.activeHole, 3, "the player lands back on the hole they were on")
        XCTAssertEqual(state.holeState(for: 1)?.score, 4)
        XCTAssertEqual(state.holeState(for: 2)?.score, 6)
        XCTAssertEqual(state.holeState(for: 2)?.putts, 2)
        XCTAssertEqual(Set(state.scoredHoles), [1, 2])
    }

    // goals: I-20
    func testColdStartWithoutRoundLandsIdleWithNoResumedScores() async throws {
        let root = makeRoot()
        let (model, store) = await coldStart(root: root, playerId: "p_idle")

        XCTAssertFalse(model.isBootstrapping)
        XCTAssertEqual(model.liveRoundState?.scoredHoles ?? [], [], "no round means nothing is resumed")
        XCTAssertEqual(model.pendingEventCount, 0)
        let events = try store.loadEvents()
        XCTAssertTrue(events.isEmpty, "an idle launch records nothing")
    }

    // goals: I-20
    func testColdStartMigratesAndResumesRoundWrittenByOlderVersion() async throws {
        let root = makeRoot()
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        // An older build wrote everything at the storage root (no account folder), with event lines
        // that predate `clientId`/`startHole` and no live-progress cursor file.
        try OfflineStore(directoryURL: root).saveRoundPackage(round)
        let legacyLog = [
            goalLegacyEventLine(id: "legacy-1", roundId: round.roundId, hole: 1, strokes: 5),
            goalLegacyEventLine(id: "legacy-2", roundId: round.roundId, hole: 2, strokes: 3),
        ].joined(separator: "\n") + "\n"
        try Data(legacyLog.utf8).write(to: root.appendingPathComponent("events.jsonl"))

        let (model, store) = await coldStart(root: root, playerId: "p_legacy")

        XCTAssertFalse(model.isBootstrapping)
        let state = try XCTUnwrap(model.liveRoundState, "an older version's round must be resumed")
        XCTAssertEqual(state.roundId, round.roundId)
        XCTAssertEqual(model.package?.dataMode, "local")
        XCTAssertEqual(model.package?.loopKey, round.loopKey)
        XCTAssertEqual(state.activeHole, 2, "without a cursor file the last scored hole is current")
        XCTAssertEqual(state.holeState(for: 1)?.score, 5)
        XCTAssertEqual(state.holeState(for: 2)?.score, 3)
        let migrated = try store.loadEvents()
        XCTAssertEqual(migrated.map(\.eventId), ["legacy-1", "legacy-2"])
        XCTAssertTrue(migrated.allSatisfy { $0.startHole == nil })
    }

    // goals: I-20
    func testColdStartAfterTornEventWriteKeepsCompletedHoles() async throws {
        let root = makeRoot()
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let previous = accountStore(root: root, playerId: "p_torn")
        try previous.saveRoundPackage(round)
        try previous.appendEvent(goalScoreEvent("torn-1", roundId: round.roundId, hole: 1, strokes: 5))
        try previous.appendEvent(goalScoreEvent("torn-2", roundId: round.roundId, hole: 2, strokes: 4))
        // The app died mid-append: the last line is an unterminated JSON fragment.
        let logURL = root
            .appendingPathComponent("accounts", isDirectory: true)
            .appendingPathComponent("p_torn", isDirectory: true)
            .appendingPathComponent("events.jsonl")
        let handle = try FileHandle(forWritingTo: logURL)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data(#"{"schema":"ai-caddie-live-round-event-v1","eventId":"torn-3","roundId":"#.utf8))
        try handle.close()

        let (model, _) = await coldStart(root: root, playerId: "p_torn")

        XCTAssertFalse(model.isBootstrapping)
        let state = try XCTUnwrap(model.liveRoundState, "a torn final write must not hide the round")
        XCTAssertEqual(state.roundId, round.roundId)
        XCTAssertEqual(model.package?.dataMode, "local")
        XCTAssertEqual(state.holeState(for: 1)?.score, 5)
        XCTAssertEqual(state.holeState(for: 2)?.score, 4)
        XCTAssertEqual(Set(state.scoredHoles), [1, 2])
    }

    // goals: I-20
    func testColdStartWithCorruptedPackageFilesDoesNotCrashOrLoseScores() async throws {
        let root = makeRoot()
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let previous = accountStore(root: root, playerId: "p_corrupt")
        try previous.saveRoundPackage(round)
        try previous.appendEvent(goalScoreEvent("corrupt-1", roundId: round.roundId, hole: 1, strokes: 7))
        let accountDirectory = root
            .appendingPathComponent("accounts", isDirectory: true)
            .appendingPathComponent("p_corrupt", isDirectory: true)
        // A half-written package: both the per-round file and the current-round pointer.
        let garbage = Data("{\"roundId\": \"\(round.roundId)\", \"holes\": [tru".utf8)
        let corruptedFiles = [
            accountDirectory
                .appendingPathComponent("packages", isDirectory: true)
                .appendingPathComponent("\(round.roundId).json"),
            accountDirectory.appendingPathComponent("current_package.json"),
        ]
        for file in corruptedFiles {
            XCTAssertTrue(FileManager.default.fileExists(atPath: file.path), file.lastPathComponent)
            try garbage.write(to: file)
        }

        let (model, store) = await coldStart(root: root, playerId: "p_corrupt")

        XCTAssertFalse(model.isBootstrapping, "a damaged package must not wedge the launch")
        for file in corruptedFiles {
            XCTAssertNotEqual(
                try? Data(contentsOf: file),
                garbage,
                "\(file.lastPathComponent): damaged bytes are invalidated, not left to break the next launch"
            )
        }
        if let state = model.liveRoundState {
            XCTAssertEqual(model.package?.roundId, state.roundId, "whatever is on screen comes from a readable package")
        }
        XCTAssertEqual(
            try store.loadEvents().filter { $0.roundId == round.roundId }.map(\.eventId),
            ["corrupt-1"],
            "recorded holes stay on disk for a later re-download"
        )
    }

    // goals: I-20
    func testColdStartWithCorruptedEventLogDoesNotCrash() async throws {
        let root = makeRoot()
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let previous = accountStore(root: root, playerId: "p_badlog")
        try previous.saveRoundPackage(round)
        let logURL = root
            .appendingPathComponent("accounts", isDirectory: true)
            .appendingPathComponent("p_badlog", isDirectory: true)
            .appendingPathComponent("events.jsonl")
        let damagedLog = Data((
            goalLegacyEventLine(id: "badlog-1", roundId: round.roundId, hole: 1, strokes: 4)
                + "\n\u{0}\u{0}not json at all\u{0}\n"
                + goalLegacyEventLine(id: "badlog-2", roundId: round.roundId, hole: 2, strokes: 5)
                + "\n"
        ).utf8)
        try damagedLog.write(to: logURL)

        let (model, _) = await coldStart(root: root, playerId: "p_badlog")

        XCTAssertFalse(model.isBootstrapping, "a damaged event log must not wedge the launch")
        XCTAssertEqual(model.pendingEventCount, 0)
        XCTAssertEqual(
            try Data(contentsOf: logURL),
            damagedLog,
            "the damaged log is kept as-is, never truncated or rewritten during launch"
        )
    }
}
