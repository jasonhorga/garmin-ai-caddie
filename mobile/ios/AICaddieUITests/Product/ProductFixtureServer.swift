import Foundation
import Network
import UIKit
import XCTest

/// One synthetic HTTP backend on port 9000, shared for the lifetime of this UI test process.
/// Mutable request state stays on `queue`; startup failure crosses queues under `startupLock`.
final class ProductFixtureServer: @unchecked Sendable {
    // Static initialization is lazy and runs once, including a cached startup failure.
    static let shared: Result<ProductFixtureServer, Error> = Result { try ProductFixtureServer() }

    struct State {
        var roundCount = 3
        var reviewHoles = 18
        var hasShots = true
        var includePutts = false
        var providerFailure = false
        var coverage = "ready"
    }
    private let queue = DispatchQueue(label: "product-native-fixture")
    private let listener: NWListener
    private var state = State()
    private var paths: [String] = []
    private let sourcePackage: [String: Any]
    /// A plain topo raster sized like the template overlay; served only while coverage is ready.
    private let topoPNG: Data
    private let startupSemaphore = DispatchSemaphore(value: 0)
    private let startupLock = NSLock()
    private var startupFailure: Error?

    struct Sample: Equatable {
        let window: String
        let roundIDs: [String]
    }
    private var samples: [Sample] = []

    private enum StartupFailure: Error {
        case timedOut
        case missingPort
    }

    var baseURL: URL {
        guard let port = listener.port else { preconditionFailure("fixture has no bound port") }
        return URL(string: "http://127.0.0.1:\(port.rawValue)")!
    }

