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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(course).font(.footnote).opacity(0.9)
                Spacer()
                Text("⛳︎ 第 \(holeNumber)/\(holeCount)").font(.footnote).opacity(0.9)
            }
            Text("第 \(holeNumber) 洞 · Par \(par)").font(.title2.weight(.bold))
            HStack(spacing: 10) {
                HeaderStat(value: toPinYards.map(String.init) ?? "—", label: "到旗杆(米)")
                HeaderStat(value: carryFrontYards.map(String.init) ?? "—", label: "过前缘")
                HeaderStat(value: toParText, label: "本洞")
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

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(clubs, id: \.self) { club in
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
        }
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
