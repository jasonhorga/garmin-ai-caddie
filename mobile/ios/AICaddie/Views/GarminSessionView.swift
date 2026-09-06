import Foundation
import SwiftUI
import UIKit

/// 连接 Garmin:在内嵌网页里登录自己的 Garmin,我们只抓登录后的 cookie(不存密码)绑定到后端
/// (成员走 /players/{id}/…,owner 走 owner 路由)。纯网页登录流 —— 消费界面没有任何"会话头 /
/// CSRF / 令牌"之类的工程术语,用户只看到「连接 Garmin」→ 登录 → 「已连接」。
public struct GarminSessionView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let sessionStore: GarminSessionStore?
    /// Kept for source compatibility with older callers. New callers should use the typed outcome
    /// callback so a busy sync is not collapsed into a generic Bool failure.
    public let onSessionImported: (() async -> Bool)?
    public let onSessionImportedOutcome: (() async -> GarminSyncOutcome)?

    @State private var statusText = "未连接"
    @State private var isImporting = false
    @State private var connected = false
    @State private var showingWebLogin = false
    @State private var webLoginStatus = "请在 Garmin 页面完成登录"
    @State private var loginRetryToken = 0

    public init(
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore(),
        onSessionImported: (() async -> Bool)? = nil,
        onSessionImportedOutcome: (() async -> GarminSyncOutcome)? = nil
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.sessionStore = sessionStore
        self.onSessionImported = onSessionImported
        self.onSessionImportedOutcome = onSessionImportedOutcome
    }

    public var body: some View {
        Form {
            Section("Garmin") {
                Button {
                    webLoginStatus = "请在 Garmin 页面完成登录"
                    showingWebLogin = true
                } label: {
                    Label(connected ? "重新连接 Garmin" : "连接 Garmin", systemImage: "link")
                }
                .disabled(isImporting)
                if connected {
                    Button(role: .destructive) {
                        forgetStoredSession()
                    } label: {
                        Label("断开 Garmin", systemImage: "link.badge.minus")
                    }
                    .disabled(isImporting)
                }
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("连接 Garmin")
        .task {
            refreshStoredSessionPresentation()
        }
        .sheet(isPresented: $showingWebLogin) {
            NavigationStack {
                VStack(spacing: 0) {
                    GarminWebSessionCaptureView(
                        onCaptured: { captured in
                            Task {
                                await importCapturedSession(captured)
                            }
                        },
                        retryToken: loginRetryToken,
                        onStatus: { status in
                            webLoginStatus = status
                        }
                    )
                    HStack(spacing: 8) {
                        Image(systemName: "info.circle")
                            .foregroundStyle(.secondary)
                        Text(webLoginStatus)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color(uiColor: .secondarySystemBackground))
                }
                .navigationTitle("登录 Garmin")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            loginRetryToken &+= 1
                        } label: {
                            Label("检查登录", systemImage: "arrow.clockwise")
                        }
                        .disabled(isImporting)
                    }
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消") {
                            showingWebLogin = false
                        }
                    }
                }
            }
        }
    }

    @MainActor
    private func importCapturedSession(_ captured: CapturedGarminWebSession) async {
        guard !isImporting else { return }
        guard let apiBaseURL else {
            statusText = "暂无法连接,请稍后重试"
            webLoginStatus = "暂无法连接后端，请稍后重试"
            return
        }

        isImporting = true
        defer {
            isImporting = false
        }

        let client = GarminSessionClient(baseURL: apiBaseURL, adminToken: adminToken)
        do {
            _ = try await client.importSession(
                GarminSessionImportRequest(
                    webSessionHeader: captured.webSessionHeader,
                    antiForgeryValue: captured.antiForgeryValue,
                    source: "ios_web_login"
                )
            )
            try sessionStore?.saveSession(
                GarminSessionMaterial(
                    webSessionHeader: captured.webSessionHeader,
                    antiForgeryValue: captured.antiForgeryValue,
                    storedAt: captured.capturedAt,
                    verifiedAt: nil
                )
            )
            connected = false
            statusText = "正在验证 Garmin 登录"
            webLoginStatus = "已保存，正在验证 Garmin 数据访问…"

            let outcome: GarminSyncOutcome?
            if let onSessionImportedOutcome {
                outcome = await onSessionImportedOutcome()
            } else if let onSessionImported {
                outcome = (await onSessionImported()) ? .completed : .failed
            } else {
                outcome = nil
            }

            guard let outcome else {
                statusText = "待验证"
                webLoginStatus = "登录信息已保存，完成一次同步后才会显示已连接"
                showingWebLogin = false
                return
            }
            switch outcome {
            case .completed:
                guard markStoredSessionVerified() else {
                    connected = false
                    statusText = "验证结果未保存，请重试"
                    webLoginStatus = "Garmin 已完成同步，但本机验证状态保存失败，请重试"
                    return
                }
                connected = true
                statusText = "已连接 · 同步完成"
                webLoginStatus = "已连接 · 同步完成"
                showingWebLogin = false
            case .inProgress:
                connected = false
                statusText = "同步正在进行，请稍后查看"
                webLoginStatus = "同步正在进行，请稍后查看"
                showingWebLogin = false
            case .reauthRequired:
                connected = false
                statusText = "Garmin 登录验证失败，请重新连接"
                webLoginStatus = "Garmin 登录验证失败，请重新连接"
            case .failed:
                connected = false
                statusText = "Garmin 连接验证失败，请重试"
                webLoginStatus = "Garmin 连接验证失败，请重试"
            }
        } catch {
            if Self.shouldInvalidateAppleSession(error, environment: ProcessInfo.processInfo.environment) {
                SessionStore.shared.signOut()
            }
            let message = Self.importErrorMessage(error)
            statusText = message
            webLoginStatus = message
        }
    }

    static func shouldInvalidateAppleSession(
        _ error: Error,
        environment: [String: String]
    ) -> Bool {
        guard case let SyncClientError.http(status, _) = error, status == 401 else { return false }
        #if DEBUG
        return environment["UITEST_MODE"] != "1"
        #else
        _ = environment
        return true
        #endif
    }

    static func importErrorMessage(_ error: Error) -> String {
        if case let SyncClientError.http(status, _) = error, status == 401 {
            return "Apple 登录已失效，请重新登录"
        }
        if case let SyncClientError.http(status, _) = error, status == 403 {
            return "当前 Apple 账号无权连接此 Garmin"
        }
        if case let SyncClientError.http(status, _) = error, status == 409 {
            return "同步正在进行，请稍后重试"
        }
        if case let SyncClientError.http(status, _) = error, (400..<500).contains(status) {
            return "Garmin 登录信息无效，请重新登录"
        }
        return "连接失败，请重试"
    }

    @MainActor
    private func forgetStoredSession() {
        guard let sessionStore else {
            connected = false
            statusText = "未连接"
            return
        }
        do {
            try sessionStore.deleteSession()
            connected = false
            statusText = "已断开"
        } catch {
            statusText = "断开失败,请重试"
        }
    }

    @MainActor
    private func refreshStoredSessionPresentation() {
        guard let material = loadStoredSession() else {
            connected = false
            statusText = "未连接"
            return
        }
        guard material.verifiedAt != nil else {
            connected = false
            statusText = "待验证"
            return
        }
        connected = true
        statusText = "已连接"
    }

    /// Mark the exact captured material as verified only after a real Garmin sync completed. A
    /// missing keychain item is treated as a failed verification instead of showing a false green
    /// connection badge.
    @discardableResult
    private func markStoredSessionVerified() -> Bool {
        guard let sessionStore else { return true }
        do {
            guard let material = try sessionStore.loadSession() else { return false }
            if material.verifiedAt != nil { return true }
            let formatter = ISO8601DateFormatter()
            try sessionStore.saveSession(material.withVerifiedAt(formatter.string(from: Date())))
            return true
        } catch {
            return false
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

}
