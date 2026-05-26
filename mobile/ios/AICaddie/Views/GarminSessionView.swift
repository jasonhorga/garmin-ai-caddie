import Foundation
import SwiftUI

public struct GarminSessionView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var webSessionHeader = ""
    @State private var antiForgeryValue = ""
    @State private var statusText = "Session material not imported"
    @State private var isImporting = false

    public init(apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
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
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Garmin Session")
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
                GarminSessionImportRequest(webSessionHeader: sessionHeader, antiForgeryValue: csrfToken)
            )
            statusText = response.detail
            webSessionHeader = ""
            antiForgeryValue = ""
        } catch {
            statusText = "Session import failed"
        }
    }
}
