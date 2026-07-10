import SwiftUI

/// Watch design-system #15: 设置 — the round's on-watch settings (reached from the 球局 menu page).
/// A short toggle/stepper list: GPS 预热, 大字模式, 佩戴手 (informs swing detection). Presentational.
public struct WatchSettingsView: View {
    public let gpsPrewarm: Bool
    public let bigText: Bool
    public let wristRight: Bool

    public init(gpsPrewarm: Bool = true, bigText: Bool = false, wristRight: Bool = false) {
        self.gpsPrewarm = gpsPrewarm
        self.bigText = bigText
        self.wristRight = wristRight
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("设置").font(.headline.weight(.bold)).padding(.bottom, 2)
            toggleRow("GPS 预热", on: gpsPrewarm)
            toggleRow("大字模式", on: bigText)
            row("佩戴手", value: wristRight ? "右手" : "左手")
        }
        .padding(8)
    }

    private func toggleRow(_ label: String, on: Bool) -> some View {
        HStack {
            Text(label).font(.system(size: 14))
            Spacer()
            ZStack(alignment: on ? .trailing : .leading) {
                Capsule().fill(on ? AICaddieDesignTokens.par : Color.white.opacity(0.18)).frame(width: 38, height: 22)
                Circle().fill(.white).frame(width: 18, height: 18).padding(2)
            }
        }
        .padding(.vertical, 7)
        .overlay(alignment: .bottom) { Divider() }
    }

    private func row(_ label: String, value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 14))
            Spacer()
            Text(value).font(.system(size: 13, weight: .semibold)).foregroundStyle(.secondary)
        }
        .padding(.vertical, 7)
        .overlay(alignment: .bottom) { Divider() }
    }
}
