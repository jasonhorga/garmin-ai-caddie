import CoreLocation
import XCTest
@testable import AICaddie

final class LiveRoundEventBuilderTests: XCTestCase {
    private func makeBuilder() -> LiveRoundEventBuilder {
        var counter = 0
        return LiveRoundEventBuilder(
            roundId: "round-1",
            idFactory: {
                counter += 1
                return "evt-\(counter)"
            },
            now: { Date(timeIntervalSince1970: 0) }
        )
    }

    func testScoreEventCarriesRoundIdHoleAndStrokes() {
        let event = makeBuilder().makeScoreEvent(hole: 7, strokes: 5)
        XCTAssertEqual(event.roundId, "round-1")
        XCTAssertEqual(event.hole, 7)
        XCTAssertEqual(event.kind, .score)
        XCTAssertEqual(event.eventId, "evt-1")
        XCTAssertEqual(event.payload["strokes"], .number(5))
    }

    func testPuttAndPenaltyEvents() {
        let builder = makeBuilder()
        XCTAssertEqual(builder.makePuttEvent(hole: 3, putts: 2).payload["putts"], .number(2))
        XCTAssertEqual(builder.makePenaltyEvent(hole: 3, penalties: 1).payload["penalties"], .number(1))
    }

    func testClubEventIncludesOptionalContext() {
        let event = makeBuilder().makeClubEvent(
            hole: 1,
            clubName: "7i",
            shotType: "approach",
            strategyMode: "stock",
            lie: "fairway",
            distanceToPinM: 150
        )
        XCTAssertEqual(event.kind, .club)
        XCTAssertEqual(event.payload["clubName"], .string("7i"))
        XCTAssertEqual(event.payload["shotType"], .string("approach"))
        XCTAssertEqual(event.payload["strategyMode"], .string("stock"))
        XCTAssertEqual(event.payload["lie"], .string("fairway"))
        XCTAssertEqual(event.payload["distanceToPinM"], .number(150))
    }

    func testClubEventOmitsUnsetContextButKeepsNullableNumbers() {
        let event = makeBuilder().makeClubEvent(hole: 1, clubName: "PW")
        XCTAssertEqual(event.payload["clubName"], .string("PW"))
        XCTAssertNil(event.payload["shotType"])
        XCTAssertEqual(event.payload["distanceToPinM"], .null)
    }

    func testActualFirstShotReferencesSavedLocationAndUsesTeeFacts() {
        let event = makeBuilder().makeActualClubEvent(
            hole: 1,
            clubName: "3W",
            sourceLocationEventId: "location-1",
            shotOrder: 1,
            shotType: "approach",
            strategyMode: "stock",
            lie: "fairway"
        )

        XCTAssertEqual(event.kind, .club)
        XCTAssertEqual(event.payload["clubName"], .string("3W"))
        XCTAssertEqual(event.payload["shotType"], .string("tee"))
        XCTAssertEqual(event.payload["lie"], .string("tee"))
        XCTAssertEqual(
            event.payload["actualShot"],
            .object([
                "sourceLocationEventId": .string("location-1"),
                "shotOrder": .number(1),
                "clubName": .string("3W"),
                "shotType": .string("tee"),
                "lie": .string("tee"),
            ])
        )
    }

    func testActualLaterShotKeepsSelectedShotTypeAndLie() {
        let event = makeBuilder().makeActualClubEvent(
            hole: 4,
            clubName: "8I",
            sourceLocationEventId: "location-2",
            shotOrder: 2,
            shotType: "recovery",
            lie: "rough"
        )

        XCTAssertEqual(event.payload["shotType"], .string("recovery"))
        XCTAssertEqual(event.payload["lie"], .string("rough"))
        guard case .object(let actualShot) = event.payload["actualShot"] else {
            return XCTFail("actual club event must carry source-linked shot facts")
        }
        XCTAssertEqual(actualShot["sourceLocationEventId"], .string("location-2"))
        XCTAssertEqual(actualShot["shotOrder"], .number(2))
    }

    func testActualClubEventReferencesLargeOnlineDecisionWithoutEmbeddingIt() throws {
        let decision = makeLargeDecision(confidenceSource: "live_decision")
        XCTAssertGreaterThan(try JSONEncoder().encode(decision).count, 1_000_000)

        let event = makeBuilder().makeActualClubEvent(
            hole: 4,
            clubName: "8I",
            sourceLocationEventId: "location-online",
            shotOrder: 2,
            shotType: "approach",
            lie: "fairway",
            decision: decision
        )

        XCTAssertEqual(event.payload["decisionId"], .string("online-decision-4"))
        XCTAssertNil(event.payload["decision"], "online decisions are authoritative in the server ledger")
        XCTAssertNotNil(event.payload["actualShot"])
        XCTAssertLessThan(
            try JSONEncoder().encode(event).count,
            2_048,
            "an actual club event must not duplicate a megabyte online decision"
        )
    }

