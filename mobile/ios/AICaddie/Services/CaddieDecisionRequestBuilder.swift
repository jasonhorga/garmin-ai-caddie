import CoreLocation
import Foundation

public enum LiveCaddieDistance {
    public static func resolve(manualM: Double?, liveMiddleM: Double?, staticMiddleM: Double?) -> Double? {
        manualM ?? liveMiddleM ?? staticMiddleM
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

        if let distanceToPinM = input.distanceToPinM {
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
