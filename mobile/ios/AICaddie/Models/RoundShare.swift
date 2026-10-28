import Foundation

/// The server response for a product spec 9.5 read-only round share.
public struct RoundShare: Codable, Equatable, Identifiable {
    public let schema: String
    public let url: String
    public let pageUrl: String
    public let expiresAt: String
    public let shareId: String

    public var id: String { shareId }

    public init(schema: String, url: String, pageUrl: String, expiresAt: String, shareId: String) {
        self.schema = schema
        self.url = url
        self.pageUrl = pageUrl
        self.expiresAt = expiresAt
        self.shareId = shareId
    }

    /// Resolve the server's relative page path against the configured API origin. An absolute or
    /// scheme-relative response is rejected so a bad server response cannot send a share outside
    /// the configured backend origin.
    public func absolutePageURL(baseURL: URL) -> URL? {
        guard let relative = URL(string: pageUrl), relative.scheme == nil, relative.host == nil,
              pageUrl.hasPrefix("/") else { return nil }
        return URL(string: pageUrl, relativeTo: baseURL)?.absoluteURL
    }
}

public struct RoundShareRevocation: Codable, Equatable {
    public let revoked: Int
}

/// Presentation chosen after a share request. A missing/invalid response deliberately falls back
/// to the old plain-text share so offline or not-yet-uploaded rounds remain shareable.
public enum RoundSharePresentation: Equatable {
    case activityText(String)
    case plainText(String)

    public static func resolve(
        fallbackText: String,
        share: RoundShare?,
        baseURL: URL?
    ) -> RoundSharePresentation {
        guard let share, let baseURL, let pageURL = share.absolutePageURL(baseURL: baseURL) else {
            return .plainText(fallbackText)
        }
        return .activityText(fallbackText + "\n" + pageURL.absoluteString)
    }
}

/// Main-actor share orchestration keeps the request gate beside the injected transport. This lets
/// the view use the same flow instance for every tap while tests exercise failures without UIKit.
@MainActor
public final class RoundShareFlow {
    public typealias Create = (String) async throws -> RoundShare

    private let create: Create
    public let baseURL: URL?
    public private(set) var fallbackText: String
    public private(set) var isInFlight = false

    public init(create: @escaping Create, fallbackText: String, baseURL: URL?) {
        self.create = create
        self.fallbackText = fallbackText
        self.baseURL = baseURL
    }

    public func update(fallbackText: String) {
        self.fallbackText = fallbackText
    }

    public func share(roundRef: String) async -> RoundSharePresentation? {
        guard !isInFlight else { return nil }
        isInFlight = true
        let fallback = fallbackText
        defer { isInFlight = false }
        do {
            let share = try await create(roundRef)
            return RoundSharePresentation.resolve(
                fallbackText: fallback, share: share, baseURL: baseURL
            )
        } catch {
            return .plainText(fallback)
        }
    }
}
