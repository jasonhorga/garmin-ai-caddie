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

    /// UI-test GPS injection: when UITEST_GPS_LAT/LON are set in the process environment, the provider
    /// emits a fixed on-course fix instead of touching CoreLocation — so the simulator-driven XCUITest
    /// renders real green/last-shot distances deterministically (and skips the location-permission
    /// dialog entirely). Nil in every normal run, so production behaviour is unchanged.
    private let simulatedFix: LocationFix?

    public init(manager: CLLocationManager = CLLocationManager()) {
        self.manager = manager
        let env = ProcessInfo.processInfo.environment
        if let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), let lon = Double(lonText) {
            self.simulatedFix = LocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                altitudeM: env["UITEST_GPS_ALT"].flatMap(Double.init),
                capturedAt: ISO8601DateFormatter().string(from: Date())
            )
            self.authorizationStatus = .authorizedWhenInUse
        } else {
            self.simulatedFix = nil
            self.authorizationStatus = manager.authorizationStatus
        }
        super.init()
        self.manager.delegate = self
        self.manager.desiredAccuracy = kCLLocationAccuracyBest
        self.manager.distanceFilter = 3
        if let simulatedFix {
            self.latestFix = simulatedFix
        }
    }

    public func requestAuthorization() {
        if simulatedFix != nil {
            authorizationStatus = .authorizedWhenInUse
            return
        }
        manager.requestWhenInUseAuthorization()
    }

    public func startUpdatingLocation() {
        if let simulatedFix {
            latestFix = simulatedFix
            return
        }
        manager.startUpdatingLocation()
    }

    public func stopUpdatingLocation() {
        manager.stopUpdatingLocation()
    }

    #if DEBUG
    /// Move the deterministic simulator fix while a real multi-hole UI journey advances. The guard
    /// keeps this inert unless the process was launched with UITEST_GPS_LAT/LON; Release/TestFlight
    /// builds do not compile this entry point at all.
    public func moveSimulatedFixForUITest(latitude: Double, longitude: Double) {
        guard simulatedFix != nil,
              latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude) else { return }
        latestFix = LocationFix(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            horizontalAccuracyM: latestFix?.horizontalAccuracyM ?? 5,
            altitudeM: latestFix?.altitudeM,
            capturedAt: formatter.string(from: Date())
        )
    }
    #endif

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
