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
        private static let maxCaptureAttempts = 4
        private static let captureRetryDelay: TimeInterval = 0.25
        private let onCaptured: (CapturedGarminWebSession) -> Void
        private let onStatus: (String) -> Void
        private let formatter = ISO8601DateFormatter()
        private var lastFingerprint: String?
        private var lastRetryToken: Int
        private var golfProbeUsed = false
        private var captureGeneration = 0
        /// A page can finish several times while Garmin redirects and hydrates its session. Once
        /// one material has been handed to the importer, suppress those duplicate callbacks until
        /// the user explicitly asks for another check.
        private var captureInFlight = false

        static func shouldRetryCapture(attempt: Int) -> Bool {
            attempt >= 0 && attempt + 1 < maxCaptureAttempts
        }

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
            captureInFlight = false
            retryCapture(from: webView)
        }

        func retryCapture(from webView: WKWebView) {
            guard GarminWebSessionCaptureView.isOfficialGarminHost(webView.url?.host) else {
                report("不支持的 Garmin 登录页面")
                return
            }
            report("正在检查 Garmin 登录状态…")
            beginCapture(from: webView)
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
            // Invalidate a delayed cookie poll belonging to the previous page/redirect.
            captureGeneration &+= 1
            report("正在检查 Garmin 登录状态…")
        }

        public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            beginCapture(from: webView)
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

        private func beginCapture(from webView: WKWebView) {
            captureGeneration &+= 1
            captureSessionMaterial(from: webView, attempt: 0, generation: captureGeneration)
        }

        private func captureSessionMaterial(
            from webView: WKWebView,
            attempt: Int,
            generation: Int
        ) {
            guard GarminWebSessionCaptureView.isOfficialGarminHost(webView.url?.host) else {
                report("不支持的 Garmin 登录页面")
                return
            }
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { [weak self, weak webView] cookies in
                guard let self, let webView, generation == self.captureGeneration else {
                    return
                }
                let garminCookies = Self.chinaConnectCookies(from: cookies)
                let cookiePairs = Self.garminCookiePairs(from: garminCookies)
                guard !cookiePairs.isEmpty else {
                    if self.scheduleCaptureRetry(
                        from: webView,
                        attempt: attempt,
                        generation: generation
                    ) {
                        return
                    }
                    self.report("尚未找到 Garmin 登录信息，请先完成登录")
                    return
                }
                webView.evaluateJavaScript(Self.csrfProbeScript) { value, _ in
                    guard generation == self.captureGeneration else { return }
                    let antiForgery = Self.antiForgeryValue(
                        from: garminCookies,
                        javaScriptValue: value,
                        allowJavaScriptFallback: GarminWebSessionCaptureView.isChinaConnectCookieDomain(webView.url?.host)
                    )
                    guard !antiForgery.isEmpty else {
                        if self.scheduleCaptureRetry(
                            from: webView,
                            attempt: attempt,
                            generation: generation
                        ) {
                            return
                        }
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
                    guard !self.captureInFlight else { return }
                    self.captureInFlight = true
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

        @discardableResult
        private func scheduleCaptureRetry(
            from webView: WKWebView,
            attempt: Int,
            generation: Int
        ) -> Bool {
            guard Self.shouldRetryCapture(attempt: attempt) else { return false }
            DispatchQueue.main.asyncAfter(deadline: .now() + Self.captureRetryDelay) { [weak self, weak webView] in
                guard let self, let webView, generation == self.captureGeneration else { return }
                self.captureSessionMaterial(
                    from: webView,
                    attempt: attempt + 1,
                    generation: generation
                )
            }
            return true
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

        /// Cookie material is intentionally narrower than the navigation allow-list. SSO and
        /// tracking cookies from `garmin.com` are not valid connect.garmin.cn session material.
        static func isChinaConnectCookieDomain(_ domain: String?) -> Bool {
            guard let domain else { return false }
            let normalized = domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
            return normalized == "garmin.cn"
                || normalized == "connect.garmin.cn"
                || normalized.hasSuffix(".garmin.cn")
        }

        private static func chinaConnectCookies(from cookies: [HTTPCookie], now: Date = Date()) -> [HTTPCookie] {
            cookies
                .filter { cookie in
                    isChinaConnectCookieDomain(cookie.domain)
                        && (cookie.expiresDate == nil || cookie.expiresDate! > now)
                        && !cookie.name.isEmpty
                        && !cookie.value.isEmpty
                }
                .sorted { lhs, rhs in
                    let lhsDomain = lhs.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
                    let rhsDomain = rhs.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
                    let lhsHostRank = lhsDomain == "connect.garmin.cn" ? 1 : 0
                    let rhsHostRank = rhsDomain == "connect.garmin.cn" ? 1 : 0
                    if lhsHostRank != rhsHostRank { return lhsHostRank > rhsHostRank }
                    if lhsDomain.count != rhsDomain.count { return lhsDomain.count > rhsDomain.count }
                    if lhs.path.count != rhs.path.count { return lhs.path.count > rhs.path.count }
                    if lhs.name != rhs.name { return lhs.name < rhs.name }
                    return lhs.value < rhs.value
                }
        }

        static func garminCookiePairs(from cookies: [HTTPCookie]) -> [String] {
            var seenNames = Set<String>()
            let candidates = chinaConnectCookies(from: cookies)
            return candidates.compactMap { cookie in
                guard seenNames.insert(cookie.name).inserted else { return nil }
                return "\(cookie.name)=\(cookie.value)"
            }
        }

        static func antiForgeryValue(
            from cookies: [HTTPCookie],
            javaScriptValue: Any?,
            allowJavaScriptFallback: Bool = true
        ) -> String {
            let csrfCookieNames = ["connect-csrf-token", "csrf", "csrf_token", "xsrf-token", "x-csrf-token"]
            if let cookie = chinaConnectCookies(from: cookies).first(where: {
                csrfCookieNames.contains($0.name.lowercased())
            }) {
                return cookie.value.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if allowJavaScriptFallback, let value = javaScriptValue as? String {
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
