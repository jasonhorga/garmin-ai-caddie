#if !SWIFT_PACKAGE
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Network
import XCTest
@testable import AICaddie

private enum LiveRoundAppModelTestFailure: Error {
    case directorySync
    case loopbackServerStart(String)
    case loopbackServerTimeout
}

private final class LoopbackHTTPServer: @unchecked Sendable {
    private struct Request {
        let path: String
        let body: Data
    }

    private let listener: NWListener
    private let queue = DispatchQueue(label: "ai-caddie-tests.loopback-http")
    private let handler: (String, Data) -> (Int, Data)
    private let startupSemaphore = DispatchSemaphore(value: 0)
    private let startupLock = NSLock()
    private var startupFailure: Error?

    init(handler: @escaping (String, Data) -> (Int, Data)) throws {
        self.handler = handler
        self.listener = try NWListener(using: .tcp, on: .any)
        listener.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                startupSemaphore.signal()
            case .failed(let error):
                startupLock.lock()
                startupFailure = LiveRoundAppModelTestFailure.loopbackServerStart(
                    String(describing: error)
                )
                startupLock.unlock()
                startupSemaphore.signal()
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.accept(connection)
        }
        listener.start(queue: queue)
        guard startupSemaphore.wait(timeout: .now() + 5) == .success else {
            listener.cancel()
            throw LiveRoundAppModelTestFailure.loopbackServerTimeout
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
            throw LiveRoundAppModelTestFailure.loopbackServerStart("missing bound port")
        }
    }

    var baseURL: URL {
        guard let port = listener.port,
              let url = URL(string: "http://127.0.0.1:\(port.rawValue)")
        else {
            preconditionFailure("loopback listener lost its bound port")
        }
        return url
    }

    func stop() {
        listener.cancel()
    }

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(on: connection, accumulated: Data())
    }

    private func receive(on connection: NWConnection, accumulated: Data) {
        connection.receive(
            minimumIncompleteLength: 1,
            maximumLength: 64 * 1024
        ) { [weak self] data, _, isComplete, error in
            guard let self else {
                connection.cancel()
                return
            }
            var received = accumulated
            if let data {
                received.append(data)
            }
            if let request = parseRequest(received) {
                let response = handler(request.path, request.body)
                send(status: response.0, body: response.1, on: connection)
                return
            }
            if isComplete || error != nil || received.count > 1_048_576 {
                connection.cancel()
                return
            }
            receive(on: connection, accumulated: received)
        }
    }

    private func parseRequest(_ data: Data) -> Request? {
        let separator = Data("\r\n\r\n".utf8)
        guard let headerRange = data.range(of: separator),
              let header = String(data: data[..<headerRange.lowerBound], encoding: .utf8)
        else {
            return nil
        }
        let lines = header.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else { return nil }
        let requestParts = requestLine.split(separator: " ", omittingEmptySubsequences: true)
        guard requestParts.count >= 2 else { return nil }
        let contentLength = lines.dropFirst().compactMap { line -> Int? in
            let fields = line.split(separator: ":", maxSplits: 1).map(String.init)
            guard fields.count == 2,
                  fields[0].trimmingCharacters(in: .whitespacesAndNewlines)
                    .caseInsensitiveCompare("Content-Length") == .orderedSame
            else {
                return nil
            }
            return Int(fields[1].trimmingCharacters(in: .whitespacesAndNewlines))
        }.first ?? 0
        let bodyStart = headerRange.upperBound
        let bodyEnd = bodyStart + contentLength
        guard data.count >= bodyEnd else { return nil }
        return Request(
            path: String(requestParts[1]),
            body: data.subdata(in: bodyStart..<bodyEnd)
        )
    }

    private func send(status: Int, body: Data, on connection: NWConnection) {
        let reason: String
        switch status {
        case 200: reason = "OK"
        case 404: reason = "Not Found"
        default: reason = "Service Unavailable"
        }
        var response = Data(
            """
            HTTP/1.1 \(status) \(reason)\r
            Content-Type: application/json\r
            Content-Length: \(body.count)\r
            Connection: close\r
            \r

            """.utf8
        )
        response.append(body)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}

private func capturedRequestBodyData(from request: URLRequest) throws -> Data {
    if let body = request.httpBody {
        return body
    }
    guard let stream = request.httpBodyStream else {
        throw URLError(.zeroByteResource)
    }
    stream.open()
    defer { stream.close() }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 1024)
    while stream.hasBytesAvailable {
        let readCount = stream.read(&buffer, maxLength: buffer.count)
        if readCount < 0 {
            throw stream.streamError ?? URLError(.cannotDecodeContentData)
        }
        if readCount == 0 {
            break
        }
        data.append(buffer, count: readCount)
    }
    return data
}

