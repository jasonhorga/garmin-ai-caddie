import SwiftUI

public struct BackendSettingsView: View {
    public let apiBaseURL: URL?
    public let adminTokenConfigured: Bool
    public let syncStatus: String
    public let onSave: (String, String?) -> Void
    public let onClear: () -> Void

    @State private var apiBaseURLText: String
    @State private var adminTokenText = ""

    public init(
        apiBaseURL: URL? = nil,
        adminTokenConfigured: Bool = false,
        syncStatus: String = "Offline ready",
        onSave: @escaping (String, String?) -> Void = { _, _ in },
        onClear: @escaping () -> Void = {}
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminTokenConfigured = adminTokenConfigured
        self.syncStatus = syncStatus
        self.onSave = onSave
        self.onClear = onClear
        self._apiBaseURLText = State(initialValue: apiBaseURL?.absoluteString ?? "")
    }

    public var body: some View {
        Form {
            Section("Backend") {
                TextField("API origin", text: $apiBaseURLText)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
#if DEBUG
                SecureField(adminTokenConfigured ? "New admin token" : "Admin token", text: $adminTokenText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                HStack {
                    Label(adminTokenConfigured ? "Token saved" : "No token", systemImage: adminTokenConfigured ? "checkmark.seal" : "exclamationmark.triangle")
                    .foregroundStyle(adminTokenConfigured ? .green : .secondary)
                    Spacer()
                    Text(connectionLabel)
                        .foregroundStyle(apiBaseURL == nil ? .secondary : .primary)
                }
                .font(.caption)
#endif
                Button {
#if DEBUG
                    let token = adminTokenText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : adminTokenText
#else
                    let token: String? = nil
#endif
                    onSave(apiBaseURLText, token)
                    adminTokenText = ""
                } label: {
                    Label("保存服务器", systemImage: "checkmark.circle")
                }
                Button(role: .destructive) {
                    onClear()
                    apiBaseURLText = ""
                    adminTokenText = ""
                } label: {
                    Label("恢复默认服务器", systemImage: "arrow.uturn.backward")
                }
            }

            Section("Status") {
                Text(syncStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("服务器连接")
    }

    private var connectionLabel: String {
        apiBaseURL?.host ?? "Offline"
    }
}
