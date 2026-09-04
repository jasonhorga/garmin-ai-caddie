import SwiftUI
import WatchKit

/// Round settings aligned to the approved Watch render. `GPS 预热` is a real preference: it keeps
/// location warm before a round, while an active round always retains GPS for truthful rangefinding.
public struct WatchSettingsView: View {
    @Binding public var gpsPreheatEnabled: Bool
    @Binding public var bigTextMode: Bool
    public let autoShotSupported: Bool
    public let autoShotEnabled: Bool
    public let autoShotStatus: String
    public let wristLabel: String
    public let onToggleAutoShot: () -> Void
    public let onBack: () -> Void

    public init(
        gpsPreheatEnabled: Binding<Bool>,
        bigTextMode: Binding<Bool>,
        autoShotSupported: Bool = false,
        autoShotEnabled: Bool = false,
        autoShotStatus: String = "本机不支持",
        wristLabel: String = WatchSettingsView.currentWristLabel,
        onToggleAutoShot: @escaping () -> Void = {},
        onBack: @escaping () -> Void = {}
    ) {
        self._gpsPreheatEnabled = gpsPreheatEnabled
        self._bigTextMode = bigTextMode
        self.autoShotSupported = autoShotSupported
        self.autoShotEnabled = autoShotEnabled
        self.autoShotStatus = autoShotStatus
        self.wristLabel = wristLabel
        self.onToggleAutoShot = onToggleAutoShot
        self.onBack = onBack
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                WatchInstrumentHeader("设置", backLabel: "返回菜单", onBack: onBack)

                Toggle("GPS 预热", isOn: $gpsPreheatEnabled)
                    .font(.system(size: 17, weight: .bold))
                    .toggleStyle(WatchApprovedToggleStyle())
                    .padding(.vertical, 7)
                Divider()

                Toggle("大字模式", isOn: $bigTextMode)
                    .font(.system(size: 17, weight: .bold))
                    .toggleStyle(WatchApprovedToggleStyle())
                    .padding(.vertical, 7)
                Divider()

                Toggle(
                    "自动记杆",
                    isOn: Binding(
                        get: { autoShotEnabled },
                        set: { requestedValue in
                            guard requestedValue != autoShotEnabled else { return }
                            onToggleAutoShot()
                        }
                    )
                )
                .font(.system(size: 17, weight: .bold))
                .toggleStyle(WatchApprovedToggleStyle())
                .disabled(!autoShotSupported)
                .accessibilityHint(autoShotSupported ? autoShotStatus : "本机不支持")
                .padding(.vertical, 7)
                Divider()

                HStack(spacing: 6) {
                    Text("佩戴手")
                        .font(.system(size: 17, weight: .bold))
                    Spacer(minLength: 4)
                    Text(wristLabel)
                        .font(.system(size: 16, weight: .black))
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 9)
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard value.startLocation.x <= 28,
                          value.translation.width >= 60,
                          abs(value.translation.height) < 50 else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回菜单"), onBack)
    }

    public static var currentWristLabel: String {
        WKInterfaceDevice.current().wristLocation == .right ? "右手" : "左手"
    }
}

private struct WatchApprovedToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(spacing: 8) {
                configuration.label
                Spacer(minLength: 4)
                ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                    Capsule()
                        .fill(configuration.isOn
                            ? Color(red: 0.10, green: 0.50, blue: 0.29)
                            : Color.white.opacity(0.18))
                    Circle()
                        .fill(.white)
                        .padding(2)
                }
                .frame(width: 44, height: 26)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityValue(configuration.isOn ? "开启" : "关闭")
    }
}
