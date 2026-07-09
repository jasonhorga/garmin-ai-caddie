import Combine
import CoreLocation
import Foundation
import os

public struct WatchLocationFix: Equatable {
    public let coordinate: CLLocationCoordinate2D
    public let horizontalAccuracyM: Double
    public let capturedAt: String

    public static func == (lhs: WatchLocationFix, rhs: WatchLocationFix) -> Bool {
        lhs.coordinate.latitude == rhs.coordinate.latitude
            && lhs.coordinate.longitude == rhs.coordinate.longitude
            && lhs.horizontalAccuracyM == rhs.horizontalAccuracyM
            && lhs.capturedAt == rhs.capturedAt
    }
}

/// watch P3: the watch's OWN GPS (CLLocationManager on watchOS), mirroring the phone `LocationProvider`.
/// Lets the hole view recompute you/green distances from the wrist without the phone — the base for
/// standalone play. Foreground here; the keep-alive HKWorkoutSession (background / always-on) is a follow-up.
/// `UITEST_GPS_LAT/LON` inject a fixed on-course fix (deterministic snapshots + no permission dialog), nil
/// in every normal run so production behaviour is unchanged.
public final class WatchLocationProvider: NSObject, ObservableObject, CLLocationManagerDelegate {
    private let manager: CLLocationManager
    private let formatter = ISO8601DateFormatter()
    private let log = Logger(subsystem: "com.aicaddie.watch", category: "location")

    @Published public private(set) var latestFix: WatchLocationFix?
    @Published public private(set) var authorizationStatus: CLAuthorizationStatus

    private let simulatedFix: WatchLocationFix?

    public init(manager: CLLocationManager = CLLocationManager()) {
        self.manager = manager
        let env = ProcessInfo.processInfo.environment
        if let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), let lon = Double(lonText) {
            self.simulatedFix = WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                capturedAt: ISO8601DateFormatter().string(from: Date()))
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

    public func stopUpdatingLocation() { manager.stopUpdatingLocation() }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        log.error("watch location update failed: \(String(describing: error), privacy: .public)")
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        latestFix = WatchLocationFix(
            coordinate: location.coordinate,
            horizontalAccuracyM: location.horizontalAccuracy,
            capturedAt: formatter.string(from: location.timestamp))
    }
}
