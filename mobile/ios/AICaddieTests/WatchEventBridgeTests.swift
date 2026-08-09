import XCTest
@testable import AICaddie

final class WatchEventBridgeTests: XCTestCase {
    func testWatchRoundSeedUsesRealCourseAndHoleFacts() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()

        let seed = bridge.makeWatchRoundSeedPayload(
            package: package,
            activeHole: 1
        )

        XCTAssertEqual(seed.roundId, "live-round-1")
        XCTAssertEqual(seed.courseName, "Fixture Links")
        XCTAssertEqual(seed.activeHole, 1)
        XCTAssertEqual(seed.holes.map(\.hole), [1])
        XCTAssertEqual(seed.holes.map(\.par), [4])
        XCTAssertEqual(seed.holes.map(\.globalId), [31795])
        XCTAssertEqual(try XCTUnwrap(seed.holes.first?.distanceM), 374.904, accuracy: 0.001)
    }

    func testWatchRoundClosurePublishesTypedDisposition() throws {
        let bridge = WatchEventBridge()
        var received: WatchRoundClosurePayload?
        bridge.onRoundClosure = { received = $0 }
        let closure = WatchRoundClosurePayload(
            roundId: "watch-closure-round",
            disposition: .abandoned,
            closedAt: "2026-08-09T00:00:00Z"
        )
        let object = try XCTUnwrap(try Self.jsonObject(from: closure) as? [String: Any])

        bridge.handleWatchRoundClosure(object)

        XCTAssertEqual(received, closure)
    }

    func testWatchRoundSeedIncludesTeeCoordinateFromRealMapProjection() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackageWithTeeProjection()

        let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 1)

        XCTAssertEqual(try XCTUnwrap(seed.holes.first?.teeLatitude), 0.8, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(seed.holes.first?.teeLongitude), 0.2, accuracy: 0.000001)
    }

    func testWatchRoundSeedUsesHoleTeeCoordinateWhenFastPackageOmitsCoursePrep() throws {
        let bridge = WatchEventBridge()
        let base = try fixturePackage()
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(base)) as? [String: Any]
        )
        var holes = try XCTUnwrap(object["holes"] as? [[String: Any]])
        holes[0]["teeLatitude"] = 40.0454995
        holes[0]["teeLongitude"] = 116.5461531
        object["holes"] = holes
        object["coursePrep"] = NSNull()
        let package = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: object)
        )

        let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 1)

        XCTAssertEqual(try XCTUnwrap(seed.holes.first?.teeLatitude), 40.0454995, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(seed.holes.first?.teeLongitude), 116.5461531, accuracy: 0.000001)
    }

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
                    "label": .string("1D-5I-54"),
                    "expectedRemaining_m": .number(13),
                    "sourceRefs": .array([.string("club-sample-1d-0")]),
                    "clubs": .array([
                        .object(["clubName": .string("1D"), "targetCarry_m": .number(245)]),
                        .object(["clubName": .string("5I"), "targetCarry_m": .number(168)]),
                        .object(["clubName": .string("54"), "targetCarry_m": .number(94)]),
                    ]),
                ]
            ],
            selectedSequence: [
                "id": .string("stock"),
                "label": .string("1D-5I-54"),
                "expectedRemaining_m": .number(13),
                "clubs": .array([
                    .object(["clubName": .string("1D"), "targetCarry_m": .number(245)]),
                    .object(["clubName": .string("5I"), "targetCarry_m": .number(168)]),
                    .object(["clubName": .string("54"), "targetCarry_m": .number(94)]),
                ]),
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
        XCTAssertEqual(payload.holePlanSummary, "1D → 5I → 54 · 留 14 码")
        XCTAssertEqual(payload.expectedRemainingM, 13)

        let plans = bridge.makeWatchCaddieOptions(from: decision)
        let stock = try XCTUnwrap(plans.first { $0.optionId == "stock" })
        XCTAssertEqual(stock.plan?.map(\.clubName), ["1D", "5I", "54"])
        XCTAssertEqual(stock.plan?.map(\.carryM), [245, 168, 94])
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

    func testLiveDecisionBuildsCompleteRootRecommendationFromItsInputAndMeasuredCarryRange() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()
        let selected: [String: JSONValue] = [
            "id": .string("stock"),
            "label": .string("推进"),
            "carry_m": .number(205),
            "clubName": .string("3W"),
            "dispersion": .object([
                "state": .string("modeled"),
                "clubName": .string("3W"),
                "sampleSize": .number(24),
                "carryP10_m": .number(188),
                "carryP90_m": .number(220),
            ]),
        ]
        let decision = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v1",
            decisionId: "decision-live-1",
            sourceRef: "round:live-round-1:hole:1",
            evidenceRefs: ["club-profile:3W", "route:1"],
            shotType: "tee",
            phase: "tee",
            context: [
                "source": .string("ios_live"),
                "strategyMode": .string("stock"),
                "currentLocation": .object([
                    "latitude": .number(40.0455),
                    "longitude": .number(116.5462),
                    "horizontalAccuracyM": .number(5),
                    "capturedAt": .string("2026-06-20T00:00:00Z"),
                ]),
            ],
            options: [selected],
            selected: selected,
            selectedOptionId: "stock",
            selectedOption: selected,
            sequences: nil,
            selectedSequence: nil,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [["label": .string("route"), "state": .string("ready")]],
            confidence: ["level": .string("high"), "source": .string("live_decision")],
            missingData: [],
            auditCriteria: []
        )
        let holeMap = WatchHoleMap(
            w: 1000,
            h: 1000,
            you: [500, 900],
            pin: [500, 100],
            layup: [500, 500],
            apex: [500, 700],
            greenCtrl: [500, 300],
            route: [[500, 900, 0], [500, 500, 200], [500, 100, 400]]
        )

        let payload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: try XCTUnwrap(package.holes.first),
            score: 0,
            putts: 0,
            penaltyCount: 0,
            selectedClub: nil,
            decision: decision,
            holeMap: holeMap
        )

        let object = try XCTUnwrap(try Self.jsonObject(from: payload) as? [String: Any])
        let recommendation = try XCTUnwrap(object["rootCaddieRecommendation"] as? [String: Any])
        XCTAssertEqual(recommendation["decisionId"] as? String, "decision-live-1")
        XCTAssertEqual(recommendation["clubName"] as? String, "3W")
        XCTAssertEqual(recommendation["aimCarryM"] as? Double, 205)
        XCTAssertEqual(recommendation["carryP10M"] as? Double, 188)
        XCTAssertEqual(recommendation["carryP90M"] as? Double, 220)
        XCTAssertEqual(recommendation["sampleSize"] as? Int, 24)
        XCTAssertEqual(recommendation["source"] as? String, "live")
        XCTAssertEqual(recommendation["mode"] as? String, "automatic")
        XCTAssertEqual(recommendation["generatedAt"] as? String, "2026-06-20T00:00:00Z")
        XCTAssertEqual(recommendation["validUntil"] as? String, "2026-06-20T00:03:00Z")
        XCTAssertEqual(recommendation["maximumMovementM"] as? Double, 25)
        XCTAssertEqual(recommendation["evidenceCount"] as? Int, 2)
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
            createdAt: "2026-05-25T00:00:00Z",
            fairwayResult: "LEFT"
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
        XCTAssertEqual(try store.loadEvents().first?.payload["fairway"], .string("left"))

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

    func testDuplicateWatchRetryReentersAsyncAcceptanceBeforeAcknowledgement() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let bridge = WatchEventBridge(offlineStore: store)
        let event = WatchInputEvent(
            eventId: "watch-retry-1",
            roundId: "closed-round",
            hole: 1,
            kind: .score,
            value: "5",
            createdAt: "2026-08-09T08:00:00Z"
        )
        let liveEvent = try bridge.mapWatchInputEvent(event)
        try store.appendEvent(liveEvent)
        let callback = expectation(description: "duplicate is offered to the durable acceptance path")
        let reply = expectation(description: "watch receives duplicate acknowledgement")
        bridge.onAcceptedLiveEvent = { retried in
            XCTAssertEqual(retried.eventId, liveEvent.eventId)
            callback.fulfill()
        }
        var replyPayload: [String: Any]?

        bridge.handleWatchInputMessage(
            ["event": try Self.jsonObject(from: event)]
        ) { value in
            replyPayload = value
            reply.fulfill()
        }

        await fulfillment(of: [callback, reply], timeout: 2)
        XCTAssertEqual(replyPayload?["accepted"] as? Bool, true)
        XCTAssertEqual(replyPayload?["duplicateEventIds"] as? [String], [event.eventId])
        XCTAssertEqual(try store.loadEvents().map(\.eventId), [event.eventId])
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

    func testWatchManualShotLocationMapsToLiveLocationEvent() throws {
        let bridge = WatchEventBridge()
        let event = WatchInputEvent(
            eventId: "watch-location-1",
            roundId: "round-1",
            hole: 1,
            kind: .location,
            value: "40.0454995,116.5461531,5.0",
            createdAt: "2026-07-26T08:00:00Z"
        )

        let liveEvent = try bridge.mapWatchInputEvent(event)

        XCTAssertEqual(liveEvent.kind, .location)
        XCTAssertEqual(liveEvent.payload["latitude"], .number(40.0454995))
        XCTAssertEqual(liveEvent.payload["longitude"], .number(116.5461531))
        XCTAssertEqual(liveEvent.payload["horizontalAccuracyM"], .number(5))
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
        XCTAssertEqual(tee.route, overlay.route)           // hazard map keeps the real placement line
        let live = try XCTUnwrap(WatchEventBridge.makeHoleMap(overlay: overlay, landingM: 240, youPxOverride: [123, 456]))
        XCTAssertEqual(live.you, [123, 456])               // GPS fix → projected position
        XCTAssertEqual(live.pin, [200, 100])               // pin unchanged
        XCTAssertEqual(live.route, overlay.route)
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }

    private func fixturePackageWithTeeProjection() throws -> LiveRoundPackage {
        let base = try fixturePackage()
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(base)) as? [String: Any]
        )
        object["coursePrep"] = [
            "schema": "ai-caddie-course-prep-package-v1",
            "globalId": 31795,
            "missingData": [],
            "holes": [[
                "hole": 1,
                "par": 4,
                "par_source": "fixture",
                "blue_yards": 410,
                "route_len_m": 375.0,
                "route": [[20.0, 80.0, 0.0], [80.0, 20.0, 375.0]],
                "geometryCoverage": "ready",
                "sourceRefs": [],
                "missingData": [],
                "candidateRoutes": [],
                "carryTargets": [],
                "steps": [],
                "cautions": [],
                "hazards": ["water_carry": [], "bunkers": []],
                "map": [
                    "image": "data:image/jpeg;base64,AAAA",
                    "overlay": [
                        "w": 100, "h": 100, "ppm": 1.0, "ln": 375.0,
                        "route": [[20.0, 80.0, 0.0], [80.0, 20.0, 375.0]],
                    ],
                ],
                "holeImageProjection": [
                    "available": true,
                    "widthPx": 100,
                    "heightPx": 100,
                    "refs": [
                        ["lat": 0.0, "lon": 0.0, "px": 0.0, "py": 0.0],
                        ["lat": 0.0, "lon": 1.0, "px": 100.0, "py": 0.0],
                        ["lat": 1.0, "lon": 0.0, "px": 0.0, "py": 100.0],
                    ],
                ],
            ]],
        ]
        let data = try JSONSerialization.data(withJSONObject: object)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }

    private static func jsonObject<T: Encodable>(from value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data)
    }
}
