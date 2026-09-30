@testable import AICaddie
import XCTest

/// B4b-2 acceptance: an 18-hole course played as two halves in any order. The oracle is the real
/// server route's output (`Fixtures/b4b2_server_loop_tables.json`, kept in lock-step with the
/// server by `tests/test_b4b2_loop_tables_fixture.py`): local projection and turn composition
/// must reproduce its `number → (sourceGlobalId, sourceLocalHole, courseHoleNumber)` tables.
final class RoundLoopCompositionTests: XCTestCase {
    private struct Row: Decodable, Equatable {
        let number: Int
        let sourceGlobalId: Int
        let sourceLocalHole: Int
        let courseHoleNumber: Int
        let par: Int
    }

    private struct Table: Decodable {
        let roundLoops: [RoundLoop]
        let holes: [Row]
    }

    private struct Oracle: Decodable {
        let globalId: Int
        let wholeCourseTemplate: LiveRoundPackage
        let frontHalf: LiveRoundPackage
        let backHalf: LiveRoundPackage
        let tables: [String: Table]
    }

    private func oracle() throws -> Oracle {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: RoundLoopCompositionTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "b4b2_server_loop_tables", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "b4b2_server_loop_tables", withExtension: "json")
        )
        return try JSONDecoder().decode(Oracle.self, from: Data(contentsOf: url))
    }

    private func rows(_ package: LiveRoundPackage) -> [Row] {
        package.holes.sorted { $0.number < $1.number }.map {
            Row(
                number: $0.number,
                sourceGlobalId: $0.sourceGlobalId,
                sourceLocalHole: $0.sourceLocalHole,
                courseHoleNumber: $0.courseHoleNumber,
                par: $0.par
            )
        }
    }

    private func assertMatches(
        _ package: LiveRoundPackage?,
        _ table: Table?,
        loopKey: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let package = try XCTUnwrap(package, "no package for \(loopKey)", file: file, line: line)
        let table = try XCTUnwrap(table, "no server table for \(loopKey)", file: file, line: line)
        XCTAssertEqual(package.loopKey, loopKey, file: file, line: line)
        XCTAssertEqual(package.roundLoops, table.roundLoops, loopKey, file: file, line: line)
        XCTAssertEqual(rows(package), table.holes, loopKey, file: file, line: line)
        // Round-indexed facts follow the round number, never the physical hole.
        XCTAssertEqual(
            package.caddieContextSeeds.map(\.hole),
            package.holes.map(\.number).sorted(),
            loopKey,
            file: file,
            line: line
        )
        XCTAssertTrue(
            package.caddieContextSeeds.allSatisfy { $0.sourceRef == "\(package.roundId):\($0.hole)" },
            loopKey,
            file: file,
            line: line
        )
    }

    func testServerPackagesDecodeAsStrictV2() throws {
        let oracle = try oracle()
        let template = oracle.wholeCourseTemplate
        XCTAssertEqual(template.schema, LiveRoundPackage.supportedSchema)
        XCTAssertTrue(template.isWholeCourseTemplate)
        XCTAssertEqual(template.loopKey, "\(oracle.globalId):front+\(oracle.globalId):back")
        XCTAssertEqual(oracle.backHalf.loopEntries, [RoundLoopEntry(globalId: oracle.globalId, half: "back")])
        XCTAssertFalse(oracle.backHalf.isWholeCourseTemplate)
        XCTAssertNil(oracle.backHalf.wholeCourseTemplate(), "one half never becomes a template")
    }

    func testOfflineProjectionOfEveryOrderEqualsTheServerTable() throws {
        let oracle = try oracle()
        XCTAssertEqual(oracle.tables.count, 6)
        for (loopKey, table) in oracle.tables {
            let entries = try XCTUnwrap(RoundLoopEntry.entries(loopKey: loopKey))
            let projected = LiveRoundPackage.projecting(
                entries,
                templates: [oracle.globalId: oracle.wholeCourseTemplate],
                roundId: "offline-\(loopKey)"
            )
            try assertMatches(projected, table, loopKey: loopKey)
        }
    }

    /// The turn: each one-half start composes either half as its second loop — the opposite half
    /// and the same half — from the installed template, equal to the server's two-loop table.
    func testTurnCompositionFromEitherHalfEqualsTheServerTable() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        for first in [oracle.frontHalf, oracle.backHalf] {
            for half in ["front", "back"] {
                let entry = RoundLoopEntry(globalId: gid, half: half)
                let composed = first.composingSecondLoop(
                    entry,
                    from: oracle.wholeCourseTemplate,
                    roundId: first.roundId
                )
                let loopKey = first.loopKey + "+\(gid):\(half)"
                try assertMatches(composed, oracle.tables[loopKey], loopKey: loopKey)
            }
        }
    }

    /// 后→前 specifically: round hole 10 is course hole 1 and is shown as 第 1 洞; round hole 1
    /// is course hole 10.
    func testBackThenFrontNumbersRoundHolesInPlayOrder() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let round = try XCTUnwrap(oracle.backHalf.composingSecondLoop(
            RoundLoopEntry(globalId: gid, half: "front"),
            from: oracle.wholeCourseTemplate,
            roundId: oracle.backHalf.roundId
        ))
        XCTAssertEqual(round.courseHoleNumber(forRoundHole: 1), 10)
        XCTAssertEqual(round.courseHoleNumber(forRoundHole: 10), 1)
        XCTAssertEqual(round.secondLoop?.roundStartHole, 10)
        XCTAssertEqual(round.secondLoop?.sourceStartHole, 1)
        XCTAssertEqual(round.loop(containingRoundHole: 18)?.half, "front")
    }

    func testRemovingTheSecondLoopRestoresTheFirstHalfTable() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let round = try XCTUnwrap(oracle.backHalf.composingSecondLoop(
            RoundLoopEntry(globalId: gid, half: "back"),
            from: oracle.wholeCourseTemplate,
            roundId: oracle.backHalf.roundId
        ))
        let trimmed = round.removingSecondLoop()
        try assertMatches(trimmed, oracle.tables["\(gid):back"], loopKey: "\(gid):back")
    }

    /// A round played 后→前 carries the whole physical course, so it re-projects into the
    /// canonical template (the offline store keys templates by that canonical loop key).
    func testAnyWholeRoundReprojectsIntoTheCanonicalTemplate() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let backFront = try XCTUnwrap(LiveRoundPackage.projecting(
            [RoundLoopEntry(globalId: gid, half: "back"), RoundLoopEntry(globalId: gid, half: "front")],
            templates: [gid: oracle.wholeCourseTemplate],
            roundId: "played-back-front"
        ))
        let canonical = try XCTUnwrap(backFront.wholeCourseTemplate())
        try assertMatches(canonical, oracle.tables["\(gid):front+\(gid):back"], loopKey: "\(gid):front+\(gid):back")
        let sameHalfTwice = try XCTUnwrap(LiveRoundPackage.projecting(
            [RoundLoopEntry(globalId: gid, half: "back"), RoundLoopEntry(globalId: gid, half: "back")],
            templates: [gid: oracle.wholeCourseTemplate],
            roundId: "played-back-back"
        ))
        XCTAssertNil(sameHalfTwice.wholeCourseTemplate(), "后→后 never saw the front nine")
    }

    /// The four orders stay distinct identities everywhere they are keyed.
    func testTheFourOrdersHaveDistinctLoopKeysAndHoleSets() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let orders = [("front", "back"), ("front", "front"), ("back", "front"), ("back", "back")]
        let packages = try orders.map { first, second in
            try XCTUnwrap(LiveRoundPackage.projecting(
                [RoundLoopEntry(globalId: gid, half: first), RoundLoopEntry(globalId: gid, half: second)],
                templates: [gid: oracle.wholeCourseTemplate],
                roundId: "same-round"
            ))
        }
        XCTAssertEqual(Set(packages.map(\.loopKey)).count, 4)
        XCTAssertEqual(Set(packages.map(\.holeSetIdentity)).count, 4)
    }

    /// README §8 lock: the second loop changes freely until anything is recorded on its first
    /// round hole, and is locked from then on — including 后→前, whose round hole 10 is course hole 1.
    func testSecondLoopLockUsesTheRoundHoleForEveryOrder() throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        for (first, second) in [("front", "back"), ("back", "front"), ("back", "back"), ("front", "front")] {
            let firstHalf = first == "front" ? oracle.frontHalf : oracle.backHalf
            let round = try XCTUnwrap(firstHalf.composingSecondLoop(
                RoundLoopEntry(globalId: gid, half: second),
                from: oracle.wholeCourseTemplate,
                roundId: firstHalf.roundId
            ))
            func event(_ hole: Int, roundId: String? = nil) -> LiveRoundEvent {
                LiveRoundEvent(
                    eventId: "e-\(hole)-\(roundId ?? round.roundId)",
                    roundId: roundId ?? round.roundId,
                    timestamp: "2026-09-29T08:00:00Z",
                    hole: hole,
                    kind: .score,
                    payload: ["score": .number(4)]
                )
            }
            let firstNine = (1...9).map { event($0) }
            XCTAssertFalse(round.isSecondLoopLocked(by: firstNine), "\(first)→\(second) before hole 10")
            XCTAssertFalse(
                round.isSecondLoopLocked(by: firstNine + [event(10, roundId: "another-round")]),
                "another round's hole 10 never locks this one"
            )
            XCTAssertTrue(round.isSecondLoopLocked(by: firstNine + [event(10)]), "\(first)→\(second) after hole 10")
        }
        XCTAssertFalse(oracle.backHalf.isSecondLoopLocked(by: []), "a one-loop round has nothing to lock")
    }
}
