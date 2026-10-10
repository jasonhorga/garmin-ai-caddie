import Combine
import CoreLocation
import Foundation
import os

public struct WatchLocationFix: Equatable {
    public let coordinate: CLLocationCoordinate2D
    public let horizontalAccuracyM: Double
    public let capturedAt: String
    /// Core Location ground speed and its accuracy; nil when the fix carries none (negative values).
    public var speedMps: Double? = nil
    public var speedAccuracyMps: Double? = nil

    public static func == (lhs: WatchLocationFix, rhs: WatchLocationFix) -> Bool {
        lhs.coordinate.latitude == rhs.coordinate.latitude
            && lhs.coordinate.longitude == rhs.coordinate.longitude
            && lhs.horizontalAccuracyM == rhs.horizontalAccuracyM
            && lhs.capturedAt == rhs.capturedAt
    }
}

/// A calibrated Core Location heading fact. Pin direction uses true north only; magnetic-only or
/// invalid samples remain unavailable because a plausible-looking wrong arrow is worse than no arrow.
public struct WatchHeadingFix: Equatable {
    public let trueDegrees: Double
    public let accuracyDegrees: Double
    public let capturedAt: Date

    public init(trueDegrees: Double, accuracyDegrees: Double, capturedAt: Date) {
        self.trueDegrees = trueDegrees
        self.accuracyDegrees = accuracyDegrees
        self.capturedAt = capturedAt
    }
}

/// watch P3: the watch's OWN GPS (CLLocationManager on watchOS), mirroring the phone `LocationProvider`.
/// Lets the hole view recompute you/green distances from the wrist without the phone — the base for
/// standalone play. The round-scoped HKWorkoutSession owned by WatchAutoShotProvider keeps these
/// updates eligible while the display sleeps; AutoShot motion itself can remain disabled.
/// `UITEST_GPS_LAT/LON` inject a fixed on-course fix (deterministic snapshots + no permission dialog), nil
/// in every normal run so production behaviour is unchanged.
public final class WatchLocationProvider: NSObject, ObservableObject, CLLocationManagerDelegate {
    public static let maximumLiveRangefinderAgeSeconds: TimeInterval = 15

    private let manager: CLLocationManager
    private let formatter = ISO8601DateFormatter()
    private let log = Logger(subsystem: "com.aicaddie.watch", category: "location")
    private var wantsLocationUpdates = false
    /// Only the 旗向指引 page reads the heading. Every published heading re-renders the whole round
    /// UI (map canvas included), and with a 2° filter the wrist moving through a round published
    /// constantly (battery report 2026-10-10), so heading runs only while that page is open.
    private(set) var wantsHeadingUpdates = false
    private var lastPublishedFixAt: Date?

    @Published public private(set) var latestFix: WatchLocationFix?
    @Published public private(set) var latestHeading: WatchHeadingFix?
    @Published public private(set) var authorizationStatus: CLAuthorizationStatus

    private let simulatedFix: WatchLocationFix?
    private let simulatedAuthorizationStatus: CLAuthorizationStatus?

