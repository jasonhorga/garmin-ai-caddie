import CoreLocation
import Foundation

public enum LiveCaddieDistance {
    /// A live GPS range is useful only while the player is plausibly on this hole. A stale fix from
    /// home or another hole must not outrank the downloaded Tee-to-green distance and create a
    /// 20,000-yard caddie sequence. Manual input remains authoritative but is still finite/positive.
    public static func resolve(
        manualM: Double?,
        liveMiddleM: Double?,
        staticMiddleM: Double?,
        holeYards: Int? = nil
    ) -> Double? {
        if let manualM, manualM.isFinite, manualM > 0 { return manualM }
        let nominalM = holeYards.flatMap { $0 > 0 ? CoursePrepRoute.metres(fromYards: Double($0)) : nil }
            ?? staticMiddleM
        let maximumPlausibleM = max(GeoDistance.maximumUsefulGreenMetres, (nominalM ?? 0) + 250)
        if let liveMiddleM,
           liveMiddleM.isFinite,
           liveMiddleM > 0,
           liveMiddleM <= maximumPlausibleM {
            return liveMiddleM
        }
        if let staticMiddleM, staticMiddleM.isFinite, staticMiddleM > 0 { return staticMiddleM }
        return nil
    }
}

public struct LiveCaddieInput {
    public let shotType: String
    public let distanceToPinM: Double?
    public let lie: String?
    public let coordinate: CLLocationCoordinate2D?
    public let targetCoordinate: CLLocationCoordinate2D?
    public let targetKind: String?
    public let horizontalAccuracyM: Double?
    public let capturedAt: String?
    public let strategyMode: String?
    public let visionFindings: [[String: JSONValue]]

    public init(
        shotType: String,
        distanceToPinM: Double? = nil,
        lie: String? = nil,
        coordinate: CLLocationCoordinate2D? = nil,
        targetCoordinate: CLLocationCoordinate2D? = nil,
        targetKind: String? = nil,
        horizontalAccuracyM: Double? = nil,
        capturedAt: String? = nil,
        strategyMode: String? = nil,
        visionFindings: [[String: JSONValue]] = []
    ) {
        self.shotType = shotType
        self.distanceToPinM = distanceToPinM
        self.lie = lie
        self.coordinate = coordinate
        self.targetCoordinate = targetCoordinate
        self.targetKind = targetKind
        self.horizontalAccuracyM = horizontalAccuracyM
        self.capturedAt = capturedAt
        self.strategyMode = strategyMode
        self.visionFindings = visionFindings
    }
}

public final class CaddieDecisionRequestBuilder {
    public init() {}

    public func makeDecisionRequest(seed: CaddieContextSeed, input: LiveCaddieInput) -> CaddieDecisionRequest {
        var context = seed.context
        context["source"] = .string("ios_live")
        context["sourceRef"] = .string(seed.sourceRef)
        context["hole"] = .number(Double(seed.hole))
        context["requiredLiveInputs"] = .array(seed.requiredLiveInputs.map { JSONValue.string($0) })

        if let distanceToPinM = input.distanceToPinM,
           distanceToPinM.isFinite,
           distanceToPinM > 0,
           distanceToPinM <= GeoDistance.maximumUsefulGreenMetres {
            context["distanceToPin_m"] = .number(distanceToPinM)
        }
        if let lie = input.lie, !lie.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            context["lie"] = .string(lie)
        }
        if let coordinate = input.coordinate {
            var location: [String: JSONValue] = [
                "latitude": .number(coordinate.latitude),
                "longitude": .number(coordinate.longitude),
                "source": .string("ios_gps")
            ]
            if let horizontalAccuracyM = input.horizontalAccuracyM {
                location["horizontalAccuracyM"] = .number(horizontalAccuracyM)
            }
            if let capturedAt = input.capturedAt,
               !capturedAt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                location["capturedAt"] = .string(capturedAt)
            }
            context["currentLocation"] = .object(location)
        }
        if let targetCoordinate = input.targetCoordinate {
            var targetLocation: [String: JSONValue] = [
                "latitude": .number(targetCoordinate.latitude),
                "longitude": .number(targetCoordinate.longitude),
                "source": .string("ios_target")
            ]
            if let targetKind = input.targetKind, !targetKind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                targetLocation["kind"] = .string(targetKind)
            }
            context["targetLocation"] = .object(targetLocation)
        }
        if let strategyMode = input.strategyMode, !strategyMode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            context["strategyMode"] = .string(strategyMode)
        }
        if !input.visionFindings.isEmpty {
            context["visionFindings"] = .array(input.visionFindings.map { .object($0) })
        }

        return CaddieDecisionRequest(shotType: input.shotType, context: context)
    }
}
