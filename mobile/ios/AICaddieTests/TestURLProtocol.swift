import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest

func validOnePixelPNGData() -> Data {
    // Complete, decoder-valid 1x1 PNG. Signature-only placeholders must never satisfy offline-map
    // readiness because a real UIImage/CGImage cannot render them.
    Data(
        base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )!
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
final class CapturingURLProtocol: URLProtocol {
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
        true
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

    override func stopLoading() {}
}

/// A handler token belongs to one test's URLSession. Requests carrying an old token fail closed
/// after that scope is released, so a delayed request can never enter the next test's handler.
final class CapturingURLProtocolScope {
    let token: String

    init(handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) {
        token = CapturingURLProtocol.installScopedHandler(handler)
    }

    func configuration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
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
        configuration.protocolClasses = [CapturingURLProtocol.self]
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
        configuration.protocolClasses = [CapturingURLProtocol.self]
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
        configuration.protocolClasses = [CapturingURLProtocol.self]
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