    public init(manager: CLLocationManager = CLLocationManager()) {
        self.manager = manager
        let env = ProcessInfo.processInfo.environment
        #if DEBUG
        let forcedAuthorization: CLAuthorizationStatus? = {
            switch env["UITEST_LOCATION_AUTHORIZATION"]?.lowercased() {
            case "denied": return .denied
            case "restricted": return .restricted
            case "authorized", "authorizedwheninuse": return .authorizedWhenInUse
            default: return nil
            }
        }()
        #else
        let forcedAuthorization: CLAuthorizationStatus? = nil
        #endif
        let injectedFix: WatchLocationFix?
        if forcedAuthorization == nil,
           let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), lat.isFinite, (-90...90).contains(lat),
           let lon = Double(lonText), lon.isFinite, (-180...180).contains(lon) {
            injectedFix = WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                capturedAt: ISO8601DateFormatter().string(from: Date()))
        } else {
            injectedFix = nil
        }
        self.simulatedFix = injectedFix
        self.simulatedAuthorizationStatus = forcedAuthorization
        self.authorizationStatus = forcedAuthorization
            ?? (injectedFix == nil ? manager.authorizationStatus : .authorizedWhenInUse)
        super.init()
        self.manager.delegate = self
        self.manager.desiredAccuracy = kCLLocationAccuracyBest
        // Every fix, not only after a move: a player standing at the ball or on the tee got no
        // callback under a 3 m filter, the last fix aged past the 15 s rangefinder window, and
        // F/M/B fell back to 999 "等待定位" until they walked again (field report 2026-10-10).
        // The round's workout session keeps GPS on anyway; this only adds the callbacks.
        self.manager.distanceFilter = kCLDistanceFilterNone
        self.manager.headingFilter = 2
        if let simulatedFix {
            self.latestFix = simulatedFix
        }
    }

    public func requestAuthorization() {
        if let simulatedAuthorizationStatus {
            authorizationStatus = simulatedAuthorizationStatus
            return
        }
        if simulatedFix != nil {
            authorizationStatus = .authorizedWhenInUse
            return
        }
        manager.requestWhenInUseAuthorization()
    }

    public func startUpdatingLocation() {
        wantsLocationUpdates = true
        if simulatedAuthorizationStatus != nil {
            return
        }
        if let simulatedFix {
            latestFix = simulatedFix
            return
        }
        manager.startUpdatingLocation()
        if wantsHeadingUpdates, CLLocationManager.headingAvailable() {
            manager.startUpdatingHeading()
        }
    }

    public func stopUpdatingLocation() {
        wantsLocationUpdates = false
        manager.stopUpdatingLocation()
        manager.stopUpdatingHeading()
    }

    /// Heading only while a view that shows it is open (and location is wanted at all).
    public func setHeadingUpdates(_ wanted: Bool) {
        guard wanted != wantsHeadingUpdates else { return }
        wantsHeadingUpdates = wanted
        guard simulatedAuthorizationStatus == nil, simulatedFix == nil else { return }
        if wanted, wantsLocationUpdates, CLLocationManager.headingAvailable() {
            manager.startUpdatingHeading()
        } else if !wanted {
            manager.stopUpdatingHeading()
            latestHeading = nil
        }
    }

    /// Every fix arrives (no distance filter), but republishing an unchanged position each second
    /// redraws the whole round UI. Publish a move of 2 m, an accuracy change of 3 m, a ground-speed
    /// or speed-accuracy change of 1 m/s (a cart stopping must reach the swing riding gate), or at
    /// least every `stationaryRepublishSeconds` — inside both the 15 s rangefinder window and the
    /// 10 s swing-speed window — so a player standing still keeps a live range and a usable speed
    /// without a redraw per fix.
    public static let stationaryRepublishSeconds: TimeInterval = 5

    static func shouldPublish(
        previous: WatchLocationFix?,
        previousPublishedAt: Date?,
        next: CLLocation,
        now: Date = Date()
    ) -> Bool {
        guard let previous, let previousPublishedAt else { return true }
        let moved = CLLocation(
            latitude: previous.coordinate.latitude,
            longitude: previous.coordinate.longitude
        ).distance(from: next)
        return moved >= 2
            || abs(next.horizontalAccuracy - previous.horizontalAccuracyM) >= 3
            || changed(previous.speedMps, next.speed, by: 1)
            || changed(previous.speedAccuracyMps, next.speedAccuracy, by: 1)
            || now.timeIntervalSince(previousPublishedAt) >= stationaryRepublishSeconds
    }

    /// Core Location marks a missing speed (or its accuracy) with a negative value.
    private static func changed(_ previous: Double?, _ raw: Double, by threshold: Double) -> Bool {
        let next: Double? = raw >= 0 ? raw : nil
        switch (previous, next) {
        case let (previous?, next?): return abs(next - previous) >= threshold
        case (nil, nil): return false
        default: return true
        }
    }

    /// Hole-root F/M/B is a live rangefinder, not a generic cached-location consumer. Keep the
    /// provider's longer Core Location acceptance window for continuity, but never label an old fix
    /// as the player's current distance.
    public static func isLiveRangefinderFix(
        _ fix: WatchLocationFix,
        now: Date = Date()
    ) -> Bool {
        guard fix.coordinate.latitude.isFinite,
              (-90...90).contains(fix.coordinate.latitude),
              fix.coordinate.longitude.isFinite,
              (-180...180).contains(fix.coordinate.longitude),
              fix.horizontalAccuracyM.isFinite,
              (0...15).contains(fix.horizontalAccuracyM),
              let capturedAt = ISO8601DateFormatter().date(from: fix.capturedAt) else {
            return false
        }
        let age = now.timeIntervalSince(capturedAt)
        return age >= 0 && age <= maximumLiveRangefinderAgeSeconds
    }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if let simulatedAuthorizationStatus {
            authorizationStatus = simulatedAuthorizationStatus
            if simulatedAuthorizationStatus == .denied || simulatedAuthorizationStatus == .restricted {
                latestFix = nil
                latestHeading = nil
            }
            return
        }
        authorizationStatus = manager.authorizationStatus
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            // startUpdatingLocation is normally called while permission is still undetermined.
            // Resume both wrist location and heading immediately after the player grants access.
            if wantsLocationUpdates {
                manager.startUpdatingLocation()
                if wantsHeadingUpdates, CLLocationManager.headingAvailable() {
                    manager.startUpdatingHeading()
                }
            }
        case .denied, .restricted:
            latestFix = nil
            latestHeading = nil
            manager.stopUpdatingLocation()
            manager.stopUpdatingHeading()
        case .notDetermined:
            break
        @unknown default:
            break
        }
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        log.error("watch location update failed: \(String(describing: error), privacy: .public)")
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = Self.latestUsableLocation(in: locations) else { return }
        let now = Date()
        guard Self.shouldPublish(previous: latestFix, previousPublishedAt: lastPublishedFixAt, next: location, now: now) else {
            return
        }
        lastPublishedFixAt = now
        latestFix = WatchLocationFix(
            coordinate: location.coordinate,
            horizontalAccuracyM: location.horizontalAccuracy,
            capturedAt: formatter.string(from: location.timestamp),
            speedMps: location.speed >= 0 ? location.speed : nil,
            speedAccuracyMps: location.speedAccuracy >= 0 ? location.speedAccuracy : nil)
    }

    static func latestUsableLocation(
        in locations: [CLLocation],
        now: Date = Date()
    ) -> CLLocation? {
        locations.last { isUsable($0, now: now) }
    }

    static func isUsable(_ location: CLLocation, now: Date = Date()) -> Bool {
        CLLocationCoordinate2DIsValid(location.coordinate)
            && location.coordinate.latitude.isFinite
            && location.coordinate.longitude.isFinite
            && location.horizontalAccuracy.isFinite
            && location.horizontalAccuracy >= 0
            && abs(location.timestamp.timeIntervalSince(now)) <= 300
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        guard newHeading.trueHeading.isFinite,
              (0..<360).contains(newHeading.trueHeading),
              newHeading.headingAccuracy.isFinite,
              newHeading.headingAccuracy >= 0 else {
            latestHeading = nil
            return
        }
        latestHeading = WatchHeadingFix(
            trueDegrees: newHeading.trueHeading,
            accuracyDegrees: newHeading.headingAccuracy,
            capturedAt: newHeading.timestamp
        )
    }
}
