import Combine
import CoreLocation
import Foundation

public struct LocationFix {
    public let coordinate: CLLocationCoordinate2D
    public let horizontalAccuracyM: Double
    public let altitudeM: Double?
    public let capturedAt: String
}

public struct MonitoredCourseRegion: Equatable, Sendable {
    public let identifier: String
    public let latitude: Double
    public let longitude: Double
    public let radiusM: Double

    public init(identifier: String, latitude: Double, longitude: Double, radiusM: Double) {
        self.identifier = identifier
        self.latitude = latitude
        self.longitude = longitude
        self.radiusM = radiusM
    }
}

public final class LocationProvider: NSObject, ObservableObject, CLLocationManagerDelegate {
    private static let monitoredRegionsKey = "aicaddie.course-regions.v1"
    private static let pendingRegionEntryKey = "aicaddie.pending-region-entry.v1"
    private static let pendingRegionEntryAtKey = "aicaddie.pending-region-entry-at.v1"
    private static let pendingRegionEntryNotifiedKey = "aicaddie.pending-region-entry-notified.v1"
    private static let pendingRegionEntryNotifiedAtKey = "aicaddie.pending-region-entry-notified-at.v1"
    private static let pendingRegionEntryMaxAge: TimeInterval = 10 * 60
    private let manager: CLLocationManager
    private let formatter = LocationProvider.makeCaptureFormatter()

    private static func makeCaptureFormatter() -> ISO8601DateFormatter {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }
    private var wantsLocationUpdates = false

    @Published public private(set) var latestFix: LocationFix?
    @Published public private(set) var enteredRegionIdentifier: String?
    @Published public private(set) var authorizationStatus: CLAuthorizationStatus
    public var onRegionEntered: ((String) -> Void)?

    /// UI-test GPS injection: when UITEST_GPS_LAT/LON are set in the process environment, the provider
    /// emits a fixed on-course fix instead of touching CoreLocation — so the simulator-driven XCUITest
    /// renders real green/last-shot distances deterministically (and skips the location-permission
    /// dialog entirely). Nil in every normal run, so production behaviour is unchanged.
    private let simulatedFix: LocationFix?
    /// DEBUG-only permission override used by the real simulator journey to prove that denying GPS
    /// still leaves the explicit city/name search usable. It is never read in Release/TestFlight.
    private let simulatedAuthorizationStatus: CLAuthorizationStatus?
    /// True only for `fixedFix` (snapshot fixtures), never for the UI-test environment fix.
    private let isFixtureFix: Bool