@MainActor
final class LiveRoundAppModelTests: XCTestCase {
    func testReadyForegroundPrepIsDurablePreservesOtherHolesAndRenumbersCompositeBackNine() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()
        let frontSourceHole = try XCTUnwrap(source.holes.first)
        let factualPrep = try JSONDecoder().decode(
            CoursePrepResponse.self,
            from: offlinePrepResponseData(
                for: source,
                localHoles: [frontSourceHole.sourceLocalHole ?? frontSourceHole.number]
            )
        ).holes[0]
        let partialPrep = try JSONDecoder().decode(
            CoursePrepResponse.self,
            from: offlinePrepResponseData(
                for: source,
                localHoles: [frontSourceHole.sourceLocalHole ?? frontSourceHole.number],
                geometryCoverage: "partial"
            )
        ).holes[0]
        let compositeHoles = [
            Hole(
                number: 9,
                par: 4,
                yards: 390,
                geometryCoverage: .ready,
                sourceGlobalId: source.course.globalId,
                sourceLocalHole: 9
            ),
            Hole(
                number: 10,
                par: factualPrep.par,
                yards: factualPrep.blueYards,
                geometryCoverage: .ready,
                sourceGlobalId: source.course.globalId + 1,
                sourceLocalHole: factualPrep.hole
            ),
        ]
        let round = package(
            source,
            roundId: "foreground-prep-retention",
            recentRounds: [],
            holes: compositeHoles
        ).replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: source.course.globalId,
            holes: [factualPrep.renumbered(to: 9)],
            missingData: [CoursePrepMissingData(label: "offline_course_prep", reason: "1/2 retained")]
        ))
        try store.saveRoundPackage(round)
        try store.saveActiveHole(roundId: round.roundId, hole: 10)

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: 503,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                Data(#"{"detail":"offline"}"#.utf8)
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: round.roundId,
            syncClient: SyncClient(
                baseURL: URL(string: "https://offline.example.test")!,
                session: session,
                retrySleep: { _ in }
            )
        )
        await model.bootstrap()

        XCTAssertTrue(model.retainReadyHolePrep(
            roundId: round.roundId,
            roundHole: 10,
            prep: factualPrep
        ))
        XCTAssertEqual(model.package?.coursePrep?.holes.map(\.hole), [9, 10])
        XCTAssertEqual(model.package?.coursePrep?.holes.first(where: { $0.hole == 9 }), factualPrep.renumbered(to: 9))
        XCTAssertEqual(model.package?.coursePrep?.holes.first(where: { $0.hole == 10 }), factualPrep.renumbered(to: 10))

        let resumed = try XCTUnwrap(store.loadResumablePackage())
        XCTAssertEqual(resumed.roundId, round.roundId)
        XCTAssertEqual(resumed.coursePrep?.holes.map(\.hole), [9, 10])
        XCTAssertEqual(resumed.coursePrep?.holes.first(where: { $0.hole == 10 })?.geometryCoverage, "ready")

        XCTAssertFalse(model.retainReadyHolePrep(
            roundId: "a-later-round",
            roundHole: 10,
            prep: factualPrep
        ), "a late callback from another round must not overwrite the active package")
        XCTAssertFalse(model.retainReadyHolePrep(
            roundId: round.roundId,
            roundHole: 9,
            prep: partialPrep
        ), "partial geometry must not replace a retained precise hole")
        XCTAssertEqual(
            try store.loadResumablePackage()?.coursePrep?.holes.first(where: { $0.hole == 9 })?.geometryCoverage,
            "ready"
        )
    }

    func testPrepareCourseRoundEntersDownloadedTemplateBeforeRevalidatingInBackground() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let template = try offlineReadyPackage(localFixturePackage())
        try store.saveCourseTemplate(template)
        _ = try store.saveCourseTopoImage(
            minimalPNGData(),
            globalId: template.course.globalId,
            localHole: template.holes[0].sourceLocalHole ?? template.holes[0].number
        )

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestCount = 0
        CapturingURLProtocol.requestHandler = { request in
            requestLock.withLock {
                requestCount += 1
            }
            return (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: 503,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                Data(#"{"detail":"offline"}"#.utf8)
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: URL(string: "https://offline.example.test")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: client.baseURL,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: client
        )

        XCTAssertEqual(model.downloadedCourseOptions.map(\.globalId), [template.course.globalId])
        await model.prepareCourseRound(
            globalId: template.course.globalId,
            roundId: "offline-new-round",
            teeBox: template.course.teeBox,
            nine: template.nine ?? "all"
        )

        XCTAssertEqual(model.package?.roundId, "offline-new-round")
        XCTAssertEqual(model.package?.course, template.course)
        XCTAssertEqual(model.liveRoundState?.roundId, "offline-new-round")
        XCTAssertEqual(model.pendingLiveHole, template.holes.first?.number)
        XCTAssertEqual(try store.loadRoundPackage(roundId: "offline-new-round")?.roundId, "offline-new-round")
        XCTAssertTrue(try store.loadPendingEvents(roundId: "offline-new-round").isEmpty)
        XCTAssertEqual(
            requestLock.withLock { requestCount },
            0,
            "release verification must not start before SwiftUI has committed the first live hole"
        )
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()
        XCTAssertGreaterThan(
            requestLock.withLock { requestCount },
            0,
            "the first live-hole appearance must release Garmin revision verification"
        )
    }

    func testMatchingCourseRevisionReusesPrepAndTopoAfterBackgroundRevalidation() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()
        let revision = "aaaaaaaaaaaaaaaa"
        let revisedHoles = source.holes.map { hole in
            Hole(
                number: hole.number,
                par: hole.par,
                yards: hole.yards,
                geometryCoverage: .ready,
                geometryRevision: revision,
                sourceGlobalId: hole.sourceGlobalId,
                sourceLocalHole: hole.sourceLocalHole,
                teeLatitude: hole.teeLatitude,
                teeLongitude: hole.teeLongitude
            )
        }
        let revisedSource = package(
            source,
            roundId: source.roundId,
            recentRounds: source.recentHistory.rounds,
            holes: revisedHoles
        )
        let selectedDisplayName = "Nicklaus Club Beijing"
        let template = try offlineReadyPackage(
            revisedSource,
            geometryRevision: revision
        ).replacingCourseDisplayName(selectedDisplayName)
        try store.saveCourseTemplate(template)
        for hole in template.holes {
            _ = try store.saveCourseTopoImage(
                minimalPNGData(),
                globalId: hole.sourceGlobalId ?? template.course.globalId,
                localHole: hole.sourceLocalHole ?? hole.number,
                geometryRevision: revision
            )
        }
        let roundId = "matching-revision-round"
        let remote = package(
            template,
            roundId: roundId,
            recentRounds: template.recentHistory.rounds,
            holes: template.holes
        ).replacingCourseDisplayName("北京尼克劳斯俱乐部")
        let remoteData = try JSONEncoder().encode(remote)
        let requestLock = NSLock()
        var paths: [String] = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            requestLock.withLock { paths.append(url.path) }
            if url.path.contains("/api/v2/mobile/courses/") {
                return (
                    HTTPURLResponse(
                        url: url,
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    remoteData
                )
            }
            return (
                HTTPURLResponse(
                    url: url,
                    statusCode: 500,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                Data(#"{"detail":"unexpected"}"#.utf8)
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: URL(string: "https://revision.example.test")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: client.baseURL,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [0]
        )

        await model.prepareCourseRound(
            globalId: template.course.globalId,
            roundId: roundId,
            teeBox: template.course.teeBox,
            nine: template.nine ?? "all"
        )
        XCTAssertEqual(model.liveRoundState?.roundId, roundId)
        XCTAssertTrue(requestLock.withLock { paths }.isEmpty)
        model.liveHoleInitialLoadDidFinish()
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()

        let requested = requestLock.withLock { paths }
        XCTAssertEqual(
            requested.filter { $0.contains("/api/v2/mobile/courses/") }.count,
            1
        )
        XCTAssertFalse(requested.contains { $0.hasSuffix("/prep") })
        XCTAssertFalse(requested.contains { $0.hasSuffix("/topo.png") })
        XCTAssertTrue(store.hasCourseTopoImages(for: try XCTUnwrap(model.package)))
        XCTAssertEqual(model.package?.course.name, selectedDisplayName)
        XCTAssertEqual(
            try store.loadRoundPackage(roundId: roundId)?.course.name,
            selectedDisplayName,
            "release revalidation must not replace the catalogue label selected by the player"
        )
    }

    func testOnlineCourseStartRetainsAllHolePrepAndTopoForLaterOfflineUse() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()
        let holes = (1...7).map { number in
            Hole(
                number: number,
                par: number % 3 == 0 ? 3 : 4,
                yards: 320 + number * 10,
                geometryCoverage: .ready,
                sourceGlobalId: source.course.globalId,
                sourceLocalHole: number
            )
        }
        let online = package(
            source,
            roundId: "online-new-round",
            recentRounds: source.recentHistory.rounds,
            holes: holes
        ).replacingCoursePrep(nil)
        let packageData = try JSONEncoder().encode(online)
        let png = minimalPNGData()

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedURLs: [URL] = []
        var topoRequestCount = 0
        var firstTopoWasDurableBeforeSecondRequest: Bool?
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            requestLock.withLock {
                requestedURLs.append(url)
            }
            let body: Data
            let contentType: String
            switch url.path {
            case let path where path.contains("/api/v2/mobile/courses/"):
                body = packageData
                contentType = "application/json"
            case let path where path.hasSuffix("/prep"):
                let requested = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
                    .filter { $0.name == "holes" }
                    .compactMap { $0.value.flatMap(Int.init) } ?? []
                body = try self.offlinePrepResponseData(for: online, localHoles: requested)
                contentType = "application/json"
            case let path where path.hasSuffix("/topo.png"):
                let isSecondTopo = requestLock.withLock {
                    topoRequestCount += 1
                    return topoRequestCount == 2
                }
                if isSecondTopo {
                    let firstHole = try XCTUnwrap(online.holes.first)
                    let durable = store.loadCourseTopoImageURL(
                        globalId: firstHole.sourceGlobalId ?? online.course.globalId,
                        localHole: firstHole.sourceLocalHole ?? firstHole.number
                    ) != nil
                    requestLock.withLock {
                        firstTopoWasDurableBeforeSecondRequest = durable
                    }
                }
                body = png
                contentType = "image/png"
            default:
                body = Data(#"{"queued":true}"#.utf8)
                contentType = "application/json"
            }
            return (
                HTTPURLResponse(
                    url: url,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: ["Content-Type": contentType]
                )!,
                body
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: URL(string: "https://cache.example.test")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: client.baseURL,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: client
        )
        let selectedDisplayName = "Nicklaus Club Beijing"
        model.rememberSelectedCourseDisplayName(
            globalId: online.course.globalId,
            name: selectedDisplayName
        )

        await model.prepareCourseRound(
            globalId: online.course.globalId,
            roundId: online.roundId,
            teeBox: online.course.teeBox,
            nine: online.nine ?? "all"
        )

        let beforeAppearance = requestLock.withLock { requestedURLs }
        XCTAssertEqual(
            beforeAppearance.filter { $0.path.contains("/api/v2/mobile/courses/") }.count,
            1,
            "round preparation may fetch only the selected package before entering live play"
        )
        XCTAssertFalse(beforeAppearance.contains { $0.path.hasSuffix("/prep") })
        XCTAssertFalse(beforeAppearance.contains { $0.path.hasSuffix("/topo.png") })
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()

        XCTAssertEqual(model.downloadedCourseOptions.map(\.globalId), [online.course.globalId])
        XCTAssertEqual(model.package?.course.name, selectedDisplayName)
        XCTAssertEqual(
            try store.loadRoundPackage(roundId: online.roundId)?.course.name,
            selectedDisplayName,
            "the selected catalogue identity must already be durable before the first relaunch"
        )
        XCTAssertTrue(model.package?.hasCompleteOfflineCoursePrep == true)
        XCTAssertTrue(store.hasCourseTopoImages(for: try XCTUnwrap(model.package)))
        XCTAssertEqual(
            requestLock.withLock { firstTopoWasDurableBeforeSecondRequest },
            true,
            "each cold topo must be persisted before the background downloader asks for the next hole"
        )
        XCTAssertNotNil(try store.loadCourseTemplate(
            globalId: online.course.globalId,
            teeBox: online.course.teeBox,
            nine: online.nine ?? "all"
        )?.coursePrep)
        let urls = requestLock.withLock { requestedURLs }
        let paths = urls.map(\.path)
        XCTAssertFalse(
            paths.contains("/api/v2/courses/\(online.course.globalId)/topo/prewarm"),
            "the complete offline download must not compete with a duplicate server-wide prewarm"
        )
        XCTAssertEqual(
            paths.filter { $0.hasSuffix("/topo.png") }.count,
            online.holes.count,
            "every drawable hole must be fetched exactly once on the successful path"
        )
        let prepHoleBatches = urls.filter { $0.path.hasSuffix("/prep") }.map { url in
            URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
                .filter { $0.name == "holes" }
                .compactMap { $0.value.flatMap(Int.init) } ?? []
        }
        XCTAssertTrue(prepHoleBatches.contains([online.holes[0].number]))
        XCTAssertTrue(prepHoleBatches.allSatisfy { (1...3).contains($0.count) })
        XCTAssertEqual(
            Set(prepHoleBatches.flatMap { $0 }),
            Set(online.holes.map(\.number)),
            "bounded prep batches must cover the complete course exactly as the former all-hole request did"
        )
        XCTAssertEqual(
            prepHoleBatches.flatMap { $0 }.count,
            online.holes.count,
            "the successful path must not download the same hole facts twice"
        )
    }

    func testPartialCoursePrepWaitsOnCheapCoverageThenFetchesEachPreciseHoleOnce() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()
        let holes = (1...2).map { number in
            Hole(
                number: number,
                par: 4,
                yards: 350 + number,
                geometryCoverage: .partial,
                sourceGlobalId: source.course.globalId,
                sourceLocalHole: number
            )
        }
        let online = package(
            source,
            roundId: "partial-upgrade-round",
            recentRounds: [],
            holes: holes
        ).replacingCoursePrep(nil)
        let packageData = try JSONEncoder().encode(online)
        let png = minimalPNGData()
        let currentRevision = "bbbbbbbbbbbbbbbb"
        for hole in holes {
            _ = try store.saveCourseTopoImage(
                png,
                globalId: hole.sourceGlobalId ?? online.course.globalId,
                localHole: hole.sourceLocalHole ?? hole.number,
                geometryRevision: "aaaaaaaaaaaaaaaa"
            )
        }
        let requestLock = NSLock()
        var geometryReady = false
        var prepCoverages: [String] = []
        var coverageRequestCount = 0
        var requestedTopoRevisions: [String?] = []

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            let body: Data
            let contentType: String
            switch url.path {
            case let path where path.contains("/api/v2/mobile/courses/"):
                body = packageData
                contentType = "application/json"
            case let path where path.contains("/geometry/course/"):
                requestLock.withLock {
                    coverageRequestCount += 1
                    geometryReady = true
                }
                body = Data(
                    """
                    {"schema":"ai-caddie-course-geometry-coverage-v1",\
                    "globalId":\(online.course.globalId),"coverage":"ready",\
                    "readyHoles":2,"partialHoles":0,"totalHoles":2,"holes":[\
                    {"globalId":\(online.course.globalId),"localHole":1,"coverage":"ready"},\
                    {"globalId":\(online.course.globalId),"localHole":2,"coverage":"ready"}]}
                    """.utf8
                )
                contentType = "application/json"
            case let path where path.hasSuffix("/prep"):
                let ready = requestLock.withLock { geometryReady }
                let coverage = ready ? "ready" : "partial"
                requestLock.withLock { prepCoverages.append(coverage) }
                let requested = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
                    .filter { $0.name == "holes" }
                    .compactMap { $0.value.flatMap(Int.init) } ?? []
                body = try self.offlinePrepResponseData(
                    for: online,
                    localHoles: requested,
                    geometryCoverage: coverage,
                    geometryRevision: ready ? currentRevision : nil
                )
                contentType = "application/json"
            case let path where path.hasSuffix("/topo.png"):
                requestLock.withLock {
                    requestedTopoRevisions.append(
                        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
                            .first { $0.name == "r" }?.value
                    )
                }
                body = png
                contentType = "image/png"
            default:
                body = Data(#"{"queued":true}"#.utf8)
                contentType = "application/json"
            }
            return (
                HTTPURLResponse(
                    url: url,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: ["Content-Type": contentType]
                )!,
                body
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: URL(string: "https://partial.example.test")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: client.baseURL,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [0, 0]
        )

        await model.prepareCourseRound(
            globalId: online.course.globalId,
            roundId: online.roundId,
            teeBox: online.course.teeBox,
            nine: "all"
        )
        XCTAssertTrue(requestLock.withLock { prepCoverages }.isEmpty)
        XCTAssertEqual(requestLock.withLock { coverageRequestCount }, 0)
        XCTAssertTrue(requestLock.withLock { requestedTopoRevisions }.isEmpty)
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()

        let observations = requestLock.withLock { prepCoverages }
        XCTAssertEqual(observations.filter { $0 == "partial" }.count, holes.count)
        XCTAssertEqual(observations.filter { $0 == "ready" }.count, holes.count)
        XCTAssertEqual(requestLock.withLock { coverageRequestCount }, 1)
        XCTAssertEqual(
            requestLock.withLock { requestedTopoRevisions.compactMap { $0 } },
            Array(repeating: currentRevision, count: holes.count),
            "a previously cached Garmin revision must not satisfy the replacement bitmap request"
        )
        XCTAssertTrue(model.package?.hasCompleteOfflineCoursePrep == true)
        XCTAssertTrue(store.hasCourseTopoImages(for: try XCTUnwrap(model.package)))
    }

    func testFinishActiveRoundAcknowledgesEventsBeforeFinishAndOnlyThenClearsLocalRound() async throws {
        let fixture = try completedFixtureRound()
        let finishedRound = RecentRoundSummary(
            roundId: fixture.package.roundId,
            date: "2026-07-29T05:00:00Z",
            courseName: fixture.package.course.name,
            score: 5,
            par: 4,
            toPar: 1,
            holesCompleted: 1,
            globalId: fixture.package.course.globalId,
            sourceRefs: [fixture.package.roundId]
        )
        let refreshedHome = package(
            fixture.package,
            roundId: "home-\(fixture.package.course.globalId)",
            recentRounds: [finishedRound]
        )
        let morePlayedOtherCourseId = 3881
        let courseOptions = MobileCourseOptionsResponse(
            schema: "ai-caddie-mobile-course-options-v1",
            dataMode: "real",
            total: 2,
            courses: [
                MobileCourseOption(
                    globalId: morePlayedOtherCourseId,
                    name: "Cypress Point Club",
                    roundCount: 99,
                    suggestedLiveRoundId: "home-\(morePlayedOtherCourseId)",
                    holes: 18,
                    teeBox: "Blue",
                    geometryCoverage: "ready"
                ),
                MobileCourseOption(
                    globalId: fixture.package.course.globalId,
                    name: fixture.package.course.name,
                    roundCount: 1,
                    suggestedLiveRoundId: refreshedHome.roundId,
                    holes: fixture.package.holes.count,
                    teeBox: fixture.package.course.teeBox,
                    geometryCoverage: "ready"
                )
            ],
            generatedAt: "2026-07-29T05:01:00Z"
        )
        let courseOptionsBody = try JSONEncoder().encode(courseOptions)
        let refreshedHomeBody = try JSONEncoder().encode(refreshedHome)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        var finishBody: Data?
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            switch path {
            case "/api/v2/mobile/courses/options":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url), statusCode: 200,
                        httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                    )!,
                    courseOptionsBody
                )
            case "/api/v2/mobile/courses/\(fixture.package.course.globalId)/package":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url), statusCode: 200,
                        httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                    )!,
                    refreshedHomeBody
                )
            case "/api/v2/mobile/rounds/\(fixture.package.roundId)/events":
                let batch = try JSONDecoder().decode(
                    EventBatch.self,
                    from: try capturedRequestBodyData(from: request)
                )
                let ids = batch.events.map(\.eventId)
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url), statusCode: 200,
                        httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                    )!,
                    try JSONSerialization.data(withJSONObject: [
                        "accepted": ids.count,
                        "duplicate": false,
                        "acceptedEventIds": ids,
                        "duplicateEventIds": [],
                        "serverSequence": ids.count,
                    ])
                )
            case "/api/v2/mobile/rounds/\(fixture.package.roundId)/finish":
                requestLock.lock()
                finishBody = try capturedRequestBodyData(from: request)
                requestLock.unlock()
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url), statusCode: 201,
                        httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url), statusCode: 500,
                        httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = LiveRoundAppModel(
            offlineStore: fixture.store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: fixture.package.roundId,
            syncClient: SyncClient(
                baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                clientId: "ios-phone",
                session: session
            ),
            offlineGeometryRetryDelaysNanoseconds: [0]
        )

        await model.bootstrap()
        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()

        let didFinish = await model.finishActiveRound()
        XCTAssertTrue(didFinish)

        requestLock.lock()
        let paths = requestedPaths
        let capturedFinishBody = finishBody
        requestLock.unlock()
        let eventsPath = "/api/v2/mobile/rounds/\(fixture.package.roundId)/events"
        let finishPath = "/api/v2/mobile/rounds/\(fixture.package.roundId)/finish"
        let homePath = "/api/v2/mobile/courses/\(fixture.package.course.globalId)/package"
        let eventsIndex = try XCTUnwrap(paths.firstIndex(of: eventsPath))
        let finishIndex = try XCTUnwrap(paths.firstIndex(of: finishPath))
        XCTAssertLessThan(
            eventsIndex,
            finishIndex
        )
        // Bootstrap may still have a best-effort offline course refresh in flight, and that request
        // legitimately uses the same package path before Finish. Prove that Finish itself performs a
        // fresh home read *after* the finish transaction instead of comparing against that earlier read.
        XCTAssertNotNil(
            paths.indices.first { index in
                index > finishIndex && paths[index] == homePath
            },
            "a successful finish must refresh the just-finished course after the finish request"
        )
        XCTAssertFalse(
            paths.contains("/api/v2/mobile/courses/\(morePlayedOtherCourseId)/package"),
            "finishing a course must refresh that course instead of the historically most-played course"
        )
        let body = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(capturedFinishBody)) as? [String: Any]
        )
        let meta = try XCTUnwrap(body["meta"] as? [String: Any])
        XCTAssertEqual(meta["courseName"] as? String, fixture.package.course.name)
        XCTAssertEqual(meta["courseGlobalId"] as? Int, fixture.package.course.globalId)
        XCTAssertEqual(meta["holePars"] as? [Int], [4])
        XCTAssertEqual(meta["holesCompleted"] as? Int, 1)
        XCTAssertEqual(model.package?.roundId, refreshedHome.roundId)
        XCTAssertEqual(model.package?.recentHistory.rounds.first, finishedRound)
        XCTAssertEqual(try fixture.store.loadHomePackage()?.recentHistory.rounds.first, finishedRound)
        XCTAssertNil(model.liveRoundState)
        XCTAssertNil(try fixture.store.loadCurrentRoundPackage())
        XCTAssertFalse(try fixture.store.loadEvents().contains { $0.roundId == fixture.package.roundId })

        // A home package intentionally keeps this same identity. Starting it again must still enter
        // hole 1; comparing only package.roundId used to leave the UI stuck on “准备中”.
        await model.prepareCourseRound(
            globalId: fixture.package.course.globalId,
            roundId: refreshedHome.roundId,
            teeBox: refreshedHome.course.teeBox,
            nine: refreshedHome.nine ?? "all"
        )
        XCTAssertEqual(model.liveRoundState?.roundId, refreshedHome.roundId)
        XCTAssertEqual(model.pendingLiveHole, refreshedHome.holes.first?.number)
        XCTAssertTrue(try fixture.store.loadPendingEvents(roundId: refreshedHome.roundId).isEmpty)
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()
    }

    func testLatestCoursePreparationWinsWhenAnOlderResponseArrivesLate() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()
        let slow = package(source, roundId: "slow-round", recentRounds: [])
        let fast = package(source, roundId: "fast-round", recentRounds: [])
        let slowData = try JSONEncoder().encode(slow)
        let fastData = try JSONEncoder().encode(fast)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            if url.path.contains("/api/v2/mobile/courses/") {
                let roundId = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
                    .first { $0.name == "round_id" }?.value
                if roundId == slow.roundId {
                    Thread.sleep(forTimeInterval: 0.25)
                }
                return (
                    HTTPURLResponse(
                        url: url, statusCode: 200, httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    roundId == slow.roundId ? slowData : fastData
                )
            }
            return (
                HTTPURLResponse(
                    url: url, statusCode: 503, httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                Data(#"{"detail":"not needed"}"#.utf8)
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: URL(string: "https://generation.example.test")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: client.baseURL,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [0]
        )

        let slowTask = Task {
            await model.prepareCourseRound(
                globalId: source.course.globalId,
                roundId: slow.roundId,
                teeBox: source.course.teeBox,
                nine: "all"
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        await model.prepareCourseRound(
            globalId: source.course.globalId,
            roundId: fast.roundId,
            teeBox: source.course.teeBox,
            nine: "all"
        )
        await slowTask.value

        XCTAssertEqual(model.package?.roundId, fast.roundId)
        XCTAssertEqual(model.liveRoundState?.roundId, fast.roundId)
        XCTAssertEqual(model.pendingLiveHole, fast.holes.first?.number)
        XCTAssertFalse(model.isPreparingRound)
        XCTAssertNil(try store.loadRoundPackage(roundId: slow.roundId))
        model.liveHoleInitialLoadDidFinish()
        await model.waitForOfflineCourseDownloadForTesting()
    }

    func testFinishActiveRoundRejectsPartialAcknowledgementAndPreservesWholeRound() async throws {
        let fixture = try completedFixtureRound()
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            let status = path.hasSuffix("/events") ? 200 : 500
            let data = path.hasSuffix("/events")
                ? Data(
                    """
                    {"accepted":1,"duplicate":false,"acceptedEventIds":["finish-score"],"duplicateEventIds":[],"serverSequence":1}
                    """.utf8
                )
                : Data("{}".utf8)
            return (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url), statusCode: status,
                    httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                )!,
                data
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = LiveRoundAppModel(
            offlineStore: fixture.store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: fixture.package.roundId,
            syncClient: SyncClient(
                baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                clientId: "ios-phone",
                session: session
            )
        )

        await model.bootstrap()
        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()

        let didFinish = await model.finishActiveRound()
        XCTAssertFalse(didFinish)

        requestLock.lock()
        let paths = requestedPaths
        requestLock.unlock()
        XCTAssertTrue(paths.contains("/api/v2/mobile/rounds/\(fixture.package.roundId)/events"))
        XCTAssertFalse(paths.contains("/api/v2/mobile/rounds/\(fixture.package.roundId)/finish"))
        XCTAssertEqual(model.package?.roundId, fixture.package.roundId)
        XCTAssertNotNil(model.liveRoundState)
        XCTAssertEqual(
            Set(try fixture.store.loadPendingEvents(roundId: fixture.package.roundId).map(\.eventId)),
            Set(fixture.events.map(\.eventId))
        )
        XCTAssertNotNil(try fixture.store.loadCurrentRoundPackage())
    }

    func testResponseLostEventRetryStaysExactAfterLaterMediaUploadSuccess() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let attachment = try store.savePendingMedia(
            data: Data("image".utf8),
            eventId: "photo-event",
            roundId: package.roundId,
            hole: 1,
            targetId: "\(package.roundId):1",
            assetLocalId: "photo.jpg",
            mediaKind: "photo",
            fileName: "photo.jpg",
            capturedAt: "2026-07-21T00:00:00Z"
        )
        let event = LiveRoundEventBuilder(
            roundId: package.roundId,
            idFactory: { "photo-event" },
            now: { Date(timeIntervalSince1970: 1_774_051_200) }
        ).makePhotoEvent(
            hole: 1,
            assetLocalId: attachment.assetLocalId,
            fileURL: attachment.fileURL,
            note: nil,
            mediaId: nil
        )
        try store.appendEvent(event)
        let logURL = directory.appendingPathComponent("events.jsonl")

        let mediaStateLock = NSLock()
        var mediaUploadMaySucceed = false
        let mediaSuccessBody = Data(
            """
            {
              "schema": "ai-caddie-media-create-v1",
              "media": {
                "id": "uploaded-media-1",
                "createdAt": "2026-07-21T00:00:01Z",
                "targetType": "hole",
                "targetId": "\(package.roundId):1",
                "mediaKind": "photo",
                "localPath": "private/media/uploaded-media-1.jpg",
                "capturedAt": "2026-07-21T00:00:00Z",
                "privacyState": "private_local",
                "source": "ios"
              }
            }
            """.utf8
        )
        let mediaServer = try LoopbackHTTPServer { path, _ in
            mediaStateLock.lock()
            defer { mediaStateLock.unlock() }
            switch path {
            case "/api/v2/media":
                if !mediaUploadMaySucceed {
                    return (503, Data("{}".utf8))
                }
                return (200, mediaSuccessBody)
            case "/api/v2/media/uploaded-media-1/analyze":
                return (503, Data("{}".utf8))
            default:
                return (404, Data("{}".utf8))
            }
        }
        defer { mediaServer.stop() }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let stateLock = NSLock()
        var cycle = 1
        var eventPostMaySucceed = false
        var capturedEventPosts: [(cycle: Int, body: Data, key: String, log: Data)] = []
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            stateLock.lock()
            let currentCycle = cycle
            let shouldSucceedEventPost = eventPostMaySucceed
            stateLock.unlock()

            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events":
                let captured = (
                    cycle: currentCycle,
                    body: try capturedRequestBodyData(from: request),
                    key: try XCTUnwrap(request.value(forHTTPHeaderField: "Idempotency-Key")),
                    log: try Data(contentsOf: logURL)
                )
                stateLock.lock()
                capturedEventPosts.append(captured)
                stateLock.unlock()
                guard shouldSucceedEventPost else {
                    throw URLError(.networkConnectionLost)
                }
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"accepted":1,"duplicate":false,"acceptedEventIds":["photo-event"],"duplicateEventIds":[],"serverSequence":1}
                        """.utf8
                    )
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"schema":"ai-caddie-mobile-event-replay-v1","roundId":"\(package.roundId)","clientId":"ios-phone","afterSequence":0,"latestServerSequence":0,"nextCursor":0,"eventCount":0,"hasMore":false,"events":[]}
                        """.utf8
                    )
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 500,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let syncClient = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: mediaServer.baseURL,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: syncClient
        )

        await model.bootstrap()
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadPendingMedia(roundId: package.roundId).map(\.id), [attachment.id])

        mediaStateLock.lock()
        mediaUploadMaySucceed = true
        mediaStateLock.unlock()
        stateLock.lock()
        cycle = 2
        eventPostMaySucceed = true
        stateLock.unlock()
        await model.syncPendingEvents()

        stateLock.lock()
        let firstCyclePosts = capturedEventPosts.filter { $0.cycle == 1 }
        let secondCyclePosts = capturedEventPosts.filter { $0.cycle == 2 }
        stateLock.unlock()
        let firstPost = try XCTUnwrap(firstCyclePosts.first)
        let retryPost = try XCTUnwrap(secondCyclePosts.first)
        XCTAssertEqual(
            try JSONDecoder().decode(EventBatch.self, from: retryPost.body),
            try JSONDecoder().decode(EventBatch.self, from: firstPost.body)
        )
        XCTAssertEqual(retryPost.key, firstPost.key)
        XCTAssertEqual(retryPost.log, firstPost.log)
        XCTAssertTrue(try store.loadPendingMedia(roundId: package.roundId).isEmpty)
    }

    func testTornEOFReplayReopensDurablyBeforeHTTPAck() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let existing = LiveRoundEvent(
            eventId: "existing-before-torn-tail",
            roundId: package.roundId,
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        try store.appendEvent(existing)
        try store.appendSyncMarker(
            roundId: package.roundId,
            timestamp: "2026-07-21T00:00:01Z"
        )
        let logURL = directory.appendingPathComponent("events.jsonl")
        let handle = try FileHandle(forWritingTo: logURL)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data(#"{"eventId":"torn""#.utf8))
        try handle.close()

        let replayed = LiveRoundEvent(
            eventId: "durable-before-http-ack",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:02Z",
            hole: 1,
            kind: .note,
            payload: ["note": .string("replayed after repair")]
        )
        let replayBody = try JSONEncoder().encode(
            EventReplayResponse(
                schema: "ai-caddie-mobile-event-replay-v1",
                roundId: package.roundId,
                clientId: "ios-phone",
                afterSequence: 0,
                latestServerSequence: 7,
                nextCursor: 7,
                eventCount: 1,
                hasMore: false,
                events: [
                    EventReplayItem(
                        serverSequence: 7,
                        idempotencyKey: "remote-page",
                        event: replayed
                    )
                ]
            )
        )
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        var ackBody: Data?
        var durableEventsObservedAtAck: [LiveRoundEvent]?
        var durableLogObservedAtAck: Data?
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    replayBody
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/ack":
                let reopened = OfflineStore(directoryURL: directory)
                let durableEvents = try reopened.loadEvents()
                let durableLog = try Data(contentsOf: logURL)
                guard durableEvents.contains(replayed),
                      durableLog.last == 0x0A,
                      !String(decoding: durableLog, as: UTF8.self).contains(#"{"eventId":"torn""#)
                else {
                    throw URLError(.cannotParseResponse)
                }
                requestLock.lock()
                ackBody = try capturedRequestBodyData(from: request)
                durableEventsObservedAtAck = durableEvents
                durableLogObservedAtAck = durableLog
                requestLock.unlock()
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)","clientId":"ios-phone","ackedServerSequence":7,"latestServerSequence":7,"pendingEventCount":0}
                        """.utf8
                    )
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 500,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: client
        )

        await model.bootstrap()
        await model.syncPendingEvents()

        requestLock.lock()
        let paths = requestedPaths
        let capturedAckBody = ackBody
        let eventsAtAck = durableEventsObservedAtAck
        let logAtAck = durableLogObservedAtAck
        requestLock.unlock()
        let replayPath = "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
        let ackPath = "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
        let replayIndex = try XCTUnwrap(paths.firstIndex(of: replayPath))
        let ackIndex = try XCTUnwrap(paths.firstIndex(of: ackPath))
        XCTAssertLessThan(replayIndex, ackIndex)
        XCTAssertEqual(
            try JSONDecoder().decode(
                EventCursorAckRequest.self,
                from: try XCTUnwrap(capturedAckBody)
            ),
            EventCursorAckRequest(clientId: "ios-phone", serverSequence: 7)
        )
        let unwrappedEventsAtAck = try XCTUnwrap(eventsAtAck)
        XCTAssertTrue(unwrappedEventsAtAck.contains(replayed))
        let durableLog = try XCTUnwrap(logAtAck)
        XCTAssertEqual(durableLog.last, 0x0A)
        XCTAssertFalse(String(decoding: durableLog, as: UTF8.self).contains(#"{"eventId":"torn""#))
        XCTAssertEqual(try OfflineStore(directoryURL: directory).loadEvents(), unwrappedEventsAtAck)
    }

    func testExactReplayDirectoryBarrierFaultNeverSendsHTTPAck() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let barrierLock = NSLock()
        var barrierShouldFail = false
        var barrierOperations: [String] = []
        let store = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                barrierLock.lock()
                barrierOperations.append("file:\(url.lastPathComponent)")
                barrierLock.unlock()
            },
            syncEventLogDirectory: { url in
                barrierLock.lock()
                barrierOperations.append("directory:\(url.lastPathComponent)")
                let mustFail = barrierShouldFail
                    && url.standardizedFileURL.resolvingSymlinksInPath()
                        == directory.standardizedFileURL.resolvingSymlinksInPath()
                barrierLock.unlock()
                if mustFail {
                    throw LiveRoundAppModelTestFailure.directorySync
                }
            }
        )
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let replayed = LiveRoundEvent(
            eventId: "visible-but-directory-barrier-uncertain",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:02Z",
            hole: 1,
            kind: .syncMarker,
            payload: [
                "status": .string("synced"),
                "serverSequence": .number(0),
            ]
        )
        let logURL = directory.appendingPathComponent("events.jsonl")
        let packageBody = try JSONEncoder().encode(package)
        let replayBody = try JSONEncoder().encode(
            EventReplayResponse(
                schema: "ai-caddie-mobile-event-replay-v1",
                roundId: package.roundId,
                clientId: "ios-phone",
                afterSequence: 0,
                latestServerSequence: 7,
                nextCursor: 7,
                eventCount: 1,
                hasMore: false,
                events: [
                    EventReplayItem(
                        serverSequence: 7,
                        idempotencyKey: "remote-page",
                        event: replayed
                    )
                ]
            )
        )
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        var ackBody: Data?
        var ackObservedEvents: [LiveRoundEvent]?
        var ackObservedLog: Data?
        var ackObservedBarriers: [String]?
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/package":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    packageBody
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    replayBody
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/ack":
                barrierLock.lock()
                let barriers = barrierOperations
                barrierLock.unlock()
                let reopened = OfflineStore(directoryURL: directory)
                let durableEvents = try reopened.loadEvents()
                let durableLog = try Data(contentsOf: logURL)
                requestLock.lock()
                ackBody = try capturedRequestBodyData(from: request)
                ackObservedEvents = durableEvents
                ackObservedLog = durableLog
                ackObservedBarriers = barriers
                requestLock.unlock()
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)","clientId":"ios-phone","ackedServerSequence":7,"latestServerSequence":7,"pendingEventCount":0}
                        """.utf8
                    )
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 500,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: client
        )

        await model.bootstrap()
        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()
        barrierLock.lock()
        barrierOperations.removeAll()
        barrierShouldFail = true
        barrierLock.unlock()

        await model.syncPendingEvents()

        requestLock.lock()
        let failedAttemptPaths = requestedPaths
        requestLock.unlock()
        barrierLock.lock()
        let failedAttemptBarriers = barrierOperations
        barrierLock.unlock()
        let physicallyVisibleEvents = try OfflineStore(directoryURL: directory).loadEvents()
        let physicallyVisibleLog = try Data(contentsOf: logURL)
        XCTAssertEqual(physicallyVisibleEvents, [replayed])
        XCTAssertEqual(physicallyVisibleLog.last, 0x0A)
        XCTAssertEqual(physicallyVisibleLog.split(separator: 0x0A).count, 1)

        barrierLock.lock()
        barrierShouldFail = false
        barrierOperations.removeAll()
        barrierLock.unlock()
        XCTAssertTrue(
            failedAttemptPaths.contains(
                "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
            )
        )
        XCTAssertFalse(
            failedAttemptPaths.contains(
                "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
            )
        )
        XCTAssertEqual(
            Array(failedAttemptBarriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )

        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()
        await model.syncPendingEvents()

        requestLock.lock()
        let successfulAttemptPaths = requestedPaths
        let capturedAckBody = ackBody
        let durableEventsAtAck = ackObservedEvents
        let durableLogAtAck = ackObservedLog
        let barriersAtAck = ackObservedBarriers
        requestLock.unlock()
        let replayPath = "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
        let ackPath = "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
        let replayIndex = try XCTUnwrap(successfulAttemptPaths.firstIndex(of: replayPath))
        let ackIndex = try XCTUnwrap(successfulAttemptPaths.firstIndex(of: ackPath))
        XCTAssertLessThan(replayIndex, ackIndex)
        XCTAssertEqual(successfulAttemptPaths.filter { $0 == ackPath }.count, 1)
        XCTAssertEqual(
            try JSONDecoder().decode(
                EventCursorAckRequest.self,
                from: try XCTUnwrap(capturedAckBody)
            ),
            EventCursorAckRequest(clientId: "ios-phone", serverSequence: 7)
        )
        XCTAssertEqual(try XCTUnwrap(durableEventsAtAck), [replayed])
        let durableLog = try XCTUnwrap(durableLogAtAck)
        XCTAssertEqual(durableLog.last, 0x0A)
        XCTAssertEqual(durableLog.split(separator: 0x0A).count, 1)
        XCTAssertEqual(
            Array(try XCTUnwrap(barriersAtAck).suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )
    }

    func testLaterConflictWithinReplayPageDoesNotAcknowledgeThatPage() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let existing = LiveRoundEvent(
            eventId: "conflict-later-in-page",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        try store.appendEvent(existing)
        try store.appendSyncMarker(
            roundId: package.roundId,
            timestamp: "2026-07-21T00:00:01Z"
        )

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        let replayPayload = """
        {
          "schema": "ai-caddie-mobile-event-replay-v1",
          "roundId": "\(package.roundId)",
          "clientId": "ios-phone",
          "afterSequence": 0,
          "latestServerSequence": 2,
          "nextCursor": 2,
          "eventCount": 2,
          "hasMore": false,
          "events": [
            {
              "serverSequence": 1,
              "idempotencyKey": "remote-page",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "durable-prefix",
                "roundId": "\(package.roundId)",
                "clientId": "web",
                "timestamp": "2026-07-21T00:00:02Z",
                "hole": 1,
                "kind": "note",
                "payload": {"note": "prefix persisted before later conflict"}
              }
            },
            {
              "serverSequence": 2,
              "idempotencyKey": "remote-page",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "conflict-later-in-page",
                "roundId": "\(package.roundId)",
                "clientId": "apple-watch",
                "timestamp": "2026-07-21T00:00:00Z",
                "hole": 1,
                "kind": "score",
                "payload": {"strokes": 6}
              }
            }
          ]
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            let status: Int
            let data: Data
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                status = 200
                data = replayPayload
            case "/api/v2/mobile/rounds/\(package.roundId)/events/ack":
                status = 200
                data = Data(
                    """
                    {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)","clientId":"ios-phone","ackedServerSequence":2,"latestServerSequence":2,"pendingEventCount":0}
                    """.utf8
                )
            default:
                status = 500
                data = Data("{}".utf8)
            }
            return (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: status,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                data
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: client
        )

        await model.bootstrap()
        await model.syncPendingEvents()

        requestLock.lock()
        let paths = requestedPaths
        requestLock.unlock()
        XCTAssertTrue(paths.contains("/api/v2/mobile/rounds/\(package.roundId)/events/replay"))
        XCTAssertFalse(paths.contains("/api/v2/mobile/rounds/\(package.roundId)/events/ack"))
        let events = try store.loadEvents()
        XCTAssertTrue(events.contains { $0.eventId == "durable-prefix" })
        XCTAssertEqual(
            events.filter { $0.eventId == existing.eventId },
            [existing]
        )
    }

    private func localFixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let fixture = try String(contentsOf: url, encoding: .utf8)
            .replacingOccurrences(of: #""dataMode": "fixture""#, with: #""dataMode": "local""#)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: Data(fixture.utf8))
    }

    private func offlineReadyPackage(
        _ package: LiveRoundPackage,
        geometryRevision: String? = nil
    ) throws -> LiveRoundPackage {
        let response = try JSONDecoder().decode(
            CoursePrepResponse.self,
            from: offlinePrepResponseData(
                for: package,
                geometryRevision: geometryRevision
            )
        )
        return package.replacingCoursePrep(CoursePrepPackage(
            schema: response.schema,
            globalId: response.globalId,
            holes: response.holes,
            missingData: nil
        ))
    }

    private func offlinePrepResponseData(
        for package: LiveRoundPackage,
        localHoles: [Int]? = nil,
        geometryCoverage: String = "ready",
        geometryRevision: String? = nil
    ) throws -> Data {
        let requested = localHoles.map { Set($0) }
        let holes = package.holes.filter { hole in
            guard let requested else { return true }
            return requested.contains(hole.sourceLocalHole ?? hole.number)
        }
        XCTAssertFalse(holes.isEmpty)
        let rows = holes.map { hole in
            let blueYards = hole.yards.map(String.init) ?? "null"
            let revisionField = geometryRevision.map {
                ",\"geometryRevision\":\"\($0)\""
            } ?? ""
            return """
            {"hole":\(hole.sourceLocalHole ?? hole.number),"par":\(hole.par),
             "par_source":"courseview","blue_yards":\(blueYards),"route_len_m":360,
             "route":[[0,0,0],[0,360,360]],"geometryCoverage":"\(geometryCoverage)"\(revisionField),"steps":[],"cautions":[],
             "hazards":{"water_carry":[],"bunkers":[],"details":[]},
             "map":{"image":"data:image/jpeg;base64,AQID","overlay":{"w":720,"h":1120,
             "ppm":1,"ln":360,"route":[[360,1000,0],[360,100,360]]}}}
            """
        }.joined(separator: ",")
        return Data("""
        {"schema":"ai-caddie-course-prep-v1","globalId":\(package.course.globalId),
         "holeCount":\(holes.count),"clubs":[],"holes":[\(rows)]}
        """.utf8)
    }

    private func minimalPNGData() -> Data {
        validOnePixelPNGData()
    }

    private func package(
        _ source: LiveRoundPackage,
        roundId: String,
        recentRounds: [RecentRoundSummary],
        holes: [Hole]? = nil
    ) -> LiveRoundPackage {
        let selectedHoles = holes ?? source.holes
        return LiveRoundPackage(
            schema: source.schema,
            roundId: roundId,
            dataMode: source.dataMode,
            sourceCoverage: source.sourceCoverage,
            missingData: source.missingData,
            playerProfile: source.playerProfile,
            course: source.course,
            holes: selectedHoles,
            nine: source.nine,
            coursePrep: source.coursePrep,
            geometryCoverage: GeometryCoverage(
                state: source.geometryCoverage.state,
                readyHoles: source.geometryCoverage.state == .ready
                    ? selectedHoles.count
                    : min(source.geometryCoverage.readyHoles, selectedHoles.count),
                totalHoles: selectedHoles.count
            ),
            readinessChecks: source.readinessChecks,
            caddieContextSeeds: source.caddieContextSeeds,
            weatherSnapshot: source.weatherSnapshot,
            clubProfiles: source.clubProfiles,
            caddieDecisionEndpoint: source.caddieDecisionEndpoint,
            offlinePackageStatus: source.offlinePackageStatus,
            eventCursor: source.eventCursor,
            recentHistory: RecentHistory(
                course: source.recentHistory.course,
                rounds: recentRounds,
                holes: source.recentHistory.holes
            ),
            cachedCaddieRules: source.cachedCaddieRules,
            generatedAt: source.generatedAt
        )
    }

    private func completedFixtureRound() throws -> (
        store: OfflineStore,
        package: LiveRoundPackage,
        events: [LiveRoundEvent]
    ) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let timestamp = "2026-07-29T05:00:00Z"
        let events = [
            LiveRoundEvent(
                eventId: "finish-score", roundId: package.roundId, timestamp: timestamp,
                hole: 1, kind: .score, payload: ["strokes": .number(5), "fairway": .string("hit")]
            ),
            LiveRoundEvent(
                eventId: "finish-putt", roundId: package.roundId, timestamp: timestamp,
                hole: 1, kind: .putt, payload: ["putts": .number(2)]
            ),
            LiveRoundEvent(
                eventId: "finish-penalty", roundId: package.roundId, timestamp: timestamp,
                hole: 1, kind: .penalty, payload: ["penalties": .number(0)]
            ),
        ]
        try events.forEach(store.appendEvent)
        return (store, package, events)
    }
}
#endif
