import SwiftUI
import AICaddieDomain

/// The Watch turn (B4b-2 §7): the first half of an 18-hole course is finished, choose the second
/// nine with the shared `NineLoopPlan` — 前九 / 后九 (the other half preselected, the same half
/// allowed) or 只打 9 洞. The chosen half continues the same round on holes 10–18.
public struct WatchTurnView: View {
    public let plan: NineLoopPlan
    public let isLoading: Bool
    public let message: String?
    public let onChoose: (NineLoopPlan.Second) -> Void
    public let onConfirm: () -> Void
    public let onBack: () -> Void

    public init(
        plan: NineLoopPlan,
        isLoading: Bool = false,
        message: String? = nil,
        onChoose: @escaping (NineLoopPlan.Second) -> Void = { _ in },
        onConfirm: @escaping () -> Void = {},
        onBack: @escaping () -> Void = {}
    ) {
        self.plan = plan
        self.isLoading = isLoading
        self.message = message
        self.onChoose = onChoose
        self.onConfirm = onConfirm
        self.onBack = onBack
    }

    /// One row per half in course order, then 只打 9 洞. `id` is the accessibility identifier.
    static func choices(for plan: NineLoopPlan) -> [WatchRoundSetupChoicePresentation] {
        let halves = plan.course.loops.map { loop in
            WatchRoundSetupChoicePresentation(
                id: "watch-turn-half-\(loop.id.split(separator: ":").last.map(String.init) ?? loop.id)",
                title: loop.displayName,
                detail: loop.id == plan.first ? "再打一次" : "第 10–18 洞",
                isSelected: plan.second == .loop(loop.id)
            )
        }
        let stop = WatchRoundSetupChoicePresentation(
            id: "watch-turn-stop-after-nine",
            title: "只打 9 洞",
            detail: "结束本场",
            isSelected: plan.second == .stopAfterNine
        )
        return halves + [stop]
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                WatchInstrumentHeader(plan.turnTitle, backLabel: "返回第 9 洞", onBack: onBack)

                ForEach(Self.choices(for: plan)) { choice in
                    Button {
                        guard !isLoading else { return }
                        onChoose(second(for: choice.id))
                    } label: {
                        HStack(spacing: 7) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(choice.title)
                                    .font(.system(size: 16, weight: .black))
                                Text(choice.detail)
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 2)
                            if choice.isSelected {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 13, weight: .black))
                                    .foregroundStyle(AICaddieDesignTokens.par)
                            }
                        }
                        .padding(.horizontal, 10)
                        .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.white.opacity(choice.isSelected ? 0.12 : 0.06))
                        )
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(choice.id)
                    .accessibilityValue(choice.isSelected ? "已选择" : "未选择")
                }

                if let message {
                    Text(message)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.orange)
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(Color.orange.opacity(0.10))
                        )
                        .accessibilityIdentifier("watch-turn-message")
                }

                Button(action: onConfirm) {
                    HStack(spacing: 5) {
                        if isLoading {
                            ProgressView()
                                .controlSize(.small)
                        }
                        Text(isLoading ? "正在准备" : (message == nil ? plan.turnActionTitle : "重试 · \(plan.turnActionTitle)"))
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                    }
                    .font(.system(size: 16, weight: .black))
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .background(
                        AICaddieDesignTokens.par,
                        in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                    )
                }
                .buttonStyle(.plain)
                .disabled(isLoading)
                .opacity(isLoading ? 0.52 : 1)
                .accessibilityIdentifier("watch-turn-continue")
                .padding(.top, 4)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
            .padding(.bottom, 6)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
        .persistentSystemOverlays(.hidden)
    }

    private func second(for choiceId: String) -> NineLoopPlan.Second {
        guard choiceId != "watch-turn-stop-after-nine" else { return .stopAfterNine }
        let half = String(choiceId.dropFirst("watch-turn-half-".count))
        let loop = plan.course.loops.first { $0.id.hasSuffix(":\(half)") }
        return loop.map { .loop($0.id) } ?? .stopAfterNine
    }
}
