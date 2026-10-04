import Foundation

/// 首页「今天」天气磁贴: the current conditions at the player (or the course), from
/// `GET /api/v2/weather/snapshot?source=open_meteo` (a read; nothing is stored).
public struct HomeWeather: Decodable, Equatable {
    public let state: String
    public let temperatureC: Double?
    public let windSpeedMps: Double?
    public let windDirectionDeg: Int?
    public let condition: String?
    public let precipitationProbabilityPct: Int?

    public init(
        state: String = "ready",
        temperatureC: Double?,
        windSpeedMps: Double?,
        windDirectionDeg: Int?,
        condition: String?,
        precipitationProbabilityPct: Int?
    ) {
        self.state = state
        self.temperatureC = temperatureC
        self.windSpeedMps = windSpeedMps
        self.windDirectionDeg = windDirectionDeg
        self.condition = condition
        self.precipitationProbabilityPct = precipitationProbabilityPct
    }

    /// Nil unless the provider answered with at least a temperature.
    public var presentation: HomeWeatherPresentation? {
        guard state == "ready", let temperatureC, temperatureC.isFinite else { return nil }
        return HomeWeatherPresentation(
            temperatureText: "\(Int(temperatureC.rounded()))°",
            conditionText: Self.conditionText(condition),
            symbolName: Self.symbolName(condition),
            windText: Self.windText(speedMps: windSpeedMps, directionDeg: windDirectionDeg),
            rainText: Self.rainText(precipitationProbabilityPct)
        )
    }

    static func conditionText(_ condition: String?) -> String? {
        switch condition {
        case "clear": return "晴"
        case "partly_cloudy": return "多云"
        case "overcast": return "阴"
        case "fog": return "雾"
        case "drizzle": return "毛毛雨"
        case "rain": return "雨"
        case "snow": return "雪"
        case "thunderstorm": return "雷雨"
        default: return nil
        }
    }

    static func symbolName(_ condition: String?) -> String {
        switch condition {
        case "clear": return "sun.max"
        case "partly_cloudy": return "cloud.sun"
        case "overcast": return "cloud"
        case "fog": return "cloud.fog"
        case "drizzle": return "cloud.drizzle"
        case "rain": return "cloud.rain"
        case "snow": return "cloud.snow"
        case "thunderstorm": return "cloud.bolt.rain"
        default: return "thermometer.medium"
        }
    }

    /// "西北风 3 m/s · 2 级"; below 1.6 m/s (force 1) the direction means little: "微风".
    static func windText(speedMps: Double?, directionDeg: Int?) -> String? {
        guard let speedMps, speedMps.isFinite, speedMps >= 0 else { return nil }
        let force = beaufortForce(speedMps)
        let speed = "\(Int(speedMps.rounded())) m/s"
        guard force >= 2, let directionDeg else { return "微风 \(speed)" }
        return "\(windDirectionName(directionDeg))风 \(speed) · \(force) 级"
    }

    /// Meteorological direction (where the wind blows FROM), eight points.
    static func windDirectionName(_ degrees: Int) -> String {
        let names = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        let normalised = ((degrees % 360) + 360) % 360
        return names[Int((Double(normalised) / 45).rounded()) % 8]
    }

    /// Beaufort force from the upper bound of each band (m/s).
    static func beaufortForce(_ speedMps: Double) -> Int {
        let upperBounds: [Double] = [0.2, 1.5, 3.3, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6]
        return upperBounds.firstIndex { speedMps <= $0 } ?? 12
    }

    /// "降雨 70% · 带伞" from 50 % on.
    static func rainText(_ percent: Int?) -> String? {
        guard let percent, (0...100).contains(percent) else { return nil }
        return percent >= 50 ? "降雨 \(percent)% · 带伞" : "降雨 \(percent)%"
    }
}

public struct HomeWeatherPresentation: Equatable {
    public let temperatureText: String
    public let conditionText: String?
    public let symbolName: String
    public let windText: String?
    public let rainText: String?
}

enum HomeWeatherClient {
    /// One best-effort read; any failure leaves the tile in its quiet "暂无天气" state.
    static func fetch(
        baseURL: URL,
        adminToken: String?,
        latitude: Double,
        longitude: Double,
        session: URLSession = .shared
    ) async -> HomeWeather? {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              var components = URLComponents(
                  url: baseURL.appendingPathComponent("api/v2/weather/snapshot"),
                  resolvingAgainstBaseURL: false
              ) else { return nil }
        components.queryItems = [
            URLQueryItem(name: "source", value: "open_meteo"),
            URLQueryItem(name: "latitude", value: String(latitude)),
            URLQueryItem(name: "longitude", value: String(longitude)),
        ]
        guard let url = components.url else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        applyAICaddieAuth(to: &request, adminToken: adminToken)
        guard let (data, response) = try? await session.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(HomeWeather.self, from: data)
    }
}
