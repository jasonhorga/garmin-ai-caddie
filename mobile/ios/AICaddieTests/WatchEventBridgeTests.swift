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
            sequences: [
                [
                    "id": .string("stock"),
                    "label": .string("1D-3W-58"),
                    "expectedStrokes": .number(3),
                    "expectedRemaining_m": .number(-21),
                    "sourceRefs": .array([.string("club-sample-1d-0")]),
                ]
            ],
            selectedSequence: [
                "id": .string("stock"),
                "label": .string("1D-3W-58"),
                "expectedStrokes": .number(3),
                "expectedRemaining_m": .number(-21),
            ],
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
        XCTAssertEqual(payload.availableClubs.map(\.clubName), ["8I", "9I", "7I"])
        XCTAssertEqual(payload.availableClubs.first?.sampleSize, 24)
        XCTAssertEqual(payload.availableClubs.first?.medianM, 144)
        XCTAssertEqual(payload.shotType, "approach")
        XCTAssertEqual(payload.strategyMode, "stock")
        XCTAssertEqual(payload.offlineOptionId, "stock")
        XCTAssertEqual(payload.decisionId, "decision-1")
        XCTAssertEqual(payload.holePlanSummary, "1D-3W-58 / 3 shots / leave -21m")
        XCTAssertEqual(payload.expectedStrokes, 3)
        XCTAssertEqual(payload.expectedRemainingM, -21)
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
        XCTAssertEqual(acceptedReply?["rejectedEventIds"] as? [String], [])
        XCTAssertEqual(try store.loadEvents().map(\.eventId), ["watch-event-1"])

        var duplicateReply: [String: Any]?
        bridge.handleWatchInputMessage(message) { reply in
            duplicateReply = reply
        }

        XCTAssertEqual(duplicateReply?["accepted"] as? Bool, true)
        XCTAssertEqual(duplicateReply?["eventId"] as? String, "watch-event-1")
        XCTAssertEqual(duplicateReply?["acceptedEventIds"] as? [String], [])
        XCTAssertEqual(duplicateReply?["duplicateEventIds"] as? [String], ["watch-event-1"])
        XCTAssertEqual(duplicateReply?["rejectedEventIds"] as? [String], [])
        XCTAssertEqual(try store.loadEvents().map(\.eventId), ["watch-event-1"])
    }

    func testWatchInputRejectionReportsRejectedEventIds() throws {
        let bridge = WatchEventBridge()
        let event = WatchInputEvent(
            eventId: "watch-distance-2",
            roundId: "round-1",
            hole: 4,
            kind: .distance,
            value: "155",
            createdAt: "2026-05-25T00:00:00Z"
        )
        let message = ["event": try Self.jsonObject(from: event)]

        var replyPayload: [String: Any]?
        bridge.handleWatchInputMessage(message) { reply in
            replyPayload = reply
        }

        XCTAssertEqual(replyPayload?["accepted"] as? Bool, false)
        XCTAssertEqual(replyPayload?["eventId"] as? String, "watch-distance-2")
        XCTAssertEqual(replyPayload?["rejectedEventIds"] as? [String], ["watch-distance-2"])
        XCTAssertEqual(replyPayload?["reason"] as? String, "missing_club_context")
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

    func testWatchClubInputIncludesDecisionContextForAudit() throws {
        let bridge = WatchEventBridge()
        let event = WatchInputEvent(
            eventId: "watch-club-1",
            roundId: "round-1",
            hole: 4,
            kind: .club,
            value: "8I",
            createdAt: "2026-05-25T00:00:00Z",
            contextClub: "8I",
            shotType: "approach",
            strategyMode: "stock",
            lie: "fairway",
            distanceToPinM: 142,
            offlineOptionId: "stock",
            decisionId: "decision-1"
        )

        let liveEvent = try bridge.mapWatchInputEvent(event)

        XCTAssertEqual(liveEvent.kind, .club)
        XCTAssertEqual(liveEvent.payload["clubName"], .string("8I"))
        XCTAssertEqual(liveEvent.payload["shotType"], .string("approach"))
        XCTAssertEqual(liveEvent.payload["strategyMode"], .string("stock"))
        XCTAssertEqual(liveEvent.payload["lie"], .string("fairway"))
        XCTAssertEqual(liveEvent.payload["distanceToPinM"], .number(142))
        XCTAssertEqual(liveEvent.payload["offlineOptionId"], .string("stock"))
        XCTAssertEqual(liveEvent.payload["decisionId"], .string("decision-1"))
        XCTAssertEqual(liveEvent.payload["source"], .string("apple_watch"))
    }

    func testWatchDistanceInputRejectsMissingClubContext() throws {
        let bridge = WatchEventBridge()
        let event = WatchInputEvent(
            eventId: "watch-distance-2",
            roundId: "round-1",
            hole: 4,
            kind: .distance,
            value: "155",
            createdAt: "2026-05-25T00:00:00Z"
        )

        XCTAssertThrowsError(try bridge.mapWatchInputEvent(event)) { error in
            XCTAssertTrue(error is WatchEventBridgeError)
        }
    }

    func testProjectToTopoPxMapsReferencePointsAndMidpoint() throws {
        // watch P1c: affine projection from 3 refs. Unit square: (lon,lat)→(px,py) with lon→x, lat→y×100.
        let refs: [(lat: Double, lon: Double, px: Double, py: Double)] = [
            (lat: 0, lon: 0, px: 0, py: 0),
            (lat: 0, lon: 1, px: 100, py: 0),
            (lat: 1, lon: 0, px: 0, py: 100),
        ]
        let atRef0 = try XCTUnwrap(WatchEventBridge.projectToTopoPx(lat: 0, lon: 0, refs: refs))
        XCTAssertEqual(atRef0[0], 0, accuracy: 0.001)
        XCTAssertEqual(atRef0[1], 0, accuracy: 0.001)
        let atRef1 = try XCTUnwrap(WatchEventBridge.projectToTopoPx(lat: 0, lon: 1, refs: refs))
        XCTAssertEqual(atRef1[0], 100, accuracy: 0.001)
        XCTAssertEqual(atRef1[1], 0, accuracy: 0.001)
        let mid = try XCTUnwrap(WatchEventBridge.projectToTopoPx(lat: 0.5, lon: 0.5, refs: refs))
        XCTAssertEqual(mid[0], 50, accuracy: 0.001)
        XCTAssertEqual(mid[1], 50, accuracy: 0.001)
        // Degenerate (collinear) refs → nil.
        let bad: [(lat: Double, lon: Double, px: Double, py: Double)] = [
            (lat: 0, lon: 0, px: 0, py: 0), (lat: 0, lon: 1, px: 100, py: 0), (lat: 0, lon: 2, px: 200, py: 0),
        ]
        XCTAssertNil(WatchEventBridge.projectToTopoPx(lat: 0.5, lon: 0.5, refs: bad))
    }

    func testMakeHoleMapUsesGpsYouOverrideElseTee() throws {
        // route: tee [50,480] → mid [150,250] @200m → green [200,100] @400m.
        let overlay = CoursePrepOverlay(w: 300, h: 500, ppm: 1, ln: 400,
                                        route: [[50, 480, 0], [150, 250, 200], [200, 100, 400]])
        let tee = try XCTUnwrap(WatchEventBridge.makeHoleMap(overlay: overlay, landingM: 240))
        XCTAssertEqual(tee.you, [50, 480])                 // no GPS → tee
        XCTAssertEqual(tee.pin, [200, 100])                // green = route end
        let live = try XCTUnwrap(WatchEventBridge.makeHoleMap(overlay: overlay, landingM: 240, youPxOverride: [123, 456]))
        XCTAssertEqual(live.you, [123, 456])               // GPS fix → projected position
        XCTAssertEqual(live.pin, [200, 100])               // pin unchanged
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }

    private static func jsonObject<T: Encodable>(from value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data)
    }
}
