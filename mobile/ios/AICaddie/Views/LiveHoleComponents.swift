import SwiftUI

// Presentational building blocks for the redesigned 实战/记分 (live hole) screen.
// Pure views: plain inputs + closures, no app state or networking — so they
// compile-check independently and can be composed into CurrentHoleView next
// without disturbing its existing logic. Mirrors the approved HTML mockup
// (caddie-recommendation-first, GPS record, compact score).

enum LiveHoleStyle {
    static let green = Color(red: 21 / 255, green: 128 / 255, blue: 61 / 255)
    static let tint = Color(red: 231 / 255, green: 243 / 255, blue: 236 / 255)
    static let warnBg = Color(red: 247 / 255, green: 226 / 255, blue: 221 / 255)
    static let warnInk = Color(red: 162 / 255, green: 63 / 255, blue: 44 / 255)
    static let line = Color(red: 231 / 255, green: 233 / 255, blue: 236 / 255)
}

/// Trim a raw ISO datetime ("2026-05-20T08:00:00+08:00") to a clean date ("2026-05-20")
/// for display — the live screens show user-facing dates, never raw timestamps.
func aiCaddieShortDate(_ raw: String) -> String {
    let trimmed = raw.trimmingCharacters(in: .whitespaces)
    if let tIndex = trimmed.firstIndex(of: "T") {
        return String(trimmed[..<tIndex])
    }
    return trimmed
}

/// Full-screen centered loading — fills the area so the parent's background shows uniformly, with a
/// spinner + caption. Replaces the sparse "white screen + lonely spinner + grey strip" look that a
/// bare ProgressView inside a ScrollView produced while a fetch was in flight.
struct AICaddieLoadingView: View {
    var text: String = "载入中…"

