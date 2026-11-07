import XCTest
@testable import AICaddie

@MainActor
final class CurrentHoleShotCountTests: XCTestCase {
    private func locationEvent(
        id: String,
        roundId: String = "round-1",
        hole: Int = 3,
        timestamp: String,
        source: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "latitude": .number(40.0),
            "longitude": .number(116.0)
        ]
        if let source { payload["source"] = .string(source) }
        return LiveRoundEvent(
            eventId: id,
            roundId: roundId,
            timestamp: timestamp,
            hole: hole,
            kind: .location,
            payload: payload
        )
    }

    private func actualClubEvent(
        id: String,
        roundId: String = "round-1",
        hole: Int = 3,
        source: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = ["clubName": .string("7I")]
        if let source {
            payload["source"] = .string(source)
        } else {
            payload["actualShot"] = .object([
                "sourceLocationEventId": .string("location-" + id),
                "shotOrder": .number(1),
            ])
        }
        return LiveRoundEvent(
            eventId: id,
            roundId: roundId,
            timestamp: "2026-10-27T08:01:00Z",
            hole: hole,
            kind: .club,
            payload: payload
        )
    }

    func testOneSnapshotReadIsSharedByFMBAndWatchDerivedValues() throws {
        var redrawReads = 0
        let events = [
            locationEvent(id: "tee", timestamp: "2026-10-27T08:00:00Z"),
            locationEvent(id: "landing", timestamp: "2026-10-27T08:05:00Z"),
            locationEvent(id: "other-hole", hole: 4, timestamp: "2026-10-27T08:06:00Z"),
            locationEvent(id: "other-round", roundId: "round-2", timestamp: "2026-10-27T08:07:00Z")
        ]
        let redrawLoad = {
            redrawReads += 1
            return events
        }

        // One redraw derives the F/M/B shot count, second-shot landing, and newest-shot marker
        // from one snapshot read.
        let redraw = CurrentHoleView.liveHoleEventDerivedValues(
            load: redrawLoad, roundId: "round-1", hole: 3
        )

        XCTAssertEqual(redraw.markedShots.map(\.eventId), ["tee", "landing"])
        XCTAssertEqual(redraw.secondShotCoordinate?.latitude ?? -1, 40.0)
        XCTAssertEqual(redraw.newestShotCoordinate?.capturedAt ?? "", "2026-10-27T08:05:00Z")
        XCTAssertEqual(redrawReads, 1)

        // sendWatchState builds its event portion through the same one-read boundary.
        var sendReads = 0
        let sendLoad = {
            sendReads += 1
            return events
        }
        let payload = CurrentHoleView.liveWatchShotPayload(
            load: sendLoad, roundId: "round-1", hole: 3
        )
        XCTAssertEqual(payload.phoneShotEventIds, [])
        XCTAssertEqual(payload.teeShotLanding?.latitude ?? -1, 40.0)
        XCTAssertEqual(payload.lastShotCapturedAt ?? "", "2026-10-27T08:05:00Z")
        XCTAssertEqual(sendReads, 1)

        _ = CurrentHoleView.liveWatchShotPayload(
            load: sendLoad, roundId: "round-1", hole: 3
        )
        XCTAssertEqual(sendReads, 2)
    }

    /// C250 red test: a GPS/location fact before the first stroke must leave the hole in its
    /// opening state. It is a position fact, not evidence that a shot was hit.
    func testPositionOnlyEventDoesNotCountAsARecordedShot() {
        let events = [locationEvent(id: "position", timestamp: "2026-10-27T08:00:00Z")]

        XCTAssertEqual(
            CurrentHoleView.recordedNonPuttShotCount(from: events, roundId: "round-1", hole: 3),
            0,
            "a position-only event must not leave the tee state"
        )
    }

    func testActualClubEvidenceCountsWhilePositionAndPlanningEventsDoNot() {
        let events = [
            locationEvent(id: "position", timestamp: "2026-10-27T08:00:00Z"),
            locationEvent(id: "location-phone-shot", timestamp: "2026-10-27T08:00:30Z", source: "ios_gps"),
            actualClubEvent(id: "phone-shot"),
            actualClubEvent(id: "watch-shot", source: "apple_watch"),
            locationEvent(id: "watch-location", timestamp: "2026-10-27T08:01:30Z", source: "apple_watch"),
            LiveRoundEvent(
                eventId: "recommendation", roundId: "round-1", timestamp: "2026-10-27T08:02:00Z",
                hole: 3, kind: .club, payload: ["clubName": .string("1W")]
            ),
        ]

        XCTAssertEqual(
            CurrentHoleView.recordedNonPuttShotCount(from: events, roundId: "round-1", hole: 3),
            2,
            "a phone location and its actual club are one stroke; untagged positions and Watch planning clubs are none"
        )
    }

    /// While the phone club prompt is still open the recorded position is pending: the hole keeps
    /// its opening state until the prompt is answered or skipped.
    func testPendingPhonePositionKeepsOpeningStateUntilThePromptCloses() {
        let events = [
            locationEvent(id: "phone-location", timestamp: "2026-10-27T08:00:00Z", source: "ios_gps"),
        ]
        let pendingCount = CurrentHoleView.recordedNonPuttShotCount(
            from: events, roundId: "round-1", hole: 3, pendingLocationEventId: "phone-location"
        )
        let closedCount = CurrentHoleView.recordedNonPuttShotCount(
            from: events, roundId: "round-1", hole: 3
        )

        XCTAssertEqual(pendingCount, 0, "a pending phone position must not leave the tee state")
        XCTAssertEqual(closedCount, 1, "closing the prompt confirms the recorded stroke")
        XCTAssertEqual(
            CurrentHoleView.caddiePlanningDistanceMetres(
                recordedShotCount: pendingCount,
                hasLeftSelectedTee: false,
                manualM: nil,
                isTeeShotOffTheHole: false,
                routeRemainingM: 180,
                liveMiddleM: 205,
                staticMiddleM: 241,
                holeYards: 263,
                pinM: 170,
                shotType: "tee"
            ) ?? -1,
            241,
            accuracy: 0.001,
            "the opening plan keeps the tee distance while the shot is pending"
        )
    }

    func testWatchLocationWithoutAClubStillCountsOnce() {
        let events = [
            locationEvent(id: "watch-location", timestamp: "2026-10-27T08:00:00Z", source: "apple_watch"),
        ]

        XCTAssertEqual(
            CurrentHoleView.recordedNonPuttShotCount(from: events, roundId: "round-1", hole: 3),
            1,
            "skipping the optional Watch club prompt does not erase the confirmed stroke"
        )
    }

    /// J5.4: the phone record button saves the GPS shot first; "跳过球杆（位置已记录）" keeps that
    /// stroke, so the hole leaves its opening state even without a club.
    func testPhoneRecordedShotWithSkippedClubStillCountsOnce() {
        let events = [
            locationEvent(id: "phone-location", timestamp: "2026-10-27T08:00:00Z", source: "ios_gps"),
        ]

        XCTAssertEqual(
            CurrentHoleView.recordedNonPuttShotCount(from: events, roundId: "round-1", hole: 3),
            1,
            "skipping the phone club prompt does not erase the recorded stroke"
        )
        XCTAssertEqual(
            LiveMarkedShots.actualShotLocationEventIds(in: events, roundId: "round-1", hole: 3),
            ["phone-location"],
            "the skipped-club phone shot still retires Watch planning and caddie origins"
        )
    }

    func testWatchPlanningClubWithoutLocationDoesNotCountAsAShot() {
        let event = LiveRoundEvent(
            eventId: "watch-distance",
            roundId: "round-1",
            timestamp: "2026-10-27T08:00:00Z",
            hole: 3,
            kind: .club,
            payload: [
                "clubName": .string("7I"),
                "distanceToPinM": .number(155),
                "source": .string("apple_watch"),
            ]
        )

        XCTAssertEqual(
            CurrentHoleView.recordedNonPuttShotCount(from: [event], roundId: "round-1", hole: 3),
            0,
            "a Watch planning-distance event must not advance the shot gates"
        )
    }

    func testPositionOnlyKeepsOpeningPlanningDistanceUntilTheFirstRealShot() {
        let positionOnly = [locationEvent(id: "position", timestamp: "2026-10-27T08:00:00Z")]
        let actualShot = positionOnly + [actualClubEvent(id: "shot")]
        let openingCount = CurrentHoleView.recordedNonPuttShotCount(
            from: positionOnly, roundId: "round-1", hole: 3
        )
        let afterShotCount = CurrentHoleView.recordedNonPuttShotCount(
            from: actualShot, roundId: "round-1", hole: 3
        )

        let openingDistance = CurrentHoleView.caddiePlanningDistanceMetres(
            recordedShotCount: openingCount,
            hasLeftSelectedTee: false,
            manualM: nil,
            isTeeShotOffTheHole: false,
            routeRemainingM: nil,
            liveMiddleM: 205,
            staticMiddleM: 241,
            holeYards: 263,
            pinM: 170,
            shotType: "tee"
        )
        let afterShotDistance = CurrentHoleView.caddiePlanningDistanceMetres(
            recordedShotCount: afterShotCount,
            hasLeftSelectedTee: false,
            manualM: nil,
            isTeeShotOffTheHole: false,
            routeRemainingM: 180,
            liveMiddleM: 205,
            staticMiddleM: 241,
            holeYards: 263,
            pinM: 170,
            shotType: "tee"
        )

        XCTAssertEqual(openingDistance ?? -1, 241, accuracy: 0.001)
        XCTAssertEqual(afterShotDistance ?? -1, 180, accuracy: 0.001)
    }

    func testConfirmedShotLocationIDsExcludePendingPhonePositions() {
        let confirmedLocation = locationEvent(
            id: "location-phone-shot", timestamp: "2026-10-27T08:00:00Z", source: "ios_gps"
        )
        let confirmedClub = actualClubEvent(id: "phone-shot")
        let pendingPosition = locationEvent(
            id: "pending-position", timestamp: "2026-10-27T08:02:00Z", source: "ios_gps"
        )

        XCTAssertEqual(
            LiveMarkedShots.actualShotLocationEventIds(
                in: [confirmedLocation, confirmedClub, pendingPosition],
                roundId: "round-1",
                hole: 3,
                pendingLocationEventId: "pending-position"
            ),
            ["location-phone-shot"],
            "pending phone GPS must not become a Watch shot or caddie origin"
        )
    }
}
