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
        altitudeM: Double? = nil,
        targetCoordinate: CLLocationCoordinate2D? = nil,
        targetKind: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "latitude": .number(coordinate.latitude),
            "longitude": .number(coordinate.longitude),
            "source": .string("ios_gps"),
        ]
        payload["horizontalAccuracyM"] = jsonNumberOrNull(horizontalAccuracyM)
        payload["altitudeM"] = jsonNumberOrNull(altitudeM)
        if let targetCoordinate {
            payload["targetLatitude"] = .number(targetCoordinate.latitude)
            payload["targetLongitude"] = .number(targetCoordinate.longitude)
            payload["targetSource"] = .string("ios_target")
            payload["targetKind"] = .string(targetKind ?? "pin")
        }
        return event(hole: hole, kind: .location, payload: payload)
    }

    public func makePhotoEvent(
        hole: Int,
        assetLocalId: String,
        fileURL: URL?,
        note: String? = nil,
        mediaId: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "assetLocalId": .string(assetLocalId),
            "mediaType": .string("photo"),
            "source": .string("ios_camera"),
        ]
        payload["fileURL"] = jsonStringOrNull(fileURL?.absoluteString)
        payload["note"] = jsonStringOrNull(note)
        if let mediaId {
            payload["mediaId"] = .string(mediaId)
        }
        return event(hole: hole, kind: .photo, payload: payload)
    }

    public func makeVideoEvent(
        hole: Int,
        assetLocalId: String,
        fileURL: URL?,
        durationS: Double?,
        note: String? = nil,
        mediaId: String? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = [
            "assetLocalId": .string(assetLocalId),
            "mediaType": .string("video"),
            "source": .string("ios_camera"),
        ]
        payload["fileURL"] = jsonStringOrNull(fileURL?.absoluteString)
        payload["durationS"] = jsonNumberOrNull(durationS)
        payload["note"] = jsonStringOrNull(note)
        if let mediaId {
            payload["mediaId"] = .string(mediaId)
        }
        return event(hole: hole, kind: .video, payload: payload)
    }

    public func makeScoreEvent(hole: Int, strokes: Int) -> LiveRoundEvent {
        event(hole: hole, kind: .score, payload: ["strokes": .number(Double(strokes))])
    }

    public func makeClubEvent(
        hole: Int,
        clubName: String,
        shotType: String? = nil,
        strategyMode: String? = nil,
        lie: String? = nil,
        distanceToPinM: Double? = nil,
        offlineOptionId: String? = nil,
        decision: CaddieDecisionResponse? = nil,
        actualShot: [String: JSONValue]? = nil
    ) -> LiveRoundEvent {
        var payload: [String: JSONValue] = ["clubName": .string(clubName)]
        if let shotType {
            payload["shotType"] = .string(shotType)
        }
        if let strategyMode {
            payload["strategyMode"] = .string(strategyMode)
        }
        if let lie {
            payload["lie"] = .string(lie)
        }
        payload["distanceToPinM"] = jsonNumberOrNull(distanceToPinM)
        payload["offlineOptionId"] = jsonStringOrNull(offlineOptionId)
        if let decision {
            if let decisionId = decision.decisionId {
                payload["decisionId"] = .string(decisionId)
            }
            payload["decision"] = .object(decision.auditPayload)
        }
        if let actualShot {
            payload["actualShot"] = .object(actualShot)
        }
        return event(hole: hole, kind: .club, payload: payload)
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
