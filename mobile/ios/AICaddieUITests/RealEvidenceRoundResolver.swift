import Foundation
#if canImport(UIKit)
import UIKit
#endif

struct RealEvidencePoint: Equatable {
    let x: Double
    let y: Double
}

struct RealEvidenceRound: Equatable {
    let roundRef: String
    let courseName: String
    let date: String?
    let score: Int?
    let hole: Int
    let globalId: Int
    let localHole: Int
    let clubs: [String]
    let shotCount: Int
    let landing: RealEvidencePoint
    let emptyMapPoint: RealEvidencePoint

    var diagnosticText: String {
        [
            "roundRef=\(roundRef)",
            "courseName=\(courseName)",
            "date=\(date ?? "-")",
            "score=\(score.map(String.init) ?? "-")",
            "hole=\(hole)",
            "globalId=\(globalId)",
            "localHole=\(localHole)",
            "clubs=\(clubs.joined(separator: ","))",
            "shotCount=\(shotCount)",
            "landing=\(landing.x),\(landing.y)",
            "emptyMapPoint=\(emptyMapPoint.x),\(emptyMapPoint.y)",
        ].joined(separator: "\n")
    }
}

enum RealEvidenceRoundResolverError: LocalizedError {
    case invalidBaseURL
    case timedOut(String)
    case transport(String)
    case status(Int, String)
    case malformed(String)
    case noEligibleRound

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "invalid evidence API base URL"
        case .timedOut(let path):
            return "evidence request timed out: \(path)"
        case .transport(let message):
            return "evidence request failed: \(message)"
        case .status(let code, let path):
            return "evidence request returned HTTP \(code): \(path)"
        case .malformed(let path):
            return "evidence response was malformed: \(path)"
        case .noEligibleRound:
            return "no real Garmin round has a scored hole with two club-labelled, spatially separated shots and usable geometry"
        }
    }
}

struct RealEvidenceRoundRejection: Equatable, CustomStringConvertible {
    let roundRef: String
    let hole: Int?
    let reason: String

    var description: String {
        "roundRef=\(roundRef) hole=\(hole.map(String.init) ?? \"-\") reason=\(reason)"
    }
}

/// Resolves live review evidence from the current owner history instead of treating one mutable
/// Garmin import id as a permanent fixture. Selection stays read-only and fail-closed: a candidate
/// must have a real scorecard row, a real topo/overlay, and two non-synthetic club-labelled landings
/// separated on that same hole.
final class RealEvidenceRoundResolver {
    private let baseURL: URL
    private let adminToken: String
    private let requestTimeout: TimeInterval
    private(set) var rejections: [RealEvidenceRoundRejection] = []

    var diagnosticsText: String {
        rejections.isEmpty ? "no candidate rejection recorded" : rejections.map(\.description).joined(separator: "\n")
    }

    init(baseURL: String, adminToken: String, requestTimeout: TimeInterval = 75) throws {
        guard let url = URL(string: baseURL), url.scheme != nil, url.host != nil else {
            throw RealEvidenceRoundResolverError.invalidBaseURL
        }
        self.baseURL = url
        self.adminToken = adminToken
        self.requestTimeout = requestTimeout
    }

