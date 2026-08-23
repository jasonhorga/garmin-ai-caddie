import CoreLocation
import Foundation

struct LiveHoleGPSCandidate: Equatable {
    let hole: Int
    let distanceM: Double
}

/// Tee proximity proposes a hole; it never changes the playing cursor by itself. This distinction is
/// important on compact courses where an approach can finish beside another Tee or an errant shot can
/// land on an adjacent hole. The player confirms the candidate from the live screen or scorecard.
enum LiveHoleGPSResolver {
    static let maximumHorizontalAccuracyM = 35.0
    static let maximumTeeDistanceM = 45.0
    static let minimumSeparationM = 12.0

    static func candidate(
        holes: [Hole],
        coordinate: CLLocationCoordinate2D,
        horizontalAccuracyM: Double
    ) -> LiveHoleGPSCandidate? {
        guard CLLocationCoordinate2DIsValid(coordinate),
              coordinate.latitude.isFinite,
              coordinate.longitude.isFinite,
              horizontalAccuracyM.isFinite,
              (0...maximumHorizontalAccuracyM).contains(horizontalAccuracyM) else { return nil }

        let ranked = holes.compactMap { hole -> LiveHoleGPSCandidate? in
            guard let latitude = hole.teeLatitude,
                  let longitude = hole.teeLongitude,
                  latitude.isFinite,
                  longitude.isFinite,
                  (-90...90).contains(latitude),
                  (-180...180).contains(longitude) else { return nil }
            return LiveHoleGPSCandidate(
                hole: hole.number,
                distanceM: GeoDistance.haversineMetres(
                    coordinate.latitude,
                    coordinate.longitude,
                    latitude,
                    longitude
                )
            )
        }
        .sorted { lhs, rhs in
            lhs.distanceM == rhs.distanceM ? lhs.hole < rhs.hole : lhs.distanceM < rhs.distanceM
        }

        guard let nearest = ranked.first,
              nearest.distanceM <= maximumTeeDistanceM else { return nil }
        if ranked.count > 1,
           ranked[1].distanceM - nearest.distanceM < minimumSeparationM {
            return nil
        }
        return nearest
    }
}
