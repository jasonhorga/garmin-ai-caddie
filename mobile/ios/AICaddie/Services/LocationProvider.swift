import Combine
import CoreLocation
import Foundation

public struct LocationFix {
    public let coordinate: CLLocationCoordinate2D
    public let horizontalAccuracyM: Double
    public let altitudeM: Double?
    public let capturedAt: String
}

public final class LocationProvider: NSObject, ObservableObject, CLLocationManagerDelegate {
    private let manager: CLLocationManager
    private let formatter = ISO8601DateFormatter()

    @Published public private(set) var latestFix: LocationFix?
    @Published public private(set) var authorizationStatus: CLAuthorizationStatus

    public init(manager: CLLocationManager = CLLocationManager()) {
        self.manager = manager
        self.authorizationStatus = manager.authorizationStatus
        super.init()
        self.manager.delegate = self
        self.manager.desiredAccuracy = kCLLocationAccuracyBest
        self.manager.distanceFilter = 3
    }

    public func requestAuthorization() {
        manager.requestWhenInUseAuthorization()
    }

    public func startUpdatingLocation() {
        manager.startUpdatingLocation()
    }

    public func stopUpdatingLocation() {
        manager.stopUpdatingLocation()
    }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
        AICaddieLog.location.debug("Location authorization changed: \(manager.authorizationStatus.rawValue, privacy: .public)")
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Previously dropped silently — a stalled GPS on the course left no trail.
        AICaddieLog.location.error("Location update failed: \(String(describing: error), privacy: .public)")
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else {
            return
        }
        latestFix = LocationFix(
            coordinate: location.coordinate,
            horizontalAccuracyM: location.horizontalAccuracy,
            altitudeM: location.verticalAccuracy >= 0 ? location.altitude : nil,
            capturedAt: formatter.string(from: location.timestamp)
        )
    }
}
