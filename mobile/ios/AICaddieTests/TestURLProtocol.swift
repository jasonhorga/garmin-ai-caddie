import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

func validOnePixelPNGData() -> Data {
    // Complete, decoder-valid 1x1 PNG. Signature-only placeholders must never satisfy offline-map
    // readiness because a real UIImage/CGImage cannot render them.
    Data(
        base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )!
}

/// Reserved fixture namespaces used across the native tests, including interpolated host names.
/// Official Garmin/OAuth hosts and loopback fixture servers are deliberately outside this policy.
enum TestFixtureHosts {
    static func contains(_ url: URL?) -> Bool {
        guard let host = url?.host?.lowercased() else { return false }
        let reservedRoots = ["test", "example", "invalid", "example.com", "example.net", "example.org"]
        return host == "evilgarmin.com" || reservedRoots.contains {
            host == $0 || host.hasSuffix("." + $0)
        }
    }

    static func origin(of request: URLRequest) -> String {
        let host = request.url?.host ?? "unknown-host"
        let token = request.value(forHTTPHeaderField: "X-Codex-Test-Token") ?? "unscoped"
        return "host=\(host) scope=\(token)"
    }
}

/// Only the final protocol of explicit sessions asserts. Shared best-effort work uses the separate
/// offline protocol below, so an old background request cannot fail the next test by association.
final class UnhandledTestURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool {
        guard TestFixtureHosts.contains(request.url) else { return false }
        XCTFail("route=explicit origin=[\(TestFixtureHosts.origin(of: request))] "
            + "No test URLProtocol handled \(request.url?.absoluteString ?? "missing URL")")
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
    }

    override func stopLoading() {}
}

/// Process-wide fallback for production's shared/default clients. Match the old transport failure
/// code without DNS or its platform-generated log text. A later test-specific global handler wins.
final class SharedOfflineTestURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool {
        TestFixtureHosts.contains(request.url)
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let error = URLError(.cannotFindHost, userInfo: [
            NSLocalizedDescriptionKey: "route=shared origin=[\(TestFixtureHosts.origin(of: request))] "
                + "fixture intentionally offline; DNS disabled",
            "CaddieTestRoute": "shared",
            "CaddieTestOrigin": TestFixtureHosts.origin(of: request),
        ])
        client?.urlProtocol(self, didFailWithError: error)
    }

    override func stopLoading() {}
}

/// Install before constructing the session, rather than waiting for its first canInit callback.
/// Protocol classes are tried in array order, so the test's handler always has first refusal.
func testProtocolClasses(_ handler: URLProtocol.Type) -> [AnyClass] {
    ensureC156TopoBundleStub()
    return [handler, UnhandledTestURLProtocol.self]
}

/// Bundle-wide interceptor for the production topo prefetch, which intentionally uses
/// URLSession.shared. Explicit test sessions keep their protocol classes and therefore retain
/// their own request handlers and assertions.
final class SharedTopoURLProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var urls = Set<URL>()
    private static var requestCount = 0

    override class func canInit(with request: URLRequest) -> Bool {
        return TestFixtureHosts.contains(request.url)
            && request.url?.path.hasSuffix("/topo.png") == true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        Self.lock.withLock {
            Self.urls.insert(url)
            Self.requestCount += 1
        }
        let response = HTTPURLResponse(
            url: url, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "image/png"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: validOnePixelPNGData())
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func resetRecords() {
        lock.withLock {
            urls.removeAll()
            requestCount = 0
        }
    }

    static func records() -> (urls: Set<URL>, count: Int) {
        lock.withLock { (urls, requestCount) }
    }
}

/// Session helpers register before traffic and keep the shared topo and offline stubs alive
/// through process exit. Explicit sessions retain their own protocol order and handlers.
private final class C156TopoBundleObserver: NSObject, XCTestObservation {
    override init() {
        URLProtocol.registerClass(SharedOfflineTestURLProtocol.self)
        URLProtocol.registerClass(SharedTopoURLProtocol.self)
        super.init()
    }

