import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Shared URLProtocol stub for client tests: install on an ephemeral `URLSessionConfiguration` and
/// set `requestHandler` to inspect the outgoing request + return a canned response. Used by
/// `SyncClientTests` and `AppleAuthClientTests` (so it must not be `private` to one file).
final class CapturingURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

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
        guard let requestHandler = Self.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }

        do {
            let (response, data) = try requestHandler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