    var body: some View {
        VStack(spacing: 10) {
            ProgressView()
            Text(text).font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A small rounded chip; `warn` flips it to the risk palette.
struct HoleChip: View {
    let text: String
    var warn: Bool = false

    var body: some View {
        Text(text)
            .font(.caption)
            .padding(.vertical, 5)
            .padding(.horizontal, 10)
            .background(warn ? LiveHoleStyle.warnBg : LiveHoleStyle.tint)
            .foregroundStyle(warn ? LiveHoleStyle.warnInk : LiveHoleStyle.green)
            .clipShape(Capsule())
    }
}

/// One distance/score readout inside the green header.
private struct HeaderStat: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 2) {
            Text(value).font(.title2.weight(.heavy))
            Text(label).font(.caption2)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(Color.white.opacity(0.16))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

/// Green header: course + hole/par + the distance trio.
struct HoleDistanceHeader: View {
    let course: String
    let holeNumber: Int
    let holeCount: Int
    let par: Int
    let toPinYards: Int?
    let carryFrontYards: Int?
    let toParText: String
    // round-13 LIVE: 前/中/后果岭 (F/M/B, 码) + 坡度补偿 (±码) from the per-hole prep geometry.
    // All optional — a hole without usable geometry shows none of them (no "—" noise).
    var greenFrontYards: Int? = nil
    var greenCenterYards: Int? = nil
    var greenBackYards: Int? = nil
    var slopeYards: Int? = nil
    // round-13 B1: true when the 前/中/后果岭 numbers are LIVE GPS distances (recomputed from the
    // phone's CoreLocation fix), not the static tee→green prep values — shows a subtle 实时 badge so
    // the player can tell the two apart.
    var isGreenLive: Bool = false

    private var hasGreenTriad: Bool { greenFrontYards != nil || greenCenterYards != nil || greenBackYards != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(course).font(.footnote).opacity(0.9)
                Spacer()
                Text("⛳︎ 第 \(holeNumber)/\(holeCount)").font(.footnote).opacity(0.9)
            }
            Text("第 \(holeNumber) 洞 · Par \(par)").font(.title2.weight(.bold))
            HStack(spacing: 10) {
                HeaderStat(value: toPinYards.map(String.init) ?? "—", label: "到旗杆(码)")
                // 过前缘只在有数据时显示,空着写「—」是噪声(round-10 反馈)。
                if let carryFrontYards {
                    HeaderStat(value: String(carryFrontYards), label: "过前缘")
                }
                HeaderStat(value: toParText, label: "本洞")
            }
            if hasGreenTriad {
                HStack(spacing: 10) {
                    if let greenFrontYards { HeaderStat(value: String(greenFrontYards), label: "前果岭") }
                    if let greenCenterYards { HeaderStat(value: String(greenCenterYards), label: "中果岭") }
                    if let greenBackYards { HeaderStat(value: String(greenBackYards), label: "后果岭") }
                    if let slopeYards, slopeYards != 0 {
                        HeaderStat(value: "\(slopeYards > 0 ? "+" : "")\(slopeYards)", label: "坡度(码)")
                    }
                }
                if isGreenLive {
                    HStack(spacing: 5) {
                        Image(systemName: "location.fill").font(.caption2)
                        Text("实时果岭距离 · 随定位更新").font(.caption2)
                    }
                    .opacity(0.9)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LiveHoleStyle.green)
        .foregroundStyle(.white)
    }
}

/// The caddie recommendation card — the focal point of the screen.
struct CaddieRecCard: View {
    let modeTitle: String          // e.g. "球童建议 · 保守(护分)"
    let recommendation: String     // e.g. "7 号铁 · 上果岭中心偏左"
    let rationale: String
    let chips: [(text: String, warn: Bool)]
    var onSeePlan: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(modeTitle.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(LiveHoleStyle.green)
            Text(recommendation).font(.title3.weight(.bold))
            Text(rationale).font(.subheadline).foregroundStyle(.secondary)
            if !chips.isEmpty {
                HStack(spacing: 6) {
                    ForEach(Array(chips.enumerated()), id: \.offset) { item in
                        HoleChip(text: item.element.text, warn: item.element.warn)
                    }
                }
            }
            Button(action: onSeePlan) {
                Text("看完整方案 / 换打法 →")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
            }
            .buttonStyle(.plain)
            .background(Color.white)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(14)
        .background(Color.white)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(LiveHoleStyle.green, lineWidth: 1.5))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

/// Horizontal club selector chips.
struct ClubStripView: View {
    let clubs: [String]
    let selected: String
    var onSelect: (String) -> Void = { _ in }

    var perRow: Int = 5

    private var rows: [[String]] {
        guard perRow > 0 else { return [clubs] }
        return stride(from: 0, to: clubs.count, by: perRow).map { start in
            Array(clubs[start ..< min(start + perRow, clubs.count)])
        }
    }

    var body: some View {
        // Wrapping rows (not a horizontal ScrollView): keeps every club visible
        // and renders in the CI ImageRenderer snapshot — ScrollView content does
        // not render there.
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(rows.enumerated()), id: \.offset) { entry in
                HStack(spacing: 8) {
                    ForEach(entry.element, id: \.self) { club in
                        chip(club)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    private func chip(_ club: String) -> some View {
        Button { onSelect(club) } label: {
            Text(club)
                .font(.body.weight(.semibold))
                .padding(.vertical, 9)
                .padding(.horizontal, 13)
        }
        .buttonStyle(.plain)
        .foregroundStyle(club == selected ? Color.white : Color.primary)
        .background(club == selected ? LiveHoleStyle.green : Color.white)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

/// Big primary "记一杆 · GPS" action with an optional last-shot caption.
struct RecordShotButton: View {
    var title: String = "📍 记一杆 · GPS"
    var isLocating: Bool = false
    var lastShotText: String?
    var onTap: () -> Void = {}

    var body: some View {
        VStack(spacing: 7) {
            Button(action: onTap) {
                Text(isLocating ? "定位中…" : title)
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
            }
            .buttonStyle(.plain)
            .background(LiveHoleStyle.green)
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .disabled(isLocating)
            if let lastShotText {
                Text(lastShotText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

/// Compact score/putts steppers row.
struct HoleScoreSteppers: View {
    @Binding var score: Int
    @Binding var putts: Int

    var body: some View {
        HStack(spacing: 10) {
            stepper(title: "杆数", value: $score, range: 1...12)
            stepper(title: "推杆", value: $putts, range: 0...6)
        }
    }

    private func stepper(title: String, value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        VStack(spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button { if value.wrappedValue > range.lowerBound { value.wrappedValue -= 1 } } label: { Text("−").font(.title3) }
                    .buttonStyle(.plain).foregroundStyle(LiveHoleStyle.green)
                Spacer()
                Text("\(value.wrappedValue)").font(.title.weight(.heavy))
                Spacer()
                Button { if value.wrappedValue < range.upperBound { value.wrappedValue += 1 } } label: { Text("+").font(.title3) }
                    .buttonStyle(.plain).foregroundStyle(LiveHoleStyle.green)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(LiveHoleStyle.line))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

extension View {
    /// White rounded card used across the redesigned live-hole screen.
    func liveCard() -> some View {
        self
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white)
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(LiveHoleStyle.line))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

// MARK: - Dark play-screen (实战/记分) reskin — map-backdrop + Apple-Maps-style glass panel.
//
// The 打球屏 v2 design language: DARK base, the hole map as a full-screen backdrop, and a floating
// dark-glass data panel (big-number distance readout → caddie strip → score steppers → save → tab
// bar). Colours are hard-coded (never semantic) so the surface renders identically dark regardless
// of the app's forced light colour scheme AND inside the CI ImageRenderer snapshot (which has no
// blur/material). Aligned to the Apple-Watch play sheet + the approved `ios_play2.html` mockup.
enum LivePlayStyle {
    static let base = Color(red: 5 / 255, green: 7 / 255, blue: 12 / 255)           // #05070c
    static let panelFill = Color(red: 14 / 255, green: 18 / 255, blue: 26 / 255)     // rgba(14,18,26,·)
    static let accent = Color(red: 34 / 255, green: 197 / 255, blue: 94 / 255)       // #22c55e
    static let accentSystem = Color(red: 52 / 255, green: 199 / 255, blue: 89 / 255) // #34c759
    static let onAccent = Color(red: 4 / 255, green: 20 / 255, blue: 10 / 255)       // #04140a
    static let front = Color(red: 92 / 255, green: 176 / 255, blue: 255 / 255)       // #5cb0ff 前
    static let back = Color(red: 154 / 255, green: 166 / 255, blue: 189 / 255)       // #9aa6bd 后
    static let hazard = Color(red: 255 / 255, green: 212 / 255, blue: 71 / 255)      // #ffd447
    static let greenLabel = Color(red: 95 / 255, green: 224 / 255, blue: 138 / 255)  // #5fe08a
    static let ink = Color.white
    static let ink78 = Color.white.opacity(0.78)
    static let ink60 = Color.white.opacity(0.60)
    static let ink50 = Color.white.opacity(0.50)
    static let ink45 = Color.white.opacity(0.45)
    static let hair = Color.white.opacity(0.09)
    static let fill08 = Color.white.opacity(0.08)
    static let fill12 = Color.white.opacity(0.12)
    static let stroke10 = Color.white.opacity(0.10)
    static let stroke14 = Color.white.opacity(0.14)
    /// Top scrim so the header stays legible over a bright hole map.
    static let topScrim = LinearGradient(
        colors: [base.opacity(0.94), base.opacity(0.6), base.opacity(0)],
        startPoint: .top, endPoint: .bottom
    )
}

/// Header over the map: 第 N 洞 + Par/码/Tee (left) + 本场 to-par chip (right).
struct LivePlayHeader: View {
    let holeNumber: Int
    let par: Int
    let yards: Int?
    let teeLabel: String?
    let roundToParText: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 1) {
                Text("第 \(holeNumber) 洞")
                    .font(.system(size: 19, weight: .heavy))
                    .foregroundStyle(LivePlayStyle.ink)
                Text(subtitle)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer(minLength: 0)
            Text(roundToParText)
                .font(.system(size: 13, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .padding(.vertical, 5)
                .padding(.horizontal, 11)
                .background(LivePlayStyle.panelFill.opacity(0.7), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(LivePlayStyle.stroke14))
        }
    }

    private var subtitle: String {
        var parts = ["Par \(par)"]
        if let yards { parts.append("\(yards) 码") }
        if let teeLabel, !teeLabel.isEmpty { parts.append(teeLabel) }
        return parts.joined(separator: " · ")
    }
}

/// The hero distance readout: 前 / 到果岭中 / 后, tabular figures, the centre is the single XL number.
/// Mirrors the shared DistanceStack (F/C/B): 前=front-blue, 中=XL white, 后=back-gray.
struct LiveDistanceReadout: View {
    let greenFrontYards: Int?
    let greenCenterYards: Int?
    let greenBackYards: Int?
    let toPinYards: Int?
    let isGreenLive: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 6) {
            side(label: "前", value: greenFrontYards, color: LivePlayStyle.front)
            VStack(spacing: 2) {
                Text("到果岭中")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink60)
                Text(greenCenterYards.map(String.init) ?? "—")
                    .font(.system(size: 66, weight: .heavy))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(unitLine)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .frame(maxWidth: .infinity)
            side(label: "后", value: greenBackYards, color: LivePlayStyle.back)
        }
    }

    private var unitLine: String {
        if isGreenLive { return "码 · 实时" }
        if let toPinYards { return "码 · 到旗杆 \(toPinYards)" }
        return "码"
    }

    private func side(label: String, value: Int?, color: Color) -> some View {
        VStack(spacing: 3) {
            Text(label).font(.system(size: 11, weight: .heavy)).foregroundStyle(LivePlayStyle.ink50)
            Text(value.map(String.init) ?? "—")
                .font(.system(size: 28, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(color)
        }
        .frame(width: 72)
    }
}

/// One club chip inside the caddie strip: recommended = filled green, others = outlined.
struct LiveClubChip: View {
    let name: String
    let sub: String
    let on: Bool
    var onTap: () -> Void = {}

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 1) {
                Text(name).font(.system(size: 15, weight: .heavy)).monospacedDigit()
                if !sub.isEmpty {
                    Text(sub)
                        .font(.system(size: 11, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(on ? LivePlayStyle.onAccent.opacity(0.72) : LivePlayStyle.ink50)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .padding(.horizontal, 2)
            .foregroundStyle(on ? LivePlayStyle.onAccent : LivePlayStyle.ink)
            .background(on ? LivePlayStyle.accent : Color.clear, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(on ? LivePlayStyle.accent : LivePlayStyle.stroke14, lineWidth: 1.5))
        }
        .buttonStyle(.plain)
    }
}

/// Caddie strip: ● 球童建议 + 展开 › · a row of club chips · one 实打 plays-like line.
struct LiveCaddieStrip: View {
    struct Club: Identifiable {
        let id = UUID()
        let name: String
        let sub: String
        let on: Bool
    }

    let clubs: [Club]
    var playsText: String?
    var isLoading: Bool = false
    var errorText: String?
    var onExpand: () -> Void = {}
    var onSelect: (String) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Circle().fill(LivePlayStyle.accentSystem).frame(width: 7, height: 7)
                Text("球童建议").font(.system(size: 13, weight: .heavy)).foregroundStyle(LivePlayStyle.greenLabel)
                Spacer(minLength: 0)
                Button(action: onExpand) {
                    Text("展开 ›").font(.system(size: 12, weight: .bold)).foregroundStyle(LivePlayStyle.ink45)
                }
                .buttonStyle(.plain)
            }
            if !clubs.isEmpty {
                HStack(spacing: 8) {
                    ForEach(clubs) { club in
                        LiveClubChip(name: club.name, sub: club.sub, on: club.on) { onSelect(club.name) }
                    }
                }
            }
            if let playsText {
                Text(playsText)
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink78)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if isLoading {
                HStack(spacing: 6) {
                    ProgressView().tint(LivePlayStyle.ink60)
                    Text("更新球童建议…").font(.caption).foregroundStyle(LivePlayStyle.ink60)
                }
            }
            if let errorText {
                Text(errorText).font(.caption).foregroundStyle(LivePlayStyle.ink60)
            }
        }
    }
}

/// Two symmetric score steppers (杆 − N ＋ / 推 − N ＋) with circular −/＋ buttons that never clip.
struct LivePlayScoreSteppers: View {
    @Binding var score: Int
    @Binding var putts: Int

    var body: some View {
        HStack(spacing: 9) {
            stepper("杆", value: $score, range: 1 ... 12)
            stepper("推", value: $putts, range: 0 ... 6)
        }
    }

    private func stepper(_ label: String, value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack(spacing: 9) {
            Text(label).font(.system(size: 13, weight: .bold)).foregroundStyle(LivePlayStyle.ink60)
            circleButton("−") { if value.wrappedValue > range.lowerBound { value.wrappedValue -= 1 } }
            Text("\(value.wrappedValue)")
                .font(.system(size: 22, weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .frame(minWidth: 22)
            circleButton("＋") { if value.wrappedValue < range.upperBound { value.wrappedValue += 1 } }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .padding(.horizontal, 8)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(LivePlayStyle.stroke10))
    }

    private func circleButton(_ glyph: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(glyph)
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(LivePlayStyle.accentSystem)
                .frame(width: 26, height: 26)
                .background(LivePlayStyle.fill12, in: Circle())
        }
        .buttonStyle(.plain)
    }
}

/// Full-width green primary — 保存本洞 ✓ — with an optional GPS caption line beneath.
struct LiveSaveButton: View {
    var title: String = "保存本洞 ✓"
    var caption: String?
    var onTap: () -> Void = {}

    var body: some View {
        VStack(spacing: 6) {
            Button(action: onTap) {
                Text(title)
                    .font(.system(size: 16, weight: .heavy))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .foregroundStyle(LivePlayStyle.onAccent)
                    .background(LivePlayStyle.accent, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
            }
            .buttonStyle(.plain)
            if let caption {
                Text(caption)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(LivePlayStyle.ink45)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
    }
}

/// Line-icon tab bar (洞图 / 记分 / 球童 / 球场 / 更多). Visual language only — the live screen's real
/// navigation is the NavigationStack back gesture; these mirror the mockup's bottom rail.
struct LivePlayTabBar: View {
    var body: some View {
        HStack(spacing: 0) {
            tab("map", "洞图", on: true)
            tab("list.bullet.rectangle", "记分", on: false)
            tab("scope", "球童", on: false)
            tab("flag", "球场", on: false)
            tab("ellipsis", "更多", on: false)
        }
    }

    private func tab(_ symbol: String, _ label: String, on: Bool) -> some View {
        VStack(spacing: 4) {
            Image(systemName: symbol).font(.system(size: 18, weight: .regular))
            Text(label).font(.system(size: 10.5, weight: .semibold))
        }
        .frame(maxWidth: .infinity)
        .foregroundStyle(on ? LivePlayStyle.accentSystem : LivePlayStyle.ink45)
    }
}

/// White crosshair reticle marking the green on the map backdrop.
struct LivePlayReticle: View {
    var body: some View {
        ZStack {
            Circle().stroke(Color.white, lineWidth: 2.5).frame(width: 46, height: 46)
            Rectangle().fill(Color.white).frame(width: 2, height: 60)
            Rectangle().fill(Color.white).frame(width: 60, height: 2)
        }
        .shadow(color: .black.opacity(0.35), radius: 1.5)
    }
}

/// One amber hazard "carry" pill over the map (e.g. 过水 235).
struct LiveHazardPill: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.system(size: 12, weight: .heavy))
            .monospacedDigit()
            .foregroundStyle(LivePlayStyle.hazard)
            .padding(.vertical, 4)
            .padding(.horizontal, 11)
            .background(Color(red: 10 / 255, green: 14 / 255, blue: 20 / 255).opacity(0.8), in: Capsule())
            .overlay(Capsule().stroke(LivePlayStyle.hazard.opacity(0.5)))
            .shadow(color: .black.opacity(0.45), radius: 6, y: 4)
    }
}

/// Apple-Maps-style dark-glass bottom panel: a grab handle + the stacked data sections.
struct LivePlayPanel<Content: View>: View {
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 12) {
            Capsule().fill(Color.white.opacity(0.22)).frame(width: 36, height: 5)
            content
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity)
        .background(LivePlayStyle.panelFill.opacity(0.94), in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 28).stroke(LivePlayStyle.stroke10))
    }
}

#Preview("Live hole components") {
    ScrollView {
        VStack(spacing: 12) {
            HoleDistanceHeader(
                course: "北京丽宫 · 前九", holeNumber: 7, holeCount: 9, par: 4,
                toPinYards: 152, carryFrontYards: 138, toParText: "+1"
            )
            VStack(spacing: 12) {
                CaddieRecCard(
                    modeTitle: "球童建议 · 保守(护分)",
                    recommendation: "7 号铁 · 上果岭中心偏左",
                    rationale: "右侧沙坑 138–150 码,落点避开;球道偏窄,优先保帕。",
                    chips: [(text: "期望失分最低", warn: false), (text: "命中 64%", warn: false), (text: "右沙坑", warn: true)]
                )
                ClubStripView(clubs: ["5i", "6i", "7i", "8i", "9i", "PW"], selected: "7i")
                RecordShotButton(lastShotText: "本洞已记 1 杆 · 上杆 7i · ±4m")
                HoleScoreSteppers(score: .constant(4), putts: .constant(2))
            }
            .padding(.horizontal, 14)
        }
    }
    .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
}
