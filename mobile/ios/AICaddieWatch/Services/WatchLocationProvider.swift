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
    // watch P3 uitest: a MOVING route injected via UITEST_GPS_ROUTE ("lat,lon;lat,lon;…") — walked on a
    // timer, emitting fixes, bypassing CoreLocation + the permission dialog (like simulatedFix but
    // animated) so the live-GPS video shows "you" moving with zero simctl/permission dependency.
    private let routeWaypoints: [CLLocationCoordinate2D]
    private var routeTimer: Timer?
    private var routeStep = 0
    private let routeSteps = 42

    public init(manager: CLLocationManager = CLLocationManager()) {
        self.manager = manager
        let env = ProcessInfo.processInfo.environment
        if let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), let lon = Double(lonText) {
            self.simulatedFix = WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                capturedAt: ISO8601DateFormatter().string(from: Date()))
        } else {
            self.simulatedFix = nil
        }
        self.routeWaypoints = (env["UITEST_GPS_ROUTE"]).map { text in
            text.split(separator: ";").compactMap { pair -> CLLocationCoordinate2D? in
                let c = pair.split(separator: ",")
                guard c.count == 2, let lat = Double(c[0]), let lon = Double(c[1]) else { return nil }
                return CLLocationCoordinate2D(latitude: lat, longitude: lon)
            }
        } ?? []
        // Injected sources never touch the permission dialog.
        self.authorizationStatus = (simulatedFix != nil || routeWaypoints.count >= 2)
            ? .authorizedWhenInUse : manager.authorizationStatus
        super.init()
        self.manager.delegate = self
        self.manager.desiredAccuracy = kCLLocationAccuracyBest
        self.manager.distanceFilter = 3
        if let simulatedFix {
            self.latestFix = simulatedFix
        }
    }

    public func requestAuthorization() {
        if simulatedFix != nil || routeWaypoints.count >= 2 {
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
        if routeWaypoints.count >= 2 {
            emitRouteFix()
            routeTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
                self?.emitRouteFix()
            }
            return
        }
        manager.startUpdatingLocation()
    }

    /// Lerp along the injected route (first→last) by `routeStep/routeSteps`, emitting a fix each tick.
    private func emitRouteFix() {
        guard let a = routeWaypoints.first, let b = routeWaypoints.last else { return }
        let frac = min(1.0, Double(routeStep) / Double(routeSteps))
        let coord = CLLocationCoordinate2D(
            latitude: a.latitude + (b.latitude - a.latitude) * frac,
            longitude: a.longitude + (b.longitude - a.longitude) * frac)
        latestFix = WatchLocationFix(coordinate: coord, horizontalAccuracyM: 5,
                                     capturedAt: formatter.string(from: Date()))
        routeStep += 1
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
