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
    /// Latest pull status from the owning app model. It lets this account page say "已连接；本次
    /// 同步失败" instead of erasing a valid account state after a transient network error.
    public let garminSyncStatus: String?
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
    @State private var capturedSession: CapturedGarminWebSession?
    @State private var backgroundSyncStarted = false

    public init(
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore(),
        onSessionImported: (() async -> Bool)? = nil,
        onSessionImportedOutcome: (() async -> GarminSyncOutcome)? = nil,
        garminSyncStatus: String? = nil
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.sessionStore = sessionStore
        self.onSessionImported = onSessionImported
        self.onSessionImportedOutcome = onSessionImportedOutcome
        self.garminSyncStatus = garminSyncStatus
    }

    public var body: some View {
        Form {
            Section("Garmin") {
                Button {
                    webLoginStatus = "请在 Garmin 页面完成登录"
                    capturedSession = nil
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
                if shouldShowStoredSessionRetry {
                    Button {
                        retryStoredSessionSync()
                    } label: {
                        Label("重试同步", systemImage: "arrow.clockwise")
                    }
                    .disabled(isImporting || storedSessionSyncInProgress)
                    .accessibilityIdentifier("garmin-retry-sync")
                }
            }
        }
        .navigationTitle("连接 Garmin")
        .task {
            refreshStoredSessionPresentation()
            startStoredSessionSyncIfNeeded()
        }
        .onChange(of: garminSyncStatus) { _, _ in
            refreshStoredSessionPresentation()
        }
        .sheet(isPresented: $showingWebLogin) {
            NavigationStack {
                VStack(spacing: 0) {
                    if capturedSession != nil {
                        verificationPanel
                    } else {
                        GarminWebSessionCaptureView(
                            onCaptured: { captured in
                                // Freeze the web status as soon as cookies are captured. Garmin's
                                // dashboard can emit a later generic toast while our API validation
                                // is running; that toast must not overwrite the app's explanation.
                                capturedSession = captured
                                Task {
                                    await importCapturedSession(captured)
                                }
                            },
                            retryToken: loginRetryToken,
                            onStatus: { status in
                                guard capturedSession == nil else { return }
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
                }
                .navigationTitle("登录 Garmin")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            if let capturedSession, !isImporting {
                                Task { await importCapturedSession(capturedSession) }
                            } else {
                                loginRetryToken &+= 1
                            }
                        } label: {
                            Label(capturedSession == nil ? "检查登录" : "重试验证", systemImage: "arrow.clockwise")
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
        capturedSession = captured
        guard let apiBaseURL else {
            statusText = "Garmin 网页已登录，但 App 后端未配置"
            webLoginStatus = "登录信息已捕获，但 App 还没有可用的后端地址"
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
            statusText = Self.pendingStatusText(syncStatus: garminSyncStatus)
            webLoginStatus = "登录已保存，正在同步；完成后会自动显示已连接"
            showingWebLogin = false
            capturedSession = nil
            startBackgroundSync()
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
        GarminSyncPresentation.importErrorMessage(error)
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
            statusText = Self.pendingStatusText(syncStatus: garminSyncStatus)
            return
        }
        connected = true
        statusText = Self.connectedStatusText(syncStatus: garminSyncStatus)
    }

    static func connectedStatusText(syncStatus: String?) -> String {
        guard let status = syncStatus?.trimmingCharacters(in: .whitespacesAndNewlines),
              !status.isEmpty,
              status != "尚未手动更新" else {
            return "已连接"
        }
        if status.contains("失败") || status.contains("不可用") || status.contains("未完成") {
            return "已连接 · 本次同步失败"
        }
        if status.contains("正在") {
            return "已连接 · 正在同步"
        }
        return "已连接"
    }

    static func pendingStatusText(syncStatus: String?) -> String {
        guard let status = syncStatus?.trimmingCharacters(in: .whitespacesAndNewlines),
              !status.isEmpty,
              status != "尚未手动更新" else {
            return "登录已保存，正在同步"
        }
        if status.contains("登录已过期") || status.contains("会话无效") {
            return "Garmin 登录已过期，请重新连接"
        }
        if status.contains("失败") || status.contains("不可用") || status.contains("未完成") || status.contains("可重试") {
            return "登录已保存；本次同步失败，请稍后重试"
        }
        if status.contains("同步") || status.contains("正在") {
            return "登录已保存，正在同步"
        }
        return "登录已保存，正在同步"
    }

    private var storedSessionSyncInProgress: Bool {
        guard let status = garminSyncStatus else { return false }
        return status.contains("正在") || status.contains("进行") || status.contains("拉取")
    }

    private var shouldShowStoredSessionRetry: Bool {
        guard let material = loadStoredSession(), material.verifiedAt == nil else { return false }
        return !storedSessionSyncInProgress || garminSyncStatus?.contains("失败") == true
    }

    @ViewBuilder
    private var verificationPanel: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: isImporting ? "arrow.triangle.2.circlepath" : "checkmark.shield")
                .font(.system(size: 42))
                .foregroundStyle(isImporting ? LiveHoleStyle.green : .secondary)
            Text(statusText)
                .font(.headline)
                .multilineTextAlignment(.center)
            Text(webLoginStatus)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
            if isImporting {
                ProgressView()
                    .accessibilityIdentifier("garmin-verification-progress")
            } else {
                Button {
                    retryCapturedSession()
                } label: {
                    Label("重试验证", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
                .disabled(capturedSession == nil)
                Button {
                    returnToGarminLogin()
                } label: {
                    Label("返回 Garmin 登录", systemImage: "arrow.uturn.backward.circle")
                }
                .buttonStyle(.bordered)
            }
            Spacer()
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("garmin-verification-panel")
    }

    @MainActor
    private func retryCapturedSession() {
        guard let capturedSession, !isImporting else { return }
        backgroundSyncStarted = false
        Task { await importCapturedSession(capturedSession) }
    }

    @MainActor
    private func retryStoredSessionSync() {
        guard !isImporting, !storedSessionSyncInProgress else { return }
        backgroundSyncStarted = false
        startBackgroundSync()
    }

    @MainActor
    private func returnToGarminLogin() {
        guard !isImporting else { return }
        capturedSession = nil
        webLoginStatus = "请在 Garmin 页面完成登录"
        loginRetryToken &+= 1
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

    @MainActor
    private func startStoredSessionSyncIfNeeded() {
        guard let material = loadStoredSession(), material.verifiedAt == nil else { return }
        startBackgroundSync()
    }

    @MainActor
    private func startBackgroundSync() {
        guard !backgroundSyncStarted else { return }
        guard onSessionImportedOutcome != nil || onSessionImported != nil else { return }
        backgroundSyncStarted = true
        statusText = Self.pendingStatusText(syncStatus: garminSyncStatus)
        Task { @MainActor in
            defer { backgroundSyncStarted = false }
            let outcome: GarminSyncOutcome
            if let onSessionImportedOutcome {
                outcome = await onSessionImportedOutcome()
            } else if let onSessionImported {
                outcome = (await onSessionImported()) ? .completed : .failed
            } else {
                outcome = .failed
            }
            applySyncOutcome(outcome)
        }
    }

    @MainActor
    private func applySyncOutcome(_ outcome: GarminSyncOutcome) {
        switch outcome {
        case .completed:
            guard markStoredSessionVerified() else {
                connected = false
                statusText = "同步完成，但连接状态保存失败"
                return
            }
            connected = true
            statusText = "已连接 · 同步完成"
            webLoginStatus = "已连接 · 同步完成"
        case .inProgress:
            connected = false
            statusText = "登录已保存，正在同步"
            webLoginStatus = "同步正在后台进行，完成后会自动更新"
        case .reauthRequired:
            connected = false
            statusText = "Garmin 登录已过期，请重新连接"
            webLoginStatus = "Garmin 会话已失效，请重新登录"
        case .failed:
            connected = false
            statusText = "登录已保存；本次同步失败，请稍后重试"
            webLoginStatus = "登录已保存；本次同步未完成，请稍后重试"
        }
    }

}
