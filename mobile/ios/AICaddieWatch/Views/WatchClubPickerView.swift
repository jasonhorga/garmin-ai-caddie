import SwiftUI

/// Watch design-system #17: 选杆浮层 — the ONE recording UI (the "face" of shot detection). It rises
/// after a detected/tapped shot; the top still shows the new 球位→旗 distance; the Digital Crown scrolls
/// clubs; the recommended club is centred + tagged 推荐; tapping a row records to the CURRENT hole
/// (regardless of GPS). Left ~8s untouched → auto-records the recommended club (marked 自动). Swipe down =
/// false positive, don't record. Presentational VStack (no List) so it renders in ImageRenderer snapshots.
public struct WatchClubPickerView: View {
    public struct Club: Identifiable, Equatable {
        public let name: String
        public let carryYd: Int?
        public var id: String { name }
        public init(name: String, carryYd: Int? = nil) {
            self.name = name
            self.carryYd = carryYd
        }
    }

    public let hole: Int
    public let toPinYd: Int
    public let clubs: [Club]
    public let recommended: String
    public let selected: String?
    public let onPick: (String) -> Void

    public init(
        hole: Int,
        toPinYd: Int,
        clubs: [Club],
        recommended: String,
        selected: String? = nil,
        onPick: @escaping (String) -> Void = { _ in }
    ) {
        self.hole = hole
        self.toPinYd = toPinYd
        self.clubs = clubs
        self.recommended = recommended
        self.selected = selected
        self.onPick = onPick
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            // Top: still shows the new distance to the pin (so recording never hides the number).
            HStack(spacing: 5) {
                Text("记进第\(hole)洞").font(.system(size: 11, weight: .bold)).foregroundStyle(AICaddieDesignTokens.par)
                Spacer()
                Text("到旗 \(toPinYd)").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary).monospacedDigit()
            }
            Text("刚打这杆用的?").font(.system(size: 10)).foregroundStyle(.secondary)

            ForEach(clubs) { club in
                Button { onPick(club.name) } label: { row(club) }
                    .buttonStyle(.plain)
            }

            Text("转表冠选 · 放 8 秒自动记推荐").font(.system(size: 8.5, weight: .medium)).foregroundStyle(.tertiary)
        }
        .padding(8)
    }

    @ViewBuilder private func row(_ club: Club) -> some View {
        let isRec = club.name == recommended
        let isSel = club.name == selected
        HStack(spacing: 6) {
            Text(club.name).font(.system(size: 15, weight: .bold))
            if let c = club.carryYd {
                Text("\(c)").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary).monospacedDigit()
            }
            Spacer()
            if isSel {
                Text("已选").font(.system(size: 9, weight: .black)).foregroundStyle(.black.opacity(0.7))
            } else if isRec {
                Text("推荐").font(.system(size: 9, weight: .black)).opacity(0.75)
            }
        }
        .padding(.horizontal, 9).padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .foregroundStyle(isSel || isRec ? Color.black : Color.white)
        .background(
            RoundedRectangle(cornerRadius: 9).fill(
                isSel ? AnyShapeStyle(LinearGradient(colors: [Color(red: 0.35, green: 0.78, blue: 0.98), Color(red: 0.17, green: 0.62, blue: 0.84)], startPoint: .top, endPoint: .bottom))
                      : isRec ? AnyShapeStyle(LinearGradient(colors: [Color(red: 0.30, green: 0.86, blue: 0.46), Color(red: 0.17, green: 0.66, blue: 0.37)], startPoint: .top, endPoint: .bottom))
                      : AnyShapeStyle(Color.white.opacity(0.08))
            )
        )
    }
}
