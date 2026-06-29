import AuthenticationServices
import SwiftUI

/// The app's single entry. Everyone signs in with Apple; the backend decides owner vs family member.
/// No admin token, no backend config — a shippable consumer screen. Apple's identity token is
/// exchanged for a backend session via `AppleAuthClient`; the result is stored in `SessionStore`.
public struct SignInView: View {
    private let apiBaseURL: URL?
    private let authClient: AppleAuthClient?
    private let onSignedIn: (AppSession) -> Void

    @State private var errorText: String?
    @State private var working = false

    public init(apiBaseURL: URL?, authClient: AppleAuthClient? = nil, onSignedIn: @escaping (AppSession) -> Void) {
        self.apiBaseURL = apiBaseURL
        self.authClient = authClient
        self.onSignedIn = onSignedIn
    }

    public var body: some View {
        ZStack {
            Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255).ignoresSafeArea()
            VStack(spacing: 18) {
                Spacer()
                Image(systemName: "flag.checkered")
                    .font(.system(size: 56))
                    .foregroundStyle(LiveHoleStyle.green)
                Text("AI 高尔夫球童")
                    .font(.largeTitle.bold())
                Text("用 Apple 登录,开始你的球场备战、记分与球童建议。")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 36)
                Spacer()
                if let errorText {
                    Text(errorText)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 36)
                }
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.fullName]
                } onCompletion: { result in
                    handle(result)
                }
                .signInWithAppleButtonStyle(.black)
                .frame(height: 50)
                .padding(.horizontal, 36)
                .disabled(working)
                Text("家庭成员各自登录、各看各的数据。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 36)
            }
        }
    }

    private func handle(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .failure(let error):
            errorText = "登录未完成:\(error.localizedDescription)"
        case .success(let auth):
            guard
                let credential = auth.credential as? ASAuthorizationAppleIDCredential,
                let tokenData = credential.identityToken,
                let identityToken = String(data: tokenData, encoding: .utf8)
            else {
                errorText = "无法获取 Apple 身份凭证,请重试。"
                return
            }
            let name = [credential.fullName?.givenName, credential.fullName?.familyName]
                .compactMap { $0 }
                .joined(separator: " ")
            guard let apiBaseURL else {
                errorText = "暂时无法连接服务器,请检查网络后重试。"
                return
            }
            let client = authClient ?? AppleAuthClient(baseURL: apiBaseURL)
            working = true
            errorText = nil
            Task {
                do {
                    let response = try await client.signIn(identityToken: identityToken, displayName: name.isEmpty ? nil : name)
                    let expires = response.expiresAt.flatMap { ISO8601DateFormatter().date(from: $0) }
                    onSignedIn(AppSession(token: response.token, playerId: response.playerId ?? "me", expiresAt: expires))
                } catch {
                    errorText = "登录失败,请检查网络后重试。"
                }
                working = false
            }
        }
    }
}