    /// `fixedFix`: a deterministic, already-authorised fix for in-process fixtures (snapshot
    /// tests); nil in the app, which reads CoreLocation (or the UI-test environment below).
    public init(manager: CLLocationManager = CLLocationManager(), fixedFix: LocationFix? = nil) {
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
        if let fixedFix {
            injectedFix = fixedFix
        } else if forcedAuthorization == nil,
           let latText = env["UITEST_GPS_LAT"], let lonText = env["UITEST_GPS_LON"],
           let lat = Double(latText), lat.isFinite, (-90...90).contains(lat),
           let lon = Double(lonText), lon.isFinite, (-180...180).contains(lon) {
            injectedFix = LocationFix(
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                horizontalAccuracyM: 5,
                altitudeM: env["UITEST_GPS_ALT"].flatMap(Double.init),
                capturedAt: Self.makeCaptureFormatter().string(from: Date())
            )
        } else {
            injectedFix = nil
        }
        self.simulatedFix = injectedFix
        self.isFixtureFix = fixedFix != nil
        self.simulatedAuthorizationStatus = forcedAuthorization
        self.authorizationStatus = forcedAuthorization
            ?? (injectedFix == nil ? manager.authorizationStatus : .authorizedWhenInUse)
        super.init()
        self.manager.delegate = self
        self.manager.desiredAccuracy = kCLLocationAccuracyBest
        self.manager.distanceFilter = 3
        self.manager.pausesLocationUpdatesAutomatically = true
        if let simulatedFix {
            self.latestFix = simulatedFix
        }
        restorePersistedCourseRegions()
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

    /// Region entry is the low-power background wake-up used by automatic round preparation.
    /// Always authorization is requested only once a caller has installed course regions.
    public func requestAlwaysAuthorizationForRegions() {
        guard simulatedAuthorizationStatus == nil, simulatedFix == nil else { return }
        manager.requestAlwaysAuthorization()
    }

    public func monitorCourseRegions(_ regions: [MonitoredCourseRegion]) {
        if regions.isEmpty {
            UserDefaults.standard.removeObject(forKey: Self.monitoredRegionsKey)
        } else {
            UserDefaults.standard.set(regions.map { [
                "identifier": $0.identifier,
                "latitude": $0.latitude,
                "longitude": $0.longitude,
                "radiusM": $0.radiusM,
            ] }, forKey: Self.monitoredRegionsKey)
        }
        let wanted = Set(regions.map(\.identifier))
        for monitored in manager.monitoredRegions where !wanted.contains(monitored.identifier) {
            manager.stopMonitoring(for: monitored)
        }
        for region in regions {
            guard CLLocationCoordinate2DIsValid(CLLocationCoordinate2D(
                latitude: region.latitude, longitude: region.longitude
            )) else { continue }
            let circular = CLCircularRegion(
                center: CLLocationCoordinate2D(latitude: region.latitude, longitude: region.longitude),
                radius: min(max(region.radiusM, 100), 1_500),
                identifier: region.identifier
            )
            circular.notifyOnEntry = true
            circular.notifyOnExit = false
            manager.startMonitoring(for: circular)
        }
        if !regions.isEmpty {
            requestAlwaysAuthorizationForRegions()
        }
    }

    /// A terminated app may receive a region callback before SwiftUI has rebuilt its scene. Keep
    /// the identifier until the model has restored the account and can act on the matching course.
    public func consumePendingRegionEntry() -> String? {
        defer { clearPendingRegionEntry() }
        return freshPendingRegionEntry()
    }

    public func peekPendingRegionEntry() -> String? {
        freshPendingRegionEntry()
    }

    public func clearPendingRegionEntry() {
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryKey)
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryAtKey)
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryNotifiedKey)
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryNotifiedAtKey)
    }

    /// Mark the current persisted entry after its automatic prep notification has been delivered.
    /// The marker is tied to the entry timestamp, so a later arrival at the same course is a new
    /// notification even when the old identifier is reused.
    public static func markPendingRegionEntryNotified(_ identifier: String) {
        guard UserDefaults.standard.string(forKey: pendingRegionEntryKey) == identifier,
              let capturedAt = UserDefaults.standard.object(forKey: pendingRegionEntryAtKey) as? Date else {
            return
        }
        UserDefaults.standard.set(identifier, forKey: pendingRegionEntryNotifiedKey)
        UserDefaults.standard.set(capturedAt, forKey: pendingRegionEntryNotifiedAtKey)
    }

    public static func isPendingRegionEntryNotified(_ identifier: String) -> Bool {
        guard UserDefaults.standard.string(forKey: pendingRegionEntryKey) == identifier,
              UserDefaults.standard.string(forKey: pendingRegionEntryNotifiedKey) == identifier,
              let capturedAt = UserDefaults.standard.object(forKey: pendingRegionEntryAtKey) as? Date,
              let notifiedAt = UserDefaults.standard.object(forKey: pendingRegionEntryNotifiedAtKey) as? Date else {
            return false
        }
        return capturedAt == notifiedAt
    }

    public func acknowledgeRegionEntry(_ identifier: String) {
        // The persisted value is the cross-launch authority. A stale publisher callback must not
        // clear a newer region entry that another provider has already stored.
        guard freshPendingRegionEntryValue() == identifier else { return }
        enteredRegionIdentifier = nil
        clearPendingRegionEntry()
    }

    private func freshPendingRegionEntry(now: Date = Date()) -> String? {
        guard let value = UserDefaults.standard.string(forKey: Self.pendingRegionEntryKey),
              let capturedAt = UserDefaults.standard.object(forKey: Self.pendingRegionEntryAtKey) as? Date,
              now.timeIntervalSince(capturedAt) >= 0,
              now.timeIntervalSince(capturedAt) <= Self.pendingRegionEntryMaxAge else {
            if let value = UserDefaults.standard.string(forKey: Self.pendingRegionEntryKey),
               enteredRegionIdentifier == value {
                enteredRegionIdentifier = nil
            }
            if UserDefaults.standard.object(forKey: Self.pendingRegionEntryKey) != nil {
                clearPendingRegionEntry()
            }
            return nil
        }
        return value
    }

    public func freshEnteredRegionIdentifier() -> String? {
        guard let identifier = enteredRegionIdentifier,
              freshPendingRegionEntryValue() == identifier else { return nil }
        return identifier
    }

    /// Validate the value emitted by `enteredRegionIdentifier` without reading the published
    /// property again. Combine may deliver the value before the property's backing storage is
    /// updated, so observers must validate the emitted identifier they already received.
    public func isFreshEnteredRegionIdentifier(_ identifier: String) -> Bool {
        freshPendingRegionEntryValue() == identifier
    }

    /// Clear an expired or rejected emitted entry after the publisher callback has returned.
    public func clearRegionEntry(_ identifier: String) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.enteredRegionIdentifier == identifier else { return }
            if let pending = UserDefaults.standard.string(forKey: Self.pendingRegionEntryKey),
               pending != identifier {
                return
            }
            self.enteredRegionIdentifier = nil
            self.clearPendingRegionEntry()
        }
    }

    /// Read the persisted region entry without changing either published property. Callers that
    /// observe `enteredRegionIdentifier` must keep this validation side-effect free; an expired
    /// value can be acknowledged/cleared afterwards on the normal event path.
    private func freshPendingRegionEntryValue(now: Date = Date()) -> String? {
        guard let value = UserDefaults.standard.string(forKey: Self.pendingRegionEntryKey),
              let capturedAt = UserDefaults.standard.object(forKey: Self.pendingRegionEntryAtKey) as? Date,
              now.timeIntervalSince(capturedAt) >= 0,
              now.timeIntervalSince(capturedAt) <= Self.pendingRegionEntryMaxAge else {
            return nil
        }
        return value
    }

    public func setBackgroundUpdatesEnabled(_ enabled: Bool) {
        manager.allowsBackgroundLocationUpdates = enabled
        manager.pausesLocationUpdatesAutomatically = !enabled
        if enabled && wantsLocationUpdates {
            manager.startUpdatingLocation()
        }
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

    public func locationManager(_ manager: CLLocationManager, didEnterRegion region: CLRegion) {
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryNotifiedKey)
        UserDefaults.standard.removeObject(forKey: Self.pendingRegionEntryNotifiedAtKey)
        UserDefaults.standard.set(region.identifier, forKey: Self.pendingRegionEntryKey)
        UserDefaults.standard.set(Date(), forKey: Self.pendingRegionEntryAtKey)
        // Persist first: Combine can deliver the @Published value before the property's backing
        // storage is visible to observers, and those observers must still find a fresh timestamp.
        enteredRegionIdentifier = region.identifier
        onRegionEntered?(region.identifier)
    }

    private func restorePersistedCourseRegions() {
        guard let rows = UserDefaults.standard.array(forKey: Self.monitoredRegionsKey) as? [[String: Any]] else {
            return
        }
        let regions = rows.compactMap { row -> MonitoredCourseRegion? in
            guard let identifier = row["identifier"] as? String,
                  let latitude = row["latitude"] as? Double,
                  let longitude = row["longitude"] as? Double,
                  let radiusM = row["radiusM"] as? Double else { return nil }
            return MonitoredCourseRegion(
                identifier: identifier, latitude: latitude, longitude: longitude, radiusM: radiusM
            )
        }
        for region in regions {
            let circular = CLCircularRegion(
                center: CLLocationCoordinate2D(latitude: region.latitude, longitude: region.longitude),
                radius: min(max(region.radiusM, 100), 1_500),
                identifier: region.identifier
            )
            circular.notifyOnEntry = true
            circular.notifyOnExit = false
            manager.startMonitoring(for: circular)
        }
    }

    #if DEBUG
    /// Install a deterministic fix for in-process product tests. Production builds do not expose
    /// mutation of the provider's latest fix.
    public func setFixForTesting(_ fix: LocationFix?) {
        latestFix = fix
    }

    /// Move the deterministic simulator fix while a real multi-hole UI journey advances. The guard
    /// keeps this inert unless the process was launched with UITEST_GPS_LAT/LON; Release/TestFlight
    /// builds do not compile this entry point at all.
    @discardableResult
    public func moveSimulatedFixForUITest(latitude: Double, longitude: Double) -> LocationFix? {
        guard simulatedFix != nil,
              latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude) else { return nil }
        let movedFix = LocationFix(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            horizontalAccuracyM: latestFix?.horizontalAccuracyM ?? 5,
            altitudeM: latestFix?.altitudeM,
            capturedAt: formatter.string(from: Date())
        )
        latestFix = movedFix
        return movedFix
    }
    #endif

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        // Core Location can deliver its real simulator/device callback after a DEBUG journey has
        // installed a deterministic permission override. Letting that callback replace the forced
        // denial with `.notDetermined` left the product spinner running forever and hid the manual
        // city/name fallback that the test is meant to exercise.
        if let simulatedAuthorizationStatus {
            authorizationStatus = simulatedAuthorizationStatus
            if simulatedAuthorizationStatus == .denied || simulatedAuthorizationStatus == .restricted {
                latestFix = nil
            }
            return
        }
        // An in-process fixture fix is already authorised; the test host's real CoreLocation
        // answer must not replace it or clear the fix. (The UI-test environment fix keeps the
        // simulator's real authorisation callback, which its journeys are written against.)
        if isFixtureFix {
            authorizationStatus = .authorizedWhenInUse
            return
        }
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
