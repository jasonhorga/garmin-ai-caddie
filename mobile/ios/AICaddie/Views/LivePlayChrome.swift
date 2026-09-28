import SwiftUI

/// Controls that float on the full-screen live hole map (IMPLEMENTATION_PLAN B1, `live-play.html`).
///
/// The map owns the screen; everything here is a small glass control on its edges:
/// top-left back + hole facts, top-right front / middle / back ladder, a left column of on-demand
/// controls (障碍 / 打法 / 回到), 记分 bottom-left and the single white 记一杆 bottom-right.
enum LivePlayChromeStyle {
    static let captionShadow = Color.black.opacity(0.7)
    static let flagRed = Color(red: 1, green: 0.54, blue: 0.5)
}

/// Frosted circle used by every secondary map control.
struct LivePlayGlassCircle<Label: View>: View {
    let diameter: CGFloat
    var pressed = false
    @ViewBuilder let label: () -> Label

    var body: some View {
        label()
            .foregroundStyle(pressed ? Color.black : Color.white)
            .frame(width: diameter, height: diameter)
            .background {
                if pressed {
                    Circle().fill(Color.white.opacity(0.94))
                } else {
                    Circle().fill(.ultraThinMaterial).environment(\.colorScheme, .dark)
                }
            }
            .overlay(Circle().stroke(Color.white.opacity(pressed ? 0 : 0.18), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.3), radius: 6, y: 2)
    }
}

/// A caption under a map control ("障碍", "记分", …); legible on any fairway colour.
struct LivePlayControlCaption: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(.white)
            .shadow(color: LivePlayChromeStyle.captionShadow, radius: 2, y: 1)
    }
}

/// Top-left: back, then the hole number, par and yards, and the round line underneath.
struct LivePlayTopInfo: View {
    let holeNumber: Int
    let par: Int
    let yards: Int?
    let roundLine: String
    let onBack: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Button(action: onBack) {
                LivePlayGlassCircle(diameter: 40) {
                    Image(systemName: "chevron.backward")
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("计分卡")
            .accessibilityHint("查看每洞成绩，也可以结束本场或回到首页")
            .accessibilityIdentifier("live-back-to-scorecard")

            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("\(holeNumber)")
                        .font(.system(size: 30, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .accessibilityLabel("第 \(holeNumber) 洞")
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("live-hole-title")
                    Text(subtitle)
                        .font(.system(size: 14, weight: .medium))
                        .monospacedDigit()
                }
                Text(roundLine)
                    .font(.system(size: 12.5, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.78))
                    .accessibilityIdentifier("live-round-line")
            }
            .foregroundStyle(.white)
            .shadow(color: LivePlayChromeStyle.captionShadow, radius: 3, y: 1)
        }
    }

    private var subtitle: String {
        var parts = ["Par \(par)"]
        if let yards { parts.append("\(yards) 码") }
        return parts.joined(separator: " · ")
    }
}

/// Top-right: the most-read numbers — back / middle / front of the green, plus the flag when one
/// has been placed. Without a live fix the ladder is the Tee's static reference and says so.
struct LivePlayGreenLadder: View {
    let frontYards: Int?
    let middleYards: Int?
    let backYards: Int?
    let flagYards: Int?
    let isLive: Bool

    var body: some View {
        VStack(spacing: 2) {
            edgeRow("后", backYards, identifier: "live-green-back")
            Text(GeoDistance.greenRangeText(middleYards))
                .font(.system(size: 44, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .accessibilityIdentifier("live-green-middle")
            edgeRow("前", frontYards, identifier: "live-green-front")
            if let flagYards, !GeoDistance.isBeyondUsefulGreenRange(flagYards) {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text("旗").font(.system(size: 11, weight: .semibold))
                    Text("\(flagYards)").font(.system(size: 15, weight: .bold, design: .rounded)).monospacedDigit()
                }
                .foregroundStyle(LivePlayChromeStyle.flagRed)
                .padding(.top, 2)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("到旗 \(flagYards) 码")
                .accessibilityIdentifier("live-green-flag")
            }
            Text(isLive ? "到果岭 · 码" : "发球台 · 码")
                .font(.system(size: 10.5, weight: .medium))
                .foregroundStyle(.white.opacity(0.62))
                .padding(.top, 2)
        }
        .foregroundStyle(.white)
        .frame(width: 92)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .environment(\.colorScheme, .dark)
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(Color.white.opacity(0.18), lineWidth: 0.5))
        .accessibilityElement(children: .contain)
        .accessibilityHint(isLive ? "距离根据当前位置实时计算。" : "这是发球台到果岭的静态参考，不代表当前位置。")
        .accessibilityIdentifier("live-green-ladder")
    }

    private func edgeRow(_ label: String, _ value: Int?, identifier: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(label).font(.system(size: 11, weight: .medium))
            Text(GeoDistance.greenRangeText(value))
                .font(.system(size: 14, weight: .medium, design: .rounded))
                .monospacedDigit()
                .accessibilityIdentifier(identifier)
        }
        .foregroundStyle(.white.opacity(0.7))
    }
}

