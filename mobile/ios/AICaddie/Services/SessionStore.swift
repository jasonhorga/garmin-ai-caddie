import Foundation
import Security

/// A signed-in app session: the backend session token (minted by `/api/v2/auth/apple`), the
/// resolved player id (owner "me" or a member "p_*"), and when the token expires. Persisted so a
/// relaunch stays signed in.
public struct AppSession: Codable, Equatable {
    public let token: String
    public let playerId: String
    public let expiresAt: Date?

    public init(token: String, playerId: String, expiresAt: Date? = nil) {
        self.token = token
        self.playerId = playerId
        self.expiresAt = expiresAt
    }

    public var isExpired: Bool {
        guard let expiresAt else { return false }
        return expiresAt <= Date()
    }
}

/// Where a session is persisted. The real app uses the Keychain; tests/previews inject an in-memory
/// store so they never depend on a host-app Keychain (flaky in logic tests).
public protocol SessionPersisting {
    func read() -> AppSession?
    func write(_ session: AppSession)
    func clear()
}

/// Persists the signed-in session and publishes it so the app's sign-in gate reacts. Everyone signs
/// in with Apple → a session here; no admin token in the product.
@MainActor
public final class SessionStore: ObservableObject {
    public static let shared = SessionStore()

    @Published public private(set) var currentSession: AppSession?
    private let persisting: SessionPersisting

    public init(persisting: SessionPersisting = KeychainSessionPersisting()) {
        self.persisting = persisting
        self.currentSession = persisting.read()
    }

    public func save(_ session: AppSession) {
        currentSession = session
        persisting.write(session)
    }

    public func clear() {
        currentSession = nil
        persisting.clear()
    }
}

/// Keychain-backed persistence (service `com.ai-caddie.session`).
public struct KeychainSessionPersisting: SessionPersisting {
    private let service = "com.ai-caddie.session"
    private let account = "session"

    public init() {}

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    public func read() -> AppSession? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return try? JSONDecoder().decode(AppSession.self, from: data)
    }

    public func write(_ session: AppSession) {
        guard let data = try? JSONEncoder().encode(session) else { return }
        SecItemDelete(baseQuery as CFDictionary)
        var query = baseQuery
        query[kSecValueData as String] = data
        SecItemAdd(query as CFDictionary, nil)
    }

    public func clear() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

/// In-memory persistence for tests/previews.
public final class InMemorySessionPersisting: SessionPersisting {
    private var stored: AppSession?
    public init(_ initial: AppSession? = nil) { self.stored = initial }
    public func read() -> AppSession? { stored }
    public func write(_ session: AppSession) { stored = session }
    public func clear() { stored = nil }
}
