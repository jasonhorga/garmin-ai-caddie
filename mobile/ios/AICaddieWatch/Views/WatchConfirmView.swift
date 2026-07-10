import SwiftUI

/// Watch design-system #18: 确认页 — the ONLY confirm surface, reserved for the irreversible three
/// (结束本场 / 放弃 / 跳洞). The 「确认」 button sits OPPOSITE the trigger button's side to defeat a
/// double-tap misfire. Reversible actions never get a confirm. Presentational.
public struct WatchConfirmView: View {
    public let title: String
    public let detail: String?
    public let confirmLabel: String
    public let cancelLabel: String
    public let destructive: Bool
    public let onConfirm: () -> Void
    public let onCancel: () -> Void

    public init(
        title: String,
        detail: String? = nil,
        confirmLabel: String = "确认",
        cancelLabel: String = "返回",
        destructive: Bool = true,
        onConfirm: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.title = title
        self.detail = detail
        self.confirmLabel = confirmLabel
        self.cancelLabel = cancelLabel
        self.destructive = destructive
        self.onConfirm = onConfirm
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 4)
            Text(title).font(.system(size: 16, weight: .bold)).multilineTextAlignment(.center)
            if let detail {
                Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            Spacer(minLength: 4)
            // Cancel LEFT, confirm RIGHT (opposite the leading back-swipe) — misfire guard.
            HStack(spacing: 8) {
                Button(action: onCancel) {
                    Text(cancelLabel).font(.system(size: 13, weight: .semibold)).frame(maxWidth: .infinity).padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.12)))
                        .foregroundStyle(.white)
                }.buttonStyle(.plain)
                Button(action: onConfirm) {
                    Text(confirmLabel).font(.system(size: 13, weight: .bold)).frame(maxWidth: .infinity).padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 12).fill(destructive ? Color(red: 1.0, green: 0.27, blue: 0.23) : AICaddieDesignTokens.par))
                        .foregroundStyle(.white)
                }.buttonStyle(.plain)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