    func testBundleWillStart(_ testBundle: Bundle) {
        URLProtocol.registerClass(SharedOfflineTestURLProtocol.self)
        URLProtocol.registerClass(SharedTopoURLProtocol.self)
    }

    func testBundleDidFinish(_ testBundle: Bundle) {
        // Detached image loads can outlive XCTest's bundle callback. Keep both stubs installed
        // until process exit so late retries still cannot fall through to a real network lookup.
    }
}

/// The first touch can come from a URLProtocol/URLSession background thread, but XCTest only
/// accepts observer registration on the main thread. The stub itself is registered in init on
/// any thread; the observer is hopped to main without
/// blocking, so a test waiting on the main thread cannot deadlock against it.
private let c156TopoBundleObserver: C156TopoBundleObserver = {
    let observer = C156TopoBundleObserver()
    if Thread.isMainThread {
        XCTestObservationCenter.shared.addTestObserver(observer)
    } else {
        DispatchQueue.main.async {
            XCTestObservationCenter.shared.addTestObserver(observer)
        }
    }
    return observer
}()

/// Swift file globals are lazy. Protocol/session helpers must explicitly touch the observer
/// before starting traffic; declaring the global alone does not bootstrap the bundle.
func ensureC156TopoBundleStub() {
    _ = c156TopoBundleObserver
}

