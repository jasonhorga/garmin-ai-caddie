import Foundation

struct NewCourseEvidence: Equatable {
    let globalId: Int
    let name: String
    let holes: Int
    let searchQuery: String
    let radiusKm: Int

    var diagnosticText: String {
        [
            "globalId=\(globalId)",
            "name=\(name)",
            "holes=\(holes)",
            "searchQuery=\(searchQuery)",
            "radiusKm=\(radiusKm)",
        ].joined(separator: "\n")
    }
}

enum NewCourseEvidenceResolverError: LocalizedError {
    case invalidBaseURL
    case timedOut(String)
    case transport(String)
    case status(Int, String)
    case malformed(String)
    case noEligibleCourse

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "invalid new-course evidence API base URL"
        case .timedOut(let path):
            return "new-course evidence request timed out: \(path)"
        case .transport(let message):
            return "new-course evidence request failed: \(message)"
        case .status(let code, let path):
            return "new-course evidence returned HTTP \(code): \(path)"
        case .malformed(let path):
            return "new-course evidence response was malformed: \(path)"
        case .noEligibleCourse:
            return "no nearby, uninstalled 9/18-hole course has a searchable name and missing hole-1 precise geometry"
        }
    }
}

/// Chooses one real provider-catalogue course for the empty-cache journey. It is intentionally
/// read-only: the resolver proves that the row is nearby, absent from the player's installed/options
/// roster, searchable by name, and still missing precise hole-1 geometry. The app itself must then
/// select the row, fetch its Tee/package, show the lightweight map, and trigger the precise upgrade.
final class NewCourseEvidenceResolver {
    private let baseURL: URL
    private let adminToken: String
    private let latitude: Double
    private let longitude: Double
    private let requestTimeout: TimeInterval
    private let radiusKm = 200

    init(
        baseURL: String,
        adminToken: String,
        latitude: Double,
        longitude: Double,
        requestTimeout: TimeInterval = 75
    ) throws {
        guard let url = URL(string: baseURL), url.scheme != nil, url.host != nil,
              latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude) else {
            throw NewCourseEvidenceResolverError.invalidBaseURL
        }
        self.baseURL = url
        self.adminToken = adminToken
        self.latitude = latitude
        self.longitude = longitude
        self.requestTimeout = requestTimeout
    }

    func resolve() throws -> NewCourseEvidence {
        let optionsPath = "/api/v2/mobile/courses/options"
        let optionsRoot = try getJSON(path: optionsPath)
        guard let optionRows = optionsRoot["courses"] as? [[String: Any]] else {
            throw NewCourseEvidenceResolverError.malformed(optionsPath)
        }
        let installedIds = Set(optionRows.compactMap { integer($0["globalId"]) })

        let nearbyPath = "/api/v2/courses/nearby"
        let nearbyRoot = try getJSON(
            path: nearbyPath,
            queryItems: [
                URLQueryItem(name: "latitude", value: String(latitude)),
                URLQueryItem(name: "longitude", value: String(longitude)),
                URLQueryItem(name: "radius_km", value: String(radiusKm)),
            ]
        )
        guard let matches = nearbyRoot["matches"] as? [[String: Any]] else {
            throw NewCourseEvidenceResolverError.malformed(nearbyPath)
        }

        // This is a journey precondition, not a provider crawler. The nearest bounded set is enough
        // to find an honest empty-cache candidate without turning one UI run into a catalogue scan.
        for match in matches.prefix(40) {
            guard let globalId = integer(match["globalId"]), globalId > 0,
                  !installedIds.contains(globalId),
                  let holes = integer(match["holes"]), holes == 9 || holes == 18,
                  let name = nonEmptyString(match["name"]) else {
                continue
            }
            let coverage = try getJSON(
                path: "/api/v2/geometry/course/\(globalId)/coverage",
                queryItems: [URLQueryItem(name: "holes", value: "1")]
            )
            guard nonEmptyString(coverage["coverage"])?.lowercased() == "missing" else {
                continue
            }
            guard let query = try verifiedSearchQuery(for: name, globalId: globalId) else {
                continue
            }
            return NewCourseEvidence(
                globalId: globalId,
                name: name,
                holes: holes,
                searchQuery: query,
                radiusKm: radiusKm
            )
        }
        throw NewCourseEvidenceResolverError.noEligibleCourse
    }

    private func verifiedSearchQuery(for name: String, globalId: Int) throws -> String? {
        for query in searchQueries(for: name) {
            let root = try getJSON(
                path: "/api/v2/courses/search",
                queryItems: [
                    URLQueryItem(name: "name", value: query),
                    URLQueryItem(name: "latitude", value: String(latitude)),
                    URLQueryItem(name: "longitude", value: String(longitude)),
                ]
            )
            guard let rows = root["matches"] as? [[String: Any]] else {
                throw NewCourseEvidenceResolverError.malformed("/api/v2/courses/search")
            }
            if rows.prefix(24).contains(where: { integer($0["globalId"]) == globalId }) {
                return query
            }
        }
        return nil
    }

    /// Prefer a full ASCII name (reliable simulator keyboard input), then distinctive long tokens.
    private func searchQueries(for name: String) -> [String] {
        var values: [String] = []
        if name.unicodeScalars.allSatisfy(\.isASCII), name.count >= 2 {
            values.append(name)
        }
        let tokens = name.components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { token in
                token.count >= 4 && token.unicodeScalars.contains {
                    CharacterSet.letters.contains($0) && $0.isASCII
                }
            }
            .sorted { $0.count > $1.count }
        values.append(contentsOf: tokens)
        var seen = Set<String>()
        return values.filter { seen.insert($0.lowercased()).inserted }
    }

    private func getJSON(path: String, queryItems: [URLQueryItem] = []) throws -> [String: Any] {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw NewCourseEvidenceResolverError.invalidBaseURL
        }
        let basePath = components.path.hasSuffix("/")
            ? String(components.path.dropLast())
            : components.path
        components.path = basePath + path
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        guard let url = components.url else {
            throw NewCourseEvidenceResolverError.invalidBaseURL
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = requestTimeout
        if !adminToken.isEmpty {
            request.setValue(adminToken, forHTTPHeaderField: "x-ai-caddie-admin-token")
        }

        let semaphore = DispatchSemaphore(value: 0)
        var responseData: Data?
        var responseCode = -1
        var responseError: Error?
        URLSession.shared.dataTask(with: request) { data, response, error in
            responseData = data
            responseCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            responseError = error
            semaphore.signal()
        }.resume()

        guard semaphore.wait(timeout: .now() + requestTimeout + 5) == .success else {
            throw NewCourseEvidenceResolverError.timedOut(path)
        }
        if let responseError {
            throw NewCourseEvidenceResolverError.transport(responseError.localizedDescription)
        }
        guard responseCode == 200 else {
            throw NewCourseEvidenceResolverError.status(responseCode, path)
        }
        guard let responseData,
              let root = try JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
            throw NewCourseEvidenceResolverError.malformed(path)
        }
        return root
    }

    private func integer(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String { return Int(value) }
        return nil
    }

    private func nonEmptyString(_ value: Any?) -> String? {
        guard let value = value as? String else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
