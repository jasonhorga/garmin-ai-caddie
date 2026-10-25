import Foundation

/// B6 洞结束触发 (README §3, IMPLEMENTATION_PLAN B6): a hole is over once the player has been on its
/// green and then walked more than 25 m off the green toward the next tee. (The other trigger, the
/// next hole's first shot, is the model's next-tee shot path.) Pure and fed one GPS fix at a time, so
/// it is tested against recorded tracks; coarse fixes are ignored rather than guessed through.
public struct WatchHoleEndDetector: Equatable {
    public struct Green: Equatable {
        public let latitude: Double
        public let longitude: Double
        /// Half the green's depth, never under `minimumGreenRadiusM`.
        public let radiusM: Double

        public init(latitude: Double, longitude: Double, radiusM: Double) {
            self.latitude = latitude
            self.longitude = longitude
            self.radiusM = max(WatchHoleEndDetector.minimumGreenRadiusM, radiusM)
        }
    }

    public struct Point: Equatable {
        public let latitude: Double
        public let longitude: Double

        public init(latitude: Double, longitude: Double) {
            self.latitude = latitude
            self.longitude = longitude
        }
    }

    /// Off the green's edge by more than this.
    public static let leaveGreenM = 25.0
    /// And this much closer to the next tee than when last on the green.
    public static let towardNextTeeM = 10.0
    public static let minimumGreenRadiusM = 10.0
    /// Fixes coarser than this neither put the player on the green nor end the hole.
    public static let maximumAccuracyM = 20.0

    public let green: Green
    public let nextTee: Point?
    public private(set) var reachedGreen = false
    public private(set) var ended = false
    /// Distance to the next tee at the last fix on the green.
    private var nextTeeAtGreenM: Double?

    public init(green: Green, nextTee: Point?) {
        self.green = green
        self.nextTee = nextTee
    }

    /// Feed one fix; true exactly once, on the fix that ends the hole.
    public mutating func observe(latitude: Double, longitude: Double, horizontalAccuracyM: Double) -> Bool {
        guard !ended, horizontalAccuracyM.isFinite, horizontalAccuracyM >= 0,
              horizontalAccuracyM <= Self.maximumAccuracyM else { return false }
        let fromCenter = WatchGeoMath.metres(latitude, longitude, green.latitude, green.longitude)
        let toNextTee = nextTee.map { WatchGeoMath.metres(latitude, longitude, $0.latitude, $0.longitude) }
        if fromCenter <= green.radiusM + min(horizontalAccuracyM, 10) {
            reachedGreen = true
            nextTeeAtGreenM = toNextTee
            return false
        }
        guard reachedGreen, fromCenter - green.radiusM > Self.leaveGreenM else { return false }
        if let toNextTee, let atGreen = nextTeeAtGreenM, toNextTee > atGreen - Self.towardNextTeeM {
            return false
        }
        ended = true
        return true
    }
}

extension WatchHoleEndDetector.Green {
    /// The green of a hole state: its centre, and half the front–back depth when both edges are known.
    public init?(hole: WatchRoundState) {
        guard let lat = hole.centerGreenLat, let lon = hole.centerGreenLon else { return nil }
        var radius = WatchHoleEndDetector.minimumGreenRadiusM
        if let fLat = hole.frontGreenLat, let fLon = hole.frontGreenLon,
           let bLat = hole.backGreenLat, let bLon = hole.backGreenLon {
            radius = WatchGeoMath.metres(fLat, fLon, bLat, bLon) / 2
        }
        self.init(latitude: lat, longitude: lon, radiusM: radius)
    }
}
