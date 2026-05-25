import CoreLocation
import Foundation

public final class LiveRoundEventBuilder {
    private let roundId: String
    private let idFactory: () -> String
    private let now: () -> Date
    private let formatter: ISO8601DateFormatter

    public init(
        roundId: String,
        idFactory: @escaping () -> String = { UUID().uuidString },
        now: @escaping () -> Date = Date.init
    ) {
        self.roundId = roundId
        self.idFactory = idFactory
        self.now = now
        self.formatter = ISO8601DateFormatter()
    }

    public func makeLocationEvent(
        hole: Int,
        coordinate: CLLocationCoordinate2D,
        horizontalAccuracyM: Double?,
        altitudeM: Double? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "latitude": .number(coordinate.latitude),
            "longitude": .number(coordinate.longitude),
            "source": .string("ios_gps"),
        ]
        payload["horizontalAccuracyM"] = jsonNumberOrNull(horizontalAccuracyM)
        payload["altitudeM"] = jsonNumberOrNull(altitudeM)
        return event(hole: hole, kind: .location, payload: payload)
    }

    public func makePhotoEvent(
        hole: Int,
        assetLocalId: String,
        fileURL: URL?,
        note: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "assetLocalId": .string(assetLocalId),
            "mediaType": .string("photo"),
            "source": .string("ios_camera"),
        ]
        payload["fileURL"] = jsonStringOrNull(fileURL?.absoluteString)
        payload["note"] = jsonStringOrNull(note)
        return event(hole: hole, kind: .photo, payload: payload)
    }

    public func makeVideoEvent(
        hole: Int,
        assetLocalId: String,
        fileURL: URL?,
        durationS: Double?,
        note: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "assetLocalId": .string(assetLocalId),
            "mediaType": .string("video"),
            "source": .string("ios_camera"),
        ]
        payload["fileURL"] = jsonStringOrNull(fileURL?.absoluteString)
        payload["durationS"] = jsonNumberOrNull(durationS)
        payload["note"] = jsonStringOrNull(note)
        return event(hole: hole, kind: .video, payload: payload)
    }

    public func makeScoreEvent(hole: Int, strokes: Int) -> LiveRoundEvent {
        event(hole: hole, kind: .score, payload: ["strokes": .number(Double(strokes))])
    }

    public func makeClubEvent(hole: Int, clubName: String) -> LiveRoundEvent {
        event(hole: hole, kind: .club, payload: ["clubName": .string(clubName)])
    }

    public func makePuttEvent(hole: Int, putts: Int) -> LiveRoundEvent {
        event(hole: hole, kind: .putt, payload: ["putts": .number(Double(putts))])
    }

    public func makePenaltyEvent(hole: Int, penalties: Int) -> LiveRoundEvent {
        event(hole: hole, kind: .penalty, payload: ["penalties": .number(Double(penalties))])
    }

    public func makeNoteEvent(hole: Int, note: String) -> LiveRoundEvent {
        event(hole: hole, kind: .note, payload: ["note": .string(note)])
    }

    private func event(hole: Int, kind: LiveRoundEventKind, payload: [String: JSONValue]) -> LiveRoundEvent {
        LiveRoundEvent(
            eventId: idFactory(),
            roundId: roundId,
            timestamp: formatter.string(from: now()),
            hole: hole,
            kind: kind,
            payload: payload
        )
    }

    private func jsonStringOrNull(_ value: String?) -> JSONValue {
        guard let value else {
            return .null
        }
        return .string(value)
    }

    private func jsonNumberOrNull(_ value: Double?) -> JSONValue {
        guard let value else {
            return .null
        }
        return .number(value)
    }
}
