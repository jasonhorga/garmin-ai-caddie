import SwiftUI

struct LiveScoreConfirmationView: View {
    @Binding var draft: LiveScoreDraft
    let nextHole: Int?
    let onAccept: (LiveScoreDraft) -> Void
    let onCancel: () -> Void

    var body: some View {
        ZStack {
            LivePlayStyle.panelFill.ignoresSafeArea()
            VStack(spacing: 18) {
                header
                Group {
                    if draft.step == .recommendation {
                        recommendation
                    } else {
                        manualEntry
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 22)
            .padding(.top, 18)
            .padding(.bottom, 16)
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.height(430)])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled()
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                Text("第 \(draft.hole) 洞 · Par \(draft.par)")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(LivePlayStyle.ink)
                Text(draft.step == .recommendation ? "确认上一洞成绩" : manualStepTitle)
                    .font(.caption)
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer()
            Button("取消", action: onCancel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LivePlayStyle.ink60)
        }
    }

    private var recommendation: some View {
        VStack(spacing: 16) {
            VStack(spacing: 3) {
                Text("推荐 \(draft.score) 杆")
                    .font(.system(size: 42, weight: .heavy, design: .rounded))
                    .foregroundStyle(LivePlayStyle.ink)
                Text("\(draft.putts) 推 · \(draft.penalty) 罚杆")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                if let nextHole {
                    Text("确认后进入第 \(nextHole) 洞")
                        .font(.caption)
                        .foregroundStyle(LivePlayStyle.greenLabel)
                }
            }

            primaryButton("接受推荐 \(draft.score) 杆") {
                onAccept(draft)
            }
            secondaryButton("手动确认") {
                updateDraft { $0.startManualEntry() }
            }
        }
    }

    @ViewBuilder private var manualEntry: some View {
        VStack(spacing: 18) {
            switch draft.step {
            case .score:
                counter(title: "总杆", value: draft.score, lower: 1, upper: 20) { value in
                    draft.score = value
                    draft.putts = min(draft.putts, value)
                }
                primaryButton("下一步 · 推杆") { updateDraft { $0.advanceManualEntry() } }
            case .putts:
                counter(title: "推杆", value: draft.putts, lower: 0, upper: max(0, draft.score)) {
                    draft.putts = $0
                }
                primaryButton(draft.par == 3 ? "下一步 · 罚杆" : "下一步 · 开球结果") {
                    updateDraft { $0.advanceManualEntry() }
                }
            case .fairway:
                fairwayPicker
            case .penalty:
                counter(title: "罚杆", value: draft.penalty, lower: 0, upper: 10) {
                    draft.penalty = $0
                }
                primaryButton(nextHole.map { "保存并进入第 \($0) 洞" } ?? "保存本洞") {
                    onAccept(draft)
                }
            case .recommendation:
                EmptyView()
            }

            if draft.step != .recommendation {
                Button("‹ 返回上一步") { updateDraft { $0.retreatManualEntry() } }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .buttonStyle(.plain)
            }
        }
    }

    private var fairwayPicker: some View {
        VStack(spacing: 12) {
            Text("第一杆开球结果")
                .font(.title3.weight(.bold))
                .foregroundStyle(LivePlayStyle.ink)
            HStack(spacing: 9) {
                fairwayButton(.left, "偏左")
                fairwayButton(.hit, "上球道")
                fairwayButton(.right, "偏右")
            }
            Text("偏左 / 偏右均表示未上球道")
                .font(.caption)
                .foregroundStyle(LivePlayStyle.ink45)
        }
    }

    private func fairwayButton(_ result: LiveFairwayResult, _ label: String) -> some View {
        Button {
            updateDraft { $0.selectFairway(result) }
        } label: {
            Text(label)
                .font(.subheadline.weight(.bold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .foregroundStyle(draft.fairway == result ? LivePlayStyle.onAccent : LivePlayStyle.ink)
                .background(
                    draft.fairway == result ? LivePlayStyle.accent : LivePlayStyle.fill08,
                    in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                )
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(LivePlayStyle.stroke14))
        }
        .buttonStyle(.plain)
    }

    private func counter(
        title: String,
        value: Int,
        lower: Int,
        upper: Int,
        onChange: @escaping (Int) -> Void
    ) -> some View {
        VStack(spacing: 12) {
            Text(title)
                .font(.title3.weight(.bold))
                .foregroundStyle(LivePlayStyle.ink60)
            HStack(spacing: 28) {
                counterButton("−") { onChange(max(lower, value - 1)) }
                Text("\(value)")
                    .font(.system(size: 52, weight: .heavy, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                    .frame(minWidth: 70)
                counterButton("＋") { onChange(min(upper, value + 1)) }
            }
        }
    }

    private func counterButton(_ glyph: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(glyph)
                .font(.title2.weight(.bold))
                .foregroundStyle(LivePlayStyle.accentSystem)
                .frame(width: 52, height: 52)
                .background(LivePlayStyle.fill12, in: Circle())
        }
        .buttonStyle(.plain)
    }

    private func primaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.headline.weight(.heavy))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .foregroundStyle(LivePlayStyle.onAccent)
                .background(LivePlayStyle.accent, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func secondaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.headline.weight(.bold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .foregroundStyle(LivePlayStyle.ink)
                .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 15).stroke(LivePlayStyle.stroke14))
        }
        .buttonStyle(.plain)
    }

    private var manualStepTitle: String {
        switch draft.step {
        case .score: return "手动确认 · 总杆"
        case .putts: return "手动确认 · 推杆"
        case .fairway: return "手动确认 · 开球结果"
        case .penalty: return "手动确认 · 罚杆"
        case .recommendation: return "确认上一洞成绩"
        }
    }

    private func updateDraft(_ update: (inout LiveScoreDraft) -> Void) {
        var next = draft
        update(&next)
        draft = next
    }
}
