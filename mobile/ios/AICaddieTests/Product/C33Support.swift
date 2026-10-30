#if !SWIFT_PACKAGE
import Foundation
import XCTest
@testable import AICaddie

// A nonblocking protocol: holding a request never blocks URLProtocol's serial delivery queue.
final class C33URLProtocol: URLProtocol {
    static var onStart: ((C33URLProtocol) -> Void)?
    static var onStop: ((URLRequest) -> Void)?
    private static let callbackLock = NSLock()
    override class func canInit(with request: URLRequest) -> Bool {
        ensureC156TopoBundleStub()
        // This protocol is installed only on injected sessions: their handler owns topo too.
        return TestFixtureHosts.contains(request.url)
    }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.callbackLock.lock(); let handler = Self.onStart; Self.callbackLock.unlock()
        if let handler { handler(self) } else { reply(404) }
    }
    override func stopLoading() {
        guard TestFixtureHosts.contains(request.url) else { return }
        Self.callbackLock.lock(); let handler = Self.onStop; Self.callbackLock.unlock()
        handler?(request)
    }
    static func setHandlers(
        onStart: ((C33URLProtocol) -> Void)?, onStop: ((URLRequest) -> Void)? = nil
    ) {
        callbackLock.lock(); self.onStart = onStart; self.onStop = onStop; callbackLock.unlock()
    }
    func reply(_ status: Int, _ data: Data = Data()) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil
        )!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    static func session() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(C33URLProtocol.self)
        configuration.httpMaximumConnectionsPerHost = 1
        return URLSession(configuration: configuration)
    }
}

/// Scope the shared topo downloader used by fresh-entry tests. The production store intentionally
/// uses URLSession.shared, so the bundle-level SharedTopoURLProtocol intercepts its prefetch. A
/// valid one-pixel response completes that task and prevents the five/15-second retry chain. The
/// scope only drains the store before clearing it; the bundle stub remains installed for late
/// outer tasks and therefore cannot leak a retry to DNS.
@MainActor
final class C33TopoPrefetchScope {
    private var stopped = false

    init() {
        ensureC156TopoBundleStub()
        TopoHoleImageStore.resetForUITesting()
        SharedTopoURLProtocol.resetRecords()
    }

    func stop() async {
        guard !stopped else { return }
        // reset only cancels the detached download, not prefetch's outer ensureLoaded task. Let
        // every served image reach the cache first, while still intercepting any late first load.
        // Require a quiet polling round too, including when no prefetch had started at teardown.
        let deadline = Date().addingTimeInterval(10)
        var lastCount = SharedTopoURLProtocol.records().count
        var lastChange = Date()
        var drained = false
        while Date() < deadline {
            // Poll cadence, not a success delay: completion requires both cache and quiescence.
            do { try await Task.sleep(nanoseconds: 10_000_000) } catch { break }
            let snapshot = SharedTopoURLProtocol.records()
            if snapshot.count != lastCount {
                lastCount = snapshot.count
                lastChange = Date()
            }
            if snapshot.urls.allSatisfy({ TopoHoleImageStore.isMemoryCached($0) }),
               Date().timeIntervalSince(lastChange) >= 0.1 {
                drained = true
                break
            }
        }
        guard drained else {
            // Leave the bundle stub installed. A delayed outer task can still finish safely after
            // this bounded drain rather than being turned into a real DNS retry.
            XCTFail("Shared topo prefetch did not reach cached, quiescent completion before teardown")
            return
        }
        TopoHoleImageStore.resetForUITesting()
        stopped = true
    }
}

/// Earlier tests' models may still be draining requests through the process-wide URL protocol, and
/// a test's own model can follow up on the same URL. An expectation tied to one request claims its
/// first match only, so a late stray callback can never crash the run by over-fulfilling it.
final class C33FirstMatch {
    private let lock = NSLock()
    private var matched = false

    func claim() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !matched else { return false }
        matched = true
        return true
    }
}

/// A deterministic clock substitute for the model's 8/20-second progress timers.
actor C33StartSleepGate {
    private var waiter: CheckedContinuation<Void, Never>?
    private var permits = 0

    func wait() async {
        if permits > 0 {
            permits -= 1
            return
        }
        await withCheckedContinuation { continuation in
            waiter = continuation
        }
    }

    func release() {
        if let waiter {
            waiter.resume()
            self.waiter = nil
        } else {
            permits += 1
        }
    }
}

func c33Query(_ request: URLRequest, _ name: String) -> String? {
    guard let url = request.url else { return nil }
    return URLComponents(url: url, resolvingAgainstBaseURL: false)?
        .queryItems?.first(where: { $0.name == name })?.value
}

func c33Package() throws -> LiveRoundPackage {
    let url = try XCTUnwrap(Bundle(for: C33StartTests.self).url(
        forResource: "c33-32850-hole1", withExtension: "json"
    ))
    // Production's v2 identity requires a complete nine-hole table. The captured fixture retains
    // only hole 1; fill 2–9 with synthetic identity rows, never additional captured golf facts.
    var json = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    var holes = try XCTUnwrap(json["holes"] as? [[String: Any]])
    for number in 2...9 {
        holes.append(["number": number, "par": 4, "geometryCoverage": "missing",
                      "sourceGlobalId": 32850, "sourceLocalHole": number, "courseHoleNumber": number])
    }
    json["holes"] = holes
    return try JSONDecoder().decode(LiveRoundPackage.self, from: JSONSerialization.data(withJSONObject: json))
        .validatedRoundIdentity()
}

func c33RequestBody(_ request: URLRequest) throws -> Data {
    if let data = request.httpBody { return data }
    guard let stream = request.httpBodyStream else { throw URLError(.cannotDecodeContentData) }
    stream.open()
    defer { stream.close() }
    var data = Data()
    var bytes = [UInt8](repeating: 0, count: 4096)
    while stream.hasBytesAvailable {
        let count = stream.read(&bytes, maxLength: bytes.count)
        if count < 0 { throw stream.streamError ?? URLError(.cannotDecodeContentData) }
        if count == 0 { break }
        data.append(contentsOf: bytes.prefix(count))
    }
    return data
}

@MainActor
func c33Model(
    _ store: OfflineStore,
    _ client: SyncClient,
    roundStartIntentWaitNanoseconds: UInt64 = LiveRoundAppModel.defaultRoundStartIntentWaitNanoseconds
) -> LiveRoundAppModel {
    LiveRoundAppModel(
        offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
        garminSessionStore: nil, syncClient: client,
        offlineGeometryRetryDelaysNanoseconds: [],
        roundStartIntentWaitNanoseconds: roundStartIntentWaitNanoseconds,
        networkPathObserver: nil
    )
}

@MainActor
final class C33NetworkObserver: NetworkPathObserving {
    private var handler: (@MainActor (SpeculativeNetworkState) -> Void)?

    func start(_ onChange: @escaping @MainActor (SpeculativeNetworkState) -> Void) {
        handler = onChange
    }

    func publish(_ state: SpeculativeNetworkState) {
        handler?(state)
    }
}
#endif
