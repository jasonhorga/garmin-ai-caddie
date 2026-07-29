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
}