    func resolve(preferredRoundRef: String? = nil) throws -> RealEvidenceRound {
        rejections.removeAll(keepingCapacity: true)
        let roundsRoot = try getJSON(
            path: "/api/v2/history/rounds",
            queryItems: [
                URLQueryItem(name: "hasShots", value: "true"),
                URLQueryItem(name: "limit", value: "120"),
            ]
        )
        guard let groups = roundsRoot["groups"] as? [[String: Any]] else {
            throw RealEvidenceRoundResolverError.malformed("/api/v2/history/rounds")
        }
        let allCards = groups
            .flatMap { ($0["rounds"] as? [[String: Any]]) ?? [] }
            // Manual rounds can contain simulator/test shots. Legacy cards with no source predate
            // the marker and are Garmin-backed, so reject only an explicit manual source here.
            .filter { nonEmptyString($0["source"])?.lowercased() != "manual" }
            .sorted(by: evidenceCardPrecedes)
        let requestedRef = preferredRoundRef?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cards = requestedRef.map { ref in
            allCards.filter { nonEmptyString($0["id"]) == ref }
        } ?? allCards

        var shotMapRequests = 0
        // This is a screenshot precondition, not a history crawler. Inspect a bounded recent set;
        // each round detail already exposes the per-hole shot refs needed to avoid probing every
        // shot-map endpoint in the owner's history.
        for card in cards.prefix(24) {
            guard let roundRef = nonEmptyString(card["id"]) else { continue }
            let encodedRef = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
            let detailPath = "/api/v2/history/rounds/\(encodedRef)"
            let detail = try getJSON(path: detailPath)
            guard detail["found"] as? Bool == true,
                  let scorecard = detail["scorecard"] as? [[String: Any]],
                  !scorecard.isEmpty else {
                record(roundRef, nil, "missing scored hole/detail")
                continue
            }

            // The detail payload already carries each hole's compact shot summaries, including
            // the recorded club. Use that cheap metadata before requesting a shot map. Merely
            // having two GPS refs is not enough for this evidence: older Garmin rounds often have
            // many positions whose club is Unknown. Probing those holes forced the backend to cold
            // render up to 18 topo images only to reject them afterwards, starving the real app
            // and other Watch clients sharing the service. The shot map remains the final authority
            // for geometry and spatial separation; this is only a truthful prefilter.
            let labelledShotCounts: [Int: Int] = ((detail["holeDetails"] as? [[String: Any]]) ?? [])
                .reduce(into: [:]) { counts, row in
                    guard let hole = integer(row["hole"]), hole > 0 else { return }
                    let count = ((row["shots"] as? [[String: Any]]) ?? []).reduce(into: 0) { total, shot in
                        guard let club = nonEmptyString(shot["club"]),
                              club.lowercased() != "unknown" else { return }
                        total += 1
                    }
                    counts[hole] = max(counts[hole] ?? 0, count)
                }

            let scoredHoles: [(hole: Int, globalId: Int?, localHole: Int?)] = scorecard.compactMap { row in
                // `shotCount` belongs to holeDetails, while scorecard rows expose `shotRefs`.
                // Reading a nonexistent scorecard field made every genuine hole look empty and
                // caused the resolver to crawl dozens of rounds before returning noEligibleRound.
                let shotCount = (row["shotRefs"] as? [Any])?.count ?? integer(row["shotCount"]) ?? 0
                guard let hole = integer(row["hole"]), hole > 0,
                      integer(row["score"]) != nil,
                      shotCount >= 2,
                      (labelledShotCounts[hole] ?? 0) >= 2 else {
                    return nil
                }
                return (hole, integer(row["globalId"]), integer(row["localHole"]))
            }
            var seenHoles = Set<Int>()
            let holes = scoredHoles
                .filter { seenHoles.insert($0.hole).inserted }
                .sorted { lhs, rhs in
                    if lhs.hole == rhs.hole { return false }
                    if lhs.hole == 1 { return true }
                    if rhs.hole == 1 { return false }
                    return lhs.hole < rhs.hole
                }

            if holes.isEmpty {
                record(roundRef, nil, scorecard.contains { integer($0["score"]) == nil }
                    ? "no scored hole with at least two club-labelled shots"
                    : "no scored hole met the two-shot club-label requirement")
            }

            for scoredHole in holes.prefix(18) {
                let hole = scoredHole.hole
                shotMapRequests += 1
                guard shotMapRequests <= 24 else {
                    record(roundRef, hole, "shot-map budget exhausted (24)")
                    throw RealEvidenceRoundResolverError.noEligibleRound
                }
                let shotMapPath = "\(detailPath)/holes/\(hole)/shotmap"
                let shotMap = try getJSON(path: shotMapPath)
                guard shotMap["found"] as? Bool == true,
                      let globalId = integer(shotMap["globalId"]), globalId > 0,
                      let localHole = integer(shotMap["localHole"]), localHole > 0,
                      scoredHole.globalId == nil || scoredHole.globalId == globalId,
                      scoredHole.localHole == nil || scoredHole.localHole == localHole,
                      let map = shotMap["map"] as? [String: Any],
                      let overlay = map["overlay"] as? [String: Any],
                      let width = number(overlay["w"]), width > 0,
                      let height = number(overlay["h"]), height > 0,
                      usableMapImage(map["image"], width: width, height: height),
                      let shots = shotMap["shots"] as? [[String: Any]] else {
                    record(roundRef, hole, "shotmap mismatch or missing geometry/image")
                    continue
                }

                let recorded = recordedLandings(shots)
                guard let pair = mostSeparatedPair(recorded),
                      pair.distance >= max(24, min(width, height) * 0.035) else {
                    record(roundRef, hole, recorded.count < 2
                        ? "fewer than two non-synthetic club-labelled landings"
                        : "club-labelled landings are not spatially separated")
                    continue
                }

                let allPoints = shots.compactMap(landingPoint)
                let landing = normalized(pair.first.point, width: width, height: height)
                return RealEvidenceRound(
                    roundRef: roundRef,
                    courseName: nonEmptyString(card["courseName"]) ?? "真实 Garmin 球局",
                    date: nonEmptyString(card["date"]),
                    score: integer(card["score"]),
                    hole: hole,
                    globalId: globalId,
                    localHole: localHole,
                    clubs: [pair.first.club, pair.second.club],
                    shotCount: shots.count,
                    landing: landing,
                    emptyMapPoint: farthestEmptyPoint(from: allPoints, width: width, height: height)
                )
            }
        }
        throw RealEvidenceRoundResolverError.noEligibleRound
    }