    func testActualClubEventEmbedsOnlyCompactOfflineAuditSnapshot() throws {
        let decision = makeLargeDecision(confidenceSource: "offline_package_seed")
        let event = makeBuilder().makeActualClubEvent(
            hole: 4,
            clubName: "8I",
            sourceLocationEventId: "location-offline",
            shotOrder: 2,
            shotType: "approach",
            lie: "rough",
            decision: decision
        )

        guard case .object(let snapshot) = event.payload["decision"] else {
            return XCTFail("offline decisions need an embedded audit snapshot")
        }
        XCTAssertEqual(snapshot["schema"], .string("ai-caddie-decision-audit-snapshot-v1"))
        XCTAssertEqual(snapshot["decisionId"], .string("online-decision-4"))
        XCTAssertEqual(snapshot["selectedOptionId"], .string("stock"))
        XCTAssertEqual(snapshot["evidenceRefs"], .array([.string("round-1:4")]))
        guard case .object(let context) = snapshot["context"] else {
            return XCTFail("offline snapshot needs source identity context")
        }
        XCTAssertEqual(context["globalId"], .number(31_676))
        XCTAssertNil(context["geometry"])
        guard case .object(let selected) = snapshot["selectedOption"] else {
            return XCTFail("offline snapshot needs the selected option")
        }
        XCTAssertEqual(selected["carry_m"], .number(145))
        XCTAssertNil(selected["historyAdjustment"])
        XCTAssertNil(snapshot["selected"])
        XCTAssertNil(snapshot["evidence"])
        XCTAssertNil(snapshot["sequences"])
        XCTAssertNotNil(event.payload["actualShot"])
        XCTAssertLessThan(
            try JSONEncoder().encode(event).count,
            8_192,
            "offline auditability must not reintroduce the full decision payload"
        )
    }

    func testLocationEventCarriesCoordinateAccuracyAndTarget() {
        let event = makeBuilder().makeLocationEvent(
            hole: 4,
            coordinate: CLLocationCoordinate2D(latitude: 39.9, longitude: 116.4),
            horizontalAccuracyM: 5,
            targetCoordinate: CLLocationCoordinate2D(latitude: 39.91, longitude: 116.41),
            targetKind: "pin"
        )
        XCTAssertEqual(event.kind, .location)
        XCTAssertEqual(event.payload["latitude"], .number(39.9))
        XCTAssertEqual(event.payload["longitude"], .number(116.4))
        XCTAssertEqual(event.payload["horizontalAccuracyM"], .number(5))
        XCTAssertEqual(event.payload["targetLatitude"], .number(39.91))
        XCTAssertEqual(event.payload["targetKind"], .string("pin"))
        XCTAssertEqual(event.payload["source"], .string("ios_gps"))
    }

    func testNoteEvent() {
        let event = makeBuilder().makeNoteEvent(hole: 2, note: "wind picking up")
        XCTAssertEqual(event.kind, .note)
        XCTAssertEqual(event.payload["note"], .string("wind picking up"))
    }

    func testIncrementingEventIdsAreUnique() {
        let builder = makeBuilder()
        let first = builder.makeScoreEvent(hole: 1, strokes: 4)
        let second = builder.makePuttEvent(hole: 1, putts: 2)
        XCTAssertEqual(first.eventId, "evt-1")
        XCTAssertEqual(second.eventId, "evt-2")
        XCTAssertNotEqual(first.eventId, second.eventId)
    }

    private func makeLargeDecision(confidenceSource: String) -> CaddieDecisionResponse {
        let largeBlob = String(repeating: "x", count: 150_000)
        let club: [String: JSONValue] = [
            "clubName": .string("8I"),
            "sourceRefs": .array([.string(largeBlob)]),
        ]
        let clubRecommendation: [String: JSONValue] = [
            "clubs": .array([.object(club)]),
        ]
        let targetWindow: [String: JSONValue] = [
            "frontCarry_m": .number(135),
            "backCarry_m": .number(155),
        ]
        let selected: [String: JSONValue] = [
            "id": .string("stock"),
            "label": .string("Stock"),
            "carry_m": .number(145),
            "riskScore": .number(1),
            "targetWindow": .object(targetWindow),
            "clubRecommendation": .object(clubRecommendation),
            "historyAdjustment": .object(["rawSamples": .string(largeBlob)]),
        ]
        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2",
            decisionId: "online-decision-4",
            sourceRef: "round-1:4",
            evidenceRefs: ["round-1:4"],
            shotType: "approach",
            phase: "Approach",
            context: [
                "sourceRef": .string("round-1:4"),
                "roundId": .string("round-1"),
                "hole": .number(4),
                "localHole": .number(4),
                "globalId": .number(31_676),
                "geometry": .string(largeBlob),
            ],
            options: [
                ["id": .string("safe"), "carry_m": .number(125)],
                selected,
                ["id": .string("attack"), "carry_m": .number(165)],
            ],
            selected: selected,
            selectedOptionId: "stock",
            selectedOption: selected,
            sequences: [["rawRoute": .string(largeBlob)]],
            selectedSequence: ["rawRoute": .string(largeBlob)],
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [["rawEvidence": .string(largeBlob)]],
            confidence: [
                "level": .string("medium"),
                "source": .string(confidenceSource),
            ],
            missingData: [],
            auditCriteria: [
                ["label": .string("club_match"), "rule": .string("match selected club")],
                ["label": .string("carry_window"), "rule": .string("match selected carry")],
            ]
        )
    }
}
