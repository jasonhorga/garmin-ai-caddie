import AICaddieDomain
import SwiftUI

/// 打完第一个 9 洞 (README §8, `pre-round.html` at the turn): "B 场打完了 — 接着打哪个 9 洞". The
/// usual pairing is preselected; any loop, the same loop again, or 只打 9 洞 can be chosen. 稍后
/// closes the sheet without deciding; the choice stays open until the second loop's first hole.
struct LiveRoundTurnSheet: View {
    @State var plan: NineLoopPlan
    let isPreparing: Bool
    /// Shown when the last continuation could not add the loop; the choice stays actionable.
    var failureText: String? = nil
    let onContinue: (NineLoop) -> Void
    let onStop: () -> Void
    let onLater: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(plan.turnTitle)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                Button("稍后") {
                    guard Self.acceptsInput(isPreparing: isPreparing) else { return }
                    onLater()
                }
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .buttonStyle(.plain)
                    .disabled(isPreparing)
                    .accessibilityIdentifier("turn-later")
            }
            Text("接着打哪个 9 洞")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(LivePlayStyle.ink60)
            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: max(2, min(plan.course.loops.count, 3))),
                spacing: 8
            ) {
                ForEach(plan.course.loops, id: \.id) { loop in
                    loopTile(loop)
                }
            }
            stopTile
            if let failureText, !isPreparing {
                Label(failureText, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.orange)
                    .accessibilityIdentifier("turn-failure")
            }
            Button {
                guard Self.acceptsInput(isPreparing: isPreparing) else { return }
                if let loop = plan.secondLoop { onContinue(loop) } else { onStop() }
            } label: {
                HStack(spacing: 8) {
                    if isPreparing { ProgressView().tint(LiveScoreStyle.primaryInk) }
                    Text(plan.turnActionTitle)
                        .font(.system(size: 17, weight: .bold))
                }
                .foregroundStyle(LiveScoreStyle.primaryInk)
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(LiveScoreStyle.primaryFill, in: Capsule())
            }
            .buttonStyle(.plain)
            .disabled(isPreparing)
            .accessibilityIdentifier("turn-go")
        }
        .padding(.horizontal, 20)
        .padding(.top, 22)
        .padding(.bottom, 16)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(LivePlayStyle.panelFill.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(isPreparing)
    }

    /// While a continuation is in flight every control is frozen — 稍后, the loop tiles, 只打 9 洞
    /// and the CTA — so a different choice or a dismissal can never race the captured one, and the
    /// sheet is still there to offer a retry if it fails.
    static func acceptsInput(isPreparing: Bool) -> Bool { !isPreparing }

    private func loopTile(_ loop: NineLoop) -> some View {
        let selected = plan.second == .loop(loop.id)
        let isUsual = plan.course.usualSecond(after: plan.first) == loop.id
        return Button {
            guard Self.acceptsInput(isPreparing: isPreparing) else { return }
            plan.chooseSecond(.loop(loop.id))
        } label: {
            VStack(spacing: 3) {
                Text(loop.displayName)
                    .font(.system(size: 18, weight: .bold))
                Text(isUsual ? "上次搭配" : loop.par.map { "Par \($0)" } ?? "9 洞")
                    .font(.system(size: 12))
                    .monospacedDigit()
                    .opacity(0.7)
            }
            .foregroundStyle(selected ? LiveScoreStyle.primaryInk : LivePlayStyle.ink)
            .frame(maxWidth: .infinity)
            .frame(height: 64)
            .background(
                selected ? LiveScoreStyle.primaryFill : LivePlayStyle.fill08,
                in: RoundedRectangle(cornerRadius: 14, style: .continuous)
            )
        }
        .buttonStyle(.plain)
        .disabled(isPreparing)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier("turn-loop-\(loop.id)")
    }

    private var stopTile: some View {
        let selected = plan.second == .stopAfterNine
        return Button {
            guard Self.acceptsInput(isPreparing: isPreparing) else { return }
            plan.chooseSecond(.stopAfterNine)
        } label: {
            Text("不打了 · 只打 9 洞")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(selected ? LiveScoreStyle.primaryInk : LivePlayStyle.ink78)
                .frame(maxWidth: .infinity)
                .frame(height: 44)
                .background(
                    selected ? LiveScoreStyle.primaryFill : LivePlayStyle.fill08,
                    in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                )
        }
        .buttonStyle(.plain)
        .disabled(isPreparing)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier("turn-stop")
    }
}
