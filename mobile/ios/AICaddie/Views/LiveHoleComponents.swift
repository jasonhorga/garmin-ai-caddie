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