    private func record(_ roundRef: String, _ hole: Int?, _ reason: String) {
        rejections.append(RealEvidenceRoundRejection(roundRef: roundRef, hole: hole, reason: reason))
    }

    private func getJSON(
        path: String,
        queryItems: [URLQueryItem] = []
    ) throws -> [String: Any] {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw RealEvidenceRoundResolverError.invalidBaseURL
        }
        let basePath = components.path.hasSuffix("/")
            ? String(components.path.dropLast())
            : components.path
        components.path = basePath + path
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        guard let url = components.url else {
            throw RealEvidenceRoundResolverError.invalidBaseURL
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = requestTimeout
        request.setValue(adminToken, forHTTPHeaderField: "x-ai-caddie-admin-token")

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
            throw RealEvidenceRoundResolverError.timedOut(path)
        }
        if let responseError {
            throw RealEvidenceRoundResolverError.transport(responseError.localizedDescription)
        }
        guard responseCode == 200 else {
            throw RealEvidenceRoundResolverError.status(responseCode, path)
        }
        guard let responseData,
              let root = try JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
            throw RealEvidenceRoundResolverError.malformed(path)
        }
        return root
    }

    private func evidenceCardPrecedes(_ lhs: [String: Any], _ rhs: [String: Any]) -> Bool {
        let lhsSource = nonEmptyString(lhs["source"])
        let rhsSource = nonEmptyString(rhs["source"])
        let lhsRank = lhsSource == "garmin" ? 0 : (lhsSource == "manual" ? 2 : 1)
        let rhsRank = rhsSource == "garmin" ? 0 : (rhsSource == "manual" ? 2 : 1)
        if lhsRank != rhsRank { return lhsRank < rhsRank }

        let lhsHoles = integer(lhs["holesCompleted"]) ?? 0
        let rhsHoles = integer(rhs["holesCompleted"]) ?? 0
        if (lhsHoles >= 9) != (rhsHoles >= 9) { return lhsHoles >= 9 }
        return (nonEmptyString(lhs["date"]) ?? "") > (nonEmptyString(rhs["date"]) ?? "")
    }

    private struct RecordedLanding {
        let club: String
        let point: RealEvidencePoint
    }

    private func recordedLandings(_ shots: [[String: Any]]) -> [RecordedLanding] {
        shots.compactMap { shot in
            guard shot["synthetic"] as? Bool != true,
                  let club = nonEmptyString(shot["club"]),
                  club.lowercased() != "unknown",
                  let point = landingPoint(shot) else {
                return nil
            }
            return RecordedLanding(club: club, point: point)
        }
    }

    private func mostSeparatedPair(
        _ values: [RecordedLanding]
    ) -> (first: RecordedLanding, second: RecordedLanding, distance: Double)? {
        guard values.count >= 2 else { return nil }
        var best: (RecordedLanding, RecordedLanding, Double)?
        for firstIndex in values.indices {
            for secondIndex in values.indices where secondIndex > firstIndex {
                let first = values[firstIndex]
                let second = values[secondIndex]
                let distance = hypot(first.point.x - second.point.x, first.point.y - second.point.y)
                if best == nil || distance > best!.2 {
                    best = (first, second, distance)
                }
            }
        }
        return best.map { (first: $0.0, second: $0.1, distance: $0.2) }
    }

    private func landingPoint(_ shot: [String: Any]) -> RealEvidencePoint? {
        guard let end = shot["end"] as? [Any], end.count >= 2,
              let x = number(end[0]), let y = number(end[1]) else {
            return nil
        }
        return RealEvidencePoint(x: x, y: y)
    }

    private func normalized(
        _ point: RealEvidencePoint,
        width: Double,
        height: Double
    ) -> RealEvidencePoint {
        RealEvidencePoint(
            x: min(max(point.x / width, 0.02), 0.98),
            y: min(max(point.y / height, 0.02), 0.98)
        )
    }

    /// RoundShotMapView needs a decodable fallback bitmap before it can build the map at all, even
    /// when the realistic topo URL later succeeds. Prove this payload is a real raster in the exact
    /// overlay frame instead of accepting a non-empty or placeholder data URI.
    private func usableMapImage(_ value: Any?, width: Double, height: Double) -> Bool {
        guard let uri = nonEmptyString(value),
              uri.hasPrefix("data:image/"),
              let comma = uri.firstIndex(of: ","),
              uri[..<comma].contains(";base64"),
              let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])),
              data.count > 1_024 else {
            return false
        }
        #if canImport(UIKit)
        guard let image = UIImage(data: data), let raster = image.cgImage else { return false }
        return abs(Double(raster.width) - width) <= 1 && abs(Double(raster.height) - height) <= 1
        #else
        return true
        #endif
    }

    private func farthestEmptyPoint(
        from points: [RealEvidencePoint],
        width: Double,
        height: Double
    ) -> RealEvidencePoint {
        let candidates = [
            RealEvidencePoint(x: 0.12, y: 0.16),
            RealEvidencePoint(x: 0.88, y: 0.16),
            RealEvidencePoint(x: 0.12, y: 0.84),
            RealEvidencePoint(x: 0.88, y: 0.84),
            RealEvidencePoint(x: 0.50, y: 0.50),
            RealEvidencePoint(x: 0.22, y: 0.50),
            RealEvidencePoint(x: 0.78, y: 0.50),
        ]
        let normalizedPoints = points.map { normalized($0, width: width, height: height) }
        return candidates.max { lhs, rhs in
            minimumDistance(from: lhs, to: normalizedPoints)
                < minimumDistance(from: rhs, to: normalizedPoints)
        } ?? RealEvidencePoint(x: 0.12, y: 0.16)
    }

    private func minimumDistance(
        from point: RealEvidencePoint,
        to others: [RealEvidencePoint]
    ) -> Double {
        others.map { hypot(point.x - $0.x, point.y - $0.y) }.min() ?? 1
    }

    private func nonEmptyString(_ value: Any?) -> String? {
        guard let value = value as? String else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func integer(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String { return Int(value) }
        return nil
    }

    private func number(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? Int { return Double(value) }
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String { return Double(value) }
        return nil
    }
}
