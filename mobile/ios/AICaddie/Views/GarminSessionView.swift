import Foundation
import SwiftUI

public struct GarminSessionView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let sessionStore: GarminSessionStore?

    @State private var webSessionHeader = ""
    @State private var antiForgeryValue = ""
    @State private var statusText = "Session material not imported"
    @State private var isImporting = false
    @State private var cachedSessionAvailable = false

    public init(
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore()
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.sessionStore = sessionStore
    }

    public var body: some View {
        Form {
            Section("Garmin CN") {
                SecureField("Web session header", text: $webSessionHeader, axis: .vertical)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("CSRF token", text: $antiForgeryValue)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button {
                    Task {
                        await importSession()
                    }
                } label: {
                    Label("Import session", systemImage: "key")
                }
                .disabled(isImporting)
                if cachedSessionAvailable {
                    Button {
                        Task {
                            await importStoredSession()
                        }
                    } label: {
                        Label("Import stored session", systemImage: "key.viewfinder")
                    }
                    .disabled(isImporting)
                    Button(role: .destructive) {
                        forgetStoredSession()
                    } label: {
                        Label("Forget stored session", systemImage: "trash")
                    }
                }
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Garmin Session")
        .task {
            cachedSessionAvailable = hasStoredSession()
        }
    }

    @MainActor
    private func importSession() async {
        guard let apiBaseURL else {
            statusText = "No sync server configured"
            return
        }
        let sessionHeader = webSessionHeader.trimmingCharacters(in: .whitespacesAndNewlines)
        let csrfToken = antiForgeryValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sessionHeader.isEmpty, !csrfToken.isEmpty else {
            statusText = "Session header and token are required"
            return
        }

        isImporting = true
        defer {
            isImporting = false
        }

        let client = GarminSessionClient(baseURL: apiBaseURL, adminToken: adminToken)
        do {
            let response = try await client.importSession(
                GarminSessionImportRequest(
                    webSessionHeader: sessionHeader,
                    antiForgeryValue: csrfToken,
                    source: "ios_secure_input"
                )
            )
            try sessionStore?.saveSession(
                GarminSessionMaterial(
                    webSessionHeader: sessionHeader,
                    antiForgeryValue: csrfToken,
                    storedAt: ISO8601DateFormatter().string(from: Date())
                )
            )
            statusText = response.detail
            webSessionHeader = ""
            antiForgeryValue = ""
            cachedSessionAvailable = hasStoredSession()
        } catch {
            statusText = "Session import or local storage failed"
        }
    }

    @MainActor
    private func importStoredSession() async {
        guard let apiBaseURL else {
            statusText = "No sync server configured"
            return
        }
        guard let material = loadStoredSession() else {
            statusText = "No stored session material"
            cachedSessionAvailable = false
            return
        }

        isImporting = true
        defer {
            isImporting = false
        }

        let client = GarminSessionClient(baseURL: apiBaseURL, adminToken: adminToken)
        do {
            let response = try await client.importSession(
                GarminSessionImportRequest(
                    webSessionHeader: material.webSessionHeader,
                    antiForgeryValue: material.antiForgeryValue,
                    source: "ios_keychain_replay"
                )
            )
            statusText = response.detail
            cachedSessionAvailable = hasStoredSession()
        } catch {
            statusText = "Stored session import failed"
        }
    }

    @MainActor
    private func forgetStoredSession() {
        guard let sessionStore else {
            cachedSessionAvailable = false
            statusText = "No stored session material"
            return
        }
        do {
            try sessionStore.deleteSession()
            cachedSessionAvailable = false
            statusText = "Stored session removed"
        } catch {
            statusText = "Stored session remove failed"
        }
    }

    private func loadStoredSession() -> GarminSessionMaterial? {
        guard let sessionStore else {
            return nil
        }
        do {
            return try sessionStore.loadSession()
        } catch {
            return nil
        }
    }

    private func hasStoredSession() -> Bool {
        loadStoredSession() != nil
    }
}
