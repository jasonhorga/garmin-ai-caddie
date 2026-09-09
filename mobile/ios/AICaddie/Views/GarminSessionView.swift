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
    /// The owning app model is the sole account-state authority. This view never reconstructs state
    /// from localized strings or from an independent "connected" Boolean.
    public let connectionState: GarminConnectionState
    /// Deprecated read-only compatibility projection for older callers.
    @available(*, deprecated, message: "Use connectionState instead")
    public var garminSyncStatus: String { connectionState.statusText }
    /// Kept for source compatibility with older callers. New callers should use the typed outcome
    /// callback so a busy sync is not collapsed into a generic Bool failure.
    public let onSessionImported: (() async -> Bool)?
    public let onSessionImportedOutcome: (() async -> GarminSyncOutcome)?
    public let onSessionForgot: () -> Void

    @State private var isImporting = false
    @State private var showingWebLogin = false
    @State private var webLoginStatus = "请在 Garmin 页面完成登录"
    @State private var loginRetryToken = 0
    @State private var capturedSession: CapturedGarminWebSession?
    @State private var backgroundSyncStarted = false
    @State private var transientErrorText: String?

    public init(
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore(),
        onSessionImported: (() async -> Bool)? = nil,
        onSessionImportedOutcome: (() async -> GarminSyncOutcome)? = nil,
        connectionState: GarminConnectionState = .disconnected,
        garminSyncStatus: String? = nil,
        onSessionForgot: @escaping () -> Void = {}
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.sessionStore = sessionStore
        self.onSessionImported = onSessionImported
        self.onSessionImportedOutcome = onSessionImportedOutcome
        self.connectionState = connectionState
        // Source compatibility only; all rendering and retry decisions use the typed state.
        _ = garminSyncStatus
        self.onSessionForgot = onSessionForgot
    }

    public var body: some View {
        Form {
            Section("Garmin") {
                Button {
                    webLoginStatus = "请在 Garmin 页面完成登录"
                    capturedSession = nil
                    transientErrorText = nil
                    showingWebLogin = true
                } label: {
                    Label(hasStoredSession ? "更换 Garmin 账号" : "连接 Garmin", systemImage: "link")
                }
                .disabled(isImporting)
                if hasStoredSession {
                    Button(role: .destructive) {
                        forgetStoredSession()
                    } label: {
                        Label("断开 Garmin", systemImage: "link.badge.minus")
                    }
                    .disabled(isImporting)
                }
                // The owning app model is the only source of truth for the account lifecycle. A
                // transient web/import error belongs to the verification sheet; rendering it here
                // alongside the model state used to produce contradictory labels such as
                // "网页已登录但未验证" and "已连接正在同步" at the same time.
                Text(connectionState.statusText)
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
            startStoredSessionSyncIfNeeded()
        }
        .onChange(of: connectionState) { _, _ in
            transientErrorText = nil
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
            transientErrorText = "Garmin 网页已登录，但服务暂时不可用"
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
            transientErrorText = nil
            webLoginStatus = "Garmin 登录已保存"
            showingWebLogin = false
            capturedSession = nil
            backgroundSyncStarted = false
            startBackgroundSync()
        } catch {
            if Self.shouldInvalidateAppleSession(error, environment: ProcessInfo.processInfo.environment) {
                SessionStore.shared.signOut()
            }
            let message = Self.importErrorMessage(error)
            transientErrorText = message
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
            transientErrorText = nil
            onSessionForgot()
            return
        }
        do {
            try sessionStore.deleteSession()
            transientErrorText = nil
            onSessionForgot()
        } catch {
            transientErrorText = "断开失败，请重试"
        }
    }

    private var storedSessionSyncInProgress: Bool {
        connectionState.isBusy || backgroundSyncStarted
    }

    private var shouldShowStoredSessionRetry: Bool {
        hasStoredSession && connectionState.canRetrySavedSession && !storedSessionSyncInProgress
    }

    private var hasStoredSession: Bool {
        loadStoredSession() != nil
    }

    @ViewBuilder
    private var verificationPanel: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: isImporting ? "arrow.triangle.2.circlepath" : "checkmark.shield")
                .font(.system(size: 42))
                .foregroundStyle(isImporting ? LiveHoleStyle.green : .secondary)
            Text(isImporting ? "正在保存 Garmin 登录" : (transientErrorText ?? "Garmin 登录已读取"))
                .font(.headline)
                .multilineTextAlignment(.center)
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
        guard loadStoredSession() != nil else { return }
        // A keychain session can outlive the in-memory model after a cold launch. Treat a stale
        // `.disconnected` projection the same as an unverified state so the saved account reconnects
        // automatically; verified terminal states remain untouched.
        guard connectionState == .disconnected
            || connectionState == .awaitingVerification
            || connectionState == .verificationFailed
            || connectionState == .syncFailed
            || connectionState == .persistenceFailed else {
            return
        }
        startBackgroundSync()
    }

    @MainActor
    private func startBackgroundSync() {
        guard !backgroundSyncStarted else { return }
        guard onSessionImportedOutcome != nil || onSessionImported != nil else { return }
        backgroundSyncStarted = true
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
        // Typed production callbacks update `connectionState` in the owning model before returning.
        // Only the legacy Bool bridge needs a local fallback when it cannot publish that state.
        guard onSessionImportedOutcome == nil else { return }
        switch outcome {
        case .completed:
            transientErrorText = nil
        case .inProgress:
            transientErrorText = nil
        case .reauthRequired:
            transientErrorText = GarminConnectionState.reauthRequired.statusText
        case .failed:
            transientErrorText = GarminConnectionState.verificationFailed.statusText
        }
    }

}