/// Contract-valid lightweight prep used by tests that exercise the whole-course installer.
/// Keep this in the shared test support so every fixture uses the same decoder-shaped payload.
func offlinePrepResponseData(
    for package: LiveRoundPackage,
    localHoles: [Int]? = nil,
    geometryCoverage: String = "ready",
    geometryRevision: String? = nil
) throws -> Data {
    let requested = localHoles.map { Set($0) }
    let holes = package.holes.filter { hole in
        guard let requested else { return true }
        return requested.contains(hole.sourceLocalHole)
    }
    XCTAssertFalse(holes.isEmpty)
    let rows = holes.map { hole in
        let blueYards = hole.yards.map(String.init) ?? "null"
        let revisionField = geometryRevision.map {
            ",\"geometryRevision\":\"\($0)\""
        } ?? ""
        return """
        {"hole":\(hole.sourceLocalHole),"par":\(hole.par),
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

/// A test-only gate that stays closed until the owning test explicitly releases it.
final class TestRequestGate: @unchecked Sendable {
    private let condition = NSCondition()
    private var open = false

    func wait() {
        condition.lock()
        while !open { condition.wait() }
        condition.unlock()
    }

    func release() {
        condition.lock()
        open = true
        condition.broadcast()
        condition.unlock()
    }
}

/// Shared URLProtocol stub for client tests: install on an ephemeral `URLSessionConfiguration` and
/// set `requestHandler` to inspect the outgoing request + return a canned response. Used by
/// `SyncClientTests` and `AppleAuthClientTests` (so it must not be `private` to one file).
class CapturingURLProtocol: URLProtocol {
    static let tokenHeader = "X-Codex-Test-Token"
    private static let handlerLock = NSLock()
    private static var storedRequestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    private static var scopedHandlers: [String: ((URLRequest) throws -> (HTTPURLResponse, Data))] = [:]
    /// Keep the existing assignment API while making handler capture atomic across URL sessions.
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))? {
        get {
            handlerLock.lock()
            defer { handlerLock.unlock() }
            return storedRequestHandler
        }
        set {
            handlerLock.lock()
            storedRequestHandler = newValue
            handlerLock.unlock()
        }
    }
    static var stopLoadingHandler: ((URLRequest) -> Void)? {
        get {
            handlerLock.lock()
            defer { handlerLock.unlock() }
            return storedStopLoadingHandler
        }
        set {
            handlerLock.lock()
            storedStopLoadingHandler = newValue
            handlerLock.unlock()
        }
    }
    private static var storedStopLoadingHandler: ((URLRequest) -> Void)?

    static func installScopedHandler(
        _ handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> String {
        let token = UUID().uuidString
        handlerLock.lock()
        scopedHandlers[token] = handler
        handlerLock.unlock()
        return token
    }

    static func removeScopedHandler(_ token: String) {
        handlerLock.lock()
        scopedHandlers.removeValue(forKey: token)
        handlerLock.unlock()
    }

    static func replaceScopedHandler(
        _ handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data),
        for token: String
    ) {
        handlerLock.lock()
        if scopedHandlers[token] != nil {
            scopedHandlers[token] = handler
        }
        handlerLock.unlock()
    }

    /// URLSession may hand a custom URLProtocol the encoded request body either as `httpBody` or
    /// as `httpBodyStream` (the latter is what the GitHub Xcode runner does). Tests that inspect the
    /// wire payload must accept both representations or they become simulator/runtime dependent.
    static func requestBodyData(from request: URLRequest) throws -> Data {
        if let body = request.httpBody {
            return body
        }
        guard let stream = request.httpBodyStream else {
            throw URLError(.zeroByteResource)
        }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1_024)
        while true {
            let readCount = stream.read(&buffer, maxLength: buffer.count)
            if readCount < 0 {
                throw stream.streamError ?? URLError(.cannotDecodeContentData)
            }
            if readCount == 0 {
                return data
            }
            data.append(buffer, count: readCount)
        }
    }

    override class func canInit(with request: URLRequest) -> Bool {
        ensureC156TopoBundleStub()
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        // Capture the handler before leaving URLProtocol's serial callback queue.  A test handler
        // may deliberately wait on a semaphore; running it here would block every other request
        // in the process and make the next test inherit the stalled request.
        let token = request.value(forHTTPHeaderField: Self.tokenHeader)
        Self.handlerLock.lock()
        let requestHandler = token.map { Self.scopedHandlers[$0] } ?? Self.storedRequestHandler
        Self.handlerLock.unlock()
        guard let requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                let (response, data) = try requestHandler(self.request)
                self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                self.client?.urlProtocol(self, didLoad: data)
                self.client?.urlProtocolDidFinishLoading(self)
            } catch {
                self.client?.urlProtocol(self, didFailWithError: error)
            }
        }
    }

    override func stopLoading() {
        Self.handlerLock.lock()
        let handler = Self.storedStopLoadingHandler
        Self.handlerLock.unlock()
        handler?(request)
    }
}

/// Only the tests of production stores need a global capture protocol. Keep topo with the bundle
/// stub even when this class is registered later; injected sessions still use CapturingURLProtocol
/// itself, which accepts topo and preserves the owning test's handler.
final class SharedNonTopoCapturingURLProtocol: CapturingURLProtocol {
    private static let registrationLock = NSLock()
    private static var registeredHost: String?

    static func registerForSharedSession(host: String) {
        ensureC156TopoBundleStub()
        registrationLock.withLock { registeredHost = host.lowercased() }
        URLProtocol.registerClass(SharedNonTopoCapturingURLProtocol.self)
    }

    override class func canInit(with request: URLRequest) -> Bool {
        ensureC156TopoBundleStub()
        let ownsHost = registrationLock.withLock { registeredHost == request.url?.host?.lowercased() }
        return ownsHost && !SharedTopoURLProtocol.canInit(with: request)
    }
}

/// A handler token belongs to one test's URLSession. Requests carrying an old token fail closed
/// after that scope is released, so a delayed request can never enter the next test's handler.
final class CapturingURLProtocolScope {
    let token: String

    init(handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) {
        ensureC156TopoBundleStub()
        token = CapturingURLProtocol.installScopedHandler(handler)
    }

    func configuration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        configuration.httpAdditionalHeaders = [CapturingURLProtocol.tokenHeader: token]
        return configuration
    }

    func replaceHandler(
        _ handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) {
        CapturingURLProtocol.replaceScopedHandler(handler, for: token)
    }

    deinit {
        CapturingURLProtocol.removeScopedHandler(token)
    }
}

final class CapturingURLProtocolTests: XCTestCase {
    override func tearDown() {
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    #if !SWIFT_PACKAGE
    /// J4.2 test transport: a missed fixture request must fail XCTest before any DNS attempt.
    func testProductSpec42AnUnhandledFixtureRequestFailsDuringProtocolSelection() throws {
        for host in ["unhandled.example.test", "caddie.example", "caddie.example.com", "example.invalid", "protocol.test"] {
            let url = try XCTUnwrap(URL(string: "https://\(host)/topo.png"))
            var request = URLRequest(url: url)
            request.setValue("originating-test", forHTTPHeaderField: CapturingURLProtocol.tokenHeader)
            XCTExpectFailure("The explicit-session protocol must report missing fixture interception") {
                let claimed = UnhandledTestURLProtocol.canInit(with: request)
                XCTAssertTrue(claimed, "claim the request so URLSession cannot fall through to DNS")
            }
        }
    }
    #endif

    /// J4.2/J8: shared best-effort work keeps its former offline error without consulting DNS,
    /// including a previous test's host while a newer test has a global capture installed.
    func testProductSpec42SharedFixtureFallbackPreservesOfflineErrors() async throws {
        ensureC156TopoBundleStub()
        CapturingURLProtocol.requestHandler = { request in
            XCTFail("another test's shared request reached this test's handler")
            return (HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 202,
                                    httpVersion: nil, headerFields: nil)!, Data())
        }
        SharedNonTopoCapturingURLProtocol.registerForSharedSession(host: "current-owner.example.test")
        defer { URLProtocol.unregisterClass(SharedNonTopoCapturingURLProtocol.self) }
        let paths = ["/garmin-raster.webp", "/api/v2/players/me/clubs/bag",
                     "/api/v2/history/clubs/bag", "/api/v2/caddie/decision", "/prep", "/weather"]
        for host in ["old-owner.example.test", "caddie.example", "caddie.example.com", "example.invalid"] {
            for path in paths {
                let url = try XCTUnwrap(URL(string: "https://\(host)\(path)"))
                do {
                    _ = try await URLSession.shared.data(from: url)
                    XCTFail("shared fixture requests must preserve the offline transport failure")
                } catch let error as URLError {
                    XCTAssertEqual(error.code, .cannotFindHost)
                    XCTAssertEqual((error as NSError).userInfo["CaddieTestRoute"] as? String, "shared")
                    XCTAssertTrue(error.localizedDescription.contains("route=shared"))
                    XCTAssertFalse(error.localizedDescription.contains("hostname could not be found"))
                }
            }
        }
    }

    /// J4.2: SyncClient's foreground-start session copies the supplied configuration.
    /// Copying the default/shared configuration must retain the bundle's offline interception.
    func testProductSpec42CopiedSharedConfigurationKeepsFixtureOffline() async throws {
        ensureC156TopoBundleStub()
        let session = URLSession(configuration: URLSession.shared.configuration)
        defer { session.invalidateAndCancel() }
        let url = try XCTUnwrap(URL(string: "https://copied-session.example.test/package"))
        do {
            _ = try await session.data(from: url)
            XCTFail("a copied default session must preserve the offline failure")
        } catch let error as URLError {
            XCTAssertEqual(error.code, .cannotFindHost)
            XCTAssertEqual((error as NSError).userInfo["CaddieTestRoute"] as? String, "shared")
        }
    }

    /// J4.2: injecting a session keeps raster and bag responses with that test's handler.
    func testProductSpec42InjectedRasterAndBagKeepTheirOwnHandler() async throws {
        let body = Data("own fixture".utf8)
        let scope = CapturingURLProtocolScope { request in
            (HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 202,
                             httpVersion: nil, headerFields: nil)!, body)
        }
        let session = URLSession(configuration: scope.configuration())
        defer { session.invalidateAndCancel() }
        for path in ["/garmin-raster.jpg", "/api/v2/players/me/clubs/bag"] {
            let url = try XCTUnwrap(URL(string: "https://caddie.example\(path)"))
            let (data, response) = try await session.data(from: url)
            XCTAssertEqual(data, body)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 202)
        }
    }

    /// J4.2 test transport: the guard must preserve access to the local fixture server.
    func testProductSpec42TheFixtureGuardLeavesLoopbackServersAvailable() throws {
        let url = try XCTUnwrap(URL(string: "http://localhost/fixture"))
        XCTAssertFalse(UnhandledTestURLProtocol.canInit(with: URLRequest(url: url)))
    }

    func testAHandlerWaitingOnOneRequestDoesNotBlockAnotherRequest() async throws {
        let heldStarted = expectation(description: "held request entered its handler")
        let fastFinished = expectation(description: "fast request finished while held request waits")
        let release = DispatchSemaphore(value: 0)
        CapturingURLProtocol.requestHandler = { request in
            if request.url?.path == "/held" {
                heldStarted.fulfill()
                _ = release.wait(timeout: .now() + 5)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        let session = URLSession(configuration: configuration)
        let held = Task { try await session.data(from: URL(string: "https://protocol.test/held")!) }

        await fulfillment(of: [heldStarted], timeout: 1)
        let fast = Task {
            _ = try await session.data(from: URL(string: "https://protocol.test/fast")!)
            fastFinished.fulfill()
        }
        await fulfillment(of: [fastFinished], timeout: 1)
        release.signal()
        _ = try await held.value
        _ = try await fast.value
    }

    func testARequestAlreadyInFlightKeepsItsHandlerWhenTheNextTestInstallsOne() async throws {
        let started = expectation(description: "old request entered its handler")
        let release = DispatchSemaphore(value: 0)
        var nextHandlerCalls = 0
        CapturingURLProtocol.requestHandler = { request in
            started.fulfill()
            _ = release.wait(timeout: .now() + 5)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        let session = URLSession(configuration: configuration)
        let oldRequest = Task { try await session.data(from: URL(string: "https://protocol.test/old")!) }

        await fulfillment(of: [started], timeout: 1)
        CapturingURLProtocol.requestHandler = { request in
            nextHandlerCalls += 1
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }
        release.signal()
        _ = try await oldRequest.value
        XCTAssertEqual(nextHandlerCalls, 0)
    }

    /// A request queued by the previous test must not be answered by the next test's handler.
    /// An unknown token fails closed even while the process-wide compatibility handler is set.
    func testAStaleTestTokenCannotReachTheNextHandler() async throws {
        let staleToken = UUID().uuidString
        var globalHandlerCalls = 0
        CapturingURLProtocol.requestHandler = { request in
            globalHandlerCalls += 1
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }
        let scope = CapturingURLProtocolScope { request in
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data())
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        configuration.httpAdditionalHeaders = ["X-Codex-Test-Token": staleToken]
        let session = URLSession(configuration: configuration)
        do {
            _ = try await session.data(from: URL(string: "https://protocol.test/stale")!)
            XCTFail("a stale request must fail instead of reaching the next test handler")
        } catch {
            XCTAssertEqual(globalHandlerCalls, 0)
        }
        _ = scope
    }

    func testARequestWithItsScopeTokenReachesOnlyItsOwnHandler() async throws {
        var scopedHandlerCalls = 0
        var observedToken: String?
        let scope = CapturingURLProtocolScope { request in
            scopedHandlerCalls += 1
            observedToken = request.value(forHTTPHeaderField: CapturingURLProtocol.tokenHeader)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data("scoped".utf8))
        }
        let session = URLSession(configuration: scope.configuration())
        let request = URLRequest(url: URL(string: "https://protocol.test/scoped")!)
        let result: (Data, URLResponse) = try await session.data(for: request)

        XCTAssertEqual(scopedHandlerCalls, 1)
        XCTAssertEqual(observedToken, scope.token)
        XCTAssertEqual(result.0, Data("scoped".utf8))
    }
}
