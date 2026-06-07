import Foundation
#if canImport(Security)
import Security
#endif

public struct BackendConfigurationStore {
    private static let apiBaseURLKey = "ai-caddie.api-base-url"
    private static let adminTokenService = "com.ai-caddie.mobile.backend"
    private static let adminTokenAccount = "admin-token"

    public static func loadAPIBaseURL() -> URL? {
        normalizedAPIBaseURL(from: UserDefaults.standard.string(forKey: apiBaseURLKey))
    }

    public static func saveAPIBaseURL(_ url: URL?) {
        if let url {
            UserDefaults.standard.set(url.absoluteString, forKey: apiBaseURLKey)
        } else {
            UserDefaults.standard.removeObject(forKey: apiBaseURLKey)
        }
    }

    public static func loadAdminToken() -> String? {
        KeychainAdminToken.load(service: adminTokenService, account: adminTokenAccount)
    }

    public static func saveAdminToken(_ token: String?) {
        KeychainAdminToken.save(token, service: adminTokenService, account: adminTokenAccount)
    }

    public static func normalizedAPIBaseURL(from value: String?) -> URL? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let trimmed, !trimmed.isEmpty, !trimmed.contains("$(") else {
            return nil
        }
        guard var components = URLComponents(string: trimmed) else {
            return nil
        }
        guard components.scheme?.lowercased() == "https",
              components.host?.isEmpty == false,
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil else {
            return nil
        }
        guard components.percentEncodedPath.isEmpty || components.percentEncodedPath == "/" else {
            return nil
        }
        components.percentEncodedPath = ""
        return components.url
    }
}

private enum KeychainAdminToken {
    static func load(service: String, account: String) -> String? {
        #if canImport(Security)
        var query = baseQuery(service: service, account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else {
            return nil
        }
        let token = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return token?.isEmpty == false ? token : nil
        #else
        let token = UserDefaults.standard.string(forKey: "\(service).\(account)")?.trimmingCharacters(in: .whitespacesAndNewlines)
        return token?.isEmpty == false ? token : nil
        #endif
    }

    static func save(_ token: String?, service: String, account: String) {
        let trimmed = token?.trimmingCharacters(in: .whitespacesAndNewlines)
        #if canImport(Security)
        SecItemDelete(baseQuery(service: service, account: account) as CFDictionary)
        guard let trimmed, !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else {
            return
        }
        var item = baseQuery(service: service, account: account)
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(item as CFDictionary, nil)
        #else
        if let trimmed, !trimmed.isEmpty {
            UserDefaults.standard.set(trimmed, forKey: "\(service).\(account)")
        } else {
            UserDefaults.standard.removeObject(forKey: "\(service).\(account)")
        }
        #endif
    }

    #if canImport(Security)
    private static func baseQuery(service: String, account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
    #endif
}
