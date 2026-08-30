import Foundation
import CryptoKit
import SwiftUI
import WebKit

public struct CapturedGarminWebSession: Equatable {
    public let webSessionHeader: String
    public let antiForgeryValue: String
    public let capturedAt: String
}

public struct GarminWebSessionCaptureView: UIViewRepresentable {
    public let startURL: URL
    public let retryToken: Int
    public let onStatus: (String) -> Void
    public let onCaptured: (CapturedGarminWebSession) -> Void

    public init(
        startURL: URL = URL(string: "https://connect.garmin.cn/modern/")!,
        onCaptured: @escaping (CapturedGarminWebSession) -> Void,
        retryToken: Int = 0,
        onStatus: @escaping (String) -> Void = { _ in }
    ) {
        self.startURL = startURL
        self.retryToken = retryToken
        self.onStatus = onStatus
        self.onCaptured = onCaptured
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(onCaptured: onCaptured, onStatus: onStatus, retryToken: retryToken)
    }

    public func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = WKWebsiteDataStore.default()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        if Self.isOfficialGarminHost(startURL.host) {
            webView.load(URLRequest(url: startURL))
        } else {
            context.coordinator.report("不支持的 Garmin 登录页面")
        }
        return webView
    }

    public func updateUIView(_ uiView: WKWebView, context: Context) {
        context.coordinator.updateRetryToken(retryToken, webView: uiView)
    }

    /// Accept only Garmin-owned hosts, including official SSO redirects, while rejecting lookalikes
    /// such as `evilgarmin.com` and all unrelated third-party domains.
    static func isOfficialGarminHost(_ host: String?) -> Bool {
        guard let host else { return false }
        let normalized = host.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
        return normalized == "garmin.com"
            || normalized.hasSuffix(".garmin.com")
            || normalized == "garmin.cn"
            || normalized.hasSuffix(".garmin.cn")
    }

    static func officialGolfURL(from url: URL) -> URL? {
        guard isOfficialGarminHost(url.host),
              let scheme = url.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = url.host?.lowercased(), host.hasPrefix("connect.") else {
            return nil
        }
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        guard components?.path != "/app/golf" else { return nil }
        components?.path = "/app/golf"
        components?.query = nil
        components?.fragment = nil
        return components?.url
    }

    public final class Coordinator: NSObject, WKNavigationDelegate {
        private let onCaptured: (CapturedGarminWebSession) -> Void
        private let onStatus: (String) -> Void
        private let formatter = ISO8601DateFormatter()
        private var lastFingerprint: String?
        private var lastRetryToken: Int
        private var golfProbeUsed = false

        init(
            onCaptured: @escaping (CapturedGarminWebSession) -> Void,
            onStatus: @escaping (String) -> Void,
            retryToken: Int
        ) {
            self.onCaptured = onCaptured
            self.onStatus = onStatus
            self.lastRetryToken = retryToken
        }

        func updateRetryToken(_ token: Int, webView: WKWebView) {
            guard token != lastRetryToken else { return }
            lastRetryToken = token
            golfProbeUsed = false
            // An explicit user retry must be able to re-import the same valid material after a
            // transient backend failure; automatic navigation callbacks remain fingerprint-deduped.
            lastFingerprint = nil
            retryCapture(from: webView)
        }

        func retryCapture(from webView: WKWebView) {
            guard GarminWebSessionCaptureView.isOfficialGarminHost(webView.url?.host) else {
                report("不支持的 Garmin 登录页面")
                return
            }
            report("正在检查 Garmin 登录状态…")
            captureSessionMaterial(from: webView)
        }

        func report(_ status: String) {
            DispatchQueue.main.async { [onStatus] in
                onStatus(status)
            }
        }

        public func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url,
                  let scheme = url.scheme?.lowercased(),
                  ["http", "https"].contains(scheme),
                  GarminWebSessionCaptureView.isOfficialGarminHost(url.host)
            else {
                report("不支持的 Garmin 登录页面")
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        public func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            report("正在检查 Garmin 登录状态…")
        }

        public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            captureSessionMaterial(from: webView)
        }

        public func webView(
            _ webView: WKWebView,
            didFail navigation: WKNavigation!,
            withError error: Error
        ) {
            report("Garmin 页面加载失败，请检查网络后重试")
        }

        public func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: Error
        ) {
            report("Garmin 页面加载失败，请检查网络后重试")
        }

        private func captureSessionMaterial(from webView: WKWebView) {
            guard GarminWebSessionCaptureView.isOfficialGarminHost(webView.url?.host) else {
                report("不支持的 Garmin 登录页面")
                return
            }
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { [weak self, weak webView] cookies in
                guard let self, let webView else {
                    return
                }
                let garminCookies = cookies.filter { GarminWebSessionCaptureView.isOfficialGarminHost($0.domain) }
                let cookiePairs = Self.garminCookiePairs(from: garminCookies)
                guard !cookiePairs.isEmpty else {
                    self.report("尚未找到 Garmin 登录信息，请先完成登录")
                    return
                }
                webView.evaluateJavaScript(Self.csrfProbeScript) { value, _ in
                    let antiForgery = Self.antiForgeryValue(from: garminCookies, javaScriptValue: value)
                    guard !antiForgery.isEmpty else {
                        self.report("已找到 Garmin Cookie，但尚未找到安全校验信息")
                        self.probeOfficialGolfPageIfNeeded(from: webView)
                        return
                    }
                    let webSessionHeader = cookiePairs.joined(separator: "; ")
                    let fingerprint = Self.sessionFingerprint(
                        webSessionHeader: webSessionHeader,
                        antiForgeryValue: antiForgery
                    )
                    guard fingerprint != self.lastFingerprint else {
                        return
                    }
                    self.lastFingerprint = fingerprint
                    self.report("已找到 Garmin 登录信息，正在连接")
                    self.onCaptured(
                        CapturedGarminWebSession(
                            webSessionHeader: webSessionHeader,
                            antiForgeryValue: antiForgery,
                            capturedAt: self.formatter.string(from: Date())
                        )
                    )
                }
            }
        }

        private func probeOfficialGolfPageIfNeeded(from webView: WKWebView) {
            guard !golfProbeUsed,
                  let currentURL = webView.url,
                  let golfURL = GarminWebSessionCaptureView.officialGolfURL(from: currentURL) else {
                return
            }
            golfProbeUsed = true
            report("正在检查 Garmin 球场页面…")
            webView.load(URLRequest(url: golfURL))
        }

        private static func garminCookiePairs(from cookies: [HTTPCookie]) -> [String] {
            var seen = Set<String>()
            return cookies
                .filter { cookie in
                    let domain = cookie.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
                    return GarminWebSessionCaptureView.isOfficialGarminHost(domain)
                }
                .compactMap { cookie in
                    guard !cookie.name.isEmpty else {
                        return nil
                    }
                    let pair = "\(cookie.name)=\(cookie.value)"
                    guard !seen.contains(pair) else {
                        return nil
                    }
                    seen.insert(pair)
                    return pair
                }
        }

        private static func antiForgeryValue(from cookies: [HTTPCookie], javaScriptValue: Any?) -> String {
            let csrfCookieNames = ["connect-csrf-token", "csrf", "csrf_token", "xsrf-token", "x-csrf-token"]
            if let cookie = cookies.first(where: { csrfCookieNames.contains($0.name.lowercased()) }) {
                return cookie.value.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if let value = javaScriptValue as? String {
                return value.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return ""
        }

        private static func sessionFingerprint(webSessionHeader: String, antiForgeryValue: String) -> String {
            let data = Data("\(webSessionHeader)\n\(antiForgeryValue)".utf8)
            let digest = SHA256.hash(data: data)
            return digest.map { String(format: "%02x", $0) }.joined()
        }

        private static let csrfProbeScript = """
        (() => {
          const meta = document.querySelector('meta[name="csrf-token"]');
          if (meta && meta.content) return meta.content;
          const keys = ['connect-csrf-token', 'csrf', 'csrf_token', 'xsrf-token', 'x-csrf-token'];
          for (const key of keys) {
            const value = window.localStorage.getItem(key) || window.sessionStorage.getItem(key);
            if (value) return value;
          }
          return '';
        })()
        """
    }
}
