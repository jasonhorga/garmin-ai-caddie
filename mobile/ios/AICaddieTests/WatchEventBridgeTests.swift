import XCTest
@testable import AICaddie

final class WatchEventBridgeTests: XCTestCase {
    func testWatchRoundStatePayloadCompactsDecisionEvidenceWithoutDroppingContext() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()
        let decision = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v1",
            decisionId: "decision-1",
            sourceRef: nil,
            evidenceRefs: nil,
            shotType: "approach",
            phase: "approach",
            context: [:],
            options: [
                [
                    "id": .string("stock"),
                    "label": .string("Center green"),
                    "carryM": .number(142),
                    "clubName": .string("8I"),
                ]
            ],
            selected: nil,
            selectedOptionId: "stock",
            selectedOption: nil,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [
                [
                    "label": .string("route"),
                    "source": .string("prodgeometry"),
                    "kind": .string("geometry"),
                    "value": .number(2),
                    "text": .string("water left"),
                    "state": .string("ready"),
                ]
            ],
            confidence: ["level": .string("medium")],
            missingData: [
                [
                    "label": .string("wind"),
                    "reason": .string("not cached"),
                    "state": .string("missing"),
                ]
            ],
            auditCriteria: []
        )

        let payload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: try XCTUnwrap(package.holes.first),
            score: 4,
            putts: 2,
            penaltyCount: 0,
            selectedClub: "8I",
            decision: decision,
            distanceToPinM: 139,
            targetLatitude: 22.279,
            targetLongitude: 114.162,
            targetKind: "pin"
        )

        XCTAssertEqual(payload.distanceM, 139)
        XCTAssertEqual(payload.targetKind, "pin")
        XCTAssertEqual(payload.targetLatitude, 22.279)
        XCTAssertEqual(payload.targetNote, "Center green / pin set on iPhone")
        XCTAssertEqual(payload.evidenceSummary, "route / prodgeometry / geometry: 2 / water left / ready")
        XCTAssertEqual(payload.missingDataSummary, "wind: not cached / missing")
    }

    func testOfflineEvidenceSummaryRedactsPrivateSourceRefs() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()
        let option = OfflineCaddieOption(
            optionId: "stock",
            label: "Center green",
            clubName: "8I",
            carryM: 142,
            riskScore: 1,
            source: "offline_seed",
            sourceRefs: ["/Users/player/private/raw.json"]
        )

        let payload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: try XCTUnwrap(package.holes.first),
            score: 4,
            putts: 2,
            penaltyCount: 0,
            selectedClub: "8I",
            decision: nil,
            offlineOption: option
        )

        XCTAssertEqual(payload.evidenceSummary, "offline_seed / [redacted]")
        XCTAssertFalse(try XCTUnwrap(payload.evidenceSummary).contains("/Users/"))
    }

    func testWatchInputAcknowledgementReportsAcceptedAndDuplicateEventIds() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let bridge = WatchEventBridge(offlineStore: store)
        let event = WatchInputEvent(
            eventId: "watch-event-1",
            roundId: "round-1",
            hole: 4,
            kind: .score,
            value: "5",
            createdAt: "2026-05-25T00:00:00Z"
        )
        let message = ["event": try Self.jsonObject(from: event)]

        var acceptedReply: [String: Any]?
        bridge.handleWatchInputMessage(message) { reply in
            acceptedReply = reply
        }

        XCTAssertEqual(acceptedReply?["accepted"] as? Bool, true)
        XCTAssertEqual(acceptedReply?["eventId"] as? String, "watch-event-1")
        XCTAssertEqual(acceptedReply?["acceptedEventIds"] as? [String], ["watch-event-1"])
        XCTAssertEqual(acceptedReply?["duplicateEventIds"] as? [String], [])
        XCTAssertEqual(try store.loadEvents().map(\.eventId), ["watch-event-1"])

        var duplicateReply: [String: Any]?
        bridge.handleWatchInputMessage(message) { reply in
            duplicateReply = reply
        }

        XCTAssertEqual(duplicateReply?["accepted"] as? Bool, true)
        XCTAssertEqual(duplicateReply?["eventId"] as? String, "watch-event-1")
        XCTAssertEqual(duplicateReply?["acceptedEventIds"] as? [String], [])
        XCTAssertEqual(duplicateReply?["duplicateEventIds"] as? [String], ["watch-event-1"])
        XCTAssertEqual(try store.loadEvents().map(\.eventId), ["watch-event-1"])
    }

    func testWatchDistanceInputMapsToLiveDistanceForOfflineRestore() throws {
        let bridge = WatchEventBridge()
        let event = WatchInputEvent(
            eventId: "watch-distance-1",
            roundId: "round-1",
            hole: 4,
            kind: .distance,
            value: "155",
            createdAt: "2026-05-25T00:00:00Z",
            contextClub: "8I"
        )

        let liveEvent = try bridge.mapWatchInputEvent(event)

        XCTAssertEqual(liveEvent.kind, .club)
        XCTAssertEqual(liveEvent.payload["clubName"], .string("8I"))
        XCTAssertEqual(liveEvent.payload["distanceToPinM"], .number(155))
        XCTAssertEqual(liveEvent.payload["source"], .string("apple_watch"))
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }
}
