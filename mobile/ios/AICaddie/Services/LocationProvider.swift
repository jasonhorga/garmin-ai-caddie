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
    private var wantsLocationUpdates = false

    @Published public private(set) var latestFix: LocationFix?
    @Published public private(set) var authorizationStatus: CLAuthorizationStatus

    /// UI-test GPS injection: when UITEST_GPS_LAT/LON are set in the process environment, the provider
    /// emits a fixed on-course fix instead of touching CoreLocation — so the simulator-driven XCUITest
    /// renders real green/last-shot distances deterministically (and skips the location-permission
    /// dialog entirely). Nil in every normal run, so production behaviour is unchanged.
    private let simulatedFix: LocationFix?
    /// DEBUG-only permission override used by the real simulator journey to prove that denying GPS
    /// still leaves the explicit city/name search usable. It is never read in Release/TestFlight.
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
        let injectedFix: LocationFix?
        if forcedAuthorization == nil,
           let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), lat.isFinite, (-90...90).contains(lat),
           let lon = Double(lonText), lon.isFinite, (-180...180).contains(lon) {
            injectedFix = LocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                altitudeM: env["UITEST_GPS_ALT"].flatMap(Double.init),
                capturedAt: ISO8601DateFormatter().string(from: Date())
            )
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
        self.manager.distanceFilter = 3
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
    }

    public func stopUpdatingLocation() {
        wantsLocationUpdates = false
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
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            // The first start request commonly happens while permission is still `.notDetermined`.
            // Resume explicitly after the answer instead of leaving course discovery waiting forever.
            if wantsLocationUpdates {
                manager.startUpdatingLocation()
            }
        case .denied, .restricted:
            latestFix = nil
        case .notDetermined:
            break
        @unknown default:
            break
        }
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Previously dropped silently — a stalled GPS on the course left no trail.
        AICaddieLog.location.error("Location update failed: \(String(describing: error), privacy: .public)")
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        // Core Location may first replay an old cached or invalid fix. A stale city can be tens of
        // kilometres away and would make a healthy Garmin nearby query honestly return the wrong list.
        guard let location = Self.latestUsableLocation(in: locations) else {
            return
        }
        latestFix = LocationFix(
            coordinate: location.coordinate,
            horizontalAccuracyM: location.horizontalAccuracy,
            altitudeM: location.verticalAccuracy >= 0 ? location.altitude : nil,
            capturedAt: formatter.string(from: location.timestamp)
        )
    }

    /// Kept pure for boundary tests: Core Location commonly delivers an invalid/current pair or a
    /// valid cached fix followed by a stale one. Select the newest usable sample rather than blindly
    /// trusting the array's last element.
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
}