/// Left column of on-demand controls. 回到 appears only after the map was zoomed or panned.
struct LivePlaySideControls: View {
    let hasHazards: Bool
    let hazardShown: Bool
    let planPosition: (index: Int, count: Int)?
    let showsRecenter: Bool
    let onToggleHazards: () -> Void
    let onNextPlan: () -> Void
    let onRecenter: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            if hasHazards {
                control(caption: "障碍") {
                    Button(action: onToggleHazards) {
                        LivePlayGlassCircle(diameter: 46, pressed: hazardShown) {
                            Image(systemName: "square.3.layers.3d")
                                .font(.system(size: 19, weight: .medium))
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(hazardShown ? "隐藏障碍" : "显示障碍")
                    .accessibilityAddTraits(hazardShown ? .isSelected : [])
                    .accessibilityIdentifier("live-hazard-toggle")
                }
            }
            if let planPosition, planPosition.count > 1 {
                control(caption: "打法") {
                    Button(action: onNextPlan) {
                        LivePlayGlassCircle(diameter: 46) {
                            Text("\(planPosition.index + 1)/\(planPosition.count)")
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                .monospacedDigit()
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("切换打法，当前第 \(planPosition.index + 1) 个，共 \(planPosition.count) 个")
                    .accessibilityIdentifier("live-plan-next")
                }
            }
            if showsRecenter {
                control(caption: "回到") {
                    Button(action: onRecenter) {
                        LivePlayGlassCircle(diameter: 46) {
                            Image(systemName: "location.north.fill")
                                .font(.system(size: 17, weight: .semibold))
                                .rotationEffect(.degrees(45))
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("回到整洞视图")
                    .accessibilityIdentifier("live-hero-map-reset-zoom")
                }
            }
        }
    }

    private func control<Content: View>(caption: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 4) {
            content()
            LivePlayControlCaption(text: caption)
        }
    }
}

/// Bottom-centre strip for the one selected obstacle: its name, "2 / 4" and ‹ ›.
struct LivePlayHazardBar: View {
    let row: LiveHazardDisplayItem
    let index: Int
    let count: Int
    let onPrevious: () -> Void
    let onNext: () -> Void

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(row.isWater ? Color(red: 0.36, green: 0.69, blue: 1) : Color(red: 0.92, green: 0.78, blue: 0.4))
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 1) {
                Text(row.label)
                    .font(.system(size: 12.5, weight: .bold))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text("\(index + 1) / \(count)")
                    .font(.system(size: 10.5, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.62))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            navigation("chevron.backward", label: "上一个障碍", identifier: "hazard-previous", disabled: index == 0, action: onPrevious)
            navigation("chevron.forward", label: "下一个障碍", identifier: "hazard-next", disabled: index >= count - 1, action: onNext)
        }
        .foregroundStyle(.white)
        .padding(.leading, 12)
        .padding(.trailing, 5)
        .frame(height: 50)
        .background(.ultraThinMaterial, in: Capsule())
        .environment(\.colorScheme, .dark)
        .overlay(Capsule().stroke(Color.white.opacity(0.18), lineWidth: 0.5))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("selected-hazard-\(index + 1)")
    }

    private func navigation(
        _ systemName: String,
        label: String,
        identifier: String,
        disabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 14, weight: .semibold))
                .frame(width: 32, height: 32)
                .background(Color.white.opacity(0.1), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.3 : 1)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }
}

/// Bottom-left: finish this hole (once per hole, away from 记一杆 to avoid mis-taps).
struct LivePlayScoreButton: View {
    let action: () -> Void

    var body: some View {
        VStack(spacing: 4) {
            Button(action: action) {
                LivePlayGlassCircle(diameter: 60) {
                    Image(systemName: "flag")
                        .font(.system(size: 22, weight: .medium))
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("完成本洞")
            .accessibilityHint("记分")
            .accessibilityIdentifier("live-score-hole")
            LivePlayControlCaption(text: "记分")
        }
    }
}

/// Bottom-right: the only solid white control — the most frequent action.
struct LivePlayRecordShotButton: View {
    let enabled: Bool
    let recordedShotCount: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 0) {
                Text("＋").font(.system(size: 26, weight: .light))
                Text("记一杆").font(.system(size: 12, weight: .bold))
            }
            .foregroundStyle(Color(red: 0.04, green: 0.06, blue: 0.05))
            .frame(width: 76, height: 76)
            .background(Color(red: 0.96, green: 0.96, blue: 0.95), in: Circle())
            .shadow(color: .black.opacity(0.45), radius: 9, y: 6)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
        .accessibilityLabel("记一杆")
        .accessibilityValue(recordedShotCount > 0 ? "已记第 \(recordedShotCount) 杆" : (enabled ? "" : "等待 GPS"))
        .accessibilityHint(enabled ? "在当前位置记录一杆" : "等待 GPS 定位")
        .accessibilityIdentifier("live-record-shot")
    }
}
