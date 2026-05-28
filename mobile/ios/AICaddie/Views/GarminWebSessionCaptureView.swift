import Foundation
import SwiftUI
import WebKit

public struct CapturedGarminWebSession: Equatable {
    public let webSessionHeader: String
    public let antiForgeryValue: String
    public let capturedAt: String
}

public struct GarminWebSessionCaptureView: UIViewRepresentable {
    public let startURL: URL
    public let onCaptured: (CapturedGarminWebSession) -> Void

    public init(
        startURL: URL = URL(string: "https://connect.garmin.cn/modern/")!,
        onCaptured: @escaping (CapturedGarminWebSession) -> Void
    ) {
        self.startURL = startURL
        self.onCaptured = onCaptured
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(onCaptured: onCaptured)
    }

    public func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = WKWebsiteDataStore.default()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.load(URLRequest(url: startURL))
        return webView
    }

    public func updateUIView(_ uiView: WKWebView, context: Context) {}

    public final class Coordinator: NSObject, WKNavigationDelegate {
        private let onCaptured: (CapturedGarminWebSession) -> Void
        private let formatter = ISO8601DateFormatter()
        private var lastFingerprint: String?

        init(onCaptured: @escaping (CapturedGarminWebSession) -> Void) {
            self.onCaptured = onCaptured
        }

        public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            captureSessionMaterial(from: webView)
        }

        private func captureSessionMaterial(from webView: WKWebView) {
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { [weak self, weak webView] cookies in
                guard let self, let webView else {
                    return
                }
                let cookiePairs = Self.garminCookiePairs(from: cookies)
                guard !cookiePairs.isEmpty else {
                    return
                }
                webView.evaluateJavaScript(Self.csrfProbeScript) { value, _ in
                    let antiForgery = Self.antiForgeryValue(from: cookies, javaScriptValue: value)
                    guard !antiForgery.isEmpty else {
                        return
                    }
                    let webSessionHeader = cookiePairs.joined(separator: "; ")
                    let fingerprint = "\(webSessionHeader.count):\(antiForgery.count)"
                    guard fingerprint != self.lastFingerprint else {
                        return
                    }
                    self.lastFingerprint = fingerprint
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

        private static func garminCookiePairs(from cookies: [HTTPCookie]) -> [String] {
            var seen = Set<String>()
            return cookies
                .filter { cookie in
                    let domain = cookie.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased()
                    return domain == "garmin.cn" || domain.hasSuffix(".garmin.cn")
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
