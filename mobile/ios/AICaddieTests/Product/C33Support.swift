#if !SWIFT_PACKAGE
import Foundation
import XCTest
@testable import AICaddie

// A nonblocking protocol: holding a request never blocks URLProtocol's serial delivery queue.
final class C33URLProtocol: URLProtocol {
    static var onStart: ((C33URLProtocol) -> Void)?
    static var onStop: ((URLRequest) -> Void)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { if let handler = Self.onStart { handler(self) } else { reply(404) } }
    override func stopLoading() { Self.onStop?(request) }
    func reply(_ status: Int, _ data: Data = Data()) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil
        )!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    static func session() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        configuration.httpMaximumConnectionsPerHost = 1
        return URLSession(configuration: configuration)
    }
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
func c33Model(_ store: OfflineStore, _ client: SyncClient) -> LiveRoundAppModel {
    LiveRoundAppModel(
        offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
        garminSessionStore: nil, syncClient: client,
        offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil
    )
}
#endif