    private init() throws {
        let fixture = try XCTUnwrap(Bundle(for: ProductPhoneUITests.self).url(forResource: "native_product", withExtension: "json"))
        let document = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as? [String: Any]
        var template = try XCTUnwrap(document?["package"] as? [String: Any])
        let hole = try XCTUnwrap((template["holes"] as? [[String: Any]])?.first)
        var coursePrep = try XCTUnwrap(template["coursePrep"] as? [String: Any])
        let prep = try XCTUnwrap((coursePrep["holes"] as? [[String: Any]])?.first)
        template["holes"] = (1...9).map { number -> [String: Any] in
            var row = hole; row["number"] = number; row["sourceLocalHole"] = number; row["courseHoleNumber"] = number; return row
        }
        coursePrep["holes"] = (1...9).map { number -> [String: Any] in
            var row = prep; row["hole"] = number; return row
        }
        template["coursePrep"] = coursePrep
        sourcePackage = template
        let overlay = (prep["map"] as? [String: Any])?["overlay"] as? [String: Any]
        let width = try XCTUnwrap((overlay?["w"] as? NSNumber)?.doubleValue)
        let height = try XCTUnwrap((overlay?["h"] as? NSNumber)?.doubleValue)
        let size = CGSize(width: width, height: height)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        topoPNG = UIGraphicsImageRenderer(size: size, format: format).pngData { context in
            UIColor(red: 0.25, green: 0.5, blue: 0.3, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
        let parameters = NWParameters.tcp
        parameters.allowLocalEndpointReuse = true
        listener = try NWListener(using: parameters, on: 9000)
        listener.stateUpdateHandler = { [weak self] value in
            guard let self else { return }
            switch value {
            case .ready:
                self.startupSemaphore.signal()
            case .failed(let error):
                self.startupLock.lock()
                self.startupFailure = error
                self.startupLock.unlock()
                self.startupSemaphore.signal()
            default: break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            guard let self else { connection.cancel(); return }
            connection.start(queue: self.queue)
            self.receive(connection, accumulated: Data())
        }
        listener.start(queue: queue)
        guard startupSemaphore.wait(timeout: .now() + 5) == .success else {
            listener.cancel()
            throw StartupFailure.timedOut
        }
        startupLock.lock()
        let failure = startupFailure
        startupLock.unlock()
        if let failure {
            listener.cancel()
            throw failure
        }
        guard listener.port != nil else {
            listener.cancel()
            throw StartupFailure.missingPort
        }
    }

    func configure(_ next: State) { queue.sync { state = next; paths = []; samples = [] } }
    func requestedPaths() -> [String] { queue.sync { paths } }
    func lastSample() -> Sample? { queue.sync { samples.last } }
    deinit { listener.cancel() }

    private func receive(_ connection: NWConnection, accumulated: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, complete, error in
            guard let self, error == nil else { connection.cancel(); return }
            var buffer = accumulated
            if let data { buffer.append(data) }
            guard let boundary = buffer.range(of: Data("\r\n\r\n".utf8)) else {
                if complete { connection.cancel() } else { self.receive(connection, accumulated: buffer) }
                return
            }
            let headers = String(decoding: buffer[..<boundary.lowerBound], as: UTF8.self)
            let length = headers.components(separatedBy: "\r\n").first { $0.lowercased().hasPrefix("content-length:") }
                .flatMap { Int($0.split(separator: ":", maxSplits: 1)[1].trimmingCharacters(in: .whitespaces)) } ?? 0
            guard buffer.count >= boundary.upperBound + length else {
                self.receive(connection, accumulated: buffer)
                return
            }
            let target = headers.components(separatedBy: "\r\n").first?.split(separator: " ").dropFirst().first.map(String.init) ?? "/"
            self.paths.append(target)
            let (code, object) = self.response(target)
            let body: Data
            let contentType: String
            if let raw = object as? Data {
                body = raw
                contentType = "image/png"
            } else {
                guard let json = try? JSONSerialization.data(withJSONObject: object) else { connection.cancel(); return }
                body = json
                contentType = "application/json"
            }
            var response = Data("HTTP/1.1 \(code) \(code == 200 ? "OK" : "Unavailable")\r\nContent-Type: \(contentType)\r\nContent-Length: \(body.count)\r\nConnection: close\r\n\r\n".utf8)
            response.append(body)
            connection.send(content: response, completion: .contentProcessed { _ in connection.cancel() })
        }
    }

    private func response(_ target: String) -> (Int, Any) {
        let components = URLComponents(string: "http://localhost\(target)")
        let path = components?.path ?? target
        let query = Dictionary((components?.queryItems ?? []).map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { a, _ in a })
        if path == "/api/v2/health" { return (200, ["status": "ok", "dataMode": "fixture"]) }
        if path == "/api/v2/mobile/courses/options" {
            // geometryCoverage and sourceRefs are required by MobileCourseOption; without them the
            // catalogue fails to decode and the DEBUG app activates its bundled fixture round instead.
            return (200, ["schema": "ai-caddie-course-options-v1", "dataMode": "fixture", "total": 1,
                "courses": [["globalId": 82001, "name": "Example", "holes": 9, "roundCount": 3, "teeBox": "blue",
                    "geometryCoverage": state.coverage, "sourceRefs": ["fixture-course:82001"]]],
                "generatedAt": "2026-10-23T00:00:00Z"])
        }
        // 开始一场 lists provider rows only (nearby with a fix, name search without one). The row has
        // no coordinates, so the home never treats the player as standing on this course.
        let match: [String: Any] = ["globalId": 82001, "name": "Example", "holes": 9, "ratio": 1.0]
        if path == "/api/v2/courses/nearby" {
            let radius = Int(Double(query["radius_km"] ?? "") ?? 50)
            return (200, ["schema": "ai-caddie-course-nearby-v1", "radiusKm": radius, "complete": true,
                "matches": [match], "courses": [match]])
        }
        if path == "/api/v2/courses/search" {
            let name = query["name"] ?? ""
            let matches = name.localizedCaseInsensitiveContains("example") ? [match] : []
            return (200, ["schema": "ai-caddie-course-search-v1", "query": name, "matches": matches, "courses": matches])
        }
        if path.hasSuffix("/topo.png") {
            // Partial and missing coverage have no raster; their revision differs (geometryRevision),
            // so the app's URL-keyed topo cache cannot carry the ready image into them.
            if state.coverage == "ready" { return (200, topoPNG) }
            return (404, ["error": "synthetic-unavailable"])
        }
        if path.hasSuffix("/package") {
            var package = sourcePackage
            let roundFromPath = path.hasPrefix("/api/v2/mobile/rounds/") ? path.split(separator: "/").dropLast().last.map(String.init) : nil
            let roundID = query["round_id"] ?? roundFromPath ?? "home-82001"
            package["roundId"] = roundID
            if var coverage = package["sourceCoverage"] as? [String: Any] {
                coverage["requestedRoundId"] = roundID
                package["sourceCoverage"] = coverage
            }
            package["coursePrep"] = configuredPrep()
            if var holes = package["holes"] as? [[String: Any]] {
                for i in holes.indices {
                    holes[i]["geometryCoverage"] = state.coverage
                    holes[i]["geometryRevision"] = geometryRevision
                }
                package["holes"] = holes
            }
            package["geometryCoverage"] = ["state": state.coverage,
                "readyHoles": state.coverage == "ready" ? 9 : 0, "totalHoles": 9]
            return (200, package)
        }
        if path == "/api/v2/history/stats/mobile" {
            let window = query["window"] ?? "all"
            let ids = (1...max(1, state.roundCount)).filter { $0 <= state.roundCount }
            let selected: [Int]
            switch window {
            case "last10": selected = Array(ids.suffix(10))
            case "last20": selected = Array(ids.suffix(20))
            default: selected = ids // All three synthetic dates fall inside the twelve-month sample.
            }
            samples.append(Sample(window: window, roundIDs: selected.map { "r\($0)" }))
            return (200, stats(roundIDs: selected))
        }
        if path == "/api/v2/history/rounds" {
            // Q2's hand-written sample is r1/r2; Q3 contains r3.
            let ids: [Int] = query["period"] == "2026-Q2" ? [2, 1] : Array((1...max(1, state.roundCount)).reversed()).filter { $0 <= state.roundCount }
            let groups: [[String: Any]] = ["2026-09", "2026-06"].compactMap { month in
                let members = ids.filter { ($0 == 3 ? "2026-09" : "2026-06") == month }
                return members.isEmpty ? nil : ["key": month, "label": month, "count": members.count, "rounds": members.map(card)]
            }
            return (200, ["total": ids.count, "groups": groups, "availableYears": ["2026"], "availableCourses": []])
        }
        if path.hasSuffix("/shotmap") {
            let hole = Int(path.split(separator: "/").dropLast().last ?? "1") ?? 1
            let prep = ((sourcePackage["coursePrep"] as? [String: Any])?["holes"] as? [[String: Any]])?.first ?? [:]
            let first: [String: Any] = ["id": "s\(hole)-1", "order": 1, "start": [100, 350],
                "end": [100, 200], "club": "7I", "endLie": "fairway"]
            let second: [String: Any] = ["id": "s\(hole)-2", "order": 2, "start": [100, 200],
                "end": [100, 16], "club": "6I", "endLie": "green"]
            let shots: [[String: Any]] = state.hasShots ? [first, second] : []
            let result: [String: Any] = ["found": true, "hole": hole, "par": 4, "globalId": 81001,
                "localHole": hole <= 9 ? hole + 9 : hole - 9, "geometryRevision": "native-r1",
                "mapKind": "prodgeometry", "map": prep["map"] ?? [:], "shots": shots,
                "manualPenalty": 0, "missingData": []]
            return (200, result)
        }
        if path.hasPrefix("/api/v2/history/rounds/") && !path.contains("/report") {
            let ref = path.split(separator: "/").last.map(String.init) ?? "r1"
            let index = Int(ref.dropFirst()) ?? 1
            let total = 78 + index * 2
            let pars = state.reviewHoles * 4
            let extra = total - pars
            let perHole = extra / state.reviewHoles
            let remainder = extra % state.reviewHoles
            let round: [String: Any] = ["courseName": "Example", "date": date(index), "score": total,
                "par": pars, "toPar": extra, "holesCompleted": state.reviewHoles]
            let scorecard: [[String: Any]] = (1...state.reviewHoles).map { n in
                let toPar = perHole + (n <= remainder ? 1 : 0)
                let putts: Any
                if state.includePutts { putts = 2 } else { putts = NSNull() }
                let refs: [String] = state.hasShots ? ["s\(n)-1", "s\(n)-2"] : []
                return ["hole": n, "par": 4, "score": 4 + toPar, "toPar": toPar, "putts": putts,
                    "localHole": n <= 9 ? n + 9 : n - 9, "globalId": 81001, "shotRefs": refs]
            }
            let detail: [String: Any] = ["roundRef": ref, "found": true, "round": round,
                "scorecard": scorecard, "phaseSummary": [], "missingData": []]
            return (200, detail)
        }
        if path.contains("report") || path.contains("caddie/decision") {
            return (state.providerFailure ? 503 : 404, ["error": "synthetic-provider-unavailable"])
        }
        if path.hasSuffix("/tees") { return (200, ["schema": "ai-caddie-course-tees-v1", "globalId": 82001, "tees": [["teeBox": "blue", "name": "blue", "holeCount": 9, "yards": 3285, "default": true]], "defaultTeeBox": "blue"]) }
        if path.hasSuffix("/prep") {
            var prep = configuredPrep()
            prep["holeCount"] = 9
            prep["clubs"] = []
            prep["missingData"] = []
            return (200, prep)
        }
        return (404, ["error": "synthetic-unavailable"])
    }

    /// The template revision while ready; other coverage states get their own revision.
    private var geometryRevision: String {
        state.coverage == "ready" ? "native-r1" : "native-r1-\(state.coverage)"
    }

    private func configuredPrep() -> [String: Any] {
        var prep = sourcePackage["coursePrep"] as? [String: Any] ?? [:]
        var holes = prep["holes"] as? [[String: Any]] ?? []
        for i in holes.indices {
            holes[i]["geometryCoverage"] = state.coverage
            holes[i]["geometryRevision"] = geometryRevision
            if state.coverage == "missing" {
                holes[i]["route"] = []
                for key in ["map", "holeImageProjection", "greenDistances", "greenOutline"] {
                    holes[i].removeValue(forKey: key)
                }
                holes[i]["hazards"] = [:]
            }
        }
        prep["holes"] = holes
        return prep
    }

    private func date(_ n: Int) -> String { n == 3 ? "2026-09-03" : "2026-06-0\(n)" }

    private func card(_ n: Int) -> [String: Any] {
        ["id": "r\(n)", "date": date(n), "courseName": "Example", "holesCompleted": 18,
         "score": 78 + n * 2, "par": 72, "toPar": 6 + n * 2, "globalId": 81001,
         "scoreStrip": [], "badges": []]
    }

    private func stats(roundIDs: [Int]) -> [String: Any] {
        let summary: [String: Any] = ["totalRounds": roundIDs.count, "eighteenHoleRounds": roundIDs.count,
            "recent10Average": 82, "bestScore": 80, "handicapEstimate": 10]
        let points: [[String: Any]] = roundIDs.map {
            ["roundId": "r\($0)", "date": date($0), "score": 78 + $0 * 2]
        }
        let q2: [String: Any] = ["key": "2026-Q2", "roundCount": 2, "eighteenHoleRounds": 2,
            "average18": 81, "bestScore": 80, "worstScore": 82, "roundIds": ["r1", "r2"]]
        let q3: [String: Any] = ["key": "2026-Q3", "roundCount": 1, "eighteenHoleRounds": 1,
            "average18": 84, "bestScore": 84, "worstScore": 84, "roundIds": ["r3"]]
        let time: [String: Any] = ["byMonth": [], "byYear": [], "byQuarter": [q2, q3]]
        let courseRound: [String: Any] = ["roundId": "r1", "date": "2026-06-01", "score": 80, "holesCompleted": 18]
        let course: [String: Any] = ["courseKey": "example", "courseName": "Example", "roundCount": 3,
            "average18": 82, "loopKeys": ["gid:81001:1-9", "gid:81001:10-18"], "nineOnlyRounds": 1,
            "rounds": [courseRound]]
        let frontHole: [String: Any] = ["hole": 1, "par": 4, "averageToPar": 1.5, "samples": 2]
        let backHole: [String: Any] = ["hole": 10, "par": 4, "averageToPar": 3, "samples": 1]
        let front: [String: Any] = ["loopKey": "gid:81001:1-9", "label": "1–9", "holes": [frontHole]]
        let back: [String: Any] = ["loopKey": "gid:81001:10-18", "label": "10–18", "holes": [backHole]]
        let frontBack: [String: Any] = ["frontKey": "gid:81001:1-9", "backKey": "gid:81001:10-18",
            "front": "1–9", "back": "10–18", "rounds": 2, "average": 81]
        let backFront: [String: Any] = ["frontKey": "gid:81001:10-18", "backKey": "gid:81001:1-9",
            "front": "10–18", "back": "1–9", "rounds": 1, "average": 84]
        let scoring: [String: Any] = ["loops": [front, back], "nineCombos": [frontBack, backFront]]
        return ["summary": summary, "trend": ["points": points], "time": time,
            "courses": [course], "scoring": scoring]
    }
}
