import Combine
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
/// in with Apple → a session here; the admin token is only a DEBUG/CI fallback.
///
/// Thread-safety: networking runs off the main actor, so the live token + expiry are kept under a
/// lock and read synchronously by `applyAICaddieAuth` at REQUEST time (never a value captured once
/// at client init). `currentSession` is `@Published` for the SwiftUI gate and is only mutated on the
/// main thread.
public final class SessionStore: ObservableObject {
    public static let shared = SessionStore()

    @Published public private(set) var currentSession: AppSession?

    private let persisting: SessionPersisting
    private let lock = NSLock()
    private var liveTokenValue: String?
    private var liveExpiry: Date?

    public init(persisting: SessionPersisting = KeychainSessionPersisting()) {
        self.persisting = persisting
        let stored = persisting.read()
        if let stored, !stored.isExpired {
            self.currentSession = stored
            self.liveTokenValue = stored.token
            self.liveExpiry = stored.expiresAt
        } else {
            self.currentSession = nil
            if stored != nil {
                persisting.clear()  // never vend a stale/expired session
            }
        }
    }

    /// The live auth token, readable synchronously from ANY thread at request time. Returns nil once
    /// the token has expired, so an expired session never authenticates a request.
    public var liveToken: String? {
        lock.lock(); defer { lock.unlock() }
        if let liveExpiry, liveExpiry <= Date() { return nil }
        return liveTokenValue
    }

    public func save(_ session: AppSession) {
        lock.lock()
        liveTokenValue = session.token
        liveExpiry = session.expiresAt
        lock.unlock()
        publish(session)
        persisting.write(session)
    }

    /// Clear the session everywhere: the live token, the published session, and the Keychain.
    public func signOut() {
        lock.lock()
        liveTokenValue = nil
        liveExpiry = nil
        lock.unlock()
        publish(nil)
        persisting.clear()
    }

    public func clear() { signOut() }

    private func publish(_ session: AppSession?) {
        if Thread.isMainThread {
            currentSession = session
        } else {
            DispatchQueue.main.async { [weak self] in self?.currentSession = session }
        }
    }
}

/// Attach auth to a request, reading the LIVE session at request time. A signed-in session (Bearer)
/// wins; the admin token is only the DEBUG/CI fallback (a real Apple sign-in can't run on the
/// simulator). Every phone networking client routes through this so sign-in takes effect everywhere
/// immediately and a clean consumer build (no admin token) requires sign-in for every API call.
public func applyAICaddieAuth(to request: inout URLRequest, adminToken: String?) {
    if let token = SessionStore.shared.liveToken {
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return
    }
    // DEBUG/CI ONLY: a real Apple sign-in can't run on the simulator, so dev/test builds fall back to
    // an admin token. Consumer (Release) builds never load one (AICaddieApp.defaultAdminToken returns
    // nil in Release), so this branch is compiled out — and because the app gates on Apple sign-in, a
    // Release request always has a live session here. A Release request without a session carries no
    // auth header rather than an admin one.
    #if DEBUG
    if let adminToken {
        request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
    }
    #endif
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
