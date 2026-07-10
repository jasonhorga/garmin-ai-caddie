#if DEBUG
import SwiftUI

/// UITEST-only screen (`-uitest-screen wc-push-demo`): pumps a "walking toward the green" live state to a
/// PAIRED watch sim over WatchConnectivity, so the watch's companion glance (WatchHoleView) shows its
/// 到旗 distance counting down as the phone pushes — the phone→watch interaction, recordable on the watch
/// sim. Drives the REAL `WatchEventBridge.sendStateToWatch` path; no real round, no backend write. DEBUG
/// only — never compiled into a shipped build.
struct WcPushDemoView: View {
    @State private var step = 0
    @State private var bridge = WatchEventBridge(autoActivate: true)
    private let total = 16
    private let ticker = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "applewatch.radiowaves.left.and.right")
                .font(.system(size: 44)).foregroundStyle(LiveHoleStyle.green)
            Text("正在向手表推送实时距离").font(.headline)
            Text("模拟走向果岭 · 第 \(min(step, total))/\(total) 步")
                .font(.subheadline).foregroundStyle(.secondary)
            ProgressView(value: Double(min(step, total)), total: Double(total))
                .tint(LiveHoleStyle.green).padding(.horizontal, 40)
        }
        .onAppear { bridge.sendDemoState(step: 0, total: total) }
        .onReceive(ticker) { _ in
            guard step < total else { return }
            step += 1
            bridge.sendDemoState(step: step, total: total)
        }
    }
}
#endif
