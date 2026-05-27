import Foundation
import Security

public struct GarminSessionMaterial: Codable, Equatable {
    public let webSessionHeader: String
    public let antiForgeryValue: String
    public let storedAt: String

    public init(webSessionHeader: String, antiForgeryValue: String, storedAt: String) {
        self.webSessionHeader = webSessionHeader
        self.antiForgeryValue = antiForgeryValue
        self.storedAt = storedAt
    }
}

public enum GarminSessionStoreError: Error, Equatable {
    case invalidItemData
    case unexpectedStatus(OSStatus)
}

public final class GarminSessionStore {
    private let service: String
    private let account: String
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(
        service: String = "com.ai-caddie.garmin-cn-session",
        account: String = "primary"
    ) {
        self.service = service
        self.account = account
    }

    public func saveSession(_ material: GarminSessionMaterial) throws {
        let data = try encoder.encode(material)
        let updateAttributes: [String: Any] = [
            kSecValueData as String: data,
        ]
        let updateStatus = SecItemUpdate(baseQuery() as CFDictionary, updateAttributes as CFDictionary)
        if updateStatus == errSecSuccess {
            return
        }
        if updateStatus == errSecItemNotFound {
            var query = baseQuery()
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            query[kSecValueData as String] = data
            let addStatus = SecItemAdd(query as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw GarminSessionStoreError.unexpectedStatus(addStatus)
            }
            return
        }
        throw GarminSessionStoreError.unexpectedStatus(updateStatus)
    }

    public func loadSession() throws -> GarminSessionMaterial? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw GarminSessionStoreError.unexpectedStatus(status)
        }
        guard let data = item as? Data else {
            throw GarminSessionStoreError.invalidItemData
        }
        return try decoder.decode(GarminSessionMaterial.self, from: data)
    }

    public func deleteSession() throws {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw GarminSessionStoreError.unexpectedStatus(status)
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
